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
import copy
import errno
import httplib
import os
import simplejson as json
import statvfs
import tempfile
import zlib

import pkg.catalog as catalog
import pkg.client.api_errors as apx
import pkg.client.imageconfig as imageconfig
import pkg.client.publisher as publisher
import pkg.client.transport.engine as engine
import pkg.client.transport.exception as tx
import pkg.client.transport.mdetect as mdetect
import pkg.client.transport.repo as trepo
import pkg.client.transport.stats as tstats
import pkg.file_layout.file_manager as fm
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.nrlock as nrlock
import pkg.p5i as p5i
import pkg.p5s as p5s
import pkg.portable as portable
import pkg.server.repository as sr
import pkg.updatelog as updatelog

from pkg.actions import ActionError
from pkg.client import global_settings
logger = global_settings.logger

class TransportCfg(object):
        """Contains configuration needed by the transport for proper
        operations.  Clients must create one of these objects, and then pass
        it to a transport instance when it is initialized.  This is the base
        class.
        """

        def __init__(self):
                self.__caches = {}

                # Used to track if reset_caches() has been called at least
                # once.
                self.__caches_set = False

                self.pkg_pub_map = None
                self.alt_pubs = None

        def add_cache(self, path, pub=None, readonly=True):
                """Adds the directory specified by 'path' as a location to read
                file data from, and optionally to store to for the specified
                publisher. 'path' must be a directory created for use with the
                pkg.file_manager module.  If the cache already exists for the
                specified 'pub', its 'readonly' status will be updated.

                'pub' is an optional publisher prefix to restrict usage of this
                cache to.  If not provided, it is assumed that file data for any
                publisher could be contained within this cache.

                'readonly' is an optional boolean value indicating whether file
                data should be stored here as well.  Only one writeable cache
                can exist for each 'pub' at a time."""

                if not self.__caches_set:
                        self.reset_caches(shared=True)

                if not pub:
                        pub = "__all"

                pub_caches = self.__caches.setdefault(pub, [])

                write_caches = [
                    cache
                    for cache in pub_caches
                    if not cache.readonly
                ]

                # For now, there should be no write caches or a single one.
                assert len(write_caches) <= 1

                path = path.rstrip(os.path.sep)
                for cache in pub_caches:
                        if cache.root != path:
                                continue

                        if readonly:
                                # Nothing more to do.
                                cache.readonly = True
                                return

                        # Ensure no other writeable caches exist for this
                        # publisher.
                        for wr_cache in write_caches:
                                if id(wr_cache) == id(cache):
                                        continue
                                raise tx.TransportOperationError("Only one "
                                    "cache that is writable for all or a "
                                    "specific publisher may exist at a time.")

                        cache.readonly = False
                        break
                else:
                        # Either no caches exist for this publisher, or this is
                        # a new cache.
                        pub_caches.append(fm.FileManager(path, readonly))

        def gen_publishers(self):
                raise NotImplementedError

        def get_caches(self, pub=None, readonly=True):
                """Returns the file_manager cache objects for the specified
                publisher in order of preference.  That is, caches should
                be checked for file content in the order returned.

                'pub' is an optional publisher prefix.  If provided, caches
                designated for use with the given publisher will be returned
                first followed by any caches applicable to all publishers.

                'readonly' is an optional boolean value indicating whether
                a cache for storing file data should be returned.  By default,
                only caches for reading file data are returned."""

                if not self.__caches_set:
                        self.reset_caches(shared=True)

                if isinstance(pub, publisher.Publisher):
                        pub = pub.prefix
                elif not pub or not isinstance(pub, basestring):
                        pub = None

                caches = [
                    cache
                    for cache in self.__caches.get(pub, [])
                    if readonly or not cache.readonly
                ]

                if not readonly and caches:
                        # If a publisher-specific writeable cache has been
                        # found, return it alone.
                        return caches

                # If this is a not a specific publisher case, a readonly case,
                # or no writeable cache exists for the specified publisher,
                # return any publisher-specific ones first and any additional
                # ones after.
                return caches + [
                    cache
                    for cache in self.__caches.get("__all", [])
                    if readonly or not cache.readonly
                ]

        def get_policy(self, policy_name):
                raise NotImplementedError

        def get_property(self, property_name):
                raise NotImplementedError

        def get_pkg_dir(self, pfmri):
                """Returns the absolute path of the directory that should be
                used to store and load manifest data.
                """
                raise NotImplementedError

        def get_pkg_pathname(self, pfmri):
                """Returns the absolute pathname of the file that manifest data
                should be stored in and loaded from.
                """
                raise NotImplementedError

        def get_pkg_alt_repo(self, pfmri):
                """Returns the repository object containing the origins that
                should be used to retrieve the specified package or None.

                'pfmri' is the FMRI object for the package."""

                if not self.pkg_pub_map:
                        return

                # Package data should be retrieved from an alternative location.
                pfx, stem, ver = pfmri.tuple()
                sver = str(ver)
                pmap = self.pkg_pub_map
                try:
                        return pmap[pfx][stem][sver].repository
                except KeyError:
                        # No alternate known for source.
                        return

        def get_publisher(self, publisher_name):
                raise NotImplementedError

        def reset_caches(self, shared=False):
                """Discard any cache information and reconfigure based on
                current publisher configuration data.

                'shared' is an optional boolean value indicating that any
                shared cache information (caches not specific to any publisher)
                should also be discarded.  If True, callers are responsible for
                ensuring a new set of shared cache information is added again.
                """

                # Caches fully set at least once.
                self.__caches_set = True

                for pub in self.__caches.keys():
                        if shared or pub != "__all":
                                # Remove any publisher specific caches so that
                                # the most current publisher information can be
                                # used.
                                del self.__caches[pub]

                # Automatically add any publisher repository origins
                # or mirrors that are filesystem-based as read-only caches.
                for pub in self.gen_publishers():
                        repo = pub.repository
                        if not repo:
                                continue

                        for ruri in repo.origins + repo.mirrors:
                                if ruri.scheme != "file":
                                        continue

                                path = ruri.get_pathname()
                                try:
                                        frepo = sr.Repository(root=path,
                                            read_only=True)
                                        for rstore in frepo.rstores:
                                                if not rstore.file_root:
                                                        continue
                                                if rstore.publisher and \
                                                    rstore.publisher != pub.prefix:
                                                        # If the repository
                                                        # storage object is for
                                                        # a different publisher,
                                                        # skip it.
                                                        continue
                                                self.add_cache(rstore.file_root,
                                                    pub=rstore.publisher,
                                                    readonly=True)
                                except (sr.RepositoryError, apx.ApiException):
                                        # Cache isn't currently valid, so skip
                                        # it for now.  This essentially defers
                                        # any errors that might be encountered
                                        # accessing this repository until
                                        # later when transport attempts to
                                        # retrieve data through the engine.
                                        continue

        incoming_root = property(doc="The absolute pathname of the "
            "directory where in-progress downloads should be stored.")

        pkg_root = property(doc="The absolute pathname of the directory "
            "where manifest files should be stored to and loaded from.")

        user_agent = property(doc="A string that identifies the user agent for "
            "the transport.")


class ImageTransportCfg(TransportCfg):
        """A subclass of TransportCfg that gets its configuration information
        from an Image object.
        """

        def __init__(self, image):
                TransportCfg.__init__(self)
                self.__img = image

        def gen_publishers(self):
                return self.__img.gen_publishers()

        def get_policy(self, policy_name):
                if not self.__img.cfg:
                        return False
                return self.__img.cfg.get_policy(policy_name)

        def get_pkg_dir(self, pfmri):
                """Returns the absolute path of the directory that should be
                used to store and load manifest data.
                """

                return self.__img.get_manifest_dir(pfmri)

        def get_pkg_pathname(self, pfmri):
                """Returns the absolute pathname of the file that the manifest
                should be stored in and loaded from."""

                return self.__img.get_manifest_path(pfmri)

        def get_pkg_alt_repo(self, pfmri):
                """Returns the repository object containing the origins that
                should be used to retrieve the specified package or None.

                'pfmri' is the FMRI object for the package."""

                alt_repo = TransportCfg.get_pkg_alt_repo(self, pfmri)
                if not alt_repo:
                        alt_repo = self.__img.get_pkg_repo(pfmri)
                return alt_repo

        def get_property(self, property_name):
                if not self.__img.cfg:
                        raise KeyError
                return self.__img.get_property(property_name)

        def get_publisher(self, publisher_name):
                return self.__img.get_publisher(publisher_name)

        def reset_caches(self, shared=True):
                """Discard any publisher specific cache information and
                reconfigure based on current publisher configuration data.

                'shared' is ignored and exists only for compatibility with
                the interface defined by TransportCfg.
                """

                # Call base class method to perform initial reset of all
                # cache information.
                TransportCfg.reset_caches(self, shared=True)

                # Then add image-specific cache data after.
                for path, readonly, pub in self.__img.get_cachedirs():
                        self.add_cache(path, pub=pub, readonly=readonly)

        def __get_user_agent(self):
                return misc.user_agent_str(self.__img,
                    global_settings.client_name)

        incoming_root = property(lambda self: self.__img._incoming_cache_dir,
            doc="The absolute pathname of the directory where in-progress "
            "downloads should be stored.")

        user_agent = property(__get_user_agent, doc="A string that identifies "
            "the user agent for the transport.")


class GenericTransportCfg(TransportCfg):
        """A subclass of TransportCfg for use by transport clients that
        do not have an image."""

        def __init__(self, publishers=misc.EmptyI, incoming_root=None,
            pkg_root=None, policy_map=misc.EmptyDict,
            property_map=misc.EmptyDict):

                TransportCfg.__init__(self)
                self.__publishers = {}
                self.__incoming_root = incoming_root
                self.__pkg_root = pkg_root
                self.__policy_map = policy_map
                self.__property_map = property_map

                for p in publishers:
                        self.__publishers[p.prefix] = p

        def add_publisher(self, pub):
                self.__publishers[pub.prefix] = pub

        def gen_publishers(self):
                return (p for p in self.__publishers.values())

        def get_pkg_dir(self, pfmri):
                """Returns the absolute pathname of the directory that should be
                used to store and load manifest data."""

                return os.path.join(self.pkg_root, pfmri.get_dir_path())

        def get_pkg_pathname(self, pfmri):
                """Returns the absolute pathname of the file that manifest data
                should be stored in and loaded from."""

                return os.path.join(self.get_pkg_dir(pfmri), "manifest")

        def get_policy(self, policy_name):
                return self.__policy_map.get(policy_name, False)

        def get_property(self, property_name):
                return self.__property_map[property_name]

        def get_publisher(self, publisher_name):
                pub = self.__publishers.get(publisher_name)
                if not pub:
                        raise apx.UnknownPublisher(publisher_name)
                return pub

        def remove_publisher(self, publisher_name):
                return self.__publishers.pop(publisher_name, None)

        def __get_user_agent(self):
                return misc.user_agent_str(None, global_settings.client_name)

        def __set_inc_root(self, inc_root):
                self.__incoming_root = inc_root

        def __set_pkg_root(self, pkg_root):
                self.__pkg_root = pkg_root

        incoming_root = property(
            lambda self: self.__incoming_root, __set_inc_root,
            doc="Absolute pathname to directory of in-progress downloads.")

        pkg_root = property(lambda self: self.__pkg_root, __set_pkg_root,
            doc="The absolute pathname of the directory where in-progress "
            "downloads should be stored.")

        user_agent = property(__get_user_agent,
            doc="A string that identifies the user agent for the transport.")


class LockedTransport(object):
        """A decorator class that wraps transport functions, calling
        their lock and unlock methods.  Due to implementation differences
        in the decorator protocol, the decorator must be used with
        parenthesis in order for this to function correctly.  Always
        decorate functions @LockedTransport()."""

        def __init__(self, *d_args, **d_kwargs):
                object.__init__(self)

        def __call__(self, f):
                def wrapper(*fargs, **f_kwargs):
                        instance, fargs = fargs[0], fargs[1:]
                        lock = instance._lock
                        lock.acquire()
                        try:
                                return f(instance, *fargs, **f_kwargs)
                        finally:
                                lock.release()
                return wrapper

class Transport(object):
        """The generic transport wrapper object.  Its public methods should
        be used by all client code that wishes to perform file/network
        packaging operations."""

        def __init__(self, tcfg):
                """Initialize the Transport object. Caller must supply
                a TransportCfg object."""

                self.__engine = None
                self.__cadir = None
                self.__portal_test_executed = False
                self.__repo_cache = None
                self.__dynamic_mirrors = []
                self._lock = nrlock.NRLock()
                self.cfg = tcfg
                self.stats = tstats.RepoChooser()

        def __setup(self):
                self.__engine = engine.CurlTransportEngine(self)

                # Configure engine's user agent
                self.__engine.set_user_agent(self.cfg.user_agent)

                self.__repo_cache = trepo.RepoCache(self.__engine)

                if self.cfg.get_policy(imageconfig.MIRROR_DISCOVERY):
                        self.__dynamic_mirrors = mdetect.MirrorDetector()
                        try:
                                self.__dynamic_mirrors.locate()
                        except tx.mDNSException:
                                # Not fatal.  Suppress.
                                pass


        def reset(self):
                """Resets the transport.  This needs to be done
                if an install plan has been canceled and needs to
                be restarted.  This clears the state of the
                transport and its associated components."""

                if not self.__engine:
                        # Don't reset if not configured
                        return

                self._lock.acquire()
                try:
                        self.__engine.reset()
                        self.__repo_cache.clear_cache()
                        self.cfg.reset_caches()
                        if self.__dynamic_mirrors:
                                try:
                                        self.__dynamic_mirrors.locate()
                                except tx.mDNSException:
                                        # Not fatal. Suppress.
                                        pass
                finally:
                        self._lock.release()

        def shutdown(self):
                """Shuts down any portions of the transport that can
                actively be connected to remote endpoints."""

                if not self.__engine:
                        # Already shut down
                        return

                self._lock.acquire()
                try:
                        self.__engine.shutdown()
                        self.__engine = None
                        if self.__repo_cache:
                                self.__repo_cache.clear_cache()
                        self.__repo_cache = None
                        self.__dynamic_mirrors = []
                finally:
                        self._lock.release()

        @LockedTransport()
        def do_search(self, pub, data, ccancel=None, alt_repo=None):
                """Perform a search request.  Returns a file-like object or an
                iterable that contains the search results.  Callers need to
                catch transport exceptions that this object may generate."""

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
                self._captive_portal_test(ccancel=ccancel)

                # For search, prefer remote sources if available.  This allows
                # consumers to configure both a file-based and network-based set
                # of origins for a publisher without incurring the significant
                # overhead of performing file-based search unless the network-
                # based resource is unavailable.
                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    prefer_remote=True, alt_repo=alt_repo, operation="search",
                    versions=[0, 1]):

                        try:
                                fobj = d.do_search(data, header,
                                    ccancel=ccancel, pub=pub)
                                if hasattr(fobj, "_prime"):
                                        fobj._prime()

                                if hasattr(fobj, "set_lock"):
                                        # Since we're returning a file object
                                        # that's using the same engine as the
                                        # rest of this transport, assign our
                                        # lock to the fobj.  It must synchronize
                                        # with us too.
                                        fobj.set_lock(self._lock)

                                return fobj

                        except tx.ExcessiveTransientFailure, ex:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(ex.failures)

                        except tx.TransportProtoError, e:
                                if e.code in (httplib.NOT_FOUND, errno.ENOENT):
                                        raise apx.UnsupportedSearchError(e.url,
                                            "search/1")
                                elif e.code == httplib.NO_CONTENT:
                                        raise apx.NegativeSearchResult(e.url)
                                elif e.code == (httplib.BAD_REQUEST,
                                    errno.EINVAL):
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
                        # If transport isn't connected to image, or no
                        # ca-dir is specified, fallback to this one.
                        fb_cadir = os.path.join(os.path.sep, "etc",
                            "openssl", "certs")

                        try:
                                cadir = self.cfg.get_property("ca-path")
                                cadir = os.path.normpath(cadir)
                        except KeyError:
                                cadir = fb_cadir

                        if not os.path.exists(cadir):
                                raise tx.TransportOperationError("Unable to "
                                    "locate a CA directory: %s\n"
                                    "Secure connection is not available."
                                    % cadir)

                        self.__cadir = cadir
                        return cadir

                return self.__cadir

        @LockedTransport()
        def get_catalog(self, pub, ts=None, ccancel=None, path=None,
            alt_repo=None):
                """Get the catalog for the specified publisher.  If
                ts is defined, request only changes newer than timestamp
                ts."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))
                download_dir = self.cfg.incoming_root
                if path:
                        croot = path
                else:
                        croot = pub.catalog_root

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test(ccancel=ccancel)

                for d in self.__gen_repo(pub, retry_count, origin_only=True,
                    alt_repo=alt_repo):

                        repostats = self.stats[d.get_url()]

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:

                                resp = d.get_catalog(ts, header,
                                    ccancel=ccancel, pub=pub)

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

        @LockedTransport()
        def get_catalog1(self, pub, flist, ts=None, path=None,
            progtrack=None, ccancel=None, revalidate=False, redownload=False,
            alt_repo=None):
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
                set a directory path in 'path'.

                If the caller knows that the upstream metadata is cached,
                and needs a refresh it should set 'revalidate' to True.
                If the caller knows that the upstream metadata is cached and
                is corrupted, it should set 'redownload' to True.  Either
                'revalidate' or 'redownload' may be used, but not both."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = []
                header = self.__build_header(uuid=self.__get_uuid(pub))

                if progtrack and ccancel:
                        progtrack.check_cancelation = ccancel

                # Ensure that caller only passed one item, if ts was
                # used.
                if ts and len(flist) > 1:
                        raise ValueError("Ts may only be used with a single"
                            " item flist.")

                if redownload and revalidate:
                        raise ValueError("Either revalidate or redownload"
                            " may be used, but not both.")

                # download_dir is temporary download path.  Completed_dir
                # is the cache where valid content lives.
                if path:
                        completed_dir = path
                else:
                        completed_dir = pub.catalog_root
                download_dir = self.cfg.incoming_root

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test(ccancel=ccancel)

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

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    operation="catalog", versions=[1], ccancel=ccancel,
                    alt_repo=alt_repo):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]
                        gave_up = False

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to supress a permanent failure.
                        try:
                                errlist = d.get_catalog1(flist, download_dir,
                                    header, ts, progtrack=progtrack, pub=pub,
                                    redownload=redownload,
                                    revalidate=revalidate)
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
                                        repostats.record_error(content=True)
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

                if failedreqs and failures:
                        failures = [
                            x for x in failures
                            if x.request in failedreqs
                        ]
                        tfailurex = tx.TransportFailures()
                        for f in failures:
                                tfailurex.append(f)
                        raise tfailurex

        @LockedTransport()
        def get_publisherdata(self, pub, ccancel=None):
                """Given a publisher pub, return the publisher/0
                information as a list of publisher objects.  If
                no publisher information was contained in the
                response, the list will be empty."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = None

                if isinstance(pub, publisher.Publisher):
                        header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    operation="publisher", versions=[0], ccancel=ccancel):
                        try:
                                resp = d.get_publisherinfo(header,
                                    ccancel=ccancel)
                                infostr = resp.read()

                                # If parse succeeds, then the data is valid.
                                pub_data = p5i.parse(data=infostr)
                                return [pub for pub, ignored in pub_data if pub]
                        except tx.ExcessiveTransientFailure, e:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(e.failures)

                        except apx.InvalidP5IFile, e:
                                url = d.get_url()
                                exc = tx.TransferContentException(url,
                                    "api_errors.InvalidP5IFile:%s" %
                                    (" ".join([str(a) for a in e.args])))
                                repostats = self.stats[url]
                                repostats.record_error(content=True)
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

        @LockedTransport()
        def get_syspub_data(self, repo_uri, ccancel=None):
                """Get the publisher and image configuration from the system
                repo given in repo_uri."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = None

                assert isinstance(self.cfg, ImageTransportCfg)
                assert isinstance(repo_uri, publisher.RepositoryURI)

                for d, v in self.__gen_repo(repo_uri, retry_count,
                    origin_only=True, operation="syspub", versions=[0],
                    ccancel=ccancel):
                        try:
                                resp = d.get_syspub_info(header,
                                    ccancel=ccancel)
                                infostr = resp.read()
                                return p5s.parse(repo_uri.get_host(), infostr)
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

        @LockedTransport()
        def get_content(self, pub, fhash, fmri=None, ccancel=None):
                """Given a fhash, return the uncompressed content content from
                the remote object.  This is similar to get_datastream, except
                that the transport handles retrieving and decompressing the
                content.

                'fmri' If the fhash corresponds to a known package, the fmri
                should be specified for optimal transport performance.
                """

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = self.__build_header(uuid=self.__get_uuid(pub))

                alt_repo = None
                if not fmri and self.cfg.alt_pubs:
                        # No FMRI was provided, but alternate package sources
                        # are available, so create a new repository object
                        # that composites the repository information returned
                        # from the image with the alternate sources for this
                        # publisher.
                        alt_repo = pub.repository
                        if alt_repo:
                                alt_repo = copy.copy(alt_repo)
                        else:
                                alt_repo = publisher.Repository()

                        for tpub in self.cfg.alt_pubs:
                                if tpub.prefix != pub.prefix:
                                        continue
                                for o in tpub.repository.origins:
                                        if not alt_repo.has_origin(o):
                                                alt_repo.add_origin(o)
                elif fmri:
                        alt_repo = self.cfg.get_pkg_alt_repo(fmri)

                for d, v in self.__gen_repo(pub, retry_count, operation="file",
                    versions=[0, 1], alt_repo=alt_repo):

                        url = d.get_url()

                        try:
                                resp = d.get_datastream(fhash, v, header,
                                    ccancel=ccancel, pub=pub)
                                s = cStringIO.StringIO()
                                hash_val = misc.gunzip_from_stream(resp, s)

                                if hash_val != fhash:
                                        exc = tx.InvalidContentException(
                                            reason="hash failure:  expected: %s"
                                            "computed: %s" % (fhash, hash_val),
                                            url=url)
                                        repostats = self.stats[url]
                                        repostats.record_error(content=True)
                                        raise exc

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
                                repostats = self.stats[url]
                                repostats.record_error(content=True)
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

        @LockedTransport()
        def get_status(self, pub, ccancel=None):
                """Given a publisher pub, return the stats information
                for the repository as a dictionary."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = None

                if isinstance(pub, publisher.Publisher):
                        header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    operation="status", versions=[0], ccancel=ccancel):
                        try:
                                resp = d.get_status(header, ccancel=ccancel)
                                infostr = resp.read()

                                # If parse succeeds, then the data is valid.
                                return dict(json.loads(infostr))
                        except tx.ExcessiveTransientFailure, e:
                                # If an endpoint experienced so many failures
                                # that we just gave up, grab the list of
                                # failures that it contains
                                failures.extend(e.failures)

                        except (TypeError, ValueError), e:
                                url = d.get_url()
                                exc = tx.TransferContentException(url,
                                    "Invalid stats response: %s" % e)
                                repostats = self.stats[url]
                                repostats.record_error(content=True)
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

        @LockedTransport()
        def touch_manifest(self, fmri, intent=None, ccancel=None,
            alt_repo=None):
                """Touch a manifest.  This operation does not
                return the manifest's content.  The FMRI is given
                as fmri.  An optional intent string may be supplied
                as intent."""

                failures = tx.TransportFailures()
                pub_prefix = fmri.publisher
                pub = self.cfg.get_publisher(pub_prefix)
                mfst = fmri.get_url_path()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(intent=intent,
                    uuid=self.__get_uuid(pub))

                if not alt_repo:
                        alt_repo = self.cfg.get_pkg_alt_repo(fmri)

                for d in self.__gen_repo(pub, retry_count, origin_only=True,
                    alt_repo=alt_repo):

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:
                                d.touch_manifest(mfst, header, ccancel=ccancel,
                                    pub=pub)
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

        @LockedTransport()
        def get_manifest(self, fmri, excludes=misc.EmptyI, intent=None,
            ccancel=None, pub=None, content_only=False, alt_repo=None):
                """Given a fmri, and optional excludes, return a manifest
                object."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                pub_prefix = fmri.publisher
                download_dir = self.cfg.incoming_root
                mcontent = None
                header = None

                if not pub:
                        pub = self.cfg.get_publisher(pub_prefix)

                if isinstance(pub, publisher.Publisher):
                        header = self.__build_header(intent=intent,
                            uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test(ccancel=ccancel)

                # Check if the download_dir exists.  If it doesn't create
                # the directories.
                self._makedirs(download_dir)

                if not alt_repo:
                        alt_repo = self.cfg.get_pkg_alt_repo(fmri)

                for d in self.__gen_repo(pub, retry_count, origin_only=True,
                    alt_repo=alt_repo):

                        repostats = self.stats[d.get_url()]
                        verified = False
                        try:
                                resp = d.get_manifest(fmri, header,
                                    ccancel=ccancel, pub=pub)
                                mcontent = resp.read()

                                verified = self._verify_manifest(fmri,
                                    content=mcontent, pub=pub)

                                if content_only:
                                        return mcontent

                                m = manifest.FactoredManifest(fmri,
                                    self.cfg.get_pkg_dir(fmri),
                                    contents=mcontent, excludes=excludes,
                                    pathname=self.cfg.get_pkg_pathname(fmri))

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

                        except (apx.InvalidPackageErrors, ActionError), e:
                                if verified:
                                        raise
                                repostats.record_error(content=True)
                                te = tx.TransferContentException(
                                    d.get_url(), reason=str(e))
                                failures.append(te)

                raise failures

        @LockedTransport()
        def prefetch_manifests(self, fetchlist, excludes=misc.EmptyI,
            progtrack=None, ccancel=None, alt_repo=None):
                """Given a list of tuples [(fmri, intent), ...], prefetch
                the manifests specified by the fmris in argument
                fetchlist.  Caller may supply a progress tracker in
                'progtrack' as well as the check-cancellation callback in
                'ccancel.'

                This method will not return transient transport errors,
                but it should raise any that would cause an immediate
                failure."""

                download_dir = self.cfg.incoming_root

                if not fetchlist:
                        return

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                try:
                        self._captive_portal_test(ccancel=ccancel)
                except apx.InvalidDepotResponseException:
                        return

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
                                return
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

                get_alt = not alt_repo
                for fmri, intent in fetchlist:
                        if get_alt:
                                alt_repo = self.cfg.get_pkg_alt_repo(fmri)

                        # Multi transfer object must be created for each unique
                        # publisher or repository.
                        if alt_repo:
                                eid = id(alt_repo)
                        else:
                                eid = fmri.publisher

                        pub = self.cfg.get_publisher(fmri.publisher)
                        header = self.__build_header(intent=intent,
                            uuid=self.__get_uuid(pub))

                        if eid not in mx_pub:
                                mx_pub[eid] = MultiXfr(pub,
                                    progtrack=progtrack,
                                    ccancel=ccancel,
                                    alt_repo=alt_repo)

                        # Add requests keyed by requested package
                        # fmri.  Value contains (header, fmri) tuple.
                        mx_pub[eid].add_hash(fmri, (header, fmri))

                for mxfr in mx_pub.values():
                        namelist = [k for k in mxfr]
                        while namelist:
                                chunksz = self.__chunk_size(pub,
                                    alt_repo=mxfr.get_alt_repo(),
                                    origin_only=True)
                                mfstlist = [
                                    (n, mxfr[n][0])
                                    for n in namelist[:chunksz]
                                ]
                                del namelist[:chunksz]

                                try:
                                        self._prefetch_manifests_list(mxfr,
                                            mfstlist, excludes)
                                except apx.PermissionsException:
                                        return

        def _prefetch_manifests_list(self, mxfr, mlist, excludes=misc.EmptyI):
                """Perform bulk manifest prefetch.  This is the routine
                that downloads initiates the downloads in chunks
                determined by its caller _prefetch_manifests.  The mxfr
                argument should be a MultiXfr object, and mlist
                should be a list of tuples (fmri, header)."""

                # Don't perform multiple retries, since we're just prefetching.
                retry_count = 1
                mfstlist = mlist
                pub = mxfr.get_publisher()
                progtrack = mxfr.get_progtrack()

                # download_dir is temporary download path.
                download_dir = self.cfg.incoming_root

                for d in self.__gen_repo(pub, retry_count, origin_only=True,
                    alt_repo=mxfr.get_alt_repo()):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]
                        gave_up = False

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to suppress a permanant failure.
                        try:
                                errlist = d.get_manifests(mfstlist,
                                    download_dir, progtrack=progtrack, pub=pub)
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

                        for s in success:

                                dl_path = os.path.join(download_dir,
                                    s.get_url_path())

                                try:
                                        # Verify manifest content.
                                        fmri = mxfr[s][1]
                                        verified = self._verify_manifest(fmri,
                                            dl_path)
                                except tx.InvalidContentException, e:
                                        e.request = s
                                        repostats.record_error(content=True)
                                        failedreqs.append(s)
                                        continue

                                try:
                                        mf = file(dl_path)
                                        mcontent = mf.read()
                                        mf.close()
                                        manifest.FactoredManifest(fmri,
                                            self.cfg.get_pkg_dir(fmri),
                                            contents=mcontent, excludes=excludes,
                                            pathname=self.cfg.get_pkg_pathname(fmri))
                                except (apx.InvalidPackageErrors,
                                    ActionError), e:
                                        if verified:
                                                # If the manifest was physically
                                                # valid, but can't be logically
                                                # parsed, drive on.
                                                os.remove(dl_path)
                                                progtrack.evaluate_progress(
                                                    fmri)
                                                mxfr.del_hash(s)
                                                continue
                                        repostats.record_error(content=True)
                                        failedreqs.append(s)
                                        os.remove(dl_path)
                                        continue

                                os.remove(dl_path)
                                if progtrack:
                                        progtrack.evaluate_progress(fmri)
                                mxfr.del_hash(s)

                        # If there were failures, re-generate list for just
                        # failed requests.
                        if failedreqs:
                                # Generate mfstlist here, which included any
                                # reqs that failed during verification.
                                mfstlist = [
                                    (x,y) for x,y in mfstlist
                                    if x in failedreqs
                                ]
                        # Return if everything was successful
                        else:
                                return

        def _verify_manifest(self, fmri, mfstpath=None, content=None, pub=None):
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

                if not isinstance(pub, publisher.Publisher):
                        # Get publisher using information from FMRI.
                        try:
                                pub = self.cfg.get_publisher(fmri.publisher)
                        except apx.UnknownPublisher:
                                return False

                # Handle case where publisher has no Catalog.
                if not pub.catalog:
                        return False

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
                if not self.cfg.get_policy(imageconfig.SEND_UUID):
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
                header = None

                if isinstance(pub, publisher.Publisher):
                        header = self.__build_header(uuid=self.__get_uuid(pub))

                # download_dir is temporary download path.
                download_dir = self.cfg.incoming_root

                cache = self.cfg.get_caches(pub, readonly=False)
                if cache:
                        # For now, pick first cache in list, if any are
                        # present.
                        cache = cache[0]
                else:
                        cache = None

                for d, v in self.__gen_repo(pub, retry_count, operation="file",
                    versions=[0, 1], alt_repo=mfile.get_alt_repo()):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]
                        gave_up = False

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to supress a permanant failure.
                        try:
                                errlist = d.get_files(filelist, download_dir,
                                    progtrack, v, header, pub=pub)
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

                                if cache:
                                        cpath = cache.insert(s, dl_path)
                                        mfile.file_done(s, cpath)
                                else:
                                        mfile.file_done(s, dl_path)

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

        @LockedTransport()
        def _get_files(self, mfile):
                """Perform an operation that gets multiple files at once.
                A mfile object contains information about the multiple-file
                request that will be performed."""

                download_dir = self.cfg.incoming_root
                pub = mfile.get_publisher()

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test(ccancel=mfile.get_ccancel())

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
                        chunksz = self.__chunk_size(pub,
                            alt_repo=mfile.get_alt_repo())

                        for i, v in enumerate(mfile):
                                if i >= chunksz:
                                        break
                                filelist.append(v)

                        self._get_files_list(mfile, filelist)

        def get_versions(self, pub, ccancel=None, alt_repo=None):
                """Query the publisher's origin servers for versions
                information.  Return a dictionary of "name":"versions" """

                self._lock.acquire()
                try:
                        v = self._get_versions(pub, ccancel=ccancel,
                            alt_repo=alt_repo)
                finally:
                        self._lock.release()

                return v

        def _get_versions(self, pub, ccancel=None, alt_repo=None):
                """Implementation of get_versions"""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self._captive_portal_test(ccancel=ccancel)

                for d in self.__gen_repo(pub, retry_count, origin_only=True,
                    alt_repo=alt_repo):
                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:
                                vers = self.__get_version(d, header,
                                    ccancel=ccancel)
                                # Save this information for later use, too.
                                self.__fill_repo_vers(d, vers)
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
                                    d.get_url(), "Unable to parse repository "
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

        def __fill_repo_vers(self, repo, vers=None, ccancel=None):
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
                        versids.sort(reverse=True)
                        vers[key] = versids

                repo.add_version_data(vers)

        def __gen_repo(self, pub, count, prefer_remote=False, origin_only=False,
            single_repository=False, operation=None, versions=None,
            ccancel=None, alt_repo=None):
                """An internal method that returns the list of Repo objects
                for a given Publisher.  Callers use this method to generate
                lists of endpoints for transport operations, and to retry
                operations to a single endpoint.

                The 'pub' argument is a Publisher object or RepositoryURI
                object.  This is used to lookup a transport.Repo object.

                The 'count' argument determines how many times the routine
                will iterate through a list of endpoints.

                'prefer_remote' is an optional boolean value indicating whether
                network-based sources are preferred over local sources.  If
                True, network-based origins will be returned first after the
                default order criteria has been applied.  This is a very
                special case operation, and should not be used liberally.

                'origin_only' returns only endpoints that are Origins.
                This allows the caller to exclude mirrors from the list,
                for operations that are meta-data only.

                If callers are performing a publication operation and want
                to ensure that only one Repository is used as an endpoint,
                'single_repository' should be set to True.

                If callers wish to only obtain repositories that support
                a particular version of an operation, they should supply
                the operation's name as a string to the 'operation' argument.
                The 'versions' argument should contain the desired available
                versions for the operation.  This must be given as integers
                in a list.

                If a versioned operation is requested, this routine may have
                to perform network operations to complete the request.  If
                cancellation is desired, a cancellation object should be
                passed in the 'ccancel' argument.

                By default, this routine looks at a Publisher's
                repository.  If the caller would like to use a
                different Repository object, it should pass one in
                'alt_repo.'

                This function returns a Repo object by default.  If
                versions and operation are specified, it returns a tuple
                of (Repo, highest supported version)."""

                if not self.__engine:
                        self.__setup()

                # If alt_repo supplied, use that as the Repository.
                # Otherwise, check that a Publisher was passed, and use
                # its repository.
                repo = None
                if alt_repo:
                        repo = alt_repo
                elif isinstance(pub, publisher.Publisher):
                        repo = pub.repository
                        if not repo:
                                raise apx.NoPublisherRepositories(pub)

                if repo and origin_only:
                        repolist = repo.origins
                        origins = repo.origins
                        if single_repository:
                                assert len(repolist) == 1
                elif repo:
                        repolist = repo.mirrors[:]
                        repolist.extend(repo.origins)
                        repolist.extend(self.__dynamic_mirrors)
                        origins = repo.origins
                else:
                        # Caller passed RepositoryURI object in as
                        # pub argument, repolist is the RepoURI
                        repolist = [pub]
                        origins = repolist

                def remote_first(a, b):
                        # For now, any URI using the file scheme is considered
                        # local.  Realistically, it could be an NFS mount, etc.
                        # However, that's a further refinement that can be done
                        # later.
                        aremote = a[0].scheme != "file"
                        bremote = b[0].scheme != "file"
                        return cmp(aremote, bremote) * -1

                if versions:
                        versions = sorted(versions, reverse=True)

                fail = None
                for i in xrange(count):
                        rslist = self.stats.get_repostats(repolist, origins)
                        if prefer_remote:
                                rslist.sort(cmp=remote_first)

                        fail = tx.TransportFailures()
                        repo_found = False
                        for rs, ruri in rslist:
                                if operation and versions:
                                        repo = self.__repo_cache.new_repo(rs,
                                            ruri)
                                        if not repo.has_version_data():
                                                try:
                                                        self.__fill_repo_vers(
                                                            repo,
                                                            ccancel=ccancel)
                                                except tx.TransportException, ex:
                                                        # Encountered a
                                                        # transport error while
                                                        # trying to contact this
                                                        # origin.  Save the
                                                        # errors on each retry
                                                        # so that they can be
                                                        # raised instead of
                                                        # an unsupported
                                                        # operation error.
                                                        if isinstance(ex,
                                                            tx.TransportFailures):
                                                                fail.extend(
                                                                    ex.exceptions)
                                                        else:
                                                                fail.append(ex)
                                                        continue

                                        verid = repo.supports_version(operation,
                                            versions)
                                        if verid >= 0:
                                                repo_found = True
                                                yield repo, verid
                                else:
                                        repo_found = True
                                        yield self.__repo_cache.new_repo(rs,
                                            ruri)

                        if not repo_found and fail:
                                raise fail
                        if not repo_found and operation and versions:
                                if not origins and \
                                    isinstance(pub, publisher.Publisher):
                                        # Special error case; no transport
                                        # configuration available for this
                                        # publisher.
                                        raise apx.NoPublisherRepositories(pub)

                                # If a versioned operation was requested and
                                # wasn't found, then raise an unsupported
                                # exception using the newest version allowed.
                                raise apx.UnsupportedRepositoryOperation(pub,
                                    "%s/%d" % (operation, versions[-1]))

        def __chunk_size(self, pub, alt_repo=None, origin_only=False):
                """Determine the chunk size based upon how many of the known
                mirrors have been visited.  If not all mirrors have been
                visited, choose a small size so that if it ends up being
                a poor choice, the client doesn't transfer too much data."""

                CHUNK_SMALL = 10
                CHUNK_LARGE = 100

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                if alt_repo:
                        repolist = alt_repo.origins[:]
                        if not origin_only:
                                repolist.extend(alt_repo.mirrors)
                elif isinstance(pub, publisher.Publisher):
                        repo = pub.repository
                        if not repo:
                                raise apx.NoPublisherRepositories(pub)
                        repolist = repo.origins[:]
                        if not origin_only:
                                repolist.extend(repo.mirrors)
                else:
                        # If caller passed RepositoryURI object in as
                        # pub argument, repolist is the RepoURI.
                        repolist = [pub]

                n = len(repolist)
                m = self.stats.get_num_visited(repolist)
                if m < n:
                        return CHUNK_SMALL
                return CHUNK_LARGE

        @LockedTransport()
        def valid_publisher_test(self, pub, ccancel=None):
                """Test that the publisher supplied in pub actually
                points to a valid packaging server."""

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
                            "contact repository.\nReported the following "
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

                self._lock.acquire()
                try:
                        self._captive_portal_test(ccancel=ccancel)
                finally:
                        self._lock.release()

        def _captive_portal_test(self, ccancel=None):
                """Implementation of captive_portal_test."""

                fail = tx.TransportFailures()

                if self.__portal_test_executed:
                        return

                self.__portal_test_executed = True
                vd = None

                for pub in self.cfg.gen_publishers():
                        try:
                                vd = self._get_versions(pub, ccancel=ccancel)
                        except tx.TransportException, ex:
                                # Encountered a transport error while
                                # trying to contact this publisher.
                                # Pick another publisher instead.
                                if isinstance(ex, tx.TransportFailures):
                                        fail.extend(ex.exceptions)
                                else:
                                        fail.append(ex)
                                continue
                        except apx.CanceledException:
                                self.__portal_test_executed = False
                                raise

                        if self._valid_versions_test(vd):
                                return
                        else:
                                fail.append(tx.PkgProtoError(pub.prefix,
                                    "version", 0,
                                    "Invalid content in response"))
                                continue

                if not vd:
                        # We got all the way through the list of publishers but
                        # encountered transport errors in every case.  This is
                        # likely a network configuration problem.  Report our
                        # inability to contact a server.
                        estr = "Unable to contact any configured publishers." \
                            "\nThis is likely a network configuration problem."
                        if fail:
                                estr += "\n%s" % fail
                        raise apx.InvalidDepotResponseException(None, estr)

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

        def multi_file(self, fmri, progtrack, ccancel, alt_repo=None):
                """Creates a MultiFile object for this transport.
                The caller may add actions to the multifile object
                and wait for the download to complete."""

                if not fmri:
                        return None

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                if not alt_repo:
                        alt_repo = self.cfg.get_pkg_alt_repo(fmri)

                try:
                        pub = self.cfg.get_publisher(fmri.publisher)
                except apx.UnknownPublisher:
                        # Allow publishers that don't exist in configuration
                        # to be used so that if data exists in the cache for
                        # them, the operation will still succeed.  This only
                        # needs to be done here as multi_file_ni is only used
                        # for publication tools.
                        pub = publisher.Publisher(fmri.publisher)

                mfile = MultiFile(pub, self, progtrack, ccancel,
                    alt_repo=alt_repo)

                return mfile

        def multi_file_ni(self, publisher, final_dir, decompress=False,
            progtrack=None, ccancel=None, alt_repo=None):
                """Creates a MultiFileNI object for this transport.
                The caller may add actions to the multifile object
                and wait for the download to complete.

                This is used by callers who want to download files,
                but not install them through actions."""

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                mfile = MultiFileNI(publisher, self, final_dir,
                    decompress=decompress, progtrack=progtrack, ccancel=ccancel,
                    alt_repo=alt_repo)

                return mfile

        def _action_cached(self, action, pub):
                """If a file with the name action.hash is cached,
                and if it has the same content hash as action.chash,
                then return the path to the file.  If the file can't
                be found, return None."""

                hashval = action.hash
                for cache in self.cfg.get_caches(pub=pub, readonly=True):
                        cache_path = cache.lookup(hashval)
                        try:
                                if cache_path:
                                        self._verify_content(action, cache_path)
                                        return cache_path
                        except tx.InvalidContentException:
                                # If the content in the cache doesn't match the
                                # hash of the action, verify will have already
                                # purged the item from the cache.
                                pass

                return None

        @staticmethod
        def _verify_content(action, filepath):
                """If action contains an attribute that has the compressed
                hash, read the file specified in filepath and verify
                that the hash values match.  If the values do not match,
                remove the file and raise an InvalidContentException."""

                chash = action.attrs.get("chash", None)
                if action.name == "signature":
                        name = os.path.basename(filepath)
                        found = False
                        assert len(action.get_chain_certs()) == \
                            len(action.get_chain_certs_chashes())
                        for n, c in zip(action.get_chain_certs(),
                            action.get_chain_certs_chashes()):
                                if name == n:
                                        found = True
                                        chash = c
                                        break
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

        @LockedTransport()
        def publish_add(self, pub, action=None, ccancel=None, progtrack=None,
            trans_id=None):
                """Perform the 'add' publication operation to the publisher
                supplied in pub.  The transaction-id is passed in trans_id."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                if progtrack and ccancel:
                        progtrack.check_cancelation = ccancel

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="add", versions=[0]):
                        try:
                                d.publish_add(action, header=header,
                                    progtrack=progtrack, trans_id=trans_id)
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

        @LockedTransport()
        def publish_add_file(self, pub, pth, trans_id=None):
                """Perform the 'add_file' publication operation to the publisher
                supplied in pub.  The caller should include the action in the
                action argument. The transaction-id is passed in trans_id."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if the transport isn't configured or was shutdown.
                if not self.__engine:
                        self.__setup()

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="file", versions=[1]):
                        try:
                                d.publish_add_file(pth, header=header,
                                    trans_id=trans_id)
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

        @LockedTransport()
        def publish_abandon(self, pub, trans_id=None):
                """Perform an 'abandon' publication operation to the
                publisher supplied in the pub argument.  The caller should
                also include the transaction id in trans_id."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="abandon", versions=[0]):
                        try:
                                state, fmri = d.publish_abandon(header=header,
                                    trans_id=trans_id)
                                return state, fmri
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

        @LockedTransport()
        def publish_close(self, pub, trans_id=None, refresh_index=False,
            add_to_catalog=False):
                """Perform a 'close' publication operation to the
                publisher supplied in the pub argument.  The caller should
                also include the transaction id in trans_id.  If add_to_catalog
                is true, the pkg will be added to the catalog once
                the transactions close.  Not all transport methods
                recognize this parameter."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="close", versions=[0]):
                        try:
                                state, fmri = d.publish_close(header=header,
                                    trans_id=trans_id,
                                    add_to_catalog=add_to_catalog)
                                return state, fmri
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

        @LockedTransport()
        def publish_open(self, pub, client_release=None, pkg_name=None):
                """Perform an 'open' transaction to start a publication
                transaction to the publisher named in pub.  The caller should
                supply the client's OS release in client_release, and the
                package's name in pkg_name."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="open", versions=[0]):
                        try:
                                trans_id = d.publish_open(header=header,
                                    client_release=client_release,
                                    pkg_name=pkg_name)
                                return trans_id
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

        @LockedTransport()
        def publish_rebuild(self, pub):
                """Instructs the repositories named by Publisher pub
                to rebuild package and search data."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="admin", versions=[0]):
                        try:
                                d.publish_rebuild(header=header, pub=pub)
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

        @LockedTransport()
        def publish_append(self, pub, client_release=None, pkg_name=None):
                """Perform an 'append' transaction to start a publication
                transaction to the publisher named in pub.  The caller should
                supply the client's OS release in client_release, and the
                package's name in pkg_name."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # Call setup if transport isn't configured, or was shutdown.
                if not self.__engine:
                        self.__setup()

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="append", versions=[0]):
                        try:
                                trans_id = d.publish_append(header=header,
                                    client_release=client_release,
                                    pkg_name=pkg_name)
                                return trans_id
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

        @LockedTransport()
        def publish_rebuild_indexes(self, pub):
                """Instructs the repositories named by Publisher pub
                to rebuild their search indexes."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="admin", versions=[0]):
                        try:
                                d.publish_rebuild_indexes(header=header,
                                    pub=pub)
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

        @LockedTransport()
        def publish_rebuild_packages(self, pub):
                """Instructs the repositories named by Publisher pub
                to rebuild package data."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="admin", versions=[0]):
                        try:
                                d.publish_rebuild_packages(header=header,
                                    pub=pub)
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

        @LockedTransport()
        def publish_refresh(self, pub):
                """Instructs the repositories named by Publisher pub
                to refresh package and search data."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="admin", versions=[0]):
                        try:
                                d.publish_refresh(header=header, pub=pub)
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

        @LockedTransport()
        def publish_refresh_indexes(self, pub):
                """Instructs the repositories named by Publisher pub
                to refresh their search indexes."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # In this case, the operation and versions keywords are
                # purposefully avoided as the underlying repo function
                # will automatically determine what operation to use
                # for the single origin returned by __gen_repo.
                for d in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True):
                        try:
                                d.publish_refresh_indexes(header=header,
                                    pub=pub)
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

        @LockedTransport()
        def publish_refresh_packages(self, pub):
                """Instructs the repositories named by Publisher pub
                to refresh package data."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d, v in self.__gen_repo(pub, retry_count, origin_only=True,
                    single_repository=True, operation="admin", versions=[0]):
                        try:
                                d.publish_refresh_packages(header=header,
                                    pub=pub)
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

        def publish_cache_repository(self, pub, repo):
                """If the caller needs to override the underlying Repository
                object kept by the transport, it should use this method
                to replace the cached Repository object."""

                assert(isinstance(pub, publisher.Publisher))

                if not self.__engine:
                        self.__setup()

                origins = [pub.repository.origins[0]]
                rslist = self.stats.get_repostats(origins, origins)
                rs, ruri = rslist[0]

                self.__repo_cache.update_repo(rs, ruri, repo)

        def publish_cache_contains(self, pub):
                """Returns true if the publisher's origin is cached
                in the repo cache."""

                if not self.__engine:
                        self.__setup()

                originuri = pub.repository.origins[0].uri
                return originuri in self.__repo_cache


class MultiXfr(object):
        """A transport object for performing multiple simultaneous
        requests.  This object matches publisher to list of requests, and
        allows the caller to associate a piece of data with the request key."""

        def __init__(self, pub, progtrack=None, ccancel=None, alt_repo=None):
                """Supply the publisher as argument 'pub'."""

                self._publisher = pub
                self._hash = {}
                self._progtrack = progtrack
                self._alt_repo = alt_repo
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

        def get_alt_repo(self):
                """Return the alternate Repository object, if one has
                been selected.  Otherwise, return None."""

                return self._alt_repo

        def get_ccancel(self):
                """If the progress tracker has an associated ccancel,
                return it.  Otherwise, return None."""

                return getattr(self._progtrack, "check_cancelation", None)

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

        def __init__(self, pub, xport, progtrack, ccancel, alt_repo=None):
                """Supply the destination publisher in the pub argument.
                The transport object should be passed in xport."""

                MultiXfr.__init__(self, pub, progtrack=progtrack,
                    ccancel=ccancel, alt_repo=alt_repo)

                self._transport = xport

        def add_action(self, action):
                """The multiple file retrieval operation is asynchronous.
                Add files to retrieve with this function.  The caller
                should pass the action, which causes its file to
                be added to an internal retrieval list."""

                cpath = self._transport._action_cached(action,
                    self.get_publisher())
                if cpath:
                        action.data = self._make_opener(cpath)
                        if self._progtrack:
                                filesz = int(misc.get_pkg_otw_size(action))
                                file_cnt = 1
                                if action.name == "signature":
                                        filesz += \
                                            action.get_action_chain_csize()
                                        file_cnt += \
                                            len(action.attrs.get("chain",
                                            "").split())
                                self._progtrack.download_add_progress(file_cnt,
                                    filesz)
                        return

                hashval = action.hash

                self.add_hash(hashval, action)
                if action.name == "signature":
                        for c in action.get_chain_certs():
                                self.add_hash(c, action)

        def add_hash(self, hashval, item):
                """Add 'item' to list of values that exist for
                hash value 'hashval'."""

                self._hash.setdefault(hashval, []).append(item)

        @staticmethod
        def _make_opener(cache_path):
                def opener():
                        f = open(cache_path, "rb")
                        return f
                return opener

        def file_done(self, hashval, current_path):
                """Tell MFile that the transfer completed successfully."""

                self._make_openers(hashval, current_path)
                self.del_hash(hashval)

        def _make_openers(self, hashval, cache_path):
                """Find each action associated with the hash value hashval.
                Create an opener that points to the cache file for the
                action's data method."""

                totalsz = 0
                nfiles = 0

                filesz = os.stat(cache_path).st_size
                for action in self._hash[hashval]:
                        nfiles += 1
                        bn = os.path.basename(cache_path)
                        if action.name != "signature" or action.hash == bn:
                                action.data = self._make_opener(cache_path)
                                totalsz += misc.get_pkg_otw_size(action)
                        else:
                                totalsz += action.get_chain_csize(bn)

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
                nbytes = int(totalsz - filesz)
                if self._progtrack:
                        self._progtrack.download_add_progress((nfiles - 1),
                            nbytes)

        def subtract_progress(self, size):
                """Subtract the progress accumulated by the download of
                file with hash of hashval.  make_openers accounts for
                hashes with multiple actions.  If this has been invoked,
                it has happened before make_openers, so it's only necessary
                to adjust the progress for a single file."""

                if not self._progtrack:
                        return

                self._progtrack.download_add_progress(-1, int(-size))

        def wait_files(self):
                """Wait for outstanding file retrieval operations to
                complete."""

                if self._hash:
                        self._transport._get_files(self)

class MultiFileNI(MultiFile):
        """A transport object for performing multi-file requests
        using pkg actions.  This takes care of matching the publisher
        with the actions, and performs the download and content
        verification necessary to assure correct content installation.

        This subclass is used when the actions won't be installed, but
        are used to identify and verify the content.  Additional parameters
        define what happens when download finishes successfully."""

        def __init__(self, pub, xport, final_dir, decompress=False,
            progtrack=None, ccancel=None, alt_repo=None):
                """Supply the destination publisher in the pub argument.
                The transport object should be passed in xport."""

                MultiFile.__init__(self, pub, xport, progtrack=progtrack,
                    ccancel=ccancel, alt_repo=alt_repo)

                self._final_dir = final_dir
                self._decompress = decompress

        def add_action(self, action):
                """The multiple file retrieval operation is asynchronous.
                Add files to retrieve with this function.  The caller
                should pass the action, which causes its file to
                be added to an internal retrieval list."""

                cpath = self._transport._action_cached(action,
                    self.get_publisher())
                hashval = action.hash

                if cpath:
                        self._final_copy(hashval, cpath)
                        if self._progtrack:
                                filesz = int(misc.get_pkg_otw_size(action))
                                self._progtrack.download_add_progress(1, filesz)
                        return
                self.add_hash(hashval, action)
                if action.name == "signature":
                        for c in action.get_chain_certs():
                                # file_done does some magical accounting for
                                # files which may have been downloaded multiple
                                # times but this accounting breaks when the
                                # chain certificates are involved.  For now,
                                # adjusting the pkg size and csize for the
                                # action associated with the certificates solves
                                # the problem by working around the special
                                # accounting.  This fixes the problem because it
                                # tells file_done that no other data was
                                # expected for this hash of this action.
                                a = copy.copy(action)
                                # Copying the attrs separately is needed because
                                # otherwise the two copies of the actions share
                                # the dictionary.
                                a.attrs = copy.copy(action.attrs)
                                a.attrs["pkg.size"] = str(
                                    action.get_chain_size(c))
                                a.attrs["pkg.csize"] = str(
                                    action.get_chain_csize(c))
                                self.add_hash(c, a)

        def file_done(self, hashval, current_path):
                """Tell MFile that the transfer completed successfully."""

                totalsz = 0
                nactions = 0

                filesz = os.stat(current_path).st_size
                for action in self._hash[hashval]:
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
                nbytes = int(totalsz - filesz)
                if self._progtrack:
                        self._progtrack.download_add_progress((nactions - 1),
                            nbytes)

                self._final_copy(hashval, current_path)
                self.del_hash(hashval)

        def _final_copy(self, hashval, current_path):
                """Copy the file named by hashval from current_path
                to the final destination, decompressing, if necessary."""

                dest = os.path.join(self._final_dir, hashval)
                tmp_prefix = "%s." % hashval

                try:
                        os.makedirs(self._final_dir, mode=misc.PKG_DIR_MODE)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        if e.errno != errno.EEXIST:
                                raise

                try:
                        fd, fn = tempfile.mkstemp(dir=self._final_dir,
                            prefix=tmp_prefix)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                src = file(current_path, "rb")
                outfile = os.fdopen(fd, "wb")
                if self._decompress:
                        misc.gunzip_from_stream(src, outfile)
                else:
                        while True:
                                buf = src.read(64 * 1024)
                                if buf == "":
                                        break
                                outfile.write(buf)
                outfile.close()
                src.close()

                try:
                        os.chmod(fn, misc.PKG_FILE_MODE)
                        portable.rename(fn, dest)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

# The following two methods are to be used by clients without an Image that
# need to configure a transport and or publishers.

def setup_publisher(repo_uri, prefix, xport, xport_cfg,
    remote_prefix=False, remote_publishers=False, ssl_key=None, 
    ssl_cert=None):
        """Given transport 'xport' and publisher configuration 'xport_cfg'
        take the string that identifies a repository by uri in 'repo_uri'
        and create a publisher object.  The caller must specify the prefix.

        If remote_prefix is True, the caller will contact the remote host
        and use its publisher info to determine the publisher's actual prefix.

        If remote_publishers is True, the caller will obtain the prefix and
        repository information from the repo's publisher info."""


        if isinstance(repo_uri, list):
                repo = publisher.Repository(origins=repo_uri)
                repouri_list = repo_uri
        else:
                repouri_list = [publisher.RepositoryURI(repo_uri)]
                repo = publisher.Repository(origins=repouri_list)

        for origin in repo.origins:
                if origin.scheme == "https": 
                        origin.ssl_key = ssl_key
                        origin.ssl_cert = ssl_cert

        pub = publisher.Publisher(prefix=prefix, repository=repo)

        if not remote_prefix and not remote_publishers:
                xport_cfg.add_publisher(pub)
                return pub

        try:
                newpubs = xport.get_publisherdata(pub)
        except apx.UnsupportedRepositoryOperation:
                newpubs = None

        if not newpubs:
                xport_cfg.add_publisher(pub)
                return pub

        for p in newpubs:
                psr = p.repository

                if not psr:
                        p.repository = repo
                elif remote_publishers:
                        if not psr.origins:
                                for r in repouri_list:
                                        psr.add_origin(r)
                        elif repo not in psr.origins:
                                for i, r in enumerate(repouri_list):
                                        psr.origins.insert(i, r)
                else:
                        psr.origins = repouri_list

                if p.repository:
                        for origin in p.repository.origins:
                                if origin.scheme == \
                                    pkg.client.publisher.SSL_SCHEMES: 
                                        origin.ssl_key = ssl_key
                                        origin.ssl_cert = ssl_cert

                xport_cfg.add_publisher(p)

        # Return first publisher in list
        return newpubs[0]

def setup_transport():
        """Initialize the transport and transport configuration. The caller
        must manipulate the transport configuration and add publishers
        once it receives control of the objects."""

        xport_cfg = GenericTransportCfg()
        xport = Transport(xport_cfg)

        return xport, xport_cfg
