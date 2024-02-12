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
# Copyright (c) 2011, 2024, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest
import os

import rapidjson as json


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

    def __get_avoid_set(self):
        """Returns a tuple of (avoid, implicit_avoid, obsolete)
        representing packages being avoided by image configuration or
        due to package constraints (respectively)."""

        fpath = self.get_img_file_path("var/pkg/state/avoid_set")
        with open(fpath) as f:
            version, d = json.load(f)

        avoid = set()
        implicit_avoid = set()
        obsolete = set()
        for stem in d:
            if d[stem] == "avoid":
                avoid.add(stem)
            elif d[stem] == "implicit-avoid":
                implicit_avoid.add(stem)
            elif d[stem] == "obsolete":
                obsolete.add(stem)
        return avoid, implicit_avoid, obsolete

    def __assertAvoids(self, avoid=frozenset(), implicit=frozenset(),
        obsolete=frozenset()):
        aavoid, aimplicit, aobsolete = self.__get_avoid_set()
        self.assertEqualDiff(sorted(avoid), sorted(aavoid),
            msg="avoids")
        self.assertEqualDiff(sorted(implicit), sorted(aimplicit),
            msg="implicit avoids")
        self.assertEqualDiff(sorted(obsolete), sorted(aobsolete),
            msg="obsolete avoids")

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
        self.__assertAvoids()

        # avoid a package
        self.pkg("avoid 'B*'")
        self.pkg("avoid")
        assert " B" in self.output
        assert "Bobcats" in self.output
        self.__assertAvoids(avoid=frozenset(["B", "Bobcats"]))
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
        self.__assertAvoids()

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
        # check to make sure we're avoiding despite
        # forced install of B
        self.__assertAvoids(avoid=frozenset(["A", "B"]))
        # Uninstall of D removes B as well
        self.pkg("uninstall D")
        self.pkg("verify A", exit=1)
        self.pkg("verify D", exit=1)
        self.pkg("verify B", exit=1)
        self.pkg("uninstall '*'")
        self.pkg("unavoid A B")
        self.__assertAvoids()

    def test_group_update(self):
        """Test to make sure avoided packages
        are removed when required dependency
        goes away"""
        self.image_create(self.rurl)
        # examine upgrade behavior
        self.pkg("avoid A B")
        self.__assertAvoids(avoid=frozenset(["A", "B"]))
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
        self.__assertAvoids(avoid=frozenset(["A", "B"]))

    def test_group_reject_1(self):
        """test aspects of reject."""
        self.image_create(self.rurl)
        # make sure install w/ --reject
        # places packages w/ group dependencies
        # on avoid list
        self.pkg("install --reject A F@1.0")
        self.__assertAvoids(avoid=frozenset(["A"]))
        # install A and see it removed from avoid list
        self.pkg("install A")
        self.__assertAvoids()
        self.pkg("verify F@1.0 A")
        # remove A and see it added to avoid list
        self.pkg("uninstall A")
        self.__assertAvoids(avoid=frozenset(["A"]))
        # update F and see A kept out, but B added
        self.pkg("update F@2")
        self.pkg("verify F@2.0 B")
        self.pkg("verify A", exit=1)
        self.__assertAvoids(avoid=frozenset(["A"]))
        self.pkg("update --reject B F@3.0")
        self.__assertAvoids(avoid=frozenset(["A", "B"]))
        self.pkg("verify F@3.0 C")
        self.pkg("verify A", exit=1)
        self.pkg("verify B", exit=1)
        # update everything
        self.pkg("update")
        self.__assertAvoids(avoid=frozenset(["A", "B"]))
        self.pkg("verify F@4.0 C D B")
        self.pkg("verify A", exit=1)
        # check 17264951
        # break something so pkg fix will do some work
        dpath = self.get_img_file_path("etc/breakable")
        os.chmod(dpath, 0o700)
        self.pkg("fix F")
        self.__assertAvoids(avoid=frozenset(["A", "B"]))
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
        self.__assertAvoids(avoid=frozenset(["A", "B"]))

    def test_group_obsolete_ok(self):
        """Make sure we're down w/ obsoletions, and that
        they are automatically placed on the avoid list"""
        self.image_create(self.rurl)
        self.pkg("install I@1.0") # anchor version of G
        self.pkg("install H")
        self.pkg("verify G@1.0 H@1.0 I@1.0")
        self.__assertAvoids()
        # update I; this will force G to an obsolete
        # version.  This should place it on the
        # avoid list
        self.pkg("update I@2.0")
        self.pkg("list G", exit=1)
        self.pkg("verify I@2.0 H@1.0")
        self.__assertAvoids(obsolete=frozenset(["G"]))
        # update I again; this should bring G back
        # as it is no longer obsolete.
        self.pkg("update I@3.0")
        self.pkg("verify I@3.0 G@3.0 H@1.0")
        self.__assertAvoids()

    def test_unavoid(self):
        """Make sure pkg unavoid should always allow installed packages
        that are a target of group dependencies to be unavoided."""

        self.image_create(self.rurl)
        # Avoid package liveroot to put it on the avoid list.
        self.pkg("avoid liveroot")
        self.__assertAvoids(avoid=frozenset(["liveroot"]))

        # A has require dependency on liveroot and B has group
        # dependency on liveroot. Since require dependency 'overpower'
        # avoid state, liveroot is required to be installed.
        self.pkg("--debug simulate_live_root={0} install A B".format(
            self.get_img_path()))
        self.pkg("list")
        assert "liveroot" in self.output

        # Make sure liveroot is still on the avoid list.
        self.__assertAvoids(avoid=frozenset(["liveroot"]))

        # Unable to uninstall A because the package system currently
        # requires the avoided package liveroot to be uninstalled,
        # which requires reboot.
        self.pkg("--debug simulate_live_root={0} uninstall --deny-new-be A".format(
            self.get_img_path()), exit=5)

        # We need to remove liveroot from the avoid list, and pkg unvoid
        # should allow installed packages that are a target of group
        # dependencies to be unavoided.
        self.pkg("unavoid liveroot")
        self.__assertAvoids()

        # Uninstall A should succeed now because liveroot is not on the
        # avoid list.
        self.pkg("--debug simulate_live_root={0} uninstall --deny-new-be A".format(
            self.get_img_path()))

    def test_corrupted_avoid_file(self):
        self.image_create(self.rurl)
        self.pkg("avoid A")
        avoid_set_path = self.get_img_file_path("var/pkg/state/avoid_set")

        # test for empty avoid set file
        with open(avoid_set_path, "w+") as f:
            f.truncate(0)
        self.pkg("avoid B", exit=0)
        self.__assertAvoids(avoid=frozenset(["B"]))

        # test avoid set file having junk values
        with open(avoid_set_path, "w+") as f:
            f.write('Some junk value\n')
        self.pkg("avoid C", exit=0)
        self.__assertAvoids(avoid=frozenset(["C"]))

    def test_group_trim(self):
        """Verify that trimmed group dependencies are placed on the
        correct avoid list."""

        self.image_create(self.rurl)

        exclude_pkgs = \
            """open bar@1.0
                    add depend type=group fmri=foo
                    close
                    open baz@1.0
                    add depend type=exclude fmri=foo
                    close
                    open foo@1.0
                    close"""

        pfmris = self.pkgsend_bulk(self.rurl, exclude_pkgs)

        # Install bar; foo should also be installed.
        self.pkg("install --parsable=0 bar")
        self.assertEqualParsable(self.output,
            add_packages=[pfmris[0], pfmris[2]]
        )
        self.__assertAvoids()

        # Install baz; should fail since foo is installed and it is
        # excluded.
        self.pkg("install --parsable=0 baz", exit=1)
        self.__assertAvoids()

        # Remove foo; foo should be placed on avoid list.
        self.pkg("uninstall --parsable=0 foo")
        self.assertEqualParsable(self.output,
            remove_packages=pfmris[-1:]
        )
        self.__assertAvoids(avoid=frozenset(["foo"]))

        # Remove all packages.
        self.pkg("uninstall --parsable=0 \*")
        self.assertEqualParsable(self.output,
            remove_packages=pfmris[0:1]
        )

        # Foo should still be on the avoid list.
        self.__assertAvoids(avoid=frozenset(["foo"]))
        self.pkg("unavoid foo")

        # Nothing should be installed.
        self.pkg("list", exit=1)

        # Install baz...
        self.pkg("install --parsable=0 baz")
        self.assertEqualParsable(self.output,
            add_packages=pfmris[1:2]
        )
        self.__assertAvoids()

        # ...and then try to install bar; it should fail because the
        # installed 'baz' package has an 'exclude' dependency on foo.
        # Currently, the solver only allows group dependencies to be
        # satisfied if at least one fmri matches the group dependency or
        # if the only matches are obsolete.
        self.pkg("install --parsable=0 bar", exit=1)

    def test_group_any_trim(self):
        """Verify that unused group-any dependencies are placed on the
        implicit avoid list (invisible to administrator) and obsoletion
        behavior."""

        self.image_create(self.rurl)

        pkgs = [
            """open dbx@1.0
                    add depend type=group fmri=dbx-python
                    close""",
            """open dbx-python@1.0
                    add depend type=group-any fmri=python-26 fmri=python-27
                    close""",
            """open python-26@2.6
                    close""",
            """open python-27@2.7
                    close""",
            """open python-26@2.6.1
                    add set name=pkg.obsolete value=true
                    close""",
            """open python-27@2.7.1
                    add set name=pkg.obsolete value=true
                    close"""
        ]
        pfmris = self.pkgsend_bulk(self.rurl, pkgs[0])

        # Install dbx; should succeed even though no dbx-python is
        # available.
        self.pkg("install --parsable=0 dbx")
        self.assertEqualParsable(self.output,
            add_packages=pfmris[0:1],
        )
        self.__assertAvoids(implicit=frozenset(["dbx-python"]))
        self.pkg("verify")

        # Publish dbx-python; pkg verify should still succeed.
        pfmris.extend(self.pkgsend_bulk(self.rurl, pkgs[1]))
        self.__assertAvoids(implicit=frozenset(["dbx-python"]))
        self.pkg("refresh")
        self.pkg("verify")

        # Install dbx-python; should succeed even though no python-*
        # package is available and should be removed from implicit avoid
        # list automatically.
        self.pkg("install --parsable=0 dbx-python")
        self.assertEqualParsable(self.output,
            add_packages=pfmris[1:2],
        )
        self.__assertAvoids(implicit=frozenset(["python-26",
            "python-27"]))
        self.pkg("verify")

        # Remove dbx-python; python-26 and python-27 should be removed
        # from implicit avoid list.
        self.pkg("uninstall --parsable=0 dbx-python")
        self.assertEqualParsable(self.output,
            remove_packages=pfmris[1:2]
        )
        self.__assertAvoids(avoid=frozenset(["dbx-python"]))
        self.pkg("verify")

        # Publish python-26; pkg verify should still
        # succeed.
        pfmris.extend(self.pkgsend_bulk(self.rurl, pkgs[2]))
        self.pkg("refresh")
        self.pkg("verify")

        # Install dbx-python; python-26 should also be installed.
        self.pkg("install --parsable=0 dbx-python")
        self.assertEqualParsable(self.output,
            add_packages=pfmris[1:3],
        )
        self.__assertAvoids(implicit=frozenset(["python-27"]))
        self.pkg("verify")

        # Publish python-27; pkg verify should still succeed.
        pfmris.extend(self.pkgsend_bulk(self.rurl, pkgs[3]))
        self.pkg("refresh")
        self.pkg("verify")

        # pkg update should do nothing since optimal solution is to
        # simply leave python-26 installed and not install python-27.
        self.pkg("update", exit=4)

        # Publish obsolete python-26; pkg verify should still succeed.
        pfmris.extend(self.pkgsend_bulk(self.rurl, pkgs[4]))
        self.pkg("refresh")
        self.pkg("verify")

        # pkg update should remove python-26 and place it on the
        # obsolete list, and install python-27 as we prefer newer
        # versions of packages whenever possible.
        self.pkg("update --parsable=0")
        self.assertEqualParsable(self.output,
            add_packages=pfmris[3:4],
            remove_packages=pfmris[2:3]
        )
        self.__assertAvoids(obsolete=frozenset(["python-26"]))

        # Publish obsolete python-27; pkg verify should still succeed.
        pfmris.extend(self.pkgsend_bulk(self.rurl, pkgs[5]))
        self.pkg("refresh")
        self.pkg("verify")

        # pkg update should remove python-27 and place it on the
        # obsolete list as we prefer newer versions of packages whenever
        # possible.
        self.pkg("update --parsable=0")
        self.assertEqualParsable(self.output,
            remove_packages=pfmris[3:4]
        )
        self.__assertAvoids(implicit=frozenset(["python-26"]),
            obsolete=frozenset(["python-27"]))


if __name__ == "__main__":
    unittest.main()
