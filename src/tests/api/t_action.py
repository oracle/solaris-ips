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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import pkg.actions as action

import os
import sys

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
                action.fromstr("file 12345 name=foo path=/tmp/foo")
                action.fromstr("file 12345 name=foo attr=bar path=/tmp/foo")
                action.fromstr("file 12345 name=foo attr=bar attr=bar path=/tmp/foo")

                action.fromstr("file 12345 name=foo     path=/tmp/foo attr=bar")
                action.fromstr("file 12345 name=foo     path=/tmp/foo attr=bar   ")
                action.fromstr("file 12345 name=foo     path=/tmp/foo attr=bar   ")

                action.fromstr("file 12345 name=\"foo bar\"  path=\"/tmp/foo\" attr=\"bar baz\"")
                action.fromstr("file 12345 name=\"foo bar\"  path=\"/tmp/foo\" attr=\"bar baz\"")

                action.fromstr("file 12345 name=foo  value=barbaz path=/tmp/foo")
                action.fromstr("file 12345 name=foo  value=\"bar baz\" path=/tmp/foo")
                action.fromstr("file 12345 name=\"foo bar\"  value=baz path=/tmp/foo")

                action.fromstr("file 12345 name=foo  value=barbazquux path=/tmp/foo")
                action.fromstr("file 12345 name=foo  value=\"bar baz quux\" path=/tmp/foo")
                action.fromstr("file 12345 name=\"foo bar baz\"  value=quux path=/tmp/foo")

                action.fromstr("file 12345 name=\"foo\"  value=\"bar\" path=/tmp/foo")
                action.fromstr("file 12345 name=foo  value=\"bar\" path=/tmp/foo")
                action.fromstr("file 12345 name=\"foo\"  value=bar path=/tmp/foo")

                action.fromstr("signature 12345 name=foo  value=bar")

                # Single quoted value
                a = action.fromstr("file 12345 name='foo' value=bar path=/tmp/foo")
                self.assertAttributes(a, ["name", "value", "path"])
                self.assertAttributeValue(a, "name", "foo")
                self.assertAttributeValue(a, "value", "bar")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # Make sure that unescaped double quotes are parsed properly
                # inside a single-quoted value.
                a = action.fromstr("file 12345 name='f\"o\"o' value=bar path=/tmp/foo")
                self.assertAttributes(a, ["name", "path", "value"])
                self.assertAttributeValue(a, "name", "f\"o\"o")
                self.assertAttributeValue(a, "value", "bar")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # Make sure that escaped single quotes are parsed properly
                # inside a single-quoted value.
                a = action.fromstr("file 12345 name='f\\'o\\'o' value=bar path=/tmp/foo")
                self.assertAttributes(a, ["name", "path", "value"])
                self.assertAttributeValue(a, "name", "f'o'o")
                self.assertAttributeValue(a, "value", "bar")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # You should be able to separate key/value pairs with tabs as
                # well as spaces.
                a = action.fromstr("file 12345 name=foo\tvalue=bar path=/tmp/foo")
                self.assertAttributes(a, ["name", "path", "value"])
                self.assertAttributeValue(a, "name", "foo")
                self.assertAttributeValue(a, "value", "bar")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # Unescaped, unpaired quotes are allowed in the middle of values
                # without further quoting
                a = action.fromstr("file 12345 name=foo\"bar path=/tmp/foo")
                self.assertAttributes(a, ["name", "path"])
                self.assertAttributeValue(a, "name", "foo\"bar")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # They can even be paired.  Note this is not like shell quoting.
                a = action.fromstr("file 12345 name=foo\"bar\"baz path=/tmp/foo")
                self.assertAttributes(a, ["name", "path"])
                self.assertAttributeValue(a, "name", "foo\"bar\"baz")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # An unquoted value can end in an escaped backslash
                a = action.fromstr("file 12345 name=foo\\ path=/tmp/foo")
                self.assertAttributes(a, ["name", "path"])
                self.assertAttributeValue(a, "name", "foo\\")
                self.assertAttributeValue(a, "path", "tmp/foo")

                # An action with multiple identical attribute names should
                # result in an attribute with a list value.
                a = action.fromstr("driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega")
                self.assertAttributes(a, ["alias", "class", "name"])
                self.assertAttributeValue(a, "alias", ["pci1234,56", "pci4567,89"])

                # An action with an empty value.
                a = action.fromstr('set name=foo value=""')
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "foo")
                self.assertAttributeValue(a, "value", "")

                # An action with an empty value as part of a list.
                a = action.fromstr('set name=foo value=ab value="" value=c')
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "foo")
                self.assertAttributeValue(a, "value", ["ab", "c", ""])

                # An action with its key attribute and extra attributes that
                # are not used by the package system.
                a = action.fromstr('license license="Common Development and '
                    'Distribution License 1.0 (CDDL)" custom="foo" '
                    'bool_val=true')
                self.assertAttributes(a, ["license", "custom", "bool_val"])
                self.assertAttributeValue(a, "license", 'Common Development '
                    'and Distribution License 1.0 (CDDL)')
                self.assertAttributeValue(a, "custom", "foo")
                self.assertAttributeValue(a, "bool_val", "true")

        def test_action_license(self):
                """Test license action attributes."""

                # Verify license attributes for must-accept / must-display
                # contain expected values.
                a = action.fromstr('license license="Common Development and '
                    'Distribution License 1.0 (CDDL)" custom="foo" '
                    'bool_val=true')
                self.assertEqual(a.must_accept, False)
                self.assertEqual(a.must_display, False)

                a = action.fromstr('license license="Common Development and '
                    'Distribution License 1.0 (CDDL)" must-accept=true '
                    'must-display=False')
                self.assertEqual(a.must_accept, True)
                self.assertEqual(a.must_display, False)

                a = action.fromstr('license license="Common Development and '
                    'Distribution License 1.0 (CDDL)" must-accept=True '
                    'must-display=true')
                self.assertEqual(a.must_accept, True)
                self.assertEqual(a.must_display, True)

                a = action.fromstr('license license="Common Development and '
                    'Distribution License 1.0 (CDDL)" must-accept=True ')
                self.assertEqual(a.must_accept, True)
                self.assertEqual(a.must_display, False)

        def test_action_tostr(self):
                str(action.fromstr("file 12345 name=foo path=/tmp/foo"))
                str(action.fromstr("file 12345 name=foo attr=bar path=/tmp/foo"))
                str(action.fromstr("file 12345 name=foo attr=bar attr=bar path=/tmp/foo"))

                str(action.fromstr("file 12345 name=foo     attr=bar path=/tmp/foo"))
                str(action.fromstr("file 12345 name=foo     path=/tmp/foo attr=bar   "))
                str(action.fromstr("file 12345 name=foo     path=/tmp/foo attr=bar   "))

                str(action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\" path=/tmp/foo"))
                str(action.fromstr("file 12345 name=\"foo bar\"  attr=\"bar baz\" path=/tmp/foo"))

                str(action.fromstr("file 12345 name=foo  value=barbaz path=/tmp/foo"))
                str(action.fromstr("file 12345 name=foo  value=\"bar baz\" path=/tmp/foo"))
                str(action.fromstr("file 12345 name=\"foo bar\"  value=baz path=/tmp/foo"))

                str(action.fromstr("file 12345 name=foo  value=barbazquux path=/tmp/foo"))
                str(action.fromstr("file 12345 name=foo  value=\"bar baz quux\" path=/tmp/foo"))
                str(action.fromstr("file 12345 name=\"foo bar baz\"  value=quux path=/tmp/foo"))

                str(action.fromstr("file 12345 name=\"foo\"  value=\"bar\" path=/tmp/foo"))
                str(action.fromstr("file 12345 name=foo  value=\"bar\" path=/tmp/foo"))
                str(action.fromstr("file 12345 name=\"foo\"  value=bar path=/tmp/foo"))

                str(action.fromstr("file 12345 name='foo' value=bar path=/tmp/foo"))
                str(action.fromstr("file 12345 name='f\"o\"o' value=bar path=/tmp/foo"))
                str(action.fromstr("file 12345 name='f\\'o\\'o' value=bar path=/tmp/foo"))

                str(action.fromstr("file 12345 name=foo\tvalue=bar path=/tmp/foo"))

                str(action.fromstr("driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega"))

                str(action.fromstr("signature foo=v bar=y"))

                a = 'set name=foo value=""'
                self.assertEqual(str(action.fromstr(a)), a)

                a = 'set name=foo value=ab value="" value=c'
                self.assertEqual(str(action.fromstr(a)), a)

        def assertMalformed(self, text):
                malformed = False

                try:
                        action.fromstr(text)
                except action.MalformedActionError:
                        malformed = True

                # If the action isn't malformed, something is wrong.
                self.assert_(malformed, "Action not malformed: " + text)

        def assertInvalid(self, text):
                invalid = False

                try:
                        action.fromstr(text)
                except action.InvalidActionError:
                        invalid = True

                # If the action isn't invalid, something is wrong.
                self.assert_(invalid, "Action not invalid: " + text)

        def test_action_errors(self):
                # Unknown action type
                self.assertRaises(action.UnknownActionError, action.fromstr,
                    "moop bar=baz")

                # Nothing but the action type
                self.assertMalformed("moop")

                # Bad quoting: missing close quote
                self.assertMalformed("file 12345 path=/tmp/foo name=\"foo bar")
                self.assertMalformed("file 12345 path=/tmp/foo name=\"foo bar\\")

                # Bad quoting: quote in key
                self.assertMalformed("file 12345 path=/tmp/foo \"name=foo bar")
                self.assertMalformed("file 12345 path=/tmp/foo na\"me=foo bar")
                self.assertMalformed("file 1234 path=/tmp/foo \"foo\"=bar")

                # Missing key
                self.assertMalformed("file 1234 path=/tmp/foo =\"\"")
                self.assertMalformed("file path=/tmp/foo =")
                self.assertMalformed("file 1234 path=/tmp/foo =")
                self.assertMalformed("file 1234 path=/tmp/foo ==")
                self.assertMalformed("file 1234 path=/tmp/foo ===")

                # Missing value
                self.assertMalformed("file 1234 path=/tmp/foo broken=")
                self.assertMalformed("file 1234 path=/tmp/foo broken= ")
                self.assertMalformed("file 1234 path=/tmp/foo broken")

                # Whitespace in key
                self.assertMalformed("file 1234 path=/tmp/foo bro ken")

                # Attribute value is invalid.
                self.assertInvalid("depend type=unknown fmri=foo@1.0")

                # Missing required attribute 'type'.
                self.assertInvalid("depend fmri=foo@1.0")

                # Missing key attribute 'fmri'.
                self.assertInvalid("depend type=require")

                # 'data' used as an attribute key
                self.assertInvalid("file 1234 path=/tmp/foo data=rubbish")

                # Missing required attribute 'path'.
                self.assertRaises(action.InvalidActionError, action.fromstr,
                    "file 1234 owner=foo")

                # Missing required attribute 'name'.
                self.assertRaises(action.InvalidActionError, action.fromstr,
                    "driver alias=pci1234,56 alias=pci4567,89 class=scsi")

        def test_validate(self):
                """Verify that action validate() works as expected; currently
                only used during publication or action execution failure."""

                fact = "file 12345 name=foo path=/tmp/foo mode=XXX"
                dact = "dir path=/tmp mode=XXX"

                # Invalid attribute for file and directory actions.
                for act in (fact, dact):
                        for bad_mode in ("", 'mode=""', "mode=???", 
                            "mode=44755", "mode=44", "mode=999", "mode=0898"):
                                nact = act.replace("mode=XXX", bad_mode)
                                bad_act = action.fromstr(nact)
                                self.assertRaises(
                                    action.InvalidActionAttributesError,
                                    bad_act.validate)


if __name__ == "__main__":
        unittest.main()
