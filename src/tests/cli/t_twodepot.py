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

class TestTwoDepots(testutils.ManyDepotTestCase):

        foo10 = """
            open foo@1.0,5.11-0
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        moo10 = """
            open moo@1.0,5.11-0
            close """

        def setUp(self):
                """ Start two depots.
                    depot 1 gets foo and moo, depot 2 gets foo and bar
                    depot1 is mapped to authority test1 (preferred)
                    depot2 is mapped to authority test2 """

                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo10)
                self.pkgsend_bulk(durl1, self.moo10)

                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.foo10)
                self.pkgsend_bulk(durl2, self.bar10)

                # Create image and hence primary authority
                self.image_create(durl1, prefix="test1")

                # Create second authority using depot #2
                self.pkg("set-authority -O " + durl2 + " test2")

                self.pkg("refresh")


        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)

        def test_basics_1(self):
                self.pkg("list -a")

                # Install and uninstall moo (which is unique to depot 1)
                self.pkg("install moo")

                self.pkg("list")
                self.pkg("uninstall moo")

                # Install and uninstall bar (which is unique to depot 2)
                self.pkg("install bar")

                self.pkg("list")

                self.pkg("uninstall bar")

                # Install and uninstall foo (which is in both depots)
                # In this case, we should select foo from depot 1, since
                # it is preferred.
                self.pkg("install foo")

                self.pkg("list pkg://test1/foo")

                self.pkg("uninstall foo")

        def test_basics_2(self):
                """ Test install from an explicit preferred authority """
                self.pkg("install pkg://test1/foo")
                self.pkg("list pkg://test1/foo")
                self.pkg("uninstall foo")

        def test_basics_3(self):
                """ Test install from an explicit non-preferred authority """
                self.pkg("install pkg://test2/foo")
                self.pkg("list pkg://test2/foo")
                self.pkg("uninstall foo")


if __name__ == "__main__":
        unittest.main()

