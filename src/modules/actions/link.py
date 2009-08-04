#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a (symbolic) link packaging object

This module contains the LinkAction class, which represents a link-type
packaging object."""

import os
import errno

import generic
import pkg.actions
from pkg.client.api_errors import ActionExecutionError
import stat

class LinkAction(generic.Action):
        """Class representing a link-type packaging object."""

        name = "link"
        attributes = ("path", "target")
        key_attr = "path"

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

                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path), mode=0755)

                # XXX The exists-unlink-symlink path appears to be as safe as it
                # gets to modify a link with the current symlink(2) interface.
                if os.path.lexists(path):
                        try:
                                os.unlink(path)
                        except EnvironmentError, e:
                                if e.errno == errno.EPERM:
                                        # Unlinking a directory gives EPERM,
                                        # which is confusing, so ignore errno
                                        # and give a good message.
                                        path = self.attrs["path"]
                                        raise ActionExecutionError(self, e,
                                            "attempted to remove link '%s' but "
                                            "found a directory" % path,
                                            ignoreerrno=True)
                                else:
                                        raise ActionExecutionError(self, e)

                os.symlink(target, path)

        def verify(self, img, **args):
                """client-side method to verify install of self"""
                path = self.attrs["path"]
                target = self.attrs["target"]

                path = os.path.normpath(os.path.sep.join(
                    (img.get_root(), path)))

                lstat, errors, abort = \
                    self.verify_fsobj_common(img, stat.S_IFLNK)

                if abort:
                        assert errors
                        return errors

                atarget = os.readlink(path)

                if target != atarget:
                        errors.append("Target: '%s' should be '%s'" %
                            (atarget, target))

                return errors

        def remove(self, pkgplan):
                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), self.attrs["path"])))
                try:
                        os.unlink(path)
                except OSError,e:
                        if e.errno != errno.ENOENT:
                                raise

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [
                    (self.name, "basename", os.path.basename(self.attrs["path"]),
                    None),
                    (self.name, "path", os.path.sep + self.attrs["path"], None)
                ]
