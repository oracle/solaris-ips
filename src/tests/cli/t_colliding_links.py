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

# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest


class TestPkgCollidingLinks(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg_A = """
        open pkg_A@1.0,5.11-0
        add file tmp/link_target_0 mode=0555 owner=root group=bin path=link_target_0
        add file tmp/link_target_1 mode=0555 owner=root group=bin path=link_target_1
        add file tmp/link_target_2 mode=0555 owner=root group=bin path=link_target_2
        close"""

        pkg_B = """
        open pkg_B@1.0,5.11-0
        add link path=0 target=./link_target_0
        add link path=1 target=./link_target_1
        add link path=2 target=./link_target_2
        close"""

        pkg_C = """
        open pkg_C@1.0,5.11-0
        add link path=0 target=./link_target_0
        add link path=1 target=./link_target_1
        add link path=/2 target=./link_target_2
        close"""


        misc_files = [p for p in pkg_A.split() if "tmp/link_target" in p]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, (self.pkg_A, self.pkg_B,
                    self.pkg_C))

        def test_1(self):
                """Verify symlinks are correctly reference counted
                during installation & removal of packages"""
                # create an image 
                self.image_create(self.rurl)
                # install packages and verify

                self.pkg("install pkg_A pkg_B")
                self.pkg("verify")

                # add a pkg w/ duplicate links
                self.pkg("install pkg_C")
                self.pkg("verify")

                # cause trouble.
                self.pkg("uninstall pkg_C")
                self.pkg("verify")

                # readd a pkg w/ duplicate links
                self.pkg("install pkg_C")
                self.pkg("verify")

                self.pkg("uninstall pkg_B pkg_C")
                self.pkg("verify")

class TestPkgCollidingHardLinks(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg_A = """
        open pkg_A@1.0,5.11-0
        add file tmp/link_target_0 mode=0555 owner=root group=bin path=link_target_0
        add file tmp/link_target_1 mode=0555 owner=root group=bin path=link_target_1
        add file tmp/link_target_2 mode=0555 owner=root group=bin path=link_target_2
        close
        open pkg_A@2.0,5.11-0
        add file tmp/link_target_3 mode=0555 owner=root group=bin path=link_target_0
        add file tmp/link_target_4 mode=0555 owner=root group=bin path=link_target_1
        add file tmp/link_target_5 mode=0555 owner=root group=bin path=link_target_2
        close"""

        pkg_B = """
        open pkg_B@1.0,5.11-0
        add hardlink path=0 target=./link_target_0
        add hardlink path=1 target=./link_target_1
        add hardlink path=2 target=./link_target_2
        add depend type=require fmri=pkg_A@1.0,5.11-0
        close"""

        pkg_C = """
        open pkg_C@1.0,5.11-0
        add hardlink path=0 target=./link_target_0
        add hardlink path=1 target=./link_target_1
        add hardlink path=2 target=./link_target_2
        add depend type=require fmri=pkg_A@1.0,5.11-0
        close"""


        misc_files = [p for p in pkg_A.split() if "tmp/link_target" in p]


        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, (self.pkg_A, self.pkg_B,
                    self.pkg_C))

        def check_link_count(self, n):
                """ Make sure link count is what we think it should be"""
                for f in ("link_target_{0:d}".format(i) for i in range(3)):
                        self.assertEqual(os.stat(os.path.join(self.get_img_path(), 
                            f)).st_nlink, n)
 
        def test_1(self):
                """Verify hardlinks are correctly reference counted
                during installation & removal of packages"""
                # create an image 
                self.image_create(self.rurl)
                # install packages and verify

                self.pkg("install pkg_A@1.0")
                self.check_link_count(1)

                self.pkg("install pkg_B")
                self.pkg("verify")
                self.check_link_count(2)

                # add a pkg w/ duplicate links
                self.pkg("install pkg_C")
                self.pkg("verify")
                self.check_link_count(2)

                # cause trouble.
                self.pkg("uninstall pkg_C")
                self.pkg("verify")
                self.check_link_count(2)

                # readd a pkg w/ duplicate links
                self.pkg("install pkg_C")
                self.pkg("verify")
                self.check_link_count(2)

                # update the files the links all point to
                self.pkg("install pkg_A@2.0")
                self.pkg("verify")

                self.pkg("uninstall pkg_B pkg_C")
                self.pkg("verify")
                self.check_link_count(1)
                
if __name__ == "__main__":
        unittest.main()
