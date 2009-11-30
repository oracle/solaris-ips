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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import time
import sys
import unittest
from stat import *
import pkg.fmri as fmri
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress

API_VERSION = 24
PKG_CLIENT_NAME = "pkg"

class TestPkgIntent(testutils.SingleDepotTestCase):

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1 timestamp="20080731T024051Z"
            close """
        foo11_timestamp = 1217472051

        foo12 = """
            open foo@1.2,5.11-0
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        bar11 = """
            open bar@1.1,5.11-0
            add depend type=require fmri=pkg:/foo@1.2
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        bar12 = """
            open bar@1.2,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat 
            close """

        baz10 = """
            open baz@1.0,5.11-0
            add depend type=require fmri=pkg:/bar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/baz mode=0555 owner=root group=bin path=/bin/baz
            close """

        misc_files = [ "/tmp/libc.so.1", "/tmp/cat", "/tmp/baz" ]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self,
                    debug_features=["headers"])
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

        def get_intent_entries(self):
                """Scan logpath looking for request header log entries for
                X-IPkg-Intent.  Returns a list of dicts each representing
                an intent entry."""

                hdr = "X-IPKG-INTENT:"

                entries = []
                for i in sorted(self.dcs.keys()):
                        dc = self.dcs[i]
                        logpath = dc.get_logpath()
                        self.debug("check for intent entries in %s" % logpath)
                        logfile = open(logpath, "r")
                        for line in logfile.readlines():
                                spos = line.find(hdr)
                                if spos > -1:
                                        spos += len(hdr)
                                        l = line[spos:].strip()
                                        l = l.strip("()")
                                        d = {}
                                        for e in l.split(";"):
                                                k, v = e.split("=")
                                                d[k] = v
                                        if d:
                                                entries.append(d)
                return entries

        def intent_entry_exists(self, entries, expected):
                """Returns a boolean value indicating whether the expected
                intent entry was found."""
                for entry in entries:
                        if entry == expected:
                                return True
                self.debug("Intent log entries:\n%s" % (
                    "\n".join(str(e) for e in entries)))
                self.debug("Unable to match:\n%s" % expected)
                return False

        @staticmethod
        def __do_install(api_obj, fmris, noexecute=False):
                api_obj.reset()
                api_obj.plan_install(fmris, noexecute=noexecute)
                if not noexecute:
                        api_obj.prepare()
                        api_obj.execute_plan()

        @staticmethod
        def __do_uninstall(api_obj, fmris, recursive_removal=False,
            noexecute=False):
                api_obj.reset()
                api_obj.plan_uninstall(fmris, recursive_removal,
                    noexecute=noexecute)
                if not noexecute:
                        api_obj.prepare()
                        api_obj.execute_plan()

        def test_0_info(self):
                """Verify that informational operations do not send
                intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                api_obj.info(plist, False, frozenset([api.PackageInfo.IDENTITY,
                    api.PackageInfo.STATE, api.PackageInfo.PREF_PUBLISHER]))

                entries = self.get_intent_entries()
                self.assert_(entries == [])
                
                api_obj.info(plist, False,
                    frozenset([api.PackageInfo.DEPENDENCIES]))

                entries = self.get_intent_entries()
                # Verify that no entries are present
                self.assert_(not entries)


        def test_1_install_uninstall(self):
                """Verify that the install and uninstall of a single package
                sends the expected intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                # Test install.
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["foo"], noexecute=True)
                entries = self.get_intent_entries()
                # no data should be there
                self.assert_(not entries)

                self.__do_install(api_obj, ["foo"])

                entries = self.get_intent_entries()

                foo = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True)


                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "new_fmri" : foo,
                    "reference": "foo"
                }))

                # Test uninstall.
                self.__do_uninstall(api_obj, ["*"])

                # Verify that processing entries are present for uninstall.
                entries = self.get_intent_entries()
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "old_fmri" :  foo,
                    "reference": "*"
                }))

        def test_2_upgrade(self):
                """Verify the the install of a single package, and then an
                upgrade (install of newer version) of that package sends the
                expected intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10 + self.foo11)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                foo10 = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True)
                foo11 = fmri.PkgFmri(plist[1]).get_fmri(anarchy=True)

                # Test install.
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["foo@1.0"])
                self.__do_install(api_obj, ["foo@1.1"])

                # Test uninstall.
                self.__do_uninstall(api_obj, ["foo"])

                entries = self.get_intent_entries()
                # Verify that evaluation and processing entries are present
                # for install.
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "new_fmri" : foo10,
                    "reference": "foo@1.0"
                }))

                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "new_fmri" : foo11,
                    "old_fmri" : foo10,
                    "reference": "foo@1.1"
                }))
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "old_fmri" :  foo11,
                    "reference": "foo"
                }))

        def test_3_dependencies(self):
                """Verify that an install or uninstall of a single package with
                a single dependency sends the expected intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10 + self.bar10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["bar@1.0"])
                self.__do_uninstall(api_obj, ["bar", "foo"])


                foo = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True)
                bar = fmri.PkgFmri(plist[1]).get_fmri(anarchy=True)

                # Only testing for process; no need to re-test for evaluate.
                entries = self.get_intent_entries()
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "new_fmri" : bar,
                    "reference": "bar@1.0"
                }))

                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "new_fmri" : foo,
                }))

        def test_4_image_upgrade(self):
                """Verify that the correct intent information is sent during an
                image upgrade."""

                fmri_list = ["foo10", "foo11", "bar10", "foo12", "bar11"]
                
                plist = []
                durl = self.dc.get_depot_url()
                plist.extend(self.pkgsend_bulk(durl, self.foo10 + self.foo11 + \
                    self.bar10))


                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["bar@1.0"])

                plist.extend(self.pkgsend_bulk(durl, self.foo12 + self.bar11))

                def print_fmri(a):
                        return fmri.PkgFmri(a).get_fmri(anarchy=True)

                fmris = dict(zip(fmri_list, [print_fmri(p) for p in plist]))

                api_obj.refresh(immediate=True)

                api_obj.reset()
                api_obj.plan_update_all(sys.argv[0])
                api_obj.prepare()
                api_obj.execute_plan()

                # uninstall foo & bar
                self.__do_uninstall(api_obj, ["foo"], True)
                                       
                entries = self.get_intent_entries()
                # Verify that foo11 was installed when upgrading to foo12.
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "image-update",
                    "new_fmri" : fmris["foo12"],
                    "old_fmri" : fmris["foo11"]
                }))

                # Verify that bar10 was installed when upgrading to bar11.
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "image-update",
                    "new_fmri" : fmris["bar11"],
                    "old_fmri" : fmris["bar10"]
                }))
                # Verify that bar was uninstalled along w/ foo
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "old_fmri" : fmris["bar11"]
                }))

                # Verify that bar was uninstalled along w/ foo
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "old_fmri" : fmris["foo12"],
                    "reference": "foo"
                }))

if __name__ == "__main__":
        unittest.main()
