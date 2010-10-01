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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.portable
import pkg.catalog
import pkg.client.image as image
import shutil
import unittest


class TestPkgImageCreateBasics(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depots once (instead of for every test)
        persistent_setup = True

        def setUp(self):
                # Extra instances of test1 are created so that a valid
                # repository that is different than the actual test1
                # repository can be used.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test1", "test1", "nopubconfig", "test1"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.rurl3 = self.dcs[3].get_repo_url()
                self.rurl4 = self.dcs[4].get_repo_url()
                self.durl5 = self.dcs[5].get_depot_url()
                self.durl6 = self.dcs[6].get_depot_url()

                # The fifth depot is purposefully one with the publisher
                # operation disabled.
                self.dcs[5].set_disable_ops(["publisher/0"])
                self.dcs[5].start()

        def test_basic(self):
                """ Create an image, verify it. """

                self.pkg_image_create(self.rurl1, prefix="test1")
                self.pkg("verify")

        def test_image_create_bad_opts(self):
                """Test some bad cli options."""

                self.pkg("image-create -@", exit=2)
                self.pkg("image-create --bozo", exit=2)
                self.pkg("image-create", exit=2)

                self.pkg("image-create --set-property foo -p test1=%s %s" %
                    (self.rurl1, self.test_root), exit=2)
                self.pkg("image-create --set-property foo=bar --set-property "
                    "foo=baz -p test1=%s %s" % (self.rurl1, self.test_root),
                    exit=2)

        def __add_install_file(self, imgdir, fmri):
                """Take an image path and fmri. Write a file to disk that
                indicates that the package named by the fmri has been
                installed.  Assumes package was installed from a preferred
                publisher."""

                def install_file(fmri):
                        return "%s/pkg/%s/installed" % (imgdir,
                            fmri.get_dir_path())

                f = file(install_file(fmri), "w")
                f.writelines(["VERSION_1\n_PRE_", fmri.publisher])
                f.close()

                fi = file("%s/state/installed/%s" % (imgdir,
                    fmri.get_link_path()), "w")
                fi.close()

        @staticmethod
        def __transform_v1_v0(v1_cat, v0_dest):
                name = os.path.join(v0_dest, "attrs")
                f = open(name, "wb")
                f.write("S "
                    "Last-Modified: %s\n" % v1_cat.last_modified.isoformat())
                f.write("S prefix: CRSV\n")
                f.write("S npkgs: %s\n" % v1_cat.package_version_count)
                f.close()

                name = os.path.join(v0_dest, "catalog")
                f = open(name, "wb")
                # Now write each FMRI in the catalog in the v0 format:
                # V pkg:/SUNWdvdrw@5.21.4.10.8,5.11-0.86:20080426T173208Z
                for pub, stem, ver in v1_cat.tuples():
                        f.write("V pkg:/%s@%s\n" % (stem, ver))
                f.close()

        def test_3588(self):
                """Ensure that image creation works as expected when an image
                already exists."""

                # These tests are interdependent.
                #
                # Bug 3588: Make sure we can't create an image where one
                # already exists
                self.pkg("image-create -p test1=%s %s/3588_image" % (
                    self.rurl1, self.get_img_path()))
                self.pkg("image-create -p test1=%s %s/3588_image" % (
                    self.rurl1, self.get_img_path()), exit=1)

                # Make sure we can create an image where one
                # already exists with the -f (force) flag
                self.pkg("image-create -p test1=%s %s/3588_image_1" % (
                    self.rurl1, self.get_img_path()))
                self.pkg("image-create -f -p test1=%s %s/3588_image_1" %
                         (self.rurl1, self.get_img_path()))

                # Bug 3588: Make sure we can't create an image where a
                # non-empty directory exists
                p = os.path.join(self.get_img_path(), "3588_2_image")
                os.mkdir(p)
                self.cmdline_run("touch %s/%s" % (p, "somefile"),
                    coverage=False)
                self.pkg("image-create -p test1=%s %s" % (self.rurl1, p),
                    exit=1)
                self.pkg("image-create -f -p test1=%s %s" % (self.rurl1, p))

        def __verify_pub_cfg(self, img_path, prefix, pub_cfg):
                """Private helper method to verify publisher configuration."""

                img = image.Image(img_path, should_exist=True)
                pub = img.get_publisher(prefix=prefix)
                for section in pub_cfg:
                        for prop, val in pub_cfg[section].iteritems():
                                if section == "publisher":
                                        pub_val = getattr(pub, prop)
                                else:
                                        pub_val = getattr(
                                            pub.selected_repository, prop)

                                if prop in ("legal_uris", "mirrors", "origins",
                                    "related_uris"):
                                        # The publisher will have these as lists,
                                        # so transform both sets of data first
                                        # for reliable comparison.  Remove any
                                        # trailing slashes so comparison can
                                        # succeed.
                                        if not val:
                                                val = set()
                                        else:
                                                val = set(val.split(","))
                                        new_pub_val = set()
                                        for u in pub_val:
                                                uri = u.uri
                                                if uri.endswith("/"):
                                                        uri = uri[:-1]
                                                new_pub_val.add(uri)
                                        pub_val = new_pub_val
                                self.assertEqual(val, pub_val)

                # Loading an image changed the cwd, so change it back.
                os.chdir(self.test_root)

        def test_4_options(self):
                """Verify that all of the options for specifying publisher
                information work as expected for image-create."""

                img_path = os.path.join(self.test_root, "test_4_img")
                for opt in ("-a", "-p", "--publisher"):
                        self.pkg("image-create %s test1=%s %s" % (opt,
                            self.rurl1, img_path))
                        shutil.rmtree(img_path)

                # Verify that specifying additional mirrors and origins works.
                mirrors = " ".join(
                    "-m %s" % u
                    for u in (self.rurl3, self.rurl4)
                )
                origins = " ".join(
                    "-g %s" % u
                    for u in (self.rurl3, self.rurl4)
                )

                self.pkg("image-create -p test1=%s %s %s %s" % (self.rurl1,
                    mirrors, origins, img_path))

                self.pkg("-R %s publisher | grep origin.*%s" % (img_path,
                    self.rurl1))
                for u in (self.rurl3, self.rurl4):
                        self.pkg("-R %s publisher | grep mirror.*%s" % (
                            img_path, u))
                        self.pkg("-R %s publisher | grep origin.*%s" % (
                            img_path, u))
                shutil.rmtree(img_path, True)

                # Verify that a v0 repo can be configured for a publisher.
                # This should succeed as the API should fallback to manual
                # configuration if auto-configuration isn't available.
                self.pkg("image-create -p test5=%s %s" % (self.durl5, img_path))
                pub_cfg = {
                    "publisher": { "prefix": "test5" },
                    "repository": { "origins": self.durl5 }
                }
                self.__verify_pub_cfg(img_path, "test5", pub_cfg)
                shutil.rmtree(img_path)

                # Verify that -p auto-configuration works as expected for a
                # a v1 repository when no prefix is provided.
                self.pkg("image-create -p %s %s" % (self.rurl1, img_path))
                pub_cfg = {
                    "publisher": { "prefix": "test1" },
                    "repository": { "origins": self.rurl1 }
                }
                self.__verify_pub_cfg(img_path, "test1", pub_cfg)
                shutil.rmtree(img_path)

                # Verify that -p auto-configuration works as expected for a
                # a v1 repository when a prefix is provided.
                self.pkg("image-create -p test1=%s %s" % (self.rurl1, img_path))
                pub_cfg = {
                    "publisher": { "prefix": "test1" },
                    "repository": { "origins": self.rurl1 }
                }
                self.__verify_pub_cfg(img_path, "test1", pub_cfg)
                shutil.rmtree(img_path)

                # Verify that -p auto-configuration works as expected for a
                # a v1 repository with additional origins and mirrors.
                self.pkg("image-create -p test1=%s -g %s -m %s %s" % (
                    self.rurl1, self.rurl3, self.durl5, img_path))
                pub_cfg = {
                    "publisher": { "prefix": "test1" },
                    "repository": {
                        "origins": "%s,%s" % (self.rurl1,self.rurl3),
                        "mirrors": self.durl5,
                    },
                }
                self.__verify_pub_cfg(img_path, "test1", pub_cfg)
                shutil.rmtree(img_path)

        def test_5_bad_values_no_image(self):
                """Verify that an invalid publisher URI or other piece of
                information provided to image-create will not result in an
                empty image being created despite failure.  In addition,
                test that omitting required information will also not result
                in the creation of an image."""

                p = os.path.join(self.get_img_path(), "test_5_image")

                # Invalid URIs should not result in the creation of an image.
                self.pkg("image-create -p test=InvalidURI %s" % p, exit=1)
                self.assertFalse(os.path.exists(p))

                self.pkg("image-create -p InvalidURI %s" % p, exit=1)
                self.assertFalse(os.path.exists(p))

                # Valid URI but without prefix and with --no-refresh; auto-
                # configuration isn't possible in this scenario and so
                # an image should not be created.
                self.pkg("image-create --no-refresh -p %s %s" % (self.rurl1, p),
                    exit=2)
                self.assertFalse(os.path.exists(p))

                # Valid URI but with the wrong publisher prefix should
                # not create an image.
                self.pkg("image-create -p nosuchpub=%s %s" % (self.rurl1, p),
                    exit=1)
                self.assertFalse(os.path.exists(p))

                # Valid URI, without a publisher prefix, but for a repository
                # that doesn't provide publisher configuration should not
                # create an image.
                self.pkg("image-create -p %s %s" % (self.durl5, p),
                    exit=1)
                self.assertFalse(os.path.exists(p))

        def test_6_relative_root_create(self):
                """Verify that an image with a relative path for the root is
                created correctly."""

                pwd = os.getcwd()
                img_path = "test_6_image"
                abs_img_path = os.path.join(self.test_root, img_path)

                # Now verify that the image root isn't duplicated within the
                # specified image root if the specified root doesn't already
                # exist.
                os.chdir(self.test_root)
                self.pkg("image-create -p test1=%s %s" % (self.rurl1,
                    img_path))
                os.chdir(pwd)
                self.assertFalse(os.path.exists(os.path.join(abs_img_path,
                    img_path)))
                shutil.rmtree(abs_img_path)

                # Now verify that the image root isn't duplicated within the
                # specified image root if the specified root already exists.
                os.chdir(self.test_root)
                os.mkdir(img_path)
                self.pkg("image-create -p test1=%s %s" % (self.rurl1,
                    img_path))
                os.chdir(pwd)
                self.assertFalse(os.path.exists(os.path.join(abs_img_path,
                    img_path)))
                shutil.rmtree(abs_img_path)

        def test_7_image_create_no_refresh(self):
                """Verify that image-create --no-refresh works as expected.
                See bug 8777 for related issue."""

                pkgsend_data = """
                open baz@0.0
                close
                """
                self.pkgsend_bulk(self.rurl1, pkgsend_data)

                # First, check to be certain that an image-create --no-refresh
                # will succeed.
                self.pkg_image_create(self.rurl2, prefix="test1",
                    additional_args="--no-refresh")
                self.pkg("list --no-refresh -a | grep baz", exit=1)

                # Finally, verify that using set-publisher will cause a refresh
                # which in turn should cause 'baz' to be listed *if* the origin
                # has changed (setting it to the same value again won't work).
                self.pkg("set-publisher -O %s test1" % self.rurl1)
                self.pkg("list --no-refresh -a | grep baz")

        def test_8_image_upgrade(self):
                """Verify that a version 0 image can be used by a client that
                normally creates version 1 images, and that it will be upgraded
                correctly when a privileged user uses it."""

                # Publish some sample packages (to separate repositories).
                self.pkgsend_bulk(self.rurl1, "open quux@1.0\nclose")
                self.pkgsend_bulk(self.rurl2, "open corge@1.0\nclose")

                # First, create a new image.
                self.pkg_image_create(self.rurl1, prefix="test1")

                # Add the second repository.
                self.pkg("set-publisher -O %s test2" % self.rurl2)

                # Next, install the packages.
                self.pkg("install quux")
                self.pkg("set-publisher -P test2")

                # This is necessary to ensure that packages installed from a
                # previously preferred publisher also get the correct status.
                self.pkg("install corge")
                self.pkg("set-publisher -P test1")

                # Next, disable the second repository's publisher.
                self.pkg("set-publisher -d test2")

                # Next, convert the v1 image to a v0 image.
                img_root = os.path.join(self.get_img_path(), "var", "pkg")
                cat_path = os.path.join(img_root, "catalog")
                pub_path = os.path.join(img_root, "publisher")

                v1_cat = pkg.catalog.Catalog(meta_root=os.path.join(pub_path,
                    "test1", "catalog"), read_only=True)
                v0_cat_path = os.path.join(cat_path, "test1")

                # For conversion, the v0 catalogs need to be generated in
                # the v0 location.
                os.makedirs(v0_cat_path)
                self.__transform_v1_v0(v1_cat, v0_cat_path)

                # The existing installed state has to be converted to v0.
                state_dir = os.path.join(img_root, "state")
                inst_state_dir = os.path.join(state_dir, "installed")
                cat = pkg.catalog.Catalog(meta_root=inst_state_dir)
                for f in cat.fmris():
                        self.__add_install_file(img_root, f)
                cat = None

                # Now dump the new publisher directory, the 'known' state
                # directory, and any catalog files in the 'installed'
                # directory.
                known_state_dir = os.path.join(state_dir, "known")
                for path in (pub_path, known_state_dir):
                        shutil.rmtree(path)

                for fname in sorted(os.listdir(inst_state_dir)):
                        if fname.startswith("catalog"):
                                pkg.portable.remove(os.path.join(inst_state_dir,
                                    fname))

                # Next, verify that the new client can read v0 images as an
                # an unprivileged user.  Each must be done with and without
                # the publisher prefix to test that these are stripped and
                # read properly (because of the publisher preferred prefix).
                self.pkg("publisher -a", su_wrap=True)
                self.pkg("info pkg://test1/quux corge", su_wrap=True)
                self.pkg("info pkg://test2/corge quux", su_wrap=True)

                # Next, verify that the new client can upgrade v0 images to
                # v1 images.
                self.pkg("info quux pkg://test1/quux pkg://test2/corge")

                # Finally, verify that the old structures and state information
                # are gone.
                self.assertFalse(os.path.exists(cat_path))
                self.assertTrue(os.path.exists(pub_path))

                for pl in sorted(os.listdir(inst_state_dir)):
                        # If there any other files but catalog files here, then
                        # the old state information didn't get properly removed.
                        self.assert_(pl.startswith("catalog."))

        def test_9_bad_image_state(self):
                """Verify that the pkg(1) command handles invalid image state
                gracefully."""

                # Publish a package.
                self.pkgsend_bulk(self.rurl1, """
                open foo@0.0
                close
                """)

                # First, create a new image.
                self.pkg_image_create(self.rurl1, prefix="test1")

                # Verify pkg info works as expected.
                self.pkg("info -r foo")

                # Now invalidate the existing image data.
                state_path = self.get_img_api_obj().img._statedir
                kfile_path = os.path.join(state_path, "known", "catalog.attrs")
                ifile_path = os.path.join(state_path, "installed",
                    "catalog.attrs")

                self.pkg("install foo")

                with open(kfile_path, "w") as f:
                        f.write("InvalidCatalogFile")
                        f.flush()

                # Should work since known catalog file was corrupted, not the
                # installed catalog file.
                self.pkg("info foo")

                # These should all fail as they depend on the known catalog
                # file.
                self.pkg("list -a", exit=1)
                self.pkg("install -nv foo", exit=1)
                self.pkg("update -nv", exit=1)
                self.pkg("info -r foo", exit=1)

                with open(ifile_path, "w") as f:
                        f.write("InvalidCatalogFile")
                        f.flush()

                # Should fail since installed catalog file is corrupt.
                self.pkg("info foo", exit=1)
                self.pkg("list", exit=1)

        def test_10_unprivileged(self):
                """Verify that pkg correctly handles permission errors during
                image-create."""

                p = os.path.join(self.test_root, "unpriv_test_10")
                os.mkdir(p)

                self.pkg("image-create -p test1=%s %s/image" % (
                    self.rurl1, p), su_wrap=True, exit=1)


class TestImageCreateNoDepot(pkg5unittest.CliTestCase):
        persistent_setup = True
        def test_bad_image_create(self):
                """ Create image from non-existent server """

                #
                # Currently port 4 is unassigned by IANA and we
                # Can just hope that it never gets assigned.
                # We choose localhost because, well, we think
                # it will be universally able to be looked up.
                #
                durl = "http://localhost:4"
                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg_image_create, durl)

        def test_765(self):
                """Bug 765: malformed publisher URL."""

                durl = "bar=baz"
                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg_image_create, durl)

        def test_763a(self):
                """Bug 763, traceback 1: no -p option given to image-create."""

                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg, "image-create foo")

        def test_763c(self):
                """Bug 763, traceback 3: -p given to image-create, but no
                publisher specified."""

                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p foo")

        def test_bad_publisher_options(self):
                """More tests that abuse the publisher prefix and URL."""

                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p $%^8" + ("=http://%s1" %
                    self.bogus_url))

                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p test1=http://$%^8")

                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p test1=http://%s1:abcde" %
                    self.bogus_url)

                self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
                    self.pkg, "image-create -p test1=ftp://%s1" %
                    self.bogus_url)


if __name__ == "__main__":
        unittest.main()
