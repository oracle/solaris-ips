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

# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.

# The client is going to maintain an on-disk cache of its state, so that startup
# assembly of the graph is reduced.

# Client graph is of the entire local catalog.  As operations progress, package
# states will change.

# Deduction operation allows the compilation of the local component of the
# catalog, only if an authoritative repository can identify critical files.

import getopt
import httplib
import os
import re
import sys
import urllib2
import urlparse

import pkg.catalog
import pkg.config
import pkg.dependency
import pkg.fmri
import pkg.package
import pkg.version

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

Options:
        --repo, -s
        --image, -R

Environment:
        PKG_REPO
        PKG_IMAGE
"""
        sys.exit(2)

def catalog(config, args):
        """XXX will need to show available content series for each package"""

        if len(args) != 0:
                print "pkg: catalog subcommand takes no arguments"
                usage()

        # GET /catalog
        for repo in pcfg.repo_uris:
                uri = urlparse.urljoin(repo, "catalog")
                c = urllib2.urlopen(uri)

                # compare headers

def install(config, args):
        """Attempt to take package specified to INSTALLED state."""
        return

def uninstall(config, args):
        """Attempt to take package specified to DELETED state."""
        return

def freeze(config, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions."""
        return

def unfreeze(config, args):
        """Attempt to return package specified to INSTALLED state from FROZEN state."""
        return

# XXX need an Image configuration by default

pcfg = ParentRepo("http://localhost:10000", ["http://localhost:10000"])

if __name__ == "__main__":
        opts = None
        pargs = None
        try:
                if len(sys.argv) > 1:
                        opts, pargs = getopt.getopt(sys.argv[1:], "s:R:")
        except:
                print "pkg: illegal global option(s)"
                usage()

        if len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        if subcommand == "catalog":
                catalog(pcfg, pargs)
        elif subcommand == "install":
                install(pcfg, pargs)
        elif subcommand == "uninstall":
                uninstall(pcfg, pargs)
        elif subcommand == "freeze":
                freeze(pcfg, pargs)
        elif subcommand == "unfreeze":
                unfreeze(pcfg, pargs)
        else:
                print "pkg: unknown subcommand '%s'" % pargs[0]
                usage()
