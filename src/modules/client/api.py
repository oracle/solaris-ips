#!/usr/bin/python2.4
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import pkg.search_errors as search_errors
import pkg.client.bootenv as bootenv
import pkg.client.image as image
import pkg.client.api_errors as api_errors
import pkg.client.history as history
import pkg.misc as misc
import pkg.fmri as fmri
from pkg.client.imageplan import EXECUTED_OK
from pkg.client import global_settings

import threading

CURRENT_API_VERSION = 7

class ImageInterface(object):
        """This class presents an interface to images that clients may use.
        There is a specific order of methods which must be used to install
        or uninstall packages, or update an image. First, plan_install,
        plan_uninstall, or plan_update_all must be called. After that
        method completes successfully, describe may be called, and prepare
        must be called. Finally, execute_plan may be called to implement
        the previous created plan. The other methods do not hav an ordering
        imposed upon them, and may be used as needed. Cancel may only be
        invoked while a cancelable method is running."""

        # Constants used to reference specific values that info can return.
        INFO_FOUND = 0
        INFO_MISSING = 1
        INFO_MULTI_MATCH = 2
        INFO_ILLEGALS = 3

        # Private constants used for tracking which type of plan was made.
        __INSTALL = 1
        __UNINSTALL = 2
        __IMAGE_UPDATE = 3

        def __init__(self, img_path, version_id, progesstracker,
            cancel_state_callable, pkg_client_name):
                """Constructs an ImageInterface. img_path should point to an
                existing image. version_id indicates the version of the api
                the client is expecting to use. progesstracker is the
                progresstracker the client wants the api to use for UI
                callbacks. cancel_state_callable is a function which the client
                wishes to have called each time whether the operation can be
                canceled changes. It can raise VersionException and
                ImageNotFoundException."""

                compatible_versions = set([1, 2, 3, 4, 5, 6, 7])

                if version_id not in compatible_versions:
                        raise api_errors.VersionException(CURRENT_API_VERSION,
                            version_id)

                # The image's History object will use client_name from
                # global_settings, but if the program forgot to set it,
                # we'll go ahead and do so here.
                if global_settings.client_name is None:
                        global_settings.client_name = pkg_client_name

                # These variables are private and not part of the API.
                self.img = image.Image()
                self.img.find_root(img_path)
                self.img.load_config()
                self.progresstracker = progesstracker
                self.cancel_state_callable = cancel_state_callable
                self.plan_type = None
                self.plan_desc = None
                self.prepared = False
                self.executed = False

                self.__can_be_canceled = False
                self.__canceling = False

                self.__activity_lock = threading.Lock()
                
        def plan_install(self, pkg_list, filters, refresh_catalogs=True,
            noexecute=False, verbose=False, update_index=True):
                """Contructs a plan to install the packages provided in
                pkg_list. pkg_list is a list of packages to install. filters
                is a list of filters to apply to the actions of the installed
                packages. refresh_catalogs controls whether the catalogs will
                automatically be refreshed. noexecute determines whether the
                history will be recorded after planning is finished. verbose
                controls whether verbose debugging output will be printed to the
                terminal. Its existence is temporary. It returns a tuple of
                two things. The first is a boolean which tells the client
                whether there is anything to do. The third is either None, or an
                exception which indicates partial success. It can raise
                InvalidCertException, PlanCreationException,
                NetworkUnavailableException, PermissionsException and
                InventoryException. The noexecute argument is included for
                compatibility with operational history. The hope is it can be
                removed in the future."""

                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        if self.plan_type is not None:
                                raise api_errors.PlanExistsException(
                                    self.plan_type)
                        try:
                                self.img.history.operation_name = "install"
                                # Verify validity of certificates before
                                # attempting network operations
                                if not self.img.check_cert_validity():
                                        raise api_errors.InvalidCertException()

                                self.img.load_catalogs(self.progresstracker)

                                exception_caught = None
                                if refresh_catalogs:
                                        try:
                                                self.img.retrieve_catalogs(
                                                    progtrack=self.progresstracker)
                                        except api_errors.CatalogRefreshException, e:
                                                if not e.succeeded:
                                                        raise
                                                exception_caught = e

                                        # Reload catalog. This picks up the
                                        # update from retrieve_catalogs.
                                        self.img.load_catalogs(
                                            self.progresstracker)

                                self.img.make_install_plan(pkg_list,
                                    self.progresstracker,
                                    self.__check_cancelation, noexecute,
                                    filters=filters, verbose=verbose)

                                assert self.img.imageplan

                                if self.__canceling:
                                        raise api_errors.CanceledException()
                                self.__set_can_be_canceled(False)

                                if not noexecute:
                                        self.plan_type = self.__INSTALL

                                self.plan_desc = PlanDescription(
                                    self.img.imageplan)
                                if self.img.imageplan.nothingtodo() or \
                                    noexecute:
                                        self.img.history.operation_result = \
                                            history.RESULT_NOTHING_TO_DO
                                self.img.imageplan.update_index = update_index
                                res = not self.img.imageplan.nothingtodo()
                        except api_errors.CanceledException:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_CANCELED
                                raise
                        except api_errors.PlanCreationException, e:
                                self.__reset_unlock()
                                self.__set_history_PlanCreationException(e)
                                raise
                        except fmri.IllegalFmri:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_BAD_REQUEST
                                raise
                        except Exception:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_UNKNOWN
                                raise
                finally:
                        self.__activity_lock.release()
                
                return res, exception_caught


        def plan_uninstall(self, pkg_list, recursive_removal, noexecute=False,
            verbose=False, update_index=True):
                """Contructs a plan to uninstall the packages provided in
                pkg_list. pkg_list is a list of packages to install.
                recursive_removal controls whether recursive removal is
                allowed. noexecute determines whether the history will be
                recorded after planning is finished. verbose controls whether
                verbose debugging output will be printed to the terminal. Its
                existence is temporary. If there are things to do to complete
                the uninstall, it returns True, otherwise it returns False. It
                can raise NonLeafPackageException and PlanCreationException."""

                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        if self.plan_type is not None:
                                raise api_errors.PlanExistsException(
                                    self.plan_type)
                        try:
                                self.img.history.operation_name = "uninstall"
                                self.img.load_catalogs(self.progresstracker)

                                self.img.make_uninstall_plan(pkg_list,
                                    recursive_removal, self.progresstracker,
                                    self.__check_cancelation, noexecute,
                                    verbose=verbose)

                                assert self.img.imageplan

                                if self.__canceling:
                                        raise api_errors.CanceledException()
                                self.__set_can_be_canceled(False)

                                if not noexecute:
                                        self.plan_type = self.__UNINSTALL

                                self.plan_desc = PlanDescription(
                                    self.img.imageplan)
                                if noexecute:
                                        self.img.history.operation_result = \
                                            history.RESULT_NOTHING_TO_DO
                                self.img.imageplan.update_index = update_index
                                res = not self.img.imageplan.nothingtodo()
                        except api_errors.CanceledException:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_CANCELED
                                raise
                        except api_errors.NonLeafPackageException, e:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_CONSTRAINED
                                raise
                        except api_errors.PlanCreationException, e:
                                self.__reset_unlock()
                                self.__set_history_PlanCreationException(e)
                                raise
                        except fmri.IllegalFmri:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_BAD_REQUEST
                                raise
                        except Exception:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_UNKNOWN
                                raise
                finally:
                        self.__activity_lock.release()

                return res
                
        def plan_update_all(self, actual_cmd, refresh_catalogs=True,
            noexecute=False, force=False, verbose=False, update_index=True):
                """Creates a plan to update all packages on the system to the
                latest known versions. actual_cmd is the command used to start
                the client. It is used to determine the image to check whether
                SUNWipkg is up to date. refresh_catalogs controls whether the
                catalogs will automatically be refreshed. noexecute determines
                whether the history will be recorded after planning is finished.
                force controls whether update should proceed even if ipkg is not
                up to date. verbose controls whether verbose debugging output
                will be printed to the terminal. Its existence is temporary. It
                returns a tuple of three things. The first is a boolean which
                tells the client whether there is anything to do. The second
                tells whether the image is an opensolaris image. The third is
                either None, or an exception which indicates partial success.
                This is currently used to indicate a failure in refreshing
                catalogs. It can raise CatalogRefreshException,
                IpkgOutOfDateException, NetworkUnavailableException,
                PlanCreationException and PermissionsException."""

                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        if self.plan_type is not None:
                                raise api_errors.PlanExistsException(
                                    self.plan_type)
                        try:
                                self.img.history.operation_name = "image-update"
                                exception_caught = None

                                # Verify validity of certificates before
                                # attempting network operations
                                if not self.img.check_cert_validity():
                                        raise api_errors.InvalidCertException()

                                self.img.load_catalogs(self.progresstracker)

                                if refresh_catalogs:
                                        try:
                                                self.img.retrieve_catalogs(
                                                    progtrack=self.progresstracker)
                                        except api_errors.CatalogRefreshException, e:
                                                if not e.succeeded:
                                                        raise
                                                exception_caught = e

                                        # Reload catalog. This picks up the
                                        # update from retrieve_catalogs.
                                        self.img.load_catalogs(
                                            self.progresstracker)

                                # If we can find SUNWipkg and SUNWcs in the
                                # target image, then we assume this is a valid
                                # opensolaris image, and activate some
                                # special case behaviors.
                                opensolaris_image = True
                                fmris, notfound, illegals = \
                                    self.img.installed_fmris_from_args(
                                        ["SUNWipkg", "SUNWcs"])
                                assert(len(illegals) == 0)
                                if notfound:
                                        opensolaris_image = False

                                if opensolaris_image and not force:
                                        try:
                                                if not \
                                                    self.img.ipkg_is_up_to_date(
                                                    actual_cmd,
                                                    self.__check_cancelation,
                                                    noexecute,
                                                    refresh_catalogs, self.progresstracker):
                                                        self.img.history.operation_result = \
                                                            history.RESULT_FAILED_CONSTRAINED
                                                        raise api_errors.IpkgOutOfDateException()
                                        except api_errors.ImageNotFoundException:
                                                # We can't answer in this case,
                                                # so we proceed
                                                pass

                                pkg_list = [ 
                                        ipkg.get_pkg_stem()
                                        for ipkg in self.img.gen_installed_pkgs() 
                                ]

                                self.img.make_install_plan(pkg_list,
                                    self.progresstracker,
                                    self.__check_cancelation,
                                    noexecute, verbose=verbose)

                                assert self.img.imageplan

                                if self.__canceling:
                                        self.__reset_unlock()
                                        raise api_errors.CanceledException()
                                self.__set_can_be_canceled(False)

                                if not noexecute:
                                        self.plan_type = self.__IMAGE_UPDATE

                                self.plan_desc = PlanDescription(
                                    self.img.imageplan)

                                if self.img.imageplan.nothingtodo() or \
                                    noexecute:
                                        self.img.history.operation_result = \
                                            history.RESULT_NOTHING_TO_DO
                                self.img.imageplan.update_index = update_index
                                res = not self.img.imageplan.nothingtodo()
                        except api_errors.CanceledException:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_CANCELED
                                raise
                        except api_errors.PlanCreationException, e:
                                self.__reset_unlock()
                                self.__set_history_PlanCreationException(e)
                                raise
                        except api_errors.IpkgOutOfDateException:
                                self.__reset_unlock()
                                raise
                        except Exception:
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_UNKNOWN
                                raise
                finally:
                        self.__activity_lock.release()
                
                return res, opensolaris_image, exception_caught

        def describe(self):
                """Returns None if no plan is ready yet, otherwise returns
                a PlanDescription"""
                return self.plan_desc
                
        def prepare(self):
                """Takes care of things which must be done before the plan
                can be executed. This includes downloading the packages to
                disk and preparing the indexes to be updated during
                execution. It can raise ProblematicPermissionsIndexException,
                and PlanMissingException. Should only be called once a
                plan_X method has been called."""

                self.__activity_lock.acquire()
                self.__set_can_be_canceled(True)

                try:
                        try:
                                if not self.img.imageplan:
                                        raise api_errors.PlanMissingException()

                                if self.prepared:
                                        raise api_errors.AlreadyPreparedException()
                                assert self.plan_type == self.__INSTALL or \
                                    self.plan_type == self.__UNINSTALL or \
                                    self.plan_type == self.__IMAGE_UPDATE
                                try:
                                        self.img.imageplan.preexecute()
                                except search_errors.ProblematicPermissionsIndexException, e:
                                        self.img.cleanup_downloads()
                                        raise api_errors.ProblematicPermissionsIndexException(e)
                                except Exception, e:
                                        self.img.cleanup_downloads()
                                        raise

                                if self.__canceling:
                                        self.img.cleanup_downloads()
                                        raise api_errors.CanceledException()
                                self.prepared = True
                        except Exception:
                                if self.img.history.operation_result:
                                        self.img.history.operation_result = \
                                            history.RESULT_FAILED_UNKNOWN
                                raise
                finally:
                        self.__set_can_be_canceled(False)
                        self.__activity_lock.release()

        def execute_plan(self):
                """Executes the plan. This is uncancelable one it begins. It
                can raise  CorruptedIndexException,
                ProblematicPermissionsIndexException, ImageplanStateException,
                ImageUpdateOnLiveImageException, and PlanMissingException.
                Should only be called after the prepare method has been
                called."""

                self.__activity_lock.acquire()
                self.__set_can_be_canceled(False)
                try:
                        if not self.img.imageplan:
                                raise api_errors.PlanMissingException()

                        if not self.prepared:
                                raise api_errors.PrematureExecutionException()

                        if self.executed:
                                raise api_errors.AlreadyExecutedException()
                        
                        assert self.plan_type == self.__INSTALL or \
                            self.plan_type == self.__UNINSTALL or \
                            self.plan_type == self.__IMAGE_UPDATE
                        try:
                                be = bootenv.BootEnv(self.img.get_root())
                        except RuntimeError:
                                be = bootenv.BootEnvNull(self.img.get_root())

                        if self.plan_type is self.__IMAGE_UPDATE:
                                be.init_image_recovery(self.img)
                                if self.img.is_liveroot():
                                        self.img.history.operation_result = \
                                            history.RESULT_FAILED_BAD_REQUEST
                                        raise api_errors.ImageUpdateOnLiveImageException()

                        try:
                                self.img.imageplan.execute()

                                if self.plan_type is self.__IMAGE_UPDATE:
                                        be.activate_image()
                                else:
                                        be.activate_install_uninstall()
                                ret_code = 0
                        except RuntimeError, e:
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_UNKNOWN
                                if self.plan_type is self.__IMAGE_UPDATE:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                self.img.cleanup_downloads()
                                raise
                        except search_errors.ProblematicPermissionsIndexException, e:
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_STORAGE
                                self.img.cleanup_downloads()
                                raise api_errors.ProblematicPermissionsIndexException(e)
                        except (search_errors.InconsistentIndexException,
                                search_errors.PartialIndexingException), e:
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_SEARCH
                                self.img.cleanup_downloads()
                                raise api_errors.CorruptedIndexException(e)
                        except Exception, e:
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_UNKNOWN
                                if self.plan_type is self.__IMAGE_UPDATE:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                self.img.cleanup_downloads()
                                raise

                        if self.img.imageplan.state != EXECUTED_OK:
                                if self.plan_type is self.__IMAGE_UPDATE:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                raise api_errors.ImageplanStateException(
                                    self.img.imageplan.state)

                        self.img.cleanup_downloads()
                        self.img.cleanup_cached_content()
                        self.img.history.operation_result = \
                            history.RESULT_SUCCEEDED
                        self.executed = True
                finally:
                        self.__activity_lock.release()
                        
                
        def refresh(self, full_refresh, auths=None):
                """Refreshes the catalogs. full_refresh controls whether to do
                a full retrieval of the catalog from the authority or only
                update the existing catalog. auths is a list of authorities to
                refresh. Passing an empty list or using the default value means
                all known authorities will be refreshed. While it currently
                returns an image object, this is an expedient for allowing
                existing code to work while the rest of the API is put into
                place."""
                
                self.__activity_lock.acquire()
                self.__set_can_be_canceled(False)
                try:
                        # Verify validity of certificates before attempting
                        # network operations
                        if not self.img.check_cert_validity():
                                raise api_errors.InvalidCertException()

                        auths_to_refresh = []
                        
                        if not auths:
                                auths = []
                        for auth in auths:
                                try:
                                        auth = self.img.get_authority(auth)
                                except KeyError:
                                        raise api_errors.UnrecognizedAuthorityException(auth)
                                auths_to_refresh.append(auth)


                        # Ensure Image directory structure is valid.
                        self.img.mkdirs()

                        # Loading catalogs allows us to perform incremental
                        # update
                        self.img.load_catalogs(self.progresstracker)

                        self.img.retrieve_catalogs(full_refresh,
                            auths_to_refresh)

                        return self.img
                        
                finally:
                        self.__activity_lock.release()

        def __licenses(self, mfst, local):
                """Private function. Returns the license info from the
                manifest mfst. Local controls whether the information is
                retrieved locally."""
                license_lst = []
                for lic in mfst.gen_actions_by_type("license"):
                        if not local:
                                s = misc.FilelikeString()
                                hash_val = misc.gunzip_from_stream(
                                    lic.get_remote_opener(self.img,
                                        mfst.fmri)(),
                                    s)
                                text = s.buf
                        else:
                                text = lic.get_local_opener(self.img,
                                    mfst.fmri)().read()[:-1]
                        license_lst.append(LicenseInfo(text))
                return license_lst

        def info(self, fmri_strings, local, get_licenses, get_action_info=False):
                """Gathers information about fmris. fmri_strings is a list
                of fmri_names for which information is desired. local
                determines whether to retrieve the information locally.
                get_licenses determines whether to retrieve the text of
                the licenses. It returns a dictionary of lists. The keys
                for the dictionary are the constants specified in the class
                definition. The values are lists of PackageInfo objects or
                strings."""

                self.img.history.operation_name = "info"
                self.img.load_catalogs(self.progresstracker)

                fmris = []
                notfound = []
                multiple_matches = []
                illegals = []
                
                if local:
                        fmris, notfound, illegals = \
                            self.img.installed_fmris_from_args(fmri_strings)
                        if not fmris and not notfound and not illegals:
                                self.img.history.operation_result = \
                                    history.RESULT_NOTHING_TO_DO
                                raise api_errors.NoPackagesInstalledException()
                else:
                        # Verify validity of certificates before attempting
                        # network operations
                        if not self.img.check_cert_validity():
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_TRANSPORT
                                raise api_errors.InvalidCertException()
                        
                        # XXX This loop really needs not to be copied from
                        # Image.make_install_plan()!
                        for p in fmri_strings:
                                try:
                                        matches = list(self.img.inventory([ p ],
                                            all_known = True))
                                except api_errors.InventoryException, e:
                                        assert(len(e.notfound) == 1 or \
                                            len(e.illegal) == 1)
                                        if e.notfound:
                                                notfound.append(e.notfound[0])
                                        else:
                                                illegals.append(e.illegal[0])
                                        err = 1
                                        continue

                                pnames = {}
                                pmatch = []
                                npnames = {}
                                npmatch = []
                                for m, state in matches:
                                        if m.preferred_authority():
                                                pnames[m.get_pkg_stem()] = 1
                                                pmatch.append(m)
                                        else:
                                                npnames[m.get_pkg_stem()] = 1
                                                npmatch.append(m)

                                if len(pnames.keys()) > 1:
                                        multiple_matches.append(
                                            (p, pnames.keys()))
                                        error = 1
                                        continue
                                elif len(pnames.keys()) < 1 and \
                                    len(npnames.keys()) > 1:
                                        multiple_matches.append(
                                            (p, pnames.keys()))
                                        error = 1
                                        continue

                                # matches is a list reverse sorted by version,
                                # so take the first; i.e., the latest.
                                if len(pmatch) > 0:
                                        fmris.append(pmatch[0])
                                else:
                                        fmris.append(npmatch[0])

                pis = []

                for f in fmris:
                        mfst = self.img.get_manifest(f, filtered=True)
                        licenses = None
                        if get_licenses:
                                licenses = self.__licenses(mfst, local)
                        authority, name, version = f.tuple()
                        authority = fmri.strip_auth_pfx(authority)
                        summary = mfst.get("description", "")
                        pref_auth = False
                        if f.preferred_authority():
                                pref_auth = True
                        if self.img.is_installed(f):
                                state = PackageInfo.INSTALLED
                        else:
                                state = PackageInfo.NOT_INSTALLED
                        links = hardlinks = files = dirs = dependencies = None
                        if get_action_info:
                                links = list(
                                    mfst.gen_key_attribute_value_by_type("link"))
                                hardlinks = list(
                                    mfst.gen_key_attribute_value_by_type(
                                    "hardlink"))
                                files = list(
                                    mfst.gen_key_attribute_value_by_type("file"))
                                dirs = list(
                                    mfst.gen_key_attribute_value_by_type("dir"))
                                dependencies = list(
                                    mfst.gen_key_attribute_value_by_type(
                                    "depend"))
                        cat_info = [
                            PackageCategory(scheme, cat)
                            for ca in mfst.gen_actions_by_type("set")
                            if ca.has_category_info()
                            for scheme, cat in ca.parse_category_info()
                        ]

                        pis.append(PackageInfo(pkg_stem=name, summary=summary,
                            category_info_list=cat_info, state=state,
                            authority=authority,
                            preferred_authority=pref_auth,
                            version=version.release,
                            build_release=version.build_release,
                            branch=version.branch,
                            packaging_date=version.get_timestamp().ctime(),
                            size=mfst.size, pfmri=str(f), licenses=licenses,
                            links=links, hardlinks=hardlinks, files=files,
                            dirs=dirs, dependencies=dependencies))
                if pis:
                        self.img.history.operation_result = \
                            history.RESULT_SUCCEEDED
                elif illegals or multiple_matches:
                        self.img.history.operation_result = \
                            history.RESULT_FAILED_BAD_REQUEST
                else:
                        self.img.history.operation_result = \
                            history.RESULT_NOTHING_TO_DO
                return {
                    self.INFO_FOUND: pis,
                    self.INFO_MISSING: notfound,
                    self.INFO_MULTI_MATCH: multiple_matches,
                    self.INFO_ILLEGALS: illegals
                }
                        
        def can_be_canceled(self):
                """Returns true if the API is in a cancelable state."""
                return self.__can_be_canceled

        def __set_can_be_canceled(self, status):
                """Private method. Handles the details of changing the
                cancelable state."""
                if self.__can_be_canceled != status:
                        self.__can_be_canceled = status
                        if self.cancel_state_callable:
                                self.cancel_state_callable(
                                    self.__can_be_canceled)

        def reset(self):
                """Resets the API back the the initial state. Note:
                this does not necessarily return the disk to its initial state
                since the indexes or download cache may have been changed by
                the prepare method."""
                self.__activity_lock.acquire()
                self.__reset_unlock()
                self.__activity_lock.release()

        def __reset_unlock(self):
                """Private method. Provides a way to reset without taking the
                activity lock. Should only be called by a thread which already
                holds the activity lock."""
                self.img.imageplan = None
                self.plan_desc = None
                self.plan_type = None
                self.prepared = False
                self.executed = False
                self.__set_can_be_canceled(False)
                self.__canceling = False
                self.progresstracker.reset()

        def __check_cancelation(self):
                """Private method. Provides a callback method for internal
                code to use to determine whether the current action has been
                canceled."""
                return self.__canceling
                
        def cancel(self):
                """Used for asynchronous cancelation. It returns the API
                to the state it was in prior to the current method being
                invoked.  Canceling during a plan phase returns the API to
                its initial state. Canceling during prepare puts the API
                into the state it was in just after planning had completed.
                Plan execution cannot be canceled. A call to this method blocks
                until the canelation has happened. Note: this does not
                necessarily return the disk to its initial state since the
                indexes or download cache may have been changed by the
                prepare method."""
                if not self.__can_be_canceled:
                        return False
                self.__set_can_be_canceled(False)
                self.__canceling = True
                # The lock is taken here to make the call block, until
                # the activity has been canceled.
                self.__activity_lock.acquire()
                self.__activity_lock.release()
                self.__canceling = False
                return True

        def __set_history_PlanCreationException(self, e):
                if e.unfound_fmris or e.multiple_matches or \
                    e.missing_matches or e.illegal:
                        self.img.history.operation_result = \
                            history.RESULT_FAILED_BAD_REQUEST
                elif e.constraint_violations:
                        self.img.history.operation_result = \
                            history.RESULT_FAILED_CONSTRAINED
                else:
                        self.img.history.operation_result = \
                            history.RESULT_FAILED_UNKNOWN


class PlanDescription(object):
        """A class which describes the changes the plan will make. It
        provides a list of tuples of PackageInfo's. The first item in the
        tuple is the package that is being changed. The second item in the
        tuple is the package that will be in the image after the change."""
        def __init__(self, imageplan):
                self.__pkgs = \
                        [ (PackageInfo.build_from_fmri(pp.origin_fmri),
                          PackageInfo.build_from_fmri(pp.destination_fmri))
                          for pp
                          in imageplan.pkg_plans ]

        def get_changes(self):
                return self.__pkgs

class LicenseInfo(object):
        """A class representing the license information a package
        provides."""
        def __init__(self, text):
                self.__text = text

        def get_text(self):
                return self.__text

        def __str__(self):
                return self.__text

class PackageCategory(object):
        def __init__(self, scheme, category):
                self.scheme = scheme
                self.category = category

        def __str__(self, verbose=False):
                if verbose:
                        return "%s (%s)" % (self.category, self.scheme)
                else:
                        return "%s" % self.category
        
class PackageInfo(object):
        """A class capturing the information about packages that a client
        could need. The fmri is guaranteed to be set. All other values may
        be None, depending on how the PackageInfo instance was created."""

        # Possible package installation states
        INSTALLED = 1
        NOT_INSTALLED = 2
        
        def __init__(self, pfmri, pkg_stem=None, summary=None,
            category_info_list=None, state=None, authority=None,
            preferred_authority=None, version=None, build_release=None,
            branch=None, packaging_date=None, size=None, licenses=None,
            links=None, hardlinks=None, files=None, dirs=None,
            dependencies=None):
                self.pkg_stem = pkg_stem
                self.summary = summary
                if category_info_list is None:
                        category_info_list = []
                self.category_info_list = category_info_list
                self.state = state
                self.authority = authority
                self.preferred_authority = preferred_authority
                self.version = version
                self.build_release = build_release
                self.branch = branch
                self.packaging_date = packaging_date
                self.size = size
                self.fmri = pfmri
                self.licenses = licenses
                self.links = links
                self.hardlinks = hardlinks
                self.files = files
                self.dirs = dirs
                self.dependencies = dependencies

        def __str__(self):
                return self.fmri

        @staticmethod
        def build_from_fmri(f):
                if not f:
                        return f
                authority, name, version = f.tuple()
                authority = fmri.strip_auth_pfx(authority)
                return PackageInfo(pkg_stem=name, authority=authority,
                    version=version.release,
                    build_release=version.build_release, branch=version.branch,
                    packaging_date=version.get_timestamp().ctime(), pfmri=str(f))
