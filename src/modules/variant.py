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

# basic variant support

import copy
import itertools
import six
import types

from collections import namedtuple
from pkg._varcet import _allow_variant
from pkg.misc import EmptyI

class _Variants(dict):
        # store information on variants; subclass dict
        # and maintain set of keys for performance reasons

        def __init__(self, init=EmptyI):
                dict.__init__(self)
                self.__keyset = set()
                for i in init:
                        self[i] = init[i]

        def __setitem__(self, item, value):
                dict.__setitem__(self, item, value)
                self.__keyset.add(item)

        def __delitem__(self, item):
                dict.__delitem__(self, item)
                self.__keyset.remove(item)

        # allow_action is provided as a native function (see end of class
        # declaration).

        def pop(self, item, default=None):
                self.__keyset.discard(item)
                return dict.pop(self, item, default)

        def popitem(self):
                popped = dict.popitem(self)
                self.__keyset.remove(popped[0])
                return popped

        def setdefault(self, item, default=None):
                if item not in self:
                        self[item] = default
                return self[item]

        def update(self, d):
                for a in d:
                        self[a] = d[a]

        def copy(self):
                return Variants(self)

        def clear(self):
                self.__keyset = set()
                dict.clear(self)

        if six.PY3:
                def allow_action(self, action, publisher=None):
                        return _allow_variant(self, action, publisher=publisher)
if six.PY2:
        _Variants.allow_action = types.MethodType(_allow_variant, None, _Variants)


class Variants(_Variants):
        """This is a wrapper-class used by other consumers that handles implicit
        variant values.  This class cannot be used by the VariantCombination*
        classes since they rely on explicit values only to be found."""

        def __getitem_internal(self, item):
                """Implement variant lookup algorithm here

                Note that _allow_variant bypasses __getitem__ for performance
                reasons; if __getitem__ changes, _allow_variant in _varcet.c
                must also be updated.

                We return a tuple of the form (<key>, <value>) where key is the
                explicitly set variant name that matched the caller specific
                variant name."""

                if not item.startswith("variant."):
                        raise KeyError("key must start w/ variant.")

                if item in self:
                        return item, dict.__getitem__(self, item)

                # The trailing '.' is to encourage namespace usage.
                if item.startswith("variant.debug."):
                        return None, "false" # 'false' by default
                raise KeyError("unknown variant {0}".format(item))

        def __getitem__(self, item):
                return self.__getitem_internal(item)[1]


# The two classes which follow are used during dependency calculation when
# actions have variants, or the packages they're contained in do.  The
# VariantCombinationTemplate corresponds to information that is encoded in
# the actions.  Specifically, it records what types of variants exist
# (variant.arch or variant.debug) and what values are known to exist for them
# (x86/sparc or debug/non-debug).  The variant types are the keys of the
# dictionary while the variant values are what the keys map to.
#
# The VariantCombinations class serves a different purpose.  In order to
# determine whether a dependency is satisfied under all combinations of
# variants, it is necessary to track whether each combination has been
# satisfied.  When a VariantCombinations is created, it is provided a
# VariantCombinationTemplate which it uses to seed the combinations of variants.
# To make a single combination instance, for each type of variant, it chooses
# one value and adds it to the instance.  It creates all possible combination
# instances and these are what it uses to track whether all combinations have
# been satisfied.  The class also provides methods for manipulating the
# instances while maintaining consistency between the satisfied set and the
# unsatisfied set.

class VariantCombinationTemplate(_Variants):
        """Class for holding a template of variant types and their potential
        values."""

        def __copy__(self):
                return VariantCombinationTemplate(self)

        def __setitem__(self, item, value):
                """Overrides _Variants.__setitem__ to ensure that all values are
                sets."""

                if isinstance(value, list):
                        value = set(value)
                elif not isinstance(value, set):
                        value = set([value])
                _Variants.__setitem__(self, item, value)

        def issubset(self, var):
                """Returns whether self is a subset of variant var."""
                res = self.difference(var)
                return not res.type_diffs and not res.value_diffs

        def difference(self, var):
                res = VCTDifference([], [])
                for k in self:
                        if k not in var:
                                res.type_diffs.append(k)
                        else:
                                for v in self[k] - var[k]:
                                        res.value_diffs.append((k, v))
                return res

        def merge_unknown(self, var):
                """Pull the values for unknown keys in var into self."""
                for name in var:
                        if name not in self:
                                self[name] = var[name]

        def merge_values(self, var):
                """Pull all unknown values of all keys in var into self."""
                for name in var:
                        self.setdefault(name, set([])).update(var[name])

        def __repr__(self):
                return "VariantTemplate({0})".format(dict.__repr__(self))

        def __str__(self):
                s = ""
                for k in sorted(self):
                        t = ",".join(['"{0}"'.format(v) for v in sorted(self[k])])
                        s += " {0}={1}".format(k, t)
                if s:
                        return s
                else:
                        return " <none>"


VCTDifference = namedtuple("VCTDifference", ["type_diffs", "value_diffs"])
# Namedtuple used to store the results of VariantCombinationTemplate
# differences.  The type_diffs field stores the variant types which are in the
# caller and not in the argument to difference.  The value_diffs field stores
# the values for particular types which are in the caller and not in the
# argument to difference.


class VariantCombinations(object):
        """Class for keeping track of which combinations of variant values have
        and have not been satisfied for a particular action."""

        def __init__(self, vct, satisfied):
                """Create an instance of VariantCombinations based on the
                template provided.

                The 'vct' parameter is the template from which to build the
                combinations.

                The 'satisfied' parameter is a boolean which determines whether
                the combinations created from the template will be considered
                satisfied or unsatisfied."""

                assert(isinstance(vct, VariantCombinationTemplate))
                self.__sat_set = set()
                self.__not_sat_set = set()
                tmp = []
                # This builds all combinations of variant values presented in
                # vct.
                for k in sorted(vct):
                        if not tmp:
                                # Initialize tmp with the key-value pairs for
                                # the first key in vct.
                                tmp = [[(k, v)] for v in vct[k]]
                                continue
                        # For each subsequent key in vct, append each of its
                        # key-value pairs to each of the existing combinations.
                        new_tmp = [
                            exist[:] + [(k, v)] for v in vct[k]
                            for exist in tmp
                        ]
                        tmp = new_tmp
                # Here is an example of how the loop above would handle a vct
                # of { 1:["a", "b"], 2:["x", "y"], 3:["m", "n"] }
                # First, tmp would be initialized as [[(1, "a")], [(1, "b")]]
                # Next, a new list is created by adding (2, "x") to a copy
                # of each item in tmp, and then (2, "y"). This produces
                # [[(1, "a"), (2, "x")], [(1, "a"), (2, "y")],
                #  [(1, "b"), (2, "x")], [(1, "b"), (2, "y")]]
                # That process is repeated one more time for the 3 key,
                # resulting in:
                # [[(1, "a"), (2, "x"), (3, "m")],
                #  [(1, "a"), (2, "x"), (3, "n")],
                #  [(1, "a"), (2, "y"), (3, "m")],
                #  [(1, "a"), (2, "y"), (3, "n")],
                #  [(1, "b"), (2, "x"), (3, "m")],
                #  [(1, "b"), (2, "x"), (3, "n")],
                #  [(1, "b"), (2, "y"), (3, "m")],
                #  [(1, "b"), (2, "y"), (3, "n")]]
                self.__combinations = [frozenset(l) for l in tmp]
                res = set(self.__combinations)
                if satisfied:
                        self.__sat_set = res
                else:
                        self.__not_sat_set = res
                self.__template = copy.copy(vct)
                self.__simpl_template = None

        @property
        def template(self):
                return self.__template

        @property
        def sat_set(self):
                if not self.__simpl_template:
                        return self.__sat_set
                else:
                        return self.__calc_simple(True)

        @property
        def not_sat_set(self):
                if not self.__simpl_template:
                        return self.__not_sat_set
                else:
                        return self.__calc_simple(False)

        def __copy__(self):
                vc = VariantCombinations(self.__template, True)
                vc.__sat_set = copy.copy(self.__sat_set)
                vc.__not_sat_set = copy.copy(self.__not_sat_set)
                vc.__simpl_template = self.__simpl_template
                vc.__combinations = self.__combinations
                return vc

        def __eq__(self, other):
                return self.__template == other.__template and \
                    self.__sat_set == other.__sat_set and \
                    self.__not_sat_set == other.__not_sat_set and \
                    self.__simpl_template == other.__simpl_template and \
                    self.__combinations == other.__combinations

        def __ne__(self, other):
                return not self.__eq__(other)

        __hash__ = object.__hash__

        def is_empty(self):
                """Returns whether self was created with any potential variant
                values."""

                return not self.__sat_set and not self.__not_sat_set
                
        def issubset(self, vc, satisfied):
                """Returns whether the instances in self are a subset of the
                instances in vc. 'satisfied' determines whether the instances
                compared are drawn from the set of satisfied instances or the
                set of unsatisfied instances."""

                if satisfied:
                        return self.__sat_set.issubset(vc.__sat_set)
                else:
                        return self.__not_sat_set.issubset(vc.__not_sat_set)

        def intersects(self, vc, only_not_sat=False):
                """Returns whether an action whose variants are vc could satisfy
                dependencies whose variants are self.

                'only_not_sat' determines whether only the unsatisfied set of
                variants for self is used for comparision.  When only_not_sat
                is True, then intersects returns wether vc would satisfy at
                least one instance which is currently unsatisfied."""

                if self.is_empty() or vc.is_empty():
                        return True
                tmp = self.intersection(vc)
                if only_not_sat:
                        return bool(tmp.__not_sat_set)
                return not tmp.is_empty()
                
        def intersection(self, vc):
                """Find those variant values in self that are also in var, and
                return them."""
                assert len(vc.not_sat_set) == 0
                res = copy.copy(self)
                res.__sat_set &= vc.__sat_set
                res.__not_sat_set &= vc.__sat_set
                return res

        def separate_satisfied(self, vc):
                """Find those combinations of variants that are satisfied only
                in self, in both self and vc, and only in vc."""

                intersect = None
                only_big = None
                only_small = None

                if self.is_empty() and vc.is_empty():
                        return None, self, None

                if vc.__template.issubset(self.__template):
                        big = self
                        small = vc
                elif self.__template.issubset(vc.__template):
                        big = vc
                        small = self
                else:
                        # If one template isn't a subset of, or identical to,
                        # the other, then no meaningful comparison can be
                        # performed.
                        return self, None, vc

                if big.__sat_set & small.__sat_set:
                        intersect = VariantCombinations(big.__template, False)
                        intersect.__sat_set = big.__sat_set & small.__sat_set
                        intersect.__not_sat_set -= intersect.__sat_set

                if big.__sat_set - small.__sat_set:
                        only_big = VariantCombinations(big.__template, False)
                        only_big.__sat_set = big.__sat_set - small.__sat_set
                        only_big.__not_sat_set -= only_big.__sat_set

                if small.__sat_set - big.__sat_set:
                        only_small = VariantCombinations(big.__template, False)
                        only_small.__sat_set = small.__sat_set - big.__sat_set
                        only_small.__not_sat_set -= only_small.__sat_set

                if big == self:
                        return only_big, intersect, only_small
                return only_small, intersect, only_big

        def mark_as_satisfied(self, vc):
                """For all instances in vc, mark those instances as being
                satisfied.  Returns a boolean indicating whether any changes
                have been made."""

                i = vc.__sat_set & self.__not_sat_set
                if not i:
                        return False
                self.__not_sat_set -= i
                self.__sat_set |= i
                return True

        def mark_as_unsatisfied(self, vc):
                """For all satisfied instances in vc, mark those instances as
                being unsatisfied."""

                i = vc.__sat_set & self.__sat_set
                if not i:
                        return False
                self.__sat_set -= i
                self.__not_sat_set |= i
                return True

        def mark_all_as_satisfied(self):
                """Mark all instances as being satisfied."""

                self.__sat_set |= self.__not_sat_set
                self.__not_sat_set = set()

        def is_satisfied(self):
                """Returns whether all variant combinations for this package
                have been satisfied."""

                return not self.__not_sat_set

        def simplify(self, vct, assert_on_different_domains=True):
                """Store the provided VariantCombinationTemplate as the template
                to use when simplifying the combinations."""

                if not self.__template.issubset(vct):
                        self.__simpl_template = {}                
                        if assert_on_different_domains:
                                assert self.__template.issubset(vct), \
                                    "template:{0}\nvct:{1}".format(
                                    self.__template, vct)
                self.__simpl_template = vct

        def split_combinations(self):
                """Create one VariantCombination object for each possible
                combination of variants.  This is useful when each combination
                needs to be associated with other information."""

                tmp = []
                for c in self.__combinations:
                        vc = VariantCombinations(self.__template, False)
                        vc.__sat_set.add(c)
                        vc.__not_sat_set = set()
                        tmp.append(vc)
                # If there weren't any combinations, then this is an empty
                # variant combination, so just return a copy of ourselves.
                if not tmp:
                        tmp.append(copy.copy(self))
                return tmp

        def unsatisfied_copy(self):
                """Create a copy of this variant combination, but make sure all
                the variant combinations are marked as unsatisifed."""

                return VariantCombinations(self.__template, False)

        def __calc_simple(self, sat):
                """Given VariantCombinationTemplate to be simplified against,
                reduce the instances to the empty set if the instances cover all
                possible combinations of the template provided.

                A general approach to simplification is currently deemed to
                difficult in the face of arbitrary numbers of variant types and
                arbitrary numbers of variant."""

                if not self.__simpl_template:
                        possibilities = 0
                else:
                        possibilities = 1
                        for k in self.__simpl_template:
                                possibilities *= len(self.__simpl_template[k])

                if sat:
                        rel_set = self.__sat_set
                else:
                        rel_set = self.__not_sat_set

                # If the size of sat_set or not_sat_set matches the number of
                # possibilities a template can produce, then it can be
                # simplified.
                if possibilities == len(rel_set):
                        return set()
                # If any dependencies are merged, then another pass over the
                # variant types is necessary.  'keep_going' tracks whether that
                # has happened.
                keep_going = True
                while keep_going:
                        keep_going = False
                        # For each variant type ...
                        # Sort to ensure variant_name is being visited in a
                        # reversed aliphatic order so that the logic below can
                        # get a deterministic simplified variant combination
                        # between Python 2 and 3.
                        # For example, "variant.opensolaris.zone" should be
                        # visited before "variant.arch".
                        for variant_name in sorted(self.__simpl_template,
                            reverse=True):
                                def exclude_name(item):
                                        return [
                                            (k, v) for k, v in item
                                            if k != variant_name
                                        ]
                                # For sanity, instead of modifying rel_set on
                                # the fly, a new working set is created to which
                                # members or collapsed members of rel_set are
                                # added.
                                new_rel_set = set()

                                # Put the combinations of variant values into
                                # groups so that all members of the group are
                                # identical except for the values for
                                # variant_name.
                                for k, g in itertools.groupby(
                                    sorted(rel_set, key=exclude_name),
                                    exclude_name):
                                        g = set(g)

                                        # If there are fewer members in the
                                        # group than there are values, then
                                        # there's no way this value can be
                                        # collapsed.
                                        if len(g) < len(self.__simpl_template[
                                            variant_name]):
                                                new_rel_set |= g
                                                continue

                                        # 'expected' is the set of variant
                                        # values that will need to be seen to
                                        # collapse the combinations in g by
                                        # removing the values associated with
                                        # variant_name.
                                        expected = set(self.__simpl_template[
                                            variant_name])

                                        # Check to see whether all possible
                                        # variant values are covered.
                                        for tup in g:
                                                for v_name, v_value in tup:
                                                        if v_name != \
                                                            variant_name:
                                                                continue
                                                        expected.remove(v_value)

                                        # If not all the possible values have
                                        # been seen, then the variant
                                        # combinations can't be collapsed.
                                        if expected:
                                                new_rel_set |= g
                                                continue
                                        # If they have, then the variant
                                        # combinations can be collapsed by
                                        # removing variant_name.  The key used
                                        # to group the variant combinations,
                                        # 'k', is identical to each of the
                                        # variant combinations with the value
                                        # for variant_name removed, so 'k' is
                                        # added to the new result set.  Since
                                        # some variant combinations have been
                                        # collapsed, then it's necessary to make
                                        # another pass over the variant types as
                                        # 'k' may be able to collapse with other
                                        # variant combinations.
                                        keep_going = True
                                        new_rel_set.add(frozenset(k))
                                rel_set = new_rel_set
                return rel_set

        def __repr__(self):
                return "VC Sat:{0} Unsat:{1}".format(sorted(self.__sat_set),
                    sorted(self.__not_sat_set))
