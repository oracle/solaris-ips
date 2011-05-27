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

import cStringIO
import errno
import httplib
import itertools
import os
import simplejson as json
import sys
import urlparse
import urllib

import pkg
import pkg.p5i as p5i
import pkg.client.api_errors as apx
import pkg.client.transport.exception as tx
import pkg.config as cfg
import pkg.p5p
import pkg.server.repository as svr_repo
import pkg.server.query_parser as sqp

from email.utils import formatdate


class TransportRepo(object):
        """The TransportRepo class handles transport requests.
        It represents a repo, and provides the same interfaces as
        the operations that are performed against a repo.  Subclasses
        should implement protocol specific repo modifications."""

        def do_search(self, data, header=None, ccancel=None, pub=None):
                """Perform a search request."""

                raise NotImplementedError

        def get_catalog(self, ts=None, header=None, ccancel=None, pub=None):
                """Get the catalog from the repo.  If ts is defined,
                request only changes newer than timestamp ts."""

                raise NotImplementedError

        def get_catalog1(self, filelist, destloc, header=None, ts=None,
            progtrack=None, pub=None, revalidate=False, redownload=False):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch.

                Revalidate and redownload are used to control upstream
                caching behavior, for protocols that support caching. (HTTP)"""

                raise NotImplementedError

        def get_datastream(self, fhash, version, header=None, ccancel=None, pub=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                raise NotImplementedError

        def get_files(self, filelist, dest, progtrack, version, header=None, pub=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given. Progtrack is a ProgressTracker"""

                raise NotImplementedError

        def get_manifest(self, fmri, header=None, ccancel=None, pub=None):
                """Get a manifest from repo.  The name of the
                package is given in fmri.  If dest is set, download
                the manifest to dest."""

                raise NotImplementedError

        def get_manifests(self, mfstlist, dest, progtrack=None, pub=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                raise NotImplementedError

        def get_publisherinfo(self, header=None, ccancel=None):
                """Get publisher configuration information from the
                repository."""

                raise NotImplementedError

        def get_status(self, header=None, ccancel=None):
                """Get status from the repository."""

                raise NotImplementedError

        def get_url(self):
                """Return's the Repo's URL."""

                raise NotImplementedError

        def get_versions(self, header=None, ccancel=None):
                """Query the repo for versions information.
                Returns a fileobject."""

                raise NotImplementedError

        def publish_add(self, action, header=None, progtrack=None,
            trans_id=None):
                """The publish operation that adds content to a repository.
                The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                raise NotImplementedError

        def publish_add_file(self, action, header=None, trans_id=None):
                raise NotImplementedError

        def publish_abandon(self, header=None, trans_id=None):
                """The 'abandon' publication operation, that tells a
                Repository to abort the current transaction.  The caller
                must specify the transaction id in trans_id. Returns
                a (publish-state, fmri) tuple."""

                raise NotImplementedError

        def publish_close(self, header=None, trans_id=None,
            add_to_catalog=False):
                """The close operation tells the Repository to commit
                the transaction identified by trans_id.  The caller may
                specify add_to_catalog, if needed.  This method returns a
                (publish-state, fmri) tuple."""

                raise NotImplementedError

        def publish_open(self, header=None, client_release=None, pkg_name=None):
                """Begin a publication operation by calling 'open'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID."""

                raise NotImplementedError

        def publish_rebuild(self, header=None, pub=None):
                """Attempt to rebuild the package data and search data in the
                repository."""

                raise NotImplementedError

        def publish_rebuild_indexes(self, header=None, pub=None):
                """Attempt to rebuild the search data in the repository."""

                raise NotImplementedError

        def publish_rebuild_packages(self, header=None, pub=None):
                """Attempt to rebuild the package data in the repository."""

                raise NotImplementedError

        def publish_refresh(self, header=None, pub=None):
                """Attempt to refresh the package data and search data in the
                repository."""

                raise NotImplementedError

        def publish_refresh_indexes(self, header=None, pub=None):
                """Attempt to refresh the search data in the repository."""

                raise NotImplementedError

        def publish_refresh_packages(self, header=None, pub=None):
                """Attempt to refresh the package data in the repository."""

                raise NotImplementedError

        def touch_manifest(self, fmri, header=None, ccancel=None, pub=None):
                """Send data about operation intent without actually
                downloading a manifest."""

                raise NotImplementedError

        @staticmethod
        def _annotate_exceptions(errors, mapping=None):
                """Walk a list of transport errors, examine the
                url, and add a field that names the request.  This request
                information is derived from the URL."""

                for e in errors:
                        if not e.url:
                                # Error may have been raised before request path
                                # was determined; nothing to annotate.
                                continue

                        if not mapping:
                                # Request is basename of path portion of URI.
                                e.request = os.path.basename(urlparse.urlsplit(
                                    e.url)[2])
                                continue

                        # If caller specified a mapping object, use that
                        # instead of trying to deduce the request's name.
                        if e.url not in mapping:
                                raise tx.TransportOperationError(
                                    "No mapping found for URL %s" % e.url)

                        e.request = mapping[e.url]

                return errors

        @staticmethod
        def _parse_html_error(content):
                """Parse a html document that contains error information.
                Return the html as a plain text string."""

                msg = None
                if not content:
                        return msg

                from xml.dom.minidom import Document, parse
                dom = parse(cStringIO.StringIO(content))
                msg = ""

                paragraphs = []
                if not isinstance(dom, Document):
                        # Assume the output was the message.
                        msg = content
                else:
                        paragraphs = dom.getElementsByTagName("p")

                # XXX this is specific to the depot server's current
                # error output style.
                for p in paragraphs:
                        for c in p.childNodes:
                                if c.nodeType == c.TEXT_NODE:
                                        value = c.nodeValue
                                        if value is not None:
                                                msg += ("\n%s" % value)

                return msg

        @staticmethod
        def _url_to_request(urllist, mapping=None):
                """Take a list of urls and remove the protocol information,
                leaving just the information about the request."""

                reqlist = []

                for u in urllist:

                        if not mapping:
                                utup = urlparse.urlsplit(u)
                                req = utup[2]
                                req = os.path.basename(req)
                                reqlist.append(req)
                                continue

                        if u not in mapping:
                                raise tx.TransportOperationError(
                                    "No mapping found for URL %s" % u)

                        req = mapping[u]
                        reqlist.append(req)

                return reqlist


class HTTPRepo(TransportRepo):

        def __init__(self, repostats, repouri, engine):
                """Create a http repo.  Repostats is a RepoStats object.
                Repouri is a RepositoryURI object.  Engine is a transport
                engine object.

                The convenience function new_repo() can be used to create
                the correct repo."""
                self._url = repostats.url
                self._repouri = repouri
                self._engine = engine
                self._verdata = None

        def __str__(self):
                return "HTTPRepo url: %s repouri: %s" % (self._url,
                    self._repouri)

        def _add_file_url(self, url, filepath=None, progclass=None,
            progtrack=None, header=None, compress=False):
                self._engine.add_url(url, filepath=filepath,
                    progclass=progclass, progtrack=progtrack, repourl=self._url,
                    header=header, compressible=compress,
                    proxy=self._repouri.proxy)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None,
            failonerror=True):
                return self._engine.get_url(url, header, repourl=self._url,
                    compressible=compress, ccancel=ccancel,
                    failonerror=failonerror, proxy=self._repouri.proxy)

        def _fetch_url_header(self, url, header=None, ccancel=None,
            failonerror=True):
                return self._engine.get_url_header(url, header,
                    repourl=self._url, ccancel=ccancel,
                    failonerror=failonerror, proxy=self._repouri.proxy)

        def _post_url(self, url, data=None, header=None, ccancel=None,
            data_fobj=None, data_fp=None, failonerror=True, progclass=None,
            progtrack=None):
                return self._engine.send_data(url, data=data, header=header,
                    repourl=self._url, ccancel=ccancel,
                    data_fobj=data_fobj, data_fp=data_fp,
                    failonerror=failonerror, progclass=progclass,
                    progtrack=progtrack, proxy=self._repouri.proxy)

        def __check_response_body(self, fobj):
                """Parse the response body found accessible using the provided
                filestream object and raise an exception if appropriate."""

                try:
                        fobj.free_buffer = False
                        fobj.read()
                except tx.TransportProtoError, e:
                        if e.code == httplib.BAD_REQUEST:
                                exc_type, exc_value, exc_tb = sys.exc_info()
                                try:
                                        e.details = self._parse_html_error(
                                            fobj.read())
                                except:
                                        # If parse fails, raise original
                                        # exception.
                                        raise exc_value, None, exc_tb
                        raise
                finally:
                        fobj.close()

        def add_version_data(self, verdict):
                """Cache the information about what versions a repository
                supports."""

                self._verdata = verdict

        def __get_request_url(self, methodstr, query=None, pub=None):
                """Generate the request URL for the given method and
                publisher.
                """

                base = self._repouri.uri

                # Only append the publisher prefix if the publisher of the
                # request is known, not already part of the URI, if this isn't
                # an open operation, and if the repository supports version 1
                # of the publisher opation.  The prefix shouldn't be appended
                # for open because the publisher may not yet be known to the
                # repository, and not in other cases because the repository
                # doesn't support it.
                pub_prefix = getattr(pub, "prefix", None)
                if pub_prefix and not methodstr.startswith("open/") and \
                    not base.endswith("/%s/" % pub_prefix) and \
                    self.supports_version("publisher", [1]) > -1:
                        # Append the publisher prefix to the repository URL.
                        base = urlparse.urljoin(base, pub_prefix) + "/"

                uri = urlparse.urljoin(base, methodstr)
                if not query:
                        return uri

                # If a set of query data was provided, then decompose the URI
                # into its component parts and replace the query portion with
                # the encoded version of the new query data.
                components = list(urlparse.urlparse(uri))
                components[4] = urllib.urlencode(query)
                return urlparse.urlunparse(components)

        def do_search(self, data, header=None, ccancel=None, pub=None):
                """Perform a remote search against origin repos."""

                requesturl = self.__get_request_url("search/1/", pub=pub)
                if len(data) > 1:
                        # Post and retrieve.
                        request_data = urllib.urlencode(
                            [(i, str(q)) for i, q in enumerate(data)])
                        return self._post_url(requesturl, request_data,
                            header, ccancel=ccancel)

                # Retrieval only.
                requesturl = urlparse.urljoin(requesturl, urllib.quote(
                    str(data[0]), safe=''))
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_catalog(self, ts=None, header=None, ccancel=None, pub=None):
                """Get the catalog from the repo.  If ts is defined,
                request only changes newer than timestamp ts."""

                requesturl = self.__get_request_url("catalog/0/", pub=pub)
                if ts:
                        if not header:
                                header = {"If-Modified-Since": ts}
                        else:
                                header["If-Modified-Since"] = ts

                return self._fetch_url(requesturl, header, compress=True,
                    ccancel=ccancel)

        def get_catalog1(self, filelist, destloc, header=None, ts=None,
            progtrack=None, pub=None, revalidate=False, redownload=False):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch.

                If 'redownload' or 'revalidate' is set, cache control
                headers are appended to the request.  Re-download
                uses http's no-cache header, while revalidate uses
                max-age=0."""

                baseurl = self.__get_request_url("catalog/1/", pub=pub)
                urllist = []
                progclass = None
                headers = {}

                if redownload and revalidate:
                        raise ValueError("Either revalidate or redownload"
                            " may be used, but not both.")
                if ts:
                        # Convert date to RFC 1123 compliant string
                        tsstr = formatdate(timeval=ts, localtime=False,
                            usegmt=True)
                        headers["If-Modified-Since"] = tsstr
                if revalidate:
                        headers["Cache-Control"] = "max-age=0"
                if redownload:
                        headers["Cache-Control"] = "no-cache"
                if header:
                        headers.update(header)
                if progtrack:
                        progclass = ProgressCallback

                for f in filelist:
                        url = urlparse.urljoin(baseurl, f)
                        urllist.append(url)
                        fn = os.path.join(destloc, f)
                        self._add_file_url(url, filepath=fn, header=headers,
                            compress=True, progtrack=progtrack,
                            progclass=progclass)

                try:
                        while self._engine.pending:
                                self._engine.run()
                except tx.ExcessiveTransientFailure, e:
                        # Attach a list of failed and successful
                        # requests to this exception.
                        errors, success = self._engine.check_status(urllist,
                            True)

                        errors = self._annotate_exceptions(errors)
                        success = self._url_to_request(success)
                        e.failures = errors
                        e.success = success

                        # Reset the engine before propagating exception.
                        self._engine.reset()
                        raise

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanent failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.

                return self._annotate_exceptions(errors)

        def get_datastream(self, fhash, version, header=None, ccancel=None,
            pub=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                # The only versions this operation is compatible with.
                assert version == 0 or version == 1

                baseurl = self.__get_request_url("file/%s/" % version, pub=pub)
                requesturl = urlparse.urljoin(baseurl, fhash)
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_publisherinfo(self, header=None, ccancel=None):
                """Get publisher information from the repository."""

                requesturl = self.__get_request_url("publisher/0/")
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_syspub_info(self, header=None, ccancel=None):
                """Get configuration from the system depot."""

                requesturl = self.__get_request_url("syspub/0/")
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_status(self, header=None, ccancel=None):
                """Get status/0 information from the repository."""

                requesturl = self.__get_request_url("status/0")
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_manifest(self, fmri, header=None, ccancel=None, pub=None):
                """Get a package manifest from repo.  The FMRI of the
                package is given in fmri."""

                mfst = fmri.get_url_path()
                baseurl = self.__get_request_url("manifest/0/", pub=pub)
                requesturl = urlparse.urljoin(baseurl, mfst)

                return self._fetch_url(requesturl, header, compress=True,
                    ccancel=ccancel)

        def get_manifests(self, mfstlist, dest, progtrack=None, pub=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                baseurl = self.__get_request_url("manifest/0/", pub=pub)
                urlmapping = {}
                progclass = None

                if progtrack:
                        progclass = ProgressCallback

                for fmri, h in mfstlist:
                        f = fmri.get_url_path()
                        url = urlparse.urljoin(baseurl, f)
                        urlmapping[url] = fmri
                        fn = os.path.join(dest, f)
                        self._add_file_url(url, filepath=fn, header=h,
                            progtrack=progtrack, progclass=progclass)

                # Compute urllist from keys in mapping
                urllist = urlmapping.keys()

                try:
                        while self._engine.pending:
                                self._engine.run()
                except tx.ExcessiveTransientFailure, e:
                        # Attach a list of failed and successful
                        # requests to this exception.
                        errors, success = self._engine.check_status(urllist,
                            True)

                        errors = self._annotate_exceptions(errors, urlmapping)
                        success = self._url_to_request(success, urlmapping)
                        e.failures = errors
                        e.success = success

                        # Reset the engine before propagating exception.
                        self._engine.reset()
                        raise

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanant failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.

                return self._annotate_exceptions(errors, urlmapping)

        def get_files(self, filelist, dest, progtrack, version, header=None, pub=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given.  If progtrack is not None,
                it contains a ProgressTracker object for the
                downloads."""

                baseurl = self.__get_request_url("file/%s/" % version, pub=pub)
                urllist = []
                progclass = None

                if progtrack:
                        progclass = FileProgress

                for f in filelist:
                        url = urlparse.urljoin(baseurl, f)
                        urllist.append(url)
                        fn = os.path.join(dest, f)
                        self._add_file_url(url, filepath=fn,
                            progclass=progclass, progtrack=progtrack,
                            header=header)

                try:
                        while self._engine.pending:
                                self._engine.run()
                except tx.ExcessiveTransientFailure, e:
                        # Attach a list of failed and successful
                        # requests to this exception.
                        errors, success = self._engine.check_status(urllist,
                            True)

                        errors = self._annotate_exceptions(errors)
                        success = self._url_to_request(success)
                        e.failures = errors
                        e.success = success

                        # Reset the engine before propagating exception.
                        self._engine.reset()
                        raise

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanant failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.

                return self._annotate_exceptions(errors)

        def get_url(self):
                """Returns the repo's url."""

                return self._url

        def get_versions(self, header=None, ccancel=None):
                """Query the repo for versions information.
                Returns a fileobject."""

                requesturl = self.__get_request_url("versions/0/")
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def has_version_data(self):
                """Returns true if this repo knows its version information."""

                return self._verdata is not None

        def publish_add(self, action, header=None, progtrack=None,
            trans_id=None):
                """The publish operation that adds content to a repository.
                The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                attrs = action.attrs
                data_fobj = None
                data = None
                progclass = None

                if progtrack:
                        progclass = FileProgress

                baseurl = self.__get_request_url("add/0/")
                request_str = "%s/%s" % (trans_id, action.name)
                requesturl = urlparse.urljoin(baseurl, request_str)

                if action.data:
                        data_fobj = action.data()
                else:
                        data = ""

                headers = dict(
                    ("X-IPkg-SetAttr%s" % i, "%s=%s" % (k, attrs[k]))
                    for i, k in enumerate(attrs)
                )

                if header:
                        headers.update(header)

                fobj = self._post_url(requesturl, header=headers,
                    data_fobj=data_fobj, data=data, failonerror=False,
                    progclass=progclass, progtrack=progtrack)
                self.__check_response_body(fobj)

        def publish_add_file(self, pth, header=None, trans_id=None):
                """The publish operation that adds content to a repository.
                The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                attrs = {}
                baseurl = self.__get_request_url("file/1/")
                requesturl = urlparse.urljoin(baseurl, trans_id)

                headers = dict(
                    ("X-IPkg-SetAttr%s" % i, "%s=%s" % (k, attrs[k]))
                    for i, k in enumerate(attrs)
                )

                if header:
                        headers.update(header)

                fobj = self._post_url(requesturl, header=headers, data_fp=pth)
                self.__check_response_body(fobj)

        def publish_abandon(self, header=None, trans_id=None):
                """The 'abandon' publication operation, that tells a
                Repository to abort the current transaction.  The caller
                must specify the transaction id in trans_id. Returns
                a (publish-state, fmri) tuple."""

                baseurl = self.__get_request_url("abandon/0/")
                requesturl = urlparse.urljoin(baseurl, trans_id)
                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)

                try:
                        fobj.free_buffer = False
                        fobj.read()
                        state = fobj.getheader("State", None)
                        pkgfmri = fobj.getheader("Package-FMRI", None)
                except tx.TransportProtoError, e:
                        if e.code == httplib.BAD_REQUEST:
                                exc_type, exc_value, exc_tb = sys.exc_info()
                                try:
                                        e.details = self._parse_html_error(
                                            fobj.read())
                                except:
                                        # If parse fails, raise original
                                        # exception.
                                        raise exc_value, None, exc_tb
                        raise
                finally:
                        fobj.close()

                return state, pkgfmri

        def publish_close(self, header=None, trans_id=None,
            add_to_catalog=False):
                """The close operation tells the Repository to commit
                the transaction identified by trans_id.  The caller may
                specify add_to_catalog, if needed.  This method returns a
                (publish-state, fmri) tuple."""

                headers = {}
                if not add_to_catalog:
                        headers["X-IPkg-Add-To-Catalog"] = 0
                if header:
                        headers.update(header)

                baseurl = self.__get_request_url("close/0/")
                requesturl = urlparse.urljoin(baseurl, trans_id)

                fobj = self._fetch_url(requesturl, header=headers,
                    failonerror=False)

                try:
                        fobj.free_buffer = False
                        fobj.read()
                        state = fobj.getheader("State", None)
                        pkgfmri = fobj.getheader("Package-FMRI", None)
                except tx.TransportProtoError, e:
                        if e.code == httplib.BAD_REQUEST:
                                exc_type, exc_value, exc_tb = sys.exc_info()
                                try:
                                        e.details = self._parse_html_error(
                                            fobj.read())
                                except:
                                        # If parse fails, raise original
                                        # exception.
                                        raise exc_value, None, exc_tb

                        raise
                finally:
                        fobj.close()

                return state, pkgfmri

        def publish_open(self, header=None, client_release=None, pkg_name=None):
                """Begin a publication operation by calling 'open'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID."""

                baseurl = self.__get_request_url("open/0/")
                return self.__start_trans(baseurl, header, client_release,
                    pkg_name)

        def __start_trans(self, baseurl, header, client_release, pkg_name):
                """Start a publication transaction."""

                request_str = urllib.quote(pkg_name, "")
                requesturl = urlparse.urljoin(baseurl, request_str)

                headers = {"Client-Release": client_release}
                if header:
                        headers.update(header)

                fobj = self._fetch_url(requesturl, header=headers,
                    failonerror=False)

                try:
                        fobj.free_buffer = False
                        fobj.read()
                        trans_id = fobj.getheader("Transaction-ID", None)
                except tx.TransportProtoError, e:
                        if e.code == httplib.BAD_REQUEST:
                                exc_type, exc_value, exc_tb = sys.exc_info()
                                try:
                                        e.details = self._parse_html_error(
                                            fobj.read())
                                except:
                                        # If parse fails, raise original
                                        # exception.
                                        raise exc_value, None, exc_tb
                        raise
                finally:
                        fobj.close()

                return trans_id

        def publish_append(self, header=None, client_release=None,
            pkg_name=None):
                """Begin a publication operation by calling 'append'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID."""

                baseurl = self.__get_request_url("append/0/")
                return self.__start_trans(baseurl, header, client_release,
                    pkg_name)

        def publish_rebuild(self, header=None, pub=None):
                """Attempt to rebuild the package data and search data in the
                repository."""

                requesturl = self.__get_request_url("admin/0", query={
                    "cmd": "rebuild" }, pub=pub)
                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)
                self.__check_response_body(fobj)

        def publish_rebuild_indexes(self, header=None, pub=None):
                """Attempt to rebuild the search data in the repository."""

                requesturl = self.__get_request_url("admin/0", query={
                    "cmd": "rebuild-indexes" }, pub=pub)
                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)
                self.__check_response_body(fobj)

        def publish_rebuild_packages(self, header=None, pub=None):
                """Attempt to rebuild the package data in the repository."""

                requesturl = self.__get_request_url("admin/0", query={
                    "cmd": "rebuild-packages" }, pub=pub)
                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)
                self.__check_response_body(fobj)

        def publish_refresh(self, header=None, pub=None):
                """Attempt to refresh the package data and search data in the
                repository."""

                requesturl = self.__get_request_url("admin/0", query={
                    "cmd": "refresh" }, pub=pub)
                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)
                self.__check_response_body(fobj)

        def publish_refresh_indexes(self, header=None, pub=None):
                """Attempt to refresh the search data in the repository."""

                if self.supports_version("admin", [0]) > -1:
                        requesturl = self.__get_request_url("admin/0", query={
                            "cmd": "refresh-indexes" }, pub=pub)
                else:
                        requesturl = self.__get_request_url("index/0/refresh")

                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)
                self.__check_response_body(fobj)

        def publish_refresh_packages(self, header=None, pub=None):
                """Attempt to refresh the package data in the repository."""

                requesturl = self.__get_request_url("admin/0", query={
                    "cmd": "refresh-packages" }, pub=pub)
                fobj = self._fetch_url(requesturl, header=header,
                    failonerror=False)
                self.__check_response_body(fobj)

        def supports_version(self, op, verlist):
                """Returns version-id of highest supported version.
                If the version is not supported, or no data is available,
                -1 is returned instead."""

                if not self.has_version_data() or op not in self._verdata:
                        return -1

                # This code assumes that both the verlist and verdata
                # are sorted in reverse order.  This behavior is currently
                # implemented in the transport code.

                for v in verlist:
                        if v in self._verdata[op]:
                                return v
                return -1

        def touch_manifest(self, mfst, header=None, ccancel=None, pub=None):
                """Invoke HTTP HEAD to send manifest intent data."""

                baseurl = self.__get_request_url("manifest/0/", pub=pub)
                requesturl = urlparse.urljoin(baseurl, mfst)

                resp = self._fetch_url_header(requesturl, header,
                    ccancel=ccancel)

                # response is empty, or should be.
                resp.read()

                return True


class HTTPSRepo(HTTPRepo):

        def __init__(self, repostats, repouri, engine):
                """Create a http repo.  Repostats is a RepoStats object.
                Repouri is a RepositoryURI object.  Engine is a transport
                engine object.

                The convenience function new_repo() can be used to create
                the correct repo."""

                HTTPRepo.__init__(self, repostats, repouri, engine)

        # override the download functions to use ssl cert/key
        def _add_file_url(self, url, filepath=None, progclass=None,
            progtrack=None, header=None, compress=False):
                self._engine.add_url(url, filepath=filepath,
                    progclass=progclass, progtrack=progtrack,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    header=header, compressible=compress)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None,
            failonerror=True):
                return self._engine.get_url(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    compressible=compress, ccancel=ccancel,
                    failonerror=failonerror)

        def _fetch_url_header(self, url, header=None, ccancel=None,
            failonerror=True):
                return self._engine.get_url_header(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    ccancel=ccancel, failonerror=failonerror)

        def _post_url(self, url, data=None, header=None, ccancel=None,
            data_fobj=None, data_fp=None, failonerror=True):
                return self._engine.send_data(url, data=data, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    ccancel=ccancel, data_fobj=data_fobj,
                    data_fp=data_fp, failonerror=failonerror)


class _FilesystemRepo(TransportRepo):
        """Private implementation of transport repository logic for filesystem
        repositories.
        """

        def __init__(self, repostats, repouri, engine, frepo=None):
                """Create a file repo.  Repostats is a RepoStats object.
                Repouri is a RepositoryURI object.  Engine is a transport
                engine object.  If the caller wants to pass a Repository
                object instead of having FileRepo create one, it should
                pass the object in the frepo argument.

                The convenience function new_repo() can be used to create
                the correct repo."""

                self._frepo = frepo
                self._url = repostats.url
                self._repouri = repouri
                self._engine = engine
                self._verdata = None
                self.__stats = repostats

                # If caller supplied a Repository object, we're done. Return.
                if self._frepo:
                        return

                try:
                        scheme, netloc, path, params, query, fragment = \
                            urlparse.urlparse(self._repouri.uri, "file",
                            allow_fragments=0)
                        path = urllib.url2pathname(path)
                        self._frepo = svr_repo.Repository(read_only=True,
                            root=path)
                except cfg.ConfigError, e:
                        reason = _("The configuration file for the repository "
                            "is invalid or incomplete:\n%s") % e
                        ex = tx.TransportProtoError("file", errno.EINVAL,
                            reason=reason, repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                except svr_repo.RepositoryInvalidError, e:
                        ex = tx.TransportProtoError("file", errno.EINVAL,
                            reason=str(e), repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                except Exception, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex

        def __del__(self):
                # Dump search cache if repo goes out of scope.
                if self._frepo:
                        self._frepo.reset_search()
                        self._frepo = None

        def _add_file_url(self, url, filepath=None, progclass=None,
            progtrack=None, header=None, compress=False):
                self._engine.add_url(url, filepath=filepath,
                    progclass=progclass, progtrack=progtrack, repourl=self._url,
                    header=header, compressible=False)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None,
            failonerror=True):
                return self._engine.get_url(url, header, repourl=self._url,
                    compressible=False, ccancel=ccancel,
                    failonerror=failonerror)

        def _fetch_url_header(self, url, header=None, ccancel=None,
            failonerror=True):
                return self._engine.get_url_header(url, header,
                    repourl=self._url, ccancel=ccancel, failonerror=failonerror)

        def __record_proto_error(self, ex):
                """Private helper function that records a protocol error that
                was raised by the class instead of the transport engine.  It
                records both that a transaction was initiated and that an
                error occurred."""

                self.__stats.record_tx()
                self.__stats.record_error(decayable=ex.decayable)

        def add_version_data(self, verdict):
                """Cache the information about what versions a repository
                supports."""

                self._verdata = verdict

        def do_search(self, data, header=None, ccancel=None, pub=None):
                """Perform a search against repo."""

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        res_list = self._frepo.search(data, pub=pub_prefix)
                except svr_repo.RepositorySearchUnavailableError:
                        ex = tx.TransportProtoError("file", errno.EAGAIN,
                            reason=_("Search temporarily unavailable."),
                            repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                except sqp.QueryException, e:
                        ex = tx.TransportProtoError("file", errno.EINVAL,
                            reason=str(e), repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                except Exception, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex

                # In order to be able to have a return code distinguish between
                # no results and search unavailable, we need to use a different
                # http code.  Check and see if there's at least one item in
                # the results.  If not, set the result code to be NO_CONTENT
                # and return.  If there is at least one result, put the result
                # examined back at the front of the results and stream them
                # to the user.
                if len(res_list) == 1:
                        try:
                                tmp = res_list[0].next()
                                res_list = [itertools.chain([tmp], res_list[0])]
                        except StopIteration:
                                self.__stats.record_tx()
                                raise apx.NegativeSearchResult(self._url)

                def output():
                        # Yield the string used to let the client know it's
                        # talking to a valid search server.
                        yield str(sqp.Query.VALIDATION_STRING[1])
                        for i, res in enumerate(res_list):
                                for v, return_type, vals in res:
                                        if return_type == \
                                            sqp.Query.RETURN_ACTIONS:
                                                fmri_str, fv, line = vals
                                                yield "%s %s %s %s %s\n" % \
                                                    (i, return_type, fmri_str,
                                                    urllib.quote(fv),
                                                    line.rstrip())
                                        elif return_type == \
                                            sqp.Query.RETURN_PACKAGES:
                                                fmri_str = vals
                                                yield "%s %s %s\n" % \
                                                    (i, return_type, fmri_str)
                return output()

        def get_catalog1(self, filelist, destloc, header=None, ts=None,
            progtrack=None, pub=None, revalidate=False, redownload=False):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch.  This protocol
                doesn't implment revalidate and redownload.  The options
                are ignored."""

                urllist = []
                progclass = None
                pub_prefix = getattr(pub, "prefix", None)

                if progtrack:
                        progclass = ProgressCallback

                # create URL for requests
                for f in filelist:
                        try:
                                url = urlparse.urlunparse(("file", None,
                                    urllib.pathname2url(self._frepo.catalog_1(f,
                                    pub=pub_prefix)), None, None, None))
                        except svr_repo.RepositoryError, e:
                                ex = tx.TransportProtoError("file",
                                    errno.EPROTO, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                raise ex

                        urllist.append(url)
                        fn = os.path.join(destloc, f)
                        self._add_file_url(url, filepath=fn, header=header,
                            progtrack=progtrack, progclass=progclass)

                try:
                        while self._engine.pending:
                                self._engine.run()
                except tx.ExcessiveTransientFailure, e:
                        # Attach a list of failed and successful
                        # requests to this exception.
                        errors, success = self._engine.check_status(urllist,
                            True)

                        errors = self._annotate_exceptions(errors)
                        success = self._url_to_request(success)
                        e.failures = errors
                        e.success = success

                        # Reset the engine before propagating exception.
                        self._engine.reset()
                        raise

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanent failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.

                return self._annotate_exceptions(errors)

        def get_datastream(self, fhash, version, header=None, ccancel=None, pub=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        requesturl = urlparse.urlunparse(("file", None,
                            urllib.pathname2url(self._frepo.file(fhash,
                            pub=pub_prefix)), None, None, None))
                except svr_repo.RepositoryFileNotFoundError, e:
                        ex = tx.TransportProtoError("file", errno.ENOENT,
                            reason=str(e), repourl=self._url, request=fhash)
                        self.__record_proto_error(ex)
                        raise ex
                except svr_repo.RepositoryError, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url, request=fhash)
                        self.__record_proto_error(ex)
                        raise ex
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_publisherinfo(self, header=None, ccancel=None):
                """Get publisher information from the repository."""

                try:
                        pubs = self._frepo.get_publishers()
                        buf = cStringIO.StringIO()
                        p5i.write(buf, pubs)
                except Exception, e:
                        reason = "Unable to retrieve publisher configuration " \
                            "data:\n%s" % e
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=reason, repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                buf.seek(0)
                return buf

        def get_status(self, header=None, ccancel=None):
                """Get status/0 information from the repository."""

                buf = cStringIO.StringIO()
                try:
                        rstatus = self._frepo.get_status()
                        json.dump(rstatus, buf, ensure_ascii=False, indent=2,
                            sort_keys=True)
                        buf.write("\n")
                except Exception, e:
                        reason = "Unable to retrieve status data:\n%s" % e
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=reason, repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                buf.seek(0)
                return buf

        def get_manifest(self, fmri, header=None, ccancel=None, pub=None):
                """Get a manifest from repo.  The fmri of the package for the
                manifest is given in fmri."""

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        requesturl = urlparse.urlunparse(("file", None,
                            urllib.pathname2url(self._frepo.manifest(fmri,
                            pub=pub_prefix)), None, None, None))
                except svr_repo.RepositoryError, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url, request=str(fmri))
                        self.__record_proto_error(ex)
                        raise ex

                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_manifests(self, mfstlist, dest, progtrack=None, pub=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                urlmapping = {}
                progclass = None
                pub_prefix = getattr(pub, "prefix", None)

                if progtrack:
                        progclass = ProgressCallback

                # Errors that happen before the engine is executed must be
                # collected and added to the errors raised during engine
                # execution so that batch processing occurs as expected.
                pre_exec_errors = []
                for fmri, h in mfstlist:
                        try:
                                url = urlparse.urlunparse(("file", None,
                                    urllib.pathname2url(self._frepo.manifest(
                                    fmri, pub=pub_prefix)), None, None, None))
                        except svr_repo.RepositoryError, e:
                                ex = tx.TransportProtoError("file",
                                    errno.EPROTO, reason=str(e),
                                    repourl=self._url, request=str(fmri))
                                self.__record_proto_error(ex)
                                pre_exec_errors.append(ex)
                                continue
                        urlmapping[url] = fmri
                        fn = os.path.join(dest, fmri.get_url_path())
                        self._add_file_url(url, filepath=fn, header=h,
                            progtrack=progtrack, progclass=progclass)

                urllist = urlmapping.keys()

                try:
                        while self._engine.pending:
                                self._engine.run()
                except tx.ExcessiveTransientFailure, e:
                        # Attach a list of failed and successful
                        # requests to this exception.
                        errors, success = self._engine.check_status(urllist,
                            True)

                        errors = self._annotate_exceptions(errors, urlmapping)
                        errors.extend(pre_exec_errors)
                        success = self._url_to_request(success, urlmapping)
                        e.failures = errors
                        e.success = success

                        # Reset the engine before propagating exception.
                        self._engine.reset()
                        raise

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanant failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.
                errors = self._annotate_exceptions(errors, urlmapping)

                return errors + pre_exec_errors

        def get_files(self, filelist, dest, progtrack, version, header=None, pub=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given.  If progtrack is not None,
                it contains a ProgressTracker object for the
                downloads."""

                urllist = []
                progclass = None
                pub_prefix = getattr(pub, "prefix", None)

                if progtrack:
                        progclass = FileProgress

                # Errors that happen before the engine is executed must be
                # collected and added to the errors raised during engine
                # execution so that batch processing occurs as expected.
                pre_exec_errors = []
                for f in filelist:
                        try:
                                url = urlparse.urlunparse(("file", None,
                                    urllib.pathname2url(self._frepo.file(f,
                                    pub=pub_prefix)), None, None, None))
                        except svr_repo.RepositoryFileNotFoundError, e:
                                ex = tx.TransportProtoError("file",
                                    errno.ENOENT, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                pre_exec_errors.append(ex)
                                continue
                        except svr_repo.RepositoryError, e:
                                ex = tx.TransportProtoError("file",
                                    errno.EPROTO, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                pre_exec_errors.append(ex)
                                continue
                        urllist.append(url)
                        fn = os.path.join(dest, f)
                        self._add_file_url(url, filepath=fn,
                            progclass=progclass, progtrack=progtrack,
                            header=header)

                try:
                        while self._engine.pending:
                                self._engine.run()
                except tx.ExcessiveTransientFailure, e:
                        # Attach a list of failed and successful
                        # requests to this exception.
                        errors, success = self._engine.check_status(urllist,
                            True)

                        errors = self._annotate_exceptions(errors)
                        errors.extend(pre_exec_errors)
                        success = self._url_to_request(success)
                        e.failures = errors
                        e.success = success

                        # Reset the engine before propagating exception.
                        self._engine.reset()
                        raise

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanant failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.
                errors = self._annotate_exceptions(errors)

                return errors + pre_exec_errors

        def get_url(self):
                """Returns the repo's url."""

                return self._url

        def get_versions(self, header=None, ccancel=None):
                """Query the repo for versions information.
                Returns a file-like object."""

                buf = cStringIO.StringIO()
                vops = {
                    "abandon": ["0"],
                    "add": ["0"],
                    "admin": ["0"],
                    "append": ["0"],
                    "catalog": ["1"],
                    "close": ["0"],
                    "file": ["0", "1"],
                    "manifest": ["0"],
                    "open": ["0"],
                    "publisher": ["0", "1"],
                    "search": ["1"],
                    "status": ["0"],
                    "versions": ["0"],
                }

                buf.write("pkg-server %s\n" % pkg.VERSION)
                buf.write("\n".join(
                    "%s %s" % (op, " ".join(vers))
                    for op, vers in vops.iteritems()
                ) + "\n")
                buf.seek(0)
                self.__stats.record_tx()
                return buf

        def has_version_data(self):
                """Returns true if this repo knows its version information."""

                return self._verdata is not None

        def publish_add(self, action, header=None, progtrack=None,
            trans_id=None):
                """The publish operation that adds an action and its
                payload (if applicable) to an existing transaction in a
                repository.  The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                progclass = None
                if progtrack:
                        progclass = FileProgress
                        progtrack = progclass(progtrack)

                try:
                        self._frepo.add(trans_id, action)
                except svr_repo.RepositoryError, e:
                        if progtrack:
                                progtrack.abort()
                        raise tx.TransportOperationError(str(e))
                else:
                        if progtrack:
                                sz = int(action.attrs.get("pkg.size", 0))
                                progtrack.progress_callback(0, 0, sz, sz)

        def publish_add_file(self, pth, header=None, trans_id=None):
                """The publish operation that adds a file to an existing
                transaction."""

                try:
                        self._frepo.add_file(trans_id, pth)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_abandon(self, header=None, trans_id=None):
                """The abandon operation, that tells a Repository to abort
                the current transaction.  The caller must specify the
                transaction id in trans_id. Returns a (publish-state, fmri)
                tuple."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                try:
                        pkg_state = self._frepo.abandon(trans_id)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return None, pkg_state

        def publish_close(self, header=None, trans_id=None,
            add_to_catalog=False):
                """The close operation tells the Repository to commit
                the transaction identified by trans_id.  The caller may
                specify add_to_catalog, if needed.  This method returns a
                (publish-state, fmri) tuple."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                try:
                        pkg_fmri, pkg_state = self._frepo.close(trans_id,
                            add_to_catalog=add_to_catalog)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return pkg_fmri, pkg_state

        def publish_open(self, header=None, client_release=None, pkg_name=None):
                """Begin a publication operation by calling 'open'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID string."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                try:
                        trans_id = self._frepo.open(client_release, pkg_name)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return trans_id

        def publish_append(self, header=None, client_release=None,
            pkg_name=None):
                try:
                        trans_id = self._frepo.append(client_release, pkg_name)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return trans_id

        def publish_rebuild(self, header=None, pub=None):
                """Attempt to rebuild the package data and search data in the
                repository."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        self._frepo.rebuild(pub=pub_prefix,
                            build_catalog=True, build_index=True)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_rebuild_indexes(self, header=None, pub=None):
                """Attempt to rebuild the search data in the repository."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        self._frepo.rebuild(pub=pub_prefix,
                            build_catalog=False, build_index=True)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_rebuild_packages(self, header=None, pub=None):
                """Attempt to rebuild the package data in the repository."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        self._frepo.rebuild(pub=pub_prefix,
                            build_catalog=True, build_index=False)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_refresh(self, header=None, pub=None):
                """Attempt to refresh the package data and search data in the
                repository."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        self._frepo.add_content(pub=pub_prefix,
                            refresh_index=True)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_refresh_indexes(self, header=None, pub=None):
                """Attempt to refresh the search data in the repository."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                try:
                        self._frepo.refresh_index()
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_refresh_packages(self, header=None, pub=None):
                """Attempt to refresh the package data in the repository."""

                # Calling any publication operation sets read_only to False.
                self._frepo.read_only = False

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        self._frepo.add_content(pub=pub_prefix,
                            refresh_index=False)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def supports_version(self, op, verlist):
                """Returns version-id of highest supported version.
                If the version is not supported, or no data is available,
                -1 is returned instead."""

                if not self.has_version_data() or op not in self._verdata:
                        return -1

                # This code assumes that both the verlist and verdata
                # are sorted in reverse order.  This behavior is currently
                # implemented in the transport code.

                for v in verlist:
                        if v in self._verdata[op]:
                                return v
                return -1

        def touch_manifest(self, mfst, header=None, ccancel=None, pub=None):
                """No-op for file://."""

                return True

class _ArchiveRepo(TransportRepo):
        """Private implementation of transport repository logic for repositories
        contained within an archive.
        """

        def __init__(self, repostats, repouri, engine):
                """Create a file repo.  Repostats is a RepoStats object.
                Repouri is a RepositoryURI object.  Engine is a transport
                engine object.

                The convenience function new_repo() can be used to create
                the correct repo."""

                self._arc = None
                self._url = repostats.url
                self._repouri = repouri
                self._engine = engine
                self._verdata = None
                self.__stats = repostats

                try:
                        scheme, netloc, path, params, query, fragment = \
                            urlparse.urlparse(self._repouri.uri, "file",
                            allow_fragments=0)
                        # Path must be rstripped of separators to be used as
                        # a file.
                        path = urllib.url2pathname(path.rstrip(os.path.sep))
                        self._arc = pkg.p5p.Archive(path, mode="r")
                except pkg.p5p.InvalidArchive, e:
                        ex = tx.TransportProtoError("file", errno.EINVAL,
                            reason=str(e), repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                except Exception, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex

        def __record_proto_error(self, ex):
                """Private helper function that records a protocol error that
                was raised by the class instead of the transport engine.  It
                records both that a transaction was initiated and that an
                error occurred."""

                self.__stats.record_tx()
                self.__stats.record_error(decayable=ex.decayable)

        def add_version_data(self, verdict):
                """Cache the information about what versions a repository
                supports."""

                self._verdata = verdict

        def get_catalog1(self, filelist, destloc, header=None, ts=None,
            progtrack=None, pub=None, revalidate=False, redownload=False):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch.  This protocol
                doesn't implment revalidate and redownload.  The options
                are ignored."""

                pub_prefix = getattr(pub, "prefix", None)
                errors = []
                for f in filelist:
                        try:
                                self._arc.extract_catalog1(f, destloc,
                                   pub=pub_prefix)
                                if progtrack:
                                        fs = os.stat(os.path.join(destloc, f))
                                        progtrack.download_add_progress(1,
                                            fs.st_size)
                        except pkg.p5p.UnknownArchiveFiles, e:
                                ex = tx.TransportProtoError("file",
                                    errno.ENOENT, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                errors.append(ex)
                                continue
                        except Exception, e:
                                ex = tx.TransportProtoError("file",
                                    errno.EPROTO, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                errors.append(ex)
                                continue
                return errors

        def get_datastream(self, fhash, version, header=None, ccancel=None,
            pub=None):
                """Get a datastream from a repo.  The name of the file is given
                in fhash."""

                pub_prefix = getattr(pub, "prefix", None)
                try:
                        return self._arc.get_package_file(fhash,
                            pub=pub_prefix)
                except pkg.p5p.UnknownArchiveFiles, e:
                        ex = tx.TransportProtoError("file", errno.ENOENT,
                            reason=str(e), repourl=self._url, request=fhash)
                        self.__record_proto_error(ex)
                        raise ex
                except Exception, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url, request=fhash)
                        self.__record_proto_error(ex)
                        raise ex

        def get_publisherinfo(self, header=None, ccancel=None):
                """Get publisher information from the repository."""

                try:
                        pubs = self._arc.get_publishers()
                        buf = cStringIO.StringIO()
                        p5i.write(buf, pubs)
                except Exception, e:
                        reason = "Unable to retrieve publisher configuration " \
                            "data:\n%s" % e
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=reason, repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                buf.seek(0)
                return buf

        def get_manifest(self, fmri, header=None, ccancel=None, pub=None):
                """Get a manifest from repo.  The fmri of the package for the
                manifest is given in fmri."""

                try:
                        return self._arc.get_package_manifest(fmri, raw=True)
                except pkg.p5p.UnknownPackageManifest, e:
                        ex = tx.TransportProtoError("file", errno.ENOENT,
                            reason=str(e), repourl=self._url, request=fmri)
                        self.__record_proto_error(ex)
                        raise ex
                except Exception, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url, request=fmri)
                        self.__record_proto_error(ex)
                        raise ex

        def get_manifests(self, mfstlist, dest, progtrack=None, pub=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                errors = []
                for fmri, h in mfstlist:
                        try:
                                self._arc.extract_package_manifest(fmri, dest,
                                   filename=fmri.get_url_path())
                                if progtrack:
                                        fs = os.stat(os.path.join(dest,
                                            fmri.get_url_path()))
                                        progtrack.download_add_progress(1,
                                            fs.st_size)
                        except pkg.p5p.UnknownPackageManifest, e:
                                ex = tx.TransportProtoError("file",
                                    errno.ENOENT, reason=str(e),
                                    repourl=self._url, request=fmri)
                                self.__record_proto_error(ex)
                                errors.append(ex)
                                continue
                        except Exception, e:
                                ex = tx.TransportProtoError("file",
                                    errno.EPROTO, reason=str(e),
                                    repourl=self._url, request=fmri)
                                self.__record_proto_error(ex)
                                errors.append(ex)
                                continue
                return errors

        def get_files(self, filelist, dest, progtrack, version, header=None, pub=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given.  If progtrack is not None,
                it contains a ProgressTracker object for the
                downloads."""

                pub_prefix = getattr(pub, "prefix", None)
                errors = []
                for f in filelist:
                        try:
                                self._arc.extract_package_files([f], dest,
                                    pub=pub_prefix)
                                if progtrack:
                                        fs = os.stat(os.path.join(dest, f))
                                        progtrack.download_add_progress(1,
                                            fs.st_size)
                        except pkg.p5p.UnknownArchiveFiles, e:
                                ex = tx.TransportProtoError("file",
                                    errno.ENOENT, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                errors.append(ex)
                                continue
                        except Exception, e:
                                ex = tx.TransportProtoError("file",
                                    errno.EPROTO, reason=str(e),
                                    repourl=self._url, request=f)
                                self.__record_proto_error(ex)
                                errors.append(ex)
                                continue
                return errors

        def get_url(self):
                """Returns the repo's url."""

                return self._url

        def get_versions(self, header=None, ccancel=None):
                """Query the repo for versions information.
                Returns a file-like object."""

                buf = cStringIO.StringIO()
                vops = {
                    "catalog": ["1"],
                    "file": ["0"],
                    "manifest": ["0"],
                    "publisher": ["0", "1"],
                    "versions": ["0"],
                }

                buf.write("pkg-server %s\n" % pkg.VERSION)
                buf.write("\n".join(
                    "%s %s" % (op, " ".join(vers))
                    for op, vers in vops.iteritems()
                ) + "\n")
                buf.seek(0)
                self.__stats.record_tx()
                return buf

        def has_version_data(self):
                """Returns true if this repo knows its version information."""

                return self._verdata is not None

        def supports_version(self, op, verlist):
                """Returns version-id of highest supported version.
                If the version is not supported, or no data is available,
                -1 is returned instead."""

                if not self.has_version_data() or op not in self._verdata:
                        return -1

                # This code assumes that both the verlist and verdata
                # are sorted in reverse order.  This behavior is currently
                # implemented in the transport code.

                for v in verlist:
                        if v in self._verdata[op]:
                                return v
                return -1

        def touch_manifest(self, mfst, header=None, ccancel=None, pub=None):
                """No-op."""
                return True


class FileRepo(object):
        """Factory class for creating transport repository objects for
        filesystem-based repository sources.
        """

        def __new__(cls, repostats, repouri, engine, frepo=None):
                """Returns a new transport repository object based on the
                provided information.

                'repostats' is a RepoStats object.

                'repouri' is a RepositoryURI object.
                
                'engine' is a transport engine object.

                'frepo' is an optional Repository object to use instead
                of creating one.

                The convenience function new_repo() can be used to create
                the correct repo."""

                try:
                        scheme, netloc, path, params, query, fragment = \
                            urlparse.urlparse(repouri.uri, "file",
                            allow_fragments=0)
                        path = urllib.url2pathname(path)
                except Exception, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=repostats.url)
                        repostats.record_tx()
                        repostats.record_error(decayable=ex.decayable)
                        raise ex

                # Path must be rstripped of separators for this check to
                # succeed.
                if not frepo and os.path.isfile(path.rstrip(os.path.sep)):
                        # Assume target is a repository archive.
                        return _ArchiveRepo(repostats, repouri, engine)

                # Assume target is a filesystem repository.
                return _FilesystemRepo(repostats, repouri, engine, frepo=frepo)


# ProgressCallback objects that bridge the interfaces between ProgressTracker,
# and the necessary callbacks for the TransportEngine.

class ProgressCallback(object):
        """This class bridges the interfaces between a ProgressTracker
        object and the progress callback that's provided by Pycurl.
        Since progress callbacks are per curl handle, and handles aren't
        guaranteed to succeed, this object watches a handle's progress
        and updates the tracker accordingly."""

        def __init__(self, progtrack):
                self.progtrack = progtrack

        def abort(self):
                """Download failed."""
                pass

        def commit(self, size):
                """This download has succeeded.  The size argument is
                the total size that the client received."""
                pass

        def progress_callback(self, dltot, dlcur, ultot, ulcur):
                """Called by pycurl/libcurl framework to update
                progress tracking."""

                if hasattr(self.progtrack, "check_cancelation") and \
                    self.progtrack.check_cancelation():
                        return -1

                return 0


class FileProgress(ProgressCallback):
        """This class bridges the interfaces between a ProgressTracker
        object and the progress callback that's provided by Pycurl.
        Since progress callbacks are per curl handle, and handles aren't
        guaranteed to succeed, this object watches a handle's progress
        and updates the tracker accordingly.  If the handle fails,
        it will correctly remove the bytes from the file.  The curl
        callback reports bytes even when it doesn't make progress.
        It's necessary to keep additonal state here, since the client's
        ProgressTracker has global counts of the bytes.  If we're
        unable to keep a per-file count, the numbers will get
        lost quickly."""

        def __init__(self, progtrack):
                ProgressCallback.__init__(self, progtrack)
                self.dltotal = 0
                self.dlcurrent = 0
                self.ultotal = 0
                self.ulcurrent = 0
                self.completed = False

        def abort(self):
                """Download failed.  Remove the amount of bytes downloaded
                by this file from the ProgressTracker."""

                self.progtrack.download_add_progress(0, -self.dlcurrent)
                self.progtrack.upload_add_progress(-self.ulcurrent)
                self.completed = True

        def commit(self, size):
                """Indicate that this download has succeeded.  The size
                argument is the total size that we received.  Compare this
                value against the dlcurrent.  If it's out of sync, which
                can happen if the underlying framework swaps our request
                across connections, adjust the progress tracker by the
                amount we're off."""

                adjustment = int(size - self.dlcurrent)

                self.progtrack.download_add_progress(1, adjustment)
                self.completed = True

        def progress_callback(self, dltot, dlcur, ultot, ulcur):
                """Called by pycurl/libcurl framework to update
                progress tracking."""

                if hasattr(self.progtrack, "check_cancelation") and \
                    self.progtrack.check_cancelation():
                        return -1

                if self.completed:
                        return 0

                if self.dltotal != dltot:
                        self.dltotal = dltot

                new_progress = int(dlcur - self.dlcurrent)
                if new_progress > 0:
                        self.dlcurrent += new_progress
                        self.progtrack.download_add_progress(0, new_progress)

                if self.ultotal != ultot:
                        self.ultotal = ultot

                new_progress = int(ulcur - self.ulcurrent)
                if new_progress > 0:
                        self.ulcurrent += new_progress
                        self.progtrack.upload_add_progress(new_progress)

                return 0


# cache transport repo objects, so one isn't created on every operation

class RepoCache(object):
        """An Object that caches repository objects.  Used to make
        sure that repos are re-used instead of re-created for each
        operation."""

        # Schemes supported by the cache.
        supported_schemes = {
            "file": FileRepo,
            "http": HTTPRepo,
            "https": HTTPSRepo,
        }

        update_schemes = {
            "file": FileRepo
        }

        def __init__(self, engine):
                """Caller must include a TransportEngine."""

                self.__engine = engine
                self.__cache = {}

        def __contains__(self, url):
                return url in self.__cache

        def clear_cache(self):
                """Flush the contents of the cache."""

                self.__cache = {}

        def new_repo(self, repostats, repouri):
                """Create a new repo server for the given repouri object."""

                origin_url = repostats.url
                urltuple = urlparse.urlparse(origin_url)
                scheme = urltuple[0]

                if scheme not in RepoCache.supported_schemes:
                        raise tx.TransportOperationError("Scheme %s not"
                            " supported by transport." % scheme)

                if origin_url in self.__cache:
                        return self.__cache[origin_url]

                repo = RepoCache.supported_schemes[scheme](repostats, repouri,
                    self.__engine)

                self.__cache[origin_url] = repo

                return repo

        def update_repo(self, repostats, repouri, repository):
                """For the FileRepo, some callers need to update its
                Repository object.  They should use this method to do so.
                If the Repo isn't in the cache, it's created and added."""

                origin_url = repostats.url
                urltuple = urlparse.urlparse(origin_url)
                scheme = urltuple[0]

                if scheme not in RepoCache.update_schemes:
                        return

                if origin_url in self.__cache:
                        repo = self.__cache[origin_url]
                        repo._frepo = repository
                        return

                repo = RepoCache.update_schemes[scheme](repostats, repouri,
                    self.__engine, frepo=repository)

                self.__cache[origin_url] = repo

        def remove_repo(self, repo=None, url=None):
                """Remove a repo from the cache.  Caller must supply
                either a RepositoryURI object or a URL."""

                if repo:
                        origin_url = repo.uri
                elif url:
                        origin_url = url
                else:
                        raise ValueError, "Must supply either a repo or a uri."

                if origin_url in self.__cache:
                        del self.__cache[origin_url]
