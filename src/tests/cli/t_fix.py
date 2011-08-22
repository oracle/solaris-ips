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
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.portable as portable
import pkg.misc as misc
import shutil
import time
import unittest


class TestFix(pkg5unittest.SingleDepotTestCase):

        # Don't need to restart depot for every test.
        persistent_setup = True

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

        # All of these purposefully omit dir dependency.
        file10 = """
            open file@1.0,5.11-0
            add file amber1 path=amber1 mode=0600 owner=root group=bin
            close """

        preserve10 = """
            open preserve@1.0,5.11-0
            add file amber1 path=amber1 mode=755 owner=root group=bin preserve=true timestamp="20080731T001051Z"
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

        misc_files = [ "copyright.licensed", "license.licensed", "libc.so.1",
            "license.licensed", "license.licensed.addendum", "amber1", "amber2"]

        misc_files2 = { "tmp/empty": "" }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.make_misc_files(self.misc_files2)
                self.plist = {}
                for p in self.pkgsend_bulk(self.rurl, (self.amber10,
                    self.licensed13, self.dir10, self.file10, self.preserve10,
                    self.preserve11, self.preserve12, self.driver10,
                    self.driver_prep10)):
                        pfmri = fmri.PkgFmri(p, "5.11")
                        pfmri.publisher = None
                        sfmri = pfmri.get_short_fmri().replace("pkg:/", "")
                        self.plist[sfmri] = pfmri

        def test_01_basics(self):
                """Basic fix test: install the amber package, modify one of the
                files, and make sure it gets fixed.  """

                self.image_create(self.rurl)
                self.pkg("install amber@1.0")

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
                self.pkg("set-publisher -P --no-refresh -g %s foo" % self.rurl)
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

        def __do_alter_verify(self, pfmri):
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
                self.pkg("fix %s" % pfmri)

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
                        preserve = a.attrs.get("preserve", None)
                        if preserve == "renamenew":
                                self.assert_(not os.path.exists(fpath + ".new"))
                        elif preserve == "renameold":
                                self.assert_(not os.path.exists(fpath + ".old"))

                        # Verify timestamp (if applicable).
                        ts = a.attrs.get("timestamp", None)
                        if ts:
                                expected = misc.timestamp_to_time(ts)
                                actual = lstat.st_mtime
                                if preserve:
                                        # Timestamp should not match expected
                                        # for preserved files that already
                                        # existed.
                                        self.assertNotEqual(expected, actual)
                                else:
                                        self.assertEqual(expected, actual)

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
                        self.pkg("install %s" % pfmri)
                        self.__do_alter_verify(pfmri)
                        self.pkg("verify %s" % pfmri)
                        self.pkg("uninstall %s" % pfmri)

        def test_05_driver(self):
                """Verify that fixing a name collision for drivers doesn't
                cause a stack trace. Bug 14948"""

                self.image_create(self.rurl)

                self.pkg("install drv-prep")
                self.pkg("install drv")

                fh = open(os.path.join(self.get_img_path(), "etc",
                    "driver_aliases"), "wb")
                # Change the entry from whee to wqee.
                fh.write('wqee "pci8186,4321"\n')
                fh.close()

                self.pkg("fix drv")
                self.pkg("verify")


if __name__ == "__main__":
        unittest.main()
