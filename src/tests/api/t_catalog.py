#!/usr/bin/python
# -*- coding: utf-8 -*-
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

# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import datetime
import errno
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest

import pkg.actions
import pkg.fmri as fmri
import pkg.catalog as catalog
import pkg.client.api_errors as api_errors
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.portable as portable
import pkg.variant as variant


class TestCatalog(pkg5unittest.Pkg5TestCase):
        """Tests for all catalog functionality."""

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)

                self.paths = [self.test_root]
                self.c = catalog.Catalog(log_updates=True)
                self.nversions = 0

                stems = {}
                for f in [
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120000Z"),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1:20000101T120010Z"),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.1:20000101T120020Z"),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-1.2:20000101T120030Z"),
                    fmri.PkgFmri("pkg:/test@1.0,5.11-2:20000101T120040Z"),
                    fmri.PkgFmri("pkg:/test@1.1,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg:/test@3.2.1,5.11-1:20000101T120050Z"),
                    fmri.PkgFmri("pkg:/test@3.2.1,5.11-1.2:20000101T120051Z"),
                    fmri.PkgFmri("pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z"),
                    fmri.PkgFmri("pkg:/apkg@1.0,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg:/zpkg@1.0,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg:/zpkg@1.0,5.11-1:20000101T120014Z")
                ]:
                        if f.pkg_name == "apkg":
                                f.set_publisher("extra")
                        elif f.pkg_name == "zpkg":
                                f.set_publisher("contrib.opensolaris.org")
                        else:
                                f.set_publisher("opensolaris.org")
                        self.c.add_package(f)
                        self.nversions += 1
                        stems[f.get_pkg_stem()] = None

                # And for good measure, ensure that one of the publishers has
                # a package with the exact same name and version as another
                # publisher's package.
                f = fmri.PkgFmri("pkg://extra/zpkg@1.0,5.11-1:20000101T120040Z")
                stems[f.get_pkg_stem()] = None
                self.c.add_package(f)
                self.nversions += 1

                self.npkgs = len(stems)

        def create_test_dir(self, name):
                """Creates a temporary directory with the specified name for
                test usage and returns its absolute path."""

                target = os.path.join(self.test_root, name)
                try:
                        os.makedirs(target, misc.PKG_DIR_MODE)
                except OSError, e:
                        if e.errno != errno.EEXIST:
                                raise e
                return os.path.abspath(target)

        def __gen_manifest(self, f):
                m = manifest.Manifest()
                lines = unicode(
                    "depend fmri=foo@1.0 type=require\n"
                    "set name=facet.devel value=true\n"
                    "set name=info.classification "
                    """value="Desktop (GNOME)/Application" """
                    """value="org.opensolaris.category.2009:GNOME (Desktop)"\n"""
                    "set name=info.classification "
                    """value="Sparc Application" variant.arch=sparc\n"""
                    "set name=info.classification "
                    """value="i386 Application" variant.arch=i386\n"""
                    "set name=variant.arch value=i386 value=sparc\n"
                    "set name=pkg.fmri value=\"%s\"\n"
                    "set name=pkg.summary value=\"Summary %s\"\n"
                    "set name=pkg.summary value=\"Sparc Summary %s\""
                    " variant.arch=sparc\n"
                    "set name=pkg.summary:th value=\"ซอฟต์แวร์ %s\"\n"
                    "set name=pkg.description value=\"Desc %s\"\n", "utf-8") % \
                    (f, f, f, f, f)

                if f.pkg_name == "zpkg":
                        lines += "set name=pkg.depend.install-hold value=test\n"
                        lines += "set name=pkg.renamed value=true\n"
                else:
                        lines += "set name=pkg.obsolete value=true\n"
                m.set_content(lines, signatures=True)

                return m

        def __test_catalog_actions(self, nc, pkg_src_list):
                def expected_dependency(f):
                        expected = [
                            "depend fmri=foo@1.0 type=require",
                            "set name=facet.devel value=true",
                            "set name=variant.arch value=i386 value=sparc",
                        ]

                        if f.pkg_name == "zpkg":
                                expected.append("set name=pkg.depend.install-hold "
                                    "value=test")
                                expected.append("set name=pkg.renamed "
                                    "value=true")
                        else:
                                expected.append("set name=pkg.obsolete "
                                    "value=true")
                        return expected

                def expected_summary(f):
                        return [
                            ('set name=info.classification '
                            'value="Desktop (GNOME)/Application" '
                            'value="org.opensolaris.category.2009:GNOME (Desktop)"'),
                            ("set name=info.classification "
                            """value="i386 Application" variant.arch=i386"""),
                            "set name=pkg.summary value=\"Summary %s\"" % f,
                            "set name=pkg.description value=\"Desc %s\"" % f,
                        ]

                def expected_all_variant_summary(f):
                        return [
                            ('set name=info.classification '
                            'value="Desktop (GNOME)/Application" '
                            'value="org.opensolaris.category.2009:GNOME (Desktop)"'),
                            ("set name=info.classification "
                            """value="Sparc Application" variant.arch=sparc"""),
                            ("set name=info.classification "
                            """value="i386 Application" variant.arch=i386"""),
                            "set name=pkg.summary value=\"Summary %s\"" % f,
                            ("set name=pkg.summary value=\"Sparc Summary %s\""
                            " variant.arch=sparc" % f),
                            "set name=pkg.description value=\"Desc %s\"" % f,
                        ]

                def expected_all_locale_summary(f):
                        # The comparison has to be sorted for this case.
                        return sorted([
                            "set name=pkg.summary value=\"Summary %s\"" % f,
                            "set name=pkg.description value=\"Desc %s\"" % f,
                            "set name=pkg.summary:th value=\"ซอฟต์แวร์ %s\"" % f,
                            ('set name=info.classification '
                            'value="Desktop (GNOME)/Application" '
                            'value="org.opensolaris.category.2009:GNOME (Desktop)"'),
                            ("set name=info.classification "
                            """value="i386 Application" variant.arch=i386"""),
                        ])

                def expected_categories(f):
                        # The comparison has to be sorted for this case.
                        return set([
                            ("", "Desktop (GNOME)/Application"),
                            ("org.opensolaris.category.2009", "GNOME (Desktop)"),
                            ("", "i386 Application"),
                        ])

                def expected_all_variant_categories(f):
                        # The comparison has to be sorted for this case.
                        return set([
                            ("", "Desktop (GNOME)/Application"),
                            ("org.opensolaris.category.2009", "GNOME (Desktop)"),
                            ("", "i386 Application"),
                            ("", "Sparc Application"),
                        ])

                # Next, ensure its populated.
                def ordered(a, b):
                        rval = cmp(a.pkg_name, b.pkg_name)
                        if rval != 0:
                                return rval
                        rval = cmp(a.publisher, b.publisher)
                        if rval != 0:
                                return rval
                        return cmp(a.version, b.version) * -1
                self.assertEqual([f for f in nc.fmris(ordered=True)],
                    sorted(pkg_src_list, cmp=ordered))

                # This case should raise an AssertionError.
                try:
                        for f, actions in nc.actions([]):
                                break
                except AssertionError:
                        pass
                else:
                        raise RuntimeError("actions() did not raise expected "
                            "exception")

                variants = variant.Variants()
                variants["variant.arch"] = "i386"
                excludes = [variants.allow_action]
                locales = set(("C", "th"))

                # This case should only return the dependency-related actions.
                def validate_dep(f, actions):
                        returned = []
                        for a in actions:
                                self.assertTrue(isinstance(a,
                                    pkg.actions.generic.Action))
                                returned.append(str(a))

                        var = nc.get_entry_variants(f, "variant.arch")
                        vars = nc.get_entry_all_variants(f)
                        if f.pkg_name == "apkg":
                                # No actions should be returned for this case,
                                # as the callback will return an empty manifest.
                                self.assertEqual(returned, [])
                                self.assertEqual(var, None)
                                self.assertEqual([v for v in vars], [])
                                return

                        expected = expected_dependency(f)
                        self.assertEqual(returned, expected)
                        self.assertEqual(var, ["i386", "sparc"])
                        self.assertEqual([(n, vs) for n, vs in vars],
                            [("variant.arch", ["i386", "sparc"])])

                for f, actions in nc.actions([nc.DEPENDENCY]):
                        validate_dep(f, actions)

                latest = [f for f in nc.fmris(last=True)]
                for f, actions in nc.actions([nc.DEPENDENCY], last=True):
                        self.assert_(f in latest)
                        validate_dep(f, actions)

                latest = [
                    (pub, stem, ver)
                    for pub, stem, ver in nc.tuples(last=True)
                ]
                for (pub, stem, ver), entry, actions in nc.entry_actions(
                    [nc.DEPENDENCY], last=True):
                        self.assert_((pub, stem, ver) in latest)
                        f = fmri.PkgFmri("%s@%s" % (stem, ver), publisher=pub)
                        validate_dep(f, actions)

                # This case should only return the summary-related actions (but
                # for all variants).
                for f, actions in nc.actions([nc.SUMMARY]):
                        returned = []
                        for a in actions:
                                self.assertTrue(isinstance(a,
                                    pkg.actions.generic.Action))
                                returned.append(str(a))

                        if f.pkg_name == "apkg":
                                # No actions should be returned for this case,
                                # as the callback will return an empty manifest.
                                self.assertEqual(returned, [])
                                continue

                        expected = expected_all_variant_summary(f)
                        self.assertEqual(returned, expected)

                # This case should only return the summary-related actions (but
                # for 'C' and 'th' locales and without sparc variants).
                for f, actions in nc.actions([nc.SUMMARY], excludes=excludes,
                    locales=locales):
                        returned = []
                        for a in actions:
                                self.assertTrue(isinstance(a,
                                    pkg.actions.generic.Action))
                                returned.append(str(a))

                        if f.pkg_name == "apkg":
                                # No actions should be returned for this case,
                                # as the callback will return an empty manifest.
                                self.assertEqual(returned, [])
                                continue

                        returned.sort()
                        expected = expected_all_locale_summary(f)
                        self.assertEqual(returned, expected)

                # This case should only return the summary-related actions (but
                # without sparc variants).
                for f, actions in nc.actions([nc.SUMMARY], excludes=excludes):
                        returned = []
                        for a in actions:
                                self.assertTrue(isinstance(a,
                                    pkg.actions.generic.Action))
                                returned.append(str(a))

                        if f.pkg_name == "apkg":
                                # No actions should be returned for this case,
                                # as the callback will return an empty manifest.
                                self.assertEqual(returned, [])
                                continue

                        expected = expected_summary(f)
                        self.assertEqual(returned, expected)

                # Verify that retrieving a single entry's actions works as well.
                f = pkg_src_list[0]
                try:
                        for a in nc.get_entry_actions(f, []):
                                break
                except AssertionError:
                        pass
                else:
                        raise RuntimeError("get_entry_actions() did not raise "
                            "expected exception")

                # This case should only return the dependency-related actions.
                returned = [
                    str(a)
                    for a in nc.get_entry_actions(f, [nc.DEPENDENCY])
                ]
                expected = expected_dependency(f)
                self.assertEqual(returned, expected)

                # This case should only return the summary-related actions (but
                # for all variants).
                returned = [
                    str(a)
                    for a in nc.get_entry_actions(f, [nc.SUMMARY])
                ]
                expected = expected_all_variant_summary(f)
                self.assertEqual(returned, expected)

                # This case should only return the summary-related actions (but
                # for 'C' and 'th' locales and without sparc variants).
                returned = sorted([
                    str(a)
                    for a in nc.get_entry_actions(f, [nc.SUMMARY],
                    excludes=excludes, locales=locales)
                ])
                expected = expected_all_locale_summary(f)
                self.assertEqual(returned, expected)

                # This case should only return the summary-related actions (but
                # without sparc variants).
                returned = [
                    str(a)
                    for a in nc.get_entry_actions(f, [nc.SUMMARY],
                    excludes=excludes)
                ]
                expected = expected_summary(f)
                self.assertEqual(returned, expected)

                # This case should return the categories used (but without sparc
                # variants).
                returned = nc.categories(excludes=excludes)
                expected = expected_categories(f)
                self.assertEqual(returned, expected)

        def test_01_attrs(self):
                self.assertEqual(self.npkgs, self.c.package_count)
                self.assertEqual(self.nversions, self.c.package_version_count)

        def test_02_extract_matching_fmris(self):
                """Verify that the filtering logic provided by
                extract_matching_fmris works as expected."""

                cf = fmri.PkgFmri("pkg:/test@1.0,5.10-1:20070101T120000Z")
                cl = catalog.extract_matching_fmris(self.c.fmris(),
                    patterns=[cf])[0]
                self.assertEqual(len(cl), 7)

                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-1:20061231T120000Z")
                cl = catalog.extract_matching_fmris(self.c.fmris(),
                    patterns=[cf])[0]
                self.assertEqual(len(cl), 7)

                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-2")
                cl = catalog.extract_matching_fmris(self.c.fmris(),
                    patterns=[cf])[0]
                self.assertEqual(len(cl), 5)

                cf = fmri.PkgFmri("pkg:/test@1.0,5.11-3")
                cl = catalog.extract_matching_fmris(self.c.fmris(),
                    patterns=[cf])[0]
                self.assertEqual(len(cl), 4)

                # First, verify that passing a single version pattern
                # works as expected.

                # Sorts by stem, then version, then publisher.
                def extract_order(a, b):
                        res = cmp(a.pkg_name, b.pkg_name)
                        if res != 0:
                                return res
                        res = cmp(a.version, b.version) * -1
                        if res != 0:
                                return res
                        return cmp(a.publisher, b.publisher)

                # This is a dict containing the set of fmris that are expected
                # to be returned by extract_matching_fmris keyed by version
                # pattern.
                versions = {
                    "*": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                        "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@1.0,5.11-2:20000101T120040Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                    "1.0": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                        "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@1.0,5.11-2:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                    "1.1": ["pkg:/test@1.1,5.11-1:20000101T120040Z"],
                    "*.1": ["pkg:/test@1.1,5.11-1:20000101T120040Z"],
                    "3.*": ["pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z"],
                    "3.2.*": ["pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z"],
                    "3.*.*": ["pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z"],
                    "*,5.11": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                        "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@1.0,5.11-2:20000101T120040Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                    "*,*-*": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                        "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@1.0,5.11-2:20000101T120040Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                    "*,*-*.2": ["pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z"],
                    "*,*-*.*.3": ["pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z"],
                    "*,*-1": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                    "*,*-1.2": ["pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z"],
                    "*,*-1.2.*": ["pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z"],
                    "*,*-*:*": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                        "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@1.0,5.11-2:20000101T120040Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                }

                for pat in versions:
                        chash = {}
                        rlist = []
                        for f in catalog.extract_matching_fmris(self.c.fmris(),
                            counthash=chash, versions=[pat])[0]:
                                f.set_publisher(None)
                                rlist.append(f)

                        # Custom sort the returned and expected to avoid having
                        # to define test data in extract order.  The primary
                        # interest here is in what is returned, not the order.
                        rlist = sorted([
                            fmri.PkgFmri(f.get_fmri(anarchy=True))
                            for f in rlist
                        ])
                        rlist = [f.get_fmri() for f in rlist]

                        elist = sorted([
                            fmri.PkgFmri(e)
                            for e in versions[pat]
                        ])
                        elist = [f.get_fmri() for f in elist]

                        # Verify that the list of matches are the same.
                        self.assertEqual(rlist, elist)

                        # Verify that the same number of matches was returned
                        # in the counthash.
                        self.assertEqual(chash[pat], len(versions[pat]))

                # Last, verify that providing multiple versions for a single
                # call returns the expected results.

                # This is a dict containing the set of fmris that are expected
                # to be returned by extract_matching_fmris keyed by version
                # pattern.
                versions = {
                    "*,*-1": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                    "*,*-*:*": ["pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/test@1.0,5.11-1:20000101T120000Z",
                        "pkg:/test@1.0,5.11-1:20000101T120010Z",
                        "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                        "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                        "pkg:/test@1.0,5.11-2:20000101T120040Z",
                        "pkg:/test@1.1,5.11-1:20000101T120040Z",
                        "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                        "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                        "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                        "pkg:/zpkg@1.0,5.11-1:20000101T120040Z"],
                }

                elist = [
                    "pkg:/apkg@1.0,5.11-1:20000101T120040Z",
                    "pkg:/test@1.0,5.11-1:20000101T120000Z",
                    "pkg:/test@1.0,5.11-1:20000101T120010Z",
                    "pkg:/test@1.0,5.11-1.1:20000101T120020Z",
                    "pkg:/test@1.0,5.11-1.2:20000101T120030Z",
                    "pkg:/test@1.0,5.11-2:20000101T120040Z",
                    "pkg:/test@1.1,5.11-1:20000101T120040Z",
                    "pkg:/test@3.2.1,5.11-1:20000101T120050Z",
                    "pkg:/test@3.2.1,5.11-1.2:20000101T120051Z",
                    "pkg:/test@3.2.1,5.11-1.2.3:20000101T120052Z",
                    "pkg:/zpkg@1.0,5.11-1:20000101T120014Z",
                    "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                    "pkg:/zpkg@1.0,5.11-1:20000101T120040Z",
                ]

                rlist = catalog.extract_matching_fmris(self.c.fmris(),
                    counthash=chash, versions=versions.keys())[0]
                rlist = sorted([
                    fmri.PkgFmri(f.get_fmri(anarchy=True))
                    for f in rlist
                ])
                rlist = [f.get_fmri() for f in rlist]

                # Verify that the list of matches are the same.
                self.assertEqual(rlist, elist)

                for pat in versions:
                        # Verify that the same number of matches was returned
                        # in the counthash.
                        self.assertEqual(chash[pat], len(versions[pat]))

        def test_03_permissions(self):
                """Verify that new catalogs are created with a mode of 644 and
                that old catalogs will have their mode forcibly changed, unless
                read_only is specified, in which case an exception is raised.
                See bug 5603 for a documented case."""

                # Catalog files should have this mode.
                mode = stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH
                # Windows doesn't have group or other permissions, so they
                # are set to be the same as for the owner
                if portable.ostype == "windows":
                        mode |= stat.S_IWGRP|stat.S_IWOTH

                # Catalog files should not have this mode.
                bad_mode = stat.S_IRUSR|stat.S_IWUSR

                # Test new catalog case.
                cpath = self.create_test_dir("test-04")
                c = catalog.Catalog(meta_root=cpath, log_updates=True)
                c.add_package(fmri.PkgFmri(
                    "pkg://opensolaris.org/test@1.0,5.11-1:20000101T120000Z"))
                c.save()

                for fname in c.signatures:
                        fn = os.path.join(c.meta_root, fname)
                        portable.assert_mode(fn, mode)

                # Now test old catalog case.
                for fname in c.signatures:
                        os.chmod(os.path.join(c.meta_root, fname), bad_mode)
                c = catalog.Catalog(meta_root=cpath, log_updates=True)
                for fname in c.signatures:
                        fn = os.path.join(c.meta_root, fname)
                        portable.assert_mode(fn, mode)

                # Need to add an fmri to it and then re-test the permissions
                # since this causes the catalog file to be re-created.
                c.add_package(fmri.PkgFmri(
                    "pkg://opensolaris.org/test@2.0,5.11-1:20000101T120000Z"))
                c.save()

                for fname in c.signatures:
                        fn = os.path.join(c.meta_root, fname)
                        portable.assert_mode(fn, mode)

                # Finally, test read_only old catalog case.
                for fname in c.signatures:
                        os.chmod(os.path.join(c.meta_root, fname), bad_mode)

                self.assertRaises(api_errors.BadCatalogPermissions,
                        catalog.Catalog, meta_root=c.meta_root, read_only=True)

        def test_04_store_and_validate(self):
                """Test catalog storage, retrieval, and validation."""

                cpath = self.create_test_dir("test-05")
                c = catalog.Catalog(meta_root=cpath, log_updates=True)

                # Verify that a newly created catalog has no signature data.
                for file, sigs in c.signatures.iteritems():
                        self.assertEqual(len(sigs), 0)

                # Verify that a newly created catalog will validate since no
                # signature data is present.
                c.validate()

                # Verify catalog storage and retrieval works.
                c.add_package(fmri.PkgFmri("pkg://opensolaris.org/"
                    "test@2.0,5.11-1:20000101T120000Z"))
                c.save()

                # Get a copy of the signature data.
                old_sigs = c.signatures

                # Verify that a catalog will have signature data after save().
                self.assertTrue(len(old_sigs) >= 1)

                # Verify that expected entries are present.
                self.assertTrue("catalog.attrs" in old_sigs)
                self.assertTrue("catalog.base.C" in old_sigs)

                updates = 0
                for file, sigs in old_sigs.iteritems():
                        self.assertTrue(len(sigs) >= 1)

                        if file.startswith("update."):
                                updates += 1

                # Only one updatelog should exist.
                self.assertEqual(updates, 1)

                # Next, retrieve the stored catalog.
                c = catalog.Catalog(meta_root=cpath, log_updates=True)
                pkg_list = [f for f in c.fmris()]
                self.assertEqual(pkg_list, [fmri.PkgFmri(
                    "pkg://opensolaris.org/test@2.0,5.11-1:20000101T120000Z")])

                # Verify that a stored catalog will validate, and that its
                # current signatures match its previous signatures.
                c.validate()
                self.assertEqual(old_sigs, c.signatures)

                # Finally, test that a catalog created with sign=False won't
                # have any signature data after being saved.
                c = catalog.Catalog(sign=False)
                c.save()
                self.assertEqual(c.signatures, { "catalog.attrs": {} })

        def test_05_retrieval(self):
                """Verify that various catalog retrieval methods work as
                expected."""

                vers = {}
                fmris = {}
                for f in self.c.fmris():
                        vers.setdefault(f.pkg_name, [])
                        vers[f.pkg_name].append(f.version)

                        fmris.setdefault(f.pkg_name, {})
                        fmris[f.pkg_name].setdefault(str(f.version), [])
                        fmris[f.pkg_name][str(f.version)].append(f)

                # test names()
                self.assertEqual(self.c.names(), set(["apkg", "test", "zpkg"]))
                self.assertEqual(self.c.names(pubs=["extra",
                    "opensolaris.org"]), set(["apkg", "test", "zpkg"]))
                self.assertEqual(self.c.names(pubs=["extra",
                    "contrib.opensolaris.org"]), set(["apkg", "zpkg"]))
                self.assertEqual(self.c.names(pubs=["opensolaris.org"]),
                    set(["test"]))

                # test pkg_names()
                expected = [
                    ("extra", "apkg"),
                    ("opensolaris.org", "test"),
                    ("contrib.opensolaris.org", "zpkg"),
                    ("extra", "zpkg"),
                ]

                for pubs in ([], ["extra", "opensolaris.org"], ["extra"],
                    ["bobcat"]):
                        elist = [
                            e for e in expected
                            if not pubs or e[0] in pubs
                        ]
                        rlist = [e for e in self.c.pkg_names(pubs=pubs)]
                        self.assertEqual(rlist, elist)

                def fmri_order(a, b):
                        rval = cmp(a.pkg_name, b.pkg_name)
                        if rval != 0:
                                return rval
                        rval = cmp(a.publisher, b.publisher)
                        if rval != 0:
                                return rval
                        return cmp(a.version, b.version) * -1

                def tuple_order(a, b):
                        apub, astem, aver = a
                        bpub, bstem, bver = b
                        rval = cmp(astem, bstem)
                        if rval != 0:
                                return rval
                        rval = cmp(apub, bpub)
                        if rval != 0:
                                return rval
                        aver = version.Version(aver, "5.11")
                        bver = version.Version(bver, "5.11")
                        return cmp(aver, bver) * -1

                def tuple_entry_order(a, b):
                        (apub, astem, aver), entry = a
                        (bpub, bstem, bver), entry = b
                        rval = cmp(astem, bstem)
                        if rval != 0:
                                return rval
                        rval = cmp(apub, bpub)
                        if rval != 0:
                                return rval
                        aver = version.Version(aver, "5.11")
                        bver = version.Version(bver, "5.11")
                        return cmp(aver, bver) * -1

                # test fmris()
                for pubs in ([], ["extra", "opensolaris.org"], ["extra"],
                    ["bobcat"]):
                        # Check base functionality.
                        elist = [
                            f for f in self.c.fmris()
                            if not pubs or f.publisher in pubs
                        ]
                        rlist = [e for e in self.c.fmris(pubs=pubs)]
                        self.assertEqual(rlist, elist)

                        # Check last functionality.
                        elist = {}
                        for f in self.c.fmris(pubs=pubs):
                                if f.get_pkg_stem() not in elist or \
                                    f.version > elist[f.get_pkg_stem()].version:
                                        elist[f.get_pkg_stem()] = f
                        elist = sorted(elist.values())

                        rlist = sorted([f for f in self.c.fmris(last=True,
                            pubs=pubs)])
                        self.assertEqual(rlist, elist)

                        # Check ordered functionality.
                        elist.sort(cmp=fmri_order)

                        rlist = [f for f in self.c.fmris(last=True,
                            ordered=True, pubs=pubs)]
                        self.assertEqual(rlist, elist)

                # test entries(), tuple_entries()
                for pubs in ([], ["extra", "opensolaris.org"], ["extra"],
                    ["bobcat"]):
                        # Check base functionality.
                        elist = [(f, {}) for f in self.c.fmris(pubs=pubs)]
                        rlist = [e for e in self.c.entries(pubs=pubs)]
                        self.assertEqual(rlist, elist)

                        # Check last functionality.
                        elist = {}
                        for f in self.c.fmris(pubs=pubs):
                                if f.get_pkg_stem() not in elist or \
                                    f.version > elist[f.get_pkg_stem()].version:
                                        elist[f.get_pkg_stem()] = f
                        elist = [(f, {}) for f in sorted(elist.values(),
                            cmp=fmri_order)]
                        rlist = [e for e in self.c.entries(last=True,
                            ordered=True, pubs=pubs)]
                        self.assertEqual(rlist, elist)

                        # Check base functionality.
                        elist = []
                        for f in self.c.fmris(pubs=pubs):
                                pub, stem, ver = f.tuple()
                                ver = str(ver)
                                elist.append(((pub, stem, ver), {}))
                        rlist = [e for e in self.c.tuple_entries(pubs=pubs)]
                        self.assertEqual(rlist, elist)

                        # Check last functionality.
                        elist = {}
                        for f in self.c.fmris(pubs=pubs):
                                if f.get_pkg_stem() not in elist or \
                                    f.version > elist[f.get_pkg_stem()].version:
                                        elist[f.get_pkg_stem()] = f

                        nlist = []
                        for f in sorted(elist.values()):
                                pub, stem, ver = f.tuple()
                                ver = str(ver)
                                nlist.append(((pub, stem, ver), {}))
                        elist = sorted(nlist, cmp=tuple_entry_order)
                        nlist = None
                        rlist = [e for e in self.c.tuple_entries(last=True,
                            ordered=True, pubs=pubs)]
                        self.assertEqual(rlist, elist)

                # test entries_by_version() and fmris_by_version()
                for pubs in ([], ["extra", "opensolaris.org"], ["extra"]):
                        for name in fmris:
                                for ver, entries in self.c.entries_by_version(
                                    name, pubs=pubs):
                                        flist = [
                                            f[1] for f in entries
                                            if not pubs or f[0].publisher in pubs
                                        ]
                                        elist = [
                                            {} for f in entries
                                            if not pubs or f[0].publisher in pubs
                                        ]
                                        self.assertEqual(flist, elist)

                                for ver, pfmris in self.c.fmris_by_version(name,
                                    pubs=pubs):
                                        elist = [
                                            f for f in fmris[name][str(ver)]
                                            if not pubs or f.publisher in pubs
                                        ]
                                        self.assertEqual(pfmris, elist)

        def test_06_operations(self):
                """Verify that catalog operations work as expected."""

                # Three sample packages used to verify that catalog data
                # is populated as expected:
                p1_fmri = fmri.PkgFmri("pkg://opensolaris.org/"
                        "base@1.0,5.11-1:20000101T120000Z")
                p1_man = manifest.Manifest()
                p1_man.set_fmri(None, p1_fmri)
                p1_man.set_content("", signatures=True)

                p2_fmri = fmri.PkgFmri("pkg://opensolaris.org/"
                        "dependency@1.0,5.11-1:20000101T130000Z")
                p2_man = manifest.Manifest()
                p2_man.set_fmri(None, p2_fmri)
                p2_man.set_content("set name=fmri value=%s\n"
                    "depend type=require fmri=base@1.0\n" % p2_fmri.get_fmri(),
                    signatures=True)

                p3_fmri = fmri.PkgFmri("pkg://opensolaris.org/"
                        "summary@1.0,5.11-1:20000101T140000Z")
                p3_man = manifest.Manifest()
                p3_man.set_fmri(None, p2_fmri)
                p3_man.set_content("set name=fmri value=%s\n"
                    "set description=\"Example Description\"\n"
                    "set pkg.description=\"Example pkg.Description\"\n"
                    "set summary=\"Example Summary\"\n"
                    "set pkg.summary=\"Example pkg.Summary\"\n"
                    "set name=info.classification value=\"org.opensolaris."
                    "category.2008:Applications/Sound and Video\"\n" % \
                    p3_fmri.get_fmri(), signatures=True)

                # Create and prep an empty catalog.
                cpath = self.create_test_dir("test-06")
                cat = catalog.Catalog(meta_root=cpath, log_updates=True)

                # Populate the catalog and then verify the Manifest signatures
                # for each entry are correct.
                cat.add_package(p1_fmri, manifest=p1_man)
                sigs = p1_man.signatures
                cat_sigs = dict(
                    (s, v)
                    for s, v in cat.get_entry_signatures(p1_fmri)
                )
                self.assertEqual(sigs, cat_sigs)

                cat.add_package(p2_fmri, manifest=p2_man)
                sigs = p2_man.signatures
                cat_sigs = dict(
                    (s, v)
                    for s, v in cat.get_entry_signatures(p2_fmri)
                )
                self.assertEqual(sigs, cat_sigs)

                cat.add_package(p3_fmri, manifest=p3_man)
                sigs = p3_man.signatures
                cat_sigs = dict(
                    (s, v)
                    for s, v in cat.get_entry_signatures(p3_fmri)
                )
                self.assertEqual(sigs, cat_sigs)

                # Next, verify that removal of an FMRI not in the catalog will
                # raise the expected exception.  Do this by removing an FMRI
                # and then attempting to remove it again.
                cat.remove_package(p3_fmri)
                self.assertRaises(api_errors.UnknownCatalogEntry,
                        cat.remove_package, p3_fmri)

                # Verify that update_entry will update base metadata and update
                # the last_modified timestamp of the catalog and base part.
                base = cat.get_part("catalog.base.C")
                orig_cat_lm = cat.last_modified
                orig_base_lm = base.last_modified

                # Update logging has to be disabled for this to work.
                cat.log_updates = False

                cat.update_entry(p2_fmri, { "foo": True })

                entry = cat.get_entry(p2_fmri)
                self.assertEqual(entry["metadata"], { "foo": True })

                self.assert_(cat.last_modified > orig_cat_lm)
                self.assert_(base.last_modified > orig_base_lm)

                part_lm = cat.parts[base.name]["last-modified"]
                self.assert_(base.last_modified == part_lm)

        def test_07_updates(self):
                """Verify that catalog updates are applied as expected."""

                # First, start by creating and populating the original catalog.
                cpath = self.create_test_dir("test-07-orig")
                orig = catalog.Catalog(meta_root=cpath, log_updates=True)
                orig.save()

                # Next, duplicate the original for testing, and load it.
                dup1_path = os.path.join(self.test_root, "test-07-dup1")
                shutil.copytree(cpath, dup1_path)
                dup1 = catalog.Catalog(meta_root=dup1_path)
                dup1.validate()

                # No catalog updates should be needed.
                self.assertEqual(dup1.get_updates_needed(orig.meta_root), None)

                # Add some packages to the original.
                pkg_src_list = [
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1:20000101T120000Z"),
                ]

                for f in pkg_src_list:
                        orig.add_package(f)
                orig.save()

                # Check the expected number of package versions in each catalog.
                self.assertEqual(orig.package_version_count, 1)
                self.assertEqual(dup1.package_version_count, 0)

                # Only the new catalog parts should be listed as updates.
                updates = dup1.get_updates_needed(orig.meta_root)
                self.assertEqual(updates, set(["catalog.base.C"]))

                # Now copy the existing catalog so that a baseline exists for
                # incremental update testing.
                shutil.rmtree(dup1_path)
                shutil.copytree(cpath, dup1_path)

                def apply_updates(src, dest):
                        # Next, determine the updates that could be made to the
                        # duplicate based on the original.
                        updates = dest.get_updates_needed(src.meta_root)

                        # Verify that the updates available to the original
                        # catalog are the same as the updated needed to update
                        # the duplicate.
                        self.assertEqual(src.updates.keys(), updates)

                        # Apply original catalog's updates to the duplicate.
                        dest.apply_updates(src.meta_root)

                        # Verify the contents.
                        self.assertEqual(dest.package_version_count,
                            src.package_version_count)
                        self.assertEqual([f for f in dest.fmris()],
                            [f for f in src.fmris()])

                # Add some packages to the original.
                pkg_src_list = [
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1:20000101T120010Z"),
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1.1:20000101T120020Z"),
                ]

                for f in pkg_src_list:
                        orig.add_package(f)
                orig.save()

                # Load the duplicate and ensure it contains the expected data.
                dup1 = catalog.Catalog(meta_root=dup1_path)
                self.assertEqual(dup1.package_version_count, 1)
                dup1.validate()

                # Apply the updates and verify.
                apply_updates(orig, dup1)

                # Now remove the packages that were added during the last
                # update.
                for f in pkg_src_list:
                        orig.remove_package(f)
                orig.save()

                # Apply the updates and verify.
                self.assertEqual(orig.package_version_count, 1)
                apply_updates(orig, dup1)

                # Now add back one of the packages removed.
                for f in pkg_src_list:
                        orig.add_package(f)
                        break
                orig.save()

                # Apply the updates and verify.
                self.assertEqual(orig.package_version_count, 2)
                apply_updates(orig, dup1)

                # Now remove the package we just added and add back both
                # packages we first removed and attempt to update.
                for f in pkg_src_list:
                        orig.remove_package(f)
                        break
                for f in pkg_src_list:
                        orig.add_package(f)
                orig.save()

                # Apply the updates and verify.
                self.assertEqual(orig.package_version_count, 3)
                apply_updates(orig, dup1)

        def test_08_append(self):
                """Verify that append functionality works as expected."""

                # First, populate a new catalog with the entries from the test
                # base one using synthesized manifest data.
                c = catalog.Catalog()
                for f in self.c.fmris():
                        c.add_package(f, manifest=self.__gen_manifest(f))

                # Next, test that basic append functionality works.
                nc = catalog.Catalog()
                nc.append(c)
                nc.finalize(pfmris=set([f for f in c.fmris()]))

                self.assertEqual([f for f in c.fmris()],
                    [f for f in nc.fmris()])
                self.assertEqual(c.package_version_count,
                    nc.package_version_count)

                for f, entry in nc.entries(info_needed=[nc.DEPENDENCY,
                    nc.SUMMARY], locales=set(("C", "th"))):
                        self.assertTrue("metadata" not in entry)

                        m = self.__gen_manifest(f)
                        expected = sorted(
                            s.strip() for s in m.as_lines()
                            if not s.startswith("set name=pkg.fmri")
                        )
                        returned = sorted(entry["actions"])
                        self.assertEqual(expected, returned)

                # Next, test that callbacks work as expected.
                pkg_list = []
                for f in c.fmris():
                        if f.pkg_name == "apkg":
                                continue
                        pkg_list.append(f)

                def append_cb(cat, f, entry):
                        if f.pkg_name == "apkg":
                                return False, None
                        return True, { "states": [] }

                nc = catalog.Catalog()
                nc.append(c, cb=append_cb)
                nc.finalize()

                for f, entry in nc.entries():
                        self.assertNotEqual(f.pkg_name, "apkg")
                        self.assertTrue("states" in entry["metadata"])

                # Next, check that an append for a single FMRI works with a
                # callback.
                def cb_true(x, y, z):
                        return True, None

                def cb_false(x, y, z):
                        return False, None

                for f in c.fmris():
                        if f.pkg_name == "apkg":
                                nc.append(c, cb=cb_false, pfmri=f)
                                break
                nc.finalize()

                for f, entry in nc.entries():
                        self.assertNotEqual(f.pkg_name, "apkg")
                        self.assertTrue("states" in entry["metadata"])

                for f in c.fmris():
                        if f.pkg_name == "apkg":
                                nc.append(c, cb=cb_true, pfmri=f)
                                break
                nc.finalize()

                self.assertEqual([f for f in c.fmris()],
                    [f for f in nc.fmris()])
                self.assertEqual(c.package_version_count,
                    nc.package_version_count)

        def test_09_actions(self):
                """Verify that the actions-related catalog functions work as
                expected."""

                pkg_src_list = [
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1:20000101T120010Z"),
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1.1:20000101T120020Z"),
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "apkg@1.0,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg://extra/"
                        "apkg@1.0,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg://extra/zpkg@1.0,5.11-1:20000101T120040Z")
                ]

                def manifest_cb(cat, f):
                        if f.pkg_name == "apkg":
                                m = manifest.Manifest()
                                m.set_content("", signatures=True)
                                return m
                        return self.__gen_manifest(f)

                def ret_man(f):
                        return manifest_cb(None, f)

                # First, create a catalog (with callback) and populate it
                # using only FMRIs.
                nc = catalog.Catalog(manifest_cb=manifest_cb)
                for f in pkg_src_list:
                        nc.add_package(f)
                self.__test_catalog_actions(nc, pkg_src_list)

                # Second, create a catalog (without callback) and populate it
                # using FMRIs and Manifests.
                nc = catalog.Catalog()
                for f in pkg_src_list:
                        nc.add_package(f, manifest=ret_man(f))
                self.__test_catalog_actions(nc, pkg_src_list)

                # Third, create a catalog (with callback), but populate it
                # using FMRIs and Manifests.
                nc = catalog.Catalog(manifest_cb=manifest_cb)
                for f in pkg_src_list:
                        nc.add_package(f, manifest=ret_man(f))
                self.__test_catalog_actions(nc, pkg_src_list)

                # Fourth, create a catalog (no callback) and populate it
                # using only FMRIs.
                nc = catalog.Catalog()
                for f in pkg_src_list:
                        nc.add_package(f)

                # These cases should not return any actions.
                for f, actions in nc.actions([nc.DEPENDENCY]):
                        returned = [a for a in actions]
                        self.assertEqual(returned, [])

                returned = nc.get_entry_actions(f, [nc.DEPENDENCY])
                self.assertEqual(list(returned), [])

        def test_10_destroy(self):

                pkg_src_list = [
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1:20000101T120010Z"),
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "test@1.0,5.11-1.1:20000101T120020Z"),
                    fmri.PkgFmri("pkg://opensolaris.org/"
                        "apkg@1.0,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg://extra/"
                        "apkg@1.0,5.11-1:20000101T120040Z"),
                    fmri.PkgFmri("pkg://extra/zpkg@1.0,5.11-1:20000101T120040Z")
                ]

                def manifest_cb(cat, f):
                        if f.pkg_name == "apkg":
                                m = manifest.Manifest()
                                m.set_content("", signatures=True)
                                return m
                        return self.__gen_manifest(f)

                def ret_man(f):
                        return manifest_cb(None, f)

                # First, create a catalog (with callback) and populate it
                # using only FMRIs.
                cpath = self.create_test_dir("test-10")
                nc = catalog.Catalog(meta_root=cpath)
                for f in pkg_src_list:
                        nc.add_package(f, manifest=ret_man(f))

                # Now verify that destroy really destroys the catalog.
                nc.destroy()

                # Verify that destroy actually emptied the catalog.
                self.assertEqual(nc.package_count, 0)
                self.assertEqual(list(nc.fmris()), [])
                self.assertEqual(nc.parts, {})
                self.assertEqual(nc.updates, {})
                self.assertEqual(nc.signatures, { "catalog.attrs": {} })

                # Next, re-create the catalog and then delete a few arbitrary
                # parts (specifically, the attrs file).
                cpath = self.create_test_dir("test-10")
                nc = catalog.Catalog(manifest_cb=manifest_cb, meta_root=cpath)
                for f in pkg_src_list:
                        nc.add_package(f, manifest=ret_man(f))
                nc.save()

                # Now remove arbitrary files.
                for fname in ("catalog.attrs", "catalog.dependency.C",
                    "catalog.summary.C"):
                        pname = os.path.join(nc.meta_root, fname)
                        portable.remove(pname)

                # Verify that destroy actually removes the files.
                nc = catalog.Catalog(meta_root=cpath)
                nc.destroy()

                for fname in os.listdir(nc.meta_root):
                        self.assertFalse(fname.startswith("catalog.") or \
                            fname.startswith("update."))


class TestEmptyCatalog(pkg5unittest.Pkg5TestCase):
        """Basic functionality tests for empty catalogs."""

        def setUp(self):
                self.c = catalog.Catalog()

        def test_01_attrs(self):
                self.assertEqual(self.c.package_count, 0)
                self.assertEqual(self.c.package_version_count, 0)

        def test_02_extract_matching_fmris(self):
                cf = fmri.PkgFmri("pkg:/test@1.0,5.10-1:20070101T120000Z")
                cl = catalog.extract_matching_fmris(self.c.fmris(),
                    patterns=[cf])[0]
                self.assertEqual(len(cl), 0)

        def test_03_actions(self):
                returned = [
                    (f, actions)
                    for f, actions in self.c.actions([self.c.DEPENDENCY])
                ]
                self.assertEqual(returned, [])


if __name__ == "__main__":
        unittest.main()
