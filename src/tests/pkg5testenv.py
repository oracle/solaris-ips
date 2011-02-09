#!/usr/bin/python

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

# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.

import os
import sys
import platform
import tempfile

def setup_environment(path_to_proto, covdir=None, debug=False):
        """ Set up environment for doing testing.

            We set PYTHONPATH and PATH so that they reference the proto
            area, and clear packaging related environment variables
            (every variable prefixed with PKG_).

            path_to_proto should be a relative path indicating a path
            to proto area of the workspace.  So, if your test case is
            three levels deep: ex. src/tests/cli/foo.py, this should be
            "../../../proto"

            This function looks at argv[0] to compute the ultimate
            path to the proto area; this is nice because you can then
            invoke test cases like normal commands; i.e.:
            "python cli/t_my_test_case.py" will just work.

            If 'covdir' is provided, coverage will be started and the
            related coverage object returned.
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
        elif osname == 'aix':
                proc = osname
        else:
                print "Unable to determine appropriate proto area location."
                print "This is a porting problem."
                sys.exit(1)

        # Figure out from where we're invoking the command
        cmddir, cmdname = os.path.split(sys.argv[0])
        cmddir = os.path.realpath(cmddir)

        if "ROOT" in os.environ:
                proto_area = os.environ["ROOT"]
        else:
                proto_area = "%s/%s/root_%s" % (cmddir, path_to_proto, proc)

        # Clean up relative ../../, etc. out of path to proto
        proto_area = os.path.realpath(proto_area)

        pkgs = "%s/usr/lib/python2.6/vendor-packages" % proto_area
        bins = "%s/usr/bin" % proto_area

        sys.path.insert(1, pkgs)

        #
        # Because subprocesses must also source from the proto area,
        # we need to set PYTHONPATH in the environment as well as
        # in sys.path.
        #
        if "PYTHONPATH" in os.environ:
                pypath = os.pathsep + os.environ["PYTHONPATH"]
        else:
                pypath = ""
        os.environ["PYTHONPATH"] = "." + os.pathsep + pkgs + pypath

        os.environ["PATH"] = bins + os.pathsep + os.environ["PATH"]

        # Use "keys"; otherwise we'll change dictionary size during iteration.
        for k in os.environ.keys():
                if k.startswith("PKG_") or k in ("http_proxy", "HTTP_PROXY",
                    "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
                        del os.environ[k]

        #
        # Start coverage before proceeding so that reports are accurate.
        #
        cov = None
        if covdir:
                # This must be imported here just after PYTHONPATH setup above.
                import coverage
                os.chmod(covdir, 01777)
                cov_file = "%s/pkg5" % covdir
                cov = coverage.coverage(data_file=cov_file, data_suffix=True)
                cov.start()

        #
        # Tell package manager where its application data files live.
        #
        os.environ["PACKAGE_MANAGER_ROOT"] = proto_area

        from pkg.client import global_settings
        global_settings.client_name = "pkg"

        import pkg5unittest
        pkg5unittest.g_proto_area = proto_area

        # Save off the value for tempdir when we were invoked, since the
        # suite will subsequently modify tempdir to sandbox test cases.
        pkg5unittest.g_tempdir = tempfile.gettempdir()

        return cov
