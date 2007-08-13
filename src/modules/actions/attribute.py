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

"""module describing a package attribute

This module contains the AttributeAction class, which represents a single
attribute of a package (package metadata).  Attributes are typed, and the
possible types are: XXX."""

import generic

class AttributeAction(generic.Action):
        """Class representing a package attribute."""

        name = "set"
        attributes = ("type",)

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

                # XXX This is pretty hokey.  Is this okay, do we get rid of it
                # in favor of just doing name/value attributes to start with, or
                # do we find a better solution for upgrade?
                if len(attrs) == 1:
                        self.key_attr = "name"
                        self.attrs["name"] = attrs.keys()[0]
