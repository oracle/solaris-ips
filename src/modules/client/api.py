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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import copy
import errno
import os
import pkg.client.bootenv as bootenv
import pkg.client.image as image
import pkg.client.api_errors as api_errors
import pkg.client.history as history
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.search_errors as search_errors
from pkg.client.imageplan import EXECUTED_OK
from pkg.client import global_settings
import simplejson as json
import threading
import urllib2

CURRENT_API_VERSION = 11
CURRENT_P5I_VERSION = 1

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

                compatible_versions = set([11])

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
                self.be_name = None

                self.__can_be_canceled = False
                self.__canceling = False

                self.__activity_lock = threading.Lock()

        @staticmethod
        def check_be_name(be_name):
                return bootenv.BootEnv.check_be_name(be_name)

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
                PlanCreationException, NetworkUnavailableException,
                PermissionsException and InventoryException. The noexecute
                argument is included for compatibility with operational
                history. The hope is it can be removed in the future."""

                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        if self.plan_type is not None:
                                raise api_errors.PlanExistsException(
                                    self.plan_type)
                        try:
                                self.log_operation_start("install")
                                # Verify validity of certificates before
                                # attempting network operations.
                                try:
                                        self.img.check_cert_validity()
                                except api_errors.ExpiringCertificate, e:
                                        misc.emsg(e)
                                except api_errors.CertificateError, e:
                                        self.log_operation_end(error=e)
                                        raise

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
                                        self.log_operation_end(
                                            result=history.RESULT_NOTHING_TO_DO)
                                self.img.imageplan.update_index = update_index
                                res = not self.img.imageplan.nothingtodo()
                        except api_errors.PlanCreationException, e:
                                self.__reset_unlock()
                                self.__set_history_PlanCreationException(e)
                                raise
                        except (api_errors.CanceledException, fmri.IllegalFmri,
                            Exception), e:
                                self.__reset_unlock()
                                self.log_operation_end(error=e)
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
                                self.log_operation_start("uninstall")
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
            noexecute=False, force=False, verbose=False, update_index=True,
            be_name=None):
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
                                self.log_operation_start("image-update")
                                exception_caught = None
                                if not self.check_be_name(be_name):
                                        raise api_errors.InvalidBENameException(
                                            be_name)
                                self.be_name = be_name

                                # Verify validity of certificates before
                                # attempting network operations.
                                try:
                                        self.img.check_cert_validity()
                                except api_errors.ExpiringCertificate, e:
                                        misc.emsg(e)
                                except api_errors.CertificateError, e:
                                        self.log_operation_end(error=e)
                                        raise

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
                                                    refresh_catalogs,
                                                    self.progresstracker):
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
                        except (api_errors.BENamingNotSupported,
                            api_errors.InvalidBENameException):
                                self.__reset_unlock()
                                self.img.history.operation_result = \
                                    history.RESULT_FAILED_BAD_REQUEST
                                raise
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
                                be.init_image_recovery(self.img, self.be_name)
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


        def refresh(self, full_refresh, pubs=None):
                """Refreshes the metadata for a publisher (e.g. catalog).

                'full_refresh' is a boolean value indicating whether a full
                retrieval of the catalog or only an update to the existing
                catalog should be performed.

                'pubs' is a list of prefixes of publishers to refresh.  Passing
                an empty list or using the default value means all known
                publishers will be refreshed.

                Currently returns an image object, allowing existing code to
                work while the rest of the API is put into place."""

                self.log_operation_start("refresh-publisher")
                self.__activity_lock.acquire()
                self.__set_can_be_canceled(False)
                try:
                        # Verify validity of certificates before attempting
                        # network operations.
                        try:
                                self.img.check_cert_validity()
                        except api_errors.ExpiringCertificate, e:
                                misc.emsg(e)

                        pubs_to_refresh = []

                        if not pubs:
                                # Omit disabled publishers.
                                pubs = [p for p in self.img.gen_publishers()]
                        for pub in pubs:
                                p = pub
                                if not isinstance(p, publisher.Publisher):
                                        p = self.img.get_publisher(prefix=pub)
                                if p.disabled:
                                        raise api_errors.DisabledPublisher(pub)
                                pubs_to_refresh.append(p)

                        # Ensure Image directory structure is valid.
                        self.img.mkdirs()

                        # Loading catalogs allows us to perform incremental
                        # update
                        self.img.load_catalogs(self.progresstracker)

                        self.img.retrieve_catalogs(full_refresh,
                            pubs_to_refresh)

                        return self.img

                finally:
                        self.__activity_lock.release()
                        self.log_operation_end()

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

        def info(self, fmri_strings, local, info_needed):
                """Gathers information about fmris.  fmri_strings is a list
                of fmri_names for which information is desired.  local
                determines whether to retrieve the information locally.  It
                returns a dictionary of lists.  The keys for the dictionary are
                the constants specified in the class definition.  The values are
                lists of PackageInfo objects or strings."""

                bad_opts = info_needed - PackageInfo.ALL_OPTIONS
                if bad_opts:
                        raise api_errors.UnrecognizedOptionsToInfo(bad_opts)

                self.log_operation_start("info")
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
                        # network operations.
                        try:
                                self.img.check_cert_validity()
                        except api_errors.ExpiringCertificate, e:
                                misc.emsg(e)
                        except api_errors.CertificateError, e:
                                self.log_operation_end(error=e)
                                raise

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
                                        if m.preferred_publisher():
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
                        pub = name = version = release = None
                        build_release = branch = packaging_date = None
                        if PackageInfo.IDENTITY in info_needed:
                                pub, name, version = f.tuple()
                                pub = fmri.strip_pub_pfx(pub)
                                release = version.release
                                build_release = version.build_release
                                branch = version.branch
                                packaging_date = version.get_timestamp().ctime()
                        pref_pub = None
                        if PackageInfo.PREF_AUTHORITY in info_needed:
                                pref_pub = False
                                if f.preferred_publisher():
                                        pref_pub = True
                        state = None
                        if PackageInfo.STATE in info_needed:
                                if self.img.is_installed(f):
                                        state = PackageInfo.INSTALLED
                                else:
                                        state = PackageInfo.NOT_INSTALLED
                        links = hardlinks = files = dirs = dependencies = None
                        summary = size = licenses = cat_info = None

                        if (frozenset([PackageInfo.SIZE, PackageInfo.LICENSES,
                            PackageInfo.SUMMARY, PackageInfo.CATEGORIES]) |
                            PackageInfo.ACTION_OPTIONS) & info_needed:
                                mfst = self.img.get_manifest(f)
                                if PackageInfo.SIZE in info_needed:
                                        size=mfst.size
                                if PackageInfo.LICENSES in info_needed:
                                        licenses = self.__licenses(mfst, local)
                                if PackageInfo.SUMMARY in info_needed:
                                        summary = mfst.get("description", "")

                                if PackageInfo.ACTION_OPTIONS & info_needed:
                                        excludes = self.img.list_excludes()
                                        if PackageInfo.LINKS in info_needed:
                                                links = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "link", excludes))
                                        if PackageInfo.HARDLINKS in info_needed:
                                                hardlinks = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "hardlink", excludes))
                                        if PackageInfo.FILES in info_needed:
                                                files = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "file", excludes))
                                        if PackageInfo.DIRS in info_needed:
                                                dirs = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "dir", excludes))
                                        if PackageInfo.DEPENDENCIES in \
                                            info_needed:
                                                dependencies = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "depend", excludes))

                                if PackageInfo.CATEGORIES in info_needed:
                                        cat_info = [
                                            PackageCategory(scheme, cat)
                                            for ca
                                            in mfst.gen_actions_by_type("set")
                                            if ca.has_category_info()
                                            for scheme, cat
                                            in ca.parse_category_info()
                                        ]

                        pis.append(PackageInfo(pkg_stem=name, summary=summary,
                            category_info_list=cat_info, state=state,
                            publisher=pub, preferred_publisher=pref_pub,
                            version=release, build_release=build_release,
                            branch=branch, packaging_date=packaging_date,
                            size=size, pfmri=str(f), licenses=licenses,
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
                        self.log_operation_end(error=e,
                            result=history.RESULT_FAILED_BAD_REQUEST)
                elif e.constraint_violations:
                        self.log_operation_end(error=e,
                            result=history.RESULT_FAILED_CONSTRAINED)
                else:
                        self.log_operation_end(error=e)

        def add_publisher(self, pub, refresh_allowed=True):
                """Add the provided publisher object to the image
                configuration."""
                self.img.add_publisher(pub, refresh_allowed=refresh_allowed)

        def get_preferred_publisher(self):
                """Returns the preferred publisher object for the image."""
                return self.get_publisher(
                    prefix=self.img.get_preferred_publisher())

        def get_publisher(self, prefix=None, alias=None, duplicate=False):
                """Retrieves a publisher object matching the provided prefix
                (name) or alias.

                'duplicate' is an optional boolean value indicating whether
                a copy of the publisher object should be returned instead
                of the original.
                """
                pub = self.img.get_publisher(prefix=prefix, alias=alias)
                if duplicate:
                        # Never return the original so that changes to the
                        # retrieved object are not reflected until
                        # update_publisher is called.
                        return copy.copy(pub)
                return pub

        def get_publishers(self, duplicate=False):
                """Returns a list of the publisher objects for the current
                image.

                'duplicate' is an optional boolean value indicating whether
                copies of the publisher objects should be returned instead
                of the originals.
                """
                if duplicate:
                        # Return a copy so that changes to the retrieved objects
                        # are not reflected until update_publisher is called.
                        pubs = [
                            copy.copy(p)
                            for p in self.img.get_publishers().values()
                        ]
                else:
                        pubs = self.img.get_publishers().values()
                return misc.get_sorted_publishers(pubs,
                    preferred=self.img.get_preferred_publisher())

        def get_publisher_last_update_time(self, prefix=None, alias=None):
                """Returns a datetime object representing the last time the
                catalog for a publisher was modified or None."""
                if alias:
                        prefix = self.get_publisher(alias=alias).prefix
                dt = None
                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        try:
                                dt = self.img.get_publisher_last_update_time(
                                    prefix)
                        except api_errors.CanceledException:
                                self.__reset_unlock()
                                raise
                        except Exception:
                                self.__reset_unlock()
                                raise
                finally:
                        self.__activity_lock.release()
                return dt

        def has_publisher(self, prefix=None, alias=None):
                """Retrieves a publisher object matching the provided prefix
                (name) or alias."""
                return self.img.has_publisher(prefix=prefix, alias=alias)

        def remove_publisher(self, prefix=None, alias=None):
                """Removes a publisher object matching the provided prefix
                (name) or alias."""
                self.img.remove_publisher(prefix=prefix, alias=alias)

        def set_preferred_publisher(self, prefix=None, alias=None):
                """Sets the preferred publisher for the image."""
                self.img.set_preferred_publisher(prefix=prefix, alias=alias)

        def update_publisher(self, pub, refresh_allowed=True):
                """Replaces an existing publisher object with the provided one
                using the _source_object_id identifier set during copy.

                'refresh_allowed' is an optional boolean value indicating
                whether a refresh of publisher metadata (such as its catalog)
                should be performed if transport information is changed for a
                repository, mirror, or origin.  If False, no attempt will be
                made to retrieve publisher metadata."""

                self.log_operation_start("update-publisher")

                if pub.disabled and \
                    pub.prefix == self.img.get_preferred_publisher():
                        raise api_errors.SetPreferredPublisherDisabled(
                            pub.prefix)

                refresh_catalog = False
                purge_catalog = False

                def need_refresh(oldo, newo):
                        if oldo.disabled and not newo.disabled:
                                # The publisher has been re-enabled, so
                                # retrieve the catalog.
                                return True

                        if len(newo.repositories) != len(oldo.repositories):
                                # If there are an unequal number of repositories
                                # then some have been added or removed.
                                return True

                        matched = 0
                        for oldr in oldo.repositories:
                                for newr in newo.repositories:
                                        if newr._source_object_id == id(oldr):
                                                matched += 1
                                                if oldr.origins != newr.origins:
                                                        return True

                        if matched != len(newo.repositories):
                                # If not all of the repositories match up, then
                                # one has been removed or added, or an origin
                                # URI has changed.
                                return True
                        return False

                updated = False
                publishers = self.img.get_publishers()
                for key, old in publishers.iteritems():
                        if pub._source_object_id == id(old):
                                if need_refresh(old, pub):
                                        refresh_catalog = True
                                elif pub.disabled:
                                        purge_catalog = True
                                del publishers[key]
                                publishers[pub.prefix] = pub
                                updated = True

                if not updated:
                        # If a matching publisher couldn't be found and
                        # replaced, something is wrong (client api usage
                        # error).
                        e = api_errors.UnknownPublisher(pub)
                        self.log_operation_end(e)
                        raise e

                if refresh_allowed and not refresh_catalog:
                        # If the publisher's catalog is missing, retrieve it.
                        refresh_catalog = not self.img.has_catalog(pub.prefix)

                if refresh_catalog or purge_catalog:
                        try:
                                self.img.destroy_catalog(pub)
                                self.img.destroy_catalog_cache()
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                raise

                        if purge_catalog:
                                self.img.cache_catalogs()
                        elif refresh_allowed:
                                self.refresh(True, pubs=[pub])

                # Successful refresh or purge has happened, so save
                # final configuration.
                self.img.save_config()
                self.log_operation_end()
                return

        def log_operation_end(self, error=None, result=None):
                """Marks the end of an operation to be recorded in image
                history.

                'result' should be a pkg.client.history constant value
                representing the outcome of an operation.  If not provided,
                and 'error' is provided, the final result of the operation will
                be based on the class of 'error' and 'error' will be recorded
                for the current operation.  If 'result' and 'error' is not
                provided, success is assumed."""
                self.img.history.log_operation_end(error=error, result=result)

        def log_operation_error(self, error):
                """Adds an error to the list of errors to be recorded in image
                history for the current opreation."""
                self.img.history.log_operation_error(error)

        def log_operation_start(self, name):
                """Marks the start of an operation to be recorded in image
                history."""
                self.img.history.log_operation_start(name)

        def parse_p5i(self, fileobj=None, location=None):
                """Reads the pkg(5) publisher json formatted data at 'location'
                or from the provided file-like object 'fileobj' and returns a
                list of tuples of the format (publisher object, pkg_names).
                pkg_names is a list of strings representing package names or
                FMRIs.  If any pkg_names not specific to a publisher were
                provided, the last tuple returned will be of the format (None,
                pkg_names).

                'fileobj' is an optional file-like object that must support a
                'read' method for retrieving data.

                'location' is an optional string value that should either start
                with a leading slash and be pathname of a file or a URI string.
                If it is a URI string, supported protocol schemes are 'file',
                'ftp', 'http', and 'https'.

                'fileobj' or 'location' must be provided."""

                if location is None and fileobj is None:
                        raise api_errors.InvalidResourceLocation(location)

                if location:
                        if location.startswith(os.path.sep):
                                location = os.path.abspath(location)
                                location = "file://" + location

                        try:
                                fileobj = urllib2.urlopen(location)
                        except (EnvironmentError, ValueError,
                            urllib2.HTTPError), e:
                                raise api_errors.RetrievalError(e,
                                    location=location)

                try:
                        dump_struct = json.load(fileobj)
                except (EnvironmentError, urllib2.HTTPError), e:
                        raise api_errors.RetrievalError(e)
                except ValueError, e:
                        # Not a valid json file.
                        raise api_errors.InvalidP5IFile(e)

                try:
                        ver = int(dump_struct["version"])
                except KeyError:
                        raise api_errors.InvalidP5IFile(_("missing version"))
                except ValueError:
                        raise api_errors.InvalidP5IFile(_("invalid version"))

                if ver > CURRENT_P5I_VERSION:
                        raise api_errors.UnsupportedP5IFile()

                result = []
                try:
                        plist = dump_struct.get("publishers", [])

                        for p in plist:
                                alias = p.get("alias", None)
                                prefix = p.get("name", None)

                                if not prefix:
                                        prefix = "Unknown"

                                pub = publisher.Publisher(prefix, alias=alias)
                                pkglist = p.get("packages", [])
                                result.append((pub, pkglist))

                                for r in p.get("repositories", []):
                                        rargs = {}
                                        for prop in ("collection_type",
                                            "description", "name",
                                            "refresh_seconds",
                                            "registration_uri"):
                                                val = r.get(prop, None)
                                                if val is None or val == "None":
                                                        continue
                                                rargs[prop] = val

                                        for prop in ("legal_uris", "mirrors",
                                            "origins", "related_uris"):
                                                val = r.get(prop, [])
                                                if not isinstance(val, list):
                                                        continue
                                                rargs[prop] = val

                                        if rargs.get("origins", None):
                                                repo = publisher.Repository(
                                                    **rargs)
                                                pub.add_repository(repo)

                        pkglist = dump_struct.get("packages", [])
                        if pkglist:
                                result.append((None, pkglist))
                except (api_errors.PublisherError, TypeError, ValueError), e:
                        raise api_errors.InvalidP5IFile(str(e))
                return result

        def write_p5i(self, fileobj, pkg_names=None, pubs=None):
                """Writes the publisher, repository, and provided package names
                to the provided file-like object 'fileobj' in json p5i format.

                'fileobj' is only required to have a 'write' method that accepts
                data to be written as a parameter.

                'pkg_names' is a dict of lists, tuples, or sets indexed by
                publisher prefix that contain package names, FMRI strings, or
                package info objects.  A prefix of "" can be used for packages
                that are not specific to a publisher.

                'pubs' is an optional list of publisher prefixes or Publisher
                objects.  If not provided, the information for all publishers
                (excluding those disabled) will be output."""

                dump_struct = {
                    "packages": [],
                    "publishers": [],
                    "version": CURRENT_P5I_VERSION,
                }

                if not pubs:
                        plist = [
                            p for p in self.get_publishers()
                            if not p.disabled
                        ]
                else:
                        plist = []
                        for p in pubs:
                                if not isinstance(p, publisher.Publisher):
                                        plist.append(self.img.get_publisher(
                                            prefix=p, alias=p))
                                else:
                                        plist.append(p)

                if pkg_names is None:
                        pkg_names = {}

                def copy_pkg_names(source, dest):
                        for entry in source:
                                # Publisher information is intentionally
                                # omitted as association with this specific
                                # publisher is implied by location in the
                                # output.
                                if isinstance(entry, PackageInfo):
                                        dest.append(entry.fmri.get_fmri(
                                            anarchy=True))
                                elif isinstance(entry, fmri.PkgFmri):
                                        dest.append(entry.get_fmri(
                                            anarchy=True))
                                else:
                                        dest.append(str(entry))

                dpubs = dump_struct["publishers"]
                for p in plist:
                        dpub = {
                            "alias": p.alias,
                            "name": p.prefix,
                            "packages": [],
                            "repositories": []
                        }
                        dpubs.append(dpub)

                        try:
                                copy_pkg_names(pkg_names[p.prefix],
                                    dpub["packages"])
                        except KeyError:
                                pass

                        drepos = dpub["repositories"]
                        for r in p.repositories:
                                reg_uri = ""
                                if r.registration_uri:
                                        reg_uri = r.registration_uri.uri

                                drepos.append({
                                    "collection_type": r.collection_type,
                                    "description": r.description,
                                    "legal_uris": [u.uri for u in r.legal_uris],
                                    "mirrors": [u.uri for u in r.mirrors],
                                    "name": r.name,
                                    "origins": [u.uri for u in r.origins],
                                    "refresh_seconds": r.refresh_seconds,
                                    "registration_uri": reg_uri,
                                    "related_uris": [
                                        u.uri for u in r.related_uris
                                    ],
                                })

                try:
                        copy_pkg_names(pkg_names[""], dump_struct["packages"])
                except KeyError:
                        pass

                return json.dump(dump_struct, fileobj, ensure_ascii=False,
                    allow_nan=False, indent=2, sort_keys=True)


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



        __NUM_PROPS = 12
        IDENTITY, SUMMARY, CATEGORIES, STATE, PREF_AUTHORITY, SIZE, LICENSES, \
            LINKS, HARDLINKS, FILES, DIRS, DEPENDENCIES = range(__NUM_PROPS)
        ALL_OPTIONS = frozenset(range(__NUM_PROPS))
        ACTION_OPTIONS = frozenset([LINKS, HARDLINKS, FILES, DIRS,
            DEPENDENCIES])

        def __init__(self, pfmri, pkg_stem=None, summary=None,
            category_info_list=None, state=None, publisher=None,
            preferred_publisher=None, version=None, build_release=None,
            branch=None, packaging_date=None, size=None, licenses=None,
            links=None, hardlinks=None, files=None, dirs=None,
            dependencies=None):
                self.pkg_stem = pkg_stem
                self.summary = summary
                if category_info_list is None:
                        category_info_list = []
                self.category_info_list = category_info_list
                self.state = state
                self.publisher = publisher
                self.preferred_publisher = preferred_publisher
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
                pub, name, version = f.tuple()
                pub = fmri.strip_pub_pfx(pub)
                return PackageInfo(pkg_stem=name, publisher=pub,
                    version=version.release,
                    build_release=version.build_release, branch=version.branch,
                    packaging_date=version.get_timestamp().ctime(),
                    pfmri=str(f))
