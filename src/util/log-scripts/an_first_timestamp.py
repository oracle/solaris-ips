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


"""an_first_timestamp.py - read first line of an Apache HTTPD log, and print 
   Unix timestamp"""

from __future__ import print_function
import datetime
import fileinput
import re
import sys
import time

# Apache combined log pattern
#   Canonical version is in an_report.py
comb_log_pat = re.compile("(?P<ip>[\d\.]*) - - \[(?P<date>[^:]*):(?P<time>\S*) (?P<tz>[^\]]*)\] \"(?P<op>GET|POST|HEAD|\S*) (?P<uri>\S*) HTTP/(?P<httpver>[^\"]*)\" (?P<response>\d*) (?P<subcode>\d*|-) \"(?P<refer>[^\"]*)\" \"(?P<agent>[^\"]*)\"")

lastdate = None
lastdatetime = None
printed = False

for l in fileinput.input(sys.argv[1:]):
        m = comb_log_pat.search(l)
        if not m:
                continue

        mg = m.groupdict()

        d = datetime.datetime(*(time.strptime(mg["date"] + ":" + mg["time"], "%d/%b/%Y:%H:%M:%S")[0:6]))

        print("{0:d}".format(time.mktime(d.timetuple())))
        sys.exit(0)

