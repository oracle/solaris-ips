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
# Copyright (c) 2009, 2012, Oracle and/or its affiliates. All rights reserved.
#

SPECIAL_CATEGORIES = ["locale", "plugin"] # We should cut all, but last part of the
                                          # new name scheme as part of fix for #7037.
                                          # However we need to have an exception rule
                                          # where we will cut all but three last parts.

RELEASE_URL = "http://www.opensolaris.org" # Fallback url for release notes if api
                                           # does not gave us one.

PROP_SIGNATURE_POLICY = "signature-policy"
PROP_SIGNATURE_REQUIRED_NAMES = "signature-required-names"
SIG_POLICY_IGNORE = "ignore"
SIG_POLICY_VERIFY = "verify"
SIG_POLICY_REQUIRE_SIGNATURES = "require-signatures"
SIG_POLICY_REQUIRE_NAMES = "require-names"

import gettext
import locale
import os
import sys
import traceback
import threading
try:
        import gobject
        import gnome
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.client.api_errors as api_errors
import pkg.client.api as api
import pkg.client.publisher as publisher
from pkg.gui.misc_non_gui import get_api_object as ngao
from pkg.gui.misc_non_gui import setup_logging as su_logging
from pkg.gui.misc_non_gui import shutdown_logging as sd_logging
from pkg.gui.misc_non_gui import get_version as g_version
from pkg.gui.misc_non_gui import get_os_version_and_build as g_os_version_and_build

from pkg.gui.misc_non_gui import get_log_path as ge_log_path
from pkg.gui.misc_non_gui import get_log_error_ext as ge_log_error_ext
from pkg.gui.misc_non_gui import get_log_info_ext as ge_log_info_ext
from pkg.gui.misc_non_gui import get_catalogrefresh_exception_msg as get_msg
from pkg.gui.misc_non_gui import get_um_name as get_um
from pkg.gui.misc_non_gui import is_frameworkerror as is_frameworke

from pkg.client import global_settings

misc.setlocale(locale.LC_ALL, "")
gettext.install("pkg", "/usr/share/locale")

PUBCERT_COMMON_NAME =  _("  Common Name (CN):")
PUBCERT_ORGANIZATION =  _("  Organization (O):")
PUBCERT_ORGANIZATIONAL_UNIT =  _("  Organizational Unit (OU):")

PKG_CLIENT_NAME_PM = "packagemanager"
PKG_CLIENT_NAME_WI = "packagemanager-webinstall"

logger = global_settings.logger

# Dictionary which converts old package names to current name.
package_name = { 'SUNWcs' : 'SUNWcs',
    'SUNWipkg' : 'package/pkg',
    'SUNWipkg-gui' : 'package/pkg/package-manager',
    'SUNWipkg-um' : 'package/pkg/update-manager',
    'SUNWpython26-notify' : 'library/python-2/python-notify-26' }

def set_signature_policy_names_for_textfield(widget, names):
        txt = ""
        if names != None and len(names) > 0:
                txt = names[0]
                for name in names[1:]:
                        txt += ", " + name
        widget.set_text(txt)

def fetch_signature_policy_names_from_textfield(text):
        names = []
        names = __split_ignore_comma_in_quotes(text)
        names = [x.strip(' ') for x in names]
        if len(names) == 1 and names[0] == '':
                del names[0]
        return names

def setup_signature_policy_properties(ignore, verify, req_sigs, req_names, names, orig):
        set_props = {}
        if ignore != orig[SIG_POLICY_IGNORE] and ignore:
                set_props[PROP_SIGNATURE_POLICY] = SIG_POLICY_IGNORE
        elif verify != orig[SIG_POLICY_VERIFY] and verify:
                set_props[PROP_SIGNATURE_POLICY] = SIG_POLICY_VERIFY
        elif req_sigs != orig[SIG_POLICY_REQUIRE_SIGNATURES] and req_sigs:
                set_props[PROP_SIGNATURE_POLICY] = SIG_POLICY_REQUIRE_SIGNATURES
        elif req_names != orig[SIG_POLICY_REQUIRE_NAMES] and req_names:
                set_props[PROP_SIGNATURE_POLICY] = SIG_POLICY_REQUIRE_NAMES

        if names != orig[PROP_SIGNATURE_REQUIRED_NAMES]:
                set_props[PROP_SIGNATURE_REQUIRED_NAMES] = names
        return set_props

def create_sig_policy_from_property(prop_sig_pol, prop_sig_req_names):
        names = []
        #Names with embedded commas, the default name separator, need to
        #be quoted to be treated as a single name
        if prop_sig_req_names:
                for name in prop_sig_req_names:
                        if name.split(",", 1) == 2:
                                names.append("\"%s\"" % name)
                        else:
                                names.append(name)
        sig_policy = {}
        sig_policy[SIG_POLICY_IGNORE] = False
        sig_policy[SIG_POLICY_VERIFY] = False
        sig_policy[SIG_POLICY_REQUIRE_SIGNATURES] = False
        sig_policy[SIG_POLICY_REQUIRE_NAMES] = False
        sig_policy[PROP_SIGNATURE_REQUIRED_NAMES] = []

        if prop_sig_pol == SIG_POLICY_IGNORE:
                sig_policy[SIG_POLICY_IGNORE] = True
        elif prop_sig_pol == SIG_POLICY_VERIFY:
                sig_policy[SIG_POLICY_VERIFY] = True
        elif prop_sig_pol == SIG_POLICY_REQUIRE_SIGNATURES:
                sig_policy[SIG_POLICY_REQUIRE_SIGNATURES] = True
        elif prop_sig_pol == SIG_POLICY_REQUIRE_NAMES:
                sig_policy[SIG_POLICY_REQUIRE_NAMES] = True
        sig_policy[PROP_SIGNATURE_REQUIRED_NAMES] = names
        return sig_policy

def __split_ignore_comma_in_quotes(string):
        split_char = ","
        quote = "'"
        string_split = []
        current_word = ""
        inside_quote = False
        for letter in string:
                if letter == "'" or letter == "\"":
                        quote = letter
                        current_word += letter
                        if inside_quote:
                                inside_quote = False
                        else:
                                inside_quote = True
                elif letter == split_char and not inside_quote:
                        if current_word != '':
                                string_split.append(current_word)
                        current_word = ""
                else:
                        current_word += letter
        if current_word != "" and inside_quote:
                current_word += quote
        if current_word != '':
                string_split.append(current_word)
        return string_split

def check_sig_required_names_policy(text, req_names, error_dialog_title):
        if not req_names:
                return True
        names = fetch_signature_policy_names_from_textfield(text)
        if len(names) == 0:
                error_occurred(None,
                    _("One or more certificate names must be specified "
                        "with this option."),
                    error_dialog_title,
                    gtk.MESSAGE_INFO)
                return False
        return True
                
def get_version():
        return g_version()

def get_os_version_and_build():
        return g_os_version_and_build()

def get_publishers_for_output(api_o):
        publisher_str = ""
        fmt = "\n%s\t%s\t%s (%s)"
        try:
                pref_pub = api_o.get_highest_ranked_publisher()
                for pub in api_o.get_publishers():
                        pstatus = " "
                        if pub == pref_pub:
                                # Preferred
                                pstatus = "P"
                        elif pub.disabled:
                                # Disabled
                                pstatus = "D"
                        else:
                                # Enabled, but not preferred
                                pstatus = "E"
                        r = pub.repository
                        for uri in r.origins:
                                # Origin
                                publisher_str += fmt % \
                                        (pstatus, "O", pub.prefix, uri)
                        for uri in r.mirrors:
                                # Mirror
                                publisher_str += fmt % \
                                        (pstatus, "M", pub.prefix, uri)
        except api_errors.ApiException:
                pass
        except Exception:
                pass
        return publisher_str

def get_log_path(client_name):
        return ge_log_path(client_name)

def get_log_error_ext():
        return ge_log_error_ext()

def get_log_info_ext():
        return ge_log_info_ext()

def get_pm_name():
        return PKG_CLIENT_NAME_PM

def get_wi_name():
        return PKG_CLIENT_NAME_WI

def get_um_name():
        return get_um()

def is_frameworkerror(err):
        return is_frameworke(err)

def notify_log_error(app):
        if global_settings.client_name == PKG_CLIENT_NAME_PM:
                gobject.idle_add(__notify_log_error, app,
                    _("Errors logged: click to view"))

def notify_log_warning(app):
        if global_settings.client_name == PKG_CLIENT_NAME_PM:
                gobject.idle_add(__notify_log_error, app,
                    _("Warnings logged: click to view"))

def __notify_log_error(app, msg):
        app.error_logged = True
        app.w_logalert_frame.show()
        app.w_logalert_frame.set_tooltip_text(msg)

def setup_logging():
        return su_logging(global_settings.client_name)

def shutdown_logging():
        sd_logging()
        
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
        try:
                if help_id != None:
                        gnome.help_display('package-manager', link_id=help_id)
                else:
                        gnome.help_display('package-manager')
        except gobject.GError, ex:
                msg = str(ex)
                logger.error(msg)

def add_pkgname_to_dic(dic, name, special_table):
        """Adds the original name of the package to the
        dictionary of names.
        
        'dic' is the dictionary, which holds all the names
        
        'name' is the original package name

        'special_table' table with special names. Special name is when the full name
        is part of another name. Example package/name another/package/name. package/name
        is the special name in this situation."""

        table = name.split("/")
        if len(table) == 1:
                if table[0] in dic:
                        return
                else:
                        dic[table[0]] = {}
        table.reverse()
        i = 0
        j = len(table)
        for entry in table:
                dictionary = dic.get(entry)
                if dictionary == None:
                        dic[entry] = {}
                        i += 1
                dic = dic[entry]
        if i == 0 and j > 1:
                special_table.append(name)

def __is_recursion_gr_then_one(dic):
        if not isinstance(dic, dict):
                return False
        keys = dic.keys()
        if len(keys) == 1:
                return __is_recursion_gr_then_one(dic.get(keys[0]))
        elif len(keys) > 1:
                return True
        else:
                return False

def get_minimal_unique_name(dic, name, special_table):
        name_table = name.split("/")
        len_name_table = len(name_table)
        if len_name_table == 1 and name_table[0] in dic:
                # Special case. The name doesn't contain any "/"
                return name_table[0]
        elif len_name_table == 1:
                return name
        name_table.reverse()
        max_special_level = 0
        for special_name in special_table:
                if name.endswith(special_name):
                        level = len(special_name.split("/"))
                        if level > max_special_level:
                                max_special_level = level
        for special_category in SPECIAL_CATEGORIES:
                found = False
                level = 1
                while  level < len_name_table:
                        if special_category == name_table[level - 1]:
                                found = True
                                break
                        level += 1 
                if found:
                        if level > max_special_level:
                                max_special_level = level

        if len_name_table < max_special_level:
                return name

        new_name = []
        i = 0
        for entry in name_table:
                dictionary = dic.get(entry)
                recursion = __is_recursion_gr_then_one(dictionary)
                if dictionary and recursion:
                        new_name.append(entry)
                        dic = dictionary
                        i += 1
                elif dictionary != None:
                        new_name.append(entry)
                        dic = dictionary
                        i += 1
                        if i > max_special_level:
                                break
        n = ""
        new_name.reverse()
        for part in new_name:
                n += part + "/"
        return n.strip("/")

def release_lock(lock):
        if not lock:
                return
        try:
                lock.release()
        except RuntimeError, ex:
                msg = str(ex)
                logger.error(msg)
        except Exception:
                pass

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
        except api_errors.ImageLockedError, ex:
                message = str(ex)
        except api_errors.ApiException, ex:
                message = _("An unknown error occurred") + "\n\n" + _("Error details:\n")
                message += str(ex)
        except Exception:
                traceback_lines = traceback.format_exc().splitlines()
                traceback_str = ""
                for line in traceback_lines:
                        traceback_str += line + "\n"
                message = _("An unknown error occurred")
                if traceback_str != "":
                        message += "\n\n" + _("Error details:\n") + traceback_str
        if api_o == None or message != None:
                if message == None:
                        message = _("An unknown error occurred")
                raise Exception(message)
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

def get_version_fmt_string():
        build_str = _("Build")
        return "%(version)s (" + build_str + " %(build)s-%(branch)s)"

def set_dependencies_text(textview, info, dep_info, installed_dep_info,
    installed_icon, not_installed_icon):
        names = []
        states = None
        installed_states = []
        if dep_info != None and len(dep_info.get(0)) >= 0:
                states = dep_info[0]
        if installed_dep_info != None and len(installed_dep_info.get(0)) >= 0:
                installed_states = installed_dep_info[0]
        version_fmt = get_version_fmt_string()
        for x in info.dependencies:
                if states != None and len(states) > 0:
                        name = fmri.extract_pkg_name(x)
                        found = False
                        for state in states:
                                if name ==  state.pkg_stem:
                                        version = version_fmt % \
                                            {"version": state.version,
                                            "build": state.build_release,
                                            "branch": state.branch}
                                        found = True
                                        break
                        if not found:
                                version = version_fmt % \
                                    {"version": '0',
                                     "build": '0',
                                    "branch": '0'}
                        found = False
                        for state in installed_states:
                                if name ==  state.fmri.get_name():
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

        depbuffer = textview.get_buffer()
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
        style = textview.get_style()
        font_size_in_pango_unit = style.font_desc.get_size()
        font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
        tab_array = pango.TabArray(3, True)
        header = [_("Name"), _("Dependency"), _("Installed Version")]
        max_len = [0, 0]
        for i in range(2):
                depbuffer.set_text("")
                itr = depbuffer.get_iter_at_line(0)
                depbuffer.insert_with_tags_by_name(itr, header[i], "bold")
                max_len[i] = get_textview_width(textview)

                depbuffer.set_text("")
                for one_names in names:
                        itr = depbuffer.get_iter_at_line(0)
                        depbuffer.insert(itr, one_names[i])
                        test_len = get_textview_width(textview)

                        if test_len > max_len[i]:
                                max_len[i] = test_len
                        depbuffer.set_text("")

        tab_array.set_tab(1, pango.TAB_LEFT, max_len[0] + font_size_in_pixel)
        tab_array.set_tab(2, pango.TAB_LEFT,
            max_len[0] + max_len[1] + 2 * font_size_in_pixel)

        textview.set_tabs(tab_array)

        if len(names) == 0:
                depbuffer.set_text("")
                itr = depbuffer.get_iter_at_line(0)
                depbuffer.insert_with_tags_by_name(itr, _("No dependencies"), "bold")
                return

        itr = depbuffer.get_iter_at_line(0)
        header_text = "%s\t%s\t%s\n" % (header[0], header[1], header[2])
        depbuffer.insert_with_tags_by_name(itr, header_text, "bold")
        resized_installed_icon = None
        resized_not_installed_icon = None
        i += 0
        for (name, version, installed_version, is_installed) in names:
                if is_installed:
                        if resized_installed_icon == None:
                                resized_installed_icon = resize_icon(
                                    installed_icon,
                                    font_size_in_pixel)
                        icon = resized_installed_icon
                else:
                        if resized_not_installed_icon == None:
                                resized_not_installed_icon = resize_icon(
                                    not_installed_icon,
                                    font_size_in_pixel)
                        icon = resized_not_installed_icon
                itr = depbuffer.get_iter_at_line(i + 1)
                dep_str = "%s\t%s\t" % (name, version)
                depbuffer.insert(itr, dep_str)
                end_itr = depbuffer.get_end_iter()
                depbuffer.insert_pixbuf(end_itr, icon)
                depbuffer.insert(end_itr, " %s\n" % installed_version)
                i += 1

def set_package_details(pkg_name, local_info, remote_info, textview,
    installed_icon, not_installed_icon, update_available_icon, 
    is_all_publishers_installed=None, pubs_info=None, renamed_info=None,
    pkg_renamed = False):
        installed = True
        has_remote = True 

        if not local_info:
                # Package is not installed
                local_info = remote_info
                installed = False

        if not remote_info:
                remote_info = local_info
                has_remote = False
                installed = True

        labs = {}
        labs["name"] = _("Name:")
        labs["summ"] = _("Summary:")
        labs["desc"] = _("Description:")
        labs["size"] = _("Size:")
        labs["cat"] = _("Category:")
        labs["ins"] = _("Installed:")
        labs["available"] = _("Version Available:")
        labs["renamed_to"] = _("Renamed To:")
        labs["lat"] = _("Latest Version:")
        labs["repository"] = _("Publisher:")

        summary = _("None")
        if local_info.summary:
                summary = local_info.summary
        description = ""
        if local_info.description:
                description = local_info.description

        obsolete_str = ""
        text = {}
        text["name"] = pkg_name
        text["summ"] = summary
        text["desc"] = description
        renamed_to = ""
        if renamed_info != None and \
                len(renamed_info.dependencies) > 0:
                renamed_pkgs = []
                for dep in renamed_info.dependencies:
                        if dep.startswith('pkg:/'):
                                dep_strs = dep.split('/', 1)
                                dep = dep_strs[1]
                        renamed_pkgs.append(dep)
                renamed_to += renamed_pkgs[0] + "\n"
                for dep in renamed_pkgs[1:]:
                        renamed_to += "\t" + dep + "\n"
        text["renamed_to"] = renamed_to
        if installed:
                if api.PackageInfo.OBSOLETE in local_info.states:
                        obsolete_str = _(" (Obsolete)")
                ver_text = _("%(version)s (Build %(build)s-%(branch)s)")
                text["ins"] = ver_text % \
                    {"version": local_info.version,
                    "build": local_info.build_release,
                    "branch": local_info.branch}
                text["ins"] += obsolete_str
                labs["available"] =  _("Latest Version:")
                if not same_pkg_versions(local_info, remote_info):
                        text["available"] = ver_text % \
                            {"version": remote_info.version,
                            "build": remote_info.build_release,
                            "branch": remote_info.branch}
                elif has_remote:
                        text["available"] = _("Not available from this publisher")
                else:
                        text["available"] = "No"
        else:
                if api.PackageInfo.OBSOLETE in remote_info.states:
                        obsolete_str = _(" (Obsolete)")
                text["ins"] = _("No")
                text["ins"] += obsolete_str
                labs["available"] =  _("Latest Version:")
                text["available"] = _(
                    "%(version)s (Build %(build)s-%(branch)s)") % \
                    {"version": remote_info.version,
                    "build": remote_info.build_release,
                    "branch": remote_info.branch}
        if local_info.size != 0:
                text["size"] = misc.bytes_to_str(local_info.size)
        else:
                text["size"] = "0"
        categories = _("None")
        if local_info.category_info_list:
                verbose = len(local_info.category_info_list) > 1
                categories = ""
                categories += local_info.category_info_list[0].__str__(verbose)
                if len(local_info.category_info_list) > 1:
                        for ci in local_info.category_info_list[1:]:
                                categories += ", " + ci.__str__(verbose)

        text["cat"] = categories
        pub_name = local_info.publisher
        if pubs_info != None:
                try:
                        item = pubs_info[local_info.publisher]
                except KeyError:
                        item = None
                if item:
                        alias = item[1]
                        if alias != None and len(alias) > 0:
                                pub_name = "%s (%s)" % (
                                    alias, local_info.publisher)
        text["repository"] = pub_name
        # pubs_info: dict of publisher disabled status and aliases:
        # pub_info[pub_name][0] = True disabled or False enabled
        # pub_info[pub_name][1] = Alias
        if is_all_publishers_installed and pubs_info != None:
                if local_info.publisher in pubs_info:
                        if pubs_info[local_info.publisher][0]:
                                text["repository"] = pub_name + \
                                _(" (disabled)")
                else:
                        text["repository"] = pub_name + _(" (removed)")
        set_package_details_text(labs, text, textview, installed_icon,
                not_installed_icon, update_available_icon, pkg_renamed)
        return (labs, text)

def get_scale(textview):
        scale = 1.0
        if not textview:
                return scale
        style = textview.get_style()
        font_size_in_pango_unit = style.font_desc.get_size()
        font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
        s = gtk.settings_get_default()
        dpi = s.get_property("gtk-xft-dpi") / 1024

        # AppFontSize*DPI/72 = Cairo Units
        # DefaultFont=10, Default DPI=96: 10*96/72 = 13.3 Default FontInCairoUnits
        def_font_cunits = 13.3
        app_cunits = round(font_size_in_pixel*dpi/72.0, 1)
        if app_cunits >= def_font_cunits:
                scale = round(
                    ((app_cunits - def_font_cunits)/def_font_cunits) + 1, 2)
        return scale

def get_textview_width(textview):
        infobuffer = textview.get_buffer()
        bounds = infobuffer.get_bounds()
        start = textview.get_iter_location(bounds[0])
        end = textview.get_iter_location(bounds[1])
        return end[0] - start[0]

def set_package_details_text(labs, text, textview, installed_icon,
    not_installed_icon, update_available_icon, pkg_renamed):
        style = textview.get_style()
        font_size_in_pango_unit = style.font_desc.get_size()
        font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
        tab_array = pango.TabArray(2, True)

        infobuffer = textview.get_buffer()
        infobuffer.set_text("")
        max_test_len = 0
        for lab in labs:
                __add_label_to_generalinfo(infobuffer, 0, labs[lab])
                test_len = get_textview_width(textview)
                if test_len > max_test_len:
                        max_test_len = test_len
                infobuffer.set_text("")
        tab_array.set_tab(1, pango.TAB_LEFT, max_test_len + font_size_in_pixel)
        textview.set_tabs(tab_array)
        infobuffer.set_text("")
        i = 0
        __add_line_to_generalinfo(infobuffer, i, labs["name"], text["name"])
        i += 1
        if pkg_renamed:
                i =  __add_renamed_line_to_generalinfo(infobuffer, i, labs, text)
        __add_line_to_generalinfo(infobuffer, i, labs["summ"], text["summ"])
        i += 1
        installed = False
        if text["ins"].startswith(_("No")):
                icon = not_installed_icon
        else:
                icon = installed_icon
                installed = True
        __add_line_to_generalinfo(infobuffer, i, labs["ins"],
            text["ins"], icon, font_size_in_pixel)
        i += 1
        if installed:
                if text["available"] != "No":
                        __add_line_to_generalinfo(infobuffer, i,
                            labs["available"], text["available"],
                            update_available_icon, font_size_in_pixel)
                i += 1
                if not pkg_renamed:
                        i =  __add_renamed_line_to_generalinfo(infobuffer, i,
                                 labs, text)
        else:
                __add_line_to_generalinfo(infobuffer, i,
                    labs["available"], text["available"])
                i += 1
        if text["size"] != "0":
                __add_line_to_generalinfo(infobuffer, i, labs["size"], text["size"])
                i += 1
        __add_line_to_generalinfo(infobuffer, i, labs["cat"], text["cat"])
        i += 1
        __add_line_to_generalinfo(infobuffer, i, labs["repository"],
            text["repository"])
        if len(text["desc"]) > 0:
                i += 1
                __add_label_to_generalinfo(infobuffer, i, labs["desc"] + '\n')
                i += 1
                itr = infobuffer.get_iter_at_line(i)
                infobuffer.insert(itr, text["desc"])

def set_pub_cert_details_text(labs, text, textview, added=False, reinstated=False):
        style = textview.get_style()
        font_size_in_pango_unit = style.font_desc.get_size()
        font_size_in_pixel = font_size_in_pango_unit / pango.SCALE
        tab_array = pango.TabArray(3, True)

        infobuffer = textview.get_buffer()
        infobuffer.set_text("")

        labs_issuer = {}
        labs_issuer["common_name_to"] = PUBCERT_COMMON_NAME
        labs_issuer["org_to"] = PUBCERT_ORGANIZATION
        labs_issuer["org_unit_to"] = PUBCERT_ORGANIZATIONAL_UNIT
        max_issuer_len = 0
        for lab in labs_issuer:
                __add_label_to_generalinfo(infobuffer, 0, labs_issuer[lab])
                test_len = get_textview_width(textview)
                if test_len > max_issuer_len:
                        max_issuer_len = test_len
                infobuffer.set_text("")

        max_finger_len = 0
        __add_label_to_generalinfo(infobuffer, 0, labs["fingerprints"])
        max_finger_len = get_textview_width(textview)
        infobuffer.set_text("")

        tab_array.set_tab(0, pango.TAB_LEFT, max_finger_len + font_size_in_pixel)
        tab_array.set_tab(1, pango.TAB_LEFT, max_issuer_len + font_size_in_pixel)
        textview.set_tabs(tab_array)
        infobuffer.set_text("")
        i = 0
        __add_label_to_generalinfo(infobuffer, i, labs["issued_to"] + '\n')
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["common_name_to"],
           text["common_name_to"])
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["org_to"], text["org_to"],
            bold_label=False)
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["org_unit_to"],
            text["org_unit_to"])

        i += 1
        __add_label_to_generalinfo(infobuffer, i, labs["issued_by"] + '\n')
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["common_name_by"],
            text["common_name_by"])
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["org_by"], text["org_by"])
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["org_unit_by"],
            text["org_unit_by"])

        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["validity"], "", bold_label=True)
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["issued_on"], text["issued_on"])

        i += 1
        __add_label_to_generalinfo(infobuffer, i, labs["fingerprints"] + '\n')

        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["sha1"], text["sha1"])
        i += 1
        __add_line_to_pub_cert_info(infobuffer, i, labs["md5"], text["md5"])
        i += 1
        if not added and not reinstated:
                __add_line_to_pub_cert_info(infobuffer, i, labs["ips"], text["ips"],
                    add_return=False)
        elif added and not reinstated:
                __add_label_to_generalinfo(infobuffer, i,
                    _("Note: \t Certificate is marked to be added"))
        elif not added and reinstated:
                __add_label_to_generalinfo(infobuffer, i,
                    _("Note: \t Certificate is marked to be reinstated"))

def __add_renamed_line_to_generalinfo(text_buffer, index, labs, text):
        if text["renamed_to"] != "":
                rename_list = text["renamed_to"].split("\n", 1)
                start = ""
                remainder = ""
                if rename_list != None:
                        if len(rename_list) > 0:
                                start = rename_list[0]
                        if len(rename_list) > 1:
                                remainder = rename_list[1]
                __add_line_to_generalinfo(text_buffer, index, labs["renamed_to"],
                    start)
                index += 1
                if len(remainder) > 0:
                        itr = text_buffer.get_iter_at_line(index)
                        text_buffer.insert(itr, remainder)
                        index += remainder.count("\n")
        return index

def __add_label_to_generalinfo(text_buffer, index, label):
        itr = text_buffer.get_iter_at_line(index)
        text_buffer.insert_with_tags_by_name(itr, label, "bold")

def __add_line_to_generalinfo(text_buffer, index, label, text,
    icon = None, font_size = 1):
        itr = text_buffer.get_iter_at_line(index)
        text_buffer.insert_with_tags_by_name(itr, label, "bold")
        end_itr = text_buffer.get_end_iter()
        if icon == None:
                text_buffer.insert(end_itr, "\t%s\n" % text)
        else:
                resized_icon = resize_icon(icon, font_size)
                text_buffer.insert(end_itr, "\t")
                text_buffer.get_end_iter()
                text_buffer.insert_pixbuf(end_itr, resized_icon)
                text_buffer.insert(end_itr, " %s\n" % text)

def __add_line_to_pub_cert_info(text_buffer, index, label, text,
    bold_label = False, add_return = True):
        tab_str = "\t"
        itr = text_buffer.get_iter_at_line(index)
        if bold_label:
                text_buffer.insert_with_tags_by_name(itr, label, "bold")
        else:
                text_buffer.insert_with_tags_by_name(itr, label, "normal")
        end_itr = text_buffer.get_end_iter()

        return_str = ""
        if add_return:
                return_str = "\n"

        text_buffer.insert(end_itr, tab_str)
        text_buffer.get_end_iter()
        text_buffer.insert(end_itr, (" %s" + return_str) % text)

def same_pkg_versions(info1, info2):
        if info1 == None or info2 == None:
                return False

        return info1.version == info2.version and \
                info1.build_release == info2.build_release and \
                info1.branch == info2.branch

def resize_icon(icon, font_size):
        width = icon.get_width()
        height = icon.get_height()
        return icon.scale_simple(
            (font_size * width) / height,
            font_size,
            gtk.gdk.INTERP_BILINEAR)

def get_pkg_info(app, api_o, pkg_stem, local):
        info = None
        try:
                info = api_o.info([pkg_stem], local,
                    api.PackageInfo.ALL_OPTIONS -
                    frozenset([api.PackageInfo.LICENSES]))
        except api_errors.ApiException, ex:
                err = str(ex)
                logger.error(err)
                notify_log_error(app)
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

def restart_system():
        # "init 6" performs reboot in a clean and orderly manner informing
        # the svc.startd daemon of the change in runlevel which subsequently
        # achieves the appropriate milestone and ultimately executes
        # the rc0 kill scripts.
        command = "init 6"
        return os.system(command)

def set_modal_and_transient(top_window, parent_window = None):
        if parent_window:
                top_window.set_transient_for(parent_window)
        top_window.set_modal(True)

def get_catalogrefresh_exception_msg(cre):
        return get_msg(cre)

def __get_stockbutton_label(button):
        # Gtk.Button->Gtk.Alignment->Gtk.HBox->[Gtk.Image, Gtk.Label]
        # Drill into Button widget to get Gtk.Label and set its text
        children = button.get_children()
        if len(children) == 0:
                return None
        align = children[0]
        if not align or not isinstance(align, gtk.Alignment):
                return None
        children = align.get_children()
        if len(children) == 0:
                return None
        hbox = children[0]
        if not hbox or not isinstance(hbox, gtk.HBox):
                return None
        children = hbox.get_children()
        if not (len(children) > 1):
                return None
        button_label = children[1]
        if not button_label or not isinstance(button_label, gtk.Label):
                return None
        return button_label

def get_stockbutton_label_label(button):
        button_label = __get_stockbutton_label(button)
        if button_label != None:
                return button_label.get_label()
        else:
                return None

def change_stockbutton_label(button, text):
        button_label = __get_stockbutton_label(button)
        if button_label != None:
                button_label.set_label(text)

def set_icon_for_button_and_menuitem(icon_name, button=None, menuitem=None):
        icon_source = gtk.IconSource()
        icon_source.set_icon_name(icon_name)
        icon_set = gtk.IconSet()
        icon_set.add_source(icon_source)
        if button:
                image_widget = gtk.image_new_from_icon_set(icon_set,
                    gtk.ICON_SIZE_SMALL_TOOLBAR)
                button.set_icon_widget(image_widget)
        if menuitem:
                image_widget = gtk.image_new_from_icon_set(icon_set,
                    gtk.ICON_SIZE_MENU)
                menuitem.set_image(image_widget)

def exit_if_no_threads():
        if threading.activeCount() == 1:
                if gtk.main_level() > 0:
                        gtk.main_quit()
                sys.exit(0)
        return True

def get_statusbar_label(statusbar):
        sb_frame = None
        sb_hbox = None
        sb_label = None
        children = statusbar.get_children()
        if len(children) > 0:
                sb_frame = children[0]
        if sb_frame and isinstance(sb_frame, gtk.Frame):
                children = sb_frame.get_children()
                if len(children) > 0:
                        sb_hbox = children[0] 
                        if sb_hbox and isinstance(sb_hbox, gtk.HBox):
                                children = sb_hbox.get_children()
                                if len(children) == 0:
                                        return None
                        sb_label = children[0]
                if sb_label and isinstance(sb_label, gtk.Label):
                        return sb_label
        return None

def get_origin_uri(repo):
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

def get_pkg_stem(pkg_name, pkg_pub=None):
        pkg_str = "pkg:/"
        if pkg_pub == None:
                return_str = "%s%s" % (pkg_str, pkg_name)
        else:
                return_str = "%s/%s/%s" % (pkg_str, pkg_pub, pkg_name)
        return return_str

def get_max_text_length(length_to_check, text, widget):
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

def is_a_textview( widget):
        return widget.class_path().rpartition('.')[2] == "GtkTextView"

def alias_clash(pubs, prefix, alias):
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

def setup_package_license(licenses):
        lic = ""
        lic_u = ""
        if licenses == None:
                lic_u = _("Not available")
        else:
                try:
                        for licens in licenses:
                                lic += licens.get_text()
                                lic += "\n"
                except api_errors.ApiException:
                        pass
                try:
                        lic_u = unicode(lic, "utf-8")
                except UnicodeDecodeError:
                        lic_u = _("License could not be shown "
                            "due to conversion problem.")
        return lic_u

def get_state_from_states(states):
        if api.PackageInfo.INSTALLED in states:
                pkg_state = api.PackageInfo.INSTALLED
                if api.PackageInfo.UPGRADABLE in states:
                        pkg_state = api.PackageInfo.UPGRADABLE
        else:
                pkg_state = api.PackageInfo.KNOWN

        return pkg_state
