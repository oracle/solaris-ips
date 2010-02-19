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

MODIFY_DIALOG_WIDTH_DEFAULT = 500
MODIFY_DIALOG_SSL_WIDTH_DEFAULT = 410

import sys
import os
import pango
from threading import Thread
from gettext import ngettext

try:
        import gobject
        gobject.threads_init()
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)

import pkg.client.publisher as publisher
import pkg.client.api_errors as api_errors
import pkg.misc as misc
import pkg.gui.enumerations as enumerations
import pkg.gui.misc as gui_misc
import pkg.gui.progress as progress
from pkg.client import global_settings

logger = global_settings.logger

ERROR_FORMAT = "<span color = \"red\">%s</span>"

class Repository(progress.GuiProgressTracker):
        def __init__(self, parent, image_directory,
            action = -1, webinstall_new = False, main_window = None):
                progress.GuiProgressTracker.__init__(self)
                self.parent = parent
                self.action = action
                self.main_window = main_window
                self.api_o = gui_misc.get_api_object(image_directory,
                    self, main_window)
                if self.api_o == None:
                        return
                self.webinstall_new = webinstall_new
                self.progress_stop_thread = False
                self.repository_selection = None
                self.cancel_progress_thread = False
                self.cancel_function = None
                self.is_name_valid = False
                self.is_url_valid = False
                self.priority_changes = []
                self.url_err = None
                self.name_error = None
                self.publisher_info = _("e.g. http://pkg.opensolaris.org/release")
                self.publishers_list = None
                self.repository_modify_publisher = None
                self.no_changes = 0
                self.pylintstub = None
                w_tree_add_publisher = \
                    gtk.glade.XML(parent.gladefile, "add_publisher")
                w_tree_add_publisher_complete = \
                    gtk.glade.XML(parent.gladefile, "add_publisher_complete")
                w_tree_modify_repository = \
                    gtk.glade.XML(parent.gladefile, "modify_repository")
                w_tree_manage_publishers = \
                    gtk.glade.XML(parent.gladefile, "manage_publishers")
                w_tree_publishers_apply = \
                    gtk.glade.XML(parent.gladefile, "publishers_apply")
                # Dialog reused in the beadmin.py
                w_tree_confirmation = gtk.glade.XML(parent.gladefile,
                    "confirmationdialog")
                self.w_confirmation_dialog =  \
                    w_tree_confirmation.get_widget("confirmationdialog")
                self.w_confirmation_label = \
                    w_tree_confirmation.get_widget("confirm_label")
                self.w_confirmation_dialog.set_icon(self.parent.window_icon)
                self.w_confirmation_textview = \
                    w_tree_confirmation.get_widget("confirmtext")
                self.w_confirm_cancel_btn = w_tree_confirmation.get_widget("cancel_conf")
                confirmbuffer = self.w_confirmation_textview.get_buffer()
                confirmbuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_confirmation_dialog.set_title(
                    _("Manage Publishers Confirmation"))
                self.w_publishers_treeview = \
                    w_tree_manage_publishers.get_widget("publishers_treeview")
                self.w_add_publisher_dialog = \
                    w_tree_add_publisher.get_widget("add_publisher")
                self.w_add_publisher_dialog.set_icon(self.parent.window_icon)
                self.w_add_error_label = \
                    w_tree_add_publisher.get_widget("add_error_label")
                self.w_add_sslerror_label = \
                    w_tree_add_publisher.get_widget("add_sslerror_label")
                self.w_publisher_add_button = \
                    w_tree_add_publisher.get_widget("add_button")
                self.w_ssl_box = \
                    w_tree_add_publisher.get_widget("ssl_box")
                self.w_add_publisher_name = \
                    w_tree_add_publisher.get_widget("add_publisher_name")
                self.w_add_pub_label = \
                    w_tree_add_publisher.get_widget("add_pub_label")
                self.w_add_pub_instr_label = \
                    w_tree_add_publisher.get_widget("add_pub_instr_label")
                self.w_add_publisher_url = \
                    w_tree_add_publisher.get_widget("add_publisher_url")
                self.w_cert_entry = \
                    w_tree_add_publisher.get_widget("certentry")
                self.w_key_entry = \
                    w_tree_add_publisher.get_widget("keyentry")
                self.w_publisher_add_button.set_sensitive(False)
                self.w_add_publisher_comp_dialog = \
                    w_tree_add_publisher_complete.get_widget("add_publisher_complete")
                self.w_add_image = \
                    w_tree_add_publisher_complete.get_widget("add_image")
                self.w_add_publisher_comp_dialog.set_icon(self.parent.window_icon)
                self.w_add_publisher_c_name = \
                    w_tree_add_publisher_complete.get_widget("add_publisher_name")
                self.w_add_publisher_c_url = \
                    w_tree_add_publisher_complete.get_widget("add_publisher_url")
                self.w_add_publisher_c_desc = \
                    w_tree_add_publisher_complete.get_widget("add_publisher_desc")
                self.w_add_publisher_c_desc_l = \
                    w_tree_add_publisher_complete.get_widget("add_publisher_desc_l")
                self.w_registration_box = \
                    w_tree_add_publisher.get_widget("registration_box")
                self.w_registration_link = \
                    w_tree_add_publisher.get_widget("registration_button")
                self.w_modify_repository_dialog = \
                    w_tree_modify_repository.get_widget("modify_repository")
                self.w_modify_repository_dialog.set_icon(self.parent.window_icon)
                self.w_addmirror_entry = \
                    w_tree_modify_repository.get_widget("addmirror_entry")
                self.w_addorigin_entry = \
                    w_tree_modify_repository.get_widget("add_repo")
                self.w_addmirror_button = \
                    w_tree_modify_repository.get_widget("addmirror_button")
                self.w_rmmirror_button = \
                    w_tree_modify_repository.get_widget("mirrorremove")
                self.w_addorigin_button = \
                    w_tree_modify_repository.get_widget("pub_add_repo")
                self.w_rmorigin_button = \
                    w_tree_modify_repository.get_widget("pub_remove_repo")
                self.w_modify_pub_alias = \
                    w_tree_modify_repository.get_widget("repositorymodifyalias")
                self.w_repositorymodifyok_button = \
                    w_tree_modify_repository.get_widget("repositorymodifyok")
                self.modify_repo_mirrors_treeview = \
                    w_tree_modify_repository.get_widget("modify_repo_mirrors_treeview")
                self.modify_repo_origins_treeview = \
                    w_tree_modify_repository.get_widget("modify_pub_repos_treeview")
                self.w_modmirrerror_label = \
                    w_tree_modify_repository.get_widget("modmirrerror_label")
                self.w_modoriginerror_label = \
                    w_tree_modify_repository.get_widget("modrepoerror_label")
                self.w_modsslerror_label = \
                    w_tree_modify_repository.get_widget("modsslerror_label")
                self.w_repositorymodify_name = \
                    w_tree_modify_repository.get_widget("repository_name_label")
                self.w_repositorymodify_registration_link = \
                    w_tree_modify_repository.get_widget(
                    "repositorymodifyregistrationlinkbutton")
                self.w_repositoryssl_expander = \
                    w_tree_modify_repository.get_widget(
                    "repositorymodifysslexpander")
                self.w_repositorymirror_expander = \
                    w_tree_modify_repository.get_widget(
                    "repositorymodifymirrorsexpander")
                self.w_repositorymodify_registration_box = \
                    w_tree_modify_repository.get_widget(
                    "registration_box")   
                self.w_repositorymodify_key_entry = \
                    w_tree_modify_repository.get_widget(
                    "modkeyentry")   
                self.w_repositorymodify_cert_entry = \
                    w_tree_modify_repository.get_widget(
                    "modcertentry")   
                self.w_manage_publishers_dialog = \
                    w_tree_manage_publishers.get_widget("manage_publishers")
                self.w_manage_publishers_dialog.set_icon(self.parent.window_icon)
                self.w_manage_publishers_details = \
                    w_tree_manage_publishers.get_widget("manage_publishers_details")
                manage_pub_details_buf =  self.w_manage_publishers_details.get_buffer()
                manage_pub_details_buf.create_tag("level0", weight=pango.WEIGHT_BOLD)
                self.w_manage_ok_btn = \
                    w_tree_manage_publishers.get_widget("manage_ok")
                self.w_manage_remove_btn = \
                    w_tree_manage_publishers.get_widget("manage_remove")
                self.w_manage_modify_btn = \
                    w_tree_manage_publishers.get_widget("manage_modify")
                self.w_manage_up_btn = \
                    w_tree_manage_publishers.get_widget("manage_move_up")
                self.w_manage_down_btn = \
                    w_tree_manage_publishers.get_widget("manage_move_down")
                self.publishers_apply = \
                    w_tree_publishers_apply.get_widget("publishers_apply")
                self.publishers_apply.set_icon(self.parent.window_icon)
                self.publishers_apply_expander = \
                    w_tree_publishers_apply.get_widget("apply_expander")
                self.publishers_apply_textview = \
                    w_tree_publishers_apply.get_widget("apply_textview")
                applybuffer = self.publishers_apply_textview.get_buffer()
                applybuffer.create_tag("level1", left_margin=30, right_margin=10)
                self.publishers_apply_cancel = \
                    w_tree_publishers_apply.get_widget("apply_cancel")
                self.publishers_apply_progress = \
                    w_tree_publishers_apply.get_widget("publishers_apply_progress")

                checkmark_icon = gui_misc.get_icon(
                    self.parent.icon_theme, "pm-check", 24)

                self.w_add_image.set_from_pixbuf(checkmark_icon)

                try:
                        dic_add_publisher = \
                            {
                                "on_add_publisher_delete_event" : \
                                    self.__on_add_publisher_delete_event,
                                "on_publisherurl_changed": \
                                    self.__on_publisherurl_changed,
                                "on_publishername_changed": \
                                    self.__on_publishername_changed,
                                "on_keyentry_changed": \
                                    self.__on_keyentry_changed,
                                "on_certentry_changed": \
                                    self.__on_certentry_changed,
                                "on_add_publisher_add_clicked" : \
                                    self.__on_add_publisher_add_clicked,
                                "on_add_publisher_cancel_clicked" : \
                                    self.__on_add_publisher_cancel_clicked,
                                "on_keybrowse_clicked": \
                                    self.__on_keybrowse_clicked,
                                "on_certbrowse_clicked": \
                                    self.__on_certbrowse_clicked,
                                "on_add_pub_help_clicked": \
                                    self.__on_add_pub_help_clicked,
                            }
                        dic_add_publisher_comp = \
                            {
                                "on_add_publisher_complete_delete_event" : \
                                    self.__on_add_publisher_complete_delete_event,
                                "on_add_publisher_c_close_clicked" : \
                                    self.__on_add_publisher_c_close_clicked,
                            }
                        dic_manage_publishers = \
                            {
                                "on_manage_publishers_delete_event" : \
                                    self.__on_manage_publishers_delete_event,
                                "on_manage_add_clicked" : \
                                    self.__on_manage_add_clicked,
                                "on_manage_modify_clicked" : \
                                    self.__on_manage_modify_clicked,
                                "on_manage_remove_clicked" : \
                                    self.__on_manage_remove_clicked,
                                "on_manage_move_up_clicked" : \
                                    self.__on_manage_move_up_clicked,
                                "on_manage_move_down_clicked" : \
                                    self.__on_manage_move_down_clicked,
                                "on_manage_cancel_clicked" : \
                                    self.__on_manage_cancel_clicked,
                                "on_manage_ok_clicked" : \
                                    self.__on_manage_ok_clicked,
                                "on_manage_help_clicked": \
                                    self.__on_manage_help_clicked,
                            }
                        dic_modify_repo = \
                            {
                                "on_modify_repository_delete_event": \
                                    self.__delete_widget_handler_hide,
                                "on_modkeybrowse_clicked": \
                                    self.__on_modkeybrowse_clicked,
                                "on_modcertbrowse_clicked": \
                                    self.__on_modcertbrowse_clicked,
                                "on_addmirror_entry_changed": \
                                    self.__on_addmirror_entry_changed,
                                "on_add_repo_changed": \
                                    self.__on_addorigin_entry_changed,
                                "on_addmirror_button_clicked": \
                                    self.__on_addmirror_button_clicked,
                                "on_pub_add_repo_clicked": \
                                    self.__on_addorigin_button_clicked,
                                "on_repositorymodifyok_clicked": \
                                    self.__on_repositorymodifyok_clicked,
                                "on_mirrorremove_clicked": \
                                    self.__on_rmmirror_button_clicked,
                                "on_pub_remove_repo_clicked": \
                                    self.__on_rmorigin_button_clicked,
                                "on_repositorymodifycancel_clicked": \
                                    self.__on_repositorymodifycancel_clicked,
                                "on_modkeyentry_changed": \
                                    self.__on_modcertkeyentry_changed,
                                "on_modcertentry_changed": \
                                    self.__on_modcertkeyentry_changed,
                                "on_modify_repo_help_clicked": \
                                    self.__on_modify_repo_help_clicked,
                            }
                        dic_confirmation = \
                            {
                                "on_cancel_conf_clicked": \
                                    self.__on_cancel_conf_clicked,
                                "on_ok_conf_clicked": \
                                    self.__on_ok_conf_clicked,
                                "on_confirmationdialog_delete_event": \
                                    self.__delete_widget_handler_hide,
                            }
                        dic_apply = \
                            {
                                "on_apply_cancel_clicked": \
                                    self.__on_apply_cancel_clicked,
                                "on_publishers_apply_delete_event": \
                                    self.__on_publishers_apply_delete_event,
                            }
                        w_tree_add_publisher_complete.signal_autoconnect(
                            dic_add_publisher_comp)
                        w_tree_add_publisher.signal_autoconnect(dic_add_publisher)
                        w_tree_manage_publishers.signal_autoconnect(dic_manage_publishers)
                        w_tree_modify_repository.signal_autoconnect(dic_modify_repo)
                        w_tree_confirmation.signal_autoconnect(dic_confirmation)
                        w_tree_publishers_apply.signal_autoconnect(dic_apply)
                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check repository.py signals") \
                            % error

                self.publishers_list = self.__get_publishers_liststore()
                self.__init_pubs_tree_view(self.publishers_list)
                self.__init_mirrors_tree_view(self.modify_repo_mirrors_treeview)
                self.__init_origins_tree_view(self.modify_repo_origins_treeview)

                if self.action == enumerations.ADD_PUBLISHER:
                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog, 
                            self.main_window)
                        self.__on_manage_add_clicked(None)
                        return
                elif self.action == enumerations.MANAGE_PUBLISHERS:
                        gui_misc.set_modal_and_transient(self.w_manage_publishers_dialog,
                            self.main_window)
                        gui_misc.set_modal_and_transient(self.w_confirmation_dialog,
                            self.w_manage_publishers_dialog)
                        self.__prepare_publisher_list()
                        publisher_selection = self.w_publishers_treeview.get_selection()
                        publisher_selection.set_mode(gtk.SELECTION_SINGLE)
                        publisher_selection.connect("changed",
                            self.__on_publisher_selection_changed, None)
                        mirrors_selection = \
                            self.modify_repo_mirrors_treeview.get_selection()
                        mirrors_selection.set_mode(gtk.SELECTION_SINGLE)
                        mirrors_selection.connect("changed",
                            self.__on_mirror_selection_changed, None)
                        origins_selection = \
                            self.modify_repo_origins_treeview.get_selection()
                        origins_selection.set_mode(gtk.SELECTION_SINGLE)
                        origins_selection.connect("changed",
                            self.__on_origin_selection_changed, None)

                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog,
                            self.w_manage_publishers_dialog)
                        self.w_manage_publishers_dialog.show_all()
                        return

        def __init_pubs_tree_view(self, publishers_list):
                publishers_list_filter = publishers_list.filter_new()
                publishers_list_sort = gtk.TreeModelSort(publishers_list_filter)
                publishers_list_sort.set_sort_column_id(
                    enumerations.PUBLISHER_PRIORITY_CHANGED, gtk.SORT_ASCENDING)
                # Name column
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Publisher"),
                    name_renderer,  text = enumerations.PUBLISHER_NAME)
                column.set_expand(True)
                self.w_publishers_treeview.append_column(column)
                # Alias column
                alias_renderer = gtk.CellRendererText()
                alias_renderer.set_property("ellipsize", pango.ELLIPSIZE_END)
                column = gtk.TreeViewColumn(_("Alias"),
                    alias_renderer, text = enumerations.PUBLISHER_ALIAS)
                column.set_expand(True)
                self.w_publishers_treeview.append_column(column)
                # Enabled column
                toggle_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Enabled"),
                    toggle_renderer, active = enumerations.PUBLISHER_ENABLED)
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)
                toggle_renderer.connect('toggled', self.__enable_disable)
                column.set_cell_data_func(toggle_renderer, 
                    self.__toggle_data_function, None)
                self.w_publishers_treeview.append_column(column)
                publishers_list_filter.set_visible_func(self.__publishers_filter)
                self.w_publishers_treeview.set_model(publishers_list_sort)

        def __prepare_publisher_list(self, restore_changes = False):
                sorted_model = self.w_publishers_treeview.get_model()
                selection = self.w_publishers_treeview.get_selection()
                selected_rows = selection.get_selected_rows()
                self.w_publishers_treeview.set_model(None)
                try:
                        pubs = self.api_o.get_publishers(duplicate=True)
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return
                if not sorted_model:
                        return
                filtered_model = sorted_model.get_model()
                model = filtered_model.get_model()

                if len(pubs) > 1:
                        try:
                                so = self.api_o.get_pub_search_order()
                        except api_errors.ApiException, e:
                                self.__show_errors([("", e)])
                                return
                        pub_dict = dict([(p.prefix, p) for p in pubs])
                        pubs = [
                            pub_dict[name]
                            for name in so
                            if name in pub_dict
                            ]

                if restore_changes == False:
                        self.no_changes = 0
                        self.priority_changes = []
                        model.clear()

                        j = 0
                        for pub in pubs:
                                name = pub.prefix
                                alias = pub.alias
                                # BUG: alias should be either "None" or None.
                                # in the list it's "None", but when adding pub it's None
                                if not alias or len(alias) == 0 or alias == "None":
                                        alias = name
                                publisher_row = [j, j, name, alias, not pub.disabled, 
                                    pub, False, False]
                                model.insert(j, publisher_row)
                                j += 1
                else:
                        j = 0
                        for publisher_row in model:
                                pub = pubs[j]
                                name = pub.prefix
                                alias = pub.alias
                                if not alias or len(alias) == 0 or alias == "None":
                                        alias = name
                                publisher_row[enumerations.PUBLISHER_ALIAS] = alias
                                publisher_row[enumerations.PUBLISHER_OBJECT] = pub
                                j += 1

                self.w_publishers_treeview.set_model(sorted_model)

                if restore_changes:
                        # We do have gtk.SELECTION_SINGLE mode, so if exists, we are
                        # interested only in the first selected path. 
                        if len(selected_rows) > 1 and len(selected_rows[1]) > 0:
                                selection.select_path(selected_rows[1][0])

        def __validate_url(self, url_widget, w_ssl_key = None, w_ssl_cert = None):
                self.__validate_url_generic(url_widget, self.w_add_error_label, 
                    self.w_publisher_add_button, self.is_name_valid,
                    w_ssl_label=self.w_add_sslerror_label,
                    w_ssl_key=w_ssl_key, w_ssl_cert=w_ssl_cert)

        def __validate_url_generic(self, w_url_text, w_error_label, w_action_button,
                name_valid = False, function = None, w_ssl_label = None, 
                w_ssl_key = None, w_ssl_cert = None):
                ssl_key = None
                ssl_cert = None
                ssl_error = None
                ssl_valid = True
                url = w_url_text.get_text()
                self.is_url_valid, self.url_err = self.__is_url_valid(url)
                if not self.webinstall_new:
                        w_error_label.set_markup(self.publisher_info)
                        w_error_label.set_sensitive(False)
                        w_error_label.show()
                if w_ssl_label:
                        w_ssl_label.set_sensitive(False)
                        w_ssl_label.show()
                valid_url = False
                valid_func = True
                if self.is_url_valid:
                        if name_valid:
                                valid_url = True
                        else:
                                if self.name_error != None:
                                        self.__show_error_label_with_format(w_error_label,
                                            self.name_error)
                else:
                        if self.url_err != None:
                                self.__show_error_label_with_format(w_error_label,
                                    self.url_err)
                if w_ssl_key != None and w_ssl_cert != None:
                        if w_ssl_key:
                                ssl_key = w_ssl_key.get_text()
                        if w_ssl_cert:
                                ssl_cert = w_ssl_cert.get_text()
                        ssl_valid, ssl_error = self.__validate_ssl_key_cert(url, ssl_key,
                            ssl_cert, ignore_ssl_check_for_http=True)
                        self.__update_repository_dialog_width(ssl_error)
                        if ssl_error != None and w_ssl_label:
                                self.__show_error_label_with_format(w_ssl_label,
                                    ssl_error)
                        elif w_ssl_label:
                                w_ssl_label.hide()
                if function != None:
                        valid_func = function()
                w_action_button.set_sensitive(valid_url and valid_func and ssl_valid)

        def __validate_name_addpub(self, ok_btn, name_widget, url_widget, error_label,
            function = None):
                valid_btn = False
                valid_func = True
                name = name_widget.get_text() 
                self.is_name_valid = self.__is_name_valid(name)
                error_label.set_markup(self.publisher_info)
                error_label.set_sensitive(False)
                error_label.show()
                if self.is_name_valid:
                        if (self.is_url_valid):
                                valid_btn = True
                        else:
                                if self.url_err == None:
                                        self.__validate_url(url_widget,
                                            w_ssl_key=self.w_key_entry,
                                            w_ssl_cert=self.w_cert_entry)
                                if self.url_err != None:
                                        self.__show_error_label_with_format(error_label,
                                            self.url_err)
                else:
                        if self.name_error != None:
                                self.__show_error_label_with_format(error_label,
                                            self.name_error)
                if function != None:
                        valid_func = function()
                ok_btn.set_sensitive(valid_btn and valid_func)

        def __is_name_valid(self, name):
                self.name_error = None
                if len(name) == 0:
                        return False
                if not misc.valid_pub_prefix(name):
                        self.name_error = _("Name contains invalid characters")
                        return False
                try:
                        pubs = self.api_o.get_publishers()
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return False
                for p in pubs:
                        if name == p.prefix or name == p.alias:
                                self.name_error = _("Name already in use")
                                return False
                return True

        def __get_selected_publisher_itr_model(self):
                tsel = self.w_publishers_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr == None:
                        return (None, None)
                sorted_model = selection[0]
                sorted_path = sorted_model.get_path(itr)
                filter_path = sorted_model.convert_path_to_child_path(sorted_path)
                filter_model = sorted_model.get_model()
                path = filter_model.convert_path_to_child_path(filter_path)
                model = filter_model.get_model()
                itr = model.get_iter(path)
                return (itr, model)

        def __get_selected_mirror_itr_model(self):
                return self.__get_fitr_model_from_tree(\
                    self.modify_repo_mirrors_treeview)

        def __get_selected_origin_itr_model(self):
                return self.__get_fitr_model_from_tree(\
                    self.modify_repo_origins_treeview)

        def __modify_publisher_dialog(self, pub):
                gui_misc.set_modal_and_transient(self.w_modify_repository_dialog,
                    self.w_manage_publishers_dialog)
                try:
                        self.repository_modify_publisher = self.api_o.get_publisher(
                            prefix=pub.prefix, alias=pub.prefix, duplicate=True)
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return                
                updated_modify_repository = self.__update_modify_repository_dialog(True,
                    True, True, True)
                    
                self.w_modify_repository_dialog.set_size_request(
                    MODIFY_DIALOG_WIDTH_DEFAULT, -1)

                if updated_modify_repository:
                        self.w_modify_repository_dialog.show_all()

        def __update_repository_dialog_width(self, ssl_error):
                if ssl_error == None:
                        self.w_modify_repository_dialog.set_size_request(
                            MODIFY_DIALOG_WIDTH_DEFAULT, -1)
                        return

                style = self.w_repositorymodify_name.get_style()
                font_size_in_pango_unit = style.font_desc.get_size()
                font_size_in_pixel = font_size_in_pango_unit / pango.SCALE 
                ssl_error_len = len(unicode(ssl_error)) * font_size_in_pixel
                if ssl_error_len > MODIFY_DIALOG_SSL_WIDTH_DEFAULT:
                        new_dialog_width = ssl_error_len * \
                                (float(MODIFY_DIALOG_WIDTH_DEFAULT)/
                                    MODIFY_DIALOG_SSL_WIDTH_DEFAULT)
                        self.w_modify_repository_dialog.set_size_request(
                            int(new_dialog_width), -1)
                else:
                        self.w_modify_repository_dialog.set_size_request(
                            MODIFY_DIALOG_WIDTH_DEFAULT, -1)

        def __update_modify_repository_dialog(self, update_alias=False, 
            update_mirrors=False, update_origins=False, update_ssl=False):
                if not self.repository_modify_publisher:
                        return False
                pub = self.repository_modify_publisher
                selected_repo = pub.selected_repository
                prefix = ""
                ssl_cert = ""
                ssl_key = ""

                if pub.prefix and len(pub.prefix) > 0:
                        prefix = pub.prefix
                self.w_repositorymodify_name.set_text(prefix)

                if update_alias:
                        alias = ""
                        if pub.alias and len(pub.alias) > 0 \
                            and pub.alias != "None":
                                alias = pub.alias
                        self.w_modify_pub_alias.set_text(alias)

                if update_mirrors or update_ssl:
                        if update_mirrors:
                                insert_count = 0
                                mirrors_list = self.__get_mirrors_origins_liststore()
                        for mirror in selected_repo.mirrors:
                                if mirror.ssl_cert:
                                        ssl_cert = mirror.ssl_cert
                                if mirror.ssl_key:
                                        ssl_key = mirror.ssl_key
                                if update_mirrors:
                                        mirror_uri = [mirror.uri]
                                        mirrors_list.insert(insert_count, mirror_uri)
                                        insert_count += 1
                        if update_mirrors:
                                self.modify_repo_mirrors_treeview.set_model(mirrors_list)
                                if len(selected_repo.mirrors) > 0:
                                        self.w_repositorymirror_expander.set_expanded(
                                            True)
                                else:
                                        self.w_repositorymirror_expander.set_expanded(
                                            False)

                if update_origins or update_ssl:
                        if update_origins:
                                insert_count = 0
                                origins_list = self.__get_mirrors_origins_liststore()
                        for origin in selected_repo.origins:
                                if origin.ssl_cert:
                                        ssl_cert = origin.ssl_cert
                                if origin.ssl_key:
                                        ssl_key = origin.ssl_key
                                if update_origins:
                                        origin_uri = [origin.uri]
                                        origins_list.insert(insert_count, origin_uri)
                                        insert_count += 1
                        if update_origins:
                                self.modify_repo_origins_treeview.set_model(origins_list)

                reg_uri = self.__get_registration_uri(selected_repo)
                if reg_uri != None:
                        self.w_repositorymodify_registration_link.set_uri(
                            reg_uri)
                        self.w_repositorymodify_registration_box.show()
                else:
                        self.w_repositorymodify_registration_box.hide()

                if update_ssl:
                        self.w_repositorymodify_cert_entry.set_text(ssl_cert)
                        self.w_repositorymodify_key_entry.set_text(ssl_key)
                        if len(ssl_cert) > 0 or len(ssl_key) > 0:
                                self.w_repositoryssl_expander.set_expanded(True)
                        else:
                                self.w_repositoryssl_expander.set_expanded(False)
                return True

        def __add_mirror(self, new_mirror):
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                try:
                        repo.add_mirror(new_mirror)
                        self.w_addmirror_entry.set_text("")
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_mirrors=True)

        def __rm_mirror(self):
                itr, model = self.__get_selected_mirror_itr_model()
                remove_mirror = None
                if itr and model:
                        remove_mirror = model.get_value(itr, 0)
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                try:
                        repo.remove_mirror(remove_mirror)
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_mirrors=True)

        def __add_origin(self, new_origin):
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                try:
                        repo.add_origin(new_origin)
                        self.w_addorigin_entry.set_text("")
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_origins=True)

        def __rm_origin(self):
                itr, model = self.__get_selected_origin_itr_model()
                remove_origin = None
                if itr and model:
                        remove_origin = model.get_value(itr, 0)
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                try:
                        repo.remove_origin(remove_origin)
                except api_errors.ApiException, e:
                        self.__show_errors([(pub, e)])
                self.__update_modify_repository_dialog(update_origins=True)

        def __enable_disable(self, cell, sorted_path):
                sorted_model = self.w_publishers_treeview.get_model()
                filtered_path = sorted_model.convert_path_to_child_path(sorted_path)
                filtered_model = sorted_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                model = filtered_model.get_model()
                itr = model.get_iter(path)
                if itr == None:
                        return
                preferred = 0 == model.get_value(itr,
                    enumerations.PUBLISHER_PRIORITY_CHANGED)
                if preferred:
                        return
                enabled = model.get_value(itr, enumerations.PUBLISHER_ENABLED)
                changed = model.get_value(itr, enumerations.PUBLISHER_ENABLE_CHANGED)
                model.set_value(itr, enumerations.PUBLISHER_ENABLED, not enabled)
                model.set_value(itr, enumerations.PUBLISHER_ENABLE_CHANGED, not changed)
                self.__enable_disable_updown_btn(itr, model)

        @staticmethod
        def __is_at_least_one_entry(treeview):
                model = treeview.get_model()
                if len(model) > 1:
                        return True
                return False

        def __enable_disable_remove_btn(self, itr):
                if itr:
                        if self.__is_at_least_one_entry(self.w_publishers_treeview):
                                self.w_manage_remove_btn.set_sensitive(True)
                                return
                self.w_manage_remove_btn.set_sensitive(False)

        def __enable_disable_updown_btn(self, itr, model):
                up_enabled = True
                down_enabled = True
                sorted_size = len(self.w_publishers_treeview.get_model())
                i = 0

                if itr:
                        enabled = model.get_value(itr,
                            enumerations.PUBLISHER_ENABLED)
                        cur_priority = model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                        self.__enable_disable_remove_btn(itr)
                        if cur_priority == 0:
                                self.__enable_disable_remove_btn(None)
                                up_enabled = False
                                for row in self.w_publishers_treeview.get_model():
                                        if i == 1:
                                                down_enabled = \
                                                    row[enumerations.PUBLISHER_ENABLED]
                                                break
                                        i += 1
                        elif cur_priority == 1 and not enabled:
                                up_enabled = False
                                down_enabled = True
                                if cur_priority == sorted_size - 1:
                                        down_enabled = False
                        elif cur_priority == sorted_size - 1:
                                up_enabled = True
                                down_enabled = False
                        if sorted_size == 1:
                                up_enabled = False
                                down_enabled = False
                self.w_manage_up_btn.set_sensitive(up_enabled)
                self.w_manage_down_btn.set_sensitive(down_enabled)

        def __do_add_repository(self, name=None, url=None, ssl_key=None, ssl_cert=None,
            pub=None):
                self.publishers_apply.set_title(_("Adding Publisher"))
                if self.webinstall_new:
                        self.__run_with_prog_in_thread(self.__add_repository,
                            self.main_window, self.__stop, None, None,  ssl_key,
                            ssl_cert, self.repository_modify_publisher)
                else:
                        repo = publisher.Repository()
                        repo.add_origin(url)
                        self.__run_with_prog_in_thread(self.__add_repository,
                            self.w_add_publisher_dialog, self.__stop, name,
                            url, ssl_key, ssl_cert, pub)

        def __stop(self):
                if self.cancel_progress_thread == False:
                        self.__update_details_text(_("Canceling...\n"))
                        self.cancel_progress_thread = True
                        self.publishers_apply_cancel.set_sensitive(False)

        def __add_repository(self, name=None, origin_url=None, ssl_key=None, 
            ssl_cert=None, pub=None):
                errors = []
                if pub == None:
                        pub, repo, new_pub = self.__get_or_create_pub_with_url(self.api_o,
                            name, origin_url)
                else:
                        repo = pub.selected_repository
                        new_pub = True
                        name = pub.prefix
                errors_ssl = self.__update_ssl_creds(pub, repo, ssl_cert, ssl_key)
                errors_update = []
                try:
                        errors_update = self.__update_publisher(pub,
                            new_publisher=new_pub)
                except api_errors.UnknownRepositoryPublishers, e:
                        if len(e.known) > 0:
                                pub, repo, new_pub = self.__get_or_create_pub_with_url(
                                    self.api_o, e.known[0], origin_url)
                                pub.alias = name
                                errors_update = self.__update_publisher(pub,
                                    new_publisher=new_pub, raise_unknownpubex=False)
                        else:
                                errors_update.append((pub, e))
                errors += errors_ssl
                errors += errors_update
                if self.cancel_progress_thread:
                        try:
                                self.__g_update_details_text(
                                    _("Removing publisher %s\n") % name)
                                self.api_o.remove_publisher(prefix=name,
                                    alias=name)
                                self.__g_update_details_text(
                                    _("Publisher %s succesfully removed\n") % name)
                        except api_errors.ApiException, e:
                                errors.append((pub, e))
                        self.progress_stop_thread = True
                else:
                        self.progress_stop_thread = True
                        if len(errors) > 0:
                                gobject.idle_add(self.__show_errors, errors)
                        elif not self.webinstall_new:
                                gobject.idle_add(self.__afteradd_confirmation, pub)
                                self.progress_stop_thread = True
                                gobject.idle_add(
                                   self.__g_on_add_publisher_delete_event,
                                   self.w_add_publisher_dialog, None)
                        elif self.webinstall_new:
                                gobject.idle_add(
                                   self.__g_on_add_publisher_delete_event,
                                   self.w_add_publisher_dialog, None)
                                gobject.idle_add(self.parent.reload_packages)

        def __update_publisher(self, pub, new_publisher=False, raise_unknownpubex=True):
                errors = []
                try:
                        self.no_changes += 1
                        if new_publisher:
                                self.__g_update_details_text(
                                    _("Adding publisher %s\n") % pub.prefix)
                                self.api_o.add_publisher(pub)
                        else:
                                self.__g_update_details_text(
                                    _("Updating publisher %s\n") % pub.prefix)
                                self.api_o.update_publisher(pub)
                        if new_publisher:
                                self.__g_update_details_text(
                                    _("Publisher %s succesfully added\n") % pub.prefix)
                        else:
                                self.__g_update_details_text(
                                    _("Publisher %s succesfully updated\n") % pub.prefix)
                except api_errors.UnknownRepositoryPublishers, e:
                        if raise_unknownpubex:
                                raise e
                        else:
                                errors.append((pub, e))
                except api_errors.ApiException, e:
                        errors.append((pub, e))
                return errors

        def __afteradd_confirmation(self, pub):
                repo = pub.selected_repository
                origin = repo.origins[0]
                # Descriptions not available at the moment
                self.w_add_publisher_c_desc.hide()
                self.w_add_publisher_c_desc_l.hide()
                if pub.alias and len(pub.alias) > 0:
                        self.w_add_publisher_c_name.set_text(
                                pub.alias + " ("+ pub.prefix +")")
                else:
                        self.w_add_publisher_c_name.set_text(pub.prefix)
                self.w_add_publisher_c_url.set_text(origin.uri)
                self.w_add_publisher_comp_dialog.show()

        def __prepare_confirmation_dialog(self):
                disable = ""
                enable = ""
                delete = ""
                priority_change = ""
                disable_no = 0
                enable_no = 0
                delete_no = 0
                not_removed = []
                removed_priorities = []
                priority_changed = []
                for row in self.publishers_list:
                        pub_name = row[enumerations.PUBLISHER_NAME]
                        if row[enumerations.PUBLISHER_REMOVED]:
                                delete += "\t" + pub_name + "\n"
                                delete_no += 1
                                removed_priorities.append(
                                    row[enumerations.PUBLISHER_PRIORITY])
                        else:
                                if row[enumerations.PUBLISHER_ENABLE_CHANGED]:
                                        to_enable = row[enumerations.PUBLISHER_ENABLED]
                                        if not to_enable:
                                                disable += "\t" + pub_name + "\n"
                                                disable_no += 1
                                        else:
                                                enable += "\t" + pub_name + "\n"
                                                enable_no += 1
                                not_removed.append(row)

                for pub in not_removed:
                        if not self.__check_if_ignore(pub, removed_priorities):
                                pub_name = pub[enumerations.PUBLISHER_NAME]
                                pri = pub[enumerations.PUBLISHER_PRIORITY_CHANGED]
                                priority_changed.append([pri, pub_name])

                if disable_no == 0 and enable_no == 0 and delete_no == 0 and \
                    len(priority_changed) == 0:
                        self.__on_manage_cancel_clicked(None)
                        return

                priority_changed.sort()
                for pri, pub_name in priority_changed:
                        priority_change += "\t" + str(pri+1) + \
                            " - " + pub_name + "\n"

                textbuf = self.w_confirmation_textview.get_buffer()
                textbuf.set_text("")
                textiter = textbuf.get_end_iter()

                disable_text = ngettext("Disable Publisher:\n",
		    "Disable Publishers:\n", disable_no)
                enable_text = ngettext("Enable Publisher:\n",
		    "Enable Publishers:\n", enable_no)
                delete_text = ngettext("Remove Publisher:\n",
		    "Remove Publishers:\n", delete_no)
                priority_text = _("Change Priorities:\n")

                confirm_no = delete_no + enable_no + disable_no
                confirm_text = ngettext("Apply the following change:",
		    "Apply the following changes:", confirm_no)

                self.w_confirmation_label.set_markup("<b>" + confirm_text + "</b>")

                if len(delete) > 0:
                        textbuf.insert_with_tags_by_name(textiter,
                            delete_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            delete)
                if len(disable) > 0:
                        if len(delete) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            disable_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            disable)
                if len(enable) > 0:
                        if len(delete) > 0 or len(disable) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            enable_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            enable)
                if len(priority_change) > 0:
                        if len(delete) > 0 or len(disable) or len(enable) > 0:
                                textbuf.insert_with_tags_by_name(textiter,
                                    "\n")
                        textbuf.insert_with_tags_by_name(textiter,
                            priority_text, "bold")
                        textbuf.insert_with_tags_by_name(textiter,
                            priority_change)

                self.w_confirm_cancel_btn.grab_focus()
                self.w_confirmation_dialog.show_all()

        def __proceed_enable_disable(self, pub_names, to_enable):
                errors = []

                gobject.idle_add(self.publishers_apply_expander.set_expanded, True)
                for name in pub_names.keys():
                        try:
                                pub = self.api_o.get_publisher(name,
                                    duplicate = True)
                                if pub.disabled == (not to_enable):
                                        continue
                                pub.disabled = not to_enable
                                self.no_changes += 1
                                enable_text = _("Disabling")
                                if to_enable:
                                        enable_text = _("Enabling")

                                details_text = \
                                        _("%(enable)s publisher %(name)s\n")
                                self.__g_update_details_text(details_text %
                                    {"enable" : enable_text, "name" : name})
                                self.api_o.update_publisher(pub)
                        except api_errors.ApiException, e:
                                errors.append(pub, e)
                self.progress_stop_thread = True
                gobject.idle_add(self.publishers_apply_expander.set_expanded, False)
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.parent.reload_packages, False)

        def __proceed_after_confirmation(self):
                errors = []

                image_lock_err = False
                for row in self.priority_changes:
                        try:
                                if row[0] == enumerations.PUBLISHER_MOVE_BEFORE:
                                        self.api_o.set_pub_search_before(row[1],
                                            row[2])
                                else:
                                        self.api_o.set_pub_search_after(row[1],
                                            row[2])
                                self.no_changes += 1
                                self.__g_update_details_text(
                                    _("Changing priority for publisher %s\n")
                                    % row[1])
                        except api_errors.ImageLockedError, e:
                                self.no_changes = 0
                                if not image_lock_err:
                                        errors.append((row[1], e))
                                        image_lock_err = True
                        except api_errors.ApiException, e:
                                errors.append((row[1], e))

                for row in self.publishers_list:
                        name = row[enumerations.PUBLISHER_NAME]
                        try:
                                if row[enumerations.PUBLISHER_REMOVED]:
                                        self.no_changes += 1
                                        self.__g_update_details_text(
                                            _("Removing publisher %s\n") % name)
                                        self.api_o.remove_publisher(prefix=name,
                                            alias=name)
                                        self.__g_update_details_text(
                                            _("Publisher %s succesfully removed\n")
                                            % name)
                                elif row[enumerations.PUBLISHER_ENABLE_CHANGED]:
                                        to_enable = row[enumerations.PUBLISHER_ENABLED]
                                        pub = self.api_o.get_publisher(name, 
                                            duplicate = True)
                                        pub.disabled = not to_enable
                                        self.no_changes += 1
                                        enable_text = _("Disabling")
                                        if to_enable:
                                                enable_text = _("Enabling")

                                        details_text = \
                                                _("%(enable)s publisher %(name)s\n")
                                        self.__g_update_details_text(details_text % 
                                            {"enable" : enable_text, "name" : name})
                                        self.api_o.update_publisher(pub)
                        except api_errors.ImageLockedError, e:
                                self.no_changes = 0
                                if not image_lock_err:
                                        errors.append(
                                            (row[enumerations.PUBLISHER_OBJECT], e))
                                        image_lock_err = True
                        except api_errors.ApiException, e:
                                errors.append((row[enumerations.PUBLISHER_OBJECT], e))
                self.progress_stop_thread = True
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.__after_confirmation)

        def __after_confirmation(self):
                self.__on_manage_publishers_delete_event(
                    self.w_manage_publishers_dialog, None)
                return False

        def __proceed_modifyrepo_ok(self):
                errors = []
                alias = self.w_modify_pub_alias.get_text()
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                pub.alias = alias
                errors += self.__update_ssl_creds(pub, repo, ssl_cert, ssl_key)
                try:
                        errors += self.__update_publisher(pub, new_publisher=False)
                except api_errors.UnknownRepositoryPublishers, e:
                        errors.append((pub, e))
                self.progress_stop_thread = True
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.__g_delete_widget_handler_hide,
                            self.w_modify_repository_dialog, None)
                        if self.action == enumerations.MANAGE_PUBLISHERS:
                                gobject.idle_add(self.__prepare_publisher_list, True)
                                self.no_changes += 1

        def __run_with_prog_in_thread(self, func, parent_window = None,
            cancel_func = None, *f_args):
                self.progress_stop_thread = False
                self.cancel_progress_thread = False
                if cancel_func == None:
                        self.publishers_apply_cancel.set_sensitive(False)
                else:
                        self.publishers_apply_cancel.set_sensitive(True)
                gui_misc.set_modal_and_transient(self.publishers_apply, parent_window)
                self.publishers_apply_textview.get_buffer().set_text("")
                self.publishers_apply.show_all()
                self.cancel_function = cancel_func
                gobject.timeout_add(100, self.__progress_pulse)
                Thread(target = func, args = f_args).start()

        def __progress_pulse(self):
                if not self.progress_stop_thread:
                        self.publishers_apply_progress.pulse()
                        return True
                else:
                        self.publishers_apply.hide()
                        return False

        def __g_update_details_text(self, text, *tags):
                gobject.idle_add(self.__update_details_text, text, *tags)

        def __update_details_text(self, text, *tags):
                buf = self.publishers_apply_textview.get_buffer()
                textiter = buf.get_end_iter()
                if tags:
                        buf.insert_with_tags_by_name(textiter, text, *tags)
                else:
                        buf.insert(textiter, text)
                self.publishers_apply_textview.scroll_to_iter(textiter, 0.0)

        # Signal handlers
        def __on_publisher_selection_changed(self, selection, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                if itr and model:
                        self.__enable_disable_updown_btn(itr, model)
                        self.__update_publisher_details(
                            model.get_value(itr, enumerations.PUBLISHER_OBJECT),
                            self.w_manage_publishers_details)
                        if 0 == model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED):
                                itr = None
                self.__enable_disable_remove_btn(itr)

        def __on_mirror_selection_changed(self, selection, widget):
                model_itr = selection.get_selected()
                if model_itr[1]:
                        self.w_rmmirror_button.set_sensitive(True)
                else:
                        self.w_rmmirror_button.set_sensitive(False)

        def __on_origin_selection_changed(self, selection, widget):
                model_itr = selection.get_selected()
                if model_itr[1] and \
                    self.__is_at_least_one_entry(self.modify_repo_origins_treeview):
                        self.w_rmorigin_button.set_sensitive(True)
                else:
                        self.w_rmorigin_button.set_sensitive(False)

        def __g_on_add_publisher_delete_event(self, widget, event):
                self.__on_add_publisher_delete_event(widget, event)
                return False
                
        def __on_add_publisher_delete_event(self, widget, event):
                self.w_add_publisher_url.set_text("")
                self.w_add_publisher_name.set_text("")
                self.__delete_widget_handler_hide(widget, event)
                return True

        def __on_add_publisher_complete_delete_event(self, widget, event):
                if self.no_changes > 0:
                        self.parent.reload_packages()
                        if self.action == enumerations.MANAGE_PUBLISHERS:
                                self.__prepare_publisher_list()
                                self.w_publishers_treeview.get_selection().select_path(0)
                self.__delete_widget_handler_hide(widget, event)
                return True

        def __on_publisherurl_changed(self, widget):
                url = widget.get_text()
                if url.startswith("https"):
                        self.w_ssl_box.show()
                else:
                        self.w_ssl_box.hide()
                self.__validate_url(widget,
                    w_ssl_key=self.w_key_entry, w_ssl_cert=self.w_cert_entry)

        def __on_certentry_changed(self, widget):
                self.__validate_url_generic(self.w_add_publisher_url,
                    self.w_add_error_label, self.w_publisher_add_button,
                    self.is_name_valid, w_ssl_label=self.w_add_sslerror_label,
                    w_ssl_key=self.w_key_entry, w_ssl_cert=widget)

        def __on_keyentry_changed(self, widget):
                self.__validate_url_generic(self.w_add_publisher_url,
                    self.w_add_error_label, self.w_publisher_add_button,
                    self.is_name_valid, w_ssl_label=self.w_add_sslerror_label,
                    w_ssl_key=widget, w_ssl_cert=self.w_cert_entry)

        def __on_modcertkeyentry_changed(self, widget):
                self.__on_addorigin_entry_changed(None)
                self.__on_addmirror_entry_changed(None)
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                ssl_valid, ssl_error = self.__validate_ssl_key_cert(None,
                    ssl_key, ssl_cert)
                self.__update_repository_dialog_width(ssl_error)
                self.w_repositorymodifyok_button.set_sensitive(True)
                if ssl_valid == False and (len(ssl_key) > 0 or len(ssl_cert) > 0):
                        self.w_repositorymodifyok_button.set_sensitive(False)
                        if ssl_error != None:
                                self.__show_error_label_with_format(
                                    self.w_modsslerror_label, ssl_error)
                        else:
                                self.w_modsslerror_label.set_text("")
                        return
                self.w_modsslerror_label.set_text("")

        def __on_addmirror_entry_changed(self, widget):
                uri_list_model = self.modify_repo_mirrors_treeview.get_model()
                error_text = _("Mirrors for a secure publisher\n"
                            "need to begin with https://")
                self.__validate_mirror_origin_url(self.w_addmirror_entry.get_text(),
                    self.w_addmirror_button, self.w_modmirrerror_label, uri_list_model,
                    error_text)

        def __on_addorigin_entry_changed(self, widget):
                uri_list_model = self.modify_repo_origins_treeview.get_model()
                error_text = _("Origins for a secure publisher\n"
                            "need to begin with https://")
                self.__validate_mirror_origin_url(self.w_addorigin_entry.get_text(),
                    self.w_addorigin_button, self.w_modoriginerror_label, uri_list_model,
                    error_text)

        def __validate_mirror_origin_url(self, url, add_button, error_label,
            uri_list_model, error_text):
                url_error = None
                is_url_valid, url_error = self.__is_url_valid(url)
                add_button.set_sensitive(False)
                error_label.set_sensitive(False)
                error_label.set_markup(self.publisher_info)
                if len(url) <= 4:
                        if is_url_valid == False and url_error != None:
                                self.__show_error_label_with_format(
                                    error_label, url_error)
                        return

                for uri_row in uri_list_model:
                        origin_url = uri_row[0].strip("/")
                        if origin_url.strip("/") == url.strip("/"):
                                url_error = _("URI already added")
                                self.__show_error_label_with_format(
                                            error_label, url_error)
                                return

                ssl_specified = self.__is_ssl_specified()
                is_mirror_ssl = url.startswith("https")
                if ssl_specified and is_mirror_ssl == False:
                        self.__show_error_label_with_format(error_label, error_text)
                        return

                if is_url_valid == False:
                        if url_error != None:
                                self.__show_error_label_with_format(error_label,
                                    url_error)
                        return
                add_button.set_sensitive(True)

        def __is_ssl_specified(self):
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                if len(ssl_key) > 0 or len(ssl_cert) > 0:
                        return True
                return False

        def __on_publishername_changed(self, widget):
                error_label = self.w_add_error_label
                url_widget = self.w_add_publisher_url
                ok_btn = self.w_publisher_add_button
                self.__validate_name_addpub(ok_btn, widget, url_widget, error_label)

        def __on_add_publisher_add_clicked(self, widget):
                if self.w_publisher_add_button.get_property('sensitive') == 0:
                        return
                name = self.w_add_publisher_name.get_text()
                url = self.w_add_publisher_url.get_text()
                ssl_key = self.w_key_entry.get_text()
                ssl_cert = self.w_cert_entry.get_text()
                if not url.startswith("https") or not \
                    (ssl_key and ssl_cert and os.path.isfile(ssl_cert) and
                    os.path.isfile(ssl_key)):
                        ssl_key = None
                        ssl_cert = None
                self.__do_add_repository(name, url, ssl_key, ssl_cert)

        def __on_apply_cancel_clicked(self, widget):
                if self.cancel_function:
                        self.cancel_function()

        def __on_add_publisher_cancel_clicked(self, widget):
                self.__on_add_publisher_delete_event(
                    self.w_add_publisher_dialog, None)

        def __on_modkeybrowse_clicked(self, widget):
                self.__keybrowse(self.w_modify_repository_dialog,
                    self.w_repositorymodify_key_entry,
                    self.w_repositorymodify_cert_entry)

        def __on_modcertbrowse_clicked(self, widget):
                self.__certbrowse(self.w_modify_repository_dialog,
                    self.w_repositorymodify_cert_entry)

        def __on_keybrowse_clicked(self, widget):
                self.__keybrowse(self.w_add_publisher_dialog,
                    self.w_key_entry, self.w_cert_entry)

        def __on_certbrowse_clicked(self, widget):
                self.__certbrowse(self.w_add_publisher_dialog,
                    self.w_cert_entry)

        def __on_add_publisher_c_close_clicked(self, widget):
                self.__on_add_publisher_complete_delete_event(
                    self.w_add_publisher_comp_dialog, None)

        def __on_manage_publishers_delete_event(self, widget, event):
                self.__delete_widget_handler_hide(widget, event)
                if self.no_changes > 0:
                        self.parent.reload_packages()
                return True

        def __g_delete_widget_handler_hide(self, widget, event):
                self.__delete_widget_handler_hide(widget, event)
                return False

        def __on_manage_add_clicked(self, widget):
                self.w_add_publisher_name.grab_focus()
                self.w_registration_box.hide()
                self.w_add_publisher_dialog.set_title(_("Add Publisher"))
                self.w_add_publisher_dialog.show_all()

        def __on_manage_modify_clicked(self, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                if itr and model:
                        pub = model.get_value(itr, enumerations.PUBLISHER_OBJECT)
                        self.__modify_publisher_dialog(pub)

        def __on_manage_remove_clicked(self, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                tsel = self.w_publishers_treeview.get_selection()
                selection = tsel.get_selected()
                sel_itr = selection[1]
                sorted_model = selection[0]
                sorted_path = sorted_model.get_path(sel_itr)
                if itr and model:
                        current_priority = model.get_value(itr, 
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                        model.set_value(itr, enumerations.PUBLISHER_REMOVED, True)
                        for element in model:
                                if element[enumerations.PUBLISHER_PRIORITY_CHANGED] > \
                                    current_priority:
                                        element[
                                            enumerations.PUBLISHER_PRIORITY_CHANGED] -= 1
                        tsel.select_path(sorted_path)
                        if not tsel.path_is_selected(sorted_path):
                                row = sorted_path[0]-1
                                if row >= 0:
                                        tsel.select_path((row,))

        def __on_manage_move_up_clicked(self, widget):
                before_name = None
                itr, model = self.__get_selected_publisher_itr_model()
                cur_priority = model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                cur_name = model.get_value(itr, enumerations.PUBLISHER_NAME)
                for element in model:
                        if cur_priority == \
                            element[enumerations.PUBLISHER_PRIORITY_CHANGED]:
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] -= 1
                        elif element[enumerations.PUBLISHER_PRIORITY_CHANGED] \
                            == cur_priority - 1 :
                                before_name = element[enumerations.PUBLISHER_NAME]
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] += 1
                self.priority_changes.append([enumerations.PUBLISHER_MOVE_BEFORE,
                    cur_name, before_name])
                self.__enable_disable_updown_btn(itr, model)

        def __on_manage_move_down_clicked(self, widget):
                after_name = None
                itr, model = self.__get_selected_publisher_itr_model()
                cur_priority = model.get_value(itr,
                            enumerations.PUBLISHER_PRIORITY_CHANGED)
                cur_name = model.get_value(itr, enumerations.PUBLISHER_NAME)
                for element in model:
                        if cur_priority == \
                            element[enumerations.PUBLISHER_PRIORITY_CHANGED]:
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] += 1
                        elif element[enumerations.PUBLISHER_PRIORITY_CHANGED] \
                            == cur_priority + 1 :
                                after_name = element[enumerations.PUBLISHER_NAME]
                                element[
                                    enumerations.PUBLISHER_PRIORITY_CHANGED] -= 1
                self.priority_changes.append([enumerations.PUBLISHER_MOVE_AFTER,
                    cur_name, after_name])
                self.__enable_disable_updown_btn(itr, model)

        def __on_manage_cancel_clicked(self, widget):
                self.__on_manage_publishers_delete_event(
                    self.w_manage_publishers_dialog, None)

        def __on_manage_ok_clicked(self, widget):
                self.__prepare_confirmation_dialog()

        def __on_publishers_apply_delete_event(self, widget, event):
                self.__on_apply_cancel_clicked(None)
                return True

        def __on_addmirror_button_clicked(self, widget):
                if self.w_addmirror_button.get_property('sensitive') == 0:
                        return
                new_mirror = self.w_addmirror_entry.get_text()
                self.__add_mirror(new_mirror)

        def __on_addorigin_button_clicked(self, widget):
                if self.w_addorigin_button.get_property('sensitive') == 0:
                        return
                new_origin = self.w_addorigin_entry.get_text()
                self.__add_origin(new_origin)

        def __on_rmmirror_button_clicked(self, widget):
                self.__rm_mirror()

        def __on_rmorigin_button_clicked(self, widget):
                self.__rm_origin()
                
        def __on_repositorymodifyok_clicked(self, widget):
                if self.w_repositorymodifyok_button.get_property('sensitive') == 0:
                        return
                self.publishers_apply.set_title(_("Applying Changes"))
                self.__run_with_prog_in_thread(self.__proceed_modifyrepo_ok,
                    self.w_manage_publishers_dialog)

        def __on_repositorymodifycancel_clicked(self, widget):
                self.__delete_widget_handler_hide(
                    self.w_modify_repository_dialog, None)

        def __on_cancel_conf_clicked(self, widget):
                self.__delete_widget_handler_hide(
                    self.w_confirmation_dialog, None)

        def __on_ok_conf_clicked(self, widget):
                self.w_confirmation_dialog.hide()
                self.publishers_apply.set_title(_("Applying Changes"))
                self.__run_with_prog_in_thread(self.__proceed_after_confirmation,
                    self.w_manage_publishers_dialog)

#-----------------------------------------------------------------------------#
# Static Methods
#-----------------------------------------------------------------------------#
        @staticmethod
        def __check_if_ignore(pub, removed_list):
                """If we remove a publisher from our model, the priorities of
                   subsequent publishers  are decremented. We need to ignore the
                   priority changes caused solely by publisher(s) removal.
                   This function returns True if the priority change for a publisher
                   is due to publisher(s) removal or False otherwise.""" 
                priority_sum = 0
                priority = pub[enumerations.PUBLISHER_PRIORITY]
                priority_changed = pub[enumerations.PUBLISHER_PRIORITY_CHANGED]
                for num in removed_list:
                        if num < priority:
                                priority_sum += 1
                return (priority == priority_changed + priority_sum)

        @staticmethod
        def __on_add_pub_help_clicked(widget):
                gui_misc.display_help("add-publisher")

        @staticmethod
        def __on_manage_help_clicked(widget):
                gui_misc.display_help("manage-publisher")

        @staticmethod
        def __on_modify_repo_help_clicked(widget):
                gui_misc.display_help("manage-publisher")

        @staticmethod
        def __update_publisher_details(pub, details_view):
                if pub == None:
                        return
                details_buffer = details_view.get_buffer()
                details_buffer.set_text("")
                uri_s_itr = details_buffer.get_start_iter()
                repo = pub.selected_repository
                num = len(repo.origins)
                origin_txt = ngettext("Origin:\n", "Origins:\n", num)
                details_buffer.insert_with_tags_by_name(uri_s_itr,
                    origin_txt, "level0")
                uri_itr = details_buffer.get_end_iter()
                for origin in repo.origins:
                        details_buffer.insert(uri_itr, "%s\n" % origin.uri)

        def __show_errors(self, errors, msg_type=gtk.MESSAGE_ERROR, title = None):
                error_msg = ""
                if title != None:
                        msg_title = title
                else:   # More Generic for WebInstall
                        msg_title = _("Publisher error")
                for err in errors:
                        if isinstance(err[1], api_errors.CatalogRefreshException):
                                crerr = gui_misc.get_catalogrefresh_exception_msg(err[1])
                                logger.error(crerr)
                                gui_misc.notify_log_error(self.parent)
                        else:
                                error_msg += str(err[1])
                                error_msg += "\n\n"
                if error_msg != "":
                        gui_misc.error_occurred(None, error_msg, msg_title, msg_type)

        @staticmethod
        def __keybrowse(w_parent, key_entry, cert_entry):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Key File"),
                    parent = w_parent,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(w_parent)
                chooser.set_modal(True)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        key = chooser.get_filename()
                        key_entry.set_text(key)
                        cert = key.replace("key", "certificate")
                        if key != cert and \
                            cert_entry.get_text() == "":
                                if os.path.isfile(cert):
                                        cert_entry.set_text(cert)
                chooser.destroy()

        @staticmethod
        def __certbrowse(w_parent, cert_entry):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Certificate File"),
                    parent = w_parent,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(w_parent)
                chooser.set_modal(True)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        cert_entry.set_text(
                            chooser.get_filename())
                chooser.destroy()

        @staticmethod
        def __delete_widget_handler_hide(widget, event):
                widget.hide()
                return True

        def __get_or_create_pub_with_url(self, api_o, name, origin_url):
                new_pub = False
                repo = None
                pub = None
                try:
                        pub = api_o.get_publisher(prefix=name, alias=name,
                            duplicate=True)
                        repo = pub.selected_repository
                except api_errors.UnknownPublisher:
                        repo = publisher.Repository()
                        pub = publisher.Publisher(name, repositories=[repo])
                        new_pub = True
                        # This part is copied from "def publisher_set(img, args)"
                        # from the client.py as the publisher API is not ready yet.
                        if not repo.origins:
                                repo.add_origin(origin_url)
                                origin = repo.origins[0]
                        else:
                                origin = repo.origins[0]
                                origin.uri = origin_url
                except api_errors.ApiException, e:
                        self.__show_errors([(name, e)])
                return (pub, repo, new_pub)

        @staticmethod
        def __update_ssl_creds(pub, repo, ssl_cert, ssl_key):
                errors = []
                # Assume the user wanted to update the ssl_cert or ssl_key
                # information for *all* of the currently selected
                # repository's origins and mirrors.
                origin = repo.origins[0]
                if not origin.uri.startswith("https"):
                        ssl_cert = None
                        ssl_key = None
                try:
                        for uri in repo.origins:
                                uri.ssl_cert = ssl_cert
                                uri.ssl_key = ssl_key
                        for uri in repo.mirrors:
                                uri.ssl_cert = ssl_cert
                                uri.ssl_key = ssl_key
                except api_errors.ApiException, e:
                        errors.append((pub, e))
                return errors

        @staticmethod
        def __get_fitr_model_from_tree(treeview):
                tsel = treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr == None:
                        return None
                model = selection[0]
                return (itr, model)

        @staticmethod
        def __show_error_label_with_format(w_label, error_string):
                error_str = ERROR_FORMAT % error_string
                w_label.set_markup(error_str)
                w_label.set_sensitive(True)
                w_label.show()

        def __is_url_valid(self, url):
                url_error = None
                if len(url) == 0:
                        return False, url_error
                try:
                        publisher.RepositoryURI(url)
                        return True, url_error
                except api_errors.PublisherError:
                        # Check whether the user has started typing a valid URL.
                        # If he has we do not display an error message.
                        valid_start = False
                        for val in publisher.SUPPORTED_SCHEMES:
                                check_str = "%s://" % val
                                if check_str.startswith(url):
                                        valid_start = True
                                        break 
                        if valid_start:
                                url_error = None
                        else:
                                url_error = _("URI is not valid")
                        return False, url_error
                except api_errors.ApiException, e:
                        self.__show_errors([("", e)])
                        return False, url_error

        @staticmethod
        def __validate_ssl_key_cert(origin_url, ssl_key, ssl_cert, 
            ignore_ssl_check_for_http = False):
                '''The SSL Cert and SSL Key may be valid and contain no error'''
                ssl_error = None
                ssl_valid = True
                if origin_url and origin_url.startswith("http:"):
                        if ignore_ssl_check_for_http:
                                return ssl_valid, ssl_error
                        if (ssl_key != None and len(ssl_key) != 0) or \
                            (ssl_cert != None and len(ssl_cert) != 0):
                                ssl_error = _("SSL should not be specified")
                                ssl_valid = False
                        elif (ssl_key == None or len(ssl_key) == 0) or \
                            (ssl_cert == None or len(ssl_cert) == 0):
                                ssl_valid = True
                elif origin_url == None or origin_url.startswith("https"):
                        if (ssl_key == None or len(ssl_key) == 0) or \
                            (ssl_cert == None or len(ssl_cert) == 0):
                                ssl_valid = False
                        elif not os.path.isfile(ssl_key):
                                ssl_error = _("SSL Key not found at specified location")
                                ssl_valid = False
                        elif not os.path.isfile(ssl_cert):
                                ssl_error = \
                                    _("SSL Certificate not found at specified location")
                                ssl_valid = False
                return ssl_valid, ssl_error

        @staticmethod
        def __init_mirrors_tree_view(treeview):
                # URI column - 0
                uri_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Mirror URI"),
                    uri_renderer,  text = 0)
                column.set_expand(True)
                treeview.append_column(column)

        @staticmethod
        def __init_origins_tree_view(treeview):
                # URI column - 0
                uri_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Origin URI"),
                    uri_renderer,  text = 0)
                column.set_expand(True)
                treeview.append_column(column)

        @staticmethod
        def __get_publishers_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,      # enumerations.PUBLISHER_PRIORITY
                        gobject.TYPE_INT,      # enumerations.PUBLISHER_PRIORITY_CHANGED
                        gobject.TYPE_STRING,   # enumerations.PUBLISHER_NAME
                        gobject.TYPE_STRING,   # enumerations.PUBLISHER_ALIAS
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_ENABLED
                        gobject.TYPE_PYOBJECT, # enumerations.PUBLISHER_OBJECT
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_ENABLE_CHANGED
                        gobject.TYPE_BOOLEAN,  # enumerations.PUBLISHER_REMOVED
                        )

        @staticmethod
        def __get_mirrors_origins_liststore():
                return gtk.ListStore(
                        gobject.TYPE_STRING,      # name
                        )

        @staticmethod
        def __publishers_filter(model, itr):
                return not model.get_value(itr, enumerations.PUBLISHER_REMOVED)

        @staticmethod
        def __toggle_data_function(column, renderer, model, itr, data):
                if itr:
                        # Do not allow to remove the publisher of first priority search
                        renderer.set_property("sensitive", (0 != model.get_value(itr, 
                            enumerations.PUBLISHER_PRIORITY_CHANGED)))

        @staticmethod
        def __get_registration_uri(repo):
                #TBD: Change Publisher API to return an RegistrationURI or a String
                # but not either.
                # Currently RegistrationURI is coming back with a trailing / this should
                # be removed.
                if repo == None:
                        return None
                if repo.registration_uri == None:
                        return None
                ret_uri = None
                if isinstance(repo.registration_uri, str):
                        if len(repo.registration_uri) > 0:
                                ret_uri = repo.registration_uri.strip("/")
                elif isinstance(repo.registration_uri, publisher.RepositoryURI):
                        uri = repo.registration_uri.uri
                        if uri != None and len(uri) > 0:
                                ret_uri = uri.strip("/")
                return ret_uri

#-----------------------------------------------------------------------------#
# Public Methods
#-----------------------------------------------------------------------------#
        def webinstall_new_pub(self, parent, pub = None):
                if pub == None:
                        return
                self.repository_modify_publisher = pub
                repo = pub.selected_repository
                origin_uri = repo.origins[0].uri
                if origin_uri != None and origin_uri.startswith("https"):
                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog, 
                            parent)
                        self.main_window = self.w_add_publisher_dialog
                        self.__on_manage_add_clicked(None)
                        self.w_add_publisher_url.set_text(origin_uri)
                        self.w_add_publisher_name.set_text(pub.prefix)
                        self.w_add_pub_label.hide()
                        self.w_add_pub_instr_label.hide()
                        self.w_add_publisher_url.set_sensitive(False)
                        self.w_add_publisher_name.set_sensitive(False)
                        reg_uri = self.__get_registration_uri(repo)
                        if reg_uri == None or len(reg_uri) == 0:
                                reg_uri = origin_uri
                        self.w_registration_link.set_uri(reg_uri)
                        self.w_registration_box.show()
                        self.w_ssl_box.show()
                        self.__validate_url(self.w_add_publisher_url,
                            w_ssl_key=self.w_key_entry, w_ssl_cert=self.w_cert_entry)
                        self.w_add_error_label.hide()
                else:
                        self.main_window = parent
                        self.w_ssl_box.hide()
                        self.__do_add_repository()

        def webinstall_enable_disable_pubs(self, parent, pub_names, to_enable):
                if pub_names == None:
                        return
                num = len(pub_names)
                if to_enable:
                        msg = ngettext("Enabling Publisher", "Enabling Publishers", num)
                else:
                        msg = ngettext("Disabling Publisher", "Disabling Publishers", num)
                self.publishers_apply.set_title(msg)

                self.__run_with_prog_in_thread(self.__proceed_enable_disable,
                    parent, None, pub_names, to_enable)

        def update_label_text(self, markup_text):
                self.__g_update_details_text(markup_text)

        def update_details_text(self, text, *tags):
                self.__g_update_details_text(text, *tags)

        def update_progress(self, current_progress, total_progress):
                pass

        def start_bouncing_progress(self):
                pass

        def is_progress_bouncing(self):
                self.pylintstub = self
                return True

        def stop_bouncing_progress(self):
                pass
