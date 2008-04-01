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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import bisect
import os
import cPickle
from itertools import groupby, chain

import pkg.actions as actions
import pkg.client.retrieve as retrieve
import pkg.client.filter as filter
from pkg.actions.attribute import AttributeAction

# The type member is used for the ordering of actions.
ACTION_DIR = 10
ACTION_FILE = 20
ACTION_LINK = 50
ACTION_HARDLINK = 55
ACTION_DEVICE = 100
ACTION_USER = 200
ACTION_GROUP = 210
ACTION_SERVICE = 300
ACTION_RESTART = 310
ACTION_DEPEND = 400

DEPEND_REQUIRE = 0
DEPEND_OPTIONAL = 1
DEPEND_INCORPORATE =10

depend_str = { DEPEND_REQUIRE : "require",
                DEPEND_OPTIONAL : "optional",
                DEPEND_INCORPORATE : "incorporate"
}

class Manifest(object):
        """A Manifest is the representation of the actions composing a specific
        package version on both the client and the repository.  Both purposes
        utilize the same storage format.

        The serialized structure of a manifest is an unordered list of actions.

        The special action, "set", represents a package attribute.

        The reserved attribute, "fmri", represents the package and version
        described by this manifest.  It is available as a string via the
        attributes dictionary, and as an FMRI object from the fmri member.

        The list of manifest-wide reserved attributes is

        base_directory          Default base directory, for non-user images.
        fmri                    Package FMRI.
        isa                     Package is intended for a list of ISAs.
        platform                Package is intended for a list of platforms.
        relocatable             Suitable for User Image.

        All non-prefixed attributes are reserved to the framework.  Third
        parties may prefix their attributes with a reversed domain name, domain
        name, or stock symbol.  An example might be

        com.example,supported

        as an indicator that a specific package version is supported by the
        vendor, example.com.

        manifest.null is provided as the null manifest.  Differences against the
        null manifest result in the complete set of attributes and actions of
        the non-null manifest, meaning that all operations can be viewed as
        tranitions between the manifest being installed and the manifest already
        present in the image (which may be the null manifest).
        """

        def __init__(self):
                self.img = None
                self.fmri = None

                self.actions = []

        def __str__(self):
                r = ""

                if self.fmri != None:
                        r = r + "set name=fmri value=%s\n" % self.fmri

                for act in sorted(self.actions):
                        r = r + "%s\n" % act

                return r

        def difference(self, origin):
                """Return three lists of action pairs representing origin and
                destination actions.  The first list contains the pairs
                representing additions, the second list contains the pairs
                representing updates, and the third list contains the pairs
                represnting removals.  All three lists are in the order in which
                they should be executed."""
                # XXX Do we need to find some way to assert that the keys are
                # all unique?

                sdict = dict(
                    ((a.name, a.attrs.get(a.key_attr, id(a))), a)
                    for a in self.actions
                )
                odict = dict(
                    ((a.name, a.attrs.get(a.key_attr, id(a))), a)
                    for a in origin.actions
                )

                sset = set(sdict.keys())
                oset = set(odict.keys())

                added = [(None, sdict[i]) for i in sset - oset]
                removed = [(odict[i], None) for i in oset - sset]
		# XXX for now, we force license actions to always be
		# different to insure that existing license files for
		# new versions are always installed
                changed = [
                    (odict[i], sdict[i])
                    for i in oset & sset
                    if odict[i].different(sdict[i]) or i[0] == "license"
                ]

                # XXX Do changed actions need to be sorted at all?  This is
                # likely to be the largest list, so we might save significant
                # time by not sorting.  Should we sort above?  Insert into a
                # sorted list?

                # singlesort = lambda x: x[0] or x[1]
                addsort = lambda x: x[1]
                remsort = lambda x: x[0]
                removed.sort(key = remsort, reverse = True)
                added.sort(key = addsort)
                changed.sort(key = addsort)

                return (added, changed, removed)

        def combined_difference(self, origin):
                """Where difference() returns three lists, combined_difference()
                returns a single list of the concatenation of th three."""
                return list(chain(*self.difference(origin)))

        def humanized_differences(self, other):
                """Output expects that self is newer than other.  Use of sets
                requires that we convert the action objects into some marshalled
                form, otherwise set member identities are derived from the
                object pointers, rather than the contents."""

                l = self.difference(other)
                out = ""

                for src, dest in chain(*l):
                        if not src:
                                out += "+ %s\n" % str(dest)
                        elif not dest:
                                out += "- %s\n" + str(src)
                        else:
                                out += "%s -> %s\n" % (src, dest)
                return out

        def filter(self, filters):
                """Filter out actions from the manifest based on filters."""

                self.actions = [
                    a
                    for a in self.actions
                    if filter.apply_filters(a, filters)
                ]

        def duplicates(self):
                """Find actions in the manifest which are duplicates (i.e.,
                represent the same object) but which are not identical (i.e.,
                have all the same attributes)."""

                def fun(a):
                        """Return a key on which actions can be sorted."""
                        return a.name, a.attrs.get(a.key_attr, id(a))

                alldups = []
                for k, g in groupby(sorted(self.actions, key = fun), fun):
                        glist = list(g)
                        dups = set()
                        for i in range(len(glist) - 1):
                                if glist[i].different(glist[i + 1]):
                                        dups.add(glist[i])
                                        dups.add(glist[i + 1])
                        if dups:
                                alldups.append((k, dups))
                return alldups

        def set_fmri(self, img, fmri):
                self.img = img
                self.fmri = fmri

        @staticmethod
        def make_opener(img, fmri, action):
                def opener():
                        return retrieve.get_datastream(img, fmri, action.hash)
                return opener

        def set_content(self, str):
                """str is the text representation of the manifest"""

                # So we could build up here the type/key_attr dictionaries like
                # sdict and odict in difference() above, and have that be our
                # main datastore, rather than the simple list we have now.  If
                # we do that here, we can even assert that the "same" action
                # can't be in a manifest twice.  (The problem of having the same
                # action more than once in packages that can be installed
                # together has to be solved somewhere else, though.)
                for l in str.splitlines():
                        l = l.lstrip()
                        if not l or l[0] == "#":
                                continue

                        try:
                                action = actions.fromstr(l)
                        except KeyError:
                                raise SyntaxError, \
                                    "unknown action '%s'" % l.split()[0]

                        if action.attrs.has_key("path"):
                                np = action.attrs["path"].lstrip(os.path.sep)
                                action.attrs["path"] = np

                        if hasattr(action, "hash"):
                                action.data = \
                                    self.make_opener(self.img, self.fmri, action)

                        if not self.actions:
                                self.actions.append(action)
                        else:
                                bisect.insort(self.actions, action)

                return

        def search_dict(self):
                """Return the dictionary used for searching."""
                action_dict = {}
                for a in self.actions:
                        for k, v in a.generate_indices().iteritems():
                                if isinstance(v, list):
                                        if k in action_dict:
                                                action_dict[k].update(
                                                    dict((i, True) for i in v))
                                        else:
                                                action_dict[k] = \
                                                    dict((i, True) for i in v)
                                else:
                                        if k in action_dict:
                                                action_dict[k][v] = True
                                        else:
                                                action_dict[k] = { v: True }
                return action_dict

        def pickle(self, file):
                """Pickle the indices of the manifest's actions to the 'file'.
                """

                cPickle.dump(self.search_dict(), file,
                    protocol = cPickle.HIGHEST_PROTOCOL)

        def get(self, key, default):
                try:
                        return self[key]
                except KeyError:
                        return default

        def __getitem__(self, key):
                """Return the value for the package attribute 'key'.  If
                multiple attributes exist, return the first.  Raises KeyError if
                the attribute is not found."""
                try:
                        values = [
                            a.attrs["value"]
                            for a in self.actions
                            if a.name == "set" and a.attrs["name"] == key
                        ]
                except KeyError:
                        # This hides the fact that we had busted attribute
                        # actions in the manifest, but that's probably not so
                        # bad.
                        raise KeyError, key

                if values:
                        return values[0]

                raise KeyError, key

        def __setitem__(self, key, value):
                """Set the value for the package attribute 'key' to 'value'."""
                for a in self.actions:
                        if a.name == "set" and a.attrs["name"] == key:
                                a.attrs["value"] = value
                                return

                new_attr = AttributeAction(None, name=key, value=value)
                self.actions.append(new_attr)

        def __contains__(self, key):
                for a in self.actions:
                        if a.name == "set" and a.attrs["name"] == key:
                                return True
                return False

null = Manifest()
