#!/usr/bin/python
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
# Copyright (c) 2010, Oracle and/or its affiliates.  All rights reserved.
#

import os
import sys
import urllib
import urlparse
import locale
import re
from gettext import ngettext

try:
        import gtkhtml2
        import gtk
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc
import pkg.gui.parseqs as parseqs
from pkg.client import global_settings

logger = global_settings.logger

(
DISPLAY_LINK,
CLICK_LINK,
) = range(2)

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
INTERNAL_SEARCH_ALL_PUBS_PAGE = "search_all_publishers_page"
                                #Internal field: go to search all publishers page
INTERNAL_SEARCH_ALL_PUBS = "search_all_publishers" #Internal field: search all publishers
INTERNAL_SEARCH_ALL_PUBS_INSTALLED = "search_all_publishers_installed"
                               #Internal field: search all publishers installed
INTERNAL_SEARCH_HELP = "search_help" # Internal field: display search help

FONTSIZE_H3_DEFAULT = 16        # Default H3 font size when display web page
FONTSIZE_BODY_DEFAULT = 10      # Default Body font size when display web page

# External Example: <a href="pm?pm-action=external&uri=www.opensolaris.com">
ACTION_EXTERNAL = 'external'   # External Action value: pm-action=external
EXTERNAL_URI = 'uri'           # External field: uri to navigate to in external
                               # default browser without protocol scheme specified
EXTERNAL_PROTOCOL = 'protocol' # External field: optional protocol scheme,
                               # defaults to http
DEFAULT_PROTOCOL = 'http'

# Theme: use High Contrast or Inverse images for HCI and HC themes, specified by prefix
INFORMATION_TABLE_HEADER = (
            "<table border='0' cellpadding='3' style='table-layout:fixed' >"
            "<TR><TD><IMG SRC = '%(base)s/%(prefix)sdialog-information.png' "
            "style='border-style: none' "
            )
HIGH_CONTRAST_PREFIX = "hc_"
HIGH_CONTRAST_INV_PREFIX = "hci_"

debug = False

class StartPage:
        def __init__(self, parent, application_dir):
                self.application_dir = application_dir
                self.current_url = None
                self.document = None
                self.lang = None
                self.lang_root = None
                self.cached_internal_stream = ""
                self.opener = None
                self.parent = parent
                self.start_page_uri = ""
                self.view = None
                self.page_bg = "#ffff"
                self.page_fg = "#0000"
                self.image_prefix = ""
                s = gtk.settings_get_default()
                self.theme_name = s.get_property("gtk-theme-name")
                self.font_scale = 1.0
                self.h3_fontsize = FONTSIZE_H3_DEFAULT
                self.body_fontsize = FONTSIZE_BODY_DEFAULT

        def setup_startpage(self):
                self.opener = urllib.FancyURLopener()
                self.document = gtkhtml2.Document()
                self.document.connect('request_url', self.__request_url)
                self.document.connect('link_clicked', self.__handle_link)
                self.document.clear()

                self.view = gtkhtml2.View()
                self.view.set_document(self.document)
                self.view.connect('request_object', self.__request_object)
                self.view.connect('on_url', self.__on_url)
                self.view.connect('style-set', self.__style_set)
                try:
                        result = locale.getlocale(locale.LC_CTYPE)
                        self.lang = result[0]
                except locale.Error:
                        self.lang = "C"
                if self.lang == None or self.lang == "":
                        self.lang = "C"
                self.lang_root = self.lang.split('_')[0]
                # Load Start Page to setup base URL to allow loading images in other pages
                self.load_startpage()

        # Theme: on Theme change setup bg and fg colours and prefix for loading pages
        def __style_set(self, widget, style, data=None):
                self.font_scale = gui_misc.get_scale(
                        self.parent.detailspanel.w_generalinfo_textview)
                if self.font_scale < 1.0:
                        self.font_scale = 1.0

                self.h3_fontsize = \
                        int(round(FONTSIZE_H3_DEFAULT * self.font_scale))
                self.body_fontsize = \
                        int(round(FONTSIZE_BODY_DEFAULT * self.font_scale))

                s = gtk.settings_get_default()
                self.theme_name = s.get_property("gtk-theme-name")

                style = self.parent.w_application_treeview.get_style().copy()
                self.page_bg = style.bg[gtk.STATE_NORMAL]
                self.page_fg = style.fg[gtk.STATE_NORMAL]

                self.image_prefix = ""
                if self.theme_name == "HighContrastInverse" or \
                        self.theme_name == "HighContrastLargePrintInverse":
                        self.image_prefix = HIGH_CONTRAST_INV_PREFIX
                elif self.theme_name == "HighContrast" or \
                        self.theme_name == "HighContrastLargePrint":
                        self.image_prefix = HIGH_CONTRAST_PREFIX

                self.handle_resize()

        def load_startpage(self):
                self.cached_internal_stream = ""
                if self.__load_startpage_locale(START_PAGE_CACHE_LANG_BASE):
                        return
                if self.__load_startpage_locale(START_PAGE_LANG_BASE):
                        return
                self.link_load_error(self.start_page_uri)

        # Stub handler required by GtkHtml widget
        def __request_object(self, *vargs):
                pass

        def __load_startpage_locale(self, start_page_lang_base):
                self.start_page_uri = os.path.join(self.application_dir,
                        start_page_lang_base % (self.lang, START_PAGE_HOME))
                if self.__load_internal_uri(self.document, self.start_page_uri):
                        return True

                if self.lang_root != None and self.lang_root != self.lang:
                        self.start_page_uri = os.path.join(self.application_dir,
                                start_page_lang_base % (self.lang_root, START_PAGE_HOME))
                        if self.__load_internal_uri(self.document, self.start_page_uri):
                                return True

                self.start_page_uri = os.path.join(self.application_dir,
                        start_page_lang_base % ("C", START_PAGE_HOME))
                if self.__load_internal_uri(self.document, self.start_page_uri):
                        return True
                return False

       # Stub handler required by GtkHtml widget or widget will assert
        def __stream_cancel(self, *vargs):
                pass

        def __load_internal_uri(self, document, link):
                self.parent.update_statusbar_message(_("Loading... %s") % link)
                try:
                        f = self.__open_url(link)
                except  (IOError, OSError):
                        self.parent.update_statusbar_message(_("Stopped"))
                        return False
                self.current_url = self.__resolve_uri(link)

                self.document.clear()
                headers = f.info()
                mime = headers.getheader('Content-type').split(';')[0]
                if mime:
                        self.document.open_stream(mime)
                else:
                        self.document.open_stream('text/plain')

                text = f.read()
                # Theme: use current Theme's bg and fg colours in internally loaded uri
                text = text.replace('<body>',
                    "<body fgcolor='%s' bgcolor='%s'>" % (self.page_fg, self.page_bg))

                # Theme: setup Start Page for current Theme
                if link.endswith(START_PAGE_HOME):
                        text = self.__process_startpage(text)
                self.document.write_stream(text)
                self.document.close_stream()
                self.parent.update_statusbar_message(_("Done"))
                return True

        # Theme: setup Start Page for the current Theme
        def __process_startpage(self, text):
                # Strip background and all style colors for High Contrast, Inverse and
                # Low Contrast Themes
                if self.theme_name.startswith("HighContrast") or \
                        self.theme_name.startswith("LowContrast"):
                        text = re.sub("background-color: #\w+; ", "", text)
                        text = re.sub('style="background-color: #\w+"', "", text)
                        text = re.sub("color: #\w+;", "", text)
                if self.font_scale > 1.0:
                        text = re.sub("font-size: 20pt;",
                            "font-size: %dpx;" % int(round(20 * self.font_scale)), text)
                        text = re.sub("font-size: 15px;",
                            "font-size: %dpx;" % int(round(15 * self.font_scale)), text)
                        text = re.sub("font-size: 14px;",
                            "font-size: %dpx;" % int(round(14 * self.font_scale)), text)
                        text = re.sub('width="125"',
                            'width="%d"' % int(round(125 * self.font_scale)), text)

                # Use High Contrast and Inverse images for HC and HCI themes
                if self.image_prefix != "":
                        text = re.sub("/\w*install.png",
                            "/" + self.image_prefix + "install.png", text)
                # OpenSolaris icon renders poorly on Low Contrast and dark nimbus themes
                # replace with text link
                if self.theme_name.startswith("LowContrast") or \
                        self.theme_name == "dark-nimbus":
                        text = re.sub(
                            '<td><a href="http://www.opensolaris.com">'
                            '<IMG SRC = "opensolaris.png" align="right"/></a></td>',
                            '<td align="right"><a href="http://www.opensolaris.com">'
                            'OpenSolaris...  </a></td>', text)
                elif self.image_prefix != "":
                        text = re.sub(
                            "opensolaris.png",
                            self.image_prefix + "opensolaris.png", text)
                return text

        def __request_url(self, document, url, stream):
                try:
                        f = self.__open_url(url)
                except  (IOError, OSError), err:
                        logger.error(str(err))
                        gui_misc.notify_log_error(self.parent)
                        return
                stream.set_cancel_func(self.__stream_cancel)
                stream.write(f.read())

        def __handle_link(self, document, link, handle_what = CLICK_LINK):
                query_dict = self.__urlparse_qs(link)

                action = None
                if query_dict.has_key(PM_ACTION):
                        action = query_dict[PM_ACTION][0]
                elif handle_what == DISPLAY_LINK:
                        return link

                search_action = None
                if action == ACTION_INTERNAL:
                        if query_dict.has_key(INTERNAL_SEARCH):
                                search_action = query_dict[INTERNAL_SEARCH][0]

                s1, e1 = self.parent.get_start_end_strings()

                # Browse a Publisher
                if search_action and search_action.find(INTERNAL_SEARCH_VIEW_PUB) > -1:
                        pub = re.findall(r'<b>(.*)<\/b>', search_action)[0]
                        if handle_what == DISPLAY_LINK:
                                pub_name =  \
                                    self.parent.get_publisher_display_name_from_prefix(
                                    pub)
                                return _("View packages in %(s1)s%(pub)s%(e1)s") % \
                                        {"s1": s1, "pub": \
                                        pub_name, "e1": e1}
                        self.parent.browse_publisher(pub)
                        return

                # Go to Search in All Publishers page
                if search_action and search_action == INTERNAL_SEARCH_ALL_PUBS_PAGE:
                        if handle_what == DISPLAY_LINK:
                                return _("Go to Search %(s1)sAll Publishers%(e1)s page")\
                                        % {"s1": s1, "e1": e1}
                        self.parent.pm_setup_search_all_page()
                        return

                # Search in All Publishers
                if search_action and search_action == INTERNAL_SEARCH_ALL_PUBS:
                        if handle_what == DISPLAY_LINK:
                                return _("Search within %(s1)sAll Publishers%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.parent.handle_search_all_publishers()
                        return

                # Change view to All Publishers (Installed)
                if search_action and search_action == INTERNAL_SEARCH_ALL_PUBS_INSTALLED:
                        if handle_what == DISPLAY_LINK:
                                return _("View %(s1)sAll Installed Packages%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.parent.handle_view_all_publishers_installed()
                        return
                # Launch Search Help
                if search_action and search_action == INTERNAL_SEARCH_HELP:
                        if handle_what == DISPLAY_LINK:
                                return _("Display %(s1)sSearch Help%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.parent.update_statusbar_message(
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
                        self.parent.goto_recent_search(recent_search)
                        return

               # Change View to All Packages
                if search_action and search_action == INTERNAL_SEARCH_VIEW_ALL:
                        if handle_what == DISPLAY_LINK:
                                return _("Change View to %(s1)sAll Packages%(e1)s") % \
                                        {"s1": s1, "e1": e1}
                        self.parent.set_view_all_packages()
                        return
                # Internal Browse
                if action == ACTION_INTERNAL:
                        if query_dict.has_key(INTERNAL_URI):
                                int_uri = query_dict[INTERNAL_URI][0]
                                if handle_what == DISPLAY_LINK:
                                        return int_uri
                        else:
                                if handle_what == CLICK_LINK:
                                        self.link_load_error(
                                            _("No URI specified"))
                                return
                        if handle_what == CLICK_LINK and \
                            not self.__load_internal_uri(document, int_uri):
                                self.link_load_error(int_uri)
                        return
                # External browse
                elif action == ACTION_EXTERNAL:
                        if query_dict.has_key(EXTERNAL_URI):
                                ext_uri = query_dict[EXTERNAL_URI][0]
                        else:
                                if handle_what == CLICK_LINK:
                                        self.link_load_error(
                                            _("No URI specified"))
                                return
                        if query_dict.has_key(EXTERNAL_PROTOCOL):
                                protocol = query_dict[EXTERNAL_PROTOCOL][0]
                        else:
                                protocol = DEFAULT_PROTOCOL

                        if handle_what == DISPLAY_LINK:
                                return protocol + "://" + ext_uri
                        self.parent.open_link(protocol + "://" + ext_uri)
                        return
                elif handle_what == DISPLAY_LINK:
                        return None
                elif action == None:
                        if link and link.endswith(".p5i"):
                                self.parent.invoke_webinstall(link)
                                return
                        self.parent.open_link(link)
                        return
                # Handle empty and unsupported actions
                elif action == "":
                        self.link_load_error(_("Empty Action not supported"))
                        return
                elif action != None:
                        self.link_load_error(
                            _("Action not supported: %s") % action)
                        return

        def __on_url(self, view, link):
                # Handle mouse over events on links and reset when not on link
                if link == None or link == "":
                        self.parent.update_statusbar()
                else:
                        display_link = self.__handle_link(None, link, DISPLAY_LINK)
                        if display_link != None:
                                self.parent.update_statusbar_message(display_link)
                        else:
                                self.parent.update_statusbar()
       
        def __open_url(self, url):
                uri = self.__resolve_uri(url)
                return self.opener.open(uri)

        def __resolve_uri(self, uri):
                if self.__is_relative_to_server(uri) and self.current_url != uri:
                        return urlparse.urljoin(self.current_url, uri)
                return uri

        @staticmethod
        def __is_relative_to_server(url):
                parts = urlparse.urlparse(url)
                if parts[0] or parts[1]:
                        return 0
                return 1

        def __load_internal_page(self, text =""):
                self.cached_internal_stream = text
                self.document.clear()
                self.document.open_stream('text/html')
                # Theme: use Theme's bg and fg colours in loaded internal page

                display = ("<html><head><meta http-equiv='Content-Type' "
                        "content='text/html; charset=UTF-8'></head>"
                        "<style>h3 {font-size:%(h3_fs)dpt}</style>"
                        "<style>body {font-size:%(body_fs)dpt}</style><body "
                        "fgcolor='%(fg)s' bgcolor='%(bg)s'>%(text)s</body></html>" %
                         {"h3_fs": self.h3_fontsize, "body_fs": self.body_fontsize,
                         "fg": self.page_fg, "bg": self.page_bg, "text": text})

                self.document.write_stream(display)
                self.document.close_stream()

        def load_blank(self):
                self.__load_internal_page()

        def handle_resize(self):
                if self.cached_internal_stream == "":
                        self.load_startpage()
                        return
                # Theme: setup images for current Theme in self.cached_internal_stream
                # before reloading
                self.cached_internal_stream = re.sub(
                    "/\w*dialog-information.png",
                    "/" + self.image_prefix + "dialog-information.png",
                    self.cached_internal_stream)
                self.cached_internal_stream = re.sub(
                    "/\w*dialog-warning.png",
                    "/" + self.image_prefix + "dialog-warning.png",
                    self.cached_internal_stream)

                self.__load_internal_page(self.cached_internal_stream)

        def setup_search_all_page(self, publisher_list, publisher_all):
                tbl_header = INFORMATION_TABLE_HEADER % {"base": START_PAGE_IMAGES_BASE,
                    "prefix": self.image_prefix}
                tbl_header += _("alt='[Information]' title='Information' ALIGN='bottom'>"
                    "</TD><TD><h3><b>Search All Publishers</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD> Use the Search field to search for packages "
                    "within the following Publishers:</TD></TR>"
                    )
                tbl_body = "<TR><TD></TD><TD>"
                pub_browse_list = ""
                for (prefix, pub_alias) in publisher_list:
                        if pub_alias != None and len(pub_alias) > 0:
                                pub_name = "%s (%s)" % (pub_alias, prefix)
                        else:
                                pub_name = prefix

                        tbl_body += "<li style='padding-left:7px'>%s</li>" % pub_name
                        pub_browse_list += "<li style='padding-left:7px'><a href="
                        pub_browse_list += "'pm?pm-action=internal&search=%s" % \
                                INTERNAL_SEARCH_VIEW_PUB
                        if pub_alias != None and len(pub_alias) > 0:
                                name = pub_alias
                        else:
                                name = pub_name
                        pub_browse_list += " <b>%s</b>'>%s</a></li>" % \
                            (prefix, name)
                tbl_body += "<TD></TD></TR>"
                tbl_body += _("<TR><TD></TD><TD></TD></TR>"
                    "<TR><TD></TD><TD>Click on the Publishers below to view their list "
                    "of packages:</TD></TR>"
                    )
                tbl_body += "<TR><TD></TD><TD>"
                tbl_body += pub_browse_list
                tbl_body += "<TD></TD></TR>"
                
                pub_browse_all = "<li style='padding-left:7px'><a href="
                pub_browse_all += "'pm?pm-action=internal&search=%s" % \
                        INTERNAL_SEARCH_VIEW_PUB
                pub_browse_all += " <b>%s</b>'>%s</a></li>" % \
                            (publisher_all, publisher_all)
                tbl_body += _("<TR><TD></TD><TD></TD></TR>"
                    "<TR><TD></TD><TD>Click on the link below to view the full list "
                    "of packages:</TD></TR>"
                    )
                tbl_body += "<TR><TD></TD><TD>"
                tbl_body += pub_browse_all
                tbl_body += "<TD></TD></TR>"
                tbl_footer = "</table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def setup_search_installed_page(self, text):
                tbl_header = INFORMATION_TABLE_HEADER % {"base": START_PAGE_IMAGES_BASE,
                    "prefix": self.image_prefix}
                tbl_header += _("alt='[Information]' title='Information' ALIGN='bottom'>"
                    "</TD><TD><h3><b>Search in All Installed Packages</b></h3><TD></TD>"
                    "</TR><TR><TD></TD><TD> Search is <b>not</b> supported in "
                    "All Installed Packages.</TD></TR>"
                    )

                tbl_body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD>"
                    "</TR><TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )

                tbl_body += _("<li style='padding-left:7px'>Return to view "
                    "All Installed Packages <a href='pm?pm-action=internal&search="
                    "%s'>(Installed)</a></li>")  % INTERNAL_SEARCH_ALL_PUBS_INSTALLED
                tbl_body += _("<li style='padding-left:7px'>Search for <b>%(text)s"
                    "</b> using All Publishers <a href='pm?pm-action=internal&search="
                    "%(all_pubs)s'>(Search)</a></li>")  % \
                    {"text": text, "all_pubs": INTERNAL_SEARCH_ALL_PUBS}

                tbl_body += _("<li style='padding-left:7px'>"
                    "See <a href='pm?pm-action=internal&search="
                    "%s'>Search Help</a></li></TD></TR>") % INTERNAL_SEARCH_HELP
                tbl_footer = "</table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def setup_search_zero_results_page(self, name, text, is_all_publishers):
                tbl_header = INFORMATION_TABLE_HEADER % {"base": START_PAGE_IMAGES_BASE,
                    "prefix": self.image_prefix}
                tbl_header += _("alt='[Information]' title='Information' ALIGN='bottom'>"
                    "</TD><TD><h3><b>Search Results</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD>No packages found in <b>%(pub)s</b> "
                    "matching <b>%(text)s</b></TD></TR>") % {"pub": name, "text": text}

                tbl_body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD>"
                    "</TR><TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    "<li style='padding-left:7px'>Check your spelling</li>"
                    "<li style='padding-left:7px'>Try new search terms</li>"
                    )
                if not is_all_publishers:
                        tbl_body += _("<li style='padding-left:7px'>Search for <b>"
                            "%(text)s</b> within <a href='pm?pm-action=internal&search="
                            "%(all_pubs)s'>All Publishers</a></li>")  % \
                            {"text": text, "all_pubs": INTERNAL_SEARCH_ALL_PUBS}

                tbl_body += _("<li style='padding-left:7px'>"
                    "See <a href='pm?pm-action=internal&search="
                    "%s'>Search Help</a></li></TD></TR>") % INTERNAL_SEARCH_HELP
                tbl_footer = "</table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def setup_recent_search_page(self, searches_list):
                tbl_header = INFORMATION_TABLE_HEADER % {"base": START_PAGE_IMAGES_BASE,
                    "prefix": self.image_prefix}
                tbl_header += _("alt='[Information]' title='Information' ALIGN='bottom'>"
                    "</TD><TD><h3><b>Recent Searches</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD> Access stored results from recent searches "
                    "in this session.</TD></TR>"
                    )
                tbl_body = "<TR><TD></TD><TD>"
                search_list = ""
                for search in searches_list:
                        search_list += "<li style='padding-left:7px'>%s: <a href=" % \
                                search
                        search_list += "'pm?pm-action=internal&search=%s" % \
                                INTERNAL_SEARCH_VIEW_RESULTS
                        search_list += " <span>%s</span>'>" % search
                        search_list += _("results")
                        search_list += "</a></li>"

                if len(searches_list) > 0:
                        tbl_body += "<TR><TD></TD><TD></TD></TR><TR><TD></TD><TD>"
                        tbl_body += ngettext(
                            "Click on the search results link below to view the stored "
                            "results:", "Click on one of the search results links below "
                            "to view the stored results:",
                            len(searches_list)
                            )
                        tbl_body += "</TD></TR><TR><TD></TD><TD>"
                        tbl_body += search_list
                tbl_body += "<TD></TD></TR>"
                tbl_footer = "</table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def setup_zero_filtered_results_page(self, length_visible_list, filter_desc):
                tbl_header = INFORMATION_TABLE_HEADER % {"base": START_PAGE_IMAGES_BASE,
                    "prefix": self.image_prefix}
                tbl_header += _("alt='[Information]' title='Information' ALIGN='bottom'>"
                    "</TD><TD><h3><b>View Packages</b></h3><TD></TD></TR><TR><TD></TD>"
                    "<TD>")
                tbl_header += ngettext(
                    "There is one package in this category, "
                    "however it is not visible in the selected View:\n"
                    "<li style='padding-left:7px'><b>%s</b></li>",
                    "There are a number of packages in this category, "
                    "however they are not visible in the selected View:\n"
                    "<li style='padding-left:7px'><b>%s</b></li>",
                    length_visible_list) %  filter_desc
                tbl_body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD>"
                    "</TR><TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )
                tbl_body += _("<li style='padding-left:7px'>"
                    "<a href='pm?pm-action=internal&"
                    "search=%s'>Change View to All Packages</a></li>") % \
                    INTERNAL_SEARCH_VIEW_ALL
                tbl_footer = "</TD></TR></table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def setup_search_zero_filtered_results_page(self, text, num, filter_desc):
                tbl_header = INFORMATION_TABLE_HEADER % {"base": START_PAGE_IMAGES_BASE,
                    "prefix": self.image_prefix}
                tbl_header += _("alt='[Information]' title='Information' ALIGN='bottom'>"
                    "</TD><TD><h3><b>Search Results</b></h3><TD></TD></TR><TR><TD></TD>"
                    "<TD>")
                tbl_header += ngettext(
                    "Found <b>%(num)s</b> package matching <b>%(text)s</b> "
                    "in All Packages, however it is not listed in the "
                    "<b>%(filter)s</b> View.",
                    "Found <b>%(num)s</b> packages matching <b>%(text)s</b> "
                    "in All Packages, however they are not listed in the "
                    "<b>%(filter)s</b> View.", num) % {"num": num, "text": text,
                    "filter": filter_desc}

                tbl_body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD>"
                    "</TR><TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )
                tbl_body += _("<li style='padding-left:7px'>"
                    "<a href='pm?pm-action=internal&"
                    "search=%s'>Change View to All Packages</a></li>") % \
                    INTERNAL_SEARCH_VIEW_ALL
                tbl_footer = "</TD></TR></table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def setup_search_wildcard_page(self):
                tbl_header = _(
                    "<table border='0' cellpadding='3' style='table-layout:fixed' >"
                    "<TR><TD><IMG SRC = '%(base)s/%(prefix)sdialog-warning.png' "
                    "style='border-style: "
                    "none' alt='[Warning]' title='Warning' ALIGN='bottom'></TD>"
                    "<TD><h3><b>Search Warning</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD>Search using only the wildcard character, "
                    "<b>*</b>, is not supported in All Publishers</TD></TR>"
                    ) % {"base": START_PAGE_IMAGES_BASE, "prefix": self.image_prefix}
                tbl_body = _("<TR><TD></TD><TD<TD></TD></TR><TR><TD></TD><TD<TD></TD>"
                    "</TR><TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    "<li style='padding-left:7px'>Try new search terms</li>"
                    )
                tbl_body += _("<li style='padding-left:7px'>"
                    "Return to <a href='pm?pm-action=internal&search="
                    "%s'>Search All Publishers</a></li>") \
                    % INTERNAL_SEARCH_ALL_PUBS_PAGE
                tbl_body += _("<li style='padding-left:7px'>"
                    "See <a href='pm?pm-action=internal&search="
                    "%s'>Search Help</a></li></TD></TR>") % INTERNAL_SEARCH_HELP
                tbl_footer = "</table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        def link_load_error(self, link):
                tbl_header = _(
                    "<table border='0' cellpadding='3' style='table-layout:fixed' >"
                    "<TR><TD><a href='stub'></a>"
                    "<IMG SRC = '%(base)s/%(prefix)sdialog-warning.png' "
                    "style='border-style: "
                    "none' alt='[Warning]' title='Warning' ALIGN='bottom'>"
                    "</TD><TD><h3><b>Warning</b></h3><TD></TD></TR>"
                    "<TR><TD></TD><TD>Unable to load the following URI: </TD></TR>"
                    ) % {"base": START_PAGE_IMAGES_BASE, "prefix": self.image_prefix}
                tbl_body = "<TR><TD></TD><TD<TD>"
                tbl_body +="<li style='padding-left:7px'>%s</li></TD></TR>" % (link)
                tbl_body += _("<TR><TD></TD><TD<TD></TD>"
                    "</TR><TR><TD></TD><TD<TD><b>Suggestions:</b><br></TD></TR>"
                    "<TR><TD></TD><TD<TD>"
                    )
                tbl_body += _("<li style='padding-left:7px'>"
                    "Return to <a href='pm?pm-action=internal&uri="
                    "%s'>Start Page</a></li></TD></TR>") % START_PAGE_HOME
                tbl_footer = "</table>"
                self.__load_internal_page(tbl_header + tbl_body + tbl_footer)

        @staticmethod
        def __urlparse_qs(url, keep_blank_values=0, strict_parsing=0):
                scheme, netloc, url, params, querystring, fragment = urlparse.urlparse(
                    url)
                if debug:
                        print ("Query: scheme %s, netloc %s, url %s, params %s,"
                            "querystring %s, fragment %s"
                            % (scheme, netloc, url, params, querystring, fragment))
                return parseqs.parse_qs(querystring)
