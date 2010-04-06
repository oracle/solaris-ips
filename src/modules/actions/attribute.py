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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a package attribute

This module contains the AttributeAction class, which represents a single
attribute of a package (package metadata).  Attributes are typed, and the
possible types are: XXX."""

import generic
import pkg.fmri as fmri
import pkg.actions

class AttributeAction(generic.Action):
        """Class representing a package attribute."""

        __slots__ = ["value"]

        name = "set"
        key_attr = "name"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

                # For convenience, we allow people to express attributes as
                # "<name>=<value>", rather than "name=<name> value=<value>", but
                # we always convert to the latter.
                if len(attrs) == 1:
                        self.attrs["name"], self.attrs["value"] = \
                            self.attrs.popitem()

                if "name" not in self.attrs or "value" not in self.attrs:
                        raise pkg.actions.InvalidActionError(str(self),
                            'Missing "name" or "value" attribute')

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                if self.has_category_info():
                        try:

                                return [
                                    (self.name, self.attrs["name"],
                                    [all_levels] +
                                    [t.split() for t in all_levels.split("/")],
                                    all_levels)
                                    for scheme, all_levels
                                    in self.parse_category_info()
                                ]
                        except ValueError:
                                pass

                if isinstance(self.attrs["value"], list):
                        tmp = []
                        for v in self.attrs["value"]:
                                assert isinstance(v, basestring)
                                if " " in v:
                                        words = v.split()
                                        for w in words:
                                                tmp.append((self.name,
                                                    self.attrs["name"], w,
                                                    v))
                                else:
                                        tmp.append((self.name,
                                            self.attrs["name"], v, None))
                        return  tmp
                elif self.attrs["name"] in ("fmri", "pkg.fmri"):
                        fmri_obj = fmri.PkgFmri(self.attrs["value"])

                        lst = [
                            fmri_obj.get_pkg_stem(include_scheme=False),
                            str(fmri_obj.version.build_release),
                            str(fmri_obj.version.release),
                            str(fmri_obj.version.timestr)
                        ]
                        lst.extend(fmri_obj.hierarchical_names())
                        return [
                            (self.name, self.attrs["name"], w,
                            fmri_obj.get_pkg_stem(include_scheme=False))
                            for w in lst
                        ]

                elif " " in self.attrs["value"]:
                        v = self.attrs["value"]
                        return [
                            (self.name, self.attrs["name"], w, v)
                            for w in v.split()
                        ]
                else:
                        return [
                            (self.name, self.attrs["name"],
                            self.attrs["value"], None)
                        ]

        def has_category_info(self):
                return self.attrs["name"] == "info.classification"
        
        def parse_category_info(self):
                rval = []
                # Some logic is inlined here for performance reasons.
                if self.attrs["name"] != "info.classification":
                        return rval

                for val in self.attrlist("value"):
                        if ":" in val:
                                scheme, cats = val.split(":", 1)
                        else:
                                scheme = ""
                                cats = val
                        rval.append((scheme, cats))
                return rval
