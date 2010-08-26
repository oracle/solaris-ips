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

# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest

class TestPkgHelp(pkg5unittest.CliTestCase):

        def test_help(self):
                """Verify that usage message works regardless of how it is
                triggered."""

                def verify_help(msg, expected, unexpected=[]):
                        """Verify a usage message contains output for each of
                        the elements of a given array 'expected', and none
                        of the items in the array 'unexpected'."""

                        for str in expected:
                                if str not in msg:
                                        self.assert_(False, "%s not in %s" %
                                            (str, msg))
                        for str in unexpected:
                                if str in msg:
                                        self.assert_(False, "%s in %s" %
                                            (str, msg))

                # Full usage text, ensuring we exit 0
                for option in ["-\?", "--help", "help"]:
                        ret, out, err = self.pkg(option, out=True, stderr=True)
                        verify_help(err,
                            ["pkg [options] command [cmd_options] [operands]",
                            "pkg verify [-Hqv] [pkg_fmri_pattern ...]",
                            "PKG_IMAGE", "Usage:"])

                # Invalid subcommands, ensuring we exit 2
                for option in ["-\? bobcat", "--help bobcat", "help bobcat",
                    "bobcat --help"]:
                        ret, out, err = self.pkg("-\? bobcat", exit=2, out=True,
                            stderr=True)
                        verify_help(err,
                            ["pkg [options] command [cmd_options] [operands]",
                            "pkg: unknown subcommand",
                            "PKG_IMAGE", "Usage:"])

                # Unrequested usage
                ret, out, err = self.pkg("", exit=2, out=True, stderr=True)
                verify_help(err,
                    ["pkg: no subcommand specified",
                    "Try `pkg --help or -?' for more information."],
                    unexpected = ["PKG_IMAGE", "Usage:"])

                # help for a subcommand should only print that subcommand usage
                for option in ["property --help", "--help property",
                    "help property"]:
                        ret, out, err = self.pkg(option, out=True, stderr=True)
                        verify_help(err, ["pkg property [-H] [propname ...]",
                            "Usage:"], unexpected=[
                            "pkg [options] command [cmd_options] [operands]",
                            "PKG_IMAGE"])

if __name__ == "__main__":
        unittest.main()
