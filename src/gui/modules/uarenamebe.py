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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import pkg.gui.misc as gui_misc
import os
import pkg.misc as misc
from threading import Thread
import time

try:
        import gobject
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        import sys
        sys.exit(1)

try:
        import libbe as be
        nobe = False
except ImportError:
        # All actions are disabled when libbe can't be imported. 
        nobe = True

VALID_BE_NAME = 0
INVALID_BE_NAME = -1
DUPLICATE_BE_NAME = -2
ACTIVATED_BE_NAME = -3          #If the be was not changed by the user
ERROR_FORMAT = "<span color = \"red\">%s</span>"

class RenameBeAfterUpdateAll:
        def __init__(self, parent, dialog_icon, parent_window):
                if nobe:
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
                self.updated_packages_list = None
                self.stop_progress_bouncing = False
                self.stopped_bouncing_progress = True
                gladefile = os.path.join(self.parent.application_dir,
                    "usr/share/package-manager/packagemanager.glade")
                w_tree_ua_completed = \
                    gtk.glade.XML(gladefile, "ua_completed_dialog")
                w_xmltree_progress = gtk.glade.XML(gladefile, "progressdialog")

                self.w_ua_completed_dialog = \
                    w_tree_ua_completed.get_widget("ua_completed_dialog")
                self.w_ua_be_entry = \
                    w_tree_ua_completed.get_widget("ua_be_entry")
                self.w_ua_release_notes_button = \
                    w_tree_ua_completed.get_widget("ua_release_notes_button")
                self.w_be_error_label = \
                    w_tree_ua_completed.get_widget("be_error_label")
                self.w_ua_restart_later_button = \
                    w_tree_ua_completed.get_widget("ua_restart_later_button")
                self.w_ua_restart_now_button = \
                    w_tree_ua_completed.get_widget("ua_restart_now_button")
                self.w_ua_ok_image = \
                    w_tree_ua_completed.get_widget("ua_ok_image")

                self.w_progress_dialog = w_xmltree_progress.get_widget("progressdialog")
                self.w_progressinfo_label = w_xmltree_progress.get_widget("progressinfo")
                self.w_progress_cancel = w_xmltree_progress.get_widget("progresscancel")
                self.w_progressbar = w_xmltree_progress.get_widget("progressbar")
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

                try:
                        dic_be_rename = \
                            {
                                "on_ua_help_button_clicked" : \
                                    self.__on_ua_help_button_clicked,
                                "on_ua_restart_later_button_clicked" : \
                                    self.__on_ua_restart_later_button_clicked,
                                "on_ua_restart_now_button_clicked" : \
                                    self.__on_ua_restart_now_button_clicked,
                                "on_ua_dialog_close" : \
                                    self.__on_ua_dialog_close,
                                "on_ua_completed_dialog_delete_event" : \
                                    self.__on_ua_completed_dialog_delete_event,
                                "on_ua_be_entry_changed" : \
                                    self.__on_ua_be_entry_changed,
                            }
                        w_tree_ua_completed.signal_autoconnect(dic_be_rename)
                except AttributeError, error:
                        print _(
                            "GUI will not respond to any event! %s. "
                            "Check declare_signals()") \
                            % error

        def show_rename_dialog(self, updated_packages_list):
                '''Returns False if no BE rename is needed'''
                self.updated_packages_list = updated_packages_list
                self.__set_release_notes_url()
                self.__setup_be_list()
                orig_name = self.__get_activated_be_name()
                if orig_name == self.active_be_before_update_all:
                        self.w_ua_completed_dialog.hide()
                        self.parent.update_package_list(self.updated_packages_list)
                        return False
                else:
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

        def __on_ua_dialog_close(self, widget):
                self.__proceed_after_update()

        @staticmethod
        def __on_ua_completed_dialog_delete_event(widget, event):
                return True

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
                else:
                        gobject.idle_add(self.parent.update_package_list,
                            self.updated_packages_list)
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

        def __setup_be_list(self):
                be_list = self.__get_be_list()
                proposed_name = ""
                for bee in be_list:
                        if bee.get("active_boot"):
                                proposed_name = bee.get("orig_be_name")
                self.w_ua_be_entry.set_text(proposed_name)

        def __verify_be_name(self, new_name):
                be_list = self.__get_be_list()
                for bee in be_list:
                        name = bee.get("orig_be_name")
                        if name == new_name:
                                active_boot = bee.get("active_boot")
                                if name == new_name \
                                    and active_boot == False:
                                        return DUPLICATE_BE_NAME
                                elif active_boot:
                                        return ACTIVATED_BE_NAME
                if be.beVerifyBEName(new_name) != VALID_BE_NAME:
                        return INVALID_BE_NAME
                return VALID_BE_NAME

        def __get_activated_be_name(self):
                be_list = self.__get_be_list()
                for bee in be_list:
                        name = bee.get("orig_be_name")
                        active_boot = bee.get("active_boot")
                        if active_boot:
                                return name

        def __get_active_be_name(self):
                be_list = self.__get_be_list()
                for bee in be_list:
                        name = bee.get("orig_be_name")
                        active_boot = bee.get("active")
                        if active_boot:
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
        def __get_be_list():
                be_list_vals = be.beList()
                be_list = None
                if isinstance(be_list_vals[0], int):
                        be_list = be_list_vals[1]
                else:
                        be_list = be_list_vals
                return be_list

        @staticmethod
        def __rename_be(orig_name, new_name):
                # The rename operation is i/o intensive, so the gui
                # progress is not responsive. This will allow to show the
                # gui progress.
                time.sleep(0.2)
                return be.beRename(orig_name, new_name)

        @staticmethod
        def __workaround_for_6472202(active_name, orig_name, new_name):
                ret_code = 0
                ret_code = be.beActivate(active_name)
                if ret_code == 0:
                        ret_code = be.beRename(orig_name, new_name)
                if ret_code == 0:
                        ret_code = be.beActivate(new_name)
                else:
                        be.beActivate(orig_name)
                return ret_code

        @staticmethod
        def __on_ua_help_button_clicked(widget):
                gui_misc.display_help("intro_be")
