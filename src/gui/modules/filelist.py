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
import pkg.portable as portable
from pkg.misc import hash_file_name
import pkg.client.filelist as filelist

class FileList(filelist.FileList):

        def __init__(self, progtrack, image, fmri, gui_thread = None, maxbytes = None):
                self.progtrack = progtrack
                self.gui_thread = gui_thread
                filelist.FileList.__init__(self, image, fmri, progtrack, \
                    maxbytes = maxbytes)


        def _extract_file(self, tarinfo, tar_stream, download_dir):
                """Given a tarinfo object, extract that onto the filesystem
                so it can be installed."""

                if self.gui_thread.is_cancelled():
                        self.image.cleanup_downloads()
                        raise CancelException

                completed_dir = self.image.cached_download_dir()

                hashval = tarinfo.name

                # Set the perms of the temporary file. The file must
                # be writable so that the mod time can be changed on Windows
                tarinfo.mode = 0600
                tarinfo.uname = "root"
                tarinfo.gname = "root"

                # Now that the file has been successfully extracted, move
                # it to the cached content directory.
                final_path = os.path.normpath(os.path.join(completed_dir,
                    hash_file_name(hashval)))

                # XXX catch IOError if tar stream closes inadvertently?
                tar_stream.extract_to(tarinfo, download_dir, hashval)
                # XXX Single file progress consumed by pkg.gui.installupdate
                file_path = self.fhash[hashval][0].attrs.get("path")
                self.progtrack.download_file_path(file_path)

                if not os.path.exists(os.path.dirname(final_path)):
                        os.makedirs(os.path.dirname(final_path))

                portable.rename(os.path.join(download_dir, hashval), final_path)

                # assign opener to actions in the list
                try:
                        lis = self.fhash[hashval]
                except KeyError:
                        # If the key isn't in the dictionary, the server sent us
                        # a file we didn't ask for.  In this case, we can't
                        # create an opener for it, nor should we leave it in the
                        # cache.
                        os.remove(final_path)
                        return

                self._verify_content(lis[0], final_path)

                for action in lis:
                        action.data = self._make_opener(final_path)

                # Remove successfully extracted items from the hash
                # and adjust bean counters
                self._del_hash(hashval)

                @staticmethod
                def _make_opener(filepath):
                        def opener():
                                if self.gui_thread.is_cancelled():
                                        self.image.cleanup_downloads()
                                        raise CancelException
                                file_op = open(filepath, "rb")
                                os.unlink(filepath)
                                return file_op
                        return opener

class CancelException(Exception):
        def __init__(self, args=None):
                Exception.__init__(self)
                self.args = args

class FileListException(Exception):
        def __init__(self, args = None):
                Exception.__init__(self)
                self.args = args
