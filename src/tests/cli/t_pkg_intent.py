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

API_VERSION = 21
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
        def __do_install(api_obj, fmris, filters=None, noexecute=False):
                if not filters:
                        filters = []
                api_obj.reset()
                api_obj.plan_install(fmris, filters, noexecute=noexecute)
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
                """Verify that informational operations send the expected
                intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    frozenset([api.PackageInfo.LICENSES,
                    api.PackageInfo.SIZE]) - \
                    (api.PackageInfo.ACTION_OPTIONS - \
                    frozenset([api.PackageInfo.DEPENDENCIES]))

                api_obj.info(plist, False, info_needed)

                entries = self.get_intent_entries()
                self.assertEqual(entries, [])

                api_obj.info(plist, False,
                    info_needed | api.PackageInfo.ACTION_OPTIONS)

                entries = self.get_intent_entries()
                # Verify that evaluation and processing entries are present
                # for info.  This will only happen if the client actually
                # has to contact the repository to get information not found
                # in the catalog.
                target = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "info",
                    "reason": "info",
                    "initial_target": target,
                }))

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
                self.__do_install(api_obj, ["foo"])

                # Test uninstall.
                self.__do_uninstall(api_obj, ["foo"], noexecute=True)
                self.__do_uninstall(api_obj, ["foo"])

                entries = self.get_intent_entries()
                # Verify that entries are present for install.
                target = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target,
                }))

                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target,
                }))

                # Verify that evaluation entries are not present for uninstall.
                # Image operations that are for evaluation only and do not
                # require retrieving manifest information will not send any
                # intent information for efficiency.
                target_ver = str(fmri.PkgFmri(target).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "prior_version": target_ver,
                    "reason": "evaluate",
                    "initial_target": target,
                }) == False)

                # Verify that processing entries are present for uninstall.
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "prior_version": target_ver,
                    "reason": "process",
                    "initial_target": target,
                }))

        def test_2_upgrade(self):
                """Verify the the install of a single package, and then an
                upgrade (install of newer version) of that package sends the
                expected intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10 + self.foo11)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                # Test install.
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["foo@1.0"], noexecute=True)
                self.__do_install(api_obj, ["foo@1.0"])
                self.__do_install(api_obj, ["foo@1.1"], noexecute=True)
                self.__do_install(api_obj, ["foo@1.1"])

                # Test uninstall.
                self.__do_uninstall(api_obj, ["foo"], noexecute=True)
                self.__do_uninstall(api_obj, ["foo"])

                entries = self.get_intent_entries()
                # Verify entries are present for install.
                target0 = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target0,
                }))

                target1 = fmri.PkgFmri(plist[1]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target1,
                }))

                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target0,
                }))

                version0 = str(fmri.PkgFmri(target0).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target1,
                }))

                # Verify that evaluation entries are not present for uninstall.
                # Image operations that are for evaluation only and do not
                # require retrieving manifest information will not send any
                # intent information for efficiency.
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "reason": "evaluate",
                    "prior_version": str(fmri.PkgFmri(plist[1]).version),
                    "initial_target": target1,
                }) == False)

                version1 = str(fmri.PkgFmri(target1).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "reason": "process",
                    "prior_version": version1,
                    "initial_target": target1,
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

                # Only testing for process; no need to re-test for evaluate.
                entries = self.get_intent_entries()
                target1 = fmri.PkgFmri(plist[1]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target1,
                }))

                target0 = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target0,
                }))

        def test_4_image_upgrade(self):
                """Verify that the correct intent information is sent during an
                image upgrade."""

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

                api_obj.refresh(immediate=True)

                api_obj.reset()
                api_obj.plan_update_all(sys.argv[0])
                api_obj.prepare()
                api_obj.execute_plan()

                # Only testing for process; no need to re-test for evaluate.
                entries = self.get_intent_entries()
                # Verify that foo10 was installed when upgrading to foo12.
                version0 = str(fmri.PkgFmri(plist[0]).version)
                target3 = fmri.PkgFmri(plist[3]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "image-update",
                    "reason": "info",
                    "initial_target": target3,
                }))

                version2 = str(fmri.PkgFmri(plist[2]).version)
                target4 = fmri.PkgFmri(plist[4]).get_fmri(anarchy=True,
                    include_scheme=False)
                # Verify that bar10 was installed when upgrading to bar11.
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "image-update",
                    "reason": "info",
                    "initial_target": target4,
                }))

        def test_5_recursive_uninstall(self):
                """Verify that a recursive uninstall sends the expected intent
                information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10 + self.foo11 + self.bar10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["bar@1.0"])

                # Only testing for process; no need to re-test for evaluate.
                self.__do_uninstall(api_obj, ["foo"], True)

                entries = self.get_intent_entries()
                # Verify that foo10 was uninstalled.
                target0 = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True,
                    include_scheme=False)
                version0 = str(fmri.PkgFmri(target0).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "reason": "process",
                    "initial_target": target0,
                    "prior_version": version0,
                }))

                # Verify that bar10 was uninstalled because of foo10.
                target2 = fmri.PkgFmri(plist[2]).get_fmri(anarchy=True,
                    include_scheme=False)
                version2 = str(fmri.PkgFmri(target2).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "needed_by": target0,
                    "reason": "process",
                    "initial_target": target0,
                    "target": target2,
                    "prior_version": version2,
                }))

        def test_6_deep_dependencies(self):
                """Verify that an install or uninstall of a package with a
                dependency chain sends the expected intent information."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10 + self.bar10 + \
                    self.baz10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()

                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["baz"])
                self.__do_uninstall(api_obj, ["foo"], True)

                # Only testing for process; no need to re-test for evaluate.
                entries = self.get_intent_entries()

                #
                # Verify the install entries.
                #

                # Verify baz is logged.
                target2 = fmri.PkgFmri(plist[2]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target2,
                }))

                # Verify bar is logged.
                target1 = fmri.PkgFmri(plist[1]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target1,
                }))

                # Verify foo is logged.
                target0 = fmri.PkgFmri(plist[0]).get_fmri(anarchy=True,
                    include_scheme=False)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "install",
                    "reason": "info",
                    "initial_target": target0,
                }))

                #
                # Verify the uninstall entries.
                #

                # Verify foo is the initial target.
                version0 = str(fmri.PkgFmri(target0).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "reason": "process",
                    "initial_target": target0,
                    "prior_version": version0,
                }))

                # Verify foo is the initial target, bar is needed_by foo, and
                # foo is the target.
                version1 = str(fmri.PkgFmri(target1).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "needed_by": target0,
                    "reason": "process",
                    "initial_target": target0,
                    "target": target1,
                    "prior_version": version1,
                }))

                # Verify foo is the initial target, baz is needed_by bar, and
                # baz is the target.
                version2 = str(fmri.PkgFmri(target2).version)
                self.assert_(self.intent_entry_exists(entries, {
                    "operation": "uninstall",
                    "needed_by": target1,
                    "reason": "process",
                    "initial_target": target0,
                    "target": target2,
                    "prior_version": version2,
                }))


if __name__ == "__main__":
        unittest.main()
