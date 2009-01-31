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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import sys
import os
import traceback
import getopt
import urllib
import tempfile
import gettext
import shutil

import pkg.fmri
import pkg.pkgtarfile as ptf
import pkg.catalog as catalog
import pkg.actions as actions
import pkg.manifest as manifest
import pkg.version as version

from pkg.misc import versioned_urlopen, gunzip_from_stream, msg, PipeError
from pkg.client import global_settings

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

def fetch_files_byhash(server_url, hashes, pkgdir):
        """Given a list of files named by content hash, download from
        server_url into pkgdir."""

        req_dict = { }

        for i, k in enumerate(hashes):
                str = "File-Name-%s" % i
                req_dict[str] = k

        req_str = urllib.urlencode(req_dict)

        try:
                f, v = versioned_urlopen(server_url, "filelist", [0],
                    data = req_str)
        except:
                error(_("Unable to download files from: %s") % server_url)
                sys.exit(1)

        tar_stream = ptf.PkgTarFile.open(mode = "r|", fileobj = f)

        if not os.path.exists(pkgdir):
                try:
                        os.makedirs(pkgdir)
                except:
                        error(_("Unable to create directory: %s") % pkgdir)
                        sys.exit(1)

        for info in tar_stream:
                gzfobj = None
                try:
                        # Uncompress as we retrieve the files
                        gzfobj = tar_stream.extractfile(info)
                        fpath = os.path.join(pkgdir, info.name)
                        outfile = open(fpath, "wb")
                        gunzip_from_stream(gzfobj, outfile)
                        outfile.close()
                        gzfobj.close()
                except:
                        error(_("Unable to extract file: %s") % info.name)
                        sys.exit(1)

        tar_stream.close()
        f.close()

manifest_cache={}
null_manifest = manifest.Manifest()

def get_manifest(server_url, fmri):
        if not fmri: # no matching fmri
                return null_manifest

        key = "%s->%s" % (server_url, fmri)
        if key not in manifest_cache:
                manifest_cache[key] = fetch_manifest(server_url, fmri)
        return manifest_cache[key]

def fetch_manifest(server_url, fmri):
        """Fetch the manifest for package-fmri 'fmri' from the server
        in 'server_url'... return as Manifest object."""
        # Request manifest from server

        try:
                m, v = versioned_urlopen(server_url, "manifest", [0],
                    fmri.get_url_path())
        except:
                error(_("Unable to download manifest %s from %s") %
                    (fmri.get_url_path(), server_url))
                sys.exit(1)

        # Read from server, write to file
        try:
                mfst_str = m.read()
        except:
                error(_("Error occurred while reading from: %s") % server_url)
                sys.exit(1)

        m = manifest.Manifest()
        m.set_content(mfst_str)

        return m

catalog_cache = {}

def get_catalog(server_url):
        if server_url not in catalog_cache:
                catalog_cache[server_url] = fetch_catalog(server_url)
        return catalog_cache[server_url][0]

def cleanup_catalogs():
        global catalog_cache
        for c, d in catalog_cache.values():
                shutil.rmtree(d)
        catalog_cache = {}

def fetch_catalog(server_url):
        """Fetch the catalog from the server_url."""

        # open connection for catalog
        try:
                c, v = versioned_urlopen(server_url, "catalog", [0])
        except:
                error(_("Unable to download catalog from: %s") % server_url)
                sys.exit(1)

        # make a tempdir for catalog
        dl_dir = tempfile.mkdtemp()

        # call catalog.recv to pull down catalog
        try:
                catalog.recv(c, dl_dir)
        except: 
                error(_("Error while reading from: %s") % server_url)
                sys.exit(1)

        # close connection to server
        c.close()

        # instantiate catalog object
        cat = catalog.Catalog(dl_dir)
        
        # return (catalog, tmpdir path)
        return cat, dl_dir

catalog_dict = {}
def load_catalog(server_url):
        c = get_catalog(server_url)
        d = {}
        for f in c.fmris():
                if f.pkg_name in d:
                        d[f.pkg_name].append(f)
                else:
                        d[f.pkg_name] = [f]
                for k in d.keys():
                        d[k].sort(reverse = True)
                catalog_dict[server_url] = d        

def expand_fmri(server_url, fmri_string, constraint=version.CONSTRAINT_AUTO):
        """ from specified server, find matching fmri using CONSTRAINT_AUTO
        cache for performance.  Returns None if no matching fmri is found """
        if server_url not in catalog_dict:
                load_catalog(server_url)

        fmri = pkg.fmri.PkgFmri(fmri_string, "5.11")        

        for f in catalog_dict[server_url].get(fmri.pkg_name, []):
                if not fmri.version or f.version.is_successor(fmri.version, constraint):
                        return f
        return None

def get_all_pkg_names(server_url):
        """ return all the pkg_names in this catalog """
        if server_url not in catalog_dict:
                load_catalog(server_url)
        return catalog_dict[server_url].keys()

def get_dependencies(server_url, fmri_list):
        s = set()
        for f in fmri_list:
                fmri = expand_fmri(server_url, f)
                _get_dependencies(s, server_url, fmri)
        return s

def _get_dependencies(s, server_url, fmri):
        """ recursive incorp expansion"""
        s.add(fmri)
        for a in get_manifest(server_url, fmri).gen_actions_by_type("depend"):
                if a.attrs["type"] == "incorporate":
                        new_fmri = expand_fmri(server_url, a.attrs["fmri"])
                        if new_fmri and new_fmri not in s:
                                _get_dependencies(s, server_url, new_fmri)
        return s

        
def main_func():

        basedir = None
        newfmri = False

        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgmerge", "/usr/lib/locale")

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

        server_list = [
                v.split(",", 1)[1]
                for v in varlist
                ]                
        
        if len(pargs) == 1:
                recursive = False
                overall_set = set()
                for s in server_list:
                        for name in get_all_pkg_names(s):
                                overall_set.add(name)
                fmri_arguments = list(overall_set)

        else:
                fmri_arguments = pargs[1:]

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

                except AssertionError:
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
        cleanup_catalogs()

        return 0

def merge_fmris(server_list, fmri_list, variant_list, variant, basedir, basename, get_files):

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

        for a_list, v in zip(action_lists[0:-1], variant_list):
                for a in a_list:
                        a.attrs[variant] = v

        # combine actions into single list
        allactions = reduce(lambda a,b:a + b, action_lists)
        
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
        m.actions=allactions

        basedir = os.path.join(basedir, basename)
        if not os.path.exists(basedir):
                os.makedirs(basedir)
                
        m_file = file(os.path.join(basedir, "manifest"), "w")
        m_file.write(m.tostr_unsorted())
        m_file.close()

        for f in fmri_list:
                if f:
                        fmri= str(f).rsplit(":", 1)[0]
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

                hash_sets = [
                        set(
                                [
                                 a.hash
                                 for a in action_list
                                 if hasattr(a, "hash") and not \
                                 repeated(a.hash, already_seen)
                                ]
                                )
                        for action_list in action_lists
                        ]
                # remove duplicate files (save time)
                
                for server, hash_set in zip(server_list + [server_list[0]], hash_sets):
                        if len(hash_set) > 0:
                                fetch_files_byhash(server, hash_set, basedir)

        return 0


if __name__ == "__main__":
        try:
                ret = main_func()
        except SystemExit, e:
                raise e
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                sys.exit(1)
        except:
                traceback.print_exc()
                sys.exit(99)
        sys.exit(ret)

