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
# Copyright (c) 2014, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import unicode_literals
from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import six
import unittest
from six.moves import range

try:
        import pkg.sha512_t as sha512_t
        sha512_supported = True
except ImportError:
        sha512_supported = False

class TestPkgSha(pkg5unittest.Pkg5TestCase):
        """A class tests the sha512_t module."""

        def test_basic(self):
                if not sha512_supported:
                        return

                # The expected values are from the examples:
                # http://csrc.nist.gov/groups/ST/toolkit/documents/Examples/SHA512_224.pdf
                # http://csrc.nist.gov/groups/ST/toolkit/documents/Examples/SHA512_256.pdf

                # Test SHA512/256
                # Test hexdigest()
                a = sha512_t.SHA512_t()
                a.update(b"abc")
                expected = "53048e2681941ef99b2e29b76b4c7dabe4c2d0c634fc6d46e0e2f13107e7af23"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                a = sha512_t.SHA512_t(b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu")
                expected = "3928e184fb8690f840da3988121d31be65cb9d3ef83ee6146feac861e19b563a"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                # Test the length of the output of hexdigest()
                output = len(sha512_t.SHA512_t(b"0.861687995815").hexdigest())
                self.assertEqualDiff(64, output)
                output = len(sha512_t.SHA512_t(b"0.861687995815", 224).hexdigest())
                self.assertEqualDiff(56, output)

                # Test digest()
                a = sha512_t.SHA512_t()
                a.update(b"abc")
                expected = b"S\x04\x8e&\x81\x94\x1e\xf9\x9b.)\xb7kL}\xab\xe4\xc2\xd0\xc64\xfcmF\xe0\xe2\xf11\x07\xe7\xaf#"
                output = a.digest()
                self.assertEqualDiff(expected, output)

                # Test the length of the output of digest()
                output = len(sha512_t.SHA512_t(b"0.861687995815").digest())
                self.assertEqualDiff(32, output)
                output = len(sha512_t.SHA512_t(b"0.861687995815", 224).digest())
                self.assertEqualDiff(28, output)

                # Test update()
                a = sha512_t.SHA512_t(b"a")
                a.update(b"bc")
                expected = "53048e2681941ef99b2e29b76b4c7dabe4c2d0c634fc6d46e0e2f13107e7af23"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                a = sha512_t.SHA512_t(b"a")
                a.hexdigest()
                a.digest()
                a.update(b"b")
                a.hexdigest()
                a.update(b"c")
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                # Test hash_size
                a = sha512_t.SHA512_t()
                self.assertEqualDiff("256", a.hash_size)

                # Test SHA512/224
                a = sha512_t.SHA512_t(t=224)
                a.update(b"abc")
                expected = "4634270f707b6a54daae7530460842e20e37ed265ceee9a43e8924aa"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                a = sha512_t.SHA512_t(b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu", t=224)
                expected = "23fec5bb94d60b23308192640b0c453335d664734fe40e7268674af9"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                # Test positional arguments
                a = sha512_t.SHA512_t(b"abc", 224)
                expected = "4634270f707b6a54daae7530460842e20e37ed265ceee9a43e8924aa"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                # Test keyword arguments
                a = sha512_t.SHA512_t(message=b"abc", t=224)
                expected = "4634270f707b6a54daae7530460842e20e37ed265ceee9a43e8924aa"
                output = a.hexdigest()
                self.assertEqualDiff(expected, output)

                # Test scalability
                a = sha512_t.SHA512_t()
                for i in range(1000000):
                        a.update(b"abc")
                a.hexdigest()

                # Test bad input
                self.assertRaises(TypeError, sha512_t.SHA512_t, 8)
                self.assertRaises(ValueError, sha512_t.SHA512_t, t=160)
                self.assertRaises(TypeError, sha512_t.SHA512_t.update, 8)

                if six.PY2:
                        # We allow unicode in Python 2 as hashlib does
                        a = sha512_t.SHA512_t(u"abc")
                        expected = "53048e2681941ef99b2e29b76b4c7dabe4c2d0c634fc6d46e0e2f13107e7af23"
                        output = a.hexdigest()
                        self.assertEqualDiff(expected, output)
                        # Test special unicode character
                        a = sha512_t.SHA512_t("α♭¢")
                        a.hexdigest()
                        a.update("ρ⑂☂♄øη")
                        a.hexdigest()
                else:
                        # We don't allow unicode in Python 3 as hashlib does
                        self.assertRaises(TypeError, sha512_t.SHA512_t, "str")


if __name__ == "__main__":
        unittest.main()
