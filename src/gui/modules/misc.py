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

import os
import sys
try:
        import gobject
        import gtk
except ImportError:
        sys.exit(1)

def get_app_pixbuf(application_dir, icon_name):
        return get_pixbuf_from_path(application_dir +
            "/usr/share/package-manager/", icon_name)

def get_icon_pixbuf(application_dir, icon_name):
        return get_pixbuf_from_path(application_dir +
            "/usr/share/icons/package-manager/", icon_name)

def get_pixbuf_from_path(path, icon_name):
        icon = icon_name.replace(' ', '_')

        # Performance: Faster to check if files exist rather than catching
        # exceptions when they do not. Picked up open failures using dtrace
        png_exists = os.path.exists(path + icon + ".png")
        svg_exists = os.path.exists(path + icon + ".svg")

        if not png_exists and not svg_exists:
                return None
        try:
                return gtk.gdk.pixbuf_new_from_file(path + icon + ".png")
        except gobject.GError:
                try:
                        return gtk.gdk.pixbuf_new_from_file(path + icon + ".png")
                except gobject.GError:
                        iconview = gtk.IconView()
                        icon = iconview.render_icon(getattr(gtk,
                            "STOCK_MISSING_IMAGE"),
                            size = gtk.ICON_SIZE_MENU,
                            detail = None)
                        # XXX Could return image-we don't want to show ugly icon.
                        return None
