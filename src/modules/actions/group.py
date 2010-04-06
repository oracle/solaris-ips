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

"""module describing a user packaging object

This module contains the UserAction class, which represents a user
packaging object.  This contains the attributes necessary to create
a new user."""

import generic
try:
        from pkg.cfgfiles import *
        have_cfgfiles = True
except ImportError:
        have_cfgfiles = False

class GroupAction(generic.Action):
        """Class representing a group packaging object.
        note that grouplist members are selected via the user action,
        although they are stored in the /etc/group file.  Use of
        group passwds is not supported."""

        __slots__ = []

        name = "group"
        key_attr = "groupname"
        globally_unique = True

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def extract(self, attrlist):
                """ return a dictionary containing attrs in attr list
                from self.attrs; omit if no such attrs in self.attrs"""
                return dict((a, self.attrs[a])
                             for a in self.attrs
                             if a in attrlist)

        def install(self, pkgplan, orig):
                """client-side method that adds the group
                   use gid from disk if different"""
                if not have_cfgfiles:
                        # the group action is ignored if cfgfiles is not available
                        return

                template = self.extract(["groupname", "gid"])

                gr = GroupFile(pkgplan.image.get_root())

                cur_attrs = gr.getvalue(template)

                # XXX needs modification if more attrs are used
                if not cur_attrs:
                        gr.setvalue(template)
                        gr.writefile()

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []
                if not have_cfgfiles:
                        # The user action is ignored if cfgfiles is not
                        # available.
                        return errors, warnings, info

                gr = GroupFile(img.get_root())

                cur_attrs = gr.getvalue(self.attrs)

                # Get the default values if they're non-empty
                grdefval = dict((
                    (k, v)
                    for k, v in gr.getdefaultvalues().iteritems()
                    if v != ""
                ))

                # If "gid" is set dynamically, ignore what's on disk.
                if "gid" not in self.attrs:
                        cur_attrs["gid"] = ""

                should_be = grdefval.copy()
                should_be.update(self.attrs)
                # Note where attributes are missing
                for k in should_be:
                        cur_attrs.setdefault(k, "<missing>")
                # Note where attributes should be empty
                for k in cur_attrs:
                        if cur_attrs[k]:
                                should_be.setdefault(k, "<empty>")
                # Ignore "user-list", as it is only modified by user actions
                should_be.pop("user-list", None)

                errors = [
                    _("%(entry)s: '%(found)s' should be '%(expected)s'") % {
                        "entry": a, "found": cur_attrs[a],
                        "expected": should_be[a] }
                    for a in should_be
                    if cur_attrs[a] != should_be[a]
                ]
                return errors, warnings, info

        def remove(self, pkgplan):
                """client-side method that removes this group"""
                if not have_cfgfiles:
                        # The user action is ignored if cfgfiles is not
                        # available.
                        return
                gr = GroupFile(pkgplan.image.get_root())
                cur_attrs = gr.getvalue(self.attrs)
                # groups need to be first added, last removed
                if not cur_attrs["user-list"]:
                        gr.removevalue(self.attrs)
                        gr.writefile()

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [("group", "name", self.attrs["groupname"], None)]

