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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
#

"""module describing a (hard) link packaging object

This module contains the HardLinkAction class, which represents a hardlink-type
packaging object."""

import errno
from . import generic, link
import os
import stat

from pkg import misc
from pkg.client.api_errors import ActionExecutionError

class HardLinkAction(link.LinkAction):
        """Class representing a hardlink-type packaging object."""

        __slots__ = []

        name = "hardlink"
        ordinality = generic._orderdict[name]

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

                target = self.get_target_path()
                path = self.get_installed_path(pkgplan.image.get_root())

                # Don't allow installation through symlinks.
                self.fsobj_checkpath(pkgplan, path)

                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path),
                            mode=misc.PKG_DIR_MODE,
                            fmri=pkgplan.destination_fmri)
                elif os.path.exists(path):
                        self.remove(pkgplan)

                fulltarget = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), target)))

                try:
                        os.link(fulltarget, path)
                except EnvironmentError as e:
                        if e.errno != errno.ENOENT:
                                raise ActionExecutionError(self, error=e)

                        # User or another process has removed target for
                        # hardlink, a package hasn't declared correct
                        # dependencies, or the target hasn't been installed
                        # yet.
                        err_txt = _("Unable to create hard link {path}; "
                            "target {target} is missing.").format(
                            path=path, target=fulltarget)
                        raise ActionExecutionError(self, details=err_txt,
                            error=e, fmri=pkgplan.destination_fmri)

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                #
                # We only allow hard links to regular files, so the hard
                # link should lstat() as a regular file.
                #
                lstat, errors, warnings, info, abort = \
                    self.verify_fsobj_common(img, stat.S_IFREG)
                if abort:
                        assert errors
                        return errors, warnings, info

                target = self.get_target_path()
                path = self.get_installed_path(img.get_root())
                target = os.path.normpath(os.path.sep.join(
                    (img.get_root(), target)))

                if not os.path.exists(target):
                        errors.append(_("Target '{0}' does not exist").format(
                            self.attrs["target"]))

                # No point in continuing if no target
                if errors:
                        return errors, warnings, info

                try:
                        if os.stat(path).st_ino != os.stat(target).st_ino:
                                errors.append(_("Broken: Path and Target ({0}) "
                                    "inodes not the same").format(
                                    self.get_target_path()))
                except OSError as e:
                        errors.append(_("Unexpected Error: {0}").format(e))

                return errors, warnings, info
