#!/usr/bin/python
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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import copy
import os
import StringIO
import sys
import urllib

import pkg.client.actuator as actuator
import pkg.client.api_errors as api_errors
import pkg.client.bootenv as bootenv
import pkg.client.history as history
import pkg.client.image as image
import pkg.client.indexer as indexer
import pkg.client.publisher as publisher
import pkg.client.query_parser as query_p
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.p5i as p5i
import pkg.search_errors as search_errors
import pkg.nrlock

from pkg.client.imageplan import EXECUTED_OK
from pkg.client import global_settings

CURRENT_API_VERSION = 24
CURRENT_P5I_VERSION = 1

logger = global_settings.logger

class ImageInterface(object):
        """This class presents an interface to images that clients may use.
        There is a specific order of methods which must be used to install
        or uninstall packages, or update an image. First, plan_install,
        plan_uninstall, plan_update_all or plan_change_variant must be
        called.  After that method completes successfully, describe may be
        called, and prepare must be called. Finally, execute_plan may be
        called to implement the previous created plan. The other methods
        do not have an ordering imposed upon them, and may be used as
        needed. Cancel may only be invoked while a cancelable method is
        running."""

        # Constants used to reference specific values that info can return.
        INFO_FOUND = 0
        INFO_MISSING = 1
        INFO_MULTI_MATCH = 2
        INFO_ILLEGALS = 3

        # Private constants used for tracking which type of plan was made.
        __INSTALL = 1
        __UNINSTALL = 2
        __IMAGE_UPDATE = 3

        def __init__(self, img_path, version_id, progresstracker,
            cancel_state_callable, pkg_client_name):
                """Constructs an ImageInterface. img_path should point to an
                existing image. version_id indicates the version of the api
                the client is expecting to use. progresstracker is the
                progresstracker the client wants the api to use for UI
                callbacks. cancel_state_callable is a function which the client
                wishes to have called each time whether the operation can be
                canceled changes. It can raise VersionException and
                ImageNotFoundException."""

                compatible_versions = set([CURRENT_API_VERSION])

                if version_id not in compatible_versions:
                        raise api_errors.VersionException(CURRENT_API_VERSION,
                            version_id)

                # The image's History object will use client_name from
                # global_settings, but if the program forgot to set it,
                # we'll go ahead and do so here.
                if global_settings.client_name is None:
                        global_settings.client_name = pkg_client_name

                if isinstance(img_path, basestring):
                        # Store this for reset().
                        self.__img_path = img_path
                        self.__img = image.Image(img_path,
                            progtrack=progresstracker)
                elif isinstance(img_path, image.Image):
                        # This is a temporary, special case for client.py
                        # until the image api is complete.
                        self.__img = img_path
                        self.__img_path = img_path.get_root()
                else:
                        # API consumer passed an unknown type for img_path.
                        raise TypeError(_("Unknown img_path type."))

                self.__progresstracker = progresstracker
                self.__cancel_state_callable = cancel_state_callable
                self.__plan_type = None
                self.__plan_desc = None
                self.__prepared = False
                self.__executed = False
                self.__be_name = None
                self.__can_be_canceled = False
                self.__canceling = False
                self.__activity_lock = pkg.nrlock.NRLock()

        @property
        def img(self):
                """Private; public access to this property will be removed at
                a later date.  Do not use."""
                return self.__img

        @property
        def root(self):
                """The absolute pathname of the filesystem root of the image.
                This property is read-only."""
                if not self.__img:
                        return None
                return self.__img.root

        @staticmethod
        def check_be_name(be_name):
                bootenv.BootEnv.check_be_name(be_name)
                return True


        def __cert_verify(self, log_op_end=None):
                """Verify validity of certificates.  Any
                api_errors.ExpiringCertificate exceptions are caught
                here, a message is displayed, and execution continues.
                All other exceptions will be passed to the calling
                context.  The caller can also set log_op_end to a list
                of exceptions that should result in a call to
                self.log_operation_end() before the exception is passed
                on."""

                if log_op_end == None:
                        log_op_end = []

                # we always explicitly handle api_errors.ExpiringCertificate
                assert api_errors.ExpiringCertificate not in log_op_end

                try:
                        self.__img.check_cert_validity()
                except api_errors.ExpiringCertificate, e:
                        logger.error(e)
                except:
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        if exc_type in log_op_end:
                                self.log_operation_end(error=exc_value)
                        raise

        def __refresh_publishers(self):
                """Refresh publisher metadata."""

                #
                # Verify validity of certificates before possibly
                # attempting network operations.
                #
                self.__cert_verify()

                try:
                        self.__img.refresh_publishers(
                            progtrack=self.__progresstracker)
                except KeyboardInterrupt:
                        raise
                except api_errors.InvalidDepotResponseException:
                        raise
                except:
                        # Since this is not a refresh
                        # that was explicitly requested,
                        # it doesn't matter if it fails.
                        pass

        def __plan_common_start(self, operation):
                """Start planning an operation.  Aquire locks and log
                the start of the operation."""

                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        if self.__plan_type is not None:
                                raise api_errors.PlanExistsException(
                                    self.__plan_type)
                except:
                        self.__activity_lock.release()
                        raise

                assert self.__activity_lock._is_owned()
                self.log_operation_start(operation)

        def __plan_common_finish(self):
                """Finish planning an operation."""

                assert self.__activity_lock._is_owned()
                self.__img.cleanup_downloads()
                self.__activity_lock.release()

        def __plan_common_exception(self, log_op_end=None):
                """Deal with exceptions that can occur while planning an
                operation.  Any exceptions generated here are passed
                onto the calling context.  By default all exceptions
                will result in a call to self.log_operation_end() before
                they are passed onto the calling context.  Optionally,
                the caller can specify the exceptions that should result
                in a call to self.log_operation_end() by setting
                log_op_end."""

                if log_op_end == None:
                        log_op_end = []

                # we always explicity handle api_errors.PlanCreationException
                assert api_errors.PlanCreationException not in log_op_end

                exc_type, exc_value, exc_traceback = sys.exc_info()

                if exc_type == api_errors.PlanCreationException:
                        self.__set_history_PlanCreationException(exc_value)
                elif not log_op_end or exc_type in log_op_end:
                        self.log_operation_end(error=exc_value)
                self.__reset_unlock()
                self.__activity_lock.release()
                raise

        def plan_install(self, pkg_list, refresh_catalogs=True,
            noexecute=False, verbose=False, update_index=True):
                """Contructs a plan to install the packages provided in
                pkg_list.  pkg_list is a list of packages to install.  
                refresh_catalogs controls whether the catalogs will
                automatically be refreshed. noexecute determines whether the
                history will be recorded after planning is finished.  verbose
                controls whether verbose debugging output will be printed to the
                terminal.  Its existence is temporary.  It returns a boolean
                which tells the client whether there is anything to do.  It can
                raise PlanCreationException, PermissionsException and
                InventoryException. The noexecute argument is included for
                compatibility with operational history.  The hope is it can be
                removed in the future."""

                self.__plan_common_start("install")
                try:
                        if refresh_catalogs:
                                self.__refresh_publishers()

                        self.__img.make_install_plan(pkg_list,
                            self.__progresstracker,
                            self.__check_cancelation, noexecute,
                            verbose=verbose)

                        assert self.__img.imageplan

                        if self.__canceling:
                                raise api_errors.CanceledException()
                        self.__set_can_be_canceled(False)

                        if not noexecute:
                                self.__plan_type = self.__INSTALL

                        self.__plan_desc = PlanDescription(self.__img.imageplan)
                        if self.__img.imageplan.nothingtodo() or noexecute:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)

                        self.__img.imageplan.update_index = update_index
                except:
                        self.__plan_common_exception(log_op_end=[
                            api_errors.CanceledException, fmri.IllegalFmri,
                            Exception])
                        # NOTREACHED

                self.__plan_common_finish()
                res = not self.__img.imageplan.nothingtodo()
                return res

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

                self.__plan_common_start("uninstall")

                try:
                        self.__img.make_uninstall_plan(pkg_list,
                            recursive_removal, self.__progresstracker,
                            self.__check_cancelation, noexecute,
                            verbose=verbose)

                        assert self.__img.imageplan

                        if self.__canceling:
                                raise api_errors.CanceledException()
                        self.__set_can_be_canceled(False)

                        if not noexecute:
                                self.__plan_type = self.__UNINSTALL

                        self.__plan_desc = PlanDescription(self.__img.imageplan)
                        if noexecute:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                        self.__img.imageplan.update_index = update_index
                except:
                        self.__plan_common_exception()
                        # NOTREACHED

                self.__plan_common_finish()
                res = not self.__img.imageplan.nothingtodo()
                return res

        def plan_update_all(self, actual_cmd, refresh_catalogs=True,
            noexecute=False, force=False, verbose=False, update_index=True,
            be_name=None):
                """Creates a plan to update all packages on the system to the
                latest known versions.  actual_cmd is the command used to start
                the client.  It is used to determine the image to check whether
                SUNWipkg is up to date.  refresh_catalogs controls whether the
                catalogs will automatically be refreshed.  noexecute determines
                whether the history will be recorded after planning is finished.
                force controls whether update should proceed even if ipkg is not
                up to date.  verbose controls whether verbose debugging output
                will be printed to the terminal.  Its existence is temporary. It
                returns a tuple of two things.  The first is a boolean which
                tells the client whether there is anything to do.  The second
                tells whether the image is an opensolaris image.  It can raise
                CatalogRefreshException, IpkgOutOfDateException,
                PlanCreationException and PermissionsException."""

                self.__plan_common_start("image-update")
                try:
                        self.check_be_name(be_name)
                        self.__be_name = be_name

                        if refresh_catalogs:
                                self.__refresh_publishers()

                        # If we can find SUNWipkg and SUNWcs in the
                        # target image, then we assume this is a valid
                        # opensolaris image, and activate some
                        # special case behaviors.
                        opensolaris_image = True
                        fmris, notfound, illegals = \
                            self.__img.installed_fmris_from_args(
                                ["SUNWipkg", "SUNWcs"])
                        assert(len(illegals) == 0)
                        if notfound:
                                opensolaris_image = False

                        if opensolaris_image and not force:
                                try:
                                        if not self.__img.ipkg_is_up_to_date(
                                            actual_cmd,
                                            self.__check_cancelation,
                                            noexecute,
                                            refresh_allowed=refresh_catalogs,
                                            progtrack=self.__progresstracker):
                                                raise api_errors.IpkgOutOfDateException()
                                except api_errors.ImageNotFoundException:
                                        # Can't do anything in this
                                        # case; so proceed.
                                        pass

                        self.__img.make_update_plan(self.__progresstracker,
                            self.__check_cancelation, noexecute,
                            verbose=verbose)
                            
                        assert self.__img.imageplan

                        if self.__canceling:
                                raise api_errors.CanceledException()
                        self.__set_can_be_canceled(False)

                        if not noexecute:
                                self.__plan_type = self.__IMAGE_UPDATE

                        self.__plan_desc = PlanDescription(self.__img.imageplan)

                        if self.__img.imageplan.nothingtodo() or noexecute:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                        self.__img.imageplan.update_index = update_index

                except:
                        self.__plan_common_exception(
                            log_op_end=[api_errors.IpkgOutOfDateException])
                        # NOTREACHED

                self.__plan_common_finish()
                res = not self.__img.imageplan.nothingtodo()
                return res, opensolaris_image

        def plan_change_varcets(self, variants=None, facets=None,
            noexecute=False, verbose=False, be_name=None):
                """Creates a plan to change the specified variants/facets on an image.
                verbose controls
                whether verbose debugging output will be printed to the
                terminal.  This function has two return values.  The first is
                a boolean which tells the client whether there is anything to
                do.  The third is either None, or an exception which indicates
                partial success.  This is currently used to indicate a failure
                in refreshing catalogs. It can raise CatalogRefreshException,
                IpkgOutOfDateException, NetworkUnavailableException,
                PlanCreationException and PermissionsException."""

                self.__plan_common_start("change-variant")
                if not variants and not facets:
                        raise ValueError, "Nothing to do"
                try:
                        self.check_be_name(be_name)
                        self.be_name = be_name

                        self.__refresh_publishers()

                        self.__img.image_change_varcets(variants, 
                            facets,
                            self.__progresstracker,
                            self.__check_cancelation,
                            noexecute, verbose=verbose)

                        assert self.__img.imageplan

                        if self.__canceling:
                                raise api_errors.CanceledException()
                        self.__set_can_be_canceled(False)

                        if not noexecute:
                                self.__plan_type = self.__IMAGE_UPDATE

                        self.plan_desc = PlanDescription(self.__img.imageplan)

                        if self.__img.imageplan.nothingtodo() or noexecute:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)

                        #
                        # We always rebuild the search index after a
                        # variant change
                        #
                        self.__img.imageplan.update_index = True

                except:
                        self.__plan_common_exception()
                        # NOTREACHED

                self.__plan_common_finish()
                res = not self.__img.imageplan.nothingtodo()
                return res

        def describe(self):
                """Returns None if no plan is ready yet, otherwise returns
                a PlanDescription"""
                return self.__plan_desc

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
                                if not self.__img.imageplan:
                                        raise api_errors.PlanMissingException()

                                if self.__prepared:
                                        raise api_errors.AlreadyPreparedException()
                                assert self.__plan_type == self.__INSTALL or \
                                    self.__plan_type == self.__UNINSTALL or \
                                    self.__plan_type == self.__IMAGE_UPDATE
                                try:
                                        self.__img.imageplan.preexecute()
                                except search_errors.ProblematicPermissionsIndexException, e:
                                        raise api_errors.ProblematicPermissionsIndexException(e)
                                except:
                                        raise

                                if self.__canceling:
                                        self.__img.transport.reset()
                                        raise api_errors.CanceledException()
                                self.__prepared = True
                        except Exception, e:
                                if self.__img.history.operation_name:
                                        # If an operation is in progress, log
                                        # the error and mark its end.
                                        self.log_operation_end(error=e)
                                raise
                        except:
                                # Handle exceptions that are not subclasses of
                                # Exception.
                                if self.__img.history.operation_name:
                                        # If an operation is in progress, log
                                        # the error and mark its end.
                                        exc_type, exc_value, exc_traceback = \
                                            sys.exc_info()
                                        self.log_operation_end(error=exc_type)
                                raise
                finally:
                        self.__img.cleanup_downloads()
                        self.__set_can_be_canceled(False)
                        self.__activity_lock.release()

        def execute_plan(self):
                """Executes the plan. This is uncancelable one it begins. It
                can raise CorruptedIndexException,
                ProblematicPermissionsIndexException, ImageplanStateException,
                ImageUpdateOnLiveImageException, and PlanMissingException.
                Should only be called after the prepare method has been
                called."""

                self.__activity_lock.acquire()
                self.__set_can_be_canceled(False)
                try:
                        if not self.__img.imageplan:
                                raise api_errors.PlanMissingException()

                        if not self.__prepared:
                                raise api_errors.PrematureExecutionException()

                        if self.__executed:
                                raise api_errors.AlreadyExecutedException()

                        assert self.__plan_type == self.__INSTALL or \
                            self.__plan_type == self.__UNINSTALL or \
                            self.__plan_type == self.__IMAGE_UPDATE

                        try:
                                be = bootenv.BootEnv(self.__img.get_root())
                        except RuntimeError:
                                be = bootenv.BootEnvNull(self.__img.get_root())
                        self.__img.bootenv = be

                        if self.__plan_type is self.__IMAGE_UPDATE:
                                try:
                                        be.init_image_recovery(self.__img,
                                            self.__be_name)
                                except Exception, e:
                                        self.log_operation_end(error=e)
                                        raise
                                except:
                                        # Handle exceptions that are not
                                        # subclasses of Exception.
                                        exc_type, exc_value, exc_traceback = \
                                            sys.exc_info()
                                        self.log_operation_end(error=exc_type)
                                        raise

                                if self.__img.is_liveroot():
                                        e = api_errors.ImageUpdateOnLiveImageException()
                                        self.log_operation_end(error=e)
                                        raise e
                        else:
                                if self.__img.imageplan.reboot_needed() and \
                                    self.__img.is_liveroot():
                                        e = api_errors.RebootNeededOnLiveImageException()
                                        self.log_operation_end(error=e)
                                        raise e

                        try:
                                self.__img.imageplan.execute()
                        except RuntimeError, e:
                                if self.__plan_type is self.__IMAGE_UPDATE:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                # Must be done after bootenv restore.
                                self.log_operation_end(error=e)
                                raise
                        except search_errors.ProblematicPermissionsIndexException, e:
                                error = api_errors.ProblematicPermissionsIndexException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except (search_errors.InconsistentIndexException,
                                search_errors.PartialIndexingException), e:
                                error = api_errors.CorruptedIndexException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except search_errors.MainDictParsingException, e:
                                error = api_errors.MainDictParsingException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except actuator.NonzeroExitException, e:
                                # Won't happen during image-update
                                be.restore_install_uninstall()
                                error = api_errors.ActuatorException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except api_errors.WrapIndexingException, e:
                                self.__finished_execution(be)
                                raise
                        except Exception, e:
                                if self.__plan_type is self.__IMAGE_UPDATE:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                # Must be done after bootenv restore.
                                self.log_operation_end(error=e)
                                raise
                        except:
                                # Handle exceptions that are not subclasses of
                                # Exception.
                                exc_type, exc_value, exc_traceback = \
                                    sys.exc_info()

                                if self.__plan_type is self.__IMAGE_UPDATE:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                # Must be done after bootenv restore.
                                self.log_operation_end(error=exc_type)
                                raise

                        self.__finished_execution(be)
                finally:
                        self.__img.cleanup_downloads()
                        self.__activity_lock.release()

        def __finished_execution(self, be):
                if self.__img.imageplan.state != EXECUTED_OK:
                        if self.__plan_type is self.__IMAGE_UPDATE:
                                be.restore_image()
                        else:
                                be.restore_install_uninstall()

                        error = api_errors.ImageplanStateException(
                            self.__img.imageplan.state)
                        # Must be done after bootenv restore.
                        self.log_operation_end(error=error)
                        raise error
                if self.__plan_type is self.__IMAGE_UPDATE:
                        be.activate_image()
                else:
                        be.activate_install_uninstall()
                self.__img.cleanup_cached_content()
                # If the end of the operation wasn't already logged
                # by one of the previous operations, then log it as
                # ending now.
                if self.__img.history.operation_name:
                        self.log_operation_end()
                self.__executed = True
                try:
                        if int(os.environ.get("PKG_DUMP_STATS", 0)) > 0:
                                self.__img.transport.stats.dump()
                except ValueError:
                        # Don't generate stats if an invalid value
                        # is supplied.
                        pass

        def refresh(self, full_refresh=False, pubs=None, immediate=False):
                """Refreshes the metadata (e.g. catalog) for one or more
                publishers.

                'full_refresh' is an optional boolean value indicating whether
                a full retrieval of publisher metadata (e.g. catalogs) or only
                an update to the existing metadata should be performed.  When
                True, 'immediate' is also set to True.
 
                'pubs' is a list of publisher prefixes or publisher objects
                to refresh.  Passing an empty list or using the default value
                implies all publishers.

                'immediate' is an optional boolean value indicating whether
                a refresh should occur now.  If False, a publisher's selected
                repository will only be checked for updates if the update
                interval period recorded in the image configuration has been
                exceeded.

                Currently returns an image object, allowing existing code to
                work while the rest of the API is put into place."""

                self.__activity_lock.acquire()
                self.__set_can_be_canceled(False)
                try:
                        self.__img.refresh_publishers(full_refresh=full_refresh,
                            immediate=immediate, pubs=pubs,
                            progtrack=self.__progresstracker)
                        return self.__img
                finally:
                        self.__img.cleanup_downloads()
                        self.__activity_lock.release()

        def __licenses(self, mfst, local):
                """Private function. Returns the license info from the
                manifest mfst. Local controls whether the information is
                retrieved locally."""
                license_lst = []
                for lic in mfst.gen_actions_by_type("license"):
                        if not local:
                                s = StringIO.StringIO()
                                hash_val = misc.gunzip_from_stream(
                                    lic.get_remote_opener(self.__img,
                                    mfst.fmri)(), s)
                                text = s.getvalue()
                                s.close()
                        else:
                                text = lic.get_local_opener(self.__img,
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

                # Currently, this is mostly a wapper for activity locking.
                self.__activity_lock.acquire()
                try:
                        i = self._info_op(fmri_strings, local, info_needed)
                finally:
                        self.__img.cleanup_downloads()
                        self.__activity_lock.release()

                return i

        def _info_op(self, fmri_strings, local, info_needed):
                """Performs the actual info operation.  The external
                interface to the API's consumers is defined in info()."""

                bad_opts = info_needed - PackageInfo.ALL_OPTIONS
                if bad_opts:
                        raise api_errors.UnrecognizedOptionsToInfo(bad_opts)

                self.log_operation_start("info")

                fmris = []
                notfound = []
                multiple_matches = []
                illegals = []

                ppub = self.__img.get_preferred_publisher()
                if local:
                        fmris, notfound, illegals = \
                            self.__img.installed_fmris_from_args(fmri_strings)
                        if not fmris and not notfound and not illegals:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                raise api_errors.NoPackagesInstalledException()
                else:
                        # Verify validity of certificates before attempting
                        # network operations.
                        self.__cert_verify(
                            log_op_end=[api_errors.CertificateError])

                        # XXX This loop really needs not to be copied from
                        # Image.make_install_plan()!
                        for p in fmri_strings:
                                try:
                                        matches = list(self.__img.inventory([p],
                                            all_known=True, ordered=False))
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
                                        if m.get_publisher() == ppub:
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

                if local:
                        img_cat = self.__img.get_catalog(
                            self.__img.IMG_CATALOG_INSTALLED)
                else:
                        img_cat = self.__img.get_catalog(
                            self.__img.IMG_CATALOG_KNOWN)
                excludes = self.__img.list_excludes()

                # Set of summary-related options that are in catalog data.
                summ_opts = frozenset([PackageInfo.SUMMARY,
                    PackageInfo.CATEGORIES, PackageInfo.DESCRIPTION])

                # Set of all options that are in catalog data.
                cat_opts = summ_opts | frozenset([PackageInfo.DEPENDENCIES])

                # Set of options that require manifest retrieval.
                act_opts = PackageInfo.ACTION_OPTIONS - \
                    frozenset([PackageInfo.DEPENDENCIES])

                def get_pkg_cat_data(f):
                        # XXX this doesn't handle locale.
                        get_summ = summ = desc = cat_info = deps = None
                        cat_data = []
                        if summ_opts & info_needed:
                                cat_data.append(img_cat.SUMMARY)
                                get_summ = PackageInfo.SUMMARY in info_needed
                        if PackageInfo.CATEGORIES in info_needed:
                                cat_info = []
                        if PackageInfo.DEPENDENCIES in info_needed:
                                cat_data.append(img_cat.DEPENDENCY)
                                deps = []

                        for a in img_cat.get_entry_actions(f, cat_data,
                            excludes=excludes):
                                if a.name == "depend":
                                        deps.append(a.attrs.get(a.key_attr))
                                elif a.attrs["name"] == "pkg.summary":
                                        if get_summ:
                                                summ = a.attrs["value"]
                                elif a.attrs["name"] in ("description",
                                    "pkg.description"):
                                        desc = a.attrs["value"]
                                elif cat_info != None and a.has_category_info():
                                        cat_info.extend(
                                            PackageCategory(scheme, cat)
                                            for scheme, cat
                                            in a.parse_category_info())

                        if get_summ and summ == None:
                                summ = desc
                        if not PackageInfo.DESCRIPTION in info_needed:
                                desc = None
                        return summ, desc, cat_info, deps

                pis = []
                for f in fmris:
                        pub = name = version = release = states = None
                        build_release = branch = packaging_date = None
                        if PackageInfo.IDENTITY in info_needed:
                                pub, name, version = f.tuple()
                                pub = fmri.strip_pub_pfx(pub)
                                release = version.release
                                build_release = version.build_release
                                branch = version.branch
                                packaging_date = \
                                    version.get_timestamp().strftime("%c")
                        pref_pub = None
                        if PackageInfo.PREF_PUBLISHER in info_needed:
                                pref_pub = f.get_publisher() == ppub
                        state = None
                        if PackageInfo.STATE in info_needed:
                                states = self.__img.get_pkg_state(f)
                        links = hardlinks = files = dirs = dependencies = None
                        summary = size = licenses = cat_info = description = \
                            None

                        if frozenset([PackageInfo.SUMMARY,
                            PackageInfo.CATEGORIES,
                            PackageInfo.DESCRIPTION,
                            PackageInfo.DEPENDENCIES]) & info_needed:
                                summary, description, cat_info, dependencies = \
                                    get_pkg_cat_data(f)

                        if (frozenset([PackageInfo.SIZE,
                            PackageInfo.LICENSES]) | act_opts) & info_needed:
                                mfst = self.__img.get_manifest(f)
                                if PackageInfo.LICENSES in info_needed:
                                        licenses = self.__licenses(mfst, local)

                                if PackageInfo.SIZE in info_needed:
                                        size = mfst.get_size(excludes=excludes)

                                if act_opts & info_needed:
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

                        pis.append(PackageInfo(pkg_stem=name, summary=summary,
                            category_info_list=cat_info, states=states,
                            publisher=pub, preferred_publisher=pref_pub,
                            version=release, build_release=build_release,
                            branch=branch, packaging_date=packaging_date,
                            size=size, pfmri=str(f), licenses=licenses,
                            links=links, hardlinks=hardlinks, files=files,
                            dirs=dirs, dependencies=dependencies,
                            description=description))
                if pis:
                        self.log_operation_end()
                elif illegals or multiple_matches:
                        self.log_operation_end(
                            result=history.RESULT_FAILED_BAD_REQUEST)
                else:
                        self.log_operation_end(
                            result=history.RESULT_NOTHING_TO_DO)
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
                        if self.__cancel_state_callable:
                                self.__cancel_state_callable(
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

                assert self.__activity_lock._is_owned()

                # This needs to be done first so that find_root can use it.
                self.__progresstracker.reset()

                self.__img.cleanup_downloads()
                # Recreate the image object using the path the api
                # object was created with instead of the current path.
                self.__img = image.Image(self.__img_path,
                    progtrack=self.__progresstracker)

                self.__plan_desc = None
                self.__plan_type = None
                self.__prepared = False
                self.__executed = False
                self.__be_name = None
                self.__set_can_be_canceled(False)
                self.__canceling = False

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
                if e.unmatched_fmris or e.multiple_matches or \
                    e.missing_matches or e.illegal:
                        self.log_operation_end(error=e,
                            result=history.RESULT_FAILED_BAD_REQUEST)
                else:
                        self.log_operation_end(error=e)

        def local_search(self, query_lst):
                """local_search takes a list of Query objects and performs
                each query against the installed packages of the image."""

                l = query_p.QueryLexer()
                l.build()
                qp = query_p.QueryParser(l)
                ssu = None
                for i, q in enumerate(query_lst):
                        try:
                                query = qp.parse(q.encoded_text())
                                query_rr = qp.parse(q.encoded_text())
                                if query_rr.remove_root(self.__img.root):
                                        query.add_or(query_rr)
                        except query_p.BooleanQueryException, e:
                                raise api_errors.BooleanQueryException(e)
                        except query_p.ParseError, e:
                                raise api_errors.ParseError(e)
                        self.__img.update_index_dir()
                        assert self.__img.index_dir
                        try:
                                query.set_info(num_to_return=q.num_to_return,
                                    start_point=q.start_point,
                                    index_dir=self.__img.index_dir,
                                    get_manifest_path=\
                                        self.__img.get_manifest_path,
                                    gen_installed_pkg_names=\
                                        self.__img.gen_installed_pkg_names,
                                    case_sensitive=q.case_sensitive)
                                res = query.search(
                                    self.__img.gen_installed_pkgs,
                                    self.__img.get_manifest_path,
                                    self.__img.list_excludes())
                        except search_errors.InconsistentIndexException, e:
                                raise api_errors.InconsistentIndexException(e)
                        # i is being inserted to track which query the results
                        # are for.  None is being inserted since there is no
                        # publisher being searched against.
                        try:
                                for r in res:
                                        yield i, None, r
                        except api_errors.SlowSearchUsed, e:
                                ssu = e
                if ssu:
                        raise ssu

        @staticmethod
        def __parse_v_0(line, pub, v):
                """This function parses the string returned by a version 0
                search server and puts it into the expected format of
                (query_number, publisher, (version, return_type, (results))).

                "query_number" in the return value is fixed at 0 since search
                v0 servers cannot accept multiple queries in a single HTTP
                request."""

                line = line.strip()
                fields = line.split(None, 3)
                return (0, pub, (v, Query.RETURN_ACTIONS, (fields[:4])))

        @staticmethod
        def __parse_v_1(line, pub, v):
                """This function parses the string returned by a version 1
                search server and puts it into the expected format of
                (query_number, publisher, (version, return_type, (results)))
                If it receives a line it can't parse, it raises a
                ServerReturnError."""

                fields = line.split(None, 2)
                if len(fields) != 3:
                        raise api_errors.ServerReturnError(line)
                try:
                        return_type = int(fields[1])
                        query_num = int(fields[0])
                except ValueError:
                        raise api_errors.ServerReturnError(line)
                if return_type == Query.RETURN_ACTIONS:
                        subfields = fields[2].split(None, 2)
                        return (query_num, pub, (v, return_type,
                            (subfields[0], urllib.unquote(subfields[1]),
                            subfields[2])))
                elif return_type == Query.RETURN_PACKAGES:
                        return (query_num, pub, (v, return_type, fields[2]))
                else:
                        raise api_errors.ServerReturnError(line)

        def remote_search(self, query_str_and_args_lst, servers=None):
                """This function takes a list of Query objects, and optionally
                a list of servers to search against.  It performs each query
                against each server and yields the results in turn.  If no
                servers are provided, the search is conducted against all
                active servers known by the image.

                The servers argument is a list of servers in two possible
                forms: the old deprecated form of a publisher, in a
                dictionary, or a Publisher object. """

                failed = []
                invalid = []
                unsupported = []

                if not servers:
                        servers = self.__img.gen_publishers()

                new_qs = []
                l = query_p.QueryLexer()
                l.build()
                qp = query_p.QueryParser(l)
                for q in query_str_and_args_lst:
                        try:
                                query = qp.parse(q.encoded_text())
                                query_rr = qp.parse(q.encoded_text())
                                if query_rr.remove_root(self.__img.root):
                                        query.add_or(query_rr)
                                        new_qs.append(query_p.Query(str(query),
                                            q.case_sensitive, q.return_type,
                                            q.num_to_return, q.start_point))
                                else:
                                        new_qs.append(q)
                        except query_p.BooleanQueryException, e:
                                raise api_errors.BooleanQueryException(e)
                        except query_p.ParseError, e:
                                raise api_errors.ParseError(e)
                query_str_and_args_lst = new_qs

                for pub in servers:
                        descriptive_name = None

                        if isinstance(pub, dict):
                                origin = pub["origin"]
                                try:
                                        pub = self.__img.get_publisher(
                                            origin=origin)
                                except api_errors.UnknownPublisher:
                                        pub = publisher.RepositoryURI(origin)
                                        descriptive_name = origin

                        if not descriptive_name:
                                descriptive_name = pub.prefix

                        try:
                                res = self.__img.transport.do_search(pub,
                                    query_str_and_args_lst)
                        except api_errors.NegativeSearchResult:
                                continue
                        except api_errors.TransportError, e:
                                failed.append((descriptive_name, e))
                                continue
                        except api_errors.UnsupportedSearchError, e:
                                unsupported.append((descriptive_name, e))
                                continue
                        except api_errors.MalformedSearchRequest, e:
                                ex = self._validate_search(
                                    query_str_and_args_lst)
                                if ex:
                                        raise ex
                                failed.append((descriptive_name, e))
                                continue

                        try:
                                if not self.validate_response(res, 1):
                                        invalid.append(descriptive_name)
                                        continue
                                for line in res:
                                        yield self.__parse_v_1(line, pub, 1)
                        except api_errors.TransportError, e:
                                failed.append((descriptive_name, e))
                                continue

                if failed or invalid or unsupported:
                        raise api_errors.ProblematicSearchServers(failed,
                            invalid, unsupported)

        @staticmethod
        def __unconvert_return_type(v):
                return v == query_p.Query.RETURN_ACTIONS

        def _validate_search(self, query_str_lst):
                """Called by remote search if server responds that the
                request was invalid.  In this case, parse the query on
                the client-side and determine what went wrong."""

                for q in query_str_lst:
                        l = query_p.QueryLexer()
                        l.build()
                        qp = query_p.QueryParser(l)
                        try:
                                query = qp.parse(q.encoded_text())
                        except query_p.BooleanQueryException, e:
                                return api_errors.BooleanQueryException(e)
                        except query_p.ParseError, e:
                                return api_errors.ParseError(e)

                return None

        def rebuild_search_index(self):
                """Rebuilds the search indexes.  Removes all
                existing indexes and replaces them from scratch rather than
                performing the incremental update which is usually used.
                This is useful for times when the index for the client has
                been corrupted."""
                self.__img.update_index_dir()
                self.log_operation_start("rebuild-index")
                if not os.path.isdir(self.__img.index_dir):
                        self.__img.mkdirs()
                try:
                        ind = indexer.Indexer(self.__img, self.__img.get_manifest,
                            self.__img.get_manifest_path,
                            self.__progresstracker, self.__img.list_excludes())
                        ind.rebuild_index_from_scratch(
                            self.__img.gen_installed_pkgs())
                except search_errors.ProblematicPermissionsIndexException, e:
                        error = api_errors.ProblematicPermissionsIndexException(e)
                        self.log_operation_end(error=error)
                        raise error
                except search_errors.MainDictParsingException, e:
                        error = api_errors.MainDictParsingException(e)
                        self.log_operation_end(error=error)
                        self.__img.cleanup_downloads()
                        raise error
                else:
                        self.log_operation_end()

        @staticmethod
        def validate_response(res, v):
                """This function is used to determine whether the first
                line returned from a server is expected.  This ensures that
                search is really communicating with a search-enabled server."""

                try:
                        s = res.next()
                        return s == Query.VALIDATION_STRING[v]
                except StopIteration:
                        return False

        def add_publisher(self, pub, refresh_allowed=True):
                """Add the provided publisher object to the image
                configuration."""
                try:
                        self.__img.add_publisher(pub,
                            refresh_allowed=refresh_allowed,
                            progtrack=self.__progresstracker)
                finally:
                        self.__img.cleanup_downloads()

        def get_pub_search_order(self):
                """Return current search order of publishers; includes
                disabled publishers"""
                return self.__img.cfg_cache.publisher_search_order

        def set_pub_search_after(self, being_moved_prefix, staying_put_prefix):
                """Change the publisher search order so that being_moved is
                searched after staying_put"""
                self.__img.pub_search_after(being_moved_prefix, staying_put_prefix)

        def set_pub_search_before(self, being_moved_prefix, staying_put_prefix):
                """Change the publisher search order so that being_moved is
                searched before staying_put"""
                self.__img.pub_search_before(being_moved_prefix, staying_put_prefix)

        def get_preferred_publisher(self):
                """Returns the preferred publisher object for the image."""
                return self.get_publisher(
                    prefix=self.__img.get_preferred_publisher())

        def get_publisher(self, prefix=None, alias=None, duplicate=False):
                """Retrieves a publisher object matching the provided prefix
                (name) or alias.

                'duplicate' is an optional boolean value indicating whether
                a copy of the publisher object should be returned instead
                of the original.
                """
                pub = self.__img.get_publisher(prefix=prefix, alias=alias)
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
                            for p in self.__img.get_publishers().values()
                        ]
                else:
                        pubs = self.__img.get_publishers().values()
                return misc.get_sorted_publishers(pubs,
                    preferred=self.__img.get_preferred_publisher())

        def get_publisher_last_update_time(self, prefix=None, alias=None):
                """Returns a datetime object representing the last time the
                catalog for a publisher was modified or None."""

                if alias:
                        pub = self.get_publisher(alias=alias)
                else:
                        pub = self.get_publisher(prefix=prefix)

                if pub.disabled:
                        return None

                dt = None
                self.__activity_lock.acquire()
                try:
                        self.__set_can_be_canceled(True)
                        try:
                                dt = pub.catalog.last_modified
                        except:
                                self.__reset_unlock()
                                raise
                finally:
                        self.__activity_lock.release()
                return dt

        def has_publisher(self, prefix=None, alias=None):
                """Returns a boolean value indicating whether a publisher using
                the given prefix or alias exists."""
                return self.__img.has_publisher(prefix=prefix, alias=alias)

        def remove_publisher(self, prefix=None, alias=None):
                """Removes a publisher object matching the provided prefix
                (name) or alias."""
                self.__img.remove_publisher(prefix=prefix, alias=alias,
                    progtrack=self.__progresstracker)

        def set_preferred_publisher(self, prefix=None, alias=None):
                """Sets the preferred publisher for the image."""
                self.__img.set_preferred_publisher(prefix=prefix, alias=alias)

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
                    pub.prefix == self.__img.get_preferred_publisher():
                        raise api_errors.SetPreferredPublisherDisabled(
                            pub.prefix)

                def need_refresh(oldo, newo):
                        if newo.disabled:
                                # The publisher is disabled, so no refresh
                                # should be performed.
                                return False

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
                                # one has been added or removed.
                                return True

                        return False

                refresh_catalog = False
                updated = False
                disable = False
                orig_pub = None
                publishers = self.__img.get_publishers()
                for key, old in publishers.iteritems():
                        if pub._source_object_id == id(old):
                                if need_refresh(old, pub):
                                        refresh_catalog = True
                                if not old.disabled and pub.disabled:
                                        disable = True

                                # Store the new publisher's id and the old
                                # publisher object so it can be restored if the
                                # update operation fails.
                                orig_pub = (id(pub), publishers[key])

                                # Now remove the old publisher object using the
                                # iterator key since the prefix might be
                                # different for the new publisher object.
                                updated = True

                                # only if prefix is different - this
                                # preserves search order
                                if key != pub.prefix:
                                        del publishers[key]

                                # Prepare the new publisher object.
                                pub.meta_root = \
                                    self.__img._get_publisher_meta_root(
                                    pub.prefix)
                                pub.transport = self.__img.transport

                                # Finally, add the new publisher object.
                                publishers[pub.prefix] = pub
                                break

                if not updated:
                        # If a matching publisher couldn't be found and
                        # replaced, something is wrong (client api usage
                        # error).
                        e = api_errors.UnknownPublisher(pub)
                        self.log_operation_end(e)
                        raise e

                def cleanup():
                        new_id, old_pub = orig_pub
                        for new_pfx, new_pub in publishers.iteritems():
                                if id(new_pub) == new_id:
                                        del publishers[new_pfx]
                                        publishers[old_pub.prefix] = old_pub
                                        break

                repo = pub.selected_repository
                if not repo.origins:
                        raise api_errors.PublisherOriginRequired(pub.prefix)

                try:
                        if disable:
                                # Remove the publisher's metadata (such as
                                # catalogs, etc.).  This only needs to be done
                                # in the event that a publisher is disabled; in
                                # any other case (the origin changing, etc.),
                                # refresh() will do the right thing.
                                self.__img.remove_publisher_metadata(pub)
                        elif not pub.disabled and not refresh_catalog:
                                refresh_catalog = pub.needs_refresh

                        if refresh_catalog:
                                if refresh_allowed:
                                        # One of the publisher's repository
                                        # origins may have changed, so the
                                        # publisher needs to be revalidated.
                                        self.__img.transport.valid_publisher_test(
                                            pub)
                                        self.refresh(pubs=[pub], immediate=True)
                                else:
                                        # Something has changed (such as a
                                        # repository origin) for the publisher,
                                        # so a refresh should occur, but isn't
                                        # currently allowed.  As such, clear the
                                        # last_refreshed time so that the next
                                        # time the client checks to see if a
                                        # refresh is needed and is allowed, one
                                        # will be performed.
                                        pub.last_refreshed = None
                except Exception, e:
                        # If any of the above fails, the original publisher
                        # information needs to be restored so that state is
                        # consistent.
                        cleanup()
                        self.__img.cleanup_downloads()
                        self.log_operation_end(error=e)
                        raise
                except:
                        # If any of the above fails, the original publisher
                        # information needs to be restored so that state is
                        # consistent.
                        cleanup()
                        self.__img.cleanup_downloads()
                        exc_type, exc_value, exc_traceback = \
                            sys.exc_info()
                        self.log_operation_end(error=exc_type)
                        raise

                # Successful; so save configuration.
                self.__img.save_config()
                self.__img.cleanup_downloads()
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
                self.__img.history.log_operation_end(error=error, result=result)

        def log_operation_error(self, error):
                """Adds an error to the list of errors to be recorded in image
                history for the current opreation."""
                self.__img.history.log_operation_error(error)

        def log_operation_start(self, name):
                """Marks the start of an operation to be recorded in image
                history."""
                self.__img.history.log_operation_start(name)

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

                return p5i.parse(fileobj=fileobj, location=location)

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

                if not pubs:
                        plist = [
                            p for p in self.get_publishers()
                            if not p.disabled
                        ]
                else:
                        plist = []
                        for p in pubs:
                                if not isinstance(p, publisher.Publisher):
                                        plist.append(self.__img.get_publisher(
                                            prefix=p, alias=p))
                                else:
                                        plist.append(p)

                # Transform PackageInfo object entries into PkgFmri entries
                # before passing them to the p5i module.
                new_pkg_names = {}
                for pub in pkg_names:
                        pkglist = []
                        for p in pkg_names[pub]:
                                if isinstance(p, PackageInfo):
                                        pkglist.append(p.fmri)
                                else:
                                        pkglist.append(p)
                        new_pkg_names[pub] = pkglist
                p5i.write(fileobj, plist, pkg_names=new_pkg_names)


class Query(query_p.Query):
        """This class is the object used to pass queries into the api functions.
        It encapsulates the possible options available for a query as well as
        the text of the query itself."""

        def __init__(self, text, case_sensitive, return_actions=True,
            num_to_return=None, start_point=None):
                if return_actions:
                        return_type = query_p.Query.RETURN_ACTIONS
                else:
                        return_type = query_p.Query.RETURN_PACKAGES
                query_p.Query.__init__(self, text, case_sensitive, return_type,
                    num_to_return, start_point)


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
        OBSOLETE = 3
        RENAMED = 4

        __NUM_PROPS = 13
        IDENTITY, SUMMARY, CATEGORIES, STATE, PREF_PUBLISHER, SIZE, LICENSES, \
            LINKS, HARDLINKS, FILES, DIRS, DEPENDENCIES, DESCRIPTION = \
            range(__NUM_PROPS)
        ALL_OPTIONS = frozenset(range(__NUM_PROPS))
        ACTION_OPTIONS = frozenset([LINKS, HARDLINKS, FILES, DIRS,
            DEPENDENCIES])

        def __init__(self, pfmri, pkg_stem=None, summary=None,
            category_info_list=None, states=None, publisher=None,
            preferred_publisher=None, version=None, build_release=None,
            branch=None, packaging_date=None, size=None, licenses=None,
            links=None, hardlinks=None, files=None, dirs=None,
            dependencies=None, description=None):
                self.pkg_stem = pkg_stem
                self.summary = summary
                if category_info_list is None:
                        category_info_list = []
                self.category_info_list = category_info_list
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
                self.description = description
                self.states = self.__map_states(states)

        def __str__(self):
                return self.fmri

        @classmethod
        def __map_states(cls, states):
                d = {
                    0: cls.NOT_INSTALLED,
                    2: cls.INSTALLED,
                    8: cls.OBSOLETE,
                    9: cls.RENAMED
                }

                if not states:
                        return []

                return [
                    t
                    for t in (
                        d.get(s, -1)
                        for s in states
                    )
                    if t != -1
                ]

        @staticmethod
        def build_from_fmri(f):
                if not f:
                        return f
                pub, name, version = f.tuple()
                pub = fmri.strip_pub_pfx(pub)
                return PackageInfo(pkg_stem=name, publisher=pub,
                    version=version.release,
                    build_release=version.build_release, branch=version.branch,
                    packaging_date=version.get_timestamp().strftime("%c"),
                    pfmri=str(f))
