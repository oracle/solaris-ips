
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
import pkg.version as version

class TestVersion(unittest.TestCase):
        def setUp(self):
                self.d1 = version.DotSequence("1.1.3")
                self.d2 = version.DotSequence("1.1.3")
                self.d3 = version.DotSequence("5.4")
                self.d4 = version.DotSequence("5.6")

                self.v1 = version.Version("5.5.1-10:20051122T000000Z", "5.5.1")
                self.v2 = version.Version("5.5.1-10:20070318T123456Z", "5.5.1")
                self.v3 = version.Version("5.5.1-10", "5.5")
                self.v4 = version.Version("5.5.1-6", "5.4")
                self.v5 = version.Version("5.6,1", "5.4")
                self.v6 = version.Version("5.7", "5.4")
                self.v7 = version.Version("5.10", "5.5.1")
                self.v8 = version.Version("5.10.1", "5.5.1")
                self.v9 = version.Version("5.11", "5.5.1")
                self.v10 = version.Version("0.1,5.11-1", None)
                self.v11 = version.Version("0.1,5.11-1:20070710T120000Z", None)
                self.v12 = version.Version("5.11-0.72:20070921T211008Z",
                    "0.5.11")
                self.v13 = version.Version("5.11-0.72:20070922T160226Z",
                    "0.5.11")
		self.v14 = version.Version("0.1,5.11", None)
		self.v15 = version.Version("0.1,5.11:20071014T234545Z", None)
		self.v16 = version.Version("0.2,5.11", None)
		self.v17 = version.Version("0.2,5.11-1:20071029T131519Z", None)

        def testdotsequenceequality(self):
                self.assert_(self.d1 == self.d2)

	def teststr(self):
		self.assert_(str(self.v1) == "5.5.1,5.5.1-10:20051122T000000Z")
		self.assert_(str(self.v2) == "5.5.1,5.5.1-10:20070318T123456Z")
		self.assert_(str(self.v3) == "5.5.1,5.5-10")
		self.assert_(str(self.v4) == "5.5.1,5.4-6")
		self.assert_(str(self.v5) == "5.6,1")
		self.assert_(str(self.v6) == "5.7,5.4")
		self.assert_(str(self.v7) == "5.10,5.5.1")
		self.assert_(str(self.v8) == "5.10.1,5.5.1")
		self.assert_(str(self.v9) == "5.11,5.5.1")
		self.assert_(str(self.v10) == "0.1,5.11-1")
		self.assert_(str(self.v11) == "0.1,5.11-1:20070710T120000Z")
		self.assert_(
		    str(self.v12) == "5.11,0.5.11-0.72:20070921T211008Z")
		self.assert_(
		    str(self.v13) == "5.11,0.5.11-0.72:20070922T160226Z")
		self.assert_(str(self.v14) == "0.1,5.11")
		self.assert_(str(self.v15) == "0.1,5.11:20071014T234545Z")
		self.assert_(str(self.v16) == "0.2,5.11")
		self.assert_(str(self.v17) == "0.2,5.11-1:20071029T131519Z")

        def testdotsequencelt(self):
                self.assert_(self.d3 < self.d4)

        def testversionlt(self):
                self.assert_(self.v1 < self.v2)

        def testversionlt2(self):
                self.assert_(self.v4 < self.v3)

        def testversionlt3(self):
                self.assert_(self.v4 < self.v5)

        def testversionlt4(self):
                self.assert_(self.v7 < self.v8)

        def testversiongt1(self):
                self.assert_(self.v6 > self.v5)

        def testversiongt2(self):
                self.assert_(self.v9 > self.v8)

        def testversiongt3(self):
                self.assert_(self.v11 > self.v10)

        def testversiongt4(self):
                self.assert_(self.v13 > self.v12)

        def testversioneq(self):
                self.assert_(not self.v9 == self.v8)

        def testversionne(self):
                self.assert_(self.v9 != self.v8)

        def testversionbuildcompat1(self):
                self.assert_(not self.v9.compatible_with_build(self.d3))

        def testversionbuildcompat2(self):
                self.assert_(self.v9.compatible_with_build(self.d4))

        def testversionsuccessor1(self):
                self.assert_(self.v13.is_successor(self.v12,
                    version.CONSTRAINT_BRANCH))

        def testversionsuccessor2(self):
                self.assert_(self.v2.is_successor(self.v1,
                    version.CONSTRAINT_BRANCH))

        def testversionsuccessor3(self):
                self.assert_(self.v4.is_successor(self.v2,
                    version.CONSTRAINT_RELEASE))

        def testversionsuccessor4(self):
                self.assert_(self.v6.is_successor(self.v5,
                    version.CONSTRAINT_RELEASE_MAJOR))

        def testversionsuccessor5(self):
                self.assert_(self.v8.is_successor(self.v7,
                    version.CONSTRAINT_RELEASE_MAJOR))

	def testversionsuccessor6(self):
		self.assert_(self.v10.is_successor(self.v14,
		    version.CONSTRAINT_AUTO))

	def testversionsuccessor7(self):
		self.assert_(self.v15.is_successor(self.v14,
		    version.CONSTRAINT_AUTO))

	def testversionsuccessor8(self):
		self.assert_(not self.v16.is_successor(self.v14,
		    version.CONSTRAINT_AUTO))

	def testversionsuccessor9(self):
		self.assert_(not self.v17.is_successor(self.v14,
		    version.CONSTRAINT_AUTO))

if __name__ == "__main__":
        unittest.main()
