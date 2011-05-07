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

import unittest
import os
import re
import shutil
import difflib
import time

import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.fmri as fmri

class TestApiInfo(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        def test_0_local_remote(self):
                """Verify that ImageInterface.info() works as expected
                for both local (installed or cached) and remote packages."""

                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.NoPackagesInstalledException,
                    api_obj.info, [], True, api.PackageInfo.ALL_OPTIONS -
                    (frozenset([api.PackageInfo.LICENSES]) |
                    api.PackageInfo.ACTION_OPTIONS))

                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, [], True, set([-1]))
                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, [], True, set('a'))

                misc_files = ["tmp/copyright1", "tmp/example_file"]
                self.make_misc_files(misc_files)

                pkg1 = """
                    open jade@1.0,5.11-0
                    add set name=description value="Ye Olde Summary"
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video"
                    close
                """

                pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    close
                """

                pkg4 = """
                    open example_pkg@1.0,5.11-0
                    add depend fmri=pkg:/amber@2.0 type=require
                    add dir mode=0755 owner=root group=bin path=/bin
                    add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
                    add hardlink path=/bin/example_path2 target=/bin/example_path
                    add link path=/bin/example_path3 target=/bin/example_path
                    add set description='FOOO bAr O OO OOO'
                    add license tmp/copyright1 license=copyright
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    add set pkg.description="DESCRIPTION 1"
                    close """

                pkg5 = """
                    open example_pkg5@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set pkg.summary='SUMMARY: Example Package 5'
                    add set pkg.description="DESCRIPTION 2"
                    close
                """

                pkg6 = """
                    open example_pkg6@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set description='DESCRIPTION: Example Package 6'
                    add set pkg.summary='SUMMARY: Example Package 6'
                    add set pkg.description="DESCRIPTION 3"
                    close
                """

                pkg7 = """
                    open amber@1.0,5.11-0
                    add set name=description value="Amber's Olde Summary"
                    add set name=pkg.summary value="Amber's Actual Summary"
                    close
                """

                self.pkgsend_bulk(self.rurl, (pkg1, pkg2, pkg4, pkg5, pkg6,
                    pkg7))
                api_obj = self.image_create(self.rurl)

                local = True
                get_license = False

                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    (api.PackageInfo.ACTION_OPTIONS |
                    frozenset([api.PackageInfo.LICENSES]))
                
                ret = api_obj.info(["jade"], local, info_needed)
                self.assert_(not ret[api.ImageInterface.INFO_FOUND])
                self.assert_(len(ret[api.ImageInterface.INFO_MISSING]) == 1)
                
                for pd in api_obj.gen_plan_install(["jade"]):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()

                self.pkg("verify -v")
                
                ret = api_obj.info(["jade", "turquoise", "emerald"],
                    local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(api.PackageInfo.INSTALLED in pis[0].states)
                self.assert_(pis[0].pkg_stem == 'jade')
                self.assert_(len(notfound) == 2)
                self.assert_(len(illegals) == 0)
                self.assert_(len(pis[0].category_info_list) == 1)

                ret = api_obj.info(["j*"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis))

                ret = api_obj.info(["*a*"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis))

                local = False

                ret = api_obj.info(["jade"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(api.PackageInfo.INSTALLED in res.states)
                self.assert_(len(res.category_info_list) == 1)
                self.assertEqual(res.summary, "Ye Olde Summary")
                self.assertEqual(res.description, None)

                ret = api_obj.info(["amber"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(api.PackageInfo.INSTALLED not in res.states)
                self.assert_(len(res.category_info_list) == 0)
                self.assertEqual(res.summary, "Amber's Actual Summary")
                self.assertEqual(res.description, None)

                ret = api_obj.info(["turquoise"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(api.PackageInfo.INSTALLED not in res.states)
                self.assert_(len(res.category_info_list) == 1)
                self.assertEqual(res.summary, "")
                self.assertEqual(res.description, None)

                ret = api_obj.info(["example_pkg"], local,
                    api.PackageInfo.ALL_OPTIONS)
                pis = ret[api.ImageInterface.INFO_FOUND]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(api.PackageInfo.INSTALLED not in res.states)
                self.assert_(len(res.category_info_list) == 1)

                self.assert_(res.pkg_stem is not None)
                self.assert_(res.summary is not None)
                self.assert_(res.publisher is not None)
                self.assert_(res.version is not None)
                self.assert_(res.build_release is not None)
                self.assert_(res.branch is not None)
                self.assert_(res.packaging_date is not None)
                total_size = 0
                for p in misc_files:
                        total_size += \
                            os.stat(os.path.join(self.test_root, p)).st_size
                self.assertEqual(res.size, total_size)
                self.assert_(res.licenses is not None)
                self.assert_(res.links is not None)
                self.assert_(res.hardlinks is not None)
                self.assert_(res.files is not None)
                self.assert_(res.dirs is not None)
                self.assert_(res.dependencies is not None)
                # A test for bug 8868 which ensures the pkg.description field
                # is as exected.
                self.assertEqual(res.description, "DESCRIPTION 1")

                # Verify that summary is pulled from the old "name=description"
                # set action.
                self.assertEqual(res.summary, "FOOO bAr O OO OOO")

                ret = api_obj.info(["emerald"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(notfound) == 1)

                local = True
                get_license = False
                get_action_info = True

                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    frozenset([api.PackageInfo.LICENSES])
                
                ret = api_obj.info(["jade"],
                    local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(len(pis[0].dirs) == 1)
                
                ret = api_obj.info(["jade"], local, set())
                pis = ret[api.ImageInterface.INFO_FOUND]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(res.pkg_stem is None)
                self.assert_(res.summary is None)
                self.assertEqual(res.category_info_list, [])
                self.assertEqual(res.states, tuple())
                self.assert_(res.publisher is None)
                self.assert_(res.version is None)
                self.assert_(res.build_release is None)
                self.assert_(res.branch is None)
                self.assert_(res.packaging_date is None)
                self.assert_(res.size is None)
                self.assert_(res.licenses is None)
                self.assert_(res.links is None)
                self.assert_(res.hardlinks is None)
                self.assert_(res.files is None)
                self.assert_(res.dirs is None)
                self.assertEqual(res.dependencies, ())
                
                local = False

                ret = api_obj.info(["jade"],
                    local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(len(pis[0].dirs) == 1)

                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, ["jade"], local, set([-1]))
                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, ["jade"], local, set('a'))

                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, ["foo"], local, set([-1]))
                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, ["foo"], local, set('a'))

                # Test if the package summary has been correctly set if just
                # a pkg.summary had been set in the package.
                # See bug #4395 and bug #8829 for more details.
                ret = api_obj.info(["example_pkg5"], local,
                    api.PackageInfo.ALL_OPTIONS)
                pis = ret[api.ImageInterface.INFO_FOUND]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(res.summary == "SUMMARY: Example Package 5")
                # A test for bug 8868 which ensures the pkg.description field
                # is as exected.
                self.assertEqual(res.description, "DESCRIPTION 2")

                # Test if the package summary has been correctly set if both
                # a pkg.summary and a description had been set in the package.
                # See bug #4395 and bug #8829 for more details.
                ret = api_obj.info(["example_pkg6"], local,
                    api.PackageInfo.ALL_OPTIONS)
                pis = ret[api.ImageInterface.INFO_FOUND]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(res.summary == "SUMMARY: Example Package 6")
                # A test for bug 8868 which ensures the pkg.description field
                # is as exected.
                self.assertEqual(res.description, "DESCRIPTION 3")

        def test_1_bad_packages(self):
                """Verify that the info operation handles packages with invalid
                metadata."""

                api_obj = self.image_create(self.rurl)

                self.assertRaises(api_errors.NoPackagesInstalledException,
                    api_obj.info, [], True, api.PackageInfo.ALL_OPTIONS -
                    (frozenset([api.PackageInfo.LICENSES]) |
                    api.PackageInfo.ACTION_OPTIONS))

                self.make_misc_files("tmp/baz")

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

                plist = self.pkgsend_bulk(self.rurl, (badfile10, baddir10))
                api_obj.refresh(immediate=True)

                # This should succeed and cause the manifests to be cached.
                info_needed = api.PackageInfo.ALL_OPTIONS
                ret = api_obj.info(plist, False, info_needed)

                # Now attempt to corrupt the client's copy of the manifest by
                # adding malformed actions.
                for p in plist:
                        self.debug("Testing package %s ..." % p)
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
                                    "'%s'." % bad_act)
                                bad_mdata = mdata + "%s\n" % bad_act
                                self.write_img_manifest(pfmri, bad_mdata)

                                # Info shouldn't raise an exception.
                                api_obj.info([pfmri.pkg_name], False,
                                    info_needed)

        def test_2_renamed_packages(self):
                """Verify that info returns the expected list of dependencies
                for renamed packages."""

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

                # Renamed package for opposite image variant, with dependencies
                # only for opposite image variant.
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

                # Create an image and get the api object needed to run tests.
                variants = { "variant.cat": "bobcat" }
                api_obj = self.image_create(self.rurl, variants=variants)

                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    (api.PackageInfo.ACTION_OPTIONS -
                    frozenset([api.PackageInfo.DEPENDENCIES,
                    api.PackageInfo.LICENSES]))

                # First, verify that a renamed package (for all variants), and
                # with the correct dependencies will provide the expected info.
                ret = api_obj.info(["ren_correct"], False, info_needed)
                pi = ret[api.ImageInterface.INFO_FOUND][0]
                self.assert_(api.PackageInfo.RENAMED in pi.states)
                self.assertEqual(pi.dependencies, ["target@1.0"])

                # Next, verify that a renamed package (for a variant not
                # applicable to this image), and with dependencies that
                # are only for that other variant will provide the expected
                # info.
                ret = api_obj.info(["ren_op_variant"], False, info_needed)
                pi = ret[api.ImageInterface.INFO_FOUND][0]
                self.assert_(api.PackageInfo.RENAMED not in pi.states)

                # No dependencies expected; existing don't apply to image.
                self.assertEqual(pi.dependencies, [])

                # Next, verify that a renamed package (for a variant applicable
                # to this image), and with dependencies that are only for that
                # other variant will provide the expected info.
                ret = api_obj.info(["ren_variant_missing"], False, info_needed)
                pi = ret[api.ImageInterface.INFO_FOUND][0]

                # Ensure package isn't seen as renamed for current variant.
                self.assert_(api.PackageInfo.RENAMED in pi.states)

                # No dependencies expected; existing don't apply to image.
                self.assertEqual(pi.dependencies, [])

                # Next, verify that a renamed package (for all variants),
                # but that is missing a dependency for the current variant
                # will provide the expected info.
                ret = api_obj.info(["ren_partial_variant"], False, info_needed)
                pi = ret[api.ImageInterface.INFO_FOUND][0]
                self.assert_(api.PackageInfo.RENAMED in pi.states)
                self.assertEqual(pi.dependencies, [])


if __name__ == "__main__":
        unittest.main()
