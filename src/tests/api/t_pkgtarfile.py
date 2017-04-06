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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import sys
import os
import tempfile
import shutil
import tarfile
import pkg.portable as portable
import pkg.pkgtarfile as pkgtarfile

class TestPkgTarFile(pkg5unittest.Pkg5TestCase):

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)
                self.tpath = tempfile.mkdtemp(dir=self.test_root)

                cpath = tempfile.mkdtemp(dir=self.test_root)
                filepath = os.path.join(cpath, "foo/bar")
                filename = "baz"
                create_path = os.path.join(filepath, filename)
                os.makedirs(filepath)
                wfp = open(create_path, "wb")
                buf = os.urandom(8192)
                wfp.write(buf)
                wfp.close()

                self.tarfile = os.path.join(self.tpath, "test.tar")

                tarfp = tarfile.open(self.tarfile, 'w')
                tarfp.add(create_path, "foo/bar/baz")
                tarfp.close()
                shutil.rmtree(cpath)

        def testerrorlevelIsCorrect(self):
                p = pkgtarfile.PkgTarFile(self.tarfile, 'r')

                # "read-only" folders on Windows are not actually read-only so
                # the test below doesn't cause the exception to be raised
                if portable.is_admin() or portable.util.get_canonical_os_type() == "windows":
                        self.assertTrue(p.errorlevel == 2)
                        p.close()
                        return

                extractpath = os.path.join(self.tpath, "foo/bar")
                os.makedirs(extractpath)
                os.chmod(extractpath, 0o555)
                self.assertRaises(IOError, p.extract, "foo/bar/baz",
                    self.tpath)
                p.close()
                os.chmod(extractpath, 0o777)


if __name__ == "__main__":
        unittest.main()
