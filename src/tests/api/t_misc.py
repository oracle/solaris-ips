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

#
# Copyright (c) 2010, 2015, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import ctypes
import os
import shutil
import stat
import sys
import tempfile
import unittest

import pkg.misc as misc
import pkg.actions as action
from pkg.actions.generic import Action

class TestMisc(pkg5unittest.Pkg5TestCase):

        def testMakedirs(self):
                tmpdir = tempfile.mkdtemp()
                # make the parent directory read-write
                os.chmod(tmpdir, stat.S_IRWXU)
                fpath = os.path.join(tmpdir, "f")
                fopath = os.path.join(fpath, "o")
                foopath = os.path.join(fopath, "o")

                # make the leaf, and ONLY the leaf read-only
                act = action.fromstr("dir path={0}".format(foopath))
                act.makedirs(foopath, mode = stat.S_IREAD)

                # Now make sure the directories leading up the leaf
                # are read-write, and the leaf is readonly.
                assert(os.stat(tmpdir).st_mode & (stat.S_IREAD | stat.S_IWRITE) != 0)
                assert(os.stat(fpath).st_mode & (stat.S_IREAD | stat.S_IWRITE) != 0)
                assert(os.stat(fopath).st_mode & (stat.S_IREAD | stat.S_IWRITE) != 0)
                assert(os.stat(foopath).st_mode & stat.S_IREAD != 0)
                assert(os.stat(foopath).st_mode & stat.S_IWRITE == 0)

                # change it back to read/write so we can delete it
                os.chmod(foopath, stat.S_IRWXU)
                shutil.rmtree(tmpdir)

        def test_pub_prefix(self):
                """Verify that misc.valid_pub_prefix returns True or False as
                expected."""

                self.assertFalse(misc.valid_pub_prefix(None))
                self.assertFalse(misc.valid_pub_prefix(""))
                self.assertFalse(misc.valid_pub_prefix("!@#$%^&*(*)"))
                self.assertTrue(misc.valid_pub_prefix(
                    "a0bc.def-ghi"))

        def test_pub_url(self):
                """Verify that misc.valid_pub_url returns True or False as
                expected."""

                self.assertFalse(misc.valid_pub_url(None))
                self.assertFalse(misc.valid_pub_url(""))
                self.assertFalse(misc.valid_pub_url("!@#$%^&*(*)"))
                self.assertTrue(misc.valid_pub_url(
                    "http://pkg.opensolaris.org/dev"))

        def test_out_of_memory(self):
                """Verify that misc.out_of_memory doesn't raise an exception
                and displays the amount of memory that was in use."""

                self.assertRegexp(misc.out_of_memory(),
                    "virtual memory was in use")

        def test_psinfo(self):
                """Verify that psinfo gets us some reasonable data."""

                psinfo = misc.ProcFS.psinfo()

                # verify pids
                self.assertEqual(psinfo.pr_pid, os.getpid())
                self.assertEqual(psinfo.pr_ppid, os.getppid())

                # verify user/group ids
                self.assertEqual(psinfo.pr_uid, os.getuid())
                self.assertEqual(psinfo.pr_euid, os.geteuid())
                self.assertEqual(psinfo.pr_gid, os.getgid())
                self.assertEqual(psinfo.pr_egid, os.getegid())

                # verify zoneid (it's near the end of the structure so if it
                # is right then we likely got most the stuff inbetween decoded
                # correctly).
                libc = ctypes.CDLL('libc.so')
                self.assertEqual(psinfo.pr_zoneid, libc.getzoneid())


if __name__ == "__main__":
        unittest.main()
