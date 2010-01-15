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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import pkg.flavor.base as base
import pkg.flavor.depthlimitedmf as mf
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

        if "PYTHONPATH" in os.environ:
                py_path = [
                    os.path.normpath(fp)
                    for fp in os.environ["PYTHONPATH"].split(os.pathsep)
                ]
        else:
                py_path = []

        # Remove any paths that start with the defined python paths.
        new_path = sorted([
            fp
            for fp in sys.path
            if not mf.DepthLimitedModuleFinder.startswith_path(fp, py_path)
        ])

        @staticmethod
        def __make_paths(added, paths):
                return " ".join([
                    ("%(pfx)s.path=%(p)s/%(added)s" % {
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "p":p.lstrip("/"),
                        "added": added
                    }).rstrip("/")
                    for p in paths
                ])

        def make_res_manf_1(self, proto_area):
                return ("depend %(pfx)s.file=python "
                    "%(pfx)s.path=usr/bin fmri=%(dummy_fmri)s "
                    "type=require %(pfx)s.reason="
                    "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py "
                    "%(pfx)s.type=script\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=authlog "
                    "%(pfx)s.path=var/log "
                    "type=require %(pfx)s.reason=baz "
                    "%(pfx)s.type=hardlink\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=indexer.py "
                    "%(pfx)s.file=indexer.pyc "
                    "%(pfx)s.file=indexer.pyo "
                    "%(pfx)s.file=indexer/__init__.py " +
                    self.__make_paths("pkg",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason="
                    "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=pkg/__init__.py " +
                    self.__make_paths("",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason="
                    "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py "
                    "%(pfx)s.type=python type=require\n"
                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=search_storage.py "
                    "%(pfx)s.file=search_storage.pyc "
                    "%(pfx)s.file=search_storage.pyo "
                    "%(pfx)s.file=search_storage/__init__.py " +
                    self.__make_paths("pkg",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason="
                    "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=misc.py "
                    "%(pfx)s.file=misc.pyc "
                    "%(pfx)s.file=misc.pyo "
                    "%(pfx)s.file=misc/__init__.py " +
                    self.__make_paths("pkg",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason="
                    "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py "
                    "%(pfx)s.type=python type=require\n"

                    )  % {
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
                    }
        
        def make_full_res_manf_1(self, proto_area):
                return self.make_res_manf_1(proto_area) + self.test_manf_1

        err_manf_1 = """\
Couldn't find %s/usr/xpg4/lib/libcurses.so.1
"""
        res_manf_2 = """\
depend %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/xpg4/lib/libcurses.so.1 variant.arch=foo %(pfx)s.type=elf
""" % {"pfx":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_int_manf = """\
depend %(pfx)s.file=syslog %(pfx)s.path=var/log fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/foo %(pfx)s.type=hardlink
""" % {"pfx":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_manf_2_missing = "ascii text"

        resolve_error = """\
%(manf_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=usr/xpg4/lib/libcurses.so.1 %(pfx)s.type=elf type=require variant.arch=foo' under the following combinations of variants:
variant.arch:foo
"""

        test_manf_1_resolved = """\
depend fmri=%(py_pkg_name)s %(pfx)s.file=usr/bin/python %(pfx)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(pfx)s.type=script type=require
depend fmri=%(ips_pkg_name)s %(pfx)s.file=usr/lib/python2.6/vendor-packages/pkg/__init__.py %(pfx)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python type=require
depend fmri=%(ips_pkg_name)s %(pfx)s.file=usr/lib/python2.6/vendor-packages/pkg/indexer.py %(pfx)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python type=require
depend fmri=%(ips_pkg_name)s %(pfx)s.file=usr/lib/python2.6/vendor-packages/pkg/misc.py %(pfx)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python type=require
depend fmri=%(ips_pkg_name)s %(pfx)s.file=usr/lib/python2.6/vendor-packages/pkg/search_storage.py %(pfx)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python type=require
depend fmri=%(resolve_name)s %(pfx)s.file=var/log/authlog %(pfx)s.reason=baz %(pfx)s.type=hardlink type=require
depend fmri=%(csl_pkg_name)s %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=usr/xpg4/lib/libcurses.so.1 %(pfx)s.type=elf type=require
"""

        test_manf_1_full_resolved = test_manf_1_resolved + test_manf_1

        def make_full_res_manf_1_mod_proto(self, proto_area):
                return self.make_full_res_manf_1(proto_area) + \
                    """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=usr/xpg4/lib/libcurses.so.1 %(pfx)s.type=elf type=require
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}
        
        def make_res_payload_1(self, proto_area):
                return ("depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=misc.py "
                    "%(pfx)s.file=misc.pyc "
                    "%(pfx)s.file=misc.pyo "
                    "%(pfx)s.file=misc/__init__.py " +
                    self.__make_paths("pkg",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason=foo/bar.py "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=pkg/__init__.py " +
                    self.__make_paths("",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason=foo/bar.py "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=python "
                    "%(pfx)s.path=usr/bin "
                    "%(pfx)s.reason=foo/bar.py "
                    "%(pfx)s.type=script type=require\n"
                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=search_storage.py "
                    "%(pfx)s.file=search_storage.pyc "
                    "%(pfx)s.file=search_storage.pyo "
                    "%(pfx)s.file=search_storage/__init__.py " +
                    self.__make_paths("pkg",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason=foo/bar.py "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=indexer.py "
                    "%(pfx)s.file=indexer.pyc "
                    "%(pfx)s.file=indexer.pyo "
                    "%(pfx)s.file=indexer/__init__.py " +
                    self.__make_paths("pkg",
                        [proto_area + "/usr/bin"] + self.new_path) +
                    " %(pfx)s.reason=foo/bar.py "
                    "%(pfx)s.type=python type=require\n") % {
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
                    }

        res_payload_1_tmp = """\
depend fmri=__TBD pkg.debug.depend.file=misc.py pkg.debug.depend.file=misc.pyc pkg.debug.depend.file=misc.pyo pkg.debug.depend.file=misc/__init__.py pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/proto/root_i386/usr/bin/pkg pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/src/tests/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-dynload/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-old/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-tk/pkg pkg.debug.depend.path=usr/lib/python2.6/pkg pkg.debug.depend.path=usr/lib/python2.6/plat-sunos5/pkg pkg.debug.depend.path=usr/lib/python2.6/site-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gst-0.10/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/pkg pkg.debug.depend.path=usr/lib/python26.zip/pkg pkg.debug.depend.reason=foo/bar.py pkg.debug.depend.type=python type=require
depend fmri=__TBD pkg.debug.depend.file=pkg/__init__.py pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/proto/root_i386/usr/bin pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/src/tests pkg.debug.depend.path=usr/lib/python2.6 pkg.debug.depend.path=usr/lib/python2.6/lib-dynload pkg.debug.depend.path=usr/lib/python2.6/lib-old pkg.debug.depend.path=usr/lib/python2.6/lib-tk pkg.debug.depend.path=usr/lib/python2.6/plat-sunos5 pkg.debug.depend.path=usr/lib/python2.6/site-packages pkg.debug.depend.path=usr/lib/python2.6/vendor-packages pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gst-0.10 pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gtk-2.0 pkg.debug.depend.path=usr/lib/python26.zip pkg.debug.depend.reason=foo/bar.py pkg.debug.depend.type=python type=require
depend fmri=__TBD pkg.debug.depend.file=python pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=foo/bar.py pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=search_storage.py pkg.debug.depend.file=search_storage.pyc pkg.debug.depend.file=search_storage.pyo pkg.debug.depend.file=search_storage/__init__.py pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/proto/root_i386/usr/bin/pkg pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/src/tests/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-dynload/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-old/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-tk/pkg pkg.debug.depend.path=usr/lib/python2.6/pkg pkg.debug.depend.path=usr/lib/python2.6/plat-sunos5/pkg pkg.debug.depend.path=usr/lib/python2.6/site-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gst-0.10/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/pkg pkg.debug.depend.path=usr/lib/python26.zip/pkg pkg.debug.depend.reason=foo/bar.py pkg.debug.depend.type=python type=require
depend fmri=__TBD pkg.debug.depend.file=indexer.py pkg.debug.depend.file=indexer.pyc pkg.debug.depend.file=indexer.pyo pkg.debug.depend.file=indexer/__init__.py pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/proto/root_i386/usr/bin/pkg pkg.debug.depend.path=export/home/bpytlik/IPS/dep_tests/src/tests/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-dynload/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-old/pkg pkg.debug.depend.path=usr/lib/python2.6/lib-tk/pkg pkg.debug.depend.path=usr/lib/python2.6/pkg pkg.debug.depend.path=usr/lib/python2.6/plat-sunos5/pkg pkg.debug.depend.path=usr/lib/python2.6/site-packages/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gst-0.10/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/gtk-2.0/pkg pkg.debug.depend.path=usr/lib/python2.6/vendor-packages/pkg pkg.debug.depend.path=usr/lib/python26.zip/pkg pkg.debug.depend.reason=foo/bar.py pkg.debug.depend.type=python type=require
"""        
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
%(payload_path)s (which will be installed at %(installed_path)s) had this token, %(tok)s, in its run path: %(rp)s.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
"""

        payload_elf_sub_stdout = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1%(replaced_path)s %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=bar/foo %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI,
    "replaced_path":"%(replaced_path)s"
}

        kernel_manf_stdout = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=kernel %(pfx)s.path=usr/kernel %(pfx)s.reason=kernel/foobar %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        kernel_manf_stdout2 = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=baz %(pfx)s.path=foo/bar %(pfx)s.reason=kernel/foobar %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        kernel_manf_stdout_platform = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=libc.so.1 %(depend_debug_prefix)s.path=platform/baz/kernel %(depend_debug_prefix)s.path=platform/tp/kernel %(depend_debug_prefix)s.path=kernel %(depend_debug_prefix)s.path=usr/kernel %(depend_debug_prefix)s.reason=kernel/foobar %(depend_debug_prefix)s.type=elf type=require\
""" % {
    "depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        miss_payload_manf_error = """\
Couldn't find %(path_pref)s/tmp/file/should/not/exist/here/foo
"""

        double_plat_error = """\
%(image_dir)s/proto/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path: /platform/$PLATFORM/foo.  It is not currently possible to automatically expand this token. Please specify its value on the command line.
%(image_dir)s/proto/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path: /isadir/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line."""

        double_plat_stdout = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=bar/foo %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        double_plat_isa_error = """\
%(image_dir)s/proto/elf_test (which will be installed at bar/foo) had this token, $ISALIST, in its run path: /$ISALIST/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
"""

        double_plat_isa_stdout = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=platform/pfoo/foo %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=bar/foo %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        double_double_stdout = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=platform/pfoo/foo %(pfx)s.path=platform/pfoo2/foo %(pfx)s.path=isadir/pfoo/baz %(pfx)s.path=isadir/pfoo2/baz %(pfx)s.path=isadir/pfoo/baz %(pfx)s.path=isadir/pfoo2/baz %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=bar/foo %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        two_v_deps_resolve_error = """\
%(manf_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(pfx)s.file=var/log/authlog %(pfx)s.reason=baz %(pfx)s.type=hardlink type=require' under the following combinations of variants:
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
The file dependency depend fmri=%(dummy_fmri)s %(pfx)s.file=no_such_named_file %(pfx)s.path=platform/foo/baz %(pfx)s.path=platform/bar/baz %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=foo/bar %(pfx)s.type=elf type=require has paths which resolve to multiple packages. The actions are as follows:
	depend fmri=pkg:/sat_bar_libc %(pfx)s.file=platform/bar/baz/no_such_named_file %(pfx)s.reason=foo/bar %(pfx)s.type=elf type=require
	depend fmri=pkg:/sat_foo_libc %(pfx)s.file=platform/foo/baz/no_such_named_file %(pfx)s.reason=foo/bar %(pfx)s.type=elf type=require
%(unresolved_path)s has unresolved dependency 'depend fmri=__TBD %(pfx)s.file=no_such_named_file %(pfx)s.path=platform/foo/baz %(pfx)s.path=platform/bar/baz %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=foo/bar %(pfx)s.type=elf type=require' under the following combinations of variants:
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI,
    "unresolved_path":"%(unresolved_path)s"
}

        amb_path_errors = """\
The file dependency depend fmri=%(dummy_fmri)s %(pfx)s.file=no_such_named_file %(pfx)s.path=platform/foo/baz %(pfx)s.path=platform/bar/baz %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=foo/bar %(pfx)s.type=elf type=require depends on a path delivered by multiple packages. Those packages are:pkg:/sat_bar_libc2 pkg:/sat_bar_libc
%(unresolved_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(pfx)s.file=no_such_named_file %(pfx)s.path=platform/foo/baz %(pfx)s.path=platform/bar/baz %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=foo/bar %(pfx)s.type=elf type=require' under the following combinations of variants:
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI,
    "unresolved_path":"%(unresolved_path)s"
}

        python_text = """\
#!/usr/bin/python

import pkg.indexer as indexer
import pkg.search_storage as ss
from pkg.misc import EmptyI
"""

        p24_test_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py
"""

        p24_res_full_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py
depend %(pfx)s.file=usr/bin/python fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(pfx)s.type=script
depend %(pfx)s.file=usr/lib/python2.4/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python
depend %(pfx)s.file=usr/lib/python2.4/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python
depend %(pfx)s.file=usr/lib/python2.4/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python
depend %(pfx)s.file=usr/lib/python2.4/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(pfx)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(pfx)s.type=python
""" % {"pfx":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                self.image_create(self.dc.get_depot_url())
                self.manf_dirs = os.path.join(self.img_path, "manfs")
                os.makedirs(self.manf_dirs)
                self.proto_dir = os.path.join(self.img_path, "proto")
                os.makedirs(self.proto_dir)
        
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

        def make_elf(self, run_paths, o_path="elf_test"):
                t_fd, t_path = tempfile.mkstemp(suffix=".c", dir=self.proto_dir)
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write("int main(){}\n")
                t_fh.close()
                out_file = os.path.join(self.proto_dir, o_path)
                out_dir = os.path.dirname(out_file)
                if not os.path.exists(out_dir):
                        os.makedirs(out_dir)
                cmd = ["/usr/bin/cc", "-o", out_file]
                for rp in run_paths:
                        cmd.append("-R")
                        cmd.append(rp)
                cmd.append(t_path)
                s = subprocess.Popen(cmd, stderr=subprocess.PIPE)
                out, err = s.communicate()
                rc = s.returncode
                if rc != 0:
                        raise RuntimeError("Compile of %s failed. Runpaths "
                            "were %s\nCommand was:\n%s\nError was:\n%s" %
                            (t_path, " ".join(run_paths), " ".join(cmd), err))
                return out_file[len(self.img_path)+1:]

        def make_text_file(self, o_path, o_text=""):
                f_path = os.path.join(self.proto_dir, o_path)
                f_dir = os.path.dirname(f_path)
                if not os.path.exists(f_dir):
                        os.makedirs(f_dir)

                fh = open(f_path, "w")
                fh.write(o_text)
                fh.close()
                return f_path

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

                tp = self.make_manifest(self.test_manf_1)
                
                self.pkgdepend("generate %s" % tp, exit=1)
                self.check_res(self.make_res_manf_1(testutils.g_proto_area),
                    self.output)
                self.check_res(self.err_manf_1 % testutils.g_proto_area,
                    self.errout)

                self.pkgdepend("generate -m %s" % tp, exit=1)
                self.check_res(
                    self.make_full_res_manf_1(testutils.g_proto_area),
                    self.output)
                self.check_res(self.err_manf_1 % testutils.g_proto_area,
                    self.errout)

                self.make_text_file(
                    "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py",
                    self.python_text)
                self.make_elf([], "usr/xpg4/lib/libcurses.so.1")
                
                self.pkgdepend("generate -m %s" % tp, proto=self.proto_dir)
                self.check_res(
                    self.make_full_res_manf_1_mod_proto(testutils.g_proto_area),
                    self.output)
                self.check_res("", self.errout)

                tp = self.make_manifest(self.test_manf_2)
                self.make_text_file("etc/pam.conf", "text")
                
                self.pkgdepend("generate %s" % tp, proto=self.proto_dir)
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                res_path = self.make_manifest(self.output)

                self.pkgdepend("resolve -o %s" %
                    res_path, use_proto=False, exit=1)
                self.check_res("%s" % res_path, self.output)
                self.check_res(self.resolve_error % {
                        "manf_path": res_path,
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
                    }, self.errout)
                
                self.pkgdepend("generate -M %s" % tp, proto=self.proto_dir)
                self.check_res(self.res_manf_2, self.output)
                self.check_res(self.res_manf_2_missing, self.errout)

                portable.remove(tp)
                portable.remove(res_path)

                tp = self.make_manifest(self.int_hardlink_manf)

                self.make_text_file("var/log/syslog", "text")
                
                self.pkgdepend("generate %s" % tp, proto=self.proto_dir)
                self.check_res("", self.output)
                self.check_res("", self.errout)

                self.pkgdepend("generate -I %s" % tp, proto=self.proto_dir)
                self.check_res(self.res_int_manf, self.output)
                self.check_res("", self.errout)

                portable.remove(tp)

        def test_bug_11989(self):
                """These tests fail because they're resolved using a 2.6 based
                interpreter, instead of a 2.4 one."""

                tp = self.make_manifest(self.p24_test_manf_1)
                self.make_text_file("usr/lib/python2.4/vendor-packages/pkg/"
                    "client/indexer.py", self.python_text)
                self.make_elf([], "usr/xpg4/lib/libcurses.so.1")
                
                self.pkgdepend("generate -m %s" % tp, proto=self.proto_dir)
                self.check_res(self.p24_res_full_manf_1, self.output)
                self.check_res("ensure failure", self.errout)

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
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri": base.Dependency.DUMMY_FMRI
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
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
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
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
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
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
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
                        "pfx":
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
                self.check_res(self.make_res_payload_1(testutils.g_proto_area),
                    self.output)
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

                # Test for platform substitution in kernel module paths. Bug
                # 13057
                self.pkgdepend("generate -D PLATFORM=baz -D PLATFORM=tp %s %s" %
                    (m_path, self.img_path), use_proto=False)
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout_platform, self.output)
                
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
