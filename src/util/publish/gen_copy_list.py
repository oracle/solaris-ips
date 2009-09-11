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
# This command line utility produces a list of files to copy from
# source repo to another to move the fmris specified on the command
# line.  The -r option recursively adds all dependencies (of any type) 
# as well.
#
# usage: gen_copy_list.py [-r] [-a] server_url fmri ... 

import sys
import os
import traceback
import getopt
import tempfile
import shutil

import pkg.fmri
import pkg.manifest as manifest
import pkg.server.catalog as catalog
import pkg.version as version

from pkg.misc import versioned_urlopen, PipeError, hash_file_name

all_fmris=[]
complete_catalog=None
server_url=None

manifest_cache={}
null_manifest=manifest.Manifest()


def pname():
        return os.path.basename(sys.argv[0])

def usage(usage_error = None):

        if usage_error:
                error(usage_error)

        print >> sys.stderr, """\
Usage:
        %s [-r] [-t] [-v] url fmri ...

        -r recursively evaluates all dependencies, adding them to the list
        -t include all matching timestamps, not just latest (also implies -v)
        -v include all matching versions, not just latest

        """ % pname()

        sys.exit(2)

def error(error):
        """ Emit an error message prefixed by the command name """

        print >> sys.stderr, pname() + ": " + error


def get_manifest(fmri):
        if not fmri: # no matching fmri
                return null_manifest

        if fmri not in manifest_cache:
                manifest_cache[fmri] = fetch_manifest(fmri)

        return manifest_cache[fmri]

def fetch_manifest(fmri):
        """Fetch the manifest for package-fmri 'fmri' from the server
        in 'server_url'... return as Manifest object."""
        # Request manifest from server

        try:
                m, v = versioned_urlopen(server_url, "manifest", [0],
                    fmri.get_url_path())
        except:
                error("Unable to download manifest %s from %s" %
                    (fmri.get_url_path(), server_url))
                traceback.print_stack()
                sys.exit(1)

        # Read from server, write to file
        try:
                mfst_str = m.read()
        except:
                error("Error occurred while reading from: %s" % server_url)
                sys.exit(1)

        m = manifest.Manifest()
        m.set_content(mfst_str)

        return m

def fetch_catalog():
        """Fetch the catalog from the server_url."""
        global complete_catalog
        global all_fmris

        # open connection for catalog
        try:
                c, v = versioned_urlopen(server_url, "catalog", [0])
        except:
                error("Unable to download catalog from: %s" % server_url)
                sys.exit(1)

        # make a tempdir for catalog
        delete_dir = tempfile.mkdtemp()

        # call catalog.recv to pull down catalog
        try:
                catalog.ServerCatalog.recv(c, delete_dir)
        except: 
                error("Error while reading from: %s" % server_url)
                sys.exit(1)

        # close connection to server
        c.close()

        d = {}

        cat = catalog.ServerCatalog(delete_dir, read_only=True)

        for f in cat.fmris():
                all_fmris.append(f)
                if f.pkg_name in d:
                        d[f.pkg_name].append(f)
                else:
                        d[f.pkg_name] = [f]
        for k in d.keys():
                d[k].sort(reverse = True)

        shutil.rmtree(delete_dir)
        complete_catalog = d
        
def expand_fmri(fmri, constraint=version.CONSTRAINT_AUTO):
        """ find matching fmri using CONSTRAINT_AUTO
        cache for performance.  Returns None if no matching fmri is found """
        if isinstance(fmri, str):
                fmri = pkg.fmri.PkgFmri(fmri, "5.11")        

        for f in complete_catalog.get(fmri.pkg_name, []):
                if not fmri.version or \
                    f.version.is_successor(fmri.version, constraint):
                        return f
        return None

def expand_matching_fmris(fmri_strings):
        """ find matching fmris using pattern matching and
        constraint auto."""
        counthash={}

        patterns = [pkg.fmri.MatchingPkgFmri(s, "5.11") for s in fmri_strings]

        matches = catalog.extract_matching_fmris(all_fmris,
            patterns=patterns, constraint=version.CONSTRAINT_AUTO,
            counthash=counthash, matcher=pkg.fmri.glob_match)

        bail = False

        for f in patterns:
                if f not in counthash:
                        print "No match found for %s" % f.pkg_name
                        bail = True

        if bail:
                sys.exit(2)

        return matches

        
def get_dependencies(fmri_list):
        s = set()
        for f in fmri_list:
                fmri = expand_fmri(f)
                _get_dependencies(s, fmri)
        return list(s)

def _get_dependencies(s, fmri):
        """ expand all dependencies"""
        s.add(fmri)
        for a in get_manifest(fmri).gen_actions_by_type("depend"):
                new_fmri = expand_fmri(a.attrs["fmri"])
                if new_fmri and new_fmri not in s:
                        _get_dependencies(s, new_fmri)
        return s

seen_hashes = {}

def get_hashes(fmri):
        """ return list of new hashes in manifest """

        def repeated(a):
                if a in seen_hashes:
                        return True
                seen_hashes[a] = 1
                return False

        return [
                a.hash
                for a in get_manifest(fmri).gen_actions()
                if hasattr(a, "hash") and not repeated(a.hash)
                ]

def prune(fmri_list, all_versions, all_timestamps):
        if all_timestamps:
                pass
        elif all_versions:
                dedup = {}
                for f in fmri_list:
                        dedup.setdefault(f.get_short_fmri(), []).append(f)
                fmri_list = [sorted(dedup[f], reverse=True)[0] for f in dedup]
        else:
                dedup = {}
                for f in fmri_list:
                        dedup.setdefault(f.pkg_name, []).append(f)
                fmri_list = [sorted(dedup[f], reverse=True)[0] for f in dedup]
        return fmri_list


def main_func():
        global server_url

        try:
               opts, pargs = getopt.getopt(sys.argv[1:], "rtv")
        except getopt.GetoptError, e:
                usage("Illegal option -- %s" % e.opt) 

        recursive      = False
        all_versions   = False
        all_timestamps = False

        for opt, arg in opts:
                if opt == "-r":
                        recursive = True
                elif opt == "-t":
                        all_timestamps = True
                elif opt == "-v":
                        all_versions = True

        if not pargs:
                usage("no options specified")

        server_url = pargs[0]
        fmri_arguments = pargs[1:]

        fetch_catalog()

        fmri_list = prune(list(set(expand_matching_fmris(fmri_arguments))), 
            all_versions, all_timestamps)

        if recursive:
                fmri_list = prune(get_dependencies(fmri_list), 
                    all_versions, all_timestamps)
                
                
        print >> sys.stderr, "Processing %d pkgs" % len(fmri_list)

        
        for f in fmri_list:
                print >> sys.stderr, "%s" % f
                # print path to manifest in repo
                print "%s" % os.path.join("pkg", f.get_dir_path())
                # print paths to any hashes in manifest
                for h in get_hashes(f):
                        print "%s" % os.path.join("file", hash_file_name(h))


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

