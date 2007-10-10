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

"""module describing a (symbolic) link packaging object

This module contains the LinkAction class, which represents a link-type
packaging object."""

import os
import sha

import generic

class LinkAction(generic.Action):
        """Class representing a link-type packaging object."""

        name = "link"
        attributes = ("path", "target")
        key_attr = "path"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def install(self, pkgplan, orig):
                """Client-side method that installs a link."""
                # XXX The exists-unlink-symlink path appears to be as safe as it
                # gets with the current symlink(2) interface.

                path = self.attrs["path"]
                target = self.attrs["target"]

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                if os.path.lexists(path):
                        os.unlink(path)

                os.symlink(target, path)

        def remove(self, pkgplan):
                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))

                os.unlink(path)

        def generate_indices(self):
                return {
                    "basename": os.path.basename(self.attrs["path"]),
                    "path": os.path.sep + self.attrs["path"]
                }
