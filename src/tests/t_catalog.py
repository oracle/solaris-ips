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
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import shutil
import tempfile

import pkg.fmri as fmri
import pkg.catalog as catalog

class TestCatalog(unittest.TestCase):
        def setUp(self):
		self.cpath = tempfile.mkdtemp()
                self.c = catalog.Catalog(self.cpath)

                for f in [
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120000Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120010Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.1:20000101T120020Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.2:20000101T120030Z", None),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-2:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/test@1.1,5.11-1:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/apkg@1.0,5.11-1:20000101T120040Z", None),
                    fmri.PkgFmri("pkg:/zpkg@1.0,5.11-1:20000101T120040Z", None)
                ]:
                        self.c.add_fmri(f)

	def tearDown(self):
		shutil.rmtree(self.cpath)

        def testcatalogfmris1(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.10-1:20070101T120000Z")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 4)

        def testcatalogfmris2(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-1:20061231T120000Z")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 4)

        def testcatalogfmris3(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-2")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 2)

        def testcatalogfmris4(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-3")
                cl = self.c.get_matching_fmris(cf, None)

                self.assert_(len(cl) == 1)

        def testcatalogregex1(self):
                self.assertRaises(KeyError,
                    self.c.get_matching_fmris, "flob", \
                    matcher = fmri.regex_match)

if __name__ == "__main__":
        unittest.main()
