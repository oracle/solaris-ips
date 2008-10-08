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

import unittest
import os
import re
import shutil
import difflib

class TestPkgRefresh(testutils.ManyDepotTestCase):

        foo1 = """
            open foo@1,5.11-0
            close """

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        foo12 = """
            open foo@1.2,5.11-0
            close """

        foo121 = """
            open foo@1.2.1,5.11-0
            close """

        food12 = """
            open food@1.2,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 2)

                self.durl1 = self.dcs[1].get_depot_url()
                self.durl2 = self.dcs[2].get_depot_url()
        
        def reduce_spaces(self, string):
                """Reduce runs of spaces down to a single space."""
                return re.sub(" +", " ", string)

        def assert_equal_diff(self, expected, actual):
                self.assertEqual(expected, actual,
                    "Actual output differed from expected output.\n" +
                    "\n".join(difflib.unified_diff(
                        expected.splitlines(), actual.splitlines(),
                        "Expected output", "Actual output", lineterm="")))

        def _check(self, expected, actual):
                tmp_e = expected.splitlines()
                tmp_e.sort()
                tmp_a = actual.splitlines()
                tmp_a.sort()
                if tmp_e == tmp_a:
                        return True
                else:
                        self.assertEqual(tmp_e, tmp_a,
                            "Actual output differed from expected output.\n" +
                            "\n".join(difflib.unified_diff(
                                tmp_e, tmp_a,
                                "Expected output", "Actual output",
                                lineterm="")))
        
        def checkAnswer(self,expected, actual):
                return self._check(
                    self.reduce_spaces(expected),
                    self.reduce_spaces(actual))
        
        def test_general_refresh(self):
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("set-authority -O " + self.durl2 + " test2")
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo12)
                self.pkg("refresh")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known u---\n" + \
                    "foo (test2) 1.2-0 known ----\n"
                self.checkAnswer(expected, self.output)

        def test_specific_refresh(self):
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("set-authority -O " + self.durl2 + " test2")
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo12)
                self.pkg("refresh test1")
                self.pkg("list -aH pkg:/foo@1,5.11-0")
                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("refresh test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known u---\n" + \
                    "foo (test2) 1.2-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("refresh unknownAuth", exit=1)
                self.pkg("set-authority -P test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo (test1) 1.0-0 known u---\n" + \
                    "foo 1.2-0 known ----\n"
                self.pkgsend_bulk(self.durl1, self.foo11)
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.pkg("refresh test1 test2")
                self.pkg("list -aHf pkg:/foo")
                expected = \
                    "foo (test1) 1.0-0 known u---\n" + \
                    "foo (test1) 1.1-0 known u---\n" + \
                    "foo 1.1-0 known u---\n" + \
                    "foo 1.2-0 known ----\n"
                self.checkAnswer(expected, self.output)


        def test_set_authority_induces_full_refresh(self):
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("set-authority --no-refresh -O " +
                    self.durl2 + " test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("set-authority -O " + self.durl2 + " test1") 
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.1-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("set-authority -O " + self.durl1 + " test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.1-0 known ----\n" \
                    "foo (test2) 1.0-0 known ----\n"
                
        def test_set_authority_induces_delayed_full_refresh(self):
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.dcs[2].stop()
                self.pkg("set-authority -O " + self.durl2 + " test1", exit=1)
                self.pkg("set-authority -O " + self.durl2 + " test1", exit=1)
                self.pkg("set-authority -O " + self.durl2 + " test1", exit=1)
                self.pkg("list -aH pkg:/foo", exit=1)
                self.dcs[2].start()
                self.pkg("refresh test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.1-0 known ----\n"
                self.checkAnswer(expected, self.output)

if __name__ == "__main__":
        unittest.main()
