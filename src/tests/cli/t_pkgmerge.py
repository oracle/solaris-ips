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

import os
import pkg.config as cfg
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.server.repository as repo
import shutil
import tempfile
import time
import urllib
import urlparse
import unittest
import zlib


class TestUtilMerge(pkg5unittest.ManyDepotTestCase):
        persistent_setup = True

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

        bronze20b = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/scheme mode=0444 owner=root group=bin path=/etc/scheme
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            add depend fmri=pkg:/scheme@1.0 type=require
            close 
        """

        bronze20c = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/scheme mode=0444 owner=root group=bin path=/etc/scheme
            add file tmp/sh mode=0444 owner=root group=bin path=/etc/tree
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            add depend fmri=pkg:/scheme@1.0 type=require
            add depend fmri=pkg:/tree@1.0 type=require
            close 
        """

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
            "tmp/bronze2", "tmp/copyright2", "tmp/copyright3", "tmp/libc.so.1",
            "tmp/sh", "tmp/scheme"]

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["os.org", "os.org",
                    "os.org", "os.org", "os.org", "os.org", "os.org"])
                self.make_misc_files(self.misc_files)

                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.rurl4 = self.dcs[4].get_repo_url()
                self.rurl5 = self.dcs[5].get_repo_url()
                self.rurl6 = self.dcs[6].get_repo_url()

                # Empty repository.
                self.rurl7 = self.dcs[7].get_repo_url()
        
                # Publish a set of packages to one repository.
                self.published = self.pkgsend_bulk(self.rurl1, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20, self.tree10,
                    self.scheme10))

                # Ensure timestamps of all successive publications are greater.
                time.sleep(1)

                # Publish the same set to another repository (minus the tree
                # and scheme packages, and with a slightly different version
                # of the bronze20 package).
                self.published += self.pkgsend_bulk(self.rurl2, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20b))

                # Ensure timestamps of all successive publications are greater.
                time.sleep(1)

                # Publish the same set to another repository (with a slightly
                # different version of the bronze20b package and with tree).
                self.published += self.pkgsend_bulk(self.rurl3, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20c, self.tree10))

                # Ensure timestamps of all successive publications are greater.
                time.sleep(1)

                # Everything above again, but this time using the debug version
                # of the misc. files and a different set of repositories.
                dfiles = dict((f, f + ".debug") for f in self.misc_files)

                # For testing purposes, don't change this file for the debug
                # variant case.
                dfiles["tmp/libc.so.1"] = "tmp/libc.so.1"
                self.make_misc_files(dfiles)

                self.published_debug = self.pkgsend_bulk(self.rurl4,
                    (self.amber10, self.amber20, self.bronze10, self.bronze20,
                    self.tree10, self.scheme10))
                time.sleep(1)

                self.published_debug += self.pkgsend_bulk(self.rurl5,
                    (self.amber10, self.amber20, self.bronze10, self.bronze20b))
                time.sleep(1)

                self.published_debug += self.pkgsend_bulk(self.rurl6, (
                    self.amber10, self.amber20, self.bronze10, self.bronze20c,
                    self.tree10))

        def test_0_options(self):
                """Verify that pkgmerge gracefully fails when given bad option
                values."""

                # Should fail because no source was specified.
                self.pkgmerge(" ".join([
                    "-d %s" % self.rurl2,
                ]), exit=2)

                # Should fail because no destination was specified.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.rurl2,
                ]), exit=2)

                # Should fail because variant for source was not provided.
                self.pkgmerge(" ".join([
                    "-s %s" % self.rurl1,
                    "-d %s" % self.rurl2,
                ]), exit=2)

                # Should fail because only source variant was provided.
                self.pkgmerge(" ".join([
                    "-s arch=i386",
                    "-d %s" % self.rurl2,
                ]), exit=2)

                # Should fail because user did not specify the same variants
                # for every source.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,%s" % self.dcs[1].get_repodir(),
                    "-s arch=i386,debug=true,%s" % self.dcs[2].get_repodir(),
                    "-d %s" % self.rurl7
                ]), exit=2)

                # Should fail because user did not specify a source for all
                # variant combinations (e.g. i386 & arm debug).
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=false,%s" % self.dcs[1].get_repodir(),
                    "-s arch=i386,debug=false,%s" % self.dcs[2].get_repodir(),
                    "-s arch=arm,debug=false,%s" % self.dcs[3].get_repodir(),
                    "-s arch=sparc,debug=true,%s" % self.dcs[4].get_repodir(),
                    "-d %s" % self.rurl7
                ]), exit=2)

                # Should fail because source is not a repository.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.test_root,
                    "-d %s" % self.rurl2,
                ]), exit=1)

                # Should fail because destination is not a repository.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.rurl2,
                    "-d %s" % self.test_root,
                ]), exit=1)

        def test_1_single_merge(self):
                """Verify that merge functionality works as expected when
                specifying a single source."""

                #
                # First, verify that merging all packages from a single source
                # works as expected.
                #

                # Create the target repository.
                repodir = os.path.join(self.test_root, "1merge_repo")
                self.create_repo(repodir)

                # Perform a dry-run.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.rurl2,
                    "-d %s" % repodir,
                    "-n",
                ]))

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.rurl2,
                    "-d %s" % repodir,
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                expected = [
                    self.published[7], # pkg://os.org/amber@2.0-0
                    self.published[9], # pkg://os.org/bronze@2.0-0
                ]
                actual = [str(f) for f in sorted(cat.fmris())]
                self.assertEqualDiff(expected, actual)

                # Verify that each package was merged correctly.
                merged_expected = {
                    "amber": """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value=%s
set name=variant.arch value=i386\
""" % self.published[7], # pkg://os.org/amber@2.0-0
                    "bronze": """\
depend fmri=pkg:/amber@2.0 type=require
depend fmri=pkg:/scheme@1.0 type=require
dir group=bin mode=0755 owner=root path=etc
dir group=bin mode=0755 owner=root path=lib
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10
file 8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8 chash=6ff2f52d2f894f5c71fb8fdd3b214e22959fccbb group=bin mode=0555 owner=root path=lib/libc.bronze pkg.csize=33 pkg.size=13
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11
hardlink path=lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14
link path=usr/bin/jsh target=./sh
set name=pkg.fmri value=%s
set name=variant.arch value=i386\
""" % self.published[9] # pkg://os.org/bronze@2.0-0
                }

                for f in cat.fmris():
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                #
                # Next, verify that merging specific packages from a single
                # source works as expected.
                #

                # Create the target repository.
                shutil.rmtree(repodir)
                self.create_repo(repodir)

                # Perform a dry-run.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.rurl2,
                    "-d %s" % repodir,
                    "-n",
                    "amber@latest",
                ]))

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=i386,%s" % self.rurl2,
                    "-d %s" % repodir,
                    "amber@latest",
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                expected = [
                    self.published[7], # pkg://os.org/amber@2.0-0
                ]
                actual = [str(f) for f in sorted(cat.fmris())]
                self.assertEqualDiff(expected, actual)

                # Verify that each package was merged correctly.
                for f in cat.fmris():
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                # Next, verify that an attempt to merge using a variant that
                # doesn't match what is already declared in a source's packages
                # results in failure.  (e.g. packages are tagged i386, but
                # source was claimed to be sparc.)
                junk_repodir = os.path.join(self.test_root, "1junk_repo")
                self.create_repo(junk_repodir)

                self.pkgmerge(" ".join([
                    "-s arch=sparc,%s" % repodir,
                    "-d %s" % junk_repodir,
                    "amber@latest",
                ]), exit=1)

                # Cleanup.
                shutil.rmtree(repodir)

        def test_2_multi_merge(self):
                """Verify that merge functionality works as expected when
                specifying multiple sources."""

                #
                # First, verify that merging all packages from multiple sources
                # works as expected when specifying two variant values.
                #

                # Create the target repository.
                repodir = os.path.join(self.test_root, "2merge_repo")
                self.create_repo(repodir)

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,%s" % self.rurl1,
                    "-s arch=i386,%s" % self.rurl2,
                    "-d %s" % repodir
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                nlist = {}
                for s in self.published[:10]:
                        f = fmri.PkgFmri(s, "5.11")
                        if f.pkg_name not in nlist or \
                            f.version > nlist[f.pkg_name].version:
                                nlist[f.pkg_name] = f
                nlist = sorted(nlist.values())

                expected = [str(f) for f in nlist]
                actual = [str(f) for f in sorted(cat.fmris())]
                self.assertEqualDiff(expected, actual)

                # Verify that each package was merged correctly.
                merged_expected = {
                    "amber": """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386\
""" % self.published[7], # pkg://os.org/amber@2.0-0
                    "bronze": """\
depend fmri=pkg:/amber@2.0 type=require
depend fmri=pkg:/scheme@1.0 type=require variant.arch=i386
dir group=bin mode=0755 owner=root path=etc
dir group=bin mode=0755 owner=root path=lib
file 058b358a95c4417cb6d68eb9e37f41c063e03892 chash=69d518d352b7406393903e41f6316a01c13c53f9 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=31 pkg.size=11 variant.arch=sparc
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=i386
file 8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8 chash=6ff2f52d2f894f5c71fb8fdd3b214e22959fccbb group=bin mode=0555 owner=root path=lib/libc.bronze pkg.csize=33 pkg.size=13
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11
hardlink path=lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14
link path=usr/bin/jsh target=./sh
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386\
""" % self.published[9], # pkg://os.org/bronze@2.0-0
                    "scheme": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc\
""" % self.published[5], # pkg://os.org/scheme@1.0-0
                    "tree": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc\
""" % self.published[4], # pkg://os.org/tree@1.0-0
                }

                for f in nlist:
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                #
                # Next, verify that merging packages for three variant values
                # works as expected.
                #

                # Create the target repository.
                shutil.rmtree(repodir)
                self.create_repo(repodir)

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,%s" % self.rurl1,
                    "-s arch=i386,%s" % self.rurl2,
                    "-s arch=arm,%s" % self.rurl3,
                    "-d %s" % repodir
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                nlist = {}
                for s in self.published:
                        f = fmri.PkgFmri(s, "5.11")
                        if f.pkg_name not in nlist or \
                            f.version > nlist[f.pkg_name].version:
                                nlist[f.pkg_name] = f
                nlist = sorted(nlist.values())

                expected = [str(f) for f in nlist]
                actual = [str(f) for f in sorted(cat.fmris())]
                self.assertEqualDiff(expected, actual)

                # Verify that each package was merged correctly.
                merged_expected = {
                    "amber": """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386 value=arm\
""" % self.published[11], # pkg://os.org/amber@2.0-0
                    "bronze": """\
depend fmri=pkg:/amber@2.0 type=require
depend fmri=pkg:/scheme@1.0 type=require variant.arch=arm
depend fmri=pkg:/scheme@1.0 type=require variant.arch=i386
depend fmri=pkg:/tree@1.0 type=require variant.arch=arm
dir group=bin mode=0755 owner=root path=etc
dir group=bin mode=0755 owner=root path=lib
file 058b358a95c4417cb6d68eb9e37f41c063e03892 chash=69d518d352b7406393903e41f6316a01c13c53f9 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=31 pkg.size=11 variant.arch=sparc
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0444 owner=root path=etc/tree pkg.csize=26 pkg.size=6 variant.arch=arm
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=arm
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=i386
file 8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8 chash=6ff2f52d2f894f5c71fb8fdd3b214e22959fccbb group=bin mode=0555 owner=root path=lib/libc.bronze pkg.csize=33 pkg.size=13
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11
hardlink path=lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14
link path=usr/bin/jsh target=./sh
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386 value=arm\
""" % self.published[13], # pkg://os.org/bronze@2.0-0
                    "scheme": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc\
""" % self.published[5], # pkg://os.org/scheme@1.0-0
                    "tree": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=arm\
""" % self.published[14], # pkg://os.org/tree@1.0-0
                }

                for f in nlist:
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                #
                # Next, verify that merging specific packages from multiple
                # sources works as expected.
                #

                # Create the target repository.
                shutil.rmtree(repodir)
                self.create_repo(repodir)

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,%s" % self.rurl1,
                    "-s arch=i386,%s" % self.rurl2,
                    "-s arch=arm,%s" % self.rurl3,
                    "-d %s" % repodir,
                    "scheme amber@1.0 bronze@latest",
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                expected = [
                    self.published[10], # pkg://os.org/amber@1.0-0
                    self.published[13], # pkg://os.org/bronze@2.0-0
                    self.published[5], # pkg://os.org/scheme@1.0-0
                ]
                actual = [str(f) for f in sorted(cat.fmris())]
                self.assertEqualDiff(expected, actual)

                merged_expected["amber"] = """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386 value=arm\
""" % self.published[10] # pkg://os.org/amber@1.0-0

                # Verify that each package was merged correctly.
                for f in cat.fmris():
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                # Cleanup.
                shutil.rmtree(repodir)

        def test_3_cross_merge(self):
                """Verify that pkgmerge works as expected when the resulting
                merge is a cross-product (e.g. a prior merge in steps or all at
                once for sparc/x86 with debug/non-debug)."""

                # Create final merge repository.
                repodir = os.path.join(self.test_root, "3merge_repo")
                self.create_repo(repodir)

                for i, arch in enumerate(("sparc", "i386", "arm")):
                        # For each arch, merge the debug and non-debug variants
                        # first.
                        rdir = os.path.join(self.test_root, "3%s_repo" % arch)
                        self.create_repo(rdir)

                        ndrepo = self.dcs[i + 1].get_repodir()
                        drepo = self.dcs[i + 4].get_repodir()

                        # Merge the packages.
                        self.pkgmerge(" ".join([
                            "-s debug=false,%s" % ndrepo,
                            "-s variant.debug=true,%s" % drepo,
                            "-d %s" % rdir
                        ]))

                # Now merge all of the debug/non-debug repositories.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,%s" % os.path.join(self.test_root,
                        "3sparc_repo"),
                    "-s arch=i386,%s" % os.path.join(self.test_root,
                        "3i386_repo"),
                    "-s arch=arm,%s" % os.path.join(self.test_root,
                        "3arm_repo"),
                    "-d %s" % repodir,
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                nlist = {}
                for s in self.published + self.published_debug:
                        f = fmri.PkgFmri(s, "5.11")
                        if f.pkg_name not in nlist or \
                            f.version > nlist[f.pkg_name].version:
                                nlist[f.pkg_name] = f
                nlist = sorted(nlist.values())

                expected = [str(f) for f in nlist]
                actual = [str(f) for f in sorted(cat.fmris())]
                self.assertEqualDiff(expected, actual)

                # Verify that each package was merged correctly.
                merged_expected = {
                    "amber": """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386 value=arm
set name=variant.debug value=false value=true\
""" % self.published_debug[11], # pkg://os.org/amber@2.0-0
                    "bronze": """\
depend fmri=pkg:/amber@2.0 type=require
depend fmri=pkg:/scheme@1.0 type=require variant.arch=arm
depend fmri=pkg:/scheme@1.0 type=require variant.arch=i386
depend fmri=pkg:/tree@1.0 type=require variant.arch=arm
dir group=bin mode=0755 owner=root path=etc
dir group=bin mode=0755 owner=root path=lib
file 058b358a95c4417cb6d68eb9e37f41c063e03892 chash=69d518d352b7406393903e41f6316a01c13c53f9 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=31 pkg.size=11 variant.arch=sparc variant.debug=false
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0444 owner=root path=etc/tree pkg.csize=26 pkg.size=6 variant.arch=arm variant.debug=false
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6 variant.debug=false
file 1abe1a7084720f501912eceb1312ddd799fb2a34 chash=ea7230676e13986491d7405c5a9298e074930575 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=37 pkg.size=17 variant.debug=true
file 34f88965d55d3a730fa7683bc0f370fc6e42bf95 chash=66eebb69ee0299dcb495162336db81a3188de037 group=bin mode=0444 owner=root path=etc/tree pkg.csize=32 pkg.size=12 variant.arch=arm variant.debug=true
file 34f88965d55d3a730fa7683bc0f370fc6e42bf95 chash=66eebb69ee0299dcb495162336db81a3188de037 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=32 pkg.size=12 variant.debug=true
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12 variant.debug=false
file 6d8f3b9498aa3bbe7db01189b88f1b71f4ce40ad chash=6f3882864ebd7fd1a09e0e7b889fdc524c8c8bb2 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=37 pkg.size=17 variant.arch=sparc variant.debug=true
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=arm variant.debug=false
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=i386 variant.debug=false
file 8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8 chash=6ff2f52d2f894f5c71fb8fdd3b214e22959fccbb group=bin mode=0555 owner=root path=lib/libc.bronze pkg.csize=33 pkg.size=13
file 91fa26695f9891b2d94fd72c31b640efb5589da5 chash=4eed1e5dc5ab131812da34dc148562e6833fa92b group=bin mode=0444 owner=root path=etc/scheme pkg.csize=36 pkg.size=16 variant.arch=arm variant.debug=true
file 91fa26695f9891b2d94fd72c31b640efb5589da5 chash=4eed1e5dc5ab131812da34dc148562e6833fa92b group=bin mode=0444 owner=root path=etc/scheme pkg.csize=36 pkg.size=16 variant.arch=i386 variant.debug=true
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11 variant.debug=false
file cf68b26a90cb9a0d7510f24cfb8cf6d901cec34e chash=0eb6fe69c4492f801c35dcc9175d55f783cc64a2 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=38 pkg.size=18 variant.debug=true
hardlink path=lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
license 773b94a252723da43e8f969b4384701bcd41ce12 chash=e0715301fc211f6543ce0c444f4c34e38c70f70e license=copyright pkg.csize=40 pkg.size=20 variant.debug=true
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14 variant.debug=false
link path=usr/bin/jsh target=./sh
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=i386 value=arm
set name=variant.debug value=false value=true\
""" % self.published_debug[13], # pkg://os.org/bronze@2.0-0
                    "scheme": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc
set name=variant.debug value=false value=true\
""" % self.published_debug[5], # pkg://os.org/scheme@1.0-0
                    "tree": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc value=arm
set name=variant.debug value=false value=true\
""" % self.published_debug[14], # pkg://os.org/tree@1.0-0
                }

                for f in nlist:
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                # Cleanup.
                shutil.rmtree(repodir)

                #
                # Attempt to merge x86 and sparc debug/non-debug all at once.
                #
                self.create_repo(repodir)
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=false,%s" % self.dcs[1].get_repodir(),
                    "-s arch=i386,debug=false,%s" % self.dcs[2].get_repodir(),
                    "-s arch=arm,debug=false,%s" % self.dcs[3].get_repodir(),
                    "-s arch=sparc,debug=true,%s" % self.dcs[4].get_repodir(),
                    "-s arch=i386,debug=true,%s" % self.dcs[5].get_repodir(),
                    "-s arch=arm,debug=true,%s" % self.dcs[6].get_repodir(),
                    "-d %s" % repodir
                ]))

                repo = self.get_repo(repodir)
                for f in nlist:
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                # Cleanup.
                shutil.rmtree(repodir)

                #
                # Verify that naming an empty source allows a user to perform
                # mismatched merges (i.e. merge sparc debug/non-debug with i386
                # and arm non-debug) if empty repositories are used to fill in
                # the missing cases.
                nlist = {}
                for s in self.published + self.published_debug[:6]:
                        f = fmri.PkgFmri(s, "5.11")
                        if f.pkg_name not in nlist or \
                            f.version > nlist[f.pkg_name].version:
                                nlist[f.pkg_name] = f
                nlist = sorted(nlist.values())

                self.create_repo(repodir)
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=false,%s" % self.dcs[1].get_repodir(),
                    "-s arch=i386,debug=false,%s" % self.dcs[2].get_repodir(),
                    "-s arch=arm,debug=false,%s" % self.dcs[3].get_repodir(),
                    "-s arch=sparc,debug=true,%s" % self.dcs[4].get_repodir(),
                    # Explicitly state debug packages don't exist for these
                    # arch values by using an empty repository.
                    "-s arch=i386,debug=true,%s" % self.dcs[7].get_repodir(),
                    "-s arch=arm,debug=true,%s" % self.dcs[7].get_repodir(),
                    "-d %s" % repodir
                ]))

                # Verify that each package was merged correctly.
                merged_expected = {
                    "amber": """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value=%s
set name=variant.arch value=i386 value=arm value=sparc
set name=variant.debug value=false value=true variant.arch=sparc
set name=variant.debug value=false variant.arch=arm
set name=variant.debug value=false variant.arch=i386\
""" % self.published_debug[1], # pkg://os.org/amber@2.0-0
                    "bronze": """\
depend fmri=pkg:/amber@2.0 type=require
depend fmri=pkg:/scheme@1.0 type=require variant.arch=arm
depend fmri=pkg:/scheme@1.0 type=require variant.arch=i386
depend fmri=pkg:/tree@1.0 type=require variant.arch=arm
dir group=bin mode=0755 owner=root path=etc
dir group=bin mode=0755 owner=root path=lib
file 058b358a95c4417cb6d68eb9e37f41c063e03892 chash=69d518d352b7406393903e41f6316a01c13c53f9 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=31 pkg.size=11 variant.arch=sparc variant.debug=false
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0444 owner=root path=etc/tree pkg.csize=26 pkg.size=6 variant.arch=arm
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6 variant.arch=arm
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6 variant.arch=i386
file 05fbc66156a145a81f2985a65988519ffd6bffc6 chash=e22205864f82cf4f25885280135d076bf90f0fd0 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=26 pkg.size=6 variant.arch=sparc variant.debug=false
file 1abe1a7084720f501912eceb1312ddd799fb2a34 chash=ea7230676e13986491d7405c5a9298e074930575 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=37 pkg.size=17 variant.arch=sparc variant.debug=true
file 34f88965d55d3a730fa7683bc0f370fc6e42bf95 chash=66eebb69ee0299dcb495162336db81a3188de037 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=32 pkg.size=12 variant.arch=sparc variant.debug=true
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12 variant.arch=arm
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12 variant.arch=i386
file 5ae4f5f38ad6830ce0f163e5bf925e7a22be8d1d chash=2f4af72b2265bf0c894b18067357d811c3b27c67 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=32 pkg.size=12 variant.arch=sparc variant.debug=false
file 6d8f3b9498aa3bbe7db01189b88f1b71f4ce40ad chash=6f3882864ebd7fd1a09e0e7b889fdc524c8c8bb2 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=37 pkg.size=17 variant.arch=sparc variant.debug=true
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=arm
file 8264e757d4a4d8e2108a26b32edbf0412229b4d6 chash=9f0d43e4d39acd2c97a1ba8e86f3afce4d265757 group=bin mode=0444 owner=root path=etc/scheme pkg.csize=30 pkg.size=10 variant.arch=i386
file 8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8 chash=6ff2f52d2f894f5c71fb8fdd3b214e22959fccbb group=bin mode=0555 owner=root path=lib/libc.bronze pkg.csize=33 pkg.size=13
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11 variant.arch=arm
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11 variant.arch=i386
file a268afd7e6131a2273314b397dd6232827b6152b chash=2e7390833be180b7373d90884ec1e45bd1edfa92 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=31 pkg.size=11 variant.arch=sparc variant.debug=false
file cf68b26a90cb9a0d7510f24cfb8cf6d901cec34e chash=0eb6fe69c4492f801c35dcc9175d55f783cc64a2 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=38 pkg.size=18 variant.arch=sparc variant.debug=true
hardlink path=lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
license 773b94a252723da43e8f969b4384701bcd41ce12 chash=e0715301fc211f6543ce0c444f4c34e38c70f70e license=copyright pkg.csize=40 pkg.size=20 variant.arch=sparc variant.debug=true
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14 variant.arch=arm
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14 variant.arch=i386
license 995ad376b9c7ae79d67e673504fc4199fbfb32eb chash=9374d402ed3034a553119e179d0ae00386bb5206 license=copyright pkg.csize=34 pkg.size=14 variant.arch=sparc variant.debug=false
link path=usr/bin/jsh target=./sh
set name=pkg.fmri value=%s
set name=variant.arch value=i386 value=arm value=sparc
set name=variant.debug value=false value=true variant.arch=sparc
set name=variant.debug value=false variant.arch=arm
set name=variant.debug value=false variant.arch=i386\
""" % self.published_debug[3], # pkg://os.org/bronze@2.0-0
                    "scheme": """\
set name=pkg.fmri value=%s
set name=variant.arch value=sparc
set name=variant.debug value=false value=true\
""" % self.published_debug[5], # pkg://os.org/scheme@1.0-0
                    "tree": """\
set name=pkg.fmri value=%s
set name=variant.arch value=arm value=sparc
set name=variant.debug value=false value=true variant.arch=sparc
set name=variant.debug value=false variant.arch=arm\
""" % self.published_debug[4], # pkg://os.org/tree@1.0-0
                }

                repo = self.get_repo(repodir)
                for f in nlist:
                        with open(repo.manifest(f), "rb") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                # Cleanup.
                shutil.rmtree(repodir)


if __name__ == "__main__":
        unittest.main()
