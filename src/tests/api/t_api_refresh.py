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
# Copyright (c) 2012, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import shutil
import stat
import time
import unittest

import pkg.client.api as api
import pkg.client.publisher as publisher

LIST_ALL = api.ImageInterface.LIST_ALL

class TestApiRefresh(pkg5unittest.ManyDepotTestCase):

        # restart depos for every test.
        persistent_setup = False

        pubs = [
            "test1",
            "test1",
        ]

        pkgs = [
            "foo@1.0,5.11-0",
            "bar@1.0,5.11-0",
            "baz@1.0,5.11-0",
        ]

        pkgs_data = {}
        for i, pkg in enumerate(pkgs):
                pkgs_data[i] = """
                    open {pkg}
                    close""".format(pkg=pkg)

        def setUp(self):
                # we want two publishers with the same name
                pkg5unittest.ManyDepotTestCase.setUp(self, self.pubs)

                self.rurl = []
                self.rurl.append(self.dcs[1].get_repo_url())
                self.rurl.append(self.dcs[2].get_repo_url())

        def test_stale_publisher_catalog(self):
                """Verify that refresh updates the publisher catalog if it's
                older than any of the origin catalogs."""

                # create an image with one publisher (which has two origin)
                origins = [self.rurl[0], self.rurl[1]]
                api_obj = self.image_create(prefix=self.pubs[0],
                    origins=origins)

                # make sure we don't see any packages
                res = api_obj.get_pkg_list(LIST_ALL)
                self.assertEqual(len(list(res)), 0)

                # get the publisher object
                pub = api_obj.get_publishers()[0]

                # note when the publisher catalog was last updated
                ts1 = pub.catalog.last_modified

                # create a copy of the publisher catalog
                statedir = pub.catalog.meta_root
                statedir_backup = statedir + ".backup"
                shutil.copytree(statedir, statedir_backup)

                # force a delay so if the catalog is updated we'll notice.
                time.sleep(1)

                # publish a new package
                self.pkgsend_bulk(self.rurl[0], self.pkgs_data[0])

                # refresh the image catalog
                api_obj.refresh(immediate=True)

                # make sure the publisher catalog was updated.
                pub = api_obj.get_publishers()[0]
                ts2 = pub.catalog.last_modified
                self.assertNotEqual(ts1, ts2)

                # overwrite the current publisher catalog with the old catalog
                shutil.rmtree(statedir)
                shutil.copytree(statedir_backup, statedir)
                api_obj.reset()

                # make sure the publisher catalog is old
                pub = api_obj.get_publishers()[0]
                ts2 = pub.catalog.last_modified
                self.assertEqual(ts1, ts2)

                # refresh the image catalog
                api_obj.refresh(immediate=True)

                # make sure the publisher catalog was updated
                pub = api_obj.get_publishers()[0]
                ts2 = pub.catalog.last_modified
                self.assertNotEqual(ts1, ts2)

        def test_stale_image_catalog(self):
                """Verify that refresh updates the image catalog if it's
                older than any of the publisher catalogs."""

                # create an image with one publisher (which has one origin)
                origins = [self.rurl[0]]
                api_obj = self.image_create(prefix=self.pubs[0],
                    origins=origins)

                # make sure we don't see any packages
                res = api_obj.get_pkg_list(LIST_ALL)
                self.assertEqual(len(list(res)), 0)

                # create a copy of the image catalog
                img_statedir = api_obj._img._statedir
                img_statedir_backup = img_statedir + ".backup"
                shutil.copytree(img_statedir, img_statedir_backup)

                # publish a new package
                self.pkgsend_bulk(self.rurl[0], self.pkgs_data[0])

                # refresh the image catalog
                api_obj.refresh(immediate=True)

                # make sure we see the new package
                res = api_obj.get_pkg_list(LIST_ALL)
                self.assertEqual(len(list(res)), 1)

                # overwrite the current image catalog with the old catalog
                shutil.rmtree(img_statedir)
                shutil.copytree(img_statedir_backup, img_statedir)
                api_obj.reset()

                # refresh the image catalog
                api_obj.refresh(immediate=True)

                # make sure we see don't see the new package
                res = api_obj.get_pkg_list(LIST_ALL)
                self.assertEqual(len(list(res)), 0)

                # trick the image into thinking that an update was interrupted
                pathname = os.path.join(api_obj._img._statedir,
                     "state_updating")
                with open(pathname, "w"):
                        os.chmod(pathname,
                            stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)

                # make sure we see don't see the new package
                res = api_obj.get_pkg_list(LIST_ALL)
                self.assertEqual(len(list(res)), 0)

                # refresh the image catalog
                api_obj.refresh(immediate=True)

                # make sure we see the new package
                res = api_obj.get_pkg_list(LIST_ALL)
                self.assertEqual(len(list(res)), 1)

        def test_no_origins_means_no_image_catalog_updates(self):
                """Make sure we don't update the image catalog
                unnecessarily."""

                # create an image with no publishers
                api_obj = self.image_create()
                repo = publisher.Repository()
                pub = publisher.Publisher(self.pubs[0], repository=repo)
                api_obj.add_publisher(pub)

                # make sure we've created a local catalog for this publisher
                api_obj.refresh(immediate=True)

                # get the image catalog timestamp
                ts1 = api_obj._img.get_last_modified(string=True)

                # force a delay so if the catalog is updated we'll notice.
                time.sleep(1)

                # refresh the image catalog (should be a noop)
                api_obj.refresh(immediate=True)

                # make sure the image catalog wasn't updated
                ts2 = api_obj._img.get_last_modified(string=True)
                self.assertEqual(ts1, ts2)


if __name__ == "__main__":
        unittest.main()
