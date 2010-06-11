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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import stat
import pkg.misc

import pkg.bundle
import pkg.actions.file
import pkg.actions.link
import pkg.actions.hardlink

class DirectoryBundle(object):
        """The DirectoryBundle class assists in the conversion of a directory
        tree to a pkg(5) package by traversing the tree and emitting actions for
        all files, directories, and links found therein.

        Paths are published relative to the given directory.  Hardlinks are
        resolved as long as their companions are in the tree as well.

        All owners are set to "root" and groups to "bin", as the ownership
        information is not considered to be valid.  These can be set by the
        caller once the action has been emitted.
        """

        def __init__(self, path):
                # XXX This could be more intelligent.  Or get user input.  Or
                # extend API to take FMRI.
                self.rootdir = os.path.normpath(path)
                self.pkgname = os.path.basename(self.rootdir)
                self.inodes = {}

        def __iter__(self):
                for root, dirs, files in os.walk(self.rootdir):
                        for obj in dirs + files:
                                yield self.action(os.path.join(root, obj))

        def action(self, path):
                rootdir = self.rootdir
                pubpath = os.path.relpath(path, rootdir)
                pstat = os.lstat(path)
                mode = oct(stat.S_IMODE(pstat.st_mode))
                timestamp = pkg.misc.time_to_timestamp(pstat.st_mtime)

                if stat.S_ISREG(pstat.st_mode):
                        inode = pstat.st_ino
                        if inode not in self.inodes:
                                if pstat.st_nlink > 1:
                                        self.inodes[inode] = path
                                return pkg.actions.file.FileAction(
                                    open(path, "rb"), mode=mode, owner="root",
                                    group="bin", path=pubpath,
                                    timestamp=timestamp)
                        else:
                                # Find the relative path to the link target.
                                target = os.path.relpath(self.inodes[inode],
                                    os.path.dirname(path))
                                return pkg.actions.hardlink.HardLinkAction(
                                    path=pubpath, target=target)
                elif stat.S_ISLNK(pstat.st_mode):
                        return pkg.actions.link.LinkAction(
                            target=os.readlink(path), path=pubpath)
                elif stat.S_ISDIR(pstat.st_mode):
                        return pkg.actions.directory.DirectoryAction(
                            timestamp=timestamp, mode=mode, owner="root",
                            group="bin", path=pubpath)

def test(filename):
        return stat.S_ISDIR(os.stat(filename).st_mode)
