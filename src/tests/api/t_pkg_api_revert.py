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

#
# Copyright (c) 2014, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest


class TestPkgApiRevert(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkgs = """
            open A@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file1 mode=0555 owner=root group=bin path=etc/file1
            add file etc/file2 mode=0555 owner=root group=bin path=etc/file2
            close
            open B@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file3 mode=0555 owner=root group=bin path=etc/file3
            close
            """

        misc_files = ["etc/file1", "etc/file2", "etc/file3"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.rurl, self.pkgs)

        def test_changed_packages(self):
                """Verify that pkg revert correctly marks changed packages."""

                api_inst = self.image_create(self.rurl)

                # try reverting non-editable files
                self._api_install(api_inst, ["A@1.0", "B@1.0"])

                # remove a files from pkg A only
                self.file_remove("etc/file2")

                # make sure we broke only pkg A
                self.pkg("verify A", exit=1)
                self.pkg("verify B")

                # now see if revert when files in both packages are named only
                # marks pkg A as changed
                self._api_revert(api_inst, ["/etc/file2"], noexecute=True)
                plan = api_inst.describe()
                pfmri = self.plist[0]
                self.assertEqualDiff([(pfmri, pfmri)], [
                    (str(entry[0]), str(entry[1]))
                    for entry in plan.plan_desc
                ])

                # actually execute it, then check verify passes
                self._api_revert(api_inst, ["/etc/file2", "/etc/file3"])
                self.pkg("verify")


if __name__ == "__main__":
        unittest.main()
