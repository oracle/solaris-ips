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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import itertools
import datetime
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)

import pkg5unittest

import pkg.variant as variant

class TestVariants(pkg5unittest.Pkg5TestCase):

        def __check_equal(self, v1, v2):
                self.assertEqual(sorted(v1.keys()), sorted(v2.keys()))
                for k in v1:
                        self.assertEqual(sorted(v1[k]), sorted(v2[k]))
        
        def test_1(self):
                """Test basic functionality of variants."""
                v1 = variant.Variants(dict([(1, ["a"]), (3, ["b"])]))
                v2 = variant.Variants(dict([(1, ["a"]), (4, ["b"])]))
                v3 = variant.Variants(dict([(1, ["a"]), (3, ["c"])]))
                v1_v2_merge = variant.Variants(dict([(1, ["a"]), (3, ["b"]),
                    (4, ["b"])]))
                v1_v3_merge = variant.Variants(dict([(1, ["a"]),
                    (3, ["b", "c"])]))

                self.assertEqual(v1.issubset(v2), False, )
                self.assertEqual(v1.issubset(v1_v2_merge), True)
                self.assertEqual(v1.issubset(v1_v3_merge), True)
                self.assertEqual(v1.difference(v3), dict([(3, set(["b"]))]))
                self.assertEqual(v1.difference(v1_v3_merge), {})
                v2.merge(v1)
                self.__check_equal(v2, v1_v2_merge)
                v1.merge(v3)
                self.__check_equal(v1, v1_v3_merge)
                
