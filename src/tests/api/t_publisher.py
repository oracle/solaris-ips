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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#


from . import testutils
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

        # Tests in this suite use the read only data directory.
        need_ro_data = True

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
                # this value is valid only for ProxyURI objects, not
                # RepositoryURI objects
                self.assertRaises(api_errors.BadRepositoryURI, setattr, uobj,
                    "uri", "http://user:password@server")
                self.assertRaises(api_errors.BadRepositoryURIPriority,
                    setattr, uobj, "priority", "foo")
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "ssl_cert", -1)
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "ssl_key", -1)

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

                # Verify that proxies are set properly
                uobj = publisher.RepositoryURI("https://example.com",
                    proxies=[])
                uobj = publisher.RepositoryURI("https://example.com",
                    proxies=[publisher.ProxyURI("http://foo.com")])

                self.assertTrue(uobj.proxies == [publisher.ProxyURI(
                    "http://foo.com")])
                uobj.proxies = []
                self.assertTrue(uobj.proxies == [])

                # Verify that proxies and proxy are linked
                uobj.proxies = [publisher.ProxyURI("http://foo.com")]
                self.assertTrue(uobj.proxy == "http://foo.com")
                uobj.proxy = "http://bar"
                self.assertTrue(uobj.proxies == [publisher.ProxyURI("http://bar")])

                try:
                        raised = False
                        publisher.RepositoryURI("http://foo", proxies=[
                            publisher.ProxyURI("http://bar")],
                            proxy="http://foo")
                except api_errors.PublisherError:
                        raised = True
                finally:
                        self.assertTrue(raised, "No exception raised when "
                            "creating a RepositoryURI obj with proxies & proxy")

                # Check that we detect bad values for proxies
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "proxies", "foo")
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "proxies", [None])
                # we only support a single proxy per RepositoryURI
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, uobj, "proxies", [
                    publisher.ProxyURI("http://foo.com"),
                    publisher.ProxyURI("http://bar.com")])


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
                                method = getattr(robj, "add_{0}".format(utype))
                                method(u, priority=1, ssl_cert=tcert,
                                    ssl_key=tkey)

                # Verify that has and get functions work as expected.
                for utype in ("mirror", "origin"):
                        prop = utype + "s"
                        for u in rprops[prop]:
                                method = getattr(robj, "has_{0}".format(utype))
                                self.assertTrue(method(u))

                                method = getattr(robj, "get_{0}".format(utype))
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
                        method = getattr(robj, "remove_{0}".format(utype))
                        method(u)
                        self.assertTrue(u not in getattr(robj, prop))
                        self.assertEqual(len(getattr(robj, prop)), 1)

                # Verify that update functions work as expected.
                for utype in ("mirror", "origin"):
                        prop = utype + "s"

                        # Update only the last entry for each property.
                        u = rprops[prop][-1]

                        method = getattr(robj, "update_{0}".format(utype))
                        method(u, priority=2, ssl_cert=t2cert, ssl_key=t2key)

                        method = getattr(robj, "get_{0}".format(utype))
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
                        method = getattr(robj, "reset_{0}".format(prop))
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
                    "repository": r2obj,
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
                        if p == "repository":
                                # These attributes can't be directly compared.
                                continue
                        self.assertEqual(getattr(pobj, p), getattr(cpobj, p))

                # Assume that if the origins match, we have the right selected
                # repository.
                self.assertEqual(cpobj.repository.origins,
                    r2obj.origins)

                # Compare the source_object_id of the copied repository object
                # with the id of the source repository object.
                self.assertEqual(id(pobj), cpobj._source_object_id)

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

                pobj.repository = robj
                self.assertEqual(pobj.repository, robj)

                # An invalid value shouldn't be allowed.
                self.assertRaises(api_errors.UnknownRepository, setattr,
                    pobj, "repository", -1)

                pobj.reset_client_uuid()
                self.assertNotEqual(pobj.client_uuid, None)
                self.assertNotEqual(pobj.client_uuid, pprops["client_uuid"])

                pobj.create_meta_root()
                self.assertTrue(os.path.exists(pobj.meta_root))

                pobj.remove_meta_root()
                self.assertFalse(os.path.exists(pobj.meta_root))

        def test_04_proxy_uri(self):
                """Verify that a ProxyURI object can be created, copied,
                modified, and used as expected."""

                pobj = publisher.ProxyURI("http://example.com")
                self.assertTrue(pobj.uri == "http://example.com")

                tcert = os.path.join(self.test_root, "test.cert")
                tkey = os.path.join(self.test_root, "test.key")
                # check that we can't set several RepositoryURI attributes
                bad_props = {
                    "priority": 1,
                    "ssl_cert": tcert,
                    "ssl_key": tkey,
                    "trailing_slash": False
                }

                pobj = publisher.ProxyURI("http://example.com")
                for prop in bad_props:
                        self.assertRaises(ValueError,
                            setattr, pobj, prop, bad_props[prop])

                # check bad values for system
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, pobj, "system", "Carrots")
                self.assertRaises(api_errors.BadRepositoryAttributeValue,
                    setattr, pobj, "system", None)

                # check that we can set URI values that RespositoryURI would
                # choke on
                uri = "http://user:pass@server"
                pobj.uri = uri
                self.assertTrue(pobj.uri == uri)

                # check that setting system results in uri being overridden
                pobj.system = True
                self.assertTrue(pobj.system == True)
                self.assertTrue(pobj.uri == publisher.SYSREPO_PROXY)

                # check that clearing system also clears uri
                pobj.system = False
                self.assertTrue(pobj.system == False)
                self.assertTrue(pobj.uri == None)


if __name__ == "__main__":
        unittest.main()

