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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.


import getopt
import os
import shlex
import sys
import fnmatch
import re

from datetime import datetime
from itertools import groupby
from tempfile import mkstemp

from pkg.sysvpkg import SolarisPackage
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle

import pkg.config as config
import pkg.publish.transaction as trans
from pkg import actions, elf

class pkg(object):
        def __init__(self, name):
                self.name = name
                self.files = []
                self.depend = []
                self.idepend = []     #svr4 pkg deps, if any
                self.undepend = []
                self.extra = []
                self.nonhollow_dirs = {}
                self.srcpkgs = []
                self.desc = ""
                self.version = ""
                self.imppkg = None
                pkgdict[name] = self

        def import_pkg(self, imppkg, line):
                try:
                        p = SolarisPackage(pkg_path(imppkg))
                except:
                        raise RuntimeError, "No such package: '%s'" % imppkg

                self.imppkg = p

                svr4pkgpaths[p.pkginfo["PKG"]] = pkg_path(imppkg)

                imppkg = p.pkginfo["PKG"] # filename NOT always same as pkgname
                svr4pkgsseen[imppkg] = p;

                if "SUNW_PKG_HOLLOW" in p.pkginfo and \
                    p.pkginfo["SUNW_PKG_HOLLOW"].lower() == "true":
                        hollow_pkgs[imppkg] = True

                excludes = dict((f, True) for f in line.split())

                # XXX This isn't thread-safe.  We want a dict method that adds
                # the key/value pair, but throws an exception if the key is
                # already present.
                for o in p.manifest:
                        if o.pathname in excludes:
                                print "excluding %s from %s" % (o.pathname, imppkg)
                                continue

                        if o.pathname in elided_files:
                                print "ignoring %s in %s" % (o.pathname, imppkg)
                                continue

                        if o.type == "e":
                                   if o.pathname not in editable_files:
                                        editable_files[o.pathname] = [(imppkg, self)]
                                   else :
                                        editable_files[o.pathname].append((imppkg, self))

                        # XXX This decidedly ignores "e"-type files.

                        if o.type in "fv" and o.pathname in usedlist:
                                print reuse_err % (
                                        o.pathname, 
                                        self.name, 
                                        imppkg, 
                                        svr4pkgpaths[imppkg], 
                                        usedlist[o.pathname][1].name,
                                        usedlist[o.pathname][0], 
                                        svr4pkgpaths[usedlist[o.pathname][0]])
                        elif o.type != "i":

                                if o.type in "dx" and imppkg not in hollow_pkgs:
                                        self.nonhollow_dirs[o.pathname] = True
                                        
                                usedlist[o.pathname] = (imppkg, self)
                                self.check_perms(o)
                                self.files.append(o)

                if not self.version:
                        self.version = "%s-%s" % (def_vers, def_branch)
                if not self.desc:
                        self.desc = p.pkginfo["NAME"]

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

        def import_file(self, file, line):
                imppkgname = self.imppkg.pkginfo["PKG"]

                if "SUNW_PKG_HOLLOW" in self.imppkg.pkginfo and \
                    self.impkpkg.pkginfo["SUNW_PKG_HOLLOW"].lower() == "true":
                        hollow_pkgs[imppkgname] = True

                if file in usedlist:
                        t = [
                            f
                            for f in usedlist[file][1].files
                            if f.pathname == file
                        ][0].type
                        if t in "fv":
                                assert imppkgname == usedlist[file][0]
                                raise RuntimeError, reuse_err % (
                                        file, 
                                        self.name, 
                                        imppkg, 
                                        svr4pkgpaths[imppkg], 
                                        usedlist[file][1].name,
                                        usedlist[file][0], 
                                        svr4pkgpaths[usedlist[file][0]])

                usedlist[file] = (imppkgname, self)
                o = [
                    o
                    for o in self.imppkg.manifest
                    if o.pathname == file
                ]
                # There should be only one file with a given pathname in a
                # single package.
                if len(o) != 1:
                        print "ERROR: %s %s" % (imppkgname, file)
                        assert len(o) == 1
                        
                if line:
                        a = actions.fromstr(
                            "%s path=%s %s" % (self.convert_type(o[0].type), o[0].pathname, 
                            line))
                        for attr in a.attrs:
                                if attr == "owner":
                                        o[0].owner = a.attrs[attr]
                                elif attr == "group":
                                        o[0].group = a.attrs[attr]
                                elif attr == "mode":
                                        o[0].mode = a.attrs[attr]
                self.check_perms(o[0])
                self.files.extend(o)

        def convert_type(self, type):
                return {
                        "f": "file", "e": "file", "v": "file",
                        "d": "dir", "x": "dir",
                        "s": "link",
                        "l": "hardlink"
                        }[type]

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
                        (pkg.name, f.pathname, f.target)
                        action = actions.hardlink.HardLinkAction(None,
                            target = f.target, path = f.pathname)
                else:
                        print "unknown type %s - path %s" % ( f.type, f.pathname)

                return action
        
        def check_perms(self, manifest):
                if manifest.type not in "fevdxbc":
                        return

                if manifest.owner == "?":
                        manifest.owner = "root"
                        print "File %s in pkg %s owned by '?': mapping to %s" % \
                            (manifest.pathname, self.name, manifest.owner)

                if manifest.group == "?":
                        manifest.group = "bin"
                        print "File %s in pkg %s of group '?': mapping to %s" % \
                            (manifest.pathname, self.name, manifest.group)
                if manifest.mode == "?":
                        manifest.mode = "0444"
                        print "File %s in pkg %s mode '?': mapping to %s" % \
                            (manifest.pathname, self.name, manifest.mode)


        def chattr(self, file, line):
                o = [f for f in self.files if f.pathname == file]
                if not o:
                        raise RuntimeError, "No file '%s' in package '%s'" % \
                            (file, curpkg.name)
                # It's probably a file, but all we care about are the
                # attributes.
                if show_debug:
                        print "Updating attributes on '%s' in '%s' with '%s'" % \
                            (file, curpkg.name, line)

                a = actions.fromstr(("%s path=%s %s" % (self.convert_type(f.type), 
                    file, line)).rstrip())
                o[0].changed_attrs = a.attrs

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
                                usedlist[f.pathname][0], pkgglob)
                     ]

                chattr_line = line

                for f in o:
                        file = f.pathname
                        
                        if edit:
                                a = self.file_to_action(f)
                                old_value = a.attrs[target]
                                new_value = regexp.sub(replace, old_value)
                                if old_value == new_value:
                                        continue

                                chattr_line = "%s=%s %s" % (target, new_value, line)
			chattr_line = chattr_line.rstrip()
                        if show_debug:
                                print "Updating attributes on '%s' in '%s' with '%s'" % \
                                    (file, curpkg.name, chattr_line)
                        s = "%s path=%s %s" % (self.convert_type(f.type), file, chattr_line)
			a = actions.fromstr(s)
			f.changed_attrs = a.attrs
                

def sysv_to_new_name(pkgname):
        return "pkg:/" + os.path.basename(pkgname)


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

                raise RuntimeError, "package %s not found" % pkgname


def start_package(pkgname):
        return pkg(pkgname)

def end_package(pkg):
        if not pkg.version:
                pkg.version = "%s-%s" % (def_vers, def_branch)
        elif "-" not in pkg.version:
                pkg.version += "-%s" % def_branch

        print "Package '%s'" % sysv_to_new_name(pkg.name)
        print "  Version:", pkg.version
        print "  Description:", pkg.desc

def publish_pkg(pkg):
        
        t = trans.Transaction()

        if nopublish:
                # Give t some bogus methods so that it won't actually touch the
                # server, and just return reasonable information.
                t.open = lambda a, b: (200, 1000)
                t.add = lambda a, b, c: None
                t.close = lambda a, b, c: (200, {
                    "Package-FMRI": 
                        "%s@%s" % (sysv_to_new_name(pkg.name), pkg.version),
                    "State": "PUBLISHED"
                })

        cfg = config.ParentRepo(def_repo, [def_repo])
        print "    open %s@%s" % (sysv_to_new_name(pkg.name), pkg.version)
        status, id = t.open(cfg, "%s@%s" % (sysv_to_new_name(pkg.name), pkg.version))
        if status / 100 in (4, 5) or not id:
                raise RuntimeError, "failed to open transaction for %s" % pkg.name

        # Publish non-file objects first: they're easy.
        for f in pkg.files:
                if f.type in "dx":
                        print "    %s add dir %s %s %s %s" % \
                            (pkg.name, f.mode, f.owner, f.group, f.pathname)
                        action = actions.directory.DirectoryAction(
                            None, mode = f.mode, owner = f.owner,
                            group = f.group, path = f.pathname)
                elif f.type == "s":
                        print "    %s add link %s %s" % \
                            (pkg.name, f.pathname, f.target)
                        action = actions.link.LinkAction(None,
                            target = f.target, path = f.pathname)
                elif f.type == "l":
                        print "    %s add hardlink %s %s" % \
                            (pkg.name, f.pathname, f.target)
                        action = actions.hardlink.HardLinkAction(None,
                            target = f.target, path = f.pathname)
                        pkg.depend += process_link_dependencies(
                            f.pathname, f.target)
                else:
                        continue
                #
                # If the originating package was hollow, tag this file
                # as being global zone only.
                #
                if f.type not in "dx" and \
                    usedlist[f.pathname][0] in hollow_pkgs:
                        action.attrs["opensolaris.zone"] = "global"

                if f.type in "dx" and \
                    usedlist[f.pathname][0] in hollow_pkgs and \
                    f.pathname not in pkg.nonhollow_dirs:
                        action.attrs["opensolaris.zone"] = "global"

                t.add(cfg, id, action)

        # Group the files in a (new) package based on what (old) package they
        # came from, so that we can iterate through all files in a single (old)
        # package (and, therefore, in a single bzip2 archive) before moving on
        # to the next.
        def fn(key):
                return usedlist[key.pathname][0]
        groups = []
        for k, g in groupby((f for f in pkg.files if f.type in "fev"), fn):
                groups.append(list(g))

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
        for g in groups:
                pkgname = usedlist[g[0].pathname][0]
                print "pulling files from archive in package", pkgname
                bundle = SolarisPackageDirBundle(svr4pkgpaths[pkgname])
                pathdict = dict((f.pathname, f) for f in g)
                for f in bundle:
                        if f.name == "license":
                                t.add(cfg, id, f)
                        elif f.attrs["path"] in pathdict:
                                if pkgname in hollow_pkgs:
                                        f.attrs["opensolaris.zone"] = "global"
                                path = f.attrs["path"]
                                if pathdict[path].type in "ev":
                                        f.attrs["preserve"] = "true"
                                f.attrs["owner"] = pathdict[path].owner
                                f.attrs["group"] = pathdict[path].group
                                f.attrs["mode"] = pathdict[path].mode
                                if pathdict[path].klass in preserve_dict.keys():
                                        f.attrs["preserve"] = \
                                            preserve_dict[pathdict[path].klass]
                                if hasattr(pathdict[path], "changed_attrs"):
                                        f.attrs.update(
                                            pathdict[path].changed_attrs)
                                        # chattr may have produced two path values
                                        f.attrs["path"] = f.attrlist("path")[-1]
                                print "    %s add file %s %s %s %s%s" % \
                                    (pkg.name, f.attrs["mode"],
                                        f.attrs["owner"], f.attrs["group"],
                                        f.attrs["path"], otherattrs(f))
                                # Write the file to a temporary location.
                                d = f.data().read()
                                fd, tmp = mkstemp(prefix="pkg.")
                                os.write(fd, d)
                                os.close(fd)

                                # Fool the action into pulling from the
                                # temporary file.
                                f.data = lambda: open(tmp)
                                t.add(cfg, id, f)

                                # Look for dependencies
                                deps, u = process_dependencies(tmp, path)
                                pkg.depend += deps
                                if u:
                                        print "%s has missing dependencies: %s" % \
                                            (path, u)
                                undeps |= set(u)
                                os.unlink(tmp)              

        # Publish dependencies

        missing_cnt = 0

        for p in set(pkg.idepend):              # over set of svr4 deps, append ipkgs
                if p in destpkgs:
                        pkg.depend.extend(destpkgs[p]) 
                else:
                        print "pkg %s: SVR4 package %s not seen" % \
                            (pkg.name, p)
                        missing_cnt += 1
        if missing_cnt > 0:
                raise RuntimeError, "missing packages!"

        for p in set(pkg.depend) - set(pkg.undepend):
                # Don't make a package depend on itself.
                if p[:len(pkg.name)] == pkg.name:
                        continue
                # enhance unqualified dependencies to include current pkg version
                if "@" not in p and p in pkgdict:
                        p = "%s@%s" % (p, pkgdict[p].version)

                print "    %s add depend require %s" % \
                    (pkg.name, sysv_to_new_name(p))
                action = actions.depend.DependencyAction(None,
                    type = "require", fmri = sysv_to_new_name(p))
                t.add(cfg, id, action)

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
                t.add(cfg, id, action)

        if pkg.desc:
                print "    %s add set description=%s" % (pkg.name, pkg.desc)
                action = actions.attribute.AttributeAction(None,
                    description = pkg.desc)
                t.add(cfg, id, action)

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

			action = actions.legacy.LegacyAction(None, **attrs)

			print "    %s add %s" % (pkg.name, action)
			t.add(cfg, id, action)

        if undeps:
                print "Missing dependencies:", list(undeps)

        print "    close"
        ret, hdrs = t.close(cfg, id, False)
        if hdrs:
                print "%s: %s" % (hdrs["Package-FMRI"], hdrs["State"])
        else:
                print "%s: FAILED" % pkg.name

        print

def process_link_dependencies(path, target):
        orig_target = target
        if target[0] != "/":
                target = os.path.normpath(
                    os.path.join(os.path.split(path)[0], target))

        if target in usedlist:
                if show_debug:
                        print "hardlink %s -> %s makes %s depend on %s" % \
                            (path, orig_target,
                                usedlist[path][1].name, usedlist[target][1].name)
                return ["%s@%s" % (usedlist[target][1].name,
                    usedlist[target][1].version)]
        else:
                return []

def process_dependencies(file, path):
        if not elf.is_elf_object(file):
                return [], []

        ei = elf.get_info(file)
        ed = elf.get_dynamic(file)
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
                        print "RUNPATH set for kernel module (%s): %s" % (path, rp)
                # Default kernel search path
                rp.extend(("/kernel", "/usr/kernel"));
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
                                deppath = os.path.join(p, head, kernel64, tail)[1:]
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
                                depend_list.append((deppath, usedlist[deppath][1].name))
                                break
                else:
                        undeps += [ d ]

        if show_debug:
                print "%s makes %s depend on %s" % (path, usedlist[path][1].name, depend_list)

        return dep_pkgs, undeps

def_vers = "0.5.11"
def_branch = ""
def_wos_path = ["/net/netinstall.eng/export/nv/x/latest/Solaris_11/Product"]
nopublish = False
show_debug = False
def_repo = "http://localhost:10000"
wos_path = []
#
# files (by path) we always delete for bulk imports
# note that we ignore these if specifically included.
#
elided_files = {}

try:
        opts, args = getopt.getopt(sys.argv[1:], "D:b:dns:v:w:")
except getopt.GetoptError, e:
        print "unknown option", e.opt
        sys.exit(1)

for opt, arg in opts:
        if opt == "-b":
                def_branch = arg
        elif opt == "-d":
                show_debug = True
        elif opt == "-n":
                nopublish = True
        elif  opt == "-s":
                def_repo = arg
        elif opt == "-v":
                def_vers = arg
        elif opt == "-w":
                wos_path.append(arg)
        elif opt == "-D":
                elided_files[arg] = True

if not def_branch:
        try:
                pkgpath = pkg_path("SUNWsolnm")
                release_file = pkgpath + "/reloc/etc/release"
                if os.path.isfile(release_file):
                        rf = file(release_file)
                        l = rf.readline()
                        idx = l.index("nv_") + 3
                        def_branch = "0." + l[idx:idx+2]
                        rf.close()        
        except:
                pass

if not def_branch:
        print "need a branch id (build number)"
        sys.exit(1)
elif "." not in def_branch:
        print "branch id needs to be of the form 'x.y'"
        sys.exit(1)

if not args:
        print "need argument!"
        sys.exit(1)

if not wos_path:
        wos_path = def_wos_path

infile = file(args[0])
lexer = shlex.shlex(infile, args[0], True)
lexer.whitespace_split = True
lexer.source = "include"

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


reuse_err = "Conflict in path %s: IPS %s SVR4 %s from %s with IPS %s SVR4 %s from %s"

print "First pass:", datetime.now()

# First pass: don't actually publish anything, because we're not collecting
# dependencies here.
while True:
        token = lexer.get_token()

        if not token:
                break

        if token == "package":
                curpkg = start_package(lexer.get_token())

        elif token == "end":
                endarg = lexer.get_token()
                if endarg == "package":
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
                        line = lexer.instream.readline().strip()

                curpkg.import_pkg(package_name, line)

        elif token == "from":
                pkgspec = lexer.get_token()
                p = SolarisPackage(pkg_path(pkgspec))
                curpkg.imppkg = p
                spkgname = p.pkginfo["PKG"]
                svr4pkgpaths[spkgname] = pkg_path(pkgspec)
                svr4pkgsseen[spkgname] = p;
                curpkg.add_svr4_src(spkgname)

                junk = lexer.get_token()
                assert junk == "import"
                in_multiline_import = True

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
                curpkg.extra.append(lexer.instream.readline().strip())

        elif token == "drop":
                f = lexer.get_token()
                l = [o for o in curpkg.files if o.pathname == f]
                if not l:
                        print "Cannot drop '%s' from '%s': not found" % \
                            (f, curpkg.name)
                else:
                        del curpkg.files[curpkg.files.index(l[0])]
                        # XXX The problem here is that if we do this on a shared
                        # file (directory, etc), then it's missing from usedlist
                        # entirely, since we don't keep around *all* packages
                        # delivering a shared file, just the last seen.  This
                        # probably doesn't matter much.
                        del usedlist[f]

        elif token == "chattr":
                fname = lexer.get_token()
                line = lexer.instream.readline().strip()
                try:
                        curpkg.chattr(fname, line)
                except Exception, e:
                        print "Can't change attributes on '%s': not in the package" % \
                            fname, e
                        raise

        elif token == "chattr_glob":
                glob = lexer.get_token()
                line = lexer.instream.readline().strip()
                try:
                        curpkg.chattr_glob(glob, line)
                except Exception, e:
                        print "Can't change attributes on '%s': no matches in the package" % \
                            glob, e
                        raise

        elif in_multiline_import:
                next = lexer.get_token()
                if next == "with":
                        # I can't imagine this is supported, but there's no
                        # other way to read the rest of the line without a whole
                        # lot more pain.
                        line = lexer.instream.readline().strip()
                else:
                        lexer.push_token(next)
                        line = ""

                try:
                        curpkg.import_file(token, line)
                except Exception, e:
                        print "ERROR(import_file):", e
                        raise
        else:
                raise "Error: unknown token '%s' (%s:%s)" % \
                    (token, lexer.infile, lexer.lineno)

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
                            ("\n".ljust(length)).join("%s (from %s)" % (l[1].name, l[0])
                            for l in editable_files[paths])


# Second pass: iterate over the existing package objects, gathering dependencies
# and publish!

print "Second pass:", datetime.now()

print "New packages:\n"
# XXX Sort these.  Preferably topologically, if possible, alphabetically
# otherwise (for a rough progress gauge).
if args[1:]:
        newpkgs = set(pkgdict[name] for name in pkgdict.keys() if name in args[1:])
else:
        newpkgs = set(pkgdict.values())
for p in sorted(newpkgs):
        print "Package '%s'" % sysv_to_new_name(p.name)
        print "  Version:", p.version
        print "  Description:", p.desc
        publish_pkg(p)

print "Done:", datetime.now()
