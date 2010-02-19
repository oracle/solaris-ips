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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import calendar
import os
import shutil
import simplejson as json
import unittest

class TestPkgList(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

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

        newpkg10 = """
            open newpkg@1.0
            close """

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test2"])

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1 + self.foo10 + self.foo11 + \
                    self.foo12 + self.foo121 + self.food12)

                durl2 = self.dcs[2].get_depot_url()

                # Ensure that the second repo's packages have exactly the same
                # timestamps as those in the first ... by copying the repo over.
                # If the repos need to have some contents which are different,
                # send those changes after restarting depot 2.
                self.dcs[2].stop()
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                self.copy_repository(d1dir, "test1", d2dir, "test2")

                # The new repository won't have a catalog, so set the depot
                # server to rebuild it.
                self.dcs[2].set_rebuild()
                self.dcs[2].start()
                self.dcs[2].set_norebuild()

                # The third repository should remain empty and not be
                # published to.

                # Next, create the image and configure publishers.
                self.image_create(durl1, prefix="test1")
                self.pkg("set-publisher -O " + durl2 + " test2")

        def test_pkg_list_cli_opts(self):

                self.pkg("list -@", exit=2)
                self.pkg("list -v -s", exit=2)

        def test_list_00(self):
                """Verify that sort order and content of a full list matches
                expected."""

                self.pkg("list -aH")
                expected = \
                    ("foo 1.2.1-0 known -----\n"
                    "foo (test2) 1.2.1-0 known -----\n"
                    "food 1.2-0 known -----\n"
                    "food (test2) 1.2-0 known -----\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -afH")
                expected = \
                    ("foo 1.2.1-0 known -----\n"
                    "foo 1.2-0 known u----\n"
                    "foo 1.1-0 known u----\n"
                    "foo 1.0-0 known u----\n"
                    "foo 1-0 known u----\n"
                    "foo (test2) 1.2.1-0 known -----\n"
                    "foo (test2) 1.2-0 known u----\n"
                    "foo (test2) 1.1-0 known u----\n"
                    "foo (test2) 1.0-0 known u----\n"
                    "foo (test2) 1-0 known u----\n"
                    "food 1.2-0 known -----\n"
                    "food (test2) 1.2-0 known -----\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Put options in different order to ensure output still matches.
                self.pkg("list -faH")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_list_01(self):
                """List all "foo@1.0" from auth "test1"."""
                self.pkg("list -afH pkg://test1/foo@1.0,5.11-0")
                expected = \
                    "foo 1.0-0 known u----\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_list_02(self):
                """List all "foo@1.0", regardless of publisher, with "pkg:/"
                prefix."""
                self.pkg("list -afH pkg:/foo@1.0,5.11-0")
                expected = \
                    "foo 1.0-0 known u----\n" \
                    "foo (test2) 1.0-0 known u----\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_list_03(self):
                """List all "foo@1.0", regardless of publisher, without "pkg:/"
                prefix."""
                self.pkg("list -afH pkg:/foo@1.0,5.11-0")
                expected = \
                    "foo         1.0-0 known u----\n" \
                    "foo (test2) 1.0-0 known u----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_04(self):
                """List all versions of package foo, regardless of publisher."""
                self.pkg("list -aHf foo")
                expected = \
                    "foo         1.2.1-0 known -----\n" \
                    "foo         1.2-0   known u----\n" \
                    "foo         1.1-0   known u----\n" \
                    "foo         1.0-0   known u----\n" \
                    "foo         1-0     known u----\n" \
                    "foo (test2) 1.2.1-0 known -----\n" \
                    "foo (test2) 1.2-0   known u----\n" \
                    "foo (test2) 1.1-0   known u----\n" \
                    "foo (test2) 1.0-0   known u----\n" \
                    "foo (test2) 1-0     known u----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH foo")
                expected = \
                    "foo         1.2.1-0 known -----\n" \
                    "foo (test2) 1.2.1-0 known -----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)


        def test_list_05(self):
                """Show foo@1.0 from both depots, but 1.1 only from test2."""
                self.pkg("list -aHf foo@1.0-0 pkg://test2/foo@1.1-0")
                expected = \
                    "foo         1.0-0 known u----\n" \
                    "foo (test2) 1.1-0 known u----\n" \
                    "foo (test2) 1.0-0 known u----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aHf foo@1.0-0 pkg://test2/foo@1.1-0")
                expected = \
                    "foo         1.0-0 known u----\n" \
                    "foo (test2) 1.1-0 known u----\n" \
                    "foo (test2) 1.0-0 known u----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_06(self):
                """Show versions 1.0 and 1.1 of foo only from publisher test2."""
                self.pkg("list -aHf pkg://test2/foo")
                expected = \
                    "foo (test2) 1.2.1-0 known -----\n" \
                    "foo (test2) 1.2-0   known u----\n" \
                    "foo (test2) 1.1-0   known u----\n" \
                    "foo (test2) 1.0-0   known u----\n" \
                    "foo (test2) 1-0     known u----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH pkg://test2/foo")
                expected = \
                    "foo (test2) 1.2.1-0 known -----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_07(self):
                """List all foo@1 from test1, but all foo@1.2(.x), and only list
                the latter once."""
                self.pkg("list -aHf pkg://test1/foo@1 pkg:/foo@1.2")
                expected = \
                    "foo         1.2.1-0 known -----\n" \
                    "foo         1.2-0   known u----\n" \
                    "foo         1.1-0   known u----\n" \
                    "foo         1.0-0   known u----\n" \
                    "foo         1-0     known u----\n" \
                    "foo (test2) 1.2.1-0 known -----\n" \
                    "foo (test2) 1.2-0   known u----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH pkg://test1/foo@1 pkg:/foo@1.2")
                expected = \
                    "foo         1.2.1-0 known -----\n" + \
                    "foo (test2) 1.2.1-0 known -----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_list_08_after_pub_update_removal(self):
                """Install a package from a publisher which is also offered by
                another publisher.  Then alter or remove the installed package's
                publisher, and verify that list still shows the package
                as installed."""

                durl2 = self.dcs[2].get_depot_url()
                durl3 = self.dcs[3].get_depot_url()

                self.pkg("list -a")
                # Install a package from the second publisher.
                self.pkg("install pkg://test2/foo@1.0")

                # Change the origin of the publisher of an installed package to
                # that of an empty repository.  The package should still be
                # shown as known for test1 and installed for test2.
                self.pkg("set-publisher -O %s test2" % durl3)
                self.pkg("list -aHf foo@1.0")
                expected = \
                    "foo 1.0-0 known u----\n" + \
                    "foo (test2) 1.0-0 installed u----\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("set-publisher -O %s test2" % durl2)

                # Remove the publisher of an installed package, then add the
                # publisher back, but with an empty repository.  The package
                # should still be shown as known for test1 and installed
                # for test2.
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O %s test2" % durl3)
                self.pkg("list -aHf foo@1.0")
                expected = \
                    "foo 1.0-0 known u----\n" + \
                    "foo (test2) 1.0-0 installed u----\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("set-publisher -O %s test2" % durl2)

                # With the publisher of an installed package unknown, add a new
                # publisher using the repository the package was originally
                # installed from.  The pkg should be shown as known for test1,
                # installed for test2, and test3 shouldn't be listed since the
                # packages in the specified repository are for publisher test2.
                self.pkg("unset-publisher test2")

                # A refresh has to be prevented here as set-publisher will not
                # allow the provided repository URI as it is for a different
                # publisher.  However, since this test is checking for the case
                # where a different publisher's data is now being used for
                # a publisher, this can be worked around.
                self.pkg("set-publisher --no-refresh -O %s test3" % durl2)
                self.pkg("refresh test3")
                self.pkg("list -aHf foo@1.0")
                expected = \
                    "foo 1.0-0 known u----\n" + \
                    "foo (test2) 1.0-0 installed u----\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("unset-publisher test3")
                self.pkg("set-publisher -O %s test2" % durl2)

                # Uninstall the package so any remaining tests won't be
                # impacted.
                self.pkg("uninstall pkg://test2/foo@1.0")

        def test_list_09_needs_refresh(self):
                """Verify that a list operation performed when a publisher's
                metadata needs refresh works as expected."""

                durl1 = self.dcs[1].get_depot_url()

                # Package should not exist as an unprivileged user or as a
                # privileged user since it hasn't been published yet.
                self.pkg("list -a | grep newpkg", su_wrap=True, exit=1)
                self.pkg("list -a | grep newpkg", exit=1)

                self.pkgsend_bulk(durl1, self.newpkg10)

                # Package should not exist as an unprivileged user or as a
                # privileged user since the publisher doesn't need a refresh
                # yet.
                self.pkg("list -a | grep newpkg", su_wrap=True, exit=1)
                self.pkg("list -a | grep newpkg", exit=1)

                # Remove the last_refreshed file for one of the publishers so
                # that it will be seen as needing refresh.
                pkg_path = os.path.join(self.get_img_path(), "var", "pkg")
                if not os.path.exists(pkg_path):
                        pkg_path = os.path.join(self.get_img_path(),
                            ".org.opensolaris,pkg")
                        self.assertTrue(os.path.exists(pkg_path))

                os.remove(os.path.join(pkg_path, "publisher", "test1",
                    "last_refreshed"))

                # Package should not exist as an unprivileged user since the
                # metadata for the publisher has not yet been refreshed and
                # cannot be.
                self.pkg("list -a | grep newpkg", su_wrap=True, exit=1)

                # pkg list should work as an unprivileged user even though one
                # or more publishers need their metadata refreshed.
                self.pkg("list -a", su_wrap=True)

                # Package should exist as a privileged user since the metadata
                # for the publisher needs to be refreshed and can be.
                self.pkg("list -a | grep newpkg")

                # Package should now exist for unprivileged user since the
                # metadata has been refreshed.
                self.pkg("list -a | grep newpkg", su_wrap=True)

        def test_list_10_all_known_failed_refresh(self):
                """Verify that a failed implicit refresh will not prevent pkg
                list from working properly when appropriate."""

                # Set test2's origin to an unreachable URI.
                self.pkg("set-publisher --no-refresh -O http://test.invalid2 "
                    "test2")

                # Verify pkg list -a works as expected for an unprivileged user
                # when a permissions failure is encountered.
                self.pkg("list -a", su_wrap=True)

                # Verify pkg list -a fails for a privileged user when a
                # publisher's repository is unreachable.
                self.pkg("list -a", exit=1)

                # Reset test2's origin.
                durl2 = self.dcs[2].get_depot_url()
                self.pkg("set-publisher -O %s test2" % durl2)

        def test_list_11_v0_repo(self):
                """Verify that pkg list works with a v0 repository, especially
                for unprivileged users."""

                dc = self.dcs[1]
                durl = dc.get_depot_url()
                dc.stop()
                dc.set_disable_ops(["catalog/1"])
                dc.start()

                self.pkg("refresh --full")

                # This should work for an unprivileged user, even though it
                # requires manifest retrieval (because of the v0 repo).
                self.pkg("list -a", su_wrap=True)

                # This should work for a privileged user.
                self.pkg("list -a")

                dc.stop()
                dc.unset_disable_ops()
                dc.start()

                self.pkg("refresh --full")

        def test_list_matching(self):
                """Verify that pkg list pattern matching works as expected."""
                self.pkg("list -aHf foo*")
                expected = \
                    "foo         1.2.1-0 known -----\n" \
                    "foo         1.2-0   known u----\n" \
                    "foo         1.1-0   known u----\n" \
                    "foo         1.0-0   known u----\n" \
                    "foo         1-0     known u----\n" \
                    "foo (test2) 1.2.1-0 known -----\n" \
                    "foo (test2) 1.2-0   known u----\n" \
                    "foo (test2) 1.1-0   known u----\n" \
                    "foo (test2) 1.0-0   known u----\n" \
                    "foo (test2) 1-0     known u----\n" \
                    "food        1.2-0   known -----\n" \
                    "food (test2) 1.2-0  known -----\n"

                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aHf 'fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aHf '*fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aHf 'f?o*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH foo*")
                expected = \
                    "foo         1.2.1-0 known -----\n" \
                    "foo (test2) 1.2.1-0 known -----\n" \
                    "food        1.2-0   known -----\n" \
                    "food (test2) 1.2-0  known -----\n"

                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH 'fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH '*fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH 'f?o*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                for pat, ecode in (("foo food", 0), ("bogus", 1),
                    ("foo bogus", 3), ("foo food bogus", 3),
                    ("bogus quirky names", 1), ("'fo*' bogus", 3),
                    ("'fo*' food bogus", 3), ("'f?o*' bogus", 3)):
                        self.pkg("list -a %s" % pat, exit=ecode)

        def test_list_multi_name(self):
                """Test for multiple name match listing."""
                self.pkg("list -aHf foo*@1.2")
                expected = \
                    "foo          1.2.1-0 known -----\n" + \
                    "foo          1.2-0   known u----\n" + \
                    "foo  (test2) 1.2.1-0 known -----\n" + \
                    "foo  (test2) 1.2-0   known u----\n" + \
                    "food         1.2-0   known -----\n" + \
                    "food (test2) 1.2-0   known -----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH foo*@1.2")
                expected = \
                    "foo          1.2.1-0 known -----\n" + \
                    "foo  (test2) 1.2.1-0 known -----\n" + \
                    "food         1.2-0   known -----\n" + \
                    "food (test2) 1.2-0   known -----\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        # Put this one last since it screws the other tests up
        def test_list_z_empty_image(self):
                """ pkg list should fail in an empty image """

                self.image_create(self.dcs[1].get_depot_url(),
                    prefix="test1")
                self.pkg("list", exit=1)

if __name__ == "__main__":
        unittest.main()
