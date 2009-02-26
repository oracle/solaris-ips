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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.


import fnmatch
import getopt
import gettext
import os
import pkg.depotcontroller as depotcontroller
import pkg.publish.transaction as trans
import re
import shlex
import sys
import urllib
import urlparse

from datetime import datetime
from itertools import groupby
from pkg import actions, elf
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle
from pkg.sysvpkg import SolarisPackage
from tempfile import mkstemp

gettext.install("import", "/usr/lib/locale")

class package(object):
        def __init__(self, name):
                self.name = name
                self.files = []
                self.depend = []
                self.idepend = []     #svr4 pkg deps, if any
                self.undepend = []
                self.extra = []
                self.nonhollow_dirs = {}
                self.srcpkgs = []
                self.classification = ""
                self.desc = ""
                self.version = ""
                self.imppkg = None
                pkgdict[name] = self

        def import_pkg(self, imppkg, line):
                try:
                        p = SolarisPackage(pkg_path(imppkg))
                except:
                        raise RuntimeError("No such package: '%s'" % imppkg)

                self.imppkg = p

                svr4pkgpaths[p.pkginfo["PKG.PLAT"]] = pkg_path(imppkg)

                # filename NOT always same as pkgname
                imppkg = p.pkginfo["PKG.PLAT"]
                svr4pkgsseen[imppkg] = p

                if "SUNW_PKG_HOLLOW" in p.pkginfo and \
                    p.pkginfo["SUNW_PKG_HOLLOW"].lower() == "true":
                        hollow_pkgs[imppkg] = True

                excludes = dict((f, True) for f in line.split())

                # XXX This isn't thread-safe.  We want a dict method that adds
                # the key/value pair, but throws an exception if the key is
                # already present.
                for o in p.manifest:
                        if o.pathname in excludes:
                                print "excluding %s from %s" % \
                                    (o.pathname, imppkg)
                                continue

                        if o.pathname in elided_files:
                                print "ignoring %s in %s" % (o.pathname, imppkg)
                                continue

                        if o.type == "e":
                                if o.pathname not in editable_files:
                                        editable_files[o.pathname] = \
                                            [(imppkg, self)]
                                else:
                                        editable_files[o.pathname].append(
                                            (imppkg, self))

                        # XXX This decidedly ignores "e"-type files.

                        if o.type in "fv" and o.pathname in usedlist:
                                s = reuse_err % (
                                        o.pathname,
                                        self.name,
                                        imppkg,
                                        svr4pkgpaths[imppkg],
                                        usedlist[o.pathname][1].name,
                                        usedlist[o.pathname][0],
                                        svr4pkgpaths[usedlist[o.pathname][0]])
                                print s
                                raise RuntimeError(s)
                        elif o.type != "i":

                                if o.type in "dx" and imppkg not in hollow_pkgs:
                                        self.nonhollow_dirs[o.pathname] = True

                                usedlist[o.pathname] = (imppkg, self)
                                self.check_perms(o)
                                self.files.append(o)

                if not self.version:
                        self.version = "%s-%s" % (def_vers,
                            get_branch(self.name))
                if not self.desc:
                        self.desc = zap_strings(p.pkginfo["NAME"],
                            description_detritus)

                # This is how we'd import dependencies, but we'll use
                # file-specific dependencies only, since these tend to be
                # broken.
                # self.depend.extend(
                #     d.req_pkg_fmri
                #     for d in p.deps
                # )

                self.add_svr4_src(imppkg)

        def add_svr4_src(self, imppkg):
                if imppkg in destpkgs:
                        destpkgs[imppkg].append(self.name)
                else:
                        destpkgs[imppkg] = [self.name]
                self.srcpkgs.append(imppkg)

        def import_file(self, fname, line):
                imppkgname = self.imppkg.pkginfo["PKG.PLAT"]

                if "SUNW_PKG_HOLLOW" in self.imppkg.pkginfo and \
                    self.imppkg.pkginfo["SUNW_PKG_HOLLOW"].lower() == "true":
                        hollow_pkgs[imppkgname] = True

                if fname in usedlist:
                        t = [
                            f for f in usedlist[fname][1].files
                            if f.pathname == fname
                        ][0].type
                        if t in "fv":
                                assert imppkgname == usedlist[fname][0]
                                raise RuntimeError(reuse_err % (
                                        fname,
                                        self.name,
                                        self.imppkg,
                                        svr4pkgpaths[self.imppkg],
                                        usedlist[fname][1].name,
                                        usedlist[fname][0],
                                        svr4pkgpaths[usedlist[fname][0]]))

                usedlist[fname] = (imppkgname, self)
                o = [
                    o
                    for o in self.imppkg.manifest
                    if o.pathname == fname 
                ]
                # There should be only one file with a given pathname in a
                # single package.
                if len(o) != 1:
                        print "ERROR: %s %s" % (imppkgname, fname)
                        assert len(o) == 1

                if line:
                        a = actions.fromstr(
                            "%s path=%s %s" % \
                                    (
                                        self.convert_type(o[0].type),
                                        o[0].pathname,
                                        line
                                        )
                            )
                        for attr in a.attrs:
                                if attr == "owner":
                                        o[0].owner = a.attrs[attr]
                                elif attr == "group":
                                        o[0].group = a.attrs[attr]
                                elif attr == "mode":
                                        o[0].mode = a.attrs[attr]
                self.check_perms(o[0])
                self.files.extend(o)

        def convert_type(self, svrtype):
                """ given sv4r type, return IPS type"""
                return {
                        "f": "file", "e": "file", "v": "file",
                        "d": "dir", "x": "dir",
                        "s": "link",
                        "l": "hardlink"
                        }[svrtype]

        def type_convert(self, ipstype):
                """ given IPS type, return svr4 type(s)"""
                return {
                        "file": "fev", "dir": "dx", "link": "s",
                        "hardlink": "l"
                        }[ipstype]

        def file_to_action(self, f):

                if f.type in "dx":
                        action = actions.directory.DirectoryAction(
                            None, mode = f.mode, owner = f.owner,
                            group = f.group, path = f.pathname)
                elif f.type in "efv":
                        action = actions.file.FileAction(
                            None, mode = f.mode, owner = f.owner,
                            group = f.group, path = f.pathname)
                elif f.type == "s":
                        action = actions.link.LinkAction(None,
                            target = f.target, path = f.pathname)
                elif f.type == "l":
                        action = actions.hardlink.HardLinkAction(None,
                            target = f.target, path = f.pathname)
                else:
                        print "unknown type %s - path %s" % \
                            ( f.type, f.pathname)

                return action

        def check_perms(self, manifest):
                if manifest.type not in "fevdxbc":
                        return

                if manifest.owner == "?":
                        manifest.owner = "root"
                        print "File %s in pkg %s owned by '?': mapping to %s" \
                            % (manifest.pathname, self.name, manifest.owner)

                if manifest.group == "?":
                        manifest.group = "bin"
                        print "File %s in pkg %s of group '?': mapping to %s" \
                            % (manifest.pathname, self.name, manifest.group)
                if manifest.mode == "?":
                        manifest.mode = "0444"
                        print "File %s in pkg %s mode '?': mapping to %s" % \
                            (manifest.pathname, self.name, manifest.mode)


        def chattr(self, fname, line):
                o = [f for f in self.files if f.pathname == fname]
                if not o:
                        raise RuntimeError("No file '%s' in package '%s'" % \
                            (fname, curpkg.name))

                line = line.rstrip()

                # is this a deletion?
                if line.startswith("drop"):
                        for f in o:
                                # deletion of existing attribute
                                if not hasattr(f, "deleted_attrs"):
                                        f.deleted_attrs = []
                                print "Adding drop on %s of %s" % \
                                    (fname, line.split()[1:])
                                f.deleted_attrs.extend(line.split()[1:])
                        return

                # handle insertion/modification case
                for f in o:
                        a = actions.fromstr(("%s path=%s %s" %
                            (self.convert_type(f.type), fname, line)).rstrip())
                        if show_debug:
                                print "Updating attributes on " + \
                                    "'%s' in '%s' with '%s'" % \
                                    (f.pathname, curpkg.name, a)
                        orig_action = self.file_to_action(f)

                        if not hasattr(f, "changed_attrs"):
                                f.changed_attrs = {}

                        # each chattr produces a dictionary of actions
                        # including a path=xxxx and whatever modifications
                        # are made.  Note that the path value may be a list in
                        # the case of modifications to the path... since
                        # each chattr produces another path= entry and results
                        # from applying the changes to the original file spec,
                        # we need to ignore path if it hasn't changed... for
                        # generality, we ignore all unchanged attributes in
                        # the code below, adding into changed_attrs only those
                        # that are different from the original... this also
                        # insulates us from the possibility of actions.fromstr
                        # adding additional attributes in the constructor...

                        for key in a.attrs.keys():
                                if key not in orig_action.attrs or \
                                    orig_action.attrs[key] != a.attrs[key]:
                                        if key in f.changed_attrs:
                                                print "Warning: overwriting " \
                                                    "changed attr %s on %s " \
                                                    "from %s to %s" % \
                                                    (key, f.pathname,
                                                     f.changed_attrs[key],
                                                     a.attrs[key])
                                        f.changed_attrs[key] = a.attrs[key]


        # apply a chattr to wildcarded files/dirs
        # also allows package specification, wildcarding, regexp edit

        def chattr_glob(self, glob, line):
                args = line.split()
                if args[0] == "from":
                        args.pop(0)
                        pkgglob = args.pop(0)
                        line = " ".join(args)
                else:
                        pkgglob = "*"

                if args[0] == "type": # we care about type
                        args.pop(0)
                        types = self.type_convert(args.pop(0))
                        line = " ".join(args)
                else:
                        types = "dfevslx"

                if args[0] == "edit": # we're doing regexp edit of attr
                        edit = True
                        args.pop(0)
                        target = args.pop(0)
                        regexp = re.compile(args.pop(0))
                        replace = args.pop(0)
                        line = " ".join(args)
                else:
                        edit = False

                o = [
                        f
                        for f in self.files
                        if fnmatch.fnmatchcase(f.pathname, glob) and
                            fnmatch.fnmatchcase(
                                usedlist[f.pathname][0], pkgglob) and
                            f.type in types
                     ]

                chattr_line = line

                for f in o:
                        fname = f.pathname
                        orig_action = self.file_to_action(f)
                        if edit:
                                if target in orig_action.attrs:
                                        old_value = orig_action.attrs[target]
                                        new_value = regexp.sub(replace, \
                                            old_value)
                                        if old_value == new_value:
                                                continue
                                        chattr_line = "%s=%s %s" % \
                                            (target, new_value, line)
                                else:
                                        continue
                        chattr_line = chattr_line.rstrip()
                        if show_debug:
                                print "Updating attributes on " + \
                                    "'%s' in '%s' with '%s'" % \
                                    (fname, curpkg.name, chattr_line)
                        s = "%s path=%s %s" % (self.convert_type(f.type), \
                           fname, chattr_line)
                        a = actions.fromstr(s)

                        # each chattr produces a dictionary of actions
                        # including a path=xxxx and whatever modifications
                        # are made.  Note that the path value may be a list in
                        # the case of modifications to the path... since
                        # each chattr produces another path= entry and results
                        # from applying the changes to the original file spec,
                        # we need to ignore path if it hasn't changed... for
                        # generality, we ignore all unchanged attributes in
                        # the code below, adding into changed_attrs only those
                        # that are different from the original... this also
                        # insulates us from the possibility of actions.fromstr
                        # adding additional attributes in the constructor...

                        if not hasattr(f, "changed_attrs"):
                                f.changed_attrs = {}
                        for key in a.attrs.keys():
                                if key not in orig_action.attrs or \
                                    orig_action.attrs[key] != a.attrs[key]:
                                        if key in f.changed_attrs:
                                                print "Warning: overwriting " \
                                                    "changed attr %s on %s " \
                                                    "from %s to %s" % \
                                                    (key, f.pathname,
                                                     f.changed_attrs[key],
                                                     a.attrs[key])
                                        f.changed_attrs[key] = a.attrs[key]

pkgpaths = {}

def pkg_path(pkgname):
        name = os.path.basename(pkgname)
        if pkgname in pkgpaths:
                return pkgpaths[name]
        if "/" in pkgname:
                pkgpaths[name] = os.path.realpath(pkgname)
                return pkgname
        else:
                for each_path in wos_path:
                        if os.path.exists(each_path + "/" + pkgname):
                                pkgpaths[name] = each_path + "/" + pkgname
                                return pkgpaths[name]

                raise RuntimeError("package %s not found" % pkgname)


def start_package(pkgname):
        return package(pkgname)

def end_package(pkg):
        pkg_branch = get_branch(pkg.name)
        if not pkg.version:
                pkg.version = "%s-%s" % (def_vers, pkg_branch)
        elif "-" not in pkg.version:
                pkg.version += "-%s" % pkg_branch

        print "Package '%s'" % pkg.name
        print "  Version:", pkg.version
        print "  Description:", pkg.desc
        print "  Classification: ", pkg.classification

def publish_pkg(pkg):

        new_pkg_name = "%s@%s" % (pkg.name, pkg.version)
        t = trans.Transaction(def_repo, pkg_name=new_pkg_name,
            noexecute=nopublish)

        print "    open %s" % new_pkg_name
        transaction_id = t.open()

        # Publish non-file objects first: they're easy.
        for f in pkg.files:
                if f.type in "dx":
                        action = actions.directory.DirectoryAction(
                            None, mode = f.mode, owner = f.owner,
                            group = f.group, path = f.pathname)
                        if hasattr(f, "changed_attrs"):
                                action.attrs.update(f.changed_attrs)
                                # chattr may have produced two path values
                                action.attrs["path"] = \
                                    action.attrlist("path")[-1]
                        print "    %s add dir %s %s %s %s" % (
                                pkg.name,
                                action.attrs["mode"],
                                action.attrs["owner"],
                                action.attrs["group"],
                                action.attrs["path"]
                                )
                elif f.type == "s":
                        action = actions.link.LinkAction(None,
                            target = f.target, path = f.pathname)
                        if hasattr(f, "changed_attrs"):
                                action.attrs.update(f.changed_attrs)
                                # chattr may have produced two path values
                                action.attrs["path"] = \
                                    action.attrlist("path")[-1]
                        print "    %s add link %s %s" % (
                                pkg.name,
                                action.attrs["path"],
                                action.attrs["target"]
                                )
                elif f.type == "l":
                        action = actions.hardlink.HardLinkAction(None,
                            target = f.target, path = f.pathname)
                        if hasattr(f, "changed_attrs"):
                                action.attrs.update(f.changed_attrs)
                                # chattr may have produced two path values
                                action.attrs["path"] = \
                                    action.attrlist("path")[-1]
                        pkg.depend += process_link_dependencies(
                            action.attrs["path"], action.attrs["target"])
                        print "    %s add hardlink %s %s" % (
                                pkg.name,
                                action.attrs["path"],
                                action.attrs["target"]
                                )
                else:
                        continue

                #
                # If the originating package was hollow, tag this file
                # as being global zone only.
                #

                if f.type not in "dx" and f.pathname in usedlist and \
                    usedlist[f.pathname][0] in hollow_pkgs:
                        action.attrs["opensolaris.zone"] = "global"
                        action.attrs["variant.opensolaris.zone"] = "global"

                if f.type in "dx" and f.pathname in usedlist and \
                    usedlist[f.pathname][0] in hollow_pkgs and \
                    f.pathname not in pkg.nonhollow_dirs:
                        action.attrs["opensolaris.zone"] = "global"
                        action.attrs["variant.opensolaris.zone"] = "global"

                # handle attribute deletion
                if hasattr(f, "deleted_attrs"):
                        for d in f.deleted_attrs:
                                if d in action.attrs:
                                        del action.attrs[d]

                t.add(action)

        # Group the files in a (new) package based on what (old) package they
        # came from, so that we can iterate through all files in a single (old)
        # package (and, therefore, in a single bzip2 archive) before moving on
        # to the next.  Because groupby() needs its input pre-sorted by group
        # and we want to maintain the order that the files come out of the cpio
        # archives, we coalesce the groups with the groups dictionary.
        def fn(key):
                return usedlist[key.pathname][0]
        groups = {}
        for k, g in groupby((f for f in pkg.files if f.type in "fev"), fn):
                if k in groups:
                        groups[k].extend(g)
                else:
                        groups[k] = list(g)

        def otherattrs(action):
                s = " ".join(
                    "%s=%s" % (a, action.attrs[a])
                    for a in action.attrs
                    if a not in ("owner", "group", "mode", "path")
                )
                if s:
                        return " " + s
                else:
                        return ""

        # Maps class names to preserve attribute values.
        preserve_dict = {
            "renameold": "renameold",
            "renamenew": "renamenew",
            "preserve": "true",
            "svmpreserve": "true"
        }

        undeps = set()
        for g in groups.values():
                pkgname = usedlist[g[0].pathname][0]
                print "pulling files from archive in package", pkgname
                bundle = SolarisPackageDirBundle(svr4pkgpaths[pkgname])
                pathdict = dict((f.pathname, f) for f in g)
                for f in bundle:
                        if f.name == "license":
                                # add transaction id so that every version
                                # of a pkg will have a unique license to prevent
                                # license from disappearing on upgrade
                                f.attrs["transaction_id"] = transaction_id
                                # The "path" attribute is confusing and
                                # unnecessary for licenses.
                                del f.attrs["path"]
                                t.add(f)
                        elif f.attrs["path"] in pathdict:
                                if pkgname in hollow_pkgs:
                                        f.attrs["opensolaris.zone"] = "global"
                                        f.attrs["variant.opensolaris.zone"] = \
                                            "global"
                                path = f.attrs["path"]
                                if pathdict[path].type in "ev":
                                        f.attrs["preserve"] = "true"
                                f.attrs["owner"] = pathdict[path].owner
                                f.attrs["group"] = pathdict[path].group
                                f.attrs["mode"] = pathdict[path].mode

                                # is this a file for which we need a timestamp?
                                basename = os.path.basename(path)
                                for file_pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename,
                                            file_pattern):
                                                break
                                else:
                                        del f.attrs["timestamp"]
                                if pathdict[path].klass in preserve_dict.keys():
                                        f.attrs["preserve"] = \
                                            preserve_dict[pathdict[path].klass]
                                if hasattr(pathdict[path], "changed_attrs"):
                                        f.attrs.update(
                                            pathdict[path].changed_attrs)
                                        # chattr may have produced two values
                                        f.attrs["path"] = f.attrlist("path")[-1]

                                print "    %s add file %s %s %s %s%s" % \
                                    (pkg.name, f.attrs["mode"],
                                        f.attrs["owner"], f.attrs["group"],
                                        f.attrs["path"], otherattrs(f))

                                # handle attribute deletion
                                if hasattr(pathdict[path], "deleted_attrs"):
                                        for d in pathdict[path].deleted_attrs:
                                                if d in f.attrs:
                                                        print "removed %s from %s in pkg %s" % (d, path, new_pkg_name)
                                                        del f.attrs[d]

                                # Read the file in chunks to avoid a memory
                                # footprint blowout.
                                fo = f.data()
                                bufsz = 256 * 1024
                                sz = int(f.attrs["pkg.size"])
                                fd, tmp = mkstemp(prefix="pkg.")
                                while sz > 0:
                                        d = fo.read(min(bufsz, sz))
                                        os.write(fd, d)
                                        sz -= len(d)
                                d = None
                                os.close(fd)

                                # Fool the action into pulling from a
                                # temporary file so that both add() and
                                # process_dependencies() can read() the
                                # data.
                                f.data = lambda: open(tmp, "rb")
                                t.add(f)

                                # Look for dependencies
                                deps, u = process_dependencies(tmp, path)
                                pkg.depend += deps
                                if u:
                                        print \
                                            "%s has missing dependencies: %s" \
                                            % (path, u)
                                undeps |= set(u)
                                os.unlink(tmp)

        # Publish dependencies

        missing_cnt = 0

        for p in set(pkg.idepend): # over set of svr4 deps, append ipkgs
                if p in destpkgs:
                        pkg.depend.extend(destpkgs[p])
                else:
                        print "pkg %s: SVR4 package %s not seen" % \
                            (pkg.name, p)
                        missing_cnt += 1
        if missing_cnt > 0:
                raise RuntimeError("missing packages!")

        for p in set(pkg.depend) - set(pkg.undepend):
                # Don't make a package depend on itself.
                if p.split("@")[0] == pkg.name:
                        continue
                # enhance unqualified dependencies to include current
                # pkg version
                if "@" not in p and p in pkgdict:
                        p = "%s@%s" % (p, pkgdict[p].version)

                print "    %s add depend require %s" % (pkg.name, p)
                action = actions.depend.DependencyAction(None,
                    type = "require", fmri = p)
                t.add(action)

        for a in pkg.extra:
                print "    %s add %s" % (pkg.name, a)
                action = actions.fromstr(a)
                #
                # fmris may not be completely specified; enhance them to current
                # version if this is the case
                #
                for attr in action.attrs:
                        if attr == "fmri" and \
                            "@" not in action.attrs[attr] and \
                            action.attrs[attr][5:] in pkgdict:
                                action.attrs[attr] += "@%s" % \
                                    pkgdict[action.attrs[attr][5:]].version
                t.add(action)

        if pkg.desc:
                print "    %s add set description=%s" % (pkg.name, pkg.desc)
                action = actions.attribute.AttributeAction(None,
                    description = pkg.desc)
                t.add(action)

        if pkg.classification:
                print "    %s add set info.classification=%s" % \
                    (pkg.name, pkg.classification)
                attrs = dict(name="info.classification",
                             value=pkg.classification)
                action = actions.attribute.AttributeAction(None, **attrs)
                t.add(action)

        if pkg.name != "SUNWipkg":
                for p in pkg.srcpkgs:
                        try:
                                sp = svr4pkgsseen[p]
                        except KeyError:
                                continue

                        wanted_attrs = (
                                "PKG", "NAME", "ARCH", "VERSION", "CATEGORY",
                                "VENDOR", "DESC", "HOTLINE"
                                )
                        attrs = dict(
                                (k.lower(), v)
                                for k, v in sp.pkginfo.iteritems()
                                if k in wanted_attrs
                                )
                        attrs["pkg"] = sp.pkginfo["PKG.PLAT"]

                        action = actions.legacy.LegacyAction(None, **attrs)

                        print "    %s add %s" % (pkg.name, action)
                        t.add(action)

        if undeps:
                print "Missing dependencies:", list(undeps)

        print "    close"
        pkg_fmri, pkg_state = t.close(refresh_index=not defer_refresh)
        print "%s: %s\n" % (pkg_fmri, pkg_state)

def process_link_dependencies(path, target):
        orig_target = target
        if target[0] != "/":
                target = os.path.normpath(
                    os.path.join(os.path.split(path)[0], target))

        if target in usedlist:
                if show_debug:
                        print "hardlink %s -> %s makes %s depend on %s" % \
                            (
                                path, orig_target,
                                usedlist[path][1].name,
                                usedlist[target][1].name
                                )
                return ["%s@%s" % (usedlist[target][1].name,
                    usedlist[target][1].version)]
        else:
                return []

def process_dependencies(fname, path):
        if not elf.is_elf_object(fname):
                return [], []

        ei = elf.get_info(fname)
        try:
                ed = elf.get_dynamic(fname)
        except elf.ElfError:
                deps = []
                rp = []
        else:
                deps = [
                    d[0]
                    for d in ed.get("deps", [])
                ]
                rp = ed.get("runpath", "").split(":")
                if len(rp) == 1 and rp[0] == "":
                        rp = []

        rp = [
            os.path.normpath(p.replace("$ORIGIN", "/" + os.path.dirname(path)))
            for p in rp
        ]

        kernel64 = None

        # For kernel modules, default path resolution is /platform/<platform>,
        # /kernel, /usr/kernel.  But how do we know what <platform> would be for
        # a given module?  Does it do fallbacks to, say, sun4u?
        if path.startswith("kernel") or path.startswith("usr/kernel") or \
            (path.startswith("platform") and path.split("/")[2] == "kernel"):
                if rp:
                        print "RUNPATH set for kernel module (%s): %s" % \
                            (path, rp)
                # Default kernel search path
                rp.extend(("/kernel", "/usr/kernel"))
                # What subdirectory should we look in for 64-bit kernel modules?
                if ei["bits"] == 64:
                        if ei["arch"] == "i386":
                                kernel64 = "amd64"
                        elif ei["arch"] == "sparc":
                                kernel64 = "sparcv9"
                        else:
                                print ei["arch"]
        else:
                if "/lib" not in rp:
                        rp.append("/lib")
                if "/usr/lib" not in rp:
                        rp.append("/usr/lib")

        # XXX Do we need to handle anything other than $ORIGIN?  x86 images have
        # a couple of $PLATFORM and $ISALIST instances.
        for p in rp:
                if "$" in p:
                        tok = p[p.find("$"):]
                        if "/" in tok:
                                tok = tok[:tok.find("/")]
                        print "%s has dynamic token %s in rpath" % (path, tok)

        dep_pkgs = []
        undeps = []
        depend_list = []
        for d in deps:
                for p in rp:
                        # The instances of "[1:]" below are because usedlist
                        # stores paths without leading slash
                        if kernel64:
                                # Find 64-bit modules the way krtld does.
                                # XXX We don't resolve dependencies found in
                                # /platform, since we don't know where under
                                # /platform to look.
                                head, tail = os.path.split(d)
                                deppath = os.path.join(p,
                                                       head,
                                                       kernel64,
                                                       tail)[1:]
                        else:
                                # This is a hack for when a runpath uses the 64
                                # symlink to the actual 64-bit directory.
                                # Better would be to see if the runpath was a
                                # link, and if so, use its resolution, but
                                # extracting that information from used list is
                                # a pain, especially because you potentially
                                # have to resolve symlinks at all levels of the
                                # path.
                                if p.endswith("/64"):
                                        if ei["arch"] == "i386":
                                                p = p[:-2] + "amd64"
                                        elif ei["arch"] == "sparc":
                                                p = p[:-2] + "sparcv9"
                                deppath = os.path.join(p, d)[1:]
                        if deppath in usedlist:
                                dep_pkgs += [ "%s@%s" %
                                    (usedlist[deppath][1].name,
                                    usedlist[deppath][1].version) ]
                                depend_list.append(
                                        (
                                                deppath,
                                                usedlist[deppath][1].name
                                                )
                                        )
                                break
                else:
                        undeps += [ d ]

        if show_debug:
                print "%s makes %s depend on %s" % \
                    (path, usedlist[path][1].name, depend_list)

        return dep_pkgs, undeps

def zap_strings(instr, strings):
        """takes an input string and a list of strings to be removed, ignoring
        case"""
        for s in strings:
                ls = s.lower()
                while True:
                        li = instr.lower()
                        i = li.find(ls)
                        if i < 0:
                                break
                        instr = instr[0:i] + instr[i + len(ls):]
        return instr 

def get_branch(name):
        return branch_dict.get(name, def_branch)

def_vers = "0.5.11"
def_branch = ""
def_wos_path = ["/net/netinstall.eng/export/nv/x/latest/Solaris_11/Product"]
nopublish = False
show_debug = False
def_repo = "http://localhost:10000"
wos_path = []
include_path = []
branch_dict = {}
timestamp_files = []

#
# files (by path) we always delete for bulk imports
# note that we ignore these if specifically included.
#
elided_files = {}
#
# if user uses -j, just_these_pkgs becomes list of pkgs to process
# allowing other arguments to be read in as files...
#
just_these_pkgs = []
#
# strings to rip out of descriptions (case insensitve)
#
description_detritus = [", (usr)", ", (root)", " (usr)", " (root)",
" (/usr)", " - / filesystem", ",root(/)"]
#
# list of global includes to add to every package
#
global_includes = []
# list of macro substitutions
macro_definitions = {}

try:
        _opts, _args = getopt.getopt(sys.argv[1:], "B:D:I:G:T:b:dj:m:ns:v:w:p:")
except getopt.GetoptError, _e:
        print "unknown option", _e.opt
        sys.exit(1)

g_proto_area = os.environ.get("ROOT", "")

for opt, arg in _opts:
        if opt == "-b":
                def_branch = arg.rstrip("abcdefghijklmnopqrstuvwxyz")
        elif opt == "-d":
                show_debug = True
        elif opt == "-j": # means we're using the new argument form...
                just_these_pkgs.append(arg)
        elif opt == "-m":
                _a = arg.split("=", 1)
                macro_definitions.update([("$(%s)" % _a[0], _a[1])])
        elif opt == "-n":
                nopublish = True
        elif opt == "-p":
                if not os.path.exists(arg):
                        raise RuntimeError("Invalid prototype area specified.")
                # Clean up relative ../../, etc. out of path to proto
                g_proto_area = os.path.realpath(arg)
        elif  opt == "-s":
                def_repo = arg
        elif opt == "-v":
                def_vers = arg
        elif opt == "-w":
                wos_path.append(arg)
        elif opt == "-D":
                elided_files[arg] = True
        elif opt == "-I":
                include_path.extend(arg.split(":"))
        elif opt == "-B":
                branch_file = file(arg)
                for _line in branch_file:
                        if not _line.startswith("#"):
                                bfargs = _line.split()
                                if len(bfargs) == 2:
                                        branch_dict[bfargs[0]] = bfargs[1]
                branch_file.close()
        elif opt == "-G": #another file of global includes
                global_includes.append(arg)
        elif opt == "-T":
                timestamp_files.append(arg)

if not def_branch:
        print "need a branch id (build number)"
        sys.exit(1)
elif "." not in def_branch:
        print "branch id needs to be of the form 'x.y'"
        sys.exit(1)

if not _args:
        print "need argument!"
        sys.exit(1)

if not wos_path:
        wos_path = def_wos_path

if just_these_pkgs:
        filelist = _args
else:
        filelist = _args[0:1]
        just_these_pkgs = _args[1:]


in_multiline_import = False

# This maps what files we've seen to a tuple of what packages they came from and
# what packages they went into, so we can prevent more than one package from
# grabbing the same file.
usedlist = {}

#
# pkgdict contains ipkgs by name
#
pkgdict = {}

#
# destpkgs contains the list of ipkgs generated from each svr4 pkg
# this is needed to generate metaclusters
#
destpkgs = {}

#
#svr4 pkgs seen - pkgs indexed by name
#
svr4pkgsseen = {}

#
#paths where we found the packages we need
#
svr4pkgpaths = {}

#
# editable files and where they're found
#
editable_files = {}

#
# hollow svr4 packages processed
#
hollow_pkgs = {}


reuse_err = \
    "Conflict in path %s: IPS %s SVR4 %s from %s with IPS %s SVR4 %s from %s"

print "First pass:", datetime.now()


# First pass: don't actually publish anything, because we're not collecting
# dependencies here.
def read_full_line(lexer, continuation='\\'):
        """Read a complete line, allowing for the possibility of it being
        continued over multiple lines.  Returns a single joined line, with
        continuation characters and leading and trailing spaces removed.
        """

        lines = []
        while True:
                line = lexer.instream.readline().strip()
                lexer.lineno = lexer.lineno + 1
                if line[-1] in continuation:
                        lines.append(line[:-1])
                else:
                        lines.append(line)
                        break

        return apply_macros(' '.join(lines))

def apply_macros(s):
        """Apply macro subs defined on command line... keep applying
        macros until no translations are found.  If macro translates
        to a comment, replace entire token text."""
        while s and "$(" in s:
                for key in macro_definitions.keys():
                        if key in s:
                                value = macro_definitions[key]
                                if value == "#": # comment character
                                        s = "#"  # affects whole token
                                        break
                                s = s.replace(key, value)
                                break # look for more substitutions
                else:
                        break # no more substitutable tokens
        return s

def sourcehook(filename):
        """ implement include hierarchy """
        for i in include_path:
                f = os.path.join(i, filename)
                if os.path.exists(f):
                        return (f, open(f))

        return filename, open(filename)

class tokenlexer(shlex.shlex):
        def read_token(self):
                """ simple replacement of $(ARCH) with a non-special
                value defined on the command line is trivial.  Since
                shlex's read_token routine also strips comments and
                white space, this read_token cannot return either 
                one so any macros that translate to either spaces or
                # (comment) need to be removed from the token stream."""

                while True:
                        s = apply_macros(shlex.shlex.read_token(self))
                        if s == "#": # discard line if comment; try again
                                self.instream.readline()
                                self.lineno = self.lineno + 1
                        # bail on EOF or not space; loop on space
                        elif s == None or (s != "" and not s.isspace()):
                                break
                return s

curpkg = None
def SolarisParse(mf):
        global curpkg
        global in_multiline_import

        lexer = tokenlexer(file(mf), mf, True)
        lexer.whitespace_split = True
        lexer.source = "include"
        lexer.sourcehook = sourcehook

        print "Processing %s" % lexer.infile

        while True:
                token = lexer.get_token()

                if not token:
                        break

                if token == "package":
                        curpkg = start_package(lexer.get_token())

                elif token == "end":
                        endarg = lexer.get_token()
                        if endarg == "package":
                                for filename in global_includes:
                                        for i in include_path:
                                                f = os.path.join(i, filename)
                                                if os.path.exists(f):
                                                        SolarisParse(f)
                                                        break
                                        else:
                                                raise RuntimeError("File not "
                                                    "found: %s" % filename)
                                try:
                                        end_package(curpkg)
                                except Exception, e:
                                        print "ERROR(end_pkg):", e

                                curpkg = None
                        if endarg == "import":
                                in_multiline_import = False
                                curpkg.imppkg = None

                elif token == "version":
                        curpkg.version = lexer.get_token()

                elif token == "import":
                        package_name = lexer.get_token()
                        next = lexer.get_token()
                        if next != "exclude":
                                line = ""
                                lexer.push_token(next)
                        else:
                                line = read_full_line(lexer)

                        curpkg.import_pkg(package_name, line)

                elif token == "from":
                        pkgspec = lexer.get_token()
                        p = SolarisPackage(pkg_path(pkgspec))
                        curpkg.imppkg = p
                        spkgname = p.pkginfo["PKG.PLAT"]
                        svr4pkgpaths[spkgname] = pkg_path(pkgspec)
                        svr4pkgsseen[spkgname] = p
                        curpkg.add_svr4_src(spkgname)

                        junk = lexer.get_token()
                        assert junk == "import"
                        in_multiline_import = True

                elif token == "classification":
                        cat_subcat = lexer.get_token()
                        curpkg.classification = \
                            "org.opensolaris.category.2008:%s" % cat_subcat

                elif token == "description":
                        curpkg.desc = lexer.get_token()

                elif token == "depend":
                        curpkg.depend.append(lexer.get_token())

                elif token == "cluster":
                        curpkg.add_svr4_src(lexer.get_token())

                elif token == "idepend":
                        curpkg.idepend.append(lexer.get_token())

                elif token == "undepend":
                        curpkg.undepend.append(lexer.get_token())

                elif token == "add":
                        curpkg.extra.append(read_full_line(lexer))

                elif token == "drop":
                        f = lexer.get_token()
                        l = [o for o in curpkg.files if o.pathname == f]
                        if not l:
                                print "Cannot drop '%s' from '%s': not " \
                                    "found" % (f, curpkg.name)
                        else:
                                del curpkg.files[curpkg.files.index(l[0])]
                                # XXX The problem here is that if we do this on
                                # a shared file (directory, etc), then it's
                                # missing from usedlist entirely, since we don't
                                # keep around *all* packages delivering a shared
                                # file, just the last seen.  This probably
                                # doesn't matter much.
                                del usedlist[f]

                elif token == "chattr":
                        fname = lexer.get_token()
                        line = read_full_line(lexer)
                        try:
                                curpkg.chattr(fname, line)
                        except Exception, e:
                                print "Can't change attributes on " + \
                                    "'%s': not in the package" % fname, e
                                raise

                elif token == "chattr_glob":
                        glob = lexer.get_token()
                        line = read_full_line(lexer)
                        try:
                                curpkg.chattr_glob(glob, line)
                        except Exception, e:
                                print "Can't change attributes on " + \
                                    "'%s': no matches in the package" % \
                                    glob, e
                                raise

                elif in_multiline_import:
                        next = lexer.get_token()
                        if next == "with":
                                # I can't imagine this is supported, but there's
                                # no other way to read the rest of the line
                                # without a whole lot more pain.
                                line = read_full_line(lexer)
                        else:
                                lexer.push_token(next)
                                line = ""

                        try:
                                curpkg.import_file(token, line)
                        except Exception, e:
                                print "ERROR(import_file):", e
                                raise
                else:
                        raise RuntimeError("Error: unknown token '%s' "
                            "(%s:%s)" % (token, lexer.infile, lexer.lineno))

for _mf in filelist:
        SolarisParse(_mf)

seenpkgs = set(i[0] for i in usedlist.values())

print "Files you seem to have forgotten:\n  " + "\n  ".join(
    "%s %s" % (f.type, f.pathname)
    for pkg in seenpkgs
    for f in svr4pkgsseen[pkg].manifest
    if f.type != "i" and f.pathname not in usedlist)

print "\n\nDuplicate Editables files list:\n"

if editable_files:
        length = 2 + max(len(p) for p in editable_files)
        for paths in editable_files:
                if len(editable_files[paths]) > 1:
                        print ("%s:" % paths).ljust(length - 1) + \
                            ("\n".ljust(length)).join("%s (from %s)" % \
                            (l[1].name, l[0]) for l in editable_files[paths])


# Second pass: iterate over the existing package objects, gathering dependencies
# and publish!

print "Second pass:", datetime.now()

print "New packages:\n"
# XXX Sort these.  Preferably topologically, if possible, alphabetically
# otherwise (for a rough progress gauge).
if just_these_pkgs:
        newpkgs = set(pkgdict[name]
                      for name in pkgdict.keys()
                      if name in just_these_pkgs
                      )
else:
        newpkgs = set(pkgdict.values())

# Indicates whether search indices refresh will be deferred until the end.
defer_refresh = False
# Indicates whether local publishing is active.
local_publish = False
if def_repo.startswith("file:"):
        # If publishing to disk, the search indices should be refreshed at
        # the end of the publishing process and the feed cache will have to be
        # generated by starting the depot server using the provided path and
        # then accessing it.
        defer_refresh = True
        local_publish = True

processed = 0
total = len(newpkgs)
for _p in sorted(newpkgs):
        print "Package '%s'" % _p.name
        print "  Version:", _p.version
        print "  Description:", _p.desc
        print "  Classification:", _p.classification
        try:
                publish_pkg(_p)
        except trans.TransactionError, _e:
                print "%s: FAILED: %s\n" % (_p.name, _e)
        processed += 1
        print "%d/%d packages processed; %.2f%% complete" % (processed, total,
            processed * 100.0 / total)

if not nopublish and defer_refresh:
        # This has to be done at the end for some publishing modes.
        print "Updating search indices..."
        _t = trans.Transaction(def_repo)
        _t.refresh_index()

# Ensure that the feed is updated and cached to reflect changes.
if not nopublish:
        print "Caching RSS/Atom feed..."
        dc = None
        durl = def_repo
        if local_publish:
                # The depot server isn't already running, so will have to be
                # temporarily started to allow proper feed cache generation.
                dc = depotcontroller.DepotController()
                dc.set_depotd_path(g_proto_area + "/usr/lib/pkg.depotd")
                dc.set_depotd_content_root(g_proto_area + "/usr/share/lib/pkg")

                _scheme, _netloc, _path, _params, _query, _fragment = \
                    urlparse.urlparse(def_repo, "file", allow_fragments=0)

                dc.set_repodir(_path)

                # XXX There must be a better way...
                dc.set_port(29083)

                # Start the depot
                dc.start()

                durl = "http://localhost:29083"

        _f = urllib.urlopen("%s/feed" % durl)
        _f.close()

        if dc:
                dc.stop()
                dc = None

print "Done:", datetime.now()
