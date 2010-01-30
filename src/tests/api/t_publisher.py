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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import errno
import os
import shutil
import sys
import tempfile
import unittest

import pkg.client.api_errors as api_errors
import pkg.client.publisher as publisher
import pkg.misc as misc


class TestPublisher(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of the pkg.client.publisher module.
        """

        misc_files = [ "test.cert", "test.key", "test2.cert", "test2.key" ]

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def test_01_repository_uri(self):
                """Verify that a RepositoryURI object can be created, copied,
                modified, and used as expected."""

                nsfile = os.path.join(self.test_root, "nosuchfile")
                tcert = os.path.join(self.test_root, "test.cert")
                tkey = os.path.join(self.test_root, "test.key")

                uprops = {
                    "priority": 1,
                    "ssl_cert": tcert,
                    "ssl_key": tkey,
                    "trailing_slash": False,
                }

                # Check that all properties can be set at construction time.
                uobj = publisher.RepositoryURI("https://example.com", **uprops)

                # Verify that all properties provided at construction time were
                # set as expected.
                self.assertEqual(uobj.uri, "https://example.com")
                for p in uprops:
                        self.assertEqual(uprops[p], getattr(uobj, p))

                # Verify that scheme matches provided URI.
                self.assertEqual(uobj.scheme, "https")

                # Verify that a copy matches its original.
                cuobj = copy.copy(uobj)
                self.assertEqual(uobj.uri, cuobj.uri)
                for p in uprops:
                        self.assertEqual(getattr(uobj, p), getattr(cuobj, p))
                cuobj = None

                # Verify that setting invalid property values raises the
                # expected exception.
                self.assertRaises(api_errors.BadRepositoryURI, setattr, uobj,
                    "uri", None)
                self.assertRaises(api_errors.UnsupportedRepositoryURI, setattr,
                    uobj, "uri", ":/notvalid")
                self.assertRaises(api_errors.BadRepositoryURIPriority,
                    setattr, uobj, "priority", "foo")
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "ssl_cert", -1)
                self.assertRaises(api_errors.NoSuchCertificate, setattr, uobj,
                    "ssl_cert", nsfile)
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "ssl_key", -1)
                self.assertRaises(api_errors.NoSuchKey, setattr, uobj,
                    "ssl_key", nsfile)

                # Verify that changing the URI scheme will null properties that
                # no longer apply.
                uobj.uri = "http://example.com"
                self.assertEqual(uobj.ssl_cert, None)
                self.assertEqual(uobj.ssl_key, None)

                # Verify that scheme matches provided URI.
                self.assertEqual(uobj.scheme, "http")

                # Verify that attempting to set properties not valid for the
                # current URI scheme raises the expected exception.
                self.assertRaises(api_errors.UnsupportedRepositoryURIAttribute,
                    setattr, uobj, "ssl_cert", tcert)
                self.assertRaises(api_errors.UnsupportedRepositoryURIAttribute,
                    setattr, uobj, "ssl_key", tkey)

                # Verify that individual properties can be set.
                uobj = publisher.RepositoryURI("https://example.com/")
                for p in uprops:
                        setattr(uobj, p, uprops[p])
                        self.assertEqual(getattr(uobj, p), uprops[p])

                # Finally, verify all properties (except URI and trailing_slash)
                # can be set to None.
                for p in ("priority", "ssl_cert", "ssl_key"):
                        setattr(uobj, p, None)
                        self.assertEqual(getattr(uobj, p), None)

        def test_02_repository(self):
                """Verify that a Repository object can be created, copied,
                modified, and used as expected."""

                tcert = os.path.join(self.test_root, "test.cert")
                tkey = os.path.join(self.test_root, "test.key")

                t2cert = os.path.join(self.test_root, "test2.cert")
                t2key = os.path.join(self.test_root, "test2.key")

                rprops = {
                    "collection_type": publisher.REPO_CTYPE_SUPPLEMENTAL,
                    "description": "Provides only the best BobCat packages!",
                    "legal_uris": [
                        "http://legal1.example.com",
                        "http://legal2.example.com"
                    ],
                    "mirrors": [
                        "http://mirror1.example.com/",
                        "http://mirror2.example.com/"
                    ],
                    "name": "BobCat Repository",
                    "origins": [
                        "http://origin1.example.com/",
                        "http://origin2.example.com/"
                    ],
                    "refresh_seconds": 70000,
                    "registered": True,
                    "registration_uri": "http://register.example.com/",
                    "related_uris": [
                        "http://related1.example.com",
                        "http://related2.example.com"
                    ],
                    "sort_policy": publisher.URI_SORT_PRIORITY,
                }

                # Check that all properties can be set at construction time.
                robj = publisher.Repository(**rprops)

                # Verify that all properties provided at construction time were
                # set as expected.
                for p in rprops:
                        self.assertEqual(rprops[p], getattr(robj, p))

                # Verify that a copy matches its original.
                crobj = copy.copy(robj)
                for p in rprops:
                        self.assertEqual(getattr(robj, p), getattr(crobj, p))
                crobj = None

                # New set of rprops for testing (all the URI use https so that
                # setting ssl_key and ssl_cert can be tested).
                rprops = {
                    "collection_type": publisher.REPO_CTYPE_SUPPLEMENTAL,
                    "description": "Provides only the best BobCat packages!",
                    "legal_uris": [
                        "https://legal1.example.com",
                        "https://legal2.example.com"
                    ],
                    "mirrors": [
                        "https://mirror1.example.com/",
                        "https://mirror2.example.com/"
                    ],
                    "name": "BobCat Repository",
                    "origins": [
                        "https://origin1.example.com/",
                        "https://origin2.example.com/"
                    ],
                    "refresh_seconds": 70000,
                    "registered": True,
                    "registration_uri": "https://register.example.com/",
                    "related_uris": [
                        "https://related1.example.com",
                        "https://related2.example.com"
                    ],
                    "sort_policy": publisher.URI_SORT_PRIORITY,
                }

                # Verify that individual properties can be set.
                robj = publisher.Repository()
                for p in rprops:
                        setattr(robj, p, rprops[p])
                        self.assertEqual(getattr(robj, p), rprops[p])

                # Verify that setting invalid property values raises the
                # expected exception.
                self.assertRaises(api_errors.BadRepositoryCollectionType,
                    setattr, robj, "collection_type", -1)
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, robj, "refresh_seconds", -1)
                self.assertRaises(api_errors.BadRepositoryURISortPolicy,
                    setattr, robj, "sort_policy", -1)

                # Verify that add functions work as expected.
                robj = publisher.Repository()
                for utype in ("legal_uri", "mirror", "origin", "related_uri"):
                        prop = utype + "s"
                        for u in rprops[prop]:
                                method = getattr(robj, "add_%s" % utype)
                                method(u, priority=1, ssl_cert=tcert,
                                    ssl_key=tkey)

                # Verify that has and get functions work as expected.
                for utype in ("mirror", "origin"):
                        prop = utype + "s"
                        for u in rprops[prop]:
                                method = getattr(robj, "has_%s" % utype)
                                self.assertTrue(method(u))

                                method = getattr(robj, "get_%s" % utype)
                                cu = publisher.RepositoryURI(u, priority=1,
                                    ssl_cert=tcert, ssl_key=tkey,
                                    trailing_slash=True)
                                ou = method(u)

                                # This verifies that the expected URI object is
                                # returned and that all of the properties match
                                # exactly as they were added.
                                for uprop in ("uri", "priority", "ssl_cert",
                                    "ssl_key", "trailing_slash"):
                                        self.assertEqual(getattr(cu, uprop),
                                            getattr(ou, uprop))

                # Verify that remove functions work as expected.
                for utype in ("legal_uri", "mirror", "origin", "related_uri"):
                        prop = utype + "s"

                        # Remove only the first URI for each property.
                        u = rprops[prop][0]
                        method = getattr(robj, "remove_%s" % utype)
                        method(u)
                        self.assertTrue(u not in getattr(robj, prop))
                        self.assertEqual(len(getattr(robj, prop)), 1)

                # Verify that update functions work as expected.
                for utype in ("mirror", "origin"):
                        prop = utype + "s"

                        # Update only the last entry for each property.
                        u = rprops[prop][-1]

                        method = getattr(robj, "update_%s" % utype)
                        method(u, priority=2, ssl_cert=t2cert, ssl_key=t2key)

                        method = getattr(robj, "get_%s" % utype)
                        ou = method(u)

                        # This verifies that the expected URI object is
                        # returned and that all of the properties match
                        # exactly as specified to the update method.
                        cu = publisher.RepositoryURI(u, priority=2,
                            ssl_cert=t2cert, ssl_key=t2key)
                        for uprop in ("uri", "priority", "ssl_cert",
                            "ssl_key", "trailing_slash"):
                                self.assertEqual(getattr(cu, uprop),
                                    getattr(ou, uprop))

                # Verify that reset functions work as expected.
                for prop in ("mirrors", "origins"):
                        method = getattr(robj, "reset_%s" % prop)
                        method()
                        self.assertEqual(getattr(robj, prop), [])


        def test_03_publisher(self):
                """Verify that a Repository object can be created, copied,
                modified, and used as expected."""

                robj = publisher.Repository(
                    collection_type=publisher.REPO_CTYPE_SUPPLEMENTAL,
                    description="Provides only the best BobCat packages!",
                    legal_uris=[
                        "http://legal1.example.com",
                        "http://legal2.example.com"
                    ],
                    mirrors=[
                        "http://mirror1.example.com/",
                        "http://mirror2.example.com/"
                    ],
                    name="First Repository",
                    origins=[
                        "http://origin1.example.com/",
                        "http://origin2.example.com/"
                    ],
                    refresh_seconds=70000,
                    registered=True,
                    registration_uri="http://register.example.com/",
                    related_uris=[
                        "http://related1.example.com",
                        "http://related2.example.com"
                    ],
                    sort_policy=publisher.URI_SORT_PRIORITY,
                )

                r2obj = copy.copy(robj)
                r2obj.origins = ["http://origin3.example.com"]
                r2obj.name = "Second Repository"
                r2obj.reset_mirrors()

                pprops = {
                    "alias": "cat",
                    "client_uuid": "2c6a8ff8-20e5-11de-a818-001fd0979039",
                    "disabled": True,
                    "meta_root": os.path.join(self.test_root, "bobcat"),
                    "repositories": [robj, r2obj],
                    "selected_repository": r2obj,
                }

                # Check that all properties can be set at construction time.
                pobj = publisher.Publisher("bobcat", **pprops)

                # Verify that all properties provided at construction time were
                # set as expected.
                for p in pprops:
                        self.assertEqual(pprops[p], getattr(pobj, p))

                # Verify that a copy matches its original.
                cpobj = copy.copy(pobj)
                for p in pprops:
                        if p in ("repositories", "selected_repository"):
                                # These attributes can't be directly compared.
                                continue
                        self.assertEqual(getattr(pobj, p), getattr(cpobj, p))

                # Assume that if the origins match, we have the right selected
                # repository.
                self.assertEqual(cpobj.selected_repository.origins,
                    r2obj.origins)

                # Compare all of the repository objects individually.  Assume
                # that if the source_object_id matches, that the copy happened
                # correctly.
                for i in range(0, len(pobj.repositories)):
                        srepo = pobj.repositories[i]
                        crepo = cpobj.repositories[i]
                        self.assertEqual(id(srepo), crepo._source_object_id)
                cpobj = None

                # Verify that individual properties can be set.
                pobj = publisher.Publisher("tomcat")
                pobj.prefix = "bobcat"
                self.assertEqual(pobj.prefix, "bobcat")

                for p in pprops:
                        if p == "repositories":
                                for r in pprops[p]:
                                        pobj.add_repository(r)
                        else:
                                setattr(pobj, p, pprops[p])
                        self.assertEqual(getattr(pobj, p), pprops[p])

                pobj.selected_repository = robj
                self.assertEqual(pobj.selected_repository, robj)

                # An invalid value shouldn't be allowed.
                self.assertRaises(api_errors.UnknownRepository, setattr,
                    pobj, "selected_repository", -1)

                # A repository object not already in the list of repositories
                # shouldn't be allowed.
                self.assertRaises(api_errors.UnknownRepository, setattr,
                    pobj, "selected_repository", publisher.Repository())

                # Verify that management methods work as expected.
                pobj.set_selected_repository(origin=r2obj.origins[-1])
                self.assertEqual(pobj.selected_repository, r2obj)

                pobj.set_selected_repository(name=robj.name)
                self.assertEqual(pobj.selected_repository, robj)

                pobj.reset_client_uuid()
                self.assertNotEqual(pobj.client_uuid, None)
                self.assertNotEqual(pobj.client_uuid, pprops["client_uuid"])

                pobj.create_meta_root()
                self.assertTrue(os.path.exists(pobj.meta_root))

                pobj.remove_meta_root()
                self.assertFalse(os.path.exists(pobj.meta_root))

                # Verify that get and remove works as expected.
                for r in pprops["repositories"]:
                        gr = pobj.get_repository(name=r.name)
                        self.assertEqual(r, gr)

                        gr = pobj.get_repository(origin=r.origins[-1])
                        self.assertEqual(r, gr)

                        if r == pobj.selected_repository:
                                # Attempting to remove the selected repository
                                # should raise an exception.
                                ex = api_errors.SelectedRepositoryRemoval
                                self.assertRaises(ex, pobj.remove_repository,
                                    name=r.name)
                        else:
                                pobj.remove_repository(name=r.name)
                                self.assertRaises(api_errors.UnknownRepository,
                                    pobj.get_repository, name=r.name)


if __name__ == "__main__":
        unittest.main()

