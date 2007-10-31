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
import pkg.fmri as fmri

class TestFMRI(unittest.TestCase):
        def setUp(self):
                self.n1 = fmri.PkgFmri("pkg://pion/sunos/coreutils",
                    build_release = "5.9")
                self.n2 = fmri.PkgFmri("sunos/coreutils",
                    build_release = "5.10")
                self.n3 = fmri.PkgFmri("sunos/coreutils@5.10",
                    build_release = "5.10")
                self.n4 = fmri.PkgFmri(
                    "sunos/coreutils@6.7,5.10-2:20070710T164744Z",
                    build_release = "5.10")
                self.n5 = fmri.PkgFmri(
                    "sunos/coreutils@6.6,5.10-2:20070710T164744Z",
                    build_release = "5.10")
                self.n6 = fmri.PkgFmri("coreutils")
                self.n7 = fmri.PkgFmri(
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
                self.n8 = fmri.PkgFmri(
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070922T153047Z")
                self.n9 = fmri.PkgFmri("sunos/coreutils@6.8,5.11-0",
                    authority = "opensolaris.org")

        def testfmricmp1(self):
                self.assert_(self.n3.__cmp__(self.n3) == 0)

        def testfmricmp2(self):
                self.assert_(self.n3.__cmp__(self.n4) < 0)

        def testfmricmp3(self):
                self.assert_(self.n5.__cmp__(self.n3) > 0)

        def testfmrisuccessor1(self):
                self.assert_(self.n8.is_successor(self.n7))

        def testfmrisuccessor2(self):
                self.assert_(not self.n1.is_successor(self.n2))

        def testfmrisuccessor3(self):
                self.assert_(self.n4.is_successor(self.n3))

        def testfmrisuccessor4(self):
                self.assert_(not self.n5.is_successor(self.n4))

        def testfmrisimilar1(self):
                self.assert_(self.n4.is_similar(self.n2))

        def testfmrisimilar2(self):
                self.assert_(self.n1.is_similar(self.n2))

        def testfmrisimilar3(self):
                self.assert_(not self.n1.is_similar(self.n6))

if __name__ == "__main__":
        unittest.main()
