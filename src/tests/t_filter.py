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

import unittest
import sys
import pkg.client.filter as filter
import pkg.actions as actions


class TestFilter(unittest.TestCase):
        def setUp(self):
		self.actionstr = """\
		file path=/usr/bin/ls arch=i386 debug=true
		file path=/usr/bin/ls arch=i386 debug=false
		file path=/usr/bin/ls arch=sparc debug=true
		file path=/usr/bin/ls arch=sparc debug=false
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
		#print "\n------"
		for f in in_filters:
			expr, comp_expr = filter.compile_filter(f)
			filters.append((expr, comp_expr))

		for a in self.actions:
			d = a.attrs
			res = filter.apply_filters(a, filters)
			#print "%-5s" % res, d
			if res:
				match += 1
			else:
				nomatch += 1
		#print "------%d %d\n" % (match, nomatch)
		return match

	def doFilterStr(self, in_filters):
		filters = []
		outstr = ""

		for f in in_filters:
			expr, comp_expr = filter.compile_filter(f)
			filters.append((expr, comp_expr))

		for a in self.actions:
			d = a.attrs
			res = filter.apply_filters(a, filters)
			outstr += "%-5s %s" % (res, str(d))

		return outstr

	def test_01_debug_i386(self):
		""" ASSERT: arch=i386 & debug=true filters work """
		self.assertEqual(
		    self.doFilter([ "arch=i386 & debug=true" ]), 6)

	def test_02_nondebug_i386(self):
		""" ASSERT: arch=i386 & debug=false filters work """
		self.assertEqual(
		    self.doFilter([ "arch=i386 & debug=false" ]), 6)

	def test_03_i386(self):
		""" ASSERT: arch=i386 filters work """
		self.assertEqual(
		    self.doFilter([ "arch=i386" ]), 7)

	def test_04_sparc(self):
		""" ASSERT: arch=sparc filters work """
		self.assertEqual(
		    self.doFilter([ "arch=sparc" ]), 7)

	def test_05_doc(self):
		""" ASSERT: doc=true filters work """
		self.assertEqual(
		    self.doFilter([ "doc=true" ]), 9)

	def test_06_doc(self):
		""" ASSERT: doc=false filters work """
		self.assertEqual(
		    self.doFilter([ "doc=false" ]), 5)

	def test_07_or(self):
		""" ASSERT: OR filters work """
		self.assertEqual(
		    self.doFilter([ "locale=sv | locale=fr" ]), 7)

	def test_08_and_or(self):
		""" ASSERT: complex filters work """
		self.assertEqual(
		    self.doFilter([ "arch=sparc & debug=false & (locale=sv | locale=fr)" ]), 4)

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

if __name__ == "__main__":
        unittest.main()
