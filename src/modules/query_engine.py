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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import pkg.search_storage as ss
import pkg.search_errors as search_errors

FILE_OPEN_TIMEOUT_SECS = 1

class Query(object):
        """The class which handles all query parsing and representation. """

        def __init__(self, term, case_sensitive):
                term = term.strip()
                self._glob = False
                self._case_sensitive = case_sensitive
                if '*' in term or '?' in term or '[' in term:
                        self._glob = True
                self._term = term

        def get_term(self):
                return self._term

        def uses_glob(self):
                return self._glob

        def is_case_sensitive(self):
                return self._case_sensitive

class QueryEngine(object):
        """This class contains the data structures and methods needed to
        perform search on the indexes created by Indexer.
        """
        def __init__(self, dir_path):

                assert dir_path

                self._dir_path = dir_path

                self._file_timeout_secs = FILE_OPEN_TIMEOUT_SECS

                # This structure was used to gather all index files into one
                # location. If a new index structure is needed, the files can
                # be added (or removed) from here. Providing a list or
                # dictionary allows an easy approach to opening or closing all
                # index files.
                
                self._data_dict = {
                    'fmri': ss.IndexStoreDict(ss.FMRI_FILE),
                    'action': ss.IndexStoreDict(ss.ACTION_FILE),
                    'tok_type':
                        ss.IndexStoreDict(ss.TT_FILE),
                    'version':
                        ss.IndexStoreDict(ss.VERSION_FILE),
                    'keyval': ss.IndexStoreDict(ss.KEYVAL_FILE),
                    'main_dict': ss.IndexStoreMainDict(ss.MAIN_FILE),
                    'token_byte_offset':
                            ss.IndexStoreDictMutable(ss.BYTE_OFFSET_FILE)
                }

                self._data_fmri = self._data_dict['fmri']
                self._data_action = self._data_dict['action']
                self._data_tok_type = self._data_dict['tok_type']
                self._data_version = self._data_dict['version']
                self._data_keyval = self._data_dict['keyval']
                self._data_main_dict = self._data_dict['main_dict']
                self._data_token_offset = \
                    self._data_dict['token_byte_offset']

        def _open_dicts(self, raise_on_no_index=True):
                ret = ss.consistent_open(self._data_dict.values(),
                    self._dir_path, self._file_timeout_secs)
                if ret == None and raise_on_no_index:
                        raise search_errors.NoIndexException(self._dir_path)
                return ret

        def _close_dicts(self):
                for d in self._data_dict.values():
                        d.close_file_handle()
