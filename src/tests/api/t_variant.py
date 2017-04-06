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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

import copy
from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import pkg.variant as variant

class TestVariants(pkg5unittest.Pkg5TestCase):

        def __check_equal(self, v1, v2):
                self.assertEqual(sorted(v1.keys()), sorted(v2.keys()))
                for k in v1:
                        self.assertEqual(sorted(v1[k]), sorted(v2[k]))


        def test_vct(self):
                """Test functionality of VariantCombinationTemplates."""

                vct_1 = variant.VariantCombinationTemplate(
                    dict([(1, ["a", "b", "c"]), (2, ["z", "y", "x"])]))
                self.assertEqual(vct_1[1], set(["a", "b", "c"]))
                self.assertTrue(vct_1.issubset(vct_1))
                self.assertEqual(str(vct_1), ' 1="a","b","c" 2="x","y","z"')

                vct_2 = variant.VariantCombinationTemplate(
                    dict([(1, ["a", "b"]), (2, ["z", "y"])]))
                self.assertTrue(vct_2.issubset(vct_1))
                self.assertTrue(not vct_1.issubset(vct_2))
                vct_2.merge_unknown(vct_1)
                self.assertEqual(vct_2[1], set(["a", "b"]))
                self.assertEqual(vct_2[2], set(["z", "y"]))

                vct_3 = variant.VariantCombinationTemplate(
                    dict([(1, ["a", "b", "c"])]))
                self.assertTrue(vct_3.issubset(vct_1))
                self.assertTrue(not vct_1.issubset(vct_3))
                vct_3.merge_unknown(vct_1)
                self.assertEqual(vct_1, vct_3)

                vct_3 = variant.VariantCombinationTemplate(
                    dict([(1, ["a", "b", "c"])]))
                vct_m = variant.VariantCombinationTemplate(set([]))
                vct_m.merge_values(vct_3)
                self.assertEqual(vct_m, vct_3)
                vct_m.merge_values(vct_2)
                self.assertEqual(vct_m[1], set(["a", "b", "c"]))
                self.assertEqual(vct_m[2], set(["z", "y"]))
                self.assertEqual(vct_3[1], set(["a", "b", "c"]))
                self.assertTrue(2 not in vct_3)
                vct_m.merge_values(vct_1)
                self.assertEqual(str(vct_m), ' 1="a","b","c" 2="x","y","z"')
                self.assertEqual(vct_2[1], set(["a", "b"]))
                self.assertEqual(vct_2[2], set(["z", "y"]))
                vct_m.merge_values(vct_2)
                self.assertEqual(str(vct_m), ' 1="a","b","c" 2="x","y","z"')

        def test_variant_combinations(self):
                """Test functionality of VariantCombinations."""

                vct_1 = variant.VariantCombinationTemplate(
                    dict([(1, ["a", "b", "c"]), (2, ["z", "y", "x"])]))
                vct_2 = variant.VariantCombinationTemplate(
                    dict([(10, ["l", "m", "n"]), (20, ["p", "q", "r"])]))
                vct_3 = variant.VariantCombinationTemplate(
                    dict([(1, ["a"]), (2, ["z"])]))
                vct_4 = variant.VariantCombinationTemplate(
                    dict([(1, ["a", "b", "d"]), (2, ["z", "y", "x"])]))
                set_combo = set([
                    frozenset([(1, "a"), (2, "z")]),
                    frozenset([(1, "a"), (2, "y")]),
                    frozenset([(1, "a"), (2, "x")]),
                    frozenset([(1, "b"), (2, "z")]),
                    frozenset([(1, "b"), (2, "y")]),
                    frozenset([(1, "b"), (2, "x")]),
                    frozenset([(1, "c"), (2, "z")]),
                    frozenset([(1, "c"), (2, "y")]),
                    frozenset([(1, "c"), (2, "x")])])
                vc1_s = variant.VariantCombinations(vct_1, True)
                self.assertEqual(vc1_s.sat_set, set_combo)
                self.assertEqual(vc1_s.not_sat_set, set())
                self.assertTrue(not vc1_s.is_empty())
                
                vc1_ns = variant.VariantCombinations(vct_1, False)
                self.assertEqual(vc1_ns.not_sat_set, set_combo)
                self.assertEqual(vc1_ns.sat_set, set())
                self.assertTrue(not vc1_ns.is_empty())

                self.assertRaises(AssertionError, vc1_ns.simplify, vct_2)
                self.assertEqual(vc1_ns.not_sat_set, set_combo)
                self.assertEqual(vc1_ns.sat_set, set())
                self.assertTrue(not vc1_ns.is_empty())

                self.assertRaises(AssertionError, vc1_ns.simplify, vct_4)
                self.assertEqual(vc1_ns.not_sat_set, set_combo)
                self.assertEqual(vc1_ns.sat_set, set())
                self.assertTrue(not vc1_ns.is_empty())

                vc1_tmp = copy.copy(vc1_ns)
                self.assertTrue(not vc1_tmp.is_satisfied())
                vc1_tmp.mark_all_as_satisfied()
                self.assertTrue(vc1_tmp.is_satisfied())
                self.assertEqual(vc1_tmp.sat_set, set_combo)

                vct3_set_combo = set([frozenset([(1, "a"), (2, "z")])])
                vc3_ns = variant.VariantCombinations(vct_3, False)
                self.assertEqual(vc3_ns.not_sat_set, vct3_set_combo)
                self.assertTrue(vc3_ns.issubset(vc1_ns, False))
                self.assertTrue(not vc1_ns.issubset(vc3_ns, False))
                self.assertTrue(vc1_ns.issubset(vc3_ns, True))
                self.assertTrue(not vc1_s.issubset(vc3_ns, True))

                vc3_s = variant.VariantCombinations(vct_3, True)
                vc2_s = variant.VariantCombinations(vct_2, True)
                self.assertTrue(vc3_s.intersects(vc1_s))
                self.assertTrue(vc3_ns.intersects(vc1_s))
                self.assertTrue(not vc3_ns.intersects(vc2_s))
                self.assertTrue(not vc3_s.intersects(vc2_s))
                self.assertTrue(vc1_s.intersects(vc3_s))
                intersect = vc3_s.intersection(vc1_s)
                self.assertEqual(intersect.sat_set, vct3_set_combo)
                self.assertEqual(intersect.not_sat_set, set())

                # Test that modifing the original does not modify the copy.
                vc3_ns_copy = copy.copy(vc3_ns)
                vc3_ns.mark_all_as_satisfied()
                self.assertEqual(vc3_ns_copy.not_sat_set, vct3_set_combo)
                self.assertEqual(vc3_ns.not_sat_set, set())
                self.assertEqual(vc3_ns.sat_set, vct3_set_combo)
                
                vct_empty = variant.VariantCombinationTemplate(dict([]))
                vc_empty = variant.VariantCombinations(vct_empty, True)
                self.assertTrue(vc_empty.is_empty())
                self.assertTrue(vc_empty.intersects(vc1_ns))
                self.assertTrue(vc1_ns.intersects(vc_empty))

                vc1_ns.mark_as_satisfied(vc3_s)
                self.assertEqual(vc1_ns.sat_set, vct3_set_combo)
                self.assertEqual(vc1_ns.not_sat_set, set_combo - vct3_set_combo)

                vc1_s.simplify(vct_1)
                self.assertEqual(vc1_s.sat_set, set())
                self.assertEqual(vc1_s.not_sat_set, set())

                vc1_ns_simp = variant.VariantCombinations(vct_1, False)
                vc1_ns_simp.simplify(vct_1)
                self.assertEqual(vc1_ns_simp.sat_set, set())
                self.assertEqual(vc1_ns_simp.not_sat_set, set())


if __name__ == "__main__":
        unittest.main()
