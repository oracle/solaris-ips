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

import getopt
import os
import sys
import time
import pango
import locale
import gettext
from threading import Thread
try:
        import pygtk
        pygtk.require("2.0")
except:
        pass
try:
        import gobject
        gobject.threads_init()
        import gtk
        import gtk.glade
except:
        sys.exit(1)
import pkg.catalog as catalog
import pkg.client.image as image
import pkg.client.progress as progress
import pkg.client.filelist as filelist
import pkg.gui.imageinfo as imageinfo
import pkg.gui.installupdate as installupdate
import pkg.gui.remove as remove
import pkg.gui.enumerations as enumerations
import pkg.gui.userrights as userrights

class PackageManager:
        def __init__(self):
                pass

        def N_(self, message): 
                return message

        def create_widgets_and_show_gui(self):
                '''This method prepares all widgets and runs empty GUI'''
                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                locale.setlocale(locale.LC_ALL, '')
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("packagemanager", self.application_dir + "/usr/share/locale")
                        module.textdomain("packagemanager")
                self._ = gettext.gettext
                main_window_title = self._('Package Manager - revision 0.1')
                rights = userrights.UserRights()
                self.user_rights = rights.check_administrative_rights()
                self.cancelled = False                   # For background processes
                self.preparing_list = True               #
                self.description_thread_running = False # For background processes
                self.pkginfo_thread = None              # For background processes
                gtk.rc_parse('~/.gtkrc-1.2-gnome2')     # Load gtk theme
                self.gladefile = self.application_dir + \
                    "/usr/share/package-manager/packagemanager.glade"
                self.wTree = gtk.glade.XML(self.gladefile, "mainwindow")
                self.application_list = None            #List for applications/main view
                self.category_list = None               #List for categories
                self.section_list = None                #List for sections
                self.clipboard_text = None
                self.create_models_lists()              #Creates gtk.ListStore for models
                self.pr = progress.NullProgressTracker()
                self.create_available_widgets()         #Get widgets from glade file
                self.update_reload_button()
                self.clipboard.request_text(self.clipboard_text_received)
                self.mainwindow.set_title(main_window_title)
                try:
                        dic = self.declare_signals()
                        self.wTree.signal_autoconnect(dic)
                except AttributeError, error:
                        print self._('GUI will not respond to any event! %s.Check declare_signals()')\
                            % error
                self.init_tree_views()                 #Connects treeviews with models
                self.init_sections()                   #Initiates sections
                self.init_show_filter()                #Initiates filter sections
                self.mainwindow.show_all()

        def create_available_widgets(self):
                '''Create available widgets'''
                #Widnows
                self.mainwindow = self.wTree.get_widget("mainwindow")
                self.downloadingfiles = self.wTree.get_widget("downloadingfiles")
                self.applyingchanges = self.wTree.get_widget("applyingchanges")
                self.downloadpreferences1 = self.wTree.get_widget("downloadpreferences1")
                self.downloadingpackageinformation = \
                    self.wTree.get_widget("downloadingpackageinformation")
                self.managerepositories = self.wTree.get_widget("managerepositories")
                #Treeviews
                self.applicationtreeview = self.wTree.get_widget("applicationtreeview")
                self.categoriestreeview = self.wTree.get_widget("categoriestreeview")
                #Textviews
                self.generalinfotextview = self.wTree.get_widget("generalinfotextview")
                self.installedfilestextview = self.wTree.get_widget("installedfilestextview")
                self.dependenciestextview = self.wTree.get_widget("dependenciestextview")
                #Labels
                self.packagenamelabel = self.wTree.get_widget("packagenamelabel")
                self.shortdescriptionlabel = \
                    self.wTree.get_widget("shortdescriptionlabel")
                #Search dialog
                self.searchentrydialog = self.wTree.get_widget("searchentry")
                #Buttons
                self.install_update_button = self.wTree.get_widget("install_update_button")
                self.remove_button = self.wTree.get_widget("remove_button")
                self.update_all_button = self.wTree.get_widget("update_all_button")
                self.reload_button = self.wTree.get_widget("reloadbutton")
                #Other
                self.repositorycombobox = self.wTree.get_widget("repositorycombobox")
                self.sectionscombobox = self.wTree.get_widget("sectionscombobox")
                self.filtercombobox = self.wTree.get_widget("filtercombobox")
                self.packageimage = self.wTree.get_widget("packageimage")
                self.statusbar = self.wTree.get_widget("statusbar")
                #Menu
                self.install_update_menu = self.wTree.get_widget("package_install_update")
                self.remove_menu = self.wTree.get_widget("package_remove")
                self.update_all_menu = self.wTree.get_widget("package_update_all")
                self.cut_menu = self.wTree.get_widget("edit_cut")
                self.copy_menu = self.wTree.get_widget("edit_copy")
                self.paste_menu = self.wTree.get_widget("edit_paste")
                self.clear_menu = self.wTree.get_widget("edit_clear")
                self.select_all_menu = self.wTree.get_widget("edit_select_all")
                self.select_updates_menu = self.wTree.get_widget("edit_select_updates")
                self.deselect_menu = self.wTree.get_widget("edit_deselect")
                #Clipboard
                self.clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)

        def clipboard_text_received(self, clipboard, text, data):
                self.clipboard_text = text
                return

        def init_tree_views(self):
                '''This function connects treeviews with their models and also applies
                filters'''
                # XXX 1 Do we need to clear treeviews before appending columns?
                # XXX 2 Do we need to have hidden columns with not shown information
                # XXX 2 like objects, other lists or we can get those information from
                # XXX 2 lists rather than models???
                # XXX 3 Make sure that not only name is sortable, other columns should be
                # XXX 3 as well. Please refer to wireframes
                # XXX 4 check if there should be some padding between columns or the names
                # XXX 4 should have " name " instead of "name"
                # XXX 5 compare with ipsgui what should be added, like row activated??
                ##APPLICATION MAIN TREEVIEW
                self.application_list_filter = self.application_list.filter_new()
                self.application_list_sort = \
                    gtk.TreeModelSort(self.application_list_filter)
                self.applicationtreeview.set_model(self.application_list_sort)
                model = self.applicationtreeview.get_model()
                toggle_renderer = gtk.CellRendererToggle()
                toggle_renderer.connect('toggled', self.active_pane_toggle, model)
                column = gtk.TreeViewColumn("", toggle_renderer, active = enumerations.MARK_COLUMN)
                column.set_sort_column_id(enumerations.MARK_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(toggle_renderer, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                column = gtk.TreeViewColumn()
                column.set_title("")
                #Commented, since there was funny jumping of the icons
                #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = False)
                column.add_attribute(render_pixbuf, "pixbuf", enumerations.STATUS_ICON_COLUMN)
                column.set_fixed_width(32)
                column.set_cell_data_func(render_pixbuf, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                column = gtk.TreeViewColumn()
                column.set_title("")
                #Commented, since there was funny jumping of the icons
                #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = False)
                column.add_attribute(render_pixbuf, "pixbuf", enumerations.ICON_COLUMN)
                column.set_fixed_width(32)
                column.set_cell_data_func(render_pixbuf, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._("Name"), name_renderer, \
                    text = enumerations.NAME_COLUMN)
                column.set_sort_column_id(enumerations.NAME_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(name_renderer, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                installed_version_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Installed Version'), \
                    installed_version_renderer, text = enumerations.INSTALLED_VERSION_COLUMN)
                column.set_cell_data_func(installed_version_renderer, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                latest_available_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Latest Version'), \
                    latest_available_renderer, text = enumerations.LATEST_AVAILABLE_COLUMN)
                column.set_cell_data_func(latest_available_renderer, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                rating_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Rating'), rating_renderer, text = enumerations.RATING_COLUMN)
                column.set_cell_data_func(rating_renderer, self.cell_data_function, None)
                description_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Description'), description_renderer, \
                    text = enumerations.DESCRIPTION_COLUMN)
                column.set_cell_data_func(description_renderer, self.cell_data_function, None)
                self.applicationtreeview.append_column(column)
                #Added selection listener
                self.package_selection = self.applicationtreeview.get_selection()
                self.package_selection.set_mode(gtk.SELECTION_SINGLE)
                self.package_selection.connect("changed", self.on_package_selection_changed,
                    None)
                ##CATEGORIES TREEVIEW
                #enumerations.CATEGORY_NAME
                self.category_list_filter = self.category_list.filter_new()
                self.category_list_filter.set_visible_func(self.category_filter)
                self.categoriestreeview.set_model(self.category_list_filter)
                enumerations.CATEGORY_NAME_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(self._('Name'), enumerations.CATEGORY_NAME_renderer, \
                    text = enumerations.CATEGORY_NAME)
                self.categoriestreeview.append_column(column)
                #Added selection listener
                self.category_selection = self.categoriestreeview.get_selection()
                self.category_selection.set_mode(gtk.SELECTION_SINGLE)
                self.category_selection.connect("changed", self.on_category_selection_changed,
                    None)
                ##SECTION COMBOBOX
                #enumerations.SECTION_NAME
                self.sectionscombobox.set_model(self.section_list)
                cell = gtk.CellRendererText()
                self.sectionscombobox.pack_start(cell, True)
                self.sectionscombobox.add_attribute(cell, 'text', enumerations.SECTION_NAME)
                self.sectionscombobox.set_row_separator_func(self.combobox_separator)
                ##FILTER COMBOBOX
                #enumerations.FILTER_NAME
                self.filtercombobox.set_model(self.filter_list)
                cell = gtk.CellRendererText()
                self.filtercombobox.pack_start(cell, True)
                self.filtercombobox.add_attribute(cell, 'text', enumerations.FILTER_NAME)
                self.filtercombobox.set_row_separator_func(self.combobox_separator)
                ##FILTER COMBOBOX
                #enumerations.FILTER_NAME
                self.repositorycombobox.set_model(self.repositories_list)
                cell = gtk.CellRendererText()
                self.repositorycombobox.pack_start(cell, True)
                self.repositorycombobox.add_attribute(cell, 'text', enumerations.REPOSITORY_NAME)
                self.repositorycombobox.set_row_separator_func(self.combobox_separator)

        def on_mainwindow_delete_event(self, widget, event):
                ''' handler for delete event of the main window '''
                if self.check_if_something_was_changed() == True:
                        # XXX Change this to not quit and show dialog
                        # XXX if some changes were applied:
                        self.main_application_quit()
                        return True
                else:
                        self.main_application_quit()

        def download_pref_close_clicked(self, widget):
                self.downloadpreferences.destroy()

        def on_file_quit_activate(self, widget):
                ''' handler for quit menu event '''
                self.on_mainwindow_delete_event(None,None)

        def downloadpreferences_delete_event(self, widget, event):
                self.downloadpreferences.destroy()

        def on_settings_download_preferences_activate(self, widget):
                ''' handler for quit menu event '''
                wTree = gtk.glade.XML(self.gladefile, "downloadpreferences")
                self.downloadpreferences = wTree.get_widget("downloadpreferences")
                self.arch = wTree.get_widget("arch_1")
                self.debug = wTree.get_widget("debug_1")
                self.arch_2 = wTree.get_widget("arch_2")
                self.debug_2 = wTree.get_widget("debug_2")
                self.download_pref_reset_clicked(None)
                dic = \
                    {
                        #downloadpreferences signals  
                        "download_pref_close_clicked":\
                            self.download_pref_close_clicked,
                        "downloadpreferences_delete_event":\
                            self.downloadpreferences_delete_event,
                        "download_pref_reset_clicked":\
                            self.download_pref_reset_clicked,
                    }
                wTree.signal_autoconnect(dic)
                self.downloadpreferences.run()

        def download_pref_reset_clicked(self, widget):
                # XXX Not for rev 1
                return

        def main_application_quit(self):
                '''quits the main gtk loop'''
                self.cancelled = True
                gtk.main_quit()
                sys.exit(0)
                return True

        def check_if_something_was_changed(self):
                ''' Returns True if any of the check boxes for package was changed, false
                if not'''
                for pkg in self.application_list:
                        if pkg[enumerations.MARK_COLUMN] == True:
                                return True
                return False

        def cell_data_function(self, column, renderer, model, iter, data):
                '''Function which sets the background colour to black if package is 
                selected'''
                if iter:
                        if model.get_value(iter, enumerations.MARK_COLUMN):
                                renderer.set_property("cell-background", "#ffe5cc")
                                renderer.set_property("cell-background-set", True)
                        else:
                                renderer.set_property("cell-background-set", False)

        def combobox_separator(self, model, iter):
                return model.get_value(iter, enumerations.FILTER_NAME) == "" 

        def set_visible_packages_from_category(self, category):
                '''Sets all packages as visible from category'''
                if not category:
                        return
                pkglist = category[PACKAGE_LIST_OBJECT];
                if pkglist:
                        for pkg in pkglist:
                                pkg[enumerations.IS_VISIBLE_COLUMN] = True

        def init_sections(self):
                '''This function is for initializing sections combo box, also adds "All"
                Category. It sets active section combobox entry "All"'''
                self.section_list.append([self._('All'), ])
                self.section_list.append(["", ])
                self.section_list.append([self._('Meta Packages'), ])
                self.section_list.append([self._('Applications Desktop'), ])
                self.section_list.append([self._('Applications Web-Based'), ])
                self.section_list.append([self._('Operating System'), ])
                self.section_list.append([self._('User Environment'), ])
                self.section_list.append([self._('Web Infrastructure'), ])
                self.category_list.append([self._('All'), None, None, True, None])
                self.sectionscombobox.set_active(0)

        def init_show_filter(self):
                self.filter_list.append([self._('All Packages'), ])
                self.filter_list.append(["", ])
                self.filter_list.append([self._('Installed Packages'), ])
                self.filter_list.append([self._('Updates'), ])
                self.filter_list.append([self._('Non-installed Packages'), ])
                self.filter_list.append(["", ])
                # self.filter_list.append([self._('Locked Packages'), ])
                # self.filter_list.append(["", ])
                self.filter_list.append([self._('Selected Packages'), ])
                self.filtercombobox.set_active(0)

        def setup_repositories_combobox(self, image):
                repositories = image.catalogs
                default_authority = image.get_default_authority()
                self.repositories_list.clear()
                i = 0
                active = 0
                for repo in repositories:
                        if cmp(repo, default_authority) == 0:
                                active = i
                        i = i + 1
                        self.repositories_list.append([repo, ])
                if default_authority:
                        self.repositorycombobox.set_active(active)
                else:
                        self.repositorycombobox.set_active(0)

        def active_pane_toggle(self, cell, path, model_sort):
                '''Toggle function for column enumerations.MARK_COLUMN'''
                applicationModel = model_sort.get_model()
                applicationPath = model_sort.convert_path_to_child_path(path)
                filterModel = applicationModel.get_model()
                child_path = applicationModel.convert_path_to_child_path(applicationPath)
                iter = filterModel.get_iter(child_path)
                if iter:
                        modified = filterModel.get_value(iter, enumerations.MARK_COLUMN)
                        filterModel.set_value(iter, enumerations.MARK_COLUMN, not modified)
                        latest_available = filterModel.get_value(iter, enumerations.LATEST_AVAILABLE_COLUMN)
                        installed_available = filterModel.get_value(iter, enumerations.INSTALLED_VERSION_COLUMN)
                        self.update_statusbar()
                        self.update_install_update_button(latest_available, modified)
                        self.update_remove_button(installed_available, modified)
                        self.enable_disable_selection_menus()

        def update_install_update_button(self, latest_available, toggle_true):
                if not toggle_true and self.user_rights:
                        if latest_available:
                                self.install_update_button.set_sensitive(True)
                                self.install_update_menu.set_sensitive(True)
                else:
                        available = None
                        for row in self.application_list:
                                if row[enumerations.MARK_COLUMN]:
                                        available = row[enumerations.LATEST_AVAILABLE_COLUMN]
                                        if available:
                                                return
                        if not available:
                                self.install_update_button.set_sensitive(False)
                                self.install_update_menu.set_sensitive(False)

        def update_reload_button(self):
                if self.user_rights:
                        self.reload_button.set_sensitive(True)
                else:
                        self.reload_button.set_sensitive(False)

        def update_remove_button(self, installed_available, toggle_true):
                if not toggle_true and self.user_rights:
                        if installed_available:
                                self.remove_button.set_sensitive(True)
                                self.remove_menu.set_sensitive(True)
                else:
                        available = None
                        for row in self.application_list:
                                if row[enumerations.MARK_COLUMN]:
                                        installed = row[enumerations.INSTALLED_VERSION_COLUMN]
                                        if installed:
                                                return
                        if not available:
                                self.remove_button.set_sensitive(False)
                                self.remove_menu.set_sensitive(False)

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
                self.statusbar.push(0, listed_str + ', ' + inst_str + ', ' + sel_str + \
                    ', ' + broken_str + '.')

        def update_package_list(self):
                for row in self.application_list:
                        if row[enumerations.MARK_COLUMN]:
                                image =  row[enumerations.IMAGE_OBJECT_COLUMN]
                                pkg = max(row[enumerations.PACKAGE_OBJECT_COLUMN])
                                package_installed = self.get_installed_version(image, pkg)
                                version_installed = None
                                if package_installed:
                                        version_installed = package_installed.version.get_short_version()
                                row[enumerations.MARK_COLUMN] = False
                                row[enumerations.STATUS_ICON_COLUMN] = None
                                row[enumerations.INSTALLED_VERSION_COLUMN] = version_installed
                                row[enumerations.INSTALLED_OBJECT_COLUMN] = package_installed
                                if not package_installed:
                                        dt = self.get_datetime(pkg.version)
                                        dt_str = (":%02d%02d") % (dt.month, dt.day)
                                        available_version = pkg.version.get_short_version() + dt_str
                                        row[enumerations.LATEST_AVAILABLE_COLUMN] = available_version
                                else:
                                        row[enumerations.LATEST_AVAILABLE_COLUMN] = None
                self.install_update_button.set_sensitive(False)
                self.install_update_menu.set_sensitive(False)
                self.remove_button.set_sensitive(False)
                self.remove_menu.set_sensitive(False)
                self.enable_disable_selection_menus()
                self.update_statusbar()

        def get_datetime(self, version):
                dt = None
                try:
                        dt = version.get_datetime()
                except AttributeError:
                        dt = version.get_timestamp()
                return dt

        def on_searchentry_changed(self, widget):
                '''On text search field changed we should refilter the main view'''
                Thread(target = self.on_searchentry_threaded, args = ()).start()

        def on_searchentry_threaded(self):
                gobject.idle_add(self.application_list_filter.refilter)
                gobject.idle_add(self.enable_disable_selection_menus)

        def on_edit_paste(self, widget):
                self.searchentrydialog.insert_text(self.clipboard_text, self.searchentrydialog.get_position())

        def on_clear_paste(self, widget):
                bounds = self.searchentrydialog.get_selection_bounds()
                text = self.searchentrydialog.get_chars(bounds[0], bounds[1])
                self.searchentrydialog.delete_text(bounds[0], bounds[1])
                return

        def on_copy(self, widget):
                bounds = self.searchentrydialog.get_selection_bounds()
                text = self.searchentrydialog.get_chars(bounds[0], bounds[1])
                self.clipboard.set_text(text)
                return

        def on_cut(self, widget):
                bounds = self.searchentrydialog.get_selection_bounds()
                text = self.searchentrydialog.get_chars(bounds[0], bounds[1])
                self.searchentrydialog.delete_text(bounds[0], bounds[1])
                self.clipboard.set_text(text)
                return

        def on_select_all(self, widget):
                sort_filt_model = self.applicationtreeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                iter_next = sort_filt_model.get_iter_first()
                list_of_paths = []
                while iter_next != None:
                        sorted_path = sort_filt_model.get_path(iter_next)
                        filtered_path = sort_filt_model.convert_path_to_child_path(sorted_path)
                        path = filt_model.convert_path_to_child_path(filtered_path)
                        list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        iter = model.get_iter(path)
                        model.set_value(iter, enumerations.MARK_COLUMN, True)
                self.enable_disable_selection_menus()
                self.update_statusbar()
                self.enable_disable_install_update()
                self.enable_disable_remove()

        def on_select_updates(self, widget):
                sort_filt_model = self.applicationtreeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                iter_next = sort_filt_model.get_iter_first()
                list_of_paths = []
                while iter_next != None:
                        sorted_path = sort_filt_model.get_path(iter_next)
                        filtered_iter = sort_filt_model.convert_iter_to_child_iter(None, iter_next)
                        app_iter = filt_model.convert_iter_to_child_iter(filtered_iter)

                        filtered_path = sort_filt_model.convert_path_to_child_path(sorted_path)
                        path = filt_model.convert_path_to_child_path(filtered_path)
                        if model.get_value(app_iter, enumerations.INSTALLED_VERSION_COLUMN):
                                if  model.get_value(app_iter, enumerations.LATEST_AVAILABLE_COLUMN):
                                        list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        iter = model.get_iter(path)
                        model.set_value(iter, enumerations.MARK_COLUMN, True) 
                self.enable_disable_selection_menus()
                self.update_statusbar()
                self.enable_disable_install_update()
                self.enable_disable_remove()

        def on_deselect(self, widget):
                sort_filt_model = self.applicationtreeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                iter_next = sort_filt_model.get_iter_first()
                list_of_paths = []
                while iter_next != None:
                        sorted_path = sort_filt_model.get_path(iter_next)
                        filtered_iter = sort_filt_model.convert_iter_to_child_iter(None, iter_next)
                        app_iter = filt_model.convert_iter_to_child_iter(filtered_iter)
                        filtered_path = sort_filt_model.convert_path_to_child_path(sorted_path)
                        path = filt_model.convert_path_to_child_path(filtered_path)
                        if model.get_value(app_iter, enumerations.MARK_COLUMN):
                                list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        iter = model.get_iter(path)
                        model.set_value(iter, enumerations.MARK_COLUMN, False)
                self.enable_disable_selection_menus()
                self.update_statusbar()
                self.enable_disable_install_update()
                self.enable_disable_remove()

        def on_searchentry_focus_in(self, widget, event):
                self.paste_menu.set_sensitive(True)

        def on_searchentry_focus_out(self, widget, event):
                self.paste_menu.set_sensitive(False)

        def on_searchentry_event(self, widget, event):
                self.clipboard.request_text(self.clipboard_text_received)
                if widget.get_selection_bounds():
                        #enable selection functions
                        self.cut_menu.set_sensitive(True)
                        self.copy_menu.set_sensitive(True)
                        self.clear_menu.set_sensitive(True)
                else:
                        self.cut_menu.set_sensitive(False)
                        self.copy_menu.set_sensitive(False)
                        self.clear_menu.set_sensitive(False)

        def on_category_selection_changed(self, selection, widget):
                '''This function is for handling category selection changes'''
                self.application_list_filter.refilter()
                self.enable_disable_selection_menus()

        def on_package_selection_changed(self, selection, widget):
                '''This function is for handling package selection changes'''
                model, iter = selection.get_selected()
                if iter:
                        image = model.get_value(iter, enumerations.IMAGE_OBJECT_COLUMN)
                        pkg = model.get_value(iter, enumerations.INSTALLED_OBJECT_COLUMN)
                        if not pkg:
                                packages = model.get_value(iter, enumerations.PACKAGE_OBJECT_COLUMN)
                                pkg = max(packages)
                        self.pkginfo_thread = pkg
                        Thread(target = self.show_package_info, args = (model, iter)).start()

        def show_package_info(self, model, iter):
                image = model.get_value(iter, enumerations.IMAGE_OBJECT_COLUMN)
                pkg = model.get_value(iter, enumerations.INSTALLED_OBJECT_COLUMN)
                icon = model.get_value(iter, enumerations.INSTALLED_OBJECT_COLUMN)
                if not pkg:
                        packages = model.get_value(iter, enumerations.PACKAGE_OBJECT_COLUMN)
                        pkg = max(packages)
                        gobject.idle_add(self.update_package_info, pkg, icon, False, None)
                else:
                        gobject.idle_add(self.update_package_info, pkg, icon, True, None)
                man = None
                try:
                        man = image.get_manifest(pkg, filtered = True)
                except:
                        man = "NotAvailable"
                if cmp(self.pkginfo_thread, pkg) == 0:
                        if not pkg:
                                gobject.idle_add(self.update_package_info, pkg, icon, False, man)
                        else:
                                gobject.idle_add(self.update_package_info, pkg, icon, True, man)
                else:
                        return

        # This function is ported from pkg.actions.generic.distinguished_name()
        def locale_distinguished_name(self,action):
                if action.key_attr == None:
                        return str(action)
                return "%s: %s" % \
                    (self._(action.name), action.attrs.get(action.key_attr, "???"))

        def update_package_info(self, pkg, icon, installed, manifest):
                if icon and icon != pkg:
                        self.packageimage.set_from_pixbuf(icon)
                else:
                        self.packageimage.set_from_icon_name("None", 4)
                self.packagenamelabel.set_markup("<b>" + pkg.get_name() + "</b>")
                instbuffer = self.installedfilestextview.get_buffer()
                depbuffer = self.dependenciestextview.get_buffer()
                infobuffer = self.generalinfotextview.get_buffer()
                if not manifest:
                        self.shortdescriptionlabel.set_text(self._("Fetching description..."))
                        instbuffer.set_text(self._("Fetching information..."))
                        depbuffer.set_text(self._("Fetching information..."))
                        infobuffer.set_text(self._("Fetching information..."))
                        return
                if manifest == "NotAvailable":
                        self.shortdescriptionlabel.set_text(self._("Description not available for this package..."))
                        instbuffer.set_text(self._("Files Details not available for this package..."))
                        depbuffer.set_text(self._("Dependencies info not available for this package..."))
                        infobuffer.set_text(self._("Information not available for this package..."))
                        return
                self.shortdescriptionlabel.set_text(manifest.get("description", ""))
                instbuffer.set_text(self._("Root: %s\n") % manifest.img.get_root())
                depbuffer.set_text(self._("Dependencies:\n"))
                if installed:
                        infobuffer.set_text(self._("Information for installed package:\n\n"))
                else:
                        infobuffer.set_text(self._("Information for latest available package:\n\n"))
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
                        if cmp(a.name,self.N_("depend")) == 0:
                                #Remove "depend: " -> [8:]
                                depbuffer.insert(depiter,"\t"+self.locale_distinguished_name(a)[8:]+"\n")
                        elif cmp(a.name,self.N_("dir")) == 0:
                                instbuffer.insert(institer,"\t"+self.locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.N_("file")) == 0:
                                instbuffer.insert(institer,"\t"+self.locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.N_("hardlink")) == 0:
                                instbuffer.insert(institer,"\t"+self.locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.N_("link")) == 0:
                                instbuffer.insert(institer,"\t"+self.locale_distinguished_name(a)+"\n")
                        elif cmp(a.name,self.N_("legacy")) == 0:
                                if cmp(a.attrlist(self.N_("pkg"))[0],pkg.get_name()) == 0:
                                        desc = a.attrlist(self.N_("desc"))
                                        infobuffer.insert(infoiter,self._("  Description:\t%s\n") % desc[0])
                                        pass
                        else:
                                pass
                infobuffer.insert(infoiter, self._("  Name:\t\t%s\n") % pkg.get_name())
                infobuffer.insert(infoiter, self._("  FMRI:\t\t%s\n") % pkg.get_fmri())
                infobuffer.insert(infoiter, self._("  Version:\t\t%s\n") % pkg.version.get_short_version())
                infobuffer.insert(infoiter, self._("  Packaged:\t%s\n") % self.get_datetime(pkg.version))

        def on_filtercombobox_changed(self, widget):
                '''On filter combobox changed'''
                self.application_list_filter.refilter()
                self.enable_disable_selection_menus()

        def on_sectionscombobox_changed(self, widget):
                '''On section combobox changed'''
                selected_section = widget.get_active_text()
                if selected_section == self._('All'):
                        for category in self.category_list:
                                category[enumerations.CATEGORY_VISIBLE] = True
                else:
                        for category in self.category_list:
                                if category[enumerations.CATEGORY_NAME] == self._('All'):
                                        category[enumerations.CATEGORY_VISIBLE] = True
                                else:
                                        category_list = category[enumerations.SECTION_LIST_OBJECT]
                                        if not category_list:
                                                category[enumerations.CATEGORY_VISIBLE] = False
                                        else:
                                                for section in category_list:
                                                        if section == selected_section:
                                                                category[enumerations.CATEGORY_VISIBLE] = True
                                                        else:
                                                                category[enumerations.CATEGORY_VISIBLE] = False
                self.category_list_filter.refilter()
                self.application_list_filter.refilter()
                self.enable_disable_selection_menus()

        def on_repositorycombobox_changed(self, widget):
                '''On repository combobox changed'''
                self.application_list_filter.refilter()
                self.enable_disable_selection_menus()

        def category_filter(self, model, iter):
                '''This function filters category in the main application view'''
                return model.get_value(iter, enumerations.CATEGORY_VISIBLE)

        def is_package_filtered(self, model, iter):
                '''Function for filtercombobox'''
                # XXX Instead of string comparison, we should do it through integers.
                # XXX It should be faster and better for localisations.
                filter_text = self.filtercombobox.get_active_text()
                if filter_text == self._('All Packages'):
                        return True
                elif filter_text == self._('Installed Packages'):
                        return model.get_value(iter, enumerations.INSTALLED_VERSION_COLUMN) != None
                elif filter_text == self._('Non-installed Packages'):
                        return not model.get_value(iter, enumerations.INSTALLED_VERSION_COLUMN) != None
                elif filter_text == self._('Updates'):
                        return (model.get_value(iter, enumerations.INSTALLED_VERSION_COLUMN) != None) & \
                            (model.get_value(iter, enumerations.LATEST_AVAILABLE_COLUMN) != None)
                elif filter_text == self._('Locked Packages'):
                        # XXX Locked support
                        return False
                elif filter_text == self._('Selected Packages'):
                        return model.get_value(iter, enumerations.MARK_COLUMN)

        def application_filter(self, model, iter):
                '''This function is used to filter content in the main application view'''
                if self.preparing_list:
                        return False
                # XXX Show filter, chenge text to integers 
                selection = self.categoriestreeview.get_selection()
                show_filter = None
                category_model, category_iter = selection.get_selected()
                if not category_iter:         #no category was selected, so select "All"
                        selection.select_path(0)
                        category_model, category_iter = selection.get_selected()
                if category_iter:
                        selected_category = category_model.get_value(category_iter, enumerations.CATEGORY_NAME)
                category_list_iter = model.get_value(iter, enumerations.CATEGORY_LIST_OBJECT)
                category = False
                repository = self.is_pkg_repository_visible(model, iter)
                if category_list_iter:
                        sel = False
                        for category_iter in category_list_iter:
                                if category != True:
                                        category = self.category_filter(self.category_list, category_iter)
                                if selected_category != self._('All'):
                                        if selected_category == self.category_list.get_value(category_iter, enumerations.CATEGORY_NAME):
                                                sel = True
                                        category = sel
                else:
                        if selected_category == self._('All'):
                                selected_section = self.sectionscombobox.get_active_text()
                                if selected_section == self._('All'):
                                        category = True
                if (model.get_value(iter, enumerations.IS_VISIBLE_COLUMN) == False):
                        return False
                if self.searchentrydialog.get_text() == "":
                        return (repository & category & self.is_package_filtered(model, iter))
                if not model.get_value(iter, enumerations.NAME_COLUMN) == None:
                        if self.searchentrydialog.get_text().lower() in model.get_value\
                            (iter, enumerations.NAME_COLUMN).lower():
                                return (repository & category & self.is_package_filtered(model, iter))
                if not model.get_value(iter, enumerations.DESCRIPTION_COLUMN) == None:
                        if self.searchentrydialog.get_text().lower() in model.get_value\
                            (iter, enumerations.DESCRIPTION_COLUMN).lower():
                                return (repository & category & self.is_package_filtered(model, iter))
                else:
                        return False

        def is_pkg_repository_visible(self, model, iter):
                if len(self.repositories_list) <= 1:
                        return True
                else:
                        auth_iter = self.repositorycombobox.get_active_iter()
                        authority = self.repositories_list.get_value(auth_iter, enumerations.REPOSITORY_NAME)
                        packages = model.get_value(iter, enumerations.PACKAGE_OBJECT_COLUMN)
                        if not packages:
                                return False
                        pkg = max(packages)
                        if cmp(pkg.get_authority(), authority) == 0:
                                return True
                        else:
                                return False

        def create_models_lists(self):
                '''Creates gtk.ListStore lists for application and category models'''
                self.application_list = \
                    gtk.ListStore(
                        gobject.TYPE_BOOLEAN,      # enumerations.MARK_COLUMN
                        gtk.gdk.Pixbuf,            # enumerations.STATUS_ICON_COLUMN
                        gtk.gdk.Pixbuf,            # enumerations.ICON_COLUMN
                        gobject.TYPE_STRING,       # enumerations.NAME_COLUMN
                        gobject.TYPE_STRING,       # enumerations.INSTALLED_VERSION_COLUMN
                        gobject.TYPE_PYOBJECT,     # enumerations.INSTALLED_OBJECT_COLUMN
                        gobject.TYPE_STRING,       # enumerations.LATEST_AVAILABLE_COLUMN
                        gobject.TYPE_INT,          # enumerations.RATING_COLUMN
                        gobject.TYPE_STRING,       # enumerations.DESCRIPTION_COLUMN
                        gobject.TYPE_PYOBJECT,     # enumerations.PACKAGE_OBJECT_COLUMN
                        gobject.TYPE_PYOBJECT,     # enumerations.IMAGE_OBJECT_COLUMN
                        gobject.TYPE_BOOLEAN,      # enumerations.IS_VISIBLE_COLUMN
                        gobject.TYPE_PYOBJECT      # enumerations.CATEGORY_LIST_OBJECT
                        )
                self.category_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,       # enumerations.CATEGORY_NAME
                        gobject.TYPE_STRING,       # enumerations.CATEGORY_DESCRIPTION
                        gtk.gdk.Pixbuf,            # enumerations.CATEGORY_ICON
                        gobject.TYPE_BOOLEAN,      # enumerations.CATEGORY_VISIBLE
                        gobject.TYPE_PYOBJECT,     # enumerations.SECTION_LIST_OBJECT
                        )
                self.section_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,       # enumerations.SECTION_NAME
                        )
                self.filter_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,       # enumerations.FILTER_NAME
                        )
                self.repositories_list = \
                    gtk.ListStore(
                        gobject.TYPE_STRING,       # enumerations.REPOSITORY_NAME
                        )

        def declare_signals(self):
                '''Returns dictionary with signal events declared in the glade file
                and mapped to the functions that should be present in this class'''
                dic = \
                    {
                        "on_mainwindow_delete_event":self.on_mainwindow_delete_event,
                        "on_searchentry_changed": self.on_searchentry_changed,
                        "on_searchentry_focus_in_event": self.on_searchentry_focus_in,
                        "on_searchentry_focus_out_event": self.on_searchentry_focus_out,
                        "on_searchentry_event": self.on_searchentry_event,
                        "on_sectionscombobox_changed": self.on_sectionscombobox_changed,
                        "on_filtercombobox_changed": self.on_filtercombobox_changed,
                        "on_repositorycombobox_changed":self.on_repositorycombobox_changed,
                        #menu signals
                        "on_settings_download_preferences_activate":\
                            self.on_settings_download_preferences_activate,
                        "on_file_quit_activate":self.on_file_quit_activate,
                        "on_package_install_update_activate":self.on_install_update,
                        "on_package_remove_activate":self.on_remove,
                        "on_help_about_activate":self.on_help_about,
                        "on_edit_paste_activate":self.on_edit_paste,
                        "on_edit_clear_activate":self.on_clear_paste,
                        "on_edit_copy_activate":self.on_copy,
                        "on_edit_cut_activate":self.on_cut,
                        "on_edit_select_all_activate":self.on_select_all,
                        "on_edit_select_updates_activate":self.on_select_updates,
                        "on_edit_deselect_activate":self.on_deselect,
                        "on_package_update_all_activate":self.on_update_all,
                        #toolbar signals
                        "on_update_all_button_clicked":self.on_update_all,
                        "on_reload_button_clicked":self.on_reload,
                        "on_install_update_button_clicked":self.on_install_update,
                        "on_remove_button_clicked":self.on_remove
                    }
                return dic

        def check_if_pkg_have_row_in_model(self, pkg, p_pkg):
                """Returns True if package is already in model or False if not"""
                if p_pkg:
                        if pkg.is_same_pkg(p_pkg):
                                return True
                        else:
                                return False
                return False

        def on_install_update(self, widget):
                installupdate.InstallUpdate(self.application_list, self)

        def on_update_all(self, widget):
                for row in self.application_list:
                        if self.is_pkg_repository_visible(self.application_list, row.iter):
                                if self.application_list.get_value(row.iter, enumerations.INSTALLED_VERSION_COLUMN):
                                        if self.application_list.get_value(row.iter, enumerations.LATEST_AVAILABLE_COLUMN):
                                                self.application_list.set_value(row.iter, enumerations.MARK_COLUMN, True)
                                        else:
                                                self.application_list.set_value(row.iter, enumerations.MARK_COLUMN, False)
                                else:
                                        self.application_list.set_value(row.iter, enumerations.MARK_COLUMN, False)
                        else:
                                self.application_list.set_value(row.iter, enumerations.MARK_COLUMN, False)
                installupdate.InstallUpdate(self.application_list, self)

        def enable_disable_selection_menus(self):
                self.enable_disable_select_all()
                self.enable_disable_select_updates()
                self.enable_disable_deselect()
                self.enable_disable_update_all()

        def enable_disable_select_all(self):
                if len(self.applicationtreeview.get_model()) > 0:
                        for row in self.applicationtreeview.get_model():
                                if not row[enumerations.MARK_COLUMN]:
                                        self.select_all_menu.set_sensitive(True)
                                        return
                        self.select_all_menu.set_sensitive(False)
                else:
                        self.select_all_menu.set_sensitive(False)

        def enable_disable_install_update(self):
                for row in self.application_list:
                        if row[enumerations.MARK_COLUMN]:
                                if row[enumerations.LATEST_AVAILABLE_COLUMN] and self.user_rights:
                                        self.install_update_button.set_sensitive(True)
                                        self.install_update_menu.set_sensitive(True)
                                        return
                self.install_update_button.set_sensitive(False)
                self.install_update_menu.set_sensitive(False)

        def enable_disable_remove(self):
                for row in self.application_list:
                        if row[enumerations.MARK_COLUMN]:
                                if row[enumerations.INSTALLED_VERSION_COLUMN] and self.user_rights:
                                        self.remove_button.set_sensitive(True)
                                        self.remove_menu.set_sensitive(True)
                                        return
                self.remove_button.set_sensitive(False)
                self.remove_menu.set_sensitive(False)

        def enable_disable_select_updates(self):
                for row in self.applicationtreeview.get_model():
                        if row[enumerations.INSTALLED_VERSION_COLUMN]:
                                if row[enumerations.LATEST_AVAILABLE_COLUMN]:
                                        if not row[enumerations.MARK_COLUMN]:
                                                self.select_updates_menu.set_sensitive(True)
                                                return
                self.select_updates_menu.set_sensitive(False)
                return

        def enable_disable_update_all(self):
                for row in self.application_list:
                        if self.is_pkg_repository_visible(self.application_list, row.iter):
                                if self.application_list.get_value(row.iter, enumerations.INSTALLED_VERSION_COLUMN):
                                        if self.application_list.get_value(row.iter, enumerations.LATEST_AVAILABLE_COLUMN) and self.user_rights:
                                                self.update_all_menu.set_sensitive(True)
                                                self.update_all_button.set_sensitive(True)
                                                return
                self.update_all_button.set_sensitive(False)
                self.update_all_menu.set_sensitive(False)

        def enable_disable_deselect(self):
                for row in self.applicationtreeview.get_model():
                        if row[enumerations.MARK_COLUMN]:
                                self.deselect_menu.set_sensitive(True)
                                return
                self.deselect_menu.set_sensitive(False)
                return

        def on_help_about(self, widget):
                wTreePlan = gtk.glade.XML(self.gladefile, "aboutdialog") 
                aboutdialog = wTreePlan.get_widget("aboutdialog")
                aboutdialog.connect("response", lambda x = None, y = None: aboutdialog.destroy())
                aboutdialog.run()

        def on_remove(self, widget):
                remove.Remove(self.application_list, self)

        def on_reload(self, widget):
                if self.description_thread_running:
                        self.cancelled = True
                self.catalog_refresh()
                self.get_image_from_directory(self.image_directory)
                self.category_list_filter.refilter()
                self.application_list_filter.refilter()

        def catalog_refresh(self):
                """Update image's catalogs."""
                images = self.get_images_from_model()
                full_refresh = True
                for img in images:
                        # Ensure Image directory structure is valid.
                        if not os.path.isdir("%s/catalog" % img.imgdir):
                                img.mkdirs()
                        # Loading catalogs allows us to perform incremental update
                        img.load_catalogs(self.pr)
                        img.retrieve_catalogs(full_refresh)

        def get_images_from_model(self):
                images = []
                for row in self.application_list:
                        image = row[enumerations.IMAGE_OBJECT_COLUMN]
                        if image:
                                if not image in images:
                                        images.append(image)
                return images 

        def get_installed_version(self, image, pkg):
                if not image.has_version_installed(pkg):
                        return None
                else:
                        img = None
                        try:
                                img = image.get_version_installed(pkg)
                        except AttributeError:
                                img = image._get_version_installed(pkg)
                        return img

        def get_image_obj_from_directory(self, image_directory):
                image_obj = image.Image()
                dir = "/"
                try:
                        image_obj.find_root(image_directory)
                        image_obj.load_config()
                        image_obj.load_catalogs(self.pr)
                except ValueError:
                        print self._('%s is not valid image, trying root image')\
                            % image_directory 
                        try:
                                dir = os.environ["PKG_IMAGE"]
                        except KeyError:
                                pass
                        try:
                                image_obj.find_root(dir)
                                image_obj.load_config()
                                image_obj.load_catalogs(self.pr)
                        except ValueError:
                                print self._('%s is not valid root image, return None') % dir
                                image_obj = None
                return image_obj



        def get_image_from_directory(self, image_obj):
                """ This method set up image from the given directory and returns the 
                image object or None"""
                # XXX Convert timestamp to some nice date :)
                self.preparing_list = True
                self.application_list.clear()
                pkgs_known = [ pf for pf in 
                    sorted(image_obj.gen_known_package_fmris()) ]
                #Only one instance of those icons should be in memory
                locked_icon = None #self.get_icon_pixbuf("locked")
                update_available_icon = self.get_icon_pixbuf("new_update")
                update_locked_icon = None #self.get_icon_pixbuf("update_locked")
                #Imageinfo for categories
                imginfo = imageinfo.ImageInfo()
                sectioninfo = imageinfo.ImageInfo()
                catalogs = image_obj.catalogs
                categories = {}
                sections = {}
#                self.setup_repositories_combobox(image_obj)
                for catalog in catalogs:
                        category = imginfo.read(self.application_dir + "/usr/share/package-manager/data/" + catalog)
                        categories[catalog] = category
                        section = sectioninfo.read(self.application_dir + "/usr/share/package-manager/data/" + catalog + ".sections")
                        sections[catalog] = section
                # Speedup, instead of checking if the pkg is already in the list, 
                # iterating through all elements, we will only compare to the previous
                # package and if the package is the same (version difference) then we
                # are adding to the first iterator for the set of those packages. 
                # We can do that, since the list pkgs_known is sorted
                # This will give a sppedup from 18sec to ~3!!!
                p_pkg_itr = None
                p_pkg = None
                insert_count = 0
                icon_path = self.application_dir + "/usr/share/package-manager/data/pixmaps/"
                for pkg in pkgs_known:
                        #speedup hack, check only last package
                        already_in_model = self.check_if_pkg_have_row_in_model(pkg, p_pkg)
                        if not already_in_model:         #Create new row
                                available_version = None
                                version_installed = None
                                status_icon = None
                                fmris = [pkg, ]
                                package_installed = self.get_installed_version(image_obj, pkg)
                                if package_installed:
                                        version_installed = package_installed.version.get_short_version()
                                        #HACK, sometimes the package is installed but it's not in the
                                        #pkgs_known
                                        if package_installed != pkg:
                                                fmris.append(package_installed)
                                else:
                                        dt = self.get_datetime(pkg.version)
                                        dt_str = (":%02d%02d") % (dt.month, dt.day)
                                        available_version = pkg.version.get_short_version() + dt_str
                                package_icon = self.get_pixbuf_from_path(icon_path, pkg.get_name())
                                app = \
                                    [
                                        False, status_icon, package_icon, pkg.get_name(),
                                        version_installed, package_installed,
                                        available_version, -1, self._('...'), fmris,
                                        image_obj, True, None
                                    ]
                                # XXX Small hack, if this is not applied, first package is 
                                #listed twice. Insert is ~0.5 sec faster than append
                                if insert_count == 0:
                                        row_itr = self.application_list.append(app)
                                else:
                                        row_itr = self.application_list.insert(insert_count, app)
                                # XXX Do not iterate through all the catalogs. Package should
                                #know what is package fmri prefix?
                                for cat in categories:
                                        if cat in categories:
                                                if pkg.get_name() in categories[cat]:
                                                        pkg_categories = categories[cat][pkg.get_name()]
                                                        for pkg_category in pkg_categories.split(","):
                                                                if pkg_category:
                                                                        self.add_package_to_category(self._(pkg_category), None, None, row_itr)
                                insert_count = insert_count + 1
                                p_pkg_itr = row_itr
                                p_pkg = pkg                      #The current become previous
                                #self.add_package_to_category("Games", None, None, row_itr)
                        else:
                                # XXX check versions in here. For all installed/not installed:
                                # if there is newer version, put it in the available field.
                                #
                                # XXXhack, since image_get_version_installed(pkg) is not 
                                #working,as it should. For example package:
                                #SUNWarc@0.5.11,5.11-0.79:20080205T152309Z
                                #is not installed and it's newer version of installed package:
                                #SUNWarc@0.5.11,5.11-0.75:20071114T201151Z
                                #the function returns only proper installed version for 
                                #the older package and None for the newer.
                                #The hack is a little bit slow since we are iterating for all
                                #known packages
                                list_of_pkgs = self.application_list.get_value(p_pkg_itr, enumerations.PACKAGE_OBJECT_COLUMN)
                                if pkg not in list_of_pkgs:
                                        list_of_pkgs.append(pkg)
                                installed = self.application_list.get_value(p_pkg_itr, enumerations.INSTALLED_OBJECT_COLUMN)
                                latest = max(list_of_pkgs)
                                dt = self.get_datetime(latest.version)
                                dt_str = (":%02d%02d") % (dt.month, dt.day)
                                if not installed:
                                        self.application_list.set_value(p_pkg_itr, enumerations.LATEST_AVAILABLE_COLUMN, latest.version.get_short_version() + dt_str)
                                else:
                                        if installed < latest:
                                                self.application_list.set_value(p_pkg_itr, enumerations.LATEST_AVAILABLE_COLUMN, latest.version.get_short_version() + dt_str)
                                                self.application_list.set_value(p_pkg_itr, enumerations.STATUS_ICON_COLUMN, update_available_icon)
                        # XXX How to get descriptions without manifest?
                        # XXX Downloading manifest is slow and can not work without 
                        # XXX Network connection
                        #if not image_obj.has_manifest(pkg):
                        #        image_obj.get_manifest(pkg)#verify(pkg, pr)
                        installed_version = None
                        package_itr = None #the iterator which points for other package
                for authority in sections:
                        for section in sections[authority]:
                                for category in sections[authority][section].split(","):
                                        self.add_category_to_section(self._(category), self._(section))
                self.preparing_list = False
                self.application_list_filter.set_visible_func(self.application_filter)
                return self.application_list

        def switch_to_active_valid_image(self):
                ''' switches to active and valid image, if there is no, tries to
                switch to root image, if this fails returns None '''
                pkgconfig = packagemanagerconfig.PackageManagerConfig()
                # XXX We should be able to get list of images (valid and non valid)
                #So we are able to put them into combo-box
                #The imageconfig should return something nicer than now, like 

        def get_manifests_for_packages(self):
                ''' Function, which get's manifest for packages. If the manifest is not
                locally tries to retrieve it. For installed packages gets manifest
                for the particular version (local operation only), if the package is 
                not installed than the newest one'''
                self.description_thread_running = True
                for pkg in self.application_list:
                        if self.cancelled:
                                self.description_thread_running = False
                                return
                        info = None
                        img = pkg[enumerations.IMAGE_OBJECT_COLUMN]
                        pkg_name = pkg[enumerations.NAME_COLUMN]
                        package = pkg[enumerations.PACKAGE_OBJECT_COLUMN][0]
                        if (img and package):
                                version = img.has_version_installed(package)
                                if version:
                                        version = self.get_installed_version(img, package)
                                        man = self.get_manifest(img, version, filtered = True)
                                        if man:
                                                info = man.get("description", "")
                                else:
                                        newest = max(pkg[enumerations.PACKAGE_OBJECT_COLUMN])
                                        man = self.get_manifest(img, newest, filtered = True)
                                        if man:
                                                info = man.get("description", "")
                        # XXX workaround, this should be done nicer
                        gobject.idle_add(self.update_description, info, package)
                self.description_thread_running = False

        def get_manifest(self, image, package, filtered = True):
                '''helper function'''
                # XXX Should go to the  -> imageinfo.py
                manifest = None
                try:
                        manifest = image.get_manifest(package, filtered)
                except OSError:
                        # XXX It is possible here that the user doesn't have network con, or
                        # XXX proper permissions to save manifest, should we do something 
                        # XXX and popup information dialog?
                        pass
                except NameError:
                        pass
                return manifest

        def update_description(self, description, package):
                '''workaround function'''
                for pkg in self.application_list:
                        p = pkg[enumerations.PACKAGE_OBJECT_COLUMN][0]
                        if p == package:
                                pkg[enumerations.DESCRIPTION_COLUMN] = description
                                return

        def add_package_to_category(self, category_name, category_description, category_icon, package):
                if not package or category_name == self._('All'):
                        return
                if not category_name:
                        return
                        # XXX check if needed
                        category_name = self._('All')
                        category_description = self._('All packages')
                        category_icon = None
                category_ref = None
                for category in self.category_list:
                        if category[enumerations.CATEGORY_NAME] == category_name:
                                category_ref = category.iter
                if not category_ref:                       # Category not exists
                        category_ref = self.category_list.append([category_name, category_description, category_icon, True, None])
                if category_ref:
                        if self.application_list.get_value(package, enumerations.CATEGORY_LIST_OBJECT):
                                a = self.application_list.get_value(package, enumerations.CATEGORY_LIST_OBJECT)
                                a.append(category_ref)
                        else:
                                category_list = []
                                category_list.append(category_ref)
                                self.application_list.set(package, enumerations.CATEGORY_LIST_OBJECT, category_list)

        def add_category_to_section(self, category_name, section_name):
                '''Adds the section to section list in category. If there is no such 
                section, than it is not added. If there was already section than it
                is skipped. Sections must be case sensitive'''
                if not category_name:
                        return
                for section in self.section_list:
                        if section[enumerations.SECTION_NAME] == section_name:
                                for category in self.category_list:
                                        if category[enumerations.CATEGORY_NAME] == category_name:
                                                if not category[enumerations.SECTION_LIST_OBJECT]:
                                                        category[enumerations.SECTION_LIST_OBJECT] = [section_name,]
                                                else:
                                                        if not section_name in category[enumerations.SECTION_LIST_OBJECT]:
                                                                category[enumerations.SECTION_LIST_OBJECT].append(section_name)

        def get_icon_pixbuf(self, icon_name):
                return self.get_pixbuf_from_path("/usr/share/icons/package-manager/", icon_name)

        def get_pixbuf_from_path(self, path, icon_name):
                icon = icon_name.replace(' ', '_')
                try:
                        return gtk.gdk.pixbuf_new_from_file(self.application_dir + path + icon + ".png")
                except:
                        try:
                                return gtk.gdk.pixbuf_new_from_file(self.application_dir + path + icon + ".svg")
                        except:
                                iconview = gtk.IconView()
                                icon = iconview.render_icon(getattr(gtk, "STOCK_MISSING_IMAGE"),
                                    size = gtk.ICON_SIZE_MENU,
                                    detail = None)
                                # XXX Could return image, but we don't want to show ugly icon.
                                return None

        def process_package_list_start(self, image_directory):
                image_obj = self.get_image_obj_from_directory(image_directory)
                #gobject # tutaj dodac jakis progress mowiacy o tym ile sie juz zrobilo
                #ten progress powinien byc updatowany z funkcji ponizszej
                self.get_image_from_directory(image_obj)
                # tutaj powinna byc odpalana funkcja ktora zwiaze liste z view,
                #ale oczywiscie w gobject.add_idle
                # na koncu tej funkcji powinien byc dodany filtr


###############################################################################
#-----------------------------------------------------------------------------#
# Test functions
#-----------------------------------------------------------------------------#
        def fill_with_fake_data(self):
                '''test data for gui'''
                app1 = [False, self.get_icon_pixbuf("locked"), self.get_icon_pixbuf("None"), "acc", None, None, None, 4, "desc6", "Object Name1", None, True, None]
                app2 = [False, self.get_icon_pixbuf("update_available"), self.get_icon_pixbuf(self._('All')), "acc_gam", "2.3", None, "2.8", 4, "desc7", "Object Name2", None, True, None]
                app3 = [False, self.get_icon_pixbuf("None"), self.get_icon_pixbuf("Other"), "gam_grap", "2.3", None, None, 4, "desc8", "Object Name3", None, True, None]
                app4 = [False, self.get_icon_pixbuf("update_locked"), self.get_icon_pixbuf("Office"), "grap_gam", "2.3", None, "2.8", 4, "desc9", "Object Name2", None, True, None]
                app5 = [False, self.get_icon_pixbuf("update_available"), self.get_icon_pixbuf("None"), "grap", "2.3", None, "2.8", 4, "desc0", "Object Name3", None, True, None]
                itr1 = self.application_list.append(app1)
                itr2 = self.application_list.append(app2)
                itr3 = self.application_list.append(app3)
                itr4 = self.application_list.append(app4)
                itr5 = self.application_list.append(app5)
                self.preparing_list = False
                #      self.add_package_to_category(_("All"),None,None,None);
                self.add_package_to_category(self._("Accessories"),None,None,itr1)
                self.add_package_to_category(self._("Accessories"),None,None,itr2)
                self.add_package_to_category(self._("Games"),None,None,itr3)
                self.add_package_to_category(self._("Graphics"),None,None,itr3)
                self.add_package_to_category(self._("Games"),None,None,itr2)
                self.add_package_to_category(self._("Graphics"),None,None,itr4)
                self.add_package_to_category(self._("Games"),None,None,itr4)
                self.add_package_to_category(self._("Graphics"),None,None,itr5)

                #     Category names until xdg is imported.
                #     from xdg.DesktopEntry import *
                #     entry = DesktopEntry ()
                #     directory = '/usr/share/desktop-directories'
                #     for root, dirs, files in os.walk (directory):
                #       for name in files:
                #       entry.parse (os.path.join (root, name))
                #       self.add_category_to_section (entry.getName (), self._('Applications Desktop'))

                self.add_category_to_section(self._("Accessories"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Games"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Graphics"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Internet"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Office"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Sound & Video"),self._('Applications Desktop'))
                self.add_category_to_section(self._("System Tools"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Universal Access"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Developer Tools"),self._('Applications Desktop'))
                self.add_category_to_section(self._("Core"),self._('Operating System'))
                self.add_category_to_section(self._("Graphics"),self._('Operating System'))
                self.add_category_to_section(self._("Media"),self._('Operating System'))
                #Can be twice :)
                self.add_category_to_section(self._("Developer Tools"),self._('Operating System'))
                self.add_category_to_section(self._("Office"),"Progs")
                self.add_category_to_section(self._("Office2"),"Progs")

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main():
        gtk.main()
        return 0

if __name__ == '__main__':
        packagemanager = PackageManager()
        packagemanager.create_widgets_and_show_gui()
        test = False
        try:
                opts, args = getopt.getopt(sys.argv[1:], "htd", ["help", "test-gui", "image-dir"])
        except getopt.error, msg:
                print ('%s, for help use --help') % msg
                sys.exit(2)
        for option, arguments in opts:
                if option in ("-h", "--help"):
                        print ('Use -d (--image-dir) to specify image directory.')
                        print ('Use -t (--test-gui) to work on fake data.')
                        sys.exit(0)
                if option in ("-t", "--test-gui"):
                        packagemanager.fill_with_fake_data()
                        test = True
                if option in ("-d", "--image-dir"):
                        if test:
                                print "Options -d and -t can not be used together."
                                sys.exit(0)
                        #Thread(target = packagemanager.process_package_list_start, args = (args[0], )).start()
                        packagemanager.process_package_list_start(args[0])
                        Thread(target = packagemanager.get_manifests_for_packages, args = ()).start()
                        test = True
        if not test:
                #Thread(target = packagemanager.process_package_list_start, args = ("/", )).start()
                packagemanager.process_package_list_start(args[0])
                Thread(target = packagemanager.get_manifests_for_packages, args = ()).start()
        packagemanager.update_statusbar()
        main()
