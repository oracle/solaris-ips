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
import pkg.fmri as fmri

import os
import sys

class TestFMRI(pkg5unittest.Pkg5TestCase):

        pkg_name_valid_chars = {
            "never": " `~!@#$%^&*()=[{]}\\|;:\",<>?",
            "always": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" +
                "0123456789",
            "after-first": "_-.+",
        }

        def setUp(self):
                self.n1 = fmri.PkgFmri("pkg://pion/sunos/coreutils")
                self.n2 = fmri.PkgFmri("sunos/coreutils")
                self.n3 = fmri.PkgFmri("sunos/coreutils@5.10")
                self.n4 = fmri.PkgFmri(
                    "sunos/coreutils@6.7,5.10-2:20070710T164744Z")
                self.n5 = fmri.PkgFmri(
                    "sunos/coreutils@6.6,5.10-2:20070710T164744Z")
                self.n6 = fmri.PkgFmri("coreutils")
                self.n7 = fmri.PkgFmri(
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070921T203926Z")
                self.n8 = fmri.PkgFmri(
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070922T153047Z")
                self.n9 = fmri.PkgFmri("sunos/coreutils@6.8,5.11-0",
                    publisher = "opensolaris.org")
                self.n10 = fmri.PkgFmri(
                    "pkg://origin2/SUNWxwssu@0.5.11,5.11-0.72:20070922T153047Z")
                # same as n10
                self.n11 = fmri.PkgFmri(
                    "pkg://origin2/SUNWxwssu@0.5.11,5.11-0.72:20070922T153047Z")

        def testfmricmp1(self):
                self.assertTrue(self.n3.__eq__(self.n3))

        def testfmricmp2(self):
                self.assertTrue(self.n3.__lt__(self.n4))

        def testfmricmp3(self):
                self.assertTrue(self.n5.__gt__(self.n3))

        def testfmrisuccessor1(self):
                self.assertTrue(self.n8.is_successor(self.n7))

        def testfmrisuccessor2(self):
                self.assertTrue(self.n1.is_successor(self.n2))

        def testfmrisuccessor3(self):
                self.assertTrue(self.n4.is_successor(self.n3))

        def testfmrisuccessor4(self):
                self.assertTrue(not self.n5.is_successor(self.n4))

        def testfmrisuccessor5(self):
                """is_successor should return true on equality"""
                self.assertTrue(self.n5.is_successor(self.n5))

        def testfmrisuccessor6(self):
                """fmris have different versions and different authorities"""
                self.assertTrue(self.n10.is_successor(self.n7))

        def testfmrisimilar1(self):
                self.assertTrue(self.n4.is_similar(self.n2))

        def testfmrisimilar2(self):
                self.assertTrue(self.n1.is_similar(self.n2))

        def testfmrisimilar3(self):
                self.assertTrue(not self.n1.is_similar(self.n6))

        def testfmrihaspublisher(self):
                self.assertTrue(self.n1.has_publisher() == True)
                self.assertTrue(self.n2.has_publisher() == False)
                self.assertTrue(self.n3.has_publisher() == False)
                self.assertTrue(self.n4.has_publisher() == False)
                self.assertTrue(self.n5.has_publisher() == False)
                self.assertTrue(self.n6.has_publisher() == False)
                self.assertTrue(self.n7.has_publisher() == True)
                self.assertTrue(self.n8.has_publisher() == True)

        def testfmrihasversion(self):
                self.assertTrue(self.n1.has_version() == False)
                self.assertTrue(self.n2.has_version() == False)
                self.assertTrue(self.n3.has_version() == True)
                self.assertTrue(self.n4.has_version() == True)
                self.assertTrue(self.n5.has_version() == True)
                self.assertTrue(self.n6.has_version() == False)

        def testfmriissamepkg(self):
                self.assertTrue(self.n7.is_same_pkg(self.n8))
                self.assertTrue(self.n7.is_same_pkg(self.n10))
                self.assertTrue(not self.n7.is_same_pkg(self.n6))

        def testbadfmri1(self):
                # no 31st day in february
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070231T203926Z")

        def testbadfmri2(self):
                # missing version
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://origin/SUNWxwssu@")

        #
        # The next assertions are for various bogus fmris
        #
        def testbadfmri3(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "")

        def testbadfmri4(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "@")

        def testbadfmri5(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "@1,1-1")

        def testbadfmri6(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg:")

        def testbadfmri7(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg://")

        def testbadfmri8(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg://foo")

        def testbadfmri9(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg://foo/")

        def testbadfmri10(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg:/")

        def testbadfmri11(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg://@")

        def testbadfmri12(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg:/@")

        def testbadfmri13(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri, "pkg:/pkg:")

        def testbadfmri14(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://foo/pkg:")

        def testbadfmri15(self):
                # Truncated time
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:20070231T203")

        def testbadfmri16(self):
                # Truncated time
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-0.72:200702")

        def testbadfmri17(self):
                # Dangling Branch with Time
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-:20070922T153047Z")

        def testbadfmri18(self):
                # Dangling Branch
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "pkg://origin/SUNWxwssu@0.5.11,5.11-")

        def test_pkgname_grammar(self):
                for char in self.pkg_name_valid_chars["never"]:
                        invalid_name = "invalid{0}pkg@1.0,5.11-0".format(char)
                        self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                            invalid_name)

                for char in self.pkg_name_valid_chars["after-first"]:
                        invalid_name = "{0}invalidpkg@1.0,5.11-0".format(char)
                        self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                            invalid_name)

                for char in self.pkg_name_valid_chars["after-first"]:
                        invalid_name = "test/{0}pkg@1.0,5.11-0".format(char)
                        self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                            invalid_name)

                # Some positive tests
                for char in self.pkg_name_valid_chars["always"]:
                        for char2 in self.pkg_name_valid_chars["after-first"]:
                                valid_name = "{0}{1}test@1.0,5.11-0".format(
                                    char, char2)
                                fmri.PkgFmri(valid_name)

                # Test '/' == 'pkg:/'; '//' == 'pkg://'.
                for vn in ("/test@1.0,5.11-0", "//publisher/test@1.0,5.11-0"):
                        pfmri = fmri.PkgFmri(vn)
                        self.assertEqual(pfmri.pkg_name, "test")
                        if vn.startswith("//"):
                                self.assertEqual(pfmri.publisher, "publisher")
                        else:
                                self.assertEqual(pfmri.publisher, None)

        def testbadfmri_pkgname(self):
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "application//office@0.5.11,5.11-0.96")
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "application/office/@0.5.11,5.11-0.96")
                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "app/.cool@0.5.11,5.11-0.96")

        def testgoodfmris_dots(self):
                fmri.PkgFmri("a.b")
                fmri.PkgFmri("a.b@1.0")

        def testgoodfmris_slashes(self):
                fmri.PkgFmri("a/b")
                fmri.PkgFmri("a/b/c")

        def testgoodfmris_dashes(self):
                fmri.PkgFmri("a--b---")

        def testgoodfmris_unders(self):
                fmri.PkgFmri("a___b__")

        def testgoodfmris_pluses(self):
                fmri.PkgFmri("a+++b+++")

        def testgoodfmris_(self):
                fmri.PkgFmri("pkg:/abcdef01234.-+_/GHIJK@1.0")
                fmri.PkgFmri("pkg:/a/b/c/d/e/f/g/H/I/J/0/1/2")

        def testfmrihash(self):
                """FMRIs override __hash__.  Test that this is working
                properly."""
                a = {}
                a[self.n10] = 1
                self.assertTrue(a[self.n11] == 1)

        def testpartial(self):
                """Verify that supported operations on a partial FMRI
                function properly."""

                pfmri = "pkg:/BRCMbnx"

                f = fmri.PkgFmri(pfmri)
                self.assertEqual(f.get_short_fmri(), pfmri)
                self.assertEqual(f.get_pkg_stem(), pfmri)
                self.assertEqual(f.get_fmri(), pfmri)
                self.assertFalse(f.has_version())
                self.assertFalse(f.has_publisher())

        def testpublisher(self):
                """Verify that different ways of specifying the publisher
                information in an FMRI produce the same results."""

                for s in ("pkg:///name", "pkg:/name", "///name", "/name"):
                        f = fmri.PkgFmri(s)
                        self.assertEqual(f.publisher, None)

                for s in ("pkg://test/name", "//test/name"):
                        f = fmri.PkgFmri(s)
                        self.assertEqual(f.publisher, "test")

        def testunsupported(self):
                """Verify that unsupported operations on a partial FMRI raise
                the correct exceptions."""

                f = fmri.PkgFmri("BRCMbnx")
                self.assertRaises(fmri.MissingVersionError, f.get_dir_path)
                self.assertRaises(fmri.MissingVersionError, f.get_link_path)
                self.assertRaises(fmri.MissingVersionError, f.get_url_path)

        def testbadversionexception(self):
                """Verify that a bad version in an FMRI still only raises an
                FMRI exception."""

                self.assertRaises(fmri.IllegalFmri, fmri.PkgFmri,
                    "BRCMbnx@0.5.aa,5.aa-0.aa")

if __name__ == "__main__":
        unittest.main()
