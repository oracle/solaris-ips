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

import gzip
import os
import stat

from pkg.sysvpkg import SolarisPackage

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
                        if p.type in "fevd":
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
                        # XXX Skip other types for now.
                        if typemap[stat.S_IFMT(p.mode)] in ("directory", "file"):
                                yield SolarisPackageDatastreamBundleFile(p, self)

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
                                o = PseudoCI(dir + p.pathname)
                                yield SolarisPackageDatastreamBundleFile(o, self)

class PseudoCI(object):
        """A trivial class to pretend for a moment it's a CpioInfo object."""

        def __init__(self, name):
                self.name = name

def test(filename):
        if not os.path.isfile(filename):
                return False

        try:
                SolarisPackage(filename)
                return True
        except:
                return False

class SolarisPackageDatastreamBundleFile(object):

        def __init__(self, ci, bundle):
                self.attrs = {}

                try:
                        thing = bundle.pkgmap[ci.name]
                except KeyError:
                        self.type = "missing"
                        self.attrs = {
                                "path": ci.name
                        }
                        return

                if thing.type == "d":
                        self.type = "dir"
                        self.attrs = {
                                "mode": thing.mode,
                                "owner": thing.owner,
                                "group": thing.group,
                                "path": thing.pathname,
                        }
                elif thing.type in "fev":
                        self.type = "file"
                        self.attrs = {
                                "mode": thing.mode,
                                "owner": thing.owner,
                                "group": thing.group,
                                "path": thing.pathname,
                                "filestream": ci.extractfile()
                        }
                else:
                        self.type = "unknown"
                        self.attrs = {
                                "path": thing.pathname
                        }
