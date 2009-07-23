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
import datetime as dt
import errno
import os
import pkg.client.api_errors as api_errors
import pkg.misc as misc
import pkg.portable as portable
import pkg.Uuid25
import shutil
import time
import urlparse

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
SUPPORTED_SCHEMES = set(("http", "https"))

# SSL Protocol Schemes
SSL_SCHEMES = set(("https",))

# Supported RepositoryURI sorting policies.
URI_SORT_PRIORITY = "priority"

# Sort policy mapping.
URI_SORT_POLICIES = {
    URI_SORT_PRIORITY: lambda obj: (obj.priority, obj.uri),
}

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
                if not netloc or not misc.valid_pub_url(uri):
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
        __client_uuid = None
        __disabled = False
        __meta_root = None
        __prefix = None
        __selected_repository = None
        __repositories = []

        # Used to store the id of the original object this one was copied
        # from during __copy__.
        _source_object_id = None

        def __init__(self, prefix, alias=None, client_uuid=None, disabled=False,
            meta_root=None, repositories=None, selected_repository=None):
                """Initialize a new publisher object."""

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
                self.meta_root = meta_root
                self.prefix = prefix

                if repositories:
                        for r in repositories:
                                self.add_repository(r)

                if selected_repository:
                        self.selected_repository = selected_repository

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
                    selected_repository=selected)
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

        def __set_prefix(self, prefix):
                if not misc.valid_pub_prefix(prefix):
                        raise api_errors.BadPublisherPrefix(prefix)
                self.__prefix = prefix

        def __set_selected_repository(self, value):
                if not isinstance(value, Repository) or \
                    value not in self.repositories:
                        raise api_errors.UnknownRepository(value)
                self.__selected_repository = value

        def __set_client_uuid(self, value):
                self.__client_uuid = value

        def __str__(self):
                return self.prefix

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

        def create_meta_root(self):
                """Create the publisher's meta_root."""

                if not self.meta_root:
                        raise api_errors.BadPublisherMetaRoot(self.meta_root,
                            operation="create_meta_root")

                try:
                        os.makedirs(self.meta_root)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        elif e.errno != errno.EEXIST:
                                # If the meta_root already exists, move on.
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

        def get_ssl_creds(self):
                """Deprecated"""

                origin = self.selected_repository.origins[0]
                return (origin.ssl_key, origin.ssl_cert)

        @property
        def needs_refresh(self):
                """A boolean value indicating whether the publisher's
                metadata for the currently selected repository needs to be
                refreshed."""

                if not self.selected_repository or not self.meta_root:
                        # Nowhere to obtain metadata from; this should rarely
                        # occur except during publisher initialization.
                        return False

                cfile = os.path.join(self.meta_root, "catalog")
                if not os.path.exists(cfile):
                        # If metadata is missing, a refresh is needed.
                        return True

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

                self.__client_uuid = str(pkg.Uuid25.uuid1())

        def set_origin(self, origin):
                """Deprecated"""

                r = self.selected_repository
                r.reset_origins()
                r.add_origin(origin)

        def set_selected_repository(self, name=None, origin=None):
                """Sets the selected repository for the publisher to the
                repository object matching the name or that has a matching
                origin URI."""

                self.__selected_repository = self.get_repository(name=name,
                    origin=origin)

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
