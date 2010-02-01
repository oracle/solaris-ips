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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import errno
import httplib
import os
import statvfs
import zlib
import cStringIO

import pkg.catalog as catalog
import pkg.client.api_errors as apx
import pkg.client.imageconfig as imageconfig
import pkg.client.publisher as publisher
import pkg.client.transport.engine as engine
import pkg.client.transport.exception as tx
import pkg.client.transport.repo as trepo
import pkg.client.transport.stats as tstats
import pkg.file_layout.file_manager as file_manager
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.nrlock as nrlock
import pkg.portable as portable
import pkg.updatelog as updatelog

from pkg.actions import ActionError
from pkg.client import global_settings

class Transport(object):
        """The generic transport wrapper object.  Its public methods should
        be used by all client code that wishes to perform file/network
        packaging operations."""

        def __init__(self, img):
                """Initialize the Transport object.  If an Image object
                is provided in img, use that to determine some of the
                destination locations for transport operations."""

                self.__img = img
                self.__engine = None
                self.__cadir = None
                self.__portal_test_executed = False
                self.__repo_cache = None
                self.__lock = nrlock.NRLock()
                self.stats = tstats.RepoChooser()
                self.cache_store = None

        def __setup(self):
                self.__engine = engine.CurlTransportEngine(self)

                # Configure engine's user agent based upon img configuration
                ua = misc.user_agent_str(self.__img,
                    global_settings.client_name)
                self.__engine.set_user_agent(ua)

                self.__repo_cache = trepo.RepoCache(self.__engine)

                self.cache_store = file_manager.FileManager(
                    self.__img.cached_download_dir(), False)

        def reset(self):
                """Resets the transport.  This needs to be done
                if an install plan has been canceled and needs to
                be restarted.  This clears the state of the
                transport and its associated components."""

                if not self.__engine:
                        # Don't reset if not configured
                        return

                self.__lock.acquire()
                try:
                        self.__engine.reset()
                        self.__repo_cache.clear_cache()
                finally:
                        self.__lock.release()

        def shutdown(self):
                """Shuts down any portions of the transport that can
                actively be connected to remote endpoints."""

                if not self.__engine:
                        # Already shut down
                        return

                self.__lock.acquire()
                try:
                        self.__engine.shutdown()
                        self.__engine = None
                        self.__repo_cache = None
                        self.cache_store = None
                finally:
                        self.__lock.release()

        def do_search(self, pub, data, ccancel=None):
                """Perform a search request.  Returns a file-like object
                that contains the search results.  Callers need to catch
                transport exceptions that this object may generate."""

                self.__lock.acquire()
                try:
                        fobj = self._do_search(pub, data, ccancel=ccancel)
                finally:
                        self.__lock.release()

                # Since we're returning a file object that's using the
                # same engine as the rest of this transport, assign
                # our lock to the fobj.  It must synchronize with us
                # too.
                fobj.set_lock(self.__lock)

                return fobj

        def _do_search(self, pub, data, ccancel=None):
                """Implementation of do_search, which is wrapper for this
                method."""

                failures = tx.TransportFailures()
                fobj = None
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = None

                if isinstance(pub, publisher.Publisher):
                        header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):

                        try:
                                fobj = d.do_search(data, header,
                                    ccancel=ccancel)
                                fobj._prime()
                                return fobj

                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(ex.failures)

                        except tx.TransportProtoError, e:
                                if e.code == httplib.NOT_FOUND:
                                        raise apx.UnsupportedSearchError(e.url,
                                            "search/1")
                                elif e.code == httplib.NO_CONTENT:
                                        raise apx.NegativeSearchResult(e.url)
                                elif e.code == httplib.BAD_REQUEST:
                                        raise apx.MalformedSearchRequest(e.url)
                                elif e.retryable:
                                        failures.append(e)
                                else:
                                        raise

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                        fobj = None
                                else:
                                        raise

                raise failures

        def get_ca_dir(self):
                """Return the path to the directory that contains CA
                certificates."""
                if self.__cadir is None:
                        cadir = os.path.join(os.path.sep, "usr", "share",
                            "pkg", "cacert")
                        if os.path.exists(cadir):
                                self.__cadir = cadir
                                return cadir
                        else:
                                self.__cadir = ""

                if self.__cadir == "":
                        return None

                return self.__cadir

        def get_catalog(self, pub, ts=None, ccancel=None):
                """Get the catalog for the specified publisher.  If
                ts is defined, request only changes newer than timestamp
                ts."""

                self.__lock.acquire()
                try:
                        self._get_catalog(pub, ts, ccancel=ccancel)
                finally:
                        self.__lock.release()

        def _get_catalog(self, pub, ts=None, ccancel=None):
                """Get catalog.  This is the implementation of get_catalog,
                a wrapper for this function."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))
                croot = pub.catalog_root

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):

                        repostats = self.stats[d.get_url()]

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:

                                resp = d.get_catalog(ts, header,
                                    ccancel=ccancel)

                                updatelog.recv(resp, croot, ts, pub)

                                return

                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(ex.failures)
                        except tx.TransportProtoError, e:
                                if e.code == httplib.NOT_MODIFIED:
                                        return
                                elif e.retryable:
                                        failures.append(e)
                                else:
                                        raise
                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise
                        except pkg.fmri.IllegalFmri, e:
                                repostats.record_error()
                                raise tx.TransportOperationError(
                                    "Could not retrieve catalog from '%s'\n"
                                    " Unable to parse FMRI. Details follow:\n%s"
                                    % (pub.prefix, e))
                        except EnvironmentError, e:
                                repostats.record_error()
                                raise tx.TransportOperationError(
                                    "Could not retrieve catalog from '%s'\n"
                                    " Exception: str:%s repr:%r" % (pub.prefix,
                                    e, e))
                 
                raise failures

        @staticmethod
        def _verify_catalog(filename, dirname):
                """A wrapper for catalog.verify() that catches
                BadCatalogSignatures exceptions and translates them to
                the appropriate InvalidContentException that the transport
                uses for content verification."""

                filepath = os.path.join(dirname, filename)

                try:
                        catalog.verify(filepath)
                except (apx.BadCatalogSignatures, apx.InvalidCatalogFile), e:
                        os.remove(filepath)
                        te = tx.InvalidContentException(filepath,
                            "CatalogPart failed validation: %s" % e)
                        te.request = filename
                        raise te
                return

        def get_catalog1(self, pub, flist, ts=None, path=None,
            progtrack=None, ccancel=None):
                """Get the catalog1 files from publisher 'pub' that
                are given as a list in 'flist'.  If the caller supplies
                an optional timestamp argument, only get the files that
                have been modified since the timestamp.  At the moment,
                this interface only supports supplying a timestamp
                if the length of flist is 1.

                The timestamp, 'ts', should be provided as a floating
                point value of seconds since the epoch in UTC.  If callers
                have a datetime object, they should use something like:

                time.mktime(dtobj.timetuple()) -> float

                If the caller has a UTC datetime object, the following
                should be used instead:

                calendar.timegm(dtobj.utctimetuple()) -> float

                The examples above convert the object to the appropriate format
                for get_catalog1.

                If the caller wants the completed download to be placed
                in an alternate directory (pub.catalog_root is standard),
                set a directory path in 'path'."""

                self.__lock.acquire()
                try:
                        self._get_catalog1(pub, flist, ts=ts, path=path,
                            progtrack=progtrack, ccancel=ccancel)
                finally:
                        self.__lock.release()

        def _get_catalog1(self, pub, flist, ts=None, path=None,
            progtrack=None, ccancel=None):
                """This is the implementation of get_catalog1.  The
                other function is a wrapper for this one."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = []
                repo_found = False
                header = self.__build_header(uuid=self.__get_uuid(pub))

                if progtrack and ccancel:
                        progtrack.check_cancelation = ccancel

                # Ensure that caller only passed one item, if ts was
                # used.
                if ts and len(flist) > 1:
                        raise ValueError("Ts may only be used with a single"
                            " item flist.")

                # download_dir is temporary download path.  Completed_dir
                # is the cache where valid content lives.
                if path:
                        completed_dir = path
                else:
                        completed_dir = pub.catalog_root
                download_dir = self.__img.incoming_download_dir()

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                # Check if the download_dir exists.  If it doesn't, create
                # the directories.
                self._makedirs(download_dir)
                self._makedirs(completed_dir)

                # Call statvfs to find the blocksize of download_dir's
                # filesystem.
                try:
                        destvfs = os.statvfs(download_dir)
                        # Set the file buffer size to the blocksize of our
                        # filesystem.
                        self.__engine.set_file_bufsz(destvfs[statvfs.F_BSIZE])
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        else:
                                raise tx.TransportOperationError(
                                    "Unable to stat VFS: %s" % e)
                except AttributeError, e:
                        # os.statvfs is not available on Windows
                        pass

                for d in self.__gen_origins_byversion(pub, retry_count,
                    "catalog", 1, ccancel=ccancel):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]
                        repo_found = True
                        gave_up = False

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to supress a permanent failure.
                        try:
                                errlist = d.get_catalog1(flist, download_dir,
                                    header, ts, progtrack=progtrack)
                        except tx.TransportProtoError, e:
                                # If we've performed a conditional
                                # request, and it returned 304, raise a
                                # CatalogNotModified exception here.
                                if e.code == httplib.NOT_MODIFIED:
                                        raise apx.CatalogNotModified(e.url)
                                else:
                                        raise
                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that the client just gave up, make a note
                                # of this condition and try another host.
                                gave_up = True
                                errlist = ex.failures
                                success = ex.success

                        for e in errlist:
                                # General case: Fish the request information
                                # out of the exception, so the transport
                                # can retry the request at another host.
                                req = getattr(e, "request", None)
                                if req:
                                        failedreqs.append(req)
                                        failures.append(e)
                                else:
                                        raise e


                        if gave_up:
                                # If the transport gave up due to excessive
                                # consecutive errors, the caller is returned a
                                # list of successful requests, and a list of
                                # failures.  We need to consider the requests
                                # that were not attempted because we gave up
                                # early.  In this situation, they're failed
                                # requests, even though no exception was
                                # returned.  Filter the flist to remove the
                                # successful requests.  Everything else failed.
                                failedreqs = [
                                    x for x in flist
                                    if x not in success
                                ]
                                flist = failedreqs
                        elif failedreqs:
                                success = [
                                    x for x in flist
                                    if x not in failedreqs
                                ]
                                flist = failedreqs
                        else:
                                success = flist
                                flist = None

                        for s in success:
                                dl_path = os.path.join(download_dir, s)

                                try:
                                        self._verify_catalog(s, download_dir)
                                except tx.InvalidContentException, e:
                                        repostats.record_error()
                                        failedreqs.append(e.request)
                                        failures.append(e)
                                        if not flist:
                                                flist = failedreqs
                                        continue

                                final_path = os.path.normpath(
                                    os.path.join(completed_dir, s))
                                    
                                finaldir = os.path.dirname(final_path)

                                self._makedirs(finaldir)
                                portable.rename(dl_path, final_path)

                        # Return if everything was successful
                        if not flist and not errlist:
                                return

                if not repo_found:
                        raise apx.UnsupportedRepositoryOperation(pub,
                            "catalog/1")

                if failedreqs and failures:
                        failures = [
                            x for x in failures
                            if x.request in failedreqs
                        ]
                        tfailurex = tx.TransportFailures()
                        for f in failures:
                                tfailurex.append(f)
                        raise tfailurex

        def get_publisherinfo(self, pub, ccancel=None):
                """Given a publisher pub, return the publisher/0
                information in a StringIO object.""" 

                self.__lock.acquire()
                try:
                        publisher_info = self._get_publisherinfo(pub,
                            ccancel=ccancel)
                finally:
                        self.__lock.release()

                return publisher_info

        def _get_publisherinfo(self, pub, ccancel=None):
                """Implementation of get_publisherinfo.  This routine
                implements the method, the other is an external interface
                and lock wrapper."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                for d in self.__gen_origins_byversion(pub, retry_count,
                    "publisher", 0, ccancel=ccancel):

                        try:
                                resp = d.get_publisherinfo(header,
                                    ccancel=ccancel)

                                infostr = resp.read()
                                s = cStringIO.StringIO(infostr)
                                return s

                        except tx.ExcessiveTransientFailure, e:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(e.failures)

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise
                raise failures

        def get_content(self, fmri, fhash, ccancel=None):
                """Given a fmri and fhash, return the uncompressed content
                from the remote object.  This is similar to get_datstream,
                except that the transport handles retrieving and decompressing
                the content."""
               
                self.__lock.acquire()
                try:
                        content = self._get_content(fmri, fhash,
                            ccancel=ccancel)
                finally:
                        self.__lock.release()

                return content

        def _get_content(self, fmri, fhash, ccancel=None):
                """This is the function that implements get_content.
                The other function is a wrapper for this one, which handles
                the transport locking correctly."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                pub_prefix = fmri.get_publisher()
                pub = self.__img.get_publisher(pub_prefix)
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                for d in self.__gen_repos(pub, retry_count):

                        url = d.get_url()

                        try:
                                resp = d.get_datastream(fhash, header,
                                    ccancel=ccancel)
                                s = cStringIO.StringIO()
                                hash_val = misc.gunzip_from_stream(resp, s)
                                content = s.getvalue()
                                s.close()

                                return content

                        except tx.ExcessiveTransientFailure, e:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(e.failures)

                        except zlib.error, e:
                                exc = tx.TransferContentException(url,
                                    "zlib.error:%s" %
                                    (" ".join([str(a) for a in e.args])))
                                if exc.retryable:
                                        failures.append(exc)
                                else:
                                        raise exc

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise
                raise failures

        def touch_manifest(self, fmri, intent=None, ccancel=None):
                """Touch a manifest.  This operation does not
                return the manifest's content.  The FMRI is given
                as fmri.  An optional intent string may be supplied
                as intent."""

                self.__lock.acquire()
                try:
                        self._touch_manifest(fmri, intent, ccancel=ccancel)
                finally:
                        self.__lock.release()

        def _touch_manifest(self, fmri, intent=None, ccancel=None):
                """Implementation of touch_manifest, which is a wrapper
                around this function."""

                failures = tx.TransportFailures()
                pub_prefix = fmri.get_publisher()
                pub = self.__img.get_publisher(pub_prefix)
                mfst = fmri.get_url_path()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(intent=intent,
                    uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                for d in self.__gen_origins(pub, retry_count):

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:
                                d.touch_manifest(mfst, header, ccancel=ccancel)
                                return

                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(ex.failures)

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise

                raise failures

        def get_manifest(self, fmri, excludes=misc.EmptyI, intent=None,
            ccancel=None):
                """Given a fmri, and optional excludes, return a manifest
                object."""

                self.__lock.acquire()
                try:
                        m = self._get_manifest(fmri, excludes, intent,
                            ccancel=ccancel)
                finally:
                        self.__lock.release()

                return m

        def _get_manifest(self, fmri, excludes=misc.EmptyI, intent=None,
            ccancel=None):
                """This is the implementation of get_manifest.  The
                get_manifest function wraps this."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                pub_prefix = fmri.get_publisher()
                pub = self.__img.get_publisher(pub_prefix)
                mfst = fmri.get_url_path()
                download_dir = self.__img.incoming_download_dir()
                mcontent = None
                header = self.__build_header(intent=intent,
                    uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                # Check if the download_dir exists.  If it doesn't create
                # the directories.
                self._makedirs(download_dir)

                for d in self.__gen_origins(pub, retry_count):

                        repostats = self.stats[d.get_url()]

                        try:
                                resp = d.get_manifest(mfst, header,
                                    ccancel=ccancel)
                                mcontent = resp.read()

                                self._verify_manifest(fmri, content=mcontent)

                                m = manifest.CachedManifest(fmri,
                                    self.__img.pkgdir,
                                    self.__img.cfg_cache.preferred_publisher,
                                    excludes, mcontent)

                                return m

                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(ex.failures)
                                mcontent = None

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                        mcontent = None
                                else:
                                        raise
 
                        except ActionError, e:
                                repostats.record_error(content=True)
                                te = tx.TransferContentException(
                                    d.get_url(), reason=str(e))
                                failures.append(te)

                raise failures

        def prefetch_manifests(self, fetchlist, excludes=misc.EmptyI,
            progtrack=None, ccancel=None):
                """Given a list of tuples [(fmri, intent), ...], prefetch
                the manifests specified by the fmris in argument
                fetchlist.  Caller may supply a progress tracker in
                'progtrack' as well as the check-cancellation callback in
                'ccancel.'

                This method will not return transient transport errors,
                but it should raise any that would cause an immediate
                failure."""

                if not fetchlist:
                        return

                self.__lock.acquire()
                try:
                        try:
                                self._prefetch_manifests(fetchlist, excludes,
                                    progtrack, ccancel=ccancel)
                        except (apx.PermissionsException, 
                            apx.InvalidDepotResponseException):
                                pass             
                finally:
                        self.__lock.release()


        def _prefetch_manifests(self, fetchlist, excludes=misc.EmptyI,
            progtrack=None, ccancel=None):
                """This is the implementation of prefetch_manifests.
                The other function is a wrapper for this one."""

                download_dir = self.__img.incoming_download_dir()

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                # Check if the download_dir exists.  If it doesn't create
                # the directories.
                self._makedirs(download_dir)

                # Call statvfs to find the blocksize of download_dir's
                # filesystem.
                try:
                        destvfs = os.statvfs(download_dir)
                        # set the file buffer size to the blocksize of
                        # our filesystem
                        self.__engine.set_file_bufsz(destvfs[statvfs.F_BSIZE])
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        else:
                                raise tx.TransportOperationError(
                                    "Unable to stat VFS: %s" % e)
                except AttributeError, e:
                        # os.statvfs is not available on Windows
                        pass

                # Walk the tuples in fetchlist and create a MultiXfr
                # instance for each publisher's worth of requests that
                # this routine must process.
                mx_pub = {}
                for fmri, intent in fetchlist:
                        pub_prefix = fmri.get_publisher()
                        pub = self.__img.get_publisher(pub_prefix)
                        mfst = fmri.get_url_path()
                        header = self.__build_header(intent=intent,
                            uuid=self.__get_uuid(pub))
                        if pub_prefix not in mx_pub:
                                mx_pub[pub_prefix] = MultiXfr(pub,
                                    progtrack=progtrack,
                                    ccancel=ccancel)
                        # Add requests keyed by requested manifest
                        # name.  Value contains (header, fmri) tuple.
                        mx_pub[pub_prefix].add_hash(
                            mfst, (header, fmri))

                for mxfr in mx_pub.values():
                        namelist = [k for k in mxfr]
                        while namelist:
                                chunksz = self.__chunk_size(pub,
                                    origin_only=True)
                                mfstlist = [
                                    (n, mxfr[n][0])
                                    for n in namelist[:chunksz]
                                ]
                                del namelist[:chunksz]

                                self._prefetch_manifests_list(mxfr, mfstlist,
                                    excludes)

        def _prefetch_manifests_list(self, mxfr, mlist, excludes=misc.EmptyI):
                """Perform bulk manifest prefetch.  This is the routine
                that downloads initiates the downloads in chunks
                determined by its caller _prefetch_manifests.  The mxfr
                argument should be a MultiXfr object, and mlist
                should be a list of tuples (manifestname, header)."""

                # Don't perform multiple retries, since we're just prefetching.
                retry_count = 1
                mfstlist = mlist
                pub = mxfr.get_publisher()
                progtrack = mxfr.get_progtrack()

                # download_dir is temporary download path.
                download_dir = self.__img.incoming_download_dir()

                for d in self.__gen_origins(pub, retry_count):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]
                        gave_up = False

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to suppress a permanant failure.
                        try:
                                errlist = d.get_manifests(mfstlist,
                                    download_dir, progtrack=progtrack)
                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, record this for later
                                # and try a different host.
                                gave_up = True
                                errlist = ex.failures
                                success = ex.success

                        for e in errlist:
                                req = getattr(e, "request", None)
                                if req:
                                        failedreqs.append(req)
                                else:
                                        raise e

                        if gave_up:
                                # If the transport gave up due to excessive
                                # consecutive errors, the caller is returned a
                                # list of successful requests, and a list of
                                # failures.  We need to consider the requests
                                # that were not attempted because we gave up
                                # early.  In this situation, they're failed
                                # requests, even though no exception was
                                # returned.  Filter the flist to remove the
                                # successful requests.  Everything else failed.
                                failedreqs = [
                                    x[0] for x in mfstlist
                                    if x[0] not in success
                                ]
                        elif failedreqs:
                                success = [
                                    x[0] for x in mfstlist
                                    if x[0] not in failedreqs
                                ]
                        else:
                                success = [ x[0] for x in mfstlist ]
                                mfstlist = None

                        for s in success:

                                dl_path = os.path.join(download_dir, s)

                                try:
                                        # Verify manifest content.
                                        fmri = mxfr[s][1]
                                        self._verify_manifest(fmri, dl_path)
                                except tx.InvalidContentException, e:
                                        e.request = s
                                        repostats.record_error(content=True)
                                        failedreqs.append(s)
                                        continue

                                pref_pub = \
                                    self.__img.cfg_cache.preferred_publisher

                                try:
                                        mf = file(dl_path)
                                        mcontent = mf.read()
                                        mf.close()
                                        m = manifest.CachedManifest(fmri,
                                            self.__img.pkgdir, pref_pub,
                                            excludes, mcontent)
                                except ActionError, e:
                                        repostats.record_error(content=True)
                                        failedreqs.append(s)
                                        os.remove(dl_path)
                                        continue
        
                                os.remove(dl_path)
                                progtrack.evaluate_progress(fmri)
                                mxfr.del_hash(s)

                        # Return if everything was successful
                        if not mfstlist and not failedreqs:
                                return
                        elif failedreqs:
                                # Generate mfstlist here, which included any
                                # reqs that failed during verification.
                                mfstlist = [
                                    (x,y) for x,y in mfstlist
                                    if x in failedreqs
                                ]
 
        def _verify_manifest(self, fmri, mfstpath=None, content=None):
                """Verify a manifest.  The caller must supply the FMRI
                for the package in 'fmri', as well as the path to the
                manifest file that will be verified.  If signature information
                is not present, this routine returns False.  If signature
                information is present, and the manifest verifies, this
                method returns true.  If the manifest fails to verify,
                this function throws an InvalidContentException.

                The caller may either specify a pathname to a file that
                contains the manifest in 'mfstpath' or a string that contains
                the manifest content in 'content'.  One of these arguments
                must be used."""

                # Get publisher information from FMRI.
                pub = self.__img.get_publisher(fmri.get_publisher())
                # Use the publisher to get the catalog and its signature info.
                try:
                        sigs = dict(pub.catalog.get_entry_signatures(fmri))
                except apx.UnknownCatalogEntry:
                        return False

                if sigs and "sha-1" in sigs:
                        chash = sigs["sha-1"]
                else:
                        return False

                if mfstpath:
                        mf = file(mfstpath)
                        mcontent = mf.read()
                        mf.close()
                elif content:
                        mcontent = content
                else:
                        raise ValueError("Caller must supply either mfstpath "
                            "or content arguments.")

                newhash = manifest.Manifest.hash_create(mcontent)
                if chash != newhash:
                        if mfstpath:
                                sz = os.stat(mfstpath).st_size
                                os.remove(mfstpath)
                        else:
                                sz = None
                        raise tx.InvalidContentException(mfstpath,
                            "manifest hash failure: fmri: %s \n"
                            "expected: %s computed: %s" % 
                            (fmri, chash, newhash), size=sz)

                return True

        @staticmethod
        def __build_header(intent=None, uuid=None):
                """Return a dictionary that contains various
                header fields, depending upon what arguments
                were passed to the function.  Supply intent header in intent
                argument, uuid information in uuid argument."""

                header = {}

                if intent:
                        header["X-IPkg-Intent"] = intent

                if uuid:
                        header["X-IPkg-UUID"] = uuid

                if not header:
                        return None

                return header

        def __get_uuid(self, pub):
                if not self.__img.cfg_cache.get_policy(imageconfig.SEND_UUID):
                        return None

                try:
                        return pub.client_uuid
                except KeyError:
                        return None

        @staticmethod
        def _makedirs(newdir):
                """A helper function for _get_files that makes directories,
                if needed."""

                if not os.path.exists(newdir):
                        try:
                                os.makedirs(newdir)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise apx.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise apx.ReadOnlyFileSystemException(
                                            e.filename)
                                raise tx.TransportOperationError("Unable to "
                                    "make directory: %s" % e)

        def _get_files_list(self, mfile, flist):
                """Download the files given in argument 'flist'.  This
                allows us to break up download operations into multiple
                chunks.  Since we re-evaluate our host selection after
                each chunk, this gives us a better way of reacting to
                changing conditions in the network."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = []
                filelist = flist
                pub = mfile.get_publisher()
                progtrack = mfile.get_progtrack()
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # download_dir is temporary download path.
                download_dir = self.__img.incoming_download_dir()

                for d in self.__gen_repos(pub, retry_count):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]
                        gave_up = False

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to supress a permanant failure.
                        try:
                                errlist = d.get_files(filelist, download_dir,
                                    progtrack, header)
                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, record this for later
                                # and try a different host.
                                gave_up = True
                                errlist = ex.failures
                                success = ex.success

                        for e in errlist:
                                req = getattr(e, "request", None)
                                if req:
                                        failedreqs.append(req)
                                        failures.append(e)
                                else:
                                        raise e

                        if gave_up:
                                # If the transport gave up due to excessive
                                # consecutive errors, the caller is returned a
                                # list of successful requests, and a list of
                                # failures.  We need to consider the requests
                                # that were not attempted because we gave up
                                # early.  In this situation, they're failed
                                # requests, even though no exception was
                                # returned.  Filter the flist to remove the
                                # successful requests.  Everything else failed.
                                failedreqs = [
                                    x for x in filelist
                                    if x not in success
                                ]
                                filelist = failedreqs
                        elif failedreqs:
                                success = [
                                    x for x in filelist
                                    if x not in failedreqs
                                ]
                                filelist = failedreqs
                        else:
                                success = filelist
                                filelist = None

                        for s in success:

                                dl_path = os.path.join(download_dir, s)

                                try:
                                        self._verify_content(mfile[s][0],
                                            dl_path)
                                except tx.InvalidContentException, e:
                                        mfile.subtract_progress(e.size)
                                        e.request = s
                                        repostats.record_error(content=True)
                                        failedreqs.append(s)
                                        failures.append(e)
                                        if not filelist:
                                                filelist = failedreqs
                                        continue

                                try:
                                        self.cache_store.insert(s, dl_path)
                                except file_manager.FMPermissionsException, e:
                                        raise apx.PermissionsException(
                                            e.filename)
                                mfile.make_openers(s)
                                mfile.del_hash(s)

                        # Return if everything was successful
                        if not filelist and not errlist:
                                return

                if failedreqs and failures:
                        failures = [
                            x for x in failures
                            if x.request in failedreqs
                        ]
                        tfailurex = tx.TransportFailures()
                        for f in failures:
                                tfailurex.append(f)
                        raise tfailurex

        def _get_files_impl(self, mfile):
                """The implementation of _get_files.  The _get_files
                function is a wrapper around this function, mainly for
                locking purposes."""

                download_dir = self.__img.incoming_download_dir()
                pub = mfile.get_publisher()

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                # Check if the download_dir exists.  If it doesn't create
                # the directories.
                self._makedirs(download_dir)

                # Call statvfs to find the blocksize of download_dir's
                # filesystem.
                try:
                        destvfs = os.statvfs(download_dir)
                        # set the file buffer size to the blocksize of
                        # our filesystem
                        self.__engine.set_file_bufsz(destvfs[statvfs.F_BSIZE])
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        else:
                                raise tx.TransportOperationError(
                                    "Unable to stat VFS: %s" % e)
                except AttributeError, e:
                        # os.statvfs is not available on Windows
                        pass

                while mfile:

                        filelist = []
                        chunksz = self.__chunk_size(pub)

                        for i, v in enumerate(mfile):
                                if i >= chunksz:
                                        break
                                filelist.append(v)

                        self._get_files_list(mfile, filelist)

        def _get_files(self, mfile):
                """Perform an operation that gets multiple files at once.
                A mfile object contains information about the multiple-file
                request that will be performed."""

                self.__lock.acquire()
                try:
                        self._get_files_impl(mfile)
                finally:
                        self.__lock.release()

        def get_versions(self, pub, ccancel=None):
                """Query the publisher's origin servers for versions
                information.  Return a dictionary of "name":"versions" """

                self.__lock.acquire()
                try:
                        v = self._get_versions(pub, ccancel=ccancel)
                finally:
                        self.__lock.release()

                return v

        def _get_versions(self, pub, ccancel=None):
                """Implementation of get_versions"""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):
                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:
                                vers = self.__get_version(d, header,
                                    ccancel=ccancel)
                                # Save this information for later use, too.
                                self.__populate_repo_versions(d, vers)
                                return vers 
                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                for f in ex.failures:
                                        f.url = d.get_url()
                                        failures.append(f)
                        except tx.TransportException, e:
                                e.url = d.get_url()
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise
                        except ValueError:
                                raise apx.InvalidDepotResponseException(
                                    d.get_url(), "Unable to parse server "
                                    "response")
                raise failures

        @staticmethod
        def __get_version(repo, header=None, ccancel=None):
                """An internal method that returns a versions dictionary
                given a transport repo object."""

                resp = repo.get_versions(header, ccancel=ccancel)
                verlines = resp.readlines()

                return dict(
                    s.split(None, 1)
                    for s in (l.strip() for l in verlines)
                )

        def __populate_repo_versions(self, repo, vers=None, ccancel=None):
                """Download versions information for the transport
                repository object and store that information inside
                of it."""

                # Call __get_version to get the version dictionary
                # from the repo.
                
                if not vers:
                        try:
                                vers = self.__get_version(repo, ccancel=ccancel)
                        except ValueError:
                                raise tx.PkgProtoError(repo.get_url(),
                                    "versions", 0,
                                    "VaueError while parsing response")

                for key, val in vers.items():
                        # Don't turn this line into a list of versions.
                        if key == "pkg-server":
                                continue

                        try:
                                versids = [
                                    int(v)
                                    for v in val.split()
                                ]
                        except ValueError:
                                raise tx.PkgProtoError(repo.get_url(),
                                    "versions", 0,
                                    "Unable to parse version ids.")

                        # Insert the list back into the dictionary.
                        vers[key] = versids

                repo.add_version_data(vers)

        def __gen_origins(self, pub, count):
                """The pub argument may either be a Publisher or a
                RepositoryURI object."""

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                if isinstance(pub, publisher.Publisher):
                        origins = pub.selected_repository.origins
                else:
                        # If search was invoked with -s option, we'll have
                        # a RepoURI instead of a publisher.  Convert
                        # this to a repo uri
                        origins = [pub]

                for i in xrange(count):
                        rslist = self.stats.get_repostats(origins, origins)
                        for rs, ruri in rslist:
                                yield self.__repo_cache.new_repo(rs, ruri)

        def __gen_origins_byversion(self, pub, count, operation, version,
            ccancel=None):
                """Return origin repos for publisher pub, that support
                the operation specified as a string in the 'operation'
                argument.  The operation must support the version
                given in as an integer to the 'version' argument."""

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                if isinstance(pub, publisher.Publisher):
                        origins = pub.selected_repository.origins
                else:
                        # If search was invoked with -s option, we'll have
                        # a RepoURI instead of a publisher.  Convert
                        # this to a repo uri
                        origins = [pub]

                for i in xrange(count):
                        rslist = self.stats.get_repostats(origins)
                        for rs, ruri in rslist:
                                repo = self.__repo_cache.new_repo(rs, ruri)
                                if not repo.has_version_data():
                                        try:
                                                self.__populate_repo_versions(
                                                    repo, ccancel=ccancel)
                                        except tx.TransportException:
                                                continue

                                if repo.supports_version(operation, version):
                                        yield repo

        def __gen_repos(self, pub, count):
                """Generate a list of all repositories for a given publisher.
                This is used for content operations, whereas __gen_origins
                or __gen_origins_byversion should be used for metadata
                operations."""

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                for i in xrange(count):
                        repo = pub.selected_repository
                        repolist = repo.mirrors[:]
                        repolist.extend(repo.origins)
                        rslist = self.stats.get_repostats(repolist,
                            repo.origins)
                        for rs, ruri in rslist:
                                yield self.__repo_cache.new_repo(rs, ruri)

        def __chunk_size(self, pub, origin_only=False):
                """Determine the chunk size based upon how many of the known
                mirrors have been visited.  If not all mirrors have been
                visited, choose a small size so that if it ends up being
                a poor choice, the client doesn't transfer too much data."""

                CHUNK_SMALL = 10
                CHUNK_LARGE = 100

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                repo = pub.selected_repository
                if origin_only:
                        repolist = repo.origins[:]
                else:
                        repolist = repo.mirrors[:]
                        repolist.extend(repo.origins)

                n = len(repolist)
                m = self.stats.get_num_visited(repolist)
                if m < n:
                        return CHUNK_SMALL
                return CHUNK_LARGE

        def valid_publisher_test(self, pub, ccancel=None):
                """Test that the publisher supplied in pub actually
                points to a valid packaging server."""

                self.__lock.acquire()
                try:
                        val = self._valid_publisher_test(pub)
                finally:
                        self.__lock.release()

                return val

        def _valid_publisher_test(self, pub, ccancel=None):
                """Implementation of valid_publisher_test."""

                try:
                        vd = self._get_versions(pub, ccancel=ccancel)
                except tx.TransportException, e:
                        # Failure when contacting server.  Report
                        # this as an error.  Attempt to report
                        # the specific origin that failed, and
                        # if not available, fallback to the
                        # first one for the publisher.
                        url = getattr(e, "url", pub["origin"])
                        raise apx.InvalidDepotResponseException(url,
                            "Transport errors encountered when trying to "
                            "contact depot server.\nReported the following "
                            "errors:\n%s" % e)

                if not self._valid_versions_test(vd):
                        url = pub["origin"]
                        raise apx.InvalidDepotResponseException(url,
                            "Invalid or unparseable version information.")

                return True

        def captive_portal_test(self, ccancel=None):
                """A captive portal forces a HTTP client on a network
                to see a special web page, usually for authentication
                purposes.  (http://en.wikipedia.org/wiki/Captive_portal)."""

                self.__lock.acquire()
                try:
                        self._captive_portal_test(ccancel=ccancel)
                finally:
                        self.__lock.release()

        def _captive_portal_test(self, ccancel=None):
                """Implementation of captive_portal_test."""

                if self.__portal_test_executed:
                        return

                self.__portal_test_executed = True
                vd = None

                for pub in self.__img.gen_publishers():
                        try:
                                vd = self._get_versions(pub, ccancel=ccancel)
                        except tx.TransportException:
                                # Encountered a transport error while
                                # trying to contact this publisher.
                                # Pick another publisher instead.
                                continue
                        except apx.CanceledException:
                                self.__portal_test_executed = False
                                raise

                        if self._valid_versions_test(vd):
                                return
                        else:
                                continue

                if not vd:
                        # We got all the way through the list of publishers but
                        # encountered transport errors in every case.  This is
                        # likely a network configuration problem.  Report our
                        # inability to contact a server.
                        raise apx.InvalidDepotResponseException(None,
                            "Unable to contact any configured publishers. "
                            "This is likely a network configuration problem.")

        @staticmethod
        def _valid_versions_test(versdict):
                """Check that the versions information contained in
                versdict contains valid version specifications.

                In order to test for this condition, pick a publisher
                from the list of active publishers.  Check to see if
                we can connect to it.  If so, test to see if it supports
                the versions/0 operation.  If versions/0 is not found,
                we get an unparseable response, or the response does
                not contain pkg-server, or versions 0 then we're not
                talking to a depot.  Return an error in these cases."""

                if "pkg-server" in versdict:
                        # success!
                        return True
                elif "versions" in versdict:
                        try:
                                versids = [
                                    int(v)
                                    for v in versdict["versions"]
                                ]
                        except ValueError:
                                # Unable to determine version number.  Fail.
                                return False

                        if 0 not in versids:
                                # Paranoia.  Version 0 should be in the
                                # output for versions/0.  If we're here,
                                # something has gone very wrong.  EPIC FAIL!
                                return False

                        # Found versions/0, success!
                        return True

                # Some other error encountered. Fail.
                return False

        def multi_file(self, fmri, progtrack, ccancel):
                """Creates a MultiFile object for this transport.
                The caller may add actions to the multifile object
                and wait for the download to complete."""

                if not fmri:
                        return None

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()
                
                publisher = self.__img.get_publisher(fmri.get_publisher())
                mfile = MultiFile(publisher, self, progtrack, ccancel)

                return mfile

        def _action_cached(self, action):
                """If a file with the name action.hash is cached,
                and if it has the same content hash as action.chash,
                then return the path to the file.  If the file can't
                be found, return None."""

                hashval = action.hash

                cache_path = self.cache_store.lookup(hashval)

                try:
                        if cache_path:
                                self._verify_content(action, cache_path)
                                return cache_path
                except tx.InvalidContentException:
                        # If the content in the cache doesn't match the hash of
                        # the action, verify will have already purged the item
                        # from the cache. 
                        pass

                return None

        @staticmethod
        def _verify_content(action, filepath):
                """If action contains an attribute that has the compressed
                hash, read the file specified in filepath and verify
                that the hash values match.  If the values do not match,
                remove the file and raise an InvalidContentException."""

                chash = action.attrs.get("chash", None)
                path = action.attrs.get("path", None)
                if not chash:
                        # Compressed hash doesn't exist.  Decompress and
                        # generate hash of uncompressed content.
                        ifile = open(filepath, "rb")
                        ofile = open(os.devnull, "wb")

                        try:
                                fhash = misc.gunzip_from_stream(ifile, ofile)
                        except zlib.error, e:
                                s = os.stat(filepath)
                                os.remove(filepath)
                                raise tx.InvalidContentException(path,
                                    "zlib.error:%s" %
                                    (" ".join([str(a) for a in e.args])),
                                    size=s.st_size)

                        ifile.close()
                        ofile.close()

                        if action.hash != fhash:
                                s = os.stat(filepath)
                                os.remove(filepath)
                                raise tx.InvalidContentException(action.path,
                                    "hash failure:  expected: %s"
                                    "computed: %s" % (action.hash, fhash),
                                    size=s.st_size)
                        return

                newhash = misc.get_data_digest(filepath)[0]
                if chash != newhash:
                        s = os.stat(filepath)
                        os.remove(filepath)
                        raise tx.InvalidContentException(path,
                            "chash failure: expected: %s computed: %s" % \
                            (chash, newhash), size=s.st_size)

class MultiXfr(object):
        """A transport object for performing multiple simultaneous
        requests.  This object matches publisher to list of requests, and
        allows the caller to associate a piece of data with the request key."""

        def __init__(self, pub, progtrack=None, ccancel=None):
                """Supply the publisher as argument 'pub'."""

                self._publisher = pub
                self._hash = {}
                self._progtrack = progtrack
                # Add the check_cancelation to the progress tracker
                if progtrack and ccancel:
                        self._progtrack.check_cancelation = ccancel

        def __contains__(self, key):
                return key in self._hash

        def __getitem__(self, key):
                return self._hash[key]

        def __iter__(self):
                for k in self._hash:
                        yield k

        def __len__(self):
                return len(self._hash)

        def __nonzero__(self):
                return bool(self._hash)

        def add_hash(self, hashval, item):
                """Add 'item' to list of values that exist for
                hash value 'hashval'."""

                self._hash[hashval] = item

        def del_hash(self, hashval):
                """Remove the hashval from the dictionary, if it exists."""

                self._hash.pop(hashval, None)

        def get_progtrack(self):
                """Return the progress tracker object for this MFile,
                if it has one."""

                return self._progtrack

        def get_publisher(self):
                """Return the publisher object that will be used
                for this MultiFile request."""

                return self._publisher

        def keys(self):
                """Return a list of the keys in the hash."""

                return self._hash.keys()


class MultiFile(MultiXfr):
        """A transport object for performing multi-file requests
        using pkg actions.  This takes care of matching the publisher
        with the actions, and performs the download and content
        verification necessary to assure correct content installation."""

        def __init__(self, pub, xport, progtrack, ccancel):
                """Supply the destination publisher in the pub argument.
                The transport object should be passed in xport."""

                MultiXfr.__init__(self, pub, progtrack=progtrack,
                    ccancel=ccancel)

                self._transport = xport

        def add_action(self, action):
                """The multiple file retrieval operation is asynchronous.
                Add files to retrieve with this function.  Supply the
                publisher in pub and the list of files in filelist.
                Wait for the operation by calling waitFiles."""

                cachedpath = self._transport._action_cached(action)
                if cachedpath:
                        action.data = self._make_opener(cachedpath,
                            self._transport.cache_store)
                        filesz = int(misc.get_pkg_otw_size(action))
                        self._progtrack.download_add_progress(1, filesz)
                        return

                hashval = action.hash

                self.add_hash(hashval, action)

        def add_hash(self, hashval, item):
                """Add 'item' to list of values that exist for
                hash value 'hashval'."""

                self._hash.setdefault(hashval, []).append(item)

        @staticmethod
        def _make_opener(hashval, cache_store):
                def opener():
                        f = open(cache_store.lookup(hashval), "rb")
                        return f
                return opener                                

        def make_openers(self, hashval):
                """Find each action associated with the hash value hashval.
                Create an opener that points to the file for hashval for the
                action's data method."""

                totalsz = 0
                nactions = 0

                filesz = os.stat(
                    self._transport.cache_store.lookup(hashval)).st_size

                for action in self._hash[hashval]:
                        action.data = self._make_opener(hashval,
                            self._transport.cache_store)
                        nactions += 1
                        totalsz += misc.get_pkg_otw_size(action)

                # The progress tracker accounts for the sizes of all actions
                # even if we only have to perform one download to satisfy
                # multiple actions with the same hashval.  Since we know
                # the size of the file we downloaded, but not necessarily
                # the size of the action responsible for the download,
                # generate the total size and subtract the size that was
                # downloaded.  The downloaded size was already accounted for in
                # the engine's progress tracking.  Adjust the progress tracker
                # by the difference between what we have and the total we should
                # have received.
                bytes = int(totalsz - filesz)
                self._progtrack.download_add_progress((nactions - 1), bytes)

        def subtract_progress(self, size):
                """Subtract the progress accumulated by the download of
                file with hash of hashval.  make_openers accounts for
                hashes with multiple actions.  If this has been invoked,
                it has happened before make_openers, so it's only necessary
                to adjust the progress for a single file."""

                self._progtrack.download_add_progress(-1, int(-size))

        def wait_files(self):
                """Wait for outstanding file retrieval operations to
                complete."""

                if self._hash:
                        self._transport._get_files(self)

