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
# Copyright (c) 2009, 2012, Oracle and/or its affiliates. All rights reserved.
#

import pkg.gui.misc as gui_misc
import os
import pkg.misc as misc
import pkg.client.api_errors as api_errors
import pkg.client.bootenv as bootenv
from threading import Thread
import time

try:
        import gobject
        import gtk
        import pygtk
        pygtk.require("2.0")
except ImportError:
        import sys
        sys.exit(1)

VALID_BE_NAME = 0
INVALID_BE_NAME = -1
DUPLICATE_BE_NAME = -2
ACTIVATED_BE_NAME = -3          #If the be was not changed by the user
ERROR_FORMAT = "<span color = \"red\">%s</span>"

class RenameBeAfterUpdateAll:
        def __init__(self, parent, dialog_icon, parent_window):
                if not bootenv.BootEnv.libbe_exists():
                        msg = _("The <b>libbe</b> library was not "
                            "found on your system.")
                        msgbox = gtk.MessageDialog(
                            buttons = gtk.BUTTONS_CLOSE,
                            flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_INFO,
                            message_format = None)
                        msgbox.set_markup(msg)
                        msgbox.set_title(_("Rename BE"))
                        msgbox.run()
                        msgbox.destroy()
                        return

                # Before performing update all (image-update) task, we are storing
                # the active on reboot be name. If the be name after update is different
                # it means that new BE was created and we can show BE rename dialog
                # otherwise we can show update completed dialog.
                # Also we need to store original BE name to work-around the bug: 6472202
                self.active_be_before_update_all = self.__get_activated_be_name()

                self.parent = parent
                self.stop_progress_bouncing = False
                self.stopped_bouncing_progress = True
                builder = gtk.Builder()
                gladefile = os.path.join(self.parent.application_dir,
                    "usr/share/package-manager/packagemanager.ui")
                builder.add_from_file(gladefile)

                self.w_ua_completed_dialog = \
                    builder.get_object("ua_completed_dialog")
                self.w_ua_be_entry = \
                    builder.get_object("ua_be_entry")
                self.w_ua_release_notes_button = \
                    builder.get_object("release_notes_button")
                self.w_be_error_label = \
                    builder.get_object("be_error_label")
                self.w_ua_help_button = \
                    builder.get_object("ua_help_button")
                self.w_ua_restart_later_button = \
                    builder.get_object("ua_restart_later_button")
                self.w_ua_restart_now_button = \
                    builder.get_object("ua_restart_now_button")
                self.w_ua_ok_image = \
                    builder.get_object("ua_ok_image")
                self.w_ua_whats_this_button = \
                    builder.get_object("ua_whats_this_button")
                self.w_ua_whats_this_button.set_tooltip_text(_(
                    "A boot environment (BE) contains the operating\n"
                    "system image and updated packages. The\n"
                    "system will boot into the new BE on restart."))

                self.w_progress_dialog = builder.get_object("progressdialog")
                self.w_progressinfo_label = builder.get_object("progressinfo")
                self.w_progress_cancel = builder.get_object("progresscancel")
                self.w_progressbar = builder.get_object("progressbar")
                self.w_progress_dialog.connect('delete-event', lambda stub1, stub2: True)
                self.w_progress_cancel.set_sensitive(False)

                self.w_progress_dialog.set_title(_("Rename BE"))
                self.w_progressinfo_label.set_text(_("Renaming BE, please wait..."))

                self.w_progress_dialog.set_icon(dialog_icon)
                self.w_ua_completed_dialog.set_icon(dialog_icon)

                checkmark_icon = gui_misc.get_icon(
                    self.parent.icon_theme, "pm-check", 24)

                self.w_ua_ok_image.set_from_pixbuf(checkmark_icon)

                gui_misc.set_modal_and_transient(self.w_progress_dialog, parent_window)
                gui_misc.set_modal_and_transient(self.w_ua_completed_dialog,
                    parent_window)

                self.__setup_signals()

        def __setup_signals(self):
                signals_table = [
                    (self.w_ua_help_button, "clicked",
                     self.__on_ua_help_button_clicked),
                    (self.w_ua_restart_later_button, "clicked",
                     self.__on_ua_restart_later_button_clicked),
                    (self.w_ua_restart_now_button, "clicked",
                     self.__on_ua_restart_now_button_clicked),
                    (self.w_ua_completed_dialog, "delete_event",
                     self.__on_ua_completed_dialog_delete_event),
                    (self.w_ua_be_entry, "changed",
                     self.__on_ua_be_entry_changed),
                    (self.w_ua_whats_this_button, "clicked", 
                     self.__on_ua_whats_this_button_clicked),
                    ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def show_rename_dialog(self, updated_packages_list):
                '''Returns False if no BE rename is needed'''
                orig_name = self.__get_activated_be_name()
                if orig_name == self.active_be_before_update_all:
                        self.w_ua_completed_dialog.hide()
                        self.parent.update_package_list(updated_packages_list)
                        return False
                else:
                        self.__set_release_notes_url()
                        self.__setup_be_name()
                        self.w_ua_completed_dialog.show_all()
                        return True

        def __set_release_notes_url(self):
                info_url = misc.get_release_notes_url()
                if info_url and len(info_url) == 0:
                        info_url = gui_misc.RELEASE_URL
                self.w_ua_release_notes_button.set_uri(info_url)

        def __on_ua_restart_later_button_clicked(self, widget):
                self.__proceed_after_update()

        def __on_ua_restart_now_button_clicked(self, widget):
                self.__proceed_after_update(True)

        def __on_ua_whats_this_button_clicked(self, widget):
                msgbox = gtk.MessageDialog(parent = self.w_ua_completed_dialog,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL,
                    type = gtk.MESSAGE_INFO,
                    message_format = None)
                msgbox.set_property('text',
                    _(self.w_ua_whats_this_button.get_tooltip_text()))
                title = _("Update All")

                msgbox.set_title(title)
                msgbox.run()
                msgbox.destroy()

        def __on_ua_completed_dialog_delete_event(self, widget, event):
                self.__proceed_after_update()

        def __proceed_after_update(self, reboot=False):
                orig_name = self.__get_activated_be_name()
                new_name = self.w_ua_be_entry.get_text()
                Thread(target = self.__set_be_name,
                    args = (orig_name, new_name, reboot)).start()
                self.w_ua_completed_dialog.hide()

        def __set_be_name(self, orig_name, new_name, reboot):
                ret_code = self.__verify_be_name(new_name)
                be_rename_code = 0
                if ret_code != ACTIVATED_BE_NAME:
                        self.__start_bouncing_progress()
                        be_rename_code = self.__rename_be(orig_name, new_name)
                if be_rename_code != 0:
                        # Workaround for bug: 6472202
                        # If the rename didn't work for the first time, we should:
                        # - Activate current BE - active_name
                        # - Rename the BE orig_name to BE new_name
                        # - Activate the BE new_name
                        active_name = self.__get_active_be_name()
                        workaround_code = self.__workaround_for_6472202(
                            active_name, orig_name, new_name)
                        if workaround_code != 0:
                                gobject.idle_add(self.__g_be_rename_problem_dialog,
                                    new_name, orig_name)
                if reboot:
                        ret = gui_misc.restart_system()
                        if ret != 0:
                                gobject.idle_add(self.__g_be_reboot_problem_dialog)
                        else:
                                gobject.idle_add(self.parent.shutdown_after_image_update)
                self.__stop_bouncing_progress()
                gobject.idle_add(self.parent.shutdown_after_image_update, False)

        @staticmethod
        def __g_be_rename_problem_dialog(new_name, orig_name):
                msg_type = gtk.MESSAGE_INFO
                error_msg = _("Could not change the BE name to:\n\t"
                    "%s\n\nThe following name will be used instead:"
                    "\n\t%s" % (new_name, orig_name))
                msg_title = _("BE Name")
                gui_misc.error_occurred(None, error_msg, msg_title, msg_type)

        @staticmethod
        def __g_be_reboot_problem_dialog():
                msg_type = gtk.MESSAGE_ERROR
                error_msg = _("Could not restart the system."
                    "\nPlease restart the system manually.")
                msg_title = _("Restart Error")
                gui_misc.error_occurred(None, error_msg, msg_title, msg_type)

        def __on_ua_be_entry_changed(self, widget):
                if len(widget.get_text()) == 0:
                        self.w_be_error_label.hide()
                        self.__set_buttons_state(False)
                        return
                ret_code = self.__verify_be_name(widget.get_text())
                if ret_code == ACTIVATED_BE_NAME:
                        self.__set_buttons_state(True)
                        self.w_be_error_label.hide()
                elif ret_code == DUPLICATE_BE_NAME:
                        self.__set_buttons_state(False)
                        error_string = _("This name already exists.")
                        error = ERROR_FORMAT % error_string
                        self.w_be_error_label.set_markup(error)
                        self.w_be_error_label.show()
                elif ret_code == INVALID_BE_NAME:
                        self.__set_buttons_state(False)
                        error_string = _("BE name contains invalid character.")
                        error = ERROR_FORMAT % error_string
                        self.w_be_error_label.set_markup(error)
                        self.w_be_error_label.show()
                else:
                        self.__set_buttons_state(True)
                        self.w_be_error_label.hide()

        def __set_buttons_state(self, sensitive=False):
                self.w_ua_restart_later_button.set_sensitive(sensitive)
                self.w_ua_restart_now_button.set_sensitive(sensitive)

        def __setup_be_name(self):
                proposed_name = self.__get_activated_be_name()
                self.w_ua_be_entry.set_text(proposed_name)

        def __verify_be_name(self, new_name):
                try:
                        bootenv.BootEnv.check_be_name(new_name)
                except api_errors.DuplicateBEName:
                        if new_name == self.__get_activated_be_name():
                                return ACTIVATED_BE_NAME
                        else:
                                return DUPLICATE_BE_NAME
                except api_errors.ApiException:
                        return INVALID_BE_NAME
                return VALID_BE_NAME

        @staticmethod
        def __get_activated_be_name():
                try:
                        name = bootenv.BootEnv.get_activated_be_name()
                except api_errors.ApiException:
                        name = ""
                return name

        @staticmethod
        def __get_active_be_name():
                try:
                        name = bootenv.BootEnv.get_active_be_name()
                except api_errors.ApiException:
                        name = ""
                return name

        def __start_bouncing_progress(self):
                self.stop_progress_bouncing = False
                self.stopped_bouncing_progress = False
                gobject.idle_add(self.w_progress_dialog.show)
                Thread(target =
                    self.__g_progressdialog_progress_pulse).start()

        def __stop_bouncing_progress(self):
                if self.__is_progress_bouncing():
                        self.stop_progress_bouncing = True

        def __g_progressdialog_progress_pulse(self):
                while not self.stop_progress_bouncing:
                        gobject.idle_add(self.w_progressbar.pulse)
                        time.sleep(0.1)
                self.stopped_bouncing_progress = True
                gobject.idle_add(self.w_progress_dialog.hide)

        def __is_progress_bouncing(self):
                return not self.stopped_bouncing_progress

        @staticmethod
        def __rename_be(orig_name, new_name):
                # The rename operation is i/o intensive, so the gui
                # progress is not responsive. This will allow to show the
                # gui progress.
                time.sleep(0.2)
                return bootenv.BootEnv.rename_be(orig_name, new_name)

        @staticmethod
        def __workaround_for_6472202(active_name, orig_name, new_name):
                ret_code = 0
                ret_code = bootenv.BootEnv.set_default_be(active_name)
                if ret_code == 0:
                        ret_code = bootenv.BootEnv.rename_be(orig_name, new_name)
                if ret_code == 0:
                        ret_code = bootenv.BootEnv.set_default_be(new_name)
                else:
                        bootenv.BootEnv.set_default_be(orig_name)
                return ret_code

        @staticmethod
        def __on_ua_help_button_clicked(widget):
                gui_misc.display_help("um_info")
