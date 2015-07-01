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

#
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
import getopt
import gettext
import locale
import sys
import traceback

import pkg.actions
import pkg.variant as variant
import pkg.client.api_errors as apx
import pkg.manifest as manifest
import pkg.misc as misc
from pkg.misc import PipeError
from collections import defaultdict
from itertools import product

def usage(errmsg="", exitcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                print("pkgdiff: {0}".format(errmsg), file=sys.stderr)

        print(_("""\
Usage:
        pkgdiff [-i attribute]... [-o attribute]
            [-t action_name[,action_name]...]...
            [-v name=value]... (file1 | -) (file2 | -)"""))
        sys.exit(exitcode)

def error(text, exitcode=3):
        """Emit an error message prefixed by the command name """

        print("pkgdiff: {0}".format(text), file=sys.stderr)

        if exitcode != None:
                sys.exit(exitcode)

def main_func():
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())

        ignoreattrs = []
        onlyattrs = []
        onlytypes = []
        varattrs = defaultdict(set)

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "i:o:t:v:?", ["help"])
                for opt, arg in opts:
                        if opt == "-i":
                                ignoreattrs.append(arg)
                        elif opt == "-o":
                                onlyattrs.append(arg)
                        elif opt == "-t":
                                onlytypes.extend(arg.split(","))
                        elif opt == "-v":
                                args = arg.split("=")
                                if len(args) != 2:
                                        usage(_("variant option incorrect {0}").format(
                                            arg))
                                if not args[0].startswith("variant."):
                                        args[0] = "variant." + args[0]
                                varattrs[args[0]].add(args[1])
                        elif opt in ("--help", "-?"):
                                usage(exitcode=0)

        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        if len(pargs) != 2:
                usage(_("two manifest arguments are required"))

        if (pargs[0] == "-" and pargs[1] == "-"):
                usage(_("only one manifest argument can be stdin"))

        if ignoreattrs and onlyattrs:
                usage(_("-i and -o options may not be used at the same time."))

        for v in varattrs:
                if len(varattrs[v]) > 1:
                        usage(_("For any variant, only one value may be "
                            "specified."))
                varattrs[v] = varattrs[v].pop()

        ignoreattrs = set(ignoreattrs)
        onlyattrs = set(onlyattrs)
        onlytypes = set(onlytypes)

        utypes = set(
            t
            for t in onlytypes
            if t == "generic" or t not in pkg.actions.types
        )

        if utypes:
                usage(_("unknown action types: {0}".format(
                    apx.list_to_lang(list(utypes)))))

        manifest1 = manifest.Manifest()
        manifest2 = manifest.Manifest()
        try:
                # This assumes that both pargs are not '-'.
                for p, m in zip(pargs, (manifest1, manifest2)):
                        if p == "-":
                                m.set_content(content=sys.stdin.read())
                        else:
                                m.set_content(pathname=p)
        except (pkg.actions.ActionError, apx.InvalidPackageErrors) as e:
                error(_("Action error in file {p}: {e}").format(**locals()))
        except (EnvironmentError, apx.ApiException) as e:
                error(e)

        #
        # manifest filtering
        #

        # filter action type
        if onlytypes:
                for m in (manifest1, manifest2):
                        # Must pass complete list of actions to set_content, not
                        # a generator, to avoid clobbering manifest contents.
                        m.set_content(content=list(m.gen_actions_by_types(
                            onlytypes)))

        # filter variant
        v1 = manifest1.get_all_variants()
        v2 = manifest2.get_all_variants()
        for vname in varattrs:
                for _path, v, m in zip(pargs, (v1, v2), (manifest1, manifest2)):
                        if vname not in v:
                                continue
                        filt = varattrs[vname]
                        if filt not in v[vname]:
                                usage(_("Manifest {path} doesn't support "
                                    "variant {vname}={filt}".format(**locals())))
                        # remove the variant tag
                        def rip(a):
                                a.attrs.pop(vname, None)
                                return a
                        m.set_content([
                            rip(a)
                            for a in m.gen_actions(excludes=[
                            variant.Variants({vname: filt}).allow_action])
                        ])
                        m[vname] = filt

        if varattrs:
                # need to rebuild these if we're filtering variants
                v1 = manifest1.get_all_variants()
                v2 = manifest2.get_all_variants()

        # we need to be a little clever about variants, since
        # we can have multiple actions w/ the same key attributes
        # in each manifest in that case.  First, make sure any variants
        # of the same name have the same values defined.
        for k in set(v1.keys()) & set(v2.keys()):
                if v1[k] != v2[k]:
                        error(_("Manifests support different variants "
                            "{v1} {v2}").format(v1=v1, v2=v2))

        # Now, get a list of all possible variant values, including None
        # across all variants and both manifests
        v_values = dict()

        for v in v1:
                v1[v].add(None)
                for a in v1[v]:
                        v_values.setdefault(v, set()).add((v, a))

        for v in v2:
                v2[v].add(None)
                for a in v2[v]:
                        v_values.setdefault(v, set()).add((v, a))

        diffs = []

        for tup in product(*v_values.values()):
                # build excludes closure to examine only actions exactly
                # matching current variant values... this is needed to
                # avoid confusing manifest difference code w/ multiple
                # actions w/ same key attribute values or getting dups
                # in output
                def allow(a, publisher=None):
                        for k, v in tup:
                                if v is not None:
                                        if k not in a.attrs or a.attrs[k] != v:
                                                return False
                                elif k in a.attrs:
                                        return False
                        return True

                a, c, r = manifest2.difference(manifest1, [allow], [allow])
                diffs += a
                diffs += c
                diffs += r

        # License action still causes spurious diffs... check again for now.
        real_diffs = [
            (a, b)
            for a, b in diffs
            if a is None or b is None or a.different(b)
        ]

        if not real_diffs:
                return 0

        # define some ordering functions so that output is easily readable
        # First, a human version of action comparison that works across
        # variants and action changes...
        def compare(a, b):
                if hasattr(a, "key_attr") and hasattr(b, "key_attr") and \
                    a.key_attr == b.key_attr:
                        res = cmp(a.attrs[a.key_attr], b.attrs[b.key_attr])
                        if res:
                                return res
                        # sort by variant
                        res = cmp(sorted(list(a.get_variant_template())),
                            sorted(list(b.get_variant_template())))
                        if res:
                                return res
                else:
                        res = cmp(a.ordinality, b.ordinality)
                        if res:
                                return res
                return cmp(str(a), str(b))

        # and something to pull the relevant action out of the old value, new
        # value tuples
        def tuple_key(a):
                if not a[0]:
                        return a[1]
                return a[0]

        # sort and....
        diffs = sorted(diffs, key=tuple_key, cmp=compare)

        # handle list attributes
        def attrval(attrs, k, elide_iter=tuple()):
                def q(s):
                        if " " in s or s == "":
                                return '"{0}"'.format(s)
                        else:
                                return s

                v = attrs[k]
                if isinstance(v, list) or isinstance(v, set):
                        out = " ".join([
                            "{0}={1}".format(k, q(lmt))
                            for lmt in sorted(v)
                            if lmt not in elide_iter
                        ])
                elif " " in v or v == "":
                        out = k + "=\"" + v + "\""
                else:
                        out = k + "=" + v
                return out

        # figure out when to print diffs
        def conditional_print(s, a):
                if onlyattrs:
                        if not set(a.attrs.keys()) & onlyattrs:
                                return False
                elif ignoreattrs:
                        if not set(a.attrs.keys()) - ignoreattrs:
                                return False

                print("{0} {1}".format(s, a))
                return True

        different = False

        for old, new in diffs:
                if not new:
                        different |= conditional_print("-", old)
                elif not old:
                        different |= conditional_print("+", new)
                else:
                        s = []

                        if not onlyattrs:
                                if (hasattr(old, "hash") and
                                    "hash" not in ignoreattrs):
                                        if old.hash != new.hash:
                                                s.append("  - {0}".format(old.hash))
                                                s.append("  + {0}".format(new.hash))
                                attrdiffs = (set(new.differences(old)) -
                                    ignoreattrs)
                                attrsames = sorted( list(set(list(old.attrs.keys()) +
                                    list(new.attrs.keys())) -
                                    set(new.differences(old))))
                        else:
                                if hasattr(old, "hash") and "hash" in onlyattrs:
                                        if old.hash != new.hash:
                                                s.append("  - {0}".format(old.hash))
                                                s.append("  + {0}".format(new.hash))
                                attrdiffs = (set(new.differences(old)) &
                                    onlyattrs)
                                attrsames = sorted(list(set(list(old.attrs.keys()) +
                                    list(new.attrs.keys())) -
                                    set(new.differences(old))))

                        for a in sorted(attrdiffs):
                                if a in old.attrs and a in new.attrs and \
                                    isinstance(old.attrs[a], list) and \
                                    isinstance(new.attrs[a], list):
                                        elide_set = (set(old.attrs[a]) &
                                            set(new.attrs[a]))
                                else:
                                        elide_set = set()
                                if a in old.attrs:
                                        diff_str = attrval(old.attrs, a,
                                            elide_iter=elide_set)
                                        if diff_str:
                                                s.append("  - {0}".format(diff_str))
                                if a in new.attrs:
                                        diff_str = attrval(new.attrs, a,
                                            elide_iter=elide_set)
                                        if diff_str:
                                                s.append("  + {0}".format(diff_str))
                        # print out part of action that is the same
                        if s:
                                different = True
                                print("{0} {1} {2}".format(old.name,
                                    attrval(old.attrs, old.key_attr),
                                    " ".join(("{0}".format(attrval(old.attrs,v))
                                    for v in attrsames if v != old.key_attr))))

                                for l in s:
                                        print(l)

        return int(different)

if __name__ == "__main__":
        try:
                exit_code = main_func()
        except (PipeError, KeyboardInterrupt):
                exit_code = 1
        except SystemExit as __e:
                exit_code = __e
        except Exception as __e:
                traceback.print_exc()
                error(misc.get_traceback_message(), exitcode=None)
                exit_code = 99

        sys.exit(exit_code)
