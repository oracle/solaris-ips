#!/usr/bin/python2.6
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
# Copyright (c) 2008, 2012, Oracle and/or its affiliates. All rights reserved.
#

"""This utility checks to see if there are any available updates for
the relevant image.  If so, it stashes information about the updates in
the gui cache file, for retrieval by other desktop utilities.  See also
the update-refresh cron job."""

import errno
import getopt
import gettext
import locale
import logging
import os
import sys
import traceback
import warnings

import pkg.client.api as api
import pkg.client.api_errors as apx
import pkg.client.progress as progress
import pkg.client.printengine as printengine
import pkg.gui.enumerations as enumerations
import pkg.gui.misc_non_gui as nongui_misc
import pkg.misc as misc
import pkg.nrlock as nrlock
from cPickle import UnpicklingError
from pkg.client import global_settings
from pkg.client.pkgdefs import EXIT_OOPS

logger = global_settings.logger

PKG_CLIENT_NAME = "updatemanager"
CACHE_VERSION =  3
CACHE_NAME = ".last_refresh_cache"


class CheckForUpdates:
        """Implements the main logic for this utility"""

        def __init__(self, image_directory, application_path, check_all,
            check_cache):
                global_settings.client_name = nongui_misc.get_um_name()
                self.api_lock = nrlock.NRLock()
                self.image_dir_arg = image_directory
                self.exact_match = True
                if self.image_dir_arg == None:
                        self.image_dir_arg, self.exact_match =  \
                            api.get_default_image_root()
                if not self.exact_match:
                        if debug:
                                print >> sys.stderr, ("Unable to get image directory")
                                sys.exit(enumerations.UPDATES_UNDETERMINED)
                        
                self.application_path = application_path
                self.check_all = check_all
                self.check_cache_only = check_cache
                self.application_dir = \
                    os.environ.get("PACKAGE_MANAGER_ROOT", "/")
                misc.setlocale(locale.LC_ALL, "")

                if global_settings.verbose:
                        pe = printengine.LoggingPrintEngine(
                            logger, logging.DEBUG)
                        self.progress_tracker = \
                            progress.CommandLineProgressTracker(print_engine=pe)
                else:
                        self.progress_tracker = progress.NullProgressTracker()
                self.api_obj = None
                self.return_status = enumerations.UPDATES_UNDETERMINED
                self.pylintstub = None

                # Check Updates - by default check all
                self.api_obj = self.__get_api_obj()
                if self.api_obj == None:
                        self.return_status = enumerations.UPDATES_UNDETERMINED
                        return

                if self.check_all:
                        self.__check_for_updates()
                elif self.check_cache_only:
                        self.__check_for_updates_cache_only()

        def __get_api_obj(self):
                """Returns a singleton api instance."""
                if self.api_obj == None:
                        api_obj = nongui_misc.get_api_object(self.image_dir_arg,
                            self.progress_tracker)
                return api_obj

        def __check_for_updates_cache_only(self):
                """Reports on the cached status of available updates"""
                assert self.api_obj
                self.return_status = ret = self.__check_last_refresh()
                if ret == enumerations.UPDATES_AVAILABLE:
                        logger.debug("From cache: Updates Available")
                elif ret == enumerations.NO_UPDATES_AVAILABLE:
                        logger.debug("From cache: No Updates Available")
                else:
                        logger.debug("From cache: Updates Undetermined")
                return ret

        def __check_for_updates(self):
                """Plans an update for the image."""
                assert self.api_obj
                ret = self.__check_for_updates_cache_only()
                if ret != enumerations.UPDATES_UNDETERMINED:
                        # Definitive answer from cache.
                        return
                logger.debug("Checking image for updates...")
                self.return_status = enumerations.UPDATES_UNDETERMINED
                try:
                        #
                        # Since this program is intended to primarily be a
                        # helper for the gui components, and since the gui
                        # components are currently unaware of child images,
                        # we'll limit the available update check we're about
                        # to do to just the parent image.  If we didn't do
                        # this we could end up in a situation where the parent
                        # has no available updates, but a child image does,
                        # and then the gui (which is unaware of children)
                        # would show that no updates are available to the
                        # parent.
                        #

                        # Unused variable; pylint: disable-msg=W0612
                        for pd in self.api_obj.gen_plan_update(
                            refresh_catalogs=True, noexecute=True,
                            force=True, li_ignore=[]):
                                continue
                        stuff_to_do = not self.api_obj.planned_nothingtodo()
                except apx.CatalogRefreshException, cre:
                        res = nongui_misc.get_catalogrefresh_exception_msg(cre)
                        logger.error(res[0])
                        return
                except apx.ApiException, e:
                        logger.error(str(e))
                        return

                self.__dump_updates_available(stuff_to_do)
                if stuff_to_do:
                        logger.debug("From image: Updates Available")
                        self.return_status = enumerations.UPDATES_AVAILABLE
                else:
                        logger.debug("From image: No Updates Available")
                        self.return_status = enumerations.NO_UPDATES_AVAILABLE

        def __check_last_refresh(self):
                """Reads the cache if possible; if it isn't stale or corrupt
                or out of date, return whether updates are available.
                Otherwise return 'undetermined'."""

                cache_dir = nongui_misc.get_cache_dir(self.api_obj)
                if not cache_dir:
                        return enumerations.UPDATES_UNDETERMINED
                try:
                        info = nongui_misc.read_cache_file(os.path.join(
                            cache_dir, CACHE_NAME + '.cpl'))
                        if len(info) == 0:
                                logger.debug("No cache")
                                return enumerations.UPDATES_UNDETERMINED
                        # Non-portable API used; pylint: disable-msg=E0901
                        utsname = os.uname()
                        # pylint: disable-msg=E1103
                        if info.get("version") != CACHE_VERSION:
                                logger.debug("Cache version mismatch: %s" %
                                    (info.get("version") + " " + CACHE_VERSION))
                                return enumerations.UPDATES_UNDETERMINED
                        if info.get("os_release") != utsname[2]:
                                logger.debug("OS release mismatch: %s" %
                                    (info.get("os_release") + " " + utsname[2]))
                                return enumerations.UPDATES_UNDETERMINED
                        if info.get("os_version") != utsname[3]:
                                logger.debug("OS version mismatch: %s" %
                                    (info.get("os_version") + " " + utsname[3]))
                                return enumerations.UPDATES_UNDETERMINED
                        old_publishers = info.get("publishers")
                        count = 0
                        for p in self.api_obj.get_publishers():
                                if p.disabled:
                                        continue
                                if old_publishers.get(p.prefix, -1) != \
                                    p.last_refreshed:
                                        return enumerations.UPDATES_UNDETERMINED
                                count += 1

                        if count != len(old_publishers):
                                return enumerations.UPDATES_UNDETERMINED

                        n_updates = n_installs = n_removes = 0
                        if info.get("updates_available"):
                                n_updates = info.get("updates")
                                n_installs = info.get("installs")
                                n_removes = info.get("removes")
                        # pylint: enable-msg=E1103
                        if self.check_cache_only:
                                print "n_updates: %d" % n_updates
                                print "n_installs: %d" % n_installs
                                print "n_removes: %d" % n_removes
                        if (n_updates + n_installs + n_removes) > 0:
                                return enumerations.UPDATES_AVAILABLE
                        else:
                                return enumerations.NO_UPDATES_AVAILABLE

                except (UnpicklingError, IOError):
                        return enumerations.UPDATES_UNDETERMINED

        def __dump_updates_available(self, stuff_to_do):
                """Record update information to the cache file."""
                cache_dir = nongui_misc.get_cache_dir(self.api_obj)
                if not cache_dir:
                        return
                publisher_list = {}
                for p in self.api_obj.get_publishers():
                        if p.disabled:
                                continue
                        publisher_list[p.prefix] = p.last_refreshed
                n_installs = 0
                n_removes = 0
                n_updates = 0
                plan_desc = self.api_obj.describe()
                if plan_desc:
                        plan = plan_desc.get_changes()
                        for (orig, dest) in plan:
                                if orig and dest:
                                        n_updates += 1
                                elif not orig and dest:
                                        n_installs += 1
                                elif orig and not dest:
                                        n_removes += 1
                dump_info = {}
                dump_info["version"] = CACHE_VERSION
                # Non-portable API used; pylint: disable-msg=E0901
                dump_info["os_release"] = os.uname()[2]
                dump_info["os_version"] = os.uname()[3]
                dump_info["updates_available"] = stuff_to_do
                dump_info["publishers"] = publisher_list
                dump_info["updates"] = n_updates
                dump_info["installs"] = n_installs
                dump_info["removes"] = n_removes

                try:
                        nongui_misc.dump_cache_file(os.path.join(
                            cache_dir, CACHE_NAME + '.cpl'), dump_info)
                except IOError, e:
                        logger.error("Failed to dump cache: %s" % e)
                return


def main_func():
        """Main routine for this utility"""
        set_check_all = True
        set_check_cache = False
        image_dir = None 
        try:
                # Unused variable pargs; pylint: disable-msg=W0612
                opts, pargs = getopt.getopt(sys.argv[1:], "hdnacR:",
                    ["help", "debug", "nice", "checkupdates-cache",
                    "image-dir="])
        except getopt.GetoptError, oex:
                print >> sys.stderr, \
                    ("Usage: illegal option -- %s, for help use -h or --help" %
                    oex.opt )
                sys.exit(enumerations.UPDATES_UNDETERMINED)
        for opt, arg in opts:
                if opt in ("-h", "--help"):
                        print >> sys.stderr, """\n\
Use -h (--help) to print out help.
Use -d (--debug) to run in debug mode.
Use -n (--nice) to run at nice level 20.
Use -c (--checkupdates-cache) to check for updates from cache only (output results to stdout).
Use -R (--image-dir) to specify image directory (defaults to '/')"""
                        sys.exit(0)
                elif opt in ( "-n", "--nice"):
                        # Non-portable API used; pylint: disable-msg=E0901
                        os.nice(20)
                elif opt in ("-d", "--debug"):
                        global_settings.verbose = True
                elif opt in ( "-c", "--checkupdates-cache"):
                        set_check_cache = True
                        set_check_all = False
                elif opt in ("-R", "--image-dir"):
                        image_dir = arg

        if os.path.isabs(sys.argv[0]):
                app_path = sys.argv[0]
        else:
                cmd = os.path.join(os.getcwd(), sys.argv[0])
                app_path = os.path.realpath(cmd)

        checkforupdates = CheckForUpdates(image_dir, app_path,
            set_check_all, set_check_cache)

        return checkforupdates.return_status

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
def handle_errors(func, *args, **kwargs):
        """Catch exceptions raised by the main program function and then print
        a message and/or exit with an appropriate return code.
        """

        traceback_str = misc.get_traceback_message()

        try:
                # Out of memory errors can be raised as EnvironmentErrors with
                # an errno of ENOMEM, so in order to handle those exceptions
                # with other errnos, we nest this try block and have the outer
                # one handle the other instances.
                try:
                        __ret = func(*args, **kwargs)
                except (MemoryError, EnvironmentError), __e:
                        if isinstance(__e, EnvironmentError) and \
                            __e.errno != errno.ENOMEM:
                                raise
                        logger.error("\n" + misc.out_of_memory())
                        __ret = EXIT_OOPS
        except SystemExit, __e:
                raise __e
        except (IOError, misc.PipeError, KeyboardInterrupt), __e:
                # Don't display any messages here to prevent possible further
                # broken pipe (EPIPE) errors.
                if isinstance(__e, IOError) and __e.errno != errno.EPIPE:
                        logger.error(str(__e))
                __ret = EXIT_OOPS
        except apx.VersionException, __e:
                logger.error("The pmcheckforupdates command appears out of "
                    "sync with the libraries provided\nby pkg:/package/pkg. "
                    "The client version is %(client)s while the library\n"
                    "API version is %(api)s." % \
                    {'client': __e.received_version,
                     'api': __e.expected_version})
                __ret = EXIT_OOPS
        except:
                traceback.print_exc()
                logger.error(traceback_str)
                __ret = 99
        return __ret


if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())

        # Make all warnings be errors.
        warnings.simplefilter('error')

        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
