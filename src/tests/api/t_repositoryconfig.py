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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import copy
import os
import sys
import tempfile

import pkg.server.repositoryconfig as rcfg

class TestRepositoryConfig(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of RepositoryConfig.
        """
        __props = {
            "publisher": {
                "alias": {
                    "type": rcfg.PROP_TYPE_PUB_ALIAS,
                    "default": "pending"
                },
                "prefix": {
                    "type": rcfg.PROP_TYPE_PUB_PREFIX,
                    "default": "org.opensolaris.pending"
                }
            },
            "repository": {
                "collection_type": {
                    "type": rcfg.PROP_TYPE_REPO_COLL_TYPE,
                    "default": "supplemental"
                },
                "description": {
                    "default": """This repository serves the currently in-""" \
                        """development packages for the contrib repository. """ \
                        """For tested bits, see <a """ \
                        """href="http://pkg.opensolaris.org/contrib">the """ \
                        """contrib repository</a>."""
                },
                "detailed_url": {
                    "type": rcfg.PROP_TYPE_URI,
                    "default":
                        "http://opensolaris.org/os/community/sw-porters/contributing/",
                },
                "legal_uris": {
                    "type": rcfg.PROP_TYPE_URI_LIST,
                    "default": [
                        "http://www.opensolaris.org/os/copyrights/",
                        "http://www.opensolaris.org/os/tou/",
                        "http://www.opensolaris.org/os/trademark/"
                    ]
                },
                "maintainer": {
                    "default":
                        "Software Porters <sw-porters-discuss@opensolaris.org>"
                },
                "maintainer_url": {
                    "type": rcfg.PROP_TYPE_URI,
                    "default":
                        "http://www.opensolaris.org/os/community/sw-porters/"
                },
                "mirrors": {
                    "type": rcfg.PROP_TYPE_URI_LIST,
                    "default": []
                },
                "name": {
                    "default": """"Pending" Repository"""
                },
                "origins": {
                    "type": rcfg.PROP_TYPE_URI_LIST,
                    "default": ["http://pkg.opensolaris.org/pending"]
                },
                "refresh_seconds": {
                    "type": rcfg.PROP_TYPE_INT,
                    "default": 86400,
                },
                "registration_uri": {
                    "type": rcfg.PROP_TYPE_URI,
                    "default": "",
                },
                "related_uris": {
                    "type": rcfg.PROP_TYPE_URI_LIST,
                    "default": [
                        "http://pkg.opensolaris.org/contrib",
                        "http://jucr.opensolaris.org/pending",
                        "http://jucr.opensolaris.org/contrib"
                    ]
                },
            },
            "feed": {
                "id": {
                    "type": rcfg.PROP_TYPE_UUID,
                    "readonly": True,
                    "default": "16fd2706-8baf-433b-82eb-8c7fada847da"
                },
                "name": {
                    "default": "pending repository image packaging feed"
                },
                "description": {
                    "default": "An RSS/Atom feed that contains a summary of "
                        "repository changes."
                },
                "icon": {
                    "default": "pkg-block-icon.png"
                },
                "logo": {
                    "default": "pkg-block-logo.png"
                },
                "window": {
                    "type": rcfg.PROP_TYPE_INT,
                    "default": 24
                },
                # This property is only present in this test program so that
                # boolean properties can be tested.
                "enabled": {
                    "type": rcfg.PROP_TYPE_BOOL,
                    "default": True
                }
            }
        }

        def setUp(self):
                """Setup our tests.
                """
                pkg5unittest.Pkg5TestCase.setUp(self)

                fd, self.sample_conf = tempfile.mkstemp(dir=self.test_root)
                f = os.fdopen(fd, "w")

                self.remove = [self.sample_conf]

                # Merge any test properties into RepositoryConfig's normal
                # set so that we can test additional property data types.
                props = self.__props
                cprops = rcfg.RepositoryConfig._props
                for section in props:
                        if section not in cprops:
                                cprops[section] = copy.deepcopy(props[section])
                                continue

                        for prop in props[section]:
                                if prop not in cprops[section]:
                                        cprops[section][prop] = copy.deepcopy(
                                            props[section][prop])

                # Write out a sample configuration in ConfigParser format.
                get_property_type = rcfg.RepositoryConfig.get_property_type
                props = self.__props
                for section in props:
                        f.write("[%s]\n" % section)
                        for prop in props[section]:
                                atype = get_property_type(section, prop)
                                val = props[section][prop]["default"]
                                if atype == rcfg.PROP_TYPE_URI_LIST:
                                        val = ",".join(val)
                                f.write("%s = %s\n" % (prop, val))
                        f.write("\n")
                f.close()

        def tearDown(self):
                """Cleanup after our tests.
                """
                for f in self.remove:
                        if os.path.exists(f):
                                os.remove(f)

        def test_init(self):
                """Verify that RepositoryConfig init accepts a pathname and
                returns the expected configuration data.
                """
                rcfg.RepositoryConfig(self.sample_conf)

        def test_write(self):
                """Verify that write() succeeds for a known good configuration.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                rc.set_property("publisher", "prefix", "test-write")
                rc.write()
                rc = rcfg.RepositoryConfig(self.sample_conf)
                self.assertEqual(rc.get_property("publisher", "prefix"),
                    "test-write")

        def test_get_property(self):
                """Verify that each property's value in sample_conf matches
                what we retrieved.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)

                props = self.__props
                for section in props:
                        for prop in props[section]:
                                returned = rc.get_property(section, prop)
                                self.assertEqual(returned,
                                    props[section][prop]["default"])

        def test_get_invalid_property(self):
                """Verify that attempting to retrieve an invalid property will
                result in an InvalidPropertyError exception.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                self.assertRaises(rcfg.InvalidPropertyError, rc.get_property,
                    "repository", "foo")

        def test_get_property_type(self):
                """Verify that each property's type matches the\
                default object state.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                props = self.__props
                for section in props:
                        for prop in props[section]:
                                returned = rc.get_property_type(section, prop)
                                expected = props[section][prop].get("type",
                                    rcfg.PROP_TYPE_STR)
                                try:
                                        self.assertEqual(returned, expected)
                                except Exception, e:
                                        raise RuntimeError("An unexpected "
                                            "property type was returned for "
                                            "property '%s': '%s'")

        def test_get_properties(self):
                """Verify that all expected properties were returned by
                get_properties and that each property returned can have its
                value retrieved.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                props = rc.get_properties()
                self.assertEqual(len(props), len(self.__props))
                for section in props:
                        self.assertEqual(len(props[section]),
                            len(self.__props[section]))
                        for prop in props[section]:
                                rc.get_property(section, prop)

        def test_set_property(self):
                """Verify that each property can be set (unless read-only) and
                that the set value matches what we expect both before and after
                write().  Calling set for a read-only value should raise a
                ValueError exception.
                """
                fd, sample_conf = tempfile.mkstemp(dir=self.test_root)
                self.remove.append(sample_conf)
                rc = rcfg.RepositoryConfig(sample_conf)
                props = self.__props
                for section in props:
                        for prop in props[section]:
                                value = props[section][prop]["default"]
                                readonly = props[section][prop].get("readonly",
                                    False)
                                if readonly:
                                        self.assertRaises(
                                            rcfg.ReadOnlyPropertyError,
                                            rc.set_property, section, prop,
                                            value)
                                        rc._set_property(section, prop, value)
                                else:
                                        rc.set_property(section, prop, value)

                                returned = rc.get_property(section, prop)
                                self.assertEqual(returned, value)

                rc.write()
                os.close(fd)

                rc = rcfg.RepositoryConfig(sample_conf)
                for section in props:
                        for prop in props[section]:
                                value = props[section][prop]["default"]
                                returned = rc.get_property(section, prop)
                                self.assertEqual(returned, value)

        def test_set_invalid_property(self):
                """Verify that attempting to set an invalid property will
                result in an InvalidPropertyError exception.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify an exception is raised for an invalid property.
                self.assertRaises(rcfg.InvalidPropertyError, rc.set_property,
                    "repository", "foo", "baz")

                # Verify that an exception is raised for an invalid section.
                self.assertRaises(rcfg.InvalidPropertyError, rc.set_property,
                    "bar", "id", None)

        def test__set_invalid_property(self):
                """Verify that attempting to _set an invalid property will
                result in an InvalidPropertyError exception.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that it happens for an invalid property.
                self.assertRaises(rcfg.InvalidPropertyError,
                    rc.set_property, "repository", "foo", "bar")

                # Verify that it happens for an invalid section.
                self.assertRaises(rcfg.InvalidPropertyError,
                    rc._set_property, "bar", "id", "baz")

        def test_is_valid_property(self):
                """Verify that is_valid_property returns a boolean value
                indicating the validity of the property or raises an
                exception if raise_error=True and the property is
                invalid.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property.
                self.assertFalse(rc.is_valid_property("repository", "foo"))

                # Verify that False is returned for an invalid property
                # section.
                self.assertFalse(rc.is_valid_property("bar", "foo"))

                # Verify that True is returned for a valid property.
                self.assertTrue(rc.is_valid_property("feed", "id"))

                # Verify that an exception is raised for an invalid property.
                self.assertRaises(rcfg.InvalidPropertyError,
                    rc.is_valid_property, "repository", "foo",
                    raise_error=True)

                # Verify that an exception is raised for an invalid property
                # section.
                self.assertRaises(rcfg.InvalidPropertyError,
                    rc.is_valid_property, "bar", "foo", raise_error=True)

        def test_is_valid_property_value(self):
                """Verify that is_valid_property_value returns a boolean value
                indicating the validity of the property value or raises an
                exception if raise_error=True and the property value is
                invalid.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("feed", "window",
                    "foo"))

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("feed", "window",
                    24))

                # Verify that an exception is raised for an invalid property
                # value when raise_error=True.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "feed", "window", "foo",
                    raise_error=True)

        def test_is_valid_property_value_uuid(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of UUID property values.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("feed", "id",
                    "8baf-433b-82eb-8c7fada847da"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "feed", "id",
                    "8baf-433b-82eb-8c7fada847da", raise_error=True)

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("feed", "id",
                    "16fd2706-8baf-433b-82eb-8c7fada847da"))

        def test_is_valid_property_value_bool(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of bool property values.
                """
                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for invalid property values.
                self.assertFalse(rc.is_valid_property_value("feed",
                    "enabled", "foo"))
                self.assertFalse(rc.is_valid_property_value("feed",
                    "enabled", "1"))
                self.assertFalse(rc.is_valid_property_value("feed",
                    "enabled", "0"))
                self.assertFalse(rc.is_valid_property_value("feed",
                    "enabled", "true"))
                self.assertFalse(rc.is_valid_property_value("feed",
                    "enabled", "false"))
                self.assertFalse(rc.is_valid_property_value("feed",
                    "enabled", ""))

                # Verify that an exception is raised when raise_error=True for
                # a missing property value.
                self.assertRaises(rcfg.RequiredPropertyValueError,
                    rc.is_valid_property_value, "feed", "enabled", "",
                    raise_error=True)

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "feed", "id", "mumble",
                    raise_error=True)

                # Verify that True is returned for valid property values.
                self.assertTrue(rc.is_valid_property_value("feed",
                    "enabled", "True"))
                self.assertTrue(rc.is_valid_property_value("feed",
                    "enabled", True))
                self.assertTrue(rc.is_valid_property_value("feed",
                    "enabled", "False"))
                self.assertTrue(rc.is_valid_property_value("feed",
                    "enabled", False))

        def test_is_valid_property_value_uri(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of uri property values.
                """

                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("repository",
                    "registration_uri", "abc.123^@#$&)(*&#$)"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "repository",
                    "registration_uri",
                    "abc.123^@#$&)(*&#$)", raise_error=True)

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("repository",
                    "registration_uri", "https://pkg.sun.com/register"))

        def test_is_valid_property_value_uri_list(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of uri_list property
                values.
                """

                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("repository",
                    "mirrors", "http://example.com/mirror, abc.123^@#$&)(*&#$)"))
                self.assertFalse(rc.is_valid_property_value("repository",
                    "mirrors", ","))

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "repository", "mirrors",
                    "example.com,example.net", raise_error=True)

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("repository",
                    "mirrors", ["http://example.com/mirror1",
                    "http://example.net/mirror2"]))

        def test_is_valid_property_value_pub_alias(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of publisher alias
                property values.
                """

                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("publisher",
                    "alias", "abc.123^@#$&)(*&#$)"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "publisher", "alias",
                    "abc.123^@#$&)(*&#$)", raise_error=True)

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("publisher",
                    "alias", "bobcat"))

        def test_is_valid_property_value_pub_prefix(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of publisher prefix
                property values.
                """

                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("publisher",
                    "prefix", "abc.123^@#$&)(*&#$)"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "publisher", "prefix",
                    "abc.123^@#$&)(*&#$)", raise_error=True)

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("publisher",
                    "prefix", "xkcd.net"))

        def test_is_valid_property_value_repo_coll_type(self):
                """Verify that is_valid_property_value returns the expected
                boolean value indicating the validity of repository collection
                type property values.
                """

                rc = rcfg.RepositoryConfig(self.sample_conf)
                # Verify that False is returned for an invalid property value.
                self.assertFalse(rc.is_valid_property_value("repository",
                    "collection_type", "donotwant"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid property value.
                self.assertRaises(rcfg.InvalidPropertyValueError,
                    rc.is_valid_property_value, "repository",
                    "collection_type", "donotwant", raise_error=True)

                # Verify that True is returned for a valid property value.
                self.assertTrue(rc.is_valid_property_value("repository",
                    "collection_type", "supplemental"))

        def test_missing_conffile(self):
                """Verify that a missing conf file gets created"
                """
                os.remove(self.sample_conf)
                rc = rcfg.RepositoryConfig(self.sample_conf)
                rc.write()
                self.assertTrue(os.path.isfile(self.sample_conf))

        def test_overrides_are_dirty(self):
                """Verify that specifying overridden properties marks
                the RepositoryConfig dirty, so a subsequent write()
                goes to disk"""
                overrides = {"publisher": {"prefix": "overridden"}}

                rc = rcfg.RepositoryConfig(self.sample_conf,
                    properties=overrides)
                rc.write()
                rc = rcfg.RepositoryConfig(self.sample_conf)
                self.assertEqual(rc.get_property("publisher", "prefix"),
                    "overridden")


if __name__ == "__main__":
        unittest.main()

