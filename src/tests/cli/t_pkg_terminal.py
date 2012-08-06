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

# Copyright (c) 2012, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest

class TestPkgTerminal(pkg5unittest.SingleDepotTestCase):

        def setUp(self):
                # This test suite needs actual depots.
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)

        def tearDown(self):
                pkg5unittest.SingleDepotTestCase.tearDown(self)

 	def test_pkg_pty(self):
                """Smoke test pkg on a PTY"""

                durl = self.dcs[1].get_depot_url()
                self.image_create(durl)
                cmdline = self.pkg_cmdpath + " -R " + self.img_path() + \
                    " refresh"
                self.cmdline_run(cmdline, exit=0, usepty=True)
                cmdline = self.pkg_cmdpath + " -R " + self.img_path() + \
                    " BADCOMMAND"
                self.cmdline_run(cmdline, exit=2, usepty=True)

 	def test_pkg_bad_term(self):
                """Test that pkg runs properly even with a bad $TERM"""

                durl = self.dcs[1].get_depot_url()
                self.image_create(durl)

                cmdline = self.pkg_cmdpath + " -R " + self.img_path() + \
                    " refresh"
                # give pkg a bad $TERM, make sure it works
                self.cmdline_run(cmdline, env_arg={"TERM": "moop"}, exit=0,
                    usepty=True)
                # give pkg no $TERM, make sure it works
                self.cmdline_run(cmdline, env_arg={"TERM": ""}, exit=0,
                    usepty=True)


class TestPkgTerminalTesters(pkg5unittest.CliTestCase):
        """Test the runprintengine and runprogress test utilities."""
        def setUp(self):
                pkg5unittest.CliTestCase.setUp(self)
                self.runprog = "%s/interactive/runprogress.py" % \
                    pkg5unittest.g_test_dir
                self.runprint = "%s/interactive/runprintengine.py" % \
                    pkg5unittest.g_test_dir

        #
        # This is also an effective way to spot-check certain behaviors of
        # the printengine and progress trackers that are hard to test in
        # the API suite-- such as interactions with environment variables.
        #
 	def test_runprogress(self):
                """Smoke test the "runprogress" debugging utility"""
                self.cmdline_run(self.runprog + " -f fancy -", usepty=True)

 	def test_runprogress_fancy_notty(self):
                """Fail when creating a fancy tracker on a non-tty."""
                self.cmdline_run(self.runprog + " -f fancy -", usepty=False,
                    exit=1)

 	def test_runprogress_badterm(self):
                """Fail when creating a fancy tracker with bad $TERM."""
                self.cmdline_run(self.runprog + " -f fancy -", usepty=True,
                    env_arg={"TERM": "moop"}, exit=1)
                self.cmdline_run(self.runprog + " -f fancy -", usepty=True,
                    env_arg={"TERM": ""}, exit=1)

 	def test_runprogress_slowterm(self):
                """Test fancy progress tracker on a slow terminal."""
                self.cmdline_run("stty ispeed 9600 ospeed 9600; " +
                    self.runprog + " -f fancy -", usepty=True)

 	def test_runprintengine(self):
                """Smoke test the "runprintengine" debugging utility"""
                self.cmdline_run(self.runprint + " -tTl", usepty=True)

 	def test_runprintengine_notty(self):
                """Fail when creating a ttymode printengine on a non-tty."""
                self.cmdline_run(self.runprint + " -t", usepty=False, exit=1)

 	def test_runprintengine_badterm(self):
                """Fail when creating a ttymode printengine with a bad $TERM."""
                self.cmdline_run(self.runprint + " -t", usepty=True,
                    env_arg={"TERM": "moop"}, exit=1)
                self.cmdline_run(self.runprint + " -t", usepty=True,
                    env_arg={"TERM": ""}, exit=1)


if __name__ == "__main__":
        unittest.main()
