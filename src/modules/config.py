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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
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

import ConfigParser
import ast
import codecs
import commands
import copy
import errno
import os
import re
import shlex
import stat
import tempfile
import uuid

from pkg import misc, portable
import pkg.client.api_errors as api_errors


class ConfigError(api_errors.ApiException):
        """Base exception class for property errors."""


class PropertyConfigError(api_errors.ApiException):
        """Base exception class for property errors."""

        def __init__(self, section=None, prop=None):
                ConfigError.__init__(self)
                assert section is not None or prop is not None
                self.section = section
                self.prop = prop


class InvalidPropertyNameError(PropertyConfigError):
        """Exception class used to indicate an invalid property name."""

        def __str__(self):
                return _("Property name '%s' is not valid.  Section names "
                    "may not contain: tabs, newlines, carriage returns, "
                    "form feeds, vertical tabs, slashes, backslashes, or "
                    "non-ASCII characters.") % self.prop


class InvalidPropertyValueError(PropertyConfigError):
        """Exception class used to indicate an invalid property value."""

        def __init__(self, section=None, prop=None, value=None):
                PropertyConfigError.__init__(self, section=section, prop=prop)
                self.value = value

        def __str__(self):
                if self.section:
                        return _("Invalid value '%(val)s' for " \
                            "%(section)s.%(prop)s.") % { "val": self.value,
                                "section": self.section, "prop": self.prop }
                return _("Invalid value '%(val)s' for %(prop)s.") % {
                    "val": self.value, "prop": self.prop }


class InvalidSectionNameError(PropertyConfigError):
        """Exception class used to indicate an invalid section name."""

        def __str__(self):
                return _("Section name '%s' is not valid.  Section names "
                    "may not contain: tabs, newlines, carriage returns, "
                    "form feeds, vertical tabs, slashes, backslashes, or "
                    "non-ASCII characters.") % self.section


class UnknownPropertyError(PropertyConfigError):
        """Exception class used to indicate an invalid property."""

        def __str__(self):
                if self.section:
                        return _("Unknown property %s.%s") % (self.section,
                            self.prop)
                return _("Unknown property %s") % self.prop


class UnknownSectionError(PropertyConfigError):
        """Exception class used to indicate an invalid section."""

        def __str__(self):
                return _("Unknown property section: %s.") % self.section


class Property(object):
        """Base class for properties."""

        # Whitespace, '/', and '\' are never allowed.
        __name_re = re.compile(r"\A[^\t\n\r\f\v\\/]+\Z")

        _value = None

        def __init__(self, name, default=""):
                if not isinstance(name, basestring) or \
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

        def __cmp__(self, other):
                if not isinstance(other, Property):
                        return -1
                return cmp(self.name, other.name)

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

        def __copy__(self):
                return self.__class__(self.name, default=self.value)

        def __unicode__(self):
                if isinstance(self.value, unicode):
                        return self.value
                # Assume that value can be represented in utf-8.
                return unicode(self.__str__(), "utf-8")

        def __str__(self):
                if isinstance(self.value, unicode):
                        return self.value.encode("utf-8")
                return str(self.value)

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """
                if not isinstance(value, basestring):
                        # Only string values are allowed.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)

        def _transform_string(self, value):
                # Transform encoded UTF-8 data into unicode objects if needed.
                if isinstance(value, str):
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
                if value is None:
                        value = ""
                elif isinstance(value, (bool, int)):
                        value = str(value)
                else:
                        value = self._transform_string(value)
                self._is_allowed(value)
                self._value = value


class PropBool(Property):
        """Class representing properties with a boolean value."""

        def __init__(self, name, default=False):
                Property.__init__(self, name, default=default)

        @Property.value.setter
        def value(self, value):
                if value is None or value == "":
                        self._value = False
                        return
                elif isinstance(value, basestring):
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

        def __init__(self, name, default=0):
                Property.__init__(self, name, default=default)

        @Property.value.setter
        def value(self, value):
                if value is None or value == "":
                        self._value = 0
                        return

                try:
                        self._value = int(value)
                except Exception:
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)


class PropPublisher(Property):
        """Class representing properties with a publisher prefix/alias value."""

        @Property.value.setter
        def value(self, value):
                if value is None or value == "":
                        self._value = ""
                        return
                if not isinstance(value, basestring) or \
                    not misc.valid_pub_prefix(value):
                        # Only string values are allowed.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)
                self._value = value


class PropDefined(Property):
        """Class representing properties with that can only have one of a set
        of pre-defined values."""

        def __init__(self, name, allowed=misc.EmptyI, default=""):
                self.__allowed = allowed
                Property.__init__(self, name, default=default)

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
                except ValueError:
                        # ast raises ValueError if input isn't safe or
                        # valid.
                        raise InvalidPropertyValueError(prop=self.name,
                            value=value)
                return value

        @PropDefined.value.setter
        def value(self, value):
                if value is None or value == "":
                        value = []
                elif isinstance(value, basestring):
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
                        elif not isinstance(v, basestring):
                                # Only string values are allowed.
                                raise InvalidPropertyValueError(prop=self.name,
                                    value=value)
                        self._is_allowed(v)
                        nvalue.append(v)

                if self.allowed and "" not in self.allowed and not len(nvalue):
                        raise InvalidPropertyValueError(prop=self.name,
                            value=nvalue)

                self._value = nvalue


class PropSimpleList(PropList):
        """Class representing a property with a list of string values that are
        simple in nature.  Output is in a comma-separated format that may not
        be suitable for some datasets such as those containing arbitrary data,
        newlines, commas or that may contain zero-length strings.
        """

        def _is_allowed(self, value):
                """Raises an InvalidPropertyValueError if 'value' is not allowed
                for this property.
                """

                # Enforce base class rules.
                PropList._is_allowed(self, value)

                if isinstance(value, str):
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
                # unicode() objects.
                result = []
                for v in value.split(","):
                        try:
                                v = v.encode("ascii")
                        except ValueError:
                                if not isinstance(v, unicode):
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

        def __unicode__(self):
                if self.value and len(self.value):
                        # Performing the join using a unicode string results in
                        # a single unicode string object.
                        return u",".join(self.value)
                return u""

        def __str__(self):
                if self.value and len(self.value):
                        return ",".join([v.encode("utf-8") for v in self.value])
                return ""


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


class PropPubURIList(PropSimpleList):
        """Class representing a property for a list of publisher URIs.  Output
        is in a basic comma-separated format that may not be suitable for some
        datasets."""

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
                if not isinstance(name, basestring) or \
                    not self.__name_re.match(name) or \
                    name == "CONFIGURATION":
                        raise InvalidSectionNameError(section=name)
                try:
                        name.encode("ascii")
                except ValueError:
                        # Name contains non-ASCII characters.
                        raise InvalidSectionNameError(section=name)
                self.__name = name

                # Should be set last.
                self.__properties = dict((p.name, p) for p in properties)

        def __cmp__(self, other):
                if not isinstance(other, PropertySection):
                        return -1
                return cmp(self.name, other.name)

        def __copy__(self):
                propsec = self.__class__(self.__name)
                for p in self.get_properties():
                        propsec.add_property(copy.copy(p))
                return propsec

        def __unicode__(self):
                return unicode(self.name)

        def __str__(self):
                return self.name

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
                    for pname, p in self.__properties.iteritems()
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
                return self.__properties.itervalues()

        def remove_property(self, name):
                """Removes any matching property object from the section."""
                try:
                        del self.__properties[name]
                except KeyError:
                        # Already removed; don't care.
                        pass

        @property
        def name(self):
                """The name of the section."""
                return self.__name


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

                self.__sections = {}
                self._defs = definitions
                if version is None:
                        if definitions:
                                version = max(definitions.keys())
                        else:
                                version = 0
                self._version = version
                self.reset(overrides=overrides)

        def __unicode__(self):
                """Returns a unicode object representation of the configuration
                object.
                """
                out = u""
                for sec, props in self.get_properties():
                        out += "[%s]\n" % sec.name
                        for p in props:
                                out += u"%s = %s\n" % (p.name, unicode(p))
                        out += "\n"
                return out

        def __str__(self):
                """Returns a string representation of the configuration
                object.
                """
                out = ""
                for sec, props in self.get_properties():
                        out += "[%s]\n" % sec.name
                        for p in props:
                                out += "%s = %s\n" % (p.name, str(p))
                        out += "\n"
                return out

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

        def __reset(self, overrides=misc.EmptyDict):
                """Returns the configuration object to its default state."""
                self.__sections = {}
                for s in self._defs.get(self._version, misc.EmptyDict):
                        self._validate_section_name(s.name)
                        self.add_section(copy.copy(s))
                for sname, props in overrides.iteritems():
                        for pname, val in props.iteritems():
                                self.set_property(sname, pname, val)

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
                return self.__sections.itervalues()

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

                try:
                        secobj = self.get_section(section)
                except UnknownSectionError:
                        # Add a new section.
                        secobj = PropertySection(section)
                        self.add_section(secobj)

                try:
                        propobj = secobj.get_property(name)
                except UnknownPropertyError:
                        # Assume unknown properties are base type.
                        propobj = secobj.add_property(Property(name))

                propobj.value = value
                self._dirty = True

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
        inst_root = /var/pkg/repo

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
                cp = ConfigParser.SafeConfigParser()

                try:
                        efile = codecs.open(self._target, mode="rb",
                            encoding="utf-8")
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                # Assume default configuration.
                                pass
                        elif e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        else:
                                raise
                else:
                        cp.readfp(efile)
                        # Attempt to determine version from contents.
                        try:
                                version = cp.getint("CONFIGURATION", "version")
                                self._version = version
                        except (ConfigParser.NoSectionError,
                            ConfigParser.NoOptionError, ValueError):
                                # Assume current version.
                                pass

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

                                try:
                                        secobj = self.get_section(section)
                                except UnknownSectionError:
                                        secobj = PropertySection(section)
                                        self.add_section(secobj)

                                try:
                                        propobj = secobj.get_property(prop)
                                except UnknownPropertyError:
                                        # Assume unknown properties are strings.
                                        propobj = secobj.add_property(
                                            Property(prop))

                                # Try to convert unicode object to str object
                                # to ensure comparisons works as expected for
                                # consumers.
                                try:
                                        value = str(value)
                                except UnicodeEncodeError:
                                        # Value contains unicode.
                                        pass
                                propobj.value = value

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

                cp = ConfigParser.SafeConfigParser()
                for section, props in self.get_properties():
                        cp.add_section(section.name)
                        for p in props:
                                cp.set(section.name, p.name, str(p))

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
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                        if st:
                                os.fchmod(fd, stat.S_IMODE(st.st_mode))
                                try:
                                        portable.chown(fn, st.st_uid, st.st_gid)
                                except OSError, e:
                                        if e.errno != errno.EPERM:
                                                raise
                        else:
                                os.fchmod(fd, misc.PKG_FILE_MODE)

                        with os.fdopen(fd, "wb") as f:
                                with codecs.EncodedFile(f, "utf-8") as ef:
                                        cp.write(ef)
                        portable.rename(fn, self._target)
                        self._dirty = False
                except EnvironmentError, e:
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

        def __str__(self):
                return _("Property name '%(name)s' is not valid.  Property "
                    "names may not contain: tabs, newlines, carriage returns, "
                    "form feeds, vertical tabs, slashes, or backslashes and "
                    "must also match the regular expression: %(exp)s") % {
                    "name": self.prop, "exp": _SMF_name_re }


class SMFInvalidSectionNameError(PropertyConfigError):
        """Exception class used to indicate an invalid SMF section name."""

        def __str__(self):
                return _("Section name '%(name)s' is not valid.  Section names "
                    "may not contain: tabs, newlines, carriage returns, form "
                    "feeds, vertical tabs, slashes, or backslashes and must "
                    "also match the regular expression: %(exp)s") % {
                    "name": self.prop, "exp": _SMF_name_re }


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
                    "'%(fmri)s':\n%(errmsg)s") % self.__dict__


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
                    "'%(fmri)s':\n%(errmsg)s") % self.__dict__


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
                        doorpath = "LIBSCF_DOORPATH=%s " % self.__doorpath

                cmd = "%s/usr/bin/svcprop -c -t %s" % (doorpath, self._target)
                status, result = commands.getstatusoutput(cmd)
                if status:
                        raise SMFReadError(self._target, "%(cmd)s: %(result)s" %
                            locals())

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
                for section, props in cfgdata.iteritems():
                        if section == "CONFIGURATION":
                                # Reserved for configuration file management.
                                continue
                        for prop, value in props.iteritems():
                                if section in overrides and \
                                    prop in overrides[section]:
                                        continue

                                # Get the property section and property.
                                try:
                                        secobj = self.get_section(section)
                                except UnknownSectionError:
                                        secobj = PropertySection(section)
                                        self.add_section(secobj)

                                try:
                                        propobj = secobj.get_property(prop)
                                except UnknownPropertyError:
                                        # Assume unknown properties are strings.
                                        propobj = secobj.add_property(
                                            Property(prop))

                                if isinstance(propobj, PropList):
                                        nvalue = []
                                        for v in shlex.split(value):
                                                try:
                                                        v = v.encode("ascii")
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
                                propobj.value = value

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
