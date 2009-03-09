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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import cherrypy
import pkg.catalog
import pkg.version
import pkg.server.api_errors as api_errors

CURRENT_API_VERSION = 2

class BaseInterface(object):
        """This class represents a base API object that is provided by the
        server to clients.  A base API object is required when creating
        objects for any other interface provided by the API.  This allows
        the server to provide a set of private object references that are
        needed by interfaces to provide functionality to clients.
        """

        # A semi-private reference to a cherrypy request object.
        _request = None
        # A semi-private reference to a SvrConfig object.
        _svrconfig = None
        # A semi-private reference to a RepositoryConfig object.
        _rcconfig = None

        def __init__(self, request, svrconfig, rcconfig):
                self._request = request
                self._svrconfig = svrconfig
                self._rcconfig = rcconfig

class _Interface(object):
        """Private base class used for api interface objects.
        """
        def __init__(self, version_id, base):
                compatible_versions = set([2])
                if version_id not in compatible_versions:
                        raise api_errors.VersionException(CURRENT_API_VERSION,
                            version_id)

class CatalogInterface(_Interface):
        """This class presents an interface to server catalog objects that
        clients may use.
        """

        def __init__(self, version_id, base):
                _Interface.__init__(self, version_id, base)
                catalog = None
                if not base._svrconfig.is_mirror():
                        catalog = base._svrconfig.catalog
                self.__catalog = catalog

        def fmris(self):
                """Returns a list of FMRIs as it iterates over the contents of
                the server's catalog.  Returns an empty list if the catalog is
                not available.
                """
                if not self.__catalog:
                        return []
                return self.__catalog.fmris()

        def get_matching_pattern_fmris(self, patterns):
                """Returns a sorted list of PkgFmri objects, newest versions
                first, for packages matching those found in the 'patterns' list.
                """
                c = self.__catalog
                if not c:
                        return []
                return pkg.catalog.extract_matching_fmris(c.fmris(),
                    patterns=patterns)

        def get_matching_version_fmris(self, versions):
                """Returns a sorted list of PkgFmri objects, newest versions
                first, for packages matching those found in the 'versions' list.

                'versions' should be a list of strings of the format:
                    release,build_release-branch:datetime 

                ...with a value of '*' provided for any component to be ignored.
                '*' or '?' may be used within each component value and will act
                as wildcard characters ('*' for one or more characters, '?' for
                a single character).
                """
                c = self.__catalog
                if not c:
                        return []

                return pkg.catalog.extract_matching_fmris(c.fmris(),
                    versions=versions)

        @property
        def last_modified(self):
                """Returns a datetime object representing the date and time at
                which the catalog was last modified.  Returns None if not
                available.
                """
                if not self.__catalog:
                        return None
                lm = self.__catalog.last_modified()
                if not lm:
                        return None
                return pkg.catalog.ts_to_datetime(lm)

        @property
        def package_count(self):
                """The total number of packages in the catalog.  Returns None
                if the catalog is not available.
                """
                if not self.__catalog:
                        return None
                return self.__catalog.npkgs()

        def search(self, token):
                """Searches the catalog for 'token'.  Returns a generator object
                for a list of token type / fmri pairs or an empty list if search
                is not available.  search_done() must be called after the caller
                has finished retrieving the results of this function for proper
                cleanup.
                """
                if not self.search_available:
                        return []
                return self.__catalog.search(token)

        @property
        def search_available(self):
                """Returns a Boolean value indicating whether search
                functionality is available for the catalog.
                """
                if not self.__catalog:
                        return False
                return self.__catalog.search_available()

        def search_done(self):
                """Indicates that a client is finished retrieving results from
                search(); this function must be called after search() for proper
                cleanup.  Does not return a value.
                """
                self.__catalog.query_engine.search_done()

class ConfigInterface(_Interface):
        """This class presents a read-only interface to configuration
        information and statistics about the depot that clients may use.
        """

        def __init__(self, version_id, base):
                _Interface.__init__(self, version_id, base)
                self.__svrconfig = base._svrconfig
                self.__rcconfig = base._rcconfig

        @property
        def catalog_requests(self):
                """The number of /catalog operation requests that have occurred
                during the current server session.
                """
                return self.__svrconfig.catalog_requests

        @property
        def content_root(self):
                """The file system path where the server's content and web
                directories are located.
                """
                return self.__svrconfig.content_root

        @property
        def file_requests(self):
                """The number of /file operation requests that have occurred
                during the current server session.
                """
                return self.__svrconfig.file_requests

        @property
        def filelist_requests(self):
                """The number of /filelist operation requests that have occurred
                during the current server session.
                """
                return self.__svrconfig.flist_requests

        @property
        def filelist_file_requests(self):
                """The number of files served by /filelist operations requested
                during the current server session.
                """
                return self.__svrconfig.flist_files

        @property
        def in_flight_transactions(self):
                """The number of package transactions awaiting completion.
                """
                return len(self.__svrconfig.in_flight_trans)

        @property
        def manifest_requests(self):
                """The number of /manifest operation requests that have occurred
                during the current server session.
                """
                return self.__svrconfig.manifest_requests

        @property
        def mirror(self):
                """A Boolean value indicating whether the server is currently
                operating in mirror mode.
                """
                return self.__svrconfig.mirror

        @property
        def readonly(self):
                """A Boolean value indicating whether the server is currently
                operating in readonly mode.
                """
                return self.__svrconfig.read_only

        @property
        def rename_requests(self):
                """The number of /rename operation requests that have occurred
                during the current server session.
                """
                return self.__svrconfig.pkgs_renamed

        @property
        def web_root(self):
                """The file system path where the server's web content is
                located.
                """
                return self.__svrconfig.web_root


        def get_repo_attrs(self):
                """Returns a dictionary of repository configuration
                attributes organized by section, with each section's keys
                as a list.

                Available attributes are as follows:

                Section         Attribute       Description
                ==========      ==========      ===============
                repository      name            A short, descriptive name for
                                                the repository.

                                description     A descriptive paragraph for the
                                                repository.

                                maintainer      A human readable string
                                                describing the entity
                                                maintaining the repository.  For
                                                an individual, this string is
                                                expected to be their name or
                                                name and email.

                                maintainer_url  A URL associated with the entity
                                                maintaining the repository.

                                detailed_url    One or more URLs to pages or
                                                sites with further information
                                                about the repository.

                feed            id              A Universally Unique Identifier
                                                (UUID) used to permanently,
                                                uniquely identify the feed.

                                name            A short, descriptive name for
                                                RSS/Atom feeds generated by the
                                                depot serving the repository.

                                description     A descriptive paragraph for the
                                                feed.

                                publisher       A fully-qualified domain name or
                                                email address that is used to
                                                generate a unique identifier for
                                                each entry in the feed.

                                icon            A filename of a small image that
                                                is used to visually represent
                                                the feed.

                                logo            A filename of a large image that
                                                is used by user agents to
                                                visually brand or identify the
                                                feed.

                                window          A numeric value representing the
                                                number of hours, before the feed
                                                for the repository was last
                                                generated, to include when
                                                creating the feed for the
                                                repository updatelog.
                """
                return self.__rcconfig.get_attributes()

        def get_repo_attr_value(self, section, attr):
                """Returns the current value of a repository configuration
                attribute for the specified section.
                """
                return self.__rcconfig.get_attribute(section, attr)

class RequestInterface(_Interface):
        """This class presents an interface to server request objects that
        clients may use.
        """

        def __init__(self, version_id, base):
                _Interface.__init__(self, version_id, base)
                self.__request = base._request

        def get_accepted_languages(self):
                """Returns a list of the languages accepted by the client
                sorted by priority.  This information is derived from the
                Accept-Language header provided by the client.
                """
                alist = []
                for entry in self.__request.headers.elements("Accept-Language"):
                        alist.append(str(entry).split(";")[0])

                return alist

        def get_rel_path(self, uri):
                """Returns uri relative to the current request path.
                """
                return pkg.misc.get_rel_path(self.__request, uri)

        def log(self, msg):
                """Instruct the server to log the provided message to its error
                logs.
                """
                return cherrypy.log(msg)

        @property
        def params(self):
                """A dict containing the parameters sent in the request, either
                in the query string or in the request body.
                """
                return self.__request.params

        @property
        def path_info(self):
                """A string containing the "path_info" portion of the requested
                URL.
                """
                return self.__request.path_info

        def url(self, path='', qs='', script_name=None, relative=None):
                """Create an absolute URL for the given path.

                If 'path' starts with a slash ('/'), this will return (base +
                script_name + path + qs).  If it does not start with a slash,
                this returns (base url + script_name [+ request.path_info] +
                path + qs).

                If script_name is None, an appropriate value will be
                automatically determined from the current request path.

                If no parameters are specified, an absolute URL for the current
                request path (minus the querystring) by passing no args.  If
                url(qs=cherrypy.request.query_string), is called, the original
                client URL (assuming no internal redirections) should be
                returned.

                If relative is None or not provided, an appropriate value will
                be automatically determined.  If False, the output will be an
                absolute URL (including the scheme, host, vhost, and
                script_name).  If True, the output will instead be a URL that
                is relative to the current request path, perhaps including '..'
                atoms.  If relative is the string 'server', the output will
                instead be a URL that is relative to the server root; i.e., it
                will start with a slash.
                """
                return cherrypy.url(path=path, qs=qs, script_name=script_name,
                    relative=relative)

