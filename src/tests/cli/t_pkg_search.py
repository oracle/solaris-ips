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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import os
import shutil
import sys
import unittest
import urllib2

import pkg.catalog as catalog
import pkg.fmri as fmri


class TestPkgSearchBasics(pkg5unittest.SingleDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            add dir mode=0755 owner=root group=bin path=/usr/lib/python2.6/vendor-packages/OpenSSL
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
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
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path11
            close """
        
        incorp_pkg10 = """
            open incorp_pkg@1.0,5.11-0
            add depend fmri=example_pkg@1.0,5.11-0 type=incorporate
            close """

        dup_lines_pkg10 = """
            open dup_lines@1.0,5.11-0
            add set name=com.sun.service.incorporated_changes value="aa abc a a"
            add set name=com.sun.service.bug_ids value="z x y a abc bb"
            add set name=com.sun.service.keywords value="z a abc"
            close """

        fat_pkg10 = """
open fat@1.0,5.11-0
add set name=variant.arch value=sparc value=i386
add set name=description value="i386 variant" variant.arch=i386
add set name=description value="sparc variant" variant.arch=sparc
close """

        bogus_pkg10 = """
set name=pkg.fmri value=pkg:/bogus_pkg@1.0,5.11-0:20090326T233451Z
set name=description value=""validation with simple chains of constraints ""
set name=pkg.description value="pseudo-hashes as arrays tied to a "type" (list of fields)"
depend fmri=XML-Atom-Entry
set name=com.sun.service.incorporated_changes value="6556919 6627937"
"""
        bogus_fmri = fmri.PkgFmri("bogus_pkg@1.0,5.11-0:20090326T233451Z")

        headers = "INDEX ACTION VALUE PACKAGE\n"
        pkg_headers = "PACKAGE PUBLISHER\n"

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
            "basename   dir       usr/lib/python2.6/vendor-packages/OpenSSL pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_bug_id = set([
            headers,
            "com.sun.service.bug_ids set       4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937                   pkg:/example_pkg@1.0-0\n"

        ])

        res_remote_inc_changes = set([
            headers,
            "com.sun.service.incorporated_changes set       6556919 6627937                   pkg:/example_pkg@1.0-0\n",
            "com.sun.service.bug_ids set       4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937                   pkg:/example_pkg@1.0-0\n"

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
            "com.sun.service.keywords set       sort null -n -m -t sort 0x86 separator                 pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_wildcard = set([
            headers,
            "basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n",
            "basename   dir       bin/example_dir           pkg:/example_pkg@1.0-0\n",
            "pkg.fmri   set       test/example_pkg          pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_glob = set([
            headers,
            "basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n",
            "basename   dir       bin/example_dir           pkg:/example_pkg@1.0-0\n",
            "path       file      bin/example_path          pkg:/example_pkg@1.0-0\n",
            "path       dir       bin/example_dir           pkg:/example_pkg@1.0-0\n",
            "pkg.fmri   set       test/example_pkg          pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_foo = set([
            headers,
            "description set       FOOO bAr O OO OOO                      pkg:/example_pkg@1.0-0\n"
        ])

        res_local_pkg = set([
            headers,
            "pkg.fmri       set        test/example_pkg              pkg:/example_pkg@1.0-0\n"
        ])

        res_local_path = copy.copy(res_remote_path)

        res_local_bin = copy.copy(res_remote_bin)

        res_local_bug_id = copy.copy(res_remote_bug_id)

        res_local_inc_changes = copy.copy(res_remote_inc_changes)

        res_local_random_test = copy.copy(res_remote_random_test)
        res_local_random_test_79 = copy.copy(res_remote_random_test_79)

        res_local_keywords = copy.copy(res_remote_keywords)

        res_local_wildcard = copy.copy(res_remote_wildcard)

        res_local_glob = copy.copy(res_remote_glob)

        res_local_foo = copy.copy(res_remote_foo)

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

        res_bogus_name_result = set([
            headers,
            'pkg.fmri       set       bogus_pkg                 pkg:/bogus_pkg@1.0-0\n'
        ])

        res_bogus_number_result = set([
            headers,
            'com.sun.service.incorporated_changes set       6556919 6627937                   pkg:/bogus_pkg@1.0-0\n'
        ])

        misc_files = { "tmp/example_file": "magic" }

        res_local_pkg_ret_pkg = set([
            pkg_headers,
            "pkg:/example_pkg@1.0-0\n"
        ])

        res_remote_pkg_ret_pkg = set([
            pkg_headers,
            "pkg:/example_pkg@1.0-0 test\n"
        ])

        res_remote_file = set([
            'path       file      bin/example_path          pkg:/example_pkg@1.0-0\n',
            'b40981aab75932c5b2f555f50769d878e44913d7 file      bin/example_path          pkg:/example_pkg@1.0-0\n'
        ]) | res_remote_path


        res_remote_url = set([
             headers,
             'com.sun.service.info_url set       http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z pkg:/example_pkg@1.0-0\n'
        ])

        res_remote_path_extra = set([
             headers,
             'path       file      bin/example_path          pkg:/example_pkg@1.0-0\n',
             'basename   file      bin/example_path          pkg:/example_pkg@1.0-0\n',
             'b40981aab75932c5b2f555f50769d878e44913d7 file      bin/example_path          pkg:/example_pkg@1.0-0\n'
        ])

        o_headers = \
            "ACTION.NAME ACTION.KEY PKG.NAME " \
            "PKG.SHORTFMRI SEARCH.MATCH " \
            "SEARCH.MATCH_TYPE MODE OWNER GROUP " \
            "ACTION.RAW PKG.PUBLISHER\n"

        o_results_no_pub = \
            "file bin/example_path example_pkg " \
            "pkg:/example_pkg@1.0-0 bin/example_path " \
            "basename 0555 root bin " \
            "file b40981aab75932c5b2f555f50769d878e44913d7 chash=6a4299897fca0c4d0d18870da29a0dc7ae23b79c group=bin mode=0555 owner=root path=bin/example_path pkg.csize=25 pkg.size=5\n"

        o_results = o_results_no_pub.rstrip() + " test\n"

        res_o_options_remote = set([o_headers, o_results])

        res_o_options_local = set([o_headers, o_results_no_pub])

        pkg_headers = "PKG.NAME PKG.SHORTFMRI PKG.PUBLISHER MODE"
        pkg_results_no_pub = "example_pkg pkg:/example_pkg@1.0-0"
        pkg_results = pkg_results_no_pub + " test"

        res_pkg_options_remote = set([pkg_headers, pkg_results])
        res_pkg_options_local = set([pkg_headers, pkg_results_no_pub])

        def setUp(self):
                # This test needs an actual depot for now.
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)
                self.make_misc_files(self.misc_files)
                self.init_mem_setting = None

        def _check(self, proposed_answer, correct_answer):
                if correct_answer == proposed_answer:
                        return True
                if len(proposed_answer) == len(correct_answer) and \
                    sorted([p.strip().split() for p in proposed_answer]) == \
                    sorted([c.strip().split() for c in correct_answer]):
                        return True
                self.debug("Proposed Answer: " + str(proposed_answer))
                self.debug("Correct Answer : " + str(correct_answer))
                if isinstance(correct_answer, set) and \
                    isinstance(proposed_answer, set):
                        print >> sys.stderr, "Missing: " + \
                            str(correct_answer - proposed_answer)
                        print >> sys.stderr, "Extra  : " + \
                            str(proposed_answer - correct_answer)
                self.assert_(correct_answer == proposed_answer)

        def _search_op(self, remote, token, test_value, case_sensitive=False,
            return_actions=True, exit=0, su_wrap=False, prune_versions=True):
                outfile = os.path.join(self.test_root, "res")
                if remote:
                        token = "-r " + token
                else:
                        token = "-l " + token
                if case_sensitive:
                        token = "-I " + token
                if return_actions:
                        token = "-a " + token
                else:
                        token = "-p " + token
                if not prune_versions:
                        token = "-f " + token
                self.pkg("search " + token + " > " + outfile, exit=exit)
                res_list = (open(outfile, "rb")).readlines()
                self._check(set(res_list), test_value)

        def _run_remote_tests(self):
                # This should be possible now that the server automatically adds
                # FMRIs to manifests (during publication).
                self.pkg("search -a -r example_pkg")

                self._search_op(True, "example_path", self.res_remote_path)
                self._search_op(True, "'(example_path)'", self.res_remote_path)
                self._search_op(True, "'<exam*:::>'",
                    self.res_remote_pkg_ret_pkg)
                self._search_op(True, "'::com.sun.service.info_url:'",
                    self.res_remote_url)
                self._search_op(True, "':::e* AND *path'", self.res_remote_path)
                self._search_op(True, "'e* AND *path'", self.res_remote_path)
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
                self._search_op(True, "'example*'", self.res_remote_wildcard)
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
                self._search_op(True, "4851433 OR 4725245",
                    self.res_remote_bug_id | self.res_remote_bug_id)
                self._search_op(True, "6556919", self.res_remote_inc_changes)
                self._search_op(True, "'6556?19'", self.res_remote_inc_changes)
                self._search_op(True, "42", self.res_remote_random_test)
                self._search_op(True, "79", self.res_remote_random_test_79)
                self._search_op(True, "separator", self.res_remote_keywords)
                self._search_op(True, "'\"sort 0x86\"'",
                    self.res_remote_keywords)
                self._search_op(True, "'*example*'", self.res_remote_glob)
                self._search_op(True, "fooo", self.res_remote_foo)
                self._search_op(True, "'fo*'", self.res_remote_foo)
                self._search_op(True, "bar", self.res_remote_foo)
                self._search_op(True, "openssl", self.res_remote_openssl)
                self._search_op(True, "OPENSSL", self.res_remote_openssl)
                self._search_op(True, "OpEnSsL", self.res_remote_openssl)
                self._search_op(True, "'OpEnS*'", self.res_remote_openssl)

                # Verify that search will work for an unprivileged user even if
                # the download directory doesn't exist.
                img = self.get_img_api_obj().img
                cache_dirs = [
                    path
                    for path, readonly, pub in img.get_cachedirs()
                ]
                for path in cache_dirs:
                        shutil.rmtree(path, ignore_errors=True)
                        self.assertFalse(os.path.exists(path))
                self._search_op(True, "'fo*'", self.res_remote_foo,
                    su_wrap=True)

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
                outfile = os.path.join(self.test_root, "res")

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
                self._search_op(False, "'e* AND *path'", self.res_local_path)
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
                self._search_op(False, "'example*'", self.res_local_wildcard)
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
                    self.res_remote_bug_id | self.res_remote_bug_id)
                self._search_op(False, "6556919", self.res_local_inc_changes)
                self._search_op(False, "'65569??'", self.res_local_inc_changes)
                self._search_op(False, "42", self.res_local_random_test)
                self._search_op(False, "79", self.res_local_random_test_79)
                self._search_op(False, "separator", self.res_local_keywords)
                self._search_op(False, "'\"sort 0x86\"'",
                    self.res_remote_keywords)
                self._search_op(False, "'*example*'", self.res_local_glob)
                self._search_op(False, "fooo", self.res_local_foo)
                self._search_op(False, "'fo*'", self.res_local_foo)
                self._search_op(False, "bar", self.res_local_foo)
                self._search_op(False, "openssl", self.res_local_openssl)
                self._search_op(False, "OPENSSL", self.res_local_openssl)
                self._search_op(False, "OpEnSsL", self.res_local_openssl)
                self._search_op(False, "'OpEnS*'", self.res_local_openssl)

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

        def _run_local_empty_tests(self):
                self.pkg("search -a -l example_pkg", exit=1)
                self.pkg("search -a -l example_path", exit=1)
                self.pkg("search -a -l 'example*'", exit=1)
                self.pkg("search -a -l /bin", exit=1)

        def _run_remote_empty_tests(self):
                self.pkg("search -a -r example_pkg", exit=1)
                self.pkg("search -a -r example_path", exit=1)
                self.pkg("search -a -r 'example*'", exit=1)
                self.pkg("search -a -r /bin", exit=1)
                self.pkg("search -a -r '*unique*'", exit=1)

        def _get_index_dirs(self):
                index_dir = self.get_img_api_obj().img.index_dir
                index_dir_tmp = os.path.join(index_dir, "TMP")
                return index_dir, index_dir_tmp

        def pkgsend_bulk(self, durl, pkg):
                # Ensure indexing is performed for every published package.
                pkg5unittest.SingleDepotTestCase.pkgsend_bulk(self, durl, pkg,
                    refresh_index=True)
                self.wait_repo(self.dc.get_repodir())

        def test_pkg_search_cli(self):
                """Test search cli options."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)

                self.pkg("search", exit=2)

                # Bug 1541
                self.pkg("search -s %s bin" % ("httP" + durl[4:]))
                self.pkg("search -s ftp://pkg.opensolaris.org:88 bge", exit=1)

                # Testing interaction of -o and -p options
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkg("search -o action.name -p pkg", exit=2)
                self.pkg("search -o action.name -a '<pkg>'", exit=1)
                self.pkg("search -o action.name -a '<example_path>'", exit=2)
                self.pkg("search -o action.key -p pkg", exit=2)
                self.pkg("search -o action.key -a '<pkg>'", exit=1)
                self.pkg("search -o action.key -a '<example_path>'", exit=2)
                self.pkg("search -o search.match -p pkg", exit=2)
                self.pkg("search -o search.match -a '<pkg>'", exit=1)
                self.pkg("search -o search.match -a '<example_path>'", exit=2)
                self.pkg("search -o search.match_type -p pkg", exit=2)
                self.pkg("search -o search.match_type -a '<pkg>'", exit=1)
                self.pkg("search -o search.match_type -a '<example_path>'",
                    exit=2)
                self.pkg("search -o action.foo -a pkg", exit=2)

        def test_remote(self):
                """Test remote search."""
                # Need to retain to check that default search does remote, not
                # local search, and that -r and -s work as expected
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)
                self._run_remote_tests()
                self._search_op(True, "':file::'", self.res_remote_file)
                self.pkg("search '*'")
                self.pkg("search -r '*'")
                self.pkg("search -s %s '*'" % durl)
                self.pkg("search -l '*'", exit=1)

        def test_local_0(self):
                """Install one package, and run the search suite."""
                # Need to retain that -l works as expected
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)

                self.pkg("install example_pkg")

                self._run_local_tests()

        def test_bug_1873(self):
                """Test to see if malformed actions cause tracebacks during
                indexing for client or server."""
                # Can't be moved to api search since this is to test for
                # tracebacks
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                server_manifest_path = os.path.join(depotpath, "publisher",
                    "test", "pkg", self.bogus_fmri.get_dir_path())
                os.makedirs(os.path.dirname(server_manifest_path))
                tmp_ind_dir = os.path.join(depotpath, "index", "TMP")

                fh = open(server_manifest_path, "wb")
                fh.write(self.bogus_pkg10)
                fh.close()

                self.image_create(durl)
                self.dc.stop()
                self.dc.set_rebuild()
                self.dc.start()

                # Should return nothing, as the server can't build catalog
                # data for the package since the manifest is unparseable.
                self._search_op(True, "'*bogus*'", set(), exit=1)
                self._search_op(True, "6627937", set(), exit=1)

                # Should fail since the bogus_pkg isn't even in the catalog.
                self.pkg("install bogus_pkg", exit=1)

                client_manifest_file = self.get_img_manifest_path(
                    self.bogus_fmri)
                os.makedirs(os.path.dirname(client_manifest_file))

                fh = open(client_manifest_file, "wb")
                fh.write(self.bogus_pkg10)
                fh.close()

                # Load the 'installed' catalog and add an entry for the
                # new package version.
                img = self.get_img_api_obj().img
                istate_dir = os.path.join(img._statedir, "installed")
                cat = catalog.Catalog(meta_root=istate_dir)
                # Value of PKG_STATE_INSTALLED in image.py is 2.
                # Value of __PKG_STATE_PREFERRED in image.py is 5.
                mdata = { "states": [2, 5] }
                bfmri = self.bogus_fmri.copy()
                bfmri.set_publisher("test")
                cat.add_package(bfmri, metadata=mdata)
                cat.save()

                self.pkg("rebuild-index")
                self._search_op(False, "'*bogus*'",
                    set(self.res_bogus_name_result))
                self._search_op(False, "6627937",
                    set(self.res_bogus_number_result))

        def test_bug_6177(self):
                """Test that by default search restricts the results to the
                incorporated packages and that the -f option works as
                expected."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, (self.example_pkg10, self.example_pkg11,
                    self.incorp_pkg10))

                self.image_create(durl)

                res_both_actions = set([
                    self.headers,
                    "path       dir    bin   pkg:/example_pkg@1.0-0\n",
                    "path       dir    bin   pkg:/example_pkg@1.1-0\n"
                ])

                res_10_action = set([
                    self.headers,
                    "path       dir    bin   pkg:/example_pkg@1.0-0\n"
                ])


                res_11_action = set([
                    self.headers,
                    "path       dir    bin   pkg:/example_pkg@1.1-0\n"
                ])

                self.pkg("install incorp_pkg")
                self._search_op(True, '/bin', res_10_action)
                self._search_op(True, '/bin', res_both_actions,
                    prune_versions=False)

                self.pkg("uninstall incorp_pkg")
                self.pkg("install example_pkg")
                self._search_op(True, '/bin', res_11_action)
                self._search_op(True, '/bin', res_both_actions,
                    prune_versions=False)

        def test_bug_7835(self):
                """Check that installing a package in a non-empty image
                without an index doesn't build an index."""
                # This test can't be moved to t_api_search until bug 8497 has
                # been resolved.
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, (self.fat_pkg10, self.example_pkg10))

                self.image_create(durl)

                self.pkg("install fat")

                id, tid = self._get_index_dirs()
                self.assert_(len(os.listdir(id)) > 0)
                shutil.rmtree(id)
                os.makedirs(id)
                self.pkg("install example_pkg")
                self.assert_(len(os.listdir(id)) == 0)
                self.pkg("uninstall fat")
                self.assert_(len(os.listdir(id)) == 0)
                self._run_local_tests()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkg("refresh")
                self.pkg("update")
                self.assert_(len(os.listdir(id)) == 0)

        def test_bug_8098(self):
                """Check that parse errors don't cause tracebacks in the client
                or the server."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)

                self.pkg("install example_pkg")

                self.pkg("search -l 'Intel(R)'", exit=1)
                self.pkg("search -l 'foo AND <bar>'", exit=1)
                self.pkg("search -r 'Intel(R)'", exit=1)
                self.pkg("search -r 'foo AND <bar>'", exit=1)

                urllib2.urlopen("%s/en/search.shtml?token=foo+AND+<bar>&"
                    "action=Search" % durl)
                urllib2.urlopen("%s/en/search.shtml?token=Intel(R)&"
                    "action=Search" % durl)

                pkg5unittest.eval_assert_raises(urllib2.HTTPError,
                    lambda x: x.code == 400, urllib2.urlopen,
                    "%s/search/1/False_2_None_None_Intel%%28R%%29" % durl)
                pkg5unittest.eval_assert_raises(urllib2.HTTPError,
                    lambda x: x.code == 400, urllib2.urlopen,
                    "%s/search/1/False_2_None_None_foo%%20%%3Cbar%%3E" % durl)

        def test_bug_10515(self):
                """Check that -o and -H options work as expected."""

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)

                self.image_create(durl)

                o_options = "action.name,action.key,pkg.name,pkg.shortfmri," \
                    "search.match,search.match_type,mode,owner,group," \
                    "action.raw,pkg.publisher"

                pkg_options = "-o pkg.name -o pkg.shortfmri -o pkg.publisher " \
                    "-o mode"

                self._search_op(True, "-o %s example_path" % o_options,
                    self.res_o_options_remote)
                self._search_op(True, "-H -o %s example_path" % o_options,
                    [self.o_results])
                self._search_op(True, "-s %s -o %s example_path" %
                    (durl, o_options), self.res_o_options_remote)

                self._search_op(True, "%s -p example_path" % pkg_options,
                    self.res_pkg_options_remote)
                self._search_op(True, "%s '<example_path>'" % pkg_options,
                    self.res_pkg_options_remote)

                self.pkg("install example_pkg")
                self._search_op(False, "-o %s example_path" % o_options,
                    self.res_o_options_local)
                self._search_op(False, "-H -o %s example_path" % o_options,
                    [self.o_results_no_pub])

                self._search_op(False, "%s -p example_path" % pkg_options,
                    self.res_pkg_options_local)
                self._search_op(False, "%s '<example_path>'" % pkg_options,
                    self.res_pkg_options_local)

                id, tid = self._get_index_dirs()
                shutil.rmtree(id)
                self._search_op(False, "-o %s example_path" % o_options,
                    self.res_o_options_local)
                self._search_op(False, "-H -o %s example_path" % o_options,
                    [self.o_results_no_pub])

        def test_bug_12271_14088(self):
                """Check that consecutive duplicate lines are removed and
                that having a single option to -o still prints the header."""

                # This test assumes that search is basically working and focuses
                # on testing whether consecutive duplicate lines have been
                # correctly removed.  For the first three queries, two lines are
                # expected.  The first line is the headers and the second is
                # a line for the matching package.  Without consecutive
                # duplicate line removal, far more than two lines would be
                # seen.  The final query has four lines of output.  The headers
                # are the first line and the package name followed by
                # com.sun.service.incorporated_changes, com.sun.service.bug_ids,
                # or com.sun.service.keywords.

                # The final query depends on search returning the results in
                # a consistent ordering so that all the like lines get merged
                # together.  If this changes in the future, because of parallel
                # indexing or parallel searching for example, it's possible
                # this test will need to be removed or reexamined.
                
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.dup_lines_pkg10)

                self.image_create(durl)
                
                self.pkg("search -a 'dup_lines:set:pkg.fmri:'")
                self.assertEqual(len(self.output.splitlines()), 2)

                self.pkg("search -a -o pkg.shortfmri 'a'")
                self.assertEqual(len(self.output.splitlines()), 2)

                self.pkg("install dup_lines")

                self.pkg("search -a -l 'dup_lines:set:pkg.fmri:'")
                self.assertEqual(len(self.output.splitlines()), 2)

                self.pkg("search -l -a -o pkg.shortfmri,action.key 'a'")
                self.assertEqual(len(self.output.splitlines()), 4)


if __name__ == "__main__":
        unittest.main()
