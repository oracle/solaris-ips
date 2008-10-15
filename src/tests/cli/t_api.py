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

import os
import time
import unittest
import sys
from stat import *
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress

API_VERSION = 1
PKG_CLIENT_NAME = "pkg"

class TestPkgApi(testutils.SingleDepotTestCase):

        # Only start/stop the depot once (instead of for every test)
        persistent_depot = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo12 = """
            open foo@1.2,5.11-0
            add file /tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """
        
        misc_files = [ "/tmp/libc.so.1", "/tmp/cat", "/tmp/baz" ]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                for p in self.misc_files:
                        f = open(p, "w")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(p)
                        f.close
                        self.debug("wrote %s" % p)

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(p)

        def __try_bad_installs(self, api_obj):

                self.assertRaises(api_errors.PlanExistsException,
                    api_obj.plan_install,["foo"], [])
                
                self.assertRaises(api_errors.PlanExistsException,
                    api_obj.plan_uninstall,["foo"], False)
                self.assertRaises(api_errors.PlanExistsException,
                    api_obj.plan_update_all, sys.argv[0])
                try:
                        api_obj.plan_update_all(sys.argv[0])
                except api_errors.PlanExistsException:
                        pass
                else:
                        assert 0

        def __try_bad_combinations_and_complete(self, api_obj):
                self.__try_bad_installs(api_obj)

                self.assertRaises(api_errors.PrematureExecutionException,
                    api_obj.execute_plan)
                
                api_obj.prepare()
                self.__try_bad_installs(api_obj)

                self.assertRaises(api_errors.AlreadyPreparedException,
                    api_obj.prepare)
                
                api_obj.execute_plan()
                self.__try_bad_installs(api_obj)
                self.assertRaises(api_errors.AlreadyPreparedException,
                    api_obj.prepare)
                self.assertRaises(api_errors.AlreadyExecutedException,
                    api_obj.execute_plan)
                        
        def test_bad_orderings(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)
                
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self.assert_(api_obj.describe() is None)

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)

                api_obj.plan_install(["foo"], [])
                self.__try_bad_combinations_and_complete(api_obj)
                api_obj.reset()

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)

                self.assert_(api_obj.describe() is None)

                self.pkgsend_bulk(durl, self.foo12)
                api_obj.refresh(False)

                api_obj.plan_update_all(sys.argv[0])
                self.__try_bad_combinations_and_complete(api_obj)
                api_obj.reset()

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)
                self.assert_(api_obj.describe() is None)

                api_obj.plan_uninstall(["foo"], False)
                self.__try_bad_combinations_and_complete(api_obj)
                api_obj.reset()

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)
                self.assert_(api_obj.describe() is None)
                        
        def test_reset(self):
                """ Send empty package foo@1.0, install and uninstall """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)
                self.image_create(durl)

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                recursive_removal = False
                filters = []
                
                api_obj.plan_install(["foo"], filters)
                self.assert_(api_obj.describe() is not None)
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                api_obj.plan_install(["foo"], filters)
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                api_obj.plan_install(["foo"], filters)
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)

                self.pkg("list")
                self.pkg("verify")

                self.pkgsend_bulk(durl, self.foo12)
                api_obj.refresh(False)
                
                api_obj.plan_update_all(sys.argv[0])
                self.assert_(api_obj.describe() is not None)
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                api_obj.plan_update_all(sys.argv[0])
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                api_obj.plan_update_all(sys.argv[0])
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)

                self.pkg("list")
                self.pkg("verify")
                
                api_obj.plan_uninstall(["foo"], recursive_removal)
                self.assert_(api_obj.describe() is not None)
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                api_obj.plan_uninstall(["foo"], recursive_removal)
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                api_obj.plan_uninstall(["foo"], recursive_removal)
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)

                self.pkg("verify")
