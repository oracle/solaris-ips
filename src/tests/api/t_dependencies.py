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

import cli.testutils as testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)

import pkg5unittest

import pkg.catalog as catalog
import pkg.flavor.elf as elf
import pkg.fmri as fmri
import pkg.portable as portable
import pkg.publish.dependencies as dependencies
import pkg.updatelog as updatelog

class TestDependencyAnalyzer(pkg5unittest.Pkg5TestCase):

        paths = {
            "authlog_path": "var/log/authlog",
            "curses_path": "usr/xpg4/lib/libcurses.so.1",
            "indexer_path":
                "usr/lib/python2.6/vendor-packages/pkg_test/client/indexer.py",
            "ksh_path": "usr/bin/ksh",
            "libc_path": "lib/libc.so.1",
            "pkg_path":
                "usr/lib/python2.6/vendor-packages/pkg_test/client/__init__.py",
            "script_path": "lib/svc/method/svc-pkg-depot",
            "syslog_path": "var/log/syslog"
        }   

        ext_hardlink_manf = """ \
hardlink path=usr/foo target=../%(syslog_path)s
hardlink path=usr/bar target=../%(syslog_path)s
hardlink path=baz target=%(authlog_path)s
""" % paths

        int_hardlink_manf = """ \
hardlink path=usr/foo target=../%(syslog_path)s
file NOHASH group=sys mode=0644 owner=root path=%(syslog_path)s 
""" % paths

        int_hardlink_manf_test_symlink = """ \
hardlink path=usr/foo target=../%(syslog_path)s
file NOHASH group=sys mode=0644 owner=root path=bar/syslog 
""" % paths

        ext_script_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s
""" % paths

        int_script_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s
""" % paths

        ext_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(curses_path)s
""" % paths

        int_elf_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(libc_path)s
file NOHASH group=bin mode=0755 owner=root path=%(curses_path)s
""" % paths

        ext_python_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(indexer_path)s
""" % paths

        ext_python_pkg_manf = """ \
file NOHASH group=bin mode=0755 owner=root path=%(pkg_path)s
""" % paths

        variant_manf_1 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.arch=foo
""" % paths

        variant_manf_2 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.arch=foo
""" % paths

        variant_manf_3 = """ \
set name=variant.arch value=foo value=bar value=baz
file NOHASH group=bin mode=0755 owner=root path=%(script_path)s variant.arch=bar
file NOHASH group=bin mode=0755 owner=root path=%(ksh_path)s variant.arch=foo
""" % paths

        python_abs_text = """\
#!/usr/bin/python

from __future__ import absolute_import

import os
import sys
import pkg_test.indexer_test.foobar as indexer
import pkg.search_storage as ss
from ..misc_test import EmptyI
"""

        python_text = """\
#!/usr/bin/python

import os
import sys
import pkg_test.indexer_test.foobar as indexer
import pkg.search_storage as ss
from pkg_test.misc_test import EmptyI
"""

        script_text = "#!/usr/bin/ksh -p\n"

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)
                self.image_dir = None
                self.pid = os.getpid()
                self.pwd = os.getcwd()

                self.__test_prefix = os.path.join(tempfile.gettempdir(),
                    "ips.test.%d" % self.pid)
                self.proto_dir = os.path.join(self.__test_prefix, "proto")
                self.manf_dir = os.path.join(self.__test_prefix, "manfs")
                os.makedirs(self.proto_dir)
                os.makedirs(self.manf_dir)

        def tearDown(self):
                pkg5unittest.Pkg5TestCase.tearDown(self)
                shutil.rmtree(self.__test_prefix)

        def make_python_test_files(self, py_version):
                pdir = "usr/lib/python%s/vendor-packages" % py_version
                for p in ["pkg_test/indexer_test/foobar",
                    "pkg_test/search_storage_test", "pkg_test/misc_test"]:
                        self.make_text_file("%s/%s.py" % (pdir, p))
                self.make_text_file("%s/pkg_test/__init__.py" % pdir,
                    "#!/usr/bin/python\n")
                self.make_text_file("%s/pkg_test/indexer_test/__init__.py" %
                    pdir, "#!/usr/bin/python")
                
        def make_manifest(self, str):
                t_fd, t_path = tempfile.mkstemp(dir=self.manf_dir)
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write(str)
                t_fh.close()
                return t_path

        def make_text_file(self, o_path, o_text=""):
                f_path = os.path.join(self.proto_dir, o_path)
                f_dir = os.path.dirname(f_path)
                if not os.path.exists(f_dir):
                        os.makedirs(f_dir)

                fh = open(f_path, "w")
                fh.write(o_text)
                fh.close()
                return f_path

        def make_elf(self, final_path, static=False):
                t_fd, t_path = tempfile.mkstemp(suffix=".c", dir=self.proto_dir)
                out_file = os.path.join(self.proto_dir, final_path)
                out_dir = os.path.dirname(out_file)
                if not os.path.exists(out_dir):
                        os.makedirs(out_dir)
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write("int main(){}\n")
                t_fh.close()
                cmd = ["/usr/bin/cc", "-o", out_file]
                if static:
                        cmd.append("-static")
                cmd.append(t_path)
                s = subprocess.Popen(cmd)
                rc = s.wait()
                if rc != 0:
                        raise RuntimeError("Compile of %s failed. Runpaths "
                            "were %s" % " ".join(run_paths))
                return out_file

        def __path_to_key(self, path):
                if path == self.paths["libc_path"]:
                        return ((os.path.basename(path),), tuple([
                            p.lstrip("/") for p in elf.default_run_paths
                        ]))
                return ((os.path.basename(path),), (os.path.dirname(path),))

        def test_ext_hardlink(self):
                """Check that a hardlink with a target outside the package is
                reported as a dependency."""

                def _check_results(res):
                        ds, es, ms = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 3)
                        ans = set(["usr/foo", "usr/bar"])
                        for d in ds:
                                self.assert_(d.dep_vars.is_satisfied())
                                self.assert_(d.is_error())
                                if d.dep_key() == self.__path_to_key(
                                    self.paths["syslog_path"]):
                                        self.assert_(
                                            d.action.attrs["path"] in ans)
                                        ans.remove(d.action.attrs["path"])
                                else:
                                        self.assertEqual(d.dep_key(),
                                            self.__path_to_key(
                                                self.paths["authlog_path"]))
                                        self.assertEqual(
                                            d.action.attrs["path"], "baz")
                t_path = self.make_manifest(self.ext_hardlink_manf)
                _check_results(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, []))
                _check_results(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [],
                    remove_internal_deps=False))

        def test_int_hardlink(self):
                """Check that a hardlink with a target inside the package is
                not reported as a dependency, unless the flag to show internal
                dependencies is set."""

                t_path = self.make_manifest(self.int_hardlink_manf)
                self.make_text_file(self.paths["syslog_path"])
                ds, es, ms = \
                    dependencies.list_implicit_deps(t_path, self.proto_dir, {},
                        [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assert_(len(ms) == 1)
                self.assert_(len(ds) == 0)

                # Check that internal dependencies are as expected.
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(len(ms), 1)
                self.assertEqual(len(ds), 1)
                d = ds[0]
                self.assert_(d.dep_vars.is_satisfied())
                self.assert_(d.is_error())
                self.assertEqual(d.dep_key(), self.__path_to_key(
                    self.paths["syslog_path"]))
                self.assertEqual(d.action.attrs["path"], "usr/foo")

        def test_ext_script(self):
                """Check that a file that starts with #! and references a file
                outside its package is reported as a dependency."""
                
                def _check_res(res):
                        ds, es, ms = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["ksh_path"]))
                        self.assertEqual(d.action.attrs["path"],
                            self.paths["script_path"])
                t_path = self.make_manifest(self.ext_script_manf)
                self.make_text_file(self.paths["script_path"], self.script_text)
                _check_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, []))
                _check_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False))

        def test_int_script(self):
                """Check that a file that starts with #! and references a file
                inside its package is not reported as a dependency unless
                the flag to show internal dependencies is set."""

                t_path = self.make_manifest(self.int_script_manf)
                self.make_elf(self.paths["ksh_path"])
                self.make_text_file(self.paths["script_path"], self.script_text)
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 1)
                d = ds[0]
                self.assert_(d.is_error())
                self.assert_(d.dep_vars.is_satisfied())
                self.assertEqual(d.base_names[0], "libc.so.1")
                self.assertEqual(set(d.run_paths), set(["lib",
                    "usr/lib"]))

                # Check that internal dependencies are as expected.
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False)
                self.assertEqual(len(ds), 2)
                for d in ds:
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                        else:
                                raise RuntimeError("Unexpected "
                                    "dependency path:%s" % d)
                                
        def test_ext_elf(self):
                """Check that an elf file that requires a library outside its
                package is reported as a dependency."""

                def _check_res(res):
                        ds, es, ms = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.base_names[0], "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["libc_path"]))
                        self.assertEqual(
                                d.action.attrs["path"],
                                self.paths["curses_path"])

                t_path = self.make_manifest(self.ext_elf_manf)
                self.make_elf(self.paths["curses_path"])
                _check_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, []))
                _check_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False))

        def test_int_elf(self):
                """Check that an elf file that requires a library inside its
                package is not reported as a dependency unless the flag to show
                internal dependencies is set."""

                def _check_all_res(res):
                        ds, es, ms = res
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))
                        self.assertEqual(ms, {})
                        self.assert_(len(ds) == 1)
                        d = ds[0]
                        self.assert_(d.is_error())
                        self.assert_(d.dep_vars.is_satisfied())
                        self.assertEqual(d.base_names[0], "libc.so.1")
                        self.assertEqual(set(d.run_paths),
                            set(["lib", "usr/lib"]))
                        self.assertEqual(d.dep_key(),
                            self.__path_to_key(self.paths["libc_path"]))
                        self.assertEqual(d.action.attrs["path"],
                            self.paths["curses_path"])

                t_path = self.make_manifest(self.int_elf_manf)
                self.make_elf(self.paths["curses_path"])
                self.make_elf(self.paths["libc_path"], static=True)
                d_map, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(d_map) == 0)

                # Check that internal dependencies are as expected.
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False))

        def test_ext_python_dep(self):
                """Check that a python file that imports a module outside its
                package is reported as a dependency."""

                def _check_all_res(res):
                        ds, es, ms = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "misc_test", "os",
                            "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["indexer_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_manf)
                self.make_python_test_files(2.6)
                self.make_text_file(self.paths["indexer_path"],
                    self.python_text)
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, []))
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False))

        def test_ext_python_abs_import_dep(self):
                """Check that a python file that uses absolute imports a module
                is handled correctly."""

                def _check_all_res(res):
                        ds, es, ms = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "os", "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if len(es) != 1:
                                raise RuntimeError("Expected exactly 1 error, "
                                    "got:%\n" + "\n".join([str(s) for s in es]))
                        if es[0].name != "misc_test":
                                raise RuntimeError("Didn't get the expected "
                                    "error. Error found was:%s" % es[0])

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["indexer_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_manf)
                self.make_python_test_files(2.6)
                # Check that absolute imports still work.
                self.make_text_file(self.paths["indexer_path"],
                    self.python_abs_text)
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, []))
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False))

        def test_ext_python_pkg_dep(self):
                """Check that a python file that is the __init__.py file for a
                package is handled correctly."""

                def _check_all_res(res):
                        ds, es, ms = res
                        mod_suffs = ["/__init__.py", ".py", ".pyc", ".pyo"]
                        mod_names = ["foobar", "misc_test", "os",
                            "search_storage"]
                        pkg_names = ["indexer_test", "pkg", "pkg_test"]
                        expected_deps = set([("python",)] +
                            [tuple(sorted([
                                "%s%s" % (n,s) for s in mod_suffs
                            ]))
                            for n in mod_names] +
                            [("%s/__init__.py" % n,) for n in pkg_names])
                        if es != []:
                                raise RuntimeError("Got errors in results:" +
                                    "\n".join([str(s) for s in es]))

                        self.assertEqual(ms, {})
                        for d in ds:
                                self.assert_(d.is_error())
                                if d.dep_vars is None:
                                        raise RuntimeError("This dep had "
                                            "depvars of None:%s" % d)
                                self.assert_(d.dep_vars.is_satisfied())
                                if not d.dep_key()[0] in expected_deps:
                                        raise RuntimeError("Got this "
                                            "unexpected dep:%s\n\nd:%s" %
                                            (d.dep_key()[0], d))
                                expected_deps.remove(d.dep_key()[0])
                                self.assertEqual(d.action.attrs["path"],
                                        self.paths["pkg_path"])
                        if expected_deps:
                                raise RuntimeError("Couldn't find these "
                                    "dependencies:\n" + "\n".join(
                                    [str(s) for s in sorted(expected_deps)]))
                self.__debug = True
                t_path = self.make_manifest(self.ext_python_pkg_manf)
                self.make_python_test_files(2.6)
                self.make_text_file(self.paths["pkg_path"], self.python_text)
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, []))
                _check_all_res(dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False))

        def test_variants_1(self):
                """Test that a file which satisfies a dependency only under a
                certain set of variants results in the dependency being reported
                for the other set of variants."""

                t_path = self.make_manifest(self.variant_manf_1)
                self.make_text_file(self.paths["script_path"], self.script_text)
                self.make_elf(self.paths["ksh_path"])
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                                self.assertEqual(len(d.dep_vars), 1)
                                self.assert_("variant.arch" in d.dep_vars)
                                expected_vars = set([("bar",), ("baz",)])
                                for v in d.dep_vars.not_sat_set:
                                        if v not in expected_vars:
                                                raise RuntimeError("Variant %s "
                                                    "was not in %s" %
                                                     (v, expected_vars))
                                        expected_vars.remove(v)
                                self.assertEqual(expected_vars, set())
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(
                                    d.action.attrs["path"],
                                    self.paths["ksh_path"])
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["foo"]))
                        else:
                                raise RuntimeError("Unexpected "
                                    "dependency path:%s" % (d.dep_key(),))

        def test_variants_2(self):
                """Test that when the variants of the action with the dependency
                and the action satisfying the dependency share the same
                dependency, an external dependency is not reported."""

                t_path = self.make_manifest(self.variant_manf_2)
                self.make_text_file(self.paths["script_path"], self.script_text)
                self.make_elf(self.paths["ksh_path"])
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [])    
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 1)
                d = ds[0]
                self.assert_(d.is_error())
                self.assertEqual(set(d.dep_vars.keys()), set(["variant.arch"]))
                self.assertEqual(set(d.dep_vars["variant.arch"]), set(["foo"]))
                self.assertEqual(d.base_names[0], "libc.so.1")
                self.assertEqual(set(d.run_paths), set(["lib", "usr/lib"]))

                # Check that internal dependencies are as expected.
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [], remove_internal_deps=False)
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        self.assertEqual(set(d.dep_vars.keys()),
                           set(["variant.arch"]))
                        self.assertEqual(set(d.dep_vars["variant.arch"]),
                            set(["foo"]))
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                        else:
                                raise RuntimeError(
                                    "Unexpected dependency path:%s" %
                                    (d.dep_key(),))

        def test_variants_3(self):
                """Test that when the action with the dependency is tagged with
                a different variant than the action which could satisfy it, it's
                reported as an external dependency."""

                t_path = self.make_manifest(self.variant_manf_3)
                self.make_text_file(self.paths["script_path"], self.script_text)
                self.make_elf(self.paths["ksh_path"])
                ds, es, ms = dependencies.list_implicit_deps(t_path,
                    self.proto_dir, {}, [])
                if es != []:
                        raise RuntimeError("Got errors in results:" +
                            "\n".join([str(s) for s in es]))
                self.assertEqual(ms, {})
                self.assert_(len(ds) == 2)
                for d in ds:
                        self.assert_(d.is_error())
                        if d.dep_key() == self.__path_to_key(
                            self.paths["ksh_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["script_path"])
                                self.assertEqual(set(d.dep_vars.keys()),
                                    set(["variant.arch"]))
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["bar"]))
                        elif d.dep_key() == self.__path_to_key(
                            self.paths["libc_path"]):
                                self.assertEqual(d.action.attrs["path"],
                                    self.paths["ksh_path"])
                                self.assertEqual(set(d.dep_vars.keys()),
                                    set(["variant.arch"]))
                                self.assertEqual(
                                    set(d.dep_vars["variant.arch"]),
                                    set(["foo"]))
                        else:
                                raise RuntimeError("Unexpected "
                                    "dependency path:%s" % (d.dep_key(),))

        def test_symlinks(self):
                """Test that a file is recognized as delivered when a symlink
                is involved."""

                usr_path = os.path.join(self.proto_dir, "usr")
                hardlink_path = os.path.join(usr_path, "foo")
                bar_path = os.path.join(self.proto_dir, "bar")
                file_path = os.path.join(bar_path, "syslog")
                var_path = os.path.join(self.proto_dir, "var")
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
                    self.proto_dir, {}, [])
