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

#
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import pkg.version as version
import datetime
import os
import sys

class TestVersion(pkg5unittest.Pkg5TestCase):
        def setUp(self):
                self.d1 = version.DotSequence("1.1.3")
                self.d2 = version.DotSequence("1.1.3")
                self.d3 = version.DotSequence("5.4")
                self.d4 = version.DotSequence("5.6")
                self.d5 = version.DotSequence("5.4.1")
                self.d6 = version.DotSequence("5.5.1")
                self.d7 = version.DotSequence("6.5.1")

                self.v1 = version.Version("5.5.1-10:20051122T000000Z", "5.5.1")
                self.v2 = version.Version("5.5.1-10:20070318T123456Z", "5.5.1")
                self.v3 = version.Version("5.5.1-10", "5.5")
                self.v4 = version.Version("5.5.1-6", "5.4")
                self.v5 = version.Version("5.6,1", "5.4")
                self.v6 = version.Version("5.7", "5.4")
                self.v7 = version.Version("5.10", "5.5.1")
                self.v8 = version.Version("5.10.1", "5.5.1")
                self.v9 = version.Version("5.11", "5.5.1")
                self.v9same = version.Version("5.11", "5.5.1")
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
                self.v18 = version.Version("5", "5")

        def testbogusdotsequence(self):
                self.assertRaises(version.IllegalDotSequence,
                    version.DotSequence, "x.y")
                self.assertRaises(version.IllegalDotSequence,
                    version.DotSequence, "")
                self.assertRaises(version.IllegalDotSequence,
                    version.DotSequence, "@")
                self.assertRaises(version.IllegalDotSequence,
                    version.DotSequence, "1.@")

        def testdotsequencecomparison(self):
                self.assertTrue(self.d3 < self.d4)
                self.assertTrue(self.d4 > self.d3)
                self.assertTrue(not self.d1 < self.d2)
                self.assertTrue(not self.d1 > self.d2)
                self.assertTrue(not None == self.d1)
                self.assertTrue(None != self.d1)
                self.assertTrue(self.d1 != self.d3)
                self.assertTrue(self.d1 == self.d2)
                self.assertTrue(self.d1.is_same_major(self.d2))
                self.assertTrue(self.d3.is_same_major(self.d4))
                self.assertTrue(self.d1.is_same_minor(self.d2))
                self.assertTrue(not self.d1.is_same_minor(self.d5))
                self.assertTrue(not self.d3.is_same_minor(self.d4))
                self.assertTrue(not self.d6.is_same_minor(self.d7))
                self.assertTrue(self.d3.is_subsequence(self.d5))
                self.assertTrue(not self.d3.is_subsequence(self.d6))
                self.assertTrue(not self.d1.is_subsequence(self.d6))
                self.assertTrue(not self.d6.is_subsequence(self.d1))
                self.assertTrue(not self.d5.is_subsequence(self.d3))

        def teststr(self):
                self.assertTrue(str(self.v1) == "5.5.1,5.5.1-10:20051122T000000Z")
                self.assertTrue(str(self.v2) == "5.5.1,5.5.1-10:20070318T123456Z")
                self.assertTrue(str(self.v3) == "5.5.1,5.5-10")
                self.assertTrue(str(self.v4) == "5.5.1,5.4-6")
                self.assertTrue(str(self.v5) == "5.6,1")
                self.assertTrue(str(self.v6) == "5.7,5.4")
                self.assertTrue(str(self.v7) == "5.10,5.5.1")
                self.assertTrue(str(self.v8) == "5.10.1,5.5.1")
                self.assertTrue(str(self.v9) == "5.11,5.5.1")
                self.assertTrue(str(self.v10) == "0.1,5.11-1")
                self.assertTrue(str(self.v11) == "0.1,5.11-1:20070710T120000Z")
                self.assertTrue(
                    str(self.v12) == "5.11,0.5.11-0.72:20070921T211008Z")
                self.assertTrue(
                    str(self.v13) == "5.11,0.5.11-0.72:20070922T160226Z")
                self.assertTrue(str(self.v14) == "0.1,5.11")
                self.assertTrue(str(self.v15) == "0.1,5.11:20071014T234545Z")
                self.assertTrue(str(self.v16) == "0.2,5.11")
                self.assertTrue(str(self.v17) == "0.2,5.11-1:20071029T131519Z")
                self.assertTrue(str(self.v18) == "5,5")

        def testbogusversion1(self):
                """ Test empty elements """
                self.assertRaises(version.IllegalVersion,
                    version.Version, "", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, ".", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, ",", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "-", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, ":", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "@", "5.11")

        def testbogusversion2(self):
                """ Test bad release strings """
                self.assertRaises(version.IllegalVersion,
                    version.Version, "x.y", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.y", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "-3", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.@", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.", None)
                self.assertRaises(version.IllegalVersion,
                    version.Version, ".1", None)
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1..1", None)
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0001", "5.11")

        def testbogusversion3(self):
                """ Test bad build strings """
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,-1.0", None)
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,,,,,-2.0", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,1.-0", None)

        def testbogusversion4(self):
                """ Test bad branch strings """
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,1-.0", None)
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,2----2.0", "5.11")

        def testbogusversion5(self):
                # dangling branch
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,1.0-", None)
                # dangling branch with timestamp
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,1.0-:19760113T111111Z", None)
                # empty time
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,1.0-1.0:", "5.11")
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,-1.0:19760113T111111Z", None)
                # dangling build
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,", None)
                # dangling build with timestamp
                self.assertRaises(version.IllegalVersion,
                    version.Version, "1.0,:19760113T111111Z", None)

        def testbogusversion6(self):
                """ insert a bad char at (almost) every position in a version"""
                v = "12.34.56-78:19760113T111111Z"
                # Check that v is valid
                version.Version(v)
                badchars = [ "T", "Z", "@", "-", ".", ",", ":" ]
                becareful = [".", ",", "-"]
                for b in badchars:
                        for x in range(0, len(v)):
                                vlist = list(v)
                                if b in becareful and vlist[x] in becareful:
                                        continue
                                if vlist[x] == b:
                                        continue
                                vlist[x] = b
                                vv = "".join(vlist)
                                self.assertRaises(version.IllegalVersion,
                                    version.Version, vv, "5.11")

        def testversionlt(self):
                self.assertTrue(self.v1 < self.v2)

        def testversionlt2(self):
                self.assertTrue(self.v4 < self.v3)

        def testversionlt3(self):
                self.assertTrue(self.v4 < self.v5)

        def testversionlt4(self):
                self.assertTrue(self.v7 < self.v8)

        def testversionlt5(self):
                self.assertTrue(not self.v7 < None)

        def testversionlt6(self):
                self.assertTrue(not self.v7 < self.v7)

        def testversiongt1(self):
                self.assertTrue(self.v6 > self.v5)

        def testversiongt2(self):
                self.assertTrue(self.v9 > self.v8)

        def testversiongt3(self):
                self.assertTrue(self.v11 > self.v10)

        def testversiongt4(self):
                self.assertTrue(self.v13 > self.v12)

        def testversiongt5(self):
                self.assertTrue(self.v7 > None)

        def testversiongt6(self):
                self.assertTrue(not self.v7 > self.v7)

        def testversioneq(self):
                self.assertTrue(not self.v9 == self.v8)
                self.assertTrue(not self.v9 == None)
                self.assertTrue(not None == self.v9)
                self.assertTrue(self.v9 == self.v9same)

        def testversionne(self):
                self.assertTrue(self.v9 != self.v8)
                self.assertTrue(self.v9 != None)
                self.assertTrue(None != self.v9)
                self.assertTrue(not self.v9 != self.v9same)

        def testversionsuccessor1(self):
                self.assertTrue(self.v13.is_successor(self.v12,
                    version.CONSTRAINT_BRANCH))

        def testversionsuccessor2(self):
                self.assertTrue(self.v2.is_successor(self.v1,
                    version.CONSTRAINT_BRANCH))

        def testversionsuccessor3(self):
                self.assertTrue(self.v4.is_successor(self.v2,
                    version.CONSTRAINT_RELEASE))

        def testversionsuccessor4(self):
                self.assertTrue(self.v6.is_successor(self.v5,
                    version.CONSTRAINT_RELEASE_MAJOR))

        def testversionsuccessor5(self):
                self.assertTrue(self.v8.is_successor(self.v7,
                    version.CONSTRAINT_RELEASE_MAJOR))

        def testversionsuccessor6(self):
                self.assertTrue(self.v10.is_successor(self.v14,
                    version.CONSTRAINT_AUTO))

        def testversionsuccessor7(self):
                self.assertTrue(self.v15.is_successor(self.v14,
                    version.CONSTRAINT_AUTO))

        def testversionsuccessor8(self):
                self.assertTrue(not self.v16.is_successor(self.v14,
                    version.CONSTRAINT_AUTO))

        def testversionsuccessor9(self):
                self.assertTrue(not self.v17.is_successor(self.v14,
                    version.CONSTRAINT_AUTO))

        def testversionbadversion(self):
                self.assertRaises(version.IllegalVersion,
                    version.Version, "", None)

        def testversionbaddots(self):
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2.q.4,5.11-1", None)

        def testversionbadtime1(self):
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2,5.11-1:moomoomoomoomooZ", None)

        def testversionbadtime2(self):
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2,5.11-1:20070113T131519Q", None)

        def testversionbadtime3(self):
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2,5.11-1:29T131519Z", None)

        def testversionbadtime4(self):
                #bad month
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2,5.11-1:20070013T112233Z", None)

        def testversionbadtime5(self):
                #bad day; no day 31 in feb
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2,5.11-1:20070231T112233Z", None)

        def testversionbadtime6(self):
                #bad second
                self.assertRaises(version.IllegalVersion,
                    version.Version, "0.2,5.11-1:20070113T131672Z", None)

        def testversiongettime(self):
                self.assertTrue(self.v1.get_timestamp().year == 2005)
                self.assertTrue(self.v1.get_timestamp().hour == 0)
                self.assertTrue(self.v1.get_timestamp().hour == 0)
                self.assertTrue(self.v1.get_timestamp().tzname() == None)
                self.assertTrue(self.v3.get_timestamp() == None)

        def testversionsettime(self):
                d = datetime.datetime.utcnow()
                # 'd' includes microseconds, so we trim those off.
                d = d.replace(microsecond=0)
                self.v1.set_timestamp(d)
                self.assertTrue(self.v1.get_timestamp() == d)

        def testsplit(self):
                """Verify that split() works as expected."""

                sver = "1.0,5.11-0.156:20101231T161351Z"
                expected = (("1.0", "5.11", "0.156", "20101231T161351Z"),
                    "1.0-0.156")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = "1.0:20101231T161351Z"
                expected = (("1.0", "", None, "20101231T161351Z"), "1.0")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = ":20101231T161351Z"
                expected = (("", "", None, "20101231T161351Z"), "")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = "1.0,5.11-0.156"
                expected = (("1.0", "5.11", "0.156", None), "1.0-0.156")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = "-0.156"
                expected = (("", "", "0.156", None), "-0.156")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = "1.0,5.11"
                expected = (("1.0", "5.11", None, None), "1.0")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = ",5.11"
                expected = (("", "5.11", None, None), "")
                self.assertEqualDiff(expected, version.Version.split(sver)) 

                sver = "1.0"
                expected = (("1.0", "", None, None), "1.0")
                self.assertEqualDiff(expected, version.Version.split(sver)) 


if __name__ == "__main__":
        unittest.main()
