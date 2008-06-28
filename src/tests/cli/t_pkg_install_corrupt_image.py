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

import os
import unittest

class TestImageCreateCorruptImage(testutils.SingleDepotTestCaseCorruptImage):
        """
        If a new essential directory is added to the format of an image it will
        be necessary to update this test suite. To update this test suite,
        decide in what ways it is necessary to corrupt the image (removing the
        new directory or file, or removing the some or all of contents of the
        new directory for example). Make the necessary changes in
        testutils.SingleDepotTestCaseCorruptImage to allow the needed
        corruptions, then add new tests to the suite below. Be sure to add
        tests for both Full and User images, and perhaps Partial images if
        situations are found where these behave differently than Full or User
        images.
        """
        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        misc_files = [ "/tmp/libc.so.1" ]

        def setUp(self):
                testutils.SingleDepotTestCaseCorruptImage.setUp(self)
                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)

        def tearDown(self):
                testutils.SingleDepotTestCaseCorruptImage.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        # For each test:
        # A good image is created at $basedir/image
        # A corrupted image is created at $basedir/image/bad (called bad_dir
        #     in subsequent notes) in verious ways
        # The $basedir/image/bad/final directory is created and PKG_IMAGE
        #     is set to that dirctory.

        # Tests simulating a corrupted Full Image

        def test_empty_var_pkg(self):
                """ Creates an empty bad_dir. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl,
                    set(["catalog", "cfg_cache", "file", "pkg", "index"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_catalog(self):
                """ Creates bad_dir with only the catalog dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["catalog_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_cfg_cache(self):
                """ Creates bad_dir with only the cfg_cache file missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["cfg_cache_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_file(self):
                """ Creating bad_dir with only the file dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["file_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_pkg(self):
                """ Creates bad_dir with only the pkg dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["pkg_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_index(self):
                """ Creates bad_dir with only the index dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["index_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_catalog_empty(self):
                """ Creates bad_dir with all dirs and files present, but
                with an empty catalog dir.
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["catalog_empty"]),
                    ["var/pkg"])

                # This is expected to fail because it will see an empty
                # catalog directory and not rebuild the files as needed
                self.pkg("install foo@1.1", exit = 1)

        def test_var_pkg_missing_catalog_empty_hit_then_refreshed_then_hit(
            self):
                """ Creates bad_dir with all dirs and files present, but
                with an empty catalog dir. This is to ensure that refresh
                will work, and that an install after the refresh also works.
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["catalog_empty"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1", exit = 1)
                self.pkg("refresh")
                self.pkg("install foo@1.1")


        def test_var_pkg_left_alone(self):
                """ Sanity check to ensure that the code for creating
                a bad_dir creates a good copy other than what's specified
                to be wrong. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(), ["var/pkg"])

                self.pkg("install foo@1.1")

        # Tests simulating a corrupted User Image

        # These tests are duplicates of those above but instead of creating
        # a corrupt full image, they create a corrupt User image.

        def test_empty_ospkg(self):
                """ Creates a corrupted image at bad_dir by creating empty
                bad_dir.  """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl,
                    set(["catalog", "cfg_cache", "file", "pkg", "index"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_catalog(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the catalog dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["catalog_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_cfg_cache(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the cfg_cache file missing.  """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["cfg_cache_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_file(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the file dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["file_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_pkg(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the pkg dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["pkg_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_index(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the index dir missing. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["index_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_catalog_empty(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with all dirs and files present, but with an empty
                catalog dir. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["catalog_empty"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1", exit = 1)

        def test_ospkg_missing_catalog_empty_hit_then_refreshed_then_hit(self):
                """ Creates bad_dir with all dirs and files present, but
                with an empty catalog dir. This is to ensure that refresh
                will work, and that an install after the refresh also works.
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["catalog_empty"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1", exit = 1)
                self.pkg("refresh")
                self.pkg("install foo@1.1")


        def test_ospkg_left_alone(self):
                """ Sanity check to ensure that the code for creating
                a bad_dir creates a good copy other than what's specified
                to be wrong. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(), [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

# Tests for checking what happens when two images are installed side by side.

        def test_var_pkg_missing_cfg_cache_ospkg_also_missing_alongside(self):
                """ Each bad_dir is missing a cfg_cache
                These 3 tests do nothing currently because trying to install an
                image next to an existing image in not currently possible.  The
                test cases remain against the day that such an arrangement is
                possible.
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["cfg_cache_absent"]),
                    [".org.opensolaris,pkg"])
                self.corrupt_image_create(durl, set(["cfg_cache_absent"]),
                    ["var/pkg"], destroy = False)

                self.pkg("install foo@1.1")


        def test_var_pkg_ospkg_missing_cfg_cache_alongside(self):
                """ Complete Full image besides a User image missing cfg_cache
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(), ["var/pkg"])
                self.corrupt_image_create(durl, set(["cfg_cache_absent"]),
                    [".org.opensolaris,pkg"], destroy = False)

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_cfg_cache_ospkg_alongside(self):
                """ Complete User image besides a Full image missing cfg_cache
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                self.corrupt_image_create(durl, set(["cfg_cache_absent"]),
                    ["var/pkg"])
                self.corrupt_image_create(durl, set(),
                    [".org.opensolaris,pkg"], destroy = False)

                self.pkg("install foo@1.1")


if __name__ == "__main__":
        unittest.main()
