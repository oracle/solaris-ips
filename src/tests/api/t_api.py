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

import cStringIO
import os
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.facet as facet
import pkg.fmri as fmri
import sys
import tempfile
import time
import unittest

class TestPkgApi(pkg5unittest.SingleDepotTestCase):
        # restart the depot for every test
        persistent_setup = False

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo12 = """
            open foo@1.2,5.11-0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        foo11v = """
            open foo@1.1,5.11-0
            add set name=variant.arch value=i386 value=sparc
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1 variant.arch=i386
            close """

        foo12v = """
            open foo@1.2,5.11-0
            add set name=variant.arch value=i386 value=sparc
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1 variant.arch=i386
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        baz10 = """
            open baz@1.0,5.11-0
            add license copyright.baz license=copyright.baz
            close """

        quux10 = """
            open quux@1.0,5.11-0
            add depend type=require fmri=foo@1.0
            close """

        # First iteration has just a copyright.
        licensed10 = """
            open licensed@1.0,5.11-0
            add depend type=require fmri=baz@1.0
            add license copyright.licensed license=copyright.licensed
            close """

        # Second iteration has copyright that must-display and a new license
        # that doesn't require acceptance.
        licensed12 = """
            open licensed@1.2,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed
            close """

        # Third iteration now requires acceptance of license.
        licensed13 = """
            open licensed@1.3,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed must-accept=True
            close """

        # Fourth iteration is completely unchanged, so shouldn't require
        # acceptance.
        licensed14 = """
            open licensed@1.4,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed must-accept=True
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
            "%REAL_ORIGIN%/"
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


        misc_files = ["copyright.baz", "copyright.licensed", "libc.so.1",
            "license.licensed", "license.licensed.addendum"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, publisher="bobcat")
                self.make_misc_files(self.misc_files)
                self.p5i_bobcat = self.p5i_bobcat.replace("%REAL_ORIGIN%",
                    self.rurl)

        def __try_bad_installs(self, api_obj):

                self.assertRaises(api_errors.PlanExistsException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_install(*args, **kwargs)),
                    ["foo"])
                self.assertRaises(api_errors.PlanExistsException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_uninstall(*args, **kwargs)),
                    ["foo"])
                self.assertRaises(api_errors.PlanExistsException,
                    lambda *args, **kwargs: list(
                        api_obj.gen_plan_update(*args, **kwargs)))
                try:
                        for pd in api_obj.gen_plan_update():
                                continue
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

                self.pkgsend_bulk(self.rurl, self.foo10)
                api_obj = self.image_create(self.rurl, prefix="bobcat")

                self.assert_(api_obj.describe() is None)

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)

                for pd in api_obj.gen_plan_install(["foo"]):
                        continue
                self.__try_bad_combinations_and_complete(api_obj)
                api_obj.reset()

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)

                self.assert_(api_obj.describe() is None)

                self.pkgsend_bulk(self.rurl, self.foo12)
                api_obj.refresh(immediate=True)

                for pd in api_obj.gen_plan_update():
                        continue
                self.__try_bad_combinations_and_complete(api_obj)
                api_obj.reset()

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)
                self.assert_(api_obj.describe() is None)

                for pd in api_obj.gen_plan_uninstall(["foo"]):
                        continue
                self.__try_bad_combinations_and_complete(api_obj)
                api_obj.reset()

                self.assertRaises(api_errors.PlanMissingException,
                    api_obj.prepare)
                self.assert_(api_obj.describe() is None)

        def test_reset(self):
                """ Send empty package foo@1.0, install and uninstall """

                self.pkgsend_bulk(self.rurl, self.foo10)
                api_obj = self.image_create(self.rurl, prefix="bobcat")

                facets = facet.Facets({ "facet.devel": True })
                for pd in api_obj.gen_plan_change_varcets(facets=facets):
                        continue
                self._api_finish(api_obj)

                for pd in api_obj.gen_plan_install(["foo"]):
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                for pd in api_obj.gen_plan_install(["foo"]):
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                for pd in api_obj.gen_plan_install(["foo"]):
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)

                self.pkg("list")
                self.pkg("verify")

                self.pkgsend_bulk(self.rurl, self.foo12)
                api_obj.refresh(immediate=True)

                for pd in api_obj.gen_plan_update():
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                for pd in api_obj.gen_plan_update():
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                for pd in api_obj.gen_plan_update():
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)

                self.pkg("list")
                self.pkg("verify")

                for pd in api_obj.gen_plan_uninstall(["foo"]):
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                for pd in api_obj.gen_plan_uninstall(["foo"]):
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)
                for pd in api_obj.gen_plan_uninstall(["foo"]):
                        continue
                self.assert_(api_obj.describe() is not None)
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()
                self.assert_(api_obj.describe() is None)

                self.pkg("verify")

        def test_refresh_transition(self):
                """Verify that refresh works for a v0 catalog source and that
                if the client transitions from v0 to v1 or back that the correct
                state information is recorded in the image catalog."""

                # This test requires an actual depot due to v0 operation usage.
                # First create the image and get v1 catalog.
                self.dc.start()
                self.pkgsend_bulk(self.durl, (self.foo10, self.quux10))
                try:
                        api_obj = self.image_create(self.durl, prefix="bobcat")
                except api_errors.CatalogRefreshException, e:
                        self.debug("\n".join(str(x[-1]) for x in e.failed))
                        raise

                self.pkg("publisher")
                img = api_obj.img
                kcat = img.get_catalog(img.IMG_CATALOG_KNOWN)
                entry = [e for f, e in kcat.entries()][0]
                states = entry["metadata"]["states"]
                self.assert_(img.PKG_STATE_V1 in states)
                self.assert_(img.PKG_STATE_V0 not in states)

                # Next, disable v1 catalog for the depot and force a client
                # refresh.  Only v0 state should be present.
                self.dc.stop()
                self.dc.set_disable_ops(["catalog/1"])
                self.dc.start()

                # Since the depot state changed while the API object was
                # still active, it needs to be reset to clear the internal
                # transport state cache.
                api_obj.reset()

                api_obj.refresh(immediate=True)
                api_obj.reset()
                img = api_obj.img

                kcat = img.get_catalog(img.IMG_CATALOG_KNOWN)
                entry = [e for f, e in kcat.entries()][0]
                states = entry["metadata"]["states"]
                self.assert_(img.PKG_STATE_V1 not in states)
                self.assert_(img.PKG_STATE_V0 in states)

                # Verify that there is no dependency information present
                # in the known or installed catalog.
                icat = img.get_catalog(img.IMG_CATALOG_INSTALLED)
                for cat in kcat, icat:
                        dpart = cat.get_part("catalog.dependency.C")
                        dep_acts = [
                            acts
                            for t, entry in dpart.tuple_entries()
                            for acts in entry.get("actions", [])
                        ]
                        self.assertEqual(dep_acts, [])

                # Now install a package, and verify that the entries in the
                # known catalog for installed packages exist in the installed
                # catalog and are identical.
                api_obj = self.get_img_api_obj()
                img = api_obj.img

                # Get image catalogs.
                kcat = img.get_catalog(img.IMG_CATALOG_KNOWN)
                icat = img.get_catalog(img.IMG_CATALOG_INSTALLED)

                # Verify quux package is only in known catalog.
                self.assertTrue("quux" in kcat.names())
                self.assertTrue("foo" in kcat.names())
                self.assertTrue("quux" not in icat.names())
                self.assertTrue("foo" not in icat.names())

                # Install the packages.
                for pd in api_obj.gen_plan_install(["quux@1.0"]):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

                # Get image catalogs.
                kcat = img.get_catalog(img.IMG_CATALOG_KNOWN)
                icat = img.get_catalog(img.IMG_CATALOG_INSTALLED)

                # Verify quux package is in both catalogs.
                self.assertTrue("quux" in kcat.names())
                self.assertTrue("foo" in kcat.names())
                self.assertTrue("quux" in icat.names())
                self.assertTrue("foo" in icat.names())

                # Verify state info.
                for cat in kcat, icat:
                        entry = [e for f, e in cat.entries()][0]
                        states = entry["metadata"]["states"]
                        self.assert_(img.PKG_STATE_INSTALLED in states)
                        self.assert_(img.PKG_STATE_V0 in states)

                # Finally, transition back to v1 catalog.  This requires
                # creating a new api object since transport will think that
                # v1 catalogs are still unsupported.
                self.dc.unset_disable_ops()
                self.dc.stop()
                self.dc.start()

                api_obj = self.get_img_api_obj()
                api_obj.refresh(immediate=True)
                img = api_obj.img

                # Get image catalogs.
                kcat = img.get_catalog(img.IMG_CATALOG_KNOWN)
                icat = img.get_catalog(img.IMG_CATALOG_INSTALLED)

                # Verify quux package is in both catalogs.
                self.assertTrue("quux" in kcat.names())
                self.assertTrue("foo" in kcat.names())
                self.assertTrue("quux" in icat.names())
                self.assertTrue("foo" in icat.names())

                # Verify state info.
                for f, entry in kcat.entries():
                        states = entry["metadata"]["states"]
                        self.assert_(img.PKG_STATE_V1 in states)
                        self.assert_(img.PKG_STATE_V0 not in states)

                # Verify that there is dependency information present
                # in the known and installed catalog.
                for cat in kcat, icat:
                        dpart = cat.get_part("catalog.dependency.C")
                        entries = [(t, entry) for t, entry in dpart.tuple_entries()]
                        dep_acts = [
                            acts
                            for t, entry in dpart.tuple_entries()
                            for acts in entry.get("actions", [])
                            if t[1] == "quux"
                        ]
                        self.assertNotEqual(dep_acts, [])

                # Verify that every installed package is in known and has
                # identical entries and that every installed package in
                # the installed catalog is in the known catalog and has
                # entries.
                for src, dest in ((kcat, icat), (icat, kcat)):
                        src_base = src.get_part("catalog.base.C",
                            must_exist=True)
                        self.assertNotEqual(src_base, None)

                        for f, bentry in src_base.entries():
                                states = bentry["metadata"]["states"]
                                if img.PKG_STATE_INSTALLED not in states:
                                        continue

                                for name in src.parts:
                                        spart = src.get_part(name,
                                            must_exist=True)
                                        self.assertNotEqual(spart, None)

                                        dpart = dest.get_part(name,
                                            must_exist=True)
                                        self.assertNotEqual(dpart, None)

                                        sentry = spart.get_entry(pfmri=f)
                                        dentry = dpart.get_entry(pfmri=f)
                                        self.assertEqual(sentry, dentry)

        def test_properties(self):
                """Verify that properties of the ImageInterface api object are
                accessible and return expected values."""

                api_obj = self.image_create(self.rurl, prefix="bobcat")
                self.assertEqual(api_obj.root, self.img_path())

        def test_snapdir(self):
                """Verify that image create ignores .zfs snapdir."""

                # snapdir path
                path = self.img_path()
                snapdir = os.path.join(path, ".zfs")

                # a .zfs directory is allowed
                self.image_destroy()
                os.mkdir(self.img_path())
                os.mkdir(snapdir)
                api_obj = self.image_create(destroy=False)

                # a .zfs file is not allowed
                self.image_destroy()
                os.mkdir(self.img_path())
                open(snapdir, 'w').close()
                self.assertRaises(api_errors.CreatingImageInNonEmptyDir,
                    self.image_create, destroy=False)

        def test_publisher_apis(self):
                """Verify that the publisher api methods work as expected.

                Note that not all methods are tested here as this would be
                redundant since other tests for the client will use those
                methods indirectly."""

                plist = self.pkgsend_bulk(self.rurl, (self.foo10, self.bar10))
                api_obj = self.image_create(self.rurl, prefix="bobcat")

                # Verify that existence tests succeed.
                self.assertTrue(api_obj.has_publisher("bobcat"))

                # Verify preferred publisher prefix is returned correctly.
                self.assertEqual(api_obj.get_highest_ranked_publisher().prefix,
                    "bobcat")

                # Verify that get_publisher returned the correct publisher
                # object.
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
                repo = cpub.repository
                repo.name = "source"
                repo.description = "xkcd.net/325"
                repo.legal_uris = ["http://xkcd.com/license.html"]
                repo.refresh_seconds = 43200
                repo.registered = False
                api_obj.update_publisher(cpub)

                # Verify that the update happened.
                pub = api_obj.get_publisher(prefix="bobcat")
                self.assertEqual(pub.alias, "cat")
                repo = pub.repository
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
                        srepo = pub.repository
                        crepo = cpub.repository
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
                sfoo = ffoo.get_fmri(anarchy=True)

                fbar = fmri.PkgFmri(plist[1])
                sbar = str(fbar).replace(":%s" % fbar.version.timestr, "")
                fbar = fmri.PkgFmri(sbar)
                sbar = fbar.get_fmri(anarchy=True)

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
                self.assertEqualDiff(output, self.p5i_bobcat)

                def validate_results(results):
                        # First result should be 'bobcat' publisher and its
                        # pkg_names.
                        pub, pkg_names = results[0]

                        self.assertEqual(pub.prefix, "bobcat")
                        self.assertEqual(pub.alias, "cat")
                        repo = pub.repository
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

                # Now verify that the DuplicatePublisher exception is raised
                # as expected when adding or updating publishers if the prefix
                # is the same as another publisher's prefix or alias.  This is
                # because alias and prefix are intended to be interchangeable
                # (although the API allows clients to make a distinction
                # internally).
                dpub = api_obj.get_publisher(alias=pub.alias, duplicate=True)
                dpub.alias = None

                # Should fail since a publisher exists with this prefix.
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.add_publisher, dpub, refresh_allowed=False)
                dpub.prefix = "bobcat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.update_publisher, dpub, refresh_allowed=False)

                # Should fail since a publisher exists with an alias the same
                # as this prefix.
                dpub.prefix = "copycat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.add_publisher, dpub, refresh_allowed=False)
                dpub.prefix = "cat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.update_publisher, dpub, refresh_allowed=False)

                # Should fail since a publisher exists with an alias the same
                # as this alias.
                dpub.prefix = "uniquecat"
                dpub.alias = "copycat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.add_publisher, dpub, refresh_allowed=False)
                dpub.alias = "cat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.update_publisher, dpub, refresh_allowed=False)

                # Should fail since a publisher exists with a prefix the same
                # as this alias.
                dpub.prefix = "uniquecat"
                dpub.alias = "p5icat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.add_publisher, dpub, refresh_allowed=False)
                dpub.alias = "bobcat"
                self.assertRaises(api_errors.DuplicatePublisher,
                        api_obj.update_publisher, dpub, refresh_allowed=False)

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
                (fd1, path1) = tempfile.mkstemp(dir=self.test_root)
                os.write(fd1, fobj.read())
                validate_results(api_obj.parse_p5i(location=path1))

                # Verify that parse returns the expected object and information
                # when provided a file URI.
                validate_results(api_obj.parse_p5i(location="file://" + path1))
                fobj.close()
                fobj = None

                # Verify that appropriate exceptions are raised for p5i
                # information that can't be retrieved (doesn't exist).
                nefpath = os.path.join(self.test_root, "non-existent")
                self.assertRaises(api_errors.RetrievalError,
                    api_obj.parse_p5i, location="file://%s" % nefpath)

                self.assertRaises(api_errors.RetrievalError,
                    api_obj.parse_p5i, location=nefpath)

                # Verify that appropriate exceptions are raised for invalid
                # p5i information.
                lcpath = os.path.join(self.test_root, "libc.so.1")
                self.assertRaises(api_errors.InvalidP5IFile, api_obj.parse_p5i,
                    location="file://%s" % lcpath)

                self.assertRaises(api_errors.InvalidP5IFile, api_obj.parse_p5i,
                    location=lcpath)

                # Now install a package and remove all publishers and verify a
                # publisher obj is returned by get_highest_ranked_publisher().
                self._api_install(api_obj, ["foo"])
                api_obj.remove_publisher("bobcat")
                api_obj.remove_publisher("p5icat")
                self.assert_(api_obj.get_highest_ranked_publisher().prefix,
                    "bobcat")

        def test_deprecated(self):
                """Test deprecated api interfaces."""

                self.pkgsend_bulk(self.rurl, self.foo10)
                api_obj = self.image_create(self.rurl, prefix="bobcat",
                    variants={"variant.arch": "i386"})
                api_obj.reset()

                # verify the old install interface
                stuff_to_do = api_obj.plan_install(["foo"], noexecute=False)
                self.assertTrue(stuff_to_do)
                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                api_obj.reset()

                self.pkgsend_bulk(self.rurl, self.foo11v)
                self.pkgsend_bulk(self.rurl, self.foo12v)
                api_obj.refresh(immediate=True)

                # verify the old update interface
                stuff_to_do = api_obj.plan_update(
                    ["foo@1.1,5.11-0"], noexecute=False)
                self.assertTrue(stuff_to_do)
                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                api_obj.reset()

                # verify the old update interface
                stuff_to_do, s_image = api_obj.plan_update_all(noexecute=False)
                self.assertTrue(stuff_to_do)
                self.assertFalse(s_image)
                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                api_obj.reset()

                # remove a file from the image
                os.remove(os.path.join(self.img_path(), "lib/libc.so.1"))

                # verify the old revert interface
                stuff_to_do = api_obj.plan_revert(["/lib/libc.so.1"],
                    noexecute=False)
                self.assertTrue(stuff_to_do)
                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                api_obj.reset()

                # verify the old change varcets interface
                stuff_to_do = api_obj.plan_change_varcets(
                    variants={"variant.arch": "sparc"}, noexecute=False)
                self.assertTrue(stuff_to_do)
                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                api_obj.reset()

                # verify the old change uninstall interface
                stuff_to_do = api_obj.plan_uninstall(["foo"], noexecute=False)
                self.assertTrue(stuff_to_do)
                api_obj.prepare()
                try:
                        api_obj.execute_plan()
                except api_errors.WrapSuccessfulIndexingException:
                        pass
                api_obj.reset()

        def test_license(self):
                """ Send various packages and then verify that install and
                update operations will raise the correct exceptions or
                enforce the requirements of the license actions within. """

                plist = self.pkgsend_bulk(self.rurl, (self.licensed10,
                    self.licensed12, self.licensed13, self.bar10, self.baz10))
                api_obj = self.image_create(self.rurl, prefix="bobcat")

                # First, test the basic install case to see if expected license
                # data is returned.
                for pd in api_obj.gen_plan_install(["licensed@1.0"]):
                        continue

                def lic_sort(a, b):
                        adest = a[2]
                        bdest = b[2]
                        return cmp(adest.license, bdest.license)

                plan = api_obj.describe()
                lics = sorted(plan.get_licenses(), cmp=lic_sort)

                # Expect one license action for each package: "licensed", and
                # its dependency "baz".
                self.assertEqual(len(lics), 2)

                # Now verify license entry for "baz@1.0" and "licensed@1.0".
                for i, p in enumerate([plist[4], plist[0]]):
                        pfmri = fmri.PkgFmri(p)
                        dest_fmri, src, dest, accepted, displayed = lics[i]

                        # Expect license information to be for this package.
                        self.assertEqual(pfmri, dest_fmri)

                        # This is an install, not an update, so there should be
                        # no src.
                        self.assertEqual(src, None)

                        # dest should be a LicenseInfo object.
                        self.assertEqual(type(dest), api.LicenseInfo)

                        # Verify the identity of the LicenseInfo objects.
                        self.assertEqual(dest.license,
                            "copyright.%s" % pfmri.pkg_name)

                        # The license hasn't been accepted yet.
                        self.assertEqual(accepted, False)

                        # The license hasn't beend displayed yet.
                        self.assertEqual(displayed, False)

                        # The license action doesn't require acceptance.
                        self.assertEqual(dest.must_accept, False)

                        # The license action doesn't require display.
                        self.assertEqual(dest.must_display, False)

                        # Verify license text.
                        text = dest.license
                        self.assertEqual(dest.get_text(), text)

                # Install the packages.
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

                # Next, check that an upgrade produces expected license data.
                for pd in api_obj.gen_plan_install(["licensed@1.2"]):
                        continue

                plan = api_obj.describe()
                lics = sorted(plan.get_licenses(), cmp=lic_sort)

                # Expect two license actions, both of which should be for the
                # licensed@1.2 package.
                self.assertEqual(len(lics), 2)

                # Now verify license entries for "licensed@1.2".
                pfmri = fmri.PkgFmri(plist[1])
                for dest_fmri, src, dest, accepted, displayed in lics:
                        # License information should only be for "licensed@1.2".
                        self.assertEqual(pfmri, dest_fmri)

                        must_accept = False
                        must_display = False
                        if dest.license.startswith("copyright"):
                                # This is an an update, so src should be a
                                # LicenseInfo object.
                                self.assertEqual(type(src), api.LicenseInfo)

                                # In this version, copyright must be displayed
                                # for dest.
                                must_display = True

                        # dest should be a LicenseInfo object.
                        self.assertEqual(type(dest), api.LicenseInfo)

                        # Verify LicenseInfo attributes.
                        self.assertEqual(accepted, False)
                        self.assertEqual(displayed, False)
                        self.assertEqual(dest.must_accept, must_accept)
                        self.assertEqual(dest.must_display, must_display)

                        # Verify license text.
                        text = dest.license
                        self.assertEqual(dest.get_text(), text)

                # Attempt to prepare plan; this should raise a license
                # exception.
                self.assertRaises(api_errors.PlanLicenseErrors,
                    api_obj.prepare)

                # Plan will have to be re-created first before continuing.
                api_obj.reset()
                for pd in api_obj.gen_plan_install(["licensed@1.2"]):
                        continue
                plan = api_obj.describe()

                # Set the copyright as having been displayed.
                api_obj.set_plan_license_status(pfmri, "copyright.licensed",
                    displayed=True)
                lics = sorted(plan.get_licenses(pfmri=pfmri), cmp=lic_sort)

                # Verify displayed was updated and accepted remains False.
                dest_fmri, src, dest, accepted, displayed = lics[0]
                self.assertEqual(src.license, "copyright.licensed")
                self.assertEqual(accepted, False)
                self.assertEqual(displayed, True)

                # Prepare should succeed this time; so execute afterwards.
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

                # Next, check that an update produces expected license
                # data.
                for pd in api_obj.gen_plan_update():
                        continue

                plan = api_obj.describe()
                lics = [l for l in plan.get_licenses()]

                # Expect one license action which should be for the licensed@1.3
                # package.  (Only one is expected since only one of the license
                # actions changed since licensed@1.2.)
                self.assertEqual(len(lics), 1)

                # Now verify license entries for "licensed@1.3".
                pfmri = fmri.PkgFmri(plist[2])
                dest_fmri, src, dest, accepted, displayed = lics[0]

                # License information should only be for "licensed@1.3".
                self.assertEqual(pfmri, dest_fmri)

                must_accept = False
                must_display = False

                # This is an an update, so src should be a LicenseInfo
                # object.
                self.assertEqual(type(src), api.LicenseInfo)

                assert dest.license.startswith("license.")
                # license must be accepted for dest.
                must_accept = True

                # dest should be a LicenseInfo object.
                self.assertEqual(type(dest), api.LicenseInfo)

                # Verify LicenseInfo attributes.
                self.assertEqual(accepted, False)
                self.assertEqual(displayed, False)
                self.assertEqual(dest.must_accept, must_accept)
                self.assertEqual(dest.must_display, must_display)

                # Verify license text.
                text = dest.license
                self.assertEqual(dest.get_text(), text)

                # Attempt to prepare plan; this should raise a license
                # exception.
                self.assertRaises(api_errors.PlanLicenseErrors, api_obj.prepare)

                # Plan will have to be re-created first before continuing.
                api_obj.reset()
                for pd in api_obj.gen_plan_update():
                        continue
                plan = api_obj.describe()

                # Set the license status of only one license.
                api_obj.set_plan_license_status(pfmri, "license.licensed",
                    accepted=True)
                lics = [l for l in plan.get_licenses(pfmri=pfmri)]

                # Verify only license.licensed was updated and exists.
                dest_fmri, src, dest, accepted, displayed = lics[0]
                self.assertEqual(src.license, "license.licensed")
                self.assertEqual(accepted, True)
                self.assertEqual(displayed, False)
                self.assertEqual(len(lics), 1)

                # Prepare should succeed this time; so execute afterwards.
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

                plist.extend(self.pkgsend_bulk(self.rurl, self.licensed14))
                api_obj.refresh()
                api_obj.reset()

                # Next, verify that an update to a newer version of a package
                # where the license hasn't changed and it previously required
                # acceptance is treated as already having been accepted.
                for pd in api_obj.gen_plan_update():
                        continue
                plan = api_obj.describe()
                pfmri = fmri.PkgFmri(plist[5])
                lics = sorted(plan.get_licenses(), cmp=lic_sort)
                for dest_fmri, src, dest, accepted, displayed in lics:
                        # License information should only be for "licensed@1.4".
                        self.assertEqual(pfmri, dest_fmri)

                        if dest.must_accept:
                                # Since the license hasn't changed and was
                                # previously accepted, then acceptance shouldn't
                                # be required here.
                                self.assertTrue(accepted)
                api_obj.reset()

                # Finally, verify that an uninstall won't trigger license
                # errors as acceptance should never be applied to it.
                for pd in api_obj.gen_plan_uninstall(["*"]):
                        continue
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

        def test_syspub_version_error(self):
                api_obj = self.image_create()
                try:
                        api_obj.write_syspub("", [], 999)
                except api_errors.UnsupportedP5SVersion, e:
                        str(e)
                else:
                        raise RuntimeError("Expected write_syspub to raise "
                            "an exception.")

if __name__ == "__main__":
        unittest.main()
