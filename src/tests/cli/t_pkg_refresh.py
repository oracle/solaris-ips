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

import difflib
import os
import re
import shutil
import tempfile
import unittest

class TestPkgRefreshMulti(testutils.ManyDepotTestCase):

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

 	def test_refresh_cli_options(self):
                """Test refresh and options."""

                durl = self.dcs[1].get_depot_url()
                self.image_create(durl)

                self.pkg("refresh")
                self.pkg("refresh --full")
                self.pkg("refresh -F", exit=2)

        def test_general_refresh(self):
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("set-publisher -O " + self.durl2 + " test2")
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo12)

                # This should fail as the publisher was just updated seconds
                # ago, and not enough time has passed yet for the client to
                # contact the repository to check for updates.
                self.pkg("list -aH pkg:/foo", exit=1)

                # This should succeed as a full refresh was requested, which
                # ignores the update check interval the client normally uses
                # to determine whether or not to contact the repository to
                # check for updates.
                self.pkg("refresh --full")
                self.pkg("list -aH pkg:/foo")

                expected = \
                    "foo 1.0-0 known u---\n" + \
                    "foo (test2) 1.2-0 known ----\n"
                self.checkAnswer(expected, self.output)

        def test_specific_refresh(self):
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("set-publisher -O " + self.durl2 + " test2")
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.pkgsend_bulk(self.durl2, self.foo12)

                # This should fail since only a few seconds have passed since
                # the publisher's metadata was last checked, and so the catalog
                # will not yet reflect the last published package.
                self.pkg("list -aH pkg:/foo@1,5.11-0", exit=1)

                # This should succeed since a refresh is explicitly performed,
                # and so the catalog will reflect the last published package.
                self.pkg("refresh test1")
                self.pkg("list -aH pkg:/foo@1,5.11-0")

                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)

                # This should succeed since a refresh is explicitly performed,
                # and so the catalog will reflect the last published package.
                self.pkg("refresh test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known u---\n" + \
                    "foo (test2) 1.2-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("refresh unknownAuth", exit=1)
                self.pkg("set-publisher -P test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo (test1) 1.0-0 known u---\n" + \
                    "foo 1.2-0 known ----\n"
                self.pkgsend_bulk(self.durl1, self.foo11)
                self.pkgsend_bulk(self.durl2, self.foo11)

                # This should succeed since an explicit refresh is performed,
                # and so the catalog will reflect the last published package.
                self.pkg("refresh test1 test2")
                self.pkg("list -aHf pkg:/foo")
                expected = \
                    "foo (test1) 1.0-0 known u---\n" + \
                    "foo (test1) 1.1-0 known u---\n" + \
                    "foo 1.1-0 known u---\n" + \
                    "foo 1.2-0 known ----\n"
                self.checkAnswer(expected, self.output)

        def test_set_publisher_induces_full_refresh(self):
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("set-publisher --no-refresh -O " +
                    self.durl2 + " test1")

                # If a privileged user requests this, it should succeed since
                # publisher metadata will automatically be refreshed when asking
                # for all known packages and foo@1.1 exists in the new catalog.
                self.pkg("list -aH pkg:/foo@1.1")

                self.pkg("set-publisher -O " + self.durl2 + " test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.1-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.pkg("set-publisher -O " + self.durl1 + " test2")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.1-0 known ----\n" \
                    "foo (test2) 1.0-0 known ----\n"

        def test_set_publisher_induces_delayed_full_refresh(self):
                self.pkgsend_bulk(self.durl2, self.foo11)
                self.pkgsend_bulk(self.durl1, self.foo10)
                self.image_create(self.durl1, prefix = "test1")
                self.pkg("list -aH pkg:/foo")
                expected = \
                    "foo 1.0-0 known ----\n"
                self.checkAnswer(expected, self.output)
                self.dcs[2].stop()
                self.pkg("set-publisher --no-refresh -O " + self.durl2 + " test1")
                self.dcs[2].start()

                # This should fail when listing all known packages, and running
                # as an unprivileged user since the publisher's metadata can't
                # be updated.
                self.pkg("list -aH pkg:/foo@1.1", su_wrap=True, exit=1)

                # This should fail when listing all known packages, and running
                # as a privileged user since --no-refresh was specified.
                self.pkg("list -aH --no-refresh pkg:/foo@1.1", exit=1)

                # This should succeed when listing all known packages, and
                # running as a privileged user since the publisher's metadata
                # will automatically be updated.
                self.pkg("list -aH pkg:/foo@1.1")
                expected = \
                    "foo 1.1-0 known ----\n"
                self.checkAnswer(expected, self.output)

        def test_refresh_certificate_problems(self):
                """Verify that an invalid or inaccessible certificate does not
                cause unexpected failure."""

                self.image_create(self.durl1)

                key_fh, key_path = tempfile.mkstemp(dir=self.get_test_prefix())
                cert_fh, cert_path = tempfile.mkstemp(dir=self.get_test_prefix())

                self.pkg("set-publisher --no-refresh -O https://%s1 test1" %
                    self.bogus_url)
                self.pkg("set-publisher --no-refresh -c %s test1" % cert_path)
                self.pkg("set-publisher --no-refresh -k %s test1" % key_path)

                os.close(key_fh)
                os.close(cert_fh)

                os.chmod(cert_path, 0000)
                # Verify that an invalid certificate results in a normal failure
                # when attempting to refresh.
                self.pkg("refresh test1", exit=1)

                # Verify that an inaccessible certificate results in a normal
                # failure when attempting to refresh.
                self.pkg("refresh test1", su_wrap=True, exit=1)

if __name__ == "__main__":
        unittest.main()
