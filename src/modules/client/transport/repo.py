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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import urlparse
import urllib

import pkg.client.transport.exception as tx

from email.Utils import formatdate

class TransportRepo(object):
        """The TransportRepo class handles transport requests.
        It represents a repo, and provides the same interfaces as
        the operations that are performed against a repo.  Subclasses
        should implement protocol specific repo modifications."""

        def do_search(self, data, header=None):
                """Perform a search request."""

                raise NotImplementedError

        def get_catalog(self, ts=None, header=None):
                """Get the catalog from the repo.  If ts is defined,
                request only changes newer than timestamp ts."""

                raise NotImplementedError

        def get_manifest(self, mfst, header=None):
                """Get a manifest from repo.  The name of the
                manifest is given in mfst.  If dest is set, download
                the manifest to dest."""

                raise NotImplementedError

        def get_files(self, filelist, dest, progtrack, header=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given. Progtrack is a ProgressTracker"""

                raise NotImplementedError

        def get_url(self):
                """Return's the Repo's URL."""

                raise NotImplementedError

        def get_versions(self, header=None):
                """Query the repo for versions information.
                Returns a fileobject."""

                raise NotImplementedError

        def touch_manifest(self, mfst, header=None):
                """Send data about operation intent without actually
                downloading a manifest."""

                raise NotImplementedError


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

        def _add_file_url(self, url, filepath=None, progclass=None,
            progtrack=None, header=None, compress=False):
                self._engine.add_url(url, filepath=filepath,
                    progclass=progclass, progtrack=progtrack, repourl=self._url,
                    header=header, compressible=compress)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None):
                return self._engine.get_url(url, header, repourl=self._url,
                    compressible=compress, ccancel=ccancel)

        def _fetch_url_header(self, url, header=None, ccancel=None):
                return self._engine.get_url_header(url, header,
                    repourl=self._url, ccancel=ccancel)

        def _post_url(self, url, data, header=None, ccancel=None):
                return self._engine.send_data(url, data, header,
                    repourl=self._url, ccancel=ccancel)

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

        def get_datastream(self, fhash, header=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                methodstr = "file/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, fhash)

                return self._fetch_url(requesturl, header)

        def get_manifest(self, mfst, header=None, ccancel=None):
                """Get a manifest from repo.  The name of the
                manifest is given in mfst."""

                methodstr = "manifest/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, mfst)

                return self._fetch_url(requesturl, header, compress=True,
                    ccancel=ccancel)

        def get_manifests(self, mfstlist, dest, progtrack=None):
                """Get manifests named in list.  The mfstlist argument
                contains tuples (manifest_name, header).  This is so
                that each manifest may contain unique header information.
                The destination directory is specified in the dest argument."""

                methodstr = "manifest/0/"
                urllist = []
                progclass = None

                # create URL for requests
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)

                if progtrack:
                        progclass = ProgressCallback

                for f, h in mfstlist:
                        url = urlparse.urljoin(baseurl, f)
                        urllist.append(url)
                        fn = os.path.join(dest, f)
                        self._add_file_url(url, filepath=fn, header=h,
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
                # to throw them or not.  Permanant failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.

                return self._annotate_exceptions(errors)

        @staticmethod
        def _annotate_exceptions(errors):
                """Walk a list of transport errors, examine the
                url, and add a field that names the request.  This request
                information is derived from the URL."""

                for e in errors:
                        eurl = e.url
                        utup = urlparse.urlsplit(eurl)
                        req = utup[2]
                        req = os.path.basename(req)
                        e.request = req

                return errors

        @staticmethod
        def _url_to_request(urllist):
                """Take a list of urls and remove the protocol information,
                leaving just the information about the request."""

                reqlist = []

                for u in urllist:
                        utup = urlparse.urlsplit(u)
                        req = utup[2]
                        req = os.path.basename(req)
                        reqlist.append(req)

                return reqlist

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
                return self._fetch_url(requesturl, header, ccancel=None)

        def has_version_data(self):
                """Returns true if this repo knows its version information."""

                return self._verdata is not None

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
                    header=header, compressible=compress)

        def _fetch_url(self, url, header=None, compress=False, ccancel=None):
                return self._engine.get_url(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    compressible=compress, ccancel=ccancel)

        def _fetch_url_header(self, url, header=None, ccancel=None):
                return self._engine.get_url_header(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    ccancel=ccancel)

        def _post_url(self, url, data, header=None, ccancel=None):
                return self._engine.send_data(url, data, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    ccancel=ccancel)

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
            "http": HTTPRepo,
            "https": HTTPSRepo,
        }

        def __init__(self, engine):
                """Caller must include a TransportEngine."""

                self.__engine = engine
                self.__cache = {}

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
