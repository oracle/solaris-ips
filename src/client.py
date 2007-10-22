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
import gettext
import httplib
import os
import re
import sha
import sys
import urllib
import urllib2
import urlparse

import pkg.arch as arch
import pkg.catalog as catalog
import pkg.config as config
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.package as package
import pkg.version as version

import pkg.client.image as image
import pkg.client.imageplan as imageplan
import pkg.client.filelist as filelist

def usage():
        print _("""\
Usage:
        pkg [options] command [cmd_options] [operands]

Install subcommands:
        pkg refresh
        pkg status [-auv] [pkg_fmri_pattern ...]
        pkg install [-nv] pkg_fmri
        pkg uninstall [-nrv] pkg_fmri
        pkg freeze [--version version_spec] [--release] [--branch] pkg_fmri
        pkg unfreeze pkg_fmri
        pkg search token

        pkg image-create [-FPUz] [--full|--partial|--user] [--zone]
            [--authority prefix=url] dir

Options:
        --server, -s
        --image, -R

Environment:
        PKG_SERVER
        PKG_IMAGE""")
        sys.exit(2)

# XXX Subcommands to implement:
#        pkg image-set name value
#        pkg image-unset name
#        pkg image-get [name ...]
#        pkg image-update

def catalog_refresh(img, args):
        """Update image's catalogs."""

        # XXX will need to show available content series for each package

        if len(args) != 0:
                print _("pkg: refresh subcommand takes no arguments")
                usage()

        # Ensure Image directory structure is valid.
        if not os.path.isdir("%s/catalog" % img.imgdir):
                img.mkdirs()

        img.retrieve_catalogs()

def inventory_display(img, args):
        img.reload_catalogs()
        img.display_inventory(args)

def install(img, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Authority-catalog issues.

        opts = None
        pargs = None
        error = 0

        if len(args) > 0:
                opts, pargs = getopt.getopt(args, "Snvb:f:")

        strict = noexecute = verbose = False
        filters = []
        for opt, arg in opts:
                if opt == "-S":
                        strict = True
                elif opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxfiles = int(arg)
                elif opt == "-f":
                        filters += [ arg ]

        img.reload_catalogs()

        ip = imageplan.ImagePlan(img, filters = filters)

        for ppat in pargs:
                rpat = re.sub("\*", ".*", ppat)
                rpat = re.sub("\?", ".", rpat)

                try:
                        matches = img.get_regex_matching_fmris(rpat)
                except KeyError:
                        print _("""\
pkg: no package matching '%s' could be found in current catalog
     suggest relaxing pattern, refreshing and/or examining catalogs""") % ppat
                        error = 1
                        continue

                pnames = {}
                for m in matches:
                        pnames[m[1].get_pkg_stem()] = 1
                        # If we find an exact match, forget about anything else
                        # and stop looking.
                        if m[1].pkg_name == ppat:
                                pnames.clear()
                                pnames[m[1].get_pkg_stem()] = 1
                                break

                if len(pnames.keys()) > 1:
                        print _("pkg: '%s' matches multiple packages") % ppat
                        for k in pnames.keys():
                                print "\t%s" % k
                        error = 1
                        continue

                ip.propose_fmri(m[1])

        if error != 0:
                sys.exit(error)

        if verbose:
                print _("Before evaluation:")
                print ip

        ip.evaluate()

        if verbose:
                print _("After evaluation:")
                print ip

        if not noexecute:
                ip.execute()

def uninstall(img, args):
        """Attempt to take package specified to DELETED state."""

        if len(args) > 0:
                opts, pargs = getopt.getopt(args, "nrv")

        noexecute = recursive_removal = verbose = False
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-r":
                        recursive_removal = True
                elif opt == "-v":
                        verbose = True

        img.reload_catalogs() # XXX ???

        ip = imageplan.ImagePlan(img, recursive_removal)

        for ppat in pargs:
                rpat = re.sub("\*", ".*", ppat)
                rpat = re.sub("\?", ".", rpat)

                try:
                        matches = img.get_regex_matching_fmris(rpat)
                except KeyError:
                        print _("pkg: '%s' not even in catalog!") % ppat
                        error = 1
                        continue

                pnames = dict(
                    (m[1], 1)
                    for m in matches
                    if img.is_installed(m[1])
                )

                if len(pnames) > 1:
                        print _("pkg: '%s' matches multiple packages") % ppat
                        for k in pnames.keys():
                                print "\t%s" % k
                        continue

                if len(pnames) < 1:
                        print _("pkg: '%s' matches no installed packages") % ppat
                        continue

                ip.propose_fmri_removal(pnames.keys()[0])

        if verbose:
                print _("Before evaluation:")
                print ip

        ip.evaluate()

        if verbose:
                print _("After evaluation:")
                print ip

        if not noexecute:
                ip.execute()

def freeze(img, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions.  Package must have been in the INSTALLED state."""
        return

def unfreeze(img, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""
        return

def search(img, args):
        """Search through the reverse index databases for the given token."""

        for k, v in img.search(args):
                print k, v

def create_image(img, args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial authority for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        # XXX Long options support

        type = image.IMG_USER
        filter_tags = arch.get_isainfo()
        is_zone = False
        auth_name = None
        auth_url = None

        opts = None
        pargs = None
        if len(args) > 0:
                opts, pargs = getopt.getopt(args, "FPUza:")

        for opt, arg in opts:
                if opt == "-F":
                        type = image.IMG_ENTIRE
                if opt == "-P":
                        type = image.IMG_PARTIAL
                if opt == "-U":
                        type = image.IMG_USER
                if opt == "-z":
                        is_zone = True
                if opt == "-a":
                        auth_name, auth_url = arg.split("=", 1)

        img.set_attrs(type, pargs[0], is_zone, auth_name, auth_url)

        try:
                img.retrieve_catalogs()
        except urllib2.URLError, e:
                print >> sys.stderr, "pkg:", e.reason[1]
                return 1

        return 0

img = image.Image()

if __name__ == "__main__":
        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkg", "/usr/lib/locale")

        opts = None
        pargs = None
        try:
                if len(sys.argv) > 1:
                        opts, pargs = getopt.getopt(sys.argv[1:], "s:R:")
        except getopt.GetoptError, e:
                print _("pkg: illegal global option '%s'") % e.opt
                usage()

        if pargs == None or len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        # XXX Handle PKG_SERVER environment variable.

        if subcommand == "image-create":
                sys.exit(create_image(img, pargs))

        for opt, arg in opts:
                if opt == "-R":
                        dir = arg

        if "dir" not in locals():
                try:
                        dir = os.environ["PKG_IMAGE"]
                except KeyError:
                        dir = os.getcwd()

        try:
                img.find_root(dir)
        except AssertionError:
                print _("'%s' is not an install image") % dir
                sys.exit(1)

        img.load_config()

        if subcommand == "refresh":
                catalog_refresh(img, pargs)
        elif subcommand == "status":
                inventory_display(img, pargs)
        elif subcommand == "install":
                install(img, pargs)
        elif subcommand == "uninstall":
                try:
                        uninstall(img, pargs)
                except KeyboardInterrupt:
                        pass
        elif subcommand == "freeze":
                freeze(img, pargs)
        elif subcommand == "unfreeze":
                unfreeze(img, pargs)
        elif subcommand == "search":
                search(img, pargs)
        else:
                print _("pkg: unknown subcommand '%s'") % subcommand
                usage()
