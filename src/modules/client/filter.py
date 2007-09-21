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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

from StringIO import StringIO
import tokenize
import token

def compile_filter(filter):
        def q(tup):
                if tup[0] == token.NAME:
                        return "NAME", tup[0], tup[1]
                else:
                        return tup[1], tup[0], tup[1]
        tok_stream = [
            q(i)
            for i in tokenize.generate_tokens(StringIO(filter).readline)
        ]

        s = ""
        attr = ""
        want_attr = True
        next_tok = ("(", "NAME")
        for tok_str, tok_type, tok in tok_stream:
                # print "%02s %-15s: %s" % (tok_type, tok, s)

                if tok_str not in next_tok:
                        raise RuntimeError, \
                            "'%s' is not an allowable token %s" % \
                            (tok_str, next_tok)

                if tok_type == token.NAME:
                        if want_attr:
                                attr += tok
                                next_tok = (".", "=")
                        else:
                                s += "'%s') == '%s'" % (tok, tok)
                                next_tok = ("&", "|", ")", "")
                                want_attr = True
                elif tok_type == token.OP:
                        if tok == "=":
                                s += "d.get('%s', " % attr
                                next_tok = ("NAME",)
                                want_attr = False
                                attr = ""
                        elif tok == "&":
                                s += " and "
                                next_tok = ("NAME", "(")
                        elif tok == "|":
                                s += " or "
                                next_tok = ("NAME", "(")
                        elif tok == "(":
                                s += "("
                                next_tok = ("NAME", "(")
                        elif tok == ")":
                                s += ")"
                                next_tok = ("&", "|", ")", "")
                        elif tok == ".":
                                if want_attr:
                                        attr += "."
                                next_tok = ("NAME",)

        return s, compile(s, "<filter string>", "eval")

def apply_filters(action, filters):
        """Apply the filter chain to the action, returning the True if it's
        not filtered out, or False if it is.
        
        Filters operate on action attributes.  A simple filter will eliminate
        an action if the action has the attribute in the filter, but the value
        is different.  Simple filters can be chained together with AND and OR
        logical operators.  In addition, multiple filters may be applied; they
        are effectively ANDed together.
        """

        if not action:
                return False

        # Evaluate each filter in turn.  If a filter eliminates the action, we
        # need check no further.  If no filters eliminate the action, return
        # True.
        for filter, code in filters:
                if not eval(code, {"d": action.attrs}):
                        return False
        return True

if __name__ == "__main__":
        import sys
        import pkg.actions

        actionstr = """\
        file path=/usr/bin/ls arch=i386 debug=true
        file path=/usr/bin/ls arch=i386 debug=false
        file path=/usr/bin/ls arch=sparc debug=true
        file path=/usr/bin/ls arch=sparc debug=false
        file path=/var/svc/manifest/intrd.xml opensolaris.zone=global
        file path=/path/to/french/text doc=true locale=fr
        file path=/path/to/swedish/text doc=true locale=sv
        file path=/path/to/english/text doc=true locale=en
        file path=/path/to/us-english/text doc=true locale=en_US"""

        actions = [
            pkg.actions.fromstr(s.strip())
            for s in actionstr.splitlines()
        ]

        if len(sys.argv) > 1:
                arg = sys.argv[1:]
        else:
                arg = [ "arch=i386 & debug=true" ]

        filters = []
        for filter in arg:
                expr, comp_expr = compile_filter(filter)
                print expr
                filters.append((expr, comp_expr))

        for a in actions:
                d = a.attrs
                print "%-5s" % apply_filters(a, filters), d
