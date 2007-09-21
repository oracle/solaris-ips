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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import bisect
import os
import re
import sha
import shutil
import time
import urllib
from itertools import groupby

import pkg.actions as actions
import pkg.fmri as fmri
import pkg.package as package
import pkg.client.retrieve as retrieve
import pkg.client.filter as filter

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

        The serialized structure of a manifest is an unordered list of package
        attributes, followed by an unordered list of actions (such as files to
        install).

        The special action, "set", represents an attribute setting.

        The reserved attribute, "fmri", represents the package and version
        described by this manifest.  It is available as a string via the
        attributes dictionary, and as an FMRI object from the fmri member.

        The list of manifest-wide reserved attributes is

        base_directory          Default base directory, for non-user images.
        fmri                    Package FMRI.
        isa                     Package is intended for a list of ISAs.
        licenses                Package contains software available under a list
                                of license terms.
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
                self.attributes = {}
                return

        def __str__(self):
                r = ""

                if self.fmri != None:
                        r = r + "set fmri = %s\n" % self.fmri

                for att in sorted(self.attributes.keys()):
                        r = r + "set %s = %s\n" % (att, self.attributes[att])

                for act in self.actions:
                        r = r + "%s\n" % act

                return r

        def difference(self, origin):
                """Return a list of action pairs representing origin and
                destination actions."""
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
                changed = [
                    (odict[i], sdict[i])
                    for i in oset & sset
                    if odict[i].different(sdict[i])
                ]

                # XXX Do changed actions need to be sorted at all?  This is
                # likely to be the largest list, so we might save significant
                # time by not sorting.  Should we sort above?  Insert into a
                # sorted list?

                # singlesort = lambda x: x[0] or x[1]
                addsort = lambda x: x[1]
                remsort = lambda x: x[0]
                removed.sort(key = remsort)
                added.sort(key = addsort)
                changed.sort(key = addsort)

                return removed + added + changed

        def display_differences(self, other):
                """Output expects that self is newer than other.  Use of sets
                requires that we convert the action objects into some marshalled
                form, otherwise set member identities are derived from the
                object pointers, rather than the contents."""

                l = self.difference(other)

                for src, dest in l:
                        if not src:
                                print "+", dest
                        elif not dest:
                                print "-", src
                        else:
                                print "%s -> %s" % (src, dest)

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

                def dup(a, b):
                        "Return whether or not two actions are duplicates."""
                        if not b:
                                return False
                        elif a.name == b.name and \
                            a.attrs.get(a.key_attr, id(a)) == \
                            b.attrs.get(b.key_attr, id(b)):
                                return True
                        else:
                                return False

                dups = []
                for k, g in groupby(sorted(self.actions, key = fun), fun):
                        gr = list(g)
                        if len(gr) > 1:
                                dups.append((k, gr))
                return dups

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
                        if re.match("^\s*(#.*)?$", l):
                                continue

                        try:
                                action = actions.fromstr(l)
                        except KeyError:
                                raise SyntaxError, \
                                    "unknown action '%s'" % l.split()[0]

                        if hasattr(action, "hash"):
                                action.data = \
                                    self.make_opener(self.img, self.fmri, action)

                        if not self.actions:
                                self.actions.append(action)
                        else:
                                bisect.insort(self.actions, action)

                return

null = Manifest()

if __name__ == "__main__":
        m1 = Manifest()

        x = """\
set com.sun,test=true
depend type=require fmri=pkg:/library/libc
file fff555fff mode=0555 owner=sch group=staff path=/usr/bin/i386/sort isa=i386
"""
        m1.set_content(x)

        print m1

        m2 = Manifest()

        y = """\
set com.sun,test=false
set com.sun,data=true
depend type=require fmri=pkg:/library/libc
file fff555ff9 mode=0555 owner=sch group=staff path=/usr/bin/i386/sort isa=i386
file eeeaaaeee mode=0555 owner=sch group=staff path=/usr/bin/amd64/sort isa=amd64

file ff555fff mode=0555 owner=root group=bin path=/kernel/drv/foo isa=i386
file ff555ffe mode=0555 owner=root group=bin path=/kernel/drv/amd64/foo isa=amd64
file ff555ffd mode=0644 owner=root group=bin path=/kernel/drv/foo.conf
"""

        m2.set_content(y)

        print m2

        m2.display_differences(m1)

        print null

        m2.display_differences(null)

        print
        m2.difference(m1)

        m3 = Manifest()
        t3 = """\
dir mode=0755 owner=root group=sys path=/bin
file 00000000 mode=0644 owner=root group=sys path=/bin/change
file 00000001 mode=0644 owner=root group=sys path=/bin/nochange
file 00000002 mode=0644 owner=root group=sys path=/bin/toberemoved
link path=/bin/change-link target=change
link path=/bin/nochange-link target=nochange
link path=/bin/change-target target=target1
link path=/bin/change-type target=random
"""
        m3.set_content(t3)

        m4 = Manifest()
        t4 = """\
dir mode=0755 owner=root group=sys path=/bin
file 0000000f mode=0644 owner=root group=sys path=/bin/change
file 00000001 mode=0644 owner=root group=sys path=/bin/nochange
file 00000003 mode=0644 owner=root group=sys path=/bin/wasadded
link path=/bin/change-link target=change
link path=/bin/nochange-link target=nochange
link path=/bin/change-target target=target2
dir mode=0755 owner=root group=sys path=/bin/change-type
"""
        m4.set_content(t4)

        print "\n" + 50 * "=" + "\n"
        m4.difference(m3)
        print "\n" + 50 * "=" + "\n"
        m4.difference(null)
