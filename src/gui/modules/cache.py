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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import sys
try:
        import gtk
except ImportError:
        sys.exit(1)
from threading import Thread
import pkg.gui.misc_non_gui as nongui_misc

CACHE_VERSION = 11

class CacheListStores:
        def __init__(self, api_o):
                self.api_o = api_o

        def __get_cache_dir(self):
                return nongui_misc.get_cache_dir(self.api_o)

        def get_index_timestamp(self):
                img = self.api_o.img
                index_path = os.path.join(img.imgdir, "state/installed")
                try:
                        return os.path.getmtime(index_path)
                except (OSError, IOError):
                        return None

        def __dump_categories_expanded_dict(self, cat_exp_dict):
                #CED entry: {('opensolaris.org', (6,)): True}
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                catexs = []
                for key in cat_exp_dict.keys():
                        name, path = key
                        path1 = -1
                        if len(path) > 0:
                                path1 = path[0]
                        catex = {}
                        catex["name"] = name
                        catex["path1"] = path1
                        catexs.append(catex)                
                
                nongui_misc.dump_cache_file(
                    os.path.join(cache_dir, "pm_cat_exp.cpl"),
                    catexs)
                    
        def __load_categories_expanded_dict(self, cat_exp_dict):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                catexs = nongui_misc.read_cache_file(
                    os.path.join(cache_dir, "pm_cat_exp.cpl"))
                for catex in catexs:
                        name = catex.get("name")
                        path1 = catex.get("path1")
                        if path1 != -1:
                                cat_exp_dict[name, (path1,)] = True

        def dump_categories_expanded_dict(self, cat_exp_dict):
                Thread(target = self.__dump_categories_expanded_dict,
                    args = (cat_exp_dict, )).start()

        def load_categories_expanded_dict(self, cat_exp_dict):
                Thread(target = self.__load_categories_expanded_dict,
                    args = (cat_exp_dict, )).start()

        def __dump_categories_active_dict(self, cat_ac_dict):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                catacs = []
                for name, path in cat_ac_dict.iteritems():
                        path1 = -1
                        path2 = -1
                        if len(path) == 1:
                                path1 = path[0]
                        elif len(path) > 1:
                                path1 = path[0]
                                path2 = path[1]                        
                        catac = {}
                        catac["name"] = name
                        catac["path1"] = path1
                        catac["path2"] = path2
                        catacs.append(catac)
                
                nongui_misc.dump_cache_file(
                    os.path.join(cache_dir, "pm_cat_ac.cpl"),
                    catacs)
                    
        def __load_categories_active_dict(self, cat_ac_dict):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                catacs = nongui_misc.read_cache_file(
                    os.path.join(cache_dir, "pm_cat_ac.cpl"))
                for catac in catacs:
                        name = catac.get("name")
                        path1 = catac.get("path1")
                        path2 = catac.get("path2")
                        if path1 != -1 and path2 != -1:
                                cat_ac_dict[name] = (path1, path2)
                        elif path1 != -1:
                                cat_ac_dict[name] = (path1,)

        def dump_categories_active_dict(self, cat_ac_dict):
                Thread(target = self.__dump_categories_active_dict,
                    args = (cat_ac_dict, )).start()

        def load_categories_active_dict(self, cat_ac_dict):
                Thread(target = self.__load_categories_active_dict,
                    args = (cat_ac_dict, )).start()

        def __dump_search_completion_info(self, completion_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                texts = []
                for text in completion_list:
                        txt = {}
                        txt["text"] = text[0]
                        texts.append(txt)
                try:
                        nongui_misc.dump_cache_file(
                            os.path.join(cache_dir, ".__search__completion.cpl"), texts)
                except IOError:
                        return

        def __load_search_completion_info(self, completion_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                texts = []
                try:
                        texts = nongui_misc.read_cache_file(
                            os.path.join(cache_dir, ".__search__completion.cpl"))
                except IOError:
                        return gtk.ListStore(str)

                txt_count = 0
                for txt in texts:
                        txt_val = txt.get("text")
                        text = [ txt_val ]
                        completion_list.insert(txt_count, text)
                        txt_count += 1

        def dump_search_completion_info(self, completion_list):
                Thread(target = self.__dump_search_completion_info,
                    args = (completion_list, )).start()

        def load_search_completion_info(self, completion_list):
                Thread(target = self.__load_search_completion_info,
                    args = (completion_list, )).start()
