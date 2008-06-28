#!/usr/bin/python2.4
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

#
# scan argument files for driver actions; then act as filter, 
# removing lines which contain a driver name in the first
# column
#

import sys, os

def scan_import_file(s):
        for i in include_path:
                f = os.path.join(i, s)
                if os.path.exists(f):
                        file = open(f)
                        break
        else:
                file = open(s)

        for line in file:
                fields = line.split()
                if fields and fields[0] == "include":
                        scan_import_file(fields[1])
                elif len(fields) > 3 and fields[0] == "add" and \
                    fields[1] == "driver":
                        for f in fields[2:]:
		                if f.startswith("name="):
			                driver_names[f[5:]] = True
                                        break
        file.close()

driver_names={}

include_path = sys.argv[1].split(":")

for arg in sys.argv[2:]:
        scan_import_file(arg)

for line in sys.stdin:
        if line.split()[0] not in driver_names:
	        sys.stdout.write(line)

