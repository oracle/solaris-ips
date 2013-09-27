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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

#
# membench - benchmark memory usage of various objects
#

import pkg.fmri as fmri
import pkg.version as version
import sys
import os
import pkg.misc as misc

def dotseq(num):
        return version.DotSequence("5.111111")

def dotseq_different(num):
        return version.DotSequence("5.%d" % num)

def vers(num):
        return version.Version("0.5.11-0.111:20090428T172804Z")

def vers_different(num):
        return version.Version("0.5.11,5.11-0.%d:%08dT172804Z" % (num, num))

def mfmri(num):
        return fmri.PkgFmri("pkg:/SUNWttf-google-droid@0.5.11,5.11-0.121:20090816T233516Z")
                
def mfmri_different(num):
        return fmri.PkgFmri("pkg:/SUNWttf-google-%d@0.5.11,5.11-0.%d:%08dT233516Z" % (num, num, num)) 

collection = []
funcs = [dotseq, dotseq_different, vers, vers_different, mfmri, mfmri_different]

for func in funcs:
        print "#", func.__name__
        pid = os.fork()
        if pid == 0:
                startusage = misc.__getvmusage()
                n = 0
                # Generate a good sized series of valid YYYYMMDD strings
                for y in xrange(1, 10000):
                        for m in xrange(1, 10):
                                for d in xrange(1, 2):
                                        n += 1
                                        collection.append(func(int("%04d%02d%02d" % (y, m, d))))
                endusage = misc.__getvmusage()

                est = (endusage - startusage) / n
                print func.__name__, "%d rounds, estimated memory per object: %d bytes" % (n, est)
                sys.exit(0)
        else:
                os.wait()

