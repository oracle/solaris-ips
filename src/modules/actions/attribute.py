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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a package attribute

This module contains the AttributeAction class, which represents a single
attribute of a package (package metadata).  Attributes are typed, and the
possible types are: XXX."""

from . import generic
import pkg.fmri
import pkg.actions
import six

class AttributeAction(generic.Action):
        """Class representing a package attribute."""

        __slots__ = ["value"]

        name = "set"
        key_attr = "name"
        ordinality = generic._orderdict[name]

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

                try:
                        self.attrs["name"]
                        self.attrs["value"]
                except KeyError:
                        # For convenience, we allow people to express attributes as
                        # "<name>=<value>", rather than "name=<name> value=<value>", but
                        # we always convert to the latter.
                        try:
                                if len(attrs) == 1:
                                        self.attrs["name"], self.attrs["value"] = \
                                            self.attrs.popitem()
                                        return
                        except KeyError:
                                pass
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
                                assert isinstance(v, six.string_types)
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
                        fmri_obj = pkg.fmri.PkgFmri(self.attrs["value"])

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

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action.
                """

                name = self.attrs["name"]
                if name in ("pkg.summary", "pkg.obsolete", "pkg.renamed",
                    "pkg.description", "pkg.depend.explicit-install"):
                        # If set action is for any of the above, only a single
                        # value is permitted.
                        generic.Action._validate(self, fmri=fmri,
                            single_attrs=("value",))
                elif name.startswith("pkg.additional-"):
                        # For pkg actuators, just test that the values are valid
                        # FMRIs. We want to prevent the system from failing when
                        # newer, currently unknown actuators are encountered.
                        errors = []
                        fmris = self.attrlist("value")
                        for f in fmris:
                                try:
                                        pkg.fmri.PkgFmri(f)
                                except pkg.fmri.IllegalFmri as e:
                                        errors.append((name, str(e)))
                        if errors:
                                raise pkg.actions.InvalidActionAttributesError(
                                    self, errors, fmri=fmri)

                        generic.Action._validate(self, fmri=fmri)
                else:
                        # In all other cases, multiple values are assumed to be
                        # permissible.
                        generic.Action._validate(self, fmri=fmri)
