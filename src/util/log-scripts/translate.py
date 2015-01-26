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
import GeoIP
import md5
import sys
import time

# Translate an apache log line into a format that is smaller and easier to parse:
# <ip md5> <country code> <date> <operation> <operation args> <size>
#
# Apache log format:
# 1.2.3.4 - - [12/Aug/2008:19:21:28 -0700] "GET /manifest/0/SUNWkos@0.5.11%2C5.11-0.94%3A20080721T212150Z HTTP/1.1" 200 19748 "-" "pkg/d974bb176266 (sunos i86pc; 5.11 snv_86; full)"

if len(sys.argv) != 3:
        print("Usage: {0} <in file> <out file>".format(sys.argv[0]))
        sys.exit(2)

infile = open(sys.argv[1], "r")
outfile = open(sys.argv[2], "w")

gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)

ops = ["1p.png", "filelist", "catalog", "manifest", "search", "file"] 

cnt = {}
for x in ops:
        cnt[x] = 0

while True:
        line = infile.readline()
        if len(line) == 0: # EOF
                break

        #print("line: [{0}]".format(line))

        fields = line.split()
        (ip, d, fullop) = (fields[0], fields[3], fields[6])
        del fields

        # Get country code and translate ip -> md5 of ip
        cc = gi.country_code_by_addr(ip)
        ip = md5.md5(ip)
        ip = ip.hexdigest()

        # Goofy date -> UTS
        d = time.mktime(time.strptime(d[1:], "%d/%b/%Y:%H:%M:%S"))
        d = str(d).split(".")[0]

        # Figure out op and opargs
        opflds = fullop.split("/")
        op = opflds[1]
        if "1p.png" in op:
                op = op[0:op.find("?")]
        if op not in ops:
                continue
        # only interested in catalog/0 operations
        if op == "catalog" and opflds[2] != "0":
                continue
        opargs = ""
        if op == "search":
                opargs = "/".join(opflds[3:])
        if op == "file":
                opargs = opflds[3]

        # TODO: also need to grab size

        cnt[op] += 1

        print("{0} {1} {2} {3} {4}".format(ip, cc, d, op, opargs), file=outfile)

infile.close()
outfile.close()

for x in ops:
        print("# {0}: {1:d}".format(x, cnt[x]))

