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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

#
# given two args, a fully specified path name and a file name,
# return file on stdout
#

import sys

from pkg.sysvpkg import SolarisPackage
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle


pkgpath = sys.argv[1]
filename = sys.argv[2]

p = SolarisPackage(pkgpath)

if filename not in (f.pathname for f in p.manifest):
        raise "No such file %s in package %s" % (filename, pkgpath)

bundle = SolarisPackageDirBundle(pkgpath)

for f in bundle:
        if f.attrs["path"] == filename:
	        d = f.data().read()
	        sys.stdout.write(d)
	        sys.exit(0)
