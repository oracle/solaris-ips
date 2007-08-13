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

"""module describing a file packaging object

This module contains the FileAction class, which represents a file-type
packaging object."""

import os
import grp
import pwd
import errno

import generic

class FileAction(generic.Action):
        """Class representing a file-type packaging object."""

        name = "file"
        attributes = ("mode", "owner", "group", "path")
        key_attr = "path"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"

        def install(self, image, orig):
                """Client-side method that installs a file."""
                path = self.attrs["path"]
                mode = int(self.attrs["mode"], 8)
                owner = pwd.getpwnam(self.attrs["owner"]).pw_uid
                group = grp.getgrnam(self.attrs["group"]).gr_gid

                final_path = os.path.normpath(os.path.sep.join(
                    (image.get_root(), path)))

                # If we're upgrading, extract the attributes from the old file.
                if orig:
                        omode = int(orig.attrs["mode"], 8)
                        oowner = pwd.getpwnam(orig.attrs["owner"]).pw_uid
                        ogroup = grp.getgrnam(orig.attrs["group"]).gr_gid

                # If we're not upgrading, or the file contents have changed,
                # retrieve the file and write it to a temporary location.
                if not orig or orig.hash != self.hash:
                        temp = os.path.normpath(os.path.sep.join(
                            (image.get_root(), path + "." + self.hash)))

                        stream = self.data()
                        tfile = file(temp, "wb")
                        shasum = generic.gunzip_from_stream(stream, tfile)

                        tfile.close()
                        stream.close()

                        # XXX Should throw an exception if shasum doesn't match
                        # self.hash
                else:
                        temp = final_path

                if not orig or omode != mode:
                        os.chmod(temp, mode)

                if not orig or oowner != owner or ogroup != group:
                        try:
                                os.chown(temp, owner, group)
                        except OSError, e:
                                if e.errno != errno.EPERM:
                                        raise

                # This is safe even if temp == final_path.
                os.rename(temp, final_path)

        def remove(self, image):
                path = os.path.normpath(os.path.sep.join(
                    (image.get_root(), self.attrs["path"])))

                os.unlink(path)

        def generate_indices(self):
                return {
                    "content": self.hash,
                    "basename": os.path.basename(self.attrs["path"])
                }
