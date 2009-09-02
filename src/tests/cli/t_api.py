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

import cStringIO
import os
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.progress as progress
import pkg.fmri as fmri
import sys
import tempfile
import time
import unittest

API_VERSION = 20
PKG_CLIENT_NAME = "pkg"

class TestPkgApi(testutils.SingleDepotTestCase):

        # Only start/stop the depot once (instead of for every test)
        persistent_depot = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo12 = """
            open foo@1.2,5.11-0
            add file $test_prefix/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        p5i_bobcat = """{
  "packages": [
    "pkg:/bar@1.0,5.11-0", 
    "baz"
  ], 
  "publishers": [
    {
      "alias": "cat", 
      "name": "bobcat", 
      "packages": [
        "pkg:/foo@1.0,5.11-0"
      ], 
      "repositories": [
        {
          "collection_type": "core", 
          "description": "xkcd.net/325", 
          "legal_uris": [
            "http://xkcd.com/license.html"
          ], 
          "mirrors": [], 
          "name": "source", 
          "origins": [
            "http://localhost:12001/"
          ], 
          "refresh_seconds": 43200, 
          "registration_uri": "", 
          "related_uris": []
        }
      ]
    }
  ], 
  "version": 1
}
"""


        misc_files = [ "libc.so.1" ]

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)

                self.foo12 = self.foo12.replace("$test_prefix",
                    self.get_test_prefix())

                for p in self.misc_files:
                        fpath = os.path.join(self.get_test_prefix(), p)
                        f = open(fpath, "wb")
                        # write the name of the file into the file, so that
                        # all files have differing contents
                        f.write(fpath)
                        f.close()
                        self.debug("wrote %s" % fpath)

        def tearDown(self):
                testutils.SingleDepotTestCase.tearDown(self)
                for p in self.misc_files:
                        os.remove(os.path.join(self.get_test_prefix(), p))

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
                api_obj.refresh(immediate=True)

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
                api_obj.refresh(immediate=True)

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

        def test_properties(self):
                """Verify that properties of the ImageInterface api object are
                accessible and return expected values."""

                durl = self.dc.get_depot_url()
                self.image_create(durl)

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self.assertEqual(api_obj.root, self.img_path)

        def test_publisher_apis(self):
                """Verify that the publisher api methods work as expected.

                Note that not all methods are tested here as this would be
                redundant since other tests for the client will use those
                methods indirectly."""

                durl = self.dc.get_depot_url()
                plist = self.pkgsend_bulk(durl, self.foo10 + self.bar10)
                self.image_create(durl, prefix="bobcat")

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                # Verify that existence tests succeed.
                self.assertTrue(api_obj.has_publisher("bobcat"))

                # Verify preferred publisher prefix is returned correctly.
                self.assertEqual(api_obj.get_preferred_publisher(), "bobcat")

                # Verify that get_publisher returned the correct publisher object.
                pub = api_obj.get_publisher(prefix="bobcat")
                self.assertEqual(pub.prefix, "bobcat")

                # Verify that not specifying matching criteria for get_publisher
                # raises a UnknownPublisher exception.
                self.assertRaises(api_errors.UnknownPublisher,
                    api_obj.get_publisher, "zuul")
                self.assertRaises(api_errors.UnknownPublisher,
                    api_obj.get_publisher)

                # Verify that publisher objects returned from get_publishers
                # match those returned by get_publisher.
                pubs = api_obj.get_publishers()
                self.assertEqual(pub.prefix, pubs[0].prefix)
                self.assertEqual(id(pub), id(pubs[0]))

                # Verify that duplicate actually creates duplicates.
                cpub = api_obj.get_publisher(prefix="bobcat", duplicate=True)
                self.assertNotEqual(id(pub), id(cpub))

                # Now modify publisher information and update.
                cpub.alias = "cat"
                repo = cpub.selected_repository
                repo.name = "source"
                repo.description = "xkcd.net/325"
                repo.legal_uris = ["http://xkcd.com/license.html"]
                repo.refresh_seconds = 43200
                repo.registered = False
                api_obj.update_publisher(cpub)

                # Verify that the update happened.
                pub = api_obj.get_publisher(prefix="bobcat")
                self.assertEqual(pub.alias, "cat")
                repo = pub.selected_repository
                self.assertEqual(repo.name, "source")
                self.assertEqual(repo.description, "xkcd.net/325")
                self.assertEqual(repo.legal_uris[0],
                    "http://xkcd.com/license.html")
                self.assertEqual(repo.refresh_seconds, 43200)
                self.assertEqual(repo.registered, False)

                # Verify that duplicates match their original.
                cpub = api_obj.get_publisher(alias=pub.alias, duplicate=True)
                for p in ("alias", "prefix", "meta_root"):
                        self.assertEqual(getattr(pub, p), getattr(cpub, p))

                for p in ("collection_type", "description", "legal_uris",
                    "mirrors", "name", "origins", "refresh_seconds",
                    "registered", "registration_uri", "related_uris",
                    "sort_policy"):
                        srepo = pub.selected_repository
                        crepo = cpub.selected_repository
                        self.assertEqual(getattr(srepo, p), getattr(crepo, p))
                cpub = None

                cpubs = api_obj.get_publishers(duplicate=True)
                self.assertNotEqual(id(pub), id(cpubs[0]))
                cpubs = None

                # Verify that publisher_last_update_time returns a value.
                self.assertTrue(
                    api_obj.get_publisher_last_update_time("bobcat"))

                # Verify that p5i export and parse works as expected.

                # Ensure that PackageInfo, PkgFmri, and strings are all
                # supported properly.

                # Strip timestamp information so that comparison with
                # pre-generated test data will succeed.
                ffoo = fmri.PkgFmri(plist[0])
                sfoo = str(ffoo).replace(":%s" % ffoo.version.timestr, "")
                ffoo = fmri.PkgFmri(sfoo)

                fbar = fmri.PkgFmri(plist[1])
                sbar = str(fbar).replace(":%s" % fbar.version.timestr, "")
                fbar = fmri.PkgFmri(sbar)

                # Build a simple list of packages.
                pnames = {
                    "bobcat": (api.PackageInfo(ffoo),),
                    "": [fbar, "baz"],
                }

                # Dump the p5i data.
                fobj = cStringIO.StringIO()
                api_obj.write_p5i(fobj, pkg_names=pnames, pubs=[pub])

                # Verify that output matches expected output.
                fobj.seek(0)
                output = fobj.read()
                self.assertEqual(output, self.p5i_bobcat)

                def validate_results(results):
                        # First result should be 'bobcat' publisher and its
                        # pkg_names.
                        pub, pkg_names = results[0]

                        self.assertEqual(pub.prefix, "bobcat")
                        self.assertEqual(pub.alias, "cat")
                        repo = pub.selected_repository
                        self.assertEqual(repo.name, "source")
                        self.assertEqual(repo.description, "xkcd.net/325")
                        self.assertEqual(repo.legal_uris[0],
                            "http://xkcd.com/license.html")
                        self.assertEqual(repo.refresh_seconds, 43200)
                        self.assertEqual(pkg_names, [sfoo])

                        # Last result should be no publisher and a list of
                        # pkg_names.
                        pub, pkg_names = results[1]
                        self.assertEqual(pub, None)
                        self.assertEqual(pkg_names, [sbar, "baz"])

                # Verify that parse returns the expected object and information
                # when provided a fileobj.
                fobj.seek(0)
                validate_results(api_obj.parse_p5i(fileobj=fobj))

                # Verify that an add of the parsed object works (the name has to
                # be changed to prevent a duplicate error here).
                fobj.seek(0)
                results = api_obj.parse_p5i(fileobj=fobj)
                pub, pkg_names = results[0]

                pub.prefix = "p5icat"
                pub.alias = "copycat"
                api_obj.add_publisher(pub, refresh_allowed=False)

                # Now verify that we can retrieve the added publisher.
                api_obj.get_publisher(prefix=pub.prefix)
                cpub = api_obj.get_publisher(alias=pub.alias, duplicate=True)

                # Now update the publisher and set it to disabled, to verify
                # that api functions still work as expected.
                cpub.disabled = True
                api_obj.update_publisher(cpub)

                cpub = api_obj.get_publisher(alias=cpub.alias, duplicate=True)
                self.assertTrue(cpub.disabled)

                self.assertTrue(api_obj.has_publisher(prefix=cpub.prefix))

                # Now attempt to update the disabled publisher.
                cpub = api_obj.get_publisher(alias=cpub.alias, duplicate=True)
                cpub.alias = "copycopycat"
                api_obj.update_publisher(cpub)
                cpub = None

                # Verify that parse returns the expected object and information
                # when provided a file path.
                fobj.seek(0)
                (fd1, path1) = tempfile.mkstemp(dir=self.get_test_prefix())
                os.write(fd1, fobj.read())
                validate_results(api_obj.parse_p5i(location=path1))

                # Verify that parse returns the expected object and information
                # when provided a file URI.
                validate_results(api_obj.parse_p5i(location="file://" + path1))
                fobj.close()
                fobj = None

                # Verify that appropriate exceptions are raised for p5i
                # information that can't be retrieved (doesn't exist).
                nefpath = os.path.join(self.get_test_prefix(), "non-existent")
                self.assertRaises(api_errors.RetrievalError,
                    api_obj.parse_p5i, location="file://%s" % nefpath)

                self.assertRaises(api_errors.RetrievalError,
                    api_obj.parse_p5i, location=nefpath)

                # Verify that appropriate exceptions are raised for invalid
                # p5i information.
                lcpath = os.path.join(self.get_test_prefix(), "libc.so.1")
                self.assertRaises(api_errors.InvalidP5IFile, api_obj.parse_p5i,
                    location="file://%s" % lcpath)

                self.assertRaises(api_errors.InvalidP5IFile, api_obj.parse_p5i,
                    location=lcpath)
