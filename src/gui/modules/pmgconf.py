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
        import gconf
        from glib import GError
except ImportError:
        sys.exit(1)

PACKAGEMANAGER_PREFERENCES = "/apps/packagemanager/preferences"
MAX_SEARCH_COMPLETION_PREFERENCES = \
        "/apps/packagemanager/preferences/max_search_completion"
INITIAL_APP_WIDTH_PREFERENCES = "/apps/packagemanager/preferences/initial_app_width"
INITIAL_APP_HEIGHT_PREFERENCES = "/apps/packagemanager/preferences/initial_app_height"
INITIAL_APP_HPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_hposition"
INITIAL_APP_VPOS_PREFERENCES = "/apps/packagemanager/preferences/initial_app_vposition"
INITIAL_SHOW_FILTER_PREFERENCES = "/apps/packagemanager/preferences/initial_show_filter"
INITIAL_SECTION_PREFERENCES = "/apps/packagemanager/preferences/initial_section"
LAST_EXPORT_SELECTION_PATH = \
        "/apps/packagemanager/preferences/last_export_selections_path"
SHOW_STARTPAGE_PREFERENCES = "/apps/packagemanager/preferences/show_startpage"
SHOW_IMAGE_UPDATE_CONFIRMATION = "/apps/packagemanager/preferences/imageupdate_confirm"
SHOW_INSTALL_CONFIRMATION = "/apps/packagemanager/preferences/install_confirm"
SHOW_REMOVE_CONFIRMATION = "/apps/packagemanager/preferences/remove_confirm"
SAVE_STATE_PREFERENCES = "/apps/packagemanager/preferences/save_state"
START_INSEARCH_PREFERENCES = "/apps/packagemanager/preferences/start_insearch"
LASTSOURCE_PREFERENCES = "/apps/packagemanager/preferences/lastsource"
API_SEARCH_ERROR_PREFERENCES = "/apps/packagemanager/preferences/api_search_error"
DETAILS_EXPANDED_PREFERENCES = "/apps/packagemanager/preferences/details_expanded"

class PMGConf:
        def __init__(self):
                self.client = gconf.client_get_default()
                try:
                        self.max_search_completion = \
                            self.client.get_int(MAX_SEARCH_COMPLETION_PREFERENCES)
                        self.initial_show_filter = \
                            self.client.get_int(INITIAL_SHOW_FILTER_PREFERENCES)
                        self.initial_section = \
                            self.client.get_int(INITIAL_SECTION_PREFERENCES)
                        self.last_export_selection_path = \
                            self.client.get_string(LAST_EXPORT_SELECTION_PATH)
                        self.show_startpage = \
                            self.client.get_bool(SHOW_STARTPAGE_PREFERENCES)
                        self.save_state = \
                            self.client.get_bool(SAVE_STATE_PREFERENCES)
                        self.show_image_update = \
                            self.client.get_bool(SHOW_IMAGE_UPDATE_CONFIRMATION)
                        self.show_install = \
                            self.client.get_bool(SHOW_INSTALL_CONFIRMATION)
                        self.show_remove = \
                            self.client.get_bool(SHOW_REMOVE_CONFIRMATION)
                        self.start_insearch = \
                            self.client.get_bool(START_INSEARCH_PREFERENCES)
                        self.lastsource = \
                            self.client.get_string(LASTSOURCE_PREFERENCES)
                        self.not_show_repos = \
                            self.client.get_string(API_SEARCH_ERROR_PREFERENCES)
                        self.initial_app_width = \
                            self.client.get_int(INITIAL_APP_WIDTH_PREFERENCES)
                        self.initial_app_height = \
                            self.client.get_int(INITIAL_APP_HEIGHT_PREFERENCES)
                        self.initial_app_hpos = \
                            self.client.get_int(INITIAL_APP_HPOS_PREFERENCES)
                        self.initial_app_vpos = \
                            self.client.get_int(INITIAL_APP_VPOS_PREFERENCES)
                        self.client.add_dir(PACKAGEMANAGER_PREFERENCES,
                            gconf.CLIENT_PRELOAD_NONE)
                        self.client.notify_add(SHOW_IMAGE_UPDATE_CONFIRMATION,
                            self.__show_image_update_changed)
                        self.client.notify_add(SHOW_INSTALL_CONFIRMATION,
                            self.__show_install_changed)
                        self.client.notify_add(SHOW_REMOVE_CONFIRMATION,
                            self.__show_remove_changed)
                        self.client.notify_add(SAVE_STATE_PREFERENCES,
                            self.__save_state_changed)
                        self.details_expanded = \
                            self.client.get_bool(DETAILS_EXPANDED_PREFERENCES)
                except GError:
                        # Default values - the same as in the
                        # packagemanager-preferences.schemas
                        self.max_search_completion = 20
                        self.initial_show_filter = 0
                        self.initial_section = 2
                        self.last_export_selection_path = ""
                        self.show_startpage = True
                        self.show_image_update = True
                        self.show_install = True
                        self.show_remove = True
                        self.save_state = True
                        self.start_insearch = True
                        self.lastsource = ""
                        self.not_show_repos = ""
                        self.initial_app_width = 800
                        self.initial_app_height = 600
                        self.initial_app_hpos = 200
                        self.initial_app_vpos = 320
                        self.details_expanded = True
                self.__fix_initial_values()

        def __fix_initial_values(self):
                if self.initial_app_width == -1:
                        self.initial_app_width = 800
                if self.initial_app_height == -1:
                        self.initial_app_height = 600
                if self.initial_app_hpos == -1:
                        self.initial_app_hpos = 200
                if self.initial_app_vpos == -1:
                        self.initial_app_vpos = 320

                if not self.not_show_repos:
                        self.not_show_repos = ""

        def set_lastsource(self, value):
                try:
                        self.lastsource = value
                        self.client.set_string(LASTSOURCE_PREFERENCES, value)
                except GError:
                        pass

        def set_details_expanded(self, value):
                try:
                        self.details_expanded = value
                        self.client.set_bool(DETAILS_EXPANDED_PREFERENCES, value)
                except GError:
                        pass

        def set_start_insearch(self, value):
                try:
                        self.start_insearch = value
                        self.client.set_bool(START_INSEARCH_PREFERENCES, value)
                except GError:
                        pass

        def set_show_startpage(self, value):
                try:
                        self.show_startpage = value
                        self.client.set_bool(SHOW_STARTPAGE_PREFERENCES, value)
                except GError:
                        pass

        def set_save_state(self, value):
                try:
                        self.save_state = value
                        self.client.set_bool(SAVE_STATE_PREFERENCES, value)
                except GError:
                        pass

        def set_show_image_update(self, value):
                try:
                        self.show_image_update = value
                        self.client.set_bool(SHOW_IMAGE_UPDATE_CONFIRMATION, value)
                except GError:
                        pass

        def set_show_install(self, value):
                try:
                        self.show_install = value
                        self.client.set_bool(SHOW_INSTALL_CONFIRMATION, value)
                except GError:
                        pass

        def set_show_remove(self, value):
                try:
                        self.show_remove = value
                        self.client.set_bool(SHOW_REMOVE_CONFIRMATION, value)
                except GError:
                        pass

        def set_not_show_repos(self, value):
                try:
                        self.client.set_string(API_SEARCH_ERROR_PREFERENCES, value)
                except GError:
                        pass

        def save_values(self, pub, start_insearch, width, height, hpos, vpos):
                try:    
                        if self.last_export_selection_path:
                                self.client.set_string(LAST_EXPORT_SELECTION_PATH,
                                    self.last_export_selection_path)
                        self.client.set_string(LASTSOURCE_PREFERENCES, pub)
                        self.client.set_bool(START_INSEARCH_PREFERENCES,
                            start_insearch)
                        self.client.set_int(INITIAL_APP_WIDTH_PREFERENCES, width)
                        self.client.set_int(INITIAL_APP_HEIGHT_PREFERENCES, height)
                        self.client.set_int(INITIAL_APP_HPOS_PREFERENCES, hpos)
                        self.client.set_int(INITIAL_APP_VPOS_PREFERENCES, vpos)
                except GError:
                        pass


        def __save_state_changed(self, client, connection_id, entry, arguments):
                self.save_state = entry.get_value().get_bool()

        def __show_image_update_changed(self, client, connection_id, entry, arguments):
                self.show_image_update = entry.get_value().get_bool()

        def __show_install_changed(self, client, connection_id, entry, arguments):
                self.show_install = entry.get_value().get_bool()

        def __show_remove_changed(self, client, connection_id, entry, arguments):
                self.show_remove = entry.get_value().get_bool()
