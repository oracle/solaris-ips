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
import cPickle as pickle
import GeoIP
import datetime
import math
import os
import re
import socket
import sys
import config

from six.moves.urllib.request import urlopen

# Apache combined log pattern
comb_log_pat = re.compile("(?P<ip>[\d\.]*) - - \[(?P<date>[^:]*):(?P<time>\S*) (?P<tz>[^\]]*)\] \"(?P<op>GET|POST|HEAD|\S*) (?P<uri>\S*) HTTP/(?P<httpver>[^\"]*)\" (?P<response>\d*) (?P<subcode>\d*|-) \"(?P<refer>[^\"]*)\" \"(?P<agent>[^\"]*)\" \"(?P<uuid>[^\"]*)\" \"(?P<intent>[^\"]*)\"")

# Agent field log patterns
browser_agent_pat = re.compile(".*X11; U; SunOS (?P<arch>[^;]*); (?P<lang>[^;]*)")
pkg_agent_pat = re.compile("pkg/(?P<pversion>\S*) \((?P<pos>\S*) (?P<arch>[^;]*); (?P<uname>\S*) (?P<build>[^;]*); (?P<imagetype>[^)]*)\)")

host_cache = {}
host_props = {}
host_props["file_name"] = "./host-cache.pkl"
host_props["outstanding"] = 0

gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)

def host_cache_set_file_name(path = "./host-cache.pkl"):
        host_props["file_name"] = path

def host_cache_load():
        try:
                pklfile = open(host_props["file_name"], 'rb')
                host_cache = pickle.load(pklfile)
                pklfile.close()
        except:
                host_cache = {}
        host_props["outstanding"] = 0

def host_cache_save():
        pklfile = open(host_props["file_name"], 'wb')
        pickle.dump(host_cache, pklfile)
        pklfile.close()

def host_cache_add():
        if host_props["outstanding"] > 128:
                host_cache_save()
                host_props["outstanding"] = 0

        host_props["outstanding"] += 1

def host_cache_lookup(ip):
        try:
                return host_cache[ip]
        except KeyError:
                pass

        try:
                hname = socket.gethostbyaddr(ip)[0]
                host_cache[ip] = hname

                host_cache_add()

                return host_cache[ip]
        except socket.herror:
                pass

        host_cache[ip] = ip
        return host_cache[ip]

# Countries we're not allowed to report on (iran, north korea)
filtered_countries = config.get("excluded").split(",")
filtered_countries = [x.strip() for x in filtered_countries]
def ip_to_country(ips):
        cs = {}
        for ip in ips.keys():
                cc = gi.country_code_by_addr(ip)
                if cc in filtered_countries:
                        continue
                try:
                        cs[cc] += ips[ip]
                except KeyError:
                        cs[cc] = ips[ip]
        return cs

def retrieve_chart(url, fileprefix):
        f = open("{0}.png".format(fileprefix), "w")
        try:
                u = urlopen(url)
                f.write(u.read())
        except:
                print("an_catalog: couldn't retrieve chart '{0}'".format(url),
                    file=sys.stderr)

        f.close()

        return f.name

def prefix_raw_open(fileprefix, reportname):
        f = open("{0}-{1}.dat".format(fileprefix, reportname), "w")

        return f

def prefix_summary_open(fileprefix):
        f = open("{0}-summary.html".format(fileprefix), "w")

        return f

def report_begin(cap_title):
        print("""\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
<title>pkg.depotd Logs: {0}</title>
</head>
<body>""".format(cap_title))

def report_end():
        print("""\
</body>
</html>""")


def report_section_begin(cap_title, summary_file = None):
        msg = """\
<br clear="all" />
<div class="section">
<h2>{0}</h2>""".format(cap_title)

        print(msg)
        if summary_file:
                print(msg, file=summary_file)

def report_section_end(summary_file = None):
        msg = """</div> <!--end class=section-->"""
        print(msg)
        if summary_file:
                print(msg, file=summary_file)


def report_cols_begin(summary_file = None):
        msg = """<div class="colwrapper">"""
        print(msg)
        if summary_file:
                print(msg, file=summary_file)

def report_cols_end(summary_file = None):
        msg = """<br clear="all" /></div>"""
        print(msg)
        if summary_file:
                print(msg, file=summary_file)

def report_col_begin(col, summary_file = None):
        msg = """<div class="{0}column">""".format(col)

        print(msg)
        if summary_file:
                print(msg, file=summary_file)

def report_col_end(col, summary_file = None):
        msg = """</div> <!-- end class={0}column -->""".format(col)

        print(msg)
        if summary_file:
                pprint(msg, file=summary_file)



def report_by_date(data, title, summary_file = None):
        chart_data = ""
        chart_min = 0
        chart_max = 0
        days = 0
        total = 0
        chart_hz = 440
        chart_vt = 330

        rf = prefix_raw_open(title, "date")

        sdkeys = sorted(data.keys())
        start_day = sdkeys[0]
        end_day = sdkeys[-1]

        for i in sdkeys:
                days += 1
                total += data[i]

                print(i, data[i], file=rf)
                if chart_data == "":
                        chart_data = "{0:d}".format(data[i])
                else:
                        chart_data += ",{0:d}".format(data[i])
                if data[i] > chart_max:
                        chart_max = data[i]

        msg = """\
<p>
Total {0} requests: <b>{1:d}</b><br />
Period: {2} - {3} ({4:d} days)<br />
Average {5} requests per day: {6:.1f}</p>""".format(title, total, start_day, end_day,
            days, title, total / days) # old-division; pylint: disable=W1619

        ndays = int(str(days))
        sz = (chart_hz // ndays)

        url = "cht=lc&chs={0:d}x{1:d}&chg={2:d},{3:d}&chds={4:d},{5:d}&chxt=y,x&chxl=0:|0|{6:d}|1:|{7}|{8}&chd=t:{9}".format(ndays * sz, chart_vt, 7 * sz, 250 * (chart_vt // chart_max, chart_min, chart_max, chart_max, start_day, end_day, chart_data))

        fname = retrieve_chart("http://chart.apis.google.com/chart?{0}".format(url),
            "{0}-date".format(title))

        msg += """\
<!-- {0} -->
<img src=\"{1}\" alt=\"{2}\" /><br />""".format(url, fname, title)

        rf.close()

        print(msg)
        if summary_file:
                print(msg, file=summary_file)

def report_by_ip(data, title, summary_file = None):
        total = 0
        rf = prefix_raw_open(title, "ip")

        for i, n in (sorted(data.items(), key=lambda k_v: (k_v[1], k_v[0]))):
                total += n
                print(n, i, file=rf)
                #print(n, host_cache_lookup(i))

        print("<p>Distinct IP addresses: <b>{0:d}</b></p>".format(len(data.keys())))
        print("<p>Total {0} retrievals: <b>{1:d}</b></p>".format(title, total))

        rf.close()

        if summary_file:
                print("<p>Distinct IP addresses: <b>{0:d}</b></p>".format(len(data.keys())), file=summary_file)
                print("<p>Total {0} retrievals: <b>{1:d}</b></p>".format(title, total), file=summary_file)

def report_by_country(data, title, summary_file = None):
        total = 0
        chart_data = ""
        chart_ccs = ""
        chart_max = 0

        for n in data.values():
                if n > chart_max:
                        chart_max = n

        chart_max = max(math.log(chart_max), 1)

        rf = prefix_raw_open(title, "country")
        for i, n in (sorted(data.items(), key=lambda k_v: (k_v[1], k_v[0]))):
                total += n
                print(n, i, file=rf)
                if i == None:
                        continue

                if chart_ccs == "":
                        chart_ccs = "{0}".format(i)
                else:
                        chart_ccs += "{0}".format(i)

                if chart_data == "":
                        chart_data += "{0:d}".format(math.log(n) // chart_max * 100)
                else:
                        chart_data += ",{0:d}".format(math.log(n) // chart_max * 100)

        rf.close()

        # colours from blue flare:  013476 b0d2ff

        map_regions = [ "world", "asia", "europe", "south_america",
            "middle_east", "africa" ]

        msg = """\
<h3>Requests by country</h3>
<script type="text/javascript">
        var tabView_{0} = new YAHOO.widget.TabView('{1}-country');
</script>
<div id="{2}-country" class="yui-navset">
  <ul class="yui-nav">
""".format(title, title, title)

        sel = "class=\"selected\""
        for r in map_regions:
                msg += """<li {0}><a href="#{1}-{2}"><em>{3}</em></a></li>""".format(sel, title, r, r)
                sel = ""

        msg += """\
  </ul>
  <div class="yui-content">"""

        for r in map_regions:
                url = "chs=440x220&cht=t&chtm={0}&chld={1}&chd=t:{2}&chco=ffffff,b0d2ff,013476".format(r, chart_ccs, chart_data)
                print("<!-- {0} -->".format(url))
                fname = retrieve_chart("http://chart.apis.google.com/chart?{0}".format(url),
                    "{0}-{1}-map".format(title, r))
                msg += """<div id="{0}-{1}"><img src="{2}" alt="{3}" /></div>""".format(title, r, fname, title)

        msg += """\
  </div>
</div>
<small>Color intensity linear in log of requests.</small>"""


        print(msg)
        if summary_file:
                print(msg, file=summary_file)

def report_by_raw_agent(data, title, summary_file = None):
        rf = prefix_raw_open(title, "country")
        for i, n in (sorted(data.items(), key=lambda k_v: (k_v[1], k_v[0]))):
                print(i, n, file=rf)

        rf.close()


