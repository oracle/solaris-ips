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
# Copyright (c) 2010, 2023, Oracle and/or its affiliates.
#

import os
import sys
import unittest

BASELINE_MATCH = 0
BASELINE_MISMATCH = 1

class BaseLine(object):
    """Test result baseline recording and checking. """
    sep1 = '=' * 70
    sep2 = '-' * 70

    def __init__(self, filename="baseline.txt", generate=False):

        # filename from which to get or store baseline results
        self.__filename = filename
        # 'generating' keeps track of whether we are currently
        # generating a baseline or not: if either the baseline doesn't
        # exist or the "-g" option is specified on the commandline.
        self.__generating = generate
        # List of tuples (name, result) for failed tests
        self.__failed_list = []
        # dict of "test name" -> "result"
        self.__results = {}

    def handleresult(self, name, actualresult):
        """Add a result if we're generating the baseline file,
        otherwise check it against the current result set.
        Returns a value to indicate whether the result matched
        the baseline."""

        if self.__generating:
            self.__results[name] = actualresult
            return BASELINE_MATCH

        if self.expectedresult(name) != actualresult:
            self.__failed_list.append((name, actualresult))
            return BASELINE_MISMATCH
        return BASELINE_MATCH

    def expectedresult(self, name):
        # The assumption if we're generating, or if we don't
        # have a result in baseline, is that the test should pass.
        if self.__generating:
            return "pass"
        return self.__results.get(name, "pass")

    def getfailures(self):
        """Return the list of failed tests."""
        return self.__failed_list

    def reportfailures(self):
        """Display all test cases that failed to match the baseline
        and their result.
        """
        lst = self.getfailures()
        if lst:
            print("", file=sys.stderr)
            print(self.sep1, file=sys.stderr)
            print("BASELINE MISMATCH: The following results didn't "
             "match the baseline.", file=sys.stderr)
            print(self.sep2, file=sys.stderr)
            for name, result in lst:
                print("{0}: {1}".format(name, result), file=sys.stderr)
            print(self.sep2, file=sys.stderr)
            print("", file=sys.stderr)

    def store(self):
        """Store the result set."""
        # Only store the result set if we're generating a baseline
        if not self.__generating:
            return
        try:
            f = open(self.__filename, "w")
        except IOError as xxx_todo_changeme:
            (err, msg) = xxx_todo_changeme.args
            print("ERROR: storing baseline:", file=sys.stderr)
            print("Failed to open {0}: {1}".format(
                self.__filename, msg), file=sys.stderr)
            return

        # Sort the results to make baseline diffs easier
        results_sorted = list(self.__results.keys())
        results_sorted.sort()
        print("# Writing baseline to {0}.".format(self.__filename),
            file=sys.stderr)
        for s in results_sorted:
            f.write("{0}|{1}{2}".format(
                s, self.__results[s], os.linesep))
        f.flush()
        f.close()

    def load(self):
        """Load the result set."""
        if not os.path.exists(self.__filename):
            self.__generating = True
            return

        try:
            f = open(self.__filename, "r")
        except IOError as xxx_todo_changeme1:
            (err, msg) = xxx_todo_changeme1.args
            print("ERROR: loading baseline:", file=sys.stderr)
            print("Failed to open {0}: {1}".format(
                self.__filename, msg), file=sys.stderr)
            return
        for line in f.readlines():
            n, r = line.split('|')
            self.__results[n] = r.rstrip('\n')
        f.close()

class ReadOnlyBaseLine(BaseLine):
    def store(self):
        raise NotImplementedError()
