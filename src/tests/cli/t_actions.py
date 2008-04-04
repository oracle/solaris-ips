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

import os
import unittest

class TestPkgActions(testutils.SingleDepotTestCase):

        basics0 = """
            open basics@1.0,5.11-0
            add file ./testdata/passwd mode=0644 owner=root group=sys path=etc/passwd preserve=true
            add file ./testdata/shadow mode=0400 owner=root group=sys path=etc/shadow preserve=true
            add file ./testdata/group mode=0644 owner=root group=sys path=etc/group preserve=true
            add file ./testdata/ftpusers mode=0644 owner=root group=sys path=etc/ftpd/ftpusers preserve=true
            add file ./testdata/empty mode=0644 owner=root group=sys path=etc/name_to_major preserve=true
            add file ./testdata/empty mode=0644 owner=root group=sys path=etc/driver_aliases preserve=true
            add dir mode=0755 owner=root group=bin path=/lib
            add dir mode=0755 owner=root group=sys path=/etc
            add dir mode=0755 owner=root group=sys path=/etc/ftpd
            add dir mode=0755 owner=root group=sys path=/var
            add dir mode=0755 owner=root group=sys path=/var/svc
            add dir mode=0755 owner=root group=sys path=/var/svc/manifest
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/local
            close """

	grouptest = """
            open grouptest@1.0,5.11-0
            add dir mode=0755 owner=root group=Kermit path=/usr/Kermit
            add file ./testdata/empty mode=0755 owner=root group=Kermit path=/usr/local/bin/do_group_nothing
            add group groupname=lp gid=8
            add group groupname=staff gid=10
            add group groupname=Kermit
            add depend fmri=pkg:/basics@1.0 type=require
            close """

	usertest10 = """
	    open usertest@1.0,5.11-0
            add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
            add file ./testdata/empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
            add depend fmri=pkg:/basics@1.0 type=require
            add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
            add depend fmri=pkg:/grouptest@1.0 type=require
            add depend fmri=pkg:/basics@1.0 type=require
            close """

	usertest11 = """
	    open usertest@1.1,5.11-0
            add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
            add file ./testdata/empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
            add depend fmri=pkg:/basics@1.0 type=require
            add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff group-list=root ftpuser=false
            add depend fmri=pkg:/grouptest@1.0 type=require
            add depend fmri=pkg:/basics@1.0 type=require
            close """

        def test_basics_0(self):
                """ Send basic infrastructure, install and uninstall """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.basics0)
                self.image_create(durl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install basics")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall basics")
                self.pkg("verify")

	def test_grouptest(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.basics0)
                self.pkgsend_bulk(durl, self.grouptest)
                self.image_create(durl)
                self.pkg("install basics")

		self.pkg("install grouptest")
                self.pkg("verify")
                self.pkg("uninstall grouptest")
                self.pkg("verify")

	def test_usertest(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.basics0)
                self.pkgsend_bulk(durl, self.grouptest)
                self.pkgsend_bulk(durl, self.usertest10)
                self.image_create(durl)
                self.pkg("install basics")

		self.pkg("install usertest")
                self.pkg("verify")
		self.pkg("contents -m usertest")

                self.pkgsend_bulk(durl, self.usertest11)
                self.pkg("refresh")
		self.pkg("install usertest")
                self.pkg("verify")
		self.pkg("contents -m usertest")

                self.pkg("uninstall usertest")
                self.pkg("verify")



if __name__ == "__main__":
        unittest.main()
