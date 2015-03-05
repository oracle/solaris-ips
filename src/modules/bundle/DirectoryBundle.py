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
# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.
#

import grp
import os
import pwd
import stat
import pkg.misc

import pkg.bundle
import pkg.actions.file
import pkg.actions.link
import pkg.actions.hardlink

class DirectoryBundle(pkg.bundle.Bundle):
        """The DirectoryBundle class assists in the conversion of a directory
        tree to a pkg(5) package by traversing the tree and emitting actions for
        all files, directories, and links found therein.

        Paths are published relative to the given directory.  Hardlinks are
        resolved as long as their companions are in the tree as well.

        All owners are set to "root" and groups to "bin", as the ownership
        information is not considered to be valid.  These can be set by the
        caller once the action has been emitted.
        """

        def __init__(self, path, targetpaths=(), use_default_owner=True):
                # XXX This could be more intelligent.  Or get user input.  Or
                # extend API to take FMRI.
                path = os.path.normpath(path)
                self.filename = path
                self.rootdir = path
                self.pkgname = os.path.basename(self.rootdir)
                self.inodes = None
                self.targetpaths = targetpaths
                self.pkg = None
                self.use_default_owner = use_default_owner

        def _walk_bundle(self):
                # Pre-populate self.inodes with the paths of known targets
                if self.inodes is None:
                        self.inodes = {}
                        for p in self.targetpaths:
                                fp = os.path.join(self.rootdir, p)
                                pstat = os.lstat(fp)
                                self.inodes[pstat.st_ino] = fp

                for root, dirs, files in os.walk(self.rootdir):
                        for obj in dirs + files:
                                path = os.path.join(root, obj)
                                yield path, (path,)

        def __iter__(self):
                for path, data in self._walk_bundle():
                        act = self.action(*data)
                        if act:
                                yield act

        def action(self, path):
                rootdir = self.rootdir
                pubpath = pkg.misc.relpath(path, rootdir)
                pstat = os.lstat(path)
                mode = oct(stat.S_IMODE(pstat.st_mode))
                timestamp = pkg.misc.time_to_timestamp(pstat.st_mtime)

                # Set default root and group.
                owner = "root"
                group = "bin"

                # Check whether need to change owner.
                if not self.use_default_owner:
                        try:
                                owner = pwd.getpwuid(pstat.st_uid).pw_name
                        except KeyError as e:
                                owner = None
                        try:
                                group = grp.getgrgid(pstat.st_gid).gr_name
                        except KeyError as e:
                                group = None

                        if not owner and not group:
                                raise pkg.bundle.InvalidOwnershipException(
                                    path, uid=pstat.st_uid, gid=pstat.st_gid)
                        elif not owner:
                                raise pkg.bundle.InvalidOwnershipException(
                                    path, uid=pstat.st_uid)
                        elif not group:
                                 raise pkg.bundle.InvalidOwnershipException(
                                    path, gid=pstat.st_gid)

                if stat.S_ISREG(pstat.st_mode):
                        inode = pstat.st_ino
                        # Any inode in self.inodes will either have been visited
                        # before or will have been pre-populated from the list
                        # of known targets.  Create file actions for known
                        # targets and unvisited inodes.
                        if pubpath in self.targetpaths or \
                            inode not in self.inodes:
                                if pstat.st_nlink > 1:
                                        self.inodes.setdefault(inode, path)
                                return pkg.actions.file.FileAction(
                                    open(path, "rb"), mode=mode, owner=owner,
                                    group=group, path=pubpath,
                                    timestamp=timestamp)
                        else:
                                # Find the relative path to the link target.
                                target = pkg.misc.relpath(self.inodes[inode],
                                    os.path.dirname(path))
                                return pkg.actions.hardlink.HardLinkAction(
                                    path=pubpath, target=target)
                elif stat.S_ISLNK(pstat.st_mode):
                        return pkg.actions.link.LinkAction(
                            target=os.readlink(path), path=pubpath)
                elif stat.S_ISDIR(pstat.st_mode):
                        return pkg.actions.directory.DirectoryAction(
                            timestamp=timestamp, mode=mode, owner=owner,
                            group=group, path=pubpath)

def test(filename):
        return stat.S_ISDIR(os.stat(filename).st_mode)
