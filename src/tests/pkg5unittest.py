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

import baseline
import string
import sys
import unittest

OUTPUT_DOTS=0           # Dots ...
OUTPUT_VERBOSE=1        # Verbose
OUTPUT_PARSEABLE=2      # Machine readable

class Pkg5TestCase(unittest.TestCase):
        def __init__(self, methodName='runTest'):
                super(Pkg5TestCase, self).__init__(methodName)
                self.__testMethodName = methodName

        def __str__(self):
                return "%s.py %s.%s" % (self.__class__.__module__,
                    self.__class__.__name__, self.__testMethodName)

class _Pkg5TestResult(unittest._TextTestResult):
        baseline = None
        machsep = "|"
        def __init__(self, stream, output, baseline):
                unittest.TestResult.__init__(self)
                self.stream = stream
                self.output = output
                self.baseline = baseline
                
        def addSuccess(self, test):
                unittest.TestResult.addSuccess(self, test)
                bresult = self.baseline.handleresult(str(test), "pass")
                if self.output == OUTPUT_VERBOSE or \
                    self.output == OUTPUT_PARSEABLE:
                        res = ""
                        if bresult == True:
                                res = "pass"
                        else:
                                res = "pass (FAIL)"
                        self.stream.writeln(res)
                elif self.output == OUTPUT_DOTS:
                        self.stream.write('.')

        def addError(self, test, err):
                unittest.TestResult.addError(self, test, err)
                if self.output == OUTPUT_VERBOSE or \
                    self.output == OUTPUT_PARSEABLE:
                        self.stream.writeln("ERROR")
                elif self.output == OUTPUT_DOTS:
                        self.stream.write('E')
                bresult = self.baseline.handleresult(str(test), "error")

        def addFailure(self, test, err):
                unittest.TestResult.addFailure(self, test, err)
                bresult = self.baseline.handleresult(str(test), "fail")
                if self.output == OUTPUT_VERBOSE or \
                    self.output == OUTPUT_PARSEABLE:
                        res = ""
                        if bresult == True:
                                res = "FAIL (pass)"
                        else:
                                res = "FAIL"
                        self.stream.writeln(res)
                elif self.output == OUTPUT_DOTS:
                        self.stream.write('F')

        def getDescription(self, test):
                return str(test)

        def startTest(self, test):
                unittest.TestResult.startTest(self, test)
                if not self.output == OUTPUT_DOTS:
                        self.stream.write(
                            string.ljust(self.getDescription(test), 60))
                if self.output == OUTPUT_VERBOSE:
                        self.stream.write("   ")
                if self.output == OUTPUT_PARSEABLE:
                        self.stream.write(" | ")
                self.stream.flush()

        def printErrors(self):
                self.stream.writeln()
                self.printErrorList('ERROR', self.errors)
                self.printErrorList('FAIL', self.failures)

        def printErrorList(self, flavour, errors):
                for test, err in errors:
                        self.stream.writeln(self.separator1)
                        self.stream.writeln("%s: %s" %
                            (flavour, self.getDescription(test)))
                        self.stream.writeln(self.separator2)
                        self.stream.writeln("%s" % err)

class Pkg5TestRunner(unittest.TextTestRunner):
        """TestRunner for test suites that we want to be able to compare
        against a result baseline."""
        baseline = None
        sep1 = '=' * 70
        sep2 = '-' * 70

        def __init__(self, suite, stream=sys.stderr, output=OUTPUT_DOTS,
            generate=False):
                """Set up the runner, creating a baseline object that has
                a name of 'suite'_baseline.pkl, where suite is 'cli', 'api',
                etc."""
                # output is one of "dots", "verbose", "machine"
                super(Pkg5TestRunner, self).__init__(stream)
                # Make sure we have no spaces in the filename
                self.suite = suite.replace(" ", "_")
                self.baseline = baseline.BaseLine(
                    "%s_baseline.txt" % self.suite, generate=generate)
                self.baseline.load()
                self.output = output

        def _makeResult(self):
                return _Pkg5TestResult(self.stream, self.output, self.baseline)

        def run(self, test):
                res = super(Pkg5TestRunner, self).run(test)
                self.baseline.store()
                self.baseline.reportfailures()
                return res


