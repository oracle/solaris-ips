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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
#

import sys
import os
import re
try:
        import gobject
        import pango
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc

REGEX_BOLD_MARKUP = re.compile(r'^<b>')
REGEX_STRIP_MARKUP = re.compile(r'<.*?>')

class PMLogging:
        def __init__(self, builder, window_icon):
                self.w_view_log_dialog = builder.get_object("view_log_dialog")
                self.w_view_log_dialog.set_icon(window_icon)
                self.w_view_log_dialog.set_title(_("Logs"))
                self.w_log_info_textview = builder.get_object("log_info_textview")
                self.w_log_errors_textview = builder.get_object("log_errors_textview")

                infobuffer = self.w_log_info_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)          
                infobuffer = self.w_log_errors_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)          
                self.w_log_close_button = builder.get_object("log_close_button")
                self.w_log_clear_button = builder.get_object("log_clear_button")

        def set_window_icon(self, window_icon):
                self.w_view_log_dialog.set_icon(window_icon)

        def setup_signals(self):
                signals_table = [
                    (self.w_log_close_button, "clicked",
                     self.__on_log_close_button_clicked),
                    (self.w_log_clear_button, "clicked",
                     self.__on_log_clear_button_clicked),
                    (self.w_view_log_dialog, "delete_event",
                     self.__on_log_dialog_delete_event)
                    ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def set_modal_and_transient(self, parent_window):
                gui_misc.set_modal_and_transient(self.w_view_log_dialog,
                    parent_window)

        def __on_log_dialog_delete_event(self, widget, event):
                self.__on_log_close_button_clicked(None)
                return True

        def __on_log_close_button_clicked(self, widget):
                self.w_view_log_dialog.hide()

        def __on_log_clear_button_clicked(self, widget):
                log_dir = gui_misc.get_log_dir()
                ext = gui_misc.get_log_error_ext()
                self.__clear_logs(log_dir, ext) 
                ext = gui_misc.get_log_info_ext()
                self.__clear_logs(log_dir, ext) 
                gui_misc.shutdown_logging()
                gui_misc.setup_logging()
                self.log_activate()

        def __clear_logs(self, log_dir, ext):
                self.__clear_log(os.path.join(log_dir, gui_misc.get_pm_name() + ext))
                self.__clear_log(os.path.join(log_dir, gui_misc.get_wi_name() + ext))
                self.__clear_log(os.path.join(log_dir, gui_misc.get_um_name() + ext))

        @staticmethod
        def __clear_log(path):
                try:
                        os.unlink(path)
                except OSError:
                        pass

        def log_activate(self):
                textbuffer = self.w_log_errors_textview.get_buffer()
                textbuffer.set_text(_("Loading ..."))
                textbuffer = self.w_log_info_textview.get_buffer()
                textbuffer.set_text(_("Loading ..."))
                self.w_log_close_button.grab_focus()
                self.w_view_log_dialog.show()
                gobject.idle_add(self.__load_err_view_log)
                gobject.idle_add(self.__load_info_view_log)

        def __load_err_view_log(self):
                textbuffer = self.w_log_errors_textview.get_buffer()
                textbuffer.set_text("")
                textiter = textbuffer.get_end_iter()
                log_dir = gui_misc.get_log_dir()
                log_err_ext = gui_misc.get_log_error_ext()
                pm_err_log = os.path.join(log_dir, gui_misc.get_pm_name() + log_err_ext)
                wi_err_log = os.path.join(log_dir, gui_misc.get_wi_name() + log_err_ext)
                um_err_log = os.path.join(log_dir, gui_misc.get_um_name() + log_err_ext)

                self.__write_to_view_log(um_err_log,
                    textbuffer, textiter, _("None: ") + gui_misc.get_um_name() + "\n")
                self.__write_to_view_log(wi_err_log,
                    textbuffer, textiter, _("None: ") + gui_misc.get_wi_name() + "\n")
                self.__write_to_view_log(pm_err_log,
                    textbuffer, textiter, _("None: ") + gui_misc.get_pm_name() + "\n")
                gobject.idle_add(self.w_log_errors_textview.scroll_to_iter, textiter,
                    0.0)

        def __load_info_view_log(self):
                textbuffer = self.w_log_info_textview.get_buffer()
                textbuffer.set_text("")
                textiter = textbuffer.get_end_iter()
                log_dir = gui_misc.get_log_dir()
                log_info_ext = gui_misc.get_log_info_ext()
                pm_info_log = os.path.join(log_dir, gui_misc.get_pm_name() + log_info_ext)
                wi_info_log = os.path.join(log_dir, gui_misc.get_wi_name() + log_info_ext)
                um_info_log = os.path.join(log_dir, gui_misc.get_um_name() + log_info_ext)

                self.__write_to_view_log(um_info_log,
                    textbuffer, textiter, _("None: ") + gui_misc.get_um_name() + "\n")
                self.__write_to_view_log(wi_info_log,
                    textbuffer, textiter, _("None: ") + gui_misc.get_wi_name() + "\n")
                self.__write_to_view_log(pm_info_log,
                    textbuffer, textiter, _("None: ") + gui_misc.get_pm_name() + "\n")
                gobject.idle_add(self.w_log_info_textview.scroll_to_iter, textiter, 0.0)

        @staticmethod
        def __write_to_view_log(path, textbuffer, textiter, nomessages):
                infile = None
                try:
                        infile = open(path, "r")
                except IOError:
                        textbuffer.insert_with_tags_by_name(textiter, nomessages, "bold")
                        return
                if infile == None:
                        textbuffer.insert_with_tags_by_name(textiter, nomessages, "bold")
                        return

                lines = infile.readlines()
                if len(lines) == 0:
                        textbuffer.insert_with_tags_by_name(textiter, nomessages, "bold")
                        return
                for line in lines:
                        if re.match(REGEX_BOLD_MARKUP, line):
                                line = re.sub(REGEX_STRIP_MARKUP, "", line)
                                textbuffer.insert_with_tags_by_name(textiter, line,
                                    "bold")
                        else:
                                textbuffer.insert(textiter, line)
                try:
                        infile.close()
                except IOError:
                        pass
