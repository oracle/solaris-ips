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

        res_manf_1 = """\
depend %(depend_debug_prefix)s.file=usr/bin/python2.6 fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script
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
depend %(depend_debug_prefix)s.file=usr/bin/python2.6 fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.6/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=var/log/authlog fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        err_manf_1 = """\
Couldn't find usr/xpg4/lib/libcurses.so.1
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
depend fmri=%(py_pkg_name)s %(depend_debug_prefix)s.file=usr/bin/python2.6 %(depend_debug_prefix)s.reason=usr/lib/python2.6/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script type=require
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
depend %(depend_debug_prefix)s.file=usr/bin/python2.6 fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=foo/bar.py %(depend_debug_prefix)s.type=script
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

        two_v_deps_resolve_error = """\
%(manf_path)s has unresolved dependency 'depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=var/log/authlog %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink type=require' under the following combinations of variants:
variant.foo:baz variant.num:three
"""

        usage_msg = """\
Usage:
        pkgdep [options] command [cmd_options] [operands]

Subcommands:
        pkgdep generate [-IMm] manifest proto_dir
        pkgdep [options] resolve [-dMos] manifest ...

Options:
        -R dir
        --help or -?
Environment:
        PKG_IMAGE"""
        
        @staticmethod
        def make_manifest(str):
                t_fd, t_path = tempfile.mkstemp()
                t_fh = os.fdopen(t_fd, "w")
                t_fh.write(str)
                t_fh.close()
                return t_path

        @staticmethod
        def __compare_res(b1, b2):
                import sys
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

                self.pkgdep("generate", exit=2)
                self.pkgdep("generate foo", proto="", exit=2)
                self.pkgdep("generate -z foo bar", exit=2)
                self.pkgdep("generate no_such_file_should_exist", exit=1)
                self.pkgdep("generate -?")
                self.pkgdep("generate --help")
                
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
                
                self.pkgdep("generate %s" % tp, exit=1)
                self.check_res(self.res_manf_1, self.output)
                self.check_res(self.err_manf_1, self.errout)

                self.pkgdep("generate -m %s" % tp, exit=1)
                self.check_res(self.res_full_manf_1, self.output)
                self.check_res(self.err_manf_1, self.errout)

                self.pkgdep("generate -m %s" % tp, proto="/")
                self.check_res(self.res_full_manf_1_mod_proto, self.output)
                self.check_res("", self.errout)

                dependency_mp = self.make_manifest(self.output)
                provider_mp = self.make_manifest(self.resolve_dep_manf)

                self.pkgdep("resolve %s %s" % (dependency_mp, provider_mp),
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
                
                self.pkgdep("resolve -m -d %s %s %s" %
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

                self.pkgdep("resolve -s foo -d %s %s %s" %
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

                self.pkgdep("resolve -s .foo %s %s" %
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

                tp = self.make_manifest(self.test_manf_2)
                
                self.pkgdep("generate %s" % tp, proto="/")
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                res_path = self.make_manifest(self.output)

                self.pkgdep("resolve -o %s" %
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
                
                self.pkgdep("generate -M %s" % tp, proto="/")
                self.check_res(self.res_manf_2, self.output)
                self.check_res(self.res_manf_2_missing, self.errout)

                portable.remove(tp)
                portable.remove(res_path)

                tp = self.make_manifest(self.int_hardlink_manf)
                
                self.pkgdep("generate %s" % tp, proto="/")
                self.check_res("", self.output)
                self.check_res("", self.errout)

                self.pkgdep("generate -I %s" % tp, proto="/")
                self.check_res(self.res_int_manf, self.output)
                self.check_res("", self.errout)

                portable.remove(tp)

        def test_resolve_screen_out(self):
                """Check that the results printed to screen are what is
                expected."""
                
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
                        self.pkgdep("resolve -o %s" %
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
                finally:
                        if m1_path:
                                portable.remove(m1_path)
                        if m2_path:
                                portable.remove(m2_path)
                        if m3_path:
                                portable.remove(m3_path)
                        if m4_path:
                                portable.remove(m4_path)

        def test_bug_10518(self):

                m_path = None

                try:
                        m_path = self.make_manifest(self.test_manf_1)

                        self.pkgdep("generate / %s " % m_path,
                            use_proto=False, exit=1)
                        self.check_res(self.usage_msg, self.errout)

                        self.pkgdep("resolve -o / ", use_proto=False, exit=2)
                        self.check_res(self.usage_msg, self.errout)
                finally:
                        if m_path:
                                portable.remove(m_path)

        def test_bug_11517(self):

                m_path = None
                ill_usage = 'pkgdep: illegal global option -- M\n'
                try:
                        m_path = self.make_manifest(self.test_manf_1)

                        self.pkgdep("resolve -M -o %s " % m_path,
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

                try:
                        tp = self.make_manifest(self.payload_manf)
                        self.pkgdep("generate %s" % tp)
                        self.check_res(self.res_payload_1, self.output)
                        self.check_res("", self.errout)
                finally:
                        if tp:
                                portable.remove(tp)

        def test_bug_11829(self):

                m_path = None
                nonsense = "This is a nonsense manifest"
                try:
                        m_path = self.make_manifest(nonsense)
                        
                        self.pkgdep("generate %s /" % m_path,
                            use_proto=False, exit=1)
                        self.check_res('pkgdep: Could not parse manifest ' + 
                            '%s because of the following line:\n' % m_path +
                            nonsense, self.errout)

                        self.pkgdep("resolve -o %s " % m_path, 
                            use_proto=False, exit=1)
                        self.check_res("pkgdep: Could not parse one or more " +
                            "manifests because of the following line:\n" +
                            nonsense, self.errout)
                finally:
                        if m_path:
                                portable.remove(m_path)

