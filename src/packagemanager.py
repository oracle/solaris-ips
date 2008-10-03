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

# Progress:
# Startup Progress has two phases:
# - Start phase:
#   The start phase should be fairly constant at around a few seconds and so is given 5%
#   of the total progress bar.
# - Package entry loading phase:
#   The package entry loading phase is given the remaining 95% of the bar for progress.

INITIAL_PROGRESS_TIME_INTERVAL = 0.5      # Time to update progress during start phase
INITIAL_PROGRESS_TIME_PERCENTAGE = 0.005  # Amount to update progress during start phase
INITIAL_PROGRESS_TOTAL_PERCENTAGE = 0.05  # Total progress for start phase
PACKAGE_PROGRESS_TOTAL_INCREMENTS = 95.0    # Total increments for loading phase
PACKAGE_PROGRESS_PERCENT_INCREMENT = 0.01 # Amount to update progress during loading phase
PACKAGE_PROGRESS_PERCENT_TOTAL = 1.0      # Total progress for loading phase

import getopt
import os
import sys
import time
import locale
import socket
import gettext
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
import pkg.client.history as history
import pkg.client.image as image
import pkg.client.progress as progress
import pkg.client.retrieve as retrieve
import pkg.misc as misc
import pkg.portable as portable
import pkg.gui.beadmin as beadm
import pkg.gui.imageinfo as imageinfo
import pkg.gui.installupdate as installupdate
import pkg.gui.remove as remove
import pkg.gui.enumerations as enumerations


class PackageManager:
        def __init__(self):
                self.image_o = None
                socket.setdefaulttimeout(
                    int(os.environ.get("PKG_CLIENT_TIMEOUT", "30"))) # in seconds

                # Override default MAX_TIMEOUT_COUNT if a value has been specified
                # in the environment.
                timeout_max = misc.MAX_TIMEOUT_COUNT
                misc.MAX_TIMEOUT_COUNT = int(os.environ.get("PKG_TIMEOUT_MAX",
                    timeout_max))
                    
                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                locale.setlocale(locale.LC_ALL, '')
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("packagemanager", self.application_dir + \
                            "/usr/share/locale")
                        module.textdomain("packagemanager")
                self._ = gettext.gettext
                main_window_title = self._('Package Manager - revision 0.1')
                self.user_rights = portable.is_admin()
                self.cancelled = False                    # For background processes
                self.image_directory = None
                self.description_thread_running = False   # For background processes
                self.pkginfo_thread = None                # For background processes
                gtk.rc_parse('~/.gtkrc-1.2-gnome2')       # Load gtk theme
                self.main_clipboard_text = None
                self.ipkg_fmri = "SUNWipkg"
                self.ipkggui_fmri = "SUNWipkg-gui"
                self.progress_stop_timer_thread = False
                self.progress_fraction_time_count = 0
                self.progress_canceled = False
                self.ips_uptodate = False
                self.image_dir_arg = None
                self.application_path = None

                self.application_list = \
                    gtk.ListStore(
                        gobject.TYPE_BOOLEAN,     # enumerations.MARK_COLUMN
                        gtk.gdk.Pixbuf,           # enumerations.STATUS_ICON_COLUMN
                        gtk.gdk.Pixbuf,           # enumerations.ICON_COLUMN
                        gobject.TYPE_STRING,      # enumerations.NAME_COLUMN
                        gobject.TYPE_STRING,      # enumerations.INSTALLED_VERSION_COLUMN
                        gobject.TYPE_PYOBJECT,    # enumerations.INSTALLED_OBJECT_COLUMN
                        gobject.TYPE_STRING,      # enumerations.LATEST_AVAILABLE_COLUMN
                        gobject.TYPE_INT,         # enumerations.RATING_COLUMN
                        gobject.TYPE_STRING,      # enumerations.DESCRIPTION_COLUMN
                        gobject.TYPE_PYOBJECT,    # enumerations.PACKAGE_OBJECT_COLUMN
                        gobject.TYPE_PYOBJECT,    # enumerations.IMAGE_OBJECT_COLUMN
                        gobject.TYPE_BOOLEAN,     # enumerations.IS_VISIBLE_COLUMN
                        gobject.TYPE_PYOBJECT     # enumerations.CATEGORY_LIST_OBJECT
                        )
                self.category_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.CATEGORY_ID
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_NAME
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_DESCRIPTION
                        gtk.gdk.Pixbuf,           # enumerations.CATEGORY_ICON
                        gobject.TYPE_BOOLEAN,     # enumerations.CATEGORY_VISIBLE
                        gobject.TYPE_PYOBJECT,    # enumerations.SECTION_LIST_OBJECT
                        )
                self.section_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.SECTION_ID
                        gobject.TYPE_STRING,      # enumerations.SECTION_NAME
                        )
                self.filter_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.FILTER_ID
                        gobject.TYPE_STRING,      # enumerations.FILTER_NAME
                        )
                self.repositories_list = \
                    gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.REPOSITORY_ID
                        gobject.TYPE_STRING,      # enumerations.REPOSITORY_NAME
                        )

                self.application_list_filter = self.application_list.filter_new()
                self.pr = progress.NullProgressTracker()

                # Create Widgets and show gui
                
                self.gladefile = self.application_dir + \
                    "/usr/share/package-manager/packagemanager.glade"
                w_tree_main = gtk.glade.XML(self.gladefile, "mainwindow")
                w_tree_progress = gtk.glade.XML(self.gladefile, "progressdialog")
                
                self.w_main_window = w_tree_main.get_widget("mainwindow")
                self.w_application_treeview = \
                    w_tree_main.get_widget("applicationtreeview")
                self.w_categories_treeview = w_tree_main.get_widget("categoriestreeview")
                self.w_generalinfo_textview = \
                    w_tree_main.get_widget("generalinfotextview")
                self.w_installedfiles_textview = \
                    w_tree_main.get_widget("installedfilestextview")
                self.w_dependencies_textview = \
                    w_tree_main.get_widget("dependenciestextview")
                self.w_packagename_label = w_tree_main.get_widget("packagenamelabel")
                self.w_shortdescription_label = \
                    w_tree_main.get_widget("shortdescriptionlabel")
                self.w_searchentry_dialog = w_tree_main.get_widget("searchentry")
                self.w_installupdate_button = \
                    w_tree_main.get_widget("install_update_button")
                self.w_remove_button = w_tree_main.get_widget("remove_button")
                self.w_updateall_button = w_tree_main.get_widget("update_all_button")
                self.w_reload_button = w_tree_main.get_widget("reloadbutton")
                self.w_repository_combobox = w_tree_main.get_widget("repositorycombobox")
                self.w_sections_combobox = w_tree_main.get_widget("sectionscombobox")
                self.w_filter_combobox = w_tree_main.get_widget("filtercombobox")
                self.w_packageicon_image = w_tree_main.get_widget("packageimage")
                self.w_main_statusbar = w_tree_main.get_widget("statusbar")
                self.w_installupdate_menuitem = \
                    w_tree_main.get_widget("package_install_update")
                self.w_remove_menuitem = w_tree_main.get_widget("package_remove")
                self.w_updateall_menuitem = w_tree_main.get_widget("package_update_all")
                self.w_cut_menuitem = w_tree_main.get_widget("edit_cut")
                self.w_copy_menuitem = w_tree_main.get_widget("edit_copy")
                self.w_paste_menuitem = w_tree_main.get_widget("edit_paste")
                self.w_clear_menuitem = w_tree_main.get_widget("edit_clear")
                self.w_selectall_menuitem = w_tree_main.get_widget("edit_select_all")
                self.w_selectupdates_menuitem = \
                    w_tree_main.get_widget("edit_select_updates")
                self.w_deselect_menuitem = w_tree_main.get_widget("edit_deselect")
                self.w_main_clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)

                self.w_progress_dialog = w_tree_progress.get_widget("progressdialog")
                self.w_progress_dialog.set_title(self._("Update All"))
                self.w_progressinfo_label = w_tree_progress.get_widget("progressinfo")
                self.w_progressinfo_label.set_text(self._( \
                    "Checking SUNWipkg and SUNWipkg-gui versions\n\nPlease wait ..."))
                self.w_progressbar = w_tree_progress.get_widget("progressbar")
                self.w_progressbar.set_pulse_step(0.1)
                self.w_progress_cancel = w_tree_progress.get_widget("progresscancel")
                self.progress_canceled = False

                self.__update_reload_button()
                self.w_main_clipboard.request_text(self.__clipboard_text_received)
                self.w_main_window.set_title(main_window_title)

                try:
                        dic_mainwindow = \
                            {
                                "on_mainwindow_delete_event": \
                                    self.__on_mainwindow_delete_event,
                                "on_searchentry_changed":self.__on_searchentry_changed,
                                "on_searchentry_focus_in_event": \
                                    self.__on_searchentry_focus_in,
                                "on_searchentry_focus_out_event": \
                                    self.__on_searchentry_focus_out,
                                "on_searchentry_event":self.__on_searchentry_event,
                                "on_sectionscombobox_changed": \
                                    self.__on_sectionscombobox_changed,
                                "on_filtercombobox_changed": \
                                    self.__on_filtercombobox_changed,
                                "on_repositorycombobox_changed": \
                                    self.__on_repositorycombobox_changed,
                                #menu signals
                                "on_file_quit_activate":self.__on_file_quit_activate,
                                "on_file_be_activate":self.__on_file_be_activate,
                                "on_package_install_update_activate": \
                                    self.__on_install_update,
                                "on_package_remove_activate":self.__on_remove,
                                "on_help_about_activate":self.__on_help_about,
                                "on_edit_paste_activate":self.__on_edit_paste,
                                "on_edit_clear_activate":self.__on_clear_paste,
                                "on_edit_copy_activate":self.__on_copy,
                                "on_edit_cut_activate":self.__on_cut,
                                "on_edit_select_all_activate":self.__on_select_all,
                                "on_edit_select_updates_activate": \
                                    self.__on_select_updates,
                                "on_edit_deselect_activate":self.__on_deselect,
                                # XXX disabled until new API
                                "on_package_update_all_activate":self.__on_update_all,
                                #toolbar signals
                                # XXX disabled until new API
                                "on_update_all_button_clicked":self.__on_update_all,
                                "on_reload_button_clicked":self.__on_reload,
                                "on_install_update_button_clicked": \
                                    self.__on_install_update,
                                "on_remove_button_clicked":self.__on_remove
                            }
                        dic_progress = \
                            {
                                "on_cancel_progressdialog_clicked": \
                                    self.__on_cancel_progressdialog_clicked,
                            }
                        w_tree_main.signal_autoconnect(dic_mainwindow)
                        w_tree_progress.signal_autoconnect(dic_progress)
                except AttributeError, error:
                        print self._( \
                            'GUI will not respond to any event! %s.' + \
                            'Check declare_signals()') \
                            % error
                            
                self.package_selection = None
                self.category_list_filter = None
                self.in_setup = True
                self.w_main_window.show_all()

        def __init_tree_views(self):
                '''This function connects treeviews with their models and also applies
                filters'''
                ##APPLICATION MAIN TREEVIEW
                application_list_sort = \
                    gtk.TreeModelSort(self.application_list_filter)
                self.w_application_treeview.set_model(application_list_sort)
                model = self.w_application_treeview.get_model()
                toggle_renderer = gtk.CellRendererToggle()
                toggle_renderer.connect('toggled', self.__active_pane_toggle, model)
                column = gtk.TreeViewColumn("", toggle_renderer, \
                    active = enumerations.MARK_COLUMN)
                column.set_sort_column_id(enumerations.MARK_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(toggle_renderer, self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                column = gtk.TreeViewColumn()
                column.set_title("")
                #Commented, since there was funny jumping of the icons
                #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = False)
                column.add_attribute(render_pixbuf, "pixbuf", \
                    enumerations.STATUS_ICON_COLUMN)
                column.set_fixed_width(32)
                column.set_cell_data_func(render_pixbuf, self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                column = gtk.TreeViewColumn()
                column.set_title("")
                #Commented, since there was funny jumping of the icons
                #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = False)
                column.add_attribute(render_pixbuf, "pixbuf", enumerations.ICON_COLUMN)
                column.set_fixed_width(32)
                column.set_cell_data_func(render_pixbuf, self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._("Name"), name_renderer, \
                    text = enumerations.NAME_COLUMN)
                column.set_sort_column_id(enumerations.NAME_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(name_renderer, self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                installed_version_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Installed Version'), \
                    installed_version_renderer, \
                    text = enumerations.INSTALLED_VERSION_COLUMN)
                column.set_sort_column_id(enumerations.INSTALLED_VERSION_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(installed_version_renderer, \
                    self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                latest_available_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Latest Version'), \
                    latest_available_renderer, \
                    text = enumerations.LATEST_AVAILABLE_COLUMN)
                column.set_sort_column_id(enumerations.LATEST_AVAILABLE_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(latest_available_renderer, \
                    self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                rating_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Rating'), rating_renderer, \
                    text = enumerations.RATING_COLUMN)
                column.set_cell_data_func(rating_renderer, self.cell_data_function, None)
                description_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Description'), \
                    description_renderer, text = enumerations.DESCRIPTION_COLUMN)
                column.set_sort_column_id(enumerations.DESCRIPTION_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(description_renderer, \
                    self.cell_data_function, None)
                self.w_application_treeview.append_column(column)
                #Added selection listener
                self.package_selection = self.w_application_treeview.get_selection()
                self.package_selection.set_mode(gtk.SELECTION_SINGLE)
                self.package_selection.connect("changed", \
                    self.__on_package_selection_changed, None)
                ##CATEGORIES TREEVIEW
                #enumerations.CATEGORY_NAME
                self.category_list_filter = self.category_list.filter_new()
                self.category_list_filter.set_visible_func(self.category_filter)
                self.w_categories_treeview.set_model(self.category_list_filter)
                enumerations.CATEGORY_NAME_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Name'), \
                    enumerations.CATEGORY_NAME_renderer, \
                    text = enumerations.CATEGORY_NAME)
                self.w_categories_treeview.append_column(column)
                #Added selection listener
                category_selection = self.w_categories_treeview.get_selection()
                category_selection.set_mode(gtk.SELECTION_SINGLE)
                category_selection.connect("changed", \
                    self.__on_category_selection_changed, None)
                ##SECTION COMBOBOX
                #enumerations.SECTION_NAME
                self.w_sections_combobox.set_model(self.section_list)
                cell = gtk.CellRendererText()
                self.w_sections_combobox.pack_start(cell, True)
                self.w_sections_combobox.add_attribute(cell, 'text', \
                    enumerations.SECTION_NAME)
                self.w_sections_combobox.set_row_separator_func( \
                    self.combobox_id_separator)
                ##FILTER COMBOBOX
                #enumerations.FILTER_NAME
                self.w_filter_combobox.set_model(self.filter_list)
                cell = gtk.CellRendererText()
                self.w_filter_combobox.pack_start(cell, True)
                self.w_filter_combobox.add_attribute(cell, 'text', \
                    enumerations.FILTER_NAME)
                self.w_filter_combobox.set_row_separator_func(self.combobox_id_separator)
                ##FILTER COMBOBOX
                #enumerations.FILTER_NAME
                self.w_repository_combobox.set_model(self.repositories_list)
                cell = gtk.CellRendererText()
                self.w_repository_combobox.pack_start(cell, True)
                self.w_repository_combobox.add_attribute(cell, 'text', \
                    enumerations.REPOSITORY_NAME)
                self.w_repository_combobox.set_row_separator_func( \
                    self.combobox_id_separator)
                self.w_filter_combobox.set_active(0)

        def __init_sections(self):
                '''This function is for initializing sections combo box, also adds "All"
                Category. It sets active section combobox entry "All"'''
                self.section_list.append([0, self._('All'), ])
                self.section_list.append([-1, "", ])
                self.section_list.append([2, self._('Meta Packages'), ])
                self.section_list.append([3, self._('Applications Desktop'), ])
                self.section_list.append([4, self._('Applications Web-Based'), ])
                self.section_list.append([5, self._('Operating System'), ])
                self.section_list.append([6, self._('User Environment'), ])
                self.section_list.append([7, self._('Web Infrastructure'), ])

        def __init_show_filter(self):
                self.filter_list.append([0, self._('All Packages'), ])
                self.filter_list.append([-1, "", ])
                self.filter_list.append([2, self._('Installed Packages'), ])
                self.filter_list.append([3, self._('Updates'), ])
                self.filter_list.append([4, self._('Non-installed Packages'), ])
                self.filter_list.append([-1, "", ])
                # self.filter_list.append([self._('Locked Packages'), ])
                # self.filter_list.append(["", ])
                self.filter_list.append([6, self._('Selected Packages'), ])

        def __on_cancel_progressdialog_clicked(self, widget):
                self.progress_canceled = True
                self.progress_stop_timer_thread = True

        def __on_mainwindow_delete_event(self, widget, event):
                ''' handler for delete event of the main window '''
                if self.__check_if_something_was_changed() == True:
                        # XXX Change this to not quit and show dialog
                        # XXX if some changes were applied:
                        self.__main_application_quit()
                        return True
                else:
                        self.__main_application_quit()

        def __on_file_quit_activate(self, widget):
                ''' handler for quit menu event '''
                self.__on_mainwindow_delete_event(None, None)

        def __on_file_be_activate(self, widget):
                ''' handler for be menu event '''
                beadm.Beadmin(self)

        def __on_searchentry_changed(self, widget):
                '''On text search field changed we should refilter the main view'''
                Thread(target = self.__on_searchentry_threaded, args = ()).start()

        def __on_searchentry_threaded(self):
                gobject.idle_add(self.application_list_filter.refilter)
                gobject.idle_add(self.__enable_disable_selection_menus)

        def __on_edit_paste(self, widget):
                self.w_searchentry_dialog.insert_text(self.main_clipboard_text, \
                    self.w_searchentry_dialog.get_position())

        def __on_clear_paste(self, widget):
                bounds = self.w_searchentry_dialog.get_selection_bounds()
                self.w_searchentry_dialog.delete_text(bounds[0], bounds[1])
                return

        def __on_copy(self, widget):
                bounds = self.w_searchentry_dialog.get_selection_bounds()
                text = self.w_searchentry_dialog.get_chars(bounds[0], bounds[1])
                self.w_main_clipboard.set_text(text)
                return

        def __on_cut(self, widget):
                bounds = self.w_searchentry_dialog.get_selection_bounds()
                text = self.w_searchentry_dialog.get_chars(bounds[0], bounds[1])
                self.w_searchentry_dialog.delete_text(bounds[0], bounds[1])
                self.w_main_clipboard.set_text(text)
                return

        def __on_select_all(self, widget):
                sort_filt_model = \
                    self.w_application_treeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                iter_next = sort_filt_model.get_iter_first()
                list_of_paths = []
                while iter_next != None:
                        sorted_path = sort_filt_model.get_path(iter_next)
                        filtered_path = \
                            sort_filt_model.convert_path_to_child_path(sorted_path)
                        path = filt_model.convert_path_to_child_path(filtered_path)
                        list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        itr = model.get_iter(path)
                        model.set_value(itr, enumerations.MARK_COLUMN, True)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_update()
                self.__enable_disable_remove()

        def __on_select_updates(self, widget):
                sort_filt_model = \
                    self.w_application_treeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                iter_next = sort_filt_model.get_iter_first()
                list_of_paths = []
                while iter_next != None:
                        sorted_path = sort_filt_model.get_path(iter_next)
                        filtered_iter = sort_filt_model.convert_iter_to_child_iter(None, \
                            iter_next)
                        app_iter = filt_model.convert_iter_to_child_iter(filtered_iter)

                        filtered_path = \
                            sort_filt_model.convert_path_to_child_path(sorted_path)
                        path = filt_model.convert_path_to_child_path(filtered_path)
                        if model.get_value(app_iter, \
                            enumerations.INSTALLED_VERSION_COLUMN):
                                if  model.get_value(app_iter, \
                                    enumerations.LATEST_AVAILABLE_COLUMN):
                                        list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        itr = model.get_iter(path)
                        model.set_value(itr, enumerations.MARK_COLUMN, True)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_update()
                self.__enable_disable_remove()

        def __on_deselect(self, widget):
                sort_filt_model = \
                    self.w_application_treeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                iter_next = sort_filt_model.get_iter_first()
                list_of_paths = []
                while iter_next != None:
                        sorted_path = sort_filt_model.get_path(iter_next)
                        filtered_iter = sort_filt_model.convert_iter_to_child_iter(None, \
                            iter_next)
                        app_iter = filt_model.convert_iter_to_child_iter(filtered_iter)
                        filtered_path = \
                            sort_filt_model.convert_path_to_child_path(sorted_path)
                        path = filt_model.convert_path_to_child_path(filtered_path)
                        if model.get_value(app_iter, enumerations.MARK_COLUMN):
                                list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        itr = model.get_iter(path)
                        model.set_value(itr, enumerations.MARK_COLUMN, False)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_update()
                self.__enable_disable_remove()

        def __on_searchentry_focus_in(self, widget, event):
                self.w_paste_menuitem.set_sensitive(True)

        def __on_searchentry_focus_out(self, widget, event):
                self.w_paste_menuitem.set_sensitive(False)

        def __on_searchentry_event(self, widget, event):
                self.w_main_clipboard.request_text(self.__clipboard_text_received)
                if widget.get_selection_bounds():
                        #enable selection functions
                        self.w_cut_menuitem.set_sensitive(True)
                        self.w_copy_menuitem.set_sensitive(True)
                        self.w_clear_menuitem.set_sensitive(True)
                else:
                        self.w_cut_menuitem.set_sensitive(False)
                        self.w_copy_menuitem.set_sensitive(False)
                        self.w_clear_menuitem.set_sensitive(False)

        def __on_category_selection_changed(self, selection, widget):
                '''This function is for handling category selection changes'''
                self.application_list_filter.refilter()
                self.__enable_disable_selection_menus()

        def __on_package_selection_changed(self, selection, widget):
                '''This function is for handling package selection changes'''
                model, itr = selection.get_selected()
                if itr:
                        pkg = model.get_value(itr, enumerations.INSTALLED_OBJECT_COLUMN)
                        if not pkg:
                                packages = model.get_value(itr, \
                                    enumerations.PACKAGE_OBJECT_COLUMN)
                                pkg = max(packages)
                        self.pkginfo_thread = pkg
                        Thread(target = self.__show_package_info, \
                            args = (model, itr)).start()

        def __on_filtercombobox_changed(self, widget):
                '''On filter combobox changed'''
                self.application_list_filter.refilter()
                self.__enable_disable_selection_menus()

        def __on_sectionscombobox_changed(self, widget):
                '''On section combobox changed'''
                selected_section = widget.get_active()
                if selected_section == 0:
                        for category in self.category_list:
                                category[enumerations.CATEGORY_VISIBLE] = True
                else:
                        for category in self.category_list:
                                if category[enumerations.CATEGORY_ID] == 0:
                                        category[enumerations.CATEGORY_VISIBLE] = True
                                else:
                                        category_list = \
                                            category[enumerations.SECTION_LIST_OBJECT]
                                        if not category_list:
                                                category[enumerations.CATEGORY_VISIBLE] \
                                                    = False
                                        else:
                                                for section in category_list:
                                                        if section == selected_section:
                                                                category[enumerations. \
                                                                    CATEGORY_VISIBLE] = \
                                                                    True
                                                        else:
                                                                category[enumerations. \
                                                                    CATEGORY_VISIBLE] = \
                                                                    False
                self.category_list_filter.refilter()
                self.application_list_filter.refilter()
                self.__enable_disable_selection_menus()

        def __on_repositorycombobox_changed(self, widget):
                '''On repository combobox changed'''
                if self.in_setup:
                        return
                self.application_list_filter.refilter()
                self.__enable_disable_selection_menus()

        def __on_install_update(self, widget):
                installupdate.InstallUpdate(self.application_list, self, False)

        def __on_update_all(self, widget):
                opensolaris_image = True
                notfound = self.__installed_fmris_from_args(self.image_o, \
                    ["SUNWipkg", "SUNWcs"])

                if notfound:
                        opensolaris_image = False

                if opensolaris_image:
                        # Load the catalogs from the repository, its a long 
                        # running tasks so need a progress dialog
                        self.w_progress_dialog.set_title(self._("Update All"))
                        self.w_progressinfo_label.set_text(self._( \
                            "Checking SUNWipkg and SUNWipkg-gui versions\n" + \
                            "\nPlease wait ..."))

                        self.w_progress_dialog.show()
                        Thread(target = self.__progressdialog_progress_pulse).start()
                        Thread(target = self.__do_ips_uptodate_check).start()
                        self.w_progress_dialog.run()
                        
                        if self.progress_canceled:
                                return
                else:
                        self.ips_uptodate = True
                        
                #2790: Make sure ipkg and ipkg-gui are up to date, if not update them and
                # prompt user to restart
                if not self.ips_uptodate:
                        # Prompt user
                        msgbox = gtk.MessageDialog(parent = self.w_main_window, \
                            buttons = gtk.BUTTONS_YES_NO, \
                            flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_QUESTION, \
                            message_format = self._("Newer versions of SUNWipkg and" + \
                            "SUNWipkg-gui are available " + "and\nmust be updated" + \
                            "before running Update All.\n\n Do you want to update" + \
                            "them now?"))
                        msgbox.set_title(self._("Update All"))
                        result = msgbox.run()
                        msgbox.destroy()
                        if result == gtk.RESPONSE_YES:
                                pkg_list = [self.ipkg_fmri, self.ipkggui_fmri]
                                installupdate.InstallUpdate({self.image_o:pkg_list}, \
                                    self, False, True)
                        else:
                                msgbox = gtk.MessageDialog(parent = self.w_main_window, \
                                    buttons = gtk.BUTTONS_OK, \
                                    flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_INFO, \
                                    message_format = self._("Update All was not " + \
                                    "run.\n\n It can not be run until SUNWipkg and " + \
                                    "SUNWipkg-gui have been updated."))
                                msgbox.set_title(self._("Update All"))
                                result = msgbox.run()
                                msgbox.destroy()
                else:                        
                        pkg_list = [ ipkg.get_pkg_stem() for ipkg in \
                            self.image_o.gen_installed_pkgs() ]
                        installupdate.InstallUpdate({self.image_o:pkg_list}, self, \
                            True, False)

        def __on_help_about(self, widget):
                wTreePlan = gtk.glade.XML(self.gladefile, "aboutdialog") 
                aboutdialog = wTreePlan.get_widget("aboutdialog")
                aboutdialog.connect("response", lambda x = None, \
                    y = None: aboutdialog.destroy())
                aboutdialog.run()

        def __on_remove(self, widget):
                remove.Remove(self.application_list, self)

        def __on_reload(self, widget):
                if self.description_thread_running:
                        self.cancelled = True
                self.__catalog_refresh()
                self.process_package_list_start(self.image_directory)
                self.category_list_filter.refilter()
                self.application_list_filter.refilter()
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__update_install_update_button(None, True)
                self.__update_remove_button(None, True)

        def __clipboard_text_received(self, clipboard, text, data):
                self.main_clipboard_text = text
                return

        def __main_application_quit(self, restart_app = False):
                '''quits the main gtk loop'''
                self.cancelled = True
                if self.in_setup:
                        return
                        
                if restart_app:
                        if "image_dir_arg" in self.__dict__:
                                gobject.spawn_async([self.application_path, "-R", \
                                    self.image_dir_arg])
                        else:
                                gobject.spawn_async([self.application_path])
                gtk.main_quit()
                sys.exit(0)
                return True

        def __check_if_something_was_changed(self):
                ''' Returns True if any of the check boxes for package was changed, false
                if not'''
                for pkg in self.application_list:
                        if pkg[enumerations.MARK_COLUMN] == True:
                                return True
                return False

        def __setup_repositories_combobox(self, img):
                if self.in_setup or img == None:
                        return
                        
                repositories = img.catalogs
                default_authority = img.get_default_authority()
                self.repositories_list.clear()
                i = 0
                active = 0
                for repo in repositories:
                        if cmp(repo, default_authority) == 0:
                                active = i

                        self.repositories_list.append([i, repo, ])
                        i = i + 1
                if default_authority:
                        self.w_repository_combobox.set_active(active)
                else:
                        self.w_repository_combobox.set_active(0)

        def __active_pane_toggle(self, cell, path, model_sort):
                '''Toggle function for column enumerations.MARK_COLUMN'''
                applicationModel = model_sort.get_model()
                applicationPath = model_sort.convert_path_to_child_path(path)
                filterModel = applicationModel.get_model()
                child_path = applicationModel.convert_path_to_child_path(applicationPath)
                itr = filterModel.get_iter(child_path)
                if itr:
                        modified = filterModel.get_value(itr, enumerations.MARK_COLUMN)
                        filterModel.set_value(itr, enumerations.MARK_COLUMN, \
                            not modified)
                        latest_available = filterModel.get_value(itr, \
                            enumerations.LATEST_AVAILABLE_COLUMN)
                        installed_available = filterModel.get_value(itr, \
                            enumerations.INSTALLED_VERSION_COLUMN)
                        self.update_statusbar()
                        self.__update_install_update_button(latest_available, modified)
                        self.__update_remove_button(installed_available, modified)
                        self.__enable_disable_selection_menus()


        def __update_install_update_button(self, latest_available, toggle_true):
                if not toggle_true and self.user_rights:
                        if latest_available:
                                self.w_installupdate_button.set_sensitive(True)
                                self.w_installupdate_menuitem.set_sensitive(True)
                else:
                        available = None
                        for row in self.application_list:
                                if row[enumerations.MARK_COLUMN]:
                                        available = \
                                            row[enumerations.LATEST_AVAILABLE_COLUMN]
                                        if available:
                                                return
                        if not available:
                                self.w_installupdate_button.set_sensitive(False)
                                self.w_installupdate_menuitem.set_sensitive(False)

        def __update_reload_button(self):
                if self.user_rights:
                        self.w_reload_button.set_sensitive(True)
                else:
                        self.w_reload_button.set_sensitive(False)

        def __update_remove_button(self, installed_available, toggle_true):
                if not toggle_true and self.user_rights:
                        if installed_available:
                                self.w_remove_button.set_sensitive(True)
                                self.w_remove_menuitem.set_sensitive(True)
                else:
                        available = None
                        for row in self.application_list:
                                if row[enumerations.MARK_COLUMN]:
                                        installed = \
                                            row[enumerations.INSTALLED_VERSION_COLUMN]
                                        if installed:
                                                return
                        if not available:
                                self.w_remove_button.set_sensitive(False)
                                self.w_remove_menuitem.set_sensitive(False)

        def __update_package_info(self, pkg, icon, installed, manifest):
                if icon and icon != pkg:
                        self.w_packageicon_image.set_from_pixbuf(icon)
                else:
                        self.w_packageicon_image.set_from_pixbuf( \
                            self.__get_pixbuf_from_path("/usr/share/package-manager/", \
                            "PM_package_36x"))
                self.w_packagename_label.set_markup("<b>" + pkg.get_name() + "</b>")
                instbuffer = self.w_installedfiles_textview.get_buffer()
                depbuffer = self.w_dependencies_textview.get_buffer()
                infobuffer = self.w_generalinfo_textview.get_buffer()
                if not manifest:
                        self.w_shortdescription_label.set_text( \
                            self._("Fetching description..."))
                        instbuffer.set_text(self._("Fetching information..."))
                        depbuffer.set_text(self._("Fetching information..."))
                        infobuffer.set_text(self._("Fetching information..."))
                        return
                if manifest == "NotAvailable":
                        self.w_shortdescription_label.set_text( \
                            self._("Description not available for this package..."))
                        instbuffer.set_text( \
                            self._("Files Details not available for this package..."))
                        depbuffer.set_text(self._( \
                            "Dependencies info not available for this package..."))
                        infobuffer.set_text( \
                            self._("Information not available for this package..."))
                        return
                self.w_shortdescription_label.set_text(manifest.get("description", ""))
                instbuffer.set_text(self._("Root: %s\n") % manifest.img.get_root())
                depbuffer.set_text(self._("Dependencies:\n"))
                if installed:
                        infobuffer.set_text( \
                            self._("Information for installed package:\n\n"))
                else:
                        infobuffer.set_text( \
                            self._("Information for latest available package:\n\n"))
                depiter = depbuffer.get_end_iter()
                institer = instbuffer.get_end_iter()
                infoiter = infobuffer.get_end_iter()
                #Name: SUNWckr 
                #FMRI: pkg://opensolaris.org/SUNWckr@0.5.11,5.11-0.75:20071114T203148Z
                #Version: 0.5.11
                #Branch: 0.75
                #Packaging Date: 2007-11-14 20:31:48
                #Size: 29369698
                #Summary: Core Solaris Kernel (Root)
                for a in manifest.actions:
                        if cmp(a.name, self.n_("depend")) == 0:
                                #Remove "depend: " -> [8:]
                                depbuffer.insert(depiter, "\t" + \
                                    self.__locale_distinguished_name(a)[8:]+"\n")
                        elif cmp(a.name,self.n_("dir")) == 0:
                                instbuffer.insert(institer, "\t" + \
                                    self.__locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.n_("file")) == 0:
                                instbuffer.insert(institer, "\t" + \
                                    self.__locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.n_("hardlink")) == 0:
                                instbuffer.insert(institer, "\t" + \
                                    self.__locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.n_("link")) == 0:
                                instbuffer.insert(institer, "\t" + \
                                    self.__locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.n_("legacy")) == 0:
                                if cmp(a.attrlist(self.n_("pkg"))[0], \
                                    pkg.get_name()) == 0:
                                        desc = a.attrlist(self.n_("desc"))
                                        infobuffer.insert(infoiter, \
                                            self._("  Description:\t%s\n") % desc[0])
                        else:
                                pass
                infobuffer.insert(infoiter, self._("  Name:\t\t%s\n") % pkg.get_name())
                infobuffer.insert(infoiter, self._("  FMRI:\t\t%s\n") % pkg.get_fmri())
                infobuffer.insert(infoiter, self._("  Version:\t\t%s\n") % \
                    pkg.version.get_short_version())
                infobuffer.insert(infoiter, self._("  Packaged:\t%s\n") % \
                    self.get_datetime(pkg.version))

        def __update_description(self, description, package):
                '''workaround function'''
                for pkg in self.application_list:
                        p = pkg[enumerations.PACKAGE_OBJECT_COLUMN][0]
                        if p == package:
                                pkg[enumerations.DESCRIPTION_COLUMN] = description
                                return

        def __show_package_info(self, model, itr):
                img = model.get_value(itr, enumerations.IMAGE_OBJECT_COLUMN)
                pkg = model.get_value(itr, enumerations.INSTALLED_OBJECT_COLUMN)
                icon = model.get_value(itr, enumerations.INSTALLED_OBJECT_COLUMN)
                if not pkg:
                        packages = model.get_value(itr, \
                            enumerations.PACKAGE_OBJECT_COLUMN)
                        pkg = max(packages)
                        gobject.idle_add(self.__update_package_info, pkg, icon, False, \
                            None)
                else:
                        gobject.idle_add(self.__update_package_info, pkg, icon,
                            True, None)
                man = None
                img.history.operation_name = "info"
                try:
                        man = img.get_manifest(pkg, filtered = True)
                except IOError:
                        man = "NotAvailable"
                        img.history.operation_result = \
                            history.RESULT_FAILED_STORAGE
                except:
                        img.history.operation_result = \
                            history.RESULT_FAILED_UNKNOWN

                if cmp(self.pkginfo_thread, pkg) == 0:
                        if not pkg:
                                gobject.idle_add(self.__update_package_info, pkg, icon, \
                                    False, man)
                        else:
                                gobject.idle_add(self.__update_package_info, pkg, icon, \
                                    True, man)
                        img.history.operation_result = \
                            history.RESULT_SUCCEEDED
                else:
                        img.history.operation_result = \
                            history.RESULT_SUCCEEDED
                        return

        # This function is ported from pkg.actions.generic.distinguished_name()
        def __locale_distinguished_name(self, action):
                if action.key_attr == None:
                        return str(action)
                return "%s: %s" % \
                    (self._(action.name), action.attrs.get(action.key_attr, "???"))

        def __application_filter(self, model, itr):
                '''This function is used to filter content in the main 
                application view'''
                if self.in_setup or self.cancelled:
                        return False
                # XXX Show filter, chenge text to integers 
                selected_category = 0
                selection = self.w_categories_treeview.get_selection()
                category_model, category_iter = selection.get_selected()
                if not category_iter:         #no category was selected, so select "All"
                        selection.select_path(0)
                        category_model, category_iter = selection.get_selected()
                if category_iter:
                        selected_category = category_model.get_value(category_iter, \
                            enumerations.CATEGORY_ID)
                category_list_iter = model.get_value(itr, \
                    enumerations.CATEGORY_LIST_OBJECT)
                category = False
                repository = self.__is_pkg_repository_visible(model, itr)
                if category_list_iter:
                        sel = False
                        for category_iter in category_list_iter:
                                if category != True:
                                        category = \
                                            self.category_filter(self.category_list, \
                                            category_iter)
                                if selected_category != 0:
                                        if selected_category == \
                                            self.category_list.get_value(category_iter, \
                                            enumerations.CATEGORY_ID):
                                                sel = True
                                        category = sel
                else:
                        if selected_category == 0:
                                selected_section = self.w_sections_combobox.get_active()
                                if selected_section == 0:
                                        category = True
                if (model.get_value(itr, enumerations.IS_VISIBLE_COLUMN) == False):
                        return False
                if self.w_searchentry_dialog.get_text() == "":
                        return (repository & category & \
                            self.__is_package_filtered(model, itr))
                if not model.get_value(itr, enumerations.NAME_COLUMN) == None:
                        if self.w_searchentry_dialog.get_text().lower() in \
                            model.get_value \
                            (itr, enumerations.NAME_COLUMN).lower():
                                return (repository & category & \
                                    self.__is_package_filtered(model, itr))
                if not model.get_value(itr, enumerations.DESCRIPTION_COLUMN) == None:
                        if self.w_searchentry_dialog.get_text().lower() in \
                            model.get_value \
                            (itr, enumerations.DESCRIPTION_COLUMN).lower():
                                return (repository & category & \
                                    self.__is_package_filtered(model, itr))
                else:
                        return False

        def __is_package_filtered(self, model, itr):
                '''Function for filtercombobox'''
                # XXX Instead of string comparison, we should do it through integers.
                # XXX It should be faster and better for localisations.
                filter_text = self.w_filter_combobox.get_active()
                if filter_text == 0:
                        return True
                elif filter_text == 2:
                        return model.get_value(itr, \
                            enumerations.INSTALLED_VERSION_COLUMN) != None
                elif filter_text == 3:
                        return (model.get_value(itr, \
                            enumerations.INSTALLED_VERSION_COLUMN) != None) & \
                            (model.get_value(itr, \
                            enumerations.LATEST_AVAILABLE_COLUMN) != None)
                elif filter_text == 4:
                        return not model.get_value(itr, \
                            enumerations.INSTALLED_VERSION_COLUMN) != None
                elif filter_text == 6:
                        return model.get_value(itr, enumerations.MARK_COLUMN)
                elif filter_text == 8:
                        # XXX Locked support
                        return False


        def __is_pkg_repository_visible(self, model, itr):
                if len(self.repositories_list) <= 1:
                        return True
                else:
                        auth_iter = self.w_repository_combobox.get_active_iter()
                        authority = self.repositories_list.get_value(auth_iter, \
                            enumerations.REPOSITORY_NAME)
                        packages = model.get_value(itr, \
                            enumerations.PACKAGE_OBJECT_COLUMN)
                        if not packages:
                                return False
                        pkg = max(packages)
                        if cmp(pkg.get_authority(), authority) == 0:
                                return True
                        else:
                                return False

        def __do_ips_uptodate_check(self):
                self.ips_uptodate = self.__ipkg_ipkgui_uptodate(self.image_o)
                self.progress_stop_timer_thread = True

        def __ipkg_ipkgui_uptodate(self, img):
                if not img.is_liveroot():
                        newimg = image.Image()
                        cmdpath = os.path.join(os.getcwd(), sys.argv[0])
                        cmdpath = os.path.realpath(cmdpath)
                        cmddir = os.path.dirname(os.path.realpath(cmdpath))
                        try:
                                #
                                # Find the path to ourselves, and use that
                                # as a way to locate the image we're in.  It's
                                # not perfect-- we could be in a developer's
                                # workspace, for example.
                                #
                                newimg.find_root(cmddir)
                        except ValueError:
                                # We can't answer in this case, so we return True to
                                # let installation proceed.
                                # TODO: log - msg(_("No image corresponding to '%s' was 
                                # located. " \ "Proceeding.") % cmdpath)
                                return True
                        newimg.load_config()
                        img = newimg

                try:
                        img.retrieve_catalogs()
                except image.CatalogRefreshException:
                        raise
                # Reload catalog.  This picks up the update from retrieve_catalogs.
                img.load_catalogs(self.pr)
 
                try:
                        # We will use whatever the incorporation provides as the latest 
                        # version of ipkg and ipkg-gui
                        img.make_install_plan([self.ipkg_fmri, self.ipkggui_fmri], \
                            self.pr, filters = [], noexecute = True)
                except RuntimeError:
                        return True

                if img.imageplan.nothingtodo():
                        return True                

                return False


        def __enable_disable_selection_menus(self):
                
                if self.in_setup:
                        return
                self.__enable_disable_select_all()
                self.__enable_disable_select_updates()
                self.__enable_disable_deselect()
                # XXX disabled until new API
                self.__enable_disable_update_all()

        def __enable_disable_select_all(self):
                
                if self.in_setup:
                        return
                if len(self.w_application_treeview.get_model()) > 0:
                        for row in self.w_application_treeview.get_model():
                                if not row[enumerations.MARK_COLUMN]:
                                        self.w_selectall_menuitem.set_sensitive(True)
                                        return
                        self.w_selectall_menuitem.set_sensitive(False)
                else:
                        self.w_selectall_menuitem.set_sensitive(False)

        def __enable_disable_install_update(self):
                for row in self.application_list:
                        if row[enumerations.MARK_COLUMN]:
                                if row[enumerations.LATEST_AVAILABLE_COLUMN] and \
                                    self.user_rights:
                                        self.w_installupdate_button.set_sensitive(True)
                                        self.w_installupdate_menuitem.set_sensitive(True)
                                        return
                self.w_installupdate_button.set_sensitive(False)
                self.w_installupdate_menuitem.set_sensitive(False)

        def __enable_disable_remove(self):
                for row in self.application_list:
                        if row[enumerations.MARK_COLUMN]:
                                if row[enumerations.INSTALLED_VERSION_COLUMN] and \
                                    self.user_rights:
                                        self.w_remove_button.set_sensitive(True)
                                        self.w_remove_menuitem.set_sensitive(True)
                                        return
                self.w_remove_button.set_sensitive(False)
                self.w_remove_menuitem.set_sensitive(False)

        def __enable_disable_select_updates(self):
                for row in self.w_application_treeview.get_model():
                        if row[enumerations.INSTALLED_VERSION_COLUMN]:
                                if row[enumerations.LATEST_AVAILABLE_COLUMN]:
                                        if not row[enumerations.MARK_COLUMN]:
                                                self.w_selectupdates_menuitem. \
                                                    set_sensitive(True)
                                                return
                self.w_selectupdates_menuitem.set_sensitive(False)
                return

        def __enable_disable_update_all(self):
                for row in self.application_list:
                        if self.__is_pkg_repository_visible(self.application_list, \
                            row.iter):
                                if self.application_list.get_value(row.iter, \
                                    enumerations.INSTALLED_VERSION_COLUMN):
                                        if self.application_list.get_value(row.iter, \
                                            enumerations.LATEST_AVAILABLE_COLUMN) and \
                                            self.user_rights:
                                                self.w_updateall_menuitem. \
                                                    set_sensitive(True)
                                                self.w_updateall_button. \
                                                    set_sensitive(True)
                                                return
                self.w_updateall_button.set_sensitive(False)
                self.w_updateall_menuitem.set_sensitive(False)

        def __enable_disable_deselect(self):
                for row in self.w_application_treeview.get_model():
                        if row[enumerations.MARK_COLUMN]:
                                self.w_deselect_menuitem.set_sensitive(True)
                                return
                self.w_deselect_menuitem.set_sensitive(False)
                return


        def __catalog_refresh(self):
                """Update image's catalogs."""
                images = self.__get_images_from_model()
                full_refresh = False
                for img in images:
                        # Ensure Image directory structure is valid.
                        if not os.path.isdir("%s/catalog" % img.imgdir):
                                img.mkdirs()
                        # Loading catalogs allows us to perform incremental update
                        img.retrieve_catalogs(full_refresh)

        def __get_images_from_model(self):
                images = []
                for row in self.application_list:
                        img = row[enumerations.IMAGE_OBJECT_COLUMN]
                        if img:
                                if not img in images:
                                        images.append(img)
                return images 

        def __get_image_obj_from_directory(self, image_directory):
                image_obj = image.Image()
                dr = "/"
                try:
                        image_obj.find_root(image_directory,
                            self.provided_image_dir)
                        image_obj.load_config()
                        image_obj.load_catalogs(self.pr)
                except image.ImageNotFoundException, infe:
                        print self._("%s is not a valid root image, return "
                            "None") % infe.user_dir
                        image_obj = None


                # Tell the image the name of the client performing operations.
                if image_obj is not None:
                        image_obj.history.client_name = "packagemanager"

                return image_obj

        def __get_image_from_directory(self, image_obj, progressdialog_progress):
                """ This method set up image from the given directory and
                returns the image object or None"""
                # XXX Convert timestamp to some nice date :)
                self.application_list.clear()
                self.category_list.clear()
                self.application_list_filter.refilter()
                try:
                        pkgs_known = [ pf[0] for pf in
                            sorted(image_obj.inventory(all_known = True)) ]
                except image.InventoryException:
                        # Can't happen when all_known is true and no args,
                        # but here for completeness.
                        raise
                #Only one instance of those icons should be in memory
                update_available_icon = self.get_icon_pixbuf("new_update")
                #Imageinfo for categories
                imginfo = imageinfo.ImageInfo()
                sectioninfo = imageinfo.ImageInfo()
                catalogs = image_obj.catalogs
                categories = {}
                sections = {}
                self.__setup_repositories_combobox(image_obj)
                for cat in catalogs:
                        category = imginfo.read(self.application_dir + \
                            "/usr/share/package-manager/data/" + cat)
                        categories[cat] = category
                        section = sectioninfo.read(self.application_dir + \
                            "/usr/share/package-manager/data/" + cat + ".sections")
                        sections[cat] = section
                # Speedup, instead of checking if the pkg is already in the list, 
                # iterating through all elements, we will only compare to the previous
                # package and if the package is the same (version difference) then we
                # are adding to the first iterator for the set of those packages. 
                # We can do that, since the list pkgs_known is sorted
                # This will give a sppedup from 18sec to ~3!!!
                p_pkg_iter = None
                p_pkg = None
                insert_count = 0
                icon_path = self.application_dir + \
                    "/usr/share/package-manager/data/pixmaps/"

                pkg_count = 0
                progress_percent = INITIAL_PROGRESS_TOTAL_PERCENTAGE
                total_pkg_count = len(pkgs_known)
                progress_increment = \
                        total_pkg_count / PACKAGE_PROGRESS_TOTAL_INCREMENTS

                self.progress_stop_timer_thread = True
                while gtk.events_pending():
                        gtk.main_iteration(False)
                for pkg in pkgs_known:
                        if pkg_count % progress_increment == 0:
                                progress_percent += PACKAGE_PROGRESS_PERCENT_INCREMENT
                                if progress_percent <= PACKAGE_PROGRESS_PERCENT_TOTAL:
                                        gobject.idle_add(progressdialog_progress,
                                            progress_percent, pkg_count, total_pkg_count)
                                while gtk.events_pending():
                                        gtk.main_iteration(False)
                        pkg_count += 1
                        
                        #speedup hack, check only last package
                        already_in_model = \
                            self.check_if_pkg_have_row_in_model(pkg, p_pkg)
                        if not already_in_model:         #Create new row
                                available_version = None
                                version_installed = None
                                status_icon = None
                                fmris = [pkg, ]
                                package_installed = \
                                    self.get_installed_version(image_obj, pkg)
                                if package_installed:
                                        version_installed = \
                                            package_installed.version.get_short_version()
                                        #HACK, sometimes the package is installed but 
                                        #it's not in the pkgs_known
                                        if package_installed != pkg:
                                                fmris.append(package_installed)
                                else:
                                        dt = self.get_datetime(pkg.version)
                                        dt_str = (":%02d%02d") % (dt.month, dt.day)
                                        available_version = \
                                            pkg.version.get_short_version() + dt_str
                                package_icon = self.__get_pixbuf_from_path(icon_path, \
                                    pkg.get_name())
                                app = \
                                    [
                                        False, status_icon, package_icon, pkg.get_name(),
                                        version_installed, package_installed,
                                        available_version, -1, '...', fmris,
                                        image_obj, True, None
                                    ]
                                # XXX Small hack, if this is not applied, first package 
                                # is listed twice. Insert is ~0.5 sec faster than append
                                if insert_count == 0:
                                        row_iter = self.application_list.append(app)
                                else:
                                        row_iter = \
                                            self.application_list.insert(insert_count, \
                                            app)
                                # XXX Do not iterate through all the catalogs. Package 
                                # should know what is package fmri prefix?
                                apc = self.__add_package_to_category
                                for cat in categories:
                                        if cat in categories:
                                                name = pkg.get_name()
                                                if name in categories[cat]:
                                                        pkg_categories = \
                                                            categories[cat][ \
                                                            name]
                                                        for pcat in \
                                                            pkg_categories.split(","):
                                                                if pcat:
                                                                        apc(self._( \
                                                                            pcat), None \
                                                                            , None, \
                                                                            row_iter)
                                insert_count = insert_count + 1
                                p_pkg_iter = row_iter
                                p_pkg = pkg                  #The current become previous
                        else:
                                # XXX check versions in here. For all installed/not 
                                # installed:
                                # if there is newer version, put it in the available 
                                # field.
                                #
                                # XXXhack, since image_get_version_installed(pkg) is not 
                                # working,as it should. For example package:
                                # SUNWarc@0.5.11,5.11-0.79:20080205T152309Z
                                # is not installed and it's newer version of installed
                                # package:
                                # SUNWarc@0.5.11,5.11-0.75:20071114T201151Z
                                # the function returns only proper installed version for 
                                # the older package and None for the newer.
                                # The hack is a little bit slow since we are iterating 
                                # for all known packages
                                list_of_pkgs = \
                                    self.application_list.get_value(p_pkg_iter, \
                                    enumerations.PACKAGE_OBJECT_COLUMN)
                                if pkg not in list_of_pkgs:
                                        list_of_pkgs.append(pkg)
                                installed = self.application_list.get_value(p_pkg_iter, \
                                    enumerations.INSTALLED_OBJECT_COLUMN)
                                latest = max(list_of_pkgs)
                                dt = self.get_datetime(latest.version)
                                dt_str = (":%02d%02d") % (dt.month, dt.day)
                                if not installed:
                                        self.application_list.set_value(p_pkg_iter, \
                                            enumerations.LATEST_AVAILABLE_COLUMN, \
                                            latest.version.get_short_version() + \
                                            dt_str)
                                else:
                                        if installed < latest:
                                                self.application_list.set_value( \
                                                    p_pkg_iter, \
                                                    enumerations. \
                                                    LATEST_AVAILABLE_COLUMN, \
                                                    latest.version.get_short_version() + \
                                                    dt_str)
                                                self.application_list.set_value(\
                                                    p_pkg_iter, \
                                                    enumerations.STATUS_ICON_COLUMN, \
                                                    update_available_icon)
                        # XXX How to get descriptions without manifest?
                        # XXX Downloading manifest is slow and can not work without 
                        # XXX Network connection
                        #if not image_obj.has_manifest(pkg):
                        #        image_obj.get_manifest(pkg)#verify(pkg, pr)
                        #installed_version = None
                        #package_iter = None #the iterator which points for other package
                for authority in sections:
                        for section in sections[authority]:
                                for category in sections[authority][section].split(","):
                                        self.__add_category_to_section(self._(category), \
                                            self._(section))

                #1915 Sort the Categories into alphabetical order and prepend All Category
                if len(self.category_list) > 0:
                        rows = [tuple(r) + (i,) for i, r in enumerate(self.category_list)]
                        rows.sort(self.__sort)
                        r = []
                        self.category_list.reorder([r[-1] for r in rows])
                self.category_list.prepend([0, self._('All'), None, None, True, None])

                gobject.idle_add(progressdialog_progress, PACKAGE_PROGRESS_PERCENT_TOTAL,
                        pkg_count, total_pkg_count)

        def __add_package_to_category(self, category_name, category_description, \
            category_icon, package):
                if not package or category_name == self._('All'):
                        return
                if not category_name:
                        return
                        # XXX check if needed
                        # category_name = self._('All')
                        # category_description = self._('All packages')
                        # category_icon = None
                category_ref = None
                for category in self.category_list:
                        if category[enumerations.CATEGORY_NAME] == category_name:
                                category_ref = category.iter
                if not category_ref:                       # Category not exists
                        category_ref = self.category_list.append([len( \
                            self.category_list), category_name, category_description, \
                            category_icon, True, None])
                if category_ref:
                        if self.application_list.get_value(package, \
                            enumerations.CATEGORY_LIST_OBJECT):
                                a = self.application_list.get_value(package, \
                                    enumerations.CATEGORY_LIST_OBJECT)
                                a.append(category_ref)
                        else:
                                category_list = []
                                category_list.append(category_ref)
                                self.application_list.set(package, \
                                    enumerations.CATEGORY_LIST_OBJECT, category_list)

        def __add_category_to_section(self, category_name, section_name):
                '''Adds the section to section list in category. If there is no such 
                section, than it is not added. If there was already section than it
                is skipped. Sections must be case sensitive'''
                if not category_name:
                        return
                for section in self.section_list:
                        if section[enumerations.SECTION_NAME] == section_name:
                                for category in self.category_list:
                                        if category[enumerations.CATEGORY_NAME] == \
                                            category_name:
                                                if not category[ \
                                                    enumerations.SECTION_LIST_OBJECT]:
                                                        category[ \
                                                            enumerations. \
                                                            SECTION_LIST_OBJECT] = \
                                                            [section[ \
                                                            enumerations.SECTION_ID], ]
                                                else:
                                                        if not section_name in \
                                                            category[ \
                                                            enumerations. \
                                                            SECTION_LIST_OBJECT]:
                                                                category[enumerations. \
                                                                    SECTION_LIST_OBJECT \
                                                                    ].append(section[ \
                                                                    enumerations. \
                                                                    SECTION_ID])

        def __get_pixbuf_from_path(self, path, icon_name):
                icon = icon_name.replace(' ', '_')

                # Performance: Faster to check if files exist rather than catching
                # exceptions when they do not. Picked up open failures using dtrace
                png_exists = os.path.exists(self.application_dir + path + icon + ".png")
                svg_exists = os.path.exists(self.application_dir + path + icon + ".svg")
                       
                if not png_exists and not svg_exists:
                        return None
                try:
                        return gtk.gdk.pixbuf_new_from_file( \
                            self.application_dir + path + icon + ".png")
                except gobject.GError:
                        try:
                                return gtk.gdk.pixbuf_new_from_file( \
                                    self.application_dir + path + icon + ".svg")
                        except gobject.GError:
                                iconview = gtk.IconView()
                                icon = iconview.render_icon(getattr(gtk, \
                                    "STOCK_MISSING_IMAGE"), \
                                    size = gtk.ICON_SIZE_MENU,
                                    detail = None)
                                # XXX Could return image-we don't want to show ugly icon.
                                return None

        def __progressdialog_progress_pulse(self):
                while not self.progress_stop_timer_thread:
                        gobject.idle_add(self.w_progressbar.pulse)
                        time.sleep(0.1)
                gobject.idle_add(self.w_progress_dialog.hide)
                self.progress_stop_timer_thread = False
                
        # For initial setup before loading package entries allow 5% of progress bar
        # update it on a time base as we have no other way to judge progress at this point
        def __progressdialog_progress_time(self):
                while not self.progress_stop_timer_thread and \
                        self.progress_fraction_time_count <= \
                            INITIAL_PROGRESS_TOTAL_PERCENTAGE:
                                
                        gobject.idle_add(self.w_progressbar.set_fraction, \
                                self.progress_fraction_time_count)
                        self.progress_fraction_time_count += \
                                INITIAL_PROGRESS_TIME_PERCENTAGE
                        time.sleep(INITIAL_PROGRESS_TIME_INTERVAL)
                self.progress_stop_timer_thread = False
                self.progress_fraction_time_count = 0

        def __progressdialog_progress_percent(self, fraction, count, total):
                gobject.idle_add(self.w_progressinfo_label.set_text, self._( \
                    "Processing package entries: %d of %d" % (count, total)  ))
                gobject.idle_add(self.w_progressbar.set_fraction, fraction)

        def __setup_data_finished(self):
                gobject.idle_add(self.w_progress_dialog.hide)
                self.in_setup = False
      
#-----------------------------------------------------------------------------#
# Static Methods
#-----------------------------------------------------------------------------#

        @staticmethod
        def n_(message): 
                return message

        @staticmethod
        def __sort(a, b):
                return cmp(a[1], b[1])

        @staticmethod
        def __installed_fmris_from_args(img, args):
                found = []
                notfound = []
                try:
                        for m in img.inventory(args):
                                found.append(m[0])
                except image.InventoryException, e:
                        notfound = e.notfound

                return notfound
                
        @staticmethod
        def cell_data_function(column, renderer, model, itr, data):
                '''Function which sets the background colour to black if package is 
                selected'''
                if itr:
                        if model.get_value(itr, enumerations.MARK_COLUMN):
                                renderer.set_property("cell-background", "#ffe5cc")
                                renderer.set_property("cell-background-set", True)
                        else:
                                renderer.set_property("cell-background-set", False)

        @staticmethod
        def combobox_separator(model, itr):
                return model.get_value(itr, enumerations.FILTER_NAME) == ""

        @staticmethod
        def combobox_id_separator(model, itr):
                return model.get_value(itr, 0) == -1

        @staticmethod
        def check_if_pkg_have_row_in_model(pkg, p_pkg):
                """Returns True if package is already in model or False if not"""
                if p_pkg:
                        if pkg.is_same_pkg(p_pkg):
                                return True
                        else:
                                return False
                return False

        @staticmethod
        def category_filter(model, itr):
                '''This function filters category in the main application view'''
                return model.get_value(itr, enumerations.CATEGORY_VISIBLE)

        @staticmethod
        def get_datetime(version):
                dt = None
                try:
                        dt = version.get_datetime()
                except AttributeError:
                        dt = version.get_timestamp()
                return dt

        @staticmethod
        def get_installed_version(img, pkg):
                return img.get_version_installed(pkg)

        @staticmethod
        def get_manifest(img, package, filtered = True):
                '''helper function'''
                # XXX Should go to the  -> imageinfo.py
                manifest = None

                # 3087 shutdown time is too long when closing down soon after startup
                if packagemanager.cancelled:
                        return manifest
                try:
                        manifest = img.get_manifest(package, filtered)
                except OSError:
                        # XXX It is possible here that the user doesn't have network con,
                        # XXX proper permissions to save manifest, should we do something 
                        # XXX and popup information dialog?
                        pass
                except (retrieve.ManifestRetrievalError,
                    retrieve.DatastreamRetrievalError, NameError):
                        pass
                return manifest

        @staticmethod
        def update_desc(description, pkg, package):
                p = pkg[enumerations.PACKAGE_OBJECT_COLUMN][0]
                if p == package:
                        pkg[enumerations.DESCRIPTION_COLUMN] = description
                        return

#-----------------------------------------------------------------------------#
# Public Methods
#-----------------------------------------------------------------------------#
        def setup_progressdialog_show(self):
                self.w_progress_dialog.set_title(self._("Loading Repository Information"))
                self.w_progressinfo_label.set_text(
                    self._( "Fetching package entries ..."))
                self.w_progress_cancel.hide()

                Thread(target = self.w_progress_dialog.run).start()
                Thread(target = self.__progressdialog_progress_time).start()
        
        def init_sections(self):
                self.__init_sections()                   #Initiates sections

        def process_package_list_start(self, image_directory):
                self.image_directory = image_directory
                # Create our image object based on image directory.
                image_obj = self.__get_image_obj_from_directory(image_directory)
                self.image_o = image_obj
                
                # Acquire image contents and update progress bar as you do so.
                self.__get_image_from_directory(image_obj,
                        self.__progressdialog_progress_percent)
                while gtk.events_pending():
                        gtk.main_iteration(False)
                        
        def init_package_view(self):
                self.__init_show_filter()                
                self.__setup_data_finished()
                self.__init_tree_views()                 

                self.w_filter_combobox.set_active(0)
                self.w_sections_combobox.set_active(0)
                self.application_list_filter.set_visible_func(self.__application_filter)
                self.__setup_repositories_combobox(self.image_o)

        def get_icon_pixbuf(self, icon_name):
                #2821: The get_icon_pixbuf should use PACKAGE_MANAGER_ROOT
                return self.__get_pixbuf_from_path(self.application_dir + \
                    "/usr/share/icons/package-manager/", icon_name)
                
        def get_manifests_for_packages(self):
                ''' Function, which get's manifest for packages. If the manifest is not
                locally tries to retrieve it. For installed packages gets manifest
                for the particular version (local operation only), if the package is 
                not installed than the newest one'''
                self.description_thread_running = True
                img = self.image_o
                img.history.operation_name = "info"
                for pkg in self.application_list:
                        if self.cancelled:
                                self.description_thread_running = False
                                return
                        info = None
                        img = pkg[enumerations.IMAGE_OBJECT_COLUMN]
                        package = pkg[enumerations.PACKAGE_OBJECT_COLUMN][0]
                        if (img and package):
                                version = img.has_version_installed(package)
                                if version:
                                        version = self.get_installed_version(img, \
                                            package)
                                        man = self.get_manifest(img, version, \
                                            filtered = True)
                                        if man:
                                                info = man.get("description", "")
                                else:
                                        newest = max( \
                                            pkg[enumerations.PACKAGE_OBJECT_COLUMN])
                                        man = self.get_manifest(img, newest, \
                                            filtered = True)
                                        if man:
                                                info = man.get("description", "")
                        # XXX workaround, this should be done nicer
                        gobject.idle_add(self.update_desc, info, pkg, package)
                        time.sleep(0.01)
                img = self.image_o
                img.history.operation_result = history.RESULT_SUCCEEDED
                self.description_thread_running = False
                
        def update_statusbar(self):
                '''Function which updates statusbar'''
                installed = 0
                selected = 0
                broken = 0
                for pkg in self.application_list:
                        if pkg[enumerations.INSTALLED_VERSION_COLUMN]:
                                installed = installed + 1
                        if pkg[enumerations.MARK_COLUMN]:
                                selected = selected + 1
                listed_str = self._('%d packages listed') % len(self.application_list)
                inst_str = self._('%d installed') % installed
                sel_str = self._('%d selected') % selected
                broken_str = self._('%d broken') % broken
                self.w_main_statusbar.push(0, listed_str + ', ' + inst_str + ', ' + \
                    sel_str + ', ' + broken_str + '.')


        def update_package_list(self):
                for row in self.application_list:
                        if row[enumerations.MARK_COLUMN]:
                                img =  row[enumerations.IMAGE_OBJECT_COLUMN]
                                pkg = row[enumerations.PACKAGE_OBJECT_COLUMN][0]
                                package_installed = self.get_installed_version(img, pkg)
                                version_installed = None
                                if package_installed:
                                        version_installed = \
                                            package_installed.version.get_short_version()
                                row[enumerations.MARK_COLUMN] = False
                                row[enumerations.STATUS_ICON_COLUMN] = None
                                row[enumerations.INSTALLED_VERSION_COLUMN] = \
                                    version_installed
                                row[enumerations.INSTALLED_OBJECT_COLUMN] = \
                                    package_installed
                                if not package_installed:
                                        pkg = max(row[enumerations.PACKAGE_OBJECT_COLUMN])
                                        dt = self.get_datetime(pkg.version)
                                        dt_str = (":%02d%02d") % (dt.month, dt.day)
                                        available_version = \
                                            pkg.version.get_short_version() + dt_str
                                        row[enumerations.LATEST_AVAILABLE_COLUMN] = \
                                            available_version
                                else:
                                        row[enumerations.LATEST_AVAILABLE_COLUMN] = None
                self.w_installupdate_button.set_sensitive(False)
                self.w_installupdate_menuitem.set_sensitive(False)
                self.w_remove_button.set_sensitive(False)
                self.w_remove_menuitem.set_sensitive(False)
                self.__enable_disable_selection_menus()
                self.update_statusbar()

        def shutdown_after_ips_update(self):    

                # 2790: As IPS and IPS-GUI have been updated the IPS GUI must be shutdown 
                # and restarted
                msgbox = gtk.MessageDialog(parent = self.w_main_window, \
                    buttons = gtk.BUTTONS_OK, \
                    flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_INFO, \
                    message_format = self._("SUNWipkg and SUNWipkg-gui have been" + \
                    "updated and Package Manager will now be restarted.\n\nAfter" + \
                    "restart select Update All to continue."))
                msgbox.set_title(self._("Update All"))
                msgbox.run()
                msgbox.destroy()
                self.__main_application_quit(restart_app = True)

        def shutdown_after_image_update(self):    

                msgbox = gtk.MessageDialog(parent = self.w_main_window, \
                    buttons = gtk.BUTTONS_OK, \
                    flags = gtk.DIALOG_MODAL, type = gtk.MESSAGE_INFO, \
                    message_format = self._("Update All has completed and Package" + \
                    "Manager will now exit.\n\nPlease review posted release notes" + \
                    "before rebooting:\n\n" + \
                    "   http://opensolaris.org/os/project/indiana/resources/rn3/"))
                msgbox.set_title(self._("Update All"))
                msgbox.run()
                msgbox.destroy()
                self.__main_application_quit()

###############################################################################
#-----------------------------------------------------------------------------#
# Test functions
#-----------------------------------------------------------------------------#
        def fill_with_fake_data(self):
                '''test data for gui'''
                app1 = [False, self.get_icon_pixbuf("locked"), \
                    self.get_icon_pixbuf("None"), "acc", None, None, None, 4, "desc6", \
                    "Object Name1", None, True, None]
                app2 = [False, self.get_icon_pixbuf("update_available"), \
                    self.get_icon_pixbuf(self._('All')), "acc_gam", \
                    "2.3", None, "2.8", \
                    4, "desc7", "Object Name2", None, True, None]
                app3 = [False, self.get_icon_pixbuf("None"), \
                    self.get_icon_pixbuf("Other"), "gam_grap", "2.3", None, None, 4, \
                    "desc8", "Object Name3", None, True, None]
                app4 = [False, self.get_icon_pixbuf("update_locked"), \
                    self.get_icon_pixbuf("Office"), "grap_gam", "2.3", None, "2.8", 4, \
                    "desc9", "Object Name2", None, True, None]
                app5 = [False, self.get_icon_pixbuf("update_available"), \
                    self.get_icon_pixbuf("None"), "grap", "2.3", None, "2.8", 4, \
                    "desc0", "Object Name3", None, True, None]
                itr1 = self.application_list.append(app1)
                itr2 = self.application_list.append(app2)
                itr3 = self.application_list.append(app3)
                itr4 = self.application_list.append(app4)
                itr5 = self.application_list.append(app5)
                #      self.__add_package_to_category(_("All"),None,None,None);
                self.__add_package_to_category(self._("Accessories"), None, None, itr1)
                self.__add_package_to_category(self._("Accessories"), None, None, itr2)
                self.__add_package_to_category(self._("Games"), None, None, itr3)
                self.__add_package_to_category(self._("Graphics"), None, None, itr3)
                self.__add_package_to_category(self._("Games"), None, None, itr2)
                self.__add_package_to_category(self._("Graphics"), None, None, itr4)
                self.__add_package_to_category(self._("Games"), None, None, itr4)
                self.__add_package_to_category(self._("Graphics"), None, None, itr5)

                #     Category names until xdg is imported.
                #     from xdg.DesktopEntry import *
                #     entry = DesktopEntry ()
                #     directory = '/usr/share/desktop-directories'
                #     for root, dirs, files in os.walk (directory):
                #       for name in files:
                #       entry.parse (os.path.join (root, name))
                #       self.__add_category_to_section (entry.getName (), \
                #   self._('Applications Desktop'))

                self.__add_category_to_section(self._("Accessories"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Games"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Graphics"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Internet"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Office"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Sound & Video"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("System Tools"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Universal Access"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Developer Tools"), \
                    self._('Applications Desktop'))
                self.__add_category_to_section(self._("Core"), self._('Operating System'))
                self.__add_category_to_section(self._("Graphics"), \
                    self._('Operating System'))
                self.__add_category_to_section(self._("Media"), \
                    self._('Operating System'))
                #Can be twice :)
                self.__add_category_to_section(self._("Developer Tools"), \
                    self._('Operating System'))
                self.__add_category_to_section(self._("Office"), "Progs")
                self.__add_category_to_section(self._("Office2"), "Progs")
                self.__setup_repositories_combobox(self.image_o)
                self.in_setup = False

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main():
        gtk.main()
        return 0

if __name__ == '__main__':
        packagemanager = PackageManager()
        passed_test_arg = False
        passed_imagedir_arg = False
        packagemanager.provided_image_dir = True

        try:
                opts, args = getopt.getopt(sys.argv[1:], "htR:", \
                    ["help", "test-gui", "image-dir="])
        except getopt.error, msg:
                print "%s, for help use --help" % msg
                sys.exit(2)

        cmd = os.path.join(os.getcwd(), sys.argv[0])
        cmd = os.path.realpath(cmd)
        packagemanager.application_path = cmd

        for option, argument in opts:
                if option in ("-h", "--help"):
                        print """\
Use -R (--image-dir) to specify image directory.
Use -t (--test-gui) to work on fake data."""
                        sys.exit(0)
                if option in ("-t", "--test-gui"):
                        passed_test_arg = True
                if option in ("-R", "--image-dir"):
                        packagemanager.image_dir_arg = argument
                        image_dir = argument
                        passed_imagedir_arg = True

        if passed_test_arg and passed_imagedir_arg:
                print "Options -R and -t can not be used together."
                sys.exit(2)
        if not passed_imagedir_arg:
                try:
                        image_dir = os.environ["PKG_IMAGE"]
                except KeyError:
                        image_dir = os.getcwd()
                        packagemanager.provided_image_dir = False

        if not passed_test_arg:
                packagemanager.setup_progressdialog_show()
                packagemanager.init_sections()
                packagemanager.process_package_list_start(image_dir)
        else:
                packagemanager.init_sections()
                packagemanager.fill_with_fake_data()

        packagemanager.init_package_view()        
        packagemanager.update_statusbar()
        while gtk.events_pending():
                gtk.main_iteration(False)
        
        # Performance: Start this background thread after progress dialog thread has 
        # completed in init_package_view()->self.__setup_data_finished() or GUI will block
        if not passed_test_arg:
                Thread(target = packagemanager.get_manifests_for_packages,
                        args = ()).start()
        main()
