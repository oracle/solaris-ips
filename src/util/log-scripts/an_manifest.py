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

manifest_by_date = {}
manifest_by_ip = {}
manifest_by_arch = {}
manifest_by_lang = {}
manifest_by_raw_agent = {}

manifest_by_pkg = {}
manifest_by_ver_pkg = {}

pkg_pat = re.compile("/manifest/(?P<mversion>\d+)/(?P<stem>[^@]*)@(?P<version>.*)")

def report_manifest_by_arch():
        print("<pre>")
        for i in manifest_by_arch.keys():
                print(i, manifest_by_arch[i])
        print("</pre>")

def report_manifest_by_pkg():
        print("<pre>")
        for i, n in (sorted(manifest_by_pkg.items(), key=lambda k_v: (k_v[1],k_v[0]))):
                print(i, n)
        print("</pre>")

def report_manifest_by_ver_pkg():
        print("<pre>")
        for i, n in (sorted(manifest_by_ver_pkg.items(), key=lambda k_v: (k_v[1],k_v[0]))):
                print(i, n)
        print("</pre>")

def count_manifest(mg, d):
        try:
                manifest_by_date[d.date().isoformat()] += 1
        except KeyError:
                manifest_by_date[d.date().isoformat()] = 1
        try:
                manifest_by_ip[mg["ip"]] += 1
        except KeyError:
                manifest_by_ip[mg["ip"]] = 1

        pm = pkg_pat.search(mg["uri"])
        if pm != None and mg["response"] == "200":
                pg = pm.groupdict()

                try:
                        manifest_by_pkg[unquote(pg["stem"])] += 1
                except KeyError:
                        manifest_by_pkg[unquote(pg["stem"])] = 1

                try:
                        manifest_by_ver_pkg[unquote(pg["stem"] + "@" + pg["version"])] += 1
                except KeyError:
                        manifest_by_ver_pkg[unquote(pg["stem"] + "@" + pg["version"])] = 1

        agent = pkg_agent_pat.search(mg["agent"])
        if agent == None:
                return

        ag = agent.groupdict()
        try:
                manifest_by_arch[ag["arch"]] += 1
        except KeyError:
                manifest_by_arch[ag["arch"]] = 1

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
                summary_file = prefix_summary_open("manifest")

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
                try:
                        d = datetime.datetime(*(time.strptime(mg["date"], "%d/%b/%Y")[0:6]))
                        lastdate = mg["date"]
                        lastdatetime = d
                except ValueError:
                        # In the case the line can't be parsed for a date, it's
                        # probably corrupt.
                        continue

        if after and d < after:
                continue

        count_manifest(mg, d)

host_cache_save()
manifest_by_country = ip_to_country(manifest_by_ip)

report_section_begin("Manifest", summary_file = summary_file)
report_cols_begin(summary_file = summary_file)
report_col_begin("l", summary_file = summary_file)
report_by_date(manifest_by_date, "manifest", summary_file = summary_file)
report_col_end("l", summary_file = summary_file)
report_col_begin("r", summary_file = summary_file)
report_by_country(manifest_by_country, "manifest", summary_file = summary_file)
report_col_end("r", summary_file = summary_file)
report_cols_end(summary_file = summary_file)
report_by_ip(manifest_by_ip, "manifest", summary_file = summary_file)
report_by_raw_agent(manifest_by_raw_agent, "manifest", summary_file = summary_file)

report_manifest_by_pkg()
report_manifest_by_ver_pkg()
report_section_end(summary_file = summary_file)
