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

# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.

from __future__ import print_function
import os
import six
import sys
import platform
import tempfile

def setup_environment(path_to_proto, debug=False, system_test=False):
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

            If 'system_test' is True, tests will run on live system.
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
                print("Unable to determine appropriate proto area location.")
                print("This is a porting problem.")
                sys.exit(1)

        # Figure out from where we're invoking the command
        cmddir, cmdname = os.path.split(sys.argv[0])
        cmddir = os.path.realpath(cmddir)

        if "ROOT" in os.environ:
                pkg_path = os.environ["ROOT"]
        else:
                if system_test:
                        pkg_path = "/"
                else:
                        pkg_path = "{0}/{1}/root_{2}".format(
                            cmddir, path_to_proto, proc)

        proto_area = "{0}/{1}/root_{2}".format(cmddir, path_to_proto, proc)

        # Clean up relative ../../, etc. out of path to proto
        pkg_path = os.path.realpath(pkg_path)
        proto_area = os.path.realpath(proto_area)

        pkgs = os.path.join(pkg_path, "usr/lib/python{0}/vendor-packages".format(
            sys.version[0:3]))
        bins = os.path.join(pkg_path, "usr/bin")
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

        # Because some test cases will fail under Python 3 if the locale is set
        # to "C". A "C" locale supports only "ascii" characters, so essentially
        # if we want to test unicode characters, we need to use "utf-8" locale.
        if six.PY3:
                os.environ["LC_ALL"] = "en_US.UTF-8"

        # Proxy environment variables cause all kinds of problems, strip them
        # all out.
        # Use "keys"; otherwise we'll change dictionary size during iteration.
        for k in list(os.environ.keys()):
                if k.startswith("PKG_") or k.lower().endswith("_proxy"):
                        del os.environ[k]

        #
        # Tell package manager where its application data files live.
        #
        os.environ["PACKAGE_MANAGER_ROOT"] = pkg_path

        from pkg.client import global_settings
        global_settings.client_name = "pkg"

        import pkg5unittest
        pkg5unittest.g_proto_area = proto_area
        pkg5unittest.g_test_dir = cmddir
        pkg5unittest.g_pkg_path = pkg_path

        # Save off the value for tempdir when we were invoked, since the
        # suite will subsequently modify tempdir to sandbox test cases.
        pkg5unittest.g_tempdir = tempfile.gettempdir()
