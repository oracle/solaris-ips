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

# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import os.path
import shutil
import sys
import unittest
import tempfile
import threading
import subprocess

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
set name=pkg.fmri value=pkg://opensolaris.org/system/lintedaction@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=org.opensolaris.consolidation value=ON pkg.linted=True
set name=variant.arch value=i386 value=sparc
"""

        # has two set actions, one of which is linted
        linted_manifest = """
set name=pkg.fmri value=pkg://opensolaris.org/system/lintedmf@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.linted value=True
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
"""

        # a basic manifest with a given fmri, used to test ordering
        # - when linting 'manifest' and 'manifest_ordered' together,
        # we should always visit this one first, regardless of the
        # order used on the command line.
        manifest_ordered = """
set name=pkg.fmri value=pkg://opensolaris.org/system/jkernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
set name=test value=i386 variant.arch=sparc
"""

        # has two set actions, one of which is linted
        linted_manifest1 = """
set name=pkg.fmri value=pkg://opensolaris.org/system/lintedmf1@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
# allow the System/Noodles info.classification value in this manifest
set name=pkg.linted.pkglint.manifest008.6 value=True
set name=info.classification value=org.opensolaris.category.2008:System/Noodles
set name=pkg.summary value="Core Solaris Kernel"
# allow a duplicate set action in this case
set name=org.opensolaris.consolidation value=ON pkg.linted=True
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
# we should still get this warning
depend fmri=foo type=require
"""

        # has a dependency which we'll be unable to resolve at runtime,
        # resulting in a pkglint.action005.1 warning, unless we run with
        # a pkglintrc file that specifies pkglint.action005.1.missing-deps
        # parameter
        missing_dep_manifest = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
depend type=require fmri=does/not/exist
"""

        missing_dep_manifest_action = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
# pass the parameter to the action directly
depend type=require fmri=does/not/exist pkg.lint.pkglint.action005.1.missing-deps=pkg:/does/not/exist
"""

        missing_dep_manifest_mf = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@0.5.11,5.11-0.141:20100603T215050Z
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
# pass the parameter as a set action in the manifest
set name=pkg.lint.pkglint.action005.1.missing-deps value="pkg:/does/not/exist pkg:/foo"
depend type=require fmri=does/not/exist
"""

        broken_fmri_mf = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@@@
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
"""

        no_build_release_mf = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel@1
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
"""

        no_version_mf = """
set name=pkg.fmri value=pkg://opensolaris.org/system/kernel
set name=pkg.description value="core kernel software for a specific instruction-set architecture"
set name=info.classification value=org.opensolaris.category.2008:System/Core
set name=pkg.summary value="Core Solaris Kernel"
set name=org.opensolaris.consolidation value=ON
set name=variant.arch value=i386 value=sparc
"""
        # for the rcfiles below, we also need to point the
        # info_classification_path field to the sections file we deliver in the
        # proto area
        module_exclusion_rc = """
[pkglint]
pkglint.exclude: pkg.lint.pkglint_manifest.PkgManifestChecker
info_classification_path: {0}/usr/share/lib/pkg/opensolaris.org.sections
"""

        method_exclusion_rc = """
[pkglint]
pkglint.exclude: pkg.lint.pkglint_manifest.PkgManifestChecker.duplicate_sets
info_classification_path: {0}/usr/share/lib/pkg/opensolaris.org.sections
"""

        low_noise_rc = """
[pkglint]
log_level = CRITICAL
info_classification_path: {0}/usr/share/lib/pkg/opensolaris.org.sections
"""

        missing_dep_rc = """
[pkglint]
info_classification_path: {0}/usr/share/lib/pkg/opensolaris.org.sections
pkglint.action005.1.missing-deps = pkg:/does/not/exist
"""

        missing_dep_rc_versioned = """
[pkglint]
info_classification_path: {0}/usr/share/lib/pkg/opensolaris.org.sections
pkglint.action005.1.missing-deps = pkg:/does/not/exist@2.0
"""
        # in each of the cases below, we disable the check that reports on
        # the presence of pkg.linted attributes.  However it's the report-linted
        # parameter that differs.
        no_linted_messages_rc = """
[pkglint]
pkglint001.5.report-linted = False
pkglint.exclude = pkg.lint.pkglint_action.PkgActionChecker.linted \
    pkg.lint.pkglint_manifest.PkgManifestChecker.linted
"""

        linted_messages_rc = """
[pkglint]
pkglint001.5.report-linted = True
pkglint.exclude = pkg.lint.pkglint_action.PkgActionChecker.linted \
    pkg.lint.pkglint_manifest.PkgManifestChecker.linted
"""

        def setUp(self):                
                pkg5unittest.CliTestCase.setUp(self)

        def test_1_usage(self):
                """Tests that we show a usage message."""
                ret, output, err = self.pkglint("--help")
                self.assertTrue("Usage:" in output,
                    "No usage string printed")

        def test_2_badopts(self):
                """Tests that we exit with an error on wrong or missing args"""

                for opt in ["-x", "--asdf", "-c test_bad_opts -l zappo://cats"]:
                        ret, output, err = self.pkglint(opt, exit=2)

        def test_3_list(self):
                """Tests that -L prints headers and descriptions or methods."""
                for flag in ["-L", "-vL"]:
                        ret, output, err = self.pkglint(flag)
                        self.assertTrue("pkglint.dupaction001" in output,
                            "short name didn't appear in {0} output".format(flag))

                        self.assertTrue("NAME" in output,
                            "Header not printed in {0} output".format(flag))
                        if flag == "-vL":
                                self.assertTrue(
                                    "pkg.lint.pkglint_action.PkgDupActionChecker.duplicate_paths"
                                    in output,
                                    "verbose list output didn't show method")
                        elif flag == "-L":
                                self.assertTrue(
                                    "Paths should be unique." in output,
                                    "description didn't appear in "
                                    "-L output: {0}".format(output))
                                self.assertTrue("pkg.lint." not in output,
                                    "description contained pkg.lint, possible "
                                    "missing <checker>.pkglint_desc attribute.")

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
                self.pkglint("{0} {1}".format(mpath, mpath1), exit=1)

        def test_6_rcfile(self):
                """Checks that check exclusion works, by testing a broken
                manifest, excluding checks designed to catch the fault.
                This tests part of the engine, as well as the -f handling
                in the CLI.
                """
                mpath1 = self.make_manifest(self.broken_manifest)
                self.make_misc_files({"rcfile": self.module_exclusion_rc.format(
                    pkg5unittest.g_pkg_path)})
                self.make_misc_files({"rcfile1": self.method_exclusion_rc.format(
                    pkg5unittest.g_pkg_path)})

                # verify we fail first
                self.pkglint("{0}".format(mpath1), exit=1)

                # now we should succeed
                self.pkglint("-f {0}/rcfile {1}".format(self.test_root,  mpath1),
                    testrc=False, exit=0)
                self.pkglint("-f {0}/rcfile1 {1}".format(self.test_root, mpath1),
                    exit=0)

                ret, output, err = self.pkglint("-f {0}/rcfile -vL".format(
                    self.test_root, testrc=False, exit=0))
                self.assertTrue(
                    "pkg.lint.pkglint_manifest.PkgManifestChecker.duplicate_sets"
                    in output, "List output missing excluded checker")
                self.assertTrue("Excluded checks:" in output)

                ret, output, err = self.pkglint("-f {0}/rcfile1 -vL".format(
                    self.test_root, testrc=False, exit=0))
                self.assertTrue(
                    "pkg.lint.pkglint_manifest.PkgManifestChecker.duplicate_sets"
                    in output, "List output missing excluded checker")
                self.assertTrue("Excluded checks:" in output)

        def test_7_linted(self):
                """Checks that the pkg.linted keyword works for actions and
                manifests.  While this tests the linted functionality of the
                engine, it's also a CLI test to ensure we report a zero
                exit code from a lint check that has emitted output, but
                doesn't indicate an error."""
                mpath1 = self.make_manifest(self.broken_manifest)
                linted_action_path = self.make_manifest(self.linted_action)
                linted_manifest_path = self.make_manifest(self.linted_manifest)
                linted_manifest_path1 = self.make_manifest(self.linted_manifest1)

                # verify we fail first
                self.pkglint("{0}".format(mpath1), exit=1)

                # now we should succeed
                self.pkglint(linted_action_path, exit=0)
                self.pkglint(linted_manifest_path, exit=0)

                # we should succeed, but get a warning from one check
                ret, output, err = self.pkglint(linted_manifest_path1, exit=0)
                self.assertTrue("pkglint.action005.1" in err,
                    "Expected to get a pkglint.action005.1 warning from "
                    "linted_manifest_path_1:\n{0}".format(err))

        def test_8_verbose(self):
                """Checks that the -v flag works, overriding the log level
                in pkglintrc."""
                mpath = self.make_manifest(self.broken_manifest)

                # default log setting
                ret, output, err = self.pkglint("{0}".format(mpath), exit=1)
                self.assertTrue("Total number of checks found" not in output,
                    "verbose output detected in non-verbose mode")

                self.assertTrue("duplicate set actions" in err)

                ret, output_verbose, err = self.pkglint("-v {0}".format(mpath), exit=1)
                self.assertTrue("Total number of checks found" in output_verbose,
                    "verbose output not printed in verbose mode")
                self.assertTrue("duplicate set actions" in err)

                # override log setting in config file
                self.make_misc_files(
                    {"low_noise_rc": self.low_noise_rc.format(
                    pkg5unittest.g_pkg_path)})
                ret, output, err = self.pkglint("-f {0}/low_noise_rc {1}".format(
                    self.test_root, mpath), exit=0)
                self.assertTrue("Total number of checks found" not in output,
                    "verbose output detected in non-verbose mode")
                self.assertTrue("duplicate set actions" not in err)

                ret, output, err = self.pkglint("-v -f {0}/low_noise_rc {1}".format(
                    self.test_root, mpath), exit=1)
                self.assertTrue("Total number of checks found" in output,
                    "verbose output detected in non-verbose mode")
                self.assertTrue("duplicate set actions" in err)

        def test_9_order(self):
                """Checks that we always visit manifests in the same order."""
                mpath = self.make_manifest(self.manifest)
                mpath1 = self.make_manifest(self.manifest_ordered)
                ret, out, err = self.pkglint("-v {0} {1}".format(mpath, mpath1))
                ret, out2, err2 = self.pkglint("-v {0} {1}".format(mpath1, mpath))

                self.assertTrue(out == out2,
                    "different stdout with different cli order")
                self.assertTrue(err == err2,
                    "different stderr with different cli order")

        def test_10_rcfile_params(self):
                """Loading pkglint parameters from an rcfile works"""

                mpath = self.make_manifest(self.missing_dep_manifest)
                self.make_misc_files({"rcfile": self.missing_dep_rc.format(
                    pkg5unittest.g_pkg_path),
                    "versioned": self.missing_dep_rc_versioned.format(
                    pkg5unittest.g_pkg_path)})

                # verify we fail first
                ret, output, err = self.pkglint("{0}".format(mpath))
                self.assertTrue("pkglint.action005.1" in err,
                    "Expected missing dependency warning not printed")

                # verify that with the given rc file, we don't report an error
                # since our pkglintrc now passes a parameter to
                # pkglint.action005.1 whitelisting that particular dependency
                ret, output, err = self.pkglint("-f {0}/rcfile {1}".format(
                    self.test_root, mpath), testrc=False)
                self.assertTrue("pkglint.action005.1" not in err,
                    "Missing dependency warning printed, despite paramter")

                # this time, we've whitelisted a versioned dependency, but
                # we don't depend on any given version - we should still
                # complain
                ret, output, err = self.pkglint("-f {0}/versioned {1}".format(
                    self.test_root, mpath), testrc=False)
                self.assertTrue("pkglint.action005.1" in err,
                    "Missing dep warning not printed, despite versioned rcfile")

                # finally, verify the parameter set in either the action or
                # manifest works
                for mf in [self.missing_dep_manifest_action,
                    self.missing_dep_manifest_mf]:
                        mpath = self.make_manifest(mf)
                        ret, output, err = self.pkglint(mpath)
                        self.assertTrue("pkglint.action005.1" not in err,
                            "Missing dependency warning printed, despite "
                            "paramter set in {0}".format(mf))

        def test_11_broken_missing_rcfile(self):
                """Tests that we fail gracefully with a broken or missing
                config file argument """
                mpath = self.make_manifest(self.missing_dep_manifest)
                self.pkglint("-f /dev/null {0}".format(mpath), testrc=False, exit=2)
                self.pkglint("-f /no/such/pkg5/file {0}".format(mpath), testrc=False,
                    exit=2)
                self.pkglint("-f /etc/shadow {0}".format(mpath), testrc=False, exit=2)

        def test_12_pkg_versions(self):
                """Tests that the CLI deals with pkg.fmri values properly."""

                mpath = self.make_manifest(self.broken_fmri_mf)
                self.pkglint(mpath, exit=1)
                mpath = self.make_manifest(self.no_version_mf)
                self.pkglint(mpath, exit=1)
                # pkglint will add a default build_release if one is missing,
                # in line with pkgsend.
                mpath = self.make_manifest(self.no_build_release_mf)
                self.pkglint(mpath)

        def test_13_linted_ignore(self):
                """Tests that our rcfile parameter to avoid printing linted
                messages works properly"""

                mpath1 = self.make_manifest(self.linted_manifest1)
                self.make_misc_files({"rcfile": self.no_linted_messages_rc})
                self.make_misc_files({"rcfile1": self.linted_messages_rc})

                ret, output, err = self.pkglint("-f {0}/rcfile1 {1}".format(
                    self.test_root,  mpath1), exit=0)
                self.assertTrue("INFO " in err, "error output: {0}".format(err))
                self.assertTrue("Linted message: pkglint.manifest008.6" in err,
                    "error output: {0}".format(err))

                # now we should still fail, but should not emit the linted INFO
                ret, output, err = self.pkglint("-f {0}/rcfile {1}".format(
                    self.test_root,  mpath1), testrc=False, exit=0)
                self.assertTrue("INFO " not in err, "error output: {0}".format(err))
                self.assertTrue("Linted message: pkglint.manifest008.6" not in
                    err, "error output: {0}".format(err))


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
                    "opensolaris.org", "test", "nopubconfig", "test"],
                    start_depots=True)

                self.ref_uri = self.dcs[1].get_depot_url()
                self.lint_uri = self.dcs[2].get_depot_url()
                self.lint_repo_path = self.dcs[2].get_repo_url()
                self.cache_dir = os.path.join(self.test_root, "pkglint-cache")

                paths = self.make_misc_files(self.ref_mf)

                for item in paths:
                        self.pkgsend(depot_url=self.ref_uri,
                            command="publish {0}".format(item))
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
                        self.pkglint("-l {0}".format(uri), exit=2)
                        self.pkglint("-r {0} -l {1}".format(self.lint_uri, uri),
                            exit=2)
                        self.pkglint("-r {0} -l {1}".format(uri, self.ref_uri),
                            exit=2)

                        if os.path.exists(cache):
                                shutil.rmtree(cache)
                        self.pkglint("-c {0} -l {1}".format(cache, uri), exit=2)
                        self.pkglint("-c {0} -r {1} -l {2}".format(
                            cache, self.lint_uri, uri), exit=2)
                        self.pkglint("-c {0} -r {1} -l {2}".format(
                            cache, uri, self.ref_uri), exit=2)

                        # If one of the specified repositories is bad, pkglint
                        # should fail.
                        self.pkglint("-c {0} -r {1} -r {2} -l {3}".format(
                            cache, self.ref_uri, uri, self.lint_uri), exit=2)
                        shutil.rmtree(cache)
                        self.pkglint("-c {0} -l {1} -l {2}".format(
                            cache, self.ref_uri, uri), exit=2)

        def test_2_badcache(self):
                """Checks we can deal with bad -c options """

                opts = ["/dev/null", "/system/contract", "/etc/passwd"]
                for cache in opts:
                        self.pkglint("-c {0} -r {1} -l {2}".format(
                            cache, self.ref_uri, self.lint_uri), exit=2)

                # now sufficiently corrupt the cache, such that we couldn't
                # use the provided cache dir
                for name in ["lint_image", "ref_image"]:
                        cache = tempfile.mkdtemp("pkglint-cache", "",
                            self.test_root)
                        path = os.path.join(cache, name)
                        f = open(path, "w")
                        f.close()
                        self.pkglint("-c {0} -r {1} -l {2}".format(
                            cache, self.ref_uri, self.lint_uri), exit=2)
                        shutil.rmtree(cache)

        def test_3_badrelease(self):
                """Checks we can deal with bad -b options """

                for opt in ["chickens", "0,1234", "0.16b"]:
                        self.pkglint("-c {0} -l {1} -b {2}".format(
                            self.cache_dir, self.lint_uri, opt), exit=2)

        def test_4_fancy_unix_progress_tracking(self):
                """When stdout is not a tty, pkglint uses a
                CommandLineProgressTracker. This test runs pkglint with a tty
                in order to sanity-check the FancyUnixProgressTracker.
                See also t_progress.TestProgressTrackers.__t_pty_tracker(..)
                """

                mpath1 = self.make_manifest(self.ref_mf["ref-sample1.mf"])
                cache = tempfile.mkdtemp("pkglint-cache", "", self.test_root)

                for args in [[mpath1], ["-c", cache, "-l", self.lint_uri]]:
                        cmdline = [sys.executable, "{0}/usr/bin/pkglint".format(
                            pkg5unittest.g_pkg_path)]
                        cmdline.extend(args)

                        # ensure the command works first
                        self.pkglint(" ".join(args))
                        self.cmdline_run(" ".join(cmdline), exit=0, usepty=True)

                if os.path.exists(cache):
                        shutil.rmtree(cache)

        def test_5_file_paths(self):
                """Checks that we can use file paths to repository, with
                file:// schemes, absolute paths and relative paths."""

                lint_repo_no_scheme = self.lint_repo_path.replace("file://", "")
                rel_path = lint_repo_no_scheme.replace(self.test_root, "")
                lint_repo_relative  = os.path.sep.join([self.test_root, "..",
                    os.path.basename(self.test_root), rel_path])

                cmdlines = [
                    "-c {0} -l {1}".format(self.cache_dir, self.lint_repo_path),
                    "-c {0} -l {1}".format(self.cache_dir, lint_repo_no_scheme),
                    "-c {0} -l {1}".format(self.cache_dir, lint_repo_relative)
                ]

                for cmd in cmdlines:
                        self.pkglint(cmd)
                        shutil.rmtree(self.cache_dir)

        def test_6_multiple_repos(self):
                """Checks that pkglint can accept multiple ref and lint
                repositories. Actually it is to test multiple publishers can be
                set on the same ref or lint image after it was created."""

                mpath1 = self.make_manifest(self.ref_mf["ref-sample1.mf"])
                durl3 = self.dcs[3].get_depot_url()
                durl4 = self.dcs[4].get_depot_url()
                durl5 = self.dcs[5].get_depot_url()

                # First test the case of adding new publishers.
                # Verify that adding new publishers from following ref/lint
                # repositories will work. When repository configuration info was
                # not provided, pkglint will assume the repo uri is the origin...
                self.pkglint("-c {0} -r {1} -r {2} -r {3} {4}".format(
                    self.cache_dir, self.ref_uri, durl3, durl5, mpath1))
                self.pkg("-R {0}/ref_image publisher".format(self.cache_dir))
                self.assertTrue("opensolaris.org" in self.output and
                    "test" in self.output and durl3 in self.output and
                    durl5 in self.output)
                self.pkglint("-c {0} -l {1} -l {2} -l {3}".format(
                    self.cache_dir, self.ref_uri, durl3, durl5))
                self.pkg("-R {0}/lint_image publisher".format(self.cache_dir))
                self.assertTrue("opensolaris.org" in self.output and
                    "test" in self.output and durl3 in self.output and
                    durl5 in self.output)
                shutil.rmtree(self.cache_dir)

                # ... and when no origin was provided in repository
                # configuration, pkglint will assume that the provided
                # repo uri is the origin to add.
                self.pkgrepo("set -s {0} -p test repository/origins=''".format(
                    self.dcs[3].get_repodir()))
                self.dcs[3].refresh()
                self.pkglint("-c {0} -r {1} -r {2} {3}".format(
                    self.cache_dir, self.ref_uri, durl3, mpath1))
                self.pkg("-R {0}/ref_image publisher | grep {1}".format(
                    self.cache_dir, durl3))
                self.pkglint("-c {0} -l {1} -l {2}".format(
                    self.cache_dir, self.ref_uri, durl3))
                self.pkg("-R {0}/lint_image publisher | grep {1}".format(
                    self.cache_dir, durl3))
                shutil.rmtree(self.cache_dir)

                # Verify that adding new publishers from multipublisher
                # repository will work.
                self.pkgrepo("set -s {0} -p second-pub -p third-pub "
                    "publisher/alias=''".format(self.dcs[3].get_repodir()))
                self.dcs[3].refresh()
                self.pkglint("-c {0} -r {1} -r {2} {3}".format(
                    self.cache_dir, self.ref_uri, durl3, mpath1))
                self.pkg("-R {0}/ref_image publisher".format(self.cache_dir))
                self.assertTrue("opensolaris.org" in self.output and
                    "test" in self.output and "second-pub" in self.output and
                    "third-pub" in self.output)
                self.pkglint("-c {0} -l {1} -l {2}".format(
                    self.cache_dir, self.ref_uri, durl3))
                self.pkg("-R {0}/lint_image publisher".format(self.cache_dir))
                self.assertTrue("opensolaris.org" in self.output and
                    "test" in self.output and "second-pub" in self.output and
                    "third-pub" in self.output)
                shutil.rmtree(self.cache_dir)
 
                # The fourth depot is purposefully one with the publisher
                # operation disabled.
                self.dcs[4].stop()
                self.dcs[4].set_disable_ops(["publisher/0"])
                self.dcs[4].start()
 
                # Verify that a repository that doesn't support publisher
                # operation will fail.
                cmdlines = ["-c {0} -r {1} -r {2} {3}".format(
                    self.cache_dir, self.ref_uri, durl4, mpath1),
                    "-c {0} -l {1} -l {2}".format(
                    self.cache_dir, self.ref_uri, durl4)
                ]
                for cmd in cmdlines:
                        self.pkglint(cmd, exit=2)
                shutil.rmtree(self.cache_dir)
 
                # Now test the case of updating publishers.
                # Verify that updating the exising publishers by following
                # ref/lint repositories will work.
                self.pkglint("-c {0} -r {1} -r {2} {3}".format(
                    self.cache_dir, self.ref_uri, self.lint_uri, mpath1))
                self.pkg("-R {0}/ref_image publisher".format(self.cache_dir))
                self.assertTrue(self.ref_uri in self.output,
                    self.lint_uri in self.output)
                self.pkglint("-c {0} -l {1} -l {2}".format(
                    self.cache_dir, self.ref_uri, self.lint_uri))
                self.pkg("-R {0}/lint_image publisher".format(self.cache_dir))
                self.assertTrue(self.ref_uri in self.output,
                    self.lint_uri in self.output)
                shutil.rmtree(self.cache_dir)
 
                # Verify that when origins were provided in a repository, pkglint
                # will only add those unknown origins of the repository to the
                # existing and configured origins of the image.
                self.pkgrepo("set -s {0} -p test repository/origins={1} "
                    "repository/origins={2}".format(
                    self.dcs[3].get_repodir(), durl3, durl5))
                self.pkgrepo("set -s {0} -p test repository/origins={1} "
                    "repository/origins={2}".format(
                    self.dcs[5].get_repodir(), durl3, durl5))
                self.dcs[5].refresh()
                self.pkglint("-c {0} -r {1} -r {2} {3}".format(
                    self.cache_dir, durl3, durl5, mpath1))
                self.pkg("-R {0}/ref_image publisher".format(self.cache_dir))
                self.assertTrue(self.output.count(durl5) == 1)
                self.pkglint("-c {0} -l {1} -l {2}".format(
                    self.cache_dir, durl3, durl5))
                self.pkg("-R {0}/lint_image publisher".format(self.cache_dir))
                self.assertTrue(self.output.count(durl5) == 1)
                shutil.rmtree(self.cache_dir)


if __name__ == "__main__":
        unittest.main()
