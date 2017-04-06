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

"""module describing a legacy packaging object

This module contains the LegacyAction class, which represents a legacy SVr4
package.  On installation, this action will lay down file with sufficient data
to fool the SVr4 packaging tools into thinking that package is installed, albeit
empty."""

import os
import errno
import itertools
import time

from . import generic
from pkg import misc

class LegacyAction(generic.Action):
        """Class representing a legacy SVr4 packaging object."""

        __slots__ = []

        name = "legacy"
        key_attr = "pkg"
        unique_attrs = ("category", "desc", "hotline", "name", "pkg", "vendor",
            "version", "basedir", "pkginst", "pstamp", "sunw_prodvers")
        refcountable = True
        globally_identical = True
        ordinality = generic._orderdict[name]

        def directory_references(self):
                return [os.path.normpath(os.path.join("var/sadm/pkg",
                    self.attrs["pkg"]))]

        def install(self, pkgplan, orig):
                """Client-side method that installs the dummy package files.
                Use per-pkg hardlinks to create reference count for pkginfo
                file"""

                pkgdir = os.path.join(pkgplan.image.get_root(), "var/sadm/pkg",
                    self.attrs["pkg"])

                if not os.path.isdir(pkgdir):
                        os.makedirs(pkgdir, misc.PKG_DIR_MODE)

                pkginfo = os.path.join(pkgdir, "pkginfo")

                self.__old_refcount_cleanup(pkginfo, pkgdir)

                pkg_summary = pkgplan.pkg_summary
                if len(pkg_summary) > 256:
                        # The len check is done to avoid slice creation.
                        pkg_summary = pkg_summary[:256]

                svr4attrs = {
                    "arch": pkgplan.image.get_arch(),
                    "basedir": "/",
                    "category": "system",
                    "desc": None,
                    "hotline": None,
                    "name": pkg_summary,
                    "pkg": self.attrs["pkg"],
                    "pkginst": self.attrs["pkg"],
                    "pstamp": None,
                    "sunw_prodvers": None,
                    "vendor": None,
                    "version": str(pkgplan.destination_fmri.version),
                }

                attrs = [
                    (a.upper(), b)
                    for a in svr4attrs
                    for b in ( self.attrs.get(a, svr4attrs[a]), )
                    if b
                ]
                # Always overwrite installation timestamp
                attrs.append(("INSTDATE",
                    time.strftime("%b %d %Y %H:%M")))

                with open(pkginfo, "w") as pfile:
                        for k, v in attrs:
                                pfile.write("{0}={1}\n".format(k, v))

                # the svr4 pkg commands need contents file to work, but the
                # needed directories are in the SUNWpkgcmds package....
                # Since this file is always of zero length, we can let this
                # fail until those directories (and the commands that
                # need them) appear.

                try:
                        open(os.path.join(pkgplan.image.get_root(),
                            "var/sadm/install/contents"), "a").close()
                except IOError as e:
                        if e.errno != errno.ENOENT:
                                raise

                os.chmod(pkginfo, misc.PKG_FILE_MODE)

        def __old_refcount_cleanup(self, pkginfo, pkgdir):
                """Clean up the turds of the old refcounting implementation."""

                # Don't assume that the hardlinks are still in place; just
                # remove all consecutively numbered files.
                for i in itertools.count(2):
                        lfile = os.path.join(pkgdir, "pkginfo.{0:d}".format(i))
                        try:
                                os.unlink(lfile)
                        except OSError as e:
                                if e.errno == errno.ENOENT:
                                        break
                                raise

        def verify(self, img, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []

                pkgdir = os.path.join(img.get_root(), "var/sadm/pkg",
                    self.attrs["pkg"])

                # XXX this could be a better check & exactly validate pkginfo
                # contents
                if not os.path.isdir(pkgdir):
                        errors.append(
                            _("Missing directory var/sadm/pkg/{0}").format(
                            self.attrs["pkg"]))
                        return errors, warnings, info

                if not os.path.isfile(os.path.join(pkgdir, "pkginfo")):
                        errors.append(_("Missing file "
                            "var/sadm/pkg/{0}/pkginfo").format(
                            self.attrs["pkg"]))
                return errors, warnings, info

        def remove(self, pkgplan):

                # pkg directory is removed via implicit directory removal

                pkgdir = os.path.join(pkgplan.image.get_root(), "var/sadm/pkg",
                    self.attrs["pkg"])

                pkginfo = os.path.join(pkgdir, "pkginfo")

                self.__old_refcount_cleanup(pkginfo, pkgdir)

                try:
                        os.unlink(pkginfo)
                except OSError as e:
                        if e.errno != errno.ENOENT:
                                raise

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [
                    ("legacy", "legacy_pkg", self.attrs["pkg"], None),
                    ("legacy", "pkg", self.attrs["pkg"], None)
                ]

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action."""

                generic.Action._validate(self, fmri=fmri,
                    single_attrs=("category", "desc", "hotline", "name",
                    "vendor", "version"))
