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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

"""This module provides the supported, documented interface for clients to
interface with the pkg(5) system.

Refer to pkg.api_common for additional core class documentation.

Consumers should catch ApiException when calling any API function, and
may optionally catch any subclass of ApiException for further, specific
error handling.
"""

import collections
import copy
import datetime
import errno
import fnmatch
import operator
import os
import shutil
import sys
import tempfile
import threading
import urllib

import pkg.client.api_errors as apx
import pkg.client.bootenv as bootenv
import pkg.client.history as history
import pkg.client.image as image
import pkg.client.imageplan as ip
import pkg.client.imagetypes as imgtypes
import pkg.client.indexer as indexer
import pkg.client.publisher as publisher
import pkg.client.query_parser as query_p
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.nrlock
import pkg.p5i as p5i
import pkg.p5s as p5s
import pkg.portable as portable
import pkg.search_errors as search_errors
import pkg.version

from pkg.api_common import (PackageInfo, LicenseInfo, PackageCategory,
    _get_pkg_cat_data)
from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.client.pkgdefs import *
from pkg.smf import NonzeroExitException

CURRENT_API_VERSION = 61
CURRENT_P5I_VERSION = 1

# Image type constants.
IMG_TYPE_NONE = imgtypes.IMG_NONE # No image.
IMG_TYPE_ENTIRE = imgtypes.IMG_ENTIRE # Full image ('/').
IMG_TYPE_PARTIAL = imgtypes.IMG_PARTIAL  # Not yet implemented.
IMG_TYPE_USER = imgtypes.IMG_USER # Not '/'; some other location.

logger = global_settings.logger

class _LockedGenerator(object):
        """This is a private class and should not be used by API consumers.

        This decorator class wraps API generator functions, managing the
        activity and cancelation locks.  Due to implementation differences
        in the decorator protocol, the decorator must be used with
        parenthesis in order for this to function correctly.  Always
        decorate functions @_LockedGenerator()."""

        def __init__(self, *d_args, **d_kwargs):
                object.__init__(self)

        def __call__(self, f):
                def wrapper(*fargs, **f_kwargs):
                        instance, fargs = fargs[0], fargs[1:]
                        instance._acquire_activity_lock()
                        instance._enable_cancel()

                        clean_exit = True
                        canceled = False
                        try:
                                for v in f(instance, *fargs, **f_kwargs):
                                        yield v
                        except GeneratorExit:
                                return
                        except apx.CanceledException:
                                canceled = True
                                raise
                        except Exception:
                                clean_exit = False
                                raise
                        finally:
                                if canceled:
                                        instance._cancel_done()
                                elif clean_exit:
                                        try:
                                                instance._disable_cancel()
                                        except apx.CanceledException:
                                                instance._cancel_done()
                                                instance._activity_lock.release()
                                                raise
                                else:
                                        instance._cancel_cleanup_exception()
                                instance._activity_lock.release()

                return wrapper


class _LockedCancelable(object):
        """This is a private class and should not be used by API consumers.

        This decorator class wraps non-generator cancelable API functions,
        managing the activity and cancelation locks.  Due to implementation
        differences in the decorator protocol, the decorator must be used with
        parenthesis in order for this to function correctly.  Always
        decorate functions @_LockedCancelable()."""

        def __init__(self, *d_args, **d_kwargs):
                object.__init__(self)

        def __call__(self, f):
                def wrapper(*fargs, **f_kwargs):
                        instance, fargs = fargs[0], fargs[1:]
                        instance._acquire_activity_lock()
                        instance._enable_cancel()

                        clean_exit = True
                        canceled = False
                        try:
                                return f(instance, *fargs, **f_kwargs)
                        except apx.CanceledException:
                                canceled = True
                                raise
                        except Exception:
                                clean_exit = False
                                raise
                        finally:
                                instance._img.cleanup_downloads()
                                try:
                                        if int(os.environ.get("PKG_DUMP_STATS",
                                            0)) > 0:
                                                instance._img.transport.stats.dump()
                                except ValueError:
                                        # Don't generate stats if an invalid
                                        # value is supplied.
                                        pass

                                if canceled:
                                        instance._cancel_done()
                                elif clean_exit:
                                        try:
                                                instance._disable_cancel()
                                        except apx.CanceledException:
                                                instance._cancel_done()
                                                instance._activity_lock.release()
                                                raise
                                else:
                                        instance._cancel_cleanup_exception()
                                instance._activity_lock.release()

                return wrapper


class ImageInterface(object):
        """This class presents an interface to images that clients may use.
        There is a specific order of methods which must be used to install
        or uninstall packages, or update an image. First, gen_plan_install,
        gen_plan_uninstall, gen_plan_update or gen_plan_change_varcets must be
        called.  After that method completes successfully, describe may be
        called, and prepare must be called. Finally, execute_plan may be
        called to implement the previous created plan. The other methods
        do not have an ordering imposed upon them, and may be used as
        needed. Cancel may only be invoked while a cancelable method is
        running."""

        # Constants used to reference specific values that info can return.
        INFO_FOUND = 0
        INFO_MISSING = 1
        INFO_ILLEGALS = 3

        LIST_ALL = 0
        LIST_INSTALLED = 1
        LIST_INSTALLED_NEWEST = 2
        LIST_NEWEST = 3
        LIST_UPGRADABLE = 4

        MATCH_EXACT = 0
        MATCH_FMRI = 1
        MATCH_GLOB = 2

        # Private constants used for tracking which type of plan was made.
        __INSTALL     = "install"
        __REVERT      = "revert"
        __SYNC        = "sync"
        __UNINSTALL   = "uninstall"
        __UPDATE      = "update"
        __VARCET      = "varcet"
        __plan_values = frozenset([
            __INSTALL,
            __REVERT,
            __SYNC,
            __UNINSTALL,
            __UPDATE,
            __VARCET,
        ])

        __api_op_2_plan = {
            API_OP_ATTACH:         __SYNC,
            API_OP_CHANGE_FACET:   __VARCET,
            API_OP_CHANGE_VARIANT: __VARCET,
            API_OP_DETACH:         __UNINSTALL,
            API_OP_INSTALL:        __INSTALL,
            API_OP_REVERT:         __REVERT,
            API_OP_SYNC:           __SYNC,
            API_OP_UNINSTALL:      __UNINSTALL,
            API_OP_UPDATE:         __UPDATE,
        }

        __stage_2_ip_mode = {
            API_STAGE_DEFAULT:  ip.IP_MODE_DEFAULT,
            API_STAGE_PUBCHECK: ip.IP_MODE_SAVE,
            API_STAGE_PLAN:     ip.IP_MODE_SAVE,
            API_STAGE_PREPARE:  ip.IP_MODE_LOAD,
            API_STAGE_EXECUTE:  ip.IP_MODE_LOAD,
        }


        def __init__(self, img_path, version_id, progresstracker,
            cancel_state_callable, pkg_client_name, exact_match=True,
            cmdpath=None, runid=-1):
                """Constructs an ImageInterface object.

                'img_path' is the absolute path to an existing image or to a
                path from which to start looking for an image.  To control this
                behaviour use the 'exact_match' parameter.

                'version_id' indicates the version of the api the client is
                expecting to use.

                'progresstracker' is the ProgressTracker object the client wants
                the api to use for UI progress callbacks.

                'cancel_state_callable' is an optional function reference that
                will be called if the cancellable status of an operation
                changes.

                'pkg_client_name' is a string containing the name of the client,
                such as "pkg" or "packagemanager".

                'exact_match' is a boolean indicating whether the API should
                attempt to find a usable image starting from the specified
                directory, going up to the filesystem root until it finds one.
                If set to True, an image must exist at the location indicated
                by 'img_path'.  If set to False for a client running on the
                Solaris platform, an ImageLocationAmbiguous exception will be
                raised if an image is found somewhere other than '/'.  For all
                other platforms, a value of False will allow any image location.
                """

                compatible_versions = set([CURRENT_API_VERSION, 60])

                if version_id not in compatible_versions:
                        raise apx.VersionException(CURRENT_API_VERSION,
                            version_id)

                if sys.path[0].startswith("/dev/fd/"):
                        #
                        # Normally when the kernel forks off an interpreted
                        # program, it executes the interpreter with the first
                        # argument being the path to the interpreted program
                        # we're executing.  But in the case of suid scripts
                        # this presents a security problem because that path
                        # could be updated after exec but before the
                        # interpreter opens reads the program.  To avoid this
                        # race, for suid script the kernel replaces the name
                        # of the interpreted program with /dev/fd/###, and
                        # opens the interpreted program such that it can be
                        # read from the specified file descriptor device node.
                        # So if we detect that path[0] (which should be then
                        # interpreted program name) is a /dev/fd/ path, that
                        # means we're being run as an suid script, which we
                        # don't really want to support.  (Since this breaks
                        # our subsequent code that attempt to determine the
                        # name of the executable we are running as.)
                        #
                        raise apx.SuidUnsupportedError()

                # The image's History object will use client_name from
                # global_settings, but if the program forgot to set it,
                # we'll go ahead and do so here.
                if global_settings.client_name is None:
                        global_settings.client_name = pkg_client_name

                if runid < 0:
                        runid = os.getpid()
                self.__runid = runid

                if cmdpath == None:
                        cmdpath = misc.api_cmdpath()
                self.cmdpath = cmdpath

                # prevent brokeness in the test suite
                if self.cmdpath and \
                    "PKG_NO_RUNPY_CMDPATH" in os.environ and \
                    self.cmdpath.endswith(os.sep + "run.py"):
                        raise RuntimeError, """
An ImageInterface object was allocated from within ipkg test suite and
cmdpath was not explicitly overridden.  Please make sure to set
explicitly set cmdpath when allocating an ImageInterface object, or
override cmdpath when allocating an Image object by setting PKG_CMDPATH
in the environment or by setting simulate_cmdpath in DebugValues."""

                if isinstance(img_path, basestring):
                        # Store this for reset().
                        self._img_path = img_path
                        self._img = image.Image(img_path,
                            progtrack=progresstracker,
                            user_provided_dir=exact_match,
                            cmdpath=self.cmdpath,
                            runid=runid)

                        # Store final image path.
                        self._img_path = self._img.get_root()
                elif isinstance(img_path, image.Image):
                        # This is a temporary, special case for client.py
                        # until the image api is complete.
                        self._img = img_path
                        self._img_path = img_path.get_root()
                else:
                        # API consumer passed an unknown type for img_path.
                        raise TypeError(_("Unknown img_path type."))

                self.__progresstracker = progresstracker
                lin = None
                if self._img.linked.ischild():
                        lin = self._img.linked.child_name
                self.__progresstracker.set_linked_name(lin)

                self.__cancel_state_callable = cancel_state_callable
                self.__stage = API_STAGE_DEFAULT
                self.__plan_type = None
                self.__api_op = None
                self.__plan_desc = None
                self.__planned_children = False
                self.__prepared = False
                self.__executed = False
                self.__be_activate = True
                self.__be_name = None
                self.__can_be_canceled = False
                self.__canceling = False
                self._activity_lock = pkg.nrlock.NRLock()
                self.__blocking_locks = False
                self._img.blocking_locks = self.__blocking_locks
                self.__cancel_lock = pkg.nrlock.NRLock()
                self.__cancel_cv = threading.Condition(self.__cancel_lock)
                self.__new_be = None # create if needed
                self.__alt_sources = {}

        def __set_blocking_locks(self, value):
                self._activity_lock.acquire()
                self.__blocking_locks = value
                self._img.blocking_locks = value
                self._activity_lock.release()

        def __set_img_alt_sources(self, repos):
                """Private helper function to change image to use alternate
                package sources if applicable."""

                # When using alternate package sources with the image, the
                # result is a composite of the package data already known
                # by the image and the alternate sources.
                if repos:
                        self._img.set_alt_pkg_sources(
                            self.__get_alt_pkg_data(repos))
                else:
                        self._img.set_alt_pkg_sources(None)

        blocking_locks = property(lambda self: self.__blocking_locks,
            __set_blocking_locks, doc="A boolean value indicating whether "
            "the API should wait until the image interface can be locked if "
            "it is in use by another thread or process.  Clients should be "
            "aware that there is no timeout mechanism in place if blocking is "
            "enabled, and so should take steps to remain responsive to user "
            "input or provide a way for users to cancel operations.")

        @property
        def excludes(self):
                """The list of excludes for the image."""
                return self._img.list_excludes()

        @property
        def img(self):
                """Private; public access to this property will be removed at
                a later date.  Do not use."""
                return self._img

        @property
        def img_type(self):
                """Returns the IMG_TYPE constant for the image's type."""
                if not self._img:
                        return None
                return self._img.image_type(self._img.root)

        @property
        def is_zone(self):
                """A boolean value indicating whether the image is a zone."""
                return self._img.is_zone()

        @property
        def last_modified(self):
                """A datetime object representing when the image's metadata was
                last updated."""

                return self._img.get_last_modified()

        def __set_progresstracker(self, value):
                self._activity_lock.acquire()
                self.__progresstracker = value
                self._activity_lock.release()

        progresstracker = property(lambda self: self.__progresstracker,
            __set_progresstracker, doc="The current ProgressTracker object.  "
            "This value should only be set when no other API calls are in "
            "progress.")

        @property
        def root(self):
                """The absolute pathname of the filesystem root of the image.
                This property is read-only."""
                if not self._img:
                        return None
                return self._img.root

        @staticmethod
        def check_be_name(be_name):
                bootenv.BootEnv.check_be_name(be_name)
                return True

        def set_stage(self, stage):
                """Tell the api which stage of execution we're in.  This is
                used when executing in child images during recursive linked
                operations."""

                assert stage in api_stage_values
                self.__stage = stage

        def __cert_verify(self, log_op_end=None):
                """Verify validity of certificates.  Any apx.ExpiringCertificate
                exceptions are caught here, a message is displayed, and
                execution continues.

                All other exceptions will be passed to the calling context.
                The caller can also set log_op_end to a list of exceptions
                that should result in a call to self.log_operation_end()
                before the exception is passed on.
                """

                if log_op_end == None:
                        log_op_end = []

                # we always explicitly handle apx.ExpiringCertificate
                assert apx.ExpiringCertificate not in log_op_end

                try:
                        self._img.check_cert_validity()
                except apx.ExpiringCertificate, e:
                        logger.error(e)
                except:
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        if exc_type in log_op_end:
                                self.log_operation_end(error=exc_value)
                        raise

        def __refresh_publishers(self):
                """Refresh publisher metadata; this should only be used by
                functions in this module for implicit refresh cases."""

                #
                # Verify validity of certificates before possibly
                # attempting network operations.
                #
                self.__cert_verify()
                try:
                        self._img.refresh_publishers(immediate=True,
                            progtrack=self.__progresstracker)
                except apx.ImageFormatUpdateNeeded:
                        # If image format update is needed to perform refresh,
                        # continue on and allow failure to happen later since
                        # an implicit refresh failing for this reason isn't
                        # important.  (This allows planning installs and updates
                        # before the format of an image is updated.  Yes, this
                        # means that if the refresh was needed to do that, then
                        # this isn't useful, but this is as good as it gets.)
                        logger.warning(_("Skipping publisher metadata refresh;"
                            "image rooted at %s must have its format updated "
                            "before a refresh can occur.") % self._img.root)

        def _acquire_activity_lock(self):
                """Private helper method to aqcuire activity lock."""

                rc = self._activity_lock.acquire(
                    blocking=self.__blocking_locks)
                if not rc:
                        raise apx.ImageLockedError()

        def __plan_common_start(self, operation, noexecute, new_be, be_name,
            be_activate):
                """Start planning an operation:
                    Acquire locks.
                    Log the start of the operation.
                    Check be_name."""

                self._acquire_activity_lock()
                try:
                        self._enable_cancel()
                        if self.__plan_type is not None:
                                raise apx.PlanExistsException(
                                    self.__plan_type)
                        self._img.lock(allow_unprivileged=noexecute)
                except:
                        self._cancel_cleanup_exception()
                        self._activity_lock.release()
                        raise

                assert self._activity_lock._is_owned()
                self.log_operation_start(operation)
                self.__new_be = new_be
                self.__be_activate = be_activate
                self.__be_name = be_name
                if self.__be_name is not None:
                        self.check_be_name(be_name)
                        if not self._img.is_liveroot():
                                raise apx.BENameGivenOnDeadBE(self.__be_name)

        def __plan_common_finish(self):
                """Finish planning an operation."""

                assert self._activity_lock._is_owned()
                self._img.cleanup_downloads()
                self._img.unlock()
                try:
                        if int(os.environ.get("PKG_DUMP_STATS", 0)) > 0:
                                self._img.transport.stats.dump()
                except ValueError:
                        # Don't generate stats if an invalid value
                        # is supplied.
                        pass

                self._activity_lock.release()

        def __set_new_be(self):
                """Figure out whether or not we'd create a new boot environment
                given inputs and plan.  Toss cookies if we need a new be and
                can't have one."""
                # decide whether or not to create new BE.

                if self._img.is_liveroot():
                        if self.__new_be is None:
                                self.__new_be = self._img.imageplan.reboot_needed()
                        elif self.__new_be is False and \
                            self._img.imageplan.reboot_needed():
                                raise apx.ImageUpdateOnLiveImageException()
                else:
                        self.__new_be = False

        def avoid_pkgs(self, fmri_strings, unavoid=False):
                """Avoid/Unavoid one or more packages.  It is an error to
                avoid an installed package, or unavoid one that would
                be installed."""

                self._acquire_activity_lock()
                try:
                        if not unavoid:
                                self._img.avoid_pkgs(fmri_strings,
                                    progtrack=self.__progresstracker,
                                    check_cancel=self.__check_cancel)
                        else:
                                self._img.unavoid_pkgs(fmri_strings,
                                    progtrack=self.__progresstracker,
                                    check_cancel=self.__check_cancel)
                finally:
                        self._activity_lock.release()
                return True

        def get_avoid_list(self):
                """Return list of tuples of (pkg stem, pkgs w/ group
                dependencies on this) """
                return [a for a in self._img.get_avoid_dict().iteritems()]

        def __plan_common_exception(self, log_op_end_all=False):
                """Deal with exceptions that can occur while planning an
                operation.  Any exceptions generated here are passed
                onto the calling context.  By default all exceptions
                will result in a call to self.log_operation_end() before
                they are passed onto the calling context."""

                exc_type, exc_value, exc_traceback = sys.exc_info()

                if exc_type == apx.PlanCreationException:
                        self.__set_history_PlanCreationException(exc_value)
                elif exc_type == apx.CanceledException:
                        self._cancel_done()
                elif exc_type == apx.ConflictingActionErrors:
                        self.log_operation_end(error=str(exc_value),
                            result=history.RESULT_CONFLICTING_ACTIONS)
                elif exc_type in [
                    apx.IpkgOutOfDateException,
                    fmri.IllegalFmri]:
                        self.log_operation_end(error=exc_value)
                elif log_op_end_all:
                        self.log_operation_end(error=exc_value)

                if exc_type != apx.ImageLockedError:
                        # Must be called before reset_unlock, and only if
                        # the exception was not a locked error.
                        self._img.unlock()

                try:
                        if int(os.environ.get("PKG_DUMP_STATS", 0)) > 0:
                                self._img.transport.stats.dump()
                except ValueError:
                        # Don't generate stats if an invalid value
                        # is supplied.
                        pass

                # In the case of duplicate actions, we want to save off the plan
                # description for display to the client (if they requested it),
                # as once the solver's done its job, there's interesting
                # information in the plan.  We have to save it here and restore
                # it later because __reset_unlock() torches it.
                if exc_type == apx.ConflictingActionErrors:
                        plan_desc = PlanDescription(self._img, self.__new_be,
                            self.__be_activate)

                self.__reset_unlock()

                if exc_type == apx.ConflictingActionErrors:
                        self.__plan_desc = plan_desc

                self._activity_lock.release()
                raise

        def solaris_image(self):
                """Returns True if the current image is a solaris image, or an
                image which contains the pkg(5) packaging system."""

                # First check to see if the special package "release/name"
                # exists and contains metadata saying this is Solaris.
                results = self.__get_pkg_list(self.LIST_INSTALLED,
                    patterns=["release/name"], return_fmris=True)
                results = [e for e in results]
                if results:
                        pfmri, summary, categories, states = \
                            results[0]
                        mfst = self._img.get_manifest(pfmri)
                        osname = mfst.get("pkg.release.osname", None)
                        if osname == "sunos":
                                return True

                # Otherwise, see if we can find package/pkg (or SUNWipkg) and
                # SUNWcs.
                results = self.__get_pkg_list(self.LIST_INSTALLED,
                    patterns=["pkg:/package/pkg", "SUNWipkg", "SUNWcs"])
                installed = set(e[0][1] for e in results)
                if "SUNWcs" in installed and ("SUNWipkg" in installed or
                    "package/pkg" in installed):
                        return True

                return False

        def __ipkg_require_latest(self, noexecute):
                """Raises an IpkgOutOfDateException if the current image
                contains the pkg(5) packaging system and a newer version
                of the pkg(5) packaging system is installable."""

                if not self.solaris_image():
                        return
                try:
                        if self._img.ipkg_is_up_to_date(
                            self.__check_cancel, noexecute,
                            refresh_allowed=False,
                            progtrack=self.__progresstracker):
                                return
                except apx.ImageNotFoundException:
                        # Can't do anything in this
                        # case; so proceed.
                        return

                raise apx.IpkgOutOfDateException()

        def __plan_op(self, _op, _accept=False, _ad_kwargs=None,
            _be_activate=True, _be_name=None, _ipkg_require_latest=False,
            _li_ignore=None, _li_md_only=False, _li_parent_sync=True,
            _new_be=False, _noexecute=False, _refresh_catalogs=True,
            _repos=None, _update_index=True,
            **kwargs):
                """Contructs a plan to change the package or linked image
                state of an image.

                We can raise PermissionsException, PlanCreationException,
                InventoryException, or LinkedImageException.

                Arguments prefixed with '_' are primarily used within this
                function.  All other arguments must be specified via keyword
                assignment and will be passed directly on to the image
                interfaces being invoked."

                '_op' is the API operation we will perform.

                '_ad_kwargs' is only used dyring attach or detach and it
                is a dictionary of arguments that will be passed to the
                linked image attach/detach interfaces.

                '_ipkg_require_latest' enables a check to verify that the
                latest installable version of the pkg(5) packaging system is
                installed before we proceed with the requested operation.

                For all other '_' prefixed parameters, please refer to the
                'gen_plan_*' functions which invoke this function for an
                explanation of their usage and effects.

                This function returns a boolean indicating whether there is
                anything to do."""

                # sanity checks
                assert _op in api_op_values
                assert _ad_kwargs == None or \
                    _op in [API_OP_ATTACH, API_OP_DETACH]
                assert _ad_kwargs != None or \
                    _op not in [API_OP_ATTACH, API_OP_DETACH]
                assert not _li_md_only or \
                    _op in [API_OP_ATTACH, API_OP_DETACH, API_OP_SYNC]
                assert not _li_md_only or _li_parent_sync

                # make some perf optimizations
                if _li_md_only:
                        _refresh_catalogs = _update_index = False
                if self.__stage not in [API_STAGE_DEFAULT, API_STAGE_PUBCHECK]:
                        _li_parent_sync = False
                if self.__stage not in [API_STAGE_DEFAULT, API_STAGE_PLAN]:
                        _refresh_catalogs = False
                        _ipkg_require_latest = False

                # if we have any children we don't support operations using
                # temporary repositories.
                if _repos and self._img.linked.list_related(_li_ignore):
                        raise apx.PlanCreationException(no_tmp_origins=True)

                # All the image interface functions that we inovke have some
                # common arguments.  Set those up now.
                args_common = {}
                args_common["op"] = _op
                args_common["progtrack"] = self.__progresstracker
                args_common["check_cancel"] = self.__check_cancel
                args_common["noexecute"] = _noexecute
                args_common["ip_mode"] = self.__stage_2_ip_mode[self.__stage]


                # make sure there is no overlap between the common arguments
                # supplied to all api interfaces and the arguments that the
                # api arguments that caller passed to this function.
                assert (set(args_common) & set(kwargs)) == set(), \
                    "%s & %s != set()" % (str(set(args_common)),
                    str(set(kwargs)))
                kwargs.update(args_common)

                # Lock the current image.
                self.__plan_common_start(_op, _noexecute, _new_be, _be_name,
                    _be_activate)

                try:
                        # reset any child recursion state we might have
                        self._img.linked.reset_recurse()

                        # prepare to recurse into child images
                        self._img.linked.init_recurse(_op, _li_ignore,
                            _accept, _refresh_catalogs, _update_index, kwargs)

                        if _op == API_OP_ATTACH:
                                self._img.linked.attach_parent(**_ad_kwargs)
                        elif _op == API_OP_DETACH:
                                self._img.linked.detach_parent(**_ad_kwargs)

                        if _li_parent_sync:
                                # try to refresh linked image
                                # constraints from the parent image.
                                self._img.linked.syncmd_from_parent(_op)

                        if self.__stage in [API_STAGE_DEFAULT,
                            API_STAGE_PUBCHECK]:

                                # do a linked image publisher check
                                self._img.linked.check_pubs(_op)
                                self._img.linked.do_recurse(API_STAGE_PUBCHECK)

                                if self.__stage == API_STAGE_PUBCHECK:
                                        # If this was just a publisher check
                                        # then return immediately.
                                        return

                        if _refresh_catalogs:
                                self.__refresh_publishers()

                        if _ipkg_require_latest:
                                # If this is an image update then make
                                # sure the latest version of the ipkg
                                # software is installed.
                                self.__ipkg_require_latest(_noexecute)

                        self.__set_img_alt_sources(_repos)

                        if _li_md_only:
                                self._img.make_noop_plan(**args_common)
                        elif _op in [API_OP_ATTACH, API_OP_DETACH, API_OP_SYNC]:
                                self._img.make_sync_plan(**kwargs)
                        elif _op in [API_OP_CHANGE_FACET,
                            API_OP_CHANGE_VARIANT]:
                                self._img.make_change_varcets_plan(**kwargs)
                        elif _op == API_OP_INSTALL:
                                self._img.make_install_plan(**kwargs)
                        elif _op == API_OP_REVERT:
                                self._img.make_revert_plan(**kwargs)
                        elif _op == API_OP_UNINSTALL:
                                self._img.make_uninstall_plan(**kwargs)
                        elif _op == API_OP_UPDATE:
                                self._img.make_update_plan(**kwargs)
                        else:
                                raise RuntimeError("Unknown api op: %s" % _op)

                        self.__api_op = _op
                        self.__accept = _accept
                        if not _noexecute:
                                self.__plan_type = self.__api_op_2_plan[_op]

                        if self._img.imageplan.nothingtodo():
                                # no package changes mean no index changes
                                _update_index = False

                        self._disable_cancel()
                        self.__set_new_be()
                        self.__plan_desc = PlanDescription(self._img,
                            self.__new_be, self.__be_activate)

                        # Yield to our caller so they can display our plan
                        # before we recurse into child images.  Drop the
                        # activity lock before yielding because otherwise the
                        # caller can't do things like set the displayed
                        # license state for pkg plans).
                        self._activity_lock.release()
                        yield self.__plan_desc
                        self._activity_lock.acquire()

                        # plan operation in child images.  eventually these
                        # will yield plan descriptions objects as well.
                        if self.__stage in [API_STAGE_DEFAULT, API_STAGE_PLAN]:
                                self._img.linked.do_recurse(API_STAGE_PLAN,
                                    ip=self._img.imageplan)
                        self.__planned_children = True

                except:
                        if _op in [
                            API_OP_UPDATE,
                            API_OP_INSTALL,
                            API_OP_REVERT,
                            API_OP_SYNC]:
                                self.__plan_common_exception(
                                    log_op_end_all=True)
                        else:
                                self.__plan_common_exception()
                        # NOTREACHED

                stuff_to_do = not self.planned_nothingtodo()

                if not stuff_to_do or _noexecute:
                        self.log_operation_end(
                            result=history.RESULT_NOTHING_TO_DO)

                self._img.imageplan.update_index = _update_index
                self.__plan_common_finish()

        def planned_nothingtodo(self, li_ignore_all=False):
                """Once an operation has been planned check if there is
                something todo.

                Callers should pass all arguments by name assignment and
                not by positional order.

                'li_ignore_all' indicates if we should only report on work
                todo in the parent image.  (i.e., if an operation was planned
                and that operation only involves changes to children, and
                li_ignore_all is true, then we'll report that there's nothing
                todo."""

                if self.__stage == API_STAGE_PUBCHECK:
                        # if this was just a publisher check then report
                        # that there is something todo so we continue with
                        # the operation.
                        return False
                if not self._img.imageplan:
                        # if theres no plan there nothing to do
                        return True
                if not self._img.imageplan.nothingtodo():
                        return False
                if not self._img.linked.nothingtodo():
                        return False
                if not li_ignore_all:
                        assert self.__planned_children
                        if not self._img.linked.recurse_nothingtodo():
                                return False
                return True

        def plan_update(self, pkg_list, refresh_catalogs=True,
            reject_list=None, noexecute=False, update_index=True,
            be_name=None, new_be=False, repos=None, be_activate=True):
                """DEPRECATED.  use gen_plan_update()."""
                for pd in self.gen_plan_update(
                    pkgs_update=pkg_list, refresh_catalogs=refresh_catalogs,
                    reject_list=reject_list, noexecute=noexecute,
                    update_index=update_index, be_name=be_name, new_be=new_be,
                    repos=repos, be_activate=be_activate):
                        continue
                return not self.planned_nothingtodo()

        def plan_update_all(self, refresh_catalogs=True,
            reject_list=None, noexecute=False, force=False,
            update_index=True, be_name=None, new_be=True, repos=None,
            be_activate=True):
                """DEPRECATED.  use gen_plan_update()."""
                for pd in self.gen_plan_update(
                    refresh_catalogs=refresh_catalogs, reject_list=reject_list,
                    noexecute=noexecute, force=force,
                    update_index=update_index, be_name=be_name, new_be=new_be,
                    repos=repos, be_activate=be_activate):
                        continue
                return (not self.planned_nothingtodo(), self.solaris_image())

        def gen_plan_update(self, pkgs_update=None, accept=False,
            be_activate=True, be_name=None, force=False, li_ignore=None,
            li_parent_sync=True, new_be=True, noexecute=False,
            refresh_catalogs=True, reject_list=None, repos=None,
            update_index=True):
                """This is a generator function that returns PlanDescription
                objects.

                If pkgs_update is not set, constructs a plan to update all
                packages on the system to the latest known versions.  Once an
                operation has been planned, it may be executed by first
                calling prepare(), and then execute_plan().  After execution
                of a plan, or to abandon a plan, reset() should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                If 'pkgs_update' is set, constructs a plan to update the
                packages provided in pkgs_update.

                Once an operation has been planned, it may be executed by
                first calling prepare(), and then execute_plan().

                'force' indicates whether update should skip the package
                system up to date check.

                For all other parameters, refer to the 'gen_plan_install'
                function for an explanation of their usage and effects."""

                if pkgs_update or force:
                        ipkg_require_latest = False
                else:
                        ipkg_require_latest = True

                op = API_OP_UPDATE
                return self.__plan_op(op, _accept=accept,
                    _be_activate=be_activate, _be_name=be_name,
                    _ipkg_require_latest=ipkg_require_latest,
                    _li_ignore=li_ignore, _li_parent_sync=li_parent_sync,
                    _new_be=new_be, _noexecute=noexecute,
                    _refresh_catalogs=refresh_catalogs, _repos=repos,
                    _update_index=update_index, pkgs_update=pkgs_update,
                    reject_list=reject_list)

        def plan_install(self, pkg_list, refresh_catalogs=True,
            noexecute=False, update_index=True, be_name=None,
            reject_list=None, new_be=False, repos=None,
            be_activate=True):
                """DEPRECATED.  use gen_plan_install()."""
                for pd in self.gen_plan_install(
                     pkgs_inst=pkg_list, refresh_catalogs=refresh_catalogs,
                     noexecute=noexecute, update_index=update_index,
                     be_name=be_name, reject_list=reject_list, new_be=new_be,
                     repos=repos, be_activate=be_activate):
                        continue
                return not self.planned_nothingtodo()

        def gen_plan_install(self, pkgs_inst, accept=False, be_activate=True,
            be_name=None, li_ignore=None, li_parent_sync=True, new_be=False,
            noexecute=False, refresh_catalogs=True, reject_list=None,
            repos=None, update_index=True):
                """This is a generator function that returns PlanDescription
                objects.

                Constructs a plan to install the packages provided in
                pkgs_inst.  Once an operation has been planned, it may be
                executed by first calling prepare(), and then execute_plan().
                After execution of a plan, or to abandon a plan, reset()
                should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                'pkgs_inst' is a list of packages to install.

                'be_name' is a string to use as the name of any new boot
                environment created during the operation.

                'li_ignore' is either None or a list.  If it's None (the
                default), the planning operation will attempt to keep all
                linked children in sync.  If it's an empty list the planning
                operation will ignore all children.  If this is a list of
                linked image children names, those children will be ignored
                during the planning operation.  If a child is ignored during
                the planning phase it will also be skipped during the
                preparation and execution phases.

                'li_parent_sync' if the current image is a child image, this
                flag controls whether the linked image parent metadata will be
                automatically refreshed.

                'new_be' indicates whether a new boot environment should be
                created during the operation.  If True, a new boot environment
                will be created.  If False, and a new boot environment is
                needed, an ImageUpdateOnLiveImageException will be raised.
                If None, a new boot environment will be created only if needed.

                'noexecute' determines whether the resulting plan can be
                executed and whether history will be recorded after
                planning is finished.

                'refresh_catalogs' controls whether the catalogs will
                automatically be refreshed.

                'reject_list' is a list of patterns not to be permitted
                in solution; installed packages matching these patterns
                are removed.

                'repos' is a list of URI strings or RepositoryURI objects that
                represent the locations of additional sources of package data to
                use during the planned operation.  All API functions called
                while a plan is still active will use this package data.

                'be_activate' is an optional boolean indicating whether any
                new boot environment created for the operation should be set
                as the active one on next boot if the operation is successful.

                'update_index' determines whether client search indexes
                will be updated after operation completion during plan
                execution."""

                # certain parameters must be specified
                assert pkgs_inst and type(pkgs_inst) == list

                op = API_OP_INSTALL
                return self.__plan_op(op, _accept=accept,
                    _be_activate=be_activate, _be_name=be_name,
                    _li_ignore=li_ignore, _li_parent_sync=li_parent_sync,
                    _new_be=new_be, _noexecute=noexecute,
                    _refresh_catalogs=refresh_catalogs, _repos=repos,
                    _update_index=update_index, pkgs_inst=pkgs_inst,
                    reject_list=reject_list)

        def gen_plan_sync(self, accept=False, be_activate=True, be_name=None,
            li_ignore=None, li_md_only=False, li_parent_sync=True,
            li_pkg_updates=True, new_be=False, noexecute=False,
            refresh_catalogs=True, reject_list=None, repos=None,
            update_index=True):
                """This is a generator function that returns PlanDescription
                objects.

                Constructs a plan to sync the current image with its
                linked image constraints.  Once an operation has been planned,
                it may be executed by first calling prepare(), and then
                execute_plan().  After execution of a plan, or to abandon a
                plan, reset() should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                'li_md_only' don't actually modify any packages in the current
                images, only sync the linked image metadata from the parent
                image.  If this options is True, 'li_parent_sync' must also be
                True.

                'li_pkg_updates' when planning a sync operation, allow updates
                to packages other than the constraints package.  If this
                option is False, planning a sync will fail if any packages
                (other than the constraints package) need updating to bring
                the image in sync with its parent.

                For all other parameters, refer to the 'gen_plan_install'
                function for an explanation of their usage and effects."""

                # verify that the current image is a linked image by trying to
                # access its name.
                self._img.linked.child_name

                op = API_OP_SYNC
                return self.__plan_op(op, _accept=accept,
                    _be_activate=be_activate, _be_name=be_name,
                    _li_ignore=li_ignore, _li_md_only=li_md_only,
                    _li_parent_sync=li_parent_sync, _new_be=new_be,
                    _noexecute=noexecute, _refresh_catalogs=refresh_catalogs,
                    _repos=repos, _update_index=update_index,
                    li_pkg_updates=li_pkg_updates, reject_list=reject_list)

        def gen_plan_attach(self, lin, li_path, accept=False,
            allow_relink=False, be_activate=True, be_name=None,
            force=False, li_ignore=None, li_md_only=False,
            li_pkg_updates=True, li_props=None, new_be=False,
            noexecute=False, refresh_catalogs=True, reject_list=None,
            repos=None, update_index=True):
                """This is a generator function that returns PlanDescription
                objects.

                Attach a parent image and sync the packages in the current
                image with the new parent.  Once an operation has been
                planned, it may be executed by first calling prepare(), and
                then execute_plan().  After execution of a plan, or to abandon
                a plan, reset() should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                'lin' a LinkedImageName object that is a name for the current
                image.

                'li_path' a path to the parent image.

                'allow_relink' allows re-linking of an image that is already a
                linked image child.  If this option is True we'll overwrite
                all existing linked image metadata.

                'li_props' optional linked image properties to apply to the
                child image.

                For all other parameters, refer to the 'gen_plan_install' and
                'gen_plan_sync' functions for an explanation of their usage
                and effects."""

                if li_props == None:
                        li_props = dict()

                op = API_OP_ATTACH
                ad_kwargs = {
                    "allow_relink": allow_relink,
                    "force": force,
                    "lin": lin,
                    "path": li_path,
                    "props": li_props,
                }
                return self.__plan_op(op, _accept=accept,
                    _be_activate=be_activate, _be_name=be_name,
                    _li_ignore=li_ignore, _li_md_only=li_md_only,
                    _new_be=new_be, _noexecute=noexecute,
                    _refresh_catalogs=refresh_catalogs, _repos=repos,
                    _update_index=update_index, _ad_kwargs=ad_kwargs,
                    li_pkg_updates=li_pkg_updates, reject_list=reject_list)

        def gen_plan_detach(self, accept=False, be_activate=True,
            be_name=None, force=False, li_ignore=None, new_be=False,
            noexecute=False):
                """This is a generator function that returns PlanDescription
                objects.

                Detach from a parent image and remove any constraints
                package from this image.  Once an operation has been planned,
                it may be executed by first calling prepare(), and then
                execute_plan().  After execution of a plan, or to abandon a
                plan, reset() should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                For all other parameters, refer to the 'gen_plan_install' and
                'gen_plan_sync' functions for an explanation of their usage
                and effects."""

                op = API_OP_DETACH
                ad_kwargs = {
                    "force": force
                }
                return self.__plan_op(op, _accept=accept, _ad_kwargs=ad_kwargs,
                    _be_activate=be_activate, _be_name=be_name,
                    _li_ignore=li_ignore, _new_be=new_be,
                    _noexecute=noexecute, _refresh_catalogs=False,
                    _update_index=False, li_pkg_updates=False)

        def plan_uninstall(self, pkg_list, noexecute=False, update_index=True,
            be_name=None, new_be=False, be_activate=True):
                """DEPRECATED.  use gen_plan_uninstall()."""
                for pd in self.gen_plan_uninstall(pkgs_to_uninstall=pkg_list,
                    noexecute=noexecute, update_index=update_index,
                    be_name=be_name, new_be=new_be, be_activate=be_activate):
                        continue
                return not self.planned_nothingtodo()

        def gen_plan_uninstall(self, pkgs_to_uninstall, accept=False,
            be_activate=True, be_name=None, li_ignore=None, new_be=False,
            noexecute=False, update_index=True):
                """This is a generator function that returns PlanDescription
                objects.

                Constructs a plan to remove the packages provided in
                pkgs_to_uninstall.  Once an operation has been planned, it may
                be executed by first calling prepare(), and then
                execute_plan().  After execution of a plan, or to abandon a
                plan, reset() should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                'pkgs_to_uninstall' is a list of packages to uninstall.

                For all other parameters, refer to the 'gen_plan_install'
                function for an explanation of their usage and effects."""

                # certain parameters must be specified
                assert pkgs_to_uninstall and type(pkgs_to_uninstall) == list

                op = API_OP_UNINSTALL
                return self.__plan_op(op, _accept=accept,
                    _be_activate=be_activate, _be_name=be_name,
                    _li_ignore=li_ignore, _li_parent_sync=False,
                    _new_be=new_be, _noexecute=noexecute,
                    _refresh_catalogs=False, _update_index=update_index,
                    pkgs_to_uninstall=pkgs_to_uninstall)

        def plan_change_varcets(self, variants=None, facets=None,
            noexecute=False, be_name=None, new_be=None, repos=None,
            be_activate=True):
                """DEPRECATED.  use gen_plan_change_varcets()."""
                for pd in self.gen_plan_change_varcets(
                    variants=variants, facets=facets, noexecute=noexecute,
                    be_name=be_name, new_be=new_be, repos=repos,
                    be_activate=be_activate):
                        continue
                return not self.planned_nothingtodo()

        def gen_plan_change_varcets(self, facets=None, variants=None,
            accept=False, be_activate=True, be_name=None, li_ignore=None,
            li_parent_sync=True, new_be=None, noexecute=False,
            refresh_catalogs=True, reject_list=None, repos=None,
            update_index=True):
                """This is a generator function that returns PlanDescription
                objects.

                Creates a plan to change the specified variants and/or
                facets for the image.  Once an operation has been planned, it
                may be executed by first calling prepare(), and then
                execute_plan().  After execution of a plan, or to abandon a
                plan, reset() should be called.

                Callers should pass all arguments by name assignment and
                not by positional order.

                'facets' is a dict of the facets to change the values of.

                'variants' is a dict of the variants to change the values of.

                For all other parameters, refer to the 'gen_plan_install'
                function for an explanation of their usage and effects."""

                if not variants and not facets:
                        raise ValueError, "Nothing to do"

                if variants:
                        op = API_OP_CHANGE_VARIANT
                else:
                        op = API_OP_CHANGE_FACET

                return self.__plan_op(op, _accept=accept,
                    _be_activate=be_activate, _be_name=be_name,
                    _li_ignore=li_ignore, _li_parent_sync=li_parent_sync,
                    _new_be=new_be, _noexecute=noexecute,
                    _refresh_catalogs=refresh_catalogs, _repos=repos,
                    _update_index=update_index, variants=variants,
                    facets=facets, reject_list=reject_list)

        def plan_revert(self, args, tagged=False, noexecute=True, be_name=None,
            new_be=None, be_activate=True):
                """DEPRECATED.  use gen_plan_revert()."""
                for pd in self.gen_plan_revert(
                    args=args, tagged=tagged, noexecute=noexecute,
                    be_name=be_name, new_be=new_be, be_activate=be_activate):
                        continue
                return not self.planned_nothingtodo()

        def gen_plan_revert(self, args, tagged=False, noexecute=True,
            be_activate=True, be_name=None, new_be=None):
                """This is a generator function that returns PlanDescription
                objects.

                Plan to revert either files or all files tagged with
                specified values.  Args contains either path names or tag
                names to be reverted, tagged is True if args contains tags.
                Once an operation has been planned, it may be executed by
                first calling prepare(), and then execute_plan().  After
                execution of a plan, or to abandon a plan, reset() should be
                called.

                For all other parameters, refer to the 'gen_plan_install'
                function for an explanation of their usage and effects."""

                op = API_OP_REVERT
                return self.__plan_op(op, _be_activate=be_activate,
                    _be_name=be_name, _li_ignore=[], _new_be=new_be,
                    _noexecute=noexecute, _refresh_catalogs=False,
                    _update_index=False, args=args, tagged=tagged)

        def attach_linked_child(self, lin, li_path, li_props=None,
            accept=False, allow_relink=False, force=False, li_md_only=False,
            li_pkg_updates=True, noexecute=False,
            refresh_catalogs=True, show_licenses=False, update_index=True):
                """Attach an image as a child to the current image (the
                current image will become a parent image. This operation
                results in attempting to sync the child image with the parent
                image.

                'lin' is the name of the child image

                'li_path' is the path to the child image

                'li_props' optional linked image properties to apply to the
                child image.

                'accept' indicates whether we should accept package licenses
                for any packages being installed during the child image sync.

                'allow_relink' indicates whether we should allow linking of a
                child image that is already linked (the child may already
                be a child or a parent image).

                'force' indicates whether we should allow linking of a child
                image even if the specified linked image type doesn't support
                attaching of children.

                'li_md_only' indicates whether we should only update linked
                image metadata and not actually try to sync the child image.

                'li_pkg_updates' indicates whether we should disallow pkg
                updates during the child image sync.

                'noexecute' indicates if we should actually make any changes
                rather or just simulate the operation.

                'refresh_catalogs' controls whether the catalogs will
                automatically be refreshed.

                'show_licenses' indicates whether we should display package
                licenses for any packages being installed during the child
                image sync.

                'update_index' determines whether client search indexes will
                be updated in the child after the sync operation completes.

                This function returns a tuple of the format (rv, err) where rv
                is a pkg.client.pkgdefs return value and if an error was
                encountered err is an exception object which describes the
                error."""

                return self._img.linked.attach_child(lin, li_path, li_props,
                    accept=accept, allow_relink=allow_relink, force=force,
                    li_md_only=li_md_only, li_pkg_updates=li_pkg_updates,
                    noexecute=noexecute, progtrack=self.__progresstracker,
                    refresh_catalogs=refresh_catalogs,
                    show_licenses=show_licenses, update_index=update_index)

        def detach_linked_children(self, li_list, force=False, noexecute=False):
                """Detach one or more children from the current image. This
                operation results in the removal of any constraint package
                from the child images.

                'li_list' a list of linked image name objects which specified
                which children to operate on.  If the list is empty then we
                operate on all children.

                For all other parameters, refer to the 'attach_linked_child'
                function for an explanation of their usage and effects.

                This function returns a dictionary where the keys are linked
                image name objects and the values are the result of the
                specified operation on the associated child image.  The result
                is a tuple of the format (rv, err) where rv is a
                pkg.client.pkgdefs return value and if an error was
                encountered err is an exception object which describes the
                error."""

                rvdict = self._img.linked.detach_children(li_list,
                    force=force, noexecute=noexecute,
                    progtrack=self.__progresstracker)
                return rvdict

        def detach_linked_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                return self._img.linked.detach_rvdict2rv(rvdict)

        def sync_linked_children(self, li_list,
            accept=False, li_md_only=False,
            li_pkg_updates=True, noexecute=False, refresh_catalogs=True,
            show_licenses=False, update_index=True):
                """Sync one or more children of the current image.

                For all other parameters, refer to the 'attach_linked_child'
                and 'detach_linked_children' functions for an explanation of
                their usage and effects.

                For a description of the return value, refer to the
                'detach_linked_children' function."""

                rvdict = self._img.linked.sync_children(li_list,
                    accept=accept, li_md_only=li_md_only,
                    li_pkg_updates=li_pkg_updates, noexecute=noexecute,
                    progtrack=self.__progresstracker,
                    refresh_catalogs=refresh_catalogs,
                    show_licenses=show_licenses, update_index=update_index)
                return rvdict

        def sync_linked_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                return self._img.linked.sync_rvdict2rv(rvdict)

        def audit_linked_children(self, li_list):
                """Audit one or more children of the current image to see if
                they are in sync with this image.

                For all parameters, refer to the 'detach_linked_children'
                functions for an explanation of their usage and effects.

                For a description of the return value, refer to the
                'detach_linked_children' function."""

                rvdict = self._img.linked.audit_children(li_list)
                return rvdict

        def audit_linked_rvdict2rv(self, rvdict):
                """Convenience function that takes a dictionary returned from
                an operations on multiple children and merges the results into
                a single return code."""

                return self._img.linked.audit_rvdict2rv(rvdict)

        def audit_linked(self, li_parent_sync=True):
                """If the current image is a child image, this function
                audits the current image to see if it's in sync with it's
                parent.

                For a description of the return value, refer to the
                'detach_linked_children' function."""

                lin = self._img.linked.child_name
                rvdict = {}
                rvdict[lin] = self._img.linked.audit_self(
                    li_parent_sync=li_parent_sync)
                return rvdict

        def ischild(self):
                """Indicates whether the current image is a child image."""
                return self._img.linked.ischild()

        def get_linked_name(self):
                """If the current image is a child image, this function
                returns a linked image name object which represents the name
                of the current image."""
                return self._img.linked.child_name

        def get_linked_props(self, lin=None):
                """Return a dictionary which represents the linked image
                properties associated with a linked image.

                'lin' is the name of the child image.  If lin is None then
                the current image is assumed to be a linked image and it's
                properties are returned."""

                return self._img.linked.child_props(lin=lin)

        def list_linked(self, li_ignore=None):
                """Returns a list of linked images associated with the
                current image.  This includes both child and parent images.

                For all parameters, refer to the 'gen_plan_install' function
                for an explanation of their usage and effects.

                The returned value is a list of tuples where each tuple
                contains (<li name>, <relationship>, <li path>)."""

                return self._img.linked.list_related(li_ignore=li_ignore)

        def parse_linked_name(self, li_name, allow_unknown=False):
                """Given a string representing a linked image child name,
                returns linked image name object representing the same name.

                'allow_unknown' indicates whether the name must represent
                actual children or simply be syntactically correct."""

                return self._img.linked.parse_name(li_name, allow_unknown)

        def parse_linked_name_list(self, li_name_list, allow_unknown=False):
                """Given a list of strings representing linked image child
                names, returns a list of linked image name objects
                representing the same names.

                For all other parameters, refer to the 'parse_linked_name'
                function for an explanation of their usage and effects."""

                return [
                    self.parse_linked_name(li_name, allow_unknown)
                    for li_name in li_name_list
                ]

        def describe(self):
                """Returns None if no plan is ready yet, otherwise returns
                a PlanDescription."""

                return self.__plan_desc

        def prepare(self):
                """Takes care of things which must be done before the plan can
                be executed.  This includes downloading the packages to disk and
                preparing the indexes to be updated during execution.  Should
                only be called once a gen_plan_*() method has been called.  If
                a plan is abandoned after calling this method, reset() should
                be called."""

                self._acquire_activity_lock()
                try:
                        self._img.lock()
                except:
                        self._activity_lock.release()
                        raise

                try:
                        if not self._img.imageplan:
                                raise apx.PlanMissingException()

                        if not self.__planned_children:
                                # if we never planned children images then we
                                # didn't finish planning.
                                raise apx.PlanMissingException()

                        if self.__prepared:
                                raise apx.AlreadyPreparedException()
                        assert self.__plan_type in self.__plan_values, \
                            "self.__plan_type = %s" % self.__plan_type

                        self._enable_cancel()

                        try:
                                self._img.imageplan.preexecute()
                        except search_errors.ProblematicPermissionsIndexException, e:
                                raise apx.ProblematicPermissionsIndexException(e)
                        except:
                                raise

                        self._disable_cancel()
                        self.__prepared = True
                except apx.CanceledException, e:
                        self._cancel_done()
                        if self._img.history.operation_name:
                                # If an operation is in progress, log
                                # the error and mark its end.
                                self.log_operation_end(error=e)
                        raise
                except Exception, e:
                        self._cancel_cleanup_exception()
                        if self._img.history.operation_name:
                                # If an operation is in progress, log
                                # the error and mark its end.
                                self.log_operation_end(error=e)
                        raise
                except:
                        # Handle exceptions that are not subclasses of
                        # Exception.
                        self._cancel_cleanup_exception()
                        if self._img.history.operation_name:
                                # If an operation is in progress, log
                                # the error and mark its end.
                                exc_type, exc_value, exc_traceback = \
                                    sys.exc_info()
                                self.log_operation_end(error=exc_type)
                        raise
                finally:
                        self._img.cleanup_downloads()
                        self._img.unlock()
                        try:
                                if int(os.environ.get("PKG_DUMP_STATS", 0)) > 0:
                                        self._img.transport.stats.dump()
                        except ValueError:
                                # Don't generate stats if an invalid value
                                # is supplied.
                                pass
                        self._activity_lock.release()

                if self.__stage in [API_STAGE_DEFAULT, API_STAGE_PREPARE]:
                        self._img.linked.do_recurse(API_STAGE_PREPARE)

        def execute_plan(self):
                """Executes the plan. This is uncancelable once it begins.
                Should only be called after the prepare method has been
                called.  After plan execution, reset() should be called."""

                self._acquire_activity_lock()
                try:
                        self._disable_cancel()
                        self._img.lock()
                except:
                        self._activity_lock.release()
                        raise

                try:
                        if not self._img.imageplan:
                                raise apx.PlanMissingException()

                        if not self.__prepared:
                                raise apx.PrematureExecutionException()

                        if self.__executed:
                                raise apx.AlreadyExecutedException()

                        assert self.__plan_type in self.__plan_values, \
                            "self.__plan_type = %s" % self.__plan_type

                        try:
                                be = bootenv.BootEnv(self._img)
                        except RuntimeError:
                                be = bootenv.BootEnvNull(self._img)
                        self._img.bootenv = be

                        if self.__new_be == False and \
                            self._img.imageplan.reboot_needed() and \
                            self._img.is_liveroot():
                                e = apx.RebootNeededOnLiveImageException()
                                self.log_operation_end(error=e)
                                raise e

                        if self.__new_be == True:
                                try:
                                        be.init_image_recovery(self._img,
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
                                # check if things gained underneath us
                                if self._img.is_liveroot():
                                        e = apx.UnableToCopyBE()
                                        self.log_operation_end(error=e)
                                        raise e

                        raise_later = None

                        # we're about to execute a plan so change our current
                        # working directory to / so that we won't fail if we
                        # try to remove our current working directory
                        os.chdir(os.sep)

                        try:
                                try:
                                        self._img.imageplan.execute()
                                except apx.WrapIndexingException, e:
                                        raise_later = e

                                if not self._img.linked.nothingtodo():
                                        self._img.linked.syncmd()
                        except RuntimeError, e:
                                if self.__new_be == True:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                # Must be done after bootenv restore.
                                self.log_operation_end(error=e)
                                raise
                        except search_errors.IndexLockedException, e:
                                error = apx.IndexLockedException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except search_errors.ProblematicPermissionsIndexException, e:
                                error = apx.ProblematicPermissionsIndexException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except search_errors.InconsistentIndexException, e:
                                error = apx.CorruptedIndexException(e)
                                self.log_operation_end(error=error)
                                raise error
                        except NonzeroExitException, e:
                                # Won't happen during update
                                be.restore_install_uninstall()
                                error = apx.ActuatorException(e)
                                self.log_operation_end(error=error)
                                raise error

                        except Exception, e:
                                if self.__new_be == True:
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

                                if self.__new_be == True:
                                        be.restore_image()
                                else:
                                        be.restore_install_uninstall()
                                # Must be done after bootenv restore.
                                self.log_operation_end(error=exc_type)
                                raise

                        if self.__stage in \
                            [API_STAGE_DEFAULT, API_STAGE_EXECUTE]:
                                self._img.linked.do_recurse(API_STAGE_EXECUTE)

                        self.__finished_execution(be)
                        if raise_later:
                                raise raise_later

                finally:
                        self._img.cleanup_downloads()
                        if self._img.locked:
                                self._img.unlock()
                        self._activity_lock.release()

        def __finished_execution(self, be):
                if self._img.imageplan.state != ip.EXECUTED_OK:
                        if self.__new_be == True:
                                be.restore_image()
                        else:
                                be.restore_install_uninstall()

                        error = apx.ImageplanStateException(
                            self._img.imageplan.state)
                        # Must be done after bootenv restore.
                        self.log_operation_end(error=error)
                        raise error

                if self._img.imageplan.boot_archive_needed() or \
                    self.__new_be:
                        be.update_boot_archive()

                if self.__new_be == True:
                        be.activate_image(set_active=self.__be_activate)
                else:
                        be.activate_install_uninstall()
                self._img.cleanup_cached_content()
                # If the end of the operation wasn't already logged
                # by one of the previous operations, then log it as
                # ending now.
                if self._img.history.operation_name:
                        self.log_operation_end()
                self.__executed = True

        def set_plan_license_status(self, pfmri, plicense, accepted=None,
            displayed=None):
                """Sets the license status for the given package FMRI and
                license entry.

                'accepted' is an optional parameter that can be one of three
                values:
                        None    leaves accepted status unchanged
                        False   sets accepted status to False
                        True    sets accepted status to True

                'displayed' is an optional parameter that can be one of three
                values:
                        None    leaves displayed status unchanged
                        False   sets displayed status to False
                        True    sets displayed status to True"""

                self._acquire_activity_lock()
                try:
                        try:
                                self._disable_cancel()
                        except apx.CanceledException:
                                self._cancel_done()
                                raise

                        if not self._img.imageplan:
                                raise apx.PlanMissingException()

                        for pp in self._img.imageplan.pkg_plans:
                                if pp.destination_fmri == pfmri:
                                        pp.set_license_status(plicense,
                                            accepted=accepted,
                                            displayed=displayed)
                                        break
                finally:
                        self._activity_lock.release()

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

                self._acquire_activity_lock()
                try:
                        self._disable_cancel()
                        self._img.lock()
                        try:
                                self.__refresh(full_refresh=full_refresh,
                                    pubs=pubs, immediate=immediate)
                                return self._img
                        finally:
                                self._img.unlock()
                                self._img.cleanup_downloads()
                except apx.CanceledException:
                        self._cancel_done()
                        raise
                finally:
                        try:
                                if int(os.environ.get("PKG_DUMP_STATS", 0)) > 0:
                                        self._img.transport.stats.dump()
                        except ValueError:
                                # Don't generate stats if an invalid value
                                # is supplied.
                                pass
                        self._activity_lock.release()

        def __refresh(self, full_refresh=False, pubs=None, immediate=False):
                """Private refresh method; caller responsible for locking and
                cleanup."""

                self._img.refresh_publishers(full_refresh=full_refresh,
                    immediate=immediate, pubs=pubs,
                    progtrack=self.__progresstracker)

        def __licenses(self, pfmri, mfst, alt_pub=None):
                """Private function. Returns the license info from the
                manifest mfst."""
                license_lst = []
                for lic in mfst.gen_actions_by_type("license"):
                        license_lst.append(LicenseInfo(pfmri, lic,
                            img=self._img, alt_pub=alt_pub))
                return license_lst

        @_LockedCancelable()
        def get_pkg_categories(self, installed=False, pubs=misc.EmptyI,
            repos=None):
                """Returns an ordered list of tuples of the form (scheme,
                category) containing the names of all categories in use by
                the last version of each unique package in the catalog on a
                per-publisher basis.

                'installed' is an optional boolean value indicating whether
                only the categories used by currently installed packages
                should be returned.  If False, the categories used by the
                latest vesion of every known package will be returned
                instead.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                'repos' is a list of URI strings or RepositoryURI objects that
                represent the locations of package repositories to list packages
                for.
                """

                if installed:
                        excludes = misc.EmptyI
                else:
                        excludes = self._img.list_excludes()

                if repos:
                        ignored, ignored, known_cat, inst_cat = \
                            self.__get_alt_pkg_data(repos)
                        if installed:
                                pkg_cat = inst_cat
                        else:
                                pkg_cat = known_cat
                elif installed:
                        pkg_cat = self._img.get_catalog(
                            self._img.IMG_CATALOG_INSTALLED)
                else:
                        pkg_cat = self._img.get_catalog(
                            self._img.IMG_CATALOG_KNOWN)
                return sorted(pkg_cat.categories(excludes=excludes, pubs=pubs))

        def __map_installed_newest(self, brelease, pubs, known_cat=None):
                """Private function.  Maps incorporations and publisher
                relationships for installed packages and returns them
                as a tuple of (pub_ranks, inc_stems, inc_vers, inst_stems,
                ren_stems, ren_inst_stems).
                """

                img_cat = self._img.get_catalog(
                    self._img.IMG_CATALOG_INSTALLED)
                cat_info = frozenset([img_cat.DEPENDENCY])

                inst_stems = {}
                ren_inst_stems = {}
                ren_stems = {}

                inc_stems = {}
                inc_vers = {}

                pub_ranks = self._img.get_publisher_ranks()

                # The incorporation list should include all installed,
                # incorporated packages from all publishers.
                for t in img_cat.entry_actions(cat_info):
                        (pub, stem, ver), entry, actions = t

                        inst_stems[stem] = ver
                        pkgr = False
                        targets = set()
                        try:
                                for a in actions:
                                        if a.name == "set" and \
                                            a.attrs["name"] == "pkg.renamed":
                                                pkgr = True
                                                continue
                                        elif a.name != "depend":
                                                continue

                                        if a.attrs["type"] == "require":
                                                # Because the actions are not
                                                # returned in a guaranteed
                                                # order, the dependencies will
                                                # have to be recorded for
                                                # evaluation later.
                                                targets.add(a.attrs["fmri"])
                                        elif a.attrs["type"] == "incorporate":
                                                # Record incorporated packages.
                                                tgt = fmri.PkgFmri(
                                                    a.attrs["fmri"], brelease)
                                                tver = tgt.version
                                                over = inc_vers.get(
                                                    tgt.pkg_name, None)

                                                # In case this package has been
                                                # incorporated more than once,
                                                # use the newest version.
                                                if over is not None and \
                                                    over > tver:
                                                        continue
                                                inc_vers[tgt.pkg_name] = tver
                        except apx.InvalidPackageErrors:
                                # For mapping purposes, ignore unsupported
                                # (and invalid) actions.  This is necessary so
                                # that API consumers can discover new package
                                # data that may be needed to perform an upgrade
                                # so that the API can understand them.
                                pass

                        if pkgr:
                                for f in targets:
                                        tgt = fmri.PkgFmri(f, brelease)
                                        ren_stems[tgt.pkg_name] = stem
                                        ren_inst_stems.setdefault(stem,
                                            set())
                                        ren_inst_stems[stem].add(
                                            tgt.pkg_name)

                def check_stem(t, entry):
                        pub, stem, ver = t
                        if stem in inst_stems:
                                iver = inst_stems[stem]
                                if stem in ren_inst_stems or \
                                    ver == iver:
                                        # The package has been renamed
                                        # or the entry is for the same
                                        # version as that which is
                                        # installed, so doesn't need
                                        # to be checked.
                                        return False
                                # The package may have been renamed in
                                # a newer version, so must be checked.
                                return True
                        elif stem in inc_vers:
                                # Package is incorporated, but not
                                # installed, so should be checked.
                                return True

                        tgt = ren_stems.get(stem, None)
                        while tgt is not None:
                                # This seems counter-intuitive, but
                                # for performance and other reasons,
                                # this stem should only be checked
                                # for a rename if it is incorporated
                                # or installed using a previous name.
                                if tgt in inst_stems or \
                                    tgt in inc_vers:
                                        return True
                                tgt = ren_stems.get(tgt, None)

                        # Package should not be checked.
                        return False

                if not known_cat:
                        known_cat = self._img.get_catalog(
                            self._img.IMG_CATALOG_KNOWN)

                # Find terminal rename entry for all known packages not
                # rejected by check_stem().
                for t, entry, actions in known_cat.entry_actions(cat_info,
                    cb=check_stem, last=True):
                        pkgr = False
                        targets = set()
                        try:
                                for a in actions:
                                        if a.name == "set" and \
                                            a.attrs["name"] == "pkg.renamed":
                                                pkgr = True
                                                continue

                                        if a.name != "depend":
                                                continue

                                        if a.attrs["type"] != "require":
                                                continue

                                        # Because the actions are not
                                        # returned in a guaranteed
                                        # order, the dependencies will
                                        # have to be recorded for
                                        # evaluation later.
                                        targets.add(a.attrs["fmri"])
                        except apx.InvalidPackageErrors:
                                # For mapping purposes, ignore unsupported
                                # (and invalid) actions.  This is necessary so
                                # that API consumers can discover new package
                                # data that may be needed to perform an upgrade
                                # so that the API can understand them.
                                pass

                        if pkgr:
                                pub, stem, ver = t
                                for f in targets:
                                        tgt = fmri.PkgFmri(f, brelease)
                                        ren_stems[tgt.pkg_name] = stem

                # Determine highest ranked publisher for package stems
                # listed in installed incorporations.
                def pub_order(a, b):
                        return cmp(pub_ranks[a][0], pub_ranks[b][0])

                for p in sorted(pub_ranks, cmp=pub_order):
                        if pubs and p not in pubs:
                                continue
                        for stem in known_cat.names(pubs=[p]):
                                if stem in inc_vers:
                                        inc_stems.setdefault(stem, p)

                return (pub_ranks, inc_stems, inc_vers, inst_stems, ren_stems,
                    ren_inst_stems)

        def __get_temp_repo_pubs(self, repos):
                """Private helper function to retrieve publisher information
                from list of temporary repositories.  Caller is responsible
                for locking."""

                ret_pubs = []
                for repo_uri in repos:
                        if isinstance(repo_uri, basestring):
                                repo = publisher.RepositoryURI(repo_uri)
                        else:
                                # Already a RepositoryURI.
                                repo = repo_uri

                        pubs = None
                        try:
                                pubs = self._img.transport.get_publisherdata(
                                    repo, ccancel=self.__check_cancel)
                        except apx.UnsupportedRepositoryOperation:
                                raise apx.RepoPubConfigUnavailable(
                                    location=str(repo))

                        if not pubs:
                                # Empty repository configuration.
                                raise apx.RepoPubConfigUnavailable(
                                    location=str(repo))

                        for p in pubs:
                                psrepo = p.repository
                                if not psrepo:
                                        # Repository configuration info wasn't
                                        # provided, so assume origin is
                                        # repo_uri.
                                        p.repository = publisher.Repository(
                                            origins=[repo_uri])
                                elif not psrepo.origins:
                                        # Repository configuration was provided,
                                        # but without an origin.  Assume the
                                        # repo_uri is the origin.
                                        psrepo.add_origin(repo_uri)
                                elif repo not in psrepo.origins:
                                        # If the repo_uri used is not
                                        # in the list of sources, then
                                        # add it as the first origin.
                                        psrepo.origins.insert(0, repo)
                        ret_pubs.extend(pubs)

                return sorted(ret_pubs)

        def __get_alt_pkg_data(self, repos):
                """Private helper function to retrieve composite known and
                installed catalog and package repository map for temporary
                set of package repositories.  Returns (pkg_pub_map, alt_pubs,
                known_cat, inst_cat)."""

                repos = set(repos)
                eid = ",".join(sorted(map(str, repos)))
                try:
                        return self.__alt_sources[eid]
                except KeyError:
                        # Need to cache new set of alternate sources.
                        pass

                img_inst_cat = self._img.get_catalog(
                    self._img.IMG_CATALOG_INSTALLED)
                op_time = datetime.datetime.utcnow()
                pubs = self.__get_temp_repo_pubs(repos)
                progtrack = self.__progresstracker

                # Create temporary directories.
                tmpdir = tempfile.mkdtemp()

                pkg_repos = {}
                pkg_pub_map = {}
                try:
                        progtrack.refresh_start(len(pubs))
                        pub_cats = []
                        for pub in pubs:
                                # Assign a temporary meta root to each
                                # publisher.
                                meta_root = os.path.join(tmpdir, str(id(pub)))
                                misc.makedirs(meta_root)
                                pub.meta_root = meta_root
                                pub.transport = self._img.transport
                                repo = pub.repository
                                pkg_repos[id(repo)] = repo

                                # Retrieve each publisher's catalog.
                                progtrack.refresh_progress(pub.prefix)
                                pub.refresh()
                                pub_cats.append((
                                    pub.prefix,
                                    repo,
                                    pub.catalog
                                ))

                        progtrack.refresh_done()

                        # Determine upgradability.
                        newest = {}
                        for pfx, repo, cat in [(None, None, img_inst_cat)] + \
                            pub_cats:
                                if pfx:
                                        pkg_list = cat.fmris(last=True,
                                            pubs=[pfx])
                                else:
                                        pkg_list = cat.fmris(last=True)

                                for f in pkg_list:
                                        nver, snver = newest.get(f.pkg_name,
                                            (None, None))
                                        if f.version > nver:
                                                newest[f.pkg_name] = (f.version,
                                                    str(f.version))

                        # Build list of installed packages.
                        inst_stems = {}
                        for t, entry in img_inst_cat.tuple_entries():
                                states = entry["metadata"]["states"]
                                if self._img.PKG_STATE_INSTALLED not in states:
                                        continue
                                pub, stem, ver = t
                                inst_stems.setdefault(pub, {})
                                inst_stems[pub].setdefault(stem, {})
                                inst_stems[pub][stem][ver] = False

                        # Now create composite known and installed catalogs.
                        compicat = pkg.catalog.Catalog(batch_mode=True,
                            sign=False)
                        compkcat = pkg.catalog.Catalog(batch_mode=True,
                            sign=False)

                        sparts = (
                           (pfx, cat, repo, name, cat.get_part(name, must_exist=True))
                           for pfx, repo, cat in pub_cats
                           for name in cat.parts
                        )

                        excludes = self._img.list_excludes()
                        proc_stems = {}
                        for pfx, cat, repo, name, spart in sparts:
                                # 'spart' is the source part.
                                if spart is None:
                                        # Client hasn't retrieved this part.
                                        continue

                                # New known part.
                                nkpart = compkcat.get_part(name)
                                nipart = compicat.get_part(name)
                                base = name.startswith("catalog.base.")

                                # Avoid accessor overhead since these will be
                                # used for every entry.
                                cat_ver = cat.version
                                dp = cat.get_part("catalog.dependency.C",
                                    must_exist=True)

                                for t, sentry in spart.tuple_entries(pubs=[pfx]):
                                        pub, stem, ver = t

                                        pkg_pub_map.setdefault(pub, {})
                                        pkg_pub_map[pub].setdefault(stem, {})
                                        pkg_pub_map[pub][stem].setdefault(ver,
                                            set())
                                        pkg_pub_map[pub][stem][ver].add(
                                            id(repo))

                                        if pub in proc_stems and \
                                            stem in proc_stems[pub] and \
                                            ver in proc_stems[pub][stem]:
                                                if id(cat) != proc_stems[pub][stem][ver]:
                                                        # Already added from another
                                                        # catalog.
                                                        continue
                                        else:
                                                proc_stems.setdefault(pub, {})
                                                proc_stems[pub].setdefault(stem,
                                                    {})
                                                proc_stems[pub][stem][ver] = \
                                                    id(cat)

                                        installed = False
                                        if pub in inst_stems and \
                                            stem in inst_stems[pub] and \
                                            ver in inst_stems[pub][stem]:
                                                installed = True
                                                inst_stems[pub][stem][ver] = \
                                                    True

                                        # copy() is too slow here and catalog
                                        # entries are shallow so this should be
                                        # sufficient.
                                        entry = dict(sentry.iteritems())
                                        if not base:
                                                # Nothing else to do except add
                                                # the entry for non-base catalog
                                                # parts.
                                                nkpart.add(metadata=entry,
                                                    op_time=op_time, pub=pub,
                                                    stem=stem, ver=ver)
                                                if installed:
                                                        nipart.add(
                                                            metadata=entry,
                                                            op_time=op_time,
                                                            pub=pub, stem=stem,
                                                            ver=ver)
                                                continue

                                        # Only the base catalog part stores
                                        # package state information and/or
                                        # other metadata.
                                        mdata = entry["metadata"] = {}
                                        states = [self._img.PKG_STATE_KNOWN,
                                            self._img.PKG_STATE_ALT_SOURCE]
                                        if cat_ver == 0:
                                                states.append(
                                                    self._img.PKG_STATE_V0)
                                        else:
                                                # Assume V1 catalog source.
                                                states.append(
                                                    self._img.PKG_STATE_V1)

                                        if installed:
                                                states.append(
                                                    self._img.PKG_STATE_INSTALLED)

                                        nver, snver = newest.get(stem,
                                            (None, None))
                                        if snver is not None and ver != snver:
                                                states.append(
                                                    self._img.PKG_STATE_UPGRADABLE)

                                        # Determine if package is obsolete or
                                        # has been renamed and mark with
                                        # appropriate state.
                                        dpent = None
                                        if dp is not None:
                                                dpent = dp.get_entry(pub=pub,
                                                    stem=stem, ver=ver)
                                        if dpent is not None:
                                                for a in dpent["actions"]:
                                                        # Constructing action
                                                        # objects for every
                                                        # action would be a lot
                                                        # slower, so a simple
                                                        # string match is done
                                                        # first so that only
                                                        # interesting actions
                                                        # get constructed.
                                                        if not a.startswith("set"):
                                                                continue
                                                        if not ("pkg.obsolete" in a or \
                                                            "pkg.renamed" in a):
                                                                continue

                                                        try:
                                                                act = pkg.actions.fromstr(a)
                                                        except pkg.actions.ActionError:
                                                                # If the action can't be
                                                                # parsed or is not yet
                                                                # supported, continue.
                                                                continue

                                                        if act.attrs["value"].lower() != "true":
                                                                continue

                                                        if act.attrs["name"] == "pkg.obsolete":
                                                                states.append(
                                                                    self._img.PKG_STATE_OBSOLETE)
                                                        elif act.attrs["name"] == "pkg.renamed":
                                                                if not act.include_this(
                                                                    excludes):
                                                                        continue
                                                                states.append(
                                                                    self._img.PKG_STATE_RENAMED)

                                        mdata["states"] = states

                                        # Add base entries.
                                        nkpart.add(metadata=entry,
                                            op_time=op_time, pub=pub, stem=stem,
                                            ver=ver)
                                        if installed:
                                                nipart.add(metadata=entry,
                                                    op_time=op_time, pub=pub,
                                                    stem=stem, ver=ver)

                        pub_map = {}
                        for pub in pubs:
                                try:
                                        opub = pub_map[pub.prefix]
                                except KeyError:
                                        opub = publisher.Publisher(pub.prefix,
                                            catalog=compkcat)
                                        pub_map[pub.prefix] = opub

                        rid_map = {}
                        for pub in pkg_pub_map:
                                for stem in pkg_pub_map[pub]:
                                        for ver in pkg_pub_map[pub][stem]:
                                                rids = tuple(sorted(
                                                    pkg_pub_map[pub][stem][ver]))

                                                if not rids in rid_map:
                                                        # Create a publisher and
                                                        # repository for this
                                                        # unique set of origins.
                                                        origins = []
                                                        map(origins.extend, [
                                                           pkg_repos.get(rid).origins
                                                           for rid in rids
                                                        ])
                                                        nrepo = publisher.Repository(
                                                            origins=origins)
                                                        npub = \
                                                            copy.copy(pub_map[pub])
                                                        npub.repository = nrepo
                                                        rid_map[rids] = npub

                                                pkg_pub_map[pub][stem][ver] = \
                                                    rid_map[rids]

                        # Now consolidate all origins for each publisher under
                        # a single repository object for the caller.
                        for pub in pubs:
                                npub = pub_map[pub.prefix]
                                nrepo = npub.repository
                                if not nrepo:
                                        nrepo = publisher.Repository()
                                        npub.repository = nrepo
                                for o in pub.repository.origins:
                                        if not nrepo.has_origin(o):
                                                nrepo.add_origin(o)

                        for compcat in (compicat, compkcat):
                                compcat.batch_mode = False
                                compcat.finalize()
                                compcat.read_only = True

                        # Cache these for future callers.
                        self.__alt_sources[eid] = (pkg_pub_map,
                            sorted(pub_map.values()), compkcat, compicat)
                        return self.__alt_sources[eid]
                finally:
                        shutil.rmtree(tmpdir, ignore_errors=True)
                        self._img.cleanup_downloads()

        @_LockedGenerator()
        def get_pkg_list(self, pkg_list, cats=None, patterns=misc.EmptyI,
            pubs=misc.EmptyI, raise_unmatched=False, repos=None,
            return_fmris=False, variants=False):
                """A generator function that produces tuples of the form:

                    (
                        (
                            pub,    - (string) the publisher of the package
                            stem,   - (string) the name of the package
                            version - (string) the version of the package
                        ),
                        summary,    - (string) the package summary
                        categories, - (list) string tuples of (scheme, category)
                        states      - (list) PackageInfo states
                    )

                Results are always sorted by stem, publisher, and then in
                descending version order.

                'pkg_list' is one of the following constant values indicating
                what base set of package data should be used for results:

                        LIST_ALL
                                All known packages.

                        LIST_INSTALLED
                                Installed packages.

                        LIST_INSTALLED_NEWEST
                                Installed packages and the newest
                                versions of packages not installed.
                                Renamed packages that are listed in
                                an installed incorporation will be
                                excluded unless they are installed.

                        LIST_NEWEST
                                The newest versions of all known packages
                                that match the provided patterns and
                                other criteria.

                        LIST_UPGRADABLE
                                Packages that are installed and upgradable.

                'cats' is an optional list of package category tuples of the
                form (scheme, cat) to restrict the results to.  If a package
                is assigned to any of the given categories, it will be
                returned.  A value of [] will return packages not assigned
                to any package category.  A value of None indicates that no
                package category filtering should be applied.

                'patterns' is an optional list of FMRI wildcard strings to
                filter results by.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                'raise_unmatched' is an optional boolean value that indicates
                whether an InventoryException should be raised if any patterns
                (after applying all other filtering and returning all results)
                didn't match any packages.

                'repos' is a list of URI strings or RepositoryURI objects that
                represent the locations of package repositories to list packages
                for.

                'return_fmris' is an optional boolean value that indicates that
                an FMRI object should be returned in place of the (pub, stem,
                ver) tuple that is normally returned.

                'variants' is an optional boolean value that indicates that
                packages that are for arch or zone variants not applicable to
                this image should be returned.

                Please note that this function may invoke network operations
                to retrieve the requested package information."""

                return self.__get_pkg_list(pkg_list, cats=cats,
                    patterns=patterns, pubs=pubs,
                    raise_unmatched=raise_unmatched, repos=repos,
                    return_fmris=return_fmris, variants=variants)

        def __get_pkg_list(self, pkg_list, cats=None, inst_cat=None,
            known_cat=None, patterns=misc.EmptyI, pubs=misc.EmptyI,
            raise_unmatched=False, repos=None, return_fmris=False,
            variants=False):
                """This is the implementation of get_pkg_list.  The other
                function is a wrapper that uses locking.  The separation was
                necessary because of API functions that already perform locking
                but need to use get_pkg_list().  This is a generator
                function."""

                installed = inst_newest = newest = upgradable = False
                if pkg_list == self.LIST_INSTALLED:
                        installed = True
                elif pkg_list == self.LIST_INSTALLED_NEWEST:
                        inst_newest = True
                elif pkg_list == self.LIST_NEWEST:
                        newest = True
                elif pkg_list == self.LIST_UPGRADABLE:
                        upgradable = True

                brelease = self._img.attrs["Build-Release"]

                # Each pattern in patterns can be a partial or full FMRI, so
                # extract the individual components for use in filtering.
                illegals = []
                pat_tuples = {}
                pat_versioned = False
                latest_pats = set()
                seen = set()
                npatterns = set()
                for pat, error, pfmri, matcher in self.parse_fmri_patterns(
                    patterns):
                        if error:
                                illegals.append(error)
                                continue

                        # Duplicate patterns are ignored.
                        sfmri = str(pfmri)
                        if sfmri in seen:
                                # A different form of the same pattern
                                # was specified already; ignore this
                                # one (e.g. pkg:/network/ping,
                                # /network/ping).
                                continue

                        # Track used patterns.
                        seen.add(sfmri)
                        npatterns.add(pat)

                        if "@" in pat:
                                # Mark that a pattern contained version
                                # information.  This is used for a listing
                                # optimization later on.
                                pat_versioned = True
                        if getattr(pfmri.version, "match_latest", None):
                                latest_pats.add(pat)
                        pat_tuples[pat] = (pfmri.tuple(), matcher)

                patterns = npatterns
                del npatterns, seen

                if illegals:
                        raise apx.InventoryException(illegal=illegals)

                if repos:
                        ignored, ignored, known_cat, inst_cat = \
                            self.__get_alt_pkg_data(repos)

                # For LIST_INSTALLED_NEWEST, installed packages need to be
                # determined and incorporation and publisher relationships
                # mapped.
                if inst_newest:
                        pub_ranks, inc_stems, inc_vers, inst_stems, ren_stems, \
                            ren_inst_stems = self.__map_installed_newest(
                            brelease, pubs, known_cat=known_cat)
                else:
                        pub_ranks = inc_stems = inc_vers = inst_stems = \
                            ren_stems = ren_inst_stems = misc.EmptyDict

                if installed or upgradable:
                        if inst_cat:
                                pkg_cat = inst_cat
                        else:
                                pkg_cat = self._img.get_catalog(
                                    self._img.IMG_CATALOG_INSTALLED)

                        # Don't need to perform variant filtering if only
                        # listing installed packages.
                        variants = True
                elif known_cat:
                        pkg_cat = known_cat
                else:
                        pkg_cat = self._img.get_catalog(
                            self._img.IMG_CATALOG_KNOWN)

                cat_info = frozenset([pkg_cat.DEPENDENCY, pkg_cat.SUMMARY])

                # Keep track of when the newest version has been found for
                # each incorporated stem.
                slist = set()

                # Keep track of listed stems for all other packages on a
                # per-publisher basis.
                nlist = collections.defaultdict(int)

                def check_state(t, entry):
                        states = entry["metadata"]["states"]
                        pkgi = self._img.PKG_STATE_INSTALLED in states
                        pkgu = self._img.PKG_STATE_UPGRADABLE in states
                        pub, stem, ver = t

                        if upgradable:
                                # If package is marked upgradable, return it.
                                return pkgu
                        elif pkgi:
                                # Nothing more to do here.
                                return True
                        elif stem in inst_stems:
                                # Some other version of this package is
                                # installed, so this one should not be
                                # returned.
                                return False

                        # Attempt to determine if this package is installed
                        # under a different name or constrained under a
                        # different name.
                        tgt = ren_stems.get(stem, None)
                        while tgt is not None:
                                if tgt in inc_vers:
                                        # Package is incorporated under a
                                        # different name, so allow this
                                        # to fallthrough to the incoporation
                                        # evaluation.
                                        break
                                elif tgt in inst_stems:
                                        # Package is installed under a
                                        # different name, so skip it.
                                        return False
                                tgt = ren_stems.get(tgt, None)

                        # Attempt to find a suitable version to return.
                        if stem in inc_vers:
                                # For package stems that are incorporated, only
                                # return the newest successor version  based on
                                # publisher rank.
                                if stem in slist:
                                        # Newest version already returned.
                                        return False

                                if stem in inc_stems and \
                                    pub != inc_stems[stem]:
                                        # This entry is for a lower-ranked
                                        # publisher.
                                        return False

                                # XXX version should not require build release.
                                ever = pkg.version.Version(ver, brelease)

                                # If the entry's version is a successor to
                                # the incorporated version, then this is the
                                # 'newest' version of this package since
                                # entries are processed in descending version
                                # order.
                                iver = inc_vers[stem]
                                if ever.is_successor(iver,
                                    pkg.version.CONSTRAINT_AUTO):
                                        slist.add(stem)
                                        return True
                                return False

                        pkg_stem = "!".join((pub, stem))
                        if pkg_stem in nlist:
                                # A newer version has already been listed for
                                # this stem and publisher.
                                return False
                        return True

                filter_cb = None
                if inst_newest or upgradable:
                        # Filtering needs to be applied.
                        filter_cb = check_state

                excludes = self._img.list_excludes()
                img_variants = self._img.get_variants()

                matched_pats = set()
                pkg_matching_pats = None

                # Retrieve only the newest package versions for LIST_NEWEST if
                # none of the patterns have version information and variants are
                # included.  (This cuts down on the number of entries that have
                # to be filtered.)
                use_last = newest and not pat_versioned and variants

                for t, entry, actions in pkg_cat.entry_actions(cat_info,
                    cb=filter_cb, excludes=excludes, last=use_last,
                    ordered=True, pubs=pubs):
                        pub, stem, ver = t

                        omit_ver = False
                        omit_package = None

                        pkg_stem = "!".join((pub, stem))
                        if newest and pkg_stem in nlist:
                                # A newer version has already been listed, so
                                # any additional entries need to be marked for
                                # omission before continuing.
                                omit_package = True
                                omit_ver = True
                        else:
                                nlist[pkg_stem] += 1

                        if raise_unmatched:
                                pkg_matching_pats = set()
                        if not omit_package:
                                ever = None
                                for pat in patterns:
                                        (pat_pub, pat_stem, pat_ver), matcher = \
                                            pat_tuples[pat]

                                        if pat_pub is not None and \
                                            pub != pat_pub:
                                                # Publisher doesn't match.
                                                if omit_package is None:
                                                        omit_package = True
                                                continue

                                        if matcher == self.MATCH_EXACT:
                                                if pat_stem != stem:
                                                        # Stem doesn't match.
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        continue
                                        elif matcher == self.MATCH_FMRI:
                                                if not ("/" + stem).endswith(
                                                    "/" + pat_stem):
                                                        # Stem doesn't match.
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        continue
                                        elif matcher == self.MATCH_GLOB:
                                                if not fnmatch.fnmatchcase(stem,
                                                    pat_stem):
                                                        # Stem doesn't match.
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        continue

                                        if pat_ver is not None:
                                                if ever is None:
                                                        # Avoid constructing a
                                                        # version object more
                                                        # than once for each
                                                        # entry.
                                                        ever = pkg.version.Version(ver,
                                                            brelease)
                                                if not ever.is_successor(pat_ver,
                                                    pkg.version.CONSTRAINT_AUTO):
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        omit_ver = True
                                                        continue

                                        if pat in latest_pats and \
                                            nlist[pkg_stem] > 1:
                                                # Package allowed by pattern,
                                                # but isn't the "latest"
                                                # version.
                                                if omit_package is None:
                                                        omit_package = True
                                                omit_ver = True
                                                continue

                                        # If this entry matched at least one
                                        # pattern, then ensure it is returned.
                                        omit_package = False
                                        if not raise_unmatched:
                                                # It's faster to stop as soon
                                                # as a match is found.
                                                break

                                        # If caller has requested other match
                                        # cases be raised as an exception, then
                                        # all patterns must be tested for every
                                        # entry.  This is slower, so only done
                                        # if necessary.
                                        pkg_matching_pats.add(pat)

                        if omit_package:
                                # Package didn't match critera; skip it.
                                if (filter_cb is not None or (newest and
                                    pat_versioned)) and omit_ver and \
                                    nlist[pkg_stem] == 1:
                                        # If omitting because of version, and
                                        # no other versions have been returned
                                        # yet for this stem, then discard
                                        # tracking entry so that other
                                        # versions will be listed.
                                        del nlist[pkg_stem]
                                        slist.discard(stem)
                                continue

                        # Perform image arch and zone variant filtering so
                        # that only packages appropriate for this image are
                        # returned, but only do this for packages that are
                        # not installed.
                        pcats = []
                        pkgr = False
                        unsupported = False
                        summ = None
                        targets = set()

                        omit_var = False
                        states = entry["metadata"]["states"]
                        pkgi = self._img.PKG_STATE_INSTALLED in states
                        try:
                                for a in actions:
                                        if a.name == "depend" and \
                                            a.attrs["type"] == "require":
                                                targets.add(a.attrs["fmri"])
                                                continue
                                        if a.name != "set":
                                                continue

                                        atname = a.attrs["name"]
                                        atvalue = a.attrs["value"]
                                        if atname == "pkg.summary":
                                                summ = atvalue
                                                continue

                                        if atname == "description":
                                                if summ is None:
                                                        # Historical summary
                                                        # field.
                                                        summ = atvalue
                                                continue

                                        if atname == "info.classification":
                                                pcats.extend(
                                                    a.parse_category_info())

                                        if pkgi:
                                                # No filtering for installed
                                                # packages.
                                                continue

                                        # Rename filtering should only be
                                        # performed for incorporated packages
                                        # at this point.
                                        if atname == "pkg.renamed":
                                                if stem in inc_vers:
                                                        pkgr = True
                                                continue

                                        if variants or \
                                            not atname.startswith("variant."):
                                                # No variant filtering required.
                                                continue

                                        # For all variants explicitly set in the
                                        # image, elide packages that are not for
                                        # a matching variant value.
                                        is_list = type(atvalue) == list
                                        for vn, vv in img_variants.iteritems():
                                                if vn == atname and \
                                                    ((is_list and
                                                    vv not in atvalue) or \
                                                    (not is_list and
                                                    vv != atvalue)):
                                                        omit_package = True
                                                        omit_var = True
                                                        break
                        except apx.InvalidPackageErrors:
                                # Ignore errors for packages that have invalid
                                # or unsupported metadata.  This is necessary so
                                # that API consumers can discover new package
                                # data that may be needed to perform an upgrade
                                # so that the API can understand them.
                                states = set(states)
                                states.add(PackageInfo.UNSUPPORTED)
                                unsupported = True

                        if not pkgi and pkgr and stem in inc_vers:
                                # If the package is not installed, but this is
                                # the terminal version entry for the stem and
                                # it is an incorporated package, then omit the
                                # package if it has been installed or is
                                # incorporated using one of the new names.
                                for e in targets:
                                        tgt = e
                                        while tgt is not None:
                                                if tgt in ren_inst_stems or \
                                                    tgt in inc_vers:
                                                        omit_package = True
                                                        break
                                                tgt = ren_stems.get(tgt, None)

                        if omit_package:
                                # Package didn't match criteria; skip it.
                                if (filter_cb is not None or newest) and \
                                    omit_var and nlist[pkg_stem] == 1:
                                        # If omitting because of variant, and
                                        # no other versions have been returned
                                        # yet for this stem, then discard
                                        # tracking entry so that other
                                        # versions will be listed.
                                        del nlist[pkg_stem]
                                        slist.discard(stem)
                                continue

                        if cats is not None:
                                if not cats:
                                        if pcats:
                                                # Only want packages with no
                                                # categories.
                                                continue
                                elif not [sc for sc in cats if sc in pcats]:
                                        # Package doesn't match specified
                                        # category criteria.
                                        continue

                        # Return the requested package data.
                        if not unsupported:
                                # Prevent modification of state data.
                                states = frozenset(states)

                        if raise_unmatched:
                                # Only after all other filtering has been
                                # applied are the patterns that the package
                                # matched considered "matching".
                                matched_pats.update(pkg_matching_pats)

                        if return_fmris:
                                pfmri = fmri.PkgFmri("%s@%s" % (stem, ver),
                                    build_release=brelease, publisher=pub)
                                yield (pfmri, summ, pcats, states)
                        else:
                                yield (t, summ, pcats, states)

                if raise_unmatched:
                        # Caller has requested that non-matching patterns or
                        # patterns that match multiple packages cause an
                        # exception to be raised.
                        notfound = set(pat_tuples.keys()) - matched_pats
                        if raise_unmatched and notfound:
                                raise apx.InventoryException(notfound=notfound)

        @_LockedCancelable()
        def info(self, fmri_strings, local, info_needed, repos=None):
                """Gathers information about fmris.  fmri_strings is a list
                of fmri_names for which information is desired.  local
                determines whether to retrieve the information locally
                (if possible).  It returns a dictionary of lists.  The keys
                for the dictionary are the constants specified in the class
                definition.  The values are lists of PackageInfo objects or
                strings.

                'repos' is a list of URI strings or RepositoryURI objects that
                represent the locations of packages to return information for.
                """

                bad_opts = info_needed - PackageInfo.ALL_OPTIONS
                if bad_opts:
                        raise apx.UnrecognizedOptionsToInfo(bad_opts)

                self.log_operation_start("info")

                # Common logic for image and temp repos case.
                if local:
                        ilist = self.LIST_INSTALLED
                else:
                        # Verify validity of certificates before attempting
                        # network operations.
                        self.__cert_verify(log_op_end=[apx.CertificateError])
                        ilist = self.LIST_NEWEST

                # The pkg_pub_map is only populated when temp repos are
                # specified and maps packages to the repositories that
                # contain them for manifest retrieval.
                pkg_pub_map = None
                known_cat = None
                inst_cat = None
                if repos:
                        pkg_pub_map, ignored, known_cat, inst_cat = \
                            self.__get_alt_pkg_data(repos)
                        if local:
                                pkg_cat = inst_cat
                        else:
                                pkg_cat = known_cat
                elif local:
                        pkg_cat = self._img.get_catalog(
                            self._img.IMG_CATALOG_INSTALLED)
                        if not fmri_strings and pkg_cat.package_count == 0:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                raise apx.NoPackagesInstalledException()
                else:
                        pkg_cat = self._img.get_catalog(
                            self._img.IMG_CATALOG_KNOWN)

                excludes = self._img.list_excludes()

                # Set of options that can use catalog data.
                cat_opts = frozenset([PackageInfo.DESCRIPTION,
                    PackageInfo.DEPENDENCIES])

                # Set of options that require manifest retrieval.
                act_opts = PackageInfo.ACTION_OPTIONS - \
                    frozenset([PackageInfo.DEPENDENCIES])

                pis = []
                rval = {
                    self.INFO_FOUND: pis,
                    self.INFO_MISSING: misc.EmptyI,
                    self.INFO_ILLEGALS: misc.EmptyI,
                }

                try:
                        for pfmri, summary, cats, states in self.__get_pkg_list(
                            ilist, inst_cat=inst_cat, known_cat=known_cat,
                            patterns=fmri_strings, raise_unmatched=True,
                            return_fmris=True, variants=True):
                                release = build_release = branch = \
                                    packaging_date = None

                                pub, name, version = pfmri.tuple()
                                alt_pub = None
                                if pkg_pub_map:
                                        alt_pub = \
                                            pkg_pub_map[pub][name][str(version)]

                                if PackageInfo.IDENTITY in info_needed:
                                        release = version.release
                                        build_release = version.build_release
                                        branch = version.branch
                                        packaging_date = \
                                            version.get_timestamp().strftime(
                                            "%c")
                                else:
                                        pub = name = version = None

                                links = hardlinks = files = dirs = \
                                    size = licenses = cat_info = \
                                    description = None

                                if PackageInfo.CATEGORIES in info_needed:
                                        cat_info = [
                                            PackageCategory(scheme, cat)
                                            for scheme, cat in cats
                                        ]

                                ret_cat_data = cat_opts & info_needed
                                dependencies = None
                                unsupported = False
                                if ret_cat_data:
                                        try:
                                                ignored, description, ignored, \
                                                    dependencies = \
                                                    _get_pkg_cat_data(pkg_cat,
                                                        ret_cat_data,
                                                        excludes=excludes,
                                                        pfmri=pfmri)
                                        except apx.InvalidPackageErrors:
                                                # If the information can't be
                                                # retrieved because the manifest
                                                # can't be parsed, mark it and
                                                # continue.
                                                unsupported = True

                                if dependencies is None:
                                        dependencies = misc.EmptyI

                                mfst = None
                                if not unsupported and \
                                    (frozenset([PackageInfo.SIZE,
                                    PackageInfo.LICENSES]) | act_opts) & \
                                    info_needed:
                                        try:
                                                mfst = self._img.get_manifest(
                                                    pfmri, alt_pub=alt_pub)
                                        except apx.InvalidPackageErrors:
                                                # If the information can't be
                                                # retrieved because the manifest
                                                # can't be parsed, mark it and
                                                # continue.
                                                unsupported = True

                                if mfst is not None:
                                        if PackageInfo.LICENSES in info_needed:
                                                licenses = self.__licenses(pfmri,
                                                    mfst, alt_pub=alt_pub)

                                        if PackageInfo.SIZE in info_needed:
                                                size = mfst.get_size(
                                                    excludes=excludes)

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
                                elif PackageInfo.SIZE in info_needed:
                                        size = 0

                                # Trim response set.
                                if PackageInfo.STATE in info_needed:
                                        if unsupported is True and \
                                            PackageInfo.UNSUPPORTED not in states:
                                                # Mark package as
                                                # unsupported so that
                                                # caller can decide
                                                # what to do.
                                                states = set(states)
                                                states.add(
                                                    PackageInfo.UNSUPPORTED)
                                else:
                                        states = misc.EmptyI

                                if PackageInfo.CATEGORIES not in info_needed:
                                        cats = None
                                if PackageInfo.SUMMARY in info_needed:
                                        if summary is None:
                                                summary = ""
                                else:
                                        summary = None

                                pis.append(PackageInfo(pkg_stem=name,
                                    summary=summary, category_info_list=cat_info,
                                    states=states, publisher=pub, version=release,
                                    build_release=build_release, branch=branch,
                                    packaging_date=packaging_date, size=size,
                                    pfmri=str(pfmri), licenses=licenses,
                                    links=links, hardlinks=hardlinks, files=files,
                                    dirs=dirs, dependencies=dependencies,
                                    description=description))
                except apx.InventoryException, e:
                        if e.illegal:
                                self.log_operation_end(
                                    result=history.RESULT_FAILED_BAD_REQUEST)
                        rval[self.INFO_MISSING] = e.notfound
                        rval[self.INFO_ILLEGALS] = e.illegal
                else:
                        if pis:
                                self.log_operation_end()
                        else:
                                self.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                return rval

        def can_be_canceled(self):
                """Returns true if the API is in a cancelable state."""
                return self.__can_be_canceled

        def _disable_cancel(self):
                """Sets_can_be_canceled to False in a way that prevents missed
                wakeups.  This may raise CanceledException, if a
                cancellation is pending."""

                self.__cancel_lock.acquire()
                if self.__canceling:
                        self.__cancel_lock.release()
                        self._img.transport.reset()
                        raise apx.CanceledException()
                else:
                        self.__set_can_be_canceled(False)
                self.__cancel_lock.release()

        def _enable_cancel(self):
                """Sets can_be_canceled to True while grabbing the cancel
                locks.  The caller must still hold the activity lock while
                calling this function."""

                self.__cancel_lock.acquire()
                self.__set_can_be_canceled(True)
                self.__cancel_lock.release()

        def __set_can_be_canceled(self, status):
                """Private method. Handles the details of changing the
                cancelable state."""
                assert self.__cancel_lock._is_owned()

                # If caller requests a change to current state there is
                # nothing to do.
                if self.__can_be_canceled == status:
                        return

                if status == True:
                        # Callers must hold activity lock for operations
                        # that they will make cancelable.
                        assert self._activity_lock._is_owned()
                        # In any situation where the caller holds the activity
                        # lock and wants to set cancelable to true, a cancel
                        # should not already be in progress.  This is because
                        # it should not be possible to invoke cancel until
                        # this routine has finished.  Assert that we're not
                        # canceling.
                        assert not self.__canceling

                self.__can_be_canceled = status
                if self.__cancel_state_callable:
                        self.__cancel_state_callable(self.__can_be_canceled)

        def reset(self):
                """Resets the API back the the initial state. Note:
                this does not necessarily return the disk to its initial state
                since the indexes or download cache may have been changed by
                the prepare method."""
                self._acquire_activity_lock()
                self.__reset_unlock()
                self._activity_lock.release()

        def __reset_unlock(self):
                """Private method. Provides a way to reset without taking the
                activity lock. Should only be called by a thread which already
                holds the activity lock."""

                assert self._activity_lock._is_owned()

                # This needs to be done first so that find_root can use it.
                self.__progresstracker.reset()

                # Ensure alternate sources are always cleared in an
                # exception scenario.
                self.__set_img_alt_sources(None)
                self.__alt_sources = {}

                self._img.cleanup_downloads()
                self._img.transport.shutdown()
                # Recreate the image object using the path the api
                # object was created with instead of the current path.
                self._img = image.Image(self._img_path,
                    progtrack=self.__progresstracker,
                    user_provided_dir=True,
                    cmdpath=self.cmdpath,
                    runid=self.__runid)
                self._img.blocking_locks = self.__blocking_locks

                lin = None
                if self._img.linked.ischild():
                        lin = self._img.linked.child_name
                self.__progresstracker.set_linked_name(lin)

                self.__plan_desc = None
                self.__planned_children = False
                self.__plan_type = None
                self.__prepared = False
                self.__executed = False
                self.__be_name = None

                self._cancel_cleanup_exception()

        def __check_cancel(self):
                """Private method. Provides a callback method for internal
                code to use to determine whether the current action has been
                canceled."""
                return self.__canceling

        def _cancel_cleanup_exception(self):
                """A private method that is called from exception handlers.
                This is not needed if the method calls reset unlock,
                which will call this method too.  This catches the case
                where a caller might have called cancel and gone to sleep,
                but the requested operation failed with an exception before
                it could raise a CanceledException."""

                self.__cancel_lock.acquire()
                self.__set_can_be_canceled(False)
                self.__canceling = False
                # Wake up any threads that are waiting on this aborted
                # operation.
                self.__cancel_cv.notify_all()
                self.__cancel_lock.release()

        def _cancel_done(self):
                """A private method that wakes any threads that have been
                sleeping, waiting for a cancellation to finish."""

                self.__cancel_lock.acquire()
                if self.__canceling:
                        self.__canceling = False
                        self.__cancel_cv.notify_all()
                self.__cancel_lock.release()

        def cancel(self):
                """Used for asynchronous cancelation. It returns the API
                to the state it was in prior to the current method being
                invoked.  Canceling during a plan phase returns the API to
                its initial state. Canceling during prepare puts the API
                into the state it was in just after planning had completed.
                Plan execution cannot be canceled. A call to this method blocks
                until the cancellation has happened. Note: this does not
                necessarily return the disk to its initial state since the
                indexes or download cache may have been changed by the
                prepare method."""

                self.__cancel_lock.acquire()

                if not self.__can_be_canceled:
                        self.__cancel_lock.release()
                        return False

                self.__set_can_be_canceled(False)
                self.__canceling = True
                # Wait until the cancelled operation wakes us up.
                self.__cancel_cv.wait()
                self.__cancel_lock.release()
                return True

        def __set_history_PlanCreationException(self, e):
                if e.unmatched_fmris or e.multiple_matches or \
                    e.missing_matches or e.illegal:
                        self.log_operation_end(error=e,
                            result=history.RESULT_FAILED_BAD_REQUEST)
                else:
                        self.log_operation_end(error=e)

        @_LockedGenerator()
        def local_search(self, query_lst):
                """local_search takes a list of Query objects and performs
                each query against the installed packages of the image."""

                l = query_p.QueryLexer()
                l.build()
                qp = query_p.QueryParser(l)
                ssu = None
                for i, q in enumerate(query_lst):
                        try:
                                query = qp.parse(q.text)
                                query_rr = qp.parse(q.text)
                                if query_rr.remove_root(self._img.root):
                                        query.add_or(query_rr)
                                if q.return_type == \
                                    query_p.Query.RETURN_PACKAGES:
                                        query.propagate_pkg_return()
                        except query_p.BooleanQueryException, e:
                                raise apx.BooleanQueryException(e)
                        except query_p.ParseError, e:
                                raise apx.ParseError(e)
                        self._img.update_index_dir()
                        assert self._img.index_dir
                        try:
                                query.set_info(num_to_return=q.num_to_return,
                                    start_point=q.start_point,
                                    index_dir=self._img.index_dir,
                                    get_manifest_path=\
                                        self._img.get_manifest_path,
                                    gen_installed_pkg_names=\
                                        self._img.gen_installed_pkg_names,
                                    case_sensitive=q.case_sensitive)
                                res = query.search(
                                    self._img.gen_installed_pkgs,
                                    self._img.get_manifest_path,
                                    self._img.list_excludes())
                        except search_errors.InconsistentIndexException, e:
                                raise apx.InconsistentIndexException(e)
                        # i is being inserted to track which query the results
                        # are for.  None is being inserted since there is no
                        # publisher being searched against.
                        try:
                                for r in res:
                                        yield i, None, r
                        except apx.SlowSearchUsed, e:
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
                        raise apx.ServerReturnError(line)
                try:
                        return_type = int(fields[1])
                        query_num = int(fields[0])
                except ValueError:
                        raise apx.ServerReturnError(line)
                if return_type == Query.RETURN_ACTIONS:
                        subfields = fields[2].split(None, 2)
                        pfmri = fmri.PkgFmri(subfields[0])
                        return pfmri, (query_num, pub, (v, return_type,
                            (pfmri, urllib.unquote(subfields[1]),
                            subfields[2])))
                elif return_type == Query.RETURN_PACKAGES:
                        pfmri = fmri.PkgFmri(fields[2])
                        return pfmri, (query_num, pub, (v, return_type, pfmri))
                else:
                        raise apx.ServerReturnError(line)

        @_LockedGenerator()
        def remote_search(self, query_str_and_args_lst, servers=None,
            prune_versions=True):
                """This function takes a list of Query objects, and optionally
                a list of servers to search against.  It performs each query
                against each server and yields the results in turn.  If no
                servers are provided, the search is conducted against all
                active servers known by the image.

                The servers argument is a list of servers in two possible
                forms: the old deprecated form of a publisher, in a
                dictionary, or a Publisher object.

                A call to this function returns a generator that holds
                API locks.  Callers must either iterate through all of the
                results, or call close() on the resulting object.  Otherwise
                it is possible to get deadlocks or NRLock reentrance
                exceptions."""

                failed = []
                invalid = []
                unsupported = []

                if not servers:
                        servers = self._img.gen_publishers()

                new_qs = []
                l = query_p.QueryLexer()
                l.build()
                qp = query_p.QueryParser(l)
                for q in query_str_and_args_lst:
                        try:
                                query = qp.parse(q.text)
                                query_rr = qp.parse(q.text)
                                if query_rr.remove_root(self._img.root):
                                        query.add_or(query_rr)
                                if q.return_type == \
                                    query_p.Query.RETURN_PACKAGES:
                                        query.propagate_pkg_return()
                                new_qs.append(query_p.Query(str(query),
                                    q.case_sensitive, q.return_type,
                                    q.num_to_return, q.start_point))
                        except query_p.BooleanQueryException, e:
                                raise apx.BooleanQueryException(e)
                        except query_p.ParseError, e:
                                raise apx.ParseError(e)

                query_str_and_args_lst = new_qs

                incorp_info, inst_stems = self.get_incorp_info()

                slist = []
                for entry in servers:
                        descriptive_name = None
                        if isinstance(entry, dict):
                                origin = entry["origin"]
                                try:
                                        pub = self._img.get_publisher(
                                            origin=origin)
                                except apx.UnknownPublisher:
                                        pub = publisher.RepositoryURI(origin)
                                        descriptive_name = origin
                                slist.append((pub, None, descriptive_name))
                                continue

                        # Must be a publisher object.
                        osets = entry.get_origin_sets()
                        if not osets:
                                unsupported.append((entry.prefix,
                                    apx.NoPublisherRepositories(
                                    entry.prefix)))
                                continue
                        for repo in osets:
                                slist.append((entry, repo, entry.prefix))

                for pub, alt_repo, descriptive_name in slist:
                        if self.__canceling:
                                raise apx.CanceledException()

                        try:
                                res = self._img.transport.do_search(pub,
                                    query_str_and_args_lst,
                                    ccancel=self.__check_cancel,
                                    alt_repo=alt_repo)
                        except apx.CanceledException:
                                raise
                        except apx.NegativeSearchResult:
                                continue
                        except apx.TransportError, e:
                                failed.append((descriptive_name, e))
                                continue
                        except apx.UnsupportedSearchError, e:
                                unsupported.append((descriptive_name, e))
                                continue
                        except apx.MalformedSearchRequest, e:
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
                                        pfmri, ret = self.__parse_v_1(line, pub,
                                            1)
                                        pstem = pfmri.pkg_name
                                        pver = pfmri.version
                                        # Skip this package if a newer version
                                        # is already installed and version
                                        # pruning is enabled.
                                        if prune_versions and \
                                            pstem in inst_stems and \
                                            pver < inst_stems[pstem]:
                                                continue
                                        # Return this result if version pruning
                                        # is disabled, the package is not
                                        # incorporated, or the version of the
                                        # package matches the incorporation.
                                        if not prune_versions or \
                                            pstem not in incorp_info or \
                                            pfmri.version.is_successor(
                                                incorp_info[pstem],
                                                pkg.version.CONSTRAINT_AUTO):
                                                yield ret

                        except apx.CanceledException:
                                raise
                        except apx.TransportError, e:
                                failed.append((descriptive_name, e))
                                continue

                if failed or invalid or unsupported:
                        raise apx.ProblematicSearchServers(failed,
                            invalid, unsupported)

        def get_incorp_info(self):
                """This function returns a mapping of package stems to the
                version at which they are incorporated, if they are
                incorporated, and the version at which they are installed, if
                they are installed."""

                # This maps fmris to the version at which they're incorporated.
                inc_vers = {}
                inst_stems = {}
                brelease = self._img.attrs["Build-Release"]

                img_cat = self._img.get_catalog(
                    self._img.IMG_CATALOG_INSTALLED)
                cat_info = frozenset([img_cat.DEPENDENCY])

                # The incorporation list should include all installed,
                # incorporated packages from all publishers.
                for pfmri, actions in img_cat.actions(cat_info):
                        inst_stems[pfmri.pkg_name] = pfmri.version
                        for a in actions:
                                if a.name != "depend" or \
                                    a.attrs["type"] != "incorporate":
                                        continue
                                # Record incorporated packages.
                                tgt = fmri.PkgFmri(
                                    a.attrs["fmri"], brelease)
                                tver = tgt.version
                                over = inc_vers.get(
                                    tgt.pkg_name, None)

                                # In case this package has been
                                # incorporated more than once,
                                # use the newest version.
                                if over > tver:
                                        continue
                                inc_vers[tgt.pkg_name] = tver
                return inc_vers, inst_stems

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
                                query = qp.parse(q.text)
                        except query_p.BooleanQueryException, e:
                                return apx.BooleanQueryException(e)
                        except query_p.ParseError, e:
                                return apx.ParseError(e)

                return None

        def rebuild_search_index(self):
                """Rebuilds the search indexes.  Removes all
                existing indexes and replaces them from scratch rather than
                performing the incremental update which is usually used.
                This is useful for times when the index for the client has
                been corrupted."""
                self._img.update_index_dir()
                self.log_operation_start("rebuild-index")
                if not os.path.isdir(self._img.index_dir):
                        self._img.mkdirs()
                try:
                        ind = indexer.Indexer(self._img, self._img.get_manifest,
                            self._img.get_manifest_path,
                            self.__progresstracker, self._img.list_excludes())
                        ind.rebuild_index_from_scratch(
                            self._img.gen_installed_pkgs())
                except search_errors.ProblematicPermissionsIndexException, e:
                        error = apx.ProblematicPermissionsIndexException(e)
                        self.log_operation_end(error=error)
                        raise error
                else:
                        self.log_operation_end()

        def get_manifest(self, pfmri, all_variants=True, repos=None):
                """Returns the Manifest object for the given package FMRI.

                'all_variants' is an optional boolean value indicating whther
                the manifest should include metadata for all variants.

                'repos' is a list of URI strings or RepositoryURI objects that
                represent the locations of additional sources of package data to
                use during the planned operation.
                """

                alt_pub = None
                if repos:
                        pkg_pub_map, ignored, known_cat, inst_cat = \
                            self.__get_alt_pkg_data(repos)
                        alt_pub = pkg_pub_map.get(pfmri.publisher, {}).get(
                            pfmri.pkg_name, {}).get(str(pfmri.version), None)
                return self._img.get_manifest(pfmri, all_variants=all_variants,
                    alt_pub=alt_pub)

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

        def add_publisher(self, pub, refresh_allowed=True,
            approved_cas=misc.EmptyI, revoked_cas=misc.EmptyI,
            search_after=None, search_before=None, search_first=None,
            unset_cas=misc.EmptyI):
                """Add the provided publisher object to the image
                configuration."""
                try:
                        self._img.add_publisher(pub,
                            refresh_allowed=refresh_allowed,
                            progtrack=self.__progresstracker,
                            approved_cas=approved_cas, revoked_cas=revoked_cas,
                            search_after=search_after,
                            search_before=search_before,
                            search_first=search_first,
                            unset_cas=unset_cas)
                finally:
                        self._img.cleanup_downloads()

        def get_highest_ranked_publisher(self):
                """Returns the highest ranked publisher object for the image."""
                return self._img.get_highest_ranked_publisher()

        def get_publisher(self, prefix=None, alias=None, duplicate=False):
                """Retrieves a publisher object matching the provided prefix
                (name) or alias.

                'duplicate' is an optional boolean value indicating whether
                a copy of the publisher object should be returned instead
                of the original.
                """
                pub = self._img.get_publisher(prefix=prefix, alias=alias)
                if duplicate:
                        # Never return the original so that changes to the
                        # retrieved object are not reflected until
                        # update_publisher is called.
                        return copy.copy(pub)
                return pub

        @_LockedCancelable()
        def get_publisherdata(self, pub=None, repo=None):
                """Attempts to retrieve publisher configuration information from
                the specified publisher's repository or the provided repository.
                If successful, it will either return an empty list (in the case
                that the repository supports the operation, but doesn't offer
                configuration information) or a list of Publisher objects.
                If this operation is not supported by the publisher or the
                specified repository, an UnsupportedRepositoryOperation
                exception will be raised.

                'pub' is an optional Publisher object.

                'repo' is an optional RepositoryURI object.

                Either 'pub' or 'repo' must be provided."""

                assert (pub or repo) and not (pub and repo)

                # Transport accepts either type of object, but a distinction is
                # made in the client API for clarity.
                pub = max(pub, repo)

                return self._img.transport.get_publisherdata(pub,
                    ccancel=self.__check_cancel)

        def get_publishers(self, duplicate=False):
                """Returns a list of the publisher objects for the current
                image.

                'duplicate' is an optional boolean value indicating whether
                copies of the publisher objects should be returned instead
                of the originals.
                """

                res = self._img.get_sorted_publishers()
                if duplicate:
                        return [copy.copy(p) for p in res]
                return res

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
                self._acquire_activity_lock()
                try:
                        self._enable_cancel()
                        try:
                                dt = pub.catalog.last_modified
                        except:
                                self.__reset_unlock()
                                raise
                        try:
                                self._disable_cancel()
                        except apx.CanceledException:
                                self._cancel_done()
                                raise
                finally:
                        self._activity_lock.release()
                return dt

        def has_publisher(self, prefix=None, alias=None):
                """Returns a boolean value indicating whether a publisher using
                the given prefix or alias exists."""
                return self._img.has_publisher(prefix=prefix, alias=alias)

        def remove_publisher(self, prefix=None, alias=None):
                """Removes a publisher object matching the provided prefix
                (name) or alias."""
                self._img.remove_publisher(prefix=prefix, alias=alias,
                    progtrack=self.__progresstracker)

        def update_publisher(self, pub, refresh_allowed=True, search_after=None,
            search_before=None, search_first=None):
                """Replaces an existing publisher object with the provided one
                using the _source_object_id identifier set during copy.

                'refresh_allowed' is an optional boolean value indicating
                whether a refresh of publisher metadata (such as its catalog)
                should be performed if transport information is changed for a
                repository, mirror, or origin.  If False, no attempt will be
                made to retrieve publisher metadata."""

                self._acquire_activity_lock()
                try:
                        self._disable_cancel()
                        with self._img.locked_op("update-publisher"):
                                return self.__update_publisher(pub,
                                    refresh_allowed=refresh_allowed,
                                    search_after=search_after,
                                    search_before=search_before,
                                    search_first=search_first)
                except apx.CanceledException, e:
                        self._cancel_done()
                        raise
                finally:
                        self._img.cleanup_downloads()
                        self._activity_lock.release()

        def __update_publisher(self, pub, refresh_allowed=True,
            search_after=None, search_before=None, search_first=None):
                """Private publisher update method; caller responsible for
                locking."""

                assert (not search_after and not search_before) or \
                    (not search_after and not search_first) or \
                    (not search_before and not search_first)

                def origins_changed(oldr, newr):
                        old_origins = set([
                            (o.uri, o.ssl_cert,
                                o.ssl_key)
                            for o in oldr.origins
                        ])
                        new_origins = set([
                            (o.uri, o.ssl_cert,
                                o.ssl_key)
                            for o in newr.origins
                        ])
                        return new_origins - old_origins

                def need_refresh(oldo, newo):
                        if newo.disabled:
                                # The publisher is disabled, so no refresh
                                # should be performed.
                                return False

                        if oldo.disabled and not newo.disabled:
                                # The publisher has been re-enabled, so
                                # retrieve the catalog.
                                return True

                        oldr = oldo.repository
                        newr = newo.repository
                        if newr._source_object_id != id(oldr):
                                # Selected repository has changed.
                                return True
                        return len(origins_changed(oldr, newr)) != 0

                refresh_catalog = False
                disable = False
                orig_pub = None

                # Configuration must be manipulated directly.
                publishers = self._img.cfg.publishers

                # First, attempt to match the updated publisher object to an
                # existing one using the object id that was stored during
                # copy().
                for key, old in publishers.iteritems():
                        if pub._source_object_id == id(old):
                                # Store the new publisher's id and the old
                                # publisher object so it can be restored if the
                                # update operation fails.
                                orig_pub = (id(pub), old)
                                break

                if not orig_pub:
                        # If a matching publisher couldn't be found and
                        # replaced, something is wrong (client api usage
                        # error).
                        raise apx.UnknownPublisher(pub)

                # Next, be certain that the publisher's prefix and alias
                # are not already in use by another publisher.
                for key, old in publishers.iteritems():
                        if pub._source_object_id == id(old):
                                # Don't check the object we're replacing.
                                continue

                        if pub.prefix == old.prefix or \
                            pub.prefix == old.alias or \
                            pub.alias and (pub.alias == old.alias or
                            pub.alias == old.prefix):
                                raise apx.DuplicatePublisher(pub)

                # Next, determine what needs updating and add the updated
                # publisher.
                for key, old in publishers.iteritems():
                        if pub._source_object_id == id(old):
                                old = orig_pub[-1]
                                if need_refresh(old, pub):
                                        refresh_catalog = True
                                if not old.disabled and pub.disabled:
                                        disable = True

                                # Now remove the old publisher object using the
                                # iterator key if the prefix has changed.
                                if key != pub.prefix:
                                        del publishers[key]

                                # Prepare the new publisher object.
                                pub.meta_root = \
                                    self._img._get_publisher_meta_root(
                                    pub.prefix)
                                pub.transport = self._img.transport

                                # Finally, add the new publisher object.
                                publishers[pub.prefix] = pub
                                break

                def cleanup():
                        new_id, old_pub = orig_pub
                        for new_pfx, new_pub in publishers.iteritems():
                                if id(new_pub) == new_id:
                                        publishers[old_pub.prefix] = old_pub
                                        break

                repo = pub.repository

                validate = origins_changed(orig_pub[-1].repository,
                    pub.repository)

                try:
                        if disable or (not repo.origins and
                            orig_pub[-1].repository.origins):
                                # Remove the publisher's metadata (such as
                                # catalogs, etc.).  This only needs to be done
                                # in the event that a publisher is disabled or
                                # has transitioned from having origins to not
                                # having any at all; in any other case (the
                                # origins changing, etc.), refresh() will do the
                                # right thing.
                                self._img.remove_publisher_metadata(pub)
                        elif not pub.disabled and not refresh_catalog:
                                refresh_catalog = pub.needs_refresh

                        if refresh_catalog and refresh_allowed:
                                # One of the publisher's repository origins may
                                # have changed, so the publisher needs to be
                                # revalidated.

                                if validate:
                                        self._img.transport.valid_publisher_test(
                                            pub)

                                # Validate all new origins against publisher
                                # configuration.
                                for uri, ssl_cert, ssl_key in validate:
                                        repo = publisher.RepositoryURI(uri,
                                            ssl_cert=ssl_cert, ssl_key=ssl_key)
                                        pub.validate_config(repo)

                                self.__refresh(pubs=[pub], immediate=True)
                        elif refresh_catalog:
                                # Something has changed (such as a repository
                                # origin) for the publisher, so a refresh should
                                # occur, but isn't currently allowed.  As such,
                                # clear the last_refreshed time so that the next
                                # time the client checks to see if a refresh is
                                # needed and is allowed, one will be performed.
                                pub.last_refreshed = None
                except Exception, e:
                        # If any of the above fails, the original publisher
                        # information needs to be restored so that state is
                        # consistent.
                        cleanup()
                        raise
                except:
                        # If any of the above fails, the original publisher
                        # information needs to be restored so that state is
                        # consistent.
                        cleanup()
                        raise

                if search_first:
                        self._img.set_highest_ranked_publisher(
                            prefix=pub.prefix)
                elif search_before:
                        self._img.pub_search_before(pub.prefix, search_before)
                elif search_after:
                        self._img.pub_search_after(pub.prefix, search_after)

                # Successful; so save configuration.
                self._img.save_config()

        def log_operation_end(self, error=None, result=None):
                """Marks the end of an operation to be recorded in image
                history.

                'result' should be a pkg.client.history constant value
                representing the outcome of an operation.  If not provided,
                and 'error' is provided, the final result of the operation will
                be based on the class of 'error' and 'error' will be recorded
                for the current operation.  If 'result' and 'error' is not
                provided, success is assumed."""
                self._img.history.log_operation_end(error=error, result=result)

        def log_operation_error(self, error):
                """Adds an error to the list of errors to be recorded in image
                history for the current opreation."""
                self._img.history.log_operation_error(error)

        def log_operation_start(self, name):
                """Marks the start of an operation to be recorded in image
                history."""
                be_name, be_uuid = bootenv.BootEnv.get_be_name(self._img.root)
                self._img.history.log_operation_start(name,
                    be_name=be_name, be_uuid=be_uuid)

        def parse_liname(self, name, unknown_ok=False):
                """Parse a linked image name string and return a
                LinkedImageName object.  If "unknown_ok" is true then
                liname must correspond to an existing linked image.  If
                "unknown_ok" is false and liname doesn't correspond to
                an existing linked image then liname must be a
                syntactically valid and fully qualified linked image
                name."""

                return self._img.linked.parse_name(name, unknown_ok=unknown_ok)

        def parse_p5i(self, data=None, fileobj=None, location=None):
                """Reads the pkg(5) publisher JSON formatted data at 'location'
                or from the provided file-like object 'fileobj' and returns a
                list of tuples of the format (publisher object, pkg_names).
                pkg_names is a list of strings representing package names or
                FMRIs.  If any pkg_names not specific to a publisher were
                provided, the last tuple returned will be of the format (None,
                pkg_names).

                'data' is an optional string containing the p5i data.

                'fileobj' is an optional file-like object that must support a
                'read' method for retrieving data.

                'location' is an optional string value that should either start
                with a leading slash and be pathname of a file or a URI string.
                If it is a URI string, supported protocol schemes are 'file',
                'ftp', 'http', and 'https'.

                'data' or 'fileobj' or 'location' must be provided."""

                return p5i.parse(data=data, fileobj=fileobj, location=location)

        def parse_fmri_patterns(self, patterns):
                """A generator function that yields a list of tuples of the form
                (pattern, error, fmri, matcher) based on the provided patterns,
                where 'error' is any exception encountered while parsing the
                pattern, 'fmri' is the resulting FMRI object, and 'matcher' is
                one of the following constant values:

                        MATCH_EXACT
                                Indicates that the name portion of the pattern
                                must match exactly and the version (if provided)
                                must be considered a successor or equal to the
                                target FMRI.

                        MATCH_FMRI
                                Indicates that the name portion of the pattern
                                must be a proper subset and the version (if
                                provided) must be considered a successor or
                                equal to the target FMRI.

                        MATCH_GLOB
                                Indicates that the name portion of the pattern
                                uses fnmatch rules for pattern matching (shell-
                                style wildcards) and that the version can either
                                match exactly, match partially, or contain
                                wildcards.
                """

                brelease = self._img.attrs["Build-Release"]
                for pat in patterns:
                        error = None
                        matcher = None
                        npat = None
                        try:
                                parts = pat.split("@", 1)
                                pat_stem = parts[0]
                                pat_ver = None
                                if len(parts) > 1:
                                        pat_ver = parts[1]

                                if "*" in pat_stem or "?" in pat_stem:
                                        matcher = self.MATCH_GLOB
                                elif pat_stem.startswith("pkg:/") or \
                                    pat_stem.startswith("/"):
                                        matcher = self.MATCH_EXACT
                                else:
                                        matcher = self.MATCH_FMRI

                                if matcher == self.MATCH_GLOB:
                                        npat = fmri.MatchingPkgFmri(pat_stem,
                                            brelease)
                                else:
                                        npat = fmri.PkgFmri(pat_stem, brelease)

                                if not pat_ver:
                                        # Do nothing.
                                        pass
                                elif "*" in pat_ver or "?" in pat_ver or \
                                    pat_ver == "latest":
                                        npat.version = \
                                            pkg.version.MatchingVersion(pat_ver,
                                                brelease)
                                else:
                                        npat.version = \
                                            pkg.version.Version(pat_ver,
                                                brelease)

                        except (fmri.FmriError, pkg.version.VersionError), e:
                                # Whatever the error was, return it.
                                error = e
                        yield (pat, error, npat, matcher)

        def update_format(self):
                """Attempt to update the on-disk format of the image to the
                newest version.  Returns a boolean indicating whether any action
                was taken."""

                self._acquire_activity_lock()
                try:
                        self._disable_cancel()
                        self._img.allow_ondisk_upgrade = True
                        return self._img.update_format(
                            progtrack=self.__progresstracker)
                except apx.CanceledException, e:
                        self._cancel_done()
                        raise
                finally:
                        self._activity_lock.release()

        def write_p5i(self, fileobj, pkg_names=None, pubs=None):
                """Writes the publisher, repository, and provided package names
                to the provided file-like object 'fileobj' in JSON p5i format.

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
                                        plist.append(self._img.get_publisher(
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

        def write_syspub(self, path, prefixes, version):
                """Write the syspub/version response to the provided path."""
                if version != 0:
                        raise apx.UnsupportedP5SVersion(version)

                pubs = [
                    p for p in self.get_publishers()
                    if p.prefix in prefixes
                ]
                fd, fp = tempfile.mkstemp()
                try:
                        fh = os.fdopen(fd, "wb")
                        p5s.write(fh, pubs, self._img.cfg)
                        fh.close()
                        portable.rename(fp, path)
                except:
                        if os.path.exists(fp):
                                portable.remove(fp)
                        raise


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
        """A class which describes the changes the plan will make."""

        def __init__(self, img, new_be, be_activate):
                self.__plan = img.imageplan
                self._img = img
                self.__new_be = new_be
                self.__be_activate = be_activate

        def get_services(self):
                """Returns a list of services affected in this plan."""
                return self.__plan.services

        def get_varcets(self):
                """Returns a list of variant/facet changes in this plan"""
                return self.__plan.varcets

        def get_changes(self):
                """A generation function that yields tuples of PackageInfo
                objects of the form (src_pi, dest_pi).

                If 'src_pi' is None, then 'dest_pi' is the package being
                installed.

                If 'src_pi' is not None, and 'dest_pi' is None, 'src_pi'
                is the package being removed.

                If 'src_pi' is not None, and 'dest_pi' is not None,
                then 'src_pi' is the original version of the package,
                and 'dest_pi' is the new version of the package it is
                being upgraded to."""

                for pp in self.__plan.pkg_plans:
                        yield (PackageInfo.build_from_fmri(pp.origin_fmri),
                            PackageInfo.build_from_fmri(pp.destination_fmri))

        def get_actions(self):
                """A generator function that returns action changes for all
                the package plans"""
                for pp in self.__plan.pkg_plans:
                        yield str(pp)

        def get_licenses(self, pfmri=None):
                """A generator function that yields information about the
                licenses related to the current plan in tuples of the form
                (dest_fmri, src, dest, accepted, displayed) for the given
                package FMRI or all packages in the plan.  This is only
                available for licenses that are being installed or updated.

                'dest_fmri' is the FMRI of the package being installed.

                'src' is a LicenseInfo object if the license of the related
                package is being updated; otherwise it is None.

                'dest' is the LicenseInfo object for the license that is being
                installed.

                'accepted' is a boolean value indicating that the license has
                been marked as accepted for the current plan.

                'displayed' is a boolean value indicating that the license has
                been marked as displayed for the current plan."""

                for pp in self.__plan.pkg_plans:
                        dfmri = pp.destination_fmri
                        if pfmri and dfmri != pfmri:
                                continue

                        for lid, entry in pp.get_licenses():
                                src = entry["src"]
                                src_li = None
                                if src:
                                        src_li = LicenseInfo(pp.origin_fmri,
                                            src, img=self._img)

                                dest = entry["dest"]
                                dest_li = None
                                if dest:
                                        dest_li = LicenseInfo(
                                            pp.destination_fmri, dest,
                                            img=self._img)

                                yield (pp.destination_fmri, src_li, dest_li,
                                    entry["accepted"], entry["displayed"])

                        if pfmri:
                                break

        def get_salvaged(self):
                """Returns a list of tuples of items that were salvaged during
                plan execution.  Each tuple is of the form (original_path,
                salvage_path).  Where 'original_path' is the path of the item
                before it was salvaged, and 'salvage_path' is where the item was
                moved to.  This method may only be called after plan execution
                has completed."""

                assert self.__plan.state in (ip.EXECUTED_OK,
                    ip.EXECUTED_ERROR), \
                        "self.__plan.state in (ip.EXECUTED_OK, " \
                        "ip.EXECUTED_ERROR)\nself.__plan.state == %d" % \
                        self.__plan.state
                return copy.copy(self.__plan.salvaged)

        def get_solver_errors(self):
                """Returns a list of strings for all FMRIs evaluated by the
                solver explaining why they were rejected.  (All packages
                found in solver's trim database.)  Only available if
                DebugValues["plan"] was set when the plan was created.
                """

                if not DebugValues["plan"]:
                        return []

                return self.__plan.get_solver_errors()

        @property
        def activate_be(self):
                """A boolean value indicating whether any new boot environment
                will be set active on next boot."""
                return self.__be_activate

        @property
        def reboot_needed(self):
                """A boolean value indicating that execution of the plan will
                require a restart of the system to take effect if the target
                image is an existing boot environment."""
                return self.__plan.reboot_needed()

        @property
        def new_be(self):
                """A boolean value indicating that execution of the plan will
                take place in a clone of the current live environment"""
                return self.__new_be

        @property
        def update_boot_archive(self):
                """A boolean value indicating whether or not the boot archive
                will be rebuilt"""
                return self.__plan.boot_archive_needed()

        @property
        def bytes_added(self):
                """Returns approximate number of bytes added"""
                return self.__plan.bytes_added

        @property
        def cbytes_added(self):
                """Returns approximate number of download cache bytes added"""
                return self.__plan.cbytes_added

        @property
        def bytes_avail(self):
                """Returns approximate number of bytes available in image /"""
                return self.__plan.bytes_avail

        @property
        def cbytes_avail(self):
                """Returns approximate number of space in download cache"""
                return self.__plan.cbytes_avail
         

def image_create(pkg_client_name, version_id, root, imgtype, is_zone,
    cancel_state_callable=None, facets=misc.EmptyDict, force=False,
    mirrors=misc.EmptyI, origins=misc.EmptyI, prefix=None, refresh_allowed=True,
    repo_uri=None, ssl_cert=None, ssl_key=None, user_provided_dir=False,
    progtrack=None, variants=misc.EmptyDict, props=misc.EmptyDict,
    cmdpath=None):
        """Creates an image at the specified location.

        'pkg_client_name' is a string containing the name of the client,
        such as "pkg" or "packagemanager".

        'version_id' indicates the version of the api the client is
        expecting to use.

        'root' is the absolute path of the directory where the image will
        be created.  If it does not exist, it will be created.

        'imgtype' is an IMG_TYPE constant representing the type of image
        to create.

        'is_zone' is a boolean value indicating whether the image being
        created is for a zone.

        'cancel_state_callable' is an optional function reference that will
        be called if the cancellable status of an operation changes.

        'facets' is a dictionary of facet names and values to set during
        the image creation process.

        'force' is an optional boolean value indicating that if an image
        already exists at the specified 'root' that it should be overwritten.

        'mirrors' is an optional list of URI strings that should be added to
        all publishers configured during image creation as mirrors.

        'origins' is an optional list of URI strings that should be added to
        all publishers configured during image creation as origins.

        'prefix' is an optional publisher prefix to configure as a publisher
        for the new image if origins is provided, or to restrict which publisher
        will be configured if 'repo_uri' is provided.  If this prefix does not
        match the publisher configuration retrieved from the repository, an
        UnknownRepositoryPublishers exception will be raised.  If not provided,
        'refresh_allowed' cannot be False.

        'props' is an optional dictionary mapping image property names to values
        to be set while creating the image.

        'refresh_allowed' is an optional boolean value indicating whether
        publisher configuration data and metadata can be retrieved during
        image creation.  If False, 'repo_uri' cannot be specified and
        a 'prefix' must be provided.

        'repo_uri' is an optional URI string of a package repository to
        retrieve publisher configuration information from.  If the target
        repository supports this, all publishers found will be added to the
        image and any origins or mirrors will be added to all of those
        publishers.  If the target repository does not support this, and a
        prefix was not specified, an UnsupportedRepositoryOperation exception
        will be raised.  If the target repository supports the operation, but
        does not provide complete configuration information, a
        RepoPubConfigUnavailable exception will be raised.

        'ssl_cert' is an optional pathname of an SSL Certificate file to
        configure all publishers with and to use when retrieving publisher
        configuration information.  If provided, 'ssl_key' must also be
        provided.  The certificate file must be pem-encoded.

        'ssl_key' is an optional pathname of an SSL Key file to configure all
        publishers with and to use when retrieving publisher configuration
        information.  If provided, 'ssl_cert' must also be provided.  The
        key file must be pem-encoded.

        'user_provided_dir' is an optional boolean value indicating that the
        provided 'root' was user-supplied and that additional error handling
        should be enforced.  This primarily affects cases where a relative
        root has been provided or the root was based on the current working
        directory.

        'progtrack' is an optional ProgressTracker object.

        'variants' is a dictionary of variant names and values to set during
        the image creation process.

        Callers must provide one of the following when calling this function:
         * no 'prefix' and no 'origins'
         * a 'prefix' and 'repo_uri' (origins and mirrors are optional)
         * no 'prefix' and a 'repo_uri'  (origins and mirrors are optional)
         * a 'prefix' and 'origins'
        """

        # Caller must provide a prefix and repository, or no prefix and a
        # repository, or a prefix and origins, or no prefix and no origins.
        assert (prefix and repo_uri) or (not prefix and repo_uri) or (prefix and
            origins or (not prefix and not origins))

        # If prefix isn't provided and refresh isn't allowed, then auto-config
        # cannot be done.
        assert (prefix or refresh_allowed) or not repo_uri

        destroy_root = False
        try:
                destroy_root = not os.path.exists(root)
        except EnvironmentError, e:
                if e.errno == errno.EACCES:
                        raise apx.PermissionsException(
                            e.filename)
                raise

        # The image object must be created first since transport may be
        # needed to retrieve publisher configuration information.
        img = image.Image(root, force=force, imgtype=imgtype,
            progtrack=progtrack, should_exist=False,
            user_provided_dir=user_provided_dir, cmdpath=cmdpath,
            props=props)
        api_inst = ImageInterface(img, version_id,
            progtrack, cancel_state_callable, pkg_client_name,
            cmdpath=cmdpath)

        pubs = []

        try:
                if repo_uri:
                        # Assume auto configuration.
                        if ssl_cert:
                                misc.validate_ssl_cert(ssl_cert, prefix=prefix,
                                    uri=repo_uri)

                        repo = publisher.RepositoryURI(repo_uri,
                            ssl_cert=ssl_cert, ssl_key=ssl_key)

                        pubs = None
                        try:
                                pubs = api_inst.get_publisherdata(repo=repo)
                        except apx.UnsupportedRepositoryOperation:
                                if not prefix:
                                        raise apx.RepoPubConfigUnavailable(
                                            location=repo_uri)
                                # For a v0 repo where a prefix was specified,
                                # fallback to manual configuration.
                                if not origins:
                                        origins = [repo_uri]
                                repo_uri = None

                        if not prefix and not pubs:
                                # Empty repository configuration.
                                raise apx.RepoPubConfigUnavailable(
                                    location=repo_uri)

                        if repo_uri:
                                for p in pubs:
                                        psrepo = p.repository
                                        if not psrepo:
                                                # Repository configuration info
                                                # was not provided, so assume
                                                # origin is repo_uri.
                                                p.repository = \
                                                    publisher.Repository(
                                                    origins=[repo_uri])
                                        elif not psrepo.origins:
                                                # Repository configuration was
                                                # provided, but without an
                                                # origin.  Assume the repo_uri
                                                # is the origin.
                                                psrepo.add_origin(repo_uri)
                                        elif repo not in psrepo.origins:
                                                # If the repo_uri used is not
                                                # in the list of sources, then
                                                # add it as the first origin.
                                                psrepo.origins.insert(0, repo)

                if prefix and not repo_uri:
                        # Auto-configuration not possible or not requested.
                        if ssl_cert:
                                misc.validate_ssl_cert(ssl_cert, prefix=prefix,
                                    uri=origins[0])

                        repo = publisher.Repository()
                        for o in origins:
                                repo.add_origin(o)
                        for m in mirrors:
                                repo.add_mirror(m)
                        pub = publisher.Publisher(prefix,
                            repository=repo)
                        pubs = [pub]

                if prefix and prefix not in pubs:
                        # If publisher prefix requested isn't found in the list
                        # of publishers at this point, then configuration isn't
                        # possible.
                        known = [p.prefix for p in pubs]
                        raise apx.UnknownRepositoryPublishers(
                            known=known, unknown=[prefix], location=repo_uri)
                elif prefix:
                        # Filter out any publishers that weren't requested.
                        pubs = [
                            p for p in pubs
                            if p.prefix == prefix
                        ]

                # Add additional origins and mirrors that weren't found in the
                # publisher configuration if provided.
                for p in pubs:
                        pr = p.repository
                        for o in origins:
                                if not pr.has_origin(o):
                                        pr.add_origin(o)
                        for m in mirrors:
                                if not pr.has_mirror(m):
                                        pr.add_mirror(m)

                # Set provided SSL Cert/Key for all configured publishers.
                for p in pubs:
                        repo = p.repository
                        for o in repo.origins:
                                if o.scheme not in publisher.SSL_SCHEMES:
                                        continue
                                o.ssl_cert = ssl_cert
                                o.ssl_key = ssl_key
                        for m in repo.mirrors:
                                if m.scheme not in publisher.SSL_SCHEMES:
                                        continue
                                m.ssl_cert = ssl_cert
                                m.ssl_key = ssl_key

                img.create(pubs, facets=facets, is_zone=is_zone,
                    progtrack=progtrack, refresh_allowed=refresh_allowed,
                    variants=variants, props=props)
        except EnvironmentError, e:
                if e.errno == errno.EACCES:
                        raise apx.PermissionsException(
                            e.filename)
                if e.errno == errno.EROFS:
                        raise apx.ReadOnlyFileSystemException(
                            e.filename)
                raise
        except:
                # Ensure a defunct image isn't left behind.
                img.destroy()
                if destroy_root and \
                    os.path.abspath(root) != "/" and \
                    os.path.exists(root):
                        # Root didn't exist before create and isn't '/',
                        # so remove it.
                        shutil.rmtree(root, True)
                raise

        img.cleanup_downloads()

        return api_inst
