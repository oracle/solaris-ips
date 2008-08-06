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

import os
import sys
import unittest

class BaseLine(object):
        """Test result baseline for determining which tests failed against
        the current state of the source tree.
        """

        sep1 = '=' * 70
        sep2 = '-' * 70

        # dict of "test name" -> "result"
        results = {}

        # Filename to store the results
        filename = ""

        # 'generating' keeps track of whether we are currently generating
        # a baseline or not: if either the baseline doesn't exist or the
        # "-g" option is specified on the commandline.
        #
        generating = False     

        # List of tuples (name, result) for failed tests
        failed_list = []

        def __init__(self, filename="baseline.txt", generate=False):
                self.filename = filename
                self.generating = generate

        def handleresult(self, name, result):
                """Add a result if we're generating the baseline file,
                otherwise check it against the current result set."""
                rv = True
                if self.generating:
                        self.results[name] = result
                else:
                        rv = self.checkresult(name, result)
                return rv

        def getresult(self, name):
                """Retrieve a result by test name."""
                return self.results.get(name, None)

        def checkresult(self, name, result):
                """Check a name/result pair against the current result set,
                adding this test to the list of failures if it doesn't
                match."""
                if self.generating:
                        return True
                res = self.getresult(name)
                rv = (cmp(res, result) == 0)
                if rv != True:
                        self.failed_list.append((name, result))
                return rv

        def getfailures(self):
                """Return the list of failed tests."""
                return self.failed_list

        def reportfailures(self):
                """Display all test cases that failed to match the baseline
                and their result.
                """
                lst = self.getfailures()
                if lst:
                        print >> sys.stderr, ""
                        print >> sys.stderr, self.sep1
                        print >> sys.stderr, "BASELINE MISMATCH: The" \
                            " following results didn't match the baseline." 
                        print >> sys.stderr, self.sep2
                        for name, result in lst:
                                print >> sys.stderr, "%s: %s" % (name, result)
                        print >> sys.stderr, self.sep2
                        print >> sys.stderr, ""
  
        def store(self):
                """Store the result set."""
                # Only store the result set if we're generating a baseline
                if not self.generating:
                        return
                try:
                        f = file(self.filename, "w")
                except IOError, (err, msg):
                        print >> sys.stderr, "ERROR: storing baseline:"
                        print >> sys.stderr, "Failed to open %s: %s" % \
                                (self.filename, msg)
                        return 

		# Sort the results to make baseline diffs easier
		results_sorted = self.results.keys()
		results_sorted.sort()
	
                for s in results_sorted:
                        f.write("%s|%s%s" %
                            (s, self.results[s], os.linesep))
                f.flush()
                f.close()

        def load(self):
                """Load the result set."""
                if not os.path.exists(self.filename):
                        self.generating = True
                        return

                try:
                        f = file(self.filename, "r")
                except IOError, (err, msg):
                        print >> sys.stderr, "ERROR: loading baseline:"
                        print >> sys.stderr, "Failed to open %s: %s" % \
                                (self.filename, msg)
                        return
                for line in f.readlines():
                        n, r = line.split('|')
                        self.results[n] = r.rstrip('\n')
                f.close()
