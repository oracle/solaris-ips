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

"""module describing a (symbolic) link packaging object

This module contains the LinkAction class, which represents a link-type
packaging object."""

import errno
import os
import stat

import generic
import pkg.actions
from pkg import misc

class LinkAction(generic.Action):
        """Class representing a link-type packaging object."""

        __slots__ = []

        name = "link"
        key_attr = "path"
        globally_unique = True

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                if "path" in self.attrs:
                        self.attrs["path"] = self.attrs["path"].lstrip(
                            os.path.sep)
                        if not self.attrs["path"]:
                                raise pkg.actions.InvalidActionError(
                                    str(self), _("Empty path attribute"))

        def install(self, pkgplan, orig):
                """Client-side method that installs a link."""

                path = self.attrs["path"]
                target = self.attrs["target"]

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                # Don't allow installation through symlinks.
                self.fsobj_checkpath(pkgplan, path)

                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path),
                            mode=misc.PKG_DIR_MODE,
                            fmri=pkgplan.destination_fmri)

                # XXX The exists-unlink-symlink path appears to be as safe as it
                # gets to modify a link with the current symlink(2) interface.
                if os.path.lexists(path):
                        self.remove(pkgplan)
                os.symlink(target, path)

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                path = self.attrs["path"]
                target = self.attrs["target"]

                path = os.path.normpath(os.path.sep.join(
                    (img.get_root(), path)))

                lstat, errors, warnings, info, abort = \
                    self.verify_fsobj_common(img, stat.S_IFLNK)

                if abort:
                        assert errors
                        return errors, warnings, info

                atarget = os.readlink(path)

                if target != atarget:
                        errors.append(_("Target: '%(found)s' should be "
                            "'%(expected)s'") % { "found": atarget,
                            "expected": target })
                return errors, warnings, info

        def remove(self, pkgplan):
                """Removes the installed link from the system.  If something
                other than a link is found at the destination location, it
                will be removed or salvaged."""

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))
                return self.remove_fsobj(pkgplan, path)

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [
                    (self.name, "basename", os.path.basename(self.attrs["path"]),
                    None),
                    (self.name, "path", os.path.sep + self.attrs["path"], None)
                ]
