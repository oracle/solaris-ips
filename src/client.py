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

#
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

# pkg - package system client utility
#
# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.

# The client is going to maintain an on-disk cache of its state, so that startup
# assembly of the graph is reduced.

# Client graph is of the entire local catalog.  As operations progress, package
# states will change.

# Deduction operation allows the compilation of the local component of the
# catalog, only if an authoritative repository can identify critical files.
#
# Environment variables
#
# PKG_IMAGE - root path of target image
# PKG_IMAGE_TYPE [entire, partial, user] - type of image
#       XXX or is this in the Image configuration?

import getopt
import httplib
import os
import re
import sys
import urllib
import urllib2
import urlparse

import pkg.arch as arch
import pkg.catalog as catalog
import pkg.config as config
import pkg.content as content
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.package as package
import pkg.version as version

import pkg.client.image as image

def usage():
        print """\
Usage:
        pkg [options] command [cmd_options] [operands]

Install subcommands:
        pkg catalog
        pkg install pkg_fmri
        pkg uninstall pkg_fmri
        pkg freeze [--version version_spec] [--release] [--branch] pkg_fmri
        pkg unfreeze pkg_fmri

        pkg image [--full|--partial|--user] dir
        pkg image [-FPU] dir

        pkg set name value
        pkg unset name

Options:
        --server, -s
        --image, -R

Environment:
        PKG_SERVER
        PKG_IMAGE"""
        sys.exit(2)

def catalog(config, image, args):
        """XXX will need to show available content series for each package"""
        croot = image.imgdir

        if len(args) != 0:
                print "pkg: catalog subcommand takes no arguments"
                usage()

        # Ensure Image directory structure is valid.
        if not os.path.isdir("%s/catalog" % croot):
                image.mkdirs()

        # GET /catalog
        for repo in pcfg.repo_uris:
                # Ignore http_proxy for localhost case, by overriding default
                # proxy behaviour of urlopen().
                proxy_uri = None
                netloc = urlparse.urlparse(repo)[1]
                if urllib.splitport(netloc)[0] == "localhost":
                        proxy_uri = {}

                uri = urlparse.urljoin(repo, "catalog")

                c = urllib.urlopen(uri, proxies=proxy_uri)

                # compare headers
                data = c.read()
                fname = urllib.quote(c.geturl(), "")

                # Filename should be reduced to host\:port
                cfile = file("%s/catalog/%s" % (croot, fname), "w")
                print >>cfile, data

def pattern_install(config, image, pattern, strict):
        # check catalogs for this pattern; None is the representation of the
        # freezes
        matches = image.get_matching_pkgs(pattern)

        matches.sort()

        # If there is more than one package in the list, then we've got an
        # ambiguous outcome, and need to exit.

        l = matches[0]
        for p in matches:
                if p.is_same_pkg(l):
                        l = p
                        continue

                raise KeyError, "pattern %s led to multiple packages" % pattern


        # pick appropriate version, based on request and freezes
        p = max(matches)
        #   XXX can we do this with the is_successor()/version() and a map?
        #   warn on dependencies; exit if --strict

        image.retrieve_manifest(p)

        # do we have this manifest?
        #   get it if not
        # request manifest
        # examine manifest for files
        # request files

        return # a client operation



def install(config, image, args):
        """Attempt to take package specified to INSTALLED state."""
        strict = False
        oplist = []

        opts = None
        pargs = None
        if len(args) > 0:
                opts, pargs = getopt.getopt(args, "S")

        for opt, arg in opts:
                if opt == "-S":
                        strict = True

        image.reload_catalogs()

        for ppat in pargs:
                try:
                        ops = pattern_install(config, image, ppat, strict)
                except KeyError:
                        # okay skip this argument
                        pass

                oplist.append(ops)


        # perform update transaction as given in oplist

        return

def uninstall(config, args):
        """Attempt to take package specified to DELETED state."""
        return

def freeze(config, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions."""
        return

def unfreeze(config, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""

        return

def create_image(config, args):
        """Create an image of the requested kind, at the given path."""

        type = image.IMG_USER
        filter_tags = arch.get_isainfo()

        opts = None
        pargs = None
        if len(args) > 0:
                opts, pargs = getopt.getopt(args, "FPU")

        i = image.Image()

        for opt, arg in opts:
                if opt == "-F":
                        type = image.IMG_ENTIRE
                if opt == "-P":
                        type = image.IMG_PARTIAL
                if opt == "-U":
                        type = image.IMG_USER

        i.set_attrs(type, pargs[0])
        i.mkdirs()

        return

# XXX need an Image configuration by default
icfg = image.Image()
icfg.find_parent()
pcfg = config.ParentRepo("http://localhost:10000", ["http://localhost:10000"])

if __name__ == "__main__":


        opts = None
        pargs = None
        try:
                if len(sys.argv) > 1:
                        opts, pargs = getopt.getopt(sys.argv[1:], "s:R:")
        except:
                print "pkg: illegal global option(s)"
                usage()

        if pargs == None or len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        # Handle PKG_IMAGE and PKG_SERVER environment variables.

        if subcommand == "catalog":
                catalog(pcfg, icfg, pargs)
        elif subcommand == "install":
                install(pcfg, icfg, pargs)
        elif subcommand == "uninstall":
                uninstall(pcfg, icfg, pargs)
        elif subcommand == "freeze":
                freeze(pcfg, icfg, pargs)
        elif subcommand == "unfreeze":
                unfreeze(pcfg, icfg, pargs)
        elif subcommand == "image":
                create_image(pcfg, pargs)
        else:
                print "pkg: unknown subcommand '%s'" % subcommand
                usage()
