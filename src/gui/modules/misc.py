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

import cPickle
import os
import sys
try:
        import gobject
        import gnome
        import gtk
except ImportError:
        sys.exit(1)
import pkg.client.api_errors as api_errors
import pkg.client.api as api

from pkg.client import global_settings

#The current version of the Client API the PM, UM and
#WebInstall GUIs have been tested against and are known to work with.
CLIENT_API_VERSION = 15

def get_app_pixbuf(application_dir, icon_name):
        return get_pixbuf_from_path(os.path.join(application_dir,
            "usr/share/package-manager"), icon_name)

def get_icon_pixbuf(application_dir, icon_name):
        return get_pixbuf_from_path(os.path.join(application_dir,
            "usr/share/icons/package-manager"), icon_name)

def get_pixbuf_from_path(path, icon_name):
        icon = icon_name.replace(' ', '_')

        # Performance: Faster to check if files exist rather than catching
        # exceptions when they do not. Picked up open failures using dtrace
        png_path = os.path.join(path, icon + ".png")
        png_exists = os.path.exists(png_path)
        svg_path = os.path.join(path, icon + ".png")
        svg_exists = os.path.exists(png_path)

        if not png_exists and not svg_exists:
                return None
        try:
                return gtk.gdk.pixbuf_new_from_file(png_path)
        except gobject.GError:
                try:
                        return gtk.gdk.pixbuf_new_from_file(svg_path)
                except gobject.GError:
                        return None

def get_icon(icon_theme, name, size=16):
        try:
                return icon_theme.load_icon(name, size, 0)
        except gobject.GError:
                return None

def init_for_help(application_dir="/"):
        props = { gnome.PARAM_APP_DATADIR : os.path.join(application_dir,
                    'usr/share/package-manager/help') }
        gnome.program_init('package-manager', '0.1', properties=props)

def display_help(help_id=None):
        if help_id != None:
                gnome.help_display('package-manager', link_id=help_id)
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

def get_cache_dir(api_object):
        img = api_object.img
        cache_dir = os.path.join(img.imgdir, "gui_cache")
        try:
                __mkdir(cache_dir)
        except OSError:
                cache_dir = None
        return cache_dir

def __mkdir(directory_path):
        if not os.path.isdir(directory_path):
                os.makedirs(directory_path)

def get_api_object(img_dir, progtrack, parent_dialog):
        api_o = None
        message = None
        try:
                api_o = api.ImageInterface(img_dir,
                    CLIENT_API_VERSION,
                    progtrack, None, global_settings.client_name)
        except api_errors.VersionException, ex:
                message = _("Version mismatch: expected version %d, got version %d") % \
                    (ex.expected_version, ex.received_version)
        except api_errors.ImageNotFoundException, ex:
                message = _("%s is not an install image") % ex.user_dir
        if message != None:
                if parent_dialog != None:
                        error_occurred(parent_dialog,
                            message, _("API Error"))
                        sys.exit(0)
                else:
                        print message
        return api_o

def read_cache_file(file_path):
        fh = open(file_path, 'r')
        data = cPickle.load(fh)
        fh.close()
        return data

def dump_cache_file(file_path, data):
        fh = open(file_path,"w")
        cPickle.dump(data, fh, True)
        fh.close()

def error_occurred(parent, error_msg, msg_title = None,
    msg_type=gtk.MESSAGE_ERROR, use_markup = False):
        msgbox = gtk.MessageDialog(parent =
            parent,
            buttons = gtk.BUTTONS_CLOSE,
            flags = gtk.DIALOG_MODAL,
            type = msg_type,
            message_format = None)
        if use_markup:
                msgbox.set_markup(error_msg)
        else:
                msgbox.set_property('text', error_msg)
        if msg_title != None:
                title = msg_title
        else:
                title = _("Error")

        msgbox.set_title(title)
        msgbox.run()
        msgbox.destroy()
