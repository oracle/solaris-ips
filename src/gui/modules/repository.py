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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
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

ERROR_FORMAT = "<span color = \"red\">%s</span>"

class Repository:
        def __init__(self, parent):
                self.parent = parent
                self.img = parent.api_o.img

                self.repository_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,      # Name
                        gobject.TYPE_BOOLEAN,     # Preferred
                        gobject.TYPE_STRING,      # URL
                        )
                self.progress_stop_thread = False
                self.number_of_changes = 0
                self.initial_default = 0
                w_tree_repository = gtk.glade.XML(parent.gladefile, "repository")
                w_tree_repositorymodify = \
                        gtk.glade.XML(parent.gladefile, "repositorymodif")
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
                self.list_filter = self.repository_list.filter_new()
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
                self.w_repositorymodify_ok_button = \
                        w_tree_repositorymodify.get_widget("repositorymodifyok")
                self.w_repositorymodify_cancel_button = \
                        w_tree_repositorymodify.get_widget("repositorymodifycancel")

                #Modify name of the repository is disabled, see #4990
                self.w_repositorymodify_name.set_sensitive(False)

                self.w_repository_url.connect('focus-in-event', self.on_focus_in_url)
                self.w_repository_name.connect('focus-in-event', self.on_focus_in_name)
                self.w_repository_add_button.connect('focus-in-event', self.on_focus_in)

                progress_button.hide()
                self.w_progressbar.set_pulse_step(0.1)

                self.__init_tree_views()
                self.w_progress_dialog.set_transient_for(self.w_repository_dialog)
                self.old_modify_name = None
                self.old_modify_url = None
                self.old_modify_preferred = False
                self.is_name_valid = False
                self.is_url_valid = False
                self.name_error = None
                self.url_error = None

                try:
                        dic = \
                            {
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
                                "on_repositorytreeview_move_cursor": \
                                    self.__on_repositorytreeview_move_cursor,
                                "on_repositorytreeview_button_release_event": \
                                    self.__on_repositorytreeview_button_release_event,
                            }
                        dic_conf = \
                            {
                                "on_repositorymodifycancel_clicked": \
                                    self.__on_repositorymodifycancel_clicked,
                                "on_repositorymodifyok_clicked": \
                                    self.__on_repositorymodifyok_clicked,
                            }            
                        w_tree_repository.signal_autoconnect(dic)
                        w_tree_repositorymodify.signal_autoconnect(dic_conf)
                except AttributeError, error:
                        print self.parent._('GUI will not respond to any event! %s. \
                            Check repository.py signals') \
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
        def __init_tree_views(self):
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self.parent._("Repository Name"), \
                        name_renderer,  text = 0) # 0 = Name
                column.set_expand(True)
                self.w_repository_treeview.append_column(column)
                radio_renderer = gtk.CellRendererToggle()
                column = gtk.TreeViewColumn(self.parent._("Preferred"), \
                    radio_renderer, active = 1) # 1 = Preferred
                radio_renderer.set_property("activatable", True)
                radio_renderer.set_property("radio", True)
                column.set_expand(False)
                radio_renderer.connect('toggled', self.__preferred_default)
                self.w_repository_treeview.append_column(column)

        def __prepare_repository_list(self, clear_add_entries=True, selected_auth=None, \
            stop_thread=True):
                self.number_of_changes += 1
                self.img.load_config()
                auths = self.img.gen_authorities()
                gobject.idle_add(self.__create_view_with_auths, auths, \
                    clear_add_entries, selected_auth)
                if stop_thread:
                        self.progress_stop_thread = True
                return

        def __create_view_with_auths(self, auths, clear_add_entries, selected_auth):
                self.w_repository_treeview.set_model(None)
                self.repository_list.clear()
                if clear_add_entries:
                        self.w_repository_name.set_text("")
                        self.w_repository_url.set_text("")
                self.w_repository_name.grab_focus()
                j = 0
                select_auth = -1
                preferred = self.img.get_default_authority()
                for a in auths:
                        l = self.img.split_authority(a)
                        name = l[0]
                        is_preferred = \
                            name == preferred
                        if is_preferred:
                                self.initial_default = j
                        if selected_auth:
                                if name == selected_auth:
                                        select_auth = j
                        self.repository_list.insert(j, \
                                [name, is_preferred, l[1]])
                        j += 1
                if j > 0:
                        self.w_repository_modify_button.set_sensitive(False)
                        self.w_repository_remove_button.set_sensitive(False)
                self.w_repository_treeview.set_model(self.list_filter)
                if select_auth == -1:
                        select_auth = self.initial_default
                self.w_repository_treeview.set_cursor(select_auth, \
                        None, start_editing=False)
                self.w_repository_treeview.scroll_to_cell(select_auth)

        def __preferred_default(self, cell, filtered_path):
                filtered_model = self.w_repository_treeview.get_model()
                model = filtered_model.get_model()
                path = filtered_model.convert_path_to_child_path(filtered_path)
                itr = model.get_iter(path)
                if itr:
                        preferred = model.get_value(itr, 1)
                        if preferred == False:
                                name = model.get_value(itr, 0)
                                try:
                                        self.img.set_preferred_authority(name)
                                        self.number_of_changes += 1
                                        for row in model:
                                                row[1] = False
                                        model.set_value(itr, 1, not preferred)
                                except api_errors.PermissionsException:
                                        err = self.parent._("Couldn't change" \
                                            " the preferred authority.\n" \
                                            "Please check your permissions.")
                                        self.__error_occured(err,  \
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
                        self.name_error = self.parent._(\
                            "Name contains invalid characters")
                        return False

                model = self.w_repository_treeview.get_model()
                if model:
                        for row in model:
                                if row[0] == name:
                                        self.name_error = self.parent._(\
                                            "Name already in use")
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
                                self.url_error = self.parent._("URL is not valid")
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
                # I am not sure why this needs to be done in an idle
                # function but if it is not the selection has not been
                # updated
                gobject.idle_add(self.__on_repositorytreeview_selection_changed, widget)

        def __on_repositoryadd_clicked(self, widget):
                name = self.w_repository_name.get_text()
                url = self.w_repository_url.get_text()
                p_title = self.parent._("Applying changes")
                p_text = self.parent._("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__add_repository, p_title, p_text,
                    name, url)
                return

        def __run_with_prog_in_thread(self, func, p_title, p_text, *f_args):
                self.w_progress_dialog.set_title(p_title)
                self.w_progressinfo_label.set_text(p_text)
                self.progress_stop_thread = False
                self.w_progress_dialog.show()
                gobject.timeout_add(100, self.__progress_pulse)
                Thread(target = func, args = f_args).start()
                

        def __on_repositoryremove_clicked(self, widget):
                p_title = self.parent._("Applying changes")
                p_text = self.parent._("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__delete_selected_row, p_title,
                    p_text)

        def __on_repositorymodify_clicked(self, widget):
                tsel = self.w_repository_treeview.get_selection()
                selection = tsel.get_selected()
                itr = selection[1]
                if itr != None:
                        model = selection[0]
                        self.old_modify_name = model.get_value(itr, 0)
                        self.old_modify_url = model.get_value(itr, 2)
                        self.old_modify_preferred = model.get_value(itr, 1)
                        self.w_repositorymodify_name.set_text(self.old_modify_name)
                        self.w_repositorymodify_url.set_text(self.old_modify_url)
                        self.w_repositorymodify_dialog.show_all()

        def __on_repositoryclose_clicked(self, widget):
                # if the number is grater then 1 it means that we did something to the
                # repository list and it is safer to reload package info
                if self.number_of_changes > 1:
                        self.parent.reload_packages()
                self.w_repository_dialog.hide()

        def __on_repositorymodifyok_clicked(self, widget):
                self.w_repository_treeview.grab_focus()
                self.w_repositorymodify_dialog.hide()
                name =  self.w_repositorymodify_name.get_text()
                url =  self.w_repositorymodify_url.get_text()
                p_title = self.parent._("Applying changes")
                p_text = self.parent._("Applying changes, please wait ...")
                self.__run_with_prog_in_thread(self.__update_repository, p_title,
                    p_text, name, url)

        def __update_repository(self, name, url):
                url_same = True
                name_same = True
                strt = self.parent._
                if name != self.old_modify_name:
                        name_same = False
                if url != self.old_modify_url:
                        url_same = False
                if url_same and name_same:
                        self.progress_stop_thread = True
                        return
                #we don't enable changing the name of the repository
                #so this part of the code should be skipped in the current
                #implementation.
                if not name_same:
                        omn = self.old_modify_name
                        if not self.__is_name_valid(name):
                                self.progress_stop_thread = True
                                err = strt("Failed to modify %s." % omn + \
                                    "\nThe choosen" + \
                                    " repository name %s is already in use" % name)
                                gobject.idle_add(self.__error_occured, err)
                                self.progress_stop_thread = True
                                return
                        try:
                                self.__delete_repository(self.old_modify_name, False)
                        except api_errors.PermissionsException:
                                # Do nothing
                                err = strt("Failed to modify %s." % omn +
                                    "\nPlease check your permissions.")
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
                        self.__add_repository(name, url, False)
                        if self.old_modify_preferred:
                                self.img.set_preferred_authority(name)
                                self.__prepare_repository_list(False)
                except api_errors.PermissionsException:
                        # Do nothing
                        somn = self.old_modify_name
                        err = strt("Failed to modify %s." % somn + \
                            "\nPlease check your permissions.")
                        self.__error_with_reset_repo_selection(err, \
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
                                    self.old_modify_url, False, stop_thread=False)
                                if somn != name:
                                        self.__delete_repository(name, False)
                                err = self.parent._("Failed to modify %s.") % somn + \
                                self.parent._(
                                    "\nPlease check the network connection or URL.\n"
                                    "Is the repository accessible?")
                                gobject.idle_add(self.__error_occured, err,
                                    gtk.MESSAGE_INFO)
                        except api_errors.CatalogRefreshException:
                                #We need to show at least one warning dialog
                                #This is for repository which didn't existed 
                                #and was modified
                                #To not existed repository
                                somn = self.old_modify_name
                                err = self.parent._("Failed to modify %s.") % somn + \
                                self.parent._(
                                    "\nPlease check the network connection or URL.\n"
                                    "Is the repository accessible?")
                                gobject.idle_add(self.__error_occured, err,
                                    gtk.MESSAGE_INFO)
                self.progress_stop_thread = True
                return


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

        def __add_repository(self, auth, origin_url, silent=True, stop_thread=True):

                if not misc.valid_auth_url(origin_url):
                        err = self.parent._("Invalid URL:\n%s" % origin_url)
                        gobject.idle_add(self.__error_occured, err)
                        gobject.idle_add(self.w_repository_name.grab_focus)
                        self.progress_stop_thread = True
                        return
                try:
                        ssl_key = None
                        ssl_cert = None
                        refresh_catalogs = True
                        self.img.set_authority(auth, origin_url=origin_url,
                            ssl_key=ssl_key, ssl_cert=ssl_cert,
                            refresh_allowed=refresh_catalogs)
                        self.__prepare_repository_list(silent, \
                            auth, stop_thread=stop_thread)
                except RuntimeError, ex:
                        if not silent:
                                raise
                        err = (self.parent._("Failed to add %s.") % auth)
                        err += str(ex)
                        self.__error_with_reset_repo_selection(err)
                        return
                except api_errors.PermissionsException:
                        if not silent:
                                raise
                        err = (self.parent._("Failed to add %s.") % auth) + \
                        self.parent._("\nPlease check your permissions.")
                        self.__error_with_reset_repo_selection(err, \
                            gtk.MESSAGE_INFO)
                except api_errors.CatalogRefreshException:
                        if not silent:
                                raise
                        self.__delete_repository(auth)
                        err = self.parent._("Failed to add %s.") % auth + \
                        self.parent._(
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
                        err = (self.parent._("Failed to delete %s.") % name)
                        err += str(ex)
                        self.__error_with_reset_repo_selection(err)
                        return
                except api_errors.PermissionsException:
                        if not silent:
                                raise
                        err = (self.parent._("Failed to delete %s.") % name) + \
                        self.parent._("\nPlease check your permissions.")
                        self.__error_with_reset_repo_selection(err, \
                            gtk.MESSAGE_INFO)

        def __error_with_reset_repo_selection(self, error_msg, \
            msg_type=gtk.MESSAGE_ERROR):
                gobject.idle_add(self.__error_occured, error_msg, msg_type)
                self.__reset_repo_selection()

        def __reset_repo_selection(self):
                sel = None
                selection = self.w_repository_treeview.get_selection()
                model, ite = selection.get_selected()
                if ite:
                        sel = model.get_value(ite, 0)
                self.__prepare_repository_list(False, sel)

        def __error_occured(self, error_msg, msg_type=gtk.MESSAGE_ERROR):
                msgbox = gtk.MessageDialog(parent = \
                    self.w_repository_dialog, \
                    buttons = gtk.BUTTONS_CLOSE, \
                    flags = gtk.DIALOG_MODAL, \
                    type = msg_type, \
                    message_format = None)
                msgbox.set_markup(error_msg)
                msgbox.set_title("Edit Repositories error")
                msgbox.run()
                msgbox.destroy()

