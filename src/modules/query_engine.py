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

import fnmatch

import pkg.search_storage as ss
import pkg.search_errors as search_errors

FILE_OPEN_TIMEOUT_SECS = 1

class Query(object):
        """The class which handles all query parsing and representation. """

        def __init__(self, term):
                term = term.strip()
                self._glob = False
                if '*' in term or '?' in term or '[' in term:
                        self._glob = True
                self._term = term

        def get_term(self):
                return self._term

        def uses_glob(self):
                return self._glob

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
                    'fmri': ss.IndexStoreDict('id_to_fmri_dict.ascii'),
                    'action': ss.IndexStoreDict('id_to_action_dict.ascii'),
                    'tok_type':
                        ss.IndexStoreDict('id_to_token_type_dict.ascii'),
                    'version':
                        ss.IndexStoreDict('id_to_version_dict.ascii'),
                    'keyval': ss.IndexStoreDict('id_to_keyval_dict.ascii'),
                    'main_dict': ss.IndexStoreMainDict('main_dict.ascii'),
                    'token_byte_offset':
                            ss.IndexStoreDictMutable('token_byte_offset')
                }

                self._data_fmri = self._data_dict['fmri']
                self._data_action = self._data_dict['action']
                self._data_tok_type = self._data_dict['tok_type']
                self._data_version = self._data_dict['version']
                self._data_keyval = self._data_dict['keyval']
                self._data_main_dict = self._data_dict['main_dict']
                self._data_token_offset = self._data_dict['token_byte_offset']

        def _open_dicts(self, raise_on_no_index=True):
                ret = ss.consistent_open(self._data_dict.values(),
                    self._dir_path, self._file_timeout_secs)
                if ret == None and raise_on_no_index:
                        raise search_errors.NoIndexException(self._dir_path)
                return ret

        def _close_dicts(self):
                for d in self._data_dict.values():
                        d.close_file_handle()
                
        def search_internal(self, query):
                """Searches the indexes in dir_path for any matches of query
                and the results in self.res. The method assumes the dictionaries
                have already been loaded and read appropriately.
                """

                assert self._data_main_dict.get_file_handle() is not None

                matched_ids = {
                    'fmri': set(),
                    'action': set(),
                    'tok_type': set(),
                    'version': set(),
                    'keyval': set(),
                    'main_dict': set(),
                    'token_byte_offset': set()
                }

                res = {}
                
                glob = query.uses_glob()
                term = query.get_term()

                offsets = []

                if glob:
                        keys = self._data_token_offset.get_dict().keys()
                        if not keys:
                                # No matches were found.
                                return matched_ids, res
                        matches = fnmatch.filter(keys, term)
                        offsets = [
                            self._data_token_offset.get_id(match)
                            for match in matches
                        ]
                        offsets.sort()
                elif not self._data_token_offset.has_entity(term):
                        # No matches were found
                        return matched_ids, res
                else:
                        offsets.append(
                            self._data_token_offset.get_id(term))

                md_fh = self._data_main_dict.get_file_handle()
                for o in offsets:
                        md_fh.seek(o)
                        line = md_fh.readline()
                        assert not line == '\n'
                        tok, entries = self._data_main_dict.parse_main_dict_line(line)
                        assert ((term == tok) or
                            (glob and fnmatch.fnmatch(tok, term)))
                        for tok_type_id, action_id, keyval_id, \
                            fmri_ids in entries:
                                matched_ids['tok_type'].add(tok_type_id)
                                matched_ids['action'].add(action_id)
                                matched_ids['keyval'].add(keyval_id)

                                fmri_set = set()
                                for fmri_id, version_id in fmri_ids:
                                        fmri_set.add((fmri_id,
                                            version_id))
                                        matched_ids['version'].add(
                                            version_id)
                                        matched_ids['fmri'].add(fmri_id)
                                fmri_list = list(fmri_set)
                                fmri_list.sort()
                                res[(tok_type_id,
                                    action_id, keyval_id)] = fmri_list
                return matched_ids, res

        def get_results(self, res):
                """Uses the data generated by calling search to generate
                results of the search.
                """
                
                send_res = []

                # Construct the answer for the search_0 format
                for k in res.keys():
                        tok_type_id, action_id, keyval_id = k
                        tok_type = self._data_tok_type.get_entity(tok_type_id)
                        action = self._data_action.get_entity(action_id)
                        keyval = self._data_keyval.get_entity(keyval_id)
                        fmri_list = res[k]
                        for pkg_id, version_id in fmri_list:
                                fmri_res = \
                                    self._data_fmri.get_entity(pkg_id) + \
                                    "@" + \
                                    self._data_version.get_entity(version_id)
                                send_res.append((tok_type, fmri_res,
                                                 action, keyval))
                return send_res
