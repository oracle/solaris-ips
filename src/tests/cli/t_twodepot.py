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
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        foo10 = """
            open foo@1.0,5.11-0
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        moo10 = """
            open moo@1.0,5.11-0
            close """

        upgrade_p10 = """
            open upgrade-p@1.0,5.11-0
            close"""

        upgrade_p11 = """
            open upgrade-p@1.1,5.11-0
            close"""

        upgrade_np10 = """
            open upgrade-np@1.0,5.11-0
            close"""

        upgrade_np11 = """
            open upgrade-np@1.1,5.11-0
            close"""

        incorp_p10 = """
            open incorp-p@1.0,5.11-0
            add depend type=incorporate fmri=upgrade-p@1.0
            close"""

        incorp_p11 = """
            open incorp-p@1.1,5.11-0
            add depend type=incorporate fmri=upgrade-p@1.1
            close"""

        incorp_np10 = """
            open incorp-np@1.0,5.11-0
            add depend type=incorporate fmri=upgrade-np@1.0
            close"""

        incorp_np11 = """
            open incorp-np@1.1,5.11-0
            add depend type=incorporate fmri=upgrade-np@1.1
            close"""

        def setUp(self):
                """ Start two depots.
                    depot 1 gets foo and moo, depot 2 gets foo and bar
                    depot1 is mapped to authority test1 (preferred)
                    depot2 is mapped to authority test2 """

                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo10)
                self.pkgsend_bulk(durl1, self.moo10)
                self.pkgsend_bulk(durl1, self.upgrade_p10)
                self.pkgsend_bulk(durl1, self.upgrade_np11)
                self.pkgsend_bulk(durl1, self.incorp_p10)
                self.pkgsend_bulk(durl1, self.incorp_p11)
                self.pkgsend_bulk(durl1, self.incorp_np10)
                self.pkgsend_bulk(durl1, self.incorp_np11)

                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.foo10)
                self.pkgsend_bulk(durl2, self.bar10)
                self.pkgsend_bulk(durl2, self.upgrade_p11)
                self.pkgsend_bulk(durl2, self.upgrade_np10)

                # Create image and hence primary authority
                self.image_create(durl1, prefix="test1")

                # Create second authority using depot #2
                self.pkg("set-authority -O " + durl2 + " test2")

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
                self.pkg("list foo")
                self.pkg("list pkg://test1/foo")
                self.pkg("uninstall foo")

        def test_basics_3(self):
                """ Test install from an explicit non-preferred authority """
                self.pkg("install pkg://test2/foo")
                self.pkg("list foo")
                self.pkg("list pkg://test2/foo")
                self.pkg("uninstall foo")

        def test_upgrade_preferred_to_non_preferred(self):
                """Install a package from the preferred authority, and then
                upgrade it, implicitly switching to a non-preferred
                authority."""
                self.pkg("list -a upgrade-p")
                self.pkg("install upgrade-p@1.0")
                self.pkg("install upgrade-p@1.1")

        def test_upgrade_non_preferred_to_preferred(self):
                """Install a package from a non-preferred authority, and then
                upgrade it, implicitly switching to the preferred authority."""
                self.pkg("list -a upgrade-np")
                self.pkg("install upgrade-np@1.0")
                self.pkg("install upgrade-np@1.1")

        def test_upgrade_preferred_to_non_preferred_incorporated(self):
                """Install a package from the preferred authority, and then
                upgrade it, implicitly switching to a non-preferred
                authority, when the package is constrained by an
                incorporation."""
                self.pkg("list -a upgrade-p incorp-p")
                self.pkg("install incorp-p@1.0")
                self.pkg("install upgrade-p")
                self.pkg("install incorp-p@1.1")
                self.pkg("list upgrade-p@1.1")

        def test_upgrade_non_preferred_to_preferred_incorporated(self):
                """Install a package from the preferred authority, and then
                upgrade it, implicitly switching to a non-preferred
                authority, when the package is constrained by an
                incorporation."""
                self.pkg("list -a upgrade-np incorp-np")
                self.pkg("install incorp-np@1.0")
                self.pkg("install upgrade-np")
                self.pkg("install incorp-np@1.1")
                self.pkg("list upgrade-np@1.1")

if __name__ == "__main__":
        unittest.main()

