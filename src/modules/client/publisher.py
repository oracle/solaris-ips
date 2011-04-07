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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

#
# NOTE: Any changes to this file are considered a change in client api
# interfaces and must be fully documented in doc/client_api_versions.txt
# if they are visible changes to the public interfaces provided.
#
# This also means that changes to the interfaces here must be reflected in
# the client version number and compatible_versions specifier found in
# modules/client/api.py:__init__.
#

import calendar
import copy
import cStringIO
import datetime as dt
import errno
import hashlib
import os
import pycurl
import shutil
import tempfile
import time
import urllib
import urlparse
import uuid

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
logger = global_settings.logger

import pkg.catalog
import pkg.client.api_errors as api_errors
import pkg.client.sigpolicy as sigpolicy
import pkg.misc as misc
import pkg.portable as portable
import pkg.server.catalog as old_catalog
import M2Crypto as m2

from pkg.misc import EmptyDict, EmptyI, SIGNATURE_POLICY, DictProperty

# The "core" type indicates that a repository contains all of the dependencies
# declared by packages in the repository.  It is primarily used for operating
# system repositories.
REPO_CTYPE_CORE = "core"

# The "supplemental" type indicates that a repository contains packages that
# rely on or are intended to be used with packages located in another
# repository.
REPO_CTYPE_SUPPLEMENTAL = "supplemental"

# Mapping of constant values to names (in the event these ever get changed to
# numeric values or it is decided they need "prettier" or different labels).
REPO_COLLECTION_TYPES = {
    REPO_CTYPE_CORE: "core",
    REPO_CTYPE_SUPPLEMENTAL: "supplemental",
}

# Supported Protocol Schemes
SUPPORTED_SCHEMES = set(("file", "http", "https"))

# SSL Protocol Schemes
SSL_SCHEMES = set(("https",))

# Supported RepositoryURI sorting policies.
URI_SORT_PRIORITY = "priority"

# Sort policy mapping.
URI_SORT_POLICIES = {
    URI_SORT_PRIORITY: lambda obj: (obj.priority, obj.uri),
}

# This dictionary records the recognized values of extensions.
SUPPORTED_EXTENSION_VALUES = {
    "basicConstraints": ("CA:TRUE", "CA:FALSE", "PATHLEN:"),
    "keyUsage": ("DIGITAL SIGNATURE", "CERTIFICATE SIGN", "CRL SIGN")
}

# These dictionaries map uses into their extensions.
CODE_SIGNING_USE = {
    "keyUsage": ["DIGITAL SIGNATURE"]
}

CERT_SIGNING_USE = {
    "basicConstraints": ["CA:TRUE"],
    "keyUsage": ["CERTIFICATE SIGN"]
}

CRL_SIGNING_USE = {
    "keyUsage": ["CRL SIGN"]
}

POSSIBLE_USES = [CODE_SIGNING_USE, CERT_SIGNING_USE, CRL_SIGNING_USE]

class RepositoryURI(object):
        """Class representing a repository URI and any transport-related
        information."""

        # These properties are declared here so that they show up in the pydoc
        # documentation as private, and for clarity in the property declarations
        # found near the end of the class definition.
        __priority = None
        __ssl_cert = None
        __ssl_key = None
        __trailing_slash = None
        __uri = None

        # Used to store the id of the original object this one was copied
        # from during __copy__.
        _source_object_id = None

        def __init__(self, uri, priority=None, ssl_cert=None, ssl_key=None,
            trailing_slash=True):
                # Must set first.
                self.__trailing_slash = trailing_slash

                # Note that the properties set here are intentionally lacking
                # the '__' prefix which means assignment will occur using the
                # get/set methods declared for the property near the end of
                # the class definition.
                self.priority = priority
                self.uri = uri
                self.ssl_cert = ssl_cert
                self.ssl_key = ssl_key

        def __copy__(self):
                uri = RepositoryURI(self.__uri, priority=self.__priority,
                    ssl_cert=self.__ssl_cert, ssl_key=self.__ssl_key,
                    trailing_slash=self.__trailing_slash)
                uri._source_object_id = id(self)
                return uri

        def __eq__(self, other):
                if isinstance(other, RepositoryURI):
                        return self.uri == other.uri
                if isinstance(other, str):
                        return self.uri == other
                return False

        def __ne__(self, other):
                if isinstance(other, RepositoryURI):
                        return self.uri != other.uri
                if isinstance(other, str):
                        return self.uri != other
                return True

        def __set_priority(self, value):
                if value is not None:
                        try:
                                value = int(value)
                        except (TypeError, ValueError):
                                raise api_errors.BadRepositoryURIPriority(value)
                self.__priority = value

        def __set_ssl_cert(self, filename):
                if self.scheme not in SSL_SCHEMES and filename:
                        raise api_errors.UnsupportedRepositoryURIAttribute(
                            "ssl_cert", scheme=self.scheme)
                if filename:
                        if not isinstance(filename, basestring):
                                raise api_errors.BadRepositoryAttributeValue(
                                    "ssl_cert", value=filename)
                        filename = os.path.abspath(filename)
                        if not os.path.exists(filename):
                                raise api_errors.NoSuchCertificate(filename,
                                    uri=self.uri)
                if filename == "":
                        filename = None
                # XXX attempt certificate verification here?
                self.__ssl_cert = filename

        def __set_ssl_key(self, filename):
                if self.scheme not in SSL_SCHEMES and filename:
                        raise api_errors.UnsupportedRepositoryURIAttribute(
                            "ssl_key", scheme=self.scheme)
                if filename:
                        if not isinstance(filename, basestring):
                                raise api_errors.BadRepositoryAttributeValue(
                                    "ssl_key", value=filename)
                        filename = os.path.abspath(filename)
                        if not os.path.exists(filename):
                                raise api_errors.NoSuchKey(filename,
                                    uri=self.uri)
                if filename == "":
                        filename = None
                # XXX attempt key verification here?
                self.__ssl_key = filename

        def __set_trailing_slash(self, value):
                if value not in (True, False):
                        raise api_errors.BadRepositoryAttributeValue(
                            "trailing_slash", value=value)
                self.__trailing_slash = value

        def __set_uri(self, uri):
                if uri is None:
                        raise api_errors.BadRepositoryURI(uri)

                # Decompose URI to verify attributes.
                scheme, netloc, path, params, query = \
                    urlparse.urlsplit(uri, allow_fragments=0)

                # The set of currently supported protocol schemes.
                if scheme.lower() not in SUPPORTED_SCHEMES:
                        raise api_errors.UnsupportedRepositoryURI(uri)

                # XXX valid_pub_url's check isn't quite right and could prevent
                # usage of IDNs (international domain names).
                if (scheme.lower().startswith("http") and not netloc) or \
                    not misc.valid_pub_url(uri):
                        raise api_errors.BadRepositoryURI(uri)

                if scheme.lower() == "file" and netloc:
                        raise api_errors.BadRepositoryURI(uri)

                # Normalize URI scheme.
                uri = uri.replace(scheme, scheme.lower(), 1)

                if self.__trailing_slash:
                        uri = misc.url_affix_trailing_slash(uri)

                if scheme.lower() not in SSL_SCHEMES:
                        self.__ssl_cert = None
                        self.__ssl_key = None

                self.__uri = uri

        def __str__(self):
                return self.__uri

        def get_pathname(self):
                """Returns the URI path as a pathname if the URI is a file
                URI or '' otherwise."""

                scheme, netloc, path, params, query, fragment = \
                    urlparse.urlparse(self.__uri, allow_fragments=0)
                if scheme == "file":
                        return urllib.url2pathname(path)
                return ""

        ssl_cert = property(lambda self: self.__ssl_cert, __set_ssl_cert, None,
            "The absolute pathname of a PEM-encoded SSL certificate file.")

        ssl_key = property(lambda self: self.__ssl_key, __set_ssl_key, None,
            "The absolute pathname of a PEM-encoded SSL key file.")

        uri = property(lambda self: self.__uri, __set_uri, None,
            "The URI used to access a repository.")

        priority = property(lambda self: self.__priority, __set_priority, None,
            "An integer value representing the importance of this repository "
            "URI relative to others.")

        @property
        def scheme(self):
                """The URI scheme."""
                if not self.__uri:
                        return ""
                return urlparse.urlsplit(self.__uri, allow_fragments=0)[0]

        trailing_slash = property(lambda self: self.__trailing_slash,
            __set_trailing_slash, None,
            "A boolean value indicating whether any URI provided for this "
            "object should have a trailing slash appended when setting the "
            "URI property.")


class Repository(object):
        """Class representing a repository object.

        A repository object represents a location where clients can publish
        and retrieve package content and/or metadata.  It has the following
        characteristics:

                - may have one or more origins (URIs) for publication and
                  retrieval of package metadata and content.

                - may have zero or more mirrors (URIs) for retrieval of package
                  content."""

        # These properties are declared here so that they show up in the pydoc
        # documentation as private, and for clarity in the property declarations
        # found near the end of the class definition.
        __collection_type = None
        __legal_uris = []
        __mirrors = []
        __origins = []
        __refresh_seconds = None
        __registration_uri = None
        __related_uris = []
        __sort_policy = URI_SORT_PRIORITY

        # Used to store the id of the original object this one was copied
        # from during __copy__.
        _source_object_id = None

        name = None
        description = None
        registered = False

        def __init__(self, collection_type=REPO_CTYPE_CORE, description=None,
            legal_uris=None, mirrors=None, name=None, origins=None,
            refresh_seconds=None, registered=False, registration_uri=None,
            related_uris=None, sort_policy=URI_SORT_PRIORITY):
                """Initializes a repository object.

                'collection_type' is an optional constant value indicating the
                type of packages in the repository.

                'description' is an optional string value containing a
                descriptive paragraph for the repository.

                'legal_uris' should be a list of RepositoryURI objects or URI
                strings indicating where licensing, legal, and terms of service
                information for the repository can be found.

                'mirrors' is an optional list of RepositoryURI objects or URI
                strings indicating where package content can be retrieved.

                'name' is an optional, short, descriptive name for the
                repository.

                'origins' should be a list of RepositoryURI objects or URI
                strings indicating where package metadata can be retrieved.

                'refresh_seconds' is an optional integer value indicating the
                number of seconds clients should wait before refreshing cached
                repository catalog or repository metadata information.

                'registered' is an optional boolean value indicating whether
                a client has registered with the repository's publisher.

                'registration_uri' is an optional RepositoryURI object or a URI
                string indicating a location clients can use to register or
                obtain credentials needed to access the repository.

                'related_uris' is an optional list of RepositoryURI objects or a
                list of URI strings indicating the location of related
                repositories that a client may be interested in.

                'sort_policy' is an optional constant value indicating how
                legal_uris, mirrors, origins, and related_uris should be
                sorted."""

                # Note that the properties set here are intentionally lacking
                # the '__' prefix which means assignment will occur using the
                # get/set methods declared for the property near the end of
                # the class definition.

                # Must be set first so that it will apply to attributes set
                # afterwards.
                self.sort_policy = sort_policy

                self.collection_type = collection_type
                self.description = description
                self.legal_uris = legal_uris
                self.mirrors = mirrors
                self.name = name
                self.origins = origins
                self.refresh_seconds = refresh_seconds
                self.registered = registered
                self.registration_uri = registration_uri
                self.related_uris = related_uris

        def __add_uri(self, attr, uri, dup_check=None, priority=None,
            ssl_cert=None, ssl_key=None, trailing_slash=True):
                if not isinstance(uri, RepositoryURI):
                        uri = RepositoryURI(uri, priority=priority,
                            ssl_cert=ssl_cert, ssl_key=ssl_key,
                            trailing_slash=trailing_slash)

                if dup_check:
                        dup_check(uri)

                ulist = getattr(self, attr)
                ulist.append(uri)
                ulist.sort(key=URI_SORT_POLICIES[self.__sort_policy])

        def __copy__(self):
                cluris = [copy.copy(u) for u in self.legal_uris]
                cmirrors = [copy.copy(u) for u in self.mirrors]
                cruris = [copy.copy(u) for u in self.related_uris]
                corigins = [copy.copy(u) for u in self.origins]
                repo = Repository(collection_type=self.collection_type,
                    description=self.description,
                    legal_uris=cluris,
                    mirrors=cmirrors, name=self.name,
                    origins=corigins,
                    refresh_seconds=self.refresh_seconds,
                    registered=self.registered,
                    registration_uri=copy.copy(self.registration_uri),
                    related_uris=cruris)
                repo._source_object_id = id(self)
                return repo

        def __replace_uris(self, attr, value, trailing_slash=True):
                if value is None:
                        value = []
                if not isinstance(value, list):
                        raise api_errors.BadRepositoryAttributeValue(attr,
                            value=value)
                uris = []
                for u in value:
                        if not isinstance(u, RepositoryURI):
                                u = RepositoryURI(u,
                                    trailing_slash=trailing_slash)
                        elif trailing_slash:
                                u.uri = misc.url_affix_trailing_slash(u.uri)
                        uris.append(u)
                uris.sort(key=URI_SORT_POLICIES[self.__sort_policy])
                return uris

        def __set_collection_type(self, value):
                if value not in REPO_COLLECTION_TYPES:
                        raise api_errors.BadRepositoryCollectionType(value)
                self.__collection_type = value

        def __set_legal_uris(self, value):
                self.__legal_uris = self.__replace_uris("legal_uris", value,
                    trailing_slash=False)

        def __set_mirrors(self, value):
                self.__mirrors = self.__replace_uris("mirrors", value)

        def __set_origins(self, value):
                self.__origins = self.__replace_uris("origins", value)

        def __set_registration_uri(self, value):
                if value and not isinstance(value, RepositoryURI):
                        value = RepositoryURI(value, trailing_slash=False)
                self.__registration_uri = value

        def __set_related_uris(self, value):
                self.__related_uris = self.__replace_uris("related_uris",
                    value, trailing_slash=False)

        def __set_refresh_seconds(self, value):
                if value is not None:
                        try:
                                value = int(value)
                        except (TypeError, ValueError):
                                raise api_errors.BadRepositoryAttributeValue(
                                    "refresh_seconds", value=value)
                        if value < 0:
                                raise api_errors.BadRepositoryAttributeValue(
                                    "refresh_seconds", value=value)
                self.__refresh_seconds = value

        def __set_sort_policy(self, value):
                if value not in URI_SORT_POLICIES:
                        raise api_errors.BadRepositoryURISortPolicy(value)
                self.__sort_policy = value

        def add_legal_uri(self, uri, priority=None, ssl_cert=None,
            ssl_key=None):
                """Adds the specified legal URI to the repository.

                'uri' can be a RepositoryURI object or a URI string.  If
                it is a RepositoryURI object, all other parameters will be
                ignored."""

                self.__add_uri("legal_uris", uri, priority=priority,
                    ssl_cert=ssl_cert, ssl_key=ssl_key, trailing_slash=False)

        def add_mirror(self, mirror, priority=None, ssl_cert=None,
            ssl_key=None):
                """Adds the specified mirror to the repository.

                'mirror' can be a RepositoryURI object or a URI string.  If
                it is a RepositoryURI object, all other parameters will be
                ignored."""

                def dup_check(mirror):
                        if self.has_mirror(mirror):
                                raise api_errors.DuplicateRepositoryMirror(
                                    mirror)

                self.__add_uri("mirrors", mirror, dup_check=dup_check,
                    priority=priority, ssl_cert=ssl_cert, ssl_key=ssl_key)

        def add_origin(self, origin, priority=None, ssl_cert=None,
            ssl_key=None):
                """Adds the specified origin to the repository.

                'origin' can be a RepositoryURI object or a URI string.  If
                it is a RepositoryURI object, all other parameters will be
                ignored."""

                def dup_check(origin):
                        if self.has_origin(origin):
                                raise api_errors.DuplicateRepositoryOrigin(
                                    origin)

                self.__add_uri("origins", origin, dup_check=dup_check,
                    priority=priority, ssl_cert=ssl_cert, ssl_key=ssl_key)

        def add_related_uri(self, uri, priority=None, ssl_cert=None,
            ssl_key=None):
                """Adds the specified related URI to the repository.

                'uri' can be a RepositoryURI object or a URI string.  If
                it is a RepositoryURI object, all other parameters will be
                ignored."""

                self.__add_uri("related_uris", uri, priority=priority,
                    ssl_cert=ssl_cert, ssl_key=ssl_key, trailing_slash=False)

        def get_mirror(self, mirror):
                """Returns a RepositoryURI object representing the mirror
                that matches 'mirror'.

                'mirror' can be a RepositoryURI object or a URI string."""

                if not isinstance(mirror, RepositoryURI):
                        mirror = misc.url_affix_trailing_slash(mirror)
                for m in self.mirrors:
                        if mirror == m.uri:
                                return m
                raise api_errors.UnknownRepositoryMirror(mirror)

        def get_origin(self, origin):
                """Returns a RepositoryURI object representing the origin
                that matches 'origin'.

                'origin' can be a RepositoryURI object or a URI string."""

                if not isinstance(origin, RepositoryURI):
                        origin = misc.url_affix_trailing_slash(origin)
                for o in self.origins:
                        if origin == o.uri:
                                return o
                raise api_errors.UnknownRepositoryOrigin(origin)

        def has_mirror(self, mirror):
                """Returns a boolean value indicating whether a matching
                'mirror' exists for the repository.

                'mirror' can be a RepositoryURI object or a URI string."""

                if not isinstance(mirror, RepositoryURI):
                        mirror = misc.url_affix_trailing_slash(mirror)
                return mirror in self.mirrors

        def has_origin(self, origin):
                """Returns a boolean value indicating whether a matching
                'origin' exists for the repository.

                'origin' can be a RepositoryURI object or a URI string."""

                if not isinstance(origin, RepositoryURI):
                        origin = misc.url_affix_trailing_slash(origin)
                return origin in self.origins

        def remove_legal_uri(self, uri):
                """Removes the legal URI matching 'uri' from the repository.

                'uri' can be a RepositoryURI object or a URI string."""

                for i, m in enumerate(self.legal_uris):
                        if uri == m.uri:
                                # Immediate return as the index into the array
                                # changes with each removal.
                                del self.legal_uris[i]
                                return
                raise api_errors.UnknownLegalURI(uri)

        def remove_mirror(self, mirror):
                """Removes the mirror matching 'mirror' from the repository.

                'mirror' can be a RepositoryURI object or a URI string."""

                if not isinstance(mirror, RepositoryURI):
                        mirror = misc.url_affix_trailing_slash(mirror)
                for i, m in enumerate(self.mirrors):
                        if mirror == m.uri:
                                # Immediate return as the index into the array
                                # changes with each removal.
                                del self.mirrors[i]
                                return
                raise api_errors.UnknownRepositoryMirror(mirror)

        def remove_origin(self, origin):
                """Removes the origin matching 'origin' from the repository.

                'origin' can be a RepositoryURI object or a URI string."""

                if not isinstance(origin, RepositoryURI):
                        origin = misc.url_affix_trailing_slash(origin)
                for i, o in enumerate(self.origins):
                        if origin == o.uri:
                                # Immediate return as the index into the array
                                # changes with each removal.
                                del self.origins[i]
                                return
                raise api_errors.UnknownRepositoryOrigin(origin)

        def remove_related_uri(self, uri):
                """Removes the related URI matching 'uri' from the repository.

                'uri' can be a RepositoryURI object or a URI string."""

                for i, m in enumerate(self.related_uris):
                        if uri == m.uri:
                                # Immediate return as the index into the array
                                # changes with each removal.
                                del self.related_uris[i]
                                return
                raise api_errors.UnknownRelatedURI(uri)

        def update_mirror(self, mirror, priority=None, ssl_cert=None,
            ssl_key=None):
                """Updates an existing mirror object matching 'mirror'.

                'mirror' can be a RepositoryURI object or a URI string."""

                if not isinstance(mirror, RepositoryURI):
                        mirror = RepositoryURI(mirror, priority=priority,
                            ssl_cert=ssl_cert, ssl_key=ssl_key)

                target = self.get_mirror(mirror)
                target.priority = mirror.priority
                target.ssl_cert = mirror.ssl_cert
                target.ssl_key = mirror.ssl_key
                self.mirrors.sort(key=URI_SORT_POLICIES[self.__sort_policy])

        def update_origin(self, origin, priority=None, ssl_cert=None,
            ssl_key=None):
                """Updates an existing origin object matching 'origin'.

                'origin' can be a RepositoryURI object or a URI string."""

                if not isinstance(origin, RepositoryURI):
                        origin = RepositoryURI(origin, priority=priority,
                            ssl_cert=ssl_cert, ssl_key=ssl_key)

                target = self.get_origin(origin)
                target.priority = origin.priority
                target.ssl_cert = origin.ssl_cert
                target.ssl_key = origin.ssl_key
                self.origins.sort(key=URI_SORT_POLICIES[self.__sort_policy])

        def reset_mirrors(self):
                """Discards the current list of repository mirrors."""

                self.mirrors = []

        def reset_origins(self):
                """Discards the current list of repository origins."""

                self.origins = []

        collection_type = property(lambda self: self.__collection_type,
            __set_collection_type, None,
            """A constant value indicating the type of packages in the
            repository.  The following collection types are recognized:

                    REPO_CTYPE_CORE
                        The "core" type indicates that the repository contains
                        all of the dependencies declared by packages in the
                        repository.  It is primarily used for operating system
                        repositories.

                    REPO_CTYPE_SUPPLEMENTAL
                        The "supplemental" type indicates that the repository
                        contains packages that rely on or are intended to be
                        used with packages located in another repository.""")

        legal_uris = property(lambda self: self.__legal_uris,
            __set_legal_uris, None,
            """A list of RepositoryURI objects indicating where licensing,
            legal, and terms of service information for the repository can be
            found.""")

        mirrors = property(lambda self: self.__mirrors, __set_mirrors, None,
            """A list of RepositoryURI objects indicating where package content
            can be retrieved.  If any value in the list provided is a URI
            string, it will be replaced with a RepositoryURI object.""")

        origins = property(lambda self: self.__origins, __set_origins, None,
            """A list of RepositoryURI objects indicating where package content
            can be retrieved.  If any value in the list provided is a URI
            string, it will be replaced with a RepositoryURI object.""")

        registration_uri = property(lambda self: self.__registration_uri,
            __set_registration_uri, None,
            """A RepositoryURI object indicating a location clients can use to
            register or obtain credentials needed to access the repository.  If
            the value provided is a URI string, it will be replaced with a
            RepositoryURI object.""")

        related_uris = property(lambda self: self.__related_uris,
            __set_related_uris, None,
            """A list of RepositoryURI objects indicating the location of
            related repositories that a client may be interested in.  If any
            value in the list provided is a URI string, it will be replaced with
            a RepositoryURI object.""")

        refresh_seconds = property(lambda self: self.__refresh_seconds,
            __set_refresh_seconds, None,
            """An integer value indicating the number of seconds clients should
            wait before refreshing cached repository metadata information.  A
            value of None indicates that refreshes should be performed at the
            client's discretion.""")

        sort_policy = property(lambda self: self.__sort_policy,
            __set_sort_policy, None,
            """A constant value indicating how legal_uris, mirrors, origins, and
            related_uris should be sorted.  The following policies are
            recognized:

                    URI_SORT_PRIORITY
                        The "priority" policy indicate that URIs should be
                        sorted according to the value of their priority
                        attribute.""")


class Publisher(object):
        """Class representing a publisher object and a set of interfaces to set
        and retrieve its information.

        A publisher is a forward or reverse domain name identifying a source
        (e.g. "publisher") of packages."""

        # These properties are declared here so that they show up in the pydoc
        # documentation as private, and for clarity in the property declarations
        # found near the end of the class definition.
        __alias = None
        __catalog = None
        __client_uuid = None
        __disabled = False
        __meta_root = None
        __prefix = None
        __selected_repository = None
        __repositories = []
        __sticky = True
        transport = None

        # Used to store the id of the original object this one was copied
        # from during __copy__.
        _source_object_id = None

        def __init__(self, prefix, alias=None, catalog=None, client_uuid=None,
            disabled=False, meta_root=None, repositories=None,
            selected_repository=None, transport=None, sticky=True,
            ca_certs=EmptyI, intermediate_certs=EmptyI, props=None,
            revoked_ca_certs=EmptyI, approved_ca_certs=EmptyI):
                """Initialize a new publisher object.

                'catalog' is an optional Catalog object to use in place of
                retrieving one from the publisher's meta_root.  This option
                may only be used when meta_root is not provided.
                """

                assert not (catalog and meta_root)

                if client_uuid is None:
                        self.reset_client_uuid()
                else:
                        self.__client_uuid = client_uuid

                self.__repositories = []

                # Note that the properties set here are intentionally lacking
                # the '__' prefix which means assignment will occur using the
                # get/set methods declared for the property near the end of
                # the class definition.
                self.alias = alias
                self.disabled = disabled
                self.prefix = prefix
                self.transport = transport
                self.meta_root = meta_root
                self.sticky = sticky

                if repositories:
                        for r in repositories:
                                self.add_repository(r)

                if selected_repository:
                        self.selected_repository = selected_repository

                self.__sig_policy = None
                self.__delay_validation = False

                self.__properties = {}

                # Writing out an EmptyI to a config file and reading it back
                # in doesn't work correctly at the moment, but reading and
                # writing an empty list does. So if intermediate_certs is empty,
                # make sure it's stored as an empty list.
                #
                # The relevant implementation is probably the line which
                # strips ][ from the input in imageconfig.read_list.
                if revoked_ca_certs:
                        self.revoked_ca_certs = revoked_ca_certs
                else:
                        self.revoked_ca_certs = []

                if approved_ca_certs:
                        self.approved_ca_certs = approved_ca_certs
                else:
                        self.approved_ca_certs = []

                if props:
                        self.properties.update(props)

                self.ca_dict = None

                # Must be done last.
                self.__catalog = catalog

        def __cmp__(self, other):
                if other is None:
                        return 1
                if isinstance(other, Publisher):
                        return cmp(self.prefix, other.prefix)
                return cmp(self.prefix, other)

        @staticmethod
        def __contains__(key):
                """Supports deprecated compatibility interface."""

                return key in ("client_uuid", "disabled", "mirrors", "origin",
                    "prefix", "ssl_cert", "ssl_key")

        def __copy__(self):
                selected = None
                repositories = []
                for r in self.__repositories:
                        repo = copy.copy(r)
                        if r == self.selected_repository:
                                selected = repo
                        repositories.append(repo)
                pub = Publisher(self.__prefix, alias=self.__alias,
                    client_uuid=self.__client_uuid, disabled=self.__disabled,
                    meta_root=self.meta_root, repositories=repositories,
                    selected_repository=selected, transport=self.transport,
                    sticky=self.__sticky,
                    props=self.properties,
                    revoked_ca_certs=self.revoked_ca_certs,
                    approved_ca_certs=self.approved_ca_certs)
                pub._source_object_id = id(self)
                return pub

        def __eq__(self, other):
                if isinstance(other, Publisher):
                        return self.prefix == other.prefix
                if isinstance(other, str):
                        return self.prefix == other
                return False

        def __getitem__(self, key):
                """Deprecated compatibility interface allowing publisher
                attributes to be read as pub["attribute"]."""

                if key == "client_uuid":
                        return self.__client_uuid
                if key == "disabled":
                        return self.__disabled
                if key == "prefix":
                        return self.__prefix

                repo = self.selected_repository
                if key == "mirrors":
                        return [str(m) for m in repo.mirrors]
                if key == "origin":
                        if not repo.origins[0]:
                                return None
                        return repo.origins[0].uri
                if key == "ssl_cert":
                        if not repo.origins[0]:
                                return None
                        return repo.origins[0].ssl_cert
                if key == "ssl_key":
                        if not repo.origins[0]:
                                return None
                        return repo.origins[0].ssl_key

        def __get_last_refreshed(self):
                if not self.meta_root:
                        return None

                lcfile = os.path.join(self.meta_root, "last_refreshed")
                try:
                        mod_time = os.stat(lcfile).st_mtime
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                return None
                        raise
                return dt.datetime.utcfromtimestamp(mod_time)

        def __ne__(self, other):
                if isinstance(other, Publisher):
                        return self.prefix != other.prefix
                if isinstance(other, str):
                        return self.prefix != other
                return True

        def __set_alias(self, value):
                # Aliases must comply with the same restrictions that prefixes
                # have as they are intended to be useable in any case where
                # a prefix may be used.
                if value is not None and value != "" and \
                    not misc.valid_pub_prefix(value):
                        raise api_errors.BadPublisherAlias(value)
                self.__alias = value

        def __set_disabled(self, disabled):
                if disabled:
                        self.__disabled = True
                else:
                        self.__disabled = False

        def __set_last_refreshed(self, value):
                if not self.meta_root:
                        return

                if value is not None and not isinstance(value, dt.datetime):
                        raise api_errors.BadRepositoryAttributeValue(
                            "last_refreshed", value=value)

                lcfile = os.path.join(self.meta_root, "last_refreshed")
                if not value:
                        # If no value was provided, attempt to remove the
                        # tracking file.
                        try:
                                portable.remove(lcfile)
                        except EnvironmentError, e:
                                # If the file can't be removed due to
                                # permissions, a read-only filesystem, or
                                # because it doesn't exist, continue on.
                                if e.errno not in (errno.ENOENT, errno.EACCES,
                                    errno.EROFS):
                                        raise
                        return

                def create_tracker():
                        try:
                                f = open(lcfile, "wb")
                                f.write("%s\n" % misc.time_to_timestamp(
                                    calendar.timegm(value.utctimetuple())))
                                f.close()
                        except EnvironmentError, e:
                                # If the file can't be written due to
                                # permissions or because the filesystem is
                                # read-only, continue on.
                                if e.errno not in (errno.EACCES, errno.EROFS):
                                        raise

                try:
                        # If a time was provided, write out a special file that
                        # can be used to track the information with the actual
                        # time (in UTC) contained within.
                        create_tracker()
                except EnvironmentError, e:
                        if e.errno != errno.ENOENT:
                                raise

                        # Assume meta_root doesn't exist and create it.
                        try:
                                self.create_meta_root()
                        except api_errors.PermissionsException:
                                # If the directory can't be created due to
                                # permissions, move on.
                                pass
                        except EnvironmentError, e:
                                # If the directory can't be created due to a
                                # read-only filesystem, move on.
                                if e.errno != errno.EROFS:
                                        raise
                        else:
                                # Try one last time.
                                create_tracker()

        def __set_meta_root(self, pathname):
                if pathname:
                        pathname = os.path.abspath(pathname)
                self.__meta_root = pathname
                if self.__catalog:
                        self.__catalog.meta_root = self.catalog_root
                if self.__meta_root:
                        self.cert_root = os.path.join(self.__meta_root, "certs")
                        self.__subj_root = os.path.join(self.cert_root,
                            "subject_hashes")
                        self.__crl_root = os.path.join(self.cert_root, "crls")

        def __set_prefix(self, prefix):
                if not misc.valid_pub_prefix(prefix):
                        raise api_errors.BadPublisherPrefix(prefix)
                self.__prefix = prefix

        def __set_selected_repository(self, value):
                if not isinstance(value, Repository) or \
                    value not in self.repositories:
                        raise api_errors.UnknownRepository(value)
                self.__selected_repository = value
                self.__catalog = None

        def __set_client_uuid(self, value):
                self.__client_uuid = value

        def __set_stickiness(self, value):
                self.__sticky = bool(value)

        def __str__(self):
                return self.prefix

        def __validate_metadata(self):
                """Private helper function to check the publisher's metadata
                for configuration or other issues and log appropriate warnings
                or errors.  Currently only checks catalog metadata."""

                c = self.catalog
                if not c.exists:
                        # Nothing to validate.
                        return
                if not c.version > 0:
                        # Validation doesn't apply.
                        return
                if not c.package_count:
                        # Nothing to do.
                        return

                # XXX For now, perform this check using the catalog data.
                # In the future, it should be done using the output of the
                # publisher/0 operation.
                pubs = self.catalog.publishers()

                if self.prefix not in pubs:
                        origins = self.selected_repository.origins
                        origin = origins[0]
                        logger.error(_("""
Unable to retrieve package data for publisher '%(prefix)s' from one
of the following origin(s):

%(origins)s

The catalog retrieved from one of the origin(s) listed above only
contains package data for: %(pubs)s.
""") % { "origins": "\n".join(str(o) for o in origins), "prefix": self.prefix,
    "pubs": ", ".join(pubs) })

                        if global_settings.client_name != "pkg":
                                logger.error(_("""\
This is either a result of invalid origin information being provided
for publisher '%s', or because the wrong publisher name was
provided when this publisher was added.
""") % self.prefix)
                                # Remaining messages are for pkg client only.
                                return

                        logger.error(_("""\
To resolve this issue, correct the origin information provided for
publisher '%(prefix)s' using the pkg set-publisher subcommand, or re-add
the publisher using the correct name and remove the '%(prefix)s'
publisher.
""") % { "prefix": self.prefix })

                        if len(pubs) == 1:
                                logger.warning(_("""\
To re-add this publisher with the correct name, execute the following
commands as a privileged user:

pkg set-publisher -P -g %(origin)s %(pub)s
pkg unset-publisher %(prefix)s
""") % { "origin": origin, "prefix": self.prefix, "pub": list(pubs)[0] })
                                return

                        logger.warning(_("""\
The origin(s) listed above contain package data for more than one
publisher, but this issue can likely be resolved by executing one
of the following commands as a privileged user:
"""))

                        for pfx in pubs:
                                logger.warning(_("pkg set-publisher -P -g "
                                    "%(origin)s %(pub)s\n") % {
                                    "origin": origin, "pub": pfx })

                        logger.warning(_("""\
Afterwards, the old publisher should be removed by executing the
following command as a privileged user:

pkg unset-publisher %s
""") % self.prefix)

        def add_repository(self, repository):
                """Adds the provided repository object to the publisher and
                sets it as the selected one if no repositories exist."""

                for r in self.__repositories:
                        if repository.name == r.name:
                                raise api_errors.DuplicateRepository(
                                    self.prefix)
                        for o in repository.origins:
                                if o.uri in r.origins:
                                        raise api_errors.DuplicateRepository(
                                            self.prefix)

                self.__repositories.append(repository)
                if len(self.__repositories) == 1:
                        self.selected_repository = repository

        @property
        def catalog(self):
                """A reference to the Catalog object for the publisher's
                selected repository, or None if available."""

                if not self.meta_root:
                        if self.__catalog:
                                return self.__catalog
                        return None

                if not self.__catalog:
                        croot = self.catalog_root
                        if not os.path.isdir(croot):
                                # Current meta_root structure is likely in
                                # a state of transition, so don't provide a
                                # meta_root.  Assume that an empty catalog
                                # is desired instead.  (This can happen during
                                # an image format upgrade.)
                                croot = None
                        self.__catalog = pkg.catalog.Catalog(
                            meta_root=croot)
                return self.__catalog

        @property
        def catalog_root(self):
                """The absolute pathname of the directory containing the
                Catalog data for the publisher, or None if meta_root is
                not defined."""

                if self.meta_root:
                        return os.path.join(self.meta_root, "catalog")

        def create_meta_root(self):
                """Create the publisher's meta_root."""

                if not self.meta_root:
                        raise api_errors.BadPublisherMetaRoot(self.meta_root,
                            operation="create_meta_root")

                for path in (self.meta_root, self.catalog_root):
                        try:
                                os.makedirs(path)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                elif e.errno != errno.EEXIST:
                                        # If the path already exists, move on.
                                        # Otherwise, raise the exception.
                                        raise
                # Optional roots not needed for all operations.
                for path in (self.cert_root, self.__subj_root, self.__crl_root):
                        try:
                                os.makedirs(path)
                        except EnvironmentError, e:
                                if e.errno in (errno.EACCES, errno.EROFS):
                                        pass
                                elif e.errno != errno.EEXIST:
                                        # If the path already exists, move on.
                                        # Otherwise, raise the exception.
                                        raise

        def get_repository(self, name=None, origin=None):
                """Returns the repository object matching the name or that has
                a matching origin URI."""

                assert not (name and origin)
                for r in self.__repositories:
                        if (name and r.name == name) or (origin and
                            r.has_origin(origin)):
                                return r
                raise api_errors.UnknownRepository(max(name, origin))

        @property
        def needs_refresh(self):
                """A boolean value indicating whether the publisher's
                metadata for the currently selected repository needs to be
                refreshed."""

                if not self.selected_repository or not self.meta_root:
                        # Nowhere to obtain metadata from; this should rarely
                        # occur except during publisher initialization.
                        return False

                lc = self.last_refreshed
                if not lc:
                        # There is no record of when the publisher metadata was
                        # last refreshed, so assume it should be refreshed now.
                        return True

                ts_now = time.time()
                ts_last = calendar.timegm(lc.utctimetuple())

                rs = self.selected_repository.refresh_seconds
                if not rs:
                        # There is no indicator of how often often publisher
                        # metadata should be refreshed, so assume it should be
                        # now.
                        return True

                if (ts_now - ts_last) >= rs:
                        # The number of seconds that has elapsed since the
                        # publisher metadata was last refreshed exceeds or
                        # equals the specified interval.
                        return True

                return False

        def __convert_v0_catalog(self, v0_cat):
                """Transforms the contents of the provided version 0 Catalog
                into a version 1 Catalog, replacing the current Catalog."""

                v0_lm = v0_cat.last_modified()
                if v0_lm:
                        # last_modified can be none if the catalog is empty.
                        v0_lm = pkg.catalog.ts_to_datetime(v0_lm)

                v1_cat = self.catalog

                # There's no point in signing this catalog since it's simply
                # a transformation of a v0 catalog.
                v1_cat.sign = False

                # A check for a previous non-zero package count is made to
                # determine whether the last_modified date alone can be
                # relied on.  This works around some oddities with empty
                # v0 catalogs.
                try:
                        # Could be 'None'
                        n0_pkgs = int(v0_cat.npkgs())
                except (TypeError, ValueError):
                        n0_pkgs = 0

                if n0_pkgs != v1_cat.package_version_count:
                        if v0_lm == self.catalog.last_modified:
                                # Already converted.
                                return
                        # Simply rebuild the entire v1 catalog every time, this
                        # avoids many of the problems that could happen due to
                        # deficiencies in the v0 implementation.
                        v1_cat.destroy()
                        self.__catalog = None
                        v1_cat = self.catalog

                # Now populate the v1 Catalog with the v0 Catalog's data.
                v1_cat.batch_mode = True
                for f in v0_cat.fmris():
                        v1_cat.add_package(f)

                # Normally, the Catalog's attributes are automatically
                # populated as a result of catalog operations.  But in
                # this case, we want the v1 Catalog's attributes to
                # match those of the v0 catalog.
                v1_cat.last_modified = v0_lm

                # While this is a v1 catalog format-wise, v0 data is stored.
                # This allows consumers to be aware that certain data won't be
                # available in this catalog (such as dependencies, etc.).
                v1_cat.version = 0

                # Finally, save the new Catalog, and replace the old in-memory
                # catalog.
                v1_cat.batch_mode = False
                v1_cat.finalize()
                v1_cat.save()
                self.__catalog = v1_cat

        def __refresh_v0(self, full_refresh, immediate):
                """The method to refresh the publisher's metadata against
                a catalog/0 source.  If the more recent catalog/1 version
                isn't supported, this routine gets invoked as a fallback."""

                if full_refresh:
                        immediate = True

                # Catalog needs v0 -> v1 transformation if repository only
                # offers v0 catalog.
                v0_cat = old_catalog.ServerCatalog(self.catalog_root,
                    read_only=True, publisher=self.prefix)

                new_cat = True
                v0_lm = None
                if v0_cat.exists:
                        repo = self.selected_repository
                        if full_refresh or v0_cat.origin() not in repo.origins:
                                try:
                                        v0_cat.destroy(root=self.catalog_root)
                                except EnvironmentError, e:
                                        if e.errno == errno.EACCES:
                                                raise api_errors.PermissionsException(
                                                    e.filename)
                                        if e.errno == errno.EROFS:
                                                raise api_errors.ReadOnlyFileSystemException(
                                                    e.filename)
                                        raise
                                immediate = True
                        else:
                                new_cat = False
                                v0_lm = v0_cat.last_modified()

                if not immediate and not self.needs_refresh:
                        # No refresh needed.
                        return False

                import pkg.updatelog as old_ulog
                try:
                        # Note that this currently retrieves a v0 catalog that
                        # has to be converted to v1 format.
                        self.transport.get_catalog(self, v0_lm)
                except old_ulog.UpdateLogException:
                        # If an incremental update fails, attempt a full
                        # catalog retrieval instead.
                        try:
                                v0_cat.destroy(root=self.catalog_root)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise
                        self.transport.get_catalog(self)

                v0_cat = pkg.server.catalog.ServerCatalog(
                    self.catalog_root, read_only=True,
                    publisher=self.prefix)

                self.__convert_v0_catalog(v0_cat)
                self.last_refreshed = dt.datetime.utcnow()

                if new_cat or v0_lm != v0_cat.last_modified():
                        # If the catalog was rebuilt, or the timestamp of the
                        # catalog changed, then an update has occurred.
                        return True
                return False

        def __refresh_v1(self, tempdir, full_refresh, immediate, mismatched):
                """The method to refresh the publisher's metadata against
                a catalog/1 source.  If the more recent catalog/1 version
                isn't supported, __refresh_v0 is invoked as a fallback."""

                # If full_refresh is True, then redownload should be True to
                # ensure a non-cached version of the catalog is retrieved.
                # If full_refresh is False, but mismatched is True, then
                # the retrieval requests should indicate that content should
                # be revalidated before being returned.  Note that this
                # only applies to the catalog v1 case.
                redownload = full_refresh
                revalidate = not redownload and mismatched

                try:
                        self.transport.get_catalog1(self, ["catalog.attrs"],
                            path=tempdir, redownload=redownload,
                            revalidate=revalidate)
                except api_errors.UnsupportedRepositoryOperation:
                        # No v1 catalogs available.
                        if self.catalog.exists:
                                # Ensure v1 -> v0 transition works right.
                                self.catalog.destroy()
                                self.__catalog = None
                        return self.__refresh_v0(full_refresh, immediate)

                # If a v0 catalog is present, remove it before proceeding to
                # ensure transitions between catalog versions work correctly.
                v0_cat = old_catalog.ServerCatalog(self.catalog_root,
                    read_only=True, publisher=self.prefix)
                if v0_cat.exists:
                        v0_cat.destroy(root=self.catalog_root)

                # If above succeeded, we now have a catalog.attrs file.  Parse
                # this to determine what other constituent parts need to be
                # downloaded.
                flist = []
                if not full_refresh and self.catalog.exists:
                        flist = self.catalog.get_updates_needed(tempdir)
                        if flist == None:
                                # Catalog has not changed.
                                self.last_refreshed = dt.datetime.utcnow()
                                return False
                else:
                        attrs = pkg.catalog.CatalogAttrs(meta_root=tempdir)
                        for name in attrs.parts:
                                locale = name.split(".", 2)[2]
                                # XXX Skip parts that aren't in the C locale for
                                # now.
                                if locale != "C":
                                        continue
                                flist.append(name)

                if flist:
                        # More catalog files to retrieve.
                        try:
                                self.transport.get_catalog1(self, flist,
                                    path=tempdir, redownload=redownload,
                                    revalidate=revalidate)
                        except api_errors.UnsupportedRepositoryOperation:
                                # Couldn't find a v1 catalog after getting one
                                # before.  This would be a bizzare error, but we
                                # can try for a v0 catalog anyway.
                                return self.__refresh_v0(full_refresh,
                                    immediate)

                # At this point the client should have a set of the constituent
                # pieces that are necessary to construct a catalog.  If a
                # catalog already exists, call apply_updates.  Otherwise,
                # move the files to the appropriate location.
                validate = False
                if not full_refresh and self.catalog.exists:
                        self.catalog.apply_updates(tempdir)
                else:
                        if self.catalog.exists:
                                # This is a full refresh.  Destroy
                                # the existing catalog.
                                self.catalog.destroy()
                                self.__catalog = None

                        for fn in os.listdir(tempdir):
                                srcpath = os.path.join(tempdir, fn)
                                dstpath = os.path.join(self.catalog_root, fn)
                                pkg.portable.rename(srcpath, dstpath)

                        # Apply_updates validates the newly constructed catalog.
                        # If refresh didn't call apply_updates, arrange to
                        # have the new catalog validated.
                        validate = True

                # Update refresh time.
                self.last_refreshed = dt.datetime.utcnow()

                # Clear __catalog, so we'll read in the new catalog.
                self.__catalog = None

                if validate:
                        try:
                                self.catalog.validate()
                        except api_errors.BadCatalogSignatures:
                                # If signature validation fails here, that means
                                # that the attributes and individual parts were
                                # self-consistent and not corrupt, but that the
                                # attributes and parts didn't match.  This could
                                # be the result of a broken source providing
                                # an attributes file that is much older or newer
                                # than the catalog parts being provided.
                                self.catalog.destroy()
                                self.__catalog = None
                                raise api_errors.MismatchedCatalog(self.prefix)
                return True

        def __refresh(self, full_refresh, immediate, mismatched=False):
                """The method to handle the overall refresh process.  It
                determines if a refresh is actually needed, and then calls
                the first version-specific refresh method in the chain."""

                assert self.catalog_root
                assert self.transport

                if full_refresh:
                        immediate = True

                # Ensure consistent directory structure.
                self.create_meta_root()

                # Check if we already have a v1 catalog on disk.
                if not full_refresh and self.catalog.exists:
                        # If catalog is on disk, check if refresh is necessary.
                        if not immediate and not self.needs_refresh:
                                # No refresh needed.
                                return False

                if not self.selected_repository.origins:
                        # Nothing to do.
                        return False

                # Create temporary directory for assembly of catalog pieces.
                try:
                        tempdir = tempfile.mkdtemp(dir=self.catalog_root)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                # Ensure that the temporary directory gets removed regardless
                # of success or failure.
                try:
                        rval = self.__refresh_v1(tempdir, full_refresh,
                            immediate, mismatched)

                        # Perform publisher metadata sanity checks.
                        self.__validate_metadata()

                        return rval
                finally:
                        # Cleanup tempdir.
                        shutil.rmtree(tempdir, True)

        def refresh(self, full_refresh=False, immediate=False):
                """Refreshes the publisher's metadata, returning a boolean
                value indicating whether any updates to the publisher's
                metadata occurred.

                'full_refresh' is an optional boolean value indicating whether
                a full retrieval of publisher metadata (e.g. catalogs) or only
                an update to the existing metadata should be performed.  When
                True, 'immediate' is also set to True.

                'immediate' is an optional boolean value indicating whether
                a refresh should occur now.  If False, a publisher's selected
                repository will be checked for updates only if needs_refresh
                is True."""

                try:
                        return self.__refresh(full_refresh, immediate)
                except (api_errors.BadCatalogUpdateIdentity,
                    api_errors.DuplicateCatalogEntry,
                    api_errors.ObsoleteCatalogUpdate,
                    api_errors.UnknownUpdateType):
                        if full_refresh:
                                # Completely unexpected failure.
                                # These exceptions should never
                                # be raised for a full refresh
                                # case anyway, so the error should
                                # definitely be raised.
                                raise

                        # The incremental update likely failed for one or
                        # more of the following reasons:
                        #
                        # * The origin for the publisher has changed.
                        #
                        # * The catalog that the publisher is offering
                        #   is now completely different (due to a restore
                        #   from backup or --rebuild possibly).
                        #
                        # * The catalog that the publisher is offering
                        #   has been restored to an older version, and
                        #   packages that already exist in this client's
                        #   copy of the catalog have been re-addded.
                        #
                        # * The type of incremental update operation that
                        #   that was performed on the catalog isn't supported
                        #   by this version of the client, so a full retrieval
                        #   is required.
                        #
                        return self.__refresh(True, True)
                except api_errors.MismatchedCatalog:
                        if full_refresh:
                                # If this was a full refresh, don't bother
                                # retrying as it implies that the content
                                # retrieved wasn't cached.
                                raise

                        # Retrieval of the catalog attributes and/or parts was
                        # successful, but the identity (digest or other
                        # information) didn't match the catalog attributes.
                        # This could be the result of a misbehaving or stale
                        # cache.
                        return self.__refresh(False, True, mismatched=True)
                except (api_errors.BadCatalogSignatures,
                    api_errors.InvalidCatalogFile):
                        # Assembly of the catalog failed, but this could be due
                        # to a transient error.  So, retry at least once more.
                        return self.__refresh(True, True)
                except (api_errors.BadCatalogSignatures,
                    api_errors.InvalidCatalogFile):
                        # Assembly of the catalog failed, but this could be due
                        # to a transient error.  So, retry at least once more.
                        return self.__refresh(True, True)

        def remove_meta_root(self):
                """Removes the publisher's meta_root."""

                if not self.meta_root:
                        raise api_errors.BadPublisherMetaRoot(self.meta_root,
                            operation="remove_meta_root")

                try:
                        shutil.rmtree(self.meta_root)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        if e.errno not in (errno.ENOENT, errno.ESRCH):
                                raise

        def remove_repository(self, name=None, origin=None):
                """Removes the repository object matching the name or that has
                a matching origin URI from the publisher."""

                assert not (name and origin)
                for i, r in enumerate(self.__repositories):
                        if (name and r.name == name) or (origin and
                            r.has_origin(origin)):
                                if r != self.selected_repository:
                                        # Immediate return as the index into the
                                        # array changes with each removal.
                                        del self.__repositories[i]
                                        return
                                raise api_errors.SelectedRepositoryRemoval(r)

        def reset_client_uuid(self):
                """Replaces the current client_uuid with a new UUID."""

                self.__client_uuid = str(uuid.uuid1())

        def set_selected_repository(self, name=None, origin=None):
                """Sets the selected repository for the publisher to the
                repository object matching the name or that has a matching
                origin URI."""

                self.__selected_repository = self.get_repository(name=name,
                    origin=origin)

        def validate_config(self, repo_uri=None):
                """Verify that the publisher's configuration (such as prefix)
                matches that provided by the repository.  If the configuration
                does not match as expected, an UnknownRepositoryPublishers
                exception will be raised.

                'repo_uri' is an optional RepositoryURI object or URI string
                containing the location of the repository.  If not provided,
                the publisher's selected_repository will be used instead."""

                if repo_uri and not isinstance(repo_uri, RepositoryURI):
                        repo = RepositoryURI(repo_uri)
                elif not repo_uri:
                        # Transport actually allows both type of objects.
                        repo = self
                else:
                        repo = repo_uri

                pubs = None
                try:
                        pubs = self.transport.get_publisherdata(repo)
                except (api_errors.TransportError,
                    api_errors.UnsupportedRepositoryOperation):
                        # Nothing more can be done (because the target origin
                        # can't be contacted, or beacuse it doesn't support
                        # retrievel of publisher configuration data).
                        return

                if not pubs:
                        raise api_errors.RepoPubConfigUnavailable(
                            location=repo_uri, pub=self)

                if self.prefix not in pubs:
                        known = [p.prefix for p in pubs]
                        if repo_uri:
                                raise api_errors.UnknownRepositoryPublishers(
                                    known=known, unknown=[self.prefix],
                                    location=repo_uri)
                        raise api_errors.UnknownRepositoryPublishers(
                            known=known, unknown=[self.prefix],
                            origins=self.selected_repository.origins)

        def approve_ca_cert(self, cert, trust_anchors=None, img_policy=None):
                """Add the cert as a CA for manifest signing for this publisher.

                The 'cert' parameter as a string of the certificate to add.

                The 'trust_anchors' parameter is a dictionary which contains
                the trust anchors to use to validate the certificate.

                The 'img_policy' parameter is the signature policy for the
                image."""

                hsh = self.__add_cert(cert)
                # If the user had previously revoked this certificate, remove
                # the certificate from that list.
                if hsh in self.revoked_ca_certs:
                        t = set(self.revoked_ca_certs)
                        t.remove(hsh)
                        self.revoked_ca_certs = list(t)
                self.approved_ca_certs.append(hsh)

        def revoke_ca_cert(self, s):
                """Record that the cert with hash 's' is no longer trusted
                as a CA.  This method currently assumes it's only invoked as
                a result of user action."""

                self.revoked_ca_certs.append(s)
                self.revoked_ca_certs = list(set(
                    self.revoked_ca_certs))
                if s in self.approved_ca_certs:
                        t = set(self.approved_ca_certs)
                        t.remove(s)
                        self.approved_ca_certs = list(t)

        def unset_ca_cert(self, s):
                """If the cert with hash 's' has been added or removed by the
                user, undo the add or removal."""

                if s in self.approved_ca_certs:
                        t = set(self.approved_ca_certs)
                        t.remove(s)
                        self.approved_ca_certs = list(t)
                if s in self.revoked_ca_certs:
                        t = set(self.revoked_ca_certs)
                        t.remove(s)
                        self.revoked_ca_certs = list(t)

        @staticmethod
        def __hash_cert(s):
                return hashlib.sha1(s).hexdigest()

        def __add_cert(self, s):
                """Add the certificate stored as a string in 's' to the
                certificates this publisher knows about."""

                self.create_meta_root()
                pkg_hash = self.__hash_cert(s)
                pkg_hash_pth = os.path.join(self.cert_root, pkg_hash)
                try:
                        with open(pkg_hash_pth, "wb") as fh:
                                fh.write(s)
                except EnvironmentError, e:
                        raise api_errors._convert_error(e)
                try:
                        c = m2.X509.load_cert_string(s)
                except m2.X509.X509Error, e:
                        try:
                                portable.remove(pkg_hash_pth)
                        except:
                                # Pass because the bad file format error is the
                                # more important one.
                                pass
                        raise api_errors.BadFileFormat(_("The file with hash "
                            "%s was expected to be a PEM certificate but it "
                            "could not be read.") % pkg_hash)

                # Note that while we store certs by their subject hashes,
                # M2Crypto's subject hashes differ from what openssl reports
                # the subject hash to be.
                subj_hsh = c.get_subject().as_hash()
                c = 0
                made_link = False
                while not made_link:
                        fn = os.path.join(self.__subj_root,
                            "%s.%s" % (subj_hsh, c))
                        if os.path.exists(fn):
                                c += 1
                        else:
                                try:
                                        portable.link(pkg_hash_pth, fn)
                                except EnvironmentError, e:
                                        raise api_errors._convert_error(e)
                                made_link = True
                return pkg_hash

        def get_cert_by_hash(self, pkg_hash, verify_hash=False,
            only_retrieve=False):
                """Given a pkg5 hash, retrieve the cert that's associated with
                it.

                The 'pkg_hash' parameter contains the file hash of the
                certificate to retrieve.

                The 'verify_hash' parameter determines the file that's read
                from disk matches the expected hash.

                The 'only_retrieve' parameter determines whether a X509 object
                is built from the certificate retrieved or if the certificate
                is only stored on disk. """

                assert not (verify_hash and only_retrieve)
                pth = os.path.join(self.cert_root, pkg_hash)
                if not os.path.exists(pth):
                        self.__add_cert(self.transport.get_content(self,
                            pkg_hash))
                if only_retrieve:
                        return None
                with open(pth, "rb") as fh:
                        s = fh.read()
                        c = m2.X509.load_cert_string(s)

                if verify_hash:
                        h = misc.get_data_digest(cStringIO.StringIO(s),
                            length=len(s))[0]
                        if h != pkg_hash:
                                raise api_errors.ModifiedCertificateException(c,
                                    pth)
                return c

        def __get_certs_by_name(self, name):
                """Given 'name', a M2Crypto X509_Name, return the certs with
                that name as a subject."""

                res = []
                c = 0
                name_hsh = name.as_hash()
                try:
                        while True:
                                pth = os.path.join(self.__subj_root,
                                    "%s.%s" % (name_hsh, c))
                                cert = m2.X509.load_cert(pth)
                                res.append(cert)
                                c += 1
                except EnvironmentError, e:
                        t = api_errors._convert_error(e,
                            [errno.ENOENT])
                        if t:
                                raise t
                return res

        def get_ca_certs(self):
                """Return a dictionary of the CA certificates for this
                publisher."""

                if self.ca_dict is not None:
                        return self.ca_dict
                self.ca_dict = {}
                # CA certs approved for this publisher are stored by hash to
                # prevent the later substitution or confusion over what certs
                # have or have not been approved.
                for h in set(self.approved_ca_certs):
                        c = self.get_cert_by_hash(h, verify_hash=True)
                        s = c.get_subject().as_hash()
                        self.ca_dict.setdefault(s, [])
                        self.ca_dict[s].append(c)
                return self.ca_dict

        def update_props(self, set_props=EmptyI, add_prop_values=EmptyDict,
            remove_prop_values=EmptyDict, unset_props=EmptyI):
                """Update the properties set for this publisher with the ones
                provided as arguments.  The order of application is that any
                existing properties are unset, then properties are set to their
                new values, then values are added to properties, and finally
                values are removed from properties."""

                # Delay validation so that any intermittent inconsistent state
                # doesn't cause problems.
                self.__delay_validation = True
                # Remove existing properties.
                for n in unset_props:
                        self.properties.pop(n, None)
                # Add or reset new properties.
                self.properties.update(set_props)
                # Add new values to properties.
                for n in add_prop_values.keys():
                        self.properties.setdefault(n, [])
                        self.properties[n].extend(add_prop_values[n])
                # Remove values from properties.
                for n in remove_prop_values.keys():
                        if n not in self.properties:
                                raise api_errors.InvalidPropertyValue(_(
                                    "Cannot remove a value from the property "
                                    "%(name)s because the property does not "
                                    "exist.") % {"name":n})
                        if not isinstance(self.properties[n], list):
                                raise api_errors.InvalidPropertyValue(_(
                                    "Cannot remove a value from a single "
                                    "valued property, unset must be used. The "
                                    "property name is '%(name)s' and the "
                                    "current value is '%(value)s'") %
                                    {"name":n, "value":self.properties[n]})
                        for v in remove_prop_values[n]:
                                try:
                                        self.properties[n].remove(v)
                                except ValueError:
                                        raise api_errors.InvalidPropertyValue(_(
                                            "Cannot remove the value %(value)s "
                                            "from the property %(name)s "
                                            "because the value is not in the "
                                            "property's list.") %
                                            {"value":v, "name":n})
                self.__delay_validation = False
                self.__validate_properties()

        def __validate_properties(self):
                """Check that the properties set for this publisher are
                consistent with each other."""

                if self.__properties.get(SIGNATURE_POLICY, "") == \
                    "require-names":
                        if not self.__properties.get("signature-required-names",
                            None):
                                raise api_errors.InvalidPropertyValue(_(
                                    "At least one name must be provided for "
                                    "the signature-required-names policy."))

        def __format_safe_read_crl(self, pth):
                """CRLs seem to frequently come in DER format, so try reading
                the CRL using both of the formats before giving up."""

                try:
                        return m2.X509.load_crl(pth)
                except m2.X509.X509Error:
                        try:
                                return m2.X509.load_crl(pth,
                                    format=m2.X509.FORMAT_DER)
                        except m2.X509.X509Error:
                                raise api_errors.BadFileFormat(_("The CRL file "
                                    "%s is not in a recognized format.") %
                                    pth)

        def __get_crl(self, uri):
                """Given a URI (for now only http URIs are supported), return
                the CRL object created from the file stored at that uri."""

                uri = uri.strip()
                if uri.startswith("Full Name:"):
                        uri = uri[len("Full Name:"):]
                        uri = uri.strip()
                if uri.startswith("URI:"):
                        uri = uri[4:]
                if not uri.startswith("http://") and \
                    not uri.startswith("file://"):
                        raise api_errors.InvalidResourceLocation(uri.strip())
                crl_host = DebugValues.get_value("crl_host")
                if crl_host:
                        orig = urlparse.urlparse(uri)
                        crl = urlparse.urlparse(crl_host)
                        uri = urlparse.urlunparse(urlparse.ParseResult(
                            scheme=crl.scheme, netloc=crl.netloc,
                            path=orig.path,
                            params=orig.params, query=orig.params,
                            fragment=orig.fragment))
                fn = urllib.quote(uri, "")
                assert os.path.isdir(self.__crl_root)
                fpath = os.path.join(self.__crl_root, fn)
                crl = None
                # Check if we already have a CRL for this URI.
                if os.path.exists(fpath):
                        # If we already have a CRL, check whether it's time
                        # to retrieve a new one from the location.
                        crl = self.__format_safe_read_crl(fpath)
                        nu = crl.get_next_update().get_datetime()
                        # get_datetime is supposed to return a UTC time, so
                        # assert that's the case.
                        assert nu.tzinfo.utcoffset(nu) == dt.timedelta(0)
                        # Add timezone info to cur_time so that cur_time and
                        # nu can be compared.
                        cur_time = dt.datetime.now(nu.tzinfo)
                        if cur_time < nu:
                                return crl
                # If no CRL already exists or it's time to try to get a new one,
                # try to retrieve it from the server.
                tmp_pth = fpath + ".tmp"
                with open(tmp_pth, "wb") as fh:
                        hdl = pycurl.Curl()
                        hdl.setopt(pycurl.URL, uri)
                        hdl.setopt(pycurl.WRITEDATA, fh)
                        hdl.setopt(pycurl.FAILONERROR, 1)
                        try:
                                hdl.perform()
                        except pycurl.error:
                                # If we should treat failure to get a new CRL
                                # as a failure, raise an exception here. If not,
                                # if we should use an old CRL if it exists,
                                # return that here. If none is available and
                                # that means the cert should not be treated as
                                # revoked, return None here.
                                return crl
                try:
                        ncrl = self.__format_safe_read_crl(tmp_pth)
                except api_errors.BadFileFormat:
                        portable.remove(tmp_pth)
                        return crl
                portable.rename(tmp_pth, fpath)
                return ncrl

        def __check_crls(self, cert, ca_dict):
                """Determines whether the certificate has been revoked by its
                CRL.

                The 'cert' parameter is the certificate to check for revocation.

                The 'ca_dict' is a dictionary which maps subject hashes to
                certs treated as trust anchors."""

                # If the certificate doesn't have a CRL location listed, treat
                # it as valid.
                try:
                        ext = cert.get_ext("crlDistributionPoints")
                except LookupError, e:
                        return True
                uri = ext.get_value()
                crl = self.__get_crl(uri)
                # If we couldn't retrieve a CRL from the distribution point
                # and no CRL is cached on disk, assume the cert has not been
                # revoked.  It's possible that this should be an image or
                # publisher setting in the future.
                if not crl:
                        return True

                # A CRL has been found, now it needs to be validated like
                # a certificate is.
                verified_crl = False
                crl_issuer = crl.get_issuer()
                tas = ca_dict.get(crl_issuer.as_hash(), [])
                for t in tas:
                        try:
                                if crl.verify(t.get_pubkey()):
                                        # If t isn't approved for signing crls,
                                        # the exception __check_extensions
                                        # raises will take the code to the
                                        # except below.
                                        self.__check_extensions(t,
                                            CRL_SIGNING_USE, 0)
                                        verified_crl = True
                        except api_errors.SigningException:
                                pass
                if not verified_crl:
                        crl_cas = self.__get_certs_by_name(crl_issuer)
                        for c in crl_cas:
                                if crl.verify(c.get_pubkey()):
                                        try:
                                                self.verify_chain(c, ca_dict, 0,
                                                    usages=CRL_SIGNING_USE,)
                                        except api_errors.SigningException:
                                                pass
                                        else:
                                                verified_crl = True
                                                break
                if not verified_crl:
                        return True
                # For a certificate to be revoked, its CRL must be validated
                # and revoked the certificate.
                rev = crl.is_revoked(cert)
                if rev:
                        raise api_errors.RevokedCertificate(cert, rev[1])

        def __check_revocation(self, cert, ca_dict):
                txt = cert.as_text() + cert.as_pem()
                hsh = self.__hash_cert(txt)
                if hsh in self.revoked_ca_certs:
                        raise api_errors.RevokedCertificate(cert,
                            "User manually revoked certificate.")
                self.__check_crls(cert, ca_dict)

        def __check_extensions(self, cert, usages, cur_pathlen):
                """Check whether the critical extensions in this certificate
                are supported and allow the provided use(s)."""

                def check_values(vs):
                        for v in vs:
                                if v in supported_vs:
                                        continue
                                if v.startswith("PATHLEN:") and \
                                    "PATHLEN:" in supported_vs:
                                        try:
                                                cert_pathlen = int(v[len("PATHLEN:"):])
                                        except ValueError, e:
                                                raise api_errors.UnsupportedExtensionValue(cert, ext, v)
                                        if cur_pathlen > cert_pathlen:
                                                raise api_errors.PathlenTooShort(cert, cur_pathlen, cert_pathlen)
                                        continue
                                if len(vs) < 2:
                                        raise api_errors.UnsupportedExtensionValue(cert, ext)
                                else:
                                        raise api_errors.UnsupportedExtensionValue(cert, ext, v)


                for i in range(0, cert.get_ext_count()):
                        ext = cert.get_ext_at(i)
                        name = ext.get_name()
                        v = ext.get_value().upper()
                        # Check whether the extension name is recognized.
                        if name in SUPPORTED_EXTENSION_VALUES:
                                supported_vs = \
                                    SUPPORTED_EXTENSION_VALUES[name]
                                vs = [s.strip() for s in v.split(",")]
                                # Check whether the values for the extension are
                                # recognized.
                                check_values(vs)
                                uses = usages.get(name, [])
                                if isinstance(uses, basestring):
                                        uses = [uses]
                                # For each use, check to see whether it's
                                # permitted by the certificate's extension
                                # values.
                                for u in uses:
                                        if u not in vs:
                                                raise api_errors.InappropriateCertificateUse(cert, ext, u)
                        # If the extension name is unrecognized and critical,
                        # then the chain cannot be verified.
                        elif ext.get_critical():
                                raise api_errors.UnsupportedCriticalExtension(
                                    cert, ext)
        
        def verify_chain(self, cert, ca_dict, cur_pathlen, required_names=None,
            usages=None):
                """Validates the certificate against the given trust anchors.

                The 'cert' parameter is the certificate to validate.

                The 'ca_dict' parameter is a dictionary which maps subject
                hashes to certs treated as trust anchors.

                The 'cur_pathlen' parameter is an integer indicating how many
                certificates have been found between cert and the leaf cert.

                The 'required_names' parameter is a set of strings that must
                be seen as a CN in the chain of trust for the certificate."""

                if required_names is None:
                        required_names = set()
                verified = False
                continue_loop = True
                certs_with_problems = []

                ca_dict = copy.copy(ca_dict)
                for k, v in self.get_ca_certs().iteritems():
                        if k in ca_dict:
                                ca_dict[k].extend(v)
                        else:
                                ca_dict[k] = v

                def merge_dicts(d1, d2):
                        """Function for merging usage dictionaries."""
                        res = copy.deepcopy(d1)
                        for k in d2:
                                if k in res:
                                        res[k].extend(d2[k])
                                else:
                                        res[k] = d2[k]
                        return res

                def discard_names(cert, required_names):
                        for cert_cn in [
                            str(c.get_data())
                            for c
                            in cert.get_subject().get_entries_by_nid(
                                m2.X509.X509_Name.nid["CN"])
                        ]:
                                required_names.discard(cert_cn)

                if not usages:
                        usages = {}
                        for u in POSSIBLE_USES:
                                usages = merge_dicts(usages, u)

                # Check whether we can validate this certificate.
                self.__check_extensions(cert, usages, cur_pathlen)

                # Check whether this certificate has been revoked.
                self.__check_revocation(cert, ca_dict)

                while continue_loop:
                        # If this certificate's CN is in the set of required
                        # names, remove it.
                        discard_names(cert, required_names)

                        # Find the certificate that issued this certificate.
                        issuer = cert.get_issuer()
                        issuer_hash = issuer.as_hash()

                        # See whether this certificate was issued by any of the
                        # given trust anchors.
                        for c in ca_dict.get(issuer_hash, []):
                                if cert.verify(c.get_pubkey()):
                                        verified = True
                                        # Remove any required names found in the
                                        # trust anchor.
                                        discard_names(c, required_names)
                                        # If there are more names to check for
                                        # continue up the chain of trust to look
                                        # for them.
                                        if not required_names:
                                                continue_loop = False
                                        break

                        # If the subject and issuer for this certificate are
                        # identical and the certificate hasn't been verified
                        # then this is an untrusted self-signed cert and should
                        # be rejected.
                        if cert.get_subject().as_hash() == issuer_hash:
                                if not verified:
                                        raise \
                                            api_errors.UntrustedSelfSignedCert(
                                            cert)
                                # This break should break the
                                # while continue_loop loop.
                                break

                        # If the certificate hasn't been issued by a trust
                        # anchor or more names need to be found, continue
                        # looking up the chain of trust.
                        if continue_loop:
                                up_chain = False
                                # Keep track of certs that would have verified
                                # this certificate but had critical extensions
                                # we can't handle yet for error reporting.
                                certs_with_problems = []
                                for c in self.__get_certs_by_name(issuer):
                                        # If the certificate is approved to
                                        # sign another certificate, verifies
                                        # the current certificate, and hasn't
                                        # been revoked, consider it as the
                                        # next link in the chain.  check_ca
                                        # checks both the basicConstraints
                                        # extension and the keyUsage extension.
                                        if c.check_ca() and \
                                            cert.verify(c.get_pubkey()):
                                                problem = False
                                                # Check whether this certificate
                                                # has a critical extension we
                                                # don't understand.
                                                try:
                                                        self.__check_extensions(
                                                            c, CERT_SIGNING_USE,
                                                            cur_pathlen)
                                                        self.__check_revocation(c,
                                                            ca_dict)
                                                except (api_errors.UnsupportedCriticalExtension, api_errors.RevokedCertificate), e:
                                                        certs_with_problems.append(e)
                                                        problem = True
                                                # If this certificate has no
                                                # problems with it, it's the
                                                # next link in the chain so make
                                                # it the current certificate and
                                                # add one to cur_pathlen since
                                                # there's one more chain cert
                                                # between the code signing cert
                                                # and the root of the chain.
                                                if not problem:
                                                        up_chain = True
                                                        cert = c
                                                        cur_pathlen += 1
                                                        break
                                # If there's not another link in the chain to be
                                # found, stop the iteration.
                                if not up_chain:
                                        continue_loop = False
                # If the certificate wasn't verified against a trust anchor,
                # raise an exception.
                if not verified:
                        raise api_errors.BrokenChain(cert,
                            certs_with_problems)

        alias = property(lambda self: self.__alias, __set_alias,
            doc="An alternative name for a publisher.")

        client_uuid = property(lambda self: self.__client_uuid,
            __set_client_uuid,
            doc="A Universally Unique Identifier (UUID) used to identify a "
            "client image to a publisher.")

        disabled = property(lambda self: self.__disabled, __set_disabled,
            doc="A boolean value indicating whether the publisher should be "
            "used for packaging operations.")

        last_refreshed = property(__get_last_refreshed, __set_last_refreshed,
            doc="A datetime object representing the time (in UTC) the "
                "publisher's selected repository was last refreshed for new "
                "metadata (such as catalog updates).  'None' if the publisher "
                "hasn't been refreshed yet or the time is not available.")

        meta_root = property(lambda self: self.__meta_root, __set_meta_root,
            doc="The absolute pathname of the directory where the publisher's "
                "metadata should be written to and read from.")

        prefix = property(lambda self: self.__prefix, __set_prefix,
            doc="The name of the publisher.")

        repositories = property(lambda self: self.__repositories,
            doc="A list of repository objects that belong to the publisher.")

        selected_repository = property(lambda self: self.__selected_repository,
            __set_selected_repository,
            doc="A reference to the selected repository object.")

        sticky = property(lambda self: self.__sticky, __set_stickiness,
            doc="Whether or not installed packages from this publisher are"
                " always preferred to other publishers.")

        def __get_prop(self, name):
                """Accessor method for properties dictionary"""
                return self.__properties[name]

        @staticmethod
        def __read_list(list_str):
                """Take a list in string representation and convert it back
                to a Python list."""

                list_str = list_str.encode("utf-8")
                # Strip brackets and any whitespace
                list_str = list_str.strip("][ ")
                # Strip comma and any whitespeace
                lst = list_str.split(", ")
                # Strip empty whitespace, single, and double quotation marks
                lst = [ s.strip("' \"") for s in lst ]
                # Eliminate any empty strings
                lst = [ s for s in lst if s != '' ]

                return lst

        def __set_prop(self, name, values):
                """Accessor method to add a property"""

                if name == SIGNATURE_POLICY:
                        self.__sig_policy = None
                        if isinstance(values, basestring):
                                values = [values]
                        policy_name = values[0]
                        if policy_name not in sigpolicy.Policy.policies():
                                raise api_errors.InvalidPropertyValue(_(
                                    "%(val)s is not a valid value for this "
                                    "property:%(prop)s") % {"val": policy_name,
                                    "prop": SIGNATURE_POLICY})
                        if policy_name == "require-names":
                                if self.__delay_validation:
                                        # If __delay_validation is set, then
                                        # it's possible that
                                        # signature-required-names was
                                        # set by a previous call to set_prop
                                        # file.  If so, don't overwrite the
                                        # values that have already been read.
                                        self.__properties.setdefault(
                                            "signature-required-names", [])
                                        self.__properties[
                                            "signature-required-names"].extend(
                                            values[1:])
                                else:
                                        self.__properties[
                                            "signature-required-names"] = \
                                            values[1:]
                                        self.__validate_properties()
                        else:
                                if len(values) > 1:
                                        raise api_errors.InvalidPropertyValue(_(
                                            "The %s signature-policy takes no "
                                            "argument.") % policy_name)
                        self.__properties[SIGNATURE_POLICY] = policy_name
                        return
                if name == "signature-required-names":
                        if isinstance(values, basestring):
                                values = self.__read_list(values)
                self.__properties[name] = values

        def __del_prop(self, name):
                """Accessor method for properties"""
                del self.__properties[name]

        def __prop_iter(self):
                return self.__properties.__iter__()

        def __prop_iteritems(self):
                """Support iteritems on properties"""
                return self.__properties.iteritems()

        def __prop_keys(self):
                """Support keys() on properties"""
                return self.__properties.keys()

        def __prop_values(self):
                """Support values() on properties"""
                return self.__properties.values()

        def __prop_getdefault(self, name, value):
                """Support getdefault() on properties"""
                return self.__properties.get(name, value)

        def __prop_setdefault(self, name, value):
                """Support setdefault() on properties"""
                # Must set it this way so that the logic in __set_prop is used.
                try:
                        return self.__properties[name]
                except KeyError:
                        self.properties[name] = value
                        return value

        def __prop_update(self, d):
                """Support update() on properties"""

                for k, v in d.iteritems():
                        # Must iterate through each value and
                        # set it this way so that the logic
                        # in __set_prop is used.
                        self.properties[k] = v

        def __prop_pop(self, d, default):
                """Support pop() on properties"""
                return self.__properties.pop(d, default)

        properties = DictProperty(__get_prop, __set_prop, __del_prop,
            __prop_iteritems, __prop_keys, __prop_values, __prop_iter,
            doc="A dict holding the properties for an image.",
            fgetdefault=__prop_getdefault, fsetdefault=__prop_setdefault,
            update=__prop_update, pop=__prop_pop)

        @property
        def signature_policy(self):
                """Return the signature policy for the publisher."""

                if self.__sig_policy is not None:
                        return self.__sig_policy
                txt = self.properties.get(SIGNATURE_POLICY,
                    sigpolicy.DEFAULT_POLICY)
                names = self.properties.get("signature-required-names", [])
                self.__sig_policy = sigpolicy.Policy.policy_factory(txt, names)
                return self.__sig_policy
