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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import time
import unittest

class TestFix(testutils.SingleDepotTestCase):
        amber10 = """
            open amber@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add file /tmp/amber1 mode=0644 owner=root group=bin path=/etc/amber1
            add file /tmp/amber2 mode=0644 owner=root group=bin path=/etc/amber2
            add hardlink path=/etc/amber.hardlink target=/etc/amber1
            close
        """

        misc_files = ["/tmp/amber1", "/tmp/amber2"]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close()
                        self.debug("wrote %s" % p)
                
        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        def test_fix1(self):
                """Basic fix test: install the amber package, modify one of the
                files, and make sure it gets fixed.  """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.amber10)
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

                # Fix the package
                self.pkg("fix amber")
                
                # Make sure it's the same size as the original
                size2 = self.file_size(victim)
                self.assertEqual(size1, size2)

                new_mtime = os.stat(index_file).st_mtime
                self.assertEqual(orig_mtime, new_mtime)

        def test_fix2(self):
                """Hardlink test: make sure that a file getting fixed gets any
                hardlinks that point to it updated"""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.amber10)
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
