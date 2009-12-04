#!/usr/bin/python2.6
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
import subprocess
import tempfile
import unittest

import pkg.flavor.base as base
import pkg.portable as portable

class TestPkgdepBasics(testutils.SingleDepotTestCase):
        persistent_depot = True

        test_manf_1 = """\
hardlink path=baz target=var/log/authlog
file NOHASH group=bin mode=0755 owner=root \
path=usr/lib/python2.6/v\
endor-packages/pkg/client/indexer.py
file NOHA\
SH group=bin mode=0755 owner=root path=u\
sr/xpg4/lib/libcurses.so.1
"""
        test_manf_2 = """
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=etc/pam.conf
"""

        int_hardlink_manf = """ \
hardlink path=usr/foo target=../var/log/syslog
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""

        resolve_dep_manf = """
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog preserve=true
"""

        payload_manf = """\
hardlink path=usr/baz target=../foo/bar.py
file usr/lib/python2.6/vendor-packages/pkg/client/indexer.py \
group=bin mode=0755 owner=root path=foo/bar.py
"""

        elf_sub_manf = """\
file %(file_loc)s group=bin mode=0755 owner=root path=bar/foo
"""

        kernel_manf = """\
file %(file_loc)s group=bin mode=0755 owner=root path=kernel/foobar
"""

        miss_payload_manf = """\
file tmp/file/should/not/exist/here/foo group=bin mode=0755 owner=root path=foo/bar.py
"""

        res_manf_1 = """\
depend %(depend_debug_prefix)s.file=usr/bin/python fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=var/log/authlog fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_full_manf_1 = """\
hardlink path=baz target=var/log/authlog
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1
depend %(depend_debug_prefix)s.file=usr/bin/python fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=var/log/authlog fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        err_manf_1 = """\
Couldn't find %s/usr/xpg4/lib/libcurses.so.1
"""
        res_manf_2 = """\
depend %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/xpg4/lib/libcurses.so.1 variant.arch=foo %(depend_debug_prefix)s.type=elf
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_int_manf = """\
depend %(depend_debug_prefix)s.file=var/log/syslog fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/foo %(depend_debug_prefix)s.type=hardlink
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_manf_2_missing = "ascii text"

        resolve_error = """\
%(manf_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=usr/xpg4/lib/libcurses.so.1 %(depend_debug_prefix)s.type=elf type=require variant.arch=foo' under the following combinations of variants:
variant.arch:foo
"""

        test_manf_1_resolved = """\
depend fmri=%(py_pkg_name)s %(depend_debug_prefix)s.file=usr/bin/python %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script type=require
depend fmri=%(ips_pkg_name)s %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/__init__.py %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python type=require
depend fmri=%(ips_pkg_name)s %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/indexer.py %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python type=require
depend fmri=%(ips_pkg_name)s %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/misc.py %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python type=require
depend fmri=%(ips_pkg_name)s %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/search_storage.py %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python type=require
depend fmri=%(resolve_name)s %(depend_debug_prefix)s.file=var/log/authlog %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink type=require
depend fmri=%(csl_pkg_name)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=usr/xpg4/lib/libcurses.so.1 %(depend_debug_prefix)s.type=elf type=require
"""

        test_manf_1_full_resolved = test_manf_1_resolved + test_manf_1

        res_full_manf_1_mod_proto = res_full_manf_1 + """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=usr/xpg4/lib/libcurses.so.1 %(depend_debug_prefix)s.type=elf type=require
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_payload_1 = """\
depend %(depend_debug_prefix)s.file=usr/bin/python fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=foo/bar.py %(depend_debug_prefix)s.type=script
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=foo/bar.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=foo/bar.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=foo/bar.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=foo/bar.py %(depend_debug_prefix)s.type=python
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        two_variant_deps = """\
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        two_v_deps_bar = """
set name=fmri value=pkg:/s-v-bar
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=bar
file NOHASH group=sys mode=0600 owner=root path=var/log/file2
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

        two_v_deps_output = """\
%(m1_path)s
depend fmri=pkg:/s-v-bar pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=bar
depend fmri=pkg:/s-v-baz-one pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=two
depend fmri=pkg:/s-v-bar pkg.debug.depend.file=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require


%(m2_path)s



%(m3_path)s



%(m4_path)s



"""

        payload_elf_sub_error = """\
%(payload_path)s (which will be installed at %(installed_path)s) had this token, %(tok)s, in its run path:%(rp)s.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
"""

        payload_elf_sub_stdout = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1%(replaced_path)s %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=bar/foo %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI,
    "replaced_path":"%(replaced_path)s"
}

        kernel_manf_stdout = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=kernel %(depend_debug_prefix)s.path=usr/kernel %(depend_debug_prefix)s.reason=kernel/foobar %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        kernel_manf_stdout2 = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=baz %(depend_debug_prefix)s.path=foo/bar %(depend_debug_prefix)s.reason=kernel/foobar %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        miss_payload_manf_error = """\
Couldn't find %(path_pref)s/tmp/file/should/not/exist/here/foo
"""

        double_plat_error = """\
%(image_dir)s/tmp_pkgdep_elfs/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path:/platform/$PLATFORM/foo.  It is not currently possible to automatically expand this token. Please specify its value on the command line.
%(image_dir)s/tmp_pkgdep_elfs/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path:/isadir/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line."""

        double_plat_stdout = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=bar/foo %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        double_plat_isa_error = """\
%(image_dir)s/tmp_pkgdep_elfs/elf_test (which will be installed at bar/foo) had this token, $ISALIST, in its run path:/$ISALIST/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
"""

        double_plat_isa_stdout = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=platform/pfoo/foo %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=bar/foo %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        double_double_stdout = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=platform/pfoo/foo %(depend_debug_prefix)s.path=platform/pfoo2/foo %(depend_debug_prefix)s.path=isadir/pfoo/baz %(depend_debug_prefix)s.path=isadir/pfoo2/baz %(depend_debug_prefix)s.path=isadir/pfoo/baz %(depend_debug_prefix)s.path=isadir/pfoo2/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=bar/foo %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        two_v_deps_resolve_error = """\
%(manf_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=var/log/authlog %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink type=require' under the following combinations of variants:
variant.foo:baz variant.num:three
"""
        usage_msg = """\
Usage:
        pkgdepend [options] command [cmd_options] [operands]

Subcommands:
        pkgdepend generate [-DIkMm] manifest proto_dir
        pkgdepend [options] resolve [-dMos] manifest ...

Options:
        -R dir
        --help or -?
Environment:
        PKG_IMAGE"""

        collision_manf = """\
set name=fmri value=pkg:/collision_manf
depend fmri=__TBD pkg.debug.depend.file=no_such_named_file pkg.debug.depend.path=platform/foo/baz pkg.debug.depend.path=platform/bar/baz pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require\
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

        run_path_errors = """\
The file dependency depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=no_such_named_file %(depend_debug_prefix)s.path=platform/foo/baz %(depend_debug_prefix)s.path=platform/bar/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=foo/bar %(depend_debug_prefix)s.type=elf type=require has run paths which resolve to multiple packages. The actions are as follows:
      depend fmri=pkg:/sat_bar_libc %(depend_debug_prefix)s.file=no_such_named_file %(depend_debug_prefix)s.path=platform/foo/baz %(depend_debug_prefix)s.path=platform/bar/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=foo/bar %(depend_debug_prefix)s.type=elf type=require
      depend fmri=pkg:/sat_foo_libc %(depend_debug_prefix)s.file=no_such_named_file %(depend_debug_prefix)s.path=platform/foo/baz %(depend_debug_prefix)s.path=platform/bar/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=foo/bar %(depend_debug_prefix)s.type=elf type=require
%(unresolved_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=no_such_named_file %(depend_debug_prefix)s.path=platform/foo/baz %(depend_debug_prefix)s.path=platform/bar/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=foo/bar %(depend_debug_prefix)s.type=elf type=require' under the following combinations of variants:
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI,
    "unresolved_path":"%(unresolved_path)s"
}

        amb_path_errors = """\
The file dependency depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=no_such_named_file %(depend_debug_prefix)s.path=platform/foo/baz %(depend_debug_prefix)s.path=platform/bar/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=foo/bar %(depend_debug_prefix)s.type=elf type=require depends on a path delivered by multiple packages. Those packages are:pkg:/sat_bar_libc2 pkg:/sat_bar_libc
%(unresolved_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=no_such_named_file %(depend_debug_prefix)s.path=platform/foo/baz %(depend_debug_prefix)s.path=platform/bar/baz %(depend_debug_prefix)s.path=lib %(depend_debug_prefix)s.path=usr/lib %(depend_debug_prefix)s.reason=foo/bar %(depend_debug_prefix)s.type=elf type=require' under the following combinations of variants:
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI,
    "unresolved_path":"%(unresolved_path)s"
}
        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                self.manf_dirs = os.path.join(self.img_path, "tmp_pkgdep_manfs")
                os.makedirs(self.manf_dirs)
                self.elf_dirs = os.path.join(self.img_path, "tmp_pkgdep_elfs")
                os.makedirs(self.elf_dirs)
        
        def make_manifest(self, str):
                t_fd, t_path = tempfile.mkstemp(dir=self.manf_dirs)
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write(str)
                t_fh.close()
                return t_path

        @staticmethod
        def __compare_res(b1, b2):
                res = set()
                for x in b1:
                        x_tmp = x.split()
                        found = False
                        for y in b2:
                                y_tmp = y.split()
                                if x == y or (len(x_tmp) == len(y_tmp) and
                                    x_tmp[0] == y_tmp[0] and
                                    set(x_tmp) == set(y_tmp)):
                                        found = True
                                        break
                        if not found:
                                res.add(x)
                return res

        @staticmethod
        def __read_file(file_path):
                fh = open(file_path, "rb")
                lines = fh.read()
                fh.close()
                return lines

        def make_elf(self, run_paths):
                t_fd, t_path = tempfile.mkstemp(suffix=".c", dir=self.elf_dirs)
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write("int main(){}\n")
                t_fh.close()
                out_file = os.path.join(self.elf_dirs, "elf_test")
                cmd = ["/usr/bin/cc", "-o", out_file]
                for rp in run_paths:
                        cmd.append("-R")
                        cmd.append(rp)
                cmd.append(t_path)
                s = subprocess.Popen(cmd)
                rc = s.wait()
                if rc != 0:
                        raise RuntimeError("Compile of %s failed. Runpaths "
                            "were %s" % " ".join(run_paths))
                return out_file[len(self.img_path)+1:]

        def check_res(self, expected, seen):
                seen = seen.strip()
                expected = expected.strip()
                if seen == expected:
                        return
                seen = set(seen.splitlines())
                expected = set(expected.splitlines())
                seen_but_not_expected = self.__compare_res(seen, expected)
                expected_but_not_seen = self.__compare_res(expected, seen)
                self.assertEqual(seen_but_not_expected, expected_but_not_seen)
        
        def test_opts(self):
                """Ensure that incorrect arguments don't cause a traceback."""

                self.pkgdepend("generate", exit=2)
                self.pkgdepend("generate foo", proto="", exit=2)
                self.pkgdepend("generate -z foo bar", exit=2)
                self.pkgdepend("generate no_such_file_should_exist", exit=2)
                self.pkgdepend("generate -?")
                self.pkgdepend("generate --help")
                
        def test_output(self):
                """Check that the output is in the format expected."""

                self.pkg("-R / list -Hv SUNWPython")
                python_pkg_name = self.output.split()[0]
                python_pkg_name = "/".join([python_pkg_name.split("/")[0],
                    python_pkg_name.split("/")[-1]])

                self.pkg("-R / list -Hv SUNWipkg")
                ipkg_pkg_name = self.output.split()[0]
                ipkg_pkg_name = "/".join([ipkg_pkg_name.split("/")[0],
                    ipkg_pkg_name.split("/")[-1]])

                self.pkg("-R / list -Hv SUNWcsl")
                csl_pkg_name = self.output.split()[0]
                csl_pkg_name = "/".join([csl_pkg_name.split("/")[0],
                    csl_pkg_name.split("/")[-1]])
                
                tp = self.make_manifest(self.test_manf_1)
                
                self.pkgdepend("generate %s" % tp, exit=1)
                self.check_res(self.res_manf_1, self.output)
                self.check_res(self.err_manf_1 % testutils.g_proto_area,
                    self.errout)

                self.pkgdepend("generate -m %s" % tp, exit=1)
                self.check_res(self.res_full_manf_1, self.output)
                self.check_res(self.err_manf_1 % testutils.g_proto_area,
                    self.errout)

                self.pkgdepend("generate -m %s" % tp, proto="/")
                self.check_res(self.res_full_manf_1_mod_proto, self.output)
                self.check_res("", self.errout)

                tp = self.make_manifest(self.test_manf_2)
                
                self.pkgdepend("generate %s" % tp, proto="/")
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                res_path = self.make_manifest(self.output)

                self.pkgdepend("resolve -o %s" %
                    res_path, use_proto=False, exit=1)
                self.check_res("%s" % res_path, self.output)
                self.check_res(self.resolve_error % {
                        "manf_path": res_path,
                        "depend_debug_prefix":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI,
                        "py_pkg_name": python_pkg_name,
                        "ips_pkg_name": ipkg_pkg_name,
                        "csl_pkg_name": csl_pkg_name
                    }, self.errout)
                
                self.pkgdepend("generate -M %s" % tp, proto="/")
                self.check_res(self.res_manf_2, self.output)
                self.check_res(self.res_manf_2_missing, self.errout)

                portable.remove(tp)
                portable.remove(res_path)

                tp = self.make_manifest(self.int_hardlink_manf)
                
                self.pkgdepend("generate %s" % tp, proto="/")
                self.check_res("", self.output)
                self.check_res("", self.errout)

                self.pkgdepend("generate -I %s" % tp, proto="/")
                self.check_res(self.res_int_manf, self.output)
                self.check_res("", self.errout)

                portable.remove(tp)

        def test_bug_11989(self):
                """These tests fail because they're resolved using a 2.6 based
                interpreter, instead of a 2.4 one."""

                tp = self.make_manifest(self.test_manf_1)
                
                self.pkgdepend("generate -m %s" % tp, proto="/")
                self.check_res(self.res_full_manf_1_mod_proto, self.output)
                self.check_res("", self.errout)

                dependency_mp = self.make_manifest(self.output)
                provider_mp = self.make_manifest(self.resolve_dep_manf)

                self.pkgdepend("resolve %s %s" % (dependency_mp, provider_mp),
                    use_proto=False)
                self.check_res("", self.output)
                self.check_res("", self.errout)
                dependency_res_p = dependency_mp + ".res"
                provider_res_p = provider_mp + ".res"
                lines = self.__read_file(dependency_res_p)
                self.check_res(self.test_manf_1_resolved % {
                        "resolve_name": os.path.basename(provider_mp),
                        "depend_debug_prefix":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri": base.Dependency.DUMMY_FMRI,
                        "py_pkg_name": python_pkg_name,
                        "ips_pkg_name": ipkg_pkg_name,
                        "csl_pkg_name": csl_pkg_name
                    }, lines)
                lines = self.__read_file(provider_res_p)
                self.check_res("", lines)

                portable.remove(dependency_res_p)
                portable.remove(provider_res_p)

                tmp_d = tempfile.mkdtemp()
                
                self.pkgdepend("resolve -m -d %s %s %s" %
                    (tmp_d, dependency_mp, provider_mp), use_proto=False)
                self.check_res("", self.output)
                self.check_res("", self.errout)
                dependency_res_p = os.path.join(tmp_d,
                    os.path.basename(dependency_mp))
                provider_res_p = os.path.join(tmp_d,
                    os.path.basename(provider_mp))
                lines = self.__read_file(dependency_res_p)
                self.check_res(self.test_manf_1_full_resolved % {
                        "resolve_name": os.path.basename(provider_mp),
                        "depend_debug_prefix":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI,
                        "py_pkg_name": python_pkg_name,
                        "ips_pkg_name": ipkg_pkg_name,
                        "csl_pkg_name": csl_pkg_name
                    }, lines)
                lines = self.__read_file(provider_res_p)
                self.check_res(self.resolve_dep_manf, lines)

                portable.remove(dependency_res_p)
                portable.remove(provider_res_p)

                self.pkgdepend("resolve -s foo -d %s %s %s" %
                    (tmp_d, dependency_mp, provider_mp), use_proto=False)
                self.check_res("", self.output)
                self.check_res("", self.errout)
                dependency_res_p = os.path.join(tmp_d,
                    os.path.basename(dependency_mp)) + ".foo"
                provider_res_p = os.path.join(tmp_d,
                    os.path.basename(provider_mp)) + ".foo"
                lines = self.__read_file(dependency_res_p)
                self.check_res(self.test_manf_1_resolved % {
                        "resolve_name": os.path.basename(provider_mp),
                        "depend_debug_prefix":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI,
                        "py_pkg_name": python_pkg_name,
                        "ips_pkg_name": ipkg_pkg_name,
                        "csl_pkg_name": csl_pkg_name
                    }, lines)
                lines = self.__read_file(provider_res_p)
                self.check_res("", lines)

                portable.remove(dependency_res_p)
                portable.remove(provider_res_p)

                self.pkgdepend("resolve -s .foo %s %s" %
                    (dependency_mp, provider_mp), use_proto=False)
                self.check_res("", self.output)
                self.check_res("", self.errout)
                dependency_res_p = dependency_mp + ".foo"
                provider_res_p = provider_mp + ".foo"
                lines = self.__read_file(dependency_res_p)
                self.check_res(self.test_manf_1_resolved % {
                        "resolve_name": os.path.basename(provider_mp),
                        "depend_debug_prefix":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI,
                        "py_pkg_name": python_pkg_name,
                        "ips_pkg_name": ipkg_pkg_name,
                        "csl_pkg_name": csl_pkg_name
                    }, lines)
                lines = self.__read_file(provider_res_p)
                self.check_res("", lines)

                portable.remove(dependency_res_p)
                portable.remove(provider_res_p)
                
                os.rmdir(tmp_d)
                portable.remove(dependency_mp)
                portable.remove(provider_mp)                

        def test_resolve_screen_out(self):
                """Check that the results printed to screen are what is
                expected."""
                
                m1_path = self.make_manifest(self.two_variant_deps)
                m2_path = self.make_manifest(self.two_v_deps_bar)
                m3_path = self.make_manifest(self.two_v_deps_baz_one)
                m4_path = self.make_manifest(self.two_v_deps_baz_two)
                p2_name = "s-v-bar"
                p3_name = "s-v-baz-one"
                p4_name = "s-v-baz-two"
                self.pkgdepend("resolve -o %s" %
                    " ".join([m1_path, m2_path, m3_path, m4_path]),
                    use_proto=False, exit=1)

                self.check_res(self.two_v_deps_output % {
                        "m1_path": m1_path,
                        "m2_path": m2_path,
                        "m3_path": m3_path,
                        "m4_path": m4_path
                    }, self.output)
                self.check_res(self.two_v_deps_resolve_error % {
                        "manf_path": m1_path,
                        "depend_debug_prefix":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
                    }, self.errout)

        def test_bug_10518(self):

                m_path = self.make_manifest(self.test_manf_1)

                self.pkgdepend("generate / %s " % m_path,
                    use_proto=False, exit=2)
                self.check_res(
                    "pkgdepend: The manifest file / could not be found.\n" +
                    self.usage_msg, self.errout)

                self.pkgdepend("resolve -o / ", use_proto=False, exit=2)
                self.check_res(
                    "pkgdepend: The manifest file / could not be found.\n" +
                    self.usage_msg, self.errout)

        def test_bug_11517(self):

                m_path = None
                ill_usage = 'pkgdepend: illegal global option -- M\n'
                try:
                        m_path = self.make_manifest(self.test_manf_1)

                        self.pkgdepend("resolve -M -o %s " % m_path,
                            use_proto=False, exit=2)
                        self.check_res(ill_usage + self.usage_msg,
                            self.errout)
                finally:
                        if m_path:
                                portable.remove(m_path)

        def test_bug_11805(self):
                """Test that paths as payloads work for file actions.

                This tests both that file actions with payloads have their
                dependencies analyzed correctly and that the correct path is
                used for internal dependency resolution."""

                tp = self.make_manifest(self.payload_manf)
                self.pkgdepend("generate %s" % tp)
                self.check_res(self.res_payload_1, self.output)
                self.check_res("", self.errout)

        def test_bug_11829(self):

                m_path = None
                nonsense = "This is a nonsense manifest"
                try:
                        m_path = self.make_manifest(nonsense)
                        
                        self.pkgdepend("generate %s /" % m_path,
                            use_proto=False, exit=1)
                        self.check_res('pkgdepend: Could not parse manifest ' + 
                            '%s because of the following line:\n' % m_path +
                            nonsense, self.errout)

                        self.pkgdepend("resolve -o %s " % m_path, 
                            use_proto=False, exit=1)
                        self.check_res("pkgdepend: Could not parse one or "
                            "more manifests because of the following line:\n" +
                            nonsense, self.errout)
                finally:
                        if m_path:
                                portable.remove(m_path)

        def __run_dyn_tok_test(self, run_paths, replaced_path, dep_args):
                """Using the provided run paths, produces a elf binary with
                those paths set and checks to make sure that pkgdep run with
                the provided arguments performs the substitution correctly."""

                elf_path = self.make_elf(run_paths)
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": elf_path})
                self.pkgdepend("generate %s %s %s" %
                    (dep_args, m_path, self.img_path), use_proto=False)
                self.check_res(self.payload_elf_sub_stdout %
                    {"replaced_path": \
                        (" %s.path=%s" %
                        (base.Dependency.DEPEND_DEBUG_PREFIX, replaced_path))
                    },
                    self.output)

        def test_bug_12697(self):
                """Test that the -D and -k options work as expected.

                The -D and -k options provide a way for a user to specify
                tokens to expand dynamically in run paths and the kernel paths
                to use for kernel module run paths."""

                elf_path = self.make_elf([])
                m_path = self.make_manifest(self.kernel_manf %
                    {"file_loc":elf_path})
                self.pkgdepend("generate %s %s" % (m_path, self.img_path),
                    use_proto=False)
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout, self.output)

                self.pkgdepend("generate -k baz -k foo/bar %s %s" %
                    (m_path, self.img_path), use_proto=False)
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout2, self.output)
                
                # Test unexpanded token 
                rp = ["/platform/$PLATFORM/foo"]
                elf_path = self.make_elf(rp)
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": elf_path})
                self.pkgdepend("generate %s %s" % (m_path, self.img_path),
                    use_proto=False, exit=1)
                self.check_res((self.payload_elf_sub_error %
                    {
                        "payload_path": os.path.join(self.img_path, elf_path),
                        "installed_path": "bar/foo",
                        "tok": "$PLATFORM",
                        "rp": rp[0]
                    }), self.errout)
                self.check_res(self.payload_elf_sub_stdout %
                    {"replaced_path": ""}, self.output)

                self.check_res(self.payload_elf_sub_stdout %
                    {"replaced_path": ""}, self.output)

                # Test token expansion
                self.__run_dyn_tok_test(["/platform/$PLATFORM/foo"],
                    "platform/pfoo/foo", "-D PLATFORM=pfoo")

                self.__run_dyn_tok_test(["/foo/bar/$ISALIST/baz"],
                    "foo/bar/SUBL/baz", "-D '$ISALIST=SUBL'")

                self.__run_dyn_tok_test(["/foo/$PLATFORM/$ISALIST/baz"],
                    "foo/pfoo/bar/SUBL/baz",
                    "-D ISALIST=SUBL -D PLATFORM=pfoo/bar")

                self.__run_dyn_tok_test(
                    ["/$PLATFORM/$PLATFORM/$ISALIST/$PLATFORM"],
                    "bar/bar/SUBL/bar", "-D ISALIST=SUBL -D PLATFORM=bar")

                # Test multiple run paths and multiple subs
                rp = ["/platform/$PLATFORM/foo", "/$ISALIST/$PLATFORM/baz"]
                elf_path = self.make_elf(rp)
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": elf_path})
                self.pkgdepend("generate -D ISALIST=isadir %s %s" %
                    (m_path, self.img_path), use_proto=False, exit=1)
                self.check_res(self.double_plat_error %
                    {"image_dir": self.img_path}, self.errout)
                self.check_res(self.double_plat_stdout, self.output)

                self.pkgdepend("generate -D PLATFORM=pfoo %s %s" %
                    (m_path, self.img_path), use_proto=False, exit=1)
                self.check_res(self.double_plat_isa_error %
                    {"image_dir": self.img_path}, self.errout)
                self.check_res(self.double_plat_isa_stdout, self.output)

                self.pkgdepend("generate -D PLATFORM=pfoo -D PLATFORM=pfoo2 "
                    "-D ISALIST=isadir -D ISALIST=isadir %s %s" %
                    (m_path, self.img_path), use_proto=False)
                self.check_res("", self.errout)
                self.check_res(self.double_double_stdout, self.output)
                
        def test_bug_12816(self):
                """Test that the error produced by a missing payload action
                uses the right path."""

                m_path = self.make_manifest(self.miss_payload_manf)
                self.pkgdepend("generate %s %s" % (m_path, self.img_path),
                    use_proto=False, exit=1)
                self.check_res(self.miss_payload_manf_error %
                    {"path_pref":self.img_path}, self.errout)
                self.check_res("", self.output)

        def test_bug_12896(self):
                """Test that the errors that happen when multiple packages
                deliver a dependency are displayed correctly."""

                col_path = self.make_manifest(self.collision_manf)
                bar_path = self.make_manifest(self.sat_bar_libc)
                bar2_path = self.make_manifest(self.sat_bar_libc2)
                foo_path = self.make_manifest(self.sat_foo_libc)

                self.pkgdepend("resolve -o %s %s %s" %
                    (col_path, bar_path, foo_path), use_proto=False, exit=1)
                self.check_res("\n\n".join([col_path, bar_path, foo_path]),
                    self.output)
                self.check_res(self.run_path_errors %
                    {"unresolved_path": col_path}, self.errout)

                self.pkgdepend("resolve -o %s %s %s" %
                    (col_path, bar_path, bar2_path), use_proto=False, exit=1)
                self.check_res("\n\n".join([col_path, bar_path, bar2_path]),
                    self.output)
                self.check_res(self.amb_path_errors %
                    {"unresolved_path": col_path}, self.errout)
