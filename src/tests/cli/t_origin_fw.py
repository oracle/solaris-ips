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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
from __future__ import print_function

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import pkg5unittest
import unittest
import sys
import pkg.portable as portable


class TestPkgFWDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True
        # leverage smf test infrastructure here
        smf_cmds = {
            "fwenum": """#!/usr/bin/python
import os
import resource
import sys

def main():
    installed_version = os.environ.get("PKG_INSTALLED_VERSION", None)
    devs_present = os.environ.get("PKG_NUM_FAKE_DEVICES", "1")
    if not installed_version:
        return 0
    for n in range(1, len(sys.argv)):
        key, value = sys.argv[n].split("=", 1)
        c = installed_version < value
        if key == "check.minimum-version" or key == "minimum-version":
            if c is False:
               if int(devs_present) > 240:
                   devs_present = "240"
               return int(devs_present)
            return 0
        if key == "dump_core":
            # avoid creating a core file
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.abort()
    print("attribute check.minimum-version not specified in dependency")
    return 241

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
                    ("1.0", "dwarf"),
                    ("1.1", "elf"),
                    ("1.2", "hobbit"),
                    ("1.3", "wizard")
                ):
                    self.pkg_list += ["""
                    open A@{0},5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/firmware/fwenum check.minimum-version={1}
                    close
                    open B@{2},5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/firmware/fwenum check.minimum-version={3}
                    close """.format(*(t + t))]

                self.pkg_list += ["""
                    open A@1.4,5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/firmware/fwenum
                    close """]

                self.pkg_list += ["""
                    open A@1.6,5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/firmware/fwenum dump_core=1
                    close"""]

                self.pkg_list += ["""
                    open C@1.0,5.11-0
                    add depend type=origin root-image=true fmri=pkg:/feature/firmware/no-such-enumerator
                    close"""]

        def test_fw_dependency(self):
                """test origin firmware dependency"""
                """firmware test simulator uses alphabetic comparison"""

                if portable.osname != "sunos":
                        raise pkg5unittest.TestSkippedException(
                            "Firmware check unsupported on this platform.")

                rurl = self.dc.get_repo_url()
                plist = self.pkgsend_bulk(rurl, self.pkg_list)
                self.image_create(rurl)

                os.environ["PKG_INSTALLED_VERSION"] = "elf"
                # trim some of the versions out; note that pkgs w/ firmware
                # errors/problems are silently ignored.
                self.pkg("install A B")
                self.pkg("list -v A@1.3 B@1.3")
                # test verify by changing device version
                os.environ["PKG_INSTALLED_VERSION"] = "dwarf"
                self.pkg("verify A@1.1", 1)
                os.environ["PKG_INSTALLED_VERSION"] = "elf"
                # exercise large number of devices code
                os.environ["PKG_NUM_FAKE_DEVICES"] = "500"
                self.pkg("install A@1.3", 4)
                # exercise general error codes
                self.pkg("install A@1.4", 1)
                self.pkg("install A@1.6", 1)
                # verify that upreving the firmware lets us install more
                os.environ["PKG_INSTALLED_VERSION"] = "hobbit"
                del os.environ["PKG_NUM_FAKE_DEVICES"]
                self.pkg("update -nv", 4)
                self.pkg("verify A@1.2", 1)
                # simulate removing device
                del os.environ["PKG_INSTALLED_VERSION"]
                self.pkg("list -v")
                self.pkg("update")
                self.pkg("list -v")
                self.pkg("verify A@1.6")
                # ok since we never drop core here since device
                # doesn't exist.

                # check that we ignore dependencies w/ missing enumerators
                self.pkg("install C@1.0")
