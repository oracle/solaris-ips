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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import os
import exceptions
import httplib
import urllib
import urllib2
import urlparse
import tarfile
import shutil
import errno

import pkg.client.image
import pkg.actions as actions
import pkg.actions.generic as generic
import pkg.fmri as fmri

class FileList(object):
        """A FileList maintains mappings between files and Actions.
        The list is built with knowledge of the Image and the PackagePlan's
        associated actions.

        The FileList is responsible for downloading the files needed by the
        PkgPlan from the repository. Once downloaded, the FileList generates
        the appropriate opener for the actions that it processed.  By
        downloading files in a group, it is possible to achieve better
        performance.  This is because the FileList asks for the files to be
        sent in groups, instead of individual HTTP GET's.

        The caller may limit the maximum number of entries in a FileList
        by specifying maxents when the object is constructed.  If the caller
        sets maxents to 0, the size of the list is assumed to be infinite."""

        maxfiles = 64

        def __init__(self, image, fmri, maxents=None):
                """
                Create a FileList object for the specified image and pkgplan.
                """

                self.image = image
                self.fmri = fmri
                self.maxents = maxents
                if self.maxents is None:
                        self.maxents = self.maxfiles
                self.fhash = { }

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

        def get_files(self):
                """Instruct the FileList object to download the files
                for the actions that have been associated with this object.

                This routine will raise a FileListException if the server
                does not support filelist.  Callers of get_files should
                consider catching this exception."""

                req_dict = { }

                authority, pkg_name, version = self.fmri.tuple()
                url_prefix = self.image.get_url_by_authority(authority)
                url_fpath = "%s/filelist/" % url_prefix

                for i, k in enumerate(self.fhash.keys()):
                        fstr = "File-Name-%s" % i
                        req_dict[fstr] = k

                req_str = urllib.urlencode(req_dict)

                req = urllib2.Request(url = url_fpath, data = req_str)

                try:
                        f = urllib2.urlopen(req)
                except urllib2.HTTPError, e:
                        if int(e.code) >= 400:
                                raise FileListException, \
                                    "No server-side support" 
                        else:
                                raise

                tar_stream = tarfile.open(mode = "r|", fileobj = f)
                for info in tar_stream:
                        hashval = info.name
                        pkgnm = self.fmri.pkg_name
                        l = self.fhash[hashval]
                        act = l.pop()
                        path = act.attrs["path"]
                        imgroot = self.image.get_root()
                        # get directory and basename
                        dir, base = os.path.split(path)
                        # reconstruct path without basename
                        path = os.path.normpath(os.path.join(
                            imgroot, dir))

                        # XXX catch IOError if tar stream closes inadvertently?
                        tar_stream.extract(info, path)

                        # extract path is where the file now lives
                        # after the extract
                        extract_path = os.path.normpath(os.path.join(
                            path, info.name))

                        # Since the file hash value identifies the content, and
                        # not the file or package itself, generate temporary
                        # file names that are unique by package and file name.
                        # This ensures that each opener gets access to a unique
                        # file name that hasn't been manipulated by another
                        # action.

                        mvpath = os.path.normpath(os.path.join(
                            path, "." + pkgnm + "-" + base + "-" + hashval))
                         
                        os.rename(extract_path, mvpath)
                        
                        # assign opener
                        act.data = self._make_opener(mvpath)

                        # If there are more actions in the list, copy the
                        # extracted file to their paths, changing names as
                        # appropriate to maintain uniqueness
                        for action in l:
                                path = action.attrs["path"]
                                dir, base = os.path.split(path)
                                cpdir = os.path.normpath(os.path.join(
                                    imgroot, dir))
                                cppath = os.path.normpath(os.path.join(
                                    cpdir, "." + pkgnm + "-" + base \
                                    + "-" + hashval))
                                if not os.path.exists(cpdir):
                                        os.makedirs(cpdir)
                                shutil.copy(mvpath, cppath)
                                action.data = self._make_opener(cppath)

                tar_stream.close()
                f.close()

        def is_full(self):
                """Returns true if the FileList object has filled its
                allocated slots and can no longer accept new actions."""

                if self.maxents > 0 and len(self.fhash) >= self.maxents:
                        return True

                return False

        @staticmethod
        def _make_opener(filepath):
                def opener():
                        f = open(filepath, "rb")
                        os.unlink(filepath)
                        return f
                return opener                                



class FileListException(exceptions.Exception):
        def __init__(self, args=None):
                self.args = args
