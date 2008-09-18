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
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        ftpusers_data = \
"""# ident      "@(#)ftpusers   1.6     06/11/21 SMI"
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
 
        testdata_dir = None

        pkg_name_valid_chars = {
            "never": " `~!@#$%^&*()=[{]}\\|;:\",<>?",
            "always": "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "after-first": "_/-.+",
            "at-end": "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-.+",
        }

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

                self.ugidtest = """
                    open ugidtest@1.0,5.11-0
                    add user username=dummy group=root
                    add group groupname=dummy
                    close """

                self.silver10 = """
                    open silver@1.0,5.11-0
                    add file """ + self.testdata_dir + """/empty mode=0755 owner=root group=root path=/usr/local/bin/silver
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """
                self.silver20 = """
                    open silver@2.0,5.11-0
                    add file """ + self.testdata_dir + """/empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/silver
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
                    add depend fmri=pkg:/basics@1.0 type=require
                    add depend fmri=pkg:/grouptest@1.0 type=require
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
                if self.testdata_dir:
                        shutil.rmtree(self.testdata_dir)
        
        def test_basics_0(self):
                """Send basic infrastructure, install and uninstall."""

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
                self.pkg("install usertest")
                self.pkg("verify")
                self.pkg("contents -m usertest")

                self.pkg("uninstall usertest")
                self.pkg("verify")

        def test_minugid(self):
                """Ensure that an unspecified uid/gid results in the first
                unused."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.ugidtest)
                self.image_create(durl)

                os.mkdir(os.path.join(self.get_img_path(), "etc"))
                os.mkdir(os.path.join(self.get_img_path(), "etc/ftpd"))
                for f in self.misc_files:
                        dir = "etc"
                        if f == "ftpusers":
                                dir = "etc/ftpd"
                        filename = os.path.join(self.get_img_path(), dir, f)
                        file_handle = open(filename, 'wb')
                        exec("%s_path = \"%s\"" % (f, filename))
                        try:
                                file_handle.write(eval("self.%s_data" % f))
                        finally:
                                file_handle.close()

                self.pkg("install ugidtest")
                passwd_file = file(passwd_path)
                for line in passwd_file:
                        if line.startswith("dummy"):
                                self.assert_(line.startswith("dummy:x:5:"))
                passwd_file.close()
                group_file = file(group_path)
                for line in group_file:
                        if line.startswith("dummy"):
                                self.assert_(line.startswith("dummy::5:"))
                group_file.close()

        def test_upgrade_with_user(self):
                """Ensure that we can add a user and change file ownership to
                that user in the same delta (mysql tripped over this early on
                in IPS development)."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.basics0)
                self.pkgsend_bulk(durl, self.silver10)
                self.pkgsend_bulk(durl, self.silver20)
                self.pkgsend_bulk(durl, self.grouptest)
                self.image_create(durl)
                self.pkg("install silver@1.0")
                self.pkg("list silver@1.0")
                self.pkg("verify -v")
                self.pkg("install silver@2.0")
                self.pkg("verify -v")

        def test_invalid_open(self):
                """Send a invalid package definition (invalid fmri); expect
                failure."""

                durl = self.dc.get_depot_url()

                for char in self.pkg_name_valid_chars["never"]:
                        invalid_name = "invalid%spkg@1.0,5.11-0" % char
                        self.pkgsend(durl, "open '%s'" % invalid_name, exit=1)

                for char in self.pkg_name_valid_chars["after-first"]:
                        invalid_name = "%sinvalidpkg@1.0,5.11-0" % char
                        if char == "-":
                                cmd = "open -- '%s'" % invalid_name
                        else:
                                cmd = "open '%s'" % invalid_name
                        self.pkgsend(durl, cmd, exit=1)

                        invalid_name = "invalid/%spkg@1.0,5.11-0" % char
                        cmd = "open '%s'" % invalid_name
                        self.pkgsend(durl, cmd, exit=1)

        def test_valid_open(self):
                """Send a invalid package definition (valid fmri); expect
                success."""

                durl = self.dc.get_depot_url()
                for char in self.pkg_name_valid_chars["always"]:
                        valid_name = "%svalid%s/%spkg%s@1.0,5.11-0" % (char,
                            char, char, char)
                        self.pkgsend(durl, "open '%s'" % valid_name)
                        self.pkgsend(durl, "close -A")

                for char in self.pkg_name_valid_chars["after-first"]:
                        valid_name = "v%salid%spkg@1.0,5.11-0" % (char, char)
                        self.pkgsend(durl, "open '%s'" % valid_name)
                        self.pkgsend(durl, "close -A")

                for char in self.pkg_name_valid_chars["at-end"]:
                        valid_name = "validpkg%s@1.0,5.11-0" % char
                        self.pkgsend(durl, "open '%s'" % valid_name)
                        self.pkgsend(durl, "close -A")


if __name__ == "__main__":
        unittest.main()
