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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest
import unittest

try:
        import ldtp
except ImportError:
        raise ImportError, "SUNWldtp package not installed."

class TestPkgGuiStartBasics(pkg5unittest.SingleDepotTestCase):

        foo10 = """
            open sample_package@1.0,5.11-0
            add set name="description" value="Some package description"
            close """

        def testStartPackagemanager(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)

                # image_create destroys the previous image
                # so it's not needed to call self.image_destroy()
                self.image_create(durl)

                ldtp.launchapp("%s/usr/bin/packagemanager" % pkg5unittest.g_proto_area)
                ldtp.click('frmPackageManager', 'mnuQuit')

if __name__ == "__main__":
	unittest.main()
