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

from __future__ import division
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

after = None
before = None
summary_file = None

filelist_by_date = {}

filelist_totals = {}
filelist_totals["kilobytes"] = 0
filelist_totals["bytes"] = 0

pkg_pat = re.compile("/filelist/(?P<mversion>\d+)/(?P<trailing>.*)")

# old-division; pylint: disable=W1619
def report_filelist_by_bytes():
        print("<p>Total kilobytes sent via filelist: {0:f}</p>".format(filelist_totals["kilobytes"] + filelist_totals["bytes"]/1024))

        if summary_file:
                print("<p>Total kilobytes sent via filelist: {0:f}</p>".format(filelist_totals["kilobytes"] + filelist_totals["bytes"]/1024), file=summary_file)

def count_filelist(mg, d):
        try:
                filelist_by_date[d.date().isoformat()] += 1
        except KeyError:
                filelist_by_date[d.date().isoformat()] = 1

        pm = pkg_pat.search(mg["uri"])
        if pm != None:
                pg = pm.groupdict()

                if mg["response"] == "200":
                        filelist_totals["bytes"] += int(mg["subcode"])

                        if filelist_totals["bytes"] > 1024:
                                filelist_totals["kilobytes"] += filelist_totals["bytes"] // 1024
                                filelist_totals["bytes"] = filelist_totals["bytes"] % 1024

                # XXX should measure downtime via 503, other failure responses

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
                summary_file = prefix_summary_open("filelist")

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

        count_filelist(mg, d)

host_cache_save()

report_section_begin("Filelist", summary_file = summary_file)
report_filelist_by_bytes()
report_by_date(filelist_by_date, "filelist", summary_file = summary_file)
report_section_end(summary_file = summary_file)
