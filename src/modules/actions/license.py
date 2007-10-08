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

"""module describing a license packaging object

This module contains the LicenseAction class, which represents a license
packaging object.  This contains a payload of the license text, and a single
attribute, 'license', which is the name of the license.  Licenses are
installed on the system in the package's directory."""

import os
import errno
import sha

import generic

class LicenseAction(generic.Action):
        """Class representing a license packaging object."""

        name = "license"
        key_attr = "license"
        reverse_indices = ("license", )

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                self.hash = "NOHASH"

        def install(self, pkgplan, orig):
                """Client-side method that installs the license."""
                mode = 0444
                owner = 0
                group = 0

                path = os.path.normpath(os.path.join(pkgplan.image.imgdir,
                    "pkg", pkgplan.destination_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

                stream = self.data()
                lfile = file(path, "wb")
                # XXX Should throw an exception if shasum doesn't match
                # self.hash
                shasum = generic.gunzip_from_stream(stream, lfile)

                lfile.close()
                stream.close()

                os.chmod(path, mode)

                try:
                        os.chown(path, owner, group)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def remove(self, pkgplan):
                path = os.path.normpath(os.path.join(pkgplan.image.imgdir,
                    "pkg", pkgplan.origin_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

                os.unlink(path)
