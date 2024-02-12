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
# Copyright (c) 2008, 2024, Oracle and/or its affiliates.
#

from . import testutils
if __name__ == "__main__":
    testutils.setup_environment("../../../proto")
import pkg5unittest

import hashlib
import os
import pkg.portable
import pkg.catalog
import pkg.client.image as image
import pkg.config as cfg
import pkg.misc as misc
import shutil
import unittest


class TestPkgImageCreateBasics(pkg5unittest.ManyDepotTestCase):
    # Only start/stop the depots once (instead of for every test)
    persistent_setup = True
    # Tests in this suite use the read only data directory.
    need_ro_data = True

    def setUp(self):
        # Extra instances of test1 are created so that a valid
        # repository that is different than the actual test1
        # repository can be used.
        pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
            "test1", "test1", "nopubconfig"])

        self.rurl1 = self.dcs[1].get_repo_url()
        self.rurl2 = self.dcs[2].get_repo_url()
        self.rurl3 = self.dcs[3].get_repo_url()
        self.rurl4 = self.dcs[4].get_repo_url()
        self.durl5 = self.dcs[5].get_depot_url()

        self.rpath1 = self.dcs[1].get_repodir()
        self.rpath3 = self.dcs[3].get_repodir()
        self.rpath4 = self.dcs[4].get_repodir()

        # The fifth depot is purposefully one with the publisher
        # operation disabled.
        self.dcs[5].set_disable_ops(["publisher/0", "publisher/1"])
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

        self.pkg("image-create --facet foo=NONE -p test1={0} {1}".format(
            self.rurl1, self.test_root), exit=2)
        self.pkg("image-create --facet foo= -p test1={0} {1}".format(
            self.rurl1, self.test_root), exit=2)
        self.pkg("image-create --facet foo -p test1={0} {1}".format(
            self.rurl1, self.test_root), exit=2)

        self.pkg("image-create --set-property foo -p test1={0} {1}".format(
            self.rurl1, self.test_root), exit=2)
        self.pkg("image-create --set-property foo=bar --set-property "
            "foo=baz -p test1={0} {1}".format(self.rurl1, self.test_root),
            exit=2)
        self.pkg("image-create -g {0} {1}".format(self.rurl1, self.test_root),
            exit=2)
        self.pkg("image-create -m {0} {1}".format(self.rurl1, self.test_root),
            exit=2)
        self.pkg("image-create -g {0} -m {1} {2}".format(self.rurl1,
            self.rurl1, self.test_root), exit=2)

    def __add_install_file(self, imgdir, fmri):
        """Take an image path and fmri. Write a file to disk that
        indicates that the package named by the fmri has been
        installed.  Assumes package was installed from a preferred
        publisher."""

        def install_file(fmri):
            return "{0}/pkg/{1}/installed".format(imgdir,
                fmri.get_dir_path())

        f = open(install_file(fmri), "w")
        f.writelines(["VERSION_1\n_PRE_", fmri.publisher])
        f.close()

        fi = open("{0}/state/installed/{1}".format(imgdir,
            fmri.get_link_path()), "w")
        fi.close()

    def test_force(self):
        """Ensure that image creation works as expected when an image
        already exists."""

        # These tests are interdependent.
        #
        # Bug 3588: Make sure we can't create an image where one
        # already exists
        self.pkg("image-create -p test1={0} {1}/3588_image".format(
            self.rurl1, self.get_img_path()))
        self.pkg("image-create -p test1={0} {1}/3588_image".format(
            self.rurl1, self.get_img_path()), exit=1)

        # Make sure we can create an image where one
        # already exists with the -f (force) flag
        self.pkg("image-create -p test1={0} {1}/3588_image_1".format(
            self.rurl1, self.get_img_path()))
        self.pkg("image-create -f -p test1={0} {1}/3588_image_1".format(
                 self.rurl1, self.get_img_path()))

        # Bug 3588: Make sure we can't create an image where a
        # non-empty directory exists
        p = os.path.join(self.get_img_path(), "3588_2_image")
        os.mkdir(p)
        self.cmdline_run("touch {0}/{1}".format(p, "somefile"),
            coverage=False)
        self.pkg("image-create -p test1={0} {1}".format(self.rurl1, p),
            exit=1)
        self.pkg("image-create -f -p test1={0} {1}".format(self.rurl1, p))

        # Bug 17680: Ensure ssl directory is preserved if it
        # already exists when creating an image where one
        # might already exist with the -f (force) flag.
        shutil.rmtree(self.get_img_path())
        self.pkg("image-create -p test1={0} {1}".format(self.rurl1,
            self.get_img_path()))

        img = self.get_img_api_obj().img
        cert_path = os.path.join(img.imgdir, "ssl", "cert.file")
        misc.makedirs(os.path.dirname(cert_path))
        open(cert_path, "wb").close()
        assert os.path.exists(cert_path)
        self.pkg("image-create -f -p test1={0} {1}".format(self.rurl1,
            self.get_img_path()))
        assert os.path.exists(cert_path)

    def __verify_pub_cfg(self, img_path, prefix, pub_cfg):
        """Private helper method to verify publisher configuration."""

        # pretend like the Image object is being allocated from
        # a pkg command run from within the target image.
        cmdpath = os.path.join(self.get_img_path(), "pkg")

        img = image.Image(img_path, should_exist=True,
            user_provided_dir=True, cmdpath=cmdpath)
        pub = img.get_publisher(prefix=prefix)
        for section in pub_cfg:
            for prop, val in pub_cfg[section].items():
                if section == "publisher":
                    pub_val = getattr(pub, prop)
                else:
                    pub_val = getattr(
                        pub.repository, prop)

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
        for opt in ("-p", "--publisher"):
            self.pkg("image-create {0} test1={1} {2}".format(opt,
                self.rurl1, img_path))
            shutil.rmtree(img_path)

        # Verify that specifying additional mirrors and origins works.
        mirrors = " ".join(
            "-m {0}".format(u)
            for u in (self.rurl3, self.rurl4)
        )
        origins = " ".join(
            "-g {0}".format(u)
            for u in (self.rurl3, self.rurl4)
        )

        self.pkg("image-create -p test1={0} {1} {2} {3}".format(self.rurl1,
            mirrors, origins, img_path))

        self.pkg("-R {0} publisher | grep origin.*{1}".format(img_path,
            self.rurl1))
        for u in (self.rurl3, self.rurl4):
            self.pkg("-R {0} publisher | grep mirror.*{1}".format(
                img_path, u))
            self.pkg("-R {0} publisher | grep origin.*{1}".format(
                img_path, u))
        shutil.rmtree(img_path, True)

        # Verify that specifying --no-refresh when use-system-repo
        # is set to true works.
        saved_sysrepo_env = os.environ.get("PKG_SYSREPO_URL")
        os.environ["PKG_SYSREPO_URL"] = "http://localhost:1"
        self.pkg("image-create --no-refresh --set-property \
                    use-system-repo=true {0}".format(img_path))
        shutil.rmtree(img_path)
        if saved_sysrepo_env:
            os.environ["PKG_SYSREPO_URL"] = saved_sysrepo_env

        # Verify that simple paths to file repositories can be used
        # (not just file:// URIs).
        mirrors = " ".join(
            "-m {0}".format(u)
            for u in (self.rpath3, self.rpath4)
        )
        origins = " ".join(
            "-g {0}".format(u)
            for u in (self.rpath3, self.rpath4)
        )

        self.pkg("image-create -p test1={0} {1} {2} {3}".format(self.rpath1,
            mirrors, origins, img_path))

        self.pkg("-R {0} publisher | grep origin.*{1}".format(img_path,
            self.rurl1))
        for u in (self.rurl3, self.rurl4):
            self.pkg("-R {0} publisher | grep mirror.*{1}".format(
                img_path, u))
            self.pkg("-R {0} publisher | grep origin.*{1}".format(
                img_path, u))
        shutil.rmtree(img_path, True)

        # Verify that -p auto-configuration works as expected for a
        # a v1 repository when no prefix is provided.
        self.pkg("image-create -p {0} {1}".format(self.rurl1, img_path))
        pub_cfg = {
            "publisher": { "prefix": "test1" },
            "repository": { "origins": self.rurl1 }
        }
        self.__verify_pub_cfg(img_path, "test1", pub_cfg)
        shutil.rmtree(img_path)

        # Verify that -p auto-configuration works as expected for a
        # a v1 repository when a prefix is provided.
        self.pkg("image-create -p test1={0} {1}".format(self.rurl1, img_path))
        pub_cfg = {
            "publisher": { "prefix": "test1" },
            "repository": { "origins": self.rurl1 }
        }
        self.__verify_pub_cfg(img_path, "test1", pub_cfg)
        shutil.rmtree(img_path)

        # Verify that -p auto-configuration works as expected for a
        # a v1 repository with additional origins and mirrors.
        self.pkg("image-create -p test1={0} -g {1} -m {2} {3}".format(
            self.rurl1, self.rurl3, self.durl5, img_path))
        pub_cfg = {
            "publisher": { "prefix": "test1" },
            "repository": {
                "origins": "{0},{1}".format(self.rurl1, self.rurl3),
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
        self.pkg("image-create -p test=InvalidURI {0}".format(p), exit=1)
        self.assertFalse(os.path.exists(p))

        self.pkg("image-create -p InvalidURI {0}".format(p), exit=1)
        self.assertFalse(os.path.exists(p))

        # Valid URI but without prefix and with --no-refresh; auto-
        # configuration isn't possible in this scenario and so
        # an image should not be created.
        self.pkg("image-create --no-refresh -p {0} {1}".format(self.rurl1, p),
            exit=2)
        self.assertFalse(os.path.exists(p))

        # Valid URI but with the wrong publisher prefix should
        # not create an image.
        self.pkg("image-create -p nosuchpub={0} {1}".format(self.rurl1, p),
            exit=1)
        self.assertFalse(os.path.exists(p))

        # Valid URI, without a publisher prefix, but for a repository
        # that doesn't provide publisher configuration should not
        # create an image.
        self.pkg("image-create -p {0} {1}".format(self.durl5, p),
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
        self.pkg("image-create -p test1={0} {1}".format(self.rurl1,
            img_path))
        os.chdir(pwd)
        self.assertFalse(os.path.exists(os.path.join(abs_img_path,
            img_path)))
        shutil.rmtree(abs_img_path)

        # Now verify that the image root isn't duplicated within the
        # specified image root if the specified root already exists.
        os.chdir(self.test_root)
        os.mkdir(img_path)
        self.pkg("image-create -p test1={0} {1}".format(self.rurl1,
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
        self.pkg("set-publisher -O {0} test1".format(self.rurl1))
        self.pkg("list --no-refresh -a | grep baz")

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

        self.pkg("image-create -p test1={0} {1}/image".format(
            self.rurl1, p), su_wrap=True, exit=1)

    def test_11_ssl_key_cert_set(self):
        """Verify that pkg image create will still pass if
        repo_uri doesn't have ssl_scheme but one of the origins or
        mirrors have schemes"""

        self.image_create(self.rurl1)

        # Set the first publisher to a https URL
        key_path = os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem")
        cert_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")

        img_key_path = os.path.join(self.img_path(), "var", "pkg",
            "ssl", misc.get_data_digest(key_path,
            hash_func=hashlib.sha1)[0])
        img_cert_path = os.path.join(self.img_path(), "var", "pkg",
            "ssl", misc.get_data_digest(cert_path,
            hash_func=hashlib.sha1)[0])

        img_path = os.path.join(self.test_root, "img")
        # Test image create will fail if repo_uri
        # does not have https
        self.pkg(("image-create --no-refresh -p foo=http://{0}"
            " -k {1} -c {2} {3}").format(self.bogus_url, key_path,
            cert_path, img_path), exit=1)

        # Test image create will fail if there are no https url
        self.pkg(("image-create --no-refresh -p foo=http://{0}"
                " -k {1} -c {2} -g http://{0} {3}").format(
            self.bogus_url, key_path, cert_path, img_path), exit=1)

        # Test image create will succeed if one origin as https
        self.pkg(("image-create --no-refresh -p foo=http://{0}"
            " -k {1} -c {2} -g https://{0} {3}").format(
            self.bogus_url, key_path, cert_path, img_path), exit=0)
        shutil.rmtree(img_path)

        # Test image create will succeed if one mirror has https
        self.pkg(("image-create --no-refresh -p foo=http://{0}"
            " -k {1} -c {2} -m https://{0} {3}").format(
            self.bogus_url, key_path, cert_path, img_path), exit=0)
        shutil.rmtree(img_path)


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

    def test_763c(self):
        """Bug 763, traceback 3: -p given to image-create, but no
        publisher specified."""

        self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
            self.pkg, "image-create -p foo")

    def test_bad_publisher_options(self):
        """More tests that abuse the publisher prefix and URL."""

        self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
            self.pkg, "image-create -p $%^8" + ("=http://{0}1".format(
            self.bogus_url)))

        self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
            self.pkg, "image-create -p test1=http://$%^8")

        self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
            self.pkg, "image-create -p test1=http://{0}1:abcde".format(
            self.bogus_url))

        self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
            self.pkg, "image-create -p test1=ftp://{0}1".format(
            self.bogus_url))

        self.assertRaises(pkg5unittest.UnexpectedExitCodeException, \
            self.pkg, "image-create -p test1=ftp://{0}1 -p test2=http://{1}2:abc".format(
            self.bogus_url, self.bogus_url))


if __name__ == "__main__":
    unittest.main()
