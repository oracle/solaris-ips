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
import GeoIP
import datetime
import math
import os
import re
import socket
import sys
import urllib2
import config

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
        f = open("%s.png" % fileprefix, "w")
        try:
                u = urllib2.urlopen(url)
                f.write(u.read())
        except:
                print >>sys.stderr, "an_catalog: couldn't retrieve chart '%s'" % url

        f.close()

        return f.name

def prefix_raw_open(fileprefix, reportname):
        f = open("%s-%s.dat" % (fileprefix, reportname), "w")

        return f

def prefix_summary_open(fileprefix):
        f = open("%s-summary.html" % (fileprefix), "w")

        return f

def report_begin(cap_title):
        print """\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
<title>pkg.depotd Logs: %s</title>
</head>
<body>""" % cap_title

def report_end():
        print """\
</body>
</html>"""

	
def report_section_begin(cap_title, summary_file = None):
        msg = """\
<br clear="all" />
<div class="section">
<h2>%s</h2>""" % cap_title

        print msg
        if summary_file:
                print >>summary_file, msg

def report_section_end(summary_file = None):
        msg = """</div> <!--end class=section-->"""
        print msg
        if summary_file:
                print >>summary_file, msg


def report_cols_begin(summary_file = None):
        msg = """<div class="colwrapper">"""
        print msg
        if summary_file:
                print >>summary_file, msg

def report_cols_end(summary_file = None):
        msg = """<br clear="all" /></div>"""
        print msg
        if summary_file:
                print >>summary_file, msg

def report_col_begin(col, summary_file = None):
        msg = """<div class="%scolumn">""" % col

        print msg
        if summary_file:
                print >>summary_file, msg

def report_col_end(col, summary_file = None):
        msg = """</div> <!-- end class=%scolumn -->""" % col

        print msg
        if summary_file:
                print >>summary_file, msg



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

                print >>rf, i, data[i]
                if chart_data == "":
                        chart_data = "%d" % data[i]
                else:
                        chart_data += ",%d" % data[i]
                if data[i] > chart_max:
                        chart_max = data[i]

        msg = """\
<p>
Total %s requests: <b>%d</b><br />
Period: %s - %s (%d days)<br />
Average %s requests per day: %.1f</p>""" % (title, total, start_day, end_day,
            days, title, float(total / days))

        ndays = int(str(days))
        sz = (chart_hz / ndays)

        url = "cht=lc&chs=%dx%d&chg=%d,%d&chds=%d,%d&chxt=y,x&chxl=0:|0|%d|1:|%s|%s&chd=t:%s" % (ndays * sz, chart_vt, 7 * sz, 250 * (chart_vt / chart_max), chart_min, chart_max, chart_max, start_day, end_day, chart_data)

        fname = retrieve_chart("http://chart.apis.google.com/chart?%s" % url,
            "%s-date" % title)

        msg += """\
<!-- %s -->
<img src=\"%s\" alt=\"%s\" /><br />""" % (url, fname, title)

        rf.close()
        
        print msg
        if summary_file:
                print >>summary_file, msg

def report_by_ip(data, title, summary_file = None):
        total = 0
        rf = prefix_raw_open(title, "ip")

        for i, n in (sorted(data.items(), key=lambda(k,v): (v,k))):
                total += n
                print >>rf, n, i
                #print n, host_cache_lookup(i)

        print "<p>Distinct IP addresses: <b>%d</b></p>" % len(data.keys())
        print "<p>Total %s retrievals: <b>%d</b></p>" % (title, total)

        rf.close()

        if summary_file:
                print >>summary_file, "<p>Distinct IP addresses: <b>%d</b></p>" % len(data.keys())
                print >>summary_file, "<p>Total %s retrievals: <b>%d</b></p>" % (title, total)

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
        for i, n in (sorted(data.items(), key=lambda(k,v): (v,k))):
                total += n
                print >>rf, n, i
                if i == None:
                        continue

                if chart_ccs == "":
                        chart_ccs = "%s" % i
                else:
                        chart_ccs += "%s" % i

                if chart_data == "":
                        chart_data += "%d" % (math.log(n) / chart_max * 100)
                else:
                        chart_data += ",%d" % (math.log(n) / chart_max * 100)

        rf.close()

        # colours from blue flare:  013476 b0d2ff

        map_regions = [ "world", "asia", "europe", "south_america",
            "middle_east", "africa" ]

        msg = """\
<h3>Requests by country</h3>
<script type="text/javascript">
        var tabView_%s = new YAHOO.widget.TabView('%s-country');
</script>
<div id="%s-country" class="yui-navset">
  <ul class="yui-nav">
""" % (title, title, title)

        sel = "class=\"selected\""
        for r in map_regions:
                msg += """<li %s><a href="#%s-%s"><em>%s</em></a></li>""" % (sel, title, r, r)
                sel = ""

        msg += """\
  </ul>            
  <div class="yui-content">"""

        for r in map_regions:
                url = "chs=440x220&cht=t&chtm=%s&chld=%s&chd=t:%s&chco=ffffff,b0d2ff,013476" % (r, chart_ccs, chart_data)
                print "<!-- %s -->" % url
                fname = retrieve_chart("http://chart.apis.google.com/chart?%s" % url,
                    "%s-%s-map" % (title, r))
                msg += """<div id="%s-%s"><img src="%s" alt="%s" /></div>""" % (title, r, fname, title)

        msg += """\
  </div>
</div>
<small>Color intensity linear in log of requests.</small>"""
       

        print msg
        if summary_file:
                print >>summary_file, msg

def report_by_raw_agent(data, title, summary_file = None):
        rf = prefix_raw_open(title, "country")
        for i, n in (sorted(data.items(), key=lambda(k,v): (v,k))):
                print >>rf, i, n

        rf.close()


