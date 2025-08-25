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

# Copyright (c) 2009, 2025, Oracle and/or its affiliates.

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import codecs
import os
import re
import unittest
from pkg.misc import force_text


class TestPkgHelp(pkg5unittest.CliTestCase):
    # Tests in this suite use the read only data directory.
    need_ro_data = True

    def test_help(self):
        """Verify that usage message works regardless of how it is
        triggered."""

        def verify_help(msg, expected, unexpected=[]):
            """Verify a usage message contains output for each of
            the elements of a given array 'expected', and none
            of the items in the array 'unexpected'."""

            for str in expected:
                if str not in msg:
                    self.assertTrue(False, "{0} not in {1}".format(
                        str, msg))
            for str in unexpected:
                if str in msg:
                    self.assertTrue(False, "{0} in {1}".format(
                        str, msg))

        # Full list of subcommands, ensuring we exit 0
        for option in [r"-\?", "--help", "help"]:
            ret, out, err = self.pkg(option, out=True, stderr=True)
            verify_help(err,
                ["pkg [options] command [cmd_options] [operands]",
                "For more info, run: pkg help <command>"])

        # Full usage text, ensuring we exit 0
        for option in ["help -v"]:
            ret, out, err = self.pkg(option, out=True, stderr=True)
            verify_help(err,
                ["pkg [options] command [cmd_options] [operands]",
                "pkg verify [-Hqv] [-p path]... [--parsable version]\n"
                "            [--unpackaged] [--unpackaged-only] [pkg_fmri_pattern ...]",
                "PKG_IMAGE", "Usage:"])

        # Invalid subcommands, ensuring we exit 2
        for option in [r"-\? bobcat", "--help bobcat", "help bobcat",
            "bobcat --help"]:
            ret, out, err = self.pkg(r"-\? bobcat", exit=2, out=True,
                stderr=True)
            verify_help(err,
                ["pkg: unknown subcommand",
                "For a full list of subcommands, run: pkg help"])

        # Unrequested usage
        ret, out, err = self.pkg("", exit=2, out=True, stderr=True)
        verify_help(err,
            ["pkg: no subcommand specified",
            "pkg [options] command [cmd_options] [operands]",
            "For more info, run: pkg help <command>"],
            unexpected=["PKG_IMAGE"])

        # help for a subcommand should only print that subcommand usage
        for option in ["property --help", "--help property",
            "help property"]:
            ret, out, err = self.pkg(option, out=True, stderr=True)
            verify_help(err, ["pkg property [-H] [propname ...]",
                "Usage:"], unexpected=[
                "pkg [options] command [cmd_options] [operands]",
                "PKG_IMAGE"])

    def test_help_character_encoding(self):
        """Verify help command output for ja_JP.eucJP locale.
        Match against the expected output"""

        # This is a test case for CR 7166082.
        # It compares the output of "pkg --help" command against
        # the expected output for ja_JP.eucJP locale.
        # If first 4 lines of "pkg --help" command output modified
        # in the future then this test case will also need to be
        # modified.

        ret, out = self.cmdline_run("/usr/bin/locale -a", out=True,
            coverage=False)
        line = " ".join(out.split())
        m = re.search(r"ja_JP.eucJP", line)
        if not m:
            raise pkg5unittest.TestSkippedException("The "
                "test system must have the ja_JP.eucJP locale "
                "installed to run this test.")

        eucJP_encode_file = os.path.join(self.ro_data_root,
            "pkg.help.eucJP.expected.out")
        f = codecs.open(eucJP_encode_file, encoding="eucJP")

        locale_env = { "LC_ALL": "ja_JP.eucJP" }
        ret, out, err = self.pkg("help -v", env_arg=locale_env,
            out=True, stderr=True)
        cmd_out = force_text(err, encoding="eucJP")
        # Take only 4 lines from "pkg --help" command output.
        u_out = cmd_out.splitlines()[:4]

        n = 0
        # The expected output file contain 4 lines and command output
        # is also 4 lines.
        while n < 4:
            cmd_line = u_out[n]
            # Remove \n from readline()
            file_line = f.readline()[:-1]

            self.assertEqual(cmd_line, file_line)
            n = n + 1

        f.close()


if __name__ == "__main__":
    unittest.main()
