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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import cStringIO
import errno
import itertools
import os
import urlparse
import urllib

import pkg
import pkg.p5i as p5i
import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.client.transport.exception as tx
import pkg.config as cfg
import pkg.server.repository as svr_repo
import pkg.server.query_parser as sqp

from email.Utils import formatdate


class TransportRepo(object):
        """The TransportRepo class handles transport requests.
        It represents a repo, and provides the same interfaces as
        the operations that are performed against a repo.  Subclasses
        should implement protocol specific repo modifications."""

        def do_search(self, data, header=None, ccancel=None):
                """Perform a search request."""

                raise NotImplementedError

        def get_catalog(self, ts=None, header=None, ccancel=None):
                """Get the catalog from the repo.  If ts is defined,
                request only changes newer than timestamp ts."""

                raise NotImplementedError

        def get_catalog1(self, filelist, destloc, header=None, ts=None,
            progtrack=None):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch."""

                raise NotImplementedError

        def get_datastream(self, fhash, header=None, ccancel=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                raise NotImplementedError

        def get_files(self, filelist, dest, progtrack, header=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given. Progtrack is a ProgressTracker"""

                raise NotImplementedError

        def get_manifest(self, fmri, header=None, ccancel=None):
                """Get a manifest from repo.  The name of the
                package is given in fmri.  If dest is set, download
                the manifest to dest."""

                raise NotImplementedError

        def get_manifests(self, mfstlist, dest, progtrack=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                raise NotImplementedError

        def get_publisherinfo(self, header=None, ccancel=None):
                """Get publisher configuration information from the
                repository."""

                raise NotImplementedError

        def get_url(self):
                """Return's the Repo's URL."""

                raise NotImplementedError

        def get_versions(self, header=None, ccancel=None):
                """Query the repo for versions information.
                Returns a fileobject."""

                raise NotImplementedError

        def publish_add(self, action, header=None, trans_id=None):
                """The publish operation that adds content to a repository.
                The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                raise NotImplementedError

        def publish_abandon(self, header=None, trans_id=None):
                """The 'abandon' publication operation, that tells a
                Repository to abort the current transaction.  The caller
                must specify the transaction id in trans_id. Returns
                a (publish-state, fmri) tuple."""

                raise NotImplementedError

        def publish_close(self, header=None, trans_id=None, refresh_index=False,
            add_to_catalog=False):
                """The close operation tells the Repository to commit
                the transaction identified by trans_id.  The caller may
                specify refresh_index and add_to_catalog, if needed.
                This method returns a (publish-state, fmri) tuple."""

                raise NotImplementedError

        def publish_open(self, header=None, client_release=None, pkg_name=None):
                """Begin a publication operation by calling 'open'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID."""

                raise NotImplementedError

        def publish_refresh_index(self, header=None):
                """If the Repo points to a Repository that has a refresh-able
                index, refresh the index."""

                raise NotImplementedError

        def touch_manifest(self, fmri, header=None, ccancel=None):
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
                self._sock_path = getattr(self._repouri, "socket_path", None)

        def _add_file_url(self, url, filepath=None, progclass=None,
            progtrack=None, header=None, compress=False):
                self._engine.add_url(url, filepath=filepath,
                    progclass=progclass, progtrack=progtrack, repourl=self._url,
                    header=header, compressible=compress,
                    sock_path=self._sock_path)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None):
                return self._engine.get_url(url, header, repourl=self._url,
                    compressible=compress, ccancel=ccancel,
                    sock_path=self._sock_path)

        def _fetch_url_header(self, url, header=None, ccancel=None):
                return self._engine.get_url_header(url, header,
                    repourl=self._url, ccancel=ccancel,
                    sock_path=self._sock_path)

        def _post_url(self, url, data=None, header=None, ccancel=None,
            data_fobj=None):
                return self._engine.send_data(url, data=data, header=header,
                    repourl=self._url, ccancel=ccancel,
                    sock_path=self._sock_path, data_fobj=data_fobj)

        def add_version_data(self, verdict):
                """Cache the information about what versions a repository
                supports."""

                self._verdata = verdict

        def do_search(self, data, header=None, ccancel=None):
                """Perform a remote search against origin repos."""

                methodstr = "search/1/"

                if len(data) > 1:
                        requesturl = urlparse.urljoin(self._repouri.uri,
                            methodstr)
                        request_data = urllib.urlencode(
                            [(i, str(q))
                            for i, q in enumerate(data)])

                        resp = self._post_url(requesturl, request_data,
                            header, ccancel=ccancel)

                else:
                        baseurl = urlparse.urljoin(self._repouri.uri,
                            methodstr)
                        requesturl = urlparse.urljoin(baseurl, urllib.quote(
                            str(data[0]), safe=''))

                        resp = self._fetch_url(requesturl, header,
                            ccancel=ccancel)

                return resp

        def get_catalog(self, ts=None, header=None, ccancel=None):
                """Get the catalog from the repo.  If ts is defined,
                request only changes newer than timestamp ts."""

                methodstr = "catalog/0/"

                requesturl = urlparse.urljoin(self._repouri.uri, methodstr)

                if ts:
                        if not header:
                                header = {"If-Modified-Since": ts}
                        else:
                                header["If-Modified-Since"] = ts

                return self._fetch_url(requesturl, header, compress=True,
                    ccancel=ccancel)

        def get_catalog1(self, filelist, destloc, header=None, ts=None,
            progtrack=None):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch."""

                methodstr = "catalog/1/"
                urllist = []
                progclass = None

                if ts:
                        # Convert date to RFC 1123 compliant string
                        tsstr = formatdate(timeval=ts, localtime=False,
                            usegmt=True)
                        if not header:
                                header = {"If-Modified-Since": tsstr}
                        else:
                                header["If-Modified-Since"] = tsstr

                if progtrack:
                        progclass = ProgressCallback

                # create URL for requests
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)

                for f in filelist:
                        url = urlparse.urljoin(baseurl, f)
                        urllist.append(url)
                        fn = os.path.join(destloc, f)
                        self._add_file_url(url, filepath=fn, header=header,
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

        def get_datastream(self, fhash, header=None, ccancel=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                methodstr = "file/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, fhash)

                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_publisherinfo(self, header=None, ccancel=None):
                """Get publisher/0 information from the repository."""

                requesturl = urlparse.urljoin(self._repouri.uri, "publisher/0/")
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_manifest(self, fmri, header=None, ccancel=None):
                """Get a package manifest from repo.  The FMRI of the
                package is given in fmri."""

                methodstr = "manifest/0/"

                mfst = fmri.get_url_path()
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, mfst)

                return self._fetch_url(requesturl, header, compress=True,
                    ccancel=ccancel)

        def get_manifests(self, mfstlist, dest, progtrack=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                methodstr = "manifest/0/"
                urlmapping = {}
                progclass = None

                # create URL for requests
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)

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

        def get_files(self, filelist, dest, progtrack, header=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given.  If progtrack is not None,
                it contains a ProgressTracker object for the
                downloads."""

                methodstr = "file/0/"
                urllist = []
                progclass = None

                if progtrack:
                        progclass = FileProgress

                # create URL for requests
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)

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

                requesturl = urlparse.urljoin(self._repouri.uri, "versions/0/")
                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def has_version_data(self):
                """Returns true if this repo knows its version information."""

                return self._verdata is not None

        def publish_add(self, action, header=None, trans_id=None):
                """The publish operation that adds content to a repository.
                The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                attrs = action.attrs
                data_fobj = None
                data = None
                methodstr = "add/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
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
                    data_fobj=data_fobj, data=data)

                # Discard response body
                fobj.read()

        def publish_abandon(self, header=None, trans_id=None):
                """The 'abandon' publication operation, that tells a
                Repository to abort the current transaction.  The caller
                must specify the transaction id in trans_id. Returns
                a (publish-state, fmri) tuple."""

                methodstr = "abandon/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                request_str = trans_id
                requesturl = urlparse.urljoin(baseurl, request_str)

                fobj = self._fetch_url(requesturl, header=header)

                # Discard response body
                fobj.read()

                return fobj.getheader("State", None), \
                     fobj.getheader("Package-FMRI", None)

        def publish_close(self, header=None, trans_id=None, refresh_index=False,
            add_to_catalog=False):
                """The close operation tells the Repository to commit
                the transaction identified by trans_id.  The caller may
                specify refresh_index and add_to_catalog, if needed.
                This method returns a (publish-state, fmri) tuple."""

                methodstr = "close/0/"
                headers = {}
                if not refresh_index:
                        headers["X-IPkg-Refresh-Index"] = 0
                if not add_to_catalog:
                        headers["X-IPkg-Add-To-Catalog"] = 0
                if header:
                        headers.update(header)

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                request_str = trans_id
                requesturl = urlparse.urljoin(baseurl, request_str)

                fobj = self._fetch_url(requesturl, header=headers)

                # Discard response body
                fobj.read()

                return fobj.getheader("State", None), \
                     fobj.getheader("Package-FMRI", None)

        def publish_open(self, header=None, client_release=None, pkg_name=None):
                """Begin a publication operation by calling 'open'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID."""

                methodstr = "open/0/"
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                request_str = urllib.quote(pkg_name, "")
                requesturl = urlparse.urljoin(baseurl, request_str)

                headers = {"Client-Release": client_release}
                if header:
                        headers.update(header)

                fobj = self._fetch_url(requesturl, header=headers)

                # Discard response body
                fobj.read()

                return fobj.getheader("Transaction-ID", None)

        def publish_refresh_index(self, header=None):
                """If the Repo points to a Repository that has a refresh-able
                index, refresh the index."""

                methodstr = "index/0/refresh/"
                requesturl = urlparse.urljoin(self._repouri.uri, methodstr)

                fobj = self._fetch_url(requesturl, header=header)

                # Discard response body
                fobj.read()

        def supports_version(self, op, ver):
                """Returns true if operation named in string 'op'
                supports integer version in 'ver' argument."""

                return self.has_version_data() and \
                    (op in self._verdata and ver in self._verdata[op])

        def touch_manifest(self, mfst, header=None, ccancel=None):
                """Invoke HTTP HEAD to send manifest intent data."""

                methodstr = "manifest/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
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
                    header=header, compressible=compress,
                    sock_path=self._sock_path)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None):
                return self._engine.get_url(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    compressible=compress, ccancel=ccancel,
                    sock_path=self._sock_path)

        def _fetch_url_header(self, url, header=None, ccancel=None):
                return self._engine.get_url_header(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    ccancel=ccancel, sock_path=self._sock_path)

        def _post_url(self, url, data=None, header=None, ccancel=None,
            data_fobj=None):
                return self._engine.send_data(url, data=data, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    ccancel=ccancel, sock_path=self._sock_path,
                    data_fobj=data_fobj)


class FileRepo(TransportRepo):

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
                            repo_root=path)
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
                        sqp.TermQuery.clear_cache(self._frepo.index_root)
                        self._frepo = None

        def _add_file_url(self, url, filepath=None, progclass=None,
            progtrack=None, header=None, compress=False):
                self._engine.add_url(url, filepath=filepath,
                    progclass=progclass, progtrack=progtrack, repourl=self._url,
                    header=header, compressible=False)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None):
                return self._engine.get_url(url, header, repourl=self._url,
                    compressible=False, ccancel=ccancel)

        def _fetch_url_header(self, url, header=None, ccancel=None):
                return self._engine.get_url_header(url, header,
                    repourl=self._url, ccancel=ccancel)

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

        def do_search(self, data, header=None, ccancel=None):
                """Perform a search against repo."""

                if not self._frepo.search_available:
                        ex = tx.TransportProtoError("file", errno.EAGAIN,
                            reason=_("Search temporarily unavailable."),
                            repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex

                try:
                        res_list = self._frepo.search(data)
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
            progtrack=None):
                """Get the files that make up the catalog components
                that are listed in 'filelist'.  Download the files to
                the directory specified in 'destloc'.  The caller
                may optionally specify a dictionary with header
                elements in 'header'.  If a conditional get is
                to be performed, 'ts' should contain a floating point
                value of seconds since the epoch."""

                urllist = []
                progclass = None
                if progtrack:
                        progclass = ProgressCallback

                # create URL for requests
                for f in filelist:
                        url = urlparse.urlunparse(("file", "", 
                            urllib.pathname2url(self._frepo.catalog_1(f)), "",
                            "", ""))
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

        def get_datastream(self, fhash, header=None, ccancel=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                try:
                        requesturl = urlparse.urlunparse(("file", "", 
                            urllib.pathname2url(self._frepo.file(fhash)), "",
                            "", ""))
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
                """Get publisher/0 information from the repository."""

                try:
                        rargs = {}
                        for prop in ("collection_type", "description",
                            "legal_uris", "mirrors", "name", "origins",
                            "refresh_seconds", "registration_uri",
                            "related_uris"):
                                rargs[prop] = self._frepo.cfg.get_property(
                                    "repository", prop)

                        repo = publisher.Repository(**rargs)
                        alias = self._frepo.cfg.get_property("publisher",
                            "alias")
                        pfx = self._frepo.cfg.get_property("publisher",
                            "prefix")
                        pub = publisher.Publisher(pfx, alias=alias,
                            repositories=[repo])

                        buf = cStringIO.StringIO()
                        p5i.write(buf, [pub])
                except Exception, e:
                        reason = "Unable to retrieve publisher configuration " \
                            "data:\n%s" % e
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=reason, repourl=self._url)
                        self.__record_proto_error(ex)
                        raise ex
                buf.seek(0)
                return buf

        def get_manifest(self, fmri, header=None, ccancel=None):
                """Get a manifest from repo.  The fmri of the package for the
                manifest is given in fmri."""

                try:
                        requesturl = urlparse.urlunparse(("file", "", 
                            urllib.pathname2url(self._frepo.manifest(fmri)), "",
                            "", ""))
                except svr_repo.RepositoryError, e:
                        ex = tx.TransportProtoError("file", errno.EPROTO,
                            reason=str(e), repourl=self._url, request=str(fmri))
                        self.__record_proto_error(ex)
                        raise ex

                return self._fetch_url(requesturl, header, ccancel=ccancel)

        def get_manifests(self, mfstlist, dest, progtrack=None):
                """Get manifests named in list.  The mfstlist argument contains
                tuples (fmri, header).  This is so that each manifest may have
                unique header information.  The destination directory is spec-
                ified in the dest argument."""

                urlmapping = {}
                progclass = None

                if progtrack:
                        progclass = ProgressCallback

                # Errors that happen before the engine is executed must be
                # collected and added to the errors raised during engine
                # execution so that batch processing occurs as expected.
                pre_exec_errors = []
                for fmri, h in mfstlist:
                        try:
                                url = urlparse.urlunparse(("file", "", 
                                    urllib.pathname2url(self._frepo.manifest(
                                    fmri)), "", "", ""))
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

        def get_files(self, filelist, dest, progtrack, header=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given.  If progtrack is not None,
                it contains a ProgressTracker object for the
                downloads."""

                urllist = []
                progclass = None

                if progtrack:
                        progclass = FileProgress

                # Errors that happen before the engine is executed must be
                # collected and added to the errors raised during engine
                # execution so that batch processing occurs as expected.
                pre_exec_errors = []
                for f in filelist:
                        try:
                                url = urlparse.urlunparse(("file", "", 
                                    urllib.pathname2url(self._frepo.file(f)),
                                    "", "", ""))
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
                    "catalog": ["1"],
                    "file": ["0"],
                    "manifest": ["0"],
                    "publisher": ["0"],
                    "search": ["1"],
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

        def publish_add(self, action, header=None, trans_id=None):
                """The publish operation that adds an action and its
                payload (if applicable) to an existing transaction in a
                repository.  The action must be populated with a data property.
                Callers may supply a header, and should supply a transaction
                id in trans_id."""

                try:
                        self._frepo.add(trans_id, action)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def publish_abandon(self, header=None, trans_id=None):
                """The abandon operation, that tells a Repository to abort
                the current transaction.  The caller must specify the
                transaction id in trans_id. Returns a (publish-state, fmri)
                tuple."""

                try:
                        pkg_state = self._frepo.abandon(trans_id)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return None, pkg_state

        def publish_close(self, header=None, trans_id=None, refresh_index=False,
            add_to_catalog=False):
                """The close operation tells the Repository to commit
                the transaction identified by trans_id.  The caller may
                specify refresh_index and add_to_catalog, if needed.
                This method returns a (publish-state, fmri) tuple."""

                try:
                        pkg_fmri, pkg_state = self._frepo.close(trans_id,
                            refresh_index=refresh_index,
                            add_to_catalog=add_to_catalog)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return pkg_fmri, pkg_state

        def publish_open(self, header=None, client_release=None, pkg_name=None):
                """Begin a publication operation by calling 'open'.
                The caller must specify the client's OS release in
                client_release, and the package's name in pkg_name.
                Returns a transaction-ID string."""

                try:
                        trans_id = self._frepo.open(client_release, pkg_name)
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

                return trans_id

        def publish_refresh_index(self, header=None):
                """If the Repo points to a Repository that has a refresh-able
                index, refresh the index."""

                try:
                        self._frepo.refresh_index()
                except svr_repo.RepositoryError, e:
                        raise tx.TransportOperationError(str(e))

        def supports_version(self, op, ver):
                """Returns true if operation named in string 'op'
                supports integer version in 'ver' argument."""

                return self.has_version_data() and \
                    (op in self._verdata and ver in self._verdata[op])

        def touch_manifest(self, mfst, header=None, ccancel=None):
                """No-op for file://."""

                return True


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
                self.completed = False

        def abort(self):
                """Download failed.  Remove the amount of bytes downloaded
                by this file from the ProgressTracker."""

                self.progtrack.download_add_progress(0, -self.dlcurrent)
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
