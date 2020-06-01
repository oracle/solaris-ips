#!/usr/bin/python
# -*- coding: utf-8
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
# Copyright (c) 2008, 2020, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import pkg5unittest
import sys
import unittest

import pkg.portable as portable


class TestPkgCpuDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True
        # leverage smf test infrastructure here
        smf_cmds = {
            "cpu": """#!/usr/bin/python3
import os
import resource
import sys


def main():
    installed_version = os.environ.get("PKG_INSTALLED_VERSION", None)
    if not installed_version:
        return 0
    for n in range(1, len(sys.argv)):
        key, value = sys.argv[n].split("=", 1)
        if key == "check.include":
            if installed_version > value is True:
                 print("{0}".format(key), file=sys.stderr)
                 return 1
            return 0
        if key == "check.exclude":
            if value > installed_version is True:
                 print("{0}".format(key), file=sys.stderr)
                 return 1
            return 0
        if key == "dump_core":
            # avoid creating a core file
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.abort()
    print("Neither check.include nor check.exclude specified in dependency")
    return 242

if __name__ == "__main__":
        # Make all warnings be errors.
        import warnings
        warnings.simplefilter('error')

        sys.exit(main())
"""}

        def setUp(self):

                pkg5unittest.SingleDepotTestCase.setUp(self)

                self.pkg_list = []

                for t in (
                                ("1.0", "cpu", "argo"),
                                ("1.1", "cpu", "babinda"),
                                ("1.2", "cpu", "coolabah"),
                                ("1.3", "cpu", "drongo"),
                                ("2.0", "platform", "dropbear"),
                                ("2.1", "platform", "hoopsnake"),
                                ("2.2", "platform", "oodnadatta"),
                                ("3.0", "iset", "absinthe"),
                                ("3.1", "iset", "bolli"),
                                ("3.4", "iset", "limoncello")
                ):
                    self.pkg_list += ["""
                    open A@{0},5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/cpu check.version-type={1} check.include={2}
                    close
                    open B@{3},5.12-0
                    add depend type=origin root-image=true fmri=pkg:/feature/cpu check.version-type={4} check.exclude={5}
                    close """.format(*(t + t))]

                self.pkg_list += ["""
                    open A@1.7,5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/cpu
                    close """]

                self.pkg_list += ["""
                    open A@1.8,5.12-0
                    add depend type=origin root-image=true fmri=pkg:/feature/cpu dump_core=1
                    close"""]

                self.pkg_list += ["""
                    open C@1.0,5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/cpu
                    close"""]

        def test_cpu_dependency(self):
                """test origin cpu dependency
                cpu test simulator uses alphabetic comparison"""

                if portable.osname != "sunos":
                        raise pkg5unittest.TestSkippedException(
                            "cpu check unsupported on this platform.")

                rurl = self.dc.get_repo_url()
                plist = self.pkgsend_bulk(rurl, self.pkg_list)
                self.image_create(rurl)
                os.environ["PKG_INSTALLED_VERSION"] = "hoopsnake"
                # trim some of the versions out; note that pkgs w/ cpu
                # errors/problems are silently ignored.
                self.pkg("install -v A@1.0 B@1.0")
                self.pkg("list -v")
                os.environ["PKG_INSTALLED_VERSION"] = "dropbear"
                self.pkg("install A@1.4", 1)
                # exercise general error codes
                self.pkg("install A@1.7", 1)
                # verify that upreving the cpu lets us install more
                self.pkg("list")
                os.environ["PKG_INSTALLED_VERSION"] = "coolabah"
                self.pkg("update *@latest")
                self.pkg("list")
                self.pkg("verify A@1.5", 1)
                del os.environ["PKG_INSTALLED_VERSION"]
                self.pkg("list")
                # this is a trick, there is no v1.6
                self.pkg("verify A@1.6", 1)
                # check that we ignore dependencies w/ missing enumerators
                self.pkg("install C@1.0")
                self.pkg("list")
