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

# basic variant support 

from pkg.misc import EmptyI

class Variants(dict):
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

        # Methods which are unique to variants
        def allow_action(self, action):
                """ determine if variants permit this action """
                for a in set(action.attrs.keys()) & \
                    self.__keyset:
                        if self[a] != action.attrs[a]:
                                return False
                return True

class VariantSets(Variants):
        """Class for holding sets of variants. The parent class is designed to
        hold one value per variant. This class is used when multiple values for
        a variant need to be used. It ensures that the value each variant
        maps to is a set of one or more variant values."""

        def __init__(self, init=EmptyI):
                self.set_sats = False
                self.not_sat_set = None
                Variants.__init__(self, init)

        def update(self, d):
                for a in d:
                        if isinstance(d[a], set):
                                self[a] = d[a]
                        elif isinstance(d[a], list):
                                self[a] = set(d[a])
                        else:
                                self[a] = set([d[a]])

        def copy(self):
                return VariantSets(self)
        
        def __setitem__(self, item, value):
                assert(not self.set_sats)
                if isinstance(value, list):
                        value = set(value)
                elif not isinstance(value, set):
                        value = set([value])
                Variants.__setitem__(self, item, value)
        
        def merge(self, var):
                """Combine two sets of variants into one."""
                for name in var:
                        if name in self:
                                self[name].update(var[name])
                        else:
                                self[name] = var[name]

        def issubset(self, var):
                """Returns whether self is a subset of variant var."""
                for k in self:
                        if k not in var:
                                return False
                        if self[k] - var[k]:
                                return False
                return True

        def difference(self, var):
                """Returns the variants in self and not in var."""
                res = VariantSets()
                for k in self:
                        tmp = self[k] - var.get(k, [])
                        if tmp:
                                res[k] = tmp
                return res

        def merge_unknown(self, var):
                """Pull the values for unknown keys in var into self."""
                for name in var:
                        if name not in self:
                                self[name] = var[name]

        def intersects(self, var):
                """Returns whether self and var share at least one value for
                each variant in self."""
                for k in self:
                        if k not in var:
                                return False
                        found = False
                        for v in self[k]:
                                if v in var[k]:
                                        found = True
                                        break
                        if not found:
                                return False
                return True

        def intersection(self, var):
                """Find those variant values in self that are also in var, and
                return them."""

                res = VariantSets()
                for k in self:
                        if k not in var:
                                raise RuntimeError("%s cannot be intersected "
                                    "with %s becuase %s is not a key in the "
                                    "latter." % (self, var, k))
                        res[k] = self[k] & var[k]
                return res

        def __variant_cross_product(self):
                """Generates the cross product of all the values for all the
                variants in self."""

                tmp = []
                for k in sorted(self):
                        if tmp == []:
                                tmp = [[v] for v in self[k]]
                                continue
                        new_tmp = []
                        new_tmp.extend([
                            exist[:] + [v] for v in self[k]
                            for exist in tmp
                        ])
                        tmp = new_tmp
                return set([tuple(v) for v in tmp])
                                
        def mark_as_satisfied(self, var):
                """Mark those variant combinations seen in var as being
                satisfied in self."""

                if not self.set_sats:
                        self.set_sats = True
                        self.not_sat_set = self.__variant_cross_product()
                self.not_sat_set -= var.__variant_cross_product()

        def is_satisfied(self):
                """Returns whether all variant combinations for this package
                have been satisfied."""

                return self.set_sats and not self.not_sat_set

        def get_satisfied(self):
                """Returns the combinations of variants which have been
                satisfied for this VariantSets."""
                if self == {}:
                        return None
                sats = self.__variant_cross_product()
                var_names = sorted(self)
                return [zip(var_names, tup) for tup in sorted(sats)]

        def get_unsatisfied(self):
                """Returns the variant combinations for self which have not
                been satisfied."""

                if not self.set_sats:
                        self.set_sats = True
                        self.not_sat_set = self.__variant_cross_product()
                var_names = sorted(self)
                return [zip(var_names, tup) for tup in sorted(self.not_sat_set)]

        def remove_identical(self, var):
                """For each key in self, remove it from the dictionary if its
                values are identical to the values that var maps k to."""

                for k in self.keys():
                        if k not in var:
                                continue
                        if self[k] == var[k]:
                                del self[k]

        def __repr__(self):
                return "VariantSets(%s)" % dict.__repr__(self)
