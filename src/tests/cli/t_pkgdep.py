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
import pkg5unittest

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import pkg.flavor.base as base
import pkg.flavor.depthlimitedmf as mf
import pkg.portable as portable

class TestPkgdepBasics(pkg5unittest.SingleDepotTestCase):

        test_manf_1 = """\
hardlink path=baz target=var/log/authlog
file NOHASH group=bin mode=0755 owner=root \
path=usr/lib/python2.6/v\
endor-packages/pkg/client/indexer.py
file NOHA\
SH group=bin mode=0755 owner=root path=u\
sr/xpg4/lib/libcurses.so.1
"""
        test_manf_2 = """\
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=etc/pam.conf
"""

        int_hardlink_manf = """\
hardlink path=usr/foo target=../var/log/syslog
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog
"""

        resolve_dep_manf = """\
file NOHASH group=sys mode=0600 owner=root path=var/log/authlog preserve=true
"""

        payload_manf = """\
hardlink path=usr/baz target=lib/python2.6/foo/bar.py
file usr/lib/python2.6/vendor-packages/pkg/client/indexer.py \
group=bin mode=0755 owner=root path=usr/lib/python2.6/foo/bar.py
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

        def get_ver_paths(self, ver, proto):
                """To determine what the correct results should be for several
                tests, it's necessary to discover what the sys.path is for the
                version of python the test uses."""

                cur_ver = "%s.%s" % sys.version_info[0:2]
                if cur_ver == ver:
                        # Add the directory from which pkgdepend will be run.
                        res =  [os.path.join(proto, "usr","bin")]
                        # Remove any paths that start with the defined python
                        # paths.
                        res.extend(
                            sorted(set([
                            fp for fp in sys.path
                            if not mf.DepthLimitedModuleFinder.startswith_path(
                                fp, self.py_path)
                            ])))
                        return res

                sp = subprocess.Popen(
                    "python%s -c 'import sys; print sys.path'" % ver,
                    shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = sp.communicate()
                if err:
                        raise RuntimeError("Error running python%s:%s" %
                            (ver, err))
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
        def __make_paths(added, paths):
                """ Append a dependency path for "added" to each of
                the paths in the list "paths" """

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
                    "type=require %(pfx)s.reason=%(reason)s "
                    "%(pfx)s.type=script\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=authlog "
                    "%(pfx)s.path=var/log "
                    "type=require %(pfx)s.reason=baz "
                    "%(pfx)s.type=hardlink\n" +
                    self.make_pyver_python_res("2.6", proto_area)) % {
                    "pfx": base.Dependency.DEPEND_DEBUG_PREFIX,
                    "dummy_fmri": base.Dependency.DUMMY_FMRI,
                    "reason": "%(reason)s"
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
%(manf_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=usr/xpg4/lib/libcurses.so.1 %(pfx)s.type=elf type=require' under the following combinations of variants:
variant.arch:foo
"""

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
                    "%(pfx)s.file=python "
                    "%(pfx)s.path=usr/bin "
                    "%(pfx)s.reason=%(reason)s "
                    "%(pfx)s.type=script type=require\n" +
                    self.make_pyver_python_res("2.6", proto_area)) % {
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI,
                        "reason": "%(reason)s"
                    }

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

        two_v_deps_verbose_output = """\
%(m1_path)s
depend fmri=pkg:/s-v-bar pkg.debug.depend.file=var/log/authlog pkg.debug.depend.file=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/s-v-baz-one pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=two


%(m2_path)s



%(m3_path)s



%(m4_path)s



"""

        two_v_deps_output = """\
%(m1_path)s
depend fmri=pkg:/s-v-bar type=require
depend fmri=pkg:/s-v-baz-one type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two type=require variant.foo=baz variant.num=two


%(m2_path)s



%(m3_path)s



%(m4_path)s


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
set name=fmri value=pkg:/dup-prov
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/f1
file NOHASH group=sys mode=0600 owner=root path=var/log/f2
"""

        subset_prov = """
set name=fmri value=pkg:/subset-prov
set name=variant.foo value=bar value=baz
set name=variant.num value=one value=two value=three
file NOHASH group=sys mode=0600 owner=root path=var/log/f5
file NOHASH group=sys mode=0600 owner=root path=var/log/f6
"""

        sep_vars = """
set name=fmri value=pkg:/sep_vars
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
depend fmri=pkg:/dup-prov pkg.debug.depend.file=var/log/f2 pkg.debug.depend.file=var/log/f1 pkg.debug.depend.reason=b1 pkg.debug.depend.reason=b2 pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/s-v-bar pkg.debug.depend.file=var/log/authlog pkg.debug.depend.file=var/log/file2 pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require
depend fmri=pkg:/s-v-baz-one pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=one
depend fmri=pkg:/s-v-baz-two pkg.debug.depend.file=var/log/authlog pkg.debug.depend.reason=baz pkg.debug.depend.type=hardlink type=require variant.foo=baz variant.num=two
depend fmri=pkg:/sep_vars pkg.debug.depend.file=var/log/f3 pkg.debug.depend.reason=b3 pkg.debug.depend.type=hardlink type=require variant.foo=bar
depend fmri=pkg:/sep_vars pkg.debug.depend.file=var/log/f4 pkg.debug.depend.reason=b3 pkg.debug.depend.type=hardlink type=require variant.foo=baz
depend fmri=pkg:/subset-prov pkg.debug.depend.file=var/log/f6 pkg.debug.depend.file=var/log/f5 pkg.debug.depend.reason=b5 pkg.debug.depend.type=hardlink type=require
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

        #
        # You may wonder why libc.so.1 is here as a dependency-- it's an
        # artifact of the way we compile our dummy module, and serves as
        # a "something to depend on".  In this way, the sample elf file
        # depends on libc.so.1 in the same way that a kernel module might
        # depend on another kernel module.
        #
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
%(proto_dir)s/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path: /platform/$PLATFORM/foo.  It is not currently possible to automatically expand this token. Please specify its value on the command line.
%(proto_dir)s/elf_test (which will be installed at bar/foo) had this token, $PLATFORM, in its run path: /isadir/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line."""

        double_plat_stdout = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=libc.so.1 %(pfx)s.path=lib %(pfx)s.path=usr/lib %(pfx)s.reason=bar/foo %(pfx)s.type=elf type=require\
""" % {
    "pfx":base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri":base.Dependency.DUMMY_FMRI
}

        double_plat_isa_error = """\
%(proto_dir)s/elf_test (which will be installed at bar/foo) had this token, $ISALIST, in its run path: /$ISALIST/$PLATFORM/baz.  It is not currently possible to automatically expand this token. Please specify its value on the command line.\
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
        pkgdepend [options] resolve [-dmosv] manifest ...

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

        py_in_usr_bin_manf = """\
file NOHASH group=bin mode=0755 owner=root path=usr/bin/pkg \
"""

        py_in_usr_bin_manf_non_ex = """\
file NOHASH group=bin mode=0644 owner=root path=usr/bin/pkg \
"""

        # The #! line has lots of spaces to test for bug 14632.
        pyver_python_text = """\
#!                  /usr/bin/python%s     -S    

import pkg.indexer as indexer
import pkg.search_storage as ss
from pkg.misc import EmptyI
"""

        pyver_test_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python%(py_ver)s/vendor-packages/pkg/client/indexer.py \
"""

        pyver_test_manf_1_non_ex = """\
file NOHASH group=bin mode=0644 owner=root path=usr/lib/python%(py_ver)s/vendor-packages/pkg/client/indexer.py \
"""
        def make_pyver_python_res(self, ver, proto_area=None):
                """Create the python dependency results with paths expected for
                the pyver tests.

                Because the paths that should be found depend both on the
                version of python and what is found by the site module, it's
                necessary to make the results depend on the sys.path that's
                discovered.
                """
                vp = self.get_ver_paths(ver, proto_area)
                self.debug("ver_paths is %s" % vp)
                pkg_path = self.__make_paths("pkg", vp)
                return ("depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=indexer.py "
                    "%(pfx)s.file=indexer.pyc "
                    "%(pfx)s.file=indexer.pyo "
                    "%(pfx)s.file=indexer/__init__.py " +
                    pkg_path +
                    " %(pfx)s.reason=%(reason)s "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=misc.py "
                    "%(pfx)s.file=misc.pyc "
                    "%(pfx)s.file=misc.pyo "
                    "%(pfx)s.file=misc/__init__.py " +
                    pkg_path +
                    " %(pfx)s.reason=%(reason)s "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=pkg/__init__.py " +
                    self.__make_paths("", vp) +
                    " %(pfx)s.reason=%(reason)s "
                    "%(pfx)s.type=python type=require\n"

                    "depend fmri=%(dummy_fmri)s "
                    "%(pfx)s.file=search_storage.py "
                    "%(pfx)s.file=search_storage.pyc "
                    "%(pfx)s.file=search_storage.pyo "
                    "%(pfx)s.file=search_storage/__init__.py " +
                    pkg_path +
                    " %(pfx)s.reason=%(reason)s "
                    "%(pfx)s.type=python type=require\n") % {
                    "pfx": base.Dependency.DEPEND_DEBUG_PREFIX,
                    "dummy_fmri": base.Dependency.DUMMY_FMRI,
                    "reason": "%(reason)s"
               }

        pyver_24_script_full_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path=%(reason)s
depend fmri=%(dummy_fmri)s %(pfx)s.file=python%(bin_ver)s %(pfx)s.path=usr/bin %(pfx)s.reason=%(reason)s %(pfx)s.type=script type=require
""" % {
    "pfx": base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri": base.Dependency.DUMMY_FMRI,
    "reason": "%(reason)s",
    "bin_ver": "%(bin_ver)s"
}

        pyver_25_script_full_manf_1 = """\
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.5/vendor-packages/pkg/client/indexer.py
depend fmri=%(dummy_fmri)s %(pfx)s.file=python %(pfx)s.path=usr/bin %(pfx)s.reason=usr/lib/python2.5/vendor-packages/pkg/client/indexer.py %(pfx)s.type=script type=require
""" % {
    "pfx": base.Dependency.DEPEND_DEBUG_PREFIX,
    "dummy_fmri": base.Dependency.DUMMY_FMRI
}

        def pyver_res_full_manf_1(self, ver, proto):
                """Build the full manifest results for the pyver tests."""

                if ver == "2.4":
                        tmp = self.pyver_24_script_full_manf_1
                else:
                        tmp = self.pyver_25_script_full_manf_1
                return tmp + self.make_pyver_python_res(ver, proto)

        pyver_resolve_dep_manf = """
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python%(py_ver)s/vendor-packages/pkg/indexer.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python%(py_ver)s/vendor-packages/pkg/__init__.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python%(py_ver)s/lib-tk/pkg/search_storage.py
file NOHASH group=bin mode=0444 owner=root path=usr/lib/python%(py_ver)s/vendor-packages/pkg/misc.py
file NOHASH group=bin mode=0755 owner=root path=usr/bin/python
"""

        pyver_resolve_results = """
depend fmri=pkg:/%(res_manf)s %(pfx)s.file=usr/lib/python%(py_ver)s/vendor-packages/pkg/indexer.py %(pfx)s.file=usr/lib/python%(py_ver)s/vendor-packages/pkg/misc.py %(pfx)s.file=usr/lib/python%(py_ver)s/vendor-packages/pkg/__init__.py %(pfx)s.file=usr/bin/python %(pfx)s.file=usr/lib/python%(py_ver)s/lib-tk/pkg/search_storage.py %(pfx)s.reason=usr/lib/python%(py_ver)s/vendor-packages/pkg/client/indexer.py %(pfx)s.type=script %(pfx)s.type=python type=require
"""

        pyver_mismatch_results = """\
depend fmri=%(dummy_fmri)s %(pfx)s.file=python2.6 %(pfx)s.path=usr/bin %(pfx)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(pfx)s.type=script type=require
""" % {"pfx":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        pyver_mismatch_errs = """
The file to be installed at usr/lib/python2.4/vendor-packages/pkg/client/indexer.py declares a python version of 2.6.  However, the path suggests that the version should be 2.4.  The text of the file can be found at %s/usr/lib/python2.4/vendor-packages/pkg/client/indexer.py
"""

        pyver_unspecified_ver_err = """
The file to be installed in usr/bin/pkg does not specify a specific version of python either in its installed path nor in its text.  Such a file cannot be analyzed for dependencies since the version of python it will be used with is unknown.  The text of the file is here: %s/usr/bin/pkg.
"""

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                #
                # To test pkgdepend resolve properly, we need an image.
                # Side by side with the image, we create a testing proto area.
                #
                self.image_create(self.dc.get_depot_url())

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
                fh = open(file_path, "rb")
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

        def make_elf(self, run_paths=[], output_path="elf_test"):
                out_file = os.path.join(self.test_proto_dir, output_path)

                # Make sure to quote the runpaths, as they may contain tokens
                # like $PLATFORM which we do not want the shell to evaluate.
                self.c_compile("int main(){}\n",
                    ["-R'%s'" % rp for rp in run_paths], out_file)

                return out_file[len(self.test_proto_dir)+1:]

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

                proto = pkg5unittest.g_proto_area
                self.pkgdepend_generate("", proto=proto, exit=2)
                self.pkgdepend_generate("foo", proto="", exit=2)
                self.pkgdepend_generate("-z foo bar", proto=proto, exit=2)
                self.pkgdepend_generate("no_such_file_should_exist",
                    proto=proto, exit=2)
                self.pkgdepend_generate("-\?", proto="")
                self.pkgdepend_generate("--help", proto="")

        def test_output(self):
                """Check that the output is in the format expected."""

                tp = self.make_manifest(self.test_manf_1)
                fp = "usr/lib/python2.6/vendor-packages/pkg/client/indexer.py"

                self.pkgdepend_generate("%s" % tp,
                    proto=pkg5unittest.g_proto_area, exit=1)
                self.check_res(self.make_res_manf_1(
                        pkg5unittest.g_proto_area) % {"reason": fp},
                    self.output)
                self.check_res(self.err_manf_1 % pkg5unittest.g_proto_area,
                    self.errout)

                self.pkgdepend_generate("-m %s" % tp,
                    proto=pkg5unittest.g_proto_area, exit=1)
                self.check_res(
                    self.make_full_res_manf_1(
                        pkg5unittest.g_proto_area) % {"reason": fp},
                    self.output)
                self.check_res(self.err_manf_1 % pkg5unittest.g_proto_area,
                    self.errout)

                self.make_proto_text_file(fp, self.python_text)
                self.make_elf([], "usr/xpg4/lib/libcurses.so.1")

                self.pkgdepend_generate("-m %s" % tp, proto=self.test_proto_dir)
                self.check_res(
                    self.make_full_res_manf_1_mod_proto(
                        pkg5unittest.g_proto_area)  % {"reason": fp},
                    self.output)
                self.check_res("", self.errout)

                tp = self.make_manifest(self.test_manf_2)
                self.make_proto_text_file("etc/pam.conf", "text")

                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir)
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                res_path = self.make_manifest(self.output)

                self.pkgdepend_resolve("-o %s" % res_path, exit=1)
                self.check_res("%s" % res_path, self.output)
                self.check_res(self.resolve_error % {
                        "manf_path": res_path,
                        "pfx":
                            base.Dependency.DEPEND_DEBUG_PREFIX,
                        "dummy_fmri":base.Dependency.DUMMY_FMRI
                    }, self.errout)

                self.pkgdepend_generate("-M %s" % tp, proto=self.test_proto_dir)
                self.check_res(self.res_manf_2, self.output)
                self.check_res(self.res_manf_2_missing, self.errout)

                portable.remove(tp)
                portable.remove(res_path)

                tp = self.make_manifest(self.int_hardlink_manf)

                self.make_proto_text_file("var/log/syslog", "text")

                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir)
                self.check_res("", self.output)
                self.check_res("", self.errout)

                self.pkgdepend_generate("-I %s" % tp, proto=self.test_proto_dir)
                self.check_res(self.res_int_manf, self.output)
                self.check_res("", self.errout)

                portable.remove(tp)

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
                tp = self.make_manifest(self.pyver_test_manf_1 %
                    {"py_ver":"2.4"})
                fp = "usr/lib/python2.4/vendor-packages/pkg/client/indexer.py"
                self.make_proto_text_file(fp, self.pyver_python_text % "2.6")
                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir,
                     exit=1)
                self.check_res(self.pyver_mismatch_results +
                    self.make_pyver_python_res("2.4", self.test_proto_dir) %
                        {"reason": fp, "bin_ver": "2.6"},
                    self.output)
                self.check_res(self.pyver_mismatch_errs % self.test_proto_dir,
                    self.errout)

                # Test line 2 (X D !F)
                tp = self.make_manifest(self.pyver_test_manf_1 %
                    {"py_ver":"2.4"})
                fp = "usr/lib/python2.4/vendor-packages/pkg/client/indexer.py"
                self.make_proto_text_file(fp, self.pyver_python_text % "")
                self.pkgdepend_generate("-m %s" % tp, proto=self.test_proto_dir)
                self.check_res(
                    self.pyver_res_full_manf_1("2.4", self.test_proto_dir) %
                        {"reason": fp, "bin_ver": ""},
                    self.output)
                self.check_res("", self.errout)

                # Test line 3 (X !D F)
                tp = self.make_manifest(self.py_in_usr_bin_manf)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text % "2.4")
                self.pkgdepend_generate("-m %s" % tp, proto=self.test_proto_dir)
                self.check_res(
                    self.pyver_res_full_manf_1("2.4", self.test_proto_dir) %
                        {"reason": fp, "bin_ver": "2.4"},
                    self.output)
                self.check_res("", self.errout)

                # Test line 4 (X !D !F)
                tp = self.make_manifest(self.py_in_usr_bin_manf)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text % "")
                self.pkgdepend_generate("-m %s" % tp, proto=self.test_proto_dir,
                    exit=1)
                self.check_res(
                    self.pyver_24_script_full_manf_1 %
                        {"reason": fp, "bin_ver": ""},
                    self.output)
                self.check_res(self.pyver_unspecified_ver_err % self.test_proto_dir,
                    self.errout)

                # Test line 5 (!X D F)
                tp = self.make_manifest(self.pyver_test_manf_1_non_ex %
                    {"py_ver":"2.4"})
                fp = "usr/lib/python2.4/vendor-packages/pkg/client/indexer.py"
                self.make_proto_text_file(fp, self.pyver_python_text % "2.6")
                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir)
                self.check_res(
                    self.make_pyver_python_res("2.4", self.test_proto_dir) %
                        {"reason": fp},
                    self.output)
                self.check_res("", self.errout)

                # Test line 6 (!X D !F)
                tp = self.make_manifest(self.pyver_test_manf_1_non_ex %
                    {"py_ver":"2.4"})
                fp = "usr/lib/python2.4/vendor-packages/pkg/client/indexer.py"
                self.make_proto_text_file(fp, self.pyver_python_text % "")
                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir)
                self.check_res(
                    self.make_pyver_python_res("2.4", self.test_proto_dir) %
                        {"reason": fp},
                    self.output)
                self.check_res("", self.errout)

                # Test line 7 (!X !D F)
                tp = self.make_manifest(self.py_in_usr_bin_manf_non_ex)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text % "2.4")
                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir)
                self.check_res("", self.output)
                self.check_res("", self.errout)

                # Test line 8 (!X !D !F)
                tp = self.make_manifest(self.py_in_usr_bin_manf_non_ex)
                fp = "usr/bin/pkg"
                self.make_proto_text_file(fp, self.pyver_python_text % "")
                self.pkgdepend_generate("%s" % tp, proto=self.test_proto_dir)
                self.check_res("", self.output)
                self.check_res("", self.errout)

        def test_bug_13059(self):
                """Test that python modules written for a version of python
                other than the current system version are analyzed correctly."""

                for py_ver in ["2.4", "2.5"]:

                        # Set up the files for generate.
                        tp = self.make_manifest(
                            self.pyver_test_manf_1 % {"py_ver":py_ver})
                        fp = "usr/lib/python%s/vendor-packages/pkg/" \
                            "client/indexer.py" % py_ver
                        self.make_proto_text_file(fp, self.python_text)

                        # Run generate and check the output.
                        self.pkgdepend_generate("-m %s" % tp,
                            proto=self.test_proto_dir)
                        self.check_res(
                            self.pyver_res_full_manf_1(py_ver, self.test_proto_dir) %
                                {"bin_ver": "", "reason":fp},
                            self.output)
                        self.check_res("", self.errout)

                        # Take the output from the run and make it a file
                        # for the resolver to use.
                        dependency_mp = self.make_manifest(self.output)
                        provider_mp = self.make_manifest(
                            self.pyver_resolve_dep_manf % {"py_ver":py_ver})

                        # Run resolver and check the output.
                        self.pkgdepend_resolve(
                            "-v %s %s" % (dependency_mp, provider_mp))
                        self.check_res("", self.output)
                        self.check_res("", self.errout)
                        dependency_res_p = dependency_mp + ".res"
                        provider_res_p = provider_mp + ".res"
                        lines = self.__read_file(dependency_res_p)
                        self.check_res(self.pyver_resolve_results % {
                                "res_manf": os.path.basename(provider_mp),
                                "pfx":
                                    base.Dependency.DEPEND_DEBUG_PREFIX,
                                "py_ver": py_ver,
                                "reason": fp
                            }, lines)
                        lines = self.__read_file(provider_res_p)
                        self.check_res("", lines)

                        # Clean up
                        portable.remove(dependency_res_p)
                        portable.remove(provider_res_p)

        def test_resolve_screen_out(self):
                """Check that the results printed to screen are what is
                expected."""

                m1_path = self.make_manifest(self.two_variant_deps)
                m2_path = self.make_manifest(self.two_v_deps_bar)
                m3_path = self.make_manifest(self.two_v_deps_baz_one)
                m4_path = self.make_manifest(self.two_v_deps_baz_two)
                self.pkgdepend_resolve("-o %s" %
                    " ".join([m1_path, m2_path, m3_path, m4_path]), exit=1)

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

                self.pkgdepend_resolve("-vo %s" %
                    " ".join([m1_path, m2_path, m3_path, m4_path]), exit=1)

                self.check_res(self.two_v_deps_verbose_output % {
                        "m1_path": m1_path,
                        "m2_path": m2_path,
                        "m3_path": m3_path,
                        "m4_path": m4_path
                    }, self.output)

        def test_bug_10518(self):
                """ pkgdepend should exit 2 on input args of the wrong type """
                m_path = self.make_manifest(self.test_manf_1)

                # Try feeding a directory where a manifest should be--
                # a typical scenario we play out here is a user
                # inverting the first and second args.
                self.pkgdepend_generate("/", proto=m_path, exit=2)
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

                        self.pkgdepend_resolve("-M -o %s " % m_path, exit=2)
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
                self.pkgdepend_generate("%s" % tp, proto=proto)
                self.check_res(self.make_res_payload_1(proto) %\
                        {"reason": "usr/lib/python2.6/foo/bar.py"},
                    self.output)
                self.check_res("", self.errout)

        def test_bug_11829(self):
                """ pkgdep should gracefully deal with a non-manifest """

                m_path = None
                nonsense = "This is a nonsense manifest"
                m_path = self.make_manifest(nonsense)

                self.pkgdepend_generate("%s" % m_path,
                    proto=self.test_proto_dir, exit=1)
                self.check_res('pkgdepend: Could not parse manifest ' +
                    '%s because of the following line:\n' % m_path +
                    nonsense, self.errout)

                self.pkgdepend_resolve("-o %s " % m_path, exit=1)
                self.check_res("pkgdepend: Could not parse one or "
                    "more manifests because of the following line:\n" +
                    nonsense, self.errout)

        def __run_dyn_tok_test(self, run_paths, replaced_path, dep_args):
                """Using the provided run paths, produces a elf binary with
                those paths set and checks to make sure that pkgdep run with
                the provided arguments performs the substitution correctly."""

                elf_path = self.make_elf(run_paths)
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": elf_path})
                self.pkgdepend_generate("%s %s" % (dep_args, m_path),
                    proto=self.test_proto_dir)
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
                self.pkgdepend_generate("%s" % m_path,
                    proto=self.test_proto_dir)
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout, self.output)

                self.pkgdepend_generate("-k baz -k foo/bar %s" % m_path,
                    proto=self.test_proto_dir)
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout2, self.output)

                self.debug("Test for platform substitution in kernel " \
                    "module paths. Bug 13057")

                self.pkgdepend_generate("-D PLATFORM=baz -D PLATFORM=tp %s" %
                    m_path, proto=self.test_proto_dir)
                self.check_res("", self.errout)
                self.check_res(self.kernel_manf_stdout_platform, self.output)

                self.debug("Test unexpanded token")

                rp = ["/platform/$PLATFORM/foo"]
                elf_path = self.make_elf(rp)
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": elf_path})
                self.pkgdepend_generate("%s" % m_path, proto=self.test_proto_dir,
                    exit=1)
                self.check_res((self.payload_elf_sub_error %
                    {
                        "payload_path": os.path.join(self.test_proto_dir, elf_path),
                        "installed_path": "bar/foo",
                        "tok": "$PLATFORM",
                        "rp": rp[0]
                    }), self.errout)
                self.check_res(self.payload_elf_sub_stdout %
                    {"replaced_path": ""}, self.output)

                self.check_res(self.payload_elf_sub_stdout %
                    {"replaced_path": ""}, self.output)

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
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": elf_path})
                self.pkgdepend_generate("-D ISALIST=isadir %s" % m_path,
                    proto=self.test_proto_dir, exit=1)
                self.check_res(self.double_plat_error %
                    {"proto_dir": self.test_proto_dir}, self.errout)
                self.check_res(self.double_plat_stdout, self.output)

                self.pkgdepend_generate("-D PLATFORM=pfoo %s" % m_path,
                    proto=self.test_proto_dir, exit=1)
                self.check_res(self.double_plat_isa_error %
                    {"proto_dir": self.test_proto_dir}, self.errout)
                self.check_res(self.double_plat_isa_stdout, self.output)

                self.pkgdepend_generate("-D PLATFORM=pfoo -D PLATFORM=pfoo2 "
                    "-D ISALIST=isadir -D ISALIST=isadir %s" % m_path,
                    proto=self.test_proto_dir)
                self.check_res("", self.errout)
                self.check_res(self.double_double_stdout, self.output)

        def test_bug_12816(self):
                """Test that the error produced by a missing payload action
                uses the right path."""

                m_path = self.make_manifest(self.miss_payload_manf)
                self.pkgdepend_generate("%s" % m_path,
                    proto=self.test_proto_dir, exit=1)
                self.check_res(self.miss_payload_manf_error %
                    {"path_pref":self.test_proto_dir}, self.errout)
                self.check_res("", self.output)

        def test_bug_12896(self):
                """Test that the errors that happen when multiple packages
                deliver a dependency are displayed correctly."""

                col_path = self.make_manifest(self.collision_manf)
                bar_path = self.make_manifest(self.sat_bar_libc)
                bar2_path = self.make_manifest(self.sat_bar_libc2)
                foo_path = self.make_manifest(self.sat_foo_libc)

                self.pkgdepend_resolve("-o %s %s %s" %
                    (col_path, bar_path, foo_path), exit=1)
                self.check_res("\n\n".join([col_path, bar_path, foo_path]),
                    self.output)
                self.check_res(self.run_path_errors %
                    {"unresolved_path": col_path}, self.errout)

                self.pkgdepend_resolve("-o %s %s %s" %
                    (col_path, bar_path, bar2_path), exit=1)
                self.check_res("\n\n".join([col_path, bar_path, bar2_path]),
                    self.output)
                self.check_res(self.amb_path_errors %
                    {"unresolved_path": col_path}, self.errout)

        def test_bug_14116(self):
                foo_path = self.make_proto_text_file("bar/foo", "#!perl -w\n\n")
                m_path = self.make_manifest(self.elf_sub_manf %
                    {"file_loc": "bar/foo"})
                self.pkgdepend_generate(m_path, proto=self.test_proto_dir,
                    exit=1)
                self.check_res(self.output, "")
                self.check_res(self.errout, "%s/bar/foo says it should be run "
                    "with 'perl' which is a relative path." %
                    self.test_proto_dir)

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

                self.pkgdepend_resolve(" -vm %s" % " ".join([m1_path, m2_path,
                        m3_path, m4_path, m5_path, m6_path, m7_path, m8_path]))
                fh = open(m1_path + ".res")
                res = fh.read()
                fh.close()
                self.check_res(self.dup_variant_deps_resolved, res)

                # Check that the results can be installed correctly.
                durl = self.dc.get_depot_url()
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
                self.pkgsend(durl, "publish -d %s dup-v-deps@0.1-0.2 %s" %
                    (self.test_proto_dir, m1_path + ".res"))
                self.pkgsend(durl, "publish -d %s s-v-bar@0.1-0.2 %s" %
                    (self.test_proto_dir, m2_path + ".res"))
                self.pkgsend(durl, "publish -d %s s-v-baz-one@0.1-0.2 %s" %
                    (self.test_proto_dir, m3_path + ".res"))
                self.pkgsend(durl, "publish -d %s s-v-baz-two@0.1-0.2 %s" %
                    (self.test_proto_dir, m4_path + ".res"))
                self.pkgsend(durl, "publish -d %s dup-prov@0.1-0.2 %s" %
                    (self.test_proto_dir, m5_path + ".res"))
                self.pkgsend(durl, "publish -d %s sep_vars@0.1-0.2 %s" %
                    (self.test_proto_dir, m6_path + ".res"))
                self.pkgsend(durl, "publish -d %s subset-prov@0.1-0.2 %s" %
                    (self.test_proto_dir, m7_path + ".res"))
                self.pkgsend(durl, "publish -d %s hand-dep@0.1-0.2 %s" %
                    (self.test_proto_dir, m8_path + ".res"))
                foo_vars = ["bar", "baz"]
                num_vars = ["one", "two"]
                for fv in foo_vars:
                        for nv in num_vars:
                                var_settings = "--variant variant.foo=%s " \
                                    "--variant num=%s" % (fv, nv)
                                self.image_create(durl,
                                    additional_args=var_settings)
                                self.pkg("install dup-v-deps")
                                self.image_destroy()

if __name__ == "__main__":
        unittest.main()
