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
#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import pkg.fmri
import sys

def usage():
        print >> sys.stderr, "usage: %s <fmri1> <fmri2>" % sys.argv[0]
        sys.exit(2)

if len(sys.argv) != 3:
        usage()

try:
        x = pkg.fmri.PkgFmri(sys.argv[1])
        y = pkg.fmri.PkgFmri(sys.argv[2])
except pkg.fmri.FmriError, e:
        print >> sys.stderr, "error: %s" % str(e)
        sys.exit(1)

if not x.is_same_pkg(y):
        print >> sys.stderr, \
            "error: can only compare two versions of the same package."
        sys.exit(1)

if x < y:
        print "<"
elif x > y:
        print ">"
elif x == y:
        print "="
else:
        print >> sys.stderr, "panic"
        sys.exit(1)

sys.exit(0)
