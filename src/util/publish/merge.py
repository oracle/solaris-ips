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

import sys
import os
import traceback
import getopt
import urllib
import tempfile
import gettext
import shutil
import warnings

import pkg.fmri
import pkg.client.api_errors as apx
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.actions as actions
import pkg.manifest as manifest
import pkg.version as version

from pkg.misc import PipeError
from pkg.client import global_settings

pub = None
tmpdirs = []
xport = None
xport_cfg = None

def pname():
        return os.path.basename(sys.argv[0])

def usage(usage_error = None):

        if usage_error:
                error(usage_error)

        print >> sys.stderr, _("""\
Usage:
        %s -r [-d dir] [-n] -v varname,url -v varname,url [-v varname,url ...] variant_type  pkgname [pkgname ...]

        example:

        %s -r -d /tmp/merge -n -v sparc,http://server1 -v i386,http://server2 arch entire
        """ % (pname(), pname()))

        sys.exit(2)

def error(error):
        """ Emit an error message prefixed by the command name """

        print >> sys.stderr, pname() + ": " + error

def fetch_files_byaction(repouri, actions, pkgdir):
        """Given a list of files named by content hash, download from
        repouri into pkgdir."""

        mfile = xport.multi_file_ni(repouri, pkgdir, decompress=True)

        for a in actions:
                mfile.add_action(a) 

        mfile.wait_files()

manifest_cache = {}
null_manifest = manifest.Manifest()

def get_manifest(repouri, fmri):
        if not fmri: # no matching fmri
                return null_manifest

        key = "%s->%s" % (repouri.uri, fmri)
        if key not in manifest_cache:
                manifest_cache[key] = fetch_manifest(repouri, fmri)
        return manifest_cache[key]

def fetch_manifest(repouri, fmri):
        """Fetch the manifest for package-fmri 'fmri' from the server
        in 'server_url'... return as Manifest object."""

        mfst_str = xport.get_manifest(fmri, pub=repouri, content_only=True)
        m = manifest.Manifest(fmri)
        m.set_content(content=mfst_str)
        return m

def fetch_catalog(repouri):
        """Fetch the catalog from the server_url."""

        if not pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp()
                tmpdirs.append(cat_dir)
                pub.meta_root = cat_dir

        pub.transport = xport
        # Pull catalog only from this host
        pub.selected_repository.origins = [repouri]
        pub.refresh(True, True)

        cat = pub.catalog

        return cat

catalog_dict = {}
def load_catalog(repouri):
        c = fetch_catalog(repouri)
        d = {}
        for f in c.fmris():
                if f.pkg_name in d:
                        d[f.pkg_name].append(f)
                else:
                        d[f.pkg_name] = [f]
                for k in d.keys():
                        d[k].sort(reverse = True)
        catalog_dict[repouri.uri] = d

def expand_fmri(repouri, fmri_string, constraint=version.CONSTRAINT_AUTO):
        """ from specified server, find matching fmri using CONSTRAINT_AUTO
        cache for performance.  Returns None if no matching fmri is found """
        if repouri.uri not in catalog_dict:
                load_catalog(repouri)

        fmri = pkg.fmri.PkgFmri(fmri_string, "5.11")

        for f in catalog_dict[repouri.uri].get(fmri.pkg_name, []):
                if not fmri.version or f.version.is_successor(fmri.version, constraint):
                        return f
        return None

def get_all_pkg_names(repouri):
        """ return all the pkg_names in this catalog """
        if repouri.uri not in catalog_dict:
                load_catalog(repouri)
        return catalog_dict[repouri.uri].keys()

def get_dependencies(repouri, fmri_list):
        s = set()
        for f in fmri_list:
                fmri = expand_fmri(repouri, f)
                _get_dependencies(s, repouri, fmri)
        return s

def _get_dependencies(s, repouri, fmri):
        """ recursive incorp expansion"""
        s.add(fmri)
        for a in get_manifest(repouri, fmri).gen_actions_by_type("depend"):
                if a.attrs["type"] == "incorporate":
                        new_fmri = expand_fmri(repouri, a.attrs["fmri"])
                        if new_fmri and new_fmri not in s:
                                _get_dependencies(s, repouri, new_fmri)
        return s

def cleanup():
        """To be called at program finish."""

        for d in tmpdirs:
                shutil.rmtree(d, True)

def main_func():

        global pub, xport, xport_cfg
        basedir = None
        newfmri = False
        incomingdir = None

        gettext.install("pkg", "/usr/share/locale")

        global_settings.client_name = "pkgmerge"

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "d:nrv:")
        except getopt.GetoptError, e:
                usage(_("Illegal option -- %s") % e.opt)

        varlist = []
        recursive = False
        get_files = True

        for opt, arg in opts:
                if opt == "-d":
                        basedir = arg
                if opt == "-v":
                        varlist.append(arg)
                if opt == "-r":
                        recursive = True
                if opt == "-n":
                        get_files = False


        if len(varlist) < 2:
                usage(_("at least two -v arguments needed to merge"))

        if not basedir:
                basedir = os.getcwd()
        
        incomingdir = os.path.normpath(os.path.join(basedir,
            "incoming-%d" % os.getpid()))
        os.makedirs(incomingdir)
        tmpdirs.append(incomingdir)

        server_list = [
            publisher.RepositoryURI(v.split(",", 1)[1])
            for v in varlist
        ]

        xport, xport_cfg = transport.setup_transport()
        xport_cfg.incoming_root = incomingdir
        pub = transport.setup_publisher(server_list, "merge", xport, xport_cfg,
            remote_prefix=True)

        if len(pargs) == 1:
                recursive = False
                overall_set = set()
                for s in server_list:
                        for name in get_all_pkg_names(s):
                                overall_set.add(name)
                fmri_arguments = list(overall_set)

        else:
                fmri_arguments = pargs[1:]

        if not pargs:
                usage(_("you must specify a variant"))

        variant = "variant.%s" % pargs[0]

        variant_list = [
                v.split(",", 1)[0]
                for v in varlist
                ]

        fmri_expansions = []

        if recursive:
                overall_set = set()
                for s in server_list:
                        deps = get_dependencies(s, fmri_arguments)
                        for d in deps:
                                if d:
                                        q = str(d).rsplit(":", 1)[0]
                                        overall_set.add(q)
                fmri_arguments = list(overall_set)

        fmri_arguments.sort()
        print "Processing %d packages" % len(fmri_arguments)

        for fmri in fmri_arguments:
                try:
                        fmri_list = [
                                expand_fmri(s, fmri)
                                for s in server_list
                                ]
                        if len(set([
                                   str(f).rsplit(":", 1)[0]
                                   for f in fmri_list
                                   if f
                                   ])) != 1:
                                error("fmris at different versions: %s" % fmri_list)
                                continue

                except pkg.fmri.IllegalFmri:
                        error(_("pkgfmri error"))
                        return 1

                for f in fmri_list:
                        if f:
                                basename = f.get_name()
                                break
                else:
                        error("No package of name %s in specified catalogs %s; ignoring." %\
                                      (fmri, server_list))
                        continue

                merge_fmris(server_list, fmri_list, variant_list, variant, basedir, basename, get_files)
        cleanup()

        return 0

def merge_fmris(server_list, fmri_list, variant_list, variant, basedir,
    basename, get_files):

        manifest_list = [
                get_manifest(s, f)
                for s, f in zip(server_list, fmri_list)
                ]

        # remove variant tags and package variant metadata
        # from manifests since we're reassigning...
        # this allows merging pre-tagged packages
        for m in manifest_list:
                for i, a in enumerate(m.actions[:]):
                        if variant in a.attrs:
                                del a.attrs[variant]
                        if a.name == "set" and a.attrs["name"] == variant:
                                del m.actions[i]

        action_lists = manifest.Manifest.comm(*tuple(manifest_list))

        # set fmri actions require special merge logic.
        set_fmris = []
        for l in action_lists:
                for i, a in enumerate(l):
                        if not (a.name == "set" and
                            a.attrs["name"] == "pkg.fmri"):
                                continue

                        set_fmris.append(a)
                        del l[i]

        # If set fmris are present, then only the most recent one
        # and add it back to the last action list.
        if set_fmris:
                def order(a, b):
                        f1 = pkg.fmri.PkgFmri(a.attrs["value"], "5.11")
                        f2 = pkg.fmri.PkgFmri(b.attrs["value"], "5.11")
                        return cmp(f1, f2)
                set_fmris.sort(cmp=order)
                action_lists[-1].insert(0, set_fmris[-1])

        for a_list, v in zip(action_lists[0:-1], variant_list):
                for a in a_list:
                        a.attrs[variant] = v

        # combine actions into single list
        allactions = reduce(lambda a, b: a + b, action_lists)

        # figure out which variants are actually there for this pkg
        actual_variant_list = [
                v
                for m, v in zip(manifest_list, variant_list)
                if m != null_manifest
                ]
        print "Merging %s for %s" % (basename, actual_variant_list)

        # add set action to document which variants are supported
        allactions.append(actions.fromstr("set name=%s %s" % (variant,
            " ".join(["value=%s" % a
                      for a in actual_variant_list
                      ]))))

        allactions.sort()

        m = manifest.Manifest()
        m.set_content(content=allactions)

        # urlquote to avoid problems w/ fmris w/ '/' character in name
        basedir = os.path.join(basedir, urllib.quote(basename, ""))
        if not os.path.exists(basedir):
                os.makedirs(basedir)

        m_path = os.path.join(basedir, "manifest")
        m.store(m_path)

        for f in fmri_list:
                if f:
                        fmri = str(f).rsplit(":", 1)[0]
                        break
        f_file = file(os.path.join(basedir, "fmri"), "w")
        f_file.write(fmri)
        f_file.close()


        if get_files:
                # generate list of hashes for each server; last is commom
                already_seen = {}
                def repeated(a, d):
                        if a in d:
                                return True
                        d[a] = 1
                        return False

                action_sets = [
                        set(
                                [
                                 a
                                 for a in action_list
                                 if hasattr(a, "hash") and not \
                                 repeated(a.hash, already_seen)
                                ]
                                )
                        for action_list in action_lists
                        ]
                # remove duplicate files (save time)

                for server, action_set in zip(server_list + [server_list[0]],
                    action_sets):
                        if len(action_set) > 0:
                                fetch_files_byaction(server, action_set,
                                    basedir)

        return 0


if __name__ == "__main__":

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                ret = main_func()
        except (apx.InvalidDepotResponseException, apx.TransportError,
            apx.BadRepositoryURI, apx.UnsupportedRepositoryURI), e:
                cleanup()
                print >> sys.stderr, e
                sys.exit(1)
        except SystemExit, e:
                cleanup()
                raise e
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                cleanup()
                sys.exit(1)
        except:
                traceback.print_exc()
                cleanup()
                sys.exit(99)
        sys.exit(ret)

