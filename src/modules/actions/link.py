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

"""module describing a (symbolic) link packaging object

This module contains the LinkAction class, which represents a link-type
packaging object."""

import errno
import os
import six
import stat

from . import generic
import pkg.actions
import pkg.mediator as med

from pkg import misc
from pkg.client.api_errors import ActionExecutionError

class LinkAction(generic.Action):
        """Class representing a link-type packaging object."""

        __slots__ = []

        name = "link"
        key_attr = "path"
        unique_attrs = "path", "target"
        globally_identical = True
        refcountable = True
        namespace_group = "path"
        ordinality = generic._orderdict[name]

        def install(self, pkgplan, orig):
                """Client-side method that installs a link."""

                target = self.attrs["target"]
                path = self.get_installed_path(pkgplan.image.get_root())

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

                target = self.attrs["target"]
                path = self.get_installed_path(img.get_root())

                lstat, errors, warnings, info, abort = \
                    self.verify_fsobj_common(img, stat.S_IFLNK)

                if abort:
                        assert errors
                        return errors, warnings, info

                atarget = os.readlink(path)

                if target != atarget:
                        errors.append(_("Target: '{found}' should be "
                            "'{expected}'").format(found=atarget,
                            expected=target))
                return errors, warnings, info

        def remove(self, pkgplan):
                """Removes the installed link from the system.  If something
                other than a link is found at the destination location, it
                will be removed or salvaged."""

                path = self.get_installed_path(pkgplan.image.get_root())
                return self.remove_fsobj(pkgplan, path)

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                rval = [
                    (self.name, "basename", os.path.basename(self.attrs["path"]),
                    None),
                    (self.name, "path", os.path.sep + self.attrs["path"], None),
                ]
                if "mediator" in self.attrs:
                        rval.extend(
                            (self.name, k, v, None)
                            for k, v in six.iteritems(self.attrs)
                            if k.startswith("mediator")
                        )
                return rval

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action."""

                errors = generic.Action._validate(self, fmri=fmri,
                    raise_errors=False, required_attrs=("target",),
                    single_attrs=("target", "mediator", "mediator-version",
                    "mediator-implementation", "mediator-priority"))

                if "mediator" not in self.attrs and \
                    "mediator-version" not in self.attrs and \
                    "mediator-implementation" not in self.attrs and \
                    "mediator-priority" not in self.attrs:
                        if errors:
                                raise pkg.actions.InvalidActionAttributesError(
                                    self, errors, fmri=fmri)
                        return

                mediator = self.attrs.get("mediator")
                med_version = self.attrs.get("mediator-version")
                med_implementation = self.attrs.get("mediator-implementation")
                med_priority = self.attrs.get("mediator-priority")

                if not mediator and (med_version or med_implementation or
                    med_priority):
                        errors.append(("mediator", _("a mediator must be "
                            "provided when mediator-version, "
                            "mediator-implementation, or mediator-priority "
                            "is specified")))
                elif mediator is not None and \
                    not isinstance(mediator, list):
                        valid, error = med.valid_mediator(mediator)
                        if not valid:
                                errors.append(("mediator", error))

                if not (med_version or med_implementation):
                        errors.append(("mediator", _("a mediator-version or "
                            "mediator-implementation must be provided if a "
                            "mediator is specified")))

                if med_version is not None and \
                    not isinstance(med_version, list):
                        valid, error = med.valid_mediator_version(med_version)
                        if not valid:
                                errors.append(("mediator-version", error))

                if med_implementation is not None and \
                    not isinstance(med_implementation, list):
                        valid, error = med.valid_mediator_implementation(
                            med_implementation)
                        if not valid:
                                errors.append(("mediator-implementation",
                                    error))

                if med_priority is not None and \
                    not isinstance(med_priority, list):
                        valid, error = med.valid_mediator_priority(med_priority)
                        if not valid:
                                errors.append(("mediator-priority", error))

                if errors:
                        raise pkg.actions.InvalidActionAttributesError(self,
                            errors, fmri=fmri)
