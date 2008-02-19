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

import datetime
import exceptions
import time

CONSTRAINT_NONE = 0
CONSTRAINT_AUTO = 50

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
                try:
                        self.sequence = map(int, dotstring.split("."))
                except ValueError:
                        raise IllegalDotSequence(dotstring)

        def __str__(self):
                return ".".join(map(str, self.sequence))

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

                for a, b in zip(self.sequence, other.sequence):
                        if a != b:
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
        """Version format is release[,build_release]-branch:datetime, which we
        decompose into three DotSequences and the datetime.  The text
        representation is in the ISO8601-compliant form "YYYYMMDDTHHMMSSZ",
        referring to the UTC time associated with the version.  The release and
        branch DotSequences are interpreted normally, where v1 < v2 implies that
        v2 is a later release or branch.  The build_release DotSequence records
        the system on which the package binaries were constructed.
        Interpretation of the build_release by the client is that, in the case
        b1 < b2, a b1 package can be run on either b1 or b2 systems,while a b2
        package can only be run on a b2 system."""

        def __init__(self, version_string, build_string):
                # XXX If illegally formatted, raise exception.

                try:
                        timeidx = version_string.index(":")
                        timestr = version_string[timeidx + 1:]
                except ValueError:
                        timeidx = None
                        timestr = None

                try:
                        branchidx = version_string.index("-")
                        branch = version_string[branchidx + 1:timeidx]
                except ValueError:
                        branchidx = timeidx
                        branch = None

                try:
                        buildidx = version_string.index(",")
                        build = version_string[buildidx + 1:branchidx]
                except ValueError:
                        buildidx = branchidx
                        build = None

                if buildidx == 0:
                        raise IllegalVersion, \
                            "Versions must have a release value."

                self.release = DotSequence(version_string[:buildidx])

                if branch:
                        self.branch = DotSequence(branch)
                else:
                        self.branch = None

                if build:
                        self.build_release = DotSequence(build)
                else:
                        assert build_string is not None
                        self.build_release = DotSequence(build_string)

                if timestr:
                        if timestr.endswith("Z") and "T" in timestr:
                                self.datetime = datetime.datetime(
                                    *time.strptime(timestr, "%Y%m%dT%H%M%SZ")[0:6])
                        else:
                                self.datetime = datetime.datetime.fromtimestamp(
                                    float(timestr))
                else:
                        self.datetime = None

                # raise IllegalVersion

        def compatible_with_build(self, target):
                """target is a DotSequence for the target system."""
                if self.build_release < target:
                        return True
                return False

        def __str__(self):
                branch_str = date_str = ""
                if self.branch:
                        branch_str = "-%s" % self.branch
                if self.datetime:
                        date_str = ":%s" % \
                            self.datetime.strftime("%Y%m%dT%H%M%SZ")
                return "%s,%s%s%s" % (self.release, self.build_release,
                    branch_str, date_str)

        def get_short_version(self):
                branch_str = ""
                if self.branch:
                        branch_str = "-%s" % self.branch
                return "%s%s" % (self.release, branch_str)

        def set_timestamp(self, timestamp):
                self.datetime = datetime.datetime.fromtimestamp(timestamp)

        def get_datetime(self):
                return self.datetime

        def __ne__(self, other):
                if other == None:
                        return True

                if self.release == other.release and \
                    self.branch == other.branch and \
                    self.datetime == other.datetime:
                        return False
                return True

        def __eq__(self, other):
                if other == None:
                        return False

                if self.release == other.release and \
                    self.branch == other.branch and \
                    self.datetime == other.datetime:
                        return True
                return False

        def __lt__(self, other):
                """Returns True if 'self' comes before 'other', and vice versa.

                If exactly one of the release values of the versions is None,
                then that version is less than the other.  The same applies to
                the branch and timestamp components.
                """
                if other == None:
                        return False

                if self.release and other.release:
                        if self.release < other.release:
                                return True
                        if self.release != other.release:
                                return False
                elif self.release and not other.release:
                        return False
                elif not self.release and other.release:
                        return True

                if self.branch and other.branch:
                        if self.branch < other.branch:
                                return True
                        if self.branch != other.branch:
                                return False
                elif self.branch and not other.branch:
                        return False
                elif not self.branch and other.branch:
                        return True

                if self.datetime and other.datetime:
                        if self.datetime < other.datetime:
                                return True
                elif self.datetime and not other.datetime:
                        return False
                elif not self.datetime and other.datetime:
                        return True

                return False

        def __gt__(self, other):
                """Returns True if 'self' comes after 'other', and vice versa.

                If exactly one of the release values of the versions is None,
                then that version is less than the other.  The same applies to
                the branch and timestamp components.
                """
                if other == None:
                        return False

                if self.release and other.release:
                        if self.release > other.release:
                                return True
                        if self.release != other.release:
                                return False
                elif self.release and not other.release:
                        return True
                elif not self.release and other.release:
                        return False

                if self.branch and other.branch:
                        if self.branch > other.branch:
                                return True
                        if self.branch != other.branch:
                                return False
                elif self.branch and not other.branch:
                        return True
                elif not self.branch and other.branch:
                        return False

                if self.datetime and other.datetime:
                        if self.datetime > other.datetime:
                                return True
                elif self.datetime and not other.datetime:
                        return True
                elif not self.datetime and other.datetime:
                        return False

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

                Slightly less loose is CONSTRAINT_AUTO.  In this case, if any of
                the release, branch, or timestamp components is None, it acts as
                a "don't care" value -- a versioned component always succeeds
                None.

                For CONSTRAINT_RELEASE, self is a successor to other if all of
                the components of other's release match, and there are later
                components of self's version.  The branch and datetime
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

                if constraint == CONSTRAINT_AUTO:
                        release_match = branch_match = date_match = False

                        if other.release and self.release:
                                if other.release.is_subsequence(self.release):
                                        release_match = True
                        elif not other.release:
                                release_match = True

                        if other.branch and self.branch:
                                if other.branch.is_subsequence(self.branch):
                                        branch_match = True
                        elif not other.branch:
                                branch_match = True

                        if self.datetime and other.datetime:
                                if other.datetime < self.datetime:
                                        date_match = True
                        elif not other.datetime:
                                date_match = True

                        return release_match and branch_match and date_match

                if constraint == CONSTRAINT_RELEASE:
                        return other.release.is_subsequence(self.release)

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

