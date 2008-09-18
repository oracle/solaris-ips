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


class TestRename(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_rename1(self):
		""" Test some ways in which we expect rename to fail """
                durl = self.dc.get_depot_url()

		# Not in catalog
                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0",
		    exit=1)

                self.pkgsend(durl, "open foo@1.0,5.11-0")
                self.pkgsend(durl, "close")

		# Dest. not in catalog
                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0",
		    exit=1)

                self.pkgsend(durl, "open bar@1.0,5.11-0")
                self.pkgsend(durl, "close")

		# Build string missing in source, then in dest, then both
                self.pkgsend(durl, "rename foo@1.1 bar@1.0,5.11-0", exit=1)
                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0", exit=1)
                self.pkgsend(durl, "rename foo@1.1 bar@1.0", exit=1)

		# Source must not already be in catalog.
                self.pkgsend(durl, "rename foo@1.0,5.11-0 bar@1.0,5.11-0",
		    exit=1)

	def test_rename2(self):
		""" Basic rename """
                durl = self.dc.get_depot_url()

                self.pkgsend(durl, "open foo@1.0,5.11-0")
                self.pkgsend(durl, "close")

		self.image_create(durl)
		self.pkg("install foo")
		self.pkg("verify")

                self.pkgsend(durl, "open bar@1.0,5.11-0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0")

		self.pkg("install bar")
		self.pkg("verify")

		self.pkg("list foo", exit=1)
		self.pkg("list bar", exit=0)

	def test_rename3(self):
		""" Rename to pkg previously opened without a build string """
                durl = self.dc.get_depot_url()

                self.pkgsend(durl, "open foo@1.0,5.11-0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "open bar@1.0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "rename foo@1.1,5.11-0 bar@1.0,5.11-0", exit=1)


        def test_rename4(self):
                """ Rename package and verify dependencies.

		    Send package rar@1.0, dependent on moo@1.1.
		    Rename moo to zoo.
		    Install zoo and then rar.  Verify that zoo satisfied
		    dependency for moo.
		"""

                # Send 1.0 versions of packages.
                durl = self.dc.get_depot_url()
		self.image_create(durl)

                self.pkgsend(durl, "open moo@1.1,5.11-0")
                self.pkgsend(durl, "close")

                self.pkgsend(durl, "open zoo@1.0,5.11-0")
                self.pkgsend(durl, "close")
                self.pkgsend(durl, "rename moo@1.2,5.11-0 zoo@1.0,5.11-0")

                self.pkgsend(durl, "open rar@1.0")
                self.pkgsend(durl, "add depend type=require fmri=pkg:/moo@1.1")
                self.pkgsend(durl, "close")

                self.pkg("refresh")
                self.pkg("list -aH")
		self.pkg("install -v zoo")
		self.pkg("install -v rar")

		# Check that zoo and rar were installed
                self.pkg("list zoo")
                self.pkg("list rar")

		# Check that moo was not installed
                self.pkg("list moo", exit=1)

                self.pkg("verify")

		self.pkg("uninstall rar zoo")
                self.pkg("verify")


if __name__ == "__main__":
        unittest.main()
