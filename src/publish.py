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
import gettext
import os
import sys
import threading
import traceback

import pkg.bundle
import pkg.config as config
import pkg.dependency as dependency
import pkg.fmri as fmri
import pkg.package as package
import pkg.version as version

import pkg.publish.transaction as trans

import pkg.Queue25 as Queue25

def usage():
        print _("""\
Usage:
        pkgsend [options] command [cmd_options] [operands]

Packager subcommands:
        pkgsend open [-en] pkg_fmri
        pkgsend add file|link|hardlink|device path file
        pkgsend batch file
        pkgsend delete path
        pkgsend meta include|require|exclude pkg_fmri
        pkgsend meta disclaim pkg_fmri
        pkgsend meta set property value
        pkgsend meta unset property
        pkgsend summary
        pkgsend close [-A]

Options:
        -s repo_url     destination repository server URL prefix

Environment:
        PKG_REPO""")
        sys.exit(2)

def trans_open(config, args):
        opts = None
        pargs = None
        try:
                opts, pargs = getopt.getopt(args, "e")
        except getopt.GetoptError, e:
                print _("pkgsend: illegal open option '%s'") % e.opt
                usage()

        eval_form = True
        for opt, arg in opts:
                if opt == "-e":
                        eval_form = True
                if opt == "-n":
                        eval_form = False

        if len(pargs) != 1:
                print _("pkgsend: open requires one package name")
                usage()

        t = trans.Transaction()

        status, id = t.open(config, pargs[0])

        if status / 100 == 4 or status / 100 == 5:
                print _("pkgsend: server failed (status %s)") % status
                sys.exit(1)

        if id == None:
                print _("pkgsend: no transaction ID provided in response")
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
        except getopt.GetoptError, e:
                print _("pkgsend: illegal option to close: '%s'") % e.opt
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

        if hdrs:
                print hdrs["State"]
                print hdrs["Package-FMRI"]
        else:
                print "Failed with", ret

def trans_add(config, args):
        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                print "No transaction ID specified in $PKG_TRANS_ID"
                sys.exit(1)

        if args[0] in ("file", "license"):
                action = pkg.actions.fromlist(args[0], args[2:])
                def opener():
                        return open(args[1])
                action.data = opener
        else:
                action = pkg.actions.fromlist(args[0], args[1:])

        t = trans.Transaction()
        try:
                t.add(config, trans_id, action)
        except TypeError, e:
                print "warning:", e

def trans_delete(config, args):
        return

def trans_meta(config, args):
        """Via POST request, transfer a piece of metadata to the server."""

        if not args[0] in ["set", "unset"]:
                print _("pkgsend: unknown metadata item '%s'") % args[0]
                usage()

        trans_id = os.environ["PKG_TRANS_ID"]

        t = trans.Transaction()
        t.meta(config, trans_id, args)

        return

def batch(config, args):
        return

# Subclass the Python 2.5 Queue class to allow us to interrupt joins.
#
# The join here is enhanced with the addition of a timeout parameter.
# Rather than timing out the join itself, though: it merely times out
# the waits inside the join.  It's cheap, but gets the job done, and
# allows the interpreter to wake up and smell the ^C.
class q25_plus(Queue25.Queue):

        def join(self, timeout = None):
                self.all_tasks_done.acquire()
                try:
                    while self.unfinished_tasks:
                        self.all_tasks_done.wait(timeout)
                finally:
                    self.all_tasks_done.release()

def send_bundles(config, args):
        try:
                max_threads = int(os.environ["PKG_THREAD_MAX"])
        except (KeyError, ValueError):
                max_threads = 16

        if max_threads < 2:
                for filename in args:
                        send_bundle(config, filename)
                return

        nthreads = min(len(args), max_threads)

        q = q25_plus(nthreads)

        for i in xrange(nthreads):
                thr = threading.Thread(
                    target = send_bundles_forever,
                    args = (config, q))
                thr.setDaemon(True)
                thr.start()

        # It'd be nice to put the big ones in first.
        for filename in args:
                q.put(filename)

        q.join(timeout = 1)

def send_bundles_forever(config, queue):
        while True:
                filename = queue.get()
                # We have to catch all exceptions here, or the thread will hang
                # around forever.  Just print out the stack trace and keep on
                # going.
                try:
                        send_bundle(config, filename)
                except:
                        traceback.print_exc()
                queue.task_done()

def send_bundle(config, filename):
        bundle = pkg.bundle.make_bundle(filename)

        t = trans.Transaction()
        status, id = t.open(config, bundle.pkgname + "@0-1")

        for action in bundle:
                try:
                        t.add(config, id, action)
                except TypeError, e:
                        print "warning:", e

        t.close(config, id)

try:
        repo = os.environ["PKG_REPO"]
except KeyError:
        repo_url = "http://localhost:10000"

if __name__ == "__main__":
        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgsend", "/usr/lib/locale")

        opts = None
        pargs = None
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:")
                for opt, arg in opts:
                        if opt == "-s":
                                repo_url = arg

        except getopt.GetoptError, e:
                print _("pkgsend: illegal global option '%s'") % e.opt
                usage()

        if pargs == None or len(pargs) == 0:
                usage()

        pcfg = config.ParentRepo(repo_url, [repo_url])

        subcommand = pargs[0]
        del pargs[0]

        if subcommand == "open":
                trans_open(pcfg, pargs)
        elif subcommand == "close":
                trans_close(pcfg, pargs)
        elif subcommand == "add":
                trans_add(pcfg, pargs)
        elif subcommand == "send":
                send_bundles(pcfg, pargs)
        else:
                print _("pkgsend: unknown subcommand '%s'") % subcommand
                usage()

        sys.exit(0)
