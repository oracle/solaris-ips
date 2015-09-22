#!/usr/bin/python
# -*- coding: utf-8 -*-
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

#
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import os
import platform
import unittest

class TestPkgInitInstall(pkg5unittest.SingleDepotTestCase):
        persistent_setup = True

        core = """\
        open core-os@1.0
        add set name=pkg.fmri value=pkg://solaris/system/core-os@1.0
        add set name=pkg.summary value="Core Solaris"
        add set name=pkg.description value="Operating system core utilities, daemons, and configuration files."
        add dir  path=etc group=sys owner=root mode=0555
        add dir  path=etc/ftpd group=sys owner=root mode=0555
        add file path=etc/ftpd/ftpusers group=sys preserve=true owner=root mode=0444
        add link path=etc/ftpusers target=./ftpd/ftpusers
        add file path=etc/group group=sys preserve=true owner=root mode=0444
        add file path=etc/passwd group=sys preserve=true owner=root mode=0444
        add file path=etc/shadow group=sys mode=0400 preserve=true owner=root
        add group groupname=adm gid=4
        add group groupname=bin gid=2
        add group groupname=daemon gid=12
        add group groupname=dialout gid=13
        add group groupname=games gid=20
        add group groupname=lp gid=8
        add group groupname=mail gid=6
        add group groupname=noaccess gid=60002
        add group groupname=nobody gid=60001
        add group groupname=nogroup gid=65534
        add group groupname=other gid=1
        add group groupname=root gid=0
        add group groupname=staff gid=10
        add group groupname=sys gid=3
        add group groupname=sysadmin gid=14
        add group groupname=tty gid=7
        add group groupname=webservd gid=80
        add user username=adm ftpuser=false gcos-field=Admin group=adm home-dir=/var/adm lastchg=6445 login-shell=/bin/sh password=NP uid=4 group-list=lp group-list=sys group-list=tty
        add user username=bin ftpuser=false gcos-field="" group=bin group-list=sys home-dir=/ lastchg=6445 login-shell=/bin/sh password=NP uid=2
        add user username=daemon ftpuser=false gcos-field="" group=other home-dir=/ lastchg=6445 login-shell=/bin/sh password=NP uid=1 group-list=adm group-list=bin
        add user username=noaccess ftpuser=false gcos-field="No Access User" group=nogroup home-dir=/ lastchg=6445 login-shell=/bin/sh password=*LK* uid=60002
        add user username=nobody ftpuser=false gcos-field="NFS Anonymous Access User" group=nobody home-dir=/ login-shell=/bin/sh uid=60001
        add user username=nobody4 ftpuser=false gcos-field="SunOS 4.x NFS Anonymous Access User" group=nogroup home-dir=/ lastchg=6445 login-shell=/bin/sh password=*LK* uid=65534
        add user username=root ftpuser=false gcos-field=Super-User group=root home-dir=/root lastchg=6445 login-shell=/usr/bin/bash password="" uid=0 group-list=adm group-list=bin group-list=daemon group-list=lp group-list=mail group-list=other group-list=sys group-list=tty
        add user username=sys ftpuser=false gcos-field="" group=sys home-dir=/ lastchg=6445 login-shell=/bin/sh password=NP uid=3
        add user username=webservd ftpuser=false gcos-field="WebServer Reserved UID" group=webservd home-dir=/ login-shell=/bin/sh password=*LK* uid=80
        close
"""
        misc_files = { "etc/passwd":"", "etc/group":"", "etc/shadow":"", "etc/ftpd/ftpusers":"" }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def file_in_image(self, path):
                return open(os.path.join(self.get_img_path(), path))

        def file_is_sorted(self, path, column):
                # make sure the ':' separated file is sorted in ascending order
                # on the integer in the specified column
                previous = None
                for line in self.file_in_image(path):
                        if previous is None:
                                previous = int(line.split(":")[column])
                        else:
                                now = int(line.split(":")[column])
                                self.assert_(now >= previous,
                                    "{0} is not sorted by column {1}".format(
                                    path, column))

        def test_init_install(self):
                """test initial install of stripped down core OS"""

                plist = self.pkgsend_bulk(self.rurl, self.core)
                self.image_create(self.rurl)

                self.pkg("install core-os")
                self.pkg("verify")

                # verify that /etc/passwd and /etc/group are in
                # ascending [UG]ID order

                self.file_is_sorted("etc/passwd", 2)
                self.file_is_sorted("etc/group", 2)
