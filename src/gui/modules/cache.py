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

import cPickle
import time
import os
import pkg.catalog as catalog
import pkg.gui.enumerations as enumerations
import pkg.gui.misc as gui_misc

CACHE_VERSION=6
INDEX_HASH_LENGTH=41

class CacheListStores:
        def __init__(self, application_dir, api_o):
                self.api_o = api_o
                self.update_available_icon = gui_misc.get_icon_pixbuf(application_dir, "status_newupdate")
                self.installed_icon = gui_misc.get_icon_pixbuf(application_dir, "status_installed")
                self.category_icon = gui_misc.get_pixbuf_from_path(application_dir +
                    "/usr/share/package-manager/", "legend_newupdate")

        def check_if_cache_uptodate(self, publisher):
                try:
                        info = self.__load_cache_info(publisher)
                        if info:
                                if info.get("version") != CACHE_VERSION:
                                        return False
                                image_last_modified = \
                                    self.__get_publisher_timestamp(publisher)
                                cache_last_modified = info.get("date")
                                if not cache_last_modified or \
                                    cache_last_modified != image_last_modified:
                                        return False
                                cache_index_hash = info.get("index_hash")
                                file_index_hash = self.__get_index_hash()
                                if not cache_index_hash or \
                                    cache_index_hash != file_index_hash:
                                        return False
                        else:
                                return False
                except IOError:
                        return False
                return True

        def __get_cache_dir(self):
                img = self.api_o.img
                cache_dir = "%s/gui_cache/" % (img.imgdir)
                try:
                        self.__mkdir(cache_dir)
                except OSError:
                        cache_dir = None
                return cache_dir

        def __mkdir(self, directory_path):
                if not os.path.isdir(directory_path):
                        os.makedirs(directory_path)

        def __get_index_hash(self):
                img = self.api_o.img
                index_path = "%s/state/installed" % (img.imgdir)
                try:
                        return os.path.getmtime(index_path)
                except (OSError, IOError):
                        return None

        def __get_publisher_timestamp(self, publisher):
                dt = self.api_o.get_publisher_last_update_time(prefix=publisher)
                if dt:
                        return dt.ctime()
                return dt

        def dump_datamodels(self, publisher, application_list, category_list, 
            section_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                dump_info = {}
                dump_info["version"] = CACHE_VERSION
                dump_info["date"] = self.__get_publisher_timestamp(publisher)
                dump_info["publisher"] = publisher
                dump_info["index_hash"] = self.__get_index_hash()
                try:
                        self.__dump_cache_file(cache_dir + publisher+".cpl", dump_info)
                        self.__dump_category_list(publisher, category_list)
                        self.__dump_application_list(publisher, application_list)
                        self.__dump_section_list(publisher, section_list)
                except IOError:
                        #Silently return, as probably user doesn't have permissions or
                        #other error which simply doesn't affect the GUI work
                        return

        def __dump_category_list(self, publisher, category_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                categories = []
                for category in category_list:
                        cat = {}
                        cat["id"] = category[enumerations.CATEGORY_ID]
                        cat["name"] = category[enumerations.CATEGORY_NAME]
                        cat["description"] = category[enumerations.CATEGORY_DESCRIPTION]
                        # Can't store pixbuf :(
                        # cat["icon"] = category[enumerations.CATEGORY_ICON]
                        cat["iconvisible"] = category[enumerations.CATEGORY_ICON_VISIBLE]
                        cat["visible"] = category[enumerations.CATEGORY_VISIBLE]
                        cat["section_list"] = category[enumerations.SECTION_LIST_OBJECT]
                        categories.append(cat)
                self.__dump_cache_file(cache_dir + publisher+"_categories.cpl", categories)

        def __dump_application_list(self, publisher, application_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                apps = []
                for application in application_list:
                        app = {}
                        app["mark"] = application[enumerations.MARK_COLUMN]
                        app["name"] = application[enumerations.NAME_COLUMN]
                        app["description"] = application[enumerations.DESCRIPTION_COLUMN]
                        app["status"] = application[enumerations.STATUS_COLUMN]
                        app["fmri"] = application[enumerations.FMRI_COLUMN]
                        app["stem"] = application[enumerations.STEM_COLUMN]
                        app["display_name"] = application[enumerations.DISPLAY_NAME_COLUMN]
                        app["is_visible"] = application[enumerations.IS_VISIBLE_COLUMN]
                        app["category_list"] = application[enumerations.CATEGORY_LIST_COLUMN]
                        app["pkg_authority"] = application[enumerations.AUTHORITY_COLUMN]
                        apps.append(app)
                self.__dump_cache_file(cache_dir + publisher+"_packages.cpl", apps)

        def __dump_section_list(self, publisher, section_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                sections = []
                for section in section_list:
                        sec = {}
                        sec["id"] = section[enumerations.SECTION_ID]
                        sec["name"] = section[enumerations.SECTION_NAME]
                        sec["subcategory"] = section[enumerations.SECTION_SUBCATEGORY]
                        sec["enabled"] = section[enumerations.SECTION_ENABLED]
                        sections.append(sec)
                self.__dump_cache_file(cache_dir + publisher+"_sections.cpl", sections)

        def __load_cache_info(self, publisher):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return None
                info = self.__read_cache_file(cache_dir + publisher+".cpl")
                return info

        def load_category_list(self, publisher, category_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                categories = self.__read_cache_file(cache_dir + publisher+"_categories.cpl")
                cat_count = 0
                for cat in categories:
                        cat_id = cat.get("id")
                        name = cat.get("name")
                        description = cat.get("description")
                        icon = None
                        icon_visible = cat.get("iconvisible")
                        if icon_visible:
                                icon = self.category_icon
                        visible = cat.get("visible")
                        section_list = cat.get("section_list")               
                        cat = \
                            [
                                cat_id, name, description, icon, icon_visible,
                                visible, section_list
                            ]
                        category_list.insert(cat_count, cat)
                        cat_count += 1

        def load_application_list(self, publisher, application_list, 
            selected_pkgs=None):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                applications = self.__read_cache_file(cache_dir + publisher+"_packages.cpl")
                app_count = len(application_list)
                if app_count > 0:
                        app_count += 1
                selected_pkgs_pub = None
                if selected_pkgs != None:
                        selected_pkgs_pub = selected_pkgs.get(publisher)
                for app in applications:
                        marked = False
                        status_icon = None
                        name = app.get("name")
                        description = app.get("description")
                        status = app.get("status")
                        if status == enumerations.INSTALLED:
                                status_icon = self.installed_icon
                        elif status == enumerations.UPDATABLE:
                                status_icon = self.update_available_icon
                        fmri = app.get("fmri")
                        stem = app.get("stem")
                        if selected_pkgs_pub != None:
                                if stem in selected_pkgs_pub:
                                        marked = True
                        display_name = app.get("display_name")
                        is_visible = app.get("is_visible")
                        category_list = app.get("category_list")
                        pkg_authority = app.get("pkg_authority")
                        app = \
                            [
                                marked, status_icon, name, description, status,
                                fmri, stem, display_name, is_visible, 
                                category_list, pkg_authority
                            ]
                        application_list.insert(app_count, app)
                        app_count += 1

        def load_section_list(self, publisher, section_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                sections = self.__read_cache_file(cache_dir + publisher+"_sections.cpl")
                sec_count = 0
                for sec in sections:
                        sec_id = sec.get("id")
                        name = sec.get("name")
                        subcategory = None
                        enabled = sec.get("enabled")
                        section = \
                            [
                                sec_id, name, subcategory, enabled
                            ]
                        section_list.insert(sec_count, section)
                        sec_count += 1

        def __read_cache_file(self, file_path):
                fh = open(file_path, 'r')
                data = cPickle.load(fh)
                fh.close()
                return data

        def __dump_cache_file(self, file_path, data):
                fh = open(file_path,"w")
                cPickle.dump(data, fh, True)
                fh.close()



