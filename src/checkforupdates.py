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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import getopt
import gettext
import locale
import os
import sys

import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.gui.enumerations as enumerations
import pkg.gui.misc_non_gui as nongui_misc
import pkg.misc as misc
import pkg.nrlock as nrlock
from cPickle import UnpicklingError
from pkg.client import global_settings

logger = global_settings.logger

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

IMAGE_DIRECTORY_DEFAULT = "/"   # Image default directory
IMAGE_DIR_COMMAND = "svcprop -p update/image_dir svc:/application/pkg/update"

PKG_CLIENT_NAME = "updatemanager"
CACHE_VERSION =  3
CACHE_NAME = ".last_refresh_cache"

class CheckForUpdates:
        def __init__(self, image_directory, application_path, nice, check_all,
            check_cache):
                global_settings.client_name = nongui_misc.get_um_name()
                self.api_lock = nrlock.NRLock()
                self.image_dir_arg = image_directory
                if self.image_dir_arg == None:
                        self.image_dir_arg = nongui_misc.get_image_path()
                self.application_path = application_path
                self.nice = nice
                self.check_all = check_all
                self.check_cache_only = check_cache
                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")

                self.progress_tracker = progress.NullProgressTracker()
                self.api_obj = None
                self.return_status = enumerations.UPDATES_UNDETERMINED
                self.pylintstub = None

                # Check Updates - by default check all
                if self.check_all:
                        self.api_obj = self.__get_api_obj()
                        self.__check_for_updates()
                elif self.check_cache_only:
                        self.api_obj = self.__get_api_obj()
                        ret = self.__check_for_updates_cache_only()
                        if ret == enumerations.UPDATES_UNDETERMINED:
                                self.__send_return(enumerations.UPDATES_UNDETERMINED)
                
        def __get_api_obj(self):
                if self.api_obj == None:
                        api_obj = nongui_misc.get_api_object(self.image_dir_arg,
                            self.progress_tracker)
                return api_obj

        def __check_for_updates_cache_only(self):
                if self.nice:
                        os.nice(20)

                if self.api_obj == None:
                        return enumerations.UPDATES_UNDETERMINED

                ret = self.__check_last_refresh()
                if ret == enumerations.UPDATES_AVAILABLE:
                        if debug:
                                print >> sys.stderr, "From cache: Updates Available"
                        self.__send_return(ret)
                elif ret == enumerations.NO_UPDATES_AVAILABLE:
                        if debug:
                                print >> sys.stderr, \
                                        "From cache: No Updates Available"
                        self.__send_return(ret)
                elif debug:
                        print >> sys.stderr, "From cache: Updates Undetermined"
                return ret

        def __check_for_updates(self):
                ret = self.__check_for_updates_cache_only()
                if ret != enumerations.UPDATES_UNDETERMINED:
                        return
                if debug:
                        print >> sys.stderr, \
                                "Checking image for updates..."
                if self.api_obj == None:
                        self.__send_return(enumerations.UPDATES_UNDETERMINED)
                        return
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
                        for pd in self.api_obj.gen_plan_update(
                            refresh_catalogs=True, noexecute=True,
                            force=True, li_ignore=[]):
                                continue
                        stuff_to_do = not self.api_obj.planned_nothingtodo()
                except api_errors.CatalogRefreshException, cre:
                        crerr = nongui_misc.get_catalogrefresh_exception_msg(cre)
                        if debug:
                                print >> sys.stderr, "Exception occurred: %s" % crerr
                        logger.error(crerr)
                        self.__send_return(enumerations.UPDATES_UNDETERMINED)
                        return
                except api_errors.ApiException, e:
                        err = str(e)
                        if debug:
                                print >> sys.stderr, "Exception occurred: %s" % err
                        logger.error(err)
                        self.__send_return(enumerations.UPDATES_UNDETERMINED)
                        return

                self.__dump_updates_available(stuff_to_do)
                if stuff_to_do:
                        if debug:
                                print >> sys.stderr, "From image: Updates Available"
                        self.__send_return(enumerations.UPDATES_AVAILABLE)
                else:
                        if debug:
                                print >> sys.stderr, "From image: No Updates Available"
                        self.__send_return(enumerations.NO_UPDATES_AVAILABLE)

        def __send_return(self, status):
                self.return_status = status

        def __check_last_refresh(self):
                cache_dir = nongui_misc.get_cache_dir(self.api_obj)
                if not cache_dir:
                        return enumerations.UPDATES_UNDETERMINED
                try:
                        info = nongui_misc.read_cache_file(os.path.join(
                            cache_dir, CACHE_NAME + '.cpl'))
                        if len(info) == 0:
                                if debug:
                                        print >> sys.stderr, "No cache"
                                return enumerations.UPDATES_UNDETERMINED
                        # pylint: disable-msg=E1103
                        if info.get("version") != CACHE_VERSION:
                                if debug:
                                        print >> sys.stderr, "Cache version mismatch: %s"\
                                            % (info.get("version") + " " + CACHE_VERSION)
                                return enumerations.UPDATES_UNDETERMINED
                        if info.get("os_release") != os.uname()[2]:
                                if debug:
                                        print >> sys.stderr, "OS release mismatch: %s"\
                                            % (info.get("os_release") + " " + \
                                            os.uname()[2])
                                return enumerations.UPDATES_UNDETERMINED
                        if info.get("os_version") != os.uname()[3]:
                                if debug:
                                        print >> sys.stderr, "OS version mismatch: %s"\
                                            % (info.get("os_version") + " " + \
                                            os.uname()[3])
                                return enumerations.UPDATES_UNDETERMINED
                        old_publishers = info.get("publishers")
                        count = 0
                        for p in self.api_obj.get_publishers():
                                if p.disabled:
                                        continue
                                try:
                                        if old_publishers[p.prefix] != p.last_refreshed:
                                                return enumerations.UPDATES_UNDETERMINED
                                except KeyError:
                                        return enumerations.UPDATES_UNDETERMINED
                                count += 1

                        if count != len(old_publishers):
                                return enumerations.UPDATES_UNDETERMINED
                        n_updates = 0
                        n_installs = 0
                        n_removes = 0
                        if info.get("updates_available"):
                                n_updates = info.get("updates")
                                n_installs = info.get("installs")
                                n_removes = info.get("removes")
                        # pylint: enable-msg=E1103
                        if self.check_cache_only:
                                print "n_updates: %d\nn_installs: %d\nn_removes: %d" % \
                                        (n_updates, n_installs, n_removes)
                        if (n_updates + n_installs + n_removes) > 0:
                                return enumerations.UPDATES_AVAILABLE
                        else:
                                return enumerations.NO_UPDATES_AVAILABLE

                except (UnpicklingError, IOError):
                        return enumerations.UPDATES_UNDETERMINED

        def __dump_updates_available(self, stuff_to_do):
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
                        for pkg_plan in plan:
                                orig = pkg_plan[0]
                                dest = pkg_plan[1]
                                if orig and dest:
                                        n_updates += 1
                                elif not orig and dest:
                                        n_installs += 1
                                elif orig and not dest:
                                        n_removes += 1
                dump_info = {}
                dump_info["version"] = CACHE_VERSION
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
                        err = str(e)
                        if debug:
                                print >> sys.stderr, "Failed to dump cache: %s" % err
                        logger.error(err)
                return

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main():
        sys.exit(checkforupdates.return_status)
        return 0

if __name__ == '__main__':
        misc.setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")
        debug = False
        set_nice = False
        set_check_all = True
        set_check_cache = False
        image_dir = "/"
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "hdnacR:",
                    ["help", "debug", "nice", "checkupdates-all", "checkupdates-cache",
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
                        set_nice = True
                elif opt in ("-d", "--debug"):
                        debug = True
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

        checkforupdates = CheckForUpdates(image_dir, app_path, set_nice,
            set_check_all, set_check_cache)

        main()
