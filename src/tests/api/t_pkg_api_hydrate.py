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

import pkg.client.api_errors as api_errors


class TestPkgApiHydrate(pkg5unittest.SingleDepotTestCase):

        dev10 = """
            open dev@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dev
            add dir mode=0755 owner=root group=bin path=dev/cfg
            add file dev/cfg/bar path=dev/cfg/bar mode=0644 owner=root group=bin preserve=true
            add file dev/cfg/bar1 path=dev/cfg/bar1 mode=0555 owner=root group=bin
            add file dev/cfg/bar2 path=dev/cfg/bar2 mode=0644 owner=root group=bin overlay=true
            add hardlink path=dev/cfg/bar2.hlink target=bar2
            close
            """

        misc_files = ["dev/cfg/bar", "dev/cfg/bar1", "dev/cfg/bar2",
            "dev/cfg/bar2.hlink"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, self.dev10)

        def test_01_basic(self):
                api_inst = self.image_create(self.rurl)
                self._api_install(api_inst, ["dev"])

                self._api_dehydrate(api_inst)

                # Verify that files are deleted or remained as expected.
                self.file_exists("dev/cfg/bar")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_exists("dev/cfg/bar2")
                self.file_doesnt_exist("dev/cfg/bar2.hlink")

                self._api_rehydrate(api_inst)
                self.pkg("verify")

        def test_bad_publishers(self):
                api_inst = self.image_create(self.rurl)
                self._api_install(api_inst, ["dev"])

                # Test that dehydrate will raise a PlanCreationException when
                # encountering bad publishers.
                self.assertRaises(api_errors.PlanCreationException,
                    lambda *args, **kwargs: list(
                        api_inst.gen_plan_dehydrate(*args, **kwargs)),
                    ["-p nosuch", "-p unknown", "-p test"])

                # Test that rehydrate will raise a PlanCreationException when
                # encountering bad publishers.
                self.assertRaises(api_errors.PlanCreationException,
                    lambda *args, **kwargs: list(
                        api_inst.gen_plan_rehydrate(*args, **kwargs)),
                    ["-p nosuch", "-p unknown", "-p test"])


if __name__ == "__main__":
        unittest.main()
