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
import pkg.catalog as catalog
import pkg.config as cfg
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.p5p as p5p
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
            add depend type=require-any fmri=leaf@1.0 fmri=branch@1.0
            close 
        """

        leaf10 = """
            open leaf@1.0,5.11-0
            close
        """

        branch10 = """
            open branch@1.0,5.11-0
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
                    depot2 is mapped to publisher test1 (alternate)
                    depot3 and depot4 are scratch depots"""

                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test1",
                    "test2", "test2"], start_depots=True)

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
                    (self.bronze20, self.tree10, self.branch10, self.leaf10, self.scheme10)))

                self.dpath2 = self.dcs[2].get_repodir()
                self.durl2 = self.dcs[2].get_depot_url()
                self.tempdir = tempfile.mkdtemp(dir=self.test_root)

                self.durl3 = self.dcs[3].get_depot_url()
                self.durl4 = self.dcs[4].get_depot_url()

        @staticmethod
        def get_repo(uri):
                parts = urlparse.urlparse(uri, "file", allow_fragments=0)
                path = urllib.url2pathname(parts[2])

                try:
                        return repo.Repository(root=path)
                except cfg.ConfigError, e:
                        raise repo.RepositoryError(_("The specified "
                            "repository's configuration data is not "
                            "valid:\n%s") % e)

        def test_0_opts(self):
                """Verify that various basic options work as expected and that
                invalid options or option values return expected exit code."""

                # Test that bad options return expected exit code.
                self.pkgrecv(command="--newest", exit=2)
                self.pkgrecv(self.durl1, "-!", exit=2)
                self.pkgrecv(self.durl1, "-p foo", exit=2)
                self.pkgrecv(self.durl1, "-d %s gold@1.0-1" % self.tempdir,
                    exit=1)
                self.pkgrecv(self.durl1, "-d %s invalid.fmri@1.0.a" %
                    self.tempdir, exit=1)

                # Test help.
                self.pkgrecv(command="-h", exit=0)

                # Verify that pkgrecv requires a destination repository.
                self.pkgrecv(self.durl1, "'*'", exit=2)

                # Verify that a non-existent repository results in failure.
                npath = os.path.join(self.test_root, "nochance")
                self.pkgrecv(self.durl1, "-d file://%s foo" % npath,  exit=1)

                # Test list newest.
                self.pkgrecv(self.durl1, "--newest")
                output = self.reduceSpaces(self.output)

                # The latest version of amber and bronze should be listed
                # (sans publisher prefix currently).
                amber = self.published[1]
                scheme = self.published[8]
                bronze = self.published[4]
                tree = self.published[5]
                branch = self.published[6]
                leaf = self.published[7]

                expected = "\n".join((amber, branch, bronze, leaf, scheme, tree)) + "\n"
                self.assertEqualDiff(expected, output)

        def test_1_recv_pkgsend(self):
                """Verify that a received package can be used by pkgsend."""

                f = fmri.PkgFmri(self.published[3], None)

                # First, retrieve the package.
                self.pkgrecv(self.durl1, "--raw -d %s %s" % (self.tempdir, f))

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
                self.pkgrecv(self.durl1, "--raw -k -d %s %s" % (self.tempdir,
                    f))

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
                self.wait_repo(self.dpath2)
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
                self.pkgrecv(self.durl1, "--raw -r -k -d %s %s" % (self.tempdir,
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
                self.pkgrecv(self.durl1, "--raw -m all-timestamps -r -k "
                    "-d %s %s" % (self.tempdir, "/bronze@2.0"))

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
                self.pkgrecv(self.durl1, "--raw -m all-timestamps -r -k "
                    "-d %s %s" % (self.tempdir, "bronze"))

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
                self.pkgrecv(self.durl1, "--raw -m all-versions -r -k "
                    "-d %s %s" % (self.tempdir, "bronze"))

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
                self.pkgrecv(command="--raw %s" % f)

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

        def test_6_recv_republish_preexisting(self):
                f = fmri.PkgFmri(self.published[5], None)
                f2 = fmri.PkgFmri(self.published[4], None)

                # First, pkgrecv tree into a file repository
                npath = tempfile.mkdtemp(dir=self.test_root)
                self.pkgsend("file://%s" % npath,
                    "create-repository --set-property publisher.prefix=test1")
                self.pkgrecv(self.durl1, "-d file://%s %s" % (npath, f))

                # Next, recursively pkgrecv bronze2.0 into a file repository
                # This would fail before behavior fixed to skip existing pkgs.
                self.pkgrecv(self.durl1, "-r -d file://%s %s" % (npath, f2))

        def test_7_recv_multipublisher(self):
                """Verify that pkgrecv handles multi-publisher repositories as
                expected."""

                # Setup a repository with packages from multiple publishers.
                amber = self.amber10.replace("open ", "open //test2/")
                self.pkgsend_bulk(self.durl3, amber)
                self.pkgrecv(self.durl1, "-d %s amber@1.0 bronze@1.0" %
                    self.durl3)

                # Now attempt to receive from a repository with packages from
                # multiple publishers and verify entry exists only for test1.
                self.pkgrecv(self.durl3, "-d %s bronze" % self.durl4)
                self.pkgrecv(self.durl3, "--newest")
                self.assertNotEqual(self.output.find("test1/bronze"), -1)
                self.assertEqual(self.output.find("test2/bronze"), -1)

                # Now retrieve amber, and verify entries exist for both pubs.
                self.wait_repo(self.dcs[4].get_repodir())
                self.wait_repo(self.dcs[3].get_repodir())
                self.pkgrecv(self.durl3, "-d %s amber" % self.durl4)
                self.pkgrecv(self.durl4, "--newest")
                self.assertNotEqual(self.output.find("test1/amber"), -1)
                self.assertNotEqual(self.output.find("test2/amber"), -1)

                # Verify attempting to retrieve a non-existent package fails
                # for a multi-publisher repository.
                self.pkgrecv(self.durl3, "-d %s nosuchpackage" % self.durl4,
                    exit=1)

        def test_8_archive(self):
                """Verify that pkgrecv handles package archives as expected."""

                # Setup a repository with packages from multiple publishers.
                amber = self.amber10.replace("open ", "open pkg://test2/")
                t2_amber10 = self.pkgsend_bulk(self.durl3, amber)[0]
                self.pkgrecv(self.durl1, "-d %s amber@1.0 bronze@1.0" %
                    self.durl3)

                # Now attempt to receive from a repository to a package archive.
                arc_path = os.path.join(self.test_root, "test.p5p")
                self.pkgrecv(self.durl3, "-a -d %s \*" % arc_path)

                #
                # Verify that the archive can be opened and the expected
                # packages are inside.
                #
                amber10 = self.published[0]
                bronze10 = self.published[2]
                arc = p5p.Archive(arc_path, mode="r")

                # Check for expected publishers.
                expected = set(["test1", "test2"])
                pubs = set(p.prefix for p in arc.get_publishers())
                self.assertEqualDiff(expected, pubs)

                # Check for expected package FMRIs.
                expected = set([amber10, t2_amber10, bronze10])
                tmpdir = tempfile.mkdtemp(dir=self.test_root)
                returned = []
                for pfx in pubs:
                        catdir = os.path.join(tmpdir, pfx)
                        os.mkdir(catdir)
                        for part in ("catalog.attrs", "catalog.base.C"):
                                arc.extract_catalog1(part, catdir, pfx)

                        cat = catalog.Catalog(meta_root=catdir, read_only=True)
                        returned.extend(str(f) for f in cat.fmris())
                self.assertEqualDiff(expected, set(returned))
                arc.close()
                shutil.rmtree(tmpdir)

                #
                # Verify that packages can be received from an archive to an
                # archive.
                #
                arc2_path = os.path.join(self.test_root, "test2.p5p")
                self.pkgrecv(arc_path, "-a -d %s pkg://test2/amber" % arc2_path)

                # Check for expected publishers.
                arc = p5p.Archive(arc2_path, mode="r")
                expected = set(["test2"])
                pubs = set(p.prefix for p in arc.get_publishers())
                self.assertEqualDiff(expected, pubs)

                # Check for expected package FMRIs.
                expected = set([t2_amber10])
                tmpdir = tempfile.mkdtemp(dir=self.test_root)
                returned = []
                for pfx in pubs:
                        catdir = os.path.join(tmpdir, pfx)
                        os.mkdir(catdir)
                        for part in ("catalog.attrs", "catalog.base.C"):
                                arc.extract_catalog1(part, catdir, pfx)

                        cat = catalog.Catalog(meta_root=catdir, read_only=True)
                        returned.extend(str(f) for f in cat.fmris())
                self.assertEqualDiff(expected, set(returned))
                arc.close()

                #
                # Verify that pkgrecv gracefully fails if archive already
                # exists.
                #
                self.pkgrecv(arc_path, "-d %s \*" % arc2_path, exit=1)

                #
                # Verify that packages can be received from an archive to
                # a repository.
                #
                self.pkgrecv(arc_path, "--newest")
                self.pkgrecv(arc_path, "-d %s pkg://test2/amber bronze" %
                    self.durl4)
                self.wait_repo(self.dcs[4].get_repodir())
                repo = self.dcs[4].get_repo()
                self.pkgrecv(repo.root, "--newest")

                # Check for expected publishers.
                expected = set(["test1", "test2"])
                pubs = repo.publishers
                self.assertEqualDiff(expected, pubs)

                # Check for expected package FMRIs.
                expected = sorted([t2_amber10, bronze10])
                returned = []
                for pfx in repo.publishers:
                        cat = repo.get_catalog(pub=pfx)
                        returned.extend(str(f) for f in cat.fmris())
                self.assertEqualDiff(expected, sorted(returned))


if __name__ == "__main__":
        unittest.main()
