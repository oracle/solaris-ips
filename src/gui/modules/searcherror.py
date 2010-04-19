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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
try:
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc

class SearchError:
        def __init__(self, gladefile, gconf, parent):
                self.gconf = gconf
                self.parent = parent
                self.w_tree_api_search_error = gtk.glade.XML(gladefile,
                    "api_search_error")
                self.api_search_error_dialog = \
                    self.w_tree_api_search_error.get_widget("api_search_error")
                self.api_search_error_textview = \
                    self.w_tree_api_search_error.get_widget("api_search_error_text")
                self.api_search_checkbox = \
                    self.w_tree_api_search_error.get_widget("api_search_checkbox")
                self.api_search_button = \
                    self.w_tree_api_search_error.get_widget("api_search_button")
                infobuffer = self.api_search_error_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)
                self.pylintstub = None

        def setup_signals(self):
                dic_search_error = \
                    {
                        "on_api_search_checkbox_toggled": \
                            self.__on_api_search_checkbox_toggled,
                        "on_api_search_button_clicked": \
                            self.__on_api_search_button_clicked,
                        "on_api_search_error_delete_event": \
                            self.__on_api_search_error_delete_event,
                    }
                self.w_tree_api_search_error.signal_autoconnect(
                    dic_search_error)

        def set_modal_and_transient(self, parent_window):
                gui_misc.set_modal_and_transient(self.api_search_error_dialog,
                    parent_window)

        def __on_api_search_error_delete_event(self, widget, event):
                self.__on_api_search_button_clicked(None)

        def __on_api_search_button_clicked(self, widget):
                self.api_search_error_dialog.hide()

        def __on_api_search_checkbox_toggled(self, widget):
                active = self.api_search_checkbox.get_active()

                repos = self.parent.get_current_repos_with_search_errors()
                if len(repos) > 0:
                        if active:
                                for pub, err_type, err_str in  repos:
                                        if pub not in self.gconf.not_show_repos:
                                                self.gconf.not_show_repos += pub + ","
                                        self.pylintstub = err_type
                                        self.pylintstub = err_str
                        else:
                                for pub, err_type, err_str in repos:
                                        self.gconf.not_show_repos = \
                                            self.gconf.not_show_repos.replace(
                                            pub + ",", "")
                        self.gconf.set_not_show_repos(self.gconf.not_show_repos)

        def display_search_errors(self, show_all):
                repos = self.parent.get_current_repos_with_search_errors()
                infobuffer = self.api_search_error_textview.get_buffer()
                infobuffer.set_text("")
                textiter = infobuffer.get_end_iter()
                for pub, err_type, err_str in repos:

                        if show_all or (pub not in self.gconf.not_show_repos):
                                infobuffer.insert_with_tags_by_name(textiter,
                                    "%(pub)s (%(err_type)s)\n" % {"pub": pub,
                                    "err_type": err_type}, "bold")
                                infobuffer.insert(textiter, "%s\n" % (err_str))

                self.api_search_checkbox.set_active(False)
                self.api_search_error_dialog.show()
                self.api_search_button.grab_focus()

