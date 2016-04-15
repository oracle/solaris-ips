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

#
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import six
import unittest
import pkg.actions as action
import pkg.actions.generic as generic
import pkg.actions.signature as signature
import pkg.client.api_errors as api_errors

import os
import sys

class TestActions(pkg5unittest.Pkg5TestCase):


        act_strings = [
            "set name=foo value=foo",
            "set name=foo value=\"\"",
            "set name=foo value=f'o'o",
            "set name=foo value='f\"o \"o'",
            "set name=foo value='b\"a \"r' value='f\"o \"o'",
            "set name=foo value=\"f'o 'o\"",
            "set name=foo value=\"b'a 'r\" value=\"f'o 'o\"",
            "set name=foo value='f\"o \\' \"o'",
            "set name=foo value='b\"a \\' \"r' value='f\"o \\' \"o'",
            "set name=foo value='\"foo\"'",
            "set name=foo value='\"bar\"'value='\"foo\"'",
            "set name=foo value=\"'foo'\"",
            "set name=foo value=\"'bar'\" value=\"'foo'\"",
            "set name=foo value='\"fo\\\'o\"'",
            "set name=foo value='\"ba\\\'r\"' value='\"fo\\\'o\"'",
            "set name=foo value=\"'fo\\\"o'\"",
            "set name=foo value=\"'ba\\\"r'\" value=\"'fo\\\"o'\"",
            'set name=foo value=ab value="" value=c',
            "file 12345 name=foo path=/tmp/foo",
            "file 12345 name=foo attr=bar path=/tmp/foo",
            "file 12345 name=foo attr=bar attr=bar path=/tmp/foo",
            "file 12345 name=foo     attr=bar path=/tmp/foo",
            "file 12345 name=foo     path=/tmp/foo attr=bar   ",
            "file 12345 name=foo     path=/tmp/foo attr=bar   ",
            "file 12345 name=\"foo bar\"  attr=\"bar baz\" path=/tmp/foo",
            "file 12345 name=\"foo bar\"  attr=\"bar baz\" path=/tmp/foo",
            "file 12345 name=foo  value=barbaz path=/tmp/foo",
            "file 12345 name=foo  value=\"bar baz\" path=/tmp/foo",
            "file 12345 name=\"foo bar\"  value=baz path=/tmp/foo",
            "file 12345 name=foo  value=barbazquux path=/tmp/foo",
            "file 12345 name=foo  value=\"bar baz quux\" path=/tmp/foo",
            "file 12345 name=\"foo bar baz\"  value=quux path=/tmp/foo",
            "file 12345 name=\"foo\"  value=\"bar\" path=/tmp/foo",
            "file 12345 name=foo  value=\"bar\" path=/tmp/foo",
            "file 12345 name=\"foo\"  value=bar path=/tmp/foo",
            "file 12345 name='foo' value=bar path=/tmp/foo",
            "file 12345 name='f\"o\"o' value=bar path=/tmp/foo",
            "file 12345 name='f\\'o\\'o' value=bar path=/tmp/foo",
            "file 12345 name=foo\tvalue=bar path=/tmp/foo",
            "driver alias=pci1234,56 alias=pci4567,89 class=scsi name=lsimega",
            "signature 12345 algorithm=foo",
        ]

        def assertAttributeValue(self, action, attr, value):
                attrs = action.attrs[attr]

                if isinstance(attrs, list):
                        attrs.sort()
                if isinstance(value, list):
                        value.sort()

                if attrs != value:
                        self.fail("""\
Incorrect attribute value.
    Expected: {0}
    Actual:   {1}""".format(value, attrs))

        def assertAttributes(self, action, attrlist):
                if sorted(action.attrs.keys()) != sorted(attrlist):
                        self.fail("""\
Incorrect attribute list.
    Expected: {0}
    Actual:   {1}""".format(sorted(attrlist), sorted(action.attrs.keys())))

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

                action.fromstr("signature 12345 algorithm=foo")

                # For convenience, we allow set actions to be expressed as
                # "<name>=<value>", rather than "name=<name> value=<value>", but
                # we always convert to the latter.  Verify that both forms are
                # parsed as expected.
                a = action.fromstr("set pkg.obsolete=true")
                a2 = action.fromstr("set name=pkg.obsolete value=true")
                self.assertEqual(str(a), str(a2))
                self.assertAttributes(a, ["name", "value"])
                self.assertAttributeValue(a, "name", "pkg.obsolete")
                self.assertAttributeValue(a, "value", "true")

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

                # Really long actions with lots of backslash-escaped quotes
                # should work.
                a = action.fromstr(r'set name=pkg.description value="Sphinx is a tool that makes it easy to create intelligent \"and beautiful documentation f\"or Python projects (or \"other documents consisting of\" multiple reStructuredText so\"urces), written by Georg Bran\"dl. It was originally created\" to translate the new Python \"documentation, but has now be\"en cleaned up in the hope tha\"t it will be useful to many o\"ther projects. Sphinx uses re\"StructuredText as its markup \"language, and many of its str\"engths come from the power an\"d straightforwardness of reSt\"ructuredText and its parsing \"and translating suite, the Do\"cutils. Although it is still \"under constant development, t\"he following features are alr\"eady present, work fine and c\"an be seen \"in action\" \"in the Python docs: * Output \"formats: HTML (including Wind\"ows HTML Help) and LaTeX, for\" printable PDF versions * Ext\"ensive cross-references: sema\"ntic markup and automatic lin\"ks for functions, classes, gl\"ossary terms and similar piec\"es of information * Hierarchi\"cal structure: easy definitio\"n of a document tree, with au\"tomatic links to siblings, pa\"rents and children * Automati\"c indices: general index as w\"ell as a module index * Code \"handling: automatic highlight\"ing using the Pygments highli\"ghter * Various extensions ar\"e available, e.g. for automat\"ic testing of snippets and in\"clusion of appropriately formatted docstrings."')
                self.assertTrue(a.attrs["value"].count('"') == 45)

                # Make sure that the hash member of the action object properly
                # contains the value of the "hash" named attribute.
                a = action.fromstr("file hash=abc123 path=usr/bin/foo mode=0755 owner=root group=bin")
                self.assertTrue(a.hash == "abc123")

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

        def __assert_action_str(self, astr, expected, expattrs):
                """Private helper function for action stringification
                testing."""
                act = action.fromstr(astr)
                self.assertEqualDiff(expected, str(act))
                self.assertEqualDiff(expattrs, act.attrs)

        def test_action_tostr(self):
                """Test that actions convert to strings properly.  This means
                that we can feed the resulting string back into fromstr() and
                get an identical action back (excluding a few cases detailed in
                the test)."""

                for s in self.act_strings:
                        self.debug(str(s))
                        a = action.fromstr(s)
                        s2 = str(a)
                        a2 = action.fromstr(s2)
                        if a.different(a2):
                                self.debug("a1 " + str(a))
                                self.debug("a2 " + str(a2))
                                self.assertTrue(not a.different(a2))

                # The first case that invariant doesn't hold is when you specify
                # the payload hash as the named attribute "hash", in which case
                # the resulting re-stringification emits the payload hash as a
                # positional attribute again ...
                s = "file hash=abc123 path=usr/bin/foo mode=0755 owner=root group=bin"
                self.debug(s)
                a = action.fromstr(s)
                s2 = str(a)
                self.assertTrue(s2.startswith("file abc123 "))
                self.assertTrue("hash=abc123" not in s2)
                a2 = action.fromstr(s2)
                self.assertTrue(not a.different(a2))

                # ... unless of course the hash can't be represented that way.
                d = {
                    "hash=abc=123": "abc=123",
                    "hash=\"one with spaces\"": "one with spaces",
                    "hash='one with \" character'": 'one with " character',
                    "hash=\"'= !@$%^\)(*\"": "'= !@$%^\)(*",
                    """hash="\\"'= \\ " """:""""'= \\ """,
                    '\\' : '\\'
                }

                astr = "file {0} path=usr/bin/foo mode=0755 owner=root group=bin"
                for k, v  in six.iteritems(d):
                        a = action.fromstr(astr.format(k))
                        self.assertTrue(action.fromstr(str(a)) == a)
                        self.assertTrue(a.hash == v)
                        self.assertTrue(k in str(a))

                # The attributes are verified separately from the stringified
                # action in the tests below to ensure that the attributes were
                # parsed independently and not as a single value (e.g.
                # 'file path=etc/foo\nfacet.debug=true' is parsed as having a
                # path attribute and a facet.debug attribute).

                # The next case that invariant doesn't hold is when you have
                # multiple, quoted values for a single attribute (this case
                # primarily exists for use with line-continuation support
                # offered by the Manifest class).
                expected = 'set name=pkg.description value="foo bar baz"'
                expattrs = { 'name': 'pkg.description', 'value': 'foo bar baz' }
                for astr in (
                    "set name=pkg.description value='foo ''bar ''baz'",
                    "set name=pkg.description value='foo ' 'bar ' 'baz'",
                    'set name=pkg.description value="foo " "bar " "baz"'):
                        self.__assert_action_str(astr, expected, expattrs)

                expected = "set name=pkg.description value='foo \"bar\" baz'"
                expattrs = { 'name': 'pkg.description',
                    'value': 'foo "bar" baz' }
                for astr in (
                    "set name=pkg.description value='foo \"bar\" ''baz'",
                    "set name=pkg.description value='foo \"bar\" '\"baz\""):
                        self.__assert_action_str(astr, expected, expattrs)

                # The next case that invariant doesn't hold is when there are
                # multiple whitespace characters between attributes or after the
                # action type.
                expected = 'set name=pkg.description value=foo'
                expattrs = { 'name': 'pkg.description', 'value': 'foo' }
                for astr in (
                    "set  name=pkg.description value=foo",
                    "set name=pkg.description  value=foo",
                    "set  name=pkg.description  value=foo",
                    "set\n name=pkg.description \nvalue=foo",
                    "set\t\nname=pkg.description\t\nvalue=foo"):
                        # To force stressing the parsing logic a bit more, we
                        # parse an action with a multi-value attribute that
                        # needs concatention each time before we parse a
                        # single-value attribute that needs concatenation.
                        #
                        # This simulates a refcount bug that was found during
                        # development and serves as an extra stress-test.
                        self.__assert_action_str(
                            'set name=multi-value value=bar value="foo ""baz"',
                            'set name=multi-value value=bar value="foo baz"',
                            { 'name': 'multi-value',
                                'value': ['bar', 'foo baz'] })

                        self.__assert_action_str(astr, expected, expattrs)

                astr = 'file path=etc/foo\nfacet.debug=true'
                expected = 'file NOHASH facet.debug=true path=etc/foo'
                expattrs = { 'path': 'etc/foo', 'facet.debug': 'true' }
                self.__assert_action_str(astr, expected, expattrs)

        def test_action_sig_str(self):
                sig_act = action.fromstr(
                    "signature 54321 algorithm=baz")
                for s in self.act_strings:
                        # action.sig_str should return an identical string each
                        # time it's called.  Also, parsing the result of
                        # sig_str so produce the same action.
                        a = action.fromstr(s)
                        s2 = a.sig_str(sig_act, generic.Action.sig_version)
                        s3 = a.sig_str(sig_act, generic.Action.sig_version)
                        # If s2 is None, then s was a different signature
                        # action, so there is no output to parse.
                        if s2 is None:
                                continue
                        self.assertEqual(s2, s3)
                        a2 = action.fromstr(s2)
                        if a.different(a2):
                                self.debug("a1 " + str(a))
                                self.debug("a2 " + str(a2))
                                self.assertTrue(not a.different(a2))
                        s4 = a.sig_str(sig_act, generic.Action.sig_version)
                        self.assertEqual(s2, s4)
                # Test that using an unknown sig_version triggers the
                # appropriate exception.
                self.assertRaises(api_errors.UnsupportedSignatureVersion,
                    sig_act.sig_str, sig_act, -1)
                a = action.fromstr(self.act_strings[0])
                self.assertRaises(api_errors.UnsupportedSignatureVersion,
                    a.sig_str, sig_act, -1)
                # Test that the sig_str of a signature action other than the
                # argument action is None.
                sig_act2 = action.fromstr(
                    "signature 98765 algorithm=foobar")
                self.assertTrue(sig_act.sig_str(sig_act2,
                    generic.Action.sig_version) is None)
                self.assertTrue(sig_act2.sig_str(sig_act,
                    generic.Action.sig_version) is None)

        def assertMalformed(self, text):
                malformed = False

                try:
                        action.fromstr(text)
                except action.MalformedActionError as e:
                        assert e.actionstr == text
                        self.debug(text)
                        self.debug(str(e))
                        malformed = True

                # If the action isn't malformed, something is wrong.
                self.assertTrue(malformed, "Action not malformed: " + text)

        def assertInvalid(self, text):
                invalid = False

                try:
                        action.fromstr(text)
                except action.InvalidActionError:
                        invalid = True

                # If the action isn't invalid, something is wrong.
                self.assertTrue(invalid, "Action not invalid: " + text)

        def test_action_errors(self):
                # Unknown action type
                self.assertRaises(action.UnknownActionError, action.fromstr,
                    "moop bar=baz")
                self.assertRaises(action.UnknownActionError, action.fromstr,
                    "setbar=baz quux=quark")

                # Nothing but the action type or type is malformed.
                self.assertMalformed("moop")
                self.assertMalformed("setbar=baz")

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
                self.assertMalformed("file 1234 path=/tmp/foo broken=\t")
                self.assertMalformed("file 1234 path=/tmp/foo broken=\n")
                self.assertMalformed("file 1234 path=/tmp/foo broken")

                # Whitespace in key
                self.assertMalformed("file 1234 path=/tmp/foo bro ken")
                self.assertMalformed("file 1234 path=/tmp/foo\tbro\tken")
                self.assertMalformed("file 1234 path=/tmp/foo\nbro\nken")
                self.assertMalformed("file 1234 path ='/tmp/foo")
                self.assertMalformed("file 1234 path\t=/tmp/foo")
                self.assertMalformed("file 1234 path\n=/tmp/foo")

                # Attribute value is invalid.
                self.assertInvalid("depend type=unknown fmri=foo@1.0")

                # Missing required attribute 'type'.
                self.assertInvalid("depend fmri=foo@1.0")

                # Missing key attribute 'fmri'.
                self.assertInvalid("depend type=require")

                # Mutiple fmri values only allowed for require-any deps.
                self.assertInvalid("depend type=require fmri=foo fmri=bar")

                # Multiple values never allowed for depend action 'type' attribute.
                self.assertInvalid("depend type=require type=require-any fmri=foo")
                if six.PY2:
                # have to skip this test case in Python 3 because _common.c`set_invalid_action_error
                # can't import "pkg.actions" due to some reasons
                        self.assertInvalid("depend type=require type=require-any fmri=foo fmri=bar")

                # 'path' attribute specified multiple times
                self.assertInvalid("file 1234 path=foo path=foo mode=777 owner=root group=root")
                self.assertInvalid("link path=foo path=foo target=link")
                self.assertInvalid("dir path=foo path=foo mode=777 owner=root group=root")

                # 'data' used as an attribute key
                self.assertInvalid("file 1234 path=/tmp/foo data=rubbish")

                # Missing required attribute 'path'.
                self.assertRaises(action.InvalidActionError, action.fromstr,
                    "file 1234 owner=foo")

                # Missing required attribute 'name'.
                self.assertRaises(action.InvalidActionError, action.fromstr,
                    "driver alias=pci1234,56 alias=pci4567,89 class=scsi")

                # Verify malformed actions > 255 characters don't cause corrupt
                # exception action strings.
                self.assertMalformed("""legacy arch=i386 category=GNOME2,application,JDSosol desc="XScreenSaver is two things: it is both a large collection of screen savers (distributed in the "hacks" packages) and it is also the framework for blanking and locking the screen (this package)." hotline="Please contact your local service provider" name="XScreenSaver is two things: it is both a large collection of screen savers (distributed in the "hacks" packages) and it is also the framework for blanking and locking the screen (this package)." pkg=SUNWxscreensaver vendor="XScreenSaver Community" version=5.11,REV=110.0.4.2010.07.08.22.18""")
                self.assertMalformed("""legacy arch=i386 category=GNOME2,application,JDSosol desc="XScreenSaver is two things: it is both a large collection of screen savers (distributed in the "hacks" packages) and it is also the framework for blanking and locking the screen (this package)." hotline="Please contact your local service provider" name="XScreenSaver is two things: it is both a large collection of screen savers (distributed in the "hacks" packages) and it is also the framework for blanking and locking the screen (this package)." pkg=SUNWxscreensaver-l10n vendor="XScreenSaver Community" version=5.11,REV=110.0.4.2010.07.08.22.18""")

                # Missing required attribute 'algorithm'.
                self.assertRaises(action.InvalidActionError, action.fromstr,
                    "signature 12345 pkg.cert=bar")

                # The payload hash can't be specified as both a named and a
                # positional attribute if they're not identical.
                self.assertInvalid("file xyz789 hash=abc123 path=usr/bin/foo mode=0755 owner=root group=bin")
                action.fromstr("file abc123 hash=abc123 path=usr/bin/foo mode=0755 owner=root group=bin")

        def test_validate(self):
                """Verify that action validate() works as expected; currently
                only used during publication or action execution failure."""

                fact = "file 12345 name=foo path=/tmp/foo mode=XXX"
                dact = "dir path=/tmp mode=XXX"

                def assertTrueinvalid_attrs(astr):
                        bad_act = action.fromstr(astr)
                        try:
                                bad_act.validate()
                        except Exception as e:
                                self.debug(str(e))
                        else:
                                self.debug("expected failure validating: {0}".format(
                                    astr))

                        self.assertRaises(
                            action.InvalidActionAttributesError,
                            bad_act.validate)

                # Verify predicate and target attributes of FMRIs must be valid.
                for nact in (
                    # FMRI value is invalid.
                    "depend type=require-any fmri=foo fmri=bar fmri=invalid@abc",
                    # Predicate is missing for conditional dependency.
                    "depend type=conditional fmri=foo",
                    # Predicate value is invalid.
                    "depend type=conditional predicate=-invalid fmri=foo",
                    # Predicate isn't valid for dependency type.
                    "depend type=require predicate=1invalid fmri=foo",
                    # root-image attribute is only valid for origin dependencies.
                    "depend type=require fmri=foo root-image=true",
                    # Multiple values for predicate are not allowed.
                    "depend type=conditional predicate=foo predicate=bar fmri=baz",
                    # Multiple values for ignore-check are not allowed.
                    "depend type=require fmri=foo ignore-check=true ignore-check=false"):
                        assertTrueinvalid_attrs(nact)

                # Verify multiple values for file attributes are rejected.
                for attr in ("pkg.size", "pkg.csize", "chash", "preserve",
                    "overlay", "elfhash", "original_name", "facet.doc",
                    "owner", "group"):
                        nact = "file path=/usr/bin/foo owner=root group=root " \
                            "mode=0555 {attr}=1 {attr}=2 {attr}=3".format(
                            attr=attr)
                        assertTrueinvalid_attrs(nact)

                # Verify invalid values are not allowed for mode attribute on
                # file and dir actions.
                for act in (fact, dact):
                        for bad_mode in ("", 'mode=""', "mode=???",
                            "mode=44755", "mode=44", "mode=999", "mode=0898"):
                                nact = act.replace("mode=XXX", bad_mode)
                                assertTrueinvalid_attrs(nact)

                # Verify multiple values aren't allowed for legacy action
                # attributes.
                for attr in ("category", "desc", "hotline", "name", "vendor",
                    "version"):
                        nact = "legacy pkg=SUNWcs {attr}=1 {attr}=2".format(
                            attr=attr)
                        assertTrueinvalid_attrs(nact)

                # Verify multiple values aren't allowed for gid of group.
                nact = "group groupname=staff gid=100 gid=101"
                assertTrueinvalid_attrs(nact)

                # Verify only numeric value is allowed for gid of group.
                nact = "group groupname=staff gid=abc"
                assertTrueinvalid_attrs(nact)

                # Verify multiple values are not allowed for must-accept and
                # must-display attributes of license actions.
                for attr in ("must-accept", "must-display"):
                        nact = "license license=copyright {attr}=true " \
                            "{attr}=false".format(attr=attr)
                        assertTrueinvalid_attrs(nact)

                # Ensure link and hardlink attributes are validated properly.
                for aname in ("link", "hardlink"):
                        # Action with mediator without mediator properties is
                        # invalid.
                        nact = "{0} path=usr/bin/vi target=../sunos/bin/edit " \
                            "mediator=vi".format(aname)
                        assertTrueinvalid_attrs(nact)

                        # Action with multiple mediator values is invalid.
                        nact = "{0} path=usr/bin/vi target=../sunos/bin/edit " \
                            "mediator=vi mediator=vim " \
                            "mediator-implementatio=svr4".format(aname)
                        assertTrueinvalid_attrs(nact)

                        # Action with mediator properties without mediator
                        # is invalid.
                        props = {
                            "mediator-version": "1.0",
                            "mediator-implementation": "svr4",
                            "mediator-priority": "site",
                        }
                        for prop, val in six.iteritems(props):
                                nact = "{0} path=usr/bin/vi " \
                                    "target=../sunos/bin/edit {1}={2}".format(aname,
                                    prop, val)
                                assertTrueinvalid_attrs(nact)

                        # Action with multiple values for any property is
                        # invalid.
                        for prop, val in six.iteritems(props):
                                nact = "{0} path=usr/bin/vi " \
                                    "target=../sunos/bin/edit mediator=vi " \
                                    "{1}={2} {3}={4} ".format(aname, prop, val, prop,
                                    val)
                                if prop == "mediator-priority":
                                        # mediator-priority alone isn't
                                        # valid, so test multiple value
                                        # invalid, add something.
                                        nact += " mediator-version=1.0"
                                assertTrueinvalid_attrs(nact)

                        # Verify invalid mediator names are rejected.
                        for value in ("not/valid", "not valid", "not.valid"):
                                nact = "{0} path=usr/bin/vi target=vim " \
                                    "mediator=\"{1}\" mediator-implementation=vim" \
                                   .format(aname, value)
                                assertTrueinvalid_attrs(nact)

                        # Verify invalid mediator-versions are rejected.
                        for value in ("1.a", "abc", ".1"):
                                nact = "{0} path=usr/bin/vi target=vim " \
                                    "mediator=vim mediator-version={1}" \
                                   .format(aname, value)
                                assertTrueinvalid_attrs(nact)

                        # Verify invalid mediator-implementations are rejected.
                        for value in ("1.a", "@", "@1", "vim@.1",
                            "vim@abc"):
                                nact = "{0} path=usr/bin/vi target=vim " \
                                    "mediator=vim mediator-implementation={1}" \
                                   .format(aname, value)
                                assertTrueinvalid_attrs(nact)

                        # Verify multiple targets are not allowed.
                        nact = "{0} path=/usr/bin/foo target=bar target=baz".format(
                            aname)
                        assertTrueinvalid_attrs(nact)

                # Verify multiple values are not allowed for set actions such as
                # pkg.description, pkg.obsolete, pkg.renamed, and pkg.summary.
                for attr in ("pkg.description", "pkg.obsolete", "pkg.renamed",
                    "pkg.summary", "pkg.depend.explicit-install"):
                        nact = "set name={0} value=true value=false".format(attr)
                        assertTrueinvalid_attrs(nact)

                # Verify signature action attribute 'value' is required during
                # publication.
                nact = "signature 12345 algorithm=foo"
                assertTrueinvalid_attrs(nact)

                # Verify multiple values aren't allowed for user attributes.
                for attr in ("password", "group", "gcos-field", "home-dir",
                    "login-shell", "ftpuser"):
                        nact = "user username=user {attr}=ab {attr}=cd ".format(
                            attr=attr)
                        assertTrueinvalid_attrs(nact)

                for attr in ("uid", "lastchg", "min","max", "warn", "inactive",
                    "expire", "flag"):
                        nact = "user username=user {attr}=1 {attr}=2".format(
                            attr=attr)
                        assertTrueinvalid_attrs(nact)

                # Verify only numeric values are allowed for user attributes
                # expecting a number.
                for attr in ("uid", "lastchg", "min","max", "warn", "inactive",
                    "expire", "flag"):
                        nact = "user username=user {0}=abc".format(attr)
                        assertTrueinvalid_attrs(nact)

                # Malformed pkg actuators
                assertTrueinvalid_attrs(
                    "set name=pkg.additional-update-on-uninstall "
                    "value=&@M")
                assertTrueinvalid_attrs(
                    "set name=pkg.additional-update-on-uninstall "
                    "value=A@1 value=&@M")
                # Unknown actuator (should pass)
                act = action.fromstr(
                    "set name=pkg.additional-update-on-update value=A@1")
                act.validate()

if __name__ == "__main__":
        unittest.main()
