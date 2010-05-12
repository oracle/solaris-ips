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

# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest


class TestROption(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            close """

	def test_bad_cli_options(self):

		self.image_create(self.rurl)
		self.pkg("-@", exit=2)
		self.pkg("-s status", exit=2)
                self.pkg("-R status", exit=2)

        def test_1(self):

                self.pkgsend_bulk(self.rurl, self.foo10)
                self.image_create(self.rurl)

                imgpath = self.img_path
                badpath = "/this/dir/should/not/ever/exist/foo/bar/afsddfas"

                self.pkg("-R %s list" % badpath, exit=1)
                self.pkg("-R %s list" % imgpath, exit=1)

                self.pkg("-R %s install foo" % badpath, exit=1)
                self.pkg("-R %s install foo" % imgpath)

                self.pkg("-R %s list" % badpath, exit=1)
                self.pkg("-R %s list" % imgpath)

                self.pkgsend_bulk(self.rurl, self.foo10)
                self.pkg("-R %s refresh" % imgpath)

                self.pkg("-R %s image-update" % badpath, exit=1)
                self.pkg("-R %s image-update --be-name NEWBENAME" % imgpath, exit=1)
                self.pkg("-R %s image-update" % imgpath)

                self.pkg("-R %s uninstall foo" % badpath, exit=1)
                self.pkg("-R %s install foo" % imgpath, exit=4)

                self.pkg("-R %s info foo" % badpath, exit=1)
                self.pkg("-R %s info foo" % imgpath)


if __name__ == "__main__":
        unittest.main()
