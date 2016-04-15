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

#
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest
import os

class TestPkgAvoid(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkgs = """
            open A@1.0,5.11-0
            add depend type=require fmri=liveroot
            close
            open B@1.0,5.11-0
            add depend type=group fmri=liveroot
            close
            open Bobcats@1.0,5.11-0
            close
            open C@1.0,5.11-0
            add depend type=group fmri=A
            add depend type=group fmri=B
            close
            open D@1.0,5.11-0
            add depend type=require fmri=B
            close
            open E@1.0,5.11-0
            close
            open E@2.0,5.11-0
            add depend type=require fmri=A@1.0
            close
            open E@3.0,5.11-0
            add depend type=require fmri=B@1.0
            close
            open E@4.0,5.11-0
            close
            open F@1.0,5.11-0
            add dir path=etc/breakable mode=0755 owner=root group=bin
            add depend type=group fmri=A@1.0
            close
            open F@2.0,5.11-0
            add dir path=etc/breakable mode=0755 owner=root group=bin
            add depend type=group fmri=A@1.0
            add depend type=group fmri=B@1.0
            close
            open F@3.0,5.11-0
            add dir path=etc/breakable mode=0755 owner=root group=bin
            add depend type=group fmri=A@1.0
            add depend type=group fmri=B@1.0
            add depend type=group fmri=C@1.0
            close
            open F@4.0,5.11-0
            add dir path=etc/breakable mode=0755 owner=root group=bin
            add depend type=group fmri=A@1.0
            add depend type=group fmri=B@1.0
            add depend type=group fmri=C@1.0
            add depend type=group fmri=D@1.0
            close
            open G@1.0,5.11-0
            close
            open G@2.0,5.11-0
            add set name=pkg.obsolete value=true
            close
            open G@3.0,5.11-0
            close
            open H@1.0,5.11-0
            add depend type=group fmri=G
            close
            open I@1.0,5.11-0
            add depend type=incorporate fmri=G@1.0
            close
            open I@2.0,5.11-0
            add depend type=incorporate fmri=G@2.0
            close
            open I@3.0,5.11-0
            add depend type=incorporate fmri=G@3.0
            close
            open liveroot@1.0
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/liveroot path=/etc/liveroot mode=644 owner=root group=sys reboot-needed=true
            close
            """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files("tmp/liveroot")
                self.pkgsend_bulk(self.rurl, self.pkgs)

        def test_group_basics(self):
                """Make sure group dependencies work"""
                self.image_create(self.rurl)
                # make sure that unavoiding a package which isn't avoided
                # doesn't traceback.
                self.pkg("unavoid C", exit=1)

                # make sure group dependency brings in packages
                self.pkg("install C")
                self.pkg("verify A B C")
                self.pkg("uninstall '*'")
                # test that we don't avoid packages when we
                # uninstall group at the same time
                self.pkg("avoid")
                assert self.output == ""

                # avoid a package
                self.pkg("avoid 'B*'")
                self.pkg("avoid")
                assert "B" in self.output
                assert "Bobcats" in self.output
                self.pkg("unavoid Bobcats")

                # and then see if it gets brought in
                self.pkg("install C")
                self.pkg("verify A C")
                self.pkg("list B", exit=1)
                self.pkg("avoid")
                # unavoiding it should fail because there
                # is a group dependency on it...
                self.pkg("unavoid B", exit=1)

                # installing it should work
                self.pkg("install B")
                self.pkg("verify A B C")

                # B should no longer be in avoid list
                self.pkg("avoid")
                assert "B" not in self.output

                # avoiding installed packages should fail
                self.pkg("avoid C", exit=1)
                self.pkg("uninstall '*'")

        def test_group_require(self):
                """Show that require dependencies 'overpower' avoid state"""
                self.image_create(self.rurl)
                # test require dependencies w/ avoid
                self.pkg("avoid A B")
                self.pkg("install C D")
                # D will have forced in B
                self.pkg("verify C D B")
                self.pkg("verify A", exit=1)
                self.pkg("avoid")
                # check to make sure we're avoiding despite
                # forced install of B
                assert "A" in self.output
                assert "B" in self.output
                # Uninstall of D removes B as well
                self.pkg("uninstall D")
                self.pkg("verify A", exit=1)
                self.pkg("verify D", exit=1)
                self.pkg("verify B", exit=1)
                self.pkg("uninstall '*'")
                self.pkg("unavoid A B")

        def test_group_update(self):
                """Test to make sure avoided packages
                are removed when required dependency
                goes away"""
                self.image_create(self.rurl)
                # examine upgrade behavior
                self.pkg("avoid A B")
                self.pkg("install E@1.0")
                self.pkg("verify")
                self.pkg("update E@2.0")
                self.pkg("verify E@2.0 A")
                self.pkg("verify B", exit=1)
                self.pkg("update E@3.0")
                self.pkg("verify E@3.0 B")
                self.pkg("verify A", exit=1)
                self.pkg("update E@4.0")
                self.pkg("verify E@4.0")
                self.pkg("verify A", exit=1)
                self.pkg("verify B", exit=1)
                self.pkg("update E@2.0")
                self.pkg("verify E@2.0")
                self.pkg("uninstall '*'")

        def test_group_reject_1(self):
                """test aspects of reject."""
                self.image_create(self.rurl)
                # make sure install w/ --reject
                # places packages w/ group dependencies
                # on avoid list
                self.pkg("install --reject A F@1.0")
                self.pkg("avoid")
                self.assertTrue("A" in self.output)
                # install A and see it removed from avoid list
                self.pkg("install A")
                self.pkg("avoid")
                self.assertTrue(self.output == "")
                self.pkg("verify F@1.0 A")
                # remove A and see it added to avoid list
                self.pkg("uninstall A")
                self.pkg("avoid")
                self.assertTrue("A" in self.output)
                # update F and see A kept out, but B added
                self.pkg("update F@2")
                self.pkg("verify F@2.0 B")
                self.pkg("verify A", exit=1)
                self.pkg("avoid")
                assert "A" in self.output
                self.pkg("update --reject B F@3.0")
                self.pkg("avoid")
                assert "A" in self.output
                assert "B" in self.output
                self.pkg("verify F@3.0 C")
                self.pkg("verify A", exit=1)
                self.pkg("verify B", exit=1)
                # update everything
                self.pkg("update")
                self.pkg("avoid")
                assert "A" in self.output
                self.pkg("verify F@4.0 C D B")
                self.pkg("verify A", exit=1)
                # check 17264951
                # break something so pkg fix will do some work
                dpath = self.get_img_file_path("etc/breakable")
                os.chmod(dpath, 0o700)
                self.pkg("fix F")
                self.pkg("avoid")
                assert "A" in self.output
                self.pkg("verify")

        def test_group_reject_2(self):
                """Make sure --reject places packages
                on avoid list; insure that multiple
                group dependencies don't overcome
                avoid list, and that require dependencies
                do."""
                self.image_create(self.rurl)
                self.pkg("install F@1.0")
                self.pkg("verify F@1.0 A")
                self.pkg("update --reject B --reject A F@2.0")
                self.pkg("verify F@2.0")
                self.pkg("avoid")
                assert "A" in self.output
                assert "B" in self.output

        def test_group_obsolete_ok(self):
                """Make sure we're down w/ obsoletions, and that
                they are automatically placed on the avoid list"""
                self.image_create(self.rurl)
                self.pkg("install I@1.0") # anchor version of G
                self.pkg("install H")
                self.pkg("verify G@1.0 H@1.0 I@1.0")
                self.pkg("avoid")
                assert self.output == ""
                # update I; this will force G to an obsolete
                # version.  This should place it on the
                # avoid list
                self.pkg("update I@2.0")
                self.pkg("list G", exit=1)
                self.pkg("verify I@2.0 H@1.0")
                self.pkg("avoid")
                assert self.output == ""
                # update I again; this should bring G back
                # as it is no longer obsolete.
                self.pkg("update I@3.0")
                self.pkg("verify I@3.0 G@3.0 H@1.0")
                self.pkg("avoid")
                assert self.output == ""

        def test_unavoid(self):
                """Make sure pkg unavoid should always allow installed packages
                that are a target of group dependencies to be unavoided."""

                self.image_create(self.rurl)
                # Avoid package liveroot to put it on the avoid list.
                self.pkg("avoid liveroot")
                self.pkg("avoid")
                assert "liveroot" in self.output

                # A has require dependency on liveroot and B has group
                # dependency on liveroot. Since require dependency 'overpower'
                # avoid state, liveroot is required to be installed.
                self.pkg("--debug simulate_live_root={0} install A B".format(
                    self.get_img_path()))
                self.pkg("list")
                assert "liveroot" in self.output

                # Make sure liveroot is still on the avoid list.
                self.pkg("avoid")
                assert "liveroot" in self.output

                # Unable to uninstall A because the package system currently
                # requires the avoided package liveroot to be uninstalled,
                # which requires reboot.
                self.pkg("--debug simulate_live_root={0} uninstall --deny-new-be A".format(
                    self.get_img_path()), exit=5)

                # We need to remove liveroot from the avoid list, and pkg unvoid
                # should allow installed packages that are a target of group
                # dependencies to be unavoided.
                self.pkg("unavoid liveroot")
                self.pkg("avoid")
                assert "liveroot" not in self.output

                # Uninstall A should succeed now because liveroot is not on the
                # avoid list.
                self.pkg("--debug simulate_live_root={0} uninstall --deny-new-be A".format(
                    self.get_img_path()))

        def test_corrupted_avoid_file(self):
                self.image_create(self.rurl)
                self.pkg("avoid A")
                avoid_set_path = self.get_img_file_path("var/pkg/state/avoid_set")

                #test for empty avoid set file 
                f = open(avoid_set_path, "w+")
                f.truncate(0)
                f.close()
                self.pkg("avoid B", exit=0)

                #test avoid set file having junk values
                f = open(avoid_set_path, "w+")
                f.write('Some junk value\n')
                f.close()
                self.pkg("avoid C", exit=0)

if __name__ == "__main__":
        unittest.main()
