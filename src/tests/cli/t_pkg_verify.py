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

class TestPkgVerify(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_pkg_verify_bad_opts(self):
                """ test pkg verify with bad options """
			
		durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("verify -vq", exit=2)
                
        def test_bug_1463(self):
            """When multiple FMRIs are given to pkg verify,
            if any of them aren't installed it should fail."""
            pkg1 = """
                open foo@1.0,5.11-0
                close
            """
            durl = self.dc.get_depot_url()
            self.pkgsend_bulk(durl, pkg1)
            self.image_create(durl)
            self.pkg("install foo")
            self.pkg("verify foo nonexistent", exit=1)

if __name__ == "__main__":
        unittest.main()

