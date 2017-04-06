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
# Copyright (c) 2014, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.misc as misc
import time

class TestPkgHydrate(pkg5unittest.ManyDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        # A set of packages that we publish with additional hash attributes
        pkgs = """
            open dev@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dev
            add dir mode=0755 owner=root group=bin path=dev/cfg
            add file dev/cfg/bar path=dev/cfg/bar mode=0644 owner=root group=bin preserve=true facet.locale.fr=True variant.opensolaris.zone=global
            add file dev/cfg/bar1 path=dev/cfg/bar1 mode=0555 owner=root group=bin facet.locale.fr=True variant.opensolaris.zone=global revert-tag="bob"
            add file dev/cfg/bar2 path=dev/cfg/bar2 mode=0644 owner=root group=bin overlay=true
            add link path=dev/cfg/bar1.slink target=bar1
			add hardlink path=usr/bin/vi target=../../dev/cfg/bar2 mediator=vi mediator-implementation=dev
            close
            open dev@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dev
            add dir mode=0755 owner=root group=bin path=dev/cfg
            add file dev/cfg/bar path=dev/cfg/bar mode=0644 owner=root group=bin preserve=true
            add file dev/cfg/bar1 path=dev/cfg/bar1 mode=0555 owner=root group=bin
            add file dev/cfg/bar2 path=dev/cfg/bar2 mode=0644 owner=root group=bin overlay=true
            add file dev/cfg/bar3 path=dev/cfg/bar3 mode=0644 owner=root group=bin
            add link path=dev/cfg/bar1.slink target=bar1
            add hardlink path=usr/bin/vi target=../../dev/cfg/bar2 mediator=vi mediator-implementation=dev
            close
            open dev2@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dev
            add dir mode=0755 owner=root group=bin path=dev/cfg
            add file dev/cfg/foo path=dev/cfg/foo mode=0555 owner=root group=bin
            add link path=dev/cfg/foo.slink target=foo
            add hardlink path=dev/cfg/foo.hlink target=foo
            close
            """

        pkgs2 = """
            open etc@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add dir mode=0755 owner=root group=bin path=etc/cfg
            add file etc/foo path=etc/foo mode=0555 owner=root group=bin
            add file etc/cfg/foo path=etc/cfg/foo mode=0644 owner=root group=bin preserve=true
            add file etc/cfg/foo1 path=etc/cfg/foo1 mode=0555 owner=root group=bin
            add link path=etc/foo.slink target=foo
            add hardlink path=usr/bin/vi target=../../etc/foo mediator=vi mediator-implementation=etc
            close
            open etc@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file etc/foo path=etc/foo mode=0555 owner=root group=bin
            add hardlink path=usr/bin/vi target=../../etc/foo mediator=vi mediator-implementation=etc
            close
            """

        pkgs3 = """
            open dba@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=dba
            add file dba/foo path=dba/foo mode=0555 owner=root group=bin
            add file dba/foo1 path=dba/foo1 mode=0644 owner=root group=bin preserve=true
            add link path=dba/foo.slink target=foo
            add hardlink path=dba/foo.hlink target=foo
            close
            """

        pkgs4 = """
            open cga@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=cga
            close
            open mnt@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=mnt
            add file mnt/mm path=mnt/mm mode=0555 owner=root group=bin
            add file mnt/nn path=mnt/nn mode=0644 owner=root group=bin preserve=true
            close
            """

        zones = """
            open zones@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc/zones
            add file path=etc/zones/index mode=0644 owner=root group=bin preserve=true
            add file group=bin mode=0444 owner=root path=etc/zones/SYSdefault.xml dehydrate=false variant.opensolaris.zone=global 
            close
            """

        misc_files = ["dev/cfg/bar", "dev/cfg/bar1", "dev/cfg/bar2", "dev/cfg/bar3",
                "dev/cfg/bar1.slink", "usr/bin/vi", "dev/cfg/foo",
                "dev/cfg/foo.hlink",
                "etc/foo", "etc/cfg/foo", "etc/cfg/foo1", "etc/foo.slink",
                "dba/foo", "dba/foo1", "dba/foo.slink", "dba/foo1.slink",
                "dba/foo.hlink",
                "mnt/mm", "mnt/nn"]

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test1", "test3"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.rurl1, self.pkgs)
                self.rurl2 = self.dcs[2].get_repo_url()
                self.pkgsend_bulk(self.rurl2, self.pkgs2)
                self.rurl3 = self.dcs[3].get_repo_url()
                self.pkgsend_bulk(self.rurl3, self.pkgs3)
                self.rurl4 = self.dcs[4].get_repo_url()
                self.pkgsend_bulk(self.rurl4, self.pkgs4)
                self.pkgsign_simple(self.rurl1, "'*'")
                self.pkgsign_simple(self.rurl2, "'*'")
                self.pkgsign_simple(self.rurl3, "'*'")
                self.pkgsign_simple(self.rurl4, "'*'")

        def test_01_basics(self):
                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")

                # Nothing to do when there are no packages installed under
                # all publishers.
                self.pkg("dehydrate", exit=4)
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated []\n"""
                self.assertEqual(expected, self.output)
                self.pkg("dehydrate -p test1", exit=4)
                self.pkg("rehydrate", exit=4)

                self.pkg("install dev@1.0 dev2")
                # Rehydrate do nothing if the publisher has not been dehydrated.
                self.pkg("rehydrate -p test1", exit=4)
 
                index_dir = self.get_img_api_obj().img.index_dir
                index_file = os.path.join(index_dir, "main_dict.ascii.v2")
                orig_mtime = os.stat(index_file).st_mtime
                time.sleep(1)
 
                some_files = ["dev/xxx", "dev/yyy", "dev/zzz",
                              "dev/dir1/aaaa", "dev/dir1/bbbb", "dev/dir2/cccc",
                              "dev/cfg/ffff", "dev/cfg/gggg",
                              "dev/cfg/dir3/iiii", "dev/cfg/dir3/jjjj"]
                some_dirs = ["dev/dir1/", "dev/dir1/", "dev/dir2/", "dev/cfg/dir3/"]
                self.create_some_files(some_dirs + some_files)
                self.files_are_all_there(some_dirs + some_files)
                removed = "dev/cfg/bar1"
                size1 = self.file_size(removed)
 
                # Verify that unprivileged users are handled by dehydrate.
                self.pkg("dehydrate", exit=1, su_wrap=True)
 
                # Verify that dehydrate fails gracefully,
                # if any of the specified publishers does not have a configured
                # package repository;
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("set-publisher -G '*' test2")
                self.pkg("dehydrate -p test1 -p test2", exit=1)
                # if any of the publishers specified does not exist;
                self.pkg("dehydrate -p nosuch -p test1", exit=1)
                # if all known publishers have no configured package repository.
                self.pkg("set-publisher -G '*' test1")
                self.pkg("dehydrate", exit=1)
                self.pkg("dehydrate -p test1", exit=1)

                # If no publishers exist in the image,
                self.pkg("unset-publisher test1 test2")
                # dehydrate will default to do nothing;
                self.pkg("dehydrate", exit=4)
                # the specified publisher will be treated as not having a
                # configured package repository.
                self.pkg("dehydrate -p test1", exit=1)
 
                # Verify that dehydrate works as expected.
                self.pkg("set-publisher -g " + self.rurl1 + " test1")
                self.pkg("dehydrate -vvv -p test1")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                # Verify dehydrate would not touch unpackaged data.
                self.files_are_all_there(some_dirs + some_files)
                # Verify that files are deleted or remained as expected.
                self.file_exists("dev/cfg/bar")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_exists("dev/cfg/bar2")
                self.file_doesnt_exist("usr/bin/vi")
                self.file_doesnt_exist("dev/cfg/foo.hlink")
                self.file_doesnt_exist("dev/cfg/foo")
  
                # Dehydrate do nothing on dehydrated publishers.
                self.pkg("dehydrate -vvv -p test1", exit=4)
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
  
                # Verify that rehydrate fails gracefully,
                # if any of the specified publishers does not have a configured
                # package repository;
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("set-publisher -G '*' test2")
                self.pkg("rehydrate -p test2 -p test1", exit=1)
                # if any of the publishers specified does not exist;
                self.pkg("rehydrate -p nosuch -p test1", exit=1)
                # if all known publishers have no configured package repository.
                self.pkg("set-publisher -G '*' test1")
                self.pkg("rehydrate", exit=1)
                self.pkg("rehydrate -p test1", exit=1)

                # If no publishers exist in the image,
                self.pkg("unset-publisher test1 test2")
                # The dehydrated property will not be removed if the publisher
                # is deleted.
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                # rehydrate will default to do nothing;
                self.pkg("rehydrate", exit=4)
                # the specified publisher will be treated as not having a
                # configured package repository.
                self.pkg("rehydrate -p test1", exit=1)
 
                # Verify that unprivileged users are handled by rehydrate.
                self.pkg("rehydrate", exit=1, su_wrap=True)
 
                # Verify that rehydrate works as expected.
                self.pkg("set-publisher -g " + self.rurl1 + " test1")
                self.pkg("rehydrate -vvv -p test1")
                self.pkg("verify")
  
                # Check that we didn't reindex.
                new_mtime = os.stat(index_file).st_mtime
                self.assertEqual(orig_mtime, new_mtime)
  
                # Make sure it's the same size as the original.
                size2 = self.file_size(removed)
                self.assertEqual(size1, size2)
  
                # Verify that rehydrate will not operate on rehydrated publishers.
                self.pkg("rehydrate -p test1", exit=4)

                # Verify that the default behavior of dehydrate/rehydrate works
                # as expected.
                self.pkg("dehydrate")
                self.pkg("rehydrate")
                self.pkg("verify")

                # Verify that dehydrate defaults to dehydrate on all publishers
                # that have configured repositories, regardless of whether the
                # publisher has installed packages or not.
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("dehydrate -vvv")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1', 'test2']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("rehydrate -vvv")
                self.pkg("verify")

        def test_02_multiple_publishers(self):
                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("install dev@1.0 dev2")
                self.pkg("install etc@1.0")

                some_files = ["dev/cfg/bar1", "usr/bin/vi", "dev/cfg/foo",
                "etc/foo", "etc/cfg/foo1"]
 
                # Verify that specifying publishers manually will work.
                self.pkg("dehydrate -vvv -p test1 -p test2")
                self.files_are_all_missing(some_files)
                self.pkg("rehydrate -vvv -p test1 -p test2")
                self.files_are_all_there(some_files)
                self.pkg("verify")
 
                # Verify that dehydrate defaults to operate on all publishers
                # with configured package repositories.
                self.pkg("dehydrate -vvv")
                self.files_are_all_missing(some_files)
                self.pkg("rehydrate -vvv")
                self.files_are_all_there(some_files)
                self.pkg("verify")
 
                # Verify that multiple origins with the same publisher will work.
                self.pkg("set-publisher -g " + self.rurl3 + " test1")
                self.pkg("install dba")
                self.pkg("dehydrate -vvv -p test1")
                some_files = ["dev/cfg/bar1", "dev/cfg/foo", "dba/foo",
                    "dba/foo.hlink"]
                self.files_are_all_missing(some_files)
                self.pkg("rehydrate -vvv")
                self.files_are_all_there(some_files)
                self.pkg("verify")

                # Verify that packages with nothing to dehydrate will work.
                self.pkg("set-publisher -g " + self.rurl4 + " test3")
                self.pkg("install cga")
                self.pkg("dehydrate -vvv -p test1 -p test3")
                self.pkg("rehydrate -vvv -p test1 -p test3")
                self.pkg("verify")
 
                # More tests on the user behaviors.
                self.pkg("dehydrate -vvv -p test1")
                self.pkg("dehydrate -vvv -p test2")
                self.pkg("rehydrate -vvv -p test1")
                self.pkg("rehydrate -vvv -p test1", exit=4)
                self.pkg("rehydrate -vvv -p test2")
                self.pkg("verify")

                # Test the dehydrated property will be set correctly.
                self.pkg("install mnt")
                self.pkg("dehydrate -p test1 -p test3")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1', 'test3']\n"""
                self.assertEqual(expected, self.output)

                self.pkg("dehydrate -p test1 -p test2 -p test3")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1', 'test2', 'test3']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("rehydrate -p test3")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1', 'test2']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("rehydrate")
                # The dehydrated proerty should has no value after
                # fully rehydrate.
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated []\n"""
                self.assertEqual(expected, self.output)
                self.pkg("verify")

                self.pkg("dehydrate")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1', 'test2', 'test3']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("rehydrate")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated []\n"""
                self.assertEqual(expected, self.output)
                self.pkg("verify")

        def test_03_hardlinks(self):
                """Hardlink test: make sure that a file getting rehydrated gets
                any hardlinks that point to it updated"""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("install dev@1.0")

                victim = "dev/cfg/bar2"
                victimlink = "usr/bin/vi"

                self.pkg("dehydrate")
                self.pkg("rehydrate")

                # Get the inode of the orig file.
                i1 = self.file_inode(victim)
                # Get the inode of the new hardlink.
                i2 = self.file_inode(victimlink)

                # Make sure the inode of the link is now same.
                self.assertEqual(i1, i2)

        def test_04_pkg_install(self):
                """Test that pkg install will install packages dehydrated from
                dehydrated publishers and install packages normally from normal
                publishers."""
                for install_cmd in ["install", "exact-install"]:
                        self.base_04_pkg_install(install_cmd)

        def base_04_pkg_install(self, install_cmd):
                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("install dev@1.0")
                self.pkg("dehydrate")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                # Verify that a package from a dehydrated publisher will be
                # installed dehydrated on the image.
                self.pkg("install -vvv dev2")
                self.file_doesnt_exist("dev/cfg/foo")
                self.file_doesnt_exist("dev/cfg/foo.hlink")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("dehydrate", exit=4)
                self.pkg("rehydrate")
                self.file_exists("dev/cfg/foo")
                self.file_exists("dev/cfg/foo.hlink")
                self.pkg("verify")

                # Verify that if we dehydrate a publisher without any packages,
                # installing packages for that publisher are dehydrated.
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("dehydrate -p test1 -p test2")
                self.pkg("install etc@1.0")
                self.file_doesnt_exist("etc/foo")
                self.file_doesnt_exist("etc/cfg/foo1")
                self.file_doesnt_exist("usr/bin/vi")
                self.pkg("rehydrate")
                self.pkg("verify")

                # Verify that if users adds a new publisher and install packages
                # from it, the package is installed normally.
                self.pkg("dehydrate -p test1")
                self.pkg("set-publisher -g " + self.rurl4 + " test3")
                self.pkg("install mnt")
                self.file_exists("mnt/mm")
                self.file_exists("mnt/nn")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("rehydrate")
                self.pkg("verify")

        def test_05_pkg_update(self):
                """Test that pkg update will update packages dehydrated from
                dehydrated publishers and update packages normally from normal
                publishers."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                
                # Verify that a package that is dilvered by a dehydrated publisher
                # will be updated dehydrated on the image.
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("install dev@1.0 etc@1.0")
                self.file_doesnt_exist("dev/cfg/bar3")
                self.pkg("dehydrate -p test1")
                self.file_doesnt_exist("dev/cfg/bar3")
                self.pkg("update dev")
                self.file_doesnt_exist("dev/cfg/bar3")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.pkg("rehydrate")
                self.pkg("verify")

                # Verify that a package that is not dilvered by a dehydrated
                # publisher will be updated normally.
                self.pkg("dehydrate -p test1")
                self.pkg("update etc")
                self.file_exists("etc/foo")
                self.pkg("rehydrate")
                self.pkg("verify")

                # Verify that update without pargs will work too.
                self.pkg("update dev@1.0")
                self.pkg("update etc@1.0")
                self.pkg("dehydrate -p test1")
                self.pkg("update")
                self.file_doesnt_exist("dev/cfg/bar3")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_exists("etc/foo")
                self.pkg("rehydrate")
                self.pkg("verify")

        def test_06_pkg_uninstall(self):
                """Test uninstall works fine."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                
                # Verify that if we uninstall all packages under dehydrated
                # publishers, no work to do in dehydrate and rehydrate, and
                # the dehydrated property remains.
                self.pkg("install dev@1.0")
                self.pkg("dehydrate")
                self.pkg("uninstall dev")
                self.pkg("dehydrate", exit=4)
                self.pkg("rehydrate", exit=4)
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("verify")

                # Verify that uninstalling some packages under dehydrated
                # publishers will not cause dehydrate to fail on other packages,
                # and the dehydrated property is deleted after rehydrate.
                self.pkg("unset-property dehydrated")
                self.pkg("install dev@1.0 dev2")
                self.pkg("dehydrate -p test1")
                self.pkg("uninstall dev")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated ['test1']\n"""
                self.assertEqual(expected, self.output)
                self.pkg("dehydrate -p test1", exit=4)
                self.pkg("rehydrate")
                self.pkg("property dehydrated")
                expected = \
"""PROPERTY   VALUE\ndehydrated []\n"""
                self.assertEqual(expected, self.output)
                self.pkg("verify")
 
                # Verify that uninstalling some packages under a publisher
                # will not cause dehydrate to fail on another publisher.
                self.pkg("set-publisher -g " + self.rurl4 + " test3")
                self.pkg("install mnt")
                self.pkg("dehydrate -p test3")
                self.pkg("uninstall mnt")
                self.pkg("dehydrate -p test1")
                self.pkg("rehydrate")
                self.pkg("verify")

        def test_07_pkg_verify(self):
                """Test that verify will only look at things that have not been
                dehydrated."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("install dev@1.0")
                self.file_append("dev/cfg/bar", "junk")
                self.pkg("dehydrate")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_contains("dev/cfg/bar", "junk")
                self.pkg("verify -vvv")
                # dev/cfg/bar1 is dehydrated, so verify will not look at it
                self.assertTrue("dev/cfg/bar1" not in self.output)
                self.pkg("verify -v")
                self.output.index("editable file has been changed")

        def test_08_pkg_fix(self):
                """Test that fix will only fix things that have not been
                dehydrated."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                
                self.pkg("install dev@1.0")
                self.file_append("dev/cfg/bar", "junk")
                self.pkg("dehydrate")
                # dev/cfg/bar1 is dehydrated, dev/cfg/bar is not
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_exists("dev/cfg/bar")
                self.pkg("fix -vvv", exit=4)
                self.file_doesnt_exist("dev/cfg/bar1")
                # remove dev/cfg/bar to cause an error
                self.file_remove("dev/cfg/bar")
                self.pkg("fix")

        def test_09_pkg_revert(self):
                """Test that revert will only revert things that have not been
                dehydrated."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("install dev@1.0")
                self.file_append("dev/cfg/bar", "junk")
                self.pkg("dehydrate")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_contains("dev/cfg/bar", "junk")
                # It will be treated as "not packaged" if revert by path-to-name.
                self.pkg("revert dev/cfg/bar1", exit=1)
                # Nothing to do if revert by tag-name.
                self.pkg("revert --tagged bob", exit=4)
                self.pkg("revert dev/cfg/bar")
                self.pkg("verify")

        def test_10_pkg_change_facet(self):
                """Test that change-facet for dehydrated publishers will be
                automatically dehydrated."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                
                # Test that change-facet uninstalls files on dehydrated
                # publishers.
                self.pkg("install dev@1.0")
                self.pkg("dehydrate")
                self.file_exists("dev/cfg/bar")
                self.pkg("change-facet facet.locale.fr=False")
                self.file_doesnt_exist("dev/cfg/bar")
                self.pkg("rehydrate")
                self.file_doesnt_exist("dev/cfg/bar")
                self.pkg("verify")

                # Verify that change-facet installs new files dehydrated on
                # dehydrated publishers.
                self.pkg("dehydrate")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.pkg("change-facet facet.locale.fr=True")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.pkg("rehydrate")
                self.file_exists("dev/cfg/bar1")
                self.pkg("verify")

        def test_11_pkg_change_variant(self):
                """Test that change-variant for dehydrated publishers will be
                automatically dehydrated."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                
                # Test that change-variant uninstalls files on dehydrated
                # publishers.
                self.pkg("install dev@1.0")
                self.pkg("dehydrate")
                self.file_exists("dev/cfg/bar")
                self.pkg("change-variant variant.opensolaris.zone=non-global")
                self.file_doesnt_exist("dev/cfg/bar")
                self.pkg("rehydrate")
                # Rehydrate will be restricted by variants.
                self.file_doesnt_exist("dev/cfg/bar")
                self.pkg("verify")

                # Verify that change-variant installs new files dehydrated on
                # dehydrated publishers.
                self.pkg("dehydrate")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.pkg("change-variant variant.opensolaris.zone=global")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.pkg("rehydrate")
                self.file_exists("dev/cfg/bar1")
                self.pkg("verify")

        def test_12_zone_files(self):
                """Test that zone configuration files 'index' and 'SYSdefault.xml'
                will not be removed in dehydrate."""

                self.image_create(self.rurl1)
                self.make_misc_files(["etc/zones/index", "etc/zones/SYSdefault.xml"])
                self.pkgsend_bulk(self.rurl1, self.zones)
                self.pkgsign_simple(self.rurl1, "zones")
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("install zones dev@1.0")
                self.pkg("dehydrate")
                self.file_exists("etc/zones/index")
                self.file_exists("etc/zones/SYSdefault.xml")

        def test_13_existing_file(self):
                """Test that rehydrate will reinstall the file if it was created
                manually at the same path."""

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("install dev@1.0")
                self.pkg("dehydrate")
                self.file_doesnt_exist("dev/cfg/bar1")
                self.file_append("dev/cfg/bar1", "junk")
                self.file_exists("dev/cfg/bar1")
                self.pkg("rehydrate -vvv")
                self.file_doesnt_contain("dev/cfg/bar1", "junk")
                self.pkg("verify")

        def test_14_mediator(self):
                """Test that a warning emitted whenever dehydrated publishers
                exist and 'pkg mediator' or 'pkg set-mediator' is executed, and
                the correct mediation will be applied when the publishers are
                rehydrated."""

                def get_link_path(*parts):
                        return os.path.join(self.img_path(), *parts)

                def assert_target(link, target):
                        self.assertEqual(os.stat(link).st_ino,
                            os.stat(target).st_ino)

                def assert_mediation_matches(expected, mediators=misc.EmptyI):
                        self.pkg("mediator -H -F tsv {0}".format(" ".join(mediators)))
                        self.assertEqualDiff(expected, self.output)

                vi_path = get_link_path("usr", "bin", "vi")
                dev_path = get_link_path("dev", "cfg", "bar2")
                etc_path = get_link_path("etc", "foo")

                self.image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("set-publisher -g " + self.rurl2 + " test2")
                self.pkg("install dev@1.0 etc@1.0")
                assert_mediation_matches("""\
vi\tsystem\t\tsystem\tdev\t
""")

                warning = """\
WARNING: pkg mediators may not be accurately shown when one or more publishers have been dehydrated. The correct mediation will be applied when the publishers are rehydrated.
"""
 
                # If dehydrate all publishers that have the mediated hardlink
                # to remove it and its target file exists.
                self.pkg("dehydrate -p test1 -p test2")
                self.file_doesnt_exist(vi_path)
                self.file_exists(dev_path)
                self.pkg("set-mediator -vvv -I dev vi")
                self.file_doesnt_exist(vi_path)
                self.assertTrue(warning in self.output, self.output)
                self.pkg("mediator")
                self.assertTrue(warning in self.output, self.output)
                self.pkg("rehydrate")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tlocal\tdev\t
""")
                self.pkg("verify")

                self.pkg("dehydrate -p test1 -p test2")
                self.file_doesnt_exist(vi_path)
                self.pkg("unset-mediator -vvv vi")
                self.file_doesnt_exist(vi_path)
                self.pkg("rehydrate")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tsystem\tdev\t
""")
                self.pkg("verify")

                # If dehydrate all publishers that have the mediated hardlink
                # to remove it and its target file doesn't exist.
                self.pkg("dehydrate -p test1 -p test2")
                self.file_doesnt_exist(vi_path)
                self.file_doesnt_exist(etc_path)
                self.pkg("set-mediator -vvv -I etc vi")
                self.file_doesnt_exist(vi_path)
                self.file_doesnt_exist(etc_path)
                self.pkg("rehydrate")
                assert_target(vi_path, etc_path)
                assert_mediation_matches("""\
vi\tsystem\t\tlocal\tetc\t
""")
                self.pkg("verify")

                self.pkg("dehydrate -p test1 -p test2")
                self.file_doesnt_exist(vi_path)
                self.file_doesnt_exist(etc_path)
                self.pkg("unset-mediator -vvv vi")
                self.file_doesnt_exist(vi_path)
                self.file_doesnt_exist(etc_path)
                self.pkg("rehydrate")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tsystem\tdev\t
""")
                self.pkg("verify")

                # If dehydrate only a publisher that has the mediated hardlink
                # but the other publisher still deliver it and its target file
                # exists.
                self.pkg("dehydrate -vvv -p test2")
                self.file_exists(vi_path)
                self.file_exists(dev_path)
                self.pkg("set-mediator -vvv -I dev vi")
                self.pkg("rehydrate -vvv")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tlocal\tdev\t
""")
                self.pkg("verify")

                self.pkg("dehydrate -p test2")
                self.file_exists(vi_path)
                self.file_exists(dev_path)
                self.pkg("unset-mediator -vvv vi")
                self.pkg("rehydrate")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tsystem\tdev\t
""")
                self.pkg("verify")

                self.pkg("dehydrate -p test1")
                self.file_exists(vi_path)
                self.file_exists(dev_path)
                self.pkg("set-mediator -vvv -I dev vi")
                self.pkg("rehydrate")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tlocal\tdev\t
""")
                self.pkg("verify")

                self.pkg("dehydrate -p test1")
                self.file_exists(vi_path)
                self.file_exists(etc_path)
                self.pkg("set-mediator -vvv -I etc vi")
                self.pkg("rehydrate")
                assert_target(vi_path, etc_path)
                assert_mediation_matches("""\
vi\tsystem\t\tlocal\tetc\t
""")
                self.pkg("verify")

                self.pkg("dehydrate -p test1")
                self.file_exists(vi_path)
                self.file_exists(etc_path)
                self.pkg("unset-mediator -vvv vi")
                self.pkg("rehydrate")
                assert_target(vi_path, dev_path)
                assert_mediation_matches("""\
vi\tsystem\t\tsystem\tdev\t
""")
                self.pkg("verify")

                # If dehydrate only a publisher that has the mediated hardlink
                # but the other publisher still deliver it and its target file
                # doesn't exist.
                self.pkg("dehydrate -p test2")
                self.file_exists(vi_path)
                self.file_doesnt_exist(etc_path)
                self.pkg("set-mediator -vvv -I etc vi")
                self.file_doesnt_exist(etc_path)
                self.pkg("rehydrate")
                assert_target(vi_path, etc_path)
                assert_mediation_matches("""\
vi\tsystem\t\tlocal\tetc\t
""")
                self.pkg("verify")


if __name__ == "__main__":
        unittest.main()

