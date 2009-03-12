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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import fnmatch
import re
import sys
import threading
import copy
import itertools
import errno

import ply.lex as lex
import ply.yacc as yacc
import pkg.search_storage as ss
import pkg.search_errors as search_errors
import pkg.fmri as fmri
import pkg.actions as actions
from pkg.choose import choose
from pkg.misc import EmptyI

FILE_OPEN_TIMEOUT_SECS = 1

class QueryLexer(object):

        tokens = ("FTERM", "TERM", "LPAREN", "RPAREN", "AND", "OR", "QUOTE1",
            "QUOTE2", "LBRACE", "RBRACE")
        t_LPAREN = r"\("
        t_RPAREN = r"\)"
        t_QUOTE1 = r"[\']"
        t_QUOTE2 = r'[\"]'
        t_ignore = r" "

        def __init__(self):
                object.__init__(self)
                self.reserved = {
                    "AND" : "AND",
                    "OR" : "OR"
                }

        def t_LBRACE(self, t):
                r"([pP]([kK]([gG][sS]?)?)?)?<"
                t.type = "LBRACE"
                return t

        def t_RBRACE(self, t):
                r">"
                t.type = "RBRACE"
                return t

        def t_FTERM(self, t):
                # pkg_name:action_type:key:value
                r"([^\(\s][^\s]*)?\:"
                t.type = "FTERM"
                bar = t.value.split(":", 4)
                assert len(bar) >= 2
                assert bar[-1] == ""
                pkg_name = None
                action_type = None
                key = bar[-2]
                if len(bar) >= 3:
                        action_type = bar[-3]
                        if len(bar) >= 4:
                                pkg_name = bar[-4]
                t.value = (pkg_name, action_type, key)
                return t
                
        def t_TERM(self, t):
                r'[^\s\(\'\"][^\s]*[^\s\)\'\"\>] | [^\s\(\)\'\"]'
                t.type = self.reserved.get(t.value, "TERM")
                return t

        def t_error(self, t):
                raise RuntimeError("%s is a unparseable character")

        def build(self, **kwargs):
                self.lexer = lex.lex(object=self, **kwargs)

        def set_input(self, input):
                self.lexer.input(input)
                
        def token(self):
                return self.lexer.token()
                
        def test(self, data):
                self.lexer.input(data)
                while 1:
                        tok = self.lexer.token()
                        if not tok:
                                break
                        print >> sys.stderr, tok


class QueryParser(object):

        tokens = QueryLexer.tokens

        precedence = (
            ("right", "FTERM"),
            ("left", "TERM"),
            ("right", "AND", "OR"),
            ("right", "QUOTE1", "QUOTE2"),
        )

        def p_top_level(self, p):
                '''start : xterm'''
                p[0] = self.query_objs["TopQuery"](p[1])

        def p_xterm(self, p):
                ''' xterm : basetermlist
                          | andterm
                          | orterm'''
                p[0] = p[1]

        def p_basetermlist(self, p):
                ''' basetermlist : baseterm
                                 | baseterm basetermlist '''
                if len(p) == 3:
                        p[0] = self.query_objs["AndQuery"](p[1], p[2])
                else:
                        p[0] = p[1]

        def p_baseterm(self, p):
                ''' baseterm : term
                             | fterm
                             | phraseterm
                             | parenterm
                             | pkgconv'''
                p[0] = p[1]

        def p_term(self, p):
                'term : TERM'
                p[0] = self.query_objs["TermQuery"](p[1])
                
        def p_fterm(self, p):
                '''fterm : FTERM ftermarg
                         | FTERM fterm
                         | FTERM'''
                if len(p) == 3:
                        p[0] = self.query_objs["FieldQuery"](p[1], p[2])
                else:
                        p[0] = self.query_objs["FieldQuery"](p[1],
                            self.query_objs["TermQuery"]('*'))

        def p_ftermarg(self, p):
                '''ftermarg : term
                            | phraseterm'''
                p[0] = p[1]

        def p_phraseterm(self, p):
                ''' phraseterm : QUOTE1 term_list QUOTE1
                               | QUOTE2 term_list QUOTE2'''
                p[2].reverse()
                p[0] = self.query_objs["PhraseQuery"](p[2],
                    self.query_objs["TermQuery"])

        def p_term_list(self, p):
                ''' term_list : TERM term_list
                              | TERM '''
                if len(p) == 3:
                        p[2].append(p[1])
                        p[0] = p[2]
                else:
                        p[0] = [p[1]]

        def p_parenterm(self, p):
                ''' parenterm : LPAREN xterm RPAREN '''
                p[0] = p[2]

        def p_packages(self, p):
                'pkgconv : LBRACE xterm RBRACE'
                p[0] = self.query_objs["PkgConversion"](p[2])

        def p_andterm(self, p):
                ''' andterm : xterm AND xterm'''
                p[0] = self.query_objs["AndQuery"](p[1], p[3])

        def p_orterm(self, p):
                ''' orterm : xterm OR xterm'''
                p[0] = self.query_objs["OrQuery"](p[1], p[3])

        def p_error(self, p):
                raise RuntimeError("Died in parsing, current p is:%s" % (p))
                        
        def __init__(self, lexer):
                self.lexer = lexer
                self.parser = yacc.yacc(module=self, debug=0, write_tables=0)
                self.query_objs = {
                    "AndQuery" : AndQuery,
                    "FieldQuery" : FieldQuery,
                    "OrQuery" : OrQuery,
                    "PhraseQuery" : PhraseQuery,
                    "PkgConversion" : PkgConversion,
                    "TermQuery" : TermQuery,
                    "TopQuery" : TopQuery
                }

        def parse(self, input):
                self.lexer.set_input(input)
                return self.parser.parse(lexer=self.lexer)

class Query(object):
        RETURN_EITHER = 0
        RETURN_PACKAGES = 1
        RETURN_ACTIONS = 2
        VALIDATION_STRING = { 1:'Return from search v1\n' }

        def __init__(self, text, case_sensitive, return_type, num_to_return,
            start_point):
                self.__text = text
                self.case_sensitive = case_sensitive
                self.return_type = return_type
                assert self.return_type == Query.RETURN_PACKAGES or \
                    self.return_type == Query.RETURN_ACTIONS
                self.num_to_return = num_to_return
                self.start_point = start_point

        def __str__(self):
                return "%s_%s_%s_%s_%s" % (self.case_sensitive,
                    self.return_type, self.num_to_return, self.start_point,
                    self.__text)

        def ver_0(self):
                return self.__text

        def encoded_text(self):
                if self.return_type == Query.RETURN_PACKAGES:
                        return "<%s>" % self.__text
                else:
                        return self.__text
        
        @staticmethod
        def fromstr(s):
                case_sensitive, return_type, num_to_return, start_point, \
                    text = tuple(s.split("_", 4))
                if case_sensitive == 'True':
                        case_sensitive = True
                elif case_sensitive == 'False':
                        case_sensitive = False
                else:
                        assert 0
                if num_to_return == 'None':
                        num_to_return = None
                else:
                        num_to_return = int(num_to_return)
                if start_point == 'None':
                        start_point = None
                else:
                        start_point = int(start_point)
                return_type = int(return_type)
                return Query(text, case_sensitive, int(return_type),
                    num_to_return, start_point)

        @staticmethod
        def return_action_to_key(k):
                at, st, pfmri, fv, l = k
                return pfmri

class UnknownFieldTypeException(Exception):
        def __init__(self, field_kind, field_value):
                Exception.__init__(self)
                self.field_kind = field_kind
                self.field_value = field_value
        
class BooleanQueryException(Exception):
        def __init__(self, ac, pc):
                Exception.__init__(self)
                self.ac = ac
                self.pc = pc
        
class BooleanQuery(object):
        def __init__(self, left_query, right_query):
                self.lc = left_query
                self.rc = right_query
                self.return_type = self.lc.return_type
                if self.lc.return_type != self.rc.return_type:
                        if self.lc.return_type == Query.RETURN_ACTIONS:
                                raise BooleanQueryException(self.lc, self.rc)
                        else:
                                raise BooleanQueryException(self.rc, self.lc)

        def set_info(self, *args):
                self.lc.set_info(*args)
                self.rc.set_info(*args)
                
        def search(self, *args):
                return set(self.lc.search(None, *args)), \
                    set(self.rc.search(None, *args))

        def sorted(self, res):
                key = None
                if self.return_type == Query.RETURN_ACTIONS:
                        key = Query.return_action_to_key
                return sorted(res, key=key)

        def allow_version(self, v):
                return v > 0 and self.lc.allow_version(v) and \
                    self.rc.allow_version(v)

class AndQuery(BooleanQuery):

        def search(self, restriction, *args):
                if self.return_type == Query.RETURN_ACTIONS:
                        lc_it = self.lc.search(restriction, *args)
                        return self.rc.search(lc_it, *args)
                else:
                        lc_set, rc_set = BooleanQuery.search(self, *args)
                        return self.sorted(lc_set & rc_set)
                

        def __str__(self):
                return "( " + str(self.lc) + " AND " + str(self.rc) + " )"
        
class OrQuery(BooleanQuery):

        def search(self, restriction, *args):
                if self.return_type == Query.RETURN_PACKAGES:
                        lc_set, rc_set = BooleanQuery.search(self, *args)
                        for i in self.sorted(lc_set | rc_set):
                                yield i
                elif not restriction:
                        for i in itertools.chain(self.lc.search(restriction,
                            *args), self.rc.search(restriction, *args)):
                                yield i
                else:
                        for i in restriction:
                                for j in itertools.chain(self.lc.search([i],
                                    *args), self.rc.search([i], *args)):
                                        yield j

        def __str__(self):
                return "( " + str(self.lc) + " OR " + str(self.rc) + " )"

class PkgConversion(object):
        def __init__(self, query):
                self.query = query
                self.return_type = Query.RETURN_PACKAGES

        def __str__(self):
                return "p<%s>" % str(self.query)

        def set_info(self, *args):
                self.query.set_info(*args)

        @staticmethod
        def optional_action_to_package(it, return_type, current_type):
                if current_type == return_type or return_type == \
                    Query.RETURN_EITHER:
                        return it
                elif return_type == Query.RETURN_PACKAGES and \
                    current_type == Query.RETURN_ACTIONS:
                        return sorted(set(
                            (pfmri for at, st, pfmri, fv, l in it)))
                else:
                        assert 0
                
        def search(self, restriction, *args):
                return self.optional_action_to_package(
                    self.query.search(restriction, *args),
                    Query.RETURN_PACKAGES, self.query.return_type)

        def allow_version(self, v):
                return v > 0 and self.query.allow_version(v)


class PhraseQuery(object):
        def __init__(self, str_list, term_query_class):
                assert str_list
                self.query = term_query_class(str_list[0])
                self.full_str = " ".join(str_list)
                self.return_type = Query.RETURN_ACTIONS
                if len(str_list) > 1:
                        self.query.add_trailing_wildcard()

        def __str__(self):
                return "Phrase Query:'" + self.full_str + "'"

        def set_info(self, *args):
                self.query.set_info(*args)

        def filter_res(self, l):
                return self.full_str in l

        @staticmethod
        def combine(fs, fv):
                if fs in fv:
                        return fv
                else:
                        return fs
                
        def search(self, restriction, *args):
                it = (
                    (at, st, pfmri, self.combine(self.full_str, fv), l)
                    for at, st, pfmri, fv, l
                    in self.query.search(restriction, *args)
                    if self.filter_res(l)
                )
                return it

        def allow_version(self, v):
                return v > 0 and self.query.allow_version(v)
                
class FieldQuery(object):
        def __init__(self, params, query):
                self.query = query
                self.return_type = Query.RETURN_ACTIONS
                self.query.pkg_name, self.query.action_type, self.query.key = \
                    params
                self.query.action_type_wildcard = self.__is_wildcard(
                    self.query.action_type)
                self.query.key_wildcard = self.__is_wildcard(self.query.key)
                self.query.pkg_name_wildcard = \
                    self.__is_wildcard(self.query.pkg_name)
                self.query.pkg_name_match = None
                if not self.query.pkg_name_wildcard:
                        if not self.query.pkg_name.endswith("*"):
                                self.query.pkg_name += "*"
                        self.query.pkg_name_match = \
                            re.compile(fnmatch.translate(self.query.pkg_name),
                                re.I).match

        def __str__(self):
                return "( PN:%s AT:%s ST:%s Q:%s)" % (self.query.pkg_name,
                    self.query.action_type, self.query.key, self.query)

        def set_info(self, *args):
                self.query.set_info(*args)

        @staticmethod
        def __is_wildcard(s):
                return s is None or s == '*' or s == ''
                
        def search(self, restriction, *args):
                assert self.query.return_type == Query.RETURN_ACTIONS
                return self.query.search(restriction, *args)

        def allow_version(self, v):
                return v > 0 and self.query.allow_version(v)

class TopQuery(object):
        def __init__(self, query):
                self.query = query
                self.start_point = 0
                self.num_to_return = None

        def __str__(self):
                return "TopQuery(" + str(self.query) +  " )"

        def __keep(self, x):
                return x >= self.start_point and \
                    (self.num_to_return is None or
                    x < self.num_to_return + self.start_point)
        
        def finalize_results(self, it):
                # Need to replace "1" with current search version, or something
                # similar

                if self.query.return_type == Query.RETURN_ACTIONS:
                        return (
                            (1, Query.RETURN_ACTIONS, (pfmri, fv, l))
                            for x, (at, st, pfmri, fv, l)
                            in enumerate(it)
                            if self.__keep(x)
                        )
                else:
                        return (
                            (1, Query.RETURN_PACKAGES, pfmri)
                            for x, pfmri
                            in enumerate(it)
                            if self.__keep(x)
                        )

        def set_info(self, num_to_return, start_point, *args):
                if start_point:
                        self.start_point = start_point
                self.num_to_return = num_to_return
                self.query.set_info(*args)
                
                        
        def search(self, *args):
                return self.finalize_results(self.query.search(None, *args))

        def allow_version(self, v):
                return self.query.allow_version(v)

class TermQuery(object):

        # This structure was used to gather all index files into one
        # location. If a new index structure is needed, the files can
        # be added (or removed) from here. Providing a list or
        # dictionary allows an easy approach to opening or closing all
        # index files.

        dict_lock = threading.Lock()

        has_non_wildcard_character = re.compile('.*[^\*\?].*')

        fmris = None
        
        _global_data_dict = {
            'manf':
                    ss.IndexStoreDict(ss.MANIFEST_LIST),
            'token_byte_offset':
                    ss.IndexStoreDictMutable(ss.BYTE_OFFSET_FILE),
        }
        
        def __init__(self, term):
                term = term.strip()
                self._glob = False
                if '*' in term or '?' in term or '[' in term:
                        self._glob = True
                self._term = term

                self.return_type = Query.RETURN_ACTIONS
                self._file_timeout_secs = FILE_OPEN_TIMEOUT_SECS

                self.pkg_name = None
                self.action_type = None
                self.key = None
                self.action_type_wildcard = True
                self.key_wildcard = True
                self.pkg_name_wildcard = True
                self.pkg_name_match = None
                self._case_sensitive = None
                self._dir_path = None

                self._manifest_path_func = None
                self._data_manf = None
                self._data_token_offset = None
                self._data_main_dict = None

        def __str__(self):
                return "( TermQuery: " + self._term + " )"

        def add_trailing_wildcard(self):
                if not self._term.endswith('*'):
                        self._term += "*"
        
        def set_info(self, dir_path, fmri_to_manifest_path_func,
            case_sensitive):
                self._dir_path = dir_path
                assert dir_path
                self._manifest_path_func = fmri_to_manifest_path_func
                self._case_sensitive = case_sensitive

                TermQuery.dict_lock.acquire()
                try:
                        self._data_main_dict = \
                            ss.IndexStoreMainDict(ss.MAIN_FILE)
                        tmp = TermQuery._global_data_dict.values()
                        tmp.append(self._data_main_dict)
                        ret = ss.consistent_open(tmp, self._dir_path,
                            self._file_timeout_secs)
                        if ret == None:
                                raise search_errors.NoIndexException(
                                    self._dir_path)
                        should_reread = False
                        for k, d in self._global_data_dict.items():
                                if d.should_reread():
                                        should_reread = True
                                        break
                        try:
                                if should_reread:
                                        for i in tmp:
                                                i.close_file_handle()
                                        TermQuery._global_data_dict = \
                                            dict([
                                                (k, copy.copy(d))
                                                for k, d
                                                in TermQuery._global_data_dict.items()
                                            ])
                                        tmp = \
                                            TermQuery._global_data_dict.values()
                                        tmp.append(self._data_main_dict)
                                        ret = ss.consistent_open(tmp,
                                            self._dir_path,
                                            self._file_timeout_secs)
                                        try:
                                                if ret == None:
                                                        raise search_errors.NoIndexException(self._dir_path)
                                                for d in TermQuery._global_data_dict.values():
                                                        d.read_dict_file()
                                        except:
                                                self._data_main_dict.close_file_handle()
                                                raise

                        finally:
                                for d in TermQuery._global_data_dict.values():
                                        d.close_file_handle()
                        self._data_manf = TermQuery._global_data_dict['manf']

                        self._data_token_offset = \
                            TermQuery._global_data_dict['token_byte_offset']

                finally:
                        TermQuery.dict_lock.release()

        def allow_version(self, v):
                return True
                
        def _close_dicts(self):
                self._data_main_dict.close_file_handle()

        @staticmethod
        def flatten(lst):
                res = []
                for l in lst:
                        if isinstance(l, list):
                                res.extend(TermQuery.flatten(l))
                        else:
                                res.append(l)
                return res
                
        def _restricted_search_internal(self, restriction):
                glob = self._glob
                term = self._term
                case_sensitive = self._case_sensitive

                if not case_sensitive:
                        glob = True
                for at, st, fmri_str, fv, l in restriction:
                        if not (self.pkg_name_wildcard or
                            self.pkg_name_match(fmri_str)) or \
                            not (self.action_type_wildcard or
                            at == self.action_type) or \
                            not (self.key_wildcard or st == self.key):
                                continue
                        l = l.strip()
                        act = actions.fromstr(l)
                        toks = [t[2] for t in act.generate_indices()]
                        toks = self.flatten(toks)
                        matches = []
                        if glob:
                                matches = choose(toks, term, case_sensitive)
                        elif term in toks:
                                matches = True
                        if matches:
                                yield at, st, fmri_str, fv, l

        def __offset_line_read(self, offsets):
                md_fh = self._data_main_dict.get_file_handle()
                for o in sorted(offsets):
                        md_fh.seek(o)
                        yield md_fh.readline()

        def _search_internal(self, fmris):
                """Searches the indexes in dir_path for any matches of query
                and the results in self.res. The method assumes the dictionaries
                have already been loaded and read appropriately.
                """
                assert self._data_main_dict.get_file_handle() is not None

                if TermQuery.fmris is None and not self.pkg_name_wildcard:
                        TermQuery.fmris = list(fmris())

                glob = self._glob
                term = self._term
                case_sensitive = self._case_sensitive

                if not case_sensitive:
                        glob = True
                offsets = None

                if glob:
                        if TermQuery.has_non_wildcard_character.match(term):
                                keys = self._data_token_offset.get_keys()
                                matches = choose(keys, term, case_sensitive)
                                offsets = set([
                                    self._data_token_offset.get_id(match)
                                    for match in matches
                                ])
                elif self._data_token_offset.has_entity(term):
                        offsets = set([
                            self._data_token_offset.get_id(term)])
                if not self.pkg_name_wildcard:
                        pkg_offsets = set()
                        for matching_pfmri in (
                            p
                            for p in TermQuery.fmris
                            if self.pkg_name_match(
                                p.get_fmri(anarchy=True, include_scheme=False))
                        ):
                                try:
                                        fh = open(os.path.join(
                                            self._dir_path, "pkg",
                                            matching_pfmri.get_name(),
                                            str(matching_pfmri.version)), "rb")
                                except EnvironmentError, e:
                                        if e.errno != errno.ENOENT:
                                                raise
                                        continue
                                for l in fh:
                                        pkg_offsets.add(int(l))
                        if offsets is None:
                                offsets = pkg_offsets
                        else:
                                offsets &= pkg_offsets

                if not self.action_type_wildcard:
                        tmp_set = set()
                        try:
                                fh = open(os.path.join(self._dir_path,
                                    "__at_" + self.action_type), "rb")
                                for l in fh:
                                        tmp_set.add(int(l.strip()))
                                if offsets is None:
                                        offsets = tmp_set
                                else:
                                        offsets &= tmp_set
                        except EnvironmentError, e:
                                if e.errno != errno.ENOENT:
                                        raise
                                offsets = set()

                if not self.key_wildcard:
                        tmp_set = set()
                        try:
                                fh = open(os.path.join(self._dir_path,
                                    "__st_" + self.key), "rb")
                                for l in fh:
                                        tmp_set.add(int(l))
                                if offsets is None:
                                        offsets = tmp_set
                                else:
                                        offsets &= tmp_set
                        except EnvironmentError, e:
                                if e.errno != errno.ENOENT:
                                        raise
                                offsets = set()
                line_iter = EmptyI
                if offsets is not None:
                        line_iter = self.__offset_line_read(offsets)
                elif glob and \
                    not TermQuery.has_non_wildcard_character.match(term):
                        line_iter = self._data_main_dict.get_file_handle()
                        
                for line in line_iter:
                        assert not line == '\n'
                        tok, at_lst = \
                            self._data_main_dict.parse_main_dict_line(line)
                        assert ((term == tok) or 
                            (not case_sensitive and
                            term.lower() == tok.lower()) or
                            (glob and fnmatch.fnmatch(tok, term)) or
                            (not case_sensitive and
                            fnmatch.fnmatch(tok.lower(), term.lower())))
                        for at, st_list in at_lst:
                                if not self.action_type_wildcard and \
                                    at != self.action_type:
                                        continue
                                for st, fv_list in st_list:
                                        if not self.key_wildcard and \
                                            st != self.key:
                                                continue
                                        for fv, p_list in fv_list:
                                                for p_id, m_off_set in p_list:
                                                        p_id = int(p_id)
                                                        p_str = self._data_manf.get_entity(p_id)
                                                        if not self.pkg_name_wildcard and not self.pkg_name_match(p_str):
                                                                continue
                                                        int_os = [
                                                            int(o)
                                                            for o
                                                            in m_off_set
                                                        ]
                                                        yield (p_str, int_os,
                                                            at, st, fv)
                self._close_dicts()
                return

        @staticmethod
        def __get_key(k):
                p_id, p_str = k
                return p_str
        
        def _get_results(self, res):
                # Construct the answer for the search_1 format
                for fmri_str, offsets, at, st, fv in res:
                        send_res = []
                        f = fmri.PkgFmri(fmri_str)
                        path = self._manifest_path_func(f)
                        file_handle = open(path)
                        for o in sorted(offsets):
                                file_handle.seek(o)
                                send_res.append((fv, at, st,
                                    file_handle.readline()))
                        file_handle.close()
                        for fv, at, st, l in send_res:
                                yield at, st, fmri_str, fv, l
