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
import pkg.query_engine as qe

class Query(qe.Query):
        """ The class which handles all query parsing and representation. """
        # The empty class is present to allow consumers to import a single
        # query engine module rather than have to import the client/server
        # one as well as the base one.
        pass

class ClientQueryEngine(qe.QueryEngine):
        """This class contains the data structures and methods needed to
        perform search on the indexes created by Indexer."""

        def search(self, query):
                """Searches the indexes for any matches of query
                and returns the results."""

                self._open_dicts()

                try:
                        self._data_token_offset.read_dict_file()
                        matched_ids, res = self.search_internal(query)
                        for n, d in self._data_dict.iteritems():
                                if d == self._data_main_dict or \
                                    d == self._data_token_offset:
                                        continue
                                d.matching_read_dict_file(matched_ids[n])
                finally:
                        self._close_dicts()
                return self.get_results(res)
