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

import os
import re
import time
import errno
import unittest
import shutil
import sys
from stat import *

class TestPkgCollidingLinks(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        pkg_A = """
        open pkg_A@1.0,5.11-0
        add file /tmp/link_target_0 mode=0555 owner=root group=bin path=link_target_0
        add file /tmp/link_target_1 mode=0555 owner=root group=bin path=link_target_1
        add file /tmp/link_target_2 mode=0555 owner=root group=bin path=link_target_2
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


        misc_files = [p for p in pkg_A.split() if p.startswith("/")]


        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)

                for p in self.misc_files:
                        path = os.path.dirname(p)
                        if not os.path.exists(path):
                                os.makedirs(path)
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)

                depot = self.dc.get_depot_url()
                self.pkgsend_bulk(depot, self.pkg_A)
                self.pkgsend_bulk(depot, self.pkg_B)
                self.pkgsend_bulk(depot, self.pkg_C)

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)


        def test_1(self):
                """Verify symlinks are correctly reference counted
                during installation & removal of packages"""
                # create an image w/ locales set
                depot = self.dc.get_depot_url()
                self.image_create(depot)
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
