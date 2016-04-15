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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""The pkg.config module provides a set of classes for managing both 'flat'
(single-level) and 'structured' (n-level deep) configuration data that may
be stored in memory, on disk, or using an smf(5) service instance.

The basic structure of the classes found here is roughly as follows:

Configuration Class (e.g. Config)
  Provides storage and retrieval of property sections and properties via
  its child property sections.

    Section Class (e.g. PropertySection)
      Provides storage and retrieval of property data via its child properties.

      Property Class
        Provides storage and retrieval of property data.

Generally, consumers should only need to consume the interfaces provided by the
Config class or its subclasses.   However, any public method or property of the
property sections or property objects can be used as well if advanced access or
manipulation of configuration data is needed.
"""

from __future__ import print_function
import ast
import codecs
import copy
import errno
import os
import re
import shlex
import six
import stat
import subprocess
import tempfile
import uuid
from collections import OrderedDict
from six import python_2_unicode_compatible
from six.moves import configparser

from pkg import misc, portable
import pkg.version
import pkg.client.api_errors as api_errors


class ConfigError(api_errors.ApiException):
        """Base exception class for property errors."""


class PropertyConfigError(ConfigError):
        """Base exception class for property errors."""

        def __init__(self, section=None, prop=None):
                api_errors.ApiException.__init__(self)
                assert section is not None or prop is not None
                self.section = section
                self.prop = prop


class InvalidPropertyNameError(PropertyConfigError):
        """Exception class used to indicate an invalid property name."""

        def __init__(self, prop):
                assert prop is not None
                PropertyConfigError.__init__(self, prop=prop)

        def __str__(self):
                return _("Property name '{0}' is not valid.  Section names "
                    "may not contain: tabs, newlines, carriage returns, "
                    "form feeds, vertical tabs, slashes, backslashes, or "
                    "non-ASCII characters.").format(self.prop)


class InvalidPropertyTemplateNameError(PropertyConfigError):
        """Exception class used to indicate an invalid property template name.
        """

        def __init__(self, prop):
                assert prop is not None
                PropertyConfigError.__init__(self, prop=prop)

        def __str__(self):
                return _("Property template name '{0}' is not valid.").format(
                    self.prop)


class InvalidPropertyValueError(PropertyConfigError):
        """Exception class used to indicate an invalid property value."""

        def __init__(self, maximum=None, minimum=None, section=None, prop=None,
            value=None):
                PropertyConfigError.__init__(self, section=section, prop=prop)
                assert not (minimum is not None and maximum is not None)
                self.maximum = maximum
                self.minimum = minimum
                self.value = value

        def __str__(self):
                if self.minimum is not None:
                        return _("'{value}' is less than the minimum "
                            "of '{minimum}' permitted for property "
                            "'{prop}' in section '{section}'.").format(
                            **self.__dict__)
                if self.maximum is not None:
                        return _("'{value}' is greater than the maximum "
                            "of '{maximum}' permitted for property "
                            "'{prop}' in section '{section}'.").format(
                            **self.__dict__)
                if self.section:
                        return _("Invalid value '{value}' for property "
                            "'{prop}' in section '{section}'.").format(
                            **self.__dict__)
                return _("Invalid value '{value}' for {prop}.").format(
                    **self.__dict__)


class PropertyMultiValueError(InvalidPropertyValueError):
        """Exception class used to indicate the property in question doesn't
        allow multiple values."""

        def __str__(self):
                if self.section:
                        return _("Property '{prop}' in section '{section}' "
                            "doesn't allow multiple values.").format(
                            **self.__dict__)
                return _("Property {0} doesn't allow multiple values.").format(
                    self.prop)


class UnknownPropertyValueError(PropertyConfigError):
        """Exception class used to indicate that the value specified
        could not be found in the property's list of values."""

        def __init__(self, section=None, prop=None, value=None):
                PropertyConfigError.__init__(self, section=section, prop=prop)
                self.value = value

        def __str__(self):
                if self.section:
                        return _("Value '{value}' not found in the list of "
                            "values for property '{prop}' in section "
                            "'{section}'.").format(**self.__dict__)
                return _("Value '{value}' not found in the list of values "
                    "for {prop} .").format(**self.__dict__)


class InvalidSectionNameError(PropertyConfigError):
        """Exception class used to indicate an invalid section name."""

        def __init__(self, section):
                assert section is not None
                PropertyConfigError.__init__(self, section=section)

        def __str__(self):
                return _("Section name '{0}' is not valid.  Section names "
                    "may not contain: tabs, newlines, carriage returns, "
                    "form feeds, vertical tabs, slashes, backslashes, or "
                    "non-ASCII characters.").format(self.section)


class InvalidSectionTemplateNameError(PropertyConfigError):
        """Exception class used to indicate an invalid section template name."""

        def __init__(self, section):
                assert section is not None
                PropertyConfigError.__init__(self, section=section)

        def __str__(self):
                return _("Section template name '{0}' is not valid.").format(
                    self.section)


class UnknownPropertyError(PropertyConfigError):
        """Exception class used to indicate an invalid property."""

        def __str__(self):
                if self.section:
                        return _("Unknown property '{prop}' in section "
                            "'{section}'.").format(**self.__dict__)
                return _("Unknown property {0}").format(self.prop)


class UnknownSectionError(PropertyConfigError):
        """Exception class used to indicate an invalid section."""

        def __str__(self):
                return _("Unknown property section: {0}.").format(
                    self.section)


@python_2_unicode_compatible
class Property(object):
        """Base class for properties."""

        # Whitespace, '/', and '\' are never allowed.
        __name_re = re.compile(r"\A[^\t\n\r\f\v\\/]+\Z")

        _value = None
        _value_map = misc.EmptyDict

        def __init__(self, name, default="", value_map=misc.EmptyDict):
                if not isinstance(name, six.string_types) or \
                    not self.__name_re.match(name):
                        raise InvalidPropertyNameError(prop=name)
                try:
                        name.encode("ascii")
                except ValueError:
                        # Name contains non-ASCII characters.
                        raise InvalidPropertyNameError(prop=name)
                self.__name = name

                # Last, set the property's initial value.
                self.value = default
                self._value_map = value_map

        def __lt__(self, other):
                if not isinstance(other, Property):
                        return True
                return self.name < other.name

        def __gt__(self, other):
                if not isinstance(other, Property):
                        return False
                return self.name > other.name

        def __le__(self, other):
                return self == other or self < other

        def __ge__(self, other):
                return self == other or self > other

        def __eq__(self, other):
                if not isinstance(other, Property):
                        return False
                if self.name != other.name:
                        return False
                return self.value == other.value

        def __ne__(self, other):
                if not isinstance(other, Property):
                        return True
                if self.name != other.name:
                        return True
                return self.value != other.value

        def __hash__(self):
                return hash((self.name, self.value))

        def __copy__(self):
                return self.__class__(self.name, default=self.value,
                    value_map=self._value_map)

        def __str__(self):
                # Assume that value can be represented in utf-8.
                return misc.force_text(self.value)

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """
                if not isinstance(value, six.string_types):
                        # Only string values are allowed.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)

        def _transform_string(self, value):
                # Transform encoded UTF-8 data into unicode objects if needed.
                if isinstance(value, bytes):
                        # Automatically transform encoded UTF-8 data into
                        # unicode objects if needed.
                        try:
                                value = value.encode("ascii")
                        except ValueError:
                                try:
                                        value = value.decode("utf-8")
                                except ValueError:
                                        # Assume sequence of arbitrary
                                        # 8-bit data.
                                        pass
                return value

        @property
        def name(self):
                """The name of the property."""
                return self.__name

        @property
        def value(self):
                """The value of the property."""
                return self._value

        @value.setter
        def value(self, value):
                """Sets the property's value."""
                if isinstance(value, six.string_types):
                        value = self._value_map.get(value, value)
                if value is None:
                        value = ""
                elif isinstance(value, (bool, int)):
                        value = str(value)
                else:
                        value = self._transform_string(value)
                self._is_allowed(value)
                self._value = value


class PropertyTemplate(object):
        """A class representing a template for a property.  These templates are
        used when loading existing configuration data or when adding new
        properties to an existing configuration object if the property name
        found matches the pattern name given for the template.
        """

        def __init__(self, name_pattern, allowed=None, default=None,
            prop_type=Property, value_map=None):
                assert prop_type
                if not isinstance(name_pattern, six.string_types) or not name_pattern:
                        raise InvalidPropertyTemplateNameError(
                            prop=name_pattern)
                self.__name = name_pattern
                try:
                        self.__pattern = re.compile(name_pattern)
                except Exception:
                        # Unfortunately, python doesn't have a public exception
                        # class to catch re parse issues; but this only happens
                        # for misbehaved programs anyway.
                        raise InvalidPropertyTemplateNameError(
                            prop=name_pattern)

                self.__allowed = allowed
                self.__default = default
                self.__prop_type = prop_type
                self.__value_map = value_map

        def __copy__(self):
                return self.__class__(self.__name, allowed=self.__allowed,
                    default=self.__default, prop_type=self.__prop_type,
                    value_map=self.__value_map)

        def create(self, name):
                """Returns a new PropertySection object based on the template
                using the given name.
                """
                assert self.match(name)
                pargs = {}
                if self.__allowed is not None:
                        pargs["allowed"] = self.__allowed
                if self.__default is not None:
                        pargs["default"] = self.__default
                if self.__value_map is not None:
                        pargs["value_map"] = self.__value_map
                return self.__prop_type(name, **pargs)

        def match(self, name):
                """Returns a boolean indicating whether the given name matches
                the pattern for this template.
                """
                return self.__pattern.match(name) is not None

        @property
        def name(self):
                """The name (pattern string) of the property template."""
                # Must return a string.
                return self.__name


class PropBool(Property):
        """Class representing properties with a boolean value."""

        def __init__(self, name, default=False, value_map=misc.EmptyDict):
                Property.__init__(self, name, default=default,
                    value_map=value_map)

        @Property.value.setter
        def value(self, value):
                if isinstance(value, six.string_types):
                        value = self._value_map.get(value, value)
                if value is None or value == "":
                        self._value = False
                        return
                elif isinstance(value, six.string_types):
                        if value.lower() == "true":
                                self._value = True
                                return
                        elif value.lower() == "false":
                                self._value = False
                                return
                elif isinstance(value, bool):
                        self._value = value
                        return
                raise InvalidPropertyValueError(prop=self.name, value=value)


class PropInt(Property):
        """Class representing a property with an integer value."""

        def __init__(self, name, default=0, maximum=None,
            minimum=0, value_map=misc.EmptyDict):
                assert minimum is None or type(minimum) == int
                assert maximum is None or type(maximum) == int
                self.__maximum = maximum
                self.__minimum = minimum
                Property.__init__(self, name, default=default,
                    value_map=value_map)

        def __copy__(self):
                prop = Property.__copy__(self)
                prop.__maximum = self.__maximum
                prop.__minimum = self.__minimum
                return prop

        @property
        def minimum(self):
                """Minimum value permitted for this property or None."""
                return self.__minimum

        @property
        def maximum(self):
                """Maximum value permitted for this property or None."""
                return self.__maximum

        @Property.value.setter
        def value(self, value):
                if isinstance(value, six.string_types):
                        value = self._value_map.get(value, value)
                if value is None or value == "":
                        value = 0

                try:
                        nvalue = int(value)
                except Exception:
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)

                if self.minimum is not None and nvalue < self.minimum:
                        raise InvalidPropertyValueError(prop=self.name,
                            minimum=self.minimum, value=value)
                if self.maximum is not None and nvalue > self.maximum:
                        raise InvalidPropertyValueError(prop=self.name,
                            maximum=self.maximum, value=value)
                self._value = nvalue


class PropPublisher(Property):
        """Class representing properties with a publisher prefix/alias value."""

        @Property.value.setter
        def value(self, value):
                if isinstance(value, six.string_types):
                        value = self._value_map.get(value, value)
                if value is None or value == "":
                        self._value = ""
                        return

                if not isinstance(value, six.string_types) or \
                    not misc.valid_pub_prefix(value):
                        # Only string values are allowed.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)
                self._value = value


class PropDefined(Property):
        """Class representing properties with that can only have one of a set
        of pre-defined values."""

        def __init__(self, name, allowed=misc.EmptyI, default="",
            value_map=misc.EmptyDict):
                self.__allowed = allowed
                Property.__init__(self, name, default=default,
                    value_map=value_map)

        def __copy__(self):
                prop = Property.__copy__(self)
                prop.__allowed = copy.copy(self.__allowed)
                return prop

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                Property._is_allowed(self, value)

                if len(self.__allowed) == 0:
                        return

                for a in self.__allowed:
                        if value == a:
                                break
                        if a == "<exec:pathname>" and \
                            value.startswith("exec:") and \
                            len(value) > 5:
                                # Don't try to determine if path is valid;
                                # just that the value starts with 'exec:'.
                                break
                        if a == "<smffmri>" and value.startswith("svc:") and \
                            len(value) > 4:
                                # Don't try to determine if FMRI is valid;
                                # just that the value starts with 'svc:'.
                                break
                        if a == "<abspathname>" and os.path.isabs(value):
                                break
                        if a == "<pathname>" and len(value) > 1:
                                # Don't try to determine if path is valid;
                                # just that the length is greater than 1.
                                break
                else:
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)

        @property
        def allowed(self):
                """A list of allowed values for this property."""
                return self.__allowed

class PropList(PropDefined):
        """Class representing properties with a list of string values that may
        contain arbitrary character data.
        """

        def _parse_str(self, value):
                """Parse the provided python string literal and return the
                resulting data structure."""
                try:
                        value = ast.literal_eval(value)
                except (SyntaxError, ValueError):
                        # ast raises ValueError if input isn't safe or
                        # valid.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)
                return value

        @PropDefined.value.setter
        def value(self, value):
                # the value can be arbitrary 8-bit data, so we allow bytes here
                if isinstance(value, (six.string_types, bytes)):
                        value = self._value_map.get(value, value)
                if value is None or value == "":
                        value = []
                elif isinstance(value, (six.string_types, bytes)):
                        value = self._parse_str(value)
                        if not isinstance(value, list):
                                # Only accept lists for literal string form.
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                else:
                        try:
                                iter(value)
                        except TypeError:
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)

                nvalue = []
                for v in value:
                        if v is None:
                                v = ""
                        elif isinstance(v, (bool, int)):
                                v = str(v)
                        elif not isinstance(v, six.string_types):
                                # Only string values are allowed.
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                        self._is_allowed(v)
                        nvalue.append(v)

                if self.allowed and "" not in self.allowed and not len(nvalue):
                        raise InvalidPropertyValueError(prop=self.name,
                            value=nvalue)

                self._value = nvalue


class PropDictionaryList(PropList):
        """Class representing properties with a value specified as a list of
        dictionaries. Each dictionary must contain string key/value pairs, or
        a string key, with None as a value.
        """

        @PropDefined.value.setter
        def value(self, value):
                if isinstance(value, six.string_types):
                        value = self._value_map.get(value, value)
                if value is None or value == "":
                        value = []
                elif isinstance(value, six.string_types):
                        value = self._parse_str(value)
                        if not isinstance(value, list):
                                # Only accept lists for literal string form.
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                else:
                        try:
                                iter(value)
                        except TypeError:
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)

                self._is_allowed(value)
                nvalue = []
                for v in value:
                        if v is None:
                                v = {}
                        elif not isinstance(v, dict):
                                # Only dict values are allowed.
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                        for item in v:
                                # we allow None values, but always store them
                                # as an empty string to prevent them getting
                                # serialised as "None"
                                if not v[item]:
                                        v[item] = ""
                        nvalue.append(v)

                # if we don't allow an empty list, raise an error
                if self.allowed and "" not in self.allowed and not len(nvalue):
                        raise InvalidPropertyValueError(prop=self.name,
                            value=nvalue)
                self._value = nvalue

        def _is_allowed(self, value):
                if not isinstance(value, list):
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)

                # ensure that we only have dictionary values
                for dic in value:
                        if not isinstance(dic, dict):
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)

                if not self.allowed:
                        return

                # ensure that each dictionary in the value is allowed
                for dic in value:
                        if not isinstance(dic, dict):
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                        if dic not in self.allowed:
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                        for key, val in dic.items():
                                Property._is_allowed(self, key)
                                if not val:
                                        continue
                                Property._is_allowed(self, val)

@python_2_unicode_compatible
class PropSimpleList(PropList):
        """Class representing a property with a list of string values that are
        simple in nature.  Output is in a comma-separated format that may not
        be suitable for some datasets such as those containing arbitrary data,
        newlines, commas or that may contain zero-length strings.  This class
        exists for compatibility with older configuration files that stored
        lists of data in this format and should not be used for new consumers.
        """

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                PropList._is_allowed(self, value)

                if isinstance(value, bytes):
                        try:
                                value.decode("utf-8")
                        except ValueError:
                                # Arbitrary 8-bit data not supported for simple
                                # lists.
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)

        def _parse_str(self, value):
                """Parse the provided list string and return it as a list."""
                # Automatically transform encoded UTF-8 data into Unicode
                # objects if needed.  This results in ASCII data being
                # stored using str() objects, and UTF-8 data using
                # unicode() objects. In Python 3, we just want UTF-8 data
                # using str(unicode) objects.
                result = []
                if isinstance(value, bytes):
                        value = value.split(b",")
                else:
                        value = value.split(",")
                for v in value:
                        try:
                                if six.PY2:
                                        v = v.encode("ascii")
                                else:
                                        v= misc.force_str(v)
                        except ValueError:
                                if not isinstance(v, six.text_type):
                                        try:
                                                v = v.decode("utf-8")
                                        except ValueError:
                                                # Arbitrary 8-bit data not
                                                # supported for simple lists.
                                                raise InvalidPropertyValueError(
                                                    prop=self.name,
                                                    value=value)
                        result.append(v)
                return result

        def __str__(self):
                if self.value and len(self.value):
                        # Performing the join using a unicode string results in
                        # a single unicode string object.
                        return u",".join(self.value)
                return u""


class PropPubURI(Property):
        """Class representing publisher URI properties."""

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                Property._is_allowed(self, value)

                if value == "":
                        return

                valid = misc.valid_pub_url(value)
                if not valid:
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)


class PropSimplePubURIList(PropSimpleList):
        """Class representing a property for a list of publisher URIs.  Output
        is in a basic comma-separated format that may not be suitable for some
        datasets.  This class exists for compatibility with older configuration
        files that stored lists of data in this format and should not be used
        for new consumers.
        """

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                PropSimpleList._is_allowed(self, value)

                valid = misc.valid_pub_url(value)
                if not valid:
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)


class PropPubURIList(PropList):
        """Class representing a property for a list of publisher URIs."""

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                PropList._is_allowed(self, value)

                valid = misc.valid_pub_url(value)
                if not valid:
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)


class PropPubURIDictionaryList(PropDictionaryList):
        """Class representing a list of values associated with a given publisher
        URI.

        A PropPubURIDictionaryList contains a series of dictionaries, where
        each dictionary must have a "uri" key with a valid URI as a value.

        eg.

        [ {'uri':'http://foo',
           'proxy': 'http://foo-proxy'},
          {'uri': 'http://bar',
           'proxy': http://bar-proxy'}
         ... ]
        """

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                PropDictionaryList._is_allowed(self, value)

                for dic in value:
                        if 'uri' not in dic:
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                        if not misc.valid_pub_url(dic["uri"]):
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)


class PropUUID(Property):
        """Class representing a Universally Unique Identifier property."""

        def _is_allowed(self, value):
                if value == "":
                        return

                try:
                        uuid.UUID(hex=str(value))
                except Exception:
                        # Not a valid UUID.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)


class PropVersion(Property):
        """Class representing a property with a non-negative integer dotsequence
        value."""

        def __init__(self, name, default="0", value_map=misc.EmptyDict):
                Property.__init__(self, name, default=default,
                    value_map=value_map)

        def __str__(self):
                return self.value.get_short_version()

        @Property.value.setter
        def value(self, value):
                if isinstance(value, six.string_types):
                        value = self._value_map.get(value, value)
                if value is None or value == "":
                        value = "0"

                if isinstance(value, pkg.version.Version):
                        nvalue = value
                else:
                        try:
                                nvalue = pkg.version.Version(value)
                        except Exception:
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)

                self._value = nvalue


@python_2_unicode_compatible
class PropertySection(object):
        """A class representing a section of the configuration that also
        provides an interface for adding and managing properties and sections
        for the section."""

        # Whitespace, '/', and '\' are never allowed although consumers can
        # place additional restrictions by providing a name re.  In addition,
        # the name "CONFIGURATION" is reserved for use by the configuration
        # serialization classes.
        __name_re = re.compile(r"\A[^\t\n\r\f\v\\/]+\Z")

        def __init__(self, name, properties=misc.EmptyI):
                if not isinstance(name, six.string_types) or \
                    not self.__name_re.match(name) or \
                    name == "CONFIGURATION":
                        raise InvalidSectionNameError(name)
                try:
                        name.encode("ascii")
                except ValueError:
                        # Name contains non-ASCII characters.
                        raise InvalidSectionNameError(name)
                self.__name = name

                # Should be set last.
                # Dict is in arbitrary order, sort it first to ensure the
                # order is same in Python 2 and 3.
                self.__properties = OrderedDict((p.name, p) for p in properties)

        def __lt__(self, other):
                if not isinstance(other, PropertySection):
                        return True
                return self.name < other.name

        def __gt__(self, other):
                if not isinstance(other, PropertySection):
                        return False
                return self.name > other.name

        def __eq__(self, other):
                if not isinstance(other, PropertySection):
                        return False
                return self.name == other.name

        def __hash__(self):
                return hash(self.name)

        def __copy__(self):
                propsec = self.__class__(self.__name)
                for p in self.get_properties():
                        propsec.add_property(copy.copy(p))
                return propsec

        def __str__(self):
                return six.text_type(self.name)

        def add_property(self, prop):
                """Adds the specified property object to the section.  The
                property must not already exist."""
                assert prop.name not in self.__properties
                self.__properties[prop.name] = prop
                return prop

        def get_index(self):
                """Returns a dictionary of property values indexed by property
                name."""
                return dict(
                    (pname, p.value)
                    for pname, p in six.iteritems(self.__properties)
                    if hasattr(p, "value")
                )

        def get_property(self, name):
                """Returns the property object with the specified name.  If
                not found, an UnknownPropertyError will be raised."""
                try:
                        return self.__properties[name]
                except KeyError:
                        raise UnknownPropertyError(section=self.__name,
                            prop=name)

        def get_properties(self):
                """Returns a generator that yields the list of property objects.
                """
                return six.itervalues(self.__properties)

        def remove_property(self, name):
                """Removes any matching property object from the section."""
                try:
                        del self.__properties[name]
                except KeyError:
                        raise UnknownPropertyError(section=self.__name,
                            prop=name)

        @property
        def name(self):
                """The name of the section."""
                return self.__name


class PropertySectionTemplate(object):
        """A class representing a template for a section of the configuration.
        These templates are used when loading existing configuration data
        or when adding new sections to an existing configuration object if
        the section name found matches the pattern name given for the template.
        """

        def __init__(self, name_pattern, properties=misc.EmptyI):
                if not isinstance(name_pattern, six.string_types) or not name_pattern:
                        raise InvalidSectionTemplateNameError(
                            section=name_pattern)
                self.__name = name_pattern
                try:
                        self.__pattern = re.compile(name_pattern)
                except Exception:
                        # Unfortunately, python doesn't have a public exception
                        # class to catch re parse issues; but this only happens
                        # for misbehaved programs anyway.
                        raise InvalidSectionTemplateNameError(
                            section=name_pattern)
                self.__properties = properties

        def __copy__(self):
                return self.__class__(self.__name,
                    properties=copy.copy(self.__properties))

        def create(self, name):
                """Returns a new PropertySection object based on the template
                using the given name.
                """
                assert self.match(name)
                # A *copy* of the properties must be used to construct the new
                # section; otherwise all sections created by this template will
                # share the same property *objects* (which is bad).
                return PropertySection(name, properties=[
                    copy.copy(p) for p in self.__properties
                ])

        def match(self, name):
                """Returns a boolean indicating whether the given name matches
                the pattern for this template.
                """
                return self.__pattern.match(name) is not None

        @property
        def name(self):
                """The name (pattern text) of the property section template."""
                # Must return a string.
                return self.__name


@python_2_unicode_compatible
class Config(object):
        """The Config class provides basic in-memory management of configuration
        data."""

        _dirty = False
        _target = None

        def __init__(self, definitions=misc.EmptyDict, overrides=misc.EmptyDict,
            version=None):
                """Initializes a Config object.

                'definitions' is a dictionary of PropertySection objects indexed
                by configuration version defining the initial set of property
                sections, properties, and values for a Config object.

                'overrides' is an optional dictionary of property values indexed
                by section name and property name.  If provided, it will be used
                to override any default values initially assigned during
                initialization.

                'version' is an integer value that will be used to determine
                which configuration definition to use.  If not provided, the
                newest version found in 'definitions' will be used.
                """

                assert version is None or isinstance(version, int)

                self.__sections = OrderedDict()
                self._defs = definitions
                if version is None:
                        if definitions:
                                version = max(definitions.keys())
                        else:
                                version = 0
                self._version = version
                self.reset(overrides=overrides)

        def __str__(self):
                """Returns a unicode object representation of the configuration
                object.
                """
                out = u""
                for sec, props in self.get_properties():
                        out += u"[{0}]\n".format(sec.name)
                        for p in props:
                                out += u"{0} = {1}\n".format(p.name, six.text_type(p))
                        out += u"\n"
                return out

        def _get_matching_property(self, section, name, default_type=Property):
                """Returns the Property object matching the given name for
                the given PropertySection object, or adds a new one (if it
                does not already exist) based on class definitions.

                'default_type' is an optional parameter specifying the type of
                property to create if a class definition does not exist for the
                given property.
                """

                self._validate_section_name(section)
                self._validate_property_name(name)

                try:
                        secobj = self.get_section(section)
                except UnknownSectionError:
                        # Get a copy of the definition for this section.
                        secobj = self.__get_section_def(section)

                        # Elide property templates.
                        elide = [
                            p.name for p in secobj.get_properties()
                            if not isinstance(p, Property)
                        ]
                        # force map() to process elements
                        list(map(secobj.remove_property, elide))
                        self.add_section(secobj)

                try:
                        return secobj.get_property(name)
                except UnknownPropertyError:
                        # See if there is an existing definition for this
                        # property; if there is, duplicate it, and add it
                        # to the section.
                        secdef = self.__get_section_def(secobj.name)
                        propobj = self.__get_property_def(secdef, name,
                            default_type=default_type)
                        secobj.add_property(propobj)
                        return propobj

        # Subclasses can redefine these to impose additional restrictions on
        # section and property names.  These methods should return if the name
        # is valid, or raise an exception if it is not.  These methods are only
        # used during __init__, add_section, reset, set_property, and write.
        def _validate_property_name(self, name):
                """Raises an exception if property name is not valid for this
                class.
                """
                pass

        def _validate_section_name(self, name):
                """Raises an exception if section name is not valid for this
                class.
                """
                pass

        def __get_property_def(self, secdef, name, default_type=Property):
                """Returns a new Property object for the given name based on
                class definitions (if available).
                """

                try:
                        propobj = secdef.get_property(name)
                        return copy.copy(propobj)
                except UnknownPropertyError:
                        # No specific definition found for this section,
                        # see if there is a suitable template for creating
                        # one.
                        for p in secdef.get_properties():
                                if not isinstance(p, PropertyTemplate):
                                        continue
                                if p.match(name):
                                        return p.create(name)

                        # Not a known property; create a new one using
                        # the default type.
                        return default_type(name)

        def __get_section_def(self, name):
                """Returns a new PropertySection object for the given name based
                on class definitions (if available).
                """

                # See if there is an existing definition for this
                # section; if there is, return a copy.
                for s in self._defs.get(self._version, misc.EmptyDict):
                        if not isinstance(s, PropertySection):
                                # Ignore section templates.
                                continue
                        if s.name == name:
                                return copy.copy(s)
                else:
                        # No specific definition found for this section,
                        # see if there is a suitable template for creating
                        # one.
                        for s in self._defs.get(self._version,
                            misc.EmptyDict):
                                if not isinstance(s,
                                    PropertySectionTemplate):
                                        continue
                                if s.match(name):
                                        return s.create(name)
                return PropertySection(name)

        def __reset(self, overrides=misc.EmptyDict):
                """Returns the configuration object to its default state."""
                self.__sections = OrderedDict()
                for s in self._defs.get(self._version, misc.EmptyDict):
                        if not isinstance(s, PropertySection):
                                # Templates should be skipped during reset.
                                continue
                        self._validate_section_name(s.name)

                        # Elide property templates.
                        secobj = copy.copy(s)
                        elide = [
                            p.name for p in secobj.get_properties()
                            if not isinstance(p, Property)
                        ]
                        list(map(secobj.remove_property, elide))
                        self.add_section(secobj)

                for sname, props in six.iteritems(overrides):
                        for pname, val in six.iteritems(props):
                                self.set_property(sname, pname, val)

        def add_property_value(self, section, name, value):
                """Adds the value to the property object matching the given
                section and name.  If the section or property does not already
                exist, it will be added.  Raises InvalidPropertyValueError if
                the value is not valid for the given property or if the target
                property isn't a list."""

                propobj = self._get_matching_property(section, name,
                    default_type=PropList)
                if not isinstance(propobj.value, list):
                        raise PropertyMultiValueError(section=section,
                            prop=name, value=value)

                # If a value was just appended directly, the property class
                # set method wouldn't be executed and the value added wouldn't
                # get verified, so append to a copy of the property's value and
                # then set the property to the new value.  This allows the new
                # value to be verified and/or rejected without affecting the
                # property.
                pval = copy.copy(propobj.value)
                pval.append(value)
                try:
                        propobj.value = pval
                except PropertyConfigError as e:
                        if hasattr(e, "section") and not e.section:
                                e.section = section
                        raise
                self._dirty = True

        def add_section(self, section):
                """Adds the specified property section object.  The section must
                not already exist.
                """
                assert isinstance(section, PropertySection)
                assert section.name not in self.__sections
                self._validate_section_name(section.name)
                self.__sections[section.name] = section

        def get_index(self):
                """Returns a dictionary of dictionaries indexed by section name
                and then property name for all properties."""
                return dict(
                    (s.name, s.get_index())
                    for s in self.get_sections()
                )

        def get_property(self, section, name):
                """Returns the value of the property object matching the given
                section and name.  Raises UnknownPropertyError if it does not
                exist.

                Be aware that references to the original value are returned;
                if the return value is not an immutable object (such as a list),
                changes to the object will affect the property.  If the return
                value needs to be modified, consumers are advised to create a
                copy first, and then call set_property() to update the value.
                Calling set_property() with the updated value is the only way
                to ensure that changes to a property's value are persistent.
                """
                try:
                        sec = self.get_section(section)
                except UnknownSectionError:
                        # To aid in debugging, re-raise as a property error
                        # so that both the unknown section and property are
                        # in the error message.
                        raise UnknownPropertyError(section=section, prop=name)
                return sec.get_property(name).value

        def get_properties(self):
                """Returns a generator that yields a list of tuples of the form
                (section object, property generator).  The property generator
                yields the list of property objects for the section.
                """
                return (
                    (s, s.get_properties())
                    for s in self.get_sections()
                )

        def get_section(self, name):
                """Returns the PropertySection object with the given name.
                Raises UnknownSectionError if it does not exist.
                """
                try:
                        return self.__sections[name]
                except KeyError:
                        raise UnknownSectionError(section=name)

        def get_sections(self):
                """Returns a generator that yields the list of property section
                objects."""
                return six.itervalues(self.__sections)

        def remove_property(self, section, name):
                """Remove the property object matching the given section and
                name.  Raises UnknownPropertyError if it does not exist.
                """
                try:
                        sec = self.get_section(section)
                except UnknownSectionError:
                        # To aid in debugging, re-raise as a property error
                        # so that both the unknown section and property are
                        # in the error message.
                        raise UnknownPropertyError(section=section, prop=name)
                sec.remove_property(name)
                self._dirty = True

        def remove_property_value(self, section, name, value):
                """Removes the value from the list of values for the property
                object matching the given section and name.  Raises
                UnknownPropertyError if the property or section does not
                exist.  Raises InvalidPropertyValueError if the value is not
                valid for the given property or if the target property isn't a
                list."""

                self._validate_section_name(section)
                self._validate_property_name(name)

                try:
                        secobj = self.get_section(section)
                except UnknownSectionError:
                        # To aid in debugging, re-raise as a property error
                        # so that both the unknown section and property are
                        # in the error message.
                        raise UnknownPropertyError(section=section, prop=name)

                propobj = secobj.get_property(name)
                if not isinstance(propobj.value, list):
                        raise PropertyMultiValueError(section=section,
                            prop=name, value=value)

                # Remove the value from a copy of the actual property object
                # value so that the property's set verification can happen.
                pval = copy.copy(propobj.value)
                try:
                        pval.remove(value)
                except ValueError:
                        raise UnknownPropertyValueError(section=section,
                            prop=name, value=value)
                else:
                        try:
                                propobj.value = pval
                        except PropertyConfigError as e:
                                if hasattr(e, "section") and not e.section:
                                        e.section = section
                                raise
                self._dirty = True

        def remove_section(self, name):
                """Remove the object matching the given section name.  Raises
                UnknownSectionError if it does not exist.
                """
                try:
                        del self.__sections[name]
                except KeyError:
                        raise UnknownSectionError(section=name)
                self._dirty = True

        def reset(self, overrides=misc.EmptyDict):
                """Discards current configuration data and returns the
                configuration object to its initial state.

                'overrides' is an optional dictionary of property values
                indexed by section name and property name.  If provided,
                it will be used to override any default values initially
                assigned during reset.
                """

                # Initialize to default state.
                self._dirty = True
                self.__reset(overrides=overrides)

        def set_property(self, section, name, value):
                """Sets the value of the property object matching the given
                section and name.  If the section or property does not already
                exist, it will be added.  Raises InvalidPropertyValueError if
                the value is not valid for the given property."""

                self._validate_section_name(section)
                self._validate_property_name(name)

                propobj = self._get_matching_property(section, name)
                try:
                        propobj.value = value
                except PropertyConfigError as e:
                        if hasattr(e, "section") and not e.section:
                                e.section = section
                        raise
                self._dirty = True

        def set_properties(self, properties):
                """Sets the values of the property objects matching those found
                in the provided dictionary.  If any section or property does not
                already exist, it will be added.  An InvalidPropertyValueError
                will be raised if the value is not valid for the given
                properties.

                'properties' should be a dictionary of dictionaries indexed by
                section and then by property name.  As an example:

                    {
                        'section': {
                            'property': value
                        }
                    }
                """

                # Dict is in arbitrary order, sort it first to ensure the
                # order is same in Python 2 and 3.
                properties = OrderedDict(sorted(properties.items()))
                for section, props in six.iteritems(properties):
                        props = OrderedDict(sorted(props.items()))
                        for pname, pval in six.iteritems(props):
                                self.set_property(section, pname, pval)

        @property
        def target(self):
                """Returns the target used for storage and retrieval of
                configuration data.  This can be None, a pathname, or
                an SMF FMRI.
                """
                return self._target

        @property
        def version(self):
                """Returns an integer value used to indicate what set of
                configuration data is in use."""

                return self._version

        def write(self):
                """Saves the current configuration object to the target
                provided at initialization.
                """
                pass


class FileConfig(Config):
        """The FileConfig class provides file-based retrieval and storage of
        non-structured (one-level deep) configuration data.  This particular
        class uses Python's ConfigParser module for configuration storage and
        management.

        ConfigParser uses a simple text format that consists of sections, lead
        by a "[section]" header, and followed by "name = value" entries, with
        continuations, etc. in the style of RFC 822.  Values can be split over
        multiple lines by beginning continuation lines with whitespace.  A
        sample configuration file might look like this:

        [pkg]
        port = 80
        inst_root = /export/repo

        [pub_example_com]
        feed_description = example.com's software
          update log
        """

        def __init__(self, pathname, definitions=misc.EmptyDict,
            overrides=misc.EmptyDict, version=None):
                """Initializes the object.

                'pathname' is the name of the file to read existing
                configuration data from or to write new configuration
                data to.  If the file does not already exist, defaults
                are set based on the version provided and the file will
                be created when the configuration is written.

                'definitions' is a dictionary of PropertySection objects indexed
                by configuration version defining the initial set of property
                sections, properties, and values for a Config object.

                'overrides' is an optional dictionary of property values indexed
                by section name and property name.  If provided, it will be used
                to override any default values initially assigned during
                initialization.

                'version' is an integer value that will be used to determine
                which configuration definition to use.  If not provided, the
                version will be based on the contents of the configuration
                file or the newest version found in 'definitions'.
                """
                # Must be set first.
                self._target = pathname

                Config.__init__(self, definitions=definitions,
                    overrides=overrides, version=version)

        def __read(self, overrides=misc.EmptyDict):
                """Reads the specified pathname and populates the configuration
                object based on the data contained within.  The file is
                expected to be in a ConfigParser-compatible format.
                """

                # First, attempt to read the target.
                cp = configparser.RawConfigParser()
                # Disabled ConfigParser's inane option transformation to ensure
                # option case is preserved.
                cp.optionxform = lambda x: x

                try:
                        efile = codecs.open(self._target, mode="rb",
                            encoding="utf-8")
                except EnvironmentError as e:
                        if e.errno == errno.ENOENT:
                                # Assume default configuration.
                                pass
                        elif e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        else:
                                raise
                else:
                        try:
                                # readfp() will be removed in futher Python
                                # versions, use read_file() instead.
                                if six.PY2:
                                        cp.readfp(efile)
                                else:
                                        cp.read_file(efile)
                        except (configparser.ParsingError,
                            configparser.MissingSectionHeaderError) as e:
                                raise api_errors.InvalidConfigFile(
                                    self._target)
                        # Attempt to determine version from contents.
                        try:
                                version = cp.getint("CONFIGURATION", "version")
                                self._version = version
                        except (configparser.NoSectionError,
                            configparser.NoOptionError, ValueError):
                                # Assume current version.
                                pass
                        efile.close()

                # Reset to initial state to ensure the default set of properties
                # and values exists so that any values not specified by the
                # saved configuration or overrides will be correct.  This must
                # be done after the version is determined above so that the
                # saved configuration data can be merged with the correct
                # configuration definition.
                Config.reset(self, overrides=overrides)

                for section in cp.sections():
                        if section == "CONFIGURATION":
                                # Reserved for configuration file management.
                                continue
                        for prop, value in cp.items(section):
                                if section in overrides and \
                                    prop in overrides[section]:
                                        continue

                                propobj = self._get_matching_property(section,
                                    prop)

                                # Try to convert unicode object to str object
                                # to ensure comparisons works as expected for
                                # consumers.
                                try:
                                        value = str(value)
                                except UnicodeEncodeError:
                                        # Value contains unicode.
                                        pass
                                try:
                                        propobj.value = value
                                except PropertyConfigError as e:
                                        if hasattr(e, "section") and \
                                            not e.section:
                                                e.section = section
                                        raise

        def reset(self, overrides=misc.EmptyDict):
                """Discards current configuration state and returns the
                configuration object to its initial state.

                'overrides' is an optional dictionary of property values
                indexed by section name and property name.  If provided,
                it will be used to override any default values initially
                assigned during reset.
                """

                # Reload the configuration.
                self.__read(overrides=overrides)

                if not overrides:
                        # Unless there were overrides, ignore any initial
                        # values for the purpose of determining whether a
                        # write should occur.  This isn't strictly correct,
                        # but is the desired behaviour in most cases.  This
                        # also matches the historical behaviour of the
                        # configuration classes used in pkg(5).
                        self._dirty = False

        def write(self):
                """Saves the configuration data using the pathname provided at
                initialization.
                """

                if os.path.exists(self._target) and not self._dirty:
                        return

                cp = configparser.RawConfigParser()
                # Disabled ConfigParser's inane option transformation to ensure
                # option case is preserved.
                cp.optionxform = lambda x: x

                for section, props in self.get_properties():
                        assert isinstance(section, PropertySection)
                        cp.add_section(section.name)
                        for p in props:
                                assert isinstance(p, Property)
                                cp.set(section.name, p.name, misc.force_str(p))

                # Used to track configuration management information.
                cp.add_section("CONFIGURATION")
                cp.set("CONFIGURATION", "version", str(self._version))

                fn = None
                try:
                        dirname = os.path.dirname(self._target)
                        fd, fn = tempfile.mkstemp(dir=dirname)

                        st = None
                        try:
                                st = os.stat(self._target)
                        except OSError as e:
                                if e.errno != errno.ENOENT:
                                        raise

                        if st:
                                os.fchmod(fd, stat.S_IMODE(st.st_mode))
                                try:
                                        portable.chown(fn, st.st_uid, st.st_gid)
                                except OSError as e:
                                        if e.errno != errno.EPERM:
                                                raise
                        else:
                                os.fchmod(fd, misc.PKG_FILE_MODE)

                        if six.PY2:
                                with os.fdopen(fd, "wb") as f:
                                        with codecs.EncodedFile(f, "utf-8") as ef:
                                                cp.write(ef)
                        else:
                                # it becomes easier to open the file
                                with open(fd, "w", encoding="utf-8") as f:
                                        cp.write(f)
                        portable.rename(fn, self._target)
                        self._dirty = False
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        elif e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise
                finally:
                        if fn and os.path.exists(fn):
                                os.unlink(fn)


# For SMF properties and property groups, this defines the naming restrictions.
# Although, additional restrictions may be imposed by the property and section
# classes in this module.
_SMF_name_re = '^([A-Za-z][ A-Za-z0-9.-]*,)?[A-Za-z][ A-Za-z0-9-_]*$'

class SMFInvalidPropertyNameError(PropertyConfigError):
        """Exception class used to indicate an invalid SMF property name."""

        def __init__(self, prop):
                assert prop is not None
                PropertyConfigError.__init__(self, prop=prop)

        def __str__(self):
                return _("Property name '{name}' is not valid.  Property "
                    "names may not contain: tabs, newlines, carriage returns, "
                    "form feeds, vertical tabs, slashes, or backslashes and "
                    "must also match the regular expression: {exp}").format(
                    name=self.prop, exp=_SMF_name_re)


class SMFInvalidSectionNameError(PropertyConfigError):
        """Exception class used to indicate an invalid SMF section name."""

        def __init__(self, section):
                assert section is not None
                PropertyConfigError.__init__(self, section=section)

        def __str__(self):
                return _("Section name '{name}' is not valid.  Section names "
                    "may not contain: tabs, newlines, carriage returns, form "
                    "feeds, vertical tabs, slashes, or backslashes and must "
                    "also match the regular expression: {exp}").format(
                    name=self.prop, exp=_SMF_name_re)


class SMFReadError(ConfigError):
        """Exception classes used to indicate that an error was encountered
        while attempting to read configuration data from SMF."""

        def __init__(self, svc_fmri, errmsg):
                ConfigError.__init__(self)
                assert svc_fmri and errmsg
                self.fmri = svc_fmri
                self.errmsg = errmsg

        def __str__(self):
                return _("Unable to read configuration data for SMF FMRI "
                    "'{fmri}':\n{errmsg}").format(**self.__dict__)


class SMFWriteError(ConfigError):
        """Exception classes used to indicate that an error was encountered
        while attempting to write configuration data to SMF."""

        def __init__(self, svc_fmri, errmsg):
                ConfigError.__init__(self)
                assert svc_fmri and errmsg
                self.fmri = svc_fmri
                self.errmsg = errmsg

        def __str__(self):
                return _("Unable to write configuration data for SMF FMRI "
                    "'{fmri}':\n{errmsg}").format(**self.__dict__)


class SMFConfig(Config):
        """The SMFConfig class provides SMF-based retrieval of non-structured
        (one-level deep) configuration data.  Property groups should be named
        after property sections.  Properties with list-based values should be
        stored using SMF list properties."""

        __name_re = re.compile(_SMF_name_re)
        __reserved_sections = ("general", "restarter", "fs", "autofs", "ntp",
            "network", "startd", "manifestfiles", "start", "stop",
            "tm_common_name")

        def __init__(self, svc_fmri, definitions=misc.EmptyDict,
            doorpath=None, overrides=misc.EmptyDict, version=0):
                """Initializes the object.

                'svc_fmri' is the FMRI of the SMF service to use for property
                data storage and retrieval.

                'definitions' is a dictionary of PropertySection objects indexed
                by configuration version defining the initial set of property
                sections, properties, and values for a Config object.

                'doorpath' is an optional pathname indicating the location of
                a door file to be used to communicate with SMF.  This is
                intended for use with an alternative svc.configd daemon.

                'overrides' is an optional dictionary of property values indexed
                by section name and property name.  If provided, it will be used
                to override any default values initially assigned during
                initialization.

                'version' is an integer value that will be used to determine
                which configuration definition to use.  If not provided, the
                version will be based on the newest version found in
                'definitions'.
                """
                # Must be set first.
                self.__doorpath = doorpath
                self._target = svc_fmri

                Config.__init__(self, definitions=definitions,
                    overrides=overrides, version=version)

        def _validate_property_name(self, name):
                """Raises an exception if property name is not valid for this
                class.
                """
                if not self.__name_re.match(name):
                        raise SMFInvalidPropertyNameError(name)

        def _validate_section_name(self, name):
                """Raises an exception if section name is not valid for this
                class.
                """
                if not self.__name_re.match(name) or \
                    name in self.__reserved_sections:
                        raise SMFInvalidSectionNameError(name)

        def __read(self, overrides=misc.EmptyDict):
                """Reads the configuration from the SMF FMRI specified at init
                time.
                """

                doorpath = ""
                if self.__doorpath:
                        doorpath = "LIBSCF_DOORPATH={0} ".format(
                            self.__doorpath)

                cmd = "{0}/usr/bin/svcprop -c -t {1}".format(doorpath,
                    self._target)
                p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                out, err = p.communicate()
                status, result = p.returncode, misc.force_str(out)
                if status:
                        raise SMFReadError(self._target,
                            "{cmd}: {result}".format(**locals()))

                cfgdata = {}
                prop = None
                for line in result.split("\n"):
                        if prop is None:
                                prop = line
                        else:
                                prop += line

                        # Output from svcprop can be spread over multiple lines
                        # if a property value has embedded newlines.  As such,
                        # look for the escape sequence at the end of the string
                        # to determine if output should be accumulated.
                        if re.search(r"(^|[^\\])(\\\\)*\\$", prop):
                                prop += "\n"
                                continue

                        if len(prop) < 2:
                                continue
                        n, t, v = prop.split(' ', 2)
                        pg, pn = n.split('/', 1)
                        if pg in self.__reserved_sections:
                                # SMF-specific groups ignored.
                                prop = None
                                continue

                        if (t == "astring" or t == "ustring") and v == '""':
                                v = ''
                        cfgdata.setdefault(pg, {})
                        cfgdata[pg][pn] = v
                        prop = None

                # Reset to initial state to ensure the default set of properties
                # and values exists so that any values not specified by the
                # saved configuration or overrides will be correct.  This must
                # be done after the version is determined above so that the
                # saved configuration data can be merged with the correct
                # configuration definition.
                Config.reset(self, overrides=overrides)

                # shlex.split() automatically does escaping for a list of values
                # so no need to do it here.
                for section, props in six.iteritems(cfgdata):
                        if section == "CONFIGURATION":
                                # Reserved for configuration file management.
                                continue
                        for prop, value in six.iteritems(props):
                                if section in overrides and \
                                    prop in overrides[section]:
                                        continue

                                propobj = self._get_matching_property(section,
                                    prop)
                                if isinstance(propobj, PropList):
                                        nvalue = []
                                        for v in shlex.split(value):
                                                try:
                                                        if six.PY2:
                                                                v = v.encode(
                                                                    "ascii")
                                                        else:
                                                                v = misc.force_str(
                                                                    v, "ascii")
                                                except ValueError:
                                                        try:
                                                                v = v.decode(
                                                                    "utf-8")
                                                        except ValueError:
                                                                # Permit opaque
                                                                # data.  It's
                                                                # up to each
                                                                # class whether
                                                                # to allow it.
                                                                pass
                                                nvalue.append(v)
                                        value = nvalue
                                else:
                                        # Allow shlex to unescape the value,
                                        # but rejoin all components as one.
                                        value = ''.join(shlex.split(value))

                                # Finally, set the property value.
                                try:
                                        propobj.value = value
                                except PropertyConfigError as e:
                                        if hasattr(e, "section") and \
                                            not e.section:
                                                e.section = section
                                        raise

        def reset(self, overrides=misc.EmptyDict):
                """Discards current configuration state and returns the
                configuration object to its initial state.

                'overrides' is an optional dictionary of property values
                indexed by section name and property name.  If provided,
                it will be used to override any default values initially
                assigned during reset.
                """

                # Reload the configuration.
                self.__read(overrides=overrides)

                if not overrides:
                        # Unless there were overrides, ignore any initial
                        # values for the purpose of determining whether a
                        # write should occur.  This isn't strictly correct,
                        # but is the desired behaviour in most cases.  This
                        # also matches the historical behaviour of the
                        # configuration classes used in pkg(5).
                        self._dirty = False

        def write(self):
                """Saves the current configuration object to the target
                provided at initialization.
                """

                raise SMFWriteError(self._target, _("Writing configuration "
                    "data to SMF is not supported at this time."))
