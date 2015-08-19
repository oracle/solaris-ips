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

# Copyright (c) 2011, 2015, Oracle and/or its affiliates. All rights reserved.

import re
import six

import pkg.misc as misc
import pkg.version as version

def valid_mediator(value):
        """Returns a tuple of (valid, error) indicating whether the provided
        string is a valid name for a link mediation.  'valid' is a boolean
        and 'error' is None or a string containing the error."""

        if isinstance(value, six.string_types):
                if re.match("^[a-zA-Z0-9\-]+$", value):
                        return True, None
        return False, _("'{0}' is not a valid mediator; only alphanumeric "
            "characters are allowed").format(value)

def valid_mediator_version(value):
        """Returns a tuple of (valid, error) indicating whether the provided
        string is a valid mediator version for a link mediation.  'valid' is
        a boolean and 'error' is None or a string containing the error."""

        error = ""
        if isinstance(value, six.string_types):
                try:
                        version.Version(value)
                        return True, None
                except version.VersionError as e:
                        error = str(e)

        if error:
                return False, _("'{value}' is not a valid mediator-version: "
                    "{error}").format(**locals())
        return False, _("'{0}' is not a valid mediator-version").format(value)

def parse_mediator_implementation(value):
        """Parses the provided mediator implementation string for a link and
        returns a tuple of (name, version) where 'name' is a string containing
        the name of the implementation and 'version' is None or a pkg.version
        object representing the version.  If the implementation is not valid
        a tuple of (None, None) will be returned."""

        if not isinstance(value, six.string_types):
                return None, None

        if "@" in value:
                try:
                        impl_name, impl_ver = value.rsplit("@", 1)
                except (ValueError, AttributeError):
                        # Can't parse implementation correctly, so
                        # return a tuple of None.
                        return None, None
        else:
                impl_name = value
                impl_ver = None

        if impl_ver:
                try:
                        impl_ver = version.Version(impl_ver)
                except version.VersionError:
                        # If part of implementation can't be parsed, then
                        # return nothing at all.
                        return None, None

        return impl_name, impl_ver

def valid_mediator_implementation(value, allow_empty_version=False):
        """Returns a tuple of (valid, error) indicating whether the provided
        string is a valid mediator implementation for mediated links.  'valid' is
        a boolean and 'error' is None or a string containing the error."""

        error = ""
        iname = iver = None
        if isinstance(value, six.string_types):
                if "@" in value:
                        iname, iver = value.rsplit("@", 1)
                else:
                        iname = value

                if iver or (iver == "" and not allow_empty_version):
                        try:
                                version.Version(iver)
                        except version.VersionError as e:
                                error = str(e)

                if not error and iname and re.match("^[a-zA-Z0-9\-]+$", iname):
                        return True, None

        if error:
                return False, _("'{value}' is not a valid "
                    "mediator-implementation; only alphanumeric characters and "
                    "a version dot-sequence following a single '@' are allowed: "
                    "{error}").format(**locals())
        return False, _("'{0}' is not a valid mediator-implementation; only "
            "alphanumeric characters and a version dot-sequence following a "
            "single '@' are allowed").format(value)

def valid_mediator_priority(value):
        """Returns a tuple of (valid, error) indicating whether the provided
        string is a valid mediator priority for mediated links.  'valid' is
        a boolean and 'error' is None or a string containing the error."""

        if value in ("site", "vendor"):
                return True, None
        return False, _("'{0}' is not a valid mediator-priority; valid values "
            "are 'site' or 'vendor'").format(value)

# A ranking dictionary used by cmp_mediations for sorting mediatoins based on
# mediator priority for mediated links.
_MED_PRIORITIES = {
    "site": 1,
    "vendor": 2
}

def cmp_mediations(a, b):
        """Custom mediation sorting routine.  Sort is done by
        priority, version, implementation name, implementation
        version.
        """

        aprio = _MED_PRIORITIES.get(a[0], 3)
        bprio = _MED_PRIORITIES.get(b[0], 3)
        res = misc.cmp(aprio, bprio)
        if res != 0:
                return res

        aver = a[1]
        bver = b[1]
        res = misc.cmp(aver, bver)
        if res != 0:
                # Invert version sort so greatest is first.
                return res * -1

        aimpl, aver = parse_mediator_implementation(a[2])
        bimpl, bver = parse_mediator_implementation(b[2])
        res = misc.cmp(aimpl, bimpl)
        if res != 0:
                return res

        res = misc.cmp(aver, bver)
        if res != 0:
                # Invert version sort so greatest is first.
                return res * -1
        return 0

def mediator_impl_matches(a, b):
        """Returns a boolean indicating whether two given mediator implementation
        strings match.  This is needed because an unversioned implementation is
        matches both versioned and unversioned implementations.  This function
        assumes that the values being compared are valid.
        """

        if a == b:
                return True

        aimpl, aver = parse_mediator_implementation(a)
        bimpl, bver = parse_mediator_implementation(b)
        if aimpl != bimpl or not (aimpl and bimpl):
                return False

        # If version component of either a or b is None, that
        # means the implementation was specified as 'impl'
        # which allows any version to match.  Otherwise,
        # version components must match exactly.
        return aver == None or bver == None or aver == bver
