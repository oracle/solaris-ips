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
import six

import pkg.bundle
import pkg.misc as misc

from pkg.actions import *
from pkg.actions.attribute import AttributeAction
from pkg.actions.legacy import LegacyAction
from pkg.cpiofile import CpioFile
from pkg.sysvpkg import SolarisPackage


class SolarisPackageDirBundle(pkg.bundle.Bundle):

        hollow_attr = "pkg.send.convert.sunw-pkg-hollow"

        def __init__(self, filename, data=True, **kwargs):
                filename = os.path.normpath(filename)
                self.pkg = SolarisPackage(filename)
                self.pkgname = self.pkg.pkginfo["PKG"]
                self.filename = filename
                self.data = data

                # map the path name to the SVR4 class it belongs to and
                # maintain a set of pre/post install/remove and class action
                # scripts this package uses.
                self.class_actions_dir = {}
                self.class_action_names = set()
                self.scripts = set()

                self.hollow = self.pkg.pkginfo.get("SUNW_PKG_HOLLOW",
                    "").lower() == "true"
                # A list of pkg.action.AttributeActions with pkginfo
                # attributes for items that don't map to pkg(5) equivalents
                self.pkginfo_actions = self.get_pkginfo_actions(self.pkg.pkginfo)

        def _walk_bundle(self):
                faspac = []
                if "faspac" in self.pkg.pkginfo:
                        faspac = self.pkg.pkginfo["faspac"]

                # Want to access the manifest as a dict.
                pkgmap = {}
                for p in self.pkg.manifest:
                        pkgmap[p.pathname] = p
                        self.class_actions_dir[p.pathname] = p.klass
                        self.class_action_names.add(p.klass)

                for act in self.pkginfo_actions:
                        yield act.attrs.get("path"), act

                if not self.data:
                        for p in self.pkg.manifest:
                                act = self.action(p, None)
                                if act:
                                        yield act.attrs.get("path"), act
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
                                act = self.action(pkgmap[j(ci.name)],
                                    ci.extractfile())
                                if act:
                                        yield act.attrs.get("path"), act

                # Remove BASEDIR from a relocatable path.  The extra work is
                # because if BASEDIR is not empty (non-"/"), then we probably
                # need to strip an extra slash from the beginning of the path,
                # but if BASEDIR is "" ("/" in the pkginfo file), then we don't
                # need to do anything extra.
                def r(path, ptype):
                        if ptype == "i":
                                return path
                        if path[0] == "/":
                                return path[1:]
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
                        if p.type in "ifevbcdxpls":
                                if p.type == "i":
                                        d = "install"
                                elif p.pathname[0] == "/":
                                        d = "root"
                                else:
                                        d = "reloc"
                                act = self.action(p, os.path.join(self.filename,
                                    d, r(p.pathname, p.type)))
                                if act:
                                        if act.name == "license":
                                                # This relies on the fact that
                                                # license actions have their
                                                # hash set to the package path.
                                                yield act.hash, act
                                        else:
                                                yield os.path.join(d, act.attrs.get(
                                                    "path", "")), act

        def __iter__(self):
                for entry in self._walk_bundle():
                        yield entry[-1]

        def action(self, mapline, data):
                preserve_dict = {
                    "renameold": "renameold",
                    "renamenew": "renamenew",
                    "preserve": "true",
                    "svmpreserve": "true"
                }

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
                        act = file.FileAction(data, mode=mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname,
                            timestamp=misc.time_to_timestamp(int(mapline.modtime)))

                        # Add a preserve attribute if klass is known to be used
                        # for preservation.  For editable and volatile files,
                        # always do at least basic preservation.
                        preserve = preserve_dict.get(mapline.klass, None)
                        if preserve or mapline.type in "ev":
                                if not preserve:
                                        preserve = "true"
                                act.attrs["preserve"] = preserve

                        if act.hash == "NOHASH" and \
                            isinstance(data, six.string_types) and \
                            data.startswith(self.filename):
                                act.hash = data[len(self.filename) + 1:]
                elif mapline.type in "dx":
                        act = directory.DirectoryAction(mode=mapline.mode,
                            owner=mapline.owner, group=mapline.group,
                            path=mapline.pathname)
                elif mapline.type == "s":
                        act = link.LinkAction(path=mapline.pathname,
                            target=mapline.target)
                elif mapline.type == "l":
                        act = hardlink.HardLinkAction(path=mapline.pathname,
                            target=mapline.target)
                elif mapline.type == "i" and mapline.pathname == "copyright":
                        act = license.LicenseAction(data,
                            license="{0}.copyright".format(self.pkgname))
                        if act.hash == "NOHASH" and \
                            isinstance(data, six.string_types) and \
                            data.startswith(self.filename):
                                act.hash = data[len(self.filename) + 1:]
                elif mapline.type == "i":
                        if mapline.pathname not in ["depend", "pkginfo"]:
                                # check to see if we've seen this script
                                # before
                                script = mapline.pathname
                                if script.startswith("i.") and \
                                    script.replace("i.", "", 1) \
                                    in self.class_action_names:
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
                        act.attrs["pkg.send.convert.sunw-pkg-hollow"] = "true"
                return act

        def get_pkginfo_actions(self, pkginfo):
                """Creates a list of pkg.action.AttributeActions corresponding
                to pkginfo fields that aren't directly mapped to pkg(5)
                equivalents."""

                # these keys get converted to a legacy action
                legacy_keys = [
                    "arch",
                    "category",
                    "name",
                    "desc",
                    "hotline",
                    "pkg",
                    "vendor",
                    "version"
                ]

                # parameters defined in pkginfo(4) that we always ignore.
                # by default, we also ignore SUNW_*
                ignored_keys = [
                    "pstamp",
                    "pkginst",
                    "maxinst",
                    "classes",
                    "basedir",
                    "intonly",
                    "istates",
                    "order",
                    "rstates",
                    "ulimit",
                    # XXX pkg.sysvpkg adds this, ignoring for now.
                    "pkg.plat",
                ]
                ignored_keys.extend(legacy_keys)

                actions = []
                for key in pkginfo:
                        if not pkginfo[key]:
                                continue

                        name = key.lower()
                        if name in ignored_keys or "SUNW_" in key:
                                continue
                        name = "pkg.send.convert.{0}".format(name)
                        name = name.replace("_", "-")
                        actions.append(AttributeAction(name=name,
                            value=pkginfo[key]))

                legacy_attrs = {}
                for key in pkginfo:
                        name = key.lower()
                        if name in legacy_keys:
                                name = name.replace("_", "-")
                                legacy_attrs[name] = pkginfo[key]

                actions.append(LegacyAction(**legacy_attrs))

                if "DESC" in pkginfo:
                        actions.append(AttributeAction(name="pkg.description",
                            value=pkginfo["DESC"]))
                if "NAME" in pkginfo:
                        actions.append(AttributeAction(name="pkg.summary",
                            value=pkginfo["NAME"]))
                if self.hollow:
                        for act in actions:
                                act.attrs[self.hollow_attr] = "true"

                return actions

def test(filename):
        if os.path.isfile(os.path.join(filename, "pkginfo")) and \
            os.path.isfile(os.path.join(filename, "pkgmap")):
                return True

        return False
