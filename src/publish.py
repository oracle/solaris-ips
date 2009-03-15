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

# pkgsend - publish package transactions
#
# Typical usage is
#
#       pkgsend open
#       [pkgsend summary]
#       pkgsend close
#
# A failed transaction can be cleared using
#
#       pkgsend close -A

import fnmatch
import getopt
import gettext
import os
import sys
import traceback

import pkg.actions
import pkg.bundle
import pkg.publish.transaction as trans
from pkg.misc import msg, emsg, PipeError

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
        else:
                # If we get passed something like an Exception, we can convert
                # it down to a string.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + "pkgsend: " + text_nows)

def usage(usage_error=None, cmd=None, retcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)

        print _("""\
Usage:
        pkgsend [options] command [cmd_options] [operands]

Packager subcommands:
        pkgsend create-repository
        pkgsend open [-en] pkg_fmri
        pkgsend add action arguments
        pkgsend import [-T file_pattern] bundlefile ...
        pkgsend include [-d basedir] manifest ...
        pkgsend close [-A]

        pkgsend rename src_fmri dest_fmri

Options:
        -s repo_uri     target repository URI
        --help or -?    display usage message

Environment:
        PKG_REPO""")
        sys.exit(retcode)

def trans_create_repository(repo_uri, args):
        """Creates a new repository at the location indicated by repo_uri."""

        if args:
                usage(_("command does not take operands"),
                    cmd="create-repository")

        try:
                trans.Transaction(repo_uri, create_repo=True)
        except trans.TransactionError, e:
                error(e, cmd="create-repository")
                return 1
        return 0

def trans_open(repo_uri, args):

        opts, pargs = getopt.getopt(args, "en")

        parsed = []
        eval_form = True
        for opt, arg in opts:
                parsed.append(opt)
                if opt == "-e":
                        eval_form = True
                if opt == "-n":
                        eval_form = False

        if "-e" in parsed and "-n" in parsed:
                usage(_("only -e or -n may be specified"), cmd="open")

        if len(pargs) != 1:
                usage(_("open requires one package name"), cmd="open")

        t = trans.Transaction(repo_uri, pkg_name=pargs[0])
        if eval_form:
                msg("export PKG_TRANS_ID=%s" % t.open())
        else:
                msg(t.open())

        return 0

def trans_close(repo_uri, args):
        abandon = False
        trans_id = None

        opts, pargs = getopt.getopt(args, "At:")

        for opt, arg in opts:
                if opt == "-A":
                        abandon = True
                if opt == "-t":
                        trans_id = arg

        if trans_id is None:
                try:
                        trans_id = os.environ["PKG_TRANS_ID"]
                except KeyError:
                        usage(_("No transaction ID specified using -t or in "
                            "$PKG_TRANS_ID."), cmd="close")

        t = trans.Transaction(repo_uri, trans_id=trans_id)
        pkg_state, pkg_fmri = t.close(abandon)
        for val in (pkg_state, pkg_fmri):
                if val is not None:
                        msg(val)
        return 0

def trans_add(repo_uri, args):
        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                usage(_("No transaction ID specified in $PKG_TRANS_ID"),
                    cmd="add")

        if not args:
                usage(_("No arguments specified for subcommand."), cmd="add")
        elif args[0] in ("file", "license"):
                if len(args) < 2:
                        raise RuntimeError, _("A filename must be provided "
                            "for this action.")

                try:
                        action = pkg.actions.fromlist(args[0], args[2:],
                            data=args[1])
                except ValueError, e:
                        error(e[0], cmd="add")
                        return 1

                if "pkg.size" not in action.attrs:
                        fs = os.lstat(args[1])
                        action.attrs["pkg.size"] = str(fs.st_size)
        else:
                try:
                        action = pkg.actions.fromlist(args[0], args[1:])
                except ValueError, e:
                        error(e[0], cmd="add")
                        return 1

        t = trans.Transaction(repo_uri, trans_id=trans_id)
        t.add(action)
        return 0

def trans_rename(repo_uri, args):
        if not args:
                usage(_("No arguments specified for subcommand."), cmd="rename")

        t = trans.Transaction(repo_uri)
        t.rename(args[0], args[1])
        return 0

def trans_include(repo_uri, fargs):

        basedir = None

        opts, pargs = getopt.getopt(fargs, "d:")
        for opt, arg in opts:
                if opt == "-d":
                        basedir = arg

        try:
                trans_id = os.environ["PKG_TRANS_ID"]
        except KeyError:
                usage(_("No transaction ID specified in $PKG_TRANS_ID"),
                    cmd="include")

        if not fargs:
                usage(_("No arguments specified for subcommand."),
                    cmd="include")

        t = trans.Transaction(repo_uri, trans_id=trans_id)
        for filename in pargs:
                f = file(filename)
                for line in f:
                        line = line.strip() #
                        if not line or line[0] == '#':
                                continue
                        args = line.split()
                        if args[0] in ("file", "license"):
                                if basedir:
                                        fullpath = args[1].lstrip(os.path.sep)
                                        fullpath = os.path.join(basedir,
                                            fullpath)
                                else:
                                        fullpath = args[1]

                                try:
                                        # ignore local pathname
                                        line = line.replace(args[1], "NOHASH",
                                            1)
                                        action = pkg.actions.fromstr(line,
                                            data=fullpath)
                                except ValueError, e:
                                        error(e[0], cmd="include")
                                        return 1
                        else:
                                try:
                                        action = pkg.actions.fromstr(line)
                                except ValueError, e:
                                        error(e[0], cmd="include")
                                        return 1

                        # cleanup any leading / in path to prevent problems
                        if "path" in action.attrs:
                                np = action.attrs["path"].lstrip(os.path.sep)
                                action.attrs["path"] = np

                        t.add(action)
        return 0

def trans_import(repo_uri, args):
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

        if not args:
                usage(_("No arguments specified for subcommand."),
                    cmd="import")

        for filename in pargs:
                bundle = pkg.bundle.make_bundle(filename)
                t = trans.Transaction(repo_uri, trans_id=trans_id)

                for action in bundle:
                        if action.name == "file":
                                basename = os.path.basename(
                                    action.attrs["path"])
                                for pattern in timestamp_files:
                                        if fnmatch.fnmatch(basename, pattern):
                                                break
                                else:
                                        try:
                                                del action.attrs["timestamp"]
                                        except KeyError:
                                                pass
                        t.add(action)
        return 0

def main_func():
        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgsend", "/usr/lib/locale")

        try:
                repo_uri = os.environ["PKG_REPO"]
        except KeyError:
                repo_uri = "http://localhost:10000"

        show_usage = False
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "s:?", ["help"])
                for opt, arg in opts:
                        if opt == "-s":
                                repo_uri = arg
                        elif opt in ("--help", "-?"):
                                show_usage = True
        except getopt.GetoptError, e:
                usage(_("pkgsend: illegal global option -- %s") % e.opt)

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        show_usage = True

        if show_usage:
                usage(retcode=0)
        elif not subcommand:
                usage()

        ret = 0
        try:
                if subcommand == "create-repository":
                        ret = trans_create_repository(repo_uri, pargs)
                elif subcommand == "open":
                        ret = trans_open(repo_uri, pargs)
                elif subcommand == "close":
                        ret = trans_close(repo_uri, pargs)
                elif subcommand == "add":
                        ret = trans_add(repo_uri, pargs)
                elif subcommand == "import":
                        ret = trans_import(repo_uri, pargs)
                elif subcommand == "include":
                        ret = trans_include(repo_uri, pargs)
                elif subcommand == "rename":
                        ret = trans_rename(repo_uri, pargs)
                else:
                        usage(_("unknown subcommand '%s'") % subcommand)
        except getopt.GetoptError, e:
                usage(_("illegal %s option -- %s") % (subcommand, e.opt))

        return ret

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
        try:
                __ret = main_func()
        except (pkg.actions.ActionError, trans.TransactionError,
            RuntimeError), _e:
                print >> sys.stderr, "pkgsend: %s" % _e
                __ret = 1
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = 1
        except SystemExit, _e:
                raise _e
        except:
                traceback.print_exc()
                error(
                    _("\n\nThis is an internal error.  Please let the "
                    "developers know about this\nproblem by filing a bug at "
                    "http://defect.opensolaris.org and including the\nabove "
                    "traceback and this message.  The version of pkg(5) is "
                    "'%s'.") % pkg.VERSION)
                __ret = 99
        sys.exit(__ret)
