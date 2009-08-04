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

"""module describing a (hard) link packaging object

This module contains the HardLinkAction class, which represents a hardlink-type
packaging object."""

import errno
import os
import stat

from pkg.client.api_errors import ActionExecutionError
import link

class HardLinkAction(link.LinkAction):
        """Class representing a hardlink-type packaging object."""

        name = "hardlink"

        def __init__(self, data=None, **attrs):
                link.LinkAction.__init__(self, data, **attrs)

        def get_target_path(self):
                """ return a path for target that is relative to image"""
                
                target = self.attrs["target"]

                # paths are either relative to path or absolute;
                # both need to be passed through os.path.normpath to ensure
                # that all ".." are removed to constrain target to image

                if target[0] != "/":
                        path = self.attrs["path"]
                        target = os.path.normpath(
                            os.path.join(os.path.split(path)[0], target))
                else:
                        target = os.path.normpath(target)[1:]

                return target

        def install(self, pkgplan, orig):
                """Client-side method that installs a hard link."""

                path = self.attrs["path"]
                target = self.get_target_path()

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path), mode=0755)
                elif os.path.exists(path):
                        os.unlink(path)

                fulltarget = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), target)))

                try:
                        os.link(fulltarget, path)
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                raise ActionExecutionError(self, e,
                                    "missing hard link target '%s'" % target)
                        else:
                                raise ActionExecutionError(self, e)

        def verify(self, img, **args):

                #
                # We only allow hard links to regular files, so the hard
                # link should lstat() as a regular file.
                #
                lstat, errors, abort = \
                    self.verify_fsobj_common(img, stat.S_IFREG)
                if abort:
                        assert errors
                        return errors

                target = self.get_target_path()
                path = os.path.normpath(os.path.sep.join(
                    (img.get_root(), self.attrs["path"])))
                target = os.path.normpath(os.path.sep.join(
                    (img.get_root(), target)))

                if not os.path.exists(target):
                        errors.append("Target '%s' does not exist" %
                            self.attrs["target"])

                # No point in continuing if no target
                if errors:
                        return errors

                try:
                        if os.stat(path).st_ino != os.stat(target).st_ino:
                                errors.append("Broken: Path and Target (%s) "
                                    "inodes not the same" %
                                    self.get_target_path())

                except OSError, e:
                        errors.append("Unexpected OSError: %s" % e)

                return errors
