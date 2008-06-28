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
import platform
import unittest

all_suite=None

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

#
# This is wrapped in a function because __main__ below alters
# PYTHONPATH to reference the proto area; so imports of packaging
# system stuff must happen *after* that code runs.
#
def maketests():
        import api.t_action
        import api.t_catalog
        import api.t_filter
        import api.t_fmri
        import api.t_imageconfig
        import api.t_manifest
        import api.t_misc
        import api.t_pkgtarfile
        import api.t_plat
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
            api.t_smf.TestSMF,
            api.t_version.TestVersion ]

        for t in tests:
                all_suite.addTest(unittest.makeSuite(t, 'test'))


if __name__ == "__main__":
        try:
                import t_elf
                all_suite.addTest(unittest.makeSuite(t_elf.TestElf, 'test'))
        except ImportError, e:
                # some platforms do not have support for reading ELF files, so
                # skip those tests if we cannot import the elf test.
                print("NOTE: Skipping ELF tests: " + e.__str__())

        cwd = os.getcwd()

        proto = "%s/../../proto/root_%s" % (cwd, arch)
        pkgs = "%s/usr/lib/python2.4/vendor-packages" % proto
        bins = "%s/usr/bin" % proto
        print "NOTE: Adding %s to head of PYTHONPATH" % pkgs
        sys.path.insert(1, pkgs)
        print "NOTE: Adding '%s' to head of PATH" % bins
        os.environ["PATH"] = bins + os.pathsep + os.environ["PATH"]

        all_suite = unittest.TestSuite()
        maketests()
        runner = unittest.TextTestRunner()
        res = runner.run(all_suite)
        if res.failures:
                sys.exit(1)
        sys.exit(0)

