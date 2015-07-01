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

"""SystemV / Solaris packages.

This module allows the new Solaris packaging system to interface with
System V style packages, both in directory format and in datastream
format.

When a package is in datastream format, it may be compressed with gzip.

XXX Some caveats about rewinding a datastream or multiple packages per
datastream.
"""

from __future__ import print_function
import errno
import gzip
import os
import sys

from pkg.cpiofile import CpioFile
from pkg.dependency import Dependency

__all__ = [ 'SolarisPackage' ]

PKG_MAGIC = "# PaCkAgE DaTaStReAm"
PKG_HDR_END = "# end of header"

class PkgMapLine(object):
        """A class that represents a single line of a SysV package's pkgmap.

        XXX This class should probably disappear once pkg.manifest? is a bit
        more fleshed out.
        """

        def __init__(self, line, basedir = ""):
                array = line.split()
                try:
                        self.part = int(array[0])
                except ValueError:
                        self.part = 1
                        array[0:0] = "1"

                self.type = array[1]
                self.klass = None

                if self.type == 'i':
                        (self.pathname, self.size, self.chksum,
                            self.modtime) = array[2:]
                        return

                self.klass = array[2]

                if self.type == 'f' or self.type == 'e' or self.type == 'v':
                        (self.pathname, self.mode, self.owner, self.group,
                            self.size, self.chksum, self.modtime) = array[3:]

                elif self.type == 'b' or self.type == 'c':
                        (self.pathname, self.major, self.minor, self.mode,
                            self.owner, self.group) = array[3:]

                elif self.type == 'd' or self.type == 'x' or self.type == 'p':
                        (self.pathname, self.mode, self.owner, self.group) = \
                                array[3:]

                elif self.type == 'l' or self.type == 's':
                        (self.pathname, self.target) = array[3].split('=')
                        self.target = self.target.replace("$BASEDIR", basedir)
                else:
                        raise ValueError("Invalid file type: " + self.type)

                # some packages have $BASEDIR in the pkgmap; this needs to
                # be handled specially
                if "$BASEDIR" in self.pathname:
                        self.pathname = self.pathname.replace("$BASEDIR", basedir)
                        # this will cause the pkg to have a NULL path after 
                        # basedir removal, which breaks things.  Make this
                        # entry go away by pretending it is an 'i' type file.
                        if self.pathname == basedir:
                                self.type = 'i'
                else:
                        self.pathname = os.path.join(basedir, self.pathname)


class MultiPackageDatastreamException(Exception):
        pass

# XXX This needs to have a constructor that takes a pkg: FMRI (the new name of
# the package). - sch
#
# XXX want to be able to pull datastream packages from the web.  Should the
# constructor be able to interpret path as a URI, or should we have an optional
# "fileobj" argument which can point to an http stream?
class SolarisPackage(object):
        """A SolarisPackage represents a System V package for Solaris.
        """

        def __init__(self, path):
                """The constructor for the SolarisPackage class.

                The "path" argument may be a directory -- in which case it is
                assumed to be a directory-format package -- or a file -- in
                which case it's tested whether or not it's a datastream package.
                """
                if os.path.isfile(path):
                        f = open(path)
                        if f.readline().strip() == PKG_MAGIC:
                                fo = f
                        else:
                                f.seek(0)
                                try:
                                        g = gzip.GzipFile(fileobj=f)
                                        if g.readline().rstrip() == PKG_MAGIC:
                                                fo = g
                                        else:
                                                raise IOError("not a package")
                                except IOError as e:
                                        if e.args[0] not in (
                                            "Not a gzipped file",
                                            "not a package"):
                                                raise
                                        else:
                                                g.close()
                                                raise ValueError("{0} is not a package".format(path))

                        pkgs = []
                        while True:
                                line = fo.readline().rstrip()
                                if line == PKG_HDR_END:
                                        break
                                pkgs += [ line.split()[0] ]

                        if len(pkgs) > 1:
                                raise MultiPackageDatastreamException(
                                    "{0} contains {1} packages".format(
                                    path, len(pkgs)))

                        # The cpio archive containing all the packages' pkginfo
                        # and pkgmap files starts on the next 512-byte boundary
                        # after the header, so seek to that point.
                        fo.seek(fo.tell() + 512 - fo.tell() % 512)
                        self.datastream = CpioFile.open(mode="r|", fileobj=fo)

                        # We're going to need to extract and cache the contents
                        # of the pkginfo and pkgmap files because we're not
                        # guaranteed random access to the datastream.  At least
                        # they should be reasonably small in size; the largest
                        # delivered in Solaris is a little over 2MB.
                        for ci in self.datastream:
                                if ci.name.endswith("/pkginfo"):
                                        self._pkginfo = self.datastream.extractfile(ci).readlines()
                                elif ci.name.endswith("/pkgmap"):
                                        self._pkgmap = self.datastream.extractfile(ci).readlines()

                        # XXX Here we allow for only one package.  :(
                        self.datastream = self.datastream.get_next_archive()

                else:
                        self.datastream = None
                        self.pkgpath = path

                self.pkginfo = self.readPkginfoFile()
                # Snag BASEDIR, and remove leading and trailing slashes.
                try:
                        assert self.pkginfo["BASEDIR"][0] == "/"
                        self.basedir = self.pkginfo["BASEDIR"][1:].rstrip("/")
                except KeyError:
                        self.basedir = ""
                self.deps = self.readDependFile()
                self.manifest = self.readPkgmapFile()

        def readDependFile(self):
                # XXX This is obviously bogus, but the dependency information is
                # in the main archive, which we haven't read in the constructor
                if self.datastream:
                        return []

                try:
                        fp = open(self.pkgpath + "/install/depend")
                except IOError as xxx_todo_changeme:
                        # Missing depend file is just fine
                        (err, msg) = xxx_todo_changeme.args
                        # Missing depend file is just fine
                        if err == errno.ENOENT:
                                return []
                        else:
                                raise

                deps = []
                for line in fp:
                        line = line.rstrip('\n')

                        if len(line) == 0 or line[0] == '#':
                                continue

                        if line[0] == 'P':
                                try:
                                        type, pkg, desc = line.split(None, 2)
                                except ValueError:
                                        type, pkg = line.split()
                                deps += [ Dependency(self.pkginfo['PKG'], pkg) ]

                return deps

        def readPkginfoFile(self):
                pkginfo = {}

                if self.datastream:
                        fp = self._pkginfo
                else:
                        fp = open(self.pkgpath + "/pkginfo")

                for line in fp:
                        line = line.lstrip().rstrip('\n')

                        if len(line) == 0:
                                continue

                        # Eliminate comments, but special-case the faspac turd.
                        if line[0] == '#':
                                if line.startswith("#FASPACD="):
                                        pkginfo["faspac"] = \
                                            line.lstrip("#FASPACD=").split()
                                continue

                        (key, val) = line.split('=', 1)
                        pkginfo[key] = val.strip('"')

                # Expose the platform-specific package name, too.
                platext = {
                    "i386.i86pc": ".i",
                    "sparc.sun4u": ".u",
                    "sparc.sun4v": ".v",
                }
                pkginfo["PKG.PLAT"] = \
                    pkginfo["PKG"] + platext.get(pkginfo["ARCH"], "")

                return pkginfo

        def readPkgmapFile(self):
                pkgmap = []

                if self.datastream:
                        fp = self._pkgmap
                else:
                        fp = open(self.pkgpath + "/pkgmap")

                for line in fp:
                        line = line.rstrip('\n')

                        if len(line) == 0 or line[0] == '#':
                                continue

                        if line[0] == ':':
                                continue

                        pkgmap += [ PkgMapLine(line, self.basedir) ]

                return pkgmap

if __name__ == "__main__":
        pkg = SolarisPackage(sys.argv[1])

        for key in sorted(pkg.pkginfo):
                print(key + '=' + str(pkg.pkginfo[key]))

        print()

        for obj in pkg.manifest:
                print(obj.type + ' ' + obj.pathname)

        print()

        for d in pkg.deps:
                print(d)
