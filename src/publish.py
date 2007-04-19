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

# pkgsend - publish package transactions
#
# Typical usage is
#
#       pkgsend open
#       pkgsend batch
#       [pkgsend summary]
#       pkgsend close
#
# where the batch file contains a series of subcommand invocations.
# A failed transaction can be cleared using
#
#       pkgsend close -A
#
# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.

import getopt
import httplib
import os
import re
import sys
import urllib
import urllib2
import urlparse

import pkg.catalog as catalog
import pkg.config as config
import pkg.content as content
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.image as image
import pkg.package as package
import pkg.version as version

def usage():
        print """\
Usage:
        pkgsend [options] command [cmd_options] [operands]

Packager subcommands:
        pkgsend open [-en] pkg_fmri
        pkgsend add file|link|device path file
        pkgsend batch file
        pkgsend delete path
        pkgsend meta include|require|exclude pkg_fmri
        pkgsend meta disclaim pkg_fmri
        pkgsend meta set property value
        pkgsend meta unset property
        pkgsend summary
        pkgsend close [-A]

Options:
        --repo, -s

Environment:
        PKG_REPO"""
        sys.exit(2)

def trans_open(config, args):
        opts = None
        pargs = None
        try:
                opts, pargs = getopt.getopt(args, "e")
        except:
                print "pkgsend: illegal open option(s)"
                usage()

        eval_form = True
        for opt, arg in opts:
                if opt == "-e":
                        eval_form = True
                if opt == "-n":
                        eval_form = False

        if len(pargs) != 1:
                print "pkgsend: open requires one package name"
                usage()

        # POST /open/pkg_name
        repo = config.install_uri

        # get client release
        # populate Client-Release header
        repo = config.install_uri
        uri_exp = urlparse.urlparse(repo)
        host, port = re.split(":", uri_exp[1])

        c = httplib.HTTPConnection(host, port)
        c.connect()
        c.putrequest("GET", "/open/%s" % urllib.quote(pargs[0], ""))
        c.putheader("Client-Release", os.uname()[2])
        c.endheaders()

        r = c.getresponse()

        id = r.getheader("Transaction-ID", None)
        if id == None:
                print "pkgsend: no transaction ID provided in response"
                sys.exit(1)

        if eval_form:
                print "export PKG_TRANS_ID=%s" % id
        else:
                print id

        return

def trans_close(config, args):
        opts = None
        pargs = None
        abandon = False
        trans_id = None

        try:
                if len(args) > 0:
                        opts, pargs = getopt.getopt(args, "At:")

                        for opt, arg in opts:
                                if opt == "-A":
                                        abandon = True
                                if opt == "-t":
                                        trans_id = arg
        except:
                print "pkgsend: illegal option(s) to close"
                usage()

        if trans_id == None:
                # XXX try/except -> no transaction specified
                trans_id = os.environ["PKG_TRANS_ID"]

        repo = config.install_uri
        op = "close"
        if abandon:
                op = "abandon"

        uri = urlparse.urljoin(repo, "%s/%s" % (op, trans_id))
        try:
                c = urllib2.urlopen(uri)
        except urllib2.HTTPError:
                print "pkgsend: transaction close failed"
                sys.exit(1)

        if abandon:
                return

        lines = c.readlines()
        for line in lines:
                if re.match("^Package-FMRI:", line):
                        m = re.match("^Package-FMRI: (.*)", line)
                        print m.group(1)
                elif re.match("^State:", line):
                        m = re.match("^State: (.*)", line)
                        print m.group(1)

        return

def trans_add(config, args):
        """POST the file contents to the transaction.  Default is to post to the
        currently open content series.  -s option selects a different series.

        dir mode owner group path [n=v ...]
        file mode owner group path [n=v ...]
        displace mode owner group path [n=v ...]
        preserve mode owner group path [n=v ...]

        link path_from path_to [n=v ...]
                This action is exclusively for symbolic links.

        service manifest_path [n=v ...]
                0444 root sys
        driver class  [n=v ...] (a whole slew of specifiers)
                0755 root sys binaries; 0644 root sys conf file

        restart fmri [n=v ...]
                [no file, illegal in user image]

        XXX do we need hardlinks?

        XXX driver action could follow the upload of two or three files.  In
        this case, the action can either cause the transaction to fail (since
        modes and ownership may be inconsistent) or correct the transaction to
        follow convention (with a warning).

        XXX driver action must be flavour dependent, as a driver may exist only
        on a single platform kind.

        XXX Setting a driver from the command line, rather than via a batched
        file, seems error prone.

        XXX File types needs to be made a modular API, and not be hard-coded."""

        if not args[0] in [
            "dir",
            "displace",
            "driver",
            "file",
            "link",
            "preserve",
            "restart",
            "service"
        ]:
                print "pkgsend: unknown add object '%s'" % args[0]
                usage()

        trans_id = os.environ["PKG_TRANS_ID"]
        repo = config.install_uri
        uri_exp = urlparse.urlparse(repo)
        host, port = re.split(":", uri_exp[1])
        selector = "/add/%s/%s" % (trans_id, args[0])

        headers = {}

        if args[0] == "file" or args[0] == "displace" or args[0] == "preserve":
                # XXX Need to handle larger files than available swap.
                headers["Mode"] = args[1]
                headers["Owner"] = args[2]
                headers["Group"] = args[3]
                headers["Path"] = args[4]
                file = open(args[5])
                data = file.read()
                # XXX name-value handling
                # vars_to_headers(headers, args[6:]
        elif args[0] == "dir":
                headers["Mode"] = args[1]
                headers["Owner"] = args[2]
                headers["Group"] = args[3]
                headers["Path"] = args[4]
                data = ""
                # XXX name-value handling
                # vars_to_headers(headers, args[2:]
        elif args[0] == "service":
                headers["Manifest"] = args[1]
                file = open(args[2])
                data = file.read()
                # XXX name-value handling
                # vars_to_headers(headers, args[3:]
        elif args[0] == "restart":
                print "pkgsend: restart action not defined"
                sys.exit(99)
        elif args[0] == "link":
                print "pkgsend: link action not defined"
                sys.exit(99)
        elif args[0] == "driver":
                print "pkgsend: driver action not defined"
                sys.exit(99)
        else:
                print "pkgsend: unknown action '%s'" % args[0]
                sys.exit(99)

        c = httplib.HTTPConnection(host, port)
        c.connect()
        c.request("POST", selector, data, headers)

def trans_delete(config, args):
        return

def trans_meta(config, args):
        """Via POST request, transfer a piece of metadata to the server."""

        if not args[0] in ["set", "unset"]:
                print "pkgsend: unknown metadata item '%s'" % args[0]
                usage()

        trans_id = os.environ["PKG_TRANS_ID"]
        repo = config.install_uri
        uri_exp = urlparse.urlparse(repo)
        host, port = re.split(":", uri_exp[1])
        selector = "/meta/%s/%s" % (trans_id, args[0])

        # subcommand handling
        # /meta/trans_id/set/property_name
        #       Payload is value.
        # /meta/trans_id/unset/property_name
        #       No payload.
        # /meta/trans_id/include
        # /meta/trans_id/require
        # /meta/trans_id/exclude
        #       Payload is fmri.
        # /meta/trans_id/disclaim
        #       Payload is fmri.

        headers = {}
        headers["Path"] = args[1]

        c = httplib.HTTPConnection(host, port)
        c.connect()
        c.request("POST", selector, data, headers)
        return

def trans_summary(config, args):
        return

def batch(config, args):
        return

pcfg = config.ParentRepo("http://localhost:10000", ["http://localhost:10000"])


if __name__ == "__main__":
        opts = None
        pargs = None
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:R:")
        except:
                print "pkgsend: illegal global option(s)"
                usage()

        if pargs == None or len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        if subcommand == "open":
                trans_open(pcfg, pargs)
        elif subcommand == "close":
                trans_close(pcfg, pargs)
        elif subcommand == "add":
                trans_add(pcfg, pargs)
        else:
                print "pkgsend: unknown subcommand '%s'" % subcommand
                usage()
