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
except ImportError:
        sys.exit(1)
import pkg.gui.enumerations as enumerations

SEARCH_TXT_GREY_STYLE = "#757575" #Close to DimGrey
SEARCH_TXT_BLACK_STYLE = "#000000"

class EntryStyle:
        def __init__(self, entry):
                self.search_txt_fg_style = gtk.gdk.color_parse(SEARCH_TXT_BLACK_STYLE)
                self.entry = entry
                self.entry_embedded_icons_supported = True
                try:
                        self.entry.set_property("secondary-icon-stock", None)
                except TypeError:
                        self.entry_embedded_icons_supported = False
                self.search_text_style = -1
                self.set_search_text_mode(enumerations.SEARCH_STYLE_PROMPT)

        def set_theme_colour(self, page_fg):
                self.search_txt_fg_style = page_fg
                if self.get_text() != None:
                        self.set_search_text_mode(enumerations.SEARCH_STYLE_NORMAL)
                else:
                        self.set_entry_to_prompt()

        def set_search_text_mode(self, style):
                if style == enumerations.SEARCH_STYLE_NORMAL:
                        self.entry.modify_text(gtk.STATE_NORMAL, self.search_txt_fg_style)
                        if self.search_text_style == enumerations.SEARCH_STYLE_PROMPT or\
                                self.entry.get_text() == _("Search (Ctrl-F)"):
                                self.entry.set_text("")
                        self.search_text_style = enumerations.SEARCH_STYLE_NORMAL

                else:
                        self.entry.modify_text(gtk.STATE_NORMAL,
                                gtk.gdk.color_parse(SEARCH_TXT_GREY_STYLE))
                        self.search_text_style = enumerations.SEARCH_STYLE_PROMPT
                        self.entry.set_text(_("Search (Ctrl-F)"))

        def on_entry_changed(self, widget):
                if widget.get_text_length() > 0 and \
                        self.search_text_style != enumerations.SEARCH_STYLE_PROMPT:
                        if self.entry_embedded_icons_supported:
                                self.entry.set_property("secondary-icon-stock",
                                    gtk.STOCK_CANCEL)
                                self.entry.set_property(
                                   "secondary-icon-sensitive", True)
                        return True
                else:
                        if self.entry_embedded_icons_supported:
                                self.entry.set_property("secondary-icon-stock",
                                    None)
                        return False

        def set_entry_to_prompt(self):
                if self.search_text_style !=  enumerations.SEARCH_STYLE_PROMPT:
                        self.set_search_text_mode(enumerations.SEARCH_STYLE_PROMPT)

        def get_text(self):
                if self.search_text_style == enumerations.SEARCH_STYLE_PROMPT or \
                        self.entry.get_text_length() == 0:
                        return None

                txt = self.entry.get_text()
                if len(txt.strip()) == 0:
                        self.entry.set_text("")
                        return None
                return txt

