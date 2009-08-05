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
import itertools
import pkg.server.catalog
import pkg.fmri
import pkg.version
import pkg.server.api_errors as api_errors
import pkg.server.query_parser as qp
import pkg.version as version

CURRENT_API_VERSION = 5

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
                compatible_versions = set([3, 4, 5])
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
                return pkg.server.catalog.extract_matching_fmris(c.fmris(),
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

                return pkg.server.catalog.extract_matching_fmris(c.fmris(),
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
                return pkg.server.catalog.ts_to_datetime(lm)

        @property
        def package_count(self):
                """The total number of packages in the catalog.  Returns None
                if the catalog is not available.
                """
                if not self.__catalog:
                        return None
                return self.__catalog.npkgs()

        def search(self, tokens, case_sensitive=False,
            return_type=qp.Query.RETURN_PACKAGES, start_point=None,
            num_to_return=None, matching_version=None, return_latest=False):
                """Searches the catalog for actions or packages (as determined
                by 'return_type') matching the specified 'tokens'.

                'tokens' is a string using pkg(5) query syntax.

                'case_sensitive' is an optional, boolean value indicating
                whether matching entries must have the same case as that of
                the provided tokens.

                'return_type' is an optional, constant value indicating the
                type of results to be returned.  This constant value should be
                one provided by the pkg.server.query_parser.Query class.

                'start_point' is an optional, integer value indicating how many
                search results should be discarded before returning any results.
                None is interpreted to mean 0.

                'num_to_return' is an optional, integer value indicating how
                many search results should be returned.  None means return all
                results.

                'matching_version' is a string in the format expected by the
                pkg.version.MatchingVersion class that will be used to further
                filter the search results as they are retrieved.

                'return_latest' is an optional, boolean value that will cause
                only the latest versions of packages to be returned.  Ignored
                if 'return_type' is not qp.Query.RETURN_PACKAGES.
                """

                if not tokens:
                        return []

                tokens = tokens.split()
                if not self.search_available:
                        return []

                if start_point is None:
                        start_point = 0

                def filter_results(results, mver):
                        found = 0
                        last_stem = None
                        for result in results:
                                if found and \
                                    ((found - start_point) >= num_to_return):
                                        break

                                if result[1] == qp.Query.RETURN_PACKAGES:
                                        pfmri = result[2]
                                elif result[1] == qp.Query.RETURN_ACTIONS:
                                        pfmri = result[2][0]

                                if mver is not None:
                                        if mver != version.Version(pfmri.split(
                                            "@", 1)[1], None):
                                                continue

                                if return_latest and \
                                    result[1] == qp.Query.RETURN_PACKAGES:
                                        # Latest version filtering can only be
                                        # done for packages as only they are
                                        # guaranteed to be in version order.
                                        stem = result[2].split("@", 1)[0]
                                        if last_stem == stem:
                                                continue
                                        else:
                                                last_stem = stem

                                found += 1
                                if found > start_point:
                                        yield result

                def filtered_search(results, mver):
                        try:
                                result = results.next()
                        except StopIteration:
                                return

                        return_type = result[1]
                        results = itertools.chain([result], results)

                        if return_latest and \
                            return_type == qp.Query.RETURN_PACKAGES:
                                def cmp_fmris(resa, resb):
                                        a = pkg.fmri.PkgFmri(resa[2])
                                        b = pkg.fmri.PkgFmri(resb[2])

                                        if a.pkg_name == b.pkg_name:
                                                # Version in descending order.
                                                return cmp(a.version,
                                                    b.version) * -1
                                        return cmp(a, b)
                                return filter_results(sorted(results,
                                    cmp=cmp_fmris), mver)

                        return filter_results(results, mver)

                if matching_version or return_latest:
                        # Additional filtering needs to be performed and
                        # the results yielded one by one.
                        mver = None
                        if matching_version:
                                mver = version.MatchingVersion(matching_version,
                                    None)

                        # Results should be retrieved here so that an exception
                        # can be immediately raised.
                        query = qp.Query(" ".join(tokens), case_sensitive,
                            return_type, None, None)
                        results = self.__catalog.search(query)

                        return filtered_search(results, mver)

                query = qp.Query(" ".join(tokens), case_sensitive,
                    return_type, num_to_return, start_point)
                return self.__catalog.search(query)

        @property
        def search_available(self):
                """Returns a Boolean value indicating whether search
                functionality is available for the catalog.
                """
                if not self.__catalog:
                        return False
                return self.__catalog.search_available()


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

                Section     Attribute           Description
                ==========  ==========          ===============
                publisher   alias               An alternative name for the
                                                publisher of the packages in
                                                the repository.

                            prefix              The name of the publisher of
                                                the packages in the repository.

                repository  collection_type     A constant value indicating the
                                                type of packages in the
                                                repository.  See the pydoc for
                                                pkg.client.publisher.Repository
                                                for details.

                            description         A string value containing a
                                                descriptive paragraph for the
                                                repository.

                            detailed_url        A comma-separated list of URIs
                                                where more information about the
                                                repository can be found.

                            legal_uris          A comma-separated list of URIs
                                                where licensing, legal, and
                                                terms of service information
                                                for the repository can be found.

                            maintainer          A human readable string
                                                describing the entity
                                                maintaining the repository.  For
                                                an individual, this string is
                                                expected to be their name or
                                                name and email.

                            maintainer_url      A URI associated with the entity
                                                maintaining the repository.

                            mirrors             A comma-separated list of URIs
                                                where package content can be
                                                retrieved.

                            name                A short, descriptive name for
                                                the repository.

                            origins             A comma-separated list of URIs
                                                where package metadata can be
                                                retrieved.

                            refresh_seconds     An integer value indicating the
                                                number of seconds clients should
                                                wait before refreshing cached
                                                repository catalog or repository
                                                metadata information.

                            registration_uri    A URI indicating a location
                                                clients can use to register or
                                                obtain credentials needed to
                                                access the repository.

                            related_uris        A comma-separated list of URIs
                                                of related repositories that a
                                                client may be interested in.

                feed        id                  A Universally Unique Identifier
                                                (UUID) used to permanently,
                                                uniquely identify the feed.

                            name                A short, descriptive name for
                                                RSS/Atom feeds generated by the
                                                depot serving the repository.

                            description         A descriptive paragraph for the
                                                feed.

                            publisher           A fully-qualified domain name or
                                                email address that is used to
                                                generate a unique identifier for
                                                each entry in the feed.

                            icon                A filename of a small image that
                                                is used to visually represent
                                                the feed.

                            logo                A filename of a large image that
                                                is used by user agents to
                                                visually brand or identify the
                                                feed.

                            window              A numeric value representing the
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

        @property
        def query_string(self):
                """A string containing the "query_string" portion of the
                requested URL.
                """
                return cherrypy.request.query_string

        def url(self, path="", qs="", script_name=None, relative=None):
                """Create an absolute URL for the given path.

                If 'path' starts with a slash ('/'), this will return (base +
                script_name + path + qs).  If it does not start with a slash,
                this returns (base url + script_name [+ request.path_info] +
                path + qs).

                If script_name is None, an appropriate value will be
                automatically determined from the current request path.

                If no parameters are specified, an absolute URL for the current
                request path (minus the querystring) by passing no args.  If
                url(qs=request.query_string), is called, the original client URL
                (assuming no internal redirections) should be returned.

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

