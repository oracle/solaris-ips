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


if __name__ == "__main__":
        unittest.main()
