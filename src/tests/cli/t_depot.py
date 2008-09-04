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

import pkg.depotcontroller as dc

class TestDepot(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        quux10 = """
            open quux@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        misc_files = [ "/tmp/libc.so.1", "/tmp/cat" ]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close
                        self.debug("wrote %s" % p)

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        def test_depot_ping(self):
                """ Ping the depot several times """

                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())
                self.assert_(self.dc.is_alive())

        def testStartStop(self):
                """ Start and stop the depot several times """
                self.dc.stop()
                for i in range(0, 5):
                        self.dc.start()
                        self.assert_(self.dc.is_alive())
                        self.dc.stop()
                        self.assert_(not self.dc.is_alive())

                self.dc.start()

        def test_bug_1876(self):
                """ Send package quux@1.0 an action at a time, restarting the
                    depot server after each one is sent, to ensure that
                    transactions work across depot restart. Then verify that
                    the package was successfully added by performing some
                    basic operations. """

                durl = self.dc.get_depot_url()

                for line in self.quux10.split("\n"):
                        line = line.strip()
                        if line == "":
                                continue

                        try:
                                self.pkgsend(durl, line, exit = 0)
                        except:
                                self.pkgsend(durl, "close -A", exit = 0)
                                raise

                        if not line == "close":
                                self.restart_depots()

                self.image_create(durl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install quux")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall quux")
                self.pkg("verify")

if __name__ == "__main__":
        unittest.main()
