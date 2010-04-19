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

INFO_NOTEBOOK_LICENSE_PAGE = 3            # License Tab index

import sys
try:
        import gobject
        import pango
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc

class DetailsPanel:
        def __init__(self, w_tree_main):
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
                self.w_dependencies_textview.get_buffer().create_tag(
                    "bold", weight=pango.WEIGHT_BOLD)
                self.showing_empty_details = False

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

        def set_fetching_license(self):
                if not self.showing_empty_details:
                        licbuffer = self.w_license_textview.get_buffer()
                        leg_txt = _("Fetching legal information...")
                        licbuffer.set_text(leg_txt)

        def update_package_info(self, pkg, local_info, remote_info,
            dep_info, installed_dep_info, root, installed_icon,
            not_installed_icon, update_available_icon, is_all_publishers_installed,
            pubs_info):
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

                gui_misc.set_package_details(pkg.get_name(), local_info,
                    remote_info, self.w_generalinfo_textview,
                    installed_icon, not_installed_icon,
                    update_available_icon,
                    is_all_publishers_installed, pubs_info)
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
