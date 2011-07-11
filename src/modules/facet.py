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
# Copyright (c) 2007, 2012, Oracle and/or its affiliates. All rights reserved.
#

# basic facet support

from pkg._varcet import _allow_facet
from pkg.misc import EmptyI
import fnmatch
import re
import types

class Facets(dict):
        # store information on facets; subclass dict
        # and maintain ordered list of keys sorted
        # by length.

        # subclass __getitem_ so that queries w/
        # actual facets find match

        def __init__(self, init=EmptyI):
                dict.__init__(self)
                self.__keylist = []
                self.__res = {}
                for i in init:
                        self[i] = init[i]

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                return dict(obj)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Update the state of this object using previously serialized
                state obtained via getstate()."""
                return Facets(init=state)

        def __repr__(self):
                s =  "<"
                s += ", ".join(["%s:%s" % (k, dict.__getitem__(self, k)) for k in self.__keylist])
                s += ">"

                return s

        def __setitem__(self, item, value):
                if not item.startswith("facet."):
                        raise KeyError, 'key must start with "facet".'

                if not (value == True or value == False):
                        raise ValueError, "value must be boolean"

                if item not in self:
                        self.__keylist.append(item)
                        self.__keylist.sort(cmp=lambda x, y: len(y) - len(x))
                dict.__setitem__(self, item, value)
                self.__res[item] = re.compile(fnmatch.translate(item))


        def __getitem__(self, item):
                """implement facet lookup algorithm here"""
                # Note that _allow_facet bypasses __getitem__ for performance
                # reasons; if __getitem__ changes, _allow_facet in _varcet.c
                # must also be updated.
                if not item.startswith("facet."):
                        raise KeyError, "key must start w/ facet."

                if item in self:
                        return dict.__getitem__(self, item)
                for k in self.__keylist:
                        if self.__res[k].match(item):
                                return dict.__getitem__(self, k)

                return True # be inclusive

        def __delitem__(self, item):
                dict.__delitem__(self, item)
                self.__keylist.remove(item)
                del self.__res[item]

        # allow_action is provided as a native function (see end of class
        # declaration).

        def pop(self, item, *args, **kwargs):
                assert len(args) == 0 or (len(args) == 1 and
                    "default" not in kwargs)
                try:
                        self.__keylist.remove(item)
                        del self.__res[item]
                except ValueError:
                        if not args and "default" not in kwargs:
                                raise
                default = kwargs.get("default", None)
                if args:
                        default = args[0]
                return dict.pop(self, item, default)

        def popitem(self):
                popped = dict.popitem(self)
                self.__keylist.remove(popped[0])
                del self.__res[popped]
                return popped

        def setdefault(self, item, default=None):
                if item not in self:
                        self[item] = default
                return self[item]

        def update(self, d):
                for k, v in d.iteritems():
                        self[k] = v

        def keys(self):
                return self.__keylist[:]

        def values(self):
                return [self[k] for k in self.__keylist]

        def items(self):
                return [a for a in self.iteritems()]

        def iteritems(self): # return in sorted order for display
                for k in self.__keylist:
                        yield k, self[k]

        def copy(self):
                return Facets(self)

        def clear(self):
                self.__keylist = []
                self.__res = []
                dict.clear(self)

Facets.allow_action = types.MethodType(_allow_facet, None, Facets)
