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
	import t_catalog
	import t_elf
	import t_filter
	import t_fmri
	import t_imageconfig
	import t_manifest
	import t_misc
	import t_smf
	import t_version

	all_suite.addTest(unittest.makeSuite(t_catalog.TestCatalog, 'test'))
	all_suite.addTest(unittest.makeSuite(t_catalog.TestEmptyCatalog,
            'test'))
	all_suite.addTest(unittest.makeSuite(t_catalog.TestUpdateLog, 'test'))
	all_suite.addTest(unittest.makeSuite(t_elf.TestElf, 'test'))
	all_suite.addTest(unittest.makeSuite(t_filter.TestFilter, 'test'))
	all_suite.addTest(unittest.makeSuite(t_fmri.TestFMRI, 'test'))
	all_suite.addTest(unittest.makeSuite(t_imageconfig.TestImageConfig, 'test'))
	all_suite.addTest(unittest.makeSuite(t_manifest.TestManifest, 'test'))
	all_suite.addTest(unittest.makeSuite(t_misc.TestMisc, 'test'))
	all_suite.addTest(unittest.makeSuite(t_smf.TestSMF, 'test'))
	all_suite.addTest(unittest.makeSuite(t_version.TestVersion, 'test'))

if __name__ == "__main__":

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

	all_suite = unittest.TestSuite()
	maketests()
	runner = unittest.TextTestRunner()
	res = runner.run(all_suite)
	if len(res.failures) > 0:
		sys.exit(1)
	sys.exit(0)
