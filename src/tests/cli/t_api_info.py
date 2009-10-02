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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import unittest
import os
import re
import shutil
import difflib
import time

import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress

API_VERSION = 21
PKG_CLIENT_NAME = "pkg"

class TestApiInfo(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_info_local_remote(self):
                self.image_create(self.dc.get_depot_url())
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self.assertRaises(api_errors.NoPackagesInstalledException,
                    api_obj.info, [], True, api.PackageInfo.ALL_OPTIONS -
                    (frozenset([api.PackageInfo.LICENSES]) |
                    api.PackageInfo.ACTION_OPTIONS))

                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, [], True, set([-1]))
                self.assertRaises(api_errors.UnrecognizedOptionsToInfo,
                    api_obj.info, [], True, set('a'))

                misc_files = ["/tmp/copyright1", "/tmp/example_file"]
                for p in misc_files:
                        f = open(p, "w")
                        f.write(p)
                        f.close()

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
                    close
                """

                pkg3 = """
                    open foo@1.0,5.11-0
                    close
                """

                pkg4 = """
                    open example_pkg@1.0,5.11-0
                    add depend fmri=pkg:/amber@2.0 type=require
                    add dir mode=0755 owner=root group=bin path=/bin
                    add file /tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
                    add hardlink path=/bin/example_path2 target=/bin/example_path
                    add link path=/bin/example_path3 target=/bin/example_path
                    add set description='FOOO bAr O OO OOO'
                    add license /tmp/copyright1 license=copyright
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

                durl = self.dc.get_depot_url()

                self.pkgsend_bulk(durl, pkg1)
                self.pkgsend_bulk(durl, pkg2)
                self.pkgsend_bulk(durl, pkg4)
                self.pkgsend_bulk(durl, pkg5)
                self.pkgsend_bulk(durl, pkg6)

                self.image_create(durl)

                filters = []

                local = True
                get_license = False

                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    (api.PackageInfo.ACTION_OPTIONS |
                    frozenset([api.PackageInfo.LICENSES]))
                
                ret = api_obj.info(["jade"], local, info_needed)
                self.assert_(not ret[api.ImageInterface.INFO_FOUND])
                self.assert_(len(ret[api.ImageInterface.INFO_MISSING]) == 1)
                
                api_obj.plan_install(["jade"], filters)
                api_obj.prepare()
                api_obj.execute_plan()

                self.pkg("verify -v")
                
                ret = api_obj.info(["jade", "turquoise", "emerald"],
                    local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(pis[0].state == api.PackageInfo.INSTALLED)
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
                self.assert_(pis[0].state == api.PackageInfo.INSTALLED)
                self.assert_(len(pis[0].category_info_list) == 1)

                ret = api_obj.info(["turquoise"], local, info_needed)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(pis[0].state == api.PackageInfo.NOT_INSTALLED)
                self.assert_(len(pis[0].category_info_list) == 1)

                ret = api_obj.info(["example_pkg"], local,
                    api.PackageInfo.ALL_OPTIONS)
                pis = ret[api.ImageInterface.INFO_FOUND]
                self.assert_(len(pis) == 1)
                res = pis[0]
                self.assert_(res.state == api.PackageInfo.NOT_INSTALLED)
                self.assert_(len(res.category_info_list) == 1)

                self.assert_(res.pkg_stem is not None)
                self.assert_(res.summary is not None)
                self.assert_(res.publisher is not None)
                self.assert_(res.preferred_publisher is not None)
                self.assert_(res.version is not None)
                self.assert_(res.build_release is not None)
                self.assert_(res.branch is not None)
                self.assert_(res.packaging_date is not None)
                total_size = 0
                for p in misc_files:
                        total_size += len(p)
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
                self.assert_(res.category_info_list == [])
                self.assert_(res.state is None)
                self.assert_(res.publisher is None)
                self.assert_(res.preferred_publisher is None)
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
                self.assert_(res.dependencies is None)
                
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


if __name__ == "__main__":
        unittest.main()
