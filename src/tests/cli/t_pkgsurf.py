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
# Copyright (c) 2013, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.digest as digest
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import shutil
import subprocess
import tempfile
import unittest

class TestPkgsurf(pkg5unittest.ManyDepotTestCase):
        # Cleanup after every test.
        persistent_setup = True

        # The 1.0 version of each package will be in the reference repo,
        # the 2.0 version in the target.
        # Since we publish the expected package to an additional repo, we have
        # to set the timestamps to make sure the target and expected packages
        # are equal.

        # The test cases are mainly in the different types of packages we
        # have in the repo.

        # Test cases:

        # Pkg with no content change, should be reversioned.
        # Pkg has all sorts of actions to make sure everything gets moved
        # correctly.
        tiger_ref = """
            open tiger@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/bat
            add dir mode=0755 owner=root group=bin path=/usr/tiger
            add file tmp/sting mode=0444 owner=root group=bin path=/usr/tiger/sting
            add link path=/usr/tiger/sting target=./stinger
            add hardlink path=/etc/bat target=/usr/tiger/bat
            add license tmp/copyright license=copyright
            add user username=Tiger group=galeocerdones home-dir=/export/home/Tiger
            add group groupname=galeocerdones gid=123
            close
        """

        tiger_targ = """
            open tiger@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/bat
            add dir mode=0755 owner=root group=bin path=/usr/tiger
            add file tmp/sting mode=0444 owner=root group=bin path=/usr/tiger/sting
            add link path=/usr/tiger/sting target=./stinger
            add hardlink path=/etc/bat target=/usr/tiger/bat
            add license tmp/copyright license=copyright
            add user username=Tiger group=galeocerdones home-dir=/export/home/Tiger
            add group groupname=galeocerdones gid=123
            close
        """

        tiger_exp = tiger_ref

        # Another basic pkg which gets reversioned
        sandtiger_ref = """
            open sandtiger@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/sandtiger
        """

        sandtiger_targ = """
            open sandtiger@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/sandtiger
        """

        sandtiger_exp = sandtiger_ref

        # Basic package with content change, should not be reversioned.
        hammerhead_ref = """
            open hammerhead@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/hammerhead
            close
        """

        hammerhead_targ = """
            open hammerhead@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/hammerhead
            close
        """

        hammerhead_exp = hammerhead_targ

        # Package has only dep change but dependency package changed,
        # should not be reversioned.
        blue_ref = """
            open blue@1.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/hammerhead@1.0 type=require
            close
        """

        blue_targ = """
            open blue@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        blue_exp = blue_targ

        # Same as above but let's try an additional level in the dep chain.
        bull_ref = """
            open bull@1.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/blue@1.0 type=require
            close
        """

        bull_targ = """
            open bull@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/blue@2.0 type=require
            close
        """

        bull_exp = bull_targ

        # Package has only dep change and dependency package didn't change,
        # should be reversioned.
        mako_ref = """
            open mako@1.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@1.0 type=require
            close
        """

        mako_targ = """
            open mako@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@2.0 type=require
            close
        """

        mako_exp = mako_ref

        # Same as above but let's try an additional level in the dep chain.
        white_ref = """
            open white@1.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/mako@1.0 type=require
            close
        """

        white_targ = """
            open white@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/mako@2.0 type=require
            close
        """

        white_exp = white_ref

        # Package has content change but depends on package which got reversioned,
        # dependencies should be fixed.
        # Pkg has all sorts of actions to make sure everything gets moved
        # correctly.

        angel_ref = """
            open angel@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/angel
            add dir mode=0755 owner=root group=bin path=/usr/angel
            add file tmp/sting mode=0444 owner=root group=bin path=/usr/angel/sting
            add link path=/usr/angel/sting target=./stinger
            add hardlink path=/etc/bat target=/usr/angel/bat
            add license tmp/copyright license=copyright
            add user username=Angel group=squatinae home-dir=/export/home/Angel
            add group groupname=squatinae gid=123
            add depend fmri=pkg:/tiger@1.0 type=require
            add depend fmri=pkg:/hammerhead@1.0 type=require
            close
        """

        angel_targ = """
            open angel@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/angel
            add dir mode=0755 owner=root group=bin path=/usr/angel
            add file tmp/sting mode=0444 owner=root group=bin path=/usr/angel/sting
            add link path=/usr/angel/sting target=./stinger
            add hardlink path=/etc/bat target=/usr/angel/bat
            add license tmp/copyright license=copyright
            add user username=Angel group=squatinae home-dir=/export/home/Angel
            add group groupname=squatinae gid=123
            add depend fmri=pkg:/tiger@2.0 type=require
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        angel_exp = """
            open angel@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/angel
            add dir mode=0755 owner=root group=bin path=/usr/angel
            add file tmp/sting mode=0444 owner=root group=bin path=/usr/angel/sting
            add link path=/usr/angel/sting target=./stinger
            add hardlink path=/etc/bat target=/usr/angel/bat
            add license tmp/copyright license=copyright
            add user username=Angel group=squatinae home-dir=/export/home/Angel
            add group groupname=squatinae gid=123
            add depend fmri=pkg:/tiger@1.0 type=require
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        # Package has content change and depends on package which didn't get
        # reversioned, shouldn't be touched.

        horn_ref = """
            open horn@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/horn
            add depend fmri=pkg:/hammerhead@1.0 type=require
            close
        """

        horn_targ = """
            open horn@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/horn
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        horn_exp = horn_targ


        # Package has content change but has require-any dep on package which
        # got reversioned, dependencies should be fixed.

        lemon_ref = """
            open lemon@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/lemon
            add depend fmri=pkg:/angel@1.0 fmri=pkg:/tiger@1.0 type=require-any
            close
        """

        lemon_targ = """
            open lemon@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/lemon
            add depend fmri=pkg:/angel@2.0 fmri=pkg:/tiger@2.0 type=require-any
            close
        """

        lemon_exp = """
            open lemon@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/lemon
            add depend fmri=pkg:/angel@2.0 fmri=pkg:/tiger@1.0 type=require-any
            close
        """

        # Package has content change but has require-any dep on package which
        # got reversioned, however, the require-any dependency wasn't in the old
        # version. The version of the pkg in the ref repo should be substituted
        # for tiger but not for sandtiger (since dep pkg is still successor of
        # dep FMRI).

        leopard_ref = """
            open leopard@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/leopard
            add depend fmri=pkg:/blue@1.0 fmri=pkg:/angel@1.0 type=require-any
            close
        """

        leopard_targ = """
            open leopard@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/leopard
            add depend fmri=pkg:/blue@2.0 fmri=pkg:/angel@2.0 fmri=pkg:/tiger@2.0 fmri=pkg:/sandtiger@1.0 type=require-any
            close
        """

        leopard_exp = """
            open leopard@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/leopard
            add depend fmri=pkg:/blue@2.0 fmri=pkg:/angel@2.0 fmri=pkg:/tiger@1.0-0 fmri=pkg:/sandtiger@1.0 type=require-any
            close
        """

        # Package has no content change but dependency stem changed, should
        # always be treated as content change.
        blacktip_ref = """
            open blacktip@1.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@1.0 type=require
            close
        """

        blacktip_targ = """
            open blacktip@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        blacktip_exp = blacktip_targ

        # Package has no content change but dependency got added, should
        # always be treated as content change, other dependencies should be
        # adjusted.
        whitetip_ref = """
            open whitetip@1.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@1.0 type=require
            close
        """

        whitetip_targ = """
            open whitetip@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@2.0 type=require
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        whitetip_exp = """
            open whitetip@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@1.0 type=require
            add depend fmri=pkg:/hammerhead@2.0 type=require
            close
        """

        # Package has no content change but a change in an attribute,
        # should be treated as content change by default but reversioned if
        # proper CLI options are given (goblin_exp is just for the default
        # behavior, gets modified in actual test case)

        goblin_ref = """
            open goblin@1.0,5.11-0:20000101T000000Z
            add set name=info.home value="deep sea"
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/goblin
            close
        """

        goblin_targ = """
            open goblin@2.0,5.11-0:20000101T000000Z
            add set name=info.home value="deeper sea"
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/goblin
            close
        """

        goblin_exp = goblin_targ

        # Package only found in target, not in ref, with dependency on
        # reversioned package. Dependency should be fixed.
        reef_targ = """
            open reef@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/reef
            add depend fmri=pkg:/tiger@2.0 type=require
            close
        """

        reef_exp = """
            open reef@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/reef
            add depend fmri=pkg:/tiger@1.0-0 type=require
            close
        """

        # Package is exactly the same as in ref repo, shouldn't be touched
        sandbar_targ = """
            open sandbar@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/sandbar
            close
        """

        sandbar_ref = """
            open sandbar@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/sandbar
            close
        """

        sandbar_exp = sandbar_ref

        # Packages with circular dependency and no change in dep chain.
        greenland_ref = """
            open greenland@1.0,5.11-0:20000101T000000Z
            add depend fmri=sleeper@1.0 type=require
            close
        """

        greenland_targ = """
            open greenland@2.0,5.11-0:20000101T000000Z
            add depend fmri=sleeper@2.0 type=require
            close
        """

        greenland_exp = greenland_ref

        sleeper_ref = """
            open sleeper@1.0,5.11-0:20000101T000000Z
            add depend fmri=greenland@1.0 type=require
            close
        """
        sleeper_targ = """
            open sleeper@2.0,5.11-0:20000101T000000Z
            add depend fmri=greenland@2.0 type=require
            close
        """

        sleeper_exp = sleeper_ref


        # Check for correct handling of Varcets. Pkg contains same dep FMRI stem
        # twice. It also covers the case where a facet changes and the tool has
        # to sustitute the version in the ref repo (sandtiger case).
        whale_ref = """
            open whale@1.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0444 owner=root group=bin path=/etc/whale
            add depend fmri=pkg:/tiger@1.0 facet.version-lock=True type=require
            add depend fmri=pkg:/tiger type=require
            add depend fmri=pkg:/sandtiger@1.0 facet.version-lock=False type=require
            close
        """

        whale_targ = """
            open whale@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/whale
            add depend fmri=pkg:/tiger@2.0 facet.version-lock=True type=require
            add depend fmri=pkg:/tiger type=require
            add depend fmri=pkg:/sandtiger@2.0 facet.version-lock=True type=require
            close
        """

        whale_exp = """
            open whale@2.0,5.11-0:20000101T000000Z
            add file tmp/bat mode=0644 owner=root group=bin path=/etc/whale
            add depend fmri=pkg:/tiger@1.0 facet.version-lock=True type=require
            add depend fmri=pkg:/tiger type=require
            add depend fmri=pkg:/sandtiger@1.0-0 facet.version-lock=True type=require
            close
        """

        # Pkg in ref repo is newer than the one in target.
        # Should not be reversioned.
        thresher_ref = """
            open thresher@2.0,5.11-0:20000101T000000Z
            close
        """

        thresher_targ = """
            open thresher@1.0,5.11-0:20000101T000000Z
            close
        """

        thresher_exp = thresher_targ

        # Package only found in target, not in ref.
        # Package has a dep on a reversioned pkg, but the reversioned pkg is
        # still a successor of the dep FMRI.
        # The dep should not be changed.
        bamboo_targ = """
            open bamboo@2.0,5.11-0:20000101T000000Z
            add depend fmri=pkg:/tiger@1 type=require
            close
        """

        bamboo_exp = bamboo_targ


        # Create some packages for an additional publisher
        humpback_targ = """
            open pkg://cetacea/humpback@2.0,5.11-0:20000101T000000Z
            close
        """

        humpback_ref = """
            open pkg://cetacea/humpback@1.0,5.11-0:20000101T000000Z
            close
        """

        humpback_exp = humpback_targ


        misc_files = [ "tmp/bat", "tmp/sting", "tmp/copyright" ]

        pkgs = ["tiger", "sandtiger", "hammerhead", "blue", "bull", "mako",
            "white", "angel", "horn", "lemon", "leopard", "blacktip",
            "whitetip", "goblin", "reef", "sandbar", "greenland", "sleeper",
            "whale", "thresher", "bamboo"]

        def setUp(self):
                """Start 3 depots, 1 for reference repo, 1 for the target and
                1 which should be equal to the reversioned target.
                """

                self.ref_pkgs = []
                self.targ_pkgs = []
                self.exp_pkgs = []
                for s in self.pkgs:
                        ref = s + "_ref"
                        targ = s + "_targ"
                        exp = s + "_exp"
                        try:
                                self.ref_pkgs.append(getattr(self, ref))
                        except AttributeError:
                                # reef_ref, bamboo_ref don't exist intentionally
                                pass
                        self.targ_pkgs.append(getattr(self, targ))
                        self.exp_pkgs.append(getattr(self, exp))

                pkg5unittest.ManyDepotTestCase.setUp(self, ["selachii",
                    "selachii", "selachii", "selachii"], start_depots=True)

                self.make_misc_files(self.misc_files)

                self.dpath1 = self.dcs[1].get_repodir()
                self.durl1 = self.dcs[1].get_depot_url()
                self.published_ref = self.pkgsend_bulk(self.dpath1,
                    self.ref_pkgs)

                self.dpath2 = self.dcs[2].get_repodir()
                self.durl2 = self.dcs[2].get_depot_url()
                self.published_targ = self.pkgsend_bulk(self.dpath2,
                    self.targ_pkgs)

                self.dpath3 = self.dcs[3].get_repodir()
                self.durl3 = self.dcs[3].get_depot_url()
                self.published_exp = self.pkgsend_bulk(self.dpath3,
                    self.exp_pkgs)

                # keep a tmp repo to copy the target into for each new test
                self.dpath_tmp = self.dcs[4].get_repodir()

        def test_0_options(self):
                """Check for correct input handling."""
                self.pkgsurf("-x", exit=2)
                self.pkgsurf("-s pacific", exit=2)
                self.pkgsurf("-s pacific -r atlantic arctic antarctic", exit=2)
                # invalid patterns for -c
                self.pkgsurf("-n -s {0} -r {1} -c tiger@2.0".format(self.dpath2,
                    self.dpath1), exit=1)
                self.pkgsurf("-n -s {0} -r {1} -c tig".format(self.dpath2,
                    self.dpath1), exit=1)

                # Check that -n doesn't modify repo.
                tmpdir = tempfile.mkdtemp(dir=self.test_root)
                path = os.path.join(tmpdir, "repo")
                shutil.copytree(self.dpath2, path)

                self.pkgsurf("-s {0} -r {1} -n".format(self.dpath2, self.dpath1))

                ret = subprocess.call(["/usr/bin/gdiff", "-Naur", path,
                    self.dpath2])
                self.assertTrue(ret==0)

        def test_1_basics(self):
                """Test basic resurfacing operation."""

                # Copy target repo to tmp repo
                self.copy_repository(self.dpath2, self.dpath_tmp,
                    { "selachii": "selachii" })
                # The new repository won't have a catalog, so rebuild it.
                self.dcs[4].get_repo(auto_create=True).rebuild()
                #self.assertTrue(False)

                # Check that empty repos get handled correctly
                tempdir = tempfile.mkdtemp(dir=self.test_root)
                # No repo at all
                self.pkgsurf("-s {0} -r {1}".format(tempdir, self.dpath1), exit=1)
                self.pkgsurf("-s {0} -r {1}".format(self.dpath1, tempdir), exit=1)

                # Repo empty
                self.pkgrepo("create -s {0}".format(tempdir))
                self.pkgsurf("-s {0} -r {1}".format(tempdir, self.dpath1), exit=1)
                self.pkgsurf("-s {0} -r {1}".format(self.dpath1, tempdir), exit=1)

                # No packages
                self.pkgrepo("add-publisher -s {0} selachii".format(tempdir))
                self.pkgsurf("-s {0} -r {1}".format(tempdir, self.dpath1))
                self.assertTrue("No packages to reversion." in self.output)
                self.pkgsurf("-s {0} -r {1}".format(self.dpath1, tempdir))
                self.assertTrue("No packages to reversion." in self.output)
                shutil.rmtree(tempdir)

                # Now check if it actually works.
                self.pkgsurf("-s {0} -r {1}".format(self.dpath_tmp, self.dpath1))

                ref_repo = self.get_repo(self.dpath1)
                targ_repo = self.get_repo(self.dpath_tmp)
                exp_repo = self.get_repo(self.dpath3)
                for s in self.published_exp:
                        f = fmri.PkgFmri(s, None)
                        targ = targ_repo.manifest(f)

                        # Load target manifest
                        targm = manifest.Manifest()
                        targm.set_content(pathname=targ)

                        # Load expected manifest
                        exp = exp_repo.manifest(f)
                        expm = manifest.Manifest()
                        expm.set_content(pathname=exp)

                        ta, ra, ca = manifest.Manifest.comm([targm, expm])
                        self.debug("{0}: {1:d} {2:d}".format(str(s), len(ta), len(ra)))

                        self.assertEqual(0, len(ta), "{0} had unexpected actions:"
                            " \n{1}".format(s, "\n".join([str(x) for x in ta])))
                        self.assertEqual(0, len(ra), "{0} had missing actions: "
                            "\n{1}".format(s, "\n".join([str(x) for x in ra])))

                # Check that pkgsurf informed the user that there is a newer
                # version of a pkg in the ref repo.
                self.assertTrue("Packages with successors" in self.output)

                # Check that ignore option works.
                # Just run again and see if goblin pkg now gets reversioned.
                self.pkgsurf("-s {0} -r {1} -i info.home".format(self.dpath_tmp,
                    self.dpath1))

                # Find goblin package
                for s in self.published_ref:
                        if "goblin" in s:
                                break
                f = fmri.PkgFmri(s, None)
                targ = targ_repo.manifest(f)
                ref = ref_repo.manifest(f)
                self.assertEqual(misc.get_data_digest(targ,
                    hash_func=digest.DEFAULT_HASH_FUNC),
                    misc.get_data_digest(ref,
                    hash_func=digest.DEFAULT_HASH_FUNC))

                # Check that running the tool again doesn't find any pkgs
                # to reversion. Use http for accessing reference repo this time.
                self.pkgsurf("-s {0} -r {1}".format(self.dpath_tmp, self.durl1))
                self.assertTrue("No packages to reversion." in self.output)

        def test_2_publishers(self):
                """Tests for correct publisher handling."""

                # Copy target repo to tmp repo
                self.copy_repository(self.dpath2, self.dpath_tmp,
                    { "selachii": "selachii" })
                # The new repository won't have a catalog, so rebuild it.
                self.dcs[4].get_repo(auto_create=True).rebuild()

                # Add a package from a different publisher to target
                self.pkgsend_bulk(self.dpath_tmp, [self.humpback_targ])

                # Test that unknown publisher in ref repo gets skipped without
                # issue.
                self.pkgsurf("-s {0} -r {1} -n".format(self.dpath_tmp,
                    self.dpath1))
                # Test that we also print a skipping notice
                self.assertTrue("Skipping" in self.output)

                # Test that we fail if we specify a publisher which is not in
                # reference repo.
                self.pkgsurf("-s {0} -r {1} -p cetacea -n".format(self.dpath_tmp,
                    self.dpath1), exit=1)

                # Now add packages from the 2nd pub to the ref repo
                self.pkgsend_bulk(self.durl1, [self.humpback_ref])

                # Test that only specified publisher is processed
                self.pkgsurf("-s {0} -r {1} -p cetacea -n".format(self.dpath_tmp,
                    self.dpath1))
                self.assertFalse("selachii" in self.output)
                self.pkgsurf("-s {0} -r {1} -p selachii -n".format(self.dpath_tmp,
                    self.dpath1))
                self.assertFalse("cetacea" in self.output)

                # Now do an actual resurfacing of just one publisher
                self.pkgsurf("-s {0} -r {1} -p selachii".format(self.dpath_tmp,
                    self.dpath1))
                # Check if we see anything about the unspecified publisher
                # in the output.
                self.assertFalse("cetacea" in self.output)
                # Check if we didn't reversion packages of the unspecified
                # publisher.
                self.pkgrepo("-s {0} list humpback".format(self.dpath_tmp))
                self.assertTrue("2.0" in self.output)

        def test_3_override_pkgs(self):
                """Test for correct handling of user specified packages which
                should not get reversioned."""

                # Copy target repo to tmp repo
                self.copy_repository(self.dpath2, self.dpath_tmp,
                    { "selachii": "selachii" })
                # The new repository won't have a catalog, so rebuild it.
                self.dcs[4].get_repo(auto_create=True).rebuild()

                # Check multiple patterns with globbing
                self.pkgsurf("-s {0} -r {1} -c *iger".format(self.dpath_tmp,
                    self.dpath1))
                self.pkgrepo("-s {0} list tiger".format(self.dpath_tmp))
                self.assertTrue("2.0" in self.output)
                self.pkgrepo("-s {0} list sandtiger".format(self.dpath_tmp))
                self.assertTrue("2.0" in self.output)

                # Check specific name.
                self.pkgsurf("-s {0} -r {1} -c tiger".format(self.dpath_tmp,
                    self.dpath1))
                self.pkgrepo("-s {0} list tiger".format(self.dpath_tmp))
                self.assertTrue("2.0" in self.output)


if __name__ == "__main__":
                unittest.main()
