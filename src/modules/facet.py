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
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
#

# basic facet support

import fnmatch
import re
import six
import types

from pkg._varcet import _allow_facet
from pkg.misc import EmptyI, ImmutableDict

class Facets(dict):
        # store information on facets; subclass dict
        # and maintain ordered list of keys sorted
        # by length.

        # subclass __getitem__ so that queries w/
        # actual facets find match

        #
        # For image planning purposes and to be able to compare facet objects
        # deterministically, facets must be sorted.  They are first sorted by
        # source (more details below), then by length, then lexically.
        #
        # Facets can come from three different sources.
        #
        # SYSTEM facets are facets whose values are assigned by the system.
        # These are usually facets defined in packages which are not set in an
        # image, and the value assigned by the system is always true.  These
        # facets will usually never be found in a Facets dictionary.  (Facets
        # dictionaries only contain facets which are explicitly set.)
        #
        # LOCAL facets are facets which have been set locally in an image
        # using pkg(1) or the pkg api.  Explicitly set LOCAL facets are stored
        # in Facets.__local.  Facets which are not explicitly set but match an
        # explicitly set LOCAL facet glob pattern are also considered to be
        # LOCAL.
        #
        # PARENT facets are facets which are inherited from a parent image.
        # they are managed internally by the packaging subsystem.  Explicitly
        # inherited facets are stored in Facets.__inherited.  Facets which are
        # not explicitly set but match an explicitly set PARENT facet glob
        # pattern are also considered to be PARENT.
        #
        # When evaluating facets, all PARENT facets are evaluated before LOCAL
        # facets.  This is done by ensuring that all PARENT facets come before
        # any LOCAL facets in __keylist.  This is done because PARENT facets
        # exist to propagate faceted dependencies between linked images, which
        # is needed to ensure the solver can run successfully.  ie, if a
        # parent image relaxes dependencies via facet version-locks, then the
        # child needs to inherit those facets since otherwise it is more
        # constrained in possible solutions than it's parent and likely won't
        # be able to plan an update that keeps it in sync with it's parent.
        #
        # Sine PARENT facets take priority over LOCAL facets, it's possible to
        # have conflicts between the two.  In the case where a facet is both
        # inherited and set locally, both values are preserved, but the
        # inherited value masks the local value.  Users can list and update
        # local values while they are masked using pkg(1), but as long as the
        # values are masked they will not affect image planning operations.
        # Once an inherited facet that masks a local facet is removed, the
        # local facet will be restored.
        #

        FACET_SRC_SYSTEM = "system"
        FACET_SRC_LOCAL = "local"
        FACET_SRC_PARENT = "parent"

        def __init__(self, init=EmptyI):
                dict.__init__(self)
                self.__keylist = []
                self.__res = {}
                self.__local = {}
                self.__local_ro = None
                self.__inherited = {}
                self.__inherited_ro = None

                # initialize ourselves
                self.update(init)

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""

                return [
                        [k, v, True]
                        for k, v in six.iteritems(obj.__inherited)
                ] + [
                        [k, v, False]
                        for k, v in six.iteritems(obj.__local)
                ]

        @staticmethod
        def fromstate(state, jd_state=None):
                """Update the state of this object using previously serialized
                state obtained via getstate()."""

                rv = Facets()
                for k, v, inhertited in state:
                        if not inhertited:
                                rv[k] = v
                        else:
                                rv._set_inherited(k, v)
                return rv

        def _cmp_priority(self, other):
                """Compare the facet match priority of two Facets objects.
                Since the match priority of a Facets object is dependent upon
                facet sources (local vs parent) and names, we're essentially
                ensuring that both objects have the same set of facet sources
                and names."""

                assert type(other) is Facets
                return cmp(self.__keylist, other.__keylist)

        def _cmp_values(self, other):
                """Compare the facet values of two Facets objects.  This
                comparison ignores any masked values."""

                assert type(other) is Facets
                return dict.__cmp__(self, other)

        def _cmp_all_values(self, other):
                """Compare all the facet values of two Facets objects.  This
                comparison takes masked values into account."""

                assert type(other) is Facets
                rv = cmp(self.__inherited, other.__inherited)
                if rv == 0:
                        rv = cmp(self.__local, other.__local)
                return rv

        def __cmp__(self, other):
                """Compare two Facets objects.  This comparison takes masked
                values into account."""

                # check if we're getting compared against something other than
                # another Factes object.
                if type(other) is not Facets:
                        return 1

                # Check for effective facet value changes that could affect
                # solver computations.
                rv = self._cmp_values(other)
                if rv != 0:
                        return rv

                # Check for facet priority changes that could affect solver
                # computations.  (Priority changes can occur when local or
                # inherited facets are added or removed.)
                rv = self._cmp_priority(other)
                if rv != 0:
                        return rv

                # There are no outwardly visible facet priority or value
                # changes that could affect solver computations, but it's
                # still possible that we're changing the set of local or
                # inherited facets in a way that doesn't affect solver
                # computations.  For example:  we could be adding a local
                # facet with a value that is masked by an inherited facet, or
                # having a facet transition from being inherited to being
                # local without a priority or value change.  Check if this is
                # the case.
                rv = self._cmp_all_values(other)
                return rv

        def __eq__(self, other):
                """redefine in terms of __cmp__()"""
                return (Facets.__cmp__(self, other) == 0)

        def __ne__(self, other):
                """redefine in terms of __cmp__()"""
                return (Facets.__cmp__(self, other) != 0)

        def __ge__(self, other):
                """redefine in terms of __cmp__()"""
                return (Facets.__cmp__(self, other) >= 0)

        def __gt__(self, other):
                """redefine in terms of __cmp__()"""
                return (Facets.__cmp__(self, other) > 0)

        def __le__(self, other):
                """redefine in terms of __cmp__()"""
                return (Facets.__cmp__(self, other) <= 0)

        def __lt__(self, other):
                """redefine in terms of __cmp__()"""
                return (Facets.__cmp__(self, other) < 0)

        def __repr__(self):
                s =  "<"
                s += ", ".join([
                    "{0}:{1}".format(k, dict.__getitem__(self, k))
                    for k in self.__keylist
                ])
                s += ">"

                return s

        def __keylist_sort(self):
                """Update __keysort, which is used to determine facet matching
                order.  Inherited facets always take priority over local
                facets so make sure all inherited facets come before local
                facets in __keylist.  All facets from a given source are
                sorted by length, and facets of equal length are sorted
                lexically."""

                def facet_sort(x, y):
                        i = len(y) - len(x)
                        if i != 0:
                                return i
                        return cmp(x, y)

                self.__keylist = []
                self.__keylist += sorted([
                        i
                        for i in self
                        if i in self.__inherited
                ], cmp=facet_sort)
                self.__keylist += sorted([
                        i
                        for i in self
                        if i not in self.__inherited
                ], cmp=facet_sort)

        def __setitem_internal(self, item, value, inherited=False):
                if not item.startswith("facet."):
                        raise KeyError('key must start with "facet".')

                if not (value == True or value == False):
                        raise ValueError("value must be boolean")

                keylist_sort = False
                if (inherited and item not in self.__inherited) or \
                    (not inherited and item not in self):
                        keylist_sort = True

                # save the facet in the local or inherited dictionary
                # clear the corresponding read-only dictionary
                if inherited:
                        self.__inherited[item] = value
                        self.__inherited_ro = None
                else:
                        self.__local[item] = value
                        self.__local_ro = None

                # Inherited facets always take priority over local facets.
                if inherited or item not in self.__inherited:
                        dict.__setitem__(self, item, value)
                        self.__res[item] = re.compile(fnmatch.translate(item))

                if keylist_sort:
                        self.__keylist_sort()

        def __setitem__(self, item, value):
                """__setitem__ only operates on local facets."""
                self.__setitem_internal(item, value)

        def __getitem_internal(self, item):
                """Implement facet lookup algorithm here

                Note that _allow_facet bypasses __getitem__ for performance
                reasons; if __getitem__ changes, _allow_facet in _varcet.c
                must also be updated.

                We return a tuple of the form (<key>, <value>) where key is
                the explicitly set facet name (which may be a glob pattern)
                that matched the caller specific facet name."""

                if not item.startswith("facet."):
                        raise KeyError("key must start w/ facet.")

                if item in self:
                        return item, dict.__getitem__(self, item)
                for k in self.__keylist:
                        if self.__res[k].match(item):
                                return k, dict.__getitem__(self, k)

                # The trailing '.' is to encourage namespace usage.
                if item.startswith("facet.debug.") or \
                    item.startswith("facet.optional."):
                        return None, False # exclude by default
                return None, True # be inclusive

        def __getitem__(self, item):
                return self.__getitem_internal(item)[1]

        def __delitem_internal(self, item, inherited=False):

                # check for an attempt to delete an invalid facet
                if not dict.__contains__(self, item):
                        raise KeyError(item)

                # check for an attempt to delete an invalid local facet
                if not inherited and item not in self.__local:
                        raise KeyError(item)

                # we should never try to delete an invalid inherited facet
                assert not inherited or item in self.inherited

                keylist_sort = False
                if inherited and item in self.__local:
                        # the inherited value was overriding a local value
                        # that should now be exposed
                        dict.__setitem__(self, item, self.__local[item])
                        self.__res[item] = re.compile(fnmatch.translate(item))
                        keylist_sort = True
                else:
                        # delete the item
                        dict.__delitem__(self, item)
                        del self.__res[item]
                        self.__keylist.remove(item)

                # delete item from the local or inherited dictionary
                # clear the corresponding read-only dictionary
                if inherited:
                        rv = self.__inherited[item]
                        del self.__inherited[item]
                        self.__inherited_ro = None
                else:
                        rv = self.__local[item]
                        del self.__local[item]
                        self.__local_ro = None

                if keylist_sort:
                        self.__keylist_sort()
                return rv

        def __delitem__(self, item):
                """__delitem__ only operates on local facets."""
                self.__delitem_internal(item)

        # allow_action is provided as a native function (see end of class
        # declaration).

        def _set_inherited(self, item, value):
                """Set an inherited facet."""
                self.__setitem_internal(item, value, inherited=True)

        def _clear_inherited(self):
                """Clear all inherited facet."""
                for k in self.__inherited.keys():
                        self.__delitem_internal(k, inherited=True)

        def _action_match(self, act):
                """Find the subset of facet key/values pairs which match any
                facets present on an action."""

                # find all the facets present in the current action
                action_facets = frozenset([
                        a
                        for a in act.attrs
                        if a.startswith("facet.")
                ])

                rv = set()
                for facet in self.__keylist:
                        if facet in action_facets:
                                # we found a matching facet.
                                rv.add((facet, self[facet]))
                                continue
                        for action_facet in action_facets:
                                if self.__res[facet].match(action_facet):
                                        # we found a matching facet.
                                        rv.add((facet, self[facet]))
                                        break

                return (frozenset(rv))

        def pop(self, item, *args, **kwargs):
                """pop() only operates on local facets."""

                assert len(args) == 0 or (len(args) == 1 and
                    "default" not in kwargs)

                if item not in self.__local:
                        # check if the user specified a default value
                        if args:
                                return args[0]
                        elif "default" in kwargs:
                                return kwargs["default"]
                        if len(self) == 0:
                                raise KeyError('pop(): dictionary is empty')
                        raise KeyError(item)

                return self.__delitem_internal(item, inherited=False)

        def popitem(self):
                """popitem() only operates on local facets."""

                item = None
                for item, value in self.__local:
                        break

                if item is None:
                        raise KeyError('popitem(): dictionary is empty')

                self.__delitem_internal(item)
                return (item, value)

        def setdefault(self, item, default=None):
                if item not in self:
                        self[item] = default
                return self[item]

        def update(self, d):
                if type(d) == Facets:
                        # preserve inherited facets.
                        for k, v in six.iteritems(d.__inherited):
                                self._set_inherited(k, v)
                        for k, v in six.iteritems(d.__local):
                                self[k] = v
                        return

                for k in d:
                        self[k] = d[k]

        def keys(self):
                return self.__keylist[:]

        def values(self):
                return [self[k] for k in self.__keylist]

        def _src_values(self, name):
                """A facet may be set via multiple sources and hence have
                multiple values.  If there are multiple values for a facet,
                all but one of those values will be masked.  So for a given
                facet, return a list of tuples of the form (<value>, <src>,
                <masked>) which represent all currently set values for this
                facet."""

                rv = []
                if name in self.__inherited:
                        src = self.FACET_SRC_PARENT
                        value = self.__inherited[name]
                        masked = False
                        rv.append((value, src, masked))
                if name in self.__local:
                        src = self.FACET_SRC_LOCAL
                        value = self.__local[name]
                        masked = False
                        if name in self.__inherited:
                                masked = True
                        rv.append((value, src, masked))
                return rv

        def items(self):
                return [a for a in six.iteritems(self)]

        def iteritems(self): # return in sorted order for display
                for k in self.__keylist:
                        yield k, self[k]

        def copy(self):
                return Facets(self)

        def clear(self):
                self.__keylist = []
                self.__res = {}
                self.__local = {}
                self.__local_ro = None
                self.__inherited = {}
                self.__inherited_ro = None
                dict.clear(self)

        def _match_src(self, name):
                """Report the source of a facet value if we were to attempt to
                look it up in the current Facets object dictionary."""

                k = self.__getitem_internal(name)[0]
                if k in self.__inherited:
                        return self.FACET_SRC_PARENT
                if k in self.__local:
                        return self.FACET_SRC_LOCAL
                assert k is None and k not in self
                return self.FACET_SRC_SYSTEM

        # For convenience, provide callers with direct access to local and
        # parent facets via cached read-only dictionaries.
        @property
        def local(self):
                if self.__local_ro is None:
                        self.__local_ro = ImmutableDict(self.__local)
                return self.__local_ro

        @property
        def inherited(self):
                if self.__inherited_ro is None:
                        self.__inherited_ro = ImmutableDict(self.__inherited)
                return self.__inherited_ro


Facets.allow_action = types.MethodType(_allow_facet, None, Facets)
