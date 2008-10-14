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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import pkg.actions as action

import os
import sys

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestActions(pkg5unittest.Pkg5TestCase):

        def assertAttributeValue(self, action, attr, value):
                attrs = action.attrs[attr]

                if isinstance(attrs, list):
                        attrs.sort()
                if isinstance(value, list):
                        value.sort()

                if attrs != value:
                        self.fail("""\
Incorrect attribute value.
    Expected: %s
    Actual:   %s""" % (value, attrs))

        def assertAttributes(self, action, attrlist):
                if sorted(action.attrs.keys()) != sorted(attrlist):
                        self.fail("""\
Incorrect attribute list.
    Expected: %s
    Actual:   %s""" % (sorted(attrlist), sorted(action.attrs.keys())))

        def test_action_parser(self):
                action.fromstr("file 12345 name=foo")
                action.fromstr("file 12345 name=foo attr=bar")
                action.fromstr("file 12345 name=foo attr=bar attr=bar")

                action.fromstr("file 12345 name=foo     attr=bar")
                action.fromstr("file 12345 name=foo     attr=bar   ")
                action.fromstr("file 12345 name=foo     attr=bar   ")

                action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\"")
                action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\"")

                action.fromstr("file 12345 name=foo  value=barbaz")
                action.fromstr("file 12345 name=foo  value=\"bar baz\"")
                action.fromstr("file 12345 name=\"foo bar\"  value=baz")

                action.fromstr("file 12345 name=foo  value=barbazquux")
                action.fromstr("file 12345 name=foo  value=\"bar baz quux\"")
                action.fromstr("file 12345 name=\"foo bar baz\"  value=quux")

                action.fromstr("file 12345 name=\"foo\"  value=\"bar\"")
                action.fromstr("file 12345 name=foo  value=\"bar\"")
                action.fromstr("file 12345 name=\"foo\"  value=bar")

                # Single quoted value
                a = action.fromstr("file 12345 name='foo' value=bar")
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "foo")
                self.assertAttributeValue(a, "value", "bar")

                # Make sure that unescaped double quotes are parsed properly
                # inside a single-quoted value.
                a = action.fromstr("file 12345 name='f\"o\"o' value=bar ")
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "f\"o\"o")
                self.assertAttributeValue(a, "value", "bar")

                # Make sure that escaped single quotes are parsed properly
                # inside a single-quoted value.
                a = action.fromstr("file 12345 name='f\\'o\\'o' value=bar")
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "f'o'o")
                self.assertAttributeValue(a, "value", "bar")

                # You should be able to separate key/value pairs with tabs as
                # well as spaces.
                a = action.fromstr("file 12345 name=foo\tvalue=bar")
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "foo")
                self.assertAttributeValue(a, "value", "bar")

                # Unescaped, unpaired quotes are allowed in the middle of values
                # without further quoting
                a = action.fromstr("file 12345 name=foo\"bar")
                self.assertAttributes(a, ["name"])
                self.assertAttributeValue(a, "name", "foo\"bar")

                # They can even be paired.  Note this is not like shell quoting.
                a = action.fromstr("file 12345 name=foo\"bar\"baz")
                self.assertAttributes(a, ["name"])
                self.assertAttributeValue(a, "name", "foo\"bar\"baz")

                # An unquoted value can end in an escaped backslash
                a = action.fromstr("file 12345 name=foo\\")
                self.assertAttributes(a, ["name"])
                self.assertAttributeValue(a, "name", "foo\\")

                # An action with multiple identical attribute names should
                # result in an attribute with a list value.
                a = action.fromstr("driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega")
                self.assertAttributes(a, ["alias", "class", "name"])
                self.assertAttributeValue(a, "alias", ["pci1234,56", "pci4567,89"])

        def test_action_tostr(self):
                str(action.fromstr("file 12345 name=foo"))
                str(action.fromstr("file 12345 name=foo attr=bar"))
                str(action.fromstr("file 12345 name=foo attr=bar attr=bar"))

                str(action.fromstr("file 12345 name=foo     attr=bar"))
                str(action.fromstr("file 12345 name=foo     attr=bar   "))
                str(action.fromstr("file 12345 name=foo     attr=bar   "))

                str(action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\""))
                str(action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\""))

                str(action.fromstr("file 12345 name=foo  value=barbaz"))
                str(action.fromstr("file 12345 name=foo  value=\"bar baz\""))
                str(action.fromstr("file 12345 name=\"foo bar\"  value=baz"))

                str(action.fromstr("file 12345 name=foo  value=barbazquux"))
                str(action.fromstr("file 12345 name=foo  value=\"bar baz quux\""))
                str(action.fromstr("file 12345 name=\"foo bar baz\"  value=quux"))

                str(action.fromstr("file 12345 name=\"foo\"  value=\"bar\""))
                str(action.fromstr("file 12345 name=foo  value=\"bar\""))
                str(action.fromstr("file 12345 name=\"foo\"  value=bar"))

                str(action.fromstr("file 12345 name='foo' value=bar"))
                str(action.fromstr("file 12345 name='f\"o\"o' value=bar"))
                str(action.fromstr("file 12345 name='f\\'o\\'o' value=bar"))

                str(action.fromstr("file 12345 name=foo\tvalue=bar"))

                str(action.fromstr("driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega"))

        def assertMalformed(self, text):
                malformed = False

                try:
                        action.fromstr(text)
                except action.MalformedActionError:
                        malformed = True

                self.assert_(malformed, "Action not malformed: " + text)

        def test_action_errors(self):
                # Unknown action type
                self.assertRaises(action.UnknownActionError, action.fromstr,
                    "moop bar=baz")

                # Nothing but the action type
                self.assertMalformed("moop")

                # Bad quoting: missing close quote
                self.assertMalformed("file 12345 name=\"foo bar")
                self.assertMalformed("file 12345 name=\"foo bar\\")
                # Bad quoting: quote in key
                self.assertMalformed("file 12345 \"name=foo bar")
                self.assertMalformed("file 12345 na\"me=foo bar")
                self.assertMalformed("file 1234 \"foo\"=bar")

                # Missing key
                self.assertMalformed("file 1234 =\"\"")
                self.assertMalformed("file =")
                self.assertMalformed("file 1234 =")
                self.assertMalformed("file 1234 ==")
                self.assertMalformed("file 1234 ===")

                # Missing value
                self.assertMalformed("file 1234 broken=")
                self.assertMalformed("file 1234 broken= ")

                # Whitespace in key
                self.assertMalformed("file 1234 bro ken")

                self.assertMalformed("file 1234 broken")


if __name__ == "__main__":
        unittest.main()
