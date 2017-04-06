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

"""\
an_catalog.py - analyze pre-processed Apache combined log of catalog entries

The catalog operation presents interactions similar to the web-ping interaction.
The only distinct aspect is that, since the agent for a catalog operation is
usually pkg(1), we can assess the distribution across versions of these clients.

Our list of measurements is:

        - distinct operations,
        - operations by distinct IP,
        - active users, defined as users who have contacted the repository twice
          in the past 60 days,
        - operations by country [defer],
        - operations by architecture,
        - package client distribution.

The model is that the summary is printed to standard out, and a fuller report is
printed to catalog.html in the current directory.
"""

from __future__ import print_function
import datetime
import fileinput
import getopt
import md5
import os
import re
import socket
import sys
import tempfile
import time

from an_report import *

after = None
before = None
summary_file = None

catalog_by_date = {}
catalog_by_ip = {}
catalog_by_ip_active = {}
catalog_by_country = {}
catalog_by_raw_agent = {}
catalog_by_pkg_version = {}
catalog_by_arch = {}

def report_catalog_by_arch():
        print("<pre>")
        for i in catalog_by_arch.keys():
                print(i, catalog_by_arch[i])
        print("</pre>")

def report_catalog_by_raw_agent(summary_file = None):
        print("<pre>")
        for i, n in (sorted(catalog_by_raw_agent.items(), key=lambda k_v: (k_v[1],k_v[0]))):
                print(i, n)
        print("</pre>")

def report_catalog_by_pkg_version():
        print("<pre>")
        for i, n in (sorted(catalog_by_pkg_version.items(), key=lambda k_v: (k_v[1],k_v[0]))):
                print(i, n)
        print("</pre>")

def report_catalog_by_lang():
        labels = ""
        data = ""
        min = 0
        max = 0

        print("<pre>")
        for i, n in (sorted(catalog_by_lang.items(), key=lambda k_v: (k_v[1],k_v[0]))):
                if labels == "":
                        labels = "{0}".format(i)
                else:
                        labels += "|{0}".format(i)
                if data == "":
                        data = "{0:d}".format(n)
                else:
                        data += ",{0:d}".format(n)

                print(i, n)
                if n > max:
                        max = n

        print("</pre>")

        url = "cht=p3&chs=800x300&chl={0}&chds={1:d},{2:d}&chd=t:{3}".format(labels,min,max,data)
        fname = retrieve_chart("http://chart.apis.google.com/chart?{0}".format(url, "lang"))
        print ("<img src=\"{0}\" />".format(fname))

def count_catalog(mg, d):

        try:
                catalog_by_date[d.date().isoformat()] += 1
        except KeyError:
                catalog_by_date[d.date().isoformat()] = 1
        try:
                catalog_by_ip[mg["ip"]] += 1
        except KeyError:
                catalog_by_ip[mg["ip"]] = 1


        try:
                if not d in catalog_by_ip_active[mg["ip"]]:
                        catalog_by_ip_active[mg["ip"]].append(d)
        except KeyError:
                catalog_by_ip_active[mg["ip"]] = [d]

        try:
                catalog_by_raw_agent[mg["agent"]] += 1
        except:
                catalog_by_raw_agent[mg["agent"]] = 1

        # Agent-specific measurements.

        agent = pkg_agent_pat.search(mg["agent"])
        if agent == None:
                return

        ag = agent.groupdict()
        try:
                catalog_by_arch[ag["arch"]] += 1
        except KeyError:
                catalog_by_arch[ag["arch"]] = 1
        try:
                catalog_by_pkg_version[ag["pversion"]] += 1
        except KeyError:
                catalog_by_pkg_version[ag["pversion"]] = 1

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
                summary_file = prefix_summary_open("catalog")

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

        count_catalog(mg, d)

host_cache_save()
catalog_by_country = ip_to_country(catalog_by_ip)

report_section_begin("Catalogs", summary_file = summary_file)
report_cols_begin(summary_file = summary_file)
report_col_begin("l", summary_file = summary_file)
report_by_ip(catalog_by_ip, "catalog", summary_file = summary_file)
report_by_date(catalog_by_date, "catalog", summary_file = summary_file)
report_col_end("l", summary_file = summary_file)
report_col_begin("r", summary_file = summary_file)
report_by_country(catalog_by_country, "catalog", summary_file = summary_file)
report_col_end("r", summary_file = summary_file)
report_cols_end(summary_file = summary_file)

report_by_raw_agent(catalog_by_raw_agent, "catalog", summary_file = summary_file)
report_catalog_by_pkg_version()
report_catalog_by_arch()
report_section_end(summary_file = summary_file)

