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

import unittest
import copy
import os
import sys
import tempfile

import pkg.server.repositoryconfig as rcfg

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestRepositoryConfig(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of RepositoryConfig.
        """
        __attrs = {
            "publisher": {
                "alias": {
                    "type": rcfg.ATTR_TYPE_PUB_ALIAS,
                    "default": "pending"
                },
                "prefix": {
                    "type": rcfg.ATTR_TYPE_PUB_PREFIX,
                    "default": "org.opensolaris.pending"
                }
            },
            "repository": {
                "collection_type": {
                    "type": rcfg.ATTR_TYPE_REPO_COLL_TYPE,
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
                    "type": rcfg.ATTR_TYPE_URI,
                    "default":
                        "http://opensolaris.org/os/community/sw-porters/contributing/",
                },
                "legal_uris": {
                    "type": rcfg.ATTR_TYPE_URI_LIST,
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
                    "type": rcfg.ATTR_TYPE_URI,
                    "default":
                        "http://www.opensolaris.org/os/community/sw-porters/"
                },
                "mirrors": {
                    "type": rcfg.ATTR_TYPE_URI_LIST,
                    "default": []
                },
                "name": {
                    "default": """"Pending" Repository"""
                },
                "origins": {
                    "type": rcfg.ATTR_TYPE_URI_LIST,
                    "default": ["http://pkg.opensolaris.org/pending"]
                },
                "refresh_seconds": {
                    "type": rcfg.ATTR_TYPE_INT,
                    "default": 86400,
                },
                "registration_uri": {
                    "type": rcfg.ATTR_TYPE_URI,
                    "default": "",
                },
                "related_uris": {
                    "type": rcfg.ATTR_TYPE_URI_LIST,
                    "default": [
                        "http://pkg.opensolaris.org/contrib",
                        "http://jucr.opensolaris.org/pending",
                        "http://jucr.opensolaris.org/contrib"
                    ]
                },
            },
            "feed": {
                "id": {
                    "type": rcfg.ATTR_TYPE_UUID,
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
                    "type": rcfg.ATTR_TYPE_INT,
                    "default": 24
                },
                # This attribute is only present in this test program so that
                # boolean attributes can be tested.
                "enabled": {
                    "type": rcfg.ATTR_TYPE_BOOL,
                    "default": True
                }
            }
        }

        def setUp(self):
                """Setup our tests.
                """
                fd, self.sample_conf = tempfile.mkstemp()
                f = os.fdopen(fd, "w")

                # Merge any test attributes into RepositoryConfig's normal
                # set so that we can test additional attribute data types.
                attrs = self.__attrs
                cattrs = rcfg.RepositoryConfig._attrs
                for section in attrs:
                        if section not in cattrs:
                                cattrs[section] = copy.deepcopy(attrs[section])
                                continue

                        for attr in attrs[section]:
                                if attr not in cattrs[section]:
                                        cattrs[section][attr] = copy.deepcopy(
                                            attrs[section][attr])

                # Write out a sample configuration in ConfigParser format.
                rc = rcfg.RepositoryConfig()
                attrs = self.__attrs
                for section in attrs:
                        f.write("[%s]\n" % section)
                        for attr in attrs[section]:
                                atype = rc.get_attribute_type(section, attr)
                                val = attrs[section][attr]["default"]
                                if atype == rcfg.ATTR_TYPE_URI_LIST:
                                        val = ",".join(val)
                                f.write("%s = %s\n" % (attr, val))
                        f.write("\n")
                f.close()

        def tearDown(self):
                """Cleanup after our tests.
                """
                if os.path.exists(self.sample_conf):
                        os.remove(self.sample_conf)

        def test_init(self):
                """Verify that RepositoryConfig init accepts a pathname and
                returns the expected configuration data.
                """
                rcfg.RepositoryConfig(pathname=self.sample_conf)

        def test_read(self):
                """Verify that read() succeeds for a known good configuration.
                """
                rc = rcfg.RepositoryConfig()
                rc.read(self.sample_conf)

        def test_write(self):
                """Verify that write() succeeds for a known good configuration.
                """
                rc = rcfg.RepositoryConfig()
                rc.read(self.sample_conf)
                rc.write(self.sample_conf)

        def test_multi_read_write(self):
                """Verify that a RepositoryConfig object can be read and
                written multiple times in succession.
                """
                rc = rcfg.RepositoryConfig(pathname=self.sample_conf)
                rc.write(self.sample_conf)
                rc.read(self.sample_conf)
                rc.write(self.sample_conf)

        def test_get_attribute(self):
                """Verify that each attribute's value in sample_conf matches
                what we retrieved.
                """
                rc = rcfg.RepositoryConfig(pathname=self.sample_conf)

                attrs = self.__attrs
                for section in attrs:
                        for attr in attrs[section]:
                                returned = rc.get_attribute(section, attr)
                                self.assertEqual(returned,
                                    attrs[section][attr]["default"])

        def test_get_invalid_attribute(self):
                """Verify that attempting to retrieve an invalid attribute will
                result in an InvalidAttributeError exception.
                """
                rc = rcfg.RepositoryConfig()
                self.assertRaises(rcfg.InvalidAttributeError, rc.get_attribute,
                    "repository", "foo")

        def test_get_attribute_type(self):
                """Verify that each attribute's type matches the\
                default object state.
                """
                rc = rcfg.RepositoryConfig()
                attrs = self.__attrs
                for section in attrs:
                        for attr in attrs[section]:
                                returned = rc.get_attribute_type(section, attr)
                                expected = attrs[section][attr].get("type",
                                    rcfg.ATTR_TYPE_STR)
                                try:
                                        self.assertEqual(returned, expected)
                                except Exception, e:
                                        raise RuntimeError("An unexpected "
                                            "attribute type was returned for "
                                            "attribute '%s': '%s'")

        def test_get_attributes(self):
                """Verify that all expected attributes were returned by
                get_attributes and that each attribute returned can have its
                value retrieved.
                """
                rc = rcfg.RepositoryConfig()
                attrs = rc.get_attributes()
                self.assertEqual(len(attrs), len(self.__attrs))
                for section in attrs:
                        self.assertEqual(len(attrs[section]),
                            len(self.__attrs[section]))
                        for attr in attrs[section]:
                                rc.get_attribute(section, attr)

        def test_set_attribute(self):
                """Verify that each attribute can be set (unless read-only) and
                that the set value matches what we expect both before and after
                write().  Calling set for a read-only value should raise a
                ValueError exception.
                """
                fd, sample_conf = tempfile.mkstemp()
                rc = rcfg.RepositoryConfig()
                attrs = self.__attrs
                for section in attrs:
                        for attr in attrs[section]:
                                value = attrs[section][attr]["default"]
                                readonly = attrs[section][attr].get("readonly",
                                    False)
                                if readonly:
                                        self.assertRaises(
                                            rcfg.ReadOnlyAttributeError,
                                            rc.set_attribute, section, attr,
                                            value)
                                        rc._set_attribute(section, attr, value)
                                else:
                                        rc.set_attribute(section, attr, value)

                                returned = rc.get_attribute(section, attr)
                                self.assertEqual(returned, value)

                rc.write(sample_conf)

                rc = rcfg.RepositoryConfig(pathname=sample_conf)
                for section in attrs:
                        for attr in attrs[section]:
                                value = attrs[section][attr]["default"]
                                returned = rc.get_attribute(section, attr)
                                self.assertEqual(returned, value)

        def test_set_invalid_attribute(self):
                """Verify that attempting to set an invalid attribute will
                result in an InvalidAttributeError exception.
                """
                rc = rcfg.RepositoryConfig()
                # Verify an exception is raised for an invalid attribute.
                self.assertRaises(rcfg.InvalidAttributeError, rc.set_attribute,
                    "repository", "foo", "baz")

                # Verify that an exception is raised for an invalid section.
                self.assertRaises(rcfg.InvalidAttributeError, rc.set_attribute,
                    "bar", "id", None)

        def test__set_invalid_attribute(self):
                """Verify that attempting to _set an invalid attribute will
                result in an InvalidAttributeError exception.
                """
                rc = rcfg.RepositoryConfig()
                # Verify that it happens for an invalid attribute.
                self.assertRaises(rcfg.InvalidAttributeError,
                    rc.set_attribute, "repository", "foo", "bar")

                # Verify that it happens for an invalid section.
                self.assertRaises(rcfg.InvalidAttributeError,
                    rc._set_attribute, "bar", "id", "baz")

        def test_is_valid_attribute(self):
                """Verify that is_valid_attribute returns a boolean value
                indicating the validity of the attribute or raises an
                exception if raise_error=True and the attribute is
                invalid.
                """
                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute.
                self.assertFalse(rc.is_valid_attribute("repository", "foo"))

                # Verify that False is returned for an invalid attribute
                # section.
                self.assertFalse(rc.is_valid_attribute("bar", "foo"))

                # Verify that True is returned for a valid attribute.
                self.assertTrue(rc.is_valid_attribute("feed", "id"))

                # Verify that an exception is raised for an invalid attribute.
                self.assertRaises(rcfg.InvalidAttributeError,
                    rc.is_valid_attribute, "repository", "foo",
                    raise_error=True)

                # Verify that an exception is raised for an invalid attribute
                # section.
                self.assertRaises(rcfg.InvalidAttributeError,
                    rc.is_valid_attribute, "bar", "foo", raise_error=True)

        def test_is_valid_attribute_value(self):
                """Verify that is_valid_attribute_value returns a boolean value
                indicating the validity of the attribute value or raises an
                exception if raise_error=True and the attribute value is
                invalid.
                """
                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("feed", "window",
                    "foo"))

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("feed", "window",
                    24))

                # Verify that an exception is raised for an invalid attribute
                # value when raise_error=True.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "feed", "window", "foo",
                    raise_error=True)

        def test_is_valid_attribute_value_uuid(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of UUID attribute values.
                """
                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("feed", "id",
                    "8baf-433b-82eb-8c7fada847da"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "feed", "id",
                    "8baf-433b-82eb-8c7fada847da", raise_error=True)

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("feed", "id",
                    "16fd2706-8baf-433b-82eb-8c7fada847da"))

        def test_is_valid_attribute_value_bool(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of bool attribute values.
                """
                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for invalid attribute values.
                self.assertFalse(rc.is_valid_attribute_value("feed",
                    "enabled", "foo"))
                self.assertFalse(rc.is_valid_attribute_value("feed",
                    "enabled", "1"))
                self.assertFalse(rc.is_valid_attribute_value("feed",
                    "enabled", "0"))
                self.assertFalse(rc.is_valid_attribute_value("feed",
                    "enabled", "true"))
                self.assertFalse(rc.is_valid_attribute_value("feed",
                    "enabled", "false"))
                self.assertFalse(rc.is_valid_attribute_value("feed",
                    "enabled", ""))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "feed", "enabled", "",
                    raise_error=True)

                # Verify that True is returned for valid attribute values.
                self.assertTrue(rc.is_valid_attribute_value("feed",
                    "enabled", "True"))
                self.assertTrue(rc.is_valid_attribute_value("feed",
                    "enabled", True))
                self.assertTrue(rc.is_valid_attribute_value("feed",
                    "enabled", "False"))
                self.assertTrue(rc.is_valid_attribute_value("feed",
                    "enabled", False))

        def test_is_valid_attribute_value_uri(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of uri attribute values.
                """

                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("repository",
                    "registration_uri", "abc.123^@#$&)(*&#$)"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "repository",
                    "registration_uri",
                    "abc.123^@#$&)(*&#$)", raise_error=True)

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("repository",
                    "registration_uri", "https://pkg.sun.com/register"))

        def test_is_valid_attribute_value_uri_list(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of uri_list attribute
                values.
                """

                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("repository",
                    "mirrors", "http://example.com/mirror, abc.123^@#$&)(*&#$)"))
                self.assertFalse(rc.is_valid_attribute_value("repository",
                    "mirrors", ","))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "repository", "mirrors",
                    "example.com,example.net", raise_error=True)

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("repository",
                    "mirrors", ["http://example.com/mirror1",
                    "http://example.net/mirror2"]))

        def test_is_valid_attribute_value_pub_alias(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of publisher alias
                attribute values.
                """

                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("publisher",
                    "alias", "abc.123^@#$&)(*&#$)"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "publisher", "alias",
                    "abc.123^@#$&)(*&#$)", raise_error=True)

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("publisher",
                    "alias", "bobcat"))

        def test_is_valid_attribute_value_pub_prefix(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of publisher prefix
                attribute values.
                """

                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("publisher",
                    "prefix", "abc.123^@#$&)(*&#$)"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "publisher", "prefix",
                    "abc.123^@#$&)(*&#$)", raise_error=True)

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("publisher",
                    "prefix", "xkcd.net"))

        def test_is_valid_attribute_value_repo_coll_type(self):
                """Verify that is_valid_attribute_value returns the expected
                boolean value indicating the validity of repository collection
                type attribute values.
                """

                rc = rcfg.RepositoryConfig()
                # Verify that False is returned for an invalid attribute value.
                self.assertFalse(rc.is_valid_attribute_value("repository",
                    "collection_type", "donotwant"))

                # Verify that an exception is raised when raise_error=True for
                # an invalid attribute value.
                self.assertRaises(rcfg.InvalidAttributeValueError,
                    rc.is_valid_attribute_value, "repository",
                    "collection_type", "donotwant", raise_error=True)

                # Verify that True is returned for a valid attribute value.
                self.assertTrue(rc.is_valid_attribute_value("repository",
                    "collection_type", "supplemental"))

        def test_missing_conffile(self):
                """Verify that read() will raise an exception if a non-existent
                file is specified.
                """
                os.remove(self.sample_conf)
                rc = rcfg.RepositoryConfig()
                self.assertRaises(RuntimeError, rc.read, self.sample_conf)

if __name__ == "__main__":
        unittest.main()

