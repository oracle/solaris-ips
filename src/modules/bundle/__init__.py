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
# Copyright (c) 2007, 2015, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function

# The ordering is important -- SolarisPackageDirBundle must come before
# DirectoryBundle, or the latter class will recognize a Solaris package
# as a plain directory.
__all__ = [
    "SolarisPackageDirBundle",
    "DirectoryBundle",
    "SolarisPackageDatastreamBundle",
    "TarBundle"
]

import os
import sys

class InvalidBundleException(Exception):
        pass


class InvalidOwnershipException(InvalidBundleException):
        """Raised when gid or uid lookup fails for a file during bundle
        generation."""

        def __init__(self, fname, uid=None, gid=None):
                InvalidBundleException.__init__(self)
                self.fname = fname
                msg = []
                if uid:
                        msg.append("UID {uid} is not associated with a user "
                            "name (file: {fname})".format(uid=uid, fname=fname))
                if gid:
                        msg.append("GID {gid} is not associated with a group "
                            "name (file: {fname})".format(gid=gid, fname=fname))
                self.msg = '\n'.join(msg)

        def __str__(self):
                return self.msg


class Bundle(object):
        """Base bundle class."""

        def get_action(self, path):
                """Return the first action that matches the provided path or
                None."""
                for apath, data in self._walk_bundle():
                        if not apath:
                                continue
                        npath = apath.lstrip(os.path.sep)
                        if path == npath:
                                if type(data) == tuple:
                                        # Construct action on demand.
                                        return self.action(*data)
                                # Action was returned.
                                return data

def make_bundle(filename, **kwargs):
        """Determines what kind of bundle is at the given filename, and returns
        the appropriate bundle object.
        """

        for btype in __all__:
                bname = "pkg.bundle.{0}".format(btype)
                bmodule = __import__(bname)

                bmodule = sys.modules[bname]
                if bmodule.test(filename):
                        bundle_create = getattr(bmodule, btype)
                        return bundle_create(filename, **kwargs)

        raise TypeError("Unknown bundle type for '{0}'".format(filename))


if __name__ == "__main__":
        try:
                b = make_bundle(sys.argv[1])
        except TypeError as e:
                print(e)
                sys.exit(1)

        for file in b:
                print(file.type, file.attrs)
                try:
                        print(file.attrs["file"])
                        print(os.stat(file.attrs["file"]))
                except:
                        pass
