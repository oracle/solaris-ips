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
import pkg.misc as misc
from pkg.sysvpkg import SolarisPackage
from pkg.cpiofile import CpioFile
from pkg.actions import *

class SolarisPackageDirBundle(object):

        def __init__(self, filename, data=True):
                self.pkg = SolarisPackage(filename)
                self.pkgname = self.pkg.pkginfo["PKG"]
                self.filename = filename
                self.data = data

        def __iter__(self):
                faspac = []
                if "faspac" in self.pkg.pkginfo:
                        faspac = self.pkg.pkginfo["faspac"]

                # Want to access the manifest as a dict.
                pkgmap = {}
                for p in self.pkg.manifest:
                        pkgmap[p.pathname] = p

                if not self.data:
                        for p in self.pkg.manifest:
                                yield self.action(p, None)
                        return

                def j(path):
                        return os.path.join(self.pkg.basedir, path)

                faspac_contents = set()

                for klass in faspac:
                        fpath = os.path.join(self.filename, "archive", klass)
                        # We accept either bz2 or 7zip'd files
                        for x in [".bz2", ".7z"]:
                                if os.path.exists(fpath + x):
                                        cf = CpioFile.open(fpath + x)
                                        break
                        
                        for ci in cf:
                                faspac_contents.add(j(ci.name))
                                yield self.action(pkgmap[j(ci.name)],
                                    ci.extractfile())

                # Remove BASEDIR from the path.  The extra work is because if
                # BASEDIR is not empty (non-"/"), then we probably need to strip
                # an extra slash from the beginning of the path, but if BASEDIR
                # is "" ("/" in the pkginfo file), then we don't need to do
                # anything extra.
                def r(path, type):
                        if type == "i":
                                return path
                        p = path[len(self.pkg.basedir):]
                        if p[0] == "/":
                                p = p[1:]
                        return p

                for p in self.pkg.manifest:
                        # Just do the files that remain.  Only regular file
                        # types end up compressed; so skip them and only them.
                        # Files with special characters in their names may not
                        # end up in the faspac archive, so we still need to emit
                        # the ones that aren't.
                        if p.type in "fev" and p.klass in faspac and \
                            p.pathname in faspac_contents:
                                continue

                        # These are the only valid file types in SysV packages
                        if p.type in "fevbcdxpls":
                                yield self.action(p, os.path.join(self.filename,
                                    "reloc", r(p.pathname, p.type)))
			elif p.type == "i":
				yield self.action(p, os.path.join(self.filename,
				    "install", r(p.pathname, p.type)))

        def action(self, mapline, data):
                preserve_dict = {
                            "renameold": "renameold",
                            "renamenew": "renamenew",
                            "preserve": "true",
                            "svmpreserve": "true"
                        }
                if mapline.type in "f":
                        a = file.FileAction(data, mode=mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname, 
                            timestamp=misc.time_to_timestamp(int(mapline.modtime)))
                        if mapline.klass in preserve_dict:
                                a.attrs["preserve"] = preserve_dict[mapline.klass]
                        return a
                elif mapline.type in "ev":
                        # for editable files, map klass onto IPS names; if match
                        # fails, make sure we at least preserve file
                        preserve=preserve_dict.get(mapline.klass, "true")
                        return file.FileAction(data, mode=mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname, preserve=preserve,
                            timestamp=misc.time_to_timestamp(int(mapline.modtime)))

                elif mapline.type in "dx":
                        return directory.DirectoryAction(mode=mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname)
                elif mapline.type == "s":
                        return link.LinkAction(path=mapline.pathname,
                            target=mapline.target)
                elif mapline.type == "l":
                        return hardlink.HardLinkAction(path=mapline.pathname,
                            target=mapline.target)
		elif mapline.type == "i" and mapline.pathname == "copyright":
			return license.LicenseAction(data, 
			    license="%s.copyright" % self.pkgname,
			    path=mapline.pathname)
                else:
                        return unknown.UnknownAction(path=mapline.pathname)

def test(filename):
        if os.path.isfile(os.path.join(filename, "pkginfo")) and \
            os.path.isfile(os.path.join(filename, "pkgmap")):
                return True

        return False
