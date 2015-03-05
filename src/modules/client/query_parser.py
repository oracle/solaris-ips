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
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.

import os
import sys
import threading
import pkg.client.api_errors as api_errors
import pkg.manifest as manifest
import pkg.search_storage as ss
import pkg.search_errors as se
import pkg.fmri as fmri
from pkg.choose import choose

import pkg.query_parser as qp
from pkg.query_parser import BooleanQueryException, ParseError, QueryLengthExceeded
import itertools

class QueryLexer(qp.QueryLexer):
        pass

class QueryParser(qp.QueryParser):
        """This class exists so that the classes the parent class query parser
        uses to build the AST are the ones defined in this module and not the
        parent class's module.  This is done so that a single query parser can
        be shared between the client and server modules but will construct an
        AST using the appropriate classes."""
        
        def __init__(self, lexer):
                qp.QueryParser.__init__(self, lexer)
                mod = sys.modules[QueryParser.__module__]
                tmp = {}
                for class_name in self.query_objs.keys():
                        assert hasattr(mod, class_name)
                        tmp[class_name] = getattr(mod, class_name)
                self.query_objs = tmp

# Because many classes do not have client specific modifications, they
# simply subclass the parent module's classes.
class Query(qp.Query):
        pass


class AndQuery(qp.AndQuery):
        def remove_root(self, img_dir):
                lcv = self.lc.remove_root(img_dir)
                rcv = self.rc.remove_root(img_dir)
                return lcv or rcv


class EmptyQuery(object):
        def __init__(self, return_type):
                self.return_type = return_type
        
        def search(self, *args):
                return []

        def set_info(self, **kwargs):
                return

        def __str__(self):
                if self.return_type == qp.Query.RETURN_ACTIONS:
                        return "(a AND b)"
                else:
                        return "<(a AND b)>"

        def propagate_pkg_return(self):
                """Makes this node return packages instead of actions.
                Returns None because no changes need to be made to the tree."""
                self.return_type = qp.Query.RETURN_PACKAGES
                return None


class OrQuery(qp.OrQuery):
        def remove_root(self, img_dir):
                lcv = self.lc.remove_root(img_dir)
                if not lcv:
                        self.lc = EmptyQuery(self.lc.return_type)
                rcv = self.rc.remove_root(img_dir)
                if not rcv:
                        self.rc = EmptyQuery(self.rc.return_type)
                return lcv or rcv


class PkgConversion(qp.PkgConversion):
        def remove_root(self, img_dir):
                return self.query.remove_root(img_dir)


class PhraseQuery(qp.PhraseQuery):
        def remove_root(self, img_dir):
                return self.query.remove_root(img_dir)


class FieldQuery(qp.FieldQuery):
        def remove_root(self, img_dir):
                return self.query.remove_root(img_dir)


class TopQuery(qp.TopQuery):
        """This class handles raising the exception if the search was conducted
        without using indexes.  It yields all results, then raises the
        exception."""

        def __init__(self, *args, **kwargs):
                qp.TopQuery.__init__(self, *args, **kwargs)
                self.__use_slow_search = False

        def get_use_slow_search(self):
                """Return whether slow search has been used."""

                return self.__use_slow_search

        def set_use_slow_search(self, val):
                """Set whether slow search has been used."""

                self.__use_slow_search = val
                
        def set_info(self, **kwargs):
                """This function provides the necessary information to the AST
                so that a search can be performed."""

                qp.TopQuery.set_info(self,
                    get_use_slow_search=self.get_use_slow_search,
                    set_use_slow_search=self.set_use_slow_search,
                    **kwargs)

        def search(self, *args):
                """This function performs performs local client side search.

                If slow search was used, then after all results have been
                returned, it raises SlowSearchUsed."""

                for i in qp.TopQuery.search(self, *args):
                        yield i
                if self.__use_slow_search:
                        raise api_errors.SlowSearchUsed()

        def remove_root(self, img_dir):
                return self.query.remove_root(img_dir)

        def add_or(self, rc):
                lc = self.query
                if isinstance(rc, TopQuery):
                        rc = rc.query
                self.query = OrQuery(lc, rc)


class TermQuery(qp.TermQuery):
        """This class handles the client specific search logic for searching
        for a base query term."""

        __client_dict_locks = {}
        _global_data_dict = {}

        def __init__(self, term):
                qp.TermQuery.__init__(self, term)
                self._impl_fmri_to_path = None
                self._efn = None
                self._data_fast_remove = None
                self.full_fmri_hash = None
                self._data_fast_add = None

        def __init_gdd(self, path):
                gdd = self._global_data_dict
                if path in gdd:
                        return

                # Setup default global dictionary for this index path.
                qp.TermQuery.__init_gdd(self, path)

                # Client search needs to account for the packages which have
                # been installed or removed since the last time the indexes
                # were rebuilt. Add client-specific global data dictionaries
                # for this index path.
                tq_gdd = gdd[path]
                tq_gdd["fast_add"] = ss.IndexStoreSet(ss.FAST_ADD)
                tq_gdd["fast_remove"] = ss.IndexStoreSet(ss.FAST_REMOVE)
                tq_gdd["fmri_hash"] = ss.IndexStoreSetHash(
                    ss.FULL_FMRI_HASH_FILE)

        def _lock_client_gdd(self, index_dir):
                # This lock is used so that only one instance of a term query
                # object is ever modifying the class wide variable for this
                # index.
                self.__client_dict_locks.setdefault(index_dir,
                    threading.Lock()).acquire()

        def _unlock_client_gdd(self, index_dir):
                self.__client_dict_locks[index_dir].release()

        def set_info(self, gen_installed_pkg_names, get_use_slow_search,
            set_use_slow_search, **kwargs):
                """This function provides the necessary information to the AST
                so that a search can be performed.

                The "gen_installed_pkg_names" parameter is a function which
                returns a generator function which iterates over the names of
                the installed packages in the image.

                The "get_use_slow_search" parameter is a function that returns
                whether slow search has been used.

                The "set_use_slow_search" parameter is a function that sets
                whether slow search was used."""

                self.get_use_slow_search = get_use_slow_search
                self._efn = gen_installed_pkg_names()
                index_dir = kwargs["index_dir"]
                self._lock_client_gdd(index_dir)
                try:
                        try:
                                qp.TermQuery.set_info(self,
                                    gen_installed_pkg_names=\
                                        gen_installed_pkg_names,
                                    get_use_slow_search=get_use_slow_search,
                                    set_use_slow_search=set_use_slow_search,
                                    **kwargs)
                                # Take local copies of the client-only
                                # dictionaries so that if another thread
                                # changes the shared data structure, this
                                # instance's objects won't be affected.
                                tq_gdd = self._get_gdd(index_dir)
                                self._data_fast_add = tq_gdd["fast_add"]
                                self._data_fast_remove = tq_gdd["fast_remove"]
                                self.full_fmri_hash = tq_gdd["fmri_hash"]
                                set_use_slow_search(False)
                        except se.NoIndexException:
                                # If no index was found, the slower version of
                                # search will be used.
                                set_use_slow_search(True)
                finally:
                        self._unlock_client_gdd(index_dir)
                
        def search(self, restriction, fmris, manifest_func, excludes):
                """This function performs performs local client side search.
                
                The "restriction" parameter is a generator over the results that
                another branch of the AST has already found.  If it exists,
                those results are treated as the domain for search.  If it does
                not exist, search uses the set of actions from installed
                packages as the domain.

                The "fmris" parameter is a function which produces an object
                which iterates over the names of installed fmris.

                The "manifest_func" parameter is a function which takes a fmri
                and returns a path to the manifest for that fmri.

                The "excludes" parameter is a list of the variants defined for
                this image."""

                if restriction:
                        return self._restricted_search_internal(restriction)
                elif not self.get_use_slow_search():
                        try:
                                self.full_fmri_hash.check_against_file(
                                    self._efn)
                        except se.IncorrectIndexFileHash:
                                raise \
                                    api_errors.IncorrectIndexFileHash()
                        base_res = \
                            self._search_internal(fmris)
                        client_res = \
                            self._search_fast_update(manifest_func,
                            excludes)
                        base_res = self._check_fast_remove(base_res)
                        it = itertools.chain(self._get_results(base_res),
                            self._get_fast_results(client_res))
                        return it
                else:
                        return self.slow_search(fmris, manifest_func, excludes)

        def _check_fast_remove(self, res):
                """This function removes any results from the generator "res"
                (the search results) that are actions from packages known to
                have been removed from the image since the last time the index
                was built."""

                return (
                    (p_str, o, a, s, f)
                    for p_str, o, a, s, f
                    in res
                    if not self._data_fast_remove.has_entity(p_str)
                )

        def _search_fast_update(self, manifest_func, excludes):
                """This function searches the packages which have been
                installed since the last time the index was rebuilt.

                The "manifest_func" parameter is a function which maps fmris to
                the path to their manifests.

                The "excludes" paramter is a list of variants defined in the
                image."""

                assert self._data_main_dict.get_file_handle() is not None

                glob = self._glob
                term = self._term
                case_sensitive = self._case_sensitive

                if not case_sensitive:
                        glob = True
                        
                fast_update_dict = {}

                fast_update_res = []

                # self._data_fast_add holds the names of the fmris added
                # since the last time the index was rebuilt.
                for fmri_str in self._data_fast_add._set:
                        if not (self.pkg_name_wildcard or
                            self.pkg_name_match(fmri_str)):
                                continue
                        f = fmri.PkgFmri(fmri_str)
                        path = manifest_func(f)
                        search_dict = manifest.Manifest.search_dict(path,
                            return_line=True, excludes=excludes)
                        for tmp in search_dict:
                                tok, at, st, fv = tmp
                                if not (self.action_type_wildcard or
                                    at == self.action_type) or \
                                    not (self.key_wildcard or st == self.key):
                                        continue
                                if tok not in fast_update_dict:
                                        fast_update_dict[tok] = []
                                fast_update_dict[tok].append((at, st, fv,
                                    fmri_str, search_dict[tmp]))
                if glob:
                        keys = fast_update_dict.keys()
                        matches = choose(keys, term, case_sensitive)
                        fast_update_res = [
                            fast_update_dict[m] for m in matches
                        ]
                        
                else:
                        if term in fast_update_dict:
                                fast_update_res.append(fast_update_dict[term])
                return fast_update_res

        def _get_fast_results(self, fast_update_res):
                """This function transforms the output of _search_fast_update
                to match that of _search_internal."""

                for sub_list in fast_update_res:
                        for at, st, fv, fmri_str, line_list in sub_list:
                                for l in line_list:
                                        yield at, st, fmri_str, fv, l

        def slow_search(self, fmris, manifest_func, excludes):
                """This function performs search when no prebuilt index is
                available.

                The "fmris" parameter is a generator function which iterates
                over the packages to be searched.

                The "manifest_func" parameter is a function which maps fmris to
                the path to their manifests.

                The "excludes" parameter is a list of variants defined in the
                image."""

                for pfmri in list(fmris()):
                        fmri_str = pfmri.get_fmri(anarchy=True,
                            include_scheme=False)
                        if not (self.pkg_name_wildcard or
                            self.pkg_name_match(fmri_str)):
                                continue
                        manf = manifest_func(pfmri)
                        fast_update_dict = {}
                        fast_update_res = []
                        glob = self._glob
                        term = self._term
                        case_sensitive = self._case_sensitive

                        if not case_sensitive:
                                glob = True

                        search_dict = manifest.Manifest.search_dict(manf,
                            return_line=True, excludes=excludes)
                        for tmp in search_dict:
                                tok, at, st, fv = tmp
                                if not (self.action_type_wildcard or
                                    at == self.action_type) or \
                                    not (self.key_wildcard or st == self.key):
                                        continue
                                if tok not in fast_update_dict:
                                        fast_update_dict[tok] = []
                                fast_update_dict[tok].append((at, st, fv,
                                    fmri_str, search_dict[tmp]))
                        if glob:
                                keys = fast_update_dict.keys()
                                matches = choose(keys, term, case_sensitive)
                                fast_update_res = [
                                    fast_update_dict[m] for m in matches
                                ]
                        else:
                                if term in fast_update_dict:
                                        fast_update_res.append(
                                            fast_update_dict[term])
                        for sub_list in fast_update_res:
                                for at, st, fv, fmri_str, line_list in sub_list:
                                        for l in line_list:
                                                yield at, st, fmri_str, fv, l

        def _read_pkg_dirs(self, fmris):
                """Legacy function used to search indexes which have a pkg
                directory with fmri offset information instead of the
                fmri_offsets.v1 file.  This function is in this subclass to
                translate the error from a search_error to an api_error."""

                try:
                        return qp.TermQuery._read_pkg_dirs(self, fmris)
                except se.InconsistentIndexException as e:
                        raise api_errors.InconsistentIndexException(e)

        def remove_root(self, img_root):
                if (not self.action_type_wildcard and
                    self.action_type != "file" and
                    self.action_type != "link" and
                    self.action_type != "hardlink" and
                    self.action_type != "directory") or \
                    (not self.key_wildcard and self.key != "path") or \
                    (not self._term.startswith(img_root) or img_root == "/"):
                        return False
                img_root = img_root.rstrip("/")
                self._term = self._term[len(img_root):]
                self.key = "path"
                self.key_wildcard = False
                return True
