#!/usr/bin/python
# -*- coding: utf-8 -*-
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

import copy
import os
import pwd
import re
import shutil
import signal
import stat
import tempfile
import time
import unittest

from pkg import misc, portable
import pkg.config as cfg
import pkg.portable as portable

# The Thai word for package.
TH_PACKAGE = u'บรรจุภัณฑ์'


class TestProperty(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of the pkg.config Property classes.
        """

        def __verify_init(self, propcls, propname, glist, blist):
                # 'glist' contains the list of good values to try.
                for defval, expval in glist:
                        # Check init.
                        p = propcls(propname, default=defval)
                        self.assertEqual(p.value, expval)

                        # Check set.
                        p = propcls(propname)
                        p.value = defval
                        self.assertEqual(p.value, expval)

                # 'blist' contains the list of bad values to try.
                for badval in blist:
                        # Check init.
                        self.assertRaises(cfg.InvalidPropertyValueError,
                            propcls, propname, default=badval)

                        # Check set.
                        p = cfg.PropBool(propname)
                        self.assertRaises(cfg.InvalidPropertyValueError,
                            setattr, p, "value", badval)

        def __verify_equality(self, propcls, eqlist, nelist):
                # Check eq.
                for entry in eqlist:
                        (p1name, p1def), (p2name, p2def) = entry
                        p1 = propcls(p1name, default=p1def)
                        p2 = propcls(p2name, default=p2def)
                        # This ensures that both __eq__ and __ne__ are tested
                        # properly.
                        self.assertTrue(p1 == p2)
                        self.assertFalse(p1 != p2)

                # Check ne.
                for entry in nelist:
                        (p1name, p1def), (p2name, p2def) = entry
                        p1 = propcls(p1name, default=p1def)
                        p2 = propcls(p2name, default=p2def)
                        # This ensures that both __eq__ and __ne__ are tested
                        # properly.
                        self.assertTrue(p1 != p2)
                        self.assertFalse(p1 == p2)

        def __verify_stringify(self, propcls, propname, explist, debug=False):
                for val, expstr in explist:
                        # Verify that the stringified form of the property's
                        # value matches what is expected.
                        p1 = propcls(propname, default=val)
                        self.assertEqual(unicode(p1), expstr)
                        self.assertEqual(str(p1), expstr.encode("utf-8"))

                        # Verify that a property value's stringified form
                        # provides can be parsed into an exact equivalent
                        # in native form (e.g. list -> string -> list).
                        p2 = propcls(propname)
                        p2.value = unicode(p1)
                        self.assertEqual(p1.value, p2.value)
                        self.assertEqualDiff(str(p1), str(p2))

                        p2.value = str(p1)
                        self.assertEqual(p1.value, p2.value)
                        self.assertEqualDiff(str(p1), str(p2))

        def __verify_ex_stringify(self, ex):
                encs = str(ex)
                self.assertNotEqual(len(encs), 0)
                unis = unicode(ex)
                self.assertNotEqual(len(unis), 0)
                self.assertEqualDiff(encs, unis.encode("utf-8"))

        def test_base(self):
                """Verify base property functionality works as expected."""

                propcls = cfg.Property

                # Verify invalid names aren't permitted.
                for n in ("contains\na new line", "contains\ttab",
                    "contains/slash", "contains\rcarriage return",
                    "contains\fform feed", "contains\vvertical tab",
                    "contains\\backslash", "", TH_PACKAGE):
                        self.assertRaises(cfg.InvalidPropertyNameError,
                            propcls, n)

                # Verify spaces are permitted.
                propcls("has space")

                # Verify property objects are sorted by name and that other
                # objects are sorted after.
                plist = [propcls(n) for n in ("c", "d", "a", "b")]
                plist.extend(["g", "e", "f"])
                plist.sort()
                self.assertEqual(
                    [getattr(p, "name", p) for p in plist],
                    ["a", "b", "c", "d", "e", "f", "g"]
                )

                # Verify equality is always False when comparing a property
                # object to a different object and that objects that are not
                # properties don't cause a traceback.
                p1 = propcls("property")
                self.assertFalse(p1 == "property")
                self.assertTrue(p1 != "property")
                self.assertFalse(p1 == None)
                self.assertTrue(p1 != None)

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, ""), ("", ""), ("foo", "foo"), (123, "123"),
                    (False, "False"), (TH_PACKAGE, TH_PACKAGE)]
                blist = [
                    [],         # 
                    {},         # Expect strings; not objects.
                    object(),   #
                ]
                self.__verify_init(propcls, "def", glist, blist)

                glist = [
                    (None, ""),                 # None should become "".
                    ("", ""),                   # "" should equal "".
                    ("foo", "foo"),             # simple strings should match.
                    (123, "123"),               # int should become str.
                    (False, "False"),           # boolean should become str.
                    (TH_PACKAGE, TH_PACKAGE),   # UTF-8 data.
                    ("\xfe", "\xfe")            # Passthrough of 8-bit data.
                                                # (That is not valid UTF-8.)
                ]
                blist = [
                    [],         #
                    {},         # Other data types or objects not expected.
                    object()    #       
                ]
                self.__verify_init(propcls, "def", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("def", ""), ("def", None)),
                    (("def", "bob cat"), ("def", "bob cat")),
                    (("def", TH_PACKAGE), ("def", TH_PACKAGE)),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("def", "bob cat"), ("str2", "bob cat")),
                    (("def", "lynx"), ("str2", "bob cat")),
                    (("def", u'ซ'), ("str2", TH_PACKAGE)),
                ]
                self.__verify_equality(propcls, eqlist, nelist)


                # Verify base stringify works as expected.
                self.__verify_stringify(propcls, "property", [(None, ""),
                    ("", ""), (TH_PACKAGE, TH_PACKAGE)])

                # Verify base copy works as expected.
                p1 = propcls("p1", "v1")
                p2 = copy.copy(p1)
                self.assertEqual(p1.name, p2.name)
                self.assertEqual(p1.value, p2.value)
                self.assertNotEqual(id(p1), id(p2))

        def test_bool(self):
                """Verify boolean properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropBool
                p = propcls("bool")
                self.assertEqual(p.value, False)

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, False), ("", False), (False, False),
                    ("False", False), ("True", True)]
                blist = [("bogus", 123, "-true-", "\n")]
                self.__verify_init(propcls, "bool", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("bool", True), ("bool", True)),
                    (("bool", "True"), ("bool", True)),
                    (("bool", "true"), ("bool", True)),
                    (("bool", "TrUE"), ("bool", True)),
                    (("bool", False), ("bool", False)),
                    (("bool", "False"), ("bool", False)),
                    (("bool", "false"), ("bool", False)),
                    (("bool", "FaLsE"), ("bool", False)),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("bool", True), ("bool2", True)),
                    (("bool", True), ("bool", False)),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form.
                self.__verify_stringify(propcls, "bool", [(True, "True"),
                    (False, "False")])

        def test_defined(self):
                """Verify defined properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropDefined
                p = propcls("def")
                self.assertEqual(p.value, "")

                # Verify stringified form.
                self.__verify_stringify(propcls, "def", [("", ""),
                    ("bob cat", "bob cat"), (TH_PACKAGE, TH_PACKAGE)])

                # Verify allowed value functionality permits expected values.
                p = propcls("def", allowed=["", "<pathname>", "<exec:pathname>",
                    "<smffmri>"])
                for v in ("/abs/path", "exec:/my/binary",
                    "svc:/application/pkg/server:default", ""):
                        p.value = v

                # Verify allowed value functionality denies unexpected values.
                p = propcls("def", allowed=["<abspathname>"],
                    default="/abs/path")
                for v in ("not/abs/path", "../also/not/not/abs", ""):
                        self.debug("p: %s" % v)
                        self.assertRaises(cfg.InvalidPropertyValueError,
                            setattr, p, "value", v)

        def test_int(self):
                """Verify integer properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropInt
                p = propcls("int")
                self.assertEqual(p.value, 0)

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, 0), ("", 0), (1, 1),
                    ("16384", 16384)]
                blist = [("bogus", "-true-", "\n")]
                self.__verify_init(propcls, "int", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("int", 0), ("int", 0)),
                    (("int", "16384"), ("int", 16384)),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("int", 256), ("int2", 256)),
                    (("int", 0), ("int", 256)),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify minimum works as expected.
                p = propcls("int", minimum=-1)
                self.assertEqual(p.minimum, -1)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, p, "value", -100)
                p.value = 4294967295
                self.assertEqual(p.value, 4294967295)

                # Verify maximum works as expected.
                p = propcls("int", maximum=65535)
                self.assertEqual(p.maximum, 65535)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, p, "value", 42944967295)
                p.value = 65535
                self.assertEqual(p.value, 65535)

                # Verify maximum and minimum work together.
                p = propcls("int", maximum=1, minimum=-1)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, p, "value", -2)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, p, "value", 2)

                # Verify maximum and minimum are copied when object is.
                np = copy.copy(p)
                self.assertEqual(np.maximum, 1)
                self.assertEqual(np.minimum, -1)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, np, "value", -2)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, np, "value", 2)

                # Verify stringified form.
                self.__verify_stringify(propcls, "int", [(0, "0"),
                    (4294967296, "4294967296")])

        def test_exceptions(self):
                """Verify that exception classes can be initialized as expected,
                and when stringified return a non-zero-length string.
                """

                # Verify the expected behavior of all ConfigError classes.
                for excls in (cfg.PropertyConfigError,
                    cfg.PropertyMultiValueError,
                    cfg.InvalidPropertyValueError, cfg.UnknownPropertyError,
                    cfg.UnknownPropertyValueError, cfg.UnknownSectionError):
                        # Verify that exception can't be created without
                        # specifying section or property.
                        self.assertRaises(AssertionError, excls)

                        # Verify that exception can be created with just
                        # section or property, or both, and that expected
                        # value is set.  In addition, verify that the
                        # stringified form or unicode object is equal
                        # and not zero-length.
                        ex1 = excls(section="section")
                        self.assertEqual(ex1.section, "section")

                        ex2 = excls(prop="property")
                        self.assertEqual(ex2.prop, "property")

                        ex3 = excls(section="section", prop="property")
                        self.assertEqual(ex3.section, "section")
                        self.assertEqual(ex3.prop, "property")

                        if excls == cfg.PropertyConfigError:
                                # Can't stringify base class.
                                continue
                        map(self.__verify_ex_stringify, (ex1, ex2, ex3))

                        if excls != cfg.UnknownPropertyValueError:
                                continue

                        ex4 = excls(section="section", prop="property",
                            value="value")
                        self.assertEqual(ex4.section, "section")
                        self.assertEqual(ex4.prop, "property")
                        self.assertEqual(ex4.value, "value")
                        self.__verify_ex_stringify(ex4)

                for excls in (cfg.InvalidSectionNameError,
                    cfg.InvalidSectionTemplateNameError):
                        # Verify that exception can't be created without
                        # specifying section.
                        self.assertRaises(AssertionError, excls, None)

                        # Verify that exception can be created with just section
                        # and that expected value is set.  In addition, verify
                        # that the stringified form or unicode object is equal
                        # and not zero-length.
                        ex1 = excls("section")
                        self.assertEqual(ex1.section, "section")
                        self.__verify_ex_stringify(ex1)

                for excls in (cfg.InvalidPropertyNameError,
                    cfg.InvalidPropertyTemplateNameError):
                        # Verify that exception can't be created without
                        # specifying prop.
                        self.assertRaises(AssertionError, excls, None)

                        # Verify that exception can be created with just prop
                        # and that expected value is set.  In addition, verify
                        # that the stringified form or unicode object is equal
                        # and not zero-length.
                        ex1 = excls("prop")
                        self.assertEqual(ex1.prop, "prop")
                        self.__verify_ex_stringify(ex1)

        def test_list(self):
                """Verify list properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropList
                p = propcls("list")
                self.assertEqual(p.value, [])

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [
                    ([1, 2, None], ["1", "2", ""]),
                    ([TH_PACKAGE, "bob cat", "profit"], [TH_PACKAGE, "bob cat",
                        "profit"]),
                    ([1, "???", "profit"], ["1", "???", "profit"]),
                    ([False, True, "false"], ["False", "True", "false"]),
                    ([TH_PACKAGE, "profit"], [TH_PACKAGE, "profit"]),
                    (["\xfe", "bob cat"], ["\xfe", "bob cat"]),
                ]
                blist = [[[]], [{}], [object()], '[__import__("sys").exit(-1)]',
                    '{}', 123]
                self.__verify_init(propcls, "list", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("list", [None]), ("list", [""])),
                    (("list", ["box", "cat"]), ("list", ["box", "cat"])),
                    (("list", [TH_PACKAGE, "profit"]),
                        ("list", [TH_PACKAGE, "profit"])),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("list", ["bob cat"]), ("list2", ["bob cat"])),
                    (("list", ["lynx"]), ("list2", ["bob cat"])),
                    (("list", [TH_PACKAGE]),
                        ("list", [TH_PACKAGE, "profit"])),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form and that stringified form can be used
                # to set value.
                self.__verify_stringify(propcls, "list", [
                    ([""], "['']"),
                    (["box", "cat"], "['box', 'cat']"),
                    # List literal form uses unicode_escape.
                    ([TH_PACKAGE, "profit"],
                        u"[u'%s', 'profit']" %
                        TH_PACKAGE.encode("unicode_escape")),
                    (["\xfe", "bob cat"], "['\\xfe', 'bob cat']"),
                ])

                # Verify allowed value functionality permits expected values.
                p = propcls("list", allowed=["", "<pathname>",
                    "<exec:pathname>", "<smffmri>"])
                p.value = ["/abs/path", "exec:/my/binary",
                    "svc:/application/pkg/server:default", ""]

                # Verify allowed value functionality denies unexpected values.
                p = propcls("list", allowed=["<pathname>"],
                    default=["/export/repo"])
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, p, "value", ["exec:/binary", "svc:/application",
                        ""])
                self.assertRaises(cfg.InvalidPropertyValueError,
                    setattr, p, "value", [])

                # Verify that any iterable can be used to assign the property's
                # value and the result will still be a list.
                p = propcls("list")
                expected = ["bob cat", "lynx", "tiger"]

                # List.
                p.value = ["bob cat", "lynx", "tiger"]
                self.assertEqual(p.value, expected)

                # Set.
                p.value = set(("bob cat", "lynx", "tiger"))
                self.assertEqual(p.value, list(set(expected)))

                # Tuple.
                p.value = ("bob cat", "lynx", "tiger")
                self.assertEqual(p.value, expected)

                # Generator.
                p.value = (v for v in expected)
                self.assertEqual(p.value, expected)

        def test_publisher(self):
                """Verify publisher properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropPublisher
                p = propcls("pub")
                self.assertEqual(p.value, "")

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, ""), ("", ""), ("example.com", "example.com"),
                    ("sub.sub.Example.Com", "sub.sub.Example.Com"),
                    ("bob-cat", "bob-cat")]
                blist = [(".startperiod", "!@&*#$&*(@badchars", "\n", object())]
                self.__verify_init(propcls, "pub", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("pub", ""), ("pub", None)),
                    (("pub", "bobcat"), ("pub", "bobcat")),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("pub", "bobcat"), ("pub2", "bobcat")),
                    (("pub", "lynx"), ("pub2", "bobcat")),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form.
                self.__verify_stringify(propcls, "int", [("", ""),
                    ("bobcat", "bobcat")])

        def test_simple_list(self):
                """Verify simple list properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropSimpleList
                p = propcls("slist")
                self.assertEqual(p.value, [])

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [
                    ([1, 2, None], ["1", "2", ""]),
                    ([TH_PACKAGE, "bob cat", "profit"],
                        [TH_PACKAGE, "bob cat", "profit"]),
                    ([1, "???", "profit"], ["1", "???", "profit"]),
                    ([False, True, "false"], ["False", "True", "false"]),
                    ([TH_PACKAGE, "profit"], [TH_PACKAGE, "profit"]),
                ]
                blist = [
                    [[]], [{}], [object()], # Objects not expected.
                    123,                    # Numbers not expected.
                    ["\xfe"],               # Arbitrary 8-bit data is not
                    "\xfe",                 # supported.
                ]

                self.__verify_init(propcls, "slist", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("slist", [None]), ("slist", [""])),
                    (("slist", ["box", "cat"]), ("slist", ["box", "cat"])),
                    (("slist", [TH_PACKAGE, "profit"]),
                        ("slist", [TH_PACKAGE, "profit"])),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("slist", ["bob cat"]), ("slist2", ["bob cat"])),
                    (("slist", ["lynx"]), ("slist2", ["bob cat"])),
                    (("slist", [TH_PACKAGE]),
                        ("slist", [TH_PACKAGE, "profit"])),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form (note that a simple list isn't able to
                # preserve zero-length string values whenever it is the only
                # value in the list).
                self.__verify_stringify(propcls, "slist", [
                    (["box", "cat"], "box,cat"),
                    ([TH_PACKAGE, "profit"], u'บรรจุภัณฑ์,profit'),
                ], debug=True)

        def test_puburi(self):
                """Verify publisher URI properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropPubURI
                p = propcls("uri")
                self.assertEqual(p.value, "")

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, ""), ("", ""), ("http://example.com/",
                    "http://example.com/"), ("file:/abspath", "file:/abspath")]
                blist = ["bogus://", {}, object(), 123, "http://@&*#($badchars",
                    "http:/baduri", "example.com", {}, []]
                self.__verify_init(propcls, "str", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("uri", ""), ("uri", None)),
                    (("uri", "http://example.com"),
                        ("uri", "http://example.com")),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("uri", "http://example.com"),
                        ("uri2", "http://example.com")),
                    (("uri", "http://example.org/"),
                        ("uri", "http://example.net/")),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form.
                self.__verify_stringify(propcls, "uri", [("", ""),
                    ("http://example.com", "http://example.com"),
                    ("http://example.org/", "http://example.org/")])

        def test_puburi_list(self):
                """Verify publisher URI list properties work as expected."""

                propcls = cfg.PropPubURIList

                # Verify default if no initial value provided.
                p = propcls("uri_list")
                self.assertEqual(p.value, [])

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, []), ("", []), ("['http://example.com/']",
                    ["http://example.com/"]), (["file:/abspath"],
                    ["file:/abspath"])]
                blist = [["bogus://"], [{}], [object()], [123],
                    ["http://@&*#($badchars"], ["http:/baduri"],
                    ["example.com"]]
                self.__verify_init(propcls, "uri_list", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("uri_list", ""), ("uri_list", [])),
                    (("uri_list", ["http://example.com", "file:/abspath"]),
                        ("uri_list", ["http://example.com", "file:/abspath"])),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("uri_list", ["http://example.com", "file:/abspath"]),
                        ("uri_list2", ["http://example.com", "file:/abspath"])),
                    (("uri_list", ["http://example.com", "file:/abspath"]),
                        ("uri_list", ["http://example.net/"])),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form.
                self.__verify_stringify(propcls, "uri", [("", "[]"),
                    (["http://example.com", "file:/abspath"],
                        "['http://example.com', 'file:/abspath']"),
                    (["file:/abspath"], "['file:/abspath']")])

        def test_simple_puburi_list(self):
                """Verify publisher URI list properties work as expected."""

                propcls = cfg.PropSimplePubURIList

                # Verify default if no initial value provided.
                p = propcls("uri_list")
                self.assertEqual(p.value, [])

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, []), ("", []), ("http://example.com/",
                    ["http://example.com/"]), (["file:/abspath"],
                    ["file:/abspath"])]
                blist = [["bogus://"], [{}], [object()], [123],
                    ["http://@&*#($badchars"], ["http:/baduri"],
                    ["example.com"]]
                self.__verify_init(propcls, "uri_list", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("uri_list", ""), ("uri_list", [])),
                    (("uri_list", ["http://example.com", "file:/abspath"]),
                        ("uri_list", ["http://example.com", "file:/abspath"])),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("uri_list", ["http://example.com", "file:/abspath"]),
                        ("uri_list2", ["http://example.com", "file:/abspath"])),
                    (("uri_list", ["http://example.com", "file:/abspath"]),
                        ("uri_list", ["http://example.net/"])),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form.
                self.__verify_stringify(propcls, "uri", [("", ""),
                    (["http://example.com", "file:/abspath"],
                        "http://example.com,file:/abspath"),
                    (["file:/abspath"], "file:/abspath")])

        def test_uuid(self):
                """Verify UUID properties work as expected."""

                # Verify default if no initial value provided.
                propcls = cfg.PropUUID
                p = propcls("uuid")
                self.assertEqual(p.value, "")

                # Verify that all expected values are accepted at init and
                # during set and that the value is set as expected.  Also
                # verify that bad values are rejected both during init and
                # set.
                glist = [(None, ""), ("", ""),
                    ("16fd2706-8baf-433b-82eb-8c7fada847da",
                    "16fd2706-8baf-433b-82eb-8c7fada847da")]
                blist = [[], {}, object(), "16fd2706-8baf-433b-82eb", "123",
                    "badvalue"]
                self.__verify_init(propcls, "uuid", glist, blist)

                # Verify equality works as expected.
                eqlist = [
                    # Equal because property names and values match.
                    (("uuid", ""), ("uuid", None)),
                    (("uuid", "16fd2706-8baf-433b-82eb-8c7fada847da"),
                        ("uuid", "16fd2706-8baf-433b-82eb-8c7fada847da")),
                ]
                nelist = [
                    # Not equal because property names and/or values do not
                    # match.
                    (("uuid", ""), ("uuid2", None)),
                    (("uuid", "16fd2706-8baf-433b-82eb-8c7fada847da"),
                        ("uuid", "5a912a99-86dd-cb06-8ff0-b6bdfb74d0f6")),
                ]
                self.__verify_equality(propcls, eqlist, nelist)

                # Verify stringified form.
                self.__verify_stringify(propcls, "str", [("", ""),
                    ("16fd2706-8baf-433b-82eb-8c7fada847da",
                    "16fd2706-8baf-433b-82eb-8c7fada847da")])


class TestPropertyTemplate(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of the pkg.config PropertyTemplate
        class.
        """

        def test_base(self):
                """Verify base property template functionality works as
                expected.
                """

                propcls = cfg.PropertyTemplate

                # Verify invalid names aren't permitted.
                for n in ("", re.compile("^$"), "foo.*("):
                        self.assertRaises(cfg.InvalidPropertyTemplateNameError,
                            propcls, n)

                prop = propcls("^facet\..*$")
                self.assertEqual(prop.name, "^facet\..*$")

        def test_create_match(self):
                """Verify that create and match operations work as expected."""

                proptemp = cfg.PropertyTemplate("^facet\..*$")

                # Verify match will match patterns as expected.
                self.assertEqual(proptemp.match("facet.devel"), True)
                self.assertEqual(proptemp.match("facet"), False)

                # Verify create raises an assert if name doesn't match
                # template pattern.
                self.assertRaises(AssertionError, proptemp.create, "notallowed")

                # Verify create returns expected property.
                expected_props = [
                    ({}, { "value": "" }),
                    ({ "prop_type": cfg.Property, "value_map": { "None": None }
                        }, { "value": "" } ),
                    ({ "default": True, "prop_type": cfg.PropBool},
                        { "value": True }),
                    ({ "allowed": ["always", "never"], "default": "never",
                        "prop_type": cfg.PropDefined },
                        { "allowed": ["always", "never"], "value": "never" }),
                ]
                for args, exp_attrs in expected_props:
                        proptemp = cfg.PropertyTemplate("name", **args)
                        extype = args.get("prop_type", cfg.Property)

                        prop = proptemp.create("name")
                        self.assert_(isinstance(prop, extype))

                        for attr in exp_attrs:
                                self.assertEqual(getattr(prop, attr),
                                    exp_attrs[attr])


class TestPropertySection(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of the pkg.config PropertySection
        classes.
        """

        def __verify_stringify(self, cls, explist):
                for val, expstr in explist:
                        self.assertEqual(unicode(cls(val)), expstr)
                        self.assertEqual(str(cls(val)), expstr.encode("utf-8"))

        def test_base(self):
                """Verify base section functionality works as expected."""

                seccls = cfg.PropertySection

                # Verify invalid names aren't permitted.
                for n in ("contains\na new line", "contains\ttab",
                    "contains/slash", "contains\rcarriage return",
                    "contains\fform feed", "contains\vvertical tab",
                    "contains\\backslash", "", TH_PACKAGE,
                    "CONFIGURATION"):
                        self.assertRaises(cfg.InvalidSectionNameError,
                            seccls, n)

                # Verify spaces are permitted.
                seccls("has space")

                # Verify section objects are sorted by name and that other
                # objects are sorted after.
                slist = [seccls(n) for n in ("c", "d", "a", "b")]
                slist.extend(["g", "e", "f"])
                slist.sort()
                self.assertEqual(
                    [getattr(s, "name", s) for s in slist],
                    ["a", "b", "c", "d", "e", "f", "g"]
                )

                # Verify equality is always False when comparing a section
                # object to a different object and that objects that are not
                # sections don't cause a traceback.
                s1 = seccls("section")
                self.assertFalse(s1 == "section")
                self.assertTrue(s1 != "section")
                self.assertFalse(s1 == None)
                self.assertTrue(s1 != None)

                # Verify base stringify works as expected.
                self.__verify_stringify(seccls, [("section", "section")])

                # Verify base copy works as expected.
                s1 = seccls("s1")
                s2 = copy.copy(s1)
                self.assertEqual(s1.name, s2.name)
                self.assertNotEqual(id(s1), id(s2))

        def test_add_get_remove_props(self):
                """Verify add_property, get_property, get_index, get_properties,
                and remove_property works as expected.
                """

                propcls = cfg.Property
                sec = cfg.PropertySection("section")

                # Verify that attempting to retrieve an unknown property
                # raises an exception.
                self.assertRaises(cfg.UnknownPropertyError,
                    sec.get_property, "p1")

                # Verify that attempting to remove an unknown property raises
                # an exception.
                self.assertRaises(cfg.UnknownPropertyError,
                    sec.remove_property, "p1")

                # Verify that a property cannot be added twice.
                p1 = propcls("p1", default="1")
                sec.add_property(p1)
                self.assertRaises(AssertionError, sec.add_property, p1)

                # Verify that get_properties returns expected value.
                p2 = propcls("p2", default="2")
                sec.add_property(p2)
                p3 = propcls("p3", default="3")
                sec.add_property(p3)

                returned = sorted(
                    (p.name, p.value)
                    for p in sec.get_properties()
                )
                expected = [("p1", "1"), ("p2", "2"), ("p3", "3")]
                self.assertEqualDiff(returned, expected)

                # Verify that get_index returns expected value.
                exp_idx = {
                    "p1": "1",
                    "p2": "2",
                    "p3": "3",
                }
                self.assertEqual(sec.get_index(), exp_idx)


class TestPropertySectionTemplate(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of the pkg.config PropertyTemplate
        class.
        """

        def test_base(self):
                """Verify base property section template functionality works as
                expected.
                """

                seccls = cfg.PropertySectionTemplate

                # Verify invalid names aren't permitted.
                for n in ("", re.compile("^$"), "foo.*("):
                        self.assertRaises(cfg.InvalidSectionTemplateNameError,
                            seccls, n)

                sec = seccls("^authority_.*$")
                self.assertEqual(sec.name, "^authority_.*$")

        def test_create_match(self):
                """Verify that create and match operations work as expected."""

                sectemp = cfg.PropertySectionTemplate("^authority_.*$")

                # Verify match will match patterns as expected.
                self.assertEqual(sectemp.match("authority_example.com"), True)
                self.assertEqual(sectemp.match("authority"), False)

                # Verify create raises an assert if name doesn't match
                # template pattern.
                self.assertRaises(AssertionError, sectemp.create, "notallowed")

                # Verify create returns expected section.
                exp_props = [
                    cfg.Property("prop"),
                    cfg.PropBool("bool"),
                    cfg.PropList("list"),
                    cfg.PropertyTemplate("multi_value", prop_type=cfg.PropList),
                ]
                sectemp = cfg.PropertySectionTemplate("name",
                    properties=exp_props)
                sec = sectemp.create("name")
                self.assert_(isinstance(sec, cfg.PropertySection))

                expected = sorted([
                    (p.name, type(p)) for p in exp_props
                ])
                returned = sorted([
                    (p.name, type(p)) for p in sec.get_properties()
                ])
                self.assertEqualDiff(expected, returned)


class _TestConfigBase(pkg5unittest.Pkg5TestCase):

        _defs = {
            0: [cfg.PropertySection("first_section", properties=[
                    cfg.PropBool("bool_basic"),
                    cfg.PropBool("bool_default", default=True),
                    cfg.PropInt("int_basic"),
                    cfg.PropInt("int_default", default=14400),
                    cfg.PropPublisher("publisher_basic"),
                    cfg.PropPublisher("publisher_default",
                        default="example.com"),
                    cfg.Property("str_basic"),
                    cfg.Property("str_escape", default=";, &, (, ), |, ^, <, "
                        ">, nl\n, sp , tab\t, bs\\, ', \", `"),
                    cfg.Property("str_default", default=TH_PACKAGE),
                    cfg.PropDefined("str_allowed", allowed=["<pathname>",
                        "<exec:pathname>", "<smffmri>", "builtin"],
                        default="builtin"),
                    cfg.PropDefined("str_noneallowed", allowed=["", "bob cat"]),
                    cfg.PropList("list_basic"),
                    cfg.PropList("list_default", default=[TH_PACKAGE, "bob cat",
                        "profit"]),
                    cfg.PropList("list_allowed", allowed=["<pathname>",
                        "builtin"], default=["builtin"]),
                    cfg.PropList("list_noneallowed", allowed=["", "always",
                        "never"]),
                ]),
                cfg.PropertySection("second_section", properties=[
                    cfg.PropSimpleList("simple_list_basic"),
                    cfg.PropSimpleList("simple_list_default", default=["bar",
                        "foo", TH_PACKAGE]),
                    cfg.PropSimpleList("simple_list_allowed",
                        allowed=["<pathname>", "builtin"],
                        default=["builtin"]),
                    cfg.PropSimpleList("simple_list_noneallowed",
                        allowed=["", "<pathname>", "builtin"]),
                    cfg.PropPubURI("uri_basic"),
                    cfg.PropPubURI("uri_default",
                        default="http://example.com/"),
                    cfg.PropSimplePubURIList("urilist_basic"),
                    cfg.PropSimplePubURIList("urilist_default",
                        default=["http://example.com/", "file:/example/path"]),
                    cfg.PropUUID("uuid_basic"),
                    cfg.PropUUID("uuid_default",
                        default="16fd2706-8baf-433b-82eb-8c7fada847da"),
                ]),
            ],
            1: [cfg.PropertySection("first_section", properties=[
                    cfg.PropBool("bool_basic"),
                    cfg.Property("str_basic"),
                ]),
            ],
        }

        _templated_defs = {
            0: [cfg.PropertySection("facet", properties=[
                    cfg.PropertyTemplate("^facet\..*", prop_type=cfg.PropBool)
                ]),
            ],
            1: [cfg.PropertySectionTemplate("^authority_.*", properties=[
                    cfg.PropPublisher("prefix")
                ])
            ],
        }

        _initial_state = {
            0: {
                "first_section": {
                    "bool_basic": False,
                    "bool_default": True,
                    "int_basic": 0,
                    "int_default": 14400,
                    "publisher_basic": "",
                    "publisher_default": "example.com",
                    "str_basic": "",
                    "str_escape": ";, &, (, ), |, ^, <, >, nl\n, sp , tab\t, " \
                        "bs\\, ', \", `",
                    "str_default": TH_PACKAGE,
                    "str_allowed": "builtin",
                    "str_noneallowed": "",
                    "list_basic": [],
                    "list_default": [TH_PACKAGE, "bob cat", "profit"],
                    "list_allowed": ["builtin"],
                    "list_noneallowed": [],
                },
                "second_section": {
                    "simple_list_basic": [],
                    "simple_list_default": ["bar", "foo", TH_PACKAGE],
                    "simple_list_allowed": ["builtin"],
                    "simple_list_noneallowed": [],
                    "uri_basic": "",
                    "uri_default": "http://example.com/",
                    "urilist_basic": [],
                    "urilist_default": ["http://example.com/",
                        "file:/example/path"],
                    "uuid_basic": "",
                    "uuid_default": "16fd2706-8baf-433b-82eb-8c7fada847da",
                },
            },
            1: {
                "first_section": {
                    "bool_basic": False,
                    "str_basic": "",
                },
            },
        }

        def _verify_initial_state(self, conf, exp_version, ver_defs=None,
            exp_state=None):
                if ver_defs is None:
                        try:
                                ver_defs = self._defs[exp_version]
                        except:
                                raise RuntimeError("Version not found in "
                                    "definitions.")
                if exp_state is None:
                        exp_state = self._initial_state[exp_version]

                conf_idx = conf.get_index()
                self.assertEqual(conf.version, exp_version)
                self.assertEqualDiff(exp_state, conf_idx)

                # Map out the type of each section and property returned and
                # verify that if it exists in the definition that the type
                # matches.
                def iter_section(parent, spath):
                        # Yield any properties for this section.
                        for prop in parent.get_properties():
                                yield spath, type(parent), prop.name, type(prop)

                        if not hasattr(parent, "get_sections"):
                                # Class doesn't support subsections.
                                return

                        # Yield subsections.
                        for secobj in parent.get_sections():
                                for rval in iter_section(secobj,
                                    "/".join((spath, secobj.name))):
                                        yield rval

                def map_types(slist):
                        tmap = {}
                        for secobj in slist:
                                for spath, stype, pname, ptype in iter_section(
                                    secobj, secobj.name):
                                        tmap.setdefault(spath, {
                                            "type": stype,
                                            "props": {},
                                        })
                                        tmap[spath]["props"][pname] = ptype
                        return tmap

                if not ver_defs:
                        # No version definitions to compare.
                        return

                exp_types = map_types(ver_defs)
                act_types = map_types(conf.get_sections())
                self.assertEqualDiff(exp_types, act_types)

class TestConfig(_TestConfigBase):
        """Class to test the functionality of the pkg.config 'flat'
        configuration classes.
        """

        _initial_files = {
            0: u"""\
[CONFIGURATION]
version = 0

[first_section]
bool_basic = False
bool_default = True
int_basic = 0
int_default = 14400
publisher_basic =
publisher_default = example.com
str_basic =
str_default = %(uni_txt)s
str_allowed = builtin
str_noneallowed =
list_basic = []
list_default = [u'%(uni_escape)s', 'bob cat', 'profit']
list_allowed = ['builtin']
list_noneallowed = []

[second_section]
simple_list_basic =
simple_list_default = bar,foo,%(uni_txt)s
simple_list_allowed = builtin
simple_list_noneallowed =
uri_basic =
uri_default = http://example.com/
urilist_basic =
urilist_default = http://example.com/,file:/example/path
uuid_basic = 
uuid_default = 16fd2706-8baf-433b-82eb-8c7fada847da
""" % { "uni_escape": TH_PACKAGE.encode("unicode_escape"),
    "uni_txt": TH_PACKAGE },
            1: """\
[CONFIGURATION]
version = 1

[first_section]
bool_basic = False
str_basic =
"""
        }

        def test_base(self):
                """Verify that the base Config class functionality works as
                expected.
                """

                # Verify that write() doesn't raise an error for base Config
                # class (it should be a no-op).
                conf = cfg.Config()
                conf.set_property("section", "property", "value")
                conf.write()

                #
                # Verify initial state of Config object.
                #

                # Verify no definitions, overrides, or version.
                conf = cfg.Config()
                self._verify_initial_state(conf, 0, {},
                    exp_state={})

                # Same as above, but with version.
                conf = cfg.Config(version=1)
                self._verify_initial_state(conf, 1, {},
                    exp_state={})

                # Verify no definitions with overrides.
                overrides = {
                    "first_section": {
                        "bool_basic": "False",
                    },
                }
                conf = cfg.Config(overrides=overrides)
                self._verify_initial_state(conf, 0, {},
                    exp_state=overrides)

                # Verify with no overrides and no version (max version found in
                # _defs should be used).
                conf = cfg.Config(definitions=self._defs)
                self._verify_initial_state(conf, 1)

                # Verify with no overrides and with version.
                conf = cfg.Config(definitions=self._defs, version=0)
                self._verify_initial_state(conf, 0)

                # Verify with overrides using native values (as opposed to
                # string values) and with version.
                overrides = {
                    "first_section": {
                        "bool_basic": True,
                        "int_basic": 14400,
                    },
                    "second_section": {
                        "uri_basic": "http://example.net/",
                    },
                }
                conf = cfg.Config(definitions=self._defs, overrides=overrides,
                    version=0)
                exp_state = copy.deepcopy(self._initial_state[0])
                for sname, props in overrides.iteritems():
                        for pname, value in props.iteritems():
                                exp_state[sname][pname] = value
                self._verify_initial_state(conf, 0, exp_state=exp_state)

                #
                # Verify stringify behaviour.
                #

                #
                # Test str case with and without unicode data.
                #
                conf = cfg.Config(definitions=self._defs, version=1)
                self.assertEqualDiff("""\
[first_section]
str_basic = 
bool_basic = False

""", str(conf))

                conf.set_property("first_section", "str_basic", TH_PACKAGE)
                self.assertEqualDiff("""\
[first_section]
str_basic = %s
bool_basic = False

""" % TH_PACKAGE.encode("utf-8"), str(conf))

                #
                # Test unicode case with and without unicode data.
                #
                conf = cfg.Config(definitions=self._defs, version=1)
                self.assertEqualDiff(u"""\
[first_section]
str_basic = 
bool_basic = False

""", unicode(conf))

                conf.set_property("first_section", "str_basic", TH_PACKAGE)
                self.assertEqualDiff(u"""\
[first_section]
str_basic = %s
bool_basic = False

""" % TH_PACKAGE, unicode(conf))
        
                # Verify target is None.
                self.assertEqual(conf.target, None)

        def test_add_get_remove_sections(self):
                """Verify that add_section, get_section, get_sections, and
                get_index work as expected.
                """

                propcls = cfg.Property
                conf = cfg.Config()

                # Verify that attempting to retrieve an unknown section raises
                # an exception.
                self.assertRaises(cfg.UnknownSectionError, conf.get_section,
                    "s1")

                # Verify that attempting to remove an unknown section raises
                # an exception.
                self.assertRaises(cfg.UnknownSectionError, conf.remove_section,
                    "s1")

                # Verify that a section cannot be added twice.
                seccls = cfg.PropertySection
                s1 = seccls("s1", properties=[
                   propcls("1p1", "11"),
                   propcls("1p2", "12"),
                   propcls("1p3", "13"),
                ])
                conf.add_section(s1)
                self.assertRaises(AssertionError, conf.add_section, s1)
                self.assertEqual(id(s1), id(conf.get_section(s1.name)))

                # Verify that get_sections returns expected value.
                s2 = seccls("s2", properties=[
                   propcls("2p1", "21"),
                   propcls("2p2", "22"),
                   propcls("2p3", "23"),
                ])
                conf.add_section(s2)

                s3 = seccls("s3", properties=[
                   propcls("3p1", "31"),
                   propcls("3p2", "32"),
                   propcls("3p3", "33"),
                ])
                conf.add_section(s3)

                returned = sorted(s.name for s in conf.get_sections())
                expected = ["s1", "s2", "s3"]
                self.assertEqualDiff(returned, expected)

                # Verify that get_index returns expected value.
                exp_idx = {
                    "s1": {
                        "1p1": "11",
                        "1p2": "12",
                        "1p3": "13",
                    },
                    "s2": {
                        "2p1": "21",
                        "2p2": "22",
                        "2p3": "23",
                    },
                    "s3": {
                        "3p1": "31",
                        "3p2": "32",
                        "3p3": "33",
                    },
                }
                self.assertEqual(conf.get_index(), exp_idx)

        def test_file_read_write(self):
                """Verify that read and write works as expected for
                FileConfig.
                """

                # Verify configuration files missing state can still be loaded.
                content = """\
[first_section]
str_basic = bob cat
"""
                scpath = self.make_misc_files({ "cfg_cache": content })[0]
                conf = cfg.FileConfig(scpath, definitions=self._defs)

                # Verify target matches specified path.
                self.assertEqual(conf.target, scpath)

                self.assertEqual(conf.version, 1) # Newest version assumed.
                self.assertEqual(conf.get_property("first_section",
                    "str_basic"), "bob cat")
                portable.remove(scpath)

                # Verify configuration files with unknown sections or properties
                # can still be loaded.
                content = u"""\
[CONFIGURATION]
version = 0

[unknown_section]
unknown_property = %s
""" % TH_PACKAGE
                scpath = self.make_misc_files({ "cfg_cache": content })[0]
                conf = cfg.FileConfig(scpath, definitions=self._defs)
                self.assertEqual(conf.version, 0)
                self.assertEqual(conf.get_property("unknown_section",
                    "unknown_property"), TH_PACKAGE)
                portable.remove(scpath)

                # Verify configuration files with unknown versions can still be
                # loaded.
                content = u"""\
[CONFIGURATION]
version = 2

[new_section]
new_property = %s
""" % TH_PACKAGE
                scpath = self.make_misc_files({ "cfg_cache": content })[0]
                conf = cfg.FileConfig(scpath, definitions=self._defs)
                self.assertEqual(conf.version, 2)
                self.assertEqual(conf.get_property("new_section",
                    "new_property"), TH_PACKAGE)
                portable.remove(scpath)

                # Verify read and write of sample files.
                for ver, content in self._initial_files.iteritems():
                        scpath = self.make_misc_files({
                            "cfg_cache": content })[0]

                        # Verify verison of content is auto detected and that
                        # initial state matches file.
                        conf = cfg.FileConfig(scpath, definitions=self._defs)
                        self._verify_initial_state(conf, ver)

                        # Cleanup.
                        portable.remove(scpath)

                # Verify that write only happens when needed and that perms are
                # retained on existing configuration files.
                scpath = self.make_misc_files({ "cfg_cache": "" })[0]
                portable.remove(scpath)

                # Verify that configuration files that do not already exist will
                # be created if the file doesn't exist, even if nothing has
                # changed since init.
                conf = cfg.FileConfig(scpath, definitions=self._defs, version=0)
                self.assertTrue(not os.path.isfile(scpath))
                conf.write()

                # Now the file should exist and have specific perms.
                bstat = os.stat(scpath)
                self.assertEqual(stat.S_IMODE(bstat.st_mode),
                    misc.PKG_FILE_MODE)

                # Calling write again shouldn't do anything since nothing
                # has changed since the last write.
                conf.write()
                astat = os.stat(scpath)
                self.assertEqual(bstat.st_mtime, astat.st_mtime)

                # Calling write after init shouldn't do anything since
                # nothing has changed since init.
                conf = cfg.FileConfig(scpath, definitions=self._defs)
                astat = os.stat(scpath)
                self.assertEqual(bstat.st_mtime, astat.st_mtime)

                # Set a property; write should happen this time.
                conf.set_property("first_section", "int_basic", 255)
                conf.write()
                astat = os.stat(scpath)
                self.assertNotEqual(bstat.st_mtime, astat.st_mtime)
                bstat = astat

                # Verify that set value was written along with the rest
                # of the initial state.
                conf = cfg.FileConfig(scpath, definitions=self._defs)
                exp_state = copy.deepcopy(self._initial_state[0])
                exp_state["first_section"]["int_basic"] = 255
                self._verify_initial_state(conf, 0, exp_state=exp_state)

                # If overrides are set during init, the file should get
                # written.
                overrides = {
                    "first_section": {
                        "int_basic": 0,
                    },
                }
                conf = cfg.FileConfig(scpath, definitions=self._defs,
                    overrides=overrides)
                conf.write()
                astat = os.stat(scpath)
                self.assertNotEqual(bstat.st_mtime, astat.st_mtime)
                bstat = astat

                # Verify overrides were written.
                conf = cfg.FileConfig(scpath, definitions=self._defs,
                    overrides=overrides)
                exp_state = copy.deepcopy(self._initial_state[0])
                exp_state["first_section"]["int_basic"] = 0
                self._verify_initial_state(conf, 0, exp_state=exp_state)

                # Verify that user-specified permissions are retained.
                os.chmod(scpath, 0777)
                conf.set_property("first_section", "int_basic", 16384)
                conf.write()
                astat = os.stat(scpath)
                self.assertEqual(stat.S_IMODE(astat.st_mode), 0777)
                self.assertNotEqual(bstat.st_mtime, astat.st_mtime)
                bstat = astat

                if portable.util.get_canonical_os_type() != "unix":
                        return

                portable.chown(scpath, 65534, 65534)
                conf.set_property("first_section", "int_basic", 0)
                conf.write()
                astat = os.stat(scpath)
                self.assertEqual(astat.st_uid, 65534)
                self.assertEqual(astat.st_gid, 65534)

        def test_get_modify_properties(self):
                """Verify that get_property, set_property, get_properties,
                set_properties, add_property_value, remove_property_value,
                and remove_property work as expected.
                """

                # Verify no definitions, overrides, or version.
                conf = cfg.Config()

                # Verify unknown section causes exception.
                self.assertRaises(cfg.UnknownSectionError,
                    conf.get_section, "section")
                self.assertRaises(cfg.UnknownPropertyError,
                    conf.get_property, "section", "property")

                # Verify set automatically creates unknown sections and
                # properties.
                conf.set_property("section", "bool_prop", False)

                secobj = conf.get_section("section")
                self.assertEqual(secobj.name, "section")
                self.assert_(isinstance(secobj, cfg.PropertySection))

                conf.set_properties({
                    "section": {
                        "int_prop": 16384,
                        "str_prop": "bob cat",
                    },
                })

                # Unknown properties when set are assumed to be a string
                # and forcibly cast as one if they are int, bool, etc.
                self.assertEqual(conf.get_property("section", "bool_prop"),
                    "False")
                self.assertEqual(conf.get_property("section", "int_prop"),
                    "16384")
                self.assertEqual(conf.get_property("section", "str_prop"),
                    "bob cat")

                # Verify that get_properties returns expected value.
                secobj = conf.get_section("section")
                props = [
                    secobj.get_property(p)
                    for p in ("bool_prop", "str_prop", "int_prop")
                ]
                expected = [(secobj, props)]
                returned = []
                for sec, secprops in conf.get_properties():
                        returned.append((sec, [p for p in secprops]))
                self.assertEqual(expected, returned)

                # Verify unknown property causes exception.
                self.assertRaises(cfg.UnknownPropertyError,
                    conf.get_property, "section", "property")

                # Verify with no overrides and with version.
                conf = cfg.Config(definitions=self._defs, version=0)

                # Verify that get returns set value when defaults are present.
                self.assertEqual(conf.get_property("first_section",
                    "str_default"), TH_PACKAGE)
                conf.set_property("first_section", "str_default", "lynx")
                self.assertEqual(conf.get_property("first_section",
                    "str_default"), "lynx")

                # Verify that Config's set_property passes through the expected
                # exception when the value given is not valid for the property.
                self.assertRaises(cfg.InvalidPropertyValueError,
                    conf.set_property, "first_section", "int_basic", "badval")

                # Verify that setting a property that doesn't currently exist,
                # but for which there is a matching definition, will be created
                # using the definition.
                conf = cfg.Config(definitions=self._defs, version=0)

                # If the section is removed, then setting any property for
                # that section should cause all properties defined for that
                # section to be set with their default values using the
                # types from the definition.
                conf.remove_section("first_section")
                conf.set_property("first_section", "bool_basic", False)
                self.assertRaises(cfg.InvalidPropertyValueError,
                    conf.set_property, "first_section", "bool_basic", 255)

                conf.set_property("first_section", "list_basic", [])
                self.assertRaises(cfg.InvalidPropertyValueError,
                    conf.set_property, "first_section", "list_basic", 255)

                self.assertEqualDiff(
                    sorted(conf.get_index()["first_section"].keys()),
                    sorted(self._initial_state[0]["first_section"].keys()))

                # Verify that add_property_value and remove_property_value
                # raise exceptions when used with non-list properties.
                self.assertRaises(cfg.PropertyMultiValueError,
                    conf.add_property_value, "first_section", "bool_basic",
                    True)
                self.assertRaises(cfg.PropertyMultiValueError,
                    conf.remove_property_value, "first_section", "bool_basic",
                    True)
        
                # Verify that add_property_value and remove_property_value
                # work as expected for list properties.
                conf.add_property_value("first_section", "list_noneallowed",
                    "always")
                self.assertEqual(conf.get_property("first_section",
                    "list_noneallowed"), ["always"])

                conf.remove_property_value("first_section", "list_noneallowed",
                    "always")
                self.assertEqual(conf.get_property("first_section",
                    "list_noneallowed"), [])

                # Verify that remove_property_value will raise expected error
                # if property value doesn't exist.
                self.assertRaises(cfg.UnknownPropertyValueError,
                    conf.remove_property_value, "first_section",
                    "list_noneallowed", "nosuchvalue")

                # Remove the property for following tests.
                conf.remove_property("first_section", "list_noneallowed")

                # Verify that attempting to remove a property that doesn't exist
                # will raise the expected exception.
                self.assertRaises(cfg.UnknownPropertyError,
                    conf.remove_property, "first_section", "list_noneallowed")

                # Verify that add_property_value will automatically create
                # properties, just as set_property does, if needed.
                conf.add_property_value("first_section", "list_noneallowed",
                    "always")
                self.assertEqual(conf.get_property("first_section",
                    "list_noneallowed"), ["always"])

                # Verify that add_property_value will reject invalid values
                # just as set_property does.
                self.assertRaises(cfg.InvalidPropertyValueError,
                    conf.add_property_value, "first_section",
                        "list_noneallowed", "notallowed")

                # Verify that attempting to remove a property in a section that
                # doesn't exist fails as expected.
                conf.remove_section("first_section")
                self.assertRaises(cfg.UnknownPropertyError,
                    conf.remove_property, "first_section", "list_noneallowed")

                # Verify that attempting to remove a property value in for a
                # property in a section that doesn't exist fails as expected.
                self.assertRaises(cfg.UnknownPropertyError,
                    conf.remove_property_value, "first_section",
                    "list_noneallowed", "always")

                # Verify that setting a property for which a property section
                # template exists, but an instance of the section does not yet
                # exist, works as expected.
                conf = cfg.Config(definitions=self._templated_defs, version=0)
                conf.remove_section("facet")
                conf.set_property("facet", "facet.devel", True)
                self.assertEqual(conf.get_property("facet", "facet.devel"),
                    True)

                conf = cfg.Config(definitions=self._templated_defs, version=1)
                self.assertEqualDiff([], conf.get_index().keys())

                conf.set_property("authority_example.com", "prefix",
                    "example.com")
                self.assertEqual(conf.get_property("authority_example.com",
                    "prefix"), "example.com")


class TestSMFConfig(_TestConfigBase):
        """Class to test the functionality of the pkg.config SMF
        configuration classes.
        """

        _initial_files = {
            0: u"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name=':pkg-config'>
<service
        name='application/pkg/configuration'
        type='service'
        version='1'>
        <property_group name='first_section' type='application'>
                <propval name='bool_basic' type='boolean' value='false' />
                <propval name='bool_default' type='boolean' value='true' />
                <propval name='int_basic' type='integer' value='0' />
                <propval name='publisher_basic' type='astring' value='' />
                <propval name='publisher_default' type='astring' value='example.com' />
                <propval name='str_basic' type='astring' value='' />
                <propval name='str_escape' type='astring' value=";, &amp;, (, ), |, ^, &lt;, &gt;, nl&#10;, sp , tab&#9;, bs\\, &apos;, &quot;, `" />
                <propval name='str_default' type='astring' value='%(uni_txt)s' />
                <property name='list_basic' type='astring'/>
                <property name='list_default' type='ustring'>
                        <ustring_list>
                                <value_node value="%(uni_txt)s" />
                                <value_node value="bob cat" />
                                <value_node value="profit" />
                        </ustring_list>
                </property>
                <property name='list_allowed' type='ustring'>
                        <ustring_list>
                                <value_node value='builtin' />
                        </ustring_list>
                </property>
                <property name='list_noneallowed' type='ustring' />
        </property_group>
        <property_group name='second_section' type='application'>
                <propval name='uri_basic' type='ustring' value='' />
                <propval name='uri_default' type='ustring' value='http://example.com/' />
                <propval name='uuid_basic' type='astring' value='' />
                <propval name='uuid_default' type='astring' value='16fd2706-8baf-433b-82eb-8c7fada847da' />
                <property name='simple_list_basic' type='ustring' />
                <property name='simple_list_default' type='ustring'>
                        <ustring_list>
                                <value_node value='bar' />
                                <value_node value='foo' />
                                <value_node value='%(uni_txt)s' />
                        </ustring_list>
                </property>
                <property name='simple_list_allowed' type='ustring'>
                        <ustring_list>
                                <value_node value='builtin' />
                        </ustring_list>
                </property>
                <property name='simple_list_noneallowed' type='ustring' />
                <property name='urilist_basic' type='uri' />
                <property name='urilist_default' type='uri'>
                        <uri_list>
                                <value_node value='http://example.com/' />
                                <value_node value='file:/example/path' />
                        </uri_list>
                </property>
        </property_group>
        <stability value='Unstable' />
</service>
</service_bundle>
""" % { "uni_txt": TH_PACKAGE },
            1: """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name=':pkg-config'>
<service
        name='application/pkg/configuration'
        type='service'
        version='1'>
        <property_group name='first_section' type='application'>
                <propval name='bool_basic' type='boolean' value='false' />
                <propval name='str_basic' type='astring' value='' />
        </property_group>
        <stability value='Unstable' />
</service>
</service_bundle>
""",
        }

        # Manifest and state data for testing unknown sections and properties.
        __undef_mfst = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name=':pkg-config'>
<service
        name='application/pkg/configuration'
        type='service'
        version='1'>
        <property_group name='unknown_section1' type='application'>
                <propval name='unknown_prop11' type='astring' value='foo11' />
                <propval name='unknown_prop12' type='astring' value='foo12' />
        </property_group>
        <property_group name='unknown_section2' type='application'>
                <propval name='unknown_prop21' type='astring' value='foo21' />
                <propval name='unknown_prop22' type='astring' value='foo22' />
        </property_group>
        <stability value='Unstable' />
</service>
</service_bundle>
"""
        __undef_state = {
            "unknown_section1": {
                "unknown_prop11": "foo11",
                "unknown_prop12": "foo12",
            },
            "unknown_section2": {
                "unknown_prop21": "foo21",
                "unknown_prop22": "foo22",
            },
        }

        # "Calgon, take me away!"
        # Torture data for SMFConfig parsing of values that require escaping.
        __escape_mfst = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE service_bundle SYSTEM "/usr/share/lib/xml/dtd/service_bundle.dtd.1">
<service_bundle type='manifest' name=':pkg-config'>
<service
        name='application/pkg/configuration'
        type='service'
        version='1'>
        <property_group name='escaped' type='application'>
                <propval name='one_slash' type='astring' value='\\' />
                <propval name='two_slash' type='astring' value='\\\\' />
                <propval name='one_slash_embed' type='astring' value='\\&#10;\\' />
                <propval name='two_slash_embed' type='astring' value='\\\\&#10;\\\\' />
                <propval name='end_one_slash' type='astring' value='foo\\' />
                <propval name='end_two_slash' type='astring' value='foo\\\\' />
                <propval name='end_embed_one_slash' type='astring' value='foo\\&#10;\\' />
                <propval name='end_embed_two_slash' type='astring' value='foo\\\\&#10;\\\\' />
                <propval name='multi_line' type='astring' value='foo\\&#10;&#10;\\&#10;&#10;\\&#10;\\' />
                <property name='list_multi_line' type='ustring'>
                        <ustring_list>
                                <value_node value="foo\\&#10;&#10;\\&#10;&#10;\\&#10;\\" />
                                <value_node value=";, &amp;, (, ), |, ^, &lt;, &gt;, nl&#10;, sp , tab&#9;, bs\\, &apos;, &quot;, `" />
                                <value_node value="Eat at Joe&apos;s!&#10;&#9;Really; eat at Joe&apos;s please." />
                        </ustring_list>
                </property>
        </property_group>
        <stability value='Unstable' />
</service>
</service_bundle>
"""

        __escape_defs = {
            3: [cfg.PropertySection("escaped", properties=[
                    cfg.Property("one_slash", default="\\"),
                    cfg.Property("two_slash", default="\\\\"),
                    cfg.Property("one_slash_embed", default="\\\n\\"),
                    cfg.Property("two_slash_embed", default="\\\\\n\\\\"),
                    cfg.Property("end_embed_one_slash", default="foo\\\n\\"),
                    cfg.Property("end_one_slash", default="foo\\"),
                    cfg.Property("end_two_slash", default="foo\\\\"),
                    cfg.Property("end_embed_two_slash", default="foo\\\\\n\\\\"),
                    cfg.Property("multi_line", default="foo\\\n\n\\\n\n\\\n\\"),
                    cfg.PropList("list_multi_line", default=[
                        "foo\\\n\n\\\n\n\\\n\\",
                        ";, &, (, ), |, ^, <, >, nl\n, sp , tab\t, bs\\, ', \", `",
                        "Eat at Joe's!\n\tReally; eat at Joe's please."
                    ])
            ])]
        }

        __escape_state = {
            "escaped": {
                "one_slash": "\\",
                "two_slash": "\\\\",
                "one_slash_embed": "\\\n\\",
                "two_slash_embed": "\\\\\n\\\\",
                "end_embed_one_slash": "foo\\\n\\",
                "end_one_slash": "foo\\",
                "end_two_slash": "foo\\\\",
                "end_embed_two_slash": "foo\\\\\n\\\\",
                "multi_line": "foo\\\n\n\\\n\n\\\n\\",
                "list_multi_line": [
                    "foo\\\n\n\\\n\n\\\n\\",
                    ";, &, (, ), |, ^, <, >, nl\n, sp , tab\t, bs\\, ', \", `",
                    "Eat at Joe's!\n\tReally; eat at Joe's please."
                ],
            }
        }

        def setUp(self):
                """Prepare the tests."""
                _TestConfigBase.setUp(self)
                self.__configd = None

        def __create_smf_repo(self, manifest):
                """Create a new SMF repository importing only the specified
                manifest file."""

                SVCCFG_PATH = "/usr/sbin/svccfg"

                rdbname = tempfile.mktemp(prefix="repo-", suffix=".db", dir="")
                sc_repo_filename = self.make_misc_files({ rdbname: '' })[0]
                portable.remove(sc_repo_filename)

                pdir = os.path.dirname(sc_repo_filename)
                hndl = self.cmdline_run(
                    "SVCCFG_REPOSITORY=%(sc_repo_filename)s "
                    "%(SVCCFG_PATH)s import %(manifest)s" % locals(),
                    coverage=False, handle=True)
                assert hndl is not None
                hndl.wait()

                return sc_repo_filename

        def __poll_process(self, hndl, pfile):
                try:
                        begintime = time.time()

                        sleeptime = 0.0
                        check_interval = 0.20
                        contact = False
                        while (time.time() - begintime) <= 10.0:
                                hndl.poll()
                                time.sleep(check_interval)
                                # The door file will exist but will fail
                                # os.path.isfile() check if the process
                                # has launched.
                                if os.path.exists(pfile) and \
                                    not os.path.isfile(pfile):
                                        contact = True
                                        break

                        if contact == False:
                                raise RuntimeError("Process did not launch "
                                    "successfully.")
                except (KeyboardInterrupt, RuntimeError), e:
                        try:
                                hndl.kill()
                        finally:
                                self.debug(str(e))
                        raise

        def __start_configd(self, sc_repo_filename):
                """Start svc.configd for the specified SMF repository."""

                assert not self.__configd

                SC_REPO_SERVER = "/lib/svc/bin/svc.configd"

                doorname = tempfile.mktemp(prefix="repo-door-", dir="")
                sc_repo_doorpath = self.make_misc_files({ doorname: "" })[0]
                os.chmod(sc_repo_doorpath, 0600)

                hndl = self.cmdline_run("%(SC_REPO_SERVER)s "
                    "-d %(sc_repo_doorpath)s -r %(sc_repo_filename)s" %
                    locals(), coverage=False, handle=True)
                assert hndl is not None
                self.__configd = hndl
                self.__poll_process(hndl, sc_repo_doorpath)
                self.__starttime = time.time()
                return sc_repo_doorpath

        def __verify_ex_stringify(self, ex):
                encs = str(ex)
                self.assertNotEqual(len(encs), 0)
                unis = unicode(ex)
                self.assertNotEqual(len(unis), 0)
                self.assertEqualDiff(encs, unis.encode("utf-8"))

        def test_exceptions(self):
                """Verify that exception classes can be initialized as expected,
                and when stringified return a non-zero-length string.
                """

                # Verify the expected behavior of all SMF exception classes.
                for excls in (cfg.SMFReadError, cfg.SMFWriteError):
                        # Verify that exception can't be created without
                        # specifying svc_fmri and errmsg.
                        self.assertRaises(AssertionError, excls,
                            None, None)

                        # Verify that the properties specified at init can
                        # be accessed.
                        svc_fmri = "svc:/application/pkg/configuration"
                        errmsg = "error message"
                        ex = excls(svc_fmri, errmsg)
                        self.assertEqual(ex.fmri, svc_fmri)
                        self.assertEqual(ex.errmsg, errmsg)
                        self.__verify_ex_stringify(ex)

                # Verify that exception can't be created without specifying
                # section.
                excls = cfg.SMFInvalidSectionNameError
                self.assertRaises(AssertionError, excls, None)

                # Verify that exception can be created with just section and
                # that expected value is set.  In addition, verify that the
                # stringified form or unicode object is equal and not zero-
                # length.
                ex1 = excls("section")
                self.assertEqual(ex1.section, "section")
                self.__verify_ex_stringify(ex1)

                # Verify that exception can't be created without specifying
                # prop.
                excls = cfg.SMFInvalidPropertyNameError
                self.assertRaises(AssertionError, excls, None)

                # Verify that exception can be created with just prop and that 
                # expected value is set.  In addition, verify that the
                # stringified form or unicode object is equal and not zero-
                # length.
                ex1 = excls("prop")
                self.assertEqual(ex1.prop, "prop")
                self.__verify_ex_stringify(ex1)

        def test_add_set_property(self):
                """Verify that add_section and set_property works as expected.
                (SMFConfig enforces additional restrictions on naming.)
                """

                svc_fmri = "svc:/application/pkg/configuration"

                rfiles = []
                mname = "smf-manifest-naming.xml"
                mpath = self.make_misc_files({ mname: self.__undef_mfst })[0]
                rfiles.append(mpath)

                rpath = self.__create_smf_repo(mpath)
                rfiles.append(rpath)

                dpath = self.__start_configd(rpath)
                rfiles.append(dpath)

                # Retrieve configuration data from SMF.
                try:
                        conf = cfg.SMFConfig(svc_fmri,
                            doorpath=dpath)
                finally:
                        # Removing the files stops configd.
                        self.__configd = None
                        while rfiles:
                                portable.remove(rfiles[-1])
                                rfiles.pop()

                # Verify that SMFConfig's add_section passes through the
                # expected exception when the name of the property section
                # is not valid for SMF.
                invalid_names = ("1startnum", "has.stopnocomma",
                    " startspace")
                for sname in invalid_names:
                        section = cfg.PropertySection(sname)
                        self.assertRaises(cfg.SMFInvalidSectionNameError,
                            conf.add_section, section)

                # Verify that SMFConfig's set_property passes through the
                # expected exception when the name of the property is not
                # valid for SMF.
                for pname in invalid_names:
                        self.assertRaises(cfg.SMFInvalidPropertyNameError,
                            conf.set_property, "section", pname, "value")

        def test_read(self):
                """Verify that read works as expected for SMFConfig."""

                # Verify read and write of sample configuration.
                svc_fmri = "svc:/application/pkg/configuration"

                def cleanup():
                        self.__configd = None
                        while rfiles:
                                portable.remove(rfiles[-1])
                                rfiles.pop()

                rfiles = []
                def test_mfst(svc_fmri, ver, mfst_content, defs,
                    exp_state=None):
                        mname = "smf-manifest-%d.xml" % ver 
                        mpath = self.make_misc_files({ mname: mfst_content })[0]
                        rfiles.append(mpath)

                        rpath = self.__create_smf_repo(mpath)
                        rfiles.append(rpath)

                        dpath = self.__start_configd(rpath)
                        rfiles.append(dpath)

                        # Retrieve configuration data from SMF.
                        try:
                                conf = cfg.SMFConfig(svc_fmri,
                                    definitions=defs,
                                    doorpath=dpath,
                                    version=ver)
                        finally:
                                cleanup()

                        # Verify initial state matches expected.
                        ver_defs = defs.get(ver, {})
                        self._verify_initial_state(conf, ver, ver_defs,
                            exp_state=exp_state)

                        # Verify SMFConfig raises exception if write() is
                        # attempted (not currently supported).
                        self.assertRaises(cfg.SMFWriteError, conf.write)

                for ver, mfst_content in self._initial_files.iteritems():
                        test_mfst(svc_fmri, ver, mfst_content, self._defs)

                # Verify configuration data with unknown sections or properties
                # can be loaded.
                test_mfst(svc_fmri, 2, self.__undef_mfst, {},
                    exp_state=self.__undef_state)

                # Verify configuration data that requires extensive escaping
                # during parsing can be loaded.
                test_mfst(svc_fmri, 3, self.__escape_mfst, self.__escape_defs,
                    exp_state=self.__escape_state)

                # Verify that an SMFReadError is raised if the configuration
                # data cannot be read from SMF.  (This should fail since 
                self.assertRaises(cfg.SMFReadError, test_mfst,
                    "svc:/nosuchservice", 4, self.__escape_mfst, {})


if __name__ == "__main__":
        unittest.main()
