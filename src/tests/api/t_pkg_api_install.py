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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import time
import sys
import unittest
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.portable as portable
import stat
import shutil
import urllib
import urlparse


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

        corepkgs = """
            open package/pkg@1.0,5.11-0
            close
            open package/pkg@2.0,5.11-0
            close
            open SUNWipkg@1.0,5.11-0
            close
            open SUNWipkg@2.0,5.11-0
            close
            open SUNWcs@1.0,5.11-0
            close
            open release/name@1.0,5.11-0
            close
            open release/name@2.0,5.11-0
            add set name=pkg.release.osname value=sunos
            close
        """

        carriage = """
            open carriage@1.0
            add depend type=require fmri=horse@1.0
            add depend type=exclude fmri=horse@2.0
            close
            open carriage@2.0
            add depend type=require fmri=horse@2.0
            close
            """

        horse = """
            open horse@1.0
            close
            open horse@2.0
            close """

        misc_files = [ "tmp/libc.so.1", "tmp/cat", "tmp/baz" ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        @staticmethod
        def __do_install(api_obj, fmris):
                api_obj.reset()
                for pd in api_obj.gen_plan_install(fmris):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __do_update(api_obj, fmris):
                api_obj.reset()
                for pd in api_obj.gen_plan_update(fmris):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __do_uninstall(api_obj, fmris):
                api_obj.reset()
                for pd in api_obj.gen_plan_uninstall(fmris):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()

        def test_basics_1(self):
                """ Send empty package foo@1.0, install and uninstall """

                self.pkgsend_bulk(self.rurl, self.foo10)
                api_obj = self.image_create(self.rurl)

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

                plist = self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11),
                    refresh_index=True)
                api_obj = self.image_create(self.rurl)

                self.pkg("list -a")
                self.__do_install(api_obj, ["foo"])

                # Check that manifest cache file exists after install.
                pfmri = fmri.PkgFmri(plist[1])
                mdir = self.get_img_manifest_cache_dir(pfmri)
                mcpath = os.path.join(mdir, "manifest.set")
                assert os.path.exists(mcpath)

                self.pkg("verify")
                self.pkg("list")

                self.pkg("search -l /lib/libc.so.1")
                self.pkg("search -r /lib/libc.so.1")
                self.pkg("search -l blah", exit=1)
                self.pkg("search -r blah", exit=1)

                # check to make sure timestamp was set to correct value
                libc_path = os.path.join(self.get_img_path(), "lib/libc.so.1")
                fstat = os.stat(libc_path)

                self.assert_(fstat[stat.ST_MTIME] == self.foo11_timestamp)

                # check that verify finds changes
                now = time.time()
                os.utime(libc_path, (now, now))
                self.pkg("verify", exit=1)

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])

                # Check that manifest cache file does not exist after uninstall.
                assert not os.path.exists(mcpath)

                self.pkg("verify")
                self.pkg("list -a")
                self.pkg("verify")

                # Install foo again, then remove manifest cache files and then
                # verify uninstall doesn't fail.
                api_obj.reset()
                self.__do_install(api_obj, ["foo"])
                pkg_dir = os.path.join(mdir, "..", "..")
                manifest.FactoredManifest.clear_cache(
                    api_obj.img.get_manifest_dir(pfmri))
                assert not os.path.exists(mcpath)
                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])

        def test_basics_3(self):
                """ Install foo@1.0, upgrade to foo@1.1, update foo@1.0,
                and then uninstall. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11))
                api_obj = self.image_create(self.rurl)

                self.__do_install(api_obj, ["foo@1.0"])

                self.pkg("list foo@1.0")
                self.pkg("list foo@1.1", exit=1)

                api_obj.reset()
                self.__do_install(api_obj, ["foo@1.1"])
                self.pkg("list foo@1.1")
                self.pkg("list foo@1.0", exit=1)
                self.pkg("list foo@1")
                self.pkg("verify")

                api_obj.reset()
                self.__do_update(api_obj, ["foo@1.0"])
                self.pkg("list foo@1.0")
                self.pkg("list foo@1.1", exit=1)
                self.pkg("verify")

                api_obj.reset()
                self.__do_update(api_obj, ["foo@1.1"])
                self.pkg("list foo@1.1")
                self.pkg("list foo@1.0", exit=1)
                self.pkg("verify")

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])
                self.pkg("list -a")
                self.pkg("verify")

        def test_basics_4(self):
                """ Add bar@1.0, dependent on foo@1.0, install, uninstall. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11,
                    self.bar10))
                api_obj = self.image_create(self.rurl)

                self.pkg("list -a")
                api_obj.reset()
                self.__do_install(api_obj, ["bar@1.0"])

                self.pkg("list")
                self.pkg("verify")
                api_obj.reset()
                self.__do_uninstall(api_obj, ["bar", "foo"])

                # foo and bar should not be installed at this point
                self.pkg("list bar", exit=1)
                self.pkg("list foo", exit=1)
                self.pkg("verify")

        def test_update_backwards(self):
                """ Publish horse and carriage, verify update won't downgrade
                packages not specified for operation. """

                self.pkgsend_bulk(self.rurl, (self.carriage, self.horse))
                api_obj = self.image_create(self.rurl)

                self.__do_install(api_obj, ["carriage@2"])

                # Attempting to update carriage should result in nothing to do.
                api_obj.reset()
                for pd in api_obj.gen_plan_update(["carriage"]):
                        continue
                self.assertTrue(api_obj.planned_nothingtodo())

                # Downgrading to carriage@1.0 would force a downgrade to
                # horse@1.0 and so should raise an exception...
                api_obj.reset()
                self.assertRaises(api_errors.PlanCreationException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)),
                    ["carriage@1"])

                api_obj.reset()
                self.assertRaises(api_errors.PlanCreationException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)),
                    ["carriage@1", "horse"])

                # ...unless horse is explicitly downgraded as well.
                api_obj.reset()
                self.__do_update(api_obj, ["carriage@1", "horse@1"])
                self.pkg("list carriage@1 horse@1")

                # Update carriage again.
                self.__do_update(api_obj, ["carriage"])
                self.pkg("list carriage@2 horse@2")

                # Publish a new version of carriage.
                self.pkgsend_bulk(self.rurl, """
                    open carriage@3.0
                    add depend type=require fmri=horse@1.0
                    add depend type=exclude fmri=horse@2.0
                    close """)
                api_obj.reset()
                api_obj.refresh()

                # Upgrading implicitly to carriage@3.0 would force a downgrade
                # to horse@1.0 so should be ignored as a possibility by
                # the solver.
                api_obj.reset()
                for pd in api_obj.gen_plan_update(["carriage"]):
                        continue
                self.assertTrue(api_obj.planned_nothingtodo())

                # Upgrading explicitly to carriage@3.0 would force a downgrade
                # to horse@1.0 and so should raise an exception...
                api_obj.reset()
                self.assertRaises(api_errors.PlanCreationException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)),
                    ["carriage@3", "horse"])

                # ...unless horse is explicitly downgraded as well.
                api_obj.reset()
                self.__do_update(api_obj, ["carriage@3", "horse@1"])
                self.pkg("list carriage@3 horse@1")

                # Now verify an implicit update to carriage@3.0 will work
                # if horse is explicitly downgraded to 1.0.
                api_obj.reset()
                self.__do_update(api_obj, ["carriage@2", "horse@2"])
                self.pkg("list carriage@2 horse@2")

                api_obj.reset()
                self.__do_update(api_obj, ["carriage", "horse@1"])
                self.pkg("list carriage@3 horse@1")

        def test_multi_publisher(self):
                """ Verify that package install works as expected when multiple
                publishers share the same repository. """

                # Publish a package for 'test'.
                self.pkgsend_bulk(self.rurl, self.bar10)

                # Now change the default publisher to 'test2' and publish
                # another package.
                self.pkgrepo("set -s %s publisher/prefix=test2" % self.rurl)
                self.pkgsend_bulk(self.rurl, self.foo10)

                # Finally, create an image and verify that packages from
                # both publishers may be installed.
                api_obj = self.image_create(self.rurl, prefix=None)
                self.__do_install(api_obj, ["pkg://test/bar@1.0",
                    "pkg://test2/foo@1.0"])

        def test_pkg_file_errors(self):
                """ Verify that package install and uninstall works as expected
                when files or directories are missing. """

                self.pkgsend_bulk(self.rurl, (self.bar09, self.bar10,
                    self.bar11, self.foo10, self.foo12, self.moving10,
                    self.moving20))
                api_obj = self.image_create(self.rurl)

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
                """ Send package bar@1.1, dependent on foo@1.2.  Install
                    bar@1.0.  List all packages.  Upgrade image. """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11,
                    self.bar10))
                api_obj = self.image_create(self.rurl)

                self.__do_install(api_obj, ["bar@1.0"])

                self.pkgsend_bulk(self.rurl, (self.foo12, self.bar11))

                self.pkg("contents -H")
                self.pkg("list")
                api_obj.refresh(immediate=True)

                self.pkg("list")
                self.pkg("verify")
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue
                api_obj.prepare()
                api_obj.execute_plan()
                self.pkg("verify")

                self.pkg("list foo@1.2")
                self.pkg("list bar@1.1")

                api_obj.reset()
                self.__do_uninstall(api_obj, ["bar", "foo"])
                self.pkg("verify")

        def test_ipkg_out_of_date(self):
                """Make sure that packaging system out-of-date testing works."""

                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo12,
                    self.corepkgs))
                self.image_create(self.rurl)

                api_obj = self.get_img_api_obj()

                # Update when it doesn't appear to be an opensolaris image
                # shouldn't have any issues.
                self.__do_install(api_obj, ["foo@1.0"])
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

                # Even though SUNWipkg is on the system, it won't appear as an
                # opensolaris system.
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj, ["foo@1.0", "SUNWipkg@1.0"])
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

                # Same for package/pkg
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj, ["foo@1.0", "package/pkg@1.0"])
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

                # Same for SUNWcs
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj, ["foo@1.0", "SUNWcs"])
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

                # There are still no problems if the packaging system is up to
                # date.  We can't test with SUNWipkg installed instead, because
                # we're making the assumption in the code that we always want to
                # update package/pkg, given that this revision of the code will
                # only run on systems where the packaging system is in that
                # package.
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj, ["foo@1.0", "SUNWcs", "package/pkg@2.0"])
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

                # We should run into a problem if pkg(5) is out of date.
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj,
                    ["foo@1.0", "SUNWcs", "package/pkg@1.0"])
                api_obj.reset()
                self.assertRaises(api_errors.IpkgOutOfDateException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)))

                # Use the metadata on release/name to determine it's an
                # opensolaris system.
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj,
                    ["foo@1.0", "release/name@2.0", "package/pkg@1.0"])
                api_obj.reset()
                self.assertRaises(api_errors.IpkgOutOfDateException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)))

                # An older release/name which doesn't have the metadata should
                # cause us to skip the check.
                api_obj.reset()
                self.__do_uninstall(api_obj, ["*"])
                api_obj.reset()
                self.__do_install(api_obj,
                    ["foo@1.0", "release/name@1.0", "package/pkg@1.0"])
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

                # Verify that if the installed version of pkg is from an
                # unconfigured publisher and is newer than what is available
                # that the update check will not fail.

                # First, install package/pkg again.
                self.__do_install(api_obj,
                    ["foo@1.0", "SUNWcs", "package/pkg@2.0"])

                # Next, create a repository with an older version of pkg,
                # and a newer version of foo.
                new_repo_dir = os.path.join(self.test_root, "test2")
                new_repo_uri = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(new_repo_dir), "", "", ""))

                self.create_repo(new_repo_dir,
                    properties={ "publisher": { "prefix": "test2" } })
                self.pkgsend_bulk(new_repo_uri, ("""
                    open package/pkg@1.0,5.11-0
                    close""", self.foo11))

                # Now add the new publisher and remove the old one.
                api_obj.reset()
                npub = publisher.Publisher("test2",
                    repository=publisher.Repository(origins=[new_repo_uri]))
                api_obj.add_publisher(npub, search_first=True)
                api_obj.reset()
                api_obj.remove_publisher(prefix="test")

                # Now verify that plan_update succeeds still since the
                # version of pkg installed is newer than the versions that
                # are offered by the current publishers.
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue

        def test_basics_5(self):
                """ Add bar@1.1, install bar@1.0. """

                self.pkgsend_bulk(self.rurl, self.xbar11)
                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["xbar@1.0"])

        def test_bug_1338(self):
                """ Add bar@1.1, dependent on foo@1.2, install bar@1.1. """

                self.pkgsend_bulk(self.rurl, self.bar11)
                api_obj = self.image_create(self.rurl)

                self.pkg("list -a")

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["bar@1.1"])

        def test_bug_1338_2(self):
                """ Add bar@1.1, dependent on foo@1.2, and baz@1.0, dependent
                    on foo@1.0, install baz@1.0 and bar@1.1. """

                self.pkgsend_bulk(self.rurl, (self.bar11, self.baz10))
                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["baz@1.0", "bar@1.1"])

        def test_bug_1338_3(self):
                """ Add xdeep@1.0, xbar@1.0. xDeep@1.0 depends on xbar@1.0 which
                    depends on xfoo@1.0, install xdeep@1.0. """

                self.pkgsend_bulk(self.rurl, (self.xbar10, self.xdeep10))
                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["xdeep@1.0"])

        def test_bug_1338_4(self):
                """ Add ydeep@1.0. yDeep@1.0 depends on ybar@1.0 which depends
                on xfoo@1.0, install ydeep@1.0. """

                self.pkgsend_bulk(self.rurl, self.ydeep10)
                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["ydeep@1.0"])

        def test_bug_2795(self):
                """ Try to install two versions of the same package """

                self.pkgsend_bulk(self.rurl, (self.foo11, self.foo12))
                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["foo@1.1", "foo@1.2"])

                self.pkg("list foo", exit=1)

                self.assertRaises(api_errors.PlanCreationException,
                    self.__do_install, api_obj, ["foo@1.1", "foo@1.2"])

                self.pkg("list foo", exit=1)

        def test_install_matching(self):
                """ Try to [un]install packages matching a pattern """

                self.pkgsend_bulk(self.rurl, (self.foo10, self.bar10,
                    self.baz10))
                api_obj = self.image_create(self.rurl)

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

                api_obj = self.image_create(self.rurl)

                def check_unfound(e):
                        return e.unmatched_fmris

                def check_illegal(e):
                        return e.illegal

                def check_missing(e):
                        return e.missing_matches

                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_unfound,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_install(*args, **kwargs)),
                    ["foo"])

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_uninstall(*args, **kwargs)),
                    ["foo"], False)

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_install(*args, **kwargs)),
                    ["@/foo"])

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_uninstall(*args, **kwargs)),
                    ["_foo"], False)

                self.pkgsend_bulk(self.rurl, self.foo10)

                api_obj.refresh(False)
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_uninstall(*args, **kwargs)),
                    ["foo"], False)

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_uninstall(*args, **kwargs)),
                    ["_foo"], False)

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)),
                    ["foo"])

                api_obj.reset()
                api_obj.refresh(True)
                self.__do_install(api_obj, ["foo"])

                # Verify update plan has nothing to do result for installed
                # package that can't be updated.
                api_obj.reset()
                for pd in api_obj.gen_plan_update(["foo"]):
                        continue
                self.assertTrue(api_obj.planned_nothingtodo())

                self.__do_uninstall(api_obj, ["foo"])

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_missing,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_uninstall(*args, **kwargs)),
                    ["foo"], False)

        def test_bug_4109(self):

                api_obj = self.image_create(self.rurl)

                def check_illegal(e):
                        return e.illegal

                api_obj.reset()
                pkg5unittest.eval_assert_raises(api_errors.PlanCreationException,
                    check_illegal,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_install(*args, **kwargs)),
                    ["_foo"])

        def test_catalog_v0(self):
                """Test install from a publisher's repository that only supports
                catalog v0, and then the transition from v0 to v1."""

                # Actual depot required for this test due to v0 repository
                # operation usage.
                self.dc.set_disable_ops(["catalog/1"])
                self.dc.start()

                self.pkgsend_bulk(self.durl, self.foo10)
                api_obj = self.image_create(self.durl)

                self.__do_install(api_obj, ["foo"])

                api_obj.reset()
                self.__do_uninstall(api_obj, ["foo"])

                api_obj.reset()
                self.__do_install(api_obj, ["pkg://test/foo"])

                self.pkgsend_bulk(self.durl, self.bar10)
                self.dc.stop()
                self.dc.unset_disable_ops()
                self.dc.start()

                api_obj.reset()
                api_obj.refresh(immediate=True)

                api_obj.reset()
                self.__do_install(api_obj, ["pkg://test/bar@1.0"])
                self.dc.stop()

        def test_bad_package_actions(self):
                """Test the install of packages that have actions that are
                invalid."""

                # XXX This test is not yet comprehensive.

                # First, publish the package that will be corrupted and create
                # an image for testing.
                plist = self.pkgsend_bulk(self.rurl, (self.badfile10,
                    self.baddir10))
                api_obj = self.image_create(self.rurl)

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

        def test_freeze_basics_1(self):
                """Test that installing a package which has been frozen at a
                particular version works, that installing a version which
                doesn't match fails, that upgrading doesn't move the package
                forward, and that unfreezing a package lets it move once more.
                """

                plist = self.pkgsend_bulk(self.rurl, [self.foo10, self.foo11,
                    self.foo12])
                api_obj = self.image_create(self.rurl)

                api_obj.freeze_pkgs(["foo@1.1"])
                api_obj.reset()
                self.assertRaises(api_errors.PlanCreationException,
                    self._api_install, api_obj, ["foo@1.0"])
                self.assertRaises(api_errors.PlanCreationException,
                    self._api_install, api_obj, ["foo@1.2"])
                self._api_install(api_obj, ["foo"])

                # Test that update won't move foo to 1.2 until it's unfrozen.
                self.pkg("update", exit=4)
                self.pkg("update foo@1.2", exit=1)
                api_obj.freeze_pkgs(["foo"], unfreeze=True)
                self.pkg("update -n")
                self._api_update(api_obj, ["foo@1.2"])

                # Check that freezing an installed package at a different
                # version fails.
                self.assertRaises(api_errors.FreezePkgsException,
                    api_obj.freeze_pkgs, ["foo@1.1"])
                api_obj.reset()

                # Check that freeze survives uninstalls.
                self._api_uninstall(api_obj, ["foo"])
                api_obj.freeze_pkgs(["foo@1.1"])
                api_obj.reset()
                self._api_install(api_obj, ["foo"])
                self.pkg("list foo@1.2", exit=1)
                self.pkg("list foo@1.1")
                self._api_uninstall(api_obj, ["foo"])
                self._api_install(api_obj, ["foo"])
                self.pkg("list foo@1.2", exit=1)
                self.pkg("list foo@1.1")

                # Check that freeze only freezes what it should.
                api_obj.freeze_pkgs(["foo@1"])
                api_obj.reset()
                self._api_update(api_obj, [])
                self.pkg("list foo@1.1", exit=1)
                self.pkg("list foo@1.2")


class TestActionExecutionErrors(pkg5unittest.SingleDepotTestCase):
        """This set of tests is intended to verify that the client API will
        handle image state errors gracefully during install or uninstall
        operations."""

        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        dir10 = """
            open dir@1.0,5.11-0
            add dir path=dir mode=755 owner=root group=bin
            close """

        file10 = """
            open file@1.0,5.11-0
            add file tmp/file path=file mode=755 owner=root group=bin
            close """

        # Purposefully omits depend on dir@1.0.
        filesub10 = """
            open filesub@1.0,5.11-0
            add file tmp/file path=dir/file mode=755 owner=root group=bin
            close """

        # Purposefully omits depend on dir@1.0.
        link10 = """
            open link@1.0,5.11-0
            add link path=link target=dir
            close """

        link20 = """
            open link@2.0,5.11-0
            add depend type=require fmri=file@1.0,5.11-0
            add link path=dir/link target=file
            close """

        # Purposefully omits depend on file@1.0.
        hardlink10 = """
            open hardlink@1.0,5.11-0
            add hardlink path=hardlink target=file
            close """

        # Purposefully omits depend on dir@1.0.
        hardlink20 = """
            open hardlink@2.0,5.11-0
            add depend type=require fmri=file@1.0,5.11-0
            add hardlink path=dir/hardlink target=file
            close """

        misc_files = ["tmp/file"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                plist = self.pkgsend_bulk(self.rurl, (self.dir10, self.file10,
                    self.filesub10, self.link10, self.link20, self.hardlink10,
                    self.hardlink20))

                self.plist = {}
                for p in plist:
                        pfmri = fmri.PkgFmri(p, "5.11")
                        self.plist.setdefault(pfmri.pkg_name, []).append(pfmri)

        @staticmethod
        def __do_install(api_obj, fmris):
                fmris = [str(f) for f in fmris]
                api_obj.reset()
                for pd in api_obj.gen_plan_install(fmris):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __do_verify(api_obj, pfmri):
                img = api_obj.img
                progtrack = progress.NullProgressTracker()
                for act, errors, warnings, pinfo in img.verify(pfmri, progtrack,
                    forever=True):
                        raise AssertionError("Action %s in package %s failed "
                            "verification: %s, %s" % (act, pfmri, errors,
                            warnings))

        @staticmethod
        def __do_uninstall(api_obj, fmris):
                fmris = [str(f) for f in fmris]
                api_obj.reset()
                for pd in api_obj.gen_plan_uninstall(fmris):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()

        @staticmethod
        def __write_empty_file(target, mode=misc.PKG_FILE_MODE, owner="root",
            group="bin"):
                f = open(target, "wb")
                f.write("\n")
                f.close()
                os.chmod(target, mode)
                owner = portable.get_user_by_name(owner, "/", True)
                group = portable.get_group_by_name(group, "/", True)
                os.chown(target, owner, group)

        def test_00_directory(self):
                """Verify that directory install and removal works as expected
                when directory is already present before install or has been
                replaced with a file or link during install or removal."""

                api_obj = self.image_create(self.rurl)

                # The dest_dir's installed path.
                dest_dir_name = "dir"
                dir10_pfmri = self.plist[dest_dir_name][0]
                dest_dir = os.path.join(self.get_img_path(), dest_dir_name)

                # First, verify that install won't fail if the dest_dir already
                # exists, and that it will set the correct owner, group, and
                # mode for the dest_dir even though it already exists and has
                # the wrong mode.
                os.mkdir(dest_dir, misc.PKG_FILE_MODE) # Intentionally wrong.
                os.chown(dest_dir, 0, 0)
                self.__do_install(api_obj, [dir10_pfmri])
                self.__do_verify(api_obj, dir10_pfmri)

                self.__do_uninstall(api_obj, [dir10_pfmri])

                # Next, verify that install and uninstall won't fail if the
                # dest_dir exists, but not as the expected type.  Also check
                # that the correct mode, owner, group, etc. is set for the
                # dest_dir.

                # Directory replaced with a file.
                self.__write_empty_file(dest_dir)
                self.__do_install(api_obj, [dir10_pfmri])
                self.__do_verify(api_obj, dir10_pfmri)

                shutil.rmtree(dest_dir)
                self.__write_empty_file(dest_dir)
                self.__do_uninstall(api_obj, [dir10_pfmri])

                # Directory replaced with a link (fails for install).
                self.__write_empty_file(dest_dir + ".src")
                os.symlink(dest_dir + ".src", dest_dir)
                self.assertRaises(api_errors.ActionExecutionError,
                    self.__do_install, api_obj, [dir10_pfmri])
                os.unlink(dest_dir)

                # Directory replaced with a link (succeeds for uninstall).
                self.__do_install(api_obj, [dir10_pfmri])
                shutil.rmtree(dest_dir)
                os.symlink(dest_dir + ".src", dest_dir)
                self.__do_uninstall(api_obj, [dir10_pfmri])
                os.unlink(dest_dir + ".src")

        def test_01_file(self):
                """Verify that file install and removal works as expected when
                file is: already present before install, has been replaced
                with a directory or link during install or removal, or an
                install is attempted when its parent directory has been
                replaced with a link."""

                api_obj = self.image_create(self.rurl)

                # The dest_file's installed path.
                dest_file_name = "file"
                file10_pfmri = self.plist[dest_file_name][0]
                dest_file = os.path.join(self.get_img_path(), dest_file_name)
                src = os.path.join(self.get_img_path(), "dir")

                # First, verify that install won't fail if the dest_file already
                # exists, and that it will set the correct owner, group, and
                # mode for the dest_file even though it already exists.
                self.__write_empty_file(dest_file, mode=misc.PKG_DIR_MODE,
                    owner="root", group="root")
                self.__do_install(api_obj, [file10_pfmri])
                self.__do_verify(api_obj, file10_pfmri)
                self.__do_uninstall(api_obj, [file10_pfmri])

                # Next, verify that install and uninstall won't fail if the
                # dest_file exists, but not as the expected type.  Also check
                # that the correct mode, owner, group, etc. is set for the
                # dest_file.

                # File replaced with a directory.
                os.mkdir(dest_file, misc.PKG_FILE_MODE) # Intentionally wrong.
                self.__do_install(api_obj, [file10_pfmri])
                self.__do_verify(api_obj, file10_pfmri)

                os.unlink(dest_file)
                os.mkdir(dest_file, misc.PKG_FILE_MODE) # Intentionally wrong.
                self.__do_uninstall(api_obj, [file10_pfmri])

                # File replaced with a non-empty directory.
                os.mkdir(dest_file, misc.PKG_FILE_MODE) # Intentionally wrong.
                open(os.path.join(dest_file, "foobar"), "wb").close()
                self.assert_(os.path.isfile(os.path.join(dest_file, "foobar")))
                self.__do_install(api_obj, [file10_pfmri])
                self.__do_verify(api_obj, file10_pfmri)

                os.unlink(dest_file)
                os.mkdir(dest_file, misc.PKG_FILE_MODE) # Intentionally wrong.
                open(os.path.join(dest_file, "foobar"), "wb").close()
                self.assert_(os.path.exists(os.path.join(dest_file, "foobar")))
                self.__do_uninstall(api_obj, [file10_pfmri])

                # File replaced with a link.
                self.__do_install(api_obj, ["dir"])
                os.symlink(src, dest_file)
                self.__do_install(api_obj, [file10_pfmri])
                self.__do_verify(api_obj, file10_pfmri)

                os.unlink(dest_file)
                os.symlink(src, dest_file)
                self.__do_uninstall(api_obj, [file10_pfmri])

                # File's parent directory replaced with a link.
                filesub10_pfmri = self.plist["filesub"][0]
                os.mkdir(os.path.join(self.get_img_path(), "export"))
                new_src = os.path.join(os.path.dirname(src), "export", "dir")
                shutil.move(src, os.path.dirname(new_src))
                os.symlink(new_src, src)
                self.assertRaises(api_errors.ActionExecutionError,
                    self.__do_install, api_obj, [filesub10_pfmri])

        def test_02_link(self):
                """Verify that link install and removal works as expected when
                link is already present before install or has been replaced
                with a directory or file during install or removal."""

                api_obj = self.image_create(self.rurl)

                # The dest_link's installed path.
                dest_link_name = "link"
                link10_pfmri = self.plist[dest_link_name][0]
                link20_pfmri = self.plist[dest_link_name][1]
                dest_link = os.path.join(self.get_img_path(), dest_link_name)

                # First, verify that install won't fail if the dest_link already
                # exists.
                self.__do_install(api_obj, ["dir"])
                os.symlink("dir", dest_link)
                self.__do_install(api_obj, [link10_pfmri])
                self.__do_verify(api_obj, link10_pfmri)
                self.__do_uninstall(api_obj, [link10_pfmri])

                # Next, verify that install and uninstall won't fail if the
                # dest_link exists, but not as the expected type.  Also check
                # that the correct mode, owner, group, etc. is set for the
                # dest_link.

                # Link replaced with a directory.
                os.mkdir(dest_link, misc.PKG_FILE_MODE) # Intentionally wrong.
                self.__do_install(api_obj, [link10_pfmri])
                self.__do_verify(api_obj, link10_pfmri)

                os.unlink(dest_link)
                os.mkdir(dest_link, misc.PKG_FILE_MODE) # Intentionally wrong.
                self.__do_uninstall(api_obj, [link10_pfmri])

                # Link replaced with a non-empty directory.
                os.mkdir(dest_link, misc.PKG_FILE_MODE) # Intentionally wrong.
                open(os.path.join(dest_link, "foobar"), "wb").close()
                self.assert_(os.path.isfile(os.path.join(dest_link, "foobar")))
                self.__do_install(api_obj, [link10_pfmri])
                self.__do_verify(api_obj, link10_pfmri)

                os.unlink(dest_link)
                os.mkdir(dest_link, misc.PKG_FILE_MODE) # Intentionally wrong.
                open(os.path.join(dest_link, "foobar"), "wb").close()
                self.assert_(os.path.exists(os.path.join(dest_link, "foobar")))
                self.__do_uninstall(api_obj, [link10_pfmri])

                # Link replaced with a file.
                self.__write_empty_file(dest_link)
                self.__do_install(api_obj, [link10_pfmri])
                self.__do_verify(api_obj, link10_pfmri)

                os.unlink(dest_link)
                self.__write_empty_file(dest_link)
                self.__do_uninstall(api_obj, [link10_pfmri])

                # Link's parent directory replaced with a link.
                os.mkdir(os.path.join(self.get_img_path(), "export"))
                src = os.path.join(self.get_img_path(), "dir")
                new_src = os.path.join(os.path.dirname(src), "export", "dir")
                self.__do_install(api_obj, ["dir"])
                shutil.move(src, os.path.dirname(new_src))
                os.symlink(new_src, src)
                self.assertRaises(api_errors.ActionExecutionError,
                    self.__do_install, api_obj, [link20_pfmri])

        def test_03_hardlink(self):
                """Verify that hard link install and removal works as expected
                when the link is already present before install or has been
                replaced with a directory or link during install or removal."""

                api_obj = self.image_create(self.rurl)

                # The dest_hlink's installed path.
                dest_hlink_name = "hardlink"
                hlink10_pfmri = self.plist[dest_hlink_name][0]
                hlink20_pfmri = self.plist[dest_hlink_name][1]
                dest_hlink = os.path.join(self.get_img_path(), dest_hlink_name)
                src = os.path.join(self.get_img_path(), "file")

                # First, verify that install won't fail if the dest_hlink
                # already exists, and that it will set the correct owner, group,
                # and mode for the dest_hlink even though it already exists.
                self.__do_install(api_obj, ["file"])
                os.link(src, dest_hlink)
                self.__do_install(api_obj, [hlink10_pfmri])
                self.__do_verify(api_obj, hlink10_pfmri)
                self.__do_uninstall(api_obj, [hlink10_pfmri])

                # Next, verify that install and uninstall won't fail if the
                # dest_hlink exists, but not as the expected type.  Also check
                # that the correct mode, owner, group, etc. is set for the
                # dest_hlink.

                # Hard link replaced with a directory.
                os.mkdir(dest_hlink, misc.PKG_FILE_MODE) # Intentionally wrong.
                self.__do_install(api_obj, [hlink10_pfmri])
                self.__do_verify(api_obj, hlink10_pfmri)

                os.unlink(dest_hlink)
                os.mkdir(dest_hlink, misc.PKG_FILE_MODE) # Intentionally wrong.
                self.__do_uninstall(api_obj, [hlink10_pfmri])

                # Hard link replaced with a non-empty directory.
                os.mkdir(dest_hlink, misc.PKG_FILE_MODE) # Intentionally wrong.
                open(os.path.join(dest_hlink, "foobar"), "wb").close()
                self.assert_(os.path.isfile(os.path.join(dest_hlink, "foobar")))
                self.__do_install(api_obj, [hlink10_pfmri])
                self.__do_verify(api_obj, hlink10_pfmri)

                os.unlink(dest_hlink)
                os.mkdir(dest_hlink, misc.PKG_FILE_MODE) # Intentionally wrong.
                open(os.path.join(dest_hlink, "foobar"), "wb").close()
                self.assert_(os.path.exists(os.path.join(dest_hlink, "foobar")))
                self.__do_uninstall(api_obj, [hlink10_pfmri])

                # Hard link replaced with a link.
                os.symlink(src, dest_hlink)
                self.__do_install(api_obj, [hlink10_pfmri])
                self.__do_verify(api_obj, hlink10_pfmri)

                os.unlink(dest_hlink)
                os.symlink(src, dest_hlink)
                self.__do_uninstall(api_obj, [hlink10_pfmri])

                # Hard link target is missing (failure expected).
                self.__do_uninstall(api_obj, ["file"])
                self.assertRaises(api_errors.ActionExecutionError,
                    self.__do_install, api_obj, [hlink10_pfmri])

                # Hard link's parent directory replaced with a link.
                os.mkdir(os.path.join(self.get_img_path(), "export"))
                src = os.path.join(self.get_img_path(), "dir")
                new_src = os.path.join(os.path.dirname(src), "export", "dir")
                self.__do_install(api_obj, ["dir"])
                shutil.move(src, os.path.dirname(new_src))
                os.symlink(new_src, src)
                self.assertRaises(api_errors.ActionExecutionError,
                    self.__do_install, api_obj, [hlink20_pfmri])


if __name__ == "__main__":
        unittest.main()
