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

MAX_INFO_CACHE_LIMIT = 100                # Max number of package descriptions to cache
NOTEBOOK_PACKAGE_LIST_PAGE = 0            # Main Package List page index
NOTEBOOK_START_PAGE = 1                   # Main View Start page index
INFO_NOTEBOOK_LICENSE_PAGE = 3            # License Tab index
PM_LAUNCH_OPEN_CMD = "pm-launch: OPEN:"   # Command to tell pm-launch to open link.
PUBLISHER_INSTALLED = 0                   # Index for "All Publishers (Installed)" string
PUBLISHER_ALL = 1                         # Index for "All Publishers (Search)" string
PUBLISHER_ADD = 2                         # Index for "Add..." string
SHOW_INFO_DELAY = 600       # Delay before showing selected package information
SHOW_LICENSE_DELAY = 600    # Delay before showing license information
RESIZE_DELAY = 600          # Delay before handling resize for startpage
SEARCH_STR_FORMAT = "<%s>"
MIN_APP_WIDTH = 750                       # Minimum application width
MIN_APP_HEIGHT = 500                      # Minimum application height
SECTION_ID_OFFSET = 10000                 # Offset to allow Sections to be identified 
                                          # in category tree
RECENT_SEARCH_ID_OFFSET = 10999           # Offset to allow Recent Search Sections
                                          # to be identified in category tree
RECENT_SEARCH_ID = RECENT_SEARCH_ID_OFFSET + 1 #  Recent Search Section ID
CATEGORY_TOGGLE_ICON_WIDTH = 16           # Width of category toggle icon
PACKAGEMANAGER_PREFERENCES = "/apps/packagemanager/preferences"
MAX_SEARCH_COMPLETION_PREFERENCES = \
        "/apps/packagemanager/preferences/max_search_completion"
INITIAL_APP_WIDTH_PREFERENCES = "/apps/packagemanager/preferences/initial_app_width"
INITIAL_APP_HEIGHT_PREFERENCES = "/apps/packagemanager/preferences/initial_app_height"
INITIAL_APP_HPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_hposition"
INITIAL_APP_VPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_vposition"
INITIAL_SHOW_FILTER_PREFERENCES = "/apps/packagemanager/preferences/initial_show_filter"
INITIAL_SECTION_PREFERENCES = "/apps/packagemanager/preferences/initial_section"
LAST_EXPORT_SELECTION_PATH = \
        "/apps/packagemanager/preferences/last_export_selections_path"
SHOW_STARTPAGE_PREFERENCES = "/apps/packagemanager/preferences/show_startpage"
SHOW_IMAGE_UPDATE_CONFIRMATION = "/apps/packagemanager/preferences/imageupdate_confirm"
SHOW_INSTALL_CONFIRMATION = "/apps/packagemanager/preferences/install_confirm"
SHOW_REMOVE_CONFIRMATION = "/apps/packagemanager/preferences/remove_confirm"
SAVE_STATE_PREFERENCES = "/apps/packagemanager/preferences/save_state"
START_INSEARCH_PREFERENCES = "/apps/packagemanager/preferences/start_insearch"
LASTSOURCE_PREFERENCES = "/apps/packagemanager/preferences/lastsource"
API_SEARCH_ERROR_PREFERENCES = "/apps/packagemanager/preferences/api_search_error"
STATUS_COLUMN_INDEX = 2   # Index of Status Column in Application TreeView
SEARCH_TXT_GREY_STYLE = "#757575" #Close to DimGrey
SEARCH_TXT_BLACK_STYLE = "#000000"
GDK_2BUTTON_PRESS = 5     # gtk.gdk._2BUTTON_PRESS causes pylint warning
GDK_RIGHT_BUTTON = 3      # normally button 3 = right click

# Location for themable icons
ICON_LOCATION = "usr/share/package-manager/icons"
# Load Start Page from lang dir if available
START_PAGE_CACHE_LANG_BASE = "var/pkg/gui_cache/startpagebase/%s/%s"
START_PAGE_LANG_BASE = "usr/share/package-manager/data/startpagebase/%s/%s"
START_PAGE_HOME = "startpage.html" # Default page
START_PAGE_IMAGES_BASE = "/usr/share/package-manager/data/startpagebase/C"

# StartPage Action support for url's on StartPage pages
PM_ACTION = 'pm-action'          # Action field for StartPage url's

# Internal Example: <a href="pm?pm-action=internal&uri=top_picks.html">
ACTION_INTERNAL = 'internal'   # Internal Action value: pm-action=internal
INTERNAL_URI = 'uri'           # Internal field: uri to navigate to in StartPage
                               # without protocol scheme specified
INTERNAL_SEARCH = 'search'     # Internal field: search support page action
INTERNAL_SEARCH_VIEW_RESULTS = "view_recent_search"
                               # Internal field: view recent search results
INTERNAL_SEARCH_VIEW_PUB ="view_pub_packages" # Internal field: view publishers packages
INTERNAL_SEARCH_VIEW_ALL = "view_all_packages_filter" # Internal field: change to View 
                                                      # All Packages
INTERNAL_SEARCH_ALL_PUBS = "search_all_publishers" #Internal field: search all publishers
INTERNAL_SEARCH_ALL_PUBS_INSTALLED = "search_all_publishers_installed"
                               #Internal field: search all publishers installed
INTERNAL_SEARCH_HELP = "search_help" # Internal field: display search help

# External Example: <a href="pm?pm-action=external&uri=www.opensolaris.com">
ACTION_EXTERNAL = 'external'   # External Action value: pm-action=external
EXTERNAL_URI = 'uri'           # External field: uri to navigate to in external
                               # default browser without protocol scheme specified
EXTERNAL_PROTOCOL = 'protocol' # External field: optional protocol scheme,
                               # defaults to http
DEFAULT_PROTOCOL = 'http'
INFORMATION_PAGE_HEADER = (
            "<table border='0' cellpadding='3' style='table-layout:fixed' >"
            "<TR><TD><IMG SRC = '%s/dialog-information.png' style='border-style: none' "
            ) % START_PAGE_IMAGES_BASE                  

import getopt
import pwd
import os
import sys
import time
import locale
import itertools
import urllib
import urlparse
import socket
import gettext
import signal
import threading
import re
import stat
import tempfile
from xml.sax import saxutils
from threading import Thread
from threading import Lock
from collections import deque
from gettext import ngettext
import traceback
from cStringIO import StringIO

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

logger = global_settings.logger

# Put _() in the global namespace
import __builtin__
__builtin__._ = gettext.gettext

(
DISPLAY_LINK,
CLICK_LINK,
) = range(2)

REGEX_BOLD_MARKUP = re.compile(r'^<b>')
REGEX_STRIP_MARKUP = re.compile(r'<.*?>')
REGEX_STRIP_RESULT = re.compile(r'\(\d+\) ?')

class PackageManager:
        def __init__(self):
                self.allow_links = False
                self.before_start = True
                signal.signal(signal.SIGINT, self.__main_application_quit)
                self.user_rights = portable.is_admin()
                self.__reset_home_dir()
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
                        self.last_export_selection_path = \
                            self.client.get_string(LAST_EXPORT_SELECTION_PATH)
                        self.show_startpage = \
                            self.client.get_bool(SHOW_STARTPAGE_PREFERENCES)
                        self.save_state = \
                            self.client.get_bool(SAVE_STATE_PREFERENCES)
                        self.show_image_update = \
                            self.client.get_bool(SHOW_IMAGE_UPDATE_CONFIRMATION)
                        self.show_install = \
                            self.client.get_bool(SHOW_INSTALL_CONFIRMATION)
                        self.show_remove = \
                            self.client.get_bool(SHOW_REMOVE_CONFIRMATION)
                        self.start_insearch = \
                            self.client.get_bool(START_INSEARCH_PREFERENCES)
                        self.lastsource = \
                            self.client.get_string(LASTSOURCE_PREFERENCES)
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
                        self.client.add_dir(PACKAGEMANAGER_PREFERENCES,
                            gconf.CLIENT_PRELOAD_NONE)
                        self.client.notify_add(SHOW_IMAGE_UPDATE_CONFIRMATION,
                            self.__show_image_update_changed)
                        self.client.notify_add(SHOW_INSTALL_CONFIRMATION,
                            self.__show_install_changed)
                        self.client.notify_add(SHOW_REMOVE_CONFIRMATION,
                            self.__show_remove_changed)
                        self.client.notify_add(SAVE_STATE_PREFERENCES,
                            self.__save_state_changed)
                except GError:
                        # Default values - the same as in the 
                        # packagemanager-preferences.schemas
                        self.max_search_completion = 20
                        self.initial_show_filter = 0
                        self.initial_section = 2
                        self.last_export_selection_path = ""
                        self.show_startpage = True
                        self.show_image_update = True
                        self.show_install = True
                        self.show_remove = True
                        self.save_state = True
                        self.start_insearch = False
                        self.lastsource = ""
                        self.gconf_not_show_repos = ""
                        self.initial_app_width = 800
                        self.initial_app_height = 600
                        self.initial_app_hpos = 200
                        self.initial_app_vpos = 320

                self.__fix_initial_values()

                self.set_section = 0
                self.after_install_remove = False
                self.in_search_mode = False
                self.in_recent_search = False
                self.recent_searches = {}
                self.recent_searches_cat_iter = None
                self.adding_recent_search = False
                self.recent_searches_list = []
                self.previous_search_text = None
                
                global_settings.client_name = gui_misc.get_pm_name()

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
                self.cancelled = False                    # For background processes
                self.description_queue = deque()
                self.description_thread_running = False
                self.image_directory = None
                gtk.rc_parse('~/.gtkrc-1.2-gnome2')       # Load gtk theme
                self.progress_stop_thread = True
                self.update_all_proceed = False
                self.application_path = None
                self.default_publisher = None
                self.current_repos_with_search_errors = []
                self.exiting = False
                self.first_run = True
                self.selected_pkgstem = None
                self.selected_model = None
                self.selected_path = None
                self.info_cache = {}
                self.all_selected = 0
                self.selected_pkgs = {}
                self.package_names = {}
                self.special_package_names = []
                self.link_load_page = ""
                self.start_page_url = None
                self.to_install_update = {}
                self.to_remove = {}
                self.in_startpage_startup = self.show_startpage
                self.lang = None
                self.lang_root = None
                self.visible_status_id = 0
                self.same_publisher_on_setup = False
                self.force_reload_packages = True
                self.icon_theme = gtk.icon_theme_get_default()
                icon_location = os.path.join(self.application_dir, ICON_LOCATION)
                self.icon_theme.append_search_path(icon_location)
                self.installed_icon = gui_misc.get_icon(self.icon_theme,
                    'status_installed')
                self.not_installed_icon = gui_misc.get_icon(self.icon_theme,
                    'status_notinstalled')
                self.update_available_icon = gui_misc.get_icon(self.icon_theme,
                    'status_newupdate')
                self.window_icon = gui_misc.get_icon(self.icon_theme,
                    'packagemanager', 48)
                self.filter_options = [
                    (enumerations.FILTER_ALL,
                    gui_misc.get_icon(self.icon_theme, 'filter_all'),
                    _('All Packages')),
                    (enumerations.FILTER_INSTALLED, self.installed_icon,
                    _('Installed Packages')),
                    (enumerations.FILTER_UPDATES, self.update_available_icon,
                    _('Updates')),
                    (enumerations.FILTER_NOT_INSTALLED, self.not_installed_icon,
                    _('Not Installed Packages')),
                    (-1, None, ""),
                    (enumerations.FILTER_SELECTED,
                    gui_misc.get_icon(self.icon_theme, 'filter_selected'),
                    _('Selected Packages'))
                    ]
                self.publisher_options = { 
                    PUBLISHER_INSTALLED : _("All Publishers (Installed)"),
                    PUBLISHER_ALL : _("All Publishers (Search)"),
                    PUBLISHER_ADD : _("Add...")
                    }
                self.pubs_info = {}
                self.pubs_display_name = {}
                self.last_visible_publisher = None
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
                self.repo_combobox_all_pubs_installed_index = 0
                self.repo_combobox_all_pubs_index = 0
                self.repo_combobox_add_index = 0
                self.pr = progress.NullProgressTracker()
                self.pylintstub = None
                self.__image_activity_lock = Lock()
                self.category_expanded_paths = {}
                self.category_active_paths = {}
                self.error_logged = False
                
                self.use_cache = False # Turns off Details Description cache
                                       # Search history cache is always on
                                       # Caching package list is removed

                # Create Widgets and show gui
                self.gladefile = os.path.join(self.application_dir,
                    "usr/share/package-manager/packagemanager.glade")
                w_tree_main = gtk.glade.XML(self.gladefile, "mainwindow")
                w_tree_preferences = gtk.glade.XML(self.gladefile, "preferencesdialog")
                w_tree_api_search_error = gtk.glade.XML(self.gladefile,
                    "api_search_error")
                self.w_preferencesdialog = \
                    w_tree_preferences.get_widget("preferencesdialog")
                self.w_preferencesdialog.set_icon(self.window_icon)
                self.w_startpage_checkbutton = \
                    w_tree_preferences.get_widget("startpage_checkbutton")
                self.w_exit_checkbutton = \
                    w_tree_preferences.get_widget("exit_checkbutton")
                self.w_confirm_updateall_checkbutton = \
                    w_tree_preferences.get_widget("confirm_updateall_checkbutton")
                self.w_confirm_install_checkbutton = \
                    w_tree_preferences.get_widget("confirm_install_checkbutton")
                self.w_confirm_remove_checkbutton = \
                    w_tree_preferences.get_widget("confirm_remove_checkbutton")
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
                w_tree_confirm = gtk.glade.XML(self.gladefile, "confirmationdialog")
                self.w_exportconfirm_dialog = \
                    w_tree_confirm.get_widget("confirmationdialog")
                self.w_exportconfirm_dialog.set_icon(self.window_icon)
                self.w_confirmok_button = w_tree_confirm.get_widget("ok_conf")
                self.w_confirmhelp_button = w_tree_confirm.get_widget("help_conf")
                self.w_confirm_textview = w_tree_confirm.get_widget("confirmtext")
                self.w_confirm_label = w_tree_confirm.get_widget("confirm_label")
                w_confirm_image = w_tree_confirm.get_widget("confirm_image")
                w_confirm_image.set_from_stock(gtk.STOCK_DIALOG_INFO,
                    gtk.ICON_SIZE_DND)
                self.__setup_export_selection_dialog()

                w_log = gtk.glade.XML(self.gladefile,
                    "view_log_dialog")
                self.w_view_log_dialog = \
                    w_log.get_widget("view_log_dialog")
                self.w_view_log_dialog.set_icon(self.window_icon)
                self.w_view_log_dialog.set_title(_("Logs"))
                self.w_log_info_textview = w_log.get_widget("log_info_textview")
                self.w_log_errors_textview = w_log.get_widget("log_errors_textview")
                infobuffer = self.w_log_info_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)                
                infobuffer = self.w_log_errors_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)                
                self.w_log_close_button = w_log.get_widget("log_close_button")
                
                w_version_info = gtk.glade.XML(self.gladefile,
                    "version_info_dialog")
                self.w_version_info_dialog = \
                    w_version_info.get_widget("version_info_dialog")
                self.w_info_name_label = w_version_info.get_widget("info_name")
                self.w_info_installed_label = w_version_info.get_widget("info_installed")
                self.w_info_installable_label = w_version_info.get_widget(
                    "info_installable")
                self.w_info_installable_prefix_label = w_version_info.get_widget(
                    "info_installable_label")
                self.w_info_ok_button = w_version_info.get_widget("info_ok_button")
                self.w_info_expander = w_version_info.get_widget("version_info_expander")
                self.w_info_textview = w_version_info.get_widget("infotextview")
                infobuffer = self.w_info_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)                
                self.w_main_window = w_tree_main.get_widget("mainwindow")
                self.w_main_window.set_icon(self.window_icon)
                self.w_main_hpaned = \
                    w_tree_main.get_widget("main_hpaned")
                self.w_main_vpaned = \
                    w_tree_main.get_widget("main_vpaned")

                self.w_application_treeview = \
                    w_tree_main.get_widget("applicationtreeview")
                self.w_application_treeview.connect('key_press_event',
                    self.__on_applicationtreeview_button_and_key_events)
                self.w_application_treeview.set_enable_search(True)
                self.w_application_treeview.set_search_equal_func(
                      self.__applicationtreeview_compare_func)

                self.w_categories_treeview = w_tree_main.get_widget("categoriestreeview")
                self.w_categories_treeview.set_search_equal_func(
                    self.__categoriestreeview_compare_func)

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
                self.w_startpage_scrolled_window = \
                    w_tree_main.get_widget("startpage_scrolled_window")
                self.w_startpage_eventbox = \
                    w_tree_main.get_widget("startpage_eventbox")
                self.w_startpage_eventbox.modify_bg(gtk.STATE_NORMAL,
                    gtk.gdk.color_parse("white"))

                self.w_main_statusbar = w_tree_main.get_widget("statusbar")
                #Allow markup in StatusBar
                self.w_main_statusbar_label = \
                        self.__get_statusbar_label(self.w_main_statusbar)
                if self.w_main_statusbar_label != None:
                        self.w_main_statusbar_label.set_use_markup(True) 
    
                self.w_statusbar_hbox = w_tree_main.get_widget("statusbar_hbox")
                self.w_infosearch_frame = w_tree_main.get_widget("infosearch_frame")

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
                self.w_repository_combobox = w_tree_main.get_widget("repositorycombobox")
                self.w_filter_combobox = w_tree_main.get_widget("filtercombobox")
                self.w_packageicon_image = w_tree_main.get_widget("packageimage")
                self.w_reload_menuitem = w_tree_main.get_widget("file_reload")
                self.__set_icon(self.w_reload_button, self.w_reload_menuitem,
                    'pm-refresh')
                self.w_version_info_menuitem = \
                    w_tree_main.get_widget("package_version_info")
                self.w_version_info_menuitem.set_sensitive(False)
                self.w_installupdate_menuitem = \
                    w_tree_main.get_widget("package_install_update")
                self.__set_icon(self.w_installupdate_button, 
                    self.w_installupdate_menuitem, 'pm-install_update')
                self.w_remove_menuitem = w_tree_main.get_widget("package_remove")
                self.__set_icon(self.w_remove_button, self.w_remove_menuitem, 
                    'pm-remove')
                self.w_updateall_menuitem = w_tree_main.get_widget("package_update_all")
                self.__set_icon(self.w_updateall_button,
                    self.w_updateall_menuitem, 'pm-update_all')
                self.w_export_selections_menuitem = w_tree_main.get_widget(
                    "file_export_selections")
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
                self.search_button = w_tree_main.get_widget("do_search")
                self.progress_cancel = w_tree_main.get_widget("progress_cancel")
                self.is_all_publishers = False
                self.is_all_publishers_installed = False
                self.saved_repository_combobox_active = -1
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
                self.w_main_window.set_title(self.main_window_title)

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
                                "on_mainwindow_style_set": \
                                    self.__on_mainwindow_style_set,
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
                                "on_file_export_selections": \
                                        self.__on_file_export_selections,
                                "on_file_quit_activate":self.__on_file_quit_activate,
                                "on_file_be_activate":self.__on_file_be_activate,
                                "on_package_version_info_activate": \
                                    self.__on_version_info,
                                "on_package_install_update_activate": \
                                    self.__on_install_update,
                                "on_file_manage_publishers_activate": \
                                    self.__on_file_manage_publishers,
                                "on_file_add_publisher_activate": \
                                    self.__on_file_add_publisher,
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
                                "on_log_activate":self.__on_log_activate,
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
                                "on_infosearch_eventbox_button_press_event": \
                                    self.__on_infosearch_button_press_event,
                                "on_applicationtreeview_button_press_event": \
                                    self.__on_applicationtreeview_button_and_key_events,
                                "on_applicationtreeview_query_tooltip": \
                                    self.__on_applicationtreeview_query_tooltip,
                            }
                        dic_preferences = \
                            {
                                "on_preferencesdialog_delete_event": \
                                    self.__on_preferencesdialog_delete_event,
                                "on_startpage_checkbutton_toggled": \
                                    self.__on_startpage_checkbutton_toggled,
                                "on_exit_checkbutton_toggled": \
                                    self.__on_exit_checkbutton_toggled,
                                "on_confirm_updateall_checkbutton_toggled": \
                                    self.on_confirm_updateall_checkbutton_toggled,
                                "on_confirm_install_checkbutton_toggled": \
                                    self.on_confirm_install_checkbutton_toggled,
                                "on_confirm_remove_checkbutton_toggled": \
                                    self.on_confirm_remove_checkbutton_toggled,
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
                            
                        dic_version_info = \
                            {
                                "on_info_ok_clicked": \
                                    self.__on_info_ok_button_clicked,
                                "on_info_help_clicked": \
                                    self.__on_info_help_button_clicked,
                                "on_version_info_dialog_delete_event": \
                                    self.__on_version_info_dialog_delete_event,
                            }
                            
                        dic_log = \
                            {
                                "on_log_close_button_clicked": \
                                    self.__on_log_close_button_clicked,
                                "on_view_log_dialog_delete_event": \
                                    self.__on_log_dialog_delete_event
                            }
                            
                        w_tree_confirm.signal_autoconnect(dic_confirm)
                        w_tree_main.signal_autoconnect(dic_mainwindow)
                        w_tree_preferences.signal_autoconnect(dic_preferences)
                        w_tree_api_search_error.signal_autoconnect(
                            dic_api_search_error)
                        w_version_info.signal_autoconnect(dic_version_info)
                        w_log.signal_autoconnect(dic_log)
                except AttributeError, error:
                        print _(
                            "GUI will not respond to any event! %s. "
                            "Check declare_signals()") \
                            % error

                self.package_selection = None
                self.application_list_filter = None
                self.application_list_sort = None
                self.application_refilter_id = 0
                self.application_refilter_idle_id = 0
                self.last_status_id = 0
                self.last_show_info_id = 0
                self.show_info_id = 0
                self.last_show_licenses_id = 0
                self.show_licenses_id = 0
                self.resize_id = 0
                self.last_resize = (0, 0)
                self.showing_empty_details = False
                self.in_setup = True
                self.__set_initial_sizes()
                self.w_main_window.show_all()
                self.__setup_busy_cursor()
                if self.show_startpage:
                        self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                else:
                        self.w_main_view_notebook.set_current_page(
                            NOTEBOOK_PACKAGE_LIST_PAGE)
                gui_misc.set_modal_and_transient(self.api_search_error_dialog,
                    self.w_main_window)
                gui_misc.set_modal_and_transient(self.w_version_info_dialog,
                    self.w_main_window)
                gui_misc.set_modal_and_transient(self.w_view_log_dialog,
                    self.w_main_window)
                gui_misc.set_modal_and_transient(self.w_preferencesdialog,
                    self.w_main_window)

                self.__setup_text_signals()
                gui_misc.setup_logging(gui_misc.get_pm_name())
                
        def __set_initial_sizes(self):
                if self.initial_app_width >= MIN_APP_WIDTH and \
                        self.initial_app_height >= MIN_APP_HEIGHT:
                        self.w_main_window.resize(self.initial_app_width,
                            self.initial_app_height)
                if self.initial_app_hpos > 0:
                        self.w_main_hpaned.set_position(self.initial_app_hpos)
                if self.initial_app_vpos > 0:
                        self.w_main_vpaned.set_position(self.initial_app_vpos)

        def __setup_busy_cursor(self):
                gdk_win = self.w_main_window.get_window()
                self.gdk_window = gtk.gdk.Window(gdk_win, gtk.gdk.screen_width(),
                    gtk.gdk.screen_height(), gtk.gdk.WINDOW_CHILD, 0, gtk.gdk.INPUT_ONLY)
                gdk_cursor = gtk.gdk.Cursor(gtk.gdk.WATCH)

                self.gdk_window.set_cursor(gdk_cursor)

        def __fix_initial_values(self):
                if self.initial_app_width == -1:
                        self.initial_app_width = 800
                if self.initial_app_height == -1:
                        self.initial_app_height = 600
                if self.initial_app_hpos == -1:
                        self.initial_app_hpos = 200
                if self.initial_app_vpos == -1:
                        self.initial_app_vpos = 320

                if not self.gconf_not_show_repos:
                        self.gconf_not_show_repos = ""
        @staticmethod
        def __set_icon(button, menuitem, icon_name):
                icon_source = gtk.IconSource()
                icon_source.set_icon_name(icon_name)
                icon_set = gtk.IconSet()
                icon_set.add_source(icon_source)
                image_widget = gtk.image_new_from_icon_set(icon_set,
                    gtk.ICON_SIZE_SMALL_TOOLBAR)
                button.set_icon_widget(image_widget)
                image_widget = gtk.image_new_from_icon_set(icon_set,
                    gtk.ICON_SIZE_MENU)
                menuitem.set_image(image_widget)

        @staticmethod
        def __get_statusbar_label(statusbar):
                sb_frame = None
                sb_label = None
                children = statusbar.get_children()
                if len(children) > 0:
                        sb_frame = children[0]
                if sb_frame and isinstance(sb_frame, gtk.Frame):
                        children = sb_frame.get_children()
                        if len(children) > 0:
                                sb_label = children[0]
                        if sb_label and isinstance(sb_label, gtk.Label):
                                return sb_label
                return None
                
        def __setup_export_selection_dialog(self):
                infobuffer = self.w_confirm_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.w_exportconfirm_dialog.set_title(_("Export Selections Confirmation"))
                self.w_confirm_label.set_markup(
                    _("<b>Export the following to a Web Install .p5i file:</b>"))
                self.w_confirmhelp_button.set_property('visible', True)

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

        def __on_file_export_selections(self, menuitem):
                if self.selected_pkgs == None or len(self.selected_pkgs) == 0:
                        return
                        
                infobuffer = self.w_confirm_textview.get_buffer()
                infobuffer.set_text("")
                textiter = infobuffer.get_end_iter()
                
                for pub_name, pkgs in self.selected_pkgs.items():
                        name = self.__get_publisher_name_from_prefix(pub_name)
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
                filename = self.__get_export_p5i_filename()
                if not filename:
                        return
                try:
                        fobj = open(filename, 'w')
                        self.api_o.write_p5i(fobj, pkg_names=self.selected_pkgs,
                            pubs=self.selected_pkgs.keys())
                except IOError, ex:
                        err = str(ex)
                        self.error_occurred(err, _("Export Selections Error"))
                        return
                except api_errors.ApiException, ex:
                        fobj.close()
                        err = str(ex)
                        self.error_occurred(err, _("Export Selections Error"))
                        return
                fobj.close()
                os.chmod(filename, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP |
                    stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH )

        def __get_export_p5i_filename(self):
                filename = None
                chooser = gtk.FileChooserDialog(_("Export Selections"), 
                    self.w_main_window,
                    gtk.FILE_CHOOSER_ACTION_SAVE,
                    (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                    gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        
                file_filter = gtk.FileFilter()
                file_filter.set_name(_("p5i Files"))
                file_filter.add_pattern("*.p5i")
                chooser.add_filter(file_filter)
                file_filter = gtk.FileFilter()
                file_filter.set_name(_("All Files"))
                file_filter.add_pattern("*")
                chooser.add_filter(file_filter)
                
                path = tempfile.gettempdir()
                name = _("my_packages")
                if self.last_export_selection_path and \
                        self.last_export_selection_path != "":
                        path, name_plus_ext = os.path.split(
                            self.last_export_selection_path)
                        name, ext = os.path.splitext(name_plus_ext)
                        self.pylintstub = ext

                #Check name
                base_name = None
                m = re.match("(.*)(-\d+)$", name)
                if m == None and os.path.exists(path + os.sep + name + '.p5i'):
                        base_name = name
                if m and len(m.groups()) == 2:
                        base_name = m.group(1)
                name = name + '.p5i'
                if base_name:
                        for i in range(1, 99):
                                full_path = path + os.sep + base_name + '-' + \
                                        str(i) + '.p5i'
                                if not os.path.exists(full_path):
                                        name = base_name + '-' + str(i) + '.p5i'
                                        break
                chooser.set_current_folder(path)
                chooser.set_current_name(name)
                chooser.set_do_overwrite_confirmation(True)

                response = chooser.run()
                if response == gtk.RESPONSE_OK:
                        filename = chooser.get_filename()
                        self.last_export_selection_path = filename
                chooser.destroy()

                return filename

        @staticmethod
        def __on_mainwindow_style_set(widget, previous_style):
                ''' This is called when theme is changed.
                We need to change the status icons in the Package List,
                the search icon and the icons in the filter list'''
                return
                
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
                # Load Start Page to setup base URL to allow loading images in other pages
                self.__load_startpage()
                if show_startpage:
                        self.w_main_view_notebook.set_current_page(
                                NOTEBOOK_START_PAGE)
                else:
                        if self.start_insearch:
                                self.document.clear()
                        self.w_main_view_notebook.set_current_page(
                                NOTEBOOK_PACKAGE_LIST_PAGE)
                self.w_startpage_scrolled_window.add(self.view)

        # Stub handler required by GtkHtml widget
        def __request_object(self, *vargs):
                pass

        def __load_startpage(self):
                self.link_load_page = ""
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
                    "load Start Page:<br>%s</font></body></html>")
                    % (start_page_url))
                self.document.close_stream()

        def __process_api_search_error(self, error):
                self.current_repos_with_search_errors = []

                for pub, err in error.failed_servers:
                        logger.error(_("Publisher:") + " " + pub + ": " +
                            _("failed to respond") + "\n" + str(err))
                        gui_misc.notify_log_error(self)
                for pub in error.invalid_servers:
                        logger.error(_("Publisher:") + " " + pub + ": " +
                            _("invalid response") + "\n" +
                            _("A valid response was not returned."))
                        gui_misc.notify_log_error(self)
                for pub, err in error.unsupported_servers:
                        self.current_repos_with_search_errors.append(
                            (pub, _("unsupported search"), err))

        def __on_infosearch_button_press_event(self, widget, event):
                if len(self.current_repos_with_search_errors) > 0:
                        self.__handle_api_search_error(True)
                        return
                if self.error_logged:
                        self.__on_log_activate(None)

        def __handle_api_search_error(self, show_all=False):
                if self.exiting:
                        return
                if len(self.current_repos_with_search_errors) == 0:
                        if not self.error_logged:
                                self.w_infosearch_frame.hide()
                        return

                repo_count = 0
                for pub, err_type, err_str in self.current_repos_with_search_errors:
                        if show_all or (pub not in self.gconf_not_show_repos):
                                repo_count += 1
                if repo_count == 0:
                        if not self.error_logged:
                                self.w_infosearch_frame.hide()
                        return

                self.w_infosearch_frame.set_tooltip_text(
                    _("Search Errors: click to view"))

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
                try:
                        f = self.__open_url(url)
                except  (IOError, OSError), err:
                        logger.error(str(err))
                        gui_misc.notify_log_error(self)
                        return
                stream.set_cancel_func(self.__stream_cancel)
                stream.write(f.read())

        # Stub handler required by GtkHtml widget or widget will assert
        def __stream_cancel(self, *vargs):
                pass

        def __load_uri(self, document, link):
                self.__update_statusbar_message(_("Loading... %s") % link)
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
                # The replace startpage_star.png is done as a change after
                # l10n code freeze.
                self.document.write_stream((_(
                    "<html><head></head><body><font color='#000000'>\
                    <a href='stub'></a></font>\
                    <a href='pm?%s=internal&uri=%s'>\
                    <IMG SRC = '%s/startpage_star.png' \
                    style='border-style: none'></a> <br><br>\
                    <h2><font color='#0000FF'>Warning: Unable to \
                    load URL</font></h2><br>%s</body></html>") % (PM_ACTION,
                    START_PAGE_HOME, START_PAGE_IMAGES_BASE, link)
                    ).replace("/startpage_star.png' ","/dialog-warning.png' "))
                self.document.close_stream()

        def __get_publisher_combobox_index(self, pub_name):
                index = -1
                model = self.w_repository_combobox.get_model()
                for entry in model:
                        if entry[enumerations.REPOSITORY_PREFIX] == pub_name:
                                index = entry[enumerations.REPOSITORY_ID]
                                break
                return index

        def __handle_browse_publisher(self, index):
                if index == -1:
                        return
                self.w_repository_combobox.grab_focus()
                self.w_repository_combobox.set_active(index)
                
        def __handle_search_all_publishers(self, term):
                self.__set_search_start()
                self.is_all_publishers_installed = False
                self.w_repository_combobox.set_active(self.repo_combobox_all_pubs_index)
                self.__set_search_text_mode(enumerations.SEARCH_STYLE_NORMAL)
                self.w_searchentry.set_text(term)
                gobject.idle_add(self.__do_search)

        def __handle_view_all_publishers_installed(self):
                self.w_filter_combobox.set_active(enumerations.FILTER_ALL)
                self.__set_main_view_package_list()
                self.update_statusbar()
                
        def __handle_link(self, document, link, handle_what = CLICK_LINK):
                query_dict = self.__urlparse_qs(link)

                action = None
                if query_dict.has_key(PM_ACTION):
                        action = query_dict[PM_ACTION][0]
                elif handle_what == DISPLAY_LINK:
                        return link
                ext_uri = ""
                protocol = None

                search_action = None
                if action == ACTION_INTERNAL:
                        if query_dict.has_key(INTERNAL_SEARCH):
                                search_action = query_dict[INTERNAL_SEARCH][0]
                
                if self.w_main_statusbar_label:
                        s1 = "<b>"
                        e1 = "</b>"
                else:
                        s1 = e1 = '"'

                # Browse a Publisher
                if search_action and search_action.find(INTERNAL_SEARCH_VIEW_PUB) > -1:
                        pub = re.findall(r'<b>(.*)<\/b>', search_action)[0]
                        if handle_what == DISPLAY_LINK:
                                pub_name = self.__get_publisher_display_name_from_prefix(
                                    pub)
                                return _("View packages in %(s1)s%(pub)s%(e1)s") % \
                                        {"s1": s1, "pub": \
                                        pub_name, "e1": e1}
                        index = self.__get_publisher_combobox_index(pub)
                        gobject.idle_add(self.__handle_browse_publisher, index)
                        return
                # Search in All Publishers
                if search_action and search_action == INTERNAL_SEARCH_ALL_PUBS:
                        if handle_what == DISPLAY_LINK:
                                return _("Search within %(s1)sAll Publishers%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.__handle_search_all_publishers(self.previous_search_text)
                        return
                # Change view to All Publishers (Installed)
                if search_action and search_action == INTERNAL_SEARCH_ALL_PUBS_INSTALLED:
                        if handle_what == DISPLAY_LINK:
                                return _("View installed packages for %(s1)sAll "
                                    "Publishers%(e1)s") % {"s1": s1, "e1": e1}
                        self.__handle_view_all_publishers_installed()
                        return
                # Change View to All Packages
                if search_action and search_action == INTERNAL_SEARCH_VIEW_ALL:
                        if handle_what == DISPLAY_LINK:
                                return _("Change View to %(s1)sAll Packages%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.w_filter_combobox.set_active(enumerations.FILTER_ALL)
                        self.w_filter_combobox.grab_focus()
                        return                        
                # Launch Search Help
                if search_action and search_action == INTERNAL_SEARCH_HELP:
                        if handle_what == DISPLAY_LINK:
                                return _("Display %(s1)sSearch Help%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.__update_statusbar_message(
                            _("Loading %(s1)sSearch Help%(e1)s ...") %
                            {"s1": s1, "e1": e1})
                        gui_misc.display_help("search-pkg")
                        return
                # View Recent Search Results
                if search_action and \
                        search_action.find(INTERNAL_SEARCH_VIEW_RESULTS) > -1:
                        recent_search = \
                                re.findall(r'<span>(.*)<\/span>', search_action)[0]
                        if handle_what == DISPLAY_LINK:
                                return _("View results for %s") % recent_search
                        category_tree = self.w_categories_treeview.get_model()
                        if category_tree == None:
                                return
                        rs_iter = category_tree.iter_children(
                            self.recent_searches_cat_iter)
                        while rs_iter:
                                rs_value = category_tree.get_value(rs_iter,
                                    enumerations.CATEGORY_VISIBLE_NAME)
                                if rs_value == recent_search:
                                        path = category_tree.get_path(rs_iter)
                                        self.w_categories_treeview.set_cursor(path)
                                        self.w_categories_treeview.scroll_to_cell(path)
                                        return
                                rs_iter = category_tree.iter_next(rs_iter)
                        return

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
                        self.__open_link(protocol + "://" + ext_uri)
                elif handle_what == DISPLAY_LINK:
                        return None
                elif action == None:
                        if link and link.endswith(".p5i"):
                                self.set_busy_cursor()
                                gobject.spawn_async([self.application_path, "-i", link])
                                gobject.timeout_add(1500, self.unset_busy_cursor)
                                return
                        self.__open_link(link)
                # Handle empty and unsupported actions
                elif action == "":
                        self.__link_load_error(_("Empty Action not supported"))
                        return
                elif action != None:
                        self.__link_load_error(_("Action not supported: %s") % action)
                        return

        def __open_link(self, link):
                self.set_busy_cursor()

                if not self.allow_links:
                        # Links not allowed.
                        self.__link_load_error(link)
                        self.unset_busy_cursor()
                        return
                elif not self.user_rights:
                        # Not a privileged user? Show links directly.
                        try:
                                gnome.url_show(link)
                                gobject.timeout_add(1000,
                                    self.unset_busy_cursor)
                        except gobject.GError:
                                self.__link_load_error(link)
                                self.unset_busy_cursor()
                        return

                # XXX PackageManager shouldn't run as a privileged user!
                # Opening links relies on the packagemanager having been
                # launched by the pm-launch process.  The pm-launch process
                # monitors the output of its child process for special commands
                # such as the one used to below to launch links.  This causes
                # the pm-launch program to open this link as the original user
                # that executed pm-launch instead of as the current, privileged
                # user the packagemanager is likely running as.
                try:
                        # XXX There's no way to know if opening the link failed
                        # using this method; the assumption is that the user
                        # will be informed somehow by the launcher or browser.
                        print "%s%s" % (PM_LAUNCH_OPEN_CMD, link)
                        sys.stdout.flush()
                        gobject.timeout_add(1000, self.unset_busy_cursor)
                except Exception, e:
                        # Any exception from the above likely means that the
                        # link wasn't loaded.  For example, an IOError or
                        # some other exception might be raised if the launch
                        # process was killed.
                        self.__link_load_error(link)
                        self.unset_busy_cursor()

                        # Log the error for post-mortem evaluation.
                        logger.error(str(e))

        def __link_load_page(self, text =""):
                self.link_load_page = text
                self.document.clear()
                self.document.open_stream('text/html')
                display = ("<html><head><meta http-equiv='Content-Type' "
                        "content='text/html; charset=UTF-8'></head><body>%s</body>"
                        "</html>" % text)
                self.document.write_stream(display)
                self.document.close_stream()

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
                        gobject.TYPE_STRING,      # enumerations.ACTUAL_NAME_COLUMN
                        gobject.TYPE_BOOLEAN,     # enumerations.IS_VISIBLE_COLUMN
                        gobject.TYPE_PYOBJECT,    # enumerations.CATEGORY_LIST_COLUMN
                        gobject.TYPE_STRING,      # enumerations.PUBLISHER_COLUMN
                        gobject.TYPE_STRING       # enumerations.PUBLISHER_PREFIX_COLUMN
                        )

        @staticmethod
        def __get_new_category_liststore():
                return gtk.TreeStore(
                        gobject.TYPE_INT,         # enumerations.CATEGORY_ID
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_NAME
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_VISIBLE_NAME
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_DESCRIPTION
                        gobject.TYPE_PYOBJECT,    # enumerations.SECTION_LIST_OBJECT
                        gobject.TYPE_BOOLEAN,     # enumerations.CATEGORY_IS_VISIBLE
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
                        gobject.TYPE_STRING,      # enumerations.REPOSITORY_DISPLAY_NAME
                        gobject.TYPE_STRING,      # enumerations.REPOSITORY_PREFIX
                        gobject.TYPE_STRING,      # enumerations.REPOSITORY_ALIAS
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
                            enumerations.STATUS_ICON_COLUMN, 
                            self.__column_sort_func, 
                            enumerations.STATUS_ICON_COLUMN)
                        application_list_sort.set_sort_func(
                            enumerations.DESCRIPTION_COLUMN, 
                            self.__column_sort_func, 
                            enumerations.DESCRIPTION_COLUMN)
                toggle_renderer = gtk.CellRendererToggle()

                column = gtk.TreeViewColumn("", toggle_renderer,
                    active = enumerations.MARK_COLUMN)
                column.set_cell_data_func(toggle_renderer, self.cell_data_function, None)
                column.set_clickable(True)
                column.connect('clicked', self.__select_column_clicked)
                self.w_application_treeview.append_column(column)
                select_image = gtk.Image()
                select_image.set_from_pixbuf(gui_misc.get_icon(
                    self.icon_theme, 'selection'))
                select_image.set_tooltip_text(_("Click to toggle selections"))
                select_image.show()
                column.set_widget(select_image)

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
                if self.is_all_publishers or self.is_all_publishers_installed or \
                        self.in_recent_search:
                        repository_renderer = gtk.CellRendererText()
                        column = gtk.TreeViewColumn(_('Publisher'),
                            repository_renderer,
                            markup = enumerations.PUBLISHER_COLUMN)
                        column.set_sort_column_id(enumerations.PUBLISHER_COLUMN)
                        column.set_resizable(True)
                        column.set_sort_indicator(True)
                        column.set_cell_data_func(repository_renderer,
                            self.cell_data_function, None)
                        column.connect_after('clicked',
                            self.__application_treeview_column_sorted, None)
                        self.w_application_treeview.append_column(column)
                        application_list_sort.set_sort_func(
                            enumerations.PUBLISHER_COLUMN, 
                            self.__column_sort_func, 
                            enumerations.PUBLISHER_COLUMN)
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
                if self.exiting:
                        return
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

                category_selection = self.w_categories_treeview.get_selection()
                if category_list != None:
                        ##CATEGORIES TREEVIEW
                        enumerations.CATEGORY_VISIBLE_NAME_r = gtk.CellRendererText()
                        column = gtk.TreeViewColumn(_('Name'),
                            enumerations.CATEGORY_VISIBLE_NAME_r,
                            markup = enumerations.CATEGORY_VISIBLE_NAME)
                        enumerations.CATEGORY_VISIBLE_NAME_r.set_property("xalign", 0.0)
                        self.w_categories_treeview.append_column(column)
                        #Added selection listener
                        category_selection.set_mode(gtk.SELECTION_SINGLE)
                        self.w_categories_treeview.set_search_column(
                            enumerations.CATEGORY_VISIBLE_NAME)

                if section_list != None:
                        self.section_list = section_list
                if category_list != None:
                        self.category_list = category_list

                if application_list != None:
                        self.w_application_treeview.set_model(
                            self.application_list_sort)
                        if application_list_filter == None:
                                self.application_list_filter.set_visible_func(
                                    self.__application_filter)

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
                obj = self.a11y_application_treeview.get_column_header(0)
                if obj != None:
                        obj.set_name(_("all selection toggle"))
                self.process_package_list_end()

        def __setup_filter_combobox(self):
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
                self.w_filter_combobox.set_model(self.filter_list)
                self.w_filter_combobox.set_active(self.initial_show_filter)

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
                    enumerations.REPOSITORY_DISPLAY_NAME)
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
                if status == api.PackageInfo.INSTALLED:
                        desc = _("Installed")
                elif status == api.PackageInfo.KNOWN:
                        desc = _("Not Installed")
                elif status == api.PackageInfo.UPGRADABLE:
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

                if not a11y_enabled:
                        return

                visible_range = self.w_application_treeview.get_visible_range()
                if visible_range == None:
                        return
                a11y_start = visible_range[0][0]
                a11y_end = visible_range[1][0]

                # We use check_range only for accessibility purposes to
                # reduce the amount of processing to be done in that case.
                # Switching Publishers need to use default range
                if self.publisher_changed:
                        check_range = False
                        self.publisher_changed = False
                if self.in_search_mode:
                        check_range = False
                
                if self.application_treeview_range != None:
                        if check_range and a11y_enabled:
                                old_start = self.application_treeview_range[0][0]
                                old_end = self.application_treeview_range[1][0]
                                 # Old range is the same or smaller than new range
                                 # so do nothing
                                if (a11y_start >= old_start and 
                                    a11y_end <= old_end):
                                        a11y_end =  a11y_start - 1
                                else:
                                        if a11y_start < old_end:
                                                if a11y_end < old_end:
                                                        if a11y_end >= old_start:
                                                                a11y_end = old_start
                                                else:
                                                        a11y_start = old_end
                self.application_treeview_range = visible_range

                sort_filt_model = \
                    self.w_application_treeview.get_model() #gtk.TreeModelSort

                if a11y_enabled:
                        sf_itr = sort_filt_model.get_iter_from_string(
                            str(a11y_start))                
                        while a11y_start <= a11y_end:
                                self.__set_accessible_status(sort_filt_model, sf_itr)
                                a11y_start += 1
                                sf_itr = sort_filt_model.iter_next(sf_itr)

        def __doing_search(self):
                return self.search_start > 0
                
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
                if self.w_application_treeview:
                        self.w_application_treeview.set_model(None)
                if self.w_categories_treeview:
                        self.w_categories_treeview.set_model(None)

        def __disconnect_repository_model(self):
                self.w_repository_combobox.set_model(None)

        @staticmethod
        def __column_sort_func(treemodel, iter1, iter2, column):
                get_val = treemodel.get_value
                get_val = treemodel.get_value
                status1 = get_val(iter1, column)
                status2 = get_val(iter2, column)
                ret = cmp(status1, status2)
                if ret != 0:
                        return ret
                name1 = get_val(iter1, enumerations.NAME_COLUMN)
                name2 = get_val(iter2, enumerations.NAME_COLUMN)
                return cmp(name1, name2)

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
                        if event.type == gtk.gdk.KEY_PRESS:
                                keyname = gtk.gdk.keyval_name(event.keyval)
                                if keyname == "Escape" and self.api_o.can_be_canceled():
                                        Thread(target = self.api_o.cancel,
                                            args = ()).start()
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

        def __handle_resize(self, widget):
                if self.last_resize == widget.get_size():
                        return
                self.last_resize = widget.get_size()

                if self.w_main_view_notebook.get_current_page() == NOTEBOOK_START_PAGE:
                        if self.link_load_page == "":
                                self.__load_startpage()
                        else:
                                self.__link_load_page(self.link_load_page)
                
        def __on_mainwindow_check_resize(self, widget):
                if not widget or not self.gdk_window:
                        return
                if self.resize_id != 0:
                        gobject.source_remove(self.resize_id)
                        self.resize_id = 0

                self.resize_id = \
                            gobject.timeout_add(RESIZE_DELAY,
                                self.__handle_resize, widget)
                                
                status_height = self.w_statusbar_hbox.get_allocation().height
                self.gdk_window.move_resize(0, 0, widget.get_size()[0],
                    widget.get_size()[1]-status_height)

        def __on_api_search_error_delete_event(self, widget, event):
                self.__on_api_search_button_clicked(None)

        def __on_preferencesdialog_delete_event(self, widget, event):
                self.__on_preferencesclose_clicked(None)
                return True

        def __on_api_search_button_clicked(self, widget):
                self.api_search_error_dialog.hide()

        def __on_file_quit_activate(self, widget):
                ''' handler for quit menu event '''
                self.__on_mainwindow_delete_event(None, None)

        def __on_file_manage_publishers(self, widget):
                ''' handler for manage publishers menu event '''
                repository.Repository(self, self.image_directory,
                    action=enumerations.MANAGE_PUBLISHERS,
                    main_window = self.w_main_window)

        def __on_file_add_publisher(self, widget):
                ''' handler for add publisher menu event '''
                repository.Repository(self, self.image_directory,
                    action=enumerations.ADD_PUBLISHER,
                    main_window = self.w_main_window)

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
                        self.__update_statusbar_message(_("Search all publishers"))
                else:
                        self.__update_statusbar_message(_("Search current publisher"))

        def __remove_statusbar_message(self):
                if self.statusbar_message_id > 0:
                        try:
                                self.w_main_statusbar.remove_message(0,
                                    self.statusbar_message_id)
                        except AttributeError:
                                self.w_main_statusbar.remove(0,
                                    self.statusbar_message_id)
                        self.statusbar_message_id = 0
        
        def __update_statusbar_message(self, message):
                if self.exiting:
                        return
                self.__remove_statusbar_message()
                self.statusbar_message_id = self.w_main_statusbar.push(0, message)
                if self.w_main_statusbar_label:
                        self.w_main_statusbar_label.set_markup(message)

        def __setup_before_all_publishers_mode(self):
                self.is_all_publishers_installed = False
                self.is_all_publishers = True
                self.w_infosearch_frame.hide()
                if not self.w_searchentry.is_focus():
                        self.__set_searchentry_to_prompt()
                
                self.__save_setup_before_search()
                first_run = self.first_run
                self.first_run = False
                self.__clear_before_search(False)
                # Show the Search all page if not showing the Start Page on startup
                show_search_all_page = not first_run or (first_run 
                    and not self.show_startpage)
                if show_search_all_page:
                        gobject.idle_add(self.__setup_search_all_page)
                elif self.show_startpage:
                        gobject.idle_add(self.w_main_view_notebook.set_current_page,
                            NOTEBOOK_START_PAGE)
                self.__update_statusbar_for_search()
                
        def __set_searchentry_to_prompt(self):
                if not self.first_run and self.search_text_style != \
                        enumerations.SEARCH_STYLE_PROMPT:
                        self.__set_search_text_mode(enumerations.SEARCH_STYLE_PROMPT)
  
        def __setup_search_all_page(self):
                header = INFORMATION_PAGE_HEADER
                header += _("alt='[Information]' title='Information' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Search All Publishers</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD> Use the Search field to search for packages "
                    "within the following Publishers:</TD></TR>"
                    )
                body = "<TR><TD></TD><TD>"
                pub_browse_list = ""
                model = self.w_repository_combobox.get_model()
                for pub in model:
                        prefix = pub[enumerations.REPOSITORY_PREFIX]
                        if (prefix and prefix not in self.publisher_options.values()):
                                pub_alias = pub[enumerations.REPOSITORY_ALIAS]
                                if pub_alias != None and len(pub_alias) > 0:
                                        pub_name = "%s (%s)" % (
                                            pub_alias, prefix)
                                else:
                                        pub_name = prefix
                                body += "<li style='padding-left:7px'>%s</li>" \
                                    % pub_name
                                pub_browse_list += "<li style='padding-left:7px'><a href="
                                pub_browse_list += "'pm?pm-action=internal&search=%s" % \
                                        INTERNAL_SEARCH_VIEW_PUB
                                if pub_alias != None and len(pub_alias) > 0:
                                        pub_browse_list += " <b>%s</b>'>%s</a></li>" % \
                                                (prefix, pub_alias)
                                else:
                                        pub_browse_list += " <b>%s</b>'>%s</a></li>" % \
                                                (prefix, pub_name)
                              
                body += "<TD></TD></TR>"
                body += _("<TR><TD></TD><TD></TD></TR>"
                    "<TR><TD></TD><TD>Click on the Publishers below to view their list "
                    "of packages:</TD></TR>"
                    )
                body += "<TR><TD></TD><TD>"
                body += pub_browse_list
                body += "<TD></TD></TR>"
                footer = "</table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)


        def __setup_search_installed_page(self, text):
                header = INFORMATION_PAGE_HEADER
                header += _("alt='[Information]' title='Information' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Search in All Publishers (Installed)</b></h3><TD></TD>"
                    "</TR><TR><TD></TD><TD> Search is <b>not</b> supported in "
                    "All Publishers (Installed).</TD></TR>"
                    )

                body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD></TR>"
                    "<TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )

                body += _("<li style='padding-left:7px'>Return to view packages for "
                    "All Publishers <a href='pm?pm-action=internal&search="
                    "%s'>(Installed)</a></li>")  % INTERNAL_SEARCH_ALL_PUBS_INSTALLED
                body += _("<li style='padding-left:7px'>Search for <b>%(text)s"
                    "</b> using All Publishers <a href='pm?pm-action=internal&search="
                    "%(all_pubs)s'>(Search)</a></li>")  % \
                    {"text": text, "all_pubs": INTERNAL_SEARCH_ALL_PUBS}

                body += _("<li style='padding-left:7px'>"
                    "See <a href='pm?pm-action=internal&search="
                    "%s'>Search Help</a></li></TD></TR>") % INTERNAL_SEARCH_HELP
                footer = "</table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                self.__set_focus_on_searchentry()

        def __setup_recent_search_page(self):
                header = INFORMATION_PAGE_HEADER
                header += _("alt='[Information]' title='Information' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Recent Searches</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD> Access stored results from recent searches "
                    "in this session.</TD></TR>"
                    )
                body = "<TR><TD></TD><TD>"
                search_list = ""
                for search in self.recent_searches_list:
                        search_list += "<li style='padding-left:7px'>%s: <a href=" % \
                                search
                        search_list += "'pm?pm-action=internal&search=%s" % \
                                INTERNAL_SEARCH_VIEW_RESULTS
                        search_list += " <span>%s</span>'>" % search
                        search_list += _("results")
                        search_list += "</a></li>"

                if len(self.recent_searches_list) > 0:
                        body += "<TR><TD></TD><TD></TD></TR><TR><TD></TD><TD>"
                        body += ngettext(
                            "Click on the search results link below to view the stored "
                            "results:", "Click on one of the search results links below "
                            "to view the stored results:",
                            len(self.recent_searches_list)
                            )
                        body += "</TD></TR><TR><TD></TD><TD>"
                        body += search_list
                body += "<TD></TD></TR>"
                footer = "</table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                    
        def __setup_zero_filtered_results_page(self):
                header = INFORMATION_PAGE_HEADER
                active_filter = self.w_filter_combobox.get_active()
                header += _("alt='[Information]' title='Information' ALIGN='bottom'></TD>"
                    "<TD><h3><b>View Packages</b></h3><TD></TD></TR><TR><TD></TD><TD>")
                header += ngettext(
                    "There is one package in this category, "
                    "however it is not visible in the selected View:\n"
                    "<li style='padding-left:7px'><b>%s</b></li>",
                    "There are a number of packages in this category, "
                    "however they are not visible in the selected View:\n"
                    "<li style='padding-left:7px'><b>%s</b></li>",
                    self.length_visible_list) % \
                        self.__get_filter_combobox_description(active_filter)

                body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD></TR>"
                    "<TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )
                body += _("<li style='padding-left:7px'>"
                    "<a href='pm?pm-action=internal&"
                    "search=%s'>Change View to All Packages</a></li>") % \
                    INTERNAL_SEARCH_VIEW_ALL
                footer = "</TD></TR></table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)

        def __setup_search_zero_filtered_results_page(self, text, num):
                header = INFORMATION_PAGE_HEADER
                active_filter = self.w_filter_combobox.get_active()
                header += _("alt='[Information]' title='Information' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Search Results</b></h3><TD></TD></TR><TR><TD></TD><TD>")
                header += ngettext(
                    "Found <b>%(num)s</b> package matching <b>%(text)s</b> "
                    "in All Packages, however it is not listed in the "
                    "<b>%(filter)s</b> View.",
                    "Found <b>%(num)s</b> packages matching <b>%(text)s</b> "
                    "in All Packages, however they are not listed in the "
                    "<b>%(filter)s</b> View.", num) % {"num": num, "text": text,
                    "filter": self.__get_filter_combobox_description(active_filter)}

                body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD></TR>"
                    "<TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )
                body += _("<li style='padding-left:7px'>"
                    "<a href='pm?pm-action=internal&"
                    "search=%s'>Change View to All Packages</a></li>") % \
                    INTERNAL_SEARCH_VIEW_ALL
                footer = "</TD></TR></table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                self.__set_focus_on_searchentry()

        def __get_filter_combobox_description(self, index):
                description = None
                model = self.w_filter_combobox.get_model()
                for entry in model:
                        if entry[enumerations.FILTER_ID] == index:
                                description = entry[enumerations.FILTER_NAME]
                                break
                return description
                
        def __setup_search_zero_results_page(self, pub, text):
                name =  self.__get_publisher_name_from_prefix(pub)
                header = INFORMATION_PAGE_HEADER
                header += _("alt='[Information]' title='Information' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Search Results</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD>No packages found in <b>%(pub)s</b> "
                    "matching <b>%(text)s</b></TD></TR>") % {"pub": name, "text": text}

                body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD></TR>"
                    "<TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    "<li style='padding-left:7px'>Check your spelling</li>"
                    "<li style='padding-left:7px'>Try new search terms</li>"
                    )
                if not self.is_all_publishers:
                        body += _("<li style='padding-left:7px'>Search for <b>%(text)s"
                            "</b> within <a href='pm?pm-action=internal&search="
                            "%(all_pubs)s'>All Publishers</a></li>")  % \
                            {"text": text, "all_pubs": INTERNAL_SEARCH_ALL_PUBS}

                body += _("<li style='padding-left:7px'>"
                    "See <a href='pm?pm-action=internal&search="
                    "%s'>Search Help</a></li></TD></TR>") % INTERNAL_SEARCH_HELP
                footer = "</table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                self.__set_focus_on_searchentry()

        def __set_focus_on_searchentry(self):
                self.w_searchentry.grab_focus()
                if self.w_searchentry.get_text() > 0:
                        start, end = self.w_searchentry.get_selection_bounds()
                        self.w_searchentry.select_region(end, end)
                        self.pylintstub = start
                
        def __setup_search_wildcard_page(self):
                header = _(
                    "<table border='0' cellpadding='3' style='table-layout:fixed' >"
                    "<TR><TD><IMG SRC = '%s/dialog-warning.png' style='border-style: "
                    "none' alt='[Warning]' title='Warning' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Search Warning</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD>Search using only the wildcard character, "
                    "<b>*</b>, is not supported in All Publishers</TD></TR>"
                    ) % START_PAGE_IMAGES_BASE
                body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD></TR>"
                    "<TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    "<li style='padding-left:7px'>Try new search terms</li>"
                    )
                body += _("<li style='padding-left:7px'>"
                    "See <a href='pm?pm-action=internal&search="
                    "%s'>Search Help</a></li></TD></TR>") % INTERNAL_SEARCH_HELP
                footer = "</table>"
                self.__link_load_page(header + body + footer)
                self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                self.__set_focus_on_searchentry()

        def __clear_before_search(self, show_list=True, in_setup=True, unselect_cat=True):
                self.in_setup = in_setup
                application_list = self.__get_new_application_liststore()
                self.__set_empty_details_panel()
                self.__set_main_view_package_list(show_list)
                self.__init_tree_views(application_list, None, None)
                if unselect_cat:
                        self.__unselect_category()

        def __restore_setup_for_browse(self):
                self.in_search_mode = False
                self.in_recent_search = False
                self.is_all_publishers = False
                self.w_infosearch_frame.hide()
                if self.last_visible_publisher == \
                        self.publisher_options[PUBLISHER_INSTALLED]:
                        self.is_all_publishers_installed = True
                else:
                        self.is_all_publishers_installed = False 
                self.set_busy_cursor()
                if (self.w_repository_combobox.get_active() != 
                    self.saved_repository_combobox_active):
                        self.w_repository_combobox.set_active(
                            self.saved_repository_combobox_active)
                self.set_section = self.saved_section_active
                # Reset MARK_COLUMN        
                for pkg in self.saved_application_list:
                        pub = pkg[enumerations.PUBLISHER_PREFIX_COLUMN]
                        stem = pkg[enumerations.STEM_COLUMN]
                        marked = False
                        pkgs = None
                        if self.selected_pkgs != None:
                                pkgs = self.selected_pkgs.get(pub)
                        if pkgs != None:
                                if stem in pkgs:
                                        marked = True
                        # When switching after Manage Publisher dialog
                        # this assignment can cause bogus refilter
                        if pkg[enumerations.MARK_COLUMN] != marked:
                                pkg[enumerations.MARK_COLUMN] = marked
                if self.saved_category_list == self.category_list:
                        self.__restore_category_state()
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

        def __save_application_list(self, app_list):
                self.saved_application_list = app_list
                                
        def __save_setup_before_search(self, single_search=False):
                #Do not save search data models
                if self.in_search_mode:
                        return
                self.__save_application_list(self.application_list)
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
                self.in_recent_search = False
                self.__reset_search_start()
                if self.search_text_style == enumerations.SEARCH_STYLE_PROMPT or \
                        self.w_searchentry.get_text_length() == 0:
                        return

                txt = self.w_searchentry.get_text()
                if len(txt.strip()) == 0:
                        self.w_searchentry.set_text("")
                        return
                self.previous_search_text = txt
                if self.is_all_publishers_installed:
                        gobject.idle_add(self.__setup_search_installed_page, txt)
                        return                
                contains_asterix = txt.count("*") > 0
                contains_asterix_only = False
                if contains_asterix:
                        contains_asterix_only = len(txt.replace("*", " ").strip()) == 0
                if contains_asterix_only:
                        self.w_searchentry.set_text("*")
                        self.__set_focus_on_searchentry()
                        if self.is_all_publishers:
                                gobject.idle_add(self.__setup_search_wildcard_page)
                        else:
                                if self.in_search_mode:
                                        self.__unset_search(True)
                                if self.w_categories_treeview.get_model() != None:
                                        self.w_categories_treeview.set_cursor(0)
                        return
                if not self.is_all_publishers:
                        self.__save_setup_before_search(single_search=True)
                self.__clear_before_search()
                self.__set_focus_on_searchentry()
                self.set_busy_cursor()
                self.in_search_mode = True
                        
                self.w_infosearch_frame.hide()
                gobject.idle_add(self.__set_main_view_package_list)
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
                        self.__save_active_category(path)
                        selection.unselect_all()

        def __process_after_cancel(self):
                if self.is_all_publishers:
                        self.__setup_before_all_publishers_mode()
                else:
                        self.__unset_search(True)

        def __process_after_search_failure(self):
                self.__reset_search_start()
                self.search_time_sec = 0
                self.application_list = []
                gobject.idle_add(self.update_statusbar)
                gobject.idle_add(self.unset_busy_cursor)
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
                self.__set_search_start()
                gobject.idle_add(self.update_statusbar)
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
                        self.search_all_pub_being_searched = _("All Publishers")
                        servers = None
                        try:
                                pref_pub = self.api_o.get_preferred_publisher()
                                pub_prefix = pref_pub.prefix
                        except api_errors.ApiException, ex:
                                err = str(ex)
                                gobject.idle_add(self.error_occurred, err,
                                    None, gtk.MESSAGE_INFO)
                                gobject.idle_add(self.unset_busy_cursor)
                                return
                else:
                        pub_prefix = self.__get_selected_publisher()
                        try:
                                if pub_prefix != None:
                                        pub = self.api_o.get_publisher(prefix=pub_prefix)
                                else:
                                        pub = self.api_o.get_preferred_publisher()
                        except api_errors.ApiException, ex:
                                err = str(ex)
                                gobject.idle_add(self.error_occurred, err,
                                    None, gtk.MESSAGE_INFO)
                                gobject.idle_add(self.unset_busy_cursor)
                                return
                        origin_uri = self.__get_origin_uri(pub.selected_repository)
                        servers.append({"origin": origin_uri})
                        self.search_all_pub_being_searched = \
                                self.__get_publisher_display_name_from_prefix(pub.prefix)
                if debug:
                        print "Search: pargs %s servers: %s" % (pargs, servers)

                #TBD If we ever search just Installed pkgs should allow for a local search
                case_sensitive = False
                return_actions = True

                last_name = ""
                # Sorting results by Name gives best overall appearance and flow
                sort_col = enumerations.NAME_COLUMN
                try:
                        searches.append(self.api_o.remote_search(
                            [api.Query(" ".join(pargs), case_sensitive, return_actions)],
                            servers=servers))
                        if debug:
                                print "Search Args: %s : cs: %s : retact: %s" % \
                                        ("".join(pargs), case_sensitive, return_actions)
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
                                if search_all:
                                        self.__process_after_search_with_zero_results(
                                                _("All Publishers"), text)
                                else:
                                        self.__process_after_search_with_zero_results(
                                                pub_prefix, text)
                                return
                except api_errors.CanceledException:
                        self.__reset_search_start()
                        gobject.idle_add(self.unset_busy_cursor)
                        gobject.idle_add(self.__process_after_cancel)
                        return
                except api_errors.ImageLockedError, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err,
                                None, gtk.MESSAGE_INFO)
                        self.__process_after_search_failure()
                        return
                except Exception, aex:
                        err = str(aex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                        self.__process_after_search_failure()
                        return
                if debug:
                        print "Number of search results:", len(result)
                if len(result) == 0:
                        if debug:
                                print "No search results"
                        if search_all:
                                self.__process_after_search_with_zero_results(
                                        _("All Publishers"), text)
                        else:
                                self.__process_after_search_with_zero_results(
                                        pub_prefix, text)
                        return
                #Now fetch full result set with Status
                if self.exiting:
                        return
                self.in_setup = True
                if debug_perf:
                        print "Time for search:", time.time() - self.search_start
                application_list = self.__get_full_list_from_search(result)
                gobject.idle_add(self.__add_recent_search, text, pub_prefix,
                    application_list)
                if self.search_start > 0:
                        self.search_time_sec = int(time.time() - self.search_start)
                        if debug:
                                print "Search time: %d (sec)" % self.search_time_sec
                self.__reset_search_start()
                gobject.idle_add(self.__init_tree_views, application_list, None, None, \
                    None, None, sort_col)
                if self.w_filter_combobox.get_active() == enumerations.FILTER_ALL:
                        return

                gobject.idle_add(self.__check_zero_results_afterfilter, text,
                    len(application_list))

        def __check_zero_results_afterfilter(self, text, num):
                if self.length_visible_list != 0:
                        return
                self.__setup_search_zero_filtered_results_page(text, num)
                self.update_statusbar()

        def __set_search_start(self):
                self.search_start = time.time()
                
        def __reset_search_start(self):
                self.search_start = 0
                
        def __process_after_search_with_zero_results(self, pub, text):
                if self.search_start > 0:
                        self.search_time_sec = int(time.time() - self.search_start)
                self.__reset_search_start()
                gobject.idle_add(self.__setup_search_zero_results_page, pub, text)
                self.in_setup = True
                application_list = self.__get_new_application_liststore()
                gobject.idle_add(self.__set_empty_details_panel)
                gobject.idle_add(self.__init_tree_views, application_list, None, None)

        def __get_publisher_display_name_from_prefix(self, prefix):
                if self.pubs_display_name.has_key(prefix):
                        return self.pubs_display_name[prefix]
                else:
                        return prefix

        def __get_publisher_name_from_prefix(self, prefix):
                if self.pubs_info.has_key(prefix):
                        item  = self.pubs_info[prefix]
                else:
                        return prefix
                alias = item[1]
                if alias != None and len(alias) > 0:
                        return alias
                else:
                        return prefix 

        def __get_min_list_from_search(self, search_result):
                application_list = self.__get_new_application_liststore()
                for name, pub in search_result:
                        pub_name = self.__get_publisher_name_from_prefix(pub)
                        application_list.append(
                            [False, None, name, '...', api.PackageInfo.KNOWN, None, 
                            self.__get_pkg_stem(name, pub), None, True, None, 
                            pub_name, pub])
                return application_list

        def __get_full_list_from_search(self, search_result):
                application_list = self.__get_new_application_liststore()
                self.__add_pkgs_to_list_from_search(search_result,
                    application_list)
                return application_list

        def __add_pkgs_to_list_from_search(self, search_result,
            application_list):
                local_results = self.__get_info_for_search_results(search_result)
                remote_results = self.__get_info_for_search_results(search_result,
                    local_results)
                self.__add_pkgs_to_lists_from_info(local_results, 
                    remote_results, application_list)

        def __get_info_for_search_results(self, search_result, local_results = None):
                pargs = []
                results = []
                local_info = local_results == None
                for name, pub in search_result:
                        found = False
                        if local_results:
                                for result in local_results:
                                        if (name == result.pkg_stem and
                                            pub == result.publisher):
                                                found = True
                                                break
                                if not found: 
                                        pargs.append(self.__get_pkg_stem(name, pub))
                        else:
                                pargs.append(self.__get_pkg_stem(name, pub))

                try:
                        try:
                                res = self.api_o.info(pargs, 
                                          local_info, frozenset(
                                          [api.PackageInfo.IDENTITY, 
                                          api.PackageInfo.STATE, 
                                          api.PackageInfo.SUMMARY]))
                                results = res.get(0)
                        except api_errors.TransportError, tpex:
                                err = str(tpex)
                                logger.error(err)
                                gui_misc.notify_log_error(self)
                        except api_errors.InvalidDepotResponseException, idex:
                                err = str(idex)
                                logger.error(err)
                                gui_misc.notify_log_error(self)
                        except api_errors.ImageLockedError, ex:
                                err = str(ex)
                                logger.error(err)
                                gui_misc.notify_log_error(self)
                        except Exception, ex:
                                err = str(ex)
                                gobject.idle_add(self.error_occurred, err)
                finally:
                        return results

        def __application_refilter(self):
                ''' Disconnecting the model from the treeview improves
                performance when assistive technologies are enabled'''
                if self.in_setup:
                        return
                self.application_refilter_id = 0
                self.application_refilter_idle_id = 0
                model = self.w_application_treeview.get_model()
                self.w_application_treeview.set_model(None)
                app_id, order = self.application_list_sort.get_sort_column_id()
                self.application_list_sort.reset_default_sort_func()
                self.application_list_filter.refilter()
                if app_id != None:
                        self.application_list_sort.set_sort_column_id(app_id, order)
                if model != None:
                        self.w_application_treeview.set_model(model)
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
                self.__set_empty_details_panel()
                self.__enable_disable_selection_menus()
                self.__enable_disable_install_remove()
                if not self.in_search_mode and self.length_visible_list > 0 and \
                        len_filtered_list == 0 and \
                        self.w_filter_combobox.get_active() != \
                        (enumerations.FILTER_SELECTED):
                        self.__setup_zero_filtered_results_page()
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
                if self.w_main_view_notebook.get_current_page() == NOTEBOOK_START_PAGE:
                        if self.view:
                                self.view.grab_focus()
                else:
                        self.__set_main_view_package_list()
                        self.w_application_treeview.grab_focus()

        def __on_edit_search_clicked(self, widget):
                self.w_searchentry.grab_focus()

        def __on_clear_search(self, widget, icon_pos=0, event=None):
                self.w_searchentry.set_text("")
                self.__clear_search_results()

        def __clear_search_results(self):
                # Only clear out search results
                if self.in_search_mode or self.is_all_publishers:
                        self.__clear_before_search()
                        self.__update_statusbar_message(_("Search cleared"))
                if self.is_all_publishers:
                        if self.w_main_view_notebook.get_current_page() \
                                != NOTEBOOK_START_PAGE:
                                gobject.idle_add(self.__setup_search_all_page)
                else:
                        self.__unset_search(self.in_search_mode)
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
                                pkg_publisher = model.get_value(itr,
                                    enumerations.PUBLISHER_PREFIX_COLUMN)
                                pkg_description = model.get_value(itr,
                                    enumerations.DESCRIPTION_COLUMN)
                                pkg_name = model.get_value(itr,
                                    enumerations.NAME_COLUMN)
                                self.__add_pkg_stem_to_list(pkg_stem, pkg_name, 
                                    pkg_status, pkg_publisher, pkg_description)
                        elif not select_all and mark_value:
                                model.set_value(itr, enumerations.MARK_COLUMN, False)
                                pkg_stem = model.get_value(itr,
                                    enumerations.STEM_COLUMN)
                                self.__remove_pkg_stem_from_list(pkg_stem)
                
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
                            enumerations.STATUS_COLUMN) == api.PackageInfo.UPGRADABLE:
                                list_of_paths.append(path)
                        iter_next = sort_filt_model.iter_next(iter_next)
                for path in list_of_paths:
                        itr = model.get_iter(path)
                        model.set_value(itr, enumerations.MARK_COLUMN, True)
                        pkg_stem = model.get_value(itr, enumerations.STEM_COLUMN)
                        pkg_status = model.get_value(itr, enumerations.STATUS_COLUMN)
                        pkg_publisher = model.get_value(itr,
                            enumerations.PUBLISHER_PREFIX_COLUMN)
                        pkg_description = model.get_value(itr,
                            enumerations.DESCRIPTION_COLUMN)
                        pkg_name = model.get_value(itr,
                            enumerations.NAME_COLUMN)
                        self.__add_pkg_stem_to_list(pkg_stem, pkg_name, pkg_status,
                            pkg_publisher, pkg_description)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_remove()

        def __on_deselect(self, widget):
                self.set_busy_cursor()
                gobject.idle_add(self.__toggle_select_all, False)
                return

        def __save_state_changed(self, client, connection_id, entry, arguments):
                self.save_state = entry.get_value().get_bool()

        def __show_image_update_changed(self, client, connection_id, entry, arguments):
                self.show_image_update = entry.get_value().get_bool()

        def __show_install_changed(self, client, connection_id, entry, arguments):
                self.show_install = entry.get_value().get_bool()

        def __show_remove_changed(self, client, connection_id, entry, arguments):
                self.show_remove = entry.get_value().get_bool()

        def __on_preferences(self, widget):
                self.w_startpage_checkbutton.set_active(self.show_startpage)
                self.w_exit_checkbutton.set_active(self.save_state)
                self.w_confirm_updateall_checkbutton.set_active(self.show_image_update)
                self.w_confirm_install_checkbutton.set_active(self.show_install)
                self.w_confirm_remove_checkbutton.set_active(self.show_remove)
                self.w_preferencesdialog.show()

        def __on_preferencesclose_clicked(self, widget):
                self.w_preferencesdialog.hide()

        @staticmethod
        def __on_preferenceshelp_clicked(widget):
                gui_misc.display_help("pkg-mgr-prefs")

        def __on_startpage_checkbutton_toggled(self, widget):
                self.show_startpage = self.w_startpage_checkbutton.get_active()
                try:
                        self.client.set_bool(SHOW_STARTPAGE_PREFERENCES,
                            self.show_startpage)
                except GError:
                        pass

        def __on_exit_checkbutton_toggled(self, widget):
                self.save_state = self.w_exit_checkbutton.get_active()
                try:
                        self.client.set_bool(SAVE_STATE_PREFERENCES,
                            self.save_state)
                except GError:
                        pass

        def on_confirm_updateall_checkbutton_toggled(self, widget, reverse = False):
                active = widget.get_active()
                if reverse:
                        active = not active
                self.show_image_update = active
                try:
                        self.client.set_bool(SHOW_IMAGE_UPDATE_CONFIRMATION,
                            self.show_image_update)
                except GError:
                        pass

        def on_confirm_install_checkbutton_toggled(self, widget, reverse = False):
                active = widget.get_active()
                if reverse:
                        active = not active
                self.show_install = active
                try:
                        self.client.set_bool(SHOW_INSTALL_CONFIRMATION,
                            self.show_install)
                except GError:
                        pass

        def on_confirm_remove_checkbutton_toggled(self, widget, reverse = False):
                active = widget.get_active()
                if reverse:
                        active = not active
                self.show_remove = active
                try:
                        self.client.set_bool(SHOW_REMOVE_CONFIRMATION,
                            self.show_remove)
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
                # Activated sub node in Recent Searches category
                if self.in_recent_search:
                        return
                # User activated Recent Searches Top Level category
                model = self.w_categories_treeview.get_model()
                if model != None and self.recent_searches_cat_iter:
                        rs_path = model.get_path(self.recent_searches_cat_iter)
                        selection, curr_path = self.__get_selection_and_category_path()
                        self.pylintstub = selection
                        if curr_path == rs_path:
                                self.__setup_recent_search_page()
                                return
                if self.category_list == None:
                        self.__set_main_view_package_list()
                        return
                if self.w_filter_combobox.get_model():
                        self.w_filter_combobox.set_active(
                            self.saved_filter_combobox_active)
                if self.in_search_mode or self.is_all_publishers:
                        self.__unset_search(True)
                        return
                self.__set_main_view_package_list()
                self.set_busy_cursor()
                self.__refilter_on_idle()

        def __set_main_view_package_list(self, show_list=True):
                # Only switch from Start Page View to List view if we are not in startup
                if self.in_startpage_startup:
                        return
                if show_list:
                        self.w_main_view_notebook.set_current_page(
                                NOTEBOOK_PACKAGE_LIST_PAGE)
                else:
                        self.w_main_view_notebook.set_current_page(
                                NOTEBOOK_START_PAGE)

        def __on_categoriestreeview_row_collapsed(self, treeview, itr, path, data):
                self.w_categories_treeview.set_cursor(path)
                self.__save_expanded_path(path, False)
                self.__save_active_category(path)
                
        def __on_categoriestreeview_row_expanded(self, treeview, itr, path, data):
                if self.in_setup and not self.first_run:
                        return
                self.w_categories_treeview.set_cursor(path)
                self.__save_expanded_path(path, True)
                self.__save_active_category(path)

        def __on_categoriestreeview_button_press_event(self, treeview, event, data):
                if event.type != gtk.gdk.BUTTON_PRESS:
                        return 1
                x = int(event.x)
                y = int(event.y)
                pthinfo = treeview.get_path_at_pos(x, y)
                if pthinfo is not None:
                        path = pthinfo[0]
                        cellx = pthinfo[2]
                        #Clicking on row toggle icon just select the path
                        if cellx <= CATEGORY_TOGGLE_ICON_WIDTH:
                                self.w_categories_treeview.set_cursor(path)
                                self.w_categories_treeview.scroll_to_cell(path)
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
                                self.__save_active_category(path)

        @staticmethod
        def __categoriestreeview_compare_func(model, column, key, itr):
                value = model.get_value(itr, column)
                if not value:
                        return True

                try:
                        value = re.sub(REGEX_STRIP_MARKUP, "", value)
                        value = re.sub(REGEX_STRIP_RESULT, "", value)
                        match = re.match(re.escape(key), re.escape(value), re.IGNORECASE)
                except (TypeError, re.error):
                        return True

                return match is None

        def __in_recent_searches(self, path):
                if not path or len(path) == 0:
                        return False
                model = self.w_categories_treeview.get_model()
                if model == None:
                        return False
                rs_path = model.get_path(self.recent_searches_cat_iter)
                if rs_path and len(rs_path) > 0 and path[0] == rs_path[0]:
                        return True
                return False
                
        def __save_expanded_path(self, path, expanded):
                if not path or len(path) == 0:
                        return                
                self.category_expanded_paths[(self.last_visible_publisher, path)] = \
                        expanded

        def __save_active_category(self, path):
                if self.first_run or not path or len(path) == 0 or \
                        self.__in_recent_searches(path):
                        return                
                self.category_active_paths[self.last_visible_publisher] = path
                self.saved_section_active = path[0]

        def __on_category_selection_changed(self, selection, widget):
                '''This function is for handling category selection changes'''
                if self.in_setup:
                        return
                model, itr = selection.get_selected()
                if not itr:
                        return

                path = model.get_path(itr)
                sel_category = model[path]
                if sel_category[enumerations.CATEGORY_ID] == RECENT_SEARCH_ID:
                        if not self.adding_recent_search:
                                self.__setup_recent_search_page()
                                if not self.is_all_publishers:
                                        self.__save_setup_before_search(
                                            single_search=True)
                                self.in_search_mode = True
                                self.in_recent_search = True
                        else:
                                self.__set_main_view_package_list()
                        return
                elif sel_category[enumerations.CATEGORY_ID] > RECENT_SEARCH_ID:
                        self.__restore_recent_search(sel_category)
                        return
                self.__save_active_category(path)
                if self.in_search_mode or self.is_all_publishers:
                        #Required for A11Y support because focus event not triggered
                        #when A11Y enabled and user clicks on Category after Search
                        self.__unset_search(True)
                        self.__set_main_view_package_list()
                        return
                if self.saved_filter_combobox_active != None:
                        self.w_filter_combobox.set_active(
                            self.saved_filter_combobox_active)
                self.__set_main_view_package_list()

                self.set_busy_cursor()
                self.__refilter_on_idle()

        def __on_applicationtreeview_query_tooltip(self, treeview, x, y, 
            keyboard_mode, tooltip):
                treex, treey = treeview.convert_widget_to_bin_window_coords(x, y)
                info = treeview.get_path_at_pos(treex, treey)
                if not info:
                        return False
                return self.__show_app_column_tooltip(treeview, _("Status"), 
                    info[0], info[1], tooltip)

        @staticmethod
        def __show_app_column_tooltip(treeview, col_title, path, col, tooltip):
                tip = ""
                if path and col:
                        title = col.get_title() 
                        if title != col_title:
                                return False
                        row = list(treeview.get_model()[path])
                        if row:
                                status = row[enumerations.STATUS_COLUMN]
                                if status == api.PackageInfo.INSTALLED:
                                        tip = _("Installed")
                                elif status == api.PackageInfo.KNOWN:
                                        tip = _("Not installed")
                                elif status == api.PackageInfo.UPGRADABLE:
                                        tip = _("Updates Available")

                if tip != "":
                        treeview.set_tooltip_cell(tooltip, path, col, None)
                        tooltip.set_text(tip)
                        return True
                else:
                        return False

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
                        return True

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
        def __applicationtreeview_compare_func(model, column, key, itr):
                value = model.get_value(itr, enumerations.NAME_COLUMN)
                if not value:
                        return True

                value = value.lower()
                return not value.startswith(key.lower())

        @staticmethod
        def __position_package_popup(menu, position):
                #Positions popup relative to the top left corner of the currently
                #selected row's Name cell
                x, y = position

                #Offset x by 10 and y by 15 so underlying name is visible
                return (x+10, y+15, True)

        def __process_package_selection(self):
                model, itr = self.package_selection.get_selected()
                if self.show_info_id != 0:
                        gobject.source_remove(self.show_info_id)
                        self.show_info_id = 0
                if itr:
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
                        self.w_version_info_menuitem.set_sensitive(True)
                else:
                        self.selected_model = None
                        self.selected_path = None
                        self.selected_pkgstem = None
                        self.w_version_info_menuitem.set_sensitive(False)

        def __on_package_selection_changed(self, selection, widget):
                '''This function is for handling package selection changes'''
                if self.in_setup:
                        return
                self.__process_package_selection()

        def __on_filtercombobox_changed(self, widget):
                '''On filter combobox changed'''
                if self.first_run or self.in_setup:
                        return
                active = self.w_filter_combobox.get_active()
                if active != enumerations.FILTER_SELECTED:
                        self.saved_filter_combobox_active = active
                self.__set_main_view_package_list()
                self.set_busy_cursor()
                self.__refilter_on_idle()

        def __unset_search(self, same_repo):
                self.w_infosearch_frame.hide()
                self.__update_tooltips()
                self.in_search_mode = False
                self.in_recent_search = False
                self.is_all_publishers = False
                if same_repo:
                        self.__restore_setup_for_browse()

        def __on_repositorycombobox_changed(self, widget):
                '''On repository combobox changed'''
                if debug_perf:
                        print "Start change publisher", time.time()
                if self.same_publisher_on_setup:
                        if self.is_all_publishers:
                                self.__clear_search_results()
                        self.same_publisher_on_setup = False
                        self.unset_busy_cursor()
                        if self.in_setup:
                                self.in_setup = False
                        return
                selected_publisher = self.__get_selected_publisher()
                index =  self.w_repository_combobox.get_active()
                if self.is_all_publishers:
                        if index == self.repo_combobox_all_pubs_index:
                                return
                        if index == self.repo_combobox_add_index:
                                self.w_repository_combobox.set_active(
                                    self.repo_combobox_all_pubs_index)
                                self.__on_file_add_publisher(None)
                                return
                        same_repo = self.saved_repository_combobox_active == index
                        self.__unset_search(same_repo)
                        if same_repo:
                                self.__set_searchentry_to_prompt()
                                return
                        self.w_repository_combobox.set_active(index)
                        selected_publisher = self.__get_selected_publisher()
                if selected_publisher == self.last_visible_publisher:
                        return
                if index == self.repo_combobox_all_pubs_index:
                        self.__set_all_publishers_mode()
                        return
                        
                if index == self.repo_combobox_add_index:
                        index = self.__get_publisher_combobox_index(
                            self.last_visible_publisher)
                        self.w_repository_combobox.set_active(index)
                        self.__on_file_add_publisher(None)
                        return
                if index == self.repo_combobox_all_pubs_installed_index:
                        self.w_filter_combobox.set_active(enumerations.FILTER_ALL)
                        self.is_all_publishers_installed = True
                else:
                        self.is_all_publishers_installed = False

                self.__do_set_publisher()

        def __do_set_publisher(self):
                self.cancelled = True
                self.in_setup = True
                self.set_busy_cursor()
                self.__set_empty_details_panel()
                if self.in_search_mode:
                        self.__unset_search(False)

                pub = [self.__get_selected_publisher(), ]
                self.set_section = self.initial_section
                self.__set_searchentry_to_prompt()
                self.__disconnect_models()
                Thread(target = self.__setup_publisher, args = [pub]).start()
                self.__set_main_view_package_list()

        def __get_selected_publisher(self):
                pub_iter = self.w_repository_combobox.get_active_iter()
                if pub_iter == None:
                        return None
                return self.repositories_list.get_value(pub_iter, \
                            enumerations.REPOSITORY_PREFIX)

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
                self.__save_application_list(None)
                self.saved_application_list_filter = None
                self.saved_application_list_sort = None
                self.saved_category_list = None
                self.saved_section_list = None

        def __refresh_for_publisher(self, pub):
                status_str = _("Refreshing package catalog information")
                gobject.idle_add(self.__update_statusbar_message,
                    status_str)
                if self.is_all_publishers_installed: 
                        self.__do_refresh()
                else:
                        self.__do_refresh(pubs=[pub])

        def __do_refresh(self, pubs=None, immediate=False):
                success = False
                try:
                        self.api_o.reset()
                        self.api_o.refresh(pubs=pubs, immediate=immediate)
                        success = True
                except api_errors.CatalogRefreshException, cre:
                        crerr = gui_misc.get_catalogrefresh_exception_msg(cre)
                        logger.error(crerr)
                        gui_misc.notify_log_error(self)
                except api_errors.TransportError, tpex:
                        err = str(tpex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.InvalidDepotResponseException, idex:
                        err = str(idex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.ApiException, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                except Exception, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                return success

        def __get_application_categories_lists(self, publishers):
                application_list = self.__get_new_application_liststore()
                category_list = self.__get_new_category_liststore()
                section_list = self.__get_new_section_liststore()
                for pub in publishers:
                        if debug_perf:
                                a = time.time()
                        self.__refresh_for_publisher(pub)
                        if debug_perf:
                                print "Time to refresh", time.time() - a
                                a = time.time()
                        self.__add_pkgs_to_lists_from_api(pub,
                            application_list, category_list, section_list)
                        if debug_perf:
                                b = time.time()
                                print "Time to add", b - a, b
                        category_list.prepend(None, [0, _('All'), _('All'), None,
                            None, True])

                return application_list, category_list, section_list

        def __add_install_update_pkgs_for_publishers(self, install_update,
            confirmation_list):
                for pub_name in self.selected_pkgs:
                        pub_display_name = self.__get_publisher_display_name_from_prefix(
                            pub_name)
                        pkgs = self.selected_pkgs.get(pub_name)
                        if not pkgs:
                                break
                        for pkg_stem in pkgs:
                                status = pkgs.get(pkg_stem)[0]
                                if status == api.PackageInfo.KNOWN or \
                                    status == api.PackageInfo.UPGRADABLE:
                                        install_update.append(pkg_stem)
                                        if self.show_install:
                                                desc = pkgs.get(pkg_stem)[1]
                                                pkg_name = pkgs.get(pkg_stem)[2]
                                                confirmation_list.append(
                                                    [pkg_name, pub_display_name,
                                                    desc, status])
                                                    
        def __on_log_dialog_delete_event(self, widget, event):
                self.__on_log_close_button_clicked(None)
                return True
                
        def __on_log_close_button_clicked(self, widget):
                self.w_view_log_dialog.hide()
                
        def __on_log_activate(self, widget):                                
                if self.error_logged:
                        self.error_logged = False
                        self.w_infosearch_frame.hide()
                textbuffer = self.w_log_errors_textview.get_buffer()
                textbuffer.set_text(_("Loading ..."))
                textbuffer = self.w_log_info_textview.get_buffer()
                textbuffer.set_text(_("Loading ..."))
                self.w_log_close_button.grab_focus()
                self.w_view_log_dialog.show()
                gobject.idle_add(self.__load_err_view_log)
                gobject.idle_add(self.__load_info_view_log)
                
        def __load_err_view_log(self):
                textbuffer = self.w_log_errors_textview.get_buffer()
                textbuffer.set_text("")
                textiter = textbuffer.get_end_iter()
                log_dir = gui_misc.get_log_dir()
                log_err_ext = gui_misc.get_log_error_ext()
                pm_err_log = os.path.join(log_dir, gui_misc.get_pm_name() + log_err_ext)
                wi_err_log = os.path.join(log_dir, gui_misc.get_wi_name() + log_err_ext)
                um_err_log = os.path.join(log_dir, gui_misc.get_um_name() + log_err_ext)

                self.__write_to_view_log(um_err_log, 
                    textbuffer, textiter, _("None: ") + gui_misc.get_um_name() + "\n")
                self.__write_to_view_log(wi_err_log, 
                    textbuffer, textiter, _("None: ") + gui_misc.get_wi_name() + "\n")
                self.__write_to_view_log(pm_err_log, 
                    textbuffer, textiter, _("None: ") + gui_misc.get_pm_name() + "\n")
                gobject.idle_add(self.w_log_errors_textview.scroll_to_iter, textiter,
                    0.0)
                    
        def __load_info_view_log(self):
                textbuffer = self.w_log_info_textview.get_buffer()
                textbuffer.set_text("")
                textiter = textbuffer.get_end_iter()
                log_dir = gui_misc.get_log_dir()
                log_info_ext = gui_misc.get_log_info_ext()
                pm_info_log = os.path.join(log_dir, gui_misc.get_pm_name() + log_info_ext)
                wi_info_log = os.path.join(log_dir, gui_misc.get_wi_name() + log_info_ext)
                um_info_log = os.path.join(log_dir, gui_misc.get_um_name() + log_info_ext)

                self.__write_to_view_log(um_info_log, 
                    textbuffer, textiter, _("None: ") + gui_misc.get_um_name() + "\n")
                self.__write_to_view_log(wi_info_log, 
                    textbuffer, textiter, _("None: ") + gui_misc.get_wi_name() + "\n")
                self.__write_to_view_log(pm_info_log, 
                    textbuffer, textiter, _("None: ") + gui_misc.get_pm_name() + "\n")
                gobject.idle_add(self.w_log_info_textview.scroll_to_iter, textiter, 0.0)

        @staticmethod
        def __write_to_view_log(path, textbuffer, textiter, nomessages):
                infile = None
                try:
                        infile = open(path, "r")
                except IOError:
                        textbuffer.insert_with_tags_by_name(textiter, nomessages, "bold")
                        return
                if infile == None:
                        textbuffer.insert_with_tags_by_name(textiter, nomessages, "bold")
                        return
                        
                lines = infile.readlines()
                if len(lines) == 0:
                        textbuffer.insert_with_tags_by_name(textiter, nomessages, "bold")
                        return                        
                for line in lines:
                        if re.match(REGEX_BOLD_MARKUP, line):
                                line = re.sub(REGEX_STRIP_MARKUP, "", line)
                                textbuffer.insert_with_tags_by_name(textiter, line,
                                    "bold")
                        else:
                                textbuffer.insert(textiter, line)
                try:
                        infile.close()
                except IOError:
                        pass
        
        def __on_version_info(self, widget):
                model, itr = self.package_selection.get_selected()
                if itr:
                        pkg_stem = model.get_value(itr, enumerations.STEM_COLUMN)
                        name = model.get_value(itr, enumerations.ACTUAL_NAME_COLUMN)
                        self.set_busy_cursor()
                        Thread(target = self.__get_info, args = (pkg_stem, name)).start()

        def __get_info(self, pkg_stem, name):
                if not self.__do_api_reset():
                        return
                local_info = gui_misc.get_pkg_info(self, self.api_o, pkg_stem, True)
                remote_info = gui_misc.get_pkg_info(self, self.api_o, pkg_stem, False)
                if self.exiting:
                        return
                plan_pkg = None

                installed_only = False
                if local_info:
                        if gui_misc.same_pkg_versions(local_info, remote_info):
                                installed_only = True

                if not installed_only:
                        install_update_list = []
                        stuff_to_do = False
                        install_update_list.append(pkg_stem)
                        try:
                                stuff_to_do = self.api_o.plan_install(
                                    install_update_list,
                                    refresh_catalogs = False) 
                        except api_errors.ApiException, ex:
                                err = str(ex)
                                logger.error(err)
                                gobject.idle_add(gui_misc.notify_log_error, self)
                                gobject.idle_add(self.unset_busy_cursor)
                                return
                        if stuff_to_do:
                                plan_desc = self.api_o.describe()
                                if plan_desc == None:
                                        return
                                plan = plan_desc.get_changes()
                                plan_pkg = None
                                for pkg_plan in plan:
                                        if name == pkg_plan[1].pkg_stem:
                                                plan_pkg = pkg_plan[1]
                                                break
                                if plan_pkg == None:
                                        gobject.idle_add(self.unset_busy_cursor)
                                        return
                gobject.idle_add(self.__after_get_info, local_info, remote_info,
                    plan_pkg, name)
                return

        def __hide_pkg_version_details(self):
                self.w_info_expander.hide()
                self.w_version_info_dialog.set_size_request(-1, -1)
                
        def __after_get_info(self, local_info, remote_info, plan_pkg, name):
                if self.exiting:
                        return
                self.w_info_name_label.set_text(name)
                installable_fmt = \
                    _("%(version)s (Build %(build)s-%(branch)s)")
                installed_label = ""
                installable_label = ""
                installable_prefix_label = _("<b>Installable Version:</b>")
                
                if local_info:
                        # Installed
                        installable_prefix_label = _("<b>Upgradeable Version:</b>")
                        yes_text = _("Yes, %(version)s (Build %(build)s-%(branch)s)")
                        installed_label = yes_text % \
                            {"version": local_info.version,
                            "build": local_info.build_release,
                            "branch": local_info.branch}
                        if gui_misc.same_pkg_versions(local_info, remote_info):
                                # Installed and up to date
                                installable_label = \
                                    _("Installed package is up-to-date")
                                self.__hide_pkg_version_details()
                        else:
                                if plan_pkg == None:
                                        # Installed with later version but can't upgrade
                                        # Upgradeable Version: None
                                        installable_label = _("None")
                                        self.__setup_version_info_details(name,
                                            remote_info.version,
                                            remote_info.build_release,
                                            remote_info.branch, False)
                                else:
                                        # Installed with later version and can upgrade to
                                        # Upgradeable Version: <version>
                                        # Upgradeable == Latest Version
                                        if gui_misc.same_pkg_versions(plan_pkg,
                                            remote_info):
                                                installable_label = installable_fmt % \
                                                    {"version": plan_pkg.version,
                                                    "build": plan_pkg.build_release,
                                                    "branch": plan_pkg.branch}
                                                self.__hide_pkg_version_details()
                                        else:
                                        # Installed with later version and can upgrade
                                        # Upgradeable Version: <version>
                                        # but NOT to the Latest Version
                                                installable_label = installable_fmt % \
                                                    {"version": plan_pkg.version,
                                                    "build": plan_pkg.build_release,
                                                    "branch": plan_pkg.branch}

                                                self.__setup_version_info_details(name,
                                                    remote_info.version,
                                                    remote_info.build_release,
                                                    remote_info.branch, False)
                else:
                        # Not Installed
                        installed_label = _("No")
                        if plan_pkg:
                                # Not installed with later version available to install
                                # Installable: <version>
                                # Installable == Latest Version
                                if gui_misc.same_pkg_versions(plan_pkg, remote_info):
                                        installable_label = installable_fmt % \
                                            {"version": plan_pkg.version,
                                            "build": plan_pkg.build_release,
                                            "branch": plan_pkg.branch}
                                        self.__hide_pkg_version_details()
                                else:
                                        # Not installed with later version available
                                        # Installable: <version>
                                        # but NOT to the Latest Version
                                        installable_label = installable_fmt % \
                                            {"version": plan_pkg.version,
                                            "build": plan_pkg.build_release,
                                            "branch": plan_pkg.branch}
                                            
                                        self.__setup_version_info_details(name,
                                            remote_info.version,
                                            remote_info.build_release,
                                            remote_info.branch, True)
                        else:
                                # Not Installed with later version and can't install
                                # Installable Version: None
                                installable_label = _("None")
                                self.__setup_version_info_details(name,
                                    remote_info.version,
                                    remote_info.build_release,
                                    remote_info.branch, True)
                        
                self.w_info_installed_label.set_text(installed_label)
                self.w_info_installable_label.set_text(installable_label)
                self.w_info_installable_prefix_label.set_markup(installable_prefix_label)
                self.w_info_ok_button.grab_focus()                
                self.w_version_info_dialog.show()
                self.unset_busy_cursor()

        def __setup_version_info_details(self, name, version, build_release, branch,
            to_be_installed):
                installable_fmt = \
                    _("%(version)s (Build %(build)s-%(branch)s)")
                if to_be_installed:
                        expander_fmt = _(
                            "The latest version of %s cannot be installed. "
                            "It may be possible to do so after updating your system. "
                            "Run \"Updates\" to get your system up-to-date.")
                else:
                        expander_fmt = _(
                            "Cannot upgrade to the latest version of %s. "
                            "It may be possible to do so after updating your system. "
                            "Run \"Updates\" to get your system up-to-date.")
                installable_exp = installable_fmt % \
                    {"version": version,
                    "build": build_release,
                    "branch": branch}
                expander_text = installable_exp + "\n\n"
                expander_text += expander_fmt % name   
                
                # Ensure we have enough room for the Details message
                # without requiring a scrollbar  
                self.w_info_textview.set_size_request(484, 95)
                self.w_info_expander.set_expanded(True)
                self.w_info_expander.show()

                details_buff = self.w_info_textview.get_buffer()
                details_buff.set_text("")
                itr = details_buff.get_iter_at_line(0)
                details_buff.insert_with_tags_by_name(itr,
                    _("Latest Version: "), "bold")
                details_buff.insert(itr, expander_text)
                         
        def __on_info_ok_button_clicked(self, widget):
                self.w_version_info_dialog.hide()

        @staticmethod
        def __on_info_help_button_clicked(widget):
                gui_misc.display_help("package-version")

        def __on_version_info_dialog_delete_event(self, widget, event):
                self.__on_info_ok_button_clicked(None)
                return True

        def __do_api_reset(self):
                try:
                        self.api_o.reset()
                except api_errors.ApiException, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err,
                            None, gtk.MESSAGE_INFO)
                        return False
                return True

        def __on_install_update(self, widget):
                if not self.__do_api_reset():
                        return
                install_update = []
                confirmation_list = None
                if self.show_install:
                        confirmation_list = []

                if self.all_selected > 0:
                        self.__add_install_update_pkgs_for_publishers(
                                    install_update, confirmation_list)

                if self.img_timestamp != self.cache_o.get_index_timestamp():
                        self.img_timestamp = None

                installupdate.InstallUpdate(install_update, self, \
                    self.image_directory, action = enumerations.INSTALL_UPDATE,
                    main_window = self.w_main_window,
                    confirmation_list = confirmation_list)

        def __on_update_all(self, widget):
                if not self.__do_api_reset():
                        return
                confirmation = None
                if self.show_image_update:
                        confirmation = []
                installupdate.InstallUpdate([], self,
                    self.image_directory, action = enumerations.IMAGE_UPDATE,
                    parent_name = _("Package Manager"),
                    pkg_list = [gui_misc.package_name["SUNWipkg"],
                    gui_misc.package_name["SUNWipkg-gui"]],
                    main_window = self.w_main_window,
                    icon_confirm_dialog = self.window_icon,
                    confirmation_list = confirmation)
                return

        def __on_help_about(self, widget):
                wTreePlan = gtk.glade.XML(self.gladefile, "aboutdialog")
                aboutdialog = wTreePlan.get_widget("aboutdialog")
                aboutdialog.set_icon(self.window_icon)
                aboutdialog.connect("response", lambda x = None, \
                    y = None: aboutdialog.destroy())
                aboutdialog.run()

        @staticmethod
        def __on_help_help(widget):
                gui_misc.display_help()

        def __add_remove_pkgs_for_publishers(self, remove_list, confirmation_list):
                for pub_name in self.selected_pkgs:
                        pub_display_name = self.__get_publisher_display_name_from_prefix(
                            pub_name)
                        pkgs = self.selected_pkgs.get(pub_name)
                        if not pkgs:
                                break
                        for pkg_stem in pkgs:
                                status = pkgs.get(pkg_stem)[0]
                                if status == api.PackageInfo.INSTALLED or \
                                    status == api.PackageInfo.UPGRADABLE:
                                        remove_list.append(pkg_stem)
                                        if self.show_remove:
                                                desc = pkgs.get(pkg_stem)[1]
                                                pkg_name = pkgs.get(pkg_stem)[2]
                                                confirmation_list.append(
                                                    [pkg_name, pub_display_name,
                                                    desc, status])

        def __on_remove(self, widget):
                if not self.__do_api_reset():
                        return
                remove_list = []
                confirmation_list = None
                if self.show_remove:
                        confirmation_list = []
                if self.all_selected > 0:
                        self.__add_remove_pkgs_for_publishers(remove_list, 
                            confirmation_list)

                if self.img_timestamp != self.cache_o.get_index_timestamp():
                        self.img_timestamp = None

                installupdate.InstallUpdate(remove_list, self,
                    self.image_directory, action = enumerations.REMOVE,
                    main_window = self.w_main_window,
                    confirmation_list = confirmation_list)

        def __on_reload(self, widget):
                self.force_reload_packages = True
                self.__do_reload(widget)

        def __do_reload(self, widget):
                self.w_repository_combobox.grab_focus()
                if self.force_reload_packages and (self.in_search_mode 
                    or self.is_all_publishers):
                        self.__unset_search(False)
                self.__set_empty_details_panel()
                self.in_setup = True
                self.last_visible_publisher = None
                self.set_busy_cursor()
                status_str = _("Refreshing package catalog information")
                self.__update_statusbar_message(status_str)
                Thread(target = self.__catalog_refresh).start()

        def __catalog_refresh(self):
                """Update image's catalogs."""
                success = self.__do_refresh(immediate=True)
                if not success:
                        gobject.idle_add(self.unset_busy_cursor)
                        gobject.idle_add(self.update_statusbar)
                        return -1
                gobject.idle_add(self.__clear_recent_searches)
                self.__catalog_refresh_done()
                return 0

        def __catalog_refresh_done(self):
                if not self.exiting:
                        gobject.idle_add(self.process_package_list_start)

        def __get_publisher_name_from_index(self, index):
                name = None
                if index != -1:
                        itr = self.repositories_list.iter_nth_child(None,
                            index)
                        name = self.repositories_list.get_value(itr,
                            enumerations.REPOSITORY_PREFIX)
                return name

        def __shutdown_part1(self):
                self.cancelled = True
                self.exiting = True
                self.__progress_pulse_stop()

                self.w_main_window.hide()
                gui_misc.shutdown_logging()

        def __shutdown_part2(self):
                if self.api_o and self.api_o.can_be_canceled():
                        Thread(target = self.api_o.cancel, args = ()).start()
                self.__do_exit()
                gobject.timeout_add(1000, self.__do_exit)

        def __main_application_quit(self, restart = False):
                '''quits the main gtk loop'''
                save_width, save_height = self.w_main_window.get_size()
                save_hpos = self.w_main_hpaned.get_position()
                save_vpos = self.w_main_vpaned.get_position()
                
                self.__shutdown_part1()
                pub = ""
                start_insearch = False
                width = height = hpos = vpos = -1
                if self.save_state:
                        if self.is_all_publishers:
                                start_insearch = True
                        if self.is_all_publishers or self.is_all_publishers_installed:
                                sel_pub = self.__get_publisher_name_from_index(
                                    self.saved_repository_combobox_active)
                        else:
                                sel_pub = self.__get_selected_publisher()
                        if sel_pub != None:
                                pub = sel_pub
                        width = save_width
                        height = save_height
                        hpos = save_hpos
                        vpos = save_vpos
                try:
                        if self.last_export_selection_path:
                                self.client.set_string(LAST_EXPORT_SELECTION_PATH,
                                    self.last_export_selection_path)
                        self.client.set_string(LASTSOURCE_PREFERENCES, pub)
                        self.client.set_bool(START_INSEARCH_PREFERENCES,
                            start_insearch)
                        self.client.set_int(INITIAL_APP_WIDTH_PREFERENCES, width)
                        self.client.set_int(INITIAL_APP_HEIGHT_PREFERENCES, height)
                        self.client.set_int(INITIAL_APP_HPOS_PREFERENCES, hpos)
                        self.client.set_int(INITIAL_APP_VPOS_PREFERENCES, vpos)
                except GError:
                        pass

                if restart:
                        gobject.spawn_async([self.application_path, "-R",
                            self.image_directory, "-U"])
                else:
                        if self.is_all_publishers or self.is_all_publishers_installed:
                                pub = self.__get_publisher_name_from_index(
                                    self.saved_repository_combobox_active)
                        else:
                                pub = self.__get_selected_publisher()

                if self.cache_o != None:
                        if len(self.search_completion) > 0:
                                self.cache_o.dump_search_completion_info(
                                    self.search_completion)
                        if len(self.category_active_paths) > 0:
                                self.cache_o.dump_categories_active_dict(
                                    self.category_active_paths)
                        if len(self.category_expanded_paths) > 0:
                                self.cache_o.dump_categories_expanded_dict(
                                    self.category_expanded_paths)

                self.__shutdown_part2()
                return True

        def __do_exit(self):
                if threading.activeCount() == 1:
                        if not self.before_start:
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

        @staticmethod
        def __alias_clash(pubs, prefix, alias):
                clash = False
                if alias != None and len(alias) > 0:
                        for pub in pubs:
                                if pub.disabled:
                                        continue
                                if pub.prefix == prefix:
                                        continue
                                if alias == pub.prefix or alias == pub.alias:
                                        clash = True
                                        break
                return clash

        def __setup_repositories_combobox(self, api_o):
                previous_publisher = None
                previous_saved_name = None
                if not self.first_run:
                        previous_publisher = self.__get_selected_publisher()
                        if self.saved_repository_combobox_active != -1:
                                itr = self.repositories_list.iter_nth_child(None,
                                    self.saved_repository_combobox_active)
                                previous_saved_name = \
                                   self.repositories_list.get_value(itr, 
                                   enumerations.REPOSITORY_PREFIX)
                self.__disconnect_repository_model()
                self.repositories_list = self.__get_new_repositories_liststore()
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
                self.pubs_info = {}
                self.pubs_display_name = {}
                pubs = api_o.get_publishers()
                for pub in pubs:
                        self.pubs_info[pub.prefix] = (pub.disabled, pub.alias)
                        if pub.disabled:
                                continue
                        alias = pub.alias
                        prefix = pub.prefix
                        if self.__alias_clash(pubs, prefix, alias):
                                display_name = "%s (%s)" % (alias, prefix)
                        elif alias == None or len(alias) == 0:
                                display_name = prefix
                        else:
                                display_name = alias
                        self.pubs_display_name[pub.prefix] = display_name
                        if cmp(prefix, self.default_publisher) == 0:
                                active = i
                        self.repositories_list.append([i, display_name, prefix, alias ])
                        enabled_repos.append(prefix)
                        i = i + 1
                self.repositories_list.append([-1, "", None, None, ])
                i = i + 1
                self.repo_combobox_all_pubs_installed_index = i
                self.repositories_list.append(
                    [self.repo_combobox_all_pubs_installed_index, 
                    self.publisher_options[PUBLISHER_INSTALLED],
                    self.publisher_options[PUBLISHER_INSTALLED], None, ])
                i = i + 1
                self.repo_combobox_all_pubs_index = i
                self.repositories_list.append([self.repo_combobox_all_pubs_index, 
                    self.publisher_options[PUBLISHER_ALL],
                    self.publisher_options[PUBLISHER_ALL], None, ])
                i = i + 1
                self.repositories_list.append([-1, "", None, None, ])
                i = i + 1
                self.repo_combobox_add_index = i
                self.repositories_list.append([-1,
                    self.publisher_options[PUBLISHER_ADD],
                    self.publisher_options[PUBLISHER_ADD], None, ])
                pkgs_to_remove = []
                for repo_name in selected_repos:
                        if repo_name not in enabled_repos:
                                pkg_stems = self.selected_pkgs.get(repo_name)
                                for pkg_stem in pkg_stems:
                                        pkgs_to_remove.append(pkg_stem)
                for pkg_stem in pkgs_to_remove:
                        self.__remove_pkg_stem_from_list(pkg_stem)
                self.w_repository_combobox.set_model(self.repositories_list)
                selected_id = -1
                self.same_publisher_on_setup = False
                if self.first_run:
                        for repo in self.repositories_list:
                                if (repo[enumerations.REPOSITORY_PREFIX] == \
                                    self.lastsource and
                                    repo[enumerations.REPOSITORY_ID] != -1):
                                        selected_id = \
                                           repo[enumerations.REPOSITORY_ID]
                                        break
                else:
                        for repo in self.repositories_list:
                                if (repo[enumerations.REPOSITORY_PREFIX] ==
                                    previous_publisher and
                                    repo[enumerations.REPOSITORY_ID] != -1):
                                        selected_id = \
                                           repo[enumerations.REPOSITORY_ID]
                                        if not self.force_reload_packages:
                                                self.same_publisher_on_setup = True
                                        break
                        if self.saved_repository_combobox_active != -1:
                                self.saved_repository_combobox_active = -1
                                for repo in self.repositories_list:
                                        if (repo[enumerations.REPOSITORY_PREFIX] ==
                                            previous_saved_name):
                                                self.saved_repository_combobox_active = \
                                                   repo[enumerations.REPOSITORY_ID]
                                                break
                                # Previous publisher no longer enabled
                                if self.saved_repository_combobox_active == -1:
                                        selected_id = -1
                                        self.same_publisher_on_setup = False
                if selected_id != -1:
                        self.w_repository_combobox.set_active(selected_id)
                elif self.default_publisher:
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
                                pkg_publisher = filterModel.get_value(itr, 
                                    enumerations.PUBLISHER_PREFIX_COLUMN)
                                pkg_description = filterModel.get_value(itr, 
                                    enumerations.DESCRIPTION_COLUMN)
                                pkg_name = filterModel.get_value(itr,
                                    enumerations.NAME_COLUMN)
                                self.__add_pkg_stem_to_list(pkg_stem, pkg_name,
                                    pkg_status, pkg_publisher, pkg_description)
                        self.update_statusbar()
                        self.__enable_disable_selection_menus()
                        self.__enable_disable_install_remove()

        def __update_reload_button(self):
                if self.user_rights:
                        self.w_reload_menuitem.set_sensitive(True)
                        self.w_reload_button.set_sensitive(True)
                else:
                        self.w_reload_menuitem.set_sensitive(False)
                        self.w_reload_button.set_sensitive(False)

        def __add_pkg_stem_to_list(self, stem, name, status, pub, description="test"):
                if self.selected_pkgs.get(pub) == None:
                        self.selected_pkgs[pub] = {}
                self.selected_pkgs.get(pub)[stem] = [status, description, name]
                if status == api.PackageInfo.KNOWN or \
                    status == api.PackageInfo.UPGRADABLE:
                        if self.to_install_update.get(pub) == None:
                                self.to_install_update[pub] = 1
                        else:
                                self.to_install_update[pub] += 1
                if status == api.PackageInfo.UPGRADABLE or \
                    status == api.PackageInfo.INSTALLED:
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
                self.w_installupdate_button.set_tooltip_text(to_install)
                if not to_remove:
                        to_remove = _("Select packages by marking the checkbox "
                            "and click to Remove selected.")
                self.w_remove_button.set_tooltip_text(to_remove)

        def __remove_pkg_stem_from_list(self, stem):
                remove_pub = []
                for pub in self.selected_pkgs:
                        pkgs = self.selected_pkgs.get(pub)
                        status = None
                        if stem in pkgs:
                                status = pkgs.pop(stem)[0]
                        if status == api.PackageInfo.KNOWN or \
                            status == api.PackageInfo.UPGRADABLE:
                                if self.to_install_update.get(pub) == None:
                                        self.to_install_update[pub] = 0
                                else:
                                        self.to_install_update[pub] -= 1
                        if status == api.PackageInfo.UPGRADABLE or \
                            status == api.PackageInfo.INSTALLED:
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
                # We clear the selections as the preferred repository was changed
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
                if not self.use_cache:
                        if debug:
                                print "DEBUG: __setting_from_cache: not using cache"
                        return False
                if len(self.info_cache) > MAX_INFO_CACHE_LIMIT:
                        self.info_cache = {}

                if self.info_cache.has_key(pkg_stem):
                        labs = self.info_cache[pkg_stem][
                            enumerations.INFO_GENERAL_LABELS]
                        text = self.info_cache[pkg_stem][
                            enumerations.INFO_GENERAL_TEXT]
                        gui_misc.set_package_details_text(labs, text,
                            self.w_generalinfo_textview,
                            self.installed_icon, self.not_installed_icon,
                            self.update_available_icon) 
                        text = self.info_cache[pkg_stem][
                            enumerations.INFO_INSTALLED_TEXT]
                        self.__set_installedfiles_text(text)
                        local_info = self.info_cache[pkg_stem][
                            enumerations.INFO_DEPEND_INFO]
                        dep_info = self.info_cache[pkg_stem][
                            enumerations.INFO_DEPEND_DEPEND_INFO]
                        installed_dep_info = self.info_cache[pkg_stem][
                            enumerations.INFO_DEPEND_DEPEND_INSTALLED_INFO]
                        self.__set_dependencies_text(local_info, dep_info,
                            installed_dep_info)
                        return True
                else:
                        return False

        def __set_installedfiles_text(self, text):
                instbuffer = self.w_installedfiles_textview.get_buffer()
                instbuffer.set_text("")
                itr = instbuffer.get_start_iter()
                instbuffer.insert(itr, text)

        def __set_dependencies_text(self, info, dep_info, installed_dep_info):
                names = []
                states = None
                installed_states = []
                if dep_info != None and len(dep_info.get(0)) >= 0:
                        states = dep_info[0]
                if installed_dep_info != None and len(installed_dep_info.get(0)) >= 0:
                        installed_states = installed_dep_info[0]
                version_fmt = _("%(version)s (Build %(build)s-%(branch)s)")
                i = 0
                for x in info.dependencies:
                        if states != None and len(states) > 0:
                                name = fmri.extract_pkg_name(x)
                                if i < len(states):
                                        version = version_fmt % \
                                            {"version": states[i].version,
                                            "build": states[i].build_release,
                                            "branch": states[i].branch}
                                else:
                                        version = version_fmt % \
                                            {"version": '0',
                                            "build": '0',
                                            "branch": '0'}
                                found = False
                                for state in installed_states:
                                        if name ==  fmri.extract_pkg_name(state.fmri):
                                                installed_version = version_fmt % \
                                                    {"version": state.version,
                                                    "build": state.build_release,
                                                    "branch": state.branch}
                                                found = True
                                                break
                                if not found:
                                        installed_version = (_("(not installed)"))
                                names.append((name, version, installed_version,
                                    found))
                                i += 1
                        else:
                                build_rel = "0"
                                pkg_fmri = fmri.PkgFmri(x, build_release=build_rel)
                                branch = pkg_fmri.version.branch
                                version_stripped = pkg_fmri.get_version().split("-%s"
                                    % branch)[0]
                                version = version_fmt % \
                                     {"version": version_stripped,
                                     "build": build_rel,
                                     "branch": branch}
                                names.append((pkg_fmri.pkg_name, version,
                                    _("(not installed)"), False))

                depbuffer = self.w_dependencies_textview.get_buffer()
                depbuffer.set_text("")
                if states == None:
                        if len(names) == 0:
                                itr = depbuffer.get_iter_at_line(0)
                                depbuffer.insert_with_tags_by_name(itr, 
                                    _("None"), "bold")
                        else:
                                for i in  range(0, len(names)):
                                        itr = depbuffer.get_iter_at_line(i)
                                        dep_str = "%s\n" % (names[i]) 
                                        depbuffer.insert(itr, dep_str)
                        return
                max_name_len = 0
                max_version_len = 0
                for (name, version, installed_version, is_installed) in names:
                        if len(name) > max_name_len:
                                max_name_len = len(name)
                        if len(version) > max_version_len:
                                max_version_len = len(version)

                style = self.w_dependencies_textview.get_style()
                font_size_in_pango_unit = style.font_desc.get_size()
                font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
                tab_array = pango.TabArray(3, True)
                i = 1
                tab_array.set_tab(i, pango.TAB_LEFT,
                    max_name_len * font_size_in_pixel + 1)
                i += 1
                tab_array.set_tab(i, pango.TAB_LEFT,
                    (max_name_len + max_version_len) * 
                    font_size_in_pixel + 2)
                self.w_dependencies_textview.set_tabs(tab_array)

                itr = depbuffer.get_iter_at_line(0)
                depbuffer.insert_with_tags_by_name(itr, 
                    _("Name\tDependency\tInstalled Version\n"), "bold")
                installed_icon = None
                not_installed_icon = None
                i += 0
                for (name, version, installed_version, is_installed) in names:
                        if is_installed:
                                if installed_icon == None:
                                        installed_icon = gui_misc.resize_icon(
                                            self.installed_icon,
                                            font_size_in_pixel)
                                icon = installed_icon
                        else:
                                if not_installed_icon == None:
                                        not_installed_icon = gui_misc.resize_icon(
                                            self.not_installed_icon,
                                            font_size_in_pixel)
                                icon = not_installed_icon
                        itr = depbuffer.get_iter_at_line(i + 1)
                        dep_str = "%s\t%s\t" % (name, version)
                        depbuffer.insert(itr, dep_str)
                        end_itr = depbuffer.get_end_iter()
                        depbuffer.insert_pixbuf(end_itr, icon)
                        depbuffer.insert(end_itr, " %s\n" % installed_version)
                        i += 1

        def __update_package_info(self, pkg, local_info, remote_info, dep_info,
            installed_dep_info, info_id):
                if self.showing_empty_details or (info_id != 
                    self.last_show_info_id):
                        return
                pkg_stem = pkg.get_pkg_stem()

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

                labs, text = gui_misc.set_package_details(pkg.get_name(), local_info,
                    remote_info, self.w_generalinfo_textview,
                    self.installed_icon, self.not_installed_icon,
                    self.update_available_icon,
                    self.is_all_publishers_installed, self.pubs_info)
                if not local_info:
                        # Package is not installed
                        local_info = remote_info

                if not remote_info:
                        remote_info = local_info

                inst_str = ""
                if local_info.dirs:
                        for x in local_info.dirs:
                                inst_str += ''.join("%s%s\n" % (
                                    self.api_o.root, x))
                if local_info.files:
                        for x in local_info.files:
                                inst_str += ''.join("%s%s\n" % (
                                    self.api_o.root, x))
                if local_info.hardlinks:
                        for x in local_info.hardlinks:
                                inst_str += ''.join("%s%s\n" % (
                                    self.api_o.root, x))
                if local_info.links:
                        for x in local_info.links:
                                inst_str += ''.join("%s%s\n" % (
                                    self.api_o.root, x))
                self.__set_installedfiles_text(inst_str)
                self.__set_dependencies_text(local_info, dep_info,
                    installed_dep_info)
                if self.use_cache:
                        self.info_cache[pkg_stem] = (labs, text, inst_str,
                            local_info, dep_info, installed_dep_info)
                self.unset_busy_cursor()

        @staticmethod
        def setup_package_license(licenses):
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
                return lic_u

        def __update_package_license(self, licenses, license_id):
                if self.showing_empty_details or (license_id !=
                    self.last_show_licenses_id):
                        return
                licbuffer = self.w_license_textview.get_buffer()
                licbuffer.set_text(self.setup_package_license(licenses))

        def __show_licenses(self):
                self.show_licenses_id = 0
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
                except api_errors.TransportError, tpex:
                        err = str(tpex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.InvalidDepotResponseException, idex:
                        err = str(idex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.ImageLockedError, ex:
                        err = str(ex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except Exception, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err)
                if self.showing_empty_details or (license_id != 
                    self.last_show_licenses_id):
                        return
                if not info or (info and len(info.get(0)) == 0):
                        try:
                        # Get license from remote
                                info = self.api_o.info([selected_pkgstem],
                                    False, frozenset([api.PackageInfo.LICENSES]))
                        except api_errors.TransportError, tpex:
                                err = str(tpex)
                                logger.error(err)
                                gui_misc.notify_log_error(self)
                        except api_errors.InvalidDepotResponseException, idex:
                                err = str(idex)
                                logger.error(err)
                                gui_misc.notify_log_error(self)
                        except api_errors.ImageLockedError, ex:
                                err = str(ex)
                                logger.error(err)
                                gui_misc.notify_log_error(self)
                        except Exception, ex:
                                err = str(ex)
                                gobject.idle_add(self.error_occurred, err)
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

        def __show_info(self, model, path):
                self.show_info_id = 0
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
                self.set_busy_cursor()
                Thread(target = self.__show_package_info,
                    args = (pkg, pkg_stem, pkg_status, self.last_show_info_id)).start()

        def __show_package_info(self, pkg, pkg_stem, pkg_status, info_id):
                local_info = None
                remote_info = None
                if not self.showing_empty_details and (info_id ==
                    self.last_show_info_id) and (pkg_status ==
                    api.PackageInfo.INSTALLED or pkg_status ==
                    api.PackageInfo.UPGRADABLE):
                        local_info = gui_misc.get_pkg_info(self, self.api_o, pkg_stem,
                            True)
                if not self.showing_empty_details and (info_id ==
                    self.last_show_info_id) and (pkg_status ==
                    api.PackageInfo.KNOWN or pkg_status ==
                    api.PackageInfo.UPGRADABLE):
                        remote_info = gui_misc.get_pkg_info(self, self.api_o, pkg_stem,
                            False)
                if not self.showing_empty_details and (info_id ==
                    self.last_show_info_id):
                        if local_info:
                                info = local_info
                        else:
                                info = remote_info
                        dep_info = None
                        installed_dep_info = None
                        if info and info.dependencies:
                                gobject.idle_add(self.set_busy_cursor)
                                try:
                                        try:
                                                dep_info = self.api_o.info(
                                                    info.dependencies,
                                                    False,
                                                    frozenset([api.PackageInfo.STATE,
                                                    api.PackageInfo.IDENTITY]))
                                                temp_info = []
                                                for depend in info.dependencies:
                                                        name = fmri.extract_pkg_name(
                                                            depend)
                                                        temp_info.append(name)
                                                installed_dep_info = self.api_o.info(
                                                    temp_info,
                                                    True,
                                                    frozenset([api.PackageInfo.STATE,
                                                    api.PackageInfo.IDENTITY]))
                                        except api_errors.TransportError, tpex:
                                                err = str(tpex)
                                                logger.error(err)
                                                gui_misc.notify_log_error(self)
                                        except api_errors.InvalidDepotResponseException, \
                                                idex:
                                                err = str(idex)
                                                logger.error(err)
                                                gui_misc.notify_log_error(self)
                                        except api_errors.ImageLockedError, ex:
                                                err = str(ex)
                                                logger.error(err)
                                                gui_misc.notify_log_error(self)
                                        except Exception, ex:
                                                err = str(ex)
                                                gobject.idle_add(self.error_occurred, err)
                                finally:
                                        gobject.idle_add(self.unset_busy_cursor)
                        gobject.idle_add(self.__update_package_info, pkg,
                            local_info, remote_info, dep_info, installed_dep_info,
                            info_id)
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
                if len(cat_path) == 1 and selected_category > RECENT_SEARCH_ID_OFFSET:
                        selected_section = selected_category
                        return selected_section, 0
                elif len(cat_path) == 1 and selected_category > SECTION_ID_OFFSET:
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
                        
                in_recent_search = False
                if selected_section == 0 and selected_category == 0:
                        #Clicked on All Categories
                        category = True
                elif selected_category != 0:
                        #Clicked on subcategory
                        if category_list and selected_category in category_list:
                                category = True
                elif category_list:
                        #Clicked on Top Level section                        
                        if selected_section < RECENT_SEARCH_ID_OFFSET:
                                categories_in_section = \
                                        self.section_categories_list[selected_section]
                                for cat_id in category_list:
                                        if cat_id in categories_in_section:
                                                category = True
                                                break
                        else:
                                in_recent_search = True
                if (model.get_value(itr, enumerations.IS_VISIBLE_COLUMN) == False):
                        return False
                if self.in_search_mode or in_recent_search:
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
                        return (status == api.PackageInfo.INSTALLED or status == \
                            api.PackageInfo.UPGRADABLE)
                elif filter_id == enumerations.FILTER_UPDATES:
                        return status == api.PackageInfo.UPGRADABLE
                elif filter_id == enumerations.FILTER_NOT_INSTALLED:
                        return status == api.PackageInfo.KNOWN

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
                model =  self.w_application_treeview.get_model()
                if model != None and len(model) > 0:
                        for row in model:
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
                self.__enable_if_selected_for_removal()
                self.__enable_if_selected_for_install_update()
                self.__enable_disable_export_selections()

        def __enable_if_selected_for_removal(self):
                sensitive = False
                selected = 0
                for pub in self.to_remove:
                        selected = self.to_remove.get(pub)
                        if selected > 0:
                                break
                if selected > 0:
                        sensitive = True
                self.w_remove_button.set_sensitive(sensitive)
                self.w_remove_menuitem.set_sensitive(sensitive)
                return sensitive

        def __enable_if_selected_for_install_update(self):
                sensitive = False
                selected = 0
                for pub in self.to_install_update:
                        selected = self.to_install_update.get(pub)
                        if selected > 0:
                                break
                if selected > 0:
                        sensitive = True
                self.w_installupdate_button.set_sensitive(sensitive)
                self.w_installupdate_menuitem.set_sensitive(sensitive)
                return sensitive

        def __enable_disable_select_updates(self):
                model = self.w_application_treeview.get_model()
                if model == None:
                        return
                for row in model:
                        if row[enumerations.STATUS_COLUMN] == api.PackageInfo.UPGRADABLE:
                                if not row[enumerations.MARK_COLUMN]:
                                        self.w_selectupdates_menuitem. \
                                            set_sensitive(True)
                                        return
                self.w_selectupdates_menuitem.set_sensitive(False)
                return

        def __enable_disable_export_selections(self):
                if self.selected_pkgs == None or len(self.selected_pkgs) == 0:
                        self.w_export_selections_menuitem.set_sensitive(False)
                else:
                        self.w_export_selections_menuitem.set_sensitive(True)
                return

        def __enable_disable_deselect(self):
                if self.w_application_treeview.get_model():
                        for row in self.w_application_treeview.get_model():
                                if row[enumerations.MARK_COLUMN]:
                                        self.w_deselect_menuitem.set_sensitive(True)
                                        return
                self.w_deselect_menuitem.set_sensitive(False)
                return

        def __add_pkgs_to_lists_from_api(self, pub, application_list,
            category_list, section_list):
                pubs = []
                pkgs_from_api = []

                status_str = _("Loading package list")
                gobject.idle_add(self.__update_statusbar_message, status_str)
                try:                
                        if self.is_all_publishers_installed:
                                pkgs_from_api = self.api_o.get_pkg_list(pubs = pubs,
                                    pkg_list = api.ImageInterface.LIST_INSTALLED)
                        else:
                                pubs.append(pub)
                                pkgs_from_api = self.api_o.get_pkg_list(pubs = pubs,
                                    pkg_list = api.ImageInterface.LIST_INSTALLED_NEWEST)
                except api_errors.InventoryException:
                        # This can happen if the repository does not
                        # contain any packages
                        err = _("Selected publisher does not contain any packages.")
                        gobject.idle_add(self.error_occurred, err, None,
                            gtk.MESSAGE_INFO)
                        gobject.idle_add(self.unset_busy_cursor)
                except api_errors.ApiException, apiex:
                        err = str(apiex)
                        gobject.idle_add(self.error_occurred, err, _('Unexpected Error'))
                        gobject.idle_add(self.unset_busy_cursor)
                try:    
                        self.__add_pkgs_to_lists(pkgs_from_api, pubs, application_list,
                            category_list, section_list)
                except api_errors.TransportError, tpex:
                        err = str(tpex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.ApiException, apiex:
                        err = str(apiex)
                        gobject.idle_add(self.error_occurred, err, _('Unexpected Error'))
                        gobject.idle_add(self.unset_busy_cursor)
                        
        def __get_categories_for_pubs(self, pubs):
                sections = {}
                #ImageInfo for categories
                sectioninfo = imageinfo.ImageInfo()
                share_path = os.path.join(self.application_dir, 
                        "usr/share/package-manager/data")
                if len(pubs) == 0:
                        section = sectioninfo.read(os.path.join(share_path,
                                    "opensolaris.org.sections"))
                        sections["opensolaris.org"] = section
                        return sections
                        
                for pub in pubs:
                        if debug_perf:
                                a = time.time()
                        section = sectioninfo.read(os.path.join(share_path,
                            pub + ".sections"))
                        if len(section) == 0:
                                section = sectioninfo.read(os.path.join(share_path,
                                    "opensolaris.org.sections"))
                        sections[pub] = section
                        if debug_perf:
                                print "Time for get_pkg_categories", time.time() - a

                return sections

        def __add_pkgs_to_lists_from_info(self, local_results, remote_results, 
            application_list):
                status_str = _("Loading package list")
                gobject.idle_add(self.__update_statusbar_message, status_str)

                pkg_add = self.__add_pkgs_to_lists_from_results(local_results,
                    0, application_list)
                self.__add_pkgs_to_lists_from_results(remote_results,
                    pkg_add, application_list)

        def __add_pkgs_to_lists_from_results(self, results, pkg_add,
            application_list):
                for result in results:
                        pkg_pub = result.publisher
                        pkg_name = result.pkg_stem
                        pkg_fmri = fmri.PkgFmri(result.fmri)
                        pkg_stem = pkg_fmri.get_pkg_stem()
                        summ = result.summary

                        if api.PackageInfo.INSTALLED in result.states:
                                if api.PackageInfo.UPGRADABLE in result.states:
                                        status_icon = self.update_available_icon
                                        pkg_state = api.PackageInfo.UPGRADABLE
                                else:
                                        status_icon = self.installed_icon
                                        pkg_state = api.PackageInfo.INSTALLED
                        else:
                                status_icon = self.not_installed_icon
                                pkg_state = api.PackageInfo.KNOWN
                        if not self.is_all_publishers and \
                            not self.is_all_publishers_installed:
                                pkg_name = gui_misc.get_minimal_unique_name(
                                    self.package_names, pkg_name,
                                    self.special_package_names)
                                if len(pkg_name) == 0:
                                        pkg_name = result.pkg_stem
                        marked = False
                        pkgs = self.selected_pkgs.get(pkg_pub)
                        if pkgs != None:
                                if pkg_stem in pkgs:
                                        marked = True
                        pub_name = self.__get_publisher_name_from_prefix(pkg_pub)
                        next_app = \
                            [
                                marked, status_icon, pkg_name, summ, pkg_state,
                                pkg_fmri, pkg_stem, result.pkg_stem, True,
                                None, pub_name, pkg_pub
                            ]
                        application_list.insert(pkg_add, next_app)
                        pkg_add += 1
                return pkg_add

        def __add_pkgs_to_lists(self, pkgs_from_api, pubs, application_list,
            category_list, section_list):
                if section_list != None:
                        self.__init_sections(section_list)
                sections = self.__get_categories_for_pubs(pubs)
                pkg_add = 0
                if debug_perf:
                        a = time.time()
                self.package_names = {}
                self.special_package_names = []

                for entry in pkgs_from_api:
                        (pkg_pub, pkg_name, ver), summ, cats, states = entry
                        if debug:
                                print entry
                        pkg_fmri = fmri.PkgFmri("%s@%s" % (pkg_name,
                            ver), publisher=pkg_pub)
                        pkg_stem = pkg_fmri.get_pkg_stem()
                        gui_misc.add_pkgname_to_dic(self.package_names, pkg_name, 
                            self.special_package_names)
                        if api.PackageInfo.INSTALLED in states:
                                pkg_state = api.PackageInfo.INSTALLED
                                if api.PackageInfo.UPGRADABLE in states:
                                        status_icon = self.update_available_icon
                                        pkg_state = api.PackageInfo.UPGRADABLE
                                else:
                                        status_icon = self.installed_icon
                        else:
                                pkg_state = api.PackageInfo.KNOWN
                                status_icon = self.not_installed_icon
                        marked = False
                        pkgs = self.selected_pkgs.get(pkg_pub)
                        if pkgs != None:
                                if pkg_stem in pkgs:
                                        marked = True
                        pub_name = self.__get_publisher_name_from_prefix(pkg_pub)
                        next_app = \
                            [
                                marked, status_icon, pkg_name, summ, pkg_state,
                                pkg_fmri, pkg_stem, pkg_name, True, None, pub_name,
                                pkg_pub
                            ]
                        self.__add_package_to_list(next_app,
                            application_list,
                            pkg_add, pkg_name,
                            cats, category_list, pkg_pub)
                        pkg_add += 1
                for pkg in application_list:
                        pkg_name = pkg[enumerations.NAME_COLUMN]
                        name = gui_misc.get_minimal_unique_name(self.package_names,
                            pkg_name, self.special_package_names)
                        if pkg_name != name:
                                pkg[enumerations.NAME_COLUMN] = name
                        
                if debug_perf:
                        print "Time to add packages:", time.time() - a
                if category_list != None:
                        self.__add_categories_to_sections(sections,
                            category_list, section_list)
                return

        def __add_categories_to_sections(self, sections, category_list, section_list):
                for pub in sections:
                        for section in sections[pub]:
                                self.__add_category_to_section(sections[pub][section],
                                    _(section), category_list, section_list)
                return

        def __add_package_to_list(self, app, application_list, pkg_add,
            pkg_name, cats, category_list, pub):
                row_iter = application_list.insert(pkg_add, app)
                if category_list == None:
                        return
                for cat in cats:
                        if len(cat[1]) > 1:
                                self.__add_package_to_category(cat[1],
                                    row_iter, application_list,
                                    category_list)

        @staticmethod
        def __add_package_to_category(category_name, package, 
            application_list, category_list):
                category_names = category_name.split('/', 2)
                if len(category_names) < 2:
                        return
                category_visible_name = category_names[1]
                if not package or category_visible_name == 'All':
                        return
                if not category_visible_name:
                        return
                category_id = None
                for category in category_list:
                        if category[enumerations.CATEGORY_NAME] == category_name:
                                category_id = category[enumerations.CATEGORY_ID]
                                break
                if not category_id:                       # Category not exists
                        category_id = len(category_list) + 1
                        category_list.append(None, [category_id, category_name,
                            category_visible_name, None, None, True])
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
                cat_iter = category_tree.append(None, [ 0, _("All Categories"),
                    _("All Categories"), None, None, True])

                self.section_categories_list = {}
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
                        section_name = "<b>" + section[enumerations.SECTION_NAME] + "</b>"
                        cat_iter = category_tree.append(None,
                            [ SECTION_ID_OFFSET + section[enumerations.SECTION_ID], 
                            section_name, section_name, None, None, True])

                        if not sec_id in self.section_categories_list:
                                continue
                        
                        category_ids = self.section_categories_list[sec_id]
                        category_list = self.__get_new_category_liststore()
                        for cat_id in category_ids.keys():
                                if category_ids[cat_id][
                                    enumerations.CATEGORY_IS_VISIBLE]:
                                        category_list.append(None, category_ids[cat_id])
                        # Sort the Categories into alphabetical order
                        if len(category_list) > 0:
                                rows = [tuple(r) + (i,) for i, 
                                    r in enumerate(category_list)]
                                rows.sort(self.__sort)
                                r = []
                                category_list.reorder(None, [r[-1] for r in rows])
                        for category in category_list:
                                category_tree.append(cat_iter, category)

                recent_search_name = "<span foreground='#757575'><b>" + \
                    _("Recent Searches") + "</b></span>"
                self.recent_searches_cat_iter = category_tree.append(None,
                    [RECENT_SEARCH_ID, recent_search_name, recent_search_name,
                    None, None, True])
                if self.recent_searches and len(self.recent_searches) > 0:
                        for recent_search in self.recent_searches_list:
                                category_tree.append(self.recent_searches_cat_iter, 
                                    self.recent_searches[recent_search])
                
                self.w_categories_treeview.set_model(category_tree)
                
                #Initial startup expand default Section if available
                if visible_default_section_path and self.first_run and \
                        len(self.category_active_paths) == 0 and \
                        len(self.category_expanded_paths) == 0:
                        self.w_categories_treeview.expand_row(
                            visible_default_section_path, False)
                        return
                self.__restore_category_state()

        def __add_recent_search(self, text, pub_prefix, application_list):
                self.adding_recent_search = True
                category_tree = self.w_categories_treeview.get_model()
                if category_tree == None:
                        return
                if self.is_all_publishers:
                        pub_name = _("All Publishers")
                else:
                        pub_name = self.__get_publisher_display_name_from_prefix(
                            pub_prefix)
                recent_search = "(%d) <b>%s</b> %s" % \
	        	(len(application_list), text, pub_name)
                if not (recent_search in self.recent_searches):
                        cat_iter = category_tree.append(self.recent_searches_cat_iter,
                            [RECENT_SEARCH_ID + 1, recent_search, recent_search, 
                            text, application_list, True])
                        self.recent_searches[recent_search] = \
                                [RECENT_SEARCH_ID + 1, recent_search, recent_search,
                                 text, application_list, True]
                        self.recent_searches_list.append(recent_search)
                else:
                        rs_iter = category_tree.iter_children(
                            self.recent_searches_cat_iter)
                        while rs_iter:
                                rs_value = category_tree.get_value(rs_iter,
                                    enumerations.CATEGORY_VISIBLE_NAME)
                                if rs_value == recent_search:
                                        category_tree.remove(rs_iter)
                                        break
                                rs_iter = category_tree.iter_next(rs_iter)
                        cat_iter = category_tree.append(self.recent_searches_cat_iter,
                            [RECENT_SEARCH_ID + 1, recent_search, recent_search, 
                            text, application_list, True])
                        self.recent_searches_list.remove(recent_search)
                        self.recent_searches_list.append(recent_search)
                path = category_tree.get_path(cat_iter)
                self.w_categories_treeview.expand_to_path(path)
                self.__unselect_category()
                self.w_categories_treeview.scroll_to_cell(path)
                self.adding_recent_search = False
                
        def __clear_recent_searches(self):
                self.after_install_remove = False
                category_tree = self.w_categories_treeview.get_model()
                if category_tree == None:
                        return                        
                if self.recent_searches == None or len(self.recent_searches) == 0:
                        return                        
                self.__set_searchentry_to_prompt()
                selection, sel_path = self.__get_selection_and_category_path()
                rs_iter = category_tree.iter_children(self.recent_searches_cat_iter)
                while rs_iter:
                        category_tree.remove(rs_iter)
                        if category_tree.iter_is_valid(rs_iter):
                                rs_iter = category_tree.iter_next(rs_iter)
                        else:
                                break
                del(self.recent_searches_list[:])
                self.recent_searches.clear()
                
                rs_path = category_tree.get_path(self.recent_searches_cat_iter)
                if selection and sel_path and rs_path and len(sel_path) > 0 and \
                        len(rs_path) > 0 and sel_path[0] == rs_path[0]:
                        self.__restore_setup_for_browse()

        def __update_recent_search_states(self, application_list):
                pkg_stems = []
                pkg_stem_states = {}
                for row in application_list:
                        pkg_stems.append(row[enumerations.STEM_COLUMN])
                #Check for changes in package installation status
                try:
                        info = self.api_o.info(pkg_stems, True, frozenset(
                                    [api.PackageInfo.STATE, api.PackageInfo.IDENTITY]))
                        for info_s in info.get(0):
                                pkg_stem = fmri.PkgFmri(info_s.fmri).get_pkg_stem(
                                    include_scheme = True)
                                if api.PackageInfo.INSTALLED in info_s.states:
                                        pkg_stem_states[pkg_stem] = \
                                                api.PackageInfo.INSTALLED
                                else:
                                        pkg_stem_states[pkg_stem] = \
                                                api.PackageInfo.KNOWN
                except api_errors.TransportError, tpex:
                        err = str(tpex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.InvalidDepotResponseException, idex:
                        err = str(idex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except api_errors.ImageLockedError, ex:
                        err = str(ex)
                        logger.error(err)
                        gui_misc.notify_log_error(self)
                except Exception, ex:
                        err = str(ex)
                        gobject.idle_add(self.error_occurred, err)

                #Create a new result list updated with current installation status
                tmp_app_list = self.__get_new_application_liststore()
                
                for row in application_list:
                        pkg_stem = row[enumerations.STEM_COLUMN]
                        pub = row[enumerations.PUBLISHER_COLUMN]
                        marked = False
                        pkgs = None
                        if self.selected_pkgs != None:
                                pkgs = self.selected_pkgs.get(pub)
                        if pkgs != None:
                                if pkg_stem in pkgs:
                                        marked = True
                        if row[enumerations.MARK_COLUMN] != marked:
                                row[enumerations.MARK_COLUMN] = marked
                        
                        if pkg_stem_states.has_key(pkg_stem):
                                row[enumerations.STATUS_COLUMN] = \
                                        pkg_stem_states[pkg_stem]
                                if pkg_stem_states[pkg_stem] == \
                                        api.PackageInfo.KNOWN:
                                        row[enumerations.STATUS_ICON_COLUMN] = \
                                                self.not_installed_icon
                                else:
                                        row[enumerations.STATUS_ICON_COLUMN] = \
                                                self.installed_icon
                        else:
                                row[enumerations.STATUS_COLUMN] = \
                                        api.PackageInfo.KNOWN
                                row[enumerations.STATUS_ICON_COLUMN] = \
                                        self.not_installed_icon
                        tmp_app_list.append(row)
                return tmp_app_list

        def __restore_recent_search(self, sel_category):
                if not sel_category:
                        return
                if not self.is_all_publishers:
                        self.__save_setup_before_search(single_search=True)

                application_list = sel_category[enumerations.SECTION_LIST_OBJECT]
                text = sel_category[enumerations.CATEGORY_DESCRIPTION]
                if self.after_install_remove:
                        application_list = self.__update_recent_search_states(
                            application_list)
                self.__clear_before_search(show_list=True, in_setup=False,
                    unselect_cat=False)
                self.in_search_mode = True
                self.in_recent_search = True
                self.__set_search_text_mode(enumerations.SEARCH_STYLE_NORMAL)
                self.w_searchentry.set_text(text)
                self.__set_main_view_package_list()
                self.__init_tree_views(application_list, None, None, None, None,
                    enumerations.NAME_COLUMN)

        def __setup_category_state(self):
                if self.cache_o == None:
                        return
                self.cache_o.load_categories_active_dict(self.category_active_paths)
                self.cache_o.load_categories_expanded_dict(self.category_expanded_paths)

        def __restore_category_state(self):
                #Restore expanded Category state
                if self.w_categories_treeview == None:
                        return
                model = self.w_categories_treeview.get_model()
                if model == None:
                        return
                if len(self.category_expanded_paths) > 0:
                        paths = self.category_expanded_paths.items()
                        for key, val in paths:
                                source, path = key
                                if self.last_visible_publisher == source and val:
                                        self.w_categories_treeview.expand_row(path, False)
                #Restore selected category path
                if self.last_visible_publisher in self.category_active_paths and \
                        self.category_active_paths[self.last_visible_publisher]:
                        self.w_categories_treeview.set_cursor(
                            self.category_active_paths[self.last_visible_publisher])
                else:
                        self.w_categories_treeview.set_cursor(0)
                return

        @staticmethod
        def __add_category_to_section(categories_list, section_name, category_list,
            section_list):
                '''Adds the section to section list in category. If there is no such
                section, than it is not added. If there was already section than it
                is skipped. Sections must be case sensitive'''
                if not categories_list:
                        return
                for section in section_list:
                        if section[enumerations.SECTION_NAME] == section_name:
                                section_id = section[enumerations.SECTION_ID]
                                for category in category_list:
                                        localized_top_cat = _(category[
                                            enumerations.CATEGORY_NAME].split("/")[0])
                                        if localized_top_cat == \
                                                section[enumerations.SECTION_NAME]:
                                                
                                                vis = \
                                                    enumerations.CATEGORY_VISIBLE_NAME
                                                category[vis] = _(category[
                                                    enumerations.CATEGORY_VISIBLE_NAME])
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
                                break


        def __progress_set_fraction(self, count, total):
                self.__progress_pulse_stop()
                if count == total:
                        self.w_progress_frame.hide()
                        return False
                if self.api_o and self.api_o.can_be_canceled():
                        self.progress_cancel.set_sensitive(True)
                else:
                        self.progress_cancel.set_sensitive(False)
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
                        if self.api_o and self.api_o.can_be_canceled():
                                gobject.idle_add(self.progress_cancel.set_sensitive, True)
                        else:
                                gobject.idle_add(self.progress_cancel.set_sensitive,
                                    False)
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

        @staticmethod
        def __sort(a, b):
                return cmp(a[2], b[2])

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

        def __get_version(self, api_o, local, pkg):
                version = None
                try:
                        info = api_o.info([pkg], local, frozenset(
                            [api.PackageInfo.STATE, api.PackageInfo.IDENTITY]))
                        found = info[api.ImageInterface.INFO_FOUND]
                        version = found[0]
                except IndexError:
                        pass
                except api_errors.ApiException, ex:
                        err = str(ex)
                        logger.error(err)
                        gobject.idle_add(gui_misc.notify_log_error, self)
                except Exception, ex:
                        pass
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
                self.cache_o = self.__get_cache_obj(self.api_o)
                self.force_reload_packages = False
                self.__do_reload(None)

        def is_busy_cursor_set(self):
                return self.gdk_window.is_visible()

        def set_busy_cursor(self):
                if self.gdk_window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN:
                        self.gdk_window.show()
                        self.w_main_window.get_accessible().emit('state-change',
                            'busy', True)
                if not self.exiting:
                        self.__progress_pulse_start()

        def unset_busy_cursor(self):
                self.__progress_pulse_stop()
                if not (self.gdk_window.get_state() & gtk.gdk.WINDOW_STATE_WITHDRAWN):
                        self.gdk_window.hide()
                        self.w_main_window.get_accessible().emit('state-change',
                            'busy', False)

        def process_package_list_start(self):
                if self.first_run:
                        self.__setup_filter_combobox()
                self.__setup_repositories_combobox(self.api_o)
                if self.first_run:
                        self.__update_reload_button()
                        self.w_repository_combobox.grab_focus()

        @staticmethod
        def __get_cache_obj(api_o):
                cache_o = cache.CacheListStores(api_o)
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
                        self.__on_update_all(None)
                        self.update_all_proceed = False
                self.__enable_disable_install_remove()
                self.update_statusbar()
                self.in_setup = False
                self.cancelled = False
                active_filter = self.w_filter_combobox.get_active()
                if self.set_section != 0 or \
                    active_filter != enumerations.FILTER_ALL:
                        self.__application_refilter()
                else:
                        if not self.__doing_search():
                                self.unset_busy_cursor()
                if debug_perf:
                        print "End process_package_list_end", time.time()
                if self.first_run:
                        if self.start_insearch:
                                self.w_repository_combobox.set_active(
                                    self.repo_combobox_all_pubs_index)
                        self.first_run = False

        def get_icon_pixbuf_from_glade_dir(self, icon_name):
                return gui_misc.get_pixbuf_from_path(
                    os.path.join(self.application_dir, 
                    "usr/share/package-manager/"),
                    icon_name)

        def __count_selected_packages(self):
                self.all_selected = 0
                for pub_name in self.selected_pkgs:
                        pkgs = self.selected_pkgs.get(pub_name)
                        if not pkgs:
                                break
                        self.all_selected += len(pkgs)
 
        def update_statusbar(self):
                '''Function which updates statusbar'''
                self.__remove_statusbar_message()
                search_text = self.w_searchentry.get_text()

                self.__count_selected_packages()
                if not self.in_search_mode:
                        if self.application_list == None:
                                return
                        self.length_visible_list = len(self.application_list_filter)
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
                if self.w_main_statusbar_label:
                        search_text = saxutils.escape(search_text)
                if self.w_main_statusbar_label:
                        s1 = "<b>"
                        e1 = "</b>"
                else:
                        s1 = e1 = '"'

                if self.__doing_search():
                        active_pub = self.search_all_pub_being_searched
                        status_str  = ""
                        if active_pub != None and active_pub != "":
                                status_str = \
                                        _("Searching %(s1)s%(active_pub)s%(e1)s"
                                        " for %(s1)s%(search_text)s%(e1)s ...") % \
                                        {"s1": s1, "active_pub": active_pub, "e1": e1,
                                        "search_text": search_text}
                        else:
                                status_str = \
                                        _("Searching for %(s1)s%(search_text)s%(e1)s "
                                        "...") % \
                                        {"s1": s1, "search_text": search_text, "e1": e1}
                else:
                        status_str = \
                                _("%(number)d packages found matching %(s1)s"
                                "%(search_text)s%(e1)s") % \
                                {"number": len(self.application_list),
                                    "s1": s1, "search_text": search_text, "e1": e1, }
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
                            (api.PackageInfo.INSTALLED in package_info.states)
                if package_installed:
                        package_info = self.__get_version(self.api_o,
                            local = False, pkg = pkg_stem)
                        if (package_info and
                            api.PackageInfo.INSTALLED in package_info.states):
                                row[enumerations.STATUS_COLUMN] = \
                                    api.PackageInfo.INSTALLED
                                row[enumerations.STATUS_ICON_COLUMN] = \
                                    self.installed_icon
                        else:
                                row[enumerations.STATUS_COLUMN] = \
                                    api.PackageInfo.UPGRADABLE
                                row[enumerations.STATUS_ICON_COLUMN] = \
                                    self.update_available_icon
                else:
                        row[enumerations.STATUS_COLUMN] = \
                            api.PackageInfo.KNOWN
                        row[enumerations.STATUS_ICON_COLUMN] = \
                            self.not_installed_icon
                row[enumerations.MARK_COLUMN] = False

        def __update_publisher_list(self, pub, full_list, package_list):
                for row in full_list:
                        if row[enumerations.FMRI_COLUMN] and \
                            row[enumerations.FMRI_COLUMN].pkg_name in package_list:
                                self.__reset_row_status(row)

        def update_package_list(self, update_list):
                if update_list == None and self.img_timestamp:
                        return
                self.after_install_remove = True
                visible_publisher = self.__get_selected_publisher()
                default_publisher = self.default_publisher
                self.__do_refresh()
                if update_list == None and not self.img_timestamp:
                        self.img_timestamp = self.cache_o.get_index_timestamp()
                        self.__on_reload(None)
                        return
                visible_list = update_list.get(visible_publisher)
                if self.is_all_publishers or self.is_all_publishers_installed \
                    or self.in_recent_search:
                        try:
                                pubs = self.api_o.get_publishers()
                        except api_errors.ApiException, ex:
                                err = str(ex)
                                gobject.idle_add(self.error_occurred, err,
                                    None, gtk.MESSAGE_INFO)
                                return
                        for pub in pubs:
                                if pub.disabled:
                                        continue
                                prefix = pub.prefix
                                package_list = update_list.get(prefix)
                                if package_list != None:
                                        self.__update_publisher_list(prefix,
                                            self.application_list,
                                            package_list)
                                        if self.last_visible_publisher == prefix:
                                                self.__update_publisher_list(prefix,
                                                        self.saved_application_list,
                                                        package_list)
                        if self.is_all_publishers_installed:
                                self.__do_set_publisher()
                elif visible_list:
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
                                                pkg_stem = self.__get_pkg_stem(
                                                    pkg, pub)
                                        else:
                                                pkg_stem = self.__get_pkg_stem(
                                                    pkg)
                                        if pkg_stem:
                                                if self.info_cache.has_key(pkg_stem):
                                                        del self.info_cache[pkg_stem]
                                                self.__remove_pkg_stem_from_list(pkg_stem)
                if not self.img_timestamp:
                        self.img_timestamp = self.cache_o.get_index_timestamp()
                        self.__on_reload(None)
                        return
                self.img_timestamp = self.cache_o.get_index_timestamp()
                if self.is_all_publishers_installed:
                        return
                # We need to reset status descriptions if a11y is enabled
                self.__set_visible_status(False)
                self.__process_package_selection()
                self.__enable_disable_selection_menus()
                self.__enable_disable_install_remove()
                self.update_statusbar()

        def __reset_home_dir(self):
                # We reset the HOME directory in case the user called us
                # with gksu and had NFS mounted home directory in which
                # case dbus called from gconf cannot write to the directory.
                if self.user_rights:
                        root_home_dir = self.__find_root_home_dir()
                        os.putenv('HOME', root_home_dir)

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

        @staticmethod
        def __get_pkg_stem(pkg_name, pkg_pub=None):
                pkg_str = "pkg:/"
                if pkg_pub == None:
                        return_str = "%s%s" % (pkg_str, pkg_name)
                else:
                        return_str = "%s/%s/%s" % (pkg_str, pkg_pub, pkg_name)
                return return_str

        def restart_after_ips_update(self):
                self.__main_application_quit(restart = True)

        def shutdown_after_image_update(self, exit_pm = False):
                if exit_pm == True:
                        self.__on_mainwindow_delete_event(None, None)

        def __get_api_object(self):
                self.api_o = gui_misc.get_api_object(self.image_directory, 
                    self.pr, self.w_main_window)
                self.cache_o = self.__get_cache_obj(self.api_o)
                self.img_timestamp = self.cache_o.get_index_timestamp()
                self.__setup_search_completion()
                self.__setup_category_state()
                gobject.idle_add(self.__got_api_object)

        def __got_api_object(self):
                self.process_package_list_start()
                
        def start(self):
                self.before_start = False
                self.set_busy_cursor()
                Thread(target = self.__get_api_object).start() 
        
        def unhandled_exception_shutdown(self):
                self.__shutdown_part1()
                self.__shutdown_part2()

###############################################################################
#-----------------------------------------------------------------------------#
# Main
#-----------------------------------------------------------------------------#

def installThreadExcepthook():
        """
        Workaround for sys.excepthook python thread bug from:
        Bug: sys.excepthook doesn't work in threads
        http://bugs.python.org/issue1230540#msg91244
        """
        init_old = threading.Thread.__init__
        def init(self, *ite_args, **ite_kwargs):
                init_old(self, *ite_args, **ite_kwargs)
                run_old = self.run
                def run_with_except_hook(*rweh_args, **rweh_kwargs):
                        try:
                                run_old(*rweh_args, **rweh_kwargs)
                        except (KeyboardInterrupt, SystemExit):
                                raise
                        except:
                                sys.excepthook(*sys.exc_info())
                self.run = run_with_except_hook
        threading.Thread.__init__ = init
    
def __display_unknown_err(trace):
        dmsg = _("An unknown error occurred")
        md = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, message_format=dmsg)
        close_btn = md.add_button(gtk.STOCK_CLOSE, 100)
        md.set_default_response(100)

        dmsg = _("Please let the developers know about this problem by\n"
                    "filing a bug together with the error details listed below at:")
        md.format_secondary_text(dmsg)
        md.set_title(_('Unexpected Error'))

        uri_btn = gtk.LinkButton(
            "http://defect.opensolaris.org/bz/enter_bug.cgi?product=pkg",
            "defect.opensolaris.org")
        uri_btn.set_relief(gtk.RELIEF_NONE)
        uri_btn.set_size_request(160, -1)
        align = gtk.Alignment(0, 0, 0, 0)
        align.set_padding(0, 0, 56, 0)
        align.add(uri_btn)
        textview = gtk.TextView()
        textview.show()
        textview.set_editable(False)
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(textview)
        fr = gtk.Frame()
        fr.set_shadow_type(gtk.SHADOW_IN)
        fr.add(sw)
        ca = md.get_content_area()
        ca.pack_start(align, False, False, 0)
        ca.pack_start(fr)

        textbuffer = textview.get_buffer()
        textbuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
        textbuffer.create_tag("level1", left_margin=30, right_margin=10)
        textiter = textbuffer.get_end_iter()
        textbuffer.insert_with_tags_by_name(textiter, _("Error details:\n"), "bold")
        textbuffer.insert_with_tags_by_name(textiter, trace.getvalue(), "level1")

        publisher_str = ""
        if packagemanager:
                publisher_str = \
                        gui_misc.get_publishers_for_output(packagemanager.api_o)
                if publisher_str != "":
                        textbuffer.insert_with_tags_by_name(textiter, 
                            _("\nList of configured publishers:"), "bold")
                        textbuffer.insert_with_tags_by_name(
                            textiter, publisher_str + "\n", "level1")
        
        if publisher_str == "":
                textbuffer.insert_with_tags_by_name(textiter, 
                    _("\nPlease include output from:\n"), "bold")
                textbuffer.insert(textiter, "$ pkg publisher\n")  
                
        ver = gui_misc.get_version()
        textbuffer.insert_with_tags_by_name(textiter,
            _("\npkg version:\n"), "bold")
        textbuffer.insert_with_tags_by_name(textiter, ver + "\n", "level1")

        md.set_size_request(550, 400)
        md.set_resizable(True)
        close_btn.grab_focus()
        md.show_all()
        md.run()        
        md.destroy()

def __display_unknown_err_ex(trace):
        try:
                __display_unknown_err(trace)
        except MemoryError:
                print trace
        except Exception:
                pass
        if packagemanager:
                packagemanager.unhandled_exception_shutdown()
        else:
                sys.exit()

def __display_memory_err():
        try:
                dmsg = misc.out_of_memory()
                msg_stripped = dmsg.replace("\n", " ")
                gui_misc.error_occurred(None, msg_stripped, _("Package Manager"),
                    gtk.MESSAGE_ERROR)
        except MemoryError:
                print dmsg
        except Exception:
                pass
        if packagemanager:
                packagemanager.unhandled_exception_shutdown()
        else:
                sys.exit()

def global_exception_handler(exctyp, value, tb):
        trace = StringIO()
        traceback.print_exception (exctyp, value, tb, None, trace)
        if exctyp is MemoryError:
                gobject.idle_add(__display_memory_err)
        else:
                gobject.idle_add(__display_unknown_err_ex, trace)

def main():
        gtk.main()
        return 0

sys.excepthook = global_exception_handler
if __name__ == '__main__':
        installThreadExcepthook()
        allow_links = False
        debug = False
        debug_perf = False
        max_filter_length = 0
        update_all_proceed = False
        app_path = None
        image_dir = None
        info_install_arg = None
        save_selected = _("Save selected...")
        save_selected_pkgs = _("Save selected packages...")
        reboot_needed = _("The installed package(s) require a reboot before "
            "installation can be completed.")

        try:
                opts, args = getopt.getopt(sys.argv[1:], "hR:Ui:", \
                    ["help", "allow-links", "image-dir=", "update-all",
                    "info-install="])
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
Use -U (--update-all) to proceed with Updates"""
                        sys.exit(0)
                elif option == "--allow-links":
                        allow_links = True
                elif option in ("-R", "--image-dir"):
                        image_dir = argument
                elif option in ("-U", "--update-all"):
                        update_all_proceed = True
                elif option in ("-i", "--info-install"):
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
        if info_install_arg or (args and not update_all_proceed):
                webinstall = webinstall.Webinstall(image_dir)
                if args:
                        info_install_arg = args[0]
                webinstall.process_param(info_install_arg)
                main()
                sys.exit(0)

        # Setup packagemanager
        packagemanager = PackageManager()
        packagemanager.application_path = app_path
        packagemanager.image_directory = image_dir
        packagemanager.allow_links = allow_links
        packagemanager.update_all_proceed = update_all_proceed

        while gtk.events_pending():
                gtk.main_iteration(False)

        max_filter_length = packagemanager.init_show_filter()

        gobject.idle_add(packagemanager.start)

        main()
