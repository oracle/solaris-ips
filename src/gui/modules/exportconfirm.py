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
try:
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.client.api_errors as api_errors
import pkg.fmri as fmri
import pkg.gui.misc as gui_misc

class ExportConfirm:
        def __init__(self, gladefile, window_icon, gconf, parent):
                self.gconf = gconf
                self.parent = parent
                self.parent_window = None
                self.w_tree_confirm = gtk.glade.XML(gladefile,
                    "confirmationdialog")
                self.w_exportconfirm_dialog = \
                    self.w_tree_confirm.get_widget("confirmationdialog")
                self.w_exportconfirm_dialog.set_icon(window_icon)
                self.w_confirmok_button = self.w_tree_confirm.get_widget("ok_conf")
                self.w_confirmhelp_button = self.w_tree_confirm.get_widget("help_conf")
                self.w_confirm_textview = self.w_tree_confirm.get_widget("confirmtext")
                self.w_confirm_label = self.w_tree_confirm.get_widget("confirm_label")
                w_confirm_image = self.w_tree_confirm.get_widget("confirm_image")
                w_confirm_image.set_from_stock(gtk.STOCK_DIALOG_INFO,
                    gtk.ICON_SIZE_DND)
                self.__setup_export_selection_dialog()
                self.selected_pkgs = None

        def __setup_export_selection_dialog(self):
                infobuffer = self.w_confirm_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_exportconfirm_dialog.set_title(_("Export Selections Confirmation"))
                self.w_confirm_label.set_markup(
                    _("<b>Export the following to a Web Install .p5i file:</b>"))
                self.w_confirmhelp_button.set_property('visible', True)

        def setup_signals(self):
                dic_confirm = \
                    {
                        "on_confirmationdialog_delete_event": \
                            self.__on_confirmation_dialog_delete_event,
                        "on_help_conf_clicked": \
                            self.__on_confirm_help_button_clicked,
                        "on_ok_conf_clicked": \
                            self.__on_confirm_proceed_button_clicked,
                        "on_cancel_conf_clicked": \
                            self.__on_confirm_cancel_button_clicked,
                    }
                self.w_tree_confirm.signal_autoconnect(dic_confirm)

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
                filename = gui_misc.get_export_p5i_filename(
                    self.gconf.last_export_selection_path,
                    self.parent_window)
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
