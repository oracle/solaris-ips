#!/usr/bin/python2.6
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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import fnmatch
import getopt
import gettext
import os
import pkg
import pkg.client
import pkg.client.transport.transport   as transport
import pkg.client.api_errors            as apx
import pkg.client.api
import pkg.client.progress
import pkg.flavor.smf_manifest          as smf_manifest
import pkg.fmri
import pkg.manifest                     as manifest
import pkg.misc
import pkg.pkgsubprocess                as subprocess
import pkg.publish.transaction          as trans
import pkg.variant                      as variant
import pkg.version                      as version
import platform
import re
import shlex
import shutil
import sys
import tempfile
import time
import urllib

from datetime import datetime
from pkg      import actions, elf
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle
from pkg.misc import emsg
from pkg.portable import PD_LOCAL_PATH, PD_PROTO_DIR, PD_PROTO_DIR_LIST

CLIENT_API_VERSION = 46
PKG_CLIENT_NAME = "importer.py"
pkg.client.global_settings.client_name = PKG_CLIENT_NAME

from tempfile import mkstemp

gettext.install("import", "/usr/lib/locale")

# rewrite of solaris.py to convert to actions as soon as possible;
# all chatters, etc. are performed before adding package contents
# to global name table. Actions are annotated to include svr4 source
# pkg & path


basename_dict = {}   # basenames to action lists
branch_dict = {}     # 
cons_dict = {}       # consolidation incorporation dictionaries
file_repo = False    #
curpkg = None        # which IPS package we're currently importing
def_branch = ""      # default branch
def_pub = None
def_repo = "http://localhost:10000"
def_vers = "0.5.11"  # default package version
# default search path
def_wos_path =  ["/net/netinstall.eng/export/nv/x/latest/Solaris_11/Product"]
elided_files = {}    # always delete these files; not checked on specific import
extra_entire_contents = [] # additional entries to be added to "entire"
fmridict = {}        # all ips FMRIS known, indexed by name
global_includes = [] # include these for every package
include_path = []    # where to find inport files - searched in order
just_these_pkgs = [] # publish only these pkgs
not_these_pkgs = []  # do not publish these pkgs
not_these_consolidations = [] # don't include packages in these consolidations
macro_definitions = {} # list of macro substitutions
nopublish = False    # fake publication?
path_dict = {}       # map of paths to action lists
pkgdict = {}         # pkgdict contains Package objects we're importing by name
pkgpaths = {}        # where we found svr4 pkgs by name
pkgpath_dict = {}    # mapping of paths to ips pkg
print_pkg_names = False # jusr print package names seen
publish_all = False  # always publish all obsoleted and renamed packages?
reference_uris = []  # list of url@pkg specs to compute dependencies against
show_debug = False   # print voluminous debug output
summary_detritus = [", (usr)", ", (root)", " (usr)", " (root)", " (/usr)", \
    " - / filesystem", ",root(/)"] # remove from summaries
svr4pkgsseen = {}    #svr4 pkgs seen - pkgs indexed by name
timestamp_files = [] # patterns of files that retain timestamps from svr4 pkgs
tmpdirs = []
wos_path = []        # list of search pathes for svr4 packages

local_smf_manifests = tempfile.mkdtemp(prefix="pkg_smf.") # where we store our SMF manifests

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
                self.consolidation = ""
                self.obsolete_branch = None
                self.rename_branch = None
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

                # Only pull the actual SVR4 file data into the bundle if it's likely
                # to contain an SMF manifest.
                for a in bundle:
                        if a.name == "file" and \
                            smf_manifest.has_smf_manifest_dir(a.attrs["path"]):
                                bundle = SolarisPackageDirBundle(ppath, data=True)
                                break

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
                        
                        if action.name == "file":
                                # is this a file for which we need a timestamp?
                                basename = os.path.basename(action.attrs["path"])
                                for file_pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename, file_pattern):
                                                break
                                else:
                                        del action.attrs["timestamp"]

                                # is this file likely to be an SMF manifest? If so,
                                # save a copy of the file to use for dependency analysis
                                if smf_manifest.has_smf_manifest_dir(action.attrs["path"]):
                                        fetch_file(action, local_smf_manifests)
                                        
                        if hollow:
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
                                            action.attrs[k]
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
                        type = args.pop(0)
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
        def delivered_via_ips(self):
                return self.consolidation in not_these_consolidations

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
        local_path_dict = {}
        # build dictionary of actions in pk by path
        for a in pkg.actions:
                if "path" in a.attrs:
                        local_path_dict.setdefault(a.attrs["path"], []).append(a)
        errors = check_pathdict_actions(local_path_dict, remove_dups=True)
        if errors:
                for e in errors:
                        print e
                raise RuntimeError("Package %s: errors occurred" % pkg.name)
        return local_path_dict

def check_pathdict_actions(my_path_dict, remove_dups=False, allow_dir_goofs=False):
        # investigate all paths w/ multiple actions
        errorlist = []
        for p in my_path_dict:
                # check to make sure all higher parts of path are indeed directories -
                # avoid publishing through symlinks
                tmp = p

                while True:
                        tmp = os.path.dirname(tmp)
                        if tmp:
                                if tmp in my_path_dict: # don't worry about implicit dirs for now
                                        a = my_path_dict[tmp][0]# just check the first one
                                        if a.name != "dir":
                                                errorlist.append("action %s path component %s is not directory: %s" %
                                                    (my_path_dict[p], tmp, a))
                        else:
                                break
                if len(my_path_dict[p]) == 1:
                        continue

                dups = my_path_dict[p]
                # make sure all are the same type
                if len(set((d.name for d in dups))) > 1:
                        errorlist.append("Multiple actions on different types with the same path:\n\t%s\n" %
                            ("\n\t".join(str(d) for d in dups)))
                        # disallow any duplicates that aren't directories
                        continue

                elif dups[0].name == "license": #XXX double check this
                        continue

                elif dups[0].name == "link" or dups[0].name == "hardlink":
                        targets = set((d.attrs["target"] for d in dups))
                        if len(targets) > 1:
                                errorlist.append("Multiple %s actions with same path and different targets:\n\t%s\n" %
                                    (dups[0].name, "\n\t".join(str(d) for d in dups)))
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
                                dir_error = "Multiple directory actions with the same path(%s) and different %s:\n\t%s\n" % \
                                    (p, g, "\n\t".join(str(d) for d in dups))
                                if allow_dir_goofs:
                                        print >> sys.stderr, "%s\n" % dir_error
                                else:
                                        errorlist.append(dir_error)
                        
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

        # add dependency on consolidation incorporation if not obsolete or renamed
        if pkg.consolidation and not pkg.obsolete_branch and not pkg.rename_branch:
                action = actions.fromstr(
                    "depend fmri=consolidation/%s/%s-incorporation "
                    "type=require importer.no-version=true" % 
                    (pkg.consolidation, pkg.consolidation))
                pkg.actions.append(action)

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
        
def publish_pkg(pkg, proto_dir):
        """ send this package to the repo """

        smf_fmris = []
        
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

        t = trans.Transaction(def_repo, create_repo=file_repo,
            pkg_name=pkg.fmristr(), noexecute=nopublish, xport=xport,
            pub=def_pub)
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
                                    actual_action, tmp, proto_dir))

                                fmris = get_smf_fmris(tmp, actual_action.attrs["path"])
                                if fmris:
                                        smf_fmris.extend(fmris)
                        os.unlink(tmp)

        # declare the SMF FMRIs that this package delivers
        if smf_fmris:
                values = ""
                for fmri in smf_fmris:
                        values = values + " value=%s" % fmri
                publish_action(t, pkg,
                    actions.fromstr("set name=opensolaris.smf.fmri %s" % values))

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
                        pkg.actions.extend(gen_file_depend_actions(a, fname, proto_dir))

        # resolve & combine dependencies

        # pass one; find pkgs & fix up any unspecified fmris;
        # build depend list excluding and dependencies on ourself
        depend_actions = []
        for a in pkg.actions:
                if a.name != "depend":
                        continue
                if "importer.file" not in a.attrs:
                        # set any unanchored deps to current version
                        if "@" not in a.attrs["fmri"] and a.attrs["fmri"] in fmridict and \
                            "importer.no-version" not in a.attrs:
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
                dtype = a.attrs["type"]

                if (fmri, dtype) in depend_dict:
                        del depend_actions[i - delete_count]
                        delete_count += 1
                else:
                        depend_dict[(fmri, dtype)] = True
        # pass three - publish
        for a in depend_actions:
                publish_action(t, pkg, a)

        pkg_fmri, pkg_state = t.close(add_to_catalog=not file_repo)
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

def get_smf_fmris(file, action_path):
        """ pull the delivered SMF FMRIs from file, associated with action_path """
        
        if smf_manifest.has_smf_manifest_dir(action_path):
                instance_mf, instance_deps = smf_manifest.parse_smf_manifest(file)
                if instance_mf:
                        return instance_mf.keys()

def fetch_file(action, proto_dir, server_pub=None):
        """ Save the file action contents to proto_dir """

        basename = os.path.basename(action.attrs["path"])
        dirname = os.path.dirname(action.attrs["path"])
        tmppath = os.path.join(proto_dir, dirname)
        try:
                os.makedirs(tmppath)
        except OSError, e:
                if e.errno != os.errno.EEXIST:
                        raise
        f = os.path.join(tmppath, basename)

        if server_pub:
                try:
                        file_content = xport.get_content(server_pub,
                            action.hash)
                except apx.TransportError, e:
                        print >> sys.stderr, e
                        cleanup()
                        sys.exit(1)

                ofile = file(f, "w")
                ofile.write(file_content)
                ofile.close()
                file_content = None
        elif action.data() is not None:
                ao = action.data()
                bufsz = 256 * 1024
                sz = int(action.attrs["pkg.size"])
                fd = os.open(f, os.O_CREAT|os.O_RDWR)
                while sz > 0:
                        d = ao.read(min(bufsz, sz))
                        os.write(fd, d)
                        sz -= len(d)
                d = None
        else:
                raise RuntimeError("Unable to save file %s - no URL provided."
                    % action.attrs["path"])

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

def gen_file_depend_actions(action, fname, proto_dir):
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

                # handle smf manifests
                if smf_manifest.has_smf_manifest_dir(path):
                        
                        # pkg.flavor.* used by pkgdepend wants PD_LOCAL_PATH, PD_PROTO_DIR
                        # and PD_PROTO_DIR_LIST set
                        action.attrs[PD_LOCAL_PATH] = fname
                        action.attrs[PD_PROTO_DIR] = proto_dir
                        action.attrs[PD_PROTO_DIR_LIST] = [proto_dir]
                        instance_deps, errs, attrs = \
                            smf_manifest.process_smf_manifest_deps(action,
                            {})

                        for dep in instance_deps:
                                # strip the proto_area dir name
                                manifest = dep.manifest.replace(local_smf_manifests, "", 1)
                                return_actions.append(actions.fromstr(
                                    "depend fmri=none importer.file=%s type=require importer.depsource=%s" % \
                                    (manifest.lstrip("/"), path)))
                        del(action.attrs[PD_LOCAL_PATH])
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

manifest_cache = {}
null_manifest = manifest.Manifest()

def error(text, cmd=None):
        """Emit an error message prefixed by the command name."""

        if cmd:
                text = "%s: %s" % (cmd, text)
                pkg_cmd = "importer "
        else:
                pkg_cmd = "importer: "

                # If we get passed something like an Exception, we can convert
                # it down to a string.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + pkg_cmd + text_nows)

def get_manifest(server_pub, fmri):
        if not fmri: # no matching fmri
                return null_manifest

        return manifest_cache.setdefault((server_pub, fmri), 
            fetch_manifest(server_pub, fmri))

def fetch_manifest(server_pub, fmri):
        """Fetch the manifest for package-fmri 'fmri' from the server
        in 'server_url'... return as Manifest object.... needs
        exact fmri"""

        # Request manifest from server
        try:
                mfst_str = xport.get_manifest(fmri, pub=server_pub,
                    content_only=True)
        except apx.TransportError, e:
                print >> sys.stderr, e
                cleanup()
                sys.exit(1)

        m = manifest.Manifest()
        m.set_content(mfst_str)

        return m

catalog_cache = {}

def get_catalog(server_pub):
        return catalog_cache.get(server_pub, fetch_catalog(server_pub))

def fetch_catalog(server_pub):
        """Fetch the catalog from the server_url."""

        if not server_pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp()
                tmpdirs.append(cat_dir)
                server_pub.meta_root = cat_dir

        server_pub.transport = xport
        server_pub.refresh(True, True)

        cat = server_pub.catalog

        return cat

catalog_dict = {}
def load_catalog(server_pub):
        c = get_catalog(server_pub)
        d = {}
        for f in c.fmris():
                d.setdefault(f.pkg_name, []).append(f)

        for k in d:
                d[k].sort(reverse=True)

        catalog_dict[server_pub] = d        

def expand_fmri(server_pub, fmri_string, constraint=version.CONSTRAINT_AUTO):
        """ from specified server, find matching fmri using CONSTRAINT_AUTO
        cache for performance.  Returns None if no matching fmri is found """
        if server_pub not in catalog_dict:
                load_catalog(server_pub)

        fmri = pkg.fmri.PkgFmri(fmri_string, "5.11")        

        for f in catalog_dict[server_pub].get(fmri.pkg_name, []):
                if not fmri.version or f.version.is_successor(fmri.version, constraint):
                        return f
        return None


def get_dependencies(server_pub, fmri_list):
        s = set()
        for f in fmri_list:
                fmri = expand_fmri(server_pub, f)
                _get_dependencies(s, server_pub, fmri)
        return s

def _get_dependencies(s, server_pub, fmri):
        """ recursive incorp expansion"""
        s.add(fmri)
        for a in get_manifest(server_pub, fmri).gen_actions_by_type("depend"):
                if a.attrs["type"] == "incorporate":
                        new_fmri = expand_fmri(server_pub, a.attrs["fmri"]) 
                        if new_fmri and new_fmri not in s: # ignore missing, already planned
                                _get_dependencies(s, server_pub, new_fmri)

def get_smf_packages(server_url, manifest_locations, filter):
        """ Performs a search against server_url looking for packages which contain
        SMF manifests, returning a list of those pfmris """

        dir = os.getcwd()
        tracker = pkg.client.progress.QuietProgressTracker()
        image_dir = tempfile.mkdtemp("", "pkg_importer_smfsearch.")

        is_zone = False
        refresh_allowed = True

        # create a temporary image
        api_inst = pkg.client.api.image_create(PKG_CLIENT_NAME,
            CLIENT_API_VERSION, image_dir, pkg.client.api.IMG_TYPE_USER,
            is_zone, facets=pkg.facet.Facets(), force=False,
            progtrack=tracker, refresh_allowed=refresh_allowed,
            repo_uri=server_url)

        api_inst = pkg.client.api.ImageInterface(image_dir,
            pkg.client.api.CURRENT_API_VERSION, tracker, None, PKG_CLIENT_NAME)

        # restore the current directory, which ImageInterace had changed
        os.chdir(dir)
        searches = []
        fmris = set()

        case_sensitive = False
        return_actions = True

        query = []
        for manifest_loc in manifest_locations:
                query.append(pkg.client.api.Query(":directory:path:/%s" % manifest_loc,
                    case_sensitive, return_actions))
        searches.append(api_inst.remote_search(query))
        shutil.rmtree(image_dir, True)

        for item in searches:
                for result in item:
                        pfmri = None
                        try:
                                query_num, pub, (v, return_type, tmp) = result
                                pfmri, index, action = tmp
                        except ValueError:
                                raise
                        if pfmri is None:
                                continue
                        if filter in pfmri.get_fmri():
                                fmris.add(pfmri.get_fmri())

        return [pkg.fmri.PkgFmri(pfmri) for pfmri in fmris]
        
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

def set_macro(key, value):
        macro_definitions.update([("$(%s)" % key, value)])

def clear_macro(key):
        del macro_definitions["$(%s)" % key]

def get_arch(): # use value of arch macro or platform 
        return macro_definitions.get("$ARCH", platform.processor())

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

                        if not (print_pkg_names or curpkg.delivered_via_ips()):
                                try:
                                        curpkg.import_pkg(package_name, line)
                                except Exception, e:
                                        print "Error(import): %s: in file %s, line %d" % (
                                                e, mf, lexer.lineno)
                                        raise

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
                        if not (print_pkg_names or curpkg.delivered_via_ips()):
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

                elif token == "obsoleted":
                        curpkg.obsolete_branch = lexer.get_token()
                        action = \
                            actions.fromstr("set name=pkg.obsolete value=true")
                        action.attrs["importer.source"] = "add"
                        curpkg.actions.append(action)

                elif token == "renamed":
                        curpkg.rename_branch = lexer.get_token()
                        action = \
                            actions.fromstr("set name=pkg.renamed value=true")
                        action.attrs["importer.source"] = "add"
                        curpkg.actions.append(action)

                elif token == "consolidation":
                        # Add to consolidation incorporation and
                        # include the org.opensolaris.consolidation
                        # package property.
                        curpkg.consolidation = lexer.get_token()
                        cons_dict.setdefault(curpkg.consolidation, []).append(curpkg.name)

                        action = actions.fromstr("set " \
                            "name=org.opensolaris.consolidation value=%s" %
                            curpkg.consolidation)
                        action.attrs["importer.source"] = token
                        curpkg.actions.append(action)

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
                        if print_pkg_names or curpkg.delivered_via_ips():
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
                        if print_pkg_names or curpkg.delivered_via_ips():
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
                        if print_pkg_names or curpkg.delivered_via_ips():
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
def repo_add_content(path_to_repo, path_to_proto):
        """Fire up depo to add content and rebuild search index"""

        cmdname = os.path.join(path_to_proto, "usr/bin/pkgrepo") 
        argstr = "%s -s %s refresh" % (cmdname, path_to_repo)

        print "Adding content & rebuilding search indicies synchronously...."
        print "%s" % str(argstr)
        try:
                proc = subprocess.Popen(argstr, shell=True)
                ret = proc.wait()
        except OSError, e:
                print "cannot execute %s: %s" % (argstr, e)
                return 1
        if ret:
                print "exited w/ status %d" % ret
                return 1
        print "done"
        return 0

def cleanup():
        """To be called at program finish."""
        for d in tmpdirs:
                shutil.rmtree(d, True)

def main_func():
        global file_repo
        global def_branch
        global def_pub
        global def_repo
        global def_vers
        global extra_entire_contents
        global just_these_pkgs
        global not_these_pkgs
        global nopublish
        global publish_all
        global print_pkg_names
        global reference_uris
        global show_debug
        global wos_path
        global not_these_consolidations
        global curpkg
        global xport
        global xport_cfg

        
        try:
                _opts, _args = getopt.getopt(sys.argv[1:], "AB:C:D:E:I:J:G:NR:T:b:dj:m:ns:v:w:p:")
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
                                file_repo = True
                elif opt == "-v":
                        def_vers = arg
                elif opt == "-w":
                        wos_path.append(arg)
                elif opt == "-A":
                        # Always publish obsoleted and renamed packages.
                        publish_all = True
                elif opt == "-B":
                        branch_file = file(arg)
                        for _line in branch_file:
                                if not _line.startswith("#"):
                                        bfargs = _line.split()
                                        if len(bfargs) == 2:
                                                branch_dict[bfargs[0]] = bfargs[1]
                        branch_file.close()
                elif opt == "-C":
                        not_these_consolidations.append(arg)
                elif opt == "-D":
                        elided_files[arg] = True
                elif opt == "-E":
                        if "@" not in arg:
                                print "-E fmris require a version: %s" % arg
                                sys.exit(2)

                        extra_entire_contents.append(arg)
                elif opt == "-I":
                        include_path.extend(arg.split(":"))

                elif opt == "-J":
                        not_these_pkgs.append(arg)
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

        start_time = time.clock()
        incoming_dir = tempfile.mkdtemp()

        tmpdirs.append(incoming_dir)
        tmpdirs.append(local_smf_manifests)

        xport, xport_cfg = transport.setup_transport()
        xport_cfg.incoming_root = incoming_dir

        def_pub = transport.setup_publisher(def_repo, "default", xport,
            xport_cfg, remote_prefix=True)

        print "Seeding local SMF manifest database from %s" % def_repo

        # Pull down any existing SMF manifests in the repo for
        # this build to help with dependency analysis later.  When we
        # do first pass import via SolarisParse, any newer SMF manifests
        # from the packages we're importing will overwrite these.
        for pfmri in get_smf_packages(def_repo, smf_manifest.manifest_locations,
            ",5.11-" + def_branch):
                pfmri_str = "%s@%s" % (pfmri.get_name(), pfmri.get_version())
                manifest = None
                try:
                        manifest = get_manifest(def_pub, pfmri)
                except:
                        print "No manifest found for %s" % str(pfmri)
                        raise
                for action in manifest.gen_actions_by_type("file"):
                        if smf_manifest.has_smf_manifest_dir(action.attrs["path"]):
                                fetch_file(action, local_smf_manifests,
                                    server_pub=def_pub)

        print "First pass: initial import", datetime.now()

        for _mf in filelist:
                SolarisParse(_mf)

        # Remove pkgs we're not touching  because we're skipping that
        # consolidation

        pkgs_to_elide = [
                p.name
                for p in pkgdict.values()
                if p.consolidation in not_these_consolidations
                ]

        for pkg in pkgs_to_elide:
                try:
                        del pkgdict[pkg]
                except KeyError:
                        print "elided package %s not in pkgdict" % pkg

        for pkg in not_these_pkgs:
                try:
                        del pkgdict[pkg]
                except KeyError:
                        print "excluded package %s not in pkgdict" % pkg

        # Unless we are publishing all obsolete and renamed packages 
        # (-A command line option), remove obsolete and renamed packages
        # that weren't obsoleted or renamed at this branch and create 
        # a dictionary (called or_pkgs_per_con) of obsoleted and renamed
        # packages per consolidation.  The version portion of the fmri 
        # will contain the branch that the package was obsoleted or renamed at.
        or_pkgs_per_con = {}
        obs_or_renamed_pkgs = {}

        for pkg in pkgdict.keys():
                obs_branch = pkgdict[pkg].obsolete_branch
                rename_branch = pkgdict[pkg].rename_branch
                assert not (obs_branch and rename_branch)

                ver_tokens = pkgdict[pkg].version.split("-")
                branch_tokens = ver_tokens[1].split(".")
                cons = pkgdict[pkg].consolidation
                if obs_branch:
                        branch_string = branch_tokens[0] + "." + obs_branch
                        ver_tokens[1] = branch_string
                        ver_string = "-".join(ver_tokens)
                        or_pkgs_per_con.setdefault(cons, {})[pkg] = ver_string
                        obs_or_renamed_pkgs[pkg] = (pkgdict[pkg].fmristr(), "obsolete")

                        if publish_all:
                                pkgdict[pkg].version = ver_string
                        else:
                                if obs_branch != def_branch.split(".", 1)[1]:
                                        # Not publishing this obsolete package.
                                        del pkgdict[pkg]

                if rename_branch:
                        branch_string = branch_tokens[0] + "." + rename_branch
                        ver_tokens[1] = branch_string
                        ver_string = "-".join(ver_tokens)
                        or_pkgs_per_con.setdefault(cons, {})[pkg] = ver_string
                        obs_or_renamed_pkgs[pkg] = (pkgdict[pkg].fmristr(), "renamed")

                        if publish_all:
                                pkgdict[pkg].version = ver_string
                        else:
                                if rename_branch != def_branch.split(".", 1)[1]:
                                        # Not publishing this renamed package.
                                        del pkgdict[pkg]

        # we've now pulled any SMF manifests found in the repository for this
        # branch, as well as those present in the packages to import.
        # Update our SMF manifest cache now.
        smf_manifest.SMFManifestDependency.populate_cache(local_smf_manifests,
            force_update=True)

        print "Second pass: global crosschecks", datetime.now()
        # perform global crosschecks
        #
        path_dict.clear()

        for pkg in pkgdict.values():
                for action in pkg.actions:
                        if "path" not in action.attrs:
                                continue
                        path = action.attrs["path"]
                        path_dict.setdefault(path, []).append(action)
                        if action.name in ["file", "link", "hardlink"]:
                                basename_dict.setdefault(os.path.basename(path), []).append(action)
                                pkgpath_dict.setdefault(path, []).append(action.attrs["importer.ipspkg"])
        errors = check_pathdict_actions(path_dict)
        if errors:
                for e in errors:
                        print "Fail: %s" % e
                cleanup()
                sys.exit(1)
        # check for require dependencies on obsolete or renamed pkgs

        errors = []
        warns = []
        for pack in pkgdict.values():
                for action in pack.actions:
                        if action.name != "depend":
                                continue
                        if action.attrs["type"] == "require" and "fmri" in action.attrs:
                                fmri = action.attrs["fmri"].split("@")[0] # remove version
                                if fmri.startswith("pkg:/"): # remove pkg:/ if exists
                                        fmri = fmri[5:] 
                                if fmri in obs_or_renamed_pkgs:
                                        tup = obs_or_renamed_pkgs[fmri]
                                        s = "Pkg %s has 'require' dependency on pkg %s, which is %s" % (
                                            (pack.fmristr(),) + tup)
                                        if tup[1] == "obsolete":
                                                errors.append(s)
                                        else:
                                                warns.append(s)

        if warns:
                for w in warns:
                        print "Warn: %s" % w
        if errors:
                for e in errors:
                        print "Fail: %s" % e
                cleanup()
                sys.exit(1)


        print "packages being published are self consistent"
        if reference_uris:
                print "downloading and checking external references"
                excludes = [variant.Variants({"variant.arch": get_arch()}).allow_action]
                for uri in reference_uris:
                        server, fmri_string = uri.split("@", 1)
                        server_pub = transport.setup_publisher(server,
                            "reference", xport, xport_cfg, remote_prefix=True)
                        for pfmri in get_dependencies(server_pub, [fmri_string]):
                                if pfmri is None:
                                        continue
                                if pfmri.get_name() in pkgdict:
                                        continue # ignore pkgs already seen
                                pfmri_str = "%s@%s" % (pfmri.get_name(), pfmri.get_version())
                                fmridict[pfmri.get_name()] = pfmri_str
                                for action in get_manifest(server_pub, pfmri).gen_actions(excludes):
                                        if "path" not in action.attrs:
                                                continue
                                        if action.name == "unknown":
                                                # we don't care about unknown actions -
                                                # mispublished packages with eg. SVR4
                                                # pkginfo files result in duplicate paths,
                                                # causing errors in check_pathdict_actions
                                                # "Multiple actions on different types
                                                # with the same path"
                                                print "INFO: ignoring action in %s: %s" \
                                                    % (pfmri_str, str(action))
                                                continue
                                        action.attrs["importer.ipspkg"] = pfmri_str
                                        path_dict.setdefault(action.attrs["path"], []).append(action)
                                        if action.name in ["file", "link", "hardlink"]:
                                                basename_dict.setdefault(os.path.basename(
                                                    action.attrs["path"]), []).append(action)
                                                pkgpath_dict.setdefault(action.attrs["path"],
                                                    []).append(action.attrs["importer.ipspkg"])
                errors = check_pathdict_actions(path_dict, allow_dir_goofs=True)
                if errors:
                        for e in errors:
                                print "Fail: %s" % e
                        cleanup()
                        sys.exit(1)
                print "external packages checked for conflicts"

        print "Third pass: dependency id, resolution and publication", datetime.now()

        consolidation_incorporations = []
        obsoleted_renamed_pkgs = []

        # Generate consolidation incorporations
        for cons in cons_dict.keys():
                if cons in not_these_consolidations:
                        print "skipping consolidation %s" % cons
                        continue
                consolidation_incorporation = "consolidation/%s/%s-incorporation" %  (
                    cons, cons)
                consolidation_incorporations.append(consolidation_incorporation)
                curpkg = start_package(consolidation_incorporation)
                curpkg.summary = "%s consolidation incorporation" % cons
                curpkg.desc = "This incorporation constrains packages " \
                        "from the %s consolidation." % cons

                # Add packages that aren't renamed or obsoleted
                or_pkgs = or_pkgs_per_con.get(cons, {})
                curpkg.actions.append(actions.fromstr(
                    "set name=pkg.depend.install-hold value=core-os.%s" % cons))

                for depend in cons_dict[cons]:
                        if depend not in or_pkgs:
                                action = actions.fromstr(
                                    "depend fmri=%s type=incorporate" % depend)
                                action.attrs["importer.source"] = "depend"
                                curpkg.actions.append(action)

                # Add in the obsoleted and renamed packages for this
                # consolidation.
                for name, version in or_pkgs.iteritems():
                        action = actions.fromstr(
                            "depend fmri=%s@%s type=incorporate" %
                                (name, version))
                        action.attrs["importer.source"] = "depend"
                        curpkg.actions.append(action)
                        obsoleted_renamed_pkgs.append("%s@%s" % (name, version))
                action = actions.fromstr("set " \
                    "name=org.opensolaris.consolidation value=%s" % cons)
                action.attrs["importer.source"] = "add"
                curpkg.actions.append(action)
                end_package(curpkg)
                curpkg = None

        # Generate entire consolidation if we're generating any consolidation incorps
        if consolidation_incorporations:
                curpkg = start_package("entire")
                curpkg.summary = "incorporation to lock all system packages to same build" 
                curpkg.desc = "This package constrains " \
                    "system package versions to the same build.  WARNING: Proper " \
                    "system update and correct package selection depend on the " \
                    "presence of this incorporation.  Removing this package will " \
                    "result in an unsupported system."
                curpkg.actions.append(actions.fromstr(
                    "set name=pkg.depend.install-hold value=core-os"))

                for incorp in consolidation_incorporations:
                        action = actions.fromstr("depend fmri=%s type=incorporate" % incorp)
                        action.attrs["importer.source"] = "auto-generated"
                        curpkg.actions.append(action)
                        action = actions.fromstr("depend fmri=%s type=require" % incorp)
                        action.attrs["importer.source"] = "auto-generated"
                        action.attrs["importer.no-version"] = "true"
                        curpkg.actions.append(action)

                for extra in extra_entire_contents:
                        action = actions.fromstr("depend fmri=%s type=incorporate" % extra)
                        action.attrs["importer.source"] = "command-line"
                        curpkg.actions.append(action)
                        extra_noversion = extra.split("@")[0] # remove version
                        action = actions.fromstr("depend fmri=%s type=require" % extra_noversion)
                        action.attrs["importer.source"] = "command-line"
                        action.attrs["importer.no-version"] = "true"
                        curpkg.actions.append(action)

                end_package(curpkg)
                curpkg = None


                incorporated_pkgs = set([
                                f
                                for l in cons_dict.values()
                                for f in l
                                ]) 
                incorporated_pkgs |= set(consolidation_incorporations)
                incorporated_pkgs |= set(["entire", "redistributable"])
                incorporated_pkgs |= set(obsoleted_renamed_pkgs)
                                
                unincorps = set(pkgdict.keys()) - incorporated_pkgs
                if unincorps:
                        # look through these; if they have only set actions they're
                        # ancient obsoleted pkgs - ignore them.
                        for f in unincorps.copy():
                                for a in pkgdict[f].actions:
                                        if a.name != "set":
                                                break
                                else:
                                        unincorps.remove(f)

                        print "The following non-empty unincorporated pkgs are not part of any consolidation"
                        for f in unincorps:
                                print f      
        if just_these_pkgs:
                newpkgs = set(pkgdict[name]
                              for name in pkgdict.keys()
                              if name in just_these_pkgs
                              )
        else:
                newpkgs = set(pkgdict.values())

        if not_these_consolidations:
                newpkgs = set([
                                p
                                for p in newpkgs
                                if not p.delivered_via_ips()
                                ])

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
                        publish_pkg(_p, g_proto_area)
                except trans.TransactionError, _e:
                        print "%s: FAILED: %s\n" % (_p.name, _e)
                        error_count += 1
                processed += 1
                if show_debug:
                        print "%d/%d packages processed; %.2f%% complete" % (processed, total,
                            processed * 100.0 / total)

        if error_count:
                print "%d/%d packages has errors; %.2f%% FAILED" % (error_count, total,
                    error_count * 100.0 / total)
                cleanup()
                sys.exit(1)

        print "%d/%d packages processed; %.2f%% complete" % (processed, total,
             processed * 100.0 / total)

        if file_repo:
                code = repo_add_content(def_repo[7:], g_proto_area)
                if code:
                        cleanup()
                        sys.exit(code)

        print "Done:", datetime.now()
        elapsed = time.clock() - start_time 
        print "publication took %d:%.2d" % (elapsed/60, elapsed % 60)
        cleanup()
        sys.exit(0)
        
if __name__ == "__main__":
        main_func()

