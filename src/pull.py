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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
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
from pkg.misc import versioned_urlopen, gunzip_from_stream, msg, emsg, PipeError
from pkg.client import global_settings

def usage(usage_error = None):
        """ Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        if usage_error:
                error(usage_error)

        emsg(_("""\
Usage:
        pkgrecv -s server [-d dir] pkgfmri ...
        pkgrecv -s server -n"""))

        sys.exit(2)


def error(error):
        """ Emit an error message prefixed by the command name """

        # The prgram name has to be a constant value as we can't reliably 
        # get our actual program name on all platforms.
        emsg("pkgrecv: " + error)

def hashes_from_mfst(manifest):
        """Given a path to a manifest, open the file and read through the
        actions.  Return a set of all content hashes found in the manifest."""

        hashes = set()

        try:
                f = file(manifest, "r")
        except:
                error(_("Unable to open manifest: %s") % manifest)
                sys.exit(1)

        for line in f:
                line = line.lstrip()
                if not line or line[0] == "#":
                        continue

                try:
                        action = actions.fromstr(line)
                except:
                        continue

                if hasattr(action, "hash"):
                        hashes.add(action.hash)

        f.close()

        return hashes

def fetch_files_byhash(server_url, hashes, pkgdir, keep_compressed):
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
                        if not keep_compressed:
                                # Uncompress as we retrieve the files
                                gzfobj = tar_stream.extractfile(info)
                                fpath = os.path.join(pkgdir, info.name)
                                outfile = open(fpath, "wb")
                                gunzip_from_stream(gzfobj, outfile)
                                outfile.close()
                                gzfobj.close()
                        else:
                                # We want to keep the files compressed on disk
                                tar_stream.extract_to(info, pkgdir, info.name)
                except:
                        error(_("Unable to extract file: %s") % info.name)
                        sys.exit(1)

        tar_stream.close()
        f.close()

def fetch_manifest(server_url, fmri, basedir):
        """Fetch the manifest for package-fmri 'fmri' from the server
        in 'server_url'. Put manifest in a directory named by package stem"""

        # Request manifest from server
        try:
                m, v = versioned_urlopen(server_url, "manifest", [0],
                    fmri.get_url_path())
        except:
                error(_("Unable to download manifest %s from %s") %
                    (fmri.get_url_path(), server_url))
                sys.exit(1)

        # join pkgname onto basedir.  Manifest goes here
        opath = os.path.join(basedir, urllib.quote(fmri.pkg_name, ""))

        # Create directories if they don't exist
        if not os.path.exists(opath):
                try:
                        os.makedirs(opath)
                except:
                        error(_("Unable to create directory: %s") % opath)
                        sys.exit(1)

        # Open manifest
        opath = os.path.join(opath, "manifest")
        try:
                ofile = file(opath, "w")
        except:
                error(_("Unable to open file: %s") % opath)
                sys.exit(1)

        # Read from server, write to file
        try:
                mfst = m.read()
        except:
                error(_("Error occurred while reading from: %s") % server_url)
                sys.exit(1)

        try:
                ofile.write(mfst)
        except:
                error(_("Error occurred while writing to: %s") % opath)
                sys.exit(1)

        # Close it up
        ofile.close()
        m.close()

        return opath

def list_newest_fmris(cat):
        """Look through the catalog 'cat' and return the newest version
        of a fmri found for a given package."""

        fm_hash = { }
        fm_list = [ ]

        # Order all fmris by package name
        for f in cat.fmris():
                if f.pkg_name in fm_hash:
                        fm_hash[f.pkg_name].append(f)
                else:
                        fm_hash[f.pkg_name] = [ f ]

        # sort each fmri list
        for k in fm_hash.keys():
                fm_hash[k].sort(reverse = True)
                l = fm_hash[k]
                fm_list.append(l[0])

        for e in fm_list:
                print e

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

def main_func():

        server = None
        basedir = None
        newfmri = False
        keep_compressed = False

        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgrecv", "/usr/lib/locale")

        global_settings.client_name = "pkgrecv"

        try:
               opts, pargs = getopt.getopt(sys.argv[1:], "s:d:nk")
        except getopt.GetoptError, e:
                usage(_("Illegal option -- %s") % e.opt) 

        for opt, arg in opts:
                if opt == "-s":
                        server = arg
                if opt == "-d":
                        basedir = arg
                if opt == "-n":
                        newfmri = True
                if opt == "-k":
                        keep_compressed = True

        if not server:
                usage(_("must specify a server"))

        if not server.startswith("http://"):
                server = "http://%s" % server

        if newfmri:
                if pargs or len(pargs) > 0:
                        usage(_("-n takes no options"))

                cat, dir = fetch_catalog(server)
                list_newest_fmris(cat)
                shutil.rmtree(dir)
                
        else:
                if pargs == None or len(pargs) == 0:
                        usage(_("must specify at least one pkgfmri"))

                if not basedir:
                        basedir = os.getcwd()

                for pkgfmri in pargs:
                        if not pkgfmri.startswith("pkg:/"):
                                pkgfmri = "pkg:/%s" % pkgfmri

                        try:
                                fmri = pkg.fmri.PkgFmri(pkgfmri)
                        except pkg.fmri.IllegalFmri, e:
                                error(_("%(fmri)s is an illegal fmri: "
                                    "%(error)s") %
                                    { "fmri": pkgfmri, "error": e })
                                return 1

                        mfstpath = fetch_manifest(server, fmri, basedir)
                        content_hashes = hashes_from_mfst(mfstpath)

                        if len(content_hashes) > 0:
                                fetch_files_byhash(server, content_hashes,
                                        os.path.dirname(mfstpath),
                                        keep_compressed)
                        else:
                                msg(_("No files to retrieve."))

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
