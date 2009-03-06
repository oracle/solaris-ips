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
import time
import sys
import unittest
from stat import *
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress

API_VERSION = 10
PKG_CLIENT_NAME = "pkg"

class TestPkgApiInstall(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = False

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

        xfoo10 = """
            open xfoo@1.0,5.11-0
            close """

        xbar10 = """
            open xbar@1.0,5.11-0
            add depend type=require fmri=pkg:/xfoo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xbar11 = """
            open xbar@1.1,5.11-0
            add depend type=require fmri=pkg:/xfoo@1.2
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
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/baz mode=0555 owner=root group=bin path=/bin/baz
            close """

        deep10 = """
            open deep@1.0,5.11-0
            add depend type=require fmri=pkg:/bar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """
        
        xdeep10 = """
            open xdeep@1.0,5.11-0
            add depend type=require fmri=pkg:/xbar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        ydeep10 = """
            open ydeep@1.0,5.11-0
            add depend type=require fmri=pkg:/ybar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        misc_files = [ "/tmp/libc.so.1", "/tmp/cat", "/tmp/baz" ]

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

        @staticmethod
        def __do_install(api_obj, fmris, filters=None):
                if not filters:
                        filters = []
                api_obj.reset()
                api_obj.plan_install(fmris, filters)
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __do_uninstall(api_obj, fmris, recursive_removal=False):
                api_obj.reset()
                api_obj.plan_uninstall(fmris, recursive_removal)
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __eval_assert_raises(ex_type, eval_ex_func, func, *args):
                try:
                        func(*args)
                except ex_type, e:
                        print str(e)
                        if not eval_ex_func(e):
                                raise

        def test_basics_1(self):
                """ Send empty package foo@1.0, install and uninstall """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                
                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.__do_install(api_obj, ["foo"])

                self.pkg("list")
                self.pkg("verify")

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])
                self.pkg("verify")

        def test_basics_2(self):
                """ Send package foo@1.1, containing a directory and a file,
                    install, search, and uninstall. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.pkg("list -a")
                self.__do_install(api_obj, ["foo"])

                self.pkg("verify")
                self.pkg("list")

                self.pkg("search /lib/libc.so.1")
                self.pkg("search -r /lib/libc.so.1")
                self.pkg("search blah", exit = 1)
                self.pkg("search -r blah", exit = 1)

                # check to make sure timestamp was set to correct value

                libc_path = os.path.join(self.get_img_path(), "lib/libc.so.1")
                stat = os.stat(libc_path)

                self.assert_(stat[ST_MTIME] == self.foo11_timestamp)

                # check that verify finds changes
                now = time.time()
                os.utime(libc_path, (now, now))
                self.pkg("verify", exit=1)

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])

                self.pkg("verify")
                self.pkg("list -a")
                self.pkg("verify")

        def test_basics_3(self):
                """ Install foo@1.0, upgrade to foo@1.1, uninstall. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.foo11)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.__do_install(api_obj, ["foo@1.0"])

                self.pkg("list foo@1.0")
                self.pkg("list foo@1.1", exit = 1)

                api_obj.reset()
                self.__do_install(api_obj, ["foo@1.1"])
                self.pkg("list foo@1.1")
                self.pkg("list foo@1.0", exit = 1)
                self.pkg("list foo@1")
                self.pkg("verify")

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])
                self.pkg("list -a")
                self.pkg("verify")

        def test_basics_4(self):
                """ Add bar@1.0, dependent on foo@1.0, install, uninstall. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.foo11)
                self.pkgsend_bulk(durl, self.bar10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.pkg("list -a")
                api_obj.reset()
                self.__do_install(api_obj, ["bar@1.0"])

                self.pkg("list")
                self.pkg("verify")
                api_obj.reset()
                self.__do_uninstall(api_obj, ["bar", "foo"])

                # foo and bar should not be installed at this point
                self.pkg("list bar", exit = 1)
                self.pkg("list foo", exit = 1)
                self.pkg("verify")

        def test_image_upgrade(self):
                """ Send package bar@1.1, dependent on foo@1.2.  Install bar@1.0.
                    List all packages.  Upgrade image. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.foo11)
                self.pkgsend_bulk(durl, self.bar10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.__do_install(api_obj, ["bar@1.0"])

                self.pkgsend_bulk(durl, self.foo12)
                self.pkgsend_bulk(durl, self.bar11)

                self.pkg("contents -H")
                self.pkg("list")
                api_obj.refresh(False)

                self.pkg("list")
                self.pkg("verify")
                api_obj.reset()
                api_obj.plan_update_all(sys.argv[0])
                api_obj.prepare()
                api_obj.execute_plan()
                self.pkg("verify")

                self.pkg("list foo@1.2")
                self.pkg("list bar@1.1")

                api_obj.reset()
                self.__do_uninstall(api_obj, ["bar", "foo"])
                self.pkg("verify")


        def test_recursive_uninstall(self):
                """Install bar@1.0, dependent on foo@1.0, uninstall foo recursively."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.foo11)
                self.pkgsend_bulk(durl, self.bar10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.__do_install(api_obj, ["bar@1.0"])

                # Here's the real part of the regression test;
                # at this point foo and bar are installed, and
                # bar depends on foo.  foo and bar should both
                # be removed by this action.
                self.__do_uninstall(api_obj, ["foo"], True)
                                       
                self.pkg("list bar", exit = 1)
                self.pkg("list foo", exit = 1)

        def test_nonrecursive_dependent_uninstall(self):
                """Trying to remove a package that's a dependency of another
                package should fail if the uninstall isn't recursive."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.bar10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.__do_install(api_obj, ["bar@1.0"])

                api_obj.reset()
                self.assertRaises(api_errors.NonLeafPackageException,
                    self.__do_uninstall, api_obj, ["foo"])
                self.pkg("list bar")
                self.pkg("list foo")

        def test_basics_5(self):
                """ Add bar@1.1, install bar@1.0. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.xbar11)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["xbar@1.0"])

        def test_bug_1338(self):
                """ Add bar@1.1, dependent on foo@1.2, install bar@1.1. """
                
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bar11)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.assertRaises(api_errors.InventoryException,
                    self.__do_install, api_obj, ["bar@1.1"])

        def test_bug_1338_2(self):
                """ Add bar@1.1, dependent on foo@1.2, and baz@1.0, dependent
                    on foo@1.0, install baz@1.0 and bar@1.1. """
                
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bar11)
                self.pkgsend_bulk(durl, self.baz10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.assertRaises(api_errors.InventoryException,
                    self.__do_install, api_obj, ["baz@1.0", "bar@1.1"])

        def test_bug_1338_3(self):
                """ Add xdeep@1.0, xbar@1.0. xDeep@1.0 depends on xbar@1.0 which
                    depends on xfoo@1.0, install xdeep@1.0. """
                
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.xbar10)
                self.pkgsend_bulk(durl, self.xdeep10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.assertRaises(api_errors.InventoryException,
                    self.__do_install, api_obj, ["xdeep@1.0"])

        def test_bug_1338_4(self):
                """ Add ydeep@1.0. yDeep@1.0 depends on ybar@1.0 which depends
                on xfoo@1.0, install ydeep@1.0. """
                
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.ydeep10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.assertRaises(api_errors.InventoryException,
                    self.__do_install, api_obj, ["ydeep@1.0"])

        def test_bug_2795(self):
                """ Try to install two versions of the same package """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo11)
                self.pkgsend_bulk(durl, self.foo12)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self.__do_install(api_obj, ["foo@1.1", "foo@1.2"])
                self.pkg("list foo@1.1", exit = 1)
                self.pkg("list foo@1.2")
                self.__do_uninstall(api_obj, ["foo"])

                self.__do_install(api_obj, ["foo@1.2", "foo@1.1"])
                self.pkg("list foo@1.1", exit = 1)
                self.pkg("list foo@1.2")

        def test_install_matching(self):
                """ Try to [un]install packages matching a pattern """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.pkgsend_bulk(durl, self.bar10)
                self.pkgsend_bulk(durl, self.baz10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ['ba*'])
                self.pkg("list foo@1.0", exit=0)
                self.pkg("list bar@1.0", exit=0)
                self.pkg("list baz@1.0", exit=0)

                self.__do_uninstall(api_obj, ['ba*'])
                self.pkg("list foo@1.0", exit=0)
                self.pkg("list bar@1.0", exit=1)
                self.pkg("list baz@1.0", exit=1)

        def test_bad_fmris(self):
                """ Test passing problematic fmris into the api """

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                def check_unfound(e):
                        return e.unfound_fmris

                def check_illegal(e):
                        return e.illegal

                def check_missing(e):
                        return e.missing_matches
                
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_unfound, api_obj.plan_install, ["foo"], [])

                api_obj.reset()
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_unfound, api_obj.plan_uninstall, ["foo"], [])

                api_obj.reset()
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_install, ["@/foo"], [])
                
                api_obj.reset()
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_uninstall, ["/foo"], [])

                self.pkgsend_bulk(durl, self.foo10)

                api_obj.refresh(False)
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_missing, api_obj.plan_uninstall, ["foo"], [])

                api_obj.reset()
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_uninstall, ["/foo"], [])

                api_obj.reset()
                self.__do_install(api_obj, ["foo"])
                self.__do_uninstall(api_obj, ["foo"])

                api_obj.reset()                
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_missing, api_obj.plan_uninstall, ["foo"], [])

        def test_bug_4109(self):
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                def check_illegal(e):
                        return e.illegal

                api_obj.reset()
                self.__eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_install, ["/foo"], [])


if __name__ == "__main__":
        unittest.main()
