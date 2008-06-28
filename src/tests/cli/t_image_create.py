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

class TestImageCreate(testutils.SingleDepotTestCase):

        def test_basic(self):
                """ Create an image, verify it. """

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("verify")

        def test_766(self):
                """Bug 766: image-create without authority prefix specified."""

                durl = self.dc.get_depot_url()

                pkgsend_data = """
                open foo@0.0
                close
                """
                self.pkgsend_bulk(durl, pkgsend_data)

                self.assertRaises(testutils.UnexpectedExitCodeException,
                    self.image_create, durl, "")


class TestImageCreateNoDepot(testutils.pkg5TestCase):
        def test_bad_image_create(self):
                """ Create image from non-existent server """

		#
		# Currently port 4 is unassigned by IANA and we
		# Can just hope that it never gets assigned.
		# We choose localhost because, well, we think
		# it will be universally able to be looked up.
		#
                durl = "http://localhost:4"
		self.assertRaises(testutils.UnexpectedExitCodeException, \
		    self.image_create, durl)

        def test_765(self):
                """Bug 765: malformed authority URL."""

                durl = "bar=baz"
                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.image_create, durl)

        def test_763a(self):
                """Bug 763, traceback 1: no -a option given to image-create."""

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create foo")

        def test_763c(self):
                """Bug 763, traceback 3: -a given to image-create, but no
                authority specified."""

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -a foo")

        def test_bad_authority_options(self):
                """More tests that abuse the authority prefix and URL."""

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -a $%^8=http://test1")

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -a test1=http://$%^8")

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -a test1=http://test1:abcde")

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -a test1=ftp://test1")

if __name__ == "__main__":
        unittest.main()
