#!/usr/bin/python

import getopt
import os
import shlex
import sys

from itertools import groupby

from pkg.sysvpkg import SolarisPackage
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle

import pkg.config as config
import pkg.publish.transaction as trans
from pkg import actions

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
                                    (o.pathname, imppkg, self.name, usedlist[o.pathname][1])
                        elif o.type != "i":
                                usedlist[o.pathname] = (imppkg, self.name)

                if not self.version:
                        self.version = "%s-%s" % (def_vers, def_branch)
                if not self.desc:
                        self.desc = p.pkginfo["NAME"]

                # This is how we'd import dependencies, but we'll let the
                # analyzer do all the work here.
                # self.depend.extend(
                #     d.req_pkg_fmri
                #     for d in p.deps
                # )

        def import_file(self, file):
                imppkgname = self.imppkg.pkginfo["PKG"]

                if file in usedlist:
                        assert imppkgname == usedlist[file][0]
                        raise RuntimeError, reuse_err % \
                            (file, imppkgname, self.name, usedlist[file][1])

                usedlist[file] = (imppkgname, self.name)
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

        print "    open %s@%s" % (sysv_to_new_name(pkg.name), pkg.version)

        if not notransact:
                cfg = config.ParentRepo("http://localhost:10000", ["http://localhost:10000"])
                t = trans.Transaction()
                status, id = t.open(cfg, "%s@%s" % (sysv_to_new_name(pkg.name), pkg.version))
                if status / 100 in (4, 5) or not id:
                        raise RuntimeError, "failed to open transaction for %s" % pkg.name

        for f in pkg.files:
                if f.type in "dx":
                        print "    %s add dir %s %s %s %s" % \
                            (pkg.name, f.mode, f.owner, f.group, f.pathname)
                        if not notransact:
                                action = actions.directory.DirectoryAction(
                                    None, mode = f.mode, owner = f.owner,
                                    group = f.group, path = f.pathname)
                                t.add(cfg, id, action)
                elif f.type == "s":
                        print "    %s add link %s %s" % \
                            (pkg.name, f.pathname, f.target)
                        if not notransact:
                                action = actions.link.LinkAction(None,
                                    target = f.target, path = f.pathname)
                                t.add(cfg, id, action)
                elif f.type == "l":
                        print "    %s add hardlink %s %s" % \
                            (pkg.name, f.pathname, f.target)
                        if not notransact:
                                action = actions.hardlink.HardLinkAction(None,
                                    target = f.target, path = f.pathname)
                                t.add(cfg, id, action)

        def fn(key):
                return usedlist[key.pathname][0]
        groups = []
        for k, g in groupby((f for f in pkg.files if f.type in "fev"), fn):
                groups.append(list(g))

        for g in groups:
                pkgname = usedlist[g[0].pathname][0]
                print "new group", pkgname
                bundle = SolarisPackageDirBundle(pkg_path(pkgname))
                ng = [f.pathname for f in g]
                for f in bundle:
                        if f.attrs["path"] in ng:
                                print "    %s add file %s %s %s %s" % \
                                    (pkg.name, f.attrs["mode"],
                                        f.attrs["owner"], f.attrs["group"],
                                        f.attrs["path"])
                                if not notransact:
                                        t.add(cfg, id, f)

        for p in set(pkg.depend) - set(pkg.undepend):
                print "    %s add depend require %s" % \
                    (pkg.name, sysv_to_new_name(p))
                action = actions.depend.DependencyAction(None,
                    type = "require", fmri = sysv_to_new_name(p))
                if not notransact:
                        t.add(cfg, id, action)

        for a in pkg.extra:
                print "    %s add %s" % (pkg.name, a)
                action = actions.fromstr(a)
                if not notransact:
                        t.add(cfg, id, action)

        print "    close"
        if not notransact:
                ret, hdrs = t.close(cfg, id, False)
                if hdrs:
                        print "%s: %s" % (hdrs["Package-FMRI"], hdrs["State"])
                else:
                        print "%s: FAILED" % pkg.name

        print

def_vers = "0.5.11"
def_branch = ""
wos_path = "/net/netinstall.eng/export/nv/s/latest/Solaris_11/Product"
notransact = False

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
                notransact = True
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
                                print "ERROR:", e

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
                        print "ERROR:", e

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
                        print "ERROR:", e

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
