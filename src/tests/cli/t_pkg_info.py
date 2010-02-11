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
import pkg.fmri as fmri
import shutil
import unittest

class TestPkgInfoBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add license tmp/copyright1 license=copyright
            close
        """

        badfile10 = """
            open badfile@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=/tmp/baz-file
            close
        """

        baddir10 = """
            open baddir@1.0,5.11-0
            add dir mode=755 owner=root group=bin path=/tmp/baz-dir
            close
        """

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2", "tmp/bronze1",
            "tmp/bronze2", "tmp/copyright1", "tmp/sh", "tmp/baz"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.dc.get_depot_url(),
                    self.badfile10 + self.baddir10 + self.bronze10)

        def test_pkg_info_bad_fmri(self):
                """Test bad frmi's with pkg info."""

		durl = self.dc.get_depot_url()
                pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    close
                """
                self.pkgsend_bulk(durl, pkg1)
		self.image_create(durl)

                self.pkg("info foo@x.y", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.95:20080807T160129", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.95:20080807T1", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.95:", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-0.", exit=1)
                self.pkg("info pkg:/man@0.5.11,5.11-", exit=1)
                self.pkg("info pkg:/man@0.5.11,-", exit=1)
                self.pkg("info pkg:/man@-", exit=1)
                self.pkg("info pkg:/man@", exit=1)

                # Bug 4878
                self.pkg("info -r /usr/bin/stunnel", exit=1)
                self.pkg("info /usr/bin/stunnel", exit=1)

		# bad version
		self.pkg("install jade")
                self.pkg("info pkg:/foo@bar.baz", exit=1)
                self.pkg("info pkg:/foo@bar.baz jade", exit=1)
                self.pkg("info -r pkg:/foo@bar.baz", exit=1)

		# bad time
                self.pkg("info pkg:/foo@0.5.11,5.11-0.91:20080613T999999Z",
                    exit=1)

        def test_info_empty_image(self):
                """local pkg info should fail in an empty image; remote
                should succeed on a match """

                self.image_create(self.dc.get_depot_url())
                self.pkg("info", exit=1)

        def test_info_local_remote(self):
                """pkg: check that info behaves for local and remote cases."""

                pkg1 = """
                    open jade@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video"
                    close
                """

                pkg2 = """
                    open turquoise@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set name=info.classification value=org.opensolaris.category.2008:System/Security/Foo/bar/Baz
                    add set pkg.description="Short desc"
                    close
                """

                pkg3 = """
                    open copper@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=/bin
                    add set pkg.description="This package constrains package versions to those for build 123.  WARNING: Proper system update and correct package selection depend on the presence of this incorporation.  Removing this package will result in an unsupported system."
                    close
                """

                durl = self.dc.get_depot_url()

                self.pkgsend_bulk(durl, pkg1)
                self.pkgsend_bulk(durl, pkg2)
                self.pkgsend_bulk(durl, pkg3)

                self.image_create(durl)

                # Install one package and verify
                self.pkg("install jade")
                self.pkg("verify -v")
                
                # Check local info
                self.pkg("info jade | grep 'State: Installed'")
                self.pkg("info jade | grep '      Category: Applications/Sound and Video'")
                self.pkg("info jade | grep '      Category: Applications/Sound and Video (org.opensolaris.category.2008)'", exit=1)
                self.pkg("info jade | grep 'Description:'", exit=1)
                self.pkg("info turquoise 2>&1 | grep 'no packages matching'")
                self.pkg("info emerald", exit=1)
                self.pkg("info emerald 2>&1 | grep 'no packages matching'")
                self.pkg("info 'j*'")
                self.pkg("info '*a*'")
                self.pkg("info jade", su_wrap=True)

                # Check remote info
                self.pkg("info -r jade | grep 'State: Installed'")
                self.pkg("info -r jade | grep '      Category: Applications/Sound and Video'")
                self.pkg("info -r jade | grep '      Category: Applications/Sound and Video (org.opensolaris.category.2008)'", exit=1)
                self.pkg("info -r turquoise | grep 'State: Not installed'")
                self.pkg("info -r turquoise | grep '      Category: System/Security/Foo/bar/Baz'")
                self.pkg("info -r turquoise | grep '      Category: System/Security/Foo/bar/Baz (org.opensolaris.category.2008)'", exit=1)
                self.pkg("info -r turquoise | grep '   Description: Short desc'")
                self.pkg("info -r turquoise")

                # Now remove the manifest for turquoise and retry the info -r for
                # an unprivileged user.
                mpath = os.path.join(self.get_img_path(), "var", "pkg", "pkg",
                    "turquoise")
                shutil.rmtree(mpath)
                self.assertFalse(os.path.exists(mpath))
                self.pkg("info -r turquoise", su_wrap=True)

                # Verify output.
                lines = self.output.split("\n")
                self.assertEqual(lines[2], "   Description: Short desc")
                self.assertEqual(lines[3],
                    "      Category: System/Security/Foo/bar/Baz")
                self.pkg("info -r copper")
                lines = self.output.split("\n")
                self.assertEqual(lines[2],
                   "   Description: This package constrains package versions to those for build 123.")

                self.assertEqual(lines[3], "                WARNING: Proper system update and correct package selection")
                self.assertEqual(lines[4], "                depend on the presence of this incorporation.  Removing this")
                self.assertEqual(lines[5], "                package will result in an unsupported system.")
                self.assertEqual(lines[6], "         State: Not installed")
                self.pkg("info -r emerald", exit=1)
                self.pkg("info -r emerald 2>&1 | grep 'no packages matching'")

        def test_bug_2274(self):
                """Verify that a failure to retrieve license information, for
                one or more packages specified, will result in an exit code of
                1 and a printed message."""

                pkg1 = """
                    open silver@1.0,5.11-0
                    close
                """

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, pkg1)
                self.image_create(durl)
                self.pkg("info --license -r bronze")
                self.pkg("info --license -r silver", exit=1)
                self.pkg("info --license -r bronze silver", exit=1)
                self.pkg("info --license -r silver 2>&1 | grep 'no license information'")

                self.pkg("install bronze")
                self.pkg("install silver")

                self.pkg("info --license bronze")
                self.pkg("info --license silver", exit=1)
                self.pkg("info --license bronze silver", exit=1)
                self.pkg("info --license silver 2>&1 | grep 'no license information'")

        def test_info_bad_packages(self):
                """Verify that pkg info handles packages with invalid
                metadata."""

                durl = self.dc.get_depot_url()
                self.image_create(durl)

                # Verify that no packages are installed.
                self.pkg("list", exit=1)
                plist = self.plist[:2]

                # This should succeed and cause the manifests to be cached.
                self.pkg("info -r %s" % " ".join(p for p in plist))

                # Now attempt to corrupt the client's copy of the manifest by
                # adding malformed actions.
                for p in plist:
                        self.debug("Testing package %s ..." % p)
                        pfmri = fmri.PkgFmri(p)
                        mdata = self.get_img_manifest(pfmri)
                        if mdata.find("dir") != -1:
                                src_mode = "mode=755"
                        else:
                                src_mode = "mode=644"

                        for bad_act in (
                            'set name=description value="" \" my desc \" ""',
                            "set name=com.sun.service.escalations value="):
                                self.debug("Testing with bad action "
                                    "'%s'." % bad_act)
                                bad_mdata = mdata + "%s\n" % bad_act
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("info -r %s" % pfmri.pkg_name, exit=1)


if __name__ == "__main__":
        unittest.main()
