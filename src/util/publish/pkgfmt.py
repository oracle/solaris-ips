#!/usr/bin/python2.6
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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#


# Format a manifest according to the following rules:
#
# 1) File leading comments are left alone
# 2) All other comments stay w/ the first non-comment line that follows
#    them
# 3) Actions appear grouped by type, ignoring macros
# 4) Actions are limited to 80 chars; continuation lines are accepted
#    and emitted
# 5) varient & facet tags appear at the end of actions
# 6) multi-valued tags appear at the end aside from the above
# 7) key attribute tags come first

import getopt
import gettext
import os
import sys
import shlex
import tempfile
import traceback

import pkg
import pkg.actions
from pkg.misc import emsg, PipeError

opt_unwrap = False
opt_check = False

def usage(errmsg="", exitcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                error(errmsg)

        print >> sys.stderr, _("""\
Usage:
        pkgfmt [-cu] [file1] ... """)

        sys.exit(exitcode)

def error(text, exitcode=1):
        """Emit an error message prefixed by the command name """

        # If we get passed something like an Exception, we can convert
        # it down to a string.
        text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + "pkgfmt: " + text_nows)

        if exitcode != None:
                sys.exit(exitcode)

def read_line(f):
        """Generates the lines in the file as tuples containing
        (action, prepended macro, list of prepended comment lines);
        handles continuation lines, transforms, etc."""

        accumulate = ""
        noncomment_line_seen = False
        comments = []

        for line in f:
                line = line.strip()
                if line.endswith("\\"):
                        accumulate += line[:-1]
                        continue

                elif accumulate:
                        line = accumulate + line
                        accumulate = ""

                if not line or line[0] == "#":
                        comments.append(line)
                        continue

                if not noncomment_line_seen:
                        noncomment_line_seen = True
                        yield None, "", comments
                        comments = []

                if line.startswith("$("):
                        cp = line.index(")")
                        macro = line[0:cp+1]
                        actstr = line[cp + 1:]
                else:
                        macro = ""
                        actstr = line

                if actstr[0] == "<" and actstr[-1] == ">":
                        yield None, macro + actstr, comments
                        comments = []
                        macro = ""
                        continue

                try:
                        act = pkg.actions.fromstr(actstr)
                except (pkg.actions.MalformedActionError,
                    pkg.actions.UnknownActionError,
                    pkg.actions.InvalidActionError), e:
                        # cannot convert; treat as special macro
                        yield None, actstr, comments
                        continue
                yield act, macro, comments

                comments = []

def cmplines(a, b):
        """Compare two line tuples for sorting"""
        # we know that all lines that reach here have actions
        # make set actions first
        # depend actions last
        # rest in alpha order

        def typeord(a):
                if a.name == "set":
                        return 1
                if a.name == "depend":
                        return 3
                return 2
        c = cmp(typeord(a[0]) , typeord(b[0]))
        if c:
                return c
        c = cmp(a[0].name, b[0].name)
        if c:
                return c

        if a[0].name == "set" and a[0].attrs["name"] == "pkg.fmri":
                return -1

        if b[0].name == "set" and b[0].attrs["name"] == "pkg.fmri":
                return 1


        if a[0].name == "set" and a[0].attrs["name"].startswith("pkg.") and \
            not b[0].attrs["name"].startswith("pkg."):
                return -1

        if b[0].name == "set" and b[0].attrs["name"].startswith("pkg.") and \
            not a[0].attrs["name"].startswith("pkg."):
                return 1


        key_attr = a[0].key_attr
        if key_attr:
                c = cmp(a[0].attrs[key_attr], b[0].attrs[key_attr])
                if c:
                        return c

        return cmp(str(a[0]), str(b[0]))


def write_line(line, fileobj):
        """Write out a manifest line"""
        # write out any comments w/o changes

        comments = "\n".join(line[2])
        act = line[0]
        out = line[1] + act.name

        if hasattr(act, "hash") and act.hash != "NOHASH":
                out += " " + act.hash

        # handle quoting of attribute values
        def q(s):
                if " " in s or s == "":
                        return '"%s"' % s
                else:
                        return s
        # high order bits in sorting
        def kvord(a):
                if a[0].startswith("variant."):
                        return 4
                if a[0].startswith("facet."):
                        return 3
                if isinstance(a[1], list):
                        return 2
                # note closure hack...
                if act.key_attr != a[0]:
                        return 1
                return 0
        # actual cmp function
        def cmpkv(a, b):
                c = cmp(kvord(a), kvord(b))
                if c:
                        return c
                return cmp(a[0], b[0])

        def grow(a, b, force_nl=False):
                if opt_unwrap or not force_nl:
                        lastnl = a.rfind("\n")
                        if lastnl == -1:
                                lastnl = 0
                        if opt_unwrap or (len(a) - lastnl + len(b) < 78):
                                return a + " " + b
                return a + " \\\n    " + b

        for k, v in sorted(act.attrs.iteritems(), cmp=cmpkv):
                if isinstance(v, list) or isinstance(v, set):
                        for lmt in sorted(v):
                                out = grow(out, "%s=%s" % (k, q(lmt)),
                                           force_nl=(k=="alias"))
                else:
                        out = grow(out, k + "=" + q(v))
        if comments:
                print >> fileobj, comments
        print >> fileobj, out


def main_func():
        gettext.install("pkg", "/usr/share/locale")
        global opt_unwrap
        global opt_check

        ret = 0

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "cu", ["help"])
                for opt, arg in opts:
                        if opt == "-u":
                                opt_unwrap = True
                        if opt == "-c":
                                opt_check = True
                        if opt in ("--help", "-?"):
                                usage(exitcode=0)

        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        flist = pargs
        if not flist:
                fmt_file(sys.stdin, sys.stdout)
                return ret

        for fname in flist:
                tname = None
                try:
                        # force path to be absolute; gives better diagnostics if
                        # something goes wrong.
                        path = os.path.abspath(fname)
                        pathdir = os.path.dirname(path)
                        tfd, tname = \
                             tempfile.mkstemp(dir=pathdir)

                        t = os.fdopen(tfd, "w")
                        f = file(fname)

                        fmt_file(f, t)
                        f.close()
                        t.close()

                        if opt_check:
                                f1 = open(fname, "r")
                                whole_f1 = f1.read()
                                f2 = open(tname, "r")
                                whole_f2 = f2.read()
                                if whole_f1 == whole_f2:
                                        ret = 0
                                else:
                                        error("%s: not in pkgfmt form" % fname,
                                             exitcode=None)
                                        ret = 1
                                os.unlink(tname)
                        else:
                                try:
                                        os.rename(tname, fname)
                                except EnvironmentError, e:
                                        if os.path.exists(tname):
                                                os.unlink(tname)
                                        error(str(e), exitcode=1)
                except (EnvironmentError, IOError), e:
                        try:
                                os.unlink(tname)
                        except:
                                pass
                        error(str(e), exitcode=1)
                except BaseException:
                        try:
                                os.unlink(tname)
                        except:
                                pass
                        raise


        return ret

def fmt_file(in_file, out_file):
        lines = []
        for tp in read_line(in_file):
                if tp[0] is None:
                        for l in tp[2]: # print any leading comment
                                        # or transforms or unparseables
                                print >> out_file, l
                        if tp[1]:
                                print >> out_file, tp[1]
                else:
                        lines.append(tp)

        lines.sort(cmp=cmplines)

        for l in lines:
                write_line(l, out_file)


if __name__ == "__main__":
        try:
                __ret = main_func()
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

