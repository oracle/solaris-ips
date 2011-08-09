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
# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import pkg.misc as misc


class TestPkgRevert(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkgs = """
            open A@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file1 mode=0555 owner=root group=bin path=etc/file1
            close
            open B@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file2 mode=0555 owner=root group=bin path=etc/file2 revert-tag=bob
            close
            open C@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file3 mode=0555 owner=root group=bin path=etc/file3 revert-tag=bob revert-tag=ted
            close
            open D@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file4 mode=0555 owner=root group=bin path=etc/file4 revert-tag=bob revert-tag=ted revert-tag=carol
            close
            open A@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file1 mode=0555 owner=root group=bin path=etc/file1 preserve=true
            close
            open B@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file2 mode=0555 owner=root group=bin path=etc/file2 revert-tag=bob preserve=true
            close
            open C@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file3 mode=0555 owner=root group=bin path=etc/file3 revert-tag=bob revert-tag=ted preserve=true
            close
            open D@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file4 mode=0555 owner=root group=bin path=etc/file4 revert-tag=bob revert-tag=ted revert-tag=carol preserve=true
            close"""

        misc_files = ["etc/file1", "etc/file2", "etc/file3", "etc/file4"]

        def damage_all_files(self):
                ubin = portable.get_user_by_name("bin", None, False)
                groot = portable.get_group_by_name("root", None, False)
                for path in self.misc_files:
                        file_path = os.path.join(self.get_img_path(), path)
                        with open(file_path, "a+") as f:
                                f.write("\nbogus\n")
                        os.chown(file_path, ubin, groot)
                        os.chmod(file_path, misc.PKG_RO_FILE_MODE)

        def remove_file(self, path):
                os.unlink(os.path.join(self.get_img_path(), path))

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def test_revert(self):
                plist = self.pkgsend_bulk(self.rurl, self.pkgs)
                self.image_create(self.rurl)
                # try reverting non-editable files
                self.pkg("install A@1.0 B@1.0 C@1.0 D@1.0")
                self.pkg("verify")
                # modify files
                self.damage_all_files()
                # make sure we broke 'em
                self.pkg("verify A", exit=1)
                self.pkg("verify B", exit=1)
                self.pkg("verify C", exit=1)
                self.pkg("verify D", exit=1)

                # revert damage to A by path
                self.pkg("revert /etc/file1")
                self.pkg("verify A")
                self.pkg("verify B", exit=1)
                self.pkg("verify C", exit=1)
                self.pkg("verify D", exit=1)
                self.damage_all_files()

                # revert damage to D by tag
                self.pkg("revert --tagged carol")
                self.pkg("verify A", exit=1)
                self.pkg("verify B", exit=1)
                self.pkg("verify C", exit=1)
                self.pkg("verify D")
                self.damage_all_files()

                # revert damage to C,D by tag
                self.pkg("revert -vvv --tagged ted")
                self.pkg("verify A", exit=1)
                self.pkg("verify B", exit=1)
                self.pkg("verify C")
                self.pkg("verify D")
                self.damage_all_files()

                # revert damage to B, C, D by tag and test the parsable output.
                self.pkg("revert -n --parsable=0 --tagged bob")
                self.assertEqualParsable(self.output,
                    affect_packages=[plist[1], plist[2], plist[3]])
                self.pkg("revert --parsable=0 --tagged bob")
                self.assertEqualParsable(self.output,
                    affect_packages=[plist[1], plist[2], plist[3]])
                self.pkg("verify A", exit=1)
                self.pkg("verify B")
                self.pkg("verify C")
                self.pkg("verify D")

                # fix A & update to versions w/ editable files
                self.pkg("revert /etc/file1")
                self.pkg("verify")
                self.pkg("update")
                self.pkg("list A@1.1 B@1.1 C@1.1 D@1.1")
                self.pkg("revert /etc/file1", exit=4)
                self.pkg("revert --tagged bob", exit=4) # nothing to do
                self.damage_all_files()
                self.pkg("revert /etc/file1")
                self.pkg("revert --tagged bob")
                self.pkg("revert /etc/file1", exit=4)
                self.pkg("revert --tagged bob", exit=4) # nothing to do
                self.pkg("verify")
                # handle missing files too
                self.remove_file("etc/file1")
                self.pkg("verify A", exit=1)
                self.pkg("revert /etc/file1")
                self.pkg("revert /etc/file1", exit=4)

                # check that we handle files that don't exist correctly
                self.pkg("revert /no/such/file", exit=1)
                # since tags can be missing, just nothing to do for
                # tags that we cannot find
                self.pkg("revert --tagged no-such-tag", exit=4)

if __name__ == "__main__":
        unittest.main()
