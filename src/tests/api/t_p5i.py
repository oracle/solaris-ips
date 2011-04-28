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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import difflib
import errno
import unittest
import cStringIO
import os
import pkg.client.api_errors as api_errors
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.p5i as p5i
import shutil
import sys
import tempfile
import urllib
import urlparse

class TestP5I(pkg5unittest.Pkg5TestCase):
        """Class to test the functionality of the pkg.p5i module."""

        #
        # Whitespace at the ends of some lines in the below is
        # significant.
        #
        p5i_bobcat = """{
  "packages": [
    "pkg:/bar@1.0,5.11-0", 
    "baz"
  ], 
  "publishers": [
    {
      "alias": "cat", 
      "name": "bobcat", 
      "packages": [
        "pkg:/foo@1.0,5.11-0"
      ], 
      "repositories": [
        {
          "collection_type": "core", 
          "description": "xkcd.net/325", 
          "legal_uris": [
            "http://xkcd.com/license.html"
          ], 
          "mirrors": [], 
          "name": "source", 
          "origins": [
            "http://localhost:12001/"
          ], 
          "refresh_seconds": 43200, 
          "registration_uri": "", 
          "related_uris": []
        }
      ]
    }
  ], 
  "version": 1
}
"""

        misc_files = [ "libc.so.1" ]

        def setUp(self):
                pkg5unittest.Pkg5TestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def __get_bobcat_pub(self, omit_repo=False):
                # First build a publisher object matching our expected data.
                repo = None
                if not omit_repo:
                        repo = publisher.Repository(description="xkcd.net/325",
                            legal_uris=["http://xkcd.com/license.html"],
                            name="source", origins=["http://localhost:12001/"],
                            refresh_seconds=43200)
                pub = publisher.Publisher("bobcat", alias="cat",
                    repository=repo)

                return pub

        def test_parse_write(self):
                """Verify that the p5i parsing and writing works as expected."""

                # Verify that p5i export and parse works as expected.
                pub = self.__get_bobcat_pub()

                # First, Ensure that PkgFmri and strings are supported properly.
                # Build a simple list of packages.
                fmri_foo = fmri.PkgFmri("pkg:/foo@1.0,5.11-0", None)
                pnames = {
                    "bobcat": [fmri_foo],
                    "": ["pkg:/bar@1.0,5.11-0", "baz"],
                }

                # Dump the p5i data.
                fobj = cStringIO.StringIO()
                p5i.write(fobj, [pub], pkg_names=pnames)

                # Verify that the p5i data ends with a terminating newline.
                fobj.seek(-1, 2)
                self.assertEqual(fobj.read(), "\n")

                # Verify that output matches expected output.
                fobj.seek(0)
                output = fobj.read()
                self.assertPrettyEqual(output, self.p5i_bobcat)

                def validate_results(results):
                        # First result should be 'bobcat' publisher and its
                        # pkg_names.
                        pub, pkg_names = results[0]

                        self.assertEqual(pub.prefix, "bobcat")
                        self.assertEqual(pub.alias, "cat")
                        repo = pub.repository
                        self.assertEqual(repo.name, "source")
                        self.assertEqual(repo.description, "xkcd.net/325")
                        self.assertEqual(repo.legal_uris[0],
                            "http://xkcd.com/license.html")
                        self.assertEqual(repo.refresh_seconds, 43200)
                        self.assertEqual(pkg_names, [str(fmri_foo)])

                        # Last result should be no publisher and a list of
                        # pkg_names.
                        pub, pkg_names = results[1]
                        self.assertEqual(pub, None)
                        self.assertEqual(pkg_names, ["pkg:/bar@1.0,5.11-0",
                            "baz"])

                # Verify that parse returns the expected object and information
                # when provided a fileobj.
                fobj.seek(0)
                validate_results(p5i.parse(fileobj=fobj))

                # Verify that parse returns the expected object and information
                # when provided a file path.
                fobj.seek(0)
                (fd1, path1) = tempfile.mkstemp(dir=self.test_root)
                os.write(fd1, fobj.read())
                os.close(fd1)
                validate_results(p5i.parse(location=path1))

                # Verify that parse returns the expected object and information
                # when provided a file URI.
                location = os.path.abspath(path1)
                location = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(location), "", "", ""))
                validate_results(p5i.parse(location=location))
                fobj.close()
                fobj = None

                # Verify that appropriate exceptions are raised for p5i
                # information that can't be retrieved (doesn't exist).
                nefpath = os.path.join(self.test_root, "non-existent")
                self.assertRaises(api_errors.RetrievalError,
                    p5i.parse, location="file://%s" % nefpath)

                self.assertRaises(api_errors.RetrievalError,
                    p5i.parse, location=nefpath)

                # Verify that appropriate exceptions are raised for invalid
                # p5i information.
                lcpath = os.path.join(self.test_root, "libc.so.1")
                location = os.path.abspath(lcpath)
                location = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(location), "", "", ""))

                # First, test as a file:// URI.
                self.assertRaises(api_errors.InvalidP5IFile, p5i.parse,
                    location=location)

                # Last, test as a pathname.
                self.assertRaises(api_errors.InvalidP5IFile, p5i.parse,
                    location=location)

        def assertPrettyEqual(self, actual, expected):
                if actual == expected:
                        return

                self.assertEqual(expected, actual,
                    "Actual output differed from expected output.\n" +
                    "\n".join(difflib.unified_diff(
                        expected.splitlines(), actual.splitlines(),
                        "Expected output", "Actual output", lineterm="")))
                raise AssertionError(output)

        def test_parse_write_partial(self):
                """Verify that a p5i file with various parts of a publisher's
                repository configuration omitted will still parse and write
                as expected."""

                # First, test the no repository case.
                expected = """{
  "packages": [], 
  "publishers": [
    {
      "alias": "cat", 
      "name": "bobcat", 
      "packages": [], 
      "repositories": []
    }
  ], 
  "version": 1
}
"""

                pub = self.__get_bobcat_pub(omit_repo=True)

                # Dump the p5i data.
                fobj = cStringIO.StringIO()
                p5i.write(fobj, [pub])

                # Verify that output matches expected output.
                fobj.seek(0)
                output = fobj.read()
                self.assertPrettyEqual(output, expected)

                # Now parse the result and verify no repositories are defined.
                pub, pkg_names = p5i.parse(data=output)[0]
                self.assert_(not pub.repository)

                # Next, test the partial repository configuration case.  No
                # origin is provided, but everything else is.
                expected = """{
  "packages": [], 
  "publishers": [
    {
      "alias": "cat", 
      "name": "bobcat", 
      "packages": [], 
      "repositories": [
        {
          "collection_type": "core", 
          "description": "xkcd.net/325", 
          "legal_uris": [
            "http://xkcd.com/license.html"
          ], 
          "mirrors": [], 
          "name": "source", 
          "origins": [], 
          "refresh_seconds": 43200, 
          "registration_uri": "", 
          "related_uris": []
        }
      ]
    }
  ], 
  "version": 1
}
"""
                pub = self.__get_bobcat_pub()

                # Nuke the origin data.
                pub.repository.reset_origins()

                # Dump the p5i data.
                fobj = cStringIO.StringIO()
                p5i.write(fobj, [pub])

                # Verify that output matches expected output.
                fobj.seek(0)
                output = fobj.read()
                self.assertPrettyEqual(output, expected)

                # Now parse the result and verify that there is a repository,
                # but without origins information.
                pub, pkg_names = p5i.parse(data=output)[0]
                self.assertPrettyEqual(pub.repository.origins, [])


if __name__ == "__main__":
        unittest.main()
