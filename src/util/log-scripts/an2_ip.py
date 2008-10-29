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

import datetime
import fileinput
import sys
import os

from an_report import *

total_by_ip = {}

ip_files = [ "%s-ip.dat" % i for i in sys.argv[2:] ]
ip_files = [ i for i in ip_files if os.path.exists(i) ]

for l in fileinput.input(ip_files):
        x = l.split()

        try:
                total_by_ip[x[1]] += int(x[0])
        except KeyError:
                total_by_ip[x[1]] = int(x[0])

total_by_country = ip_to_country(total_by_ip)

report_section_begin("Summary")
report_cols_begin()
report_col_begin("l")
report_by_ip(total_by_ip, "all non-filelist")
report_col_end("l")
report_col_begin("r")
report_by_country(total_by_country, "all")
report_col_end("r")
report_cols_end()
report_section_end()
