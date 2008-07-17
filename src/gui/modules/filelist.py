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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import urllib
import pkg.pkgtarfile as ptf
import pkg.misc as misc
import pkg.client.filelist as filelist

class FileList(filelist.FileList):

        def __init__(self, progtrack, image, fmri, maxbytes = None):
                filelist.FileList.__init__(self, image, fmri, maxbytes = None)
                self.progtrack = progtrack

        def get_files(self, gui_thread = None):
                """Instruct the FileList object to download the files
                for the actions that have been associated with this object.
                This routine will raise a FileListException if the server
                does not support filelist.  Callers of get_files should
                consider catching this exception."""
                req_dict = { }
                authority, pkg_name, version = self.fmri.tuple()
                url_prefix = self.image.get_url_by_authority(authority)
                for i, k in enumerate(self.fhash.keys()):
                        fstr = "File-Name-%s" % i
                        req_dict[fstr] = k
                req_str = urllib.urlencode(req_dict)
                try:
                        f, v = misc.versioned_urlopen(url_prefix, "filelist", [0],
                            data = req_str)
                except RuntimeError:
                        raise FileListException, "No server-side support" 
                tar_stream = ptf.PkgTarFile.open(mode = "r|", fileobj = f)
                filelist_download_dir = self.image.get_download_dir()
                for info in tar_stream:
                        if gui_thread.is_cancelled():
                                tar_stream.close()
                                f.close()
                                self.image.cleanup_downloads()
                                return
                        hashval = info.name
                        pkgnm = self.fmri.get_dir_path(True)
                        l = self.fhash[hashval]
                        act = l.pop()
                        path = act.attrs["path"]
                        self.progtrack.download_file_path(path) 
                        imgroot = self.image.get_root()
                        # get directory and basename
                        dirname, base = os.path.split(path)
                        # reconstruct path without basename
                        path = os.path.normpath(os.path.join(
                            filelist_download_dir,
                            dirname))
                        # Since the file hash value identifies the content, and
                        # not the file or package itself, generate temporary
                        # file names that are unique by package and file name.
                        # This ensures that each opener gets access to a unique
                        # file name that hasn't been manipulated by another
                        # action.
                        filename =  "." + pkgnm + "-" + base + "-" + hashval
                        # Set the perms of the temporary file.
                        info.mode = 0400
                        info.uname = "root"
                        info.gname = "root"
                        # XXX catch IOError if tar stream closes inadvertently?
                        tar_stream.extract_to(info, path, filename)
                        # extract path is where the file now lives
                        # after being extracted
                        extract_path = os.path.normpath(os.path.join(
                            path, filename))
                        #self.progtrack.download_file_path(extract_path)
                        # assign opener
                        act.data = self._make_opener(extract_path)
                        # If there are more actions in the list, copy the
                        # extracted file to their paths, changing names as
                        # appropriate to maintain uniqueness
                        for action in l:
                                if gui_thread.is_cancelled():
                                        tar_stream.close()
                                        f.close()
                                        self.image.cleanup_downloads()
                                        return
                                path = action.attrs["path"]
                                self.progtrack.download_file_path(path)
                                dirname, base = os.path.split(path)
                                cpdir = os.path.normpath(os.path.join(
                                    filelist_download_dir,
                                    dirname))
                                cppath = os.path.normpath(os.path.join(
                                    cpdir, "." + pkgnm + "-" + base \
                                    + "-" + hashval))
                                if not os.path.exists(cpdir):
                                        os.makedirs(cpdir)
                                # we can use hardlink here
                                os.link(extract_path, cppath)
                                action.data = self._make_opener(cppath)
                tar_stream.close()
                f.close()

                @staticmethod
                def _make_opener(filepath, gui_thread = None):
                        def opener():
                                if gui_thread.is_cancelled():
                                        self.image.cleanup_downloads()
                                        return
                                f = open(filepath, "rb")
                                os.unlink(filepath)
                                return f
                        return opener   

class FileListException(Exception):
        def __init__(self, args = None):
                Exception.__init__(self)
                self.args = args
