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

class TestDependencies(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        pkg10 = """
            open pkg1@1.0,5.11-0
            add depend type=optional fmri=pkg:/pkg2
            close
        """

        pkg20 = """
            open pkg2@1.0,5.11-0
            close
        """

        pkg11 = """
            open pkg1@1.1,5.11-0
            add depend type=optional fmri=pkg:/pkg2@1.1
            close
        """

        pkg21 = """
            open pkg2@1.1,5.11-0
            close
        """

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.pkg10)
                self.pkgsend_bulk(durl, self.pkg20)
                self.pkgsend_bulk(durl, self.pkg11)
                self.pkgsend_bulk(durl, self.pkg21)

        def test_optional_dependencies(self):
                """ check to make sure that optional dependencies are enforced
                """

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("install pkg1@1.0")

                # pkg2 is optional, it should not have been installed
                self.pkg("list pkg2", exit=1)

                self.pkg("install pkg2@1.0")

                # this should install pkg1 and upgrade pkg2 to pkg2@1.1
                self.pkg("install pkg1")
                self.pkg("list pkg2@1.1")

                self.pkg("uninstall pkg2")
                self.pkg("list pkg2", exit=1)
                # this should install pkg2@1.1 because of the optional 
                # dependency in pkg1
                self.pkg("install pkg2@1.0")
                self.pkg("list pkg2@1.1")

        def test_require_optional(self):
                """ check that the require optional policy is working
                """

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("set-property require-optional true")
                self.pkg("install pkg1")
                # the optional dependency should be installed because of the
                # policy setting
                self.pkg("list pkg2@1.1")


if __name__ == "__main__":
        unittest.main()
