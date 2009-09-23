#!/usr/bin/python2.4
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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import os
import shutil
import sys
import tempfile
import testutils
import unittest

import pkg.client.api as api
import pkg.client.progress as progress
import pkg.flavor.base as base
import pkg.portable as portable
import pkg.publish.dependencies as dependencies

API_VERSION = 21
PKG_CLIENT_NAME = "pkg"

class TestApiDependencies(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = False

        depend_dp = base.Dependency.DEPEND_DEBUG_PREFIX

        hardlink1_manf_deps = """\
hardlink path=usr/foo target=../var/log/syslog
hardlink path=usr/bar target=../var/log/syslog
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/foo pkg.debug.depend.type=hardlink type=require
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog
"""

        hardlink2_manf_deps = """\
hardlink path=baz target=var/log/authlog
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""
        multi_deps = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.4/v-p/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=usr/bin/python2.4 pkg.debug.depend.reason=usr/lib/python2.4/v-p/pkg/client/indexer.py pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=usr/lib/python2.4/v-p/pkg/misc.py pkg.debug.depend.reason=usr/lib/python2.4/v-p/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""

        misc_manf = """\
set name=fmri value=pkg:/footest@0.5.11,5.11-0.117
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python2.4/v-p/pkg/misc.py
"""

        simp_manf = """\
set name=variant.foo value=bar value=baz
depend fmri=__TBD pkg.debug.depend.file=var/log/syslog pkg.debug.depend.reason=usr/bar pkg.debug.depend.type=hardlink type=require
"""

        simple_variant_deps = """\
set name=variant.foo value=bar value=baz
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        simple_v_deps_bar = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar value=baz
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=bar
"""

        simple_v_deps_bar2 = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog
"""

        simple_v_deps_baz = """
set name=fmri value=pkg:/s-v-baz
set name=variant.foo value=bar value=baz
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz
"""

        simple_v_deps_baz2 = """
set name=fmri value=pkg:/s-v-baz
set name=variant.foo value=baz
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog
"""

        two_variant_deps = """\
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        two_v_deps_bar = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=bar
"""

        two_v_deps_baz_one = """
set name=fmri value=pkg:/s-v-baz-one
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz variant.num=one
"""

        two_v_deps_baz_two = """
set name=fmri value=pkg:/s-v-baz-two
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz variant.num=two
"""
        
        misc_files = ["foo"]
        
        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                tp = self.get_test_prefix()
                self.testdata_dir = os.path.join(tp, "manifest_dir")
                os.mkdir(self.testdata_dir)
                for n in self.misc_files:
                        f = open(os.path.join(self.testdata_dir, n), "w")
                        # Write the name of the file into the file, so that
                        # all files have differing contents.
                        f.write(n + "\n")
                        f.close()

                self.inst_pkg = """\
open example2_pkg@1.0,5.11-0
add file %(foo)s mode=0555 owner=root group=bin path=/usr/bin/python2.4
close""" % { "foo": os.path.join(self.testdata_dir, "foo") }

                self.var_pkg = """\
open variant_pkg@1.0,5.11-0
add set name=variant.foo value=bar value=baz
add file %(foo)s group=sys mode=0644 owner=root path=var/log/syslog
close""" % { "foo": os.path.join(self.testdata_dir, "foo") }

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for n in self.misc_files:
                        os.remove(os.path.join(self.testdata_dir, n))
                shutil.rmtree(self.testdata_dir)

        def make_image(self):
                self.durl = self.dc.get_depot_url()
                self.image_create(self.durl)
                progresstracker = progress.NullProgressTracker()
                self.api_obj = api.ImageInterface(self.get_img_path(),
                    API_VERSION, progresstracker, lambda x: False,
                    PKG_CLIENT_NAME)

        @staticmethod
        def _do_install(api_obj, pkg_list, **kwargs):
                api_obj.plan_install(pkg_list, [], **kwargs)
                TestApiDependencies._do_finish(api_obj)

        @staticmethod
        def _do_uninstall(api_obj, pkg_list, **kwargs):
                api_obj.plan_uninstall(pkg_list, False, **kwargs)
                TestApiDependencies._do_finish(api_obj)

        @staticmethod
        def _do_image_update(api_obj, **kwargs):
                api_obj.plan_update_all(sys.argv[0], **kwargs)
                TestApiDependencies._do_finish(api_obj)

        @staticmethod
        def _do_finish(api_obj):
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

        def make_manifest(self, str):
                t_fd, t_path = tempfile.mkstemp(dir=self.testdata_dir)
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write(str)
                t_fh.close()
                return t_path
        
        def test_resolve_cross_package(self):
                """test that cross dependencies between published packages
                works."""

                self.make_image()
                m1_path = None
                m2_path = None
                try:
                        m1_path = self.make_manifest(self.hardlink1_manf_deps)
                        m2_path = self.make_manifest(self.hardlink2_manf_deps)
                        p1_name = os.path.basename(m1_path)
                        p2_name = os.path.basename(m2_path)
                        pkg_deps, errs = dependencies.resolve_deps(
                            [m1_path, m2_path], self.api_obj)
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[m1_path]), 2)
                        self.assertEqual(len(pkg_deps[m2_path]), 1)
                        self.assertEqual(len(errs), 0)
                        for d in pkg_deps[m1_path]:
                                self.assertEqual(d.attrs["fmri"], p2_name)
                        for d in pkg_deps[m2_path]:
                                self.assertEqual(d.attrs["fmri"], p1_name)
                finally:
                        if m1_path:
                                portable.remove(m1_path)
                        if m2_path:
                                portable.remove(m2_path)

        def test_resolve_mix(self):
                """Test that resolving against both packages installed on the
                image and packages works for the same package and that the
                resolver picks up the name of the package if it's defined in
                the package."""
                
                self.make_image()

                self.pkgsend_bulk(self.durl, self.inst_pkg)
                self.api_obj.refresh(immediate=True)
                self._do_install(self.api_obj, ["example2_pkg"])
                
                m1_path = None
                m2_path = None
                try:
                        m1_path = self.make_manifest(self.multi_deps)
                        m2_path = self.make_manifest(self.misc_manf)
                        p3_name = "pkg:/example2_pkg@1.0,5.11-0"
                        p2_name = "pkg:/footest@0.5.11,5.11-0.117"

                        pkg_deps, errs = dependencies.resolve_deps(
                            [m1_path, m2_path], self.api_obj)
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[m1_path]), 2)
                        self.assertEqual(len(pkg_deps[m2_path]), 0)
                        self.assertEqual(len(errs), 0)
                        for d in pkg_deps[m1_path]:
                                if d.attrs["fmri"] == p2_name:
                                        self.assertEqual(
                                            d.attrs["%s.file" % self.depend_dp],
                                            "usr/lib/python2.4/v-p/pkg/misc.py")
                                elif d.attrs["fmri"].startswith(p3_name):
                                        self.assertEqual(
                                            d.attrs["%s.file" % self.depend_dp],
                                            "usr/bin/python2.4")
                                else:
                                        raise RuntimeError("Got expected fmri "
                                            "%s for in dependency %s" %
                                            (d.attrs["fmri"], d))
                finally:
                        if m1_path:
                                portable.remove(m1_path)
                        if m2_path:
                                portable.remove(m2_path)

        def test_simple_variants_1(self):
                """Test that variants declared on the actions work correctly
                when resolving dependencies."""

                self.make_image()
                m1_path = None
                m2_path = None
                m3_path = None
                try:
                        m1_path = self.make_manifest(self.simple_variant_deps)
                        m2_path = self.make_manifest(self.simple_v_deps_bar)
                        m3_path = self.make_manifest(self.simple_v_deps_baz)
                        p2_name = "s-v-bar"
                        p3_name = "s-v-baz"
                        pkg_deps, errs = dependencies.resolve_deps(
                            [m1_path, m2_path, m3_path], self.api_obj)
                        for d in pkg_deps[m1_path]:
                                if d.attrs["fmri"] == "pkg:/s-v-bar":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["bar"]))
                                elif d.attrs["fmri"] == "pkg:/s-v-baz":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["baz"]))
                                else:
                                        raise RuntimeError("Unexpected fmri %s "
                                            "for dependency %s" %
                                            (d.attrs["fmri"], d))
                        self.assertEqual(len(pkg_deps), 3)
                        self.assertEqual(len(pkg_deps[m1_path]), 2)
                        self.assertEqual(len(pkg_deps[m2_path]), 0)
                        self.assertEqual(len(pkg_deps[m3_path]), 0)
                        self.assertEqual(len(errs), 0)
                finally:
                        if m1_path:
                                portable.remove(m1_path)
                        if m2_path:
                                portable.remove(m2_path)
                        if m3_path:
                                portable.remove(m3_path)

        def test_simple_variants_2 (self):
                """Test that variants declared on the packages work correctly
                when resolving dependencies."""

                self.make_image()
                m1_path = None
                m2_path = None
                m3_path = None
                try:
                        m1_path = self.make_manifest(self.simple_variant_deps)
                        m2_path = self.make_manifest(self.simple_v_deps_bar2)
                        m3_path = self.make_manifest(self.simple_v_deps_baz2)
                        p2_name = "s-v-bar"
                        p3_name = "s-v-baz"
                        pkg_deps, errs = dependencies.resolve_deps(
                            [m1_path, m2_path, m3_path], self.api_obj)
                        self.assertEqual(len(pkg_deps), 3)
                        self.assertEqual(len(pkg_deps[m1_path]), 2)
                        self.assertEqual(len(pkg_deps[m2_path]), 0)
                        self.assertEqual(len(pkg_deps[m3_path]), 0)
                        self.assertEqual(len(errs), 0)
                        for d in pkg_deps[m1_path]:
                                if d.attrs["fmri"] == "pkg:/s-v-bar":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["bar"]))
                                elif d.attrs["fmri"] == "pkg:/s-v-baz":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["baz"]))
                                else:
                                        raise RuntimeError("Unexpected fmri %s "
                                            "for dependency %s" %
                                            (d.attrs["fmri"], d))
                finally:
                        if m1_path:
                                portable.remove(m1_path)
                        if m2_path:
                                portable.remove(m2_path)
                        if m3_path:
                                portable.remove(m3_path)

        def test_two_variants (self):
                """Test that variants declared on the packages work correctly
                when resolving dependencies."""

                self.make_image()
                m1_path = None
                m2_path = None
                m3_path = None
                m4_path = None
                try:
                        m1_path = self.make_manifest(self.two_variant_deps)
                        m2_path = self.make_manifest(self.two_v_deps_bar)
                        m3_path = self.make_manifest(self.two_v_deps_baz_one)
                        m4_path = self.make_manifest(self.two_v_deps_baz_two)
                        p2_name = "s-v-bar"
                        p3_name = "s-v-baz-one"
                        p4_name = "s-v-baz-two"
                        pkg_deps, errs = dependencies.resolve_deps(
                            [m1_path, m2_path, m3_path, m4_path], self.api_obj)
                        self.assertEqual(len(pkg_deps), 4)
                        self.assertEqual(len(pkg_deps[m1_path]), 3)
                        self.assertEqual(len(pkg_deps[m2_path]), 0)
                        self.assertEqual(len(pkg_deps[m3_path]), 0)
                        self.assertEqual(len(pkg_deps[m4_path]), 0)
                        self.assertEqual(len(errs), 1)
                        for d in pkg_deps[m1_path]:
                                if d.attrs["fmri"] == "pkg:/s-v-bar":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["bar"]))
                                        self.assertEqual(
                                            "variant.num" in d.attrs, False)
                                elif d.attrs["fmri"] == "pkg:/s-v-baz-one":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["baz"]))
                                        self.assertEqual(
                                            d.attrs["variant.num"],
                                            set(["one"]))
                                elif d.attrs["fmri"] == "pkg:/s-v-baz-two":
                                        self.assertEqual(
                                            d.attrs["variant.foo"],
                                            set(["baz"]))
                                        self.assertEqual(
                                            d.attrs["variant.num"],
                                            set(["two"]))
                                else:
                                        raise RuntimeError("Unexpected fmri %s "
                                            "for dependency %s" %
                                            (d.attrs["fmri"], d))
                finally:
                        if m1_path:
                                portable.remove(m1_path)
                        if m2_path:
                                portable.remove(m2_path)
                        if m3_path:
                                portable.remove(m3_path)
                        if m4_path:
                                portable.remove(m4_path)

        def test_bug_11518(self):
                """Test that resolving against an installed, cached, manifest
                works with variants."""

                self.make_image()

                self.pkgsend_bulk(self.durl, self.var_pkg)
                self.api_obj.refresh(immediate=True)
                self._do_install(self.api_obj, ["variant_pkg"])

                m1_path = None
                try:
                        m1_path = self.make_manifest(self.simp_manf)
                        p2_name = "pkg:/variant_pkg@1.0,5.11-0"

                        pkg_deps, errs = dependencies.resolve_deps(
                            [m1_path], self.api_obj)
                        self.assertEqual(len(pkg_deps), 1)
                        self.assertEqual(len(pkg_deps[m1_path]), 1)
                        self.assertEqual(len(errs), 0)
                        for d in pkg_deps[m1_path]:
                                if d.attrs["fmri"].startswith(p2_name):
                                        self.assertEqual(
                                            d.attrs["%s.file" % self.depend_dp],
                                            "var/log/syslog")
                                else:
                                        raise RuntimeError("Got expected fmri "
                                            "%s for in dependency %s" %
                                            (d.attrs["fmri"], d))
                finally:
                        if m1_path:
                                portable.remove(m1_path)
