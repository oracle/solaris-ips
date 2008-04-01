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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
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
from stat import *

import generic
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

                if not os.path.exists(os.path.dirname(path)):
                        self.makedirs(os.path.dirname(path), mode=755)

                lfile = file(path, "wb")
                # XXX Should throw an exception if shasum doesn't match
                # self.hash
                shasum = generic.gunzip_from_stream(stream, lfile)

                lfile.close()
                stream.close()

                os.chmod(path, mode)

                try:
                        portable.chown(path, owner, group)
                except OSError, e:
                        if e.errno != errno.EPERM:
                                raise

        def needsdata(self, orig):
                if not orig or orig.hash != self.hash:
                        return True

                return False

        def verify(self, img, pkg_fmri, **args):
                path = os.path.normpath(os.path.join(img.imgdir,
                    "pkg", pkg_fmri.get_dir_path(),
                    "license." + self.attrs["license"]))

                try:
                        f = file(path)
                        data = f.read()
                        f.close()
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return ["License file %s does not exist" % path]
                        return ["Unexpected exception %s" % e]
                if args["forever"] == True:
                        hashvalue = sha.new(data).hexdigest()
                        if hashvalue != self.hash:
                                return ["Hash: %s should be %s" % \
                                    (hashvalue, self.hash)]
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
