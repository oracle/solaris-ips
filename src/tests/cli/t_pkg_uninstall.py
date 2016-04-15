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

# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import shutil
import unittest

import pkg.fmri as fmri

class TestCommandLine(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self,
                    ["test", "bogus"])
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()

        def test_pkg_bogus_opts(self):
                """ pkg bogus option checks """

                # create a image to avoid non-existant image messages
                self.image_create(self.rurl1)

                self.pkg("uninstall -@ foo", exit=2)
                self.pkg("uninstall -vq foo", exit=2)
                self.pkg("uninstall", exit=2)
                self.pkg("uninstall foo@x.y", exit=1)
                self.pkg("uninstall pkg:/foo@bar.baz", exit=1)
                self.image_destroy()

        foo12 = """
            open foo@1.2,5.11-0
            add dir path=/tmp mode=0755 owner=root group=bin
            close """

        def test_rmdir_cwd(self):
                """Remove a package containing a directory that's our cwd."""

                self.pkgsend_bulk(self.rurl1, self.foo12)
                self.image_create(self.rurl1)

                self.pkg("install foo")
                os.chdir(os.path.join(self.get_img_path(), "tmp"))
                self.pkg("uninstall foo")
                self.image_destroy()

        foob20 = """
            open foob@2.0,5.11-0
            add depend type=require fmri=barb@2.0
            close """

        barb20 = """
            open barb@2.0,5.11-0
            add depend type=require fmri=foob@2.0
            close """

        bazb20 = """
            open bazb@2.0,5.11-0
            add depend type=require fmri=foob@2.0
            close """

        def test_dependencies(self):
                """This code tests for:
                  1) uninstall is blocked if dependencies are found
                  2) packages w/ circular dependencies can be uninstalled
                  3) if all dependencies are to be deleted, uninstall works."""
                self.pkgsend_bulk(self.rurl1, (self.foob20, self.barb20,
                    self.bazb20))
                self.image_create(self.rurl1)
                self.pkg("install bazb")
                self.pkg("verify")
                self.pkg("uninstall foob", exit=1)
                self.pkg("uninstall bazb foob barb")
                self.pkg("verify")
                self.image_destroy()

        quux10 = """
            open quux@1.0,5.11-0
            close """

        renamed10 = """
            open renamed@1.0,5.11-0
            add set name=pkg.renamed value=true
            add depend type=require fmri=quux@1.0
            close """

        holder10 = """
            open holder@1.0,5.11-0
            add depend type=require fmri=renamed@1.0
            close """

        implicit11 = """
            open implicit@1.1,5.11-0
            add file tmp/file1 mode=0644 owner=root group=bin path=implicit/file1
            close """

        def test_uninstalled_state(self):
                """Uninstalling a package that is no longer known should result
                in its removal from the output of pkg list -a, even if it has
                been renamed, etc.""" 

                self.pkgsend_bulk(self.rurl1, (self.quux10, self.renamed10,
                    self.holder10))
                self.image_create(self.rurl1)
                self.pkg("install -v renamed holder")
                self.pkg("verify")
                self.pkg("set-publisher -P -g {0} bogus".format(self.rurl2))
                self.pkg("unset-publisher test")
                self.pkg("info quux@1.0 renamed@1.0")
                self.pkg("uninstall holder renamed")
                self.pkg("list -a renamed@1.0", exit=1)
                self.pkg("uninstall quux")
                self.pkg("list -a quux@1.0", exit=1)
                self.image_destroy()

        def test_uninstall_implicit(self):
                """Verify uninstall fails gracefully if needed during implicit
                directory removal.""" 

                self.make_misc_files("tmp/file1")
                self.pkgsend_bulk(self.rurl1, (self.implicit11))
                self.image_create(self.rurl1)
                lofs_dir = os.path.join(self.test_root, "image0", "implicit")
                os.mkdir(lofs_dir)
                tmp_dir = os.path.join(self.test_root, "image0", "tmp_impl_dir")
                os.mkdir(tmp_dir)
                os.system("mount -F lofs {0} {1}".format(tmp_dir, lofs_dir))
                self.pkg("install implicit")
                self.pkg("uninstall implicit")
                os.system("umount {0} ".format(lofs_dir))
                os.rmdir(lofs_dir)
                os.rmdir(tmp_dir)

        def test_uninstall_missing_manifest(self):
                """Verify graceful failure if a package being removed has a
                missing manifest."""

                def remove_man(pfmri):
                        # Now remove the manifest and manifest cache for package
                        # and retry the info for an unprivileged user both local
                        # and remote.
                        mdir = os.path.dirname(self.get_img_manifest_path(
                            pfmri))
                        shutil.rmtree(mdir)
                        self.assertFalse(os.path.exists(mdir))

                        mcdir = self.get_img_manifest_cache_dir(pfmri)
                        shutil.rmtree(mcdir)
                        self.assertFalse(os.path.exists(mcdir))

                pfmri = fmri.PkgFmri(self.pkgsend_bulk(self.rurl1,
                    self.quux10)[0])
                self.image_create(self.rurl1)

                # Install a package.
                self.pkg("install quux")

                # Should succeed since original manifest can still be retrieved.
                remove_man(pfmri)
                self.pkg("uninstall -nv quux")
                remove_man(pfmri)

                # Should fail since publisher no longer exists and should
                # explain why.
                self.pkg("unset-publisher test")
                self.pkg("uninstall -nv quux", exit=1)
                self.assertTrue(len(self.errout) > 1)
                self.assertTrue("no errors" not in self.errout, self.errout)
                self.assertTrue("Unknown" not in self.errout, self.errout)

                # Should fail because publisher has no configured repositories
                # and should explain why.
                self.pkg("set-publisher test")
                self.pkg("uninstall -nv quux", exit=1)
                self.assertTrue("no errors" not in self.errout, self.errout)
                self.assertTrue("Unknown" not in self.errout, self.errout)

        def test_ignore_missing(self):
                """Test that uninstall shows correct behavior w/ and w/o
                   --ignore-missing."""
                self.image_create(self.rurl1)
                self.pkg("uninstall missing", exit=1)
                self.pkg("uninstall --ignore-missing missing", exit=4)


if __name__ == "__main__":
        unittest.main()
