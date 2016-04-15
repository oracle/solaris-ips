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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

import cherrypy
import itertools
import os
import six

from functools import cmp_to_key
from io import BytesIO
from operator import itemgetter

import pkg.catalog
import pkg.client.pkgdefs as pkgdefs
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.server.api_errors as api_errors
import pkg.server.repository as srepo
import pkg.server.query_parser as qp
import pkg.version as version

from pkg.api_common import (PackageInfo, LicenseInfo, PackageCategory,
    _get_pkg_cat_data)

CURRENT_API_VERSION = 12

class BaseInterface(object):
        """This class represents a base API object that is provided by the
        server to clients.  A base API object is required when creating
        objects for any other interface provided by the API.  This allows
        the server to provide a set of private object references that are
        needed by interfaces to provide functionality to clients.
        """

        def __init__(self, request, depot, pub):
                # A protected reference to a pkg.server.depot object.
                self._depot = depot

                # A protected reference to a cherrypy request object.
                self._request = request

                # A protected reference to the publisher this interface is for.
                self._pub = pub


class _Interface(object):
        """Private base class used for api interface objects.
        """
        def __init__(self, version_id, base):
                compatible_versions = set([CURRENT_API_VERSION])
                if version_id not in compatible_versions:
                        raise api_errors.VersionException(CURRENT_API_VERSION,
                            version_id)

                self._depot = base._depot
                self._pub = base._pub
                self._request = base._request

class CatalogInterface(_Interface):
        """This class presents an interface to server catalog objects that
        clients may use.
        """

        # Constants used to reference specific values that info can return.
        INFO_FOUND = 0
        INFO_MISSING = 1
        INFO_ILLEGALS = 3

        # Constants for some state information returned by package matching
        # functions.
        PKG_STATE_OBSOLETE = pkgdefs.PKG_STATE_OBSOLETE
        PKG_STATE_RENAMED = pkgdefs.PKG_STATE_RENAMED

        def fmris(self, ordered=False):
                """A generator function that produces FMRIs as it iterates
                over the contents of the server's catalog.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis."""

                try:
                        c = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return iter(())
                return c.fmris(ordered=ordered)

        def gen_allowed_packages(self, pfmris, build_release=None,
            excludes=misc.EmptyI):
                """A generator function that produces a list of tuples of the
                form (fmri, states) in the catalog incorporated by the named
                package and its dependencies and any packages that are not
                incorporated by the named packages or their dependencies.  FMRIs
                are returned ordered by stem and descending version.  State
                is a set of PKG_STATES applicable to the 'fmri'."""

                try:
                        cat = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return

                pubs = frozenset([pfmri.publisher for pfmri in pfmris])

                # Seed the set of allowed packages with the set of FMRIs that
                # were started with since they don't likely incorporate
                # themselves.
                allowed = dict(
                    (pfmri.pkg_name, set([(pfmri, frozenset())]))
                    for pfmri in pfmris
                )

                # pfmri is not leaked from the above list comprehension in
                # Python 3, so we need to use pfmris[-1] explicitly.
                self.__get_allowed_packages(cat, pfmris[-1], allowed,
                    build_release=build_release, excludes=excludes,
                    pubs=pubs)

                # Add packages not incorporated by the recursively discovered
                # incorporations above.
                cat_info = frozenset([cat.DEPENDENCY])
                remaining = set(cat.names(pubs=pubs)) - \
                    set(six.iterkeys(allowed))
                for pkg_name in remaining:
                        for ver, flist in cat.fmris_by_version(pkg_name,
                            pubs=pubs):
                                aset = allowed.setdefault(pkg_name, set())
                                for f in flist:
                                        states = set()
                                        for fa in cat.get_entry_actions(f,
                                            cat_info, excludes=excludes):
                                                if fa.name != "set":
                                                        continue

                                                attrs = fa.attrs
                                                aname = attrs["name"]
                                                avalue = attrs["value"]
                                                if aname == "pkg.renamed":
                                                        if avalue == "true":
                                                                states.add(
                                                                    pkgdefs.PKG_STATE_RENAMED)
                                                        break
                                                if aname == "pkg.obsolete":
                                                        if avalue == "true":
                                                                states.add(
                                                                    pkgdefs.PKG_STATE_OBSOLETE)
                                                        break

                                        aset.add((f, frozenset(states)))


                sort_ver = itemgetter(0)
                return (
                    entry
                    for name in sorted(allowed)
                    for entry in sorted(allowed[name], key=sort_ver,
                        reverse=True)
                )

        def __get_allowed_packages(self, cat, pfmri, allowed,
            build_release=None, excludes=misc.EmptyI, pubs=misc.EmptyI):
                cat_info = frozenset([cat.DEPENDENCY])

                for a in cat.get_entry_actions(pfmri, cat_info,
                    excludes=excludes):
                        if a.name != "depend":
                                continue
                        if a.attrs["type"] != "incorporate":
                                continue

                        ifmri = pkg.fmri.PkgFmri(a.attrs["fmri"],
                            build_release=build_release)
                        iver = ifmri.version
                        # Versionless incorporations don't make sense so don't
                        # recurse any further.
                        if not iver:
                                continue
                        recurse = False
                        for ver, flist in cat.fmris_by_version(ifmri.pkg_name,
                            pubs=pubs):
                                if not ver.is_successor(iver,
                                    pkg.version.CONSTRAINT_AUTO):
                                        continue

                                aset = allowed.setdefault(ifmri.pkg_name, set())
                                for f in flist:
                                        states = set()
                                        for fa in cat.get_entry_actions(f,
                                            cat_info, excludes=excludes):
                                                if fa.name != "set":
                                                        continue

                                                attrs = fa.attrs
                                                aname = attrs["name"]
                                                avalue = attrs["value"]
                                                if aname == "pkg.renamed":
                                                        if avalue == "true":
                                                                states.add(
                                                                    pkgdefs.PKG_STATE_RENAMED)
                                                        break
                                                if aname == "pkg.obsolete":
                                                        if avalue == "true":
                                                                states.add(
                                                                    pkgdefs.PKG_STATE_OBSOLETE)
                                                        break

                                        aset.add((f, frozenset(states)))
                                        self.__get_allowed_packages(cat, f,
                                            allowed=allowed, excludes=excludes,
                                            pubs=pubs)

        def gen_packages(self, collect_attrs=False, matched=None,
            patterns=misc.EmptyI, pubs=misc.EmptyI, unmatched=None,
            return_fmris=False):
                """A generator function that produces tuples of the form:

                    (
                        (
                            pub,    - (string) the publisher of the package
                            stem,   - (string) the name of the package
                            version - (string) the version of the package
                        ),
                        states,     - (list) states
                        attributes  - (dict) package attributes
                    )

                Results are always sorted by stem, publisher, and then in
                descending version order.

                'collect_attrs' is an optional boolean that indicates whether
                all package attributes should be collected and returned in the
                fifth element of the return tuple.  If False, that element will
                be an empty dictionary.

                'matched' is an optional set to add matched patterns to.

                'patterns' is an optional list of FMRI wildcard strings to
                filter results by.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                'unmatched' is an optional set to add unmatched patterns to.

                'return_fmris' is an optional boolean value that indicates that
                an FMRI object should be returned in place of the (pub, stem,
                ver) tuple that is normally returned."""

                try:
                        cat = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return iter(())

                return cat.gen_packages(collect_attrs=collect_attrs,
                    matched=matched, patterns=patterns, pubs=pubs,
                    unmatched=unmatched, return_fmris=return_fmris)

        def info(self, fmri_strings, info_needed, excludes=misc.EmptyI):
                """Gathers information about fmris.  fmri_strings is a list
                of fmri_names for which information is desired. It
                returns a dictionary of lists.  The keys for the dictionary are
                the constants specified in the class definition.  The values are
                lists of PackageInfo objects or strings."""

                bad_opts = info_needed - PackageInfo.ALL_OPTIONS
                if bad_opts:
                        raise api_errors.UnrecognizedOptionsToInfo(bad_opts)

                fmris = []
                notfound = []
                illegals = []

                for pattern in fmri_strings:
                        try:
                                pfmri = None
                                pfmri = self.get_matching_pattern_fmris(pattern)
                        except pkg.fmri.IllegalFmri as e:
                                illegals.append(pattern)
                                continue
                        else:
                                fmris.extend(pfmri[0])
                                if not pfmri:
                                        notfound.append(pattern)

                repo_cat = self._depot.repo.get_catalog(self._pub)

                # Set of options that can use catalog data.
                cat_opts = frozenset([PackageInfo.SUMMARY,
                    PackageInfo.CATEGORIES, PackageInfo.DESCRIPTION,
                    PackageInfo.DEPENDENCIES])

                # Set of options that require manifest retrieval.
                act_opts = PackageInfo.ACTION_OPTIONS - \
                    frozenset([PackageInfo.DEPENDENCIES])

                pis = []
                for f in fmris:
                        pub = name = version = release = None
                        build_release = branch = packaging_date = None
                        if PackageInfo.IDENTITY in info_needed:
                                pub, name, version = f.tuple()
                                release = version.release
                                build_release = version.build_release
                                branch = version.branch
                                packaging_date = \
                                    version.get_timestamp().strftime("%c")

                        states = None

                        links = hardlinks = files = dirs = dependencies = None
                        summary = csize = size = licenses = cat_info = \
                            description = None

                        if cat_opts & info_needed:
                                summary, description, cat_info, dependencies = \
                                    _get_pkg_cat_data(repo_cat, info_needed,
                                        excludes=excludes, pfmri=f)
                                if cat_info is not None:
                                        cat_info = [
                                            PackageCategory(scheme, cat)
                                            for scheme, cat in cat_info
                                        ]

                        if (frozenset([PackageInfo.SIZE,
                            PackageInfo.LICENSES]) | act_opts) & info_needed:
                                mfst = manifest.Manifest(f)
                                try:
                                        mpath = self._depot.repo.manifest(f)
                                except srepo.RepositoryError as e:
                                        notfound.append(f)
                                        continue

                                if not os.path.exists(mpath):
                                        notfound.append(f)
                                        continue

                                mfst.set_content(pathname=mpath)

                                if PackageInfo.LICENSES in info_needed:
                                        licenses = self.__licenses(mfst)

                                if PackageInfo.SIZE in info_needed:
                                        size, csize = mfst.get_size(
                                            excludes=excludes)

                                if act_opts & info_needed:
                                        if PackageInfo.LINKS in info_needed:
                                                links = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "link", excludes))
                                        if PackageInfo.HARDLINKS in info_needed:
                                                hardlinks = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "hardlink", excludes))
                                        if PackageInfo.FILES in info_needed:
                                                files = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "file", excludes))
                                        if PackageInfo.DIRS in info_needed:
                                                dirs = list(
                                                    mfst.gen_key_attribute_value_by_type(
                                                    "dir", excludes))

                        pis.append(PackageInfo(pkg_stem=name, summary=summary,
                            category_info_list=cat_info, states=states,
                            publisher=pub, version=release,
                            build_release=build_release, branch=branch,
                            packaging_date=packaging_date, size=size,
                            csize=csize, pfmri=f, licenses=licenses,
                            links=links, hardlinks=hardlinks, files=files,
                            dirs=dirs, dependencies=dependencies,
                            description=description))
                return {
                    self.INFO_FOUND: pis,
                    self.INFO_MISSING: notfound,
                    self.INFO_ILLEGALS: illegals
                }

        @property
        def last_modified(self):
                """Returns a datetime object representing the date and time at
                which the catalog was last modified.  Returns None if not
                available.
                """
                try:
                        c = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return None
                return c.last_modified

        @property
        def package_count(self):
                """The total number of packages in the catalog.  Returns None
                if the catalog is not available.
                """
                try:
                        c = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return None
                return c.package_count

        @property
        def package_version_count(self):
                """The total number of package versions in the catalog.  Returns
                None if the catalog is not available.
                """
                try:
                        c = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return None
                return c.package_version_count

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
                                        if mver != pfmri.version:
                                                continue

                                if return_latest and \
                                    result[1] == qp.Query.RETURN_PACKAGES:
                                        # Latest version filtering can only be
                                        # done for packages as only they are
                                        # guaranteed to be in version order.
                                        stem = result[2].pkg_name
                                        if last_stem == stem:
                                                continue
                                        else:
                                                last_stem = stem

                                found += 1
                                if found > start_point:
                                        yield result

                def filtered_search(results, mver):
                        try:
                                result = next(results)
                        except StopIteration:
                                return

                        return_type = result[1]
                        results = itertools.chain([result], results)

                        if return_latest and \
                            return_type == qp.Query.RETURN_PACKAGES:
                                def cmp_fmris(resa, resb):
                                        a = resa[2]
                                        b = resb[2]

                                        if a.pkg_name == b.pkg_name:
                                                # Version in descending order.
                                                return misc.cmp(a.version,
                                                    b.version) * -1
                                        return misc.cmp(a, b)
                                return filter_results(sorted(results,
                                    key=cmp_to_key(cmp_fmris)), mver)

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
                        res_list = self._depot.repo.search([str(query)],
                            pub=self._pub)
                        if not res_list:
                                return

                        return filtered_search(res_list[0], mver)

                query = qp.Query(" ".join(tokens), case_sensitive,
                    return_type, num_to_return, start_point)
                res_list = self._depot.repo.search([str(query)],
                    pub=self._pub)
                if not res_list:
                        return
                return res_list[0]

        @property
        def search_available(self):
                """Returns a Boolean value indicating whether search
                functionality is available for the catalog.
                """
                try:
                        rstore = self._depot.repo.get_pub_rstore(self._pub)
                except srepo.RepositoryUnknownPublisher:
                        return False
                return rstore.search_available

        def __licenses(self, mfst):
                """Private function. Returns the license info from the
                manifest mfst."""
                license_lst = []
                for lic in mfst.gen_actions_by_type("license"):
                        s = BytesIO()
                        lpath = self._depot.repo.file(lic.hash, pub=self._pub)
                        lfile = open(lpath, "rb")
                        misc.gunzip_from_stream(lfile, s, ignore_hash=True)
                        text = s.getvalue()
                        s.close()
                        license_lst.append(LicenseInfo(mfst.fmri, lic,
                            text=text))
                        lfile.close()
                return license_lst

        @property
        def version(self):
                """Returns the version of the catalog or None if no catalog
                is available.
                """

                try:
                        c = self._depot.repo.get_catalog(self._pub)
                except srepo.RepositoryMirrorError:
                        return None
                if hasattr(c, "version"):
                        return c.version
                # Assume version 0.
                return 0


class ConfigInterface(_Interface):
        """This class presents a read-only interface to configuration
        information and statistics about the depot that clients may use.
        """

        @property
        def catalog_requests(self):
                """The number of /catalog operation requests that have occurred
                during the current server session.
                """
                return self._depot.repo.catalog_requests

        @property
        def content_root(self):
                """The file system path where the server's content and web
                directories are located.
                """
                return self._depot.content_root

        @property
        def file_requests(self):
                """The number of /file operation requests that have occurred
                during the current server session.
                """
                return self._depot.repo.file_requests

        @property
        def in_flight_transactions(self):
                """The number of package transactions awaiting completion.
                """
                return self._depot.repo.in_flight_transactions

        @property
        def manifest_requests(self):
                """The number of /manifest operation requests that have occurred
                during the current server session.
                """
                return self._depot.repo.manifest_requests

        @property
        def mirror(self):
                """A Boolean value indicating whether the server is currently
                operating in mirror mode.
                """
                return self._depot.repo.mirror

        @property
        def readonly(self):
                """A Boolean value indicating whether the server is currently
                operating in readonly mode.
                """
                return self._depot.repo.read_only

        @property
        def web_root(self):
                """The file system path where the server's web content is
                located.
                """
                return self._depot.web_root

        def get_depot_properties(self):
                """Returns a dictionary of depot configuration properties
                organized by section, with each section's keys as a list.

                See pkg.depotd(1M) for the list of properties.
                """
                rval = {}
                for sname, props in six.iteritems(self._depot.cfg.get_index()):
                        rval[sname] = [p for p in props]
                return rval

        def get_depot_property_value(self, section, prop):
                """Returns the current value of a depot configuration
                property for the specified section.
                """
                return self._depot.cfg.get_property(section, prop)

        def get_repo_properties(self):
                """Returns a dictionary of repository configuration
                properties organized by section, with each section's keys
                as a list.

                Available properties are as follows:

                Section     Property            Description
                ==========  ==========          ===============
                publisher   prefix              The name of the default
                                                publisher to use for packaging
                                                operations if one is not
                                                provided.

                repository  version             An integer value representing
                                                the version of the repository's
                                                format.
                """
                rval = {}
                for sname, props in six.iteritems(self._depot.repo.cfg.get_index()):
                        rval[sname] = [p for p in props]
                return rval

        def get_repo_property_value(self, section, prop):
                """Returns the current value of a repository configuration
                property for the specified section.
                """
                return self._depot.repo.cfg.get_property(section, prop)


class RequestInterface(_Interface):
        """This class presents an interface to server request objects that
        clients may use.
        """

        def get_accepted_languages(self):
                """Returns a list of the languages accepted by the client
                sorted by priority.  This information is derived from the
                Accept-Language header provided by the client.
                """
                alist = []
                for entry in self._request.headers.elements("Accept-Language"):
                        alist.append(str(entry).split(";")[0])

                return alist

        def get_rel_path(self, uri):
                """Returns uri relative to the current request path.
                """
                return pkg.misc.get_rel_path(self._request, uri, pub=self._pub)

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
                return self._request.params

        @property
        def path_info(self):
                """A string containing the "path_info" portion of the requested
                URL.
                """
                return self._request.path_info

        @property
        def publisher(self):
                """The Publisher object for the package data related to this
                request or None if not available.
                """
                try:
                        return self._depot.repo.get_publisher(self._pub)
                except srepo.RepositoryUnknownPublisher:
                        return None

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
