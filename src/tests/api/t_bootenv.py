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

# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import os
import sys
import pkg.client.bootenv as bootenv

class TestBootEnv(pkg5unittest.Pkg5TestCase):
                
        def test_api_consistency(self):
                """Make sure every public method in BootEnv exists in
                BootEnvNull and the other way around.
                """

                nullm = set(d for d in dir(bootenv.BootEnvNull)
                    if not d.startswith("_"))
                bem = set(d for d in dir(bootenv.BootEnv)
                    if not d.startswith("_"))

                be_missing = nullm - bem
                null_missing = bem - nullm

                estr = ""
                if be_missing:
                        estr += "The following methods were missing from " \
                            "BootEnv:\n" + \
                            "\n".join("\t{0}".format(s) for s in be_missing)
                if null_missing:
                        estr += "The following methods were missing from " \
                            "BootEnvNull:\n" + \
                            "\n".join("\t{0}".format(s) for s in null_missing)
                self.assertTrue(not estr, estr)

        def test_bootenv(self):
                """All other test suite tests test the BootEnv class with,
                PKG_NO_LIVE_ROOT set in the environment, see the run() and
                env_santize(..) methods in Pkg5TestSuite.  That environment
                variable means that BootEnv.get_be_list will always return an
                empty list.  While we want to generally avoid touching the live
                image root at all, making an exception here seems the best
                reasonable way to test some of the non-modifying BootEnv code.
                To that end, this test clears the relevant environment variable.
                """

                del os.environ["PKG_NO_LIVE_ROOT"]
                self.assertTrue(bootenv.BootEnv.libbe_exists())
                self.assertTrue(bootenv.BootEnv.check_verify())
                self.assertTrue(isinstance(
                    bootenv.BootEnv.get_be_list(raise_error=False), list))
                self.assertTrue(isinstance(
                    bootenv.BootEnv.get_be_list(raise_error=True), list))

                bootenv.BootEnv.get_be_name("/")
                self.assertTrue(
                    isinstance(bootenv.BootEnv.get_uuid_be_dic(), dict))
                bootenv.BootEnv.get_activated_be_name()
                bootenv.BootEnv.get_active_be_name()
                # This assumes that a1b2c3d4e5f6g7h8i9j0 is highly unlikely to
                # be an existing BE on the system.
                bootenv.BootEnv.check_be_name("a1b2c3d4e5f6g7h8i9j0")


if __name__ == "__main__":
        unittest.main()
