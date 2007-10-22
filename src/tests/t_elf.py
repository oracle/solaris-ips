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
# fields enclosed by brackets "[[]]" replaced with your own identifying
# information: Portions Copyright [[yyyy]] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import pkg.elf as elf
import os
import unittest

class TestElf(unittest.TestCase):

	def test_is_elf_object(self):
		if os.path.exists("/usr/bin/cat"):
			self.assertEqual(elf.is_elf_object("/usr/bin/cat"),
			    True);

		if os.path.exists("/etc/motd"):
			self.assertNotEqual(elf.is_elf_object("/etc/motd"),
			    True);

		if os.path.exists("/dev/ksyms"):
			self.assertEqual(elf.is_elf_object("/dev/ksyms"),
			    True);

		self.assertRaises(OSError, elf.is_elf_object, "");

	def test_get_dynamic(self):
		if os.path.exists("/usr/bin/cat"):
			try:
				elf.get_dynamic("/usr/bin/cat")
			except:
				self.fail();

		if os.path.exists("/etc/motd"):
			self.assertRaises(RuntimeError, elf.get_dynamic,
			    "/etc/motd");

		self.assertRaises(OSError, elf.get_dynamic, "");

	def test_get_info(self):
		if os.path.exists("/usr/bin/cat"):
			try:
				elf.get_info("/usr/bin/cat")
			except:
				self.fail();

		if os.path.exists("/etc/motd"):
			self.assertRaises(RuntimeError, elf.get_info,
			    "/etc/motd");

		self.assertRaises(OSError, elf.get_info, "");
		

if __name__ == "__main__":
	unittest.main()
