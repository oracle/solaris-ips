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

import getopt
import httplib
import os
import re
import sys
import urllib2
import urlparse

def usage():
        print """\
Usage:
        pkg [options] command [cmd_options] [operands]

Install subcommands:
        pkg catalog
        pkg install pkg_name
        pkg uninstall pkg_name

Packager subcommands:
        pkg open [-e] pkg_name
        pkg add file|link|device path file
        pkg delete path
        pkg meta add require|exclude pkg_name
        pkg meta delete pkg_name
        pkg summary
        pkg close

Options:
        --repo, -s
        --image, -R

Environment:
        PKG_REPO
        PKG_IMAGE
"""
        sys.exit(2)

class ParentRepo(object):
        """Install repo URI (optional)
             Repository upon which we commit transactions.
           URL list of repos, in order of preference.

           XXX Need a local filter policy.  One filter example would be to only
           install 32-bit binaries."""
        def __init__(self, install_uri, repo_uris):
                self.install_uri = install_uri
                self.repo_uris = repo_uris

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

def trans_open(config, args):
        opts = None
        pargs = None
        try:
                opts, pargs = getopt.getopt(args, "e")
        except:
                print "pkg: illegal open option(s)"
                usage()

        eval_form = False
        for opt, arg in opts:
                if opt == "-e":
                        eval_form = True

        if len(pargs) != 1:
                print "pkg: open requires one package name"
                usage()

        # POST /open/pkg_name
        repo = config.install_uri
        uri = urlparse.urljoin(repo, "open/%s" % pargs[0])

        c = urllib2.urlopen(uri)

        lines = c.readlines()
        for line in lines:
                if re.match("^Transaction-ID:", line):
                        m = re.match("^Transaction-ID: (.*)", line)
                        if eval_form:
                                print "export PKG_TRANS_ID=%s" % m.group(1)
                        else:
                                print m.group(1)

        return

def trans_close(config, args):
        # XXX alternately args contains -t trans
        trans_id = os.environ["PKG_TRANS_ID"]
        repo = config.install_uri
        uri = urlparse.urljoin(repo, "close/%s" % trans_id)
        try:
                c = urllib2.urlopen(uri)
        except urllib2.HTTPError:
                print "pkg: transaction close failed"
                sys.exit(1)

def trans_add(config, args):
        """POST the file contents to the transaction.  Default is to post to the
        currently open content series.  -s option selects a different series."""

        if not args[0] in ["file", "link", "package"]:
                print "pkg: unknown add object '%s'" % args[0]
                usage()

        trans_id = os.environ["PKG_TRANS_ID"]
        repo = config.install_uri
        uri_exp = urlparse.urlparse(repo)
        host, port = re.split(":", uri_exp[1])
        selector = "/add/%s/%s" % (trans_id, args[0])

        if args[0] == "file":
                # XXX Need to handle larger files than available swap.
                file = open(args[2])
                data = file.read()
        else:
                sys.exit(99)

        headers = {}
        headers["Path"] = args[1]

        c = httplib.HTTPConnection(host, port)
        c.connect()
        c.request("POST", selector, data, headers)


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
        elif subcommand == "open":
                trans_open(pcfg, pargs)
        elif subcommand == "close":
                trans_close(pcfg, pargs)
        elif subcommand == "add":
                trans_add(pcfg, pargs)
        else:
                print "pkg: unknown subcommand '%s'" % pargs[0]
                usage()
