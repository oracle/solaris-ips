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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import unittest
import os

class TestCommandLine(testutils.SingleDepotTestCase):

        def test_pkg_bogus_opts(self):
                """ pkg bogus option checks """

                # create a image to avoid non-existant image messages
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("-@", exit=2)
                self.pkg("status -@", exit=2)
                self.pkg("list -@", exit=2)
                self.pkg("image-update -@", exit=2)
                self.pkg("image-create -@", exit=2)
                self.pkg("image-create --bozo", exit=2)
                self.pkg("install -@ foo", exit=2)
                self.pkg("uninstall -@ foo", exit=2)

        def test_pkg_missing_args(self):
                """ pkg: Lack of needed arguments should yield complaint """
                # create a image to avoid non-existant image messages
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("-s status", exit=2)
                self.pkg("-R status", exit=2)
                self.pkg("list -o", exit=2)
                self.pkg("list -s", exit=2)
                self.pkg("list -t", exit=2)


        def test_pkgsend_bogus_opts(self):
                """ pkgsend bogus option checks """
                durl = "bogus"
                self.pkgsend(durl, "-@ open foo@1.0,5.11-0", exit=2)
                self.pkgsend(durl, "close -@", exit=2)




if __name__ == "__main__":
        unittest.main()
