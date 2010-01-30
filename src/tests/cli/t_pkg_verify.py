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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import unittest

class TestPkgVerify(pkg5unittest.SingleDepotTestCase):

        foo10 = """
            open foo@1.0,5.11-0
            add dir mode=0755 owner=root group=sys path=/etc
            add dir mode=0755 owner=root group=sys path=/etc/security
            add dir mode=0755 owner=root group=sys path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file bobcat mode=0644 owner=root group=bin path=/usr/bin/bobcat
            add file dricon_maj path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file dricon_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file dricon_cls path=/etc/driver_classes mode=644 owner=root group=sys preserve=true
            add file dricon_mp path=/etc/minor_perm mode=644 owner=root group=sys preserve=true
            add file dricon_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add file dricon_ep path=/etc/security/extra_privs mode=644 owner=root group=sys preserve=true
            add driver name=zigit alias=pci8086,1234
            close
            """

        misc_files = {
           "bobcat": "",
           "dricon_da": """zigit "pci8086,1234"\n""",
           "dricon_maj": """zigit 103\n""",
           "dricon_cls": """\n""",
           "dricon_mp": """\n""",
           "dricon_dp": """\n""",
           "dricon_ep": """\n"""
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.foo10)

        def test_pkg_verify_bad_opts(self):
                """ test pkg verify with bad options """

                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("verify -vq", exit=2)

        def test_bug_1463(self):
                """When multiple FMRIs are given to pkg verify,
                if any of them aren't installed it should fail."""

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("install foo")
                self.pkg("verify foo nonexistent", exit=1)
                self.pkg("uninstall foo")

        def test_0_verify(self):
                """Ensure that verify returns failure as expected when packages
                are not correctly installed."""

                # XXX either this should be more comprehensive or more testing
                # needs to be added somewhere else appropriate.
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                # Should fail since foo is not installed.
                self.pkg("verify foo", exit=1)

                # Now install package.
                self.pkg("install foo")

                # Should not fail since informational messages are not
                # fatal.
                self.pkg("verify foo")

                # Informational messages should not be output unless -v
                # is provided.
                self.pkg("verify foo | grep bobcat", exit=1)
                self.pkg("verify -v foo | grep bobcat")

                # Get path to installed file.
                fpath = os.path.join(self.get_img_path(), "usr", "bin",
                    "bobcat")

                # Should fail since file is missing.
                portable.remove(fpath)
                self.pkg("verify foo", exit=1)

                # Now verify that verify warnings are not fatal.
                self.pkg("fix")

                fpath = os.path.join(self.get_img_path(), "etc",
                    "driver_aliases")

                with open(fpath, "ab+") as f:
                        out = ""
                        for l in f:
                                if l.find("zigit") != -1:
                                        nl = l.replace("1234", "4321")
                                        out += nl
                                out += l
                        f.truncate(0)
                        f.write(out)

                # Verify should find the extra alias...
                self.pkg("verify -v foo | grep 4321")

                # ...but it should not be treated as a fatal error.
                self.pkg("verify foo")


if __name__ == "__main__":
        unittest.main()

