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

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import unittest
import os
import re
import shutil
import difflib

class TestPkgList(testutils.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        foo1 = """
            open foo@1,5.11-0
            close """

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        foo12 = """
            open foo@1.2,5.11-0
            close """

        foo121 = """
            open foo@1.2.1,5.11-0
            close """

        food12 = """
            open food@1.2,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1)
                self.pkgsend_bulk(durl1, self.foo10)
                self.pkgsend_bulk(durl1, self.foo11)
                self.pkgsend_bulk(durl1, self.foo12)
                self.pkgsend_bulk(durl1, self.foo121)
                self.pkgsend_bulk(durl1, self.food12)

                durl2 = self.dcs[2].get_depot_url()

                # Ensure that the second repo's packages have exactly the same
                # timestamps as those in the first ... by copying the repo over.
                # If the repos need to have some contents which are different,
                # send those changes after restarting depot 2.
                self.dcs[2].stop()
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                shutil.rmtree(d2dir)
                shutil.copytree(d1dir, d2dir)
                self.dcs[2].start()

                self.image_create(durl1, prefix = "test1")

                self.pkg("set-authority -O " + durl2 + " test2")

        def reduceSpaces(self, string):
                """Reduce runs of spaces down to a single space."""
                return re.sub(" +", " ", string)

        def assertEqualDiff(self, expected, actual):
                self.assertEqual(expected, actual,
                    "Actual output differed from expected output.\n" +
                    "\n".join(difflib.unified_diff(
                        expected.splitlines(), actual.splitlines(),
                        "Expected output", "Actual output", lineterm="")))

        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)

        def test_list_1(self):
                """List all "foo@1.0" from auth "test1"."""
                self.pkg("list -aH pkg://test1/foo@1.0,5.11-0")
                expected = \
                    "foo 1.0-0 known u---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_list_2(self):
                """List all "foo@1.0", regardless of authority, with "pkg:/"
                prefix."""
                self.pkg("list -aH pkg:/foo@1.0,5.11-0")
                expected = \
                    "foo 1.0-0 known u---\n" \
                    "foo (test2) 1.0-0 known u---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_list_3(self):
                """List all "foo@1.0", regardless of authority, without "pkg:/"
                prefix."""
                self.pkg("list -aH pkg:/foo@1.0,5.11-0")
                expected = \
                    "foo         1.0-0 known u---\n" \
                    "foo (test2) 1.0-0 known u---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_4(self):
                """List all versions of package foo, regardless of authority."""
                self.pkg("list -aH foo")
                expected = \
                    "foo         1.2.1-0 known ----\n" \
                    "foo (test2) 1.2.1-0 known ----\n" \
                    "foo         1.2-0   known u---\n" \
                    "foo (test2) 1.2-0   known u---\n" \
                    "foo         1.1-0   known u---\n" \
                    "foo (test2) 1.1-0   known u---\n" \
                    "foo         1.0-0   known u---\n" \
                    "foo (test2) 1.0-0   known u---\n" \
                    "foo         1-0     known u---\n" \
                    "foo (test2) 1-0     known u---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_5(self):
                """Show foo@1.0 from both depots, but 1.1 only from test2."""
                self.pkg("list -aH foo@1.0-0 pkg://test2/foo@1.1-0")
                expected = \
                    "foo (test2) 1.1-0 known u---\n" + \
                    "foo         1.0-0 known u---\n" + \
                    "foo (test2) 1.0-0 known u---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_6(self):
                """Show versions 1.0 and 1.1 of foo only from authority test2."""
                self.pkg("list -aH pkg://test2/foo")
                expected = \
                    "foo (test2) 1.2.1-0 known ----\n" + \
                    "foo (test2) 1.2-0   known u---\n" + \
                    "foo (test2) 1.1-0   known u---\n" + \
                    "foo (test2) 1.0-0   known u---\n" + \
                    "foo (test2) 1-0     known u---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_7(self):
                """List all foo@1 from test1, but all foo@1.2(.x), and only list
                the latter once."""
                self.pkg("list -aH pkg://test1/foo@1 pkg:/foo@1.2")
                expected = \
                    "foo         1.2.1-0 known ----\n" + \
                    "foo (test2) 1.2.1-0 known ----\n" + \
                    "foo         1.2-0   known u---\n" + \
                    "foo (test2) 1.2-0   known u---\n" + \
                    "foo         1.1-0   known u---\n" + \
                    "foo         1.0-0   known u---\n" + \
                    "foo         1-0     known u---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_matching(self):
                """List all versions of package foo, regardless of authority."""
                self.pkg("list -aH foo*")
                expected = \
                    "foo         1.2.1-0 known ----\n" \
                    "foo (test2) 1.2.1-0 known ----\n" \
                    "foo         1.2-0   known u---\n" \
                    "foo (test2) 1.2-0   known u---\n" \
                    "foo         1.1-0   known u---\n" \
                    "foo (test2) 1.1-0   known u---\n" \
                    "foo         1.0-0   known u---\n" \
                    "foo (test2) 1.0-0   known u---\n" \
                    "foo         1-0     known u---\n" \
                    "foo (test2) 1-0     known u---\n" \
                    "food        1.2-0   known ----\n" \
                    "food (test2) 1.2-0  known ----\n"

                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH 'fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH '*fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH 'f?o*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_list_multi_name(self):
                """Test for multiple name match listing."""
                self.pkg("list -aH foo*@1.2")
                expected = \
                    "foo          1.2.1-0 known ----\n" + \
                    "foo  (test2) 1.2.1-0 known ----\n" + \
                    "foo          1.2-0   known u---\n" + \
                    "foo  (test2) 1.2-0   known u---\n" + \
                    "food         1.2-0   known ----\n" + \
                    "food (test2) 1.2-0   known ----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        # Put this one last since it screws the other tests up
        def test_list_z_empty_image(self):
                """ pkg list should fail in an empty image """

                self.image_create(self.dcs[1].get_depot_url())
                self.pkg("list", exit=1)

if __name__ == "__main__":
        unittest.main()
