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
import pkg.config as cfg
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.server.repository as repo
import shutil
import tempfile
import time
import urllib
import urlparse
import unittest
import zlib

class TestPkgrecvMulti(pkg5unittest.ManyDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False

        scheme10 = """
            open pkg:/scheme@1.0,5.11-0
            close 
        """

        tree10 = """
            open tree@1.0,5.11-0
            close 
        """

        amber10 = """
            open amber@1.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close 
        """

        amber20 = """
            open amber@2.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
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

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
            "tmp/bronze2", "tmp/copyright2", "tmp/copyright3", "tmp/libc.so.1",
            "tmp/sh"]

        def setUp(self):
                """ Start two depots.
                    depot 1 gets foo and moo, depot 2 gets foo and bar
                    depot1 is mapped to publisher test1 (preferred)
                    depot2 is mapped to publisher test1 (alternate) """

                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test1"],
                    start_depots=True)

                self.make_misc_files(self.misc_files)

                self.dpath1 = self.dcs[1].get_repodir()
                self.durl1 = self.dcs[1].get_depot_url()
                self.published = self.pkgsend_bulk(self.durl1, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20))

                # Purposefully republish bronze20 a second later so a version
                # exists that only differs in timestamp.  Also publish tree
                # and scheme after that.
                time.sleep(1)
                self.published.extend(self.pkgsend_bulk(self.durl1,
                    (self.bronze20, self.tree10, self.scheme10)))

                self.dpath2 = self.dcs[2].get_repodir()
                self.durl2 = self.dcs[2].get_depot_url()
                self.tempdir = tempfile.mkdtemp(dir=self.test_root)

        @staticmethod
        def get_repo(uri):
                parts = urlparse.urlparse(uri, "file", allow_fragments=0)
                path = urllib.url2pathname(parts[2])

                try:
                        return repo.Repository(auto_create=False,
                            fork_allowed=False, repo_root=path)
                except cfg.ConfigError, e:
                        raise repo.RepositoryError(_("The specified "
                            "repository's configuration data is not "
                            "valid:\n%s") % e)

        def test_0_opts(self):
                """Verify that various basic options work as expected and that
                invalid options or option values return expected exit code."""

                # Test that bad options return expected exit code.
                self.pkgrecv(command="-n", exit=2)
                self.pkgrecv(self.durl1, "-!", exit=2)
                self.pkgrecv(self.durl1, "-p foo", exit=2)
                self.pkgrecv(self.durl1, "-d %s gold@1.0-1" % self.tempdir,
                    exit=1)
                self.pkgrecv(self.durl1, "invalid.fmri@1.0.a", exit=1)

                # Test help.
                self.pkgrecv(command="-h", exit=0)

                # Verify that a non-existent repository results in failure.
                npath = os.path.join(self.test_root, "nochance")
                self.pkgrecv(self.durl1, "-d file://%s foo" % npath,  exit=1)

                # Test list newest.
                self.pkgrecv(self.durl1, "-n")
                output = self.reduceSpaces(self.output)

                # The latest version of amber and bronze should be listed
                # (sans publisher prefix currently).
                amber = self.published[1].replace("pkg://test1/", "pkg:/")
                scheme = self.published[6].replace("pkg://test1/", "pkg:/")
                bronze = self.published[4].replace("pkg://test1/", "pkg:/")
                tree = self.published[5].replace("pkg://test1/", "pkg:/")
                expected = "\n".join((amber, scheme, tree, bronze)) + "\n"
                self.assertEqualDiff(expected, output)

        def test_1_recv_pkgsend(self):
                """Verify that a received package can be used by pkgsend."""

                f = fmri.PkgFmri(self.published[3], None)

                # First, retrieve the package.
                self.pkgrecv(self.durl1, "-d %s %s" % (self.tempdir, f))

                # Next, load the manifest.
                basedir = os.path.join(self.tempdir, f.get_dir_path())
                mpath = os.path.join(basedir, "manifest")

                m = manifest.Manifest()
                raw = open(mpath, "rb").read()
                m.set_content(raw)

                # Verify that the files aren't compressed since -k wasn't used.
                # This is also the format pkgsend will expect for correct
                # republishing.
                ofile = file(os.devnull, "rb")
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                ifile = file(os.path.join(basedir, a.hash),
                                    "rb")

                                # Since the file shouldn't be compressed, this
                                # should return a zlib.error.
                                self.assertRaises(zlib.error,
                                    misc.gunzip_from_stream, ifile, ofile)

                # Next, send it to another depot
                self.pkgsend(self.durl2, "open foo@1.0-1")
                self.pkgsend(self.durl2,
                    "include -d %s %s" % (basedir, mpath))
                self.pkgsend(self.durl2, "close")

        def test_2_recv_compare(self):
                """Verify that a received package is identical to the
                original source."""

                f = fmri.PkgFmri(self.published[4], None)

                # First, pkgrecv the pkg to a directory.  The files are
                # kept compressed so they can be compared directly to the
                # repository's internal copy.
                self.pkgrecv(self.durl1, "-k -d %s %s" % (self.tempdir, f))

                # Next, compare the manifests.
                orepo = self.get_repo(self.dpath1)
                old = orepo.manifest(f)
                new = os.path.join(self.tempdir, f.get_dir_path(), "manifest")

                self.assertEqual(misc.get_data_digest(old),
                    misc.get_data_digest(new))

                # Next, load the manifest.
                m = manifest.Manifest()
                raw = open(new, "rb").read()
                m.set_content(raw)

                # Next, compare the package actions that have data.
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                old = orepo.file(a.hash)
                                new = os.path.join(self.tempdir,
                                    f.get_dir_path(), a.hash)
                                self.assertNotEqual(old, new)
                                self.assertEqual(misc.get_data_digest(old),
                                    misc.get_data_digest(new))

                # Second, pkgrecv to the pkg to a file repository.
                npath = tempfile.mkdtemp(dir=self.test_root)
                self.pkgsend("file://%s" % npath,
                    "create-repository --set-property publisher.prefix=test1")
                self.pkgrecv(self.durl1, "-d file://%s %s" % (npath, f))

                # Next, compare the manifests (this will also only succeed if
                # the fmris are exactly the same including timestamp).
                nrepo = self.get_repo(npath)
                old = orepo.manifest(f)
                new = nrepo.manifest(f)

                self.debug(old)
                self.debug(new)
                self.assertEqual(misc.get_data_digest(old),
                    misc.get_data_digest(new))

                # Next, load the manifest.
                m = manifest.Manifest()
                raw = open(new, "rb").read()
                m.set_content(raw)

                # Next, compare the package actions that have data.
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                old = orepo.file(a.hash)
                                new = nrepo.file(a.hash)
                                self.assertNotEqual(old, new)
                                self.assertEqual(misc.get_data_digest(old),
                                    misc.get_data_digest(new))

                # Third, pkgrecv to the pkg to a http repository from the
                # file repository from the last test.
                self.pkgrecv("file://%s" % npath, "-d %s %s" % (self.durl2, f))
                orepo = nrepo

                # Next, compare the manifests (this will also only succeed if
                # the fmris are exactly the same including timestamp).
                nrepo = self.get_repo(self.dpath2)
                old = orepo.manifest(f)
                new = nrepo.manifest(f)

                self.assertEqual(misc.get_data_digest(old),
                    misc.get_data_digest(new))

                # Next, load the manifest.
                m = manifest.Manifest()
                raw = open(new, "rb").read()
                m.set_content(raw)

                # Next, compare the package actions that have data.
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                old = orepo.file(a.hash)
                                new = nrepo.file(a.hash)
                                self.assertNotEqual(old, new)
                                self.assertEqual(misc.get_data_digest(old),
                                    misc.get_data_digest(new))

                # Fourth, create an image and verify that the sent package is
                # seen by the client.
                self.image_create(self.durl2, prefix="test1")
                self.pkg("info -r bronze@2.0")

                # Fifth, pkgrecv the pkg to a file repository and compare the
                # manifest of a package published with the scheme (pkg:/) given.
                f = fmri.PkgFmri(self.published[6], None)
                npath = tempfile.mkdtemp(dir=self.test_root)
                self.pkgsend("file://%s" % npath,
                    "create-repository --set-property publisher.prefix=test1")
                self.pkgrecv(self.durl1, "-d file://%s %s" % (npath, f))

                # Next, compare the manifests (this will also only succeed if
                # the fmris are exactly the same including timestamp).
                orepo = self.get_repo(self.dpath1)
                nrepo = self.get_repo(npath)
                old = orepo.manifest(f)
                new = nrepo.manifest(f)

                self.assertEqual(misc.get_data_digest(old),
                    misc.get_data_digest(new))

        def test_3_recursive(self):
                """Verify that retrieving a package recursively will retrieve
                its dependencies as well."""

                bronze = fmri.PkgFmri(self.published[4], None)

                # Retrieve bronze recursively to a directory, this should
                # also retrieve its dependency: amber, and amber's dependency:
                # tree.
                self.pkgrecv(self.durl1, "-r -k -d %s %s" % (self.tempdir,
                    bronze))

                amber = fmri.PkgFmri(self.published[1], None)
                tree = fmri.PkgFmri(self.published[5], None)

                # Verify that the manifests for each package was retrieved.
                for f in (amber, bronze, tree):
                        mpath = os.path.join(self.tempdir, f.get_dir_path(),
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

        def test_4_timever(self):
                """Verify that receiving with -m options work as expected."""

                bronze10 = fmri.PkgFmri(self.published[2], None)
                bronze20_1 = fmri.PkgFmri(self.published[3], None)
                bronze20_2 = fmri.PkgFmri(self.published[4], None)

                # Retrieve bronze using -m all-timestamps and a version pattern.
                # This should only retrieve bronze20_1 and bronze20_2.
                self.pkgrecv(self.durl1, "-m all-timestamps -r -k -d %s %s" % (
                    self.tempdir, "bronze@2.0"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze20_1.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

                # Cleanup for next test.
                shutil.rmtree(os.path.join(self.tempdir, "bronze"))

                # Retrieve bronze using -m all-timestamps and a package stem.
                # This should retrieve bronze10, bronze20_1, and bronze20_2.
                self.pkgrecv(self.durl1, "-m all-timestamps -r -k -d %s %s" % (
                    self.tempdir, "bronze"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze10.get_dir_path(),
                    bronze20_1.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

                # Cleanup for next test.
                shutil.rmtree(os.path.join(self.tempdir, "bronze"))

                # Retrieve bronze using -m all-versions, this should only
                # retrieve bronze10 and bronze20_2.
                self.pkgrecv(self.durl1, "-m all-versions -r -k -d %s %s" % (
                    self.tempdir, "bronze"))

                # Verify that only expected packages were retrieved.
                expected = [
                    bronze10.get_dir_path(),
                    bronze20_2.get_dir_path(),
                ]

                for d in os.listdir(os.path.join(self.tempdir, "bronze")):
                        self.assertTrue(os.path.join("bronze", d) in expected)

                        mpath = os.path.join(self.tempdir, "bronze", d,
                            "manifest")
                        self.assertTrue(os.path.isfile(mpath))

        def test_5_recv_env(self):
                """Verify that pkgrecv environment vars work as expected."""

                f = fmri.PkgFmri(self.published[3], None)

                os.environ["PKG_SRC"] = self.durl1
                os.environ["PKG_DEST"] = self.tempdir

                # First, retrieve the package.
                self.pkgrecv(command="%s" % f)

                # Next, load the manifest.
                basedir = os.path.join(self.tempdir, f.get_dir_path())
                mpath = os.path.join(basedir, "manifest")

                m = manifest.Manifest()
                raw = open(mpath, "rb").read()
                m.set_content(raw)

                # This is also the format pkgsend will expect for correct
                # republishing.
                ofile = file(os.devnull, "rb")
                for atype in ("file", "license"):
                        for a in m.gen_actions_by_type(atype):
                                if not hasattr(a, "hash"):
                                        continue

                                ifile = file(os.path.join(basedir, a.hash),
                                    "rb")

                                # Since the file shouldn't be compressed, this
                                # should return a zlib.error.
                                self.assertRaises(zlib.error,
                                    misc.gunzip_from_stream, ifile, ofile)

                for var in ("PKG_SRC", "PKG_DEST"):
                        del os.environ[var]


if __name__ == "__main__":
        unittest.main()
