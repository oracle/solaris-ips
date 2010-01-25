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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import unittest
import os
import re
import shutil
import difflib

class TestPkgContentsBasics(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file /tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file /tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license /tmp/copyright1 license=copyright
            close
        """

        misc_files = [ "/tmp/bronzeA1",  "/tmp/bronzeA2",
                    "/tmp/bronze1", "/tmp/bronze2",
                    "/tmp/copyright1", "/tmp/sh"]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)

                self.pkgsend_bulk(self.dc.get_depot_url(), self.bronze10)

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        def assertEqualDiff(self, expected, actual):
                self.assertEqual(expected, actual,
                    "Actual output differed from expected output.\n" +
                    "\n".join(difflib.unified_diff(
                        expected.splitlines(), actual.splitlines(),
                        "Expected output", "Actual output", lineterm="")))

        def reduceSpaces(self, string):
                """Reduce runs of spaces down to a single space."""
                return re.sub(" +", " ", string)

	def test_contents_bad_opts(self):

		self.image_create(self.dc.get_depot_url())

                self.pkg("contents -@", exit=2)
                self.pkg("contents -m -r", exit=2)
                self.pkg("contents -o", exit=2)
                self.pkg("contents -s", exit=2)
                self.pkg("contents -t", exit=2)
                self.pkg("contents foo@x.y", exit=1)
                self.pkg("contents -a foo", exit=2)

        def test_contents_empty_image(self):
                """local pkg contents should fail in an empty image; remote
                should succeed on a match """

                self.image_create(self.dc.get_depot_url())
                self.pkg("contents -m", exit=1)
                self.pkg("contents -m -r bronze@1.0", exit=0)

        def test_contents_1(self):
                """get contents"""
                self.image_create(self.dc.get_depot_url())
                self.pkg("install bronze@1.0")
                self.pkg("contents")
                self.pkg("contents -m")

        def test_contents_2(self):
                """test that local and remote contents are the same"""
                self.image_create(self.dc.get_depot_url())
                self.pkg("install bronze@1.0")
                self.pkg("contents -m bronze@1.0")
                x = sorted(self.output.splitlines())
                x = "".join(x) 
                x = self.reduceSpaces(x)
                self.pkg("contents -r -m bronze@1.0")
                y = sorted(self.output.splitlines())
                y = "".join(y)
                y = self.reduceSpaces(y)
                self.assertEqualDiff(x, y)

        def test_contents_3(self):
                """ test matching """
                self.image_create(self.dc.get_depot_url())
                self.pkg("install bronze@1.0")
                self.pkg("contents 'bro*'")

        def test_contents_failures(self):
                """ attempt to get contents of non-existent packages """
                self.image_create(self.dc.get_depot_url())
                self.pkg("contents bad", exit=1)
                self.pkg("contents -r bad", exit=1)

        def test_contents_dash_a(self):
                """Test the -a option of contents"""
                self.image_create(self.dc.get_depot_url())
                self.pkg("install bronze")

                # Basic -a
                self.pkg("contents -H -o action.hash -a path=usr/bin/sh")
                self.assert_(self.output.rstrip() ==
                    "f2b5bfd72a6b759e4e47599f828a174a0668b243")

                # -a with a pattern
                self.pkg("contents -H -o action.hash -a path=etc/bronze*")
                self.assert_(self.output.splitlines() == [
                    "28f75bcd652b188fbe0a7938265aa5d9196cb7e8",
                    "3bb4541b7c38be84b76994cce8bc8233d5bc9720"])

                # Multiple -a
                self.pkg("contents -H -o action.hash -a path=etc/bronze1 "
                    "-a mode=0555")
                self.assert_(self.output.splitlines() == [
                    "28f75bcd652b188fbe0a7938265aa5d9196cb7e8",
                    "f2b5bfd72a6b759e4e47599f828a174a0668b243"])

                # Non-matching pattern should exit 1
                self.pkg("contents -a path=usr/bin/notthere", 1)

if __name__ == "__main__":
        unittest.main()
