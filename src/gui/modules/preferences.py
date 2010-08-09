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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import pkg.gui.misc as gui_misc

class Preferences:
        def __init__(self, builder, window_icon, gconf):
                self.gconf = gconf
                self.w_preferencesdialog = \
                    builder.get_object("preferencesdialog")
                self.w_preferencesdialog.set_icon(window_icon)
                self.w_startpage_checkbutton = \
                    builder.get_object("startpage_checkbutton")
                self.w_exit_checkbutton = \
                    builder.get_object("exit_checkbutton")
                self.w_confirm_updateall_checkbutton = \
                    builder.get_object("confirm_updateall_checkbutton")
                self.w_confirm_install_checkbutton = \
                    builder.get_object("confirm_install_checkbutton")
                self.w_confirm_remove_checkbutton = \
                    builder.get_object("confirm_remove_checkbutton")
                self.w_help_button = builder.get_object("preferenceshelp")
                self.w_close_button = builder.get_object("preferencesclose")

        def set_window_icon(self, window_icon):
                self.w_preferencesdialog.set_icon(window_icon)

        def setup_signals(self):
                signals_table = [
                    (self.w_preferencesdialog, "delete_event",
                     self.__on_preferencesdialog_delete_event),
                    (self.w_startpage_checkbutton, "toggled",
                     self.__on_startpage_checkbutton_toggled),
                    (self.w_exit_checkbutton, "toggled",
                     self.__on_exit_checkbutton_toggled),
                    (self.w_confirm_updateall_checkbutton, "toggled",
                     self.on_confirm_updateall_checkbutton_toggled),
                    (self.w_confirm_install_checkbutton, "toggled",
                     self.on_confirm_install_checkbutton_toggled),
                    (self.w_confirm_remove_checkbutton, "toggled",
                     self.on_confirm_remove_checkbutton_toggled),
                    (self.w_help_button, "clicked",
                     self.__on_preferenceshelp_clicked),
                    (self.w_close_button, "clicked",
                     self.__on_preferencesclose_clicked),
                    ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def set_modal_and_transient(self, parent_window):
                gui_misc.set_modal_and_transient(self.w_preferencesdialog,
                    parent_window)

        def __on_preferencesdialog_delete_event(self, widget, event):
                self.__on_preferencesclose_clicked(None)
                return True

        def __on_preferencesclose_clicked(self, widget):
                self.w_preferencesdialog.hide()

        @staticmethod
        def __on_preferenceshelp_clicked(widget):
                gui_misc.display_help("pkg-mgr-prefs")

        def __on_startpage_checkbutton_toggled(self, widget):
                self.gconf.set_show_startpage(
                    self.w_startpage_checkbutton.get_active())

        def __on_exit_checkbutton_toggled(self, widget):
                self.gconf.set_save_state(
                    self.w_exit_checkbutton.get_active())

        def on_confirm_updateall_checkbutton_toggled(self, widget, reverse = False):
                active = widget.get_active()
                if reverse:
                        active = not active
                self.gconf.set_show_image_update(active)

        def on_confirm_install_checkbutton_toggled(self, widget, reverse = False):
                active = widget.get_active()
                if reverse:
                        active = not active
                self.gconf.set_show_install(active)

        def on_confirm_remove_checkbutton_toggled(self, widget, reverse = False):
                active = widget.get_active()
                if reverse:
                        active = not active
                self.gconf.set_show_remove(active)

        def activate(self):
                self.w_startpage_checkbutton.set_active(self.gconf.show_startpage)
                self.w_exit_checkbutton.set_active(self.gconf.save_state)
                self.w_confirm_updateall_checkbutton.set_active(
                    self.gconf.show_image_update)
                self.w_confirm_install_checkbutton.set_active(self.gconf.show_install)
                self.w_confirm_remove_checkbutton.set_active(self.gconf.show_remove)
                self.w_preferencesdialog.show()
