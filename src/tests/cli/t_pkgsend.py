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

class TestPkgSend(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_pkgsend_abandon(self):
                """ Send package shouldnotexist@1.0, then abandon the
                    transaction """
                durl = self.dc.get_depot_url()

                self.pkgsend(durl, "open shouldnotexist@1.0,5.11-0")
                self.pkgsend(durl, "add dir mode=0755 owner=root group=bin path=/bin")
                self.pkgsend(durl, "close -A")

                self.image_create(durl)
                self.pkg("refresh")

                self.pkg("list -a shouldnotexist", exit = 1)

        def test_bug_89(self):
                """ Client must correctly handle errors on bad pkgsends
                    See http://defect.opensolaris.org/bz/show_bug.cgi?id=89 """

                durl = self.dc.get_depot_url()
                os.environ["PKG_TRANS_ID"] = "foobarbaz"
                
                self.pkgsend(durl,
                    "add file /bin/ls path=/bin/ls", exit=1)



if __name__ == "__main__":
        unittest.main()
