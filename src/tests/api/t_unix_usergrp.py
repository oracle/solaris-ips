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
import shutil
import sys
import tempfile
import pkg.portable as portable

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestUserGroup(pkg5unittest.Pkg5TestCase):

        def setUp(self):
                self.tempdir = tempfile.mkdtemp()
                os.makedirs(os.path.join(self.tempdir, "etc"))

        def tearDown(self):
                shutil.rmtree(self.tempdir)

        def testGroup1(self):
                if not os.path.exists("/etc/group"):
                        return

                grpfile = file(os.path.join(self.tempdir, "etc", "group"), "w")
                grpfile.write( \
"""root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
uucp::5:root
mail::6:root
tty::7:root,adm""")
                grpfile.close()

                self.assertRaises(KeyError, portable.get_group_by_name,
                    "ThisShouldNotExist", self.tempdir, True)

                self.assert_(0 == \
                    portable.get_group_by_name("root", self.tempdir, True))

                self.assertRaises(KeyError, portable.get_name_by_gid,
                    12345, self.tempdir, True)

        def testGroup2(self):
                """ Test with a missing group file """
                if not os.path.exists("/etc/group"):
                        return

                self.assertRaises(KeyError, portable.get_group_by_name,
                    "ThisShouldNotExist", self.tempdir, True)

                # This should work on unix systems, since we'll "bootstrap"
                # out to the OS's version.  And AFAIK all unix systems have
                # a group with gid 0.
                grpname = portable.get_name_by_gid(0, self.tempdir, True)
                self.assert_(0 == \
                    portable.get_group_by_name(grpname, self.tempdir, True))

        def testGroup3(self):
                """ Test with corrupt/oddball group file """
                if not os.path.exists("/etc/group"):
                        return

                grpfile = file(os.path.join(self.tempdir, "etc", "group"), "w")
                grpfile.write( \
"""root::0:
blorg
bin::2:root,daemon

corrupt:x
adm::4:root,daemon
uucp::5:root
mail::6:root
tty::7:root,adm
+""")
                grpfile.close()
                self.assert_(0 == \
                    portable.get_group_by_name("root", self.tempdir, True))
                self.assert_(7 == \
                    portable.get_group_by_name("tty", self.tempdir, True))

                self.assertRaises(KeyError, portable.get_group_by_name,
                    "ThisShouldNotExist", self.tempdir, True)

                self.assertRaises(KeyError, portable.get_group_by_name,
                    "corrupt", self.tempdir, True)

                self.assertRaises(KeyError, portable.get_group_by_name,
                    570, self.tempdir, True)

        def testGroup4(self):
                """ Test with a group name line in the group file that
                starts with a "+". (See bug #4470 for more details). """
                if not os.path.exists("/etc/group"):
                        return

                grpfile = file(os.path.join(self.tempdir, "etc", "group"), "w")
                grpfile.write( \
"""root::0:
bin::2:root,daemon
+plusgrp
adm::4:root,daemon
uucp::5:root
mail::6:root
tty::7:root,adm
+""")
                grpfile.close()
                self.assert_(0 == \
                    portable.get_group_by_name("root", self.tempdir, True))
                self.assert_(7 == \
                    portable.get_group_by_name("tty", self.tempdir, True))

                self.assertRaises(KeyError, portable.get_group_by_name,
                    "plusgrp", self.tempdir, True)


        def testUser1(self):
                if not os.path.exists("/etc/passwd"):
                        return

                passwd = file(os.path.join(self.tempdir, "etc", "passwd"), "w")
                passwd.write( \
"""root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
lp:x:71:8:Line Printer Admin:/usr/spool/lp:
uucp:x:5:5:uucp Admin:/usr/lib/uucp:
moop:x:999:999:moop:/usr/moop:""")
                passwd.close()

                self.assertRaises(KeyError, portable.get_user_by_name,
                    "ThisShouldNotExist", self.tempdir, True)

                self.assert_(0 == \
                    portable.get_user_by_name("root", self.tempdir, True))
                self.assert_(999 == \
                    portable.get_user_by_name("moop", self.tempdir, True))

                self.assertRaises(KeyError, portable.get_name_by_uid,
                    12345, self.tempdir, True)


        def testUser2(self):
                """ Test with a missing passwd file """
                if not os.path.exists("/etc/passwd"):
                        return

                self.assertRaises(KeyError, portable.get_user_by_name,
                    "ThisShouldNotExist", self.tempdir, True)

                # This should work on unix systems, since we'll "bootstrap"
                # out to the OS's version.
                self.assert_(0 == \
                    portable.get_user_by_name("root", self.tempdir, True))
                self.assert_("root" == \
                    portable.get_name_by_uid(0, self.tempdir, True))


        def testUser3(self):
                """ Test with an oddball/corrupt passwd file """
                if not os.path.exists("/etc/passwd"):
                        return

                passwd = file(os.path.join(self.tempdir, "etc", "passwd"), "w")
                passwd.write( \
"""root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:

blorg
corrupt:x

adm:x:4:4:Admin:/var/adm:
lp:x:71:8:Line Printer Admin:/usr/spool/lp:
uucp:x:5:5:uucp Admin:/usr/lib/uucp:
+""")
                passwd.close()
                self.assert_(0 == \
                    portable.get_user_by_name("root", self.tempdir, True))
                self.assert_("uucp" == \
                    portable.get_name_by_uid(5, self.tempdir, True))

                self.assertRaises(KeyError, portable.get_user_by_name,
                    "ThisShouldNotExist", self.tempdir, True)

                self.assertRaises(KeyError, portable.get_user_by_name,
                    "corrupt", self.tempdir, True)

                self.assertRaises(KeyError, portable.get_user_by_name,
                    999, self.tempdir, True)

        def testUser4(self):
                """ Test with a user name line in the passwd file that
                starts with a "+". (See bug #4470 for more details). """
                if not os.path.exists("/etc/passwd"):
                        return

                passwd = file(os.path.join(self.tempdir, "etc", "passwd"), "w")
                passwd.write( \
"""root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
+plususer
adm:x:4:4:Admin:/var/adm:
lp:x:71:8:Line Printer Admin:/usr/spool/lp:
uucp:x:5:5:uucp Admin:/usr/lib/uucp:
+""")
                passwd.close()
                self.assert_(0 == \
                    portable.get_user_by_name("root", self.tempdir, True))
                self.assert_("uucp" == \
                    portable.get_name_by_uid(5, self.tempdir, True))

                self.assertRaises(KeyError, portable.get_user_by_name,
                    "plususer", self.tempdir, True)

if __name__ == "__main__":
        unittest.main()
