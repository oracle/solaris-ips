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

"""module describing a directory packaging object

This module contains the DirectoryAction class, which represents a
directory-type packaging object."""

import os
import grp
import pwd
import errno

import generic

class DirectoryAction(generic.Action):
        """Class representing a directory-type packaging object."""

        name = "dir"
        attributes = ("mode", "owner", "group", "path")

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def preinstall(self, image):
                """Client-side method that performs pre-install actions."""
                pass

        def install(self, image):
                """Client-side method that installs a directory."""
                path = self.attrs["path"]
                mode = int(self.attrs["mode"], 8)
                owner = pwd.getpwnam(self.attrs["owner"]).pw_uid
                group = grp.getgrnam(self.attrs["group"]).gr_gid

                path = os.path.normpath(os.path.sep.join(
                    (image.get_root(), path)))
                try:
                        os.mkdir(path, mode)
                except OSError, e:
                        if e.errno != errno.EEXIST:
                                raise

                try:
                        os.chown(path, owner, group)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def postinstall(self):
                """Client-side method that performs post-install actions."""
                pass
