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

import getopt
import os
import pkg5unittest
import platform
import unittest
import sys

# To get our test utilities module, we must first prepend "." to
# Python's lookup path.
sys.path.insert(0, ".")
import cli.testutils

if __name__ == "__main__":
	cli.testutils.setup_environment("../../proto")

all_suite=None

#
# This is wrapped in a function because __main__ below alters
# PYTHONPATH to reference the proto area; so imports of packaging
# system stuff must happen *after* that code runs.
#
def maketests():
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

        for t in tests:
                all_suite.addTest(unittest.makeSuite(t, 'test'))

if __name__ == "__main__":
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "gpv",
                    ["generate-baseline", "parseable", "verbose"])
        except getopt.GetoptError, e:
                print >> sys.stderr, "Illegal option -- %s" % e.opt
                sys.exit(1)

        output = pkg5unittest.OUTPUT_DOTS
        generate = False
        for opt, arg in opts:
                if opt == "-v":
                        output = pkg5unittest.OUTPUT_VERBOSE
                if opt == "-p":
                        output = pkg5unittest.OUTPUT_PARSEABLE
                if opt == "-g":
                        generate = True

        if os.getuid() != 0:
                print >> sys.stderr, "WARNING: You don't seem to be root." \
                    " Tests may fail."

	all_suite = unittest.TestSuite()
	maketests()
	runner = pkg5unittest.Pkg5TestRunner("cli", output=output,
            generate=generate)

        res = runner.run(all_suite)
        if res.failures:
                sys.exit(1)
	sys.exit(0)
