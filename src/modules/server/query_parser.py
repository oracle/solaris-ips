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

import sys
import pkg.query_parser as qp
from pkg.query_parser import BooleanQueryException, ParseError

class QueryLexer(qp.QueryLexer):
        pass

class QueryParser(qp.QueryParser):
        def __init__(self, lexer):
                qp.QueryParser.__init__(self, lexer)
                mod = sys.modules[QueryParser.__module__]
                tmp = {}
                for class_name in self.query_objs.keys():
                        assert hasattr(mod, class_name)
                        tmp[class_name] = getattr(mod, class_name)
                self.query_objs = tmp

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

        def search(self, restriction, fmris):
                if restriction:
                        return self._restricted_search_internal(restriction)
                base_res = self._search_internal(fmris)
                it = self._get_results(base_res)
                return it
