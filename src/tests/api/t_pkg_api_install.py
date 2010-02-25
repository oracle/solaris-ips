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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import time
import sys
import unittest
from stat import *
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.fmri as fmri
import pkg.client.progress as progress
import pkg.portable as portable
import shutil

API_VERSION = 34
PKG_CLIENT_NAME = "pkg"

class TestPkgApiInstall(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1 timestamp="20080731T024051Z"
            close """
        foo11_timestamp = 1217472051

        foo12 = """
            open foo@1.2,5.11-0
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        bar09 = """
            open bar@0.9,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0550 owner=root group=bin path=/bin/cat
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        bar11 = """
            open bar@1.1,5.11-0
            add depend type=require fmri=pkg:/foo@1.2
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xfoo10 = """
            open xfoo@1.0,5.11-0
            close """

        xbar10 = """
            open xbar@1.0,5.11-0
            add depend type=require fmri=pkg:/xfoo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xbar11 = """
            open xbar@1.1,5.11-0
            add depend type=require fmri=pkg:/xfoo@1.2
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        bar12 = """
            open bar@1.2,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        baz10 = """
            open baz@1.0,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/baz mode=0555 owner=root group=bin path=/bin/baz
            close """

        deep10 = """
            open deep@1.0,5.11-0
            add depend type=require fmri=pkg:/bar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xdeep10 = """
            open xdeep@1.0,5.11-0
            add depend type=require fmri=pkg:/xbar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        ydeep10 = """
            open ydeep@1.0,5.11-0
            add depend type=require fmri=pkg:/ybar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        badfile10 = """
            open badfile@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=/tmp/baz-file
            close """

        baddir10 = """
            open baddir@1.0,5.11-0
            add dir mode=755 owner=root group=bin path=/tmp/baz-dir
            close """

        moving10 = """
            open moving@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=baz preserve=true
            close """

        moving20 = """
            open moving@2.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=quux original_name="moving:baz" preserve=true
            close """

        misc_files = [ "tmp/libc.so.1", "tmp/cat", "tmp/baz" ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        @staticmethod
        def __do_install(api_obj, fmris):
                api_obj.reset()
                api_obj.plan_install(fmris)
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __do_uninstall(api_obj, fmris, recursive_removal=False):
                api_obj.reset()
                api_obj.plan_uninstall(fmris, recursive_removal)
                api_obj.prepare()
                api_obj.execute_plan()

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

                self.pkg("search -l /lib/libc.so.1")
                self.pkg("search -r /lib/libc.so.1")
                self.pkg("search -l blah", exit = 1)
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

        def test_pkg_file_errors(self):
                """ Verify that package install works as expected when
                files or directories are are missing during upgrade or
                uninstall. """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bar09 + self.bar10 + self.bar11 + \
                    self.foo10 + self.foo12 + self.moving10 + self.moving20)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                # Verify that missing files will be replaced during upgrade if
                # the file action has changed (even if the content hasn't),
                # such as when the mode changes.
                self.__do_install(api_obj, ["bar@0.9"])
                file_path = os.path.join(self.get_img_path(), "bin", "cat")
                portable.remove(file_path)
                self.assert_(not os.path.isfile(file_path))
                self.__do_install(api_obj, ["bar@1.0"])
                self.assert_(os.path.isfile(file_path))

                # Verify that if the directory containing a missing file is also
                # missing that upgrade will still work as expected for the file.
                self.__do_uninstall(api_obj, ["bar@1.0"])
                self.__do_install(api_obj, ["bar@0.9"])
                dir_path = os.path.dirname(file_path)
                shutil.rmtree(dir_path)
                self.assert_(not os.path.isdir(dir_path))
                self.__do_install(api_obj, ["bar@1.0"])
                self.assert_(os.path.isfile(file_path))

                # Verify that missing files won't cause uninstall failure.
                portable.remove(file_path)
                self.assert_(not os.path.isfile(file_path))
                self.__do_uninstall(api_obj, ["bar@1.0"])

                # Verify that missing directories won't cause uninstall failure.
                self.__do_install(api_obj, ["bar@1.0"])
                shutil.rmtree(dir_path)
                self.assert_(not os.path.isdir(dir_path))
                self.__do_uninstall(api_obj, ["bar@1.0"])

                # Verify that missing files won't cause update failure if
                # original_name is set.
                self.__do_install(api_obj, ["moving@1.0"])
                file_path = os.path.join(self.get_img_path(), "baz")
                portable.remove(file_path)
                self.__do_install(api_obj, ["moving@2.0"])
                file_path = os.path.join(self.get_img_path(), "quux")

                # Verify that missing files won't cause uninstall failure if
                # original_name is set.
                self.assert_(os.path.isfile(file_path))
                portable.remove(file_path)
                self.__do_uninstall(api_obj, ["moving@2.0"])

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
                api_obj.refresh(immediate=True)

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

                self.pkg("list -a")

                self.assertRaises(api_errors.PlanCreationException,
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

                self.assertRaises(api_errors.PlanCreationException,
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

                self.assertRaises(api_errors.PlanCreationException,
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

                self.assertRaises(api_errors.PlanCreationException,
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

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["foo@1.1", "foo@1.2"])

                self.pkg("list foo", exit = 1)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["foo@1.1", "foo@1.2"])


                self.pkg("list foo", exit = 1)

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
                        return e.unmatched_fmris

                def check_illegal(e):
                        return e.illegal

                def check_missing(e):
                        return e.missing_matches


                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_unfound, api_obj.plan_install, ["foo"])

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing, api_obj.plan_uninstall, ["foo"], False)

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_install, ["@/foo"])

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_uninstall, ["/foo"], False)

                self.pkgsend_bulk(durl, self.foo10)

                api_obj.refresh(False)
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing, api_obj.plan_uninstall, ["foo"], False)

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_uninstall, ["/foo"], False)

                api_obj.reset()
                api_obj.refresh(True)
                self.__do_install(api_obj, ["foo"])
                self.__do_uninstall(api_obj, ["foo"])

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing, api_obj.plan_uninstall, ["foo"], False)

        def test_bug_4109(self):
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                def check_illegal(e):
                        return e.illegal

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal, api_obj.plan_install, ["/foo"])

        def test_catalog_v0(self):
                """Test install from a publisher's repository that only supports
                catalog v0, and then the transition from v0 to v1."""

                self.dc.stop()
                self.dc.set_disable_ops(["catalog/1"])
                self.dc.start()

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self.__do_install(api_obj, ["foo"])

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])

                api_obj.reset()
                self.__do_install(api_obj, ["pkg://test/foo"])

                self.pkgsend_bulk(durl, self.bar10)
                self.dc.stop()
                self.dc.unset_disable_ops()
                self.dc.start()

                api_obj.reset()
                api_obj.refresh(immediate=True)

                api_obj.reset()
                self.__do_install(api_obj, ["pkg://test/bar@1.0"])

        def test_bad_package_actions(self):
                """Test the install of packages that have actions that are
                invalid."""

                # XXX This test is not yet comprehensive.

                # First, publish the package that will be corrupted and create
                # an image for testing.
                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.badfile10 + self.baddir10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                # This should succeed and cause the manifest to be cached.
                self.__do_install(api_obj, plist)

                # Now attempt to corrupt the client's copy of the manifest by
                # adding malformed actions or invalidating existing ones.
                for p in plist:
                        pfmri = fmri.PkgFmri(p)
                        mdata = self.get_img_manifest(pfmri)
                        if mdata.find("dir") != -1:
                                src_mode = "mode=755"
                        else:
                                src_mode = "mode=644"

                        # Remove the package so corrupt case can be tested.
                        self.__do_uninstall(api_obj, [pfmri.pkg_name])

                        for bad_mode in ("", 'mode=""', "mode=???"):
                                self.debug("Testing with bad mode "
                                    "'%s'." % bad_mode)

                                bad_mdata = mdata.replace(src_mode, bad_mode)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.assertRaises(api_errors.InvalidPackageErrors,
                                    self.__do_install, api_obj,
                                    [pfmri.pkg_name])

                        for bad_owner in ("", 'owner=""', "owner=invaliduser"):
                                self.debug("Testing with bad owner "
                                    "'%s'." % bad_owner)

                                bad_mdata = mdata.replace("owner=root",
                                    bad_owner)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.assertRaises(api_errors.InvalidPackageErrors,
                                    self.__do_install, api_obj,
                                    [pfmri.pkg_name])

                        for bad_group in ("", 'group=""', "group=invalidgroup"):
                                self.debug("Testing with bad group "
                                    "'%s'." % bad_group)

                                bad_mdata = mdata.replace("group=bin",
                                    bad_group)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.assertRaises(api_errors.InvalidPackageErrors,
                                    self.__do_install, api_obj,
                                    [pfmri.pkg_name])

                        for bad_act in (
                            'set name=description value="" \" my desc \" ""',
                            "set name=com.sun.service.escalations value="):
                                self.debug("Testing with bad action "
                                    "'%s'." % bad_act)

                                bad_mdata = mdata + "%s\n" % bad_act
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.assertRaises(api_errors.InvalidPackageErrors,
                                    self.__do_install, api_obj,
                                    [pfmri.pkg_name])


if __name__ == "__main__":
        unittest.main()
