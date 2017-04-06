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

import unittest
import os


class TestPkgVersion(pkg5unittest.SingleDepotTestCase):

        def test_pkg_version_bad_opts(self):
                """ test pkg version with bad options """

                self.image_create(self.rurl)

                self.pkg("version -vq", use_img_root=False, exit=2)
                self.pkg("version foo", use_img_root=False, exit=2)
                self.pkg("version --", use_img_root=False, exit=2)


if __name__ == "__main__":
        unittest.main()
