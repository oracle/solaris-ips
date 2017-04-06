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
# Copyright (c) 2009, 2013, Oracle and/or its affiliates. All rights reserved.
#

import sys
import pkg.query_parser as qp
from pkg.query_parser import BooleanQueryException, ParseError, QueryException, QueryLengthExceeded

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
        pass
        
class OrQuery(qp.OrQuery):
        pass

class PkgConversion(qp.PkgConversion):
        pass

class PhraseQuery(qp.PhraseQuery):
        pass

class FieldQuery(qp.FieldQuery):
        pass

class TopQuery(qp.TopQuery):
        pass

class TermQuery(qp.TermQuery):
        """This class handles the client specific search logic for searching
        for a specific query term."""

        _global_data_dict = {}

        def search(self, restriction, fmris):
                """This function performs the specific steps needed to do
                search on a server.

                The "restriction" parameter is a generator over results that
                another branch of the AST has already found.  If it's not None,
                then it's treated as the domain for search.  If it is None then
                the actions of all known packages is the domain for search.

                The "fmris" parameter is a function which produces an object
                which iterates over all known fmris."""
                
                if restriction:
                        return self._restricted_search_internal(restriction)
                base_res = self._search_internal(fmris)
                it = self._get_results(base_res)
                return it
