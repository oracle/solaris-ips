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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import calendar
import datetime
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

        @staticmethod
        def dotsequence_val(elem):
                # Do this first; if the string is zero chars or non-numeric
                # chars, this will throw.
                x = int(elem)
                if elem[0] == "-":
                        raise ValueError, "Negative number"
                if x > 0 and elem[0] == "0":
                        raise ValueError, "Zero padded number"
                return x

        def __init__(self, dotstring):
                try:
                        list.__init__(self,
                            map(DotSequence.dotsequence_val,
                                dotstring.split(".")))
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

        @staticmethod
        def dotsequence_val(elem):
                # Do this first; if the string is zero chars or non-numeric
                # chars (other than "*"), an exception will be raised.
                if elem == "*":
                        return elem

                return DotSequence.dotsequence_val(elem)

        def __init__(self, dotstring):
                try:
                        list.__init__(self,
                            map(self.dotsequence_val,
                                dotstring.split(".")))
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


class IllegalVersion(VersionError):
        """Used to indicate that the specified version string is not valid."""

class Version(object):
        """Version format is release[,build_release]-branch:datetime, which we
        decompose into three DotSequences and a date string.  Time
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

                if not version_string:
                        raise IllegalVersion, "Version cannot be empty"

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
                        raise IllegalVersion, \
                            "Versions must have a release value"

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
                                        raise IllegalVersion("No build version "
                                            "provided in Version constructor: "
                                            "(%s, %s)" % (version_string,
                                            build_string))
                                self.build_release = DotSequence(build_string)

                except IllegalDotSequence, e:
                        raise IllegalVersion("Bad Version: %s" % e)

                #
                # In 99% of the cases in which we use date and time, it's solely
                # for comparison.  Since the ISO date string lexicographically
                # collates in date order, we just hold onto the string-
                # converting it to anything else is expensive.
                #
                if timestr is not None:
                        if len(timestr) != 16 or timestr[8] != "T" \
                            or timestr[15] != "Z":
                                raise IllegalVersion, \
                                    "Time must be ISO8601 format."
                        try:
                                dateint = int(timestr[0:8])
                                timeint = int(timestr[9:15])
                                datetime.datetime(dateint / 10000,
                                    (dateint / 100) % 100,
                                    dateint % 100,
                                    timeint / 10000,
                                    (timeint / 100) % 100,
                                    timeint % 100)
                        except ValueError:
                                raise IllegalVersion, \
                                    "Time must be ISO8601 format."

                        self.timestr = timestr
                else:
                        self.timestr = None

        def compatible_with_build(self, target):
                """target is a DotSequence for the target system."""
                if self.build_release < target:
                        return True
                return False

        def __str__(self):
                outstr = str(self.release) + "," + str(self.build_release)
                if self.branch:
                        outstr += "-" + str(self.branch)
                if self.timestr:
                        outstr += ":" + self.timestr
                return outstr

        def __repr__(self):
                return "<pkg.fmri.Version '%s' at %#x>" % (self, id(self))

        def get_short_version(self):
                branch_str = ""
                if self.branch is not None:
                        branch_str = "-%s" % self.branch
                return "%s%s" % (self.release, branch_str)

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

                if self.branch < other.branch:
                        return True
                if self.branch != other.branch:
                        return False

                return self.timestr < other.timestr

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

                if self.branch > other.branch:
                        return True
                if self.branch != other.branch:
                        return False

                return self.timestr > other.timestr

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

                        if self.timestr and other.timestr:
                                if other.timestr == self.timestr:
                                        date_match = True
                        elif not other.timestr:
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


class MatchingVersion(Version):
        """An alternative for Version with (much) weaker rules about its format.
        This is intended to accept user input with globbing characters."""

        def __init__(self, version_string, build_string):
                # XXX If illegally formatted, raise exception.

                if version_string is None or not len(version_string):
                        raise IllegalVersion, "Version cannot be empty"

                release = None
                build_release = None
                branch = None
                timestr = None
                try:
                        release, rem = version_string.split(",")

                except ValueError:
                        release = version_string
                else:
                        try:
                                build_release, rem = rem.split("-")
                        except ValueError:
                                build_release = rem
                        else:
                                try:
                                        branch, rem = rem.split(":")
                                except (TypeError, ValueError):
                                        branch = rem
                                else:
                                        timestr = rem

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
                            ('build_release', (build_release, build_string,
                            "*")),
                            ('branch', (branch, "*")),
                            ('timestr', (timestr, "*"))):
                                for val in vals:
                                        if val is None:
                                                continue
                                        if attr != 'timestr':
                                                val = MatchingDotSequence(val)
                                        setattr(self, attr, val)
                                        break
                except IllegalDotSequence, e:
                        raise IllegalVersion("Bad Version: %s" % e)

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

                if self.release == "*" and other.release != "*":
                        return True
                if self.release < other.release:
                        return True
                if self.release != other.release:
                        return False

                if self.build_release == "*" and other.build_release != "*":
                        return True
                if self.build_release < other.build_release:
                        return True
                if self.build_release != other.build_release:
                        return False

                if self.branch == "*" and other.branch != "*":
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

                if self.release == "*" and other.release != "*":
                        return False
                if self.release > other.release:
                        return True
                if self.release != other.release:
                        return False

                if self.build_release == "*" and other.build_release != "*":
                        return False
                if self.build_release > other.build_release:
                        return True
                if self.build_release != other.build_release:
                        return False

                if self.branch == "*" and other.branch != "*":
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
