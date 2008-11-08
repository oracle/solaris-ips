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

import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress

API_VERSION = 6
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
                    api_obj.info, [], True, False)
                
                pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video
                    close
                """

                pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    close
                """

                durl = self.dc.get_depot_url()

                self.pkgsend_bulk(durl, pkg1)
                self.pkgsend_bulk(durl, pkg2)

                self.image_create(durl)

                filters = []
                
                api_obj.plan_install(["jade"], filters)
                api_obj.prepare()
                api_obj.execute_plan()

                self.pkg("verify -v")

                local = True
                get_license = False
                
                ret = api_obj.info(["jade", "turquoise", "emerald"],
                    local, get_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(pis[0].state == api.PackageInfo.INSTALLED)
                self.assert_(pis[0].pkg_stem == 'jade')
                self.assert_(len(notfound) == 2)
                self.assert_(len(illegals) == 0)
                self.assert_(len(pis[0].category_info_list) == 1)

                ret = api_obj.info(["j*"], local, get_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis))

                ret = api_obj.info(["*a*"], local, get_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis))

                local = False

                ret = api_obj.info(["jade"], local, get_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(pis[0].state == api.PackageInfo.INSTALLED)
                self.assert_(len(pis[0].category_info_list) == 1)

                ret = api_obj.info(["turquoise"], local, get_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(pis[0].state == api.PackageInfo.NOT_INSTALLED)
                self.assert_(len(pis[0].category_info_list) == 1)

                ret = api_obj.info(["emerald"], local, get_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(notfound) == 1)

                local = True
                get_license = False
                get_action_info = True
                
                ret = api_obj.info(["jade"],
                    local, get_license, get_action_info)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(len(pis[0].dirs) == 1)

                local = False

                ret = api_obj.info(["jade"],
                    local, get_license, get_action_info)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                self.assert_(len(pis) == 1)
                self.assert_(len(pis[0].dirs) == 1)

                
if __name__ == "__main__":
        unittest.main()

