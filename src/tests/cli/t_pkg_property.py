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
import re
import shutil
import difflib

class TestPkgInfoBasics(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_pkg_properties(self):
                """pkg: set, unset, and display properties """

                durl = self.dc.get_depot_url()
                self.image_create(durl)

		self.pkg("set-property -@", exit=2)
                self.pkg("get-property -@", exit=2)
                self.pkg("property -@", exit=2)

                self.pkg("set-property title sample")
                self.pkg('set-property description "more than one word"')
                self.pkg("property")
                self.pkg("property | grep title")
                self.pkg("property | grep description")
                self.pkg("property | grep 'sample'")
                self.pkg("property | grep 'more than one word'")
                self.pkg("unset-property description")
                self.pkg("property -H")
                self.pkg("property title")
                self.pkg("property -H title")
                self.pkg("property description", exit=1)
                self.pkg("unset-property description", exit=1)
                self.pkg("unset-property", exit=2)

        def test_missing_permssions(self):
                """Bug 2393"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("property")
                self.pkg("set-property require-optional True", su_wrap="noaccess", exit=1)
                self.pkg("set-property require-optional True")
                self.pkg("unset-property require-optional", su_wrap="noaccess", exit=1)
                self.pkg("unset-property require-optional")

if __name__ == "__main__":
        unittest.main()
