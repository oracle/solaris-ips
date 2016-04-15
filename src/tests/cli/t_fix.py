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

# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.portable as portable
import pkg.misc as misc
import shutil
import simplejson as json
import tempfile
import time
import unittest


class TestFix(pkg5unittest.SingleDepotTestCase):

        # Don't need to restart depot for every test.
        persistent_setup = True
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        amber10 = """
            open amber@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file amber1 mode=0644 owner=root group=bin path=etc/amber1
            add file amber2 mode=0644 owner=root group=bin path=etc/amber2
            add hardlink path=etc/amber.hardlink target=/etc/amber1
            close """

        licensed13 = """
            open licensed@1.3,5.11-0
            add file libc.so.1 mode=0555 owner=root group=bin path=lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed must-accept=True
            close """

        dir10 = """
            open dir@1.0,5.11-0
            add dir path=etc mode=0755 owner=root group=bin
            close """

        pkg_dupfile = """
            open dupfile@0,5.11-0
            add file tmp/file1 path=dir/pathname mode=0755 owner=root group=bin preserve=renameold overlay=allow
            close
        """
        pkg_duplink = """
            open duplink@0,5.11-0
            add link path=dir/pathname target=dir/other preserve=renameold overlay=true
            close
        """

        # All of these purposefully omit dir dependency.
        file10 = """
            open file@1.0,5.11-0
            add file amber1 path=amber1 mode=0600 owner=root group=bin
            close """

        preserve10 = """
            open preserve@1.0,5.11-0
            add file amber1 path=amber1 mode=755 owner=root group=bin preserve=true timestamp="20080731T001051Z"
            add file amber2 path=amber2 mode=755 owner=root group=bin preserve=true timestamp="20080731T001051Z"
            close """

        preserve11 = """
            open preserve@1.1,5.11-0
            add file amber1 path=amber1 mode=755 owner=root group=bin preserve=renamenew timestamp="20090731T004051Z"
            close """

        preserve12 = """
            open preserve@1.2,5.11-0
            add file amber1 path=amber1 mode=755 owner=root group=bin preserve=renameold timestamp="20100731T014051Z"
            close """

        driver10 = """
            open drv@1.0,5.11-0
            add driver name=whee alias=pci8186,4321
            close """

        driver_prep10 = """
            open drv-prep@1.0,5.11-0
            add dir path=/tmp mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=/var
            add dir mode=0755 owner=root group=root path=/var/run
            add dir mode=0755 owner=root group=root path=/system
            add dir mode=0755 owner=root group=root path=/system/volatile
            add file tmp/empty path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/empty path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/empty path=/etc/driver_classes mode=644 owner=root group=sys
            add file tmp/empty path=/etc/minor_perm mode=644 owner=root group=sys
            add file tmp/empty path=/etc/security/device_policy mode=644 owner=root group=sys
            add file tmp/empty path=/etc/security/extra_privs mode=644 owner=root group=sys
            close """

        sysattr = """
            open sysattr@1.0-0
            add file amber1 mode=0555 owner=root group=bin sysattr=sensitive preserve=true path=amber1 timestamp=20100731T014051Z overlay=allow
            add file amber2 mode=0555 owner=root group=bin sysattr=sensitive path=amber2 timestamp=20100731T014051Z
            close"""

        sysattr_o = """
            open sysattr_overlay@1.0-0
            add file mode=0555 owner=root group=bin sysattr=sensitive preserve=true path=amber1 overlay=true
            close"""

        gss = """
            open gss@1.0-0
            add file mech_1 path=etc/gss/mech owner=root group=sys mode=0644 overlay=allow preserve=renameold
            add file mech_3 path=etc/gss/mech_1 owner=root group=sys mode=0644 overlay=allow preserve=renameold
            close """

        krb = """
            open krb5@1.0-0
            add file mech_2 path=etc/gss/mech owner=root group=sys mode=0644 overlay=true preserve=renameold
            add file mech_4 path=etc/gss/mech_1 owner=root group=sys mode=0644 overlay=true preserve=renameold
            close """

        misc_files = [ "copyright.licensed", "license.licensed", "libc.so.1",
            "license.licensed", "license.licensed.addendum", "amber1", "amber2",
            "tmp/file1"]

        misc_files2 = {
            "tmp/empty": "",
            "mech_1": """kerberos_v5 1.2.840.113554.1.2.2 mech_krb5.so kmech_krb5\n""",
            "mech_2": """\n""",
            "mech_3": """kerberos_v5 1.2.840.113554.1.2.2 mech_krb5.so kmech_krb5\n""",
            "mech_4": """\n"""
        }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)
                self.make_misc_files(self.misc_files)
                self.make_misc_files(self.misc_files2)
                self.plist = {}
                for p in self.pkgsend_bulk(self.rurl, (self.amber10,
                    self.licensed13, self.dir10, self.file10, self.preserve10,
                    self.preserve11, self.preserve12, self.driver10,
                    self.driver_prep10, self.sysattr, self.sysattr_o, self.gss,
                    self.krb, self.pkg_dupfile, self.pkg_duplink)):
                        pfmri = fmri.PkgFmri(p)
                        old_publisher = pfmri.publisher
                        pfmri.publisher = None
                        sfmri = pfmri.get_short_fmri().replace("pkg:/", "")
                        self.plist[sfmri] = pfmri
                        pfmri.publisher = old_publisher

        def test_01_basics(self):
                """Basic fix test: install the amber package, modify one of the
                files, and make sure it gets fixed.  """

                self.image_create(self.rurl)
                self.pkg("install amber@1.0")

                # Test invalid option combo.
                self.pkg("fix -v --parsable 0 foo", exit=2)
                self.pkg("fix -H --parsable 0 foo", exit=2)
                # Test invalid option value.
                self.pkg("fix --parsable 1 foo", exit=2)

                # Test parsable output.
                self.pkg("fix --parsable 0 amber", exit=4)
                out_json = json.loads(self.output)
                item_id = list(out_json["item-messages"].keys())[0]
                self.assertTrue(
                    out_json["item-messages"][item_id]["messages"][0]["msg_level"]
                    == "info")

                # Test unpackaged option.
                self.pkg("fix --unpackaged", exit=4)
                self.pkg("fix --parsable 0 --unpackaged", exit=4)
                out_json = json.loads(self.output)
                subitem_id = list(out_json["item-messages"]["unpackaged"].keys())[0]
                self.assertTrue(
                    out_json["item-messages"]["unpackaged"][subitem_id][0]["msg_level"]
                    == "info")

                index_dir = self.get_img_api_obj().img.index_dir
                index_file = os.path.join(index_dir, "main_dict.ascii.v2")
                orig_mtime = os.stat(index_file).st_mtime
                time.sleep(1)

                victim = "etc/amber2"
                # Initial size
                size1 = self.file_size(victim)

                # Corrupt the file
                self.file_append(victim, "foobar")

                # Make sure the size actually changed
                size2 = self.file_size(victim)
                self.assertNotEqual(size1, size2)

                # Verify that unprivileged users are handled by fix.
                self.pkg("fix amber", exit=1, su_wrap=True)

                self.pkg("fix --unpackaged -nv amber")
                self.assertTrue("----" in self.output and "UNPACKAGED" in
                    self.output)

                # Fix the package
                self.pkg("fix amber")

                # Make sure it's the same size as the original
                size2 = self.file_size(victim)
                self.assertEqual(size1, size2)

                # check that we didn't reindex
                new_mtime = os.stat(index_file).st_mtime
                self.assertEqual(orig_mtime, new_mtime)

                # Verify that removing the publisher of a package that needs
                # fixing results in graceful failure (not a traceback).
                self.file_append(victim, "foobar")
                self.pkg("set-publisher -P --no-refresh -g {0} foo".format(self.rurl))
                self.pkg("unset-publisher test")
                self.pkg("fix", exit=1)

        def test_02_hardlinks(self):
                """Hardlink test: make sure that a file getting fixed gets any
                hardlinks that point to it updated"""

                self.image_create(self.rurl)
                self.pkg("install amber@1.0")

                victim = "etc/amber1"
                victimlink = "etc/amber.hardlink"

                self.file_append(victim, "foobar")
                self.pkg("fix amber")

                # Get the inode of the orig file
                i1 = self.file_inode(victim)
                # Get the inode of the new hardlink
                i2 = self.file_inode(victimlink)

                # Make sure the inode of the link is now different
                self.assertEqual(i1, i2)

        def test_03_license(self):
                """Verify that fix works with licenses that require acceptance
                and/or display."""

                self.image_create(self.rurl)
                self.pkg("install --accept licensed@1.3")

                victim = "lib/libc.so.1"

                # Initial size
                size1 = self.file_size(victim)

                # Corrupt the file
                self.file_append(victim, "foobar")

                # Make sure the size actually changed
                size2 = self.file_size(victim)
                self.assertNotEqual(size1, size2)

                # Verify that the fix will fail if the license file needs fixing
                # since the license action requires acceptance.
                img = self.get_img_api_obj().img
                shutil.rmtree(os.path.join(img.imgdir, "license"))
                self.pkg("fix licensed", exit=6)

                # Verify that when the fix failed, it displayed the license
                # that required display.
                self.pkg("fix licensed | grep 'copyright.licensed'")
                self.pkg("fix licensed | grep -v 'license.licensed'")

                # Verify that fix will display all licenses when it fails,
                # if provided the --licenses option.
                self.pkg("fix --licenses licensed | grep 'license.licensed'")

                # Finally, verify that fix will succeed when a package requires
                # license acceptance if provided the --accept option.
                self.pkg("fix --accept licensed")

                # Make sure it's the same size as the original
                size2 = self.file_size(victim)
                self.assertEqual(size1, size2)

        def __do_alter_verify(self, pfmri, verbose=False, quiet=False, exit=0,
            parsable=False):
                # Alter the owner, group, mode, and timestamp of all files (and
                # directories) to something different than the package declares.
                m = manifest.Manifest()
                m.set_content(self.get_img_manifest(pfmri))
                ctime = time.time() - 1000
                for a in m.gen_actions():
                        if a.name not in ("file", "dir"):
                                # Only want file or dir actions.
                                continue

                        ubin = portable.get_user_by_name("bin", None, False)
                        groot = portable.get_group_by_name("root", None, False)

                        fname = a.attrs["path"]
                        fpath = os.path.join(self.get_img_path(), fname)
                        os.chown(fpath, ubin, groot)
                        os.chmod(fpath, misc.PKG_RO_FILE_MODE)
                        os.utime(fpath, (ctime, ctime))

                # Call pkg fix to fix them.
                fix_cmd = "fix"
                if verbose:
                        fix_cmd += " -v"
                if quiet:
                        fix_cmd += " -q"
                if parsable:
                        fix_cmd += " --parsable=0"

                self.pkg("{0} {1}".format(fix_cmd, pfmri), exit=exit)
                if exit != 0:
                        return exit

                editables = []
                # Now verify that fix actually fixed them.
                for a in m.gen_actions():
                        if a.name not in ("file", "dir"):
                                # Only want file or dir actions.
                                continue

                        # Validate standard attributes.
                        self.validate_fsobj_attrs(a)

                        # Now validate attributes that require special handling.
                        fname = a.attrs["path"]
                        fpath = os.path.join(self.get_img_path(), fname)
                        lstat = os.lstat(fpath)

                        # Verify that preserved files don't get renamed, and
                        # the new ones are not installed if the file wasn't
                        # missing already.
                        preserve = a.attrs.get("preserve")
                        if preserve == "renamenew":
                                self.assertTrue(not os.path.exists(fpath + ".new"))
                        elif preserve == "renameold":
                                self.assertTrue(not os.path.exists(fpath + ".old"))

                        if preserve:
                                editables.append("{0}".format(a.attrs["path"]))

                        # Verify timestamp (if applicable).
                        ts = a.attrs.get("timestamp")
                        if ts:
                                expected = misc.timestamp_to_time(ts)
                                actual = lstat.st_mtime
                                if preserve:
                                        self.assertNotEqual(expected, actual,
                                            "timestamp expected {expected} == "
                                            "actual {actual} for "
                                            "{fname}".format(
                                                expected=expected,
                                                actual=actual, fname=fname))
                                else:
                                        self.assertEqual(expected, actual,
                                            "timestamp expected {expected} != "
                                            "actual {actual} for "
                                            "{fname}".format(
                                                expected=expected,
                                                actual=actual, fname=fname))

                # Verify the parsable output (if applicable).
                if parsable:
                        if editables:
                                self.assertEqualParsable(self.output,
                                    affect_packages=["{0}".format(pfmri)],
                                    change_editables=[["updated", editables]])
                        else:
                                self.assertEqualParsable(self.output,
                                    affect_packages=["{0}".format(pfmri)])

        def test_04_permissions(self):
                """Ensure that files and directories will have their owner,
                group, and modes fixed."""

                self.image_create(self.rurl)

                # Because fix and install operations for directories and
                # files can indirectly interact, each package must be
                # tested separately and then together (by using a package
                # with a mix of files and directories).
                for p in ("dir@1.0-0", "file@1.0-0", "preserve@1.0-0",
                    "preserve@1.1-0", "preserve@1.2-0", "amber@1.0-0"):
                        pfmri = self.plist[p]
                        self.pkg("install {0}".format(pfmri))
                        self.__do_alter_verify(pfmri)
                        self.pkg("verify {0}".format(pfmri))
                        self.pkg("uninstall {0}".format(pfmri))

        def test_05_driver(self):
                """Verify that fixing a name collision for drivers doesn't
                cause a stack trace. Bug 14948"""

                self.image_create(self.rurl)

                self.pkg("install drv-prep")
                self.pkg("install drv")

                fh = open(os.path.join(self.get_img_path(), "etc",
                    "driver_aliases"), "w")
                # Change the entry from whee to wqee.
                fh.write('wqee "pci8186,4321"\n')
                fh.close()

                self.pkg("fix drv")
                self.pkg("verify")

        def __test_offline_fix(self, configure_cb, offline_cb, online_cb):
                """Private helper function for ensuring that offline operation
                is supported for 'pkg fix' when no package data retrieval is
                required."""

                # If only attributes are wrong and no local modification
                # is on the file content, fix doesn't need to download the
                # file data.

                # Test the system attribute.
                # Need to create an image in /var/tmp since sysattrs don't work
                # in tmpfs.
                old_img_path = self.img_path()
                self.set_img_path(tempfile.mkdtemp(prefix="test-suite",
                    dir="/var/tmp"))
                self.image_create(self.durl)
                configure_cb()
                self.pkg("install sysattr")
                self.pkg("verify")
                fpath = os.path.join(self.img_path(), "amber1")

                # Need to get creative here to remove the system attributes
                # since you need the sys_linkdir privilege which we don't have:
                # see run.py:393
                # So we re-create the file with correct owner and mode and the
                # only thing missing are the sysattrs.
                portable.remove(fpath)
                portable.copyfile(os.path.join(self.test_root, "amber1"),
                    fpath)
                os.chmod(fpath, 0o555)
                os.chown(fpath, -1, 2)
                self.pkg("verify", exit=1)
                # Make the repository offline.
                offline_cb()
                # If only attributes on a file are wrong, pkg fix still
                # succeeds even if the repository is offline.
                self.pkg("fix sysattr")
                self.pkg("verify")
                online_cb()
                self.image_destroy()

                # Test other attributes: mode, owner, group and timestamp.
                self.image_create(self.durl)
                configure_cb()
                for p in ("file@1.0-0","preserve@1.0-0", "preserve@1.1-0",
                        "preserve@1.2-0", "amber@1.0-0", "sysattr@1.0-0"):
                        pfmri = self.plist[p]
                        self.pkg("install {0}".format(pfmri))
                        offline_cb()
                        self.__do_alter_verify(pfmri, parsable=True)
                        self.pkg("verify --parsable=0 {0}".format(pfmri))
                        self.pkg("uninstall {0}".format(pfmri))
                        online_cb()

                # If modify the file content locally and its attributes, for the
                # editable file delivered with preserve=true, fix doesn't need to
                # download the file data.
                pfmri = self.plist["preserve@1.0-0"]
                self.pkg("install {0}".format(pfmri))
                self.file_append("amber1", "junk")
                offline_cb()
                self.__do_alter_verify(pfmri, verbose=True)
                self.pkg("uninstall {0}".format(pfmri))
                online_cb()

                # For editable files delivered with preserve=renamenew or
                # preserve=renameold, and non-editable files, fix needs to
                # download the file data.
                for p in ("file@1.0-0", "preserve@1.1-0", "preserve@1.2-0"):
                        pfmri = self.plist[p]
                        self.pkg("install {0}".format(pfmri))
                        self.file_append("amber1", "junk")
                        offline_cb()
                        self.__do_alter_verify(pfmri, verbose=True, exit=1)
                        self.pkg("uninstall {0}".format(pfmri))
                        online_cb()

                # Prepare for next test iteration.
                self.image_destroy()

        def test_06_download(self):
                """Test that pkg fix won't try to download all data for
                files that fail verification when the data is not going
                to be used."""

                # For one of the tests we need a repository with at least one
                # package with the same publisher as the package we're testing
                # with.  This is to trigger the package composition code in
                # pkg(5) which will cause it to record the source each package
                # is available from.
                repodir = os.path.join(self.test_root,
                    "repo_contents_test_06_download")
                self.create_repo(repodir, properties={ "publisher": {
                    "prefix": "test" } })
                self.pkgsend_bulk(repodir, self.amber10)

                # First, test for the simple offline / online case where the
                # publisher repositories are simply unreachable.
                def nop():
                        pass

                self.__test_offline_fix(nop, self.dc.stop, self.dc.start)

                # Next, test for the case where the publisher configuration has
                # been removed entirely (historically, this generated "Unknown
                # Publisher 'foo'" errors).
                def rem_test_pub():
                        self.pkg("unset-publisher test")
                def add_test_pub():
                        self.pkg("set-publisher -p {0}".format(self.durl))

                self.__test_offline_fix(nop, rem_test_pub, add_test_pub)

                # Next, test case for where some packages are from a repository
                # that is no longer configured.
                def configure_cb():
                        self.pkg("set-publisher -p {0}".format(repodir))
                def add_multi_test_pub():
                        add_test_pub()
                        configure_cb()

                self.__test_offline_fix(configure_cb, rem_test_pub,
                    add_multi_test_pub)

        def test_fix_changed_manifest(self):
                """Test that running package fix won't change the manifest of an
                installed package even if it has changed in the repository."""

                self.image_create(self.rurl)
                self.pkg("install file")

                self.pkg("set-property signature-policy require-signatures")
                self.pkg("fix", exit=1)

                # Specify location as filesystem path.
                self.pkgsign_simple(self.dc.get_repodir(), "file")

                self.pkg("fix", exit=1)
                # Run it one more time to ensure that the manifest on disk
                # wasn't changed.
                self.pkg("fix", exit=1)

        def test_fix_output(self):
                """Test that the output and exit code works fine for pkg fix."""

                self.image_create(self.rurl)
                pfmri = self.plist["preserve@1.0-0"]
                self.pkg("install {0}".format(pfmri))
                info = "editable file has been changed"
                # Test that the output is expected when the file has only info
                # level mistakes.
                self.file_append("amber1", "junk")
                self.pkg("fix preserve", exit=4)
                assert info not in self.output
                self.pkg("fix -n preserve", exit=4)
                assert info not in self.output

                self.pkg("fix -v preserve", exit=4)
                assert info in self.output
                self.pkg("fix -nv preserve", exit=4)
                assert info in self.output

                self.pkg("fix -q preserve", exit=4)
                assert(self.output == "")

                # Test that the output is expected when the file has both info
                # and error level mistakes.
                self.__do_alter_verify(pfmri)
                assert info not in self.output
                self.__do_alter_verify(pfmri, verbose=True)
                assert info in self.output
                self.__do_alter_verify(pfmri, quiet=True)
                assert(self.output == "")

        def test_fix_overlay(self):
                """Test that pkg verify / fix should tell the users to look at
                the overlaying package in the error message if fix won't repair
                the overlaid package."""

                file_path = "etc/gss/mech"
                file_path_1 = "etc/gss/mech_1"
                self.image_create(self.rurl)
                pfmri_gss = self.plist["gss@1.0-0"]
                pfmri_krb = self.plist["krb5@1.0-0"]
                pfmri_sysattr = self.plist["sysattr@1.0-0"]
                pfmri_sysattr_o = self.plist["sysattr_overlay@1.0-0"]

                # First, only install the package that has a file with
                # attribute overlay=allow.
                self.pkg("install gss")
                self.file_exists(file_path)
                self.file_remove(file_path)
                self.file_doesnt_exist(file_path)
                # Verify should report an error if the file is missing.
                self.pkg("verify -v gss", exit=1)
                # Fix should be able to repair the file.
                self.pkg("fix -v gss")
                self.file_exists(file_path)
                self.__do_alter_verify(pfmri_gss)

                # Install the overlaying package.
                self.pkg("install krb5")
                self.file_exists(file_path)
                self.file_remove(file_path)
                self.file_doesnt_exist(file_path)

                # Now pkg verify should still report an error on the overlaid
                # package and tell the users to verify the overlaying package.
                self.pkg("verify gss", exit=1)
                self.assertTrue("package: {0}".format(
                    pfmri_krb.get_pkg_stem(anarchy=True)) in self.output)
                # Verify should report an error on the overlaying package.
                self.pkg("verify krb5", exit=1)
                # Fix won't repair the overlaid package but will tell the users
                # to fix the overlaying package in the verbose mode.
                self.pkg("fix gss", exit=4)
                self.pkg("fix -v gss", exit=4)
                self.assertTrue("Could not repair: {0}".format(pfmri_gss) in
                    self.output)
                self.assertTrue("package: {0}".format(
                    pfmri_krb.get_pkg_stem(anarchy=True)) in self.output)
                self.file_doesnt_exist(file_path)

                # Fix should be able to repair the file by fixing the overlaying
                # package.
                self.pkg("fix -v pkg:/krb5")
                self.pkg("verify gss")
                self.file_exists(file_path)

                # Test that multiple overlaid files are missing.
                self.file_remove(file_path)
                self.file_remove(file_path_1)
                self.pkg("verify gss", exit=1)
                # Test that the overlay warning only emits once for each
                # package.
                self.pkg("verify gss | grep 'verify or fix' | wc -l | grep 1")
                self.pkg("fix krb5")

                # Test the owner, group and mode change.
                self.__do_alter_verify(pfmri_gss, verbose=True, exit=4)
                self.assertTrue("Could not repair: {0}".format(pfmri_gss) in
                    self.output)
                self.assertTrue("package: {0}".format(
                    pfmri_krb.get_pkg_stem(anarchy=True)) in self.output)
                self.__do_alter_verify(pfmri_krb, verbose=True)

                # Test that verify / fix on system wide could report / fix the
                # error on the overlaid and overlaying packges.
                self.file_remove(file_path)
                self.pkg("verify", exit=1)
                # Test that verify / fix on all packages should not emit the
                # overlaying warning.
                self.assertTrue("verify or fix" not in self.output)
                self.pkg("fix")
                self.assertTrue("verify or fix" not in self.output)
                self.pkg("verify")
                self.file_exists(file_path)

                # Test different file types install. Since fix will repair the
                # overlaid package in this case, we don't need to tell the users
                # to look at the overlaying package.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfile duplink")
                self.pkg("verify dupfile", exit=1)
                self.pkg("fix dupfile")
                self.pkg("verify dupfile")

                # Test overlaid package that contains system attribute error.
                self.set_img_path(tempfile.mkdtemp(prefix="test-suite",
                    dir="/var/tmp"))
                self.image_create(self.rurl)
                self.pkg("install sysattr")
                fpath = os.path.join(self.img_path(), "amber1")

                # Install the overlaying package.
                self.pkg("install sysattr_overlay")
                portable.remove(fpath)
                portable.copyfile(os.path.join(self.test_root, "amber1"),
                    fpath)
                os.chmod(fpath, 0o555)
                os.chown(fpath, -1, 2)
                self.pkg("verify sysattr", exit=1)
                self.pkg("fix -v sysattr", exit=4)
                self.assertTrue("Could not repair: {0}".format(pfmri_sysattr) in
                    self.output, self.plist)
                self.assertTrue("package: {0}".format(
                    pfmri_sysattr_o.get_pkg_stem(anarchy=True)) in self.output)
                self.pkg("fix sysattr_overlay")
                self.pkg("verify sysattr")
                self.image_destroy()

if __name__ == "__main__":
        unittest.main()
