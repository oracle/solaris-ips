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

#
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import urllib
import urllib2
import httplib
import socket
import time
import sha
import zlib
from tarfile import ReadError

import pkg.pkgtarfile as ptf
import pkg.portable as portable
import pkg.fmri
import pkg.client.api_errors as api_errors
import pkg.misc as misc
from pkg.client import global_settings
from pkg.misc import versioned_urlopen
from pkg.misc import hash_file_name
from pkg.misc import get_pkg_otw_size
from pkg.misc import TransportException
from pkg.misc import TransportFailures
from pkg.misc import TransferTimedOutException
from pkg.misc import TransferContentException
from pkg.misc import InvalidContentException
from pkg.misc import TruncatedTransferException
from pkg.misc import retryable_http_errors
from pkg.misc import retryable_socket_errors

class FileList(object):
        """A FileList maintains mappings between files and Actions.
        The list is built with knowledge of the Image and the PackagePlan's
        associated actions.

        The FileList is responsible for downloading the files needed by the
        PkgPlan from the repository. Once downloaded, the FileList generates
        the appropriate opener and closer for the actions that it processed.  By
        downloading files in a group, it is possible to achieve better
        performance.  This is because the FileList asks for the files to be
        sent in groups, instead of individual HTTP GET's.

        The caller may limit the maximum number of bytes of content in a
        FileList by specifying maxbytes when the object is constructed.
        If the caller sets maxbytes to 0, the size of the list is assumed
        to be infinite."""

        #
        # This value can be tuned by external callers to adjust the
        # default "maxbytes" value for a file list.  This value should be
        # tuned to the lowest value which provides "good enough" performance;
        # tuning beyond 1MB has not in our experiments thus far yielded more
        # than a token speedup-- at the expense of interactivity.
        #
        maxbytes_default = 1024 * 1024

        def __init__(self, image, fmri, progtrack, check_cancelation,
            maxbytes=None):
                """
                Create a FileList object for the specified image and pkgplan.
                """

                self.image = image
                self.fmri = fmri
                self.progtrack = progtrack
                self.fhash = { }

                if maxbytes is None:
                        self.maxbytes = FileList.maxbytes_default
                else:
                        self.maxbytes = maxbytes

                self.actual_bytes = 0
                self.actual_nfiles = 0
                self.effective_bytes = 0
                self.effective_nfiles = 0

                if fmri:
                        auth, pkg_name, version = self.fmri.tuple()

                        self.authority = pkg.fmri.strip_auth_pfx(auth)
                        self.ssl_tuple = self.image.get_ssl_credentials(auth)
                        self.uuid = self.image.get_uuid(self.authority)
                else:
                        self.authority = None
                        self.ssl_tuple = None
                        self.uuid = None

                self.ds = None
                self.url = None
                self.check_cancelation = check_cancelation

        def add_action(self, action):
                """Add the specified action to the filelist.  The action
                must name a file that can be retrieved from the repository.

                This method will pull cached content from the download
                directory, if it's available."""

                # Check if we've got a cached version of the file before
                # trying to add it to the list.  If a cached version is present,
                # create the opener and return.

                hashval = action.hash
                cache_path = os.path.normpath(os.path.join(
                    self.image.cached_download_dir(),
                    hash_file_name(hashval)))

                try:
                        if os.path.exists(cache_path):
                                action.data = self._make_opener(cache_path)
                                bytes = get_pkg_otw_size(action)

                                self._verify_content(action, cache_path)
                                self.progtrack.download_add_progress(1, bytes)

                                return
                except InvalidContentException:
                        # If the content in the cache doesn't match the hash of
                        # the action, verify will have already purged the item
                        # from the cache.  Reset action.data to None and have
                        # _add_action download the file.
                        action.data = None

                while self._is_full():
                        self._do_get_files()

                self._add_action(action)
                
        def _add_action(self, action):
                """Add the specified action to the filelist.  The action
                must name a file that can be retrieved from the repository.

                This method gets invoked when we must go over the network
                to retrieve file content.

                This is a private method which performs the majority of the
                work for add_content()."""

                if not hasattr(action, "hash"):
                        raise FileListException, "Invalid action type"

                if self._is_full():
                        raise FileListFullException

                hashval = action.hash

                # Each fhash key accesses a list of one or more actions.  If we
                # already have a key in the dictionary, get the list and append
                # the action to it.  Otherwise, create a new list with the first
                # action.
                if hashval in self.fhash:
                        l = self.fhash[hashval]
                        l.append(action)
                else:
                        self.fhash[hashval] = [ action ]
                        self.actual_nfiles += 1
                        self.actual_bytes += get_pkg_otw_size(action)

                # Regardless of whether files map to the same hash, we
                # also track the total (effective) size and number of entries
                # in the flist, for reporting purposes.
                self.effective_nfiles += 1
                self.effective_bytes += get_pkg_otw_size(action)

        def _clear_mirror(self):
                """Clear any selected DepotStatus and URL assocated with
                a mirror selection."""

                self.ds = None
                self.url = None

        def _del_hash(self, hash):
                """Given the supplied content hash, remove the entry
                from the flist's dictionary and adjust the counters
                accordingly."""

                try:
                        act_list = self.fhash[hash]
                except KeyError:
                        return

                pkgsz = get_pkg_otw_size(act_list[0])
                nactions = len(act_list)
        
                # Update the actual counts by subtracting the first
                # item in the list
                self.actual_nfiles -= 1
                self.actual_bytes -= pkgsz

                # Now update effective count
                self.effective_nfiles -= nactions
                self.effective_bytes -= nactions * pkgsz

                # Now delete the entry out of the dictionary
                del self.fhash[hash] 


        # XXX detect missing size and warn

        def _do_get_files(self):
                """A wrapper around _get_files.  This handles exceptions
                that might occur and deals with timeouts."""

                num_mirrors = self.image.num_mirrors(self.authority)
                max_timeout = global_settings.PKG_TIMEOUT_MAX
                if num_mirrors > 0:
                        retry_count = max_timeout * (num_mirrors + 1)
                else:
                        retry_count = max_timeout

                files_extracted = 0
                nfiles = self._get_nfiles()
                nbytes = self._get_nbytes()
                chosen_mirrors = set()
                ts = 0
                failures = TransportFailures()

                while files_extracted == 0:
                        try:
                                self._pick_mirror(chosen_mirrors)
                                ts = time.time()

                                fe = self._get_files()
                                files_extracted += fe

                        except TransportException, e:
                                retry_count -= 1
                                self.ds.record_error()
                                self._clear_mirror()

                                failures.append(e)
                                if retry_count <= 0:
                                        raise failures
                        else:
                                ts = time.time() - ts
                                self.ds.record_success(ts)

                nfiles -= self._get_nfiles()
                nbytes -= self._get_nbytes()
                self.progtrack.download_add_progress(nfiles, nbytes)

        def _extract_file(self, tarinfo, tar_stream, download_dir):
                """Given a tarinfo object, extract that onto the filesystem
                so it can be installed."""

                completed_dir = self.image.cached_download_dir()

                hashval = tarinfo.name

                # Set the perms of the temporary file. The file must
                # be writable so that the mod time can be changed on Windows
                tarinfo.mode = 0600
                tarinfo.uname = "root"
                tarinfo.gname = "root"

                if self.check_cancelation():
                        raise api_errors.CanceledException

                # XXX catch IOError if tar stream closes inadvertently?
                tar_stream.extract_to(tarinfo, download_dir, hashval)

                # Now that the file has been successfully extracted, move
                # it to the cached content directory.
                dl_path = os.path.join(download_dir, hashval)
                final_path = os.path.normpath(os.path.join(completed_dir,
                    hash_file_name(hashval)))

                # Check that hashval is in the list of files we requested
                try:
                        l = self.fhash[hashval]
                except KeyError:
                        # If the key isn't in the dictionary, the server sent us
                        # a file we didn't ask for.  In this case, we can't
                        # create an opener for it, nor should we hold onto it.
                        os.remove(dl_path)
                        return

                # Verify downloaded content
                self._verify_content(l[0], dl_path)

                if not os.path.exists(os.path.dirname(final_path)):
                        os.makedirs(os.path.dirname(final_path))

                # Content has been verified and was requested from server.
                # Move into content cache
                portable.rename(dl_path, final_path)

                # assign opener to actions in the list
                for action in l:
                        action.data = self._make_opener(final_path)

                # Remove successfully extracted items from the hash
                # and adjust bean counters
                self._del_hash(hashval)


        def flush(self):
                """Ensure that the actions added to the filelist have had
                their data retrieved from the depot."""
                while self._list_size() > 0:
                        self._do_get_files()

        def _get_files(self):
                """Instruct the FileList object to download the files
                for the actions that have been associated with this object.

                This routine will raise a FileListException if the server
                does not support filelist.  Callers of get_files should
                consider catching this exception."""

                req_dict = { }
                tar_stream = None
                files_extracted = 0

                url_prefix = self.url

                download_dir = self.image.incoming_download_dir()
                # Make sure the download directory is there before we start
                # retrieving and extracting files.
                try:
                        if not os.path.exists(download_dir):
                                os.makedirs(download_dir)
                except OSError, (errno, errorstr):
                        raise RuntimeError("unable to create " \
                                "download directory %s: %s" % 
                                (download_dir, errorstr))

                for i, k in enumerate(self.fhash.keys()):
                        fstr = "File-Name-%s" % i
                        req_dict[fstr] = k

                req_str = urllib.urlencode(req_dict)

                try:
                        f, v = versioned_urlopen(url_prefix, "filelist", [0],
                            data=req_str, ssl_creds=self.ssl_tuple,
                            imgtype=self.image.type, uuid=self.uuid)
                except RuntimeError:
                        raise FileListRetrievalError, "No server-side support" 
                except urllib2.HTTPError, e:
                        # Must check for HTTPError before URLError
                        self.image.cleanup_downloads()
                        if e.code in retryable_http_errors:
                                raise TransferTimedOutException(url_prefix,
                                    "%d - %s" % (e.code, e.msg))

                        raise FileListRetrievalError("Could not retrieve"
                            " filelist from '%s'\nHTTPError code: %d - %s" % 
                            (url_prefix, e.code, e.msg))
                except urllib2.URLError, e:
                        self.image.cleanup_downloads()
                        if isinstance(e.args[0], socket.timeout):
                                raise TransferTimedOutException(url_prefix,
                                    e.reason)
                        elif isinstance(e.args[0], socket.error):
                                sockerr = e.args[0]
                                if isinstance(sockerr.args, tuple) and \
                                    sockerr.args[0] in retryable_socket_errors:
                                        raise TransferContentException(
                                            url_prefix,
                                            "Retryable socket error: %s" %
                                            e.reason)
                                else:
                                        raise FileListRetrievalError(
                                            "Could not retrieve filelist from"
                                            " '%s'\nURLError, reason: %s" %
                                            (url_prefix, e.reason))

                        raise FileListRetrievalError("Could not retrieve"
                            " filelist from '%s'\nURLError reason: %d" % 
                            (url_prefix, e.reason))
                except (ValueError, httplib.IncompleteRead):
                        self.image.cleanup_downloads()
                        raise TransferContentException(url_prefix,
                            "Incomplete Read from remote host")
                except KeyboardInterrupt:
                        self.image.cleanup_downloads()
                        raise
                except Exception, e:
                        self.image.cleanup_downloads()
                        raise FileListRetrievalError("Could not retrieve"
                            " filelist from '%s'\nException: str:%s repr:%s" %
                            (url_prefix, e, repr(e)))


                # Exception handling here is a bit complicated.  The finally
                # block makes sure we always close our file objects.  If we get
                # a socket.timeout we may have gotten an error in the middle of
                # downloading a file. In that case, delete the incoming files we
                # were processing.  They were not successfully retrieved.
                try:
                        try:
                                tar_stream = ptf.PkgTarFile.open(mode = "r|",
                                    fileobj = f)
                                for info in tar_stream:
                                        self._extract_file(info, tar_stream,
                                            download_dir)
                                        files_extracted += 1
                        except socket.timeout, e:
                                self.image.cleanup_downloads()
                                raise TransferTimedOutException(url_prefix)
                        except socket.error, e:
                                self.image.cleanup_downloads()
                                if isinstance(e.args, tuple) and \
                                    e.args[0] in retryable_socket_errors:
                                        raise TransferContentException(
                                            url_prefix,
                                            "Retryable socket error: %s" % e)
                                else:
                                        raise FileListRetrievalError(
                                            "Could not retrieve filelist from"
                                            " '%s'\nsocket error, reason: %s" %
                                            (url_prefix, e))
                        except (ValueError, httplib.IncompleteRead):
                                self.image.cleanup_downloads()
                                raise TransferContentException(url_prefix,
                                    "Incomplete Read from remote host")
                        except ReadError:
                                self.image.cleanup_downloads()
                                raise TransferContentException(url_prefix,
                                    "Read error on tar stream")
                        except EnvironmentError, e:
                                self.image.cleanup_downloads()
                                raise FileListRetrievalError(
                                    "Could not retrieve filelist from '%s'\n"
                                    "Exception: str:%s repr:%s" %
                                    (url_prefix, e, repr(e)))
                finally:
                        if tar_stream:
                                tar_stream.close()
                        f.close()

                return files_extracted

        def _get_nbytes(self):
                return self.effective_bytes

        def _get_nfiles(self):
                return self.effective_nfiles

        def _is_full(self):
                """Returns true if the FileList object has filled its
                allocated slots and can no longer accept new actions."""

                if self.maxbytes > 0 and self.actual_bytes >= self.maxbytes:
                        return True

                return False

        def _list_size(self):
                """Returns the current number of files in the filelist."""

                return len(self.fhash)

        @staticmethod
        def _make_opener(filepath):
                def opener():
                        f = open(filepath, "rb")
                        return f
                return opener                                

        def _pick_mirror(self, chosen_set=None):
                """If we don't already have a DepotStatus or a URL,
                select a mirror, populate the DepotStatus, and choose a URL."""

                if self.ds and self.url:
                        return
                elif self.ds:
                        self.url = self.ds.url
                else:
                        self.ds = self.image.select_mirror(self.authority,
                            chosen_set)
                        self.url = self.ds.url
                        chosen_set.add(self.ds)

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
                                hash = misc.gunzip_from_stream(ifile, ofile)
                        except zlib.error, e:
                                os.remove(filepath)
                                raise InvalidContentException(path,
                                    "zlib.error:%s" %
                                    (" ".join([str(a) for a in e.args])))

                        ifile.close()
                        ofile.close()

                        if action.hash != hash:
                                os.remove(filepath)
                                raise InvalidContentException(action.path,
                                    "hash failure:  expected: %s"
                                    "computed: %s" % (action.hash, hash))
                        return

                cfile = open(filepath, "rb")
                cdata = cfile.read()
                cfile.close()
                hashobj = sha.new(cdata)
                newhash = hashobj.hexdigest()
                cdata = None

                if chash != newhash:
                       os.remove(filepath)
                       raise InvalidContentException(path,
                           "chash failure: expected: %s computed: %s" %
                           (chash, newhash))


class FileListException(Exception):
        def __init__(self, args=None):
                Exception.__init__(self)
                self.args = args

class FileListFullException(FileListException):
        pass

class FileListRetrievalError(FileListException):
        """Used when filelist retrieval fails"""
        def __init__(self, data):
                FileListException.__init__(self)
                self.data = data

        def __str__(self):
                return str(self.data)
