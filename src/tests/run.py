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
import getopt
import os
import pkg5unittest
import platform
import re
import subprocess
import sys
import tempfile
import unittest

# Include the current directory in the python path
here = os.path.dirname(__file__)
# Make sure this points to something reasonable
if here == "":
        here = "."
sys.path.insert(0, here)

import cli.testutils
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

ostype = os.name
if ostype == '':
        ostype = 'unknown'

def add_tests(tests, testpat):
        suite = unittest.TestSuite()
        pat = re.compile(".*%s.*" % testpat, re.IGNORECASE)
        for t in tests:
                if re.match(pat, str(t)):
                        suite.addTest(unittest.makeSuite(t, 'test'))
        return suite

def make_api_tests(testpat):
        import api.t_action
        import api.t_catalog
        import api.t_filter
        import api.t_fmri
        import api.t_imageconfig
        import api.t_manifest
        import api.t_misc
        import api.t_pkgtarfile
        import api.t_plat
        import api.t_repositoryconfig
        import api.t_smf
        import api.t_version

        tests = [
            api.t_action.TestActions,
            api.t_catalog.TestCatalog,
            api.t_catalog.TestEmptyCatalog,
            api.t_catalog.TestCatalogRename,
            api.t_catalog.TestUpdateLog,
            api.t_filter.TestFilter,
            api.t_fmri.TestFMRI,
            api.t_imageconfig.TestImageConfig,
            api.t_manifest.TestManifest,
            api.t_misc.TestMisc,
            api.t_pkgtarfile.TestPkgTarFile,
            api.t_plat.TestPlat,
            api.t_repositoryconfig.TestRepositoryConfig,
            api.t_smf.TestSMF,
            api.t_version.TestVersion ]

        return add_tests(tests, testpat)

def make_cli_tests(testpat):
        import cli.t_actions
        import cli.t_circular_dependencies
        import cli.t_depot
        import cli.t_depotcontroller
        import cli.t_image_create
        import cli.t_info_contents
        import cli.t_search
        import cli.t_pkg_install_basics
        import cli.t_pkg_install_corrupt_image
        import cli.t_pkgsend
        import cli.t_pkg_list
        import cli.t_commandline
        import cli.t_upgrade
        import cli.t_recv
        import cli.t_rename
        import cli.t_twodepot
        import cli.t_setUp

        tests = [
            cli.t_actions.TestPkgActions,
            cli.t_depotcontroller.TestDepotController,
            cli.t_image_create.TestImageCreate,
            cli.t_image_create.TestImageCreateNoDepot,
            cli.t_info_contents.TestContentsAndInfo,
            cli.t_depot.TestDepot,
            cli.t_pkg_install_basics.TestPkgInstallBasics,
            cli.t_pkg_install_corrupt_image.TestImageCreateCorruptImage,
            cli.t_pkgsend.TestPkgSend,
            cli.t_pkg_list.TestPkgList,
            cli.t_commandline.TestCommandLine,
            cli.t_upgrade.TestUpgrade,
            cli.t_circular_dependencies.TestCircularDependencies,
            cli.t_recv.TestPkgRecv,
            cli.t_rename.TestRename,
            cli.t_twodepot.TestTwoDepots,
            cli.t_search.TestPkgSearch,
            cli.t_setUp.TestSetUp ]

        return add_tests(tests, testpat)

def usage():
        print >> sys.stderr, "Usage: %s [-ghpv] [-b filename] [-o regexp]" % \
            sys.argv[0]
        print >> sys.stderr, "   -g             Generate result baseline"
        print >> sys.stderr, "   -h             This help message"
        print >> sys.stderr, "   -p             Parseable output format"
        print >> sys.stderr, "   -v             Verbose output"
        print >> sys.stderr, "   -b <filename>  Baseline filename"
        print >> sys.stderr, "   -o <regexp>    Run only tests that match regexp"
        print >> sys.stderr, ""
        sys.exit(1)

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ghpvb:o:",
                    ["generate-baseline", "parseable", "verbose",
                        "baseline-file", "only"])
        except getopt.GetoptError, e:
                print >> sys.stderr, "Illegal option -- %s" % e.opt
                sys.exit(1)

        bfile = os.path.join("%s" % here, "baseline.txt")
        generate = False
        onlyval = ""
        output = pkg5unittest.OUTPUT_DOTS
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
                if opt == "-h":
			usage()

        import pkg.portable

        if not pkg.portable.is_admin():
                print >> sys.stderr, "WARNING: You don't seem to be root." \
                    " Some tests may fail."

        # Set-up for API tests.
        # Include the proto directory in the python path
        cwd = os.getcwd()
        proto = "%s/../../proto/root_%s" % (cwd, arch)
        pkgs = "%s/usr/lib/python2.4/vendor-packages" % proto
        bins = "%s/usr/bin" % proto
        sys.path.insert(1, pkgs)
        # And make sure bins are accessible
        os.environ["PATH"] = bins + os.pathsep + os.environ["PATH"]

        api_suite = make_api_tests(onlyval)
        cli_suite = make_cli_tests(onlyval)

        try:
                import t_elf
                api_suite.addTest(unittest.makeSuite(t_elf.TestElf, 'test'))
        except ImportError, e:
                # some platforms do not have support for reading ELF files, so
                # skip those tests if we cannot import the elf test.
                print("NOTE: Skipping ELF tests: " + e.__str__())

        suites = []
        suites.append(api_suite)
        if ostype == "posix":
                suites.append(cli_suite)

        # Initialize the baseline results and load them
        baseline = baseline.BaseLine(bfile, generate)
        baseline.load()

        # Make sure we capture stdout
        testlogfd, testlogpath = tempfile.mkstemp(suffix='.pkg-test.log')
        testlogfp = os.fdopen(testlogfd, "w")
        print "logging to %s" % testlogpath
        sys.stdout = testlogfp

        # Run the python test suites
        runner = pkg5unittest.Pkg5TestRunner(baseline, output=output)
        exitval = 0
        for x in suites:
                res = runner.run(x)
                if res.failures:
                        exitval = 1

        testlogfp.close()

        # Update baseline results and display mismatches (failures)
        baseline.store()
        baseline.reportfailures()

        sys.exit(exitval)
