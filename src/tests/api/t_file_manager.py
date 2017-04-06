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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import os
import shutil
import sys
import tempfile
import unittest

import pkg.misc as misc
import pkg.file_layout.file_manager as file_manager
import pkg.file_layout.layout as layout

class TestFileManager(pkg5unittest.Pkg5TestCase):

        @staticmethod
        def old_hash(s):
                return os.path.join(s[0:2], s[2:8], s)

        def touch_old_file(self, s, data=None):
                if data is None:
                        data = s
                p = os.path.join(self.base_dir, self.old_hash(s))
                if not os.path.exists(os.path.dirname(p)):
                        os.makedirs(os.path.dirname(p))
                fh = open(p, "wb")
                fh.write(misc.force_bytes(data))
                fh.close()
                return p

        @staticmethod
        def check_exception(func, ex, str_bits, *args, **kwargs):
                try:
                        func(*args, **kwargs)
                except ex as e:
                        s = str(e)
                        for b in str_bits:
                                if b not in s:
                                        raise RuntimeError("Expected to find "
                                            "{0} in {1}".format(b, s))
                else:
                        raise RuntimeError("Didn't raise expected exception")

        def check_readonly(self, fm, unmoved, p):
                self.assertTrue(os.path.isfile(p))
                self.assertEqual(fm.lookup(unmoved), p)
                fh = fm.lookup(unmoved, opener=True)
                try:
                        self.assertEqual(fh.read(), misc.force_bytes(unmoved))
                finally:
                        fh.close()
                self.assertTrue(os.path.isfile(p))

                self.check_exception(fm.insert,
                    file_manager.NeedToModifyReadOnlyFileManager,
                    ["create", unmoved], unmoved, p)
                self.assertTrue(os.path.isfile(p))
                self.check_exception(fm.remove,
                    file_manager.NeedToModifyReadOnlyFileManager,
                    ["remove", unmoved], unmoved)
                self.assertTrue(os.path.isfile(p))

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)
                # Move base_dir down one level so that the tests don't assume
                # sole control over the contents of self.test_root.
                self.base_dir = os.path.join(self.test_root, "fm")
                os.mkdir(self.base_dir)

        def test_1(self):
                """Verify base functionality works as expected."""

                t = tempfile.gettempdir()
                no_dir = os.path.join(t, "not_exist")

                # Test that a read only FileManager won't modify the file
                # system.
                fm = file_manager.FileManager(self.base_dir, readonly=True)
                self.assertEqual(os.listdir(self.base_dir), [])

                unmoved = "4b7c923af3a047d4685a39ad7bc9b0382ccde671"

                p = self.touch_old_file(unmoved)
                self.check_readonly(fm, unmoved, p)

                self.assertEqual(set(fm.walk()),
                    set([unmoved]))

                # Test a FileManager that can write to the file system.
                fm = file_manager.FileManager(self.base_dir, False)

                hash1 = "584b6ab7d7eb446938a02e57101c3a2fecbfb3cb"
                hash2 = "584b6ab7d7eb446938a02e57101c3a2fecbfb3cc"
                hash3 = "994b6ab7d7eb446938a02e57101c3a2fecbfb3cc"
                hash4 = "cc1f76cdad188714d1c3b92a4eebb4ec7d646166"

                l = layout.V1Layout()

                self.assertEqual(l.lookup(hash1),
                    "58/584b6ab7d7eb446938a02e57101c3a2fecbfb3cb")

                # Test that looking up a file stored under the old system gets
                # moved to the correct location, that the new location is
                # correctly returned, and that the old location's parent
                # directory no longer exists as only a single file existed
                # there.  Finally, remove it for the next test if successful.
                p1 = self.touch_old_file(hash1)
                self.assertTrue(os.path.isfile(p1))
                self.assertTrue(os.path.isdir(os.path.dirname(p1)))
                self.assertEqual(fm.lookup(hash1),
                    os.path.join(self.base_dir, l.lookup(hash1)))
                self.assertTrue(not os.path.exists(p1))
                self.assertTrue(not os.path.exists(os.path.dirname(p1)))
                fm.remove(hash1)

                # Test that looking up a file stored under the old system gets
                # moved to the correct location, that the new location is
                # correctly returned, and that the old location's parent
                # directory still exists as multiple files were stored there.
                # Finally, remove file stored in the old location for the next
                # few tests.
                p1 = self.touch_old_file(hash1)
                self.touch_old_file(hash2)
                self.assertTrue(os.path.isfile(p1))
                self.assertTrue(os.path.isdir(os.path.dirname(p1)))
                self.assertEqual(fm.lookup(hash1),
                    os.path.join(self.base_dir, l.lookup(hash1)))
                self.assertTrue(not os.path.exists(p1))
                self.assertTrue(os.path.exists(os.path.dirname(p1)))
                fm.remove(hash2)

                # Test that looking up a file stored under the old system gets
                # moved and that it returns a file handle with the correct
                # contents.
                p4 = self.touch_old_file(hash4)
                self.assertTrue(os.path.isfile(p4))
                self.assertTrue(os.path.isdir(os.path.dirname(p4)))
                fh = fm.lookup(hash4, opener=True)
                try:
                        self.assertEqual(fh.read(), misc.force_bytes(hash4))
                finally:
                        fh.close()
                self.assertTrue(not os.path.exists(p4))
                self.assertTrue(not os.path.exists(os.path.dirname(p4)))

                p3 = self.touch_old_file(hash3)
                self.assertTrue(os.path.isfile(p3))
                self.assertTrue(os.path.isdir(os.path.dirname(p3)))
                fm.insert(hash3, p3)

                self.assertTrue(not os.path.exists(p3))
                self.assertTrue(not os.path.exists(os.path.dirname(p3)))

                fh = fm.lookup(hash3, opener=True)
                try:
                        self.assertEqual(fh.read(), misc.force_bytes(hash3))
                finally:
                        fh.close()

                # Test that walk returns the expected values.
                self.assertEqual(set(fm.walk()),
                    set([unmoved, hash1, hash4, hash3]))

                # Test that walking with a different set of layouts works as
                # expected.
                fm2 = file_manager.FileManager(self.base_dir, readonly=True,
                    layouts=[layout.get_preferred_layout()])

                fs = set([hash1, hash4, hash3])
                try:
                        for i in fm2.walk():
                                fs.remove(i)
                except file_manager.UnrecognizedFilePaths as e:
                        self.assertEqual(e.fps, [p[len(self.base_dir) + 1:]])
                self.assertEqual(fs, set())

                # Test removing a file works and removes the containing
                # directory and that remove removes all instances of a hash
                # from the file manager.
                hash3_loc = os.path.join(self.base_dir, l.lookup(hash3))
                v0_hash3_loc = self.touch_old_file(hash3)

                self.assertTrue(os.path.isfile(hash3_loc))
                self.assertTrue(os.path.isfile(v0_hash3_loc))
                fm.remove(hash3)
                self.assertEqual(fm.lookup(hash3), None)
                self.assertTrue(not os.path.exists(hash3_loc))
                self.assertTrue(not os.path.exists(os.path.dirname(hash3_loc)))
                self.assertTrue(not os.path.exists(v0_hash3_loc))
                self.assertTrue(not os.path.exists(os.path.dirname(v0_hash3_loc)))
                self.assertTrue(os.path.isfile(fm.lookup(hash1)))

                rh2_fd, raw_hash_2_loc = tempfile.mkstemp(dir=self.base_dir)
                rh2_fh = os.fdopen(rh2_fd, "w")
                rh2_fh.write(hash2)
                rh2_fh.close()

                fm.insert(hash2, raw_hash_2_loc)
                h2_loc = fm.lookup(hash2)
                self.assertTrue(os.path.isfile(fm.lookup(hash2)))
                # Test that the directory has two files in it as expected.
                self.assertEqual(set(os.listdir(
                    os.path.dirname(fm.lookup(hash2)))),
                    set([hash1, hash2]))
                # Test removing one of the two files doesn't remove the other.
                fm.remove(hash1)
                self.assertTrue(os.path.isfile(h2_loc))
                self.assertEqual(fm.lookup(hash2), h2_loc)
                self.assertEqual(fm.lookup(hash1), None)
                # Test that removing the second file works and removes the
                # containing directory as well.
                fm.remove(hash2)
                self.assertTrue(not os.path.exists(h2_loc))
                self.assertTrue(not os.path.exists(os.path.dirname(h2_loc)))

                # Test that setting the read_only property works and that none
                # of the activities has effected the location where unmoved has
                # been stored.
                fm.set_read_only()
                self.check_readonly(fm, unmoved, p)

        def test_2_reverse(self):
                """Verify that reverse layout migration works as expected."""

                # Verify that reverse layout migration works as expected.
                hash1 = "584b6ab7d7eb446938a02e57101c3a2fecbfb3cb"
                hash2 = "584b6ab7d7eb446938a02e57101c3a2fecbfb3cc"
                hash3 = "994b6ab7d7eb446938a02e57101c3a2fecbfb3cc"
                hash4 = "cc1f76cdad188714d1c3b92a4eebb4ec7d646166"

                l0 = layout.V0Layout()
                l1 = layout.V1Layout()

                # Populate the managed location using the v0 layout.
                for fhash in (hash1, hash2, hash3, hash4):
                        self.touch_old_file(fhash)

                # Migrate it to the v1 layout.
                fm = file_manager.FileManager(self.base_dir, False)
                for fhash in fm.walk():
                        self.assertEqual(fm.lookup(fhash),
                            os.path.join(self.base_dir, l1.lookup(fhash)))

                # After migration verify that no v0 parent directories remain.
                for fhash in fm.walk():
                        self.assertFalse(os.path.exists(os.path.dirname(
                            os.path.join(self.base_dir, l0.lookup(fhash)))))

                # Re-create the FileManager using v0 as the preferred layout.
                fm = file_manager.FileManager(self.base_dir, False,
                    layouts=[l0, l1])

                # Test that looking up a file stored under the v1 layout is
                # correctly moved to the v0 layout.
                for fhash in fm.walk():
                        self.assertEqual(fm.lookup(fhash),
                            os.path.join(self.base_dir, l0.lookup(fhash)))

        def test_3_replace(self):
                """Verify that insert will replace an existing file even though
                the hashval is the same."""

                # Verify that reverse layout migration works as expected.
                hash1 = "584b6ab7d7eb446938a02e57101c3a2fecbfb3cb"
                hash2 = "584b6ab7d7eb446938a02e57101c3a2fecbfb3cc"
                hash3 = "994b6ab7d7eb446938a02e57101c3a2fecbfb3cc"
                hash4 = "cc1f76cdad188714d1c3b92a4eebb4ec7d646166"

                l1 = layout.V1Layout()

                # Populate the managed location using the v0 layout.
                for fhash in (hash1, hash2, hash3, hash4):
                        self.touch_old_file(fhash, data="old-{0}".format(fhash))

                # Migrate it to the v1 layout and verify that each
                # file contains the expected data.
                fm = file_manager.FileManager(self.base_dir, False)
                for fhash in fm.walk():
                        loc = fm.lookup(fhash)
                        self.assertEqual(loc, os.path.join(self.base_dir,
                            l1.lookup(fhash)))

                        f = open(loc, "rb")
                        self.assertEqual(f.read(), misc.force_bytes(
                            "old-{0}".format(fhash)))
                        f.close()

                # Now replace each file using the old hashnames and verify
                # that the each contains the expected data.
                for fhash in fm.walk():
                        loc = os.path.join(self.base_dir, l1.lookup(fhash))
                        self.assertTrue(os.path.exists(loc))

                        npath = os.path.join(self.base_dir, "new-{0}".format(fhash))
                        nfile = open(npath, "wb")
                        nfile.write(misc.force_bytes("new-{0}".format(fhash)))
                        nfile.close()
                        fm.insert(fhash, npath)

                        loc = fm.lookup(fhash)
                        f = open(loc, "rb")
                        self.assertEqual(f.read(), misc.force_bytes(
                            "new-{0}".format(fhash)))
                        f.close()

if __name__ == "__main__":
        unittest.main()
