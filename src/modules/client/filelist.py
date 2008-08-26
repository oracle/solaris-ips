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
from tarfile import ReadError

import pkg.pkgtarfile as ptf
import pkg.portable as portable
import pkg.fmri
from pkg.misc import versioned_urlopen
from pkg.misc import hash_file_name
from pkg.misc import get_pkg_otw_size
from pkg.misc import TransferTimedOutException
from pkg.misc import TransferContentException
from pkg.misc import InvalidContentException
from pkg.misc import MAX_TIMEOUT_COUNT

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

        def __init__(self, image, fmri, progtrack, maxbytes=None):
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
                else:
                        self.authority = None
                        self.ssl_tuple = None

                self.ds = None
                self.url = None

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

                if os.path.exists(cache_path):
                        action.data = self._make_opener(cache_path)
                        bytes = get_pkg_otw_size(action)

                        self._verify_content(action, cache_path)

                        self.progtrack.download_adjust_goal(0, -1, -bytes)

                        return

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

                retry_count = MAX_TIMEOUT_COUNT
                files_extracted = 0

                nfiles = self._get_nfiles()
                nbytes = self._get_nbytes()
                chosen_mirrors = set()
                ts = 0

                while files_extracted == 0:
                        try:
                                self._pick_mirror(chosen_mirrors)
                                ts = time.time()

                                fe = self._get_files()
                                files_extracted += fe

                        except (TransferTimedOutException,
                            TransferContentException, InvalidContentException):

                                retry_count -= 1
                                self.ds.record_error()
                                self._clear_mirror()

                                if retry_count <= 0:
                                        raise TransferTimedOutException
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

                # XXX catch IOError if tar stream closes inadvertently?
                tar_stream.extract_to(tarinfo, download_dir, hashval)

                # Now that the file has been successfully extracted, move
                # it to the cached content directory.
                final_path = os.path.normpath(os.path.join(completed_dir,
                    hash_file_name(hashval)))

                if not os.path.exists(os.path.dirname(final_path)):
                        os.makedirs(os.path.dirname(final_path))

                portable.rename(os.path.join(download_dir, hashval), final_path)

                # assign opener to actions in the list
                try:
                        l = self.fhash[hashval]
                except KeyError:
                        # If the key isn't in the dictionary, the server sent us
                        # a file we didn't ask for.  In this case, we can't
                        # create an opener for it, nor should we leave it in the
                        # cache.
                        os.remove(final_path)
                        return

                self._verify_content(l[0], final_path)

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
                            data = req_str, ssl_creds = self.ssl_tuple,
                            imgtype = self.image.type)
                except RuntimeError:
                        raise FileListException, "No server-side support" 
                except urllib2.HTTPError, e:
                        # Must check for HTTPError before URLError
                        if e.code == httplib.REQUEST_TIMEOUT:
                                raise TransferTimedOutException
                        raise
                except urllib2.URLError, e:
                        if len(e.args) == 1 and \
                            isinstance(e.args[0], socket.timeout):
                                self.image.cleanup_downloads()
                                raise TransferTimedOutException
                        raise

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
                        except socket.timeout:
                                self.image.cleanup_downloads()
                                raise TransferTimedOutException
                        except ReadError:
                                raise TransferContentException

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
                if not chash:
                        return

                cfile = open(filepath, "rb")
                cdata = cfile.read()
                cfile.close()
                hashobj = sha.new(cdata)
                newhash = hashobj.hexdigest()
                cdata = None

                if chash != newhash:
                       os.remove(filepath)
                       raise InvalidContentException(action, newhash)


class FileListException(Exception):
        def __init__(self, args=None):
                self.args = args

class FileListFullException(FileListException):
        pass
