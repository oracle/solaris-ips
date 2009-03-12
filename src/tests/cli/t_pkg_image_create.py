#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import os
import shutil
import unittest


class TestPkgImageCreateBasics(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_basic(self):
                """ Create an image, verify it. """

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("verify")

        def test_image_create_bad_opts(self):
                """Test some bad cli options."""

                self.pkg("image-create -@", exit=2)
                self.pkg("image-create --bozo", exit=2)
                self.pkg("image-create", exit=2)

        def test_766(self):
                """Bug 766: image-create without publisher prefix specified."""

                durl = self.dc.get_depot_url()

                pkgsend_data = """
                open foo@0.0
                close
                """
                self.pkgsend_bulk(durl, pkgsend_data)

                self.assertRaises(testutils.UnexpectedExitCodeException,
                    self.image_create, durl, "")

        def test_3588(self):
                """Bug 3588: Make sure we can't create an image where one
                already exists"""
                durl = self.dc.get_depot_url()
                self.pkg("image-create -p mydepot=%s %s/3588_image" % (
                    durl, self.get_img_path()))
                self.pkg("image-create -p mydepot=%s %s/3588_image" %
                                  (durl, self.get_img_path()), exit=1)

        def test_3588_1(self):
                """Bug 3588: Make sure we can create an image where one
                already exists with the -f (force) flag"""
                durl = self.dc.get_depot_url()
                self.pkg("image-create -p mydepot=%s %s/3588_image_1" % (
                    durl, self.get_img_path()))
                self.pkg("image-create -f -p mydepot=%s %s/3588_image_1" %
                         (durl, self.get_img_path()))

        def test_3588_2(self):
                """Bug 3588: Make sure we can't create an image where a  
                non-empty directory exists"""
                durl = self.dc.get_depot_url()
                p = os.path.join(self.get_img_path(), "3588_2_image")
                os.mkdir(p)
                os.system("touch %s/%s" % (p, "somefile"))
                self.pkg("image-create -p mydepot=%s %s" % (durl, p), exit=1)
                self.pkg("image-create -f -p mydepot=%s %s" % (durl, p))

        def test_4_options(self):
                """Verify that all of the options for specifying publisher
                information work as expected for image-create."""

                img_path = os.path.join(self.get_test_prefix(), "test_4_img")
                for opt in ("-a", "-p", "--publisher"):
                        durl = self.dc.get_depot_url()
                        self.pkg("image-create %s mydepot=%s %s" % (opt, durl,
                            img_path))
                        shutil.rmtree(img_path)


class TestImageCreateNoDepot(testutils.CliTestCase):
        persistent_depot = True
        def test_bad_image_create(self):
                """ Create image from non-existent server """

                #
                # Currently port 4 is unassigned by IANA and we
                # Can just hope that it never gets assigned.
                # We choose localhost because, well, we think
                # it will be universally able to be looked up.
                #
                durl = "http://localhost:4"
                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.image_create, durl)

        def test_765(self):
                """Bug 765: malformed publisher URL."""

                durl = "bar=baz"
                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.image_create, durl)

        def test_763a(self):
                """Bug 763, traceback 1: no -p option given to image-create."""

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create foo")

        def test_763c(self):
                """Bug 763, traceback 3: -p given to image-create, but no
                publisher specified."""

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p foo")

        def test_bad_publisher_options(self):
                """More tests that abuse the publisher prefix and URL."""

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p $%^8" + ("=http://%s1" %
                    self.bogus_url))

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p test1=http://$%^8")

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p test1=http://%s1:abcde" %
                    self.bogus_url)

                self.assertRaises(testutils.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p test1=ftp://%s1" %
                    self.bogus_url)


if __name__ == "__main__":
        unittest.main()
