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

import httplib
import unittest
import os
import pkg.misc as misc
import shutil
import urllib
import urllib2

import pkg.depotcontroller as dc

class TestPkgDepot(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        quux10 = """
            open quux@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        info10 = """
            open info@1.0,5.11-0
            close """

        system10 = """
            open system/libc@1.0,5.11-0
            add set name="description" value="Package to test package names with slashes"
            add dir path=tmp/foo mode=0755 owner=root group=bin
            add depend type=require fmri=pkg:/SUNWcsl
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

        def test_bad_fmris(self):
                durl = self.dc.get_depot_url()
                self.pkgsend(durl, "open foo@", exit=1)
                self.pkgsend(durl, "open foo@x.y", exit=1)
                self.pkgsend(durl, "open foo@1.0,-2.0", exit=1)

        def test_bug_3365(self):
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()

                dir_file = os.path.join(depotpath, "search.dir")
                pag_file = os.path.join(depotpath, "search.pag")
                
                self.assert_(not os.path.exists(dir_file))
                self.assert_(not os.path.exists(pag_file))

                f = open(dir_file, "w")
                f.close()
                f = open(pag_file, "w")
                f.close()
                self.assert_(os.path.exists(dir_file))
                self.assert_(os.path.exists(pag_file))

                self.dc.stop()
                self.dc.start()
                self.pkgsend_bulk(durl, self.quux10)
                self.assert_(not os.path.exists(dir_file))
                self.assert_(not os.path.exists(pag_file))

        def test_bug_4489(self):
                """Publish a package and then verify that the depot /info
                operation doesn't fail."""
                depot_url = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(depot_url, self.info10)
                misc.versioned_urlopen(depot_url, "info", [0], plist[0])

        def test_bug_5366(self):
                """Publish a package with slashes in the name, and then verify
                that the depot manifest and info operations work regardless of
                the encoding."""
                depot_url = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(depot_url, self.system10)
                # First, try it un-encoded.
                misc.versioned_urlopen(depot_url, "info", [0], plist[0])
                misc.versioned_urlopen(depot_url, "manifest", [0], plist[0])
                # Second, try it encoded.
                misc.versioned_urlopen(depot_url, "info", [0],
                    urllib.quote(plist[0]))
                misc.versioned_urlopen(depot_url, "manifest", [0],
                    urllib.quote(plist[0]))

        def test_face_root(self):
                """Verify that files outside of the package content web root
                cannot be accessed, and that files inside can be."""
                depot_url = self.dc.get_depot_url()
                # Since /usr/share/lib/pkg/web/ is the content web root,
                # any attempts to go outside that directory should fail
                # with a 404 error.
                try:
                        urllib2.urlopen("%s/../../../../bin/pkg" % depot_url)
                except urllib2.HTTPError, e:
                        if e.code != httplib.NOT_FOUND:
                                raise

                f = urllib2.urlopen("%s/robots.txt" % depot_url)
                self.assert_(len(f.read()))
                f.close()

class TestDepotController(testutils.CliTestCase):

        def setUp(self):
                testutils.CliTestCase.setUp(self)

                self.__dc = dc.DepotController()
                self.__pid = os.getpid()
		self.__dc.set_depotd_path(testutils.g_proto_area + \
                    "/usr/lib/pkg.depotd")
		self.__dc.set_depotd_content_root(testutils.g_proto_area + \
                    "/usr/share/lib/pkg")

                depotpath = os.path.join(self.get_test_prefix(), "depot")
                logpath = os.path.join(self.get_test_prefix(), self.id())

                try:
                        os.makedirs(depotpath, 0755)
                except:
                        pass

                self.__dc.set_repodir(depotpath)
                self.__dc.set_logpath(logpath)

        def tearDown(self):
                testutils.CliTestCase.tearDown(self)

                self.__dc.kill()
                shutil.rmtree(self.__dc.get_repodir())
                os.remove(self.__dc.get_logpath())


        def testStartStop(self):
                self.__dc.set_port(12000)
                for i in range(0, 5):
                        self.__dc.start()
                        self.assert_(self.__dc.is_alive())
                        self.__dc.stop()
                        self.assert_(not self.__dc.is_alive())

        def testBadArgs(self):
                self.__dc.set_readonly()
                self.__dc.set_rebuild()
                self.__dc.set_norefresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_readonly()
                self.__dc.set_norebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_readonly()
                self.__dc.set_rebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_readwrite()
                self.__dc.set_rebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_mirror()
                self.__dc.set_rebuild()
                self.__dc.set_norefresh_index()

                self.assert_(self.__dc.start_expected_fail())

                self.__dc.set_mirror()
                self.__dc.set_norebuild()
                self.__dc.set_refresh_index()

                self.assert_(self.__dc.start_expected_fail())

if __name__ == "__main__":
        unittest.main()
