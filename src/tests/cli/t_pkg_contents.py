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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import os
import shutil

class TestPkgContentsBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license tmp/copyright1 license=copyright
            close
        """

        nopathA10 = """
            open nopathA@1.0,5.11-0
            add license tmp/copyright1 license=copyright
            close
        """

        nopathB10 = """
            open nopathB@1.0,5.11-0
            add license tmp/copyright1 license=copyright
            close
        """

        # wire file contents to well known values so we're sure we
        # know their hashes.
        misc_files = {
                "tmp/bronzeA1": "magic1",
                "tmp/bronzeA2": "magic2",
                "tmp/bronze1": "magic3",
                "tmp/bronze2": "magic4",
                "tmp/copyright1": "magic5",
                "tmp/sh": "magic6",
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

                self.pkgsend_bulk(self.dc.get_depot_url(), self.bronze10)
                self.pkgsend_bulk(self.dc.get_depot_url(), self.nopathA10)
                self.pkgsend_bulk(self.dc.get_depot_url(), self.nopathB10)


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
                    "422bdb3eb2d613367933194e3f11220aebe56226")

                # -a with a pattern
                self.pkg("contents -H -o action.hash -a path=etc/bronze*")
                self.assert_(self.output.splitlines() == [
                    "02cdf31d12ccfb6d35e4b8eeff10535e22da3f7e",
                    "b14e4cdfee720f1eab645bcbfb76eca153301715"])

                # Multiple -a
                self.pkg("contents -H -o action.hash -a path=etc/bronze1 "
                    "-a mode=0555")
                self.assert_(self.output.splitlines() == [
                    "02cdf31d12ccfb6d35e4b8eeff10535e22da3f7e",
                    "422bdb3eb2d613367933194e3f11220aebe56226"])

                # Non-matching pattern should exit 1
                self.pkg("contents -a path=usr/bin/notthere", 1)

        def test_contents_nocolumns(self):
                """Test that when pkg contents doesn't find any actions that
                match the specified output columns, we produce appropriate
                error messages """

                self.image_create(self.dc.get_depot_url())
                self.pkg("install nopathA")
                self.pkg("install nopathB")

                # part of the messages that result in running pkg contents
                # when no output would result.  Note that pkg still returns 0
                # at present in these cases.
                # XXX Checking for a substring of an error message in a test case
                # isn't ideal.
                nopath = "This package delivers no filesystem content"
                nopath_plural = "These packages deliver no filesystem content"

                nofield = "This package contains no actions with the fields specified " \
                    "using the -o"
                nofield_plural = "These packages contain no actions with the fields " \
                    "specified using the -o"

                self.pkg("contents nopathA")
                self.assert_(nopath in self.output)

                self.pkg("contents nopathA nopathB")
                self.assert_(nopath_plural in self.output)

                self.pkg("contents -o noodles nopathA")
                self.assert_(nofield in self.output)

                self.pkg("contents -o noodles -o mice nopathA nopathB")
                self.assert_(nofield_plural in self.output)

if __name__ == "__main__":
        unittest.main()
