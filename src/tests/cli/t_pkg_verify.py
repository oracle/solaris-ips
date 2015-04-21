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

# Copyright (c) 2008, 2015, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import shutil
import subprocess
import tempfile
import time
import unittest


class TestPkgVerify(pkg5unittest.SingleDepotTestCase):
        # Tests in this suite use the read only data directory
        need_ro_data = True

        foo10 = """
            open foo@1.0,5.11-0
            add dir mode=0755 owner=root group=sys path=/etc
            add dir mode=0755 owner=root group=sys path=/etc/security
            add dir mode=0755 owner=root group=sys path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file bobcat mode=0644 owner=root group=bin path=/usr/bin/bobcat
            add file ls path=/usr/bin/ls mode=755 owner=root group=sys
            add file bobcat path=/etc/preserved mode=644 owner=root group=sys preserve=true timestamp="20080731T024051Z"
            add file dricon_maj path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file dricon_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file dricon_cls path=/etc/driver_classes mode=644 owner=root group=sys preserve=true
            add file dricon_mp path=/etc/minor_perm mode=644 owner=root group=sys preserve=true
            add file dricon_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add file dricon_ep path=/etc/security/extra_privs mode=644 owner=root group=sys preserve=true
            add file permission mode=0600 owner=root group=bin path=/etc/permission preserve=true
            add driver name=zigit alias=pci8086,1234
            close
            """

        sysattr = """
            open sysattr@1.0-0
            add dir mode=0755 owner=root group=bin path=/p1
            add file bobcat mode=0555 owner=root group=bin sysattr=SH path=/p1/bobcat
            close """

        misc_files = {
           "bobcat": "",
           "dricon_da": """zigit "pci8086,1234"\n""",
           "dricon_maj": """zigit 103\n""",
           "dricon_cls": """\n""",
           "dricon_mp": """\n""",
           "dricon_dp": """\n""",
           "dricon_ep": """\n""",
           "permission": ""
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                # We want at least one ELF file here to check for ELF action
                # verification.
                portable.copyfile("/usr/bin/ls", os.path.join(self.test_root,
                    "ls"))
                self.pkgsend_bulk(self.rurl, self.foo10)

        def test_00_bad_opts(self):
                """ test pkg verify with bad options """

                self.image_create(self.rurl)
                self.pkg_verify("-vq", exit=2)

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
                self.pkg_verify("foo", exit=1)
                self.assert_("Unexpected Exception" not in self.output)

                # Now install package.
                self.pkg("install foo")

                # Should not fail since informational messages are not
                # fatal.
                self.pkg_verify("foo")
                # Unprivileged users don't cause a traceback.
                retcode, output = self.pkg_verify("foo", su_wrap=True, out=True,
                    exit=1)
                self.assert_("Traceback" not in output)

                # Should not output anything when using -q.
                self.pkg_verify("-q foo")
                assert(self.output == "")

                # Should not fail if publisher is disabled and package is ok.
                self.pkg("set-publisher -d test")
                self.pkg_verify("foo")

                # Should not fail if publisher is removed and package is ok.
                self.pkg("unset-publisher test")
                self.pkg_verify("foo")

                # Should fail with exit code 1 if publisher is removed and
                # package is not ok.
                portable.remove(os.path.join(self.get_img_path(), "usr", "bin",
                    "bobcat"))
                self.pkg_verify("foo", exit=1)
                self.assert_("Unexpected Exception" not in self.output)
                self.assert_("PACKAGE" in self.output and "STATUS" in self.output)

                # Test that "-H" works as expected. 
                self.pkg_verify("foo -H", exit=1)
                self.assert_("PACKAGE" not in self.output and
                    "STATUS" not in self.output)

                # Should not output anything when using -q.
                self.pkg_verify("-q foo", exit=1)
                assert(self.output == "")
                self.pkg("set-publisher -p {0}".format(self.rurl))
                self.pkg("fix foo")

                # Informational messages should not be output unless -v
                # is provided.
                self.pkg("set-publisher -p {0}".format(self.rurl))
                self.pkg_verify("foo | grep bobcat", exit=1)
                self.pkg_verify("-v foo | grep bobcat")

                # Verify shouldn't care if timestamp has changed on
                # preserved files.
                fpath = os.path.join(self.get_img_path(), "etc", "preserved")
                ctime = time.time() - 1240
                os.utime(fpath, (ctime, ctime))
                self.pkg_verify("foo")

                # Verify should fail if file is missing.
                fpath = os.path.join(self.get_img_path(), "usr", "bin",
                    "bobcat")
                portable.remove(fpath)
                self.pkg_verify("foo", exit=1)

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
                self.pkg_verify("-v foo | grep 4321")

                # ...but it should not be treated as a fatal error.
                self.pkg_verify("foo")

        def test_02_installed(self):
                """When multiple FMRIs are given to pkg verify, if any of them
                aren't installed it should fail."""

                self.image_create(self.rurl)
                self.pkg("install foo")
                self.pkg_verify("foo nonexistent", exit=1)
                self.pkg("uninstall foo")

        def test_03_invalid(self):
                """Test that pkg verify handles invalid input gracefully."""

                self.image_create(self.rurl)

                # Verify invalid package causes graceful exit.
                self.pkg_verify("_not_valid", exit=1)

                # Verify unmatched input fails gracefully.
                self.pkg_verify("no/such/package", exit=1)

                # Verify invalid package name and unmatched input combined with
                # installed package name results in graceful failure.
                self.pkg("install foo")
                self.pkg_verify("_not_valid no/such/package foo", exit=1)

        def test_03_editable(self):
                """When editable files are changed, verify should treat these specially"""
                # check that verify is silent on about modified editable files
                self.image_create(self.rurl)
                self.pkg("install foo")
                fd = file(os.path.join(self.get_img_path(), "etc", "preserved"), "w+")
                fd.write("Bobcats are here")
                fd.close()
                self.pkg_verify("foo")
                assert("editable file has been changed" not in self.output)
                # find out about it via -v
                self.pkg_verify("-v foo")
                self.output.index("etc/preserved")
                self.output.index("editable file has been changed")

        def test_verify_changed_manifest(self):
                """Test that running package verify won't change the manifest of
                an installed package even if it has changed in the repository.
                """

                self.image_create(self.rurl)
                self.pkg("install foo")

                self.pkg_verify("")
                self.pkg("set-property signature-policy require-signatures")
                self.pkg_verify("", exit=1)

                # Specify location as filesystem path.
                self.pkgsign_simple(self.dc.get_repodir(), "foo")

                self.pkg_verify("", exit=1)

        def test_sysattrs(self):
                """Test that system attributes are verified correctly."""

                if portable.osname != "sunos":
                        raise pkg5unittest.TestSkippedException(
                            "System attributes unsupported on this platform.")

                self.pkgsend_bulk(self.rurl, [self.sysattr])

                # Need to create an image in /var/tmp since sysattrs don't work
                # in tmpfs.
                old_img_path = self.img_path()
                self.set_img_path(tempfile.mkdtemp(prefix="test-suite",
                    dir="/var/tmp"))

                self.image_create(self.rurl)
                self.pkg("install sysattr")
                self.pkg("verify")
                fpath = os.path.join(self.img_path(),"p1/bobcat")

                # Need to get creative here to remove the system attributes
                # since you need the sys_linkdir privilege which we don't have:
                # see run.py:393
                # So we re-create the file with correct owner and mode and the
                # only thing missing are the sysattrs.
                portable.remove(fpath)
                portable.copyfile(os.path.join(self.test_root, "bobcat"), fpath)
                os.chmod(fpath, 0o555)
                os.chown(fpath, -1, 2)
                self.pkg("verify", exit=1)
                for sattr in ('H','S'):
                        expected = "System attribute '{0}' not set".format(sattr)
                        self.assertTrue(expected in self.output,
                            "Missing in verify output:  {0}".format(expected))

                shutil.rmtree(self.img_path())
                self.set_img_path(old_img_path)


if __name__ == "__main__":
        unittest.main()
