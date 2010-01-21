#!/usr/bin/python2.6
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


import getopt
import os
import subprocess
import sys
import locale
import gettext
import pango
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

import pkg.portable as portable
import pkg.client.progress as progress
import pkg.client.api as api
import pkg.fmri as fmri
import pkg.gui.beadmin as beadm
import pkg.gui.installupdate as installupdate
import pkg.gui.enumerations as enumerations
import pkg.gui.misc as gui_misc
import pkg.misc as misc
from pkg.client import global_settings
logger = global_settings.logger

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

IMAGE_DIRECTORY_DEFAULT = "/"   # Image default directory
IMAGE_DIR_COMMAND = "svcprop -p update/image_dir svc:/application/pkg/update"

PKG_ICON_LOCATION = "usr/share/package-manager/icons"
ICON_LOCATION = "usr/share/update-manager/icons"
CHECK_FOR_UPDATES = "/usr/lib/pm-checkforupdates"
SHOW_INFO_DELAY = 500           # Delay in milliseconds before showing selected
                                # package information
UPDATES_FETCH_DELAY = 200       # Time to wait before fetching updates, allows gtk main
                                # loop time to start and display main UI
MAX_INFO_CACHE_LIMIT = 100      # Max numger of package descriptions to cache

#UM Row Model
(
UM_ID,
UM_INSTALL_MARK,
UM_STATUS,
UM_NAME,
UM_REBOOT,
UM_LATEST_VER,
UM_SIZE,
UM_STEM,
) = range(8)

class Updatemanager:
        def __init__(self):
                global_settings.client_name = gui_misc.get_um_name()
                    
                try:
                        self.application_dir = os.environ["UPDATE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("pkg", os.path.join(
                            self.application_dir,
                            "usr/share/locale"))
                        module.textdomain("pkg")
                gui_misc.init_for_help(self.application_dir)
                # Duplicate ListStore setup in get_updates_to_list()
                self.um_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # UM_ID
                        gobject.TYPE_BOOLEAN,     # UM_INSTALL_MARK
                        gtk.gdk.Pixbuf,           # UM_STATUS
                        gobject.TYPE_STRING,      # UM_NAME
                        gtk.gdk.Pixbuf,           # UM_REBOOT
                        gobject.TYPE_STRING,      # UM_LATEST_VER
                        gobject.TYPE_STRING,      # UM_SIZE
                        gobject.TYPE_STRING,      # UM_STEM
                        )
                self.progress_stop_thread = False
                self.last_select_time = 0
                self.user_rights = portable.is_admin()
                self.image_dir_arg = None
                self.toggle_counter = 0
                self.last_show_info_id = 0
                self.show_info_id = 0
                self.package_selection = None
                self.update_all_proceed = False
                self.application_path = None
                self.icon_theme = gtk.icon_theme_get_default()
                pkg_icon_location = os.path.join(self.application_dir, PKG_ICON_LOCATION)
                self.icon_theme.append_search_path(pkg_icon_location)
                self.pkg_installed_icon = gui_misc.get_icon(self.icon_theme,
                    'status_installed')
                self.pkg_not_installed_icon = gui_misc.get_icon(self.icon_theme,
                    'status_installed')
                self.pkg_update_available_icon = gui_misc.get_icon(self.icon_theme,
                    'status_newupdate')
                icon_location = os.path.join(self.application_dir, ICON_LOCATION)
                self.icon_theme.append_search_path(icon_location)
                self.pylintstub = None
                self.api_obj = None
                self.use_cache = False # Turns off Details Description cache

                # Progress Dialog
                self.gladefile = os.path.join(self.application_dir,
                    "usr/share/update-manager/updatemanager.glade")
                w_xmltree_progress = gtk.glade.XML(self.gladefile, "progressdialog")
                self.w_progress_dialog = w_xmltree_progress.get_widget("progressdialog")
                self.w_progress_dialog.connect('delete-event', lambda stub1, stub2: True)
                
                self.w_progressinfo_label = w_xmltree_progress.get_widget("progressinfo")
                self.w_progressinfo_separator = w_xmltree_progress.get_widget(
                    "progressinfo_separator")                
                self.w_progressinfo_expander = \
                    w_xmltree_progress.get_widget("progressinfo_expander")
                self.w_progressinfo_textview = \
                    w_xmltree_progress.get_widget("progressinfo_textview")
                infobuffer = self.w_progressinfo_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

                self.w_progress_install_vbox = \
                    w_xmltree_progress.get_widget("progress_install_vbox")
                
                self.w_progress_closeon_finish_chk = \
                    w_xmltree_progress.get_widget("closeon_finish_checkbutton")

                self.w_progress_cancel = w_xmltree_progress.get_widget("progresscancel")
                self.w_progress_ok = w_xmltree_progress.get_widget("progressok")
                self.w_progressbar = w_xmltree_progress.get_widget("progressbar")
                
                # UM Dialog
                w_xmltree_um = gtk.glade.XML(self.gladefile, "um_dialog")
                self.w_um_dialog = w_xmltree_um.get_widget("um_dialog")
                self.w_um_dialog.connect("destroy", self.__on_um_dialog_close)
                self.w_um_intro_label = w_xmltree_um.get_widget("um_intro_label")
                self.w_um_intro2_label = w_xmltree_um.get_widget("um_intro2_label")
                self.w_um_install_button = w_xmltree_um.get_widget("um_install_button")
                self.w_um_updateall_button = \
                    w_xmltree_um.get_widget("um_updateall_button")
                self.pm_image = \
                    w_xmltree_um.get_widget("pm_image")
                self.pm_image.set_from_pixbuf(self.__get_icon_pixbuf('updatemanager', 48))
                self.w_um_expander = w_xmltree_um.get_widget("um_expander")
                self.w_um_expander.set_expanded(True)

                self.w_progress_dialog.set_transient_for(self.w_um_dialog)

                self.w_um_treeview = w_xmltree_um.get_widget("um_treeview")  
                self.w_um_treeview_frame = w_xmltree_um.get_widget("um_treeview_frame")  
                self.w_um_textview = w_xmltree_um.get_widget("um_textview")  
                infobuffer = self.w_um_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_select_checkbox = w_xmltree_um.get_widget("selectall_checkbutton")
                self.w_um_cancel_button = w_xmltree_um.get_widget("cancel_button")
                self.w_um_close_button = w_xmltree_um.get_widget("close_button")

                self.details_cache = {}
                
                try:
                        dic = \
                            {
                                "on_um_dialog_close": \
                                    self.__on_um_dialog_close,
                                "on_cancel_button_clicked": \
                                    self.__on_cancel_button_clicked,
                                "on_close_button_clicked": \
                                    self.__on_cancel_button_clicked,
                                "on_help_button_clicked": \
                                    self.__on_help_button_clicked,
                                "on_um_updateall_button_clicked": \
                                    self.__on_updateall_button_clicked,
                                "on_um_expander_activate": \
                                    self.__on_um_expander_activate,
                                "on_selectall_checkbutton_toggled": \
                                    self.__on_selectall_checkbutton_toggled,
                            }
                        w_xmltree_um.signal_autoconnect(dic)

                except AttributeError, error:
                        print _("GUI will not respond to any event! %s. "
                            "Check updatemanager.py signals") % error

                self.pr = progress.NullProgressTracker()
 
                self.w_um_dialog.show_all()
                self.w_um_dialog.resize(620, 500)
                gui_misc.setup_logging(gui_misc.get_um_name())

        def __set_cancel_state(self, status):
                if status:
                        gobject.idle_add(self.w_progress_cancel.grab_focus)
                gobject.idle_add(self.w_progress_cancel.set_sensitive, status)
                
        def __set_initial_selection(self):
                self.__selectall_toggle(True)
                if len(self.um_list) == 0:
                        self.__display_noupdates()
                else:
                        self.w_um_treeview.set_cursor(0, None)
                        if self.update_all_proceed:
                                self.__on_updateall_button_clicked(None)
                                self.update_all_proceed = False
                        
        def __mark_cell_data_default_function(self, column, renderer, model, itr, data):
                if itr:
                        if model.get_value(itr, UM_STATUS) != None:
                                self.__set_renderer_active(renderer, False)
                        else:
                                self.__set_renderer_active(renderer, True)
                                
        @staticmethod
        def __set_renderer_active(renderer, active):
                if active:
                        renderer.set_property("sensitive", True)
                        renderer.set_property("mode", gtk.CELL_RENDERER_MODE_ACTIVATABLE)
                else:
                        renderer.set_property("sensitive", False)
                        renderer.set_property("mode", gtk.CELL_RENDERER_MODE_INERT)
                
        def __get_icon_pixbuf(self, icon_name, size=16):
                return gui_misc.get_icon(self.icon_theme, icon_name, size)

        def __get_selected_fmris(self):
                model = self.w_um_treeview.get_model()
                iter_next = model.get_iter_first()
                list_of_selected_fmris = []
                while iter_next != None:
                        if model.get_value(iter_next, UM_INSTALL_MARK):
                                list_of_selected_fmris.append(model.get_value(iter_next,
                                    UM_NAME))
                        iter_next = model.iter_next(iter_next)
                return list_of_selected_fmris

        def init_tree_views(self):
                model = self.w_um_treeview.get_model()
                toggle_renderer = gtk.CellRendererToggle()
                toggle_renderer.connect('toggled', self.__active_pane_toggle, model)
                column = gtk.TreeViewColumn("", toggle_renderer,
                    active = UM_INSTALL_MARK)
                column.set_cell_data_func(toggle_renderer,
                    self.__mark_cell_data_default_function, None)                    
                toggle_renderer.set_property("activatable", True)
                column.set_expand(False)

                # Show Cancel, Update All only
                self.w_select_checkbox.hide()
                self.w_um_install_button.hide()
                self.w_um_intro_label.set_markup(_(
                    "<b>Updates are available for the following packages</b>"))
                self.w_um_intro2_label.set_markup(_(
                    "Click Update All to create a new boot environment and "
                    "install all packages into it."))
                        
                render_pixbuf = gtk.CellRendererPixbuf()
                column = gtk.TreeViewColumn()
                column.pack_start(render_pixbuf, expand = False)
                column.add_attribute(render_pixbuf, "pixbuf", UM_STATUS)
                column.set_title("   ")
                # Hiding Status column for now
                #self.w_um_treeview.append_column(column)
                
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Name"), name_renderer,
                    text = UM_NAME)
                column.set_cell_data_func(name_renderer, self.__cell_data_function, None)
                column.set_expand(True)
                self.w_um_treeview.append_column(column)
                
                column = gtk.TreeViewColumn()
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = True)
                column.add_attribute(render_pixbuf, "pixbuf", UM_REBOOT)
                # Hiding Reboot required column for now
                # self.w_um_treeview.append_column(column)

                version_renderer = gtk.CellRendererText()
                version_renderer.set_property('xalign', 0.0)
                column = gtk.TreeViewColumn(_("Current Version"), version_renderer,
                    text = UM_LATEST_VER) 
                column.set_cell_data_func(version_renderer,
                    self.__cell_data_function, None)
                column.set_expand(True)
                self.w_um_treeview.append_column(column)

                size_renderer = gtk.CellRendererText()
                size_renderer.set_property('xalign', 0.0)
                column = gtk.TreeViewColumn(_("Size (Meg)"), size_renderer,
                    text = UM_SIZE)
                column.set_cell_data_func(size_renderer, self.__cell_data_function, None)
                column.set_expand(True)
                # XXX Hiding Size as it takes too long to fetch at the minute
                #self.w_um_treeview.append_column(column)

                #Added selection listener
                self.package_selection = self.w_um_treeview.get_selection()
                self.package_selection.set_mode(gtk.SELECTION_SINGLE)
                self.package_selection.connect("changed",
                    self.__on_package_selection_changed, None)

                # Setup Icons
                self.w_um_dialog.set_icon(self.__get_icon_pixbuf("updatemanager", 36))

        def __get_image_path(self):
                '''This function gets the image path or the default'''
                if self.image_dir_arg != None:
                        return self.image_dir_arg

                try:
                        image_directory = os.environ["PKG_IMAGE"]
                except KeyError:
                        image_directory = \
                            os.popen(IMAGE_DIR_COMMAND).readline().rstrip()
                        if len(image_directory) == 0:
                                image_directory = IMAGE_DIRECTORY_DEFAULT
                return image_directory
                
        def get_updates_to_list(self):
                '''This function fetches a list of the updates
                        that are available to list'''
                # MUST match self.um_list ListStore setup in __init__
                um_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # UM_ID
                        gobject.TYPE_BOOLEAN,     # UM_INSTALL_MARK
                        gtk.gdk.Pixbuf,           # UM_STATUS
                        gobject.TYPE_STRING,      # UM_NAME
                        gtk.gdk.Pixbuf,           # UM_REBOOT
                        gobject.TYPE_STRING,      # UM_LATEST_VER
                        gobject.TYPE_STRING,      # UM_SIZE
                        gobject.TYPE_STRING,      # UM_STEM
                        )

                # Use check_for_updates to determine whether updates
                # are available
                return_code = subprocess.call([CHECK_FOR_UPDATES,
                    self.__get_image_path()])
                if return_code == enumerations.NO_UPDATES_AVAILABLE:
                        self.progress_stop_thread = True
                        gobject.idle_add(self.__display_noupdates)
                        return

                self.api_obj = self.__get_api_obj()

                count = 0
                list_option = api.ImageInterface.LIST_UPGRADABLE
                if list_uninstalled:
                        list_option = api.ImageInterface.LIST_INSTALLED_NEWEST
                pkgs_from_api = self.api_obj.get_pkg_list(pkg_list = list_option)
                for entry in pkgs_from_api:
                        (pkg_pub, pkg_name, ver) = entry[0]
                        states = entry[3]
                        pkg_fmri = fmri.PkgFmri("%s@%s" % (pkg_name, ver),
                            publisher = pkg_pub)
                        add_package = True
                        if list_uninstalled:
                                if api.PackageInfo.INSTALLED in states:
                                        add_package = False

                        if add_package:
                                count += 1
                                # XXX: Would like to caputre if package for upgrade is
                                # incorporated, could then indicate this to user
                                # and take action when doing install to run image-update.
                                #if state["incorporated"]:
                                #        incState = _("Inc")
                                #else:
                                #        incState = "--"
                                pkg_name = gui_misc.get_pkg_name(pkg_name)
                                um_list.insert(count, [count, False, None,
                                    pkg_name, None, 
                                    pkg_fmri.get_version(), None, 
                                    pkg_fmri.get_pkg_stem()])
                                
                if debug:
                        print _("count: %d") % count

                self.progress_stop_thread = True
                gobject.idle_add(self.w_um_treeview.set_model, um_list)
                self.um_list = um_list                
                gobject.idle_add(self.__set_initial_selection)
                        
                # XXX: Currently this will fetch the sizes but it really slows down the
                # app responsiveness - until we get caching I think we should just hide
                # the size column
                # gobject.timeout_add(1000, self.__setup_sizes)
                
        def __get_api_obj(self):
                if self.api_obj == None:
                        self.api_obj = gui_misc.get_api_object(self.__get_image_path(),
                            progress.NullProgressTracker(), self.w_um_dialog)
                return self.api_obj

        def __display_nopermissions(self):
                self.w_um_intro_label.set_markup(
                    _("<b>You do not have sufficient permissions</b>"))
                self.w_um_intro2_label.set_markup(
                    _("Please restart pm-updatemanager using pfexec."))
                self.__setup_display()

        def __display_noupdates(self):
                self.w_um_intro_label.set_markup(_("<b>No Updates available</b>"))
                self.w_um_intro2_label.hide()
                self.__setup_display()

        def __setup_display(self):
                self.w_um_treeview_frame.hide()
                self.w_um_expander.hide()
                self.w_um_install_button.set_sensitive(False)
                self.w_um_updateall_button.hide()
                self.w_um_cancel_button.hide()
                self.w_um_close_button.show()
                self.w_select_checkbox.set_active(False)
                self.w_select_checkbox.set_sensitive(False)
                self.w_um_dialog.present()
                self.w_um_dialog.resize(420, 100)
                
        @staticmethod
        def __removed_filter(model, itr):
                '''This function filters category in the main application view'''
                return True
                
        def __on_package_selection_changed(self, selection, widget):
                '''This function is for handling package selection changes'''
                model, itr = selection.get_selected()
                if self.show_info_id != 0:
                        gobject.source_remove(self.show_info_id)
                        self.show_info_id = 0
                if itr:                        
                        stem = model.get_value(itr, UM_STEM)
                        if self.__setting_from_cache(stem):
                                return
                        pkg_name =  model.get_value(itr, UM_NAME)
                        infobuffer = self.w_um_textview.get_buffer()
                        infobuffer.set_text(
                            _("\nFetching details for %s ...") % pkg_name)
                        self.last_show_info_id = self.show_info_id = \
                            gobject.timeout_add(SHOW_INFO_DELAY,
                            self.__show_info, model, model.get_path(itr))

        def __setting_from_cache(self, stem):
                if not self.use_cache:
                        return False
                if len(self.details_cache) > MAX_INFO_CACHE_LIMIT:
                        self.details_cache = {}

                if self.details_cache.has_key(stem):
                        labs = self.details_cache[stem][0]
                        text = self.details_cache[stem][1]
                        gui_misc.set_package_details_text(labs, text,
                            self.w_um_textview, self.pkg_installed_icon,
                            self.pkg_not_installed_icon, 
                            self.pkg_update_available_icon)
                        return True
                else:
                        return False

        def __show_info(self, model, path):
                self.show_info_id = 0

                itr = model.get_iter(path)
                stem = model.get_value(itr, UM_STEM)
                pkg_name =  model.get_value(itr, UM_NAME)
                Thread(target = self.__show_package_info,
                    args=(stem, pkg_name, self.last_show_info_id)).start()

        def __show_package_info(self, stem, pkg_name, info_id):
                local_info = None
                remote_info = None
                if info_id == self.last_show_info_id:
                        local_info = gui_misc.get_pkg_info(self, self.__get_api_obj(),
                            stem, True) 
                if info_id == self.last_show_info_id:
                        remote_info = gui_misc.get_pkg_info(self, self.__get_api_obj(),
                            stem, False) 
                if info_id == self.last_show_info_id:
                        gobject.idle_add(self.__update_package_info, stem,
                            pkg_name, local_info, remote_info, info_id)
                return 
 
        def  __update_package_info(self, stem, pkg_name, local_info, remote_info,
            info_id):
                if info_id != self.last_show_info_id:
                        return

                if not local_info and not remote_info:
                        infobuffer = self.w_um_textview.get_buffer()
                        infobuffer.set_text("")
                        textiter = infobuffer.get_end_iter()
                        infobuffer.insert_with_tags_by_name(textiter,
                            _("\nNo details available"), "bold")
                        return
                labs, text = gui_misc.set_package_details(pkg_name, local_info,
                    remote_info, self.w_um_textview, self.pkg_installed_icon,
                    self.pkg_not_installed_icon, self.pkg_update_available_icon)
                if self.use_cache:
                        self.details_cache[stem] = (labs, text)

        def __on_um_dialog_close(self, widget):
                self.__exit_app()

        def __on_cancel_button_clicked(self, widget):
                self.__exit_app()
                
        @staticmethod
        def __on_help_button_clicked(widget):
                gui_misc.display_help("um_info")

        def __exit_app(self, restart = False):
                gui_misc.shutdown_logging()
                if restart:
                        if self.image_dir_arg:
                                gobject.spawn_async([self.application_path, "-R",
                                    self.image_dir_arg, "-U"])
                        else:
                                gobject.spawn_async([self.application_path, "-U"])
                self.w_um_dialog.hide()
                gtk.main_quit()
                sys.exit(0)
                return True
        
        def restart_after_ips_update(self):
                self.__exit_app(restart = True)

        def __on_updateall_button_clicked(self, widget):
                self.__selectall_toggle(True)
                self.__get_api_obj().reset()
                installupdate.InstallUpdate([], self,
                    self.__get_image_path(), action = enumerations.IMAGE_UPDATE,
                    parent_name = _("Update Manager"),
                    pkg_list = ["SUNWipkg", "SUNWipkg-gui", "SUNWipkg-um"],
                    main_window = self.w_um_dialog,
                    icon_confirm_dialog = self.__get_icon_pixbuf("updatemanager", 36))
                return
               
        def __on_selectall_checkbutton_toggled(self, widget):
                self.__selectall_toggle(widget.get_active())
                
        def __handle_cancel_exception(self):
                gobject.idle_add(self.w_progress_dialog.hide)
                gobject.idle_add(self.w_progressinfo_expander.set_expanded, False)
                self.__cleanup()                
        
        def __prompt_to_load_beadm(self):
                msgbox = gtk.MessageDialog(parent = self.w_progress_dialog,
                    buttons = gtk.BUTTONS_OK_CANCEL, flags = gtk.DIALOG_MODAL,
                    type = gtk.MESSAGE_ERROR,
                    message_format = _(
                    "Not enough disc space, the Update All action cannot "
                    "be performed.\n\n"
                    "Click OK to manage your existing BEs and free up disk space or "
                    "Cancel to cancel Update All."))
                msgbox.set_title(_("Not Enough Disc Space"))
                result = msgbox.run()
                msgbox.destroy()
                if result == gtk.RESPONSE_OK:
                        gobject.idle_add(self.__create_beadm)
                        
        def __create_beadm(self):
                self.gladefile = \
                        "/usr/share/package-manager/packagemanager.glade"
                beadm.Beadmin(self)
                return False
                
        @staticmethod
        def __unique(list1, list2):
                """Return a list containing all items
                        in 'list1' that are not in 'list2'"""
                list2 = dict([(k, None) for k in list2])
                return [item for item in list1 if item not in list2]
                
        def __cleanup(self):
                self.api_obj.reset()
                self.pr.reset()
                self.progress_stop_thread = True   
                
        @staticmethod
        def __on_um_expander_activate(widget):
                return

        def __selectall_toggle(self, select):
                for row in self.um_list:
                        row[UM_INSTALL_MARK] = select
                if select:
                        self.toggle_counter += len(self.um_list)
                        self.w_um_install_button.set_sensitive(True)
                else:
                        self.toggle_counter = 0
                        self.w_um_install_button.set_sensitive(False)

        def __active_pane_toggle(self, cell, filtered_path, filtered_model):
                model = self.w_um_treeview.get_model()
                itr = model.get_iter(filtered_path)
                if itr:
                        installed = model.get_value(itr, UM_STATUS)
                        if installed is None:
                                modified = model.get_value(itr, UM_INSTALL_MARK)
                                model.set_value(itr, UM_INSTALL_MARK, not modified)
                        if not modified:
                                self.toggle_counter += 1
                        else:
                                self.toggle_counter -= 1

                        if self.toggle_counter > 0:
                                self.w_um_install_button.set_sensitive(True)
                        else:
                                self.toggle_counter = 0
                                self.w_um_install_button.set_sensitive(False)
                                
        @staticmethod
        def __cell_data_function(column, renderer, model, itr, data):
                '''Function which sets the background colour to black if package is 
                selected'''
                if itr:
                        if model.get_value(itr, 1):
                                #XXX Setting BOLD looks too noisy - disable for now
                                # renderer.set_property("weight", pango.WEIGHT_BOLD)
                                renderer.set_property("weight", pango.WEIGHT_NORMAL)
                        else:
                                renderer.set_property("weight", pango.WEIGHT_NORMAL)
        
        def __on_progressdialog_progress(self):
                if not self.progress_stop_thread:
                        self.w_progressbar.pulse()
                        return True
                else:
                        self.w_progress_dialog.hide()
                return False

        def setup_progressdialog_show(self, title):
                infobuffer = self.w_progressinfo_textview.get_buffer()
                infobuffer.set_text("")
                self.w_progressinfo_label.hide()                        
                self.w_progressinfo_expander.hide()    
                self.w_progressinfo_separator.hide()                            
                self.w_progress_cancel.hide() 
                self.w_progress_ok.hide()
                self.w_progress_install_vbox.hide()   
                self.w_progress_closeon_finish_chk.hide()
                self.w_progress_ok.hide()                        
                self.w_progress_dialog.set_title(title)                
                self.w_progress_dialog.show()
                self.progress_stop_thread = False
                gobject.timeout_add(100, self.__on_progressdialog_progress)

        def setup_updates(self):
                if self.user_rights:
                        Thread(target = self.get_updates_to_list, args = ()).start()
                else:
                        self.progress_stop_thread = True
                        self.__display_nopermissions()
                return False

        def update_package_list(self, update_list):
                self.pylintstub = update_list
                return

        def shutdown_after_image_update(self, exit_um = False):
                if exit_um == False:
                        self.__exit_app()

#-------------------- remove those
def main():
        gtk.main()
        return 0
        
if __name__ == "__main__":
        um = Updatemanager()
        list_uninstalled = False
        debug = False

        try:
                opts, args = getopt.getopt(sys.argv[1:], "huR:U",
                    ["help", "uninstalled", "image-dir=", "update-all"])
        except getopt.error, msg:
                print "%s, for help use --help" % msg
                sys.exit(2)

        if os.path.isabs(sys.argv[0]):
                um.application_path = sys.argv[0]
        else:
                cmd = os.path.join(os.getcwd(), sys.argv[0])
                um.application_path = os.path.realpath(cmd)

        for option, argument in opts:
                if option in ("-h", "--help"):
                        print """\
Use -r (--refresh) to force a refresh before checking for updates.
Use -R (--image-dir) to specify image directory.
Use -U (--update-all) to proceed with Update All"""
                        sys.exit(0)
                if option in ("-u", "--uninstalled"):
                        list_uninstalled = True
                if option in ("-R", "--image-dir"):
                        um.image_dir_arg = argument
                if option in ("-U", "--update-all"):
                        um.update_all_proceed = True

        um.init_tree_views()

        um.setup_progressdialog_show(_("Checking for new software"))
        gobject.timeout_add(UPDATES_FETCH_DELAY, um.setup_updates)
        main()

