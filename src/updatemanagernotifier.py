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
#

import os
import errno
import sys
import time
import socket
import locale
import gettext
import getopt
try:
        import gobject
        gobject.threads_init()
        import gconf
        import gtk
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)
try:
        import pynotify
except ImportError:
        print "SUNWpython-notify package must be installed"
        sys.exit(1)
import pkg.client.image as image
import pkg.client.progress as progress

START_DELAY_DEFAULT = 120
REFRESH_PERIOD_DEFAULT = "Never"
SHOW_NOTIFY_ICON_DEFAULT = True
IMAGE_DIRECTORY_DEFAULT = "/"
LASTCHECK_DIR_NAME = os.path.expanduser("~") + '/.updatemanager/notify/'
IMAGE_DIR_COMMAND = "svcprop -p update/image_dir svc:/application/pkg/update"

NOTIFY_ICON_PATH = "/usr/share/icons/update-manager/notify_update.png"
GKSU_PATH = "/usr/bin/gksu"
UPDATEMANAGER = "updatemanager"

START_DELAY_PREFERENCES = "/apps/updatemanager/preferences/start_delay"
REFRESH_PERIOD_PREFERENCES = "/apps/updatemanager/preferences/refresh_period"
SHOW_NOTIFY_MESSAGE_PREFERENCES = "/apps/updatemanager/preferences/show_notify_message"
SHOW_ICON_ON_STARTUP_PREFERENCES = "/apps/updatemanager/preferences/show_icon_on_startup"

DAILY = "Daily"
WEEKLY = "Weekly"
MONTHLY = "Monthly"
NEVER = "Never"

DAILY_SECS = 24*60*60
WEEKLY_SECS = 7*24*60*60
# We asssume that a month has 30 days
MONTHLY_SECS = 30*24*60*60

class UpdateManagerNotifier:
        def __init__(self):
                # Required for pkg strings used in pkg API
                gettext.install("pkg", "/usr/lib/locale")

                locale.setlocale(locale.LC_ALL, '')
                self._ = gettext.gettext
                self.client = gconf.client_get_default()
                self.start_delay  =  self.get_start_delay()
                # Allow gtk.main loop to start as quickly as possible
                gobject.timeout_add(self.start_delay * 1000, self.check_and_start)

        def check_and_start(self):
                self.check_already_running()
                self.refresh_period  =  self.get_refresh_period()
                self.host = socket.gethostname()
                self.last_check_filename = None
                self.time_until_next_check = 0
                self.status_icon = None
                self.notify = None

                if self.get_show_icon_on_startup():
                        self.show_status_icon()
                self.last_check_time = self.get_last_check_time()
                self.pr = progress.NullProgressTracker()
                gobject.idle_add(self.do_next_check)
                return False
                
        def get_start_delay(self):
                start_delay  =  self.client.get_int(START_DELAY_PREFERENCES)
                if start_delay == 0:
                        start_delay = START_DELAY_DEFAULT
                if debug == True:
                        print "start_delay: %d" % start_delay
                return start_delay

        def get_refresh_period(self):
                refresh_period  =  self.client.get_string(REFRESH_PERIOD_PREFERENCES)
                if refresh_period == None:
                        refresh_period = REFRESH_PERIOD_DEFAULT
                if debug == True:
                        print "refresh_period: %s" % refresh_period
                return refresh_period

        def get_show_notify_message(self):
                show_notify_message  =  \
                        self.client.get_bool(SHOW_NOTIFY_MESSAGE_PREFERENCES)
                if debug == True:
                        print "show_notify_message: %d" % show_notify_message
                return show_notify_message

        def get_show_icon_on_startup(self):
                show_icon_on_startup  =  \
                        self.client.get_bool(SHOW_ICON_ON_STARTUP_PREFERENCES)
                if debug == True:
                        print "show_icon_on_startup: %d" % show_icon_on_startup
                return show_icon_on_startup

        def get_last_check_time(self):
                if (self.last_check_filename == None):
                        self.last_check_filename = \
                                LASTCHECK_DIR_NAME + self.host + '-lastcheck'
                try:
                        f = open(self.last_check_filename, "r")

                        try:
                                return float(f.read(64))
                        finally:
                                f.close()

                except IOError, strerror:
                        if debug == True:
                                print "Unable to get last check time error %s" % strerror

                return 0

        def set_last_check_time(self):
                self.last_check_time = time.time()

                try:
                        os.makedirs(LASTCHECK_DIR_NAME)
                except os.error, eargs:
                        if eargs[0] != errno.EEXIST: # File exists
                                raise os.error, args

                try:
                        f = open(self.last_check_filename, "w")

                        try:
                                f.write(str(self.last_check_time))
                        finally:
                                f.close()

                except IOError, strerror:
                        print "I/O error: %s opening %s" \
                                % (strerror, self.last_check_filename)

        def is_check_required(self):
                if self.refresh_period == DAILY:
                        delta = DAILY_SECS
                elif self.refresh_period == WEEKLY:
                        delta = WEEKLY_SECS
                elif self.refresh_period == MONTHLY:
                        delta = MONTHLY_SECS
                else:
                        self.time_until_next_check = 0
                        return False
                current_time = time.time()
                if debug == True:
                        print "current time %s " \
                        % time.strftime("%a %d %b %Y %H:%M:%S", time.gmtime(current_time))
                self.time_until_next_check = self.last_check_time + delta - current_time
                if debug == True:
                        print "time until next check %f " % self.time_until_next_check
                if self.time_until_next_check <= 0:
                        return True
                else:
                        return False

        def show_status_icon(self):
                if self.status_icon == None:
                        self.status_icon = self.create_status_icon()
                self.client.set_bool(SHOW_ICON_ON_STARTUP_PREFERENCES, True)
                self.status_icon.set_visible(True)

        def check_for_updates(self):
                self.set_last_check_time()
                image_directory = os.popen(IMAGE_DIR_COMMAND).readline().rstrip()
                if debug == True:
                        print "image_directory: %s" % image_directory
                if len(image_directory) == 0:
                        image_directory = IMAGE_DIRECTORY_DEFAULT
                image_obj = self.__get_image_obj_from_directory(image_directory)
                pkgs_to_be_updated = [ pf[0] for pf in 
                        sorted(image_obj.inventory(all_known = False)) ]
                if debug == True:
                        print "pkgs_to_be_updated: %d" % len(pkgs_to_be_updated)
                if len(pkgs_to_be_updated):
                        self.show_status_icon()
                return False
        
        # This is copied from a similar function in packagemanager.py 
        def __get_image_obj_from_directory(self, image_directory):
                image_obj = image.Image()
                dr = "/"
                try:
                        image_obj.find_root(image_directory)
                        image_obj.load_config()
                        image_obj.load_catalogs(self.pr)
                except ValueError:
                        print self._('%s is not valid image, trying root image') \
                            % image_directory
                        try:
                                dr = os.environ["PKG_IMAGE"]
                        except KeyError:
                                print
                        try:
                                image_obj.find_root(dr)
                                image_obj.load_config()
                        except ValueError:
                                print self._('%s is not valid root image, return None') \
                                    % dr
                                image_obj = None
                return image_obj

        def create_status_icon(self):
                status_icon = gtk.status_icon_new_from_file(NOTIFY_ICON_PATH)
                status_icon.set_visible(False)
                status_icon.connect('activate', self.activate_status_icon)
                status_icon.connect('notify', self.notify_status_icon)
                status_icon.set_tooltip(self._("Updates are available"))
                return status_icon

        def notify_status_icon(self, status_icon, paramspec):
                if paramspec.name == "embedded" and self.status_icon.is_embedded():
                        if self.get_show_notify_message():
                                gobject.idle_add(self.show_notify_message)

        def activate_status_icon(self, status_icon):
                self.status_icon.set_visible(False)
                self.client.set_bool(SHOW_ICON_ON_STARTUP_PREFERENCES, False)
                gobject.spawn_async([GKSU_PATH, UPDATEMANAGER])
                gtk.main_quit()
                sys.exit(0)

        def show_notify_message(self):
                if self.notify == None:
                        if pynotify.init("UpdateManager"):
                                self.notify = pynotify.Notification(\
                self._("Update Manager"), \
                self._("Updates available\nPlease click on icon to update."))

                if self.notify != None:
                        self.set_notify_position()
                        self.notify.show()

        def set_notify_position(self):
                geometry = self.status_icon.get_geometry()
                rectangle = geometry[1]
                orientation = geometry[2]
                x = rectangle.x
                y = rectangle.y

                if orientation == gtk.ORIENTATION_HORIZONTAL and y > 200:
                        x += 10
                        y += 5
                elif orientation == gtk.ORIENTATION_HORIZONTAL and y <=200:
                        x += 10
                        y += 25
                elif orientation == gtk.ORIENTATION_VERTICAL and x >200:
                        x -= 5
                        y += 10
                else:
                        x += 25
                        y += 10
                self.notify.set_hint_int32("x", x)
                self.notify.set_hint_int32("y", y)

        def do_next_check(self):
                if debug == True:
                        print "Called do_next_check"
                if self.last_check_time == 0 or self.is_check_required():
                        gobject.idle_add(self.check_for_updates)
                else:
                        if self.time_until_next_check > DAILY_SECS:
                                next_check_time = DAILY_SECS
                        else:
                                next_check_time = self.time_until_next_check
                        gobject.timeout_add(int(next_check_time*1000), self.do_next_check)
                        return False
                return True

        def check_already_running(self):
                atom = gtk.gdk.atom_intern("UPDATEMANAGERNOTIFIER",
                                           only_if_exists = False)
                pid = os.getpid()
                atom_args = [pid, ]
                fail = True

                is_running = gtk.gdk.get_default_root_window().property_get(atom)
                if is_running != None:
                        old_pid = is_running[2][0]
                        try:
                                os.kill(old_pid, 0)
                        except os.error, eargs:
                                if eargs[0] != errno.ESRCH: # No such process
                                        raise os.error, args
                                # Old process no longer exists
                                fail = False
                else:
                        # Atom does not exist
                        fail = False

                if fail == True:
                        print self._("Another instance of UpdateManagerNotify is running")
                        sys.exit(1)

                gtk.gdk.get_default_root_window().property_change(atom,
                        "INTEGER", 16, gtk.gdk.PROP_MODE_REPLACE, atom_args)


###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main():
        gtk.main()
        return 0

if __name__ == '__main__':
        debug = False
        try:
                opts, args = getopt.getopt(sys.argv[1:], "hd", ["help", "debug"])
        except getopt.error, msg:
                print "%s, for help use --help" % msg
                sys.exit(2)

        for option, argument in opts:
                if option in ("-h", "--help"):
                        print "Use -d (--debug) to run in debug mode."
                        sys.exit(0)
                if option in ("-d", "--debug"):
                        debug = True

        updatemanager_notifier = UpdateManagerNotifier()

        main()
