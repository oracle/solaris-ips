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

# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import os


class TestImageUpdate(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        bar11 = """
            open bar@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        baz10 = """
            open baz@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        baz11 = """
            open baz@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        qux10 = """
            open qux@1.0,5.11-0
            add depend type=require fmri=pkg:/quux@1.0
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        qux11 = """
            open qux@1.1,5.11-0
            add depend type=require fmri=pkg:/quux@1.1
            add dir mode=0755 owner=root group=bin path=/lib
            close """

        quux10 = """
            open quux@1.0,5.11-0
            add depend type=require fmri=pkg:/corge@1.0
            add dir mode=0755 owner=root group=bin path=/usr
            close """

        quux11 = """
            open quux@1.1,5.11-0
            add depend type=require fmri=pkg:/corge@1.1
            add dir mode=0755 owner=root group=bin path=/usr
            close """

        corge10 = """
            open corge@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        corge11 = """
            open corge@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        incorp10 = """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=foo@1.0
            add depend type=incorporate fmri=bar@1.0
            add set name=pkg.depend.install-hold value=test
            close """

        incorp11 = """
            open incorp@1.1,5.11-0
            add depend type=incorporate fmri=foo@1.1
            add depend type=incorporate fmri=bar@1.1
            add set name=pkg.depend.install-hold value=test
            close """

        def setUp(self):
                # Two repositories are created for test2.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test2", "test4", "test5"])
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.rurl4 = self.dcs[4].get_repo_url()
                self.rurl5 = self.dcs[5].get_repo_url()
                self.pkgsend_bulk(self.rurl1, (self.foo10, self.foo11,
                    self.baz11, self.qux10, self.qux11, self.quux10,
                    self.quux11, self.corge11, self.incorp10, self.incorp11))

                self.pkgsend_bulk(self.rurl2, (self.foo10, self.bar10,
                    self.bar11, self.baz10, self.qux10, self.qux11,
                    self.quux10, self.quux11, self.corge10))

                # Copy contents of repository 2 to repos 4 and 5.
                for i in (4, 5):
                        self.copy_repository(self.dcs[2].get_repodir(),
                                self.dcs[i].get_repodir(),
                                { "test1": "test%d" % i })
                        self.dcs[i].get_repo(auto_create=True).rebuild()

        def test_image_update_bad_opts(self):
                """Test update with bad options."""

                self.image_create(self.rurl1, prefix="test1")
                self.pkg("update -@", exit=2)
                self.pkg("update -vq", exit=2)

        def test_01_after_pub_removal(self):
                """Install packages from multiple publishers, then verify that
                removal of the second publisher will not prevent an
                update."""

                self.image_create(self.rurl1, prefix="test1")

                # Install a package from the preferred publisher.
                self.pkg("install foo@1.0")

                # Install a package from a second publisher.
                self.pkg("set-publisher -O %s test2" % self.rurl2)
                self.pkg("install bar@1.0")

                # Remove the publisher of an installed package, then add the
                # publisher back, but with an empty repository.  An update
                # should still be possible.
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O %s test2" % self.rurl3)
                self.pkg("update -nv")

                # Add two publishers with the same packages as a removed one;
                # an update should be possible despite the conflict (as
                # the newer versions will simply be ignored).
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O %s test4" % self.rurl4)
                self.pkg("set-publisher -O %s test5" % self.rurl5)
                self.pkg("update -nv")

                # Remove one of the conflicting publishers. An update
                # should still be possible even though the conflicts no longer
                # exist and the original publisher is unknown (see bug 6856).
                self.pkg("unset-publisher test4")
                self.pkg("update -nv")

                # Remove the remaining test publisher.
                self.pkg("unset-publisher test5")

        def test_02_update_multi_publisher(self):
                """Verify that updates work as expected when different
                publishers offer the same package."""

                self.image_create(self.rurl1, prefix="test1")

                # First, verify that the preferred status of a publisher will
                # not affect which source is used for update when two
                # publishers offer the same package and the package publisher
                # was preferred at the time of install.
                self.pkg("set-publisher -P -O %s test2" % self.rurl2)
                self.pkg("install foo@1.0")
                self.pkg("info foo@1.0 | grep test2")
                self.pkg("set-publisher -P test1")
                self.pkg("update -v", exit=4)
                self.pkg("info foo@1.1 | grep test1", exit=1)
                self.pkg("uninstall foo")

                # Next, verify that the preferred status of a publisher will
                # not cause an upgrade of a package if the newer version is
                # offered by the preferred publisher and the package publisher
                # was not preferred at the time of isntall and was not used
                # to install the package.
                self.pkg("install baz@1.0")
                self.pkg("info baz@1.0 | grep test2")
                # Also verify that the client still accepts 'image-update'
                # as a synonym for 'update' for compatibility.
                self.pkg("image-update -v", exit=4)
                self.pkg("info baz@1.0 | grep test2")

                # Finally, cleanup and verify no packages are installed.
                self.pkg("uninstall '*'")
                self.pkg("list", exit=1)

        def test_03_update_specific_packages(self):
                """Verify that update only updates specified packages."""

                self.image_create(self.rurl1, prefix="test1")

                # Install a package from the preferred publisher.
                self.pkg("install foo@1.0")

                # Install a package from a second publisher.
                self.pkg("set-publisher -O %s test2" % self.rurl2)
                self.pkg("install bar@1.0")

                # Update just bar, and then verify foo wasn't updated.
                self.pkg("update bar")
                self.pkg("info bar@1.1 foo@1.0")

                # Now update bar back to 1.0 and then verify that update '*',
                # update '*@*', or update without arguments will update all
                # packages.
                self.pkg("update bar@1.0")
                self.pkg("install incorp@1.0")

                self.pkg("update")
                self.pkg("info bar@1.1 foo@1.1 incorp@1.1")

                self.pkg("update *@1.0")
                self.pkg("info bar@1.0 foo@1.0 incorp@1.0")

                self.pkg("update '*'")
                self.pkg("info bar@1.1 foo@1.1 incorp@1.1")

                self.pkg("update bar@1.0 foo@1.0 incorp@1.0")
                self.pkg("info bar@1.0 foo@1.0 incorp@1.0")

                self.pkg("update '*@*'")
                self.pkg("info bar@1.1 foo@1.1 incorp@1.1")

                # Now rollback everything to 1.0, and then verify that
                # '@latest' will take everything to the latest version.
                self.pkg("update '*@1.0'")
                self.pkg("info bar@1.0 foo@1.0 incorp@1.0")

                self.pkg("update '*@latest'")
                self.pkg("info bar@1.1 foo@1.1 incorp@1.1")

        def test_bug_18536(self):
                """Test that when a package specified on the command line can't
                be upgraded because of a sticky publisher, the exception raised
                is correct."""

                self.image_create(self.rurl2)
                self.pkg("install foo")
                self.pkg("set-publisher -p %s" % self.rurl1)
                self.pkg("update foo@1.1", exit=1)
                self.assert_("test1" in self.errout)


if __name__ == "__main__":
        unittest.main()
