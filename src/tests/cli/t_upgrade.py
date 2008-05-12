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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import unittest

class TestUpgrade(testutils.SingleDepotTestCase):

        incorp10 = """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@1.0
            add depend type=incorporate fmri=pkg:/bronze@1.0
            close
        """

        incorp20 = """
            open incorp@2.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        incorpA = """
            open incorpA@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@1.0
            add depend type=incorporate fmri=pkg:/bronze@1.0
            close
        """

        incorpB =  """
            open incorpB@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        amber10 = """
            open amber@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add dir mode=0755 owner=root group=bin path=/etc
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add link path=/lib/libc.symlink target=/lib/libc.so.1
            add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
            add file /tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
            add file /tmp/amber2 mode=0444 owner=root group=bin path=/etc/amber2
            add license /tmp/copyright1 license=copyright
            close
        """

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file /tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze target=/lib/libc.so.1
            add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file /tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add depend fmri=pkg:/amber@1.0 type=require
            add license /tmp/copyright2 license=copyright
            close
        """

        amber20 = """
            open amber@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add link path=/lib/libc.symlink target=/lib/libc.so.1
            add hardlink path=/lib/libc.amber target=/lib/libc.bronze
            add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
            add file /tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
            add file /tmp/amber2 mode=0444 owner=root group=bin path=/etc/bronze2
            add depend fmri=pkg:/bronze@2.0 type=require
            add license /tmp/copyright2 license=copyright
            close
        """

        bronze20 = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file /tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license /tmp/copyright3 license=copyright
            add file /tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close 
        """

        misc_files = [ "/tmp/amber1", "/tmp/amber2",
                    "/tmp/bronzeA1",  "/tmp/bronzeA2",
                    "/tmp/bronze1", "/tmp/bronze2",
                    "/tmp/copyright1", "/tmp/copyright2",
                    "/tmp/copyright3", "/tmp/copyright4",
                    "/tmp/libc.so.1", "/tmp/sh"]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)
                
        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        def test_upgrade1(self):
                """ Upgrade torture test.
                    Send package amber@1.0, bronze1.0; install bronze1.0, which
                    should cause amber to also install.
                    Send 2.0 versions of packages which contains a lot of
                    complex transactions between amber and bronze, then do
                    an image-update, and try to check the results.
                """

                # Send 1.0 versions of packages.
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.incorp10)
                self.pkgsend_bulk(durl, self.amber10)
                self.pkgsend_bulk(durl, self.bronze10)

                self.image_create(durl)
                self.pkg("install incorp@1.0")
                self.pkg("install bronze")

                self.pkg("list amber@1.0")
                self.pkg("list bronze@1.0")
                self.pkg("verify -v")

                #
                # Now send 2.0 versions of packages.  image-update will (should)
                # implicitly refresh.
                #
                # In version 2.0, several things happen:
                #
                # Amber and Bronze swap a file with each other in both directions.
                # The dependency flips over (Amber now depends on Bronze)
                # Amber and Bronze swap ownership of various directories.
                #
                # Bronze's 1.0 hardlink to amber's libc goes away and is replaced
                # with a file of the same name.  Amber hardlinks to that.
                #
                self.pkgsend_bulk(durl, self.incorp20)
                self.pkgsend_bulk(durl, self.amber20)
                self.pkgsend_bulk(durl, self.bronze20)

                # Now image-update to get new versions of amber and bronze
                self.pkg("image-update")

                # Try to verify that it worked.
                self.pkg("list")
                self.pkg("list -a")
                self.pkg("list amber@2.0")
                self.pkg("list bronze@2.0")
                self.pkg("verify -v")
                # make sure old implicit directories for bronzeA1 were removed
                self.assert_(not os.path.isdir(os.path.join(self.get_img_path(), "A")))                
                # Remove packages
                self.pkg("uninstall amber bronze")
                self.pkg("verify -v")

                # make sure all directories are gone save /var in test image
                self.assert_(os.listdir(self.get_img_path()) ==  ["var"])

        def test_upgrade2(self):
                """ Basic test for incorporations """

                # Send all pkgs
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.incorpA)
                self.pkgsend_bulk(durl, self.amber10)
                self.pkgsend_bulk(durl, self.bronze10)
                self.pkgsend_bulk(durl, self.incorpB)
                self.pkgsend_bulk(durl, self.amber20)
                self.pkgsend_bulk(durl, self.bronze20)

                self.image_create(durl)
                self.pkg("install incorpA")
                self.pkg("install incorpB")
                self.pkg("install bronze")
                self.pkg("list bronze@2.0")
                self.pkg("verify -v")
                
if __name__ == "__main__":
        unittest.main()
