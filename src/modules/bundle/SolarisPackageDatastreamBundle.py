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
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
#

import os
import stat
import pkg.misc as misc

from pkg.sysvpkg import SolarisPackage, MultiPackageDatastreamException
from pkg.actions import *
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle
from pkg.bundle import InvalidBundleException

typemap = {
        stat.S_IFBLK: "block-special",
        stat.S_IFCHR: "character-special",
        stat.S_IFDIR: "directory",
        stat.S_IFIFO: "fifo",
        stat.S_IFLNK: "link",
        stat.S_IFREG: "file",
        stat.S_IFSOCK: "socket"
}

class SolarisPackageDatastreamBundle(SolarisPackageDirBundle):
        """XXX Need a class comment."""

        def __init__(self, filename, **kwargs):
                filename = os.path.normpath(filename)
                self.pkg = SolarisPackage(filename)
                self.pkgname = self.pkg.pkginfo["PKG"]
                self.filename = filename

                # map the path name to the SVR4 class it belongs to and
                # maintain a set of pre/post install/remove and class action
                # scripts this package uses.
                self.class_actions_dir = {}
                self.class_action_names = set()
                self.scripts = set()

                self.hollow = self.pkg.pkginfo.get("SUNW_PKG_HOLLOW",
                    "").lower() == "true"
                self.pkginfo_actions = self.get_pkginfo_actions(
                    self.pkg.pkginfo)

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
                                if p.pathname[0] == "/":
                                        d = "root"
                                else:
                                        d = "reloc/"
                                self.pkgmap[d + p.pathname] = p
                                self.class_actions_dir[p.pathname] = p.klass
                                self.class_action_names.add(p.klass)
                        elif p.type == "i":
                                self.pkgmap["install/" + p.pathname] = p

        def _walk_bundle(self):
                for act in self.pkginfo_actions:
                        yield act.attrs.get("path"), act

                for p in self.pkg.datastream:
                        yield p.name, (self.pkgmap, p, p.name)

                # for some reason, some packages may have directories specified
                # in the pkgmap that don't exist in the archive.  They need to
                # be found and iterated as well.
                #
                # Some of the blastwave packages also have directories in the
                # archive that don't exist in the package metadata.  I don't see
                # a whole lot of point in faking those up.
                for p in self.pkg.manifest:
                        if p.type not in "lsd":
                                continue

                        if p.pathname[0] == "/":
                                d = "root"
                        else:
                                d = "reloc/"
                        path = d + p.pathname
                        if (p.type == "d" and path not in self.pkg.datastream) or \
                            p.type in "ls":
                                yield path, (self.pkgmap, None, path)

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
                for path, data in self._walk_bundle():
                        if type(data) != tuple:
                                yield data
                                continue

                        act = self.action(*data)
                        if act:
                                yield act

        def action(self, pkgmap, ci, path):
                try:
                        mapline = pkgmap[path]
                except KeyError:
                        # XXX Return an unknown instead of a missing, for now.
                        return unknown.UnknownAction(path=path)

                act = None

                # If any one of the mode, owner, or group is "?", then we're
                # clearly not capable of delivering the object correctly, so
                # ignore it.
                if mapline.type in "fevdx" and (mapline.mode == "?" or
                    mapline.owner == "?" or mapline.group == "?"):
                        return None

                if mapline.type in "fev":
                        # false positive
                        # file-builtin; pylint: disable=W1607
                        act = file.FileAction(ci.extractfile(),
                            mode=mapline.mode, owner=mapline.owner,
                            group=mapline.group, path=mapline.pathname,
                            timestamp=misc.time_to_timestamp(int(mapline.modtime)))
                elif mapline.type in "dx":
                        act = directory.DirectoryAction(mode = mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname)
                elif mapline.type == "s":
                        act = link.LinkAction(path=mapline.pathname,
                            target=mapline.target)
                elif mapline.type == "l":
                        act = hardlink.HardLinkAction(path=mapline.pathname,
                            target=mapline.target)
                elif mapline.type == "i" and mapline.pathname == "copyright":
                        act = license.LicenseAction(ci.extractfile(),
                            license="{0}.copyright".format(self.pkgname))
                        act.hash = "install/copyright"
                elif mapline.type == "i":
                        if mapline.pathname not in ["depend", "pkginfo"]:
                                # check to see if we've seen this script
                                # before
                                script = mapline.pathname
                                if script.startswith("i.") and \
                                    script.replace("i.", "", 1) in \
                                    self.class_action_names:
                                        pass
                                elif script.startswith("r.") and \
                                    script.replace("r.", "", 1) in \
                                    self.class_action_names:
                                        pass
                                else:
                                        self.scripts.add(script)
                        return None
                else:
                        act = unknown.UnknownAction(path=mapline.pathname)

                if self.hollow and act:
                        act.attrs[self.hollow_attr] = "true"
                return act

def test(filename):
        if not os.path.isfile(filename):
                return False

        try:
                SolarisPackage(filename)
                return True
        except MultiPackageDatastreamException:
                raise InvalidBundleException(
                    _("Multi-package datastreams are not supported.\n"
                    "Please use pkgtrans(1) to convert this bundle to "
                    "multiple\nfilesystem format packages."))
        except:
                return False
