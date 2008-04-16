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
#

import re
import urllib

from version import Version

# In order to keep track of what authority is presently the preferred authority,
# a prefix is included ahead of the name of the authority.  If this prefix is
# present, the authority is considered to be the current preferred authority for
# the image.  This is where we define the prefix, since it's used primarily in
# the FMRI.  PREF_AUTH_PFX => preferred authority prefix.
PREF_AUTH_PFX = "_PRE"

#
# For is_same_authority(), we need a version of this constant with the
# trailing _ attached.
#
PREF_AUTH_PFX_ = PREF_AUTH_PFX + "_"


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
                """Return the name of the authority that is contained
                within this FMRI.  This strips off extraneous data
                that may be attached to the authority.  The output
                is suitable as a key into the authority["prefix"] table."""

                # Strip off preferred authority prefix, if it exists.
                if self.authority and self.authority.startswith(PREF_AUTH_PFX):
                        r = self.authority.rsplit('_', 1)
                        a = r[len(r) - 1]
                        return a

                # Otherwise just return the authority
                return self.authority

        def set_authority(self, authority, preferred = False):
                """Set the FMRI's authority.  If this is a preferred
                authority, set preferred to True."""

                if preferred and not authority.startswith(PREF_AUTH_PFX):
                        self.authority = "%s_%s" % (PREF_AUTH_PFX, authority)
                else:
                        self.authority = authority

        def has_authority(self):
                """Returns true if the FMRI has an authority."""

                if self.authority:
                        return True

                return False

        def has_version(self):
                """Returns True if the FMRI has a version"""
                if self.version:
                        return True
                return False

        def preferred_authority(self):
                """Returns true if this FMRI's authority is the preferred
                authority."""

                if not self.authority or \
                    self.authority.startswith(PREF_AUTH_PFX):
                        return True

                return False

        def get_authority_str(self):
                """Return the bare string that specifies everything about
                the authority.  This should only be used by code that
                must write out (or restore) the complete authority
                information to disk."""

                return self.authority

        def get_name(self):
                return self.pkg_name

        def set_name(self, name):
                self.pkg_name = name

        def set_timestamp(self, new_ts):
                self.version.set_timestamp(new_ts)

        def get_timestamp(self):
                return self.version.get_timestamp()

        def get_version(self):
                return self.version.get_short_version()

        def get_pkg_stem(self, default_authority = None, anarchy = False):
                """Return a string representation of the FMRI without a specific
                version.  Anarchy returns a stem without any authority."""
                if not self.authority or \
                    self.authority.startswith(PREF_AUTH_PFX) or anarchy:
                        return "pkg:/%s" % self.pkg_name

                return "pkg://%s/%s" % (self.authority, self.pkg_name)

        def get_short_fmri(self, default_authority = None):
                """Return a string representation of the FMRI without a specific
                version."""
                authority = self.authority
                if not authority:
                        authority = default_authority

                if not authority or authority.startswith(PREF_AUTH_PFX):
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

                if not authority or authority.startswith(PREF_AUTH_PFX) \
                    or anarchy:
                        if self.version == None:
                                return "pkg:/%s" % self.pkg_name

                        return "pkg:/%s@%s" % (self.pkg_name, self.version)

                if self.version == None:
                        return "pkg://%s/%s" % (authority, self.pkg_name)

                return "pkg://%s/%s@%s" % (authority, self.pkg_name,
                                self.version)

        def __str__(self):
                """Return as specific an FMRI representation as possible."""
                return self.get_fmri()

        def __hash__(self):
                return hash(str(self))

        def __cmp__(self, other):
                if not other:
                        return 1

                if self.authority and not other.authority:
                        return 1

                if not self.authority and other.authority:
                        return -1

                if self.authority and other.authority:
                        if not is_same_authority(self.authority,
                             other.authority):
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
                if not is_same_authority(self.authority, other.authority):
                        return False

                if self.pkg_name == other.pkg_name:
                        return True

                return False

        def tuple(self):
                return self.get_authority_str(), self.pkg_name, self.version

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
                """ returns True if self > fmri """

                if not self.pkg_name == fmri.pkg_name:
                        return False

                if not is_same_authority(self.authority, fmri.authority):
                        return False

                if fmri.version == None:
                        return True

                if self.version == None:
                        return False

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

def strip_auth_pfx(auth):
        """Strip the PREF_AUTH_PFX off of an authority."""
        if auth.startswith(PREF_AUTH_PFX_):
                str = auth[len(PREF_AUTH_PFX_):]
        else:
                str = auth

        return str
        

def is_same_authority(auth1, auth2):
        """Compare two authorities.  Return true if they are the same, false
           otherwise. """
	#
	# This code is performance sensitive.  Ensure that you benchmark
	# changes to it.
	#

	# Fastest path for most common case.
	if auth1 == auth2:
		return True

	if auth1 == None:
		auth1 = ""
	if auth2 == None:
		auth2 = ""

	# String concatenation and string equality are both pretty fast.
	if ((PREF_AUTH_PFX_ + auth1) == auth2) or \
	    (auth1 == (PREF_AUTH_PFX_ + auth2)):
		return True
        if auth1.startswith(PREF_AUTH_PFX_) and auth2.startswith(PREF_AUTH_PFX_):
                return True
	return False

