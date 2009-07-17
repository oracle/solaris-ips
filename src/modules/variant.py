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

        def merge(self, var):
                """Combine two sets of variants into one."""
                for name in var:
                        if name in self:
                                self[name].extend(var[name])
                                self[name] = list(set(self[name]))
                        else:
                                self[name] = list(set(var[name]))

        def issubset(self, var):
                """Returns whether self is a subset of variant var."""
                for k in self:
                        if k not in var:
                                return False
                        if set(self[k]) - set(var[k]):
                                return False
                return True

        def difference(self, var):
                """Returns the variants in self and not in var."""
                res = Variants()
                for k in self:
                        tmp = set(self[k]) - set(var.get(k, []))
                        if tmp:
                                res[k] = tmp
                return res
