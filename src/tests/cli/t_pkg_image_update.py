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

class TestImageUpdate(testutils.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        foo10 = """
            open foo@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        bar11 = """
            open bar@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 3)
                durl1 = self.dcs[1].get_depot_url()
                durl2 = self.dcs[2].get_depot_url()
                durl3 = self.dcs[3].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo10 + self.foo11)
                self.pkgsend_bulk(durl2, self.bar10 + self.bar11)

        def test_image_update_bad_opts(self):
                """Test image-update with bad options."""

                durl1 = self.dcs[1].get_depot_url()
                self.image_create(durl1)

                self.pkg("image-update -@", exit=2)
                self.pkg("image-update -vq", exit=2)
                self.pkg("image-update foo", exit=2)

        def test_after_pub_removal(self):
                """Install packages from multiple publishers, then verify that
                removal of the second publisher will not prevent an
                image-update."""

                durl1 = self.dcs[1].get_depot_url()
                durl2 = self.dcs[2].get_depot_url()
                durl3 = self.dcs[3].get_depot_url()
                self.image_create(durl1)

                # Install a package from the preferred publisher.
                self.pkg("install foo@1.0")

                # Install a package from a second publisher.
                self.pkg("set-publisher -O %s test2" % durl2)
                self.pkg("install bar@1.0")

                # Remove the publisher of an installed package, then add the
                # publisher back, but with an empty repository.  An image-update
                # should still be possible.
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O %s test2" % durl3)
                self.pkg("image-update -nv")

                # Add two publishers using the removed publisher's repository,
                # an image-update should be possible despite the conflict.
                self.pkg("set-publisher -O %s test3" % durl2)
                self.pkg("set-publisher -O %s test4" % durl2)
                self.pkg("image-update -nv")
                self.pkg("unset-publisher test4")
                self.pkg("unset-publisher test3")

                # With the publisher of an installed package unknown, add a new
                # publisher using the repository the package was originally
                # installed from.  An image-update should still be possible (see
                # bug 6856).
                self.pkg("set-publisher -O %s test3" % durl2)
                self.pkg("image-update -nv")

                # Remove the publisher of an installed package, then add the
                # publisher back, but with an empty catalog.  Then add a new
                # publisher using the repository the package was originally
                # installed from.  An image-update should still be possible (see
                # bug 6856).
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O %s test2" % durl3)
                self.pkg("set-publisher -O %s test3" % durl2)
                self.pkg("image-update -nv")


if __name__ == "__main__":
        unittest.main()

