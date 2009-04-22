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
from pkg.client.api_errors import InvalidDepotResponseException

try:
        import gnome
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

ERROR_FORMAT = "<span color = \"red\">%s</span>"

class Repository:
        def __init__(self, parent, webinstall_new=False):
                self.parent = parent
                self.api_o = parent.api_o
                self.webinstall_new = webinstall_new
                self.registration_url = None
                self.pub_copy = None
                self.repo_copy = None

                self.repository_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_NAME
                        gobject.TYPE_BOOLEAN,     # enumerations.PUBLISHER_PREFERRED
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_URL
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_SSL_KEY
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_SSL_CERT
                        gobject.TYPE_PYOBJECT,    # enumerations.PUBLISHER_MIRRORS
                        gobject.TYPE_BOOLEAN,     # enumerations.PUBLISHER_ENABLED
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
                self.error_dialog_parent =  self.w_repository_dialog
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
                self.w_repositorymodify_error_label = \
                        w_tree_repositorymodify.get_widget("moderror_label")
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
                self.w_repositorymodify_title_label = \
                    w_tree_repositorymodify.get_widget("repositorymodifytitlelabel")
                    
                self.w_repositorymodify_registration_comment_label = \
                    w_tree_repositorymodify.get_widget(
                        "repositorymodifyregistrationcommentlabel")
                self.w_repositorymodify_registration_link = \
                    w_tree_repositorymodify.get_widget(
                        "repositorymodifyregistrationlinkbutton")                    
                    
                self.w_repositorymodify_ssl_expander = \
                    w_tree_repositorymodify.get_widget("repositorymodifysslexpander")
                self.w_repositorymodify_mirrors_expander = \
                    w_tree_repositorymodify.get_widget("repositorymodifymirrorsexpander")

                self.mirror_list_filter = self.mirror_list.filter_new()
                self.w_mirror_add_entry = \
                    w_tree_repositorymodify.get_widget("addmirror_entry")
                self.w_mirror_add_button = \
                    w_tree_repositorymodify.get_widget("addmirror_button")
                self.w_mirror_remove_button = \
                    w_tree_repositorymodify.get_widget("mirrorremove")
                self.w_repositorymodify_url.connect('focus-in-event', 
                    self.on_focus_in_modurl)
                    
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
                                "on_repositoryhelp_clicked": \
                                    self.__on_repositoryhelp_clicked,                                                                        
                            }
                        dic_conf = \
                            {
                                "on_repositorymodif_delete_event": \
                                    self.__on_repositorymodify_delete_event,
                                "on_repositorymodifycancel_clicked": \
                                    self.__on_repositorymodifycancel_clicked,
                                "on_repositorymodifyok_clicked": \
                                    self.__on_repositorymodifyok_clicked,
                                "on_repositorymodifyregistrationlinkbutton_clicked": \
                                    self.__on_repositorymodifyregistrationlink_clicked,
                                "on_repositorymodifyurl_changed": \
                                    self.__on_repositorymodifyurl_changed,
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

                if not self.webinstall_new:
                        Thread(target = self.__prepare_repository_list).start()
                        self.w_repository_dialog.show_all()
                self.w_repository_error_label.hide()

        def webinstall_new_pub(self, parent, pub = None):
                if pub == None:
                        return
                self.w_progress_dialog.set_transient_for(parent)
                auth = origin_uri = registration_url = mirror_datalist = None
                
                self.pub_copy = pub
                self.repo_copy = pub.selected_repository

                auth = self.pub_copy.prefix
                origin_uri = self.repo_copy.origins[0].uri

                scheme = None                
                if origin_uri != None and origin_uri.startswith("https"):
                        scheme = "https"

                reg_uri = self.__get_registration_uri(self.repo_copy)
                if reg_uri != None:
                        registration_url = reg_uri
                elif scheme == "https":
                        registration_url = origin_uri
                mirror_datalist = self.repo_copy.mirrors

                self.__webinstall_new_repository(parent, auth, origin_uri,
                    registration_url, mirror_datalist, scheme)

        def __webinstall_new_repository(self, parent, auth = None, origin_uri = None,
            registration_url = None, mirror_datalist = None, scheme = None):
                if (auth == None or origin_uri == None):
                        return
                        
                self.registration_url = registration_url
                self.error_dialog_parent = parent
                self.w_repositorymodify_dialog.set_title(
                    _("Add New Repository"))
                self.w_repositorymodify_name.set_text(auth)
                self.w_repositorymodify_url.set_text(origin_uri)
                self.w_repositorymodify_name.set_sensitive(False)
                self.w_repositorymodify_url.set_sensitive(False)
                self.w_repositorymodify_dialog.set_modal(True)
                self.w_repositorymodify_dialog.set_transient_for(parent)
                self.w_repositorymodify_title_label.set_markup(
                    _("<b>New Repository</b>"))
                self.w_mirror_add_button.set_sensitive(False)
                
                if scheme != "https" and registration_url == None:
                        self.__on_repositorymodifyok_clicked(None)
                        return
                        
                self.w_repositorymodify_ssl_expander.set_expanded(True)
                self.w_repositorymodify_registration_link.set_uri(registration_url)
                        
                self.w_repositorymodify_dialog.show_all()
                self.w_repositorymodify_error_label.hide()

                if scheme == "https":
                        self.w_repositorymodify_ssl_expander.show()
                else:
                        self.w_repositorymodify_ssl_expander.hide()
                        
                if mirror_datalist == None or len(mirror_datalist) == 0:
                        self.w_repositorymodify_mirrors_expander.hide()
                else:
                        gobject.idle_add(self.__setup_mirrors, mirror_datalist)

        def on_focus_in(self, widget, event):
                self.w_repository_modify_button.set_sensitive(False)
                self.w_repository_remove_button.set_sensitive(False)

        def on_focus_in_name(self, widget, event):
                self.__validate_name(widget)
                self.w_repository_modify_button.set_sensitive(False)
                self.w_repository_remove_button.set_sensitive(False)

        def on_focus_in_modurl(self, widget, event):
                self.__validate_modurl(widget)

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
                    name_renderer,  text = enumerations.PUBLISHER_NAME)
                column.set_expand(True)
                column.set_sort_column_id(enumerations.PUBLISHER_NAME)
                column.set_sort_indicator(True)
                column.set_cell_data_func(name_renderer,
                    self.name_data_function, None)
                self.w_repository_treeview.append_column(column)
                radio_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Preferred"),
                    radio_renderer, active = enumerations.PUBLISHER_PREFERRED)
                radio_renderer.set_property("activatable", True)
                radio_renderer.set_property("radio", True)
                column.set_expand(False)
                column.set_sort_column_id(enumerations.PUBLISHER_PREFERRED)
                column.set_sort_indicator(True)
                radio_renderer.connect('toggled', self.__preferred_default)
                column.set_cell_data_func(radio_renderer,
                    self.radio_data_function, None)
                self.w_repository_treeview.append_column(column)
                toggle_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(_("Enabled"),
                    toggle_renderer, active = enumerations.PUBLISHER_ENABLED)
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)
                column.set_sort_column_id(enumerations.PUBLISHER_ENABLED)
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

        def __prepare_repository_list(self, clear_add_entries=True, selected_pub=None,
            stop_thread=True):
                self.number_of_changes += 1
                pubs = self.api_o.get_publishers()
                gobject.idle_add(self.__create_view_with_pubs, pubs,
                    clear_add_entries, selected_pub)
                if stop_thread:
                        self.progress_stop_thread = True
                return

        def __create_view_with_pubs(self, pubs, clear_add_entries, selected_pub):
                model = self.w_repository_treeview.get_model()
                self.w_repository_treeview.set_model(None)
                self.repository_list.clear()
                if clear_add_entries:
                        self.w_repository_name.set_text("")
                        self.w_repository_url.set_text("")
                self.w_repository_name.grab_focus()
                j = 0
                select_pub = -1
                pref_pub = self.api_o.get_preferred_publisher()
                self.preferred = pref_pub.prefix
                self.original_preferred = self.preferred
                for pub in pubs:
                        repo = pub.selected_repository
                        origin = repo.origins[0]

                        name = pub.prefix
                        is_preferred = name == self.preferred
                        if is_preferred:
                                self.initial_default = j
                        if selected_pub:
                                if name == selected_pub:
                                        select_pub = j
                        self.repository_list.insert(j, [name, is_preferred,
                            origin.uri, origin.ssl_key, origin.ssl_cert,
                            [m.uri for m in repo.mirrors], not pub.disabled])
                        j += 1
                if j > 0:
                        self.w_repository_modify_button.set_sensitive(False)
                        self.w_repository_remove_button.set_sensitive(False)
                self.w_repository_treeview.set_model(model)
                if select_pub == -1:
                        select_pub = self.initial_default
                self.w_repository_treeview.set_cursor(select_pub,
                    None, start_editing=False)
                self.w_repository_treeview.scroll_to_cell(select_pub)

        @staticmethod
        def name_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 

                            model.get_value(itr, enumerations.PUBLISHER_ENABLED))

        @staticmethod
        def radio_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 
                            model.get_value(itr, enumerations.PUBLISHER_ENABLED))

        @staticmethod
        def toggle_data_function(column, renderer, model, itr, data):
                if itr:
                        renderer.set_property("sensitive", 
                            not model.get_value(itr, 
                            enumerations.PUBLISHER_PREFERRED))

        def __enable_disable(self, cell, filtered_path):
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__enable_disable_in_thread, p_title,
                    p_text, cell, filtered_path)

        def __enable_disable_in_thread(self, cell, filtered_path):
                sorted_model = self.w_repository_treeview.get_model()
                filtered_model = sorted_model.get_model()
                model = filtered_model.get_model()
                path = sorted_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr == None:
                        self.progress_stop_thread = True
                        return
                        
                preferred = model.get_value(itr, 
                    enumerations.PUBLISHER_PREFERRED)
                if preferred == True:
                        self.progress_stop_thread = True
                        return
                enabled = model.get_value(itr,
                    enumerations.PUBLISHER_ENABLED)
                pub = model.get_value(itr, enumerations.PUBLISHER_NAME)
                try:
                        pub = self.api_o.get_publisher(pub, duplicate=True)
                        pub.disabled = enabled
                        self.api_o.update_publisher(pub,
                            refresh_allowed=False)
                        self.number_of_changes += 1
                        gobject.idle_add(model.set_value, itr, 
                            enumerations.PUBLISHER_ENABLED, not enabled)
                        self.progress_stop_thread = True
                except api_errors.PublisherError, pex:
                        self.progress_stop_thread = True
                        if enabled:
                                err = _("Failed to disable %s.\n") % pub
                        else:
                                err = _("Failed to enable %s.\n") % pub
                        err += str(pex)
                        gobject.idle_add(self.__error_occurred, err, gtk.MESSAGE_INFO)
                except api_errors.PermissionsException:
                        self.progress_stop_thread = True
                        if enabled:
                                err1 = _("Failed to disable %s.") % pub
                        else:
                                err1 = _("Failed to enable %s.") % pub
                        err = err1 + _("\nPlease check your permissions.")
                        gobject.idle_add(self.__error_occurred, err, gtk.MESSAGE_INFO)
                except api_errors.CatalogRefreshException:
                        self.progress_stop_thread = True
                        if enabled:
                                err1 = _("Failed to disable %s.") % pub
                        else:
                                err1 = _("Failed to enable %s.") % pub
                        err = err1 + _(
                            "\nPlease check the network connection or URL.\n"
                            "Is the repository accessible?")
                        gobject.idle_add(self.__error_occurred, err, gtk.MESSAGE_INFO)
                except RuntimeError, rex:
                        self.progress_stop_thread = True
                        if enabled:
                                err1 = _("Failed to disable %s.") % pub
                        else:
                                err1 = _("Failed to enable %s.") % pub
                        err = err1 + _("\nUnexpected error.\n")
                        err += str(rex)
                        gobject.idle_add(self.__error_occurred, err)

        def __preferred_default(self, cell, filtered_path):
                p_title = _("Applying changes")
                p_text = _("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__preferred_default_in_thread,
                    p_title, p_text, cell, filtered_path)

        def __preferred_default_in_thread(self, cell, filtered_path):
                sorted_model = self.w_repository_treeview.get_model()
                filtered_model = sorted_model.get_model()
                model = filtered_model.get_model()
                path = sorted_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr == None:
                        self.progress_stop_thread = True
                        return
                        
                preferred = model.get_value(itr, 
                    enumerations.PUBLISHER_PREFERRED)
                enabled = model.get_value(itr,
                    enumerations.PUBLISHER_ENABLED)
                if preferred == False and enabled == True:
                        pub = model.get_value(itr, 
                            enumerations.PUBLISHER_NAME)
                        try:
                                self.api_o.set_preferred_publisher(pub)
                                self.preferred = pub
                                index = enumerations.PUBLISHER_PREFERRED
                                for row in model:
                                        row[index] = False
                                gobject.idle_add(model.set_value, itr,
                                    enumerations.PUBLISHER_PREFERRED, not preferred)
                                self.progress_stop_thread = True
                        except api_errors.PublisherError, pex:
                                self.progress_stop_thread = True
                                gobject.idle_add(self.__error_occurred, str(pex), 
                                    gtk.MESSAGE_INFO)
                                self.__prepare_repository_list()
                        except api_errors.PermissionsException:
                                self.progress_stop_thread = True
                                err = _("Couldn't change"
                                    " the preferred publisher.\n"
                                    "Please check your permissions.")
                                gobject.idle_add(self.__error_occurred, err,
                                    gtk.MESSAGE_INFO)
                else:
                        self.progress_stop_thread = True

        def __progress_pulse(self):
                if not self.progress_stop_thread:
                        self.w_progressbar.pulse()
                        return True
                else:
                        self.w_progress_dialog.hide()
                        return False


        def __on_repositoryurl_changed(self, widget):
                self.__validate_url(widget)

        def __on_repositorymodifyurl_changed(self, widget):
                self.__validate_modurl(widget)

        def __validate_url(self, widget):
                w_url_text = widget
                w_error_label = self.w_repository_error_label
                w_action_button = self.w_repository_add_button
                self.__validate_url_generic(w_url_text, w_error_label, w_action_button,
                    self.is_name_valid)

        def __validate_modurl(self, widget):
                w_url_text = widget
                w_error_label = self.w_repositorymodify_error_label
                w_action_button = self.w_repositorymodify_ok_button
                self.__validate_url_generic(w_url_text, w_error_label, w_action_button, 
                    True)

        def __validate_url_generic(self, w_url_text, w_error_label, w_action_button,
                name_valid = False):
                url = w_url_text.get_text()
                self.is_url_valid = self.__is_url_valid(url)
                w_error_label.hide()
                if self.is_url_valid:
                        if name_valid:
                                w_action_button.set_sensitive(True)
                        else:
                                w_action_button.set_sensitive(False)
                                if self.name_error != None:
                                        error_str = ERROR_FORMAT % self.name_error
                                        w_error_label.set_markup(
                                            error_str)
                                        w_error_label.show()
                else:
                        w_action_button.set_sensitive(False)
                        if self.url_error != None:
                                error_str = ERROR_FORMAT % self.url_error
                                w_error_label.set_markup(error_str)
                                w_error_label.show()
                        
        def __is_name_valid(self, name):
                self.name_error = None
                if len(name) == 0:
                        return False
                if not misc.valid_pub_prefix(name):
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

                if not misc.valid_pub_url(name):
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
                repo = publisher.Repository()
                repo.add_origin(url)
                self.pub_copy = publisher.Publisher(name, repositories=[repo])
                
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
                self.__clear_repositorymodify()
                self.pub_copy = None
                self.repo_copy = None
                
                tsel = self.w_repository_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr == None:
                        return
                        
                model = selection[0]
                prefix = model.get_value(itr, enumerations.PUBLISHER_NAME)
                url = model.get_value(itr, enumerations.PUBLISHER_URL)
                
                try:                        
                        self.pub_copy = self.api_o.get_publisher(prefix,
                            duplicate=True)
                        self.repo_copy = self.pub_copy.selected_repository
                        
                except api_errors.PublisherError, ex:
                        gobject.idle_add(self.__error_occurred, str(ex),
                            gtk.MESSAGE_ERROR)
                        gobject.idle_add(self.w_repository_name.grab_focus)
                        return
                                        
                self.mirror_list.clear()
                self.__setup_mirrors(self.repo_copy.mirrors)
                if len(self.repo_copy.mirrors) > 0:
                        self.w_repositorymodify_mirrors_expander.set_expanded(True)

                self.w_repositorymodify_name.set_text(prefix)
                self.w_repositorymodify_url.set_text(url)
                
                origin = self.repo_copy.origins[0]
                if origin.ssl_key != None:
                        self.w_repositorymodify_key_entry.set_text(origin.ssl_key)
                if origin.ssl_cert != None:
                        self.w_repositorymodify_cert_entry.set_text(
                            origin.ssl_cert)
                self.w_mirror_add_button.set_sensitive(False)
                
                self.w_repositorymodify_dialog.show_all()
                self.w_repositorymodify_error_label.hide()
                self.w_repositorymodify_registration_comment_label.hide()
                self.w_repositorymodify_registration_link.hide()
                self.w_repositorymodify_registration_link.set_uri("")
                self.w_repositorymodify_ssl_expander.set_expanded(False) 
                
                reg_uri = self.__get_registration_uri(self.repo_copy)
                if reg_uri == None and origin.ssl_key == None:
                        return
                            
                self.w_repositorymodify_registration_comment_label.show()
                self.w_repositorymodify_registration_link.show()
                                
                if reg_uri != None:
                        self.registration_url = reg_uri
                else:
                        self.registration_url = url
                self.w_repositorymodify_registration_link.set_uri(self.registration_url)
                        
                if origin.ssl_key != None:
                        self.w_repositorymodify_ssl_expander.set_expanded(True)
                
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
                
        def __on_repository_delete_event(self, widget, event):
                self.__on_repositoryclose_clicked(widget)

        def __on_repositoryhelp_clicked(self, widget):
                gui_misc.display_help(self.parent.application_dir, "manage_repo")

        def __on_repositoryclose_clicked(self, widget):
                # if the number is greater then 1 it means that we did something
                # to the repository list and it is safer to reload package info
                if (not self.webinstall_new and self.number_of_changes > 1) or \
                    (not self.webinstall_new and 
                    self.original_preferred != self.preferred):
                        self.parent.reload_packages()
                self.w_repository_dialog.hide()

        def __on_repositorymodifyregistrationlink_clicked(self, widget):
                try:
                        gnome.url_show(self.registration_url)
                except gobject.GError:
                        self.__error_occurred(_("Unable to navigate to:\n\t%s") % 
                            self.registration_url, title=_("Registration"))
                
        def __on_repositorymodifyok_clicked(self, widget):
                self.w_repositorymodify_dialog.hide()
                name =  self.w_repositorymodify_name.get_text()
                url =  self.w_repositorymodify_url.get_text()
                if self.webinstall_new:
                        p_title = _("Adding New Repository")
                        p_text = _("Adding:\n\t%s (%s)..." % (name, url))
                else:
                        self.w_repository_treeview.grab_focus()
                        p_title = _("Applying changes")
                        p_text = _("Applying changes, please wait ...")
                        
                ssl_key =  self.w_repositorymodify_key_entry.get_text()
                if ssl_key == "":
                        ssl_key = None
                ssl_cert =  self.w_repositorymodify_cert_entry.get_text()
                if ssl_cert == "":
                        ssl_cert = None
                self.__run_with_prog_in_thread(self.__add_repository, p_title,
                    p_text, name, url, ssl_key, ssl_cert)
                    
                self.__clear_repositorymodify()

        def __on_repositorymodify_delete_event(self, widget, event):
                self.__on_repositorymodifycancel_clicked(widget)
                return True

        def __clear_repositorymodify(self):
                self.w_repositorymodify_registration_comment_label.hide()
                self.w_repositorymodify_registration_link.hide()
                self.w_repositorymodify_registration_link.set_uri("")
                
                self.w_repositorymodify_ssl_expander.set_expanded(False)                
                self.w_repositorymodify_key_entry.set_text("")
                self.w_repositorymodify_cert_entry.set_text("")
                
                self.w_repositorymodify_mirrors_expander.set_expanded(False)
                self.w_mirror_add_entry.set_text("")
                
        def __on_repositorymodifycancel_clicked(self, widget):
                self.w_repository_treeview.grab_focus()
                self.w_repositorymodify_dialog.hide()
                self.webinstall_new = False
                self.__clear_repositorymodify()
                
        def __delete_selected_row(self):
                tsel = self.w_repository_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr != None:
                        model = selection[0]
                        name = model.get_value(itr, 0)
                        self.__delete_repository(name)

        def __add_repository(self, prefix, origin_url, ssl_key=None, 
            ssl_cert=None, silent=True, stop_thread=True):
                if self.pub_copy == None:
                        return
                pub = self.pub_copy
                repo = pub.selected_repository

                try:
                        new_pub = not self.api_o.has_publisher(pub.prefix)

                        # XXX once image configuration supports storing this
                        # information at the uri level, ssl info should
                        # be set here instead of below.
                        if not repo.origins:
                                repo.add_origin(origin_url)
                                origin = repo.origins[0]
                        else:
                                origin = repo.origins[0]
                                origin.uri = origin_url

                        for uri in repo.origins:
                                if ssl_cert is not None:
                                        uri.ssl_cert = ssl_cert
                                if ssl_key is not None:
                                        uri.ssl_key = ssl_key
                        for uri in repo.mirrors:
                                if ssl_cert is not None:
                                        uri.ssl_cert = ssl_cert
                                if ssl_key is not None:
                                        uri.ssl_key = ssl_key
                                        
                        if new_pub:
                                self.api_o.add_publisher(pub)
                        else:
                                self.api_o.update_publisher(pub)
                                
                        if self.webinstall_new:
                                self.webinstall_new = False
                                self.progress_stop_thread = True
                                self.parent.reload_packages()
                        else:
                                self.__prepare_repository_list(silent,
                                        selected_pub=prefix, stop_thread=stop_thread)
                        self.pub_copy = None
                        self.repo_copy = None
                        
                except api_errors.PublisherError, ex:
                        self.progress_stop_thread = True
                        if not silent:
                                raise
                        gobject.idle_add(self.__error_occurred, str(ex),
                            gtk.MESSAGE_ERROR)
                        gobject.idle_add(self.w_repository_name.grab_focus)
                except InvalidDepotResponseException, idrex:
                        self.progress_stop_thread = True
                        if not silent:
                                raise
                        err = (_("Failed to add repository: %s\n\n") % prefix)
                        err += str(idrex)
                        self.__error_with_reset_repo_selection(err)
                except RuntimeError, ex:
                        self.progress_stop_thread = True
                        if not silent:
                                raise
                        err = (_("Failed to add %s.\n") % prefix)
                        err += str(ex)
                        self.__error_with_reset_repo_selection(err)
                        return
                except api_errors.PermissionsException:
                        self.progress_stop_thread = True
                        if not silent:
                                raise
                        err = (_("Failed to add %s.") % prefix) + \
                            _("\nPlease check your permissions.")
                        self.__error_with_reset_repo_selection(err,
                            gtk.MESSAGE_INFO)
                except api_errors.CatalogRefreshException:
                        self.progress_stop_thread = True
                        if not silent:
                                raise
                        self.__delete_repository(pub)
                        err = _("Failed to add %s.") % prefix + \
                            _(
                            "\nPlease check the network connection or URL.\nIs the "
                            "repository accessible?")
                        self.__error_with_reset_repo_selection(err, gtk.MESSAGE_INFO)

        def __delete_repository(self, name, silent=True):
                try:
                        self.api_o.remove_publisher(name)
                        self.__prepare_repository_list(clear_add_entries = False, \
                            stop_thread = silent)
                except api_errors.PublisherError, ex:
                        if not silent:
                                raise
                        self.__error_with_reset_repo_selection(str(ex))
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
                mirror = self.w_mirror_add_entry.get_text()
                self.w_mirror_add_entry.set_text("")
                try:
                        self.repo_copy.add_mirror(mirror)
                except api_errors.PublisherError, ex:
                        self.__error_with_reset_repo_selection(str(ex))
                        return                        
                gobject.idle_add(self.__setup_mirrors, self.repo_copy.mirrors)

        def __delete_mirror(self, mirror):
                try:
                        self.repo_copy.remove_mirror(mirror)
                except api_errors.PublisherError, ex:
                        self.__error_with_reset_repo_selection(str(ex))
                        return                        
                gobject.idle_add(self.__setup_mirrors, self.repo_copy.mirrors)

        def __delete_selected_mirror(self):
                tsel = self.w_mirror_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr == None:
                        return
                model = selection[0]
                mirror = model.get_value(itr, 0)
                self.__delete_mirror(mirror)

        def __on_mirror_remove_clicked(self, widget):
                self.__delete_selected_mirror()

        def __on_mirrorentry_changed(self, widget):
                url = widget.get_text()
                if self.__is_url_valid(url):
                        self.w_mirror_add_button.set_sensitive(True)
                else:
                        self.w_mirror_add_button.set_sensitive(False)

        def __on_mirroradd_button_clicked(self, widget):
                self.__add_mirror()

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
                self.progress_stop_thread = True

        def __error_occurred(self, error_msg, msg_type=gtk.MESSAGE_ERROR, title = None):
                msgbox = gtk.MessageDialog(parent =
                    self.error_dialog_parent,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL,
                    type = msg_type,
                    message_format = None)
                msgbox.set_property('text', error_msg)
                if title != None:
                        msgbox.set_title(title)
                else:   # More Generic for WebInstall
                        msgbox.set_title(_("Repository error"))
                        
                msgbox.run()
                msgbox.destroy()

