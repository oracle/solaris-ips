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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a directory packaging object

This module contains the DirectoryAction class, which represents a
directory-type packaging object."""

import os
import errno
from stat import *
import generic
import pkg.portable as portable
import pkg.actions

class DirectoryAction(generic.Action):
        """Class representing a directory-type packaging object."""

        name = "dir"
        attributes = ("mode", "owner", "group", "path")
        key_attr = "path"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                if "path" in self.attrs:
                        self.attrs["path"] = self.attrs["path"].lstrip(
                            os.path.sep)
                        if not self.attrs["path"]:
                                raise pkg.actions.InvalidActionError(
                                    str(self), _("Empty path attribute"))

        def compare(self, other):
                return cmp(self.attrs["path"], other.attrs["path"])

        def directory_references(self):
                return [os.path.normpath(self.attrs["path"])]

        def install(self, pkgplan, orig):
                """Client-side method that installs a directory."""
                path = self.attrs["path"]
                mode = int(self.attrs["mode"], 8)
                owner = pkgplan.image.get_user_by_name(self.attrs["owner"])
                group = pkgplan.image.get_group_by_name(self.attrs["group"])

                if orig:
                        omode = int(orig.attrs["mode"], 8)
                        oowner = pkgplan.image.get_user_by_name(
                            orig.attrs["owner"])
                        ogroup = pkgplan.image.get_group_by_name(
                            orig.attrs["group"])

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                # XXX Hack!  (See below comment.)
                if not portable.is_admin():
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
                                portable.chown(path, owner, group)
                        except OSError, e:
                                if e.errno != errno.EPERM and \
                                    e.errno != errno.ENOSYS:
                                        raise

        def verify(self, img, **args):
                """ make sure directory is correctly installed"""

                mode = int(self.attrs["mode"], 8)
                owner = img.get_user_by_name(self.attrs["owner"])
                group = img.get_group_by_name(self.attrs["group"])

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
                            (img.get_name_by_uid(stat[ST_UID], True),
                            img.get_name_by_uid(owner, True)))
                if stat[ST_GID] != group:
                        errors.append("Group: '%s' should be '%s'" % \
                            (img.get_name_by_gid(stat[ST_GID], True),
                            img.get_name_by_gid(group, True)))

                if S_IMODE(stat[ST_MODE]) != mode:
                        errors.append("Mode: 0%.3o should be 0%.3o" % \
                            (S_IMODE(stat[ST_MODE]), mode))

                return errors

        def remove(self, pkgplan):
                localpath = os.path.normpath(self.attrs["path"])
                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), localpath)))
                try:
                        os.rmdir(path)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                pass
                        elif e.errno == errno.EEXIST or \
                                    e.errno == errno.ENOTEMPTY:
                                # cannot remove directory since it's
                                # not empty...
                                pkgplan.image.salvagedir(localpath)
                        elif e.errno != errno.EACCES: # this happens on Windows
                                raise

        def generate_indices(self):
                return [
                    ("directory", "basename",
                    os.path.basename(self.attrs["path"].rstrip(os.path.sep)),
                    None),
                    ("directory", "path", os.path.sep + self.attrs["path"],
                    None)
                ]
