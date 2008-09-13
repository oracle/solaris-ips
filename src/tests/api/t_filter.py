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
import pkg.client.filter as filter
import pkg.actions as actions

import sys
import os

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestFilter(pkg5unittest.Pkg5TestCase):
        def setUp(self):
                self.actionstr = """\
                file path=/usr/bin/ls arch=i386 debug=true
                file path=/usr/bin/ls arch=i386 debug=false
                file path=/usr/bin/ls arch=sparc debug=true
                file path=/usr/bin/ls arch=sparc debug=false
                file path=/usr/bin/hostname arch=386 version=0.9
                file path=/usr/bin/hostname arch=sparc version=9
                file path=/usr/bin/hostid arch=386 version=0.9.9
                file path=/usr/bin/hostid arch=sparc version=9.9
                file path=/usr/sbin/6to4relay arch=386 version=0.a6.b5.c4.d3.e2.f1
                file path=/usr/sbin/6to4relay arch=sparcv9 version=0.6.5.4.3.2.1
                file path=/usr/bin/i386 386=true 0.i.3.8.6=cpuarch
                file path=/usr/bin/sparc 386=false 0.9.9=cpuarch
                file path=/var/svc/manifest/intrd.xml opensolaris.zone=global
                file path=/path/to/french/text doc=true locale=fr
                file path=/path/to/swedish/text doc=true locale=sv
                file path=/path/to/english/text doc=true locale=en
                file path=/path/to/us-english/text doc=true locale=en_US"""

                self.actions = [
                    actions.fromstr(s.strip())
                    for s in self.actionstr.splitlines()
                ]

        def doFilter(self, in_filters):
                filters = []
                match = 0
                nomatch = 0
                for f_entry in in_filters:
                        expr, comp_expr = filter.compile_filter(f_entry)
                        filters.append((expr, comp_expr))

                for a_entry in self.actions:
                        res = filter.apply_filters(a_entry, filters)
                        if res:
                                match += 1
                        else:
                                nomatch += 1
                return match

        def doFilterStr(self, in_filters):
                filters = []
                outstr = ""

                for f_entry in in_filters:
                        expr, comp_expr = filter.compile_filter(f_entry)
                        filters.append((expr, comp_expr))

                for a_entry in self.actions:
                        d_attrs = a_entry.attrs
                        res = filter.apply_filters(a_entry, filters)
                        outstr += "%-5s %s" % (res, str(d_attrs))

                return outstr

        def test_01_debug_i386(self):
                """ ASSERT: arch=i386 & debug=true filters work """
                self.assertEqual(
                    self.doFilter([ "arch=i386 & debug=true" ]), 8)

        def test_02_nondebug_i386(self):
                """ ASSERT: arch=i386 & debug=false filters work """
                self.assertEqual(
                    self.doFilter([ "arch=i386 & debug=false" ]), 8)

        def test_03_i386(self):
                """ ASSERT: arch=i386 filters work """
                self.assertEqual(
                    self.doFilter([ "arch=i386" ]), 9)

        def test_04_sparc(self):
                """ ASSERT: arch=sparc filters work """
                self.assertEqual(
                    self.doFilter([ "arch=sparc" ]), 11)

        def test_05_doc(self):
                """ ASSERT: doc=true filters work """
                self.assertEqual(
                    self.doFilter([ "doc=true" ]), 17)

        def test_06_doc(self):
                """ ASSERT: doc=false filters work """
                self.assertEqual(
                    self.doFilter([ "doc=false" ]), 13)

        def test_07_or(self):
                """ ASSERT: OR filters work """
                self.assertEqual(
                    self.doFilter([ "locale=sv | locale=fr" ]), 15)

        def test_08_and_or(self):
                """ ASSERT: complex filters work """
                self.assertEqual(
                    self.doFilter([
                        "arch=sparc & debug=false & (locale=sv | locale=fr)"
                        ]), 8)

        def test_09_multiple(self):
                """ ASSERT: a list of multiple filters is possible """
                self.assertNotEqual(
                    self.doFilter([ "arch=i386", "debug=false" ]),
                    self.doFilter([ "arch=i386" ]))

        def test_10_multiple(self):
                """ ASSERT: multiple filters is the same as ANDing """

                self.assertEqual(
                    self.doFilterStr([ "arch=i386", "debug=false" ]),
                    self.doFilterStr([ "arch=i386 & debug=false" ]))

        def test_11_numval(self):
                """ ASSERT: filters with numeric values work """
                self.assertEqual(
                    self.doFilter([ "arch=386" ]), 10)

        def test_12_fracval(self):
                """ ASSERT: filters with fractional numeric values work """
                self.assertEqual(
                    self.doFilter([ "version=0.9" ]), 12)

        def test_13_fracval_and_numval(self):
                """ ASSERT: filters with fractional numeric values ANDed with filters with numeric values work """
                self.assertEqual(
                    self.doFilter([ "version=0.9 & arch=386" ]), 8)

        def test_14_fracval_and_textval_(self):
                """ ASSERT: filters with fractional numeric values ANDed with filters with text values work """
                self.assertEqual(
                    self.doFilter([ "version=0.9 & arch=sparc" ]), 9)

        def test_15_numval_and_textval(self):
                """ ASSERT: filters with numeric ANDed with filters with text value work """
                self.assertEqual(
                    self.doFilter([ "version=9 & arch=sparc" ]), 10)

        def test_16_multinumval(self):
                """ ASSERT: filters with multi-component numeric values work """
                self.assertEqual(
                    self.doFilter([ "version=0.9.9" ]), 12)

        def test_17_multinumval_and_numval(self):
                """ ASSERT: filters with multi-component numeric values ANDed with filters with numeric values work """
                self.assertEqual(
                    self.doFilter([ "version=0.6.5.4.3.2.1 & arch=386" ]), 7)

        def test_18_multinumval_and_textval(self):
                """ ASSERT: filters with multi-component numeric values ANDed with filters with text values work """
                self.assertEqual(
                    self.doFilter([ "version=0.9.9 & arch=sparc" ]), 9)

        def test_19_multinumtextval(self):
                """ ASSERT: filters with multi-component numeric and text values work """
                self.assertEqual(
                    self.doFilter([ "version=0.a6.b5.c4.d3.e2.f1" ]), 12)

        def test_20_multinumtextval_and_numval(self):
                """ ASSERT: filters with multi-component numeric and text values ANDed with filters with numeric values work """
                self.assertEqual(
                    self.doFilter([ "version=0.a6.b5.c4.d3.e2.f1 & arch=386" ]), 8)

        def test_21_multinumtextval_and_textval(self):
                """ ASSERT: filters with multi-component numeric and text values ANDed with filters with text values work """
                self.assertEqual(
                    self.doFilter([ "version=0.a6.b5.c4.d3.e2.f1 & arch=sparcv9" ]), 7)

        def test_22_numfilter(self):
                """ ASSERT: numeric filters with text values work """
                self.assertEqual(
                    self.doFilter([ "386=true" ]), 16)

        def test_23_multinumfilter(self):
                """ ASSERT: multi-component numeric filters with text values work """
                self.assertEqual(
                    self.doFilter([ "0.9.9=foobar" ]), 16)

        def test_24_multinumtextfilter(self):
                """ ASSERT: multi-component numeric and text filters with text values work """
                self.assertEqual(
                    self.doFilter([ "0.i.3.8.6=foobar" ]), 16)

        def test_25_multinumfilter_complex(self):
                """ ASSERT: multi-component numeric complex filters work """
                self.assertEqual(
                    self.doFilter([
                        "version=0.9 & (0.i.3.8.6=cpuarch | 0.9.9=foobar) | version=0.a6.b5.c4.d3.e2.f1"
                        ]), 13)

if __name__ == "__main__":
        unittest.main()
