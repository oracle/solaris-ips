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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
import datetime
import fileinput
import getopt
import md5
import os
import re
import sys
import time

from an_report import *
from six.moves.urllib.parse import unquote

after = None
before = None
summary_file = None

search_by_date = {}
search_by_ip = {}
search_by_arch = {}
search_by_lang = {}

search_by_success = {}
search_by_failure = {}

pkg_pat = re.compile("/search/(?P<mversion>\d+)/(?P<keywords>.*)")

def emit_search_report(summary_file, searchtype, label, results):
        print("<pre>")
        for i, n in results:
                print(i, n)
        print("</pre>")

        if summary_file:
                print("""
			<h3>Top 25 {searchtype} searches</h3>
			<div id="search-{searchtype}-container">
			<table id="search-{searchtype}-table">
			<thead><tr><th>Term</th><th>{label}</th></tr></thead>
		""".format(label=label, searchtype=searchtype), file=summary_file)

                for i, n in results[:25]:
                        print("<tr><td>{0}</td><td>{1}</td></tr>".format(i, n),
                file=summary_file)

                print("</table></div>", file=summary_file)
		print("""
<script type="text/javascript">
	var myDataSource =
	    new YAHOO.util.DataSource(YAHOO.util.Dom.get(
	    "search-{searchtype}-table"));
	myDataSource.responseType = YAHOO.util.DataSource.TYPE_HTMLTABLE;
	myDataSource.responseSchema = {
	    fields: [{key:"Term", sortable:true},
		    {key:"{label}", parser:YAHOO.util.DataSource.parseNumber}
	    ]
	};

	var myColumnDefs = [
	    {key:"Term", sortable:true},
	    {key:"{label}", sortable:true}
	];

	var myDataTable =
	    new YAHOO.widget.DataTable("search-{searchtype}-container",
	    myColumnDefs, myDataSource,
	    {sortedBy:{key:"{label}", dir:YAHOO.widget.DataTable.CLASS_DESC}});
</script>
                """.format(label=label, searchtype=searchtype), file=summary_file)



def report_search_by_failure():
        sfi = sorted(search_by_failure.items(), reverse=True, key=lambda k_v: (k_v[1],k_v[0]))
	emit_search_report(summary_file, "failed", "Misses", sfi)


def report_search_by_success():
        ssi = sorted(search_by_success.items(), reverse=True, key=lambda k_v1: (k_v1[1],k_v1[0]))
	emit_search_report(summary_file, "successful", "Hits", ssi)


def count_search(mg, d):
        try:
                search_by_date[d.date().isoformat()] += 1
        except KeyError:
                search_by_date[d.date().isoformat()] = 1
        try:
                search_by_ip[mg["ip"]] += 1
        except KeyError:
                search_by_ip[mg["ip"]] = 1


        pm = pkg_pat.search(mg["uri"])
        if pm != None:
                pg = pm.groupdict()

                kw = unquote(pg["keywords"])

                if mg["response"] == "200":
                        if mg["subcode"] == "-":
                                # A zero-length response is a failed search
                                # (4 Aug - ...).  Consequence of the migration
                                # to CherryPy; will be unneeded once
                                # http://defect.opensolaris.org/bz/show_bug.cgi?id=3238
                                # is fixed.
                                try:
                                        search_by_failure[kw] += 1
                                except KeyError:
                                        search_by_failure[kw] = 1
                        else:
                                try:
                                        search_by_success[kw] += 1
                                except KeyError:
                                        search_by_success[kw] = 1
                elif mg["response"] == "404":
                        try:
                                search_by_failure[kw] += 1
                        except KeyError:
                                search_by_failure[kw] = 1

                # XXX should measure downtime via 503, other failure responses


        agent = pkg_agent_pat.search(mg["agent"])
        if agent == None:
                return

        ag = agent.groupdict()

        try:
                search_by_arch[ag["arch"]] += 1
        except KeyError:
                search_by_arch[ag["arch"]] = 1

opts, args = getopt.getopt(sys.argv[1:], "a:b:sw:")

for opt, arg in opts:
        if opt == "-a":
                try:
                        after = datetime.datetime(*(time.strptime(arg, "%Y-%b-%d")[0:6]))
                except ValueError:
                        after = datetime.datetime(*(time.strptime(arg, "%Y-%m-%d")[0:6]))

        if opt == "-b":
                before = arg

        if opt == "-s":
                summary_file = prefix_summary_open("search")

        if opt == "-w":
                active_window = arg

host_cache_set_file_name()
host_cache_load()

lastdate = None
lastdatetime = None

for l in fileinput.input(args):
        m = comb_log_pat.search(l)
        if not m:
                continue

        mg = m.groupdict()

        d = None

        if lastdatetime and mg["date"] == lastdate:
                d = lastdatetime
        else:
                d = datetime.datetime(*(time.strptime(mg["date"], "%d/%b/%Y")[0:6]))
                lastdate = mg["date"]
                lastdatetime = d

        if after and d < after:
                continue

        count_search(mg, d)

host_cache_save()
search_by_country = ip_to_country(search_by_ip)

report_section_begin("Search", summary_file = summary_file)
report_cols_begin(summary_file = summary_file)
report_col_begin("l", summary_file = summary_file)
report_by_date(search_by_date, "search", summary_file = summary_file)
report_by_ip(search_by_ip, "search", summary_file = summary_file)
report_col_end("l", summary_file = summary_file)
report_col_begin("r", summary_file = summary_file)
report_by_country(search_by_country, "search", summary_file = summary_file)
report_col_end("r", summary_file = summary_file)
report_cols_end(summary_file = summary_file)

report_cols_begin(summary_file = summary_file)
report_col_begin("l", summary_file = summary_file)
report_search_by_failure()
report_col_end("l", summary_file = summary_file)
report_col_begin("r", summary_file = summary_file)
report_search_by_success()
report_col_end("r", summary_file = summary_file)
report_cols_end(summary_file = summary_file)
report_section_end(summary_file = summary_file)
