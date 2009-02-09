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
from threading import Thread

try:
        import gobject
        gobject.threads_init()
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
except ImportError:
        sys.exit(1)

import pkg.client.api_errors as api_errors
import pkg.misc as misc
import pkg.gui.enumerations as enumerations

ERROR_FORMAT = "<span color = \"red\">%s</span>"

class Repository:
        def __init__(self, parent):
                self.parent = parent
                self.img = parent.api_o.img

                self.repository_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,      # enumerations.AUTHORITY_NAME
                        gobject.TYPE_BOOLEAN,     # enumerations.AUTHORITY_PREFERRED
                        gobject.TYPE_STRING,      # enumerations.AUTHORITY_URL
                        gobject.TYPE_STRING,      # enumerations.AUTHORITY_SSL_KEY
                        gobject.TYPE_STRING,      # enumerations.AUTHORITY_SSL_CERT
                        gobject.TYPE_PYOBJECT,    # enumerations.AUTHORITY_MIRRORS
                        gobject.TYPE_BOOLEAN,     # enumerations.AUTHORITY_ENABLED
                        )
                self.mirror_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,      # URL
                        )
                self.progress_stop_thread = False
                self.number_of_changes = 0
                self.initial_default = 0
                w_tree_repository = gtk.glade.XML(parent.gladefile, "repository")
                w_tree_repositorymodify = \
                        gtk.glade.XML(parent.gladefile, "repositorymodif")
                w_tree_sslkeyandcert_dialog = \
                        gtk.glade.XML(parent.gladefile, "sslkeyandcertdialog")
                w_tree_progress = gtk.glade.XML(parent.gladefile, "progressdialog")
                self.w_progress_dialog = w_tree_progress.get_widget("progressdialog")
                self.w_progressinfo_label = w_tree_progress.get_widget("progressinfo")
                progress_button = w_tree_progress.get_widget("progresscancel")
                self.w_progressbar = w_tree_progress.get_widget("progressbar")
                self.w_repository_dialog = w_tree_repository.get_widget("repository")
                self.w_repository_name = w_tree_repository.get_widget("repositoryname")
                self.w_repository_url = w_tree_repository.get_widget("repositoryurl")
                self.w_repository_treeview = \
                        w_tree_repository.get_widget("repositorytreeview")
                self.w_repository_close_button = \
                        w_tree_repository.get_widget("repositoryclose")
                self.w_repository_add_button = \
                        w_tree_repository.get_widget("repositoryadd")
                self.w_repository_modify_button = \
                        w_tree_repository.get_widget("repositorymodify")
                self.w_repository_remove_button = \
                        w_tree_repository.get_widget("repositoryremove")
                self.repository_list_filter = self.repository_list.filter_new()
                self.w_repository_error_label = \
                        w_tree_repository.get_widget("error_label")
                self.w_repository_add_button.set_sensitive(False)
                self.w_repository_modify_button.set_sensitive(True)
                self.w_repository_remove_button.set_sensitive(False)

                self.w_repositorymodify_dialog = \
                    w_tree_repositorymodify.get_widget("repositorymodif")
                self.w_repositorymodify_name = \
                    w_tree_repositorymodify.get_widget("repositorymodifyname")
                self.w_repositorymodify_url = \
                    w_tree_repositorymodify.get_widget("repositorymodifyurl")
                self.w_repositorymodify_keybrowse_button = \
                    w_tree_repositorymodify.get_widget("modkeybrowse")
                self.w_repositorymodify_certbrowse_button = \
                    w_tree_repositorymodify.get_widget("modcertbrowse")
                self.w_repositorymodify_key_entry = \
                    w_tree_repositorymodify.get_widget("modkeyentry")
                self.w_repositorymodify_cert_entry = \
                    w_tree_repositorymodify.get_widget("modcertentry")
                self.w_repositorymodify_ok_button = \
                    w_tree_repositorymodify.get_widget("repositorymodifyok")
                self.w_repositorymodify_cancel_button = \
                    w_tree_repositorymodify.get_widget("repositorymodifycancel")
                self.w_mirror_treeview = \
                    w_tree_repositorymodify.get_widget("mirrortreeview")
                self.mirror_list_filter = self.mirror_list.filter_new()
                self.w_mirror_add_entry = \
                    w_tree_repositorymodify.get_widget("addmirror_entry")
                self.w_mirror_add_button = \
                    w_tree_repositorymodify.get_widget("addmirror_button")
                self.w_mirror_remove_button = \
                    w_tree_repositorymodify.get_widget("mirrorremove")

                #Modify name of the repository is disabled, see #4990
                self.w_repositorymodify_name.set_sensitive(False)

                self.w_repository_url.connect('focus-in-event', self.on_focus_in_url)
                self.w_repository_name.connect('focus-in-event', self.on_focus_in_name)
                self.w_repository_treeview.connect('focus-in-event', 
                    self.on_focus_in_repository_treeview)
                self.w_repository_treeview.connect_after('move-cursor', 
                    self.__on_repositorytreeview_move_cursor)
                self.w_repository_add_button.connect('focus-in-event', self.on_focus_in)
                self.w_repository_close_button.connect('focus-in-event', self.on_focus_in)
                self.w_repository_add_button.connect('focus-in-event', self.on_focus_in)

                self.w_sslkeyandcert_dialog = \
                    w_tree_sslkeyandcert_dialog.get_widget("sslkeyandcertdialog")
                self.w_sslkeyandcert_keybrowse_button = \
                    w_tree_sslkeyandcert_dialog.get_widget("keybrowse")
                self.w_sslkeyandcert_certbrowse_button = \
                    w_tree_sslkeyandcert_dialog.get_widget("certbrowse")
                self.w_sslkeyandcert_key_entry = \
                    w_tree_sslkeyandcert_dialog.get_widget("keyentry")
                self.w_sslkeyandcert_cert_entry = \
                    w_tree_sslkeyandcert_dialog.get_widget("certentry")
                self.w_sslkeyandcert_ok_button = \
                    w_tree_sslkeyandcert_dialog.get_widget("keyandcertok")
                self.w_sslkeyandcert_cancel_button = \
                    w_tree_sslkeyandcert_dialog.get_widget("keyandcertcancel")

                progress_button.hide()
                self.w_progressbar.set_pulse_step(0.1)

                self.__init_tree_views()
                self.w_progress_dialog.set_transient_for(self.w_repository_dialog)
                self.w_sslkeyandcert_dialog.set_transient_for(self.w_repository_dialog)
                self.w_repositorymodify_dialog.set_transient_for(self.w_repository_dialog)
                self.old_modify_name = None
                self.old_modify_url = None
                self.old_modify_preferred = False
                self.old_modify_ssl_key = None
                self.old_modify_ssl_cert = None
                self.is_name_valid = False
                self.is_url_valid = False
                self.name_error = None
                self.original_preferred = None
                self.preferred = None
                self.url_error = None

                try:
                        dic = \
                            {
                                "on_repository_delete_event": \
                                    self.__on_repository_delete_event,
                                "on_repositoryadd_clicked": \
                                    self.__on_repositoryadd_clicked,
                                "on_repositorymodify_clicked": \
                                    self.__on_repositorymodify_clicked,
                                "on_repositoryremove_clicked": \
                                    self.__on_repositoryremove_clicked,
                                "on_repositoryclose_clicked": \
                                    self.__on_repositoryclose_clicked,
                                "on_repositoryurl_changed": \
                                    self.__on_repositoryurl_changed,
                                "on_repositoryname_changed": \
                                    self.__on_repositoryname_changed,
                                "on_repositorytreeview_button_release_event": \
                                    self.__on_repositorytreeview_button_release_event,
                            }
                        dic_conf = \
                            {
                                "on_repositorymodif_delete_event": \
                                    self.__on_repositorymodify_delete_event,
                                "on_repositorymodifycancel_clicked": \
                                    self.__on_repositorymodifycancel_clicked,
                                "on_repositorymodifyok_clicked": \
                                    self.__on_repositorymodifyok_clicked,
                                "on_sslkeybrowse_clicked": \
                                    self.__on_modify_keybrowse_clicked,
                                "on_sslcertbrowse_clicked": \
                                    self.__on_modify_certbrowse_clicked,
                                "on_mirrorremove_clicked": \
                                    self.__on_mirror_remove_clicked,
                                "on_addmirror_button_clicked": \
                                    self.__on_mirroradd_button_clicked,
                                "on_addmirror_entry_changed": \
                                    self.__on_mirrorentry_changed,
                                "on_modkeyentry_changed": \
                                    self.__on_mod_key_or_cert_entry_changed,
                                "on_modcertentry_changed": \
                                    self.__on_mod_key_or_cert_entry_changed,
                            }            
                        dic_ssl = \
                            {
                                "on_sslkeyandcertdialog_delete_event": \
                                    self.__on_sslkeyandcert_dialog_delete_event,
                                "on_keyentry_changed": \
                                    self.__on_key_or_cert_entry_changed,
                                "on_certentry_changed": \
                                    self.__on_key_or_cert_entry_changed,
                                "on_sslkeyandcertcancel_clicked": \
                                    self.__on_sslkeyandcertcancel_clicked,
                                "on_sslkeyandcertok_clicked": \
                                    self.__on_sslkeyandcertok_clicked,
                                "on_keybrowse_clicked": \
                                    self.__on_keybrowse_clicked,
                                "on_certbrowse_clicked": \
                                    self.__on_certbrowse_clicked,
                            }            
                        w_tree_repository.signal_autoconnect(dic)
                        w_tree_repositorymodify.signal_autoconnect(dic_conf)
                        w_tree_sslkeyandcert_dialog.signal_autoconnect(dic_ssl)
                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check repository.py signals") \
                            % error

                Thread(target = self.__prepare_repository_list).start()
                self.w_repository_dialog.show_all()
                self.w_repository_error_label.hide()

        def on_focus_in(self, widget, event):
                self.w_repository_modify_button.set_sensitive(False)
                self.w_repository_remove_button.set_sensitive(False)

        def on_focus_in_name(self, widget, event):
                self.__validate_name(widget)
                self.w_repository_modify_button.set_sensitive(False)
                self.w_repository_remove_button.set_sensitive(False)

        def on_focus_in_url(self, widget, event):
                self.__validate_url(widget)
                self.w_repository_modify_button.set_sensitive(False)
                self.w_repository_remove_button.set_sensitive(False)

        def on_focus_in_repository_treeview(self, widget, event):
                self.__on_repositorytreeview_selection_changed(widget)

        def __init_tree_views(self):
                repository_list_sort = gtk.TreeModelSort(self.repository_list_filter)
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Repository Name"),
                    name_renderer,  text = enumerations.AUTHORITY_NAME)
                column.set_expand(True)
                column.set_sort_column_id(enumerations.AUTHORITY_NAME)
                column.set_sort_indicator(True)
                column.set_cell_data_func(name_renderer,
                    self.name_data_function, None)
                self.w_repository_treeview.append_column(column)
                radio_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Preferred"),
                    radio_renderer, active = enumerations.AUTHORITY_PREFERRED)
                radio_renderer.set_property("activatable", True)
                radio_renderer.set_property("radio", True)
                column.set_expand(False)
                column.set_sort_column_id(enumerations.AUTHORITY_PREFERRED)
                column.set_sort_indicator(True)
                radio_renderer.connect('toggled', self.__preferred_default)
                column.set_cell_data_func(radio_renderer,
                    self.radio_data_function, None)
                self.w_repository_treeview.append_column(column)
                toggle_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Enabled"),
                    toggle_renderer, active = enumerations.AUTHORITY_ENABLED)
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)
                column.set_sort_column_id(enumerations.AUTHORITY_ENABLED)
                column.set_sort_indicator(True)
                toggle_renderer.connect('toggled', self.__enable_disable)
                column.set_cell_data_func(toggle_renderer, 
                    self.toggle_data_function, None)
                self.w_repository_treeview.append_column(column)
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn("",
                    name_renderer,  text = 0) # 0 = Mirror
                column.set_expand(True)
                self.w_mirror_treeview.append_column(column)
                self.w_repository_treeview.set_model(repository_list_sort)

        def __prepare_repository_list(self, clear_add_entries=True, selected_auth=None,
            stop_thread=True):
                self.number_of_changes += 1
                self.img.load_config()
                auths = self.img.gen_authorities(inc_disabled=True)
                gobject.idle_add(self.__create_view_with_auths, auths,
                    clear_add_entries, selected_auth)
                if stop_thread:
                        self.progress_stop_thread = True
                return

        def __create_view_with_auths(self, auths, clear_add_entries, selected_auth):
                model = self.w_repository_treeview.get_model()
                self.w_repository_treeview.set_model(None)
                self.repository_list.clear()
                if clear_add_entries:
                        self.w_repository_name.set_text("")
                        self.w_repository_url.set_text("")
                self.w_repository_name.grab_focus()
                j = 0
                select_auth = -1
                self.preferred = self.img.get_default_authority()
                self.original_preferred = self.preferred
                for a in auths:
                        l = self.img.split_authority(a)
                        name = l[0]
                        is_preferred = name == self.preferred
                        if is_preferred:
                                self.initial_default = j
                        if selected_auth:
                                if name == selected_auth:
                                        select_auth = j
                        self.repository_list.insert(j, 
                            [name, is_preferred, l[1], l[2], l[3], l[5], \
                            not a["disabled"]])
                        j += 1
                if j > 0:
                        self.w_repository_modify_button.set_sensitive(False)
                        self.w_repository_remove_button.set_sensitive(False)
                self.w_repository_treeview.set_model(model)
                if select_auth == -1:
                        select_auth = self.initial_default
                self.w_repository_treeview.set_cursor(select_auth,
                    None, start_editing=False)
                self.w_repository_treeview.scroll_to_cell(select_auth)

        @staticmethod
        def name_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 

                            model.get_value(itr, enumerations.AUTHORITY_ENABLED))

        @staticmethod
        def radio_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 
                            model.get_value(itr, enumerations.AUTHORITY_ENABLED))

        @staticmethod
        def toggle_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 
                            not model.get_value(itr, 
                            enumerations.AUTHORITY_PREFERRED))

        def __enable_disable(self, cell, filtered_path):
                sorted_model = self.w_repository_treeview.get_model()
                filtered_model = sorted_model.get_model()
                model = filtered_model.get_model()
                path = sorted_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr:
                        preferred = model.get_value(itr, 
                            enumerations.AUTHORITY_PREFERRED)
                        if preferred == True:
                                return
                        enabled = model.get_value(itr,
                            enumerations.AUTHORITY_ENABLED)
                        auth = model.get_value(itr, enumerations.AUTHORITY_NAME)
                        try:
                                self.img.set_authority(auth,
                                    refresh_allowed=False,
                                    disabled=enabled)
                                self.number_of_changes += 1
                                model.set_value(itr, 
                                    enumerations.AUTHORITY_ENABLED,
                                    not enabled)
                        except RuntimeError, ex:
                                if enabled:
                                        err = _("Failed to disable %s.") % auth
                                else:
                                        err = _("Failed to enable %s.") % auth
                                err += str(ex)
                                self.__error_occurred(err,
                                    msg_type=gtk.MESSAGE_INFO)
                                self.__prepare_repository_list()
                        except api_errors.PermissionsException:
                                if enabled:
                                        err1 = _("Failed to disable %s.") % auth
                                else:
                                        err1 = _("Failed to enable %s.") % auth
                                err = err1 + _("\nPlease check your permissions.")
                                self.__error_occurred(err,
                                    msg_type=gtk.MESSAGE_INFO)
                                self.__prepare_repository_list()
                        except api_errors.CatalogRefreshException:
                                if enabled:
                                        err1 = _("Failed to disable %s.") % auth
                                else:
                                        err1 = _("Failed to enable %s.") % auth
                                err = err1 + _(
                                    "\nPlease check the network connection or URL.\n"
                                    "Is the repository accessible?")
                                self.__error_occurred(err,
                                    msg_type=gtk.MESSAGE_INFO)
                                self.__prepare_repository_list()

        def __preferred_default(self, cell, filtered_path):
                sorted_model = self.w_repository_treeview.get_model()
                filtered_model = sorted_model.get_model()
                model = filtered_model.get_model()
                path = sorted_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr:
                        preferred = model.get_value(itr, 
                            enumerations.AUTHORITY_PREFERRED)
                        enabled = model.get_value(itr,
                            enumerations.AUTHORITY_ENABLED)
                        if preferred == False and enabled == True:
                                auth = model.get_value(itr, 
                                    enumerations.AUTHORITY_NAME)
                                try:
                                        self.img.set_preferred_authority(auth)
                                        self.preferred = auth
                                        index = enumerations.AUTHORITY_PREFERRED
                                        for row in model:
                                                row[index] = False
                                        model.set_value(itr, 
                                            enumerations.AUTHORITY_PREFERRED,
                                            not preferred)
                                except api_errors.PermissionsException:
                                        err = _("Couldn't change"
                                            " the preferred authority.\n"
                                            "Please check your permissions.")
                                        self.__error_occurred(err,
                                            msg_type=gtk.MESSAGE_INFO) 
                                        self.__prepare_repository_list()

        def __progress_pulse(self):
                if not self.progress_stop_thread:
                        self.w_progressbar.pulse()
                        return True
                else:
                        self.w_progress_dialog.hide()
                        return False


        def __on_repositoryurl_changed(self, widget):
                self.__validate_url(widget)

        def __validate_url(self, widget):
                url = widget.get_text()
                self.is_url_valid = self.__is_url_valid(url)
                self.w_repository_error_label.hide()
                if self.is_url_valid:
                        if self.is_name_valid:
                                self.w_repository_add_button.set_sensitive(True)
                        else:
                                self.w_repository_add_button.set_sensitive(False)
                                if self.name_error != None:
                                        error_str = ERROR_FORMAT % self.name_error
                                        self.w_repository_error_label.set_markup(
                                            error_str)
                                        self.w_repository_error_label.show()
                else:
                        self.w_repository_add_button.set_sensitive(False)
                        if self.url_error != None:
                                error_str = ERROR_FORMAT % self.url_error
                                self.w_repository_error_label.set_markup(error_str)
                                self.w_repository_error_label.show()
                        
        def __is_name_valid(self, name):
                self.name_error = None
                if len(name) == 0:
                        return False
                if not misc.valid_auth_prefix(name):
                        self.name_error = _("Name contains invalid characters")
                        return False

                model = self.w_repository_treeview.get_model()
                if model:
                        for row in model:
                                if row[0] == name:
                                        self.name_error = _("Name already in use")
                                        return False
                return True

        def __is_url_valid(self, name):
                self.url_error = None
                if len(name) == 0:
                        return False

                if not misc.valid_auth_url(name):
                        # Check whether the user has started typing a valid URL.
                        # If he has we do not display an error message.
                        valid_start = False
                        for val in misc._valid_proto:
                                check_str = "%s://" % val
                                if check_str.startswith(name):
                                        valid_start = True
                                        break 
                        if valid_start:
                                self.url_error = None
                        else:
                                self.url_error = _("URL is not valid")
                        return False
                return True
        
        def __on_repositoryname_changed(self, widget):
                self.__validate_name(widget)

        def __validate_name(self, widget):
                name = widget.get_text() 
                self.is_name_valid = self.__is_name_valid(name)
                self.w_repository_error_label.hide()
                if self.is_name_valid:
                        if (self.is_url_valid):
                                self.w_repository_add_button.set_sensitive(True)
                        else:
                                self.w_repository_add_button.set_sensitive(False)
                                if self.url_error == None:
                                        self.__validate_url(self.w_repository_url)
                                if self.url_error != None:
                                        error_str = ERROR_FORMAT % self.url_error
                                        self.w_repository_error_label.set_markup(
                                            error_str)
                                        self.w_repository_error_label.show()
                else:
                        self.w_repository_add_button.set_sensitive(False)
                        if self.name_error != None:
                                error_str = ERROR_FORMAT % self.name_error
                                self.w_repository_error_label.set_markup(error_str)
                                self.w_repository_error_label.show()

        def __on_repositorytreeview_selection_changed(self, widget):
                self.w_repository_modify_button.set_sensitive(True)
                tsel = widget.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr != None:
                        model = selection[0]
                        preferred = model.get_value(itr, 1)
                        if len(self.repository_list) > 1:
                                self.w_repository_remove_button.set_sensitive(
                                    not preferred)

        def __on_repositorytreeview_button_release_event(self, widget, event):
                if event.type == gtk.gdk.BUTTON_RELEASE:
                        self.__on_repositorytreeview_selection_changed(widget)

        def __on_repositorytreeview_move_cursor(self, widget, step, count):
                self.__on_repositorytreeview_selection_changed(widget)

        def __on_repositoryadd_clicked(self, widget):
                name = self.w_repository_name.get_text()
                url = self.w_repository_url.get_text()
                if url.startswith("https"):
                        self.w_sslkeyandcert_dialog.show_all()
                else:
                        self.__do_add_repository(name, url)

        def __do_add_repository(self, name, url, ssl_key=None, ssl_cert=None):
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__add_repository, p_title,
                    p_text, name, url, ssl_key, ssl_cert)

        def __run_with_prog_in_thread(self, func, p_title, p_text, *f_args):
                self.w_progress_dialog.set_title(p_title)
                self.w_progressinfo_label.set_text(p_text)
                self.progress_stop_thread = False
                self.w_progress_dialog.show()
                gobject.timeout_add(100, self.__progress_pulse)
                Thread(target = func, args = f_args).start()
                

        def __on_repositoryremove_clicked(self, widget):
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__delete_selected_row, p_title,
                    p_text)

        def __on_repositorymodify_clicked(self, widget):
                tsel = self.w_repository_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr != None:
                        model = selection[0]
                        self.old_modify_name = model.get_value(itr, 
                            enumerations.AUTHORITY_NAME)
                        self.old_modify_url = model.get_value(itr,
                            enumerations.AUTHORITY_URL)
                        self.old_modify_ssl_key = model.get_value(itr,
                            enumerations.AUTHORITY_SSL_KEY)
                        self.old_modify_ssl_cert = model.get_value(itr,
                            enumerations.AUTHORITY_SSL_CERT)
                        self.old_modify_preferred = model.get_value(itr,
                            enumerations.AUTHORITY_PREFERRED)
                        self.mirror_list.clear()
                        mirrors = model.get_value(itr,
                            enumerations.AUTHORITY_MIRRORS)
                        self.__setup_mirrors(mirrors)
                        self.w_repositorymodify_name.set_text(self.old_modify_name)
                        self.w_repositorymodify_url.set_text(self.old_modify_url)
                        if self.old_modify_ssl_key != None:
                                self.w_repositorymodify_key_entry.set_text(
                                    self.old_modify_ssl_key)
                        if self.old_modify_ssl_cert != None:
                                self.w_repositorymodify_cert_entry.set_text(
                                    self.old_modify_ssl_cert)
                        self.w_mirror_add_button.set_sensitive(False)
                        self.w_repositorymodify_dialog.show_all()

        def __on_repository_delete_event(self, widget, event):
                self.__on_repositoryclose_clicked(widget)

        def __on_repositoryclose_clicked(self, widget):
                # if the number is greater then 1 it means that we did something
                # to the repository list and it is safer to reload package info
                if self.number_of_changes > 1 or \
                    self.original_preferred != self.preferred:
                        self.parent.reload_packages()
                self.w_repository_dialog.hide()

        def __on_repositorymodifyok_clicked(self, widget):
                self.w_repository_treeview.grab_focus()
                self.w_repositorymodify_dialog.hide()
                name =  self.w_repositorymodify_name.get_text()
                url =  self.w_repositorymodify_url.get_text()
                ssl_key =  self.w_repositorymodify_key_entry.get_text()
                if ssl_key == "":
                        ssl_key = None
                ssl_cert =  self.w_repositorymodify_cert_entry.get_text()
                if ssl_cert == "":
                        ssl_cert = None
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__update_repository, p_title,
                    p_text, name, url, ssl_key, ssl_cert)

        def __update_repository(self, name, url, ssl_key, ssl_cert):
                url_same = True
                name_same = True
                ssl_key_same = True
                ssl_cert_same = True
                if name != self.old_modify_name:
                        name_same = False
                if url != self.old_modify_url:
                        url_same = False
                if ssl_key != self.old_modify_ssl_key:
                        ssl_key_same = False
                if ssl_cert != self.old_modify_ssl_cert:
                        ssl_cert_same = False
                if url_same and name_same and ssl_key_same and ssl_cert_same:
                        self.progress_stop_thread = True
                        return
                #we don't enable changing the name of the repository
                #so this part of the code should be skipped in the current
                #implementation.
                if not name_same:
                        omn = self.old_modify_name
                        if not self.__is_name_valid(name):
                                self.progress_stop_thread = True
                                err = _("Failed to modify %(old_name)s."
                                    "\nThe chosen repository name %(new_name)s is "
                                    "already in use") % \
                                    {'old_name': omn,
                                     'new_name': name}
                                gobject.idle_add(self.__error_occurred, err)
                                self.progress_stop_thread = True
                                return
                        try:
                                self.__delete_repository(self.old_modify_name, False)
                        except api_errors.PermissionsException:
                                # Do nothing
                                err = _("Failed to modify %s." 
                                    "\nPlease check your permissions.") % omn
                                self.__error_with_reset_repo_selection(err,
                                    gtk.MESSAGE_INFO)
                                return
                        except RuntimeError, ex:
                                if "no defined authorities" in str(ex):
                                        pass
                                else:
                                        err = str(ex)
                                        self.__error_with_reset_repo_selection(err)
                                        return
                try:
                        self.__add_repository(name, url, ssl_key, ssl_cert, silent=False)
                        if self.old_modify_preferred:
                                self.img.set_preferred_authority(name)
                                self.__prepare_repository_list(False)
                except api_errors.PermissionsException:
                        # Do nothing
                        somn = self.old_modify_name
                        err = _("Failed to modify %s."
                            "\nPlease check your permissions.") % omn
                        self.__error_with_reset_repo_selection(err,
                            gtk.MESSAGE_INFO)
                        return
                except RuntimeError, ex:
                        #The "no defined authorities" should never happen
                        #Because we skipped removal of repository during name
                        #change as we disabled name changing.
                        if "no defined authorities" in str(ex):
                                pass
                        else:
                                err = str(ex)
                                self.__error_with_reset_repo_selection(err)
                                return
                except api_errors.CatalogRefreshException:
                        try:
                                somn = self.old_modify_name
                                self.__add_repository(somn,
                                    self.old_modify_url, silent=False, stop_thread=False)
                                if somn != name:
                                        self.__delete_repository(name, False)
                                err = _("Failed to modify %s.") % somn + \
                                    _(
                                    "\nPlease check the network connection or URL.\n"
                                    "Is the repository accessible?")
                                gobject.idle_add(self.__error_occurred, err,
                                    gtk.MESSAGE_INFO)
                        except api_errors.CatalogRefreshException:
                                #We need to show at least one warning dialog
                                #This is for repository which didn't existed 
                                #and was modified
                                #To not existed repository
                                somn = self.old_modify_name
                                err = _("Failed to modify %s.") % somn + \
                                    _(
                                    "\nPlease check the network connection or URL.\n"
                                    "Is the repository accessible?")
                                gobject.idle_add(self.__error_occurred, err,
                                    gtk.MESSAGE_INFO)
                self.progress_stop_thread = True
                return


        def __on_repositorymodify_delete_event(self, widget, event):
                self.__on_repositorymodifycancel_clicked(widget)

        def __on_repositorymodifycancel_clicked(self, widget):
                self.w_repository_treeview.grab_focus()
                self.w_repositorymodify_dialog.hide()

        def __delete_selected_row(self):
                tsel = self.w_repository_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr != None:
                        model = selection[0]
                        name = model.get_value(itr, 0)
                        self.__delete_repository(name)

        def __add_repository(self, auth, origin_url, ssl_key=None, 
            ssl_cert=None, silent=True, stop_thread=True):

                if not misc.valid_auth_url(origin_url):
                        err = _("Invalid URL:\n%s" % origin_url)
                        gobject.idle_add(self.__error_occurred, err)
                        gobject.idle_add(self.w_repository_name.grab_focus)
                        self.progress_stop_thread = True
                        return
                try:
                        refresh_catalogs = True
                        self.img.set_authority(auth, origin_url=origin_url,
                            ssl_key=ssl_key, ssl_cert=ssl_cert,
                            refresh_allowed=refresh_catalogs)
                        self.__prepare_repository_list(silent,
                            auth, stop_thread=stop_thread)
                except RuntimeError, ex:
                        if not silent:
                                raise
                        err = (_("Failed to add %s.") % auth)
                        err += str(ex)
                        self.__error_with_reset_repo_selection(err)
                        return
                except api_errors.PermissionsException:
                        if not silent:
                                raise
                        err = (_("Failed to add %s.") % auth) + \
                            _("\nPlease check your permissions.")
                        self.__error_with_reset_repo_selection(err,
                            gtk.MESSAGE_INFO)
                except api_errors.CatalogRefreshException:
                        if not silent:
                                raise
                        self.__delete_repository(auth)
                        err = _("Failed to add %s.") % auth + \
                            _(
                            "\nPlease check the network connection or URL.\nIs the "
                            "repository accessible?")
                        self.__error_with_reset_repo_selection(err, gtk.MESSAGE_INFO)

        def __delete_repository(self, name, silent=True):
                try:
                        self.img.delete_authority(name)
                        self.__prepare_repository_list(clear_add_entries = False, \
                            stop_thread = silent)
                except RuntimeError, ex:
                        if not silent:
                                raise
                        err = (_("Failed to delete %s.") % name)
                        err += str(ex)
                        self.__error_with_reset_repo_selection(err)
                        return
                except api_errors.PermissionsException:
                        if not silent:
                                raise
                        err = (_("Failed to delete %s.") % name) + \
                            _("\nPlease check your permissions.")
                        self.__error_with_reset_repo_selection(err,
                            gtk.MESSAGE_INFO)

        def __setup_mirrors(self, mirrors):
                self.mirror_list.clear()
                j = 0
                for m in mirrors:
                        self.mirror_list.insert(j, [m])
                        j += 1
                if self.w_mirror_treeview.get_model() == None:
                        self.w_mirror_treeview.set_model(self.mirror_list_filter)
                if j > 0:
                        self.w_mirror_treeview.set_cursor(0, None, 
                            start_editing = False)
                        self.w_mirror_remove_button.set_sensitive(True)
                else:
                        self.w_mirror_remove_button.set_sensitive(False)

        def __add_mirror(self):
                name = self.w_repositorymodify_name.get_text()
                mirror = self.w_mirror_add_entry.get_text()
                try:
                        self.img.add_mirror(name, mirror)
                        self.w_mirror_add_entry.set_text("")
                        tsel = self.w_repository_treeview.get_selection()
                        selection = tsel.get_selected()
                        itr = selection[1]
                        if itr != None:
                                model = selection[0]
                                mirrors = model.get_value(itr,
                                    enumerations.AUTHORITY_MIRRORS)
                                gobject.idle_add(self.__setup_mirrors, mirrors)
                        self.progress_stop_thread = True
                except RuntimeError, ex:
                        err = (_("Failed to add mirror %(mirror)s for "
                            "repository %(repository)s.") % \
                            {'mirror': mirror,
                             'repository': name})
                        err += str(ex)
                        gobject.idle_add(self.__error_occurred, err,
                            gtk.MESSAGE_ERROR)
                        self.progress_stop_thread = True
                        return
                except api_errors.PermissionsException:
                        err = (_("Failed to add mirror %(mirror)s for "
                            "repository %(repository)s.") % \
                            {'mirror': mirror,
                             'repository': name}) + \
                            _("\nPlease check your permissions.")
                        gobject.idle_add(self.__error_occurred, err,
                            gtk.MESSAGE_INFO)
                        self.progress_stop_thread = True

        def __delete_mirror(self, name, mirror):
                try:
                        self.img.del_mirror(name, mirror)
                        tsel = self.w_repository_treeview.get_selection()
                        selection = tsel.get_selected()
                        itr = selection[1]
                        if itr != None:
                                model = selection[0]
                                mirrors = model.get_value(itr,
                                    enumerations.AUTHORITY_MIRRORS)
                                gobject.idle_add(self.__setup_mirrors, mirrors)
                        self.progress_stop_thread = True
                except RuntimeError, ex:
                        err = (_("Failed to delete mirror %(mirror)s for "
                            "repository %(repository)s.") % \
                            {'mirror': mirror,
                             'repository': name})
                        err += str(ex)
                        gobject.idle_add(self.__error_occurred, err,
                            gtk.MESSAGE_ERROR)
                        self.progress_stop_thread = True
                        return
                except api_errors.PermissionsException:
                        err = (_("Failed to delete mirror %(mirror)s for "
                            "repository %(repository)s.") % \
                            {'mirror': mirror,
                             'repository': name}) + \
                            _("\nPlease check your permissions.")
                        gobject.idle_add(self.__error_occurred, err,
                            gtk.MESSAGE_INFO)
                        self.progress_stop_thread = True

        def __delete_selected_mirror(self):
                tsel = self.w_mirror_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr != None:
                        model = selection[0]
                        mirror = model.get_value(itr, 0)
                        name = self.w_repositorymodify_name.get_text()
                        self.__delete_mirror(name, mirror)
                else:
                        self.progress_stop_thread = True

        def __on_mirror_remove_clicked(self, widget):
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__delete_selected_mirror, p_title,
                    p_text)

        def __on_mirrorentry_changed(self, widget):
                url = widget.get_text()
                if self.__is_url_valid(url):
                        self.w_mirror_add_button.set_sensitive(True)
                else:
                        self.w_mirror_add_button.set_sensitive(False)

        def __on_mirroradd_button_clicked(self, widget):
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__add_mirror, p_title,
                    p_text)

        def __on_mod_key_or_cert_entry_changed(self, widget):
                key = self.w_repositorymodify_key_entry.get_text()
                cert = self.w_repositorymodify_cert_entry.get_text()
                self.__key_or_cert_validation(key, cert, 
                    self.w_repositorymodify_ok_button)

        @staticmethod
        def __key_or_cert_validation(key, cert, button):
                if key == "":
                        if cert == "":
                                button.set_sensitive(True)
                        else:
                                button.set_sensitive(False)
                else:
                        if os.path.isfile(key):
                                if cert == "":
                                        button.set_sensitive(False)
                                elif os.path.isfile(cert):
                                        button.set_sensitive(True)
                                else:
                                        button.set_sensitive(False)
                        else:
                                button.set_sensitive(False)

        def __on_key_or_cert_entry_changed(self, widget):
                key = self.w_sslkeyandcert_key_entry.get_text()
                cert = self.w_sslkeyandcert_cert_entry.get_text()
                self.__key_or_cert_validation(key, cert, 
                    self.w_sslkeyandcert_ok_button)

        @staticmethod
        def __on_sslkeyandcert_dialog_delete_event(widget, event):
                return widget.hide_on_delete()

        def __on_sslkeyandcertcancel_clicked(self, widget):
                self.w_sslkeyandcert_dialog.hide()

        def __on_sslkeyandcertok_clicked(self, widget):
                self.w_sslkeyandcert_dialog.hide()
                name = self.w_repository_name.get_text()
                url = self.w_repository_url.get_text()
                key = self.w_sslkeyandcert_key_entry.get_text()
                cert = self.w_sslkeyandcert_cert_entry.get_text()
                self.__do_add_repository(name, url, key, cert)

        def __on_keybrowse_clicked(self, widget):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Key File"),
                    parent = self.w_repository_dialog,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(self.w_sslkeyandcert_dialog)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        key = chooser.get_filename()
                        self.w_sslkeyandcert_key_entry.set_text(key)
                        cert = key.replace("key", "certificate")
                        if key != cert and \
                            self.w_sslkeyandcert_cert_entry.get_text() == "":
                                if os.path.isfile(cert):
                                        self.w_sslkeyandcert_cert_entry.set_text(cert)
                chooser.destroy()

        def __on_certbrowse_clicked(self, widget):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Certificate File"),
                    parent = self.w_repository_dialog,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(self.w_sslkeyandcert_dialog)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        self.w_sslkeyandcert_cert_entry.set_text(
                            chooser.get_filename())
                chooser.destroy()

        def __on_modify_keybrowse_clicked(self, widget):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Key File"),
                    parent = self.w_repository_dialog,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(self.w_repositorymodify_dialog)
                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        key = chooser.get_filename()
                        self.w_repositorymodify_key_entry.set_text(key)
                        cert = key.replace("key", "certificate")
                        if key != cert and \
                            self.w_repositorymodify_cert_entry.get_text() == "":
                                if os.path.isfile(cert):
                                        self.w_repositorymodify_cert_entry.set_text(cert)
                chooser.destroy()

        def __on_modify_certbrowse_clicked(self, widget):
                chooser =  gtk.FileChooserDialog(
                    title=_("Specify SSL Certificate File"),
                    parent = self.w_repository_dialog,
                    action=gtk.FILE_CHOOSER_ACTION_OPEN,
                    buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
                chooser.set_default_response(gtk.RESPONSE_OK)
                chooser.set_transient_for(self.w_repositorymodify_dialog)
                reponse = chooser.run()
                if reponse == gtk.RESPONSE_OK:
                        self.w_repositorymodify_cert_entry.set_text(
                            chooser.get_filename())
                chooser.destroy()

        def __error_with_reset_repo_selection(self, error_msg,
            msg_type=gtk.MESSAGE_ERROR):
                gobject.idle_add(self.__error_occurred, error_msg, msg_type)
                self.__reset_repo_selection()

        def __reset_repo_selection(self):
                sel = None
                selection = self.w_repository_treeview.get_selection()
                model, ite = selection.get_selected()
                if ite:
                        sel = model.get_value(ite, 0)
                self.__prepare_repository_list(False, sel)

        def __error_occurred(self, error_msg, msg_type=gtk.MESSAGE_ERROR):
                msgbox = gtk.MessageDialog(parent =
                    self.w_repository_dialog,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL,
                    type = msg_type,
                    message_format = None)
                msgbox.set_markup(error_msg)
                msgbox.set_title("Edit Repositories error")
                msgbox.run()
                msgbox.destroy()

