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

MAX_DESC_LEN = 60                         # Max length of the description
MAX_INFO_CACHE_LIMIT = 100                # Max number of package descriptions to cache
NOTEBOOK_PACKAGE_LIST_PAGE = 0            # Main Package List page index
NOTEBOOK_START_PAGE = 1                   # Main View Start page index
INFO_NOTEBOOK_LICENSE_PAGE = 3            # License Tab index
PUBLISHER_ADD = 0                         # Index for "Add..." string
PUBLISHER_ALL = 1                         # Index for "All Sources" string
SHOW_INFO_DELAY = 600       # Delay before showing selected pacakge information
SHOW_LICENSE_DELAY = 600    # Delay before showing license information
SEARCH_STR_FORMAT = "<%s>"
MIN_APP_WIDTH = 750                       # Minimum application width
MIN_APP_HEIGHT = 500                      # Minimum application height
SECTION_ID_OFFSET = 10000                 # Offset to allow Sections to be identified 
                                          # in category tree
IMAGE_DIRECTORY_DEFAULT = "/"             # Image default directory
MAX_SEARCH_COMPLETION_PREFERENCES = \
        "/apps/packagemanager/preferences/max_search_completion"
INITIAL_APP_WIDTH_PREFERENCES = "/apps/packagemanager/preferences/initial_app_width"
INITIAL_APP_HEIGHT_PREFERENCES = "/apps/packagemanager/preferences/initial_app_height"
INITIAL_APP_HPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_hposition"
INITIAL_APP_VPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_vposition"
INITIAL_SHOW_FILTER_PREFERENCES = "/apps/packagemanager/preferences/initial_show_filter"
INITIAL_SECTION_PREFERENCES = "/apps/packagemanager/preferences/initial_section"
SHOW_STARTPAGE_PREFERENCES = "/apps/packagemanager/preferences/show_startpage"
API_SEARCH_ERROR_PREFERENCES = "/apps/packagemanager/preferences/api_search_error"
CATEGORIES_STATUS_COLUMN_INDEX = 0   # Index of Status Column in Categories TreeView
STATUS_COLUMN_INDEX = 2   # Index of Status Column in Application TreeView
SEARCH_TXT_GREY_STYLE = "#757575" #Close to DimGrey
SEARCH_TXT_BLACK_STYLE = "#000000"
GDK_2BUTTON_PRESS = 5     # gtk.gdk._2BUTTON_PRESS causes pylint warning
GDK_RIGHT_BUTTON = 3      # normally button 3 = right click


PKG_CLIENT_NAME = "packagemanager"
CHECK_FOR_UPDATES = "usr/lib/pm-checkforupdates"

# Location for themable icons
ICON_LOCATION = "usr/share/package-manager/icons"
# Load Start Page from lang dir if available
START_PAGE_CACHE_LANG_BASE = "var/pkg/gui_cache/startpagebase/%s/%s"
START_PAGE_LANG_BASE = "usr/share/package-manager/data/startpagebase/%s/%s"
START_PAGE_HOME = "startpage.html" # Default page

# StartPage Action support for url's on StartPage pages
PM_ACTION = 'pm-action'          # Action field for StartPage url's

# Internal Example: <a href="pm?pm-action=internal&uri=top_picks.html">
ACTION_INTERNAL = 'internal'   # Internal Action value: pm-action=internal
INTERNAL_URI = 'uri'           # Internal field: uri to navigate to in StartPage
                               # without protocol scheme specified

# External Example: <a href="pm?pm-action=external&uri=www.opensolaris.com">
ACTION_EXTERNAL = 'external'   # External Action value: pm-action=external
EXTERNAL_URI = 'uri'           # External field: uri to navigate to in external
                               # default browser without protocol scheme specified
EXTERNAL_PROTOCOL = 'protocol' # External field: optional protocol scheme,
                               # defaults to http
DEFAULT_PROTOCOL = 'http'

import getopt
import pwd
import os
import subprocess
import sys
import time
import locale
import itertools
import urllib
import urlparse
import socket
import gettext
import signal
from threading import Thread
from threading import Lock
from cPickle import UnpicklingError

try:
        import gobject
        import gnome
        gobject.threads_init()
        import gconf
        import gtk
        import gtk.glade
        import pygtk
        pygtk.require("2.0")
        import gtkhtml2
        import pango
        from glib import GError
except ImportError:
        sys.exit(1)
import pkg.misc as misc
import pkg.client.progress as progress
import pkg.client.api_errors as api_errors
import pkg.client.api as api
import pkg.client.publisher as publisher
import pkg.portable as portable
import pkg.fmri as fmri
import pkg.gui.repository as repository
import pkg.gui.beadmin as beadm
import pkg.gui.cache as cache
import pkg.gui.misc as gui_misc
import pkg.gui.imageinfo as imageinfo
import pkg.gui.installupdate as installupdate
import pkg.gui.enumerations as enumerations
import pkg.gui.parseqs as parseqs
import pkg.gui.webinstall as webinstall
from pkg.client import global_settings

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

(
DISPLAY_LINK,
CLICK_LINK,
) = range(2)

class PackageManager:
        def __init__(self):
                signal.signal(signal.SIGINT, self.__main_application_quit)
                # We reset the HOME directory in case the user called us
                # with gksu and had NFS mounted home directory in which
                # case dbus called from gconf cannot write to the directory.
                if os.getuid() == 0:
                        home_dir = self.__find_root_home_dir()
                        os.putenv('HOME', home_dir)
                self.api_o = None
                self.cache_o = None
                self.img_timestamp = None
                self.client = gconf.client_get_default()
                try:
                        self.max_search_completion = \
                            self.client.get_int(MAX_SEARCH_COMPLETION_PREFERENCES)
                        self.initial_show_filter = \
                            self.client.get_int(INITIAL_SHOW_FILTER_PREFERENCES)
                        self.initial_section = \
                            self.client.get_int(INITIAL_SECTION_PREFERENCES)
                        self.show_startpage = \
                            self.client.get_bool(SHOW_STARTPAGE_PREFERENCES)
                        self.gconf_not_show_repos = \
                            self.client.get_string(API_SEARCH_ERROR_PREFERENCES)
                        self.initial_app_width = \
                            self.client.get_int(INITIAL_APP_WIDTH_PREFERENCES)
                        self.initial_app_height = \
                            self.client.get_int(INITIAL_APP_HEIGHT_PREFERENCES)
                        self.initial_app_hpos = \
                            self.client.get_int(INITIAL_APP_HPOS_PREFERENCES)
                        self.initial_app_vpos = \
                            self.client.get_int(INITIAL_APP_VPOS_PREFERENCES)
                except GError:
                        # Default values - the same as in the 
                        # packagemanager-preferences.schemas
                        self.max_search_completion = 20
                        self.initial_show_filter = 0
                        self.initial_section = 2
                        self.show_startpage = True
                        self.gconf_not_show_repos = ""
                        self.initial_app_width = 800
                        self.initial_app_height = 600
                        self.initial_app_hpos = 200
                        self.initial_app_vpos = 320

                if not self.gconf_not_show_repos:
                        self.gconf_not_show_repos = ""
                self.set_show_filter = 0
                self.set_section = 0
                self.in_search_mode = False

                global_settings.client_name = PKG_CLIENT_NAME

                # This call only affects sockets created by Python.  The
                # transport framework uses the defaults in global_settings,
                # which may be overridden in the environment.  The default
                # socket module should only be used in rare cases by ancillary
                # code, making it safe to code the value here, at least for now.
                socket.setdefaulttimeout(30) # in secs

                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("pkg", os.path.join(
                            self.application_dir,
                            "usr/share/locale"))
                        module.textdomain("pkg")
                gui_misc.init_for_help(self.application_dir)
                self.main_window_title = _('Package Manager')
                self.gdk_window = None
                self.user_rights = portable.is_admin()
                self.cancelled = False                    # For background processes
                self.image_directory = None
                self.description_thread_running = False   # For background processes
                gtk.rc_parse('~/.gtkrc-1.2-gnome2')       # Load gtk theme
                self.progress_stop_thread = True
                self.catalog_loaded = False
                self.image_dir_arg = None
                self.update_all_proceed = False
                self.ua_be_name = None
                self.application_path = None
                self.default_publisher = None
                self.current_repos_with_search_errors = []
                self.first_run = True
                self.in_reload = False
                self.selected_pkgstem = None
                self.selected_model = None
                self.selected_path = None
                self.info_cache = {}
                self.selected = 0
                self.selected_pkgs = {}
                self.start_page_url = None
                self.to_install_update = {}
                self.to_remove = {}
                self.in_startpage_startup = self.show_startpage
                self.lang = None
                self.lang_root = None
                self.visible_status_id = 0
                self.categories_status_id = 0
                self.icon_theme = gtk.IconTheme()
                icon_location = os.path.join(self.application_dir, ICON_LOCATION)
                self.icon_theme.append_search_path(icon_location)
                self.installed_icon = gui_misc.get_icon(self.icon_theme,
                    'status_installed')
                self.not_installed_icon = gui_misc.get_icon(self.icon_theme,
                    'status_notinstalled')
                self.update_available_icon = gui_misc.get_icon(self.icon_theme,
                    'status_newupdate')
                self.filter_options = [
                    (enumerations.FILTER_ALL,
                    gui_misc.get_icon(self.icon_theme, 'filter_all'),
                    _('All Packages')),
                    (enumerations.FILTER_INSTALLED, self.installed_icon,
                    _('Installed Packages')),
                    (enumerations.FILTER_UPDATES, self.update_available_icon,
                    _('Updates')),
                    (enumerations.FILTER_NOT_INSTALLED, self.not_installed_icon,
                    _('Not installed Packages')),
                    (-1, None, ""),
                    (enumerations.FILTER_SELECTED,
                    gui_misc.get_icon(self.icon_theme, 'filter_selected'),
                    _('Selected Packages'))
                    ]
                self.publisher_options = { 
                    PUBLISHER_ADD : _("Add..."),
                    PUBLISHER_ALL : _("All Sources (Search Only)")}
                self.last_visible_publisher = None
                self.last_visible_publisher_uptodate = False
                self.publisher_changed = True
                self.search_start = 0
                self.search_time_sec = 0
                self.search_all_pub_being_searched = None
                self.section_list = None
                self.filter_list = self.__get_new_filter_liststore()
                self.length_visible_list = 0
                self.application_list = None
                self.a11y_application_treeview = None
                self.application_treeview_range = None
                self.application_treeview_initialized = False
                self.categories_treeview_range = None
                self.categories_treeview_initialized = False
                self.category_list = None
                self.repositories_list = None
                self.repo_combobox_all_pubs_index = 0
                self.repo_combobox_add_index = 0
                self.pr = progress.NullProgressTracker()
                self.pylintstub = None
                self.release_notes_url = "http://www.opensolaris.org"
                self.__image_activity_lock = Lock()
                self.category_expanded_paths = {}
                self.category_active_paths = {}
                
                # Create Widgets and show gui
                self.gladefile = os.path.join(self.application_dir,
                    "usr/share/package-manager/packagemanager.glade")
                w_tree_main = gtk.glade.XML(self.gladefile, "mainwindow")
                w_tree_preferences = gtk.glade.XML(self.gladefile, "preferencesdialog")
                w_tree_api_search_error = gtk.glade.XML(self.gladefile,
                    "api_search_error")
                self.w_preferencesdialog = \
                    w_tree_preferences.get_widget("preferencesdialog")
                self.w_startpage_checkbutton = \
                    w_tree_preferences.get_widget("startpage_checkbutton")
                self.api_search_error_dialog = \
                    w_tree_api_search_error.get_widget("api_search_error")
                self.api_search_error_textview = \
                    w_tree_api_search_error.get_widget("api_search_error_text")
                self.api_search_checkbox = \
                    w_tree_api_search_error.get_widget("api_search_checkbox")
                self.api_search_button = \
                    w_tree_api_search_error.get_widget("api_search_button")
                infobuffer = self.api_search_error_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

                self.w_main_window = w_tree_main.get_widget("mainwindow")
                self.w_main_hpaned = \
                    w_tree_main.get_widget("main_hpaned")
                self.w_main_vpaned = \
                    w_tree_main.get_widget("main_vpaned")

                self.w_application_treeview = \
                    w_tree_main.get_widget("applicationtreeview")
                self.w_application_treeview.connect('key_press_event',
                    self.__on_applicationtreeview_button_and_key_events)
                self.w_application_treeview.connect('motion-notify-event',
                    self.__on_applicationtreeview_motion_events)
                self.applicationtreeview_tooltips = None

                self.w_categories_treeview = w_tree_main.get_widget("categoriestreeview")
                self.w_info_notebook = w_tree_main.get_widget("details_notebook")
                self.w_generalinfo_textview = \
                    w_tree_main.get_widget("generalinfotextview")
                self.w_generalinfo_textview.get_buffer().create_tag(
                    "bold", weight=pango.WEIGHT_BOLD)
                self.w_installedfiles_textview = \
                    w_tree_main.get_widget("installedfilestextview")
                self.w_installedfiles_textview.get_buffer().create_tag(
                    "bold", weight=pango.WEIGHT_BOLD)
                self.w_license_textview = \
                    w_tree_main.get_widget("licensetextview")
                self.w_dependencies_textview = \
                    w_tree_main.get_widget("dependenciestextview")
                self.w_dependencies_textview.get_buffer().create_tag(
                    "bold", weight=pango.WEIGHT_BOLD)
                self.w_general_info_label = \
                    w_tree_main.get_widget("general_info_label")
                self.w_startpage_frame = \
                    w_tree_main.get_widget("startpage_frame")
                self.w_startpage_eventbox = \
                    w_tree_main.get_widget("startpage_eventbox")
                self.w_startpage_eventbox.modify_bg(gtk.STATE_NORMAL,
                    gtk.gdk.color_parse("white"))

                self.w_main_statusbar = w_tree_main.get_widget("statusbar")
                self.w_statusbar_hbox = w_tree_main.get_widget("statusbar_hbox")
                self.w_infosearch_frame = w_tree_main.get_widget("infosearch_frame")
                self.w_infosearch_button = w_tree_main.get_widget("infosearch_button")

                self.w_progress_frame = w_tree_main.get_widget("progress_frame")
                self.w_status_progressbar = w_tree_main.get_widget("status_progressbar")
                self.w_status_progressbar.set_pulse_step(0.1)
                self.w_progress_frame.hide()

                self.w_main_view_notebook = \
                    w_tree_main.get_widget("main_view_notebook")
                self.w_searchentry = w_tree_main.get_widget("searchentry")
                self.entry_embedded_icons_supported = True
                try:
                        self.w_searchentry.set_property("secondary-icon-stock", None)
                except TypeError:
                        self.entry_embedded_icons_supported = False
                self.search_text_style = -1
                self.__set_search_text_mode(enumerations.SEARCH_STYLE_PROMPT)
                self.search_completion = gtk.ListStore(str)
                self.w_package_menu = w_tree_main.get_widget("package_menu")
                self.w_reload_button = w_tree_main.get_widget("reload_button")
                self.w_installupdate_button = \
                    w_tree_main.get_widget("install_update_button")
                self.w_remove_button = w_tree_main.get_widget("remove_button")
                self.w_updateall_button = w_tree_main.get_widget("update_all_button")
                self.w_reload_menuitem = w_tree_main.get_widget("file_reload")
                self.w_repository_combobox = w_tree_main.get_widget("repositorycombobox")
                self.w_filter_combobox = w_tree_main.get_widget("filtercombobox")
                self.w_packageicon_image = w_tree_main.get_widget("packageimage")
                self.w_installupdate_menuitem = \
                    w_tree_main.get_widget("package_install_update")
                self.w_remove_menuitem = w_tree_main.get_widget("package_remove")
                self.w_updateall_menuitem = w_tree_main.get_widget("package_update_all")
                self.w_cut_menuitem = w_tree_main.get_widget("edit_cut")
                self.w_copy_menuitem = w_tree_main.get_widget("edit_copy")
                self.w_paste_menuitem = w_tree_main.get_widget("edit_paste")
                self.w_delete_menuitem = w_tree_main.get_widget("edit_delete")
                self.w_selectall_menuitem = w_tree_main.get_widget("edit_select_all")
                self.w_selectupdates_menuitem = \
                    w_tree_main.get_widget("edit_select_updates")
                self.w_deselect_menuitem = w_tree_main.get_widget("edit_deselect")
                self.w_clear_search_menuitem = w_tree_main.get_widget("clear")
                self.w_main_clipboard =  gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)
                self.saved_filter_combobox_active = self.initial_show_filter
                self.search_image = w_tree_main.get_widget("search_image")
                self.search_button = w_tree_main.get_widget("do_search")
                self.progress_cancel = w_tree_main.get_widget("progress_cancel")
                self.is_all_publishers = False
                self.search_image.set_from_pixbuf(gui_misc.get_icon(self.icon_theme,
                    'search', 20))
                self.saved_repository_combobox_active = 0
                self.saved_section_active = 0
                self.saved_application_list = None
                self.saved_application_list_filter = None
                self.saved_application_list_sort = None
                self.saved_category_list = None
                self.saved_section_list = None
                self.saved_selected_application_path = None
                self.section_categories_list = {}
                self.statusbar_message_id = 0
                toolbar =  w_tree_main.get_widget("toolbutton2")
                toolbar.set_expand(True)
                self.__init_repository_tree_view()
                self.install_button_tooltip = gtk.Tooltips()
                self.remove_button_tooltip = gtk.Tooltips()
                self.__update_reload_button()
                self.w_main_window.set_title(self.main_window_title)
                self.w_repository_combobox.grab_focus()

                # Update All Completed Dialog
                w_xmltree_ua_completed = gtk.glade.XML(self.gladefile,
                    "ua_completed_dialog")
                self.w_ua_completed_dialog = w_xmltree_ua_completed.get_widget(
                    "ua_completed_dialog")
                self.w_ua_completed_dialog .connect("destroy",
                    self.__on_ua_completed_close)
                self.w_ua_completed_release_label = w_xmltree_ua_completed.get_widget(
                    "ua_completed_release_label")
                self.w_ua_completed_linkbutton = w_xmltree_ua_completed.get_widget(
                    "ua_completed_linkbutton")

                # Setup Start Page
                self.document = None
                self.view = None
                self.current_url = None
                self.opener = None
                self.__setup_startpage(self.show_startpage)

                try:
                        dic_mainwindow = \
                            {
                                "on_mainwindow_delete_event": \
                                    self.__on_mainwindow_delete_event,
                                "on_mainwindow_check_resize": \
                                    self.__on_mainwindow_check_resize,
                                "on_mainwindow_key_press_event": \
                                    self.__on_mainwindow_key_press_event,
                                "on_searchentry_changed":self.__on_searchentry_changed,
                                "on_searchentry_focus_in_event": \
                                    self.__on_searchentry_focus_in,
                                "on_searchentry_focus_out_event": \
                                    self.__on_searchentry_focus_out,
                                "on_searchentry_activate": \
                                    self.__do_search,
                                "on_filtercombobox_changed": \
                                    self.__on_filtercombobox_changed,
                                "on_repositorycombobox_changed": \
                                    self.__on_repositorycombobox_changed,
                                #menu signals
                                "on_file_quit_activate":self.__on_file_quit_activate,
                                "on_file_be_activate":self.__on_file_be_activate,
                                "on_package_install_update_activate": \
                                    self.__on_install_update,
                                "on_settings_edit_repositories_activate": \
                                    self.__on_edit_repositories_activate,
                                "on_package_remove_activate":self.__on_remove,
                                "on_help_about_activate":self.__on_help_about,
                                "on_help_help_activate":self.__on_help_help,
                                "on_edit_paste_activate":self.__on_edit_paste,
                                "on_edit_delete_activate":self.__on_delete,
                                "on_edit_copy_activate":self.__on_copy,
                                "on_edit_cut_activate":self.__on_cut,
                                "on_edit_search_activate":self.__on_edit_search_clicked,
                                "on_goto_list_activate":self.__on_goto_list_clicked,
                                "on_clear_search_activate":self.__on_clear_search,
                                "on_clear_search_clicked":self.__on_clear_search,
                                "on_do_search_clicked":self.__do_search,
                                "on_do_search_button_press_event":self.__do_search,
                                "on_progress_cancel_clicked": \
                                    self.__on_progress_cancel_clicked,
                                "on_edit_select_all_activate":self.__on_select_all,
                                "on_edit_select_updates_activate": \
                                    self.__on_select_updates,
                                "on_edit_deselect_activate":self.__on_deselect,
                                "on_edit_preferences_activate":self.__on_preferences,
                                # XXX disabled until new API
                                "on_package_update_all_activate":self.__on_update_all,
                                #toolbar signals
                                # XXX disabled until new API
                                "on_update_all_button_clicked":self.__on_update_all,
                                "on_reload_button_clicked":self.__on_reload,
                                "on_install_update_button_clicked": \
                                    self.__on_install_update,
                                "on_remove_button_clicked":self.__on_remove,
                                "on_help_start_page_activate":self.__on_startpage,
                                "on_details_notebook_switch_page": \
                                    self.__on_notebook_change,
                                "on_infosearch_button_clicked": \
                                    self.__on_infosearch_button_clicked,
                                "on_applicationtreeview_button_press_event": \
                                    self.__on_applicationtreeview_button_and_key_events,
                            }
                        dic_preferences = \
                            {
                                "on_startpage_checkbutton_toggled": \
                                    self.__on_startpage_checkbutton_toggled,
                                "on_preferenceshelp_clicked": \
                                    self.__on_preferenceshelp_clicked,
                                "on_preferencesclose_clicked": \
                                    self.__on_preferencesclose_clicked,
                            }
                        dic_api_search_error = \
                            {
                                "on_api_search_checkbox_toggled": \
                                    self.__on_api_search_checkbox_toggled,
                                "on_api_search_button_clicked": \
                                    self.__on_api_search_button_clicked,
                                "on_api_search_error_delete_event": \
                                    self.__on_api_search_error_delete_event,
                            }
                        dic_completed = \
                            {
                                "on_ua_complete_close_button_clicked": \
                                     self.__on_ua_completed_close,
                                "on_ua_completed_linkbutton_clicked": \
                                     self.__on_ua_completed_linkbutton_clicked,
                            }
                        w_xmltree_ua_completed.signal_autoconnect(dic_completed)
        
                            
                        w_tree_main.signal_autoconnect(dic_mainwindow)
                        w_tree_preferences.signal_autoconnect(dic_preferences)
                        w_tree_api_search_error.signal_autoconnect(
                            dic_api_search_error)
                except AttributeError, error:
                        print _(
                            "GUI will not respond to any event! %s."
                            "Check declare_signals()") \
                            % error

                self.package_selection = None
                self.category_list_filter = None
                self.application_list_filter = None
                self.application_list_sort = None
                self.application_refilter_id = 0
                self.application_refilter_idle_id = 0
                self.last_show_info_id = 0
                self.show_info_id = 0
                self.last_show_licenses_id = 0
                self.show_licenses_id = 0
                self.showing_empty_details = False
                self.in_setup = True
                self.catalog_refresh_done = False
                if self.initial_app_width >= MIN_APP_WIDTH and \
                        self.initial_app_height >= MIN_APP_HEIGHT:
                        self.w_main_window.resize(self.initial_app_width,
                            self.initial_app_height)
                if self.initial_app_hpos > 0:
                        self.w_main_hpaned.set_position(self.initial_app_hpos)
                if self.initial_app_vpos > 0:
                        self.w_main_vpaned.set_position(self.initial_app_vpos)
                self.w_main_window.show_all()
                gdk_win = self.w_main_window.get_window()
                self.gdk_window = gtk.gdk.Window(gdk_win, gtk.gdk.screen_width(),
                    gtk.gdk.screen_height(), gtk.gdk.WINDOW_CHILD, 0, gtk.gdk.INPUT_ONLY)
                gdk_cursor = gtk.gdk.Cursor(gtk.gdk.WATCH)

                self.gdk_window.set_cursor(gdk_cursor)
                if self.show_startpage:
                        self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                else:
                        self.w_main_view_notebook.set_current_page(
                            NOTEBOOK_PACKAGE_LIST_PAGE)
                self.api_search_error_dialog.set_transient_for(self.w_main_window)
                self.__setup_text_signals()

        def __set_search_text_mode(self, style):
                if style == enumerations.SEARCH_STYLE_NORMAL:
                        self.w_searchentry.modify_text(gtk.STATE_NORMAL,
                                gtk.gdk.color_parse(SEARCH_TXT_BLACK_STYLE))
                        if self.search_text_style == enumerations.SEARCH_STYLE_PROMPT or\
                                self.w_searchentry.get_text() == _("Search (Ctrl-F)"):
                                self.w_searchentry.set_text("")
                        self.search_text_style = enumerations.SEARCH_STYLE_NORMAL
                        
                else:
                        self.w_searchentry.modify_text(gtk.STATE_NORMAL,
                                gtk.gdk.color_parse(SEARCH_TXT_GREY_STYLE))
                        self.search_text_style = enumerations.SEARCH_STYLE_PROMPT
                        self.w_searchentry.set_text(_("Search (Ctrl-F)"))
        
        def __search_completion_cb(self, entry):
                text = entry.get_text()
                if text:
                        if text not in [row[0] for row in self.search_completion]:
                                len_search_completion = len(self.search_completion)
                                if len_search_completion > 0 and \
                                        len_search_completion >= \
                                                self.max_search_completion:
                                        itr = self.search_completion.get_iter_first()
                                        if itr:
                                                self.search_completion.remove(itr)
                                self.search_completion.append([text])
                return
                
        def __setup_text_signals(self):
                self.w_generalinfo_textview.get_buffer().connect(
                    "notify::has-selection", self.__on_text_buffer_has_selection)
                self.w_installedfiles_textview.get_buffer().connect(
                    "notify::has-selection", self.__on_text_buffer_has_selection)
                self.w_dependencies_textview.get_buffer().connect(
                    "notify::has-selection", self.__on_text_buffer_has_selection)
                self.w_license_textview.get_buffer().connect(
                    "notify::has-selection", self.__on_text_buffer_has_selection)
                self.w_searchentry.connect(
                    "notify::cursor-position", self.__on_searchentry_selection)
                self.w_searchentry.connect(
                    "notify::selection-bound", self.__on_searchentry_selection)
                self.w_generalinfo_textview.connect(
                    "focus-in-event", self.__on_textview_focus_in)
                self.w_installedfiles_textview.connect(
                    "focus-in-event", self.__on_textview_focus_in)
                self.w_dependencies_textview.connect(
                    "focus-in-event", self.__on_textview_focus_in)
                self.w_license_textview.connect(
                    "focus-in-event", self.__on_textview_focus_in)
                self.w_generalinfo_textview.connect(
                    "focus-out-event", self.__on_textview_focus_out)
                self.w_installedfiles_textview.connect(
                    "focus-out-event", self.__on_textview_focus_out)
                self.w_dependencies_textview.connect(
                    "focus-out-event", self.__on_textview_focus_out)
                self.w_license_textview.connect(
                    "focus-out-event", self.__on_textview_focus_out)

        def __on_textview_focus_in(self, widget, event):
                char_count = widget.get_buffer().get_char_count()
                if char_count > 0:
                        self.w_selectall_menuitem.set_sensitive(True)
                else:
                        self.w_selectall_menuitem.set_sensitive(False)
                bounds = widget.get_buffer().get_selection_bounds()
                if bounds:
                        offset1 = bounds[0].get_offset() 
                        offset2 = bounds[1].get_offset() 
                        if abs(offset2 - offset1) == char_count:
                                self.w_selectall_menuitem.set_sensitive(False)
                        self.w_deselect_menuitem.set_sensitive(True)
                        self.w_copy_menuitem.set_sensitive(True)
                else:
                        self.w_deselect_menuitem.set_sensitive(False)

        def __on_textview_focus_out(self, widget, event):
                self.__enable_disable_select_all()
                self.__enable_disable_deselect()
                self.w_copy_menuitem.set_sensitive(False)

        def __on_text_buffer_has_selection(self, obj, pspec):
                if obj.get_selection_bounds():
                        self.w_copy_menuitem.set_sensitive(True)
                        self.w_deselect_menuitem.set_sensitive(True)
                else:
                        self.w_copy_menuitem.set_sensitive(False)
                        self.w_deselect_menuitem.set_sensitive(False)

        def __register_iconsets(self, icon_info):
                factory = gtk.IconFactory()
                for stock_id, pixbuf, name, description in icon_info:
                        iconset = gtk.IconSet(pixbuf)
                        factory.add(stock_id, iconset)
                        self.pylintstub = name
                        self.pylintstub = description
                factory.add_default()

        def __set_all_publishers_mode(self):
                if self.is_all_publishers:
                        return
                self.__setup_before_all_publishers_mode()

        def __setup_startpage(self, show_startpage):
                self.opener = urllib.FancyURLopener()
                self.document = gtkhtml2.Document()
                self.document.connect('request_url', self.__request_url)
                self.document.connect('link_clicked', self.__handle_link)
                self.document.clear()

                self.view = gtkhtml2.View()
                self.view.set_document(self.document)
                self.view.connect('request_object', self.__request_object)
                self.view.connect('on_url', self.__on_url)

                try:
                        self.lang, encode = locale.getlocale(locale.LC_CTYPE)
                        if debug:
                                print "Lang: %s: Encode: %s" % (self.lang, encode)
                except locale.Error:
                        self.lang = "C"
                if self.lang == None or self.lang == "":
                        self.lang = "C"
                self.lang_root = self.lang.split('_')[0]
                if show_startpage:
                        self.__load_startpage()
                self.w_startpage_frame.add(self.view)

        # Stub handler required by GtkHtml widget
        def __request_object(self, *vargs):
                pass

        def __load_startpage(self):
                if self.__load_startpage_locale(START_PAGE_CACHE_LANG_BASE):
                        return
                if self.__load_startpage_locale(START_PAGE_LANG_BASE):
                        return                        
                self.__handle_startpage_load_error(self.start_page_url)


        def __load_startpage_locale(self, start_page_lang_base):
                self.start_page_url = os.path.join(self.application_dir,
                        start_page_lang_base % (self.lang, START_PAGE_HOME))
                if self.__load_uri(self.document, self.start_page_url):
                        return True
                        
                if self.lang_root != None and self.lang_root != self.lang:
                        start_page_url = os.path.join(self.application_dir,
                                start_page_lang_base % (self.lang_root, START_PAGE_HOME))
                        if self.__load_uri(self.document, start_page_url):
                                return True

                start_page_url = os.path.join(self.application_dir,
                        start_page_lang_base % ("C", START_PAGE_HOME))
                if self.__load_uri(self.document, start_page_url):
                        return True
                return False

        def __handle_startpage_load_error(self, start_page_url):
                self.document.open_stream('text/html')
                self.document.write_stream(_(
                    "<html><head></head><body><H2>Welcome to"
                    "PackageManager!</H2><br>"
                    "<font color='#0000FF'>Warning: Unable to "
                    "load Start Page:<br>%s</font></body></html>"
                    % (start_page_url)))
                self.document.close_stream()

        def __process_api_search_error(self, error):
                self.current_repos_with_search_errors = []

                for pub, err in error.failed_servers:
                        self.current_repos_with_search_errors.append(
                            (pub, _("failed to respond"), err))
                for pub in error.invalid_servers:
                        self.current_repos_with_search_errors.append(
                            (pub, _("invalid response"),
                                _("A valid response was not returned.")))
                for pub, err in error.unsupported_servers:
                        self.current_repos_with_search_errors.append(
                            (pub, _("unsupported search"), err))

        def __on_infosearch_button_clicked(self, widget):
                self.__handle_api_search_error(True)

        def __handle_api_search_error(self, show_all=False):
                if len(self.current_repos_with_search_errors) == 0:
                        self.w_infosearch_frame.hide()
                        return

                repo_count = 0
                for pub, err_type, err_str in self.current_repos_with_search_errors:
                        if show_all or (pub not in self.gconf_not_show_repos):
                                repo_count += 1
                if repo_count == 0:
                        self.w_infosearch_frame.hide()
                        return

                self.w_infosearch_button.set_size_request(26, 22)
                self.w_infosearch_frame.show()
                infobuffer = self.api_search_error_textview.get_buffer()
                infobuffer.set_text("")
                textiter = infobuffer.get_end_iter()
                for pub, err_type, err_str in self.current_repos_with_search_errors:

                        if show_all or (pub not in self.gconf_not_show_repos):
                                infobuffer.insert_with_tags_by_name(textiter,
                                    "%(pub)s (%(err_type)s)\n" % {"pub": pub,
                                    "err_type": err_type}, "bold")
                                infobuffer.insert(textiter, "%s\n" % (err_str))

                self.api_search_checkbox.set_active(False)
                self.api_search_error_dialog.show()
                self.api_search_button.grab_focus()

        def __on_url(self, view, link):
                # Handle mouse over events on links and reset when not on link
                if link == None or link == "":
                        self.update_statusbar()
                else:
                        display_link = self.__handle_link(None, link, DISPLAY_LINK)
                        if display_link != None:
                                self.__update_statusbar_message(display_link)
                        else:
                                self.update_statusbar()

        @staticmethod
        def __is_relative_to_server(url):
                parts = urlparse.urlparse(url)
                if parts[0] or parts[1]:
                        return 0
                return 1

        def __open_url(self, url):
                uri = self.__resolve_uri(url)
                return self.opener.open(uri)

        def __resolve_uri(self, uri):
                if self.__is_relative_to_server(uri) and self.current_url != uri:
                        return urlparse.urljoin(self.current_url, uri)
                return uri

        def __request_url(self, document, url, stream):
                f = self.__open_url(url)
                stream.set_cancel_func(self.__stream_cancel)
                stream.write(f.read())

        # Stub handler required by GtkHtml widget or widget will assert
        def __stream_cancel(self, *vargs):
                pass

        def __load_uri(self, document, link):
                self.__update_statusbar_message(_("Loading... " + link))
                try:
                        f = self.__open_url(link)
                except  (IOError, OSError), err:
                        if debug:
                                print "err: %s" % (err)
                        self.__update_statusbar_message(_("Stopped"))
                        return False
                self.current_url = self.__resolve_uri(link)

                self.document.clear()
                headers = f.info()
                mime = headers.getheader('Content-type').split(';')[0]
                if mime:
                        self.document.open_stream(mime)
                else:
                        self.document.open_stream('text/plain')

                self.document.write_stream(f.read())
                self.document.close_stream()
                self.__update_statusbar_message(_("Done"))
                return True

        def __link_load_error(self, link):
                self.document.clear()
                self.document.open_stream('text/html')
                self.document.write_stream(_(
                    "<html><head></head><body><font color='#000000'>\
                    <a href='stub'></a></font>\
                    <a href='pm?%s=internal&uri=%s'>\
                    <IMG SRC = 'startpage_star.png' \
                    style='border-style: none'></a> <br><br>\
                    <h2><font color='#0000FF'>Warning: Unable to \
                    load URL</font></h2><br>%s</body></html>"
                    % (PM_ACTION, START_PAGE_HOME, link)))
                self.document.close_stream()

        def __handle_link(self, document, link, handle_what = CLICK_LINK):
                query_dict = self.__urlparse_qs(link)

                action = None
                if query_dict.has_key(PM_ACTION):
                        action = query_dict[PM_ACTION][0]
                elif handle_what == DISPLAY_LINK:
                        return link
                ext_uri = ""
                protocol = None

                # Internal Browse
                if action == ACTION_INTERNAL:
                        if query_dict.has_key(INTERNAL_URI):
                                int_uri = query_dict[INTERNAL_URI][0]
                                if handle_what == DISPLAY_LINK:
                                        return int_uri
                        else:
                                if handle_what == CLICK_LINK:
                                        self.__link_load_error(_("No URI specified"))
                                return
                        if handle_what == CLICK_LINK and \
                            not self.__load_uri(document, int_uri):
                                self.__link_load_error(int_uri)
                        return
                # External browse
                elif action == ACTION_EXTERNAL:
                        if query_dict.has_key(EXTERNAL_URI):
                                ext_uri = query_dict[EXTERNAL_URI][0]
                        else:
                                if handle_what == CLICK_LINK:
                                        self.__link_load_error(_("No URI specified"))
                                return
                        if query_dict.has_key(EXTERNAL_PROTOCOL):
                                protocol = query_dict[EXTERNAL_PROTOCOL][0]
                        else:
                                protocol = DEFAULT_PROTOCOL

                        if handle_what == DISPLAY_LINK:
                                return protocol + "://" + ext_uri
                        try:
                                gnome.url_show(protocol + "://" + ext_uri)
                        except gobject.GError:
                                self.__link_load_error(protocol + "://" + ext_uri)
                elif handle_what == DISPLAY_LINK:
                        return None
                elif action == None:
                        try:
                                gnome.url_show(link)
                        except gobject.GError:
                                self.__link_load_error(link)
                # Handle empty and unsupported actions
                elif action == "":
                        self.__link_load_error(_("Empty Action not supported"
                            % action))
                        return
                elif action != None:
                        self.__link_load_error(_("Action not supported: %s"
                            % action))
                        return

        @staticmethod
        def __urlparse_qs(url, keep_blank_values=0, strict_parsing=0):
                scheme, netloc, url, params, querystring, fragment = urlparse.urlparse(
                    url)
                if debug:
                        print ("Query: scheme %s, netloc %s, url %s, params %s,"
                            "querystring %s, fragment %s"
                            % (scheme, netloc, url, params, querystring, fragment))
                return parseqs.parse_qs(querystring)

        @staticmethod
        def __get_new_application_liststore():
                return gtk.ListStore(
                        gobject.TYPE_BOOLEAN,     # enumerations.MARK_COLUMN
                        gtk.gdk.Pixbuf,           # enumerations.STATUS_ICON_COLUMN
                        gobject.TYPE_STRING,      # enumerations.NAME_COLUMN
                        gobject.TYPE_STRING,      # enumerations.DESCRIPTION_COLUMN
                        gobject.TYPE_INT,         # enumerations.STATUS_COLUMN
                        gobject.TYPE_PYOBJECT,    # enumerations.FMRI_COLUMN
                        gobject.TYPE_STRING,      # enumerations.STEM_COLUMN
                        gobject.TYPE_STRING,      # enumerations.DISPLAY_NAME_COLUMN
                        gobject.TYPE_BOOLEAN,     # enumerations.IS_VISIBLE_COLUMN
                        gobject.TYPE_PYOBJECT,    # enumerations.CATEGORY_LIST_COLUMN
                        gobject.TYPE_STRING       # enumerations.REPOSITORY_COLUMN
                        )

        @staticmethod
        def __get_new_category_liststore():
                return gtk.TreeStore(
                        gobject.TYPE_INT,         # enumerations.CATEGORY_ID
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_NAME
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_DESCRIPTION
                        gobject.TYPE_PYOBJECT,    # enumerations.SECTION_LIST_OBJECT
                        )

        @staticmethod
        def __get_new_section_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.SECTION_ID
                        gobject.TYPE_STRING,      # enumerations.SECTION_NAME
                        gobject.TYPE_BOOLEAN,     # enumerations.SECTION_ENABLED
                        )

        @staticmethod
        def __get_new_filter_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.FILTER_ID
                        gtk.gdk.Pixbuf,           # enumerations.FILTER_ICON
                        gobject.TYPE_STRING,      # enumerations.FILTER_NAME
                        )

        @staticmethod
        def __get_new_repositories_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.REPOSITORY_ID
                        gobject.TYPE_STRING,      # enumerations.REPOSITORY_NAME
                        )

        def __init_application_tree_view(self, application_list,
            application_list_filter, application_list_sort,
            application_sort_column):
                ##APPLICATION MAIN TREEVIEW
                if application_list_filter == None:
                        application_list_filter = application_list.filter_new()
                if application_list_sort == None:
                        application_list_sort = \
                            gtk.TreeModelSort(application_list_filter)
                        application_list_sort.set_sort_column_id(
                            application_sort_column, gtk.SORT_ASCENDING)
                        application_list_sort.set_sort_func(
                            enumerations.STATUS_ICON_COLUMN, self.__status_sort_func)
                toggle_renderer = gtk.CellRendererToggle()

                column = gtk.TreeViewColumn("", toggle_renderer,
                    active = enumerations.MARK_COLUMN)
                column.set_cell_data_func(toggle_renderer, self.cell_data_function, None)
                column.set_clickable(True)
                column.connect('clicked', self.__select_column_clicked)
                self.w_application_treeview.append_column(column)
                image = gtk.Image()
                image.set_from_pixbuf(gui_misc.get_icon(self.icon_theme, 'selection'))
                tooltips = gtk.Tooltips()
                tooltips.set_tip(image, _("Click to toggle selections"))
                image.show()
                column.set_widget(image)

                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Name"), name_renderer,
                    text = enumerations.NAME_COLUMN)
                column.set_resizable(True)
                column.set_min_width(150)
                column.set_sort_column_id(enumerations.NAME_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(name_renderer, self.cell_data_function, None)
                column.connect_after('clicked',
                    self.__application_treeview_column_sorted, None)
                self.w_application_treeview.append_column(column)
                column = self.__create_icon_column(_("Status"), True,
                    enumerations.STATUS_ICON_COLUMN, True)
                column.set_sort_column_id(enumerations.STATUS_ICON_COLUMN)
                column.set_sort_indicator(True)
                column.connect_after('clicked',
                    self.__application_treeview_column_sorted, None)
                self.w_application_treeview.append_column(column)
                if self.is_all_publishers:
                        repository_renderer = gtk.CellRendererText()
                        column = gtk.TreeViewColumn(_('Repository'),
                            repository_renderer,
                            text = enumerations.AUTHORITY_COLUMN)
                        column.set_sort_column_id(enumerations.AUTHORITY_COLUMN)
                        column.set_resizable(True)
                        column.set_sort_indicator(True)
                        column.set_cell_data_func(repository_renderer,
                            self.cell_data_function, None)
                        column.connect_after('clicked',
                            self.__application_treeview_column_sorted, None)
                        self.w_application_treeview.append_column(column)
                description_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_('Description'),
                    description_renderer,
                    text = enumerations.DESCRIPTION_COLUMN)
                column.set_sort_column_id(enumerations.DESCRIPTION_COLUMN)
                column.set_resizable(True)
                column.set_sort_indicator(True)
                column.set_cell_data_func(description_renderer,
                    self.cell_data_function, None)
                column.connect_after('clicked',
                    self.__application_treeview_column_sorted, None)
                self.w_application_treeview.append_column(column)
                #Added selection listener
                self.package_selection = self.w_application_treeview.get_selection()
                self.application_list = application_list
                self.application_list_filter = application_list_filter
                self.application_list_sort = application_list_sort
                toggle_renderer.connect('toggled', self.__active_pane_toggle,
                    application_list_sort)

        def __init_tree_views(self, application_list, category_list, 
            section_list, application_list_filter = None, 
            application_list_sort = None, 
            application_sort_column = enumerations.NAME_COLUMN):
                '''This function connects treeviews with their models and also applies
                filters'''
                if category_list == None:
                        self.w_application_treeview.set_model(None)
                        self.__remove_treeview_columns(self.w_application_treeview)
                elif application_list == None:
                        self.w_categories_treeview.set_model(None)
                        self.__remove_treeview_columns(self.w_categories_treeview)
                else:
                        self.__disconnect_models()
                        self.__remove_treeview_columns(self.w_application_treeview)
                        self.__remove_treeview_columns(self.w_categories_treeview)
                # The logic for set section needs to be here as some sections
                # might be not enabled. In such situation we are setting the set
                # section to "All Categories" one.
                if section_list != None:
                        row = section_list[self.set_section]
                        if row[enumerations.SECTION_ENABLED] and \
                            self.set_section >= 0 and \
                            self.set_section < len(section_list):
                                if row[enumerations.SECTION_ID] != self.set_section:
                                        self.set_section = 0
                        else:
                                self.set_section = 0

                if application_list != None:
                        self.__init_application_tree_view(application_list,
                            application_list_filter, application_list_sort, 
                            application_sort_column)

                if self.first_run:
                        # When vadj changes we need to set image descriptions
                        # on visible status icons. This catches moving the scroll bars
                        # and scrolling up and down using keyboard.
                        vadj = self.w_application_treeview.get_vadjustment()
                        vadj.connect('value-changed',
                            self.__application_treeview_vadjustment_changed, None)

                        # When the size of the application_treeview changes
                        # we need to set image descriptions on visible status icons.
                        self.w_application_treeview.connect('size-allocate',
                            self.__application_treeview_size_allocate, None)

                if category_list != None:
                        ##CATEGORIES TREEVIEW
                        category_list_filter = category_list.filter_new()
                        enumerations.CATEGORY_NAME_renderer = gtk.CellRendererText()
                        column = gtk.TreeViewColumn(_('Name'),
                            enumerations.CATEGORY_NAME_renderer,
                            markup = enumerations.CATEGORY_NAME)
                        enumerations.CATEGORY_NAME_renderer.set_property("xalign", 0.0)
                        self.w_categories_treeview.append_column(column)
                        #Added selection listener
                        category_selection = self.w_categories_treeview.get_selection()
                        category_selection.set_mode(gtk.SELECTION_SINGLE)

                if self.first_run:
                        ##FILTER COMBOBOX
                        render_pixbuf = gtk.CellRendererPixbuf()
                        self.w_filter_combobox.pack_start(render_pixbuf, expand = True)
                        self.w_filter_combobox.add_attribute(render_pixbuf, "pixbuf", 
                            enumerations.FILTER_ICON)
                        self.w_filter_combobox.set_cell_data_func(render_pixbuf,
                            self.filter_cell_data_function, enumerations.FILTER_ICON)
                        
                        cell = gtk.CellRendererText()
                        self.w_filter_combobox.pack_start(cell, True)
                        self.w_filter_combobox.add_attribute(cell, 'text',
                            enumerations.FILTER_NAME)
                        self.w_filter_combobox.set_cell_data_func(cell,
                            self.filter_cell_data_function, enumerations.FILTER_NAME)
                        self.w_filter_combobox.set_row_separator_func(
                            self.combobox_filter_id_separator)

                if section_list != None:
                        self.section_list = section_list
                if category_list != None:
                        self.category_list = category_list
                        self.category_list_filter = category_list_filter
                        self.w_categories_treeview.set_model(category_list_filter)
                if application_list != None:
                        if category_list != None:
                                self.w_filter_combobox.set_model(self.filter_list)
                                self.w_filter_combobox.set_active(self.set_show_filter)
                        self.w_application_treeview.set_model(
                            self.application_list_sort)
                        if application_list_filter == None:
                                self.application_list_filter.set_visible_func(
                                    self.__application_filter)
                if not self.in_search_mode:
                        if self.last_visible_publisher in self.category_active_paths and \
                                self.category_active_paths[self.last_visible_publisher]:
                                self.w_categories_treeview.set_cursor(
                                    self.category_active_paths[(
                                    self.last_visible_publisher)])
                        else:
                                self.w_categories_treeview.set_cursor(0)

                if self.first_run:
                        category_selection.connect("changed",
                            self.__on_category_selection_changed, None)
                        self.w_categories_treeview.connect("row-activated",
                            self.__on_category_row_activated, None)
                        self.w_categories_treeview.connect("focus-in-event",
                            self.__on_category_focus_in, None)
                        self.w_categories_treeview.connect("button_press_event",
                            self.__on_categoriestreeview_button_press_event, None)
                        self.w_categories_treeview.connect("row-collapsed",
                            self.__on_categoriestreeview_row_collapsed, None)
                        self.w_categories_treeview.connect("row-expanded",
                            self.__on_categoriestreeview_row_expanded, None)
                        self.package_selection.set_mode(gtk.SELECTION_SINGLE)
                        self.package_selection.connect("changed",
                            self.__on_package_selection_changed, None)
                if category_list != None and section_list != None:
                        self.__add_categories_to_tree(category_list, section_list)
                self.a11y_application_treeview = \
                    self.w_application_treeview.get_accessible()
                self.process_package_list_end()

        def __select_column_clicked(self, data):
                self.set_busy_cursor()
                gobject.idle_add(self.__toggle_select_all,
                    self.w_selectall_menuitem.props.sensitive)

        def __application_treeview_column_sorted(self, widget, user_data):
                self.__set_visible_status(False)

        def __init_repository_tree_view(self):
                cell = gtk.CellRendererText()
                self.w_repository_combobox.pack_start(cell, True)
                self.w_repository_combobox.add_attribute(cell, 'text',
                    enumerations.REPOSITORY_NAME)
                self.w_repository_combobox.set_row_separator_func(
                    self.combobox_id_separator)

        def __application_treeview_size_allocate(self, widget, allocation, user_data):
                # We ignore any changes in the size during initialization.
                if self.visible_status_id == 0:
                        self.visible_status_id = gobject.idle_add(
                            self.__set_visible_status)

        def __application_treeview_vadjustment_changed(self, widget, user_data):
                self.__set_visible_status()

        def __set_accessible_status(self, model, itr):
                status = model.get_value(itr, enumerations.STATUS_COLUMN)
                if status == enumerations.INSTALLED:
                        desc = _("Installed")
                elif status == enumerations.NOT_INSTALLED:
                        desc = _("Not Installed")
                elif status == enumerations.UPDATABLE:
                        desc = _("Updates Available")
                else:
                        desc = None
                if desc != None:
                        obj = self.a11y_application_treeview.ref_at(
                            int(model.get_string_from_iter(itr)),
                            STATUS_COLUMN_INDEX)
                        obj.set_image_description(desc)

        def __set_visible_status(self, check_range = True):
                self.visible_status_id = 0
                if self.w_main_view_notebook.get_current_page() != \
                    NOTEBOOK_PACKAGE_LIST_PAGE:
                        return
                if self.__doing_search():
                        return

                a11y_enabled = False
                if self.a11y_application_treeview.get_n_accessible_children() != 0:
                        a11y_enabled = True

                visible_range = self.w_application_treeview.get_visible_range()
                if visible_range == None:
                        return
                start = visible_range[0][0]
                end = visible_range[1][0]
                if debug_descriptions:
                        print "Range Start: %d End: %d" % (start, end)

                # Switching Publishers need to use default range
                if self.publisher_changed:
                        check_range = False
                        self.publisher_changed = False
                if self.in_search_mode:
                        check_range = False
                
                if self.application_treeview_range != None:
                        if check_range:
                                old_start = self.application_treeview_range[0][0]
                                old_end = self.application_treeview_range[1][0]
                                 # Old range is the same or smaller than new range
                                 # so do nothing
                                if start >= old_start and end <= old_end:
                                        return
                                if start < old_end:
                                        if end < old_end:
                                                if end >= old_start:
                                                        end = old_start
                                        else:
                                                start = old_end
                if debug_descriptions:
                        print "Adjusted Range Start: %d End: %d" % (start, end)
                self.application_treeview_range = visible_range

                sort_filt_model = \
                    self.w_application_treeview.get_model() #gtk.TreeModelSort
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore
                sf_itr = sort_filt_model.get_iter_from_string(str(start))                
                pkg_stems_and_itr_to_fetch = {}
                while start <= end:
                        filtered_itr = sort_filt_model.convert_iter_to_child_iter(None,
                            sf_itr)
                        app_itr = filt_model.convert_iter_to_child_iter(filtered_itr)

                        desc = sort_filt_model.get_value(sf_itr,
                            enumerations.DESCRIPTION_COLUMN)
                        # Only Fetch description for packages without a
                        # description
                        if desc == '...':
                                pkg_fmri = sort_filt_model.get_value(sf_itr,
                                    enumerations.FMRI_COLUMN)
                                if pkg_fmri != None:
                                        pkg_stem = pkg_fmri.get_pkg_stem(
                                            include_scheme = True)
                                        pkg_stems_and_itr_to_fetch[pkg_stem] = \
                                            model.get_string_from_iter(app_itr)
                        if a11y_enabled:
                                self.__set_accessible_status(sort_filt_model, sf_itr)
                        start += 1
                        sf_itr = sort_filt_model.iter_next(sf_itr)

                if debug_descriptions:
                        print "PKGS to FETCH: \n%s" % pkg_stems_and_itr_to_fetch
                if len(pkg_stems_and_itr_to_fetch) > 0:
                        Thread(target = self.__get_pkg_descriptions,
                            args = [pkg_stems_and_itr_to_fetch, model]).start() 
                    
        def __doing_search(self):
                return self.search_start > 0
                
        def __get_pkg_descriptions(self, pkg_stems_and_itr_to_fetch, orig_model):
                # Note: no need to aquire lock even though this can be called from
                # multiple threads, it is just creating an update job and dispatching it
                # to the idle handler, not modifying any global state
                info = None
                if not self.__doing_search():
                        gobject.idle_add(self.__update_statusbar_message,
                            _("Fetching descriptions..."))
                try:
                        info = self.api_o.info(pkg_stems_and_itr_to_fetch.keys(), False,
                                frozenset([api.PackageInfo.IDENTITY,
                                    api.PackageInfo.SUMMARY]))
                except api_errors.TransportError:
                        self.update_statusbar()
                        return
                if info and len(info.get(0)) == 0:
                        self.update_statusbar()
                        return
                pkg_infos = info.get(0)
                pkg_descriptions_for_update = []
                for pkg_info in pkg_infos:
                        short_fmri = fmri.PkgFmri(pkg_info.fmri).get_pkg_stem(
                            include_scheme = True)
                        pkg_descriptions_for_update.append((short_fmri,
                            pkg_stems_and_itr_to_fetch[short_fmri],
                            pkg_info.summary))
                if debug_descriptions:
                        print "FETCHED PKGS: \n%s" % pkg_descriptions_for_update
                gobject.idle_add(self.__update_description_from_iter,
                    pkg_descriptions_for_update, orig_model)

        def __update_description_from_iter(self, pkg_descriptions_for_update, orig_model):
                sort_filt_model = \
                    self.w_application_treeview.get_model() #gtk.TreeModelSort
                if not sort_filt_model:
                        return
                filt_model = sort_filt_model.get_model() #gtk.TreeModelFilter
                model = filt_model.get_model() #gtk.ListStore

                #If model has changed abandon description updates
                if orig_model != model:
                        return

                #If doing a search or switching sources abandon description updates
                if self.__doing_search() or self.in_setup:
                        return

                if debug_descriptions:
                        print "UPDATE DESCRIPTIONS: \n%s" % pkg_descriptions_for_update
                for pkg_stem, path, summary in pkg_descriptions_for_update:
                        itr = model.get_iter_from_string(path)
                        stored_pkg_fmri = model.get_value(itr, enumerations.FMRI_COLUMN)
                        stored_pkg_stem = stored_pkg_fmri.get_pkg_stem(
                            include_scheme = True)

                        if pkg_stem != stored_pkg_stem:
                                if debug:
                                        print ("__update_description_from_iter(): "
                                            "model not consistent so abandoning "
                                            "these description updates.")
                                self.update_statusbar()
                                return
                        model.set_value(itr, enumerations.DESCRIPTION_COLUMN, summary)
                if not self.__doing_search():
                        self.update_statusbar()

        def __create_icon_column(self, name, expand_pixbuf, enum_value, set_data_func):
                column = gtk.TreeViewColumn()
                column.set_title(name)
                #Commented, since there was funny jumping of the icons
                #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
                render_pixbuf = gtk.CellRendererPixbuf()
                column.pack_start(render_pixbuf, expand = expand_pixbuf)
                column.add_attribute(render_pixbuf, "pixbuf", enum_value)
                column.set_fixed_width(32)
                if set_data_func:
                        column.set_cell_data_func(render_pixbuf,
                            self.cell_data_function, None)
                return column

        def __disconnect_models(self):
                self.w_application_treeview.set_model(None)
                self.w_categories_treeview.set_model(None)
                self.w_filter_combobox.set_model(None)

        def __disconnect_repository_model(self):
                self.w_repository_combobox.set_model(None)

        @staticmethod
        def __status_sort_func(treemodel, iter1, iter2, user_data=None):
                get_val = treemodel.get_value
                status1 = get_val(iter1, enumerations.STATUS_COLUMN)
                status2 = get_val(iter2, enumerations.STATUS_COLUMN)
                return cmp(status1, status2)

        @staticmethod
        def __remove_treeview_columns(treeview):
                columns = treeview.get_columns()
                if columns:
                        for column in columns:
                                treeview.remove_column(column)

        @staticmethod
        def __init_sections(section_list):
                '''This function is for initializing the sections list'''
                enabled = True
                # Only enable the first section. Later other sections are enabled
                # in __add_category_to_section() if the section contains any categories
                # which in turn contain some packages.
                section_list.append([0, _('All Categories'), enabled ])
                enabled = False
                section_list.append([1, _('Meta Packages'), enabled ])
                section_list.append([2, _('Applications'), enabled ])
                section_list.append([3, _('Desktop (GNOME)'), enabled ])
                section_list.append([4, _('Development'), enabled ])
                section_list.append([5, _('Distributions'), enabled ])
                section_list.append([6, _('Drivers'), enabled ])
                section_list.append([7, _('System'), enabled ])
                section_list.append([8, _('Web Services'), enabled ])

        def __init_show_filter(self):
                max_length = 0
                for filter_id, pixbuf, label in self.filter_options:
                        self.filter_list.append([filter_id, pixbuf, label, ])
                        if filter_id == -1:
                                continue
                        max_length = self.__get_max_text_length(
                            max_length, label, self.w_filter_combobox)
                
                if self.initial_show_filter >= enumerations.FILTER_ALL and \
                    self.initial_show_filter < len(self.filter_list):
                        row = self.filter_list[self.initial_show_filter]
                        if row[enumerations.SECTION_ID] != self.initial_show_filter:
                                self.initial_show_filter = enumerations.FILTER_ALL
                else:
                        self.initial_show_filter = enumerations.FILTER_ALL
                return max_length

        @staticmethod
        def __get_max_text_length(length_to_check, text, widget):
                if widget == None:
                        return 0
                context = widget.get_pango_context()
                metrics = context.get_metrics(context.get_font_description())
                current_length = pango.PIXELS(
                    metrics.get_approximate_char_width() * len(text))
                if current_length > length_to_check:
                        return current_length
                else:
                        return length_to_check

        def __on_mainwindow_key_press_event(self, widget, event):
                if self.is_busy_cursor_set():
                        return True
                else:
                        return False

        def __on_mainwindow_delete_event(self, widget, event):
                ''' handler for delete event of the main window '''
                if self.__check_if_something_was_changed() == True:
                        # XXX Change this to not quit and show dialog
                        # XXX if some changes were applied:
                        self.__main_application_quit()
                        return True
                else:
                        self.__main_application_quit()

        def __on_mainwindow_check_resize(self, widget):
                if widget and self.gdk_window:
                        status_height = self.w_statusbar_hbox.get_allocation().height
                        self.gdk_window.move_resize(0, 0, widget.get_size()[0],
                            widget.get_size()[1]-status_height)

        def __on_api_search_error_delete_event(self, widget, event):
                self.__on_api_search_button_clicked(None)

        def __on_api_search_button_clicked(self, widget):
                self.api_search_error_dialog.hide()

        def __on_file_quit_activate(self, widget):
                ''' handler for quit menu event '''
                self.__on_mainwindow_delete_event(None, None)

        def __on_ua_completed_close(self, widget):
                self.w_ua_completed_dialog.hide()
                self.__on_mainwindow_delete_event(None, None)

        def __on_edit_repositories_activate(self, widget):
                ''' handler for repository menu event '''
                repository.Repository(self)

        def __on_file_be_activate(self, widget):
                ''' handler for be menu event '''
                beadm.Beadmin(self)

        def __on_searchentry_changed(self, widget):
                if widget.get_text_length() > 0 and \
                        self.search_text_style != enumerations.SEARCH_STYLE_PROMPT:
                        if self.entry_embedded_icons_supported:
                                self.w_searchentry.set_property("secondary-icon-stock", 
                                    gtk.STOCK_CANCEL)
                                self.w_searchentry.set_property(
                                   "secondary-icon-sensitive", True)
                        self.w_clear_search_menuitem.set_sensitive(True)
                else:
                        if self.entry_embedded_icons_supported:
                                self.w_searchentry.set_property("secondary-icon-stock", 
                                    None)
                        self.w_clear_search_menuitem.set_sensitive(False)
                self.__enable_disable_entry_selection(widget)

        def __update_statusbar_for_search(self):
                if self.is_all_publishers:
                        self.__update_statusbar_message(_("Search all sources"))
                else:
                        self.__update_statusbar_message(_("Search current source"))

        def __update_statusbar_message(self, message):
                if self.statusbar_message_id > 0:
                        self.w_main_statusbar.remove(0, self.statusbar_message_id)
                        self.statusbar_message_id = 0
                self.statusbar_message_id = self.w_main_statusbar.push(0, message)

        def __setup_before_all_publishers_mode(self):
                self.is_all_publishers = True
                self.w_infosearch_frame.hide()

                self.__save_setup_before_search()
                self.__clear_before_search()
                self.__update_statusbar_for_search()

        def __clear_before_search(self):
                self.in_setup = True
                application_list = self.__get_new_application_liststore()
                self.__set_empty_details_panel()
                self.__set_main_view_package_list()
                self.__init_tree_views(application_list, None, None)
                self.__unselect_category()

        def __restore_setup_for_browse(self):
                self.in_search_mode = False
                self.is_all_publishers = False
                self.w_infosearch_frame.hide()
                self.set_busy_cursor()
                self.w_repository_combobox.set_active(
                    self.saved_repository_combobox_active)
                self.set_section = self.saved_section_active
                if self.saved_category_list == self.category_list:
                        self.__init_tree_views(self.saved_application_list,
                            None, None,
                            self.saved_application_list_filter,
                            self.saved_application_list_sort)
                else:
                        self.__init_tree_views(self.saved_application_list,
                            self.saved_category_list, self.saved_section_list,
                            self.saved_application_list_filter,
                            self.saved_application_list_sort)
                        
                self.__set_main_view_package_list()

        def __save_setup_before_search(self, single_search=False):
                #Do not save search data models
                if self.in_search_mode:
                        return
                selected_section, selected_category = \
                        self.__get_active_section_and_category()
                self.pylintstub = selected_category
                self.saved_section_active = selected_section
                self.saved_application_list = self.application_list
                self.saved_application_list_sort = \
                        self.application_list_sort
                self.saved_application_list_filter = \
                        self.application_list_filter
                self.saved_category_list = self.category_list
                self.saved_section_list = self.section_list

                pub_index = self.w_repository_combobox.get_active()
                if pub_index != self.repo_combobox_all_pubs_index and \
                        pub_index != self.repo_combobox_add_index:
                        self.saved_repository_combobox_active = pub_index

        def __do_search(self, widget=None, ev=None):
                self.search_start = 0
                if self.w_searchentry.get_text_length() == 0:
                        return
                if self.w_searchentry.get_text() == "*":
                        if self.in_search_mode:
                                self.__unset_search(True)
                        self.w_categories_treeview.set_cursor(0)
                        return
                if not self.is_all_publishers:
                        self.__save_setup_before_search(single_search=True)
                self.__clear_before_search()
                self.set_busy_cursor()
                self.in_search_mode = True
                        
                self.w_infosearch_frame.hide()
                self.__update_statusbar_message(_("Searching..."))
                Thread(target = self.__do_api_search,
                    args = (self.is_all_publishers, )).start()

        def __get_selection_and_category_path(self):
                selection = self.w_categories_treeview.get_selection()
                if not selection:
                        return None, (0,)
                model, itr = selection.get_selected()
                if not model or not itr:
                        return None, (0,)
                return selection, model.get_path(itr)

        def __unselect_category(self):
                selection, path = self.__get_selection_and_category_path()
                if selection:
                        self.category_active_paths[self.last_visible_publisher] = path
                        selection.unselect_all()

        def __process_after_search_failure(self):
                self.search_start = 0
                self.search_time_sec = 0
                self.application_list = []
                self.update_statusbar()
                self.unset_busy_cursor()
                self.in_setup = False

        @staticmethod
        def __get_origin_uri(repo):
                if repo == None:
                        return None
                origin_uri = repo.origins[0]
                ret_uri = None
                if isinstance(origin_uri, str):
                        if len(origin_uri) > 0:
                                ret_uri = origin_uri.strip("/")
                elif isinstance(origin_uri, publisher.RepositoryURI):
                        uri = origin_uri.uri
                        if uri != None and len(uri) > 0:
                                ret_uri = uri.strip("/")
                return ret_uri


        def __do_api_search(self, search_all = True):
                self.search_start = time.time()
                self.search_time_sec = 0
                text = self.w_searchentry.get_text()
                # Here we call the search API to get the results
                searches = []
                servers = []
                result = []
                pargs = []
                search_str = SEARCH_STR_FORMAT % text
                pargs.append(search_str)
                if search_all:
                        servers = None
                else:
                        pub_prefix = self.__get_selected_publisher()
                        if pub_prefix != None:
                                pub = self.api_o.get_publisher(prefix=pub_prefix)
                        else:
                                pub = self.api_o.get_preferred_publisher()
                        origin_uri = self.__get_origin_uri(pub.selected_repository)
                        servers.append({"origin": origin_uri})
                if debug:
                        print "Search: pargs %s servers: %s" % (pargs, servers)

                #TBD If we ever search just Installed pkgs should allow for a local search
                case_sensitive = False
                return_actions = True
                searches.append(self.api_o.remote_search(
                    [api.Query(" ".join(pargs), case_sensitive, return_actions)],
                    servers=servers))
                if debug:
                        print "Search Args: %s : cs: %s : retact: %s" % \
                                ("".join(pargs), case_sensitive, return_actions)

                last_name = ""
                self.search_all_pub_being_searched = None

                # Sorting results by Name gives best overall appearance and flow
                sort_col = enumerations.NAME_COLUMN
                try:
                        for query_num, pub, (v, return_type, tmp) in \
                            itertools.chain(*searches):
                                if v < 1 or return_type != api.Query.RETURN_PACKAGES:
                                        self.__process_after_search_failure()
                                        return

                                active_pub = None
                                if pub is not None \
                                    and "prefix" in pub:
                                        active_pub = pub["prefix"]
                                name = fmri.PkgFmri(str(tmp)).get_name()
                                if last_name != name:
                                        if debug:
                                                print "Result Name: %s (%s)" \
                                                    % (name, active_pub)
                                        a_res = name, active_pub
                                        result.append(a_res)
                                        #Ignore Status when fetching
                                        application_list = \
                                                self.__get_min_list_from_search(result)
                                        self.search_all_pub_being_searched = active_pub
                                        self.in_setup = True
                                        gobject.idle_add(self.__init_tree_views, 
                                            application_list, None, None, None, None,
                                            sort_col)
                                last_name = name
                                self.pylintstub = query_num
                except api_errors.ProblematicSearchServers, ex:
                        self.__process_api_search_error(ex)
                        gobject.idle_add(self.__handle_api_search_error)
                        if len(result) == 0:
                                self.__process_after_search_with_zero_results()
                                return
                except api_errors.CanceledException:
                        # TBD. Currently search is not cancelable
                        # so this should not happen, but the logic is in place
                        # to support cancelable search.
                        self.unset_busy_cursor()
                        return
                except Exception, ex:
                        # We are not interested in this error
                        self.__process_after_search_failure()
                        return
                if debug:
                        print "Number of search results:", len(result)
                if len(result) == 0:
                        if debug:
                                print "No search results"
                        self.__process_after_search_with_zero_results()
                        return
                # We cannot get status of the packages if catalogs have not
                # been loaded so we pause for up to 5 seconds here to
                # allow catalogs to be loaded
                times = 5
                while self.catalog_loaded == False:
                        if times == 0:
                                break
                        time.sleep(1)
                        times -= 1

                #Now fetch full result set with Status
                self.in_setup = True
                application_list = self.__get_full_list_from_search(result)
                gobject.idle_add(self.__init_tree_views, application_list, None, None, \
                    None, None, sort_col)

                if self.search_start > 0:
                        self.search_time_sec = int(time.time() - self.search_start)
                        if debug:
                                print "Search time: %d (sec)" % self.search_time_sec
                self.search_start = 0

        def __process_after_search_with_zero_results(self):
                if self.search_start > 0:
                        self.search_time_sec = int(time.time() - self.search_start)
                self.search_start = 0
                self.in_setup = True
                application_list = self.__get_new_application_liststore()
                gobject.idle_add(self.__set_empty_details_panel)
                gobject.idle_add(self.__set_main_view_package_list)
                gobject.idle_add(self.__init_tree_views, application_list, None, None)

        def __get_min_list_from_search(self, search_result):
                application_list = self.__get_new_application_liststore()
                for name, pub in search_result:
                        application_list.append(
                            [False, None, name, '...', enumerations.NOT_INSTALLED, None, 
                            "pkg://" + pub + "/" + name, None, True, None, 
                            pub])
                return application_list

        def __get_full_list_from_search(self, search_result):
                application_list = self.__get_new_application_liststore()
                self.__add_pkgs_to_list_from_search(search_result,
                    application_list)
                return application_list

        def __add_pkgs_to_list_from_search(self, search_result,
            application_list):
                pargs = []
                for name, pub in search_result:
                        pargs.append("pkg://" + pub + "/" + name)
                # We now need to get the status for each package
                if debug_descriptions:
                        print "pargs:", pargs
                try:
                        pkgs_known = self.__get_inventory_list(pargs,
                            True, True)
                except api_errors.InventoryException:
                        # This can happen if load_catalogs has not been run
                        err = _("Unable to get status for search results.\n"
                            "The catalogs have not been loaded.\n"
                            "Please try after few seconds.\n")
                        gobject.idle_add(self.error_occurred, err)
                        return
                return self.__add_pkgs_to_lists(pkgs_known, application_list,
                    None, None)

        def __application_refilter(self):
                ''' Disconnecting the model from the treeview improves
                performance when assistive technologies are enabled'''
                if self.in_setup:
                        return
                self.application_refilter_id = 0
                self.application_refilter_idle_id = 0
                model = self.w_application_treeview.get_model()
                self.w_application_treeview.set_model(None)
                self.application_list_filter.refilter()
                self.w_application_treeview.set_model(model)
                gobject.idle_add(self.__set_empty_details_panel)
                gobject.idle_add(self.__enable_disable_selection_menus)
                gobject.idle_add(self.__enable_disable_install_remove)
                self.application_treeview_initialized = True
                self.application_treeview_range = None
                if self.visible_status_id == 0:
                        self.visible_status_id = gobject.idle_add(
                            self.__set_visible_status)
                self.categories_treeview_initialized = True
                self.categories_treeview_range = None
                len_filtered_list = len(self.application_list_filter)
                if len_filtered_list > 0 and \
                        self.length_visible_list != len_filtered_list:
                        self.update_statusbar()
                return False

        def __on_edit_paste(self, widget):
                self.w_searchentry.paste_clipboard()

        def __on_delete(self, widget):
                bounds = self.w_searchentry.get_selection_bounds()
                self.w_searchentry.delete_text(bounds[0], bounds[1])
                return

        def __on_copy(self, widget):
                focus_widget = self.w_main_window.get_focus()
                if focus_widget == self.w_searchentry:
                        self.w_searchentry.copy_clipboard()
                        self.w_paste_menuitem.set_sensitive(True)
                elif self.__is_a_textview(focus_widget):
                        focus_widget.get_buffer().copy_clipboard(
                            self.w_main_clipboard)

        def __on_cut(self, widget):
                self.w_searchentry.cut_clipboard()
                self.w_paste_menuitem.set_sensitive(True)

        def __on_goto_list_clicked(self, widget):
                self.__set_main_view_package_list()
                self.w_application_treeview.grab_focus()

        def __on_edit_search_clicked(self, widget):
                self.w_searchentry.grab_focus()

        def __on_clear_search(self, widget, icon_pos=0, event=None):
                self.w_searchentry.set_text("")
                # Only clear out search results
                if self.in_search_mode or self.is_all_publishers:
                        self.__clear_before_search()
                        self.__update_statusbar_message(_("Search cleared"))
                return

        def __on_progress_cancel_clicked(self, widget):
                Thread(target = self.api_o.cancel, args = ()).start()

        def __on_startpage(self, widget):
                self.__load_startpage()
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)

        def __on_notebook_change(self, widget, event, pagenum):
                if (pagenum == INFO_NOTEBOOK_LICENSE_PAGE and 
                    not self.showing_empty_details):
                        licbuffer = self.w_license_textview.get_buffer()
                        leg_txt = _("Fetching legal information...")
                        licbuffer.set_text(leg_txt)
                        if self.show_licenses_id != 0:
                                gobject.source_remove(self.show_licenses_id)
                                self.show_licenses_id = 0
                        self.last_show_licenses_id = self.show_licenses_id = \
                            gobject.timeout_add(SHOW_LICENSE_DELAY,
                                self.__show_licenses)

        def __is_a_textview(self, widget):
                if (widget == self.w_generalinfo_textview or
                    widget == self.w_installedfiles_textview or
                    widget == self.w_dependencies_textview or
                    widget == self.w_license_textview):
                        return True
                else:
                        return False

        def __toggle_select_all(self, select_all=True):
                focus_widget = self.w_main_window.get_focus()
                if self.__is_a_textview(focus_widget):
                        focus_widget.emit('select-all', select_all)
                        self.w_selectall_menuitem.set_sensitive(False)
                        self.w_deselect_menuitem.set_sensitive(True)
                        self.unset_busy_cursor()
                        return
                elif focus_widget == self.w_searchentry:
                        if select_all:
                                focus_widget.select_region(0, -1)
                        else:
                                focus_widget.select_region(0, 0)
                        self.w_selectall_menuitem.set_sensitive(False)
                        self.w_deselect_menuitem.set_sensitive(True)
                        self.unset_busy_cursor()
                        return

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
                        if select_all:
                                list_of_paths.append(path)
                        else:
                                filtered_iter = \
                                        sort_filt_model.convert_iter_to_child_iter(None,
                                            iter_next)
                                app_iter = filt_model.convert_iter_to_child_iter(
                                    filtered_iter)
                                if model.get_value(app_iter, enumerations.MARK_COLUMN):
                                        list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        itr = model.get_iter(path)
                        mark_value = model.get_value(itr, enumerations.MARK_COLUMN)
                        if select_all and not mark_value:
                                model.set_value(itr, enumerations.MARK_COLUMN, True)
                                pkg_stem = model.get_value(itr,
                                    enumerations.STEM_COLUMN)
                                pkg_status = model.get_value(itr,
                                    enumerations.STATUS_COLUMN)
                                self.__add_pkg_stem_to_list(pkg_stem, pkg_status)
                        elif not select_all and mark_value:
                                model.set_value(itr, enumerations.MARK_COLUMN, False)
                                self.__remove_pkg_stem_from_list(model.get_value(itr,
                                    enumerations.STEM_COLUMN))
                
                self.w_selectall_menuitem.set_sensitive(not select_all)
                self.w_deselect_menuitem.set_sensitive(select_all)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_remove()
                self.unset_busy_cursor()
                        
        def __on_select_all(self, widget):
                self.set_busy_cursor()
                gobject.idle_add(self.__toggle_select_all, True)
                return

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
                            enumerations.STATUS_COLUMN) == enumerations.UPDATABLE:
                                list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        itr = model.get_iter(path)
                        model.set_value(itr, enumerations.MARK_COLUMN, True)
                        pkg_stem = model.get_value(itr, enumerations.STEM_COLUMN)
                        pkg_status = model.get_value(itr, enumerations.STATUS_COLUMN)
                        self.__add_pkg_stem_to_list(pkg_stem, pkg_status)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_remove()

        def __on_deselect(self, widget):
                self.set_busy_cursor()
                gobject.idle_add(self.__toggle_select_all, False)
                return

        def __on_preferences(self, widget):
                self.w_startpage_checkbutton.set_active(self.show_startpage)
                self.w_preferencesdialog.show()

        def __on_preferencesclose_clicked(self, widget):
                self.w_preferencesdialog.hide()

        @staticmethod
        def __on_preferenceshelp_clicked(widget):
                gui_misc.display_help("pm_win")

        def __on_startpage_checkbutton_toggled(self, widget):
                self.show_startpage = self.w_startpage_checkbutton.get_active()
                try:
                        self.client.set_bool(SHOW_STARTPAGE_PREFERENCES,
                            self.show_startpage)
                except GError:
                        pass

        def __on_api_search_checkbox_toggled(self, widget):
                active = self.api_search_checkbox.get_active()
                if len(self.current_repos_with_search_errors) > 0:
                        if active:
                                for pub, err_type, err_str in \
                                        self.current_repos_with_search_errors:
                                        if pub not in self.gconf_not_show_repos:
                                                self.gconf_not_show_repos += pub + ","
                                        self.pylintstub = err_type
                                        self.pylintstub = err_str
                        else:
                                for pub, err_type, err_str in \
                                        self.current_repos_with_search_errors:
                                        self.gconf_not_show_repos = \
                                            self.gconf_not_show_repos.replace(
                                            pub + ",", "")
                        try:
                                self.client.set_string(API_SEARCH_ERROR_PREFERENCES,
                                    self.gconf_not_show_repos)
                        except GError:
                                pass

        def __on_searchentry_focus_in(self, widget, event):
                self.__set_search_text_mode(enumerations.SEARCH_STYLE_NORMAL)
                if self.w_main_clipboard.wait_is_text_available():
                        self.w_paste_menuitem.set_sensitive(True)
                char_count = widget.get_text_length()
                if char_count > 0:
                        self.w_selectall_menuitem.set_sensitive(True)
                else:
                        self.w_selectall_menuitem.set_sensitive(False)
                bounds = widget.get_selection_bounds()
                if bounds:
                        offset1 = bounds[0]
                        offset2 = bounds[1] 
                        if abs(offset2 - offset1) == char_count:
                                self.w_selectall_menuitem.set_sensitive(False)
                        self.w_deselect_menuitem.set_sensitive(True)
                        self.w_copy_menuitem.set_sensitive(True)
                else:
                        self.w_deselect_menuitem.set_sensitive(False)

        def __on_searchentry_focus_out(self, widget, event):
                if self.w_searchentry.get_text_length() == 0:
                        self.__set_search_text_mode(enumerations.SEARCH_STYLE_PROMPT)
                self.w_paste_menuitem.set_sensitive(False)
                self.__enable_disable_select_all()
                self.__enable_disable_deselect()
                self.w_cut_menuitem.set_sensitive(False)
                self.w_copy_menuitem.set_sensitive(False)
                self.w_delete_menuitem.set_sensitive(False)
                return False

        def __on_searchentry_selection(self, widget, pspec):
                self.__enable_disable_entry_selection(widget)

        def __enable_disable_entry_selection(self, widget):
                char_count = widget.get_text_length()
                bounds = widget.get_selection_bounds()
                if bounds:
                        #enable selection functions
                        self.w_cut_menuitem.set_sensitive(True)
                        self.w_copy_menuitem.set_sensitive(True)
                        self.w_delete_menuitem.set_sensitive(True)
                        if char_count == abs(bounds[1] - bounds[0]):
                                self.w_selectall_menuitem.set_sensitive(False)
                        else:
                                self.w_selectall_menuitem.set_sensitive(True)
                        self.w_deselect_menuitem.set_sensitive(True)
                else:
                        self.w_cut_menuitem.set_sensitive(False)
                        self.w_copy_menuitem.set_sensitive(False)
                        self.w_delete_menuitem.set_sensitive(False)
                        self.w_deselect_menuitem.set_sensitive(False)
                        if char_count == 0:
                                self.w_selectall_menuitem.set_sensitive(False)
                        else:
                                self.w_selectall_menuitem.set_sensitive(True)

        def __refilter_on_idle(self):
                if self.application_refilter_id != 0:
                        gobject.source_remove(self.application_refilter_id)
                        self.application_refilter_id = 0
                if self.application_refilter_idle_id == 0:
                        self.application_refilter_idle_id = gobject.idle_add(
                            self.__application_refilter)

        def __on_category_focus_in(self, widget, event, user):
                self.__on_category_row_activated(None, None, None, user)

        def __on_category_row_activated(self, view, path, col, user):
                '''This function is for handling category double click activations'''
                if self.w_filter_combobox.get_model():
                        self.w_filter_combobox.set_active(
                            self.saved_filter_combobox_active)
                if self.in_search_mode or self.is_all_publishers:
                        self.__unset_search(True)
                        if self.selected == 0:
                                gobject.idle_add(self.__enable_disable_install_remove)
                        return
                self.__set_main_view_package_list()
                self.set_busy_cursor()
                self.__refilter_on_idle()
                if self.selected == 0:
                        gobject.idle_add(self.__enable_disable_install_remove)

        def __set_main_view_package_list(self):
                # Only switch from Start Page View to List view if we are not in startup
                if not self.in_startpage_startup:
                        self.w_main_view_notebook.set_current_page(
                                NOTEBOOK_PACKAGE_LIST_PAGE)

        def __on_categoriestreeview_row_collapsed(self, treeview, itr, path, data):
                self.w_categories_treeview.set_cursor(path)
                self.category_expanded_paths[(self.last_visible_publisher, path)] = 0
                self.category_active_paths[self.last_visible_publisher] = path
                
        def __on_categoriestreeview_row_expanded(self, treeview, itr, path, data):
                if self.in_setup and not self.first_run:
                        return
                self.w_categories_treeview.set_cursor(path)
                self.category_expanded_paths[(self.last_visible_publisher, path)] = 1
                self.category_active_paths[self.last_visible_publisher] = path

        def __on_categoriestreeview_button_press_event(self, treeview, event, data):
                if event.type != gtk.gdk.BUTTON_PRESS:
                        return 1
                x = int(event.x)
                y = int(event.y)
                pthinfo = treeview.get_path_at_pos(x, y)
                if pthinfo is not None:
                        path = pthinfo[0]
                        cellx = pthinfo[2]
                        #Ignore clicks on row toggle icon which is 16 pixels wide
                        if cellx <= 16:
                                return
                        #Collapse expand Top level Sections only
                        tree_view = self.w_categories_treeview
                        if path != 0 and len(path) == 1:
                                if tree_view.row_expanded(path) and \
                                        self.w_main_view_notebook.get_current_page() == \
                                        NOTEBOOK_START_PAGE:
                                        self.__on_category_selection_changed(
                                            tree_view.get_selection(), None)
                                elif tree_view.row_expanded(path):
                                        selection, sel_path = \
                                                self.__get_selection_and_category_path()
                                        if selection and sel_path == path:
                                                tree_view.collapse_row(path)
                                else:
                                        tree_view.expand_row(path, False)
                                self.category_active_paths[self.last_visible_publisher]\
                                        = path

        def __on_category_selection_changed(self, selection, widget):
                '''This function is for handling category selection changes'''
                if self.in_setup:
                        return
                model, itr = selection.get_selected()
                if itr:
                        self.category_active_paths[self.last_visible_publisher] = \
                                model.get_path(itr)
                if self.in_search_mode or self.is_all_publishers:
                        return
                if self.saved_filter_combobox_active != None:
                        self.w_filter_combobox.set_active(
                            self.saved_filter_combobox_active)
                self.__set_main_view_package_list()

                self.set_busy_cursor()
                self.__refilter_on_idle()
                if self.selected == 0:
                        gobject.idle_add(self.__enable_disable_install_remove)

        def __on_applicationtreeview_motion_events(self, treeview, event):
                if event.state == gtk.gdk.CONTROL_MASK or \
                        event.state == gtk.gdk.SHIFT_MASK or \
                        event.state == gtk.gdk.MOD1_MASK or \
                        event.state == gtk.gdk.BUTTON1_MASK or \
                        event.state == gtk.gdk.BUTTON2_MASK or \
                        event.state == gtk.gdk.BUTTON3_MASK:
                        return
                info = treeview.get_path_at_pos(int(event.x), int(event.y))
                if not info:
                        return 
                self.__show_app_column_tooltip(treeview, _("Status"), info[0], info[1])

        def __show_app_column_tooltip(self, treeview, col_title, path, col):
                self.applicationtreeview_tooltips = gtk.Tooltips()
                tip = ""
                if path and col:
                        title = col.get_title() 
                        if title != col_title:
                                self.applicationtreeview_tooltips.set_tip(treeview, tip)
                                self.applicationtreeview_tooltips.disable()
                                return
                        row = list(treeview.get_model()[path])
                        if row:
                                status = row[enumerations.STATUS_COLUMN]
                                if status == enumerations.INSTALLED:
                                        tip = _("Installed")
                                elif status == enumerations.NOT_INSTALLED:
                                        tip = _("Not installed")
                                elif status == enumerations.UPDATABLE:
                                        tip = _("Updates Available")

                self.applicationtreeview_tooltips.set_tip(treeview, tip)
                if tip != "":
                        self.applicationtreeview_tooltips.enable()
                else:
                        self.applicationtreeview_tooltips.disable()

        def __on_applicationtreeview_button_and_key_events(self, treeview, event):
                if event.type == gtk.gdk.KEY_PRESS:
                        keyname = gtk.gdk.keyval_name(event.keyval)
                        if event.state == gtk.gdk.CONTROL_MASK and keyname == "F1":
                                return True #Disable Tooltip popup using Ctrl-F1

                        if not(event.state == gtk.gdk.SHIFT_MASK and keyname == "F10"):
                                return

                        selection = self.w_application_treeview.get_selection()
                        if not selection:
                                return
                        model, itr = selection.get_selected()
                        if not model or not itr:
                                return
                        curr_time = event.time
                        path = model.get_path(itr)
                        col = treeview.get_column(1) # NAME_COLUMN
                        treeview.set_cursor(path, col, 0)

                        #Calculate popup coordinates
                        treecell_rect = treeview.get_cell_area(path, col)
                        rx, ry = treeview.tree_to_widget_coords(treecell_rect[0],
                            treecell_rect[1])
                        winx, winy  = treeview.get_bin_window().get_origin()
                        winx += rx
                        winy += ry
                        popup_position = (winx, winy)
                        self.w_package_menu.popup( None, None,
                            self.__position_package_popup, gtk.gdk.KEY_PRESS,
                            curr_time, popup_position)
                        return

                if event.type != gtk.gdk.BUTTON_PRESS and event.type != 5:
                        return
                x = int(event.x)
                y = int(event.y)
                pthinfo = treeview.get_path_at_pos(x, y)
                if pthinfo == None:
                        return                
                path = pthinfo[0]
                col = pthinfo[1]

                #Double click
                if event.type == GDK_2BUTTON_PRESS:
                        self.__active_pane_toggle(None, path, treeview.get_model())
                        return                          
                if event.button == GDK_RIGHT_BUTTON: #Right Click
                        curr_time = event.time
                        treeview.grab_focus()
                        treeview.set_cursor( path, col, 0)
                        self.w_package_menu.popup( None, None, None, event.button,
                            curr_time)
                        return

        @staticmethod
        def __position_package_popup(menu, position):
                #Positions popup relative to the top left corner of the currently
                #selected row's Name cell
                x, y = position

                #Offset x by 10 and y by 15 so underlying name is visible
                return (x+10, y+15, True)

        @staticmethod
        def __on_applicationtreeview_motion_notify_event(treeview, event):
                #TBD - needed for Tooltips in application treeview
                return
                
                
        def __process_package_selection(self):
                model, itr = self.package_selection.get_selected()
                if self.show_info_id != 0:
                        gobject.source_remove(self.show_info_id)
                        self.show_info_id = 0
                if itr:
                        self.__enable_disable_install_remove()
                        self.selected_pkgstem = \
                               model.get_value(itr, enumerations.STEM_COLUMN)
                        pkg = model.get_value(itr, enumerations.FMRI_COLUMN)
                        gobject.idle_add(self.__show_fetching_package_info, pkg)
                        self.showing_empty_details = False
                        self.last_show_info_id = self.show_info_id = \
                            gobject.timeout_add(SHOW_INFO_DELAY,
                                self.__show_info, model, model.get_path(itr))
                        if (self.w_info_notebook.get_current_page() == 
                            INFO_NOTEBOOK_LICENSE_PAGE):
                                self.__on_notebook_change(None, None, 
                                    INFO_NOTEBOOK_LICENSE_PAGE)
                else:
                        self.selected_model = None
                        self.selected_path = None
                        self.selected_pkgstem = None

        def __on_package_selection_changed(self, selection, widget):
                '''This function is for handling package selection changes'''
                if self.in_setup:
                        return
                self.__process_package_selection()

        def __on_filtercombobox_changed(self, widget):
                '''On filter combobox changed'''
                if self.in_setup:
                        return
                active = self.w_filter_combobox.get_active()
                if active != enumerations.FILTER_SELECTED:
                        self.saved_filter_combobox_active = active
                self.__set_main_view_package_list()
                self.set_busy_cursor()
                self.__refilter_on_idle()
                if self.selected == 0:
                        gobject.idle_add(self.__enable_disable_install_remove)

        def __unset_search(self, same_repo):
                self.w_infosearch_frame.hide()
                selected_publisher = self.__get_selected_publisher()
                if selected_publisher in self.selected_pkgs:
                        self.selected_pkgs.pop(selected_publisher)
                if selected_publisher in self.to_install_update:
                        self.to_install_update.pop(selected_publisher)
                if selected_publisher in self.to_remove:
                        self.to_remove.pop(selected_publisher)
                self.__update_tooltips()
                self.in_search_mode = False
                self.is_all_publishers = False
                if same_repo:
                        self.__restore_setup_for_browse()

        def __on_repositorycombobox_changed(self, widget):
                '''On repository combobox changed'''
                selected_publisher = self.__get_selected_publisher()
                index =  self.w_repository_combobox.get_active()
                if self.is_all_publishers:
                        if index == self.repo_combobox_all_pubs_index:
                                return
                        if index == self.repo_combobox_add_index:
                                self.w_repository_combobox.set_active(
                                    self.repo_combobox_all_pubs_index)
                                self.__on_edit_repositories_activate(None)
                                return
                        same_repo = self.saved_repository_combobox_active == index
                        self.__unset_search(same_repo)
                        if same_repo:
                                return
                        self.w_repository_combobox.set_active(index)
                        selected_publisher = self.__get_selected_publisher()
                if selected_publisher == self.last_visible_publisher:
                        return
                if index == self.repo_combobox_all_pubs_index:
                        self.__set_all_publishers_mode()
                        return
                        
                if index == self.repo_combobox_add_index:
                        index = -1
                        model = self.w_repository_combobox.get_model()
                        for entry in model:
                                if entry[1] == self.last_visible_publisher:
                                        index = entry[0]
                                        break
                        self.w_repository_combobox.set_active(index)
                        self.__on_edit_repositories_activate(None)
                        return
                self.cancelled = True
                self.in_setup = True
                self.set_busy_cursor()
                self.__set_empty_details_panel()
                if self.in_search_mode:
                        self.__unset_search(False)

                pub = [selected_publisher, ]
                self.set_show_filter = self.initial_show_filter
                self.set_section = self.initial_section
                Thread(target = self.__setup_publisher, args = [pub]).start()
                self.__set_main_view_package_list()

        def __get_selected_publisher(self):
                pub_iter = self.w_repository_combobox.get_active_iter()
                if pub_iter == None:
                        return None
                return self.repositories_list.get_value(pub_iter, \
                            enumerations.REPOSITORY_NAME)

        def __setup_publisher(self, publishers):
                self.saved_filter_combobox_active = self.initial_show_filter
                application_list, category_list , section_list = \
                    self.__get_application_categories_lists(publishers)
                self.__unset_saved()
                self.publisher_changed = True
                self.last_visible_publisher = self.__get_selected_publisher()
                self.saved_repository_combobox_active = \
                        self.w_repository_combobox.get_active()   
                gobject.idle_add(self.__init_tree_views, application_list,
                    category_list, section_list)

        def __unset_saved(self):
                self.saved_application_list = None
                self.saved_application_list_filter = None
                self.saved_application_list_sort = None
                self.saved_category_list = None
                self.saved_section_list = None

        def __refresh_for_publisher(self, pub):
                status_str = _("Refreshing package catalog information")
                gobject.idle_add(self.__update_statusbar_message,
                    status_str)
                try:
                        self.api_o.refresh(pubs=[pub])
                except api_errors.CatalogRefreshException, cre:
                        self.__catalog_refresh_message(cre)
                except api_errors.InvalidDepotResponseException, idrex:
                        err = str(idrex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                except api_errors.ApiException, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)

        def __get_application_categories_lists(self, publishers):
                application_list = self.__get_new_application_liststore()
                category_list = self.__get_new_category_liststore()
                section_list = self.__get_new_section_liststore()
                for pub in publishers:
                        uptodate = False
                        try:
                                uptodate = self.__check_if_cache_uptodate(pub)
                                if uptodate:
                                        self.__add_pkgs_to_lists_from_cache(pub,
                                            application_list, category_list,
                                            section_list)
                        except (UnpicklingError, EOFError, IOError):
                                #Most likely cache is corrupted, silently load list
                                #from api.
                                application_list = self.__get_new_application_liststore()
                                category_list = self.__get_new_category_liststore()
                                uptodate = False
                        if not uptodate:
                                self.__refresh_for_publisher(pub)
                                self.__add_pkgs_to_lists_from_api(pub,
                                    application_list, category_list, section_list)
                                category_list.prepend(None, [0, _('All'), None, None])
                        if self.application_list and self.category_list and \
                            not self.last_visible_publisher_uptodate:
                                status_str = _("Loading package list")
                                gobject.idle_add(self.__update_statusbar_message,
                                    status_str)
                                if self.last_visible_publisher:
                                        dump_list = self.application_list
                                        if self.saved_application_list != None:
                                                dump_list = \
                                                    self.saved_application_list
                                        self.__dump_datamodels(
                                            self.last_visible_publisher, dump_list,
                                            self.category_list, self.section_list)
                        self.last_visible_publisher_uptodate = uptodate
                return application_list, category_list, section_list

        def __check_if_cache_uptodate(self, pub):
                if self.cache_o:
                        uptodate = self.cache_o.check_if_cache_uptodate(pub)
                        # We need to reset the state of the api, otherwise
                        # method api.can_be_canceled() will return True
                        self.api_o.reset()
                        return uptodate
                return False

        def __dump_datamodels(self, pub, application_list, category_list,
            section_list):
                #Consistency check - only dump models if publisher passed in matches 
                #publisher in application list
                if application_list == None:
                        return
                try:
                        app_pub = self.application_list[0]\
                                [enumerations.AUTHORITY_COLUMN]
                except (IndexError, ValueError):
                        #Empty application list nothing to dump
                        return

                if pub != app_pub:
                        if debug:
                                print "ERROR: __dump_data_models(): INCONSISTENT " \
                                        "pub %s != app_list_pub %s" % \
                                        (pub,  app_pub)
                        return

                if self.cache_o:
                        if self.img_timestamp == \
                            self.cache_o.get_index_timestamp():
                                Thread(target = self.cache_o.dump_datamodels,
                                    args = (pub, application_list, category_list,
                                    section_list)).start()
                        else:
                                self.__remove_cache()

        def __remove_cache(self):
                model = self.w_repository_combobox.get_model()
                for pub in model:
                        pub_name = pub[1]
                        if (pub_name and 
                            pub_name not in self.publisher_options.values()):
                                Thread(target = self.cache_o.remove_datamodel,
                                    args = [pub[1]]).start()

        def __on_install_update(self, widget):
                self.api_o.reset()
                install_update = []
                if self.selected == 0:
                        model, itr = self.package_selection.get_selected()
                        if itr:
                                install_update.append(
                                    model.get_value(itr, enumerations.STEM_COLUMN))
                else:
                        visible_publisher = self.__get_selected_publisher()
                        pkgs = self.selected_pkgs.get(visible_publisher)
                        if pkgs:
                                for pkg_stem in pkgs:
                                        status = pkgs.get(pkg_stem)
                                        if status == enumerations.NOT_INSTALLED or \
                                            status == enumerations.UPDATABLE:
                                                install_update.append(pkg_stem)

                if self.img_timestamp != self.cache_o.get_index_timestamp():
                        self.img_timestamp = None
                        self.__remove_cache()

                installupdate.InstallUpdate(install_update, self, \
                    self.image_directory, ips_update = False, \
                    action = enumerations.INSTALL_UPDATE,
                    main_window = self.w_main_window)

        def __on_update_all(self, widget):
                self.api_o.reset()
                skip_be_dlg = False
                if self.api_o.root != IMAGE_DIRECTORY_DEFAULT:
                        skip_be_dlg = True
                installupdate.InstallUpdate([], self,
                    self.image_directory, ips_update = False,
                    action = enumerations.IMAGE_UPDATE, be_name = self.ua_be_name,
                    parent_name = _("Package Manager"),
                    pkg_list = ["SUNWipkg", "SUNWipkg-gui"],
                    main_window = self.w_main_window,
                    skip_be_dialog = skip_be_dlg)
                return

        def __on_ua_completed_linkbutton_clicked(self, widget):
                try:
                        gnome.url_show(self.release_notes_url)
                except gobject.GError:
                        self.error_occurred(_("Unable to navigate to:\n\t%s") % 
                            self.release_notes_url)

        def __on_help_about(self, widget):
                wTreePlan = gtk.glade.XML(self.gladefile, "aboutdialog")
                aboutdialog = wTreePlan.get_widget("aboutdialog")
                aboutdialog.connect("response", lambda x = None, \
                    y = None: aboutdialog.destroy())
                aboutdialog.run()

        @staticmethod
        def __on_help_help(widget):
                gui_misc.display_help()

        def __on_remove(self, widget):
                self.api_o.reset()
                remove_list = []
                if self.selected == 0:
                        model, itr = self.package_selection.get_selected()
                        if itr:
                                remove_list.append(
                                    model.get_value(itr, enumerations.STEM_COLUMN))
                else:
                        visible_publisher = self.__get_selected_publisher()
                        pkgs = self.selected_pkgs.get(visible_publisher)
                        if pkgs:
                                for pkg_stem in pkgs:
                                        status = pkgs.get(pkg_stem)
                                        if status == enumerations.INSTALLED or \
                                            status == enumerations.UPDATABLE:
                                                remove_list.append(pkg_stem)

                if self.img_timestamp != self.cache_o.get_index_timestamp():
                        self.img_timestamp = None
                        self.__remove_cache()

                installupdate.InstallUpdate(remove_list, self,
                    self.image_directory, ips_update = False,
                    action = enumerations.REMOVE,
                    main_window = self.w_main_window)

        def __on_reload(self, widget):
                self.w_repository_combobox.grab_focus()
                if self.description_thread_running:
                        self.cancelled = True
                if self.in_search_mode or self.is_all_publishers:
                        self.__unset_search(False)
                self.__set_empty_details_panel()
                self.in_setup = True
                self.last_visible_publisher = None
                if widget != None:
                        self.__remove_cache()
                self.set_busy_cursor()
                status_str = _("Refreshing package catalog information")
                self.__update_statusbar_message(status_str)
                self.__disconnect_models()
                self.in_reload = True
                Thread(target = self.__catalog_refresh).start()

        def __catalog_refresh_done(self):
                gobject.idle_add(self.process_package_list_start,
                    self.image_directory)

        def __main_application_quit(self, be_name = None):
                '''quits the main gtk loop'''
                self.cancelled = True
                if self.in_setup:
                        return

                width, height = self.w_main_window.get_size()
                hpos = self.w_main_hpaned.get_position()
                vpos = self.w_main_vpaned.get_position()
                try:
                        self.client.set_int(INITIAL_APP_WIDTH_PREFERENCES, width)
                        self.client.set_int(INITIAL_APP_HEIGHT_PREFERENCES, height)
                        self.client.set_int(INITIAL_APP_HPOS_PREFERENCES, hpos)
                        self.client.set_int(INITIAL_APP_VPOS_PREFERENCES, vpos)
                except GError:
                        pass

                self.w_main_window.hide()
                if be_name:
                        if self.image_dir_arg:
                                gobject.spawn_async([self.application_path, "-R",
                                    self.image_dir_arg, "-U", be_name])
                        else:
                                gobject.spawn_async([self.application_path,
                                    "-U", be_name])
                else:
                        if self.is_all_publishers:
                                self.w_repository_combobox.set_active(
                                    self.saved_repository_combobox_active)
                        pub = self.__get_selected_publisher()
                        if self.in_search_mode:
                                self.__dump_datamodels(pub,
                                    self.saved_application_list, self.category_list,
                                    self.section_list)
                        else:
                                self.__dump_datamodels(pub,
                                    self.application_list, self.category_list,
                                    self.section_list)

                if len(self.search_completion) > 0 and self.cache_o != None:
                        self.cache_o.dump_search_completion_info(self.search_completion)

                while gtk.events_pending():
                        gtk.main_iteration(False)
                gtk.main_quit()
                sys.exit(0)
                return True

        def __check_if_something_was_changed(self):
                ''' Returns True if any of the check boxes for package was changed, false
                if not'''
                if self.application_list:
                        for pkg in self.application_list:
                                if pkg[enumerations.MARK_COLUMN] == True:
                                        return True
                return False

        def __setup_repositories_combobox(self, api_o, repositories_list):
                self.__disconnect_repository_model()
                default_pub = api_o.get_preferred_publisher().prefix
                if self.default_publisher != default_pub:
                        self.__clear_pkg_selections()
                        self.default_publisher = default_pub
                selected_repos = []
                enabled_repos = []
                for repo in self.selected_pkgs:
                        selected_repos.append(repo)
                i = 0
                active = 0
                for pub in api_o.get_publishers():
                        if pub.disabled:
                                continue
                        prefix = pub.prefix
                        if cmp(prefix, self.default_publisher) == 0:
                                active = i
                        repositories_list.append([i, prefix, ])
                        enabled_repos.append(prefix)
                        i = i + 1
                self.repo_combobox_all_pubs_index = i
                repositories_list.append([self.repo_combobox_all_pubs_index, 
                    self.publisher_options[PUBLISHER_ALL], ])
                i = i + 1
                repositories_list.append([-1, "", ])
                i = i + 1
                self.repo_combobox_add_index = i
                repositories_list.append([-1,
                    self.publisher_options[PUBLISHER_ADD], ])
                pkgs_to_remove = []
                for repo_name in selected_repos:
                        if repo_name not in enabled_repos:
                                pkg_stems = self.selected_pkgs.get(repo_name)
                                for pkg_stem in pkg_stems:
                                        pkgs_to_remove.append(pkg_stem)
                for pkg_stem in pkgs_to_remove:
                        self.__remove_pkg_stem_from_list(pkg_stem)
                self.w_repository_combobox.set_model(repositories_list)
                if self.default_publisher:
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
                        filterModel.set_value(itr, enumerations.MARK_COLUMN,
                            not modified)
                        pkg_status = filterModel.get_value(itr,
                            enumerations.STATUS_COLUMN)
                        pkg_stem = filterModel.get_value(itr, enumerations.STEM_COLUMN)
                        if modified:
                                self.__remove_pkg_stem_from_list(pkg_stem)
                        else:
                                self.__add_pkg_stem_to_list(pkg_stem, pkg_status)
                        self.update_statusbar()
                        self.__enable_disable_selection_menus()

        def __update_reload_button(self):
                if self.user_rights:
                        self.w_reload_menuitem.set_sensitive(True)
                        self.w_reload_button.set_sensitive(True)
                else:
                        self.w_reload_menuitem.set_sensitive(False)
                        self.w_reload_button.set_sensitive(False)

        def __add_pkg_stem_to_list(self, stem, status):
                pub = self.__get_selected_publisher()
                if self.selected_pkgs.get(pub) == None:
                        self.selected_pkgs[pub] = {}
                self.selected_pkgs.get(pub)[stem] = status
                if status == enumerations.NOT_INSTALLED or \
                    status == enumerations.UPDATABLE:
                        if self.to_install_update.get(pub) == None:
                                self.to_install_update[pub] = 1
                        else:
                                self.to_install_update[pub] += 1
                if status == enumerations.UPDATABLE or status == enumerations.INSTALLED:
                        if self.to_remove.get(pub) == None:
                                self.to_remove[pub] = 1
                        else:
                                self.to_remove[pub] += 1
                self.__update_tooltips()

        def __update_tooltips(self):
                to_remove = None
                to_install = None
                no_iter = 0
                for pub in self.to_remove:
                        packages = self.to_remove.get(pub)
                        if packages > 0:
                                if no_iter == 0:
                                        to_remove = _("Selected for Removal:")
                                to_remove += "\n   %s: %d" % (pub, packages)
                                no_iter += 1
                no_iter = 0
                for pub in self.to_install_update:
                        packages = self.to_install_update.get(pub)
                        if packages > 0:
                                if no_iter == 0:
                                        to_install = _("Selected for Install/Update:")
                                to_install += "\n   %s: %d" % (pub, packages)
                                no_iter += 1
                if not to_install:
                        to_install = _("Select packages by marking the checkbox "
                            "and click to Install/Update.")
                self.w_installupdate_button.set_tooltip(self.install_button_tooltip,
                    to_install)
                if not to_remove:
                        to_remove = _("Select packages by marking the checkbox "
                            "and click to Remove selected.")
                self.w_remove_button.set_tooltip(self.remove_button_tooltip, to_remove)

        def __remove_pkg_stem_from_list(self, stem):
                remove_pub = []
                for pub in self.selected_pkgs:
                        pkgs = self.selected_pkgs.get(pub)
                        status = None
                        if stem in pkgs:
                                status = pkgs.pop(stem)
                        if status == enumerations.NOT_INSTALLED or \
                            status == enumerations.UPDATABLE:
                                if self.to_install_update.get(pub) == None:
                                        self.to_install_update[pub] = 0
                                else:
                                        self.to_install_update[pub] -= 1
                        if status == enumerations.UPDATABLE or \
                            status == enumerations.INSTALLED:
                                if self.to_remove.get(pub) == None:
                                        self.to_remove[pub] = 0
                                else:
                                        self.to_remove[pub] -= 1
                        if len(pkgs) == 0:
                                remove_pub.append(pub)
                for pub in remove_pub:
                        self.selected_pkgs.pop(pub)
                self.__update_tooltips()

        def __clear_pkg_selections(self):
                # We clear the selections as the preffered repository was changed
                # and pkg stems are not valid.
                remove_pub = []
                for pub in self.selected_pkgs:
                        stems = self.selected_pkgs.get(pub)
                        for pkg_stem in stems:
                                remove_pub.append(pkg_stem)
                for pkg_stem in remove_pub:
                        self.__remove_pkg_stem_from_list(pkg_stem)

        def __set_empty_details_panel(self):
                self.showing_empty_details = True
                if self.show_info_id != 0:
                        gobject.source_remove(self.show_info_id)
                        self.show_info_id = 0
                if self.show_licenses_id != 0:
                        gobject.source_remove(self.show_licenses_id)
                        self.show_licenses_id = 0
                self.w_installedfiles_textview.get_buffer().set_text("")
                self.w_dependencies_textview.get_buffer().set_text("")
                self.w_generalinfo_textview.get_buffer().set_text("")
                self.w_license_textview.get_buffer().set_text("")
                return

        def __show_fetching_package_info(self, pkg):
                pkg_stem = pkg.get_pkg_stem()
                if self.__setting_from_cache(pkg_stem):
                        return

                instbuffer = self.w_installedfiles_textview.get_buffer()
                depbuffer = self.w_dependencies_textview.get_buffer()
                infobuffer = self.w_generalinfo_textview.get_buffer()
                fetching_text = _("Fetching information...")
                instbuffer.set_text(fetching_text)
                depbuffer.set_text(fetching_text)
                infobuffer.set_text(fetching_text)
                return

        def __setting_from_cache(self, pkg_stem):
                if len(self.info_cache) > MAX_INFO_CACHE_LIMIT:
                        self.info_cache = {}

                if self.info_cache.has_key(pkg_stem):
                        labs = self.info_cache[pkg_stem][1]
                        text = self.info_cache[pkg_stem][2]
                        self.__set_generalinfo_text(labs, text)
                        text = self.info_cache[pkg_stem][3]
                        self.__set_installedfiles_text(text)
                        text = self.info_cache[pkg_stem][4]
                        self.__set_dependencies_text(text)
                        return True
                else:
                        return False

        def __set_installedfiles_text(self, text):
                instbuffer = self.w_installedfiles_textview.get_buffer()
                instbuffer.set_text("")
                itr = instbuffer.get_start_iter()
                instbuffer.insert_with_tags_by_name(itr, _("Root: "), "bold")
                end_itr = instbuffer.get_end_iter()
                instbuffer.insert(end_itr, "%s" % text)

        def __set_dependencies_text(self, text):
                depbuffer = self.w_dependencies_textview.get_buffer()
                depbuffer.set_text("")
                itr = depbuffer.get_start_iter()
                depbuffer.insert_with_tags_by_name(itr, _("Dependencies:\n"),
                    "bold")
                end_itr = depbuffer.get_end_iter()
                depbuffer.insert(end_itr, "%s" % text)

        @staticmethod
        def __add_line_to_generalinfo(text_buffer, index, label, text, 
            icon = None, font_size = 1):
                itr = text_buffer.get_iter_at_line(index)
                text_buffer.insert_with_tags_by_name(itr, label, "bold")
                end_itr = text_buffer.get_end_iter()
                if icon == None:
                        text_buffer.insert(end_itr, "\t%s\n" % text)
                else:
                        width = icon.get_width()
                        height = icon.get_height()
                        resized_icon = icon.scale_simple(
                            (font_size * width) / height,
                            font_size,
                            gtk.gdk.INTERP_BILINEAR)
                        text_buffer.insert(end_itr, "\t ")
                        text_buffer.get_end_iter()
                        text_buffer.insert_pixbuf(end_itr, resized_icon)
                        text_buffer.insert(end_itr, " %s\n" % text)

        def __set_generalinfo_text(self, labs, text):
                max_len = 0
                for lab in labs:
                        if len(labs[lab]) > max_len:
                                max_len = len(labs[lab])

                style = self.w_generalinfo_textview.get_style()
                font_size_in_pango_unit = style.font_desc.get_size()
                font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
                tab_array = pango.TabArray(2, True)
                tab_array.set_tab(1, pango.TAB_LEFT, max_len * font_size_in_pixel)
                self.w_generalinfo_textview.set_tabs(tab_array)

                infobuffer = self.w_generalinfo_textview.get_buffer()
                infobuffer.set_text("")
                i = 0
                self.__add_line_to_generalinfo(infobuffer, i, labs["name"], 
                    text["name"])
                i += 1
                self.__add_line_to_generalinfo(infobuffer, i, labs["desc"],
                    text["desc"])
                i += 1
                installed = False
                if text["ins"] == _("No"):
                        icon = self.not_installed_icon
                else: 
                        icon = self.installed_icon
                        installed = True
                self.__add_line_to_generalinfo(infobuffer, i, labs["ins"],
                    text["ins"], icon, font_size_in_pixel)
                i += 1
                if installed and text["available"] != _("No"):
                        self.__add_line_to_generalinfo(infobuffer, i, 
                            labs["available"], text["available"],
                            self.update_available_icon, font_size_in_pixel)
                else:
                        self.__add_line_to_generalinfo(infobuffer, i,
                            labs["available"], text["available"])
                i += 1
                self.__add_line_to_generalinfo(infobuffer, i, labs["size"], 
                    text["size"])
                i += 1
                self.__add_line_to_generalinfo(infobuffer, i, labs["cat"], 
                    text["cat"])
                i += 1
                self.__add_line_to_generalinfo(infobuffer, i, labs["repository"], 
                    text["repository"])

        def __update_package_info(self, pkg, local_info, remote_info, info_id):
                if self.showing_empty_details or (info_id != 
                    self.last_show_info_id):
                        return
                pkg_name = pkg.get_name()
                pkg_stem = pkg.get_pkg_stem()
                installed = True

                if self.__setting_from_cache(pkg_stem):
                        return

                instbuffer = self.w_installedfiles_textview.get_buffer()
                depbuffer = self.w_dependencies_textview.get_buffer()
                infobuffer = self.w_generalinfo_textview.get_buffer()

                if not local_info and not remote_info:
                        network_str = \
                            _("\nThis might be caused by network problem "
                            "while accessing the repository.")
                        instbuffer.set_text( \
                            _("Files Details not available for this package...") +
                            network_str)
                        depbuffer.set_text(_(
                            "Dependencies info not available for this package...") +
                            network_str)
                        infobuffer.set_text(
                            _("Information not available for this package...") +
                            network_str)
                        return

                if not local_info:
                        # Package is not installed
                        local_info = remote_info
                        installed = False

                if not remote_info:
                        remote_info = local_info
                        installed = True

                description = local_info.summary
                #XXX long term need to have something more robust here for multi byte
                if len(description) > MAX_DESC_LEN:
                        description = description[:MAX_DESC_LEN] + " ..."
                inst_str = "%s\n" % self.api_o.root
                dep_str = ""

                if local_info.dependencies:
                        dep_str += ''.join(
                            ["\t%s\n" % x for x in local_info.dependencies])
                if local_info.dirs:
                        inst_str += ''.join(["\t%s\n" % x for x in local_info.dirs])
                if local_info.files:
                        inst_str += ''.join(["\t%s\n" % x for x in local_info.files])
                if local_info.hardlinks:
                        inst_str += ''.join(["\t%s\n" % x for x in local_info.hardlinks])
                if local_info.links:
                        inst_str += ''.join(["\t%s\n" % x for x in local_info.links])
                labs = {}
                labs["name"] = _("Name:")
                labs["desc"] = _("Description:")
                labs["size"] = _("Size:")
                labs["cat"] = _("Category:")
                labs["ins"] = _("Installed:")
                labs["available"] = _("Version Available:")
                labs["lat"] = _("Latest Version:")
                labs["repository"] = _("Publisher:")

                categories = _("None")
                if local_info.category_info_list:
                        verbose = len(local_info.category_info_list) > 1
                        categories = ""
                        categories += local_info.category_info_list[0].__str__(verbose)
                        if len(local_info.category_info_list) > 1:
                                for ci in local_info.category_info_list[1:]:
                                        categories += ", " + ci.__str__(verbose)
                description = _("None")
                if local_info.summary:
                        description = local_info.summary

                text = {}
                text["name"] = pkg_name
                text["desc"] = description
                if installed:
                        text["ins"] = _("Yes, %s-%s") % (
                            local_info.build_release, local_info.branch) 
                        labs["available"] =  _("Update Available:")
                        if (local_info.build_release != remote_info.build_release or
                            local_info.branch != remote_info.branch):
                                text["available"] = _("Yes, %s-%s") % (
                                    remote_info.build_release, remote_info.branch)
                        else:
                                text["available"] = _("No")
                else: 
                        text["ins"] = _("No")
                        labs["available"] =  _("Version Available:")
                        text["available"] = "%s-%s" % (
                            remote_info.build_release, remote_info.branch)
                text["size"] = misc.bytes_to_str(local_info.size)
                text["cat"] = categories
                text["repository"] = local_info.publisher
                self.__set_generalinfo_text(labs, text)

                self.__set_installedfiles_text(inst_str)
                self.__set_dependencies_text(dep_str)
                self.info_cache[pkg_stem] = \
                    (description, labs, text, inst_str, dep_str)

        def __update_package_license(self, licenses, license_id):
                if self.showing_empty_details or (license_id !=
                    self.last_show_licenses_id):
                        return
                lic = ""
                lic_u = ""
                if licenses == None:
                        lic_u = _("Not available")
                else:
                        for licens in licenses:
                                lic += licens.get_text()
                                lic += "\n"
                        try:
                                lic_u = unicode(lic, "utf-8")
                        except UnicodeDecodeError:
                                lic_u = _("License could not be shown "
                                    "due to conversion problem.")
                licbuffer = self.w_license_textview.get_buffer()
                licbuffer.set_text(lic_u)

        def __show_licenses(self):
                self.show_licenses_id = 0
                if self.catalog_loaded == False:
                        return
                Thread(target = self.__show_package_licenses,
                    args = (self.selected_pkgstem, self.last_show_licenses_id,)).start()

        def __show_package_licenses(self, selected_pkgstem, license_id):
                if selected_pkgstem == None:
                        gobject.idle_add(self.__update_package_license, None,
                            self.last_show_licenses_id)
                        return
                info = None
                try:
                        info = self.api_o.info([selected_pkgstem],
                            True, frozenset([api.PackageInfo.LICENSES]))
                except (api_errors.TransportError):
                        pass
                if self.showing_empty_details or (license_id != 
                    self.last_show_licenses_id):
                        return
                if not info or (info and len(info.get(0)) == 0):
                        try:
                        # Get license from remote
                                info = self.api_o.info([selected_pkgstem],
                                    False, frozenset([api.PackageInfo.LICENSES]))
                        except (api_errors.TransportError):
                                pass
                if self.showing_empty_details or (license_id != 
                    self.last_show_licenses_id):
                        return
                pkgs_info = None
                package_info = None
                no_licenses = 0
                if info:
                        pkgs_info = info[0]
                if pkgs_info:
                        package_info = pkgs_info[0]
                if package_info:
                        no_licenses = len(package_info.licenses)
                if no_licenses == 0:
                        gobject.idle_add(self.__update_package_license, None, 
                            license_id)
                        return
                else:
                        gobject.idle_add(self.__update_package_license,
                            package_info.licenses, license_id)

        def __get_pkg_info(self, pkg_stem, local):
                info = None
                try:
                        info = self.api_o.info([pkg_stem], local,
                            api.PackageInfo.ALL_OPTIONS -
                            frozenset([api.PackageInfo.LICENSES]))
                except (api_errors.TransportError):
                        return info
                pkgs_info = None
                package_info = None
                if info:
                        pkgs_info = info[0]
                if pkgs_info:
                        package_info = pkgs_info[0]
                if package_info:
                        return package_info
                else:
                        return None

        def __show_info(self, model, path):
                self.show_info_id = 0
                if self.catalog_loaded == False:
                        self.selected_model = model
                        self.selected_path = path
                        return
                if not (model and path):
                        return
                if self.selected_model != None:
                        if (self.selected_model != model or
                            self.selected_path != path):
                        # This can happen after catalogs are loaded in
                        # enable_disable_update_all and a different
                        # package is selected before enable_disable_update_all
                        # calls __show_info. We set these variable to None
                        # so that when __show_info is called it does nothing.
                                self.selected_model = None
                                self.selected_path = None

                itr = model.get_iter(path)
                pkg = model.get_value(itr, enumerations.FMRI_COLUMN)
                pkg_stem = model.get_value(itr, enumerations.STEM_COLUMN)
                pkg_status = model.get_value(itr, enumerations.STATUS_COLUMN)
                if self.info_cache.has_key(pkg_stem):
                        return
                Thread(target = self.__show_package_info,
                    args = (pkg, pkg_stem, pkg_status, self.last_show_info_id)).start()

        def __show_package_info(self, pkg, pkg_stem, pkg_status, info_id):
                self.api_o.log_operation_start("info")
                local_info = None
                remote_info = None
                if not self.showing_empty_details and (info_id ==
                    self.last_show_info_id) and (pkg_status ==
                    enumerations.INSTALLED or pkg_status ==
                    enumerations.UPDATABLE):
                        local_info = self.__get_pkg_info(pkg_stem, True)
                if not self.showing_empty_details and (info_id ==
                    self.last_show_info_id) and (pkg_status ==
                    enumerations.NOT_INSTALLED or pkg_status ==
                    enumerations.UPDATABLE):
                        remote_info = self.__get_pkg_info(pkg_stem, False)
                if not self.showing_empty_details and (info_id ==
                    self.last_show_info_id):
                        gobject.idle_add(self.__update_package_info, pkg,
                            local_info, remote_info, info_id)
                self.api_o.log_operation_end()
                return

        # This function is ported from pkg.actions.generic.distinguished_name()
        @staticmethod
        def __locale_distinguished_name(action):
                if action.key_attr == None:
                        return str(action)
                return "%s: %s" % \
                    (_(action.name), action.attrs.get(action.key_attr, "???"))

        def __get_active_section_and_category(self):
                selection = self.w_categories_treeview.get_selection()
                selected_section = 0
                selected_category = 0
                
                if not selection:
                        return 0, 0
                category_model, category_itr = selection.get_selected()
                if not category_model or not category_itr:
                        return 0, 0

                selected_category = category_model.get_value(category_itr,
                    enumerations.CATEGORY_ID)
                cat_path = list(category_model.get_path(category_itr))
                        
                # Top level Section has been selected
                if len(cat_path) == 1 and selected_category > SECTION_ID_OFFSET:
                        selected_section = selected_category - SECTION_ID_OFFSET
                        return selected_section, 0
                else:
                        # Subcategory selected need to get categories parent Section
                        parent_iter = category_model.iter_parent(category_itr)
                        if not parent_iter:
                                return selected_section, selected_category
                        selected_section = category_model.get_value(
                            parent_iter, enumerations.CATEGORY_ID) - SECTION_ID_OFFSET
                        return selected_section, selected_category

        def __application_filter(self, model, itr):
                '''This function is used to filter content in the main
                application view'''
                selected_category = 0
                selected_section = 0
                category = False

                if self.in_setup or self.cancelled:
                        return category
                filter_id = self.w_filter_combobox.get_active()
                if filter_id == enumerations.FILTER_SELECTED:
                        return model.get_value(itr, enumerations.MARK_COLUMN)

                category_list = model.get_value(itr, enumerations.CATEGORY_LIST_COLUMN)
                selected_section, selected_category = \
                        self.__get_active_section_and_category()
                
                if selected_section == 0 and selected_category == 0:
                        #Clicked on All Categories
                        category = True
                elif selected_category != 0:
                        #Clicked on subcategory
                        if category_list and selected_category in category_list:
                                category = True
                elif category_list:
                        #Clicked on Top Level section
                        categories_in_section = \
                                self.section_categories_list[selected_section]
                        for cat_id in category_list:
                                if cat_id in categories_in_section:
                                        category = True
                                        break
                if (model.get_value(itr, enumerations.IS_VISIBLE_COLUMN) == False):
                        return False
                if self.in_search_mode:
                        return self.__is_package_filtered(model, itr, filter_id)
                return (category &
                    self.__is_package_filtered(model, itr, filter_id))

        @staticmethod
        def __is_package_filtered(model, itr, filter_id):
                '''Function for filtercombobox'''
                if filter_id == enumerations.FILTER_ALL:
                        return True
                status = model.get_value(itr, enumerations.STATUS_COLUMN)
                if filter_id == enumerations.FILTER_INSTALLED:
                        return (status == enumerations.INSTALLED or status == \
                            enumerations.UPDATABLE)
                elif filter_id == enumerations.FILTER_UPDATES:
                        return status == enumerations.UPDATABLE
                elif filter_id == enumerations.FILTER_NOT_INSTALLED:
                        return status == enumerations.NOT_INSTALLED

        def __is_pkg_repository_visible(self, model, itr):
                if len(self.repositories_list) <= 1:
                        return True
                else:
                        visible_publisher = self.__get_selected_publisher()
                        pkg = model.get_value(itr, enumerations.FMRI_COLUMN)
                        if not pkg:
                                return False
                        if cmp(pkg.get_publisher(), visible_publisher) == 0:
                                return True
                        else:
                                return False

        def __enable_disable_selection_menus(self):
                if self.in_setup:
                        return
                self.__enable_disable_select_updates()
                if not self.__doing_search():
                        self.unset_busy_cursor()

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

        def __enable_disable_install_remove(self):
                if not self.user_rights:
                        self.w_installupdate_button.set_sensitive(False)
                        self.w_installupdate_menuitem.set_sensitive(False)
                        self.w_remove_button.set_sensitive(False)
                        self.w_remove_menuitem.set_sensitive(False)
                        return
                selected_removal = self.__enable_if_selected_for_removal()
                selected_install_update = self.__enable_if_selected_for_install_update()
                if selected_removal or selected_install_update:
                        return
                remove = False
                install = False
                if self.selected == 0:
                        model, itr = self.package_selection.get_selected()
                        if itr:
                                status = \
                                       model.get_value(itr, enumerations.STATUS_COLUMN)
                                if status == enumerations.NOT_INSTALLED:
                                        remove = False
                                        install = True
                                elif status == enumerations.UPDATABLE:
                                        remove = True
                                        install = True
                                elif status == enumerations.INSTALLED:
                                        remove = True
                                        install = False
                                self.w_installupdate_button.set_sensitive(install)
                                self.w_installupdate_menuitem.set_sensitive(install)
                                self.w_remove_button.set_sensitive(remove)
                                self.w_remove_menuitem.set_sensitive(remove)

        def __enable_if_selected_for_removal(self):
                sensitive = False
                visible_publisher = self.__get_selected_publisher()
                selected = self.to_remove.get(visible_publisher)
                if selected > 0:
                        sensitive = True
                self.w_remove_button.set_sensitive(sensitive)
                self.w_remove_menuitem.set_sensitive(sensitive)
                return sensitive

        def __enable_if_selected_for_install_update(self):
                sensitive = False
                visible_publisher = self.__get_selected_publisher()
                selected = self.to_install_update.get(visible_publisher)
                if selected > 0:
                        sensitive = True
                self.w_installupdate_button.set_sensitive(sensitive)
                self.w_installupdate_menuitem.set_sensitive(sensitive)
                return sensitive

        def __enable_disable_select_updates(self):
                for row in self.w_application_treeview.get_model():
                        if row[enumerations.STATUS_COLUMN] == enumerations.UPDATABLE:
                                if not row[enumerations.MARK_COLUMN]:
                                        self.w_selectupdates_menuitem. \
                                            set_sensitive(True)
                                        return
                self.w_selectupdates_menuitem.set_sensitive(False)
                return

        def __get_inventory_list(self, pargs, all_known, all_versions):
                self.__image_activity_lock.acquire()
                try:
                        res = misc.get_inventory_list(self.api_o.img, 
                            pargs, all_known, all_versions)
                finally:
                        self.__image_activity_lock.release()
                return res

        def __enable_disable_update_all(self, refresh_done):
                #XXX Api to provide fast information if there are some updates
                #available within image
                gobject.idle_add(self.w_updateall_button.set_sensitive, False)
                gobject.idle_add(self.w_updateall_menuitem.set_sensitive, False)
                update_available = self.__check_if_updates_available(refresh_done)
                gobject.idle_add(self.__g_enable_disable_update_all, update_available)
                return False

        def __show_info_after_catalog_load(self):
                self.__show_info(self.selected_model, self.selected_path)
                self.selected_model = None
                self.selected_path = None
                if (self.w_info_notebook.get_current_page() == 
                    INFO_NOTEBOOK_LICENSE_PAGE and
                    not self.showing_empty_details):
                        self.__show_licenses()

        def __check_if_updates_available(self, refresh_done):
                # First we load the catalogs so package info can work
                try:
                        if not refresh_done:
                                self.catalog_loaded = False
                                self.api_o.refresh()
                                self.catalog_loaded = True
                except api_errors.InventoryException:
                        gobject.idle_add(self.__set_empty_details_panel)
                        return False
                except api_errors.InvalidDepotResponseException, idrex:
                        err = str(idrex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                        gobject.idle_add(self.__set_empty_details_panel)
                        return False
                except api_errors.CatalogRefreshException, cre:
                        self.__catalog_refresh_message(cre)
                        gobject.idle_add(self.__set_empty_details_panel)
                        return False
                except api_errors.ApiException, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                        gobject.idle_add(self.__set_empty_details_panel)
                        return False
                gobject.idle_add(self.__show_info_after_catalog_load)

                return_code = subprocess.call([os.path.join(self.application_dir, 
                    CHECK_FOR_UPDATES),
                    self.image_directory])
                if return_code == enumerations.UPDATES_AVAILABLE:
                        return True
                else:
                        return False

        def __g_enable_disable_update_all(self, update_available):
                self.w_updateall_button.set_sensitive(update_available)
                self.w_updateall_menuitem.set_sensitive(update_available)
                self.__enable_disable_install_remove()

        def __enable_disable_deselect(self):
                if self.w_application_treeview.get_model():
                        for row in self.w_application_treeview.get_model():
                                if row[enumerations.MARK_COLUMN]:
                                        self.w_deselect_menuitem.set_sensitive(True)
                                        return
                self.w_deselect_menuitem.set_sensitive(False)
                return

        def __catalog_refresh(self, reload_gui=True):
                """Update image's catalogs."""
                try:
                        # Since the user requested the refresh, perform it
                        # immediately for all publishers.
                        self.api_o.refresh(immediate=True)
                        self.catalog_refresh_done = True
                        # Refresh will load the catalogs.
                        self.catalog_loaded = True
                except api_errors.PublisherError:
                        # In current implementation, this will never happen
                        # We are not refreshing specific publisher
                        self.__catalog_refresh_done()
                        raise
                except api_errors.PermissionsException:
                        #Error will already have been reported in
                        #Manage Repository dialog
                        self.__catalog_refresh_done()
                        return -1
                except api_errors.CatalogRefreshException, cre:
                        self.__catalog_refresh_message(cre)
                        self.__catalog_refresh_done()
                        return -1
                except api_errors.InvalidDepotResponseException, idrex:
                        err = str(idrex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                        self.__catalog_refresh_done()
                        return -1
                except api_errors.PublisherError:
                        self.__catalog_refresh_done()
                        raise
                except Exception:
                        self.__catalog_refresh_done()
                        raise
                if reload_gui:
                        self.__catalog_refresh_done()
                return 0

        def __add_pkgs_to_lists_from_cache(self, pub, application_list,
            category_list, section_list):
                if self.cache_o:
                        self.cache_o.load_application_list(pub, application_list,
                            self.selected_pkgs)
                        self.cache_o.load_category_list(pub, category_list)
                        self.cache_o.load_section_list(pub, section_list)

        def __add_pkgs_to_lists_from_api(self, pub, application_list,
            category_list, section_list):
                """ This method set up image from the given directory and
                returns the image object or None"""
                pargs = []
                pargs.append("pkg://" + pub + "/*")
                try:
                        pkgs_known = self.__get_inventory_list(pargs,
                            True, True)
                except api_errors.InventoryException:
                        # This can happen if the repository does not
                        # contain any packages
                        err = _("Selected package source does not contain any packages.")
                        gobject.idle_add(self.error_occurred, err, None,
                            gtk.MESSAGE_INFO)
                        self.unset_busy_cursor()
                        pkgs_known = []

                return self.__add_pkgs_to_lists(pkgs_known, application_list,
                    category_list, section_list)

        def __add_pkgs_to_lists(self, pkgs_known, application_list,
            category_list, section_list):
                if section_list != None:
                        self.__init_sections(section_list)
                #Imageinfo for categories
                imginfo = imageinfo.ImageInfo()
                sectioninfo = imageinfo.ImageInfo()
                pubs = [p.prefix for p in self.api_o.get_publishers()]
                categories = {}
                sections = {}
                share_path = os.path.join(self.application_dir,
                    "usr/share/package-manager/data")
                for pub in pubs:
                        category = imginfo.read(os.path.join(share_path, pub))
                        if len(category) == 0:
                                category = imginfo.read(os.path.join(share_path,
                                    "opensolaris.org"))
                        categories[pub] = category
                        section = sectioninfo.read(os.path.join(share_path,
                            pub + ".sections"))
                        if len(section) == 0:
                                section = sectioninfo.read(os.path.join(share_path,
                                "opensolaris.org.sections"))
                        sections[pub] = section
                pkg_count = 0
                pkg_add = 0
                total_pkg_count = len(pkgs_known)
                status_str = _("Loading package list")
                gobject.idle_add(self.__update_statusbar_message, status_str)
                prev_stem = ""
                prev_pfmri_str = ""
                next_app = None
                pkg_name = None
                pkg_publisher = None
                prev_state = None
                for pkg, state in pkgs_known:
                        if prev_pfmri_str and \
                            prev_pfmri_str == pkg.get_short_fmri() and \
                            prev_state == state:
                                pkg_count += 1
                                continue
                        if prev_stem and \
                            prev_stem == pkg.get_pkg_stem() and \
                            prev_state["state"] == "known" and \
                            state["state"] == "installed":
                                pass
                        elif next_app != None:
                                self.__add_package_to_list(next_app,
                                    application_list,
                                    pkg_add, pkg_name,
                                    categories, category_list, pkg_publisher)
                                pkg_add += 1
                        prev_stem = pkg.get_pkg_stem()
                        prev_pfmri_str = pkg.get_short_fmri()
                        prev_state = state

                        gobject.idle_add(self.__progress_set_fraction,
                            pkg_count, total_pkg_count)
                        status_icon = None
                        pkg_name = pkg.get_name()
                        pkg_name = gui_misc.get_pkg_name(pkg_name)
                        pkg_stem = pkg.get_pkg_stem()
                        pkg_publisher = pkg.get_publisher()
                        pkg_state = enumerations.NOT_INSTALLED
                        if state["state"] == "installed":
                                pkg_state = enumerations.INSTALLED
                                if state["upgradable"] == True:
                                        status_icon = self.update_available_icon
                                        pkg_state = enumerations.UPDATABLE
                                else:
                                        status_icon = self.installed_icon
                        else:
                                status_icon = self.not_installed_icon
                        marked = False
                        if not self.is_all_publishers:
                                pkgs = self.selected_pkgs.get(pkg_publisher)
                                if pkgs != None:
                                        if pkg_stem in pkgs:
                                                marked = True
                        next_app = \
                            [
                                marked, status_icon, pkg_name, '...', pkg_state,
                                pkg, pkg_stem, None, True, None, pkg_publisher
                            ]
                        pkg_count += 1

                if next_app:
                        self.__add_package_to_list(next_app, application_list, 
                            pkg_add, pkg_name, categories, 
                            category_list, pkg_publisher)
                        pkg_add += 1
                if category_list != None:
                        self.__add_categories_to_sections(sections,
                            category_list, section_list)
                gobject.idle_add(self.__progress_set_fraction,
                    pkg_count, total_pkg_count)
                return

        def __add_categories_to_sections(self, sections, category_list, section_list):
                for pub in sections:
                        for section in sections[pub]:
                                for category in sections[pub][section].split(","):
                                        self.__add_category_to_section(_(category),
                                            _(section), category_list, section_list)

                #1915 Sort the Categories into alphabetical order and prepend All Category
                if len(category_list) > 0:
                        rows = [tuple(r) + (i,) for i, r in enumerate(category_list)]
                        rows.sort(self.__sort)
                        r = []
                        category_list.reorder(None, [r[-1] for r in rows])
                return

        def __add_package_to_list(self, app, application_list, pkg_add,
            pkg_name, categories, category_list, pub):
                row_iter = application_list.insert(pkg_add, app)
                if category_list == None:
                        return
                cat_pub = categories.get(pub)
                if pkg_name in cat_pub:
                        pkg_categories = cat_pub.get(pkg_name)
                        for pcat in pkg_categories.split(","):
                                self.__add_package_to_category(_(pcat), None,
                                    row_iter, application_list,
                                    category_list)

        @staticmethod
        def __add_package_to_category(category_name, category_description,
            package, application_list, category_list):
                if not package or category_name == _('All'):
                        return
                if not category_name:
                        return
                category_id = None
                for category in category_list:
                        if category[enumerations.CATEGORY_NAME] == category_name:
                                category_id = category[enumerations.CATEGORY_ID]
                                break
                if not category_id:                       # Category not exists
                        category_id = len(category_list) + 1
                        category_list.append(None, [category_id, category_name,
                            category_description, None])
                if application_list.get_value(package,
                    enumerations.CATEGORY_LIST_COLUMN):
                        a = application_list.get_value(package,
                            enumerations.CATEGORY_LIST_COLUMN)
                        a.append(category_id)
                else:
                        category_list = []
                        category_list.append(category_id)
                        application_list.set(package,
                            enumerations.CATEGORY_LIST_COLUMN, category_list)

        def __add_categories_to_tree(self, category_list, section_list):
                category_tree = self.__get_new_category_liststore()
                cat_iter = category_tree.append(None,
                            [ 0, _("All Categories"), None, None])

                #Build dic of section ids and categories they contain
                #section_category_list[<sec_id>] -> cat_ids[cat_id] -> category
                #Each category row contains a list of sections it belongs to stored in
                #category[enumerations.SECTION_LIST_OBJECT]
                for category in category_list:
                        category_section_ids = \
                                category[enumerations.SECTION_LIST_OBJECT]
                        if category_section_ids == None:
                                continue
                        for sec_id in category_section_ids:
                                if sec_id in self.section_categories_list:
                                        category_ids = \
                                                self.section_categories_list[sec_id]
                                        category_ids[category[enumerations.CATEGORY_ID]] \
                                                = category
                                else:
                                        self.section_categories_list[sec_id] = \
                                                {category[enumerations.CATEGORY_ID]:\
                                                    category}

                #Build up the Category Tree
                count = 1
                visible_default_section_path = None
                for section in section_list:
                        sec_id = section[enumerations.SECTION_ID]
                        #Map self.set_section section_list index to visible section index
                        if sec_id <= 0 or not section[enumerations.SECTION_ENABLED]:
                                continue
                        if self.set_section == sec_id:
                                visible_default_section_path = (count,)
                        count += count
                        
                        cat_iter = category_tree.append(None,
                            [ SECTION_ID_OFFSET + section[enumerations.SECTION_ID], 
                            "<b>" + section[enumerations.SECTION_NAME] + "</b>",
                            None, None])

                        if not sec_id in self.section_categories_list:
                                continue
                        
                        category_ids = self.section_categories_list[sec_id]
                        for cat_id in category_ids.keys():
                                category_tree.append(cat_iter, category_ids[cat_id])
                                        
                self.w_categories_treeview.set_model(category_tree)
                
                #Initial startup expand default Section if available
                if visible_default_section_path and self.first_run:
                        self.w_categories_treeview.expand_row(
                            visible_default_section_path, False)
                        return

                #Restore expanded Category state
                if len(self.category_expanded_paths) > 0:
                        paths = self.category_expanded_paths.items()
                        for key, val in paths:
                                source, path = key
                                if self.last_visible_publisher == source and val:
                                        self.w_categories_treeview.expand_row(path, False)
                #Resotre selected category path
                if self.last_visible_publisher in self.category_active_paths and \
                        self.category_active_paths[self.last_visible_publisher]:
                        self.w_categories_treeview.set_cursor(
                            self.category_active_paths[self.last_visible_publisher])
                else:
                        self.w_categories_treeview.set_cursor(0)
                return

        @staticmethod
        def __add_category_to_section(category_name, section_name, category_list,
            section_list):
                '''Adds the section to section list in category. If there is no such
                section, than it is not added. If there was already section than it
                is skipped. Sections must be case sensitive'''
                if not category_name:
                        return
                for section in section_list:
                        if section[enumerations.SECTION_NAME] == section_name:
                                section_id = section[enumerations.SECTION_ID]
                                for category in category_list:
                                        if category[enumerations.CATEGORY_NAME] == \
                                            category_name:
                                                section_lst = category[ \
                                                    enumerations.SECTION_LIST_OBJECT]
                                                section[enumerations.SECTION_ENABLED] = \
                                                    True
                                                if not section_lst:
                                                        category[ \
                                                    enumerations.SECTION_LIST_OBJECT] = \
                                                            [section_id, ]
                                                else:
                                                        if not section_name in \
                                                            section_lst:
                                                                section_lst.append(
                                                                    section_id)


        def __progress_set_fraction(self, count, total):
                self.__progress_pulse_stop()
                if count == total:
                        self.w_progress_frame.hide()
                        return False
                if self.api_o.can_be_canceled():
                        self.progress_cancel.show()
                else:
                        self.progress_cancel.hide()
                self.w_progress_frame.show()
                result = (count + 0.0)/total
                if result > 1.0:
                        result = 1.0
                elif result < 0.0:
                        result = 0.0
                self.w_status_progressbar.set_fraction(result)


        def __progress_pulse_start(self):
                if self.progress_stop_thread == True:
                        self.progress_stop_thread = False
                        Thread(target = self.__progress_pulse).start()

        def __progress_pulse_stop(self):
                self.progress_stop_thread = True

        def __progress_pulse(self):
                gobject.idle_add(self.w_progress_frame.show)
                while not self.progress_stop_thread:
                        if self.api_o.can_be_canceled():
                                gobject.idle_add(self.progress_cancel.show)
                        else:
                                gobject.idle_add(self.progress_cancel.hide)
                        gobject.idle_add(self.w_status_progressbar.pulse)
                        time.sleep(0.1)
                gobject.idle_add(self.w_progress_frame.hide)
                self.progress_stop_thread = True

        def error_occurred(self, error_msg, msg_title=None, msg_type=gtk.MESSAGE_ERROR):
                if msg_title:
                        title = msg_title
                else:
                        title = _("Package Manager")
                gui_misc.error_occurred(self.w_main_window, error_msg,
                    title, msg_type, use_markup=True)

#-----------------------------------------------------------------------------#
# Static Methods
#-----------------------------------------------------------------------------#

        #@staticmethod
        #def N_(message):
        #        return message

        @staticmethod
        def __sort(a, b):
                return cmp(a[1], b[1])

        @staticmethod
        def filter_cell_data_function(column, renderer, model, itr, data):
                '''Function which sets icon size'''
                if data == enumerations.FILTER_NAME:
                        renderer.set_property("xalign", 0)
                        renderer.set_property("width", max_filter_length + 10)
                elif data == enumerations.FILTER_ICON:
                        renderer.set_property("xalign", 0)
                        renderer.set_property("width", 24)
                return

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
                return model.get_value(itr, 0) == -1 and \
                    model.get_value(itr, 1) == ""

        @staticmethod
        def combobox_filter_id_separator(model, itr):
                return model.get_value(itr, 0) == -1 and \
                    model.get_value(itr, 2) == ""

        @staticmethod
        def get_datetime(version):
                dt = None
                try:
                        dt = version.get_datetime()
                except AttributeError:
                        dt = version.get_timestamp()
                return dt

        @staticmethod
        def __get_version(api_o, local, pkg):
                info = api_o.info([pkg], local, frozenset(
                    [api.PackageInfo.STATE, api.PackageInfo.IDENTITY]))
                found = info[api.ImageInterface.INFO_FOUND]
                try:
                        version = found[0]
                except IndexError:
                        version = None
                return version

#-----------------------------------------------------------------------------#
# Public Methods
#-----------------------------------------------------------------------------#
        def init_show_filter(self):
                """ Sets up the Filter Combobox and returns the maximum length of text
                    labels it is displaying."""
                return self.__init_show_filter()                #Initiates filter

        def reload_packages(self):
                self.api_o = gui_misc.get_api_object(self.image_directory, 
                    self.pr, self.w_main_window)
                self.cache_o = self.__get_cache_obj(self.icon_theme, 
                    self.application_dir, self.api_o)
                self.__on_reload(None)

        def is_busy_cursor_set(self):
                return self.gdk_window.is_visible()

        def set_busy_cursor(self):
                if self.gdk_window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN:
                        self.gdk_window.show()
                        self.w_main_window.get_accessible().emit('state-change',
                            'busy', True)
                self.__progress_pulse_start()

        def unset_busy_cursor(self):
                self.__progress_pulse_stop()
                if not (self.gdk_window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN):
                        self.gdk_window.hide()
                        self.w_main_window.get_accessible().emit('state-change',
                            'busy', False)

        def process_package_list_start(self, image_directory):
                self.image_directory = image_directory
                if not self.api_o:
                        self.api_o = gui_misc.get_api_object(image_directory, 
                            self.pr, self.w_main_window)
                        self.cache_o = self.__get_cache_obj(self.icon_theme,
                            self.application_dir, self.api_o)
                        self.img_timestamp = self.cache_o.get_index_timestamp()
                        self.__setup_search_completion()
                self.repositories_list = self.__get_new_repositories_liststore()
                self.__setup_repositories_combobox(self.api_o, self.repositories_list)

        def __get_cache_obj(self, icon_theme, application_dir, api_o):
                cache_o = cache.CacheListStores(icon_theme, application_dir,
                    api_o, self.lang, self.update_available_icon, self.installed_icon,
                    self.not_installed_icon)
                return cache_o

        def __setup_search_completion(self):
                completion = gtk.EntryCompletion()
                if self.cache_o != None:
                        self.cache_o.load_search_completion_info(self.search_completion)
                completion.set_model(self.search_completion)
                self.w_searchentry.set_completion(completion)
                completion.set_text_column(0)
                self.w_searchentry.connect('activate', self.__search_completion_cb)


        def process_package_list_end(self):
                self.in_startpage_startup = False
                if self.update_all_proceed:
                # TODO: Handle situation where only SUNWipkg/SUNWipg-gui have been updated
                # in update all: bug 6357
                        self.__on_update_all(None)
                        self.update_all_proceed = False
                self.__enable_disable_install_remove()
                self.update_statusbar()
                self.in_setup = False
                self.cancelled = False
                if self.set_section != 0 or \
                    self.set_show_filter != enumerations.FILTER_ALL:
                        self.__application_refilter()
                else:
                        self.unset_busy_cursor()
                
                if self.user_rights and (self.first_run or self.in_reload):
                        Thread(target = self.__enable_disable_update_all,
                            args = (self.catalog_refresh_done,)).start()
                self.catalog_refresh_done = False
                self.first_run = False
                self.in_reload = False

        def get_icon_pixbuf_from_glade_dir(self, icon_name):
                return gui_misc.get_pixbuf_from_path(
                    os.path.join(self.application_dir, 
                    "usr/share/package-manager/"),
                    icon_name)

        def update_statusbar(self):
                '''Function which updates statusbar'''
                if self.statusbar_message_id > 0:
                        self.w_main_statusbar.remove(0, self.statusbar_message_id)
                        self.statusbar_message_id = 0
                search_text = self.w_searchentry.get_text()

                if not self.in_search_mode:
                        if self.application_list == None:
                                return
                        self.length_visible_list = len(self.application_list_filter)
                        self.selected = 0
                        visible_publisher = self.__get_selected_publisher()
                        pkgs = self.selected_pkgs.get(visible_publisher)
                        if pkgs:
                                self.selected = len(pkgs)
                        selected_in_list = 0
                        for pkg_row in self.application_list_filter:
                                if pkg_row[enumerations.MARK_COLUMN]:
                                        selected_in_list = selected_in_list + 1
                        status_str = _("Total: %(total)s  Selected: %(selected)s") % \
                                {"total": self.length_visible_list, 
                                "selected": selected_in_list}
                        self.__update_statusbar_message(status_str)
                        return

                # In Search Mode
                active = ""
                if self.is_all_publishers:
                        if self.__doing_search():
                                if self.search_all_pub_being_searched != None:
                                        active = "(" + \
                                            self.search_all_pub_being_searched + ") "
                                opt_str = _('Searching... '
                                    '%(active)sfor "%(search_text)s"') % \
                                        {"active": active, "search_text": search_text}
                        else:
                                opt_str = _('Searched All for "%s"') % (search_text)
                else:
                        search_str = _("Searched")
                        if self.__doing_search():
                                search_str = _("Searching...")
                        visible_publisher = self.__get_selected_publisher()
                        if visible_publisher != None:
                                active = "(" + visible_publisher + ") "
                        opt_str = \
                                _('%(search)s %(last_active)sfor "%(search_text)s"') \
                                % {"search": search_str, "last_active" : active,
                                    "search_text" : search_text}
                fmt_str = _("%(option_str)s:  %(number)d found %(time)s")
                time_str = ""
                if self.search_time_sec == 1:
                        time_str = _("in 1 second")
                elif self.search_time_sec > 1:
                        time_str = _("in %d seconds") % self.search_time_sec
                        
                status_str = fmt_str % {"option_str" : opt_str, "number" :
                    len(self.application_list), "time" : time_str}
                self.__update_statusbar_message(status_str)

        def __reset_row_status(self, row):
                pkg_stem = row[enumerations.STEM_COLUMN]
                self.__remove_pkg_stem_from_list(pkg_stem)
                if self.info_cache.has_key(pkg_stem):
                        del self.info_cache[pkg_stem]
                package_info = self.__get_version(self.api_o,
                    local = True, pkg = pkg_stem)
                package_installed =  False
                if package_info:
                        package_installed =  \
                            (package_info.state == api.PackageInfo.INSTALLED)
                if package_installed:
                        package_info = self.__get_version(self.api_o,
                            local = False, pkg = pkg_stem)
                        if (package_info and
                            package_info.state == api.PackageInfo.INSTALLED):
                                row[enumerations.STATUS_COLUMN] = \
                                    enumerations.INSTALLED
                                row[enumerations.STATUS_ICON_COLUMN] = \
                                    self.installed_icon
                        else:
                                row[enumerations.STATUS_COLUMN] = \
                                    enumerations.UPDATABLE
                                row[enumerations.STATUS_ICON_COLUMN] = \
                                    self.update_available_icon
                else:
                        row[enumerations.STATUS_COLUMN] = \
                            enumerations.NOT_INSTALLED
                        row[enumerations.STATUS_ICON_COLUMN] = \
                            self.not_installed_icon
                row[enumerations.MARK_COLUMN] = False

        def __update_publisher_list(self, pub, full_list, package_list):
                for row in full_list:
                        if row[enumerations.NAME_COLUMN] in package_list:
                                self.__reset_row_status(row)

        @staticmethod
        def __update_package_list_names(package_list):
                i = 0
                while i < len(package_list):
                        package_list[i] = gui_misc.get_pkg_name(package_list[i])
                        i +=  1
                return package_list

        def update_package_list(self, update_list):
                if update_list == None and self.img_timestamp:
                        return
                visible_publisher = self.__get_selected_publisher()
                default_publisher = self.default_publisher
                self.api_o.refresh()
                if not self.img_timestamp:
                        self.img_timestamp = self.cache_o.get_index_timestamp()
                        self.__on_reload(None)
                        return
                self.img_timestamp = self.cache_o.get_index_timestamp()
                visible_list = update_list.get(visible_publisher)
                if self.is_all_publishers:
                        for pub in self.api_o.get_publishers():
                                if pub.disabled:
                                        continue
                                prefix = pub.prefix
                                package_list = update_list.get(prefix)
                                if package_list != None:
                                        package_list = \
                                            self.__update_package_list_names(
                                            package_list)
                                        self.__update_publisher_list(prefix,
                                            self.application_list,
                                            package_list)
                                        if self.last_visible_publisher == prefix:
                                                self.__update_publisher_list(prefix,
                                                        self.saved_application_list,
                                                        package_list)
                elif visible_list:
                        visible_list = self.__update_package_list_names(visible_list)
                        self.__update_publisher_list(visible_publisher, 
                                self.application_list, visible_list)
                        if self.in_search_mode:
                                self.__update_publisher_list(visible_publisher,
                                        self.saved_application_list,
                                        visible_list)

                for pub in update_list:
                        if pub != visible_publisher:
                                pkg_list = update_list.get(pub)
                                for pkg in pkg_list:
                                        pkg_stem = None
                                        if pub != default_publisher:
                                                pkg_stem = "pkg://%s/%s" % \
                                                        (pub, pkg)
                                        else:
                                                pkg_stem = "pkg:/%s" % pkg
                                        if pkg_stem:
                                                if self.info_cache.has_key(pkg_stem):
                                                        del self.info_cache[pkg_stem]
                                                self.__remove_pkg_stem_from_list(pkg_stem)
                # We need to reset status descriptions if a11y is enabled
                self.__set_visible_status(False)
                self.__process_package_selection()
                self.__enable_disable_selection_menus()
                self.__enable_disable_install_remove()
                self.update_statusbar()
                Thread(target = self.__enable_disable_update_all,
                    args = (False,)).start()

        def __catalog_refresh_message(self, cre):
                total = cre.total
                succeeded = cre.succeeded
                ermsg = _("Network problem.\n\n")
                ermsg += _("Details:\n")
                ermsg += "%s/%s" % (succeeded, total)
                ermsg += _(" catalogs successfully updated:\n")
                for pub, err in cre.failed:
                        ermsg += "%s: %s\n" % (pub["origin"], str(err))
                gobject.idle_add(self.error_occurred, ermsg,
                    None, gtk.MESSAGE_INFO)

        @staticmethod
        def __find_root_home_dir():
                return_str = '/var/tmp'
                 
                try:
                        lines = pwd.getpwnam('root')
                except KeyError:
                        if debug:
                                print "Error getting passwd database entry for root"
                        return return_str
                try:
                        return_str = lines[5]
                except IndexError:
                        if debug:
                                print "Error getting home directory for root"
                return return_str

        def restart_after_ips_update(self, be_name):
                self.__main_application_quit(be_name)

        def shutdown_after_image_update(self):
                info_str = _("The Update All action is now complete and "
                    "Package Manager will close.\n\nReview the posted release notes "
                    "before rebooting your system:\n\n"
                    )
                self.w_ua_completed_release_label.set_text(info_str.strip('\n'))

                info_str = misc.get_release_notes_url()
                self.w_ua_completed_linkbutton.set_uri(info_str)
                self.w_ua_completed_linkbutton.set_label(info_str)
                self.release_notes_url = info_str
                
                self.w_ua_completed_dialog.set_title(_("Update All Complete"))
                self.w_ua_completed_dialog.show()

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def main():
        gtk.main()
        return 0

if __name__ == '__main__':
        debug = False
        debug_descriptions = False
        max_filter_length = 0
        update_all_proceed = False
        ua_be_name = None
        app_path = None
        image_dir = None
        info_install_arg = None
        save_selected = _("Save selected...")
        save_selected_pkgs = _("Save selected packages...")
        reboot_needed = _("The installed package(s) require a reboot before "
            "installation can be completed.")

        try:
                opts, args = getopt.getopt(sys.argv[1:], "hR:U:i:", \
                    ["help", "image-dir=", "update-all=", "info-install="])
        except getopt.error, msg:
                print "%s, for help use --help" % msg
                sys.exit(2)

        if os.path.isabs(sys.argv[0]):
                app_path = sys.argv[0]
        else:
                cmd = os.path.join(os.getcwd(), sys.argv[0])
                app_path = os.path.realpath(cmd)

        for option, argument in opts:
                if option in ("-h", "--help"):
                        print """\
Use -R (--image-dir) to specify image directory.
Use -U (--update-all) to proceed with Update All"""
                        sys.exit(0)
                if option in ("-R", "--image-dir"):
                        image_dir = argument
                if option in ("-U", "--update-all"):
                        update_all_proceed = True
                        ua_be_name = argument
                if option in ("-i", "--info-install"):
                        info_install_arg = argument

        if image_dir == None:
                try:
                        image_dir = os.environ["PKG_IMAGE"]
                except KeyError:
                        image_dir = os.getcwd()
        try:
                gtk.init_check()
        except RuntimeError, e:
                print _("Unable to initialize gtk")
                print str(e)
                sys.exit(1)

        # Setup webinstall
        if info_install_arg or len(sys.argv) == 2:
                webinstall = webinstall.Webinstall(image_dir)
                if len(sys.argv) == 2:
                        info_install_arg = sys.argv[1]
                webinstall.process_param(info_install_arg)
                main()
                sys.exit(0)

        # Setup packagemanager
        packagemanager = PackageManager()
        packagemanager.application_path = app_path
        packagemanager.image_dir_arg = image_dir
        packagemanager.update_all_proceed = update_all_proceed
        packagemanager.ua_be_name = ua_be_name

        while gtk.events_pending():
                gtk.main_iteration(False)

        max_filter_length = packagemanager.init_show_filter()

        packagemanager.process_package_list_start(image_dir)

        main()
