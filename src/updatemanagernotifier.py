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

import os
import subprocess
import errno
import sys
import time
import socket
import locale
import gettext
import getopt
import random
try:
        import gobject
        gobject.threads_init()
        import gconf
        import gtk
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)
import pkg.client.progress as progress
import pkg.misc as misc
import pkg.gui.misc as gui_misc
import pkg.gui.enumerations as enumerations
from gettext import ngettext
try:
        import pynotify
except ImportError:
        print "%s package must be installed" % (
            gui_misc.package_name["SUNWpython26-notify"])
        sys.exit(1)

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

START_DELAY_DEFAULT = 120
REFRESH_PERIOD_DEFAULT = "Never"
SHOW_NOTIFY_ICON_DEFAULT = True
IMAGE_DIRECTORY_DEFAULT = "/"
LASTCHECK_DIR_NAME = os.path.join(os.path.expanduser("~"),'.updatemanager/notify')
IMAGE_DIR_COMMAND = "svcprop -p update/image_dir svc:/application/pkg/update"
UPDATEMANAGER_FULLPATH = "/usr/bin/pm-updatemanager"
UPDATEMANAGER = "pm-updatemanager"

ICON_LOCATION = "/usr/share/update-manager/icons"
NOTIFY_ICON_NAME = "updatemanager"
GKSU_PATH = "/usr/bin/gksu"

UPDATEMANAGER_PREFERENCES = "/apps/updatemanager/preferences"
START_DELAY_PREFERENCES = "/apps/updatemanager/preferences/start_delay"
REFRESH_PERIOD_PREFERENCES = "/apps/updatemanager/preferences/refresh_period"
SHOW_NOTIFY_MESSAGE_PREFERENCES = "/apps/updatemanager/preferences/show_notify_message"
SHOW_ICON_ON_STARTUP_PREFERENCES = "/apps/updatemanager/preferences/show_icon_on_startup"
TERMINATE_AFTER_ICON_ACTIVATE_PREFERENCES = \
    "/apps/updatemanager/preferences/terminate_after_icon_activate"

DAILY = "Daily"
WEEKLY = "Weekly"
MONTHLY = "Monthly"
NEVER = "Never"

DAILY_SECS = 24*60*60
WEEKLY_SECS = 7*24*60*60
# We asssume that a month has 30 days
MONTHLY_SECS = 30*24*60*60
NEVER_SECS = 365*24*60*60

class UpdateManagerNotifier:
        def __init__(self):
                os.nice(20)
                try:
                        self.application_dir = os.environ["UPDATE_MANAGER_NOTIFIER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                gettext.bindtextdomain("pkg", os.path.join(
                    self.application_dir,
                    "usr/share/locale"))
                gettext.textdomain("pkg")
                self.pr = None
                self.last_check_filename = None
                self.time_until_next_check = 0
                self.status_icon = None
                self.n_updates = 0
                self.n_installs = 0
                self.n_removes = 0
                self.notify = None
                self.host = None
                self.last_check_time = 0
                self.refresh_period = 0
                self.timeout_id = 0
                self.terminate_after_activate = False

                self.client = gconf.client_get_default()
                self.start_delay  =  self.get_start_delay()
                # Allow gtk.main loop to start as quickly as possible
                gobject.timeout_add(self.start_delay * 1000, self.check_and_start)

        def check_and_start(self):
                self.check_already_running()
                self.client.add_dir(UPDATEMANAGER_PREFERENCES, 
                    gconf.CLIENT_PRELOAD_NONE)
                self.client.notify_add(REFRESH_PERIOD_PREFERENCES, 
                    self.refresh_period_changed)
                self.client.notify_add(SHOW_ICON_ON_STARTUP_PREFERENCES, 
                    self.show_icon_changed)
                self.refresh_period  =  self.get_refresh_period()
                self.host = socket.gethostname()

                self.last_check_time = self.get_last_check_time()
                self.pr = progress.NullProgressTracker()
                if self.get_show_icon_on_startup():
                        self.client.set_bool(SHOW_ICON_ON_STARTUP_PREFERENCES, False)
                        self.schedule_check_for_updates()
                else:
                        gobject.idle_add(self.do_next_check)
                return False
                
        def refresh_period_changed(self, client, connection_id, entry, arguments):
                old_delta = self.get_delta_for_refresh_period()
                if entry.get_value().type == gconf.VALUE_STRING:
                        self.refresh_period = entry.get_value().get_string()
                new_delta = self.get_delta_for_refresh_period()
                if debug == True:
                        print "old_delta %d" % old_delta
                        print "new_delta %d" % new_delta
                if old_delta > new_delta:
                        if self.timeout_id > 0:
                                gobject.source_remove(self.timeout_id)
                                self.timeout_id = 0
                        self.do_next_check()

        def show_icon_changed(self, client, connection_id, entry, arguments):
                if entry.get_value().type == gconf.VALUE_BOOL:
                        show_icon = entry.get_value().get_bool()
                if self.status_icon != None:
                        self.status_icon.set_visible(show_icon)

        def get_start_delay(self):
                start_delay  =  self.client.get_int(START_DELAY_PREFERENCES)
                if start_delay == 0:
                        start_delay = START_DELAY_DEFAULT
                if debug == True:
                        start_delay = 1
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

        def get_terminate_after_activate(self):
                terminate_after_activate  =  \
                        self.client.get_bool(TERMINATE_AFTER_ICON_ACTIVATE_PREFERENCES)
                if debug == True:
                        print "terminate_after_activate: %d" % terminate_after_activate
                return terminate_after_activate

        def get_last_check_time(self):
                if (self.last_check_filename == None):
                        self.last_check_filename = \
                                os.path.join(LASTCHECK_DIR_NAME,
                                    self.host + '-lastcheck')
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

        def get_delta_for_refresh_period(self):
                if self.refresh_period == DAILY:
                        delta = DAILY_SECS
                elif self.refresh_period == WEEKLY:
                        delta = WEEKLY_SECS
                elif self.refresh_period == MONTHLY:
                        delta = MONTHLY_SECS
                else:
                        delta = NEVER_SECS
                return delta

        def is_check_required(self):
                delta = self.get_delta_for_refresh_period()
                if delta == NEVER_SECS:
                        self.time_until_next_check = NEVER_SECS
                        return False
                if self.last_check_time == 0:
                        return True
                current_time = time.time()
                if debug == True:
                        print "current time %f " % current_time
                        print "last check time %f " % self.last_check_time
                self.time_until_next_check = self.last_check_time + delta - current_time
                if debug == True:
                        print "time until next check %f " % self.time_until_next_check
                if self.time_until_next_check <= 0:
                        return True
                else:
                        return False

        def show_status_icon(self, value):
                if self.status_icon == None:
                        self.status_icon = self.create_status_icon()
                self.client.set_bool(SHOW_ICON_ON_STARTUP_PREFERENCES, value)
                self.status_icon.set_visible(value)
                if not value:
                        return

                toolfmt = _("<b>Updates are available: </b>\n"
                    "%(updates)s %(installs)s %(removes)s")
                tooltip = self.__set_updates_str(toolfmt)
                self.status_icon.set_tooltip_markup(tooltip)

        def __set_updates_str(self, str_fmt):
                if self.n_updates == 0:
                        updates_str = ""
                else:
                        updates_fmt = ngettext("%d Update,", "%d Updates,",
                            self.n_updates)
                        updates_str = updates_fmt % self.n_updates
                if self.n_installs == 0:
                        installs_str = ""
                else:
                        installs_fmt = ngettext("%d Install,", "%d Installs,",
                            self.n_installs)
                        installs_str = installs_fmt % self.n_installs
                if self.n_removes == 0:
                        removes_str = ""
                else:
                        removes_fmt = ngettext("%d Remove", "%d Removes",
                            self.n_removes)
                        removes_str = removes_fmt % self.n_removes
                updates_str = str_fmt % \
                    {"updates": updates_str,
                    "installs": installs_str,
                    "removes": removes_str}
                updates_str = updates_str.rstrip(', ')
                return updates_str

        def schedule_check_for_updates(self):
                self.last_check_time = time.time()
                # Add random delay so that servers will not be hit 
                # all at once
                if debug:
                        random_delay = 0
                else:
                        random_delay = random.randint(0, 1800)
                gobject.timeout_add(random_delay * 1000, self.check_for_updates)

        def check_for_updates(self):
                image_directory = os.popen(IMAGE_DIR_COMMAND).readline().rstrip()
                if debug == True:
                        print "image_directory: %s" % image_directory
                if len(image_directory) == 0:
                        image_directory = IMAGE_DIRECTORY_DEFAULT
                proc = subprocess.Popen([UPDATEMANAGER_FULLPATH,
                            '--nice', '--checkupdates-cache',
                            '--image-dir', image_directory],
                            stdout=subprocess.PIPE)

                output = proc.communicate()[0].strip()
                lines = output.splitlines()
                n_updates = 0
                n_installs = 0
                n_removes = 0
                for line in lines:
                        if line.startswith("n_updates"):
                                updates = line.split(":", 1)
                                n_updates = int(updates[1]) 
                        if line.startswith("n_installs"):
                                installs = line.split(":", 1)
                                n_installs = int(installs[1]) 
                        if line.startswith("n_removes"):
                                removes = line.split(":", 1)
                                n_removes = int(removes[1])
                return_code = proc.wait()
                if debug:
                        print "return from subprocess is %d" % return_code
                self.set_last_check_time()
                if return_code == enumerations.UPDATES_AVAILABLE:
                        self.n_updates = n_updates
                        self.n_installs = n_installs
                        self.n_removes = n_removes
                        self.show_status_icon(True)
                else:
                        self.show_status_icon(False)
                self.schedule_next_check_for_checks()
                return False                                

        def create_status_icon(self):
                icon_theme = gtk.IconTheme()
                icon_theme.append_search_path(ICON_LOCATION)
                icon = gui_misc.get_icon(icon_theme, NOTIFY_ICON_NAME, 24)
                status_icon = gtk.status_icon_new_from_pixbuf(icon)
                status_icon.set_visible(False)
                status_icon.connect('activate', self.activate_status_icon)
                status_icon.connect('notify', self.notify_status_icon)
                return status_icon

        def notify_status_icon(self, status_icon, paramspec):
                if paramspec.name == "embedded" and self.status_icon.is_embedded():
                        if self.get_show_notify_message():
                                gobject.idle_add(self.show_notify_message)

        def activate_status_icon(self, status_icon):
                self.show_status_icon(False)
                gobject.spawn_async([GKSU_PATH, UPDATEMANAGER])
                if self.get_terminate_after_activate():
                        gtk.main_quit()
                        sys.exit(0)
                else:
                        self.schedule_next_check_for_checks()

        def show_notify_message(self):
                if self.notify == None:
                        if pynotify.init("UpdateManager"):
                                notify_fmt = _("Updates available\n"
                                    "%(updates)s %(installs)s %(removes)s")
                                notify_str = self.__set_updates_str(notify_fmt)
                                notify_str += _("\nPlease click on icon to update.")
                                self.notify = pynotify.Notification(\
                                    _("Update Manager"), notify_str)

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

        def schedule_next_check_for_checks(self):
                """This schedules the next time to wake up to check if it's
                necessary to check for updates yet."""
                if self.time_until_next_check <= 0:
                        next_check_time = self.get_delta_for_refresh_period()
                else:
                        next_check_time = self.time_until_next_check
                if debug == True:
                        print "scheduling next check: %s" % next_check_time
                self.timeout_id = gobject.timeout_add(int(next_check_time * 1000),
                    self.do_next_check)

        def do_next_check(self):
                self.timeout_id = 0
                if debug == True:
                        print "Called do_next_check"
                        print "time for check: %f - %f \n" % (time.time(), \
                                self.last_check_time)
                if self.is_check_required():
                        self.schedule_check_for_updates()
                else:
                        self.schedule_next_check_for_checks()
                return False

        @staticmethod
        def check_already_running():
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
                        print _("Another instance of UpdateManagerNotify is running")
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
