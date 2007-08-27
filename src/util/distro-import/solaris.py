#!/usr/bin/python

import getopt
import os
import shlex
import sys

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
                self.undepend = []
                self.extra = []
                self.desc = ""
                self.version = ""
                self.imppkg = None

        def import_pkg(self, imppkg):
                try:
                        p = SolarisPackage(pkg_path(imppkg))
                except:
                        raise RuntimeError, "No such package: '%s'" % imppkg

                self.files.extend(
                    o
                    for o in p.manifest
                    if o.type != "i"
                )

                # XXX This isn't thread-safe.  We want a dict method that adds
                # the key/value pair, but throws an exception if the key is
                # already present.
                for o in p.manifest:
                        # XXX This decidedly ignores "e"-type files.
                        if o.type in "fv" and o.pathname in usedlist:
                                raise RuntimeError, reuse_err % \
                                    (o.pathname, imppkg, self.name,
                                        usedlist[o.pathname][1].name)
                        elif o.type != "i":
                                usedlist[o.pathname] = (imppkg, self)

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

        def import_file(self, file):
                imppkgname = self.imppkg.pkginfo["PKG"]

                if file in usedlist:
                        t = [
                            f
                            for f in usedlist[file][1].files
                            if f.pathname == file
                        ][0].type
                        if t in "fv":
                                assert imppkgname == usedlist[file][0]
                                raise RuntimeError, reuse_err % \
                                    (file, imppkgname, self.name,
                                        usedlist[file][1].name)

                usedlist[file] = (imppkgname, self)
                self.files.extend(
                    o
                    for o in self.imppkg.manifest
                    if o.pathname == file
                )

def sysv_to_new_name(pkgname):
        return "pkg:/" + pkgname

def pkg_path(pkgname):
        return wos_path + "/" + pkgname

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

        cfg = config.ParentRepo("http://localhost:10000", ["http://localhost:10000"])
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
                        t.add(cfg, id, action)
                elif f.type == "s":
                        print "    %s add link %s %s" % \
                            (pkg.name, f.pathname, f.target)
                        action = actions.link.LinkAction(None,
                            target = f.target, path = f.pathname)
                        t.add(cfg, id, action)
                elif f.type == "l":
                        print "    %s add hardlink %s %s" % \
                            (pkg.name, f.pathname, f.target)
                        action = actions.hardlink.HardLinkAction(None,
                            target = f.target, path = f.pathname)
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

        undeps = set()
        for g in groups:
                pkgname = usedlist[g[0].pathname][0]
                print "pulling files from archive in package", pkgname
                bundle = SolarisPackageDirBundle(pkg_path(pkgname))
                ng = [f.pathname for f in g]
                for f in bundle:
                        path = f.attrs["path"]
                        if path in ng:
                                print "    %s add file %s %s %s %s" % \
                                    (pkg.name, f.attrs["mode"],
                                        f.attrs["owner"], f.attrs["group"],
                                        path)
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
        for p in set(pkg.depend) - set(pkg.undepend):
                # Don't make a package depend on itself.
                if p[:len(pkg.name)] == pkg.name:
                        continue
                print "    %s add depend require %s" % \
                    (pkg.name, sysv_to_new_name(p))
                action = actions.depend.DependencyAction(None,
                    type = "require", fmri = sysv_to_new_name(p))
                t.add(cfg, id, action)

        for a in pkg.extra:
                print "    %s add %s" % (pkg.name, a)
                action = actions.fromstr(a)
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
                                break
                else:
                        undeps += [ d ]

        return dep_pkgs, undeps

def_vers = "0.5.11"
def_branch = ""
wos_path = "/net/netinstall.eng/export/nv/s/latest/Solaris_11/Product"
nopublish = False

try:
        opts, args = getopt.getopt(sys.argv[1:], "b:nv:w:")
except getopt.GetoptError, e:
        print "unknown option", e.opt
        sys.exit(1)

# Quick, icky hack.
if "i386" in args[0]:
        wos_path = wos_path.replace("/s/", "/x/")

for opt, arg in opts:
        if opt == "-b":
                def_branch = arg
        elif opt == "-n":
                nopublish = True
        elif opt == "-v":
                def_vers = arg
        elif opt == "-w":
                wos_path = arg

if not def_branch:
        release_file = wos_path + "/SUNWsolnm/reloc/etc/release"
        if os.path.isfile(release_file):
                rf = file(release_file)
                l = rf.readline()
                idx = l.index("nv_") + 3
                def_branch = "0." + l[idx:idx+2]
                rf.close()
if not def_branch:
        print "need a branch id (build number)"
        sys.exit(1)
elif "." not in def_branch:
        print "branch id needs to be of the form 'x.y'"
        sys.exit(1)

if not args:
        print "need argument!"
        sys.exit(1)

infile = file(args[0])
lexer = shlex.shlex(infile, args[0], True)
lexer.whitespace_split = True
lexer.source = "include"

in_multiline_import = False

# This maps what files we've seen to a tuple of what packages they came from and
# what packages they went into, so we can prevent more than one package from
# grabbing the same file.
usedlist = {}

reuse_err = "Tried to put file '%s' from package '%s' into\n    '%s' as well as '%s'!"

print "First pass:", datetime.now()

# First pass: don't actually publish anything, because we're not collecting
# dependencies here.
while True:
        token = lexer.get_token()

        if not token:
                break

        # XXX want "from package import foobar with name=blah mode=blah etc"
        # XXX want "drop /usr/bin/foo"

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
                try:
                        curpkg.import_pkg(lexer.get_token())
                except Exception, e:
                        print "ERROR(import_pkg):", e

        elif token == "from":
                pkgname = lexer.get_token()
                curpkg.imppkg = SolarisPackage(pkg_path(pkgname))
                junk = lexer.get_token()
                assert junk == "import"
                in_multiline_import = True

        elif token == "description":
                curpkg.desc = lexer.get_token()

        elif token == "depend":
                curpkg.depend.append(lexer.get_token())

        elif token == "undepend":
                curpkg.undepend.append(lexer.get_token())

        elif token == "add":
                curpkg.extra.append(lexer.get_token())

        elif in_multiline_import:
                try:
                        curpkg.import_file(token)
                except Exception, e:
                        print "ERROR(import_file):", e
                        raise

        else:
                print "unknown token '%s' (%s:%s)" % \
                    (token, lexer.infile, lexer.lineno)

seenpkgs = set(i[0] for i in usedlist.values())

print "Files you seem to have forgotten:\n  " + "\n  ".join(
    "%s %s" % (f.type, f.pathname)
    for pkg in seenpkgs
    for f in SolarisPackage(pkg_path(pkg)).manifest
    if f.type != "i" and f.pathname not in usedlist
)

# Second pass: iterate over the existing package objects, gathering dependencies
# and publish!

print "Second pass:", datetime.now()

print "New packages:\n"
# XXX Sort these.  Preferably topologically, if possible, alphabetically
# otherwise (for a rough progress gauge).
if args[1:]:
        newpkgs = set(i[1] for i in usedlist.values() if i[1].name in args[1:])
else:
        newpkgs = set(i[1] for i in usedlist.values())
for p in sorted(newpkgs):
        print "Package '%s'" % sysv_to_new_name(p.name)
        print "  Version:", p.version
        print "  Description:", p.desc
        publish_pkg(p)

print "Done:", datetime.now()
