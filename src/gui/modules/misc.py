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
        import pango
except ImportError:
        sys.exit(1)
import pkg.misc as misc
import pkg.client.api_errors as api_errors
import pkg.client.api as api
from pkg.gui.misc_non_gui import get_api_object as ngao

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

def get_api_object(img_dir, progtrack, parent_dialog):
        api_o = None
        message = None
        try:
                api_o = ngao(img_dir, progtrack)
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

def set_package_details(pkg_name, local_info, remote_info, textview,
    installed_icon, not_installed_icon, update_available_icon):
        installed = True

        if not local_info:
                # Package is not installed
                local_info = remote_info
                installed = False

        if not remote_info:
                remote_info = local_info
                installed = True

        labs = {}
        labs["name"] = _("Name:")
        labs["desc"] = _("Description:")
        labs["size"] = _("Size:")
        labs["cat"] = _("Category:")
        labs["ins"] = _("Installed:")
        labs["available"] = _("Version Available:")
        labs["lat"] = _("Latest Version:")
        labs["repository"] = _("Publisher:")

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
        categories = _("None")
        if local_info.category_info_list:
                verbose = len(local_info.category_info_list) > 1
                categories = ""
                categories += local_info.category_info_list[0].__str__(verbose)
                if len(local_info.category_info_list) > 1:
                        for ci in local_info.category_info_list[1:]:
                                categories += ", " + ci.__str__(verbose)

        text["cat"] = categories
        text["repository"] = local_info.publisher
        set_package_details_text(labs, text, textview, installed_icon,
                not_installed_icon, update_available_icon)
        return (labs, text)


def set_package_details_text(labs, text, textview, installed_icon,
    not_installed_icon, update_available_icon):
        max_len = 0
        for lab in labs:
                if len(labs[lab]) > max_len:
                        max_len = len(labs[lab])

        style = textview.get_style()
        font_size_in_pango_unit = style.font_desc.get_size()
        font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
        tab_array = pango.TabArray(2, True)
        tab_array.set_tab(1, pango.TAB_LEFT, max_len * font_size_in_pixel)
        textview.set_tabs(tab_array)

        infobuffer = textview.get_buffer()
        infobuffer.set_text("")
        i = 0
        __add_line_to_generalinfo(infobuffer, i, labs["name"], text["name"])
        i += 1
        __add_line_to_generalinfo(infobuffer, i, labs["desc"], text["desc"])
        i += 1
        installed = False
        if text["ins"] == _("No"):
                icon = not_installed_icon
        else:
                icon = installed_icon
                installed = True
        __add_line_to_generalinfo(infobuffer, i, labs["ins"],
            text["ins"], icon, font_size_in_pixel)
        i += 1
        if installed and text["available"] != _("No"):
                __add_line_to_generalinfo(infobuffer, i,
                    labs["available"], text["available"],
                    update_available_icon, font_size_in_pixel)
        else:
                __add_line_to_generalinfo(infobuffer, i,
                    labs["available"], text["available"])
        i += 1
        __add_line_to_generalinfo(infobuffer, i, labs["size"], text["size"])
        i += 1
        __add_line_to_generalinfo(infobuffer, i, labs["cat"], text["cat"])
        i += 1
        __add_line_to_generalinfo(infobuffer, i, labs["repository"],
            text["repository"])

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

def get_pkg_info(api_o, pkg_stem, local):
        info = None
        try:
                info = api_o.info([pkg_stem], local,
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
