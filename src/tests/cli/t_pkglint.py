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

# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import os.path
import shutil
import unittest
import tempfile

class TestPkglintBasics(pkg5unittest.CliTestCase):

        manifest = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
set name=test value=i386 variant.arch=sparc
"""
        # has two set actions, which we should catch
        broken_manifest = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
"""

        # has two set actions, one of which is linted
        linted_action = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=org.opensolaris.consolidation value=ON pkg.linted=True
set name=variant.arch value=i386 value=sparc
"""

        # has two set actions, one of which is linted
        linted_manifest = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.linted value=True
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
"""

        # for the rcfiles below, we also need to point the
        # info_classification_path field to the sections file we deliver in the
        # proto area
        module_exclusion_rc = """
[pkglint]
pkglint.exclude: pkg.lint.pkglint_manifest.PkgManifestChecker
info_classification_path: %s/usr/share/lib/pkg/opensolaris.org.sections
"""

        method_exclusion_rc = """
[pkglint]
pkglint.exclude: pkg.lint.pkglint_manifest.PkgManifestChecker.duplicate_sets
info_classification_path: %s/usr/share/lib/pkg/opensolaris.org.sections
"""

        low_noise_rc = """
[pkglint]
log_level = CRITICAL
info_classification_path: %s/usr/share/lib/pkg/opensolaris.org.sections
"""

        def setUp(self):                
                pkg5unittest.CliTestCase.setUp(self)

        def test_1_usage(self):
                """Tests that we show a usage message."""
                ret, output, err = self.pkglint("--help")
                self.assert_("Usage:" in output,
                    "No usage string printed")

        def test_2_badopts(self):
                """Tests that we exit with an error on wrong or missing args"""
                for opt in ["-x", "--asdf" ]:
                        ret, output, err = self.pkglint(opt, exit=2)

        def test_3_list(self):
                """Tests that -L prints headers and descriptions or methods."""
                for flag in ["-L", "-vL"]:
                        ret, output, err = self.pkglint(flag)
                        self.assert_("pkglint.dupaction001" in output,
                            "short name didn't appear in %s output" % flag)

                        self.assert_("NAME" in output,
                            "Header not printed in %s output" % flag)
                        if flag == "-vL":
                                self.assert_(
                                    "pkg.lint.pkglint_action.PkgDupActionChecker.duplicate_paths"
                                    in output,
                                    "verbose list output didn't show method")
                        elif flag == "-L":
                                self.assert_(
                                    "Paths should be unique." in output,
                                    "description didn't appear in -L output: %s" % output)

        def test_4_manifests(self):
                """Tests that we exit normally with a correct manifest."""
                mpath = self.make_manifest(self.manifest)
                self.pkglint(mpath)

        def test_5_broken_manifest(self):
                """Tests that we exit with an error when presented one or more
                broken manifests."""
                mpath = self.make_manifest(self.manifest)
                mpath1 = self.make_manifest(self.broken_manifest)
                self.pkglint(mpath1, exit=1)
                # only one of these is broken
                self.pkglint("%s %s" % (mpath, mpath1), exit=1)

        def test_6_rcfile(self):
                """Checks that check exclusion works, by testing a broken
                manifest, excluding checks designed to catch the fault.
                This tests part of the engine, as well as the -f handling
                in the CLI.
                """
                mpath1 = self.make_manifest(self.broken_manifest)
                self.make_misc_files({"rcfile": self.module_exclusion_rc %
                    pkg5unittest.g_proto_area})
                self.make_misc_files({"rcfile1": self.method_exclusion_rc %
                    pkg5unittest.g_proto_area})

                # verify we fail first
                self.pkglint("%s" % mpath1, exit=1)

                # now we should succeed
                self.pkglint("-f %s/rcfile %s" % (self.test_root,  mpath1),
                    testrc=False, exit=0)
                self.pkglint("-f %s/rcfile1 %s" % (self.test_root, mpath1),
                    exit=0)

                ret, output, err = self.pkglint("-f %s/rcfile -vL" %
                    self.test_root, testrc=False, exit=0)
                self.assert_(
                    "pkg.lint.pkglint_manifest.PkgManifestChecker.duplicate_sets"
                    in output, "List output missing excluded checker")
                self.assert_("Excluded checks:" in output)

                ret, output, err = self.pkglint("-f %s/rcfile1 -vL" %
                    self.test_root, testrc=False, exit=0)
                self.assert_(
                    "pkg.lint.pkglint_manifest.PkgManifestChecker.duplicate_sets"
                    in output, "List output missing excluded checker")
                self.assert_("Excluded checks:" in output)

        def test_7_linted(self):
                """Checks that the pkg.linted keyword works for actions and
                manifests.  While this tests the linted functionality of the
                engine, it's also a CLI test to ensure we report a zero
                exit code from a lint check that has emitted output, but
                doesn't indicate an error."""
                mpath1 = self.make_manifest(self.broken_manifest)
                linted_action_path = self.make_manifest(self.linted_action)
                linted_manifest_path = self.make_manifest(self.linted_manifest)

                # verify we fail first
                self.pkglint("%s" % mpath1, exit=1)

                # now we should succeed
                self.pkglint(linted_action_path, exit=0)
                self.pkglint(linted_manifest_path, exit=0)

        def test_8_verbose(self):
                """Checks that the -v flag works, overriding the log level
                in pkglintrc."""
                mpath = self.make_manifest(self.broken_manifest)

                # default log setting
                ret, output, err = self.pkglint("%s" % mpath, exit=1)
                self.assert_("Total number of checks found" not in output,
                    "verbose output detected in non-verbose mode")

                self.assert_("duplicate set actions" in err)

                ret, output_verbose, err = self.pkglint("-v %s" % mpath, exit=1)
                self.assert_("Total number of checks found" in output_verbose,
                    "verbose output not printed in verbose mode")
                self.assert_("duplicate set actions" in err)

                # override log setting in config file
                self.make_misc_files(
                    {"low_noise_rc": self.low_noise_rc})
                ret, output, err = self.pkglint("-f %s/low_noise_rc %s" %
                    (self.test_root, mpath), exit=0)
                self.assert_("Total number of checks found" not in output,
                    "verbose output detected in non-verbose mode")
                self.assert_("duplicate set actions" not in err)

                ret, output, err = self.pkglint("-v -f %s/low_noise_rc %s" %
                    (self.test_root, mpath), exit=1)
                self.assert_("Total number of checks found" in output,
                    "verbose output detected in non-verbose mode")
                self.assert_("duplicate set actions" in err)


class TestPkglintCliDepot(pkg5unittest.ManyDepotTestCase):
        """Tests that exercise the CLI aspect of dealing with repositories"""

        ref_mf = {}
        ref_mf["ref-sample1.mf"] = """
#
# A sample package which delivers several actions
#
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/passwd path=etc/passwd group=sys mode=0644 owner=root preserve=true
dir group=sys mode=0755 owner=root path=etc
"""

        ref_mf["ref-sample2.mf"] = """
#
# A sample package which delivers several actions
#
set name=pkg.fmri value=pkg://opensolaris.org/system/additional@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/motd group=sys mode=0644 owner=root path=etc/motd
dir group=sys mode=0755 owner=root path=etc
dir group=sys mode=0755 owner=root path=etc
"""

        ref_mf["ref-sample3.mf"] = """
#
# A sample package which delivers several actions
#
set name=pkg.fmri value=pkg://opensolaris.org/system/more@0.5.11,5.11-0.141
set name=pkg.description value="additional reference actions for pkglint"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=osnet
set name=variant.arch value=i386 value=sparc
file /etc/group group=sys mode=0644 owner=root path=etc/group
dir group=sys mode=0755 owner=root path=etc
"""

        lint_mf = {}

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["opensolaris.org",
                    "opensolaris.org"], start_depots=True)

                self.ref_uri = self.dcs[1].get_depot_url()
                self.lint_uri = self.dcs[2].get_depot_url()
                self.cache_dir = os.path.join(self.test_root, "pkglint-cache")

                paths = self.make_misc_files(self.ref_mf)

                for item in paths:
                        self.pkgsend(depot_url=self.ref_uri,
                            command="publish --fmri-in-manifest %s" % item)
                self.pkgsend(depot_url=self.ref_uri,
                            command="refresh-index")

        def test_1_invalid_uri(self):
                """ Tests that we can cope with bad URIs for both ref and
                lint repository arguments."""

                bad = ["htto://foobar", "https://nosuchhost", "file:/dev/null",
                    "file:///dev/null", "utternonsense"]

                cache = tempfile.mkdtemp("pkglint-cache", "", self.test_root)
                for uri in bad:
                        # bad usage, missing a -c argument
                        self.pkglint("-l %s" % uri, exit=2)
                        self.pkglint("-r %s -l %s" % (self.lint_uri, uri),
                            exit=2)
                        self.pkglint("-r %s -l %s" % (uri, self.ref_uri),
                            exit=2)
                        self.pkglint

                        if os.path.exists(cache):
                                shutil.rmtree(cache)

                        self.pkglint("-c %s -l %s" % (cache, uri), exit=1)
                        self.pkglint("-c %s -r %s -l %s" %
                            (cache, self.lint_uri, uri), exit=1)
                        self.pkglint("-c %s -r %s -l %s" %
                            (cache, uri, self.ref_uri), exit=1)

        def test_2_badcache(self):
                """Checks we can deal with bad -c options """

                opts = ["/dev/null", "/home", "/etc/passwd"]
                for cache in opts:
                        self.pkglint("-c %s -r %s -l %s" %
                            (cache, self.ref_uri, self.lint_uri), exit=1)

                # now sufficiently corrupt the cache, such that we couldn't
                # use the provided cache dir
                for name in ["lint_image", "ref_image"]:
                        cache = tempfile.mkdtemp("pkglint-cache", "",
                            self.test_root)
                        path = os.path.join(cache, name)
                        f = file(path, "w")
                        f.close()
                        self.pkglint("-c %s -r %s -l %s" %
                            (cache, self.ref_uri, self.lint_uri), exit=1)
                        shutil.rmtree(cache)

        def test_3_badrelease(self):
                """Checks we can deal with bad -b options """

                for opt in ["chickens", "0,1234", "0.16b"]:
                        self.pkglint("-c %s -l %s -b %s" %
                            (self.cache_dir, self.lint_uri, opt), exit=1)

if __name__ == "__main__":
        unittest.main()
