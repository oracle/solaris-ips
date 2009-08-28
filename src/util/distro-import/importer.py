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
import pkg.fmri
import pkg.publish.transaction as trans
import re
import shlex
import sys
import urllib
import urlparse

from datetime import datetime
from pkg import actions, elf
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle
from pkg.misc import versioned_urlopen
from tempfile import mkstemp

gettext.install("import", "/usr/lib/locale")

# rewrite of solaris.py to convert to actions as soon as possible;
# all chatters, etc. are performed before adding package contents
# to global name table. Actions are annotated to include svr4 source
# pkg & path


basename_dict = {}   # basenames to action lists
branch_dict = {}     # 
create_repo = False  #
curpkg = None        # which IPS package we're currently importing
defer_refresh = False
def_branch = ""      # default branch
def_repo = "http://localhost:10000"
def_vers = "0.5.11"  # default package version
# default search path
def_wos_path =  ["/net/netinstall.eng/export/nv/x/latest/Solaris_11/Product"]
elided_files = {}    # always delete these files; not checked on specific import
fmridict = {}        # all ips FMRIS known, indexed by name
global_includes = [] # include these for every package
include_path = []    # where to find inport files - searched in order
just_these_pkgs = [] # publish only thesee pkgs
macro_definitions = {} # list of macro substitutions
nopublish = False    # fake publication?
path_dict = {}       # map of paths to action lists
pkgdict = {}         # pkgdict contains Package objects we're importing by name
pkgpaths = {}        # where we found svr4 pkgs by name
pkgpath_dict = {}    # mapping of paths to ips pkg
print_pkg_names = False # jusr print package names seen
reference_uris = []  # list of url@pkg specs to compute dependencies against
show_debug = False   # print voluminous debug output
summary_detritus = [", (usr)", ", (root)", " (usr)", " (root)", " (/usr)",\
    " - / filesystem", ",root(/)"] # remove from summaries
svr4pkgsseen = {}    #svr4 pkgs seen - pkgs indexed by name
timestamp_files = [] # patterns of files that retain timestamps from svr4 pkgs
wos_path = []        # list of search pathes for svr4 packages


class Package(object):
        def __init__(self, name):
                self.name = name
                self.depend = []        # require dependencies
                self.file_depend = []   # file dependencies
                self.undepend = []
                self.extra = []
                self.dropped_licenses = []
                self.nonhollow_dirs = {}
                self.srcpkgs = []
                self.classification = []
                self.desc = ""
                self.summary = ""
                self.version = ""
                self.imppkg = None
                self.actions = []

                pkgdict[name] = self

        def fmristr(self):
                return "%s@%s" % (self.name, self.version)

        def import_pkg(self, imppkg_filename, line):
                exclude_files = line.split() + elided_files.keys()
                p = self.import_files_from_pkg(imppkg_filename,
                    [], exclude_files)

                if not self.version:
                        self.version = "%s-%s" % (def_vers,
                            get_branch(self.name))
                if not self.desc:
                        try:
                                self.desc = zap_strings(p.pkginfo["DESC"],
                                    summary_detritus)
                        except KeyError:
                                self.desc = None
                if not self.summary:
                        self.summary = zap_strings(p.pkginfo["NAME"],
                            summary_detritus)

        def add_svr4_src(self, imppkg):
                self.srcpkgs.append(imppkg)

        def import_files_from_pkg(self, imppkg_filename, includes, excludes):
                try:
                        ppath = pkg_path(imppkg_filename)
                except:
                        raise RuntimeError("No such package: '%s'" % imppkg_filename)

                bundle = SolarisPackageDirBundle(ppath, data=False)
                p = bundle.pkg
                imppkg_name = p.pkginfo["PKG.PLAT"]
                self.imppkg = bundle.pkg

                includes_seen = []

                # filename NOT always same as pkgname

                svr4pkgsseen[imppkg_name] = p

                if "SUNW_PKG_HOLLOW" in p.pkginfo and \
                    p.pkginfo["SUNW_PKG_HOLLOW"].lower() == "true":
                        hollow = True
                else:
                        hollow = False

                for action in bundle:
                        if includes:
                                if action.name == "license":
                                        pass # always include license.
                                elif "path" not in action.attrs or \
                                    action.attrs["path"] not in includes:
                                        continue
                                else:
                                        includes_seen.append(
                                            action.attrs["path"])

                        elif not includes and "path" in action.attrs and \
                            action.attrs["path"] in excludes:
                                if show_debug:
                                        print "excluding %s from %s" % \
                                            (action.attrs["path"], imppkg_name)
                                continue
 
                        if action.name == "unknown":
                                continue

                        action.attrs["importer.source"] = "svr4pkg"
                        action.attrs["importer.svr4pkg"] = imppkg_name
                        action.attrs["importer.svr4path"] = action.attrs["path"]

                        if action.name == "license":
                                # The "path" attribute is confusing and
                                # unnecessary for licenses.
                                del action.attrs["path"]

                        # is this a file for which we need a timestamp?
                        if action.name == "file":
                                basename = os.path.basename(action.attrs["path"])
                                for file_pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename, file_pattern):
                                                break
                                else:
                                        del action.attrs["timestamp"]

                        if hollow:
                                action.attrs["opensolaris.zone"] = "global"
                                action.attrs["variant.opensolaris.zone"] = "global"

                        self.check_perms(action)
                        self.actions.append(action)
                includes_missed = set(includes) - set(includes_seen)
                if includes_missed:
                        raise RuntimeError("pkg %s: Files specified in multi-line import from %s not seen: %s" %
                            (self.name, imppkg_name, " ".join(includes_missed)))
                self.add_svr4_src(imppkg_name)
                return p

        def import_files(self, imppkg_filename, filenames):
                self.import_files_from_pkg(imppkg_filename, filenames, [])

        def check_perms(self, action):
                if action.name not in ["file", "dir"]:
                        return
                orig = action.attrs.copy()

                if action.attrs["owner"] == "?":
                        action.attrs["owner"] = "root"
                if action.attrs["group"] == "?":
                        action.attrs["group"] = "bin"
                if action.attrs["mode"] == "?":
                        if action.name == "dir":
                                action.attrs["mode"] = "0755"
                        else:
                                action.attrs["mode"] = "0444"
                if orig != action.attrs:
                        for k in action.attrs:
                                if orig[k] != action.attrs[k]:
                                        print "File %s in pkg %s has %s == \"?\": mapped to %s" % \
                                            (
                                            action.attrs["path"],
                                            action.attrs["importer.svr4pkgname"],
                                            k,
                                            actions.attrs[k]
                                            )

        def chattr(self, fname, line):
                matches = [
                    a 
                    for a in self.actions
                    if "path" in a.attrs and a.attrs["path"] == fname
                ]

                if not matches:
                        raise RuntimeError("No file '%s' in package '%s'" % \
                            (fname, curpkg.name))

                line = line.rstrip()

                # is this a deletion?
                if line.startswith("drop"):
                        for f in matches:
                                # deletion of existing attribute
                                for d in line.split()[1:]:
                                        if d in f.attrs:
                                                del f.attrs[d]
                                                if show_debug:
                                                        print "removing attribute \"%s\" on %s" % \
                                                            (d, fname)
                        return

                # handle insertion/modification case
                for f in matches:
                        # create attribute dictionary from line
                        new_attrs = actions.attrsfromstr(line.rstrip())
                        f.attrs.update(new_attrs)
                        if show_debug:
                                print "Updating attributes on " + \
                                    "'%s' in '%s' with '%s'" % \
                                    (f.attrs["path"], curpkg.name, new_attrs)

        # apply a chattr to wildcarded files/dirs in current package
        # also allows regexp edit of existing attrs

        def chattr_glob(self, glob, line):
                args = line.split()

                if args[0] == "type": # we care about type
                        args.pop(0)
                        type= args.pop(0)
                        line = " ".join(args)
                else:
                        type = None

                if args[0] == "edit": # we're doing regexp edit of attr
                        edit = True
                        args.pop(0)
                        target = args.pop(0)
                        regexp = re.compile(args.pop(0))
                        replace = args.pop(0)
                        line = " ".join(args)
                else:
                        edit = False
                        new_attrs = actions.attrsfromstr(line.rstrip())

                o = [
                        f
                        for f in self.actions
                        if "path" in f.attrs and 
                            fnmatch.fnmatchcase(f.attrs["path"], glob) and
                            (not type or type == f.name)
                     ]

                for f in o:
                        fname = f.attrs["path"]
                        if edit:
                                if target in f.attrs:
                                        old_value = f.attrs[target]
                                        new_value = regexp.sub(replace, \
                                            old_value)
                                        if old_value == new_value:
                                                continue
                                        f.attrs[target] = new_value
                                else:
                                        continue
                        else:
                                f.attrs.update(new_attrs)
                                if show_debug:
                                        print "Updating attributes on " + \
                                            "'%s' in '%s' with '%s'" % \
                                            (fname, curpkg.name, new_attrs)

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

def check_pkg_actions(pkg):
        path_dict = {}
        # build dictionary of actions in pk by path
        for a in pkg.actions:
                if "path" in a.attrs:
                        path_dict.setdefault(a.attrs["path"], []).append(a)
        errors = check_pathdict_actions(path_dict, remove_dups=True)
        if errors:
                for e in errors:
                        print e
                raise RuntimeError("Package %s: errors occurred" % pkg.name)
        return path_dict

def check_pathdict_actions(path_dict, remove_dups=False):
        # investigate all paths w/ multiple actions
        errorlist = []
        for p in path_dict:
                if len(path_dict[p]) == 1:
                        continue

                dups = path_dict[p]
                # make sure all are the same type
                if len(set((d.name for d in dups))) > 1:
                        errorlist.append("Multiple actions on different types with the same path:\n\t%s\n" %
                            ("\n\t".join(str(d) for d in dups)))
                        # disallow any duplicates that aren't directories
                        continue

                elif dups[0].name == "license": #XXX double check this
                        continue

                elif dups[0].name == "link":
                        targets = set((d.attrs["target"] for d in dups))
                        if len(targets) > 1:
                                errorlist.append("Multiple link actions with same path and different targets:\n\t%s\n" %
                                    ("\n\t".join(str(d) for d in dups)))
                        continue
                        
                elif dups[0].name != "dir":
                        errorlist.append("Multiple actions with the same path that aren't directories:\n\t%s\n" %
                            ("\n\t".join(str(d) for d in dups)))
                        continue

                # construct glommed attrs dict; this check could be more thorough
                dkeys = set([
                    k
                    for d in dups
                    for k in d.attrs.keys()
                ])
                ga = dict(zip(dkeys, [set([d.attrs.get(k, None) for d in dups]) for k in dkeys]))
                for g in ga:
                        if len(ga[g]) == 1:
                                continue
                        if g in ["owner", "group", "mode"]:
                                errorlist.append("Multiple directory actions with the same path(%s) and different %s:\n\t%s\n" %
                                    (p, g, "\n\t".join(str(d) for d in dups)))
                        elif remove_dups and g.startswith("variant.") and None in ga[g]:
                                # remove any dirs that are zone variants if same dir w/o variant exists
                                for d in dups:
                                        if d.attrs.get(g) != None:
                                                d.attrs["importer.deleteme"] = "True"
                                                if 1 or show_debug:
                                                        print "removing %s as hollow dup" % d
                return errorlist

def start_package(pkgname):
        set_macro("PKGNAME", urllib.quote(pkgname, ""))
        return Package(pkgname)

def end_package(pkg):
        pkg_branch = get_branch(pkg.name)
        if not pkg.version:
                pkg.version = "%s-%s" % (def_vers, pkg_branch)
        elif "-" not in pkg.version:
                pkg.version += "-%s" % pkg_branch

       # add description actions
        if pkg.desc:
                pkg.actions.append( actions.attribute.AttributeAction(None,
                    name="pkg.description", value=pkg.desc))

        if pkg.summary:
                pkg.actions.extend([
                    actions.attribute.AttributeAction(None,
                        name="pkg.summary", value=pkg.summary),
                    actions.attribute.AttributeAction(None,
                        name="description", value=pkg.summary)
                ])
        if pkg.classification:
                pkg.actions.append(actions.attribute.AttributeAction(None,
                    name="info.classification", value=pkg.classification))

        # add legacy actions
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

                        pkg.actions.append(
                            actions.legacy.LegacyAction(None, **attrs))

        for action in pkg.actions[:]:
                action.attrs["importer.ipspkg"] = pkg.fmristr()
                if action.name == "license" and \
                    action.attrs["license"] in pkg.dropped_licenses:
                        del pkg.actions[pkg.actions.index(action)]

        # need to check for duplicate actions
        check_pkg_actions(pkg)
        # add to dictionary of known fmris
        fmridict[pkg.name] = pkg.fmristr()

        clear_macro("PKGNAME")
        print "Package '%s'" % pkg.name
        if not show_debug:
                return

        print "  Version:", pkg.version
        print "  Description:", pkg.desc
        print "  Summary:", pkg.summary
        print "  Classification: ", ",".join(pkg.classification)

def publish_action(t, pkg, a):
        # remove any temp attributes
        if show_debug:
                        print "%s: %s" % (pkg.name, a)

        for k in a.attrs.keys():
                if k.startswith("importer."):
                        del a.attrs[k]
        try:
                t.add(a)
        except TypeError, e:
                print a.attrs
                print a.name
                
                raise
        
def publish_pkg(pkg):
        """ send this package to the repo """

        svr4_pkg_list = sorted(list(set([
            a.attrs["importer.svr4pkg"]
            for a in pkg.actions
            if "importer.svr4pkg" in a.attrs and
            a.name in ["license", "file"]
            ])))

        svr4_traversal_list = [
            ("%s:%s" % (a.attrs["importer.svr4pkg"], a.attrs["importer.svr4path"]), a)
            for a in pkg.actions
            if "importer.svr4pkg" in a.attrs and
            a.name in ["license", "file"]
        ]
        svr4_traversal_dict = dict(svr4_traversal_list)
        # won't happen unless same pkg imported more than once into same ips pkg
        assert len(svr4_traversal_dict) == len(svr4_traversal_list)

        t = trans.Transaction(def_repo, create_repo=create_repo,
            pkg_name=pkg.fmristr(), noexecute=nopublish)
        transaction_id = t.open()

        # publish easy actions
        for a in sorted(pkg.actions):
                if a.name in ["license", "file", "depend"]:
                        continue
                if a.name == "hardlink":
                        # add depend file= actions for hardlinks
                        pkg.actions.extend(gen_hardlink_depend_actions(a))
                elif a.name == "license":
                        # hack until license action is fixed
                        a.attrs["transaction_id"] = transaction_id
                publish_action(t, pkg, a)

        # publish actions w/ data from imported svr4 pkgs
        # do so by looping through svr4 packages; use traversal_dict
        # to get the right action corresponding to its source.

        for p in svr4_pkg_list:
                bundle = SolarisPackageDirBundle(pkg_path(p))
                for a in bundle:
                        if a.name not in ["license", "file"]:
                                continue
                        index = "%s:%s" % (p, a.attrs["path"])
                        actual_action = svr4_traversal_dict.get(index)
                        if not actual_action:
                                continue

                        # make a copy of the data in a temp file, and
                        # put the opener on the proper action
                        ao = a.data()
                        bufsz = 256 * 1024
                        sz = int(a.attrs["pkg.size"])
                        fd, tmp = mkstemp(prefix="pkg.")
                        while sz > 0:
                                d = ao.read(min(bufsz, sz))
                                os.write(fd, d)
                                sz -= len(d)
                        d = None # free data
                        os.close(fd)

                        actual_action.data = lambda: open(tmp, "rb")
                        actual_action.attrs["pkg.size"] = a.attrs["pkg.size"]
                        publish_action(t, pkg, actual_action)
                        if "path" in actual_action.attrs:
                                pkg.actions.extend(gen_file_depend_actions(
                                    actual_action, tmp))
                        os.unlink(tmp)
        # publish any actions w/ data defined in import file
        for a in pkg.actions:
                if a.name not in ["license", "file"] or \
                    a.attrs.get("importer.source") != "add":
                        continue

                if hasattr(a, "hash"):
                        fname, fd = sourcehook(a.hash)
                        fd.close()
                        a.data = lambda: file(fname, "rb")
                        a.attrs["pkg.size"] = str(os.stat(fname).st_size)
                        if a.name == "license":
                                a.attrs["transaction_id"] = transaction_id

                publish_action(t, pkg, a)
                if "path" in a.attrs:
                        pkg.actions.extend(gen_file_depend_actions(a, fname))

        # resolve & combine dependencies

        # pass one; find pkgs & fix up any unspecified fmris;
        # build depend list excluding and dependencies on ourself
        depend_actions = []
        for a in pkg.actions:
                if a.name != "depend":
                        continue
                if "importer.file" not in a.attrs:
                        # set any unanchored deps to current version
                        if "@" not in a.attrs["fmri"] and a.attrs["fmri"] in fmridict:
                                a.attrs["fmri"] = fmridict[a.attrs["fmri"]]
                        depend_actions.append(a)
                        continue
                if "importer.path" in a.attrs: # we have a search path
                        fname = a.attrs["importer.file"]
                        pathlist = [os.path.join(p, fname) for p in a.attrs["importer.path"]]
                else:
                        pathlist = [a.attrs["importer.file"].lstrip("/")]

                for path in pathlist:
                        fmris = search_dicts(path)
                        if fmris:
                                repl_string = "fmri=%s" % a.attrs["fmri"]
                                orig_action = str(a)
                                for f in fmris:
                                        if f != pkg.fmristr():
                                                b = actions.fromstr(
                                                    orig_action.replace(
                                                    repl_string, "fmri=%s" % f))
                                                depend_actions.append(b)
                                break
                else:
                        possibles = basename_dict.get(pathlist[0].split("/")[-1])
                        if not possibles:
                                suggestions = "None"
                        else:
                                # get pkg names that might work
                                suggestions = " ".join("%s" % a for a in set(pkgpath_dict[p.attrs["path"]][0] for p in possibles))
                        print "%s: unresolved dependency %s: suggest %s" % (
                            pkg.name, a, suggestions)

        #  pass two; combine dependencies and look for errors
        depend_dict = {}
        delete_count = 0
        for i, a in enumerate(depend_actions[:]):
                fmri = str(a.attrs["fmri"])
                if fmri in depend_dict:
                        if depend_dict[fmri] != a.attrs["type"]:
                                print "%s: multiple dependency types on same pkg %s:%s" % (
                                    pkg.name, fmri, depend_dict)
                                raise RuntimeError("dependency error")
                        del depend_actions[i - delete_count]
                        delete_count += 1
                else:
                        depend_dict[fmri] = a.attrs["type"]
        # pass three - publish
        for a in depend_actions:
                publish_action(t, pkg, a)

        pkg_fmri, pkg_state = t.close(refresh_index=not defer_refresh)
        print "%s: %s\n" % (pkg_fmri, pkg_state)

def search_dicts(path):
        """ search dictionaries looking for path; translate symlinks.  Returns
        list of fmris that resolve dependency"""
        if path in pkgpath_dict:
                if len(path_dict[path]) > 1:
                        print "Caution: more than one pkg supplies %s (%s)" % (
                            path, path_dict[path])
                ret = [pkgpath_dict[path][0]]
                return ret
        # hmmm - check if any components of path are symlinks
        comp = path.split("/")

        for p in ["/".join(comp[:i]) for i in range(1, len(comp))]:
                if p not in path_dict:
                        break
                elif path_dict[p][0].name == "dir": #expected
                        continue
                elif path_dict[p][0].name == "link":
                        link = path_dict[p][0]
                        np = link.attrs["path"]
                        nt = link.attrs["target"]
                        newpath = os.path.normpath(
                                    os.path.join(os.path.split(np)[0], nt))
                        assert path.startswith(np)
                        ret = [pkgpath_dict[p][0]] 
                        next = search_dicts(path.replace(np, newpath))
                        if next:
                                ret += next
                                return ret
                else:
                        print "unexpected action %s in path %s" % (path_dict[p][0], path)
        return []

def gen_hardlink_depend_actions(action):
        """ generate dependency action for hardlinks; action is the
        hardlink action we're analyzing"""
        target = action.attrs["target"]
        path = action.attrs["path"]
        if not target.startswith("/"):
                target = os.path.normpath( os.path.join(os.path.split(path)[0],
                    target))
        return [actions.fromstr(
            "depend importer.file=%s fmri=none type=require importer.source=hardlink" %
            target)]

def gen_file_depend_actions(action, fname):
        """ generate dependency action for each file; action is the action
        being analyzed for dependencies, fname is the path to the local
        version of the file"""
        return_actions = []
        path = action.attrs["path"]

        if not elf.is_elf_object(fname):
                f = file(fname)
                l = f.readline()
                f.close()
                # add #!/ dependency
                if l.startswith("#!/"):
                        p = (l[2:].split()[0]) # first part of string is path (removes options)
                        # we don't handle dependencies through links, so fix up the common one
                        if p.startswith("/bin"):
                                p = "/usr" + p
                        return_actions.append(actions.fromstr("depend fmri=none importer.file=%s type=require importer.depsource=%s" %
                            (p.lstrip("/"), path)))
                if "python" in l or path.endswith(".py"):
                        pass # do something here....
                elif "perl" in l or path.endswith(".pl"):
                        pass # and here

                return return_actions
        # handle elf files

        ei = elf.get_info(fname)
        try:
                ed = elf.get_dynamic(fname)
        except elf.ElfError:
                deps = []
                rp = []
        else:
                deps = [
                    a 
                    for d in ed.get("deps", [])
                    for a in d[0].split()
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

                if path.startswith("platform"): # add this platform to search path
                        rp.append("/platform/%s/kernel" % path.split("/")[1])
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
        for d in deps:
                pathlist = []
                for p in rp:
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
                        # deppath includes filename; remove that.
                        head, tail = os.path.split(deppath)
                        if head:
                                pathlist.append(head)
                pn, fn = os.path.split(d)
                return_actions.append(actions.fromstr("depend fmri=none type=require importer.file=%s importer.depsource=%s %s" %
                    (fn, path, " ".join("importer.path=%s" % p for p in pathlist))))
        return return_actions

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

def get_fmri_from_uri(uri):
        # uris are of form http://depohost/...@SUNWfoo@1.2
        return pkg.fmri.PkgFmri(uri.split("@",1)[1], "5.11")

def get_server_from_uri(uri):
        # uris are of form http://depohost/...@SUNWfoo@1.2
        return uri.split("@",1)[0]

def get_manifest_from_uri(uri):
        assert 0,  "Not yet implemented"
        return get_manifest(get_server_from_uri(uri), get_fmri)

def get_expanded_uris(uri_list):
        assert 0,  "Not yet implemented"
        new_list = []
        for uri in uri_list:
                new_list.extend(expand_fmri(get_server_from_uri(uri), get_fmri_from_uri(uri)))
        for server in server_dict.keys():
                server_dict[server] = get_dependent_fmris(server, fmri_list)


def set_macro(key, value):
        macro_definitions.update([("$(%s)" % key, value)])

def clear_macro(key):
        del macro_definitions["$(%s)" % key]



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


def SolarisParse(mf):
        global curpkg
        global in_multiline_import

        lexer = tokenlexer(file(mf), mf, True)
        lexer.whitespace_split = True
        lexer.source = "include"
        lexer.sourcehook = sourcehook

        while True:
                token = lexer.get_token()

                if not token:
                        break

                if token == "package":
                        curpkg = start_package(lexer.get_token())

                        if print_pkg_names:
                                print "-j %s" % curpkg.name

                elif token == "end":
                        endarg = lexer.get_token()
                        if endarg == "package":
                                if print_pkg_names:
                                        curpkg = None
                                        continue

                                for filename in global_includes:
                                        for i in include_path:
                                                f = os.path.join(i, filename)
                                                if os.path.exists(f):
                                                        SolarisParse(f)
                                                        break
                                        else:
                                                raise RuntimeError("File not "
                                                    "found: %s" % filename)
                                end_package(curpkg)
                                curpkg = None

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

                        if not print_pkg_names:
                                try:
                                        curpkg.import_pkg(package_name, line)
                                except Exception, e:
                                        print "Error(import): %s: in file %s, line %d" % (
                                                e, mf, lexer.lineno)

                elif token == "from":
                        # slurp up all import lines
                        pkgspec = lexer.get_token()
                        filenames = []
                        junk = lexer.get_token()
                        assert junk == "import"
                        next = lexer.get_token()
                        while next != "end":
                                filenames.append(next)
                                next = lexer.get_token()
                        junk = lexer.get_token()
                        assert junk == "import"
                        if not print_pkg_names:
                                try:
                                        curpkg.import_files(pkgspec, filenames)
                                except Exception, e:
                                        print "ERROR(from ... import): %s: in file %s, line %d" % (
                                            e, mf, lexer.lineno)
                                        raise

                elif token == "classification":
                        cat_subcat = lexer.get_token()
                        curpkg.classification.append(
                            "org.opensolaris.category.2008:%s" % cat_subcat)

                elif token == "description":
                        curpkg.desc = lexer.get_token()

                elif token == "summary":
                        curpkg.summary = lexer.get_token()

                elif token == "depend":
                        action = actions.fromstr("depend fmri=%s type=require" %
                            lexer.get_token())
                        action.attrs["importer.source"] = token
                        curpkg.actions.append(action)

                elif token == "depend_path":
                        action = actions.fromstr("depend importer.file=%s fmri=none type=require" %
                            lexer.get_token())
                        action.attrs["importer.source"] = token
                        curpkg.actions.append(action)


                elif token == "cluster":
                        curpkg.add_svr4_src(lexer.get_token())

                elif token == "add":
                        action = actions.fromstr(read_full_line(lexer))
                        action.attrs["importer.source"] = token
                        curpkg.actions.append(action)

                elif token == "drop":
                        f = lexer.get_token()
                        if print_pkg_names:
                                continue
                        m = [a for a in curpkg.actions if a.attrs.get("path") == f]
                        if not m:
                                print "Cannot drop '%s' from '%s': not " \
                                    "found" % (f, curpkg.name)
                        else:
                                # delete all actions w/ matching path
                                for a in m:
                                        if show_debug:
                                                print "drop %s from %s" % (a, curpkg.name)
                                        del curpkg.actions[curpkg.actions.index(a)]

                elif token == "drop_license":
                        curpkg.dropped_licenses.append(lexer.get_token())

                elif token == "chattr":
                        fname = lexer.get_token()
                        line = read_full_line(lexer)
                        if print_pkg_names:
                                continue
                        try:
                                curpkg.chattr(fname, line)
                        except Exception, e:
                                print "Can't change attributes on " + \
                                    "'%s': not in the package" % fname, e
                                raise

                elif token == "chattr_glob":
                        glob = lexer.get_token()
                        line = read_full_line(lexer)
                        if print_pkg_names:
                                continue
                        try:
                                curpkg.chattr_glob(glob, line)
                        except Exception, e:
                                print "Can't change attributes on " + \
                                    "'%s': no matches in the package" % \
                                    glob, e
                                raise

                else:
                        raise RuntimeError("Error: unknown token '%s' "
                            "(%s:%s)" % (token, lexer.infile, lexer.lineno))
def main_func():
        global create_repo
        global defer_refresh
        global def_branch
        global def_repo
        global def_vers
        global just_these_pkgs
        global nopublish
        global print_pkg_names
        global reference_uris
        global show_debug
        global wos_path

        
        try:
                _opts, _args = getopt.getopt(sys.argv[1:], "B:D:I:G:NR:T:b:dj:m:ns:v:w:p:")
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
                        set_macro(_a[0], _a[1])
                elif opt == "-n":
                        nopublish = True
                elif opt == "-p":
                        if not os.path.exists(arg):
                                raise RuntimeError("Invalid prototype area specified.")
                        # Clean up relative ../../, etc. out of path to proto
                        g_proto_area = os.path.realpath(arg)
                elif  opt == "-s":
                        def_repo = arg
                        if def_repo.startswith("file://"):
                                # When publishing to file:// repositories, automatically
                                # create the target repository if needed.
                                create_repo = True
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
                elif opt == "-N":
                        print_pkg_names = True
                elif opt == "-R":
                        reference_uris.append(arg)
                elif opt == "-T":
                        timestamp_files.append(arg)

        if not def_branch:
                print "need a branch id (build number)"
                sys.exit(2)
        elif "." not in def_branch:
                print "branch id needs to be of the form 'x.y'"
                sys.exit(2)

        if not _args:
                print "need argument!"
                sys.exit(2)

        if not wos_path:
                wos_path = def_wos_path

        if just_these_pkgs:
                filelist = _args
        else:
                filelist = _args[0:1]
                just_these_pkgs = _args[1:]

        if print_pkg_names:
                for _mf in filelist:
                        SolarisParse(_mf)
                sys.exit(0)


        print "First pass: initial import", datetime.now()

        for _mf in filelist:
                SolarisParse(_mf)

        print "Second pass: global crosschecks", datetime.now()
        # perform global crosschecks
        #
        for pkg in pkgdict.values():
                for action in pkg.actions:
                        if "path" not in action.attrs:
                                continue
                        path_dict.setdefault(action.attrs["path"],[]).append(action)
                        if action.name in ["file", "link", "hardlink"]:
                                basename_dict.setdefault(os.path.basename(action.attrs["path"]), []).append(action)
                                pkgpath_dict.setdefault(action.attrs["path"],[]).append(action.attrs["importer.ipspkg"])
        errors = check_pathdict_actions(path_dict)
        if errors:
                for e in errors:
                        print e
                sys.exit(1)
        print "packages being published are self consistent"
        if reference_uris:
                print "downloading and checking external dependencies"
                reference_uris = get_expanded_uris(reference_uris)
                for uri in reference_uris:
                        pfmri = get_fmri_from_uri(uri)
                        if pfmri.get_name() in pkgdict:
                                continue # ignore pkgs already seen
                        fmridict[pfmri.get_name()] = str(pfmri);
                        for action in get_manifest_from_uri(uri):
                                action.attrs["importer.ipspkg"] = pfmri.get_name()
                                if action.name in ["file", "link", "hardlink"]:
                                        basename_dict.setdefault(os.path.basename(action.attrs["path"]), []).append(action)
                                        pkgpath_dict.setdefault(action.attrs["path"],[]).append(action.attr["importer.ipspkg"])
                errors = check_pathdict_actions(path_dict)
                if errors:
                        for e in errors:
                                print e
                        sys.exit(1)
                print "external packages checked for conflicts"

        print "Third pass: dependency id, resolution and publication", datetime.now()

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
        error_count = 0
        for _p in sorted(newpkgs):
                if show_debug:
                        print "  Version:", _p.version
                        print "  Description:", _p.desc
                        print "  Summary:", _p.summary
                        print "  Classification:", ",".join(_p.classification)
                try:
                        publish_pkg(_p)
                except trans.TransactionError, _e:
                        print "%s: FAILED: %s\n" % (_p.name, _e)
                        error_count += 1
                if show_debug:
                        processed += 1
                        print "%d/%d packages processed; %.2f%% complete" % (processed, total,
                            processed * 100.0 / total)

        if error_count:
                print "%d/%d packages has errors; %.2f%% FAILED" % (error_count, total,
                    error_count * 100.0 / total)
                sys.exit(1)

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
        print "%d/%d packages processed; %.2f%% complete" % (processed, total,
             processed * 100.0 / total)
        print "Done:", datetime.now()


if __name__ == "__main__":
        main_func()
