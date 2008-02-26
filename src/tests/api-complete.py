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
        import api.t_catalog
        import api.t_elf
        import api.t_filter
        import api.t_fmri
        import api.t_imageconfig
        import api.t_manifest
        import api.t_misc
        import api.t_smf
        import api.t_version

        all_suite.addTest(unittest.makeSuite(api.t_catalog.TestCatalog, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_catalog.TestEmptyCatalog,
            'test'))
        all_suite.addTest(unittest.makeSuite(api.t_catalog.TestCatalogRename, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_catalog.TestUpdateLog, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_elf.TestElf, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_filter.TestFilter, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_fmri.TestFMRI, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_imageconfig.TestImageConfig, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_manifest.TestManifest, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_misc.TestMisc, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_smf.TestSMF, 'test'))
        all_suite.addTest(unittest.makeSuite(api.t_version.TestVersion, 'test'))

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
        print "NOTE: Adding '.' to head of PYTHONPATH"
        sys.path.insert(0, ".")

        all_suite = unittest.TestSuite()
        maketests()
        runner = unittest.TextTestRunner()
        res = runner.run(all_suite)
        if res.failures:
                sys.exit(1)
        sys.exit(0)
