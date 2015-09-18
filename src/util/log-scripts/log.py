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
import os
import getopt
import re
import socket
import sys

codes_200 = {}
codes_206 = {}
codes_other = {}

totals = {}
totals["dl"] = 0

hosts = {}


def process(l):
        """Process one Apache common log line."""
        ex = "([\d\.]*) - - \[([^\]]*)\] \"([A-Z]*) (.*) HTTP/1\..\" (\d\d\d) (\d*)"
        m = re.match(ex, l)

        totals["dl"] += int(m.group(6))
        hosts[m.group(1)] = 1

        if m.group(5) == "200":
                try:
                        codes_200[m.group(1)].append(int(m.group(6)))
                except KeyError:
                        codes_200[m.group(1)] = [ int(m.group(6)) ]

        elif m.group(5) == "206":
                try:
                        codes_206[m.group(1)].append(int(m.group(6)))
                except KeyError:
                        codes_206[m.group(1)] = [ int(m.group(6)) ]

        else:
                try:
                        codes_other[m.group(1)].append(m.group(5))
                except KeyError:
                        codes_other[m.group(1)] = [m.group(5)]

def dlunits(codes, size):
        n = 0

        for k in codes.keys():
                if sum(codes[k]) >= size:
                        n +=1

        return n

def dls_linked(codes_200, codes_206, size):
        linked = 0
        for k in codes_206.keys():
                if k in codes_200.keys():
                        total = sum(codes_200[k]) + sum(codes_206[k])
                        if total > size:
                                linked += total//size

                        if total > 10 * size:
                                try:
                                        host = socket.gethostbyaddr(k)[0],
                                        print(host)
                                except:
                                        pass

        return linked

if __name__ == "__main__":
        opts, pargs = getopt.getopt(sys.argv[1:], "f:s:")

        size = None
        fname = None

        for opt, arg in opts:
                if opt == "-f":
                        fname = arg
                if opt == "-s":
                        size = int(arg)

        assert not fname == None

        lg = open(fname)

        for l in lg.readlines():
                process(l)

        print("distinct hosts:  {0:d}".format(len(hosts.keys())))
        print("200 requests:  {0:d}".format(len(codes_200.keys())))
        print("206 requests:  {0:d}".format(len(codes_206.keys())))
        print("other requests:  {0:d}".format(len(codes_other.keys())))

        if not size:
                sys.exit(0)

        print("200 units: {0:d}".format(dlunits(codes_200, size)))
        print("206 units: {0:d}".format(dlunits(codes_206, size)))

        print("linked units: {0:d}".format(dls_linked(codes_200, codes_206, size)))

        print("total units: {0:d}".format(totals["dl"] // size))

