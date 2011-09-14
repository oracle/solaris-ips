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

# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import errno
import unittest


class TestPkgChangeFacet(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg_A = """
        open pkg_A@1.0,5.11-0
        add file tmp/facets_0 mode=0555 owner=root group=bin path=0
        add file tmp/facets_1 mode=0555 owner=root group=bin path=1 facet.locale.fr=True
        add file tmp/facets_2 mode=0555 owner=root group=bin path=2 facet.locale.fr_FR=True
        add file tmp/facets_3 mode=0555 owner=root group=bin path=3 facet.locale.fr_CA=True
        add file tmp/facets_4 mode=0555 owner=root group=bin path=4 facet.locale.fr_CA=True facet.locale.nl_ZA=True
        add file tmp/facets_5 mode=0555 owner=root group=bin path=5 facet.locale.nl=True
        add file tmp/facets_6 mode=0555 owner=root group=bin path=6 facet.locale.nl_NA=True
        add file tmp/facets_7 mode=0555 owner=root group=bin path=7 facet.locale.nl_ZA=True
        add file tmp/facets_8 mode=0555 owner=root group=bin path=8 facet.has/some/slashes=true
        close"""

        misc_files = [
            "tmp/facets_0", "tmp/facets_1", "tmp/facets_2", "tmp/facets_3",
            "tmp/facets_4", "tmp/facets_5", "tmp/facets_6", "tmp/facets_7",
            "tmp/facets_8"
        ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.rurl, self.pkg_A)

        def assert_file_is_there(self, path, negate=False):
                """Verify that the specified path exists. If negate is true,
                then make sure the path doesn't exist"""

                file_path = os.path.join(self.get_img_path(), path)

                try:
                        f = file(file_path)
                except IOError, e:
                        if e.errno == errno.ENOENT and negate:
                                return
                        self.assert_(False, "File %s is not there" % path)
                # file is there
                if negate:
                        self.assert_(False, "File %s is there" % path)
                return

        def test_1(self):
                # create an image w/ locales set
                ic_args = "";
                ic_args += " --facet 'facet.locale*=False' "
                ic_args += " --facet 'facet.locale.fr*=True' "
                ic_args += " --facet 'facet.locale.fr_CA=False' "

                rurl = self.dc.get_repo_url()
                self.pkg_image_create(rurl, additional_args=ic_args)
                self.pkg("facet")
                self.pkg("facet -H 'facet.locale*' | egrep False")
                # install a package and verify

                self.pkg("install --parsable=0 pkg_A")
                self.assertEqualParsable(self.output,
                    add_packages=self.plist)
                self.pkg("verify")
                self.pkg("facet")

                # make sure it delivers it's files as appropriate
                self.assert_file_is_there("0")
                self.assert_file_is_there("1")
                self.assert_file_is_there("2")
                self.assert_file_is_there("3", negate=True)
                self.assert_file_is_there("4", negate=True)
                self.assert_file_is_there("5", negate=True)
                self.assert_file_is_there("6", negate=True)
                self.assert_file_is_there("7", negate=True)

                # change to pick up another file w/ two tags and test the
                # parsable output
                self.pkg("change-facet --parsable=0 facet.locale.nl_ZA=True")
                self.assertEqualParsable(self.output,
                    affect_packages=self.plist,
                    change_facets=[["facet.locale.nl_ZA", True]])
                self.pkg("verify")
                self.pkg("facet")

                self.assert_file_is_there("0")
                self.assert_file_is_there("1")
                self.assert_file_is_there("2")
                self.assert_file_is_there("3", negate=True)
                self.assert_file_is_there("4")
                self.assert_file_is_there("5", negate=True)
                self.assert_file_is_there("6", negate=True)
                self.assert_file_is_there("7")

                # remove all the facets
                self.pkg("change-facet --parsable=0 facet.locale*=None "
                    "'facet.locale.fr*'=None facet.locale.fr_CA=None")
                self.assertEqualParsable(self.output,
                    affect_packages=self.plist,
                    change_facets=[
                        ["facet.locale*", None],
                        ["facet.locale.fr*", None],
                        ["facet.locale.fr_CA", None]
                    ])
                self.pkg("verify")

                for i in range(8):
                        self.assert_file_is_there("%d" % i)

                # zap all the locales
                self.pkg("change-facet -v facet.locale*=False facet.locale.nl_ZA=None")
                self.pkg("verify")
                self.pkg("facet")

                for i in range(8):
                        self.assert_file_is_there("%d" % i, negate=(i != 0))

        def test_removing_facets(self):
                self.image_create()
                # Test that setting an unset, non-existent facet to None works.
                self.pkg("change-facet foo=None", exit=4)

                # Test that setting a non-existent facet to True then removing
                # it works.
                self.pkg("change-facet -v foo=True")
                self.pkg("facet -H")
                self.assertEqual("facet.foo True\n", self.output)
                self.pkg("change-facet --parsable=0 foo=None")
                self.assertEqualParsable(self.output, change_facets=[
                    ["facet.foo", None]])
                self.pkg("facet -H")
                self.assertEqual("", self.output)

                self.pkg("change-facet -v foo=None", exit=4)

        def test_slashed_facets(self):
                rurl = self.dc.get_repo_url()
                self.pkg_image_create(rurl)
                self.pkg("install pkg_A")
                self.pkg("verify")

                self.assert_file_is_there("8")
                self.pkg("change-facet -v facet.has/some/slashes=False")
                self.assert_file_is_there("8", negate=True)
                self.pkg("verify")
                self.pkg("change-facet -v facet.has/some/slashes=True")
                self.assert_file_is_there("8")
                self.pkg("verify")

if __name__ == "__main__":
        unittest.main()
