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

"""module describing a license packaging object

This module contains the LicenseAction class, which represents a license
packaging object.  This contains a payload of the license text, and a single
attribute, 'license', which is the name of the license.  Licenses are
installed on the system in the package's directory."""

import errno
import os
import StringIO
from stat import S_IWRITE, S_IREAD

import generic
import pkg.misc as misc
import pkg.portable as portable

class LicenseAction(generic.Action):
        """Class representing a license packaging object."""

        __slots__ = ["hash"]

        name = "license"
        key_attr = "license"
        reverse_indices = ("license", )

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"

        def preinstall(self, pkgplan, orig):
                # set attrs["path"] so filelist can handle this action
                # No leading / chars allowed
                self.attrs["path"] = os.path.normpath(os.path.join(
                    pkgplan.image.img_prefix,
                    "pkg",
                    pkgplan.destination_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

        def install(self, pkgplan, orig):
                """Client-side method that installs the license."""
                owner = 0
                group = 0

                path = self.attrs["path"]

                stream = self.data()

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                # make sure the directory exists and the file is writable
                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path),
                            mode=misc.PKG_DIR_MODE,
                            fmri=pkgplan.destination_fmri)
                elif os.path.exists(path):
                        os.chmod(path, misc.PKG_FILE_MODE)

                lfile = file(path, "wb")
                # XXX Should throw an exception if shasum doesn't match
                # self.hash
                shasum = misc.gunzip_from_stream(stream, lfile)

                lfile.close()
                stream.close()

                os.chmod(path, misc.PKG_RO_FILE_MODE)

                try:
                        portable.chown(path, owner, group)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def needsdata(self, orig, pkgplan):
                # We always want to download the license
                return True

        def verify(self, img, pkg_fmri, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []

                path = os.path.normpath(os.path.join(img.imgdir,
                    "pkg", pkg_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

                if args["forever"] == True:
                        try:
                                chash, cdata = misc.get_data_digest(path)
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT:
                                        errors.append(_("License file %s does "
                                            "not exist.") % path)
                                        return errors, warnings, info
                                raise

                        if chash != self.hash:
                                errors.append(_("Hash: '%(found)s' should be "
                                    "'%(expected)s'") % { "found": chash,
                                    "expected": self.hash})
                return errors, warnings, info

        def remove(self, pkgplan):
                path = os.path.normpath(os.path.join(pkgplan.image.imgdir,
                    "pkg", pkgplan.origin_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

                try:
                        # Make file writable so it can be deleted
                        os.chmod(path, S_IWRITE|S_IREAD)
                        os.unlink(path)
                except OSError,e:
                        if e.errno != errno.ENOENT:
                                raise

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                indices = [("license", idx, self.attrs[idx], None)
                           for idx in self.reverse_indices]
                if hasattr(self, "hash"):
                        indices.append(("license", "content", self.hash, None))

                return indices

        def get_text(self, img, fmri):
                """Retrieves and returns the payload of the license (which
                should be text).  This may require remote retrieval of
                resources and so this could raise a TransportError or other
                ApiException."""

                opener = self.get_local_opener(img, fmri)
                if opener:
                        # License installed already; return its content.
                        return opener().read()

                try:
                        pub = img.get_publisher(fmri.get_publisher())
                        return img.transport.get_content(pub, self.hash)
                finally:
                        img.cleanup_downloads()

        def get_local_opener(self, img, fmri):
                """Return an opener for the license text from the local disk or
                None if the data for the text is not on-disk."""

                path = os.path.normpath(os.path.join(img.imgdir, "pkg",
                    fmri.get_dir_path(), "license." + self.attrs["license"]))

                if not os.path.exists(path):
                        return None

                def opener():
                        # XXX Do we check to make sure that what's there is what
                        # we think is there (i.e., re-hash)?
                        return file(path, "rb")

                return opener

        @property
        def must_accept(self):
                """Returns a boolean value indicating whether this license
                action requires acceptance of its payload by clients."""

                return self.attrs.get("must-accept", "").lower() == "true"

        @property
        def must_display(self):
                """Returns a boolean value indicating whether this license
                action requires its payload to be displayed by clients."""

                return self.attrs.get("must-display", "").lower() == "true"

