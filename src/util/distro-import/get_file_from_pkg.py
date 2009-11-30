#!/usr/bin/python2.6
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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

#
# given two args, a fully specified path name and a file name,
# return file on stdout
#

import os
import platform
import sys

from pkg.sysvpkg import SolarisPackage
from pkg.bundle.SolarisPackageDirBundle import SolarisPackageDirBundle

def setup_environment(path_to_proto):
        """ Set up environment for running the Solaris import.

            We modify the Python search path by adjusting sys.path so
            that it references the proto area.

            path_to_proto should be a relative path indicating a path
            to proto area of the workspace.

            This function looks at argv[0] to compute the ultimate
            path to the proto area.

        """

        osname = platform.uname()[0].lower()
        proc = 'unknown'
        if osname == 'sunos':
                proc = platform.processor()
        elif osname == 'linux':
                proc = "linux_" + platform.machine()
        elif osname == 'windows':
                proc = osname
        elif osname == 'darwin':
                proc = osname
        else:
                print >> sys.stderr, \
                    "Unable to determine appropriate proto area location."
                sys.exit(1)

        # Figure out from where we're invoking the command
        cmddir, cmdname = os.path.split(sys.argv[0])
        cmddir = os.path.realpath(cmddir)

        if "ROOT" in os.environ:
                g_proto_area = os.environ["ROOT"]
        else:
                g_proto_area = "%s/%s/root_%s" % (cmddir, path_to_proto, proc)

        # Clean up relative ../../, etc. out of path to proto
        g_proto_area = os.path.realpath(g_proto_area)

        pkgs = "%s/usr/lib/python2.6/vendor-packages" % g_proto_area

        sys.path.insert(1, pkgs)

pkgpath = sys.argv[1]
filename = sys.argv[2]

setup_environment("../../../proto")
p = SolarisPackage(pkgpath)

if filename not in (f.pathname for f in p.manifest):
        raise "No such file %s in package %s" % (filename, pkgpath)

bundle = SolarisPackageDirBundle(pkgpath)

for f in bundle:
        if f.attrs["path"] == filename:
	        d = f.data().read()
	        sys.stdout.write(d)
	        sys.exit(0)
