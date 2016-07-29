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

# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import pkg.elf as elf
import os
import re
import pkg.portable

class TestElf(pkg5unittest.Pkg5TestCase):

        # If something in this list does not exist, the test_valid_elf
        # tests may fail.  At some point if someone moves paths around in
        # ON, this might fail.  Sorry!
        elf_paths = [
            "/usr/bin/mdb",
            "/usr/bin/__ARCH__/mdb",
            "/usr/lib/libc.so",
            "/usr/lib/__ARCH__/libc.so",
            "/usr/lib/crti.o",
            "/usr/lib/__ARCH__/crti.o",
            "/kernel/drv/__ARCH__/sd",
            "/kernel/fs/__ARCH__/zfs",
            "/usr/kernel/drv/__ARCH__/ptm",
        ]

        def test_non_elf(self):
                """Test that elf routines gracefully handle non-elf objects."""

                p = "this-is-not-an-elf-file.so"
                self.make_misc_files({p: "this is only a test"})
                os.chdir(self.test_root)
                self.assertEqual(elf.is_elf_object(p), False)
                self.assertRaises(elf.ElfError, elf.get_dynamic, p)
                self.assertRaises(elf.ElfError, elf.get_hashes, p)
                self.assertRaises(elf.ElfError, elf.get_info, p)

        def test_non_existent(self):
                """Test that elf routines gracefully handle ENOENT."""

                os.chdir(self.test_root)
                p = "does/not/exist"
                self.assertRaises(OSError, elf.is_elf_object, p)
                self.assertRaises(OSError, elf.get_dynamic, p)
                self.assertRaises(OSError, elf.get_hashes, p)
                self.assertRaises(OSError, elf.get_info, p)

        def test_valid_elf(self):
                """Test that elf routines work on a small set of objects."""
                arch = pkg.portable.get_isainfo()[0]
                for p in self.elf_paths:
                        p = re.sub("__ARCH__", arch, p)
                        self.debug("testing elf file {0}".format(p))
                        self.assertTrue(os.path.exists(p), "{0} does not exist".format(p))
                        self.assertEqual(elf.is_elf_object(p), True)
                        elf.get_dynamic(p)
                        elf.get_hashes(p)
                        elf.get_info(p)

        def test_get_hashes_params(self):
                """Test that get_hashes(..) returns checksums according to the
                parameters passed to the method."""

                # Check that the hashes generated have the correct length
                # depending on the algorithm used to generated.
                sha1_len = 40
                sha256_len = 64

                # the default is to return both the SHA-1 elfhash and
                # the SHA-256 pkg.content-hash
                d = elf.get_hashes(self.elf_paths[0])
                self.assertTrue(len(d["elfhash"]) == sha1_len)
                self.assertTrue("pkg.content-hash" in d)
                self.assertTrue(len(d["pkg.content-hash"]) == 2)
                for h in range(2):
                        v = d["pkg.content-hash"][h].split(":")
                        self.assertTrue(len(v) == 3)
                        self.assertTrue(v[1] == "sha256")
                        self.assertTrue(len(v[2]) == sha256_len)

                d = elf.get_hashes(self.elf_paths[0],
                    elfhash=False, sha512t_256=True)
                self.assertTrue("elfhash" not in d)
                self.assertTrue("pkg.content-hash" in d)
                self.assertTrue(len(d["pkg.content-hash"]) == 4)
                sha256_count = 0
                sha512t_256_count = 0
                unsigned_count = 0
                for h in range(4):
                        v = d["pkg.content-hash"][h].split(":")
                        self.assertTrue(len(v) == 3)
                        self.assertTrue(len(v[2]) == sha256_len)
                        if v[0].endswith(".unsigned"):
                                unsigned_count += 1
                        if v[1] == "sha256":
                                sha256_count += 1
                        elif v[1] == "sha512t_256":
                                sha512t_256_count += 1
                self.assertTrue(sha256_count == 2)
                self.assertTrue(sha512t_256_count == 2)
                self.assertTrue(unsigned_count == 2)

                d = elf.get_hashes(self.elf_paths[0], elfhash=False,
                    sha256=False)
                self.assertTrue(len(d) == 0)


if __name__ == "__main__":
        unittest.main()
