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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import exceptions
import re
import string

CONSTRAINT_NONE = 0

CONSTRAINT_RELEASE = 100
CONSTRAINT_RELEASE_MAJOR = 101
CONSTRAINT_RELEASE_MINOR = 102

CONSTRAINT_BRANCH = 200
CONSTRAINT_BRANCH_MAJOR = 101
CONSTRAINT_BRANCH_MINOR = 102

CONSTRAINT_SEQUENCE = 300

class IllegalDotSequence(exceptions.Exception):
        def __init__(self, args=None):
                self.args = args

class DotSequence(object):
        """A DotSequence is the typical "x.y.z" string used in software
        versioning.  We define the "major release" value and the "minor release"
        value as the first two numbers in the sequence."""

        def __init__(self, dotstring):
                m = re.match("\d+(\.\d)*", dotstring)
                if m == None:
                        raise IllegalDotSequence
                self.sequence = map(int, re.split("\.", dotstring))

        def __str__(self):
                return string.join(map(str, self.sequence), ".")

        def __ne__(self, other):
                if self.sequence != other.sequence:
                        return True
                return False

        def __eq__(self, other):
                if self.sequence == other.sequence:
                        return True
                return False

        def __lt__(self, other):
                if self.sequence < other.sequence:
                        return True
                return False

        def __gt__(self, other):
                if self.sequence > other.sequence:
                        return True
                return False

        def is_subsequence(self, other):
                """Return true if self is a "subsequence" of other, meaning that
                other and self have identical components, up to the length of
                self's sequence."""

                if len(self.sequence) > len(other.sequence):
                        return False

                for n in xrange(len(self.sequence) - 1):
                        if self.sequence[n] != other.sequence[n]:
                                return False

                return True

        def is_same_major(self, other):
                if self.sequence[0] == other.sequence[0]:
                        return True
                return False

        def is_same_minor(self, other):
                if not is_same_major(self, other):
                        return False

                if self.sequence[1] == other.sequence[1]:
                        return True
                return False

class IllegalVersion(exceptions.Exception):
        def __init__(self, args=None):
                self.args = args

class Version(object):
        """Version format is release[,build_release]-branch:timestamp, which we
        decompose into three DotSequences and the timestamp.  The
        release and branch DotSequences are interpreted normally, where v1 < v2
        implies that v2 is a later release or branch.  The build_release
        DotSequence records the system on which the package binaries were
        constructed.  Interpretation of the build_release by the client is that,
        in the case b1 < b2, a b1 package can be run on either b1 or b2
        systems,while a b2 package can only be run on a b2 system."""

        def __init__(self, version_string, build_string):
                # XXX If illegally formatted, raise exception.
                m = re.match("(\d+[\.\d]*),(\d+[\.\d]*)-(\d+[\.\d]*)\:(\d+)",
                    version_string)
                if m != None:
                        self.release = DotSequence(m.group(1))
                        self.build_release = DotSequence(m.group(2))
                        self.branch = DotSequence(m.group(3))
                        self.timestamp = m.group(4)
                        return

                assert build_string != None
                self.build_release = DotSequence(build_string)

                m = re.match("(\d+[\.\d]*)-(\d+[\.\d]*)\:(\d+)", version_string)
                if m != None:
                        self.release = DotSequence(m.group(1))
                        self.branch = DotSequence(m.group(2))
                        self.timestamp = int(m.group(3))
                        return

                # Sequence omitted?
                m = re.match("(\d[\.\d]*)-(\d[\.\d]*)", version_string)
                if m != None:
                        self.release = DotSequence(m.group(1))
                        self.branch = DotSequence(m.group(2))
                        self.timestamp = 0
                        return

                # Branch omitted?
                m = re.match("(\d[\.\d]*)", version_string)
                if m != None:
                        self.release = DotSequence(m.group(1))
                        self.branch = DotSequence("0")
                        self.timestamp = 0
                        return

                raise IllegalVersion

        def compatible_with_build(self, target):
                """target is a DotSequence for the target system."""
                if self.build_release < target:
                        return True
                return False

        def __str__(self):
                return "%s,%s-%s:%s" % (self.release, self.build_release,
                    self.branch, self.timestamp)

        def get_short_version(self):
                return "%s-%s" % (self.release, self.branch)

        def set_timestamp(self, new_ts):
                assert new_ts > self.timestamp
                self.timestamp = new_ts

        def get_timestamp(self):
                return self.timestamp

        def __ne__(self, other):
                if other == None:
                        return True

                if self.release == other.release and \
                    self.branch == other.branch and \
                    self.timestamp == other.timestamp:
                        return False
                return True

        def __eq__(self, other):
                if other == None:
                        return False

                if self.release == other.release and \
                    self.branch == other.branch and \
                    self.timestamp == other.timestamp:
                        return True
                return False

        def __lt__(self, other):
                if self.release < other.release:
                        return True
                if self.release != other.release:
                        return False
                if self.branch < other.branch:
                        return True
                if self.branch != other.branch:
                        return False
                if self.timestamp < other.timestamp:
                        return True
                return False

        def __gt__(self, other):
                if self.release > other.release:
                        return True
                if self.release != other.release:
                        return False
                if self.branch > other.branch:
                        return True
                if self.branch != other.branch:
                        return False
                if self.timestamp > other.timestamp:
                        return True
                return False

        def __cmp__(self, other):
                if self < other:
                        return -1
                if self > other:
                        return 1
                if self.build_release < other.build_release:
                        return -1
                if self.build_release > other.build_release:
                        return 1
                return 0

        def is_successor(self, other, constraint):
                """Evaluate true if self is a successor version to other.

                The loosest constraint is CONSTRAINT_NONE (None is treated
                equivalently, which is a simple test for self > other.  As we
                proceed through the policies we get stricter, depending on the
                selected constraint.

                For CONSTRAINT_RELEASE, self is a successor to other if all of
                the components of other's release match, and there are later
                components of self's version.  The branch and timestamp
                components are ignored.

                For CONSTRAINT_RELEASE_MAJOR and CONSTRAINT_RELEASE_MINOR, other
                is effectively truncated to [other[0]] and [other[0], other[1]]
                prior to being treated as for CONSTRAINT_RELEASE.

                Similarly for CONSTRAINT_BRANCH, the release fields of other and
                self are expected to be identical, and then the branches are
                compared as releases were for the CONSTRAINT_RELEASE* policies.
                """

                if constraint == None or constraint == CONSTRAINT_NONE:
                        return self > other

                if constraint == CONSTRAINT_RELEASE:
                        return other.release.is_subtimestamp(self.release)

                if constraint == CONSTRAINT_RELEASE_MAJOR:
                        return other.release.is_same_major(self.release)

                if constraint == CONSTRAINT_RELEASE_MINOR:
                        return other.release.is_same_minor(self.release)

                if constraint == CONSTRAINT_BRANCH:
                        return other.branch.is_subsequence(self.branch)

                if constraint == CONSTRAINT_BRANCH_MAJOR:
                        return other.branch.is_same_major(self.branch)

                if constraint == CONSTRAINT_BRANCH_MINOR:
                        return other.branch.is_same_minor(self.branch)

                raise ValueError, "constraint has unknown value"

if __name__ == "__main__":
        d1 = DotSequence("1.1.3")
        d2 = DotSequence("1.1.3")
        assert d1 == d2

        v1 = Version("5.5.1-10:6", "5.5.1")
        v2 = Version("5.5.1-10:8", "5.5.1")
        v3 = Version("5.5.1-10", "5.5")
        v4 = Version("5.5.1-6", "5.4")
        v5 = Version("5.6,1", "5.4")
        v6 = Version("5.7", "5.4")
        v7 = Version("5.10", "5.5.1")
        v8 = Version("5.10.1", "5.5.1")
        v9 = Version("5.11", "5.5.1")

        d3 = DotSequence("5.4")
        d4 = DotSequence("5.6")

        assert v1 < v2
        assert v4 < v3
        assert v4 < v5
        assert v6 > v5
        assert v7 < v8
        assert v9 > v8
        assert not v9 == v8
        assert v9 != v8

        assert not v9.compatible_with_build(d3)
        assert v9.compatible_with_build(d4)

        assert v2.is_successor(v1, CONSTRAINT_BRANCH)
        assert v4.is_successor(v2, CONSTRAINT_RELEASE)
        assert v6.is_successor(v5, CONSTRAINT_RELEASE_MAJOR)
        assert v8.is_successor(v7, CONSTRAINT_RELEASE_MAJOR)

