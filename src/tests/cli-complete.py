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
# fields enclosed by brackets "[[]]" replaced with your own identifying
# information: Portions Copyright [[yyyy]] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import sys
import platform
import unittest

all_suite=None

#
# This is wrapped in a function because __main__ below alters
# PYTHONPATH to reference the proto area; so imports of packaging
# system stuff must happen *after* that code runs.
#
def maketests():
	import cli.t_depot
	import cli.t_depotcontroller
	import cli.t_image_create
	import cli.t_pkg_install_basics
	import cli.t_pkgsend
	import cli.t_pkg_status
	import cli.t_commandline
	import cli.t_upgrade
	import cli.t_rename

	all_suite.addTest(unittest.makeSuite(cli.t_depotcontroller.TestDepotController, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_image_create.TestImageCreate, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_image_create.TestImageCreateNoDepot, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_depot.TestDepot, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_pkg_install_basics.TestPkgInstallBasics, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_pkgsend.TestPkgSend, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_pkg_status.TestPkgStatus, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_commandline.TestCommandLine, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_upgrade.TestUpgrade, 'test'))
	all_suite.addTest(unittest.makeSuite(cli.t_rename.TestRename, 'test'))

if __name__ == "__main__":

	if os.getuid() != 0:
		print >> sys.stderr, "WARNING: You don't seem to be root." \
		    " Tests may fail."

	cwd = os.getcwd()
	if os.uname()[0] == "SunOS":
		proc = platform.processor()
	elif os.uname()[0] == "Linux":
		proc = platform.machine()
	else:
		print "Unable to determine appropriate proto area location."
		print "This is a porting problem."
		sys.exit(1)

	proto = "%s/../../proto/root_%s/usr/lib/python2.4/vendor-packages" % \
	    (cwd, proc)

	print "NOTE: Adding %s to head of PYTHONPATH" % proto
	sys.path.insert(0, proto)
	print "NOTE: Adding '.' to head of PYTHONPATH"
	sys.path.insert(0, ".")
	print "DEBUG: Set TEST_DEBUG=1 for verbose output"

	all_suite = unittest.TestSuite()
	maketests()
	runner = unittest.TextTestRunner()
	res = runner.run(all_suite)
	if res.failures:
		sys.exit(1)
	sys.exit(0)
