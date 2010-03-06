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

import os
import shutil
import time
import unittest

class TestFix(pkg5unittest.SingleDepotTestCase):

        # Don't need to restart depot for every test.
        persistent_setup = True

        amber10 = """
            open amber@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add file amber1 mode=0644 owner=root group=bin path=/etc/amber1
            add file amber2 mode=0644 owner=root group=bin path=/etc/amber2
            add hardlink path=/etc/amber.hardlink target=/etc/amber1
            close """

        licensed13 = """
            open licensed@1.3,5.11-0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed must-accept=True
            close """

        driver10 = """
            open drv@1.0,5.11-0
            add driver name=whee alias=pci8186,4321
            close drv
        """

        driver_prep10 = """
            open drv-prep@1.0,5.11-0
            add dir path=/tmp mode=755 owner=root group=root
            add file tmp/empty path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/empty path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/empty path=/etc/driver_classes mode=644 owner=root group=sys
            add file tmp/empty path=/etc/minor_perm mode=644 owner=root group=sys
            add file tmp/empty path=/etc/security/device_policy mode=644 owner=root group=sys
            add file tmp/empty path=/etc/security/extra_privs mode=644 owner=root group=sys
            close drv-prep
        """

        misc_files = [ "copyright.licensed", "license.licensed", "libc.so.1",
            "license.licensed", "license.licensed.addendum", "amber1", "amber2"]

        misc_files2 = {"tmp/empty": ""}

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.make_misc_files(self.misc_files2)
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.amber10)
                self.pkgsend_bulk(durl, self.licensed13)
                self.pkgsend_bulk(durl, self.driver10)
                self.pkgsend_bulk(durl, self.driver_prep10)

        def test_fix1(self):
                """Basic fix test: install the amber package, modify one of the
                files, and make sure it gets fixed.  """

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("install amber@1.0")

                index_file = os.path.join(self.img_path, "var","pkg","index",
                    "main_dict.ascii.v2")
                orig_mtime = os.stat(index_file).st_mtime
                time.sleep(1)

                victim = "etc/amber2"
                # Initial size
                size1 = self.file_size(victim)

                # Corrupt the file
                self.file_append(victim, "foobar")

                # Make sure the size actually changed
                size2 = self.file_size(victim)
                self.assertNotEqual(size1, size2)

                # Verify that unprivileged users are handled by fix.
                self.pkg("fix amber", exit=1, su_wrap=True)

                # Fix the package
                self.pkg("fix amber")

                # Make sure it's the same size as the original
                size2 = self.file_size(victim)
                self.assertEqual(size1, size2)

                # check that we didn't reindex
                new_mtime = os.stat(index_file).st_mtime
                self.assertEqual(orig_mtime, new_mtime)

        def test_fix2(self):
                """Hardlink test: make sure that a file getting fixed gets any
                hardlinks that point to it updated"""

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("install amber@1.0")

                victim = "etc/amber1"
                victimlink = "etc/amber.hardlink"

                self.file_append(victim, "foobar")
                self.pkg("fix amber")

                # Get the inode of the orig file
                i1 = self.file_inode(victim)
                # Get the inode of the new hardlink
                i2 = self.file_inode(victimlink)

                # Make sure the inode of the link is now different
                self.assertEqual(i1, i2)

        def test_fix3_license(self):
                """Verify that fix works with licenses that require acceptance
                and/or display."""

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("install --accept licensed@1.3")

                victim = "lib/libc.so.1"

                # Initial size
                size1 = self.file_size(victim)

                # Corrupt the file
                self.file_append(victim, "foobar")

                # Make sure the size actually changed
                size2 = self.file_size(victim)
                self.assertNotEqual(size1, size2)

                # Verify that the fix will fail since the license requires
                # acceptance.
                self.pkg("fix licensed", exit=6)

                # Verify that when the fix failed, it displayed the license
                # that required display.
                self.pkg("fix licensed | grep 'copyright.licensed'")
                self.pkg("fix licensed | grep -v 'license.licensed'")

                # Verify that fix will display all licenses when it fails,
                # if provided the --licenses option.
                self.pkg("fix --licenses licensed | grep 'license.licensed'")

                # Finally, verify that fix will succeed when a package requires
                # license acceptance if provided the --accept option.
                self.pkg("fix --accept licensed")

                # Make sure it's the same size as the original
                size2 = self.file_size(victim)
                self.assertEqual(size1, size2)

        def test_fix4_driver(self):
                """Verify that fixing a name collision for drivers doesn't
                cause a stack trace. Bug 14948"""

                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("install drv-prep")
                self.pkg("install drv")

                fh = open(os.path.join(self.get_img_path(), "etc",
                    "driver_aliases"), "wb")
                # Change the entry from whee to wqee.
                fh.write('wqee "pci8186,4321"\n')
                fh.close()

                self.pkg("fix drv")
                self.pkg("verify")

        def file_inode(self, path):
                file_path = os.path.join(self.get_img_path(), path)
                st = os.stat(file_path)
                return st.st_ino

        def file_size(self, path):
                file_path = os.path.join(self.get_img_path(), path)
                st = os.stat(file_path)
                return st.st_size

        def file_append(self, path, string):
                file_path = os.path.join(self.get_img_path(), path)
                f = file(file_path, "a+")
                f.write("\n%s\n" % string)
                f.close


if __name__ == "__main__":
        unittest.main()
