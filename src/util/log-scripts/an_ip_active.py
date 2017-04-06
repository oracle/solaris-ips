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
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#

import six.moves.cPickle as pickle
import datetime
import fileinput
import GeoIP
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
timestamp = "0000000000"
stem = "ip"

entry_by_date = {}
country_by_date = {}

country_by_hashed_ip = {}

gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)

def count_entry(mg, d):
        di = d.date().isoformat()

        ip = mg["ip"]
        cc = gi.country_code_by_addr(ip)

        dip = md5.md5(ip)
        dipd = dip.hexdigest()

        if di in entry_by_date:
                if not dipd in entry_by_date[di]:
                        entry_by_date[di].append(dipd)
        else:
                entry_by_date[di] = [dipd]

opts, args = getopt.getopt(sys.argv[1:], "a:b:S:t:w:")

for opt, arg in opts:
        if opt == "-a":
                try:
                        after = datetime.datetime(*(time.strptime(arg, "%Y-%b-%d")[0:6]))
                except ValueError:
                        after = datetime.datetime(*(time.strptime(arg, "%Y-%m-%d")[0:6]))

        if opt == "-b":
                before = arg

        if opt == "-S":
                stem = arg

        if opt == "-t":
                timestamp = arg

        if opt == "-w":
                active_window = arg

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

        count_entry(mg, d)

# open, trunc
pklfile = open("{0}.{1}.pkl".format(stem, timestamp), "wb")
pickle.dump(entry_by_date, pklfile)
pklfile.close()
