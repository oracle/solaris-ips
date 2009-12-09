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
import pkg.gui.misc_non_gui as gui_misc

CACHE_VERSION = 11

class CacheListStores:
        def __init__(self, api_o):
                self.api_o = api_o

        def __get_cache_dir(self):
                return gui_misc.get_cache_dir(self.api_o)

        def get_index_timestamp(self):
                img = self.api_o.img
                index_path = os.path.join(img.imgdir, "state/installed")
                try:
                        return os.path.getmtime(index_path)
                except (OSError, IOError):
                        return None

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
                        gui_misc.dump_cache_file(
                            os.path.join(cache_dir, ".__search__completion.cpl"), texts)
                except IOError:
                        return

        def __load_search_completion_info(self, completion_list):
                cache_dir = self.__get_cache_dir()
                if not cache_dir:
                        return
                texts = []
                try:
                        texts = gui_misc.read_cache_file(
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
