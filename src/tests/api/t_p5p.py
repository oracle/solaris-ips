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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import difflib
import errno
import unittest
import os
import pkg.catalog
import pkg.client.progress
import pkg.fmri
import pkg.misc
import pkg.p5p
import pkg.pkgtarfile as ptf
import pkg.portable as portable
import shutil
import sys
import tarfile as tf
import tempfile


class TestP5P(pkg5unittest.SingleDepotTestCase):
        """Class to test the functionality of the pkg.p5p module."""

        # Don't recreate repository and publish packages for every test.
        persistent_setup = True
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        pkgs = """
            open pkg://test/foo@1.0
            add set name=pkg.summary value="Example package foo."
            add dir mode=0755 owner=root group=bin path=lib
            add dir mode=0755 owner=root group=bin path=usr
            add dir mode=0755 owner=root group=bin path=usr/bin
            add dir mode=0755 owner=root group=bin path=usr/local
            add dir mode=0755 owner=root group=bin path=usr/local/bin
            add dir mode=0755 owner=root group=bin path=usr/share
            add dir mode=0755 owner=root group=bin path=usr/share/doc
            add dir mode=0755 owner=root group=bin path=usr/share/doc/foo
            add dir mode=0755 owner=root group=bin path=usr/share/man
            add dir mode=0755 owner=root group=bin path=usr/share/man/man1
            add file tmp/foo mode=0755 owner=root group=bin path=usr/bin/foo
            add file tmp/libfoo.so.1 mode=0755 owner=root group=bin path=lib/libfoo.so.1
            add file tmp/foo.1 mode=0444 owner=root group=bin path=usr/share/man/man1/foo.1
            add file tmp/README mode=0444 owner=root group=bin path=/usr/share/doc/foo/README
            add link path=usr/local/bin/soft-foo target=usr/bin/foo
            add hardlink path=usr/local/bin/hard-foo target=/usr/bin/foo
            close
            open pkg://test/signed@1.0
            add dir mode=0755 owner=root group=bin path=usr/bin
            add set name=authorized.species value=bobcat
            close
            open pkg://test2/quux@1.0
            add set name=pkg.summary value="Example package quux."
            add dir mode=0755 owner=root group=bin path=usr
            add dir mode=0755 owner=root group=bin path=usr/bin
            add file tmp/quux mode=0755 owner=root group=bin path=usr/bin/quux
            close """

        misc_files = ["tmp/foo", "tmp/libfoo.so.1", "tmp/foo.1", "tmp/README",
            "tmp/LICENSE", "tmp/quux"]

        def seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, basestring):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assert_(dest_dir)
                self.assert_(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "%s_cert.pem" % c
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))

        def image_create(self, *args, **kwargs):
                pkg5unittest.SingleDepotTestCase.image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

                # Setup base test paths.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")
                self.ta_dir = None

                # Publish packages needed for tests.
                plist = self.pkgsend_bulk(self.rurl, self.pkgs)

                # Stash published package FMRIs away for easy access by tests.
                self.foo = pkg.fmri.PkgFmri(plist[0])
                self.signed = pkg.fmri.PkgFmri(plist[1])
                self.quux = pkg.fmri.PkgFmri(plist[2])

                # Sign the 'signed' package.
                r = self.get_repo(self.dcs[1].get_repodir())
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s -i %(i6)s %(pkg)s" % {
                    "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                    "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                    "i1": os.path.join(self.chain_certs_dir,
                        "ch1_ta1_cert.pem"),
                    "i2": os.path.join(self.chain_certs_dir,
                        "ch2_ta1_cert.pem"),
                    "i3": os.path.join(self.chain_certs_dir,
                        "ch3_ta1_cert.pem"),
                    "i4": os.path.join(self.chain_certs_dir,
                        "ch4_ta1_cert.pem"),
                    "i5": os.path.join(self.chain_certs_dir,
                        "ch5_ta1_cert.pem"),
                    "i6": os.path.join(self.chain_certs_dir,
                        "ch1_ta3_cert.pem"),
                    "pkg": self.signed
                }
                self.pkgsign(self.rurl, sign_args)

                # This is just a test assertion to verify that the package
                # was signed as expected.
                self.image_create(self.rurl)
                self.seed_ta_dir("ta1")
                self.pkg("set-property signature-policy verify")
                self.pkg("install signed")
                self.image_destroy()

                # Expected list of archive members for archive containing foo.
                self.foo_expected = [
                    "pkg5.index.0.gz",
                    "publisher",
                    "publisher/test",
                    "publisher/test/pkg",
                    "publisher/test/pkg/foo",
                    "publisher/test/pkg/%s" % self.foo.get_dir_path(),
                    "publisher/test/file",
                    "publisher/test/file/b2",
                    "publisher/test/file/b2/b265f2ec87c4a55eb2b6b4c926e7c65f7247a27e",
                    "publisher/test/file/a2",
                    "publisher/test/file/a2/a285ada5f3cae14ea00e97a8d99bd3e357cb0dca",
                    "publisher/test/file/0a",
                    "publisher/test/file/0a/0acf1107d31f3bab406f8611b21b8fade78ac874",
                    "publisher/test/file/dc",
                    "publisher/test/file/dc/dc84bd4b606fe43fc892eb245d9602b67f8cba38",
                    "pkg5.repository",
                ]

                # Expected list of archive members for archive containing foo
                # and quux (sorted).
                self.multi_expected = [
                    "pkg5.index.0.gz",
                    "pkg5.repository",
                    "publisher",
                    "publisher/test",
                    "publisher/test/file",
                    "publisher/test/file/0a",
                    "publisher/test/file/0a/0acf1107d31f3bab406f8611b21b8fade78ac874",
                    "publisher/test/file/a2",
                    "publisher/test/file/a2/a285ada5f3cae14ea00e97a8d99bd3e357cb0dca",
                    "publisher/test/file/b2",
                    "publisher/test/file/b2/b265f2ec87c4a55eb2b6b4c926e7c65f7247a27e",
                    "publisher/test/file/dc",
                    "publisher/test/file/dc/dc84bd4b606fe43fc892eb245d9602b67f8cba38",
                    "publisher/test/pkg",
                    "publisher/test/pkg/foo",
                    "publisher/test/pkg/%s" % self.foo.get_dir_path(),
                    "publisher/test/pkg/signed",
                    "publisher/test/pkg/%s" % self.signed.get_dir_path(),
                    "publisher/test2",
                    "publisher/test2/file",
                    "publisher/test2/file/80",
                    "publisher/test2/file/80/801eebbfe8c526bf092d98741d4228e4d0fc99ae",
                    "publisher/test2/pkg",
                    "publisher/test2/pkg/quux",
                    "publisher/test2/pkg/%s" % self.quux.get_dir_path(),
                ]

        def test_00_create(self):
                """Verify that archive creation works as expected."""

                # Verify that an empty package archive can be created and that
                # the resulting archive is of the correct type.
                arc_path = os.path.join(self.test_root, "empty.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                self.assertEqual(arc.pathname, arc_path)
                arc.close()

                # Verify archive exists and use the tarfile module to read the
                # archive so that the implementation can be verified.
                assert os.path.exists(arc_path)
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                fm = arc.firstmember
                self.assertEqual(fm.name, "pkg5.index.0.gz")
                comment = fm.pax_headers.get("comment", "")
                self.assertEqual(comment, "pkg5.archive.version.0")

                # Verify basic expected content exists.
                expected = ["pkg5.index.0.gz", "publisher", "pkg5.repository"]
                actual = [m.name for m in arc.getmembers()]
                self.assertEqualDiff(expected, actual)

                # Destroy the archive.
                os.unlink(arc_path)

        def test_01_add(self):
                """Verify that add() works as expected."""

                # Prep the archive.
                arc_path = os.path.join(self.test_root, "add.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")

                # add() permits addition of arbitrary files (intentionally);
                # it is also the routine that higher-level functions to add
                # package content use internally.  Because of that, this
                # function does not strictly need standalone testing, but it
                # helps ensure all code paths for add() are tested.
                arc.add(self.test_root)
                tmp_root = os.path.join(self.test_root, "tmp")
                arc.add(tmp_root)

                for f in self.misc_files:
                        src = os.path.join(self.test_root, f)

                        # Ensure files are read-only mode so that file perm
                        # normalization can be tested.
                        os.chmod(src, pkg.misc.PKG_RO_FILE_MODE)
                        arc.add(src)

                # Write out archive.
                arc.close()

                # Now open the archive and iterate through its contents and
                # verify that each member has the expected characteristics.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")

                members = [m for m in arc.getmembers()]

                # Should be 11 files including package archive index and three
                # directories.
                actual = [m.name for m in members]
                self.assertEqual(len(actual), 11)
                expected = ["pkg5.index.0.gz", "publisher",
                    pkg.misc.relpath(self.test_root, "/"),
                    pkg.misc.relpath(tmp_root, "/")
                ]
                expected.extend(
                    pkg.misc.relpath(os.path.join(self.test_root, e), "/")
                    for e in self.misc_files
                )
                expected.append("pkg5.repository")
                self.assertEqualDiff(expected, actual)

                for member in members:
                        # All archive members should be a file or directory.
                        self.assert_(member.isreg() or member.isdir())

                        if member.name == "pkg5.index.0.gz":
                                assert member.isreg()
                                comment = member.pax_headers.get("comment", "")
                                self.assertEqual(comment,
                                    "pkg5.archive.version.0")
                                continue

                        if member.isdir():
                                # Verify directories were added with expected
                                # mode.
                                self.assertEqual(oct(member.mode),
                                    oct(pkg.misc.PKG_DIR_MODE))
                        elif member.isfile():
                                # Verify files were added with expected mode.
                                self.assertEqual(oct(member.mode),
                                    oct(pkg.misc.PKG_FILE_MODE))

                        # Verify files and directories have expected ownership.
                        self.assertEqual(member.uname, "root")
                        self.assertEqual(member.gname, "root")
                        self.assertEqual(member.uid, 0)
                        self.assertEqual(member.gid, 0)

                os.unlink(arc_path)

        def test_02_add_package(self):
                """Verify that pkg(5) archive creation using add_package() works
                as expected.
                """

                # Get repository.
                repo = self.get_repo(self.dc.get_repodir())

                # Create a directory and copy package files from repository to
                # it (this is how pkgrecv stores content during republication
                # or when using --raw).
                dfroot = os.path.join(self.test_root, "pfiles")
                os.mkdir(dfroot, pkg.misc.PKG_DIR_MODE)

                foo_path = os.path.join(dfroot, "foo.p5m")
                portable.copyfile(repo.manifest(self.foo), foo_path)

                signed_path = os.path.join(dfroot, "signed.p5m")
                portable.copyfile(repo.manifest(self.signed), signed_path)

                quux_path = os.path.join(dfroot, "quux.p5m")
                portable.copyfile(repo.manifest(self.quux), quux_path)

                for rstore in repo.rstores:
                        for dirpath, dirnames, filenames in os.walk(
                            rstore.file_root):
                                if not filenames:
                                        continue
                                for f in filenames:
                                        portable.copyfile(
                                            os.path.join(dirpath, f),
                                            os.path.join(dfroot, f))

                # Prep the archive.
                progtrack = pkg.client.progress.QuietProgressTracker()
                arc_path = os.path.join(self.test_root, "add_package.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")

                # Create an archive with just one package.
                arc.add_package(self.foo, foo_path, dfroot)
                arc.close(progtrack=progtrack)

                # Verify the result.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                expected = self.foo_expected
                actual = [m.name for m in arc.getmembers()]
                self.assertEqualDiff(expected, actual)

                # Prep a new archive.
                os.unlink(arc_path)
                arc = pkg.p5p.Archive(arc_path, mode="w")

                # Create an archive with multiple packages.
                # (Don't use progtrack this time.)
                arc.add_package(self.foo, foo_path, dfroot)
                arc.add_package(self.signed, signed_path, dfroot)
                arc.add_package(self.quux, quux_path, dfroot)
                arc.close()

                # Verify the result.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                expected = self.multi_expected[:]
                action_certs = [self.calc_pem_hash(t) for t in (
                    os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch1_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch2_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch3_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch4_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch5_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch1_ta3_cert.pem"),
                )]
                for hsh in action_certs:
                        d = "publisher/test/file/%s" % hsh[0:2]
                        f = "%s/%s" % (d, hsh)
                        expected.append(d)
                        expected.append(f)

                actual = sorted(m.name for m in arc.getmembers())
                self.assertEqualDiff(sorted(set(expected)), actual)

                os.unlink(arc_path)
                os.unlink(foo_path)
                os.unlink(quux_path)
                os.unlink(signed_path)

        def test_03_add_repo_package(self):
                """Verify that pkg(5) archive creation using add_repo_package()
                works as expected.
                """

                progtrack = pkg.client.progress.QuietProgressTracker()

                # Get repository.
                repo = self.get_repo(self.dc.get_repodir())

                # Create an archive with just one package.
                arc_path = os.path.join(self.test_root, "add_repo_package.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                arc.add_repo_package(self.foo, repo)
                arc.close(progtrack=progtrack)

                # Verify the result.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                expected = self.foo_expected
                actual = [m.name for m in arc.getmembers()]
                self.assertEqualDiff(expected, actual)

                # Prep a new archive.
                os.unlink(arc_path)
                arc = pkg.p5p.Archive(arc_path, mode="w")

                # Create an archive with multiple packages.
                # (Don't use progtrack this time.)
                arc.add_repo_package(self.foo, repo)
                arc.add_repo_package(self.signed, repo)
                arc.add_repo_package(self.quux, repo)
                arc.close()

                # Verify the result.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                # Add in the p5i file since this is an archive with signed
                # packages created from a repo.
                expected = sorted(self.multi_expected +
                    ["publisher/test/pub.p5i"])
                action_certs = [self.calc_pem_hash(t) for t in (
                    os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch1_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch2_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch3_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch4_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch5_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch1_ta3_cert.pem"),
                )]
                for hsh in action_certs:
                        d = "publisher/test/file/%s" % hsh[0:2]
                        f = "%s/%s" % (d, hsh)
                        expected.append(d)
                        expected.append(f)
                actual = sorted(m.name for m in arc.getmembers())
                self.assertEqualDiff(sorted(set(expected)), actual)

                os.unlink(arc_path)

        def __verify_manifest_sig(self, repo, pfmri, content):
                """Helper method to verify that the given manifest signature
                data matches that of the corresponding manifest in a repository.
                """

                sm = pkg.manifest.Manifest(pfmri=pfmri)
                sm.set_content(pathname=repo.manifest(pfmri), signatures=True)

                if isinstance(content, basestring):
                        dm = pkg.manifest.Manifest()
                        dm.set_content(content=content, signatures=True)
                else:
                        dm = content
                self.assertEqualDiff(sm.signatures, dm.signatures)

        def __verify_manifest_file_sig(self, repo, pfmri, target):
                """Helper method to verify that target manifest's signature data
                matches that of the corresponding manifest in a repository.
                """

                sm = pkg.manifest.Manifest(pfmri=pfmri)
                sm.set_content(pathname=repo.manifest(pfmri), signatures=True)

                dm = pkg.manifest.Manifest()
                dm.set_content(pathname=target, signatures=True)
                self.assertEqualDiff(sm.signatures, dm.signatures)

        def __verify_extract(self, repo, arc_path, hashes, ext_dir):
                """Helper method to test extraction and retrieval functionality.
                """

                arc = pkg.p5p.Archive(arc_path, mode="r")

                #
                # Verify behaviour of extract_package_manifest().
                #

                # Test bad FMRI.
                self.assertRaises(pkg.fmri.IllegalFmri,
                    arc.extract_package_manifest, "pkg:/^boguspkg@1.0,5.11",
                    ext_dir)

                # Test unqualified (no publisher) FMRI.
                self.assertRaises(AssertionError,
                    arc.extract_package_manifest, "pkg:/unknown@1.0,5.11",
                    ext_dir)

                # Test unknown FMRI.
                self.assertRaisesStringify(pkg.p5p.UnknownPackageManifest,
                    arc.extract_package_manifest, "pkg://test/unknown@1.0,5.11",
                    ext_dir)

                # Test extraction when not specifying filename.
                fpath = os.path.join(ext_dir, self.foo.get_dir_path())
                arc.extract_package_manifest(self.foo, ext_dir)
                self.__verify_manifest_file_sig(repo, self.foo, fpath)

                # Test extraction specifying directory that does not exist.
                shutil.rmtree(ext_dir)
                arc.extract_package_manifest(self.foo, ext_dir,
                    filename="foo.p5m")
                self.__verify_manifest_file_sig(repo, self.foo,
                    os.path.join(ext_dir, "foo.p5m"))

                # Test extraction specifying directory that already exists.
                arc.extract_package_manifest(self.quux, ext_dir,
                    filename="quux.p5m")
                self.__verify_manifest_file_sig(repo, self.quux,
                    os.path.join(ext_dir, "quux.p5m"))

                # Test extraction in the case that manifest already exists.
                arc.extract_package_manifest(self.quux, ext_dir,
                    filename="quux.p5m")
                self.__verify_manifest_file_sig(repo, self.quux,
                    os.path.join(ext_dir, "quux.p5m"))

                #
                # Verify behaviour of extract_package_files().
                #
                arc.close()
                arc = pkg.p5p.Archive(arc_path, mode="r")
                shutil.rmtree(ext_dir)

                # Test unknown hashes.
                self.assertRaisesStringify(pkg.p5p.UnknownArchiveFiles,
                    arc.extract_package_files, ["a", "b", "c"], ext_dir)

                # Test extraction specifying directory that does not exist.
                arc.extract_package_files(hashes["all"], ext_dir)
                for h in hashes["all"]:
                        fpath = os.path.join(ext_dir, h)
                        assert os.path.exists(fpath)

                        # Now change mode to readonly.
                        os.chmod(fpath, pkg.misc.PKG_RO_FILE_MODE)

                # Test extraction in the case that files already exist
                # (and those files are readonly).
                arc.extract_package_files(hashes["all"], ext_dir)
                for h in hashes["all"]:
                        assert os.path.exists(os.path.join(ext_dir, h))

                # Test extraction when publisher is specified.
                shutil.rmtree(ext_dir)
                arc.extract_package_files(hashes["test"], ext_dir, pub="test")
                for h in hashes["test"]:
                        assert os.path.exists(os.path.join(ext_dir, h))

                #
                # Verify behaviour of extract_to().
                #
                arc.close()
                arc = pkg.p5p.Archive(arc_path, mode="r")
                shutil.rmtree(ext_dir)

                # Test unknown file.
                self.assertRaisesStringify(pkg.p5p.UnknownArchiveFiles,
                    arc.extract_to, "no/such/file", ext_dir)

                # Test extraction when not specifying filename (archive
                # member should be extracted into target directory using
                # full path in archive; that is, the target dir is pre-
                # pended).
                for pub in hashes:
                        if pub == "all":
                                continue
                        for h in hashes[pub]:
                                arcname = os.path.join("publisher", pub, "file",
                                    h[:2], h)
                                arc.extract_to(arcname, ext_dir)

                                fpath = os.path.join(ext_dir, arcname)
                                assert os.path.exists(fpath)

                # Test extraction specifying directory that does not exist.
                shutil.rmtree(ext_dir)
                for pub in hashes:
                        if pub == "all":
                                continue
                        for h in hashes[pub]:
                                arcname = os.path.join("publisher", pub, "file",
                                    h[:2], h)
                                arc.extract_to(arcname, ext_dir, filename=h)

                                fpath = os.path.join(ext_dir, h)
                                assert os.path.exists(fpath)

                                # Now change mode to readonly.
                                os.chmod(fpath, pkg.misc.PKG_RO_FILE_MODE)

                # Test extraction in the case that files already exist
                # (and those files are readonly).
                for pub in hashes:
                        if pub == "all":
                                continue
                        for h in hashes[pub]:
                                arcname = os.path.join("publisher", pub, "file",
                                    h[:2], h)
                                arc.extract_to(arcname, ext_dir, filename=h)

                                fpath = os.path.join(ext_dir, h)
                                assert os.path.exists(fpath)

                #
                # Verify behaviour of get_file().
                #
                arc.close()
                arc = pkg.p5p.Archive(arc_path, mode="r")

                # Test behaviour for non-existent file.
                self.assertRaisesStringify(pkg.p5p.UnknownArchiveFiles,
                    arc.get_file, "no/such/file")

                # Test that archived content retrieved is identical.
                arcname = os.path.join("publisher", self.foo.publisher, "pkg",
                    self.foo.get_dir_path())
                fobj = arc.get_file(arcname)
                self.__verify_manifest_sig(repo, self.foo, fobj.read())
                fobj.close()

                #
                # Verify behaviour of get_package_file().
                #
                arc.close()
                arc = pkg.p5p.Archive(arc_path, mode="r")

                # Test behaviour when specifying publisher.
                nullf = open(os.devnull, "wb")
                for h in hashes["test"]:
                        fobj = arc.get_package_file(h, pub="test")
                        uchash = pkg.misc.gunzip_from_stream(fobj, nullf)
                        self.assertEqual(uchash, h)
                        fobj.close()

                # Test behaviour when not specifying publisher.
                for h in hashes["test"]:
                        fobj = arc.get_package_file(h)
                        uchash = pkg.misc.gunzip_from_stream(fobj, nullf)
                        self.assertEqual(uchash, h)
                        fobj.close()

                #
                # Verify behaviour of get_package_manifest().
                #
                arc.close()
                arc = pkg.p5p.Archive(arc_path, mode="r")

                # Test bad FMRI.
                self.assertRaises(pkg.fmri.IllegalFmri,
                    arc.get_package_manifest, "pkg:/^boguspkg@1.0,5.11")

                # Test unqualified (no publisher) FMRI.
                self.assertRaises(AssertionError,
                    arc.get_package_manifest, "pkg:/unknown@1.0,5.11")

                # Test unknown FMRI.
                self.assertRaisesStringify(pkg.p5p.UnknownPackageManifest,
                    arc.get_package_manifest, "pkg://test/unknown@1.0,5.11")

                # Test that archived content retrieved is identical.
                mobj = arc.get_package_manifest(self.foo)
                self.__verify_manifest_sig(repo, self.foo, mobj)

                mobj = arc.get_package_manifest(self.signed)
                self.__verify_manifest_sig(repo, self.signed, mobj)

                #
                # Verify behaviour of extract_catalog1().
                #
                arc.close()
                arc = pkg.p5p.Archive(arc_path, mode="r")
                ext_tmp_dir = tempfile.mkdtemp(dir=self.test_root)
                def verify_catalog(pub, pfmris):
                        for pname in ("catalog.attrs", "catalog.base.C",
                            "catalog.dependency.C", "catalog.summary.C"):
                                expected = os.path.join(ext_tmp_dir, pname)
                                try:
                                        arc.extract_catalog1(pname, ext_tmp_dir,
                                            pub=pub)
                                except pkg.p5p.UnknownArchiveFiles:
                                        if pname == "catalog.dependency.C":
                                                # No dependencies, so exeception
                                                # is only expected for this.
                                                continue
                                        raise

                                assert os.path.exists(expected)

                        cat = pkg.catalog.Catalog(meta_root=ext_tmp_dir)
                        self.assertEqual([f for f in cat.fmris()], pfmris)

                verify_catalog("test", [self.foo, self.signed])
                shutil.rmtree(ext_tmp_dir)
                os.mkdir(ext_tmp_dir)

                verify_catalog("test2", [self.quux])
                shutil.rmtree(ext_tmp_dir)
                return arc

        def test_04_extract(self):
                """Verify that pkg(5) archive extraction methods work as
                expected.
                """

                # Get repository.
                repo = self.get_repo(self.dc.get_repodir())

                # Create an archive with a few packages.
                arc_path = os.path.join(self.test_root, "retrieve.p5p")
                arc = pkg.p5p.Archive(arc_path, mode="w")
                arc.add_repo_package(self.foo, repo)
                arc.add_repo_package(self.signed, repo)
                arc.add_repo_package(self.quux, repo)
                arc.close()

                # Get list of file hashes.
                hashes = { "all": set() }
                for rstore in repo.rstores:
                        for dirpath, dirnames, filenames in os.walk(
                            rstore.file_root):
                                if not filenames:
                                        continue
                                hashes["all"].update(filenames)
                                hashes.setdefault(rstore.publisher,
                                    set()).update(filenames)

                # Extraction directory for testing.
                ext_dir = os.path.join(self.test_root, "extracted")

                # First, verify behaviour using archive created using
                # pkg(5) archive class.
                arc = self.__verify_extract(repo, arc_path, hashes, ext_dir)
                arc.close()

                # Now extract everything from the archive and create
                # a new archive using the tarfile class, and verify
                # that the pkg(5) archive class can still extract
                # and access the contents as expected even though
                # the index file isn't marked with the appropriate
                # pax headers (and so should be ignored since it's
                # also invalid).
                shutil.rmtree(ext_dir)

                # Extract all of the existing content.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                arc.extractall(ext_dir)
                arc.close()

                # Create a new archive.
                os.unlink(arc_path)
                arc = ptf.PkgTarFile(name=arc_path, mode="w")

                def add_entry(src):
                        fpath = os.path.join(dirpath, src)
                        arcname = pkg.misc.relpath(fpath, ext_dir)
                        arc.add(name=fpath, arcname=arcname,
                            recursive=False)

                for dirpath, dirnames, filenames in os.walk(ext_dir):
                        map(add_entry, filenames)
                        map(add_entry, dirnames)
                arc.close()

                # Verify that archive has expected contents.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                # Add in the p5i file since this is an archive with signed
                # packages created from a repo.
                expected = sorted(self.multi_expected +
                    ["publisher/test/pub.p5i"])
                action_certs = [self.calc_pem_hash(t) for t in (
                    os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch1_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch2_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch3_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch4_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch5_ta1_cert.pem"),
                    os.path.join(self.chain_certs_dir, "ch1_ta3_cert.pem"),
                )]
                for hsh in action_certs:
                        d = "publisher/test/file/%s" % hsh[0:2]
                        f = "%s/%s" % (d, hsh)
                        expected.append(d)
                        expected.append(f)
                actual = sorted(m.name for m in arc.getmembers())
                self.assertEqualDiff(sorted(set(expected)), actual)
                arc.close()

                # Verify pkg(5) archive class extraction behaviour using
                # the new archive.
                arc = self.__verify_extract(repo, arc_path, hashes, ext_dir)
                arc.close()

                # Extract all of the existing content.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                arc.extractall(ext_dir)
                arc.close()
       
                # Now verify archive can still be used when index file
                # is omitted.
                os.unlink(arc_path)
                arc = ptf.PkgTarFile(name=arc_path, mode="w")
                for dirpath, dirnames, filenames in os.walk(ext_dir):
                        map(add_entry,
                            [f for f in filenames if f != "pkg5.index.0.gz"])
                        map(add_entry, dirnames)
                arc.close()

                # Verify pkg(5) archive class extraction behaviour using
                # the new archive.
                arc = self.__verify_extract(repo, arc_path, hashes, ext_dir)
                arc.close()

        def test_05_invalid(self):
                """Verify that pkg(5) archive class handles broken archives
                and items that aren't archives as expected."""

                arc_path = os.path.join(self.test_root, "nosucharchive.p5p")

                #
                # Check that no archive is handled.
                #
                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    pkg.p5p.Archive, arc_path, mode="r")

                #
                # Check that empty archive file is handled.
                #
                arc_path = os.path.join(self.test_root, "retrieve.p5p")
                open(arc_path, "wb").close()
                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    pkg.p5p.Archive, arc_path, mode="r")
                os.unlink(arc_path)

                #
                # Check that invalid archive file is handled.
                #
                with open(arc_path, "wb") as f:
                        f.write("not_a_valid_archive")
                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    pkg.p5p.Archive, arc_path, mode="r")
                os.unlink(arc_path)

                #
                # Check that a truncated archive is handled.
                #
                repo = self.get_repo(self.dc.get_repodir())
                arc = pkg.p5p.Archive(arc_path, mode="w")
                arc.add_repo_package(self.foo, repo)
                arc.add_repo_package(self.signed, repo)
                arc.add_repo_package(self.quux, repo)
                arc.close()

                #
                # Check that truncated archives, or archives with invalid
                # indexes are handled as expected.
                #

                # Determine where to truncate archive by looking for specific
                # package file and then setting truncate location to halfway
                # through data for file.
                arc = ptf.PkgTarFile(name=arc_path, mode="r")
                idx_data_offset = 0
                src_offset = 0
                src_bytes = 0
                dest_offset = 0
                trunc_sz = 0
                src_fhash = "b265f2ec87c4a55eb2b6b4c926e7c65f7247a27e"
                dest_fhash = "801eebbfe8c526bf092d98741d4228e4d0fc99ae"
                for m in arc.getmembers():
                        if m.name.endswith("/" + dest_fhash):
                                dest_offset = m.offset
                                trunc_sz = m.offset_data + int(m.size / 2)
                        elif m.name.endswith("pkg5.index.0.gz"):
                                idx_data_offset = m.offset_data
                        elif m.name.endswith("/" + src_fhash):
                                # Calculate size of source entry.
                                src_bytes = m.offset_data - m.offset
                                blocks, rem = divmod(m.size, tf.BLOCKSIZE)
                                if rem > 0:
                                        blocks += 1
                                src_bytes += blocks * tf.BLOCKSIZE
                                src_offset = m.offset

                arc.close()

                # Test truncated archive case.
                bad_arc_path = os.path.join(self.test_root, "bad_arc.p5p")
                portable.copyfile(arc_path, bad_arc_path)

                self.debug("%s size: %d truncate: %d" % (arc_path,
                    os.stat(arc_path).st_size, trunc_sz))
                with open(bad_arc_path, "ab+") as f:
                        f.truncate(trunc_sz)

                ext_dir = os.path.join(self.test_root, "extracted")
                shutil.rmtree(ext_dir, True)
                arc = pkg.p5p.Archive(bad_arc_path, mode="r")
                self.assertRaisesStringify(pkg.p5p.CorruptArchiveFiles,
                    arc.extract_package_files, [dest_fhash], ext_dir,
                    pub="test2")
                arc.close()

                # Test archive with invalid index; do this by writing some bogus
                # bytes into the data area for the index.
                portable.copyfile(arc_path, bad_arc_path)
                with open(bad_arc_path, "ab+") as dest:
                        dest.seek(idx_data_offset)
                        dest.truncate()
                        with open(arc_path, "rb") as src:
                                bogus_data = "invalid_index_data"
                                dest.write(bogus_data)
                                src.seek(idx_data_offset + len(bogus_data))
                                dest.write(src.read())

                shutil.rmtree(ext_dir, True)
                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    pkg.p5p.Archive, bad_arc_path, mode="r")

                # Test archive with invalid index offsets; do this by truncating
                # an existing archive at the offset of one of its files and then
                # appending the data for a different archive member in its
                # place.
                portable.copyfile(arc_path, bad_arc_path)
                with open(bad_arc_path, "ab+") as dest:
                        dest.seek(dest_offset)
                        dest.truncate()
                        with open(arc_path, "rb") as src:
                                src.seek(src_offset)
                                dest.write(src.read(src_bytes))

                shutil.rmtree(ext_dir, True)
                arc = pkg.p5p.Archive(bad_arc_path, mode="r")
                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    arc.extract_package_files, [dest_fhash], ext_dir,
                    pub="test2")
                arc.close()

                os.unlink(arc_path)
                os.unlink(bad_arc_path)

                #
                # Check that directory where archive expected is handled.
                #
                os.mkdir(arc_path)
                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    pkg.p5p.Archive, arc_path, mode="r")
                os.rmdir(arc_path)

                # Temporarily change the current archive version and create a
                # a new archive, and then verify that the expected exception is
                # raised when an attempt to read it is made.
                orig_ver = pkg.p5p.Archive.CURRENT_VERSION
                try:
                        pkg.p5p.Archive.CURRENT_VERSION = 99 # EVIL
                        arc = pkg.p5p.Archive(arc_path, mode="w")
                        arc.close()
                finally:
                        # Ensure this is reset to the right value.
                        pkg.p5p.Archive.CURRENT_VERSION = orig_ver

                self.assertRaisesStringify(pkg.p5p.InvalidArchive,
                    pkg.p5p.Archive, arc_path, mode="r")
                os.unlink(arc_path)


if __name__ == "__main__":
        unittest.main()
