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

import threading
import fnmatch

import pkg.search_storage as ss
import pkg.search_errors as search_errors
import pkg.query_engine as qe
from pkg.choose import choose

class Query(qe.Query):
        """ The class which handles all query parsing and representation. """
        # The empty class is present to allow consumers to import a single
        # query engine module rather than have to import the client/server
        # one as well as the base one.
        pass


class ServerQueryEngine(qe.QueryEngine):
        """ This class contains the data structures and methods needed to
        perform search on the indexes created by Indexer.
        """
        def __init__(self, dir_path):

                # A lock that ensures that only one thread may be modifying
                # the internal dictionaries at any given time.
                self.dict_lock = threading.Lock()
                self.dict_lock.acquire()
                
                qe.QueryEngine.__init__(self, dir_path)

                try:
                        if self._open_dicts(False):
                                try:
                                        for d in self._data_dict.values():
                                                if d == self._data_main_dict:
                                                        continue
                                                d.read_dict_file()
                                finally:
                                        for d in self._data_dict.values():
                                                d.close_file_handle()
                finally:
                        self.dict_lock.release()

        def _read_dicts(self):
                for d in self._data_dict.values():
                        if d == self._data_main_dict:
                                continue
                        d.read_dict_file()
                        
        def search(self, query):
                """ Searches the indexes in dir_path for any matches of query
                and returns the results.
                """
                
                self.dict_lock.acquire()
                try:
                        self._open_dicts()
                        try:
                                self._read_dicts()
                                return self.search_internal_server(query)
                        except:
                                self._close_dicts()
                                raise
                except:
                        self.dict_lock.release()
                        raise

        def search_done(self):
                try:
                        self._close_dicts()
                finally:
                        self.dict_lock.release()
                        
        def search_internal_server(self, query):
                """Searches the indexes in dir_path for any matches of query
                and the results in self.res. The method assumes the dictionaries
                have already been loaded and read appropriately.
                """

                assert self._data_main_dict.get_file_handle() is not None

                res = {}

                glob = query.uses_glob()
                term = query.get_term()
                case_sensitive = query.is_case_sensitive()

                if not case_sensitive:
                        glob = True
                offsets = []

                if glob:
                        keys = self._data_token_offset.get_keys()
                        if not keys:
                                # No matches were found.
                                return
                        matches = choose(keys, term, case_sensitive)
                        offsets = [
                            self._data_token_offset.get_id(match)
                            for match in matches
                        ]
                        offsets.sort()
                elif not self._data_token_offset.has_entity(term):
                        # No matches were found
                        return
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
                            (not case_sensitive and term.lower() == tok.lower()) or
                            (glob and fnmatch.fnmatch(tok, term)) or
                            (not case_sensitive and
                            fnmatch.fnmatch(tok.lower(), term.lower())))
                        for tok_type_id, action_id, keyval_id, \
                            fmri_ids in entries:
                                fmri_set = set()
                                for fmri_id, version_id in fmri_ids:
                                        fmri_set.add((fmri_id,
                                            version_id))
                                tok_type = \
                                    self._data_tok_type.get_entity(tok_type_id)
                                action = \
                                    self._data_action.get_entity(action_id)
                                keyval = \
                                    self._data_keyval.get_entity(keyval_id)
                                for pkg_id, version_id in sorted(fmri_set):
                                        fmri_res = \
                                            self._data_fmri.get_entity(pkg_id) + \
                                            "@" + \
                                            self._data_version.get_entity(version_id)
                                        yield((tok_type, fmri_res,
                                                         action, keyval))
                return
