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

# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import os
import shutil
import sys
import tempfile
import traceback
import unittest

import pkg.altroot as ar
import pkg.client.image as image


class TestAltroot(pkg5unittest.Pkg5TestCase):
        persistent_setup = True

        def setUp(self):
                self.i_count = 4

                # Create images in /var/tmp to run the tests on ZFS
                # filesystems.
                self.test_path = tempfile.mkdtemp(prefix="test-suite",
                    dir="/var/tmp")

                self.imgs_path = {}
                for i in range(0, self.i_count):
                        path = os.path.join(self.test_path,
                            "image{0:d}".format(i))
                        self.imgs_path[i] = path

                # image path
                self.i = []

                # image files and directories
                self.p_f1 = "f1"
                self.p_f2 = "f2"
                self.p_none = "none"
                self.p_d = "d"
                self.p_d_f1 = os.path.join(self.p_d, "f1")
                self.p_d_f2 = os.path.join(self.p_d, "f2")
                self.p_d_none = os.path.join(self.p_d, "none")
                self.p_f1_redir = "f1_redir"
                self.p_f2_redir = "f2_redir"
                self.p_d_redir = "d_redir"
                self.p_d_f1_redir = os.path.join(self.p_d_redir, "f1")
                self.p_d_f2_redir = os.path.join(self.p_d_redir, "f2")
                self.p_d_none_redir = os.path.join(self.p_d_redir, "none")

                for i in range(0, self.i_count):
                        # first assign paths.  we'll use the image paths even
                        # though we're not actually doing any testing with
                        # real images.
                        r = self.imgs_path[i]
                        self.i.insert(i, r)

                        os.makedirs(r)
                        if i == 0:
                                # simulate a user image
                                os.makedirs(
                                    os.path.join(r, image.img_user_prefix))
                        elif i == 1:
                                # simulate a root image
                                os.makedirs(
                                    os.path.join(r, image.img_root_prefix))
                        elif i == 2:
                                # corrupt image: both root and user
                                os.makedirs(
                                    os.path.join(r, image.img_user_prefix))
                                os.makedirs(
                                    os.path.join(r, image.img_root_prefix))

                for i in range(0, self.i_count):
                        r = self.i[i]
                        if i > 0:
                                r_alt = self.i[i - 1]
                        else:
                                r_alt = self.i[self.i_count - 1]
                        r_redir = os.path.basename(r_alt)

                        # create directories and files within the image
                        self.make_file(os.path.join(r, self.p_f1), "foo")
                        self.make_file(os.path.join(r, self.p_f2), "foo")
                        self.make_file(os.path.join(r, self.p_d_f1), "bar")
                        self.make_file(os.path.join(r, self.p_d_f2), "bar")

                        # create sym links that point outside that image
                        os.symlink(os.path.join("..", r_redir, self.p_f1),
                            os.path.join(r, self.p_f1_redir))

                        os.symlink(os.path.join("..", r_redir, self.p_f2),
                            os.path.join(r, self.p_f2_redir))

                        os.symlink(os.path.join("..", r_redir, self.p_d),
                            os.path.join(r, self.p_d_redir))

        def tearDown(self):
                shutil.rmtree(self.test_path)

        def __eremote(self, func, args):
                e = None
                try:
                        func(*args)
                except:
                        e_type, e, e_traceback = sys.exc_info()

                if isinstance(e, OSError) and e.errno == errno.EREMOTE:
                        return

                if e == None:
                        e_str = str(None)
                else:
                        e_str = traceback.format_exc()

                args = ", ".join([str(a) for a in args])
                self.fail(
                    "altroot call didn't return OSError EREMOTE exception\n"
                    "call: {0}({1})\n"
                    "exception: {2}\n".format(
                    func.__name__, args, e_str))

        def test_ar_err_eremote(self):
                """Verify that all altroot accessor functions return EREMOTE
                if they traverse a path which contains a symlink that point
                somewhere outside the specified altroot namespace."""

                r = self.i[0]
                invoke = [
                    (ar.ar_open, (r, self.p_f1_redir, os.O_RDONLY)),
                    (ar.ar_open, (r, self.p_d_f1_redir, os.O_RDONLY)),

                    (ar.ar_unlink, (r, self.p_d_f1_redir)),

                    (ar.ar_rename, (r, self.p_d_f1_redir, self.p_d_f1)),
                    (ar.ar_rename, (r, self.p_d_f1, self.p_d_f1_redir)),
                    (ar.ar_rename, (r, self.p_d_f1_redir, self.p_d_f2_redir)),

                    (ar.ar_mkdir, (r, self.p_d_none_redir, 0o777)),

                    (ar.ar_stat, (r, self.p_f1_redir)),
                    (ar.ar_stat, (r, self.p_d_f1_redir)),

                    (ar.ar_isdir, (r, self.p_d_redir)),
                    (ar.ar_isdir, (r, self.p_d_f1_redir)),

                    (ar.ar_exists, (r, self.p_f1_redir)),
                    (ar.ar_exists, (r, self.p_d_redir)),
                    (ar.ar_exists, (r, self.p_d_f1_redir)),

                    (ar.ar_diff, (r, self.p_f1, self.p_f2_redir)),
                    (ar.ar_diff, (r, self.p_f1_redir, self.p_f2)),
                    (ar.ar_diff, (r, self.p_d_f1, self.p_d_f2_redir)),
                    (ar.ar_diff, (r, self.p_d_f1_redir, self.p_d_f2)),
                ]
                for func, args in invoke:
                        self.__eremote(func, args)

        def __bad_img_prefix(self, func, args):
                rv = func(*args)
                if rv == None:
                        return

                args = ", ".join([str(a) for a in args])
                self.fail(
                    "altroot call didn't return None\n"
                    "call: {0}({1})\n"
                    "rv: {0}\n".format(
                    func.__name__, args, str(rv)))

        def test_ar_err_img_prefix(self):
                """Verify that ar_img_prefix() returns None if we have a
                corrupt image.  image 2 has both user and root image
                repositories.  image 3 is not an image, it's an empty
                directory."""

                invoke = [
                    (ar.ar_img_prefix, (self.i[2],)),
                    (ar.ar_img_prefix, (self.i[3],)),
                ]
                for func, args in invoke:
                        self.__bad_img_prefix(func, args)

if __name__ == "__main__":
        unittest.main()
