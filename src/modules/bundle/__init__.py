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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

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
from pkg.bundle import *

def make_bundle(filename):
        """Determines what kind of bundle is at the given filename, and returns
        the appropriate bundle object.
        """

        for type in __all__:
                if eval("%s.test('%s')" % (type, filename)):
                        return eval("%s.%s('%s')" % (type, type, filename))

        raise TypeError("Unknown bundle type for '%s'" % filename)

if __name__ == "__main__":
        try:
                b = make_bundle(sys.argv[1])
        except TypeError, e:
                print e
                sys.exit(1)

        for file in b:
                print file.type, file.attrs
                try:
                        print file.attrs["file"]
                        print os.stat(file.attrs["file"])
                except:
                        pass
