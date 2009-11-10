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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import shutil
import stat
import sys
import tempfile
import unittest

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)

import pkg5unittest

import pkg.file_layout.file_manager as file_manager
import pkg.file_layout.layout as layout

class TestFileManager(pkg5unittest.Pkg5TestCase):

        def setUp(self):
                self.pid = os.getpid()
                self.pwd = os.getcwd()

                self.__test_dir = os.path.join(tempfile.gettempdir(),
                    "ips.test.%d" % self.pid)

                try:
                        os.makedirs(self.__test_dir, 0755)
                except OSError, e:
                        if e.errno != errno.EEXIST:
                                raise e

        def tearDown(self):
                shutil.rmtree(self.__test_dir)

        @staticmethod
        def old_hash(s):
                return os.path.join(s[0:2], s[2:8], s)

        def touch_old_file(self, s):
                p = os.path.join(self.__test_dir, self.old_hash(s))
                if not os.path.exists(os.path.dirname(p)):
                        os.makedirs(os.path.dirname(p))
                fh = open(p, "wb")
                fh.write(s)
                fh.close()
                return p

        @staticmethod
        def check_exception(func, ex, str_bits, *args, **kwargs):
                try:
                        func(*args, **kwargs)
                except ex, e:
                        s = str(e)
                        for b in str_bits:
                                if b not in s:
                                        raise RuntimeError("Expected to find "
                                            "%s in %s" % (b, s))
                else:
                        raise RuntimeError("Didn't raise expected exception")

        def check_readonly(self, fm, unmoved, p):
                self.assert_(os.path.isfile(p))
                self.assertEqual(fm.lookup(unmoved), p)
                fh = fm.lookup(unmoved, opener=True)
                try:
                        self.assertEqual(fh.read(), unmoved)
                finally:
                        fh.close()
                self.assert_(os.path.isfile(p))

                self.check_exception(fm.insert,
                    file_manager.NeedToModifyReadOnlyFileManager,
                    ["create", unmoved], unmoved, p)
                self.assert_(os.path.isfile(p))
                self.check_exception(fm.remove,
                    file_manager.NeedToModifyReadOnlyFileManager,
                    ["remove", unmoved], unmoved)
                self.assert_(os.path.isfile(p))

        def test_1(self):
                """Verify base functionality works as expected."""

                t = tempfile.gettempdir()
                no_dir = os.path.join(t, "not_exist")
                
                self.check_exception(file_manager.FileManager,
                    file_manager.NeedToModifyReadOnlyFileManager,
                    ["create", no_dir], no_dir, readonly=True)

                # Test that a read only FileManager won't modify the file
                # system.
                fm = file_manager.FileManager(self.__test_dir, readonly=True)
                self.assertEqual(os.listdir(self.__test_dir), [])

                unmoved = "4b7c923af3a047d4685a39ad7bc9b0382ccde671"

                p = self.touch_old_file(unmoved)
                self.check_readonly(fm, unmoved, p)

                self.assertEqual(set(fm.walk()),
                    set([unmoved]))

                # Test a FileManager that can write to the file system.
                fm = file_manager.FileManager(self.__test_dir, False)

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
                self.assert_(os.path.isfile(p1))
                self.assert_(os.path.isdir(os.path.dirname(p1)))
                self.assertEqual(fm.lookup(hash1),
                    os.path.join(self.__test_dir, l.lookup(hash1)))
                self.assert_(not os.path.exists(p1))
                self.assert_(not os.path.exists(os.path.dirname(p1)))
                fm.remove(hash1)

                # Test that looking up a file stored under the old system gets
                # moved to the correct location, that the new location is
                # correctly returned, and that the old location's parent
                # directory still exists as multiple files were stored there.
                # Finally, remove file stored in the old location for the next
                # few tests.
                p1 = self.touch_old_file(hash1)
                p2 = self.touch_old_file(hash2)
                self.assert_(os.path.isfile(p1))
                self.assert_(os.path.isdir(os.path.dirname(p1)))
                self.assertEqual(fm.lookup(hash1),
                    os.path.join(self.__test_dir, l.lookup(hash1)))
                self.assert_(not os.path.exists(p1))
                self.assert_(os.path.exists(os.path.dirname(p1)))
                fm.remove(hash2)

                # Test that looking up a file stored under the old system gets
                # moved and that it returns a file handle with the correct
                # contents.
                p4 = self.touch_old_file(hash4)
                self.assert_(os.path.isfile(p4))
                self.assert_(os.path.isdir(os.path.dirname(p4)))
                fh = fm.lookup(hash4, opener=True)
                try:
                        self.assertEqual(fh.read(), hash4)
                finally:
                        fh.close()
                self.assert_(not os.path.exists(p4))
                self.assert_(not os.path.exists(os.path.dirname(p4)))

                # Test that inserting a file already in the file manager just
                # moves the old file if necessary.
                p3 = self.touch_old_file(hash3)
                self.assert_(os.path.isfile(p3))
                self.assert_(os.path.isdir(os.path.dirname(p3)))
                
                rh3_fd, raw_hash_3_loc = tempfile.mkstemp(dir=self.__test_dir)
                rh3_fh = os.fdopen(rh3_fd, "w")
                rh3_fh.write("foo")
                rh3_fh.close()
                
                fm.insert(hash3, raw_hash_3_loc)

                self.assert_(not os.path.exists(p3))
                self.assert_(not os.path.exists(os.path.dirname(p3)))

                fh = fm.lookup(hash3, opener=True)
                try:
                        self.assertEqual(fh.read(), hash3)
                finally:
                        fh.close()

                # Test that walk returns the expected values.
                self.assertEqual(set(fm.walk()),
                    set([unmoved, hash1, hash4, hash3]))

                # Test that walking with a different set of layouts works as
                # expected.
                fm2 = file_manager.FileManager(self.__test_dir, readonly=True,
                    layouts=[layout.get_preferred_layout()])

                fs = set([hash1, hash4, hash3])
                try:
                        for i in fm2.walk():
                                fs.remove(i)
                except file_manager.UnrecognizedFilePaths, e:
                        self.assertEqual(e.fps, [p[len(self.__test_dir) + 1:]])
                self.assertEqual(fs, set())

                # Test removing a file works and removes the containing
                # directory and that remove removes all instances of a hash
                # from the file manager.
                hash3_loc = os.path.join(self.__test_dir, l.lookup(hash3))
                v0_hash3_loc = self.touch_old_file(hash3)

                self.assert_(os.path.isfile(hash3_loc))
                self.assert_(os.path.isfile(v0_hash3_loc))
                fm.remove(hash3)
                self.assertEqual(fm.lookup(hash3), None)
                self.assert_(not os.path.exists(hash3_loc))
                self.assert_(not os.path.exists(os.path.dirname(hash3_loc)))
                self.assert_(not os.path.exists(v0_hash3_loc))
                self.assert_(not os.path.exists(os.path.dirname(v0_hash3_loc)))
                self.assert_(os.path.isfile(fm.lookup(hash1)))
                
                rh2_fd, raw_hash_2_loc = tempfile.mkstemp(dir=self.__test_dir)
                rh2_fh = os.fdopen(rh2_fd, "w")
                rh2_fh.write(hash2)
                rh2_fh.close()

                fm.insert(hash2, raw_hash_2_loc)
                h2_loc = fm.lookup(hash2)
                self.assert_(os.path.isfile(fm.lookup(hash2)))
                # Test that the directory has two files in it as expected.
                self.assertEqual(set(os.listdir(
                    os.path.dirname(fm.lookup(hash2)))),
                    set([hash1, hash2]))
                # Test removing one of the two files doesn't remove the other.
                fm.remove(hash1)
                self.assert_(os.path.isfile(h2_loc))
                self.assertEqual(fm.lookup(hash2), h2_loc)
                self.assertEqual(fm.lookup(hash1), None)
                # Test that removing the second file works and removes the
                # containing directory as well.
                fm.remove(hash2)
                self.assert_(not os.path.exists(h2_loc))
                self.assert_(not os.path.exists(os.path.dirname(h2_loc)))

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
                for hash in (hash1, hash2, hash3, hash4):
                        self.touch_old_file(hash)

                # Migrate it to the v1 layout.
                fm = file_manager.FileManager(self.__test_dir, False)
                for hash in fm.walk():
                        self.assertEqual(fm.lookup(hash),
                            os.path.join(self.__test_dir, l1.lookup(hash)))

                # After migration verify that no v0 parent directories remain.
                for hash in fm.walk():
                        self.assertFalse(os.path.exists(os.path.dirname(
                            os.path.join(self.__test_dir, l0.lookup(hash)))))

                # Re-create the FileManager using v0 as the preferred layout.
                fm = file_manager.FileManager(self.__test_dir, False,
                    layouts=[l0, l1])

                # Test that looking up a file stored under the v1 layout is
                # correctly moved to the v0 layout.
                for hash in fm.walk():
                        self.assertEqual(fm.lookup(hash),
                            os.path.join(self.__test_dir, l0.lookup(hash)))

