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

API_VERSION = 28
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
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/v-p/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=usr/bin/python2.6 pkg.debug.depend.reason=usr/lib/python2.6/v-p/pkg/client/indexer.py pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=usr/lib/python2.6/v-p/pkg/misc.py pkg.debug.depend.reason=usr/lib/python2.6/v-p/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""

        misc_manf = """\
set name=fmri value=pkg:/footest@0.5.11,5.11-0.117
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python2.6/v-p/pkg/misc.py
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

        collision_manf = """\
set name=fmri value=pkg:/collision_manf
depend fmri=__TBD pkg.debug.depend.file=no_such_named_file pkg.debug.depend.path=platform/foo/baz pkg.debug.depend.path=platform/bar/baz pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require\
"""

        collision_manf_num_var = """\
set name=fmri value=pkg:/collision_manf
set name=variant.num value=one value=two
depend fmri=__TBD pkg.debug.depend.file=no_such_named_file pkg.debug.depend.path=platform/foo/baz pkg.debug.depend.path=platform/bar/baz pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require\
"""

        sat_both = """\
set name=fmri value=pkg:/sat_both
file NOHASH path=platform/bar/baz/no_such_named_file
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        sat_bar_libc = """\
set name=fmri value=pkg:/sat_bar_libc
file NOHASH path=platform/bar/baz/no_such_named_file
"""

        sat_bar_libc2 = """\
set name=fmri value=pkg:/sat_bar_libc2
file NOHASH path=platform/bar/baz/no_such_named_file
"""

        sat_foo_libc = """\
set name=fmri value=pkg:/sat_foo_libc
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        sat_bar_libc_num_var = """\
set name=fmri value=pkg:/sat_bar_libc
set name=variant.num value=one
file NOHASH path=platform/bar/baz/no_such_named_file
"""
        sat_foo_libc_num_var = """\
set name=fmri value=pkg:/sat_foo_libc
set name=variant.num value=two
file NOHASH path=platform/foo/baz/no_such_named_file
"""
        sat_foo_libc_num_var_both = """\
set name=fmri value=pkg:/sat_foo_libc
set name=variant.num value=one value=two
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        multi_file_dep_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=search_storage.py pkg.debug.depend.file=search_storage.pyc pkg.debug.depend.file=search_storage/__init__.py pkg.debug.depend.path=usr/lib/python2.6/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-dynload/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-old/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-tk/pkg pkg.debug.depend.path=usr/lib/python2.6/plat-sunos5/pkg pkg.debug.depend.path=usr/lib/python2.6/site-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gst-0.10/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg pkg.debug.depend.path=usr/lib/python26.zip/pkg pkg.debug.depend.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py pkg.debug.depend.type=python type=require
"""
        multi_file_sat_both = """\
set name=fmri value=pkg:/sat_both
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.pyc
"""

        multi_file_sat_py = """\
set name=fmri value=pkg:/sat_py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.py
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/lib-tk/pkg/search_storage.py
"""
        multi_file_sat_pyc = """\
set name=fmri value=pkg:/sat_pyc
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/search_storage.pyc
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
add file %(foo)s mode=0555 owner=root group=bin path=/usr/bin/python2.6
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
                api_obj.plan_install(pkg_list, **kwargs)
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
                m1_path = self.make_manifest(self.hardlink1_manf_deps)
                m2_path = self.make_manifest(self.hardlink2_manf_deps)
                p1_name = os.path.basename(m1_path)
                p2_name = os.path.basename(m2_path)
                pkg_deps, errs = dependencies.resolve_deps(
                    [m1_path, m2_path], self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % e for e in errs]))
                self.assertEqual(len(pkg_deps), 2)
                self.assertEqual(len(pkg_deps[m1_path]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 1)
                for d in pkg_deps[m1_path]:
                        self.assertEqual(d.attrs["fmri"], p2_name)
                for d in pkg_deps[m2_path]:
                        self.assertEqual(d.attrs["fmri"], p1_name)

        def test_resolve_mix(self):
                """Test that resolving against both packages installed on the
                image and packages works for the same package and that the
                resolver picks up the name of the package if it's defined in
                the package."""
                
                self.make_image()

                self.pkgsend_bulk(self.durl, self.inst_pkg)
                self.api_obj.refresh(immediate=True)
                self._do_install(self.api_obj, ["example2_pkg"])
                
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
                        if d.attrs["fmri"].startswith(p2_name):
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["usr/lib/python2.6/v-p/pkg/misc.py"])
                        elif d.attrs["fmri"].startswith(p3_name):
                                self.assertEqual(
                                    d.attrs["%s.file" % self.depend_dp],
                                    ["usr/bin/python2.6"])
                        else:
                                raise RuntimeError("Got expected fmri "
                                    "%s for in dependency %s" %
                                    (d.attrs["fmri"], d))

        def test_simple_variants_1(self):
                """Test that variants declared on the actions work correctly
                when resolving dependencies."""

                self.make_image()
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
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" % "\n".join(["%s" % (e,) for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[m1_path]), 2)
                self.assertEqual(len(pkg_deps[m2_path]), 0)
                self.assertEqual(len(pkg_deps[m3_path]), 0)

        def test_simple_variants_2 (self):
                """Test that variants declared on the packages work correctly
                when resolving dependencies."""

                self.make_image()
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

        def test_two_variants (self):
                """Test that variants declared on the packages work correctly
                when resolving dependencies."""

                self.make_image()
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

        def test_multi_file_dependencies(self):
                def __check_results(pkg_deps, errs, exp_pkg, no_deps, one_dep):
                        if errs:
                                raise RuntimeError("Got the following "
                                    "unexpected errors:\n%s" %
                                    "\n".join([str(e) for e in errs]))
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[no_deps]), 0)
                        if len(pkg_deps[one_dep]) != 1:
                                raise RuntimeError("Got more than one "
                                    "dependency:\n%s" %
                                    "\n".join(
                                        [str(d) for d in pkg_deps[col_path]]))
                        d = pkg_deps[one_dep][0]
                        self.assertEqual(d.attrs["fmri"], exp_pkg)
                
                self.make_image()

                col_path = self.make_manifest(self.multi_file_dep_manf)
                # This manifest provides two files that satisfy col_path's
                # file dependencies.
                both_path = self.make_manifest(self.multi_file_sat_both)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a py or pyc file..
                py_path = self.make_manifest(self.multi_file_sat_py)
                pyc_path = self.make_manifest(self.multi_file_sat_pyc)

                # The following tests should all succeed because either the same
                # package delivers both files which could satisfy the dependency
                # or only one package which delivers the dependency is being
                # resolved against.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, both_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_both", both_path,
                    col_path)

                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, py_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_py", py_path,
                    col_path)

                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, pyc_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_pyc", pyc_path,
                    col_path)

                # This resolution should fail because files which satisfy the
                # dependency are delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, py_path, pyc_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.MultiplePackagesPathError):
                                for d in e.res:
                                        if d.attrs["fmri"] not in \
                                            ("pkg:/sat_py",
                                            "pkg:/sat_pyc"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    ["search_storage.py", "search_storage.pyc",
                                    "search_storage/__init__.py"])
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    ["search_storage.py", "search_storage.pyc",
                                    "search_storage/__init__.py"])
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)


        def test_bug_11518(self):
                """Test that resolving against an installed, cached, manifest
                works with variants."""

                self.make_image()

                self.pkgsend_bulk(self.durl, self.var_pkg)
                self.api_obj.refresh(immediate=True)
                self._do_install(self.api_obj, ["variant_pkg"])

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
                                    ["var/log/syslog"])
                        else:
                                raise RuntimeError("Was expecting %s, got fmri "
                                    "%s for dependency %s" %
                                    (p2_name, d.attrs["fmri"], d))

        def test_bug_12697_and_12896(self):
                """Test that pkgdep resolve handles multiple run path
                dependencies correctly when the files are delivered in the same
                package and when the files are delivered in different packages.
                """

                def __check_results(pkg_deps, errs, exp_pkg, no_deps, one_dep):
                        if errs:
                                raise RuntimeError("Got the following "
                                    "unexpected errors:\n%s" %
                                    "\n".join([str(e) for e in errs]))
                        self.assertEqual(len(pkg_deps), 2)
                        self.assertEqual(len(pkg_deps[no_deps]), 0)
                        if len(pkg_deps[one_dep]) != 1:
                                raise RuntimeError("Got more than one "
                                    "dependency:\n%s" %
                                    "\n".join(
                                        [str(d) for d in pkg_deps[col_path]]))
                        d = pkg_deps[one_dep][0]
                        self.assertEqual(d.attrs["fmri"], exp_pkg)
                
                self.make_image()

                col_path = self.make_manifest(self.collision_manf)
                col_path_num_var = self.make_manifest(
                    self.collision_manf_num_var)
                # This manifest provides both files that satisfy col_path's
                # dependencies.
                both_path = self.make_manifest(self.sat_both)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/bar/baz/.
                bar_path = self.make_manifest(self.sat_bar_libc)
                bar2_path = self.make_manifest(self.sat_bar_libc2)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/foo/baz/.
                foo_path = self.make_manifest(self.sat_foo_libc)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/bar/baz/, but that
                # file is tagged with variant.num=one.
                bar_path_num_var = self.make_manifest(self.sat_bar_libc_num_var)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/foo/baz/, but that
                # file is tagged with variant.num=two.
                foo_path_num_var = self.make_manifest(self.sat_foo_libc_num_var)
                # This manifest provides a file that satisfies the dependency
                # in col_path by delivering a file in patform/foo/baz/, but that
                # file is tagged with variant.num=one and variant.num=two.
                foo_path_num_var_both = self.make_manifest(
                    self.sat_foo_libc_num_var_both)

                # The following tests should all succeed because either the same
                # package delivers both files which could satisfy the dependency
                # or only one package which delivers the dependency is being
                # resolved against.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, both_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_both", both_path,
                    col_path)

                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, bar_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_bar_libc", bar_path,
                    col_path)

                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, foo_path], self.api_obj)
                __check_results(pkg_deps, errs, "pkg:/sat_foo_libc", foo_path,
                    col_path)

                # This test should also pass because the dependencies will be
                # variant tagged, just as the file delivery is.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path_num_var, foo_path_num_var, bar_path_num_var],
                    self.api_obj)
                if errs:
                        raise RuntimeError("Got the following unexpected "
                            "errors:\n%s" %
                            "\n".join([str(e) for e in errs]))
                self.assertEqual(len(pkg_deps), 3)
                self.assertEqual(len(pkg_deps[foo_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[bar_path_num_var]), 0)
                self.assertEqual(len(pkg_deps[col_path_num_var]), 2)
                for d in pkg_deps[col_path_num_var]:
                        if d.attrs["fmri"] not in \
                            ("pkg:/sat_foo_libc", "pkg:/sat_bar_libc"):
                                raise RuntimeError("Unexpected fmri in %s" % d)

                # This resolution should fail because in the case of
                # variant.num=one, files which satisfy the dependency are
                # delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path_num_var, foo_path_num_var_both, bar_path_num_var],
                    self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.MultiplePackagesPathError):
                                for d in e.res:
                                        if d.attrs["fmri"] not in \
                                            ("pkg:/sat_foo_libc",
                                            "pkg:/sat_bar_libc"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path_num_var)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)

                # This resolution should fail because files which satisfy the
                # dependency are being delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, bar_path, foo_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.MultiplePackagesPathError):
                                for d in e.res:
                                        if d.attrs["fmri"] not in \
                                            ("pkg:/sat_foo_libc",
                                            "pkg:/sat_bar_libc"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)

                # This resolution should fail because files which satisfy the
                # dependency are being delivered in two packages.
                pkg_deps, errs = dependencies.resolve_deps(
                    [col_path, bar_path, bar2_path], self.api_obj)
                self.assertEqual(len(pkg_deps), 3)
                for k in pkg_deps:
                        if pkg_deps[k]:
                                raise RuntimeError("Got the following "
                                    "unexpected dependencies:\n%s" %
                                    "\n".join(["%s\n%s" %
                                        (k,"\n".join([
                                            "\t%s" % d for d in pkg_deps[k]]))
                                            for k in pkg_deps
                                        ]))
                if len(errs) != 2:
                        raise RuntimeError("Didn't get two errors:\n%s" %
                            "\n".join(str(e) for e in errs))
                for e in errs:
                        if isinstance(e,
                            dependencies.AmbiguousPathError):
                                for d in e.pkgs:
                                        if d not in \
                                            ("pkg:/sat_bar_libc",
                                            "pkg:/sat_bar_libc2"):
                                                raise RuntimeError("Unexpected "
                                                    "dependency action:%s" % d)
                                self.assertEqual(
                                    e.source.attrs["%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        elif isinstance(e,
                            dependencies.UnresolvedDependencyError):
                                self.assertEqual(e.path, col_path)
                                self.assertEqual(
                                    e.file_dep.attrs[
                                        "%s.file" % self.depend_dp],
                                    "no_such_named_file")
                        else:
                                raise RuntimeError("Unexpected error:%s" % e)
