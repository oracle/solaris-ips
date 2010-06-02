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

import sys
try:
        import gobject
        import gtk
        import pango
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc
import pkg.gui.enumerations as enumerations
import pkg.version as version
import pkg.client.api as api

class DetailsPanel:
        def __init__(self, parent, w_tree_main):
                self.parent = parent
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
                self.w_versions_name_label = \
                    w_tree_main.get_widget("versions_name_label")
                self.w_versions_label = \
                    w_tree_main.get_widget("versions_label")
                self.w_versions_combobox = \
                    w_tree_main.get_widget("versions_combo")
                self.w_versions_install_button = \
                    w_tree_main.get_widget("versions_install_button")
                self.w_dependencies_textview.get_buffer().create_tag(
                    "bold", weight=pango.WEIGHT_BOLD)
                self.showing_empty_details = False
                self.versions_list = None
                self.__init_versions_tree_view()

                try:
                        dic_versions = \
                            {
                                "on_versions_install_button_clicked": \
                                    self.__on_versions_install_button_clicked,
                            }
                        w_tree_main.signal_autoconnect(dic_versions)
                except AttributeError, error:
                        print _(
                            "GUI will not respond to any event! %s. "
                            "Check declare_signals()") \
                            % error

        def __init_versions_tree_view(self):
                cell = gtk.CellRendererText()
                self.w_versions_combobox.pack_start(cell, True)
                self.w_versions_combobox.add_attribute(cell, 'text',
                    enumerations.VERSION_DISPLAY_NAME)

        def __on_versions_install_button_clicked(self, widget):
                active = self.w_versions_combobox.get_active()
                active_version = self.versions_list[active][enumerations.VERSION_NAME]
                self.parent.install_version(active_version)

        def setup_text_signals(self, has_selection_cb, focus_in_cb,
            focus_out_cb):
                self.w_generalinfo_textview.get_buffer().connect(
                    "notify::has-selection", has_selection_cb)
                self.w_installedfiles_textview.get_buffer().connect(
                    "notify::has-selection", has_selection_cb)
                self.w_dependencies_textview.get_buffer().connect(
                    "notify::has-selection", has_selection_cb)
                self.w_license_textview.get_buffer().connect(
                    "notify::has-selection", has_selection_cb)
                self.w_generalinfo_textview.connect(
                    "focus-in-event", focus_in_cb)
                self.w_installedfiles_textview.connect(
                    "focus-in-event", focus_in_cb)
                self.w_dependencies_textview.connect(
                    "focus-in-event", focus_in_cb)
                self.w_license_textview.connect(
                    "focus-in-event", focus_in_cb)
                self.w_generalinfo_textview.connect(
                    "focus-out-event", focus_out_cb)
                self.w_installedfiles_textview.connect(
                    "focus-out-event", focus_out_cb)
                self.w_dependencies_textview.connect(
                    "focus-out-event", focus_out_cb)
                self.w_license_textview.connect(
                    "focus-out-event", focus_out_cb)

        def process_selected_package(self, selected_pkgstem):
                gobject.idle_add(self.__show_fetching_package_info)
                self.showing_empty_details = False

        def __show_fetching_package_info(self):
                instbuffer = self.w_installedfiles_textview.get_buffer()
                depbuffer = self.w_dependencies_textview.get_buffer()
                infobuffer = self.w_generalinfo_textview.get_buffer()
                fetching_text = _("Fetching information...")
                instbuffer.set_text(fetching_text)
                depbuffer.set_text(fetching_text)
                infobuffer.set_text(fetching_text)

        def set_empty_details(self):
                self.showing_empty_details = True
                self.w_installedfiles_textview.get_buffer().set_text("")
                self.w_dependencies_textview.get_buffer().set_text("")
                self.w_generalinfo_textview.get_buffer().set_text("")
                self.w_license_textview.get_buffer().set_text("")

                self.versions_list = None
                self.w_versions_name_label.set_text("")
                self.w_versions_label.set_text("")
                self.w_versions_install_button.set_sensitive(False)
                self.__set_empty_versions_combo()

        def __set_empty_versions_combo(self):
                empty_versions_list = self.__get_new_versions_liststore()
                empty_versions_list.append([0, "", "", 0])
                self.w_versions_combobox.set_model(empty_versions_list)
                self.w_versions_combobox.set_active(0)

        def set_fetching_license(self):
                if not self.showing_empty_details:
                        licbuffer = self.w_license_textview.get_buffer()
                        leg_txt = _("Fetching legal information...")
                        licbuffer.set_text(leg_txt)

        def set_fetching_versions(self):
                if self.showing_empty_details or self.parent.selected_pkg_name == None:
                        return
                self.w_versions_name_label.set_text(self.parent.selected_pkg_name)
                fetching_text = _("Fetching information...")
                self.w_versions_label.set_text(fetching_text)
                self.w_versions_install_button.set_sensitive(False)
                self.__set_empty_versions_combo()

        def update_package_info(self, pkg_name, local_info, remote_info,
            dep_info, installed_dep_info, root, installed_icon,
            not_installed_icon, update_available_icon, is_all_publishers_installed,
            pubs_info, renamed_info=None):
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

                gui_misc.set_package_details(pkg_name, local_info,
                    remote_info, self.w_generalinfo_textview,
                    installed_icon, not_installed_icon,
                    update_available_icon,
                    is_all_publishers_installed, pubs_info, renamed_info)
                if not local_info:
                        # Package is not installed
                        local_info = remote_info

                if not remote_info:
                        remote_info = local_info

                inst_str = ""
                if local_info.dirs:
                        for x in local_info.dirs:
                                inst_str += ''.join("%s%s\n" % (
                                    root, x))
                if local_info.files:
                        for x in local_info.files:
                                inst_str += ''.join("%s%s\n" % (
                                    root, x))
                if local_info.hardlinks:
                        for x in local_info.hardlinks:
                                inst_str += ''.join("%s%s\n" % (
                                    root, x))
                if local_info.links:
                        for x in local_info.links:
                                inst_str += ''.join("%s%s\n" % (
                                    root, x))
                self.__set_installedfiles_text(inst_str)
                self.__set_dependencies_text(local_info, dep_info,
                    installed_dep_info, installed_icon, not_installed_icon)

        def __set_installedfiles_text(self, text):
                instbuffer = self.w_installedfiles_textview.get_buffer()
                instbuffer.set_text("")
                itr = instbuffer.get_start_iter()
                instbuffer.insert(itr, text)

        def __set_dependencies_text(self, info, dep_info, installed_dep_info,
            installed_icon, not_installed_icon):
                gui_misc.set_dependencies_text(self.w_dependencies_textview,
                    info, dep_info, installed_dep_info, installed_icon,
                    not_installed_icon)

        def update_package_license(self, licenses):
                if self.showing_empty_details:
                        return
                licbuffer = self.w_license_textview.get_buffer()
                licbuffer.set_text(gui_misc.setup_package_license(licenses))

        def update_package_versions(self, versions):
                if self.showing_empty_details:
                        return

                self.versions_list = self.__get_new_versions_liststore()
                i = 0
                previous_display_version = None
                self.w_versions_label.set_text(_("Not Installed"))
                for (version_str, states) in versions:
                        state = gui_misc.get_state_from_states(states)
                        
                        version_tuple = version.Version.split(version_str)
                        version_fmt = gui_misc.get_version_fmt_string()
                        display_version = version_fmt % \
                            {"version": version_tuple[0][0],
                            "build": version_tuple[0][1],
                            "branch": version_tuple[0][2]}
                        if api.PackageInfo.INSTALLED in states:
                                self.w_versions_label.set_text(display_version)
                                break
                        if (previous_display_version and
                            previous_display_version == display_version):
                                continue
                        previous_display_version = display_version
                        self.versions_list.append([i, display_version,
                            version_str, state])
                        i += 1
                if i > 0:
                        self.w_versions_install_button.set_sensitive(True)
                else:
                        self.versions_list.clear()
                        self.versions_list.append([0, _("No versions available"), "", 0])
                        self.w_versions_install_button.set_sensitive(False)
                self.w_versions_combobox.set_model(self.versions_list)
                self.w_versions_combobox.set_active(0)

        @staticmethod
        def __get_new_versions_liststore():
                return gtk.ListStore(
                        gobject.TYPE_INT,         # enumerations.VERSION_ID
                        gobject.TYPE_STRING,      # enumerations.VERSION_DISPLAY_NAME
                        gobject.TYPE_STRING,      # enumerations.VERSION_NAME
                        gobject.TYPE_INT,         # enumerations.VERSION_STATUS
                        )
