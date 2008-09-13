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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
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
import fnmatch

import pkg.bundle
import pkg.config as config

import pkg.publish.transaction as trans

def usage():
        print _("""\
Usage:
        pkgsend [options] command [cmd_options] [operands]

Packager subcommands:
        pkgsend open [-en] pkg_fmri
        pkgsend add action arguments 
        pkgsend import [-T file_pattern] bundlefile ...
        pkgsend include [-d basedir] manifest ...
        pkgsend close [-A]

        pkgsend rename src_fmri dest_fmri

Options:
        -s repo_url     destination repository server URL prefix

Environment:
        PKG_REPO""")
        sys.exit(2)

def _check_status(operation, status, msg = None):
        if status / 100 == 4 or status / 100 == 5:
                if msg:
                        msg = ": " + msg
                else:
                        msg = ""
                print >> sys.stderr, \
                    _("pkgsend: %s failed (status %s)%s") % (operation, status, msg)
                sys.exit(1)

def trans_open(config, args):

        opts, pargs = getopt.getopt(args, "en")

        eval_form = True
        for opt, arg in opts:
                if opt == "-e":
                        eval_form = True
                if opt == "-n":
                        eval_form = False

        if len(pargs) != 1:
                print >> sys.stderr, \
                    _("pkgsend: open requires one package name")
                usage()

        t = trans.Transaction()

        status, id = t.open(config, pargs[0])
        _check_status('open', status)

        if id == None:
                print >> sys.stderr, \
                    _("pkgsend: no transaction ID provided in response")
                sys.exit(1)

        if eval_form:
                print "export PKG_TRANS_ID=%s" % id
        else:
                print id

        return

def trans_close(config, args):
        abandon = False
        trans_id = None

        opts, pargs = getopt.getopt(args, "At:")

        for opt, arg in opts:
                if opt == "-A":
                        abandon = True
                if opt == "-t":
                        trans_id = arg

        if trans_id == None:
                try:
                        trans_id = os.environ["PKG_TRANS_ID"]
                except KeyError:
                        print >> sys.stderr, _("No transaction ID specified")
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
                print >> sys.stderr, \
                    _("No transaction ID specified in $PKG_TRANS_ID")
                sys.exit(1)

        if args[0] in ("file", "license"):
                try:
                        action = pkg.actions.fromlist(args[0], args[2:])
                except ValueError, e:
                        print >> sys.stderr, e[0]
                        sys.exit(1)
                def opener():
                        return open(args[1], "rb")
                action.data = opener
        else:
                try:
                        action = pkg.actions.fromlist(args[0], args[1:])
                except ValueError, e:
                        print >> sys.stderr, e[0]
                        sys.exit(1)

        t = trans.Transaction()
        status, msg, body = t.add(config, trans_id, action)
        _check_status('add', status, msg)

def trans_rename(config, args):
        t = trans.Transaction()
        status, msg, body = t.rename(config, args[0], args[1])
        _check_status('rename', status, msg)

def trans_include(config, fargs):

        basedir = None

        opts, pargs = getopt.getopt(fargs, "d:")

        for opt, arg in opts:
                if opt == "-d":
                        basedir = arg

        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                print >> sys.stderr, \
                    _("No transaction ID specified in $PKG_TRANS_ID")
                sys.exit(1)

        t = trans.Transaction()
        for filename in pargs:
                f = file(filename)
                for line in f:
                        line = line.strip() # 
                        if not line or line[0] == '#':
                                continue
                        args = line.split() 
                        if args[0] in ("file", "license"):
                                try:
                                        # ignore local pathname
                                        line = line.replace(args[1], "NOHASH", 1)
                                        action = pkg.actions.fromstr(line)
                                except ValueError, e:
                                        print >> sys.stderr, e[0]
                                        sys.exit(1)

                                if basedir:
                                        fullpath = args[1].lstrip(os.path.sep)
                                        fullpath = os.path.join(basedir,
                                            fullpath)
                                else:
                                        fullpath = args[1]

                                def opener():
                                        return open(fullpath, "rb")
                                action.data = opener

                        else:
                                try:
                                        action = pkg.actions.fromstr(line)
                                except ValueError, e:
                                        print >> sys.stderr, e[0]
                                        sys.exit(1)

                        # cleanup any leading / in path to prevent problems
                        if "path" in action.attrs:
                                np = action.attrs["path"].lstrip(os.path.sep)
                                action.attrs["path"] = np

                        status, msg, body = t.add(config, trans_id, action)
                        _check_status('add', status, msg)

def trans_import(config, args):
        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                print >> sys.stderr, \
                    _("No transaction ID specified in $PKG_TRANS_ID")
                sys.exit(1)
                
        opts, pargs = getopt.getopt(args, "T:")

        timestamp_files = []

        for opt, arg in opts:
                if opt == "-T":
                        timestamp_files.append(arg)
        
        for filename in pargs:
                bundle = pkg.bundle.make_bundle(filename)
                t = trans.Transaction()

                for action in bundle:
                        if action.name == "file":
                                basename = os.path.basename(action.attrs["path"])
                                for pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename, pattern):
                                                break
                                else:
                                        del action.attrs["timestamp"]
                        try:
                                status, msg, body = t.add(config, trans_id, 
                                    action)
                                _check_status('import', status, msg)
                        except TypeError, e:
                                print "warning:", e


        
def trans_delete(config, args):
        return

def batch(config, args):
        return

def main_func():
        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgsend", "/usr/lib/locale")

        try:
                repo_url = os.environ["PKG_REPO"]
        except KeyError:
                repo_url = "http://localhost:10000"

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:")
                for opt, arg in opts:
                        if opt == "-s":
                                repo_url = arg

        except getopt.GetoptError, e:
                print >> sys.stderr, \
                    _("pkgsend: illegal global option -- %s") % e.opt
                usage()

        if pargs == None or len(pargs) == 0:
                usage()

        pcfg = config.ParentRepo(repo_url, [repo_url])

        subcommand = pargs[0]
        del pargs[0]

        try:
                if subcommand == "open":
                        trans_open(pcfg, pargs)
                elif subcommand == "close":
                        trans_close(pcfg, pargs)
                elif subcommand == "add":
                        trans_add(pcfg, pargs)
                elif subcommand == "import":
                        trans_import(pcfg, pargs)
                elif subcommand == "include":
                        trans_include(pcfg, pargs)
                elif subcommand == "rename":
                        trans_rename(pcfg, pargs)
                else:
                        print >> sys.stderr, \
                            _("pkgsend: unknown subcommand '%s'") % subcommand
                        usage()
        except getopt.GetoptError, e:
                print >> sys.stderr, \
                    _("pkgsend: illegal %s option -- %s") % (subcommand, e.opt)
                usage()

        return 0



#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":

        try:
                ret = main_func()
        except SystemExit, e:
                raise e
        except:
                traceback.print_exc()
                sys.exit(99)
        sys.exit(ret)
