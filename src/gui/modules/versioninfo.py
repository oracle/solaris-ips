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
        import gobject
        import pango
except ImportError:
        sys.exit(1)
import pkg.gui.misc as gui_misc

class VersionInfo:
        def __init__(self, builder, parent):
                self.parent = parent
                self.w_version_info_dialog = \
                    builder.get_object("version_info_dialog")
                self.w_info_name_label = builder.get_object("info_name")
                self.w_info_installed_label = builder.get_object(
                    "info_installed")
                self.w_info_installable_label = builder.get_object(
                    "info_installable")
                self.w_info_installable_prefix_label = builder.get_object(
                    "info_installable_label")
                self.w_info_ok_button = builder.get_object("info_ok_button")
                self.w_info_help_button = builder.get_object("info_help_button")
                self.w_info_expander = builder.get_object(
                     "version_info_expander")
                self.w_info_textview = builder.get_object("infotextview")
                infobuffer = self.w_info_textview.get_buffer()
                infobuffer.create_tag("bold", weight=pango.WEIGHT_BOLD)

        def setup_signals(self):
                signals_table = [
                    (self.w_info_ok_button, "clicked",
                     self.__on_info_ok_button_clicked),
                    (self.w_info_help_button, "clicked",
                     self.__on_info_help_button_clicked),
                    (self.w_version_info_dialog, "delete_event",
                     self.__on_version_info_dialog_delete_event)
                    ]
                for widget, signal_name, callback in signals_table:
                        widget.connect(signal_name, callback)

        def set_modal_and_transient(self, parent_window):
                gui_misc.set_modal_and_transient(self.w_version_info_dialog,
                    parent_window)

        def get_info(self, pkg_stem, name):
                api_o = self.parent.get_api_object()
                local_info = gui_misc.get_pkg_info(self.parent, api_o, pkg_stem, True)
                remote_info = gui_misc.get_pkg_info(self.parent, api_o, pkg_stem, False)
                if self.parent.check_exiting():
                        return False

                plan_pkg = None

                installed_only = False
                if local_info:
                        if gui_misc.same_pkg_versions(local_info, remote_info):
                                installed_only = True

                if not installed_only:
                        install_update_list = []
                        stuff_to_do = False
                        install_update_list.append(pkg_stem)
                        for pd in api_o.gen_plan_install(install_update_list,
                            refresh_catalogs=False):
                                continue
                        stuff_to_do = not api_o.planned_nothingtodo()
                        if stuff_to_do:
                                plan_desc = api_o.describe()
                                if plan_desc == None:
                                        return
                                plan = plan_desc.get_changes()
                                plan_pkg = None
                                for pkg_plan in plan:
                                        if name == pkg_plan[1].pkg_stem:
                                                plan_pkg = pkg_plan[1]
                                                break
                                if plan_pkg == None:
                                        return True
                gobject.idle_add(self.__after_get_info, local_info, remote_info,
                    plan_pkg, name)
                return False

        def __hide_pkg_version_details(self):
                self.w_info_expander.hide()
                self.w_version_info_dialog.set_size_request(-1, -1)


        def __after_get_info(self, local_info, remote_info, plan_pkg, name):
                if self.parent.check_exiting():
                        return
                self.w_info_name_label.set_text(name)
                installable_fmt = \
                    _("%(version)s (Build %(build)s-%(branch)s)")
                installed_label = ""
                installable_label = ""
                installable_prefix_label = _("<b>Installable Version:</b>")

                if local_info:
                        # Installed
                        installable_prefix_label = _("<b>Upgradeable Version:</b>")
                        yes_text = _("Yes, %(version)s (Build %(build)s-%(branch)s)")
                        installed_label = yes_text % \
                            {"version": local_info.version,
                            "build": local_info.build_release,
                            "branch": local_info.branch}
                        if gui_misc.same_pkg_versions(local_info, remote_info):
                                # Installed and up to date
                                installable_label = \
                                    _("Installed package is up-to-date")
                                self.__hide_pkg_version_details()
                        else:
                                if plan_pkg == None:
                                        # Installed with later version but can't upgrade
                                        # Upgradeable Version: None
                                        installable_label = _("None")
                                        self.__setup_version_info_details(name,
                                            remote_info.version,
                                            remote_info.build_release,
                                            remote_info.branch, False)
                                else:
                                        # Installed with later version and can upgrade to
                                        # Upgradeable Version: <version>
                                        # Upgradeable == Latest Version
                                        if gui_misc.same_pkg_versions(plan_pkg,
                                            remote_info):
                                                installable_label = installable_fmt % \
                                                    {"version": plan_pkg.version,
                                                    "build": plan_pkg.build_release,
                                                    "branch": plan_pkg.branch}
                                                self.__hide_pkg_version_details()
                                        else:
                                        # Installed with later version and can upgrade
                                        # Upgradeable Version: <version>
                                        # but NOT to the Latest Version
                                                installable_label = installable_fmt % \
                                                    {"version": plan_pkg.version,
                                                    "build": plan_pkg.build_release,
                                                    "branch": plan_pkg.branch}

                                                self.__setup_version_info_details(name,
                                                    remote_info.version,
                                                    remote_info.build_release,
                                                    remote_info.branch, False)
                else:
                        # Not Installed
                        installed_label = _("No")
                        if plan_pkg:
                                # Not installed with later version available to install
                                # Installable: <version>
                                # Installable == Latest Version
                                if gui_misc.same_pkg_versions(plan_pkg, remote_info):
                                        installable_label = installable_fmt % \
                                            {"version": plan_pkg.version,
                                            "build": plan_pkg.build_release,
                                            "branch": plan_pkg.branch}
                                        self.__hide_pkg_version_details()
                                else:
                                        # Not installed with later version available
                                        # Installable: <version>
                                        # but NOT to the Latest Version
                                        installable_label = installable_fmt % \
                                            {"version": plan_pkg.version,
                                            "build": plan_pkg.build_release,
                                            "branch": plan_pkg.branch}

                                        self.__setup_version_info_details(name,
                                            remote_info.version,
                                            remote_info.build_release,
                                            remote_info.branch, True)
                        else:
                                # Not Installed with later version and can't install
                                # Installable Version: None
                                installable_label = _("None")
                                self.__setup_version_info_details(name,
                                    remote_info.version,
                                    remote_info.build_release,
                                    remote_info.branch, True)

                self.w_info_installed_label.set_text(installed_label)
                self.w_info_installable_label.set_text(installable_label)
                self.w_info_installable_prefix_label.set_markup(installable_prefix_label)
                self.w_info_ok_button.grab_focus()
                self.w_version_info_dialog.show()
                self.parent.unset_busy_cursor()

        def __setup_version_info_details(self, name, version, build_release, branch,
            to_be_installed):
                installable_fmt = \
                    _("%(version)s (Build %(build)s-%(branch)s)")
                if to_be_installed:
                        expander_fmt = _(
                            "The latest version of %s cannot be installed."
                            )
                else:
                        expander_fmt = _(
                            "Cannot upgrade to the latest version of %s."
                            )
                installable_exp = installable_fmt % \
                    {"version": version,
                    "build": build_release,
                    "branch": branch}
                expander_text = installable_exp + "\n\n"
                expander_text += expander_fmt % name

                # Ensure we have enough room for the Details message
                # without requiring a scrollbar
                self.w_info_textview.set_size_request(484, 95)
                self.w_info_expander.set_expanded(True)
                self.w_info_expander.show()

                details_buff = self.w_info_textview.get_buffer()
                details_buff.set_text("")
                itr = details_buff.get_iter_at_line(0)
                details_buff.insert_with_tags_by_name(itr,
                    _("Latest Version: "), "bold")
                details_buff.insert(itr, expander_text)

        def __on_info_ok_button_clicked(self, widget):
                self.w_version_info_dialog.hide()

        @staticmethod
        def __on_info_help_button_clicked(widget):
                gui_misc.display_help("package-version")

        def __on_version_info_dialog_delete_event(self, widget, event):
                self.__on_info_ok_button_clicked(None)
                return True


