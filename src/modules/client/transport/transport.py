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

import sys
import os
import httplib
import statvfs
import errno
import zlib

import pkg.fmri

import pkg.client.api_errors as apx
import pkg.client.imageconfig as imageconfig
import pkg.client.publisher as publisher
import pkg.client.transport.engine as engine
import pkg.client.transport.exception as tx
import pkg.client.transport.repo as trepo
import pkg.client.transport.stats as tstats
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.portable as portable
import pkg.updatelog as updatelog

from pkg.actions import MalformedActionError
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
                self.stats = tstats.RepoChooser()

        def __setup(self):
                self.__engine = engine.CurlTransportEngine(self)

                # Configure engine's user agent based upon img configuration
                ua = misc.user_agent_str(self.__img,
                    global_settings.client_name)
                self.__engine.set_user_agent(ua)

                self.__repo_cache = trepo.RepoCache(self.__engine)

        def reset(self):
                """Resets the transport.  This needs to be done
                if an install plan has been canceled and needs to
                be restarted.  This clears the state of the
                transport and its associated components."""

                if not self.__engine:
                        # Not configured, just init and return
                        self.__setup()
                        return

                self.__engine.reset()
                self.__repo_cache.clear_cache()

        def do_search(self, pub, data):
                """Perform a search request.  Returns a file-like object
                that contains the search results.  Callers need to catch
                transport exceptions that this object may generate."""

                failures = tx.TransportFailures()
                fobj = None
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = None

                if isinstance(pub, publisher.Publisher):
                        header = self.__build_header(uuid=self.__get_uuid(pub))

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self.captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):

                        try:
                                fobj = d.do_search(data, header)
                                fobj._prime()
                                return fobj

                        except tx.TransportProtoError, e:
                                if e.code == httplib.NOT_FOUND:
                                        raise apx.UnsupportedSearchError(e.url,
                                            "Search/1")
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

        def get_catalog(self, pub, ts=None):
                """Get the catalog for the specified publisher.  If
                ts is defined, request only changes newer than timestamp
                ts."""

                failures = tx.TransportFailures()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(uuid=self.__get_uuid(pub))
                croot = pub.meta_root

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self.captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):

                        repostats = self.stats[d.get_url()]

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:

                                resp = d.get_catalog(ts, header)

                                updatelog.recv(resp, croot, ts, pub)

                                return

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

        def get_datastream(self, fmri, fhash):
                """Given a fmri, and fhash, return a data stream for the remote
                object.

                Since the caller handles the streaming object, instead
                of having the transport manage it, the caller must catch
                TransportError and perform any retry logic that is desired.
                """

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                pub_prefix = fmri.get_publisher()
                pub = self.__img.get_publisher(pub_prefix)
                header = self.__build_header(uuid=self.__get_uuid(pub))

                for d in self.__gen_repos(pub, retry_count):

                        try:
                                resp = d.get_datastream(fhash, header)
                                return resp

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise
                raise failures

        def touch_manifest(self, fmri, intent=None):
                """Touch a manifest.  This operation does not
                return the manifest's content.  The FMRI is given
                as fmri.  An optional intent string may be supplied
                as intent."""

                failures = tx.TransportFailures()
                pub_prefix = fmri.get_publisher()
                pub = self.__img.get_publisher(pub_prefix)
                mfst = fmri.get_url_path()
                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                header = self.__build_header(intent=intent,
                    uuid=self.__get_uuid(pub))

                for d in self.__gen_origins(pub, retry_count):

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:
                                d.touch_manifest(mfst, header)
                                return

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                else:
                                        raise

                raise failures

        def get_manifest(self, fmri, excludes=misc.EmptyI, intent=None):
                """Given a fmri, and optional excludes, return a manifest
                object."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                pub_prefix = fmri.get_publisher()
                pub = self.__img.get_publisher(pub_prefix)
                mfst = fmri.get_url_path()
                mcontent = None
                header = self.__build_header(intent=intent,
                    uuid=self.__get_uuid(pub))

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self.captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):

                        repostats = self.stats[d.get_url()]

                        try:
                                resp = d.get_manifest(mfst, header)
                                mcontent = resp.read()
                                m = manifest.CachedManifest(fmri,
                                    self.__img.pkgdir,
                                    self.__img.cfg_cache.preferred_publisher,
                                    excludes, mcontent)

                                return m

                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                        mcontent = None
                                else:
                                        raise
 
                        except MalformedActionError, e:
                                repostats.record_error()
                                te = tx.TransferContentException(
                                    d.get_url(), reason=str(e))
                                failures.append(te)

                raise failures

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

                if len(header) == 0:
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
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EROFS:
                                        raise apx.PermissionsException(
                                            e.filename)
                                else:
                                        raise tx.TransportOperationError(
                                            "Unable to make directory: %s" % e)

        def _get_files(self, mfile):
                """Perform an operation that gets multiple files at once.
                A mfile object contains information about the multiple-file
                request that will be performed."""

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = []
                filelist = mfile.keys()
                pub = mfile.get_publisher()
                progtrack = mfile.get_progtrack()
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # download_dir is temporary download path.  Completed_dir
                # is the cache where valid content lives.
                completed_dir = self.__img.cached_download_dir()
                download_dir = self.__img.incoming_download_dir()

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self.captive_portal_test()

                # Check if the download_dir exists.  If it doesn't create
                # the directories.
                self._makedirs(download_dir)

                # Call setup if the transport isn't configured yet.
                if not self.__engine:
                        self.__setup()

                # Call statvfs to find the blocksize of download_dir's
                # filesystem.
                try:
                        destvfs = os.statvfs(download_dir)
                        # set the file buffer size to the blocksize of our filesystem
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

                for d in self.__gen_repos(pub, retry_count):

                        failedreqs = []
                        repostats = self.stats[d.get_url()]

                        # This returns a list of transient errors
                        # that occurred during the transport operation.
                        # An exception handler here isn't necessary
                        # unless we want to supress a permanant failure.
                        errlist = d.get_files(filelist, download_dir,
                            progtrack, header)

                        for e in errlist:
                                req = getattr(e, "request", None)
                                if req:
                                        failedreqs.append(req)
                                        failures.append(e)
                                else:
                                        raise e

                        if len(failedreqs) > 0:
                                success = filter(lambda x: x not in failedreqs,
                                    filelist)
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
                                        repostats.record_error()
                                        failedreqs.append(s)
                                        failures.append(e)
                                        if not filelist:
                                                filelist = failedreqs
                                        continue

                                final_path = os.path.normpath(
                                    os.path.join(completed_dir,
                                    misc.hash_file_name(s)))
                                finaldir = os.path.dirname(final_path)

                                self._makedirs(finaldir)
                                portable.rename(dl_path, final_path)

                                mfile.make_openers(s, final_path)

                        # Return if everything was successful
                        if not filelist and len(errlist) == 0:
                                return

                if len(failedreqs) > 0 and len(failures) > 0:
                        failures = filter(lambda x: x.request in failedreqs,
                            failures)
                        tfailurex = tx.TransportFailures()
                        for f in failures:
                                tfailurex.append(f)
                        raise tfailurex

        def get_versions(self, pub):
                """Query the publisher's origin servers for versions
                information.  Return a dictionary of "name":"versions" """

                retry_count = global_settings.PKG_CLIENT_MAX_TIMEOUT
                failures = tx.TransportFailures()
                verlines = None
                header = self.__build_header(uuid=self.__get_uuid(pub))

                # If captive portal test hasn't been executed, run it
                # prior to this operation.
                self.captive_portal_test()

                for d in self.__gen_origins(pub, retry_count):

                        # If a transport exception occurs,
                        # save it if it's retryable, otherwise
                        # raise the error to a higher-level handler.
                        try:
                                resp = d.get_versions(header)
                                verlines = resp.readlines()

                                return dict(
                                    s.split(None, 1)
                                    for s in (l.strip() for l in verlines)
                                )
         
                        except tx.TransportException, e:
                                if e.retryable:
                                        failures.append(e)
                                        verlines = None
                                else:
                                        raise
                        except ValueError:
                                raise apx.InvalidDepotResponseException(
                                    pub["origin"],
                                    "Unable to parse server response")

                raise failures

        def __gen_origins(self, pub, count):
                """The pub argument may either be a Publisher or a
                RepositoryURI object."""

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
                                yield self.__repo_cache.new_repo(rs, ruri)

        def __gen_repos(self, pub, count):

                if not self.__engine:
                        self.__setup()

                for i in xrange(count):
                        repo = pub.selected_repository
                        rslist = self.stats.get_repostats(repo.mirrors)
                        for rs, ruri in rslist:
                                yield self.__repo_cache.new_repo(rs, ruri)
                        rslist = self.stats.get_repostats(repo.origins)
                        for rs, ruri in rslist:
                                yield self.__repo_cache.new_repo(rs, ruri)

        def valid_publisher_test(self, pub):
                """Test that the publisher supplied in pub actually
                points to a valid packaging server."""

                try:
                        vd = self.get_versions(pub)
                except tx.TransportException, e:
                        # Failure when contacting server.  Report
                        # this as an error.
                        raise apx.InvalidDepotResponseException(pub["origin"],
                            "Transport errors encountered when trying to "
                            "contact depot server.\nReported the following "
                            "errors:\n%s" % e)

                if not self._valid_versions_test(vd):
                        raise apx.InvalidDepotResponseException(pub["origin"],
                            "Invalid or unparseable version information.")

                return True

        def captive_portal_test(self):
                """A captive portal forces a HTTP client on a network
                to see a special web page, usually for authentication
                purposes.  (http://en.wikipedia.org/wiki/Captive_portal)."""

                if self.__portal_test_executed:
                        return

                self.__portal_test_executed = True
                vd = None

                for pub in self.__img.gen_publishers():
                        try:
                                vd = self.get_versions(pub)
                        except tx.TransportException:
                                # Encountered a transport error while
                                # trying to contact this publisher.
                                # Pick another publisher instead.
                                continue

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
                                    for v in versdict["versions"].split()
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

                publisher = self.__img.get_publisher(fmri.get_publisher())
                mfile = MultiFile(publisher, self, progtrack, ccancel)

                return mfile

        def _action_cached(self, action):
                """If a file with the name action.hash is cached,
                and if it has the same content hash as action.chash,
                then return the path to the file.  If the file can't
                be found, return None."""

                hashval = action.hash

                cache_path = os.path.normpath(os.path.join(
                    self.__img.cached_download_dir(),
                    misc.hash_file_name(hashval)))

                try:
                        if os.path.exists(cache_path):
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


class MultiFile(object):
        """A transport object for performing multi-file requests
        using pkg actions.  This takes care of matching the publisher
        with the actions, and performs the download and content
        verification necessary to assure correct content installation."""

        def __init__(self, pub, xport, progtrack, ccancel):
                """Supply the destination publisher in the pub argument.
                The transport object should be passed in xport."""

                self._publisher = pub
                self._transport = xport
                self._progtrack = progtrack
                # Add the check_cancelation to the progress tracker
                self._progtrack.check_cancelation = ccancel
                self._fhash = { }

        def __getitem__(self, key):
                return self._fhash[key]

        def __contains__(self, key):
                return key in self._fhash

        def add_action(self, action):
                """The multiple file retrieval operation is asynchronous.
                Add files to retrieve with this function.  Supply the
                publisher in pub and the list of files in filelist.
                Wait for the operation by calling waitFiles."""

                cachedpath = self._transport._action_cached(action)
                if cachedpath:
                        action.data = self._make_opener(cachedpath)
                        filesz = int(misc.get_pkg_otw_size(action))
                        self._progtrack.download_add_progress(1, filesz)
                        return

                hashval = action.hash

                # Each fhash key accesses a list of one or more actions.  If we
                # already have a key in the dictionary, get the list and append
                # the action to it.  Otherwise, create a new list with the first
                # action.
                if hashval in self._fhash:
                        self._fhash[hashval].append(action)
                else:
                        self._fhash[hashval] = [ action ]

        def del_hash(self, hashval):
                """Remove the hashval from the dictionary, if it exists."""

                if hashval in self._fhash:
                        del self._fhash[hashval]

        def get_publisher(self):
                """Return the publisher object that will be used
                for this MultiFile request."""

                return self._publisher

        def get_progtrack(self):
                """Return the progress tracker object for this MFile,
                if it has one."""

                return self._progtrack

        def keys(self):
                """Return a list of the keys in the fhash."""

                return self._fhash.keys()

        @staticmethod
        def _make_opener(filepath):
                def opener():
                        f = open(filepath, "rb")
                        return f
                return opener                                

        def make_openers(self, hashval, path):
                """Find each action associated with the hash value hashval.
                Create an opener that points to the file at path for the
                action's data method."""

                totalsz = 0
                nactions = 0

                filesz = os.stat(path).st_size

                for action in self._fhash[hashval]:
                        action.data = self._make_opener(path)
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

                if len(self._fhash) > 0:
                        self._transport._get_files(self)

