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

import os
import re
import shutil
import unittest


class TestPkgHistory(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo1 = """
            open foo@1,5.11-0
            close """

        foo2 = """
            open foo@2,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            add depend type=incorporate fmri=pkg:/foo@1
            close """

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])

                rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(rurl1, (self.foo1, self.foo2))

                # Ensure that the second repo's packages are exactly the same
                # as those in the first ... by duplicating the repo.
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                self.copy_repository(d1dir, d2dir, { "test1": "test2" })
                self.dcs[2].get_repo(auto_create=True).rebuild()

                self.image_create(rurl1, prefix="test1")

        def test_1_history_options(self):
                """Verify all history options are accepted or rejected as
                expected.
                """
                self.pkg("history")
                self.pkg("history -l")
                self.pkg("history -H")
                self.pkg("history -n 5")
                self.pkg("history -n foo", exit=2)
                self.pkg("history -n -5", exit=2)
                self.pkg("history -n 0", exit=2)
                self.pkg("history -lH", exit=2)

        def test_2_history_record(self):
                """Verify that all image operations that change an image are
                recorded as expected.
                """

                rurl2 = self.dcs[2].get_repo_url()
                commands = [
                    ("install foo@1", 0),
                    ("update", 0),
                    ("uninstall foo", 0),
                    ("set-publisher -O " + rurl2 + " test2", 0),
                    ("set-publisher -P test1", 0),
                    ("set-publisher -m " + rurl2 + " test1", 0),
                    ("set-publisher -M " + rurl2 + " test1", 0),
                    ("unset-publisher test2", 0),
                    ("rebuild-index", 0)
                ]

                operations = [
                    "install",
                    "update",
                    "uninstall",
                    "add-publisher",
                    "update-publisher",
                    "set-preferred-publisher",
                    "remove-publisher",
                    "rebuild-index"
                ]

                for cmd, exit in commands:
                        self.pkg(cmd, exit=exit)

                self.pkg("history -H")
                o = self.output
                self.assert_(
                    re.search("TIME\s+", o.splitlines()[0]) == None)

                # Only the operation is listed in short format.
                for op in operations:
                        # Verify that each operation was recorded.
                        if o.find(op) == -1:
                                raise RuntimeError("Operation: %s wasn't "
                                    "recorded, o:%s" % (op, o))

                # The actual commands are only found in long format.
                self.pkg("history -l")
                o = self.output
                for cmd, exit in commands:
                        # Verify that each of the commands was recorded.
                        if o.find(" %s" % cmd) == -1:
                                raise RuntimeError("Command: %s wasn't recorded,"
                                    " o:%s" % (cmd, o))

                # Verify that a successful operation with no effect won't
                # be recorded.
                self.pkg("purge-history")
                self.pkg("refresh")
                self.pkg("history -l")
                self.assert_(" refresh" not in self.output)

                self.pkg("refresh --full")
                self.pkg("history -l")
                self.assert_(" refresh" in self.output)

        def test_3_purge_history(self):
                """Verify that the purge-history command works as expected.
                """
                self.pkg("purge-history")
                self.pkg("history -H")
                o = self.output
                # Ensure that the first item in history output is now
                # purge-history.
                self.assert_(
                    re.search("purge-history", o.splitlines()[0]) != None)

        def test_4_bug_4639(self):
                """Test that install and uninstall of non-existent packages
                both make the same history entry.
                """

                self.pkg("purge-history")
                self.pkg("uninstall doesnt_exist", exit=1)
                self.pkg("install doesnt_exist", exit=1)
                self.pkg("history -H")
                o = self.output
                for l in o.splitlines():
                        tmp = l.split()
                        res = " ".join(tmp[3:])
                        if tmp[1] == "install" or tmp[1] == "uninstall":
                                self.assert_(res == "Failed (Bad Request)")
                        else:
                                self.assert_(tmp[1] in ("purge-history",
                                    "refresh-publishers"))

        def test_5_bug_5024(self):
                """Test that install and uninstall of non-existent packages
                both make the same history entry.
                """

                rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(rurl1, self.bar1)
                self.pkg("refresh")
                self.pkg("install bar")
                self.pkg("install foo")
                self.pkgsend_bulk(rurl1, self.foo2)
                self.pkg("refresh")
                self.pkg("purge-history")
                self.pkg("install foo@2", exit=1)
                self.pkg("history -H")
                o = self.output
                for l in o.splitlines():
                        tmp = l.split()
                        res = " ".join(tmp[3:])
                        if tmp[1] == "install":
                                self.assert_(res == "Failed (Constrained)")
                        else:
                                self.assert_(tmp[1] in ("purge-history",
                                    "refresh-publishers"))

        def test_6_bug_3540(self):
                """Verify that corrupt history entries won't cause the client to
                exit abnormally.
                """
                # Overwrite first entry with bad data.
                hist_path = self.get_img_api_obj().img.history.path
                entry = sorted(os.listdir(hist_path))[0]
                f = open(os.path.join(hist_path, entry), "w")
                f.write("<Invalid>")
                f.close()
                self.pkg("history")

        def test_7_bug_5153(self):
                """Verify that an absent History directory will not cause the
                the client to exit with an error or traceback.
                """
                hist_path = self.get_img_api_obj().img.history.path
                shutil.rmtree(hist_path)
                self.pkg("history")

        def test_8_failed_record(self):
                """Verify that all failed image operations that change an image
                are recorded as expected.
                """

                commands = [
                    "install nosuchpackage",
                    "uninstall nosuchpackage",
                    "set-publisher -O http://test.invalid2 test2",
                    "set-publisher -O http://test.invalid1 test1",
                    "unset-publisher test3",
                ]

                operations = [
                    "install",
                    "uninstall",
                    "add-publisher",
                    "update-publisher",
                    "remove-publisher",
                ]

                self.pkg("purge-history")
                for cmd in commands:
                        self.pkg(cmd, exit=1)

                self.pkg("history -H")
                o = self.output
                self.assert_(
                    re.search("TIME\s+", o.splitlines()[0]) == None)

                # Only the operation is listed in short format.
                for op in operations:
                        # Verify that each operation was recorded as failing.
                        found_op = False
                        for line in o.splitlines():
                                if line.find(op) == -1:
                                        continue

                                found_op = True
                                if line.find("Failed") == -1:
                                        raise RuntimeError("Operation: %s "
                                            "wasn't recorded as failing, "
                                            "o:%s" % (op, l))
                                break

                        if not found_op:
                                raise RuntimeError("Operation: %s "
                                    "wasn't recorded, o:%s" % (op, o))

                # The actual commands are only found in long format.
                self.pkg("history -l")
                o = self.output
                for cmd in commands:
                        # Verify that each of the commands was recorded.
                        if o.find(" %s" % cmd) == -1:
                                raise RuntimeError("Command: %s wasn't recorded,"
                                    " o:%s" % (cmd, o))

        def test_9_history_limit(self):
                """Verify limiting the number of records to output
                """

                #
                # Make sure we have a nice number of entries with which to
                # experiment.
                #
                for i in xrange(5):
                        self.pkg("install pkg%d" % i, exit=1)
                self.pkg("history -Hn 3")
                self.assertEqual(len(self.output.splitlines()), 3)

                self.pkg("history -ln 3")
                lines = self.output.splitlines()
                nentries = len([l for l in lines if l.find("Operation:") >= 0])
                self.assertEqual(nentries, 3)

                hist_path = self.get_img_api_obj().img.history.path
                count = len(os.listdir(hist_path))

                # Asking for too many objects should return the full set
                self.pkg("history -Hn %d" % (count + 5))
                self.assertEqual(len(self.output.splitlines()), count)


if __name__ == "__main__":
        unittest.main()
