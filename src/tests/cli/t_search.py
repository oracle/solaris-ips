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

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import unittest
import shutil
import copy

import pkg.depotcontroller as dc

import pkg.query_engine as query_engine
import pkg.portable as portable

class TestPkgSearch(testutils.SingleDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            add file /tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
            add set name=com.sun.service.incorporated_changes value="6556919 6627937"
            add set name=com.sun.service.random_test value=42 value=79
            add set name=com.sun.service.bug_ids value="4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937"
            add set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"
            add set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z
            close """

        example_pkg11 = """
            open example_pkg@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path11
            close """
        
        headers = "INDEX      ACTION    VALUE                     PACKAGE\n"

        res_remote_path = set([
            headers,
            "basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_bin = set([
            headers,
            "path       dir       bin                       pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_bug_id = set([
            headers,
            "com.sun.service.bug_ids set       4851433                   pkg:/example_pkg@1.0-0\n"

        ])

        res_remote_inc_changes = set([
            headers,
            "com.sun.service.incorporated_changes set       6556919                   pkg:/example_pkg@1.0-0\n",
            "com.sun.service.bug_ids set       6556919                   pkg:/example_pkg@1.0-0\n"

        ])

        res_remote_random_test = set([
            headers,
            "com.sun.service.random_test set       42                        pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_keywords = set([
            headers,
            "com.sun.service.keywords set       separator                 pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_wildcard = set([
            headers,
            "basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n",
            "basename   dir       bin/example_dir           pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_glob = set([
            headers,
            "basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n",
            "basename   dir       bin/example_dir           pkg:/example_pkg@1.0-0\n",
            "path       file      bin/example_path          pkg:/example_pkg@1.0-0\n",
            "path       dir       bin/example_dir           pkg:/example_pkg@1.0-0\n"
        ])

        local_fmri_string = \
            "fmri       set       fmri                      pkg:/example_pkg@1.0-0\n"


        res_local_pkg = set([
                headers,
                local_fmri_string
                ])

        res_local_path = copy.copy(res_remote_path)

        res_local_bin = copy.copy(res_remote_bin)

        res_local_bug_id = copy.copy(res_remote_bug_id)

        res_local_inc_changes = copy.copy(res_remote_inc_changes)

        res_local_random_test = copy.copy(res_remote_random_test)

        res_local_keywords = copy.copy(res_remote_keywords)

        res_local_wildcard = copy.copy(res_remote_wildcard)
        res_local_wildcard.add(local_fmri_string)

        res_local_glob = copy.copy(res_remote_glob)
        res_local_glob.add(local_fmri_string)

        res_local_path_example11 = set([
            headers,
            "basename   file      bin/example_path11        pkg:/example_pkg@1.1-0\n"
        ])

        res_local_bin_example11 = set([
            headers,
            "path       dir       bin                       pkg:/example_pkg@1.1-0\n"
        ])

        res_local_wildcard_example11 = set([
            headers,
            "basename   file      bin/example_path11        pkg:/example_pkg@1.1-0\n",
            "fmri       set       fmri                      pkg:/example_pkg@1.1-0\n"
       ])

        res_local_pkg_example11 = set([
            headers,
            "fmri       set       fmri                      pkg:/example_pkg@1.1-0\n"
        ])


        misc_files = ['/tmp/example_file']

        # This is a copy of the 3.81%2C5.11-0.89%3A20080527T163123Z version of
        # SUNWgmake from ipkg with the file and liscense actions changed so
        # that they all take /tmp/example file when sending.
        bug_983_manifest = """
open SUNWgmake@3.81,5.11-0.89
add dir group=sys mode=0755 owner=root path=usr
add dir group=bin mode=0755 owner=root path=usr/bin
add dir group=bin mode=0755 owner=root path=usr/gnu
add dir group=bin mode=0755 owner=root path=usr/gnu/bin
add link path=usr/gnu/bin/make target=../../bin/gmake
add dir group=sys mode=0755 owner=root path=usr/gnu/share
add dir group=bin mode=0755 owner=root path=usr/gnu/share/man
add dir group=bin mode=0755 owner=root path=usr/gnu/share/man/man1
add link path=usr/gnu/share/man/man1/make.1 target=../../../../share/man/man1/gmake.1
add dir group=bin mode=0755 owner=root path=usr/sfw
add dir group=bin mode=0755 owner=root path=usr/sfw/bin
add link path=usr/sfw/bin/gmake target=../../bin/gmake
add dir group=bin mode=0755 owner=root path=usr/sfw/share
add dir group=bin mode=0755 owner=root path=usr/sfw/share/man
add dir group=bin mode=0755 owner=root path=usr/sfw/share/man/man1
add link path=usr/sfw/share/man/man1/gmake.1 target=../../../../share/man/man1/gmake.1
add dir group=sys mode=0755 owner=root path=usr/share
add dir group=bin mode=0755 owner=root path=usr/share/info
add dir group=bin mode=0755 owner=root path=usr/share/man
add dir group=bin mode=0755 owner=root path=usr/share/man/man1
add file /tmp/example_file elfarch=i386 elfbits=32 elfhash=68cca393e816e6adcbac1e8ffe9c618de70413e0 group=bin mode=0555 owner=root path=usr/bin/gmake pkg.size=153036
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info pkg.size=5442
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info-1 pkg.size=301265
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info-2 pkg.size=221686
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/man/man1/gmake.1 pkg.size=10740
add license /tmp/example_file license=SUNWgmake.copyright pkg.size=18043 transaction_id=1211931083_pkg%3A%2FSUNWgmake%403.81%2C5.11-0.89%3A20080527T163123Z
add depend fmri=pkg:/SUNWcsl@0.5.11-0.89 type=require
add set name=description value="gmake - GNU make"
add legacy arch=i386 category=system desc="GNU make - A utility used to build software (gmake) 3.81" hotline="Please contact your local service provider" name="gmake - GNU make" pkg=SUNWgmake vendor="Sun Microsystems, Inc." version=11.11.0,REV=2008.04.29.02.08
close
"""

        res_bug_983 = set([
            headers,
            "basename   link      usr/sfw/bin/gmake         pkg:/SUNWgmake@3.81-0.89\n",
            "basename   file      usr/bin/gmake             pkg:/SUNWgmake@3.81-0.89\n",
            "description set       gmake                     pkg:/SUNWgmake@3.81-0.89\n"

        ])

                
        def setUp(self):
                for p in self.misc_files:
                        f = open(p, "w")
                        # Write the name of the file into the file, so that
                        # all files have differing contents.
                        f.write(p + "\n")
                        f.close()
                testutils.SingleDepotTestCase.setUp(self)
                tp = self.get_test_prefix()
                self.testdata_dir = os.path.join(tp, "search_results")
                os.mkdir(self.testdata_dir)

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)
                shutil.rmtree(self.testdata_dir)

        def _check(self, proposed_answer, correct_answer):
                if correct_answer == proposed_answer:
                        return True
                else:
                        print "Proposed Answer: " + str(proposed_answer)
                        print "Correct Answer : " + str(correct_answer)
                        if isinstance(correct_answer, set) and \
                            isinstance(proposed_answer, set):
                                print "Missing: " + str(correct_answer - 
                                    proposed_answer)
                                print "Extra  : " + str(proposed_answer -
                                    correct_answer)
                        self.assert_(correct_answer == proposed_answer)

        def _search_op(self, remote, token, test_value):
                outfile = os.path.join(self.testdata_dir, "res")
                if remote:
                        token = "-r " + token
                self.pkg("search " + token + " > " + outfile)
                res_list = (open(outfile, "rb")).readlines()
                self._check(set(res_list), test_value)

        def _run_remote_tests(self):
                # Set to 1 since searches can't currently be performed
                # package name unless it's set inside the
                # manifest which happens at install time on
                # the client side.
                self.pkg("search -r example_pkg", exit=1)

                self._search_op(True, "example_path", self.res_remote_path)
                self._search_op(True, "example*", self.res_remote_wildcard)
                self._search_op(True, "/bin", self.res_remote_bin)
                self._search_op(True, "4851433", self.res_remote_bug_id)
                self._search_op(True, "6556919", self.res_remote_inc_changes)
                self._search_op(True, "42", self.res_remote_random_test) 
                self._search_op(True, "separator", self.res_remote_keywords)               
                self._search_op(True, "*example*", self.res_remote_glob)

                # These tests are included because a specific bug
                # was found during development. This prevents regression back
                # to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self.pkg("search -r a_non_existent_token", exit=1)
                self.pkg("search -r a_non_existent_token", exit=1)
                
        def test_remote(self):
                """Test remote search."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self._run_remote_tests()

        def _run_local_tests(self):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(False, "example_pkg", self.res_local_pkg)
                self._search_op(False, "example_path", self.res_local_path)
                self._search_op(False, "example*", self.res_local_wildcard)
                self._search_op(False, "/bin", self.res_local_bin)
                self._search_op(False, "4851433", self.res_local_bug_id)
                self._search_op(False, "6556919", self.res_local_inc_changes)
                self._search_op(False, "42", self.res_local_random_test)
                self._search_op(False, "separator", self.res_local_keywords)
                self._search_op(False, "*example*", self.res_local_glob)                

                # These tests are included because a specific bug
                # was found during development. These tests prevent regression
                # back to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self.pkg("search a_non_existent_token", exit=1)
                self.pkg("search a_non_existent_token", exit=1)

        def _run_local_tests_example11_installed(self):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(False, "example_pkg", self.res_local_pkg_example11)
                self.pkg("search  example_path", exit=1)
                self._search_op(False, "example_path11", self.res_local_path_example11)
                self._search_op(False, "example*", self.res_local_wildcard_example11)
                self._search_op(False, "/bin", self.res_local_bin_example11)

        def _run_local_empty_tests(self):
                self.pkg("search  example_pkg", exit=1)
                self.pkg("search  example_path", exit=1)
                self.pkg("search  example*", exit=1)
                self.pkg("search  /bin", exit=1)

        def test_local(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                
                self.image_create(durl)

                self.pkg("install example_pkg")

                self._run_local_tests()

        def test_repeated_install_uninstall(self):
                """Install and uninstall a package. Checking search both
                after each change to the image."""
                # During development, the index could become corrupted by
                # repeated installing and uninstalling a package. This
                # tests if that has been fixed.
                repeat = 3

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)

                self.pkg("install example_pkg")
                self.pkg("uninstall example_pkg")

                for i in range(1, repeat):
                        self.pkg("install example_pkg")
                        self._run_local_tests()
                        self.pkg("uninstall example_pkg")
                        self._run_local_empty_tests()

        def test_local_image_update(self):
                """Test that the index gets updated by image-update and
                that rebuilding the index works after updating the
                image. Specifically, this tests that rebuilding indexes with
                gaps in them works correctly."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)

                self.pkg("install example_pkg")

                self.pkgsend_bulk(durl, self.example_pkg11)

                self.pkg("image-update")

                self._run_local_tests_example11_installed()

                self.pkg("rebuild-index")

                self._run_local_tests_example11_installed()

        def test_bug_983(self):
                """Test for known bug 983."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bug_983_manifest)
                self.image_create(durl)

                self._search_op(True, "gmake", self.res_bug_983)

        def test_low_mem(self):
                """Test to check codepath used in low memory situations."""
                os.environ["PKG_INDEX_MAX_RAM"] = "0"
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.bug_983_manifest)
                self.pkgsend_bulk(durl, self.bug_983_manifest)

                self.image_create(durl)

                self._run_remote_tests()
                self._search_op(True, "gmake", self.res_bug_983)

        def test_missing_files(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self.pkg("install example_pkg")
                
                index_dir = os.path.join(self.img_path, "var","pkg","index")

                qe = query_engine.QueryEngine(index_dir)
                
                for d in qe._data_dict.values():
                        orig_fn = d.get_file_name()
                        orig_path = os.path.join(index_dir, orig_fn)
                        dest_fn = orig_fn + "TMP"
                        dest_path = os.path.join(index_dir, dest_fn)
                        portable.rename(orig_path, dest_path)
                        self.pkg("search  example_pkg", exit=1)
                        portable.rename(dest_path, orig_path)
                        self.pkg("search  example_pkg")
                        
        def test_mismatched_versions(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self.pkg("install example_pkg")
                
                index_dir = os.path.join(self.img_path, "var","pkg","index")

                qe = query_engine.QueryEngine(index_dir)
                
                for d in qe._data_dict.values():
                        orig_fn = d.get_file_name()
                        orig_path = os.path.join(index_dir, orig_fn)
                        dest_fn = orig_fn + "TMP"
                        dest_path = os.path.join(index_dir, dest_fn)
                        shutil.copy(orig_path, dest_path)
                        fh = open(orig_path, "r+")
                        fh.seek(0)
                        fh.seek(9)
                        # Overwrite the existing version number.
                        # By definition, the version 0 is never used.
                        fh.write("0")
                        fh.close()
                        self.pkg("search  example_pkg", exit=1)
                        portable.rename(dest_path, orig_path)
                        self.pkg("search  example_pkg")
                        
if __name__ == "__main__":
        unittest.main()
