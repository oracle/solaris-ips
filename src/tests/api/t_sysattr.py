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

# Copyright (c) 2014, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import pkg.portable as portable
import os
import re
import tempfile
import unittest

class TestSysattr(pkg5unittest.Pkg5TestCase):

        def __check_sysattrs(self, path, expected=[]):
                """Use ls -/ to check if sysattrs specified by expected are
                   set."""

                p_re = re.compile("{(?P<attrs>.*)}")

                self.cmdline_run("/usr/bin/ls -/ v {0}".format(path), coverage=False)
                m = re.search(p_re, self.output)

                self.assertTrue(m is not None)

                attrs = m.groupdict()["attrs"].split(",")
                for e in expected:
                        self.assertTrue(e in attrs)

        def __reset_file(self):
                """Remove and recreate test file to clear sys attrs."""
                portable.remove(self.test_fn)
                self.test_fh, self.test_fn = tempfile.mkstemp(
                    dir=self.test_path)

        def __get_supported(self):
                supported = portable.get_sysattr_dict()
                # remove "immutable" and "nounlink"
                # We can't unset system attributes and we can't use chmod
                # for unsetting them due to the missing sys_linkdir privilege
                # which gets removed in run.py.
                del supported["immutable"]
                del supported["nounlink"]

                return supported

        def setUp(self):
                if portable.osname != "sunos":
                        raise pkg5unittest.TestSkippedException(
                            "System attributes unsupported on this platform.")

                self.test_path = tempfile.mkdtemp(prefix="test-suite",
                    dir="/var/tmp")
                self.test_fh, self.test_fn = tempfile.mkstemp(
                    dir=self.test_path)
                self.unsup_test_path = tempfile.mkdtemp(prefix="test-suite",
                    dir="/tmp")
                self.test_fh2, self.test_fn2 = tempfile.mkstemp(
                    dir=self.unsup_test_path)

        def tearDown(self):
                portable.remove(self.test_fn)
                portable.remove(self.test_fn2)
                os.rmdir(self.test_path)
                os.rmdir(self.unsup_test_path)

        def test_0_bad_input(self):
                # fsetattr
                self.assertRaises(TypeError, portable.fsetattr, self.test_fn,
                    None)
                self.assertRaises(ValueError, portable.fsetattr, self.test_fn,
                    ["octopus"])
                self.assertRaises(ValueError, portable.fsetattr, self.test_fn,
                    "xyz")
                self.assertRaises(OSError, portable.fsetattr, "/nofile",
                    "H")
                # FS does not support system attributes.
                self.assertRaises(OSError, portable.fsetattr, self.test_fn2,
                    "H")

                # fgetattr
                self.assertRaises(OSError, portable.fgetattr, "/nofile")

        def test_1_supported_dict(self):
                """Check if the supported sys attr dictionary can be retrieved
                   and contains some attributes."""

                supported = portable.get_sysattr_dict()
                self.assertTrue(len(supported))

        def test_2_fsetattr(self):
                """Check if the fsetattr works with all supported attrs."""
                supported = self.__get_supported()

                # try to set all supported verbose attrs
                for a in supported:
                        portable.fsetattr(self.test_fn, [a])
                        self.__check_sysattrs(self.test_fn, [a])
                        self.__reset_file()

                # try to set all supported compact attrs
                for a in supported:
                        portable.fsetattr(self.test_fn, supported[a])
                        self.__check_sysattrs(self.test_fn, [a])
                        self.__reset_file()

                # set all at once using verbose
                portable.fsetattr(self.test_fn, supported)
                self.__check_sysattrs(self.test_fn, supported)
                self.__reset_file()

                # set all at once using compact
                cattrs = ""
                for a in supported:
                        cattrs += supported[a]
                portable.fsetattr(self.test_fn, cattrs)
                self.__check_sysattrs(self.test_fn, supported)
                self.__reset_file()

        def test_3_fgetattr(self):
                """Check if the fgetattr works with all supported attrs.""" 
                supported = self.__get_supported()
                for a in supported:
                        # av_quarantined file becomes unreadable, skip
                        if a == "av_quarantined":
                                continue
                        portable.fsetattr(self.test_fn, [a])
                        vattrs = portable.fgetattr(self.test_fn, compact=False)
                        cattrs = portable.fgetattr(self.test_fn, compact=True)
                        self.assertTrue(a in vattrs)
                        self.assertTrue(supported[a] in cattrs)
                        self.__reset_file()


if __name__ == "__main__":
        unittest.main()
