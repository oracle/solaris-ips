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

import os
import shutil
import sys
import tempfile
import unittest

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)

import pkg5unittest

import pkg.fmri as fmri
import pkg.catalog as catalog
import pkg.updatelog as updatelog
import pkg.portable as portable

import pkg.publish.dependencies as dependencies

class TestDependencyAnalyzer(pkg5unittest.Pkg5TestCase):
        ext_hardlink_manf = """ \
hardlink path=usr/foo target=../var/log/syslog
hardlink path=usr/bar target=../var/log/syslog
hardlink path=baz target=var/log/authlog
"""

        int_hardlink_manf = """ \
hardlink path=usr/foo target=../var/log/syslog
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog 
"""

        int_hardlink_manf_test_symlink = """ \
hardlink path=usr/foo target=../var/log/syslog
file NOHASH group=sys mode=0644 owner=root path=bar/syslog 
"""

        ext_pb_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=lib/svc/method/svc-pkg-depot
"""

        int_pb_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=lib/svc/method/svc-pkg-depot
file NOHASH group=bin mode=0755 owner=root path=usr/bin/ksh
"""

        ext_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1
"""

        int_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=lib/libc.so.1
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1
"""
        ext_python_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py
"""
        variant_manf_1 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=lib/svc/method/svc-pkg-depot
file NOHASH group=bin mode=0755 owner=root path=usr/bin/ksh variant.arch=foo
"""

        variant_manf_2 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=lib/svc/method/svc-pkg-depot variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=usr/bin/ksh variant.arch=foo
"""

        variant_manf_3 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=lib/svc/method/svc-pkg-depot variant.arch=bar
file NOHASH group=bin mode=0755 owner=root path=usr/bin/ksh variant.arch=foo
"""

        @staticmethod
        def make_manifest(str):
                t_fd, t_path = tempfile.mkstemp()
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write(str)
                t_fh.close()
                return t_path
        
        def test_ext_hardlink(self):
                """Check that a hardlink with a target outside the package is
                reported as a dependency."""

                def _check_results(res):
                        ds, es, ms = res
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 3)
                        ans = set(["usr/foo", "usr/bar"])
                        for d in ds:
                                self.assertEqual(d.dep_vars, None)
                                self.assert_(d.is_error())
                                if d.dep_key() == "var/log/syslog":
                                        self.assert_(
                                            d.action.attrs["path"] in ans)
                                        ans.remove(d.action.attrs["path"])
                                else:
                                        self.assertEqual(d.dep_key(),
                                            "var/log/authlog")
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "baz")
                t_path = None
                try:
                        t_path = self.make_manifest(self.ext_hardlink_manf)
                        _check_results(dependencies.list_implicit_deps(t_path,
                            "/"))
                        _check_results(dependencies.list_implicit_deps(t_path,
                            "/",
                            remove_internal_deps=False))
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_int_hardlink(self):
                """Check that a hardlink with a target inside the package is
                not reported as a dependency, unless the flag to show internal
                dependencies is set."""

                t_path = None
                try:
                        t_path = self.make_manifest(self.int_hardlink_manf)
                        ds, es, ms = \
                            dependencies.list_implicit_deps(t_path, "/")
                        self.assert_(len(es) == 0 and len(ms) == 1)
                        self.assert_(len(ds) == 0)
                        ds, es, ms = dependencies.list_implicit_deps(t_path,
                            "/", remove_internal_deps=False)
                        self.assert_(len(es) == 0 and len(ms) == 1)
                        self.assertEqual(len(ds), 1)
                        d = ds[0]
                        self.assertEqual(d.dep_vars, None)
                        self.assert_(d.is_error())
                        self.assertEqual(d.dep_key(), "var/log/syslog")
                        self.assertEqual(d.action.attrs["path"], "usr/foo")
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_ext_pb(self):
                """Check that a file that starts with #! and references a file
                outside its package is reported as a dependency."""
                
                def _check_res(res):
                        ds, es, ms = res
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assertEqual(d.dep_vars, None)
                        self.assertEqual(d.dep_key(), "usr/bin/ksh")
                        self.assertEqual(d.action.attrs["path"],
                            "lib/svc/method/svc-pkg-depot")
                t_path = None
                try:
                        t_path = self.make_manifest(self.ext_pb_manf)
                        _check_res(dependencies.list_implicit_deps(t_path, "/"))
                        _check_res(dependencies.list_implicit_deps(t_path, "/",
                            remove_internal_deps=False))
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_int_pb(self):
                """Check that a file that starts with #! and references a file
                outside its package is not reported as a dependency unless
                the flag to show internal dependencies is set."""

                t_path = None
                try:
                        t_path = self.make_manifest(self.int_pb_manf)
                        ds, es, ms = \
                            dependencies.list_implicit_deps(t_path, "/")
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assertEqual(d.dep_vars, None)
                        self.assertEqual(d.base_name, "libc.so.1")
                        self.assertEqual(set(d.run_paths), set(["lib",
                            "usr/lib"]))
                        ds, es, ms = dependencies.list_implicit_deps(t_path,
                            "/", remove_internal_deps=False)
                        for d in ds:
                                self.assert_(d.is_error())
                                self.assertEqual(d.dep_vars, None)
                                if d.dep_key() == "usr/bin/ksh":
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "lib/svc/method/svc-pkg-depot")
                                elif d.dep_key() == \
                                    ("libc.so.1", ("lib", "usr/lib")):
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "usr/bin/ksh")
                                else:
                                        raise RuntimeError("Unexpected "
                                            "dependency path:%s" % dep)
                finally:
                        if t_path:
                                portable.remove(t_path)
                                
        def test_ext_elf(self):
                """Check that an elf file that requires a library outside its
                package is reported as a dependency."""

                def _check_res(res):
                        ds, es, ms = res
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assertEqual(d.dep_vars, None)
                        self.assertEqual(d.base_name, "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            ("libc.so.1", ("lib", "usr/lib")))
                        self.assertEqual(
                                d.action.attrs["path"],
                                "usr/xpg4/lib/libcurses.so.1")
                t_path = None
                try:
                        t_path = self.make_manifest(self.ext_elf_manf)
                        _check_res(dependencies.list_implicit_deps(t_path, "/"))
                        _check_res(dependencies.list_implicit_deps(t_path, "/",
                            remove_internal_deps=False))
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_int_elf(self):
                """Check that an elf file that requires a library inside its
                package is not reported as a dependency unless the flag to show
                internal dependencies is set."""

                def _check_all_res(res):
                        ds, es, ms = res
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assertEqual(d.dep_vars, None)
                        self.assertEqual(d.base_name, "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            ("libc.so.1", ("lib", "usr/lib")))
                        self.assertEqual(
                                d.action.attrs["path"],
                                "usr/xpg4/lib/libcurses.so.1")
                t_path = None
                try:
                        t_path = self.make_manifest(self.int_elf_manf)
                        d_map, es, ms = dependencies.list_implicit_deps(t_path,
                            "/")
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(d_map) == 0)
                        _check_all_res(dependencies.list_implicit_deps(t_path,
                            "/", remove_internal_deps=False))
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_ext_python_dep(self):
                """Check that a python file that imports a module outside its
                package is reported as a dependency."""

                def _check_all_res(res):
                        ds, es, ms = res
                        expected_deps = set(["usr/bin/python2.4",
                            "usr/lib/python2.4/vendor-packages/pkg/" +
                            "__init__.py",
                            "usr/lib/python2.4/vendor-packages/pkg/indexer.py",
                            "usr/lib/python2.4/vendor-packages/pkg/misc.py",
                            "usr/lib/python2.4/vendor-packages/pkg/" +
                            "search_storage.py"])
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assertEqual(len(ds), len(expected_deps))
                        for d in ds:
                                self.assert_(d.is_error())
                                self.assertEqual(d.dep_vars, None)
                                self.assert_(d.dep_key() in
                                             expected_deps)
                                expected_deps.remove(d.dep_key())
                                self.assertEqual(
                                        d.action.attrs["path"],
                                        "usr/lib/python2.4/vendor-packages/"
                                        "pkg/client/indexer.py")
                t_path = None
                try:
                        t_path = self.make_manifest(self.ext_python_manf)
                        _check_all_res(dependencies.list_implicit_deps(t_path,
                            "/"))
                        _check_all_res(dependencies.list_implicit_deps(t_path,
                            "/", remove_internal_deps=False))
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_variants_1(self):
                """Test that a file which satisfies a dependency only under a
                certain set of variants results in the dependency being reported
                for the other set of variants."""

                t_path = None
                try:
                        t_path = self.make_manifest(self.variant_manf_1)
                        ds, es, ms = \
                            dependencies.list_implicit_deps(t_path, "/")
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 2)
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_key() == "usr/bin/ksh":
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "lib/svc/method/svc-pkg-depot")
                                        self.assertEqual(len(d.dep_vars), 1)
                                        self.assert_(
                                            "variant.arch" in d.dep_vars)
                                        expected_vars = set(["bar", "baz"])
                                        for v in d.dep_vars["variant.arch"]:
                                                self.assert_(v in expected_vars)
                                                expected_vars.remove(v)
                                        self.assertEqual(expected_vars, set())
                                elif d.dep_key() == \
                                    ("libc.so.1", ("lib", "usr/lib")):
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "usr/bin/ksh")
                                        self.assertEqual(
                                            set(d.dep_vars["variant.arch"]),
                                            set(["foo"]))
                                else:
                                        raise RuntimeError("Unexpected "
                                            "dependency path:%s" % d.dep_key())
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_variants_2(self):
                """Test that when the variants of the action with the dependency
                and the action satisfying the dependency share the same
                dependency, an external dependency is not reported."""

                t_path = None
                try:
                        t_path = self.make_manifest(self.variant_manf_2)
                        ds, es, ms = \
                            dependencies.list_implicit_deps(t_path, "/")
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assertEqual(set(d.dep_vars.keys()),
                            set(["variant.arch"]))
                        self.assertEqual(set(d.dep_vars["variant.arch"]),
                            set(["foo"]))
                        self.assertEqual(d.base_name, "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        ds, es, ms = dependencies.list_implicit_deps(t_path,
                            "/", remove_internal_deps=False)
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 2)
                        for d in ds:
                                self.assert_(d.is_error())
                                self.assertEqual(set(d.dep_vars.keys()),
                                    set(["variant.arch"]))
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["foo"]))
                                if d.dep_key() == "usr/bin/ksh":
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "lib/svc/method/svc-pkg-depot")
                                elif d.dep_key() == \
                                    ("libc.so.1", ("lib", "usr/lib")):
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "usr/bin/ksh")
                                else:
                                        raise RuntimeError(
                                            "Unexpected dependency path:%s" %
                                            d.dep_key())
                finally:
                        if t_path:
                                portable.remove(t_path)


        def test_variants_3(self):
                """Test that when the action with the dependency is tagged with
                a different variant than the action which could satisfy it, it's
                reported as an external dependency."""

                t_path = None
                try:
                        t_path = self.make_manifest(self.variant_manf_3)
                        ds, es, ms = \
                            dependencies.list_implicit_deps(t_path, "/")
                        self.assert_(len(es) == 0 and len(ms) == 0)
                        self.assert_(len(ds) == 2)
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_key() == "usr/bin/ksh":
                                        self.assertEqual(
                                            d.action.attrs["path"],
                                            "lib/svc/method/svc-pkg-depot")
                                        self.assertEqual(set(d.dep_vars.keys()),
                                            set(["variant.arch"]))
                                        self.assertEqual(
                                            set(d.dep_vars["variant.arch"]),
                                            set(["bar"]))
                                elif d.dep_key() == \
                                    ("libc.so.1", ("lib", "usr/lib")):
                                        self.assertEqual(d.action.attrs["path"],
                                            "usr/bin/ksh")
                                        self.assertEqual(set(d.dep_vars.keys()),
                                            set(["variant.arch"]))
                                        self.assertEqual(
                                            set(d.dep_vars["variant.arch"]),
                                            set(["foo"]))
                                else:
                                        raise RuntimeError("Unexpected "
                                            "dependency path:%s" % d.dep_key())
                finally:
                        if t_path:
                                portable.remove(t_path)

        def test_symlinks(self):
                """Test that a file is recognized as delivered when a symlink
                is involved."""

                dir_path = None
                t_path = None
                try:
                        dir_path = tempfile.mkdtemp()
                        usr_path = os.path.join(dir_path, "usr")
                        hardlink_path = os.path.join(usr_path, "foo")
                        bar_path = os.path.join(dir_path, "bar")
                        file_path = os.path.join(bar_path, "syslog")
                        var_path = os.path.join(dir_path, "var")
                        symlink_loc = os.path.join(var_path, "log")
                        hardlink_target = os.path.join(usr_path,
                            "../var/log/syslog")
                        os.mkdir(usr_path)
                        os.mkdir(bar_path)
                        os.mkdir(var_path)
                        fh = open(file_path, "w")
                        fh.close()
                        os.symlink(bar_path, symlink_loc)
                        os.link(hardlink_target, hardlink_path)

                        t_path = self.make_manifest(
                            self.int_hardlink_manf_test_symlink)
                        ds, es, ms = dependencies.list_implicit_deps(t_path,
                            dir_path)
                finally:
                        if dir_path:
                                shutil.rmtree(dir_path)
                        if t_path:
                                portable.remove(t_path)
