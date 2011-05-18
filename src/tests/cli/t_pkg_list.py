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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.fmri as fmri
import pkg.manifest as manifest
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

        hierfoo10 = """
            open hier/foo@1.0,5.11-0
            close """

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test2"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(self.rurl1, (self.foo1, self.foo10,
                    self.foo11, self.foo12, self.foo121, self.food12,
                    self.hierfoo10))

                # Ensure that the second repo's packages have exactly the same
                # timestamps as those in the first ... by copying the repo over.
                # If the repos need to have some contents which are different,
                # send those changes after restarting depot 2.
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                self.copy_repository(d1dir, d2dir, { "test1": "test2" })

                # The new repository won't have a catalog, so rebuild it.
                self.dcs[2].get_repo(auto_create=True).rebuild()

                # The third repository should remain empty and not be
                # published to.

                # Next, create the image and configure publishers.
                self.image_create(self.rurl1, prefix="test1")
                self.rurl2 = self.dcs[2].get_repo_url()
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

                self.rurl3 = self.dcs[3].get_repo_url()

        def test_pkg_list_cli_opts(self):

                self.pkg("list -@", exit=2)
                self.pkg("list -v -s", exit=2)

        def test_00(self):
                """Verify that sort order and content of a full list matches
                expected."""

                self.pkg("list -aH")
                expected = \
                    ("foo 1.2.1-0 ---\n"
                    "foo (test2) 1.2.1-0 ---\n"
                    "food 1.2-0 ---\n"
                    "food (test2) 1.2-0 ---\n"
                    "hier/foo 1.0-0 ---\n"
                    "hier/foo (test2) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -afH")
                expected = \
                    ("foo 1.2.1-0 ---\n"
                    "foo 1.2-0 ---\n"
                    "foo 1.1-0 ---\n"
                    "foo 1.0-0 ---\n"
                    "foo 1-0 ---\n"
                    "foo (test2) 1.2.1-0 ---\n"
                    "foo (test2) 1.2-0 ---\n"
                    "foo (test2) 1.1-0 ---\n"
                    "foo (test2) 1.0-0 ---\n"
                    "foo (test2) 1-0 ---\n"
                    "food 1.2-0 ---\n"
                    "food (test2) 1.2-0 ---\n"
                    "hier/foo 1.0-0 ---\n"
                    "hier/foo (test2) 1.0-0 ---\n")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Put options in different order to ensure output still matches.
                self.pkg("list -faH")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_01(self):
                """List all "foo@1.0" from auth "test1"."""
                self.pkg("list -afH pkg://test1/foo@1.0,5.11-0")
                expected = \
                    "foo 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Test 'rooted' name.
                self.pkg("list -afH //test1/foo@1.0,5.11-0")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_02(self):
                """List all "foo@1.0", regardless of publisher, with "pkg:/"
                or '/' prefix."""
                self.pkg("list -afH pkg:/foo@1.0,5.11-0")
                expected = \
                    "foo 1.0-0 ---\n" \
                    "foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Test 'rooted' name.
                self.pkg("list -afH /foo@1.0,5.11-0")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_03(self):
                """List all "foo@1.0", regardless of publisher, without "pkg:/"
                prefix."""
                self.pkg("list -afH pkg:/foo@1.0,5.11-0")
                expected = \
                    "foo         1.0-0 ---\n" \
                    "foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_04(self):
                """List all versions of package foo, regardless of publisher."""
                self.pkg("list -aHf foo")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "foo              1.2-0   ---\n" \
                    "foo              1.1-0   ---\n" \
                    "foo              1.0-0   ---\n" \
                    "foo              1-0     ---\n" \
                    "foo (test2)      1.2.1-0 ---\n" \
                    "foo (test2)      1.2-0   ---\n" \
                    "foo (test2)      1.1-0   ---\n" \
                    "foo (test2)      1.0-0   ---\n" \
                    "foo (test2)      1-0     ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH foo")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "foo (test2)      1.2.1-0 ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_05(self):
                """Show foo@1.0 from both depots, but 1.1 only from test2."""
                self.pkg("list -aHf foo@1.0-0 pkg://test2/foo@1.1-0")
                expected = \
                    "foo              1.0-0 ---\n" \
                    "foo (test2)      1.1-0 ---\n" \
                    "foo (test2)      1.0-0 ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aHf foo@1.0-0 pkg://test2/foo@1.1-0")
                expected = \
                    "foo              1.0-0 ---\n" \
                    "foo (test2)      1.1-0 ---\n" \
                    "foo (test2)      1.0-0 ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_06(self):
                """Show versions 1.0 and 1.1 of foo only from publisher test2."""
                self.pkg("list -aHf pkg://test2/foo")
                expected = \
                    "foo (test2) 1.2.1-0 ---\n" \
                    "foo (test2) 1.2-0   ---\n" \
                    "foo (test2) 1.1-0   ---\n" \
                    "foo (test2) 1.0-0   ---\n" \
                    "foo (test2) 1-0     ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH pkg://test2/foo")
                expected = \
                    "foo (test2) 1.2.1-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_07(self):
                """List all foo@1 from test1, but all foo@1.2(.x), and only list
                the latter once."""
                self.pkg("list -aHf pkg://test1/foo@1 pkg:/foo@1.2")
                expected = \
                    "foo         1.2.1-0 ---\n" \
                    "foo         1.2-0   ---\n" \
                    "foo         1.1-0   ---\n" \
                    "foo         1.0-0   ---\n" \
                    "foo         1-0     ---\n" \
                    "foo (test2) 1.2.1-0 ---\n" \
                    "foo (test2) 1.2-0   ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH pkg://test1/foo@1 pkg:/foo@1.2")
                expected = \
                    "foo         1.2.1-0 ---\n" + \
                    "foo (test2) 1.2.1-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_08_after_pub_update_removal(self):
                """Install a package from a publisher which is also offered by
                another publisher.  Then alter or remove the installed package's
                publisher, and verify that list still shows the package
                as installed."""

                self.pkg("list -a")
                # Install a package from the second publisher.
                self.pkg("install pkg://test2/foo@1.0")

                # Change the origin of the publisher of an installed package to
                # that of an empty repository.  The package should still be
                # shown for test1 and installed for test2.
                self.pkg("set-publisher -O %s test2" % self.rurl3)
                self.pkg("list -aHf /foo@1.0")
                expected = \
                    "foo 1.0-0 ---\n" + \
                    "foo (test2) 1.0-0 i--\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("set-publisher -O %s test2" % self.rurl2)

                # Remove the publisher of an installed package, then add the
                # publisher back, but with an empty repository.  The package
                # should still be shown as for test1 and installed for test2.
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O %s test2" % self.rurl3)
                self.pkg("list -aHf /foo@1.0")
                expected = \
                    "foo 1.0-0 ---\n" + \
                    "foo (test2) 1.0-0 i--\n"
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("set-publisher -O %s test2" % self.rurl2)

                # With the publisher of an installed package unknown, add a new
                # publisher using the repository the package was originally
                # installed from.  The pkg should be shown as for test1,
                # installed for test2, and test3 shouldn't be listed since the
                # packages in the specified repository are for publisher test2.
                self.pkg("unset-publisher test2")

                # Uninstall the package so any remaining tests won't be
                # impacted.
                self.pkg("uninstall pkg://test2/foo@1.0")

        def test_09_needs_refresh(self):
                """Verify that a list operation performed when a publisher's
                metadata needs refresh works as expected."""

                # Package should not exist as an unprivileged user or as a
                # privileged user since it hasn't been published yet.
                self.pkg("list -a | grep newpkg", su_wrap=True, exit=1)
                self.pkg("list -a | grep newpkg", exit=1)

                self.pkgsend_bulk(self.rurl1, self.newpkg10)

                # Package should not exist as an unprivileged user or as a
                # privileged user since the publisher doesn't need a refresh
                # yet.
                self.pkg("list -a | grep newpkg", su_wrap=True, exit=1)
                self.pkg("list -a | grep newpkg", exit=1)

                # Remove the last_refreshed file for one of the publishers so
                # that it will be seen as needing refresh.
                api_inst = self.get_img_api_obj()
                pub = api_inst.get_publisher("test1")
                os.remove(os.path.join(pub.meta_root, "last_refreshed"))

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

        def test_10_all_known_failed_refresh(self):
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
                self.pkg("set-publisher -O %s test2" % self.rurl2)

        def test_11_v0_repo(self):
                """Verify that pkg list works with a v0 repository, especially
                for unprivileged users."""

                # This test requires an actual depot due to v0 operation usage.
                dc = self.dcs[1]
                dc.set_disable_ops(["catalog/1"])
                dc.start()
                self.pkg("set-publisher --no-refresh -O %s test1" %
                    dc.get_depot_url())

                self.pkg("refresh --full")

                # This should work for an unprivileged user, even though it
                # requires manifest retrieval (because of the v0 repo).
                self.pkg("list -a", su_wrap=True)

                # This should work for a privileged user.
                self.pkg("list -a")

                dc.stop()
                dc.unset_disable_ops()

                self.pkg("set-publisher --no-refresh -O %s test1" % self.rurl1)
                self.pkg("refresh --full")

        def test_12_matching(self):
                """Verify that pkg list pattern matching works as expected."""

                self.pkg("publisher")
                self.pkg("list -aHf 'foo*'")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "foo              1.2-0   ---\n" \
                    "foo              1.1-0   ---\n" \
                    "foo              1.0-0   ---\n" \
                    "foo              1-0     ---\n" \
                    "foo (test2)      1.2.1-0 ---\n" \
                    "foo (test2)      1.2-0   ---\n" \
                    "foo (test2)      1.1-0   ---\n" \
                    "foo (test2)      1.0-0   ---\n" \
                    "foo (test2)      1-0     ---\n" \
                    "food             1.2-0   ---\n" \
                    "food (test2)     1.2-0   ---\n"

                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aHf '/fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aHf 'f?o*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                expected += \
                    "hier/foo         1.0-0   ---\n" \
                    "hier/foo (test2) 1.0-0   ---\n"
                expected = self.reduceSpaces(expected)
                self.pkg("list -aHf '*fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH 'foo*'")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "foo (test2)      1.2.1-0 ---\n" \
                    "food             1.2-0   ---\n" \
                    "food (test2)     1.2-0   ---\n" \

                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH '/fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)
                self.pkg("list -aH 'f?o*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                expected += \
                    "hier/foo         1.0-0   ---\n" \
                    "hier/foo (test2) 1.0-0   ---\n"
                expected = self.reduceSpaces(expected)
                self.pkg("list -aH '*fo*'")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                for pat, ecode in (("foo food", 0), ("bogus", 1),
                    ("foo bogus", 3), ("foo food bogus", 3),
                    ("bogus quirky names", 1), ("'fo*' bogus", 3),
                    ("'fo*' food bogus", 3), ("'f?o*' bogus", 3)):
                        self.pkg("list -a %s" % pat, exit=ecode)

        def test_13_multi_name(self):
                """Test for multiple name match listing."""
                self.pkg("list -aHf '/foo*@1.2'")
                expected = \
                    "foo          1.2.1-0 ---\n" + \
                    "foo          1.2-0   ---\n" + \
                    "foo  (test2) 1.2.1-0 ---\n" + \
                    "foo  (test2) 1.2-0   ---\n" + \
                    "food         1.2-0   ---\n" + \
                    "food (test2) 1.2-0   ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aH '/foo*@1.2'")
                expected = \
                    "foo          1.2.1-0 ---\n" + \
                    "foo  (test2) 1.2.1-0 ---\n" + \
                    "food         1.2-0   ---\n" + \
                    "food (test2) 1.2-0   ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

        def test_14_invalid_input(self):
                """Verify that invalid input is handled gracefully."""

                pats = ("bar -v", "*@a", "bar@a", "@1.0", "foo@1.0.a")
                # First, test individually.
                for val in pats:
                        self.pkg("list %s" % val, exit=1)

                # Next, test invalid input but with options.  The option
                # should not be in the error output. (If it is, the FMRI
                # parsing has parsed the option too.)
                self.pkg("list -a bar@a", exit=1)
                self.assert_(self.output.find("FMRI '-a'") == -1)

                # Last, test all at once.
                self.pkg("list %s" % " ".join(pats), exit=1)

        def test_15_latest(self):
                """Verify that FMRIs using @latest work as expected."""

                self.pkg("list -aHf foo@latest")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "foo (test2)      1.2.1-0 ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aHf foo@latest foo@1.1 //test2/foo@1.2")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "foo              1.1-0   ---\n" \
                    "foo (test2)      1.2.1-0 ---\n" \
                    "foo (test2)      1.2-0   ---\n" \
                    "foo (test2)      1.1-0   ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("list -aHf /hier/foo@latest //test1/foo@latest")
                expected = \
                    "foo              1.2.1-0 ---\n" \
                    "hier/foo         1.0-0 ---\n" \
                    "hier/foo (test2) 1.0-0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)


class TestPkgListSingle(pkg5unittest.SingleDepotTestCase):
        # Destroy test space every time.
        persistent_setup = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        unsupp10 = """
            open unsupported@1.0
            add depend type=require fmri=foo@1.0
            close """

        def test_01_empty_image(self):
                """ pkg list should fail in an empty image """

                self.image_create(self.rurl)
                self.pkg("list", exit=1)

        def __populate_repo(self, unsupp_content):
                # Publish a package and then add some unsupported action data
                # to the repository's copy of the manifest and catalog.
                sfmri = self.pkgsend_bulk(self.rurl, self.unsupp10)[0]
                pfmri = fmri.PkgFmri(sfmri)
                repo = self.get_repo(self.dcs[1].get_repodir())
                mpath = repo.manifest(pfmri)

                with open(mpath, "ab+") as mfile:
                        mfile.write(unsupp_content + "\n")

                mcontent = None
                with open(mpath, "rb") as mfile:
                        mcontent = mfile.read()

                cat = repo.get_catalog("test")
                cat.log_updates = False

                # Update the catalog signature.
                entry = cat.get_entry(pfmri)
                entry["signature-sha-1"] = manifest.Manifest.hash_create(
                    mcontent)

                # Update the catalog actions.
                self.debug(str(cat.parts))
                dpart = cat.get_part("catalog.dependency.C", must_exist=True)
                entry = dpart.get_entry(pfmri)
                entry["actions"].append(unsupp_content)

                # Write out the new catalog.
                cat.save()

        def test_02_unsupported(self):
                """Verify that packages with invalid or unsupported actions are
                handled gracefully.
                """

                # Base package needed for testing.
                self.pkgsend_bulk(self.rurl, self.foo10)

                # Verify that a package with unsupported content doesn't cause
                # a problem.
                newact = "depend type=new-type fmri=foo@1.1"

                # Now create a new image and verify that pkg list will
                # list both packages even though one of them has an
                # unparseable manifest.
                self.__populate_repo(newact)
                self.image_create(self.rurl)
                self.pkg("list -aH foo unsupported")
                expected = \
                    "foo         1.0-0 ---\n" \
                    "unsupported 1.0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                # Verify that a package with invalid content doesn't cause
                # a problem.
                newact = "depend notvalid"
                self.__populate_repo(newact)
                self.pkg("refresh --full")
                self.pkg("list -afH foo unsupported")
                expected = \
                    "foo         1.0-0 ---\n" \
                    "unsupported 1.0 ---\n" \
                    "unsupported 1.0 ---\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)


if __name__ == "__main__":
        unittest.main()
