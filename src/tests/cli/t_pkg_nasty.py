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
# Copyright (c) 2012, 2023, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest
import random
import re
import shutil
import signal
import time

import pkg.portable as portable

class TestPkgNasty(pkg5unittest.SingleDepotTestCase):

    need_ro_data = True

    # Default number iterations; tune with NASTY_ITERS in environ.
    NASTY_ITERS = 10
    # Default nastiness; tune with NASTY_LEVEL in environ.
    NASTY_LEVEL = 50

    NASTY_SLEEP = 2

    template_10 = """
            open testpkg/__SUB__@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/stuff
            add file tmp/file1 mode=0644 owner=root group=bin path=/__SUB__/f1 preserve=true
            add file tmp/file2 mode=0644 owner=root group=bin path=/__SUB__/f2
            add file tmp/file3 mode=0644 owner=root group=bin path=/__SUB__/f3
            close """

    # in v1.1, file contents are shifted around
    template_11 = """
            open testpkg/__SUB__@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/stuff
            add file tmp/file2 mode=0644 owner=root group=bin path=/__SUB__/f1 preserve=true
            add file tmp/file3 mode=0644 owner=root group=bin path=/__SUB__/f2
            add file tmp/file4 mode=0644 owner=root group=bin path=/__SUB__/f3
            add file tmp/file5 mode=0644 owner=root group=bin path=/__SUB__/f4
            close """

    def __make_rand_string(self, outlen):
        s = ""
        while outlen > 0:
            s += random.choice("\n\n\n\nabcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()")
            outlen -= 1
        return s

    def __make_rand_files(self):
        misc_files = {
            "tmp/file1": 1,
            "tmp/file2": 32,
            "tmp/file3": 4096,
            "tmp/file4": 16384,
            "tmp/file5": 65536
        }
        for f in misc_files:
            # Overwrite the number with file contents of size
            # <that number>
            misc_files[f] = \
                self.__make_rand_string(misc_files[f])
        self.make_misc_files(misc_files)

    def __make_pkgs(self):
        self.testpkgs = []
        for pkgname in ["A", "B", "C", "D"]:
            self.testpkgs.append(re.sub("__SUB__", pkgname,
                self.template_10))
            self.testpkgs.append(re.sub("__SUB__", pkgname,
                self.template_11))

    def setUp(self):
        pkg5unittest.SingleDepotTestCase.setUp(self)

        self.NASTY_ITERS = \
            int(os.environ.get("NASTY_ITERS", self.NASTY_ITERS))
        self.NASTY_LEVEL = \
            int(os.environ.get("NASTY_LEVEL", self.NASTY_LEVEL))

        os.chdir(self.test_root)
        self.__make_rand_files()
        self.__make_pkgs()
        for pkgcontents in self.testpkgs:
            plist = self.pkgsend_bulk(self.rurl, pkgcontents)
            self.pkgsign_simple(self.rurl, plist[0])
        self.dc.set_nasty(self.NASTY_LEVEL)
        self.dc.set_nasty_sleep(self.NASTY_SLEEP)

        self.nasty_env = {
            "PKG_CLIENT_MAX_CONSECUTIVE_ERRORS": "3",
            "PKG_CLIENT_MAX_TIMEOUT": "2",
            "PKG_CLIENT_LOWSPEED_TIMEOUT": \
                "{0:d}".format(self.NASTY_SLEEP - 1),
        }

        self.dc.start()

        pubname = "test"
        self.mfst_path = os.path.join(self.img_path(),
            "var/pkg/publisher/{0}/pkg".format(pubname))

    def _rm_mfsts(self):
        # Note that we have chosen not to ignore errors here,
        # since we're depending on knowing the internal layout
        # of var/pkg.
        shutil.rmtree(self.mfst_path)

    def _dumplog(self):
        self.debug("---- Last 50 depot log entries:")
        try:
            lp = self.dc.get_logpath()
            log = open(lp)
            lines = log.readlines()
            self.debug("".join(lines[-50:]))
        except Exception:
            self.debug("Failed to print log entries")

    def _trythis(self, label, kallable, ntries=10):
        """Runs kallable ntries times; if after ntries the operation
        has not returned 0, try again with the nastiness disabled in
        the depot.  The goal is to push through to get a real result
        but also to prevent infinite looping."""
        for tries in range(1, ntries + 1):
            if tries > 1:
                self.debug(
                    "--try: '{0}' try #{1:d}".format(
                    label, tries))
            ret = kallable()
            if ret == 0:
                break
        else:
            # Turn nastiness off on the depot and try again;
            # this helps prevent waiting around forever for
            # something to eventually work.
            self.debug("Note: Repeated failures for '{0}' "
                "({1:d} times).  Disabling nasty and retrying".format(
                label, ntries))
            # Reset environment params and depot nastiness.
            # We have to edit self.nasty_env in place (as opposed
            # to just replacing it) because a reference to it is
            # already bound up with kallable.
            save_low = self.nasty_env["PKG_CLIENT_LOWSPEED_TIMEOUT"]
            save_maxtmo = self.nasty_env["PKG_CLIENT_MAX_TIMEOUT"]
            # Set these to "" to make them revert to defaults
            self.nasty_env["PKG_CLIENT_LOWSPEED_TIMEOUT"] = ""
            self.nasty_env["PKG_CLIENT_MAX_TIMEOUT"] = ""
            self.dc.set_nasty(0)

            ret = kallable()

            # Restore Nastiness and environment parameters.
            self.nasty_env["PKG_CLIENT_LOWSPEED_TIMEOUT"] = save_low
            self.nasty_env["PKG_CLIENT_MAX_TIMEOUT"] = save_maxtmo
            self.dc.set_nasty(self.NASTY_LEVEL)
            if ret != 0:
                raise self.failureException(
                    "Failed '{0}' {1:d} times, then failed again "
                    "with nasty disabled.  Test failed".format(
                    label, ntries))

    def do_main_loop(self, kallable):
        """Loop running a nasty test.  Iterations tunable by setting
        NASTY_ITERS in the process environment, i.e. NASTY_ITERS=100."""
        for x in range(1, self.NASTY_ITERS + 1):
            self.debug("---- Iteration {0:d}/{1:d} ----".format(
                x, self.NASTY_ITERS))
            try:
                kallable()
            except:
                self._dumplog()
                self.debug("---- Iteration {0:d}/{1:d} FAILED ----".format(
                    x, self.NASTY_ITERS))
                raise


class TestNastyInstall(TestPkgNasty):
    # Exists as a subclass only so we can run tests in parallel.

    def __nasty_install_1_run(self):
        env = self.nasty_env

        self._trythis("image create",
            lambda: self.pkg_image_create(repourl=self.durl,
            env_arg=env, exit=[0, 1]))

        # Set up signature stuff.
        emptyCA = os.path.join(self.img_path(), "emptyCA")
        os.makedirs(emptyCA)
        self.pkg("set-property trust-anchor-directory emptyCA")
        self.seed_ta_dir("ta3", dest_dir=emptyCA)
        self.pkg("set-property signature-policy require-signatures")

        self._trythis("refresh",
            lambda: self.pkg("refresh", env_arg=env, exit=[0, 1]))
        self._trythis("refresh --full",
            lambda: self.pkg("refresh --full",
                env_arg=env, exit=[0, 1]))
        self._trythis("search -r /A/f2",
            lambda: self.pkg("search -r /A/f2",
                env_arg=env, exit=[0, 1, 3]))

        # test contents -r
        contentscmd = "contents -m -r testpkg/*A@1.0"
        self._trythis(contentscmd,
            lambda: self.pkg(contentscmd, env_arg=env, exit=[0, 1]))
        # clean up mfsts.
        self._rm_mfsts()

        self._trythis("install testpkg/*@1.0",
            lambda: self.pkg("install testpkg/*@1.0",
                env_arg=env, exit=[0, 1]))
        self._trythis("update",
            lambda: self.pkg("update", env_arg=env, exit=[0, 1]))

        # Change a file in the image and then revert it.
        path = os.path.join(self.img_path(), "A", "f1")
        self.assertTrue(os.path.exists(path))
        f = open(path, "w")
        print("I LIKE COCONUTS!", file=f)
        f.close()
        self._trythis("revert",
            lambda: self.pkg("revert A/f1", env_arg=env, exit=[0, 1]))

        # Try some things which are supposed to fail; we can't really
        # pick apart transport failures versus the actual semantic
        # failure; oh well for now.
        self.pkg("search -r /doesnotexist", env_arg=env, exit=1)
        self.pkg("contents -r doesnotexist", env_arg=env, exit=1)
        self.pkg("verify", exit=0)

    def test_install_nasty_looping(self):
        """Test the pkg command against a nasty depot."""
        self.do_main_loop(self.__nasty_install_1_run)


class TestNastyPkgUtils(TestPkgNasty):
    # Exists as a subclass only so we can run tests in parallel.
    persistent_setup = True

    def __nasty_pkgrecv_1_run(self):
        env = self.nasty_env
        self.cmdline_run("rm -rf test_repo", exit=[0, 1],
            coverage=False)
        self.pkgrepo("create test_repo")
        self._trythis("recv *",
            lambda: self.pkgrecv(self.durl,
                "-d test_repo '*'", env_arg=env, exit=[0, 1]))
        # clean up pkgrecv "resume" turds
        self.cmdline_run("rm -rf pkgrecv-*", exit=[0, 1],
            coverage=False)

    def test_pkgrecv_nasty_looping(self):
        """Test the pkgrecv command against a nasty depot."""
        self.do_main_loop(self.__nasty_pkgrecv_1_run)

    def __nasty_pkgrepo_1_run(self):
        env = self.nasty_env
        self._trythis("pkgrepo get",
            lambda: self.pkgrepo(
                "get -s {0}".format(self.durl), env_arg=env, exit=[0, 1]))
        self._trythis("pkgrepo info",
            lambda: self.pkgrepo(
                "info -s {0}".format(self.durl), env_arg=env, exit=[0, 1]))
        self._trythis("pkgrepo list",
            lambda: self.pkgrepo(
                "list -s {0}".format(self.durl), env_arg=env, exit=[0, 1]))
        self._trythis("pkgrepo rebuild",
            lambda: self.pkgrepo(
                "rebuild -s {0}".format(self.durl), env_arg=env, exit=[0, 1]))
        self._trythis("pkgrepo refresh",
            lambda: self.pkgrepo(
                "refresh -s {0}".format(self.durl), env_arg=env, exit=[0, 1]))

    def test_pkgrepo_nasty_looping(self):
        """Test the pkgrepo command against a nasty depot."""
        self.do_main_loop(self.__nasty_pkgrepo_1_run)


class TestNastyTempPub(TestPkgNasty):
    # Exists as a subclass only so we can run tests in parallel.

    def __nasty_temppub_1_run(self):
        env = self.nasty_env

        self.pkg_image_create(repourl=None)
        # Set up signature stuff.
        emptyCA = os.path.join(self.img_path(), "emptyCA")
        os.makedirs(emptyCA)
        self.pkg("set-property trust-anchor-directory emptyCA")
        self.seed_ta_dir("ta3", dest_dir=emptyCA)
        self.pkg("set-property signature-policy require-signatures")

        # test list with temporary publisher
        cmd = "list -a -g {0} \*".format(self.durl)
        self._trythis(cmd,
            lambda: self.pkg(cmd, env_arg=env, exit=[0, 1]))

        # test contents with temporary publisher
        cmd = "contents -m -g {0} -r testpkg/*A@1.1".format(self.durl)
        self._trythis(cmd,
            lambda: self.pkg(cmd, env_arg=env, exit=[0, 1]))

        # clean out dl'd mfsts
        self._rm_mfsts()
        # test info with temporary publisher
        cmd = "info -g {0} \*".format(self.durl)
        self._trythis(cmd,
            lambda: self.pkg(cmd, env_arg=env, exit=[0, 1]))

        # clean out dl'd mfsts
        self._rm_mfsts()
        # test install with temporary publisher
        cmd = "install -g {0} testpkg/*@1.0".format(self.durl)
        self._trythis(cmd,
            lambda: self.pkg(cmd, env_arg=env, exit=[0, 1]))

        # test update with temporary publisher
        cmd = "update -g {0}".format(self.durl)
        self._trythis(cmd,
            lambda: self.pkg(cmd, env_arg=env, exit=[0, 1, 4]))

        self.pkg("verify", exit=0)

    def test_temppub_nasty_looping(self):
        self.do_main_loop(self.__nasty_temppub_1_run)


class TestNastySig(pkg5unittest.SingleDepotTestCase):
    # Only start/stop the depot once (instead of for every test)
    persistent_setup = True

    foo10 = """
            open foo@1.0,5.11-0
            close """

    def setUp(self):
        pkg5unittest.SingleDepotTestCase.setUp(self)
        self.pkgsend_bulk(self.rurl, self.foo10)

    def test_00_sig(self):
        """Verify pkg client handles SIGTERM, SIGHUP, SIGINT gracefully
        and writes a history entry if possible."""

        if portable.osname == "windows":
            # SIGHUP not supported on Windows.
            sigs = (signal.SIGINT, signal.SIGTERM)
        else:
            sigs = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)

        for sig in sigs:
            self.pkg_image_create(self.rurl)

            imgdir = os.path.join(self.img_path(), "var", "pkg")
            self.assertTrue(os.path.exists(imgdir))

            hfile = os.path.join(imgdir, "pkg5.hang")
            self.assertTrue(not os.path.exists(hfile))

            self.pkg("purge-history")

            hndl = self.pkg(
                ["-D", "simulate-plan-hang=true", "install", "foo"],
                handle=True, coverage=False)

            # Wait for hang file before sending signal.
            while not os.path.exists(hfile):
                self.assertEqual(hndl.poll(), None)
                time.sleep(0.25)

            hndl.send_signal(sig)
            rc = hndl.wait()

            self.assertEqual(rc, 1)

            # Verify that history records operation as canceled.
            self.pkg(["history", "-H"])
            hentry = self.output.splitlines()[-1]
            self.assertTrue("install" in hentry)
            self.assertTrue("Canceled" in hentry)


if __name__ == "__main__":
    unittest.main()
