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
PACKAGE_PROGRESS_TOTAL_INCREMENTS = 95    # Total increments for loading phase
PACKAGE_PROGRESS_PERCENT_INCREMENT = 0.01 # Amount to update progress during loading phase
PACKAGE_PROGRESS_PERCENT_TOTAL = 1.0      # Total progress for loading phase
MAX_DESC_LEN = 60                         # Max length of the description
MAX_INFO_CACHE_LIMIT = 100                # Max number of package descriptions to cache
NOTEBOOK_PACKAGE_LIST_PAGE = 0            # Main Package List page index
NOTEBOOK_START_PAGE = 1                   # Main View Start page index
INFO_NOTEBOOK_LICENSE_PAGE = 3            # License Tab index
TYPE_AHEAD_DELAY = 600    # The last type in search box after which search is performed
SEARCH_STR_FORMAT = "<%s>"
SEARCH_LIMIT = 100                        # Maximum number of results shown for
                                          # remote search
MIN_APP_WIDTH = 750                       # Minimum application width
MIN_APP_HEIGHT = 500                     # Minimum application height
INITIAL_APP_WIDTH_PREFERENCES = "/apps/packagemanager/preferences/initial_app_width"
INITIAL_APP_HEIGHT_PREFERENCES = "/apps/packagemanager/preferences/initial_app_height"
INITIAL_APP_HPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_hposition"
INITIAL_APP_VPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_vposition"
INITIAL_SHOW_FILTER_PREFERENCES = "/apps/packagemanager/preferences/initial_show_filter"
INITIAL_SECTION_PREFERENCES = "/apps/packagemanager/preferences/initial_section"
SHOW_STARTPAGE_PREFERENCES = "/apps/packagemanager/preferences/show_startpage"
TYPEAHEAD_SEARCH_PREFERENCES = "/apps/packagemanager/preferences/typeahead_search"
REMOTE_SEARCH_ERROR_PREFERENCES = "/apps/packagemanager/preferences/remote_search_error"
CATEGORIES_STATUS_COLUMN_INDEX = 0   # Index of Status Column in Categories TreeView

STATUS_COLUMN_INDEX = 2   # Index of Status Column in Application TreeView

PKG_CLIENT_NAME = "packagemanager"

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
PKGINFO_SUFFIX   = '.p5i'      # Mime type file extension

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
from threading import Thread
from threading import Lock
from urllib2 import HTTPError, URLError
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
import pkg.client.retrieve as retrieve
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

CLIENT_API_VERSION = gui_misc.get_client_api_version()

class PackageManager:
        def __init__(self):
                signal.signal(signal.SIGINT, self.__main_application_quit)
                # We reset the HOME directory in case the user called us
                # with gksu and had NFS mounted home directory in which
                # case dbus called from gconf cannot write to the directory.
                if os.getuid() == 0:
                        dir = self.__find_root_home_dir()
                        os.putenv('HOME', dir)
                self.api_o = None
                self.cache_o = None
                self.img_timestamp = None
                self.client = gconf.client_get_default()
                try:
                        self.initial_show_filter = \
                            self.client.get_int(INITIAL_SHOW_FILTER_PREFERENCES)
                        self.initial_section = \
                            self.client.get_int(INITIAL_SECTION_PREFERENCES)
                        self.show_startpage = \
                            self.client.get_bool(SHOW_STARTPAGE_PREFERENCES)
                        self.typeahead_search = \
                            self.client.get_bool(TYPEAHEAD_SEARCH_PREFERENCES)
                        self.gconf_not_show_repos = \
                            self.client.get_string(REMOTE_SEARCH_ERROR_PREFERENCES)
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
                        self.initial_show_filter = 0
                        self.initial_section = 3
                        self.show_startpage = True
                        self.typeahead_search = False
                        self.gconf_not_show_repos = ""
                        self.initial_app_width = 800
                        self.initial_app_height = 600
                        self.initial_app_hpos = 200
                        self.initial_app_vpos = 320

                if not self.gconf_not_show_repos:
                        self.gconf_not_show_repos = ""
                self.set_show_filter = 0
                self.set_section = 0
                self.current_search_option = 0

                socket.setdefaulttimeout(
                    int(os.environ.get("PKG_CLIENT_TIMEOUT", "30"))) # in seconds

                # Override default PKG_TIMEOUT_MAX if a value has been specified
                # in the environment.
                global_settings.PKG_TIMEOUT_MAX = int(os.environ.get("PKG_TIMEOUT_MAX",
                    global_settings.PKG_TIMEOUT_MAX))

                global_settings.client_name = PKG_CLIENT_NAME

                try:
                        self.application_dir = os.environ["PACKAGE_MANAGER_ROOT"]
                except KeyError:
                        self.application_dir = "/"
                misc.setlocale(locale.LC_ALL, "")
                for module in (gettext, gtk.glade):
                        module.bindtextdomain("pkg", self.application_dir + \
                            "/usr/share/locale")
                        module.textdomain("pkg")
                # XXX Remove and use _() where self._ and self.parent._ are being used
                main_window_title = _('Package Manager')
                self.user_rights = portable.is_admin()
                self.cancelled = False                    # For background processes
                self.image_directory = None
                self.description_thread_running = False   # For background processes
                gtk.rc_parse('~/.gtkrc-1.2-gnome2')       # Load gtk theme
                self.progress_stop_timer_thread = False
                self.progress_fraction_time_count = 0
                self.progress_canceled = False
                self.catalog_loaded = False
                self.image_dir_arg = None
                self.update_all_proceed = False
                self.ua_be_name = None
                self.application_path = None
                self.default_publisher = None
                self.current_not_show_repos = []
                self.first_run = True
                self.in_reload = False
                self.in_search = False
                self.selected_pkgstem = None
                self.selected_model = None
                self.selected_path = None
                self.info_cache = {}
                self.selected = 0
                self.selected_pkgs = {}
                self.to_install_update = {}
                self.to_remove = {}
                self.in_startpage_startup = self.show_startpage
                self.lang = None
                self.lang_root = None
                self.visible_status_id = 0
                self.categories_status_id = 0
                self.search_options = [
                    ('ips-search',
                    gui_misc.get_icon_pixbuf(self.application_dir, 'search'),
                    _("_Current Repository (Name and Description)"),
                    _("Search Current Repository (Name and Description)")),
                    ('ips-search-all',
                    gui_misc.get_icon_pixbuf(self.application_dir, 'search_all'),
                    _("_All Repositories (Exact Match)"),
                    _("Search All Repositories (Exact Match)"))
                    ]
                self.__register_iconsets(self.search_options)

                self.visible_repository = None
                self.visible_repository_uptodate = False
                self.section_list = None
                self.filter_list = self.__get_new_filter_liststore()
                self.application_list = None
                self.a11y_application_treeview = None
                self.a11y_categories_treeview = None
                self.application_treeview_range = None
                self.application_treeview_initialized = False
                self.categories_treeview_range = None
                self.categories_treeview_initialized = False
                self.category_list = None
                self.repositories_list = None
                self.pr = progress.NullProgressTracker()
                self.pylintstub = None
                self.release_notes_url = "http://www.opensolaris.org"
                self.__image_activity_lock = Lock()

                # Create Widgets and show gui
                self.gladefile = self.application_dir + \
                    "/usr/share/package-manager/packagemanager.glade"
                w_tree_main = gtk.glade.XML(self.gladefile, "mainwindow")
                w_tree_progress = gtk.glade.XML(self.gladefile, "progressdialog")
                w_tree_preferences = gtk.glade.XML(self.gladefile, "preferencesdialog")
                w_tree_remote_search_error = gtk.glade.XML(self.gladefile,
                    "remote_search_error")
                self.w_preferencesdialog = \
                    w_tree_preferences.get_widget("preferencesdialog")
                self.w_startpage_checkbutton = \
                    w_tree_preferences.get_widget("startpage_checkbutton")
                self.w_typeaheadsearch_checkbutton = \
                    w_tree_preferences.get_widget("typeaheadsearch_checkbutton")
                self.remote_search_error_dialog = \
                    w_tree_remote_search_error.get_widget("remote_search_error")
                self.remote_search_error_textview = \
                    w_tree_remote_search_error.get_widget("remote_search_error_text")
                self.remote_search_checkbox = \
                    w_tree_remote_search_error.get_widget("remote_search_checkbox")
                self.remote_search_button = \
                    w_tree_remote_search_error.get_widget("remote_search_button")
                infobuffer = self.remote_search_error_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

                self.w_main_window = w_tree_main.get_widget("mainwindow")
                self.w_main_hpaned = \
                    w_tree_main.get_widget("main_hpaned")
                self.w_main_vpaned = \
                    w_tree_main.get_widget("main_vpaned")

                self.w_application_treeview = \
                    w_tree_main.get_widget("applicationtreeview")
                self.w_categories_treeview = w_tree_main.get_widget("categoriestreeview")
                self.w_info_notebook = w_tree_main.get_widget("details_notebook")
                self.w_generalinfo_textview = \
                    w_tree_main.get_widget("generalinfotextview")
                self.w_generalinfo_textview.set_wrap_mode(gtk.WRAP_WORD)
                self.w_installedfiles_textview = \
                    w_tree_main.get_widget("installedfilestextview")
                self.w_license_textview = \
                    w_tree_main.get_widget("licensetextview")
                self.w_dependencies_textview = \
                    w_tree_main.get_widget("dependenciestextview")
                self.w_packagename_label = w_tree_main.get_widget("packagenamelabel")
                self.w_shortdescription_label = \
                    w_tree_main.get_widget("shortdescriptionlabel")
                w_package_hbox = \
                    w_tree_main.get_widget("package_hbox")
                self.w_general_info_label = \
                    w_tree_main.get_widget("general_info_label")
                self.w_startpage_frame = \
                    w_tree_main.get_widget("startpage_frame")
                self.w_startpage_eventbox = \
                    w_tree_main.get_widget("startpage_eventbox")
                self.w_startpage_eventbox.modify_bg(gtk.STATE_NORMAL,
                    gtk.gdk.color_parse("white"))

                self.w_main_statusbar = w_tree_main.get_widget("statusbar")
                self.w_infosearch_frame = w_tree_main.get_widget("infosearch_frame")
                self.w_infosearch_button = w_tree_main.get_widget("infosearch_button")

                self.w_main_view_notebook = \
                    w_tree_main.get_widget("main_view_notebook")
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
                self.w_progress_dialog = w_tree_progress.get_widget("progressdialog")
                self.w_progress_dialog.connect('delete-event', lambda stub1, stub2: True)
                self.w_progress_dialog.set_title(_("Update All"))
                self.w_progressinfo_label = w_tree_progress.get_widget("progressinfo")
                self.w_progressinfo_label.set_text(_(
                    "Checking SUNWipkg and SUNWipkg-gui versions\n\nPlease wait ..."))
                self.w_progressbar = w_tree_progress.get_widget("progressbar")
                self.w_progressbar.set_pulse_step(0.1)
                self.w_progress_cancel = w_tree_progress.get_widget("progresscancel")
                self.progress_canceled = False
                self.w_clear_search_button = w_tree_main.get_widget("clear_search")
                self.w_clear_search_button.set_sensitive(False)
                clear_search_image = w_tree_main.get_widget("clear_image")
                clear_search_image.set_from_stock(gtk.STOCK_CLEAR, gtk.ICON_SIZE_MENU)
                self.saved_filter_combobox_active = self.initial_show_filter
                self.search_image = w_tree_main.get_widget("search_image")
                self.search_button = w_tree_main.get_widget("set_search")
                self.a11y_search_button = self.search_button.get_accessible()
                self.is_remote_search = False
                self.need_descriptions = True
                self.searchmenu = gtk.Menu()
                self.search_image.set_from_pixbuf(self.search_options[0][1])
                self.a11y_search_button.set_description(self.search_options[0][3])
                for stock_id, pixbuf, label, description in self.search_options:
                        action = gtk.Action(stock_id, label, None, stock_id)
                        action.connect('activate',
                            self.__search_menu_item_activate)
                        menu_item = action.create_menu_item()
                        self.searchmenu.append(menu_item)
                        self.pylintstub = description
                        self.pylintstub = pixbuf
                self.changing_search_option = False
                self.saved_repository_combobox_active = -1
                self.saved_sections_combobox_active = 0
                self.saved_application_list = None
                self.saved_application_list_filter = None
                self.saved_application_list_sort = None
                self.saved_category_list = None
                self.saved_section_list = None
                self.saved_selected_application_path = None
                self.search_message_id = 0
                toolbar =  w_tree_main.get_widget("toolbutton2")
                toolbar.set_expand(True)
                self.__init_repository_tree_view()
                self.install_button_tooltip = gtk.Tooltips()
                self.remove_button_tooltip = gtk.Tooltips()
                self.__update_reload_button()
                self.w_main_window.set_title(main_window_title)
                self.w_searchentry_dialog.grab_focus()

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
                                "on_searchentry_changed":self.__on_searchentry_changed,
                                "on_searchentry_focus_in_event": \
                                    self.__on_searchentry_focus_in,
                                "on_searchentry_focus_out_event": \
                                    self.__on_searchentry_focus_out,
                                "on_searchentry_event":self.__on_searchentry_event,
                                "on_searchentry_key_press_event": \
                                    self.__on_searchentry_key_press_event,
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
                                "on_settings_edit_repositories_activate": \
                                    self.__on_edit_repositories_activate,
                                "on_package_remove_activate":self.__on_remove,
                                "on_help_about_activate":self.__on_help_about,
                                "on_help_help_activate":self.__on_help_help,
                                "on_edit_paste_activate":self.__on_edit_paste,
                                "on_edit_clear_activate":self.__on_clear_paste,
                                "on_edit_copy_activate":self.__on_copy,
                                "on_edit_cut_activate":self.__on_cut,
                                "on_edit_search_activate":self.__on_edit_search_clicked,
                                "on_set_search_clicked":self.__on_set_search_clicked,
                                "on_set_search_button_press_event":self.__on_set_search,
                                "on_clear_search_clicked":self.__on_clear_search,
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
                            }
                        dic_progress = \
                            {
                                "on_cancel_progressdialog_clicked": \
                                    self.__on_cancel_progressdialog_clicked,
                            }
                        dic_preferences = \
                            {
                                "on_startpage_checkbutton_toggled": \
                                    self.__on_startpage_checkbutton_toggled,
                                "on_typeaheadsearch_checkbutton_toggled": \
                                    self.__on_typeaheadsearch_checkbutton_toggled,
                                "on_preferenceshelp_clicked": \
                                    self.__on_preferenceshelp_clicked,
                                "on_preferencesclose_clicked": \
                                    self.__on_preferencesclose_clicked,
                            }
                        dic_remote_search_error = \
                            {
                                "on_remote_search_checkbox_toggled": \
                                    self.__on_remote_search_checkbox_toggled,
                                "on_remote_search_button_clicked": \
                                    self.__on_remote_search_button_clicked,
                                "on_remote_search_error_delete_event": \
                                    self.__on_remote_search_error_delete_event,
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
                        w_tree_progress.signal_autoconnect(dic_progress)
                        w_tree_preferences.signal_autoconnect(dic_preferences)
                        w_tree_remote_search_error.signal_autoconnect(
                            dic_remote_search_error)
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
                # Until package icons become available hide Package Icon Panel
                w_package_hbox.hide()
                if self.show_startpage:
                        self.w_main_view_notebook.set_current_page(NOTEBOOK_START_PAGE)
                else:
                        self.w_main_view_notebook.set_current_page(
                            NOTEBOOK_PACKAGE_LIST_PAGE)
                self.remote_search_error_dialog.set_transient_for(self.w_main_window)

        def __register_iconsets(self, icon_info):
                factory = gtk.IconFactory()
                for stock_id, pixbuf, name, description in icon_info:
                        iconset = gtk.IconSet(pixbuf)
                        factory.add(stock_id, iconset)
                        self.pylintstub = name
                        self.pylintstub = description
                factory.add_default()

        def __set_search_option(self, i):
                # The value i is the index in the table search_options
                # of the current choice.
                # Index 0 corresponds to Current Repository.
                # We assume that anything else is remote search.
                # This may need to be revisited if more search options are
                # added.
                if i == self.current_search_option:
                        return
                self.current_search_option = i
                self.changing_search_option = True
                self.__update_repository_combobox_for_search(i != 0)
                self.__update_gui_for_search(i != 0)
                self.changing_search_option = False

        def __update_repository_combobox_for_search(self, is_remote):
                if is_remote:
                        self.saved_repository_combobox_active = \
                            self.w_repository_combobox.get_active()
                self.__disconnect_repository_model()
                if is_remote:
                        self.repositories_list.prepend(
                            [-1, _("All Repositories Search Results"), ])
                else:
                        self.repositories_list.remove(
                            self.repositories_list.get_iter_first())
                self.w_repository_combobox.set_model(self.repositories_list)
                self.visible_repository = None

        def __update_gui_for_search(self, is_remote):
                self.is_remote_search = is_remote
                self.__on_clear_search(None)
                self.current_not_show_repos = []
                self.w_infosearch_frame.hide()
                if is_remote:
                        self.need_descriptions = False
                        self.saved_sections_combobox_active = \
                            self.w_sections_combobox.get_active()
                        self.saved_filter_combobox_active = \
                            self.w_filter_combobox.get_active()
                        self.saved_application_list = self.application_list
                        self.saved_application_list_filter = \
                            self.application_list_filter
                        self.saved_application_list_sort = \
                            self.application_list_sort
                        self.saved_category_list = self.category_list
                        self.saved_section_list = self.section_list
                        model, itr = self.package_selection.get_selected()
                        if itr:
                                path = model.get_path(itr)
                                self.saved_selected_application_path = path
                        self.w_repository_combobox.set_active(0)
                        self.w_filter_combobox.set_active(0)
                        self.w_sections_combobox.set_active(0)
                        category_list = self.__get_new_category_liststore()
                        category_list.prepend([-1, _('All'), None, None, False,
                            True, None])
                        self.category_list = category_list
                        self.__init_tree_views(None, category_list, None)
                        self.__link_load_blank()
                        self.w_main_view_notebook.set_current_page(
                            NOTEBOOK_START_PAGE)
                        self.update_statusbar_for_search()
                        self.w_searchentry_dialog.grab_focus()
                else:
                        self.set_busy_cursor()
                        self.w_repository_combobox.set_active(
                            self.saved_repository_combobox_active)
                        self.set_section = self.saved_sections_combobox_active
                        self.set_show_filter = self.saved_filter_combobox_active
                        self.need_descriptions = True
                        self.__init_tree_views(self.saved_application_list,
                            self.saved_category_list, self.saved_section_list,
                            self.saved_application_list_filter,
                            self.saved_application_list_sort)
                        if self.saved_selected_application_path != None:
                                self.package_selection.select_path(
                                    self.saved_selected_application_path)
                                self.saved_selected_application_path = None
                        self.__set_main_view_package_list()

        def __link_load_blank(self):
                self.document.clear()
                self.document.open_stream('text/html')
                self.document.write_stream(_(
                    "<html><head></head><body></body></html>"))
                self.document.close_stream()

        def __search_menu_item_activate(self, widget):
                name = widget.get_name()
                i = 0
                for stock_id, pixbuf, label, description in self.search_options:
                        if stock_id == name:
                                self.__set_search_option(i)
                                self.search_image.set_from_pixbuf(pixbuf)
                                self.a11y_search_button.set_description(description)
                                break
                        i += 1
                        self.pylintstub = label

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
                self.__handle_startpage_load_error(start_page_url)


        def __load_startpage_locale(self, start_page_lang_base):
                start_page_url = self.application_dir + \
                        start_page_lang_base % (self.lang, START_PAGE_HOME)
                if self.__load_uri(self.document, start_page_url):
                        return True
                        
                if self.lang_root != None and self.lang_root != self.lang:
                        start_page_url = self.application_dir + \
                                start_page_lang_base % (self.lang_root, START_PAGE_HOME)
                        if self.__load_uri(self.document, start_page_url):
                                return True

                start_page_url = self.application_dir + \
                        start_page_lang_base % ("C", START_PAGE_HOME)                        
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

        def __parse_remote_search_error(self, error):
                self.current_not_show_repos = []
                if "failed_servers" in error.__dict__ and len(error.failed_servers) > 0:
                        # the error msg in the misc.py is not translated
                        rem_str = " doesn't speak a known version of search operation"
                        repos = []
                        for err in error.failed_servers:
                                err_str = str(err[1])
                                if rem_str in err_str:
                                        repo = err_str.replace(rem_str,"")
                                        self.current_not_show_repos.append(repo)

        def __on_infosearch_button_clicked(self, widget):
                self.__handle_remote_search_error(True)

        def __handle_remote_search_error(self, show_all=False):
                if len(self.current_not_show_repos) == 0:
                        self.w_infosearch_frame.hide()
                        return
                else:
                        self.w_infosearch_button.set_size_request(26, 22)
                        self.w_infosearch_frame.show()

                repo_pubs = self.__get_repo_publishers()
                repo_count = 0
                for url in self.current_not_show_repos:
                        if show_all or (url not in self.gconf_not_show_repos):
                                repo_count += 1
                if repo_count == 0:
                        return

                infobuffer = self.remote_search_error_textview.get_buffer()
                infobuffer.set_text("")
                textiter = infobuffer.get_end_iter()
                for url in self.current_not_show_repos:
                        if show_all or (url not in self.gconf_not_show_repos):
                                infobuffer.insert_with_tags_by_name(textiter,
                                        _("%s") % repo_pubs[url], "bold")
                                infobuffer.insert(textiter, _(" (%s)\n") % url)
                self.remote_search_checkbox.set_active(False)
                self.remote_search_error_dialog.show()
                self.remote_search_button.grab_focus()

        def __get_repo_publishers(self):
                repo_pub_dict = {}
                pubs = self.api_o.get_publishers()
                for pub in pubs:
                        repo = pub.selected_repository
                        origin = repo.origins[0]
                        repo_pub_dict[origin.uri] = pub.prefix
                return repo_pub_dict

        def __on_url(self, view, link):
                # Handle mouse over events on links and reset when not on link
                if link == None or link == "":
                        self.update_statusbar()
                else:
                        display_link = self.__handle_link(None, link, DISPLAY_LINK)
                        if display_link != None:
                                self.w_main_statusbar.push(0, display_link)
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
                self.w_main_statusbar.push(0, _("Loading... " + link))
                try:
                        f = self.__open_url(link)
                except  (IOError, OSError), err:
                        if debug:
                                print "err: %s" % (err)
                        self.w_main_statusbar.push(0, _("Stopped"))
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
                self.w_main_statusbar.push(0, _("Done"))
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
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.CATEGORY_ID
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_NAME
                        gobject.TYPE_STRING,      # enumerations.CATEGORY_DESCRIPTION
                        gtk.gdk.Pixbuf,           # enumerations.CATEGORY_ICON
                        gobject.TYPE_BOOLEAN,     # enumerations.CATEGORY_ICON_VISIBLE
                        gobject.TYPE_BOOLEAN,     # enumerations.CATEGORY_VISIBLE
                        gobject.TYPE_PYOBJECT,    # enumerations.SECTION_LIST_OBJECT
                        )

        @staticmethod
        def __get_new_section_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.SECTION_ID
                        gobject.TYPE_STRING,      # enumerations.SECTION_NAME
                        gobject.TYPE_STRING,      # enumerations.SECTION_SUBCATEGORY
                        gobject.TYPE_BOOLEAN,     # enumerations.SECTION_ENABLED
                        )

        @staticmethod
        def __get_new_filter_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.FILTER_ID
                        gobject.TYPE_STRING,      # enumerations.FILTER_NAME
                        )

        @staticmethod
        def __get_new_repositories_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.REPOSITORY_ID
                        gobject.TYPE_STRING,      # enumerations.REPOSITORY_NAME
                        )

        def __init_application_tree_view(self, application_list,
            application_list_filter, application_list_sort):
                ##APPLICATION MAIN TREEVIEW
                if application_list_filter == None:
                        application_list_filter = application_list.filter_new()
                if application_list_sort == None:
                        application_list_sort = \
                            gtk.TreeModelSort(application_list_filter)
                        application_list_sort.set_sort_column_id(
                            enumerations.NAME_COLUMN, gtk.SORT_ASCENDING)
                        application_list_sort.set_sort_func(
                            enumerations.STATUS_ICON_COLUMN, self.__status_sort_func)
                toggle_renderer = gtk.CellRendererToggle()

                column = gtk.TreeViewColumn("", toggle_renderer, \
                    active = enumerations.MARK_COLUMN)
                column.set_sort_column_id(enumerations.MARK_COLUMN)
                column.set_sort_indicator(True)
                column.set_cell_data_func(toggle_renderer, self.cell_data_function, None)
                column.connect_after('clicked',
                    self.__application_treeview_column_sorted, None)
                self.w_application_treeview.append_column(column)
                name_renderer = gtk.CellRendererText()
                column = gtk.TreeViewColumn(_("Name"), name_renderer,
                    text = enumerations.NAME_COLUMN)
                column.set_resizable(True)
                column.set_sort_column_id(enumerations.NAME_COLUMN)
                column.set_sort_indicator(True)
                column.set_min_width(200)
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
                description_renderer = gtk.CellRendererText()
                if self.is_remote_search:
                        column = gtk.TreeViewColumn(_('Repository'),
                            description_renderer,
                            text = enumerations.AUTHORITY_COLUMN)
                        column.set_sort_column_id(enumerations.AUTHORITY_COLUMN)
                else:
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
            application_list_sort = None):
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
                            application_list_filter, application_list_sort)

                if self.first_run:
                        # When vadj changes we need to set image descriptions
                        # on visible status icons. This catches moving the scroll bars
                        # and scrolling up and down using keyboard.
                        vadj = self.w_application_treeview.get_vadjustment()
                        vadj.connect('value-changed',
                            self.__application_treeview_vadjustment_changed, None)
                        vadj = self.w_categories_treeview.get_vadjustment()
                        vadj.connect('value-changed',
                            self.__categories_treeview_vadjustment_changed, None)

                        # When the size of the application_treeview changes
                        # we need to set image descriptions on visible status icons.
                        self.w_application_treeview.connect('size-allocate',
                            self.__application_treeview_size_allocate, None)
                        self.w_categories_treeview.connect('size-allocate',
                            self.__categories_treeview_size_allocate, None)

                if category_list != None:
                        ##CATEGORIES TREEVIEW
                        #enumerations.CATEGORY_NAME
                        category_list_filter = category_list.filter_new()
                        column =  self.__create_icon_column("", False,
                            enumerations.CATEGORY_ICON, False)
                        self.w_categories_treeview.append_column(column)
                        enumerations.CATEGORY_NAME_renderer = gtk.CellRendererText()
                        column = gtk.TreeViewColumn(_('Name'),
                            enumerations.CATEGORY_NAME_renderer,
                            text = enumerations.CATEGORY_NAME)
                        self.w_categories_treeview.append_column(column)
                        #Added selection listener
                        category_selection = self.w_categories_treeview.get_selection()
                        category_selection.set_mode(gtk.SELECTION_SINGLE)

                if self.first_run:
                        ##SECTION COMBOBOX
                        #enumerations.SECTION_NAME
                        cell = gtk.CellRendererText()
                        self.w_sections_combobox.pack_start(cell, True)
                        self.w_sections_combobox.add_attribute(cell, 'text',
                            enumerations.SECTION_NAME)
                        self.w_sections_combobox.set_row_separator_func(
                            self.combobox_id_separator)
                        self.w_sections_combobox.add_attribute( cell,
                            'sensitive', enumerations.SECTION_ENABLED )
                        ##FILTER COMBOBOX
                        #enumerations.FILTER_NAME
                        cell = gtk.CellRendererText()
                        self.w_filter_combobox.pack_start(cell, True)
                        self.w_filter_combobox.add_attribute(cell, 'text',
                            enumerations.FILTER_NAME)
                        self.w_filter_combobox.set_row_separator_func(
                            self.combobox_id_separator)

                self.section_list = section_list
                if category_list != None:
                        self.category_list = category_list
                        self.category_list_filter = category_list_filter
                        self.w_categories_treeview.set_model(category_list_filter)
                        if not self.is_remote_search:
                                category_list_filter.set_visible_func(
                                    self.category_filter)
                                self.__set_categories_visibility(self.set_section)
                        self.a11y_categories_treeview = \
                            self.w_categories_treeview.get_accessible()
                if application_list != None:
                        if category_list != None:
                                self.w_sections_combobox.set_model(section_list)
                                self.w_sections_combobox.set_active(self.set_section)
                                self.w_filter_combobox.set_model(self.filter_list)
                                self.w_filter_combobox.set_active(self.set_show_filter)
                        self.w_application_treeview.set_model(
                                self.application_list_sort)
                        if not self.is_remote_search:
                                if application_list_filter == None:
                                        self.application_list_filter.set_visible_func(
                                            self.__application_filter)

                category_selection = self.w_categories_treeview.get_selection()
                category_model, category_iter = category_selection.get_selected()
                self.pylintstub = category_model
                if not category_iter and not self.is_remote_search:
                #no category was selected, so select "All"
                        category_selection.select_path(0)
                        category_model, category_iter = category_selection.get_selected()
                if self.first_run:
                        category_selection.connect("changed",
                            self.__on_category_selection_changed, None)
                        self.w_categories_treeview.connect("row-activated",
                            self.__on_category_row_activated, None)
                        self.w_categories_treeview.connect("focus-in-event",
                            self.__on_category_focus_in, None)
                        self.package_selection.set_mode(gtk.SELECTION_SINGLE)
                        self.package_selection.connect("changed",
                            self.__on_package_selection_changed, None)

                self.a11y_application_treeview = \
                    self.w_application_treeview.get_accessible()
                self.process_package_list_end()

        def __categories_treeview_size_allocate(self, widget, allocation, user_data):
                # We ignore any changes in the size during initialization.
                if self.categories_treeview_initialized:
                        if self.categories_status_id == 0:
                                self.categories_status_id = gobject.idle_add(
                                    self.__set_accessible_categories_visible_status)

        def __categories_treeview_vadjustment_changed(self, widget, user_data):
                self.__set_accessible_categories_visible_status()

        def __set_accessible_categories_status(self, model, itr):
                status = model.get_value(itr, enumerations.CATEGORY_ICON)
                if status != None:
                        desc = _("Updates Available")
                else:
                        desc = None
                if desc != None:
                        obj = self.a11y_categories_treeview.ref_at(
                            int(model.get_string_from_iter(itr)),
                            CATEGORIES_STATUS_COLUMN_INDEX)
                        obj.set_image_description(desc)

        def __set_accessible_categories_visible_status(self):
                self.categories_status_id = 0
                if self.a11y_categories_treeview.get_n_accessible_children() == 0:
                        # accessibility is not enabled
                        return

                visible_range = self.w_categories_treeview.get_visible_range()
                if visible_range == None:
                        return
                start = visible_range[0][0]
                end = visible_range[1][0]
                # We try to minimize the range of accessible objects
                # on which we set image descriptions
                if self.categories_treeview_range != None:
                        old_start = self.categories_treeview_range[0][0]
                        old_end = self.categories_treeview_range[1][0]
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
                self.categories_treeview_range = visible_range
                model = self.category_list_filter
                itr = model.get_iter_from_string(str(start))
                while start <= end:
                        start += 1
                        self.__set_accessible_categories_status(model, itr)
                        itr = model.iter_next(itr)

        def __application_treeview_column_sorted(self, widget, user_data):
                self.__set_accessible_visible_status(False)

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
                            self.__set_accessible_visible_status)

        def __application_treeview_vadjustment_changed(self, widget, user_data):
                self.__set_accessible_visible_status()

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

        def __set_accessible_visible_status(self, check_range = True):
                self.visible_status_id = 0
                if self.a11y_application_treeview.get_n_accessible_children() == 0:
                        # accessibility is not enabled
                        return

                visible_range = self.w_application_treeview.get_visible_range()
                if visible_range == None:
                        return
                start = visible_range[0][0]
                end = visible_range[1][0]
                # We try to minimize the range of accessible objects
                # on which we set image descriptions
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
                self.application_treeview_range = visible_range
                model = self.w_application_treeview.get_model()
                itr = model.get_iter_from_string(str(start))
                while start <= end:
                        start += 1
                        self.__set_accessible_status(model, itr)
                        itr = model.iter_next(itr)

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
                self.w_sections_combobox.set_model(None)
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
                '''This function is for initializing sections combo box, also adds "All"
                Category. It sets active section combobox entry "All"'''
                cat_path = None
                enabled = True
                # We enable only first section and later we might enable the rest,
                # depending if there are some packages connected with them
                section_list.append([0, _('All Categories'), cat_path, enabled ])
                section_list.append([-1, "", cat_path, enabled ])
                enabled = False
                section_list.append([2, _('Meta Packages'), cat_path, enabled ])
                section_list.append([3, _('Applications'), cat_path, enabled ])
                section_list.append([4, _('Desktop (GNOME)'), cat_path, enabled ])
                section_list.append([5, _('Development'), cat_path, enabled ])
                section_list.append([6, _('Distributions'), cat_path, enabled ])
                section_list.append([7, _('Drivers'), cat_path, enabled ])
                section_list.append([8, _('System'), cat_path, enabled ])
                section_list.append([9, _('Web Services'), cat_path, enabled ])

        def __init_show_filter(self):
                self.filter_list.append([enumerations.FILTER_ALL, _('All Packages'), ])
                self.filter_list.append([enumerations.FILTER_INSTALLED,
                    _('Installed Packages'), ])
                self.filter_list.append([enumerations.FILTER_UPDATES,
                    _('Updates'), ])
                self.filter_list.append([enumerations.FILTER_NOT_INSTALLED,
                    _('Non-installed Packages'), ])
                self.filter_list.append([-1, "", ])
                self.filter_list.append([enumerations.FILTER_SELECTED,
                    _('Selected Packages'), ])
                if self.initial_show_filter >= enumerations.FILTER_ALL and \
                    self.initial_show_filter < len(self.filter_list):
                        row = self.filter_list[self.initial_show_filter]
                        if row[enumerations.SECTION_ID] != self.initial_show_filter:
                                self.initial_show_filter = enumerations.FILTER_ALL
                else:
                        self.initial_show_filter = enumerations.FILTER_ALL


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

        def __on_remote_search_error_delete_event(self, widget, event):
                self.__on_remote_search_button_clicked(None)

        def __on_remote_search_button_clicked(self, widget):
                self.remote_search_error_dialog.hide()

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
                '''On text search field changed we should refilter the main view'''
                if len(widget.get_text()) > 0:
                        self.w_clear_search_button.set_sensitive(True)
                else:
                        self.w_clear_search_button.set_sensitive(False)
                if self.typeahead_search and not self.is_remote_search:
                        self.__do_search()
                elif self.is_remote_search and not self.changing_search_option:
                        if self.w_searchentry_dialog.get_text() == "":
                                self.current_not_show_repos = []
                                self.w_infosearch_frame.hide()
                                self.__link_load_blank()
                                self.w_main_view_notebook.set_current_page(
                                    NOTEBOOK_START_PAGE)
                                self.update_statusbar_for_search()
                                self.w_searchentry_dialog.grab_focus()

        def __do_search(self):
                if self.changing_search_option:
                        return
                active = self.w_filter_combobox.get_active()
                if active != enumerations.FILTER_SELECTED:
                        self.saved_filter_combobox_active = active
                self.set_busy_cursor()
                if not self.is_remote_search:
                        self.__set_main_view_package_list()
                        self.__do_local_search()
                else:
                        text = self.w_searchentry_dialog.get_text()
                        if text == "":
                                self.unset_busy_cursor()
                                return
                        selection = self.w_categories_treeview.get_selection()
                        model, itr = selection.get_selected()
                        if itr:
                                cat_path = model.get_string_from_iter(itr)
                                selected_section = self.w_sections_combobox.get_active()
                                section_row = self.section_list[selected_section]
                                section_row[enumerations.SECTION_SUBCATEGORY] = cat_path
                                selection.unselect_all()
                        self.w_infosearch_frame.hide()
                        self.update_statusbar_for_searching()
                        self.in_search = True
                        Thread(target = self.__do_remote_search,
                            args = ()).start()

        def __process_after_search_failure(self):
                self.application_list = []
                self.update_statusbar()
                self.unset_busy_cursor()
                self.in_setup = False

        def __do_remote_search(self):
                text = self.w_searchentry_dialog.get_text()
                # Here we call the search API to get the results
                searches = []
                servers = []
                result = []
                pargs = []
                search_str = SEARCH_STR_FORMAT % text
                pargs.append(search_str)
                if debug:
                        print "pargs:", pargs
                        print "servers:", servers
                searches.append(self.api_o.remote_search(
                    [api.Query(" ".join(pargs), False, True, None, None)],
                    ))
                result_tuple = {}
                try:
                        for query_num, publisher, (v, return_type, tmp) in \
                            itertools.chain(*searches):
                                if v == 1 and \
                                    return_type == api.Query.RETURN_PACKAGES:
                                        repo = None
                                        if publisher is not None \
                                            and "prefix" in publisher:
                                                repo = publisher["prefix"]
                                        name = fmri.PkgFmri(str(tmp)).get_name()
                                        result_tuple[(name, repo)] = -1
                                        if len(result_tuple) == SEARCH_LIMIT:
                                                break
                                else:
                                        # We are not interested in this error
                                        gobject.idle_add(self.w_progress_dialog.hide)
                                        self.__process_after_search_failure()
                                        return
                                self.pylintstub = query_num
                except api_errors.ProblematicSearchServers, ex:
                        self.__parse_remote_search_error(ex)
                        gobject.idle_add(self.w_progress_dialog.hide)
                        gobject.idle_add(self.__handle_remote_search_error)
                        if len(result_tuple) == 0:
                                self.__process_after_search_with_zero_results()
                                return
                except Exception, ex:
                        # We are not interested in this error
                        gobject.idle_add(self.w_progress_dialog.hide)
                        self.__process_after_search_failure()
                        return
                if debug:
                        print "Number of search results:", len(result_tuple)
                for name, repo in result_tuple:
                        a_res = name, repo
                        result.insert(0, a_res)
                if len(result) == 0:
                        if debug:
                                print "No search results"
                        self.__process_after_search_with_zero_results()
                        return
                result.reverse()
                # We cannot get status of the packages if catalogs have not
                # been loaded so we pause for up to 5 seconds here to
                # allow catalogs to be loaded
                times = 5
                while self.catalog_loaded == False:
                        if times == 0:
                                break
                        time.sleep(1)
                        times -= 1
                self.in_setup = True
                application_list = self.__get_list_from_search(result)
                gobject.idle_add(self.__set_empty_details_panel)
                gobject.idle_add(self.__set_main_view_package_list)
                gobject.idle_add(self.__init_tree_views, application_list, None, None)

        def __process_after_search_with_zero_results(self):
                        self.in_setup = True
                        application_list = self.__get_new_application_liststore()
                        gobject.idle_add(self.__set_empty_details_panel)
                        gobject.idle_add(self.__set_main_view_package_list)
                        gobject.idle_add(self.__init_tree_views, application_list, None, None)

        def __get_list_from_search(self, search_result):
                application_list = self.__get_new_application_liststore()
                self.__add_pkgs_to_list_from_search(search_result,
                    application_list)
                return application_list

        def __add_pkgs_to_list_from_search(self, search_result,
            application_list):
                pargs = []
                default_pub = self.api_o.get_preferred_publisher().prefix
                for name, publisher in search_result:
                        if publisher == default_pub:
                                pargs.append("pkg:/" + name)
                        else:
                                pargs.append("pkg://" + publisher + "/" + name)
                # We now need to get the status for each package
                if debug:
                        print "pargs:", pargs
                try:
                        pkgs_known = self.__get_inventory_list(pargs,
                            True, True)
                except api_errors.InventoryException:
                        # This can happen if load_catalogs has not been run
                        err = _("Unable to get status for search results.\n"
                            "The catalogs have not been loaded.\n"
                            "Please try after few seconds.\n")
                        gobject.idle_add(self.w_progress_dialog.hide)
                        gobject.idle_add(self.error_occured, err)
                        return
                return self.__add_pkgs_to_lists(pkgs_known, application_list,
                    None, None)

        def __do_local_search(self):
                self.in_search = True
                self.w_filter_combobox.set_active(enumerations.FILTER_ALL)
                if self.application_refilter_id != 0:
                        gobject.source_remove(self.application_refilter_id)
                        self.application_refilter_id = 0
                if self.w_searchentry_dialog.get_text() == "" or \
                    not self.typeahead_search:
                        self.application_refilter_id = \
                            gobject.idle_add(self.__application_refilter)
                else:
                        self.application_refilter_id = \
                            gobject.timeout_add(TYPE_AHEAD_DELAY,
                            self.__application_refilter)

        def __application_refilter(self):
                ''' Disconnecting the model from the treeview improves
                performance when assistive technologies are enabled'''
                if self.in_setup:
                        return
                self.application_refilter_id = 0
                self.application_refilter_idle_id = 0
                if not self.is_remote_search:
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
                            self.__set_accessible_visible_status)
                self.categories_treeview_initialized = True
                self.categories_treeview_range = None
                if self.categories_status_id == 0:
                        self.categories_status_id = gobject.idle_add(
                            self.__set_accessible_categories_visible_status)
                return False

        def __on_edit_paste(self, widget):
                self.w_searchentry_dialog.paste_clipboard()

        def __on_clear_paste(self, widget):
                bounds = self.w_searchentry_dialog.get_selection_bounds()
                self.w_searchentry_dialog.delete_text(bounds[0], bounds[1])
                return

        def __on_copy(self, widget):
                self.w_searchentry_dialog.copy_clipboard()

        def __on_cut(self, widget):
                self.w_searchentry_dialog.cut_clipboard()

        def __popup_position_func(self, menu):
                ''' Position popup menu immediately below search button'''
                root = self.w_main_window.window.get_origin()
                alloc = self.search_button.get_allocation()
                return (root[0] + alloc.x, root[1] + alloc.y + alloc.height, False)

        def __on_set_search(self, widget, event):
                if  event.type == gtk.gdk.BUTTON_PRESS:
                        self.searchmenu.popup(None, None, self.__popup_position_func,
                            event.button, event.time)
                        return True
                return False

        def __on_set_search_clicked(self, widget):
                self.searchmenu.popup(None, None, self.__popup_position_func,
                    0, 0)
                return True

        def __on_edit_search_clicked(self, widget):
                self.w_searchentry_dialog.grab_focus()

        def __on_clear_search(self, widget):
                self.w_searchentry_dialog.delete_text(0, -1)
                self.__do_search()
                return

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
                            gobject.timeout_add(TYPE_AHEAD_DELAY,
                                self.__show_licenses)

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
                        already_marked = model.get_value(itr, enumerations.MARK_COLUMN)
                        if not already_marked:
                                model.set_value(itr, enumerations.MARK_COLUMN, True)
                                pkg_stem = model.get_value(itr,
                                    enumerations.STEM_COLUMN)
                                pkg_status = model.get_value(itr,
                                    enumerations.STATUS_COLUMN)
                                self.__add_pkg_stem_to_list(pkg_stem, pkg_status)
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_remove()

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
                        already_deselected = not model.get_value(itr,
                            enumerations.MARK_COLUMN)
                        if not already_deselected:
                                model.set_value(itr, enumerations.MARK_COLUMN, False)
                                self.__remove_pkg_stem_from_list(model.get_value(itr,
                                    enumerations.STEM_COLUMN))
                self.__enable_disable_selection_menus()
                self.update_statusbar()
                self.__enable_disable_install_remove()

        def __on_preferences(self, widget):
                self.w_startpage_checkbutton.set_active(self.show_startpage)
                self.w_typeaheadsearch_checkbutton.set_active(self.typeahead_search)
                self.w_preferencesdialog.show()

        def __on_preferencesclose_clicked(self, widget):
                self.w_preferencesdialog.hide()

        def __on_preferenceshelp_clicked(self, widget):
                gui_misc.display_help(self.application_dir, "pm_win")

        def __on_startpage_checkbutton_toggled(self, widget):
                self.show_startpage = self.w_startpage_checkbutton.get_active()
                try:
                        self.client.set_bool(SHOW_STARTPAGE_PREFERENCES,
                            self.show_startpage)
                except GError:
                        pass

        def __on_typeaheadsearch_checkbutton_toggled(self, widget):
                self.typeahead_search = self.w_typeaheadsearch_checkbutton.get_active()
                try:
                        self.client.set_bool(TYPEAHEAD_SEARCH_PREFERENCES,
                            self.typeahead_search)
                except GError:
                        pass

        def __on_remote_search_checkbox_toggled(self, widget):
                active = self.remote_search_checkbox.get_active()
                if len(self.current_not_show_repos) > 0:
                        if active:
                                for url in self.current_not_show_repos:
                                        if url not in self.gconf_not_show_repos:
                                                self.gconf_not_show_repos += url + ","
                        else:
                                for url in self.current_not_show_repos:
                                        self.gconf_not_show_repos = \
                                            self.gconf_not_show_repos.replace(
                                            url + ",", "")
                        try:
                                self.client.set_string(REMOTE_SEARCH_ERROR_PREFERENCES,
                                    self.gconf_not_show_repos)
                        except GError:
                                pass

        def __on_searchentry_focus_in(self, widget, event):
                self.w_paste_menuitem.set_sensitive(True)

        def __on_searchentry_focus_out(self, widget, event):
                self.w_paste_menuitem.set_sensitive(False)

        def __on_searchentry_key_press_event(self, widget, event):
                if self.typeahead_search and not self.is_remote_search:
                        return False
                from gtk.gdk import keyval_name
                if debug:
                        print "Pressed %s" % keyval_name(event.keyval)
                if event.keyval == gtk.keysyms.Return:
                        self.__do_search()
                        return True
                return False

        def __on_searchentry_event(self, widget, event):
                if widget.get_selection_bounds():
                        #enable selection functions
                        self.w_cut_menuitem.set_sensitive(True)
                        self.w_copy_menuitem.set_sensitive(True)
                        self.w_clear_menuitem.set_sensitive(True)
                else:
                        self.w_cut_menuitem.set_sensitive(False)
                        self.w_copy_menuitem.set_sensitive(False)
                        self.w_clear_menuitem.set_sensitive(False)

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
                self.w_filter_combobox.set_active(self.saved_filter_combobox_active)
                self.w_searchentry_dialog.delete_text(0, -1)
                if self.is_remote_search:
                        self.__unset_remote_search(True)
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

        def __on_category_selection_changed(self, selection, widget):
                '''This function is for handling category selection changes'''
                if self.in_setup:
                        return
                if self.changing_search_option or self.is_remote_search:
                        return
                self.w_filter_combobox.set_active(self.saved_filter_combobox_active, )
                self.w_searchentry_dialog.delete_text(0, -1)
                self.__set_main_view_package_list()
                model, itr = selection.get_selected()
                if self.is_remote_search:
                        return
                if itr:
                        cat_path = model.get_string_from_iter(itr)
                        selected_section = self.w_sections_combobox.get_active()
                        section_row = self.section_list[selected_section]
                        section_row[enumerations.SECTION_SUBCATEGORY] = cat_path

                self.set_busy_cursor()
                self.__refilter_on_idle()
                if self.selected == 0:
                        gobject.idle_add(self.__enable_disable_install_remove)

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
                            gobject.timeout_add(TYPE_AHEAD_DELAY,
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
                if self.in_setup or self.in_search or self.changing_search_option:
                        return
                active = self.w_filter_combobox.get_active()
                if active != enumerations.FILTER_SELECTED:
                        self.saved_filter_combobox_active = active
                self.w_searchentry_dialog.delete_text(0, -1)
                self.__set_main_view_package_list()
                if self.is_remote_search:
                        self.set_busy_cursor()
                        self.saved_filter_combobox_active = \
                            self.w_filter_combobox.get_active()
                        self.__unset_remote_search(True)
                        return
                self.set_busy_cursor()
                self.__refilter_on_idle()
                if self.selected == 0:
                        gobject.idle_add(self.__enable_disable_install_remove)

        def __set_categories_visibility(self, selected_section):
                self.category_list[0][enumerations.CATEGORY_ICON] = None
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

                # Set category icon for All if a visible category has it
                for category in self.category_list:
                        if category[enumerations.CATEGORY_ICON] != None:
                                self.category_list[0][enumerations.CATEGORY_ICON] = \
                                    category[enumerations.CATEGORY_ICON]
                                break

                section_row = self.section_list[selected_section]
                cat_path = section_row[enumerations.SECTION_SUBCATEGORY]
                if cat_path != None:
                        itr = self.category_list_filter.get_iter_from_string(cat_path)
                        path = self.category_list_filter.get_path(itr)
                        self.w_categories_treeview.set_cursor(path,
                            None, start_editing=False)

        def __on_sectionscombobox_changed(self, widget):
                '''On section combobox changed'''
                if self.in_setup:
                        return
                if self.changing_search_option:
                        return
                self.__set_main_view_package_list()
                self.set_busy_cursor()
                if self.is_remote_search:
                        self.saved_sections_combobox_active = \
                            self.w_sections_combobox.get_active()
                        self.__unset_remote_search(True)
                        return
                self.__set_first_category_text()
                self.__set_categories_visibility(widget.get_active())
                self.category_list_filter.refilter()
                self.__refilter_on_idle()
                if self.selected == 0:
                        gobject.idle_add(self.__enable_disable_install_remove)

        def __set_first_category_text(self):
                active_section = self.w_sections_combobox.get_active()
                all_cat_text = _("All")
                if active_section != 0:
                        all_cat_text += " " + self.section_list[active_section][1]
                category_model = self.w_categories_treeview.get_model()
                if category_model:
                        list_store = category_model.get_model()
                        list_store[0][1] = all_cat_text

        def __unset_remote_search(self, same_repo):
                self.current_not_show_repos = []
                self.w_infosearch_frame.hide()
                self.changing_search_option = True
                self.current_search_option = 0
                visible_repository = self.__get_visible_repository_name()
                if visible_repository in self.selected_pkgs:
                        self.selected_pkgs.pop(visible_repository)
                if visible_repository in self.to_install_update:
                        self.to_install_update.pop(visible_repository)
                if visible_repository in self.to_remove:
                        self.to_remove.pop(visible_repository)
                self.__update_tooltips()
                self.__update_repository_combobox_for_search(False)
                pixbuf = self.search_options[0][1]
                self.search_image.set_from_pixbuf(pixbuf)
                if same_repo:
                        self.__update_gui_for_search(False)
                else:
                        self.__on_clear_search(None)
                        self.is_remote_search = False
                        self.need_descriptions = True
                self.changing_search_option = False

        def __on_repositorycombobox_changed(self, widget):
                '''On repository combobox changed'''
                if self.changing_search_option:
                        return
                self.changing_search_option = True
                self.__on_clear_search(None)
                active_publisher = self.__get_active_publisher()
                if self.is_remote_search:
                        same_repo = False
                        active =  self.w_repository_combobox.get_active() - 1
                        if active == -1:
                                # We get here is we choose "Add ..." when
                                # doing remote search
                                self.changing_search_option = False
                                return
                        if not active_publisher == _("Add..."):
                                if self.saved_repository_combobox_active == active:
                                        same_repo = True
                                self.__unset_remote_search(same_repo)
                                self.w_repository_combobox.set_active(active)

                        if same_repo:
                                self.changing_search_option = False
                                return
                        active_publisher = self.__get_active_publisher()
                self.changing_search_option = False
                if self.visible_repository == active_publisher:
                # If we are coming back to the same repository, we do
                # not want to setup publishers. This is the case when
                # we are calling Add... then we are firing the event for
                # Add... case and immediately coming back to the
                # previously selected repository.
                        return
                # Checking for Add... is fine enough, as the repository
                # name cannot contain "..." in the name.
                if active_publisher == _("Add..."):
                        index = -1
                        if self.is_remote_search:
                                index = 0
                        else:
                                model = self.w_repository_combobox.get_model()
                                for entry in model:
                                        if entry[1] == self.visible_repository:
                                                index = entry[0]
                                                break
                        # We do not want to switch permanently to the Add...
                        self.w_repository_combobox.set_active(index)
                        self.__on_edit_repositories_activate(None)
                        return
                self.cancelled = True
                self.in_setup = True
                self.w_searchentry_dialog.delete_text(0, -1)
                self.set_busy_cursor()
                self.__set_empty_details_panel()
                pub = [active_publisher, ]
                self.set_show_filter = self.initial_show_filter
                self.set_section = self.initial_section
                Thread(target = self.__setup_publisher, args = [pub]).start()
                self.__set_main_view_package_list()

        def __get_active_publisher(self):
                pub_iter = self.w_repository_combobox.get_active_iter()
                return self.repositories_list.get_value(pub_iter, \
                            enumerations.REPOSITORY_NAME)

        def __setup_publisher(self, publishers=[]):
                self.saved_filter_combobox_active = self.initial_show_filter
                application_list, category_list , section_list = \
                    self.__get_application_categories_lists(publishers)
                gobject.idle_add(self.__init_tree_views, application_list,
                    category_list, section_list)

        def __get_application_categories_lists(self, publishers=[]):
                if not self.visible_repository:
                        self.visible_repository = self.__get_active_publisher()
                application_list = self.__get_new_application_liststore()
                category_list = self.__get_new_category_liststore()
                section_list = self.__get_new_section_liststore()
                first_loop = True
                for publisher in publishers:
                        uptodate = False
                        try:
                                uptodate = self.__check_if_cache_uptodate(publisher)
                                if uptodate:
                                        self.__add_pkgs_to_lists_from_cache(publisher,
                                            application_list, category_list,
                                            section_list)
                        except (UnpicklingError, EOFError, IOError):
                                #Most likely cache is corrupted, silently load list
                                #from api.
                                application_list = self.__get_new_application_liststore()
                                category_list = self.__get_new_category_liststore()
                                uptodate = False
                        if not uptodate:
                                if first_loop == True:
                                        first_loop = False
                                        gobject.idle_add(self.setup_progressdialog_show)
                                self.__load_catalogs()
                                self.__add_pkgs_to_lists_from_api(publisher,
                                    application_list, category_list, section_list)
                                category_list.prepend([0, _('All'), None, None, False,
                                    True, None])
                        if self.application_list and self.category_list and \
                            not self.visible_repository_uptodate:
                                if self.visible_repository:
                                        self.__dump_datamodels(self.visible_repository,
                                            self.application_list, self.category_list,
                                            self.section_list)
                        self.visible_repository = self.__get_active_publisher()
                        self.visible_repository_uptodate = uptodate
                return application_list, category_list, section_list

        def __check_if_cache_uptodate(self, publisher):
                if self.cache_o:
                        return self.cache_o.check_if_cache_uptodate(publisher)
                return False

        def __dump_datamodels(self, publisher, application_list, category_list,
            section_list):
                if self.cache_o:
                        if self.img_timestamp == \
                            self.cache_o.get_index_timestamp():
                                Thread(target = self.cache_o.dump_datamodels,
                                    args = (publisher, application_list, category_list,
                                    section_list)).start()
                        else:
                                self.__remove_cache()

        def __remove_cache(self):
                model = self.w_repository_combobox.get_model()
                for publisher in model:
                        pub_name = publisher[1]
                        if pub_name and pub_name != _("Add..."):
                                Thread(target = self.cache_o.remove_datamodel,
                                    args = [publisher[1]]).start()

        def __on_install_update(self, widget):
                self.api_o.reset()
                install_update = []
                if self.selected == 0:
                        model, itr = self.package_selection.get_selected()
                        if itr:
                                install_update.append(
                                    model.get_value(itr, enumerations.STEM_COLUMN))
                else:
                        visible_repository = self.__get_visible_repository_name()
                        pkgs = self.selected_pkgs.get(visible_repository)
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
                    self.api_o, ips_update = False, \
                    action = enumerations.INSTALL_UPDATE)

        def __on_update_all(self, widget):
                self.api_o.reset()
                installupdate.InstallUpdate([], self,
                    self.api_o, ips_update = False,
                    action = enumerations.IMAGE_UPDATE, be_name = self.ua_be_name,
                    parent_name = _("Package Manager"),
                    pkg_list = ["SUNWipkg", "SUNWipkg-gui"],
                    main_window = self.w_main_window)
                return

        def __on_ua_completed_linkbutton_clicked(self, widget):
                try:
                        gnome.url_show(self.release_notes_url)
                except gobject.GError:
                        self.error_occured(_("Unable to navigate to:\n\t%s") % 
                            self.release_notes_url, msg_title=_("Package Manager"))

        def __on_help_about(self, widget):
                wTreePlan = gtk.glade.XML(self.gladefile, "aboutdialog")
                aboutdialog = wTreePlan.get_widget("aboutdialog")
                aboutdialog.connect("response", lambda x = None, \
                    y = None: aboutdialog.destroy())
                aboutdialog.run()

        def __on_help_help(self, widget):
                gui_misc.display_help(self.application_dir)

        def __on_remove(self, widget):
                self.api_o.reset()
                remove_list = []
                if self.selected == 0:
                        model, itr = self.package_selection.get_selected()
                        if itr:
                                remove_list.append(
                                    model.get_value(itr, enumerations.STEM_COLUMN))
                else:
                        visible_repository = self.__get_visible_repository_name()
                        pkgs = self.selected_pkgs.get(visible_repository)
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
                    self.api_o, ips_update = False,
                    action = enumerations.REMOVE)

        def __on_reload(self, widget):
                if self.description_thread_running:
                        self.cancelled = True
                if self.is_remote_search:
                        self.__unset_remote_search(False)
                self.__set_empty_details_panel()
                self.in_setup = True
                self.visible_repository = None
                if widget != None:
                        self.__remove_cache()
                self.w_progress_dialog.set_title(_("Refreshing catalogs"))
                self.w_progressinfo_label.set_text(_("Refreshing catalogs..."))
                self.progress_stop_timer_thread = False
                Thread(target = self.__progressdialog_progress_pulse).start()
                self.w_progress_dialog.show()
                self.w_progress_cancel.hide()
                self.__disconnect_models()
                self.in_reload = True
                Thread(target = self.__catalog_refresh).start()

        def __catalog_refresh_done(self):
                self.progress_stop_timer_thread = True
                #Let the progress_pulse finish. This should be done other way, but at
                #The moment this works fine
                time.sleep(0.2)
                gobject.idle_add(self.w_progress_cancel.show)
                gobject.idle_add(self.process_package_list_start,
                    self.image_directory)

        def __main_application_quit(self, be_name = None):
                '''quits the main gtk loop'''
                self.cancelled = True
                if self.in_setup:
                        return

                if be_name:
                        if self.image_dir_arg:
                                gobject.spawn_async([self.application_path, "-R",
                                    self.image_dir_arg, "-U", be_name])
                        else:
                                gobject.spawn_async([self.application_path,
                                    "-U", be_name])
                elif not self.is_remote_search:
                        visible_repository = self.__get_visible_repository_name()
                        self.__dump_datamodels(visible_repository,
                                self.application_list, self.category_list,
                                self.section_list)

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
                while gtk.events_pending():
                        gtk.main_iteration(False)
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
                repositories_list.append([-1, "", ])
                repositories_list.append([-1, _("Add..."), ])
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
                        self.w_reload_button.set_sensitive(True)
                else:
                        self.w_reload_button.set_sensitive(False)

        def __add_pkg_stem_to_list(self, stem, status):
                publisher = self.__get_active_publisher()
                if self.selected_pkgs.get(publisher) == None:
                        self.selected_pkgs[publisher] = {}
                self.selected_pkgs.get(publisher)[stem] = status
                if status == enumerations.NOT_INSTALLED or \
                    status == enumerations.UPDATABLE:
                        if self.to_install_update.get(publisher) == None:
                                self.to_install_update[publisher] = 1
                        else:
                                self.to_install_update[publisher] += 1
                if status == enumerations.UPDATABLE or status == enumerations.INSTALLED:
                        if self.to_remove.get(publisher) == None:
                                self.to_remove[publisher] = 1
                        else:
                                self.to_remove[publisher] += 1
                self.__update_tooltips()

        def __update_tooltips(self):
                to_remove = None
                to_install = None
                no_iter = 0
                for publisher in self.to_remove:
                        packages = self.to_remove.get(publisher)
                        if packages > 0:
                                if no_iter == 0:
                                        to_remove = _("Selected for Removal:")
                                to_remove += "\n   %s: %d" % (publisher, packages)
                                no_iter += 1
                no_iter = 0
                for publisher in self.to_install_update:
                        packages = self.to_install_update.get(publisher)
                        if packages > 0:
                                if no_iter == 0:
                                        to_install = _("Selected for Install/Update:")
                                to_install += "\n   %s: %d" % (publisher, packages)
                                no_iter += 1
                if not to_install:
                        to_install = _("Select packages by marking checkbox\n"+
                            "and click to Install/Update.")
                self.w_installupdate_button.set_tooltip(self.install_button_tooltip,
                    to_install)
                if not to_remove:
                        to_remove = _("Select packages by marking checkbox\n"+
                            "and click to Remove selected.")
                self.w_remove_button.set_tooltip(self.remove_button_tooltip, to_remove)

        def __remove_pkg_stem_from_list(self, stem):
                remove_pub = []
                for publisher in self.selected_pkgs:
                        pkgs = self.selected_pkgs.get(publisher)
                        status = None
                        if stem in pkgs:
                                status = pkgs.pop(stem)
                        if status == enumerations.NOT_INSTALLED or \
                            status == enumerations.UPDATABLE:
                                if self.to_install_update.get(publisher) == None:
                                        self.to_install_update[publisher] = 0
                                else:
                                        self.to_install_update[publisher] -= 1
                        if status == enumerations.UPDATABLE or \
                            status == enumerations.INSTALLED:
                                if self.to_remove.get(publisher) == None:
                                        self.to_remove[publisher] = 0
                                else:
                                        self.to_remove[publisher] -= 1
                        if len(pkgs) == 0:
                                remove_pub.append(publisher)
                for publisher in remove_pub:
                        self.selected_pkgs.pop(publisher)
                self.__update_tooltips()

        def __clear_pkg_selections(self):
                # We clear the selections as the preffered repository was changed
                # and pkg stems are not valid.
                remove_pub = []
                for publisher in self.selected_pkgs:
                        stems = self.selected_pkgs.get(publisher)
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
                pkg_name = _("Package Name")
                self.w_packagename_label.set_markup("<b>" + pkg_name + "</b>")
                self.w_general_info_label.set_markup("<b>" + pkg_name + "</b>")
                self.w_installedfiles_textview.get_buffer().set_text("")
                self.w_dependencies_textview.get_buffer().set_text("")
                self.w_generalinfo_textview.get_buffer().set_text("")
                self.w_license_textview.get_buffer().set_text("")
                return

        def __show_fetching_package_info(self, pkg):
                pkg_name = pkg.get_name()
                self.w_packagename_label.set_markup("<b>" + pkg_name + "</b>")
                self.w_general_info_label.set_markup("<b>" + pkg_name + "</b>")

                pkg_stem = pkg.get_pkg_stem()
                if self.__setting_from_cache(pkg_stem):
                        return

                self.w_shortdescription_label.set_text(
                    _("Fetching description..."))
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
                        self.w_shortdescription_label.set_text(
                            self.info_cache[pkg_stem][0])
                        instbuffer = self.w_installedfiles_textview.get_buffer()
                        depbuffer = self.w_dependencies_textview.get_buffer()
                        infobuffer = self.w_generalinfo_textview.get_buffer()
                        infobuffer.set_text(self.info_cache[pkg_stem][1])
                        instbuffer.set_text(self.info_cache[pkg_stem][2])
                        depbuffer.set_text(self.info_cache[pkg_stem][3])
                        return True
                else:
                        return False

        def __update_package_info(self, pkg, local_info, remote_info, info_id):
                if self.showing_empty_details or (info_id != 
                    self.last_show_info_id):
                        return
                pkg_name = pkg.get_name()
                pkg_stem = pkg.get_pkg_stem()
                self.w_packagename_label.set_markup("<b>" + pkg_name + "</b>")
                self.w_general_info_label.set_markup("<b>" + pkg_name + "</b>")
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
                        self.w_shortdescription_label.set_text(
                            _("Description not available for this package...") +
                            network_str)
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
                self.w_shortdescription_label.set_text(description)
                inst_str = _("Root: %s\n") % self.api_o.img.get_root()
                dep_str = _("Dependencies:\n")

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
                info_str = ""
                labs = {}
                labs["sum"] = _("Summary:\t\t")
                labs["size"] = _("Size:\t\t\t")
                labs["cat"] = _("Category:\t\t")
                labs["ins"] = _("Installed Version:\t")
                labs["lat"] = _("Latest Version:\t")
                labs["pkg_date"] = _("Packaging Date:\t")
                labs["fmri"] = _("FMRI:\t\t\t")
                labs["repository"] = _("Repository:\t\t")
                max_len = 0
                for lab in labs:
                        if len(labs[lab]) > max_len:
                                max_len = len(labs[lab])
                categories = _("None")
                if local_info.category_info_list:
                        verbose = len(local_info.category_info_list) > 1
                        categories = ""
                        categories += local_info.category_info_list[0].__str__(verbose)
                        if len(local_info.category_info_list) > 1:
                                for ci in local_info.category_info_list[1:]:
                                        categories += ", " + ci.__str__(verbose)
                summary = _("None")
                if local_info.summary:
                        summary = local_info.summary
                info_str += "  %s %s" % (labs["sum"], summary)
                info_str += "\n  %s %s" % (labs["size"],
                    misc.bytes_to_str(local_info.size))
                info_str += "\n  %s %s" % (labs["cat"], categories)
                if installed:
                        info_str += "\n  %s %s,%s-%s" % (labs["ins"], local_info.version,
                            local_info.build_release, local_info.branch)
                info_str += "\n  %s %s,%s-%s" % (labs["lat"], remote_info.version,
                    remote_info.build_release, remote_info.branch)
                info_str += "\n  %s %s" % (labs["pkg_date"], local_info.packaging_date)
                info_str += "\n  %s %s" % (labs["fmri"], local_info.fmri)
                info_str += "\n  %s %s" % (labs["repository"], local_info.publisher)
                infobuffer.set_text(info_str)
                instbuffer.set_text(inst_str)
                depbuffer.set_text(dep_str)
                self.info_cache[pkg_stem] = \
                    (description, info_str, inst_str, dep_str)

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
                                lic_u += ""
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
                except (misc.TransportFailures, retrieve.ManifestRetrievalError,
                    retrieve.DatastreamRetrievalError):
                        pass
                if self.showing_empty_details or (license_id != 
                    self.last_show_licenses_id):
                        return
                if not info or (info and len(info.get(0)) == 0):
                        try:
                        # Get license from remote
                                info = self.api_o.info([selected_pkgstem],
                                    False, frozenset([api.PackageInfo.LICENSES]))
                        except (misc.TransportFailures, retrieve.ManifestRetrievalError,
                            retrieve.DatastreamRetrievalError):
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
                except (misc.TransportFailures, retrieve.ManifestRetrievalError,
                    retrieve.DatastreamRetrievalError):
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

        def __application_filter(self, model, itr):
                '''This function is used to filter content in the main
                application view'''
                if self.in_setup or self.cancelled:
                        return False
                search_text = self.w_searchentry_dialog.get_text()
                if not search_text == "":
                        if not model.get_value(itr, enumerations.NAME_COLUMN) == None:
                                if search_text.lower() in model.get_value(itr,
                                    enumerations.NAME_COLUMN).lower():
                                        return True
                        if not model.get_value(itr, enumerations.DESCRIPTION_COLUMN) == \
                            None:
                                if search_text.lower() in model.get_value(itr,
                                    enumerations.DESCRIPTION_COLUMN).lower():
                                        return True
                        return False
                filter_id = self.w_filter_combobox.get_active()
                if filter_id == enumerations.FILTER_SELECTED:
                        return model.get_value(itr, enumerations.MARK_COLUMN)
                # XXX Show filter, chenge text to integers
                selected_category = 0
                category_selection = self.w_categories_treeview.get_selection()
                category_model, category_iter = category_selection.get_selected()
                if category_iter:
                        selected_category = category_model.get_value(category_iter,
                            enumerations.CATEGORY_ID)
                category_list = model.get_value(itr, enumerations.CATEGORY_LIST_COLUMN)
                selected_section = self.w_sections_combobox.get_active()
                category = False
                if selected_section == 0 and selected_category == 0:
                        #For section "All" and category "All" always true
                        category = True
                elif selected_category != 0:
                        if category_list and selected_category in category_list:
                                category = True
                elif category_list:
                        #The selected category is "All" so we need to check
                        #If the package belongs to one of the visible categories
                        for visible_category in category_model:
                                visible_id = visible_category[enumerations.CATEGORY_ID]
                                if visible_id in category_list:
                                        category = True
                                        break
                if (model.get_value(itr, enumerations.IS_VISIBLE_COLUMN) == False):
                        return False
                if search_text == "":
                        return (category &
                            self.__is_package_filtered(model, itr, filter_id))
                else:
                        return False

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
                        visible_repository = self.__get_visible_repository_name()
                        pkg = model.get_value(itr, enumerations.FMRI_COLUMN)
                        if not pkg:
                                return False
                        if cmp(pkg.get_publisher(), visible_repository) == 0:
                                return True
                        else:
                                return False

        def __get_visible_repository_name(self):
                pub_iter = self.w_repository_combobox.get_active_iter()
                visible = self.repositories_list.get_value(pub_iter, \
                    enumerations.REPOSITORY_NAME)
                return visible

        def __enable_disable_selection_menus(self):
                if self.in_setup:
                        return
                self.__enable_disable_select_all()
                self.__enable_disable_select_updates()
                self.__enable_disable_deselect()
                self.unset_busy_cursor()

        def __enable_disable_select_all(self):
                if self.in_setup:
                        return
                was_in_search = self.in_search
                self.in_search = False
                if len(self.w_application_treeview.get_model()) > 0:
                        for row in self.w_application_treeview.get_model():
                                if not row[enumerations.MARK_COLUMN]:
                                        self.w_selectall_menuitem.set_sensitive(True)
                                        if was_in_search:
                                                self.w_application_treeview.grab_focus()
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
                visible_repository = self.__get_visible_repository_name()
                selected = self.to_remove.get(visible_repository)
                if selected > 0:
                        sensitive = True
                self.w_remove_button.set_sensitive(sensitive)
                self.w_remove_menuitem.set_sensitive(sensitive)
                return sensitive

        def __enable_if_selected_for_install_update(self):
                sensitive = False
                visible_repository = self.__get_visible_repository_name()
                selected = self.to_install_update.get(visible_repository)
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

        def __load_catalogs(self):
                self.__image_activity_lock.acquire()
                try:
                        self.catalog_loaded = False
                        self.api_o.img.load_catalogs(self.pr)
                        self.catalog_loaded = True
                finally:
                        self.__image_activity_lock.release()

        def __enable_disable_update_all(self):
                #XXX Api to provide fast information if there are some updates
                #available within image
                gobject.idle_add(self.w_updateall_button.set_sensitive, False)
                gobject.idle_add(self.w_updateall_menuitem.set_sensitive, False)
                update_available = self.__check_if_updates_available()
                gobject.idle_add(self.__g_enable_disable_update_all, update_available)
                gobject.idle_add(self.__show_info_after_catalog_load)
                return False

        def __show_info_after_catalog_load(self):
                self.__show_info(self.selected_model, self.selected_path)
                self.selected_model = None
                self.selected_path = None
                if (self.w_info_notebook.get_current_page() == 
                    INFO_NOTEBOOK_LICENSE_PAGE and
                    not self.showing_empty_details):
                        self.__show_licenses()

        def __check_if_updates_available(self):
                try:
                        self.__load_catalogs()
                        res = self.__get_inventory_list([], False, False)
                        for pfmri, state in res:
                                if state["upgradable"]:
                                        self.pylintstub = pfmri
                                        return True

                except api_errors.InventoryException:
                        gobject.idle_add(self.__set_empty_details_panel)
                        return False
                return False

        def __g_enable_disable_update_all(self, update_available):
                self.w_updateall_button.set_sensitive(update_available)
                self.w_updateall_menuitem.set_sensitive(update_available)
                self.__enable_disable_install_remove()

        def __enable_disable_deselect(self):
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
                        # Refresh will load the catalogs.
                        self.catalog_loaded = True
                except api_errors.PublisherError:
                        # In current implementation, this will never happen
                        # We are not refrehsing specific publisher
                        self.__catalog_refresh_done()
                        raise
                except api_errors.PermissionsException:
                        #Error will already have been reported in
                        #Manage Repository dialog
                        self.__catalog_refresh_done()
                        return -1
                except api_errors.CatalogRefreshException, cre:
                        total = cre.total
                        succeeded = cre.succeeded
                        ermsg = _("Network problem.\n\n")
                        ermsg += _("Details:\n")
                        ermsg += "%s/%s" % (succeeded, total)
                        ermsg += _(" catalogs successfully updated:\n")
                        for pub, err in cre.failed:
                                if isinstance(err, HTTPError):
                                        ermsg += "   %s: %s - %s\n" % \
                                            (err.filename, err.code, err.msg)
                                elif isinstance(err, URLError):
                                        if err.args[0][0] == 8:
                                                ermsg += "    %s: %s\n" % \
                                                    (urlparse.urlsplit(
                                                        pub["origin"])[1].split(":")[0],
                                                    err.args[0][1])
                                        else:
                                                if isinstance(err.args[0], \
                                                    socket.timeout):
                                                        ermsg += "    %s: %s\n" % \
                                                            (pub["origin"], "timeout")
                                                else:
                                                        ermsg += "    %s: %s\n" % \
                                                            (pub["origin"], \
                                                            err.args[0][1])
                                elif "data" in err.__dict__ and err.data:
                                        ermsg += err.data
                                else:
                                        ermsg += _("Unknown error")
                                        ermsg += "\n"

                        gobject.idle_add(self.error_occured, ermsg,
                            None, gtk.MESSAGE_INFO)
                        self.__catalog_refresh_done()
                        return -1
                except api_errors.InvalidDepotResponseException, idrex:
                        err = str(idrex)
                        gobject.idle_add(self.error_occured, err,
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

        def __add_pkgs_to_lists_from_cache(self, publisher, application_list,
            category_list, section_list):
                if self.cache_o:
                        self.cache_o.load_application_list(publisher, application_list,
                            self.selected_pkgs)
                        self.cache_o.load_category_list(publisher, category_list)
                        self.cache_o.load_section_list(publisher, section_list)

        def __add_pkgs_to_lists_from_api(self, publisher, application_list,
            category_list, section_list):
                """ This method set up image from the given directory and
                returns the image object or None"""
                pargs = []
                pargs.append("pkg://" + publisher + "/*")
                try:
                        pkgs_known = self.__get_inventory_list(pargs,
                            True, True)
                except api_errors.InventoryException:
                        # Can't happen when all_known is true and no args,
                        # but here for completeness.
                        err = _("Selected repository does not contain any packages."
                                "\nPlease reload the list of package.")
                        gobject.idle_add(self.w_progress_dialog.hide)
                        gobject.idle_add(self.error_occured, err, None,
                            gtk.MESSAGE_INFO)
                        self.unset_busy_cursor()
                        return

                return self.__add_pkgs_to_lists(pkgs_known, application_list,
                    category_list, section_list)

        def __add_pkgs_to_lists(self, pkgs_known, application_list,
            category_list, section_list):
                if section_list != None:
                        self.__init_sections(section_list)
                #Only one instance of those icons should be in memory
                update_available_icon = gui_misc.get_icon_pixbuf(self.application_dir,
                    "status_newupdate")
                installed_icon = gui_misc.get_icon_pixbuf(self.application_dir,
                    "status_installed")
                update_for_category_icon = \
                    self.get_icon_pixbuf_from_glade_dir("legend_newupdate")
                #Imageinfo for categories
                imginfo = imageinfo.ImageInfo()
                sectioninfo = imageinfo.ImageInfo()
                pubs = [p.prefix for p in self.api_o.get_publishers()]
                categories = {}
                sections = {}
                share_path = "/usr/share/package-manager/data/"
                for pub in pubs:
                        category = imginfo.read(self.application_dir +
                            share_path + pub)
                        if len(category) == 0:
                                category = imginfo.read(self.application_dir +
                                    share_path + "opensolaris.org")
                        categories[pub] = category
                        section = sectioninfo.read(self.application_dir +
                            share_path + pub + ".sections")
                        if len(section) == 0:
                                section = sectioninfo.read(self.application_dir +
                                    share_path + "opensolaris.org.sections")
                        sections[pub] = section
                pkg_count = 0
                pkg_add = 0
                progress_percent = INITIAL_PROGRESS_TOTAL_PERCENTAGE
                total_pkg_count = len(pkgs_known)
                progress_increment = \
                        total_pkg_count / PACKAGE_PROGRESS_TOTAL_INCREMENTS
                self.progress_stop_timer_thread = True
                while gtk.events_pending():
                        gtk.main_iteration(False)
                prev_stem = ""
                prev_pfmri_str = ""
                next_app = None
                pkg_name = None
                pkg_publisher = None
                prev_state = None
                category_icon = None
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
                                    category_icon,
                                    categories, category_list, pkg_publisher)
                                pkg_add += 1
                        prev_stem = pkg.get_pkg_stem()
                        prev_pfmri_str = pkg.get_short_fmri()
                        prev_state = state

                        if progress_increment > 0 and pkg_count % progress_increment == 0:
                                progress_percent += PACKAGE_PROGRESS_PERCENT_INCREMENT
                                if progress_percent <= PACKAGE_PROGRESS_PERCENT_TOTAL:
                                        self.__progressdialog_progress_percent(
                                            progress_percent, pkg_count, total_pkg_count)
                                while gtk.events_pending():
                                        gtk.main_iteration(False)

                        status_icon = None
                        category_icon = None
                        pkg_name = pkg.get_name()
                        pkg_name = gui_misc.get_pkg_name(pkg_name)
                        pkg_stem = pkg.get_pkg_stem()
                        pkg_publisher = pkg.get_publisher()
                        pkg_state = enumerations.NOT_INSTALLED
                        if state["state"] == "installed":
                                pkg_state = enumerations.INSTALLED
                                if state["upgradable"] == True:
                                        status_icon = update_available_icon
                                        category_icon = update_for_category_icon
                                        pkg_state = enumerations.UPDATABLE
                                else:
                                        status_icon = installed_icon
                        marked = False
                        if not self.is_remote_search:
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

                self.__add_package_to_list(next_app, application_list, pkg_add,
                    pkg_name, category_icon, categories, category_list, pkg_publisher)
                pkg_add += 1
                if category_list != None:
                        self.__add_categories_to_sections(sections,
                            category_list, section_list)
                self.__progressdialog_progress_percent(PACKAGE_PROGRESS_PERCENT_TOTAL,
                    total_pkg_count, total_pkg_count)
                return

        def __add_categories_to_sections(self, sections, category_list, section_list):
                for publisher in sections:
                        for section in sections[publisher]:
                                for category in sections[publisher][section].split(","):
                                        self.__add_category_to_section(_(category),
                                            _(section), category_list, section_list)

                #1915 Sort the Categories into alphabetical order and prepend All Category
                if len(category_list) > 0:
                        rows = [tuple(r) + (i,) for i, r in enumerate(category_list)]
                        rows.sort(self.__sort)
                        r = []
                        category_list.reorder([r[-1] for r in rows])
                return

        def __add_package_to_list(self, app, application_list, pkg_add,
            pkg_name, category_icon, categories, category_list, publisher):
                row_iter = application_list.insert(pkg_add, app)
                if category_list == None:
                        return
                cat_pub = categories.get(publisher)
                if pkg_name in cat_pub:
                        pkg_categories = cat_pub.get(pkg_name)
                        for pcat in pkg_categories.split(","):
                                self.__add_package_to_category(_(pcat), None,
                                    category_icon, row_iter, application_list,
                                    category_list)

        @staticmethod
        def __add_package_to_category(category_name, category_description,
            category_icon, package, application_list, category_list):
                if not package or category_name == _('All'):
                        return
                if not category_name:
                        return
                category_id = None
                icon_visible = False
                if category_icon:
                        icon_visible = True
                for category in category_list:
                        if category[enumerations.CATEGORY_NAME] == category_name:
                                category_id = category[enumerations.CATEGORY_ID]
                                if category_icon:
                                        category[enumerations.CATEGORY_ICON] = \
                                            category_icon
                                        category[enumerations.CATEGORY_ICON_VISIBLE] = \
                                            icon_visible
                                break
                if not category_id:                       # Category not exists
                        category_id = len(category_list) + 1
                        category_list.append([category_id, category_name,
                            category_description, category_icon, icon_visible,
                            True, None])
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

                        gobject.idle_add(self.w_progressbar.set_fraction,
                            self.progress_fraction_time_count)
                        self.progress_fraction_time_count += \
                                INITIAL_PROGRESS_TIME_PERCENTAGE
                        time.sleep(INITIAL_PROGRESS_TIME_INTERVAL)
                self.progress_stop_timer_thread = False
                self.progress_fraction_time_count = 0

        def __progressdialog_progress_percent(self, fraction, count, total):
                gobject.idle_add(self.w_progressinfo_label.set_text, _(
                    "Processing package entries: %d of %d") % (count, total)  )
                gobject.idle_add(self.w_progressbar.set_fraction, fraction)

        def error_occured(self, error_msg, msg_title=None, msg_type=gtk.MESSAGE_ERROR):
                msgbox = gtk.MessageDialog(parent =
                    self.w_main_window,
                    buttons = gtk.BUTTONS_CLOSE,
                    flags = gtk.DIALOG_MODAL,
                    type = msg_type,
                    message_format = None)
                msgbox.set_property('text', error_msg)
                title = None
                if msg_title:
                        title = msg_title
                else:
                        title = _("Package Manager")
                msgbox.set_title(title)
                msgbox.run()
                msgbox.destroy()

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
        def get_installed_version(api_o, pkg):
                return api_o.img.get_version_installed(pkg)

        @staticmethod
        def get_manifest(img, package):
                '''helper function'''
                # XXX Should go to the  -> imageinfo.py
                manifest = None

                # 3087 shutdown time is too long when closing down soon after startup
                if packagemanager.cancelled:
                        return manifest
                try:
                        manifest = img.get_manifest(package)
                except OSError:
                        # XXX It is possible here that the user doesn't have network con,
                        # XXX proper permissions to save manifest, should we do something
                        # XXX and popup information dialog?
                        pass
                except (retrieve.ManifestRetrievalError,
                    retrieve.DatastreamRetrievalError, NameError):
                        pass
                except misc.TransportFailures:
                        pass
                return manifest

        @staticmethod
        def update_desc(description, pkg):
                if pkg[enumerations.DESCRIPTION_COLUMN] != description:
                        pkg[enumerations.DESCRIPTION_COLUMN] = description
                return

#-----------------------------------------------------------------------------#
# Public Methods
#-----------------------------------------------------------------------------#
        def setup_progressdialog_show(self):
                self.w_progress_dialog.set_title(_("Loading Repository Information"))
                self.w_progressinfo_label.set_text(
                    _( "Fetching package entries ..."))
                self.w_progress_cancel.hide()
                self.w_progress_dialog.show()
                Thread(target = self.__progressdialog_progress_time).start()

        def setup_progressdialog_hide(self):
                self.progress_stop_timer_thread = True
                self.w_progress_dialog.hide()

        def init_show_filter(self):
                self.__init_show_filter()                #Initiates filter

        def reload_packages(self):
                self.api_o = self.__get_api_object(self.image_directory, self.pr)
                self.cache_o = self.__get_cache_obj(self.application_dir, self.api_o)
                self.__on_reload(None)

        def set_busy_cursor(self):
                self.gdk_window.show()

        def unset_busy_cursor(self):
                self.gdk_window.hide()

        def process_package_list_start(self, image_directory):
                self.image_directory = image_directory
                if not self.api_o:
                        self.api_o = self.__get_api_object(image_directory, self.pr)
                        self.cache_o = self.__get_cache_obj(self.application_dir,
                            self.api_o)
                        self.img_timestamp = self.cache_o.get_index_timestamp()
                self.repositories_list = self.__get_new_repositories_liststore()
                self.__setup_repositories_combobox(self.api_o, self.repositories_list)

        @staticmethod
        def __get_cache_obj(application_dir, api_o):
                cache_o = cache.CacheListStores(application_dir,
                    api_o)
                return cache_o

        @staticmethod
        def __get_api_object(img_dir, progtrack):
                api_o = None
                try:
                        api_o = api.ImageInterface(img_dir,
                            CLIENT_API_VERSION,
                            progtrack, None, PKG_CLIENT_NAME)
                except (api_errors.VersionException,\
                    api_errors.ImageNotFoundException):
                        raise
                return api_o

        def process_package_list_end(self):
                self.__set_first_category_text()
                self.in_startpage_startup = False
                if self.update_all_proceed:
                # TODO: Handle situation where only SUNWipkg/SUNWipg-gui have been updated
                # in update all: bug 6357
                        self.__on_update_all(None)
                        self.update_all_proceed = False
                self.setup_progressdialog_hide()
                self.__enable_disable_install_remove()
                self.update_statusbar()
                self.in_setup = False
                self.cancelled = False
                if self.set_section != 0 or \
                    self.set_show_filter != enumerations.FILTER_ALL:
                        self.__application_refilter()
                else:
                        self.unset_busy_cursor()
                
                if self.first_run or self.in_reload:
                        Thread(target = self.__enable_disable_update_all).start()
                self.first_run = False
                self.in_reload = False
                if self.need_descriptions:
                        self.__get_manifests_thread()

        def __get_manifests_thread(self):
                Thread(target = self.get_manifests_for_packages,
                    args = ()).start()

        def get_icon_pixbuf_from_glade_dir(self, icon_name):
                return gui_misc.get_pixbuf_from_path(self.application_dir +
                    "/usr/share/package-manager/", icon_name)

        def get_manifests_for_packages(self):
                ''' Function, which get's manifest for packages. If the manifest is not
                locally tries to retrieve it. For installed packages gets manifest
                for the particular version (local operation only), if the package is
                not installed than the newest one'''
                time.sleep(2)
                count = 0
                self.description_thread_running = True
                img = self.api_o.img
                for pkg in self.application_list:
                        if self.cancelled:
                                self.description_thread_running = False
                                return
                        info = None
                        package = pkg[enumerations.FMRI_COLUMN]
                        if (img and package):
                                man = self.get_manifest(img, package)
                                if man:
                                        info = man.get("description", "")
                        gobject.idle_add(self.update_desc, info, pkg)
                        count += 1
                        if count % 2 ==  0:
                                time.sleep(0.001)
                self.api_o.log_operation_start("info")
                self.api_o.log_operation_end()
                self.description_thread_running = False

        def update_statusbar_for_search(self):
                status_str = self.search_options[self.current_search_option][3]
                self.search_message_id = self.w_main_statusbar.push(0, status_str)

        def update_statusbar_for_searching(self):
                if self.search_message_id > 0:
                        self.w_main_statusbar.remove(0, self.search_message_id)
                        self.search_message_id = 0
                status_str = _("Searching...")
                self.search_message_id = self.w_main_statusbar.push(0, status_str)

        def update_statusbar(self):
                '''Function which updates statusbar'''
                if self.search_message_id > 0:
                        self.w_main_statusbar.remove(0, self.search_message_id)
                        self.search_message_id = 0
                if self.is_remote_search:
                        opt_str = self.search_options[self.current_search_option][3]
                        if len(self.application_list) == SEARCH_LIMIT:
                                fmt_str = _("%s: first %d found")
                        else:
                                fmt_str = _("%s: %d found")
                        status_str = fmt_str % (opt_str,
                            len(self.application_list))
                        self.w_main_statusbar.push(0, status_str)
                        return
                installed = 0
                self.selected = 0
                sel = 0
                if self.application_list == None:
                        return
                visible_repository = self.__get_visible_repository_name()
                pkgs = self.selected_pkgs.get(visible_repository)
                if pkgs:
                        self.selected = len(pkgs)
                for pkg_row in self.application_list:
                        if pkg_row[enumerations.STATUS_COLUMN] == enumerations.INSTALLED \
                            or pkg_row[enumerations.STATUS_COLUMN] == \
                            enumerations.UPDATABLE:
                                installed = installed + 1
                        if pkg_row[enumerations.MARK_COLUMN]:
                                sel = sel + 1
                listed_str = _('%d listed') % len(self.application_list)
                sel_str = _('%d selected') % sel
                inst_str = _('%d installed') % installed
                status_str = _("%s: %s , %s, %s.") % (visible_repository, listed_str,
                        inst_str, sel_str)
                self.w_main_statusbar.push(0, status_str)

        def update_package_list(self, update_list):
                if update_list == None and self.img_timestamp:
                        return
                visible_repository = self.__get_visible_repository_name()
                default_publisher = self.default_publisher
                self.__load_catalogs()
                if not self.img_timestamp:
                        self.img_timestamp = self.cache_o.get_index_timestamp()
                        self.__on_reload(None)
                        return
                self.img_timestamp = self.cache_o.get_index_timestamp()
                installed_icon = gui_misc.get_icon_pixbuf(self.application_dir,
                    "status_installed")
                visible_list = update_list.get(visible_repository)
                if visible_list:
                        i = 0
                        while i < len(visible_list):
                                visible_list[i] = gui_misc.get_pkg_name(
                                    visible_list[i])
                                i +=  1
                        for row in self.application_list:
                                if row[enumerations.NAME_COLUMN] in visible_list:
                                        pkg = row[enumerations.FMRI_COLUMN]
                                        pkg_stem = row[enumerations.STEM_COLUMN]
                                        self.__remove_pkg_stem_from_list(pkg_stem)
                                        if self.info_cache.has_key(pkg_stem):
                                                del self.info_cache[pkg_stem]
                                        package_installed = \
                                            self.get_installed_version(self.api_o, pkg)
                                        if package_installed:
                                                inst_stem = \
                                                    package_installed.get_pkg_stem()
                                                if inst_stem == pkg_stem:
                                                        row[enumerations.STATUS_COLUMN] = \
                                                            enumerations.INSTALLED
                                                        row[enumerations.STATUS_ICON_COLUMN] = \
                                                            installed_icon
                                        else:
                                                row[enumerations.STATUS_COLUMN] = \
                                                    enumerations.NOT_INSTALLED
                                                row[enumerations.STATUS_ICON_COLUMN] = \
                                                    None
                                        row[enumerations.MARK_COLUMN] = False
                        self.__dump_datamodels(visible_repository,
                                self.application_list, self.category_list,
                                self.section_list)
                for publisher in update_list:
                        if publisher != visible_repository:
                                pkg_list = update_list.get(publisher)
                                for pkg in pkg_list:
                                        pkg_stem = None
                                        if publisher != default_publisher:
                                                pkg_stem = "pkg://%s/%s" % \
                                                        (publisher, pkg)
                                        else:
                                                pkg_stem = "pkg:/%s" % pkg
                                        if pkg_stem:
                                                if self.info_cache.has_key(pkg_stem):
                                                        del self.info_cache[pkg_stem]
                                                self.__remove_pkg_stem_from_list(pkg_stem)
                self.__process_package_selection()
                self.__enable_disable_selection_menus()
                self.__enable_disable_install_remove()
                self.update_statusbar()
                Thread(target = self.__enable_disable_update_all).start()

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
                
                self.w_ua_completed_dialog.set_title(_("Update All"))
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


        # Setup webinstall
        if info_install_arg or (len(sys.argv) == 2 and \
            sys.argv[1].endswith(PKGINFO_SUFFIX)):
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

        packagemanager.init_show_filter()

        packagemanager.process_package_list_start(image_dir)

        main()
