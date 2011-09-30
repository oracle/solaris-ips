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

#
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

import getopt
import gettext
import sys
import traceback

import pkg.actions
import pkg.variant as variant
import pkg.client.api_errors as apx
import pkg.manifest as manifest
import pkg.misc as misc
from pkg.misc import PipeError
from collections import defaultdict

def usage(errmsg="", exitcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                print >> sys.stderr, "pkgdiff: %s" % errmsg

        print _("""\
Usage:
        pkgdiff [-i attribute ...] [-o attribute] [-v variant=value ...]
            file1 file2""")
        sys.exit(exitcode)

def error(text, exitcode=1):
        """Emit an error message prefixed by the command name """

        print >> sys.stderr, "pkgdiff: %s" % text

        if exitcode != None:
                sys.exit(exitcode)

def main_func():
        gettext.install("pkg", "/usr/share/locale")

        ignoreattrs = []
        onlyattrs = []
        varattrs = defaultdict(set)

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "i:o:v:", ["help"])
                for opt, arg in opts:
                        if opt == "-i":
                                ignoreattrs.append(arg)
                        if opt == "-o":
                                onlyattrs.append(arg)
                        if opt == "-v":
                                args = arg.split("=")
                                if len(args) != 2:
                                        usage(_("variant option incorrect %s") % arg)
                                if not args[0].startswith("variant."):
                                        args[0] = "variant." + args[0]
                                varattrs[args[0]].add(args[1])
                        if opt in ("--help", "-?"):
                                usage(exitcode=0)

        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        if len(pargs) != 2:
                usage(_("two file arguments are required."))

        if ignoreattrs and onlyattrs:
                usage(_("-i and -o options may not be used at the same time."))

        for v in varattrs:
                if len(varattrs[v]) > 1:
                        usage(_("For any variant, only one value may be specified."))
                varattrs[v] = varattrs[v].pop()

        ignoreattrs = set(ignoreattrs)
        onlyattrs = set(onlyattrs)

        manifest1 = manifest.Manifest()
        manifest2 = manifest.Manifest()
        try:
                for p, m in zip(pargs, (manifest1, manifest2)):
                        m.set_content(pathname=p)
        except (pkg.actions.ActionError, apx.InvalidPackageErrors), e:
                error(_("Action error in file %(p)s: %(e)s") % locals())
        except (EnvironmentError, apx.ApiException), e:
                error(e)

        v1 = manifest1.get_all_variants()
        v2 = manifest2.get_all_variants()

        # implement manifest filtering
        for vname in varattrs:
                for path, v, m in zip(pargs, (v1, v2), (manifest1, manifest2)):
                        if vname not in v:
                                continue
                        filt = varattrs[vname]
                        if filt not in v[vname]:
                                usage(_("Manifest %(path)s doesn't support variant %(vname)s=%(filt)s" %
                                    locals()))
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
                        error(_("Manifests support different variants %s %s") % (v1, v2))

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
                def allow(a):
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
            (a,b)
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
                        res = cmp(sorted(list(a.get_variant_template())), sorted(list(b.get_variant_template())))
                        if res:
                                return res
                else:
                        res = cmp(a.ord, b.ord)
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
                                return '"%s"' % s
                        else:
                                return s

                v = attrs[k]
                if isinstance(v, list) or isinstance(v, set):
                        out = " ".join(["%s=%s" %
                            (k, q(lmt)) for lmt in sorted(v) if lmt not in elide_iter])
                elif " " in v or v == "":
                        out = k + "=\"" + v + "\""
                else:
                        out = k + "=" + v
                return out

        #figure out when to print diffs
        def conditional_print(s, a):
                if onlyattrs:
                        if not set(a.attrs.keys()) & onlyattrs:
                                return False
                elif ignoreattrs:
                        if not set(a.attrs.keys()) - ignoreattrs:
                                return False
                print "%s %s" % (s, a)
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
                                if hasattr(old, "hash") and "hash" not in ignoreattrs:
                                        if old.hash != new.hash:
                                                s.append("  - %s" % new.hash)
                                                s.append("  + %s" % old.hash)
                                attrdiffs = set(new.differences(old)) - ignoreattrs
                                attrsames = sorted(list(set(old.attrs.keys() + new.attrs.keys()) -
                                    set(new.differences(old))))
                        else:
                                if hasattr(old, "hash") and "hash"  in onlyattrs:
                                        if old.hash != new.hash:
                                                s.append("  - %s" % new.hash)
                                                s.append("  + %s" % old.hash)
                                attrdiffs = set(new.differences(old)) & onlyattrs
                                attrsames = sorted(list(set(old.attrs.keys() + new.attrs.keys()) -
                                    set(new.differences(old))))

                        for a in sorted(attrdiffs):
                                if a in old.attrs and a in new.attrs and \
                                    isinstance(old.attrs[a], list) and \
                                    isinstance(new.attrs[a], list):
                                        elide_set = set(old.attrs[a]) & set(new.attrs[a])
                                else:
                                        elide_set = set()
                                if a in old.attrs:
                                        diff_str = attrval(old.attrs, a, elide_iter=elide_set)
                                        if diff_str:
                                                s.append("  - %s" % diff_str)
                                if a in new.attrs:
                                        diff_str = attrval(new.attrs, a, elide_iter=elide_set)
                                        if diff_str:
                                                s.append("  + %s" % diff_str)
                        # print out part of action that is the same
                        if s:
                                different = True
                                print "%s %s %s" % (old.name,
                                    attrval(old.attrs, old.key_attr),
                                    " ".join(("%s" % attrval(old.attrs,v)
                                    for v in attrsames if v != old.key_attr)))
                                for l in s:
                                        print l

        return int(different)

def product(*args, **kwds):
        # product('ABCD', 'xy') --> Ax Ay Bx By Cx Cy Dx Dy
        # product(range(2), repeat=3) --> 000 001 010 011 100 101 110 111
        # from python 2.6 itertools
        pools = map(tuple, args) * kwds.get('repeat', 1)
        result = [[]]
        for pool in pools:
                result = [x+[y] for x in result for y in pool]
        for prod in result:
                yield tuple(prod)

if __name__ == "__main__":
        try:
                exit_code = main_func()
        except (PipeError, KeyboardInterrupt):
                exit_code = 1
        except SystemExit, __e:
                exit_code = __e
        except Exception, __e:
                traceback.print_exc()
                error(misc.get_traceback_message(), exitcode=None)
                exit_code = 99

        sys.exit(exit_code)
