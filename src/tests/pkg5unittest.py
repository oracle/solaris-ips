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
import time
import unittest

OUTPUT_DOTS=0           # Dots ...
OUTPUT_VERBOSE=1        # Verbose
OUTPUT_PARSEABLE=2      # Machine readable

class SuccessfulException(Exception):
        """An exception for situations where raising an exception is the
        correct behavior for a test in the test suite. This is useful for
        testing the testsuite behavior itself, but should not be used in
        testing other code."""
        pass

class Pkg5TestCase(unittest.TestCase):
        def __init__(self, methodName='runTest'):
                super(Pkg5TestCase, self).__init__(methodName)
                self.__testMethodName = methodName

        def __str__(self):
                return "%s.py %s.%s" % (self.__class__.__module__,
                    self.__class__.__name__, self.__testMethodName)

        def run(self, result=None):
                # The only difference between this code and the original
                # code in unittest.TestCase.run is that
                # except SuccessfulException: has been added and counted as
                # a successful test.
                if result is None:
                        result = self.defaultTestResult()
                result.startTest(self)
                testMethod = getattr(self, self._TestCase__testMethodName)
                try:
                        try:
                                self.setUp()
                        except KeyboardInterrupt:
                                raise
                        except SuccessfulException:
                                result.addSuccess(self)
                                return
                        except:
                                result.addError(self, self._TestCase__exc_info())
                                return

                        ok = False
                        try:
                                testMethod()
                                ok = True
                        except self.failureException:
                                result.addFailure(self, self._TestCase__exc_info())
                        except KeyboardInterrupt:
                                raise
                        except:
                                result.addError(self, self._TestCase__exc_info())

                        try:
                                self.tearDown()
                        except KeyboardInterrupt:
                                raise
                        except:
                                result.addError(self, self._TestCase__exc_info())
                                ok = False
                        if ok:
                                result.addSuccess(self)
                finally:
                        result.stopTest(self)

class _Pkg5TestResult(unittest._TextTestResult):
        baseline = None
        machsep = "|"
        def __init__(self, stream, output, baseline):
                unittest.TestResult.__init__(self)
                self.stream = stream
                self.output = output
                self.baseline = baseline
                self.success = []

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
                self.success.append(test)

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

        def __init__(self, baseline, stream=sys.stderr, output=OUTPUT_DOTS):
                """Set up the runner, creating a baseline object that has
                a name of 'suite'_baseline.pkl, where suite is 'cli', 'api',
                etc."""
                # output is one of "dots", "verbose", "machine"
                super(Pkg5TestRunner, self).__init__(stream)
                self.baseline = baseline
                self.output = output

        def _makeResult(self):
                return _Pkg5TestResult(self.stream, self.output, self.baseline)

        def run(self, test):
                "Run the given test case or test suite."
                result = self._makeResult()
                startTime = time.time()
                test(result)
                stopTime = time.time()
                timeTaken = stopTime - startTime
                result.printErrors()
                self.stream.writeln(result.separator2)
                run = result.testsRun
                self.stream.writeln("Ran %d test%s in %.3fs" %
                    (run, run != 1 and "s" or "", timeTaken))
                self.stream.writeln()
                if not result.wasSuccessful():
                        self.stream.write("FAILED (")
                        success, failed, errored, mismatches = map(len,
                            (result.success, result.failures, result.errors,
                                self.baseline.getfailures()))
                        self.stream.write("successes=%d, " % success)
                        self.stream.write("failures=%d, " % failed)
                        self.stream.write("errors=%d, " % errored)
                        self.stream.write("mismatches=%d" % mismatches)
                        self.stream.writeln(")")
                else:
                        self.stream.writeln("OK")
                return result
