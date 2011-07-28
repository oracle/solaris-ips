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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

# basic facet support

from pkg.misc import EmptyI
import fnmatch 

class Facets(dict):
        # store information on facets; subclass dict 
        # and maintain ordered list of keys sorted
        # by length.

        # subclass __getitem_ so that queries w/ 
        # actual facets find match

        def __init__(self, init=EmptyI):
                dict.__init__(self)
                self.__keylist = []
                for i in init:
                        self[i] = init[i]

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

        def __getitem__(self, item):
                """implement facet lookup algorithm here"""
                if not item.startswith("facet."):
                        raise KeyError, "key must start w/ facet."

                if item in self:
                        return dict.__getitem__(self, item)
                for k in self.__keylist:
                        if fnmatch.fnmatch(item, k):
                                return dict.__getitem__(self, k)

                return True # be inclusive

        def __delitem__(self, item):
                dict.__delitem__(self, item)
                self.__keylist.remove(item)

        def pop(self, item, *args, **kwargs):
                assert len(args) == 0 or (len(args) == 1 and
                    "default" not in kwargs)
                try:
                        self.__keylist.remove(item)
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
                dict.clear(self)

        def allow_action(self, action):
                """ determine if facets permit this action; if any facets
                allow it, return True; also return True if no facets are present"""
                facets = [k for k in action.attrs.keys() if k.startswith("facet.")]
                
                ret = True

                for f in facets:
                        if self[f]:
                                return True
                        else:
                                ret = False

                return ret
