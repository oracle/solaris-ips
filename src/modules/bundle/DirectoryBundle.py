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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import stat
import pkg.misc

from pkg.actions import *

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

        def __init__(self, dir):
                # XXX This could be more intelligent.  Or get user input.  Or
                # extend API to take FMRI.
                self.pkgname = os.path.basename(dir)
                self.rootdir = dir
                self.inodes = {}

        def __iter__(self):
                for root, dirs, files in os.walk(self.rootdir):
                        for obj in dirs + files:
                                yield self.action(os.path.join(root, obj))

        @staticmethod
        def __commonroot(one, two):
                for i, c in enumerate(zip(one, two)):
                        if c[0] != c[1]:
                                break

                return i

        def action(self, path):
                pubpath = path[len(self.rootdir) + 1:]
                pstat = os.lstat(path)
                mode = oct(stat.S_IMODE(pstat.st_mode))
                timestamp = pkg.misc.time_to_timestamp(pstat.st_mtime)

                if stat.S_ISREG(pstat.st_mode):
                        inode = pstat.st_ino
                        if inode not in self.inodes:
                                if pstat.st_nlink > 1:
                                        self.inodes[inode] = pubpath
                                return file.FileAction(open(path), mode=mode,
                                    owner="root", group="bin", path=pubpath,
                                    timestamp=timestamp)
                        else:
                                # Find the relative path to the link target.
                                cp = self.__commonroot(pubpath,
                                    self.inodes[inode])
                                target = os.path.sep.join(
                                    pubpath[cp:].count("/") * [os.path.pardir] +
                                        [self.inodes[inode][cp:]])
                                return hardlink.HardLinkAction(
                                    path=pubpath, target=target)
                elif stat.S_ISLNK(pstat.st_mode):
                        return link.LinkAction(
                            target=os.readlink(path), path=pubpath)
                elif stat.S_ISDIR(pstat.st_mode):
                        return directory.DirectoryAction(timestamp=timestamp,
                            mode=mode, owner="root", group="bin", path=pubpath)

def test(filename):
        try:
                return stat.S_ISDIR(os.stat(filename).st_mode)
        except:
                return False
