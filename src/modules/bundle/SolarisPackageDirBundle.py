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

import os
from pkg.sysvpkg import SolarisPackage
from pkg.cpiofile import CpioFile

class SolarisPackageDirBundle(object):

        def __init__(self, filename):
                self.pkg = SolarisPackage(filename)
                self.pkgname = self.pkg.pkginfo["PKG"]
                self.filename = filename

        def __iter__(self):
                faspac = []
                if "faspac" in self.pkg.pkginfo:
                        faspac = self.pkg.pkginfo["faspac"]

                # Want to access the manifest as a dict.
                pkgmap = {}
                for p in self.pkg.manifest:
                        pkgmap[p.pathname] = p

                for klass in faspac:
                        cf = CpioFile.open(os.path.join(
                            self.filename, "archive", klass + ".bz2"))
                        for ci in cf:
                                yield \
                                    SolarisPackageDirBundleFile(pkgmap[ci.name],
                                        "", stream=ci.extractfile())

                for p in self.pkg.manifest:
                        # Just do the files that remain.  Only regular file
                        # types end up compressed; so skip them and only them.
                        if p.type in "fev" and p.klass in faspac:
                                continue

                        # These are the only valid file types in SysV packages
                        if p.type in "ifevbcdxpls":
                                yield SolarisPackageDirBundleFile(p,
                                    self.filename)

def test(filename):
        if os.path.isfile(os.path.join(filename, "pkginfo")) and \
            os.path.isfile(os.path.join(filename, "pkgmap")):
                return True

        return False

class SolarisPackageDirBundleFile(object):

        def __init__(self, thing, pkgpath, stream=None):
                self.attrs = {}
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
                        }
                        if stream is None:
                                self.attrs["file"] = \
                                        os.path.join(pkgpath, "reloc", thing.pathname)
                        else:
                                self.attrs["filestream"] = stream
                else:
                        self.type = "unknown"
                        self.attrs = {
                                "path": thing.pathname
                        }
