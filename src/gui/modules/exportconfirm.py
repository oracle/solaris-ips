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

import sys
import os
import stat
import tempfile
import re
try:
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.client.api_errors as api_errors
import pkg.fmri as fmri
import pkg.gui.misc as gui_misc

class ExportConfirm:
        def __init__(self, builder, window_icon, gconf, parent):
                self.gconf = gconf
                self.parent = parent
                self.parent_window = None
                self.window_icon = window_icon
                self.w_exportconfirm_dialog = \
                    builder.get_object("confirmationdialog")
                self.w_exportconfirm_dialog.set_icon(window_icon)
                self.w_confirmok_button = builder.get_object("ok_conf")
                self.w_confirmcancel_button = builder.get_object("cancel_conf")
                self.w_confirmhelp_button = builder.get_object("help_conf")
                self.w_confirm_textview = builder.get_object("confirmtext")
                self.w_confirm_label = builder.get_object("confirm_label")
                w_confirm_image = builder.get_object("confirm_image")
                w_confirm_image.set_from_stock(gtk.STOCK_DIALOG_INFO,
                    gtk.ICON_SIZE_DND)
                self.__setup_export_selection_dialog()
                self.selected_pkgs = None
                self.chooser_dialog = None

        def set_window_icon(self, window_icon):
                self.window_icon = window_icon
                self.w_exportconfirm_dialog.set_icon(window_icon)
                if self.chooser_dialog:
                        self.chooser_dialog.set_icon(window_icon)

        def __setup_export_selection_dialog(self):
                infobuffer = self.w_confirm_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_exportconfirm_dialog.set_title(_("Export Selections Confirmation"))
                self.w_confirm_label.set_markup(
                    _("<b>Export the following to a Web Install .p5i file:</b>"))
                self.w_confirmhelp_button.set_property('visible', True)

        def setup_signals(self):
                signals_table = [
                    (self.w_exportconfirm_dialog, "delete_event",
                     self.__on_confirmation_dialog_delete_event),
                    (self.w_confirmhelp_button, "clicked",
                     self.__on_confirm_help_button_clicked),
                    (self.w_confirmok_button, "clicked",
                     self.__on_confirm_proceed_button_clicked),
                    (self.w_confirmcancel_button, "clicked",
                     self.__on_confirm_cancel_button_clicked),
                    ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def set_modal_and_transient(self, parent_window):
                self.parent_window = parent_window
                gui_misc.set_modal_and_transient(self.w_exportconfirm_dialog,
                    parent_window)

        def __on_confirmation_dialog_delete_event(self, widget, event):
                self.__on_confirm_cancel_button_clicked(None)
                return True

        @staticmethod
        def __on_confirm_help_button_clicked(widget):
                gui_misc.display_help("webinstall-export")

        def __on_confirm_cancel_button_clicked(self, widget):
                self.w_exportconfirm_dialog.hide()

        def __on_confirm_proceed_button_clicked(self, widget):
                self.w_exportconfirm_dialog.hide()
                self.__export_selections()

        def activate(self, selected_pkgs):
                self.selected_pkgs = selected_pkgs
                if self.selected_pkgs == None or len(self.selected_pkgs) == 0:
                        return

                infobuffer = self.w_confirm_textview.get_buffer()
                infobuffer.set_text("")
                textiter = infobuffer.get_end_iter()

                for pub_name, pkgs in self.selected_pkgs.items():
                        name = self.parent.get_publisher_name_from_prefix(pub_name)
                        if name == pub_name:
                                infobuffer.insert_with_tags_by_name(textiter,
                                    "%s\n" % pub_name, "bold")
                        else:
                                infobuffer.insert_with_tags_by_name(textiter,
                                    "%s" % name, "bold")
                                infobuffer.insert(textiter, " (%s)\n" % pub_name)
                        for pkg in pkgs.keys():
                                infobuffer.insert(textiter,
                                    "\t%s\n" % fmri.extract_pkg_name(pkg))
                self.w_confirmok_button.grab_focus()
                self.w_exportconfirm_dialog.show()

        def __export_selections(self):
                filename = self.__get_export_p5i_filename(
                    self.gconf.last_export_selection_path)
                if not filename:
                        return
                self.gconf.last_export_selection_path = filename
                try:
                        fobj = open(filename, 'w')
                        api_o = self.parent.get_api_object()
                        api_o.write_p5i(fobj, pkg_names=self.selected_pkgs,
                            pubs=self.selected_pkgs.keys())
                except IOError, ex:
                        err = str(ex)
                        self.parent.error_occurred(err, _("Export Selections Error"))
                        return
                except api_errors.ApiException, ex:
                        fobj.close()
                        err = str(ex)
                        self.parent.error_occurred(err, _("Export Selections Error"))
                        return
                fobj.close()
                os.chmod(filename, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP |
                    stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH )

        def __get_export_p5i_filename(self, last_export_selection_path):
                filename = None
                chooser = gtk.FileChooserDialog(_("Export Selections"),
                    self.parent_window,
                    gtk.FILE_CHOOSER_ACTION_SAVE,
                    (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_SAVE, gtk.RESPONSE_OK))
                chooser.set_icon(self.window_icon)
                self.chooser_dialog = chooser

                file_filter = gtk.FileFilter()
                file_filter.set_name(_("p5i Files"))
                file_filter.add_pattern("*.p5i")
                chooser.add_filter(file_filter)
                file_filter = gtk.FileFilter()
                file_filter.set_name(_("All Files"))
                file_filter.add_pattern("*")
                chooser.add_filter(file_filter)

                path = tempfile.gettempdir()
                name = _("my_packages")
                if last_export_selection_path and last_export_selection_path != "":
                        path, name_plus_ext = os.path.split(last_export_selection_path)
                        result = os.path.splitext(name_plus_ext)
                        name = result[0]

                #Check name
                base_name = None
                m = re.match("(.*)(-\d+)$", name)
                if m == None and os.path.exists(path + os.sep + name + '.p5i'):
                        base_name = name
                if m and len(m.groups()) == 2:
                        base_name = m.group(1)
                name = name + '.p5i'
                if base_name:
                        for i in range(1, 99):
                                full_path = path + os.sep + base_name + '-' + \
                                    str(i) + '.p5i'
                                if not os.path.exists(full_path):
                                        name = base_name + '-' + str(i) + '.p5i'
                                        break
                chooser.set_current_folder(path)
                chooser.set_current_name(name)
                chooser.set_do_overwrite_confirmation(True)

                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        filename = chooser.get_filename()
                self.chooser_dialog = None
                chooser.destroy()

                return filename
