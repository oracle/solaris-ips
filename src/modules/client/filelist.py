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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import urllib
import shutil
import stat

import pkg.pkgtarfile as ptf
import pkg.portable as portable
import pkg.fmri
from pkg.misc import emsg, hash_file_name, versioned_urlopen

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

        def __init__(self, image, fmri, maxbytes=None):
                """
                Create a FileList object for the specified image and pkgplan.
                """

                self.image = image
                self.fmri = fmri
                self.fhash = { }

                if maxbytes is None:
                        self.maxbytes = FileList.maxbytes_default
                else:
                        self.maxbytes = maxbytes

                self.actual_bytes = 0
                self.actual_nfiles = 0
                self.effective_bytes = 0
                self.effective_nfiles = 0

        def add_action(self, action):
                """Add the specified action to the filelist.  The action
                must name a file that can be retrieved from the repository."""

                if not hasattr(action, "hash"):
                        raise FileListException, "Invalid action type"

                if self.is_full():
                        raise FileListException, "FileList full"

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
                        self.actual_bytes += int(action.attrs.get("pkg.size", "0"))

                # Regardless of whether files map to the same hash, we
                # also track the total (effective) size and number of entries
                # in the flist, for reporting purposes.
                self.effective_nfiles += 1
                self.effective_bytes += int(action.attrs.get("pkg.size", "0"))

        # XXX detect missing size and warn

        def get_files(self):
                """Instruct the FileList object to download the files
                for the actions that have been associated with this object.

                This routine will raise a FileListException if the server
                does not support filelist.  Callers of get_files should
                consider catching this exception."""

                req_dict = { }

                authority, pkg_name, version = self.fmri.tuple()
                authority = pkg.fmri.strip_auth_pfx(authority)
                url_prefix = self.image.get_url_by_authority(authority)
                ssl_tuple = self.image.get_ssl_credentials(authority)

                for i, k in enumerate(self.fhash.keys()):
                        fstr = "File-Name-%s" % i
                        req_dict[fstr] = k

                req_str = urllib.urlencode(req_dict)

                try:
                        f, v = versioned_urlopen(url_prefix, "filelist", [0],
                            data = req_str, ssl_creds = ssl_tuple,
                            imgtype = self.image.type)
                except RuntimeError:
                        raise FileListException, "No server-side support" 

                tar_stream = ptf.PkgTarFile.open(mode = "r|", fileobj = f)

                filelist_download_dir = self.image.get_download_dir()

                for info in tar_stream:
                        hashval = info.name
                        pkgnm = self.fmri.get_dir_path(True)
                        l = self.fhash[hashval]
                        act = l.pop()
                        path = act.attrs["path"]
                        imgroot = self.image.get_root()

                        # Set the perms of the temporary file. The file must
                        # be writable so that the mod time can be changed on Windows
                        info.mode = 0600
                        info.uname = "root"
                        info.gname = "root"

                        # extract path is where the file lives
                        # after being extracted
                        extract_path = os.path.normpath(os.path.join(
                            filelist_download_dir, pkgnm,
                            hash_file_name(hashval)))
                        (dir, fname) = os.path.split(extract_path)
                        
                        # XXX catch IOError if tar stream closes inadvertently?
                        tar_stream.extract_to(info, dir, fname)

                        # assign opener
                        act.data = self._make_opener(extract_path)

                        # If there are more actions in the list, copy the
                        # extracted file to their paths, changing names as
                        # appropriate to maintain uniqueness
                        for action in l:
                                action.data = self._make_opener(extract_path)
                tar_stream.close()
                f.close()

        def is_full(self):
                """Returns true if the FileList object has filled its
                allocated slots and can no longer accept new actions."""

                if self.maxbytes > 0 and self.actual_bytes >= self.maxbytes:
                        return True

                return False

        def get_nbytes(self):
                return self.effective_bytes

        def get_nfiles(self):
                return self.effective_nfiles

        @staticmethod
        def _make_opener(filepath):
                def opener():
                        f = open(filepath, "rb")
                        return f
                return opener                                

        @staticmethod
        def _make_cleaner(filepath):
                def cleaner():
                        try:
                               # Make file writable so it can be deleted
                               os.chmod(filepath, stat.S_IWRITE|stat.S_IREAD)
                               os.unlink(filepath)
                        except EnvironmentError, e:
                                emsg("EnvError in cleaner", e)
                                pass
                return cleaner                                

class FileListException(Exception):
        def __init__(self, args=None):
		Exception.__init__(self)
                self.args = args
