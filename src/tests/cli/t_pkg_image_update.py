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

# Copyright (c) 2008, 2022, Oracle and/or its affiliates.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

from pkg.client.pkgdefs import *

import hashlib
import os
import random
import unittest

import pkg.misc as misc

class NoTestImageUpdate(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True
        need_ro_data = True

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

        elftest1 = """
            open elftest@1.0
            add file {0} mode=0755 owner=root group=bin path=/bin/true
            close """

        elftest2 = """
            open elftest@2.0
            add file {0} mode=0755 owner=root group=bin path=/bin/true
            close """

        # An example of dueling incorporations for an upgrade case.
        dueling_inst = """
            open entire@5.12-5.12.0.0.0.45.0
            add set name=pkg.depend.install-hold value=core-os
            add depend fmri=consolidation/java-7/java-7-incorporation type=require
            add depend facet.version-lock.consolidation/java-7/java-7-incorporation=true fmri=consolidation/java-7/java-7-incorporation@1.7.0.51.34-0 type=incorporate
            add depend fmri=consolidation/java-7/java-7-incorporation@1.7.0 type=incorporate
            add depend fmri=consolidation/osnet/osnet-incorporation type=require
            add depend facet.version-lock.consolidation/osnet/osnet-incorporation=true fmri=consolidation/osnet/osnet-incorporation@5.12-5.12.0.0.0.45.2 type=incorporate
            add depend fmri=consolidation/osnet/osnet-incorporation@5.12-5.12.0 type=incorporate
            close
            open consolidation/java-7/java-7-incorporation@1.7.0.51.34-0
            add depend fmri=runtime/java/jre-7@1.7.0.51.34,5.11 type=incorporate
            close
            open consolidation/osnet/osnet-incorporation@5.12-5.12.0.0.0.45.25345
            add set name=pkg.depend.install-hold value=core-os.osnet
            add depend fmri=pkg:/system/resource-mgmt/dynamic-resource-pools@5.12,5.12-5.12.0.0.0.45.25345 type=incorporate
            close
            open runtime/java/jre-7@1.7.0.51.34
            add depend fmri=consolidation/java-7/java-7-incorporation type=require
            close
            open system/resource-mgmt/dynamic-resource-pools@5.12-5.12.0.0.0.45.25345
            add depend fmri=consolidation/osnet/osnet-incorporation type=require
            add depend fmri=pkg:/runtime/java/jre-7@1.7.0.51.34 type=require
            close
        """

        dueling_latest = """
            open consolidation/osnet/osnet-incorporation@5.12-5.12.0.0.0.46.25205
            add set name=pkg.depend.install-hold value=core-os.osnet
            add depend fmri=pkg:/system/resource-mgmt/dynamic-resource-pools@5.12,5.12-5.12.0.0.0.46.25205 type=incorporate
            close
            open runtime/java/jre-7@1.7.0.55.13
            add depend fmri=consolidation/java-7/java-7-incorporation type=require
            close
            open system/resource-mgmt/dynamic-resource-pools@5.12,5.12-5.12.0.0.0.46.25205
            add depend fmri=consolidation/osnet/osnet-incorporation type=require
            add depend fmri=pkg:/runtime/java/jre-7@1.7.0.55.13 type=require
            close
        """

        obsolete = """
            open goingaway@1.0
            add dir mode=0755 owner=root group=bin path=/lib
            close
            open goingaway@2.0
            add set name=pkg.obsolete value=true
            close
            open moreoldstuff@1.0
            add dir mode=0755 owner=root group=bin path=/lib
            close
            open moreoldstuff@2.0
            add set name=pkg.obsolete value=true
            close
        """

        def setUp(self):
                # Two repositories are created for test2.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test2", "test4", "test5", "nightly"], image_count=2)
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.rurl4 = self.dcs[4].get_repo_url()
                self.rurl5 = self.dcs[5].get_repo_url()
                self.rurl6 = self.dcs[6].get_repo_url()
                self.pkgsend_bulk(self.rurl1, (self.foo10, self.foo11,
                    self.baz11, self.qux10, self.qux11, self.quux10,
                    self.quux11, self.corge11, self.incorp10, self.incorp11,
                    self.obsolete))

                self.pkgsend_bulk(self.rurl2, (self.foo10, self.bar10,
                    self.bar11, self.baz10, self.qux10, self.qux11,
                    self.quux10, self.quux11, self.corge10))

                # Copy contents of repository 2 to repos 4 and 5.
                for i in (4, 5):
                        self.copy_repository(self.dcs[2].get_repodir(),
                                self.dcs[i].get_repodir(),
                                { "test1": "test{0:d}".format(i) })
                        self.dcs[i].get_repo(auto_create=True).rebuild()

                self.pkgsend_bulk(self.rurl6, (self.dueling_inst,
                    self.dueling_latest))

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
                self.pkg("set-publisher -O {0} test2".format(self.rurl2))
                self.pkg("install bar@1.0")

                # Remove the publisher of an installed package, then add the
                # publisher back, but with an empty repository.  An update
                # should still be possible.
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O {0} test2".format(self.rurl3))
                self.pkg("update -nv")

                # Add two publishers with the same packages as a removed one;
                # an update should be possible despite the conflict (as
                # the newer versions will simply be ignored).
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -O {0} test4".format(self.rurl4))
                self.pkg("set-publisher -O {0} test5".format(self.rurl5))
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
                self.pkg("set-publisher -P -O {0} test2".format(self.rurl2))
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

                # Finally, cleanup and verify no packages are installed.
                self.pkg("uninstall '*'")
                self.pkg("list", exit=1)

        def test_03_update_specific_packages(self):
                """Verify that update only updates specified packages."""

                self.image_create(self.rurl1, prefix="test1")

                # Install a package from the preferred publisher.
                self.pkg("install foo@1.0")

                # Install a package from a second publisher.
                self.pkg("set-publisher -O {0} test2".format(self.rurl2))
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

        def test_upgrade_sticky(self):
                """Test that when a package specified on the command line can't
                be upgraded because of a sticky publisher, the exception raised
                is correct."""

                self.image_create(self.rurl2)
                self.pkg("install foo")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
                self.pkg("update foo@1.1", exit=1)
                self.assertTrue("test1" in self.errout)

        def test_nothingtodo(self):
                """Test that if we have multiple facets of equal length that
                we don't accidentally report that there are image updates when
                there are not."""

                facet_max = 1000
                facet_fmt = "{{0:{0:d}d}}".format(len("{0:d}".format(facet_max)))

                facet_set = set()
                random.seed()
                self.image_create()
                for i in range(15):
                        facet = facet_fmt.format(random.randint(0, facet_max))
                        if facet in facet_set:
                                # skip dups
                                continue
                        facet_set.add(facet)
                        self.pkg("change-facet {0}=False".format(facet))
                        self.pkg("update -nv", exit=EXIT_NOP)

        def test_ignore_missing(self):
                """Test that update shows correct behavior w/ and w/o
                   --ignore-missing."""
                self.image_create(self.rurl1)
                self.pkg("update missing", exit=1)
                self.pkg("update --ignore-missing missing", exit=4)

        def test_content_policy(self):
                """ Test the content-update-policy property. When set to
                'when-required' content should only be updated if the GELF content
                hash has changed, if set to 'always' content should be updated
                if there is any file change at all."""

                def get_test_sum(fname=None):
                        """ Helper to get sha256 sum of installed test file."""
                        if fname is None:
                                fname = os.path.join(self.get_img_path(),
                                    "bin/true")
                        fsum , data = misc.get_data_digest(fname,
                            hash_func=hashlib.sha256)
                        return fsum

                # Elftest1 and elftest2 have the same content and the same size,
                # just different entries in the comment section. The content
                # hash for both is the same, however the file hash is different.
                elftest1 = self.elftest1.format(os.path.join("ro_data",
                    "elftest.so.1"))
                elftest2 = self.elftest2.format(os.path.join("ro_data",
                    "elftest.so.2"))

                # get the sha256 sums from the original files to distinguish
                # what actually got installed
                elf1sum = get_test_sum(fname=os.path.join(self.ro_data_root,
                    "elftest.so.1"))
                elf2sum = get_test_sum(fname=os.path.join(self.ro_data_root,
                    "elftest.so.2"))

                elf1, elf2 = self.pkgsend_bulk(self.rurl1, (elftest1, elftest2))

                # prepare image, install elftest@1.0 and verify
                self.image_create(self.rurl1)
                self.pkg("install -v {0}".format(elf1))
                self.pkg("contents -m {0}".format(elf1))
                self.assertEqual(elf1sum, get_test_sum())

                # test default behavior (always update)
                self.pkg("update -v elftest")
                self.pkg("contents -m {0}".format(elf2))
                self.assertEqual(elf2sum, get_test_sum())
                # reset and start over
                self.pkg("uninstall elftest")
                self.pkg("install -v {0}".format(elf1))

                # set policy to when-required, file shouldn't be updated
                self.pkg("set-property content-update-policy when-required")
                self.pkg("update -v elftest")
                self.pkg("list {0}".format(elf2))
                self.assertEqual(elf1sum, get_test_sum())
                # reset and start over
                self.pkg("uninstall elftest")
                self.pkg("install -v {0}".format(elf1))

                # set policy to always, file should be updated now
                self.pkg("set-property content-update-policy always")
                self.pkg("update -v elftest")
                self.pkg("list {0}".format(elf2))
                self.assertEqual(elf2sum, get_test_sum())

                # do tests again for downgrading, test file shouldn't change
                self.pkg("set-property content-update-policy when-required")
                self.pkg("update -v {0}".format(elf1))
                self.pkg("list {0}".format(elf1))
                self.assertEqual(elf2sum, get_test_sum())
                # reset and start over
                self.pkg("uninstall elftest")
                self.pkg("install -v {0}".format(elf2))

                # set policy to always, file should be updated now
                self.pkg("set-property content-update-policy always")
                self.pkg("update -v {0}".format(elf1))
                self.pkg("list {0}".format(elf1))
                self.assertEqual(elf1sum, get_test_sum())

        def test_dueling_incs(self):
                """Verify that dueling incorporations don't result in a 'no
                solution' error in a case sometimes found with 'nightly'
                upgrades."""

                self.image_create(self.rurl6)
                self.image_clone(1)
                self.pkg("change-facet "
                    "version-lock.consolidation/osnet/osnet-incorporation=false")
                self.pkg("install entire@5.12-5.12.0.0.0.45.0 "
                    "osnet-incorporation@5.12-5.12.0.0.0.45.25345 "
                    "system/resource-mgmt/dynamic-resource-pools@5.12-5.12.0.0.0.45.25345")

                # Failure is expected for these cases because an installed
                # incorporation prevents the upgrade of an installed dependency
                # required by the new packages.

                # Should fail and result in 'no solution' because user failed to
                # specify any input. In this case we also get the constrained
                # operation exit status.
                self.pkg("update -nv", exit=9, assert_solution=False)
                self.assertTrue("No solution" in self.errout)

                # Should fail, but not result in 'no solution' because user
                # specified a particular package.
                self.pkg("update -nv osnet-incorporation@latest", exit=1)
                self.assertTrue("No matching version" in self.errout)

                # Should exit with 'nothing to do' since update to new version
                # of osnet-incorporation is not possible.
                self.pkg("update -nv osnet-incorporation", exit=4)

                # A pkg update (with no arguments) should not fail if we are a
                # linked image child because we're likely constrained by our
                # parent dependencies.
                self.pkg("attach-linked --linked-md-only -p system:foo "
                    "{0}".format(self.img_path(1)))
                self.pkg("update -nv", exit=4)

        def test_display_removed_pkgs(self):
            """Verify that the names of removed packages are displayed during
            upgrade."""

            self.image_create(self.rurl1)
            self.pkg("install foo@1.0 goingaway@1.0 moreoldstuff@1.0")
            self.pkg("update", exit=0)

            # Check the header and the package names without a version are
            # present.
            # Ensure that a package that has not been obsoleted is not included.
            self.assertTrue("Removed Packages:" in self.output)

            self.assertTrue("goingaway" in self.output)
            self.assertFalse("goingaway@" in self.output)
            self.assertTrue("moreoldstuff" in self.output)
            self.assertFalse("moreoldstuff@" in self.output)

            self.assertFalse("foo" in self.output)

class TestIDROps(pkg5unittest.SingleDepotTestCase):

        need_ro_data = True

        idr_comb = """
            open pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103,5.11-0.1:20160225T115559Z 
            add set name=pkg.description value="test package"
            add dir path=foo/hello owner=root group=sys mode=555
            close
            open pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103,5.11-0.1.1697.1:20160225T115610Z 
            add set name=pkg.description value="test package"
            add dir path=foo/hello owner=root group=sys mode=555
            add depend type=require fmri=idr1697@1
            close
            open pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103,5.11-0.1:20160225T115616Z 
            add set name=pkg.description value="test package"
            add dir path=foo/hello owner=root group=sys mode=555
            close
            open pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.3.2.906,5.11-0.1:20160225T115622Z 
            add set name=pkg.description value="test package"
            add dir path=foo/hello owner=root group=sys mode=555
            close
            open pkg://test/management/em-sysmgmt-ecpc/opscenter-ecpc-incorporation@12.2.2.1103,5.11-0.1:20141203T103418Z
            add set name=pkg.description value="This incorporation constrains packages for the opscenter enterprise and proxy controller."
            add depend fmri=management/em-sysmgmt-ecpc/em-oc-ec@12.2.2.1103-0.1 type=incorporate
            add depend fmri=management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103-0.1 type=incorporate
            add depend fmri=management/em-sysmgmt-ecpc/em-oc-pc@12.2.2.1103-0.1 type=incorporate
            close
            open pkg://test/idr1697@1
            add set name=pkg.description value="idr package"
            add dir path=foo/hello owner=root group=sys mode=555
            add depend type=incorporate fmri=management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103-0.1.1697.1
            close"""


        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, self.idr_comb)

        def test_idr_application(self):
                """Verify branch versioning that might that might lead to odd
                ordering of the possible FMRIs will not be erroneously trimmed
                during installation or removal."""

                self.image_create(self.rurl)
                self.pkg("install opscenter-ecpc-incorporation")
                self.pkg("list -afv em-oc-common")
                # If branch versioning ordering is working correctly, the next
                # two packages should be installable.
                self.pkg("install pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103,5.11-0.1:20160225T115559Z")
                self.pkg("install pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103,5.11-0.1:20160225T115616Z")
                # If branch ordering is broken, only this package will be
                # instalable.
                self.pkg("install pkg://test/management/em-sysmgmt-ecpc/em-oc-common")
                self.pkg("list -afv em-oc-common")
                # If branch ordering is broken, the upgrade will fail because
                # em-oc-common won't be installable despite removal of the idr.
                self.pkg("update --reject pkg://test/idr1697@1 "
                    "pkg://test/management/em-sysmgmt-ecpc/em-oc-common@12.2.2.1103,5.11-0.1:20160225T115616Z")


class NoTestPkgUpdateOverlappingPatterns(pkg5unittest.SingleDepotTestCase):

        a_1 = """
            open a@1.0,5.11-0
            close """

        pub2_a_1 = """
            open pkg://pub2/a@1.0,5.11-0
            close """

        a_11 = """
            open a@1.1,5.11-0
            close """

        a_2 = """
            open a@2.0,5.11-0
            close """

        pub2_a_2 = """
            open pkg://pub2/a@2.0,5.11-0
            close """

        a_3 = """
            open a@3.0,5.11-0
            close """

        aa_1 = """
            open aa@1.0,5.11-0
            close """

        aa_2 = """
            open aa@2.0,5.11-0
            close """

        afoo_1 = """
            open a/foo@1.0,5.11-0
            close """

        bfoo_1 = """
            open b/foo@1.0,5.11-0
            close """

        fooa_1 = """
            open foo/a@1.0,5.11-0
            close """

        foob_1 = """
            open foo/b@1.0,5.11-0
            close """

        def test_overlapping_patterns_one_stem_update(self):
                self.pkgsend_bulk(self.rurl, self.a_1 + self.a_2 + self.a_11)
                api_inst = self.image_create(self.rurl)

                self._api_install(api_inst, ["a@1.0"])
                self._api_update(api_inst, pkgs_update=["a@latest", "a@2"],
                    noexecute=True)
                self.pkg("update a@1.1 a@2", exit=1)

        def test_overlapping_patterns_multi_stems_update(self):
                self.pkgsend_bulk(self.rurl, self.a_1 + self.a_11 + self.a_2 +
                    self.aa_1 + self.aa_2)
                api_inst = self.image_create(self.rurl)

                self._api_install(api_inst, ["a@1.0", "aa@1.0"])
                self._api_update(api_inst, pkgs_update=["*", "a@1.1"])
                self.pkg("list aa@2.0 a@1.1")
                self._api_uninstall(api_inst, ["*"])

                self._api_install(api_inst, ["a@1.0", "aa@1.0"])
                self._api_update(api_inst, pkgs_update=["*", "a@1.1", "a*@2"])
                self.pkg("list aa@2.0 a@1.1")
                self._api_uninstall(api_inst, ["*"])

        def test_overlapping_patterns_multi_publisher_update(self):
                self.pkgsend_bulk(self.rurl, self.a_1 + self.a_2 +
                    self.aa_1 + self.aa_2 + self.pub2_a_1 + self.pub2_a_2)
                api_inst = self.image_create(self.rurl)
                self.pkg("set-publisher -P test")

                # Test that naming a specific publisher and stem will override
                # the general wildcard.
                self._api_install(api_inst, ["a@1", "aa@1"])
                self.pkg("update '*' 'pkg://pub2/a@1'")
                self.pkg("list -Hv pkg://pub2/a@1 pkg://test/aa@2")
                self._api_uninstall(api_inst, ["*"])

                # Test that naming a specific publisher will correctly change
                # the publisher of the installed package.
                self._api_install(api_inst, ["a@1", "aa@1"])
                self.pkg("update 'pkg://pub2/*@1'")
                self.pkg("list -Hv pkg://pub2/a@1 pkg://test/aa@1")
                self._api_uninstall(api_inst, ["*"])

                # Test that a specific publisher and stem will override an
                # unspecified publisher with a specific stem.
                self._api_install(api_inst, ["a@1"])
                self.pkg("update 'a@1' 'pkg://pub2/a@1'")
                self.pkg("list -Hv pkg://pub2/a@1")
                self.pkg("update 'a@2' '//test/a@2'")
                self.pkg("list -Hv pkg://test/a@2")
                self._api_uninstall(api_inst, ["*"])

                self._api_install(api_inst, ["a@1"])
                self.pkg("update 'a@1' 'pkg://pub2/a@2'", exit=1)
                self._api_uninstall(api_inst, ["*"])

                # Test that a specific publisher with a wildcard will override a
                # unspecified publisher with a wildcard.
                self._api_install(api_inst, ["a@1", "aa@1"])
                self.pkg("update '*' 'pkg://pub2/*@1'")
                self.pkg("list -Hv pkg://pub2/a@1 pkg://test/aa@2")
                self._api_uninstall(api_inst, ["*"])

                # Test that a specific stem without a specific publisher
                # overrides a specific publisher without a specific stem.
                self._api_install(api_inst, ["a@1", "aa@1"])
                self.pkg("update '*' 'pkg://pub2/*@1' 'a@2'")
                self.pkg("list -Hv pkg://test/a@2 pkg://test/aa@2")
                self._api_uninstall(api_inst, ["*"])

                # Test that conflicting publishers results in an error.
                self._api_install(api_inst, ["a@1", "aa@1"])
                self.pkg("update '*' 'pkg://pub2/a@1' 'pkg://test/a@2'", exit=1)
                self.pkg("update '*' 'pkg://pub2/*@1' 'pkg://test/*@2'", exit=1)
                self._api_uninstall(api_inst, ["*"])


if __name__ == "__main__":
        unittest.main()
