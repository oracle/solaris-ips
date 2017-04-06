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

#
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#


# This Indexer class handles the client-side specific code for hashing the
# full_fmri_list and storing it as a file on disk. Storing the hash allows
# fast comparison between what the catalog thinks is installed and what
# the indexer has indexed.

import pkg.indexer as indexer
import pkg.search_storage as ss
from pkg.misc import EmptyI

class Indexer(indexer.Indexer):
        def __init__(self, image, get_manf_func, get_manifest_path,
            progtrack=None, excludes=EmptyI):
                indexer.Indexer.__init__(self, image.index_dir, get_manf_func,
                    get_manifest_path, progtrack, excludes)
                self.image = image
                self._data_dict['full_fmri_hash'] = \
                    ss.IndexStoreSetHash('full_fmri_list.hash')
                self._data_full_fmri_hash = self._data_dict['full_fmri_hash']

        def _write_assistant_dicts(self, out_dir):
                """Gives the full_fmri hash object the data it needs before
                the superclass is called to write out the dictionaries.
                """
                self._data_full_fmri_hash.set_hash(
                    self._data_full_fmri.get_set())
                indexer.Indexer._write_assistant_dicts(self, out_dir)

        def check_index_has_exactly_fmris(self, fmri_names):
                """Checks to see if the fmris given are the ones indexed.
                """
                try:
                        res = \
                            ss.consistent_open(self._data_dict.values(),
                                self._index_dir, self._file_timeout_secs)
                        if res is not None and \
                            not self._data_full_fmri_hash.check_against_file(
                            fmri_names):
                                res = None
                finally:
                        for d in self._data_dict.values():
                                d.close_file_handle()
                return res is not None
