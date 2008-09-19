#!/usr/bin/python2.4
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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import os
import subprocess
import shutil
import sys
import tempfile
import pkg.fmri as fmri
import pkg.client.image as image
import pkg.portable.util as util
import pkg.portable as portable

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestPlat(pkg5unittest.Pkg5TestCase):
        def setUp(self):
                pass
                
        def testbasic(self):
                portable.get_isainfo()
                portable.get_release()
                portable.get_platform()

        def testGroup(self):
                if os.path.exists("/etc/group"):
                        self.assertRaises(KeyError, portable.get_group_by_name,
                            "ThisShouldNotExist", "/", True)

                        self.assertRaises(KeyError, portable.get_name_by_gid, 
                            87285, "/", True)

        def testUser(self):        
                if os.path.exists("/etc/passwd"):
                        self.assertRaises(KeyError, portable.get_user_by_name,
                            "ThisShouldNotExist", "/", True)

                        self.assertRaises(KeyError, portable.get_name_by_uid, 
                            87285, "/", True)


        def testAdmin(self):
                if os.name == 'posix' and os.getuid() == 0:
                        self.assert_(portable.is_admin())
                if os.name == 'posix' and os.getuid() != 0:
                        self.assert_(not portable.is_admin())

        def testUtils(self):
                self.assertNotEqual("unknown", util.get_canonical_os_type())
                self.assertNotEqual("unknown", util.get_canonical_os_name())

        def testRelease(self):
                rel = util.get_os_release()
                # make sure it can be used in an fmri
                test_fmri = fmri.PkgFmri("testpkg", build_release = rel)

        def testForcibleRename(self):
                # rename a file on top of another file which already exists
                (fd1, path1) = tempfile.mkstemp()
                os.write(fd1, "foo")
                (fd2, path2) = tempfile.mkstemp()
                os.write(fd2, "bar")
                os.close(fd1)
                os.close(fd2)
                portable.rename(path1, path2)
                self.failIf(os.path.exists(path1))
                self.failUnless(os.path.exists(path2))
                fd2 = os.open(path2, os.O_RDONLY)
                self.assertEquals(os.read(fd2, 3), "foo")
                os.close(fd2)
                os.unlink(path2)

        def testRenameOfRunningExecutable(self):
                if util.get_canonical_os_type() != 'windows':
                        return
                import pkg.portable.os_windows as os_windows
                exefilesrc = 'C:\\Windows\\system32\\more.com'
                self.assert_(os.path.exists(exefilesrc))

                # create an image, copy an executable into it, 
                # run the executable, replace the executable
                tdir1 = tempfile.mkdtemp()
                img1 = image.Image()
                img1.history.client_name = "pkg-test"
                img1.set_attrs(image.IMG_USER, tdir1, False, "test", 
                    "http://localhost:10000")
                exefile = os.path.join(tdir1, 'less.com')
                shutil.copyfile(exefilesrc, exefile)
                proc = subprocess.Popen([exefile], stdin = subprocess.PIPE)
                self.assertRaises(OSError, os.unlink, exefile)
                fd1, path1 = tempfile.mkstemp(dir = tdir1)
                os.write(fd1, "foo")
                os.close(fd1)
                portable.rename(path1, exefile)
                fd2 = os.open(exefile, os.O_RDONLY)
                self.assertEquals(os.read(fd2, 3), "foo")
                os.close(fd2)
                proc.communicate()

                # Make sure that the moved executable gets deleted
                # First do a rename in another image
                tdir2 = tempfile.mkdtemp()
                img2 = image.Image()
                img2.history.client_name = "pkg-test"
                img2.set_attrs(image.IMG_USER, tdir2, False, "test", 
                    "http://localhost:10000")
                fd2, path2 = tempfile.mkstemp(dir = tdir2)
                os.write(fd2, "bar")
                os.close(fd2)
                portable.rename(path2, os.path.join(tdir2, "bar"))
                # Now do another rename in the original image
                # This should cause the executable to deleted from the trash
                portable.rename(exefile, os.path.join(tdir1, "foo"))
                self.assert_(not os.path.exists(os.path.join(img1.imgdir, 
                    os_windows.trashname)))

                # cleanup
                shutil.rmtree(img1.get_root())
                shutil.rmtree(img2.get_root())

        def testRemoveOfRunningExecutable(self):
                if util.get_canonical_os_type() != 'windows':
                        return
                import pkg.portable.os_windows as os_windows
                exefilesrc = 'C:\\Windows\\system32\\more.com'
                self.assert_(os.path.exists(exefilesrc))

                # create an image, copy an executable into it, 
                # run the executable, remove the executable
                tdir1 = tempfile.mkdtemp()
                img1 = image.Image()
                img1.history.client_name = "pkg-test"
                img1.set_attrs(image.IMG_USER, tdir1, False, "test", 
                    "http://localhost:10000")
                exefile = os.path.join(tdir1, 'less.com')
                shutil.copyfile(exefilesrc, exefile)
                proc = subprocess.Popen([exefile], stdin = subprocess.PIPE)
                self.assertRaises(OSError, os.unlink, exefile)
                portable.remove(exefile)
                self.assert_(not os.path.exists(exefile))
                proc.communicate()

                # Make sure that the removed executable gets deleted
                # First do a rename in another image
                tdir2 = tempfile.mkdtemp()
                img2 = image.Image()
                img2.history.client_name = "pkg-test"
                img2.set_attrs(image.IMG_USER, tdir2, False, "test", 
                    "http://localhost:10000")
                fd2, path2 = tempfile.mkstemp(dir = tdir2)
                os.write(fd2, "bar")
                os.close(fd2)
                portable.rename(path2, os.path.join(tdir2, "bar"))
                # Now do another rename in the original image
                # This should cause the executable to deleted from the trash
                fd3, path3 = tempfile.mkstemp(dir = tdir1)
                os.write(fd3, "baz")
                os.close(fd3)
                portable.rename(path3, os.path.join(tdir1, "foo"))
                self.assert_(not os.path.exists(os.path.join(img1.imgdir, 
                    os_windows.trashname)))

                # cleanup
                shutil.rmtree(img1.get_root())
                shutil.rmtree(img2.get_root())
            
if __name__ == "__main__":
        unittest.main()
