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

# Copyright (c) 2008, 2023, Oracle and/or its affiliates.

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import rapidjson as json
import os
import shutil
import unittest

import pkg.catalog as catalog
import pkg.actions as actions
import pkg.fmri as fmri

class TestPkgInfoBasics(pkg5unittest.SingleDepotTestCase):
    # Only start/stop the depot once (instead of for every test)
    persistent_setup = True

    bronze10 = """
            open bronze@1.0,5.11-0:20110910T004546Z
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license tmp/copyright1 license=copyright
            close
        """

    bronze05 = """
            open bronze@0.5,5.11-0:20110908T004546Z
            add license tmp/copyright0 license=copyright
            close
        """

    badfile10 = """
            open badfile@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=/tmp/baz-file
            close
        """

    baddir10 = """
            open baddir@1.0,5.11-0
            add dir mode=755 owner=root group=bin path=/tmp/baz-dir
            close
        """

    human = """
            open human@0.9.8.18,5.11-0:20110910T004546Z
            add set name=pkg.human-version value=0.9.8r
            close
        """

    human2 = """
            open human2@0.9.8.18,5.11-0:20110908T004546Z
            add set name=pkg.human-version value=0.9.8.18
            close
        """

    misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
        "tmp/bronze2", "tmp/copyright1", "tmp/copyright0", "tmp/sh",
        "tmp/baz"]

    def __check_qoutput(self, errout=False):
        self.assertEqualDiff(self.output, "")
        if errout:
            self.assertTrue(self.errout != "",
                "-q must print fatal errors!")
        else:
            self.assertTrue(self.errout == "",
                "-q should only print fatal errors!")

    def setUp(self):
        pkg5unittest.SingleDepotTestCase.setUp(self)
        self.make_misc_files(self.misc_files)
        self.plist = self.pkgsend_bulk(self.rurl, (self.badfile10,
            self.baddir10, self.bronze10, self.bronze05, self.human,
            self.human2))

    def test_pkg_info_bad_fmri(self):
        """Test bad frmi's with pkg info."""

        pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    close
                """
        self.pkgsend_bulk(self.rurl, pkg1)
        self.image_create(self.rurl)

        self.pkg("info foo@x.y", exit=1)
        # Should only print fatal errors when using -q.
        self.pkg("info -q foo@x.y", exit=1)
        self.__check_qoutput(errout=True)
        self.pkg("info pkg:/man@0.5.11,5.11-0.95:20080807T160129",
            exit=1)
        self.pkg("info pkg:/man@0.5.11,5.11-0.95:20080807T1", exit=1)
        self.pkg("info pkg:/man@0.5.11,5.11-0.95:", exit=1)
        self.pkg("info pkg:/man@0.5.11,5.11-0.", exit=1)
        self.pkg("info pkg:/man@0.5.11,5.11-", exit=1)
        self.pkg("info pkg:/man@0.5.11,-", exit=1)
        self.pkg("info pkg:/man@-", exit=1)
        self.pkg("info pkg:/man@", exit=1)

        # Bug 4878
        self.pkg("info -r _usr/bin/stunnel", exit=1)
        self.pkg("info _usr/bin/stunnel", exit=1)

        # bad version
        self.pkg("install jade")
        self.pkg("info pkg:/foo@bar.baz", exit=1)
        self.pkg("info pkg:/foo@bar.baz jade", exit=1)
        self.pkg("info -r pkg:/foo@bar.baz", exit=1)

        # bad time
        self.pkg("info pkg:/foo@0.5.11,5.11-0.91:20080613T999999Z",
            exit=1)

    def test_info_empty_image(self):
        """local pkg info should fail in an empty image; remote
        should succeed on a match """

        self.image_create(self.rurl)
        self.pkg("info", exit=1)

    def test_info_local_remote(self):
        """pkg: check that info behaves for local and remote cases."""

        pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video"
                    close
                """

        pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    add set pkg.description="Short desc"
                    close
                """

        pkg3 = """
                    open copper@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set pkg.description="This package constrains package versions to those for build 123.  WARNING: Proper system update and correct package selection depend on the presence of this incorporation.  Removing this package will result in an unsupported system."
                    close
                """

        # This unit test needs an actual depot due to unprivileged user
        # testing.
        self.dc.start()
        plist = self.pkgsend_bulk(self.durl, (pkg1, pkg2, pkg3))
        self.image_create(self.durl)

        # Install one package and verify
        self.pkg("install jade")
        self.pkg("verify -v")

        # Now remove the manifest and manifest cache for jade and retry
        # the info for an unprivileged user both local and remote.
        pfmri = fmri.PkgFmri(plist[0])
        mdir = os.path.dirname(self.get_img_manifest_path(pfmri))
        shutil.rmtree(mdir)
        self.assertFalse(os.path.exists(mdir))

        mcdir = self.get_img_manifest_cache_dir(pfmri)
        shutil.rmtree(mcdir)
        self.assertFalse(os.path.exists(mcdir))

        # A remote request should work even though local manifest is gone.
        self.pkg("info -r jade", su_wrap=True)

        # A local request should succeed even though manifest is missing
        # since we can still retrieve it from the publisher repository.
        self.pkg("info jade", su_wrap=True)

        # Remove the publisher, and verify a remote or local request
        # fails since the manifest isn't cached within the image and we
        # can't retrieve it.
        self.pkg("unset-publisher test")
        self.pkg("info -r jade", su_wrap=True, exit=1)
        self.assertTrue("no errors" not in self.errout, self.errout)
        self.assertTrue("Unknown" not in self.errout, self.errout)

        self.pkg("info jade", su_wrap=True, exit=1)
        self.assertTrue("no errors" not in self.errout, self.errout)
        self.assertTrue("Unknown" not in self.errout, self.errout)

        self.pkg("set-publisher test")
        self.pkg("info -r jade", su_wrap=True, exit=1)
        self.assertTrue("no errors" not in self.errout, self.errout)
        self.assertTrue("Unknown" not in self.errout, self.errout)

        self.pkg("info jade", su_wrap=True, exit=1)
        self.assertTrue("no errors" not in self.errout, self.errout)
        self.assertTrue("Unknown" not in self.errout, self.errout)

        self.pkg("set-publisher -p {0} test".format(self.durl))

        # Check local info
        self.pkg("info jade | grep 'State: Installed'")
        self.pkg("info jade | grep '      Category: Applications/Sound and Video'")
        self.pkg("info jade | grep '      Category: Applications/Sound and Video (org.opensolaris.category.2008)'", exit=1)
        self.pkg("info jade | grep 'Description:'", exit=1)
        self.pkg("info turquoise 2>&1 | grep 'no packages matching'")
        self.pkg("info emerald", exit=1)
        self.pkg("info emerald 2>&1 | grep 'no packages matching'")
        self.pkg("info 'j*'")
        self.pkg("info '*a*'")
        self.pkg("info jade", su_wrap=True)
        # Should only print fatal errors when using -q.
        self.pkg("info -q jade")
        self.__check_qoutput(errout=False)

        # Check remote info
        self.pkg("info -r jade | grep 'State: Installed'")
        self.pkg("info -r jade | grep '      Category: Applications/Sound and Video'")
        self.pkg("info -r jade | grep '      Category: Applications/Sound and Video (org.opensolaris.category.2008)'", exit=1)
        self.pkg("info -r turquoise | grep 'State: Not installed'")
        self.pkg("info -r turquoise | grep '      Category: System/Security/Foo/bar/Baz'")
        self.pkg("info -r turquoise | grep '      Category: System/Security/Foo/bar/Baz (org.opensolaris.category.2008)'", exit=1)
        self.pkg("info -r turquoise | grep '   Description: Short desc'")
        # Should only print fatal errors when using -q.
        self.pkg("info -qr turquoise")
        self.__check_qoutput(errout=False)
        self.pkg("info -r turquoise")

        # Now remove the manifest and manifest cache for turquoise and
        # retry the info -r for an unprivileged user.
        pfmri = fmri.PkgFmri(plist[1])
        mdir = os.path.dirname(self.get_img_manifest_path(pfmri))
        shutil.rmtree(mdir)
        self.assertFalse(os.path.exists(mdir))

        mcdir = self.get_img_manifest_cache_dir(pfmri)
        shutil.rmtree(mcdir)
        self.assertFalse(os.path.exists(mcdir))

        self.pkg("info -r turquoise", su_wrap=True)

        # Verify output.
        lines = self.output.split("\n")
        self.assertEqual(lines[1], "   Description: Short desc")
        self.assertEqual(lines[2],
            "      Category: System/Security/Foo/bar/Baz")
        self.pkg("info -r copper")
        lines = self.output.split("\n")
        self.assertEqual(lines[1],
           "   Description: This package constrains package versions to those for build 123.")

        self.assertEqual(lines[2], "                WARNING: Proper system update and correct package selection")
        self.assertEqual(lines[3], "                depend on the presence of this incorporation.  Removing this")
        self.assertEqual(lines[4], "                package will result in an unsupported system.")
        self.assertEqual(lines[5], "         State: Not installed")
        # Should only print fatal errors when using -q.
        self.pkg("info -qr turquoise")
        self.__check_qoutput(errout=False)
        # Now check for an unknown remote package.
        self.pkg("info -r emerald", exit=1)
        self.pkg("info -r emerald 2>&1 | grep 'no packages matching'")
        # Should only print fatal errors when using -q.
        self.pkg("info -qr emerald", exit=1)
        self.__check_qoutput(errout=False)

        self.dc.stop()

    def test_bug_2274(self):
        """Verify that a failure to retrieve license information, for
        one or more packages specified, will result in an exit code of
        1 (complete failure) or 3 (partial failure) and a printed
        message.
        """

        pkg1 = """
                    open silver@1.0,5.11-0
                    close
                """

        self.pkgsend_bulk(self.rurl, pkg1)
        self.image_create(self.rurl)
        self.pkg("info --license -r bronze")
        self.pkg("info --license -r silver", exit=1)
        # Should only print fatal errors when using -q.
        self.pkg("info --license -qr silver", exit=1)
        self.__check_qoutput(errout=False)
        self.pkg("info --license -r bronze silver", exit=3)
        self.pkg("info --license -r silver 2>&1 | grep 'no license information'")

        self.pkg("install bronze silver")

        self.pkg("info --license bronze")
        # Should only print fatal errors when using -q.
        self.pkg("info --license -q bronze")
        self.__check_qoutput(errout=False)

        self.pkg("info --license silver", exit=1)
        # Should only print fatal errors when using -q.
        self.pkg("info --license -q silver", exit=1)
        self.__check_qoutput(errout=False)

        self.pkg("info --license bronze silver", exit=3)
        # Should only print fatal errors when using -q.
        self.pkg("info --license -q bronze silver", exit=3)
        self.__check_qoutput(errout=False)

        self.pkg("info --license silver 2>&1 | grep 'no license information'")

    def test_info_attribute(self):
        """Verify that 'pkg info' handles optional attributes as expected."""

        pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video"
                    add set name=info.maintainer value="Bob Smith <bob.smith@example.com>" value="allen knight <allen.knight@example.com>" value="Anna Kour <Anna.Kour@example.com"
                    add set name=info.upstream value="Gisle Aas"
                    add set name=info.source-url value=http://search.cpan.org/CPAN/authors/id/G/GA/GAAS/URI-1.37.tar.gz
                    add set name=info.maintainer-url value=""
                    close
                """

        pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    add set pkg.description="Short desc"
                    close
                """
        pkg3 = """
                    open copper@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set pkg.description="This package constrains package versions to those for build 123.  WARNING: Proper system update and correct packagsudo ../run.py -dvo test_info_local_remote selection depend on the presence of this incorporation.  Removing this package will result in an unsupported system."
                    add set name=opensolaris.gui.classification value=freedesktop.org:System
                    add set name=info.maintainer-url value="abc"
                    close
                """

        plist = self.pkgsend_bulk(self.rurl, (pkg1, pkg2, pkg3))
        self.image_create(self.rurl)

        # Install packages and verify
        self.pkg("install jade")
        self.pkg("install turquoise")
        self.pkg("install copper")
        self.pkg("verify -v")

        # grep for some attributes that are defined and they have
        # single values
        self.pkg("info jade")
        self.assertTrue("Category" in self.output)

        # grep for some attributes that are defined and they have
        # multiple values
        self.pkg("info jade")
        self.assertTrue("Project Maintainer" in self.output)

        # grep for some attributes that are defined , with no value
        self.pkg("info jade")
        self.assertTrue("Project Maintainer URL" not in self.output)

        # grep for same attributes that are defined above in different
        # packages, with some value
        self.pkg("info copper")
        self.assertTrue("Project Maintainer URL" in self.output)

        # grep for attributes that are not defined
        self.pkg("info jade")
        self.assertTrue("info.foo" not in self.output)

    def test_info_bad_packages(self):
        """Verify that pkg info handles packages with invalid
        metadata."""

        self.image_create(self.rurl)

        # Verify that no packages are installed.
        self.pkg("list", exit=1)
        plist = self.plist[:2]

        # This should succeed and cause the manifests to be cached.
        self.pkg("info -r {0}".format(" ".join(p for p in plist)))

        # Now attempt to corrupt the client's copy of the manifest by
        # adding malformed actions.
        for p in plist:
            self.debug("Testing package {0} ...".format(p))
            pfmri = fmri.PkgFmri(p)
            mdata = self.get_img_manifest(pfmri)
            if mdata.find("dir") != -1:
                src_mode = "mode=755"
            else:
                src_mode = "mode=644"

            for bad_act in (
                'set name=description value="" \" my desc \" ""',
                "set name=com.sun.service.escalations value="):
                self.debug("Testing with bad action "
                    "'{0}'.".format(bad_act))
                bad_mdata = mdata + "{0}\n".format(bad_act)
                self.write_img_manifest(pfmri, bad_mdata)
                self.pkg("info -r {0}".format(pfmri.pkg_name), exit=0)

    def test_human_version(self):
        """Verify that info returns the expected output for packages
        with a human-readable version defined. If it is the same as
        version number, then only version number is displayed"""

        self.image_create(self.rurl)
        self.pkg("info -r human | grep 'Version: 0.9.8.18 (0.9.8r)'")

        # Verify that human version number should not be displayed
        # if it is identical to the version number.
        self.pkg("info -r human2 | grep 'Version: 0.9.8.18$'")

    def test_ranked(self):
        """Verify that pkg info -r returns expected results when
        multiple publishers provide the same package based on
        publisher search order."""

        # because we compare date strings we must run this in
        # a consistent locale, which we made 'C'

        os.environ['LC_ALL'] = 'C'

        # Create an isolated repository for this test
        repodir = os.path.join(self.test_root, "test-ranked")
        self.create_repo(repodir)
        self.pkgrepo("add-publisher -s {0} test".format(repodir))
        self.pkgsend_bulk(repodir, (self.bronze10, self.human))

        self.pkgrepo("add-publisher -s {0} test2".format(repodir))
        self.pkgrepo("set -s {0} publisher/prefix=test2".format(repodir))
        self.pkgsend_bulk(repodir, self.bronze10)

        self.pkgrepo("add-publisher -s {0} test3".format(repodir))
        self.pkgrepo("set -s {0} publisher/prefix=test3".format(repodir))
        self.pkgsend_bulk(repodir, self.bronze10)

        # Create a test image.
        self.image_create()
        self.pkg("set-publisher -p {0}".format(repodir))

        # Test should be higher ranked than test2 since the default
        # for auto-configuration is to use lexical order when
        # multiple publishers are found.  As such, info -r should
        # return results for 'test' by default.
        self.pkg("info -r bronze human")
        expected = """\
 Name: bronze
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110910T004546Z

 Name: human
 State: Not installed
 Publisher: test
 Version: 0.9.8.18 (0.9.8r)
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 0.00 B
 FMRI: pkg://test/human@0.9.8.18-0:20110910T004546Z
"""
        self.assertEqualDiff(expected, self.reduceSpaces(self.output))

        # Verify that if the publisher is specified, that is preferred
        # over rank.
        self.pkg("info -r //test2/bronze")
        expected = """\
 Name: bronze
 State: Not installed
 Publisher: test2
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test2/bronze@1.0-0:20110910T004546Z
"""
        self.assertEqualDiff(expected, self.reduceSpaces(self.output))

        # Verify that if stem is specified with and without publisher,
        # both matches are listed if the higher-ranked publisher differs
        # from the publisher specified.
        self.pkg("info -r //test/bronze bronze")
        expected = """\
 Name: bronze
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110910T004546Z
"""
        self.assertEqualDiff(expected, self.reduceSpaces(self.output))

        self.pkg("info -r //test2/bronze bronze")
        expected = """\
 Name: bronze
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110910T004546Z

 Name: bronze
 State: Not installed
 Publisher: test2
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test2/bronze@1.0-0:20110910T004546Z
"""
        self.assertEqualDiff(expected, self.reduceSpaces(self.output))

        self.pkg("info -r //test3/bronze //test2/bronze bronze")
        expected = """\
 Name: bronze
 State: Not installed
 Publisher: test
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test/bronze@1.0-0:20110910T004546Z

 Name: bronze
 State: Not installed
 Publisher: test2
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test2/bronze@1.0-0:20110910T004546Z

 Name: bronze
 State: Not installed
 Publisher: test3
 Version: 1.0
 Branch: 0
Packaging Date: Sat Sep 10 00:45:46 2011
 Size: 54.00 B
 FMRI: pkg://test3/bronze@1.0-0:20110910T004546Z
"""
        self.assertEqualDiff(expected, self.reduceSpaces(self.output))

        os.environ["LC_ALL"] = "en_US.UTF-8"

    def test_renamed_packages(self):
        """Verify that info returns the expected output for renamed
        packages."""

        # because we compare date strings we must run this in
        # a consistent locale, which we made 'C'
        os.environ['LC_ALL'] = 'C'

        target10 = """
                    open target@1.0
                    close
                """

        # Renamed package for all variants, with correct dependencies.
        ren_correct10 = """
                    open ren_correct@1.0
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=target@1.0 variant.cat=bobcat
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

        # Renamed package for other variant, with dependencies only for
        # for other variant.
        ren_op_variant10 = """
                    open ren_op_variant@1.0
                    add set name=pkg.renamed value=true variant.cat=lynx
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

        # Renamed package for current image variant, with dependencies
        # only for other variant.
        ren_variant_missing10 = """
                    open ren_variant_missing@1.0
                    add set name=pkg.renamed value=true variant.cat=bobcat
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

        # Renamed package for multiple variants, with dependencies
        # missing for one variant.
        ren_partial_variant10 = """
                    open ren_partial_variant@1.0
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=target@1.0 variant.cat=lynx
                    close
                """

        plist = self.pkgsend_bulk(self.rurl, (target10, ren_correct10,
            ren_op_variant10, ren_variant_missing10,
            ren_partial_variant10))

        # Create an image.
        variants = { "variant.cat": "bobcat" }
        self.image_create(self.rurl, variants=variants)

        # First, verify that a renamed package (for all variants), and
        # with the correct dependencies will provide the expected info.
        self.pkg("info -r ren_correct")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[1])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: ren_correct
         State: Not installed (Renamed)
    Renamed to: target@1.0
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)

        # Next, verify that a renamed package (for a variant not
        # applicable to this image), and with dependencies that
        # are only for that other variant will provide the expected
        # info.  Ensure package isn't seen as renamed for current
        # variant.
        self.pkg("info -r ren_op_variant")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[2])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: ren_op_variant
         State: Not installed
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)

        # Next, verify that a renamed package (for a variant applicable
        # to this image), and with dependencies that are only for that
        # other variant will provide the expected info.
        self.pkg("info -r ren_variant_missing")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[3])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: ren_variant_missing
         State: Not installed (Renamed)
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)


        # Next, verify that a renamed package (for all variants),
        # but that is missing a dependency for the current variant
        # will provide the expected info.
        self.pkg("info -r ren_partial_variant")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[4])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: ren_partial_variant
         State: Not installed (Renamed)
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)

        os.environ["LC_ALL"] = "en_US.UTF-8"

    def test_legacy_packages(self):
        """Verify that info returns the expected output for legacy
        packages."""

        # because we compare date strings we must run this in
        # a consistent locale, which we made 'C'
        os.environ['LC_ALL'] = 'C'

        target10 = """
                    open target@1.0
                    close
                """

        # Basic legacy package.
        legacy_basic10 = """
                    open legacy_basic@1.0
                    add set name=pkg.legacy value=true
                    close
                """

        # Legacy package which is also renamed.
        legacy_renamed10 = """
                    open legacy_renamed@1.0
                    add set name=pkg.legacy value=true
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=target@1.0
                    close
                """

        # Another legacy & renamed package with
        # a different order of attributes.
        legacy_renamed20 = """
                    open legacy_renamed@2.0
                    add set name=pkg.renamed value=true
                    add set name=pkg.legacy value=true
                    add depend type=require fmri=target@1.0
                    close
                """

        plist = self.pkgsend_bulk(self.rurl, (target10, legacy_basic10,
            legacy_renamed10, legacy_renamed20))

        # Create an image.
        self.image_create(self.rurl)

        # Verify that a legacy package will provide the expected info.
        self.pkg("info -r legacy_basic")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[1])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: legacy_basic
         State: Not installed (Legacy)
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)

        # Next, verify that a legacy package, which is also renamed,
        # will provide the expected info (rename takes precedence).
        self.pkg("info -r legacy_renamed@1.0")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[2])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: legacy_renamed
         State: Not installed (Renamed)
    Renamed to: target@1.0
     Publisher: test
       Version: 1.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)

        # Next, verify that rename takes precedence no matter the
        # order of attributes.
        self.pkg("info -r legacy_renamed@2.0")
        actual = self.output
        pfmri = fmri.PkgFmri(plist[3])
        pkg_date = pfmri.version.get_timestamp().strftime("%c")
        expected = """\
          Name: legacy_renamed
         State: Not installed (Renamed)
    Renamed to: target@1.0
     Publisher: test
       Version: 2.0
        Branch: None
Packaging Date: {pkg_date}
          Size: 0.00 B
          FMRI: {pkg_fmri}
""".format(pkg_date=pkg_date, pkg_fmri=pfmri.get_fmri(include_build=False))
        self.assertEqualDiff(expected, actual)

        os.environ["LC_ALL"] = "en_US.UTF-8"

    def test_appropriate_license_files(self):
        """Verify that the correct license file is displayed."""

        self.image_create(self.rurl)

        self.pkg("info -r --license bronze")
        self.assertEqual("tmp/copyright1\n", self.output)
        self.pkg("info -r --license bronze@0.5")
        self.assertEqual("tmp/copyright0\n", self.output)

        self.pkg("install --licenses bronze@0.5")
        self.assertTrue("tmp/copyright0" in self.output, "Expected "
            "tmp/copyright0 to be in the output of the install. Output "
            "was:\n{0}".format(self.output))
        self.pkg("info -l --license bronze")
        self.assertEqual("tmp/copyright0\n", self.output)
        self.pkg("info -r --license bronze")
        self.assertEqual("tmp/copyright1\n", self.output)
        self.pkg("info -r --license bronze@1.0")
        self.assertEqual("tmp/copyright1\n", self.output)

        self.pkg("update --licenses bronze@1.0")
        self.assertTrue("tmp/copyright1" in self.output, "Expected "
            "tmp/copyright1 to be in the output of the install. Output "
            "was:\n{0}".format(self.output))
        self.pkg("info -r --license bronze")
        self.assertEqual("tmp/copyright1\n", self.output)
        self.pkg("info -l --license bronze")
        self.assertEqual("tmp/copyright1\n", self.output)
        self.pkg("info -r --license bronze@0.5")
        self.assertEqual("tmp/copyright0\n", self.output)

    def test_info_update_install(self):
        """Test that pkg info will show last update and install time"""

        os.environ["LC_ALL"] = "C"
        self.image_create(self.rurl)
        self.pkg("install bronze@0.5")
        path = os.path.join(self.img_path(),
            "var/pkg/state/installed/catalog.base.C")
        entry = json.load(open(path))["test"]["bronze"][0]["metadata"]
        last_install = catalog.basic_ts_to_datetime(
            entry["last-install"]).strftime("%c")
        self.pkg(("info bronze | grep 'Last Install Time: "
            "{0}'").format(last_install))

        # Now update the version.
        self.pkg("install bronze@1.0")
        entry = json.load(open(path))["test"]["bronze"][0]["metadata"]
        last_install = catalog.basic_ts_to_datetime(
            entry["last-install"]).strftime("%c")
        self.pkg(("info bronze | grep 'Last Install Time: "
            "{0}'").format(last_install))

        # Last update should be existed this time.
        last_update = catalog.basic_ts_to_datetime(
            entry["last-update"]).strftime("%c")
        self.pkg(("info bronze | grep 'Last Update Time: "
            "{0}'").format(last_update))

        # Perfrom a full refresh and ensure the last-update/install
        # have been preserved.
        self.pkg("refresh --full")
        last_install = catalog.basic_ts_to_datetime(
            entry["last-install"]).strftime("%c")
        self.pkg(("info bronze | grep 'Last Install Time: "
            "{0}'").format(last_install))
        last_update = catalog.basic_ts_to_datetime(
            entry["last-update"]).strftime("%c")
        self.pkg(("info bronze | grep 'Last Update Time: "
            "{0}'").format(last_update))

        os.environ["LC_ALL"] = "en_US.UTF-8"


class TestPkgInfoPerTestRepo(pkg5unittest.SingleDepotTestCase):
    """A separate test class is needed because these tests modify packages
    after they've been published and need to avoid corrupting packages for
    other tests."""

    persistent_setup = False

    bronze10 = """
            open bronze@1.0,5.11-0:20110908T004546Z
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license tmp/copyright1 license=copyright
            close
        """

    misc_files = [ "tmp/bronzeA1", "tmp/bronze1", "tmp/bronze2", "tmp/cat",
        "tmp/copyright1", "tmp/sh"]

    def setUp(self):
        pkg5unittest.SingleDepotTestCase.setUp(self)
        self.make_misc_files(self.misc_files)
        self.plist = self.pkgsend_bulk(self.rurl, (self.bronze10))

    def __mangle_license(self, fmri):
        repo = self.dc.get_repo()
        m_path = repo.manifest(fmri)
        with open(m_path, "r") as fh:
            fmri_lines = fh.readlines()
        with open(m_path, "w") as fh:
            a = None
            for l in fmri_lines:
                if "license=copyright" in l:
                    continue
                elif "path=etc/bronze1" in l:
                    a = actions.fromstr(l)
                fh.write(l)
            self.assertTrue(a)
            l = """\
license {hash} license=foo chash={chash} pkg.csize={csize} \
pkg.size={size}""".format(
hash=a.hash,
chash=a.attrs["chash"],
csize=a.attrs["pkg.csize"],
size=a.attrs["pkg.size"]
)
            fh.write(l)
        repo.rebuild()

    def test_info_installed_changed_manifest(self):
        """Test that if an installed manifest has changed in the
        repository the original manifest is used for pkg info and info
        -r."""

        self.image_create(self.rurl)
        self.pkg("install bronze")

        self.pkg("info --license bronze")
        self.assertTrue("tmp/copyright1" in self.output)
        self.__mangle_license(self.plist[0])

        self.pkg("refresh --full")

        self.pkg("info --license bronze")
        self.assertTrue("tmp/bronze1" not in self.output)
        self.assertTrue("tmp/copyright1" in self.output)

        self.pkg("info -r --license bronze")
        self.assertTrue("tmp/bronze1" not in self.output)
        self.assertTrue("tmp/copyright1" in self.output)

    def test_info_uninstalled_changed_manifest(self):
        """Test that if an uninstalled manifest has changed in the
        repository but is cached locally, that the changed manifest is
        reflected in info -r."""

        # First test remote retrieval.
        self.image_create(self.rurl)

        self.pkg("info -r  --license bronze")
        self.assertTrue("tmp/copyright1" in self.output)
        self.__mangle_license(self.plist[0])
        self.pkg("refresh --full")

        self.pkg("info -r  --license bronze")
        self.assertTrue("tmp/bronze1" in self.output)
        self.assertTrue("tmp/copyright1" not in self.output)


if __name__ == "__main__":
    unittest.main()
