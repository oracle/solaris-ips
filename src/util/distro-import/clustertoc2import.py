#!/usr/bin/python2.6
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

# turns a single input argument which is the path to a Solaris
# clustertoc into a ipkg cluster definition suitable for import

import sys

contents = open(sys.argv[1])
lineno = 0

transform = { 
    "CLUSTER":         ( "package %s", "cluster %s" ),
    "METACLUSTER":     ( "package %s", "cluster %s" ),
    "DESC":            ( 'description "%s"', ),
    "VERSION":         ( "version %s", ),
    "SUNW_CSRMEMBER":  ( "idepend %s", ),
    "END":             ( "end package", ),
    "NAME":            ( ),
    "VENDOR":          ( ),
    "DEFAULT":         ( ),
    "HIDDEN":          ( ),
    "REQUIRED":        ( )
}

for line in contents:
        lineno += 1
        line = line.rstrip()
        fields = line.split("=")

        if fields[0] in transform:
                for fmt in transform[fields[0]]:
                        if "%" in fmt:
                                print fmt % fields[1]
                        else:
			        print fmt
        else:
                raise "unrecognized line %d in file %s: %s" % (lineno, sys.argv[1], line)

