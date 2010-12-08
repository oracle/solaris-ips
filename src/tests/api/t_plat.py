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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import os
import shutil
import sys
import tempfile
import pkg.pkgsubprocess as subprocess
import pkg.fmri as fmri
import pkg.client.image as image
import pkg.portable.util as util
import pkg.portable as portable

class TestPlat(pkg5unittest.Pkg5TestCase):
                
        def testbasic(self):
                portable.get_isainfo()
                portable.get_release()
                portable.get_platform()


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
                cwd = os.getcwdu()
                exefilesrc = 'C:\\Windows\\system32\\more.com'
                self.assert_(os.path.exists(exefilesrc))

                # create an image, copy an executable into it, 
                # run the executable, replace the executable
                tdir1 = tempfile.mkdtemp()
                img1 = image.Image(tdir1, imgtype=image.IMG_USER,
                    should_exist=False, user_provided_dir=True)
                img1.history.client_name = "pkg-test"
                img1.set_attrs(False, "test",
                    origins=["http://localhost:10000"], refresh_allowed=False)
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
                # This is a white-box test
                # To simulate running another process, we delete the cache
                # and call get_trashdir as if another file was being moved
                # to the trash.
                os_windows.cached_image_info = []
                os_windows.get_trashdir(exefile)
                self.assert_(not os.path.exists(os.path.join(img1.imgdir, 
                    os_windows.trashname)))

                # cleanup
                os.chdir(cwd)
                shutil.rmtree(tdir1)

        def testRemoveOfRunningExecutable(self):
                if util.get_canonical_os_type() != 'windows':
                        return
                import pkg.portable.os_windows as os_windows
                cwd = os.getcwdu()
                exefilesrc = 'C:\\Windows\\system32\\more.com'
                self.assert_(os.path.exists(exefilesrc))

                # create an image, copy an executable into it, 
                # run the executable, remove the executable
                tdir1 = tempfile.mkdtemp()
                img1 = image.Image(tdir1, imgtype=image.IMG_USER,
                    should_exist=False, user_provided_dir=True)
                img1.history.client_name = "pkg-test"
                img1.set_attrs(False, "test",
                    origins=["http://localhost:10000"], refresh_allowed=False)
                exefile = os.path.join(tdir1, 'less.com')
                shutil.copyfile(exefilesrc, exefile)
                proc = subprocess.Popen([exefile], stdin = subprocess.PIPE)
                self.assertRaises(OSError, os.unlink, exefile)
                portable.remove(exefile)
                self.assert_(not os.path.exists(exefile))
                proc.communicate()

                # Make sure that the moved executable gets deleted
                # This is a white-box test
                # To simulate running another process, we delete the cache
                # and call get_trashdir as if another file was being moved
                # to the trash.
                os_windows.cached_image_info = []
                os_windows.get_trashdir(exefile)
                self.assert_(not os.path.exists(os.path.join(img1.imgdir,
                    os_windows.trashname)))

                # cleanup
                os.chdir(cwd)
                shutil.rmtree(tdir1)
            
if __name__ == "__main__":
        unittest.main()
