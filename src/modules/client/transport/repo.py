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

        def _add_file_url(self, url, filepath=None, progtrack=None,
            header=None):
                self._engine.add_url(url, filepath=filepath,
                    progtrack=progtrack, repourl=self._url, header=header)

        def _fetch_url(self, url, header=None, compress=False):
                return self._engine.get_url(url, header, repourl=self._url,
                    compressible=compress)

        def _fetch_url_header(self, url, header=None):
                return self._engine.get_url_header(url, header,
                    repourl=self._url)

        def _post_url(self, url, data, header=None):
                return self._engine.send_data(url, data, header,
                    repourl=self._url)

        def do_search(self, data, header=None):
                """Perform a remote search against origin repos."""

                methodstr = "search/1/"

                if len(data) > 1:
                        requesturl = urlparse.urljoin(self._repouri.uri,
                            methodstr)
                        request_data = urllib.urlencode(
                            [(i, str(q))
                            for i, q in enumerate(data)])

                        resp = self._post_url(requesturl, request_data,
                            header)

                else:
                        baseurl = urlparse.urljoin(self._repouri.uri,
                            methodstr)
                        requesturl = urlparse.urljoin(baseurl, urllib.quote(
                            str(data[0]), safe=''))

                        resp = self._fetch_url(requesturl, header)

                return resp

        def get_catalog(self, ts=None, header=None):
                """Get the catalog from the repo.  If ts is defined,
                request only changes newer than timestamp ts."""

                methodstr = "catalog/0/"

                requesturl = urlparse.urljoin(self._repouri.uri, methodstr)

                if ts:
                        if not header:
                                header = {"If-Modified-Since": ts}
                        else:
                                header["If-Modified-Since"] = ts

                return self._fetch_url(requesturl, header, compress=True)

        def get_datastream(self, fhash, header=None):
                """Get a datastream from a repo.  The name of the
                file is given in fhash."""

                methodstr = "file/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, fhash)

                return self._fetch_url(requesturl, header)

        def get_manifest(self, mfst, header=None):
                """Get a manifest from repo.  The name of the
                manifest is given in mfst."""

                methodstr = "manifest/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, mfst)

                return self._fetch_url(requesturl, header, compress=True)

        def get_files(self, filelist, dest, progtrack, header=None):
                """Get multiple files from the repo at once.
                The files are named by hash and supplied in filelist.
                If dest is specified, download to the destination
                directory that is given.  If progtrack is not None,
                it contains a ProgressTracker object for the
                downloads."""

                methodstr = "file/0/"
                urllist = []

                # create URL for requests
                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)

                for f in filelist:
                        url = urlparse.urljoin(baseurl, f)
                        urllist.append(url)
                        fn = os.path.join(dest, f)
                        self._add_file_url(url, filepath=fn,
                            progtrack=progtrack, header=header)

                while self._engine.pending:
                        self._engine.run()

                errors = self._engine.check_status(urllist)

                # Transient errors are part of standard control flow.
                # The repo's caller will look at these and decide whether
                # to throw them or not.  Permanant failures are raised
                # by the transport engine as soon as they occur.
                #
                # This adds an attribute that describes the request to the
                # exception, if we were able to figure it out.

                for e in errors:
                        # when check_status is supplied with a list,
                        # all exceptions returned will have a url.
                        # If we didn't do this, we'd need a getattr check.
                        eurl = e.url
                        utup = urlparse.urlsplit(eurl)
                        req = utup[2]
                        req = os.path.basename(req)
                        e.request = req

                return errors

        def get_url(self):
                """Returns the repo's url."""

                return self._url

        def get_versions(self, header=None):
                """Query the repo for versions information.
                Returns a fileobject."""

                requesturl = urlparse.urljoin(self._repouri.uri, "versions/0/")

                resp = self._fetch_url(requesturl, header)

                return resp

        def touch_manifest(self, mfst, header=None):
                """Invoke HTTP HEAD to send manifest intent data."""

                methodstr = "manifest/0/"

                baseurl = urlparse.urljoin(self._repouri.uri, methodstr)
                requesturl = urlparse.urljoin(baseurl, mfst)

                resp = self._fetch_url_header(requesturl, header)

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
        def _add_file_url(self, url, filepath=None, progtrack=None,
            header=None):
                self._engine.add_url(url, filepath=filepath,
                    progtrack=progtrack, sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    header=header)

        def _fetch_url(self, url, header=None, compress=False):
                return self._engine.get_url(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url,
                    compressible=compress)

        def _fetch_url_header(self, url, header=None):
                return self._engine.get_url_header(url, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url)

        def _post_url(self, url, data, header=None):
                return self._engine.send_data(url, data, header=header,
                    sslcert=self._repouri.ssl_cert,
                    sslkey=self._repouri.ssl_key, repourl=self._url)

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
