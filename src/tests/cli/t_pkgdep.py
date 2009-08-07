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
import tempfile
import unittest

import pkg.flavor.base as base

class TestPkgdepBasics(testutils.SingleDepotTestCase):
        persistent_depot = True

        test_manf_1 = """
hardlink path=baz target=var/log/authlog
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 variant.arch=foo
"""
        test_manf_2 = """
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 variant.arch=foo
file NOHASH group=bin mode=0755 owner=root path=etc/pam.conf
"""

        int_hardlink_manf = """ \
hardlink path=usr/foo target=../var/log/syslog
file NOHASH group=sys mode=0644 owner=root path=var/log/syslog 
"""

        kernmod_manf = """ \
file NOHASH group=sys mode=0755 owner=root path=usr/kernel/drv/fssnap
"""

        res_manf_1 = """\
depend %(depend_debug_prefix)s.file=usr/bin/python2.4 fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=var/log/authlog fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=baz %(depend_debug_prefix)s.type=hardlink
""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

        res_full_manf_1 = """\
hardlink path=baz target=var/log/authlog
file NOHASH group=bin mode=0755 owner=root path=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py
file NOHASH group=bin mode=0755 owner=root path=usr/xpg4/lib/libcurses.so.1 variant.arch=foo
depend %(depend_debug_prefix)s.file=usr/bin/python2.4 fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=script
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/__init__.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/indexer.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/misc.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
depend %(depend_debug_prefix)s.file=usr/lib/python2.4/vendor-packages/pkg/search_storage.py fmri=%(dummy_fmri)s type=require %(depend_debug_prefix)s.reason=usr/lib/python2.4/vendor-packages/pkg/client/indexer.py %(depend_debug_prefix)s.type=python
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

        res_kernmod_manf = """\
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=fs/ufs %(depend_debug_prefix)s.path=kernel %(depend_debug_prefix)s.path=usr/kernel %(depend_debug_prefix)s.reason=usr/kernel/drv/fssnap %(depend_debug_prefix)s.type=elf type=require
depend fmri=%(dummy_fmri)s %(depend_debug_prefix)s.file=misc/fssnap_if %(depend_debug_prefix)s.path=kernel %(depend_debug_prefix)s.path=usr/kernel %(depend_debug_prefix)s.reason=usr/kernel/drv/fssnap %(depend_debug_prefix)s.type=elf type=require""" % {"depend_debug_prefix":base.Dependency.DEPEND_DEBUG_PREFIX, "dummy_fmri":base.Dependency.DUMMY_FMRI}

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
                                if len(x_tmp) == len(y_tmp) and \
                                    x_tmp[0] == y_tmp[0] and \
                                    set(x_tmp) == set(y_tmp):
                                        found = True
                                        break
                        if not found:
                                res.add(x)
                return res


        def check_res(self, expected, seen):
                import sys
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
                """Ensure that arguments don't cause a traceback."""

                self.pkgdep("", exit=2)
                self.pkgdep("foo", proto="", exit=2)
                self.pkgdep("-z foo bar", exit=2)
                self.pkgdep("", exit=2)
                self.pkgdep("no_such_file_should_exist", exit=1)
                self.pkgdep("-?")
                self.pkgdep("--help")

        def test_output(self):
                """Check that the output is in the format expected."""

                tp = self.make_manifest(self.test_manf_1)
                
                self.pkgdep(tp, exit=1)
                self.check_res(self.res_manf_1, self.output)
                self.check_res(self.err_manf_1, self.errout)

                self.pkgdep("-M %s" % tp, exit=1)
                self.check_res(self.res_full_manf_1, self.output)
                self.check_res(self.err_manf_1, self.errout)

                tp = self.make_manifest(self.test_manf_2)
                
                self.pkgdep(tp, proto="/")
                self.check_res(self.res_manf_2, self.output)
                self.check_res("", self.errout)

                self.pkgdep("-m %s" % tp, proto="/")
                self.check_res(self.res_manf_2, self.output)
                self.check_res(self.res_manf_2_missing, self.errout)

                tp = self.make_manifest(self.int_hardlink_manf)
                
                self.pkgdep(tp, proto="/")
                self.check_res("", self.output)
                self.check_res("", self.errout)

                self.pkgdep("-I %s" % tp, proto="/")
                self.check_res(self.res_int_manf, self.output)
                self.check_res("", self.errout)

                tp = self.make_manifest(self.kernmod_manf)
                
                self.pkgdep(tp, proto="/")
                self.check_res(self.res_kernmod_manf, self.output)
                self.check_res("", self.errout)
