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

import fnmatch
import re
from six.moves.urllib.parse import quote

from pkg.version import Version, VersionError

# In order to keep track of what publisher is presently the preferred publisher,
# a prefix is included ahead of the name of the publisher.  If this prefix is
# present, the publisher is considered to be the current preferred publisher for
# the image.  This is where we define the prefix, since it's used primarily in
# the FMRI.  PREF_PUB_PFX => preferred publisher prefix.
PREF_PUB_PFX = "_PRE"

#
# For is_same_publisher(), we need a version of this constant with the
# trailing _ attached.
#
PREF_PUB_PFX_ = PREF_PUB_PFX + "_"

g_valid_pkg_name = \
    re.compile("^[A-Za-z0-9][A-Za-z0-9_\-\.\+]*(/[A-Za-z0-9][A-Za-z0-9_\-\.\+]*)*$")

class FmriError(Exception):
        """Base exception class for FMRI errors."""

        def __init__(self, fmri):
                Exception.__init__(self)
                self.fmri = fmri


class IllegalFmri(FmriError):

        BAD_VERSION = 1
        BAD_PACKAGENAME = 2
        SYNTAX_ERROR = 3

        msg_prefix = "Illegal FMRI"

        def __init__(self, fmri, reason, detail=None, nested_exc=None):
                FmriError.__init__(self, fmri)
                self.reason = reason
                self.detail = detail
                self.nested_exc = nested_exc

        def __str__(self):
                outstr = "{0} '{1}': ".format(self.msg_prefix, self.fmri)
                if self.reason == IllegalFmri.BAD_VERSION:
                        return outstr + str(self.nested_exc)
                if self.reason == IllegalFmri.BAD_PACKAGENAME:
                        return outstr + "Invalid Package Name: " + self.detail
                if self.reason == IllegalFmri.SYNTAX_ERROR:
                        return outstr + self.detail


class IllegalMatchingFmri(IllegalFmri):
        msg_prefix = "Illegal matching pattern"


class MissingVersionError(FmriError):
        """Used to indicate that the requested operation is not supported for
        the fmri since version information is missing."""

        def __str__(self):
                return _("FMRI '{0}' is missing version information.").format(
                    self.fmri)


class PkgFmri(object):
        """The publisher is the anchor of a package namespace.  Clients can
        choose to take packages from multiple publishers, and specify a default
        search path.  In general, package names may also be prefixed by a domain
        name, reverse domain name, or a stock symbol to avoid conflict.  The
        unprefixed namespace is expected to be managed by architectural review.

        The primary equivalence relationship assumes that packages of the same
        package name are forwards compatible across all versions of that
        package, and that higher build release versions are superior
        publications than lower build release versions."""

        # Stored in a class variable so that subclasses can override
        valid_pkg_name = g_valid_pkg_name

        __slots__ = ["version", "publisher", "pkg_name", "_hash", "__weakref__"]

        def __init__(self, fmri=None, build_release=None, publisher=None,
            name=None, version=None):
                if fmri is not None:
                        fmri = fmri.rstrip()

                        veridx, nameidx, pubidx = \
                            PkgFmri._gen_fmri_indexes(fmri)

                        if pubidx != None:
                                # Always use publisher information provided in
                                # FMRI string.  (It could be ""; pkg:///name is
                                # valid.)
                                publisher = fmri[pubidx:nameidx - 1]

                        if veridx != None:
                                self.pkg_name = fmri[nameidx:veridx]
                                try:
                                        self.version = Version(
                                            fmri[veridx + 1:], build_release)
                                except VersionError as iv:
                                        raise IllegalFmri(fmri,
                                            IllegalFmri.BAD_VERSION,
                                            nested_exc=iv)
                        else:
                                self.pkg_name = fmri[nameidx:]
                                self.version = None
                else:
                        # pkg_name and version must be explicitly set.
                        self.pkg_name = name
                        if version:
                                self.version = Version(version, build_release)
                        else:
                                self.version = None

                # Ensure publisher is always None if one was not specified.
                if publisher:
                        self.publisher = publisher
                else:
                        self.publisher = None

                if not self.pkg_name:
                        raise IllegalFmri(fmri, IllegalFmri.SYNTAX_ERROR,
                            detail="Missing package name")

                if not self.valid_pkg_name.match(self.pkg_name):
                        raise IllegalFmri(fmri, IllegalFmri.BAD_PACKAGENAME,
                            detail=self.pkg_name)

                self._hash = None

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                return str(obj)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""
                return PkgFmri(state)

        def copy(self):
                return PkgFmri(str(self))

        @staticmethod
        def _gen_fmri_indexes(fmri):
                """Return a tuple of offsets, used to extract different
                components of the FMRI."""

                veridx = fmri.rfind("@")
                if veridx == -1:
                        veridx = None

                pubidx = None
                if fmri.startswith("pkg://"):
                        nameidx = fmri.find("/", 6, veridx)
                        if nameidx == -1:
                                raise IllegalFmri(fmri,
                                    IllegalFmri.SYNTAX_ERROR,
                                    detail=_("Missing '/' after "
                                        "publisher name"))

                        # Publisher starts after //.
                        pubidx = 6

                        # Name starts after / which terminates publisher
                        nameidx += 1

                elif fmri.startswith("pkg:/"):
                        # Name starts after / which terminates scheme
                        nameidx = 5
                elif fmri.startswith("//"):
                        nameidx = fmri.find("/", 2, veridx)
                        if nameidx == -1:
                                raise IllegalFmri(fmri,
                                    IllegalFmri.SYNTAX_ERROR,
                                    detail=_("Missing '/' after "
                                        "publisher name"))

                        # Publisher starts after //.
                        pubidx = 2

                        # Name starts after / which terminates publisher
                        nameidx += 1
                elif fmri.startswith("/"):
                        # Name starts after / which terminates scheme
                        nameidx = 1
                else:
                        nameidx = 0

                return (veridx, nameidx, pubidx)

        def get_publisher(self):
                """Return the name of the publisher that is contained
                within this FMRI.  This strips off extraneous data
                that may be attached to the publisher.  The output
                is suitable as a key into the publisher["prefix"] table."""

                # Strip off preferred publisher prefix, if it exists.
                if self.publisher and self.publisher.startswith(PREF_PUB_PFX):
                        r = self.publisher.rsplit('_', 1)
                        a = r[len(r) - 1]
                        return a

                # Otherwise just return the publisher
                return self.publisher

        def set_publisher(self, publisher, preferred = False):
                """Set the FMRI's publisher.  If this is a preferred
                publisher, set preferred to True."""

                if preferred and not publisher.startswith(PREF_PUB_PFX):
                        self.publisher = "{0}_{1}".format(PREF_PUB_PFX,
                            publisher)
                else:
                        self.publisher = publisher

        def remove_publisher(self):
                self.publisher = None
                return self

        def has_publisher(self):
                """Returns true if the FMRI has a publisher."""

                if self.publisher:
                        return True

                return False

        def has_version(self):
                """Returns True if the FMRI has a version"""
                if self.version:
                        return True
                return False

        def preferred_publisher(self):
                """Returns true if this FMRI's publisher is the preferred
                publisher."""

                if not self.publisher or \
                    self.publisher.startswith(PREF_PUB_PFX):
                        return True

                return False

        def get_publisher_str(self):
                """Return the bare string that specifies everything about
                the publisher.  This should only be used by code that
                must write out (or restore) the complete publisher
                information to disk."""

                return self.publisher

        def get_name(self):
                return self.pkg_name

        def set_name(self, name):
                self.pkg_name = name
                self._hash = None

        def set_timestamp(self, new_ts):
                self.version.set_timestamp(new_ts)
                self._hash = None

        def get_timestamp(self):
                return self.version.get_timestamp()

        def get_version(self):
                return self.version.get_short_version()

        def get_pkg_stem(self, anarchy=False, include_scheme=True):
                """Return a string representation of the FMRI without a specific
                version.  Anarchy returns a stem without any publisher."""
                pkg_str = ""
                if not self.publisher or \
                    self.publisher.startswith(PREF_PUB_PFX) or anarchy:
                        if include_scheme:
                                pkg_str = "pkg:/"
                        return "{0}{1}".format(pkg_str, self.pkg_name)
                if include_scheme:
                        pkg_str = "pkg://"
                return "{0}{1}/{2}".format(pkg_str, self.publisher,
                    self.pkg_name)

        def get_short_fmri(self, default_publisher=None, anarchy=False,
            include_scheme=True):
                """Return a string representation of the FMRI without a specific
                version."""
                pkg_str = ""
                publisher = self.publisher
                if not publisher:
                        publisher = default_publisher

                if self.version == None:
                        version = ""
                else:
                        version = "@" + self.version.get_short_version()

                if (not publisher or publisher.startswith(PREF_PUB_PFX) or
                    anarchy):
                        if include_scheme:
                                pkg_str = "pkg:/"
                        return "{0}{1}{2}".format(pkg_str, self.pkg_name,
                            version)

                if include_scheme:
                        pkg_str = "pkg://"
                return "{0}{1}/{2}{3}".format(pkg_str, publisher, self.pkg_name,
                    version)

        def get_fmri(self, default_publisher=None, anarchy=False,
            include_scheme=True, include_build=True):
                """Return a string representation of the FMRI.
                Anarchy returns a string without any publisher."""
                pkg_str = ""
                publisher = self.publisher
                if publisher == None:
                        publisher = default_publisher

                if not publisher or publisher.startswith(PREF_PUB_PFX) \
                    or anarchy:
                        if include_scheme:
                                pkg_str = "pkg:/"
                        if self.version == None:
                                return "{0}{1}".format(pkg_str, self.pkg_name)

                        return "{0}{1}@{2}".format(pkg_str, self.pkg_name,
                            self.version.get_version(
                                include_build=include_build))

                if include_scheme:
                        pkg_str = "pkg://"
                if self.version == None:
                        return "{0}{1}/{2}".format(pkg_str, publisher,
                            self.pkg_name)

                return "{0}{1}/{2}@{3}".format(pkg_str, publisher,
                    self.pkg_name,
                    self.version.get_version(include_build=include_build))

        def hierarchical_names(self):
                """Generate the different hierarchical names that could be used
                to reference this fmri."""

                names = self.pkg_name.split("/")
                res = names[-1:]
                for n in reversed(names[:-1]):
                        res.append("{0}/{1}".format(n, res[-1]))
                return res

        def __str__(self):
                """Return as specific an FMRI representation as possible."""
                return self.get_fmri()

        def __repr__(self):
                """Return as specific an FMRI representation as possible."""
                if not self.publisher:
                        if not self.version:
                                fmristr = "pkg:/{0}".format(self.pkg_name)
                        else:
                                fmristr = "pkg:/{0}@{1}".format(self.pkg_name,
                                    self.version)
                elif not self.version:
                        fmristr = "pkg://{0}/{1}".format(self.publisher,
                            self.pkg_name)
                else:
                        fmristr = "pkg://{0}/{1}@{2}".format(self.publisher,
                            self.pkg_name, self.version)

                return "<pkg.fmri.PkgFmri '{0}' at {1:#x}".format(fmristr,
                    id(self))

        def __hash__(self):
                #
                # __hash__ need not generate a unique hash value for all
                # possible objects-- it must simply guarantee that two
                # items which are equal (i.e. a = b) always hash to
                # the same value.
                #
                h = self._hash
                if h is None:
                        h = self._hash = hash(self.version) + hash(self.pkg_name)
                return h

        def __eq__(self, other):
                if not other:
                        return False

                if not isinstance(other, PkgFmri):
                        return False

                if self.publisher == other.publisher and \
                    self.pkg_name == other.pkg_name and \
                    self.version == other.version:
                        return True
                return False

        def __ne__(self, other):
                return not self == other

        def __lt__(self, other):
                if not other:
                        return False

                if not isinstance(other, PkgFmri):
                        return True

                if self.publisher != other.publisher:
                        if self.publisher is None and other.publisher:
                                return True
                        if self.publisher and other.publisher is None:
                                return False
                        if self.publisher < other.publisher:
                                return True
                        return False

                if self.pkg_name < other.pkg_name:
                        return True
                if self.pkg_name != other.pkg_name:
                        return False

                if self.version is None and other.version is None:
                        return False
                return self.version < other.version

        def __gt__(self, other):
                if not other:
                        return True

                if not isinstance(other, PkgFmri):
                        return False

                if self.publisher != other.publisher:
                        if self.publisher and other.publisher is None:
                                return True
                        if self.publisher is None and other.publisher:
                                return False
                        if self.publisher > other.publisher:
                                return True
                        return False

                if self.pkg_name > other.pkg_name:
                        return True
                if self.pkg_name != other.pkg_name:
                        return False

                if self.version is None and other.version is None:
                        return False
                return self.version > other.version

        def __ge__(self, other):
                return not self < other

        def __le__(self, other):
                return not self > other

        def get_link_path(self, stemonly = False):
                """Return the escaped link (or file) path fragment for this
                FMRI."""

                if stemonly:
                        return "{0}".format(quote(self.pkg_name, ""))

                if self.version is None:
                        raise MissingVersionError(self)

                return "{0}@{1}".format(quote(self.pkg_name, ""),
                    quote(str(self.version), ""))

        def get_dir_path(self, stemonly = False):
                """Return the escaped directory path fragment for this FMRI."""

                if stemonly:
                        return "{0}".format(quote(self.pkg_name, ""))

                if self.version is None:
                        raise MissingVersionError(self)

                return "{0}/{1}".format(quote(self.pkg_name, ""),
                    quote(self.version.__str__(), ""))

        def get_url_path(self):
                """Return the escaped URL path fragment for this FMRI.
                Requires a version to be defined."""

                if self.version is None:
                        raise MissingVersionError(self)

                return "{0}@{1}".format(quote(self.pkg_name, ""),
                    quote(self.version.__str__(), ""))

        def is_same_pkg(self, other):
                """Return true if these packages are the same (although
                potentially of different versions.)"""
                return self.pkg_name == other.pkg_name

        def tuple(self):
                return self.get_publisher_str(), self.pkg_name, self.version

        def is_name_match(self, fmristr):
                """True if the regular expression given in fmristr matches the
                stem of this pkg: FMRI."""
                m = re.match(fmristr, self.pkg_name)
                return m != None

        def is_similar(self, other):
                """True if package names match exactly.  Not a pattern-based
                query."""
                return self.pkg_name == other.pkg_name

        def is_successor(self, other):
                """ returns True if self >= other """

                # Fastest path for most common case.
                if self.pkg_name != other.pkg_name:
                        return False

                if self.version is None and other.version is None:
                        return True
                if self.version < other.version:
                        return False

                return True


class MatchingPkgFmri(PkgFmri):
        """ A subclass of PkgFmri with (much) weaker rules about package names.
        This is intended to accept user input with globbing characters. """
        valid_pkg_name = re.compile("^[A-Za-z0-9_/\-\.\+\*\?]*$")

        def __init__(self, *args, **kwargs):
                try:
                        PkgFmri.__init__(self, *args, **kwargs)
                except IllegalFmri as e:
                        raise IllegalMatchingFmri(e.fmri, e.reason,
                            detail=e.detail, nested_exc=e.nested_exc)


def fmri_match(pkg_name, pattern):
        """Returns true if 'pattern' is a proper subset of 'pkg_name'."""
        return ("/" + pkg_name).endswith("/" + pattern)

def glob_match(pkg_name, pattern):
        return fnmatch.fnmatchcase(pkg_name, pattern)

def regex_match(pkg_name, pattern):
        """Returns true if 'pattern' is a regular expression matching
        'pkg_name'."""
        return re.search(pattern, pkg_name)

def exact_name_match(pkg_name, pattern):
        """Returns true if 'pattern' matches 'pkg_name' exactly."""
        return pkg_name == pattern

def extract_pkg_name(fmri):
        """Given a string that can be converted to a FMRI.  Return the
        substring that is the FMRI's pkg_name."""
        fmri = fmri.rstrip()

        veridx, nameidx, pubidx = PkgFmri._gen_fmri_indexes(fmri)

        if veridx:
                pkg_name = fmri[nameidx:veridx]
        else:
                pkg_name = fmri[nameidx:]

        return pkg_name

def strip_pub_pfx(pub):
        """Strip the PREF_PUB_PFX off of a publisher."""
        if pub.startswith(PREF_PUB_PFX_):
                outstr = pub[len(PREF_PUB_PFX_):]
        else:
                outstr = pub

        return outstr


def is_same_publisher(pub1, pub2):
        """Compare two publishers.  Return true if they are the same, false
           otherwise. """
        #
        # This code is performance sensitive.  Ensure that you benchmark
        # changes to it.
        #

        # Fastest path for most common case.
        if pub1 == pub2:
                return True

        if pub1 == None:
                pub1 = ""
        if pub2 == None:
                pub2 = ""

        # String concatenation and string equality are both pretty fast.
        if ((PREF_PUB_PFX_ + pub1) == pub2) or \
            (pub1 == (PREF_PUB_PFX_ + pub2)):
                return True
        if pub1.startswith(PREF_PUB_PFX_) and \
            pub2.startswith(PREF_PUB_PFX_):
                return True
        return False


def is_valid_pkg_name(name):
        return g_valid_pkg_name.match(name)
