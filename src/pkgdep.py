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

import errno
import getopt
import gettext
import locale
import os
import sys
import traceback

import pkg
import pkg.misc as misc
import pkg.publish.dependencies as dependencies
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
        emsg(ws + "pkgdep: " + text_nows)

def usage(usage_error=None, cmd=None, retcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)

        print _("""\
Usage:
        pkgdep [options] manifest proto_dir

Options:
        -I              show internally satisfied dependencies
        -M              echo the input manifest before showing dependencies
        -m              show file types for which no analysis was performed
        --help or -?    display usage message

Environment:
        PKG_SEND_PLATFORM
        PKG_SEND_ISALIST""")
        sys.exit(retcode)


def main_func():
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale")
        
        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "IMm?",
                    ["help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        remove_internal_deps = True
        platform = None
        isalist = None
        echo_manf = False
        show_missing = False
        show_usage = False

        for opt, arg in opts:
                if opt == "-I":
                        remove_internal_deps = False
                elif opt == "-M":
                        echo_manf = True
                elif opt == "-m":
                        show_missing = True
                elif opt in ("--help", "-?"):
                        show_usage = True
        if show_usage:
                usage(retcode=0)
        if len(pargs) != 2:
                usage()

        retcode = 0
                
        manf = pargs[0]
        proto_dir = pargs[1]

        try:
                ds, es, ms = dependencies.list_implicit_deps(manf, proto_dir,
                    remove_internal_deps)
        except IOError, e:
                if e.errno == errno.ENOENT:
                        error("Could not find manifest file %s" % manf)
                        return 1
                raise

        if echo_manf:
                fh = open(manf, "rb")
                for l in fh:
                        msg(l.rstrip())
                fh.close()
        
        for d in sorted(ds):
                msg(d)

        if show_missing:
                for m in ms:
                        emsg(m)
                
        for e in es:
                emsg(e)
                retcode = 1
        return retcode

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
        try:
                __ret = main_func()
        except RuntimeError, _e:
                emsg("pkgdep: %s" % _e)
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
