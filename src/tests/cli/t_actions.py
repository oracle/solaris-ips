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

class TestPkgActions(testutils.SingleDepotTestCase):

        ftpusers_data = \
"""# ident	"@(#)ftpusers	1.6	06/11/21 SMI"
#
# List of users denied access to the FTP server, see ftpusers(4).
#
root
bin
sys
adm
"""
        group_data = \
"""root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
"""
        passwd_data = \
"""root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
"""
        shadow_data = \
"""root:9EIfTNBp9elws:13817::::::
daemon:NP:6445::::::
bin:NP:6445::::::
sys:NP:6445::::::
adm:NP:6445::::::
"""

	empty_data = ""
        
        misc_files = [ "empty", "ftpusers", "group", "passwd", "shadow" ]
        
        def setUp(self):

                testutils.SingleDepotTestCase.setUp(self)
                tp = self.get_test_prefix()
                self.testdata_dir = os.path.join(tp, "testdata")
                os.mkdir(self.testdata_dir)

                self.basics0 = """
                    open basics@1.0,5.11-0
                    add file """ + self.testdata_dir + """/passwd mode=0644 owner=root group=sys path=etc/passwd preserve=true
                    add file """ + self.testdata_dir + """/shadow mode=0400 owner=root group=sys path=etc/shadow preserve=true
                    add file """ + self.testdata_dir + """/group mode=0644 owner=root group=sys path=etc/group preserve=true
                    add file """ + self.testdata_dir + """/ftpusers mode=0644 owner=root group=sys path=etc/ftpd/ftpusers preserve=true
                    add file """ + self.testdata_dir + """/empty mode=0644 owner=root group=sys path=etc/name_to_major preserve=true
                    add file """ + self.testdata_dir + """/empty mode=0644 owner=root group=sys path=etc/driver_aliases preserve=true
                    add dir mode=0755 owner=root group=bin path=/lib
                    add dir mode=0755 owner=root group=sys path=/etc
                    add dir mode=0755 owner=root group=sys path=/etc/ftpd
                    add dir mode=0755 owner=root group=sys path=/var
                    add dir mode=0755 owner=root group=sys path=/var/svc
                    add dir mode=0755 owner=root group=sys path=/var/svc/manifest
                    add dir mode=0755 owner=root group=bin path=/usr
                    add dir mode=0755 owner=root group=bin path=/usr/local
                    close """

                self.grouptest = """
                    open grouptest@1.0,5.11-0
                    add dir mode=0755 owner=root group=Kermit path=/usr/Kermit
                    add file """ + self.testdata_dir + """/empty mode=0755 owner=root group=Kermit path=/usr/local/bin/do_group_nothing
                    add group groupname=lp gid=8
                    add group groupname=staff gid=10
                    add group groupname=Kermit
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.usertest10 = """
                    open usertest@1.0,5.11-0
                    add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
                    add file """ + self.testdata_dir + """/empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
                    add depend fmri=pkg:/basics@1.0 type=require
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.usertest11 = """
                    open usertest@1.1,5.11-0
                    add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
                    add file """ + self.testdata_dir + """/empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
                    add depend fmri=pkg:/basics@1.0 type=require
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff group-list=root ftpuser=false
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """
        
                for f in self.misc_files:
                        filename = os.path.join(self.testdata_dir, f)
                        file_handle = open(filename, 'wb')
                        try:
				file_handle.write(eval("self.%s_data" % f))
                        finally:
                                file_handle.close()

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                shutil.rmtree(self.testdata_dir)
        
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
