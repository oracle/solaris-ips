#!/usr/bin/python
# -*- coding: utf-8 -*-
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

# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.

import unittest
import tempfile
import os
import sys
import types
import itertools

import pkg as pkg
import pkg.client.api_errors as api_errors
import pkg.manifest as manifest
import pkg.actions as actions
import pkg.fmri as fmri

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestManifest(pkg5unittest.Pkg5TestCase):

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)

                self.m1 = manifest.Manifest()
                self.m1_contents = """\
set com.sun,test=true
depend type=require fmri=pkg:/library/libc
file fff555fff mode=0555 owner=sch group=staff path=/usr/bin/i386/sort isa=i386
"""
                self.m2 = manifest.Manifest()
                self.m2_contents = """\
set com.sun,test=false
set com.sun,data=true
depend type=require fmri=pkg:/library/libc
file fff555ff9 mode=0555 owner=sch group=staff \
 path=/usr/bin/i386/sort isa=i386
file eeeaaaeee mode=0555 owner=sch group=staff path=/usr/bin/amd64/sort isa=amd64

file ff555fff mode=0555 owner=root group=bin path=/kernel/drv/foo isa=i386
file ff555ffe mode=0555 owner=root group=bin path=/kernel/drv/amd64/foo isa=amd64
file ff555ffd mode=0644 owner=root group=bin path=/kernel/drv/foo.conf
"""

                self.m2_signatures = {
                    "sha-1": "e600f5e48a838b11ed73fd4afedfc35638ab0bbf"
                }

                #
                # Try to keep this up to date with on of
                # every action type.
                #
                self.diverse_contents = """\
set com.sun,test=false
depend type=require fmri=pkg:/library/libc
file fff555ff9 mode=0555 owner=sch group=staff path=/usr/bin/i386/sort isa=i386
dir owner=root path=usr/bin group=bin mode=0755
link path=usr/lib/amd64/libjpeg.so \
target=libjpeg.so.62.0.0
hardlink path=usr/bin/amd64/rksh93 target=ksh93 variant.opensolaris.zone=global
group groupname=testgroup gid=10
"""

                self.m4_contents = """\
set com.sun,test=false
set com.sun,data=true
depend type=require fmri=pkg:/library/libc
file fff555ff9 mode=0555 owner=sch group=staff path=/usr/bin/i386/sort \
isa=i386
"""

                self.m5_contents = """\
set com.sun,test=false
set com.sun,data=true
depend type=optional fmri=pkg:/library/libc
file fff555ff9 mode=0555 owner=sch group=staff path=/usr/bin/i386/sort isa=i386
"""


        def test_set_content1(self):
                """ ASSERT: manifest string repr reflects its construction """

                self.m1.set_content(self.m1_contents)

                # It would be nice if we could just see if the string
                # representation of the manifest matched the input, but the
                # order of individual fields seems to change.  Instead we look
                # for useful substrings.

                # Index raises an exception if the substring isn't found;
                # if that were to happen, the test case would then fail.
                str(self.m1).index("fmri=pkg:/library/libc")
                str(self.m1).index("owner=sch")
                str(self.m1).index("group=staff")
                str(self.m1).index("isa=i386")

                # Verify set_content with a byte string with unicode data
                # works.
                bstr = "set name=pkg.summary:th value=\"ซอฟต์แวร์ \""
                m = manifest.Manifest()
                m.set_content(bstr)
                output = list(m.as_lines())[0].rstrip()
                self.assertEqual(bstr, output)
                self.assert_(isinstance(output, str))

                # Verify set_content with a Unicode string results in a
                # byte string (for now).
                m = manifest.Manifest()
                m.set_content(unicode(bstr, "utf-8"))
                output = list(m.as_lines())[0].rstrip()
                self.assertEqual(bstr, output)
                self.assert_(isinstance(output, str))

        def test_diffs1(self):
                """ humanized_differences runs to completion """

                # humanized_differences is for now, at least, just a
                # useful diagnostic
                self.m1.set_content(self.m1_contents)
                self.m2.set_content(self.m2_contents)
                self.m2.humanized_differences(self.m1)
                
        def test_diffs2(self):
                self.m1.set_content(self.m1_contents)
                self.m2.set_content(self.m2_contents)
                diffs = self.m2.combined_difference(self.m1)

        #
        # Do the most obvious thing: build two manifests
        # from the same string, and then diff the results
        #
        def test_diffs3(self):
                """ ASSERT: building m1(c) and m2(c) should yield no diffs """
                self.m1.set_content(self.diverse_contents)
                self.m2.set_content(self.diverse_contents)

                diffs = self.m2.combined_difference(self.m1)
                self.assertEqual(len(diffs), 0)

                diffs = self.m1.combined_difference(self.m2)
                self.assertEqual(len(diffs), 0)
                
        def test_diffs4(self):
                """ ASSERT: Building m' from diff(m, null) should yield m """

                self.m2.set_content(self.m2_contents)
                diffs = self.m2.combined_difference(manifest.null)

                new_contents = ""
                for d in diffs:
                        new_contents += str(d[1]) + "\n"

                mtmp = manifest.Manifest()
                #print new_contents
                mtmp.set_content(new_contents)

                diffs = self.m2.combined_difference(mtmp)
                self.assertEqual(len(diffs), 0)

        def test_diffs5(self):
                """ detect an attribute change """

                self.m1.set_content(self.m4_contents)
                self.m2.set_content(self.m5_contents)

                #print self.m2.display_differences(self.m1)

                diffs = self.m2.combined_difference(self.m1)
                self.assertEqual(len(diffs), 1)

        def test_diffs6(self):
                """ ASSERT: changes in action work """

                self.m1.set_content(
                    "dir mode=0755 owner=root group=sys path=/bin/foo")
                self.m2.set_content(
                    "file 12345 mode=0755 owner=root group=sys path=/bin")

                diffs = self.m2.combined_difference(self.m1)
                #
                # Expect to see a directory going away, and a file being
                # added
                #
                for d in diffs:
                        if type(d[0]) == types.NoneType:
                                self.assertEqual(type(d[1]),
                                    pkg.actions.file.FileAction)
                        if type(d[1]) == types.NoneType:
                                self.assertEqual(type(d[0]),
                                    pkg.actions.directory.DirectoryAction)

                self.assertEqual(len(diffs), 2)

        def test_diffs7(self):
                """ ASSERT: changes in attributes are detected """

                self.m1.set_content("""
            dir mode=0755 owner=root group=sys path=bin
            dir mode=0755 owner=root group=sys path=bin/foo
            file 00000000 mode=0644 owner=root group=sys path=a
            link path=bin/change-link target=change variant.opensolaris.zone=global
                    """)

                self.m2.set_content("""
            dir mode=0755 owner=root group=sys path=bin
            dir mode=0555 owner=root group=sys path=bin/foo
            file 00000000 mode=0444 owner=root group=sys path=a
            link path=bin/change-link target=change variant.opensolaris.zone=nonglobal
                    """)

                diffs = self.m2.combined_difference(self.m1)
                #
                # Expect to see a directory -> directory, file -> file, etc.
                # 3 of the 4 things above should have changed.
                #
                self.assertEqual(len(diffs), 3)
                for d in diffs:
                        self.assertEqual(type(d[0]), type(d[1]))


        def test_diffs8(self):
                """ ASSERT: changes in checksum are detected """

                self.m1.set_content("""
                    file 00000000 mode=0444 owner=root group=sys path=a
                    file 00000001 mode=0444 owner=root group=sys path=b
                    """)
                self.m2.set_content("""
                    file 00000000 mode=0444 owner=root group=sys path=a
                    file 00000002 mode=0444 owner=root group=sys path=b
                    """)

                diffs = self.m2.combined_difference(self.m1)
                #
                # Expect to see b change.
                #
                self.assertEqual(len(diffs), 1)
                for d in diffs:
                        self.assertEqual(type(d[0]), type(d[1]))
                        self.assertEqual(d[0].attrs["path"], "b")

        def test_diffs9(self):
                """ ASSERT: addition and removal are detected """

                self.m1.set_content(self.diverse_contents)
                self.m2.set_content("")

                diffs = self.m2.combined_difference(self.m1)
                diffs2 = self.m1.combined_difference(self.m2)

                #
                # Expect to see something -> None differences
                #
                self.assertEqual(len(diffs), 7)
                for d in diffs:
                        self.assertEqual(type(d[1]), types.NoneType)

                #
                # Expect to see None -> something differences
                #
                self.assertEqual(len(diffs2), 7)
                for d in diffs2:
                        self.assertEqual(type(d[0]), types.NoneType)
                        self.assertNotEqual(type(d[1]), types.NoneType)

        def test_diffs10(self):
                """ ASSERT: changes in target are detected """

                self.m1.set_content("""
                    link target=old path=a
                    hardlink target=old path=b
                    """)
                self.m2.set_content("""
                    link target=new path=a
                    hardlink target=new path=b
                    """)

                diffs = self.m2.combined_difference(self.m1)
                #
                # Expect to see differences in which "target" flips from "old"
                # to "new"
                #
                self.assertEqual(len(diffs), 2)
                for d in diffs:
                        self.assertEqual(type(d[0]), type(d[1]))
                        self.assertEqual(d[0].attrs["target"], "old")
                        self.assertEqual(d[1].attrs["target"], "new")


        def test_dups1(self):
                """ Test the duplicate search.  /bin shouldn't show up, since
                    they're identical actions, but /usr should show up three
                    times."""

                # XXX dp: "duplicates" is an odd name for this routine.

                self.m1.set_content("""\
dir mode=0755 owner=root group=sys path=bin
dir mode=0755 owner=root group=sys path=bin
dir mode=0755 owner=root group=sys path=bin
dir mode=0755 owner=root group=sys path=usr
dir mode=0755 owner=root group=root path=usr
dir mode=0755 owner=bin group=sys path=usr
                        """)

                acount = 0
                for kv, actions in self.m1.duplicates():
                        self.assertEqual(kv, ('dir', 'usr'))
                        for a in actions:
                                acount += 1
                                #print " %s %s" % (kv, a)
                self.assertEqual(acount, 3)

        def test_errors(self):
                """ test that a variety of bogus manifests yield ActionErrors """
                self.assertRaises(actions.ActionError,
                    self.m1.set_content, "foobar 1234 owner=root")

                self.assertRaises(actions.ActionError,
                    self.m1.set_content, "file 1234 path=foo bar")

                self.assertRaises(actions.ActionError,
                    self.m1.set_content, "file 1234 path=\"foo bar")

                self.assertRaises(actions.ActionError,
                    self.m1.set_content, "file 1234 =")

        def test_validate(self):
                """Verifies that Manifest validation works as expected."""

                self.m2.set_content(self.m2_contents, signatures=True)
                self.m2.validate(signatures=self.m2_signatures)

                self.m2.set_content(self.diverse_contents, signatures=True)
                self.assertRaises(api_errors.BadManifestSignatures,
                    self.m2.validate, signatures=self.m2_signatures)

                # Verify a manifest that has its content set using a byte string
                # has the same signature as that of one set with a Unicode
                # string when the content is the same.
                bstr = "set name=pkg.summary:th value=\"ซอฟต์แวร์ \""
                m1 = manifest.Manifest()
                m1.set_content(bstr, signatures=True)
                output1 = "".join(m1.as_lines())

                m2 = manifest.Manifest()
                m2.set_content(unicode(bstr, "utf-8"), signatures=True)
                output2 = "".join(m2.as_lines())
                self.assertEqualDiff(output1, output2)
                self.assertEqualDiff(m1.signatures, m2.signatures)


if __name__ == "__main__":
        unittest.main()
