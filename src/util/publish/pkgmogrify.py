#!/usr/bin/python2.7
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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
import getopt
import gettext
import locale
import six
import sys
import traceback
import warnings

import pkg.misc as misc
import pkg.mogrify as mog
from pkg.misc import PipeError
from pkg.client.pkgdefs import EXIT_OK, EXIT_OOPS, EXIT_BADOPT, EXIT_PARTIAL


def usage(errmsg="", exitcode=EXIT_BADOPT):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                print("pkgmogrify: {0}".format(errmsg), file=sys.stderr)

        print(_("""\
Usage:
        pkgmogrify [-vi] [-I includedir ...] [-D macro=value ...]
            [-O outputfile] [-P printfile] [inputfile ...]"""))
        sys.exit(exitcode)

def error(text, exitcode=EXIT_OOPS):
        """Emit an error message prefixed by the command name """

        print("pkgmogrify: {0}".format(text), file=sys.stderr)
        if exitcode != None:
                sys.exit(exitcode)

def main_func():
        outfilename = None
        printfilename = None
        verbose = False
        ignoreincludes = False
        includes = []
        macros = {}
        printinfo = []
        output = []

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ivD:I:O:P:?", ["help"])
                for opt, arg in opts:
                        if opt == "-D":
                                if "=" not in arg:
                                        error(_("macros must be of form name=value"))
                                a = arg.split("=", 1)
                                if a[0] == "":
                                        error(_("macros must be of form name=value"))
                                macros.update([("$({0})".format(a[0]), a[1])])
                        if opt == "-i":
                                ignoreincludes = True
                        if opt == "-I":
                                includes.append(arg)
                        if opt == "-O":
                                outfilename = arg
                        if opt == "-P":
                                printfilename = arg
                        if opt == "-v":
                                verbose = True
                        if opt in ("--help", "-?"):
                                usage(exitcode=EXIT_OK)

        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        try:
                mog.process_mog(pargs, ignoreincludes, verbose, includes,
                    macros, printinfo, output, error_cb=error)
        except RuntimeError as e:
                sys.exit(EXIT_OOPS)

        try:
                if printfilename == None:
                        printfile = sys.stdout
                else:
                        printfile = open(printfilename, "w")

                for p in printinfo:
                        print("{0}".format(p), file=printfile)

        except IOError as e:
                error(_("Cannot write extra data {0}").format(e))

        try:
                if outfilename == None:
                        outfile = sys.stdout
                else:
                        outfile = open(outfilename, "w")

                emitted = set()
                for comment, actionlist, prepended_macro in output:
                        if comment:
                                for l in comment:
                                        print("{0}".format(l), file=outfile)

                        for i, action in enumerate(actionlist):
                                if action is None:
                                        continue
                                if prepended_macro is None:
                                        s = "{0}".format(action)
                                else:
                                        s = "{0}{1}".format(prepended_macro, action)
                                # The first action is the original action and
                                # should be printed; later actions are all
                                # emitted and should only be printed if not
                                # duplicates.
                                if i == 0:
                                        print(s, file=outfile)
                                elif s not in emitted:
                                        print(s, file=outfile)
                                        emitted.add(s)
        except IOError as e:
                error(_("Cannot write output {0}").format(e))

        return 0

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())
        misc.set_fd_limits(printer=error)

        # Make all warnings be errors.
        warnings.simplefilter('error')
        if six.PY3:
                # disable ResourceWarning: unclosed file
                warnings.filterwarnings("ignore", category=ResourceWarning)
        try:
                exit_code = main_func()
        except (PipeError, KeyboardInterrupt):
                exit_code = EXIT_OOPS
        except SystemExit as __e:
                exit_code = __e
        except Exception as __e:
                traceback.print_exc()
                error(misc.get_traceback_message(), exitcode=None)
                exit_code = 99

        sys.exit(exit_code)
