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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import ConfigParser
import pkg.misc as misc
import random
import uuid

PROP_TYPE_STR = 0
PROP_TYPE_INT = 1
PROP_TYPE_FLOAT = 2
PROP_TYPE_BOOL = 3
PROP_TYPE_UUID = 4
PROP_TYPE_URI = 5
PROP_TYPE_URI_LIST = 6
PROP_TYPE_PUB_ALIAS = 7
PROP_TYPE_PUB_PREFIX = 8
PROP_TYPE_REPO_COLL_TYPE = 9

class PropertyError(Exception):
        """Base exception class for property errors."""

        def __init__(self, *args):
                Exception.__init__(self, *args)


class InvalidPropertyError(PropertyError):
        """Exception class used to indicate an invalid property."""


class InvalidPropertyValueError(PropertyError):
        """Exception class used to indicate an invalid property value."""


class RequiredPropertyValueError(PropertyError):
        """Exception class used to indicate a required property value is
        missing."""


class ReadOnlyPropertyError(PropertyError):
        """Exception class used to indicate when an attempt to set a read-only
        value was made."""


class RepositoryConfig(object):
        """A RepositoryConfig object is a collection of configuration
        information and metadata for a repository.
        """

        # This data structure defines the list of possible properties for a
        # repository along with two optional properties: default and readonly.
        _props = {
            "publisher": {
                "alias": {
                    "type": PROP_TYPE_PUB_ALIAS,
                },
                "prefix": {
                    "type": PROP_TYPE_PUB_PREFIX,
                },
            },
            "repository": {
                "collection_type": {
                    "type": PROP_TYPE_REPO_COLL_TYPE,
                    "default": "core",
                },
                "description": {},
                "detailed_url": {
                    "type": PROP_TYPE_URI,
                    "default": "http://www.opensolaris.com"
                },
                "legal_uris": {
                    "type": PROP_TYPE_URI_LIST
                },
                "maintainer": {
                    "default":
                        "Project Indiana <indiana-discuss@opensolaris.org>"
                },
                "maintainer_url": {
                    "type": PROP_TYPE_URI,
                    "default": "http://www.opensolaris.org/os/project/indiana/"
                },
                "mirrors": {
                    "type": PROP_TYPE_URI_LIST
                },
                "name": {
                    "default": "package repository"
                },
                "origins": {
                    "type": PROP_TYPE_URI_LIST
                },
                "refresh_seconds": {
                    "type": PROP_TYPE_INT,
                    "default": 4 * 60 * 60, # default is 4 hours
                },
                "registration_uri": {
                    "type": PROP_TYPE_URI,
                },
                "related_uris": {
                    "type": PROP_TYPE_URI_LIST
                },
            },
            "feed": {
                "id": {
                    "type": PROP_TYPE_UUID,
                    "readonly": True,
                },
                "name": {
                    "default": "opensolaris.org repository feed"
                },
                "description": {},
                "icon": {
                    "default": "web/_themes/pkg-block-icon.png"
                },
                "logo": {
                    "default": "web/_themes/pkg-block-logo.png"
                },
                "window": {
                    "type": PROP_TYPE_INT,
                    "default": 24
                },
            },
        }

        def __init__(self, pathname=None, properties=misc.EmptyDict):
                """Initializes a RepositoryConfig object.

                Will read existing configuration data from pathname, if
                specified.
                """

                self.cfg_cache = {}
                self.nasty = 0

                if pathname:
                        # If a pathname was provided, read the data in.
                        self.read(pathname, overrides=properties)
                else:
                        # Otherwise, initialize to default state.
                        self.__reset(overrides=properties)

        def __str__(self):
                """Returns a string representation of the configuration
                object.
                """
                return "%s" % self.cfg_cache

        def __reset(self, overrides=misc.EmptyDict):
                """Returns the configuration object to its default state.
                """

                self.cfg_cache = {}
                for section in self._props:
                        sprops = self._props[section]
                        for prop in sprops:
                                info = sprops[prop]
                                default = info.get("default", None)

                                if section in overrides and \
                                    prop in overrides[section]:
                                        default = overrides[section][prop]

                                ptype = self.get_property_type(section, prop)
                                if default is None and \
                                    ptype == PROP_TYPE_URI_LIST:
                                        default = []

                                self.cfg_cache.setdefault(section, {})
                                self.cfg_cache[section][prop] = default

        @classmethod
        def is_valid_property(cls, section, prop, raise_error=False):
                """Returns a boolean indicating whether the given property
                is valid for the specified section.

                This function will raise an exception instead of returning a
                boolean is raise_error=True is specified.
                """
                if section not in cls._props:
                        if raise_error:
                                raise InvalidPropertyError("Invalid "
                                    " property. Unknown section: %s." % \
                                    (section))
                        else:
                                return False
                if prop not in cls._props[section]:
                        if raise_error:
                                raise InvalidPropertyError("Invalid "
                                    "property %s.%s." % \
                                    (section, prop))
                        else:
                                return False
                return True

        @classmethod
        def get_property_type(cls, section, prop):
                """Returns a numeric value indicating the data type of the
                given property for the specified section.

                The return value corresponds to one of the following module
                constants which matches a Python data type:
                    PROP_TYPE_STR               str
                    PROP_TYPE_INT               int
                    PROP_TYPE_FLOAT             float
                    PROP_TYPE_BOOL              boolean
                    PROP_TYPE_UUID              str
                    PROP_TYPE_URI               str
                    PROP_TYPE_URI_LIST          list of str
                    PROP_TYPE_PUB_ALIAS         str
                    PROP_TYPE_PUB_PREFIX        str
                    PROP_TYPE_REPO_COLL_TYPE    str
                """
                if cls.is_valid_property(section, prop, raise_error=True):
                        info = cls._props[section][prop]
                        return info.get("type", PROP_TYPE_STR)
                else:
                        return False

        @classmethod
        def is_valid_property_value(cls, section, prop, value,
            raise_error=False):
                """Returns a boolean indicating whether the given property
                value is valid for the specified section and property.

                This function will raise an exception instead of returning a
                boolean is raise_error=True is specified.
                """

                def validate_uri(uri):
                        try:
                                valid = misc.valid_pub_url(uri)
                        except KeyboardInterrupt:
                                raise
                        except:
                                valid = False

                        if not valid:
                                raise ValueError()

                if cls.is_valid_property(section, prop,
                    raise_error=raise_error):
                        ptype = cls.get_property_type(section, prop)
                        # If the type is string, we always assume it is valid.
                        # For all other types, we attempt a forced conversion
                        # of the value; if it fails, we know the value isn't
                        # valid for the given type.
                        try:
                                if ptype == PROP_TYPE_STR:
                                        return True
                                elif ptype == PROP_TYPE_INT:
                                        int(value)
                                elif ptype == PROP_TYPE_FLOAT:
                                        float(value)
                                elif ptype == PROP_TYPE_BOOL:
                                        if str(value) not in ("True", "False"):
                                                raise TypeError
                                elif ptype == PROP_TYPE_UUID:
                                        # None and '' are valid for
                                        # configuration purposes, even though
                                        # UUID would fail.
                                        if value not in (None, ""):
                                                uuid.UUID(hex=str(value))
                                elif ptype == PROP_TYPE_URI:
                                        if value in (None, ""):
                                                return True
                                        validate_uri(value)
                                elif ptype == PROP_TYPE_URI_LIST:
                                        if not isinstance(value, list):
                                                raise TypeError
                                        for u in value:
                                                validate_uri(u)
                                elif ptype in (PROP_TYPE_PUB_ALIAS,
                                    PROP_TYPE_PUB_PREFIX):
                                        # For now, alias is not required.
                                        if ptype == PROP_TYPE_PUB_ALIAS and \
                                            value in (None, ""):
                                                return True

                                        # The same rules that apply to publisher
                                        # prefixes also apply to aliases (for
                                        # now).
                                        if not misc.valid_pub_prefix(value):
                                                raise ValueError()
                                elif ptype == PROP_TYPE_REPO_COLL_TYPE:
                                        if str(value) not in ("core",
                                            "supplemental"):
                                                raise TypeError
                                else:
                                        raise RuntimeError(
                                            "Unknown property type: %s" % \
                                            ptype)
                        except (TypeError, ValueError, OverflowError):
                                if raise_error:
                                        if value in (None, ""):
                                                raise RequiredPropertyValueError(
                                                    "%s.%s is required." % \
                                                    (section, prop))
                                        raise InvalidPropertyValueError(
                                            "Invalid value '%s' for %s.%s." % \
                                            (value, section, prop))
                                else:
                                        return False
                else:
                        return False
                return True

        @classmethod
        def is_readonly_property(cls, section, prop):
                """Returns a boolean indicating whether the given property
                is read-only.
                """
                if cls.is_valid_property(section, prop, raise_error=True):
                        info = cls._props[section][prop]
                        return info.get("readonly", False)

        @classmethod
        def get_properties(cls):
                """Returns a dictionary of all property sections with each
                section's properties as a list.
                """
                return dict(
                    (section, [prop for prop in cls._props[section]])
                        for section in cls._props
                )

        def get_property(self, section, prop):
                """Returns the value of the specified property for the given
                section.
                """
                if self.is_valid_property(section, prop, raise_error=True):
                        return self.cfg_cache[section][prop]

        def _set_property(self, section, prop, value):
                """Sets the value of a given configuration property for the
                specified section.

                This method does not check the read-only status of an property
                and is intended for internal use.
                """
                self.is_valid_property_value(section, prop, value,
                    raise_error=True)

                ptype = self.get_property_type(section, prop)
                if ptype == PROP_TYPE_INT:
                        self.cfg_cache[section][prop] = int(value)
                elif ptype == PROP_TYPE_FLOAT:
                        self.cfg_cache[section][prop] = float(value)
                elif ptype == PROP_TYPE_BOOL:
                        if str(value) == "True":
                                self.cfg_cache[section][prop] = True
                        else:
                                self.cfg_cache[section][prop] = False
                else:
                        # Treat all remaining types as a simple value.
                        self.cfg_cache[section][prop] = value

        def set_property(self, section, prop, value):
                """Sets a given configuration property to the specified
                value for the specified section.

                This function will raise an exception if the specified
                property is read-only.
                """
                if not self.is_readonly_property(section, prop):
                        return self._set_property(section, prop, value)
                else:
                        raise ReadOnlyPropertyError("%s.%s is read-only." % \
                            (prop, section))

        def read(self, pathname, overrides=misc.EmptyDict):
                """Reads the specified pathname and populates the configuration
                object based on the data contained within.  The file is
                expected to be in a ConfigParser-compatible format.
                """

                # Reset to initial state to ensure we only have default values
                # so that any values not overwritten by the saved configuration
                # will be correct.
                self.__reset()

                cp = ConfigParser.SafeConfigParser()

                r = cp.read(pathname)
                if len(r) == 0:
                        raise RuntimeError(_("Unable to locate or read the "
                            "specified repository configuration file: "
                            "'%s'.") % pathname)

                assert r[0] == pathname
                for section in self._props:
                        for prop in self._props[section]:
                                ptype = self.get_property_type(section, prop)
                                try:
                                        if section in overrides and \
                                            prop in overrides[section]:
                                                val = overrides[section][prop]
                                                cp.set(section, prop, str(val))

                                        # Retrieve the value as a string first
                                        # to prevent ConfigParser from causing
                                        # an exception.
                                        value = cp.get(section, prop)

                                        # The list types are special in that
                                        # they must be converted first before
                                        # validation.
                                        if ptype == PROP_TYPE_URI_LIST:
                                                uris = []
                                                for u in value.split(","):
                                                        if u:
                                                                uris.append(u)
                                                value = uris

                                        self.is_valid_property_value(
                                            section, prop, value,
                                            raise_error=True)

                                        if ptype == PROP_TYPE_INT:
                                                value = cp.getint(section,
                                                    prop)
                                        elif ptype == PROP_TYPE_FLOAT:
                                                value = cp.getfloat(section,
                                                    prop)
                                        elif ptype == PROP_TYPE_BOOL:
                                                value = cp.getboolean(section,
                                                    prop)

                                        self.cfg_cache[section][prop] = value

                                except (ConfigParser.NoSectionError,
                                    ConfigParser.NoOptionError):
                                        # Skip any missing properties.
                                        continue

        def write(self, pathname):
                """Saves the current configuration object to the specified
                pathname using ConfigParser.
                """
                cp = ConfigParser.SafeConfigParser()

                for section in self._props:
                        cp.add_section(section)
                        for prop in self._props[section]:
                                value = self.cfg_cache[section][prop]

                                ptype = self.get_property_type(section, prop)
                                if ptype == PROP_TYPE_URI_LIST:
                                        value = ",".join(value)

                                if value is not None:
                                        cp.set(section, prop, str(value))
                                else:
                                        # Force None to be an empty string.
                                        cp.set(section, prop, "")

                try:
                        f = open(pathname, "w")
                except IOError, (errno, strerror):
                        raise RuntimeError("Unable to open %s for writing: "
                            "%s" % (pathname, strerror))
                cp.write(f)

        def validate(self):
                """Verify that the in-memory contents of the configuration
                satisfy validation requirements (such as required fields)."""

                for section in self._props:
                        for prop in self._props[section]:
                                value = self.cfg_cache.get(section,
                                    {}).get(prop)
                                ptype = self.get_property_type(section, prop)
                                self.is_valid_property_value(
                                    section, prop, value,
                                    raise_error=True)

        def set_nasty(self, level):
                """Set the nasty level using an integer."""

                self.nasty = level

        def is_nasty(self):
                """Returns true if nasty has been enabled."""

                if self.nasty > 0:
                        return True
                return False

        def need_nasty(self):
                """Randomly returns true when the server should misbehave."""

                if random.randint(1, 100) <= self.nasty:
                        return True
                return False

        def need_nasty_bonus(self, bonus=0):
                """Used to temporarily apply extra nastiness to an operation."""

                if self.nasty + bonus > 95:
                        nasty = 95
                else:
                        nasty = self.nasty + bonus

                if random.randint(1, 100) <= nasty:
                        return True
                return False

        def need_nasty_occasionally(self):
                if random.randint(1, 500) <= self.nasty:
                        return True
                return False

        def need_nasty_infrequently(self):
                if random.randint(1, 2000) <= self.nasty:
                        return True
                return False

        def need_nasty_rarely(self):
                if random.randint(1, 20000) <= self.nasty:
                        return True
                return False
