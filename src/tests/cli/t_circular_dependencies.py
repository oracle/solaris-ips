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

class TestCircularDependencies(testutils.SingleDepotTestCase):

        pkg10 = """
            open pkg1@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg2
            close
        """

        pkg20 = """
            open pkg2@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg3
            close
        """

        pkg30 = """
            open pkg3@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg1
            close
        """


        pkg11 = """
            open pkg1@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg2@1.1
            close
        """

        pkg21 = """
            open pkg2@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg3@1.1
            close
        """

        pkg31 = """
            open pkg3@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg1@1.1
            close
        """

        def test_unanchored_circular_dependencies(self):
                """ check to make sure we can install
                circular dependencies w/o versions
                """

                # Send 1.0 versions of packages.
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.pkg10)
                self.pkgsend_bulk(durl, self.pkg20)
                self.pkgsend_bulk(durl, self.pkg30)

                self.image_create(durl)
                self.pkg("install pkg1")
                self.pkg("list")
                self.pkg("verify -v")

        def test_anchored_circular_dependencies(self):
                """ check to make sure we can install
                circular dependencies w/ versions
                """

                # Send 1.0 versions of packages.
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.pkg11)
                self.pkgsend_bulk(durl, self.pkg21)
                self.pkgsend_bulk(durl, self.pkg31)

                self.image_create(durl)
                self.pkg("install pkg1")
                self.pkg("list")
                self.pkg("verify -v")

if __name__ == "__main__":
        unittest.main()
