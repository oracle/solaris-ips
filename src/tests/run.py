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
# We need to execute this from the tests directory
if os.path.basename(os.getcwd()) != "tests":
        os.putenv('PYEXE', sys.executable)
        os.chdir(os.path.join(os.getcwd(), "tests"))
        import subprocess
        cmd = [sys.executable, "run.py"]
        cmd.extend(sys.argv[1:]) # Skip argv[0]
        sys.exit(subprocess.call(cmd))

import baseline
import getopt
import pkg5unittest
import platform
import re
import subprocess
import tempfile
import types
import unittest

# Make sure current directory is in the path
sys.path.insert(0, ".")

import cli.testutils
import gui.testutils

if __name__ == "__main__":
        cli.testutils.setup_environment("../../proto")

osname = platform.uname()[0].lower()
arch = 'unknown' 
if osname == 'sunos':
        arch = platform.processor()
elif osname == 'linux':
        arch = "linux_" + platform.machine()
elif osname == 'windows':
        arch = osname
elif osname == 'darwin':
        arch = osname
elif osname == "aix":
        arch = osname

ostype = os.name
if ostype == '':
        ostype = 'unknown'

def find_tests(testdir, testpat, startatpat=False):
        # Test pattern to match against
        pat = re.compile("%s" % testpat, re.IGNORECASE)
        startatpat = re.compile("%s" % startattest, re.IGNORECASE)
        seen = False

        def _istest(obj):
                if (isinstance(obj, type) and 
                    issubclass(obj, unittest.TestCase)):
                        return True
                return False
        def _istestmethod(name, obj):
                if name.startswith("test") and \
                    isinstance(obj, types.MethodType):
                        return True
                return False

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        testclasses = []
        # "testdir" will be "api", "cli", etc., so find all the files in that 
        # directory that match the pattern "t_*.py".
        for f in os.listdir(testdir):
                if not (f.startswith("t_") and f.endswith(".py")):
                        continue
                name = os.path.join(testdir, f)
                name = name.replace(".py", "")
                name = '.'.join(name.split(os.path.sep))
                try:
                        obj = __import__(name)
                except ImportError, e:
                        print "Skipping %s: %s" % (name, e.__str__())
                        continue
                print "Loading tests from: %s" % name
                # "api.t_filter" -> ["api", "t_filter"]
                suitename, filename = name.split(".")
                # file object (t_filter, etc)
                fileobj = getattr(obj, filename)
                # Get all the classes from the file
                for cname in dir(fileobj):
                        # Get the actual class object
                        classobj = getattr(fileobj, cname)
                        # Make sure it's a test case
                        if not _istest(classobj):
                                continue
                        for attrname in dir(classobj):
                                methobj = getattr(classobj, attrname)
                                # Make sure its a test method
                                if not _istestmethod(attrname, methobj):
                                        continue
                                full = "%s.%s.%s.%s" % (testdir,
                                    filename, cname, attrname)
                                # Remove this function from our class obj if
                                # it doesn't match the test pattern
                                if re.search(startatpat, full):
                                        seen = True
                                if not seen:
                                        delattr(classobj, attrname)
                                if not re.search(pat, full):
                                        delattr(classobj, attrname)
                        testclasses.append(classobj)
                        
        for cobj in testclasses:
                suite.addTest(unittest.makeSuite(cobj, 'test',
                    suiteClass=pkg5unittest.Pkg5TestSuite))

        return suite

def usage():
        print >> sys.stderr, "Usage: %s [-ghptv] [-b filename] [-o regexp]" \
                % sys.argv[0]
        print >> sys.stderr, "       %s [-hptvx] [-b filename] [-s regexp] "\
                "[-o regexp]" % sys.argv[0]
        print >> sys.stderr, "   -g             Generate result baseline"
        print >> sys.stderr, "   -h             This help message"
        print >> sys.stderr, "   -p             Parseable output format"
        print >> sys.stderr, "   -t             Generate timing info file"
        print >> sys.stderr, "   -v             Verbose output"
        print >> sys.stderr, "   -x             Stop after the first failure"
        print >> sys.stderr, "   -b <filename>  Baseline filename"
        print >> sys.stderr, "   -o <regexp>    Run only tests that match regexp"
        print >> sys.stderr, "   -s <regexp>    Run tests starting at regexp"
        print >> sys.stderr, ""
        sys.exit(1)

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ghptvxb:os:",
                    ["generate-baseline", "parseable", "timing", "verbose",
                    "baseline-file", "only"])
        except getopt.GetoptError, e:
                print >> sys.stderr, "Illegal option -- %s" % e.opt
                sys.exit(1)

        bfile = os.path.join(os.getcwd(), "baseline.txt")
        generate = False
        onlyval = ""
        output = pkg5unittest.OUTPUT_DOTS
        bailonfail = False
        startattest = ""
        timing_file = False
        for opt, arg in opts:
                if opt == "-v":
                        output = pkg5unittest.OUTPUT_VERBOSE
                if opt == "-p":
                        output = pkg5unittest.OUTPUT_PARSEABLE
                if opt == "-g":
                        generate = True
                if opt == "-b":
                        bfile = arg
                if opt == "-o":
                        onlyval = arg
                if opt == "-x":
                        bailonfail = True
                if opt == "-t":
                        timing_file = True
                if opt == "-s":
                        startattest = arg
                if opt == "-h":
			usage()
        if (bailonfail or startattest) and generate:
                usage()

        import pkg.portable

        if not pkg.portable.is_admin():
                print >> sys.stderr, "WARNING: You don't seem to be root." \
                    " Some tests may fail."
        else:
                ppriv = "/usr/bin/ppriv"
                if os.path.exists(ppriv):
                        # One of the tests actually calls unlink() on a directory,
                        # and expects it to fail as it does on ZFS, but on tmpfs
                        # it scarily succeeds.
                        subprocess.call([
                            ppriv, "-s", "A-sys_linkdir", str(os.getpid())
                        ])

        api_suite = find_tests("api", onlyval, startattest)
        cli_suite = find_tests("cli", onlyval, startattest)

        suites = []
        suites.append(api_suite)
        if ostype == "posix":
                suites.append(cli_suite)
                if not gui.testutils.check_for_gtk():
                        print "GTK not present, GUI tests disabled."
                elif not gui.testutils.check_if_a11y_enabled():
                        print "Accessibility not enabled, GUI tests disabled."
                else:
                        gui_suite = find_tests("gui", onlyval, startattest)
                        suites.append(gui_suite)

        # Initialize the baseline results and load them
        baseline = baseline.BaseLine(bfile, generate)
        baseline.load()

        # Make sure we capture stdout
        testlogfd, testlogpath = tempfile.mkstemp(suffix='.pkg-test.log')
        testlogfp = os.fdopen(testlogfd, "w")
        print "logging to %s" % testlogpath
        sys.stdout = testlogfp

        if timing_file:
                timing_file = os.path.join(os.getcwd(), "timing_info.txt")
                if os.path.exists(timing_file):
                        os.remove(timing_file)
        
        # Run the python test suites
        runner = pkg5unittest.Pkg5TestRunner(baseline, output=output,
            timing_file=timing_file, bailonfail=bailonfail)
        exitval = 0
        for x in suites:
                try:
                    res = runner.run(x)
                except pkg5unittest.Pkg5TestCase.failureException, e:
                    exitval = 1
                    print >> sys.stderr, e
                    break
                if res.failures:
                        exitval = 1

        testlogfp.close()

        # Update baseline results and display mismatches (failures)
        baseline.store()
        baseline.reportfailures()

        sys.exit(exitval)
