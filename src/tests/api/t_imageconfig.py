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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import os
import shutil
import sys
import tempfile
import pkg.client.imageconfig as imageconfig
import pkg.portable as portable


class TestImageConfig(pkg5unittest.Pkg5TestCase):

        misc_files = { imageconfig.CFG_FILE : """\
[policy]
Display-Copyrights: False

[property]
name = an image
                
[authority_sfbay.sun.com]
alias: zruty
prefix: sfbay.sun.com
origin: http://zruty.sfbay:10001/
mirrors:
ssl_key:
ssl_cert:
repo.collection_type: supplemental
repo.description: Lots of development packages here.
repo.legal_uris: ['http://zruty.sfbay:10001/legal.html', 'http://zruty.sfbay:10001/tos.html']
repo.name: zruty development repository
repo.refresh_seconds: 86400
repo.registered: True
repo.registration_uri: http://zruty.sfbay:10001/reg.html
repo.related_uris:
sort_policy: priority
""" }

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.ic = imageconfig.ImageConfig(os.path.join(self.test_root,
                    "cfg_cache"), self.test_root)

        def test_0_read(self):
                """Verify that read works and that values are read properly."""

                pub = self.ic.publishers["sfbay.sun.com"]
                self.assertEqual(pub.alias, "zruty")
                repo = pub.repository
                origin = repo.origins[0]
                self.assertEqual(origin.uri, "http://zruty.sfbay:10001/")
                self.assertEqual(origin.ssl_key, None)
                self.assertEqual(origin.ssl_cert, None)
                self.assertEqual(repo.collection_type, "supplemental")
                self.assertEqual(repo.description,
                    "Lots of development packages here.")
                self.assertEqual([u.uri for u in repo.legal_uris],
                    ["http://zruty.sfbay:10001/legal.html",
                    "http://zruty.sfbay:10001/tos.html"])
                self.assertEqual(repo.name, "zruty development repository")
                self.assertEqual(repo.refresh_seconds, 86400)
                self.assertEqual(repo.registered, True)
                self.assertEqual(repo.registration_uri, "http://zruty.sfbay:10001/reg.html")
                self.assertEqual(repo.related_uris, [])
                self.assertEqual(repo.sort_policy, "priority")
                # uuid should have been set even though it wasn't in the file
                self.assertNotEqual(pub.client_uuid, None)

        def test_1_reread(self):
                """Verify that the uuid determined during the first read is the
                same as the uuid in the second read."""
                self.ic = imageconfig.ImageConfig(os.path.join(self.test_root,
                    "cfg_cache"), self.test_root)
                pub = self.ic.publishers["sfbay.sun.com"]
                uuid = pub.client_uuid

                ic2 = imageconfig.ImageConfig(os.path.join(self.test_root,
                    "cfg_cache"), self.test_root)
                pub2 = ic2.publishers["sfbay.sun.com"]
                self.assertEqual(pub2.client_uuid, uuid)


if __name__ == "__main__":
        unittest.main()
