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
# Copyright (c) 2010, 2021, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import ctypes
import os
import shutil
import stat
import subprocess
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

        def test_memory_limit(self):
                """Verify that set_memory_limit works."""

                # memory limit to test, keep small to avoid test slowdown
                mem_cap = 100 * 1024 * 1024
                # memory tolerance: allowed discrepancy between set limit and
                # measured process resources. Note, that we have a static
                # overhead in waste.py for the forking of ps, so while 20M seems
                # large compared to a 100M limit, in a real world example with
                # 8G limit it's fairly small. 
                mem_tol = 20 * 1024 * 1024

                waste_mem_py = """
import os
import resource
import subprocess

import pkg.misc as misc

misc.set_memory_limit({0})
i = 0
x = {{}}
try:
        while True:
                i += 1
                x[i] = range(i)
except MemoryError:
        # give us some breathing room (enough so the test with env var works)
        misc.set_memory_limit({0} * 3, allow_override=False)
        print(subprocess.check_output(['ps', '-o', 'rss=', '-p',
            str(os.getpid())], text=True).strip())
""".format(str(mem_cap))

                # Re-setting limits which are higher than original limit can
                # only be done by root. 
                self.assertTrue(os.geteuid() == 0,
                    "must be root to run this test")

                tmpdir = tempfile.mkdtemp(dir=self.test_root)
                tmpfile = os.path.join(tmpdir, 'waste.py')
                with open(tmpfile, 'w') as f:
                        f.write(waste_mem_py)

                res = int(subprocess.check_output(['python3.7', tmpfile]))
                # convert from kB to bytes
                res *= 1024

                self.debug("mem_cap:   " + str(mem_cap))
                self.debug("proc size: " + str(res))

                self.assertTrue(res < mem_cap + mem_tol,
                    "process mem consumption too high")
                self.assertTrue(res > mem_cap - mem_tol,
                    "process mem consumption too low")

                # test if env var works
                os.environ["PKG_CLIENT_MAX_PROCESS_SIZE"] = str(mem_cap * 2)
                res = int(subprocess.check_output(['python3.7', tmpfile]))
                res *= 1024

                self.debug("mem_cap:   " + str(mem_cap))
                self.debug("proc size: " + str(res))

                self.assertTrue(res < mem_cap * 2 + mem_tol,
                    "process mem consumption too high")
                self.assertTrue(res > mem_cap * 2 - mem_tol,
                    "process mem consumption too low")

                # test if invalid env var is handled correctly
                os.environ["PKG_CLIENT_MAX_PROCESS_SIZE"] = "octopus"
                res = int(subprocess.check_output(['python3.7', tmpfile]))
                res *= 1024

                self.debug("mem_cap:   " + str(mem_cap))
                self.debug("proc size: " + str(res))

                self.assertTrue(res < mem_cap + mem_tol,
                    "process mem consumption too high")
                self.assertTrue(res > mem_cap - mem_tol,
                    "process mem consumption too low")

if __name__ == "__main__":
        unittest.main()
