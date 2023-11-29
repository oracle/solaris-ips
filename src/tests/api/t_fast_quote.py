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
# Copyright (c) 2023, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import random
import string
import unittest
from urllib.parse import quote

from pkg._misc import fast_quote, MAX_STACK_QUOTE_SIZE


class TestFastQuote(pkg5unittest.Pkg5TestCase):

    def test_basic(self):
        """Verify that fast_quote returns the same values as standard quote."""
        for i in range(1024):
            symb = chr(i)
            # verify both strings and bytes
            self.assertEqual(quote(symb), fast_quote(symb))
            self.assertEqual(quote(symb).encode(), fast_quote(symb).encode())

    def test_long(self):
        """Verify that fast_quote handles long strings as well."""
        teststr = "a" * MAX_STACK_QUOTE_SIZE * 2
        self.assertEqual(quote(teststr), fast_quote(teststr))

        teststr = "ž" * MAX_STACK_QUOTE_SIZE * 2
        self.assertEqual(quote(teststr), fast_quote(teststr))

        teststr = "こ" * MAX_STACK_QUOTE_SIZE * 2
        self.assertEqual(quote(teststr), fast_quote(teststr))

    def test_random(self):
        """Test fast_quote with string of random length and symbols."""
        for _ in range(1024):
            length = random.randrange(2048)
            teststr = "".join(random.choices(string.printable, k=length))
            self.assertEqual(quote(teststr), fast_quote(teststr))


if __name__ == "__main__":
    unittest.main()
