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

# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import time
import unittest


class TestPkgVerify(pkg5unittest.SingleDepotTestCase):

        foo10 = """
            open foo@1.0,5.11-0
            add dir mode=0755 owner=root group=sys path=/etc
            add dir mode=0755 owner=root group=sys path=/etc/security
            add dir mode=0755 owner=root group=sys path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file bobcat mode=0644 owner=root group=bin path=/usr/bin/bobcat
            add file bobcat path=/etc/preserved mode=644 owner=root group=sys preserve=true timestamp="20080731T024051Z"
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
                self.pkgsend_bulk(self.rurl, self.foo10)

        def test_00_bad_opts(self):
                """ test pkg verify with bad options """

                self.image_create(self.rurl)
                self.pkg("verify -vq", exit=2)

        def test_01_basics(self):
                """Ensure that verify returns failure as expected when packages
                are not correctly installed."""

                # XXX either this should be more comprehensive or more testing
                # needs to be added somewhere else appropriate.
                self.image_create(self.rurl)

                # Create a dummy publisher so that test publisher can be removed
                # and added back as needed.
                self.pkg("set-publisher -P ignored")

                # Should fail since foo is not installed.
                self.pkg("verify foo", exit=1)

                # Now install package.
                self.pkg("install foo")

                # Should not fail since informational messages are not
                # fatal.
                self.pkg("verify foo")

                # Should not fail if publisher is disabled and package is ok.
                self.pkg("set-publisher -d test")
                self.pkg("verify foo")

                # Should not fail if publisher is removed and package is ok.
                self.pkg("unset-publisher test")
                self.pkg("verify foo")

                # Should fail with exit code 1 if publisher is removed and
                # package is not ok.
                portable.remove(os.path.join(self.get_img_path(), "usr", "bin",
                    "bobcat"))
                self.pkg("verify foo", exit=1)
                self.pkg("set-publisher -p %s" % self.rurl)
                self.pkg("fix foo")

                # Informational messages should not be output unless -v
                # is provided.
                self.pkg("set-publisher -p %s" % self.rurl)
                self.pkg("verify foo | grep bobcat", exit=1)
                self.pkg("verify -v foo | grep bobcat")

                # Verify shouldn't care if timestamp has changed on
                # preserved files.
                fpath = os.path.join(self.get_img_path(), "etc", "preserved")
                ctime = time.time() - 1240
                os.utime(fpath, (ctime, ctime))
                self.pkg("verify foo")

                # Verify should fail if file is missing.
                fpath = os.path.join(self.get_img_path(), "usr", "bin",
                    "bobcat")
                portable.remove(fpath)
                self.pkg("verify foo", exit=1)

                # Now verify that verify warnings are not fatal (because
                # package contained bobcat!).
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

        def test_02_installed(self):
                """When multiple FMRIs are given to pkg verify, if any of them
                aren't installed it should fail."""

                self.image_create(self.rurl)
                self.pkg("install foo")
                self.pkg("verify foo nonexistent", exit=1)
                self.pkg("uninstall foo")

        def test_03_invalid(self):
                """Test that pkg verify handles invalid input gracefully."""

                self.image_create(self.rurl)

                # Verify invalid package causes graceful exit.
                self.pkg("verify _not_valid", exit=1)

                # Verify unmatched input fails gracefully.
                self.pkg("verify no/such/package", exit=1)

                # Verify invalid package name and unmatched input combined with
                # installed package name results in graceful failure.
                self.pkg("install foo")
                self.pkg("verify _not_valid no/such/package foo", exit=1)


if __name__ == "__main__":
        unittest.main()
