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

import getopt
import os
import sys

import pkg.bundle
import pkg.config as config
import pkg.content as content
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.package as package
from pkg.sysvpkg import SolarisPackage
import pkg.version as version

import pkg.publish.transaction as trans

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

        t = trans.Transaction()

        status, id = t.open(config, pargs[0])

        if status / 100 == 4 or status / 100 == 5:
                print "pkgsend: server failed (status %s)" % status
                sys.exit(1)

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
                try:
                        trans_id = os.environ["PKG_TRANS_ID"]
                except KeyError:
                        print "No transaction ID specified"
                        sys.exit(1)

        t = trans.Transaction()
        ret, hdrs = t.close(config, trans_id, abandon)

        if abandon:
                return

        print hdrs["State"]
        print hdrs["Package-FMRI"]

        return

def trans_add(config, args):
        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                print "No transaction ID specified in $PKG_TRANS_ID"
                sys.exit(1)

        # Specifies the ordering of the commandline arguments for each file type
        # XXX this needs to be modularized.  Or does it -- should it just
        # pass the args into Transaction.add() by order, and have that sort
        # it out?  If this is to be modularized here, then pkgsend will
        # have to know how to load the extension (perhaps another API
        # call), but if it passes args by order, then the transaction API
        # won't be by keyword, which I think is less clean (ordering is
        # *such* a commandline thing).
        attrs = {
                "dir": ("mode", "owner", "group", "path"),
                "displace": ("mode", "owner", "group", "path", "file"),
                "file": ("mode", "owner", "group", "path", "file"),
                "preserve": ("mode", "owner", "group", "path", "file"),
                "service": ("manifest", ),
        }

        try:
                kw = dict((attrs[args[0]][i], args[i + 1])
                        for i in range(len(attrs[args[0]])))
        except KeyError, e:
                print 'pkgsend: action "%s" not defined' % e[0]
                sys.exit(1)
        except IndexError, e:
                print 'pkgsend: not enough arguments for "%s" action' % args[0]
                sys.exit(1)

        t = trans.Transaction()
        t.add(config, trans_id, args[0], **kw)

def trans_delete(config, args):
        return

def trans_meta(config, args):
        """Via POST request, transfer a piece of metadata to the server."""

        if not args[0] in ["set", "unset"]:
                print "pkgsend: unknown metadata item '%s'" % args[0]
                usage()

        trans_id = os.environ["PKG_TRANS_ID"]

        t = trans.Transaction()
        t.meta(config, trans_id, args)

        return

def trans_summary(config, args):
        return

def batch(config, args):
        return

def send_bundle(config, args):
        filename = args[0]

        bundle = pkg.bundle.make_bundle(filename)

        t = trans.Transaction()
        status, id = t.open(config, bundle.pkgname + "@0-1")

        for file in bundle:
                t.add(config, id, file.type, **file.attrs)

        t.close(config, id)


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
        elif subcommand == "send":
                send_bundle(pcfg, pargs)
        else:
                print "pkgsend: unknown subcommand '%s'" % subcommand
                usage()

        sys.exit(0)
