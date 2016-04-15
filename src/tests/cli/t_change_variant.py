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

# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import os
import re
import unittest

import pkg.misc as misc
from pkg.client.pkgdefs import *

class TestPkgChangeVariant(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg_i386 = """
        open pkg_i386@1.0,5.11-0
        add set name=variant.arch value=i386
        add dir mode=0755 owner=root group=bin path=/shared
        add dir mode=0755 owner=root group=bin path=/unique
        add file tmp/pkg_i386/shared/pkg_i386_shared mode=0555 owner=root group=bin path=shared/pkg_arch_shared variant.arch=i386
        add file tmp/pkg_i386/unique/pkg_i386 mode=0555 owner=root group=bin path=unique/pkg_i386 variant.arch=i386
        close"""

        pkg_sparc = """
        open pkg_sparc@1.0,5.11-0
        add set name=variant.arch value=sparc
        add dir mode=0755 owner=root group=bin path=/shared
        add dir mode=0755 owner=root group=bin path=/unique
        add file tmp/pkg_sparc/shared/pkg_sparc_shared mode=0555 owner=root group=bin path=shared/pkg_arch_shared variant.arch=sparc
        add file tmp/pkg_sparc/unique/pkg_sparc mode=0555 owner=root group=bin path=unique/pkg_sparc variant.arch=sparc
        close"""

        pkg_shared = """
        open pkg_shared@1.0,5.11-0
        add set name=variant.arch value=sparc value=i386 value=zos
        add set name=variant.opensolaris.zone value=global value=nonglobal
        add dir mode=0755 owner=root group=bin path=/shared
        add dir mode=0755 owner=root group=bin path=/unique
        add file tmp/pkg_shared/shared/common mode=0555 owner=root group=bin path=shared/common
        add file tmp/pkg_shared/shared/pkg_shared_i386 mode=0555 owner=root group=bin path=shared/pkg_shared variant.arch=i386
        add file tmp/pkg_shared/shared/pkg_shared_sparc mode=0555 owner=root group=bin path=shared/pkg_shared variant.arch=sparc
        add file tmp/pkg_shared/shared/global_motd mode=0555 owner=root group=bin path=shared/zone_motd variant.opensolaris.zone=global
        add file tmp/pkg_shared/shared/nonglobal_motd mode=0555 owner=root group=bin path=shared/zone_motd variant.opensolaris.zone=nonglobal
        add file tmp/pkg_shared/unique/global mode=0555 owner=root group=bin path=unique/global variant.opensolaris.zone=global
        add file tmp/pkg_shared/unique/nonglobal mode=0555 owner=root group=bin path=unique/nonglobal variant.opensolaris.zone=nonglobal
        close"""

        pkg_unknown = """
        open unknown@1.0
        add set name=variant.unknown value=bar value=foo
        add file tmp/bar path=usr/bin/bar mode=0755 owner=root group=root variant.unknown=bar
        add file tmp/foo path=usr/bin/foo mode=0755 owner=root group=root variant.unknown=foo
        close
        open unknown@2.0
        add set name=variant.unknown value=bar value=foo
        add file tmp/bar path=usr/bin/foobar mode=0755 owner=root group=root variant.unknown=bar
        add file tmp/foo path=usr/bin/foobar mode=0755 owner=root group=root variant.unknown=foo
        close """

        # this package intentionally has no variant.arch specification.
        pkg_inc = """
        open pkg_inc@1.0,5.11-0
        add depend fmri=pkg_i386@1.0,5.11-0 type=incorporate
        add depend fmri=pkg_sparc@1.0,5.11-0 type=incorporate
        add depend fmri=pkg_shared@1.0,5.11-0 type=incorporate
        close"""

        pkg_cluster = """
        open pkg_cluster@1.0,5.11-0
        add set name=variant.arch value=sparc value=i386 value=zos
        add depend fmri=pkg_i386@1.0,5.11-0 type=require variant.arch=i386
        add depend fmri=pkg_sparc@1.0,5.11-0 type=require variant.arch=sparc
        add depend fmri=pkg_shared@1.0,5.11-0 type=require
        close"""

        pkg_list_all = set([
            "pkg_i386",
            "pkg_sparc",
            "pkg_shared",
            "pkg_inc",
            "pkg_cluster"
        ])

        misc_files = [
            "tmp/pkg_i386/shared/pkg_i386_shared",
            "tmp/pkg_i386/unique/pkg_i386",

            "tmp/pkg_sparc/shared/pkg_sparc_shared",
            "tmp/pkg_sparc/unique/pkg_sparc",

            "tmp/pkg_shared/shared/common",
            "tmp/pkg_shared/shared/pkg_shared_i386",
            "tmp/pkg_shared/shared/pkg_shared_sparc",
            "tmp/pkg_shared/shared/global_motd",
            "tmp/pkg_shared/shared/nonglobal_motd",
            "tmp/pkg_shared/unique/global",
            "tmp/pkg_shared/unique/nonglobal",

            "tmp/bar",
            "tmp/foo"
        ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, (self.pkg_i386, self.pkg_sparc,
                    self.pkg_shared, self.pkg_inc, self.pkg_cluster,
                    self.pkg_unknown))

                # verify pkg search indexes
                self.verify_search = True

                # verify installed images before changing variants
                self.verify_install = False

        def __assert_variant_matches_tsv(self, expected, errout=None,
            exit=0, opts=misc.EmptyI, names=misc.EmptyI, su_wrap=False):
                self.pkg("variant {0} -H -F tsv {1}".format(" ".join(opts),
                    " ".join(names)), exit=exit, su_wrap=su_wrap)
                self.assertEqualDiff(expected, self.output)
                if errout:
                        self.assertTrue(self.errout != "")
                else:
                        self.assertEqualDiff("", self.errout)

        def f_verify(self, path, token=None, negate=False):
                """Verify that the specified path exists and contains
                the specified token.  If negate is true, then make sure
                the path doesn't either doesn't exist, or if it does that
                it doesn't contain the specified token."""

                file_path = os.path.join(self.get_img_path(), path)

                try:
                        f = open(file_path)
                except IOError as e:
                        if e.errno == errno.ENOENT and negate:
                                return
                        raise

                if negate and not token:
                        self.assertTrue(False,
                            "File exists when it shouldn't: {0}".format(path))

                token_re = re.compile(
                    "^"     + token  + "$"   \
                    "|^"    + token + "[/_]" \
                    "|[/_]" + token + "$"    \
                    "|[/_]" + token + "[/_]")

                found = False
                for line in f:
                        if token_re.search(line):
                                found = True
                                break
                f.close()

                if not negate and not found:
                        self.assertTrue(False, "File {0} ({1}) does not contain {2}".format(
                            path, file_path, token))
                if negate and found:
                        self.assertTrue(False, "File {0} ({1}) contains {2}".format(
                            path, file_path, token))

        def p_verify(self, p=None, v_arch=None, v_zone=None, negate=False):
                """Given a specific architecture and zone variant, verify
                the contents of the specified within an image.  If
                negate is true then verify that the package isn't
                installed, and that actions delivered by the package
                don't exist in the target image.

                This routine has hard coded knowledge of the test package
                names, variants, and dependancies.  So any updates made
                to the test package will also likely required updates to
                this function."""

                assert p != None
                assert v_arch == 'i386' or v_arch == 'sparc' or v_arch == 'zos'
                assert v_zone == 'global' or v_zone == 'nonglobal'

                # make sure the package is installed
                if negate:
                        self.pkg("list {0}".format(p), exit=1)
                else:
                        self.pkg("list {0}".format(p))
                        self.pkg("verify {0}".format(p))

                # nothing to verify for packages with no content
                if p == 'pkg_inc':
                        return
                if p == 'pkg_cluster':
                        return

                # verify package contents
                if p == 'pkg_i386':
                        assert negate or v_arch == 'i386'
                        self.f_verify("shared/pkg_arch_shared", "i386", negate)
                        self.f_verify("unique/pkg_i386", "i386", negate)
                        return
                elif p == 'pkg_sparc':
                        assert negate or v_arch == 'sparc'
                        self.f_verify("shared/pkg_arch_shared", "sparc", negate)
                        self.f_verify("unique/pkg_sparc", "sparc", negate)
                        return
                elif p == 'pkg_shared':
                        self.f_verify("shared/common", "common", negate)
                        self.f_verify("shared/pkg_shared", v_arch, negate)
                        self.f_verify("shared/zone_motd", v_zone, negate)
                        if negate:
                                self.f_verify("unique/global", v_zone, True)
                                self.f_verify("unique/nonglobal", v_zone, True)
                        elif v_zone == 'global':
                                self.f_verify("unique/global", v_zone, False)
                                self.f_verify("unique/nonglobal", v_zone, True)
                        elif v_zone == 'nonglobal':
                                self.f_verify("unique/global", v_zone, True)
                                self.f_verify("unique/nonglobal", v_zone, False)
                        return

                # NOTREACHED
                assert False

        def i_verify(self, v_arch=None, v_zone=None, pl=None):
                """Given a specific architecture variant, zone variant,
                and package list, verify that the variant settings are
                correct for the current image, and that the image
                contains the specified packages.  Also verify that the
                image doesn't contain any other unexpected packages.

                This routine has hard coded knowledge of the test package
                names, variants, and dependancies.  So any updates made
                to the test package will also likely required updates to
                this function."""

                assert v_arch == 'i386' or v_arch == 'sparc' or v_arch == 'zos'
                assert v_zone == 'global' or v_zone == 'nonglobal'

                if pl == None:
                        pl = []

                # verify the variant settings
                ic = self.get_img_api_obj().img.cfg
                if "variant.arch" not in ic.variants:
                        self.assertTrue(False,
                            "unable to determine image arch variant")
                if ic.variants["variant.arch"] != v_arch:
                        self.assertTrue(False,
                            "unexpected arch variant: {0} != {1}".format(
                            ic.variants["variant.arch"], v_arch))

                if "variant.opensolaris.zone" not in ic.variants:
                        self.assertTrue(False,
                            "unable to determine image zone variant")
                if ic.variants["variant.opensolaris.zone"] != v_zone:
                        self.assertTrue(False, "unexpected zone variant")


                # adjust the package list based on known dependancies.
                if 'pkg_cluster' in pl and 'pkg_shared' not in pl:
                        pl.append('pkg_shared')
                if v_arch == 'i386':
                        if 'pkg_cluster' in pl and 'pkg_i386' not in pl:
                                pl.append('pkg_i386')
                elif v_arch == 'sparc':
                        if 'pkg_cluster' in pl and 'pkg_sparc' not in pl:
                                pl.append('pkg_sparc')

                #
                # Make sure the number of packages installed matches the
                # number of packages in pl.
                #
                self.pkg(
                    "list -H | wc -l | nawk '{{print $1'}} | grep '^{0:d}$'".format(
                    len(pl)))

                # make sure each specified package is installed
                for p in pl:
                        self.p_verify(p, v_arch, v_zone)

                for p in (self.pkg_list_all - set(pl)):
                        self.p_verify(p, v_arch, v_zone, negate=True)

                # make sure that pkg search doesn't report corrupted indexes
                if self.verify_search:
                        for p in pl:
                                self.pkg("search -l {0}".format(p))

        def cv_test(self, v_arch, v_zone, pl, v_arch2, v_zone2, pl2,
            rv=EXIT_OK):
                """ test if change-variant works """

                assert v_arch == 'i386' or v_arch == 'sparc' or v_arch == 'zos'
                assert v_arch2 == 'i386' or v_arch2 == 'sparc' or \
                    v_arch2 == 'zos'
                assert v_zone == 'global' or v_zone == 'nonglobal'
                assert v_zone2 == 'global' or v_zone2 == 'nonglobal'

                # create an image
                variants = {
                    "variant.arch": v_arch,
                    "variant.opensolaris.zone": v_zone
                }
                self.image_create(self.rurl, variants=variants)

                exp_tsv = """\
variant.arch\t{0}
variant.opensolaris.zone\t{1}
""".format(v_arch, v_zone)
                self.__assert_variant_matches_tsv(exp_tsv)

                # install the specified packages into the image
                ii_args = ""
                for p in pl:
                        ii_args += " {0} ".format(p)
                self.pkg("install {0}".format(ii_args))

                # if we're paranoid, then verify the image we just installed
                if self.verify_install:
                        self.i_verify(v_arch, v_zone, pl)
                # change the specified variant
                cv_args = ""
                cv_args += " -v"
                cv_args += " variant.arch={0}".format(v_arch2)
                cv_args += " variant.opensolaris.zone={0}".format(v_zone2)

                self.pkg("change-variant" + cv_args, exit=rv)
                # verify the updated image
                self.i_verify(v_arch2, v_zone2, pl2)

                exp_tsv = """\
variant.arch\t{0}
variant.opensolaris.zone\t{1}
""".format(v_arch2, v_zone2)
                self.__assert_variant_matches_tsv(exp_tsv)

                self.image_destroy()

        def test_cv_01_none_1(self):
                self.cv_test("i386", "global", ["pkg_cluster"],
                    "i386", "global", ["pkg_cluster"], rv=EXIT_NOP)

        def test_cv_01_none_2(self):
                self.cv_test("i386", "nonglobal", ["pkg_cluster"],
                    "i386", "nonglobal", ["pkg_cluster"], rv=EXIT_NOP)

        def test_cv_01_none_3(self):
                self.cv_test("sparc", "global", ["pkg_cluster"],
                    "sparc", "global", ["pkg_cluster"], rv=EXIT_NOP)

        def test_cv_01_none_4(self):
                self.cv_test("sparc", "nonglobal", ["pkg_cluster"],
                    "sparc", "nonglobal", ["pkg_cluster"], rv=EXIT_NOP)

        def test_cv_02_arch_1(self):
                self.cv_test("i386", "global", ["pkg_shared"],
                    "sparc", "global", ["pkg_shared"])

        def test_cv_02_arch_2(self):
                self.cv_test("sparc", "global", ["pkg_shared"],
                    "i386", "global", ["pkg_shared"])

        def test_cv_03_arch_1(self):
                self.cv_test("i386", "global", ["pkg_inc"],
                    "sparc", "global", ["pkg_inc"])

        def test_cv_03_arch_2(self):
                self.cv_test("sparc", "global", ["pkg_inc"],
                    "i386", "global", ["pkg_inc"])

        def test_cv_04_arch_1(self):
                self.cv_test("i386", "global", ["pkg_i386"],
                    "sparc", "global", [])

        def test_cv_04_arch_2(self):
                self.cv_test("sparc", "global", ["pkg_sparc"],
                    "i386", "global", [])

        def test_cv_05_arch_1(self):
                self.cv_test("i386", "global",
                    ["pkg_i386", "pkg_shared", "pkg_inc"],
                    "sparc", "global", ["pkg_shared", "pkg_inc"])

        def test_cv_05_arch_2(self):
                self.cv_test("sparc", "global",
                    ["pkg_sparc", "pkg_shared", "pkg_inc"],
                    "i386", "global", ["pkg_shared", "pkg_inc"])

        def test_cv_06_arch_1(self):
                self.cv_test("i386", "global", ["pkg_cluster"],
                    "sparc", "global", ["pkg_cluster"])

        def test_cv_06_arch_2(self):
                self.cv_test("sparc", "global", ["pkg_cluster"],
                    "i386", "global", ["pkg_cluster"])

        def test_cv_07_arch_1(self):
                self.cv_test("i386", "global", ["pkg_cluster", "pkg_inc"],
                    "sparc", "global", ["pkg_cluster", "pkg_inc"])

        def test_cv_07_arch_2(self):
                self.cv_test("sparc", "global", ["pkg_cluster", "pkg_inc"],
                    "i386", "global", ["pkg_cluster", "pkg_inc"])

        def test_cv_08_zone_1(self):
                self.cv_test("i386", "global", ["pkg_cluster"],
                    "i386", "nonglobal", ["pkg_cluster"])

        def test_cv_08_zone_2(self):
                self.cv_test("i386", "nonglobal", ["pkg_cluster"],
                    "i386", "global", ["pkg_cluster"])

        def test_cv_09_zone_1(self):
                self.cv_test("sparc", "global", ["pkg_cluster"],
                    "sparc", "nonglobal", ["pkg_cluster"])

        def test_cv_09_zone_2(self):
                self.cv_test("sparc", "nonglobal", ["pkg_cluster"],
                    "sparc", "global", ["pkg_cluster"])

        def test_cv_10_arch_and_zone_1(self):
                self.cv_test("i386", "global", ["pkg_cluster"],
                    "sparc", "nonglobal", ["pkg_cluster"])

        def test_cv_10_arch_and_zone_2(self):
                self.cv_test("sparc", "nonglobal", ["pkg_cluster"],
                    "i386", "global", ["pkg_cluster"])

        def test_cv_11_arch_and_zone_1(self):
                self.cv_test("i386", "nonglobal", ["pkg_cluster"],
                    "sparc", "global", ["pkg_cluster"])

        def test_cv_11_arch_and_zone_2(self):
                self.cv_test("sparc", "global", ["pkg_cluster"],
                    "i386", "nonglobal", ["pkg_cluster"])

        def test_cv_12_unknown(self):
                """Ensure that packages with an unknown variant and
                non-conflicting content can be installed and subsequently
                altered using change-variant."""

                self.image_create(self.rurl)

                # Install package with unknown variant and verify both files are
                # present.
                self.pkg("install -v unknown@1.0")
                for fname in ("bar", "foo"):
                        self.f_verify("usr/bin/{0}".format(fname), fname)

                # Next, verify upgrade to version of package with unknown
                # variant fails if new version delivers conflicting content and
                # variant has not been set.
                self.pkg("update -vvv unknown@2.0", exit=1)

                # Next, set unknown variant explicitly and verify content
                # changes as expected.
                self.pkg("change-variant unknown=foo")

                # Verify bar no longer exists...
                self.f_verify("usr/bin/bar", "bar", negate=True)
                # ...and foo still does.
                self.f_verify("usr/bin/foo", "foo")

                # Next, upgrade to version of package with conflicting content
                # and verify content changes as expected.
                self.pkg("update -vvv unknown@2.0")

                # Verify bar and foo no longer exist...
                for fname in ("bar", "foo"):
                        self.f_verify("usr/bin/{0}".format(fname), fname, negate=True)

                # ...and that foo variant of foobar is now installed.
                self.f_verify("usr/bin/foobar", "foo")

        def test_cv_parsable(self):
                """Test the parsable output of change-variant."""

                self.image_create(self.rurl, variants={
                    "variant.arch": "i386",
                    "variant.opensolaris.zone": "nonglobal"
                })
                self.pkg("change-variant --parsable=0 variant.arch=sparc "
                    "variant.opensolaris.zone=global")
                self.assertEqualParsable(self.output, change_variants=[
                    ["variant.arch", "sparc"],
                    ["variant.opensolaris.zone", "global"]])
                self.pkg("change-variant --parsable=0 variant.arch=i386")
                self.assertEqualParsable(self.output, change_variants=[
                    ["variant.arch", "i386"]])

        def test_invalid_variant(self):
                """Test that invalid input is handled appropriately"""

                self.image_create(self.rurl, variants={
                    "variant.arch": "i386",
                    "variant.opensolaris.zone": "nonglobal"
                })
                self.pkg("install pkg_shared")
                self.pkg("change-variant variant.opensolaris.zone=bogus")


class TestPkgChangeVariantPerTestRepo(pkg5unittest.SingleDepotTestCase):
        """A separate test class is needed because these tests modify packages
        after they've been published and need to avoid corrupting packages for
        other tests."""

        # Only start/stop the depot once (instead of for every test)
        persistent_setup = False
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        pkg_shared = """
        open pkg_shared@1.0,5.11-0
        add set name=variant.arch value=sparc value=i386 value=zos
        add set name=variant.opensolaris.zone value=global value=nonglobal
        add dir mode=0755 owner=root group=bin path=/shared
        add dir mode=0755 owner=root group=bin path=/unique
        add file tmp/pkg_shared/shared/common mode=0555 owner=root group=bin path=shared/common
        add file tmp/pkg_shared/shared/pkg_shared_i386 mode=0555 owner=root group=bin path=shared/pkg_shared variant.arch=i386
        add file tmp/pkg_shared/shared/pkg_shared_sparc mode=0555 owner=root group=bin path=shared/pkg_shared variant.arch=sparc
        add file tmp/pkg_shared/shared/global_motd mode=0555 owner=root group=bin path=shared/zone_motd variant.opensolaris.zone=global
        add file tmp/pkg_shared/shared/nonglobal_motd mode=0555 owner=root group=bin path=shared/zone_motd variant.opensolaris.zone=nonglobal
        add file tmp/pkg_shared/unique/global mode=0555 owner=root group=bin path=unique/global variant.opensolaris.zone=global
        add file tmp/pkg_shared/unique/nonglobal mode=0555 owner=root group=bin path=unique/nonglobal variant.opensolaris.zone=nonglobal

        close"""

        misc_files = [
            "tmp/pkg_shared/shared/common",
            "tmp/pkg_shared/shared/pkg_shared_i386",
            "tmp/pkg_shared/shared/pkg_shared_sparc",
            "tmp/pkg_shared/shared/global_motd",
            "tmp/pkg_shared/shared/nonglobal_motd",
            "tmp/pkg_shared/unique/global",
            "tmp/pkg_shared/unique/nonglobal"
        ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl, self.pkg_shared)

        def test_change_variants_with_changed_manifest(self):
                """Test that if a package is installed but its manifest has
                changed in the repository, change variants doesn't use the
                changes."""

                self.image_create(self.rurl, variants={
                    "variant.arch": "i386",
                    "variant.opensolaris.zone": "nonglobal"
                })
                self.seed_ta_dir("ta3")
                self.pkg("install pkg_shared")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("change-variant variant.arch=sparc", exit=1)

                # Specify location as filesystem path.
                self.pkgsign_simple(self.dc.get_repodir(), "pkg_shared")

                self.pkg("change-variant variant.arch=sparc", exit=1)


if __name__ == "__main__":
        unittest.main()
