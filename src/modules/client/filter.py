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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

from cStringIO import StringIO
import tokenize
import token
from pkg.misc import msg

def compile_filter(filter):
        def f_get(tup):
                if tup[0] == token.NAME:
                        return "NAME", tup[0], tup[1]
                elif tup[0] == token.NUMBER:
                        return "NUMBER", tup[0], tup[1]
                else:
                        return tup[1], tup[0], tup[1]
        tok_stream = [
            f_get(i)
            for i in tokenize.generate_tokens(StringIO(filter).readline)
        ]

        f_str = ""
        expr = ""
        want_attr = True
        next_tok = ("(", "NAME", "NUMBER")
        for tok_str, tok_type, tok in tok_stream:
                if tok_str not in next_tok:
                        raise RuntimeError, \
                            "'%s' is not an allowable token. Expected one of" \
                                " the following %s after: %s" % \
                            (tok_str, next_tok, f_str)

                if tok_type == token.NAME or tok_type == token.NUMBER:
                        # If the parser has found either of these token types
                        # just append them and look for the next token.
                        expr += tok
                        if want_attr:
                                next_tok = ("NAME", "NUMBER", ".", "=")
                        else:
                                next_tok = ("NAME", "NUMBER", ".", "&", "|",
                                        ")", "")
                        continue
                elif tok_type == token.ENDMARKER:
                        if not expr == "":
                                # The parser has encountered the end of the
                                # filter string (encountered a newline). Thus,
                                # the expression portion of the filter can be
                                # generated if we have something to add.
                                f_str += "'%s') == '%s'" % (expr, expr)
                        else:
                                # End of line, but nothing to add.
                                continue
                elif tok_type == token.OP:
                        if tok == "=":
                                # The assignment operator acts as the
                                # terminator for parsing attributes.
                                f_str += "d.get('%s', " % (expr)

                                # Now setup the parser to look for a value. It
                                # can only be composed of text and/or numeric
                                # tokens. Then look for the next token.
                                expr = ""
                                want_attr = False
                                next_tok = ("NAME", "NUMBER")
                                continue
                        elif tok == "(":
                                # If the parser finds this token, it just needs
                                # to be appended, and the next token found.
                                expr = ""
                                f_str += "("
                                next_tok = ("(", "NAME", "NUMBER")
                                continue
                        elif tok == ".":
                                # If the parser finds this token, the value just
                                # needs to be appended and the next token found.
                                expr += "."
                                next_tok = ("NAME", "NUMBER")
                                continue

                        if not expr == "":
                                # The remaining tokens to be parsed act as
                                # terminating operators. As a result, the
                                # expression portion of the filter needs to be
                                # generated first before continuing if we have
                                # something to add.
                                f_str += "'%s') == '%s'" % (expr, expr)

                        # Now append any conditions to the filter or terminate
                        # this portion of it.
                        if tok == "&":
                                f_str += " and "
                                next_tok = ("NAME", "NUMBER", "(")
                                want_attr = True
                        elif tok == "|":
                                f_str += " or "
                                next_tok = ("NAME", "NUMBER", "(")
                                want_attr = True
                        elif tok == ")":
                                f_str += ")"
                                next_tok = ("&", "|", ")", "")
                                want_attr = False

                        # Finally, prepare for the next cycle.
                        expr = ""

        return f_str, compile(f_str, "<filter string>", "eval")

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
        for f_entry, code in filters:
                if not eval(code, {"d": action.attrs}):
                        return False
        return True
