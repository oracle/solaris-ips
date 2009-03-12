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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import unittest
import shutil
import copy
import sys
import time

import pkg.depotcontroller as dc

import pkg.client.query_parser as query_parser
import pkg.portable as portable
import pkg.search_storage as ss

class TestPkgSearchBasics(testutils.SingleDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            add dir mode=0755 owner=root group=bin path=/usr/lib/python2.4/vendor-packages/OpenSSL
            add file /tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
            add set name=com.sun.service.incorporated_changes value="6556919 6627937"
            add set name=com.sun.service.random_test value=42 value=79
            add set name=com.sun.service.bug_ids value="4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937"
            add set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"
            add set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z
            add set description='FOOO bAr O OO OOO'
            add set name='weirdness' value='] [ * ?'
            close """

        example_pkg11 = """
            open example_pkg@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file /tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path11
            close """

        another_pkg10 = """
            open another_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/another_dir
            add file /tmp/example_file mode=0555 owner=root group=bin path=/bin/another_path
            add set name=com.sun.service.incorporated_changes value="6556919 6627937"
            add set name=com.sun.service.random_test value=42 value=79
            add set name=com.sun.service.bug_ids value="4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937"
            add set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"
            add set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z
            close """

        bad_pkg10 = """
            open bad_pkg@1.0,5.11-0
            add dir path=foo/ mode=0755 owner=root group=bin
            close """

        space_pkg10 = """
            open space_pkg@1.0,5.11-0
            add file /tmp/example_file mode=0444 owner=nobody group=sys path='unique/with a space'
            add dir mode=0755 owner=root group=bin path=unique_dir
            close """

        cat_pkg10 = """
            open cat@1.0,5.11-0
            add set name=info.classification value=org.opensolaris.category.2008:System/Security
            close """

        cat2_pkg10 = """
            open cat2@1.0,5.11-0
            add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video"
            close """

        cat3_pkg10 = """
            open cat3@1.0,5.11-0
            add set name=info.classification value="org.opensolaris.category.2008:foo/bar/baz/bill/beam/asda"
            close """

        bad_cat_pkg10 = """
            open badcat@1.0,5.11-0
            add set name=info.classification value="TestBad1/TestBad2"
            close """

        bad_cat2_pkg10 = """
            open badcat2@1.0,5.11-0
            add set name=info.classification value="org.opensolaris.category.2008:TestBad1:TestBad2"
            close """

        fat_pkg10 = """
open fat@1.0,5.11-0
add set name=variant.arch value=sparc value=i386
add set name=description value="i386 variant" variant.arch=i386
add set name=description value="sparc variant" variant.arch=sparc
close """

        headers = "INDEX      ACTION    VALUE                     PACKAGE\n"
        pkg_headers = "PACKAGE\n"

        res_remote_path = set([
            headers,
            "basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_bin = set([
            headers,
            "path       dir       bin                       pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_openssl = set([
            headers,
            "basename   dir       usr/lib/python2.4/vendor-packages/OpenSSL pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_bug_id = set([
            headers,
            "com.sun.service.bug_ids set       4851433                   pkg:/example_pkg@1.0-0\n"

        ])

        res_remote_bug_id_4725245 = set([
            headers,
            "com.sun.service.bug_ids set       4725245                   pkg:/example_pkg@1.0-0\n"

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

        res_remote_random_test_79 = set([
            headers,
            "com.sun.service.random_test set       79                        pkg:/example_pkg@1.0-0\n"
        ])
        
        res_remote_keywords = set([
            headers,
            "com.sun.service.keywords set       separator                 pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_keywords_sort_phrase = set([
            headers,
            "com.sun.service.keywords set       sort 0x86                 pkg:/example_pkg@1.0-0\n"
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

        res_remote_foo = set([
            headers,
            "description set       FOOO                      pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_bar = set([
            headers,
            "description set       bAr                       pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_star = set([
            headers,
            "weirdness  set       *                         pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_mark = set([
            headers,
            "weirdness  set       ?                         pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_left_brace = set([
            headers,
            "weirdness  set       [                         pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_right_brace = set([
            headers,
            "weirdness  set       ]                         pkg:/example_pkg@1.0-0\n"
        ])
        
        local_fmri_string = \
            "fmri       set       example_pkg               pkg:/example_pkg@1.0-0\n"


        res_local_pkg = set([
                headers,
                local_fmri_string
                ])

        res_local_path = copy.copy(res_remote_path)

        res_local_bin = copy.copy(res_remote_bin)

        res_local_bug_id = copy.copy(res_remote_bug_id)

        res_local_inc_changes = copy.copy(res_remote_inc_changes)

        res_local_random_test = copy.copy(res_remote_random_test)
        res_local_random_test_79 = copy.copy(res_remote_random_test_79)

        res_local_keywords = copy.copy(res_remote_keywords)

        res_local_wildcard = copy.copy(res_remote_wildcard)
        res_local_wildcard.add(local_fmri_string)

        res_local_glob = copy.copy(res_remote_glob)
        res_local_glob.add(local_fmri_string)

        res_local_foo = copy.copy(res_remote_foo)
        res_local_bar = copy.copy(res_remote_bar)

        res_local_openssl = copy.copy(res_remote_openssl)

        # Results expected for degraded local search
        degraded_warning = set(["To improve, run 'pkg rebuild-index'.\n",
            'Search capabilities and performance are degraded.\n'])

        res_local_degraded_pkg = res_local_pkg.union(degraded_warning)

        res_local_degraded_path = res_local_path.union(degraded_warning)

        res_local_degraded_bin = res_local_bin.union(degraded_warning)

        res_local_degraded_bug_id = res_local_bug_id.union(degraded_warning)

        res_local_degraded_inc_changes = res_local_inc_changes.union(degraded_warning)

        res_local_degraded_random_test = res_local_random_test.union(degraded_warning)

        res_local_degraded_keywords = res_local_keywords.union(degraded_warning)

        res_local_degraded_openssl = res_local_openssl.union(degraded_warning)

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
            "fmri       set       example_pkg               pkg:/example_pkg@1.1-0\n"
       ])

        res_local_pkg_example11 = set([
            headers,
            "fmri       set       example_pkg               pkg:/example_pkg@1.1-0\n"
        ])

        res_cat_pkg10 = set([
            headers,
            "info.classification set       System/Security           pkg:/cat@1.0-0\n"
        ])

        res_cat2_pkg10 = set([
            headers,
            "info.classification set       Applications/Sound and Video pkg:/cat2@1.0-0\n"
        ])

        res_cat3_pkg10 = set([
            headers,
            "info.classification set       foo/bar/baz/bill/beam/asda pkg:/cat3@1.0-0\n"
        ])

        res_fat10_i386 = set([
            headers,
            "description set       i386                      pkg:/fat@1.0-0\n",
            "variant.arch set       i386                      pkg:/fat@1.0-0\n",
            "description set       variant                   pkg:/fat@1.0-0\n"

        ])

        res_fat10_sparc = set([
            headers,
            "description set       sparc                     pkg:/fat@1.0-0\n",
            "variant.arch set       sparc                     pkg:/fat@1.0-0\n",
            "description set       variant                   pkg:/fat@1.0-0\n"

        ])

        res_remote_fat10_star = res_fat10_sparc | res_fat10_i386

        res_local_fat10_i386_star = res_fat10_i386.union(set([
            "variant.arch set       sparc                     pkg:/fat@1.0-0\n",
            "publisher  set       test                      pkg:/fat@1.0-0\n",
            "fmri       set       fat                       pkg:/fat@1.0-0\n"
        ]))

        res_local_fat10_sparc_star = res_fat10_sparc.union(set([
            "variant.arch set       i386                      pkg:/fat@1.0-0\n",
            "publisher  set       test                      pkg:/fat@1.0-0\n",
            "fmri       set       fat                       pkg:/fat@1.0-0\n"
        ]))

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
add file /tmp/example_file elfarch=i386 elfbits=32 elfhash=68cca393e816e6adcbac1e8ffe9c618de70413e0 group=bin mode=0555 owner=root path=usr/bin/gmake pkg.size=18
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info pkg.size=18
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info-1 pkg.size=18
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info-2 pkg.size=18
add file /tmp/example_file group=bin mode=0444 owner=root path=usr/share/man/man1/gmake.1 pkg.size=18
add license /tmp/example_file license=SUNWgmake.copyright pkg.size=18 transaction_id=1211931083_pkg%3A%2FSUNWgmake%403.81%2C5.11-0.89%3A20080527T163123Z
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

        res_local_pkg_ret_pkg = set([
            pkg_headers,
            "pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_pkg_ret_pkg = set([
            pkg_headers,
            "pkg:/example_pkg@1.0-0 (test)\n"
        ])

        res_remote_file = set([
            'path       file      bin/example_path          pkg:/example_pkg@1.0-0\n',
            '820157a2043e3135f342b238129b556aade20347 file      bin/example_path          pkg:/example_pkg@1.0-0\n'
        ]) | res_remote_path


        res_remote_url = set([
             headers,
             'com.sun.service.info_url set       http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z pkg:/example_pkg@1.0-0\n'
        ])

        res_remote_path_extra = set([
             headers,
             'path       file      bin/example_path          pkg:/example_pkg@1.0-0\n',
             'basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n',
             '820157a2043e3135f342b238129b556aade20347 file      bin/example_path          pkg:/example_pkg@1.0-0\n'
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
                self._dir_restore_functions = [self._restore_dir,
                    self._restore_dir_preserve_hash]
                self.init_mem_setting = None

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)
                shutil.rmtree(self.testdata_dir)

        def _set_low_mem(self):
                self.init_mem_setting = \
                    os.environ.get("PKG_INDEX_MAX_RAM", None)
                os.environ["PKG_INDEX_MAX_RAM"] = "0"

        def _unset_low_mem(self):
                if self.init_mem_setting is not None:
                        os.environ["PKG_INDEX_MAX_RAM"] = self.init_mem_setting
                else:
                        del os.environ["PKG_INDEX_MAX_RAM"]

        def _check(self, proposed_answer, correct_answer):
                if correct_answer == proposed_answer:
                        return True
                else:
                        print "Proposed Answer: " + str(proposed_answer)
                        print "Correct Answer : " + str(correct_answer)
                        if isinstance(correct_answer, set) and \
                            isinstance(proposed_answer, set):
                                print >> sys.stderr, "Missing: " + \
                                    str(correct_answer - proposed_answer)
                                print >> sys.stderr, "Extra  : " + \
                                    str(proposed_answer - correct_answer)
                        self.assert_(correct_answer == proposed_answer)

        def _search_op(self, remote, token, test_value, case_sensitive=False):
                outfile = os.path.join(self.testdata_dir, "res")
                if remote:
                        token = "-r " + token
                else:
                        token = "-l " + token
                if case_sensitive:
                        token = "-I " + token
                self.pkg("search -a " + token + " > " + outfile)
                res_list = (open(outfile, "rb")).readlines()
                self._check(set(res_list), test_value)

        def _run_remote_tests(self):
                # Set to 1 since searches can't currently be performed
                # package name unless it's set inside the
                # manifest which happens at install time on
                # the client side.
                self.pkg("search -a -r example_pkg", exit=1)

                self._search_op(True, "example_path", self.res_remote_path)
                self._search_op(True, "'(example_path)'", self.res_remote_path)
                self._search_op(True, "'<exam*:::>'",
                    self.res_remote_pkg_ret_pkg)
                self._search_op(True, "'::com.sun.service.info_url:'",
                    self.res_remote_url)
                self._search_op(True, "':::e* AND *path'", self.res_remote_path)
                self._search_op(True, "e* AND *path", self.res_remote_path)
                self._search_op(True, "'<e*>'", self.res_remote_pkg_ret_pkg)
                self._search_op(True, "'<e*> AND <e*>'",
                    self.res_remote_pkg_ret_pkg)
                self._search_op(True, "'<e*> OR <e*>'",
                    self.res_remote_pkg_ret_pkg)
                self._search_op(True, "'<exam:::>'",
                    self.res_remote_pkg_ret_pkg)
                self._search_op(True, "'exam:::e*path'", self.res_remote_path)
                self._search_op(True, "'exam:::e*path AND e*:::'",
                    self.res_remote_path)
                self._search_op(True, "'e*::: AND exam:::*path'",
                    self.res_remote_path_extra)
                self._search_op(True, "example*", self.res_remote_wildcard)
                self._search_op(True, "/bin", self.res_remote_bin)
                self._search_op(True, "4851433", self.res_remote_bug_id)
                self._search_op(True, "'<4851433> AND <4725245>'",
                    self.res_remote_pkg_ret_pkg)
                self._search_op(True, "4851433 AND 4725245",
                    self.res_remote_bug_id)
                self._search_op(True, "4851433 AND 4725245 OR example_path",
                    self.res_remote_bug_id)
                self._search_op(True, "'4851433 AND (4725245 OR example_path)'",
                    self.res_remote_bug_id)
                self._search_op(True, "'(4851433 AND 4725245) OR example_path'",
                    self.res_remote_bug_id | self.res_remote_path)
                self._search_op(True, "4851433 OR 4725245", self.res_remote_bug_id | self.res_remote_bug_id_4725245)
                self._search_op(True, "6556919", self.res_remote_inc_changes)
                self._search_op(True, "6556?19", self.res_remote_inc_changes)
                self._search_op(True, "42", self.res_remote_random_test)
                self._search_op(True, "79", self.res_remote_random_test_79)
                self._search_op(True, "separator", self.res_remote_keywords)
                self._search_op(True, "'\"sort 0x86\"'",
                    self.res_remote_keywords_sort_phrase)
                self._search_op(True, "*example*", self.res_remote_glob)
                self._search_op(True, "fooo", self.res_remote_foo)
                self._search_op(True, "fo*", self.res_remote_foo)
                self._search_op(True, "bar", self.res_remote_bar)
                self._search_op(True, "openssl", self.res_remote_openssl)
                self._search_op(True, "OPENSSL", self.res_remote_openssl)
                self._search_op(True, "OpEnSsL", self.res_remote_openssl)
                self._search_op(True, "OpEnS*", self.res_remote_openssl)

                # These tests are included because a specific bug
                # was found during development. This prevents regression back
                # to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self.pkg("search -a -r a_non_existent_token", exit=1)
                self.pkg("search -a -r a_non_existent_token", exit=1)

                self.pkg("search -a -r '42 AND 4641790'", exit=1)
                self.pkg("search -a -r '<e*> AND e*'", exit=1)
                self.pkg("search -a -r 'e* AND <e*>'", exit=1)
                self.pkg("search -a -r '<e*> OR e*'", exit=1)
                self.pkg("search -a -r 'e* OR <e*>'", exit=1)
                
        def _run_local_tests(self):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(False, "example_pkg", self.res_local_pkg)
                self._search_op(False, "'(example_pkg)'", self.res_local_pkg)
                self._search_op(False, "'<exam*:::>'",
                    self.res_local_pkg_ret_pkg)
                self._search_op(False, "'::com.sun.service.info_url:'",
                    self.res_remote_url)
                self._search_op(False, "':::e* AND *path'",
                    self.res_remote_path)
                self._search_op(False, "e* AND *path", self.res_local_path)
                self._search_op(False, "'<e*>'", self.res_local_pkg_ret_pkg)
                self._search_op(False, "'<e*> AND <e*>'",
                    self.res_local_pkg_ret_pkg)
                self._search_op(False, "'<e*> OR <e*>'",
                    self.res_local_pkg_ret_pkg)
                self._search_op(False, "'<exam:::>'",
                    self.res_local_pkg_ret_pkg)
                self._search_op(False, "'exam:::e*path'", self.res_remote_path)
                self._search_op(False, "'exam:::e*path AND e:::'",
                    self.res_remote_path)
                self._search_op(False, "'e::: AND exam:::e*path'",
                    self.res_remote_path_extra)
                self._search_op(False, "example*", self.res_local_wildcard)
                self._search_op(False, "/bin", self.res_local_bin)
                self._search_op(False, "4851433", self.res_local_bug_id)
                self._search_op(False, "'<4851433> AND <4725245>'",
                    self.res_local_pkg_ret_pkg)
                self._search_op(False, "4851433 AND 4725245",
                    self.res_remote_bug_id)
                self._search_op(False, "4851433 AND 4725245 OR example_path",
                    self.res_remote_bug_id)
                self._search_op(False,
                    "'4851433 AND (4725245 OR example_path)'",
                    self.res_remote_bug_id)
                self._search_op(False,
                    "'(4851433 AND 4725245) OR example_path'",
                    self.res_remote_bug_id | self.res_local_path)
                self._search_op(False, "4851433 OR 4725245",
                    self.res_remote_bug_id | self.res_remote_bug_id_4725245)
                self._search_op(False, "6556919", self.res_local_inc_changes)
                self._search_op(False, "65569??", self.res_local_inc_changes)
                self._search_op(False, "42", self.res_local_random_test)
                self._search_op(False, "79", self.res_local_random_test_79)
                self._search_op(False, "separator", self.res_local_keywords)
                self._search_op(False, "'\"sort 0x86\"'",
                    self.res_remote_keywords_sort_phrase)
                self._search_op(False, "*example*", self.res_local_glob)
                self._search_op(False, "fooo", self.res_local_foo)
                self._search_op(False, "fo*", self.res_local_foo)
                self._search_op(False, "bar", self.res_local_bar)
                self._search_op(False, "openssl", self.res_local_openssl)
                self._search_op(False, "OPENSSL", self.res_local_openssl)
                self._search_op(False, "OpEnSsL", self.res_local_openssl)
                self._search_op(False, "OpEnS*", self.res_local_openssl)

                # These tests are included because a specific bug
                # was found during development. These tests prevent regression
                # back to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self.pkg("search -a -l a_non_existent_token", exit=1)
                self.pkg("search -a -l a_non_existent_token", exit=1)
                self.pkg("search -a -l '42 AND 4641790'", exit=1)
                self.pkg("search -a -l '<e*> AND e*'", exit=1)
                self.pkg("search -a -l 'e* AND <e*>'", exit=1)
                self.pkg("search -a -l '<e*> OR e*'", exit=1)
                self.pkg("search -a -l 'e* OR <e*>'", exit=1)

        def _run_local_tests_example11_installed(self):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(False, "example_pkg",
                    self.res_local_pkg_example11)
                self.pkg("search -a -l example_path", exit=1)
                self._search_op(False, "example_path11",
                    self.res_local_path_example11)
                self._search_op(False, "example*",
                    self.res_local_wildcard_example11)
                self._search_op(False, "/bin", self.res_local_bin_example11)

        def _run_local_empty_tests(self):
                self.pkg("search -a -l example_pkg", exit=1)
                self.pkg("search -a -l example_path", exit=1)
                self.pkg("search -a -l example*", exit=1)
                self.pkg("search -a -l /bin", exit=1)

        def _run_remote_empty_tests(self):
                self.pkg("search -a -r example_pkg", exit=1)
                self.pkg("search -a -r example_path", exit=1)
                self.pkg("search -a -r example*", exit=1)
                self.pkg("search -a -r /bin", exit=1)
                self.pkg("search -a -r *unique*", exit=1)

        @staticmethod
        def _restore_dir(index_dir, index_dir_tmp):
                shutil.rmtree(index_dir)
                shutil.move(index_dir_tmp, index_dir)

        @staticmethod
        def _restore_dir_preserve_hash(index_dir, index_dir_tmp):
                tmp_file = "full_fmri_list.hash"
                portable.remove(os.path.join(index_dir_tmp, tmp_file))
                shutil.move(os.path.join(index_dir, tmp_file),
                            index_dir_tmp)
                fh = open(os.path.join(index_dir_tmp, ss.MAIN_FILE), "r")
                fh.seek(0)
                fh.seek(9)
                ver = fh.read(1)
                fh.close()
                fh = open(os.path.join(index_dir_tmp, tmp_file), "r+")
                fh.seek(0)
                fh.seek(9)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("%s" % ver)
                shutil.rmtree(index_dir)
                shutil.move(index_dir_tmp, index_dir)

        def _get_index_dirs(self):
                index_dir = os.path.join(self.img_path, "var","pkg","index")
                index_dir_tmp = index_dir + "TMP"
                return index_dir, index_dir_tmp

        @staticmethod
        def _overwrite_version_number(file_path):
                fh = open(file_path, "r+")
                fh.seek(0)
                fh.seek(9)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("0")
                fh.close()

        @staticmethod
        def _overwrite_on_disk_format_version_number(file_path):
                fh = open(file_path, "r+")
                fh.seek(0)
                fh.seek(16)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("9")
                fh.close()

        @staticmethod
        def _overwrite_on_disk_format_version_number_with_letter(file_path):
                fh = open(file_path, "r+")
                fh.seek(0)
                fh.seek(16)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("a")
                fh.close()

        @staticmethod
        def _replace_on_disk_format_version(dir):
                file_path = os.path.join(dir, ss.BYTE_OFFSET_FILE)
                fh = open(file_path, "r")
                lst = fh.readlines()
                fh.close()
                fh = open(file_path, "w")
                fh.write(lst[0])
                for l in lst[2:]:
                        fh.write(l)
                fh.close()

        @staticmethod
        def _overwrite_hash(ffh_path):
                fh = open(ffh_path, "r+")
                fh.seek(0)
                fh.seek(20)
                fh.write("*")
                fh.close()

        def _check_no_index(self):
                ind_dir, ind_dir_tmp = self._get_index_dirs()
                if os.listdir(ind_dir):
                        self.assert_(0)
                if os.path.exists(ind_dir_tmp):
                        self.assert_(0)

	def test_pkg_search_cli(self):
		"""Test search cli options."""

		durl = self.dc.get_depot_url()
                self.image_create(durl)

		self.pkg("search", exit=2)

                # Bug 1541
                self.pkg("search -s httP://pkg.opensolaris.org bge")
                self.pkg("search -s ftp://pkg.opensolaris.org:88 bge", exit=1)

        def test_remote(self):
                """Test remote search."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self._run_remote_tests()
                self._search_op(True, "':file::'", self.res_remote_file)
                self.pkg("search '*'")
                
        def test_local_0(self):
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
                self._set_low_mem()
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.bug_983_manifest)
                self.pkgsend_bulk(durl, self.bug_983_manifest)

                self.image_create(durl)

                self._run_remote_tests()
                self._search_op(True, "gmake", self.res_bug_983)
                self._unset_low_mem()

        def test_missing_files(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self.pkg("install example_pkg")
                
                index_dir = os.path.join(self.img_path, "var","pkg","index")

                for d in query_parser.TermQuery._global_data_dict.values():
                        orig_fn = d.get_file_name()
                        orig_path = os.path.join(index_dir, orig_fn)
                        dest_fn = orig_fn + "TMP"
                        dest_path = os.path.join(index_dir, dest_fn)
                        portable.rename(orig_path, dest_path)
                        self.pkg("search -l example_pkg", exit=1)
                        portable.rename(dest_path, orig_path)
                        self.pkg("search -l example_pkg")
                        
        def test_mismatched_versions(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self.pkg("install example_pkg")
                
                index_dir = os.path.join(self.img_path, "var","pkg","index")

                for d in query_parser.TermQuery._global_data_dict.values():
                        orig_fn = d.get_file_name()
                        orig_path = os.path.join(index_dir, orig_fn)
                        dest_fn = orig_fn + "TMP"
                        dest_path = os.path.join(index_dir, dest_fn)
                        shutil.copy(orig_path, dest_path)
                        self._overwrite_version_number(orig_path)
                        self.pkg("search -l example_pkg", exit=1)
                        portable.rename(dest_path, orig_path)
                        self.pkg("search -l example_pkg")
                        self._overwrite_version_number(orig_path)
                        self.pkg("uninstall example_pkg")
                        self.pkg("search -l example_pkg", exit=1)
                        self._overwrite_version_number(orig_path)
                        self.pkg("install example_pkg")
                        self.pkg("search -l example_pkg")
                        
                ffh = ss.IndexStoreSetHash(ss.FULL_FMRI_HASH_FILE)
                ffh_path = os.path.join(index_dir, ffh.get_file_name())
                dest_path = ffh_path + "TMP"
                shutil.copy(ffh_path, dest_path)
                self._overwrite_hash(ffh_path)
                self.pkg("search -l example_pkg", exit=1)
                portable.rename(dest_path, ffh_path)
                self.pkg("search -l example_pkg")
                self._overwrite_hash(ffh_path)
                self.pkg("uninstall example_pkg")
                self.pkg("search -l example_pkg", exit=1)
                
        def test_degraded_search(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self.pkg("install example_pkg")
                
                index_dir = os.path.join(self.img_path, "var","pkg","index")
                shutil.rmtree(index_dir)
                self._run_local_tests()

        def test_bug_2989_1(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                for f in self._dir_restore_functions:
                        self.image_create(durl)

                        self.pkg("rebuild-index")

                        index_dir, index_dir_tmp = self._get_index_dirs()

                        shutil.copytree(index_dir, index_dir_tmp)
                
                        self.pkg("install example_pkg")

                        f(index_dir, index_dir_tmp)

                        self.pkg("uninstall example_pkg")

                        self.image_destroy()

        def test_bug_2989_2(self):
                # The low mem setting is to test for bug 6949
                self._set_low_mem()
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.another_pkg10)

                for f in self._dir_restore_functions:

                        self.image_create(durl)
                        self.pkg("install example_pkg")

                        index_dir, index_dir_tmp = self._get_index_dirs()
                
                        shutil.copytree(index_dir, index_dir_tmp)

                        self.pkg("install another_pkg")

                        f(index_dir, index_dir_tmp)

                        self.pkg("uninstall another_pkg")

                        self.image_destroy()
                self._unset_low_mem()
                
        def test_bug_2989_3(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.example_pkg11)

                for f in self._dir_restore_functions:
                
                        self.image_create(durl)
                        self.pkg("install example_pkg@1.0,5.11-0")

                        index_dir, index_dir_tmp = self._get_index_dirs()

                        shutil.copytree(index_dir, index_dir_tmp)

                        self.pkg("install example_pkg")

                        f(index_dir, index_dir_tmp)
                        
                        self.pkg("uninstall example_pkg")

                        self.image_destroy()

        def test_bug_2989_4(self):
                # The low mem setting is to test for bug 6949
                self._set_low_mem()
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.another_pkg10)
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.example_pkg11)

                for f in self._dir_restore_functions:
                
                        self.image_create(durl)
                        self.pkg("install another_pkg")
                
                        index_dir, index_dir_tmp = self._get_index_dirs()
                        
                        shutil.copytree(index_dir, index_dir_tmp)

                        self.pkg("install example_pkg@1.0,5.11-0")

                        f(index_dir, index_dir_tmp)

                        self.pkg("image-update")

                        self.image_destroy()
                self._unset_low_mem()

        def test_local_case_sensitive(self):
                """Test local case sensitive search"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self.pkg("install example_pkg")
                self.pkg("search -l -I fooo", exit=1)
                self.pkg("search -l -I fo*", exit=1)
                self.pkg("search -l -I bar", exit=1)
                self._search_op(False, "FOOO", self.res_local_foo, True)
                self._search_op(False, "bAr", self.res_local_bar, True)

        def test_weird_patterns(self):
                """Test strange patterns to ensure they're handled correctly"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self._search_op(True, "[*]", self.res_remote_star)
                self._search_op(True, "[?]", self.res_remote_mark)
                self._search_op(True, "[[]", self.res_remote_left_brace)
                self._search_op(True, "[]]", self.res_remote_right_brace)
                self._search_op(True, "FO[O]O", self.res_remote_foo)
                self._search_op(True, "FO[?O]O", self.res_remote_foo)
                self._search_op(True, "FO[*O]O", self.res_remote_foo)
                self._search_op(True, "FO[]O]O", self.res_remote_foo)

        def test_bug_3046(self):
                """Checks if directories ending in / break the indexer."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bad_pkg10)
                self.image_create(durl)
                self.pkg("search -r foo")
                self.pkg("search -r /", exit=1)

        def test_bug_2849(self):
                """Checks if things with spaces break the indexer."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.space_pkg10)
                self.image_create(durl)

                self.pkg("install space_pkg")
                time.sleep(1)
                
                self.pkgsend_bulk(durl, self.space_pkg10)

                self.pkg("refresh")
                self.pkg("install space_pkg")

                self.pkg("search -l with", exit=1)
                self.pkg("search -l with*")
                self.pkg("search -l *space")
                self.pkg("search -l unique_dir")
                self.pkg("search -r with", exit=1)
                self.pkg("search -r with*")
                self.pkg("search -r *space")
                self.pkgsend_bulk(durl, self.space_pkg10)
                self.pkg("install space_pkg")
                self.pkg("search -l with", exit=1)
                self.pkg("search -l with*")
                self.pkg("search -l *space")
                self.pkg("search -l unique_dir")

        def test_bug_2863(self):
                """Test local case sensitive search"""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self._check_no_index()
                self.pkg("install --no-index example_pkg")
                self._check_no_index()
                self.pkg("rebuild-index")
                self._run_local_tests()
                self.pkg("uninstall --no-index example_pkg")
                # Running empty test because search will notice the index
                # does not match the installed packages and complain.
                self._run_local_empty_tests()
                self.pkg("rebuild-index") 
                self._run_local_empty_tests()
                self.pkg("install example_pkg")
                self._run_local_tests()
                self.pkgsend_bulk(durl, self.example_pkg11)
                self.pkg("image-update --no-index")
                # Running empty test because search will notice the index
                # does not match the installed packages and complain.
                self._run_local_empty_tests()
                self.pkg("rebuild-index")
                self._run_local_tests_example11_installed()
                self.pkg("uninstall --no-index example_pkg")
                # Running empty test because search will notice the index
                # does not match the installed packages and complain.
                self._run_local_empty_tests()
                self.pkg("rebuild-index")
                self._run_local_empty_tests()

        def test_bug_4048_1(self):
                """Checks whether the server deals with partial indexing."""
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                tmp_dir = os.path.join(depotpath, "index", "TMP")
                os.mkdir(tmp_dir)
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)
                self._run_remote_empty_tests()
                os.rmdir(tmp_dir)
                offset = 2
                depot_logfile = os.path.join(self.get_test_prefix(),
                    self.id(), "depot_logfile%d" % offset)
                tmp_dc = self.start_depot(12000 + offset, depotpath,
                    depot_logfile, refresh_index=True)
                self._run_remote_tests()
                tmp_dc.kill()

        def test_bug_4048_2(self):
                """Checks whether the server deals with partial indexing."""
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                tmp_dir = os.path.join(depotpath, "index", "TMP")
                os.mkdir(tmp_dir)
                self.pkgsend_bulk(durl, self.space_pkg10)
                self.image_create(durl)
                self._run_remote_empty_tests()
                os.rmdir(tmp_dir)
                self.pkgsend_bulk(durl, self.example_pkg10)
                self._run_remote_tests()
                self.pkg("search -r unique_dir")
                self.pkg("search -r with*")

        def test_bug_4239(self):
                """Tests whether categories are indexed and searched for
                correctly."""

                def _run_cat_tests(self, remote):
                        self._search_op(remote, "System",
                            self.res_cat_pkg10, case_sensitive=False)
                        self._search_op(remote, "Security",
                            self.res_cat_pkg10, case_sensitive=False)
                        self._search_op(remote, "System/Security",
                            self.res_cat_pkg10, case_sensitive=False)

                def _run_cat2_tests(self, remote):
                        self._search_op(remote, "Applications",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self.pkg("search -r Sound")
                        self._search_op(remote, "'\"Sound and Video\"'",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(remote, "Sound*",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(remote, "*Video",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(remote,
                            "'\"Applications/Sound and Video\"'",
                            self.res_cat2_pkg10, case_sensitive=False)
                def _run_cat3_tests(self, remote):
                        self._search_op(remote, "foo",
                            self.res_cat3_pkg10,case_sensitive=False)
                        self._search_op(remote, "baz",
                            self.res_cat3_pkg10, case_sensitive=False)
                        self._search_op(remote, "asda",
                            self.res_cat3_pkg10, case_sensitive=False)
                        self._search_op(remote, "foo/bar/baz/bill/beam/asda",
                            self.res_cat3_pkg10, case_sensitive=False)

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.cat_pkg10)
                self.pkgsend_bulk(durl, self.cat2_pkg10)
                self.pkgsend_bulk(durl, self.cat3_pkg10)
                self.pkgsend_bulk(durl, self.bad_cat_pkg10)
                self.pkgsend_bulk(durl, self.bad_cat2_pkg10)
                self.image_create(durl)

                remote = True
                _run_cat_tests(self, remote)
                _run_cat2_tests(self, remote)
                _run_cat3_tests(self, remote)

                remote = False
                self.pkg("install cat")
                _run_cat_tests(self, remote)

                self.pkg("install cat2")
                _run_cat2_tests(self, remote)
                
                self.pkg("install cat3")
                _run_cat3_tests(self, remote)
                
                self.pkg("install badcat")
                self.pkg("install badcat2")
                _run_cat_tests(self, remote)
                _run_cat2_tests(self, remote)
                _run_cat3_tests(self, remote)

        def test_bug_6712_i386(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.fat_pkg10)
                
                self.image_create(durl,
                    additional_args="--variant variant.arch=i386")

                remote = True
                
                self._search_op(remote, "'*'", self.res_remote_fat10_star)

                self.pkg("install fat")
                remote = False
                self._search_op(remote, "'*'", self.res_local_fat10_i386_star)

        def test_bug_6712_sparc(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.fat_pkg10)
                
                self.image_create(durl,
                    additional_args="--variant variant.arch=sparc")

                remote = True
                
                self._search_op(remote, "'*'", self.res_remote_fat10_star)

                self.pkg("install fat")
                remote = False
                self._search_op(remote, "'*'", self.res_local_fat10_sparc_star)


class TestPkgSearchMulti(testutils.ManyDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.example_pkg10)

                self.image_create(durl1, prefix = "test1")
                self.pkg("set-publisher -O " + durl2 + " test2")

        def test_bug_2955(self):
                """See http://defect.opensolaris.org/bz/show_bug.cgi?id=2955"""
                self.pkg("install example_pkg")
                self.pkg("rebuild-index")
                self.pkg("uninstall example_pkg")

if __name__ == "__main__":
        unittest.main()
