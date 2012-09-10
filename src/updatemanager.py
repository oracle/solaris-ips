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

import pkg.client.api as api
import pkg.client.progress as progress
import pkg.gui.enumerations as enumerations
import pkg.gui.installupdate as installupdate
import pkg.gui.misc as gui_misc
import pkg.gui.pmgconf as pmgconf
import pkg.misc as misc
import pkg.nrlock as nrlock
from pkg.client import global_settings

logger = global_settings.logger

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

PKG_CLIENT_NAME = "updatemanager"
CACHE_VERSION =  3
CACHE_NAME = ".last_refresh_cache"
PKG_ICON_LOCATION = "usr/share/package-manager/icons"
ICON_LOCATION = "usr/share/update-manager/icons"

class Updatemanager:
        def __init__(self, image_directory, application_path):
                global_settings.client_name = gui_misc.get_um_name()
                self.api_lock = nrlock.NRLock()
                self.image_dir_arg = image_directory
                self.exact_match = True
                if self.image_dir_arg == None:
                        self.image_dir_arg, self.exact_match = \
                            api.get_default_image_root()
                if not self.exact_match:
                        if debug:
                                print >> sys.stderr, ("Unable to get the image directory")
                        sys.exit(enumerations.UPDATES_UNDETERMINED)
                self.application_path = application_path
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
                
                gui_misc.setup_logging()
                gobject.idle_add(self.__do_image_update)

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

        def __exit_app(self, restart = False):
                gui_misc.shutdown_logging()
                if restart:
                        try:
                                if self.image_dir_arg:
                                        gobject.spawn_async([self.application_path,
                                            "--image-dir", self.image_dir_arg])
                                else:
                                        gobject.spawn_async([self.application_path])
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

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main():
        gtk.main()
        return 0

if __name__ == '__main__':
        misc.setlocale(locale.LC_ALL, "")
        gettext.install("pkg", "/usr/share/locale")
        debug = False
        image_dir = "/"
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "hdR:",
                    ["help", "debug", "image-dir="])
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
Use -R (--image-dir) to specify image directory (defaults to '/')"""
                        sys.exit(0)
                elif opt in ("-d", "--debug"):
                        debug = True
                elif opt in ("-R", "--image-dir"):
                        image_dir = arg

        if os.path.isabs(sys.argv[0]):
                app_path = sys.argv[0]
        else:
                cmd = os.path.join(os.getcwd(), sys.argv[0])
                app_path = os.path.realpath(cmd)

        updatemanager = Updatemanager(image_dir, app_path)

        main()
