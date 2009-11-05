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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#


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
                self.publishers_list_filter = None
                self.progress_stop_thread = False
                self.repository_selection = None
                self.cancel_progress_thread = False
                self.cancel_function = None
                self.is_name_valid = False
                self.is_url_valid = False
                self.url_err = None
                self.name_error = None
                self.publisher_info = _("e.g. http://pkg.opensolaris.org/release")
                self.publishers_list = None
                self.repository_modify_publisher = None
                self.no_changes = 0
                w_tree_add_publisher = \
                    gtk.glade.XML(parent.gladefile, "add_publisher")
                w_tree_add_publisher_complete = \
                    gtk.glade.XML(parent.gladefile, "add_publisher_complete")
                w_tree_modify_repository = \
                    gtk.glade.XML(parent.gladefile, "modify_repository")
                w_tree_modify_publisher = \
                    gtk.glade.XML(parent.gladefile, "modify_publisher")
                w_tree_manage_publishers = \
                    gtk.glade.XML(parent.gladefile, "manage_publishers")
                w_tree_publishers_apply = \
                    gtk.glade.XML(parent.gladefile, "publishers_apply")
                # Dialog reused in the beadmin.py
                w_tree_confirmation = gtk.glade.XML(parent.gladefile,
                    "confirmationdialog")
                self.w_confirmation_dialog =  \
                    w_tree_confirmation.get_widget("confirmationdialog")
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
                self.w_addmirror_button = \
                    w_tree_modify_repository.get_widget("addmirror_button")
                self.w_rmmirror_button = \
                    w_tree_modify_repository.get_widget("mirrorremove")
                self.w_repositorymodifyok_button = \
                    w_tree_modify_repository.get_widget("repositorymodifyok")
                self.modify_repo_mirrors_treeview = \
                    w_tree_modify_repository.get_widget("modify_repo_mirrors_treeview")
                self.w_repositorymodify_url = \
                    w_tree_modify_repository.get_widget("repositorymodifyurl")
                self.w_modmirrerror_label = \
                    w_tree_modify_repository.get_widget("modmirrerror_label")
                self.w_moderror_label = \
                    w_tree_modify_repository.get_widget("moderror_label")
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
                self.w_modify_publisher_dialog = \
                    w_tree_modify_publisher.get_widget("modify_publisher")
                self.w_modify_publisher_dialog.set_icon(self.parent.window_icon)
                self.w_modify_pub_label = \
                    w_tree_modify_publisher.get_widget("modify_pub_label")
                self.w_modify_pub_alias = \
                    w_tree_modify_publisher.get_widget("modify_pub_alias")
                self.w_modify_pub_url = \
                    w_tree_modify_publisher.get_widget("modify_pub_url")
                self.modify_pub_repos_treeview = \
                    w_tree_modify_publisher.get_widget("modify_pub_repos_treeview")
                self.modify_pub_ok_btn = \
                    w_tree_modify_publisher.get_widget("modifypub_ok")
                self.pub_modify_repo_btn = \
                    w_tree_modify_publisher.get_widget("pub_modify_repo")
                self.w_modifypub_error_label = \
                    w_tree_modify_publisher.get_widget("modifypub_error_label")
                self.w_modifypub_details = \
                    w_tree_modify_publisher.get_widget("modifypub_details")
                self.w_manage_publishers_dialog = \
                    w_tree_manage_publishers.get_widget("manage_publishers")
                self.w_manage_publishers_dialog.set_icon(self.parent.window_icon)
                w_priorities_label = \
                    w_tree_manage_publishers.get_widget("priorities_label")
                # TODO: The priorities are not supported yet.
                w_priorities_label.set_property('visible', False)
                w_priorities_label.set_property('no-show-all', True)
                self.w_manage_publishers_details = \
                    w_tree_manage_publishers.get_widget("manage_publishers_details")
                modifypub_details_buf =  self.w_modifypub_details.get_buffer()
                manage_pub_details_buf =  self.w_manage_publishers_details.get_buffer()
                modifypub_details_buf.create_tag("level0", weight=pango.WEIGHT_BOLD)
                manage_pub_details_buf.create_tag("level0", weight=pango.WEIGHT_BOLD)
                self.w_manage_ok_btn = \
                    w_tree_manage_publishers.get_widget("manage_ok")
                self.w_manage_remove_btn = \
                    w_tree_manage_publishers.get_widget("manage_remove")
                self.w_manage_modify_btn = \
                    w_tree_manage_publishers.get_widget("manage_modify")
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
                        dic_modify_publisher = \
                            {
                                "on_modify_publisher_delete_event" : \
                                    self.__delete_widget_handler_hide,
                                "on_pub_modify_repo_clicked" : \
                                    self.__on_pub_modify_repo_clicked,
                                "on_modifypub_cancel_clicked" : \
                                    self.__on_modifypub_cancel_clicked,
                                "on_modifypub_ok_clicked" : \
                                    self.__on_modifypub_ok_clicked,
                                "on_modifypub_url_changed": \
                                    self.__on_modifypub_url_changed,
                                "on_modify_pub_help_clicked": \
                                    self.__on_modify_pub_help_clicked,
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
                                "on_repositorymodifyurl_changed": \
                                    self.__repositorymodifyurl_changed,
                                "on_addmirror_button_clicked": \
                                    self.__on_addmirror_button_clicked,
                                "on_repositorymodifyok_clicked": \
                                    self.__on_repositorymodifyok_clicked,
                                "on_mirrorremove_clicked": \
                                    self.__on_rmmirror_button_clicked,
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
                        w_tree_modify_publisher.signal_autoconnect(dic_modify_publisher)
                        w_tree_modify_repository.signal_autoconnect(dic_modify_repo)
                        w_tree_confirmation.signal_autoconnect(dic_confirmation)
                        w_tree_publishers_apply.signal_autoconnect(dic_apply)
                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check repository.py signals") \
                            % error

                self.publishers_list = self.__get_publishers_liststore()
                self.__init_pubs_tree_views()
                self.__init_mirrors_tree_views(self.modify_repo_mirrors_treeview)
                self.__init_repos_tree_views(self.modify_pub_repos_treeview)

                if self.action == enumerations.ADD_PUBLISHER:
                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog)
                        self.__on_manage_add_clicked(None)
                        return
                elif self.action == enumerations.MANAGE_PUBLISHERS:
                        self.__prepare_repository_list()
                        publisher_selection = self.w_publishers_treeview.get_selection()
                        publisher_selection.set_mode(gtk.SELECTION_SINGLE)
                        publisher_selection.connect("changed",
                            self.__on_publisher_selection_changed, None)
                        repository_selection = \
                            self.modify_pub_repos_treeview.get_selection()
                        repository_selection.set_mode(gtk.SELECTION_SINGLE)
                        repository_selection.connect("changed",
                            self.__on_repository_selection_changed, None)
                        mirrors_selection = \
                            self.modify_repo_mirrors_treeview.get_selection()
                        mirrors_selection.set_mode(gtk.SELECTION_SINGLE)
                        mirrors_selection.connect("changed",
                            self.__on_mirror_selection_changed, None)
                        gui_misc.set_modal_and_transient(self.w_add_publisher_dialog,
                            self.w_manage_publishers_dialog)
                        self.w_manage_publishers_dialog.show_all()
                        return

        def __init_pubs_tree_views(self):
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
                # Preferred column
                radio_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Preferred"),
                    radio_renderer, active = enumerations.PUBLISHER_PREFERRED)
                radio_renderer.set_property("activatable", True)
                radio_renderer.set_property("radio", True)
                column.set_expand(False)
                column.set_cell_data_func(radio_renderer,
                    self.__radio_data_function, None)
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
                self.publishers_list_filter = self.publishers_list.filter_new()
                self.publishers_list_filter.set_visible_func(self.__publishers_filter)
                self.w_publishers_treeview.set_model(self.publishers_list_filter)

        def __prepare_repository_list(self):
                self.no_changes = 0
                pubs = self.api_o.get_publishers(duplicate=True)
                model = self.w_publishers_treeview.get_model()
                if not model:
                        return
                self.w_publishers_treeview.set_model(None)
                self.publishers_list.clear()
                j = 0
                pref_pub = self.api_o.get_preferred_publisher()
                for pub in pubs:
                        name = pub.prefix
                        is_preferred = name == pref_pub.prefix
                        alias = pub.alias
                        # BUG: alias should be either "None" or None.
                        # in the list it's "None", but when adding pub it's None
                        if not alias or len(alias) == 0 or alias == "None":
                                alias = name
                        publisher_row = [j, name, alias, not pub.disabled, 
                            is_preferred, pub, False, False]
                        self.publishers_list.insert(j, publisher_row)
                        j += 1
                self.w_publishers_treeview.set_model(model)

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
                if name in [p.prefix for p in self.api_o.get_publishers()]:
                        self.name_error = _("Name already in use")
                        return False
                return True

        def __get_selected_publisher_itr_model(self):
                tsel = self.w_publishers_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr == None:
                        return None
                filt_model = selection[0]
                filt_path = filt_model.get_path(itr)
                path = filt_model.convert_path_to_child_path(filt_path)
                model = filt_model.get_model()
                f_itr = model.get_iter(path)
                return (f_itr, model)

        def __get_selected_mirror_itr_model(self):
                return self.__get_fitr_model_from_tree(\
                    self.modify_repo_mirrors_treeview)

        def __get_selected_repository_itr_model(self):
                return self.__get_fitr_model_from_tree(\
                    self.modify_pub_repos_treeview)

        def __modify_publisher_dialog(self, pub):
                self.__update_publisher_dialog(pub)
                self.__update_publisher_details(pub,
                    self.w_modifypub_details)
                gui_misc.set_modal_and_transient(self.w_modify_publisher_dialog,
                    self.w_manage_publishers_dialog)
                self.w_modify_publisher_dialog.show_all()

        def __update_publisher_dialog(self, pub, update_alias=True):
                pub = self.api_o.get_publisher(prefix=pub.prefix,
                    alias=pub.prefix, duplicate=True)
                selected_repo = pub.selected_repository
                origin = selected_repo.origins[0]
                prefix = ""
                alias = ""
                uri = ""
                if pub.prefix and len(pub.prefix) > 0:
                        prefix = pub.prefix
                if pub.alias and len(pub.alias) > 0 \
                    and pub.alias != "None":
                        alias = pub.alias
                if origin.uri and len(origin.uri) > 0:
                        uri = origin.uri
                self.w_modify_pub_label.set_text(prefix)
                if update_alias:
                        self.w_modify_pub_alias.set_text(alias)
                self.w_modify_pub_url.set_text(uri)
                repositories_list = self.__get_repositories_liststore()
                j = 0
                for repo in pub.repositories:
                        selected = False
                        if selected_repo == repo:
                                selected = True
                        name = uri
                        if repo.name and len(repo.name) > 0:
                                name = repo.name
                        repository = [name, selected, 'n/a', repo, pub]
                        repositories_list.insert(j, repository)
                        j += 1
                self.modify_pub_repos_treeview.set_model(repositories_list)

        def __modify_repository_dialog(self, pub, repository):
                self.repository_modify_publisher = \
                    self.api_o.get_publisher(prefix=pub.prefix,
                        alias=pub.prefix, duplicate=True)
                self.__update_repository_dialog(repository)
                gui_misc.set_modal_and_transient(self.w_modify_repository_dialog,
                    self.w_modify_publisher_dialog)
                self.w_modify_repository_dialog.show_all()

        def __update_repository_dialog(self, repository, expand=True, 
            update_ssl=True, update_url=True):
                name = ""
                ssl_cert = ""
                ssl_key = ""
                uri = None
                insert_count = 0
                mirrors_list = self.__get_mirrors_liststore()
                for mirr in repository.mirrors:
                        if mirr.ssl_cert:
                                ssl_cert = mirr.ssl_cert
                        if mirr.ssl_key:
                                ssl_key = mirr.ssl_key
                        mirror = [mirr.uri]
                        mirrors_list.insert(insert_count, mirror)
                        insert_count += 1
                for uri in repository.origins:
                        if uri.ssl_cert:
                                ssl_cert = uri.ssl_cert
                        if uri.ssl_key:
                                ssl_key = uri.ssl_key
                if expand == True:
                        if insert_count > 0:
                                self.w_repositorymirror_expander.set_expanded(True)
                        else:
                                self.w_repositorymirror_expander.set_expanded(False)
                        if len(ssl_cert) > 0 or len(ssl_key) > 0:
                                self.w_repositoryssl_expander.set_expanded(True)
                        else:
                                self.w_repositoryssl_expander.set_expanded(False)
                if update_ssl:
                        self.w_repositorymodify_cert_entry.set_text(ssl_cert)
                        self.w_repositorymodify_key_entry.set_text(ssl_key)
                if update_url:
                        self.w_repositorymodify_url.set_text(repository.origins[0].uri)
                self.modify_repo_mirrors_treeview.set_model(mirrors_list)
                if repository.name and len(repository.name) > 0:
                        name = repository.name
                reg_uri = self.__get_registration_uri(repository)
                if reg_uri != None:
                        self.w_repositorymodify_registration_link.set_uri(
                            reg_uri)
                        self.w_repositorymodify_registration_box.show()
                else:
                        self.w_repositorymodify_registration_box.hide()
                self.w_repositorymodify_name.set_text(name)
                self.modify_repo_mirrors_treeview.set_model(mirrors_list)

        def __add_mirror(self, new_mirror):
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                try:
                        # This part is copied from "def publisher_set(img, args)"
                        # from the client.py as the publisher API is not ready yet.
                        repo.add_mirror(new_mirror)
                        self.w_addmirror_entry.set_text("")
                except (api_errors.PublisherError,
                    api_errors.CertificateError), e:
                        gobject.idle_add(self.__show_errors, [(pub, e)])
                self.__update_repository_dialog(repo, 
                    expand=False, update_ssl=False, update_url=False)

        def __rm_mirror(self):
                itr, model = self.__get_selected_mirror_itr_model()
                remove_mirror = None
                if itr and model:
                        remove_mirror = model.get_value(itr, 0)
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                try:
                        repo.remove_mirror(remove_mirror)
                except api_errors.PublisherError, e:
                        gobject.idle_add(self.__show_errors, [(pub, e)])
                self.__update_repository_dialog(repo, 
                    expand=False, update_ssl=False, update_url=False)

        def __enable_disable(self, cell, filtered_path):
                filtered_model = self.w_publishers_treeview.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                model = filtered_model.get_model()
                itr = model.get_iter(path)
                if itr == None:
                        return
                preferred = model.get_value(itr, enumerations.PUBLISHER_PREFERRED)
                if preferred:
                        return
                enabled = model.get_value(itr, enumerations.PUBLISHER_ENABLED)
                changed = model.get_value(itr, enumerations.PUBLISHER_ENABLE_CHANGED)
                model.set_value(itr, enumerations.PUBLISHER_ENABLED, not enabled)
                model.set_value(itr, enumerations.PUBLISHER_ENABLE_CHANGED, not changed)

        def __is_enough_visible_pubs(self):
                model = self.w_publishers_treeview.get_model()
                if len(model) > 1:
                        return True
                return False

        def __enable_disable_remove_btn(self, itr):
                if itr:
                        if self.__is_enough_visible_pubs():
                                self.w_manage_remove_btn.set_sensitive(True)
                                return
                self.w_manage_remove_btn.set_sensitive(False)

        def __enable_disable_ok_btn(self):
                for row in self.publishers_list:
                        if row[enumerations.PUBLISHER_REMOVED] or \
                            row[enumerations.PUBLISHER_ENABLE_CHANGED]:
                                return True
                return False

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
                errors_update = self.__update_publisher(pub, new_publisher=new_pub)
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
                        except (api_errors.PermissionsException,
                            api_errors.PublisherError), e:
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
                                self.parent.reload_packages()

        def __update_publisher(self, pub, new_publisher=False):
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
                except api_errors.CatalogRefreshException, e:
                        errors.append((pub, e))
                except api_errors.InvalidDepotResponseException, e:
                        errors.append((pub, e))
                except (api_errors.PermissionsException,
                    api_errors.PublisherError), e:
                        errors.append((pub, e))
                return errors

        def __afteradd_confirmation(self, pub):
                repo = pub.selected_repository
                origin = repo.origins[0]
                # TODO: desc not available at the moment
                self.w_add_publisher_c_desc.hide()
                self.w_add_publisher_c_desc_l.hide()
                self.w_add_publisher_c_name.set_text(pub.prefix)
                self.w_add_publisher_c_url.set_text(origin.uri)
                self.w_add_publisher_comp_dialog.show()

        def __prepare_confirmation_dialog(self):
                disable_text = _("Disable Publisher:\n")
                enable_text = _("Enable Publisher:\n")
                delete_text = _("Delete Publishers:\n")
                # TODO: The priorities are not supported yet.
                # change_text = _("Change Priority:\n")
                # change = {}
                disable = ""
                enable = ""
                delete = ""
                for row in self.publishers_list:
                        pub_name = row[enumerations.PUBLISHER_NAME]
                        if row[enumerations.PUBLISHER_REMOVED]:
                                delete += pub_name + "\n"
                        elif row[enumerations.PUBLISHER_ENABLE_CHANGED]:
                                to_enable = row[enumerations.PUBLISHER_ENABLED]
                                if not to_enable:
                                        disable += pub_name + "\n"
                                else:
                                        enable += pub_name + "\n"
                textbuf = self.w_confirmation_textview.get_buffer()
                textbuf.set_text("")
                textiter = textbuf.get_end_iter()
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

                self.w_confirm_cancel_btn.grab_focus()
                self.w_confirmation_dialog.show_all()

        def __proceed_enable_disable(self, pub_names, to_enable):
                errors = []

                gobject.idle_add(self.publishers_apply_expander.set_expanded, True)
                for name in pub_names.keys():
                        try:
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
                        except (api_errors.PermissionsException,
                            api_errors.PublisherError), e:
                                errors.append(pub, e)
                self.progress_stop_thread = True
                gobject.idle_add(self.publishers_apply_expander.set_expanded, False)
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.parent.reload_packages)

        def __proceed_after_confirmation(self):
                errors = []
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
                        except (api_errors.PermissionsException,
                            api_errors.PublisherError), e:
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

        def __proceed_modifypub_ok(self):
                origin_url = self.w_modify_pub_url.get_text()
                alias = self.w_modify_pub_alias.get_text()
                name = self.w_modify_pub_label.get_text()
                pub = self.api_o.get_publisher(name, duplicate = True)
                repo = pub.selected_repository
                origin = repo.origins[0]
                origin.uri = origin_url
                pub.alias = alias
                errors = self.__update_publisher(pub, new_publisher=False)
                self.progress_stop_thread = True
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.__g_delete_widget_handler_hide,
                            self.w_modify_publisher_dialog, None)
                        if self.action == enumerations.MANAGE_PUBLISHERS:
                                gobject.idle_add(self.__prepare_repository_list)
                                self.no_changes += 1

        def __proceed_modifyrepo_ok(self):
                errors = []
                pub = self.repository_modify_publisher
                repo = pub.selected_repository
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                origin_url = self.w_repositorymodify_url.get_text()
                origin = repo.origins[0]
                origin.uri = origin_url
                errors += self.__update_ssl_creds(pub, repo, ssl_cert, ssl_key)
                errors += self.__update_publisher(pub, new_publisher=False)
                self.progress_stop_thread = True
                if len(errors) > 0:
                        gobject.idle_add(self.__show_errors, errors)
                else:
                        gobject.idle_add(self.__g_delete_widget_handler_hide,
                            self.w_modify_repository_dialog, None)
                gobject.idle_add(self.__update_publisher_dialog, pub, False)

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
                model, itr = selection.get_selected()
                if itr:
                        self.__update_publisher_details(
                            model.get_value(itr, enumerations.PUBLISHER_OBJECT),
                            self.w_manage_publishers_details)
                        if model.get_value(itr, enumerations.PUBLISHER_PREFERRED):
                                itr = None
                else:
                        selection.select_path(0)
                        self.__update_publisher_details(None,
                            self.w_manage_publishers_details)
                self.__enable_disable_remove_btn(itr)

        def __on_repository_selection_changed(self, selection, widget):
                model_itr = selection.get_selected()
                if model_itr[1]:
                        self.pub_modify_repo_btn.set_sensitive(True)
                else:
                        self.pub_modify_repo_btn.set_sensitive(False)

        def __on_mirror_selection_changed(self, selection, widget):
                model_itr = selection.get_selected()
                if model_itr[1]:
                        self.w_rmmirror_button.set_sensitive(True)
                else:
                        self.w_rmmirror_button.set_sensitive(False)

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
                                self.__prepare_repository_list()
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
                self.__repositorymodifyurl_changed(self.w_repositorymodify_url)

        @staticmethod
        def __is_pub_modified():
                return True

        def __on_modifypub_url_changed(self, widget):
                self.__validate_url_generic(widget, self.w_modifypub_error_label,
                    self.modify_pub_ok_btn, name_valid=True,
                    function=self.__is_pub_modified)

        def __on_addmirror_entry_changed(self, widget):
                error_text = ""
                url_error = None
                mirror_url = widget.get_text()
                origin_url = self.w_repositorymodify_url.get_text()
                is_url_valid, url_error = self.__is_url_valid(mirror_url)
                # http: and https: are being only checked when someone types the prefix
                if len(mirror_url) <= 4:
                        if is_url_valid == False and url_error != None:
                                self.__show_error_label_with_format(
                                    self.w_modmirrerror_label, url_error)
                        else:
                                self.w_modmirrerror_label.set_text(self.publisher_info)
                                self.w_modmirrerror_label.set_markup(self.publisher_info)
                                self.w_modmirrerror_label.set_sensitive(False)
                        self.w_addmirror_button.set_sensitive(False)
                        return
                is_origin_ssl = origin_url.startswith("https")
                is_mirror_ssl = mirror_url.startswith("https")
                if (is_mirror_ssl and is_origin_ssl) or \
                    (not is_mirror_ssl and not is_origin_ssl) :
                        if is_url_valid == False and url_error != None:
                                self.__show_error_label_with_format(
                                    self.w_modmirrerror_label, url_error)
                        else:
                                self.w_modmirrerror_label.set_text(self.publisher_info)
                                self.w_modmirrerror_label.set_markup(self.publisher_info)
                                self.w_modmirrerror_label.set_sensitive(False)
                        self.w_addmirror_button.set_sensitive(is_url_valid)
                        return
                elif is_mirror_ssl:
                        error_text = _("Mirrors and repository URL\n"
                            "must be either https or http.")
                elif is_origin_ssl:
                        # Mirror is not ssl, but origin is
                        error_text = _("Mirrors and repository URL\n"
                            "must be either https or http.")
                if error_text != "":
                        self.__show_error_label_with_format(
                            self.w_modmirrerror_label, error_text)
                        self.w_addmirror_button.set_sensitive(False)

        def __repositorymodifyurl_changed(self, widget):
                self.w_moderror_label.set_markup(self.publisher_info)
                self.w_moderror_label.set_sensitive(False)
                self.w_modsslerror_label.hide()
                valid_url = True
                valid_ssl = True
                pub = self.repository_modify_publisher
                repository = pub.selected_repository
                url = widget.get_text()
                ssl_key = self.w_repositorymodify_key_entry.get_text()
                ssl_cert = self.w_repositorymodify_cert_entry.get_text()
                is_origin_ssl = url.startswith("https")
                if is_origin_ssl:
                        self.w_repositoryssl_expander.set_expanded(True)
                is_url_valid, url_error = self.__is_url_valid(url)
                if len(repository.mirrors) > 0:
                        are_mirrors_ssl = \
                            self.__check_if_all_mirrors_are_ssl(repository.mirrors)
                        if are_mirrors_ssl and not is_origin_ssl:
                                url_error = _("SSL URL should be specified")
                                self.__show_error_label_with_format(
                                    self.w_moderror_label, url_error)
                                valid_url = False
                        elif not are_mirrors_ssl and is_origin_ssl:
                                url_error = _("SSL URL should not be specified")
                                self.__show_error_label_with_format(
                                    self.w_moderror_label, url_error)
                                valid_url = False
                ssl_valid, ssl_error = self.__validate_ssl_key_cert(url, ssl_key,
                    ssl_cert, ignore_ssl_check_for_http=False)
                self.__on_addmirror_entry_changed(self.w_addmirror_entry)
                if is_url_valid == False and url_error != None:
                        self.__show_error_label_with_format(
                            self.w_moderror_label, url_error)
                        valid_url = False
                if not is_origin_ssl and ssl_valid == False and ssl_error != None:
                        self.__show_error_label_with_format(
                            self.w_moderror_label, ssl_error)
                        valid_ssl = False
                elif is_origin_ssl and ssl_error != None:
                        self.__show_error_label_with_format(
                            self.w_modsslerror_label, ssl_error)
                        valid_ssl = False
                elif is_origin_ssl:
                        if len(ssl_key) == 0 or len(ssl_cert) == 0:
                                valid_ssl = False
                self.w_repositorymodifyok_button.set_sensitive(valid_url and valid_ssl)

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
                pub = model.get_value(itr, enumerations.PUBLISHER_OBJECT)
                self.__modify_publisher_dialog(pub)

        def __on_manage_remove_clicked(self, widget):
                itr, model = self.__get_selected_publisher_itr_model()
                if itr and model:
                        model.set_value(itr, enumerations.PUBLISHER_REMOVED, True)

        def __on_manage_move_up_clicked(self, widget):
                # TODO: The priorities are not supported yet.
                pass

        def __on_manage_move_down_clicked(self, widget):
                # TODO: The priorities are not supported yet.
                pass

        def __on_manage_cancel_clicked(self, widget):
                self.__on_manage_publishers_delete_event(
                    self.w_manage_publishers_dialog, None)

        def __on_manage_ok_clicked(self, widget):
                if self.__enable_disable_ok_btn():
                        self.__prepare_confirmation_dialog()
                else:
                        self.__on_manage_cancel_clicked(None)

        def __on_pub_modify_repo_clicked(self, widget):
                itr, model = self.__get_selected_repository_itr_model()
                pub = model.get_value(itr,
                    enumerations.MREPOSITORY_PUB_OBJECT)
                repository = model.get_value(itr,
                    enumerations.MREPOSITORY_OBJECT)
                self.__modify_repository_dialog(pub, repository)

        def __on_modifypub_cancel_clicked(self, widget):
                self.__delete_widget_handler_hide(
                    self.w_modify_publisher_dialog, None)

        def __on_modifypub_ok_clicked(self, widget):
                if self.modify_pub_ok_btn.get_property('sensitive') == 0:
                        return
                self.publishers_apply.set_title(_("Applying Changes"))
                self.__run_with_prog_in_thread(self.__proceed_modifypub_ok,
                    self.w_modify_publisher_dialog)

        def __on_publishers_apply_delete_event(self, widget, event):
                self.__on_apply_cancel_clicked(None)
                return True

        def __on_addmirror_button_clicked(self, widget):
                if self.w_addmirror_button.get_property('sensitive') == 0:
                        return
                new_mirror = self.w_addmirror_entry.get_text()
                self.__add_mirror(new_mirror)
                self.__repositorymodifyurl_changed(self.w_repositorymodify_url)

        def __on_rmmirror_button_clicked(self, widget):
                self.__rm_mirror()
                self.__repositorymodifyurl_changed(self.w_repositorymodify_url)
                
        def __on_repositorymodifyok_clicked(self, widget):
                if self.w_repositorymodifyok_button.get_property('sensitive') == 0:
                        return
                self.publishers_apply.set_title(_("Applying Changes"))
                self.__run_with_prog_in_thread(self.__proceed_modifyrepo_ok,
                    self.w_modify_repository_dialog)

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
        def __on_add_pub_help_clicked(widget):
                gui_misc.display_help("add_repo")

        @staticmethod
        def __on_manage_help_clicked(widget):
                gui_misc.display_help("manage_repo")

        @staticmethod
        def __on_modify_pub_help_clicked(widget):
                gui_misc.display_help("manage_repo")

        @staticmethod
        def __on_modify_repo_help_clicked(widget):
                gui_misc.display_help("manage_repo")

        @staticmethod
        def __update_publisher_details(pub, details_view):
                if pub == None:
                        return
                details_buffer = details_view.get_buffer()
                details_buffer.set_text("")
                uri_s_itr = details_buffer.get_start_iter()
                details_buffer.insert_with_tags_by_name(uri_s_itr,
                    _("Publisher URI:\n"), "level0")
                repo = pub.selected_repository
                origin = repo.origins[0]
                uri_itr = details_buffer.get_end_iter()
                details_buffer.insert(uri_itr, "%s\n" % origin.uri)
                description = ""
                if repo.description:
                        description = repo.description
                if len(description) > 0:
                        desc_s_itr = details_buffer.get_end_iter()
                        details_buffer.insert_with_tags_by_name(desc_s_itr,
                            _("Description:\n"), "level0")
                        desc_itr = details_buffer.get_end_iter()
                        details_buffer.insert(desc_itr, "%s\n" % description)

        @staticmethod
        def __show_errors(errors, msg_type=gtk.MESSAGE_ERROR, title = None):
                error_msg = ""
                if title != None:
                        msg_title = title
                else:   # More Generic for WebInstall
                        msg_title = _("Publisher error")
                for err in errors:
                        error_msg += str(err[1]) + "\n\n"
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

        @staticmethod
        def __get_or_create_pub_with_url(api_o, name, origin_url):
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
                except (api_errors.PublisherError,
                    api_errors.CertificateError), e:
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

        @staticmethod
        def __is_url_valid(url):
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
                                url_error = _("URL is not valid")
                        return False, url_error

        @staticmethod
        def __validate_ssl_key_cert(origin_url, ssl_key, ssl_cert, 
            ignore_ssl_check_for_http = False):
                '''The SSL Cert and SSL Key may be valid and contain no error'''
                ssl_error = None
                ssl_valid = True
                if origin_url.startswith("http:"):
                        if ignore_ssl_check_for_http:
                                return ssl_valid, ssl_error
                        if (ssl_key != None and len(ssl_key) != 0) or \
                            (ssl_cert != None and len(ssl_cert) != 0):
                                ssl_error = _("SSL should not be specified")
                                ssl_valid = False
                        elif (ssl_key == None or len(ssl_key) == 0) or \
                            (ssl_cert == None or len(ssl_cert) == 0):
                                ssl_valid = True
                elif origin_url.startswith("https"):
                        if (ssl_key == None or len(ssl_key) == 0) or \
                            (ssl_cert == None or len(ssl_cert) == 0):
                                ssl_valid = False
                        elif not os.path.isfile(ssl_key):
                                ssl_error = _("SSL Key not found at specified path")
                                ssl_valid = False
                        elif not os.path.isfile(ssl_cert):
                                ssl_error = \
                                    _("SSL Certificate not found at specified path")
                                ssl_valid = False
                return ssl_valid, ssl_error

        @staticmethod
        def __check_if_all_mirrors_are_ssl(mirrors):
                are_mirrors_ssl = False
                if mirrors:
                        for mirr in mirrors:
                                if mirr.uri.startswith("https"):
                                        are_mirrors_ssl = True
                                        break
                return are_mirrors_ssl

        @staticmethod
        def __init_repos_tree_views(treeview):
                # Name column
                name_renderer = gtk.CellRendererText()
                name_renderer.set_property("ellipsize", pango.ELLIPSIZE_END)
                column = gtk.TreeViewColumn(_("Repository"),
                    name_renderer, text = enumerations.MREPOSITORY_NAME)
                column.set_expand(True)
                treeview.append_column(column)
                # Active column
                radio_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Active"),
                    radio_renderer, active = enumerations.MREPOSITORY_ACTIVE)
                radio_renderer.set_property("activatable", True)
                radio_renderer.set_property("radio", True)
                column.set_expand(False)
                treeview.append_column(column)
                # Registered column
                alias_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Registered"),
                    alias_renderer,  markup = enumerations.MREPOSITORY_REGISTERED)
                column.set_expand(False)
                treeview.append_column(column)

        @staticmethod
        def __init_mirrors_tree_views(treeview):
                # Name column - 0
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Mirror Name"),
                    name_renderer,  text = 0)
                column.set_expand(True)
                treeview.append_column(column)

        @staticmethod
        def __get_publishers_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.PUBLISHER_PRIORITY
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_NAME
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_ALIAS
                        gobject.TYPE_BOOLEAN,     # enumerations.PUBLISHER_ENABLED
                        gobject.TYPE_BOOLEAN,     # enumerations.PUBLISHER_PREFERRED
                        gobject.TYPE_PYOBJECT,    # enumerations.PUBLISHER_OBJECT
                        gobject.TYPE_BOOLEAN,     # enumerations.PUBLISHER_ENABLE_CHANGED
                        gobject.TYPE_BOOLEAN,     # enumerations.PUBLISHER_REMOVED
                        )

        @staticmethod
        def __get_repositories_liststore():
                return gtk.ListStore(
                        gobject.TYPE_STRING,      # enumerations.MREPOSITORY_NAME
                        gobject.TYPE_BOOLEAN,     # enumerations.MREPOSITORY_ACTIVE
                        gobject.TYPE_STRING,      # enumerations.MREPOSITORY_REGISTERED
                        gobject.TYPE_PYOBJECT,    # enumerations.MREPOSITORY_OBJECT
                        gobject.TYPE_PYOBJECT,    # enumerations.MREPOSITORY_PUB_OBJECT
                        )

        @staticmethod
        def __get_mirrors_liststore():
                return gtk.ListStore(
                        gobject.TYPE_STRING,      # name
                        )

        @staticmethod
        def __publishers_filter(model, itr):
                return not model.get_value(itr, enumerations.PUBLISHER_REMOVED)

        @staticmethod
        def __toggle_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 
                            not model.get_value(itr, 
                            enumerations.PUBLISHER_PREFERRED))

        @staticmethod
        def __radio_data_function(column, renderer, model, itr, data):
                # TODO: The priority will take over preferred, so 
                # we do not allow to change preferred.
                if itr:
                        renderer.set_property("sensitive", False)

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
                return True

        def stop_bouncing_progress(self):
                pass
