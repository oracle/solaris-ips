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
#

import re
import urllib

from version import Version

class PkgFmri(object):
        """The authority is the anchor of a package namespace.  Clients can
        choose to take packages from multiple authorities, and specify a default
        search path.  In general, package names may also be prefixed by a domain
        name, reverse domain name, or a stock symbol to avoid conflict.  The
        unprefixed namespace is expected to be managed by architectural review.

        The primary equivalence relationship assumes that packages of the same
        package name are forwards compatible across all versions of that
        package, and that higher build release versions are superior
        publications than lower build release versions."""

        def __init__(self, fmri, build_release = None, authority = None):
                """XXX pkg:/?pkg_name@version not presently supported."""
                fmri = fmri.rstrip()

                veridx, nameidx = PkgFmri.gen_fmri_indexes(fmri)

                if veridx:
                        self.version = Version(fmri[veridx + 1:], build_release)
                else:
                        self.version = veridx = None

                self.authority = authority
                if fmri.startswith("pkg://"):
                        self.authority = fmri[6:nameidx - 1]

                if veridx:
                        self.pkg_name = fmri[nameidx:veridx]
                else:
                        self.pkg_name = fmri[nameidx:]

        @staticmethod
        def gen_fmri_indexes(fmri):
                """Return a tuple of offsets, used to extract different
                components of the FMRI."""

                try:
                        veridx = fmri.rindex("@")
                except ValueError:
                        veridx = None

                if fmri.startswith("pkg://"):
                        nameidx = fmri.index("/", 6) + 1
                elif fmri.startswith("pkg:/"):
                        nameidx = 5
                else:
                        nameidx = 0

                return (veridx, nameidx)

        def get_authority(self):
                return self.authority

        def set_authority(self, authority):
                self.authority = authority

        def get_name(self):
                return self.pkg_name

        def set_name(self, name):
                self.pkg_name = name

        def set_timestamp(self, new_ts):
                self.version.set_timestamp(new_ts)

        def get_timestamp(self, new_ts):
                return self.version.get_timestamp()

        def get_pkg_stem(self, default_authority = None, anarchy = False):
                """Return a string representation of the FMRI without a specific
                version.  Anarchy returns a stem without any authority."""
                if not self.authority or anarchy:
                        return "pkg:/%s" % self.pkg_name

                return "pkg://%s/%s" % (self.authority, self.pkg_name)

        def get_short_fmri(self, default_authority = None):
                """Return a string representation of the FMRI without a specific
                version."""
                authority = self.authority
                if authority == None:
                        authority = default_authority

                if authority == None:
                        return "pkg:/%s@%s" % (self.pkg_name,
                            self.version.get_short_version())

                return "pkg://%s/%s@%s" % (authority, self.pkg_name,
                    self.version.get_short_version())

        def get_fmri(self, default_authority = None, anarchy = False):
                """Return a string representation of the FMRI.
                Anarchy returns a string without any authority."""
                authority = self.authority
                if authority == None:
                        authority = default_authority

                if not authority or anarchy:
                        if self.version == None:
                                return "pkg:/%s" % self.pkg_name

                        return "pkg:/%s@%s" % (self.pkg_name, self.version)

                if self.version == None:
                        return "pkg://%s/%s" % (authority, self.pkg_name)

                return "pkg://%s/%s@%s" % (authority, self.pkg_name,
                                self.version)

        def __str__(self):
                """Return as specific an FMRI representation as possible."""
                return self.get_fmri(None)

        def __cmp__(self, other):
                if not other:
                        return 1

                if self.authority and not other.authority:
                        return 1

                if not self.authority and other.authority:
                        return -1

                if self.authority and other.authority:
                        if self.authority != other.authority:
                                return cmp(self.authority, other.authority)

                if self.pkg_name == other.pkg_name:
                        if self.version and not other.version:
                                return 1

                        if other.version and not self.version:
                                return -1

                        if not self.version and not other.version:
                                return 0

                        return self.version.__cmp__(other.version)

                if self.pkg_name > other.pkg_name:
                        return 1

                return -1

        def get_dir_path(self, stemonly = False):
                """Return the escaped directory path fragment for this FMRI."""

                if stemonly:
                        return "%s" % (urllib.quote(self.pkg_name, ""))

                assert self.version != None

                return "%s/%s" % (urllib.quote(self.pkg_name, ""),
                    urllib.quote(self.version.__str__(), ""))

        def get_url_path(self):
                """Return the escaped URL path fragment for this FMRI.
                Requires a version to be defined."""
                assert self.version != None

                return "%s@%s" % (urllib.quote(self.pkg_name, ""),
                    urllib.quote(self.version.__str__(), ""))

        def is_same_pkg(self, other):
                """Return true if these packages are the same (although
                potentially of different versions.

                XXX Authority versus package name.
                """
                if self.authority != other.authority:
                        return False

                if self.pkg_name == other.pkg_name:
                        return True

                return False

        def tuple(self):
                return self.authority, self.pkg_name, self.version

        def is_name_match(self, fmristr):
                """True if the regular expression given in fmristr matches the
                stem of this pkg: FMRI."""
                m = re.match(fmristr, self.pkg_name)
                return m != None

        def is_similar(self, fmri):
                """True if package names match exactly.  Not a pattern-based
                query."""
                return self.pkg_name == fmri.pkg_name

        def is_successor(self, fmri):
                if not self.pkg_name == fmri.pkg_name:
                        return False

                if self.authority != fmri.authority:
                        return False

                if fmri.version == None:
                        return False

                if self.version == None:
                        return True

                if self.version < fmri.version:
                        return False

                return True

def fmri_match(pkg_name, pattern):
        """Returns true if 'pattern' is a proper subset of 'pkg_name'."""
        return ("/" + pkg_name).endswith("/" + pattern)

def regex_match(pkg_name, pattern):
        """Returns true if 'pattern' is a regular expression matching 'pkg_name'."""
        return re.search(pattern, pkg_name)

def exact_name_match(pkg_name, pattern):
        """Returns true if 'pattern' matches 'pkg_name' exactly."""
        return pkg_name == pattern

def extract_pkg_name(fmri):
        """Given a string that can be converted to a FMRI.  Return the
        substring that is the FMRI's pkg_name."""
        fmri = fmri.rstrip()

        veridx, nameidx = PkgFmri.gen_fmri_indexes(fmri)

        if veridx:
                pkg_name = fmri[nameidx:veridx]
        else:
                pkg_name = fmri[nameidx:]

        return pkg_name
