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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

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

                action.fromstr("signature 12345 algorithm=foo")

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
                self.assert_(a.attrs["value"].count('"') == 45)

                # Make sure that the hash member of the action object properly
                # contains the value of the "hash" named attribute.
                a = action.fromstr("file hash=abc123 path=usr/bin/foo mode=0755 owner=root group=bin")
                self.assert_(a.hash == "abc123")

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
                """Test that actions convert to strings properly.  This means
                that we can feed the resulting string back into fromstr() and
                get an identical action back."""

                for s in self.act_strings:
                        self.debug(str(s))
                        a = action.fromstr(s)
                        s2 = str(a)
                        a2 = action.fromstr(s2)
                        if a.different(a2):
                                self.debug("a1 " + str(a))
                                self.debug("a2 " + str(a2))
                                self.assert_(not a.different(a2))

                # The one place that invariant doesn't hold is when you specify
                # the payload hash as the named attribute "hash", in which case
                # the resulting re-stringification emits the payload hash as a
                # positional attribute again ...
                s = "file hash=abc123 path=usr/bin/foo mode=0755 owner=root group=bin"
                self.debug(s)
                a = action.fromstr(s)
                s2 = str(a)
                self.assert_(s2.startswith("file abc123 "))
                self.assert_("hash=abc123" not in s2)
                a2 = action.fromstr(s2)
                self.assert_(not a.different(a2))

                # ... unless of course the hash can't be represented that way.
                a = action.fromstr("file hash=abc=123 path=usr/bin/foo mode=0755 owner=root group=bin")
                self.assert_("hash=abc=123" in str(a))
                self.assert_(not str(a).startswith("file abc=123"))

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
                                self.assert_(not a.different(a2))
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
                self.assert_(sig_act.sig_str(sig_act2,
                    generic.Action.sig_version) is None)
                self.assert_(sig_act2.sig_str(sig_act,
                    generic.Action.sig_version) is None)

        def assertMalformed(self, text):
                malformed = False

                try:
                        action.fromstr(text)
                except action.MalformedActionError, e:
                        assert e.actionstr == text
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

                # Mutiple fmri values only allowed for require-any deps.
                self.assertInvalid("depend type=require fmri=foo fmri=bar")

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

                def assert_invalid_attrs(astr):
                        bad_act = action.fromstr(astr)
                        try:
                                bad_act.validate()
                        except Exception, e:
                                self.debug(str(e))
                        else:
                                self.debug("expected failure validating: %s" %
                                    astr)

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
                    "depend type=conditional predicate=foo predicate=bar fmri=baz"):
                        assert_invalid_attrs(nact)

                # Verify multiple values for file attributes are rejected.
                for attr in ("pkg.size", "pkg.csize", "chash", "preserve",
                    "overlay", "elfhash", "original_name", "facet.doc",
                    "variant.count", "owner", "group"):
                        nact = "file path=/usr/bin/foo owner=root group=root " \
                            "mode=0555 %(attr)s=1 %(attr)s=2 %(attr)s=3" % {
                            "attr": attr }
                        assert_invalid_attrs(nact)

                # Verify invalid values are not allowed for mode attribute on
                # file and dir actions. 
                for act in (fact, dact):
                        for bad_mode in ("", 'mode=""', "mode=???", 
                            "mode=44755", "mode=44", "mode=999", "mode=0898"):
                                nact = act.replace("mode=XXX", bad_mode)
                                assert_invalid_attrs(nact)

                # Verify multiple values aren't allowed for legacy action
                # attributes.
                for attr in ("category", "desc", "hotline", "name", "vendor",
                    "version"):
                        nact = "legacy pkg=SUNWcs %(attr)s=1 %(attr)s=2" % {
                            "attr": attr }
                        assert_invalid_attrs(nact)

                # Verify multiple values aren't allowed for gid of group.
                nact = "group groupname=staff gid=100 gid=101"
                assert_invalid_attrs(nact)

                # Verify only numeric value is allowed for gid of group.
                nact = "group groupname=staff gid=abc"
                assert_invalid_attrs(nact)

                # Verify multiple values are not allowed for must-accept and
                # must-display attributes of license actions.
                for attr in ("must-accept", "must-display"):
                        nact = "license license=copyright %(attr)s=true " \
                            "%(attr)s=false" % { "attr": attr }
                        assert_invalid_attrs(nact)

                # Ensure link and hardlink attributes are validated properly.
                for aname in ("link", "hardlink"):
                        # Action with mediator without mediator properties is
                        # invalid.
                        nact = "%s path=usr/bin/vi target=../sunos/bin/edit " \
                            "mediator=vi" % aname
                        assert_invalid_attrs(nact)

                        # Action with multiple mediator values is invalid.
                        nact = "%s path=usr/bin/vi target=../sunos/bin/edit " \
                            "mediator=vi mediator=vim " \
                            "mediator-implementatio=svr4" % aname
                        assert_invalid_attrs(nact)

                        # Action with mediator properties without mediator
                        # is invalid.
                        props = {
                            "mediator-version": "1.0",
                            "mediator-implementation": "svr4",
                            "mediator-priority": "site",
                        }
                        for prop, val in props.iteritems():
                                nact = "%s path=usr/bin/vi " \
                                    "target=../sunos/bin/edit %s=%s" % (aname,
                                    prop, val)
                                assert_invalid_attrs(nact)

                        # Action with multiple values for any property is
                        # invalid.
                        for prop, val in props.iteritems():
                                nact = "%s path=usr/bin/vi " \
                                    "target=../sunos/bin/edit mediator=vi " \
                                    "%s=%s %s=%s " % (aname, prop, val, prop,
                                    val)
                                if prop == "mediator-priority":
                                        # mediator-priority alone isn't
                                        # valid, so test multiple value
                                        # invalid, add something.
                                        nact += " mediator-version=1.0"
                                assert_invalid_attrs(nact)

                        # Verify invalid mediator names are rejected.
                        for value in ("not/valid", "not valid", "not.valid"):
                                nact = "%s path=usr/bin/vi target=vim " \
                                    "mediator=\"%s\" mediator-implementation=vim" \
                                    % (aname, value)
                                assert_invalid_attrs(nact)

                        # Verify invalid mediator-versions are rejected.
                        for value in ("1.a", "abc", ".1"):
                                nact = "%s path=usr/bin/vi target=vim " \
                                    "mediator=vim mediator-version=%s" \
                                    % (aname, value)
                                assert_invalid_attrs(nact)

                        # Verify invalid mediator-implementations are rejected.
                        for value in ("1.a", "@", "@1", "vim@.1",
                            "vim@abc"):
                                nact = "%s path=usr/bin/vi target=vim " \
                                    "mediator=vim mediator-implementation=%s" \
                                    % (aname, value)
                                assert_invalid_attrs(nact)

                        # Verify multiple targets are not allowed.
                        nact = "%s path=/usr/bin/foo target=bar target=baz" % \
                            aname
                        assert_invalid_attrs(nact)

                # Verify multiple values are not allowed for set actions such as
                # pkg.description, pkg.obsolete, pkg.renamed, and pkg.summary.
                for attr in ("pkg.description", "pkg.obsolete", "pkg.renamed",
                    "pkg.summary"):
                        nact = "set name=%s value=true value=false" % attr
                        assert_invalid_attrs(nact)

                # Verify signature action attribute 'value' is required during
                # publication.
                nact = "signature 12345 algorithm=foo"
                assert_invalid_attrs(nact)

                # Verify multiple values aren't allowed for user attributes.
                for attr in ("password", "group", "gcos-field", "home-dir",
                    "login-shell", "ftpuser"):
                        nact = "user username=user %(attr)s=ab %(attr)s=cd " % \
                            { "attr": attr }
                        assert_invalid_attrs(nact)

                for attr in ("uid", "lastchg", "min","max", "warn", "inactive",
                    "expire", "flag"):
                        nact = "user username=user %(attr)s=1 %(attr)s=2" % {
                            "attr": attr }
                        assert_invalid_attrs(nact)

                # Verify only numeric values are allowed for user attributes
                # expecting a number.
                for attr in ("uid", "lastchg", "min","max", "warn", "inactive",
                    "expire", "flag"):
                        nact = "user username=user %s=abc" % attr
                        assert_invalid_attrs(nact)


if __name__ == "__main__":
        unittest.main()
