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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import cPickle as pickle
import datetime
import time

from an_report import *

ndays = 0

def report_by_date(data, title, summary_file = None):
        global ndays

        chart_data = ""
        chart_min = 0
        chart_max = 0
        days = 0
        total = 0
        chart_hz = 440
        chart_vt = 330

        sdkeys = sorted(data.keys())
        start_day = sdkeys[0]
        end_day = sdkeys[-1]

        for i in sdkeys:
                days += 1
                total += data[i]

                if chart_data == "":
                        chart_data = "%d" % data[i]
                else:
                        chart_data += ",%d" % data[i]
                if data[i] > chart_max:
                        chart_max = data[i]

        msg = """\
<p>
Period: %s - %s (%d days)<br />
""" % (start_day, end_day, days)

        ndays = days
        sz = (chart_hz / ndays)

        url = "cht=lc&chs=%dx%d&chg=%d,%d&chds=%d,%d&chxt=y,x&chxl=0:|0|%d|1:|%s|%s&chd=t:%s" % (ndays * sz, chart_vt, 7 * sz, 250 * (chart_vt / chart_max), chart_min, chart_max, chart_max, start_day, end_day, chart_data)

        fname = retrieve_chart("http://chart.apis.google.com/chart?%s" % url,
            "%s-date" % title)

        msg += """\
<!-- %s -->
<img src=\"%s\" alt=\"%s\" /><br />""" % (url, fname, "Active catalog IPs over %d day window" % ndays)

        print msg
        if summary_file:
                print >>summary_file, msg

merge_entries_by_date = {}

for fn in sys.argv[1:]:
        f = file(fn, "rb")
        ebd = pickle.load(f)
        f.close()

        for k in ebd:
                if k in merge_entries_by_date:
                        for v in ebd[k]:
                                if not v in merge_entries_by_date[k]:
                                        merge_entries_by_date[k].append(v)

                else:
                        merge_entries_by_date[k] = ebd[k]

dates = sorted(merge_entries_by_date.keys())
data = {}

for d in dates:
        data[d] = len(merge_entries_by_date[d])       

ip_counts = {}
firstdate = dates[0]
firstn = 0
firstdt = datetime.datetime(*(time.strptime(firstdate, "%Y-%m-%d")[0:6]))

for ip in merge_entries_by_date[firstdate]:
        ip_counts[ip] = 1

window = datetime.timedelta(30)
data = {}

for d in dates[1:]:
        dt = datetime.datetime(*(time.strptime(d, "%Y-%m-%d")[0:6]))
        ips = merge_entries_by_date[d]

        for ip in ips:
                try:
                        ip_counts[ip] += 1
                except KeyError:
                        ip_counts[ip] = 1

        delta = dt - firstdt

        while delta > window:
                #   run through merge_entries_by_date[firstdate] and decrement
                rips = merge_entries_by_date[firstdate]
                for rip in rips:
                        ip_counts[rip] -= 1
                        if ip_counts[rip] == 0:
                                del ip_counts[rip]

                #   advance firstn, set firstdate, firstdt to dates[firstn]
                firstn += 1
                firstdate = dates[firstn]
                firstdt = datetime.datetime(*(time.strptime(firstdate, "%Y-%m-%d")[0:6]))

                #   recalculate delta
                delta = dt - firstdt
        
        data[d] = len(ip_counts.keys())
        
report_section_begin("Active IP addresses")
print "<h3>Distinct IP addresses, by date</h3>"
report_by_date(data, "distinct-cat-1d")
report_section_end()
