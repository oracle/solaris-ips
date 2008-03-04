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
import errno
from stat import *
import generic

class DirectoryAction(generic.Action):
        """Class representing a directory-type packaging object."""

        name = "dir"
        attributes = ("mode", "owner", "group", "path")
        key_attr = "path"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def install(self, pkgplan, orig):
                """Client-side method that installs a directory."""
                path = self.attrs["path"]
                mode = int(self.attrs["mode"], 8)
                owner = pkgplan.image.getpwnam(self.attrs["owner"]).pw_uid
                group = pkgplan.image.getgrnam(self.attrs["group"]).gr_gid

                if orig:
                        omode = int(orig.attrs["mode"], 8)
                        oowner = pkgplan.image.getpwnam(
                            orig.attrs["owner"]).pw_uid
                        ogroup = pkgplan.image.getgrnam(
                            orig.attrs["group"]).gr_gid

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                # XXX Hack!  (See below comment.)
                if os.getuid() != 0:
                        mode |= 0200

                if not orig:
                        try:
                                self.makedirs(path, mode = mode)
                        except OSError, e:
                                if e.errno != errno.EEXIST:
                                        raise

                # The downside of chmodding the directory is that as a non-root
                # user, if we set perms u-w, we won't be able to put anything in
                # it, which is often not what we want at install time.  We save
                # the chmods for the postinstall phase, but it's always possible
                # that a later package install will want to place something in
                # this directory and then be unable to.  So perhaps we need to
                # (in all action types) chmod the parent directory to u+w on
                # failure, and chmod it back aftwards.  The trick is to
                # recognize failure due to missing file_dac_write in contrast to
                # other failures.  Or can we require that everyone simply have
                # file_dac_write who wants to use the tools.  Probably not.
                elif mode != omode:
                        os.chmod(path, mode)

                if not orig or oowner != owner or ogroup != group:
                        try:
                                os.chown(path, owner, group)
                        except OSError, e:
                                if e.errno != errno.EPERM and \
                                    e.errno != errno.ENOSYS:
                                        raise

        def verify(self, img, **args):
                """ make sure directory is correctly installed"""

                mode = int(self.attrs["mode"], 8)
                owner = img.getpwnam(self.attrs["owner"]).pw_uid
                group = img.getgrnam(self.attrs["group"]).gr_gid

                path = os.path.normpath(os.path.sep.join((img.get_root(),
                                        self.attrs["path"])))
                try:
                        stat = os.lstat(path)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                return ["Directory does not exist"]
                        if e.errno == errno.EACCES:
                                return ["Skipping: Permission denied"]
                        return ["Unexpected exception: %s" % e]

                errors = []

                if not S_ISDIR(stat[ST_MODE]):
                        errors.append("Not a directory")

                if stat[ST_UID] != owner:
                        errors.append("Owner: '%s' should be '%s'" % \
                            (img.getpwuid(stat[ST_UID]).pw_name,
                            img.getpwuid(owner).pw_name))
                if stat[ST_GID] != group:
                        errors.append("Group: '%s' should be '%s'" % \
                            (img.getgrgid(stat[ST_GID]).gr_name,
                            img.getgrgid(group).gr_name))

                if S_IMODE(stat[ST_MODE]) != mode:
                        errors.append("Mode: 0%.3o should be 0%.3o" % \
                            (S_IMODE(stat[ST_MODE]), mode))

                return errors
                
        def remove(self, pkgplan):
                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                try:
                        os.rmdir(path)
                except OSError, e:
                        if e.errno != errno.EEXIST and \
                            e.errno != errno.ENOENT:
                                raise

        def generate_indices(self):
                return {
                    "basename": os.path.basename(self.attrs["path"]),
                    "path": os.path.sep + self.attrs["path"]
                }
