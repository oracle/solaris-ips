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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#

import getopt
import gettext
import locale
import os
import sys

try:
        import gobject
        gobject.threads_init()
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)

import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.gui.enumerations as enumerations
import pkg.gui.installupdate as installupdate
import pkg.gui.misc as gui_misc
import pkg.gui.misc_non_gui as nongui_misc
import pkg.gui.pmgconf as pmgconf
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
PKG_ICON_LOCATION = "usr/share/package-manager/icons"
ICON_LOCATION = "usr/share/update-manager/icons"

class Updatemanager:
        def __init__(self, image_directory, application_path, nice, check_all,
            check_cache):
                global_settings.client_name = gui_misc.get_um_name()
                self.api_lock = nrlock.NRLock()
                self.image_dir_arg = image_directory
                if self.image_dir_arg == None:
                        self.image_dir_arg = self.__get_image_path()
                self.application_path = application_path
                self.nice = nice
                self.check_all = check_all
                self.check_cache_only = check_cache
                self.gconf = pmgconf.PMGConf()
                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("pkg", os.path.join(
                            self.application_dir,
                            "usr/share/locale"))
                        module.textdomain("pkg")
                gui_misc.init_for_help(self.application_dir)

                self.icon_theme = gtk.icon_theme_get_default()
                pkg_icon_location = os.path.join(self.application_dir, PKG_ICON_LOCATION)
                self.icon_theme.append_search_path(pkg_icon_location)
                icon_location = os.path.join(self.application_dir, ICON_LOCATION)
                self.icon_theme.append_search_path(icon_location)
                self.progress_tracker = progress.NullProgressTracker()
                self.api_obj = None
                self.installupdate = None
                self.return_status = enumerations.UPDATES_UNDETERMINED
                self.pylintstub = None
                
                # Check Updates
                if self.check_all:
                        self.api_obj = self.__get_api_obj()
                        self.__check_for_updates()
                        return
                elif self.check_cache_only:
                        self.api_obj = self.__get_api_obj()
                        ret = self.__check_for_updates_cache_only()
                        if ret == enumerations.UPDATES_UNDETERMINED:
                                self.__send_return(enumerations.UPDATES_UNDETERMINED)
                        return
                #If not checking for updates then launch Updatemanager to do image update
                gui_misc.setup_logging()
                gobject.idle_add(self.__do_image_update)

        def __get_api_obj(self):
                if self.api_obj == None:
                        api_obj = gui_misc.get_api_object(self.image_dir_arg,
                            self.progress_tracker, None)
                return api_obj

        def __do_image_update(self):
                self.installupdate = installupdate.InstallUpdate([], self,
                    self.image_dir_arg, action = enumerations.IMAGE_UPDATE,
                    parent_name = _("Update Manager"),
                    pkg_list = [gui_misc.package_name["SUNWipkg"],
                        gui_misc.package_name["SUNWipkg-gui"],
                        gui_misc.package_name["SUNWipkg-um"]],
                    main_window = None,
                    icon_confirm_dialog = gui_misc.get_icon(self.icon_theme,
                    "updatemanager", 36),
                    show_confirmation = self.gconf.show_image_update,
                    api_lock = self.api_lock, gconf = self.gconf)

        @staticmethod
        def __get_image_path():
                try:
                        image_directory = os.environ["PKG_IMAGE"]
                except KeyError:
                        image_directory = \
                            os.popen(IMAGE_DIR_COMMAND).readline().rstrip()
                        if len(image_directory) == 0:
                                image_directory = IMAGE_DIRECTORY_DEFAULT
                return image_directory

        def __exit_app(self, restart = False):
                gui_misc.shutdown_logging()
                if restart:
                        try:
                                if self.image_dir_arg:
                                        gobject.spawn_async([self.application_path,
                                            "--nice", "--image-dir",
                                            self.image_dir_arg])
                                else:
                                        gobject.spawn_async([self.application_path,
                                            "--nice"])
                        except gobject.GError, ex:
                                if debug:
                                        print >> sys.stderr, "Exception occurred: %s" % ex
                                logger.error(ex)
                gtk.main_quit()
                sys.exit(0)
                return True

        def restart_after_ips_update(self):
                self.__exit_app(restart = True)

        def update_package_list(self, update_list):
                self.pylintstub = update_list
                return

        def shutdown_after_image_update(self, exit_um = False):
                if exit_um == False:
                        self.__exit_app()

        def install_terminated(self):
                self.__exit_app()

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
                        plan_ret = \
                            self.api_obj.plan_update_all(sys.argv[0],
                            refresh_catalogs = True,
                            noexecute = True, force = True, verbose = False)
                        stuff_to_do = plan_ret[0]
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
        if set_check_all or set_check_cache:
                sys.exit(updatemanager.return_status)
        gtk.main()
        return 0

if __name__ == '__main__':
        misc.setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")
        debug = False
        set_nice = False
        set_check_all = False
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
Use -a (--checkupdates-all) to check for updates from cache and image (no output to stdout).
Use -c (--checkupdates-cache) to check for updates from cache only (output results to stdout).
Use -R (--image-dir) to specify image directory (defaults to '/')"""
                        sys.exit(0)
                elif opt in ( "-n", "--nice"):
                        set_nice = True
                elif opt in ("-d", "--debug"):
                        debug = True
                elif opt in ( "-a", "--checkupdates-all"):
                        set_check_all = True
                elif opt in ( "-c", "--checkupdates-cache"):
                        set_check_cache = True
                elif opt in ("-R", "--image-dir"):
                        image_dir = arg

        if os.path.isabs(sys.argv[0]):
                app_path = sys.argv[0]
        else:
                cmd = os.path.join(os.getcwd(), sys.argv[0])
                app_path = os.path.realpath(cmd)

        updatemanager = Updatemanager(image_dir, app_path, set_nice,
            set_check_all, set_check_cache)

        main()
