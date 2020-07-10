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

# Copyright (c) 2008, 2020, Oracle and/or its affiliates.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable as portable
import shutil
import simplejson as json
import subprocess
import tempfile
import time
import unittest

class TestPkgVerify(pkg5unittest.SingleDepotTestCase):
        # Tests in this suite use the read only data directory
        need_ro_data = True

        foo10 = """
            open foo@1.0,5.11-0:20160229T095441Z
            add dir mode=0755 owner=root group=sys path=/etc
            add dir mode=0755 owner=root group=sys path=/etc/security
            add dir mode=0755 owner=root group=sys path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file bobcat mode=0644 owner=root group=bin path=/usr/bin/bobcat
            add file ls path=/usr/bin/ls mode=755 owner=root group=sys
            add link path=/usr/bin/bobcat_link target=/usr/bin/bobcat
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
        bar10 = """
            open bar@1.0,5.11-0:20110908T004546Z
            add dir mode=0755 owner=root group=sys path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add link path=/usr/bin/bobcat_link target=/usr/bin/bobcat
            add file bronze1 mode=644 owner=root group=sys path=/etc/bronze1
            add file bronze2 mode=644 owner=root group=sys path=/etc/bronze2
            close
            """

        bla10 = """
            open bla@1.0,5.11-0
            add dir mode=0755 owner=root group=sys path=/opt
            add dir mode=0755 owner=root group=sys path=/opt/mybin
            add file test_perm mode=644 owner=root group=sys path=/opt/mybin/test_perm
            close
            """

        sysattr = """
            open sysattr@1.0-0
            add dir mode=0755 owner=root group=bin path=/p1
            add file bobcat mode=0555 owner=root group=bin sysattr=SH path=/p1/bobcat
            close """

        sysattr2 = """
            open sysattr2@1.0-0
            add dir mode=0755 owner=root group=bin path=/p2
            add file bobcat mode=0555 owner=root group=bin sysattr=hidden sysattr=sensitive path=/p2/bobcat
            close """

        misc_files = {
           "bobcat": "",
           "dricon_da": """zigit "pci8086,1234"\n""",
           "dricon_maj": """zigit 103\n""",
           "dricon_cls": """\n""",
           "dricon_mp": """\n""",
           "dricon_dp": """\n""",
           "dricon_ep": """\n""",
           "permission": "",
           "bronze1": "",
           "bronze2": "",
           "test_perm": "Test File"
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
                self.assertTrue("Unexpected Exception" not in self.output)

                # Now install package.
                self.pkg("install foo")

                # Should not fail since informational messages are not
                # fatal.
                self.pkg_verify("foo")
                # Unprivileged users don't cause a traceback.
                retcode, output = self.pkg_verify("foo", su_wrap=True, out=True,
                    exit=1)
                self.assertTrue("Traceback" not in output)

                # Should not output anything when using -q.
                self.pkg_verify("-q foo")
                assert(self.output == "")

                # Should not fail since the path exists in the package
                # and is intact.
                self.pkg_verify("-v -p /etc/name_to_major")
                self.assertTrue("foo" in self.output
                    and "etc/name_to_major" not in self.output)
                self.pkg_verify("-v -p /usr/bin/bobcat_link")
                self.assertTrue("OK" in self.output)
                self.pkg_verify("-v -p /usr")
                self.assertTrue(self.output.count("OK") == 1)

                # Should output path not found.
                self.pkg_verify("-p nonexist")
                self.assertTrue("not found" in self.output)

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
                self.assertTrue("Unexpected Exception" not in self.output)
                self.assertTrue("PACKAGE" in self.output and "STATUS" in self.output)

                # Should fail with exit code 2 because of invalid option combo.
                self.pkg_verify("-p /usr/bin/bobcat --unpackaged", exit=2)
                self.pkg_verify("-p /usr/bin/bobcat --unpackaged-only", exit=2)

                # Should fail with exit code 1 because the file is removed
                # and the package is not ok.
                self.pkg_verify("-p /usr/bin/bobcat", exit=1)
                self.assertTrue("PACKAGE" in self.output
                    and self.output.count("ERROR") == 2)
                self.assertTrue("usr/bin/bobcat" in self.output)

                # Test that "-H" works as expected.
                self.pkg_verify("foo -H", exit=1)
                self.assertTrue("PACKAGE" not in self.output and
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

                with open(fpath, "r+") as f:
                        out = ""
                        for l in f:
                                if l.find("zigit") != -1:
                                        nl = l.replace("1234", "4321")
                                        out += nl
                                out += l
                        f.seek(0)
                        f.write(out)

                # Verify should find the extra alias and it should be treated
                # as a warning.
                self.pkg_verify("-v foo")
                self.assertTrue("4321" in self.output and "WARNING" in self.output)

                # Test that warnings are displayed by default.
                self.pkg_verify("foo")
                self.assertTrue("4321" in self.output and "WARNING" in self.output)

                # Verify on system wide should also find the extra alias.
                self.pkg_verify("")
                self.assertTrue("4321" in self.output and "WARNING" in self.output)

        def test_multiple_paths_input(self):
                """Test that when input is multiple paths, results returned are as
                expected."""

                self.pkgsend_bulk(self.rurl, self.bar10)

                self.image_create(self.rurl)
                self.pkg("install foo bar")

                # Test verification of multiple paths in a package.
                # Should not fail since files specified by paths are all intact.
                self.pkg_verify("-v -p /etc/driver_aliases -p /etc/minor_perm \
                    -p /etc/security/extra_privs")

                # Test verification of multiple paths in different packages.
                # Should not fail since files specified by paths are all intact.
                self.pkg_verify("-v -p /etc/driver_aliases -p /etc/bronze1 -p /usr/bin/bobcat")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 2)
                self.pkg_verify("-v -p /usr -p /etc/driver_aliases")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 2)
                self.pkg_verify("-v -p /usr -p /usr/bin")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 1)
                self.pkg_verify("-v -p /usr -p /usr/bin/bobcat_link")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 1)


                # When multiple paths are given to pkg verify, if any of them
                # are not packaged in the image it should report the file not found.
                self.pkg_verify("-v -p /etc/driver_aliases -p nonexist")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 1)
                self.assertTrue("nonexist is not found" in self.output)

                fd = open(os.path.join(self.get_img_path(), "usr", "bin", "bobcat"), "w+")
                fd.write("Bobcats are here")
                fd.close()

                # When verify multilple paths in a package, should output
                # ok for one package, error for the other.
                self.pkg_verify("-v -p /etc/driver_aliases \
                    -p /usr/bin/bobcat", exit=1)
                self.assertTrue("usr/bin/bobcat" in self.output
                    and "etc/driver_aliases" not in self.output)
                self.assertTrue("foo" in self.output)
                self.assertTrue("OK" not in self.output
                    and self.output.count("ERROR") == 2
                    and "Hash" in self.output)

                # Even though the target file is modified, the link and dir
                # verification should pass.
                self.pkg_verify("-v -p /usr -p /usr/bin -p /usr/bin/bobcat_link")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 1)

                # When verifying multiple paths in different packages, should fail
                # the package whose manifest contains the path. Should not
                # fail the other package.
                self.pkg_verify("-v -p /usr/bin/bobcat -p /etc/bronze1", exit=1)
                self.assertTrue("usr/bin/bobcat" in self.output
                    and "etc/bronze1" not in self.output
                    and "foo" in self.output and "bar" in self.output)
                self.assertTrue(self.output.count("OK") == 1
                    and self.output.count("ERROR") == 2
                    and "Hash" in self.output)
                self.pkg_verify("-v -p /usr -p /usr/bin/bobcat", exit=1)
                self.assertTrue("usr/bin/bobcat" in self.output
                    and "foo" in self.output and "bar" in self.output)
                self.assertTrue("OK" in self.output
                    and self.output.count("ERROR") == 2
                    and "Hash" in self.output)

                self.pkg("uninstall foo bar")

        def test_verify_perms_py3(self):
                """Test that verify does adhear to file permission like other
                cmds, and do not exit octal notation"""

                self.pkgsend_bulk(self.rurl, self.bla10)
                self.image_create(self.rurl)
                self.pkg("install bla")
                fpath = os.path.join(self.img_path(),"opt/mybin/test_perm")
                os.chmod(fpath, 0o600)
                self.pkg_verify("bla", exit=1)
                self.assertTrue("ERROR: mode: 0600 should be 0644"
                    in self.output)

                self.pkg("uninstall bla")

        def test_mix_verify_input(self):
                """Test that when input is mix of FMRIs and paths, verbose output
                is correct"""

                self.pkgsend_bulk(self.rurl, self.bar10)
                self.image_create(self.rurl)
                self.pkg("install foo bar")

                # Should verify the package when only FMRI is provided.
                self.pkg_verify("-v foo")
                self.assertTrue("foo" in self.output and "OK" in self.output)

                # Should verify the path when no FMRI is provided.
                self.pkg_verify("-v -p /etc/name_to_major")
                self.assertTrue("foo" in self.output and "OK" in self.output)

                # Should verify only the path when both path and FMRI are
                # provided and an action of the FMRI matches the path.
                self.pkg_verify("-v -p /etc/name_to_major foo")
                self.assertTrue("foo" in self.output
                    and "etc/name_to_major" not in self.output)
                self.assertTrue(self.output.count("OK") == 1)

                # Should verify only the path when the path and more than
                # one FMRIs are provided.
                self.pkg_verify("-v -p /etc/name_to_major foo bar")
                self.assertTrue("foo" in self.output
                    and "bar" not in self.output
                    and "etc/name_to_major" not in self.output)
                self.assertTrue(self.output.count("OK") == 1)
                self.pkg_verify("-v -p /usr foo bar")
                self.assertTrue("bar" in self.output
                    and "foo" not in self.output)
                self.assertTrue(self.output.count("OK") == 1)
                self.pkg_verify("-v -p /usr/bin/bobcat_link foo bar")
                self.assertTrue("bar" in self.output
                    and "foo" not in self.output)
                self.assertTrue(self.output.count("OK") == 1)

                # Should verify the path when both the path and the FMRI are
                # provided but the path is not in the manifest of the package.
                self.pkg_verify("-v -p /etc/name_to_major bar")
                self.assertTrue("foo" not in self.output and
                    "bar" not in self.output and "not found" in self.output)
                self.assertTrue("OK" not in self.output)

                fd = open(os.path.join(self.get_img_path(), "usr", "bin", "bobcat"), "w+")
                fd.write("Bobcats are here")
                fd.close()

                # Should not output error for the package if the modified file
                # is not verified.
                self.pkg_verify("-v -p /etc/bronze1 bar")
                self.assertTrue("bar" in self.output
                    and "OK" in self.output and "ERROR" not in self.output)

                # When the path belongs to the manifest of FMRI, should
                # fail and report error for the path and the FMRI.
                self.pkg_verify("-v -p /usr/bin/bobcat foo bar", exit=1)
                self.assertTrue("foo" in self.output and "bar" not in self.output
                    and "usr/bin/bobcat" in self.output)
                self.assertTrue(self.output.count("ERROR") == 2
                    and "OK" not in self.output)

                # Even though the target file is modified, the link and dir
                # verification should pass.
                self.pkg_verify("-v -p /usr/bin -p /usr/bin/bobcat_link foo bar")
                self.assertTrue("ERROR" not in self.output
                    and self.output.count("OK") == 1)

                self.pkg("uninstall foo bar")

        def test_02_installed(self):
                """When multiple FMRIs are given to pkg verify, if any of them
                aren't installed it should fail."""

                self.image_create(self.rurl)
                self.pkg("install foo")
                self.pkg_verify("foo non-existent", exit=1)
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
                fd = open(os.path.join(self.get_img_path(), "etc", "preserved"), "w+")
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

                self.pkgsend_bulk(self.rurl, [self.sysattr, self.sysattr2])

                # Need to create an image in /var/tmp since sysattrs don't work
                # in tmpfs.
                old_img_path = self.img_path()
                self.set_img_path(tempfile.mkdtemp(prefix="test-suite",
                    dir="/var/tmp"))

                self.image_create(self.rurl)
                self.pkg("install sysattr sysattr2")
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

        def test_verify_invalid_fmri(self):
                """Test invalid fmri triggers correct output."""

                self.image_create(self.rurl)
                self.pkg("install foo")

                self.pkg_verify("foo@invalid", exit=1)
                self.assertTrue("verify" in self.errout and "illegal" in
                    self.errout)

        def test_verify_parsable_output(self):
                """Test parsable output."""

                self.image_create(self.rurl)
                self.pkg("install foo")
                # Test invalid option combo.
                self.pkg_verify("-v --parsable 0 foo", exit=2)
                self.pkg_verify("-H --parsable 0 foo", exit=2)
                # Test invalid option value.
                self.pkg_verify("--parsable 1 foo", exit=2)
                self.pkg_verify("--parsable 0 foo")
                out_json = json.loads(self.output)
                self.assertTrue("pkg://test/foo@1.0,5.11-0:20160229T095441Z"
                    in out_json["item-messages"])
                fmri_entry = out_json["item-messages"][
                    "pkg://test/foo@1.0,5.11-0:20160229T095441Z"]
                self.assertTrue(fmri_entry["messages"][0]["msg_level"]
                    == "info")
                self.assertTrue("file: usr/bin/bobcat" in fmri_entry)

                # Verify should fail if file is missing.
                fpath = os.path.join(self.get_img_path(), "usr", "bin",
                    "bobcat")
                portable.remove(fpath)
                self.pkg_verify("--parsable 0 foo", exit=1)
                out_json = json.loads(self.output)
                self.assertTrue("pkg://test/foo@1.0,5.11-0:20160229T095441Z"
                    in out_json["item-messages"])
                fmri_entry = out_json["item-messages"][
                    "pkg://test/foo@1.0,5.11-0:20160229T095441Z"]
                self.assertTrue(fmri_entry["messages"][0]["msg_type"]
                    == "general")
                self.assertTrue(fmri_entry["messages"][0]["msg_level"]
                    == "error")
                self.assertTrue("file: usr/bin/bobcat" in fmri_entry)
                self.assertTrue(fmri_entry["file: usr/bin/bobcat"][0]["msg_type"]
                    == "general")
                self.assertTrue(fmri_entry["file: usr/bin/bobcat"][0]["msg_level"]
                    == "error")

        def test_unpackaged(self):
                """Test unpackaged option."""

                self.image_create(self.rurl)
                self.pkg("install foo")
                self.pkg_verify("--unpackaged")
                self.assertTrue("ERROR" not in self.output and
                    "WARNING" not in self.output and "Unpackaged" in
                    self.output and "UNPACKAGED" in self.output)
                self.assertTrue("----" not in self.output)
                # Test verbose.
                self.pkg_verify("-v --unpackaged")
                self.assertTrue("----" in self.output)
                self.assertTrue("ERROR" not in self.output and
                    "WARNING" not in self.output and "Unpackaged" in
                    self.output and "UNPACKAGED" in self.output)
                self.assertTrue("ERROR" not in self.output and
                    "WARNING" not in self.output and "bobcat" in
                    self.output and "UNPACKAGED" in self.output)
                # Test omit header.
                self.pkg_verify("--unpackaged -H")
                self.assertTrue("----" not in self.output)
                self.assertTrue("ERROR" not in self.output and
                    "WARNING" not in self.output and "Unpackaged" in
                    self.output and "UNPACKAGED" not in self.output)
                # Test unpackaged only.
                self.pkg_verify("--unpackaged-only -v")
                self.assertTrue("----" not in self.output)
                self.assertTrue("ERROR" not in self.output and
                    "WARNING" not in self.output and "Unpackaged" in
                    self.output and "UNPACKAGED" in self.output)
                self.assertTrue("ERROR" not in self.output and
                    "WARNING" not in self.output and "Unpackaged" in
                    self.output and "bobcat" not in self.output)

                # Test quiet result.
                self.pkg_verify("-q --unpackaged")
                self.assertTrue(not self.output)

                # Test invalid usage.
                self.pkg_verify("--unpackaged-only foo", exit=2)
                self.pkg_verify("--unpackaged --unpackaged-only", exit=2)
                self.pkg_verify("-H --parsable 0 --unpackaged", exit=2)

                # Test --unpackaged with package arguments.
                self.pkg_verify("--unpackaged -v foo")
                self.assertTrue("----" in self.output and "bobcat" in
                    self.output and "UNPACKAGED" in self.output)
                self.pkg_verify("--parsable 0 --unpackaged foo")
                out_json = json.loads(self.output)
                self.assertTrue("pkg://test/foo@1.0,5.11-0:20160229T095441Z"
                    in out_json["item-messages"])
                fmri_entry = out_json["item-messages"][
                    "pkg://test/foo@1.0,5.11-0:20160229T095441Z"]
                self.assertTrue(fmri_entry["messages"][0]["msg_level"]
                    == "info")
                self.assertTrue("file: usr/bin/bobcat" in fmri_entry)

                # Test parsable output for --unpackaged.
                self.pkg_verify("--parsable 0 --unpackaged")
                out_json = json.loads(self.output)
                self.assertTrue("unpackaged" in out_json["item-messages"]
                    and out_json["item-messages"]["unpackaged"])
                out_entry = out_json["item-messages"]["unpackaged"]
                self.assertTrue("dir" in list(out_entry.keys())[0] or "file" in
                    list(out_entry.keys())[0])
                self.assertTrue(out_entry[list(out_entry.keys())[0]][0]["msg_level"]
                    == "info")
                self.assertTrue(out_entry[list(out_entry.keys())[0]][0]["msg_type"]
                    == "unpackaged")
                self.assertTrue("pkg://test/foo@1.0,5.11-0:20160229T095441Z"
                    in out_json["item-messages"])
                fmri_entry = out_json["item-messages"][
                    "pkg://test/foo@1.0,5.11-0:20160229T095441Z"]
                self.assertTrue(fmri_entry["messages"][0]["msg_level"]
                    == "info")
                self.assertTrue("file: usr/bin/bobcat" in fmri_entry)

                # Test parsable output for --unpackaged-only.
                self.pkg_verify("--parsable 0 --unpackaged-only")
                out_json = json.loads(self.output)
                self.assertTrue("unpackaged" in out_json["item-messages"]
                    and out_json["item-messages"]["unpackaged"])
                out_entry = out_json["item-messages"]["unpackaged"]
                self.assertTrue("dir" in list(out_entry.keys())[0] or "file" in
                    list(out_entry.keys())[0])
                self.assertTrue(out_entry[list(out_entry.keys())[0]][0]["msg_level"]
                    == "info")
                self.assertTrue(out_entry[list(out_entry.keys())[0]][0]["msg_type"]
                    == "unpackaged")
                self.assertTrue("pkg://test/foo@1.0,5.11-0:20160229T095441Z"
                    not in out_json["item-messages"])

if __name__ == "__main__":
        unittest.main()
