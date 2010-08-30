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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.catalog as catalog
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.portable as portable
import re
import shutil
import stat
import time
import unittest


class TestPkgInstallBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

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

        afoo10 = """
            open a/foo@1.0,5.11-0
            close """

        boring10 = """
            open boring@1.0,5.11-0
            close """

        boring11 = """
            open boring@1.1,5.11-0
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

        a6018_1 = """
            open a6018@1.0,5.11-0
            close """

        a6018_2 = """
            open a6018@2.0,5.11-0
            close """

        b6018_1 = """
            open b6018@1.0,5.11-0
            add depend type=optional fmri=a6018@1
            close """

        badfile10 = """
            open badfile@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=/tmp/baz-file
            close """

        baddir10 = """
            open baddir@1.0,5.11-0
            add dir mode=755 owner=root group=bin path=/tmp/baz-dir
            close """

        a16189 = """
            open a16189@1.0,5.11-0
            add depend type=require fmri=pkg:/b16189@1.0
            close """

        b16189 = """
            open b16189@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        misc_files = [ "tmp/libc.so.1", "tmp/cat", "tmp/baz" ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def test_cli(self):
                """Test bad cli options"""

                self.image_create(self.rurl)

                self.pkg("-@", exit=2)
                self.pkg("-s status", exit=2)
                self.pkg("-R status", exit=2)

                self.pkg("install -@ foo", exit=2)
                self.pkg("install -vq foo", exit=2)
                self.pkg("install", exit=2)
                self.pkg("install foo@x.y", exit=1)
                self.pkg("install pkg:/foo@bar.baz", exit=1)

        def test_basics_1(self):
                """ Send empty package foo@1.0, install and uninstall """

                self.pkgsend_bulk(self.rurl, self.foo10)
                self.image_create(self.rurl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install foo")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall foo")
                self.pkg("verify")

        def test_basics_2(self):
                """ Send package foo@1.1, containing a directory and a file,
                    install, search, and uninstall. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11),
                    refresh_index=True)
                self.image_create(self.rurl)

                # Set content cache to be flushed on success.
                self.pkg("set-property flush-content-cache-on-success True")

                self.pkg("list -a")
                self.pkg("install foo")

                # Verify that content cache is empty after successful install.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                cache_dirs = os.listdir(img_inst.cached_download_dir())
                self.assertEqual(cache_dirs, [])
                self.pkg("set-property flush-content-cache-on-success False")

                self.pkg("verify")
                self.pkg("list")

                self.pkg("search -l /lib/libc.so.1")
                self.pkg("search -r /lib/libc.so.1")
                self.pkg("search -l blah", exit=1)
                self.pkg("search -r blah", exit=1)

                # check to make sure timestamp was set to correct value
                libc_path = os.path.join(self.get_img_path(), "lib/libc.so.1")
                lstat = os.stat(libc_path)

                assert (lstat[stat.ST_MTIME] == self.foo11_timestamp)

                # check that verify finds changes
                now = time.time()
                os.utime(libc_path, (now, now))
                self.pkg("verify", exit=1)

                self.pkg("uninstall foo")
                self.pkg("verify")
                self.pkg("list -a")
                self.pkg("verify")

        def test_basics_3(self):
                """ Install foo@1.0, upgrade to foo@1.1, uninstall. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11))
                self.image_create(self.rurl)

                # Verify that content cache is empty before install.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                cache_dirs = os.listdir(img_inst.cached_download_dir())
                self.assertEqual(cache_dirs, [])

                self.pkg("install foo@1.0")
                self.pkg("list foo@1.0")
                self.pkg("list foo@1.1", exit=1)

                self.pkg("install foo@1.1")

                # Verify that content cache is not empty after successful
                # install (since flush-content-cache-on-success is False
                # by default) for packages that have content.
                cache_dirs = os.listdir(img_inst.cached_download_dir())
                self.assertNotEqual(cache_dirs, [])

                self.pkg("list foo@1.1")
                self.pkg("list foo@1.0", exit=1)
                self.pkg("list foo@1")
                self.pkg("verify")

                self.pkg("uninstall foo")
                self.pkg("list -a")
                self.pkg("verify")

        def test_basics_4(self):
                """ Add bar@1.0, dependent on foo@1.0, install, uninstall. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11,
                    self.bar10))
                self.image_create(self.rurl)

                # Set content cache to not be flushed on success.
                self.pkg("set-property flush-content-cache-on-success False")

                # Verify that content cache is empty before install.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                cache_dirs = os.listdir(img_inst.cached_download_dir())
                self.assertEqual(cache_dirs, [])

                self.pkg("list -a")
                self.pkg("install bar@1.0")

                # Verify that content cache is not empty after successful
                # install (since flush-content-cache-on-success is False)
                # for packages that have content.
                cache_dirs = os.listdir(img_inst.cached_download_dir())
                self.assertNotEqual(cache_dirs, [])

                self.pkg("list")
                self.pkg("verify")
                self.pkg("uninstall -v bar foo")

                # foo and bar should not be installed at this point
                self.pkg("list bar", exit=1)
                self.pkg("list foo", exit=1)
                self.pkg("verify")

        def test_basics_5(self):
                """ Add bar@1.1, install bar@1.0. """

                self.pkgsend_bulk(self.rurl, self.xbar11)
                self.image_create(self.rurl)
                self.pkg("install xbar@1.0", exit=1)

        def test_basics_6(self):
                """ Install bar@1.0, upgrade to bar@1.1.
                Boring should be left alone, while
                foo gets upgraded as needed"""

                self.pkgsend_bulk(self.rurl, (self.bar10, self.bar11,
                    self.foo10, self.foo11, self.foo12, self.boring10,
                    self.boring11))
                self.image_create(self.rurl)

                self.pkg("install foo@1.0 bar@1.0 boring@1.0")
                self.pkg("list")
                self.pkg("list foo@1.0 boring@1.0 bar@1.0")
                self.pkg("install -v bar@1.1") # upgrade bar
                self.pkg("list")
                self.pkg("list bar@1.1 foo@1.2 boring@1.0")

        def test_basics_mdns(self):
                """ Send empty package foo@1.0, install and uninstall """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.pkg("set-property mirror-discovery True")
                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install foo")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall foo")
                self.pkg("verify")

        def test_image_upgrade(self):
                """ Send package bar@1.1, dependent on foo@1.2.  Install
                    bar@1.0.  List all packages.  Upgrade image. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11,
                    self.bar10))
                self.image_create(self.rurl)

                self.pkg("install bar@1.0")

                self.pkgsend_bulk(self.rurl, (self.foo12, self.bar11))
                self.pkg("refresh")

                self.pkg("contents -H")
                self.pkg("list")
                self.pkg("refresh")

                self.pkg("list")
                self.pkg("verify")
                self.pkg("image-update -v")
                self.pkg("verify")

                self.pkg("list foo@1.2")
                self.pkg("list bar@1.1")

                self.pkg("uninstall bar foo")
                self.pkg("verify")

        def test_recursive_uninstall(self):
                """Install bar@1.0, dependent on foo@1.0, uninstall foo
                recursively."""

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11,
                    self.bar10))
                self.image_create(self.rurl)

                self.pkg("install bar@1.0")

                # Here's the real part of the regression test;
                # at this point foo and bar are installed, and
                # bar depends on foo.  foo and bar should both
                # be removed by this action.
                self.pkg("uninstall -vr foo")
                self.pkg("list bar", exit=1)
                self.pkg("list foo", exit=1)

        def test_nonrecursive_dependent_uninstall(self):
                """Trying to remove a package that's a dependency of another
                package should fail if the uninstall isn't recursive."""

                self.pkgsend_bulk(self.rurl, (self.foo10, self.bar10))
                self.image_create(self.rurl)

                self.pkg("install bar@1.0")

                self.pkg("uninstall -v foo", exit=1)
                self.pkg("list bar")
                self.pkg("list foo")

        def test_bug_1338(self):
                """ Add bar@1.1, dependent on foo@1.2, install bar@1.1. """

                self.pkg("list -a")
                self.pkgsend_bulk(self.rurl, self.bar11)
                self.image_create(self.rurl)

                self.pkg("install xbar@1.1", exit=1)

        def test_bug_1338_2(self):
                """ Add bar@1.1, dependent on foo@1.2, and baz@1.0, dependent
                    on foo@1.0, install baz@1.0 and bar@1.1. """

                self.pkgsend_bulk(self.rurl, (self.bar11, self.baz10))
                self.image_create(self.rurl)
                self.pkg("list -a")
                self.pkg("install baz@1.0 bar@1.1")

        def test_bug_1338_3(self):
                """ Add xdeep@1.0, xbar@1.0. xDeep@1.0 depends on xbar@1.0 which
                    depends on xfoo@1.0, install xdeep@1.0. """

                self.pkgsend_bulk(self.rurl, (self.xbar10, self.xdeep10))
                self.image_create(self.rurl)

                self.pkg("install xdeep@1.0", exit=1)

        def test_bug_1338_4(self):
                """ Add ydeep@1.0. yDeep@1.0 depends on ybar@1.0 which depends
                on xfoo@1.0, install ydeep@1.0. """

                self.pkgsend_bulk(self.rurl, self.ydeep10)
                self.image_create(self.rurl)

                self.pkg("install ydeep@1.0", exit=1)

        def test_bug_2795(self):
                """ Try to install two versions of the same package """

                self.pkgsend_bulk(self.rurl, (self.foo11, self.foo12))
                self.image_create(self.rurl)

                self.pkg("install foo@1.1 foo@1.2", exit=1)

        def test_bug_6018(self):
                """  From original comment in bug report:

                Consider a repository that contains:

                a@1 and a@2

                b@1 that contains an optional dependency on package a@1

                If a@1 and b@1 are installed in an image, the "pkg image-update" command
                produces the following output:

                $ pkg image-update
                No updates available for this image.

                However, "pkg install a@2" works.
                """

                self.pkgsend_bulk(self.rurl, (self.a6018_1, self.a6018_2,
                    self.b6018_1))
                self.image_create(self.rurl)
                self.pkg("install b6018@1 a6018@1")
                self.pkg("image-update")
                self.pkg("list b6018@1 a6018@2")

        def test_install_matching(self):
                """ Try to [un]install packages matching a pattern """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.bar10,
                    self.baz10))
                self.image_create(self.rurl)
                # don't specify versions here; we have many
                # different versions of foo, bar & baz in repo
                # when entire class is run w/ one repo instance.

                # first case should fail since multiple patterns
                # match the same pacakge
                self.pkg("install 'ba*' 'b*'", exit=1)
                self.pkg("install 'ba*'", exit=0)
                self.pkg("list foo", exit=0)
                self.pkg("list bar", exit=0)
                self.pkg("list baz", exit=0)
                self.pkg("uninstall 'b*' 'f*'")

        def test_bad_package_actions(self):
                """Test the install of packages that have actions that are
                invalid."""

                # First, publish the package that will be corrupted and create
                # an image for testing.
                plist = self.pkgsend_bulk(self.rurl, (self.badfile10,
                    self.baddir10))
                self.image_create(self.rurl)

                # This should succeed and cause the manifest to be cached.
                self.pkg("install %s" % " ".join(plist))

                # While the manifest is cached, get a copy of its contents.
                for p in plist:
                        pfmri = fmri.PkgFmri(p)
                        mdata = self.get_img_manifest(pfmri)
                        if mdata.find("dir") != -1:
                                src_mode = "mode=755"
                        else:
                                src_mode = "mode=644"

                        # Now remove the package so corrupt case can be tested.
                        self.pkg("uninstall %s" % pfmri.pkg_name)

                        # Now attempt to corrupt the client's copy of the
                        # manifest in various ways to check if the client
                        # handles missing mode and invalid mode cases for
                        # file and directory actions.
                        for bad_mode in ("", 'mode=""', "mode=???"):
                                self.debug("Testing with bad mode "
                                    "'%s'." % bad_mode)
                                bad_mdata = mdata.replace(src_mode, bad_mode)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("install %s" % pfmri.pkg_name, exit=1)

                        # Now attempt to corrupt the client's copy of the
                        # manifest in various ways to check if the client
                        # handles missing or invalid owners and groups.
                        for bad_owner in ("", 'owner=""', "owner=invaliduser"):
                                self.debug("Testing with bad owner "
                                    "'%s'." % bad_owner)

                                bad_mdata = mdata.replace("owner=root",
                                    bad_owner)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("install %s" % pfmri.pkg_name, exit=1)

                        for bad_group in ("", 'group=""', "group=invalidgroup"):
                                self.debug("Testing with bad group "
                                    "'%s'." % bad_group)

                                bad_mdata = mdata.replace("group=bin",
                                    bad_group)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("install %s" % pfmri.pkg_name, exit=1)

                        # Now attempt to corrupt the client's copy of the
                        # manifest such that actions are malformed.
                        for bad_act in (
                            'set name=description value="" \" my desc \" ""',
                            "set name=com.sun.service.escalations value="):
                                self.debug("Testing with bad action "
                                    "'%s'." % bad_act)
                                bad_mdata = mdata + "%s\n" % bad_act
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("install %s" % pfmri.pkg_name, exit=1)

        def test_bug_3770(self):
                """ Try to install a package from a publisher with an
                unavailable repository. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                # Depot hasn't been started, so client can't connect.
                self.pkg("set-publisher --no-refresh -O %s test" % self.durl)
                self.pkg("install foo@1.1", exit=1)

        def test_bug_9929(self):
                """Make sure that we can uninstall/install a package that
                already has its contents on disk even when the repository
                isn't accessible."""

                # Depot required for this test since client doesn't cache
                # files from a file repository by default.
                self.dc.start()
                self.pkgsend_bulk(self.durl, self.foo11)
                self.image_create(self.durl)

                self.pkg("install foo")

                # Stop depot,  so client can't connect.
                self.dc.stop()
                self.pkg("set-publisher --no-refresh -O %s test" % self.durl)

                self.pkg("uninstall foo")
                lr_path = os.path.join(self.img_path, "var","pkg","publisher",
                    "test", "last_refreshed")
                os.unlink(lr_path)
                self.pkg("install --no-refresh foo")

        def test_bug_16189(self):
                """Create a repository with a pair of manifests.  Have
                pkg A depend upon pkg B.  Rename pkg B on the depot-side
                and attempt to install. This should fail, but not traceback.
                Then, modify the manifest on the serverside, ensuring that
                the contents don't match the hash.  Then try the install again.
                This should also fail, but not traceback."""

                afmri = self.pkgsend_bulk(self.rurl, self.a16189)
                bfmri = self.pkgsend_bulk(self.rurl, self.b16189)
                self.image_create(self.rurl)

                repo = self.dc.get_repo()

                bpath = repo.manifest(bfmri[0])
                old_dirname = os.path.basename(os.path.dirname(bpath))
                old_dirpath = os.path.dirname(os.path.dirname(bpath))
                new_dirname = "potato"
                old_path = os.path.join(old_dirpath, old_dirname)
                new_path = os.path.join(old_dirpath, new_dirname)
                os.rename(old_path, new_path)
                self.pkg("install a16189", exit=1)

                os.rename(new_path, old_path)
                self.image_destroy()
                self.image_create(self.rurl)

                apath = repo.manifest(afmri[0])
                afobj = open(apath, "w")
                afobj.write("set name=pkg.summary value=\"banana\"\n")
                afobj.close()
                self.pkg("install a16189", exit=1)


class TestPkgInstallAmbiguousPatterns(pkg5unittest.SingleDepotTestCase):

        # An "ambiguous" package name pattern is one which, because of the
        # pattern matching rules, might refer to more than one package.  This
        # may be as obvious as the pattern "SUNW*", but also like the pattern
        # "foo", where "foo" and "a/foo" both exist in the catalog.

        afoo10 = """
            open a/foo@1.0,5.11-0
            close """

        bfoo10 = """
            open b/foo@1.0,5.11-0
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        anotherfoo11 = """
            open another/foo@1.1,5.11-0
            close """

        depender10 = """
            open depender@1.0,5.11-0
            add depend type=require fmri=foo@1.0
            close """

        depender11 = """
            open depender@1.1,5.11-0
            add depend type=require fmri=foo@1.1
            close """

        def test_bug_4204(self):
                """Don't stack trace when printing a PlanCreationException with
                "multiple_matches" populated (on uninstall)."""

                self.pkgsend_bulk(self.rurl, (self.afoo10, self.bfoo10,
                    self.bar10))
                self.image_create(self.rurl)

                self.pkg("install foo", exit=1)
                self.pkg("install a/foo b/foo", exit=0)
                self.pkg("list")
                self.pkg("uninstall foo", exit=1)
                self.pkg("uninstall a/foo b/foo", exit=0)

        def test_bug_6874(self):
                """Don't stack trace when printing a PlanCreationException with
                "multiple_matches" populated (on install and image-update)."""

                self.pkgsend_bulk(self.rurl, (self.afoo10, self.bfoo10))
                self.image_create(self.rurl)

                self.pkg("install foo", exit=1)

        def test_ambiguous_pattern_install(self):
                """An image-update should never get confused about an existing
                package being part of an ambiguous set of package names."""

                self.pkgsend_bulk(self.rurl, self.foo10)

                self.image_create(self.rurl)
                self.pkg("install foo")

                self.pkgsend_bulk(self.rurl, self.anotherfoo11)
                self.pkg("refresh")
                self.pkg("image-update -v", exit=4)

        def test_ambiguous_pattern_depend(self):
                """A dependency on a package should pull in an exact name
                match."""

                self.pkgsend_bulk(self.rurl, (self.depender10, self.foo10))

                self.image_create(self.rurl)
                self.pkg("install depender")

                self.pkgsend_bulk(self.rurl, (self.foo11, self.anotherfoo11,
                    self.depender11))
                self.pkg("refresh")

                self.pkg("install depender")

                # Make sure that we didn't get other/foo from the dependency.
                self.pkg("list another/foo", exit=1)

        def test_non_ambiguous_fragment(self):
                """We should be able to refer to a package by its "basename", if
                that component is unique."""

                self.pkgsend_bulk(self.rurl, self.anotherfoo11)
                self.image_create(self.rurl)

                # Right now, this is not exact, but still unambiguous
                self.pkg("install foo")

                # Create ambiguity
                self.pkgsend_bulk(self.rurl, self.foo11)
                self.pkg("refresh")

                # This is unambiguous, should succeed
                self.pkg("install pkg:/foo")

                # This is now ambiguous, should fail
                self.pkg("install foo", exit=1)


class TestPkgInstallCircularDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg10 = """
            open pkg1@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg2
            close
        """

        pkg20 = """
            open pkg2@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg3
            close
        """

        pkg30 = """
            open pkg3@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg1
            close
        """


        pkg11 = """
            open pkg1@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg2@1.1
            close
        """

        pkg21 = """
            open pkg2@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg3@1.1
            close
        """

        pkg31 = """
            open pkg3@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg1@1.1
            close
        """

        def test_unanchored_circular_dependencies(self):
                """ check to make sure we can install
                circular dependencies w/o versions
                """

                # Send 1.0 versions of packages.
                self.pkgsend_bulk(self.rurl, (self.pkg10, self.pkg20,
                    self.pkg30))

                self.image_create(self.rurl)
                self.pkg("install pkg1")
                self.pkg("list")
                self.pkg("verify -v")

        def test_anchored_circular_dependencies(self):
                """ check to make sure we can install
                circular dependencies w/ versions
                """

                # Send 1.1 versions of packages.
                self.pkgsend_bulk(self.rurl, (self.pkg11, self.pkg21,
                    self.pkg31))

                self.image_create(self.rurl)
                self.pkg("install pkg1")
                self.pkg("list")
                self.pkg("verify -v")


class TestPkgInstallUpgrade(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        incorp10 = """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@1.0
            add depend type=incorporate fmri=pkg:/bronze@1.0
            close
        """

        incorp20 = """
            open incorp@2.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        incorp30 = """
            open incorp@3.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            close
        """

        incorpA = """
            open incorpA@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@1.0
            add depend type=incorporate fmri=pkg:/bronze@1.0
            close
        """

        incorpB =  """
            open incorpB@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        iridium10 = """
            open iridium@1.0,5.11-0
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """
        amber10 = """
            open amber@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add dir mode=0755 owner=root group=bin path=/etc
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add link path=/lib/libc.symlink target=/lib/libc.so.1
            add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
            add file tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
            add file tmp/amber2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright1 license=copyright
            close
        """

        brass10 = """
            open brass@1.0,5.11-0
            add depend fmri=pkg:/bronze type=require
            close
        """

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add depend fmri=pkg:/amber@1.0 type=require
            add license tmp/copyright2 license=copyright
            close
        """

        amber20 = """
            open amber@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add link path=/lib/libc.symlink target=/lib/libc.so.1
            add hardlink path=/lib/libc.amber target=/lib/libc.bronze
            add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
            add file tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
            add file tmp/amber2 mode=0444 owner=root group=bin path=/etc/bronze2
            add depend fmri=pkg:/bronze@2.0 type=require
            add license tmp/copyright2 license=copyright
            close
        """

        bronze20 = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        bronze30 = """
            open bronze@3.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """


        gold10 = """
            open gold@1.0,5.11-0
            add file tmp/gold-passwd1 mode=0644 owner=root group=bin path=etc/passwd preserve=true
            add file tmp/gold-group mode=0644 owner=root group=bin path=etc/group preserve=true
            add file tmp/gold-shadow mode=0600 owner=root group=bin path=etc/shadow preserve=true
            add file tmp/gold-ftpusers mode=0644 owner=root group=bin path=etc/ftpd/ftpusers preserve=true
            add file tmp/gold-silly mode=0644 owner=root group=bin path=etc/silly
            add file tmp/gold-silly mode=0644 owner=root group=bin path=etc/silly2
            close
        """

        gold20 = """
            open gold@2.0,5.11-0
            add file tmp/config2 mode=0644 owner=root group=bin path=etc/config2 original_name="gold:etc/passwd" preserve=true
            close
        """

        gold30 = """
            open gold@3.0,5.11-0
            close
        """

        golduser10 = """
            open golduser@1.0
            add user username=Kermit group=adm home-dir=/export/home/Kermit
            close
        """

        golduser20 = """
            open golduser@2.0
            close
        """

        silver10  = """
            open silver@1.0,5.11-0
            close
        """

        silver20  = """
            open silver@2.0,5.11-0
            add file tmp/gold-passwd2 mode=0644 owner=root group=bin path=etc/passwd original_name="gold:etc/passwd" preserve=true
            add file tmp/gold-group mode=0644 owner=root group=bin path=etc/group original_name="gold:etc/group" preserve=true
            add file tmp/gold-shadow mode=0600 owner=root group=bin path=etc/shadow original_name="gold:etc/shadow" preserve=true
            add file tmp/gold-ftpusers mode=0644 owner=root group=bin path=etc/ftpd/ftpusers original_name="gold:etc/ftpd/ftpusers" preserve=true
            add file tmp/gold-silly mode=0644 owner=root group=bin path=etc/silly
            add file tmp/silver-silly mode=0644 owner=root group=bin path=etc/silly2
            close
        """
        silver30  = """
            open silver@3.0,5.11-0
            add file tmp/config2 mode=0644 owner=root group=bin path=etc/config2 original_name="gold:etc/passwd" preserve=true
            close
        """

        silveruser = """
            open silveruser@1.0
            add user username=Kermit group=adm home-dir=/export/home/Kermit
            close
        """


        iron10 = """
            open iron@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file tmp/config1 mode=0644 owner=root group=bin path=etc/foo
            add hardlink path=etc/foo.link target=foo
            close
        """
        iron20 = """
            open iron@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file tmp/config2 mode=0644 owner=root group=bin path=etc/foo
            add hardlink path=etc/foo.link target=foo
            close
        """

        concorp10 = """
            open concorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        dricon1 = """
            open dricon@1
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/dricon_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            close
        """

        dricon2 = """
            open dricon@2
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add driver name=zigit alias=pci8086,1234
            close
        """

        dricon3 = """
            open dricon@3
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add driver name=zigit alias=pci8086,1234
            add driver name=figit alias=pci8086,1234
            close
        """

        dripol1 = """
            open dripol@1
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit policy="read_priv_set=net_rawaccess write_priv_set=net_rawaccess"
            close
        """

        dripol2 = """
            open dripol@2
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit
            close
        """

	liveroot10 = """
            open liveroot@1.0
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/liveroot1 path=/etc/liveroot mode=644 owner=root group=sys reboot-needed=true
            close
        """
	liveroot20 = """
            open liveroot@2.0
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/liveroot2 path=/etc/liveroot mode=644 owner=root group=sys reboot-needed=true
            add file tmp/liveroot2 path=/etc/liveroot mode=644 owner=root group=sys reboot-needed=true
            close
        """

        renameold1 = """
            open renold@1.0
            add file tmp/renold1 path=testme mode=0644 owner=root group=root preserve=renameold
            close
        """

        renameold2 = """
            open renold@2.0
            add file tmp/renold1 path=testme mode=0640 owner=root group=root preserve=renameold
            close
        """

        renameold3 = """
            open renold@3.0
            add file tmp/renold3 path=testme mode=0644 owner=root group=root preserve=renameold
            close
        """

        renamenew1 = """
            open rennew@1.0
            add file tmp/rennew1 path=testme mode=0644 owner=root group=root preserve=renamenew
            close
        """

        renamenew2 = """
            open rennew@2.0
            add file tmp/rennew1 path=testme mode=0640 owner=root group=root preserve=renamenew
            close
        """

        renamenew3 = """
            open rennew@3.0
            add file tmp/rennew3 path=testme mode=0644 owner=root group=root preserve=renamenew
            close
        """

        preserve1 = """
            open preserve@1.0
            add file tmp/preserve1 path=testme mode=0644 owner=root group=root preserve=true
            close
        """

        preserve2 = """
            open preserve@2.0
            add file tmp/preserve1 path=testme mode=0640 owner=root group=root preserve=true
            close
        """

        preserve3 = """
            open preserve@3.0
            add file tmp/preserve3 path=testme mode=0644 owner=root group=root preserve=true
            close
        """

        misc_files1 = [
            "tmp/amber1", "tmp/amber2", "tmp/bronzeA1",  "tmp/bronzeA2",
            "tmp/bronze1", "tmp/bronze2",
            "tmp/copyright1", "tmp/copyright2",
            "tmp/copyright3", "tmp/copyright4",
            "tmp/libc.so.1", "tmp/sh", "tmp/config1", "tmp/config2",
            "tmp/gold-passwd1", "tmp/gold-passwd2", "tmp/gold-group",
            "tmp/gold-shadow", "tmp/gold-ftpusers", "tmp/gold-silly",
            "tmp/silver-silly", "tmp/preserve1", "tmp/preserve3",
            "tmp/renold1", "tmp/renold3", "tmp/rennew1", "tmp/rennew3",
            "tmp/liveroot1", "tmp/liveroot2",
        ]

        misc_files2 = {
            "tmp/dricon_da": """\
wigit "pci8086,1234"
wigit "pci8086,4321"
# someother "pci8086,1234"
foobar "pci8086,9999"
""",
            "tmp/dricon2_da": """\
zigit "pci8086,1234"
wigit "pci8086,4321"
# someother "pci8086,1234"
foobar "pci8086,9999"
""",
            "tmp/dricon_n2m": """\
wigit 1
foobar 2
""",
            "tmp/dripol1_dp": """\
*		read_priv_set=none		write_priv_set=none
""",
            "tmp/gold-passwd1": """\
root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
""",
            "tmp/gold-passwd2": """\
root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
bogus:x:10001:10001:Bogus User:/:
""",
            "tmp/gold-group": """\
root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
""",
            "tmp/gold-shadow": """\
root:9EIfTNBp9elws:13817::::::
daemon:NP:6445::::::
bin:NP:6445::::::
sys:NP:6445::::::
adm:NP:6445::::::
""",
            "tmp/gold-ftpusers": """\
root
bin
sys
adm
""",
        }

        cat_data = " "

        foo10 = """
            open foo@1.0,5.11-0
            close """

        only_attr10 = """
            open only_attr@1.0,5.11-0
            add set name=foo value=bar
            close """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files1)
                self.make_misc_files(self.misc_files2)

        def test_incorp_install(self):
                """Make sure we don't round up packages we specify on
                install"""

                first_bronze = self.pkgsend_bulk(self.rurl, self.bronze20)[0]
                self.pkgsend_bulk(self.rurl, (self.incorp20, self.amber10,
                    self.bronze10, self.amber20, self.bronze20))

                # create image
                self.image_create(self.rurl)
                # install incorp2
                self.pkg("install incorp@2.0")
                # try to install version 1
                self.pkg("install bronze@1.0", exit=1)
                # install earliest version bronze@2.0
                self.pkg("install %s" % first_bronze)
                self.pkg("list -v %s" % first_bronze)
                self.pkg("install bronze@2.0")

        def test_upgrade1(self):

                """ Upgrade torture test.
                    Send package amber@1.0, bronze1.0; install bronze1.0, which
                    should cause amber to also install.
                    Send 2.0 versions of packages which contains a lot of
                    complex transactions between amber and bronze, then do
                    an image-update, and try to check the results.
                """

                # Send 1.0 versions of packages.
                self.pkgsend_bulk(self.rurl, (self.incorp10, self.amber10,
                    self.bronze10))

                #
                # In version 2.0, several things happen:
                #
                # Amber and Bronze swap a file with each other in both
                # directions.  The dependency flips over (Amber now depends
                # on Bronze).  Amber and Bronze swap ownership of various
                # directories.
                #
                # Bronze's 1.0 hardlink to amber's libc goes away and is
                # replaced with a file of the same name.  Amber hardlinks
                # to that.
                #
                self.pkgsend_bulk(self.rurl, (self.incorp20, self.amber20,
                    self.bronze20))

                # create image and install version 1
                self.image_create(self.rurl)
                self.pkg("install incorp@1.0")
                self.pkg("install bronze")

                self.pkg("list amber@1.0 bronze@1.0")
                self.pkg("verify -v")

                # demonstrate that incorp@1.0 prevents package movement
                self.pkg("install bronze@2.0 amber@2.0", exit=1)

                # Now image-update to get new versions of amber and bronze
                self.pkg("image-update")

                # Try to verify that it worked.
                self.pkg("list amber@2.0 bronze@2.0")
                self.pkg("verify -v")
                # make sure old implicit directories for bronzeA1 were removed
                self.assert_(not os.path.isdir(os.path.join(self.get_img_path(),
                    "A")))
                # Remove packages
                self.pkg("uninstall amber bronze")
                self.pkg("verify -v")

                # make sure all directories are gone save /var in test image
                self.assert_(os.listdir(self.get_img_path()) ==  ["var"])

        def test_upgrade2(self):
                """ test incorporations:
                        1) install files that conflict w/ existing incorps
                        2) install package w/ dependencies that violate incorps
                        3) install incorp that violates existing incorp
                        4) install incorp that would force package backwards
                        """

                # Send all pkgs
                self.pkgsend_bulk(self.rurl, (self.incorp10, self.incorp20,
                    self.incorp30, self.iridium10, self.concorp10, self.amber10,
                    self.amber20, self.bronze10, self.bronze20, self.bronze30,
                    self.brass10))

                self.image_create(self.rurl)

                self.pkg("install incorp@1.0")
                # install files that conflict w/ existing incorps
                self.pkg("install bronze@2.0", exit=1)
                # install package w/ dependencies that violate incorps
                self.pkg("install iridium@1.0", exit=1)
                # install package w/ unspecified dependency that pulls
                # in bronze
                self.pkg("install brass")
                self.pkg("verify brass@1.0 bronze@1.0")
                # attempt to install conflicting incorporation
                self.pkg("install concorp@1.0", exit=1)

                # attempt to force downgrade of package w/ older incorp
                self.pkg("install incorp@2.0")
                self.pkg("uninstall incorp@2.0")
                self.pkg("install incorp@1.0", exit=1)

                # upgrade pkg that loses incorp. deps. in new version
                self.pkg("install incorp@2.0")
                self.pkg("image-update")
                self.pkg("list bronze@3.0")

        def test_upgrade3(self):
                """Test for editable files moving between packages or locations
                or both."""

                self.pkgsend_bulk(self.rurl, (self.silver10, self.silver20,
                    self.silver30, self.gold10, self.gold20, self.gold30,
                    self.golduser10, self.golduser20, self.silveruser))

                self.image_create(self.rurl)

                # test 1: move an editable file between packages
                self.pkg("install gold@1.0 silver@1.0")
                self.pkg("verify -v")

                # modify config file
                test_str= "this file has been modified 1"
                file_path = "etc/passwd"
                self.file_append(file_path, test_str)

                # make sure /etc/passwd contains correct string
                self.file_contains(file_path, test_str)

                # update packages
                self.pkg("install gold@3.0 silver@2.0")
                self.pkg("verify -v")

                # make sure /etc/passwd contains still correct string
                self.file_contains(file_path, test_str)

                self.pkg("uninstall silver gold")


                # test 2: change an editable file's path within a package
                self.pkg("install gold@1.0")
                self.pkg("verify -v")

                # modify config file
                test_str= "this file has been modified test 2"
                file_path = "etc/passwd"
                self.file_append(file_path, test_str)

                self.pkg("install gold@2.0")
                self.pkg("verify -v")

                # make sure /etc/config2 contains correct string
                file_path = "etc/config2"
                self.file_contains(file_path, test_str)

                self.pkg("uninstall gold")
                self.pkg("verify -v")


                # test 3: move an editable file between packages and change its path
                self.pkg("install gold@1.0 silver@1.0")
                self.pkg("verify -v")

                # modify config file
                file_path = "etc/passwd"
                test_str= "this file has been modified test 3"
                self.file_append(file_path, test_str)

                self.file_contains(file_path, test_str)

                self.pkg("install gold@3.0 silver@3.0")
                self.pkg("verify -v")

                # make sure /etc/config2 now contains correct string
                file_path = "etc/config2"
                self.file_contains(file_path, test_str)

                self.pkg("uninstall gold silver")


                # test 4: move /etc/passwd between packages and ensure that we
                # can still uninstall a user at the same time.
                self.pkg("install gold@1.0 silver@1.0")
                self.pkg("verify -v")

                # add a user
                self.pkg("install golduser@1.0")

                # make local changes to the user
                pwdpath = os.path.join(self.get_img_path(), "etc/passwd")

                pwdfile = file(pwdpath, "r+")
                lines = pwdfile.readlines()
                for i, l in enumerate(lines):
                        if l.startswith("Kermit"):
                                lines[i] = lines[i].replace("& User",
                                    "Kermit loves Miss Piggy")
                pwdfile.seek(0)
                pwdfile.writelines(lines)
                pwdfile.close()

                silly_path = os.path.join(self.get_img_path(), "etc/silly")
                silly_inode = os.stat(silly_path).st_ino

                # update packages
                self.pkg("install gold@3.0 silver@2.0 golduser@2.0 silveruser")

                # make sure Kermie is still installed and still has our local
                # changes
                self.file_contains("etc/passwd",
                    "Kermit:x:5:4:Kermit loves Miss Piggy:/export/home/Kermit:")

                # also make sure that /etc/silly hasn't been removed and added
                # again, even though it wasn't marked specially
                self.assertEqual(os.stat(silly_path).st_ino, silly_inode)

        def test_upgrade4(self):
                """Test to make sure hardlinks are correctly restored when file
                they point to is updated."""

                self.pkgsend_bulk(self.rurl, (self.iron10, self.iron20))

                self.image_create(self.rurl)

                self.pkg("install iron@1.0")
                self.pkg("verify -v")

                self.pkg("install iron@2.0")
                self.pkg("verify -v")

        def test_upgrade_liveroot(self):
                """Test to make sure upgrade of package fails if on live root
                and reboot is needed."""

                self.pkgsend_bulk(self.rurl, (self.liveroot10, self.liveroot20))
                self.image_create(self.rurl)

                self.pkg("--debug simulate_live_root=True install liveroot@1.0")
                self.pkg("verify -v")
                self.pkg("--debug simulate_live_root=True install --deny-new-be liveroot@2.0",
                    exit=5)
                self.pkg("--debug simulate_live_root=True uninstall --deny-new-be liveroot",
                    exit=5)
                # "break" liveroot@1
                self.file_append("etc/liveroot", "this file has been changed")
                self.pkg("--debug simulate_live_root=True fix liveroot", exit=5)

        def test_upgrade_driver_conflicts(self):
                """Test to make sure driver_aliases conflicts don't cause
                add_drv to fail."""

                self.pkgsend_bulk(self.rurl, (self.dricon1, self.dricon2,
                    self.dricon3))

                self.image_create(self.rurl)

                self.pkg("list -afv")
                self.pkg("install dricon@1")
                # This one should comment out the wigit entry in driver_aliases
                self.pkg("install dricon@2")
                da_contents = file(os.path.join(self.get_img_path(),
                    "etc/driver_aliases")).readlines()
                self.assert_("# pkg(5): wigit \"pci8086,1234\"\n" in da_contents)
                self.assert_("wigit \"pci8086,1234\"\n" not in da_contents)
                self.assert_("wigit \"pci8086,4321\"\n" in da_contents)
                self.assert_("zigit \"pci8086,1234\"\n" in da_contents)
                # This one should fail
                self.pkg("install dricon@3", exit=1)

        def test_driver_policy_removal(self):
                """Test for bug #9568 - that removing a policy for a
                driver where there is no minor node associated with it,
                works successfully.
                """

                self.pkgsend_bulk(self.rurl, (self.dripol1, self.dripol2))

                self.image_create(self.rurl)

                self.pkg("list -afv")

                # Should install the frigit driver with a policy.
                self.pkg("install dripol@1")

                # Check that there is a policy entry for this
                # device in /etc/security/device_policy
                dp_contents = file(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")).readlines()
                self.assert_("frigit:*\tread_priv_set=net_rawaccess\twrite_priv_set=net_rawaccess\n" in dp_contents)

                # Should reinstall the frigit driver without a policy.
                self.pkg("install dripol@2")

                # Check that there is no longer a policy entry for this
                # device in /etc/security/device_policy
                dp_contents = file(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")).readlines()
                self.assert_("frigit:*\tread_priv_set=net_rawaccess\twrite_priv_set=net_rawaccess\n" not in dp_contents)

        def test_file_preserve(self):
                """Verify that file preserve=true works as expected during
                package install, upgrade, and removal."""

                self.pkgsend_bulk(self.rurl, (self.preserve1, self.preserve2,
                    self.preserve3))
                self.image_create(self.rurl)

                # If there are no local modifications, no preservation should be
                # done.  First with no content change ...
                self.pkg("install preserve@1")
                self.pkg("install preserve@2")
                self.file_contains("testme", "preserve1")
                self.pkg("verify preserve")
                self.pkg("uninstall preserve")

                # ... and again with content change.
                self.pkg("install preserve@1")
                self.pkg("install preserve@3")
                self.file_contains("testme", "preserve3")
                self.pkg("verify preserve")
                self.pkg("uninstall preserve")

                # Modify the file locally and update to a version where the
                # content changes.
                self.pkg("install preserve@1")
                self.file_append("testme", "junk")
                self.file_contains("testme", "preserve1")
                self.pkg("install preserve@3")
                self.file_contains("testme", "preserve1")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify preserve")
                self.pkg("uninstall preserve")

                # Modify the file locally and update to a version where just the
                # mode changes.
                self.pkg("install preserve@1")
                self.file_append("testme", "junk")
                self.pkg("install preserve@2")
                self.file_contains("testme", "preserve1")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")

                # Remove the file locally and update the package; this should
                # simply replace the missing file.
                self.file_remove("testme")
                self.pkg("install preserve@3")
                self.pkg("verify preserve")
                self.file_exists("testme")
                self.pkg("uninstall preserve@3")

                # Preserved files don't get their mode changed, and verify will
                # still balk, so fix up the mode.
                self.pkg("install preserve@1")
                self.pkg("install preserve@2")
                self.file_chmod("testme", 0640)
                self.pkg("verify preserve")

                # Verify that a package with a missing file that is marked with
                # the preserve=true won't cause uninstall failure.
                self.file_remove("testme")
                self.file_doesnt_exist("testme")
                self.pkg("uninstall preserve")

        def test_file_preserve_renameold(self):
                """Make sure that file upgrade with preserve=renameold works."""

                plist = self.pkgsend_bulk(self.rurl, (self.renameold1,
                    self.renameold2, self.renameold3))
                self.image_create(self.rurl)

                # If there are no local modifications, no preservation should be
                # done.  First with no content change ...
                self.pkg("install renold@1")
                self.pkg("install renold@2")
                self.file_contains("testme", "renold1")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # ... and again with content change.
                self.pkg("install renold@1")
                self.pkg("install renold@3")
                self.file_contains("testme", "renold3")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # Modify the file locally and update to a version where the
                # content changes.
                self.pkg("install renold@1")
                self.file_append("testme", "junk")
                self.pkg("install renold@3")
                self.file_contains("testme.old", "junk")
                self.file_doesnt_contain("testme", "junk")
                self.file_contains("testme", "renold3")
                self.dest_file_valid(plist, "renold@3.0", "testme", "testme")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # Modify the file locally and update to a version where just the
                # mode changes.
                self.pkg("install renold@1")
                self.file_append("testme", "junk")
                self.pkg("install renold@2")
                self.file_contains("testme.old", "junk")
                self.file_doesnt_contain("testme", "junk")
                self.file_contains("testme", "renold1")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # Remove the file locally and update the package; this should
                # simply replace the missing file.
                self.pkg("install renold@1")
                self.file_remove("testme")
                self.pkg("install renold@2")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

        def test_file_preserve_renamenew(self):
                """Make sure that file ugprade with preserve=renamenew works."""

                plist = self.pkgsend_bulk(self.rurl, (self.renamenew1,
                    self.renamenew2, self.renamenew3))
                self.image_create(self.rurl)

                # If there are no local modifications, no preservation should be
                # done.  First with no content change ...
                self.pkg("install rennew@1")
                self.pkg("install rennew@2")
                self.file_contains("testme", "rennew1")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

                # ... and again with content change
                self.pkg("install rennew@1")
                self.pkg("install rennew@3")
                self.file_contains("testme", "rennew3")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

                # Modify the file locally and update to a version where the
                # content changes.
                self.pkg("install rennew@1")
                self.file_append("testme", "junk")
                self.pkg("install rennew@3")
                self.file_contains("testme", "junk")
                self.file_doesnt_contain("testme.new", "junk")
                self.file_contains("testme.new", "rennew3")
                self.dest_file_valid(plist, "rennew@3.0", "testme",
                    "testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

                # Modify the file locally and update to a version where just the
                # mode changes.
                self.pkg("install rennew@1")
                self.file_append("testme", "junk")
                self.pkg("install rennew@2")
                self.file_contains("testme", "junk")
                self.file_doesnt_contain("testme.new", "junk")
                self.file_contains("testme.new", "rennew1")
                self.file_doesnt_exist("testme.old")

                # Preserved files don't get their mode changed, and verify will
                # still balk, so fix up the mode.
                self.file_chmod("testme", 0640)
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")
                self.file_remove("testme.new")

                # Remove the file locally and update the package; this should
                # simply replace the missing file.
                self.pkg("install rennew@1")
                self.file_remove("testme")
                self.pkg("install rennew@2")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

        def file_append(self, path, string):
                file_path = os.path.join(self.get_img_path(), path)
                f = file(file_path, "a+")
                f.write("\n%s\n" % string)
                f.close

        def dest_file_valid(self, plist, pkg, src, dest):
                """Used to verify that the dest item's mode, attrs, timestamp,
                etc. match the src items's matching action as expected."""

                for p in plist:
                        pfmri = fmri.PkgFmri(p, "5.11")
                        pfmri.publisher = None
                        sfmri = pfmri.get_short_fmri().replace("pkg:/", "")

                        if pkg != sfmri:
                                continue

                        m = manifest.Manifest()
                        m.set_content(self.get_img_manifest(pfmri))
                        for a in m.gen_actions():
                                if a.name != "file":
                                        # Only want file actions that have
                                        # preserve attribute.
                                        continue
                                if a.attrs["path"] != src:
                                        # Only want actions with matching path.
                                        continue
                                self.validate_fsobj_attrs(a, target=dest)

        def file_chmod(self, path, mode):
                file_path = os.path.join(self.get_img_path(), path)
                os.chmod(file_path, mode)

        def file_doesnt_exist(self, path):
                file_path = os.path.join(self.get_img_path(), path)
                if os.path.isfile(file_path):
                        self.assert_(False, "File %s exists" % path)

        def file_exists(self, path):
                file_path = os.path.join(self.get_img_path(), path)
                if not os.path.isfile(file_path):
                        self.assert_(False, "File %s does not exist" % path)

        def file_contains(self, path, string):
                file_path = os.path.join(self.get_img_path(), path)
                f = file(file_path)
                for line in f:
                        if string in line:
                                f.close()
                                break
                else:
                        f.close()
                        self.assert_(False, "File %s does not contain %s" % (path, string))

        def file_doesnt_contain(self, path, string):
                file_path = os.path.join(self.get_img_path(), path)
                f = file(file_path)
                for line in f:
                        if string in line:
                                f.close()
                                self.assert_(False, "File %s contains %s" % (path, string))
                else:
                        f.close()

        def file_remove(self, path):
                file_path = os.path.join(self.get_img_path(), path)
                portable.remove(file_path)


class TestPkgInstallActions(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        misc_files = {
                "ftpusers" :
"""# ident      "@(#)ftpusers   1.6     06/11/21 SMI"
#
# List of users denied access to the FTP server, see ftpusers(4).
#
root
bin
sys
adm
""",
                "group" :
"""root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
+::::
""",
                "passwd" :
"""root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
+::::::
""",
                "shadow" :
"""root:9EIfTNBp9elws:13817::::::
daemon:NP:6445::::::
bin:NP:6445::::::
sys:NP:6445::::::
adm:NP:6445::::::
+::::::::
""",
                "cat" : " ",
                "empty" : ""
        }


        foo10 = """
            open foo@1.0,5.11-0
            close """

        only_attr10 = """
            open only_attr@1.0,5.11-0
            add set name=foo value=bar
            close """

        only_depend10 = """
            open only_depend@1.0,5.11-0
            add depend type=require fmri=foo@1.0,5.11-0
            close """

        only_directory10 = """
            open only_dir@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        only_driver10 = """
            open only_driver@1.0,5.11-0
            add driver name=zerg devlink="type=ddi_pseudo;name=zerg\\t\D"
            close """

        only_group10 = """
            open only_group@1.0,5.11-0
            add group groupname=Kermit gid=28
            close """

        only_group_file10 = """
            open only_group_file@1.0,5.11-0
            add dir mode=0755 owner=root group=Kermit path=/export/home/Kermit
            close """

        only_hardlink10 = """
            open only_hardlink@1.0,5.11-0
            add hardlink path=/cat.hardlink target=/cat
            close """

        only_legacy10 = """
            open only_legacy@1.0,5.11-0
            add legacy arch=i386 category=system desc="GNU make - A utility used to build software (gmake) 3.81" hotline="Please contact your local service provider" name="gmake - GNU make" pkg=SUNWgmake vendor="Sun Microsystems, Inc." version=11.11.0,REV=2008.04.29.02.08
            close """

        only_link10 = """
            open only_link@1.0,5.11-0
            add link path=/link target=/tmp/cat
            close """

        only_user10 = """
            open only_user@1.0,5.11-0
            add user username=Kermit group=adm home-dir=/export/home/Kermit
            close """

        only_user_file10 = """
            open only_user_file@1.0,5.11-0
            add dir mode=0755 owner=Kermit group=adm path=/export/home/Kermit
            close """

        # some of these are subsets-- "always" and "at-end"-- for performance;
        # we assume that e.g. if a and z work, that bcdef, etc. will too.
        pkg_name_valid_chars = {
            "never": " `~!@#$%^&*()=[{]}\\|;:\",<>?",
            "always": "09azAZ",
            "after-first": "_/-.+",
            "at-end": "09azAZ_-.+",
        }

        def setUp(self):

                pkg5unittest.SingleDepotTestCase.setUp(self)

                self.only_file10 = """
                    open only_file@1.0,5.11-0
                    add file cat mode=0555 owner=root group=bin path=/cat
                    close """

                self.only_license10 = """
                    open only_license@1.0,5.11-0
                    add license cat license=copyright
                    close """

                self.baseuser = """
                    open system/action/user@0,5.11
                    add dir path=etc mode=0755 owner=root group=sys
                    add dir path=etc/ftpd mode=0755 owner=root group=sys
                    add user username=root password=9EIfTNBp9elws uid=0 group=root home-dir=/root gcos-field=Super-User login-shell=/usr/bin/bash ftpuser=false lastchg=13817 group-list=other group-list=bin group-list=sys group-list=adm
                    add group gid=0 groupname=root
                    add group gid=3 groupname=sys
                    add file empty path=etc/group mode=0644 owner=root group=sys preserve=true
                    add file empty path=etc/passwd mode=0644 owner=root group=sys preserve=true
                    add file empty path=etc/shadow mode=0400 owner=root group=sys preserve=true
                    add file empty path=etc/ftpd/ftpusers mode=0644 owner=root group=sys preserve=true
                    add file empty path=etc/user_attr mode=0644 owner=root group=sys preserve=true
                    close """

                self.singleuser = """
                    open singleuser@0,5.11
                    add user group=fozzie uid=16 username=fozzie
                    add group groupname=fozzie gid=16
                    close
                """

                self.basics0 = """
                    open basics@1.0,5.11-0
                    add file passwd mode=0644 owner=root group=sys path=etc/passwd preserve=true
                    add file shadow mode=0400 owner=root group=sys path=etc/shadow preserve=true
                    add file group mode=0644 owner=root group=sys path=etc/group preserve=true
                    add file ftpusers mode=0644 owner=root group=sys path=etc/ftpd/ftpusers preserve=true
                    add file empty mode=0644 owner=root group=sys path=etc/name_to_major preserve=true
                    add file empty mode=0644 owner=root group=sys path=etc/driver_aliases preserve=true
                    add dir mode=0755 owner=root group=sys path=etc
                    add dir mode=0755 owner=root group=sys path=etc/ftpd
                    close """

                self.basics1 = """
                    open basics1@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=lib
                    add dir mode=0755 owner=root group=sys path=var
                    add dir mode=0755 owner=root group=sys path=var/svc
                    add dir mode=0755 owner=root group=sys path=var/svc/manifest
                    add dir mode=0755 owner=root group=bin path=usr
                    add dir mode=0755 owner=root group=bin path=usr/local
                    close """

                self.grouptest = """
                    open grouptest@1.0,5.11-0
                    add dir mode=0755 owner=root group=Kermit path=/usr/Kermit
                    add file empty mode=0755 owner=root group=Kermit path=/usr/local/bin/do_group_nothing
                    add group groupname=lp gid=8
                    add group groupname=staff gid=10
                    add group groupname=Kermit
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.usertest10 = """
                    open usertest@1.0,5.11-0
                    add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
                    add file empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
                    add depend fmri=pkg:/basics@1.0 type=require
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.usertest11 = """
                    open usertest@1.1,5.11-0
                    add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
                    add file empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
                    add depend fmri=pkg:/basics@1.0 type=require
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit2 group-list=lp group-list=staff group-list=root ftpuser=false
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
                    add file empty mode=0755 owner=root group=root path=/usr/local/bin/silver
                    add depend fmri=pkg:/basics@1.0 type=require
                    add depend fmri=pkg:/basics1@1.0 type=require
                    close """
                self.silver20 = """
                    open silver@2.0,5.11-0
                    add file empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/silver
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
                    add depend fmri=pkg:/basics@1.0 type=require
                    add depend fmri=pkg:/basics1@1.0 type=require
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    close """

                self.devicebase = """
                    open devicebase@1.0,5.11-0
                    add dir mode=0755 owner=root group=root path=/var
                    add dir mode=0755 owner=root group=root path=/var/run
                    add dir mode=0755 owner=root group=root path=/tmp
                    add dir mode=0755 owner=root group=root path=/etc
                    add dir mode=0755 owner=root group=root path=/etc/security
                    add file empty mode=0600 owner=root group=root path=/etc/devlink.tab preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/name_to_major preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/driver_aliases preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/driver_classes preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/minor_perm preserve=true
                    add file empty mode=0644 owner=root group=root path=/etc/security/device_policy preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/security/extra_privs preserve=true
                    close
                """

                self.devlink10 = """
                    open devlinktest@1.0,5.11-0
                    add driver name=zerg devlink="type=ddi_pseudo;name=zerg\\t\D"
                    add driver name=borg devlink="type=ddi_pseudo;name=borg\\t\D" devlink="type=ddi_pseudo;name=warg\\t\D"
                    add depend type=require fmri=devicebase
                    close
                """

                self.devlink20 = """
                    open devlinktest@2.0,5.11-0
                    add driver name=zerg devlink="type=ddi_pseudo;name=zerg2\\t\D" devlink="type=ddi_pseudo;name=zorg\\t\D"
                    add driver name=borg devlink="type=ddi_pseudo;name=borg\\t\D" devlink="type=ddi_pseudo;name=zork\\t\D"
                    add depend type=require fmri=devicebase
                    close
                """

                self.badhardlink1 = """
                    open badhardlink1@1.0,5.11-0
                    add hardlink path=foo target=bar
                    close
                """

                self.badhardlink2 = """
                    open badhardlink2@1.0,5.11-0
                    add file cat mode=0555 owner=root group=bin path=/etc/motd
                    add hardlink path=foo target=/etc/motd
                    close
                """

                self.make_misc_files(self.misc_files)

        def test_basics_0(self):
                """Send basic infrastructure, install and uninstall."""

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1))
                self.image_create(self.rurl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install basics")
                self.pkg("install basics1")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall basics basics1")
                self.pkg("verify")

        def test_grouptest(self):

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.grouptest))
                self.image_create(self.rurl)
                self.pkg("install basics")
                self.pkg("install basics1")

                self.pkg("install grouptest")
                self.pkg("verify")
                self.pkg("uninstall grouptest")
                self.pkg("verify")

        def test_usertest(self):

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.grouptest, self.usertest10))
                self.image_create(self.rurl)
                self.pkg("install basics")
                self.pkg("install basics1")

                self.pkg("install usertest")
                self.pkg("verify")
                self.pkg("contents -m usertest")

                self.pkgsend_bulk(self.rurl, self.usertest11)
                self.pkg("refresh")
                self.pkg("install usertest")
                self.pkg("verify")
                self.pkg("contents -m usertest")

                self.pkg("uninstall usertest")
                self.pkg("verify")

        def test_primordial_usergroup(self):
                """Ensure that we can install user and group actions in the same
                transaction as /etc/passwd, /etc/group, etc."""

                self.pkgsend_bulk(self.rurl, [self.baseuser, self.singleuser])

                self.image_create(self.rurl)
                self.pkg("install system/action/user")
                self.pkg("verify")

                self.image_destroy()
                self.image_create(self.rurl)
                self.pkg("install singleuser", exit=1)

        def test_ftpuser(self):
                """Make sure we correctly handle /etc/ftpd/ftpusers."""

                notftpuser = """
                open notftpuser@1
                add user username=animal group=root ftpuser=false
                close"""

                ftpuserexp = """
                open ftpuserexp@1
                add user username=fozzie group=root ftpuser=true
                close"""

                ftpuserimp = """
                open ftpuserimp@1
                add user username=gonzo group=root
                close"""

                self.pkgsend_bulk(self.rurl, (self.basics0, notftpuser,
                    ftpuserexp, ftpuserimp))
                self.image_create(self.rurl)

                self.pkg("install basics")

                # Add a user with ftpuser=false.  Make sure the user is added to
                # the file, and that the user verifies.
                self.pkg("install notftpuser")
                fpath = self.get_img_path() + "/etc/ftpd/ftpusers"
                self.assert_("animal\n" in file(fpath).readlines())
                self.pkg("verify notftpuser")

                # Add a user with an explicit ftpuser=true.  Make sure the user
                # is not added to the file, and that the user verifies.
                self.pkg("install ftpuserexp")
                self.assert_("fozzie\n" not in file(fpath).readlines())
                self.pkg("verify ftpuserexp")

                # Add a user with an implicit ftpuser=true.  Make sure the user
                # is not added to the file, and that the user verifies.
                self.pkg("install ftpuserimp")
                self.assert_("gonzo\n" not in file(fpath).readlines())
                self.pkg("verify ftpuserimp")

                # Put a user into the ftpusers file as shipped, then add that
                # user, with ftpuser=false.  Make sure the user remains in the
                # file, and that the user verifies.
                self.pkg("uninstall notftpuser")
                file(fpath, "a").write("animal\n")
                self.pkg("install notftpuser")
                self.assert_("animal\n" in file(fpath).readlines())
                self.pkg("verify notftpuser")

                # Put a user into the ftpusers file as shipped, then add that
                # user, with an explicit ftpuser=true.  Make sure the user is
                # stripped from the file, and that the user verifies.
                self.pkg("uninstall ftpuserexp")
                file(fpath, "a").write("fozzie\n")
                self.pkg("install ftpuserexp")
                self.assert_("fozzie\n" not in file(fpath).readlines())
                self.pkg("verify ftpuserexp")

                # Put a user into the ftpusers file as shipped, then add that
                # user, with an implicit ftpuser=true.  Make sure the user is
                # stripped from the file, and that the user verifies.
                self.pkg("uninstall ftpuserimp")
                file(fpath, "a").write("gonzo\n")
                self.pkg("install ftpuserimp")
                self.assert_("gonzo\n" not in file(fpath).readlines())
                self.pkg("verify ftpuserimp")

        def test_groupverify(self):
                """Make sure we correctly verify group actions when users have
                been added."""

                simplegroup = """
                open simplegroup@1
                add group groupname=muppets
                close"""

                self.pkgsend_bulk(self.rurl, (self.basics0, simplegroup))
                self.image_create(self.rurl)

                self.pkg("install basics")
                self.pkg("install simplegroup")
                self.pkg("verify simplegroup")

                gpath = self.get_img_path() + "/etc/group"
                gdata = file(gpath).readlines()
                gdata[-1] = gdata[-1].rstrip() + "kermit,misspiggy\n"
                file(gpath, "w").writelines(gdata)
                self.pkg("verify simplegroup")

        def test_userverify(self):
                """Make sure we correctly verify user actions when the on-disk
                databases have been modified."""

                simpleuser = """
                open simpleuser@1
                add user username=misspiggy group=root gcos-field="& loves Kermie" login-shell=/bin/sh
                close"""

                self.pkgsend_bulk(self.rurl, (self.basics0, simpleuser))
                self.image_create(self.rurl)

                self.pkg("install basics")
                self.pkg("install simpleuser")
                self.pkg("verify simpleuser")

                ppath = self.get_img_path() + "/etc/passwd"
                pdata = file(ppath).readlines()
                spath = self.get_img_path() + "/etc/shadow"
                sdata = file(spath).readlines()

                def finderr(err):
                        self.assert_("\t\t" + err in self.output)

                # change a provided, empty-default field to something else
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/:/bin/zsh"
                file(ppath, "w").writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("login-shell: '/bin/zsh' should be '/bin/sh'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # change a provided, non-empty-default field to the default
                pdata[-1] = "misspiggy:x:5:0:& User:/:/bin/sh"
                file(ppath, "w").writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("gcos-field: '& User' should be '& loves Kermie'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # change a non-provided, non-empty-default field to something
                # other than the default
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/misspiggy:/bin/sh"
                file(ppath, "w").writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("home-dir: '/misspiggy' should be '/'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # add a non-provided, empty-default field
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/:/bin/sh"
                sdata[-1] = "misspiggy:*LK*:14579:7:::::"
                file(ppath, "w").writelines(pdata)
                os.chmod(spath,
                    stat.S_IMODE(os.stat(spath).st_mode)|stat.S_IWUSR)
                file(spath, "w").writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("min: '7' should be '<empty>'")
                # fails fix since we don't repair shadow entries on purpose
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser", exit=1)
                finderr("min: '7' should be '<empty>'")

                # remove a non-provided, non-empty-default field
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie::/bin/sh"
                sdata[-1] = "misspiggy:*LK*:14579::::::"
                file(ppath, "w").writelines(pdata)
                file(spath, "w").writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("home-dir: '' should be '/'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove a provided, non-empty-default field
                pdata[-1] = "misspiggy:x:5:0::/:/bin/sh"
                file(ppath, "w").writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("gcos-field: '' should be '& loves Kermie'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove a provided, empty-default field
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/:"
                file(ppath, "w").writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("login-shell: '' should be '/bin/sh'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove the user from /etc/passwd
                pdata[-1] = "misswiggy:x:5:0:& loves Kermie:/:"
                file(ppath, "w").writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("login-shell: '<missing>' should be '/bin/sh'")
                finderr("gcos-field: '<missing>' should be '& loves Kermie'")
                finderr("group: '<missing>' should be 'root'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove the user completely
                pdata[-1] = "misswiggy:x:5:0:& loves Kermie:/:"
                sdata[-1] = "misswiggy:*LK*:14579::::::"
                file(ppath, "w").writelines(pdata)
                file(spath, "w").writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("username: '<missing>' should be 'misspiggy'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")


        def test_minugid(self):
                """Ensure that an unspecified uid/gid results in the first
                unused."""

                self.pkgsend_bulk(self.rurl, (self.basics0, self.ugidtest))
                self.image_create(self.rurl)

                # This will lay down the sample passwd file, group file, etc.
                self.pkg("install basics")

                self.pkg("install ugidtest")
                passwd_file = file(os.path.join(self.get_img_path(),
                    "/etc/passwd"))
                for line in passwd_file:
                        if line.startswith("dummy"):
                                self.assert_(line.startswith("dummy:x:5:"))
                passwd_file.close()
                group_file = file(os.path.join(self.get_img_path(),
                    "/etc/group"))
                for line in group_file:
                        if line.startswith("dummy"):
                                self.assert_(line.startswith("dummy::5:"))
                group_file.close()

        def test_upgrade_with_user(self):
                """Ensure that we can add a user and change file ownership to
                that user in the same delta (mysql tripped over this early on
                in IPS development)."""

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.silver10, self.silver20, self.grouptest))
                self.image_create(self.rurl)
                self.pkg("install basics@1.0")
                self.pkg("install basics1@1.0")
                self.pkg("install silver@1.0")
                self.pkg("list silver@1.0")
                self.pkg("verify -v")
                self.pkg("install silver@2.0")
                self.pkg("verify -v")

        def test_user_in_grouplist(self):
                """If a user is present in a secondary group list when the user
                is installed, the client shouldn't crash."""

                self.pkgsend_bulk(self.rurl, (self.basics0, self.only_user10))
                self.image_create(self.rurl)
                self.pkg("install basics@1.0")
                group_path = os.path.join(self.get_img_path(), "etc/group")
                with file(group_path, "r+") as group_file:
                        lines = group_file.readlines()
                        lines[0] = lines[0][:-1] + "Kermit" + "\n"
                        group_file.truncate(0)
                        group_file.writelines(lines)
                self.pkg("install only_user@1.0")

        def test_invalid_open(self):
                """Send invalid package definitions (invalid fmris); expect
                failure."""

                for char in self.pkg_name_valid_chars["never"]:
                        invalid_name = "invalid%spkg@1.0,5.11-0" % char
                        self.pkgsend(self.rurl, "open '%s'" % invalid_name,
                            exit=1)

                for char in self.pkg_name_valid_chars["after-first"]:
                        invalid_name = "%sinvalidpkg@1.0,5.11-0" % char
                        if char == "-":
                                cmd = "open -- '%s'" % invalid_name
                        else:
                                cmd = "open '%s'" % invalid_name
                        self.pkgsend(self.rurl, cmd, exit=1)

                        invalid_name = "invalid/%spkg@1.0,5.11-0" % char
                        cmd = "open '%s'" % invalid_name
                        self.pkgsend(self.rurl, cmd, exit=1)

        def test_valid_open(self):
                """Send a series of valid packages; expect success."""

                for char in self.pkg_name_valid_chars["always"]:
                        valid_name = "%svalid%s/%spkg%s@1.0,5.11-0" % (char,
                            char, char, char)
                        self.pkgsend(self.rurl, "open '%s'" % valid_name)
                        self.pkgsend(self.rurl, "close -A")

                for char in self.pkg_name_valid_chars["after-first"]:
                        valid_name = "v%salid%spkg@1.0,5.11-0" % (char, char)
                        self.pkgsend(self.rurl, "open '%s'" % valid_name)
                        self.pkgsend(self.rurl, "close -A")

                for char in self.pkg_name_valid_chars["at-end"]:
                        valid_name = "validpkg%s@1.0,5.11-0" % char
                        self.pkgsend(self.rurl, "open '%s'" % valid_name)
                        self.pkgsend(self.rurl, "close -A")

        def test_devlink(self):
                # driver actions are not valid except on OpenSolaris
                if portable.util.get_canonical_os_name() != "sunos":
                        return

                self.pkgsend_bulk(self.rurl, (self.devicebase, self.devlink10,
                    self.devlink20))
                self.image_create(self.rurl)

                def readfile():
                        dlf = file(os.path.join(self.get_img_path(),
                            "etc/devlink.tab"))
                        dllines = dlf.readlines()
                        dlf.close()
                        return dllines

                def writefile(dllines):
                        dlf = file(os.path.join(self.get_img_path(),
                            "etc/devlink.tab"), "w")
                        dlf.writelines(dllines)
                        dlf.close()

                def assertContents(dllines, contents):
                        actual = re.findall("name=([^\t;]*)",
                            "\n".join(dllines), re.M)
                        self.assert_(set(actual) == set(contents))

                # Install
                self.pkg("install devlinktest@1.0")
                self.pkg("verify -v")

                dllines = readfile()

                # Verify that three entries got added
                self.assert_(len(dllines) == 3)

                # Verify that the tab character got written correctly
                self.assert_(dllines[0].find("\t") > 0)

                # Upgrade
                self.pkg("install devlinktest@2.0")
                self.pkg("verify -v")

                dllines = readfile()

                # Verify that there are four entries now
                self.assert_(len(dllines) == 4)

                # Verify they are what they should be
                assertContents(dllines, ["zerg2", "zorg", "borg", "zork"])

                # Remove
                self.pkg("uninstall devlinktest")
                self.pkg("verify -v")

                # Install again
                self.pkg("install devlinktest@1.0")

                # Diddle with it
                dllines = readfile()
                for i, line in enumerate(dllines):
                        if line.find("zerg") != -1:
                                dllines[i] = "type=ddi_pseudo;name=zippy\t\D\n"
                writefile(dllines)

                # Upgrade
                self.pkg("install devlinktest@2.0")

                # Verify that we spewed a message on upgrade
                self.assert_(self.output.find("not found") != -1)
                self.assert_(self.output.find("name=zerg") != -1)

                # Verify the new set
                dllines = readfile()
                self.assert_(len(dllines) == 5)
                assertContents(dllines,
                    ["zerg2", "zorg", "borg", "zork", "zippy"])

                self.pkg("uninstall devlinktest")

                # Null out the "zippy" entry
                writefile([])

                # Install again
                self.pkg("install devlinktest@1.0")

                # Diddle with it
                dllines = readfile()
                for i, line in enumerate(dllines):
                        if line.find("zerg") != -1:
                                dllines[i] = "type=ddi_pseudo;name=zippy\t\D\n"
                writefile(dllines)

                # Remove
                self.pkg("uninstall devlinktest")

                # Verify that we spewed a message on removal
                self.assert_(self.output.find("not found") != -1)
                self.assert_(self.output.find("name=zerg") != -1)

                # Verify that the one left behind was the one we overwrote.
                dllines = readfile()
                self.assert_(len(dllines) == 1)
                assertContents(dllines, ["zippy"])

                # Null out the "zippy" entry, but add the "zerg" entry
                writefile(["type=ddi_pseudo;name=zerg\t\D\n"])

                # Install ... again
                self.pkg("install devlinktest@1.0")

                # Make sure we didn't get a second zerg line
                dllines = readfile()
                self.failUnless(len(dllines) == 3, msg=dllines)
                assertContents(dllines, ["zerg", "borg", "warg"])

                # Now for the same test on upgrade
                dllines.append("type=ddi_pseudo;name=zorg\t\D\n")
                writefile(dllines)

                self.pkg("install devlinktest@2.0")
                dllines = readfile()
                self.failUnless(len(dllines) == 4, msg=dllines)
                assertContents(dllines, ["zerg2", "zorg", "borg", "zork"])

        def test_uninstall_without_perms(self):
                """Test for bug 4569"""

                pkg_list = [self.foo10, self.only_attr10, self.only_depend10,
                    self.only_directory10, self.only_file10,
                    self.only_group10, self.only_hardlink10, self.only_legacy10,
                    self.only_license10, self.only_link10, self.only_user10]

                # driver actions are not valid except on OpenSolaris
                if portable.util.get_canonical_os_name() == 'sunos':
                        pkg_list += [self.only_driver10]

                self.pkgsend_bulk(self.rurl, pkg_list + [
                    self.devicebase + self.basics0 + self.basics1])

                self.image_create(self.rurl)

                name_pat = re.compile("^\s+open\s+(\S+)\@.*$")

                def __manually_check_deps(name, install=True, exit=0):
                        cmd = "install --no-refresh"
                        if not install:
                                cmd = "uninstall"
                        if name == "only_depend" and not install:
                                self.pkg("uninstall foo", exit=exit)
                        elif name == "only_driver":
                                self.pkg("%s devicebase" % cmd, exit=exit)
                        elif name == "only_group":
                                self.pkg("%s basics" % cmd, exit=exit)
                        elif name == "only_hardlink":
                                self.pkg("%s only_file" % cmd, exit=exit)
                        elif name == "only_user":
                                if install:
                                        self.pkg("%s basics" % cmd, exit=exit)
                                        self.pkg("%s only_group" % cmd, exit=exit)
                                else:
                                        self.pkg("%s only_group" % cmd, exit=exit)
                                        self.pkg("%s basics" % cmd, exit=exit)
                for p in pkg_list:
                        name_mat = name_pat.match(p.splitlines()[1])
                        pname = name_mat.group(1)
                        __manually_check_deps(pname, exit=[0,4])
                        self.pkg("install --no-refresh %s" % pname,
                            su_wrap=True, exit=1)
                        self.pkg("install %s" % pname, su_wrap=True,
                            exit=1)
                        self.pkg("install --no-refresh %s" % pname)
                        self.pkg("uninstall %s" % pname, su_wrap=True,
                            exit=1)
                        self.pkg("uninstall %s" % pname)
                        __manually_check_deps(pname, install=False)

                for p in pkg_list:
                        name_mat = name_pat.match(p.splitlines()[1])
                        pname = name_mat.group(1)
                        __manually_check_deps(pname, exit=[0,4])
                        self.pkg("install --no-refresh %s" % pname)

                for p in pkg_list:
                        self.pkgsend_bulk(self.rurl, p)
                self.pkgsend_bulk(self.rurl, (self.devicebase, self.basics0,
                    self.basics1))

                # Modifying operations require permissions needed to create and
                # manage lock files.
                self.pkg("image-update --no-refresh", su_wrap=True, exit=1)

                self.pkg("refresh")
                self.pkg("image-update", su_wrap=True, exit=1)
                # Should fail since user doesn't have permission to refresh
                # publisher metadata.
                self.pkg("refresh --full", su_wrap=True, exit=1)
                self.pkg("refresh --full")
                self.pkg("image-update --no-refresh", su_wrap=True,
                    exit=1)
                self.pkg("image-update")

        def test_bug_3222(self):
                """ Verify that a timestamp of '0' for a passwd file will not
                    cause further package operations to fail.  This can happen
                    when there are time synchronization issues within a virtual
                    environment or in other cases. """

                self.pkgsend_bulk(self.rurl, (self.basics0, self.only_user10,
                    self.only_user_file10, self.only_group10,
                    self.only_group_file10, self.grouptest, self.usertest10))
                self.image_create(self.rurl)
                fname = os.path.join(self.get_img_path(), "etc", "passwd")
                self.pkg("install basics")

                # This should work regardless of whether a user is installed
                # at the same time as the file in a package, or if the user is
                # installed first and then files owned by that user are
                # installed.
                plists = [["grouptest", "usertest"],
                    ["only_user", "only_user_file"],
                    ["only_group", "only_group_file"]]
                for plist in plists:
                        for pname in plist:
                                os.utime(fname, (0, 0))
                                self.pkg("install %s" % pname)
                                self.pkg("verify")

                        for pname in reversed(plist):
                                os.utime(fname, (0, 0))
                                self.pkg("uninstall %s" % pname)
                                self.pkg("verify")

        def test_bad_hardlinks(self):
                """A couple of bogus hard link target tests."""

                self.pkgsend_bulk(self.rurl, (self.badhardlink1,
                    self.badhardlink2))
                self.image_create(self.rurl)

                # A package which tries to install a hard link to a target that
                # doesn't exist shouldn't stack trace, but exit sanely.
                self.pkg("install badhardlink1", exit=1)

                # A package which tries to install a hard link to a target
                # specified as an absolute path should install that link
                # relative to the image root.
                self.pkg("install badhardlink2")
                ino1 = os.stat(os.path.join(self.get_img_path(), "foo")).st_ino
                ino2 = os.stat(os.path.join(self.get_img_path(), "etc/motd")).st_ino
                self.assert_(ino1 == ino2)


class TestDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg10 = """
            open pkg1@1.0,5.11-0
            add depend type=optional fmri=pkg:/pkg2
            close
        """

        pkg20 = """
            open pkg2@1.0,5.11-0
            close
        """

        pkg11 = """
            open pkg1@1.1,5.11-0
            add depend type=optional fmri=pkg:/pkg2@1.1
            close
        """

        pkg21 = """
            open pkg2@1.1,5.11-0
            close
        """

        pkg30 = """
            open pkg3@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg1@1.1
            close
        """

        pkg40 = """
            open pkg4@1.0,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            close
        """

        pkg50 = """
            open pkg5@1.0,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            add depend type=require fmri=pkg:/pkg1@1.0
            close
        """

        pkg505 = """
            open pkg5@1.0.5,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            add depend type=require fmri=pkg:/pkg1@1.0
            close
        """
        pkg51 = """
            open pkg5@1.1,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            add depend type=exclude fmri=pkg:/pkg2
            add depend type=require fmri=pkg:/pkg1@1.0
            close
        """
        pkg60 = """
            open pkg6@1.0,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            close
        """

        pkg61 = """
            open pkg6@1.1,5.11-0
            close
        """

        leaf_template = """
            open pkg%s%s@%s,5.11-0
            add depend type=require fmri=pkg:/%s_incorp%s
            close
        """
        install_hold = "add set name=pkg.depend.install-hold value=test"

        leaf_expansion = [
                ("A","_0", "1.0", "A", ""),
                ("A","_1", "1.0", "A", ""),
                ("A","_2", "1.0", "A", ""),
                ("A","_3", "1.0", "A", ""),

                ("B","_0", "1.0", "B", ""),
                ("B","_1", "1.0", "B", ""),
                ("B","_2", "1.0", "B", ""),
                ("B","_3", "1.0", "B", ""),

                ("A","_0", "1.1", "A", "@1.1"),
                ("A","_1", "1.1", "A", "@1.1"),
                ("A","_2", "1.1", "A", "@1.1"),
                ("A","_3", "1.1", "A", "@1.1"),

                ("B","_0", "1.1", "B", "@1.1"),
                ("B","_1", "1.1", "B", "@1.1"),
                ("B","_2", "1.1", "B", "@1.1"),
                ("B","_3", "1.1", "B", "@1.1"),

                ("A","_0", "1.2", "A", "@1.2"),
                ("A","_1", "1.2", "A", "@1.2"),
                ("A","_2", "1.2", "A", "@1.2"),
                ("A","_3", "1.2", "A", "@1.2"),

                ("B","_0", "1.2", "B", "@1.2"),
                ("B","_1", "1.2", "B", "@1.2"),
                ("B","_2", "1.2", "B", "@1.2"),
                ("B","_3", "1.2", "B", "@1.2"),

                ("A","_0", "1.3", "A", ""),
                ("A","_1", "1.3", "A", ""),
                ("A","_2", "1.3", "A", ""),
                ("A","_3", "1.3", "A", ""),

                ("B","_0", "1.3", "B", ""),
                ("B","_1", "1.3", "B", ""),
                ("B","_2", "1.3", "B", ""),
                ("B","_3", "1.3", "B", "")
                ]

        incorps = [ """
            open A_incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.0
            add depend type=incorporate fmri=pkg:/pkgA_1@1.0
            add depend type=incorporate fmri=pkg:/pkgA_2@1.0
            add depend type=incorporate fmri=pkg:/pkgA_3@1.0
            close
        """,

        """
            open B_incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.0
            add depend type=incorporate fmri=pkg:/pkgB_1@1.0
            add depend type=incorporate fmri=pkg:/pkgB_2@1.0
            add depend type=incorporate fmri=pkg:/pkgB_3@1.0
            close
        """,

        """
            open A_incorp@1.1,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.1
            add depend type=incorporate fmri=pkg:/pkgA_1@1.1
            add depend type=incorporate fmri=pkg:/pkgA_2@1.1
            add depend type=incorporate fmri=pkg:/pkgA_3@1.1
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open B_incorp@1.1,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.1
            add depend type=incorporate fmri=pkg:/pkgB_1@1.1
            add depend type=incorporate fmri=pkg:/pkgB_2@1.1
            add depend type=incorporate fmri=pkg:/pkgB_3@1.1
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open A_incorp@1.2,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.2
            add depend type=incorporate fmri=pkg:/pkgA_1@1.2
            add depend type=incorporate fmri=pkg:/pkgA_2@1.2
            add depend type=incorporate fmri=pkg:/pkgA_3@1.2
            add set name=pkg.depend.install-hold value=test.A
            close
        """,

        """
            open B_incorp@1.2,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.2
            add depend type=incorporate fmri=pkg:/pkgB_1@1.2
            add depend type=incorporate fmri=pkg:/pkgB_2@1.2
            add depend type=incorporate fmri=pkg:/pkgB_3@1.2
            add set name=pkg.depend.install-hold value=test.B
            close
        """,

        """
            open A_incorp@1.3,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.3
            add depend type=incorporate fmri=pkg:/pkgA_1@1.3
            add depend type=incorporate fmri=pkg:/pkgA_2@1.3
            add depend type=incorporate fmri=pkg:/pkgA_3@1.3
            add set name=pkg.depend.install-hold value=test.A
            close
        """,

        """
            open B_incorp@1.3,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.3
            add depend type=incorporate fmri=pkg:/pkgB_1@1.3
            add depend type=incorporate fmri=pkg:/pkgB_2@1.3
            add depend type=incorporate fmri=pkg:/pkgB_3@1.3
            add set name=pkg.depend.install-hold value=test.B
            close
        """,

        """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.0
            add depend type=incorporate fmri=pkg:/B_incorp@1.0
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open incorp@1.1,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.1
            add depend type=incorporate fmri=pkg:/B_incorp@1.1
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open incorp@1.2,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.2
            add depend type=incorporate fmri=pkg:/B_incorp@1.2
            add set name=pkg.depend.install-hold value=test
            close
        """,
        """
            open incorp@1.3,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.3
            add depend type=exclude fmri=pkg:/pkgB_0
            add set name=pkg.depend.install-hold value=test
            close
        """
        ]

        bug_7394_incorp = """
            open bug_7394_incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkg1@2.0
            close
        """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, (self.pkg10, self.pkg20,
                    self.pkg11, self.pkg21, self.pkg30, self.pkg40, self.pkg50,
                    self.pkg505, self.pkg51, self.pkg60, self.pkg61,
                    self.bug_7394_incorp))

                for t in self.leaf_expansion:
                        self.pkgsend_bulk(self.rurl, self.leaf_template % t)

                for i in self.incorps:
                        self.pkgsend_bulk(self.rurl, i)

        def test_require_dependencies(self):
                """ exercise require dependencies """

                self.image_create(self.rurl)
                self.pkg("install pkg1@1.0")
                self.pkg("verify  pkg1@1.0")
                self.pkg("install pkg3@1.0")
                self.pkg("verify  pkg3@1.0 pkg1@1.1")

        def test_exclude_dependencies(self):
                """ exercise exclude dependencies """

                self.image_create(self.rurl)
                # install pkg w/ exclude dep.
                self.pkg("install pkg4@1.0")
                self.pkg("verify  pkg4@1.0")
                # install pkg that is allowed by dep
                self.pkg("install pkg1@1.0")
                self.pkg("verify  pkg1@1.0")
                # try to install disallowed pkg
                self.pkg("install pkg1@1.1", exit=1)
                self.pkg("uninstall '*'")
                # install pkg
                self.pkg("install pkg1@1.1")
                # try to install pkg exclude dep on already
                # installed pkg
                self.pkg("install pkg4@1.0", exit=1)
                self.pkg("uninstall '*'")
                # install a package w/ both exclude
                # and require dependencies
                self.pkg("install pkg5")
                self.pkg("verify pkg5@1.1 pkg1@1.0 ")
                self.pkg("uninstall '*'")
                # pick pkg to install that fits constraint
                # of already installed pkg
                self.pkg("install pkg2")
                self.pkg("install pkg5")
                self.pkg("verify pkg5@1.0.5 pkg1@1.0 pkg2")
                self.pkg("uninstall '*'")
                # install a package that requires updating
                # existing package to avoid exclude
                # dependency
                self.pkg("install pkg6@1.0")
                self.pkg("install pkg1@1.1")
                self.pkg("verify pkg1@1.1 pkg6@1.1")
                self.pkg("uninstall '*'")
                # try to install two incompatible pkgs
                self.pkg("install pkg1@1.1 pkg4@1.0", exit=1)

        def test_optional_dependencies(self):
                """ check to make sure that optional dependencies are enforced
                """

                self.image_create(self.rurl)
                self.pkg("install pkg1@1.0")

                # pkg2 is optional, it should not have been installed
                self.pkg("list pkg2", exit=1)

                self.pkg("install pkg2@1.0")

                # this should install pkg1@1.1 and upgrade pkg2 to pkg2@1.1
                self.pkg("install pkg1")
                self.pkg("list pkg2@1.1")

                self.pkg("uninstall pkg2")
                self.pkg("list pkg2", exit=1)
                # this should not install pkg2@1.0 because of the optional
                # dependency in pkg1
                self.pkg("list pkg1@1.1")
                self.pkg("install pkg2@1.0", exit=1)

        def test_incorporation_dependencies(self):
                """ shake out incorporation dependencies """

                self.image_create(self.rurl)
                self.pkg("list -a") # help w/ debugging

                # simple pkg requiring controlling incorp
                # should control pkgA_1 as well
                self.pkg("install -v pkgA_0@1.0 pkgA_1")
                self.pkg("list")
                self.pkg("verify pkgA_0@1.0 pkgA_1@1.0 A_incorp@1.0")
                self.pkg("install A_incorp@1.1")
                self.pkg("list pkgA_0@1.1 pkgA_1@1.1 A_incorp@1.1")
                self.pkg("uninstall '*'")
                # try nested incorporations
                self.pkg("install -v incorp@1.0 pkgA_0 pkgB_0")
                self.pkg("list")
                self.pkg("list incorp@1.0 pkgA_0@1.0 pkgB_0@1.0 A_incorp@1.0 B_incorp@1.0")
                # try to break incorporation
                self.pkg("install -v A_incorp@1.1", exit=1) # fixed by incorp@1.0
                # try image update
                self.pkg("image-update -v")
                self.pkg("list incorp@1.2")
                self.pkg("list pkgA_0@1.2")
                self.pkg("list pkgB_0@1.2")
                self.pkg("list A_incorp@1.2")
                self.pkg("list B_incorp@1.2")
                self.pkg("uninstall '*'")
                # what happens when incorporation specified
                # a package that isn't in the catalog
                self.pkg("install bug_7394_incorp")
                self.pkg("install pkg1", exit=1)
                self.pkg("uninstall '*'")
                # test pkg.depend.install-hold feature
                self.pkg("install -v A_incorp@1.1  pkgA_1")
                self.pkg("list pkgA_1@1.1")
                self.pkg("list A_incorp@1.1")
                # next attempt will fail because incorporations prevent motion even though
                # explicit dependency exists from pkg to incorporation.
                self.pkg("install pkgA_1@1.2", exit=1)
                # test to see if we could install both; presence of incorp causes relaxation
                # of pkg.depend.install-hold
                self.pkg("install -nv A_incorp@1.2 pkgA_1@1.2")
                # this attempt also succeeds because pkg.depend.install-hold is relaxed
                # since A_incorp is on command line
                self.pkg("install A_incorp@1.2")
                self.pkg("list pkgA_1@1.2")
                self.pkg("list A_incorp@1.2")
                # now demonstrate w/ version 1.2 subincorps that master incorp
                # prevents upgrade since pkg.depend.install-hold of master != other incorps
                self.pkg("install incorp@1.2")
                self.pkg("install A_incorp@1.3", exit=1)
                self.pkg("install incorp@1.3")
                self.pkg("list pkgA_1@1.3")
                self.pkg("list A_incorp@1.3")


class TestMultipleDepots(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            close"""

        bar10 = """
            open bar@1.0,5.11-0
            close"""

        moo10 = """
            open moo@1.0,5.11-0
            close"""

        quux10 = """
            open quux@1.0,5.11-0
            add depend type=optional fmri=optional@1.0
            close"""

        baz10 = """
            open baz@1.0,5.11-0
            add depend type=require fmri=corge@1.0
            close"""

        corge10 = """
            open corge@1.0,5.11-0
            close"""

        optional10 = """
            open optional@1.0,5.11-0
            close"""

        upgrade_p10 = """
            open upgrade-p@1.0,5.11-0
            close"""

        upgrade_p11 = """
            open upgrade-p@1.1,5.11-0
            close"""

        upgrade_np10 = """
            open upgrade-np@1.0,5.11-0
            close"""

        upgrade_np11 = """
            open upgrade-np@1.1,5.11-0
            close"""

        incorp_p10 = """
            open incorp-p@1.0,5.11-0
            add depend type=incorporate fmri=upgrade-p@1.0
            close"""

        incorp_p11 = """
            open incorp-p@1.1,5.11-0
            add depend type=incorporate fmri=upgrade-p@1.1
            close"""

        incorp_np10 = """
            open incorp-np@1.0,5.11-0
            add depend type=incorporate fmri=upgrade-np@1.0
            close"""

        incorp_np11 = """
            open incorp-np@1.1,5.11-0
            add depend type=incorporate fmri=upgrade-np@1.1
            close"""

        def setUp(self):
                """ depot 1 gets foo and moo, depot 2 gets foo and bar,
                    depot 3 is empty, depot 4 gets upgrade_np@1.1
                    depot 5 gets corge10, depot6 is empty
                    depot7 is a copy of test1's repository for test3
                    depot1 is mapped to publisher test1 (preferred)
                    depot2 is mapped to publisher test2
                    depot3 is not mapped during setUp
                    depot4 is not mapped during setUp
                    depot5 is not mapped during setUp
                    depot6 is not mapped during setUp"""

                # Two depots are intentionally started for some publishers.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test3", "test2", "test4", "test1", "test3"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(self.rurl1, (self.foo10, self.moo10,
                    self.quux10, self.optional10, self.upgrade_p10,
                    self.upgrade_np11, self.incorp_p10, self.incorp_p11,
                    self.incorp_np10, self.incorp_np11, self.baz10,
                    self.corge10))

                self.rurl2 = self.dcs[2].get_repo_url()
                self.pkgsend_bulk(self.rurl2, (self.foo10, self.bar10,
                    self.upgrade_p11, self.upgrade_np10, self.corge10))

                self.rurl3 = self.dcs[3].get_repo_url()

                self.rurl4 = self.dcs[4].get_repo_url()
                self.pkgsend_bulk(self.rurl4, self.upgrade_np11)

                self.rurl5 = self.dcs[5].get_repo_url()
                self.pkgsend_bulk(self.rurl5, self.corge10)

                self.rurl6 = self.dcs[6].get_repo_url()
                self.rurl7 = self.dcs[7].get_repo_url()

                # Copy contents of test1's repo to a repo for test3.
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[7].get_repodir()
                self.copy_repository(d1dir, d2dir, { "test1": "test3" })
                self.dcs[7].get_repo(auto_create=True).rebuild()

                # Create image and hence primary publisher
                self.image_create(self.rurl1, prefix="test1")

                # Create second publisher using depot #2
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

        def test_01_basics(self):
                self.pkg("list -a")

                # Install and uninstall moo (which is unique to depot 1)
                self.pkg("install moo")

                self.pkg("list")
                self.pkg("uninstall moo")

                # Install and uninstall bar (which is unique to depot 2)
                self.pkg("install bar")

                self.pkg("list")

                self.pkg("uninstall bar")

                # Install and uninstall foo (which is in both depots)
                # In this case, we should select foo from depot 1, since
                # it is preferred.
                self.pkg("install foo")

                self.pkg("list pkg://test1/foo")

                self.pkg("uninstall foo")

        def test_02_basics(self):
                """ Test install from an explicit preferred publisher """
                self.pkg("install pkg://test1/foo")
                self.pkg("list foo")
                self.pkg("list pkg://test1/foo")
                self.pkg("uninstall foo")

        def test_03_basics(self):
                """ Test install from an explicit non-preferred publisher """
                self.pkg("install pkg://test2/foo")
                self.pkg("list foo")
                self.pkg("list pkg://test2/foo")
                self.pkg("uninstall foo")

        def test_04_upgrade_preferred_to_non_preferred(self):
                """Install a package from the preferred publisher, and then
                upgrade it, failing to implicitly switching to a non-preferred
                publisher and then managing it explicitly"""
                self.pkg("list -a upgrade-p")
                self.pkg("install upgrade-p@1.0")
                self.pkg("install upgrade-p@1.1", exit=1)
                self.pkg("install pkg://test2/upgrade-p@1.1")
                self.pkg("uninstall upgrade-p")

        def test_05_upgrade_non_preferred_to_preferred(self):
                """Install a package from a non-preferred publisher, and then
                try to upgrade it, failing to implicitly switchto the preferred
                publisher and then succeed doing it explicitly."""
                self.pkg("list -a upgrade-np")
                self.pkg("install upgrade-np@1.0")
                self.pkg("install upgrade-np@1.1", exit=1)
                self.pkg("install pkg://test1/upgrade-np@1.1")
                self.pkg("uninstall upgrade-np")

        def test_06_upgrade_preferred_to_non_preferred_incorporated(self):
                """Install a package from the preferred publisher, and then
                upgrade it, failing to implicitly switching to a non-preferred
                publisher, when the package is constrained by an
                incorporation, and then succeed when doing so explicitly"""

                self.pkg("list -a upgrade-p incorp-p")
                self.pkg("install incorp-p@1.0")
                self.pkg("install upgrade-p")
                self.pkg("install incorp-p@1.1", exit=1)
                self.pkg("install incorp-p@1.1 pkg://test2/upgrade-p@1.1")
                self.pkg("list upgrade-p@1.1")
                self.pkg("uninstall '*'")


        def test_07_upgrade_non_preferred_to_preferred_incorporated(self):
                """Install a package from the preferred publisher, and then
                upgrade it, implicitly switching to a non-preferred
                publisher, when the package is constrained by an
                incorporation."""
                self.pkg("list", exit=1)
                self.pkg("list -a upgrade-np incorp-np")
                self.pkg("install incorp-np@1.0")
                self.pkg("install upgrade-np", exit=1)
                self.pkg("uninstall '*'")

        def test_08_install_repository_access(self):
                """Verify that packages can still be installed from a repository
                even when any of the other repositories are not reachable and
                --no-refresh is used."""

                # Change the second publisher to point to an unreachable URI.
                self.pkg("set-publisher --no-refresh -O http://test.invalid7 "
                    "test2")

                # Verify that no packages are installed.
                self.pkg("list", exit=1)

                # Verify moo can not be installed (as only depot1 has it) since
                # test2 cannot be reached (and needs a refresh).
                self.pkg("install moo", exit=1)

                # Verify moo can be installed (as only depot1 has it) even
                # though test2 cannot be reached (and needs a refresh) if
                # --no-refresh is used.
                self.pkg("install --no-refresh moo")

                self.pkg("uninstall moo")

                # Reset the test2 publisher.
                self.pkg("set-publisher -O %s test2" % self.rurl2)

                # Install v1.0 of upgrade-np from test2 to prepare for
                # image-update.
                self.pkg("install upgrade-np@1.0")

                # Set test1 to point to an unreachable URI.
                self.pkg("set-publisher --no-refresh -O http://test.invalid7 "
                    "test1")

                # Set test2 so that upgrade-np has a new version available
                # even though test1's repository is not accessible.
                self.pkg("set-publisher -O %s test2" % self.rurl4)

                # Verify image-update does not work since test1 is unreachable
                # even though upgrade-np@1.1 is available from test2.
                self.pkg("image-update", exit=1)

                # Verify image-update works even though test1 is unreachable
                # since upgrade-np@1.1 is available from test2 if --no-refresh
                # is used.
                self.pkg("image-update --no-refresh")

                # Now reset everything for the next test.
                self.pkg("uninstall upgrade-np")
                self.pkg("set-publisher --no-refresh -O %s test1" % self.rurl1)
                self.pkg("set-publisher -O %s test2" % self.rurl2)

        def test_09_uninstall_from_wrong_publisher(self):
                """Install a package from a publisher and try to remove it
                using a different publisher name; this should fail."""
                self.pkg("install foo")
                self.pkg("uninstall pkg://test2/foo", exit=1)
                # Check to make sure that uninstalling using the explicit
                # publisher works
                self.pkg("uninstall pkg://test1/foo")

        def test_10_install_after_publisher_removal(self):
                """Install a package from a publisher that has an optional
                dependency; then change the preferred publisher and remove the
                original publisher and then verify that installing the package
                again succeeds since it is essentially a no-op."""
                self.pkg("install quux@1.0")
                self.pkg("set-publisher -P test2")
                self.pkg("unset-publisher test1")
                self.pkg("list -avf")

                # Attempting to install an already installed package should
                # be a no-op even if the corresponding publisher no longer
                # exists.
                self.pkg("install quux@1.0", exit=4)

                # Image update should work if we don't see the optional
                # dependency.
                self.pkg("image-update", exit=4)

                # Add back the installed package's publisher, but using a
                # a repository with an empty catalog.  After that, attempt to
                # install the package again, which should succeed even though
                # the fmri is no longer in the publisher's catalog.
                self.pkg("set-publisher -O %s test1" % self.rurl6)
                self.pkg("install quux@1.0", exit=4)
                self.pkg("info quux@1.0")
                self.pkg("unset-publisher test1")

                # Add a new publisher, with the same packages as the installed
                # publisher.  Then, add back the installed package's publisher,
                # but using an empty repository.  After that, attempt to install
                # the package again, which should succeed since at least one
                # publisher has the package in its catalog.
                self.pkg("set-publisher -O %s test3" % self.rurl7)
                self.pkg("set-publisher -O %s test1" % self.rurl6)
                self.pkg("info -r pkg://test3/quux@1.0")
                self.pkg("install quux@1.0", exit=4)
                self.pkg("unset-publisher test1")
                self.pkg("unset-publisher test3")

                self.pkg("set-publisher -O %s test1" % self.rurl1)
                self.pkg("info -r pkg://test1/quux@1.0")
                self.pkg("unset-publisher test1")

                # Add a new publisher, using the installed package publisher's
                # repository.  After that, attempt to install the package again,
                # which should simply result in a 'no updates necessary' exit
                # code since the removed publisher's package is already the
                # newest version available.
                #
                self.pkg("set-publisher -O %s test3" % self.rurl7)
                self.pkg("install quux@1.0", exit=4)
                self.pkg("unset-publisher test3")

                # Change the image metadata back to where it was, in preparation
                # for subsequent tests.
                self.pkg("set-publisher -O %s -P test1" % self.rurl1)

                # Remove the installed packages.
                self.pkg("uninstall quux")

        def test_11_uninstall_after_preferred_publisher_change(self):
                """Install a package from the preferred publisher, change the
                preferred publisher, and attempt to remove the package."""
                self.pkg("install foo@1.0")
                self.pkg("set-publisher -P test2")
                self.pkg("uninstall foo")
                # Change the image metadata back to where it was, in preparation
                # for the next test.
                self.pkg("set-publisher -P test1")

        def test_12_uninstall_after_publisher_removal(self):
                """Install a package from the preferred publisher, remove the
                preferred publisher, and then evaluate whether an uninstall
                would succeed regardless of whether its publisher still exists
                or another publisher has the same fmri in its catalog."""
                self.pkg("install foo@1.0")
                self.pkg("set-publisher -P test2")
                self.pkg("unset-publisher test1")

                # Attempting to uninstall should work even if the corresponding
                # publisher no longer exists.
                self.pkg("uninstall -nv foo")

                # Add back the installed package's publisher, but using a
                # a repository with an empty catalog.  After that, attempt to
                # uninstall the package again, which should succeed even though
                # the fmri is no longer in the publisher's catalog.
                self.pkg("set-publisher -O %s test1" % self.rurl6)
                self.pkg("uninstall -nv foo")
                self.pkg("unset-publisher test1")

                # Add a new publisher, with a repository with the same packages
                # as the installed publisher.  Then, add back the installed
                # package's publisher using an empty repository.  After that,
                # attempt to uninstall the package again, which should succeed
                # even though the package's installed publisher is known, but
                # doesn't have the package's fmri in its catalog, but the
                # package's fmri is in a different publisher's catalog.
                self.pkg("set-publisher -O %s test3" % self.rurl7)
                self.pkg("set-publisher -O %s test1" % self.rurl6)
                self.pkg("uninstall -nv foo")
                self.pkg("unset-publisher test1")
                self.pkg("unset-publisher test3")

                # Add a new publisher, with a repository with the same packages
                # as the installed publisher.  After that, attempt to uninstall
                # the package again, which should succeed even though the fmri
                # is only in a different publisher's catalog.
                self.pkg("set-publisher -O %s test3" % self.rurl7)
                self.pkg("uninstall -nv foo")
                self.pkg("unset-publisher test3")

                # Finally, actually remove the package.
                self.pkg("uninstall -v foo")

                # Change the image metadata back to where it was, in preparation
                # for subsequent tests.
                self.pkg("set-publisher -O %s -P test1" % self.rurl1)

        def test_13_non_preferred_multimatch(self):
                """Verify that when multiple non-preferred publishers offer the
                same package that the expected install behaviour occurs."""

                self.pkg("set-publisher -P -O %s test3" % self.rurl3)

                # make sure we look here first; tests rely on that
                self.pkg("set-publisher --search-before=test2 test1")
                self.pkg("publisher")
                # First, verify that installing a package from a non-preferred
                # publisher will cause its dependencies to be installed from the
                # same publisher if the preferred publisher does not offer them.
                self.pkg("list -a")
                self.pkg("install pkg://test1/baz")
                self.pkg("list")
                self.pkg("info baz | grep test1")
                self.pkg("info corge | grep test1")
                self.pkg("uninstall -r corge")

                # Next, verify that naming the specific publishers for a package
                # and all of its dependencies will install the package from the
                # specified sources instead of the same publisher the package is a
                # dependency of.
                self.pkg("install pkg://test1/baz pkg://test2/corge")
                self.pkg("info baz | grep test1")
                self.pkg("info corge | grep test2")
                self.pkg("uninstall -r corge")

                # Finally, cleanup for the next test.
                self.pkg("set-publisher -P test1")
                self.pkg("unset-publisher test3")

        def test_14_nonsticky_publisher(self):
                """Test various aspects of the stick/non-sticky
                behavior of publishers"""

                # For ease of debugging
                self.pkg("list -a")
                # install from non-preferred repo explicitly
                self.pkg("install pkg://test2/upgrade-np@1.0")
                # Demonstrate that perferred publisher is not
                # acceptable, since test2 is sticky by default
                self.pkg("install upgrade-np@1.1", exit=1) # not right repo
                # Check that we can proceed once test2 is not sticky
                self.pkg("set-publisher --non-sticky test2")
                self.pkg("install upgrade-np@1.1") # should work now
                # Restore to pristine
                self.pkg("set-publisher --sticky test2")
                self.pkg("uninstall upgrade-np")
                # Repeat the test w/ preferred
                self.pkg("install upgrade-p")
                self.pkg("set-publisher -P test2")
                self.pkg("install upgrade-p@1.1", exit=1) #orig pub is sticky
                self.pkg("set-publisher --non-sticky test1")  #not anymore
                self.pkg("install upgrade-p@1.1")
                self.pkg("set-publisher -P --sticky test1") # restore
                self.pkg("uninstall '*'")
                # Check  that search order can be overridden w/ explicit
                # version specification...
                self.pkg("install upgrade-p")
                self.pkg("install upgrade-p@1.1", exit=1)
                self.pkg("set-publisher --non-sticky test1")
                self.pkg("install upgrade-p@1.1") # find match later on
                self.pkg("set-publisher --sticky test1")
                self.pkg("uninstall '*'")

        def test_15_nonsticky_update(self):
                """Test to make sure image-update follows the same
                publisher selection mechanisms as pkg install"""

                # try image-update
                self.pkg("install pkg://test2/upgrade-np@1.0")
                self.pkg("image-update", exit=4)
                self.pkg("list upgrade-np@1.0")
                self.pkg("set-publisher --non-sticky test2")
                self.pkg("publisher")
                self.pkg("list -a upgrade-np")
                self.pkg("image-update")
                self.pkg("list upgrade-np@1.1")
                self.pkg("set-publisher --sticky test2")
                self.pkg("uninstall '*'")

        def test_16_disabled_nonsticky(self):
                """Test to make sure disabled publishers are
                automatically made non-sticky, and after
                being enabled keep their previous value
                of stickiness"""

                # For ease of debugging
                self.pkg("list -a")
                # install from non-preferred repo explicitly
                self.pkg("install pkg://test2/upgrade-np@1.0")
                # Demonstrate that perferred publisher is not
                # acceptable, since test2 is sticky by default
                self.pkg("install upgrade-np@1.1", exit=1) # not right repo
                # Disable test2 and then we should be able to proceed
                self.pkg("set-publisher --disable test2")
                self.pkg("install upgrade-np@1.1")
                self.pkg("publisher")
                self.pkg("set-publisher --enable test2")
                self.pkg("publisher")
                self.pkg("publisher | egrep sticky", exit=1 )

        def test_17_dependency_is_from_deleted_publisher(self):
                self.pkg("set-publisher -O %s test4" % self.rurl5)
                self.pkg("install pkg://test4/corge")
                self.pkg("set-publisher --disable test2")
                self.pkg("set-publisher --disable test4")
                self.pkg("list -af")
                self.pkg("publisher")
                # this should work, since dependency is already installed
                # even though it is from a disabled publisher
                self.pkg("install baz@1.0")


class TestImageCreateCorruptImage(pkg5unittest.SingleDepotTestCaseCorruptImage):
        """
        If a new essential directory is added to the format of an image it will
        be necessary to update this test suite. To update this test suite,
        decide in what ways it is necessary to corrupt the image (removing the
        new directory or file, or removing the some or all of contents of the
        new directory for example). Make the necessary changes in
        pkg5unittest.SingleDepotTestCaseCorruptImage to allow the needed
        corruptions, then add new tests to the suite below. Be sure to add
        tests for both Full and User images, and perhaps Partial images if
        situations are found where these behave differently than Full or User
        images.
        """

        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        misc_files = [ "tmp/libc.so.1" ]

        PREFIX = "unset PKG_IMAGE; cd %s;"

        def setUp(self):
                pkg5unittest.SingleDepotTestCaseCorruptImage.setUp(self)
                self.make_misc_files(self.misc_files)

        def pkg(self, command, exit=0, comment=""):
                pkg5unittest.SingleDepotTestCaseCorruptImage.pkg(self, command,
                    exit=exit, comment=comment, prefix=self.PREFIX % self.dir)

        # For each test:
        # A good image is created at $basedir/image
        # A corrupted image is created at $basedir/image/bad (called bad_dir
        #     in subsequent notes) in verious ways
        # The $basedir/image/bad/final directory is created and PKG_IMAGE
        #     is set to that dirctory.

        # Tests simulating a corrupted Full Image

        def test_empty_var_pkg(self):
                """ Creates an empty bad_dir. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher", "cfg_cache", "file", "pkg", "index"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_publisher(self):
                """ Creates bad_dir with only the publisher and known/state
                dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_absent", "known_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_cfg_cache(self):
                """ Creates bad_dir with only the cfg_cache file missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_file(self):
                """ Creating bad_dir with only the file dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["file_absent"]), ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_pkg(self):
                """ Creates bad_dir with only the pkg dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(["pkg_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_index(self):
                """ Creates bad_dir with only the index dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(["index_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_publisher_empty(self):
                """ Creates bad_dir with all dirs and files present, but
                with an empty publisher and state/known dir.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]), ["var/pkg"])

                # This is expected to fail because it will see an empty
                # publisher directory and not rebuild the files as needed
                self.pkg("install --no-refresh foo@1.1", exit=1)
                self.pkg("install foo@1.1")

        def test_var_pkg_missing_publisher_empty_hit_then_refreshed_then_hit(
            self):
                """ Creates bad_dir with all dirs and files present, but with an
                with an empty publisher and state/known dir. This is to ensure
                that refresh will work, and that an install after the refresh
                also works.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]), ["var/pkg"])

                self.pkg("install --no-refresh foo@1.1", exit=1)
                self.pkg("refresh")
                self.pkg("install foo@1.1")


        def test_var_pkg_left_alone(self):
                """ Sanity check to ensure that the code for creating
                a bad_dir creates a good copy other than what's specified
                to be wrong. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(), ["var/pkg"])

                self.pkg("install foo@1.1")

        # Tests simulating a corrupted User Image

        # These tests are duplicates of those above but instead of creating
        # a corrupt full image, they create a corrupt User image.

        def test_empty_ospkg(self):
                """ Creates a corrupted image at bad_dir by creating empty
                bad_dir.  """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher", "cfg_cache", "file", "pkg", "index"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_publisher(self):
                """ Creates a corrupted image at bad_dir by creating bad_dir
                with only the publisher and known/state dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_absent", "known_absent"]),
                        [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_cfg_cache(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the cfg_cache file missing.  """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_file(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the file dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(["file_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_pkg(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the pkg dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(["pkg_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_index(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the index dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(["index_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_publisher_empty(self):
                """ Creates a corrupted image at bad_dir by creating bad_dir
                with all dirs and files present, but with an empty publisher
                and known/state dir. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install --no-refresh foo@1.1", exit=1)

        def test_ospkg_missing_publisher_empty_hit_then_refreshed_then_hit(self):
                """ Creates bad_dir with all dirs and files present, but with
                an empty publisher and known/state dir. This is to ensure that
                refresh will work, and that an install after the refresh also
                works.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install --no-refresh foo@1.1", exit=1)
                self.pkg("refresh")
                self.pkg("install foo@1.1")

        def test_ospkg_left_alone(self):
                """ Sanity check to ensure that the code for creating
                a bad_dir creates a good copy other than what's specified
                to be wrong. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

# Tests for checking what happens when two images are installed side by side.

        def test_var_pkg_missing_cfg_cache_ospkg_also_missing_alongside(self):
                """ Each bad_dir is missing a cfg_cache
                These 3 tests do nothing currently because trying to install an
                image next to an existing image in not currently possible.  The
                test cases remain against the day that such an arrangement is
                possible.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), [".org.opensolaris,pkg"])
                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), ["var/pkg"], destroy=False)

                self.pkg("install foo@1.1")


        def test_var_pkg_ospkg_missing_cfg_cache_alongside(self):
                """ Complete Full image besides a User image missing cfg_cache
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(), ["var/pkg"])
                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), [".org.opensolaris,pkg"],
                    destroy=False)

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_cfg_cache_ospkg_alongside(self):
                """ Complete User image besides a Full image missing cfg_cache
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), ["var/pkg"])
                self.dir = self.corrupt_image_create(self.rurl, set(),
                    [".org.opensolaris,pkg"], destroy=False)

                self.pkg("install foo@1.1")


class TestPkgInstallObsolete(pkg5unittest.SingleDepotTestCase):
        """Test cases for obsolete packages."""

        persistent_setup = True
        def test_basic(self):
                foo1 = """
                    open foo@1
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """
                # Obsolete packages can have metadata
                foo2 = """
                    open foo@2
                    add set name=pkg.obsolete value=true
                    add set name=pkg.summary value="A test package"
                    close
                """

                fbar = """
                    open fbar@1
                    add depend type=require fmri=foo@2
                    close
                """

                qbar = """
                    open qbar@1
                    add depend type=require fmri=qux@2
                    close
                """

                qux1 = """
                    open qux@1
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """

                qux2 = """
                    open qux@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=foo@1
                    close
                """

                fred1 = """
                    open fred@1
                    add depend type=require fmri=foo
                    close
                """
                fred2 = """
                    open fred@2
                    close
                """

                self.pkgsend_bulk(self.rurl, (foo1, foo2, fbar, qbar, qux1, qux2,
                    fred1))

                self.image_create(self.rurl)

                # First install the non-obsolete version of foo
                self.pkg("install foo@1")
                self.pkg("list foo@1")

                # Now install the obsolete version, and ensure it disappears (5)
                self.pkg("install foo")
                self.pkg("list foo", exit=1)

                # Explicitly installing an obsolete package succeeds, but
                # results in nothing on the system. (1)
                self.pkg("install foo@2", exit=4)
                self.pkg("list foo", exit=1)

                # Installing a package with a dependency on an obsolete package
                # fails. (2)
                self.pkg("install fbar", exit=1)

                # Installing a package with a dependency on a renamed package
                # succeeds, leaving the first package and the renamed package on
                # the system, as well as the empty, pre-renamed package. (3)
                self.pkg("install qbar")
                self.pkg("list qbar")
                self.pkg("list foo@1")
                self.pkg("list qux | grep -- --r--")
                self.pkg("uninstall '*'") #clean up for next test
                # A simple rename test: First install the pre-renamed version of
                # qux.  Then install the renamed version, and see that the new
                # package is installed, and the renamed package is installed,
                # but marked renamed.  (4)
                self.pkg("install qux@1")
                self.pkg("install qux") # upgrades qux
                self.pkg("list foo@1")
                self.pkg("list qux", exit=1)
                self.pkg("uninstall '*'") #clean up for next test

                # Install a package that's going to be obsoleted and a package
                # that depends on it.  Update the package to its obsolete
                # version and see that it fails.  (6, sorta)
                self.pkg("install foo@1 fred@1")
                self.pkg("install foo@2", exit=1)
                # now add a version of fred that doesn't require foo, and
                # show that update works
                self.pkgsend_bulk(self.rurl, fred2)
                self.pkg("refresh")
                self.pkg("install foo@2")
                self.pkg("uninstall '*'") #clean up for next test
                # test fix for bug 12898
                self.pkg("install qux@1")
                self.pkg("install fred@2")
                self.pkg("list foo@1", exit=1) # should not be installed
                self.pkg("install qux") #update
                self.pkg("list foo@1")

        def test_basic_7a(self):
                """Upgrade a package to a version with a dependency on a renamed
                package.  A => A' (-> Br (-> C))"""

                t7ap1_1 = """
                    open t7ap1@1
                    close
                """

                t7ap1_2 = """
                    open t7ap1@2
                    add depend type=require fmri=t7ap2
                    close
                """

                t7ap2_1 = """
                    open t7ap2@1
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=t7ap3
                    close
                """

                t7ap3_1 = """
                    open t7ap3@1
                    close
                """

                self.pkgsend_bulk(self.rurl, t7ap1_1)
                self.image_create(self.rurl)

                self.pkg("install t7ap1")

                self.pkgsend_bulk(self.rurl, (t7ap1_2, t7ap2_1, t7ap3_1))

                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list -af")
                self.pkg("list t7ap2 | grep -- --r--")
                self.pkg("list t7ap3")

        def test_basic_7b(self):
                """Upgrade a package to a version with a dependency on a renamed
                package.  Like 7a except package A starts off depending on B.

                A (-> B) => A' (-> Br (-> C))"""

                t7bp1_1 = """
                    open t7bp1@1
                    add depend type=require fmri=t7bp2
                    close
                """

                t7bp1_2 = """
                    open t7bp1@2
                    add depend type=require fmri=t7bp2
                    close
                """

                t7bp2_1 = """
                    open t7bp2@1
                    close
                """

                t7bp2_2 = """
                    open t7bp2@1
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=t7bp3
                    close
                """

                t7bp3_1 = """
                    open t7bp3@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t7bp1_1, t7bp2_1))
                self.image_create(self.rurl)

                self.pkg("install t7bp1")

                self.pkgsend_bulk(self.rurl, (t7bp1_2, t7bp2_2, t7bp3_1))

                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list t7bp2 | grep -- --r--")
                self.pkg("list t7bp3")

        def test_basic_7c(self):
                """Upgrade a package to a version with a dependency on a renamed
                package.  Like 7b, except package A doesn't change.

                A (-> B) => A (-> Br (-> C))"""

                t7cp1_1 = """
                    open t7cp1@1
                    add depend type=require fmri=t7cp2
                    close
                """

                t7cp2_1 = """
                    open t7cp2@1
                    close
                """

                t7cp2_2 = """
                    open t7cp2@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=t7cp3
                    close
                """

                t7cp3_1 = """
                    open t7cp3@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t7cp1_1, t7cp2_1))
                self.image_create(self.rurl)

                self.pkg("install t7cp1")

                self.pkgsend_bulk(self.rurl, (t7cp2_2, t7cp3_1))

                self.pkg("refresh")
                self.pkg("image-update")

                self.pkg("list t7cp2 | grep -- --r--")
                self.pkg("list t7cp3")

        def test_basic_6a(self):
                """Upgrade a package to a version with a dependency on an
                obsolete package.  This version is unlikely to happen in real
                life."""

                t6ap1_1 = """
                    open t6ap1@1
                    close
                """

                t6ap1_2 = """
                    open t6ap1@2
                    add depend type=require fmri=t6ap2
                    close
                """

                t6ap2_1 = """
                    open t6ap2@1
                    add set name=pkg.obsolete value=true
                    close
                """


                self.pkgsend_bulk(self.rurl, t6ap1_1)
                self.image_create(self.rurl)

                self.pkg("install t6ap1")

                self.pkgsend_bulk(self.rurl, (t6ap1_2, t6ap2_1))

                self.pkg("refresh")
                self.pkg("image-update", exit=4) # does nothing
                self.pkg("list t6ap1")

        def test_basic_6b(self):
                """Install a package with a dependency, and image-update after
                publishing updated packages for both, but where the dependency
                has become obsolete."""

                t6ap1_1 = """
                    open t6ap1@1
                    add depend type=require fmri=t6ap2
                    close
                """

                t6ap1_2 = """
                    open t6ap1@2
                    add depend type=require fmri=t6ap2
                    close
                """

                t6ap2_1 = """
                    open t6ap2@1
                    close
                """

                t6ap2_2 = """
                    open t6ap2@2
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (t6ap1_1, t6ap2_1))
                self.image_create(self.rurl)

                self.pkg("install t6ap1")
                self.pkg("list")

                self.pkgsend_bulk(self.rurl, (t6ap1_2, t6ap2_2))

                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list t6ap1@2 t6ap2@1")

        def test_basic_8a(self):
                """Upgrade a package to an obsolete leaf version when another
                depends on it."""

                t8ap1_1 = """
                    open t8ap1@1
                    close
                """

                t8ap1_2 = """
                    open t8ap1@2
                    add set name=pkg.obsolete value=true
                    close
                """

                t8ap2_1 = """
                    open t8ap2@1
                    add depend type=require fmri=t8ap1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t8ap1_1, t8ap2_1))
                self.image_create(self.rurl)

                self.pkg("install t8ap2")

                self.pkgsend_bulk(self.rurl, t8ap1_2)

                self.pkg("refresh")
                self.pkg("image-update", exit=4) # does nothing
                self.pkg("list  t8ap2@1")

        def test_basic_13a(self):
                """Publish an package with a dependency, then publish both as
                obsolete, image-update, and see that both packages have gotten
                removed."""

                t13ap1_1 = """
                    open t13ap1@1
                    add depend type=require fmri=t13ap2
                    close
                """

                t13ap1_2 = """
                    open t13ap1@2
                    add set name=pkg.obsolete value=true
                    close
                """

                t13ap2_1 = """
                    open t13ap2@1
                    close
                """

                t13ap2_2 = """
                    open t13ap2@2
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (t13ap1_1, t13ap2_1))
                self.image_create(self.rurl)

                self.pkg("install t13ap1")

                self.pkgsend_bulk(self.rurl, (t13ap1_2, t13ap2_2))

                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list", exit=1)

        def test_basic_11(self):
                """Install a package with an ambiguous name, where only one
                match is non-obsolete."""

                t11p1 = """
                    open netbeans@1
                    add set name=pkg.obsolete value=true
                    close
                """

                t11p2 = """
                    open developer/netbeans@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t11p1, t11p2))
                self.image_create(self.rurl)

                self.pkg("install netbeans")
                self.pkg("list pkg:/developer/netbeans")
                self.pkg("list pkg:/netbeans", exit=1)

        def test_basic_11a(self):
                """Install a package using an ambiguous name where
                pkg is renamed to another package, but not the
                conflicting one"""

                t11p1 = """
                    open netbonze@1
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=SUNWnetbonze
                    close
                """

                t11p2 = """
                    open developer/netbonze@1
                    close
                """

                t11p3 = """
                    open SUNWnetbonze@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t11p1, t11p2, t11p3))
                self.image_create(self.rurl)

                self.pkg("install netbonze", exit=1)

        def test_basic_11b(self):
                """Install a package using an ambiguous name where only one
                match is non-renamed, and the renamed match is renamed to the
                other."""

                t11p1 = """
                    open netbooze@1
                    close
                """

                t11p2 = """
                    open netbooze@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=developer/netbooze
                    close
                """

                t11p3 = """
                    open developer/netbooze@2
                    close
                """

                t11p4 = """
                    open developer/netbooze@3
                    add depend type=require fmri=developer/missing
                    close
                """

                self.pkgsend_bulk(self.rurl, (t11p1, t11p2, t11p3, t11p4))
                self.image_create(self.rurl)

                self.pkg("install netbooze")
                self.pkg("list pkg:/developer/netbooze")
                self.pkg("list pkg:/netbooze", exit=1)


        def test_basic_12(self):
                """Upgrade a package across a rename to an ambiguous name."""

                t12p1_1 = """
                    open netbeenz@1
                    close
                """

                t12p1_2 = """
                    open netbeenz@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/developer/netbeenz
                    close
                """

                t12p2_1 = """
                    open developer/netbeenz@1
                    close
                """

                self.pkgsend_bulk(self.rurl, t12p1_1)
                self.image_create(self.rurl)

                self.pkg("install netbeenz")

                self.pkgsend_bulk(self.rurl, (t12p1_2, t12p2_1))

                self.pkg("refresh")
                self.pkg("image-update -v")
                self.pkg("list pkg:/developer/netbeenz | grep -- -----")
                self.pkg("list pkg:/netbeenz", exit=1)

        def test_remove_renamed(self):
                """If a renamed package has nothing depending on it, it should
                be removed."""

                p1_1 = """
                    open remrenA@1
                    close
                """

                p1_2 = """
                    open remrenA@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/remrenB
                    close
                """

                p2_1 = """
                    open remrenB@1
                    close
                """

                p3_1 = """
                    open remrenC@1
                    add depend type=require fmri=pkg:/remrenA
                    close
                """

                self.pkgsend_bulk(self.rurl, p1_1)
                self.image_create(self.rurl)

                self.pkg("install remrenA")

                self.pkgsend_bulk(self.rurl, (p1_2, p2_1, p3_1))

                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list remrenA", exit=1)

                # But if there is something depending on the renamed package, it
                # can't be removed.
                self.pkg("uninstall remrenB")

                self.pkg("install remrenA@1 remrenC")
                self.pkg("image-update")
                self.pkg("list remrenA")

        def test_chained_renames(self):
                """If there are multiple renames, make sure we delete as much
                as possible, but no more."""

                A1 = """
                    open chained_A@1
                    close
                """

                A2 = """
                    open chained_A@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/chained_B@2
                    close
                """

                B2 = """
                    open chained_B@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/chained_C@2
                    close
                """

                C2 = """
                    open chained_C@2
                    close
                """

                X = """
                    open chained_X@1
                    add depend type=require fmri=pkg:/chained_A
                    close
                """

                Y = """
                    open chained_Y@1
                    add depend type=require fmri=pkg:/chained_B
                    close
                """

                Z = """
                    open chained_Z@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (A1, A2, B2, C2, X, Y, Z))

                self.image_create(self.rurl)

                self.pkg("install chained_A@1 chained_X chained_Z")
                for p in ["chained_A@1", "chained_X@1"]:
                        self.pkg("list %s" % p)
                self.pkg("image-update")

                for p in ["chained_A@2", "chained_X@1", "chained_B@2",
                    "chained_C@2", "chained_Z"]:
                        self.pkg("list %s" % p)

                self.pkg("uninstall chained_X")

                for p in ["chained_C@2", "chained_Z"]:
                        self.pkg("list %s" % p)

                # make sure renamed pkgs no longer needed are uninstalled
                for p in ["chained_A@2", "chained_B@2"]:
                        self.pkg("list %s" % p, exit=1)

        def test_unobsoleted(self):
                """Ensure that the existence of an obsolete package version
                does not prevent the system from upgrading to or installing
                a resurrected version."""

                pA_1 = """
                    open reintroA@1
                    close
                """

                pA_2 = """
                    open reintroA@2
                    add set name=pkg.obsolete value=true
                    close
                """

                pA_3 = """
                    open reintroA@3
                    close
                """

                pB_1 = """
                    open reintroB@1
                    add depend type=require fmri=pkg:/reintroA@1
                    close
                """

                pB_2 = """
                    open reintroB@2
                    close
                """

                pB_3 = """
                    open reintroB@3
                    add depend type=require fmri=pkg:/reintroA@3
                    close
                """

                self.pkgsend_bulk(self.rurl, (pA_1, pA_2, pA_3, pB_1, pB_2, pB_3))
                self.image_create(self.rurl)

                # Check installation of an unobsoleted package with no
                # dependencies.

                # Testing reintroA@1 -> reintroA@3 with image-update
                self.pkg("install reintroA@1")
                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Testing reintroA@1 -> reintroA@3 with install
                self.pkg("install reintroA@1")
                self.pkg("install reintroA@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Testing empty image -> reintroA@3 with install
                self.pkg("install reintroA@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Testing reintroA@1 -> reintroA@2 -> reintroA@3 with install
                self.pkg("install reintroA@1")
                self.pkg("install reintroA@2")
                self.pkg("install reintroA@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Check installation of a package with an unobsoleted
                # dependency.

                # Testing reintroB@1 -> reintroB@3 with image-update
                self.pkg("install reintroB@1")
                self.pkg("refresh")
                self.pkg("image-update")
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

                # Testing reintroB@1 -> reintroB@3 with install
                self.pkg("install reintroB@1")
                self.pkg("install reintroB@3")
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

                # Testing empty image -> reintroB@3 with install
                self.pkg("install reintroB@3")
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

                # Testing reintroB@1 -> reintroB@2 -> reintroB@3 with install
                self.pkg("install reintroB@1")
                self.pkg("install reintroB@2")
                self.pkg("install reintroB@3")
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

        def test_incorp_1(self):
                """We should be able to incorporate an obsolete package."""

                p1_1 = """
                    open inc1p1@1
                    add depend type=incorporate fmri=inc1p2@1
                    close
                """

                p2_1 = """
                    open inc1p2@1
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (p1_1, p2_1))
                self.image_create(self.rurl)

                self.pkg("install inc1p1")
                self.pkg("install inc1p2", exit=4)

                self.pkg("list inc1p2", exit=1)

        def test_incorp_2(self):
                """We should be able to continue incorporating a package when it
                becomes obsolete on upgrade."""

                p1_1 = """
                    open inc2p1@1
                    add depend type=incorporate fmri=inc2p2@1
                    close
                """

                p1_2 = """
                    open inc2p1@2
                    add depend type=incorporate fmri=inc2p2@2
                    close
                """

                p2_1 = """
                    open inc2p2@1
                    close
                """

                p2_2 = """
                    open inc2p2@2
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (p1_1, p2_1))
                self.image_create(self.rurl)

                self.pkg("install inc2p1 inc2p2")

                self.pkgsend_bulk(self.rurl, (p1_2, p2_2))

                self.pkg("refresh")
                self.pkg("list -afv")
                self.pkg("image-update -v")
                self.pkg("list inc2p2", exit=1)


class TestPkgInstallMultiObsolete(pkg5unittest.ManyDepotTestCase):
        """Tests involving obsolete packages and multiple publishers."""

        obs = """
            open stem@1
            add set name=pkg.obsolete value=true
            close
        """

        nonobs = """
            open stem@1
            close
        """

        persistent_setup = True

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()

        def test_01(self):
                """If an obsolete package is found in a preferred publisher and
                a non-obsolete package of the same name is found in a
                non-preferred publisher, pick the preferred pub as usual """

                self.pkgsend_bulk(self.rurl1, self.obs)
                self.pkgsend_bulk(self.rurl2, self.nonobs)

                self.image_create(self.rurl1, prefix="test1")
                self.pkg("set-publisher -O " + self.rurl2 + " test2")
                self.pkg("list -a")

                self.pkg("install stem", exit=4) # noting to do since it's obs
                # We should choose the obsolete package, which means nothing
                # gets installed.
                self.pkg("list", exit=1)

        def test_02(self):
                """Same as test_01, but now we have ambiguity in the package
                names.  While at first blush we might follow the same rule as in
                test_01 (choose the preferred publisher), in this case, we can't
                figure out which package from the preferred publisher we want,
                so the choice already isn't as straightforward, so we choose the
                non-obsolete package."""

                lobs = """
                    open some/stem@1
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl1, (self.obs, lobs))
                self.pkgsend_bulk(self.rurl2, (self.nonobs, lobs))

                self.image_create(self.rurl1, prefix="test1")
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

                self.pkg("install stem", exit=1)


class TestPkgInstallLicense(pkg5unittest.SingleDepotTestCase):
        """Tests involving one or more packages that require license acceptance
        or display."""

        persistent_depot = True

        baz10 = """
            open baz@1.0,5.11-0
            add license copyright.baz license=copyright.baz
            close """

        # First iteration has just a copyright.
        licensed10 = """
            open licensed@1.0,5.11-0
            add depend type=require fmri=baz@1.0
            add license copyright.licensed license=copyright.licensed
            close """

        # Second iteration has copyright that must-display and a new license
        # that doesn't require acceptance.
        licensed12 = """
            open licensed@1.2,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed
            close """

        # Third iteration now requires acceptance of license.
        licensed13 = """
            open licensed@1.3,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed must-accept=True
            close """

        misc_files = ["copyright.baz", "copyright.licensed", "libc.so.1",
            "license.licensed", "license.licensed.addendum"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, publisher="bobcat")
                self.make_misc_files(self.misc_files)

                plist = self.pkgsend_bulk(self.rurl, (self.licensed10,
                    self.licensed12, self.licensed13, self.baz10))

        def test_01_install_update(self):
                """Verifies that install and image-update handle license
                acceptance and display."""

                self.image_create(self.rurl, prefix="bobcat")

                # First, test the basic install case to see if a license that
                # does not require viewing or acceptance will be installed.
                self.pkg("install licensed@1.0")
                self.pkg("list")
                self.pkg("info licensed@1.0 baz@1.0")

                # Verify that --licenses include the license in output.
                self.pkg("install -n --licenses licensed@1.2 | "
                    "grep 'license.licensed'")

                # Verify that licenses are not included in -n output if
                # --licenses is not provided.
                self.pkg("install -n licensed@1.2 | grep 'copyright.licensed'",
                    exit=1)

                # Next, check that an upgrade succeeds when a license requires
                # display and that the license will be displayed.
                self.pkg("install licensed@1.2 | grep 'copyright.licensed'")

                # Next, check that an image-update fails if the user has not
                # specified --accept and a license requires acceptance.
                self.pkg("image-update -v", exit=6)

                # Verify that licenses are not included in -n output if
                # --licenses is not provided.
                self.pkg("image-update -n | grep 'copyright.licensed", exit=1)

                # Verify that --licenses include the license in output.
                self.pkg("image-update -n --licenses | "
                    "grep 'license.licensed'")

                # Next, check that an image-update succeeds if the user has
                # specified --accept and a license requires acceptance.
                self.pkg("image-update -v --accept")
                self.pkg("info licensed@1.3")


class TestActionErrors(pkg5unittest.SingleDepotTestCase):
        """This set of tests is intended to verify that the client will handle
        image state and action errors gracefully during install or uninstall
        operations.  Unlike the client API version of these tests, the CLI only
        needs to be tested for failure cases since it uses the client API."""

        # Teardown the test root every time.
        persistent_setup = False

        dir10 = """
            open dir@1.0,5.11-0
            add dir path=dir mode=755 owner=root group=bin
            close """

        # Purposefully omits depend on dir@1.0.
        filesub10 = """
            open filesub@1.0,5.11-0
            add file tmp/file path=dir/file mode=755 owner=root group=bin
            close """

        # Dependency providing file intentionally omitted.
        hardlink10 = """
            open hardlink@1.0,5.11-0
            add hardlink path=hardlink target=file
            close """

        # Empty packages suitable for corruption testing.
        foo10 = """
            open foo@1.0,5.11-0
            close """

        unsupp10 = """
            open unsupported@1.0
            add depend type=require fmri=foo@1.0
            close """

        misc_files = ["tmp/file"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

                plist = self.pkgsend_bulk(self.rurl, (self.dir10,
                    self.filesub10, self.hardlink10))

                self.plist = {}
                for p in plist:
                        pfmri = fmri.PkgFmri(p, "5.11")
                        self.plist[pfmri.pkg_name] = pfmri

        @staticmethod
        def __write_empty_file(target, mode=644, owner="root", group="bin"):
                f = open(target, "wb")
                f.write("\n")
                f.close()
                os.chmod(target, mode)
                owner = portable.get_user_by_name(owner, "/", True)
                group = portable.get_group_by_name(group, "/", True)
                os.chown(target, owner, group)

        def test_00_directory(self):
                """Verify that directory install fails as expected when it has
                been replaced with a link prior to install."""

                self.image_create(self.rurl)

                # The dest_dir's installed path.
                dest_dir_name = "dir"
                dest_dir = os.path.join(self.get_img_path(), dest_dir_name)

                # Directory replaced with a link (fails for install).
                self.__write_empty_file(dest_dir + ".src")
                os.symlink(dest_dir + ".src", dest_dir)
                self.pkg("install %s" % dest_dir_name, exit=1)

        def test_01_file(self):
                """Verify that file install works as expected when its parent
                directory has been replaced with a link."""

                self.image_create(self.rurl)

                # File's parent directory replaced with a link.
                self.pkg("install dir")
                src = os.path.join(self.get_img_path(), "dir")
                os.mkdir(os.path.join(self.get_img_path(), "export"))
                new_src = os.path.join(os.path.dirname(src), "export", "dir")
                shutil.move(src, os.path.dirname(new_src))
                os.symlink(new_src, src)
                self.pkg("install filesub", exit=1)

        def test_02_hardlink(self):
                """Verify that hardlink install fails as expected when
                hardlink target is missing."""

                self.image_create(self.rurl)

                # Hard link target is missing (failure expected).
                self.pkg("install hardlink", exit=1)

        def __populate_repo(self, unsupp_content=None):
                # Publish a package and then add some unsupported action data
                # to the repository's copy of the manifest and catalog.
                sfmri = self.pkgsend_bulk(self.rurl, self.unsupp10)[0]

                if unsupp_content is None:
                        # No manipulation required.
                        return

                pfmri = fmri.PkgFmri(sfmri)
                repo = self.get_repo(self.dcs[1].get_repodir())
                mpath = repo.manifest(pfmri)
                with open(mpath, "ab+") as mfile:
                        mfile.write(unsupp_content + "\n")

                mcontent = None
                with open(mpath, "rb") as mfile:
                        mcontent = mfile.read()

                cat = repo.get_catalog("test")
                cat.log_updates = False

                # Update the catalog signature.
                entry = cat.get_entry(pfmri)
                entry["signature-sha-1"] = manifest.Manifest.hash_create(
                    mcontent)

                # Update the catalog actions.
                dpart = cat.get_part("catalog.dependency.C", must_exist=True)
                entry = dpart.get_entry(pfmri)
                entry["actions"].append(unsupp_content)

                # Write out the new catalog.
                cat.save()

        def test_03_unsupported(self):
                """Verify that packages with invalid or unsupported actions are
                handled gracefully.
                """

                # Base package needed for tests.
                self.pkgsend_bulk(self.rurl, self.foo10)

                # Verify that a package with unsupported content doesn't cause
                # a problem.
                newact = "depend type=new-type fmri=foo@1.1"

                # Now create a new image and verify that pkg install will fail
                # for the unsupported package, but succeed for the supported
                # one.
                self.__populate_repo(newact)
                self.image_create(self.rurl)
                self.pkg("install foo@1.0")
                self.pkg("install unsupported@1.0", exit=1)
                self.pkg("uninstall foo")
                self.pkg("install foo@1.0 unsupported@1.0", exit=1)

                # Verify that a package with invalid content behaves the same.
                newact = "depend notvalid"
                self.__populate_repo(newact)
                self.pkg("refresh --full")
                self.pkg("install foo@1.0")
                self.pkg("install unsupported@1.0", exit=1)
                self.pkg("uninstall foo")

                # Now verify that if a newer version of the unsupported package
                # is found that is supported, it can be installed.
                self.__populate_repo()
                self.pkg("refresh --full")
                self.pkg("install foo@1.0 unsupported@1.0")
                self.pkg("uninstall foo unsupported")


if __name__ == "__main__":
        unittest.main()
