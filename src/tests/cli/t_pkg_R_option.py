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

# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import unittest


class TestROption(pkg5unittest.SingleDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, self.foo10)
                self.image_create(self.rurl)

        def test_bad_cli_options(self):
                """Verify that pkg rejects invalid -R combos and values."""

                self.pkg("-@", exit=2)
                self.pkg("-s status", exit=2)
                self.pkg("-R status", exit=2)
                self.pkg("-R / version", exit=2)

        def test_1_explicit(self):
                """Ensure that pkg explicit image specification works as
                expected."""

                imgpath = self.img_path()
                badpath = self.test_root

                # Verify that bad paths cause exit and good paths succeed.
                self.pkg("-R {0} list".format(badpath), exit=1)
                self.pkg("-R {0} list".format(imgpath), exit=1)

                self.pkg("-R {0} install foo".format(badpath), exit=1)
                self.pkg("-R {0} install foo".format(imgpath))

                self.pkg("-R {0} list".format(badpath), exit=1)
                self.pkg("-R {0} list".format(imgpath))

                self.pkgsend_bulk(self.rurl, self.foo10)
                self.pkg("-R {0} refresh".format(imgpath))

                self.pkg("-R {0} update".format(badpath), exit=1)
                self.pkg("-R {0} update --be-name NEWBENAME".format(imgpath), exit=1)
                self.pkg("-R {0} update".format(imgpath))

                self.pkg("-R {0} uninstall foo".format(badpath), exit=1)
                self.pkg("-R {0} install foo".format(imgpath), exit=4)

                self.pkg("-R {0} info foo".format(badpath), exit=1)
                self.pkg("-R {0} info foo".format(imgpath))

        def test_2_implicit(self):
                """Ensure that pkg implicit image finding works as expected."""

                # Should fail because $PKG_IMAGE is set to test root by default,
                # and default test behaviour to use -R self.img_path() was
                # disabled.
                self.pkg("install foo", exit=1, use_img_root=False)

                # Unset unit testing default bogus image dir.
                del os.environ["PKG_IMAGE"]
                os.chdir(self.img_path())
                self.assertEqual(os.getcwd(), self.img_path())

                if portable.osname != "sunos":
                        # For other platforms, first install a package using an
                        # explicit root, and then verify that an implicit find
                        # of the image results in the right image being found.
                        self.pkg("install foo")
                        self.pkg("info foo", use_img_root=False)

                        # Remaining tests are not valid on other platforms.
                        return

                # Should fail because live root is not an image (Solaris 10
                # case), even though CWD contains a valid one since
                # PKG_FIND_IMAGE was not set in environment.
                bad_live_root = os.path.join(self.test_root, "test_2_implicit")
                os.mkdir(bad_live_root)
                self.pkg("-D simulate_live_root={0} install foo ".format(bad_live_root),
                     use_img_root=False, exit=1)

                # Should succeed because image is found at simulated live root,
                # even though one does not exist in CWD.
                os.chdir(self.test_root)
                self.pkg("-D simulate_live_root={0} install foo".format(
                    self.img_path()), use_img_root=False)

                # Should succeed because image is found using CWD and
                # PKG_FIND_IMAGE was set in environment, even though live root
                # is not a valid image.
                os.environ["PKG_FIND_IMAGE"] = "true"
                os.chdir(self.img_path())
                self.pkg("-D simulate_live_root={0} uninstall foo".format(
                     bad_live_root, use_img_root=False))
                del os.environ["PKG_FIND_IMAGE"]
                os.chdir(self.test_root)


if __name__ == "__main__":
        unittest.main()
