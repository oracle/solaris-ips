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

# Copyright (c) 2008, 2023, Oracle and/or its affiliates.

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest
import shutil


class TestPkgRebuildIndex(pkg5unittest.SingleDepotTestCase):
    # Only start/stop the depot once (instead of for every test)
    persistent_setup = True

    example_pkg11 = """
            open example_pkg@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path11
            close """

    misc_files = ["tmp/example_file"]

    def setUp(self):
        # This test suite needs actual depots.
        pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)
        self.make_misc_files(self.misc_files)

        self.durl1 = self.dcs[1].get_depot_url()
        self.pkgsend_bulk(self.durl1, self.example_pkg11)

    def test_rebuild_index_bad_opts(self):
        """Test pkg with bad options."""

        self.image_create(self.rurl)
        self.pkg("rebuild-index -@", exit=2)
        self.pkg("rebuild-index foo", exit=2)
        self.pkg("rebuild-index --", exit=2)

    def test_rebuild_index_bad_perms(self):
        """Testing for bug 4570."""

        self.image_create(self.rurl)
        self.pkg("rebuild-index")
        self.pkg("rebuild-index", exit=1, su_wrap=True)

    def test_rebuild_index_stale_index_old_dir(self):
        """Test rebuild-index for a stale index.old dir."""

        self.image_create(self.rurl)
        self.pkg("install example_pkg@1.1")

        index_dir = os.path.join(self.img_path(), "var", "pkg",
                    "cache", "index")
        shutil.copytree(index_dir, index_dir + ".old")

        self.pkg("rebuild-index")


if __name__ == "__main__":
    unittest.main()
