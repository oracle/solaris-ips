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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
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
import unittest
import zlib

import sys

class TestUtilMerge(pkg5unittest.ManyDepotTestCase):
        persistent_setup = True

        scheme10 = """
            open scheme@1.0,5.11-0
            add file tmp/sparc-only mode=0444 owner=root group=bin path=/etc/tree
            close
        """

        tree10 = """
            open tree@1.0,5.11-0
            add file tmp/sparc-only mode=0444 owner=root group=bin path=/etc/tree
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

        silverA = """
            open silver@1.0,5.11-0
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/sh mode=0444 owner=root group=bin path=/etc/tree pkg.merge.blend=arch
            close
        """
        silverB = """
            open silver@1.0,5.11-0
            add file tmp/bronze1 mode=0555 owner=root group=bin path=/etc/bronze1
           close
        """

        multiA = """
            open gold@1.0,5.11-0
            add file tmp/sparc1 mode=0444 owner=root group=bin path=/etc/debug-notes pkg.merge.blend=arch
            add file tmp/sparc2 mode=0444 owner=root group=bin path=/etc/sparc/debug-notes
            add file tmp/sparc3 mode=0444 owner=root group=bin path=/etc/binary
            add depend type=require-any fmri=foo fmri=bar
            close
        """

        multiB = """
            open gold@1.0,5.11-0
            add file tmp/sparc4 mode=0444 owner=root group=bin path=/etc/everywhere-notes pkg.merge.blend=arch pkg.merge.blend=debug
            add file tmp/sparc4 mode=0444 owner=root group=bin path=/etc/binary
            add depend type=require-any fmri=foo fmri=bar
            close
        """

        multiC = """
            open gold@1.0,5.11-0
            add file tmp/i3862 mode=0444 owner=root group=bin path=/etc/binary
            add depend type=require-any fmri=foo fmri=bar
            close
        """

        multiD = """
            open gold@1.0,5.11-0
            add file tmp/i3861 mode=0444 owner=root group=bin path=/etc/nondebug-notes pkg.merge.blend=variant.arch
            add file tmp/i3863 mode=0444 owner=root group=bin path=/etc/binary
            add depend type=require-any fmri=foo fmri=bar
            close
        """

        tinA = """
            open tin@1.0,5.11-0
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/sh mode=0444 owner=root group=bin path=/etc/tree pkg.merge.blend=arch
            close
        """
        tinB = """
            open tin@1.0,5.11-0
            add file tmp/bronze1 mode=0555 owner=root group=bin path=/etc/bronze1
            add file tmp/scheme mode=0444 owner=root group=bin path=/etc/tree pkg.merge.blend=arch
           close
        """

        mediatorPPC = """
            open mediator@1.0,5.11-0
            add link path=wombat target=blue mediator=color mediator-implementation=blue pkg.merge.blend=arch
            add link path=wombat target=red mediator=color mediator-implementation=red pkg.merge.blend=arch
            add link path=wombat target=green mediator=color mediator-implementation=green pkg.merge.blend=arch
            add link path=wombat target=orange mediator=color mediator-implementation=orange pkg.merge.blend=arch
            add link path=aardvark target=1 mediator=version mediator-version=1 pkg.merge.blend=arch
            add link path=aardvark target=2 mediator=version mediator-version=2 pkg.merge.blend=arch
            add link path=aardvark target=3 mediator=version mediator-version=3 pkg.merge.blend=arch
            add link path=aardvark target=4 mediator=version mediator-version=4 pkg.merge.blend=arch
            close
        """

        mediatorARM = """
            open mediator@1.0,5.11-0
            add link path=wombat target=teal mediator=color mediator-implementation=teal pkg.merge.blend=arch
            add link path=wombat target=pink mediator=color mediator-implementation=pink pkg.merge.blend=arch
            add link path=wombat target=mauve mediator=color mediator-implementation=mauve pkg.merge.blend=arch
            add link path=wombat target=taupe mediator=color mediator-implementation=taupe pkg.merge.blend=arch
            add link path=aardvark target=5 mediator=version mediator-version=5 pkg.merge.blend=arch
            add link path=aardvark target=6 mediator=version mediator-version=6 pkg.merge.blend=arch
            add link path=aardvark target=7 mediator=version mediator-version=7 pkg.merge.blend=arch
            add link path=aardvark target=8 mediator=version mediator-version=8 pkg.merge.blend=arch
            close
        """

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
            "tmp/bronze2", "tmp/copyright2", "tmp/copyright3", "tmp/libc.so.1",
            "tmp/sh", "tmp/scheme", "tmp/sparc-only", "tmp/sparc1", "tmp/sparc2",
            "tmp/sparc3", "tmp/sparc4", "tmp/i3861", "tmp/i3862", "tmp/i3863"]

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, 18 * ["os.org"])
                self.make_misc_files(self.misc_files)

                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.rurl4 = self.dcs[4].get_repo_url()
                self.rurl5 = self.dcs[5].get_repo_url()
                self.rurl6 = self.dcs[6].get_repo_url()

                # Empty repository.
                self.rurl7 = self.dcs[7].get_repo_url()

                # a bunch for testing blending
                self.rurl8 = self.dcs[8].get_repo_url()
                self.rurl9 = self.dcs[9].get_repo_url()
                self.rurl10 = self.dcs[10].get_repo_url()
                self.rurl11 = self.dcs[11].get_repo_url()
                self.rurl12 = self.dcs[12].get_repo_url()
                self.rurl13 = self.dcs[13].get_repo_url()

                # repositories which will contain several publishers
                self.rurl14 = self.dcs[14].get_repo_url()
                self.rurl15 = self.dcs[15].get_repo_url()

                # mediator testing
                self.rurl16 = self.dcs[16].get_repo_url()
                self.rurl17 = self.dcs[17].get_repo_url()

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

                self.published_blend = self.pkgsend_bulk(self.rurl8, (self.silverA,
                    self.tinA))
                time.sleep(1)
                self.published_blend += self.pkgsend_bulk(self.rurl9, (self.silverB,
                    self.tinB))

                time.sleep(1)
                self.published_blend += self.pkgsend_bulk(self.rurl10, (self.multiA,))
                time.sleep(1)
                self.published_blend += self.pkgsend_bulk(self.rurl11, (self.multiB,))
                time.sleep(1)
                self.published_blend += self.pkgsend_bulk(self.rurl12, (self.multiC,))
                time.sleep(1)
                self.published_blend += self.pkgsend_bulk(self.rurl13, (self.multiD,))

                # Publish to multiple repositories, maintaining lists of which
                # FMRIs are published to which repository.
                self.published_multi_14 = []
                self.published_multi_15 = []

                for url, record in [
                    (self.rurl14, self.published_multi_14),
                    (self.rurl15, self.published_multi_15)]:
                        time.sleep(1)
                        record += self.pkgsend_bulk(url, (self.scheme10))
                        time.sleep(1)
                        record += self.pkgsend_bulk(url, (self.tree10))

                        time.sleep(1)
                        record += self.pkgsend_bulk(url,
                            self.bronze20.replace("open ",
                            "open pkg://altpub/"))
                        time.sleep(1)
                        record += self.pkgsend_bulk(url,
                            (self.amber10.replace("open ",
                            "open pkg://altpub/")))
                        time.sleep(1)
                        record += self.pkgsend_bulk(url,
                            (self.multiA.replace("open ",
                            "open pkg://last/")))

                # add bronze20b to one repository so that we have at least one
                # package where more complex merging happens.
                time.sleep(1)
                self.published_multi_15 += self.pkgsend_bulk(self.rurl15,
                    self.bronze20b.replace("open ", "open pkg://altpub/"))

                # one of our source repositories also contains a newer
                # version of pkg:/gold (self.multi*)
                time.sleep(1)
                self.published_multi_15 += self.pkgsend_bulk(self.rurl15,
                    (self.multiB.replace("open ", "open pkg://last/")))

                # publish to our mediator repos
                self.published_16 = self.pkgsend_bulk(self.rurl16,
                    (self.mediatorPPC))
                self.published_17 = self.pkgsend_bulk(self.rurl17,
                    (self.mediatorARM))

        def test_0_options(self):
                """Verify that pkgmerge gracefully fails when given bad option
                values."""

                # Should fail because no source was specified.
                self.pkgmerge(" ".join([
                    "-d {0}".format(self.rurl2),
                ]), exit=2)

                # Should fail because no destination was specified.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.rurl2),
                ]), exit=2)

                # Should fail because variant for source was not provided.
                self.pkgmerge(" ".join([
                    "-s {0}".format(self.rurl1),
                    "-d {0}".format(self.rurl2),
                ]), exit=2)

                # Should fail because only source variant was provided.
                self.pkgmerge(" ".join([
                    "-s arch=i386",
                    "-d {0}".format(self.rurl2),
                ]), exit=2)

                # Should fail because user did not specify the same variants
                # for every source.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,{0}".format(self.dcs[1].get_repodir()),
                    "-s arch=i386,debug=true,{0}".format(self.dcs[2].get_repodir()),
                    "-d {0}".format(self.rurl7)
                ]), exit=2)

                # Should fail because user did not specify a source for all
                # variant combinations (e.g. i386 & arm debug).
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[1].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[2].get_repodir()),
                    "-s arch=arm,debug=false,{0}".format(self.dcs[3].get_repodir()),
                    "-s arch=sparc,debug=true,{0}".format(self.dcs[4].get_repodir()),
                    "-d {0}".format(self.rurl7)
                ]), exit=2)

                # Should fail because source is not a repository.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.test_root),
                    "-d {0}".format(self.rurl2),
                ]), exit=1)

                # Should fail because destination is not a repository.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-d {0}".format(self.test_root),
                ]), exit=1)

                # Should fail because of no matching -p publishers.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-d {0} -p noodles".format(self.test_root),
                ]), exit=1)

                # Create the target repository.
                repodir = os.path.join(self.test_root, "test_0_repo")
                self.create_repo(repodir)

                # Should fail because of no matching packages.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.rurl1),
                    "-d {0} nomatching".format(repodir),
                ]), exit=1)
                shutil.rmtree(repodir)

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
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-d {0}".format(repodir),
                    "-n",
                ]))

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-d {0}".format(repodir),
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
set name=pkg.fmri value={0}
set name=variant.arch value=i386\
""".format(self.published[7]), # pkg://os.org/amber@2.0-0
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
set name=pkg.fmri value={0}
set name=variant.arch value=i386\
""".format(self.published[9]) # pkg://os.org/bronze@2.0-0
                }

                for f in cat.fmris():
                        with open(repo.manifest(f), "r") as m:
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
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-d {0}".format(repodir),
                    "-n",
                    "amber@latest",
                ]))

                # Merge the packages.
                self.pkgmerge(" ".join([
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-d {0}".format(repodir),
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
                        with open(repo.manifest(f), "r") as m:
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
                    "-s arch=sparc,{0}".format(repodir),
                    "-d {0}".format(junk_repodir),
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
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-s arch=sparc,{0}".format(self.rurl1),
                    "-d {0}".format(repodir)
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                nlist = {}
                for s in self.published[:10]:
                        f = fmri.PkgFmri(s)
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
set name=pkg.fmri value={0}
set name=variant.arch value=i386 value=sparc\
""".format(self.published[7]), # pkg://os.org/amber@2.0-0
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
set name=pkg.fmri value={0}
set name=variant.arch value=i386 value=sparc\
""".format(self.published[9]), # pkg://os.org/bronze@2.0-0
                    "scheme": """\
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14
set name=pkg.fmri value={0}
set name=variant.arch value=sparc\
""".format(self.published[5]), # pkg://os.org/scheme@1.0-0
                    "tree": """\
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14
set name=pkg.fmri value={0}
set name=variant.arch value=sparc\
""".format(self.published[4]), # pkg://os.org/tree@1.0-0
               }

                for f in nlist:
                        with open(repo.manifest(f), "r") as m:
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
                    "-s arch=sparc,{0}".format(self.rurl1),
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-s arch=arm,{0}".format(self.rurl3),
                    "-d {0}".format(repodir)
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                nlist = {}
                for s in self.published:
                        f = fmri.PkgFmri(s)
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
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386 value=arm\
""".format(self.published[11]), # pkg://os.org/amber@2.0-0
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
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386 value=arm\
""".format(self.published[13]), # pkg://os.org/bronze@2.0-0
                    "scheme": """\
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14
set name=pkg.fmri value={0}
set name=variant.arch value=sparc\
""".format(self.published[5]), # pkg://os.org/scheme@1.0-0
                    "tree": """\
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=arm\
""".format(self.published[14]), # pkg://os.org/tree@1.0-0
               }

                for f in nlist:
                        with open(repo.manifest(f), "r") as m:
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
                    "-s arch=sparc,{0}".format(self.rurl1),
                    "-s arch=i386,{0}".format(self.rurl2),
                    "-s arch=arm,{0}".format(self.rurl3),
                    "-d {0}".format(repodir),
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
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386 value=arm\
""".format(self.published[10]) # pkg://os.org/amber@1.0-0

                # Verify that each package was merged correctly.
                for f in cat.fmris():
                        with open(repo.manifest(f), "r") as m:
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
                        rdir = os.path.join(self.test_root, "3{0}_repo".format(arch))
                        self.create_repo(rdir)

                        ndrepo = self.dcs[i + 1].get_repodir()
                        drepo = self.dcs[i + 4].get_repodir()

                        # Merge the packages.
                        self.pkgmerge(" ".join([
                            "-s debug=false,{0}".format(ndrepo),
                            "-s variant.debug=true,{0}".format(drepo),
                            "-d {0}".format(rdir)
                        ]))

                # Now merge all of the debug/non-debug repositories.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,{0}".format(os.path.join(self.test_root,
                        "3sparc_repo")),
                    "-s arch=i386,{0}".format(os.path.join(self.test_root,
                        "3i386_repo")),
                    "-s arch=arm,{0}".format(os.path.join(self.test_root,
                        "3arm_repo")),
                    "-d {0}".format(repodir),
                ]))

                # Get target repository catalog.
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")

                # Verify the list of expected packages in the target repository.
                nlist = {}
                for s in self.published + self.published_debug:
                        f = fmri.PkgFmri(s)
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
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386 value=arm
set name=variant.debug value=false value=true\
""".format(self.published_debug[11]), # pkg://os.org/amber@2.0-0
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
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386 value=arm
set name=variant.debug value=false value=true\
""".format(self.published_debug[13]), # pkg://os.org/bronze@2.0-0
                    "scheme": """\
file 3a06aa547ffe0186a2b9db55b8853874a048fb47 chash=ab50364de4ce8f847d765d402d80e37431e1f0aa group=bin mode=0444 owner=root path=etc/tree pkg.csize=40 pkg.size=20 variant.debug=true
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14 variant.debug=false
set name=pkg.fmri value={0}
set name=variant.arch value=sparc
set name=variant.debug value=false value=true\
""".format(self.published_debug[5]), # pkg://os.org/scheme@1.0-0
                    "tree": """\
file 3a06aa547ffe0186a2b9db55b8853874a048fb47 chash=ab50364de4ce8f847d765d402d80e37431e1f0aa group=bin mode=0444 owner=root path=etc/tree pkg.csize=40 pkg.size=20 variant.debug=true
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14 variant.debug=false
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=arm
set name=variant.debug value=false value=true\
""".format(self.published_debug[14]), # pkg://os.org/tree@1.0-0
               }

                for f in nlist:
                        with open(repo.manifest(f), "r") as m:
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
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[1].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[2].get_repodir()),
                    "-s arch=arm,debug=false,{0}".format(self.dcs[3].get_repodir()),
                    "-s arch=sparc,debug=true,{0}".format(self.dcs[4].get_repodir()),
                    "-s arch=i386,debug=true,{0}".format(self.dcs[5].get_repodir()),
                    "-s arch=arm,debug=true,{0}".format(self.dcs[6].get_repodir()),
                    "-d {0}".format(repodir)
                ]))

                repo = self.get_repo(repodir)
                for f in nlist:
                        with open(repo.manifest(f), "r") as m:
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
                        f = fmri.PkgFmri(s)
                        if f.pkg_name not in nlist or \
                            f.version > nlist[f.pkg_name].version:
                                nlist[f.pkg_name] = f
                nlist = sorted(nlist.values())

                self.create_repo(repodir)
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[1].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[2].get_repodir()),
                    "-s arch=arm,debug=false,{0}".format(self.dcs[3].get_repodir()),
                    "-s arch=sparc,debug=true,{0}".format(self.dcs[4].get_repodir()),
                    # Explicitly state debug packages don't exist for these
                    # arch values by using an empty repository.
                    "-s arch=i386,debug=true,{0}".format(self.dcs[7].get_repodir()),
                    "-s arch=arm,debug=true,{0}".format(self.dcs[7].get_repodir()),
                    "-d {0}".format(repodir)
                ]))

                # Verify that each package was merged correctly.
                merged_expected = {
                    "amber": """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value={0}
set name=variant.arch value=i386 value=arm value=sparc
set name=variant.debug value=false value=true variant.arch=sparc
set name=variant.debug value=false variant.arch=arm
set name=variant.debug value=false variant.arch=i386\
""".format(self.published_debug[1]), # pkg://os.org/amber@2.0-0
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
set name=pkg.fmri value={0}
set name=variant.arch value=i386 value=arm value=sparc
set name=variant.debug value=false value=true variant.arch=sparc
set name=variant.debug value=false variant.arch=arm
set name=variant.debug value=false variant.arch=i386\
""".format(self.published_debug[3]), # pkg://os.org/bronze@2.0-0
                    "scheme": """\
file 3a06aa547ffe0186a2b9db55b8853874a048fb47 chash=ab50364de4ce8f847d765d402d80e37431e1f0aa group=bin mode=0444 owner=root path=etc/tree pkg.csize=40 pkg.size=20 variant.debug=true
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14 variant.debug=false
set name=pkg.fmri value={0}
set name=variant.arch value=sparc
set name=variant.debug value=false value=true\
""".format(self.published_debug[5]), # pkg://os.org/scheme@1.0-0
                    "tree": """\
file 3a06aa547ffe0186a2b9db55b8853874a048fb47 chash=ab50364de4ce8f847d765d402d80e37431e1f0aa group=bin mode=0444 owner=root path=etc/tree pkg.csize=40 pkg.size=20 variant.arch=sparc variant.debug=true
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14 variant.arch=arm
file 3b7cee8797632f83a11b66d028016946b4fa47fa chash=00621927edeb8e5b96ef63a93b4c5d125f2a3298 group=bin mode=0444 owner=root path=etc/tree pkg.csize=34 pkg.size=14 variant.arch=sparc variant.debug=false
set name=pkg.fmri value={0}
set name=variant.arch value=arm value=sparc
set name=variant.debug value=false value=true variant.arch=sparc
set name=variant.debug value=false variant.arch=arm\
""".format(self.published_debug[4]), # pkg://os.org/tree@1.0-0
               }

                repo = self.get_repo(repodir)
                for f in nlist:
                        with open(repo.manifest(f), "r") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                        expected = merged_expected[f.pkg_name]
                        self.assertEqualDiff(expected, actual)

                # Cleanup.
                shutil.rmtree(repodir)

        def test_4_blend(self):
                """Make sure simple blending works"""

                # Create the target repository.
                repodir = os.path.join(self.test_root, "4merge_repo")
                self.create_repo(repodir)

                # Merge the silver packages.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,{0}".format(self.rurl8),
                    "-s arch=i386,{0}".format(self.rurl9),
                    "-d {0} silver".format(repodir)
                ]))

                # get target repo
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")
                expected = """\
file 1abe1a7084720f501912eceb1312ddd799fb2a34 chash=ea7230676e13986491d7405c5a9298e074930575 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=37 pkg.size=17 variant.arch=sparc
file 1abe1a7084720f501912eceb1312ddd799fb2a34 chash=ea7230676e13986491d7405c5a9298e074930575 group=bin mode=0555 owner=root path=etc/bronze1 pkg.csize=37 pkg.size=17 variant.arch=i386
file 34f88965d55d3a730fa7683bc0f370fc6e42bf95 chash=66eebb69ee0299dcb495162336db81a3188de037 group=bin mode=0444 owner=root path=etc/tree pkg.csize=32 pkg.size=12
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386\
""".format(self.published_blend[2])

                for f in cat.fmris():
                        with open(repo.manifest(f), "r") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                self.assertEqualDiff(expected, actual)
                shutil.rmtree(repodir)

        def test_5_blend(self):
                """test duplicate action detection during blending"""
                repodir = os.path.join(self.test_root, "5merge_repo")
                self.create_repo(repodir)

               # Merge the tin packages - whoops
                self.pkgmerge(" ".join([
                    "-s arch=sparc,{0}".format(self.rurl8),
                    "-s arch=i386,{0}".format(self.rurl9),
                    "-d {0} tin".format(repodir)
                ]), exit=1)
                shutil.rmtree(repodir)

        def test_6_blend(self):
                """check complex blending"""
                repodir = os.path.join(self.test_root, "6merge_repo")
                self.create_repo(repodir)

                # merge the multi packages
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=true,{0}".format(self.dcs[10].get_repodir()),
                    "-s arch=i386,debug=true,{0}".format(self.dcs[12].get_repodir()),
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[11].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[13].get_repodir()),
                    "-d {0}".format(repodir)]))

                actual = self.get_manifest(repodir)
                expected = """\
depend fmri=foo fmri=bar type=require-any
file 24bb3b46361cf7d180d0227beea4f75a872b6ff4 chash=b91fb7bdd4d35779bbd70c6b0367198e48290373 group=bin mode=0444 owner=root path=etc/nondebug-notes pkg.csize=35 pkg.size=15 variant.debug=false
file 3dfdd5c4f64e2005e7913ba8444c8ee6fa70f238 chash=05beb59e279eb2c9146c6547f1c4b94536f4b2b9 group=bin mode=0444 owner=root path=etc/binary pkg.csize=35 pkg.size=15 variant.arch=i386 variant.debug=false
file 4c12fa38950b7a5580c2715725f0ea980354b407 chash=61801db07f048941675ab3951cace0899b571430 group=bin mode=0444 owner=root path=etc/binary pkg.csize=35 pkg.size=15 variant.arch=i386 variant.debug=true
file 6b7161cb29262ea4924a8874818da189bb70da09 chash=77e271370cec04931346c969a85d6af37c1ea83f group=bin mode=0444 owner=root path=etc/binary pkg.csize=36 pkg.size=16 variant.arch=sparc variant.debug=false
file 6b7161cb29262ea4924a8874818da189bb70da09 chash=77e271370cec04931346c969a85d6af37c1ea83f group=bin mode=0444 owner=root path=etc/everywhere-notes pkg.csize=36 pkg.size=16
file 9e837a70edd530a88c88f8a58b8a5bf2a8f3943c chash=d0323533586e1153bd1701254f45d2eb2c7eb0c4 group=bin mode=0444 owner=root path=etc/debug-notes pkg.csize=36 pkg.size=16 variant.debug=true
file a10f11b8559a723bea9ee0cf5980811a9d51afbb chash=9fb8079898da8a2a9faad65c8df4c4a42095f25a group=bin mode=0444 owner=root path=etc/sparc/debug-notes pkg.csize=36 pkg.size=16 variant.arch=sparc variant.debug=true
file aab699c6424ed1fc258b6b39eb113e624a9ee368 chash=43c3b9a83a112727264390002c3db3fcebec2e76 group=bin mode=0444 owner=root path=etc/binary pkg.csize=36 pkg.size=16 variant.arch=sparc variant.debug=true
set name=pkg.fmri value={0}
set name=variant.arch value=sparc value=i386
set name=variant.debug value=true value=false\
""".format(self.published_blend[-1])
                self.assertEqualDiff(expected, actual)
                shutil.rmtree(repodir)

        def test_7_multipub_merge(self):
                """Tests that we can merge packages from repositories with
                several publishers."""

                repodir = os.path.join(self.test_root, "7merge_repo")
                self.create_repo(repodir)

                # test dry run
                self.pkgmerge(" ".join([
                    "-n",
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]))

                # test dry run with selected publishers
                self.pkgmerge(" ".join([
                    "-p os.org",
                    "-p altpub",
                    "-n",
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]))

                # this should fail, as no -p noodles publisher exists in any of
                # the source repositories
                self.pkgmerge(" ".join([
                    "-p os.org",
                    "-p altpub",
                    "-p noodles",
                    "-n",
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]), exit=1)

                # now we want to perform the merge operations and validate the
                # results. This was the order we published packages to multi_15
                # 0  = pkg://os.org/scheme@1.0,5.11-0:20120920T085857Z
                # 1  = pkg://os.org/tree@1.0,5.11-0:20120920T085859Z
                # 2  = pkg://altpub/bronze@2.0,5.11-0:20120920T085902Z
                # 3  = pkg://altpub/amber@1.0,5.11-0:20120920T085904Z
                # 4  = pkg://last/gold@1.0,5.11-0:20120920T085906Z
                # 5  = pkg://altpub/bronze@2.0,5.11-0:20120920T085920Z
                # 6  = pkg://last/gold@1.0,5.11-0:20120920T085923Z

                # build a dictionary of the FMRIs we're interested in
                repo15_fmris = {
                    "osorg_scheme": self.published_multi_15[0],
                    "osorg_tree": self.published_multi_15[1],
                    "altpub_amber": self.published_multi_15[3],
                    # we published two versions of bronze and gold, use the
                    # latest FMRI
                    "altpub_bronze": self.published_multi_15[5],
                    "last_gold": self.published_multi_15[6]
                }

                # the some expected manifests we should get after merging.
                expected_osorg_scheme = """\
file 3a06aa547ffe0186a2b9db55b8853874a048fb47 chash=ab50364de4ce8f847d765d402d80e37431e1f0aa group=bin mode=0444 owner=root path=etc/tree pkg.csize=40 pkg.size=20
set name=pkg.fmri value={osorg_scheme}
set name=variant.arch value=sparc value=i386
set name=variant.debug value=false\
""".format(**repo15_fmris)
                expected_osorg_tree = """\
file 3a06aa547ffe0186a2b9db55b8853874a048fb47 chash=ab50364de4ce8f847d765d402d80e37431e1f0aa group=bin mode=0444 owner=root path=etc/tree pkg.csize=40 pkg.size=20
set name=pkg.fmri value={osorg_tree}
set name=variant.arch value=sparc value=i386
set name=variant.debug value=false\
""".format(**repo15_fmris)
                expected_altpub_amber = """\
depend fmri=pkg:/tree@1.0 type=require
set name=pkg.fmri value={altpub_amber}
set name=variant.arch value=sparc value=i386
set name=variant.debug value=false\
""".format(**repo15_fmris)
                expected_altpub_bronze = """\
depend fmri=pkg:/amber@2.0 type=require
depend fmri=pkg:/scheme@1.0 type=require variant.arch=i386
dir group=bin mode=0755 owner=root path=etc
dir group=bin mode=0755 owner=root path=lib
file 1abe1a7084720f501912eceb1312ddd799fb2a34 chash=ea7230676e13986491d7405c5a9298e074930575 group=bin mode=0444 owner=root path=etc/bronze1 pkg.csize=37 pkg.size=17
file 34f88965d55d3a730fa7683bc0f370fc6e42bf95 chash=66eebb69ee0299dcb495162336db81a3188de037 group=bin mode=0555 owner=root path=usr/bin/sh pkg.csize=32 pkg.size=12
file 6d8f3b9498aa3bbe7db01189b88f1b71f4ce40ad chash=6f3882864ebd7fd1a09e0e7b889fdc524c8c8bb2 group=bin mode=0444 owner=root path=etc/amber2 pkg.csize=37 pkg.size=17 variant.arch=sparc
file 8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8 chash=6ff2f52d2f894f5c71fb8fdd3b214e22959fccbb group=bin mode=0555 owner=root path=lib/libc.bronze pkg.csize=33 pkg.size=13
file 91fa26695f9891b2d94fd72c31b640efb5589da5 chash=4eed1e5dc5ab131812da34dc148562e6833fa92b group=bin mode=0444 owner=root path=etc/scheme pkg.csize=36 pkg.size=16 variant.arch=i386
file cf68b26a90cb9a0d7510f24cfb8cf6d901cec34e chash=0eb6fe69c4492f801c35dcc9175d55f783cc64a2 group=bin mode=0444 owner=root path=A1/B2/C3/D4/E5/F6/bronzeA2 pkg.csize=38 pkg.size=18
hardlink path=lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
license 773b94a252723da43e8f969b4384701bcd41ce12 chash=e0715301fc211f6543ce0c444f4c34e38c70f70e license=copyright pkg.csize=40 pkg.size=20
link path=usr/bin/jsh target=./sh
set name=pkg.fmri value={altpub_bronze}
set name=variant.arch value=sparc value=i386
set name=variant.debug value=false\
""".format(**repo15_fmris)
                expected_last_gold = """\
depend fmri=foo fmri=bar type=require-any
file 6b7161cb29262ea4924a8874818da189bb70da09 chash=77e271370cec04931346c969a85d6af37c1ea83f group=bin mode=0444 owner=root path=etc/binary pkg.csize=36 pkg.size=16 variant.arch=i386
file 6b7161cb29262ea4924a8874818da189bb70da09 chash=77e271370cec04931346c969a85d6af37c1ea83f group=bin mode=0444 owner=root path=etc/everywhere-notes pkg.csize=36 pkg.size=16
file 9e837a70edd530a88c88f8a58b8a5bf2a8f3943c chash=d0323533586e1153bd1701254f45d2eb2c7eb0c4 group=bin mode=0444 owner=root path=etc/debug-notes pkg.csize=36 pkg.size=16
file a10f11b8559a723bea9ee0cf5980811a9d51afbb chash=9fb8079898da8a2a9faad65c8df4c4a42095f25a group=bin mode=0444 owner=root path=etc/sparc/debug-notes pkg.csize=36 pkg.size=16 variant.arch=sparc
file aab699c6424ed1fc258b6b39eb113e624a9ee368 chash=43c3b9a83a112727264390002c3db3fcebec2e76 group=bin mode=0444 owner=root path=etc/binary pkg.csize=36 pkg.size=16 variant.arch=sparc
set name=pkg.fmri value={last_gold}
set name=variant.arch value=sparc value=i386
set name=variant.debug value=false\
""".format(**repo15_fmris)

                # A dictionary of the expected package contents, keyed by FMRI
                expected = {
                    repo15_fmris["altpub_bronze"]: expected_altpub_bronze,
                    repo15_fmris["altpub_amber"]: expected_altpub_amber,
                    repo15_fmris["osorg_tree"]: expected_osorg_tree,
                    repo15_fmris["osorg_scheme"]: expected_osorg_scheme,
                    repo15_fmris["last_gold"]: expected_last_gold
                }

                def check_repo(repodir, keys, fmri_dic, expected):
                        """Check that packages corresponding to the list of
                        keys 'keys' to items in 'fmri_dic' are present in the
                        repository, and match the contents from the dictionary
                        'expected'.  We also check that the repository has no
                        packages other than those specified by 'keys', and no
                        more publishers than are present in those packages."""
                        sr = self.get_repo(repodir)
                        # check that the packages from 'keys' exist,
                        # and their content matches what we expect.
                        for key in keys:
                                f = fmri_dic[key]
                                with open(sr.manifest(f), "r") as manf:
                                        actual = "".join(
                                            sorted(l for l in manf)).strip()
                                self.assertEqualDiff(expected[f], actual)

                        # check that we have only the publishers used
                        # by packages from 'keys' in the repository
                        fmris = [fmri_dic[key] for key in keys]
                        pubs = set([fmri.PkgFmri(entry).get_publisher()
                            for entry in fmris])
                        known_pubs = set(
                            [p.prefix for p in sr.get_publishers()])
                        self.assertTrue(pubs == known_pubs,
                            "Repository at {0} didn't contain the "
                            "expected set of publishers")

                        # check that we have only the packages defined
                        # in 'keys' in the repository by walking all
                        # publishers, and all packages in the repository
                        for pub in sr.get_publishers():
                                cat = sr.get_catalog(pub=pub.prefix)
                                for f in cat.fmris():
                                        if f.get_fmri() not in fmris:
                                                self.assertTrue(False,
                                                    "{0} not in repository".format(f))

                # test merging all publishers.
                self.pkgmerge(" ".join([
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]))

                check_repo(repodir, repo15_fmris.keys(), repo15_fmris, expected)

                # test merging only altpub and os.org.
                shutil.rmtree(repodir)
                self.create_repo(repodir)
                self.pkgmerge(" ".join([
                    "-p altpub",
                    "-p os.org",
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]))

                check_repo(repodir, ["altpub_bronze", "altpub_amber",
                    "osorg_tree", "osorg_scheme"], repo15_fmris, expected)

                # test merging only altpub
                shutil.rmtree(repodir)
                self.create_repo(repodir)
                self.pkgmerge(" ".join([
                    "-p altpub",
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]))

                check_repo(repodir, ["altpub_bronze", "altpub_amber"],
                    repo15_fmris, expected)

                # this should exit with a 1, but we should get the same results
                # in the repository as last time.
                shutil.rmtree(repodir)
                self.create_repo(repodir)
                self.pkgmerge(" ".join([
                    "-p altpub",
                    "-p noodles",
                    "-s arch=sparc,debug=false,{0}".format(self.dcs[14].get_repodir()),
                    "-s arch=i386,debug=false,{0}".format(self.dcs[15].get_repodir()),
                    "-d {0}".format(repodir)]), exit=1)

                check_repo(repodir, ["altpub_bronze", "altpub_amber"],
                    repo15_fmris, expected)

        def test_8_mediators(self):
                """test to make sure mediator-mediated links are not detected as collisions
                in the same package or the merged package"""
                # Create the target repository.
                repodir = os.path.join(self.test_root, "8mediator_repo")
                self.create_repo(repodir)

                # Merge the two packages.
                self.pkgmerge(" ".join([
                        "-s arch=PPC,{0}".format(self.rurl16),
                        "-s arch=ARM,{0}".format(self.rurl17),
                    "-d {0} mediator".format(repodir)
                ]))

                # get target repo
                repo = self.get_repo(repodir)
                cat = repo.get_catalog(pub="os.org")
                expected = """\
link mediator=color mediator-implementation=blue path=wombat target=blue
link mediator=color mediator-implementation=green path=wombat target=green
link mediator=color mediator-implementation=mauve path=wombat target=mauve
link mediator=color mediator-implementation=orange path=wombat target=orange
link mediator=color mediator-implementation=pink path=wombat target=pink
link mediator=color mediator-implementation=red path=wombat target=red
link mediator=color mediator-implementation=taupe path=wombat target=taupe
link mediator=color mediator-implementation=teal path=wombat target=teal
link mediator=version mediator-version=1 path=aardvark target=1
link mediator=version mediator-version=2 path=aardvark target=2
link mediator=version mediator-version=3 path=aardvark target=3
link mediator=version mediator-version=4 path=aardvark target=4
link mediator=version mediator-version=5 path=aardvark target=5
link mediator=version mediator-version=6 path=aardvark target=6
link mediator=version mediator-version=7 path=aardvark target=7
link mediator=version mediator-version=8 path=aardvark target=8
set name=pkg.fmri value={0}
set name=variant.arch value=PPC value=ARM\
""".format(self.published_17[0])

                for f in cat.fmris():
                        with open(repo.manifest(f), "r") as m:
                                actual = "".join(sorted(l for l in m)).strip()
                self.assertEqualDiff(expected, actual)
                shutil.rmtree(repodir)


        def get_manifest(self, repodir, pubs=["os.org"]):
                repository = self.get_repo(repodir)
                actual = ""
                for pub in pubs:
                        cat = repository.get_catalog(pub=pub)
                        for f in cat.fmris():
                                with open(repository.manifest(f), "r") as m:
                                        actual += "".join(
                                            sorted(l for l in m)).strip()
                        actual += "\n"
                return actual.strip()

if __name__ == "__main__":
        unittest.main()
