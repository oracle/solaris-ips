#!/usr/bin/python2.7
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
import simplejson as json
import stat
import time

import pkg.client.api_errors as apx
import pkg.fmri as fmri

class TestPkgFreeze(pkg5unittest.SingleDepotTestCase):
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        baz10 = """
            open baz@1.0,5.11-0
            close """

        pkg410 = """
            open pkg4@1.0,5.11-0
            close """

        obsolete10 = """
            open obso@1.0,5.11-0
            add set name=pkg.obsolete value=true
            close """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.sent_pkgs = self.pkgsend_bulk(self.rurl, [self.foo10,
                    self.foo11, self.baz10, self.bar10, self.pkg410,
                    self.obsolete10])
                self.foo10_name = fmri.PkgFmri(self.sent_pkgs[0]).get_fmri(
                    anarchy=True)
                self.foo11_name = fmri.PkgFmri(self.sent_pkgs[1]).get_fmri(
                    anarchy=True)
                self.bar10_name = fmri.PkgFmri(self.sent_pkgs[3]).get_fmri(
                    anarchy=True)
                self.pkg410_name = fmri.PkgFmri(self.sent_pkgs[4]).get_fmri(
                    anarchy=True)

        def test_bad_input(self):
                """Test bad options to pkg freeze."""

                self.api_obj = self.image_create(self.rurl)

                self.pkg("freeze -c", exit=2)
                self.pkg("freeze -c 'foo'", exit=2)
                self.pkg("freeze pkg://foo", exit=1)
                self.pkg("unfreeze pkg://foo", exit=1)
                self.pkg("freeze foo@1.2,4,4,4", exit=1)
                self.pkg("freeze foo@1#%^", exit=1)

                self.api_obj.reset()
                self._api_install(self.api_obj, ["bar@1.0", "baz@1.0", "pkg4"])
                # Test that if the user gives two arguments, and one's invalid,
                # no packages are frozen.
                self.assertRaises(apx.FreezePkgsException,
                    self.api_obj.freeze_pkgs, ["bar", "foo"])
                self.api_obj.reset()
                self.assertEqualDiff([], self.api_obj.get_frozen_list())
                # Test that printing a FreezePkgsException works.
                self.pkg("freeze foo@1.2 foo@1.3 pkg4@1.2 'z*' 'b*@1.1' foo",
                    exit=1)
                expected = """\

pkg freeze: The following packages were frozen at two different versions by
the patterns provided.  The package stem and the versions it was frozen at are
provided:
	foo	foo@1.2 foo@1.3
The following patterns contained wildcards but matched no
installed packages.
	z*
The following patterns attempted to freeze the listed packages
at a version different from the version at which the packages are installed.
	b*@1.1
		bar
		baz
	pkg4@1.2
The following patterns don't match installed packages and
contain no version information.  Uninstalled packages can only be frozen by
providing a version at which to freeze them.
	foo
"""
                self.assertEqualDiff(expected, self.errout)

        def test_cli_operations(self):
                """Test that the pkg freeze and unfreeze cli handle exceptions
                and provide the correct arguments to the api."""

                self.api_obj = self.image_create(self.rurl)
                self.pkg("freeze")
                # Test that unfreezing a package that isn't frozen gives an
                # exitcode of 4.
                self.pkg("unfreeze foo", exit=4)
                self.pkg("unfreeze '*'", exit=4)

                # This fails because bar isn't installed and no version is
                # provided.
                self.pkg("freeze bar", exit=1)

                self.pkg("freeze foo@1.0")

                # Test that freeze and unfreeze both display the list of frozen
                # packages when no arguments are given.
                self.pkg("freeze -H")
                tmp = self.output.split()
                self.assertEqualDiff("foo", tmp[0])
                self.assertEqualDiff("1.0", tmp[1])
                self.assertTrue("None" in self.output)
                self.pkg("unfreeze -H")
                tmp = self.output.split()
                self.assertEqualDiff("foo", tmp[0])
                self.assertEqualDiff("1.0", tmp[1])
                self.assertTrue("None" in self.output)
                self.api_obj.reset()
                self._api_install(self.api_obj, ["foo"])
                # Test that a frozen package can't be updated.
                self.pkg("update", exit=4)
                # Check that -n with unfreeze works as expected.
                self.pkg("unfreeze -n foo")
                self.pkg("freeze -H")
                tmp = self.output.split()
                self.assertEqualDiff("foo", tmp[0])
                self.assertEqualDiff("1.0", tmp[1])
                self.assertTrue("None" in self.output)
                self.pkg("info foo")
                self.assertTrue("(Frozen)" in self.output)

                # Test that unfreezing a package allows it to move.
                self.pkg("unfreeze foo")
                self.pkg("update")
                # Test that freezing a package at a different version than the
                # installed version fails.
                self.pkg("freeze foo@1.0", exit=1)
                self.api_obj.reset()
                self._api_uninstall(self.api_obj, ["foo"])

                # Test -n
                self.pkg("freeze -n foo@1.0")
                self.pkg("freeze")
                self.assertEqualDiff("", self.output)
                self.api_obj.reset()
                self._api_install(self.api_obj, ["foo@1.0"])

                # Test that the -c option works and that reasons show up in the
                # output when the solver can't produce a solution.  This also
                # tests that wildcarding a package name with a specified version
                # works as expected.
                self.pkg("freeze -c '1.2 is broken' 'f*@1.0'")
                self.pkg("freeze -H")
                tmp = self.output.split()
                self.assertEqualDiff("foo", tmp[0])
                self.assertEqualDiff("1.0", tmp[1])
                self.assertTrue("1.2 is broken" in self.output)

                # Test that the reason a package was frozen is included in the
                # output of a failed install.
                self.pkg("install foo@1.1", exit=1)
                self.assertTrue("1.2 is broken" in self.errout)

                self.pkg("freeze obso@1.0")
                self.pkg("info -r obso")
                self.assertTrue("(Obsolete, Frozen)" in self.output)

        def test_unprived_operation(self):
                """Test that pkg freeze and unfreeze display the frozen packages
                without needing privs, and that they don't stack trace when run
                without privs."""

                self.api_obj = self.image_create(self.rurl)
                self.pkg("freeze", su_wrap=True)
                self.pkg("freeze foo@1.0", su_wrap=True, exit=1)
                self.pkg("unfreeze foo", su_wrap=True, exit=1)
                self.pkg("freeze foo@1.0")
                self.pkg("freeze -H", su_wrap=True)
                tmp = self.output.split()
                self.assertEqualDiff("foo", tmp[0])
                self.assertEqualDiff("1.0", tmp[1])
                self.assertTrue("None" in self.output)
                self.pkg("unfreeze -H", su_wrap=True)
                tmp = self.output.split()
                self.assertEqualDiff("foo", tmp[0])
                self.assertEqualDiff("1.0", tmp[1])
                self.assertTrue("None" in self.output)

                # Test that if the freeze file can't be read, we handle the
                # exception appropriately.
                pth = os.path.join(self.img_path(), "var", "pkg", "state",
                    "frozen_dict")
                mod = stat.S_IMODE(os.stat(pth)[stat.ST_MODE])
                new_mod = mod & ~stat.S_IROTH
                os.chmod(pth, new_mod)
                self.pkg("freeze", exit=1, su_wrap=True)
                self.pkg("unfreeze", exit=1, su_wrap=True)
                os.chmod(pth, mod)

                # Make sure that we can read the file again.
                self.pkg("freeze", su_wrap=True)

                # Test that we don't stack trace if the version is unexpected.
                version, d = json.load(open(pth))
                with open(pth, "w") as fh:
                        json.dump((-1, d), fh)
                self.pkg("freeze", exit=1)
                self.pkg("unfreeze", exit=1)

        def test_timestamp_freezes(self):
                """Test operations involving freezing and relaxing freezes down
                to the timestamp level."""

                self.api_obj = self.image_create(self.rurl)
                existing_foo = self.foo10_name
                # Sleep for one second to ensure this new package has a
                # different timestamp than the old one.
                time.sleep(1)
                new_foo = self.pkgsend_bulk(self.rurl, self.foo10)[0]
                new_foo = fmri.PkgFmri(new_foo).get_fmri(anarchy=True)

                self.api_obj.refresh(full_refresh=True)
                self.api_obj.reset()
                self.api_obj.freeze_pkgs([existing_foo])
                self.api_obj.reset()
                # Test that dispaying a timestamp freeze works.
                self.pkg("freeze")
                # This should fail because new_foo isn't the version frozen.
                self.assertRaises(apx.PlanCreationException, self._api_install,
                    self.api_obj, [new_foo])
                # Check that the output of pkg list is correct in terms of the F
                # column.
                self.pkg("list -Ha {0}".format(new_foo))
                expected = "foo 1.0-0 ---\n"
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))
                self.pkg("list -Ha {0}".format(existing_foo))
                expected = "foo 1.0-0 -f-\n"
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))
                # This should install the original foo@1.0 package.
                self._api_install(self.api_obj, ["foo"])
                # Relax the freeze so it doesn't include the timestamp.
                self.api_obj.freeze_pkgs(["foo@1.0"])
                self.api_obj.reset()
                self.pkg("freeze")

                # Test that pkg list reflects the relaxed freeze.
                self.pkg("list -H {0}".format(existing_foo))
                expected = "foo 1.0-0 if-\n"
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))
                self.pkg("list -Haf {0}".format(new_foo))
                expected = "foo 1.0-0 -f-\n"
                self.assertEqualDiff(expected, self.reduceSpaces(self.output))
                # This should work and take foo to the foo@1.0 with the newer
                # timestamp.
                self.pkg("update {0}".format(new_foo))

                # Test that freezing using just the name freezes the installed
                # package down to the timestamp.  This also tests that freezing
                # the same package with a different version overrides the
                # previous setting.
                self.api_obj.reset()
                self.api_obj.freeze_pkgs(["foo"])
                self.api_obj.reset()
                self.assertEqual(new_foo,
                    str(self.api_obj.get_frozen_list()[0][0]))
                self.api_obj.reset()

                # Test that freezing '*' freezes all installed packages and only
                # installed packages down to timestamp.
                self._api_install(self.api_obj, ["bar", "pkg4"])
                self.api_obj.freeze_pkgs(["*"])
                self.api_obj.reset()
                frzs = self.api_obj.get_frozen_list()
                self.assertEqualDiff(
                    set([new_foo, self.bar10_name, self.pkg410_name]),
                    set([str(s) for s, r, t in frzs]))
                # Test that unfreezeing '*' unfreezes all packages.
                self.api_obj.freeze_pkgs(["*"], unfreeze=True)
                self.api_obj.reset()
                self.assertEqualDiff([], self.api_obj.get_frozen_list())
