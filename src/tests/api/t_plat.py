
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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import unittest
import tempfile
import pkg.fmri as fmri
import pkg.portable.util as util
import pkg.portable as portable

class TestPlat(unittest.TestCase):
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

                    self.assertRaises(KeyError, portable.get_name_by_gid, 87285, "/", True)

    def testUser(self):        
            if os.path.exists("/etc/passwd"):
                    self.assertRaises(KeyError, portable.get_user_by_name,
                        "ThisShouldNotExist", "/", True)
                        
                    self.assertRaises(KeyError, portable.get_name_by_uid, 87285, "/", True)


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

if __name__ == "__main__":
        unittest.main()
