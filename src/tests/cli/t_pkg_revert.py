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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import pkg.misc as misc
import sys

try:
        import pkg.sha512
        sha512_supported = True
except ImportError:
        sha512_supported = False

class TestPkgRevert(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkgs = """
            open A@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file1 mode=0555 owner=root group=bin path=etc/file1
            close
            # B@1.0 is published as part of pkgs2
            # C@1.0 is published as part of pkgs3
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
            close
            open W@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc revert-tag=bob=*
            close
            open X@1.0,5.11-0
            add file etc/file5 mode=0555 owner=root group=bin path=etc/wombat/file1
            close
            open Y@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc/y-dir revert-tag=bob=*
            close
            """

        # A set of packages that we publish with additional hash attributes
        pkgs2 = """
            open B@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file2 mode=0555 owner=root group=bin path=etc/file2 revert-tag=bob
            close
            open dev@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dev revert-tag=init-dev=*
            add dir mode=0755 owner=root group=bin path=dev/cfg revert-tag=init-dev=*
            add file dev/foo path=dev/foo mode=0555 owner=root group=bin
            add file dev/cfg/bar path=dev/cfg/bar mode=0555 owner=root group=bin
            add file dev/cfg/blah path=dev/cfg/blah mode=0555 owner=root group=bin
            close
            open dev2@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dev revert-tag=init-dev=*
            add dir mode=0755 owner=root group=bin path=dev/cfg revert-tag=init-dev=*
            add file dev/cfg/bar1 path=dev/cfg/bar1 mode=0555 owner=root group=bin
            add file dev/cfg/bar2 path=dev/cfg/bar2 mode=0555 owner=root group=bin preserve=true revert-tag=init-dev
            close
            """

        # A set of packages that we publish with additional hash attributes
        pkgs3 = """
            open C@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/file3 mode=0555 owner=root group=bin path=etc/file3 revert-tag=bob revert-tag=ted
            close
            """

        misc_files = ["etc/file1", "etc/file2", "etc/file3", "etc/file4",
            "etc/file5"]

        additional_files = ["dev/foo", "dev/cfg/bar", "dev/cfg/blah",
            "dev/cfg/bar1", "dev/cfg/bar2"]

        def damage_all_files(self):
                self.damage_files(self.misc_files)

        def damage_files(self, paths):
                ubin = portable.get_user_by_name("bin", None, False)
                groot = portable.get_group_by_name("root", None, False)
                for path in paths:
                        file_path = os.path.join(self.get_img_path(), path)
                        with open(file_path, "a+") as f:
                                f.write("\nbogus\n")
                        os.chown(file_path, ubin, groot)
                        os.chmod(file_path, misc.PKG_RO_FILE_MODE)

        def remove_file(self, path):
                os.unlink(os.path.join(self.get_img_path(), path))

        def remove_dir(self, path):
                os.rmdir(os.path.join(self.get_img_path(), path))

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.make_misc_files(self.additional_files)
                self.plist = self.pkgsend_bulk(self.rurl, self.pkgs)
                self.plist.extend(self.pkgsend_bulk(self.rurl, self.pkgs2,
                    debug_hash="sha1+sha256"))
                if sha512_supported:
                        self.plist.extend(self.pkgsend_bulk(self.rurl,
                            self.pkgs3, debug_hash="sha1+sha512t_256"))
                else:
                        self.plist.extend(self.pkgsend_bulk(self.rurl,
                            self.pkgs3))

        def test_revert(self):
                self.image_create(self.rurl)
                # try reverting non-editable files
                self.pkg("install A@1.0 B@1.0 C@1.0 D@1.0")
                self.pkg("verify")
                # modify files
                self.damage_all_files()
                # make sure we broke 'em
                self.pkg("verify A", exit=1)

                # We expect that the SHA-2 hash is used whenever there are SHA-2
                # hashes on the action. Even though this client is run in
                # "SHA-1" mode as well as "SHA-2" mode, we always verify with
                # the most-preferred hash available.
                self.pkg("-D hash=sha1+sha256 verify B", exit=1)
                sha2 = "e3868252b2b2de64e85f5b221e46eb23c428fe5168848eb36d113c66628131ce"
                self.assertTrue(sha2 in self.output)
                self.pkg("verify B", exit=1)
                self.assertTrue(sha2 in self.output)

                if sha512_supported:
                        self.pkg("-D hash=sha1+sha512t_256 verify C", exit=1)
                        sha2 = "13729cb7183961b48ce300c2588c86ad123e7c636f38a0f3c8408a75fd079d09"
                        self.assertTrue(sha2 in self.output, self.output)
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
                self.debug("\n".join(self.plist))
                self.assertEqualParsable(self.output,
                    affect_packages=[self.plist[9], self.plist[12],
                    self.plist[1]])
                # When reverting damage, we always verify using the
                # most-preferred hash, but retrieve content with the
                # least-preferred hash: -D hash=sha1+sha256 and
                # -D hash=sha1+sha512t_256 should have no effect here whatsoever,
                # but -D hash=sha256 and -D hash=sha512t_256 should fail because
                # our repository stores its files by the SHA1 hash.
                self.pkg("-D hash=sha256 revert --parsable=0 --tagged bob",
                    exit=1)
                if sha512_supported:
                        self.pkg("-D hash=sha512t_256 revert --parsable=0 \
                            --tagged ted", exit=1)
                        self.pkg("-D hash=sha1+512_256 revert -n --parsable=0 \
                            --tagged ted")
                        self.assertEqualParsable(self.output,
                            affect_packages=[self.plist[12], self.plist[1]])
                self.pkg("-D hash=sha1+sha256 revert --parsable=0 --tagged bob")
                self.assertEqualParsable(self.output,
                    affect_packages=[self.plist[9], self.plist[12],
                    self.plist[1]])
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
                self.pkg("verify")
                # check that we handle missing files when tagged
                self.remove_file("etc/file2")
                self.pkg("verify", exit=1)
                self.pkg("revert --tagged bob")
                self.pkg("verify")
                # make sure we got the default contents
                self.pkg("revert --tagged bob", exit=4)
                # check that we handle files that don't exist correctly
                self.pkg("revert /no/such/file", exit=1)
                # since tags can be missing, just nothing to do for
                # tags that we cannot find
                self.pkg("revert --tagged no-such-tag", exit=4)

        def test_revert_2(self):
                """exercise new directory revert facility"""
                self.image_create(self.rurl)
                some_files = ["etc/A", "etc/B", "etc/C"]

                # first try reverting tag that doesn't exist
                self.pkg("install A@1.1 W@1")
                self.pkg("verify")
                self.pkg("revert --tagged alice", 4)
                self.pkg("verify")

                # now revert a tag that exists, but doesn't need
                # any work done
                self.pkg("revert --tagged bob", 4)

                # now create some unpackaged files
                self.create_some_files(some_files)
                self.files_are_all_there(some_files)
                # revert them
                self.pkg("revert --tagged bob", 0)
                self.pkg("verify")
                self.files_are_all_missing(some_files)

                # now create some unpackaged directories and files
                some_dirs = ["etc/X/", "etc/Y/", "etc/Z/C", "etc/X/XX/"]
                self.create_some_files(some_dirs + some_files)
                self.files_are_all_there(some_dirs + some_files)
                # revert them
                self.pkg("revert --tagged bob", 0)
                self.pkg("verify")
                self.files_are_all_missing(some_dirs + some_files)

                # install a package w/ implicit directories
                self.pkg("install X@1.0")
                self.create_some_files(some_dirs + some_files + ["etc/wombat/XXX"])
                self.files_are_all_there(some_dirs + some_files + ["etc/wombat/XXX"])
                # revert them
                self.pkg("revert --tagged bob", 0)
                self.pkg("verify")
                self.files_are_all_missing(some_dirs + some_files)
                self.files_are_all_there(["etc/wombat/XXX"])
                # mix and match w/ regular tests
                self.pkg("install B@1.1 C@1.1 D@1.1")
                self.pkg("verify")
                self.damage_all_files()
                self.create_some_files(some_dirs + some_files + ["etc/wombat/XXX"])
                self.files_are_all_there(some_dirs + some_files + ["etc/wombat/XXX"])
                self.pkg("verify A", exit=1)
                self.pkg("verify B", exit=1)
                self.pkg("verify C", exit=1)
                self.pkg("verify D", exit=1)
                self.pkg("revert --tagged bob")
                self.pkg("revert /etc/file1")
                self.pkg("verify")
                self.files_are_all_missing(some_dirs + some_files)
                self.files_are_all_there(["etc/wombat/XXX"])
                # generate some problems
                self.pkg("install Y")
                self.pkg("verify")
                self.remove_dir("etc/y-dir")
                self.pkg("revert --tagged bob", 4)
                self.pkg("fix Y")
                self.pkg("verify")
                self.pkg("revert --tagged bob", 4)

        def test_revert_3(self):
                """duplicate usage in /dev as per Ethan's mail"""
                self.image_create(self.rurl)
                some_files = ["dev/xxx", "dev/yyy", "dev/zzz",
                              "dev/dir1/aaaa", "dev/dir1/bbbb", "dev/dir2/cccc",
                              "dev/cfg/ffff", "dev/cfg/gggg",
                              "dev/cfg/dir3/iiii", "dev/cfg/dir3/jjjj"]

                some_dirs = ["dev/dir1/", "dev/dir1/", "dev/dir2/", "dev/cfg/dir3/"]
                self.pkg("install dev dev2")
                self.pkg("verify")
                self.files_are_all_missing(some_dirs + some_files)
                self.create_some_files(some_dirs + some_files)
                self.files_are_all_there(some_dirs + some_files)
                self.pkg("verify -v")
                self.damage_files(["dev/cfg/bar2"])
                self.pkg("revert -vvv --tagged init-dev")
                self.pkg("verify -v")
                self.files_are_all_missing(some_dirs + some_files)

if __name__ == "__main__":
        unittest.main()
