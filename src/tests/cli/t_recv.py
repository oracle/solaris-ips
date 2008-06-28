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

#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import shutil
import tempfile
import unittest

class TestPkgRecv(testutils.ManyDepotTestCase):

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file /tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze target=/lib/libc.so.1
            add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file /tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add depend fmri=pkg:/amber@1.0 type=require
            add license /tmp/copyright2 license=copyright
            close
        """

        bronze20 = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file /tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file /tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file /tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license /tmp/copyright3 license=copyright
            add file /tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close 
        """

        misc_files = [ "/tmp/bronzeA1",  "/tmp/bronzeA2",
                    "/tmp/bronze1", "/tmp/bronze2",
                    "/tmp/copyright2", "/tmp/copyright3",
                    "/tmp/libc.so.1", "/tmp/sh"]

        def setUp(self):
                """ Start two depots.
                    depot 1 gets foo and moo, depot 2 gets foo and bar
                    depot1 is mapped to authority test1 (preferred)
                    depot2 is mapped to authority test2 """

                testutils.ManyDepotTestCase.setUp(self, 2)

                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)

                self.durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(self.durl1, self.bronze10)
                self.pkgsend_bulk(self.durl1, self.bronze20)

                self.durl2 = self.dcs[2].get_depot_url()
                self.tempdir = tempfile.mkdtemp()


        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)
                shutil.rmtree(self.tempdir)

        def test_recv_send(self):
                rc, output = self.pkgrecv(self.durl1,
                    "-n | grep bronze@2.0", out = True)

                # Pull the pkg name out of the output from the last cmd
                outwords = output.split()

                # recv the pkg
                recvcmd = "-d %s %s" % (self.tempdir, outwords[0])
                self.pkgrecv(self.durl1, recvcmd)

                # now send it to another depot
                self.pkgsend(self.durl2, "open foo@1.0-1")

                basedir = os.path.join(self.tempdir, "bronze")
                manifest = os.path.join(basedir, "manifest")

                cmd = "include -d %s %s" % (basedir, manifest)

                self.pkgsend(self.durl2, cmd)
                self.pkgsend(self.durl2, "close")

        def test_bad_opts(self):
                self.pkgrecv("", "-n", exit = 2)
                self.pkgrecv(self.durl1, "-!", exit = 2)
                self.pkgrecv(self.durl1, "-p foo", exit = 2)
                self.pkgrecv(self.durl1, "-d %s gold@1.0-1" % self.tempdir,
                    exit = 1)


if __name__ == "__main__":
        unittest.main()

