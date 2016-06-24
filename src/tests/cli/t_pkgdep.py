#!/usr/bin/python2.7
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

# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import itertools
import os
import six
import subprocess
import sys
import unittest

import pkg.actions as actions
import pkg.flavor.base as base
import pkg.flavor.depthlimitedmf as mf
import pkg.misc as misc
import pkg.portable as portable
import pkg.publish.dependencies as dependencies

DDP = base.Dependency.DEPEND_DEBUG_PREFIX

if six.PY2:
        py_ver_default = "2.7"
        py_ver_other = "3.4"
else:
        py_ver_default = "3.4"
        py_ver_other = "2.7"

class TestPkgdepBasics(pkg5unittest.SingleDepotTestCase):

        test_manf_1 = """\
hardlink path=baz target=var/log/authlog
file group=bin mode=0755 owner=root \
path=usr/lib/python{0}/v\
endor-packages/pkg/client/indexer.py
file NOHA\
SH group=bin mode=0755 owner=root path=u\
sr/xpg4/lib/libcurses.so.1
""".format(py_ver_default)

        test_manf_2 = """\
set name=variant.arch value=foo value=bar
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=etc/pam.conf
"""

        test_elf_warning_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1
file group=bin mode=0755 owner=root path=etc/libc.so.1
"""

        test_bypass_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 pkg.depend.bypass-generate=lib/libc.so.1
"""

        test_64bit_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/bin/x64
"""

        int_hardlink_manf = """\
hardlink path=usr/foo target=../var/log/syslog
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""

        resolve_dep_manf = """\
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog preserve=true
"""

        payload_manf = """\
hardlink path=usr/baz target=lib/python{0}/foo/bar.py
file usr/lib/python{0}/vendor-packages/pkg/client/indexer.py \
group=bin mode=0755 owner=root path=usr/lib/python{0}/foo/bar.py
""".format(py_ver_default)

        elf_sub_manf = """\
file {file_loc} group=bin mode=0755 owner=root path=bar/foo
"""

        kernel_manf = """\
file {file_loc} group=bin mode=0755 owner=root path=kernel/foobar
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

        def get_ver_paths(self, ver, proto):
                """To determine what the correct results should be for several
                tests, it's necessary to discover what the sys.path is for the
                version of python the test uses."""

                cur_ver = "{0}.{1}".format(*sys.version_info[0:2])
                if cur_ver == ver:
                        # Remove any paths that start with the defined python
                        # paths.
                        res = sorted(set([
                            fp for fp in sys.path
                            if not mf.DepthLimitedModuleFinder.startswith_path(
                                fp, self.py_path)
                            ]))
                        return res

                sp = subprocess.Popen(
                    "python{0} -c 'import sys; print(sys.path)'".format(ver),
                    shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = sp.communicate()
                if err:
                        raise RuntimeError("Error running python{0}:{1}".format(
                            ver, err))
                # The first item in sys.path is empty when sys.path is examined
                # by running python via the -c option. When running an
                # executable python script, the first item is the directory
                # containing the script.
                return sorted(set([
                    fp for fp in eval(out)[1:]
                    if not mf.DepthLimitedModuleFinder.startswith_path(fp,
                        self.py_path)
                ]))

        @staticmethod
        def __make_paths(added, paths, install_path):
                """ Append a dependency path for "added" to each of
                the paths in the list "paths" """

                return " ".join([
                    ("{pfx}.path={p}/{added}".format(**{
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "p": p.lstrip("/"),
                        "added": added
                    })).rstrip("/")
                    for p in paths
                ] + [("{pfx}.path={p}/{added}".format(**{
                    "pfx":
                        base.Dependency.DEPEND_DEBUG_PREFIX,
                    "p": os.path.dirname(install_path),
                    "added": added,
                })).rstrip("/")])

        def make_res_manf_1(self, proto_area, reason, include_os=False):
                return ("depend {pfx}.file=python "
                    "{pfx}.path=usr/bin fmri={dummy_fmri} "
                    "type=require {pfx}.reason={reason} "
                    "{pfx}.type=script\n"

                    "depend fmri={dummy_fmri} "
                    "{pfx}.file=authlog "
                    "{pfx}.path=var/log "
                    "type=require {pfx}.reason=baz "
                    "{pfx}.type=hardlink\n" +
                    self.make_pyver_python_res(py_ver_default, proto_area,
                        reason, include_os=include_os)).format(
                    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
                    dummy_fmri=base.Dependency.DUMMY_FMRI,
                    reason=reason
               )

        def make_full_res_manf_1(self, proto_area, reason, include_os=False):
                return self.make_res_manf_1(proto_area, reason,
                    include_os=include_os) + self.test_manf_1

        err_manf_1 = """\
Couldn't find 'usr/xpg4/lib/libcurses.so.1' in any of the specified search directories:
	{0}
"""
        res_manf_2 = """\
depend {pfx}.file=libc.so.1 {pfx}.path=lib {pfx}.path=usr/lib fmri={dummy_fmri} type=require {pfx}.reason=usr/xpg4/lib/libcurses.so.1 variant.arch=foo {pfx}.type=elf
""".format(pfx=base.Dependency.DEPEND_DEBUG_PREFIX, dummy_fmri=base.Dependency.DUMMY_FMRI)

        res_int_manf = """\
depend {pfx}.file=syslog {pfx}.path=var/log fmri={dummy_fmri} type=require {pfx}.reason=usr/foo {pfx}.type=hardlink
""".format(pfx=base.Dependency.DEPEND_DEBUG_PREFIX, dummy_fmri=base.Dependency.DUMMY_FMRI)

        res_manf_2_missing = "ascii text"

        resolve_error = """\
{manf_path} has unresolved dependency '
    depend type=require fmri={dummy_fmri} {pfx}.file=libc.so.1 \\
        {pfx}.reason=usr/xpg4/lib/libcurses.so.1 \\
        {pfx}.type=elf \\
        {pfx}.path=lib \\
        {pfx}.path=usr/lib
' under the following combinations of variants:
variant.arch:foo
"""

        def make_full_res_manf_1_mod_proto(self, proto_area, reason,
            include_os=False):
                return self.make_full_res_manf_1(proto_area, reason,
                    include_os=include_os) + \
                    """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1 {pfx}.path=lib {pfx}.path=usr/lib {pfx}.reason=usr/xpg4/lib/libcurses.so.1 {pfx}.type=elf type=require
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        def make_res_payload_1(self, proto_area, reason):
                return ("depend fmri={dummy_fmri} "
                    "{pfx}.file=python "
                    "{pfx}.path=usr/bin "
                    "{pfx}.reason={reason} "
                    "{pfx}.type=script type=require\n" +
                    self.make_pyver_python_res(py_ver_default, proto_area, reason)).format(**{
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI,
                        "reason": reason
                    })

        two_variant_deps = """\
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
"""

        two_v_deps_bar = """
set name=pkg.fmri value=pkg:/s-v-bar
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=bar
file NOHASH group=sys mode=0600 owner=root path=var/log/file2
"""

        two_v_deps_baz_one = """
set name=pkg.fmri value=pkg:/s-v-baz-one
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz variant.num=one
"""

        two_v_deps_baz_two = """
set name=pkg.fmri value=pkg:/s-v-baz-two
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog variant.foo=baz variant.num=two
"""

        two_v_deps_verbose_output = """\
# {m1_path}
depend fmri=pkg:/s-v-bar pkg.debug.depend.file=var/log/authlog pkg.debug.depend.file=var/log/file2 pkg.debug.depend.path-id=var/log/authlog pkg.debug.depend.path-id=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/s-v-baz-one pkg.debug.depend.file=var/log/authlog pkg.debug.depend.path-id=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two pkg.debug.depend.file=var/log/authlog pkg.debug.depend.path-id=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=two


# {m2_path}



# {m3_path}



# {m4_path}
"""

        two_v_deps_output = """\
# {m1_path}
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=three value=two
depend fmri=pkg:/s-v-bar type=require
depend fmri=pkg:/s-v-baz-one type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two type=require variant.foo=baz variant.num=two


# {m2_path}
{m2_fmt}


# {m3_path}
{m3_fmt}


# {m4_path}
{m4_fmt}
"""

        dup_variant_deps = """\
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two
depend fmri=pkg:/s-v-bar type=require
depend fmri=pkg:/s-v-bar@0.1-0.2 type=incorporate
depend fmri=pkg:/hand-dep type=require
depend fmri=pkg:/hand-dep@0.1-0.2 type=incorporate
depend fmri=__TBD pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/f1 pkg.debug.depend.reason=b1 pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/f2 pkg.debug.depend.reason=b2 pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/f3 pkg.debug.depend.reason=b3 pkg.debug.depend.type=hardlink type=require variant.foo=bar
depend fmri=__TBD pkg.debug.depend.file=var/log/f4 pkg.debug.depend.reason=b3 pkg.debug.depend.type=hardlink type=require variant.foo=baz
depend fmri=__TBD pkg.debug.depend.file=var/log/f5 pkg.debug.depend.reason=b5 pkg.debug.depend.type=hardlink type=require
depend fmri=__TBD pkg.debug.depend.file=var/log/f6 pkg.debug.depend.reason=b5 pkg.debug.depend.type=hardlink type=require variant.foo=bar
"""

        dup_prov = """
set name=pkg.fmri value=pkg:/dup-prov
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/f1
file NOHASH group=sys mode=0600 owner=root path=var/log/f2
"""

        subset_prov = """
set name=pkg.fmri value=pkg:/subset-prov
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/f5
file NOHASH group=sys mode=0600 owner=root path=var/log/f6
"""

        sep_vars = """
set name=pkg.fmri value=pkg:/sep_vars
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/f3 variant.foo=bar
file NOHASH group=sys mode=0600 owner=root path=var/log/f4 variant.foo=baz
"""

        dup_variant_deps_resolved = """\
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two
depend fmri=pkg:/hand-dep type=require
depend fmri=pkg:/s-v-bar@0.1-0.2 type=incorporate
depend fmri=pkg:/hand-dep@0.1-0.2 type=incorporate
depend fmri=pkg:/dup-prov pkg.debug.depend.file=var/log/f2 pkg.debug.depend.file=var/log/f1 pkg.debug.depend.path-id=var/log/f1 pkg.debug.depend.path-id=var/log/f2 pkg.debug.depend.reason=b1 pkg.debug.depend.reason=b2 pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/s-v-bar pkg.debug.depend.file=var/log/authlog pkg.debug.depend.file=var/log/file2 pkg.debug.depend.path-id=var/log/authlog pkg.debug.depend.path-id=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/s-v-baz-one pkg.debug.depend.file=var/log/authlog pkg.debug.depend.path-id=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two pkg.debug.depend.file=var/log/authlog pkg.debug.depend.path-id=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=two
depend fmri=pkg:/sep_vars pkg.debug.depend.file=var/log/f3 pkg.debug.depend.file=var/log/f4 pkg.debug.depend.path-id=var/log/f3 pkg.debug.depend.path-id=var/log/f4 pkg.debug.depend.reason=b3 pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/subset-prov pkg.debug.depend.file=var/log/f6 pkg.debug.depend.file=var/log/f5 pkg.debug.depend.path-id=var/log/f5 pkg.debug.depend.path-id=var/log/f6 pkg.debug.depend.reason=b5 pkg.debug.depend.type=hardlink type=require
"""

        payload_elf_sub_error = """\
{payload_path} (which will be installed at {installed_path}) had this token, {tok}, in its run path: {rp}.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
"""

        payload_elf_sub_stdout = """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1{replaced_path} {pfx}.path=lib {pfx}.path=usr/lib {pfx}.reason=bar/foo {pfx}.type=elf type=require\
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI,
    replaced_path="{replaced_path}"
)

        #
        # You may wonder why libc.so.1 is here as a dependency-- it's an
        # artifact of the way we compile our dummy module, and serves as
        # a "something to depend on".  In this way, the sample elf file
        # depends on libc.so.1 in the same way that a kernel module might
        # depend on another kernel module.
        #
        kernel_manf_stdout = """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1 {pfx}.path=kernel {pfx}.path=usr/kernel {pfx}.reason=kernel/foobar {pfx}.type=elf type=require\
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        kernel_manf_stdout2 = """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1 {pfx}.path=baz {pfx}.path=foo/bar {pfx}.reason=kernel/foobar {pfx}.type=elf type=require\
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        kernel_manf_stdout_platform = """\
depend fmri={dummy_fmri} {depend_debug_prefix}.file=libc.so.1 {depend_debug_prefix}.path=platform/baz/kernel {depend_debug_prefix}.path=platform/tp/kernel {depend_debug_prefix}.path=kernel {depend_debug_prefix}.path=usr/kernel {depend_debug_prefix}.reason=kernel/foobar {depend_debug_prefix}.type=elf type=require\
""".format(
    depend_debug_prefix=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        miss_payload_manf_error = """\
Couldn't find 'foo/bar.py' in any of the specified search directories:
	{path_pref}
"""

        double_plat_error = """\
{proto_dir}/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path: /platform/$PLATFORM/foo.  It is not currently possible to automatically expand this token. Please specify its value on the command line.
{proto_dir}/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path: /isadir/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line."""

        double_plat_stdout = """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1 {pfx}.path=lib {pfx}.path=usr/lib {pfx}.reason=bar/foo {pfx}.type=elf type=require\
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        double_plat_isa_error = """\
{proto_dir}/elf_test (which will be installed at bar/foo) had this token, $ISALIST, in its run path: /$ISALIST/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
"""

        double_plat_isa_stdout = """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1 {pfx}.path=platform/pfoo/foo {pfx}.path=lib {pfx}.path=usr/lib {pfx}.reason=bar/foo {pfx}.type=elf type=require\
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        double_double_stdout = """\
depend fmri={dummy_fmri} {pfx}.file=libc.so.1 {pfx}.path=platform/pfoo/foo {pfx}.path=platform/pfoo2/foo {pfx}.path=isadir/pfoo/baz {pfx}.path=isadir/pfoo2/baz {pfx}.path=isadir/pfoo/baz {pfx}.path=isadir/pfoo2/baz {pfx}.path=lib {pfx}.path=usr/lib {pfx}.reason=bar/foo {pfx}.type=elf type=require\
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI
)

        two_v_deps_resolve_error = """\
{manf_path} has unresolved dependency '
    depend type=require fmri={dummy_fmri} {pfx}.file=var/log/authlog \\
        {pfx}.reason=baz {pfx}.type=hardlink
' under the following combinations of variants:
variant.foo:baz variant.num:three
"""
        usage_msg = """\
Usage:
        pkgdepend [options] command [cmd_options] [operands]

Subcommands:
        pkgdepend generate [-IMm] -d dir [-d dir] [-D name=value] [-k path]
            manifest_file
        pkgdepend resolve [-EmoSv] [-d output_dir]
            [-e external_package_file]... [-s suffix] manifest_file ...

Options:
        -R dir
        --help or -?
Environment:
        PKG_IMAGE"""

        collision_manf = """\
set name=pkg.fmri value=pkg:/collision_manf
depend fmri=__TBD pkg.debug.depend.file=no_such_named_file pkg.debug.depend.path=platform/foo/baz pkg.debug.depend.path=platform/bar/baz pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require\
"""

        sat_bar_libc = """\
set name=pkg.fmri value=pkg:/sat_bar_libc
file NOHASH path=platform/bar/baz/no_such_named_file
"""

        sat_bar_libc2 = """\
set name=pkg.fmri value=pkg:/sat_bar_libc2
file NOHASH path=platform/bar/baz/no_such_named_file
"""

        sat_foo_libc = """\
set name=pkg.fmri value=pkg:/sat_foo_libc
file NOHASH path=platform/foo/baz/no_such_named_file
"""

        run_path_errors = """\
The file dependency depend fmri={dummy_fmri} {pfx}.file=no_such_named_file {pfx}.path=platform/foo/baz {pfx}.path=platform/bar/baz {pfx}.path=lib {pfx}.path=usr/lib {pfx}.reason=foo/bar {pfx}.type=elf type=require delivered in pkg:/collision_manf has paths which resolve to multiple packages.
The actions are:
	depend fmri=pkg:/sat_bar_libc {pfx}.file=platform/bar/baz/no_such_named_file {pfx}.reason=foo/bar {pfx}.type=elf type=require
	depend fmri=pkg:/sat_foo_libc {pfx}.file=platform/foo/baz/no_such_named_file {pfx}.reason=foo/bar {pfx}.type=elf type=require
{unresolved_path} has unresolved dependency '
    depend type=require fmri=__TBD {pfx}.file=no_such_named_file \\
        {pfx}.reason=foo/bar {pfx}.type=elf \\
        {pfx}.path=lib \\
        {pfx}.path=platform/bar/baz \\
        {pfx}.path=platform/foo/baz \\
        {pfx}.path=usr/lib'.
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI,
    unresolved_path="{unresolved_path}"
)

        amb_path_errors = """\
The file dependency
    depend type=require fmri={dummy_fmri} {pfx}.file=no_such_named_file \\
        {pfx}.reason=foo/bar {pfx}.type=elf \\
        {pfx}.path=platform/foo/baz \\
        {pfx}.path=platform/bar/baz \\
        {pfx}.path=lib \\
        {pfx}.path=usr/lib
depends on a path delivered by multiple packages. Those packages are:pkg:/sat_bar_libc2 pkg:/sat_bar_libc
{unresolved_path} has unresolved dependency '
    depend type=require fmri={dummy_fmri} {pfx}.file=no_such_named_file \\
        {pfx}.reason=foo/bar {pfx}.type=elf \\
        {pfx}.path=lib \\
        {pfx}.path=platform/foo/baz \\
        {pfx}.path=platform/bar/baz \\
        {pfx}.path=usr/lib'.
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI,
    unresolved_path="{unresolved_path}"
)

        python_text = """\
#!/usr/bin/python

import pkg.indexer as indexer
import pkg.search_storage as ss
from pkg.misc import EmptyI
"""

        python3_so_text = """\
#!/usr/bin/python3.4

import zlib
"""

        python_amd_text = """\
#!/usr/bin/amd64/python{0}

import pkg.indexer as indexer
""".format(py_ver_default)

        python_amd_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/bin/amd64/python{0}-config
""".format(py_ver_default)

        python_sparcv9_text = """\
#!/usr/bin/sparcv9/python{0}

from pkg.misc import EmptyI
""".format(py_ver_default)

        python_sparcv9_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/bin/sparcv9/python{0}-config
""".format(py_ver_default)

        py_in_usr_bin_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/bin/pkg \
"""

        py_in_usr_bin_manf_non_ex = """\
file NOHASH group=bin mode=0644 owner=root path=usr/bin/pkg \
"""

        # The #! line has lots of spaces to test for bug 14632.
        pyver_python_text = "#!                  /usr/bin/python{0}     -S  " + \
"""
import pkg.indexer as indexer
import pkg.search_storage as ss
import os.path
from pkg.misc import EmptyI
"""

        pyver_test_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/client/indexer.py \
"""

        pyver_test_manf_1_run_path = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/client/indexer.py pkg.depend.runpath=$PKGDEPEND_RUNPATH \
"""

        pyver_test_manf_1_non_ex = """\
file NOHASH group=bin mode=0644 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/client/indexer.py \
"""

        inst_pkg = """\
open example2_pkg@1.0,5.11-0
add file tmp/foo mode=0555 owner=root group=bin path=/usr/bin/python{0}
close""".format(py_ver_default)

        multi_deps = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python{0}/v-p/pkg/client/indexer.py
depend fmri=__TBD pkg.debug.depend.file=usr/bin/python{0} pkg.debug.depend.reason=usr/lib/python{0}/v-p/pkg/client/indexer.py pkg.debug.depend.type=script type=require
depend fmri=__TBD pkg.debug.depend.file=usr/lib/python{0}/v-p/pkg/misc.py pkg.debug.depend.reason=usr/lib/python{0}/v-p/pkg/client/indexer.py pkg.debug.depend.type=python type=require
""".format(py_ver_default)

        misc_manf = """\
set name=pkg.fmri value=pkg:/footest@0.5.11,5.11-0.117
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{0}/v-p/pkg/misc.py
""".format(py_ver_default)

        unsatisfied_manf = """\
set name=pkg.fmri value=pkg:/unsatisfied_manf
set name=variant.foo value=bar
depend fmri=__TBD pkg.debug.depend.file=unsatisfied pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require
"""

        unsatisfied_error_1 = """\
{0} has unresolved dependency '
    depend type=require fmri=__TBD pkg.debug.depend.file=unsatisfied \\
        pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=foo/bar \\
        pkg.debug.depend.type=elf'.
"""

        unsatisfied_error_2 = """\
{0} has unresolved dependency '
    depend  type=require fmri=__TBD pkg.debug.depend.file=unsatisfied \\
        pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=foo/bar \\
        pkg.debug.depend.type=elf
' under the following combinations of variants:
variant.foo:bar
"""

        partially_satisfied_manf = """\
set name=pkg.fmri value=pkg:/partially_satisfied_manf
set name=variant.foo value=bar value=baz
depend fmri=__TBD pkg.debug.depend.file=unsatisfied pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=foo/bar pkg.debug.depend.type=elf type=require
"""

        satisfying_manf = """\
set name=pkg.fmri value=pkg:/satisfying_manf
set name=variant.foo value=baz
file NOHASH path=usr/bin/unsatisfied owner=root group=staff mode=0555
"""

        satisfying_out = """\
depend fmri=pkg:/satisfying_manf type=require variant.foo=baz
"""

        def make_pyver_python_res(self, ver, proto_area, reason,
            include_os=False):
                """Create the python dependency results with paths expected for
                the pyver tests.

                Because the paths that should be found depend both on the
                version of python and what is found by the site module, it's
                necessary to make the results depend on the sys.path that's
                discovered.
                """

                v3 = ver.startswith("3.") and "34m"

                vp = self.get_ver_paths(ver, proto_area)
                self.debug("ver_paths is {0}".format(vp))
                pkg_path = self.__make_paths("pkg", vp, reason)
                res = ("depend fmri={dummy_fmri} "
                    "{pfx}.file=indexer.py "
                    "{pfx}.file=indexer.pyc "
                    "{pfx}.file=indexer.pyo "
                    "{pfx}.file=64/indexer.so "
                    "{pfx}.file=indexer.so "
                    "{pfx}.file=indexer/__init__.py " +
                    (v3 and
                        "{pfx}.file=indexer.abi3.so "
                        "{pfx}.file=indexer.cpython-{v3}.so "
                        "{pfx}.file=64/indexer.abi3.so "
                        "{pfx}.file=64/indexer.cpython-{v3}.so "
                        or
                        "{pfx}.file=indexermodule.so "
                        "{pfx}.file=64/indexermodule.so ") +
                    pkg_path +
                    " {pfx}.reason={reason} "
                    "{pfx}.type=python type=require\n"

                    "depend fmri={dummy_fmri} "
                    "{pfx}.file=misc.py "
                    "{pfx}.file=misc.pyc "
                    "{pfx}.file=misc.pyo "
                    "{pfx}.file=misc.so "
                    "{pfx}.file=64/misc.so "
                    "{pfx}.file=misc/__init__.py " +
                    (v3 and
                        "{pfx}.file=misc.abi3.so "
                        "{pfx}.file=misc.cpython-{v3}.so "
                        "{pfx}.file=64/misc.abi3.so "
                        "{pfx}.file=64/misc.cpython-{v3}.so "
                        or
                        "{pfx}.file=64/miscmodule.so "
                        "{pfx}.file=miscmodule.so ") +
                    pkg_path +
                    " {pfx}.reason={reason} "
                    "{pfx}.type=python type=require\n"

                    "depend fmri={dummy_fmri} "
                    "{pfx}.file=pkg/__init__.py " +
                    self.__make_paths("", vp, reason) +
                    " {pfx}.reason={reason} "
                    "{pfx}.type=python type=require\n"

                    "depend fmri={dummy_fmri} "
                    "{pfx}.file=search_storage.py "
                    "{pfx}.file=search_storage.pyc "
                    "{pfx}.file=search_storage.pyo "
                    "{pfx}.file=64/search_storage.so "
                    "{pfx}.file=search_storage.so "
                    "{pfx}.file=search_storage/__init__.py " +
                    (v3 and
                        "{pfx}.file=search_storage.abi3.so "
                        "{pfx}.file=search_storage.cpython-{v3}.so "
                        "{pfx}.file=64/search_storage.abi3.so "
                        "{pfx}.file=64/search_storage.cpython-{v3}.so "
                        or
                        "{pfx}.file=64/search_storagemodule.so "
                        "{pfx}.file=search_storagemodule.so ") +
                    pkg_path +
                    " {pfx}.reason={reason} "
                    "{pfx}.type=python type=require\n")

                if include_os:
                        res += (
                            "depend fmri={dummy_fmri} "
                            "{pfx}.file=os.py "
                            "{pfx}.file=os.pyc "
                            "{pfx}.file=os.pyo "
                            "{pfx}.file=os.so "
                            "{pfx}.file=64/os.so "
                            "{pfx}.file=os/__init__.py " +
                            (v3 and
                                "{pfx}.file=os.abi3.so "
                                "{pfx}.file=os.cpython-{v3}.so "
                                "{pfx}.file=64/os.abi3.so "
                                "{pfx}.file=64/os.cpython-{v3}.so "
                                or
                                "{pfx}.file=64/osmodule.so "
                                "{pfx}.file=osmodule.so ") +
                            self.__make_paths("", vp, reason) +
                            " {pfx}.reason={reason} "
                            "{pfx}.type=python type=require\n")
                return res.format(
                    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
                    dummy_fmri=base.Dependency.DUMMY_FMRI,
                    reason=reason, v3=v3
                )

        pyver_other_script_full_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path={reason} {run_path}
depend fmri={dummy_fmri} {pfx}.file=python{bin_ver} {pfx}.path=usr/bin {pfx}.reason={reason} {pfx}.type=script type=require
""".format(
    pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
    dummy_fmri=base.Dependency.DUMMY_FMRI,
    reason="{reason}",
    bin_ver="{bin_ver}",
    run_path="{run_path}"
)

        def pyver_res_full_manf_1(self, ver, proto, reason, include_os=False):
                """Build the full manifest results for the pyver tests."""

                if ver == py_ver_other:
                        tmp = self.pyver_other_script_full_manf_1
                else:
                        raise RuntimeError("Unexpected version for "
                            "pyver_res_full_manf_1 {0}".format(ver))
                return tmp + self.make_pyver_python_res(ver, proto, reason,
                    include_os=include_os)

        if six.PY2:
                # in this case, py_ver_default = "2.7", py_ver_other = "3.4"
                pyver_resolve_dep_manf = """
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/indexer.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/__init__.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/lib-dynload/64/pkg/search_storage.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/misc.py
file NOHASH group=bin mode=0755 owner=root path=usr/bin/python
"""
        else:
                # py_ver_default = "3.4", py_ver_other = "2.7"
                pyver_resolve_dep_manf = """
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/indexer.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/__init__.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/lib-tk/pkg/search_storage.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python{py_ver}/vendor-packages/pkg/misc.py
file NOHASH group=bin mode=0755 owner=root path=usr/bin/python
"""

        def make_pyver_resolve_results(self, proto_area):
                """Generate the expected results when resolving a manifest which
                contains a file with a non-default version of python."""

                v3 = py_ver_other.startswith("3.") and "34m"
                patterns = (
                    "{0}.py", "{0}.pyc", "{0}.pyo",
                    "{0}.so", "64/{0}.so",
                    "{0}/__init__.py"
                )
                if v3:
                        patterns += (
                            "{0}.abi3.so", "{0}.cpython-{v3}.so",
                            "64/{0}.abi3.so", "64/{0}.cpython-{v3}.so",
                        )
                else:
                        patterns += ("{0}module.so", "64/{0}module.so")

                files = ["indexer", "misc", "search_storage"]

                # These are the paths to the files which the package depends on.
                # __init__ isn't part of files because it's not in the path-id.
                # search_storage.py is handled separately because it's delivered
                # in a different location than the other files, so it needs a
                # different path attached to it.
                rel_paths = [
                    "usr/lib/python{py_ver}/vendor-packages/pkg/" + f + ".py"
                    for f in files + ["__init__"] if f != "search_storage"
                ]

                if six.PY2:
                        rel_paths += ["usr/bin/python",
                            "usr/lib/python{py_ver}/lib-dynload/64/pkg/search_storage.py"]
                else:
                        rel_paths += ["usr/bin/python",
                            "usr/lib/python{py_ver}/lib-tk/pkg/search_storage.py"]

                # Find the potential locations an imported python module might
                # be found.
                vps = self.get_ver_paths(py_ver_other, proto_area) + \
                    ["usr/lib/python{0}/vendor-packages/pkg/client".format(py_ver_other)]
                vps = [vp.lstrip("/") + "/pkg/" for vp in vps]

                # Produce the expected dependency.  The package name will be
                # filled in by the caller of this function.  The pdd.file
                # attributes are taken from rel_paths.  Path-id is an pkgdepend
                # internal attribute which allows it to know which dependencies
                # where merged together to form a particular final dependency.
                # The __init__.py file follows a different pattern than the
                # other files, so it's handled separately.
                return "depend fmri=pkg:/{res_manf} " + \
                    " ".join(["{pfx}.file=" + rp for rp in rel_paths]) + \
                    " " + " ".join(["{pfx}.path-id=" + ":".join(sorted([
                        proto_str + pat.format(f, v3=v3)
                        for proto_str in vps
                        for pat in patterns
                        ]))
                        for f in files
                    ]) + " {pfx}.path-id=" + ":".join(sorted(
                        [vp + "__init__.py" for vp in vps])) + \
                    " {pfx}.path-id=usr/bin/python " + \
                    "{pfx}.reason=usr/lib/python{py_ver}/" + \
                    "vendor-packages/pkg/client/indexer.py " + \
                    "{pfx}.type=script {pfx}.type=python type=require"

        pyver_mismatch_results = """\
depend fmri={dummy_fmri} {pfx}.file=python{default} {pfx}.path=usr/bin {pfx}.reason=usr/lib/python{other}/vendor-packages/pkg/client/indexer.py {pfx}.type=script type=require
""".format(default=py_ver_default, other=py_ver_other, pfx=base.Dependency.DEPEND_DEBUG_PREFIX, dummy_fmri=base.Dependency.DUMMY_FMRI)

        pyver_mismatch_errs = """
The file to be installed at usr/lib/python{0}/vendor-packages/pkg/client/indexer.py declares a python version of {1}.  However, the path suggests that the version should be {0}.  The text of the file can be found at {{0}}/usr/lib/python{0}/vendor-packages/pkg/client/indexer.py
""".format(py_ver_other, py_ver_default)

        pyver_unspecified_ver_err = """
The file to be installed in usr/bin/pkg does not specify a specific version of python either in its installed path nor in its text.  Such a file cannot be analyzed for dependencies since the version of python it will be used with is unknown.  The text of the file is here: {0}/usr/bin/pkg.
"""

        bug_16808_manf = """\
file NOHASH group=bin mode=0755 owner=root path=var/log/syslog variant.opensolaris.zone=global
hardlink path=var/log/foobar target=syslog
"""

        bug_15958_manf = """\
set name=variant.opensolaris.zone value=global value=nonglobal
""" + bug_16808_manf

        res_bug_15958 = """\
depend fmri=__TBD pkg.debug.depend.file=syslog pkg.debug.depend.path=var/log pkg.debug.depend.reason=var/log/foobar pkg.debug.depend.type=hardlink type=require variant.opensolaris.zone=nonglobal
"""

        bug_16808_error = """\
The action delivering var/log/syslog is tagged with a variant type or value not tagged on the package. Dependencies on this file may fail to be reported.
The action's variants are: variant.opensolaris.zone="global"
The package's variants are: <none>
"""

        res_elf_warning = """\
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.reason=usr/xpg4/lib/libcurses.so.1 pkg.debug.depend.severity=warning pkg.debug.depend.type=elf type=require
"""

        res_bypass = """\
depend fmri=__TBD pkg.debug.depend.fullpath=usr/lib/libc.so.1 pkg.debug.depend.reason=usr/xpg4/lib/libcurses.so.1 pkg.debug.depend.type=elf type=require
set name=pkg.debug.depend.bypassed value=lib/libc.so.1
"""

        bug_16013_simple_a_dep_manf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.151
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require
"""
        bug_16013_simple_b_dep_manf = """\
set name=pkg.fmri value=pkg:/b@0.5.11,5.11-0.151
link path=usr/bin target=/b/bin
dir group=bin mode=0755 owner=root path=b/bin
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl
"""

        bug_16013_simple_b_link_manf = """\
set name=pkg.fmri value=pkg:/b_link@0.5.11,5.11-0.151
link path=usr target=/b
"""

        bug_16013_simple_b_link2_manf = """\
set name=pkg.fmri value=pkg:/b_link2@0.5.11,5.11-0.151
dir group=bin mode=0755 owner=root path=b
link path=b/bin target=/b2/bin
"""

        bug_16013_simple_b_file_manf = """\
set name=pkg.fmri value=pkg:/b_file@0.5.11,5.11-0.151
dir group=bin mode=0755 owner=root path=b2/bin
file NOHASH group=bin mode=0555 owner=root path=b2/bin/perl
"""

        bug_16013_var_a_dep_manf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.151
set name=variant.foo value=b value=c value=a
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require
"""

        bug_16013_var_b_link_manf = """\
set name=pkg.fmri value=pkg:/b_link@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
link path=usr/bin target=/b/bin variant.foo=b
dir group=bin mode=0755 owner=root path=b/bin variant.foo=b
"""

        bug_16013_var_b_file_manf = """\
set name=pkg.fmri value=pkg:/b_file@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b
"""

        bug_16013_var_c_manf = """\
set name=pkg.fmri value=pkg:/c@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
link path=usr/bin target=../c/bin variant.foo=c
dir group=bin mode=0755 owner=root path=c/bin variant.foo=c
file NOHASH group=bin mode=0555 owner=root path=c/bin/perl variant.foo=c
"""

        def bug_16013_check_res_variants_base(self, deps, errs, a_pth):
                """A common method used by tests for verifying correct
                dependency resolution when links are traversed and variants are
                taken into account."""

                self.assertEqual(len(errs), 1,
                    "\n\n".join([str(s) for s in errs]))
                e = errs[0]
                self.assertEqual(e.path, a_pth)
                self.assertEqual(
                    e.file_dep.attrs[dependencies.files_prefix], "perl")
                self.assertEqual(e.pvars.not_sat_set,
                    set([frozenset([("variant.foo", "a")])]))
                self.assertEqual(len(deps[a_pth]), 3,
                    "\n".join([str(s) for s in deps[a_pth]]))
                res_fmris = set(["pkg:/b_link@0.5.11-0.151",
                    "pkg:/c@0.5.11-0.151", "pkg:/b_file@0.5.11-0.151"])
                for d in deps[a_pth]:
                        self.assertTrue(d.attrs["fmri"] in res_fmris,
                            "Unexpected fmri for:{0}".format(d))
                        res_fmris.remove(d.attrs["fmri"])
                        if d.attrs["fmri"] == \
                            "pkg:/b_link@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "link")
                                self.assertEqual(d.attrs["variant.foo"],
                                    "b")
                        elif d.attrs["fmri"] == \
                            "pkg:/b_file@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "script")
                                self.assertEqual(d.attrs["variant.foo"],
                                    "b")
                        else:
                                self.assertEqual(d.attrs["variant.foo"],
                                    "c")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "script")

        def bug_16013_check_res_simple_links(self, deps, errs, a_pth):
                """A common method used by tests for verifying correct
                dependency resolution when links are traversed."""

                self.assertEqual(len(errs), 0,
                    "\n".join([str(s) for s in errs]))
                self.assertEqual(len(deps[a_pth]), 3,
                    "\n".join([str(s) for s in deps[a_pth]]))
                res_fmris = set(["pkg:/b_link@0.5.11-0.151",
                    "pkg:/b_link2@0.5.11-0.151",
                    "pkg:/b_file@0.5.11-0.151"])
                for d in deps[a_pth]:
                        self.assertTrue(d.attrs["fmri"] in res_fmris,
                            "Unexpected fmri for:{0}".format(d))
                        res_fmris.remove(d.attrs["fmri"])
                        if d.attrs["fmri"] in \
                            ("pkg:/b_link@0.5.11-0.151",
                            "pkg:/b_link2@0.5.11-0.151"):
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "link")
                        else:
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "script",
                                    "Was expecting type=script, " +
                                    "d:{0}".format(d))

        def bug_16013_check_res_var_files_links_deps(self, deps, errs, a_pth):
                """A common method used by tests for verifying correct
                dependency resolution when links are traversed and variants are
                present on both files and the links needed to reach those files.
                """

                self.assertEqual(len(errs), 1,
                    "\n\n".join([str(s) for s in errs]))
                e = errs[0]
                self.assertEqual(e.path, a_pth)
                self.assertEqual(
                    e.file_dep.attrs[dependencies.files_prefix], "perl")
                self.assertEqual(e.pvars.not_sat_set,
                    set([frozenset([("variant.foo", "a")])]))
                self.assertEqual(len(deps[a_pth]), 3,
                    "\n".join([str(s) for s in deps[a_pth]]))
                res_fmris = set(["pkg:/b_link@0.5.11-0.151",
                    "pkg:/c@0.5.11-0.151", "pkg:/b_file@0.5.11-0.151"])
                for d in deps[a_pth]:
                        self.assertTrue(d.attrs["fmri"] in res_fmris,
                            "Unexpected fmri for:{0}".format(d))
                        res_fmris.remove(d.attrs["fmri"])
                        if d.attrs["fmri"] == \
                            "pkg:/b_link@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "link")
                                self.assertEqual(d.attrs["variant.foo"],
                                    "b")
                        elif d.attrs["fmri"] == \
                            "pkg:/b_file@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "script")
                                self.assertEqual(d.attrs["variant.foo"],
                                    "b")
                        else:
                                self.assertEqual(d.attrs["variant.foo"],
                                    "c")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "script")


        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.rurl1 = self.dcs[1].get_repo_url()
                #
                # To test pkgdepend resolve properly, we need an image.
                # Side by side with the image, we create a testing proto area.
                #
                self.pkg_image_create(self.rurl)

                self.test_proto_dir = os.path.join(self.test_root, "proto")
                os.makedirs(self.test_proto_dir)

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
                fh = open(file_path, "r")
                lines = fh.read()
                fh.close()
                return lines

        def make_proto_text_file(self, path, contents=""):
                #
                # We add a newline if it is missing because file(1) is sensitive
                # to files which lack them.
                #
                contents = contents + "\n"
                self.make_misc_files({ path: contents }, prefix="proto")

        def make_elf(self, run_paths=[], output_path="elf_test", bit64=False,
            deferred_libs=misc.EmptyI, filter_files=misc.EmptyI,
            lazy_libs=misc.EmptyI, mapfile=None, no_link=False, obj_files=None,
            optional_filters=misc.EmptyI, program_text=None, shared_lib=False,
            record_audit=False):
                assert obj_files is None or program_text is None
                if obj_files is None and program_text is None:
                        program_text = "int main(){}\n"
                out_file = os.path.join(self.test_proto_dir, output_path)

                # Make sure to quote the runpaths, as they may contain tokens
                # like $PLATFORM which we do not want the shell to evaluate.
                opts = ["-R'{0}'".format(rp) for rp in run_paths]
                if bit64:
                        opts.append("-m64")
                if shared_lib:
                        # Always link to libc; the compiler may not.
                        opts.append("-lc")
                        opts.append("-G")
                if no_link:
                        opts.append("-c")
                if mapfile:
                        opts.append("-M{0}".format(mapfile))
                if record_audit:
                        opts.append("-Wl,-paudit.so.1")

                opts.extend(["-F{0}".format(f) for f in filter_files])
                opts.extend(["-f{0}".format(f) for f in optional_filters])
                opts.extend(["-z deferred"] +  list(deferred_libs) +
                    ["-z nodeferred"])
                opts.extend(["-z lazyload {0}".format(f) for f in lazy_libs])
                self.c_compile(program_text, opts, out_file,
                    obj_files=obj_files)

                return out_file[len(self.test_proto_dir)+1:]

        def pkgsend_with_fmri(self, pth):
                plist = self.pkgsend(self.rurl1,
                    "publish -d {0} {1}".format(
                    self.test_proto_dir, pth))

        def check_res(self, expected, seen):
                def pick_file(act):
                        fs = act.attrs[DDP + ".file"]
                        if isinstance(fs, six.string_types):
                                fs = [fs]
                        for f in fs:
                                if f.endswith(".py") and "__init__" not in f:
                                        return f
                        return fs[0]

                seen = seen.strip()
                expected = expected.strip()
                if seen == expected:
                        return
                seen = set(seen.splitlines())
                expected = set(expected.splitlines())
                seen_but_not_expected = self.__compare_res(seen, expected)
                expected_but_not_seen = self.__compare_res(expected, seen)
                try:
                        self.assertEqualDiff(expected_but_not_seen,
                            seen_but_not_expected)
                except AssertionError as e:
                        # This code is used to make the differences between
                        # expected and seen depend actions with all their debug
                        # information clearer.
                        res = str(e)
                        res += "\n\n\n"
                        try:
                                seen = [
                                    actions.fromstr(a)
                                    for a in seen_but_not_expected
                                ]
                                tmp = [
                                    actions.fromstr(a)
                                    for a in expected_but_not_seen
                                ]
                        except:
                                raise e
                        exp = dict([(pick_file(a), a) for a in tmp])
                        new = set()
                        conflicting = set()
                        for a in seen:
                                n = pick_file(a)
                                t = "the results for {0} differ in the " \
                                    "following attributes:\n".format(n)
                                if n in exp:
                                        ea = exp[n]
                                        for ak in a.attrs.keys():
                                                if ak not in ea.attrs:
                                                        t += "\thas an " \
                                                            "unexpected " \
                                                            "attribute {0}\n".format(
                                                            ak)
                                                        continue
                                                av = a.attrs[ak]
                                                ev = ea.attrs[ak]
                                                if not isinstance(av, list):
                                                        av = [av]
                                                if not isinstance(ev, list):
                                                        ev = [ev]
                                                av = set(av)
                                                ev = set(ev)
                                                diffs = sorted([
                                                    "{0}:S".format(d)
                                                    for d in
                                                    (av - ev)
                                                    ] + [
                                                    "{0}:E".format(d)
                                                    for d in (ev - av)
                                                ])
                                                if diffs:
                                                        t += "\t{0} has " \
                                                            "different " \
                                                            "values:\n".format(ak)
                                                        for d in diffs:
                                                                t += "\t\t{0}" \
                                                                    "\n".format(d)
                                res += t
                        raise RuntimeError(res)

        def test_elf_dependency_tags(self):
                """Testing related to bug 18990 where pkgdepend doesn't handle
                all types of elf dependencies correctly."""

                # Other places test the basic NEEDED elf depedency.

                manf = """\
file group=bin mode=0755 owner=sys path=usr/lib/foo.so.1
"""
                foo_c = """\
void bar() {}
void foo() { bar(); }
"""

                bar_c = """\
void bar() {}
"""
                mapfile_1 = """\
$mapfile_version 2

SYMBOL_SCOPE {
        global:
                bar { FILTER=bar.so };
};
"""
                mapfile_2 = """\
$mapfile_version 2

SYMBOL_SCOPE {
        global:
                bar { AUXILIARY=xxx.so };
};
"""
                def __check_res(es, ms, pkg_attrs):
                        self.assertEqual(len(es), 0,
                            "\n".join([str(d) for d in es]))
                        self.assertEqual(len(ms), 0,
                            "\n".join([str(d) for d in ms]))
                        self.assertEqual(pkg_attrs, {})

                base_dir = os.path.join(self.test_proto_dir, "usr", "lib")
                foo_path = os.path.join(base_dir, "foo.o")
                bar_path = os.path.join(base_dir, "bar.so")
                so_path = os.path.join(base_dir, "foo.so.1")
                mapfile_1_path = os.path.join(self.test_root, "mapfile_1")
                mapfile_2_path = os.path.join(self.test_root, "mapfile_2")
                mp = self.make_manifest(manf)

                self.make_elf(output_path=bar_path, program_text=bar_c,
                    shared_lib=True)
                # Test that FILTER dependencies are treated as needed.
                self.make_elf(output_path=foo_path, no_link=True,
                    program_text=foo_c)
                self.make_elf(output_path=so_path, run_paths=[base_dir],
                    filter_files=[bar_path], shared_lib=True,
                    obj_files=[foo_path])

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                __check_res(es, ms, pkg_attrs)
                self.assertEqual(len(ds), 2, "\n".join([str(d) for d in ds]))
                expected_file_deps = ["bar.so", "libc.so.1"]
                found_file_deps = sorted(set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds])))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

                # Test that SUNW_FILTER dependencies are treated as needed.
                self.make_file(mapfile_1_path, mapfile_1)
                self.make_elf(output_path=foo_path, no_link=True,
                    program_text=foo_c)
                self.make_elf(output_path=so_path, run_paths=[base_dir],
                    mapfile=mapfile_1_path, obj_files=[foo_path],
                    shared_lib=True)

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                __check_res(es, ms, pkg_attrs)
                self.assertEqual(len(ds), 2, "\n".join([str(d) for d in ds]))
                expected_file_deps = ["bar.so", "libc.so.1"]
                found_file_deps = sorted(set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds])))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

                # Test that AUXILIARY dependencies are ignored.
                self.make_elf(output_path=foo_path, no_link=True,
                    program_text=foo_c)
                self.make_elf(output_path=so_path, run_paths=[base_dir],
                    optional_filters=["xxx.so"], obj_files=[foo_path],
                    shared_lib=True)

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                __check_res(es, ms, pkg_attrs)
                self.assertEqual(len(ds), 1, "\n".join([str(d) for d in ds]))
                expected_file_deps = set(["libc.so.1"])
                found_file_deps = set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds]))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

                # Test that SUNW_AUXILIARY dependencies are ignored.
                self.make_file(mapfile_2_path, mapfile_2)
                self.make_elf(output_path=foo_path, no_link=True,
                    program_text=foo_c)
                self.make_elf(output_path=so_path, run_paths=[base_dir],
                    mapfile=mapfile_2_path, obj_files=[foo_path],
                    shared_lib=True)

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                __check_res(es, ms, pkg_attrs)
                self.assertEqual(len(ds), 1, "\n".join([str(d) for d in ds]))
                expected_file_deps = set(["libc.so.1"])
                found_file_deps = set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds]))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

                # Test that a NEEDED dependency with a LAZY DEFERRED POSFLAG_1
                # before it is ignored.
                self.make_elf(output_path=foo_path, no_link=True,
                    program_text=foo_c)
                self.make_elf(output_path=so_path, run_paths=[base_dir],
                    deferred_libs=[bar_path], shared_lib=True,
                    obj_files=[foo_path])

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                __check_res(es, ms, pkg_attrs)
                self.assertEqual(len(ds), 1, "\n".join([str(d) for d in ds]))
                expected_file_deps = set(["libc.so.1"])
                found_file_deps = set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds]))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

                # Test that a lazy loaded dependency is still required.
                self.make_elf(output_path=foo_path, no_link=True,
                    program_text=foo_c)
                self.make_elf(output_path=so_path, run_paths=[base_dir],
                    lazy_libs=[bar_path], shared_lib=True,
                    obj_files=[foo_path])

                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                __check_res(es, ms, pkg_attrs)
                self.assertEqual(len(ds), 2, "\n".join([str(d) for d in ds]))
                expected_file_deps = ["bar.so", "libc.so.1"]
                found_file_deps = sorted(set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds])))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

        def test_audit_dependency(self):
                """Test related to bug 7156221 where pkgdepend doesn't handle
                auditing dependencies correctly."""
                manf1 = """\
file group=bin mode=0755 owner=sys path=usr/lib/libfoo.so.1
"""

                manf2 = """\
file group=bin mode=0755 owner=sys path=usr/lib/main
"""

                foo_c = """\
int foo() { return 1; }
"""

                main_c = """\
int main() { return 1; }
"""

                base_dir = os.path.join(self.test_proto_dir, "usr", "lib")
                so_path = os.path.join(base_dir, "libfoo.so.1")
                main_path = os.path.join(base_dir, "main")
                manifest1_path = self.make_manifest(manf1)
                manifest2_path = self.make_manifest(manf2)

                # Test that AUDIT dependency can be detected.
                self.make_elf(output_path=so_path, program_text=foo_c,
                    shared_lib=True, record_audit=True)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    manifest1_path, [self.test_proto_dir], {}, [],
                    convert=False)

                self.assertEqual(len(ds), 2, "\n".join([str(d) for d in ds]))
                expected_file_deps = ["audit.so.1", "libc.so.1"]
                found_file_deps = sorted(set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds])))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

                # Test that DEPAUDIT dependency can be detected.
                self.make_elf(output_path=main_path, program_text=main_c,
                    deferred_libs=[so_path])
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    manifest2_path, [self.test_proto_dir], {}, [],
                    convert=False)
                found_file_deps = sorted(set(itertools.chain.from_iterable(
                    [d.attrs[DDP + ".file"] for d in ds])))
                self.assertEqualDiff(expected_file_deps, found_file_deps)

        def test_opts(self):
                """Ensure that incorrect arguments or permissions errors don't
                cause a traceback."""

                proto = pkg5unittest.g_proto_area
                self.pkgdepend_generate("-d {0}".format(proto), exit=2)
                self.pkgdepend_generate("foo", exit=2)
                self.pkgdepend_generate("-d {0} -z foo bar".format(proto), exit=2)
                self.pkgdepend_generate("-d {0} no_such_file_should_exist".format(
                    proto), exit=2)
                self.pkgdepend_generate("-\?")
                self.pkgdepend_generate("--help")
                tp = self.make_manifest(self.test_manf_1)
                self.pkgdepend_generate("-d {0} {1}".format(proto, tp),
                    su_wrap=True, exit=1)

        def test_output(self):
                """Check that the output is in the format expected."""

                tp = self.make_manifest(self.test_manf_1)
                fp = "usr/lib/python{0}/vendor-packages/pkg/client/indexer.py".format(
                    py_ver_default)

                self.pkgdepend_generate("-d {0} {1}".format(
                    pkg5unittest.g_proto_area, tp), exit=1)
                self.check_res(self.make_res_manf_1(
                        pkg5unittest.g_proto_area, fp),
                    self.output)
                self.check_res(self.err_manf_1.format(pkg5unittest.g_proto_area),
                    self.errout)

                self.pkgdepend_generate("-m -d {0} {1}".format(
                    pkg5unittest.g_proto_area, tp), exit=1)
                self.check_res(
                    self.make_full_res_manf_1(
                        pkg5unittest.g_proto_area, fp),
                    self.output)
                self.check_res(self.err_manf_1.format(pkg5unittest.g_proto_area),
                    self.errout)

                self.make_proto_text_file(fp, self.python_text)
                self.make_elf([], "usr/xpg4/lib/libcurses.so.1")

                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(
                    self.make_full_res_manf_1_mod_proto(
                        pkg5unittest.g_proto_area, fp),
                    self.output)
                self.check_res("", self.errout)

                tp = self.make_manifest(self.test_manf_2)
                self.make_proto_text_file("etc/pam.conf", "text")

                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(self.res_manf_2 + self.test_manf_2, self.output)
                self.check_res("", self.errout)

                res_path = self.make_manifest(self.output)

                # Check that -S doesn't prevent the resolution from happening.
                self.pkgdepend_resolve("-S -o {0}".format(res_path), exit=1)
                self.check_res("# {0}".format(res_path), self.output)
                self.check_res(self.resolve_error.format(
                        manf_path=res_path,
                        pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
                        dummy_fmri=base.Dependency.DUMMY_FMRI
                    ), self.errout)

                self.pkgdepend_generate("-M -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(self.res_manf_2, self.output)
                self.check_res(self.res_manf_2_missing, self.errout)

                portable.remove(tp)
                portable.remove(res_path)

                tp = self.make_manifest(self.int_hardlink_manf)

                self.make_proto_text_file("var/log/syslog", "text")

                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res("", self.output)
                self.check_res("", self.errout)

                self.pkgdepend_generate("-I -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(self.res_int_manf, self.output)
                self.check_res("", self.errout)

                portable.remove(tp)

        def test_resolve_screen_out(self):
                """Check that the results printed to screen are what is
                expected."""

                m1_path = self.make_manifest(self.two_variant_deps)
                m2_path = self.make_manifest(self.two_v_deps_bar)
                m3_path = self.make_manifest(self.two_v_deps_baz_one)
                m4_path = self.make_manifest(self.two_v_deps_baz_two)
                # Use pkgfmt on the manifest to test for bug 18740.
                self.pkgfmt(m1_path)
                with open(m1_path, "r") as fh:
                        m1_fmt = fh.read()
                self.pkgdepend_resolve("-o -m {0}".format(
                    " ".join([m1_path, m2_path, m3_path, m4_path])), exit=1)

                self.check_res(self.two_v_deps_output.format(
                        m1_path=m1_path,
                        m2_path=m2_path,
                        m3_path=m3_path,
                        m4_path=m4_path,
                        m1_fmt=m1_fmt,
                        m2_fmt=self.two_v_deps_bar,
                        m3_fmt=self.two_v_deps_baz_one,
                        m4_fmt=self.two_v_deps_baz_two,
                   ), self.output)

                self.check_res(self.two_v_deps_resolve_error.format(
                        manf_path=m1_path,
                        pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
                        dummy_fmri=base.Dependency.DUMMY_FMRI
                    ), self.errout)

                self.pkgdepend_resolve("-vo {0}".format(
                    " ".join([m1_path, m2_path, m3_path, m4_path])), exit=1)

                self.check_res(self.two_v_deps_verbose_output.format(
                        m1_path=m1_path,
                        m2_path=m2_path,
                        m3_path=m3_path,
                        m4_path=m4_path
                   ), self.output)

        def test_bug_10518(self):
                """ pkgdepend should exit 2 on input args of the wrong type """
                m_path = self.make_manifest(self.test_manf_1)

                # Try feeding a directory where a manifest should be--
                # a typical scenario we play out here is a user
                # inverting the first and second args.
                self.pkgdepend_generate("/", exit=2)
                self.check_res(
                    "pkgdepend: The manifest file / could not be found.\n" +
                    self.usage_msg, self.errout)

                self.pkgdepend_resolve("-o /", exit=2)
                self.check_res(
                    "pkgdepend: The manifest file / could not be found.\n" +
                    self.usage_msg, self.errout)

        def test_bug_11517(self):
                """ Test the pkgdepend handles bad global options """

                m_path = None
                ill_usage = 'pkgdepend: illegal global option -- M\n'
                try:
                        m_path = self.make_manifest(self.test_manf_1)

                        self.pkgdepend_resolve("-M -o {0} ".format(m_path), exit=2)
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

                proto = pkg5unittest.g_proto_area
                tp = self.make_manifest(self.payload_manf)
                self.pkgdepend_generate("-d {0} {1}".format(proto, tp))
                self.check_res(self.make_res_payload_1(proto,
                    "usr/lib/python{0}/foo/bar.py".format(py_ver_default)),
                    self.output)
                self.check_res("", self.errout)

        def test_bug_11829(self):
                """ pkgdep should gracefully deal with a non-manifest """

                m_path = None
                atype = "This"
                nonsense = "This is a nonsense manifest"
                m_path = self.make_manifest(nonsense)

                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, m_path), exit=1)
                self.debug(self.errout)
                self.check_res("unknown action type '{0}' in action '{1}'".format(
                    atype, nonsense), self.errout)

                self.pkgdepend_resolve("-o {0} ".format(m_path), exit=1)
                self.check_res("unknown action type '{0}' in action '{1}'".format(
                    atype, nonsense), self.errout)

        def __run_dyn_tok_test(self, run_paths, replaced_path, dep_args):
                """Using the provided run paths, produces a elf binary with
                those paths set and checks to make sure that pkgdep run with
                the provided arguments performs the substitution correctly."""

                elf_path = self.make_elf(run_paths)
                m_path = self.make_manifest(self.elf_sub_manf.format(
                    file_loc=elf_path))
                self.pkgdepend_generate("{0} -d {1} {2}".format(
                    dep_args, self.test_proto_dir, m_path))
                self.check_res(self.payload_elf_sub_stdout.format(
                    replaced_path=\
                        " {0}.path={1}".format(
                        base.Dependency.DEPEND_DEBUG_PREFIX, replaced_path)),
                    self.output)

        def test_bug_12697(self):
                """Test that the -D and -k options work as expected.

                The -D and -k options provide a way for a user to specify
                tokens to expand dynamically in run paths and the kernel paths
                to use for kernel module run paths."""

                elf_path = self.make_elf([])
                m_path = self.make_manifest(self.kernel_manf.format(
                    file_loc=elf_path))
                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, m_path))
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout, self.output)

                self.pkgdepend_generate("-k baz -k foo/bar -d {0} {1}".format(
                    self.test_proto_dir, m_path))
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout2, self.output)

                self.debug("Test for platform substitution in kernel " \
                    "module paths. Bug 13057")

                self.pkgdepend_generate(
                    "-D PLATFORM=baz -D PLATFORM=tp -d {0} {1}".format(
                    self.test_proto_dir, m_path))
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout_platform, self.output)

                self.debug("Test unexpanded token")

                rp = ["/platform/$PLATFORM/foo"]
                elf_path = self.make_elf(rp)
                m_path = self.make_manifest(self.elf_sub_manf.format(
                    file_loc=elf_path))
                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, m_path), exit=1)
                self.check_res((self.payload_elf_sub_error.format(
                        payload_path=os.path.join(self.test_proto_dir,
                            elf_path),
                        installed_path="bar/foo",
                        tok="$PLATFORM",
                        rp=rp[0]
                    )), self.errout)
                self.check_res(self.payload_elf_sub_stdout.format(
                    replaced_path=""), self.output)

                self.check_res(self.payload_elf_sub_stdout.format(
                    replaced_path=""), self.output)

                # Test token expansion
                self.debug("test token expansion: $PLATFORM")
                self.__run_dyn_tok_test(["/platform/$PLATFORM/foo"],
                    "platform/pfoo/foo", "-D PLATFORM=pfoo")

                self.debug("test token expansion: $ISALIST")
                self.__run_dyn_tok_test(["/foo/bar/$ISALIST/baz"],
                    "foo/bar/SUBL/baz", "-D '$ISALIST=SUBL'")

                self.debug("test token expansion: $PLATFORM and $ISALIST")
                self.__run_dyn_tok_test(["/foo/$PLATFORM/$ISALIST/baz"],
                    "foo/pfoo/bar/SUBL/baz",
                    "-D ISALIST=SUBL -D PLATFORM=pfoo/bar")

                self.debug("test token expansion: multiple $PLATFORM")
                self.__run_dyn_tok_test(
                    ["/$PLATFORM/$PLATFORM/$ISALIST/$PLATFORM"],
                    "bar/bar/SUBL/bar", "-D ISALIST=SUBL -D PLATFORM=bar")

                self.debug("Test multiple run paths and multiple subs")
                rp = ["/platform/$PLATFORM/foo", "/$ISALIST/$PLATFORM/baz"]
                elf_path = self.make_elf(rp)
                m_path = self.make_manifest(self.elf_sub_manf.format(
                    file_loc=elf_path))
                self.pkgdepend_generate("-D ISALIST=isadir -d {0} {1}".format(
                    self.test_proto_dir, m_path), exit=1)
                self.check_res(self.double_plat_error.format(
                    proto_dir=self.test_proto_dir), self.errout)
                self.check_res(self.double_plat_stdout, self.output)

                self.pkgdepend_generate("-D PLATFORM=pfoo -d {0} {1}".format(
                    self.test_proto_dir, m_path), exit=1)
                self.check_res(self.double_plat_isa_error.format(
                    proto_dir=self.test_proto_dir), self.errout)
                self.check_res(self.double_plat_isa_stdout, self.output)

                self.pkgdepend_generate("-D PLATFORM=pfoo -D PLATFORM=pfoo2 "
                    "-D ISALIST=isadir -D ISALIST=isadir -d {0} {1}".format(
                    self.test_proto_dir, m_path))
                self.check_res("", self.errout)
                self.check_res(self.double_double_stdout, self.output)

        def test_bug_12816(self):
                """Test that the error produced by a missing payload action
                uses the right path."""

                m_path = self.make_manifest(self.miss_payload_manf)
                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, m_path), exit=1)
                self.check_res(self.miss_payload_manf_error.format(
                    path_pref=self.test_proto_dir), self.errout)
                self.check_res("", self.output)

        def test_bug_14116(self):
                foo_path = self.make_proto_text_file("bar/foo", "#!perl -w\n\n")
                m_path = self.make_manifest(self.elf_sub_manf.format(
                    file_loc="bar/foo"))
                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, m_path), exit=1)
                self.check_res(self.output, "")
                self.check_res(self.errout, "{0}/bar/foo says it should be run "
                    "with 'perl' which is a relative path.".format(
                    self.test_proto_dir))

        def test_unsatisfied_deps(self):
                """Test resolution behaviour with various unsatisfied
                dependencies"""
                unsat = self.make_manifest(self.unsatisfied_manf)
                partial = self.make_manifest(self.partially_satisfied_manf)
                satisfying = self.make_manifest(self.satisfying_manf)

                # Generally unsatisfied dependency
                self.pkgdepend_resolve(" -o {0}".format(unsat), exit=1)
                self.check_res(self.unsatisfied_error_1.format(unsat), self.errout)

                # Dependency that would be satisfied were it not for
                # mismatched variants
                self.pkgdepend_resolve(" -o {0} {1}".format(unsat, satisfying),
                    exit=1)
                self.check_res(self.unsatisfied_error_1.format(unsat), self.errout)

                # Partially satisfied dependency (for one variant
                # value, not another)
                self.pkgdepend_resolve(" -o {0} {1}".format(partial, satisfying),
                    exit=1)
                self.check_res(self.unsatisfied_error_2.format(partial), self.errout)
                self.check_res("# {0}\n{1}\n\n# {2}\n".format(partial,
                    self.satisfying_out, satisfying), self.output)

                # No dependencies at all
                self.pkgdepend_resolve(" -o {0}".format(satisfying))

        def test_bug_14118(self):
                """Check that duplicate dependency actions are consolitdated
                correctly, taking the variants into accout."""

                # In the comments below, v.f stands for variant.foo and v.n
                # stands for variant.num.

                # dup_variant_deps contains all the dependencies to be resolved.
                # It is published as dup-v-deps.
                m1_path = self.make_manifest(self.dup_variant_deps)

                # two_v_deps_bar is published as the package s-v-bar.  It
                # provides var/log/authlog when v.f=bar and var/log/file2 under
                # all variants.  This means that dup-v-deps should depend
                # unconditionally on s-v-bar.  This resolution tests that a
                # dependency on X which exists only under a specific combination
                # of variants is merged into a more general dependency
                # appropriately.
                m2_path = self.make_manifest(self.two_v_deps_bar)

                # two_v_deps_baz_one is published as the package s-v-baz-one.
                # It provides var/log/authlog when v.f=baz and v.n=one.  This
                # means that dup-v-deps should depend on s-v-baz-one when
                # v.f=baz and v.n=one.  This resolution tests that dependencies
                # are still versioned correctly when necessary.
                m3_path = self.make_manifest(self.two_v_deps_baz_one)

                # two_v_deps_baz_two is identical to two_v_deps_baz_one except
                # that it provides var/log/authlog when v.f=baz and v.n=two.
                m4_path = self.make_manifest(self.two_v_deps_baz_two)

                # dup_prov is published as the package dup-prov.  It provides
                # var/log/f1 and var/log/f2 under all variants.  dup-v-deps
                # depends on dup-prov under all combinations of variants because
                # of each file.  This tests that when two dependencies are valid
                # under same set of variants, they're combined correctly.
                m5_path = self.make_manifest(self.dup_prov)

                # sep_vars is published as sep_vars.  It provides var/log/f3
                # when v.f=bar and var/log/f4 when v.f=baz.  This means that
                # dup-v-deps depends on sep_vars for different reasons when
                # v.f=bar and when v.f=baz.  This tests that those dependencies
                # continue to be reported as separate dependencies.
                m6_path = self.make_manifest(self.sep_vars)

                # subset_prov unconditionally provides two files, f5 and f6.
                # dup-v-deps unconditionally depends on f5, and conditionally
                # depends on f6.  This means that dup-v-deps should
                # unconditionally depend on dup-v-deps.  This also tests that
                # variants are removed and added during the internal processing
                # of dependency resolution.
                m7_path = self.make_manifest(self.subset_prov)

                # This empty manifest will be published as hand-dep. This checks
                # that manually added dependencies are propogated correctly.
                m8_path = self.make_manifest("\n\n")

                # Test that resolve handles multiline actions correctly when
                # echoing the manifest.  Bug 18740
                self.pkgfmt(m1_path)

                self.pkgdepend_resolve(" -vm {0}".format(" ".join([m1_path, m2_path,
                        m3_path, m4_path, m5_path, m6_path, m7_path, m8_path])))
                fh = open(m1_path + ".res")
                res = fh.read()
                fh.close()
                self.check_res(self.dup_variant_deps_resolved, res)

                pfmris = {
                    m1_path: "pkg:/dup-v-deps@0.1-0.2",
                    m2_path: "pkg:/s-v-bar@0.1-0.2",
                    m3_path: "pkg:/s-v-baz-one@0.1-0.2",
                    m4_path: "pkg:/s-v-baz-two@0.1-0.2",
                    m5_path: "pkg:/dup-prov@0.1-0.2",
                    m6_path: "pkg:/sep_vars@0.1-0.2",
                    m7_path: "pkg:/subset-prov@0.1-0.2 ",
                    m8_path: "pkg:/hand-dep@0.1-0.2",
                }

                # Add FMRI to each manifest for use with publish.
                for mpath, pfmri in pfmris.items():
                        lines = open(mpath + ".res", "r").readlines()
                        with open(mpath + ".res", "w") as mf:
                                mf.write("set name=pkg.fmri value={0}\n".format(pfmri))
                                for l in lines:
                                        if "pkg.fmri" in l:
                                                continue
                                        mf.write(l)

                # Check that the results can be installed correctly.
                self.make_proto_text_file("var/log/file2")
                self.make_proto_text_file("var/log/authlog")
                self.make_proto_text_file("var/log/f1")
                self.make_proto_text_file("var/log/f2")
                self.make_proto_text_file("var/log/f3")
                self.make_proto_text_file("var/log/f4")
                self.make_proto_text_file("var/log/f5")
                self.make_proto_text_file("var/log/f6")
                self.make_proto_text_file(
                    "platform/i86pc/kernel/dacf/amd64/consconfig_dacf")
                self.make_proto_text_file(
                    "platform/i86pc/kernel/dacf/consconfig_dacf")
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m1_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m2_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m3_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m4_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m5_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m6_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m7_path + ".res"))
                self.pkgsend(self.rurl, "publish -d {0} {1}".format(
                    self.test_proto_dir, m8_path + ".res"))
                foo_vars = ["bar", "baz"]
                num_vars = ["one", "two"]
                for fv in foo_vars:
                        for nv in num_vars:
                                variants = { "variant.foo": fv,
                                    "variant.num": nv }
                                self.image_create(self.rurl, variants=variants)
                                self.pkg("install dup-v-deps")
                                self.image_destroy()

        def test_bug_15777(self):
                """Test that -S switch disables resolving dependencies against
                the installed system."""

                self.make_misc_files(["tmp/foo"])
                self.pkgsend_bulk(self.rurl, self.inst_pkg)
                api_obj = self.get_img_api_obj()
                api_obj.refresh(immediate=True)
                self._api_install(api_obj, ["example2_pkg"])

                m1_path = self.make_manifest(self.multi_deps)
                m2_path = self.make_manifest(self.misc_manf)

                self.pkgdepend_resolve("-o {0} {1}".format(m1_path, m2_path))
                self.pkgdepend_resolve("-o -S {0} {1}".format(m1_path, m2_path),
                    exit=1)

        def test_bug_15843(self):
                """Test that multiple proto_dirs work as expected."""

                curses = "usr/xpg4/lib/libcurses.so.1"
                pam = "etc/pam.conf"
                self.make_elf([], "d1/{0}".format(curses))
                self.make_proto_text_file("d2/{0}".format(pam), "text")
                tp = self.make_manifest(self.test_manf_2)

                # Check that files are not found.
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp),
                    exit=1)
                self.check_res("", self.output)
                self.check_res("\n".join([
                    "Couldn't find '{0}' in any of the specified search "
                    "directories:\n\t{1}".format(d, self.test_proto_dir)
                    for d in (curses, pam)]),
                    self.errout)

                # Check that the files are now correctly found.
                self.pkgdepend_generate("-d {0} -d {1} -d {2} {3}".format(
                    self.test_proto_dir,
                    os.path.join(self.test_proto_dir, "d1"),
                    os.path.join(self.test_proto_dir, "d2"), tp))
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                # Check that ordering among proto_dirs is correct.
                # This should produce no dependencies because the text file
                # in self.test_proto_dir should be found first.
                self.make_proto_text_file("usr/xpg4/lib/libcurses.so.1", "text")
                self.pkgdepend_generate("-d {0} -d {1} -d {2} {3}".format(
                    self.test_proto_dir,
                    os.path.join(self.test_proto_dir, "d1"),
                    os.path.join(self.test_proto_dir, "d2"), tp))
                self.check_res("", self.output)
                self.check_res("", self.errout)

                # This should produce the normal results for this manifest
                # because the compiled elf file should be found before the
                # text file.
                self.pkgdepend_generate("-d {0} -d {1} -d {2} {3}".format(
                    os.path.join(self.test_proto_dir, "d2"),
                    os.path.join(self.test_proto_dir, "d1"),
                    self.test_proto_dir, tp))
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                # Check the ordering among -d dirs is correct.
                self.pkgdepend_generate("-d {0} -d {1} -d {2} {3}".format(
                    os.path.join(self.test_proto_dir, "d2"),
                    self.test_proto_dir,
                    os.path.join(self.test_proto_dir, "d1"), tp))
                self.check_res("", self.output)
                self.check_res("", self.errout)

        def test_bug_15958(self):
                """Test that a dependency which is not satisfied internally
                under certain variants is reported correctly."""

                tp = self.make_manifest(self.bug_15958_manf)
                self.make_proto_text_file("var/log/syslog", "text")
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res("", self.errout)
                self.check_res(self.res_bug_15958, self.output)

        def test_bug_16013_base(self):
                """Test that dependencies which involve links in their paths
                work correctly.  Also tests that dependencies with build
                versions set cannot be produced (bug 17412).  Build versions are
                the ,5.11 components in the fmris."""

                api_obj = self.get_img_api_obj()

                self.make_proto_text_file("b/bin/perl")
                a_pth = self.make_manifest(self.bug_16013_simple_a_dep_manf)
                b_pth = self.make_manifest(self.bug_16013_simple_b_dep_manf)

                plist = self.pkgsend_with_fmri(b_pth)

                # Test that pkgdep can resolve dependencies through symlinks
                # in paths at all.
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, b_pth], None, [],
                        prune_attrs=False)
                def check_res(deps, errs):
                        self.assertEqual(len(errs), 0,
                            "\n" + "\n\n".join([str(s) for s in errs]))
                        self.assertEqual(len(deps[a_pth]), 1,
                            "\n".join([str(s) for s in deps[a_pth]]))
                        d = deps[a_pth][0]
                        self.assertEqual(d.attrs["fmri"], "pkg:/b@0.5.11-0.151")
                        self.assertEqual(d.attrs[dependencies.type_prefix],
                            "script")
                check_res(deps, errs)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[b_pth]), 0,
                    "\n".join([str(s) for s in deps[b_pth]]))
                self._api_install(api_obj, ["b"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth], api_obj, ["*"],
                        prune_attrs=False)
                check_res(deps, errs)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["b"]), external_deps)
                self._api_uninstall(api_obj, ["b"])

        def test_bug_16013_packages_delivering_links(self):
                """Test that packages which provide path symlinks needed to
                resolve a dependency are included in the final set of
                dependencies."""

                self.make_proto_text_file("b2/bin/perl")
                a_pth = self.make_manifest(self.bug_16013_simple_a_dep_manf)
                b_link_pth = self.make_manifest(
                    self.bug_16013_simple_b_link_manf)
                b_link2_pth = self.make_manifest(
                    self.bug_16013_simple_b_link2_manf)
                b_file_pth = self.make_manifest(
                    self.bug_16013_simple_b_file_manf)

                plist = self.pkgsend_with_fmri(b_link_pth)
                plist = self.pkgsend_with_fmri(b_link2_pth)
                plist = self.pkgsend_with_fmri(b_file_pth)

                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_pth, b_file_pth, b_link_pth, b_link2_pth], None, [],
                        prune_attrs=False)

                self.bug_16013_check_res_simple_links(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

        def test_bug_16013_variants_base(self):
                """Test that variants on files, links and dependencies work
                correctly when resolving dependencies."""

                self.make_proto_text_file("c/bin/perl")
                a_pth = self.make_manifest(self.bug_16013_var_a_dep_manf)
                b_link_pth = self.make_manifest(self.bug_16013_var_b_link_manf)
                b_file_pth = self.make_manifest(self.bug_16013_var_b_file_manf)
                c_pth = self.make_manifest(self.bug_16013_var_c_manf)

                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_pth, b_file_pth, b_link_pth, c_pth], None, [],
                        prune_attrs=False)

                self.bug_16013_check_res_variants_base(deps, errs, a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

        def test_bug_16013_variants_filtered_by_links(self):
                """Test that variants due to files are appropriately filtered by
                the links needed to reach them."""

                multivar_b_file_manf = """\
set name=pkg.fmri value=pkg:/b_file@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=c
"""
                self.make_proto_text_file("c/bin/perl")
                a_pth = self.make_manifest(self.bug_16013_var_a_dep_manf)
                b_link_pth = self.make_manifest(self.bug_16013_var_b_link_manf)
                c_pth = self.make_manifest(self.bug_16013_var_c_manf)

                multivar_b_file_pth = self.make_manifest(multivar_b_file_manf)
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_pth, multivar_b_file_pth, b_link_pth, c_pth], None,
                        [])
                self.bug_16013_check_res_variants_base(deps, errs, a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[multivar_b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

        def test_bug_16013_meaningless_files_ok(self):
                """Test that files which are irrelevant due to variants do not
                cause issues resolving dependencies."""

                a_var_b_dep_manf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.151
set name=variant.foo value=b value=c value=a
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require
"""

                c_no_link_manf = """\
set name=pkg.fmri value=pkg:/c@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
file NOHASH group=bin mode=0555 owner=root path=usr/bin/perl variant.foo=c
"""
                self.make_proto_text_file("c/bin/perl")
                a_var_b_dep_pth = self.make_manifest(a_var_b_dep_manf)
                b_link_pth = self.make_manifest(self.bug_16013_var_b_link_manf)
                b_file_pth = self.make_manifest(self.bug_16013_var_b_file_manf)
                c_no_link_pth = self.make_manifest(c_no_link_manf)

                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_var_b_dep_pth, b_file_pth,
                        b_link_pth, c_no_link_pth], None, [], prune_attrs=False)
                self.assertEqual(len(errs), 1,
                    "\n\n".join([str(s) for s in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                e = errs[0]
                self.assertEqual(e.path, a_var_b_dep_pth)
                self.assertEqual(e.file_dep.attrs[dependencies.files_prefix],
                    "perl")
                self.assertEqual(e.pvars.not_sat_set,
                    set([frozenset([("variant.foo", "a")])]))
                self.assertEqual(len(deps[a_var_b_dep_pth]), 3,
                    "\n".join([str(s) for s in deps[a_var_b_dep_pth]]))
                res_fmris = set(["pkg:/b_link@0.5.11-0.151",
                    "pkg:/b_file@0.5.11-0.151", "pkg:/c@0.5.11-0.151"])
                for d in deps[a_var_b_dep_pth]:
                        self.assertTrue(d.attrs["fmri"] in res_fmris,
                            "Unexpected fmri for:{0}".format(d))
                        res_fmris.remove(d.attrs["fmri"])
                        if d.attrs["fmri"] == "pkg:/b_link@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                        elif d.attrs["fmri"] == "pkg:/b_file@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                        else:
                                self.assertEqual(d.attrs["variant.foo"], "c")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")

                self.assertEqual(len(deps[c_no_link_pth]), 0)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

        def test_bug_16013_variants_due_to_links_filtered(self):
                """Test that variants due to links are appropriately filtered by
                the files they link to."""

                multivar_b_link_manf = """\
set name=pkg.fmri value=pkg:/b_link@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
link path=usr/bin target=/b/bin variant.foo=b
link path=usr/bin target=/b/bin variant.foo=c
dir group=bin mode=0755 owner=root path=b/bin variant.foo=b
"""
                a_pth = self.make_manifest(self.bug_16013_var_a_dep_manf)
                multivar_b_link_pth = self.make_manifest(multivar_b_link_manf)
                b_file_pth = self.make_manifest(self.bug_16013_var_b_file_manf)
                c_pth = self.make_manifest(self.bug_16013_var_c_manf)

                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_pth, b_file_pth, multivar_b_link_pth, c_pth], None,
                        [], prune_attrs=False)
                self.bug_16013_check_res_variants_base(deps, errs, a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[multivar_b_link_pth]), 0)

        def test_bug_16013_links_restricted(self):
                """Test that links without specific variant tags are restricted
                correctly."""

                multivar2_b_link_manf = """\
set name=pkg.fmri value=pkg:/b_link@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
link path=usr/bin target=/b/bin
dir group=bin mode=0755 owner=root path=b/bin variant.foo=b
"""

                self.make_proto_text_file("c/bin/perl")
                a_pth = self.make_manifest(self.bug_16013_var_a_dep_manf)
                b_file_pth = self.make_manifest(self.bug_16013_var_b_file_manf)
                c_pth = self.make_manifest(self.bug_16013_var_c_manf)

                multivar2_b_link_pth = self.make_manifest(multivar2_b_link_manf)
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_pth, b_file_pth, multivar2_b_link_pth, c_pth], None,
                        [], prune_attrs=False)
                self.bug_16013_check_res_variants_base(deps, errs, a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[multivar2_b_link_pth]), 0)

        def test_bug_16013_varianted_dependency_resolution(self):
                """Test that a dependency that only applies under certain
                variant combinations is resolved correctly."""

                a_var_limited_dep_manf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.151
set name=variant.foo value=b value=c value=a
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require variant.foo=b
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require variant.foo=c
"""
                a_var_limited_pth = self.make_manifest(a_var_limited_dep_manf)
                b_link_pth = self.make_manifest(self.bug_16013_var_b_link_manf)
                b_file_pth = self.make_manifest(self.bug_16013_var_b_file_manf)
                c_pth = self.make_manifest(self.bug_16013_var_c_manf)

                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_var_limited_pth, b_file_pth, b_link_pth, c_pth],
                        None, [], prune_attrs=False)
                self.assertEqual(len(errs), 0,
                    "\n\n".join([str(s) for s in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[a_var_limited_pth]), 3,
                    "\n".join([str(s) for s in deps[a_var_limited_pth]]))
                res_fmris = set(["pkg:/b_link@0.5.11-0.151",
                    "pkg:/c@0.5.11-0.151", "pkg:/b_file@0.5.11-0.151"])
                for d in deps[a_var_limited_pth]:
                        self.assertTrue(d.attrs["fmri"] in res_fmris,
                            "Unexpected fmri for:{0}".format(d))
                        res_fmris.remove(d.attrs["fmri"])
                        if d.attrs["fmri"] == "pkg:/b_link@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                        elif d.attrs["fmri"] == "pkg:/b_file@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                        else:
                                self.assertEqual(d.attrs["variant.foo"], "c")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

        def test_bug_16013_two_d_external(self):
                """Test that two dimensions of variants works correctly when
                resolving between packages."""

                twod_a_dep_manf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.151
set name=variant.foo value=b value=c value=a
set name=variant.bar value=v value=w value=x value=y value=z
depend fmri=__TBD pkg.debug.depend.file=perl pkg.debug.depend.path=usr/bin pkg.debug.depend.reason=usr/bin/perl_app pkg.debug.depend.type=script type=require
"""

                twod_b_vw_link_manf = """\
set name=pkg.fmri value=pkg:/b_vw_link@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
set name=variant.bar value=v value=w value=x value=y value=z
link path=usr/bin target=/b/bin variant.foo=b variant.bar=v
link path=usr/bin target=/b/bin variant.foo=b variant.bar=w
dir group=bin mode=0755 owner=root path=b/bin variant.foo=b
"""

                twod_b_yz_link_manf = """\
set name=pkg.fmri value=pkg:/b_yz_link@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
set name=variant.bar value=v value=w value=x value=y value=z
link path=usr/bin target=/b/bin variant.foo=b variant.bar=y
link path=usr/bin target=/b/bin variant.foo=b variant.bar=z
dir group=bin mode=0755 owner=root path=b/bin variant.foo=b
"""

                twod_b_vwx_file_manf = """\
set name=pkg.fmri value=pkg:/b_vwx_file@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
set name=variant.bar value=v value=w value=x value=y value=z
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b variant.bar=v
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b variant.bar=w
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b variant.bar=x
"""

                twod_b_y_file_manf = """\
set name=pkg.fmri value=pkg:/b_y_file@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
set name=variant.bar value=v value=w value=x value=y value=z
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b variant.bar=y
"""

                twod_c_manf = """\
set name=pkg.fmri value=pkg:/c@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
set name=variant.bar value=v value=w value=x value=y value=z
link path=usr/bin target=../c/bin variant.foo=c
dir group=bin mode=0755 owner=root path=c/bin variant.foo=c
file NOHASH group=bin mode=0555 owner=root path=c/bin/perl variant.foo=c
"""
                twod_a_pth = self.make_manifest(twod_a_dep_manf)
                twod_b_vw_link_pth = self.make_manifest(twod_b_vw_link_manf)
                twod_b_yz_link_pth = self.make_manifest(twod_b_yz_link_manf)
                twod_b_vwx_file_pth = self.make_manifest(twod_b_vwx_file_manf)
                twod_b_y_file_pth = self.make_manifest(twod_b_y_file_manf)
                twod_c_pth = self.make_manifest(twod_c_manf)

                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([twod_a_pth, twod_b_vw_link_pth,
                        twod_b_yz_link_pth, twod_b_vwx_file_pth,
                        twod_b_y_file_pth, twod_c_pth], None, [],
                        prune_attrs=False)

                self.assertEqual(len(errs), 1,
                    "\n\n".join([str(s) for s in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                missing_vcs = []
                e = errs[0]
                self.assertEqual(e.path, twod_a_pth)
                self.assertEqual(e.file_dep.attrs[dependencies.files_prefix],
                    "perl")
                # Set is unordered, the output might be different in order, so
                # we just assert the sets are equal.
                self.assertEqual(set([
                    frozenset([("variant.foo", "a")]),
                    frozenset([("variant.foo", "b"), ("variant.bar", "x")]),
                    frozenset([("variant.foo", "b"), ("variant.bar", "z")])
                ]), e.pvars.not_sat_set)
                self.assertEqual(len(deps[twod_a_pth]), 7,
                    "\n\n".join([str(s) for s in deps[twod_a_pth]]))
                res_fmris = set(["pkg:/b_vw_link@0.5.11-0.151",
                    "pkg:/b_yz_link@0.5.11-0.151", "pkg:/c@0.5.11-0.151",
                    "pkg:/b_vwx_file@0.5.11-0.151",
                    "pkg:/b_y_file@0.5.11-0.151"])
                b_vw_link_var = set(["v", "w"])
                b_vwx_file_var = set(["v", "w"])
                b_yz_link_var = set(["y"])
                b_y_file_var = set(["y"])
                for d in deps[twod_a_pth]:
                        self.assertTrue(d.attrs["fmri"] in res_fmris,
                            "Unexpected fmri for:{0}".format(d))
                        if d.attrs["fmri"] == "pkg:/b_vw_link@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                                self.assertTrue(
                                    d.attrs["variant.bar"] in b_vw_link_var)
                                b_vw_link_var.remove(d.attrs["variant.bar"])
                        elif d.attrs["fmri"] == "pkg:/b_vwx_file@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                                self.assertTrue(
                                    d.attrs["variant.bar"] in b_vwx_file_var)
                                b_vwx_file_var.remove(d.attrs["variant.bar"])
                        elif d.attrs["fmri"] == "pkg:/b_y_file@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                                self.assertTrue(
                                    d.attrs["variant.bar"] in b_y_file_var)
                                b_y_file_var.remove(d.attrs["variant.bar"])
                        elif d.attrs["fmri"] == "pkg:/b_yz_link@0.5.11-0.151":
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "link")
                                self.assertEqual(d.attrs["variant.foo"], "b")
                                self.assertTrue(
                                    d.attrs["variant.bar"] in b_yz_link_var)
                                b_yz_link_var.remove(d.attrs["variant.bar"])
                        else:
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix], "script")
                                self.assertEqual(d.attrs["variant.foo"], "c")
                                self.assertTrue("variant.bar" not in d.attrs)

                self.assertEqual(len(deps[twod_c_pth]), 0)
                self.assertEqual(len(deps[twod_b_vwx_file_pth]), 0)
                self.assertEqual(len(deps[twod_b_y_file_pth]), 0)
                self.assertEqual(len(deps[twod_b_vw_link_pth]), 0)
                self.assertEqual(len(deps[twod_b_yz_link_pth]), 0)

        def test_bug_16013_installed_combinations(self):
                """Test various combinations of installed and delivered
                packages."""

                # We need to explicitly set the image variant or we'll blow up
                # due to conflicting actions.
                self.pkg("change-variant variant.foo=b")

                self.make_proto_text_file("c/bin/perl")
                self.make_proto_text_file("b/bin/perl")
                a_pth = self.make_manifest(self.bug_16013_var_a_dep_manf)
                b_link_pth = self.make_manifest(self.bug_16013_var_b_link_manf)
                b_file_pth = self.make_manifest(self.bug_16013_var_b_file_manf)
                c_pth = self.make_manifest(self.bug_16013_var_c_manf)

                plist = self.pkgsend_with_fmri(a_pth)
                plist = self.pkgsend_with_fmri(b_link_pth)
                plist = self.pkgsend_with_fmri(b_file_pth)
                plist = self.pkgsend_with_fmri(c_pth)

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["c"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, b_file_pth, b_link_pth],
                        api_obj, ["*"], prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["c"]), external_deps)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

                self._api_install(api_obj, ["b_link"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, b_file_pth], api_obj,
                        ["*"], prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["b_link", "c"]), external_deps)
                self.assertEqual(len(deps[b_file_pth]), 0)

                self._api_install(api_obj, ["b_file"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth], api_obj, ["*"],
                        prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["b_file", "b_link", "c"]),
                    external_deps)

                # Test that delivering installed packages works correctly.
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps(
                        [a_pth, b_file_pth, b_link_pth, c_pth], api_obj, ["*"],
                        prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[b_file_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)
                self.assertEqual(len(deps[c_pth]), 0)

                # Test more combinations of installed and delivered
                self._api_uninstall(api_obj, ["c"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, c_pth], api_obj, ["*"],
                        prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["b_file", "b_link"]), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)

                self._api_uninstall(api_obj, ["b_link"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, b_link_pth, c_pth],
                        api_obj, ["*"], prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["b_file"]), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

                bad_b_link_manf = """\
set name=pkg.fmri value=pkg:/b_link@0.5.11,5.11-0.152
set name=variant.foo value=b value=c
link path=usr/bin target=/bad_b/bin variant.foo=b
dir group=bin mode=0755 owner=root path=bad_b/bin variant.foo=b
"""
                bad_b_link_pth = self.make_manifest(bad_b_link_manf)
                plist = self.pkgsend_with_fmri(bad_b_link_pth)
                self._api_install(api_obj, ["b_link"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, c_pth], api_obj, ["*"],
                        prune_attrs=False)
                def bad_b_link_check_res(deps, errs):
                        self.assertEqual(len(errs), 1,
                            "\n".join([str(s) for s in errs]))
                        e = errs[0]
                        self.assertEqual(e.path, a_pth)
                        self.assertEqual(
                            e.file_dep.attrs[dependencies.files_prefix], "perl")
                        self.assertEqual(e.pvars.not_sat_set,
                            set([frozenset([("variant.foo", "a")]),
                                frozenset([("variant.foo", "b")])]))
                        self.assertEqual(len(deps[a_pth]), 1,
                            "\n".join([str(s) for s in deps[a_pth]]))
                        res_fmris = set(["pkg:/c@0.5.11-0.151"])
                        for d in deps[a_pth]:
                                self.assertTrue(d.attrs["fmri"] in res_fmris,
                                    "Unexpected fmri for:{0}".format(d))
                                res_fmris.remove(d.attrs["fmri"])
                                self.assertEqual(d.attrs["variant.foo"], "c")
                                self.assertEqual(
                                    d.attrs[dependencies.type_prefix],
                                    "script")
                bad_b_link_check_res(deps, errs)
                self.assertEqualDiff(set(["b_file", "b_link"]), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)

                # Check that the delivered manifests take priority over the
                # installed manifests.
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, b_link_pth, c_pth],
                        api_obj, ["*"], prune_attrs=False)
                self.bug_16013_check_res_var_files_links_deps(deps, errs,
                    a_pth)
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(["b_file"]), external_deps)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[b_link_pth]), 0)

                self._api_uninstall(api_obj, ["b_link"])
                self._api_install(api_obj, ["b_link@0.5.11,5.11-0.151"])
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([a_pth, bad_b_link_pth, c_pth],
                        api_obj, ["*"], prune_attrs=False)
                bad_b_link_check_res(deps, errs)
                self.assertEqual(len(deps[c_pth]), 0)
                self.assertEqual(len(deps[bad_b_link_pth]), 0)

        def test_bug_16013_internal_resolution(self):
                """Check that a dependency involving symbolic links is resolved
                internally during the generation phase."""

                foo_path = self.make_proto_text_file("bar/foo",
                    "#!/usr/bin/perl\n\n")
                self.make_proto_text_file("b/bin/perl")
                internal_dep_manf = """\
set name=pkg.fmri value=pkg:/internal@0.5.11,5.11-0.151
file NOHASH group=bin mode=0755 owner=root path=bar/foo
link path=usr/bin target=/b/bin
dir group=bin mode=0755 owner=root path=b/bin
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl
"""
                internal_dep_pth = self.make_manifest(internal_dep_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    internal_dep_pth, [self.test_proto_dir], {}, [],
                    convert=False)

                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 0, "\n".join([str(d) for d in ds]))
                self.assertEqual(pkg_attrs, {})

        def test_bug_16013_internal_variants(self):
                """Test that variants are handled correctly when links are
                involved in package internal dependency resolution."""

                foo_path = self.make_proto_text_file("bar/foo",
                    "#!/usr/bin/perl\n\n")
                self.make_proto_text_file("b/bin/perl")
                internal_dep_manf = """\
set name=pkg.fmri value=pkg:/internal@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c
file NOHASH group=bin mode=0755 owner=root path=bar/foo
link path=usr/bin target=/b/bin variant.foo=a
link path=usr/bin target=/b/bin variant.foo=b
dir group=bin mode=0755 owner=root path=b/bin
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=c
"""
                internal_dep_pth = self.make_manifest(internal_dep_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    internal_dep_pth, [self.test_proto_dir], {}, [],
                    convert=False)

                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 1, "\n".join([str(d) for d in ds]))
                d = ds[0]
                self.assertEqual(d.attrs[dependencies.files_prefix], ["perl"])
                self.assertEqual(d.dep_vars.not_sat_set,
                    set([frozenset([("variant.foo", "a")]),
                        frozenset([("variant.foo", "c")])]))
                self.assertEqual(d.dep_vars.sat_set,
                    set([frozenset([("variant.foo", "b")])]))
                self.assertEqual(pkg_attrs, {})

        def test_bug_16013_internal_links_and_variants(self):
                """Test that if the file doesn't exist for all package variants,
                the dependencies have the correct variant tags."""

                internal_dep_manf = """\
set name=pkg.fmri value=pkg:/internal@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c value=d
file NOHASH group=bin mode=0755 owner=root path=bar/foo variant.foo=a
file NOHASH group=bin mode=0755 owner=root path=bar/foo variant.foo=b
file NOHASH group=bin mode=0755 owner=root path=bar/foo variant.foo=c
link path=usr/bin target=/b/bin variant.foo=a
link path=usr/bin target=/b/bin variant.foo=b
link path=usr/bin target=/b/bin variant.foo=d
dir group=bin mode=0755 owner=root path=b/bin
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=c
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=d
"""
                self.make_proto_text_file("b/bin/perl")
                foo_path = self.make_proto_text_file("bar/foo",
                    "#!/usr/bin/perl\n\n")
                internal_dep_pth = self.make_manifest(internal_dep_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    internal_dep_pth, [self.test_proto_dir], {}, [],
                    convert=False)

                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 2,
                    "\n" + "\n".join([str(d) for d in ds]))
                res_not_sat_set = set([frozenset([("variant.foo", "a")]),
                    frozenset([("variant.foo", "c")])])
                for d in ds:
                        self.assertEqual(d.attrs[dependencies.files_prefix],
                            ["perl"])
                        self.assertEqual(len(d.dep_vars.not_sat_set), 1)
                        self.assertTrue(d.dep_vars.not_sat_set.issubset(
                            res_not_sat_set))
                        for t in d.dep_vars.not_sat_set:
                                res_not_sat_set.remove(t)
                        self.assertEqual(d.dep_vars.sat_set, set())
                self.assertEqual(res_not_sat_set, set())
                self.assertEqual(pkg_attrs, {})

        def test_bug_16013_two_d_internal(self):
                """Check that two dimensions of variants produce the expected
                results when resolving dependends internally to a package."""

                internal_dep_manf = """\
set name=pkg.fmri value=pkg:/internal@0.5.11,5.11-0.151
set name=variant.foo value=a value=b value=c value=d
set name=variant.bar value=x value=y value=z
file NOHASH group=bin mode=0755 owner=root path=bar/foo
link path=usr/bin target=/b/bin variant.foo=a
link path=usr/bin target=/b/bin variant.foo=b
link path=usr/bin target=/b/bin variant.foo=d variant.bar=x
link path=usr/bin target=/b/bin variant.foo=d variant.bar=y
dir group=bin mode=0755 owner=root path=b/bin
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=b
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=c
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=d variant.bar=y
file NOHASH group=bin mode=0555 owner=root path=b/bin/perl variant.foo=d variant.bar=z
"""
                self.make_proto_text_file("b/bin/perl")
                foo_path = self.make_proto_text_file("bar/foo",
                    "#!/usr/bin/perl\n\n")
                internal_dep_pth = self.make_manifest(internal_dep_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    internal_dep_pth, [self.test_proto_dir], {}, [],
                    convert=False)

                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 1, "\n".join([str(d) for d in ds]))
                d = ds[0]
                self.assertEqual(d.attrs[dependencies.files_prefix], ["perl"])
                not_sat_set = set([
                    frozenset([("variant.foo", "a")]),
                    frozenset([("variant.foo", "c")]),
                    frozenset([("variant.foo", "d"), ("variant.bar", "x")]),
                    frozenset([("variant.foo", "d"), ("variant.bar", "z")]),
                ])

                self.assertEqual(not_sat_set, d.dep_vars.not_sat_set)
                self.assertEqual(set([
                    frozenset([("variant.foo", "b")]),
                    frozenset([("variant.foo", "d"), ("variant.bar", "y")])
                ]), d.dep_vars.sat_set)
                self.assertEqual(pkg_attrs, {})

        def test_bug_16808(self):
                """Test that if an action uses a variant not declared at the
                package level, an error is reported."""

                tp = self.make_manifest(self.bug_16808_manf)
                self.make_proto_text_file("var/log/syslog", "text")
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp),
                    exit=1)
                self.check_res(self.bug_16808_error, self.errout)

        def test_bug_17808(self):
                """Test that a 64-bit binary has its runpaths set to /lib/64 and
                /usr/lib/64 instead of /lib and /usr/lib."""

                self.make_elf(bit64=True, output_path="usr/bin/x64")
                mp = self.make_manifest(self.test_64bit_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 1, "\n".join([str(d) for d in ds]))
                d = ds[0]
                self.assertEqual(d.attrs[DDP + ".file"], ["libc.so.1"])
                self.assertEqual(set(d.attrs[DDP + ".path"]),
                    set(["lib/64", "usr/lib/64"]))

        def test_elf_warning(self):
                """Test that if an action uses a variant not declared at the
                package level, an error is reported."""

                tp = self.make_manifest(self.test_elf_warning_manf)
                self.make_proto_text_file("etc/libc.so.1", "text")
                self.make_elf([], "usr/xpg4/lib/libcurses.so.1")
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res("", self.errout)
                self.check_res(self.res_elf_warning, self.output)

        def test_relative_run_path(self):
                """Test that a runpath containing ../ is handled correctly."""

                tp = self.make_manifest(self.test_elf_warning_manf)
                self.make_proto_text_file("etc/libc.so.1", "text")
                self.make_elf(["$ORIGIN/../../../etc/"],
                    "usr/xpg4/lib/libcurses.so.1")
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res("", self.errout)
                self.check_res("", self.output)

                dependent_manf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.151
depend fmri=__TBD pkg.debug.depend.file=libc.so.1 pkg.debug.depend.path=lib pkg.debug.depend.path=usr/lib pkg.debug.depend.path=usr/xpg4/lib/../../../etc pkg.debug.depend.reason=usr/xpg4/lib/libcurses.so.1 pkg.debug.depend.severity=warning pkg.debug.depend.type=elf type=require
"""
                dependee_manf = """\
set name=pkg.fmri value=pkg:/b@0.5.11,5.11-0.151
file NOHASH group=bin mode=0755 owner=root path=etc/libc.so.1
"""

                p1 = self.make_manifest(dependent_manf)
                p2 = self.make_manifest(dependee_manf)
                deps, errs, warnings, unused_fmris, external_deps = \
                    dependencies.resolve_deps([p1, p2], None, [],
                        prune_attrs=False)
                self.assertEqual(len(errs), 0,
                    "\n" + "\n\n".join([str(s) for s in errs]))
                self.assertEqualDiff(set(), unused_fmris)
                self.assertEqualDiff(set(), external_deps)
                self.assertEqual(len(deps[p1]), 1,
                    "\n".join([str(s) for s in deps[p1]]))
                d = deps[p1][0]
                self.assertEqual(d.attrs["fmri"], "pkg:/b@0.5.11-0.151")
                self.assertEqual(d.attrs[dependencies.type_prefix], "elf")

        def test_multiple_run_paths(self):
                """Test that specifying multiple $PKGDEPEND_RUNPATH tokens
                results in an error."""

                mf = """\
set name=pkg.fmri value=pkg:/a@0.5.11,5.11-0.160
file NOHASH group=bin mode=0755 owner=root path=etc/file.py \
    pkg.depend.runpath=$PKGDEPEND_RUNPATH:$PKGDEPEND_RUNPATH
    """
                self.make_proto_text_file(
                    "etc/file.py", "#!/usr/bin/python{0}".format(py_ver_default))
                tp = self.make_manifest(mf)
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp),
                    exit=1)
                expected = (
                    "More than one $PKGDEPEND_RUNPATH token was set on the "
                    "same action in this manifest.")
                self.check_res(expected, self.errout)
                self.check_res("", self.output)

        def test_bug_16271(self):
                """Test that scripts which reference a specific platform in the
                path to python are treated as python files which need
                dependencies analyzed."""

                self.make_proto_text_file(
                    "usr/bin/amd64/python{0}-config".format(py_ver_default),
                     self.python_amd_text)
                mp = self.make_manifest(self.python_amd_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 3, "\n".join([str(d) for d in ds]))
                for d in ds:
                        if d.attrs[DDP + ".type"] == "script":
                                self.assertEqual(d.attrs[DDP + ".file"],
                                    ["python{0}".format(py_ver_default)])
                                self.assertEqual(d.attrs[DDP + ".path"],
                                    ["usr/bin/amd64"])
                                continue
                        self.assertEqual(d.attrs[DDP + ".type"], "python")

                self.make_proto_text_file(
                    "usr/bin/sparcv9/python{0}-config".format(py_ver_default),
                    self.python_amd_text)
                mp = self.make_manifest(self.python_sparcv9_manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    mp, [self.test_proto_dir], {}, [], convert=False)
                self.assertEqual(len(es), 0, "\n".join([str(d) for d in es]))
                self.assertEqual(len(ds), 3, "\n".join([str(d) for d in ds]))
                for d in ds:
                        if d.attrs[DDP + ".type"] == "script":
                                self.assertEqual(d.attrs[DDP + ".file"],
                                    ["python{0}".format(py_ver_default)])
                                self.assertEqual(d.attrs[DDP + ".path"],
                                    ["usr/bin/amd64"])
                                continue
                        self.assertEqual(d.attrs[DDP + ".type"], "python")

        def test_bug_18011(self):
                """Test that a missing file delivers a helpful error message."""

                mp = self.make_manifest(self.python_amd_manf)
                foo_dir = os.path.join(self.test_proto_dir, "foo")
                bar_dir = os.path.join(self.test_proto_dir, "bar")
                os.makedirs(foo_dir)
                os.makedirs(bar_dir)
                self.pkgdepend_generate("-d {0} -d {1} -d {2} {3}".format(
                    self.test_proto_dir,foo_dir, bar_dir, mp), exit=1)
                self.assertEqual("Couldn't find "
                    "'usr/bin/amd64/python{0}-config' in any of the specified "
                    "search directories:\n{1}\n".format(py_ver_default, "\n".join(
                    "\t" + d for d in sorted(
                        [foo_dir, bar_dir, self.test_proto_dir]))),
                    self.errout)

        def test_bug_18101(self):
                """Test that importing os.path in a file using the system python
                results in the right set of dependencies."""

                # Set up the files for generate.
                fp = "usr/lib/python{0}/vendor-packages/pkg/client/indexer.py".format(
                    py_ver_default)
                self.make_proto_text_file(fp, self.pyver_python_text.format(
                    py_ver_default))
                mp = self.make_manifest(self.pyver_test_manf_1_non_ex.format(
                    py_ver=py_ver_default))

                # Run generate and check the output.
                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, mp))
                self.check_res(
                    self.make_pyver_python_res(py_ver_default,
                        pkg5unittest.g_proto_area, fp, include_os=True).format(
                        bin_ver=py_ver_default),
                    self.output)
                self.check_res("", self.errout)

        def test_bug_19029(self):
                """Test that a package with an action which doesn't validate
                causes pkgdepend generate to fail."""

                manf = """
set name=pkg.fmri value=bug_18019@1.0,5.11-1
depend fmri=pkg:/a@0,5.11-1 type=conditional
"""
                manf_path = self.make_manifest(manf)
                ds, es, ms, pkg_attrs = dependencies.list_implicit_deps(
                    manf_path, [self.test_proto_dir], {}, [],
                    convert=False)
                self.assertEqual(len(es), 1)
                self.assertTrue(isinstance(es[0],
                    actions.InvalidActionAttributesError))

        def test_python_combinations(self):
                """Test that each line in the following table is accounted for
                by a test case.

                There are three conditions which determine whether python
                dependency analysis is performed on a file with python in its
                #! line.
                1) Is the file executable.
                    (Represented in the table below by X)
                2) Is the file installed into a directory which provides
                    information about what version of python should be used
                    for it.
                    (Represented by D)
                3) Does the first line of the file include a specific version
                    of python.
                    (Represented by F)

                Conditions || Perform Analysis
                 X  D  F   || Y, if F and D disagree, display a warning in the
                           ||     output and use D to analyze the file.
                 X  D !F   || Y
                 X !D  F   || Y
                 X !D !F   || N, and display a warning in the output.
                !X  D  F   || Y
                !X  D !F   || Y
                !X !D  F   || N
                !X !D !F   || N
                """

                # The test for line 1 with matching versions is done by
                # test_bug_13059.

                # Test line 1 (X D F) with mismatched versions.
                tp = self.make_manifest(self.pyver_test_manf_1.format(
                    py_ver=py_ver_other))
                fp = "usr/lib/python{0}/vendor-packages/pkg/client/indexer.py".format(
                    py_ver_other)
                self.make_proto_text_file(fp, self.pyver_python_text.format(
                    py_ver_default))
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp),
                     exit=1)
                self.check_res(self.pyver_mismatch_results +
                    self.make_pyver_python_res(py_ver_other, self.test_proto_dir, fp,
                        include_os=True).format(bin_ver=py_ver_default),
                    self.output)
                self.check_res(self.pyver_mismatch_errs.format(self.test_proto_dir),
                    self.errout)

                # Test line 2 (X D !F)
                tp = self.make_manifest(self.pyver_test_manf_1.format(
                    py_ver=py_ver_other))
                fp = "usr/lib/python{0}/vendor-packages/pkg/client/indexer.py".format(
                    py_ver_other)
                self.make_proto_text_file(fp, self.pyver_python_text.format(""))
                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(
                    self.pyver_res_full_manf_1(py_ver_other, self.test_proto_dir, fp,
                        include_os=True).format(
                        reason=fp, bin_ver="", run_path=""),
                    self.output)
                self.check_res("", self.errout)

                # Test line 3 (X !D F)
                tp = self.make_manifest(self.py_in_usr_bin_manf)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text.format(
                    py_ver_other))
                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(
                    self.pyver_res_full_manf_1(py_ver_other, self.test_proto_dir, fp,
                        include_os=True).format(
                        reason=fp, bin_ver=py_ver_other, run_path=""),
                    self.output)
                self.check_res("", self.errout)

                # Test line 4 (X !D !F)
                tp = self.make_manifest(self.py_in_usr_bin_manf)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text.format(""))
                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp), exit=1)
                self.check_res(
                    self.pyver_other_script_full_manf_1.format(
                        reason=fp, bin_ver="", run_path=""),
                    self.output)
                self.check_res(self.pyver_unspecified_ver_err.format(
                    self.test_proto_dir), self.errout)

                # Test line 5 (!X D F)
                tp = self.make_manifest(self.pyver_test_manf_1_non_ex.format(
                    py_ver=py_ver_other))
                fp = "usr/lib/python{0}/vendor-packages/pkg/client/indexer.py".format(
                    py_ver_other)
                self.make_proto_text_file(fp, self.pyver_python_text.format(py_ver_default))
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res(
                    self.make_pyver_python_res(py_ver_other, self.test_proto_dir, fp,
                        include_os=True),
                    self.output)
                self.check_res("", self.errout)

                # Test line 6 (!X D !F)
                tp = self.make_manifest(self.pyver_test_manf_1_non_ex.format(
                    py_ver=py_ver_other))
                fp = "usr/lib/python{0}/vendor-packages/pkg/client/indexer.py".format(
                    py_ver_other)
                self.make_proto_text_file(fp, self.pyver_python_text.format(""))
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res(
                    self.make_pyver_python_res(py_ver_other, self.test_proto_dir, fp,
                        include_os=True),
                    self.output)
                self.check_res("", self.errout)

                # Test line 7 (!X !D F)
                tp = self.make_manifest(self.py_in_usr_bin_manf_non_ex)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text.format(py_ver_other))
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res("", self.output)
                self.check_res("", self.errout)

                # Test line 8 (!X !D !F)
                tp = self.make_manifest(self.py_in_usr_bin_manf_non_ex)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text.format(""))
                self.pkgdepend_generate("-d {0} {1}".format(self.test_proto_dir, tp))
                self.check_res("", self.output)
                self.check_res("", self.errout)

        def test_bug_13059(self):
                """Test that python modules written for a version of python
                other than the current system version are analyzed correctly."""

                # Set up the files for generate.
                tp = self.make_manifest(
                    self.pyver_test_manf_1.format(py_ver=py_ver_other))
                fp = "usr/lib/python{0}/vendor-packages/pkg/" \
                    "client/indexer.py".format(py_ver_other)
                self.make_proto_text_file(fp, self.python_text)

                # Run generate and check the output.
                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(
                    self.pyver_res_full_manf_1(py_ver_other,
                        self.test_proto_dir, fp).format(
                        bin_ver="", reason=fp, run_path=""),
                    self.output)
                self.check_res("", self.errout)

                # Take the output from the run and make it a file
                # for the resolver to use.
                dependency_mp = self.make_manifest(self.output)
                provider_mp = self.make_manifest(
                    self.pyver_resolve_dep_manf.format(py_ver=py_ver_other))

                # Run resolver and check the output.
                self.pkgdepend_resolve(
                    "-v {0} {1}".format(dependency_mp, provider_mp))
                self.check_res("", self.output)
                self.check_res("", self.errout)
                dependency_res_p = dependency_mp + ".res"
                provider_res_p = provider_mp + ".res"
                lines = self.__read_file(dependency_res_p)
                self.check_res(self.make_pyver_resolve_results(
                    pkg5unittest.g_proto_area).format(
                        res_manf=os.path.basename(provider_mp),
                        pfx=base.Dependency.DEPEND_DEBUG_PREFIX,
                        py_ver=py_ver_other,
                        reason=fp
                    ), lines)
                lines = self.__read_file(provider_res_p)
                self.check_res("", lines)

                # Clean up
                portable.remove(dependency_res_p)
                portable.remove(provider_res_p)

                # Now test that generating dependencies when runpaths
                # have been set works.
                tp = self.make_manifest(
                    self.pyver_test_manf_1_run_path.format(py_ver=py_ver_other))
                fp = "usr/lib/python{0}/vendor-packages/pkg/" \
                    "client/indexer.py".format(py_ver_other)
                self.make_proto_text_file(fp, self.python_text)

                # Run generate and check the output.
                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res(
                    self.pyver_res_full_manf_1(py_ver_other,
                        self.test_proto_dir, fp).format(
                            bin_ver="",
                            reason=fp,
                            run_path=\
                                "pkg.depend.runpath=$PKGDEPEND_RUNPATH"),
                    self.output)
                self.check_res("", self.errout)

        def test_PEP_3149(self):
                """Test that Python 3 modules importing native modules can find
                them in the right place, following PEP 3149.

                On Solaris, this means 64-bit only, and with the "m" (pymalloc)
                flag turned on.
                """

                # Create a python 3.x file that imports a native module.
                tp = self.make_manifest(
                    self.pyver_test_manf_1.format(py_ver="3.4"))
                fp = "usr/lib/python{0}/vendor-packages/pkg/" \
                    "client/indexer.py".format("3.4")
                self.make_proto_text_file(fp, self.python3_so_text)

                # Run generate
                self.pkgdepend_generate("-m -d {0} {1}".format(
                    self.test_proto_dir, tp))

                # Take the output, split it into actions, and find exactly one
                # action which generated a correct dependency on zlib based on
                # indexer.py.
                pfx = base.Dependency.DEPEND_DEBUG_PREFIX
                acts = [
                    a
                    for a in (
                        actions.fromstr(l)
                        for l in self.output.strip().splitlines()
                    )
                    if a.attrs.get(pfx + ".reason") == fp and
                        "64/zlib.cpython-34m.so" in a.attrs[pfx + ".file"]
                ]
                self.assertTrue(len(acts) == 1)

                self.check_res("", self.errout)

        def test_bypass_full_paths(self):
                """Test that when a match between the full paths of a dependency
                and something specified in the pkg.depend.bypass-generate is
                found, pkgdepend ignores the dependency as expected.
                """

                tp = self.make_manifest(self.test_bypass_manf)
                self.make_elf([], "usr/xpg4/lib/libcurses.so.1")
                self.pkgdepend_generate("-d {0} {1}".format(
                    self.test_proto_dir, tp))
                self.check_res("", self.errout)
                self.check_res(self.res_bypass, self.output)

if __name__ == "__main__":
        unittest.main()
