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

import os
import stat
import pkg.misc as misc

from pkg.sysvpkg import SolarisPackage
from pkg.actions import *

typemap = {
        stat.S_IFBLK: "block-special",
        stat.S_IFCHR: "character-special",
        stat.S_IFDIR: "directory",
        stat.S_IFIFO: "fifo",
        stat.S_IFLNK: "link",
        stat.S_IFREG: "file",
        stat.S_IFSOCK: "socket"
}

class SolarisPackageDatastreamBundle(object):
        """XXX Need a class comment."""

        def __init__(self, filename):
                self.pkg = SolarisPackage(filename)
                self.pkgname = self.pkg.pkginfo["PKG"]
                self.filename = filename

                # SolarisPackage.manifest is a list.  Cache it into a dictionary
                # based on pathname.  The cpio archive contains the files as
                # they would be in the directory structure -- that is, under
                # install, reloc, or root, depending on whether they're i-type
                # files, relocatable files, or unrelocatable files.  Make sure
                # we find the right object, even though the filenames in the
                # package map don't have these directory names.
                self.pkgmap = {}

                for p in self.pkg.manifest:
                        if p.type in "fevdsl":
                                if p.pathname.startswith("/"):
                                        dir = "root"
                                else:
                                        dir = "reloc/"
                                self.pkgmap[dir + p.pathname] = p
                        elif p.type == "i":
                                self.pkgmap["install/" + p.pathname] = p

        def __iter__(self):
                """Iterate through the datastream.

                   This is different than the directory-format package bundle,
                   which iterates through the package map.  We do it this way
                   because the cpio archive might not be in the same order as
                   the package map, and we want never to seek backwards.  This
                   implies that we're going to have to look up the meta info for
                   each file from the package map.  We could get the file type
                   from the archive, but it's probably safe to assume that the
                   file type in the archive is the same as the file type in the
                   package map.
                """
                for p in self.pkg.datastream:
                        yield self.action(self.pkgmap, p, p.name)

                # for some reason, some packages may have directories specified
                # in the pkgmap that don't exist in the archive.  They need to
                # be found and iterated as well.
                #
                # Some of the blastwave packages also have directories in the
                # archive that don't exist in the package metadata.  I don't see
                # a whole lot of point in faking those up.
                for p in self.pkg.manifest:
                        if p.pathname.startswith("/"):
                                dir = "root"
                        else:
                                dir = "reloc/"
                        if p.type == "d" and \
                            dir + p.pathname not in self.pkg.datastream:
                                yield self.action(self.pkgmap, None,
                                    dir + p.pathname)
                        if p.type in "ls":
                                yield self.action(self.pkgmap, None,
                                    dir + p.pathname)

        def action(self, pkgmap, ci, path):
                try:
                        mapline = pkgmap[path]
                except KeyError:
                        # XXX Return an unknown instead of a missing, for now.
                        return unknown.UnknownAction(path=path)

                if mapline.type in "fev":
                        return file.FileAction(ci.extractfile(),
                            mode=mapline.mode, owner=mapline.owner,
                            group=mapline.group, path=mapline.pathname,
                            timestamp=misc.time_to_timestamp(int(mapline.modtime)))
                elif mapline.type in "dx":
                        return directory.DirectoryAction(mode = mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname)
                elif mapline.type == "s":
                        return link.LinkAction(path=mapline.pathname,
                            target=mapline.target)
                elif mapline.type == "l":
                        return hardlink.HardLinkAction(path=mapline.pathname,
                            target=mapline.target)
                else:
                        return unknown.UnknownAction(path=mapline.pathname)

def test(filename):
        if not os.path.isfile(filename):
                return False

        try:
                SolarisPackage(filename)
                return True
        except:
                return False
