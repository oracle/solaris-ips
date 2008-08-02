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

class TestContentsAndInfo(testutils.SingleDepotTestCase):

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

        def test_empty_image(self):
                """local pkg info/contents should fail in an empty image; remote
                should succeed on a match """

                self.image_create(self.dc.get_depot_url())
                self.pkg("contents -m", exit=1)
                self.pkg("info", exit=1)
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
                x = self.output
                self.pkg("contents -r -m bronze@1.0")
                y = self.output
                self.assert_(x == y)

        def test_contents_failures(self):
                """ attempt to get contents of non-existent packages """
                self.image_create(self.dc.get_depot_url())
                self.pkg("contents bad", exit=1)
                self.pkg("contents -r bad", exit=1)

        def test_info_local_remote(self):
                """pkg: check that info behaves for local and remote cases."""

                pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    close
                """

                pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    close
                """

                durl = self.dc.get_depot_url()

                self.pkgsend_bulk(durl, pkg1)
                self.pkgsend_bulk(durl, pkg2)

                self.image_create(durl)

                # Install one package and verify
                self.pkg("install jade")
                self.pkg("verify -v")
                
                # Check local info
                self.pkg("info jade | grep 'State: Installed'")
                self.pkg("info turquoise 2>&1 | grep 'no packages matching'")
                self.pkg("info emerald", exit=1)
                self.pkg("info emerald 2>&1 | grep 'no packages matching'")

                # Check remote info
                self.pkg("info -r jade | grep 'State: Installed'")
                self.pkg("info -r turquoise| grep 'State: Not installed'")
                self.pkg("info -r emerald", exit=1)
                self.pkg("info -r emerald 2>&1 | grep 'no packages matching'")


if __name__ == "__main__":
        unittest.main()
