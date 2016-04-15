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

# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import errno
import shutil
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
        add file tmp/facets_9 mode=0555 owner=root group=bin path=debug facet.debug.foo=True
        add link path=test target=1
        close"""

        pkg_B1 = """
        open pkg_B@1.0,5.11-0
        close"""
        pkg_B2 = """
        open pkg_B@2.0,5.11-0
        close"""

        # All 'all's must be true AND any 'true's true.
        pkg_top_level = """
        open pkg_top_level@1.0,5.11-0
        add file tmp/facets_0 mode=0555 owner=root group=bin path=top0 facet.devel=all
        add file tmp/facets_1 mode=0555 owner=root group=bin path=top1 facet.doc=all
        add file tmp/facets_2 mode=0555 owner=root group=bin path=top2 facet.devel=all facet.doc=all
        add file tmp/facets_3 mode=0555 owner=root group=bin path=top3 facet.doc=all facet.locale.fr_CA=true
        add file tmp/facets_4 mode=0555 owner=root group=bin path=top4 facet.doc=all facet.locale.fr_CA=true facet.locale.nl_ZA=true
        add file tmp/facets_5 mode=0555 owner=root group=bin path=top5 facet.devel=all facet.doc=all facet.locale.fr_CA=true facet.locale.nl_ZA=true
        add file tmp/facets_6 mode=0555 owner=root group=bin path=top0.debug facet.devel=all facet.debug.top=all
        add file tmp/facets_7 mode=0555 owner=root group=bin path=optional.doc facet.optional.doc=all facet.doc=true
        add file tmp/facets_8 mode=0555 owner=root group=bin path=optional_fr.doc facet.optional.doc=all facet.doc=all facet.locale.fr_CA=true
        close"""

        misc_files = [
            "tmp/facets_0", "tmp/facets_1", "tmp/facets_2", "tmp/facets_3",
            "tmp/facets_4", "tmp/facets_5", "tmp/facets_6", "tmp/facets_7",
            "tmp/facets_8", "tmp/facets_9"
        ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.plist = self.pkgsend_bulk(self.rurl, (self.pkg_A,
                    self.pkg_top_level))
                self.plist_B = self.pkgsend_bulk(self.rurl,
                    [self.pkg_B1, self.pkg_B2])

        def assert_files_exist(self, flist):
                error = ""
                for (path, exist) in flist:
                        file_path = os.path.join(self.get_img_path(), path)
                        try:
                                self.assert_file_is_there(file_path,
                                    negate=not exist)
                        except AssertionError as e:
                                error += "\n{0}".format(e)

                if error:
                        raise AssertionError(error)

        def assert_file_is_there(self, path, negate=False):
                """Verify that the specified path exists. If negate is true,
                then make sure the path doesn't exist"""

                file_path = os.path.join(self.get_img_path(), str(path))

                try:
                        open(file_path).close()
                except IOError as e:
                        if e.errno == errno.ENOENT and negate:
                                return
                        self.assertTrue(False, "File {0} is missing".format(path))
                # file is there
                if negate:
                        self.assertTrue(False, "File {0} should not exist".format(path))
                return

        def test_01_facets(self):
                # create an image w/ locales set
                ic_args = "";
                ic_args += " --facet 'facet.locale*=False' "
                ic_args += " --facet 'facet.locale.fr*=True' "
                ic_args += " --facet 'facet.locale.fr_CA=False' "

                self.pkg_image_create(self.rurl, additional_args=ic_args)
                self.pkg("facet")
                self.pkg("facet -H -F tsv 'facet.locale*' | egrep False")

                # install a package and verify
                alist = [self.plist[0]]
                self.pkg("install --parsable=0 pkg_A")
                self.assertEqualParsable(self.output, add_packages=alist)
                self.pkg("verify")
                self.pkg("facet")

                # make sure it delivers its files as appropriate
                self.assert_file_is_there("0")
                self.assert_file_is_there("1")
                self.assert_file_is_there("2")
                self.assert_file_is_there("3", negate=True)
                self.assert_file_is_there("4", negate=True)
                self.assert_file_is_there("5", negate=True)
                self.assert_file_is_there("6", negate=True)
                self.assert_file_is_there("7", negate=True)
                self.assert_file_is_there("8")
                self.assert_file_is_there("debug", negate=True)

                # Verify that effective value is shown for facets that are
                # always implicity false such as debug / optional.
                self.pkg("facet -H -F tsv debug.top optional.doc")
                self.assertEqual(
                    "facet.debug.top\tFalse\tsystem\n"
                    "facet.optional.doc\tFalse\tsystem\n",
                    self.output
                )

                # notice that a file should not exist according to its facet
                open(os.path.join(self.get_img_path(), "3"), "w").close()
                self.pkg("verify", exit=1)
                os.remove(os.path.join(self.get_img_path(), "3"))

                # verify that a non-existent facet can be set when other facets
                # are in effect
                self.pkg("change-facet -n --parsable=0 wombat=false")
                self.assertEqualParsable(self.output,
                    affect_packages=[],
                    change_facets=[["facet.wombat", False, None, 'local',
                       False, False]])

                # Again, but this time after removing the publisher cache data
                # and as an unprivileged user to verify that cached manifest
                # data doesn't affect operation.
                cache_dir = os.path.join(self.get_img_api_obj().img.imgdir,
                    "cache", "publisher")
                shutil.rmtree(cache_dir)
                self.pkg("change-facet --no-refresh -n --parsable=0 "
                    "wombat=false", su_wrap=True)
                self.assertEqualParsable(self.output,
                    affect_packages=[],
                    change_facets=[["facet.wombat", False, None, 'local',
                        False, False]])

                # Again, but this time after removing the cache directory
                # entirely.
                cache_dir = os.path.join(self.get_img_api_obj().img.imgdir,
                    "cache")
                shutil.rmtree(cache_dir)
                self.pkg("change-facet --no-refresh -n --parsable=0 "
                    "wombat=false", su_wrap=True)
                self.assertEqualParsable(self.output,
                    affect_packages=[],
                    change_facets=[["facet.wombat", False, None, 'local',
                        False, False]])

                # change to pick up another file w/ two tags and test the
                # parsable output
                self.pkg("change-facet --parsable=0 facet.locale.nl_ZA=True")
                self.assertEqualParsable(self.output,
                    affect_packages=alist,
                    change_facets=[["facet.locale.nl_ZA", True, None, 'local',
                        False, False]])
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
                self.assert_file_is_there("8")
                self.assert_file_is_there("debug", negate=True)

                # remove all the facets
                self.pkg("change-facet --parsable=0 facet.locale*=None "
                    "'facet.locale.fr*'=None facet.locale.fr_CA=None")
                self.assertEqualParsable(self.output,
                    affect_packages=alist,
                    change_facets=[
                        ["facet.locale*", None, False, 'local', False, False],
                        ["facet.locale.fr*", None, True, 'local', False,
                            False],
                        ["facet.locale.fr_CA", None, False, 'local', False,
                            False]
                    ])
                self.pkg("verify")

                for i in range(8):
                        self.assert_file_is_there("{0:d}".format(i))

                # zap all the locales
                self.pkg("change-facet -v facet.locale*=False facet.locale.nl_ZA=None")
                self.pkg("verify")
                self.pkg("facet")

                for i in range(8):
                        self.assert_file_is_there("{0:d}".format(i), negate=(i != 0))

                # Verify that effective value is shown for facets that are
                # implicity false due to wildcards whether they're known to the
                # system through packages or not.
                self.pkg("facet -H -F tsv facet.locale.fr facet.locale.nl_ZA")
                self.assertEqual(
                    "facet.locale.fr\tFalse\tlocal\n"
                    "facet.locale.nl_ZA\tFalse\tlocal\n",
                    self.output
                )

                # Verify that an action with multiple facets will be installed
                # if at least one is implicitly true even when the first facet
                # evaluated matches an explicit wildcard facet set to false.

                # This test relies on Python iterating over the action
                # attributes dictionary such that facet.locale.nl_ZA is
                # evaluated first.  (There's no way to influence that and the
                # order seems 100% consistent for now.)
                self.pkg("change-facet --parsable=0 'facet.locale*=None' "
                    "'facet.locale.*=false' facet.locale.fr_CA=true");
                self.assertEqualParsable(self.output,
                    affect_packages=alist,
                    change_facets=[
                        ["facet.locale*", None, False, 'local', False, False],
                        ["facet.locale.*", False, None, 'local', False, False],
                        ["facet.locale.fr_CA", True, None, 'local', False,
                            False]
                    ])
                self.assert_file_is_there("4")

                # This test is merely here so that if the evaluation order is
                # reversed for some reason that expected results are still seen.
                self.pkg("change-facet --parsable=0 'facet.locale.*=None' "
                    "facet.locale.fr_*=false facet.locale.fr_CA=None");
                self.assertEqualParsable(self.output,
                    affect_packages=alist,
                    change_facets=[
                        ["facet.locale.*", None, False, 'local', False, False],
                        ["facet.locale.fr_*", False, None, 'local', False,
                            False],
                        ["facet.locale.fr_CA", None, True, 'local', False,
                            False]
                    ])
                self.assert_file_is_there("4")

        def test_02_removing_facets(self):
                self.image_create(self.rurl)
                # Test that setting an unset, non-existent facet to None works.
                self.pkg("change-facet foo=None", exit=4)

                # Test that setting a non-existent facet to True then removing
                # it works.
                self.pkg("change-facet -v foo=True")
                self.pkg("facet -H -F tsv")
                self.assertEqual("facet.foo\tTrue\tlocal\n", self.output)
                self.pkg("change-facet --parsable=0 foo=None")
                self.assertEqualParsable(self.output, change_facets=[
                    ["facet.foo", None, True, 'local', False, False]])
                self.pkg("facet -H")
                self.assertEqual("", self.output)

                self.pkg("change-facet -v foo=None", exit=4)

                # Test that setting a facet at the same time as removing a facet
                # sees both as changing.

                # First, install faceted package.
                self.pkg("install pkg_A")
                for i in range(9):
                        self.assert_file_is_there(i)

                # Next, set general locale.*=False, but locale.fr=True.
                self.pkg("change-facet 'locale.*=False' 'locale.fr=True'")

                # General 0 file, locale.fr file, and has slashes file should be
                # there.
                for i in (0, 1, 8):
                        self.assert_file_is_there(i)

                # No other locale files should be present.
                for i in (2, 3, 4, 5, 6, 7):
                        self.assert_file_is_there(i, negate=True)

                # Now set wombat=False and unset locale.fr.
                self.pkg("change-facet -vv locale.fr=None wombat=False")
                self.assert_file_is_there(0) # general 0 file exists
                self.assert_file_is_there(1, negate=True) # locale.fr file gone

        def test_03_slashed_facets(self):
                self.pkg_image_create(self.rurl)
                self.pkg("install pkg_A")
                self.pkg("verify")

                self.assert_file_is_there("8")
                self.pkg("change-facet -v facet.has/some/slashes=False")
                self.assert_file_is_there("8", negate=True)
                self.pkg("verify")
                self.pkg("change-facet -v facet.has/some/slashes=True")
                self.assert_file_is_there("8")
                self.pkg("verify")

        def test_04_no_accidental_changes(self):
                """Verify that non-facet related packaging operation don't
                accidentally change facets."""

                rurl = self.dc.get_repo_url()

                # create an image w/ two facets set.
                ic_args = ""
                ic_args += " --facet 'locale.fr=False' "
                ic_args += " --facet 'locale.fr_FR=False' "
                self.pkg_image_create(rurl, additional_args=ic_args)
                self.pkg("install pkg_A")

                # install a random package and make sure we don't accidentally
                # change facets.
                self.pkg("install pkg_B@1.0")
                self.pkg("facet -H -F tsv")
                expected = (
                    "facet.locale.fr\tFalse\tlocal\n"
                    "facet.locale.fr_FR\tFalse\tlocal\n")
                self.assertEqualDiff(expected, self.output)
                for i in [ 0, 3, 4, 5, 6, 7 ]:
                        self.assert_file_is_there(str(i))
                for i in [ 1, 2 ]:
                        self.assert_file_is_there(str(i), negate=True)
                self.pkg("verify")

                # update an image and make sure we don't accidentally change
                # facets.
                self.pkg("update")
                self.pkg("facet -H -F tsv")
                expected = (
                    "facet.locale.fr\tFalse\tlocal\n"
                    "facet.locale.fr_FR\tFalse\tlocal\n")
                self.assertEqualDiff(expected, self.output)
                for i in [ 0, 3, 4, 5, 6, 7 ]:
                        self.assert_file_is_there(str(i))
                for i in [ 1, 2 ]:
                        self.assert_file_is_there(str(i), negate=True)
                self.pkg("verify")

        def test_05_reset_facet(self):
                """Verify that resetting a Facet explicitly set to false
                restores/removes delivered content."""

                # create an image with pkg_A and no facets
                self.pkg_image_create(self.rurl)
                self.pkg("install pkg_A")
                self.pkg("facet -H")
                self.assertEqualDiff("", self.output)
                for i in range(8):
                        self.assert_file_is_there(str(i))
                self.assert_file_is_there("debug", negate=True)
                self.pkg("verify")

                # set a facet on an image with no facets
                self.pkg("change-facet -v locale.fr=False")
                self.pkg("facet -H -F tsv")
                output = self.reduceSpaces(self.output)
                expected = (
                    "facet.locale.fr\tFalse\tlocal\n")
                self.assertEqualDiff(expected, output)
                for i in [ 0, 2, 3, 4, 5, 6, 7 ]:
                        self.assert_file_is_there(str(i))
                for i in [ 1 ]:
                        self.assert_file_is_there(str(i), negate=True)
                self.pkg("verify")

                # set a facet on an image with existing facets
                self.pkg("change-facet -v locale.fr_FR=False")
                self.pkg("facet -H -F tsv")
                expected = (
                    "facet.locale.fr\tFalse\tlocal\n"
                    "facet.locale.fr_FR\tFalse\tlocal\n")
                self.assertEqualDiff(expected, self.output)
                for i in [ 0, 3, 4, 5, 6, 7 ]:
                        self.assert_file_is_there(str(i))
                for i in [ 1, 2 ]:
                        self.assert_file_is_there(str(i), negate=True)
                self.pkg("verify")

                # clear a facet while setting a facet on an image with other
                # facets that aren't being changed
                self.pkg("change-facet -v locale.fr=None locale.nl=False")
                self.pkg("facet -H -F tsv")
                output = self.reduceSpaces(self.output)
                expected = (
                    "facet.locale.fr_FR\tFalse\tlocal\n"
                    "facet.locale.nl\tFalse\tlocal\n")
                self.assertEqualDiff(expected, output)
                for i in [ 0, 1, 3, 4, 6, 7 ]:
                        self.assert_file_is_there(str(i))
                for i in [ 2, 5 ]:
                        self.assert_file_is_there(str(i), negate=True)
                self.pkg("verify")

                # clear a facet on an image with other facets that aren't
                # being changed
                self.pkg("change-facet -v locale.nl=None")
                self.pkg("facet -H -F tsv")
                output = self.reduceSpaces(self.output)
                expected = (
                    "facet.locale.fr_FR\tFalse\tlocal\n")
                self.assertEqualDiff(expected, output)
                for i in [ 0, 1, 3, 4, 5, 6, 7 ]:
                        self.assert_file_is_there(str(i))
                for i in [ 2 ]:
                        self.assert_file_is_there(str(i), negate=True)
                self.pkg("verify")

                # clear the only facet on an image
                self.pkg("change-facet -v locale.fr_FR=None")
                self.pkg("facet -H -F tsv")
                self.assertEqualDiff("", self.output)
                for i in range(8):
                        self.assert_file_is_there(str(i))
                self.pkg("verify")

                # verify debug content removed when debug facet reset
                self.pkg("change-facet -v debug.foo=True")
                self.pkg("facet -H -F tsv")
                output = self.reduceSpaces(self.output)
                expected = (
                    "facet.debug.foo\tTrue\tlocal\n")
                self.assertEqualDiff(expected, output)
                self.assert_file_is_there("debug")

                self.pkg("change-facet -v debug.foo=None")
                self.pkg("facet -H -F tsv")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff("", self.output)
                self.assert_file_is_there("debug", negate=True)

        def test_06_facet_all(self):
                """Verify that the 'all' value for facets is handled as
                expected."""

                self.pkg_image_create(self.rurl)

                # All faceted files except debug/optional should be installed.
                self.pkg("install pkg_top_level")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", False),
                    ("top1", True),
                    ("top2", True),
                    ("top3", True),
                    ("top4", True),
                    ("top5", True),
                    ("optional.doc", False),
                    ("optional_fr.doc", False),
                ))

                # All faceted files should be installed.
                self.pkg("change-facet -v debug.top=true optional.doc=true")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", True),
                    ("top1", True),
                    ("top2", True),
                    ("top3", True),
                    ("top4", True),
                    ("top5", True),
                    ("optional.doc", True),
                    ("optional_fr.doc", True),
                ))

                # Only top0[.debug] should be installed.
                self.pkg('change-facet -v doc=false')
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", True),
                    ("top1", False),
                    ("top2", False),
                    ("top3", False),
                    ("top4", False),
                    ("top5", False),
                    ("optional.doc", False),
                    ("optional_fr.doc", False),
                ))

                # No faceted files should be installed.
                self.pkg('change-facet -v devel=false optional.doc=false')
                self.assert_files_exist((
                    ("top0", False),
                    ("top0.debug", False),
                    ("top1", False),
                    ("top2", False),
                    ("top3", False),
                    ("top4", False),
                    ("top5", False),
                    ("optional.doc", False),
                    ("optional_fr.doc", False),
                ))

                # Only top1, top3, top4, optional.doc, and optional_fr.doc
                # should be installed.
                self.pkg('change-facet -v doc=true optional.doc=true')
                self.assert_files_exist((
                    ("top0", False),
                    ("top0.debug", False),
                    ("top1", True),
                    ("top2", False),
                    ("top3", True),
                    ("top4", True),
                    ("top5", False),
                    ("optional.doc", True),
                    ("optional_fr.doc", True),
                ))

                # All faceted files should be installed.
                self.pkg("change-facet -v devel=true optional.doc=true")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", True),
                    ("top1", True),
                    ("top2", True),
                    ("top3", True),
                    ("top4", True),
                    ("top5", True),
                    ("optional.doc", True),
                    ("optional_fr.doc", True),
                ))

                # Only top0[.debug], top1, top2, top4, top5, and optional.doc
                # should be installed.
                self.pkg("change-facet -v locale.fr_CA=false")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", True),
                    ("top1", True),
                    ("top2", True),
                    ("top3", False),
                    ("top4", True),
                    ("top5", True),
                    ("optional.doc", True),
                    ("optional_fr.doc", False),
                ))

                # Only top0[.debug], top1, top2, and optional.doc should be
                # installed.
                self.pkg("change-facet -v locale.nl_ZA=false")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", True),
                    ("top1", True),
                    ("top2", True),
                    ("top3", False),
                    ("top4", False),
                    ("top5", False),
                    ("optional.doc", True),
                    ("optional_fr.doc", False),
                ))

                # Reset all facets and verify all files except optional/debug
                # are installed.
                self.pkg("change-facet -vvv devel=None doc=None locale.fr_CA=None "
                    "locale.nl_ZA=None optional.doc=None debug.top=None")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", False),
                    ("top1", True),
                    ("top2", True),
                    ("top3", True),
                    ("top4", True),
                    ("top5", True),
                    ("optional.doc", False),
                    ("optional_fr.doc", False),
                ))

                # Set a false wildcard for the 'devel' and 'doc' facets.  No
                # files should be installed.
                self.pkg("change-facet -v 'facet.d*=False' optional.*=true "
                    "debug.*=true")
                self.assert_files_exist((
                    ("top0", False),
                    ("top0.debug", False),
                    ("top1", False),
                    ("top2", False),
                    ("top3", False),
                    ("top4", False),
                    ("top5", False),
                    ("optional.doc", False),
                    ("optional_fr.doc", False),
                ))

                # Set the devel facet True and the debug.top facet true and
                # verify that explicit sets trump wildcard matching.  Only
                # top0[.debug] should be installed.
                self.pkg("change-facet -v devel=True debug.top=True")
                self.assert_files_exist((
                    ("top0", True),
                    ("top0.debug", True),
                    ("top1", False),
                    ("top2", False),
                    ("top3", False),
                    ("top4", False),
                    ("top5", False),
                    ("optional.doc", False),
                    ("optional_fr.doc", False),
                ))


if __name__ == "__main__":
        unittest.main()
