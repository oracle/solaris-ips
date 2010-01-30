#!/usr/bin/python2.6 -u
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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import sys

# We need cwd to be the same dir as our program.
if os.path.dirname(__file__) != "" and \
    os.path.dirname(__file__) != ".":
        os.putenv('PYEXE', sys.executable)
        os.chdir(os.path.dirname(__file__))
        import subprocess
        cmd = [sys.executable, "run.py"]
        cmd.extend(sys.argv[1:]) # Skip argv[0]
        sys.exit(subprocess.call(cmd))

#
# Some modules we use are located in our own proto area.  So before doing
# any more imports, setup the environment we need.
#

# Make sure current directory is in the path
sys.path.insert(0, ".")

import pkg5testenv
if __name__ == "__main__":
        pkg5testenv.setup_environment("../../proto")

import baseline
import fcntl
import getopt
import platform
import re
import shutil
import subprocess
import tempfile
import types
import unittest
import warnings

import pkg5unittest
from pkg5unittest import OUTPUT_DOTS, OUTPUT_VERBOSE, OUTPUT_PARSEABLE
import coverage

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


def find_tests(testdir, testpats, startatpat=False, output=OUTPUT_DOTS):
        # Test pattern to match against
        pats = [ re.compile("%s" % pat, re.IGNORECASE) for pat in testpats ]
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

        def _vprint(*text):
                if output == OUTPUT_VERBOSE or output == OUTPUT_PARSEABLE:
                        print ' '.join([str(l) for l in text]),

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        testclasses = []
        # "testdir" will be "api", "cli", etc., so find all the files in that 
        # directory that match the pattern "t_*.py".
        _vprint("# Loading %s tests:\n" % testdir)
        curlinepos = 0
        for f in sorted(os.listdir(testdir)):
                if curlinepos == 0:
                        _vprint("#        ")
                        curlinepos += 9

                if not (f.startswith("t_") and f.endswith(".py")):
                        continue
                name = os.path.join(testdir, f)
                name = name.replace(".py", "")
                name = '.'.join(name.split(os.path.sep))
                # "api.t_filter" -> ["api", "t_filter"]
                suitename, filename = name.split(".")

                try:
                        obj = __import__(name)
                except ImportError, e:
                        print "Skipping %s: %s" % (name, str(e))
                        continue

                if curlinepos != 0 and (curlinepos + len(filename) + 1) >= 78:
                        _vprint("\n#        ")
                        curlinepos = 9
                _vprint("%s" % filename,)
                curlinepos += len(filename) + 1

                # file object (t_filter, etc)
                fileobj = getattr(obj, filename)
                # Get all the classes from the file
                for cname in dir(fileobj):
                        # Get the actual class object
                        classobj = getattr(fileobj, cname)
                        # Make sure it's a test case
                        if not _istest(classobj):
                                continue

                        # We tack this in for pretty-printing.
                        classobj._Pkg5TestCase__suite_name = suitename

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
                                found = reduce(lambda x, y: x or y,
                                    [ re.search(pat, full) for pat in pats ],
                                    None)
                                if not found:
                                        delattr(classobj, attrname)
                        testclasses.append(classobj)
        _vprint("\n#\n")
                        
        for cobj in testclasses:
                suite.addTest(unittest.makeSuite(cobj, 'test',
                    suiteClass=pkg5unittest.Pkg5TestSuite))

        return suite

def usage():
        print >> sys.stderr, "Usage: %s [-cghptv] [-b filename] [-o regexp]" \
                % sys.argv[0]
        print >> sys.stderr, "       %s [-chptvx] [-b filename] [-s regexp] "\
                "[-o regexp]" % sys.argv[0]
        print >> sys.stderr, \
"""   -a <dir>       Archive failed test cases to <dir>/$pid/$testcasename
   -c             Collect code coverage data
   -d             Show debug output, including commands run, and outputs
   -f             Show fail/error information even when test is expected to fail
   -g             Generate result baseline
   -h             This help message
   -p             Parseable output format
   -t             Generate timing info file
   -v             Verbose output
   -x             Stop after the first baseline mismatch
   -b <filename>  Baseline filename
   -o <regexp>    Run only tests that match regexp
   -s <regexp>    Run tests starting at regexp
"""
        sys.exit(2)

if __name__ == "__main__":
        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:

                #
                # !!! WARNING !!!
                #
                # If you add options here, you need to also update setup.py's
                # test_func to include said options.
                #
                opts, pargs = getopt.getopt(sys.argv[1:], "a:cdfghptvxb:o:s:",
                    ["generate-baseline", "parseable", "timing", "verbose",
                    "baseline-file", "only"])
        except getopt.GetoptError, e:
                print >> sys.stderr, "Illegal option -- %s" % e.opt
                sys.exit(1)

        bfile = os.path.join(os.getcwd(), "baseline.txt")
        generate = False
        onlyval = []
        output = OUTPUT_DOTS
        bailonfail = False
        startattest = ""
        timing_file = False
        do_coverage = False
        debug_output = False
        show_on_expected_fail = False
        archive_dir = None

        for opt, arg in opts:
                if opt == "-v":
                        output = OUTPUT_VERBOSE
                if opt == "-p":
                        output = OUTPUT_PARSEABLE
                if opt == "-c":
                        do_coverage = True
                if opt == "-d":
                        pkg5unittest.g_debug_output = True
                if opt == "-f":
                        show_on_expected_fail = True
                if opt == "-g":
                        generate = True
                if opt == "-b":
                        bfile = arg
                if opt == "-o":
                        onlyval.append(arg)
                if opt == "-x":
                        bailonfail = True
                if opt == "-t":
                        timing_file = True
                if opt == "-s":
                        startattest = arg
                if opt == "-a":
                        archive_dir = arg
                if opt == "-h":
			usage()
        if (bailonfail or startattest) and generate:
                usage()
        if not onlyval:
                onlyval = [ "" ]

        # Set up coverage directory and start code coverage for the API tests.
        if do_coverage:
                covdir = tempfile.mkdtemp(prefix=".coverage-", dir=os.getcwd())
                os.chmod(covdir, 01777)
                cov_file = "%s/pkg5" % covdir
                cov = coverage.coverage(data_file=cov_file, data_suffix=True)
                cov.start()

        # Allow relative archive dir, but first convert it to abs. paths.
        if archive_dir is not None:
                archive_dir = os.path.abspath(archive_dir)
                if not os.path.exists(archive_dir):
                        os.makedirs(archive_dir)

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

        api_suite = find_tests("api", onlyval, startattest, output)
        cli_suite = find_tests("cli", onlyval, startattest, output)

        suites = []
        suites.append(api_suite)
        if ostype == "posix":
                suites.append(cli_suite)
                import gui.testutils
                if not gui.testutils.check_for_gtk():
                        print "# GTK not present or $DISPLAY not " \
                            "set, GUI tests disabled."
                elif not gui.testutils.check_if_a11y_enabled():
                        print "# Accessibility not enabled, GUI tests disabled."
                else:
                        gui_suite = find_tests("gui", onlyval,
                            startattest, output)
                        suites.append(gui_suite)

        # This is primarily of interest to developers altering the test suite,
        # so don't enable it for now.  The testsuite suite tends to emit a bunch
        # of harmless but noisy errors to the screen due to the way it exercises
        # various corner cases.
        #testsuite_suite = find_tests("testsuite", onlyval, startattest, output)
        #suites.append(testsuite_suite)

        # Initialize the baseline results and load them
        baseline = baseline.BaseLine(bfile, generate)
        baseline.load()

        # Make sure we capture stdout
        testlogfd, testlogpath = tempfile.mkstemp(suffix='.pkg-test.log')
        testlogfp = os.fdopen(testlogfd, "w")
        print "# logging to %s" % testlogpath
        sys.stdout = testlogfp

        if timing_file:
                timing_file = os.path.join(os.getcwd(), "timing_info.txt")
                if os.path.exists(timing_file):
                        os.remove(timing_file)

        # Set up coverage for cli tests
        if do_coverage:
                cov_env = {
                    "COVERAGE_FILE": "%s/pkg5" % covdir
                }
                cov_cmd = "coverage run -p"
        else:
                cov_env = {}
                cov_cmd = ""
        
        # Run the python test suites
        runner = pkg5unittest.Pkg5TestRunner(baseline, output=output,
            timing_file=timing_file,
            bailonfail=bailonfail,
            coverage=(cov_cmd, cov_env),
            show_on_expected_fail=show_on_expected_fail,
            archive_dir=archive_dir)
        exitval = 0
        for x in suites:
                try:
                        res = runner.run(x)
                except pkg5unittest.Pkg5TestCase.failureException, e:
                        exitval = 1
                        print >> sys.stderr
                        print >> sys.stderr, e
                        break
                except pkg5unittest.TestStopException, e:
                        exitval = 1
                        print >> sys.stderr
                        break
                if res.mismatches:
                        exitval = 1

        testlogfp.close()

        # Update baseline results and display mismatches (failures)
        baseline.store()
        baseline.reportfailures()

        # Stop and save coverage data for API tests, and combine coverage data
        # from all processes.
        if do_coverage:
                cov.stop()
                cov.save()
                newenv = os.environ.copy()
                newenv.update(cov_env)
                subprocess.Popen(["coverage", "combine"], env=newenv).wait()
                os.rename("%s/pkg5" % covdir, ".coverage")
                shutil.rmtree(covdir)
                print >> sys.stderr, "Generating html coverage report"
                vp = pkg5unittest.g_proto_area + "/usr/lib/python2.6/vendor-packages"
                omits = [
                    # External modules
                    "%s/cherrypy" % vp,
                    "%s/ply" % vp,
                    "%s/mako" % vp,
                    # This removes test-related stuff, as well as compiled
                    # expressions such as Mako templates and filters.
                    ""
                ]
                subprocess.Popen(["coverage", "html", "--omit", ",".join(omits),
                    "-d", "htmlcov"]).wait()
                # The coverage data file and report are most likely owned by
                # root, if a true test run was performed.  Make the files owned
                # by the owner of the test directory, so they can be easily
                # removed.
                try:
                        uid, gid = os.stat(".")[4:6]
                        os.chown("htmlcov", uid, gid)
                        os.chown(".coverage", uid, gid)
                        for f in os.listdir("htmlcov"):
                                os.chown("htmlcov/%s" % f, uid, gid)
                except EnvironmentError:
                        pass

        sys.exit(exitval)
