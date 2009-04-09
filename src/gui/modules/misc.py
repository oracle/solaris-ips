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

SPECIAL_CATEGORIES = ["locale", "plugin"] # We should cut all, but last part of the
                                          # new name scheme as part of fix for #7037.
                                          # However we need to have an exception rule
                                          # where we will cut all but three last parts.

import os
import sys
try:
        import gobject
        import gnome
        import gtk
except ImportError:
        sys.exit(1)

def get_client_api_version():
        return 12 # CLIENT_API_VERSION Used by PM, UM and WebInstall

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
def display_help(application_dir="", id=None):
                props = { gnome.PARAM_APP_DATADIR : application_dir + \
                            '/usr/share/package-manager/help' }
                gnome.program_init('package-manager', '0.1', properties=props)
                if id != None:
                        gnome.help_display('package-manager', link_id=id)
                else:
                        gnome.help_display('package-manager')

def get_pkg_name(pkg_name):
        index = -1
        try:
                index = pkg_name.rindex("/")
        except ValueError:
                # Package Name without "/"
                return pkg_name
        pkg_name_bk = pkg_name
        test_name = pkg_name[index:]
        pkg_name = pkg_name[:index]
        try:
                index = pkg_name.rindex("/")
        except ValueError:
                # Package Name with only one "/"
                return pkg_name_bk
        if pkg_name[index:].strip("/") not in SPECIAL_CATEGORIES:
                return test_name.strip("/")
        else:
                # The package name contains special category
                converted_name = pkg_name[index:] + test_name
                pkg_name = pkg_name[:index]
                try:
                        index = pkg_name.rindex("/")
                except ValueError:
                        # Only three parts "part1/special/part2"
                        return pkg_name + converted_name
                return pkg_name[index:].strip("/") + converted_name
        return pkg_name_bk

