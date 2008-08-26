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

import os
import unittest
import shutil
import copy

import pkg.depotcontroller as dc

import pkg.query_engine as query_engine
import pkg.portable as portable

class TestPkgSearchMulti(testutils.ManyDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.example_pkg10)

                self.image_create(durl1, prefix = "test1")
                self.pkg("set-authority -O " + durl2 + " test2")
                self.pkg("refresh")

        def test_bug_2955(self):
                """See http://defect.opensolaris.org/bz/show_bug.cgi?id=2955"""
                self.pkg("install example_pkg")
                self.pkg("rebuild-index")
                self.pkg("uninstall example_pkg")

if __name__ == "__main__":
        unittest.main()
