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

"""module describing a license packaging object

This module contains the LicenseAction class, which represents a license
packaging object.  This contains a payload of the license text, and a single
attribute, 'license', which is the name of the license.  Licenses are
installed on the system in the package's directory."""

import os
import errno
from stat import S_IWRITE, S_IREAD

import generic
import pkg.misc as misc
import pkg.portable as portable

class LicenseAction(generic.Action):
        """Class representing a license packaging object."""

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
                mode = 0444
                owner = 0
                group = 0

                path = self.attrs["path"]

                stream = self.data()

                path = os.path.normpath(os.path.sep.join(
                    (pkgplan.image.get_root(), path)))

                # make sure the directory exists and the file is writable
                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path), mode=0755)
                elif os.path.exists(path):
                        os.chmod(path, 0644)

                lfile = file(path, "wb")
                # XXX Should throw an exception if shasum doesn't match
                # self.hash
                shasum = misc.gunzip_from_stream(stream, lfile)

                lfile.close()
                stream.close()

                os.chmod(path, mode)

                try:
                        portable.chown(path, owner, group)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def needsdata(self, orig):
                # We always want to download the license
                return True

        def verify(self, img, pkg_fmri, **args):
                path = os.path.normpath(os.path.join(img.imgdir,
                    "pkg", pkg_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

                if args["forever"] == True:
                        try:
                                chash, cdata = misc.get_data_digest(path)
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT:
                                        return [_("License file %s does not "
                                            "exist.") % path]
                                raise

                        if chash != self.hash:
                                return [_("Hash: '%(found)s' should be "
                                    "'%(expected)s'") % { "found": chash,
                                    "expected": self.hash}]
                return []

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

        def get_local_opener(self, img, fmri):
                """Return an opener for the license text from the local disk."""

                path = os.path.normpath(os.path.join(img.imgdir, "pkg",
                    fmri.get_dir_path(), "license." + self.attrs["license"]))

                def opener():
                        # XXX Do we check to make sure that what's there is what
                        # we think is there (i.e., re-hash)?
                        return file(path, "rb")

                return opener

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                indices = [("license", idx, self.attrs[idx], None)
                           for idx in self.reverse_indices]
                if hasattr(self, "hash"):
                        indices.append(("license", "content", self.hash, None))

                return indices
