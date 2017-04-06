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

import calendar
import datetime
import time
import weakref

from six.moves import zip

CONSTRAINT_NONE = 0
CONSTRAINT_AUTO = 50

CONSTRAINT_RELEASE = 100
CONSTRAINT_RELEASE_MAJOR = 101
CONSTRAINT_RELEASE_MINOR = 102

CONSTRAINT_BRANCH = 200
CONSTRAINT_BRANCH_MAJOR = 101
CONSTRAINT_BRANCH_MINOR = 102

CONSTRAINT_SEQUENCE = 300

class VersionError(Exception):
        """Base exception class for all version errors."""

        def __init__(self, *args):
                Exception.__init__(self, *args)


class IllegalDotSequence(VersionError):
        """Used to indicate that the specified DotSequence is not valid."""

class DotSequence(list):
        """A DotSequence is the typical "x.y.z" string used in software
        versioning.  We define the "major release" value and the "minor release"
        value as the first two numbers in the sequence."""

        #
        # We employ the Flyweight design pattern for dotsequences, since they
        # are used immutably, are highly repetitive (0.5.11 over and over) and,
        # for what they contain, are relatively expensive memory-wise.
        #
        __dotseq_pool = weakref.WeakValueDictionary()

        @staticmethod
        def dotsequence_val(elem):
                # Do this first; if the string is zero chars or non-numeric
                # chars, this will throw.
                x = int(elem)
                if elem[0] == "-":
                        raise ValueError("Negative number")
                if x > 0 and elem[0] == "0":
                        raise ValueError("Zero padded number")
                return x

        def __new__(cls, dotstring):
                ds = DotSequence.__dotseq_pool.get(dotstring)
                if ds is None:
                        cls.__dotseq_pool[dotstring] = ds = \
                            list.__new__(cls)
                return ds

        def __init__(self, dotstring):
                # Was I already initialized?  See __new__ above.
                if len(self) != 0:
                        return

                try:
                        list.__init__(self,
                            list(map(DotSequence.dotsequence_val,
                                dotstring.split("."))))
                except ValueError:
                        raise IllegalDotSequence(dotstring)

                if len(self) == 0:
                        raise IllegalDotSequence("Empty DotSequence")

        def __str__(self):
                return ".".join(map(str, self))

        def __hash__(self):
                return hash(tuple(self))

        def is_subsequence(self, other):
                """Return true if self is a "subsequence" of other, meaning that
                other and self have identical components, up to the length of
                self's sequence."""

                if len(self) > len(other):
                        return False

                for a, b in zip(self, other):
                        if a != b:
                                return False
                return True

        def is_same_major(self, other):
                """ Test if DotSequences have the same major number """
                return self[0] == other[0]

        def is_same_minor(self, other):
                """ Test if DotSequences have the same major and minor num """
                return self[0] == other[0] and self[1] == other[1]


class MatchingDotSequence(DotSequence):
        """A subclass of DotSequence with (much) weaker rules about its format.
        This is intended to accept user input with wildcard characters."""

        #
        # We employ the Flyweight design pattern for dotsequences, since they
        # are used immutably, are highly repetitive (0.5.11 over and over) and,
        # for what they contain, are relatively expensive memory-wise.
        #
        __matching_dotseq_pool = weakref.WeakValueDictionary()

        @staticmethod
        def dotsequence_val(elem):
                # Do this first; if the string is zero chars or non-numeric
                # chars (other than "*"), an exception will be raised.
                if elem == "*":
                        return elem

                return DotSequence.dotsequence_val(elem)

        def __new__(cls, dotstring):
                ds = MatchingDotSequence.__matching_dotseq_pool.get(dotstring,
                    None)
                if ds is not None:
                        return ds

                ds = list.__new__(cls)
                cls.__matching_dotseq_pool[dotstring] = ds
                return ds

        def __init__(self, dotstring):
                try:
                        list.__init__(self,
                            list(map(self.dotsequence_val,
                                dotstring.split("."))))
                except ValueError:
                        raise IllegalDotSequence(dotstring)

                if len(self) == 0:
                        raise IllegalDotSequence("Empty MatchingDotSequence")

        def __ne__(self, other):
                if not isinstance(other, DotSequence):
                        return True

                ls = len(self)
                lo = len(other)
                for i in range(max(ls, lo)):
                        try:
                                if self[i] != other[i] and ("*" not in (self[i],
                                    other[i])):
                                        return True
                        except IndexError:
                                if ls < (i + 1) and "*" not in (self[-1],
                                    other[i]):
                                        return True
                                if lo < (i + 1) and "*" not in (self[i],
                                    other[-1]):
                                        return True
                return False

        def __eq__(self, other):
                if not isinstance(other, DotSequence):
                        return False

                ls = len(self)
                lo = len(other)
                for i in range(max(ls, lo)):
                        try:
                                if self[i] != other[i] and ("*" not in (self[i],
                                    other[i])):
                                        return False
                        except IndexError:
                                if ls < (i + 1) and "*" not in (self[-1],
                                    other[i]):
                                        return False
                                if lo < (i + 1) and "*" not in (self[i],
                                    other[-1]):
                                        return False
                return True

        __hash__ = DotSequence.__hash__

        def is_subsequence(self, other):
                """Return true if self is a "subsequence" of other, meaning that
                other and self have identical components, up to the length of
                self's sequence or self or other is '*'."""

                if str(self) == "*" or str(other) == "*":
                        return True

                if len(self) > len(other):
                        return False

                for a, b in zip(self, other):
                        if a != b:
                                return False
                return True

        def is_same_major(self, other):
                """Test if DotSequences have the same major number, or major
                is '*'."""
                return self[0] == "*" or other[0] == "*" or self[0] == other[0]

        def is_same_minor(self, other):
                """ Test if DotSequences have the same major and minor num."""
                return self[0] == "*" or other[0] == "*" or self[1] == "*" or \
                    other[1] == "*" or \
                    (self[0] == other[0] and self[1] == other[1])


class IllegalVersion(VersionError):
        """Used to indicate that the specified version string is not valid."""

class Version(object):
        """Version format is release[,build_release]-branch:datetime, which we
        decompose into three DotSequences and a date string.  Time
        representation is in the ISO8601-compliant form "YYYYMMDDTHHMMSSZ",
        referring to the UTC time associated with the version.  The release and
        branch DotSequences are interpreted normally, where v1 < v2 implies that
        v2 is a later release or branch.  The build_release DotSequence records
        the system on which the package binaries were constructed."""

        __slots__ = ["release", "branch", "build_release", "timestr"]

        def __init__(self, version_string, build_string=None):
                # XXX If illegally formatted, raise exception.

                if not version_string:
                        raise IllegalVersion("Version cannot be empty")

                #
                # Locate and extract the time, branch, and build strings,
                # if specified.  Error checking happens in the second half of
                # the routine.  In the event that a given part of the input is
                # signalled but empty (for example: '0.3-' or '0.3-3.0:',
                # we'll produce an empty (but not None) string for that portion.
                #

                # Locate and extract the time string, if specified.
                timeidx = version_string.find(":")
                if timeidx != -1:
                        timestr = version_string[timeidx + 1:]
                else:
                        timeidx = None
                        timestr = None

                # Locate and extract the branch string, if specified.
                branchidx = version_string.find("-")
                if branchidx != -1:
                        branch = version_string[branchidx + 1:timeidx]
                else:
                        branchidx = timeidx
                        branch = None

                # Locate and extract the build string, if specified.
                buildidx = version_string.find(",")
                if buildidx != -1:
                        build = version_string[buildidx + 1:branchidx]
                else:
                        buildidx = branchidx
                        build = None

                if buildidx == 0:
                        raise IllegalVersion("Versions must have a release value")

                #
                # Error checking and conversion from strings to objects
                # begins here.
                #
                try:
                        self.release = DotSequence(version_string[:buildidx])

                        if branch is not None:
                                self.branch = DotSequence(branch)
                        else:
                                self.branch = None

                        if build is not None:
                                self.build_release = DotSequence(build)
                        else:
                                if build_string is None:
                                        build_string = "5.11"
                                self.build_release = DotSequence(build_string)

                except IllegalDotSequence as e:
                        raise IllegalVersion("Bad Version: {0}".format(e))

                #
                # In 99% of the cases in which we use date and time, it's solely
                # for comparison.  Since the ISO date string lexicographically
                # collates in date order, we just hold onto the string-
                # converting it to anything else is expensive.
                #
                if timestr is not None:
                        if len(timestr) != 16 or timestr[8] != "T" \
                            or timestr[15] != "Z":
                                raise IllegalVersion("Time must be ISO8601 format.")
                        try:
                                dateint = int(timestr[0:8])
                                timeint = int(timestr[9:15])
                                datetime.datetime(dateint // 10000,
                                    (dateint // 100) % 100,
                                    dateint % 100,
                                    timeint // 10000,
                                    (timeint // 100) % 100,
                                    timeint % 100)
                        except ValueError:
                                raise IllegalVersion("Time must be ISO8601 format.")

                        self.timestr = timestr
                else:
                        self.timestr = None

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                return str(obj)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                return Version(state, None)

        def __str__(self):
                outstr = str(self.release) + "," + str(self.build_release)
                if self.branch:
                        outstr += "-" + str(self.branch)
                if self.timestr:
                        outstr += ":" + self.timestr
                return outstr

        def __repr__(self):
                return "<pkg.fmri.Version '{0}' at {1:#x}>".format(self,
                    id(self))

        def get_version(self, include_build=True):
                if include_build:
                        outstr = str(self.release) + "," + str(self.build_release)
                else:
                        outstr = str(self.release)
                if self.branch:
                        outstr += "-" + str(self.branch)
                if self.timestr:
                        outstr += ":" + self.timestr
                return outstr

        def get_short_version(self):
                branch_str = ""
                if self.branch is not None:
                        branch_str = "-{0}".format(self.branch)
                return "{0}{1}".format(self.release, branch_str)

        def set_timestamp(self, timestamp=datetime.datetime.utcnow()):
                assert type(timestamp) == datetime.datetime
                assert timestamp.tzname() == None or timestamp.tzname() == "UTC"
                self.timestr = timestamp.strftime("%Y%m%dT%H%M%SZ")

        def get_timestamp(self):
                if not self.timestr:
                        return None
                t = time.strptime(self.timestr, "%Y%m%dT%H%M%SZ")
                return datetime.datetime.utcfromtimestamp(calendar.timegm(t))

        def __ne__(self, other):
                if not isinstance(other, Version):
                        return True

                if self.release == other.release and \
                    self.branch == other.branch and \
                    self.timestr == other.timestr:
                        return False
                return True

        def __eq__(self, other):
                if not isinstance(other, Version):
                        return False

                if self.release == other.release and \
                    self.branch == other.branch and \
                    self.timestr == other.timestr:
                        return True
                return False

        def __lt__(self, other):
                """Returns True if 'self' comes before 'other', and vice versa.

                If exactly one of the release values of the versions is None,
                then that version is less than the other.  The same applies to
                the branch and timestamp components.
                """
                if not isinstance(other, Version):
                        return False

                if self.release < other.release:
                        return True
                if self.release != other.release:
                        return False

                if self.branch != other.branch:
                        if self.branch is None and other.branch:
                                return True
                        if self.branch and other.branch is None:
                                return False
                        if self.branch < other.branch:
                                return True
                        return False

                if self.timestr != other.timestr:
                        if self.timestr is None and other.timestr:
                                return True
                        if self.timestr and other.timestr is None:
                                return False
                        if self.timestr < other.timestr:
                                return True
                return False

        def __gt__(self, other):
                """Returns True if 'self' comes after 'other', and vice versa.

                If exactly one of the release values of the versions is None,
                then that version is less than the other.  The same applies to
                the branch and timestamp components.
                """
                if not isinstance(other, Version):
                        return True

                if self.release > other.release:
                        return True
                if self.release != other.release:
                        return False

                if self.branch != other.branch:
                        if self.branch and other.branch is None:
                                return True
                        if self.branch is None and other.branch:
                                return False
                        if self.branch > other.branch:
                                return True
                        return False

                if self.timestr != other.timestr:
                        if self.timestr and other.timestr is None:
                                return True
                        if self.timestr is None and other.timestr:
                                return False
                        if self.timestr > other.timestr:
                                return True
                return False

        def __le__(self, other):
                return not self > other

        def __ge__(self, other):
                return not self < other

        def __hash__(self):
                # If a timestamp is present, it's enough to hash on, and is
                # nicely unique.  If not, use release and branch, which are
                # not very unique.
                if self.timestr:
                        return hash(self.timestr)
                else:
                        return hash((self.release, self.branch))

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

                if constraint == CONSTRAINT_AUTO and \
                    type(other) == MatchingVersion:
                        if other.release and self.release:
                                if not other.release.is_subsequence(
                                    self.release):
                                        return False
                        elif other.release and str(other.release) != "*":
                                return False

                        if other.branch and self.branch:
                                if not other.branch.is_subsequence(self.branch):
                                        return False
                        elif other.branch and str(other.branch) != "*":
                                return False

                        if self.timestr and other.timestr:
                                if not (other.timestr == self.timestr or \
                                    other.timestr == "*"):
                                        return False
                        elif other.timestr and str(other.timestr) != "*":
                                return False

                        return True
                elif constraint == CONSTRAINT_AUTO:
                        if other.release and self.release:
                                if not other.release.is_subsequence(
                                    self.release):
                                        return False
                        elif other.release:
                                return False

                        if other.branch and self.branch:
                                if not other.branch.is_subsequence(self.branch):
                                        return False
                        elif other.branch:
                                return False

                        if self.timestr and other.timestr:
                                if other.timestr != self.timestr:
                                        return False
                        elif other.timestr:
                                return False

                        return True

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

                raise ValueError("constraint has unknown value")

        @classmethod
        def split(self, ver):
                """Takes an assumed valid version string and splits it into
                its components as a tuple of the form ((release, build_release,
                branch, timestr), short_ver)."""

                # Locate and extract the time string.
                timeidx = ver.find(":")
                if timeidx != -1:
                        timestr = ver[timeidx + 1:]
                else:
                        timeidx = None
                        timestr = None

                # Locate and extract the branch string.
                branchidx = ver.find("-")
                if branchidx != -1:
                        branch = ver[branchidx + 1:timeidx]
                else:
                        branchidx = timeidx
                        branch = None

                # Locate and extract the build string.
                buildidx = ver.find(",")
                if buildidx != -1:
                        build = ver[buildidx + 1:branchidx]
                else:
                        buildidx = branchidx
                        build = None

                release = ver[:buildidx]

                build_release = ""
                if build is not None:
                        build_release = build

                if branch is not None:
                        short_ver = release + "-" + branch
                else:
                        short_ver = release
                return (release, build_release, branch, timestr), short_ver


class MatchingVersion(Version):
        """An alternative for Version with (much) weaker rules about its format.
        This is intended to accept user input with globbing characters."""


        __slots__ = ["match_latest", "__original"]

        def __init__(self, version_string, build_string=None):
                if version_string is None or not len(version_string):
                        raise IllegalVersion("Version cannot be empty")

                if version_string == "latest":
                        # Treat special "latest" syntax as equivalent to '*' for
                        # version comparison purposes.
                        self.match_latest = True
                        version_string = "*"
                else:
                        self.match_latest = False

                (release, build_release, branch, timestr), ignored = \
                    self.split(version_string)
                if not build_release:
                        build_release = build_string

                #
                # Error checking and conversion from strings to objects
                # begins here.
                #
                try:
                        #
                        # Every component of the version (after the first) is
                        # optional, if not provided, assume "*" (wildcard).
                        #
                        for attr, vals in (
                            ('release', (release,)),
                            ('build_release', (build_release, "*")),
                            ('branch', (branch, "*")),
                            ('timestr', (timestr, "*"))):
                                for val in vals:
                                        if not val:
                                                continue
                                        if attr != 'timestr':
                                                val = MatchingDotSequence(val)
                                        setattr(self, attr, val)
                                        break
                except IllegalDotSequence as e:
                        raise IllegalVersion("Bad Version: {0}".format(e))

                outstr = str(release)
                if build_release is not None:
                        outstr += "," + str(build_release)
                if branch is not None:
                        outstr += "-" + str(branch)
                if timestr is not None:
                        outstr += ":" + timestr

                # Store the re-constructed input value for use as a string
                # representation of this object.
                self.__original = outstr

        def __str__(self):
                if self.match_latest:
                        return "latest"
                return self.__original

        def get_timestamp(self):
                if self.timestr == "*":
                        return "*"
                return Version.get_timestamp(self)

        def __ne__(self, other):
                if not isinstance(other, Version):
                        return True

                if self.release == other.release and \
                    self.build_release == other.build_release and \
                    self.branch == other.branch and \
                    ((self.timestr == other.timestr) or ("*" in (self.timestr,
                        other.timestr))):
                        return False
                return True

        def __eq__(self, other):
                if not isinstance(other, Version):
                        return False

                if self.release == other.release and \
                    self.build_release == other.build_release and \
                    self.branch == other.branch and \
                    ((self.timestr == other.timestr) or ("*" in (self.timestr,
                        other.timestr))):
                        return True
                return False

        def __lt__(self, other):
                """Returns True if 'self' comes before 'other', and vice versa.

                If exactly one of the release values of the versions is None or
                "*", then that version is less than the other.  The same applies
                to the branch and timestamp components.
                """
                if not isinstance(other, Version):
                        return False

                if str(self.release) == "*" and str(other.release) != "*":
                        return True
                if self.release < other.release:
                        return True
                if self.release != other.release:
                        return False

                if str(self.build_release) == "*" and \
                    str(other.build_release) != "*":
                        return True
                if self.build_release < other.build_release:
                        return True
                if self.build_release != other.build_release:
                        return False

                if str(self.branch) == "*" and str(other.branch) != "*":
                        return True
                if self.branch < other.branch:
                        return True
                if self.branch != other.branch:
                        return False

                if self.timestr == "*" and other.timestr != "*":
                        return True

                return self.timestr < other.timestr

        def __gt__(self, other):
                """Returns True if 'self' comes after 'other', and vice versa.

                If exactly one of the release values of the versions is None or
                "*", then that version is less than the other.  The same applies
                to the branch and timestamp components.
                """
                if not isinstance(other, Version):
                        return True

                if str(self.release) == "*" and str(other.release) != "*":
                        return False
                if self.release > other.release:
                        return True
                if self.release != other.release:
                        return False

                if str(self.build_release) == "*" and \
                    str(other.build_release) != "*":
                        return False
                if self.build_release > other.build_release:
                        return True
                if self.build_release != other.build_release:
                        return False

                if str(self.branch) == "*" and str(other.branch) != "*":
                        return False
                if self.branch > other.branch:
                        return True
                if self.branch != other.branch:
                        return False

                if self.timestr == "*" and other.timestr != "*":
                        return False

                return self.timestr > other.timestr

        def __hash__(self):
                # If a timestamp is present, it's enough to hash on, and is
                # nicely unique.  If not, use release and branch, which are
                # not very unique.
                if self.timestr and self.timestr != "*":
                        return hash(self.timestr)
                else:
                        return hash((self.release, self.branch))
