#!/usr/bin/python
# -*- coding: utf-8 -*-
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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import errno
import hashlib
import os
import platform
import re
import shutil
import socket
import subprocess
import stat
import struct
import sys
import tempfile
import time
import unittest
from six.moves import range
from six.moves.urllib.parse import quote
from six.moves.urllib.request import urlopen, build_opener, ProxyHandler, Request

import pkg.actions
import pkg.digest as digest
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.portable as portable

from pkg.client.pkgdefs import EXIT_OOPS

try:
        import pkg.sha512_t
        sha512_supported = True
except ImportError:
        sha512_supported = False

class _TestHelper(object):
        """Private helper class for shared functionality between test
        classes."""

        def _assertEditables(self, moved=[], removed=[], installed=[],
            updated=[]):
                """Private helper function that verifies that expected editables
                are listed in parsable output.  If no editable of a given type
                is specified, then no editable files are expected."""

                changed = []
                if moved:
                        changed.append(['moved', moved])
                if removed:
                        changed.append(['removed', removed])
                if installed:
                        changed.append(['installed', installed])
                if updated:
                        changed.append(['updated', updated])

                self.assertEqualParsable(self.output,
                        include=["change-editables"],
                        change_editables=changed)


class TestPkgInstallBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1 timestamp="20080731T024051Z"
            close """
        foo11_timestamp = 1217472051

        foo12 = """
            open foo@1.2,5.11-0
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        afoo10 = """
            open a/foo@1.0,5.11-0
            close """

        boring10 = """
            open boring@1.0,5.11-0
            close """

        boring11 = """
            open boring@1.1,5.11-0
            close """

        bar10 = """
            open bar@1.0,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        bar11 = """
            open bar@1.1,5.11-0
            add depend type=require fmri=pkg:/foo@1.2
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xfoo10 = """
            open xfoo@1.0,5.11-0
            close """

        xbar10 = """
            open xbar@1.0,5.11-0
            add depend type=require fmri=pkg:/xfoo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xbar11 = """
            open xbar@1.1,5.11-0
            add depend type=require fmri=pkg:/xfoo@1.2
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """


        bar12 = """
            open bar@1.2,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        baz10 = """
            open baz@1.0,5.11-0
            add depend type=require fmri=pkg:/foo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/baz mode=0555 owner=root group=bin path=/bin/baz
            close """

        deep10 = """
            open deep@1.0,5.11-0
            add depend type=require fmri=pkg:/bar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        xdeep10 = """
            open xdeep@1.0,5.11-0
            add depend type=require fmri=pkg:/xbar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        ydeep10 = """
            open ydeep@1.0,5.11-0
            add depend type=require fmri=pkg:/ybar@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        a6018_1 = """
            open a6018@1.0,5.11-0
            close """

        a6018_2 = """
            open a6018@2.0,5.11-0
            close """

        b6018_1 = """
            open b6018@1.0,5.11-0
            add depend type=optional fmri=a6018@1
            close """

        badfile10 = """
            open badfile@1.0,5.11-0
            add file tmp/baz mode=644 owner=root group=bin path=/tmp/baz-file
            close """

        baddir10 = """
            open baddir@1.0,5.11-0
            add dir mode=755 owner=root group=bin path=/tmp/baz-dir
            close """

        a16189 = """
            open a16189@1.0,5.11-0
            add depend type=require fmri=pkg:/b16189@1.0
            close """

        b16189 = """
            open b16189@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        fuzzy = """
            open fuzzy@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path="opt/dir with white\tspace"
            add file tmp/cat mode=0644 owner=root group=bin path="opt/dir with white\tspace/cat in a hat"
            close
            open fuzzy@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path="opt/dir with white\tspace"
            add file tmp/cat mode=0644 owner=root group=bin path="opt/dir with white\tspace/cat in a hat"
            add link path=etc/cat_link target="../opt/dir with white\tspace/cat in a hat"
            close """

        ffoo10 = """
            open ffoo@1.0,5.11-0
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        ffoo11 = """
            open ffoo@1.1,5.11-0
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        fbar10 = """
            open fbar@1.0,5.11-0
            add depend type=require fmri=pkg:/ffoo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        fbar11 = """
            open fbar@1.1,5.11-0
            add depend type=require fmri=pkg:/ffoo@1.0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cät
            close """

        secret1 = """
            open secret1@1.0-0
            add dir mode=0755 owner=root group=bin path=/p1
            add file tmp/cat mode=0555 owner=root group=bin sysattr=SH path=/p1/cat
            close """

        secret2 = """
            open secret2@1.0-0
            add dir mode=0755 owner=root group=bin path=/p2
            add file tmp/cat mode=0555 owner=root group=bin sysattr=hidden,system path=/p2/cat
            close """

        secret3 = """
            open secret3@1.0-0
            add dir mode=0755 owner=root group=bin path=/p3
            add file tmp/cat mode=0555 owner=root group=bin sysattr=horst path=/p3/cat
            close """

        secret4 = """
            open secret4@1.0-0
            add dir mode=0755 owner=root group=bin path=/p3
            add file tmp/cat mode=0555 owner=root group=bin sysattr=hidden,horst path=/p3/cat
            close """

        rofiles = """
            open rofilesdir@1.0-0
            add dir mode=0755 owner=root group=bin path=rofdir
            close
            open rofiles@1.0-0
            add file tmp/cat mode=0444 owner=root group=bin path=rofdir/rofile
            close """

        filemissing = """
            open filemissing@1.0,5.11:20160426T084036Z
            add file tmp/truck1 path=opt/truck1 mode=755 owner=root group=bin
            close
        """

        manimissing = """
            open manimissing@1.0,5.11:20160426T084036Z
            add file tmp/truck2 path=opt/truck2 mode=755 owner=root group=bin
            close
        """

        fhashes = {
            "tmp/truck1": "c9e257b659ace6c3fbc4d334f49326b3889fd109",
            "tmp/truck2": "c07fd27b5b57f8131f42e5f2c719a469d9fc71c5"
        }

        misc_files = [ "tmp/libc.so.1", "tmp/cat", "tmp/baz", "tmp/truck1",
            "tmp/truck2" ]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def __get_mf_path(self, fmri_str, pub=None):
                """Given an FMRI, return the path to its manifest in our
                repository."""

                usepub = "test"
                if pub:
                        usepub = pub
                path_comps = [self.dc.get_repodir(), "publisher",
                    usepub, "pkg"]
                pfmri = pkg.fmri.PkgFmri(fmri_str)
                path_comps.append(pfmri.get_name())
                path_comps.append(pfmri.get_link_path().split("@")[1])
                return os.path.sep.join(path_comps)

        def __get_file_path(self, path):
                """Returns the path to a file in the repository. The path name
                must be present in self.fhashes."""

                fpath = os.path.sep.join([self.dc.get_repodir(), "publisher",
                    "test", "file"])
                fhash = self.fhashes[path]
                return os.path.sep.join([fpath, fhash[0:2], fhash])

        def __inject_nofile(self, path):
                fpath = self.__get_file_path(path)
                os.remove(fpath)
                return fpath

        def __inject_nomanifest(self, fmri_str):
                mpath = self.__get_mf_path(fmri_str)
                os.remove(mpath)

        def test_cli(self):
                """Test bad cli options"""

                self.cli_helper("install")
                self.cli_helper("exact-install")

        def cli_helper(self, install_cmd):
                self.image_create(self.rurl)

                self.pkg("-@", exit=2)
                self.pkg("-s status", exit=2)
                self.pkg("-R status", exit=2)

                self.pkg("{0} -@ foo".format(install_cmd), exit=2)
                self.pkg("{0} -vq foo".format(install_cmd), exit=2)
                self.pkg("{0}".format(install_cmd), exit=2)
                self.pkg("{0} foo@x.y".format(install_cmd), exit=1)
                self.pkg("{0} pkg:/foo@bar.baz".format(install_cmd), exit=1)

        def test_basics_1_install(self):
                """Send empty package foo@1.0, install and uninstall """

                plist = self.pkgsend_bulk(self.rurl, self.foo10)
                self.image_create(self.rurl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install --parsable=0 foo")
                self.assertEqualParsable(self.output,
                    add_packages=plist)

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall --parsable=0 foo")
                self.assertEqualParsable(self.output,
                    remove_packages=plist)
                self.pkg("verify")

        def test_basics_1_exact_install(self):
                """ Send empty package foo@1.0, exact-install and uninstall """

                plist = self.pkgsend_bulk(self.rurl, self.foo10)
                self.image_create(self.rurl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("exact-install --parsable=0 foo")
                self.assertEqualParsable(self.output,
                    add_packages=plist)

                # Exact-install the same version should do nothing.
                self.pkg("exact-install foo", exit=4)
                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall --parsable=0 foo")
                self.assertEqualParsable(self.output,
                    remove_packages=plist)
                self.pkg("verify")

        def test_basics_2(self):
                """ Send package foo@1.1, containing a directory and a file,
                    install or exact-install, search, and uninstall. """

                self.basics_2_helper("install")
                self.basics_2_helper("exact-install")

        def basics_2_helper(self, install_cmd):
                # This test needs to use the depot to be able to test the
                # download cache.
                self.dc.start()

                self.pkgsend_bulk(self.durl, (self.foo10, self.foo11),
                    refresh_index=True)
                self.image_create(self.durl)

                self.pkg("list -a")
                self.pkg("{0} foo".format(install_cmd))

                # Verify that content cache is empty after successful install
                # or exact-install.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                cache_dirs = []
                for path, readonly, pub, layout in img_inst.get_cachedirs():
                        if os.path.exists(path):
                                cache_dirs.extend(os.listdir(path))
                self.assertEqual(cache_dirs, [])

                self.pkg("verify")
                self.pkg("list")

                self.pkg("search -l /lib/libc.so.1")
                self.pkg("search -r /lib/libc.so.1")
                self.pkg("search -l blah", exit=1)
                self.pkg("search -r blah", exit=1)

                # check to make sure timestamp was set to correct value
                libc_path = os.path.join(self.get_img_path(), "lib/libc.so.1")
                lstat = os.stat(libc_path)

                assert (lstat[stat.ST_MTIME] == self.foo11_timestamp)

                # check that verify finds changes
                now = time.time()
                os.utime(libc_path, (now, now))
                self.pkg("verify", exit=1)

                self.pkg("uninstall foo")
                self.pkg("verify")
                self.pkg("list -a")
                self.pkg("verify")
                self.dc.stop()

        def test_basics_3(self):
                """Exact-install or Install foo@1.0, upgrade to foo@1.1,
                uninstall. """

                self.basics_3_helper("install")
                self.basics_3_helper("exact-install")

        def basics_3_helper(self, installed_cmd):
                # This test needs to use the depot to be able to test the
                # download cache.
                self.dc.start()

                self.pkgsend_bulk(self.durl, (self.foo10, self.foo11))
                self.image_create(self.durl)
                self.pkg("set-property flush-content-cache-on-success False")

                # Verify that content cache is empty before install or
                # exact-install.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                cache_dirs = []
                for path, readonly, pub, layout in img_inst.get_cachedirs():
                        if os.path.exists(path):
                                cache_dirs.extend(os.listdir(path))
                self.assertEqual(cache_dirs, [])

                self.pkg("{0} foo@1.0".format(installed_cmd))
                self.pkg("list foo@1.0")
                self.pkg("list foo@1.1", exit=1)

                self.pkg("{0} foo@1.1".format(installed_cmd))

                # Verify that content cache is not empty after successful
                # install or exact_install (since
                # flush-content-cache-on-success is True by default) for
                # packages that have content.
                cache_dirs = []
                for path, readonly, pub, layout in img_inst.get_cachedirs():
                        if os.path.exists(path):
                                cache_dirs.extend(os.listdir(path))
                self.assertNotEqual(cache_dirs, [])

                self.pkg("list foo@1.1")
                self.pkg("list foo@1.0", exit=1)
                self.pkg("list foo@1")
                self.pkg("verify")

                self.pkg("uninstall foo")
                self.pkg("list -a")
                self.pkg("verify")
                self.dc.stop()

        def test_basics_4(self):
                """ Add bar@1.0, dependent on foo@1.0, exact-install or
                install, uninstall. """

                self.basics_4_helper("install")
                self.basics_4_helper("exact-install")

        def basics_4_helper(self, installed_cmd):
                # This test needs to use the depot to be able to test the
                # download cache.
                self.dc.start()

                self.pkgsend_bulk(self.durl, (self.foo10, self.foo11,
                    self.bar10))
                self.image_create(self.durl)

                # Set content cache to not be flushed on success.
                self.pkg("set-property flush-content-cache-on-success False")

                # Verify that content cache is empty before install or
                # exact-install.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                cache_dirs = []
                for path, readonly, pub, layout in img_inst.get_cachedirs():
                        if os.path.exists(path):
                                cache_dirs.extend(os.listdir(path))
                self.assertEqual(cache_dirs, [])

                self.pkg("list -a")
                self.pkg("{0} bar@1.0".format(installed_cmd))

                # Verify that content cache is not empty after successful
                # install or exact-install (since
                # flush-content-cache-on-success is False)
                # for packages that have content.
                cache_dirs = []
                for path, readonly, pub, layout in img_inst.get_cachedirs():
                        if os.path.exists(path):
                                cache_dirs.extend(os.listdir(path))
                self.assertNotEqual(cache_dirs, [])

                self.pkg("list")
                self.pkg("verify")
                self.pkg("uninstall -v bar foo")

                # foo and bar should not be installed at this point
                self.pkg("list bar", exit=1)
                self.pkg("list foo", exit=1)
                self.pkg("verify")
                self.dc.stop()

        def test_basics_5_install(self):
                """Install bar@1.0, upgrade to bar@1.1,
                downgrade to bar@1.0.

                Boring should be left alone, while
                foo gets upgraded as needed"""

                self.pkgsend_bulk(self.rurl, (self.bar10, self.bar11,
                    self.foo10, self.foo11, self.foo12, self.boring10,
                    self.boring11))
                self.image_create(self.rurl)

                self.pkg("install foo@1.0 bar@1.0 boring@1.0")
                self.pkg("list foo@1.0 boring@1.0 bar@1.0")
                self.pkg("install -v bar@1.1") # upgrade bar
                self.pkg("list bar@1.1 foo@1.2 boring@1.0")
                self.pkg("install -v bar@1.0") # downgrade bar
                self.pkg("list bar@1.0 foo@1.2 boring@1.0")

        def test_basics_5_exact_install(self):
                """exact-install bar@1.0, upgrade to bar@1.1.
                Boring should be left alone, while
                foo gets upgraded as needed"""

                self.pkgsend_bulk(self.rurl, (self.bar10, self.bar11,
                    self.foo10, self.foo11, self.foo12, self.boring10,
                    self.boring11))
                self.image_create(self.rurl)

                self.pkg("exact-install foo@1.0 bar@1.0 boring@1.0")
                self.pkg("list foo@1.0 boring@1.0 bar@1.0")
                self.pkg("exact-install -v bar@1.1") # upgrade bar
                self.pkg("list bar@1.1 foo@1.2")
                self.pkg("list boring@1.0", exit=1)

        def test_basics_6_install(self):
                """Verify that '@latest' will install the latest version
                of a package."""

                # Create a repository for the test publisher.
                t1dir = os.path.join(self.test_root, "test-repo")
                self.create_repo(t1dir, properties={ "publisher": {
                    "prefix": "test" } })
                self.pkgsend_bulk(t1dir, (self.bar10,
                    self.foo10, self.foo11, self.foo12, self.boring10,
                    self.boring11))
                self.image_create("file:{0}".format(t1dir))

                # Create a repository for a different publisher for at
                # least one of the packages so that we can verify that
                # publisher search order is accounted for by @latest.
                # The second publisher is called 'pub2' here so that
                # it comes lexically before 'test' (see bug 18180) to
                # ensure that latest version ordering works correctly
                # when the same stem is provided by different publishers.
                t2dir = os.path.join(self.test_root, "pub2-repo")
                self.create_repo(t2dir, properties={ "publisher": {
                    "prefix": "pub2" } })
                self.pkgsend_bulk(t2dir, self.bar11)

                self.pkg("set-publisher -p {0}".format(t2dir))
                self.pkg("install '*@latest'")

                # 1.0 of bar should be installed here since pub2 is a
                # lower-ranked publisher.
                self.pkg("list")
                self.pkg("info bar@1.0 foo@1.2 boring@1.1")

                self.pkg("set-publisher --non-sticky test")
                self.pkg("set-publisher -P pub2 ")
                self.pkg("install bar@latest")

                # 1.1 of bar should be installed here since pub2 is a
                # higher-ranked publisher and test is non-sticky.
                self.pkg("list")
                self.pkg("info bar@1.1")

                # Cleanup.
                shutil.rmtree(t1dir)
                shutil.rmtree(t2dir)

        def test_basics_6_exact_install(self):
                """Verify that '@latest' will install the latest version
                of a package."""

                # Create a repository for the test publisher.
                t1dir = os.path.join(self.test_root, "test-repo")
                self.create_repo(t1dir, properties={ "publisher": {
                    "prefix": "test" } })
                self.pkgsend_bulk(t1dir, (self.bar10,
                    self.foo10, self.foo11, self.foo12, self.boring10,
                    self.boring11))
                self.image_create("file:{0}".format(t1dir))

                # Create a repository for a different publisher for at
                # least one of the packages so that we can verify that
                # publisher search order is accounted for by @latest.
                # The second publisher is called 'pub2' here so that
                # it comes lexically before 'test' (see bug 18180) to
                # ensure that latest version ordering works correctly
                # when the same stem is provided by different publishers.
                t2dir = os.path.join(self.test_root, "pub2-repo")
                self.create_repo(t2dir, properties={ "publisher": {
                    "prefix": "pub2" } })
                self.pkgsend_bulk(t2dir, self.bar11)

                self.pkg("set-publisher -p {0}".format(t2dir))
                self.pkg("exact-install '*@latest'")

                # 1.0 of bar should be installed here since pub2 is a
                # lower-ranked publisher.
                self.pkg("list")
                self.pkg("info bar@1.0 foo@1.2 boring@1.1")

                self.pkg("set-publisher --non-sticky test")
                self.pkg("set-publisher -P pub2 ")
                self.pkg("exact-install bar@latest")

                # 1.1 of bar should be installed here since pub2 is a
                # higher-ranked publisher and test is non-sticky.
                self.pkg("info bar@1.1")
                self.pkg("list foo@1.2")
                self.pkg("list boring@1.1", exit=1)

                # Cleanup.
                shutil.rmtree(t1dir)
                shutil.rmtree(t2dir)

        def test_basics_7_install(self):
                """Add xbar@1.1, install xbar@1.0."""

                self.pkgsend_bulk(self.rurl, self.xbar11)
                self.image_create(self.rurl)
                self.pkg("install xbar@1.0", exit=1)

        def test_basics_7_exact_install(self):
                """Add bar@1.1, exact-install bar@1.0."""

                self.pkgsend_bulk(self.rurl, self.xbar11)
                self.image_create(self.rurl)
                self.pkg("exact-install xbar@1.0", exit=1)

        def test_basics_8_exact_install(self):
                """Try to exact-install two versions of the same package."""

                self.pkgsend_bulk(self.rurl, (self.foo11, self.foo12))
                self.image_create(self.rurl)

                self.pkg("exact-install foo@1.1 foo@1.2", exit=1)

        def test_basics_9_exact_install(self):
                """Verify downgrade will work with exact-install."""

                self.pkgsend_bulk(self.rurl, (self.bar10, self.bar11,
                    self.foo10, self.foo12))
                self.image_create(self.rurl)

                self.pkg("install bar@1.1")
                self.pkg("exact-install bar@1.0")
                self.pkg("list bar@1.0")
                self.pkg("list foo@1.2")

        def test_freeze_exact_install(self):
                """Verify frozen packages can be relaxed with exact_install.
                Which means we can ignore the frozen list with exact_install.
                """

                self.pkgsend_bulk(self.rurl, (self.fbar10, self.ffoo10,
                    self.fbar11, self.ffoo11))
                self.image_create(self.rurl)

                # Freeze bar@1.0.
                self.pkg("install fbar@1.0")
                self.pkg("freeze fbar@1.0")
                self.pkg("exact-install fbar@1.1")
                self.pkg("list fbar@1.1")
                self.pkg("list ffoo@1.1")
                self.pkg("uninstall '*'")

                # Freeze both bar@1.0 and foo@1.0.
                self.image_create(self.rurl)
                self.pkg("install fbar@1.0 ffoo@1.0")
                self.pkg("freeze fbar@1.0")
                self.pkg("freeze ffoo@1.0")
                self.pkg("exact-install fbar@1.1")
                self.pkg("list fbar@1.1")
                self.pkg("list ffoo@1.1")

        def test_basics_mdns(self):
                """ Send empty package foo@1.0, install and uninstall """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.pkg("set-property mirror-discovery True")
                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install foo")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall foo")
                self.pkg("verify")

        def test_basics_ipv6(self):
                """Verify package operations can be performed using a depot
                server being addressed via IPv6."""

                # This test needs to use the depot to be able to test
                # IPv6 connectivity.
                self.dc.set_address("::1")
                self.dc.start()

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, (self.foo10, self.foo12))
                self.wait_repo(self.dc.get_repodir())
                self.image_create(durl)

                self.pkg("install foo@1.0")
                self.pkg("info foo@1.0")

                self.pkg("update")
                self.pkg("list")
                self.pkg("info foo@1.2")
                self.pkg("uninstall '*'")
                self.dc.stop()
                self.dc.set_address(None)

        def test_image_upgrade(self):
                """ Send package bar@1.1, dependent on foo@1.2.  Install
                or exact-install bar@1.0.  List all packages.  Upgrade image.
                """

                self.image_upgrade_helper("install")
                self.image_upgrade_helper("exact-install")

        def image_upgrade_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.foo10, self.foo11,
                    self.bar10))
                self.image_create(self.rurl)

                self.pkg("{0} bar@1.0".format(install_cmd))

                self.pkgsend_bulk(self.rurl, (self.foo12, self.bar11))
                self.pkg("refresh")

                self.pkg("contents -H")
                self.pkg("list")
                self.pkg("refresh")

                self.pkg("list")
                self.pkg("verify")
                self.pkg("update -v")
                self.pkg("verify")

                self.pkg("list foo@1.2")
                self.pkg("list bar@1.1")

                self.pkg("uninstall bar foo")
                self.pkg("verify")

        def test_dependent_uninstall(self):
                """Trying to remove a package that's a dependency of another
                package should fail since uninstall isn't recursive."""

                self.pkgsend_bulk(self.rurl, (self.foo10, self.bar10))
                self.image_create(self.rurl)

                self.pkg("install bar@1.0")

                self.pkg("uninstall -v foo", exit=1)
                self.pkg("list bar")
                self.pkg("list foo")

        def test_bug_1338(self):
                """ Add bar@1.1, dependent on foo@1.2, install bar@1.1. """

                self.pkg("list -a")
                self.pkgsend_bulk(self.rurl, self.bar11)
                self.image_create(self.rurl)

                self.pkg("install xbar@1.1", exit=1)

        def test_bug_1338_2(self):
                """ Add bar@1.1, dependent on foo@1.2, and baz@1.0, dependent
                    on foo@1.0, install baz@1.0 and bar@1.1. """

                self.pkgsend_bulk(self.rurl, (self.bar11, self.baz10))
                self.image_create(self.rurl)
                self.pkg("list -a")
                self.pkg("install baz@1.0 bar@1.1")

        def test_bug_1338_3(self):
                """ Add xdeep@1.0, xbar@1.0. xDeep@1.0 depends on xbar@1.0 which
                    depends on xfoo@1.0, install xdeep@1.0. """

                self.pkgsend_bulk(self.rurl, (self.xbar10, self.xdeep10))
                self.image_create(self.rurl)

                self.pkg("install xdeep@1.0", exit=1)

        def test_bug_1338_4(self):
                """ Add ydeep@1.0. yDeep@1.0 depends on ybar@1.0 which depends
                on xfoo@1.0, install ydeep@1.0. """

                self.pkgsend_bulk(self.rurl, self.ydeep10)
                self.image_create(self.rurl)

                self.pkg("install ydeep@1.0", exit=1)

        def test_bug_2795(self):
                """ Try to install two versions of the same package """

                self.pkgsend_bulk(self.rurl, (self.foo11, self.foo12))
                self.image_create(self.rurl)

                self.pkg("install foo@1.1 foo@1.2", exit=1)

        def test_bug_6018(self):
                """  From original comment in bug report:

                Consider a repository that contains:

                a@1 and a@2

                b@1 that contains an optional dependency on package a@1

                If a@1 and b@1 are installed in an image, the "pkg update" command
                produces the following output:

                $ pkg update
                No updates available for this image.

                However, "pkg install a@2" works.
                """

                plist = self.pkgsend_bulk(self.rurl, (self.a6018_1,
                    self.a6018_2, self.b6018_1))
                self.image_create(self.rurl)
                self.pkg("install b6018@1 a6018@1")
                # Test the parsable output of update.
                self.pkg("update --parsable=0")
                self.assertEqualParsable(self.output,
                    change_packages=[[plist[0], plist[1]]])
                self.pkg("list b6018@1 a6018@2")

        def test_install_matching(self):
                """ Try to [un]install or exact-install packages matching a
                pattern """

                self.install_matching_helper("install")
                self.install_matching_helper("exact-install")

        def install_matching_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.foo10, self.bar10,
                    self.baz10))
                self.image_create(self.rurl)
                # don't specify versions here; we have many
                # different versions of foo, bar & baz in repo
                # when entire class is run w/ one repo instance.

                # first case should fail since multiple patterns
                # match the same pacakge
                self.pkg("{0} 'ba*' 'b*'".format(install_cmd), exit=1)
                self.pkg("{0} 'ba*'".format(install_cmd), exit=0)
                self.pkg("list foo", exit=0)
                self.pkg("list bar", exit=0)
                self.pkg("list baz", exit=0)
                self.pkg("uninstall 'b*' 'f*'")

                # However, multiple forms of the same pattern should simply be
                # coalesced and allowed.
                self.pkg("{0} pkg:/foo /foo ///foo pkg:///foo".format(install_cmd))
                self.pkg("list")
                self.pkg("verify pkg:/foo /foo ///foo pkg:///foo")
                self.pkg("uninstall pkg:/foo /foo ///foo "
                    "pkg:///foo")

        def test_bad_package_actions(self):
                """Test the install of packages that have actions that are
                invalid."""

                self.bad_package_actions("install")
                self.bad_package_actions("exact-install")

        def bad_package_actions(self, install_cmd):
                # First, publish the package that will be corrupted and create
                # an image for testing.
                plist = self.pkgsend_bulk(self.rurl, (self.badfile10,
                    self.baddir10))
                self.image_create(self.rurl)

                # This should succeed and cause the manifest to be cached.
                self.pkg("{0} {1}".format(install_cmd, " ".join(plist)))

                # While the manifest is cached, get a copy of its contents.
                for p in plist:
                        pfmri = fmri.PkgFmri(p)
                        mdata = self.get_img_manifest(pfmri)
                        if mdata.find("dir") != -1:
                                src_mode = "mode=755"
                        else:
                                src_mode = "mode=644"

                        # Now remove the package so corrupt case can be tested.
                        self.pkg("uninstall {0}".format(pfmri.pkg_name))

                        # Now attempt to corrupt the client's copy of the
                        # manifest in various ways to check if the client
                        # handles missing mode and invalid mode cases for
                        # file and directory actions.
                        for bad_mode in ("", 'mode=""', "mode=???"):
                                self.debug("Testing with bad mode "
                                    "'{0}'.".format(bad_mode))
                                bad_mdata = mdata.replace(src_mode, bad_mode)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("--debug manifest_validate=Never "
                                    "{0} {1}".format(install_cmd, pfmri.pkg_name),
                                    exit=1)

                        # Now attempt to corrupt the client's copy of the
                        # manifest in various ways to check if the client
                        # handles missing or invalid owners and groups.
                        for bad_owner in ("", 'owner=""', "owner=invaliduser"):
                                self.debug("Testing with bad owner "
                                    "'{0}'.".format(bad_owner))

                                bad_mdata = mdata.replace("owner=root",
                                    bad_owner)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("--debug manifest_validate=Never "
                                    "{0} {1}".format(install_cmd, pfmri.pkg_name),
                                    exit=1)

                        for bad_group in ("", 'group=""', "group=invalidgroup"):
                                self.debug("Testing with bad group "
                                    "'{0}'.".format(bad_group))

                                bad_mdata = mdata.replace("group=bin",
                                    bad_group)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("--debug manifest_validate=Never "
                                    "{0} {1}".format(install_cmd, pfmri.pkg_name),
                                    exit=1)

                        # Now attempt to corrupt the client's copy of the
                        # manifest such that actions are malformed.
                        for bad_act in (
                            'set name=description value="" \" my desc  ""',
                            "set name=com.sun.service.escalations value="):
                                self.debug("Testing with bad action "
                                    "'{0}'.".format(bad_act))
                                bad_mdata = mdata + "{0}\n".format(bad_act)
                                self.write_img_manifest(pfmri, bad_mdata)
                                self.pkg("--debug manifest_validate=Never "
                                    "{0} {1}".format(install_cmd, pfmri.pkg_name),
                                    exit=1)

        def test_bug_3770(self):
                """ Try to install a package from a publisher with an
                unavailable repository. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                # Depot hasn't been started, so client can't connect.
                self.pkg("set-publisher --no-refresh -O {0} test".format(self.durl))
                self.pkg("install foo@1.1", exit=1)

        def test_bug_9929(self):
                """Make sure that we can uninstall a package that already
                has its contents on disk even when the repository isn't
                accessible."""

                # Depot required for this test since client doesn't cache
                # files from a file repository by default.
                self.dc.start()
                self.pkgsend_bulk(self.durl, self.foo11)
                self.image_create(self.durl)

                self.pkg("install foo")

                # Stop depot, so client can't connect.
                self.dc.stop()
                self.pkg("set-publisher --no-refresh -O {0} test".format(self.durl))
                self.pkg("uninstall foo")

        def test_bug_16189(self):
                """Create a repository with a pair of manifests.  Have
                pkg A depend upon pkg B.  Rename pkg B on the depot-side
                and attempt to install. This should fail, but not traceback.
                Then, modify the manifest on the serverside, ensuring that
                the contents don't match the hash.  Then try the install again.
                This should also fail, but not traceback."""

                afmri = self.pkgsend_bulk(self.rurl, self.a16189)
                bfmri = self.pkgsend_bulk(self.rurl, self.b16189)
                self.image_create(self.rurl)

                repo = self.dc.get_repo()

                bpath = repo.manifest(bfmri[0])
                old_dirname = os.path.basename(os.path.dirname(bpath))
                old_dirpath = os.path.dirname(os.path.dirname(bpath))
                new_dirname = "potato"
                old_path = os.path.join(old_dirpath, old_dirname)
                new_path = os.path.join(old_dirpath, new_dirname)
                os.rename(old_path, new_path)
                self.pkg("install a16189", exit=1)

                os.rename(new_path, old_path)
                self.image_destroy()
                self.image_create(self.rurl)

                apath = repo.manifest(afmri[0])
                afobj = open(apath, "w")
                afobj.write("set name=pkg.summary value=\"banana\"\n")
                afobj.close()
                self.pkg("install a16189", exit=1)

        def test_install_fuzz(self):
                """Verify that packages delivering files with whitespace in
                their paths can be installed or exact-installed, updated, and
                uninstalled."""

                self.pkgsend_bulk(self.rurl, self.fuzzy)
                self.image_create(self.rurl)

                self.pkg("install fuzzy@1")
                self.pkg("verify -v")
                self.pkg("update -vvv fuzzy@2")
                self.pkg("verify -v")

                for name in (
                    "opt/dir with white\tspace/cat in a hat",
                    "etc/cat_link",
                ):
                        self.debug("fname: {0}".format(name))
                        self.assertTrue(os.path.exists(os.path.join(self.get_img_path(),
                            name)))

                self.pkg("uninstall -vvv fuzzy")

        def test_sysattrs(self):
                """Test install with setting system attributes."""

                if portable.osname != "sunos":
                        raise pkg5unittest.TestSkippedException(
                            "System attributes unsupported on this platform.")

                plist = self.pkgsend_bulk(self.rurl, [self.secret1,
                    self.secret2, self.secret3, self.secret4])

                # Try to install in /tmp which does not support system
                # attributes. Just make sure we fail gracefully.
                self.image_create(self.rurl)
                self.pkg("install secret1", exit=1)

                # Need to create an image in /var/tmp since sysattrs don't work
                # in tmpfs.
                self.debug(self.rurl)
                old_img_path = self.img_path()
                self.set_img_path(tempfile.mkdtemp(dir="/var/tmp"))

                self.image_create(self.rurl)

                # test without permission for setting sensitive system attribute
                self.pkg("install secret1", su_wrap=True, exit=1)

                # now some tests which should succeed
                self.pkg("install secret1")
                fpath = os.path.join(self.img_path(),"p1/cat")
                p = subprocess.Popen(["/usr/bin/ls", "-/", "c", fpath],
                    stdout=subprocess.PIPE)
                out, err = p.communicate()
                # sensitive attr is not in 11 FCS, so no closing }
                expected = b"{AH-S---m----"
                self.assertTrue(expected in out, out)

                self.pkg("install secret2")
                fpath = os.path.join(self.img_path(),"p2/cat")
                p = subprocess.Popen(["/usr/bin/ls", "-/", "c", fpath],
                    stdout=subprocess.PIPE)
                out, err = p.communicate()
                # sensitive attr is not in 11 FCS, so no closing }
                expected = b"{AH-S---m----"
                self.assertTrue(expected in out, out)

                # test some packages with invalid sysattrs
                self.pkg("install secret3", exit=1)
                self.pkg("install secret4", exit=1)
                shutil.rmtree(self.img_path())
                self.set_img_path(old_img_path)

        def test_install_to_reserved_directories(self):
                """Ensure installation of new actions will fail when the delivered
                files target reserved filesystem locations."""

                b1 = """
                    open b1@1.0-0
                    add dir mode=0755 owner=root group=bin path=var/pkg/cache
                    close
                    """
                b2 = """
                    open b2@1.0-0
                    add link path=var/pkg/pkg5.image target=tmp/cat
                    close
                    """
                b3 = """
                    open b3@1.0-0
                    add dir mode=0755 owner=root group=bin path=var/pkg/config
                    close
                    """

                self.image_create(self.rurl)
                self.pkgsend_bulk(self.rurl, [b1, b2, b3])

                self.pkg("install b1", exit=1)
                self.pkg("install b2", exit=1)
                # this should pass because var/pkg/config is not reserved
                self.pkg("install b3", exit=0)

        def test_update_to_reserved_directories(self):
                """Ensure installation of new actions will fail when the delivered
                files target reserved filesystem locations."""

                b1 = """
                    open b1@1.0-0
                    add file tmp/cat mode=0755 owner=root group=bin path=var/pkg/foo
                    close
                    """
                b2 = """
                    open b1@2.0-0
                    add dir mode=0755 owner=root group=bin path=var/pkg/cache
                    close
                    """
                b3 = """
                    open b1@3.0-0
                    add dir mode=0755 owner=root group=bin path=var/pkg/config
                    close
                    """

                self.image_create(self.rurl)
                self.pkgsend_bulk(self.rurl, [b1, b2, b3])

                self.pkg("install b1@1.0-0", exit=0)
                self.pkg("update b1@2.0-0", exit=1)
                # this should pass because var/pkg/config is not reserved
                self.pkg("update b1@3.0-0", exit=0)

        def test_readonly_files(self):
                """Ensure that packages containing files found in a read-only
                directory or read-only files can be uninstalled."""

                self.pkgsend_bulk(self.rurl, self.rofiles)
                self.image_create(self.rurl)

                # First, install parent directory package.
                self.pkg("install -vvv rofilesdir@1.0")
                pdir = os.path.join(self.get_img_path(), "rofdir")

                # Next, install the package.  Note that this test intentionally
                # does not cover the case of *installing* files to a read-only
                # directory.
                self.pkg("install -vvv rofiles@1.0")

                # chmod parent directory to read-only and then verify that the
                # package can still be uninstalled
                os.chmod(pdir, 0o555)
                self.pkg("verify -vvv rofilesdir", exit=1)
                self.pkg("uninstall -vvv rofiles@1.0")

                # Finally, verify directory mode was restored to 555.
                try:
                        self.dir_exists("rofdir", mode=0o555)
                finally:
                        # Ensure directory can be cleaned up.
                        os.chmod(pdir, 0o755)

        def test_error_messages(self):
                """Verify that error messages for installing a package with a
                file or manifest that cannot be retrieved include the package
                FMRI."""

                repo_path = self.dc.get_repodir()
                durl = self.dc.get_depot_url()
                self.dc.start()
                self.image_create(durl)
                # publish a single package and break it
                fmris = self.pkgsend_bulk(repo_path, (self.filemissing,
                    self.manimissing))
                self.__inject_nofile("tmp/truck1")
                self.pkg("install filemissing", exit=1)
                self.assertTrue("pkg://test/filemissing@1.0,5.11:20160426T084036Z"
                    in self.errout)
                self.image_create("file://" + repo_path)
                self.pkg("install filemissing", exit=1)
                self.assertTrue("pkg://test/filemissing@1.0,5.11:20160426T084036Z"
                    in self.errout)
                self.__inject_nomanifest(fmris[1])
                self.pkg("install manimissing", exit=1)
                self.assertTrue("pkg://test/manimissing@1.0,5.11:20160426T084036Z"
                    in self.errout)
                self.dc.stop()


class TestPkgInstallApache(pkg5unittest.ApacheDepotTestCase):

        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1 timestamp="20080731T024051Z"
            close """

        upgrade_np10 = """
            open upgrade-np@1.0,5.11-0
            close"""

        misc_files = [ "tmp/libc.so.1" ]

        def setUp(self):
                pkg5unittest.ApacheDepotTestCase.setUp(self, ["test1", "test2"],
                    start_depots=True)
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(self.durl1, self.foo11)
                self.pkgsend_bulk(self.durl2, self.upgrade_np10)

        def test_corrupt_web_cache(self):
                """Make sure the client can detect corrupt content being served
                to it from a corrupt web cache, modifying its requests to
                retrieve correct content."""

                fmris = self.pkgsend_bulk(self.durl1, (self.foo11,
                    self.upgrade_np10))
                # we need to record just the version string of foo in order
                # to properly quote it later.
                foo_version = fmris[0].split("@")[1]
                self.image_create(self.durl1)

                # we use the system repository as a convenient way to setup
                # a caching proxy
                self.sysrepo("")
                sc_runtime_dir = os.path.join(self.test_root, "sysrepo_runtime")
                sc_conf = os.path.join(sc_runtime_dir, "sysrepo_httpd.conf")
                sc_cache = os.path.join(self.test_root, "sysrepo_cache")

                # ensure pkg5srv can write cache content
                os.chmod(sc_cache, 0o777)

                sysrepo_port = self.next_free_port
                self.next_free_port += 1
                sc = pkg5unittest.SysrepoController(sc_conf,
                    sysrepo_port, sc_runtime_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()

                sysrepo_url = "http://localhost:{0}".format(sysrepo_port)

                saved_pkg_sysrepo_env = os.environ.get("PKG_SYSREPO_URL")
                os.environ["PKG_SYSREPO_URL"] = sysrepo_url

                # create an image, installing a package, to warm up the webcache
                self.image_create(props={"use-system-repo": True})
                self.pkg("install foo@1.1")
                self.pkg("uninstall foo")

                # now recreate the image.  image_create calls image_destroy,
                # thereby cleaning any cached content in the image.
                self.image_create(props={"use-system-repo": True})

                def corrupt_path(path, value="noodles\n", rename=False):
                        """Given a path, corrupt its contents."""
                        self.assertTrue(os.path.exists(path))
                        if rename:
                                os.rename(path, path + ".not-corrupt")
                                with open(path, "w") as f:
                                        f.write(value)
                        else:
                                df = open(path, "w")
                                df.write(value)
                                df.close()

                def corrupt_cache(cache_dir):
                        """Given an apache cache, corrupt it's contents."""

                        for dirpath, dirname, filenames in os.walk(cache_dir):
                                for name in filenames:
                                        if name.endswith(".header"):
                                                data = name.replace(".header",
                                                    ".data")
                                                corrupt_path(os.path.join(
                                                    dirpath, data))
                # corrupt our web cache
                corrupt_cache(sc_cache)

                urls = [
                    # we need to quote the version carefully to use exactly the
                    # format pkg(1) uses - two logically identical urls that
                    # differ only by the way they're quoted are treated by
                    # Apache as separate cacheable resources.
                    "{0}/test1/manifest/0/foo@{1}".format(self.durl1, quote(
                    foo_version)),
                    "{0}/test1/file/1/8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8".format(
                    self.durl1),
                ]

                proxy_handler = ProxyHandler({"http": sysrepo_url})
                proxy_opener = build_opener(proxy_handler)

                # validate that our cache is returning corrupt urls.
                for url in urls:
                        self.debug("url:{0}".format(url))
                        # we should get clean content when we don't use the
                        # cache
                        u = urlopen(url)
                        content = u.readlines()
                        # content from urlopen is bytes
                        self.assertTrue(content != [b"noodles\n"],
                            "Unexpected content from depot")

                        # get the corrupted version, and verify it is broken
                        req = Request(url)
                        u = proxy_opener.open(req)
                        content = u.readlines()

                        self.assertTrue(content == [b"noodles\n"],
                            "Expected noodles, got {0} for {1}".format(content, url))

                # the following should work, as pkg should retry requests
                # where it has detected corrupt contents with a
                # "Cache-Control: no-cache" header.
                self.pkg("refresh --full")
                self.pkg("contents -rm foo@1.1")
                self.pkg("install foo@1.1")

                # since the cache has been refreshed, we should see valid
                # contents when going through the proxy now.
                for url in urls:
                        req = Request(url)
                        u = proxy_opener.open(req)
                        content = u.readlines()
                        self.assertTrue(content != ["noodles\n"],
                            "Unexpected content from depot")

                # ensure that when we actually corrupt the repository
                # as well as the cache, we do detect the errors properly.
                corrupt_cache(sc_cache)
                repodir = self.dcs[1].get_repodir()

                prefix = "publisher/test1"
                self.image_create(props={"use-system-repo": True})

                # When we corrupt the files in the repository, we intentionally
                # corrupt them with different contents than the the cache,
                # allowing us to check the error messages being printed by the
                # transport subsystem.

                filepath = os.path.join(repodir,
                    "{0}/file/85/8535c15c49cbe1e7cb1a0bf8ff87e512abed66f8".format(
                    prefix))
                mfpath = os.path.join(repodir, "{0}/pkg/foo/{1}".format(prefix,
                    quote(foo_version)))
                catpath = os.path.join(repodir, "{0}/catalog/catalog.base.C".format(
                    prefix))

                try:
                        # first corrupt the file
                        corrupt_path(filepath, value="spaghetti\n", rename=True)
                        self.pkg("install foo@1.1", stderr=True, exit=1)
                        os.rename(filepath + ".not-corrupt", filepath)

                        # we should be getting two hash errors, one from the
                        # cache, one from the repo. The one from the repo should
                        # repeat
                        self.assertTrue(
                            "1: Invalid contentpath lib/libc.so.1: chash" in
                            self.errout)
                        self.assertTrue(
                            "2: Invalid contentpath lib/libc.so.1: chash" in
                            self.errout)
                        self.assertTrue("(happened 3 times)" in self.errout)

                        # now corrupt the manifest (we have to re-corrupt the
                        # cache, since attempting to install foo above would
                        # have caused the cache to refetch the valid manifest
                        # from the repo) and remove the version of the manifest
                        # cached in the image.
                        corrupt_cache(sc_cache)
                        corrupt_path(mfpath, value="spaghetti\n", rename=True)
                        shutil.rmtree(os.path.join(self.img_path(),
                            "var/pkg/publisher/test1/pkg"))
                        self.pkg("contents -rm foo@1.1", stderr=True, exit=1)
                        os.rename(mfpath + ".not-corrupt", mfpath)

                        # we should get two hash errors, one from the cache, one
                        # from the repo - the one from the repo should repeat.
                        self.assertTrue(
                            "1: Invalid content: manifest hash failure" in
                            self.errout)
                        self.assertTrue("2: Invalid content: manifest hash failure"
                            in self.errout)
                        self.assertTrue("(happened 3 times)" in self.errout)

                        # finally, corrupt the catalog. Given we've asked for a
                        # full refresh, we retrieve the upstream version only.
                        corrupt_path(catpath, value="spaghetti\n", rename=True)
                        self.pkg("refresh --full", stderr=True, exit=1)
                        self.assertTrue("catalog.base.C' is invalid." in
                            self.errout)
                        os.rename(catpath + ".not-corrupt", catpath)

                finally:
                        # make sure we clean up any corrupt repo contents.
                        for path in [filepath, mfpath, catpath]:
                                not_corrupt = path + ".not-corrupt"
                                if os.path.exists(not_corrupt):
                                        os.rename(not_corrupt, path)

                        if saved_pkg_sysrepo_env:
                                os.environ["PKG_SYSREPO_URL"] = \
                                    saved_pkg_sysrepo_env

        def test_granular_proxy(self):
                """Tests that images can use the set-publisher --proxy argument
                to selectively proxy requests."""

                # we use the system repository as a convenient way to setup
                # a caching proxy.   Since the image doesn't have the property
                # 'use-system-repo=True', the configuration of the sysrepo
                # will remain static.
                self.image_create(self.durl1)
                self.sysrepo("")
                sc_runtime_dir = os.path.join(self.test_root, "sysrepo_runtime")
                sc_conf = os.path.join(sc_runtime_dir, "sysrepo_httpd.conf")
                sc_cache = os.path.join(self.test_root, "sysrepo_cache")

                # ensure pkg5srv can write cache content
                os.chmod(sc_cache, 0o777)

                sysrepo_port = self.next_free_port
                self.next_free_port += 1
                sc = pkg5unittest.SysrepoController(sc_conf,
                    sysrepo_port, sc_runtime_dir, testcase=self)
                self.register_apache_controller("sysrepo", sc)
                sc.start()
                sysrepo_url = "http://localhost:{0}".format(sysrepo_port)

                self.image_create()
                self.pkg("set-publisher -p {0} --proxy {1}".format(self.durl1,
                    sysrepo_url))
                self.pkg("install foo")
                self.pkg("uninstall foo")

                sc.stop()
                # with our proxy offline, and with no other origins
                # available, we should be unable to install
                self.pkg("install --no-refresh foo", exit=1)
                sc.start()

                # we cannot add another origin with the same url
                self.pkg("set-publisher --no-refresh -g {0} test1".format(
                    self.durl1), exit=1)
                # we cannot add another proxied origin with that url
                self.pkg("set-publisher --no-refresh -g {0} "
                    "--proxy http://noodles test1".format(self.durl1),
                    exit=1)

                # Now add a second, unproxied publisher, ensuring we
                # can install packages from there.  Since the proxy
                # isn't configured to proxy that resource, this tests
                # that the proxy for self.durl1 isn't being used.
                self.pkg("set-publisher -g {0} test2".format(self.durl2))
                self.pkg("install --no-refresh "
                    "pkg://test2/upgrade-np@1.0")
                self.pkg("uninstall pkg://test2/upgrade-np@1.0")
                self.pkg("set-publisher -G {0} test2".format(self.durl2))

                # check that runtime proxies are being used - we
                # set a bogus proxy, then ensure our $http_proxy value
                # gets used.
                self.pkg("publisher")
                self.pkg("set-publisher -G {0} test1".format(self.durl1))
                self.pkg("set-publisher --no-refresh -g {0} "
                    "--proxy http://noodles test1".format(self.durl1))
                env = {"http_proxy": sysrepo_url}
                self.pkg("refresh", env_arg=env)
                self.pkg("install foo", env_arg=env)
                self.pkg("uninstall foo", env_arg=env)

                # check that $all_proxy works
                env = {"all_proxy": sysrepo_url}
                self.pkg("install foo", env_arg=env)
                self.pkg("uninstall foo", env_arg=env)

                # now check that no_proxy works
                env["no_proxy"] = "*"
                self.pkg("install foo", env_arg=env)
                self.pkg("refresh --full", env_arg=env)


class TestPkgInstallRepoPerTest(pkg5unittest.SingleDepotTestCase):
        persistent_setup = False
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        foo10 = """
            open foo@1.0,5.11-0
            close """

        disappear10 = """
            open disappear@1.0,5.11-0
            add file tmp/cat mode=0555 owner=root group=bin path=/bin/cat
            close """

        disappear11 = """
            open disappear@1.1,5.11-0
            close """

        misc_files = ["tmp/cat"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

        def test_install_changed_manifest(self):
                """Test that if a manifest that is being installed is cached
                locally has been changed on the repo is updated, the new
                manifest is used."""

                plist = self.pkgsend_bulk(self.rurl, self.foo10)

                self.image_create(self.rurl)
                self.seed_ta_dir("ta3")
                api_inst = self.get_img_api_obj()

                # Use pkg contents to cache the manifest.
                self.pkg("contents -r foo")

                # Specify location as filesystem path.
                self.pkgsign_simple(self.dc.get_repodir(), plist[0])

                # Ensure that the image requires signed manifests.
                self.pkg("set-property signature-policy require-signatures")
                api_inst.reset()

                # Install the package
                self._api_install(api_inst, ["foo"])

        def test_keep_installed_changed_manifest(self):
                """Test that if a manifest that has been installed is changed on
                the server is updated, the installed manifest is not changed."""

                pfmri = self.pkgsend_bulk(self.rurl, self.disappear10)[0]

                self.image_create(self.rurl)
                api_inst = self.get_img_api_obj()

                # Install the package
                self._api_install(api_inst, ["disappear"])

                self.assertTrue(os.path.isfile(os.path.join(
                    self.img_path(), "bin", "cat")))
                repo = self.dc.get_repo()
                m_path = repo.manifest(pfmri)
                with open(m_path, "r") as fh:
                        fmri_lines = fh.readlines()
                with open(m_path, "w") as fh:
                        for l in fmri_lines:
                                if "usr/bin/cat" in l:
                                        continue
                                fh.write(l)
                repo.rebuild()

                pfmri = self.pkgsend_bulk(self.rurl, self.disappear11)[0]
                self._api_update(api_inst)
                self.assertTrue(not os.path.isfile(os.path.join(
                    self.img_path(), "bin", "cat")))


class TestPkgActuators(pkg5unittest.SingleDepotTestCase):
        """Test package actuators"""
        persistent_setup = True

        pkgs = (
                """
                    open A@0.5,5.11-0
                    close """,
                """
                    open A@1.0,5.11-0
                    close """,
                """
                    open A@2.0,5.11-0
                    close """,
                """
                    open B@1.0,5.11-0
                    close """,
                """
                    open B@2.0,5.11-0
                    close """,
                """
                    open C@1.0,5.11-0
                    add depend type=require fmri=trigger
                    close """,
                """
                    open trigger@1.0,5.11-0
                    add set name=pkg.additional-update-on-uninstall value=A@2
                    close """,
                """
                    open trigger@2.0,5.11-0
                    add set pkg.additional-update-on-uninstall=A@1
                    close """,
                """
                    open trigger@3.0,5.11-0
                    add set name=pkg.additional-uninstall-on-uninstall value=A
                    close """,
                """
                    open trigger@4.0,5.11-0
                    add set pkg.additional-uninstall-on-uninstall=A
                    close """,
                """
                    open trigger@5.0,5.11-0
                    add set name=pkg.additional-uninstall-on-uninstall value=A@2 value=B@2
                    close """,
                """
                    open trigger@6.0,5.11-0
                    add set name=pkg.additional-uninstall-on-uninstall value=A@1
                    close """,
                """
                    open trigger@7.0,5.11-0
                    add set name=pkg.additional-uninstall-on-uninstall value=C
                    close """,
                """
                    open evil@1.0,5.11-0
                    add set name=pkg.additional-update-on-uninstall value=evil@2
                    close """,
                """
                    open evil@2.0,5.11-0
                    close """,
                )

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, self.pkgs)

        def test_basics(self):
                """Test that pkg actuators work as expected."""
                # prepare image
                self.image_create(self.rurl)
                self.pkg("install A@1")
                self.pkg("install -v trigger@1")
                self.pkg("list A@1 trigger@1")

                # update on uninstall
                self.pkg("uninstall -v trigger")
                self.pkg("list A@2")

                self.pkg("install -v trigger@2")
                self.pkg("uninstall -v trigger")
                self.pkg("list A@1")

                # uninstall on uninstall
                self.pkg("install -v trigger@3")
                self.pkg("uninstall -v trigger")
                self.pkg("list A", exit=1)

                # verify unversioned actuator triggers
                self.pkg("install -v trigger@4 A@1")
                self.pkg("uninstall -v trigger")
                self.pkg("list A", exit=1)
                self.pkg("install -v trigger@4 A@2")
                self.pkg("uninstall -v trigger")
                self.pkg("list A", exit=1)

                # verify correct version is uninstalled
                self.pkg("install -v trigger@6 A@1")
                self.pkg("uninstall -v trigger")
                self.pkg("list A", exit=1)

                # verify non-matching version is not installed
                self.pkg("install -v trigger@6 A@2")
                self.pkg("uninstall -v trigger")
                self.pkg("list A")

                # multiple values
                self.pkg("install -v trigger@5 A@2 B@2")
                self.pkg("uninstall -v trigger")
                self.pkg("list A B", exit=1)

                # multiple values but at different versions
                self.pkg("install -v trigger@5 A@1 B@1")
                self.pkg("uninstall -v trigger")
                self.pkg("list A@1 B@1")

                # removal pkg depends on trigger
                self.pkg("install -v trigger@7 C")
                self.pkg("uninstall -v trigger")
                self.pkg("list C", exit=1)

                # test that uninstall actuators also work when pkg is rejected
                self.pkg("install -v A@1 trigger@1")
                self.pkg("list A@1")
                # install with reject
                self.pkg("install --reject trigger B@1")
                self.pkg("list A@2")
                # update with reject
                self.pkg("install -v trigger@2")
                self.pkg("update -v --reject trigger B@2")
                self.pkg("list A@1")

                # self-referencing (evil) pkgs
                self.pkg("install -v evil@1")
                # solver will complain about passing same pkg to reject and
                # proposed dict
                self.pkg("uninstall -v evil@1", exit=1)
                # try workaround
                self.pkg("-R {0} -D ignore-pkg-actuators=true "
                    "uninstall -v evil@1".format(self.get_img_path()))
                self.pkg("list evil", exit=1)

                # Test overlapping user and actuator pkg requests.
                # Since actuators are treated like user requests, the solver
                # will pick the latest one.
                self.pkg("install -v A@1 trigger@1")
                # update with reject
                self.pkg("update --parsable=0 --reject trigger A@0.5")
                self.pkg("list A@2")


class TestPkgInstallUpdateReject(pkg5unittest.SingleDepotTestCase):
        """Test --reject option to pkg update/install"""
        persistent_setup = True

        pkgs = (
                """
                    open A@1.0,5.11-0
                    add depend type=require-any fmri=pkg:/B@1.0 fmri=pkg:/C@1.0
                    close """,
                """
                    open A@2.0,5.11-0
                    add depend type=require-any fmri=pkg:/B@1.0 fmri=pkg:/C@1.0
                    close """,

                """
                    open B@1.0,5.11-0
                    add depend type=exclude fmri=pkg:/C
                    close """,

                """
                    open C@1.0,5.11-0
                    add depend type=exclude fmri=pkg:/B
                    close """,

                """
                    open kernel@1.0,5.11-0.1
                    add depend type=require fmri=pkg:/incorp
                    close """,

                """
                    open kernelX@1.0,5.11-0.1
                    add depend type=require fmri=pkg:/incorp
                    close """,

                """
                    open kernel@1.0,5.11-0.2
                    add depend type=require fmri=pkg:/incorp
                    close """,

                """
                    open incorp@1.0,5.11-0.1
                    add depend type=incorporate fmri=kernel@1.0,5.11-0.1
                    close """,

                 """
                    open incorp@1.0,5.11-0.2
                    add depend type=incorporate fmri=kernel@1.0,5.11-0.2
                    close """,

                """
                    open kernel@1.0,5.11-0.1.1.0
                    add depend type=require fmri=pkg:/incorp
                    add depend type=require fmri=pkg:/idr1
                    close """,


                """
                    open kernel@1.0,5.11-0.1.1.1
                    add depend type=require fmri=pkg:/incorp
                    add depend type=require fmri=pkg:/idr1
                    close """,

                """
                    open kernel@1.0,5.11-0.1.2.0
                    add depend type=require fmri=pkg:/incorp
                    add depend type=require fmri=pkg:/idr2
                    close """,

                """
                    open kernelX@1.0,5.11-0.1.1.0
                    add depend type=require fmri=pkg:/incorp
                    add depend type=require fmri=pkg:/idrX
                    close """,

                """
                    open idr1@1.0,5.11-0.1.1.0
                    add depend type=incorporate fmri=kernel@1.0,5.11-0.1.1.0
                    add depend type=require fmri=idr1_entitlement
                    close """,

                """
                    open idr1@1.0,5.11-0.1.1.1
                    add depend type=incorporate fmri=kernel@1.0,5.11-0.1.1.1
                    add depend type=require fmri=idr1_entitlement
                    close """,

                """
                    open idr2@1.0,5.11-0.1.2.0
                    add depend type=incorporate fmri=kernel@1.0,5.11-0.1.2.0
                    add depend type=require fmri=idr2_entitlement
                    close """,

                """
                    open idrX@1.0,5.11-0.1.1.0
                    add set name=pkg.additional-update-on-uninstall value=kernelX@1.0,5.11-0.1
                    add depend type=incorporate fmri=kernelX@1.0,5.11-0.1.1.0
                    add depend type=require fmri=idr1_entitlement
                    close """,

                """
                    open idr1_entitlement@1.0,5.11-0
                    add depend type=exclude fmri=no-idrs
                    close """,

                """
                    open idr2_entitlement@1.0,5.11-0
                    add depend type=exclude fmri=no-idrs
                    close """,

                # hack to prevent idrs from being installed from repo...

                """
                    open no-idrs@1.0,5.11-0
                    close """,

                """
                    open pkg://contrib/bogus@1.0,5.11-0
                    add depend type=exclude fmri=A
                    add depend type=require fmri=bogus1
                    add depend type=require fmri=bogus2
                    close """,

                """
                    open pkg://contrib/bogus1@1.0,5.11-0
                    add depend type=exclude fmri=B
                    close """,

                """
                    open pkg://contrib/bogus2@1.0,5.11-0
                    add depend type=exclude fmri=C
                    close """

                )


        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, self.pkgs)

        def test_install(self):
                self.image_create(self.rurl, prefix="")
                # simple test of reject
                self.pkg("install --reject B A")
                self.pkg("list A C")
                self.pkg("uninstall '*'")
                self.pkg("install --reject C A")
                self.pkg("list A B")
                self.pkg("uninstall '*'")

                # test swapping XOR'd pkgs B & C w/o uninstalling A
                self.pkg("install B")
                self.pkg("install A")
                self.pkg("list A B")
                self.pkg("install --reject B C")
                self.pkg("list A C")
                self.pkg("uninstall '*'")

                # test that solver picks up on impossible cases
                self.pkg("install -v --reject B --reject C A", exit=1)

                # test that publisher matching works
                self.pkg("install bogus")
                self.pkg("list bogus")
                self.pkg("install --reject B --reject 'pkg://contrib/*' A")

                # verify that matching accounts for reject.
                self.pkg("uninstall '*'")
                self.pkg("install -v --reject A A", exit=1)
                self.pkg("install -v --reject 'idr*' --reject 'bogus*' "
                    "--reject B '*'")
                self.pkg("list 'idr*' 'bogus*' B", exit=1)
                self.pkg("list A C incorp kernel no-idrs")

        def test_exact_install(self):
                """Test that the --reject option performs as expected."""

                self.image_create(self.rurl, prefix="")

                # test basic usage of --reject
                self.pkg("exact-install --reject B A")
                self.pkg("list A C")
                self.pkg("uninstall '*'")

                # test swapping XOR'd pkgs B & C.
                self.pkg("install B")
                self.pkg("install A")
                self.pkg("list A B")
                self.pkg("exact-install --reject B A")
                self.pkg("list A C")
                self.pkg("list B", exit=1)
                self.pkg("uninstall '*'")

                # test that solver picks up on impossible cases fails
                self.pkg("exact-install -v --reject B --reject C A", exit=1)

                # test that publisher matching works.
                self.pkg("install bogus")
                self.pkg("list bogus")
                self.pkg("exact-install --reject B --reject "
                    "'pkg://contrib/*' A")
                self.pkg("uninstall '*'")

                # verify that matching accounts for reject with --exact option.
                self.pkg("exact-install -v --reject A A", exit=1)
                self.pkg("exact-install -v --reject 'idr*' --reject 'bogus*' "
                    "--reject B '*'")
                self.pkg("list 'idr*' 'bogus*' B", exit=1)
                self.pkg("list A C incorp kernel no-idrs")

        def test_idr(self):
                self.image_create(self.rurl)
                # install kernel pkg; remember version so we can reinstall it later
                self.pkg("install no-idrs")
                self.pkg("install -v kernel@1.0,5.11-0.1")
                self.pkg("list -Hv kernel@1.0,5.11-0.1 | /usr/bin/awk '{print $1}'")
                kernel_fmri = self.output
                # upgrade to next version w/o encountering idrs
                self.pkg("update -v");
                self.pkg("list kernel@1.0,5.11-0.2")
                self.pkg("list")

                # try installing idr1; testing wild card support as well
                self.pkg("uninstall no-idrs")
                self.pkg("install --reject 'k*' --reject 'i*'  no-idrs")
                self.pkg("install -v kernel@1.0,5.11-0.1")
                self.pkg("install -v --reject no-idrs idr1_entitlement")
                self.pkg("install -v idr1@1.0,5.11-0.1.1.0")
                self.pkg("update -v --reject idr2")
                self.pkg("list idr1@1.0,5.11-0.1.1.1")

                # switch to idr2, which affects same package
                self.pkg("install -v --reject idr1 --reject 'idr1_*' idr2 idr2_entitlement")

                # switch back to base version of kernel
                self.pkg("update -v --reject idr2 --reject 'idr2_*' {0}".format(kernel_fmri))

                # reinstall idr1, then update to version 2 of base kernel
                self.pkg("install -v idr1@1.0,5.11-0.1.1.0 idr1_entitlement")
                self.pkg("list kernel@1.0,5.11-0.1.1.0")
                # Wildcards are purposefully used here for both patterns to
                # ensure pattern matching works as expected for update.
                self.pkg("update -v --reject 'idr1*' '*incorp@1.0-0.2'")
                self.pkg("list  kernel@1.0,5.11-0.2")

        def test_idr_removal(self):
                """IDR removal with pkg actuators."""
                self.image_create(self.rurl)
                self.pkg("install no-idrs")
                self.pkg("install -v kernelX@1.0,5.11-0.1")
                self.pkg("list kernelX@1.0,5.11-0.1")

                # try installing idr
                self.pkg("install -v --reject no-idrs idr1_entitlement")
                self.pkg("install -v idrX@1.0,5.11-0.1.1.0")
                # check if IDR pkgs got installed
                self.pkg("list idrX@1.0,5.11-0.1.1.0")
                self.pkg("list kernelX@1.0,5.11-0.1.1.0")

                # uninstall IDR
                self.pkg("uninstall -v idrX@1.0,5.11-0.1.1.0")
                self.pkg("list kernelX@1.0,5.11-0.1")

                # try with reject
                self.pkg("install -v idrX@1.0,5.11-0.1.1.0")
                self.pkg("list idrX@1.0,5.11-0.1.1.0")
                self.pkg("list kernelX@1.0,5.11-0.1.1.0")
                self.pkg("install --reject idrX B")
                self.pkg("list kernelX@1.0,5.11-0.1")

        def test_update(self):
                self.image_create(self.rurl)
                # Test update reject without wildcards.
                self.pkg("install  kernel@1.0,5.11-0.1.1.0 A@1.0,5.11-0")
                self.pkg("update -v --reject A")
                self.pkg("list A", exit=1)
                self.pkg("verify")

                # Reinstall kernel package, install A, and test update again using
                # wildcards.
                self.pkg("uninstall '*'")
                self.pkg("install kernel@1.0,5.11-0.1.1.0")
                self.pkg("list kernel@1.0,5.11-0.1.1.0")
                self.pkg("install A@1.0,5.11-0")
                self.pkg("update -v --reject A '*'")
                self.pkg("list A", exit=1)
                self.pkg("list kernel@1.0,5.11-0.1.1.1")
                self.pkg("verify")


class TestPkgInstallAmbiguousPatterns(pkg5unittest.SingleDepotTestCase):

        # An "ambiguous" package name pattern is one which, because of the
        # pattern matching rules, might refer to more than one package.  This
        # may be as obvious as the pattern "SUNW*", but also like the pattern
        # "foo", where "foo" and "a/foo" both exist in the catalog.

        afoo10 = """
            open a/foo@1.0,5.11-0
            close """

        bfoo10 = """
            open b/foo@1.0,5.11-0
            close """

        bar10 = """
            open bar@1.0,5.11-0
            close """

        foo10 = """
            open foo@1.0,5.11-0
            close """

        foo11 = """
            open foo@1.1,5.11-0
            close """

        anotherfoo11 = """
            open another/foo@1.1,5.11-0
            close """

        depender10 = """
            open depender@1.0,5.11-0
            add depend type=require fmri=foo@1.0
            close """

        depender11 = """
            open depender@1.1,5.11-0
            add depend type=require fmri=foo@1.1
            close """

        def test_bug_4204(self):
                """Don't stack trace when printing a PlanCreationException with
                "multiple_matches" populated (on uninstall)."""

                self.pkgsend_bulk(self.rurl, (self.afoo10, self.bfoo10,
                    self.bar10))
                self.image_create(self.rurl)

                self.pkg("install foo", exit=1)
                self.pkg("install a/foo b/foo", exit=0)
                self.pkg("list")
                self.pkg("uninstall foo", exit=1)
                self.pkg("uninstall a/foo b/foo", exit=0)

        def test_bug_6874(self):
                """Don't stack trace when printing a PlanCreationException with
                "multiple_matches" populated (on install and update)."""

                self.pkgsend_bulk(self.rurl, (self.afoo10, self.bfoo10))
                self.image_create(self.rurl)

                self.pkg("install foo", exit=1)

        def test_ambiguous_pattern_install(self):
                """An update should never get confused about an existing
                package being part of an ambiguous set of package names."""

                self.pkgsend_bulk(self.rurl, self.foo10)

                self.image_create(self.rurl)
                self.pkg("install foo")

                self.pkgsend_bulk(self.rurl, self.anotherfoo11)
                self.pkg("refresh")
                self.pkg("update -v", exit=4)

        def test_ambiguous_pattern_depend(self):
                """A dependency on a package should pull in an exact name
                match."""

                self.ambiguous_pattern_depend_helper("install")
                self.ambiguous_pattern_depend_helper("exact-install")

        def ambiguous_pattern_depend_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.depender10, self.foo10))

                self.image_create(self.rurl)
                self.pkg("{0} depender".format(install_cmd))

                self.pkgsend_bulk(self.rurl, (self.foo11, self.anotherfoo11,
                    self.depender11))
                self.pkg("refresh")

                self.pkg("{0} depender".format(install_cmd))

                # Make sure that we didn't get other/foo from the dependency.
                self.pkg("list another/foo", exit=1)

        def test_non_ambiguous_fragment(self):
                """We should be able to refer to a package by its "basename", if
                that component is unique."""

                self.non_ambiguous_fragment_helper("install")
                self.non_ambiguous_fragment_helper("exact-install")

        def non_ambiguous_fragment_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, self.anotherfoo11)
                self.image_create(self.rurl)

                # Right now, this is not exact, but still unambiguous
                self.pkg("{0} foo".format(install_cmd))

                # Create ambiguity
                self.pkgsend_bulk(self.rurl, self.foo11)
                self.pkg("refresh")

                # This is unambiguous, should succeed
                self.pkg("{0} pkg:/foo".format(install_cmd))

                # This is now ambiguous, should fail
                self.pkg("{0} foo".format(install_cmd), exit=1)
                self.pkgrepo("remove -s {0} pkg:/foo@1.1".format(self.rurl ))


class TestPkgInstallOverlappingPatterns(pkg5unittest.SingleDepotTestCase):

        a_1 = """
            open a@1.0,5.11-0
            close """

        pub2_a_1 = """
            open pkg://pub2/a@1.0,5.11-0
            close """

        a_11 = """
            open a@1.1,5.11-0
            close """

        a_2 = """
            open a@2.0,5.11-0
            close """

        pub2_a_2 = """
            open pkg://pub2/a@2.0,5.11-0
            close """

        a_3 = """
            open a@3.0,5.11-0
            close """

        aa_1 = """
            open aa@1.0,5.11-0
            close """

        afoo_1 = """
            open a/foo@1.0,5.11-0
            close """

        bfoo_1 = """
            open b/foo@1.0,5.11-0
            close """

        fooa_1 = """
            open foo/a@1.0,5.11-0
            close """

        foob_1 = """
            open foo/b@1.0,5.11-0
            close """

        def test_overlapping_one_package_available(self):
                self.pkgsend_bulk(self.rurl, self.a_1)
                api_inst = self.image_create(self.rurl)

                self._api_install(api_inst, ["a@1", "a@1"], noexecute=True)
                self._api_install(api_inst, ["a@1", "a@1.0"], noexecute=True)
                self._api_install(api_inst, ["a@1", "pkg://test/a@1"],
                    noexecute=True)
                self._api_install(api_inst, ["a*@1", "pkg:/*a@1"],
                    noexecute=True)
                self._api_install(api_inst, ["a*@1", "a@1"], noexecute=True)
                self._api_install(api_inst, ["a@1", "pkg://test/a*@1"],
                    noexecute=True)
                # This fails because a*@2 matches no patterns on its own.
                self.pkg("install -n 'a*@2' 'a@1'", exit=1)

        def test_overlapping_conflicting_versions_no_wildcard_match(self):
                self.pkgsend_bulk(self.rurl, self.a_1 + self.a_2)
                api_inst = self.image_create(self.rurl)

                self.pkg("install -n a@1 a@2", exit=1)
                self.pkg("install -n a@2 pkg://test/a@1", exit=1)
                self.pkg("install -n 'a*@2' 'pkg:/*a@1'", exit=1)

                # This is allowed because a*@1 matches published packages, even
                # though the packages it matches aren't installed in the image.
                self._api_install(api_inst, ["a*@1", "a@2"])
                self.pkg("list a@2")
                self._api_uninstall(api_inst, ["a"])

                self._api_install(api_inst, ["a@1", "pkg://test/a*@2"])
                self.pkg("list a@1")
                self._api_uninstall(api_inst, ["a"])

                self.pkgsend_bulk(self.rurl, self.a_3)
                self._api_install(api_inst, ["a*@1", "*a@2", "a@3"])
                self.pkg("list a@3")
                self._api_uninstall(api_inst, ["a"])

                self._api_install(api_inst, ["a*@1", "*a@2", "a@latest"])
                self.pkg("list a@3")
                self._api_uninstall(api_inst, ["a"])

                self.pkgsend_bulk(self.rurl, self.a_11)
                self.pkg("install a@1.1 a@1.0", exit=1)
                self._api_install(api_inst, ["a@1", "a@1.0", "a*@1.1"])
                self.pkg("list a@1.0")
                self._api_uninstall(api_inst, ["a"])

                self._api_install(api_inst, ["*", "a@1.0"])
                self.pkg("list a@1.0")
                self._api_uninstall(api_inst, ["a"])

        def test_overlapping_multiple_packages(self):
                self.pkgsend_bulk(self.rurl, self.a_1 + self.a_2 + self.aa_1 +
                    self.afoo_1 + self.bfoo_1 + self.fooa_1 + self.foob_1)
                api_inst = self.image_create(self.rurl)

                self.pkg("install '*a@1' 'a*@2'", exit=1)

                self._api_install(api_inst, ["a*@1", "a@2"])
                self.pkg("list -Hv")
                self.assertEqual(len(self.output.splitlines()), 3)
                self.assertTrue("a@2" in self.output)
                self._api_uninstall(api_inst, ["a", "aa", "a/foo"])

                self._api_install(api_inst, ["/a@1", "a*@2", "*foo*@1"])
                self.pkg("list -Hv")
                self.assertEqual(len(self.output.splitlines()), 5)
                self.assertTrue("a@1" in self.output)
                self._api_uninstall(api_inst,
                    ["/a", "a/foo", "b/foo", "foo/a", "foo/b"])

        def test_overlapping_multiple_publishers(self):
                self.pkgsend_bulk(self.rurl, self.a_1 + self.pub2_a_2)
                api_inst = self.image_create(self.rurl)

                self._api_install(api_inst, ["a*@1", "pkg://pub2/a@2"],
                    noexecute=True)
                self._api_install(api_inst, ["a@1", "pkg://pub2/a*@2"],
                    noexecute=True)
                self._api_install(api_inst, ["a@1", "pkg://pub2/*@2"],
                    noexecute=True)
                self.pkg("install -n 'pkg://test/a*@1' 'pkg://pub2/*a@2'",
                    exit=1)
                self.pkg("install -n 'pkg://test/a@1' 'pkg://pub2/a@2'",
                    exit=1)
                self.pkg("install -n 'a@1' 'pkg://pub2/a@2'", exit=1)

                self.pkgsend_bulk(self.rurl, self.pub2_a_1)
                self._api_install(api_inst, ["a@1", "pkg://pub2/a@1"])
                self.pkg("list -Hv 'pkg://pub2/*'")
                self.assertEqual(len(self.output.splitlines()), 1)
                self.assertTrue("a@1" in self.output)
                self._api_uninstall(api_inst, ["a"])

                self._api_install(api_inst, ["a@1", "pkg://test/a@1"])
                self.pkg("list -Hv 'pkg://test/*'")
                self.assertEqual(len(self.output.splitlines()), 1)
                self.assertTrue("a@1" in self.output)
                self._api_uninstall(api_inst, ["a"])

                self._api_install(api_inst, ["a*@1", "pkg://pub2/*@2"])
                self.pkg("list -Hv 'pkg://pub2/*'")
                self.assertEqual(len(self.output.splitlines()), 1)
                self.assertTrue("a@2" in self.output)
                self._api_uninstall(api_inst, ["a"])

                self._api_install(api_inst,
                    ["pkg://test/a@1", "pkg://pub2/*@2"])
                self.pkg("list -Hv 'pkg://test/*'")
                self.assertEqual(len(self.output.splitlines()), 1)
                self.assertTrue("a@1" in self.output)
                self._api_uninstall(api_inst, ["a"])

                # This intentionally doesn't use api_install to check for
                # special handling of '*' in client.py.
                self.pkg("install '*' 'pkg://pub2/*@2'")
                self.pkg("list -Hv 'pkg://pub2/*'")
                self.assertEqual(len(self.output.splitlines()), 1)
                self.assertTrue("a@2" in self.output)
                self._api_uninstall(api_inst, ["a"])


class TestPkgInstallCircularDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg10 = """
            open pkg1@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg2
            close
        """

        pkg20 = """
            open pkg2@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg3
            close
        """

        pkg30 = """
            open pkg3@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg1
            close
        """


        pkg11 = """
            open pkg1@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg2@1.1
            close
        """

        pkg21 = """
            open pkg2@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg3@1.1
            close
        """

        pkg31 = """
            open pkg3@1.1,5.11-0
            add depend type=require fmri=pkg:/pkg1@1.1
            close
        """

        def test_unanchored_circular_dependencies(self):
                """ check to make sure we can install or exact-install
                circular dependencies w/o versions
                """

                self.unanchored_circular_dependencies_helper("install")
                self.unanchored_circular_dependencies_helper("exact-install")

        def unanchored_circular_dependencies_helper(self, install_cmd):
                # Send 1.0 versions of packages.
                self.pkgsend_bulk(self.rurl, (self.pkg10, self.pkg20,
                    self.pkg30))

                self.image_create(self.rurl)
                self.pkg("{0} pkg1".format(install_cmd))
                self.pkg("list")
                self.pkg("verify -v")

        def test_anchored_circular_dependencies(self):
                """ check to make sure we can install or exact-install
                circular dependencies w/ versions
                """

                self.anchored_circular_dependencies_helper("install")
                self.unanchored_circular_dependencies_helper("exact-install")

        def anchored_circular_dependencies_helper(self, install_cmd):
                # Send 1.1 versions of packages.
                self.pkgsend_bulk(self.rurl, (self.pkg11, self.pkg21,
                    self.pkg31))

                self.image_create(self.rurl)
                self.pkg("{0} pkg1".format(install_cmd))
                self.pkg("list")
                self.pkg("verify -v")


class TestPkgInstallUpdateSolverOutput(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        octo10 = """
            open octo@1.0,5.11-0
            close
        """

        octo20 = """
            open octo@2.0,5.11-0
            close
        """

        incorp = """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/octo@2.0
            close
        """

        def test_output_two_issues(self):
                """ ^^^ hard to find a good name for this, it tests for bug
                21130996.
                In case one pkg triggers two or more issues, one of which is not
                considered print-worthy, we wouldn't print anything at all."""

                self.pkgsend_bulk(self.rurl,
                    (self.incorp, self.octo10, self.octo20))
                self.image_create(self.rurl)

                self.pkg("install incorp octo@2")
                self.pkg("install -v octo@1", exit=1)

                # Check that the root cause for the issue is shown;
                # the incorporation does not allow the older version.
                self.assertTrue("incorp@1.0" in self.errout,
                    "Excluding incorporation not shown in solver error.")
                # Check that the notice about a newer version already installed
                # is ommited (it's not relevant).
                self.assertFalse("octo@2.0" in self.errout,
                    "Newer version should not be shown in solver error.")


class TestPkgInstallUpgrade(_TestHelper, pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True
        need_ro_data = True

        incorp10 = """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@1.0
            add depend type=incorporate fmri=pkg:/bronze@1.0
            close
        """

        incorp20 = """
            open incorp@2.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        incorp30 = """
            open incorp@3.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            close
        """

        incorpA = """
            open incorpA@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@1.0
            add depend type=incorporate fmri=pkg:/bronze@1.0
            close
        """

        incorpB =  """
            open incorpB@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        iridium10 = """
            open iridium@1.0,5.11-0
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """
        amber10 = """
            open amber@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add dir mode=0755 owner=root group=bin path=/etc
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add link path=/lib/libc.symlink target=/lib/libc.so.1
            add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
            add file tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
            add file tmp/amber2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright1 license=copyright_ä
            close
        """

        brass10 = """
            open brass@1.0,5.11-0
            add depend fmri=pkg:/bronze type=require
            close
        """

        bronze10 = """
            open bronze@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/bronze2
            add file tmp/bronzeA1 mode=0444 owner=root group=bin path=/A/B/C/D/E/F/bronzeA1
            add depend fmri=pkg:/amber@1.0 type=require
            add license tmp/copyright2 license=copyright
            close
        """

        amber20 = """
            open amber@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/usr
            add dir mode=0755 owner=root group=bin path=/usr/bin
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add link path=/lib/libc.symlink target=/lib/libc.so.1
            add hardlink path=/lib/libc.amber target=/lib/libc.bronze
            add hardlink path=/lib/libc.hardlink target=/lib/libc.so.1
            add file tmp/amber1 mode=0444 owner=root group=bin path=/etc/amber1
            add file tmp/amber2 mode=0444 owner=root group=bin path=/etc/bronze2
            add depend fmri=pkg:/bronze@2.0 type=require
            add license tmp/copyright2 license=copyright
            close
        """

        bronze20 = """
            open bronze@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """

        bronze30 = """
            open bronze@3.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/etc
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/sh mode=0555 owner=root group=bin path=/usr/bin/sh
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.bronze
            add link path=/usr/bin/jsh target=./sh
            add hardlink path=/lib/libc.bronze2.0.hardlink target=/lib/libc.so.1
            add file tmp/bronze1 mode=0444 owner=root group=bin path=/etc/bronze1
            add file tmp/bronze2 mode=0444 owner=root group=bin path=/etc/amber2
            add license tmp/copyright3 license=copyright
            add file tmp/bronzeA2 mode=0444 owner=root group=bin path=/A1/B2/C3/D4/E5/F6/bronzeA2
            add depend fmri=pkg:/amber@2.0 type=require
            close
        """


        gold10 = """
            open gold@1.0,5.11-0
            add file tmp/gold-passwd1 mode=0644 owner=root group=bin path=etc/passwd preserve=true
            add file tmp/gold-group mode=0644 owner=root group=bin path=etc/group preserve=true
            add file tmp/gold-shadow mode=0600 owner=root group=bin path=etc/shadow preserve=true
            add file tmp/gold-ftpusers mode=0644 owner=root group=bin path=etc/ftpd/ftpusers preserve=true
            add file tmp/gold-silly mode=0644 owner=root group=bin path=etc/silly
            add file tmp/gold-silly mode=0644 owner=root group=bin path=etc/silly2
            close
        """

        gold20 = """
            open gold@2.0,5.11-0
            add file tmp/config2 mode=0644 owner=root group=bin path=etc/config2 original_name="gold:etc/passwd" preserve=true
            close
        """

        gold30 = """
            open gold@3.0,5.11-0
            close
        """

        golduser10 = """
            open golduser@1.0
            add user username=Kermit group=adm home-dir=/export/home/Kermit
            close
        """

        golduser20 = """
            open golduser@2.0
            close
        """

        silver10  = """
            open silver@1.0,5.11-0
            close
        """

        silver20  = """
            open silver@2.0,5.11-0
            add file tmp/gold-passwd2 mode=0644 owner=root group=bin path=etc/passwd original_name="gold:etc/passwd" preserve=true
            add file tmp/gold-group mode=0644 owner=root group=bin path=etc/group original_name="gold:etc/group" preserve=true
            add file tmp/gold-shadow mode=0600 owner=root group=bin path=etc/shadow original_name="gold:etc/shadow" preserve=true
            add file tmp/gold-ftpusers mode=0644 owner=root group=bin path=etc/ftpd/ftpusers original_name="gold:etc/ftpd/ftpusers" preserve=true
            add file tmp/gold-silly mode=0644 owner=root group=bin path=etc/silly
            add file tmp/silver-silly mode=0644 owner=root group=bin path=etc/silly2
            close
        """
        silver30  = """
            open silver@3.0,5.11-0
            add file tmp/config2 mode=0644 owner=root group=bin path=etc/config2 original_name="gold:etc/passwd" preserve=true
            close
        """

        silveruser = """
            open silveruser@1.0
            add user username=Kermit group=adm home-dir=/export/home/Kermit
            close
        """


        iron10 = """
            open iron@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file tmp/config1 mode=0644 owner=root group=bin path=etc/foo
            add hardlink path=etc/foo.link target=foo
            add license tmp/copyright1 license=copyright
            close
        """
        iron20 = """
            open iron@2.0,5.11-0
            add dir mode=0755 owner=root group=bin path=etc
            add file tmp/config2 mode=0644 owner=root group=bin path=etc/foo
            add hardlink path=etc/foo.link target=foo
            add license tmp/copyright2 license=copyright
            close
        """

        concorp10 = """
            open concorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/amber@2.0
            add depend type=incorporate fmri=pkg:/bronze@2.0
            close
        """

        dricon1 = """
            open dricon@1
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/dricon_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            close
        """

        dricon2 = """
            open dricon@2
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add driver name=zigit alias=pci8086,1234
            close
        """

        dricon3 = """
            open dricon@3
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add driver name=zigit alias=pci8086,1234
            add driver name=figit alias=pci8086,1234
            close
        """

        dripol1 = """
            open dripol@1
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit policy="read_priv_set=net_rawaccess write_priv_set=net_rawaccess tpd_member=true"
            close
        """

        dripol2 = """
            open dripol@2
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit
            close
        """

        dripol3 = """
            open dripol@3
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit policy="tpd_member=true"
            close
        """

        dripol4 = """
            open dripol@4
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit
            close
        """

        dripol5 = """
            open dripol@5
            add dir path=var mode=755 owner=root group=root
            add dir path=var/run mode=755 owner=root group=root
            add dir mode=0755 owner=root group=root path=system
            add dir mode=0755 owner=root group=root path=system/volatile
            add dir path=/tmp mode=755 owner=root group=root
            add dir path=/etc mode=755 owner=root group=root
            add dir path=/etc/security mode=755 owner=root group=root
            add file tmp/dricon2_da path=/etc/driver_aliases mode=644 owner=root group=sys preserve=true
            add file tmp/dricon_n2m path=/etc/name_to_major mode=644 owner=root group=sys preserve=true
            add file tmp/dripol1_dp path=/etc/security/device_policy mode=644 owner=root group=sys preserve=true
            add driver name=frigit perms="node1 0666 root sys" policy="node1 read_priv_set=all write_priv_set=all tpd_member=true"
            close
        """

        liveroot10 = """
            open liveroot@1.0
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/liveroot1 path=/etc/liveroot mode=644 owner=root group=sys reboot-needed=true
            close
        """
        liveroot20 = """
            open liveroot@2.0
            add dir path=/etc mode=755 owner=root group=root
            add file tmp/liveroot2 path=/etc/liveroot mode=644 owner=root group=sys reboot-needed=true
            close
        """

        renameold1 = """
            open renold@1.0
            add file tmp/renold1 path=testme mode=0644 owner=root group=root preserve=renameold
            close
        """

        renameold2 = """
            open renold@2.0
            add file tmp/renold1 path=testme mode=0640 owner=root group=root preserve=renameold
            close
        """

        renameold3 = """
            open renold@3.0
            add file tmp/renold3 path=testme mode=0644 owner=root group=root preserve=renameold
            close
        """

        renamenew1 = """
            open rennew@1.0
            add file tmp/rennew1 path=testme mode=0644 owner=root group=root preserve=renamenew
            close
        """

        renamenew2 = """
            open rennew@2.0
            add file tmp/rennew1 path=testme mode=0640 owner=root group=root preserve=renamenew
            close
        """

        renamenew3 = """
            open rennew@3.0
            add file tmp/rennew3 path=testme mode=0644 owner=root group=root preserve=renamenew
            close
        """

        preserve1 = """
            open preserve@1.0
            add file tmp/preserve1 path=testme mode=0644 owner=root group=root preserve=true
            close
        """

        preserve2 = """
            open preserve@2.0
            add file tmp/preserve1 path=testme mode=0640 owner=root group=root preserve=true
            close
        """

        preserve3 = """
            open preserve@3.0
            add file tmp/preserve3 path=testme mode=0644 owner=root group=root preserve=true
            close
        """

        preslegacy = """
            open preslegacy@1.0
            add file tmp/preserve1 path=testme mode=0644 owner=root group=root preserve=true
            close
            open preslegacy@2.0
            add file tmp/preserve2 path=testme mode=0444 owner=root group=root preserve=legacy
            close
            open preslegacy@3.0
            add file tmp/preserve3 path=testme mode=0444 owner=root group=root preserve=legacy
            close
        """

        renpreslegacy = """
            open orig_preslegacy@1.0
            add file tmp/preserve1 path=testme mode=0644 owner=root group=root preserve=true
            close
            open orig_preslegacy@1.1
            add set pkg.renamed=true
            add depend type=require fmri=ren_preslegacy@2.0
            close
            open ren_preslegacy@2.0
            add file tmp/preserve2 path=newme mode=0444 owner=root group=root preserve=legacy original_name=orig_preslegacy:testme
            close
        """

        presabandon = """
            open presabandon@1.0
            add file tmp/preserve1 path=testme mode=0444 owner=root group=root preserve=true
            close
            open presabandon@2.0
            add file tmp/preserve1 path=testme mode=0644  owner=root group=root preserve=abandon
            close
            open presabandon@3.0
            add file tmp/preserve3 path=testme mode=0444  owner=root group=root preserve=abandon
            close
            open presabandon@4.0
            add file tmp/preserve3 path=testme mode=0644  owner=root group=root preserve=true
            close
        """

        presinstallonly = """
            open presinstallonly@0.0
            close
            open presinstallonly@1.0
            add file tmp/preserve1 path=testme mode=0444 owner=root group=root preserve=true
            close
            open presinstallonly@2.0
            add file tmp/preserve1 path=testme mode=0644  owner=root group=root preserve=install-only
            close
            open presinstallonly@3.0
            add file tmp/preserve3 path=testme mode=0444  owner=root group=root preserve=install-only
            close
            open presinstallonly@4.0
            add file tmp/preserve3 path=testme mode=0644  owner=root group=root preserve=true
            close
        """

        renpreserve = """
            open orig_pkg@1.0
            add file tmp/preserve1 path=foo1 mode=0644 owner=root group=root preserve=true
            add file tmp/bronze1 path=bronze1 mode=0644 owner=root group=root preserve=true
            close
            open orig_pkg@1.1
            add set pkg.renamed=true
            add depend type=require fmri=new_pkg@1.0
            close
            open new_pkg@2.0
            add file tmp/foo2 path=foo2 mode=0644 owner=root group=root original_name=orig_pkg:foo1 preserve=true
            add file tmp/bronze1 path=bronze1 mode=0644 owner=root group=root preserve=true
            close
        """

        linkpreserve = """
            open linkpreserve@1.0
            add file tmp/preserve1 path=etc/ssh/sshd_config mode=0644 owner=root group=root preserve=true
            close
            open linkpreserve@2.0
            add file tmp/preserve2 path=etc/sunssh/sshd_config mode=0644 owner=root group=root preserve=true original_name=linkpreserve:etc/ssh/sshd_config
            add link path=etc/ssh/sshd_config target=../sunssh/sshd_config
            close """

        salvage = """
            open salvage@1.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/mail mode=755 owner=root group=root
            add dir path=var/log mode=755 owner=root group=root
            add dir path=var/noodles mode=755 owner=root group=root
            add dir path=var/persistent mode=755 owner=root group=root
            close
            open salvage@2.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/.migrate-to-shared mode=755 owner=root group=root
            add dir path=var/.migrate-to-shared/mail salvage-from=var/mail mode=755 owner=root group=root
            add dir path=var/.migrate-to-shared/log salvage-from=var/log mode=755 owner=root group=root
            add dir path=var/spaghetti mode=755 owner=root group=root
            add dir path=var/persistent mode=755 owner=root group=root salvage-from=var/noodles
            close
            open salvage@3.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/.migrate-to-shared mode=755 owner=root group=root
            add dir path=var/.migrate-to-shared/mail salvage-from=var/mail mode=755 owner=root group=root
            add dir path=var/.migrate-to-shared/log salvage-from=var/log mode=755 owner=root group=root
            add dir path=var/persistent mode=755 owner=root group=root salvage-from=var/noodles salvage-from=var/spaghetti
            close
        """

        salvage_special = """
            open salvage-special@1.0
            add dir path=salvage mode=755 owner=root group=root
            close
        """

        salvage_nested = """
            open salvage-nested@1.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/mail mode=755 owner=root group=root
            add dir path=var/user mode=755 owner=root group=root
            add dir path=var/user/evsuser mode=755 owner=root group=root
            add dir path=var/user/evsuser/.ssh mode=755 owner=root group=root
            add file tmp/auth1 path=var/user/evsuser/.ssh/authorized_keys \
                owner=root group=root mode=644 preserve=true
            close
            open salvage-nested@1.1
            add dir path=var mode=755 owner=root group=root
            add dir path=var/mail mode=755 owner=root group=root
            add dir path=var/user mode=755 owner=root group=root
            add dir path=var/user/evsuser mode=755 owner=root group=root
            add dir path=var/user/evsuser/.ssh mode=755 owner=root group=root
            add file tmp/auth1 path=var/user/evsuser/.ssh/authorized_keys \
                owner=root group=root mode=644 preserve=abandon
            close
            open salvage-nested@2.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/.migrate mode=755 owner=root group=root
            add dir path=var/.migrate/mail salvage-from=var/mail mode=755 \
                owner=root group=root
            add dir path=var/.migrate/user salvage-from=var/user mode=755 \
                owner=root group=root
            add dir path=var/.migrate/user/evsuser salvage-from=var/user/evsuser \
                mode=755 owner=root group=root
            add dir path=var/.migrate/user/evsuser/.ssh \
                salvage-from=var/user/evsuser/.ssh mode=755 owner=root group=root
            close
            open salvage-nested@3.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/.migrate mode=755 owner=root group=root
            add dir path=var/.migrate/user salvage-from=var/user mode=755 \
                owner=root group=root
            open salvage-nested@4.0
            add dir path=var mode=755 owner=root group=root
            add dir path=var/.migrate mode=755 owner=root group=root
            add dir path=var/.migrate/user salvage-from=var/user mode=755 \
                owner=root group=root
            add dir path=var/.migrate/evsuser salvage-from=var/user/evsuser \
                mode=755 owner=root group=root
            close
        """

        dumdir10 = """
            open dumdir@1.0
            add dir path=etc mode=0755 owner=root group=bin
            add file tmp/amber1 mode=0755 owner=root group=bin path=etc/amber1
            close
        """

        dumdir20 = """
            open dumdir@2.0
            add dir path=etc mode=0700 owner=root group=bin
            add file tmp/amber1 mode=0444 owner=root group=bin path=etc/amber1
            close
        """

        dumdir30 = """
            open dumdir@3.0
            add dir path=etc mode=0700 owner=bin group=bin
            add file tmp/amber1 mode=0400 owner=root group=bin path=etc/amber1
            close
        """

        elfhash10 = """
            open elfhash@1.0
            add file ro_data/elftest.so.1 mode=0755 owner=root group=bin path=bin/true
            close
        """

        elfhash20 = """
            open elfhash@2.0
            add file ro_data/elftest.so.1 mode=0755 owner=root group=bin path=bin/true
            close
        """

        elfhash30 = """
            open elfhash@3.0
            add file ro_data/elftest.so.2 mode=0755 owner=root group=bin path=bin/true
            close
        """

        misc_files1 = [
            "tmp/amber1", "tmp/amber2", "tmp/bronzeA1",  "tmp/bronzeA2",
            "tmp/bronze1", "tmp/bronze2",
            "tmp/copyright1", "tmp/copyright2",
            "tmp/copyright3", "tmp/copyright4",
            "tmp/libc.so.1", "tmp/sh", "tmp/config1", "tmp/config2",
            "tmp/gold-passwd1", "tmp/gold-passwd2", "tmp/gold-group",
            "tmp/gold-shadow", "tmp/gold-ftpusers", "tmp/gold-silly",
            "tmp/silver-silly", "tmp/preserve1", "tmp/preserve2",
            "tmp/preserve3", "tmp/renold1", "tmp/renold3", "tmp/rennew1",
            "tmp/rennew3", "tmp/liveroot1", "tmp/liveroot2", "tmp/foo2",
            "tmp/auth1"
        ]

        misc_files2 = {
            "tmp/dricon_da": """\
wigit "pci8086,1234"
wigit "pci8086,4321"
# someother "pci8086,1234"
foobar "pci8086,9999"
""",
            "tmp/dricon2_da": """\
zigit "pci8086,1234"
wigit "pci8086,4321"
# someother "pci8086,1234"
foobar "pci8086,9999"
""",
            "tmp/dricon_n2m": """\
wigit 1
foobar 2
""",
            "tmp/dripol1_dp": """\
*               read_priv_set=none              write_priv_set=none
""",
            "tmp/gold-passwd1": """\
root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
""",
            "tmp/gold-passwd2": """\
root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
bogus:x:10001:10001:Bogus User:/:
""",
            "tmp/gold-group": """\
root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
""",
            "tmp/gold-shadow": """\
root:9EIfTNBp9elws:13817::::::
daemon:NP:6445::::::
bin:NP:6445::::::
sys:NP:6445::::::
adm:NP:6445::::::
""",
            "tmp/gold-ftpusers": """\
root
bin
sys
adm
""",
        }

        cat_data = " "

        foo10 = """
            open foo@1.0,5.11-0
            close """

        only_attr10 = """
            open only_attr@1.0,5.11-0
            add set name=foo value=bar
            close """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files1)
                self.make_misc_files(self.misc_files2)

        def __salvage_file_contains(self, sroot, fprefix, entry):
                salvaged = [
                    n for n in os.listdir(sroot)
                    if n.startswith(fprefix + "-")
                ]

                sfile = os.path.join(sroot, salvaged[0])
                with open(sfile, "r") as f:
                        found = [l.strip() for l in f if entry in l]
                        self.assertEqual(found, [entry])

        def test_incorp_install(self):
                """Make sure we don't round up packages we specify on
                install"""

                first_bronze = self.pkgsend_bulk(self.rurl, self.bronze20)[0]
                self.pkgsend_bulk(self.rurl, (self.incorp20, self.amber10,
                    self.bronze10, self.amber20, self.bronze20))

                # create image
                self.image_create(self.rurl)
                # install incorp2
                self.pkg("install incorp@2.0")
                # try to install version 1
                self.pkg("install bronze@1.0", exit=1)
                # install earliest version bronze@2.0
                self.pkg("install {0}".format(first_bronze))
                self.pkg("list -v {0}".format(first_bronze))
                self.pkg("install bronze@2.0")

        def test_content_hash_install(self):
                """Test that pkg install/upgrade works fine for files with
                content-hash attributes."""

                plist = self.pkgsend_bulk(self.rurl, (self.elfhash10,
                    self.elfhash20))
                elf1 = plist[0]
                elf2 = plist[1]
                f1 = fmri.PkgFmri(elf1, None)
                f2 = fmri.PkgFmri(elf2, None)
                repo = self.get_repo(self.dc.get_repodir())
                mpath1 = repo.manifest(f1)
                mpath2 = repo.manifest(f2)

                # load manifest, change content-hash attr and store back
                # to disk
                mani = manifest.Manifest()
                mani.set_content(pathname=mpath1)
                mani2 = manifest.Manifest()
                mani2.set_content(pathname=mpath2)

                # Upgrade case: action that doesn't use pkg.content-hash upgrade
                # to action that uses pkg.content-hash.
                for a in mani.gen_actions():
                        if "bin/true" in str(a):
                                del a.attrs["pkg.content-hash"]
                mani.store(mpath1)
                # rebuild repo catalog since manifest digest changed
                repo.rebuild()

                self.image_create(self.rurl)
                # In our experiments, we want to compare content-hash attributes
                # instead of file hash, so we need to set the content policy
                # to be when-required so that it will check the content-hash
                # attributes; the default policy checks the file hash.
                self.pkg("set-property content-update-policy when-required")
                self.pkg("install -v elfhash@1.0")
                # should not see pkg.content-hash
                self.pkg("contents -m elfhash | grep pkg.content-hash", exit=1)
                self.pkg("update -vvv elfhash")
                # should update to the new hash attr name
                self.pkg("contents -m elfhash | grep pkg.content-hash")
                self.pkg("uninstall elfhash")

                # Upgrade case: action that uses SHA-2 hash upgrade to action
                # that uses SHA-3 hash.
                for a in mani.gen_actions():
                        if "bin/true" in str(a):
                                a.attrs["pkg.content-hash"] = "gelf:sha512t_256:abcd"
                mani.store(mpath1)
                repo.rebuild()

                for a in mani2.gen_actions():
                        if "bin/true" in str(a):
                                a.attrs["pkg.content-hash"] = ["gelf:sha3_384:wxyz"]
                mani2.store(mpath2)
                repo.rebuild()

                self.pkg("install -v elfhash@1.0")
                self.pkg("contents -m elfhash | grep gelf:sha512t_256")
                self.pkg("update -vvv elfhash")
                self.assertTrue("sha3_384" in self.output)
                self.pkg("contents -m elfhash | grep gelf:sha512t_256", exit=1)
                self.pkg("contents -m elfhash | grep gelf:sha3_384")
                self.pkg("uninstall elfhash")

                # Redo the test again with upgrading to action that uses both
                # hashes.
                for a in mani2.gen_actions():
                        if "bin/true" in str(a):
                                a.attrs["pkg.content-hash"] = \
                                    ["gelf:sha512t_256:abcd", "gelf:sha3_384:wxyz"]

                mani2.store(mpath2)
                repo.rebuild()

                self.pkg("install -v elfhash@1.0")
                self.pkg("contents -m elfhash | grep gelf:sha512t_256")
                self.pkg("update -vvv elfhash")
                # We don't add the new file to the upgrade process because
                # sha512t_256 is preferred...
                self.assertTrue("sha3_384" not in self.output)
                # ...but we still update the file's content-hash attributes.
                self.pkg("contents -m elfhash | grep gelf:sha512t_256")
                self.pkg("contents -m elfhash | grep gelf:sha3_384")
                self.pkg("uninstall elfhash")

                # Upgrade case: action that uses gelf extraction method upgrade
                # to action that uses file extraction method.
                for a in mani2.gen_actions():
                        if "bin/true" in str(a):
                                a.attrs["pkg.content-hash"] = ["file:sha512t_256:qrst"]

                mani2.store(mpath2)
                repo.rebuild()

                self.pkg("install -v elfhash@1.0")
                self.pkg("contents -m elfhash | grep gelf")
                self.pkg("update -vvv elfhash")
                self.assertTrue("file:sha512t_256" in self.output)
                self.pkg("contents -m elfhash | grep gelf", exit=1)
                self.pkg("contents -m elfhash | grep file")
                self.pkg("uninstall elfhash")

                # Redo the test again with upgrading to action uses both
                # methods.
                for a in mani2.gen_actions():
                        if "bin/true" in str(a):
                                a.attrs["pkg.content-hash"] = \
                                    ["gelf:sha512t_256:abcd", "file:sha512t_256:qrst"]

                mani2.store(mpath2)
                repo.rebuild()

                self.pkg("install -v elfhash@1.0")
                self.pkg("contents -m elfhash | grep gelf")
                # We don't add the new file to the upgrade process because
                # gelf is preferred...
                self.pkg("update -vvv elfhash")
                self.assertTrue("gelf" not in self.output)
                # ...but we still update the file's content-hash attributes.
                self.pkg("contents -m elfhash | grep gelf")
                self.pkg("contents -m elfhash | grep file")
                self.pkg("uninstall elfhash")

                # Upgrade case: action that doesn't use pkg.content-hash
                # upgrade to action that uses pkg.content-hash with action.hash
                # being changed. In this case, we are testing the most preferred
                # hash that is set on either new or old action, that is,
                # "pkg.content-hash". Since a higher-ranked digest exists on the
                # new action, but not the old, we must assume that the previous
                # digest should not be trusted, so we will update the file.

                def get_test_sum(fname=None):
                        """ Helper to get sha256 sum of installed test file."""
                        if fname is None:
                                fname = os.path.join(self.get_img_path(),
                                    "bin/true")
                        fsum, data = misc.get_data_digest(fname,
                            hash_func=hashlib.sha256)
                        return fsum

                # get the sha256 sums from the original files to distinguish
                # what actually got installed
                elf2sum = get_test_sum(fname=os.path.join(self.ro_data_root,
                    "elftest.so.2"))

                self.pkgsend_bulk(self.rurl, self.elfhash30)[0]
                for a in mani.gen_actions():
                        if "bin/true" in str(a):
                                del a.attrs["pkg.content-hash"]
                mani.store(mpath1)
                repo.rebuild()

                self.pkg("install elfhash@1.0")
                self.pkg("update -vvv elfhash@3.0")
                # The file should be updated...
                self.assertEqual(elf2sum, get_test_sum())
                self.pkg("contents -m elfhash | grep pkg.content-hash")

        def test_upgrade1(self):

                """ Upgrade torture test.
                    Send package amber@1.0, bronze1.0; install bronze1.0, which
                    should cause amber to also install.
                    Send 2.0 versions of packages which contains a lot of
                    complex transactions between amber and bronze, then do
                    an update, and try to check the results.
                """

                # Send 1.0 versions of packages.
                self.pkgsend_bulk(self.rurl, (self.incorp10, self.amber10,
                    self.bronze10))

                #
                # In version 2.0, several things happen:
                #
                # Amber and Bronze swap a file with each other in both
                # directions.  The dependency flips over (Amber now depends
                # on Bronze).  Amber and Bronze swap ownership of various
                # directories.
                #
                # Bronze's 1.0 hardlink to amber's libc goes away and is
                # replaced with a file of the same name.  Amber hardlinks
                # to that.
                #
                self.pkgsend_bulk(self.rurl, (self.incorp20, self.amber20,
                    self.bronze20))

                # create image and install version 1
                self.image_create(self.rurl)
                self.pkg("install incorp@1.0")
                self.file_exists(".SELF-ASSEMBLY-REQUIRED")
                self.pkg("install bronze")

                self.pkg("list amber@1.0 bronze@1.0")
                self.pkg("verify -v")

                # demonstrate that incorp@1.0 prevents package movement
                self.pkg("install bronze@2.0 amber@2.0", exit=1)

                # ...again, but using @latest.
                self.pkg("install bronze@latest amber@latest", exit=1)
                self.pkg("update bronze@latest amber@latest", exit=1)

                # Now update to get new versions of amber and bronze
                self.file_remove(".SELF-ASSEMBLY-REQUIRED")
                self.pkg("update")
                self.file_exists(".SELF-ASSEMBLY-REQUIRED")

                # Try to verify that it worked.
                self.pkg("list amber@2.0 bronze@2.0")
                self.pkg("verify -v")
                # make sure old implicit directories for bronzeA1 were removed
                self.assertTrue(not os.path.isdir(os.path.join(self.get_img_path(),
                    "A")))
                # Remove packages
                self.pkg("uninstall amber bronze")
                self.pkg("verify -v")

                # Make sure all directories are gone save /var in test image.
                self.assertEqual(set(os.listdir(self.get_img_path())),
                    set([".SELF-ASSEMBLY-REQUIRED", "var"]))

        def test_upgrade2(self):
                """ test incorporations:
                        1) install files that conflict w/ existing incorps
                        2) install package w/ dependencies that violate incorps
                        3) install incorp that violates existing incorp
                        4) install incorp that would force package backwards
                        """

                # Send all pkgs
                plist = self.pkgsend_bulk(self.rurl, (self.incorp10,
                    self.incorp20, self.incorp30, self.iridium10,
                    self.concorp10, self.amber10, self.amber20, self.bronze10,
                    self.bronze20, self.bronze30, self.brass10))

                self.image_create(self.rurl)

                self.pkg("install incorp@1.0")
                # install files that conflict w/ existing incorps
                self.pkg("install bronze@2.0", exit=1)
                # install package w/ dependencies that violate incorps
                self.pkg("install iridium@1.0", exit=1)
                # install package w/ unspecified dependency that pulls
                # in bronze
                self.pkg("install brass")
                self.pkg("verify brass@1.0 bronze@1.0")
                # attempt to install conflicting incorporation
                self.pkg("install concorp@1.0", exit=1)

                # attempt to force downgrade of package w/ older incorp
                self.pkg("install incorp@2.0")
                self.pkg("uninstall incorp@2.0")
                self.pkg("install incorp@1.0")

                # upgrade pkg that loses incorp. deps. in new version
                self.pkg("install -vvv incorp@2.0")

                # perform explicit update of incorp; should not update bronze
                self.pkg("update --parsable=0 -n incorp@3")
                self.assertEqualParsable(self.output, change_packages=[
                    [plist[1], plist[2]] # incorp 2.0 -> 3.0
                ])
                self.pkg("update --parsable=0 -n incorp")
                self.assertEqualParsable(self.output, change_packages=[
                    [plist[1], plist[2]] # incorp 2.0 -> 3.0
                ])

                # perform a general update; should upgrade incorp and bronze
                self.pkg("update --parsable=0 -n")
                self.assertEqualParsable(self.output, change_packages=[
                    [plist[8], plist[9]],  # bronze 2.0 -> 3.0
                    [plist[1], plist[2]] # incorp 2.0 -> 3.0
                ])

        def test_upgrade3(self):
                """Test for editable files moving between packages or locations
                or both."""

                install_cmd = "install"
                self.pkgsend_bulk(self.rurl, (self.silver10, self.silver20,
                    self.silver30, self.gold10, self.gold20, self.gold30,
                    self.golduser10, self.golduser20, self.silveruser))

                self.image_create(self.rurl)

                # test 1: move an editable file between packages
                self.pkg("{0} --parsable=0 gold@1.0 silver@1.0".format(install_cmd))
                self._assertEditables(
                    installed=[
                        'etc/ftpd/ftpusers',
                        'etc/group',
                        'etc/passwd',
                        'etc/shadow',
                    ]
                )
                self.pkg("verify -v")

                # modify config file
                test_str = "this file has been modified 1"
                file_path = "etc/passwd"
                self.file_append(file_path, test_str)

                # make sure /etc/passwd contains correct string
                self.file_contains(file_path, test_str)

                # update packages
                self.pkg("{0} -nvv gold@3.0 silver@2.0".format(install_cmd))
                self.pkg("{0} --parsable=0 gold@3.0 silver@2.0".format(install_cmd))
                self._assertEditables()
                self.pkg("verify -v")

                # make sure /etc/passwd contains still correct string
                self.file_contains(file_path, test_str)

                self.pkg("uninstall --parsable=0 silver gold")
                self._assertEditables(
                    removed=[
                        'etc/ftpd/ftpusers',
                        'etc/group',
                        'etc/passwd',
                        'etc/shadow',
                    ],
                )


                # test 2: change an editable file's path within a package
                self.pkg("{0} --parsable=0 gold@1.0".format(install_cmd))
                self.pkg("verify -v")

                # modify config file
                test_str = "this file has been modified test 2"
                file_path = "etc/passwd"
                self.file_append(file_path, test_str)

                self.pkg("{0} --parsable=0 gold@2.0".format(install_cmd))
                self._assertEditables(
                    moved=[['etc/passwd', 'etc/config2']],
                    removed=[
                        'etc/ftpd/ftpusers',
                        'etc/group',
                        'etc/shadow',
                    ],
                )
                self.pkg("verify -v")

                # make sure /etc/config2 contains correct string
                file_path = "etc/config2"
                self.file_contains(file_path, test_str)

                self.pkg("uninstall --parsable=0 gold")
                self._assertEditables(
                    removed=['etc/config2'],
                )
                self.pkg("verify -v")


                # test 3: move an editable file between packages and change its path
                self.pkg("{0} --parsable=0 gold@1.0 silver@1.0".format(install_cmd))
                self.pkg("verify -v")

                # modify config file
                file_path = "etc/passwd"
                test_str = "this file has been modified test 3"
                self.file_append(file_path, test_str)

                self.file_contains(file_path, test_str)

                self.pkg("{0} --parsable=0 gold@3.0 silver@3.0".format(install_cmd))
                self._assertEditables(
                    moved=[['etc/passwd', 'etc/config2']],
                    removed=[
                        'etc/ftpd/ftpusers',
                        'etc/group',
                        'etc/shadow',
                    ],
                )
                self.pkg("verify -v")

                # make sure /etc/config2 now contains correct string
                file_path = "etc/config2"
                self.file_contains(file_path, test_str)

                self.pkg("uninstall --parsable=0 gold silver")


                # test 4: move /etc/passwd between packages and ensure that we
                # can still uninstall a user at the same time.
                self.pkg("{0} --parsable=0 gold@1.0 silver@1.0".format(install_cmd))
                self.pkg("verify -v")

                # add a user
                self.pkg("install golduser@1.0")

                # make local changes to the user
                pwdpath = os.path.join(self.get_img_path(), "etc/passwd")

                pwdfile = open(pwdpath, "r+")
                lines = pwdfile.readlines()
                for i, l in enumerate(lines):
                        if l.startswith("Kermit"):
                                lines[i] = lines[i].replace("& User",
                                    "Kermit loves Miss Piggy")
                pwdfile.seek(0)
                pwdfile.writelines(lines)
                pwdfile.close()

                silly_path = os.path.join(self.get_img_path(), "etc/silly")
                silly_inode = os.stat(silly_path).st_ino

                # update packages
                self.pkg("{0} --parsable=0 gold@3.0 silver@2.0 golduser@2.0 "
                    "silveruser".format(install_cmd))
                self._assertEditables()

                # make sure Kermie is still installed and still has our local
                # changes
                self.file_contains("etc/passwd",
                    "Kermit:x:5:4:Kermit loves Miss Piggy:/export/home/Kermit:")

                # also make sure that /etc/silly hasn't been removed and added
                # again, even though it wasn't marked specially
                self.assertEqual(os.stat(silly_path).st_ino, silly_inode)

        def test_upgrade4(self):
                """Test to make sure hardlinks are correctly restored when file
                they point to is updated."""

                self.pkgsend_bulk(self.rurl, (self.iron10, self.iron20))
                self.image_create(self.rurl)

                self.pkg("install iron@1.0")
                self.pkg("verify -v")

                self.pkg("install iron@2.0")
                self.pkg("verify -v")

        def test_upgrade5(self):
                """Test manually removed directory and files will be restored
                 during update, if mode are different."""

                self.pkgsend_bulk(self.rurl, (self.dumdir10, self.dumdir20,
                    self.dumdir30))
                self.image_create(self.rurl)

                self.pkg("install -vvv dumdir@1.0")
                self.pkg("verify -v")
                dirpath = os.path.join(self.test_root, "image0", "etc")
                shutil.rmtree(dirpath)

                self.pkg("update -vvv dumdir@2.0")
                self.pkg("verify -v")
                shutil.rmtree(dirpath)

                self.pkg("update -vvv dumdir@3.0")
                self.pkg("verify -v")

        def test_upgrade_liveroot(self):
                """Test to make sure upgrade of package fails if on live root
                and reboot is needed."""

                self.upgrade_liveroot_helper("install")
                self.upgrade_liveroot_helper("exact-install")

        def upgrade_liveroot_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.liveroot10, self.liveroot20))
                self.image_create(self.rurl)

                self.pkg("--debug simulate_live_root={0} {1} liveroot@1.0".format(
                    self.get_img_path(), install_cmd))
                self.pkg("verify -v")
                self.pkg("--debug simulate_live_root={0} {1} --deny-new-be "
                    "liveroot@2.0".format(self.get_img_path(),  install_cmd),
                    exit=5)
                self.pkg("--debug simulate_live_root={0} uninstall "
                    "--deny-new-be liveroot".format(self.get_img_path()), exit=5)
                # "break" liveroot@1
                self.file_append("etc/liveroot", "this file has been changed")
                self.pkg("--debug simulate_live_root={0} fix --deny-new-be "
                    "liveroot".format(self.get_img_path()), exit=5)

        def test_upgrade_driver_conflicts(self):
                """Test to make sure driver_aliases conflicts don't cause
                add_drv to fail."""

                self.upgrade_driver_conflicts_helper("install")
                self.upgrade_driver_conflicts_helper("exact-install")

        def upgrade_driver_conflicts_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.dricon1, self.dricon2,
                    self.dricon3))

                self.image_create(self.rurl)

                self.pkg("list -afv")
                self.pkg("{0} dricon@1".format(install_cmd))
                # This one should comment out the wigit entry in driver_aliases
                self.pkg("{0} dricon@2".format(install_cmd))
                with open(os.path.join(self.get_img_path(),
                    "etc/driver_aliases")) as f:
                        da_contents = f.readlines()
                self.assertTrue("# pkg(7): wigit \"pci8086,1234\"\n" in da_contents)
                self.assertTrue("wigit \"pci8086,1234\"\n" not in da_contents)
                self.assertTrue("wigit \"pci8086,4321\"\n" in da_contents)
                self.assertTrue("zigit \"pci8086,1234\"\n" in da_contents)
                # This one should fail
                self.pkg("{0} dricon@3".format(install_cmd), exit=1)

        def test_driver_policy_removal(self):
                """Test for bug #9568 - that removing a policy for a
                driver where there is no minor node associated with it,
                works successfully.
                """

                self.driver_policy_removal_helper("install")
                self.driver_policy_removal_helper("exact-install")

        def driver_policy_removal_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.dripol1, self.dripol2,
                    self.dripol3, self.dripol4, self.dripol5))

                self.image_create(self.rurl)

                self.pkg("list -afv")

                # Should install the frigit driver with a policy.
                self.pkg("{0} dripol@1".format(install_cmd))

                # Check that there is a policy entry for this
                # device in /etc/security/device_policy
                with open(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")) as f:
                        dp_contents = f.readlines()
                self.assertTrue("frigit:*\tread_priv_set=net_rawaccess\t"
                    "write_priv_set=net_rawaccess\ttpd_member=true\n"
                    in dp_contents)

                # Should reinstall the frigit driver without a policy.
                self.pkg("{0} dripol@2".format(install_cmd))

                # Check that there is no longer a policy entry for this
                # device in /etc/security/device_policy
                with open(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")) as f:
                        dp_contents = f.readlines()
                self.assertTrue("frigit:*\tread_priv_set=net_rawaccess\t"
                    "write_priv_set=net_rawaccess\ttpd_member=true\n"
                    not in dp_contents)

                self.pkg("update dripol@3")
                with open(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")) as f:
                        dp_contents = f.readlines()
                self.assertTrue("frigit:*\ttpd_member=true\n"
                    in dp_contents)

                self.pkg("update dripol@5")
                with open(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")) as f:
                        dp_contents = f.readlines()
                self.assertTrue("frigit:node1\tread_priv_set=all"
                    "\twrite_priv_set=all\ttpd_member=true\n"
                    in dp_contents)

                self.pkg("update dripol@4")
                with open(os.path.join(self.get_img_path(),
                    "etc/security/device_policy")) as f:
                        dp_contents = f.readlines()
                self.assertTrue("frigit:node1" not in dp_contents)

        def test_file_preserve(self):
                """Verify that file preserve=true works as expected during
                package install, update, upgrade, and removal."""

                install_cmd = "install"
                self.pkgsend_bulk(self.rurl, (self.preserve1, self.preserve2,
                    self.preserve3, self.renpreserve))
                self.image_create(self.rurl)

                # If there are no local modifications, no preservation should be
                # done.  First with no content change ...
                self.pkg("{0} --parsable=0 preserve@1".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("{0} --parsable=0 preserve@2".format(install_cmd))
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve1")
                self.pkg("verify preserve")

                self.pkg("update --parsable=0 preserve@1")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve1")
                self.pkg("verify preserve")

                self.pkg("uninstall --parsable=0 preserve")

                # ... and again with content change.
                self.pkg("install --parsable=0 preserve@1")
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("install --parsable=0 preserve@3")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve3")

                self.pkg("update --parsable=0 preserve@1")
                self._assertEditables(
                    updated=['testme'],
                )

                self.file_contains("testme", "preserve1")

                self.pkg("verify preserve")
                self.pkg("uninstall --parsable=0 preserve")

                # Modify the file locally and update to a version where the
                # content changes.
                self.pkg("{0} --parsable=0 preserve@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.file_contains("testme", "preserve1")
                self.pkg("{0} --parsable=0 preserve@3".format(install_cmd))
                self._assertEditables()
                self.file_contains("testme", ["preserve1", "junk"])
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify preserve")
                self.pkg("uninstall --parsable=0 preserve")

                # Modify the file locally and downgrade to a version where
                # the content changes.
                self.pkg("{0} --parsable=0 preserve@3".format(install_cmd))
                self.file_append("testme", "junk")
                self.file_contains("testme", "preserve3")
                self.pkg("update --parsable=0 preserve@1")
                self._assertEditables(
                    moved=[['testme', 'testme.update']],
                    installed=['testme'],
                )
                self.file_doesnt_contain("testme", ["preserve3", "junk"])
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.file_exists("testme.update")
                self.file_remove("testme.update")
                self.pkg("verify preserve")
                self.pkg("uninstall --parsable=0 preserve")

                # Modify the file locally and update to a version where just the
                # mode changes.
                self.pkg("{0} --parsable=0 preserve@1".format(install_cmd))
                self.file_append("testme", "junk")

                self.pkg("{0} --parsable=0 preserve@2".format(install_cmd))
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", ["preserve1", "junk"])
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")

                self.pkg("update --parsable=0 preserve@1")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", ["preserve1", "junk"])
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.update")

                self.pkg("{0} --parsable=0 preserve@2".format(install_cmd))
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")

                # Remove the file locally and update the package; this should
                # simply replace the missing file.
                self.file_remove("testme")
                self.pkg("{0} --parsable=0 preserve@3".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("verify preserve")
                self.file_exists("testme")

                # Remove the file locally and downgrade the package; this should
                # simply replace the missing file.
                self.file_remove("testme")
                self.pkg("update --parsable=0 preserve@2")
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("verify preserve")
                self.file_exists("testme")
                self.pkg("uninstall preserve@2")

                # Verify preserved files will have their mode changed on update.
                self.pkg("{0} --parsable=0 preserve@1".format(install_cmd))
                self.pkg("{0} --parsable=0 preserve@2".format(install_cmd))
                self.pkg("verify preserve")

                # Verify that a package with a missing file that is marked with
                # the preserve=true won't cause uninstall failure.
                self.file_remove("testme")
                self.file_doesnt_exist("testme")
                self.pkg("uninstall --parsable=0 preserve")

                # Verify preserve works across package rename with and without
                # original_name use and even when the original file is missing.
                self.pkg("{0} --parsable=0 orig_pkg@1.0".format(install_cmd))
                foo1_path = os.path.join(self.get_img_path(), "foo1")
                self.assertTrue(os.path.isfile(foo1_path))
                bronze1_path = os.path.join(self.get_img_path(), "bronze1")
                self.assertTrue(os.path.isfile(bronze1_path))

                # Update across the rename boundary, then verify that the files
                # were installed with their new name and the old ones were
                # removed.
                self.pkg("update -nvv orig_pkg")
                self.pkg("update --parsable=0 orig_pkg")
                self._assertEditables(
                    moved=[['foo1', 'foo2']],
                )

                foo2_path = os.path.join(self.get_img_path(), "foo2")
                self.assertTrue(not os.path.exists(foo1_path))
                self.assertTrue(os.path.isfile(foo2_path))
                self.assertTrue(os.path.isfile(bronze1_path))
                self.pkg("uninstall --parsable=0 \*")

                # Update across the rename boundary, then truncate each of the
                # preserved files.  They should remain empty even though one is
                # changing names and the other is simply being preserved across
                # a package rename.
                self.pkg("{0} --parsable=0 orig_pkg@1.0".format(install_cmd))
                open(foo1_path, "wb").close()
                open(bronze1_path, "wb").close()
                self.pkg("update --parsable=0 orig_pkg")
                self._assertEditables(
                    moved=[['foo1', 'foo2']],
                )
                self.assertTrue(not os.path.exists(foo1_path))
                self.assertTrue(os.path.isfile(foo2_path))
                self.assertEqual(os.stat(foo2_path).st_size, 0)
                self.assertTrue(os.path.isfile(bronze1_path))
                self.assertEqual(os.stat(bronze1_path).st_size, 0)
                self.pkg("uninstall --parsable=0 \*")
                self._assertEditables(
                    removed=['bronze1', 'foo2'],
                )

                # Update across the rename boundary, then verify that a change
                # in file name will cause re-delivery of preserved files, but
                # unchanged, preserved files will not be re-delivered.
                self.pkg("{0} --parsable=0 orig_pkg@1.0".format(install_cmd))
                os.unlink(foo1_path)
                os.unlink(bronze1_path)
                self.pkg("update --parsable=0 orig_pkg")
                self._assertEditables(
                    moved=[['foo1', 'foo2']],
                )
                self.assertTrue(not os.path.exists(foo1_path))
                self.assertTrue(os.path.isfile(foo2_path))
                self.assertTrue(not os.path.exists(bronze1_path))
                self.pkg("uninstall --parsable=0 \*")

                # Ensure directory is empty before testing.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                sroot = os.path.join(img_inst.imgdir, "lost+found")
                shutil.rmtree(sroot)

                # Verify that unmodified, preserved files will not be salvaged
                # on uninstall.
                self.pkg("{0} --parsable=0 preserve@1.0".format(install_cmd))
                self.file_contains("testme", "preserve1")
                self.pkg("uninstall --parsable=0 preserve")
                salvaged = [
                    n for n in os.listdir(sroot)
                    if n.startswith("testme-")
                ]
                self.assertEqual(salvaged, [])

                # Verify that modified, preserved files will be salvaged
                # on uninstall.
                self.pkg("{0} --parsable=0 preserve@1.0".format(install_cmd))
                self.file_contains("testme", "preserve1")
                self.file_append("testme", "junk")
                self.pkg("uninstall --parsable=0 preserve")
                self.__salvage_file_contains(sroot, "testme", "junk")

        def test_file_preserve_renameold(self):
                """Make sure that file upgrade with preserve=renameold works."""

                install_cmd = "install"
                plist = self.pkgsend_bulk(self.rurl, (self.renameold1,
                    self.renameold2, self.renameold3))
                self.image_create(self.rurl)

                # If there are no local modifications, no preservation should be
                # done.  First with no content change ...
                self.pkg("{0} renold@1".format(install_cmd))
                self.pkg("{0} renold@2".format(install_cmd))
                self.file_contains("testme", "renold1")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # ... and again with content change.
                self.pkg("{0} renold@1".format(install_cmd))
                self.pkg("{0} renold@3".format(install_cmd))
                self.file_contains("testme", "renold3")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # Modify the file locally and update to a version where the
                # content changes.
                self.pkg("{0} renold@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("{0} --parsable=0 renold@3".format(install_cmd))
                self._assertEditables(
                    moved=[['testme', 'testme.old']],
                    installed=['testme'],
                )
                self.file_contains("testme.old", "junk")
                self.file_doesnt_contain("testme", "junk")
                self.file_contains("testme", "renold3")
                self.dest_file_valid(plist, "renold@3.0", "testme", "testme")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # Modify the file locally and update to a version where just the
                # mode changes.
                self.pkg("{0} renold@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("{0} --parsable=0 renold@2".format(install_cmd))
                self._assertEditables(
                    moved=[['testme', 'testme.old']],
                    installed=['testme'],
                )
                self.file_contains("testme.old", "junk")
                self.file_doesnt_contain("testme", "junk")
                self.file_contains("testme", "renold1")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify renold")
                self.pkg("uninstall renold")

                # Remove the file locally and update the package; this should
                # simply replace the missing file.
                self.pkg("{0} renold@1".format(install_cmd))
                self.file_remove("testme")
                self.pkg("{0} --parsable=0 renold@2".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("verify renold")
                self.pkg("uninstall renold")

        def test_file_preserve_renamenew(self):
                """Make sure that file ugprade with preserve=renamenew works."""

                install_cmd = "install"
                plist = self.pkgsend_bulk(self.rurl, (self.renamenew1,
                    self.renamenew2, self.renamenew3))
                self.image_create(self.rurl)

                # If there are no local modifications, no preservation should be
                # done.  First with no content change ...
                self.pkg("{0} rennew@1".format(install_cmd))
                self.pkg("{0} --parsable=0 rennew@2".format(install_cmd))
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "rennew1")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

                # ... and again with content change
                self.pkg("{0} rennew@1".format(install_cmd))
                self.pkg("{0} --parsable=0 rennew@3".format(install_cmd))
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "rennew3")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

                # Modify the file locally and update to a version where the
                # content changes.
                self.pkg("{0} rennew@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("{0} --parsable=0 rennew@3".format(install_cmd))
                self._assertEditables(
                    installed=['testme.new'],
                )
                self.file_contains("testme", "junk")
                self.file_doesnt_contain("testme.new", "junk")
                self.file_contains("testme.new", "rennew3")
                self.dest_file_valid(plist, "rennew@3.0", "testme",
                    "testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

                # Modify the file locally and update to a version where just the
                # mode changes.
                self.pkg("{0} rennew@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("{0} --parsable=0 rennew@2".format(install_cmd))
                self._assertEditables(
                    installed=['testme.new'],
                )
                self.file_contains("testme", "junk")
                self.file_doesnt_contain("testme.new", "junk")
                self.file_contains("testme.new", "rennew1")
                self.file_doesnt_exist("testme.old")

                # The original file won't be touched on update, so verify fails.
                self.pkg("verify rennew", exit=1)

                # Ensure that after fixing mode, verify passes.
                self.file_chmod("testme", 0o640)
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")
                self.file_remove("testme.new")

                # Remove the file locally and update the package; this should
                # simply replace the missing file.
                self.pkg("{0} rennew@1".format(install_cmd))
                self.file_remove("testme")
                self.pkg("{0} --parsable=0 rennew@2".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.old")
                self.pkg("verify rennew")
                self.pkg("uninstall rennew")

        def test_file_preserve_legacy(self):
                """Verify that preserve=legacy works as expected."""

                install_cmd = "install"
                self.pkgsend_bulk(self.rurl, (self.preslegacy,
                    self.renpreslegacy))
                self.image_create(self.rurl)

                # Ensure directory is empty before testing.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                sroot = os.path.join(img_inst.imgdir, "lost+found")
                shutil.rmtree(sroot)

                # Verify that unpackaged files will be salvaged on initial
                # install if a package being installed delivers the same file
                # and that the new file will be installed.
                self.file_append("testme", "unpackaged")
                self.pkg("{0} --parsable=0 preslegacy@1.0".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_contains("testme", "preserve1")
                self.__salvage_file_contains(sroot, "testme", "unpackaged")
                shutil.rmtree(sroot)

                # Verify that a package transitioning to preserve=legacy from
                # some other state will have the existing file renamed using
                # .legacy as an extension.
                self.pkg("update --parsable=0 preslegacy@2.0")
                self._assertEditables(
                    moved=[['testme', 'testme.legacy']],
                    installed=['testme'],
                )
                self.file_contains("testme.legacy", "preserve1")
                self.file_contains("testme", "preserve2")

                # Verify that if an action with preserve=legacy is upgraded
                # and its payload changes that the new payload is delivered
                # but the old .legacy file is not modified.
                self.pkg("update --parsable=0 preslegacy@3.0")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme.legacy", "preserve1")
                self.file_contains("testme", "preserve3")

                # Verify that if the file for an action marked with
                # preserve=legacy is removed that the package still
                # verifies.
                self.file_remove("testme")
                self.pkg("verify -v preslegacy")

                # Verify that a file removed for an action marked with
                # preserve=legacy can be reverted.
                self.pkg("revert testme")
                self.file_contains("testme", "preserve3")

                # Verify that an initial install of an action with
                # preserve=legacy will not install the payload of the action.
                self.pkg("uninstall preslegacy")
                self.pkg("{0} --parsable=0 preslegacy@3.0".format(install_cmd))
                self._assertEditables()
                self.file_doesnt_exist("testme")

                # Verify that if the original preserved file is missing during
                # a transition to preserve=legacy from some other state that
                # the new action is still delivered and the operation succeeds.
                self.pkg("uninstall preslegacy")
                self.pkg("{0} --parsable=0 preslegacy@1.0".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_remove("testme")
                self.pkg("update --parsable=0")
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_contains("testme", "preserve3")

                # Verify that a preserved file can be moved from one package to
                # another and transition to preserve=legacy at the same time.
                self.pkg("uninstall preslegacy")
                self.pkg("{0} --parsable=0 orig_preslegacy@1.0".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_exists("testme")
                self.pkg("update --parsable=0")
                self._assertEditables(
                    moved=[['testme', 'newme.legacy']],
                    installed=['newme'],
                )
                self.file_contains("testme.legacy", "preserve1")
                self.file_contains("newme", "preserve2")

        def test_file_preserve_abandon(self):
                """Verify that preserve=abandon works as expected."""

                install_cmd = "install"
                self.pkgsend_bulk(self.rurl, self.presabandon)
                self.image_create(self.rurl)

                # Ensure directory is empty before testing.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                sroot = os.path.join(img_inst.imgdir, "lost+found")
                shutil.rmtree(sroot)

                # Verify that unpackaged files will not be salvaged on initial
                # install if a package being installed delivers the same file
                # and that the new file will not be installed.
                self.file_append("testme", "unpackaged")
                self.pkg("{0} --parsable=0 presabandon@2".format(install_cmd))
                self._assertEditables()
                self.file_contains("testme", "unpackaged")
                self.assertTrue(not os.path.exists(os.path.join(sroot, "testme")))
                self.file_remove("testme")
                self.pkg("uninstall presabandon")

                # Verify that an initial install of an action with
                # preserve=abandon will not install the payload of the action.
                self.pkg("{0} --parsable=0 presabandon@2".format(install_cmd))
                self._assertEditables()
                self.file_doesnt_exist("testme")
                self.pkg("uninstall presabandon")

                # If an action delivered by the upgraded version of the package
                # has a preserve=abandon, the new file will not be installed and
                # the existing file will not be modified.

                # First with no content change ...
                self.pkg("{0} --parsable=0 presabandon@1".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("update --parsable=0 presabandon@2")
                self._assertEditables()
                self.file_contains("testme", "preserve1")
                # The currently installed version of the package has a preserve
                # value of abandon, so the file will not be removed.
                self.pkg("uninstall --parsable=0 presabandon")
                self._assertEditables()
                self.file_exists("testme")

                # If an action delivered by the downgraded version of the package
                # has a preserve=abandon, the new file will not be installed and
                # the existing file will not be modified.
                self.pkg("{0} --parsable=0 presabandon@4".format(install_cmd))
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_contains("testme", "preserve3")
                self.pkg("verify presabandon")
                self.pkg("update --parsable=0 presabandon@3")
                self._assertEditables()
                self.file_contains("testme", "preserve3")
                self.pkg("verify presabandon")
                self.pkg("uninstall --parsable=0 presabandon")
                self.file_remove("testme")

                # ... and again with content change.
                self.pkg("{0} --parsable=0 presabandon@1".format(install_cmd))
                self.pkg("{0} --parsable=0 presabandon@3".format(install_cmd))
                self._assertEditables()
                self.file_contains("testme", "preserve1")
                self.pkg("uninstall --parsable=0 presabandon")

                self.pkg("install --parsable=0 presabandon@4")
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_contains("testme", "preserve3")
                self.pkg("update --parsable=0 presabandon@2")
                self._assertEditables()
                self.file_contains("testme", "preserve3")
                self.pkg("verify presabandon")
                self.pkg("uninstall --parsable=0 presabandon")
                self.file_remove("testme")

                # Modify the file locally and upgrade to a version where the
                # file has a preserve=abandon attribute and the content changes.
                self.pkg("{0} --parsable=0 presabandon@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("{0} --parsable=0 presabandon@3".format(install_cmd))
                self._assertEditables()
                self.file_contains("testme", "preserve1")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("uninstall --parsable=0 presabandon")
                self.file_remove("testme")

                # Modify the file locally and downgrade to a version where the
                # file has a preserve=abandon attribute and the content changes.
                self.pkg("{0} --parsable=0 presabandon@4".format(install_cmd))
                self.file_append("testme", "junk")
                self.file_contains("testme", "preserve3")
                self.pkg("update --parsable=0 presabandon@2")
                self._assertEditables()
                self.file_contains("testme", "preserve3")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.update")
                self.pkg("verify presabandon")
                self.pkg("uninstall --parsable=0 presabandon")
                self.file_remove("testme")

                # Modify the file locally and upgrade to a version where the
                # file has a preserve=abandon attribute and just the mode changes.
                self.pkg("{0} --parsable=0 presabandon@1".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("{0} --parsable=0 presabandon@2".format(install_cmd))
                self._assertEditables()
                self.file_contains("testme", "preserve1")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify presabandon")
                self.pkg("uninstall --parsable=0 presabandon")
                self.file_remove("testme")

                # Modify the file locally and downgrade to a version where the
                # file has a preserve=abandon attribute and just the mode changes.
                self.pkg("{0} --parsable=0 presabandon@4".format(install_cmd))
                self.file_append("testme", "junk")
                self.pkg("update --parsable=0 presabandon@3")
                self._assertEditables()
                self.file_contains("testme", "preserve3")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.update")
                self.pkg("verify presabandon")
                self.pkg("uninstall --parsable=0 presabandon")
                self.file_remove("testme")

                # Remove the file locally and update the package where the
                # file has a preserve=abandon attribute; this will not replace
                # the missing file.
                self.pkg("{0} --parsable=0 presabandon@1".format(install_cmd))
                self.file_remove("testme")
                self.pkg("{0} --parsable=0 presabandon@2".format(install_cmd))
                self._assertEditables()
                self.file_doesnt_exist("testme")
                self.pkg("uninstall --parsable=0 presabandon")

                # Remove the file locally and downgrade the package where the
                # file has a preserve=abandon attribute; this will not replace
                # the missing file.
                self.pkg("{0} --parsable=0 presabandon@4".format(install_cmd))
                self.file_remove("testme")
                self.pkg("update --parsable=0 presabandon@3")
                self._assertEditables()

                # Verify that a package with a missing file that is marked with
                # the preserve=abandon won't cause uninstall failure.
                self.file_doesnt_exist("testme")
                self.pkg("uninstall --parsable=0 presabandon")

                # Verify that if the file for an action marked with
                # preserve=abandon is removed that the package still
                # verifies.
                self.pkg("{0} --parsable=0 presabandon@1".format(install_cmd))
                self.pkg("{0} --parsable=0 presabandon@2".format(install_cmd))
                self.file_remove("testme")
                self.pkg("verify -v presabandon")

                # Verify that a file removed for an action marked with
                # preserve=abandon can be reverted.
                self.pkg("revert testme")
                self.file_contains("testme", "preserve1")

        def test_file_preserve_install_only(self):
                """Verify that preserve=install-only works as expected."""

                self.pkgsend_bulk(self.rurl, self.presinstallonly)
                self.image_create(self.rurl)

                # Ensure directory is empty before testing.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                sroot = os.path.join(img_inst.imgdir, "lost+found")
                shutil.rmtree(sroot)

                # Verify that unpackaged files will not be modified or salvaged
                # on initial install if a package being installed delivers the
                # same file and that the new file will not be installed.
                self.file_append("testme", "unpackaged")
                self.pkg("install --parsable=0 presinstallonly@2")
                self._assertEditables()
                self.file_contains("testme", "unpackaged")
                self.assertTrue(not os.path.exists(os.path.join(sroot, "testme")))
                # Verify uninstall of the package will not remove the file.
                self.pkg("uninstall presinstallonly")
                self.file_exists("testme")
                self.file_remove("testme")

                # Verify that an initial install of an action with
                # preserve=install-only will install the payload of the action
                # if the file does not already exist.
                self.file_doesnt_exist("testme")
                self.pkg("install --parsable=0 presinstallonly@2")
                self._assertEditables(
                    installed=['testme']
                )
                self.file_exists("testme")
                self.pkg("uninstall presinstallonly")
                self.file_remove("testme")

                # Verify that an upgrade that initially delivers the action will
                # install it.
                self.pkg("install --parsable=0 presinstallonly@0")
                self._assertEditables()
                self.file_doesnt_exist("testme")
                self.pkg("install --parsable=0 presinstallonly@2")
                self._assertEditables(
                    installed=['testme']
                )
                self.file_exists("testme")
                self.pkg("uninstall presinstallonly")
                self.file_remove("testme")

                # If an action delivered by the upgraded version of the package
                # has a preserve=install-only, the new file will not be
                # installed and the existing file will not have its content
                # modified (the mode is being updated though).

                # First with no content change ...
                self.pkg("install --parsable=0 presinstallonly@1")
                self._assertEditables(
                    installed=['testme'],
                )
                self.pkg("update --parsable=0 presinstallonly@2")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve1")
                # The currently installed version of the package has a preserve
                # value of install-only, so the file will not be removed.
                self.pkg("uninstall --parsable=0 presinstallonly")
                self._assertEditables()
                self.file_exists("testme")
                self.file_remove("testme")

                # If an action delivered by the downgraded version of the
                # package has a preserve=install-only, the new file will not be
                # installed and the existing file will not be modified.
                self.pkg("install --parsable=0 presinstallonly@4")
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_contains("testme", "preserve3")
                self.pkg("verify presinstallonly")
                self.pkg("update --parsable=0 presinstallonly@3")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve3")
                self.pkg("verify presinstallonly")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                # ... and again with content change.
                self.pkg("install --parsable=0 presinstallonly@1")
                self.pkg("install --parsable=0 presinstallonly@3")
                self._assertEditables()
                self.file_contains("testme", "preserve1")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                self.pkg("install --parsable=0 presinstallonly@4")
                self._assertEditables(
                    installed=['testme'],
                )
                self.file_contains("testme", "preserve3")
                self.pkg("update --parsable=0 presinstallonly@2")
                self._assertEditables()
                self.file_contains("testme", "preserve3")
                self.pkg("verify presinstallonly")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                # Modify the file locally and upgrade to a version where the
                # file has a preserve=install-only attribute and the content
                # changes; it should not be modified.
                self.pkg("install --parsable=0 presinstallonly@1")
                self.file_append("testme", "junk")
                self.pkg("install --parsable=0 presinstallonly@3")
                self._assertEditables()
                self.file_contains("testme", "preserve1")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                # Modify the file locally and downgrade to a version where the
                # file has a preserve=install-only attribute and the content
                # changes.
                self.pkg("install --parsable=0 presinstallonly@4")
                self.file_append("testme", "junk")
                self.pkg("update --parsable=0 presinstallonly@2")
                self._assertEditables()
                self.file_contains("testme", "preserve3")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.update")
                self.pkg("verify presinstallonly")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                # Modify the file locally and upgrade to a version where the
                # file has a preserve=install-only attribute and just the mode
                # changes.
                self.pkg("install --parsable=0 presinstallonly@1")
                self.file_append("testme", "junk")
                self.pkg("install --parsable=0 presinstallonly@2")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve1")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.pkg("verify presinstallonly")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                # Modify the file locally and downgrade to a version where the
                # file has a preserve=install-only attribute and just the mode
                # changes.
                self.pkg("install --parsable=0 presinstallonly@4")
                self.file_append("testme", "junk")
                self.pkg("update --parsable=0 presinstallonly@3")
                self._assertEditables(
                    updated=['testme'],
                )
                self.file_contains("testme", "preserve3")
                self.file_contains("testme", "junk")
                self.file_doesnt_exist("testme.old")
                self.file_doesnt_exist("testme.new")
                self.file_doesnt_exist("testme.update")
                self.pkg("verify presinstallonly")
                self.pkg("uninstall --parsable=0 presinstallonly")
                self.file_remove("testme")

                # Remove the file locally and update the package where the file
                # has a preserve=install-only attribute; this will not replace
                # the missing file.
                self.pkg("install --parsable=0 presinstallonly@1")
                self.file_remove("testme")
                self.pkg("install --parsable=0 presinstallonly@2")
                self._assertEditables()
                self.file_doesnt_exist("testme")
                self.pkg("uninstall --parsable=0 presinstallonly")

                # Remove the file locally and downgrade the package where the
                # file has a preserve=install-only attribute; this will not
                # replace the missing file.
                self.pkg("install --parsable=0 presinstallonly@4")
                self.file_remove("testme")
                self.pkg("update --parsable=0 presinstallonly@3")
                self._assertEditables()
                self.file_doesnt_exist("testme")

                # Verify that a package with a missing file that is marked with
                # the preserve=install-only won't cause uninstall failure.
                self.file_doesnt_exist("testme")
                self.pkg("uninstall --parsable=0 presinstallonly")

                # Verify that if the file for an action marked with
                # preserve=install-only is removed that the package fails
                # verify.
                self.pkg("install --parsable=0 presinstallonly@1")
                self.pkg("install --parsable=0 presinstallonly@2")
                self.file_remove("testme")
                self.pkg("verify -v presinstallonly", exit=1)

                # Verify that fix will restore it.
                self.pkg("fix -v presinstallonly")
                self.file_contains("testme", "preserve1")

                # Verify that a file removed for an action marked with
                # preserve=install-only can be reverted.
                self.file_remove("testme")
                self.pkg("revert testme")
                self.file_contains("testme", "preserve1")

        def test_directory_salvage(self):
                """Make sure basic directory salvage works as expected"""

                self.pkgsend_bulk(self.rurl, self.salvage)
                self.image_create(self.rurl)
                self.pkg("install salvage@1.0")
                self.file_append("var/mail/foo", "foo's mail")
                self.file_append("var/mail/bar", "bar's mail")
                self.file_append("var/mail/baz", "baz's mail")
                self.pkg("update salvage")
                self.file_exists("var/.migrate-to-shared/mail/foo")
                self.file_exists("var/.migrate-to-shared/mail/bar")
                self.file_exists("var/.migrate-to-shared/mail/baz")

        def test_directory_salvage_persistent(self):
                """Make sure directory salvage works as expected when salvaging
                content to an existing packaged directory."""

                # we salvage content from two directories,
                # var/noodles and var/spaghetti each of which disappear over
                # subsequent updates.
                self.pkgsend_bulk(self.rurl, self.salvage)
                self.image_create(self.rurl)
                self.pkg("install salvage@1.0")
                self.file_append("var/mail/foo", "foo's mail")
                self.file_append("var/noodles/noodles.txt", "yum")
                self.pkg("update salvage@2.0")
                self.file_exists("var/.migrate-to-shared/mail/foo")
                self.file_exists("var/persistent/noodles.txt")
                self.file_append("var/spaghetti/spaghetti.txt", "yum")
                self.pkg("update")
                self.file_exists("var/persistent/noodles.txt")
                self.file_exists("var/persistent/spaghetti.txt")

                # ensure that we can jump from 1.0 to 3.0 directly.
                self.image_create(self.rurl)
                self.pkg("install salvage@1.0")
                self.file_append("var/noodles/noodles.txt", "yum")
                self.pkg("update  salvage@3.0")
                self.file_exists("var/persistent/noodles.txt")

        def test_special_salvage(self):
                """Make sure salvaging directories with special files works as
                expected."""

                self.pkgsend_bulk(self.rurl, self.salvage_special)
                self.image_create(self.rurl, destroy=True, fs=("var",))

                self.pkg("install salvage-special")

                os.mkfifo(os.path.join(self.img_path(), "salvage", "fifo"))
                sock = socket.socket(socket.AF_UNIX)
                sock.bind(os.path.join(self.img_path(), "salvage", "socket"))
                sock.close()

                # This could hang reading fifo, or keel over reading socket.
                self.pkg("uninstall salvage-special")

        def test_salvage_nested(self):
                """Make sure salvaging from nested packaged directories
                works as expected. We test four scenarios, abandoning an
                editable file (since that's a scenario ON will use for
                23743369), a direct upgrade with no user edits,
                salvaging all unpackaged contents despite nested dirs
                not being delivered to var/.migrate, and splitting the
                salvaged contents of a previously delivered directory to
                two new directories."""

                # We salvage to several places as part of the upgrade
                # operation.
                self.pkgsend_bulk(self.rurl, self.salvage_nested)
                self.image_create(self.rurl)
                self.pkg("install salvage-nested@1.0")
                # add some unpackaged directories & contents
                self.file_append("var/mail/foo", "foo's mail")
                os.makedirs(
                    os.path.join(self.get_img_path(),
                    "var", "user", "webui", "timf"))
                self.file_append("var/user/webui/user-pref.conf", "ook")
                self.file_append("var/user/webui/timf/blah.conf", "moo")
                self.file_append("var/user/evsuser/.ssh/config", "bar")

                # modify a packaged editable file
                self.file_append(
                    "var/user/evsuser/.ssh/authorized_keys", "foo")

                # abandon our editable file
                self.pkg("update salvage-nested@1.1")
                self.file_exists("var/user/evsuser/.ssh/authorized_keys")

                self.pkg("update salvage-nested@2.0")
                # Check negative cases first. This first location was where
                # files would get salvaged to incorrectly prior to the fix
                # for 23739095
                self.file_doesnt_exist("var/.migrate/user/authorized_keys")
                # these weren't known failures, but let's check anyway,
                # since this is a useful safety net.
                self.file_doesnt_exist("var/.migrate/authorized_keys")
                self.file_doesnt_exist(
                    "var/.migrate/user/evsuser/authorized_keys")
                self.file_doesnt_exist("var/.migrate/user/evsuser/config")
                self.file_doesnt_exist("var/.migrate/blah.conf")
                self.file_doesnt_exist("var/.migrate/user/blah.conf")
                self.file_doesnt_exist("var/.migrate/user/webui/blah.conf")

                # now verify we salvaged everything correctly
                self.file_contains("var/.migrate/mail/foo", "foo's mail")
                self.file_contains(
                    "var/.migrate/user/evsuser/.ssh/authorized_keys",
                    "foo")
                self.file_contains(
                    "var/.migrate/user/evsuser/.ssh/config", "bar")
                self.file_contains(
                    "var/.migrate/user/webui/user-pref.conf", "ook")
                self.file_contains(
                    "var/.migrate/user/webui/timf/blah.conf", "moo")

                # now try without the initial non-editable file
                self.image_create(self.rurl)
                self.pkg("install salvage-nested@1.1")
                # an abandoned file shouldn't be installed
                self.file_doesnt_exist("var/user/evsuser/.ssh/authorized_keys")
                self.file_append(
                    "var/user/evsuser/.ssh/authorized_keys", "ook")
                self.pkg("update salvage-nested@2.0")
                self.file_contains(
                    "var/.migrate/user/evsuser/.ssh/authorized_keys",
                    "ook")

                # now try with no user edits
                self.image_create(self.rurl)
                self.pkg("install salvage-nested@1.1")
                self.pkg("update salvage-nested@2.0")
                self.file_doesnt_exist(
                    "var/.migrate/user/evsuser/.ssh/authorized_keys")
                self.dir_exists("var/.migrate/user/evsuser/.ssh")

                # Now try without delivering the evsuser dir and subdirs
                # in the updated package
                self.image_create(self.rurl)
                self.pkg("install salvage-nested@1.1")
                os.makedirs(
                    os.path.join(self.get_img_path(),
                    "var", "user", "webui", "timf"))
                os.makedirs(
                    os.path.join(self.get_img_path(),
                    "var", "user", "noodles"))
                self.file_append("var/user/webui/timf/user-pref.conf", "ook")
                self.file_append("var/user/noodles/blah.conf", "moo")
                self.file_append("var/user/evsuser/.ssh/config", "bar")
                self.pkg("update salvage-nested@3.0")
                self.file_contains(
                    "var/.migrate/user/evsuser/.ssh/config", "bar")
                self.file_contains(
                    "var/.migrate/user/webui/timf/user-pref.conf", "ook")
                self.file_contains(
                    "var/.migrate/user/noodles/blah.conf", "moo")

                # Finally try splitting the salvaged contents from a
                # previously delivered directory into two new directories.
                self.image_create(self.rurl)
                self.pkg("install salvage-nested@1.1")
                os.makedirs(
                    os.path.join(self.get_img_path(),
                    "var", "user", "webui", "timf"))
                os.makedirs(
                    os.path.join(self.get_img_path(),
                    "var", "user", "noodles"))
                self.file_append("var/user/webui/timf/user-pref.conf", "ook")
                self.file_append("var/user/noodles/blah.conf", "moo")
                self.file_append("var/user/evsuser/.ssh/config", "bar")
                self.pkg("update salvage-nested@4.0")
                self.file_contains(
                    "var/.migrate/evsuser/.ssh/config", "bar")
                self.file_contains(
                    "var/.migrate/user/webui/timf/user-pref.conf", "ook")
                self.file_contains(
                    "var/.migrate/user/noodles/blah.conf", "moo")


        def dest_file_valid(self, plist, pkg, src, dest):
                """Used to verify that the dest item's mode, attrs, timestamp,
                etc. match the src items's matching action as expected."""

                for p in plist:
                        pfmri = fmri.PkgFmri(p)
                        pfmri.publisher = None
                        sfmri = pfmri.get_short_fmri().replace("pkg:/", "")

                        if pkg != sfmri:
                                continue

                        m = manifest.Manifest()
                        m.set_content(self.get_img_manifest(pfmri))
                        for a in m.gen_actions():
                                if a.name != "file":
                                        # Only want file actions that have
                                        # preserve attribute.
                                        continue
                                if a.attrs["path"] != src:
                                        # Only want actions with matching path.
                                        continue
                                self.validate_fsobj_attrs(a, target=dest)

        def test_link_preserve(self):
                """Ensure that files transitioning to a link still follow
                original_name preservation rules."""

                self.pkgsend_bulk(self.rurl, (self.linkpreserve))
                self.image_create(self.rurl, destroy=True, fs=("var",))

                # Install package with original config file location.
                self.pkg("install --parsable=0 linkpreserve@1.0")
                cfg_path = os.path.join("etc", "ssh", "sshd_config")
                abs_path = os.path.join(self.get_img_path(), cfg_path)

                self.file_exists(cfg_path)
                self.assertTrue(not os.path.islink(abs_path))

                # Modify the file.
                self.file_append(cfg_path, "modified")

                # Install new package version, verify file replaced with link
                # and modified version was moved to new location.
                new_cfg_path = os.path.join("etc", "sunssh", "sshd_config")
                self.pkg("update --parsable=0 linkpreserve@2.0")
                self._assertEditables(
                    moved=[['etc/ssh/sshd_config', 'etc/sunssh/sshd_config']]
                )
                self.assertTrue(os.path.islink(abs_path))
                self.file_exists(new_cfg_path)
                self.file_contains(new_cfg_path, "modified")

                # Uninstall, then install original version again.
                self.pkg("uninstall linkpreserve")
                self.pkg("install linkpreserve@1.0")
                self.file_contains(cfg_path, "preserve1")

                # Install new package version and verify that unmodified file is
                # replaced with new configuration file.
                self.pkg("update --parsable=0 linkpreserve@2.0")
                self._assertEditables(
                    moved=[['etc/ssh/sshd_config', 'etc/sunssh/sshd_config']]
                )
                self.file_contains(new_cfg_path, "preserve2")

        def test_many_hashalgs(self):
                """Test that when upgrading actions where the new action
                contains more hash attributes than the old action, that the
                upgrade works."""

                self.many_hashalgs_helper("install", "sha256")
                self.many_hashalgs_helper("exact-install", "sha256")
                if sha512_supported:
                        self.many_hashalgs_helper("install", "sha512_256")
                        self.many_hashalgs_helper("exact-install", "sha512_256")

        def many_hashalgs_helper(self, install_cmd, hash_alg):
                self.pkgsend_bulk(self.rurl, (self.iron10))
                self.image_create(self.rurl, destroy=True)
                self.pkg("install iron@1.0")
                self.pkg("contents -m iron")
                # We have not enabled SHA2 hash publication yet.
                self.assertTrue(("pkg.hash.{0}".format(hash_alg) not in self.output))

                # publish with SHA1 and SHA2 hashes
                self.pkgsend_bulk(self.rurl, self.iron20,
                    debug_hash="sha1+{0}".format(hash_alg))

                # verify that a non-SHA2 aware client can install these bits
                self.pkg("-D hash=sha1 update")
                self.image_create(self.rurl, destroy=True)

                # This also tests package retrieval: we always retrieve packages
                # with the least-preferred hash, but verify with the
                # most-preferred hash.
                self.pkg("install iron@2.0")
                self.pkg("contents -m iron")
                self.assertTrue("pkg.hash.{0}".format(hash_alg in self.output))

                # publish with only SHA-2 hashes
                self.pkgsend_bulk(self.rurl, self.iron20,
                    debug_hash="{0}".format(hash_alg))

                # verify that a non-SHA2 aware client cannot install these bits
                # since there are no SHA1 hashes present
                self.pkg("-D hash=sha1 update", exit=1)
                self.assertTrue(
                    "No file could be found for the specified hash name: "
                    "'NOHASH'" in self.errout)

                # Make sure we've been publishing only with SHA2 by removing
                # those known attributes, then checking for the presence of
                # the SHA-1 attributes.
                self.pkg("-D hash={0} update".format(hash_alg))
                self.pkg("contents -m iron")
                for attr in ["pkg.hash.{0}".format(hash_alg),
                    "pkg.chash.{0}".format(hash_alg)]:
                        self.output = self.output.replace(attr, "")
                self.assertTrue("hash" not in self.output)
                self.assertTrue("chash" not in self.output)

        def test_content_hash_ignore(self):
                """Test that pkgs with content-hash attributes are ignored for
                install and verify by default."""

                elfpkg_1 = """
                    open elftest@1.0
                    add file {0} mode=0755 owner=root group=bin path=/bin/true
                    close """
                elfpkg = elfpkg_1.format(os.path.join("ro_data", "elftest.so.1"))
                elf1 = self.pkgsend_bulk(self.rurl, (elfpkg,))[0]

                repo_dir = self.dcs[1].get_repodir()
                f = fmri.PkgFmri(elf1, None)
                repo = self.get_repo(repo_dir)
                mpath = repo.manifest(f)
                # load manifest, add content-hash attr and store back to disk
                mani = manifest.Manifest()
                mani.set_content(pathname=mpath)
                for a in mani.gen_actions():
                        if "bin/true" in str(a):
                                a.attrs["pkg.content-hash.sha256"] = "foo"
                mani.store(mpath)
                # rebuild repo catalog since manifest digest changed
                repo.rebuild()

                # assert that the current pkg gate has the correct hash ranking
                self.assertTrue(len(digest.RANKED_CONTENT_HASH_ATTRS) > 0)
                self.assertEqual(digest.RANKED_CONTENT_HASH_ATTRS[0], "pkg.content-hash")
                if sha512_supported:
                        self.assertEqual(digest.RANKED_CONTENT_HASH_TYPES[0], "gelf:sha512t_256")
                else:
                        self.assertEqual(digest.RANKED_CONTENT_HASH_TYPES[0], "gelf:sha256")

                # test that pkgrecv, pkgrepo verify, pkg install and pkg verify
                # do not complain about unknown hash
                self.pkgrecv("{0} -a -d {1} '*'".format(repo_dir,
                    os.path.join(self.test_root, "x.p5p")))
                self.pkgrepo("verify -s {0}".format(repo_dir))
                self.image_create(self.rurl, destroy=True)
                self.pkg("install -v {0}".format(elf1))
                # Note that we pass verification if any of the hashes match, but
                # we require by default that the content hash matches.
                self.pkg("verify")


class TestPkgInstallActions(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        misc_files = {
                "ftpusers" :
"""# ident      "@(#)ftpusers   1.6     06/11/21 SMI"
#
# List of users denied access to the FTP server, see ftpusers(4).
#
root
bin
sys
adm
""",
                "group" :
"""root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
+::::
""",
                "passwd" :
"""root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
+::::::
""",
                "shadow" :
"""root:9EIfTNBp9elws:13817::::::
daemon:NP:6445::::::
bin:NP:6445::::::
sys:NP:6445::::::
adm:NP:6445::::::
+::::::::
""",
                "cat" : " ",
                "empty" : ""
        }


        foo10 = """
            open foo@1.0,5.11-0
            close """

        only_attr10 = """
            open only_attr@1.0,5.11-0
            add set name=foo value=bar
            close """

        only_depend10 = """
            open only_depend@1.0,5.11-0
            add depend type=require fmri=foo@1.0,5.11-0
            close """

        only_directory10 = """
            open only_dir@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            close """

        only_driver10 = """
            open only_driver@1.0,5.11-0
            add driver name=zerg devlink="type=ddi_pseudo;name=zerg\\t\D"
            close """

        only_group10 = """
            open only_group@1.0,5.11-0
            add group groupname=Kermit gid=28
            close """

        only_group_file10 = """
            open only_group_file@1.0,5.11-0
            add dir mode=0755 owner=root group=Kermit path=/export/home/Kermit
            close """

        only_hardlink10 = """
            open only_hardlink@1.0,5.11-0
            add hardlink path=/cat.hardlink target=/cat
            close """

        only_legacy10 = """
            open only_legacy@1.0,5.11-0
            add legacy category=system desc="GNU make - A utility used to build software (gmake) 3.81" hotline="Please contact your local service provider" name="gmake - GNU make" pkg=SUNWgmake vendor="Sun Microsystems, Inc." version=11.11.0,REV=2008.04.29.02.08
            close """

        only_link10 = """
            open only_link@1.0,5.11-0
            add link path=/link target=/tmp/cat
            close """

        only_user10 = """
            open only_user@1.0,5.11-0
            add user username=Kermit group=adm home-dir=/export/home/Kermit
            close """

        only_user_file10 = """
            open only_user_file@1.0,5.11-0
            add dir mode=0755 owner=Kermit group=adm path=/export/home/Kermit
            close """

        csu1 = """
            open csu1@1.0,5.11-0
            add legacy category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu vendor="Oracle Corporation" version=11.11,REV=2009.11.11
            close
        """

        csu1_2 = """
            open csu1@2.0,5.11-0
            add legacy category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu vendor="Oracle Corporation" version=11.11,REV=2010.11.11
            close
        """

        csu2 = """
            open csu2@1.0,5.11-0
            add legacy category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu vendor="Oracle Corporation" version=11.11,REV=2009.11.11
            close
        """

        csu2_2 = """
            open csu2@2.0,5.11-0
            add legacy category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu vendor="Oracle Corporation" version=11.11,REV=2010.11.11
            close
        """

        csu3 = """
            open csu3@1.0,5.11-0
            add legacy category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu vendor="Oracle Corporation" version=11.11,REV=2009.11.11
            close
        """

        csu3_2 = """
            open csu3@2.0,5.11-0
            add legacy category=system desc="core software for a specific instruction-set architecture" hotline="Please contact your local service provider" name="Core Solaris, (Usr)" pkg=SUNWcsu vendor="Oracle Corporation" version=11.11,REV=2010.11.11
            close
        """

        # some of these are subsets-- "always" and "at-end"-- for performance;
        # we assume that e.g. if a and z work, that bcdef, etc. will too.
        pkg_name_valid_chars = {
            "never": " `~!@#$%^&*()=[{]}\\|;:\",<>?",
            "always": "09azAZ",
            "after-first": "_-.+",
            "at-end": "09azAZ_-.+",
        }

        def setUp(self):

                pkg5unittest.SingleDepotTestCase.setUp(self)

                self.only_file10 = """
                    open only_file@1.0,5.11-0
                    add file cat mode=0555 owner=root group=bin path=/cat
                    close """

                self.only_license10 = """
                    open only_license@1.0,5.11-0
                    add license cat license=copyright
                    close """

                self.baseuser = """
                    open system/action/user@0,5.11
                    add dir path=etc mode=0755 owner=root group=sys
                    add dir path=etc/ftpd mode=0755 owner=root group=sys
                    add user username=root password=9EIfTNBp9elws uid=0 group=root home-dir=/root gcos-field=Super-User login-shell=/usr/bin/bash ftpuser=false lastchg=13817 group-list=other group-list=bin group-list=sys group-list=adm
                    add group gid=0 groupname=root
                    add group gid=3 groupname=sys
                    add file empty path=etc/group mode=0644 owner=root group=sys preserve=true
                    add file empty path=etc/passwd mode=0644 owner=root group=sys preserve=true
                    add file empty path=etc/shadow mode=0400 owner=root group=sys preserve=true
                    add file empty path=etc/ftpd/ftpusers mode=0644 owner=root group=sys preserve=true
                    add file empty path=etc/user_attr mode=0644 owner=root group=sys preserve=true
                    close """

                self.singleuser = """
                    open singleuser@0,5.11
                    add user group=fozzie uid=16 username=fozzie
                    add group groupname=fozzie gid=16
                    close
                """

                self.basics0 = """
                    open basics@1.0,5.11-0
                    add file passwd mode=0644 owner=root group=sys path=etc/passwd preserve=true
                    add file shadow mode=0400 owner=root group=sys path=etc/shadow preserve=true
                    add file group mode=0644 owner=root group=sys path=etc/group preserve=true
                    add file ftpusers mode=0644 owner=root group=sys path=etc/ftpd/ftpusers preserve=true
                    add dir mode=0755 owner=root group=sys path=etc
                    add dir mode=0755 owner=root group=sys path=etc/ftpd
                    close """

                self.basics1 = """
                    open basics1@1.0,5.11-0
                    add dir mode=0755 owner=root group=bin path=lib
                    add dir mode=0755 owner=root group=sys path=var
                    add dir mode=0755 owner=root group=sys path=var/svc
                    add dir mode=0755 owner=root group=sys path=var/svc/manifest
                    add dir mode=0755 owner=root group=bin path=usr
                    add dir mode=0755 owner=root group=bin path=usr/local
                    close """

                self.grouptest = """
                    open grouptest@1.0,5.11-0
                    add dir mode=0755 owner=root group=Kermit path=/usr/Kermit
                    add file empty mode=0755 owner=root group=Kermit path=/usr/local/bin/do_group_nothing
                    add group groupname=lp gid=8
                    add group groupname=staff gid=10
                    add group groupname=Kermit
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.usertest10 = """
                    open usertest@1.0,5.11-0
                    add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
                    add file empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
                    add depend fmri=pkg:/basics@1.0 type=require
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.usertest11 = """
                    open usertest@1.1,5.11-0
                    add dir mode=0755 owner=Kermit group=Kermit path=/export/home/Kermit
                    add file empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/do_user_nothing
                    add depend fmri=pkg:/basics@1.0 type=require
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit2 group-list=lp group-list=staff group-list=root ftpuser=false
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    add depend fmri=pkg:/basics@1.0 type=require
                    close """

                self.ugidtest = """
                    open ugidtest@1.0,5.11-0
                    add user username=dummy group=root
                    add group groupname=dummy
                    close """

                self.silver10 = """
                    open silver@1.0,5.11-0
                    add file empty mode=0755 owner=root group=root path=/usr/local/bin/silver
                    add depend fmri=pkg:/basics@1.0 type=require
                    add depend fmri=pkg:/basics1@1.0 type=require
                    close """
                self.silver20 = """
                    open silver@2.0,5.11-0
                    add file empty mode=0755 owner=Kermit group=Kermit path=/usr/local/bin/silver
                    add user username=Kermit group=Kermit home-dir=/export/home/Kermit group-list=lp group-list=staff
                    add depend fmri=pkg:/basics@1.0 type=require
                    add depend fmri=pkg:/basics1@1.0 type=require
                    add depend fmri=pkg:/grouptest@1.0 type=require
                    close """

                self.devicebase = """
                    open devicebase@1.0,5.11-0
                    add dir mode=0755 owner=root group=sys path=/var
                    add dir mode=0755 owner=root group=sys path=/var/run
                    add dir mode=0755 owner=root group=root path=system
                    add dir mode=0755 owner=root group=root path=system/volatile
                    add dir mode=0755 owner=root group=sys path=/tmp
                    add dir mode=0755 owner=root group=sys path=/etc
                    add dir mode=0755 owner=root group=sys path=/etc/security
                    add file empty mode=0600 owner=root group=sys path=/etc/devlink.tab preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/name_to_major preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/driver_aliases preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/driver_classes preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/minor_perm preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/security/device_policy preserve=true
                    add file empty mode=0644 owner=root group=sys path=/etc/security/extra_privs preserve=true
                    close
                """

                self.devlink10 = """
                    open devlinktest@1.0,5.11-0
                    add driver name=zerg devlink="type=ddi_pseudo;name=zerg\\t\D"
                    add driver name=borg devlink="type=ddi_pseudo;name=borg\\t\D" devlink="type=ddi_pseudo;name=warg\\t\D"
                    add depend type=require fmri=devicebase
                    close
                """

                self.devlink20 = """
                    open devlinktest@2.0,5.11-0
                    add driver name=zerg devlink="type=ddi_pseudo;name=zerg2\\t\D" devlink="type=ddi_pseudo;name=zorg\\t\D"
                    add driver name=borg devlink="type=ddi_pseudo;name=borg\\t\D" devlink="type=ddi_pseudo;name=zork\\t\D"
                    add depend type=require fmri=devicebase
                    close
                """

                self.devalias10 = """
                    open devalias@1,5.11
                    add driver name=zerg alias=pci8086,1234 alias=pci8086,4321
                    close
                """

                self.devalias20 = """
                    open devalias@2,5.11
                    add driver name=zerg alias=pci8086,5555
                    close
                """

                self.devaliasmove10 = """
                    open devaliasmove@1,5.11
                    add driver name=zerg alias=pci8086,5555
                    close
                """

                self.devaliasmove20 = """
                    open devaliasmove@2,5.11
                    add driver name=zerg
                    add driver name=borg alias=pci8086,5555
                    close
                """

                self.badhardlink1 = """
                    open badhardlink1@1.0,5.11-0
                    add hardlink path=foo target=bar
                    close
                """

                self.badhardlink2 = """
                    open badhardlink2@1.0,5.11-0
                    add file cat mode=0555 owner=root group=bin path=/etc/motd
                    add hardlink path=foo target=/etc/motd
                    close
                """

                self.make_misc_files(self.misc_files)

        def test_basics_0_install(self):
                """Send basic infrastructure, install and uninstall."""

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1))
                self.image_create(self.rurl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("install basics")
                self.pkg("install basics1")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall basics basics1")
                self.pkg("verify")

        def test_basics_0_exact_install(self):
                """Send basic infrastructure, exact-install and uninstall."""

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1))
                self.image_create(self.rurl)

                self.pkg("list -a")
                self.pkg("list", exit=1)

                self.pkg("exact-install basics basics1")

                self.pkg("list")
                self.pkg("verify")

                self.pkg("uninstall basics basics1")
                self.pkg("verify")

        def test_grouptest_install(self):

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.grouptest))
                self.image_create(self.rurl)
                self.pkg("install basics")
                self.file_doesnt_contain("etc/group", ["lp", "staff", "Kermit"])
                self.pkg("install basics1")

                self.pkg("install grouptest")
                self.pkg("verify -v")
                self.file_contains("etc/group", ["lp", "staff", "Kermit"])
                self.pkg("uninstall -vvv grouptest")
                self.pkg("verify -v")
                self.file_doesnt_contain("etc/group", ["lp", "staff", "Kermit"])

        def test_grouptest_exact_install(self):

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.grouptest))
                self.image_create(self.rurl)
                self.pkg("exact-install basics basics1")
                self.file_doesnt_contain("etc/group", ["lp", "staff", "Kermit"])

                self.pkg("exact-install grouptest")
                self.pkg("verify")
                self.file_contains("etc/group", ["lp", "staff", "Kermit"])
                self.pkg("list basics1", exit=1)

                self.pkg("uninstall grouptest")
                self.pkg("verify")
                self.file_doesnt_contain("etc/group", ["lp", "staff", "Kermit"])

        def test_usertest_install(self):

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.grouptest, self.usertest10))
                self.image_create(self.rurl)
                self.pkg("install basics")
                self.pkg("install basics1")
                self.file_doesnt_contain("etc/passwd", "Kermit")
                self.file_doesnt_contain("etc/shadow", "Kermit")

                self.pkg("install usertest")
                self.pkg("verify")
                self.file_contains("etc/passwd", "Kermit")
                self.file_contains("etc/shadow", "Kermit")
                self.pkg("contents -m usertest")

                self.pkgsend_bulk(self.rurl, self.usertest11)
                self.pkg("refresh")
                self.pkg("install usertest")
                self.pkg("verify")
                self.pkg("contents -m usertest")

                self.pkg("uninstall usertest")
                self.pkg("verify")
                self.file_doesnt_contain("etc/passwd", "Kermit")
                self.file_doesnt_contain("etc/shadow", "Kermit")

        def test_usertest_exact_install(self):

                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.grouptest, self.usertest10))
                self.image_create(self.rurl)
                self.pkg("exact-install basics basics1")
                self.file_doesnt_contain("etc/passwd", "Kermit")
                self.file_doesnt_contain("etc/shadow", "Kermit")

                self.pkg("exact-install usertest")
                self.pkg("verify")
                self.pkg("list basics1", exit=1)
                self.pkg("contents -m usertest")
                self.file_contains("etc/passwd", "Kermit")
                self.file_contains("etc/shadow", "Kermit")

                self.pkgsend_bulk(self.rurl, self.usertest11)
                self.pkg("refresh")
                self.pkg("exact-install usertest")
                self.pkg("verify")
                self.pkg("contents -m usertest")

                self.pkg("uninstall usertest")
                self.pkg("verify")
                self.file_doesnt_contain("etc/passwd", "Kermit")
                self.file_doesnt_contain("etc/shadow", "Kermit")

        def test_primordial_usergroup_install(self):
                """Ensure that we can install user and group actions in the same
                transaction as /etc/passwd, /etc/group, etc."""

                self.pkgsend_bulk(self.rurl, [self.baseuser, self.singleuser])

                self.image_create(self.rurl)
                self.pkg("install system/action/user")
                self.pkg("verify")

                self.image_destroy()
                self.image_create(self.rurl)
                self.pkg("install singleuser", exit=1)

        def test_primordial_usergroup_exact_install(self):
                """Ensure that we can exact-install user and group actions in
                the same transaction as /etc/passwd, /etc/group, etc."""

                self.pkgsend_bulk(self.rurl, [self.basics0, self.singleuser])

                self.image_create(self.rurl)
                self.pkg("exact-install basics")
                self.pkg("verify")

                self.image_destroy()
                self.image_create(self.rurl)
                self.pkg("exact-install  basics singleuser")

        def test_ftpuser_install(self):
                """Make sure we correctly handle /etc/ftpd/ftpusers."""

                notftpuser = """
                open notftpuser@1
                add user username=animal group=root ftpuser=false
                close"""

                ftpuserexp = """
                open ftpuserexp@1
                add user username=fozzie group=root ftpuser=true
                close"""

                ftpuserimp = """
                open ftpuserimp@1
                add user username=gonzo group=root
                close"""

                self.pkgsend_bulk(self.rurl, (self.basics0, notftpuser,
                    ftpuserexp, ftpuserimp))
                self.image_create(self.rurl)

                self.pkg("install basics")

                # Add a user with ftpuser=false.  Make sure the user is added to
                # the file, and that the user verifies.
                self.pkg("install notftpuser")
                fpath = self.get_img_path() + "/etc/ftpd/ftpusers"
                with open(fpath) as f:
                        self.assertTrue("animal\n" in f.readlines())
                self.pkg("verify notftpuser")

                # Add a user with an explicit ftpuser=true.  Make sure the user
                # is not added to the file, and that the user verifies.
                self.pkg("install ftpuserexp")
                with open(fpath) as f:
                        self.assertTrue("fozzie\n" not in f.readlines())
                self.pkg("verify ftpuserexp")

                # Add a user with an implicit ftpuser=true.  Make sure the user
                # is not added to the file, and that the user verifies.
                self.pkg("install ftpuserimp")
                with open(fpath) as f:
                        self.assertTrue("gonzo\n" not in f.readlines())
                self.pkg("verify ftpuserimp")

                # Put a user into the ftpusers file as shipped, then add that
                # user, with ftpuser=false.  Make sure the user remains in the
                # file, and that the user verifies.
                self.pkg("uninstall notftpuser")
                with open(fpath, "a") as f:
                        f.write("animal\n")
                self.pkg("install notftpuser")
                with open(fpath) as f:
                        self.assertTrue("animal\n" in f.readlines())
                self.pkg("verify notftpuser")

                # Put a user into the ftpusers file as shipped, then add that
                # user, with an explicit ftpuser=true.  Make sure the user is
                # stripped from the file, and that the user verifies.
                self.pkg("uninstall ftpuserexp")
                with open(fpath, "a") as f:
                        f.write("fozzie\n")
                self.pkg("install ftpuserexp")
                with open(fpath) as f:
                        self.assertTrue("fozzie\n" not in f.readlines())
                self.pkg("verify ftpuserexp")

                # Put a user into the ftpusers file as shipped, then add that
                # user, with an implicit ftpuser=true.  Make sure the user is
                # stripped from the file, and that the user verifies.
                self.pkg("uninstall ftpuserimp")
                with open(fpath, "a") as f:
                        f.write("gonzo\n")
                self.pkg("install ftpuserimp")
                with open(fpath) as f:
                        self.assertTrue("gonzo\n" not in f.readlines())
                self.pkg("verify ftpuserimp")

        def test_groupverify_install(self):
                """Make sure we correctly verify group actions when users have
                been added."""

                simplegroups = """
                open simplegroup@1
                add group groupname=muppets gid=100
                close
                open simplegroup2@1
                add group groupname=muppets2 gid=101
                close"""

                self.pkgsend_bulk(self.rurl, (self.basics0, simplegroups))
                self.image_create(self.rurl)

                self.pkg("install basics")
                self.pkg("install simplegroup")
                self.pkg("verify simplegroup")
                self.file_contains("etc/group", "muppets")

                # add additional members to group & verify
                gpath = self.get_img_file_path("etc/group")
                with open(gpath) as f:
                        gdata = f.readlines()
                gdata[-1] = gdata[-1].rstrip() + "kermit,misspiggy\n"
                with open(gpath, "w") as f:
                        f.writelines(gdata)
                self.pkg("verify simplegroup")
                self.pkg("uninstall simplegroup")
                self.pkg("verify")
                self.file_doesnt_contain("etc/group", "muppets")

                # verify that groups appear in gid order.
                self.pkg("install simplegroup simplegroup2")
                self.pkg("verify")
                with open(gpath) as f:
                        gdata = f.readlines()
                self.assertTrue(gdata[-1].find("muppets2") == 0)
                self.pkg("uninstall simple*")
                self.pkg("install simplegroup2 simplegroup")
                with open(gpath) as f:
                        gdata = f.readlines()
                self.assertTrue(gdata[-1].find("muppets2") == 0)

        def test_preexisting_group_install(self):
                """Make sure we correct any errors in pre-existing group actions"""
                simplegroup = """
                open simplegroup@1
                add group groupname=muppets gid=70
                close
                open simplegroup@2
                add dir path=/etc/muppet owner=root group=muppets mode=755
                add group groupname=muppets gid=70
                close"""

                self.pkgsend_bulk(self.rurl, (self.basics0, simplegroup))
                self.image_create(self.rurl)

                self.pkg("install basics")
                gpath = self.get_img_file_path("etc/group")
                with open(gpath) as f:
                        gdata = f.readlines()
                gdata = ["muppets::1010:\n"] + gdata
                with open(gpath, "w") as f:
                        f.writelines(gdata)
                self.pkg("verify")
                self.pkg("install simplegroup@1")
                self.pkg("verify simplegroup")
                # check # lines beginning w/ 'muppets' in group file
                with open(gpath) as f:
                        gdata = f.readlines()
                self.assertTrue(
                    len([a for a in gdata if a.find("muppets") == 0]) == 1)

                # make sure we can add new version of same package
                self.pkg("update simplegroup")
                self.pkg("verify simplegroup")

        def test_missing_ownergroup_install(self):
                """test what happens when a owner or group is missing"""
                missing = """
                open missing_group@1
                add dir path=etc/muppet1 owner=root group=muppets mode=755
                close
                open missing_owner@1
                add dir path=etc/muppet2 owner=muppets group=root mode=755
                close
                open muppetsuser@1
                add user username=muppets group=bozomuppets uid=777
                close
                open muppetsuser@2
                add user username=muppets group=muppets uid=777
                close
                 open muppetsgroup@1
                add group groupname=muppets gid=777
                close
                """

                self.pkgsend_bulk(self.rurl, (self.basics0, missing))
                self.image_create(self.rurl)
                self.pkg("install basics")

                # try installing directory w/ a non-existing group
                self.pkg("install missing_group@1", exit=1)
                # try installing directory w/ a non-existing owner
                self.pkg("install missing_owner@1", exit=1)
                # try installing user w/ unknown group
                self.pkg("install muppetsuser@1", exit=1)
                # install group
                self.pkg("install muppetsgroup")
                # install working user & see if it all works.
                self.pkg("install muppetsuser@2")
                self.pkg("install missing_group@1")
                self.pkg("install missing_owner@1")
                self.pkg("verify")
                # edit group file to remove muppets group
                gpath = self.get_img_file_path("etc/group")
                with open(gpath) as f:
                        gdata = f.readlines()
                with open(gpath, "w") as f:
                        f.writelines(gdata[0:-1])

                # verify that we catch missing group
                # in both group and user actions
                self.pkg("verify muppetsgroup", 1)
                self.pkg("verify muppetsuser", 1)
                self.pkg("fix muppetsgroup", 0)
                self.pkg("verify muppetsgroup muppetsuser missing*")
                self.pkg("uninstall missing*")
                # try installing w/ broken group

                with open(gpath, "w") as f:
                        f.writelines(gdata[0:-1])
                self.pkg("install missing_group@1", 1)
                self.pkg("fix muppetsgroup")
                self.pkg("install missing_group@1")
                self.pkg("install missing_owner@1")
                self.pkg("verify muppetsgroup muppetsuser missing*")

        def test_userverify_install(self):
                """Make sure we correctly verify user actions when the on-disk
                databases have been modified."""

                simpleusers = """
                open simpleuser@1
                add user username=misspiggy group=root gcos-field="& loves Kermie" login-shell=/bin/sh uid=5
                close
                open simpleuser2@1
                add user username=kermit group=root gcos-field="& loves mspiggy" login-shell=/bin/sh password=UP uid=6
                close
                open simpleuser2@2
                add user username=kermit group=root gcos-field="& loves mspiggy" login-shell=/bin/sh uid=6
                close"""


                self.pkgsend_bulk(self.rurl, (self.basics0, simpleusers))
                self.image_create(self.rurl)

                self.pkg("install basics")
                self.pkg("install simpleuser")
                self.pkg("verify simpleuser")

                ppath = self.get_img_path() + "/etc/passwd"
                with open(ppath) as f:
                        pdata = f.readlines()
                spath = self.get_img_path() + "/etc/shadow"
                with open(spath) as f:
                        sdata = f.readlines()

                def finderr(err):
                        self.assertTrue("\t\tERROR: " + err in self.output)

                # change a provided, empty-default field to something else
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/:/bin/zsh"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("login-shell: '/bin/zsh' should be '/bin/sh'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # change a provided, non-empty-default field to the default
                pdata[-1] = "misspiggy:x:5:0:& User:/:/bin/sh"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("gcos-field: '& User' should be '& loves Kermie'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # change a non-provided, non-empty-default field to something
                # other than the default
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/misspiggy:/bin/sh"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("home-dir: '/misspiggy' should be '/'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # add a non-provided, empty-default field
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/:/bin/sh"
                sdata[-1] = "misspiggy:*LK*:14579:7:::::"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                os.chmod(spath,
                    stat.S_IMODE(os.stat(spath).st_mode)|stat.S_IWUSR)
                with open(spath, "w") as f:
                        f.writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("min: '7' should be '<empty>'")
                # fails fix since we don't repair shadow entries on purpose
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser", exit=1)
                finderr("min: '7' should be '<empty>'")

                # remove a non-provided, non-empty-default field
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie::/bin/sh"
                sdata[-1] = "misspiggy:*LK*:14579::::::"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                with open(spath, "w") as f:
                        f.writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("home-dir: '' should be '/'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove a provided, non-empty-default field
                pdata[-1] = "misspiggy:x:5:0::/:/bin/sh"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("gcos-field: '' should be '& loves Kermie'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove a provided, empty-default field
                pdata[-1] = "misspiggy:x:5:0:& loves Kermie:/:"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("login-shell: '' should be '/bin/sh'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove the user from /etc/passwd
                pdata[-1] = "misswiggy:x:5:0:& loves Kermie:/:"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("login-shell: '<missing>' should be '/bin/sh'")
                finderr("gcos-field: '<missing>' should be '& loves Kermie'")
                finderr("group: '<missing>' should be 'root'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # remove the user completely
                pdata[-1] = "misswiggy:x:5:0:& loves Kermie:/:"
                sdata[-1] = "misswiggy:*LK*:14579::::::"
                with open(ppath, "w") as f:
                        f.writelines(pdata)
                with open(spath, "w") as f:
                        f.writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("username: '<missing>' should be 'misspiggy'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # change the password and show an error
                self.pkg("verify simpleuser")
                sdata[-1] = "misspiggy:NP:14579::::::"
                with open(spath, "w") as f:
                        f.writelines(sdata)
                self.pkg("verify simpleuser", exit=1)
                finderr("password: 'NP' should be '*LK*'")
                self.pkg("fix simpleuser")
                self.pkg("verify simpleuser")

                # verify that passwords set to anything
                # other than '*LK*" or 'NP' in manifest
                # do not cause verify errors if changed.
                self.pkg("install --reject simpleuser simpleuser2@1")
                self.pkg("verify simpleuser2")
                with open(ppath) as f:
                        pdata = f.readlines()
                with open(spath) as f:
                        sdata = f.readlines()
                sdata[-1] = "kermit:$5$pWPEsjm2$GXjBRTjGeeWmJ81ytw3q1ah7QTaI7yJeRYZeyvB.Rp1:14579::::::"
                with open(spath, "w") as f:
                        f.writelines(sdata)
                self.pkg("verify simpleuser2")

                # verify that upgrading package to version that implicitly
                # uses *LK* default causes password to change and that it
                # verifies correctly
                self.pkg("update simpleuser2@2")
                self.pkg("verify simpleuser2")
                with open(spath) as f:
                        sdata = f.readlines()
                sdata[-1].index("*LK*")

                # ascertain that users are added in uid order when
                # installed at the same time.
                self.pkg("uninstall simpleuser2")
                self.pkg("install simpleuser simpleuser2")

                with open(ppath) as f:
                        pdata = f.readlines()
                pdata[-1].index("kermit")

                self.pkg("uninstall simpleuser simpleuser2")
                self.pkg("install simpleuser2 simpleuser")

                with open(ppath) as f:
                        pdata = f.readlines()
                pdata[-1].index("kermit")

        def test_minugid(self):
                """Ensure that an unspecified uid/gid results in the first
                unused."""

                self.minugid_helper("install")
                self.minugid_helper("exact-install")

        def minugid_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.basics0, self.ugidtest))
                self.image_create(self.rurl)

                # This will lay down the sample passwd file, group file, etc.
                self.pkg("install basics")
                if install_cmd == "install":
                        self.pkg("install ugidtest")
                else:
                        self.pkg("exact-install basics ugidtest")
                passwd_file = open(os.path.join(self.get_img_path(),
                    "/etc/passwd"))
                for line in passwd_file:
                        if line.startswith("dummy"):
                                self.assertTrue(line.startswith("dummy:x:5:"))
                passwd_file.close()
                group_file = open(os.path.join(self.get_img_path(),
                    "/etc/group"))
                for line in group_file:
                        if line.startswith("dummy"):
                                self.assertTrue(line.startswith("dummy::5:"))
                group_file.close()

        def test_upgrade_with_user(self):
                """Ensure that we can add a user and change file ownership to
                that user in the same delta (mysql tripped over this early on
                in IPS development)."""

                self.upgrade_with_user_helper("install")
                self.upgrade_with_user_helper("exact-install")

        def upgrade_with_user_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.basics0, self.basics1,
                    self.silver10, self.silver20, self.grouptest))
                self.image_create(self.rurl)
                self.pkg("install basics@1.0")
                self.pkg("{0} basics1@1.0".format(install_cmd))
                self.pkg("{0} silver@1.0".format(install_cmd))
                self.pkg("list silver@1.0")
                self.pkg("verify -v")
                self.pkg("{0} silver@2.0".format(install_cmd))
                self.pkg("verify -v")

        def test_upgrade_garbage_passwd(self):
                self.upgrade_garbage_passwd_helper("install")
                self.upgrade_garbage_passwd_helper("exact-install")

        def upgrade_garbage_passwd_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.basics0, self.singleuser))
                self.image_create(self.rurl)
                pwd_path = os.path.join(self.get_img_path(), "etc/passwd")
                # Put a garbage line in /etc/passwd, and make sure we can
                # install or exact-install, uninstall a user, and preserve the
                # garbage line.  Once with a blank line in the middle, once
                # with a non-blank line with too few fields, once with a
                # non-blank line with too many fields, and once with a blank
                # line at the end.
                for lineno, garbage in ((3, ""), (3, "garbage"),
                    (3, ":::::::::"), (100, "")):
                        garbage += "\n"
                        self.pkg("install basics")
                        with open(pwd_path, "r+") as pwd_file:
                                lines = pwd_file.readlines()
                                lines[lineno:lineno] = garbage
                                pwd_file.truncate(0)
                                pwd_file.seek(0)
                                pwd_file.writelines(lines)
                        if install_cmd == "install":
                                self.pkg("{0} singleuser".format(install_cmd))
                        else:
                                self.pkg("{0} basics singleuser".format(install_cmd))
                        with open(pwd_path) as pwd_file:
                                lines = pwd_file.readlines()
                                self.assertTrue(garbage in lines)
                        self.pkg("uninstall singleuser")
                        with open(pwd_path) as pwd_file:
                                lines = pwd_file.readlines()
                                self.assertTrue(garbage in lines)

                        self.pkg("uninstall '*'")

        def test_user_in_grouplist(self):
                """If a user is present in a secondary group list when the user
                is installed, the client shouldn't crash."""

                self.user_in_grouplist_helper("install")
                self.user_in_grouplist_helper("exact-install")

        def user_in_grouplist_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.basics0, self.only_user10))
                self.image_create(self.rurl)
                self.pkg("install basics@1.0")
                group_path = os.path.join(self.get_img_path(), "etc/group")
                with open(group_path, "r+") as group_file:
                        lines = group_file.readlines()
                        lines[0] = lines[0][:-1] + "Kermit" + "\n"
                        group_file.truncate(0)
                        group_file.seek(0)
                        group_file.writelines(lines)
                if install_cmd == "install":
                        self.pkg("install only_user@1.0")
                else:
                        self.pkg("exact-install basics@1.0 only_user@1.0")

        def test_invalid_open(self):
                """Send invalid package definitions (invalid fmris); expect
                failure."""

                for char in self.pkg_name_valid_chars["never"]:
                        invalid_name = "invalid{0}pkg@1.0,5.11-0".format(char)
                        self.pkgsend(self.rurl, "open '{0}'".format(invalid_name),
                            exit=1)

                for char in self.pkg_name_valid_chars["after-first"]:
                        invalid_name = "{0}invalidpkg@1.0,5.11-0".format(char)
                        if char == "-":
                                cmd = "open -- '{0}'".format(invalid_name)
                        else:
                                cmd = "open '{0}'".format(invalid_name)
                        self.pkgsend(self.rurl, cmd, exit=1)

                        invalid_name = "invalid/{0}pkg@1.0,5.11-0".format(char)
                        cmd = "open '{0}'".format(invalid_name)
                        self.pkgsend(self.rurl, cmd, exit=1)

        def test_valid_open(self):
                """Send a series of valid packages; expect success."""

                for char in self.pkg_name_valid_chars["always"]:
                        valid_name = "{0}valid{1}/{2}pkg{3}@1.0,5.11-0".format(char,
                            char, char, char)
                        self.pkgsend(self.rurl, "open '{0}'".format(valid_name))
                        self.pkgsend(self.rurl, "close -A")

                for char in self.pkg_name_valid_chars["after-first"]:
                        valid_name = "v{0}alid{1}pkg@1.0,5.11-0".format(char, char)
                        self.pkgsend(self.rurl, "open '{0}'".format(valid_name))
                        self.pkgsend(self.rurl, "close -A")

                for char in self.pkg_name_valid_chars["at-end"]:
                        valid_name = "validpkg{0}@1.0,5.11-0".format(char)
                        self.pkgsend(self.rurl, "open '{0}'".format(valid_name))
                        self.pkgsend(self.rurl, "close -A")

        def test_devlink(self):
                self.devlink_helper("install")
                self.devlink_helper("exact-install")

        def devlink_helper(self, install_cmd):
                # driver actions are not valid except on OpenSolaris
                if portable.util.get_canonical_os_name() != "sunos":
                        return

                self.pkgsend_bulk(self.rurl, (self.devicebase, self.devlink10,
                    self.devlink20))
                self.image_create(self.rurl)

                def readfile():
                        dlf = open(os.path.join(self.get_img_path(),
                            "etc/devlink.tab"))
                        dllines = dlf.readlines()
                        dlf.close()
                        return dllines

                def writefile(dllines):
                        dlf = open(os.path.join(self.get_img_path(),
                            "etc/devlink.tab"), "w")
                        dlf.writelines(dllines)
                        dlf.close()

                def assertContents(dllines, contents):
                        actual = re.findall("name=([^\t;]*)",
                            "\n".join(dllines), re.M)
                        self.assertTrue(set(actual) == set(contents))

                # Install
                self.pkg("install devlinktest@1.0")
                self.pkg("verify -v")

                dllines = readfile()

                # Verify that three entries got added
                self.assertTrue(len(dllines) == 3)

                # Verify that the tab character got written correctly
                self.assertTrue(dllines[0].find("\t") > 0)

                # Upgrade
                self.pkg("{0} devlinktest@2.0".format(install_cmd))
                self.pkg("verify -v")

                dllines = readfile()

                # Verify that there are four entries now
                self.assertTrue(len(dllines) == 4)

                # Verify they are what they should be
                assertContents(dllines, ["zerg2", "zorg", "borg", "zork"])

                # Remove
                self.pkg("uninstall devlinktest")
                self.pkg("verify -v")

                # Install again
                self.pkg("install devlinktest@1.0")

                # Diddle with it
                dllines = readfile()
                for i, line in enumerate(dllines):
                        if line.find("zerg") != -1:
                                dllines[i] = "type=ddi_pseudo;name=zippy\t\D\n"
                writefile(dllines)

                # Upgrade
                self.pkg("{0} devlinktest@2.0".format(install_cmd))

                # Verify that we spewed a message on upgrade
                self.assertTrue(self.output.find("not found") != -1)
                self.assertTrue(self.output.find("name=zerg") != -1)

                # Verify the new set
                dllines = readfile()
                self.assertTrue(len(dllines) == 5)
                assertContents(dllines,
                    ["zerg2", "zorg", "borg", "zork", "zippy"])

                self.pkg("uninstall devlinktest")

                # Null out the "zippy" entry
                writefile([])

                # Install again
                self.pkg("install devlinktest@1.0")

                # Diddle with it
                dllines = readfile()
                for i, line in enumerate(dllines):
                        if line.find("zerg") != -1:
                                dllines[i] = "type=ddi_pseudo;name=zippy\t\D\n"
                writefile(dllines)

                # Remove
                self.pkg("uninstall devlinktest")

                # Verify that we spewed a message on removal
                self.assertTrue(self.output.find("not found") != -1)
                self.assertTrue(self.output.find("name=zerg") != -1)

                # Verify that the one left behind was the one we overwrote.
                dllines = readfile()
                self.assertTrue(len(dllines) == 1)
                assertContents(dllines, ["zippy"])

                # Null out the "zippy" entry, but add the "zerg" entry
                writefile(["type=ddi_pseudo;name=zerg\t\D\n"])

                # Install ... again
                self.pkg("install devlinktest@1.0")

                # Make sure we didn't get a second zerg line
                dllines = readfile()
                self.assertTrue(len(dllines) == 3, msg=dllines)
                assertContents(dllines, ["zerg", "borg", "warg"])

                # Now for the same test on upgrade
                dllines.append("type=ddi_pseudo;name=zorg\t\D\n")
                writefile(dllines)

                self.pkg("{0} devlinktest@2.0".format(install_cmd))
                dllines = readfile()
                self.assertTrue(len(dllines) == 4, msg=dllines)
                assertContents(dllines, ["zerg2", "zorg", "borg", "zork"])

        def test_driver_aliases_upgrade(self):
                """Make sure that aliases properly appear and disappear on
                upgrade.  This is the result of a bug in update_drv, but it's
                not a bad idea to test some of this ourselves."""

                self.driver_aliases_upgrade_helper("install")
                self.driver_aliases_upgrade_helper("exact-install")

        def driver_aliases_upgrade_helper(self, install_cmd):
                # driver actions are not valid except on OpenSolaris
                if portable.util.get_canonical_os_name() != "sunos":
                        return

                self.pkgsend_bulk(self.rurl, [self.devicebase, self.devalias10,
                    self.devalias20])

                self.image_create(self.rurl)
                self.pkg("{0} devicebase devalias@1".format(install_cmd))
                self.pkg("update devalias")
                self.pkg("verify devalias")

                daf = open(os.path.join(self.get_img_path(),
                    "etc/driver_aliases"))
                dalines = daf.readlines()
                daf.close()

                self.assertTrue(len(dalines) == 1, msg=dalines)
                self.assertTrue(",1234" not in dalines[0])
                self.assertTrue(",4321" not in dalines[0])
                self.assertTrue(",5555" in dalines[0])

        def test_driver_aliases_move(self):
                """Make sure that an alias can be moved from one driver action
                to another."""

                self.driver_aliases_move_helper("install")
                self.driver_aliases_move_helper("exact-install")

        def driver_aliases_move_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, [self.devicebase,
                    self.devaliasmove10, self.devaliasmove20])

                self.image_create(self.rurl)
                self.pkg("{0} devicebase devaliasmove@1".format(install_cmd))
                self.pkg("update devaliasmove")
                self.assertTrue("pci8086,5555" not in self.output)

        def test_uninstall_without_perms(self):
                """Verify uninstall fails as expected for unprivileged users."""

                pkg_list = [self.foo10, self.only_attr10, self.only_depend10,
                    self.only_directory10, self.only_file10,
                    self.only_group10, self.only_hardlink10, self.only_legacy10,
                    self.only_license10, self.only_link10, self.only_user10]

                # driver actions are not valid except on OpenSolaris
                if portable.util.get_canonical_os_name() == 'sunos':
                        pkg_list += [self.only_driver10]

                self.pkgsend_bulk(self.rurl, pkg_list + [
                    self.devicebase + self.basics0 + self.basics1])

                self.image_create(self.rurl)

                name_pat = re.compile("^\s+open\s+(\S+)\@.*$")

                def __manually_check_deps(name, install=True, exit=0):
                        cmd = ["install", "--no-refresh"]
                        if not install:
                                cmd = ["uninstall"]
                        if name == "only_depend" and not install:
                                self.pkg(cmd + ["foo"], exit=exit)
                        elif name == "only_driver":
                                self.pkg(cmd + ["devicebase"], exit=exit)
                        elif name == "only_group":
                                self.pkg(cmd + ["basics"], exit=exit)
                        elif name == "only_hardlink":
                                self.pkg(cmd + ["only_file"], exit=exit)
                        elif name == "only_user":
                                if install:
                                        self.pkg(cmd + ["basics"], exit=exit)
                                        self.pkg(cmd + ["only_group"],
                                            exit=exit)
                                else:
                                        self.pkg(cmd + ["only_group"],
                                            exit=exit)
                                        self.pkg(cmd + ["basics"], exit=exit)
                for p in pkg_list:
                        name_mat = name_pat.match(p.splitlines()[1])
                        pname = name_mat.group(1)
                        __manually_check_deps(pname, exit=[0, 4])
                        self.pkg(["install", "--no-refresh", pname],
                            su_wrap=True, exit=1)
                        self.pkg(["install", pname], su_wrap=True,
                            exit=1)
                        self.pkg(["install", "--no-refresh", pname])
                        self.pkg(["uninstall", pname], su_wrap=True,
                            exit=1)
                        self.pkg(["uninstall", pname])
                        __manually_check_deps(pname, install=False)

                for p in pkg_list:
                        name_mat = name_pat.match(p.splitlines()[1])
                        pname = name_mat.group(1)
                        __manually_check_deps(pname, exit=[0, 4])
                        self.pkg(["install", "--no-refresh", pname])

                for p in pkg_list:
                        self.pkgsend_bulk(self.rurl, p)
                self.pkgsend_bulk(self.rurl, (self.devicebase, self.basics0,
                    self.basics1))

                # Modifying operations require permissions needed to create and
                # manage lock files.
                self.pkg(["update", "--no-refresh"], su_wrap=True, exit=1)

                self.pkg(["refresh"])
                self.pkg(["update"], su_wrap=True, exit=1)
                # Should fail since user doesn't have permission to refresh
                # publisher metadata.
                self.pkg(["refresh", "--full"], su_wrap=True, exit=1)
                self.pkg(["refresh", "--full"])
                self.pkg(["update", "--no-refresh"], su_wrap=True,
                    exit=1)
                self.pkg(["update"])

        def test_bug_3222(self):
                """ Verify that a timestamp of '0' for a passwd file will not
                    cause further package operations to fail.  This can happen
                    when there are time synchronization issues within a virtual
                    environment or in other cases. """

                self.pkgsend_bulk(self.rurl, (self.basics0, self.only_user10,
                    self.only_user_file10, self.only_group10,
                    self.only_group_file10, self.grouptest, self.usertest10))
                self.image_create(self.rurl)
                fname = os.path.join(self.get_img_path(), "etc", "passwd")
                self.pkg("install basics")

                # This should work regardless of whether a user is installed
                # at the same time as the file in a package, or if the user is
                # installed first and then files owned by that user are
                # installed.
                plists = [["grouptest", "usertest"],
                    ["only_user", "only_user_file"],
                    ["only_group", "only_group_file"]]
                for plist in plists:
                        for pname in plist:
                                os.utime(fname, (0, 0))
                                self.pkg("install {0}".format(pname))
                                self.pkg("verify")

                        for pname in reversed(plist):
                                os.utime(fname, (0, 0))
                                self.pkg("uninstall {0}".format(pname))
                                self.pkg("verify")

        def test_bad_hardlinks(self):
                """A couple of bogus hard link target tests."""

                self.bad_hardlinks_helper("install")
                self.bad_hardlinks_helper("exact-install")

        def bad_hardlinks_helper(self, install_cmd):
                self.pkgsend_bulk(self.rurl, (self.badhardlink1,
                    self.badhardlink2))
                self.image_create(self.rurl)

                # A package which tries to install a hard link to a target that
                # doesn't exist shouldn't stack trace, but exit sanely.
                self.pkg("{0} badhardlink1".format(install_cmd), exit=1)

                # A package which tries to install a hard link to a target
                # specified as an absolute path should install that link
                # relative to the image root.
                self.pkg("{0} badhardlink2".format(install_cmd))
                ino1 = os.stat(os.path.join(self.get_img_path(), "foo")).st_ino
                ino2 = os.stat(os.path.join(self.get_img_path(), "etc/motd")).st_ino
                self.assertTrue(ino1 == ino2)

        def test_legacy(self):
                self.pkgsend_bulk(self.rurl,
                    (self.csu1, self.csu1_2, self.csu2, self.csu2_2,
                    self.csu3, self.csu3_2))
                self.image_create(self.rurl)

                self.pkg("install csu1@1 csu2@1 csu3@1")

                # Make sure we installed one and only one pkginfo file, and with
                # the correct information.
                vsp = self.get_img_file_path("var/sadm/pkg")
                pi = os.path.join(vsp, "SUNWcsu/pkginfo")
                pi2 = os.path.join(vsp, "SUNWcsu/pkginfo.2")
                pi3 = os.path.join(vsp, "SUNWcsu/pkginfo.3")
                self.assertTrue(os.path.exists(pi), "pkginfo doesn't exist")
                self.file_contains(pi, "VERSION=11.11,REV=2009.11.11")
                self.assertTrue(not os.path.exists(pi2), "pkginfo.2 exists")
                self.assertTrue(not os.path.exists(pi3), "pkginfo.3 exists")
                # Create the hardlinks as we'd have for the old refcounting
                # system.
                os.link(pi, pi2)
                os.link(pi, pi3)

                # Make sure that upgrading the actions modifies the pkginfo file
                # correctly, and that the hardlinks go away.
                self.pkg("update")
                self.file_contains(pi, "VERSION=11.11,REV=2010.11.11")
                self.assertTrue(not os.path.exists(pi2), "pkginfo.2 exists")
                self.assertTrue(not os.path.exists(pi3), "pkginfo.3 exists")

                # Start over, but this time "break" the hardlinks.
                self.pkg("uninstall -vvv \*")
                self.pkg("install csu1@1 csu2@1 csu3@1")
                shutil.copy(pi, pi2)
                shutil.copy(pi, pi3)
                self.pkg("update")
                self.file_contains(pi, "VERSION=11.11,REV=2010.11.11")
                self.assertTrue(not os.path.exists(pi2), "pkginfo.2 exists")
                self.assertTrue(not os.path.exists(pi3), "pkginfo.3 exists")


class TestDependencies(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkg10 = """
            open pkg1@1.0,5.11-0
            add depend type=optional fmri=pkg:/pkg2
            close
        """

        pkg20 = """
            open pkg2@1.0,5.11-0
            close
        """

        pkg11 = """
            open pkg1@1.1,5.11-0
            add depend type=optional fmri=pkg:/pkg2@1.1
            close
        """

        pkg21 = """
            open pkg2@1.1,5.11-0
            close
        """

        pkg30 = """
            open pkg3@1.0,5.11-0
            add depend type=require fmri=pkg:/pkg1@1.1
            close
        """

        pkg40 = """
            open pkg4@1.0,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            close
        """

        pkg50 = """
            open pkg5@1.0,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            add depend type=require fmri=pkg:/pkg1@1.0
            close
        """

        pkg505 = """
            open pkg5@1.0.5,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            add depend type=require fmri=pkg:/pkg1@1.0
            close
        """
        pkg51 = """
            open pkg5@1.1,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            add depend type=exclude fmri=pkg:/pkg2
            add depend type=require fmri=pkg:/pkg1@1.0
            close
        """
        pkg60 = """
            open pkg6@1.0,5.11-0
            add depend type=exclude fmri=pkg:/pkg1@1.1
            close
        """

        pkg61 = """
            open pkg6@1.1,5.11-0
            close
        """

        bug_18653 = """
            open entire@1.0,5.11-0
            add depend type=incorporate fmri=osnet-incorporation@1.0
            close
            open entire@1.1,5.11-0
            add depend type=incorporate fmri=osnet-incorporation@1.1
            close
            open osnet-incorporation@1.0,5.11-0
            add depend type=incorporate fmri=sun-solaris@1.0
            add depend type=incorporate fmri=sun-solaris-510@1.0
            close
            open osnet-incorporation@1.1,5.11-0
            add depend type=incorporate fmri=sun-solaris@1.1
            add depend type=incorporate fmri=sun-solaris-510@1.1
            close
            open sun-solaris@1.0,5.11-0
            add depend type=require fmri=osnet-incorporation
            add depend type=conditional predicate=perl-510 fmri=sun-solaris-510@1.0
            close
            open sun-solaris@1.1,5.11-0
            add depend type=require fmri=osnet-incorporation
            add depend type=conditional predicate=perl-510 fmri=sun-solaris-510@1.1
            close
            open sun-solaris-510@1.0,5.11-0
            add depend type=require fmri=osnet-incorporation
            add depend type=require fmri=perl-510@1.0
            close
            open perl-510@1.0,5.11-0
            close
            open perl-510@1.1,5.11-0
            close
        """

        pkg70 = """
            open pkg7@1.0,5.11-0
            add depend type=conditional predicate=pkg:/pkg2@1.1 fmri=pkg:/pkg6@1.1
            close
        """

        pkg80 = """
            open pkg8@1.0,5.11-0
            add depend type=require-any fmri=pkg:/pkg9@1.0 fmri=pkg:/pkg2@1.1 fmri=pkg:/nonsuch
            close
        """

        pkg81 = """
            open pkg8@1.1,5.11-0
            add depend type=require-any fmri=pkg:/pkg9@1.1 fmri=pkg:/pkg2@1.1 fmri=pkg:/nonsuch
            close
        """

        pkg90 = """
            open pkg9@1.0,5.11-0
            close
        """

        pkg91 = """
            open pkg9@1.1,5.11-0
            close
        """

        pkg100 = """
            open pkg10@1.0,5.11-0
            close
        """

        pkg101 = """
            open pkg10@1.1,5.11-0
            close
        """

        pkg102 = """
            open pkg10@1.2,5.11-0
            add depend type=origin fmri=pkg10@1.1,5.11-0
            close
        """

        pkg110 = """
            open pkg11@1.0,5.11-0
            add depend type=origin root-image=true fmri=SUNWcs@0.5.11-0.75
            close
        """
        pkg111 = """
            open pkg11@1.1,5.11-0
            add depend type=origin root-image=true fmri=SUNWcs@0.5.11-1.0
            close
        """

        pkg121 = """
            open pkg12@1.1,5.11-0
        """
        pkg121 += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        pkg121 += """
            close
        """

        pkg122 = """
            open pkg12@1.2,5.11-0
        """
        pkg122 += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        pkg122 += """
            close
        """

        pkg123 = """
            open pkg12@1.3,5.11-0
        """
        pkg123 += "add depend type=parent fmri={0}".format(
            pkg.actions.depend.DEPEND_SELF)
        pkg123 += """
            close
        """

        pkg132 = """
            open pkg13@1.2,5.11-0
            add depend type=parent fmri=pkg12@1.2,5.11-0
            close
        """

        pkg142 = """
            open pkg14@1.2,5.11-0
            add depend type=parent fmri=pkg12@1.2,5.11-0
            add depend type=parent fmri=pkg13@1.2,5.11-0
            close
        """

        pkg_nosol = """
            open pkg-nosol-A@1.0,5.11-0
            add depend type=require-any fmri=pkg:/pkg-nosol-B fmri=pkg:/pkg-nosol-C
            add depend type=require fmri=pkg:/pkg-nosol-D
            close
            open pkg-nosol-B@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkg-nosol-E@2.0
            close
            open pkg-nosol-C@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkg-nosol-E@2.0
            close
            open pkg-nosol-D@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkg-nosol-E@1.0
            close
            open pkg-nosol-E@1.0,5.11-0
            close
            open pkg-nosol-E@2.0,5.11-0
            close
        """

        pkg_renames = """
            open pkg_need_rename@1.0,5.11-0
            add depend type=require fmri=pkg_rename
            close
            open pkg_rename@1.0,5.11-0
            add set name=pkg.renamed value=true
            add depend type=require fmri=pkg:/pkg_bar
            close
            open pkg_bar@1.0,5.11-0
            close
            open trusted@1.0,5.11-0
            add set name=pkg.renamed value=true
            add depend type=require fmri=system/trusted@1.0
            close
            open system/trusted@1.0,5.11-0
            close
        """

        pkgSUNWcs075 = """
            open SUNWcs@0.5.11-0.75
            close
        """

        leaf_template = """
            open pkg{0}{1}@{2},5.11-0
            add depend type=require fmri=pkg:/{3}_incorp{4}
            close
        """
        install_hold = "add set name=pkg.depend.install-hold value=test"

        leaf_expansion = [
                ("A","_0", "1.0", "A", ""),
                ("A","_1", "1.0", "A", ""),
                ("A","_2", "1.0", "A", ""),
                ("A","_3", "1.0", "A", ""),

                ("B","_0", "1.0", "B", ""),
                ("B","_1", "1.0", "B", ""),
                ("B","_2", "1.0", "B", ""),
                ("B","_3", "1.0", "B", ""),

                ("A","_0", "1.1", "A", "@1.1"),
                ("A","_1", "1.1", "A", "@1.1"),
                ("A","_2", "1.1", "A", "@1.1"),
                ("A","_3", "1.1", "A", "@1.1"),

                ("B","_0", "1.1", "B", "@1.1"),
                ("B","_1", "1.1", "B", "@1.1"),
                ("B","_2", "1.1", "B", "@1.1"),
                ("B","_3", "1.1", "B", "@1.1"),

                ("A","_0", "1.2", "A", "@1.2"),
                ("A","_1", "1.2", "A", "@1.2"),
                ("A","_2", "1.2", "A", "@1.2"),
                ("A","_3", "1.2", "A", "@1.2"),

                ("B","_0", "1.2", "B", "@1.2"),
                ("B","_1", "1.2", "B", "@1.2"),
                ("B","_2", "1.2", "B", "@1.2"),
                ("B","_3", "1.2", "B", "@1.2"),

                ("A","_0", "1.3", "A", ""),
                ("A","_1", "1.3", "A", ""),
                ("A","_2", "1.3", "A", ""),
                ("A","_3", "1.3", "A", ""),

                ("B","_0", "1.3", "B", ""),
                ("B","_1", "1.3", "B", ""),
                ("B","_2", "1.3", "B", ""),
                ("B","_3", "1.3", "B", "")
                ]

        incorps = [ """
            open A_incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.0
            add depend type=incorporate fmri=pkg:/pkgA_1@1.0
            add depend type=incorporate fmri=pkg:/pkgA_2@1.0
            add depend type=incorporate fmri=pkg:/pkgA_3@1.0
            close
        """,

        """
            open B_incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.0
            add depend type=incorporate fmri=pkg:/pkgB_1@1.0
            add depend type=incorporate fmri=pkg:/pkgB_2@1.0
            add depend type=incorporate fmri=pkg:/pkgB_3@1.0
            close
        """,

        """
            open A_incorp@1.1,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.1
            add depend type=incorporate fmri=pkg:/pkgA_1@1.1
            add depend type=incorporate fmri=pkg:/pkgA_2@1.1
            add depend type=incorporate fmri=pkg:/pkgA_3@1.1
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open B_incorp@1.1,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.1
            add depend type=incorporate fmri=pkg:/pkgB_1@1.1
            add depend type=incorporate fmri=pkg:/pkgB_2@1.1
            add depend type=incorporate fmri=pkg:/pkgB_3@1.1
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open A_incorp@1.2,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.2
            add depend type=incorporate fmri=pkg:/pkgA_1@1.2
            add depend type=incorporate fmri=pkg:/pkgA_2@1.2
            add depend type=incorporate fmri=pkg:/pkgA_3@1.2
            add set name=pkg.depend.install-hold value=test.A
            close
        """,

        """
            open B_incorp@1.2,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.2
            add depend type=incorporate fmri=pkg:/pkgB_1@1.2
            add depend type=incorporate fmri=pkg:/pkgB_2@1.2
            add depend type=incorporate fmri=pkg:/pkgB_3@1.2
            add set name=pkg.depend.install-hold value=test.B
            close
        """,

        """
            open A_incorp@1.3,5.11-0
            add depend type=incorporate fmri=pkg:/pkgA_0@1.3
            add depend type=incorporate fmri=pkg:/pkgA_1@1.3
            add depend type=incorporate fmri=pkg:/pkgA_2@1.3
            add depend type=incorporate fmri=pkg:/pkgA_3@1.3
            add set name=pkg.depend.install-hold value=test.A
            close
        """,

        """
            open B_incorp@1.3,5.11-0
            add depend type=incorporate fmri=pkg:/pkgB_0@1.3
            add depend type=incorporate fmri=pkg:/pkgB_1@1.3
            add depend type=incorporate fmri=pkg:/pkgB_2@1.3
            add depend type=incorporate fmri=pkg:/pkgB_3@1.3
            add set name=pkg.depend.install-hold value=test.B
            close
        """,

        """
            open incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.0
            add depend type=incorporate fmri=pkg:/B_incorp@1.0
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open incorp@1.1,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.1
            add depend type=incorporate fmri=pkg:/B_incorp@1.1
            add set name=pkg.depend.install-hold value=test
            close
        """,

        """
            open incorp@1.2,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.2
            add depend type=incorporate fmri=pkg:/B_incorp@1.2
            add set name=pkg.depend.install-hold value=test
            close
        """,
        """
            open incorp@1.3,5.11-0
            add depend type=incorporate fmri=pkg:/A_incorp@1.3
            add depend type=exclude fmri=pkg:/pkgB_0
            add set name=pkg.depend.install-hold value=test
            close
        """
        ]

        bug_7394_incorp = """
            open bug_7394_incorp@1.0,5.11-0
            add depend type=incorporate fmri=pkg:/pkg1@2.0
            close
        """

        exclude_group = """
            open network/rsync@1.0
            close
            open gold-server@1.0
            add depend type=group fmri=network/rsync
            close
            open utility/my-rsync@1.0
            add depend type=exclude fmri=network/rsync
            close
        """

        optional_group = """
            open consolidation/desktop/desktop-incorporation@0.5.11-0.175.3.0.0.28.0
            add depend type=incorporate fmri=communication/im/pidgin@2.10.11-0.175.3.0.0.26.0
            close
            open communication/im/pidgin@2.10.11-0.175.3.0.0.26.0
            add depend type=require fmri=consolidation/desktop/desktop-incorporation
            close
            open communication/im/pidgin@2.10.11-5.12.0.0.0.90.0
            add depend type=require fmri=consolidation/desktop/desktop-incorporation
            close
            open group/feature/multi-user-desktop@5.12-5.12.0.0.0.94.0
            add depend type=group fmri=communication/im/pidgin
            close
            open communication/im/libotr@4.1.0-5.12.0.0.0.94.0
            add depend type=optional fmri=communication/im/pidgin@2.10.11-5.12.0.0.0.88.0
            close
        """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, image_count=2)
                self.pkgsend_bulk(self.rurl, (self.pkg10, self.pkg20,
                    self.pkg11, self.pkg21, self.pkg30, self.pkg40, self.pkg50,
                    self.pkg505, self.pkg51, self.pkg60, self.pkg61,
                    self.bug_18653, self.pkg70, self.pkg80, self.pkg81,
                    self.pkg90, self.pkg91, self.bug_7394_incorp, self.pkg100,
                    self.pkg101, self.pkg102, self.pkg110, self.pkg111,
                    self.pkg121, self.pkg122, self.pkg123, self.pkg132,
                    self.pkg142, self.pkg_nosol, self.pkg_renames,
                    self.pkgSUNWcs075, self.exclude_group,
                    self.optional_group))

                self.leaf_pkgs = []
                for t in self.leaf_expansion:
                        self.leaf_pkgs.extend(self.pkgsend_bulk(self.rurl,
                            self.leaf_template.format(*t)))

                self.incorp_pkgs = []
                for i in self.incorps:
                        self.incorp_pkgs.extend(self.pkgsend_bulk(self.rurl, i))

        def test_rename_matching(self):
                """Verify install or exact-install won't fail with a multiple
                match error for a renamed package that shares a common
                basename."""

                self.rename_matching("install")
                self.rename_matching("exact-install")

        def rename_matching(self, install_cmd):
                self.image_create(self.rurl)
                self.pkg("{0} trusted".format(install_cmd))
                self.pkg("info system/trusted")

        def test_require_dependencies(self):
                """ exercise require dependencies """

                self.require_dependencies_helper("install")
                self.require_dependencies_helper("exact-install")

        def require_dependencies_helper(self, install_cmd):
                self.image_create(self.rurl)
                self.pkg("install pkg1@1.0")
                self.pkg("verify  pkg1@1.0")
                self.pkg("{0} pkg3@1.0".format(install_cmd))
                self.pkg("verify  pkg3@1.0 pkg1@1.1")

        def test_exclude_group_install(self):
                """Verify that a simultaneous exclude and group dependency on
                the same package is handled gracefully."""

                self.image_create(self.rurl)

                # These should fail (gracefully) because my-rsync packages
                # excludes network/rsync which is a group dependency of
                # gold-server package.
                self.pkg("install network/rsync gold-server my-rsync", exit=1)

                self.pkg("install network/rsync")
                self.pkg("install gold-server my-rsync", exit=1)
                self.pkg("uninstall '*'")

                # This should succeed because network/rsync dependency is not
                # installed.
                self.pkg("avoid network/rsync")
                self.pkg("install -nv gold-server my-rsync")

                # This will install network/rsync and remove it from the avoid
                # list.
                self.pkg("install network/rsync")

                # This should succeed because network/rsync will be removed and
                # placed on avoid list as part of operation.
                self.pkg("install --reject network/rsync gold-server my-rsync")

                # Now remove gold-server and then verify install will fail.
                self.pkg("uninstall gold-server")
                self.pkg("unavoid network/rsync")

                # This should fail as there's no installed constraining package
                # and user didn't provide sufficient input.
                self.pkg("install gold-server", exit=1)

        def test_exclude_dependencies_install(self):
                """ exercise exclude dependencies """

                self.image_create(self.rurl)
                # install pkg w/ exclude dep.
                self.pkg("install pkg4@1.0")
                self.pkg("verify  pkg4@1.0")
                # install pkg that is allowed by dep
                self.pkg("install pkg1@1.0")
                self.pkg("verify  pkg1@1.0")
                # try to install disallowed pkg
                self.pkg("install pkg1@1.1", exit=1)
                self.pkg("uninstall '*'")
                # install pkg
                self.pkg("install pkg1@1.1")
                # try to install pkg exclude dep on already
                # installed pkg
                self.pkg("install pkg4@1.0", exit=1)
                self.pkg("uninstall '*'")
                # install a package w/ both exclude
                # and require dependencies
                self.pkg("install pkg5")
                self.pkg("verify pkg5@1.1 pkg1@1.0 ")
                self.pkg("uninstall '*'")
                # pick pkg to install that fits constraint
                # of already installed pkg
                self.pkg("install pkg2")
                self.pkg("install pkg5")
                self.pkg("verify pkg5@1.0.5 pkg1@1.0 pkg2")
                self.pkg("uninstall '*'")
                # install a package that requires updating
                # existing package to avoid exclude
                # dependency
                self.pkg("install pkg6@1.0")
                self.pkg("install pkg1@1.1")
                self.pkg("verify pkg1@1.1 pkg6@1.1")
                self.pkg("uninstall '*'")
                # try to install two incompatible pkgs
                self.pkg("install pkg1@1.1 pkg4@1.0", exit=1)

        def test_exclude_dependencies_exact_install(self):
                """ exercise exclude dependencies """

                self.image_create(self.rurl)
                # Install pkg w/ exclude dep.
                self.pkg("install pkg4@1.0")
                self.pkg("verify  pkg4@1.0")

                # Exact-install should ignore exclude dependencies,
                # except user specifies both pkg name in command line.
                self.pkg("exact-install pkg1@1.1")
                self.pkg("uninstall '*'")

                # Exact-install a package w/ both exclude
                # and require dependencies.
                self.pkg("exact-install pkg5")
                self.pkg("verify pkg5@1.1 pkg1@1.0 ")
                self.pkg("uninstall '*'")
                # pick pkg to exact-install that fits constraint.
                self.pkg("exact-install pkg2 pkg5")
                self.pkg("verify pkg5@1.0.5 pkg1@1.0 pkg2")
                self.pkg("uninstall '*'")
                # Exact- install two packages with proper version selected for
                # one package based on the version of the other package.
                self.pkg("exact-install pkg6 pkg1@1.1")
                self.pkg("verify pkg1@1.1 pkg6@1.1")
                self.pkg("uninstall '*'")
                # try to exact-install two incompatible pkgs
                self.pkg("exact-install pkg1@1.1 pkg4@1.0", exit=1)

        def test_optional_dependencies_install(self):
                """ check to make sure that optional dependencies are enforced
                """

                self.image_create(self.rurl)
                self.pkg("install pkg1@1.0")

                # pkg2 is optional, it should not have been installed
                self.pkg("list pkg2", exit=1)

                self.pkg("install pkg2@1.0")

                # this should install pkg1@1.1 and upgrade pkg2 to pkg2@1.1
                self.pkg("install pkg1")
                self.pkg("list pkg2@1.1")

                self.pkg("uninstall pkg2")
                self.pkg("list pkg2", exit=1)
                # this should not install pkg2@1.0 because of the optional
                # dependency in pkg1
                self.pkg("list pkg1@1.1")
                self.pkg("install pkg2@1.0", exit=1)

        def test_optional_dependencies_exact_install(self):
                """ check to make sure that optional dependencies are enforced
                """

                self.image_create(self.rurl)
                self.pkg("exact-install pkg1@1.0")

                # pkg2 is optional, it should not have been installed
                self.pkg("list pkg2", exit=1)

                self.pkg("install pkg2@1.1")

                # Verify with exact-install, the optional dependency package
                # should be removed.
                self.pkg("exact-install pkg1")
                self.pkg("list pkg2@1.1", exit=1)
                self.pkg("list pkg1@1.1")

                # Verify exact-install pkg2@1.0 should succeed and pkg1 should
                # be removed.
                self.pkg("exact-install pkg2@1.0")
                self.pkg("list pkg1", exit=1)

        def test_incorporation_dependencies_install(self):
                """ shake out incorporation dependencies """

                self.image_create(self.rurl)
                # simple pkg requiring controlling incorp
                # should control pkgA_1 as well
                self.pkg("install -v pkgA_0@1.0 pkgA_1")
                self.pkg("list")
                self.pkg("verify pkgA_0@1.0 pkgA_1@1.0 A_incorp@1.0")
                self.pkg("install A_incorp@1.1")
                self.pkg("list pkgA_0@1.1 pkgA_1@1.1 A_incorp@1.1")
                self.pkg("uninstall '*'")
                # try nested incorporations
                self.pkg("install -v incorp@1.0 pkgA_0 pkgB_0")
                self.pkg("list")
                self.pkg("list incorp@1.0 pkgA_0@1.0 pkgB_0@1.0 A_incorp@1.0 B_incorp@1.0")
                # try to break incorporation
                self.pkg("install -v A_incorp@1.1", exit=1) # fixed by incorp@1.0
                # try update (using '*' which also checks that the update all
                # path is used when '*' is specified)
                self.pkg("update -v '*'")
                self.pkg("list incorp@1.2")
                self.pkg("list pkgA_0@1.2")
                self.pkg("list pkgB_0@1.2")
                self.pkg("list A_incorp@1.2")
                self.pkg("list B_incorp@1.2")
                self.pkg("uninstall '*'")
                # what happens when incorporation specified
                # a package that isn't in the catalog
                self.pkg("install bug_7394_incorp")
                self.pkg("install pkg1", exit=1)
                self.pkg("uninstall '*'")
                # test pkg.depend.install-hold feature
                self.pkg("install -v A_incorp@1.1  pkgA_1")
                self.pkg("list pkgA_1@1.1")
                self.pkg("list A_incorp@1.1")
                # next attempt will fail because incorporations prevent motion
                # even though explicit dependency exists from pkg to
                # incorporation.
                self.pkg("install pkgA_1@1.2", exit=1)
                # test to see if we could install both; presence of incorp
                # causes relaxation of pkg.depend.install-hold and also test
                # that parsable output works when -n is used
                self.pkg("install -n --parsable=0 A_incorp@1.2 pkgA_1@1.2")
                self.assertEqualParsable(self.output, change_packages=[
                    [self.incorp_pkgs[2], self.incorp_pkgs[4]],
                    [self.leaf_pkgs[9], self.leaf_pkgs[17]]])
                # this attempt also succeeds because pkg.depend.install-hold is
                # relaxed since A_incorp is on command line
                self.pkg("install A_incorp@1.2")
                self.pkg("list pkgA_1@1.2")
                self.pkg("list A_incorp@1.2")
                # now demonstrate w/ version 1.2 subincorps that master incorp
                # prevents upgrade since pkg.depend.install-hold of master != other incorps
                self.pkg("install incorp@1.2")
                self.pkg("install A_incorp@1.3", exit=1)
                self.pkg("install incorp@1.3")
                self.pkg("list pkgA_1@1.3")
                self.pkg("list A_incorp@1.3")

        def test_incorporation_dependencies_exact_install(self):
                """ shake out incorporation dependencies """

                self.image_create(self.rurl)
                # Simple pkg requiring controlling incorp
                # should control pkgA_1 as well.
                self.pkg("exact-install -v pkgA_0@1.0 pkgA_1")
                self.pkg("list")
                self.pkg("verify pkgA_0@1.0 pkgA_1@1.0 A_incorp@1.0")

                # Verify exact-install will upgrade pkgA_0 and A_incorp to 1.1
                #, and uninstall pkgA_1.
                self.pkg("exact-install pkgA_0@1.1")
                self.pkg("list pkgA_0@1.1 A_incorp@1.1")
                self.pkg("uninstall '*'")

                # Try nested incorporations.
                self.pkg("exact-install -v incorp@1.0 pkgA_0 pkgB_0")
                self.pkg("list incorp@1.0 pkgA_0@1.0 pkgB_0@1.0 A_incorp@1.0 B_incorp@1.0")
                # Try to break incorporation.
                self.pkg("exact-install -v incorp@1.0 A_incorp@1.1", exit=1) # fixed by incorp@1.0

                # Only specify A_incorp@1.1 should succeed. install holds
                # should be ignored.
                self.pkg("exact-install -v A_incorp@1.1")
                self.pkg("list A_incorp@1.1")
                self.pkg("uninstall '*'")
                # what happens when incorporation specified
                # a package that isn't in the catalog.
                self.pkg("exact-install pkg1 bug_7394_incorp", exit=1)
                # test pkg.depend.install-hold feature.
                self.pkg("exact-install -v A_incorp@1.1  pkgA_1")
                self.pkg("list pkgA_1@1.1")
                self.pkg("list A_incorp@1.1")

        def test_conditional_dependencies_install(self):
                """Get conditional dependencies working"""
                self.image_create(self.rurl)
                self.pkg("install pkg7@1.0")
                self.pkg("verify")
                self.pkg("list pkg6@1.1", exit=1) # should not be here
                self.pkg("install -v pkg2@1.0")      # older version...
                self.pkg("verify")
                self.pkg("list pkg6@1.1", exit=1)
                self.pkg("install -v pkg2@1.1")      # this triggers conditional dependency
                self.pkg("verify")
                self.pkg("list pkg6@1.1 pkg2@1.1 pkg7@1.0") # everyone is present
                self.pkg("uninstall '*'")

                self.pkg("install pkg2@1.1")  # install trigger
                self.pkg("verify")
                self.pkg("install pkg7@1.0")  # install pkg
                self.pkg("list pkg6@1.1 pkg2@1.1 pkg7@1.0") # all here again
                self.pkg("verify")
                self.pkg("uninstall '*'")

                # Test bug 18653
                self.pkg("install osnet-incorporation@1.0 sun-solaris "
                    "perl-510 sun-solaris-510")
                # Uninstall should fail because sun-solaris conditional
                # dependency requires sun-solaris-510.
                self.pkg("uninstall sun-solaris-510", exit=1)
                # Uninstalling both the predicate and the target of the
                # conditional dependency should work.
                self.pkg("uninstall perl-510 sun-solaris-510")
                self.pkg("install perl-510")
                # Check that reject also works.
                self.pkg("update --reject perl-510 --reject sun-solaris-510")
                self.pkg("uninstall '*'")

                # Verify that if the predicate of a conditional can be
                # installed, but the consequent cannot, the package delivering
                # the conditional dependency can still be installed.
                self.pkg("install -v entire osnet-incorporation@1.1 "
                    "sun-solaris")

                # Verify that the package incorporating a package that delivers
                # a conditional for a consequent that cannot be installed can be
                # removed.
                self.pkg("uninstall -v entire")

        def test_conditional_dependencies_exact_install(self):
                """Get conditional dependencies working."""

                self.image_create(self.rurl)
                # Presenting pkg7@1.0 and pkg2@1.1 in the command line should
                # trigger conditional dependency.
                self.pkg("exact-install -v pkg7@1.0 pkg2@1.1")
                self.pkg("verify")
                self.pkg("list pkg6@1.1 pkg2@1.1 pkg7@1.0")
                self.pkg("uninstall '*'")

                # If  only pkg7@1.0 present in the command line, pkg2@1.1
                # should be removed and pkg6@1.1 should not be installed.
                self.pkg("install pkg2@1.1")
                self.pkg("verify")
                self.pkg("exact-install pkg7@1.0")
                self.pkg("list pkg7@1.0")
                self.pkg("list pkg2@1.1", exit=1)
                self.pkg("list pkg6@1.1", exit=1)
                self.pkg("verify")
                self.pkg("uninstall '*'")

        def test_require_any_dependencies_install(self):
                """Get require-any dependencies working"""
                self.image_create(self.rurl)

                # test to see if solver will fail gracefully when no solution is
                # possible and a require-any dependency is involved
                self.pkg("install -vvv pkg-nosol-A pkg-nosol-E",
                    assert_solution=False, exit=1)

                # test to see if solver will pick one
                self.pkg("install pkg8@1.0")  # install pkg
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg9@1.0 pkg2@1.1", exit=3)
                self.pkg("uninstall '*'")

                # test to see if solver will be happy w/ renamed packages,
                # already installed dependencies.
                self.pkg("install pkg:/pkg2@1.1")
                self.pkg("install pkg_need_rename")
                self.pkg("install pkg8@1.0")
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg2@1.1")
                self.pkg("uninstall '*'")

                # test to see if solver will install new verion of existing
                # package rather than add new package
                self.pkg("install pkg8@1.0 pkg9@1.0")  # install pkg
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg9@1.0")
                self.pkg("list pkg2@1.1", exit=1)
                self.pkg("install pkg8 pkg9") # will fail w/o pkg9 on list
                self.pkg("verify")
                self.pkg("list pkg8@1.1 pkg9@1.1")
                self.pkg("uninstall '*'")

                # see if update works the same way
                self.pkg("install pkg8@1.0 pkg9@1.0")  # install pkg
                self.pkg("update")
                self.pkg("list pkg8@1.1 pkg9@1.1")
                self.pkg("uninstall '*'")

                # test to see if uninstall is clever enough
                self.pkg("install pkg8@1.0 pkg9@1.0")  # install pkg
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg9@1.0")
                self.pkg("uninstall pkg9@1.0")
                self.pkg("list pkg2@1.1")
                self.pkg("verify")

        def test_require_any_dependencies_exact_install(self):
                """Get require-any dependencies working"""
                self.image_create(self.rurl)

                # Test to see if solver will fail gracefully when no solution is
                # possible and a require-any dependency is involved.
                self.pkg("exact-install -v pkg-nosol-A pkg-nosol-E",
                    assert_solution=False, exit=1)

                # Test to see if solver will pick one.
                self.pkg("exact-install pkg8@1.0")
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg9@1.0 pkg2@1.1", exit=3)
                self.pkg("uninstall '*'")

                # Test to see if solver will be happy w/ renamed packages,
                # already installed dependencies.
                self.pkg("exact-install pkg:/pkg2@1.1 pkg_need_rename "
                    "pkg8@1.0")
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg2@1.1")
                self.pkg("uninstall '*'")

                # test to see if solver will install new verion of existing
                # package rather than add new package
                self.pkg("exact-install pkg8@1.0 pkg9@1.0")  # install pkg
                self.pkg("verify")
                self.pkg("list pkg8@1.0 pkg9@1.0")
                self.pkg("list pkg2@1.1", exit=1)
                self.pkg("exact-install pkg8 pkg9")
                self.pkg("verify")
                self.pkg("list pkg8@1.1 pkg9@1.1")
                self.pkg("list pkg2@1.1", exit=1)
                self.pkg("uninstall '*'")

        def test_origin_dependencies(self):
                """Get origin dependencies working"""

                self.origin_dependencies_helper("install")
                self.origin_dependencies_helper("exact-install")

        def origin_dependencies_helper(self, install_cmd):
                self.set_image(0)
                self.image_create(self.rurl)
                self.set_image(1)
                self.image_create(self.rurl)
                self.set_image(0)
                # check install or exact-install behavior
                self.pkg("{0} pkg10@1.0".format(install_cmd))
                self.pkg("{0} pkg10".format(install_cmd))
                self.pkg("list pkg10@1.1")
                self.pkg("{0} pkg10".format(install_cmd))
                self.pkg("list pkg10@1.2")
                self.pkg("uninstall '*'")
                # check update behavior
                self.pkg("install pkg10@1.0")
                self.pkg("update")
                self.pkg("list pkg10@1.1")
                self.pkg("update")
                self.pkg("list pkg10@1.2")
                self.pkg("uninstall '*'")
                # check that dependencies are ignored if
                # dependency not present
                self.pkg("{0} pkg10@1.2".format(install_cmd))
                self.pkg("uninstall '*'")
                # make sure attempts to force install don't work
                self.pkg("{0} pkg10@1.0".format(install_cmd))
                self.pkg("{0} pkg10@1.2".format(install_cmd), exit=1)
                self.pkg("{0} pkg10@1.1".format(install_cmd))
                self.pkg("{0} pkg10@1.2".format(install_cmd))
                self.pkg("uninstall '*'")
                # check origin root-image=true dependencies
                # relies on SUNWcs in root image; make image 1 the root image
                self.set_image(1)
                self.pkg("{0} SUNWcs@0.5.11-0.75".format(install_cmd))
                self.set_image(0)
                live_root = self.img_path(1)
                self.pkg("-D simulate_live_root={0} {1} pkg11@1.0".format(
                    live_root, install_cmd))
                self.pkg("-D simulate_live_root={0} {1} pkg11@1.1".format(
                    live_root, install_cmd), exit=1)
                self.pkg("uninstall '*'")

        def test_parent_dependencies(self):
                self.parent_dependencies_helper("install")
                self.parent_dependencies_helper("exact-install")

        def parent_dependencies_helper(self, install_cmd):
                self.set_image(0)
                self.image_create(self.rurl)
                self.set_image(1)
                self.image_create(self.rurl)

                # attach c2p 1 -> 0.
                self.pkg("attach-linked -p system:img1 {0}".format(self.img_path(0)))

                # try to install or exact-instal packages that have unmet
                # parent dependencies.
                self.pkg("{0} pkg12@1.2".format(install_cmd), exit=EXIT_OOPS)
                self.pkg("{0} pkg13@1.2".format(install_cmd), exit=EXIT_OOPS)
                self.pkg("{0} pkg14@1.2".format(install_cmd), exit=EXIT_OOPS)

                # install or exact-install packages in parent.
                self.set_image(0)
                self.pkg("install pkg12@1.1")
                self.set_image(1)

                # try to install or exact-install packages that have unmet
                # parent dependencies.
                self.pkg("{0} pkg12@1.2".format(install_cmd), exit=EXIT_OOPS)
                self.pkg("{0} pkg13@1.2".format(install_cmd), exit=EXIT_OOPS)
                self.pkg("{0} pkg14@1.2".format(install_cmd), exit=EXIT_OOPS)

                # install or exact-install packages in parent.
                self.set_image(0)
                self.pkg("{0} pkg12@1.3".format(install_cmd))
                self.set_image(1)

                # try to install or exact-install packages that have unmet
                # parent dependencies.
                self.pkg("{0} pkg12@1.2".format(install_cmd), exit=EXIT_OOPS)
                self.pkg("{0} pkg13@1.2".format(install_cmd), exit=EXIT_OOPS)
                self.pkg("{0} pkg14@1.2".format(install_cmd), exit=EXIT_OOPS)

                # install packages in parent
                self.set_image(0)
                self.pkg("update pkg12@1.2")
                self.set_image(1)

                # try to install or exact-install packages that have unmet parent dependencies.
                self.pkg("{0} pkg14@1.2".format(install_cmd), exit=EXIT_OOPS)

                # try to install or exact-install packages that have satisfied parent deps.
                self.pkg("{0} pkg12@1.2".format(install_cmd))
                self.pkg("verify")
                self.pkg("uninstall pkg12@1.2")
                self.pkg("{0} pkg13@1.2".format(install_cmd))
                self.pkg("verify")
                self.pkg("uninstall pkg13@1.2")

                # install or exact-install packages in parent.
                self.set_image(0)
                if install_cmd == "install":
                        self.pkg("install pkg13@1.2")
                else:
                        self.pkg("exact-install pkg12@1.2 pkg13@1.2")
                self.set_image(1)

                # try to install or exact-install packages that have satisfied.
                # parent deps.
                self.pkg("{0} pkg14@1.2".format(install_cmd))
                self.pkg("verify")
                self.pkg("uninstall pkg14@1.2")

        def test_optional_nosolution(self):
                """Ensure useful error messages are produced when an optional
                dependency in a proposed package cannot be satisfied due to
                another proposed package."""

                self.image_create(self.rurl)
                self.pkg("install desktop-incorporation")
                self.pkg("install -n multi-user-desktop@latest libotr@latest "
                    "desktop-incorporation@latest", exit=1)
                self.assertFalse("No solution" in self.errout)
                # desktop-incorporation should not be listed as a rejected
                # package; rejected packages are always listed with full FMRI
                # and scheme
                self.assertFalse("pkg://test/consolidation/desktop/desktop-incorporation" in self.errout)
                # all of these should show up as rejected packages
                self.assertTrue("pkg://test/communication/im/libotr" in self.errout)
                self.assertTrue("pkg://test/group/feature/multi-user-desktop" in self.errout)
                # reason for rejection should reference optional dependency type
                self.assertTrue("optional" in self.errout)


class TestMultipleDepots(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo10 = """
            open foo@1.0,5.11-0
            close"""

        bar10 = """
            open bar@1.0,5.11-0
            close"""

        moo10 = """
            open moo@1.0,5.11-0
            close"""

        quux10 = """
            open quux@1.0,5.11-0
            add depend type=optional fmri=optional@1.0
            close"""

        baz10 = """
            open baz@1.0,5.11-0
            add depend type=require fmri=corge@1.0
            close"""

        corge10 = """
            open corge@1.0,5.11-0
            close"""

        optional10 = """
            open optional@1.0,5.11-0
            close"""

        upgrade_p10 = """
            open upgrade-p@1.0,5.11-0
            close"""

        upgrade_p11 = """
            open upgrade-p@1.1,5.11-0
            close"""

        upgrade_np10 = """
            open upgrade-np@1.0,5.11-0
            close"""

        upgrade_np11 = """
            open upgrade-np@1.1,5.11-0
            close"""

        incorp_p10 = """
            open incorp-p@1.0,5.11-0
            add depend type=incorporate fmri=upgrade-p@1.0
            close"""

        incorp_p11 = """
            open incorp-p@1.1,5.11-0
            add depend type=incorporate fmri=upgrade-p@1.1
            close"""

        incorp_np10 = """
            open incorp-np@1.0,5.11-0
            add depend type=incorporate fmri=upgrade-np@1.0
            close"""

        incorp_np11 = """
            open incorp-np@1.1,5.11-0
            add depend type=incorporate fmri=upgrade-np@1.1
            close"""

        def setUp(self):
                """ depot 1 gets foo and moo, depot 2 gets foo and bar,
                    depot 3 is empty, depot 4 gets upgrade_np@1.1
                    depot 5 gets corge10, depot6 is empty
                    depot7 is a copy of test1's repository for test3
                    depot1 is mapped to publisher test1 (preferred)
                    depot2 is mapped to publisher test2
                    depot3 is not mapped during setUp
                    depot4 is not mapped during setUp
                    depot5 is not mapped during setUp
                    depot6 is not mapped during setUp"""

                # Two depots are intentionally started for some publishers.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test3", "test2", "test4", "test1", "test3"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(self.rurl1, (self.foo10, self.moo10,
                    self.quux10, self.optional10, self.upgrade_p10,
                    self.upgrade_np11, self.incorp_p10, self.incorp_p11,
                    self.incorp_np10, self.incorp_np11, self.baz10,
                    self.corge10))

                self.rurl2 = self.dcs[2].get_repo_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(self.rurl2, (self.foo10, self.bar10,
                    self.upgrade_p11, self.upgrade_np10, self.corge10))

                self.rurl3 = self.dcs[3].get_repo_url()

                self.rurl4 = self.dcs[4].get_repo_url()
                self.pkgsend_bulk(self.rurl4, self.upgrade_np11)

                self.rurl5 = self.dcs[5].get_repo_url()
                self.pkgsend_bulk(self.rurl5, self.corge10)

                self.rurl6 = self.dcs[6].get_repo_url()
                self.rurl7 = self.dcs[7].get_repo_url()

                # Copy contents of test1's repo to a repo for test3.
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[7].get_repodir()
                self.copy_repository(d1dir, d2dir, { "test1": "test3" })
                self.dcs[7].get_repo(auto_create=True).rebuild()

                # Create image and hence primary publisher
                self.image_create(self.rurl1, prefix="test1")

                # Create second publisher using depot #2
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

        def test_01_basics(self):
                self.pkg("list -a")

                # Install and uninstall moo (which is unique to depot 1)
                self.pkg("install moo")

                self.pkg("list")
                self.pkg("uninstall moo")

                # Install and uninstall bar (which is unique to depot 2)
                self.pkg("install bar")

                self.pkg("list")

                self.pkg("uninstall bar")

                # Install and uninstall foo (which is in both depots)
                # In this case, we should select foo from depot 1, since
                # it is preferred.
                self.pkg("install foo")

                self.pkg("list pkg://test1/foo")

                self.pkg("uninstall foo")

        def test_02_basics(self):
                """ Test install from an explicit preferred publisher """
                self.pkg("install pkg://test1/foo")
                self.pkg("list foo")
                self.pkg("list pkg://test1/foo")
                self.pkg("uninstall foo")

        def test_03_basics(self):
                """ Test install from an explicit non-preferred publisher """
                self.pkg("install pkg://test2/foo")
                self.pkg("list foo")
                self.pkg("list pkg://test2/foo")
                self.pkg("uninstall foo")

        def test_04_upgrade_preferred_to_non_preferred(self):
                """Install a package from the preferred publisher, and then
                upgrade it, failing to implicitly switching to a non-preferred
                publisher and then managing it explicitly"""
                self.pkg("list -a upgrade-p")
                self.pkg("install upgrade-p@1.0")
                self.pkg("install upgrade-p@1.1", exit=1)
                self.pkg("install pkg://test2/upgrade-p@1.1")
                self.pkg("uninstall upgrade-p")

        def test_05_upgrade_non_preferred_to_preferred(self):
                """Install a package from a non-preferred publisher, and then
                try to upgrade it, failing to implicitly switch to the preferred
                publisher and then succeed doing it explicitly."""
                self.pkg("list -a upgrade-np")
                self.pkg("install upgrade-np@1.0")
                self.pkg("install upgrade-np@1.1", exit=1)
                self.pkg("install pkg://test1/upgrade-np@1.1")
                self.pkg("uninstall upgrade-np")

        def test_06_upgrade_preferred_to_non_preferred_incorporated(self):
                """Install a package from the preferred publisher, and then
                upgrade it, failing to implicitly switch to a non-preferred
                publisher, when the package is constrained by an
                incorporation, and then succeed when doing so explicitly"""

                self.pkg("list -a upgrade-p incorp-p")
                self.pkg("install incorp-p@1.0")
                self.pkg("install upgrade-p")
                self.pkg("install incorp-p@1.1", exit=1)
                self.pkg("install incorp-p@1.1 pkg://test2/upgrade-p@1.1")
                self.pkg("list upgrade-p@1.1")
                self.pkg("uninstall '*'")

        def test_07_upgrade_non_preferred_to_preferred_incorporated(self):
                """Install a package from the preferred publisher, and then
                upgrade it, implicitly switching to a non-preferred
                publisher, when the package is constrained by an
                incorporation."""
                self.pkg("list", exit=1)
                self.pkg("list -a upgrade-np incorp-np")
                self.pkg("install incorp-np@1.0")
                self.pkg("install upgrade-np", exit=1)
                self.pkg("uninstall '*'")

        def test_08_install_repository_access(self):
                """Verify that packages can still be installed from a repository
                even when any of the other repositories are not reachable and
                --no-refresh is used."""

                # Change the second publisher to point to an unreachable URI.
                self.pkg("set-publisher --no-refresh -O http://test.invalid7 "
                    "test2")

                # Verify that no packages are installed.
                self.pkg("list", exit=1)

                # Verify moo can be installed (as only depot1 has it) even
                # though test2 cannot be reached (and needs a refresh).
                self.pkg("install moo")
                self.pkg("uninstall moo")

                # Verify moo can be installed (as only depot1 has it) even
                # though test2 cannot be reached (and needs a refresh) if
                # --no-refresh is used.
                self.pkg("install --no-refresh moo")

                self.pkg("uninstall moo")

                # Reset the test2 publisher.
                self.pkg("set-publisher -O {0} test2".format(self.rurl2))

                # Install v1.0 of upgrade-np from test2 to prepare for
                # update.
                self.pkg("install upgrade-np@1.0")

                # Set test1 to point to an unreachable URI.
                self.pkg("set-publisher --no-refresh -O http://test.invalid7 "
                    "test1")

                # Set test2 so that upgrade-np has a new version available
                # even though test1's repository is not accessible.
                self.pkg("set-publisher -O {0} test2".format(self.rurl4))

                # Verify update works even though test1 is unreachable
                # since upgrade-np@1.1 is available from test2 if --no-refresh
                # is used.
                self.pkg("update --no-refresh")

                # Now reset everything for the next test.
                self.pkg("uninstall upgrade-np")
                self.pkg("set-publisher --no-refresh -O {0} test1".format(self.rurl1))
                self.pkg("set-publisher -O {0} test2".format(self.rurl2))

        def test_09_uninstall_from_wrong_publisher(self):
                """Install a package from a publisher and try to remove it
                using a different publisher name; this should fail."""
                self.pkg("install foo")
                self.pkg("uninstall pkg://test2/foo", exit=1)
                # Check to make sure that uninstalling using the explicit
                # publisher works
                self.pkg("uninstall pkg://test1/foo")

        def test_10_install_after_publisher_removal(self):
                """Install a package from a publisher that has an optional
                dependency; then change the preferred publisher and remove the
                original publisher and then verify that installing the package
                again succeeds since it is essentially a no-op."""
                self.pkg("install quux@1.0")
                self.pkg("set-publisher -P test2")
                self.pkg("unset-publisher test1")
                self.pkg("list -avf")

                # Attempting to install an already installed package should
                # be a no-op even if the corresponding publisher no longer
                # exists.
                self.pkg("install quux@1.0", exit=4)

                # Update should work if we don't see the optional
                # dependency.
                self.pkg("update", exit=4)

                # Add back the installed package's publisher, but using a
                # a repository with an empty catalog.  After that, attempt to
                # install the package again, which should succeed even though
                # the fmri is no longer in the publisher's catalog.
                self.pkg("set-publisher -O {0} test1".format(self.rurl6))
                self.pkg("install quux@1.0", exit=4)
                self.pkg("info quux@1.0")
                self.pkg("unset-publisher test1")

                # Add a new publisher, with the same packages as the installed
                # publisher.  Then, add back the installed package's publisher,
                # but using an empty repository.  After that, attempt to install
                # the package again, which should succeed since at least one
                # publisher has the package in its catalog.
                self.pkg("set-publisher -O {0} test3".format(self.rurl7))
                self.pkg("set-publisher -O {0} test1".format(self.rurl6))
                self.pkg("info -r pkg://test3/quux@1.0")
                self.pkg("install quux@1.0", exit=4)
                self.pkg("unset-publisher test1")
                self.pkg("unset-publisher test3")

                self.pkg("set-publisher -O {0} test1".format(self.rurl1))
                self.pkg("info -r pkg://test1/quux@1.0")
                self.pkg("unset-publisher test1")

                # Add a new publisher, using the installed package publisher's
                # repository.  After that, attempt to install the package again,
                # which should simply result in a 'no updates necessary' exit
                # code since the removed publisher's package is already the
                # newest version available.
                #
                self.pkg("set-publisher -O {0} test3".format(self.rurl7))
                self.pkg("install quux@1.0", exit=4)
                self.pkg("unset-publisher test3")

                # Change the image metadata back to where it was, in preparation
                # for subsequent tests.
                self.pkg("set-publisher -O {0} -P test1".format(self.rurl1))

                # Remove the installed packages.
                self.pkg("uninstall quux")

        def test_11_uninstall_after_preferred_publisher_change(self):
                """Install a package from the preferred publisher, change the
                preferred publisher, and attempt to remove the package."""
                self.pkg("install foo@1.0")
                self.pkg("set-publisher -P test2")
                self.pkg("uninstall foo")
                # Change the image metadata back to where it was, in preparation
                # for the next test.
                self.pkg("set-publisher -P test1")

        def test_12_uninstall_after_publisher_removal(self):
                """Install a package from the preferred publisher, remove the
                preferred publisher, and then evaluate whether an uninstall
                would succeed regardless of whether its publisher still exists
                or another publisher has the same fmri in its catalog."""
                self.pkg("install foo@1.0")
                self.pkg("set-publisher -P test2")
                self.pkg("unset-publisher test1")

                # Attempting to uninstall should work even if the corresponding
                # publisher no longer exists.
                self.pkg("uninstall -nv foo")

                # Add back the installed package's publisher, but using a
                # a repository with an empty catalog.  After that, attempt to
                # uninstall the package again, which should succeed even though
                # the fmri is no longer in the publisher's catalog.
                self.pkg("set-publisher -O {0} test1".format(self.rurl6))
                self.pkg("uninstall -nv foo")
                self.pkg("unset-publisher test1")

                # Add a new publisher, with a repository with the same packages
                # as the installed publisher.  Then, add back the installed
                # package's publisher using an empty repository.  After that,
                # attempt to uninstall the package again, which should succeed
                # even though the package's installed publisher is known, but
                # doesn't have the package's fmri in its catalog, but the
                # package's fmri is in a different publisher's catalog.
                self.pkg("set-publisher -O {0} test3".format(self.rurl7))
                self.pkg("set-publisher -O {0} test1".format(self.rurl6))
                self.pkg("uninstall -nv foo")
                self.pkg("unset-publisher test1")
                self.pkg("unset-publisher test3")

                # Add a new publisher, with a repository with the same packages
                # as the installed publisher.  After that, attempt to uninstall
                # the package again, which should succeed even though the fmri
                # is only in a different publisher's catalog.
                self.pkg("set-publisher -O {0} test3".format(self.rurl7))
                self.pkg("uninstall -nv foo")
                self.pkg("unset-publisher test3")

                # Finally, actually remove the package.
                self.pkg("uninstall -v foo")

                # Change the image metadata back to where it was, in preparation
                # for subsequent tests.
                self.pkg("set-publisher -O {0} -P test1".format(self.rurl1))

        def test_13_non_preferred_multimatch(self):
                """Verify that when multiple non-preferred publishers offer the
                same package that the expected install behaviour occurs."""

                self.pkg("set-publisher -P -O {0} test3".format(self.rurl3))

                # make sure we look here first; tests rely on that
                self.pkg("set-publisher --search-before=test2 test1")
                self.pkg("publisher")
                # First, verify that installing a package from a non-preferred
                # publisher will cause its dependencies to be installed from the
                # same publisher if the preferred publisher does not offer them.
                self.pkg("list -a")
                self.pkg("install pkg://test1/baz")
                self.pkg("list")
                self.pkg("info baz | grep test1")
                self.pkg("info corge | grep test1")
                self.pkg("uninstall baz corge")

                # Next, verify that naming the specific publishers for a package
                # and all of its dependencies will install the package from the
                # specified sources instead of the same publisher the package is a
                # dependency of.
                self.pkg("install pkg://test1/baz pkg://test2/corge")
                self.pkg("info baz | grep test1")
                self.pkg("info corge | grep test2")
                self.pkg("uninstall baz corge")

                # Finally, cleanup for the next test.
                self.pkg("set-publisher -P test1")
                self.pkg("unset-publisher test3")

        def test_14_nonsticky_publisher(self):
                """Test various aspects of the stick/non-sticky
                behavior of publishers"""

                # For ease of debugging
                self.pkg("list -a")
                # install from non-preferred repo explicitly
                self.pkg("install pkg://test2/upgrade-np@1.0")
                # Demonstrate that preferred publisher is not
                # acceptable, since test2 is sticky by default
                self.pkg("install upgrade-np@1.1", exit=1) # not right repo
                # Check that we can proceed once test2 is not sticky
                self.pkg("set-publisher --non-sticky test2")
                self.pkg("install upgrade-np@1.1") # should work now
                # Restore to pristine
                self.pkg("set-publisher --sticky test2")
                self.pkg("uninstall upgrade-np")
                # Repeat the test w/ preferred
                self.pkg("install upgrade-p")
                self.pkg("set-publisher -P test2")
                self.pkg("install upgrade-p@1.1", exit=1) #orig pub is sticky
                self.pkg("set-publisher --non-sticky test1")  #not anymore
                self.pkg("install upgrade-p@1.1")
                self.pkg("set-publisher -P --sticky test1") # restore
                self.pkg("uninstall '*'")
                # Check  that search order can be overridden w/ explicit
                # version specification...
                self.pkg("install upgrade-p")
                self.pkg("install upgrade-p@1.1", exit=1)
                self.pkg("set-publisher --non-sticky test1")
                self.pkg("install upgrade-p@1.1") # find match later on
                self.pkg("set-publisher --sticky test1")
                self.pkg("uninstall '*'")

        def test_15_nonsticky_update(self):
                """Test to make sure update follows the same
                publisher selection mechanisms as pkg install"""

                # try update
                self.pkg("install pkg://test2/upgrade-np@1.0")
                self.pkg("update", exit=4)
                self.pkg("list upgrade-np@1.0")
                self.pkg("set-publisher --non-sticky test2")
                self.pkg("publisher")
                self.pkg("list -a upgrade-np")
                self.pkg("update '*@*'")
                self.pkg("list upgrade-np@1.1")
                self.pkg("set-publisher --sticky test2")
                self.pkg("uninstall '*'")

        def test_16_disabled_nonsticky(self):
                """Test to make sure disabled publishers are
                automatically made non-sticky, and after
                being enabled keep their previous value
                of stickiness"""

                # For ease of debugging
                self.pkg("list -a")
                # install from non-preferred repo explicitly
                self.pkg("install pkg://test2/upgrade-np@1.0")
                # Demonstrate that preferred publisher is not
                # acceptable, since test2 is sticky by default
                self.pkg("install upgrade-np@1.1", exit=1) # not right repo
                # Disable test2 and then we should be able to proceed
                self.pkg("set-publisher --disable test2")
                self.pkg("install upgrade-np@1.1")
                self.pkg("publisher")
                self.pkg("set-publisher --enable test2")
                self.pkg("publisher")
                self.pkg("publisher | egrep sticky", exit=1 )

        def test_17_dependency_is_from_deleted_publisher(self):
                """Verify that packages installed from a publisher that has
                been removed can still satisfy dependencies."""

                self.pkg("set-publisher -O {0} test4".format(self.rurl5))
                self.pkg("install pkg://test4/corge")
                self.pkg("set-publisher --disable test2")
                self.pkg("set-publisher --disable test4")
                self.pkg("list -af")
                self.pkg("publisher")
                # this should work, since dependency is already installed
                # even though it is from a disabled publisher
                self.pkg("install baz@1.0")

        def test_18_upgrade_across_publishers(self):
                """Verify that an install/update of specific packages when
                there is a newer package version available works as expected.
                """

                # Ensure a new image is created.
                self.image_create(self.rurl1, prefix="test1", destroy=True)

                # Add second publisher using repository #2.
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

                # Install older version of package from test1.
                self.pkg("install pkg://test1/upgrade-p@1.0")

                # Verify setting test2 as higher-ranked would not result in
                # update since test1 is sticky.
                self.pkg("set-publisher -P test2")
                self.pkg("update -v", exit=4)

                # Verify setting test1 as higher-ranked and non-sticky would not
                # result in update since test2 is lower-ranked and not
                # non-sticky.
                self.pkg("set-publisher -P --non-sticky test1")
                self.pkg("update -v", exit=4)

                # Verify setting test2 as non-sticky would result in update even
                # though it is lower-ranked since it is non-sticky..
                self.pkg("set-publisher --non-sticky test2")
                self.pkg("publisher")
                self.pkg("list -af upgrade-p")
                self.pkg("update -nvvv")

                # Verify placing a publisher between test1 and test2 causes the
                # update to fail since even though test1 and test2 are
                # non-sticky, they are not adjacent.
                self.pkg("set-publisher --search-after=test1 foo")
                self.pkg("update -v", exit=4)
                self.pkg("unset-publisher foo")

                # Verify setting test2 as higher-ranked and sticky would result
                # in update since test1 is non-sticky and test2 is higher-ranked.
                self.pkg("set-publisher -P test2")
                self.pkg("update -n")

                # Verify update of 'upgrade-p' package will result in upgrade
                # from 1.0 -> 1.1.
                self.pkg("update upgrade-p")
                self.pkg("info pkg://test2/upgrade-p@1.1")

                # Revert to 1.0 and verify install behaves the same.
                self.pkg("update pkg://test1/upgrade-p@1.0")
                self.pkg("install upgrade-p")
                self.pkg("info pkg://test2/upgrade-p@1.1")

        def test_19_refresh_failure(self):
                """Test that pkg client returns with exit code 1 when only one
                publisher is specified and it's not reachable (bug 7176158)."""

                # Create private image for this test.
                self.image_create(self.rurl1, prefix="test1")
                # Set origin to an invalid repo.
                self.pkg("set-publisher --no-refresh -O http://test.invalid7 "
                    "test1")

                # Check if install -n returns with exit code 1
                self.pkg("install -n moo", exit=1)


class TestImageCreateCorruptImage(pkg5unittest.SingleDepotTestCaseCorruptImage):
        """
        If a new essential directory is added to the format of an image it will
        be necessary to update this test suite. To update this test suite,
        decide in what ways it is necessary to corrupt the image (removing the
        new directory or file, or removing the some or all of contents of the
        new directory for example). Make the necessary changes in
        pkg5unittest.SingleDepotTestCaseCorruptImage to allow the needed
        corruptions, then add new tests to the suite below. Be sure to add
        tests for both Full and User images, and perhaps Partial images if
        situations are found where these behave differently than Full or User
        images.
        """

        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        foo11 = """
            open foo@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/lib
            add file tmp/libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            close """

        misc_files = [ "tmp/libc.so.1" ]

        PREFIX = "unset PKG_IMAGE; cd {0};"

        def setUp(self):
                pkg5unittest.SingleDepotTestCaseCorruptImage.setUp(self)
                self.make_misc_files(self.misc_files)

        def pkg(self, command, exit=0, comment="", use_img_root=True):
                pkg5unittest.SingleDepotTestCaseCorruptImage.pkg(self, command,
                    exit=exit, comment=comment, prefix=self.PREFIX.format(self.dir),
                    use_img_root=use_img_root)

        # For each test:
        # A good image is created at $basedir/image
        # A corrupted image is created at $basedir/image/bad (called bad_dir
        #     in subsequent notes) in verious ways
        # The $basedir/image/bad/final directory is created and PKG_IMAGE
        #     is set to that dirctory.

        # Tests simulating a corrupted Full Image

        def test_empty_var_pkg(self):
                """ Creates an empty bad_dir. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher", "cfg_cache", "file", "pkg", "index"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_publisher(self):
                """ Creates bad_dir with only the publisher and known/state
                dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_absent", "known_absent"]),
                    ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_cfg_cache(self):
                """ Creates bad_dir with only the cfg_cache file missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), ["var/pkg"])

                self.pkg("-D simulate_live_root={0} install foo@1.1".format(
                    self.backup_img_path()), use_img_root=False)

        def test_var_pkg_missing_index(self):
                """ Creates bad_dir with only the index dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(
                    ["index_absent"]), ["var/pkg"])

                self.pkg("install foo@1.1")

        def test_var_pkg_missing_publisher_empty(self):
                """ Creates bad_dir with all dirs and files present, but
                with an empty publisher and state/known dir.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]), ["var/pkg"])

                # This is expected to fail because it will see an empty
                # publisher directory and not rebuild the files as needed
                self.pkg("install --no-refresh foo@1.1", exit=1)
                self.pkg("install foo@1.1")

        def test_var_pkg_missing_publisher_empty_hit_then_refreshed_then_hit(
            self):
                """ Creates bad_dir with all dirs and files present, but with an
                with an empty publisher and state/known dir. This is to ensure
                that refresh will work, and that an install after the refresh
                also works.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]), ["var/pkg"])

                self.pkg("install --no-refresh foo@1.1", exit=1)
                self.pkg("refresh")
                self.pkg("install foo@1.1")


        def test_var_pkg_left_alone(self):
                """ Sanity check to ensure that the code for creating
                a bad_dir creates a good copy other than what's specified
                to be wrong. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(), ["var/pkg"])

                self.pkg("install foo@1.1")

        # Tests simulating a corrupted User Image

        # These tests are duplicates of those above but instead of creating
        # a corrupt full image, they create a corrupt User image.

        def test_empty_ospkg(self):
                """ Creates a corrupted image at bad_dir by creating empty
                bad_dir.  """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher", "cfg_cache", "file", "pkg", "index"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_publisher(self):
                """ Creates a corrupted image at bad_dir by creating bad_dir
                with only the publisher and known/state dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_absent", "known_absent"]),
                        [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_cfg_cache(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the cfg_cache file missing.  """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["cfg_cache_absent"]), [".org.opensolaris,pkg"])

                self.pkg("-D simulate_live_root={0} install foo@1.1".format(
                    self.backup_img_path()), use_img_root=False)

        def test_ospkg_missing_index(self):
                """ Creates a corrupted image at bad_dir by creating
                bad_dir with only the index dir missing. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(["index_absent"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")

        def test_ospkg_missing_publisher_empty(self):
                """ Creates a corrupted image at bad_dir by creating bad_dir
                with all dirs and files present, but with an empty publisher
                and known/state dir. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install --no-refresh foo@1.1", exit=1)

        def test_ospkg_missing_publisher_empty_hit_then_refreshed_then_hit(self):
                """ Creates bad_dir with all dirs and files present, but with
                an empty publisher and known/state dir. This is to ensure that
                refresh will work, and that an install after the refresh also
                works.
                """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl,
                    set(["publisher_empty", "known_empty"]),
                    [".org.opensolaris,pkg"])

                self.pkg("install --no-refresh foo@1.1", exit=1)
                self.pkg("refresh")
                self.pkg("install foo@1.1")

        def test_ospkg_left_alone(self):
                """ Sanity check to ensure that the code for creating
                a bad_dir creates a good copy other than what's specified
                to be wrong. """

                self.pkgsend_bulk(self.rurl, self.foo11)
                self.image_create(self.rurl)

                self.dir = self.corrupt_image_create(self.rurl, set(),
                    [".org.opensolaris,pkg"])

                self.pkg("install foo@1.1")


class TestPkgInstallObsolete(pkg5unittest.SingleDepotTestCase):
        """Test cases for obsolete packages."""

        persistent_setup = True
        def test_basic_install(self):
                foo1 = """
                    open foo@1
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """
                # Obsolete packages can have metadata
                foo2 = """
                    open foo@2
                    add set name=pkg.obsolete value=true
                    add set name=pkg.summary value="A test package"
                    close
                """

                fbar = """
                    open fbar@1
                    add depend type=require fmri=foo@2
                    close
                """

                qbar = """
                    open qbar@1
                    add depend type=require fmri=qux@2
                    close
                """

                qux1 = """
                    open qux@1
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """

                qux2 = """
                    open qux@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=foo@1
                    close
                """

                fred1 = """
                    open fred@1
                    add depend type=require fmri=foo
                    close
                """
                fred2 = """
                    open fred@2
                    close
                """

                self.pkgsend_bulk(self.rurl, (foo1, foo2, fbar, qbar, qux1,
                    qux2, fred1))

                self.image_create(self.rurl)

                # First install the non-obsolete version of foo
                self.pkg("install foo@1")
                self.pkg("list foo@1")

                # Now install the obsolete version, and ensure it disappears (5)
                self.pkg("install foo")
                self.pkg("list foo", exit=1)

                # Explicitly installing an obsolete package succeeds, but
                # results in nothing on the system. (1)
                self.pkg("install foo@2", exit=4)
                self.pkg("list foo", exit=1)

                # Installing a package with a dependency on an obsolete package
                # fails. (2)
                self.pkg("install fbar", exit=1)

                # Installing a package with a dependency on a renamed package
                # succeeds, leaving the first package and the renamed package on
                # the system, as well as the empty, pre-renamed package. (3)
                self.pkg("install qbar")
                self.pkg("list qbar")
                self.pkg("list foo@1")
                self.pkg("list qux | grep -- i-r")
                self.pkg("uninstall '*'") #clean up for next test
                # A simple rename test: First install the pre-renamed version of
                # qux.  Then install the renamed version, and see that the new
                # package is installed, and the renamed package is installed,
                # but marked renamed.  (4)
                self.pkg("install qux@1")
                self.pkg("install qux") # upgrades qux
                self.pkg("list foo@1")
                self.pkg("list qux", exit=1)
                self.pkg("uninstall '*'") #clean up for next test

                # Install a package that's going to be obsoleted and a package
                # that depends on it.  Update the package to its obsolete
                # version and see that it fails.  (6, sorta)
                self.pkg("install foo@1 fred@1")
                self.pkg("install foo@2", exit=1)
                # now add a version of fred that doesn't require foo, and
                # show that update works
                self.pkgsend_bulk(self.rurl, fred2)
                self.pkg("refresh")
                self.pkg("install foo@2")
                self.pkg("uninstall '*'") #clean up for next test
                # test fix for bug 12898
                self.pkg("install qux@1")
                self.pkg("install fred@2")
                self.pkg("list foo@1", exit=1) # should not be installed
                self.pkg("install qux") #update
                self.pkg("list foo@1")
                self.pkgrepo("remove -s {0} fred@2".format(self.rurl))

        def test_basic_exact_install(self):
                foo1 = """
                    open foo@1
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """
                # Obsolete packages can have metadata
                foo2 = """
                    open foo@2
                    add set name=pkg.obsolete value=true
                    add set name=pkg.summary value="A test package"
                    close
                """

                fbar = """
                    open fbar@1
                    add depend type=require fmri=foo@2
                    close
                """

                qbar = """
                    open qbar@1
                    add depend type=require fmri=qux@2
                    close
                """

                qux1 = """
                    open qux@1
                    add dir path=usr mode=0755 owner=root group=root
                    close
                """

                qux2 = """
                    open qux@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=foo@1
                    close
                """

                fred1 = """
                    open fred@1
                    add depend type=require fmri=foo
                    close
                """
                fred2 = """
                    open fred@2
                    close
                """

                self.pkgsend_bulk(self.rurl, (foo1, foo2, fbar, qbar, qux1,
                    qux2, fred1))

                self.image_create(self.rurl)

                # First exact-install the non-obsolete version of foo
                self.pkg("exact-install foo@1")
                self.pkg("list foo@1")

                # Now exact-install the obsolete version, and ensure it disappears
                # (5).
                self.pkg("exact-install foo")
                self.pkg("list foo", exit=1)

                # Explicitly exact-installing an obsolete package succeeds, but
                # results in nothing on the system. (1)
                self.pkg("exact-install foo@2", exit=4)
                self.pkg("list foo", exit=1)

                # Exact-installing a package with a dependency on an obsolete
                # package fails. (2)
                self.pkg("exact-install fbar", exit=1)

                # Exact-installing a package with a dependency on a renamed
                # package succeeds, leaving the first package and the renamed
                # package on the system, as well as the empty, pre-renamed
                # package. (3)
                self.pkg("exact-install qbar")
                self.pkg("list qbar")
                self.pkg("list foo@1")
                self.pkg("list qux | grep -- i-r")
                self.pkg("uninstall '*'") #clean up for next test
                # A simple rename test: First exact-install the pre-renamed
                # version of qux.  Then install the renamed version, and see
                # that the new package is installed, and the renamed package
                # is installed, but marked renamed.  (4)
                self.pkg("exact-install qux@1")
                self.pkg("exact-install qux") # upgrades qux
                self.pkg("list foo@1")
                self.pkg("list qux", exit=1)
                self.pkg("uninstall '*'") #clean up for next test

                # Exact-install a package that's going to be obsoleted and a
                # package that depends on it.  Update the package to its
                # obsolete version and see that it fails.  (6, sorta)
                self.pkg("exact-install foo@1 fred@1")
                self.pkg("exact-install foo@2 fred@1", exit=1)

                # If fred is not in the command line, we should ignore its
                # restriction and install foo@2.
                self.pkg("exact-install foo@2")
                # now add a version of fred that doesn't require foo, and
                # show that update works
                self.pkgsend_bulk(self.rurl, fred2)
                self.pkg("refresh")
                self.pkg("exact-install foo@2 fred")
                self.pkg("uninstall '*'") #clean up for next test
                self.pkgrepo("remove -s {0} fred@2".format(self.rurl))

        def test_basic_7a(self):
                """Upgrade a package to a version with a dependency on a renamed
                package.  A => A' (-> Br (-> C))"""

                t7ap1_1 = """
                    open t7ap1@1
                    close
                """

                t7ap1_2 = """
                    open t7ap1@2
                    add depend type=require fmri=t7ap2
                    close
                """

                t7ap2_1 = """
                    open t7ap2@1
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=t7ap3
                    close
                """

                t7ap3_1 = """
                    open t7ap3@1
                    close
                """

                self.pkgsend_bulk(self.rurl, t7ap1_1)
                self.image_create(self.rurl)

                self.pkg("install t7ap1")

                self.pkgsend_bulk(self.rurl, (t7ap1_2, t7ap2_1, t7ap3_1))

                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list -af")
                self.pkg("list t7ap2 | grep -- i-r")
                self.pkg("list t7ap3")

        def test_basic_7b(self):
                """Upgrade a package to a version with a dependency on a renamed
                package.  Like 7a except package A starts off depending on B.

                A (-> B) => A' (-> Br (-> C))"""

                t7bp1_1 = """
                    open t7bp1@1
                    add depend type=require fmri=t7bp2
                    close
                """

                t7bp1_2 = """
                    open t7bp1@2
                    add depend type=require fmri=t7bp2
                    close
                """

                t7bp2_1 = """
                    open t7bp2@1
                    close
                """

                t7bp2_2 = """
                    open t7bp2@1
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=t7bp3
                    close
                """

                t7bp3_1 = """
                    open t7bp3@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t7bp1_1, t7bp2_1))
                self.image_create(self.rurl)

                self.pkg("install t7bp1")

                self.pkgsend_bulk(self.rurl, (t7bp1_2, t7bp2_2, t7bp3_1))

                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list t7bp2 | grep -- i-r")
                self.pkg("list t7bp3")

        def test_basic_7c(self):
                """Upgrade a package to a version with a dependency on a renamed
                package.  Like 7b, except package A doesn't change.

                A (-> B) => A (-> Br (-> C))"""

                t7cp1_1 = """
                    open t7cp1@1
                    add depend type=require fmri=t7cp2
                    close
                """

                t7cp2_1 = """
                    open t7cp2@1
                    close
                """

                t7cp2_2 = """
                    open t7cp2@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=t7cp3
                    close
                """

                t7cp3_1 = """
                    open t7cp3@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t7cp1_1, t7cp2_1))
                self.image_create(self.rurl)

                self.pkg("install t7cp1")

                self.pkgsend_bulk(self.rurl, (t7cp2_2, t7cp3_1))

                self.pkg("refresh")
                self.pkg("update")

                self.pkg("list t7cp2 | grep -- i-r")
                self.pkg("list t7cp3")

        def test_basic_6a(self):
                """Upgrade a package to a version with a dependency on an
                obsolete package.  This version is unlikely to happen in real
                life."""

                t6ap1_1 = """
                    open t6ap1@1
                    close
                """

                t6ap1_2 = """
                    open t6ap1@2
                    add depend type=require fmri=t6ap2
                    close
                """

                t6ap2_1 = """
                    open t6ap2@1
                    add set name=pkg.obsolete value=true
                    close
                """


                self.pkgsend_bulk(self.rurl, t6ap1_1)
                self.image_create(self.rurl)

                self.pkg("install t6ap1")

                self.pkgsend_bulk(self.rurl, (t6ap1_2, t6ap2_1))

                self.pkg("refresh")
                self.pkg("update", exit=4) # does nothing
                self.pkg("list t6ap1")

        def test_basic_6b(self):
                """Install a package with a dependency, and update after
                publishing updated packages for both, but where the dependency
                has become obsolete."""

                t6ap1_1 = """
                    open t6ap1@1
                    add depend type=require fmri=t6ap2
                    close
                """

                t6ap1_2 = """
                    open t6ap1@2
                    add depend type=require fmri=t6ap2
                    close
                """

                t6ap2_1 = """
                    open t6ap2@1
                    close
                """

                t6ap2_2 = """
                    open t6ap2@2
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (t6ap1_1, t6ap2_1))
                self.image_create(self.rurl)

                self.pkg("install t6ap1")
                self.pkg("list")

                self.pkgsend_bulk(self.rurl, (t6ap1_2, t6ap2_2))

                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list t6ap1@2 t6ap2@1")

        def test_basic_8a(self):
                """Upgrade a package to an obsolete leaf version when another
                depends on it."""

                t8ap1_1 = """
                    open t8ap1@1
                    close
                """

                t8ap1_2 = """
                    open t8ap1@2
                    add set name=pkg.obsolete value=true
                    close
                """

                t8ap2_1 = """
                    open t8ap2@1
                    add depend type=require fmri=t8ap1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t8ap1_1, t8ap2_1))
                self.image_create(self.rurl)

                self.pkg("install t8ap2")

                self.pkgsend_bulk(self.rurl, t8ap1_2)

                self.pkg("refresh")
                self.pkg("update", exit=4) # does nothing
                self.pkg("list  t8ap2@1")

        def test_basic_13a(self):
                """Publish an package with a dependency, then publish both as
                obsolete, update, and see that both packages have gotten
                removed."""

                t13ap1_1 = """
                    open t13ap1@1
                    add depend type=require fmri=t13ap2
                    close
                """

                t13ap1_2 = """
                    open t13ap1@2
                    add set name=pkg.obsolete value=true
                    close
                """

                t13ap2_1 = """
                    open t13ap2@1
                    close
                """

                t13ap2_2 = """
                    open t13ap2@2
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (t13ap1_1, t13ap2_1))
                self.image_create(self.rurl)

                self.pkg("install t13ap1")

                self.pkgsend_bulk(self.rurl, (t13ap1_2, t13ap2_2))

                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list", exit=1)

        def test_basic_11(self):
                """Install or exact-install a package with an ambiguous name,
                where only one match is non-obsolete."""

                self.basic_11_helper("install")
                self.basic_11_helper("exact-install")

        def basic_11_helper(self, install_cmd):
                t11p1 = """
                    open netbeans@1
                    add set name=pkg.obsolete value=true
                    close
                """

                t11p2 = """
                    open developer/netbeans@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t11p1, t11p2))
                self.image_create(self.rurl)

                self.pkg("{0} netbeans".format(install_cmd))
                self.pkg("list pkg:/developer/netbeans")
                self.pkg("list pkg:/netbeans", exit=1)

        def test_basic_11a(self):
                """Install or exact-install a package using an ambiguous name
                where pkg is renamed to another package, but not the
                conflicting one"""

                self.basic_11a_helper("install")
                self.basic_11a_helper("exact-install")

        def basic_11a_helper(self, install_cmd):
                t11p1 = """
                    open netbonze@1
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=SUNWnetbonze
                    close
                """

                t11p2 = """
                    open developer/netbonze@1
                    close
                """

                t11p3 = """
                    open SUNWnetbonze@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (t11p1, t11p2, t11p3))
                self.image_create(self.rurl)

                self.pkg("{0} netbonze".format(install_cmd), exit=1)

        def test_basic_11b(self):
                """Install or exact-install a package using an ambiguous name
                where only one match is non-renamed, and the renamed match
                is renamed to the other."""

                self.basic_11b_helper("install")
                self.basic_11b_helper("exact-install")

        def basic_11b_helper(self, install_cmd):
                t11p1 = """
                    open netbooze@1
                    close
                """

                t11p2 = """
                    open netbooze@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=developer/netbooze
                    close
                """

                t11p3 = """
                    open developer/netbooze@2
                    close
                """

                t11p4 = """
                    open developer/netbooze@3
                    add depend type=require fmri=developer/missing
                    close
                """

                self.pkgsend_bulk(self.rurl, (t11p1, t11p2, t11p3, t11p4))
                self.image_create(self.rurl)

                self.pkg("{0} netbooze".format(install_cmd))
                self.pkg("list pkg:/developer/netbooze")
                self.pkg("list pkg:/netbooze", exit=1)


        def test_basic_12(self):
                """Upgrade a package across a rename to an ambiguous name."""

                t12p1_1 = """
                    open netbeenz@1
                    close
                """

                t12p1_2 = """
                    open netbeenz@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/developer/netbeenz
                    close
                """

                t12p2_1 = """
                    open developer/netbeenz@1
                    close
                """

                self.pkgsend_bulk(self.rurl, t12p1_1)
                self.image_create(self.rurl)

                self.pkg("install netbeenz")

                self.pkgsend_bulk(self.rurl, (t12p1_2, t12p2_1))

                self.pkg("refresh")
                self.pkg("update -v")
                self.pkg("list pkg:/developer/netbeenz | grep -- i--")
                self.pkg("list pkg:/netbeenz", exit=1)

        def test_remove_renamed(self):
                """If a renamed package has nothing depending on it, it should
                be removed."""

                p1_1 = """
                    open remrenA@1
                    close
                """

                p1_2 = """
                    open remrenA@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/remrenB
                    close
                """

                p2_1 = """
                    open remrenB@1
                    close
                """

                p3_1 = """
                    open remrenC@1
                    add depend type=require fmri=pkg:/remrenA
                    close
                """

                self.pkgsend_bulk(self.rurl, p1_1)
                self.image_create(self.rurl)

                self.pkg("install remrenA")

                self.pkgsend_bulk(self.rurl, (p1_2, p2_1, p3_1))

                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list remrenA", exit=1)

                # But if there is something depending on the renamed package, it
                # can't be removed.
                self.pkg("uninstall remrenB")

                self.pkg("install remrenA@1 remrenC")
                self.pkg("update")
                self.pkg("list remrenA")

        def test_chained_renames(self):
                """If there are multiple renames, make sure we delete as much
                as possible, but no more."""

                A1 = """
                    open chained_A@1
                    close
                """

                A2 = """
                    open chained_A@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/chained_B@2
                    close
                """

                B2 = """
                    open chained_B@2
                    add set name=pkg.renamed value=true
                    add depend type=require fmri=pkg:/chained_C@2
                    close
                """

                C2 = """
                    open chained_C@2
                    close
                """

                X = """
                    open chained_X@1
                    add depend type=require fmri=pkg:/chained_A
                    close
                """

                Y = """
                    open chained_Y@1
                    add depend type=require fmri=pkg:/chained_B
                    close
                """

                Z = """
                    open chained_Z@1
                    close
                """

                self.pkgsend_bulk(self.rurl, (A1, A2, B2, C2, X, Y, Z))

                self.image_create(self.rurl)

                self.pkg("install chained_A@1 chained_X chained_Z")
                for p in ["chained_A@1", "chained_X@1"]:
                        self.pkg("list {0}".format(p))
                self.pkg("update")

                for p in ["chained_A@2", "chained_X@1", "chained_B@2",
                    "chained_C@2", "chained_Z"]:
                        self.pkg("list {0}".format(p))

                self.pkg("uninstall chained_X")

                for p in ["chained_C@2", "chained_Z"]:
                        self.pkg("list {0}".format(p))

                # make sure renamed pkgs no longer needed are uninstalled
                for p in ["chained_A@2", "chained_B@2"]:
                        self.pkg("list {0}".format(p), exit=1)

        def test_unobsoleted(self):
                """Ensure that the existence of an obsolete package version
                does not prevent the system from upgrading to or installing
                a resurrected version."""

                self.unobsoleted_helper("install")
                self.unobsoleted_helper("exact-install")

        def unobsoleted_helper(self, install_cmd):
                pA_1 = """
                    open reintroA@1
                    close
                """

                pA_2 = """
                    open reintroA@2
                    add set name=pkg.obsolete value=true
                    close
                """

                pA_3 = """
                    open reintroA@3
                    close
                """

                pB_1 = """
                    open reintroB@1
                    add depend type=require fmri=pkg:/reintroA@1
                    close
                """

                pB_2 = """
                    open reintroB@2
                    close
                """

                pB_3 = """
                    open reintroB@3
                    add depend type=require fmri=pkg:/reintroA@3
                    close
                """

                self.pkgsend_bulk(self.rurl, (pA_1, pA_2, pA_3, pB_1, pB_2,
                    pB_3))
                self.image_create(self.rurl)

                # Check installation of an unobsoleted package with no
                # dependencies.

                # Testing reintroA@1 -> reintroA@3 with update
                self.pkg("install reintroA@1")
                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Testing reintroA@1 -> reintroA@3 with install or
                # exact-install.
                self.pkg("{0} reintroA@1".format(install_cmd))
                self.pkg("{0} reintroA@3".format(install_cmd))
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Testing empty image -> reintroA@3 with install or
                # exact-install.
                self.pkg("{0} reintroA@3".format(install_cmd))
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Testing reintroA@1 -> reintroA@2 -> reintroA@3 with install
                # or exact-install.
                self.pkg("{0} reintroA@1".format(install_cmd))
                self.pkg("{0} reintroA@2".format(install_cmd))
                self.pkg("{0} reintroA@3".format(install_cmd))
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroA")

                # Check installation of a package with an unobsoleted
                # dependency.

                # Testing reintroB@1 -> reintroB@3 with update
                self.pkg("install reintroB@1")
                self.pkg("refresh")
                self.pkg("update")
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

                # Testing reintroB@1 -> reintroB@3 with install or
                # exact-install
                self.pkg("{0} reintroB@1".format(install_cmd))
                self.pkg("{0} reintroB@3".format(install_cmd))
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

                # Testing empty image -> reintroB@3 with install or
                # exact-install
                self.pkg("{0} reintroB@3".format(install_cmd))
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

                # Testing reintroB@1 -> reintroB@2 -> reintroB@3 with install
                # or exact-install
                self.pkg("{0} reintroB@1".format(install_cmd))
                self.pkg("{0} reintroB@2".format(install_cmd))
                self.pkg("{0} reintroB@3".format(install_cmd))
                self.pkg("list reintroB@3")
                self.pkg("list reintroA@3")
                self.pkg("uninstall reintroB reintroA")

        def test_incorp_1(self):
                """We should be able to incorporate an obsolete package."""

                self.incorp_1_helper("install")
                self.incorp_1_helper("exact-install")

        def incorp_1_helper(self, install_cmd):
                p1_1 = """
                    open inc1p1@1
                    add depend type=incorporate fmri=inc1p2@1
                    close
                """

                p2_1 = """
                    open inc1p2@1
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (p1_1, p2_1))
                self.image_create(self.rurl)

                if install_cmd == "install":
                        self.pkg("install inc1p1")
                        self.pkg("install inc1p2", exit=4)

                        self.pkg("list inc1p2", exit=1)
                else:
                        self.pkg("exact-install inc1p1")

        def test_incorp_2(self):
                """We should be able to continue incorporating a package when it
                becomes obsolete on upgrade."""

                p1_1 = """
                    open inc2p1@1
                    add depend type=incorporate fmri=inc2p2@1
                    close
                """

                p1_2 = """
                    open inc2p1@2
                    add depend type=incorporate fmri=inc2p2@2
                    close
                """

                p2_1 = """
                    open inc2p2@1
                    close
                """

                p2_2 = """
                    open inc2p2@2
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl, (p1_1, p2_1))
                self.image_create(self.rurl)

                self.pkg("install inc2p1 inc2p2")

                self.pkgsend_bulk(self.rurl, (p1_2, p2_2))

                self.pkg("refresh")
                self.pkg("list -afv")
                self.pkg("update -v")
                self.pkg("list inc2p2", exit=1)


class TestObsoletionNestedIncorporations(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)

        persistent_setup = True

        bug_15713570 = """
            open oldcompiler@1.0,5.11-0
            add depend type=require fmri=oldperl@1.0
            close
            open oldperl@1.0,5.11-0
            add depend type=require fmri=osnet-incorporation
            close
            open oldperl@2.0,5.11-0
            add set name=pkg.obsolete value=true
            close
            open entire@1.0,5.11-0
            add depend type=incorporate fmri=osnet-incorporation
            add depend type=incorporate fmri=osnet-incorporation@1
            add depend type=incorporate fmri=osnet-incorporation@1.0
            close
            open entire@2.1,5.11-0
            add depend type=incorporate fmri=osnet-incorporation
            add depend type=incorporate fmri=osnet-incorporation@1
            add depend type=incorporate fmri=osnet-incorporation@1.1
            close
            open entire@2.2,5.11-0
            add depend type=incorporate fmri=osnet-incorporation
            add depend type=incorporate fmri=osnet-incorporation@1
            add depend type=incorporate fmri=osnet-incorporation@1.2
            close
            open osnet-incorporation@1.0,5.11-0
            add depend type=incorporate fmri=oldperl@1.0
            close
            open osnet-incorporation@1.1,5.11-0
            add depend type=incorporate fmri=oldperl@2.0
            close
            open osnet-incorporation@1.2,5.11-0
            add depend type=incorporate fmri=oldperl@2.0
            close
       """

        def test_15713570(self):
                """If an unincorporated package has its dependency obsoleted
                by a doubly nested incorporation with multiple levels of
                incorporation, there is no useful error message generated"""

                self.pkgsend_bulk(self.rurl, self.bug_15713570)
                self.image_create(self.rurl)

                self.pkg("install -v entire@1.0 oldcompiler")
                self.pkg("list")
                self.pkg("verify")
                self.pkg("update -v entire", exit=4)
                self.pkg("list")
                self.pkg("verify")
                self.pkg("update -v entire@2", exit=1)

                self.assertTrue("oldcompiler" in self.errout and
                    "oldperl" in self.errout,
                    "error message does not mention oldcompiler and oldperl packages")


class TestPkgInstallMultiObsolete(pkg5unittest.ManyDepotTestCase):
        """Tests involving obsolete packages and multiple publishers."""

        obs = """
            open stem@1
            add set name=pkg.obsolete value=true
            close
        """

        nonobs = """
            open stem@1
            close
        """

        persistent_setup = True

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()

        def test_01(self):
                """If an obsolete package is found in a preferred publisher and
                a non-obsolete package of the same name is found in a
                non-preferred publisher, pick the preferred pub as usual """

                self.helper_01("install")
                self.helper_01("exact-install")

        def helper_01(self, install_cmd):
                self.pkgsend_bulk(self.rurl1, self.obs)
                self.pkgsend_bulk(self.rurl2, self.nonobs)

                self.image_create(self.rurl1, prefix="test1")
                self.pkg("set-publisher -O " + self.rurl2 + " test2")
                self.pkg("list -a")

                self.pkg("{0} stem".format(install_cmd), exit=4) # noting to do since it's obs
                # We should choose the obsolete package, which means nothing
                # gets installed.
                self.pkg("list", exit=1)

        def test_02(self):
                """Same as test_01, but now we have ambiguity in the package
                names.  While at first blush we might follow the same rule as in
                test_01 (choose the preferred publisher), in this case, we can't
                figure out which package from the preferred publisher we want,
                so the choice already isn't as straightforward, so we choose the
                non-obsolete package."""

                self.helper_02("install")
                self.helper_02("exact-install")

        def helper_02(self, install_cmd):
                lobs = """
                    open some/stem@1
                    add set name=pkg.obsolete value=true
                    close
                """

                self.pkgsend_bulk(self.rurl1, (self.obs, lobs))
                self.pkgsend_bulk(self.rurl2, (self.nonobs, lobs))

                self.image_create(self.rurl1, prefix="test1")
                self.pkg("set-publisher -O " + self.rurl2 + " test2")

                self.pkg("{0} stem".format(install_cmd), exit=1)


class TestPkgInstallMultiIncorp(pkg5unittest.ManyDepotTestCase):
        """Tests involving incorporations and multiple publishers."""

        incorporated_latest = """
            open vim@7.4.233-5.12.0.0.0.44.1
            close
            open vim@7.4.232-5.12.0.0.0.44.1
            close"""

        incorporated = """
            open vim@7.4.1-5.12.0.0.0.45.0
            close
            open vim@7.4.1-5.12.0.0.0.44.1
            close """

        incorporates = """
            open userland-incorporation@0.5.12-5.12.0.0.0.44.1
            add depend type=incorporate fmri=vim@7.4-5.12.0.0.0.44.1
            close
            open vim-incorporation@0.5.12-5.12.0.0.0.44.1
            add depend type=incorporate fmri=vim@7.4.1-5.12.0.0.0.44.1
            close"""

        persistent_setup = True

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()

        def test_1_incorp_latest_older(self):
                """Ensure that if the newest release version of a package is
                available for an older branch that incorporate dependencies work
                as expected."""

                self.image_create(self.rurl1)
                self.pkgsend_bulk(self.rurl1, (self.incorporates,
                    self.incorporated, self.incorporated_latest))

                # First, install two incorporations that intersect such that
                # only the version before the latest branch can be installed.
                self.pkg("install userland-incorporation vim-incorporation")

                # Then, attempt to install vim; this should succeed even though
                # the newest version available is for an older branch.
                self.pkg("install vim@7.4")

        def test_2_incorp_multi_pub(self):
                """Ensure that if another publisher offers newer packages that
                satisfy an incorporate dependency, but are rejected because of
                publisher selection, that the preferred publisher's package can
                still satisfy the incorporate."""

                self.image_create(self.rurl1)
                self.pkgsend_bulk(self.rurl1, (self.incorporates,
                    self.incorporated))
                self.pkgsend_bulk(self.rurl2, self.incorporated_latest)

                # First, install the incorporation.
                self.pkg("install userland-incorporation")

                # Next, add the second publisher.
                self.pkg("set-publisher -p {0}".format(self.rurl2))

                # Next, verify that first publisher's incorporated package can
                # be installed since it satisfies incorporate dependencies even
                # though second publisher's versions will be rejected.
                self.pkg("install //test1/vim")


class TestPkgInstallLicense(pkg5unittest.SingleDepotTestCase):
        """Tests involving one or more packages that require license acceptance
        or display."""

        maxDiff = None
        persistent_depot = True

        # Tests in this suite use the read only data directory.
        need_ro_data = True

        baz10 = """
            open baz@1.0,5.11-0
            add license copyright.baz license=copyright.baz
            close """

        # First iteration has just a copyright.
        licensed10 = """
            open licensed@1.0,5.11-0
            add depend type=require fmri=baz@1.0
            add license copyright.licensed license=copyright.licensed
            close """

        # Second iteration has copyright that must-display and a new license
        # that doesn't require acceptance.
        licensed12 = """
            open licensed@1.2,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed
            close """

        # Third iteration now requires acceptance of license.
        licensed13 = """
            open licensed@1.3,5.11-0
            add depend type=require fmri=baz@1.0
            add file libc.so.1 mode=0555 owner=root group=bin path=/lib/libc.so.1
            add license copyright.licensed license=copyright.licensed must-display=True
            add license license.licensed license=license.licensed must-accept=True
            close """

        misc_files = ["copyright.baz", "copyright.licensed", "libc.so.1",
            "license.licensed", "license.licensed.addendum"]

        # Packages with copyright in non-ascii character
        nonascii10 = """
            open nonascii@1.0,5.11-0
            add license 88591enc.copyright license=copyright
            close """

        # Packages with copyright in non-ascii character
        utf8enc10 = """
            open utf8enc@1.0,5.11-0
            add license utf8enc.copyright license=copyright
            close """

        # Packages with copyright in unsupported character set
        unsupported10 = """
            open unsupported@1.0,5.11-0
            add license unsupported.copyright license=copyright
            close """

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, publisher="bobcat")
                self.make_misc_files(self.misc_files)

                # Use license with latin1 i.e 88591 encoding
                n_copyright = os.path.join(self.ro_data_root,
                    "88591enc.copyright")
                self.make_misc_files({"88591enc.copyright": n_copyright})

                # Use utf-8 encoding license
                utf_copyright = os.path.join(self.ro_data_root,
                    "utf8enc.copyright")
                self.make_misc_files({"utf8enc.copyright": utf_copyright})

                # Use unsupported license
                u_copyright = os.path.join(self.ro_data_root,
                    "unsupported.copyright")
                self.make_misc_files({"unsupported.copyright": u_copyright})

                self.plist = self.pkgsend_bulk(self.rurl, (self.licensed10,
                    self.licensed12, self.licensed13, self.baz10,
                    self.nonascii10, self.utf8enc10, self.unsupported10))


        def test_01_install_update(self):
                """Verifies that install and update handle license
                acceptance and display."""

                self.image_create(self.rurl, prefix="bobcat")

                # First, test the basic install case to see if a license that
                # does not require viewing or acceptance will be installed.
                self.pkg("install --parsable=0 licensed@1.0")
                self.assertEqualParsable(self.output,
                    add_packages=[self.plist[3], self.plist[0]], licenses=[
                        [self.plist[3], [],
                            [self.plist[3], "copyright.baz", "copyright.baz",
                            False, False]],
                        [self.plist[0], [],
                            [self.plist[0], "copyright.licensed",
                            "copyright.licensed", False, False]
                        ]])
                self.pkg("list")
                self.pkg("info licensed@1.0 baz@1.0")

                # Verify that --licenses include the license in output.
                self.pkg("install -n --licenses licensed@1.2 | "
                    "grep 'license.licensed'")

                # Verify that licenses that require display are included in
                # -n output even if --licenses is not provided.
                self.pkg("install -n licensed@1.2 | grep 'copyright.licensed'")

                # Next, check that an upgrade succeeds when a license requires
                # display and that the license will be displayed.
                self.pkg("install --parsable=0 licensed@1.2")
                self.assertEqualParsable(self.output,
                    change_packages=[[self.plist[0], self.plist[1]]], licenses=[
                        [self.plist[1],
                            [],
                            [self.plist[1], "license.licensed",
                            "license.licensed", False, False]],
                        [self.plist[1],
                            [self.plist[0], "copyright.licensed",
                            "copyright.licensed", False, False],
                            [self.plist[1], "copyright.licensed",
                            "copyright.licensed", False, True]]])

                # Next, check that an update fails if the user has not
                # specified --accept and a license requires acceptance.
                self.pkg("update -v", exit=6)
                # Check that asking for parsable output doesn't change this
                # requirement.
                self.pkg("update --parsable=0", exit=6)

                # Verify that licenses are not included in -n output if
                # --licenses is not provided.
                self.pkg("update -n | grep 'copyright.licensed", exit=1)

                # Verify that --licenses include the license in output.
                self.pkg("update -n --licenses | "
                    "grep 'license.licensed'")

                # Next, check that an update succeeds if the user has
                # specified --accept and a license requires acceptance.
                self.pkg("update --parsable=0 --accept")
                self.assertEqualParsable(self.output,
                    change_packages=[[self.plist[1], self.plist[2]]], licenses=[
                        [self.plist[2],
                            [self.plist[1], "license.licensed",
                            "license.licensed", False, False],
                            [self.plist[2], "license.licensed",
                            "license.licensed", True, False]]])
                self.pkg("info licensed@1.3")

        def test_02_bug_7127117(self):
                """Verifies that install with --parsable handles licenses
                with non-ascii & non UTF locale"""
                self.image_create(self.rurl, prefix="bobcat")

                self.pkg("install --parsable=0 nonascii@1.0")
                self.pkg("install --parsable=0 utf8enc@1.0")
                self.pkg("install --parsable=0 unsupported@1.0")


class TestActionErrors(pkg5unittest.SingleDepotTestCase):
        """This set of tests is intended to verify that the client will handle
        image state and action errors gracefully during install or uninstall
        operations.  Unlike the client API version of these tests, the CLI only
        needs to be tested for failure cases since it uses the client API."""

        # Teardown the test root every time.
        persistent_setup = False

        dir10 = """
            open dir@1.0,5.11-0
            add dir path=dir mode=755 owner=root group=bin
            close """

        dir11 = """
            open dir@1.1,5.11-0
            add dir path=dir mode=750 owner=root group=bin
            close """

        # Purposefully omits depend on dir@1.0.
        filesub10 = """
            open filesub@1.0,5.11-0
            add file tmp/file path=dir/file mode=755 owner=root group=bin
            close """

        filesub11 = """
            open filesub@1.1,5.11-0
            add file tmp/file path=dir/file mode=444 owner=root group=bin
            close """

        # Dependency providing file intentionally omitted.
        hardlink10 = """
            open hardlink@1.0,5.11-0
            add hardlink path=hardlink target=file
            close """

        # Empty packages suitable for corruption testing.
        foo10 = """
            open foo@1.0,5.11-0
            close """

        unsupp10 = """
            open unsupported@1.0
            add depend type=require fmri=foo@1.0
            close """

        misc_files = ["tmp/file"]

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)

                plist = self.pkgsend_bulk(self.rurl, (self.dir10, self.dir11,
                    self.filesub10, self.filesub11, self.hardlink10))

                self.plist = {}
                for p in plist:
                        pfmri = fmri.PkgFmri(p)
                        self.plist[pfmri.pkg_name] = pfmri

        @staticmethod
        def __write_empty_file(target, mode=644, owner="root", group="bin"):
                f = open(target, "w")
                f.write("\n")
                f.close()
                os.chmod(target, mode)
                owner = portable.get_user_by_name(owner, "/", True)
                group = portable.get_group_by_name(group, "/", True)
                os.chown(target, owner, group)

        def test_00_directory(self):
                """Verify that directory install fails as expected when it has
                been replaced with a link prior to install."""

                self.image_create(self.rurl)

                # The dest_dir's installed path.
                dest_dir_name = "dir"
                dest_dir = os.path.join(self.get_img_path(), dest_dir_name)

                # Directory replaced with a link (fails for install).
                self.__write_empty_file(dest_dir + ".src")
                os.symlink(dest_dir + ".src", dest_dir)
                self.pkg("install {0}".format(dest_dir_name), exit=1)

        def test_01_file(self):
                """Verify that file install works as expected when its parent
                directory has been replaced with a link."""

                self.image_create(self.rurl)

                # File's parent directory replaced with a link.
                self.pkg("install dir")
                src = os.path.join(self.get_img_path(), "dir")
                os.mkdir(os.path.join(self.get_img_path(), "export"))
                new_src = os.path.join(os.path.dirname(src), "export", "dir")
                shutil.move(src, os.path.dirname(new_src))
                os.symlink(new_src, src)
                self.pkg("install filesub@1.0", exit=1)

        def test_02_hardlink(self):
                """Verify that hardlink install fails as expected when
                hardlink target is missing."""

                self.image_create(self.rurl)

                # Hard link target is missing (failure expected).
                self.pkg("install hardlink", exit=1)

        def __populate_repo(self, unsupp_content=None):
                # Publish a package and then add some unsupported action data
                # to the repository's copy of the manifest and catalog.
                sfmri = self.pkgsend_bulk(self.rurl, self.unsupp10)[0]

                if unsupp_content is None:
                        # No manipulation required.
                        return

                pfmri = fmri.PkgFmri(sfmri)
                repo = self.get_repo(self.dcs[1].get_repodir())
                mpath = repo.manifest(pfmri)
                with open(mpath, "a+") as mfile:
                        mfile.write(unsupp_content + "\n")

                mcontent = None
                with open(mpath, "r") as mfile:
                        mcontent = mfile.read()

                cat = repo.get_catalog("test")
                cat.log_updates = False

                # Update the catalog signature.
                entry = cat.get_entry(pfmri)
                entry["signature-sha-1"] = manifest.Manifest.hash_create(
                    mcontent)

                # Update the catalog actions.
                dpart = cat.get_part("catalog.dependency.C", must_exist=True)
                entry = dpart.get_entry(pfmri)
                entry["actions"].append(unsupp_content)

                # Write out the new catalog.
                cat.save()

        def test_03_unsupported(self):
                """Verify that packages with invalid or unsupported actions are
                handled gracefully.
                """

                # Base package needed for tests.
                self.pkgsend_bulk(self.rurl, self.foo10)

                # Verify that a package with unsupported content doesn't cause
                # a problem.
                newact = "depend type=new-type fmri=foo@1.1"

                # Now create a new image and verify that pkg install will fail
                # for the unsupported package, but succeed for the supported
                # one.
                self.__populate_repo(newact)
                self.image_create(self.rurl)
                self.pkg("install foo@1.0")
                self.pkg("install unsupported@1.0", exit=1)
                self.pkg("uninstall foo")
                self.pkg("install foo@1.0 unsupported@1.0", exit=1)

                # Verify that a package with invalid content behaves the same.
                newact = "depend notvalid"
                self.__populate_repo(newact)
                self.pkg("refresh --full")
                self.pkg("install foo@1.0")
                self.pkg("install unsupported@1.0", exit=1)
                self.pkg("uninstall foo")

                # Now verify that if a newer version of the unsupported package
                # is found that is supported, it can be installed.
                self.__populate_repo()
                self.pkg("refresh --full")
                self.pkg("install foo@1.0 unsupported@1.0")
                self.pkg("uninstall foo unsupported")

        def test_04_loop(self):
                """Verify that if a directory or file is replaced with a link
                that targets itself (resulting in ELOOP) pkg fails gracefully.
                """

                # Create an image and install a package delivering a file.
                self.image_create(self.rurl)
                self.pkg("install dir@1.0 filesub@1.0")

                # Now replace the file with a link that points to itself.
                def create_link_loop(fpath):
                        if os.path.isfile(fpath):
                                portable.remove(fpath)
                        else:
                                shutil.rmtree(fpath)
                        cwd = os.getcwd()
                        os.chdir(os.path.dirname(fpath))
                        os.symlink(os.path.basename(fpath),
                            os.path.basename(fpath))
                        os.chdir(cwd)

                fpath = self.get_img_file_path("dir/file")
                create_link_loop(fpath)

                # Verify that pkg verify gracefully fails if traversing a
                # link targeting itself.
                self.pkg("verify", exit=1)

                # Verify that pkg succeeds if attempting to update a
                # package containing a file replaced with a link loop.
                self.pkg("update filesub")
                self.pkg("verify")

                # Now remove the package delivering the file and replace the
                # directory with a link loop.
                self.pkg("uninstall filesub")
                fpath = self.get_img_file_path("dir")
                create_link_loop(fpath)

                # Verify that pkg verify gracefully fails if traversing a
                # link targeting itself.
                self.pkg("verify", exit=1)

                # Verify that pkg gracefully fails if attempting to update
                # a package containing a directory replace with a link loop.
                self.pkg("update", exit=1)


class TestConflictingActions(_TestHelper, pkg5unittest.SingleDepotTestCase):
        """This set of tests verifies that packages which deliver conflicting
        actions into the same name in a namespace cannot be installed
        simultaneously."""

        pkg_boring10 = """
            open boring@1.0,5.11-0
            close """

        pkg_dupfiles = """
            open dupfiles@0,5.11-0
            add file tmp/file1 path=dir/pathname mode=0755 owner=root group=bin
            add file tmp/file2 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesp1 = """
            open dupfilesp1@0,5.11-0
            add file tmp/file1 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesp2 = """
            open dupfilesp2@0,5.11-0
            add file tmp/file2 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesp2v2 = """
            open dupfilesp2@2,5.11-0
            close
        """

        pkg_dupfilesp3 = """
            open dupfilesp3@0,5.11-0
            add file tmp/file2 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesp4 = """
            open dupfilesp4@0,5.11-0
            add file tmp/file3 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupotherfilesp1 = """
            open dupotherfilesp1@0,5.11-0
            add file tmp/file1 path=dir/namepath mode=0755 owner=root group=bin
            close
        """

        pkg_dupotherfilesp2 = """
            open dupotherfilesp2@0,5.11-0
            add file tmp/file2 path=dir/namepath mode=0755 owner=root group=bin
            close
        """

        pkg_dupotherfilesp2v2 = """
            open dupotherfilesp2@2,5.11-0
            close
        """

        pkg_dupotherfilesp3 = """
            open dupotherfilesp3@0,5.11-0
            add file tmp/file3 path=dir/namepath mode=0755 owner=root group=bin
            close
        """

        pkg_identicalfiles = """
            open identicalfiles@0,5.11-0
            add file tmp/file1 path=dir/pathname mode=0755 owner=root group=bin
            add file tmp/file1 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_overlaid = """
            open overlaid@0,5.11-0
            add dir path=etc mode=0755 owner=root group=root
            add file tmp/file1 path=etc/pam.conf mode=644 owner=root group=sys preserve=true overlay=allow
            close
            open overlaid@1,5.11-0
            add dir path=etc mode=0755 owner=root group=root
            add file tmp/file1 path=etc/pam.conf mode=644 owner=root group=sys preserve=renamenew overlay=allow
            close
            open overlaid@2,5.11-0
            add dir path=etc mode=0755 owner=root group=root
            add file tmp/file3 path=etc/pam.conf mode=644 owner=root group=sys preserve=renamenew overlay=allow
            close
            open overlaid@3,5.11-0
            add set name=pkg.renamed value=true
            add depend type=require fmri=overlaid-renamed@3
            add depend type=exclude fmri=overlaid-renamed@4
            close
            open overlaid-renamed@3,5.11-0
            add depend type=optional fmri=overlaid@3
            add dir path=etc mode=0755 owner=root group=root
            add file tmp/file3 original_name=overlaid:etc/pam.conf path=etc/pam.conf mode=644 owner=root group=sys preserve=renamenew overlay=allow
            close
            open overlaid-renamed@4.0,5.11-0
            add depend type=optional fmri=overlaid@3
            add dir path=etc mode=0755 owner=root group=root
            add dir path=etc/pam mode=0755 owner=root group=root
            add file tmp/file4 original_name=overlaid:etc/pam.conf path=etc/pam/pam.conf mode=644 owner=root group=sys preserve=renamenew
            close
            open overlaid-renamed@4.1,5.11-0
            add depend type=optional fmri=overlaid@3
            add dir path=etc mode=0755 owner=root group=root
            add dir path=etc/pam mode=0755 owner=root group=root
            add file tmp/file4 original_name=overlaid:etc/pam.conf path=etc/pam/pam.conf mode=644 owner=root group=sys preserve=renamenew overlay=allow
            close
        """

        # 'overlay' is ignored unless 'preserve' is also set.
        pkg_invalid_overlaid = """
            open invalid-overlaid@0,5.11-0
            add file tmp/file1 path=etc/pam.conf mode=644 owner=root group=sys overlay=allow
            close
        """

        pkg_overlayer = """
            open overlayer@0,5.11-0
            add file tmp/file2 path=etc/pam.conf mode=644 owner=root group=sys preserve=true overlay=true
            close
        """

        pkg_overlayer_move = """
            open overlayer-move@0,5.11-0
            add file tmp/file2 path=etc/pam.conf mode=644 owner=root group=sys preserve=true overlay=true
            close
            open overlayer-move@1,5.11-0
            add file tmp/file3 path=etc/pam/pam.conf mode=644 owner=root group=sys preserve=true overlay=true original_name=overlayer-move:etc/pam.conf
            close
        """

        pkg_overlayer_update = """
            open overlayer-update@0,5.11-0
            add file tmp/file1 path=etc/pam.conf mode=644 owner=root group=sys overlay=true
            close
            open overlayer-update@1,5.11-0
            add file tmp/file2 path=etc/pam.conf mode=644 owner=root group=sys preserve=true overlay=true
            close
            open overlayer-update@2,5.11-0
            add file tmp/file3 path=etc/pam.conf mode=644 owner=root group=sys preserve=renameold overlay=true
            close
            open overlayer-update@3,5.11-0
            add file tmp/file4 path=etc/pam.conf mode=644 owner=root group=sys preserve=renamenew overlay=true
            close
        """

        pkg_multi_overlayer = """
            open multi-overlayer@0,5.11-0
            add file tmp/file2 path=etc/pam.conf mode=644 owner=root group=sys preserve=true overlay=true
            close
        """

        # overlaying file is treated as conflicting file if its mode, owner, and
        # group attributes don't match the action being overlaid
        pkg_mismatch_overlayer = """
            open mismatch-overlayer@0,5.11-0
            add file tmp/file2 path=etc/pam.conf mode=640 owner=root group=bin preserve=true overlay=true
            close
        """

        # overlaying file is treated as conflicting file if it doesn't set overlay=true
        # even if file being overlaid allows overlay.
        pkg_invalid_overlayer = """
            open invalid-overlayer@0,5.11-0
            add file tmp/file2 path=etc/pam.conf mode=644 owner=root group=sys preserve=true
            close
        """

        pkg_unpreserved_overlayer = """
            open unpreserved-overlayer@0,5.11-0
            add file tmp/unpreserved path=etc/pam.conf mode=644 owner=root group=sys overlay=true
            close
        """

        pkgremote_pkg1 = """
            open pkg1@0,5.11-0
            add file tmp/file1 path=remote mode=644 owner=root group=sys
            close
        """

        pkgremote_pkg2 = """
            open pkg2@0,5.11-0
            add file tmp/file2 path=remote mode=644 owner=root group=sys
            close
        """

        pkg_dupfilesv1 = """
            open dupfilesv1@0,5.11-0
            add set name=variant.arch value=sparc value=i386
            add dir path=dir/pathname mode=0755 owner=root group=bin variant.arch=i386
            close
        """

        pkg_dupfilesv2 = """
            open dupfilesv2@0,5.11-0
            add dir path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesv3 = """
            open dupfilesv3@0,5.11-0
            add set name=variant.arch value=sparc value=i386
            add dir path=dir/pathname mode=0777 owner=root group=bin variant.arch=sparc
            close
        """

        pkg_dupfilesv4 = """
            open dupfilesv4@0,5.11-0
            add set name=variant.arch value=sparc value=i386
            add file tmp/file1 path=dir/pathname mode=0777 owner=root group=bin variant.arch=sparc
            add file tmp/file2 path=dir/pathname mode=0777 owner=root group=bin variant.arch=sparc
            add file tmp/file3 path=dir/pathname mode=0777 owner=root group=bin variant.arch=i386
            close
        """

        pkg_dupfilesv5 = """
            open dupfilesv5@0,5.11-0
            add set name=variant.opensolaris.zone value=global value=nonglobal
            add file tmp/file1 path=dir/pathname mode=0777 owner=root group=bin variant.opensolaris.zone=nonglobal
            close
        """

        pkg_dupfilesv6 = """
            open dupfilesv6@0,5.11-0
            add file tmp/file2 path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesf1 = """
            open dupfilesf1@0,5.11-0
            add dir path=dir/pathname mode=0755 owner=root group=bin facet.devel=true
            close
        """

        pkg_dupfilesf2 = """
            open dupfilesf2@0,5.11-0
            add dir path=dir/pathname mode=0755 owner=root group=bin facet.devel=false
            close
        """

        pkg_dupfilesf3 = """
            open dupfilesf3@0,5.11-0
            add dir path=dir/pathname mode=0755 owner=root group=bin
            close
        """

        pkg_dupfilesf4 = """
            open dupfilesf4@0,5.11-0
            add file tmp/file1 path=dir/pumpkin mode=0755 owner=root group=bin
            add file tmp/file2 path=dir/pumpkin mode=0755 owner=root group=bin facet.devel=true
            close
        """

        pkg_duppathfilelink = """
            open duppath-filelink@0,5.11-0
            add file tmp/file1 path=dir/pathname mode=0755 owner=root group=bin
            add link path=dir/pathname target=dir/other
            close
        """

        pkg_duplink = """
            open duplink@0,5.11-0
            add link path=dir/pathname target=dir/other
            close
        """

        pkg_dupmultitypes1 = """
            open dupmultitypes@1,5.11-0
            add link path=multitypepath target=dir/other
            add file tmp/file1 path=multitypepath mode=0644 owner=root group=bin
            add dir path=multitypepath mode=0755 owner=root group=bin
            close
        """

        pkg_dupmultitypes2 = """
            open dupmultitypes@2,5.11-0
            add dir path=multitypepath mode=0755 owner=root group=bin
            close
        """

        pkg_dupmultitypes3_0 = """
            open dupmultitypes3@0,5.11-0
            add link path=multitypepath target=blah
            add link path=multitypepath target=blah
            close
        """

        pkg_dupmultitypes3_1 = """
            open dupmultitypes3@1,5.11-0
            add dir path=multitypepath mode=0755 owner=root group=bin
            add dir path=multitypepath mode=0755 owner=root group=bin
            close
        """

        pkg_duppathnonidenticallinks = """
            open duppath-nonidenticallinks@0,5.11-0
            add link path=dir/pathname target=dir/something
            add link path=dir/pathname target=dir/other
            close
        """

        pkg_duppathnonidenticallinksp1 = """
            open duppath-nonidenticallinksp1@0,5.11-0
            add link path=dir/pathname target=dir/something
            close
        """

        pkg_duppathnonidenticallinksp2 = """
            open duppath-nonidenticallinksp2@0,5.11-0
            add link path=dir/pathname target=dir/other
            close
        """

        pkg_duppathnonidenticallinksp2v1 = """
            open duppath-nonidenticallinksp2@1,5.11-0
            close
        """

        pkg_duppathnonidenticaldirs = """
            open duppath-nonidenticaldirs@0,5.11-0
            add dir path=dir/pathname owner=root group=root mode=0755
            add dir path=dir/pathname owner=root group=bin mode=0711
            close
        """

        pkg_duppathalmostidenticaldirs = """
            open duppath-almostidenticaldirs@0,5.11-0
            add dir path=dir/pathname owner=root group=root mode=0755
            add dir path=dir/pathname owner=root group=root mode=755
            close
        """

        pkg_implicitdirs = """
            open implicitdirs@0,5.11-0
            add file tmp/file1 path=usr/bin/something mode=0755 owner=root group=bin
            add file tmp/file2 path=usr/bin mode=0755 owner=root group=bin
            close
        """

        pkg_implicitdirs2 = """
            open implicitdirs2@0,5.11-0
            add file tmp/file1 path=usr/bin/something mode=0755 owner=root group=bin
            add dir path=usr/bin mode=0700 owner=root group=bin
            close
        """

        pkg_implicitdirs3 = """
            open implicitdirs3@0,5.11-0
            add file tmp/file1 path=usr/bin/other mode=0755 owner=root group=bin
            close
        """

        pkg_implicitdirs4 = """
            open implicitdirs4@0,5.11-0
            add file tmp/file1 path=usr/bin/something mode=0755 owner=root group=bin
        """

        pkg_implicitdirs5 = """
            open implicitdirs5@0,5.11-0
            add dir path=usr/bin mode=0755 owner=root group=sys
        """

        pkg_implicitdirs6 = """
            open implicitdirs6@0,5.11-0
            add dir path=usr/bin mode=0755 owner=root group=bin
        """

        pkg_implicitdirs7 = """
            open implicitdirs7@0,5.11-0
            add file tmp/file1 path=usr/bin mode=0755 owner=root group=bin
        """

        pkg_dupdir = """
            open dupdir@0,5.11-0
            add dir path=dir/pathname owner=root group=bin mode=0755
            close
        """

        pkg_dupdirv1 = """
            open dupdir@1,5.11-0
            close
        """

        pkg_dupdirnowhere = """
            open dupdirnowhere@0,5.11-0
            add dir path=dir/pathname owner=root group=bin mode=0755
            close
        """

        pkg_dupdirp1 = """
            open dupdirp1@1,5.11-0
            add dir path=dir owner=root group=bin mode=0755
            close
        """

        pkg_dupdirp2 = """
            open dupdirp2@1,5.11-0
            add dir path=dir owner=root group=sys mode=0755
            close
        """

        pkg_dupdirp2_2 = """
            open dupdirp2@2,5.11-0
            add dir path=dir owner=root group=bin mode=0755
            close
        """

        pkg_dupdirp3 = """
            open dupdirp3@1,5.11-0
            add dir path=dir owner=root group=bin mode=0750
            close
        """

        pkg_dupdirp4 = """
            open dupdirp4@1,5.11-0
            add dir path=dir owner=root group=sys mode=0750
            close
        """

        pkg_dupdirp5 = """
            open dupdirp5@1,5.11-0
            add dir path=dir owner=root group=other mode=0755
            close
        """

        pkg_dupdirp6 = """
            open dupdirp6@1,5.11-0
            add dir path=dir owner=root group=other mode=0755
            close
        """

        pkg_dupdirp7 = """
            open dupdirp7@1,5.11-0
            add file tmp/file1 path=dir/file owner=root group=other mode=0755
            close
        """

        pkg_dupdirp8 = """
            open dupdirp8@1,5.11-0
            add dir path=dir owner=root group=bin mode=0755
            close
        """

        pkg_dupdirp8_2 = """
            open dupdirp8@2,5.11-0
            add dir path=dir owner=root group=sys mode=0755
            close
        """

        pkg_dupdirp9 = """
            open dupdirp9@1,5.11-0
            add dir path=var owner=root group=other mode=0755
            add dir path=usr owner=root group=other mode=0755
            close
        """

        pkg_dupdirp10 = """
            open dupdirp10@1,5.11-0
            add dir path=var owner=root group=bin mode=0755
            add dir path=usr owner=root group=bin mode=0755
            close
        """

        pkg_dupdirp11 = """
            open dupdirp11@1,5.11-0
            add dir path=usr/bin owner=root group=bin mode=0755
            add dir path=var/zap owner=root group=bin mode=0755
            close
        """

        pkg_dupdirp12 = """
            open dupdirp12@1,5.11-0
            add dir path=usr/bin owner=root group=bin mode=0755
            add legacy pkg=dupdirp9
            close
        """

        pkg_userdb = """
            open userdb@0,5.11-0
            add file tmp/passwd mode=0644 owner=root group=bin path=etc/passwd preserve=true
            add file tmp/group mode=0644 owner=root group=bin path=etc/group preserve=true
            add file tmp/shadow mode=0600 owner=root group=bin path=etc/shadow preserve=true
            add file tmp/ftpusers mode=0644 owner=root group=bin path=etc/ftpd/ftpusers preserve=true
            close
        """

        userdb_files = {
            "tmp/passwd": """\
root:x:0:0::/root:/usr/bin/bash
daemon:x:1:1::/:
bin:x:2:2::/usr/bin:
sys:x:3:3::/:
adm:x:4:4:Admin:/var/adm:
""",
            "tmp/group": """\
root::0:
other::1:root
bin::2:root,daemon
sys::3:root,bin,adm
adm::4:root,daemon
""",
            "tmp/shadow": """\
root:9EIfTNBp9elws:13817::::::
daemon:NP:6445::::::
bin:NP:6445::::::
sys:NP:6445::::::
adm:NP:6445::::::
""",
            "tmp/ftpusers": """\
root
bin
sys
adm
"""
        }

        pkg_dupuser = """
            open dupuser@0,5.11-0
            add user username=kermit group=adm gcos-field="kermit 1"
            add user username=kermit group=adm gcos-field="kermit 2"
            close
        """

        pkg_dupuserp1 = """
            open dupuserp1@0,5.11-0
            add user username=kermit group=adm gcos-field="kermit 1"
            close
        """

        pkg_dupuserp2 = """
            open dupuserp2@0,5.11-0
            add user username=kermit group=adm gcos-field="kermit 2"
            close
        """

        pkg_dupuserp2v2 = """
            open dupuserp2@1,5.11-0
            close
        """

        pkg_dupuserp3 = """
            open dupuserp3@0,5.11-0
            add user username=kermit group=adm gcos-field="kermit 2"
            close
        """

        pkg_dupuserp4 = """
            open dupuserp4@0,5.11-0
            add user username=kermit group=adm gcos-field="kermit 4"
            close
        """

        pkg_otheruser = """
            open otheruser@0,5.11-0
            add user username=fozzie group=adm home-dir=/export/home/fozzie
            close
        """

        pkg_othergroup = """
            open othergroup@0,5.11-0
            add group groupname=fozzie gid=87
            add group groupname=fozzie gid=88
            add group groupname=fozzie gid=89
            close
        """

        pkg_othergroup1 = """
            open othergroup@1,5.11-0
            add group groupname=fozzie gid=87
            close
        """

        pkg_conflictgroup1 = """
            open conflictgroup1@0,5.11
            add user group=fozzie uid=20 username=fozzie
            add group groupname=fozzie gid=200
            close
        """

        pkg_conflictgroup2 = """
            open conflictgroup2@0,5.11
            add user group=fozzie uid=21 username=fozzie
            add group groupname=fozzie gid=201
            close
        """

        pkg_driverdb = """
            open driverdb@0,5.11-0
            add file tmp/devlink.tab path=etc/devlink.tab mode=0644 owner=root group=bin
            add file tmp/driver_aliases path=etc/driver_aliases mode=0644 owner=root group=bin
            add file tmp/driver_classes path=etc/driver_classes mode=0644 owner=root group=bin
            add file tmp/minor_perm path=etc/minor_perm mode=0644 owner=root group=bin
            add file tmp/name_to_major path=etc/name_to_major mode=0644 owner=root group=bin
            add file tmp/device_policy path=etc/security/device_policy mode=0644 owner=root group=bin
            add file tmp/extra_privs path=etc/security/extra_privs mode=0644 owner=root group=bin
            close
        """

        driverdb_files = {
            "tmp/devlink.tab": "",
            "tmp/driver_aliases": "",
            "tmp/driver_classes": "",
            "tmp/minor_perm": "",
            "tmp/name_to_major": "",
            "tmp/device_policy": "",
            "tmp/extra_privs": ""
        }

        pkg_dupdrv = """
            open dupdriver@0,5.11-0
            add driver name=asy perms="* 0666 root sys" perms="*,cu 0600 uucp uucp"
            add driver name=asy perms="* 0666 root sys" alias=pci11c1,480
            close
        """

        pkg_dupdepend1 = """
            open dupdepend1@0,5.11-0
            add depend type=require fmri=dupfilesp1
            add depend type=require fmri=dupfilesp1
            close
        """

        pkg_dupdepend2 = """
            open dupdepend2@0,5.11-0
            add depend type=require fmri=dupfilesp1
            add depend type=incorporate fmri=dupfilesp1
            close
        """

        pkg_dupdepend3 = """
            open dupdepend3@0,5.11-0
            add depend type=require fmri=dupfilesp1@0-0
            add depend type=require fmri=dupfilesp1@0-0
            close
        """

        pkg_dupdepend4 = """
            open dupdepend4@0,5.11-0
            add depend type=require fmri=dupfilesp1@0-0
            add depend type=incorporate fmri=dupfilesp1@0-0
            close
        """

        pkg_tripledupfilea = """
            open tripledupfilea@0,5.11-0
            add set name=variant.foo value=one
            add file tmp/file1 path=file owner=root group=other mode=0755
            close
        """

        pkg_tripledupfileb = """
            open tripledupfileb@0,5.11-0
            add set name=variant.foo value=one value=two
            add file tmp/file2 path=file owner=root group=other mode=0755
            close
        """

        pkg_tripledupfilec = """
            open tripledupfilec@0,5.11-0
            add set name=variant.foo value=one value=two
            add file tmp/file3 path=file owner=root group=other mode=0755
            close
        """

        pkg_variantedtypes = """
            open vpath@0,5.11-0
            add set name=variant.foo value=one value=two
            add dir group=bin mode=0755 owner=root path=boot/platform \
                variant.foo=two
            add link path=boot/platform target=../platform variant.foo=one

            close
        """

        misc_files = ["tmp/file1", "tmp/file2", "tmp/file3", "tmp/file4",
            "tmp/unpreserved"]

        # Keep the depots around for the duration of the entire class
        persistent_setup = True

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.make_misc_files(self.userdb_files)
                self.make_misc_files(self.driverdb_files)

                pkgs = []
                for objname in dir(self.__class__):
                        obj = getattr(self, objname)
                        if objname.startswith("pkg_") and type(obj) == str:
                                pkgs.append(obj)

                for i in range(20):
                        s = """
                                open massivedupdir{0:d}@0,5.11-0
                                add dir path=usr owner=root group={{0}} mode={{1}} zig={{2}}
                                close
                        """.format(i)

                        if i == 14:
                                s = s.format("root", "0750", "zag")
                        elif i in (1, 9):
                                s = s.format("sys", "0750", "zag")
                        elif i in (3, 8, 12, 17):
                                s = s.format("root", "0755", "zag")
                        else:
                                s = s.format("sys", "0755", "zig")

                        pkgs.append(s)

                self.plist = self.pkgsend_bulk(self.rurl, pkgs)


        def test_conflictgroupid_install(self):
                """Test conflict group IDs will not cause user action failure.
                """

                self.image_create(self.rurl)

                self.pkg("install userdb")
                self.pkg("install conflictgroup1")
                with open(os.path.join(self.img_path(), "etc/group")) as f:
                        lines = f.readlines()
                for line in lines:
                        if "fozzie" in line:
                                self.assertTrue("200" in line)
                                break
                with open(os.path.join(self.img_path(), "etc/passwd")) as f:
                        lines = f.readlines()
                for line in lines:
                        if "fozzie" in line:
                                self.assertTrue("200" in line)
                                break
                self.pkg("install -v --reject conflictgroup1 conflictgroup2")

                self.pkg("list conflictgroup1", exit=1)
                self.pkg("list conflictgroup2")
                with open(os.path.join(self.img_path(), "etc/passwd")) as f:
                        lines = f.readlines()
                for line in lines:
                        if "fozzie" in line:
                                self.assertTrue("201" in line)
                                break
                with open(os.path.join(self.img_path(), "etc/group")) as f:
                        lines = f.readlines()
                for line in lines:
                        if "fozzie" in line:
                                self.assertTrue("201" in line)
                                break
                self.pkg("verify")

        def test_multiple_files_install(self):
                """Test the behavior of pkg(1) when multiple file actions
                deliver to the same pathname."""

                self.image_create(self.rurl)

                # Duplicate files in the same package
                self.pkg("install dupfiles", exit=1)

                # Duplicate files in different packages, but in the same
                # transaction
                self.pkg("install dupfilesp1 dupfilesp2@0", exit=1)

                # Duplicate files in different packages, in different
                # transactions
                self.pkg("install dupfilesp1")
                self.pkg("install dupfilesp2@0", exit=1)

                # Test that being in a duplicate file situation doesn't break
                # you completely and allows you to add and remove other packages
                self.pkg("-D broken-conflicting-action-handling=1 install dupfilesp2@0")
                self.pkg("install implicitdirs2")
                self.pkg("uninstall implicitdirs2")

                # If the packages involved get upgraded but leave the actions
                # themselves alone, we should be okay.
                self.pkg("install dupfilesp2 dupfilesp3")
                self.pkg("verify", exit=1)

                # Test that removing one of two offending actions reverts the
                # system to a clean state.
                self.pkg("uninstall dupfilesp3")
                self.pkg("verify")

                # You should be able to upgrade to a fixed set of packages in
                # order to move past the problem, too.
                self.pkg("uninstall dupfilesp2")
                self.pkg("-D broken-conflicting-action-handling=1 install dupfilesp2@0")
                self.pkg("update")
                self.pkg("verify")

                # If we upgrade to a version of a conflicting package that no
                # longer has the conflict, but at the same time introduce a new
                # file action at the path with different contents, we should
                # fail.
                self.pkg("uninstall dupfilesp2")
                self.pkg("-D broken-conflicting-action-handling=1 install dupfilesp2@0")
                self.pkg("install dupfilesp2 dupfilesp4", exit=1)

                # Removing one of more than two offending actions can't do much
                # of anything, but should leave the system alone.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfilesp1 dupfilesp2@0 dupfilesp3")
                # Verify should report a duplicate action error on dupfilesp1,
                # dupfilesp2 and dupfilesp3 and shouldn't report it was failing
                # due to hashes being wrong.
                self.pkg("verify", exit=1)
                out1, err1 = self.output, self.errout
                for i, l in enumerate(self.plist):
                    if l.startswith("pkg://test/dupfilesp1"):
                        index = i
                expected = "\n  {0}\n  {1}\n  {2}".format(
                    self.plist[index], self.plist[index + 1], self.plist[index + 3])
                self.assertTrue(expected in err1, err1)
                self.assertTrue("Hash" not in out1)
                self.pkg("uninstall dupfilesp3")
                # Removing dupfilesp3, verify should still report a duplicate
                # action error on dupfilesp1 and dupfilesp2.
                self.pkg("verify", exit=1)
                out2, err2 = self.output, self.errout
                expected = "\n  {0}\n  {1}".format(
                    self.plist[index], self.plist[index + 1])
                self.assertTrue(expected in err2)
                self.assertTrue("Hash" not in out2)

                # Removing all but one of the offending actions should get us
                # back to sanity.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfilesp1 dupfilesp2@0 dupfilesp3")
                self.pkg("uninstall dupfilesp3 dupfilesp2")
                self.pkg("verify")

                # Make sure we handle cleaning up multiple files properly.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfilesp1 dupfilesp2@0 dupotherfilesp1 dupotherfilesp2")
                self.pkg("uninstall dupfilesp2 dupotherfilesp2")
                self.pkg("verify")

                # Re-use the overlay packages for some preserve testing.
                self.pkg("install overlaid@0")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "invalid-overlayer")
                # We may have been able to lay down the package, but because the
                # file is marked preserve=true, we didn't actually overwrite
                self.file_contains("etc/pam.conf", "file2")
                self.pkg("uninstall invalid-overlayer")
                self.file_contains("etc/pam.conf", "file2")

                # Make sure we get rid of all implicit directories.
                self.pkg("uninstall '*'")
                self.pkg("install implicitdirs3 implicitdirs4")
                self.pkg("uninstall implicitdirs3 implicitdirs4")

                if os.path.isdir(os.path.join(self.get_img_path(), "usr/bin")):
                        self.assertTrue(False, "Directory 'usr/bin' should not exist")

                if os.path.isdir(os.path.join(self.get_img_path(), "usr")):
                        self.assertTrue(False, "Directory 'usr' should not exist")

                # Make sure identical actions don't cause problems
                self.pkg("install -nv identicalfiles", exit=1)

                # Trigger a bug similar to 17943 via duplicate files.
                self.pkg("publisher")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfilesp1@0 dupfilesp2@0 dupfilesp3@0 dupotherfilesp1@0 "
                    "dupotherfilesp2@0 dupotherfilesp3@0")
                self.pkg("update")

                # If an uninstall causes a fixup to happen and we can't because
                # we lost the cached files and the repo is down, make sure we
                # fail before actually uninstalling anything.
                self.dc.start()
                self.pkgsend_bulk(self.durl, (self.pkgremote_pkg1,
                    self.pkgremote_pkg2))
                self.image_create(self.durl)
                self.pkg("install pkg1")
                self.pkg("-D broken-conflicting-action-handling=1 install pkg2")
                self.pkg("verify pkg2")
                self.dc.stop()
                self.pkg("uninstall pkg2", exit=1)
                self.pkg("verify pkg2")

        def test_overlay_files_install(self):
                """Test the behaviour of pkg(1) when actions for editable files
                overlay other actions."""

                # Ensure that overlay is allowed for file actions when one
                # action has specified preserve attribute and overlay=allow,
                # and *one* (only) other action has specified overlay=true
                # (preserve does not have to be set).
                self.image_create(self.rurl)

                # Ensure boring package is installed as conflict checking is
                # bypassed (and thus, overlay semantics) if all packages are
                # removed from an image.
                self.pkg("install boring")

                # Should fail because one action specified overlay=allow,
                # but not preserve (it isn't editable).
                self.pkg("install invalid-overlaid")
                self.pkg("install overlayer", exit=1)
                self.pkg("uninstall invalid-overlaid")

                # Should fail because one action is overlayable but overlaying
                # action doesn't declare its intent to overlay.
                self.pkg("install overlaid@0")
                self.file_contains("etc/pam.conf", "file1")
                self.pkg("install invalid-overlayer", exit=1)

                # Should fail because one action is overlayable but overlaying
                # action mode, owner, and group attributes don't match.
                self.pkg("install mismatch-overlayer", exit=1)

                # Should succeed because one action is overlayable and
                # overlaying action declares its intent to overlay.
                self.pkg("contents -m overlaid")
                self.pkg("contents -mr overlayer")
                self.pkg("install --parsable=0 overlayer")
                self._assertEditables(
                    installed=["etc/pam.conf"],
                )
                self.file_contains("etc/pam.conf", "file2")

                # Should fail because multiple actions are not allowed to
                # overlay a single action.
                self.pkg("install multi-overlayer", exit=1)

                # Should succeed even though file is different than originally
                # delivered since original package permits file modification.
                self.pkg("verify overlaid overlayer")

                # Should succeed because package delivering overlayable file
                # permits modification and because package delivering overlay
                # file permits modification.
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("verify overlaid overlayer")

                # Verify that the file isn't touched on uninstall of the
                # overlaying package if package being overlaid is still
                # installed.
                self.pkg("uninstall --parsable=0 overlayer")
                self._assertEditables()
                self.file_contains("etc/pam.conf", ["zigit", "file2"])

                # Verify that removing the last package delivering an overlaid
                # file removes the file.
                self.pkg("uninstall --parsable=0 overlaid")
                self._assertEditables(
                    removed=["etc/pam.conf"],
                )
                self.file_doesnt_exist("etc/pam.conf")

                # Verify that installing both packages at the same time results
                # in only the overlaying file being delivered.
                self.pkg("install --parsable=0 overlaid@0 overlayer")
                self._assertEditables(
                    installed=["etc/pam.conf"],
                )
                self.file_contains("etc/pam.conf", "file2")

                # Verify that the file isn't touched on uninstall of the
                # overlaid package if overlaying package is still installed.
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("uninstall --parsable=0 overlaid")
                self._assertEditables()
                self.file_contains("etc/pam.conf", ["file2", "zigit"])

                # Re-install overlaid package and verify that file content
                # does not change.
                self.pkg("install --parsable=0 overlaid@0")
                self._assertEditables()
                self.file_contains("etc/pam.conf", ["file2", "zigit"])
                self.pkg("uninstall --parsable=0 overlaid overlayer")
                self._assertEditables(
                    removed=["etc/pam.conf"],
                )

                # Should succeed because one action is overlayable and
                # overlaying action declares its intent to overlay even
                # though the overlaying action isn't marked with preserve.
                self.pkg("install -nvv overlaid@0 unpreserved-overlayer")
                self.pkg("install --parsable=0 overlaid@0 unpreserved-overlayer")
                self._assertEditables(
                    installed=["etc/pam.conf"],
                )
                self.file_contains("etc/pam.conf", "unpreserved")

                # Should succeed because overlaid action permits modification
                # and contents matches overlaying action.
                self.pkg("verify overlaid unpreserved-overlayer")

                # Should succeed even though file has been modified since
                # overlaid action permits modification.
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("verify overlaid")

                # Should fail because overlaying action does not permit
                # modification.
                self.pkg("verify unpreserved-overlayer", exit=1)

                # Should revert to content delivered by overlaying action.
                self.pkg("fix unpreserved-overlayer")
                self.file_contains("etc/pam.conf", "unpreserved")
                self.file_doesnt_contain("etc/pam.conf", "zigit")

                # Should revert to content delivered by overlaying action.
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("revert /etc/pam.conf")
                self.file_contains("etc/pam.conf", "unpreserved")
                self.file_doesnt_contain("etc/pam.conf", "zigit")
                self.pkg("uninstall --parsable=0 unpreserved-overlayer")
                self._assertEditables()

                # Should revert to content delivered by overlaid action.
                self.file_contains("etc/pam.conf", "unpreserved")
                self.pkg("revert /etc/pam.conf")
                self.file_contains("etc/pam.conf", "file1")

                # Install overlaying package, then update overlaid package and
                # verify that file content does not change if only preserve
                # attribute changes.
                self.pkg("install --parsable=0 unpreserved-overlayer")
                self._assertEditables(
                    installed=["etc/pam.conf"],
                )
                self.file_contains("etc/pam.conf", "unpreserved")
                self.pkg("install --parsable=0 overlaid@1")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "unpreserved")
                self.pkg("uninstall --parsable=0 overlaid")
                self._assertEditables()

                # Now update overlaid package again, and verify that file
                # content does not change even though overlaid content has.
                self.pkg("install --parsable=0 overlaid@2")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "unpreserved")

                # Now update overlaid package again this time as part of a
                # rename, and verify that file content does not change even
                # though file has moved between packages.
                self.pkg("install --parsable=0 overlaid@3")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "unpreserved")

                # Verify that unpreserved overlay is not salvaged when both
                # overlaid and overlaying package are removed at the same time.
                # (Preserved files are salvaged if they have been modified on
                # uninstall.)

                # Ensure directory is empty before testing.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                sroot = os.path.join(img_inst.imgdir, "lost+found")
                shutil.rmtree(sroot)

                # Verify etc directory not found after uninstall.
                self.pkg("uninstall --parsable=0 overlaid-renamed "
                    "unpreserved-overlayer")
                self._assertEditables(
                    removed=['etc/pam.conf'],
                )
                salvaged = [
                    n for n in os.listdir(sroot)
                    if n.startswith("etc")
                ]
                self.assertEqualDiff(salvaged, [])

                # Next, update overlaid package again this time as part of a
                # file move.  Verify that the configuration file exists at both
                # the new location and the old location, that the content has
                # not changed in either, and that the new configuration exists
                # as expected as ".new".
                self.pkg("install --parsable=0 overlaid-renamed@3 "
                    "unpreserved-overlayer")
                self._assertEditables(
                    installed=['etc/pam.conf'],
                )
                self.pkg("install -nvv overlaid-renamed@4.1")
                self.pkg("install --parsable=0 overlaid-renamed@4.1")
                self._assertEditables(
                    moved=[['etc/pam.conf', 'etc/pam/pam.conf']],
                    installed=['etc/pam/pam.conf.new'],
                )
                self.file_contains("etc/pam.conf", "unpreserved")
                self.file_contains("etc/pam/pam.conf", "unpreserved")
                self.file_contains("etc/pam/pam.conf.new", "file4")

                # Verify etc/pam.conf not salvaged after uninstall as overlay
                # file has not been changed.
                self.pkg("uninstall --parsable=0 overlaid-renamed "
                    "unpreserved-overlayer")
                self._assertEditables(
                    removed=['etc/pam.conf', 'etc/pam/pam.conf'],
                )
                salvaged = [
                    n for n in os.listdir(os.path.join(sroot, "etc"))
                    if n.startswith("pam.conf")
                ]
                self.assertEqualDiff(salvaged, [])

                # Next, repeat the same set of tests performed above for renames
                # and moves with an overlaying, preserved file.
                #
                # Install overlaying package, then update overlaid package and
                # verify that file content does not change if only preserve
                # attribute changes.
                self.pkg("install --parsable=0 overlayer")
                self._assertEditables(
                    installed=['etc/pam.conf'],
                )
                self.file_contains("etc/pam.conf", "file2")
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("install --parsable=0 overlaid@1")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "zigit")
                self.pkg("uninstall --parsable=0 overlaid")
                self._assertEditables()

                # Now update overlaid package again, and verify that file
                # content does not change even though overlaid content has.
                self.pkg("install --parsable=0 overlaid@2")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "zigit")

                # Now update overlaid package again this time as part of a
                # rename, and verify that file content does not change even
                # though file has moved between packages.
                self.pkg("install --parsable=0 overlaid@3")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "zigit")

                # Verify that preserved overlay is salvaged when both overlaid
                # and overlaying package are removed at the same time.
                # (Preserved files are salvaged if they have been modified on
                # uninstall.)

                # Ensure directory is empty before testing.
                api_inst = self.get_img_api_obj()
                img_inst = api_inst.img
                sroot = os.path.join(img_inst.imgdir, "lost+found")
                shutil.rmtree(sroot)

                # Verify etc directory found after uninstall.
                self.pkg("uninstall --parsable=0 overlaid-renamed overlayer")
                self._assertEditables(
                    removed=['etc/pam.conf'],
                )
                salvaged = [
                    n for n in os.listdir(sroot)
                    if n.startswith("etc")
                ]
                self.assertEqualDiff(salvaged, ["etc"])

                # Next, update overlaid package again, this time as part of a
                # file move where the overlay attribute was dropped.  Verify
                # that the configuration file exists at both the new location
                # and the old location, that the content has not changed in
                # either, and that the new configuration exists as expected as
                # ".new".
                self.pkg("install --parsable=0 overlaid-renamed@3 overlayer")
                self._assertEditables(
                    installed=['etc/pam.conf'],
                )
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("install --parsable=0 overlaid-renamed@4.0")
                self._assertEditables(
                    moved=[['etc/pam.conf', 'etc/pam/pam.conf']],
                    installed=['etc/pam/pam.conf.new'],
                )
                self.file_contains("etc/pam.conf", "zigit")
                self.file_contains("etc/pam/pam.conf", "zigit")
                self.file_contains("etc/pam/pam.conf.new", "file4")
                self.pkg("uninstall --parsable=0 overlaid-renamed overlayer")
                self._assertEditables(
                    removed=['etc/pam.conf', 'etc/pam/pam.conf'],
                )

                # Next, update overlaid package again, this time as part of a
                # file move.  Verify that the configuration file exists at both
                # the new location and the old location, that the content has
                # not changed in either, and that the new configuration exists
                # as expected as ".new".
                self.pkg("install --parsable=0 overlaid-renamed@3 overlayer")
                self._assertEditables(
                    installed=['etc/pam.conf'],
                )
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("install --parsable=0 overlaid-renamed@4.1")
                self._assertEditables(
                    moved=[['etc/pam.conf', 'etc/pam/pam.conf']],
                    installed=['etc/pam/pam.conf.new'],
                )
                self.file_contains("etc/pam.conf", "zigit")
                self.file_contains("etc/pam/pam.conf", "zigit")
                self.file_contains("etc/pam/pam.conf.new", "file4")

                # Next, downgrade the package and verify that if an overlaid
                # file moves back to its original location, the content of the
                # overlay file will not change.
                self.pkg("update --parsable=0 overlaid-renamed@3")
                self._assertEditables(
                    removed=['etc/pam/pam.conf'],
                )
                self.file_contains("etc/pam.conf", "zigit")

                # Now upgrade again for remaining tests.
                self.pkg("install --parsable=0 overlaid-renamed@4.1")
                self._assertEditables(
                    moved=[['etc/pam.conf', 'etc/pam/pam.conf']],
                    installed=['etc/pam/pam.conf.new'],
                )

                # Verify etc/pam.conf and etc/pam/pam.conf salvaged after
                # uninstall as overlay file and overlaid file is different from
                # packaged.
                shutil.rmtree(sroot)
                self.pkg("uninstall --parsable=0 overlaid-renamed overlayer")
                self._assertEditables(
                    removed=['etc/pam.conf', 'etc/pam/pam.conf'],
                )
                salvaged = sorted(
                    n for n in os.listdir(os.path.join(sroot, "etc"))
                    if n.startswith("pam")
                )
                # Should have three entries; one should be 'pam' directory
                # (presumably containing pam.conf-X...), another a file starting
                # with 'pam.conf', and finally a 'pam-XXX' directory containing
                # the 'pam.conf.new-XXX'.
                self.assertEqualDiff(salvaged[0], "pam")
                self.assertTrue(salvaged[1].startswith("pam-"),
                    msg=str(salvaged))
                self.assertTrue(salvaged[2].startswith("pam.conf"),
                    msg=str(salvaged))

                # Next, install overlaid package and overlaying package, then
                # upgrade each to a version where the file has changed
                # locations and verify that the content remains intact.
                self.pkg("install --parsable=0 overlaid@0 overlayer-move@0")
                self._assertEditables(
                    installed=['etc/pam.conf'],
                )
                self.file_append("etc/pam.conf", "zigit")
                self.pkg("install --parsable=0 overlaid@3")
                self._assertEditables()
                self.file_contains("etc/pam.conf", "zigit")
                self.pkg("install --parsable=0 overlaid-renamed@4.1 "
                    "overlayer-move@1")
                self._assertEditables(
                    moved=[['etc/pam.conf', 'etc/pam/pam.conf']],
                )
                self.file_contains("etc/pam/pam.conf", "zigit")

                # Next, downgrade overlaid-renamed and overlaying package to
                # versions where the file is restored to its original location
                # and verify that the content is reverted to the original
                # overlay version since this is a downgrade.
                self.pkg("update --parsable=0 overlaid-renamed@3 "
                    "overlayer-move@0")
                self._assertEditables(
                    removed=['etc/pam/pam.conf'],
                    installed=['etc/pam.conf'],
                )
                self.file_contains("etc/pam.conf", "file2")
                self.pkg("uninstall --parsable=0 overlaid-renamed overlayer-move")
                self._assertEditables(
                    removed=['etc/pam.conf'],
                )

                # Next, install overlaid package and overlaying package and
                # verify preserve acts as expected for overlay package as it is
                # updated.
                self.pkg("install --parsable=0 overlaid@2 overlayer-update@0")
                self._assertEditables(
                    installed=['etc/pam.conf'],
                )
                self.file_contains("etc/pam.conf", "file1")
                # unpreserved -> preserved
                self.pkg("install --parsable=0 overlayer-update@1")
                self._assertEditables(
                    updated=['etc/pam.conf'],
                )
                self.file_contains("etc/pam.conf", "file2")
                self.file_append("etc/pam.conf", "zigit")
                # preserved -> renameold
                self.pkg("install --parsable=0 overlayer-update@2")
                self._assertEditables(
                    moved=[['etc/pam.conf', 'etc/pam.conf.old']],
                    installed=['etc/pam.conf'],
                )
                self.file_doesnt_contain("etc/pam.conf", "zigit")
                self.file_contains("etc/pam.conf.old", "zigit")
                self.file_append("etc/pam.conf", "zagat")
                # renameold -> renamenew
                self.pkg("install --parsable=0 overlayer-update@3")
                self._assertEditables(
                    installed=['etc/pam.conf.new'],
                )
                self.file_contains("etc/pam.conf", "zagat")
                self.file_contains("etc/pam.conf.new", "file4")

        def test_different_types_install(self):
                """Test the behavior of pkg(1) when multiple actions of
                different types deliver to the same pathname."""

                self.image_create(self.rurl)

                # In the same package
                self.pkg("install duppath-filelink", exit=1)

                # In different packages, in the same transaction
                self.pkg("install dupfilesp1 duplink", exit=1)

                # In different packages, in different transactions
                self.pkg("install dupfilesp1")
                self.pkg("install duplink", exit=1)

                # Does removal of one of the busted packages get us out of the
                # situation?
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install dupfilesp1 duplink")
                self.pkg("verify", exit=1)
                self.pkg("uninstall dupfilesp1")
                self.pkg("verify")
                self.pkg("-D broken-conflicting-action-handling=1 install dupfilesp1")
                self.pkg("uninstall duplink")
                self.pkg("verify")

                # Implicit directory conflicts with a file
                self.pkg("uninstall '*'")
                self.pkg("install implicitdirs", exit=1)

                # Implicit directory coincides with a delivered directory
                self.pkg("install implicitdirs2")

                # Make sure that we don't die trying to fixup a directory using
                # an implicit directory action.
                self.pkg("uninstall '*'")
                self.pkg("install implicitdirs4")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "implicitdirs7")
                self.pkg("uninstall implicitdirs7")
                # XXX We don't currently fix up anything beneath a directory
                # that was restored, so we have to do it by hand.
                os.mkdir("{0}/usr/bin".format(self.img_path()))
                shutil.copy("{0}/tmp/file1".format(self.test_root),
                    "{0}/usr/bin/something".format(self.img_path()))
                owner = portable.get_user_by_name("root", self.img_path(), True)
                group = portable.get_group_by_name("bin", self.img_path(), True)
                os.chown("{0}/usr/bin/something".format(self.img_path()), owner, group)
                os.chmod("{0}/usr/bin/something".format(self.img_path()), 0o755)
                self.pkg("verify")

                # Removing one of more than two offending actions can't do much
                # of anything, but should leave the system alone.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfilesp1 duplink dupdir@0")
                tmap = {
                    stat.S_IFIFO: "fifo",
                    stat.S_IFCHR: "character device",
                    stat.S_IFDIR: "directory",
                    stat.S_IFBLK: "block device",
                    stat.S_IFREG: "regular file",
                    stat.S_IFLNK: "symbolic link",
                    stat.S_IFSOCK: "socket",
                }
                thepath = "{0}/dir/pathname".format(self.img_path())
                fmt = stat.S_IFMT(os.lstat(thepath).st_mode)
                # XXX The checks here rely on verify failing due to action types
                # not matching what's on the system; they should probably report
                # duplicate actions instead.  Checking the output text is a bit
                # ugly, too, but we do need to make sure that the two problems
                # become one.
                self.pkg("verify", exit=1)
                verify_type_re = "File Type: '(.*?)' should be '(.*?)'"
                matches = re.findall(verify_type_re, self.output)
                # We make sure that what got reported is correct -- two actions
                # of different types in conflict with whatever actually got laid
                # down.
                self.assertTrue(len(matches) == 2)
                whatis = matches[0][0]
                self.assertTrue(matches[1][0] == whatis)
                self.assertTrue(whatis == tmap[fmt])
                shouldbe = set(["symbolic link", "regular file", "directory"]) - \
                    set([whatis])
                self.assertTrue(set([matches[0][1], matches[1][1]]) == shouldbe)
                # Now we uninstall one of the packages delivering a type which
                # isn't what's on the filesystem.  The filesystem should remain
                # unchanged, but one of the errors should go away.
                if whatis == "directory":
                        self.pkg("uninstall duplink")
                else:
                        self.pkg("uninstall dupdir")
                self.pkg("verify", exit=1)
                matches = re.findall(verify_type_re, self.output)
                self.assertTrue(len(matches) == 1)
                nfmt = stat.S_IFMT(os.lstat(thepath).st_mode)
                self.assertTrue(nfmt == fmt)

                # Now we do the same thing, but we uninstall the package
                # delivering the type which *is* what's on the filesystem.  This
                # should also leave the filesystem alone, even though what's
                # there will match *neither* of the remaining installed
                # packages.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupfilesp1 duplink dupdir@0")
                fmt = stat.S_IFMT(os.lstat(thepath).st_mode)
                self.pkg("verify", exit=1)
                matches = re.findall(verify_type_re, self.output)
                self.assertTrue(len(matches) == 2)
                whatis = matches[0][0]
                self.assertTrue(matches[1][0] == whatis)
                self.assertTrue(whatis == tmap[fmt])
                shouldbe = set(["symbolic link", "regular file", "directory"]) - \
                    set([whatis])
                self.assertTrue(set([matches[0][1], matches[1][1]]) == shouldbe)
                if whatis == "directory":
                        self.pkg("uninstall dupdir")
                elif whatis == "symbolic link":
                        self.pkg("uninstall duplink")
                elif whatis == "regular file":
                        self.pkg("uninstall dupfilesp1")
                self.pkg("verify", exit=1)
                matches = re.findall(verify_type_re, self.output)
                self.assertTrue(len(matches) == 2)
                nfmt = stat.S_IFMT(os.lstat(thepath).st_mode)
                self.assertTrue(nfmt == fmt)

                # Go from multiple conflicting types down to just one type.
                # This also tests the case where a package version being newly
                # installed gets fixed at the same time.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupmultitypes@1")
                self.pkg("install dupmultitypes")
                self.pkg("verify")

                # Upgrading from multiple instances of one refcounted type to
                # multiple instances of another (here, link to directory) should
                # succeed.
                self.pkg("uninstall '*'")
                self.pkg("install dupmultitypes3@0")
                self.pkg("update")

        def test_conflicting_attrs_fs_install(self):
                """Test the behavior of pkg(1) when multiple non-file actions of
                the same type deliver to the same pathname, but whose other
                attributes differ."""

                self.image_create(self.rurl)

                # One package, two links with different targets
                self.pkg("install duppath-nonidenticallinks", exit=1)

                # One package, two directories with different perms
                self.pkg("install duppath-nonidenticaldirs", exit=1)

                # One package, two dirs with same modes expressed two ways
                self.pkg("install duppath-almostidenticaldirs")

                # One package delivers a directory explicitly, another
                # implicitly.
                self.pkg("install implicitdirs2 implicitdirs3")
                self.pkg("verify")

                self.pkg("uninstall '*'")

                # Make sure that we don't die trying to fixup a directory using
                # an implicit directory action.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "implicitdirs4 implicitdirs5 implicitdirs6")
                self.pkg("uninstall implicitdirs5")
                self.pkg("verify")

                self.pkg("uninstall '*'")

                # Make sure that we don't die trying to fixup a directory using
                # an implicit directory action when that's all that's left.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "implicitdirs4 implicitdirs5 implicitdirs6")
                self.pkg("uninstall implicitdirs5 implicitdirs6")
                self.pkg("verify")

                self.pkg("uninstall '*'")

                # If two packages deliver conflicting directories and another
                # package delivers that directory implicitly, make sure the
                # third package isn't blamed.
                self.pkg("install implicitdirs4 implicitdirs5 implicitdirs6",
                    exit=1)
                self.assertTrue("implicitdirs4" not in self.errout)

                # Two packages, two links with different targets, installed at
                # once
                self.pkg("install duppath-nonidenticallinksp1 "
                    "duppath-nonidenticallinksp2@0", exit=1)

                # Two packages, two links with different targets, installed
                # separately
                self.pkg("install duppath-nonidenticallinksp1")
                self.pkg("install duppath-nonidenticallinksp2@0", exit=1)

                self.pkg("uninstall '*'")

                # If we get into a broken state, can we get out of it?
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "duppath-nonidenticallinksp1 duppath-nonidenticallinksp2@0")
                self.pkg("verify", exit=1)
                self.pkg("install duppath-nonidenticallinksp2")
                self.pkg("verify")

                # If we get into a broken state, can we make it a little bit
                # better by uninstalling one of the packages?  Removing dupdir5
                # here won't reduce the number of different groups under which
                # dir is delivered, but does reduce the number of actions
                # delivering it.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp1 dupdirp2@1 dupdirp5 dupdirp6")
                self.pkg("uninstall dupdirp5")
                self.pkg("verify", exit=1)

                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp5")
                # Make sure we can install a package delivering an implicit
                # directory that's currently in conflict.
                self.pkg("install dupdirp7")
                # And make sure we can uninstall it again.
                self.pkg("uninstall dupdirp7")

                # Removing the remaining conflicts in a couple of steps should
                # result in a verifiable system.
                self.pkg("uninstall dupdirp2")
                self.pkg("uninstall dupdirp5 dupdirp6")
                self.pkg("verify")

                # Add everything back in, remove everything but one variant of
                # the directory and an implicit directory, and verify.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp2@1 dupdirp5 dupdirp6 dupdirp7")
                self.pkg("uninstall dupdirp2 dupdirp5 dupdirp6")
                self.pkg("verify")

                # Get us into a saner state by upgrading.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp2@1 dupdirp5 dupdirp6")
                self.pkg("update dupdirp2@2")

                # Get us into a sane state by upgrading.
                self.pkg("uninstall dupdirp2 dupdirp5 dupdirp6")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp2@1")
                self.pkg("update dupdirp2@2")
                self.pkg("verify")

                # We start in a sane state, but the update would result in
                # conflict, though no more actions deliver the path in
                # question.
                self.pkg("uninstall '*'")
                self.pkg("install dupdirp1 dupdirp8@1")
                self.pkg("update", exit=1)

                # How about removing one of the conflicting packages?  We'll
                # remove the package which doesn't match the state on disk.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "duppath-nonidenticallinksp1 duppath-nonidenticallinksp2@0")
                link = os.readlink("{0}/dir/pathname".format(self.img_path()))
                if link == "dir/something":
                        self.pkg("uninstall duppath-nonidenticallinksp2")
                else:
                        self.pkg("uninstall duppath-nonidenticallinksp1")
                self.pkg("verify")

                # Now we'll try removing the package which *does* match the
                # state on disk.  The code should clean up after us.
                self.pkg("uninstall '*'")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "duppath-nonidenticallinksp1 duppath-nonidenticallinksp2@0")
                link = os.readlink("{0}/dir/pathname".format(self.img_path()))
                if link == "dir/something":
                        self.pkg("uninstall duppath-nonidenticallinksp1")
                else:
                        self.pkg("uninstall duppath-nonidenticallinksp2")
                self.pkg("verify")

                # Let's try a duplicate directory delivered with all sorts of
                # crazy conflicts!
                self.pkg("uninstall '*'")
                self.pkg("install dupdirp1 dupdirp2@1 dupdirp3 dupdirp4", exit=1)

                pkgs = " ".join("massivedupdir{0:d}".format(x) for x in range(20))
                self.pkg("install {0}".format(pkgs), exit=1)

                # Trigger bug 17943: we install packages with conflicts in two
                # directories (p9, p10).  We also install a package (p11) which
                # delivers those directories implicitly.  Then remove the last,
                # triggering the stack trace associated with the bug.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp9 dupdirp10 dupdirp11")
                self.pkg("uninstall dupdirp11")

                # Do the same, but with a package that delivers var implicitly
                # via a legacy action.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupdirp12")
                self.pkg("uninstall dupdirp12")

        def test_conflicting_attrs_fs_varcets(self):
                """Test the behavior of pkg(1) when multiple non-file actions of
                the same type deliver to the same pathname, but differ in their
                variants or facets."""

                install_cmd = "install"
                self.image_create(self.rurl)

                # Two packages delivering the same directory, one under the
                # current architecture, the other not tagged with an arch
                # variant.
                self.pkg("{0} dupfilesv1 dupfilesv2".format(install_cmd))
                self.dir_exists("dir/pathname")

                # Two packages delivering the same directory with different
                # attributes -- one under the current architecture, the other
                # tagged with another arch variant.
                self.pkg("uninstall '*'")
                self.pkg("{0} dupfilesv1 dupfilesv3".format(install_cmd))
                if platform.processor() == "sparc":
                        self.dir_exists("dir/pathname", mode=0o777)
                else:
                        self.dir_exists("dir/pathname", mode=0o755)

                # Two packages delivering a file at the same path where one is
                # tagged only for non-global zones should install successfully
                # together in a global zone.
                self.pkg("uninstall '*'")
                self.pkg("{0} dupfilesv5 dupfilesv6".format(install_cmd))
                path = os.path.join(self.get_img_path(), "dir/pathname")
                try:
                        f = open(path)
                except OSError as e:
                        if e.errno == errno.ENOENT:
                                self.assertTrue(False, "File dir/pathname does not exist")
                        else:
                                raise
                self.assertEqual(f.read().rstrip(), "tmp/file2")
                f.close()

                # Two packages delivering the same directory, one with the
                # devel facet false, the other true.
                self.pkg("uninstall '*'")
                self.pkg("{0} dupfilesf1 dupfilesf2".format(install_cmd))
                self.dir_exists("dir/pathname")

                # Two packages delivering the same directory, one with the
                # devel facet true, the other without.
                self.pkg("uninstall '*'")
                self.pkg("{0} dupfilesf1 dupfilesf3".format(install_cmd))
                self.dir_exists("dir/pathname")

                # Two packages delivering the same directory, one with the
                # devel facet false, the other without.
                self.pkg("uninstall '*'")
                self.pkg("{0} dupfilesf2 dupfilesf3".format(install_cmd))
                self.dir_exists("dir/pathname")

        def test_conflicting_uninstall_publisher(self):
                """Test the behaviour of pkg(1) when attempting to remove
                conflicting packages from a publisher which has also been
                removed."""

                self.conflicting_uninstall_publisher_helper("install")
                self.conflicting_uninstall_publisher_helper("exact-install")

        def conflicting_uninstall_publisher_helper(self, install_cmd):
                self.image_create(self.rurl)
                # Dummy publisher so test publisher can be removed.
                self.pkg("set-publisher -P ignored")

                # If packages with conflicting actions are found during
                # uninstall, and the publisher of the package has been
                # removed, uninstall should still succeed.
                self.pkg("-D broken-conflicting-action-handling=1 {0} "
                    "dupdirp1 dupdirp2@1".format(install_cmd))
                self.pkg("unset-publisher test")
                self.pkg("uninstall dupdirp2")
                self.pkg("verify")

        def test_change_varcet(self):
                """Test the behavior of pkg(1) when changing a variant or a
                facet would cause the new image to contain conflicting
                actions."""

                # Create the image as an x86 image, as the first test only works
                # changing variant from x86 to sparc.
                self.image_create(self.rurl, variants={"variant.arch": "i386"})

                # The x86 variant is safe, but the sparc variant has two files
                # with the same pathname.
                self.pkg("install dupfilesv4")
                self.pkg("change-variant arch=sparc", exit=1)

                # With the devel facet turned off, the package is safe, but
                # turning it on would cause a duplicate file to be added.
                self.pkg("change-facet devel=false")
                self.pkg("install dupfilesf4")
                self.pkg("change-facet devel=true", exit=1)

        def test_change_variant_removes_package(self):
                """Test that a change-variant that removes a package and
                improves but doesn't fix a conflicting action situation is
                allowed."""

                self.image_create(self.rurl, variants={"variant.foo": "one"})
                self.pkg("install tripledupfileb")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "tripledupfilec")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "tripledupfilea")
                self.pkg("change-variant -vvv variant.foo=two")
                self.pkg("change-variant -vvv variant.foo=one", exit=1)

        def test_multiple_users_install(self):
                """Test the behavior of pkg(1) when multiple user actions
                deliver the same user."""

                # This is largely identical to test_multiple_files; we may want
                # to commonize in the future.

                self.image_create(self.rurl)

                self.pkg("install userdb")

                # Duplicate users in the same package
                self.pkg("install dupuser", exit=1)

                # Duplicate users in different packages, but in the same
                # transaction
                self.pkg("install dupuserp1 dupuserp2@0", exit=1)

                # Duplicate users in different packages, in different
                # transactions
                self.pkg("install dupuserp1")
                self.pkg("install dupuserp2@0", exit=1)

                # Test that being in a duplicate user situation doesn't break
                # you completely and allows you to add and remove other packages
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupuserp2@0")
                self.pkg("verify", exit=1)
                self.pkg("install otheruser")
                self.file_contains("etc/passwd", "fozzie")
                self.file_contains("etc/shadow", "fozzie")
                self.pkg("uninstall otheruser")
                self.file_doesnt_contain("etc/passwd", "fozzie")
                self.file_doesnt_contain("etc/shadow", "fozzie")
                self.pkg("verify", exit=1)

                # If the packages involved get upgraded but leave the actions
                # themselves alone, we should be okay.
                self.pkg("install dupuserp2 dupuserp3")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("verify", exit=1)

                # Test that removing one of two offending actions reverts the
                # system to a clean state.
                self.pkg("uninstall dupuserp3")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("verify")

                # You should be able to upgrade to a fixed set of packages in
                # order to move past the problem, too.
                self.pkg("uninstall dupuserp2")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupuserp2@0")
                self.pkg("update")
                self.pkg("verify")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")

                # If we upgrade to a version of a conflicting package that no
                # longer has the conflict, but at the same time introduce a new
                # conflicting user action, we should fail.
                self.pkg("uninstall dupuserp2")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupuserp2@0")
                self.pkg("install dupuserp2 dupuserp4", exit=1)

                # Removing one of more than two offending actions can't do much
                # of anything, but should leave the system alone.
                self.image_destroy()
                self.image_create(self.rurl)
                self.pkg("install userdb")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupuserp1 dupuserp2@0 dupuserp3")
                self.pkg("verify", exit=1)
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                out1 = self.output
                self.pkg("uninstall dupuserp3")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("verify", exit=1)
                out2 = self.output
                out2 = out2[out2.index("STATUS\n") + 7:]
                self.assertTrue(out2 in out1)

                # Removing all but one of the offending actions should get us
                # back to sanity.
                self.image_destroy()
                self.image_create(self.rurl)
                self.pkg("install userdb")
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "dupuserp1 dupuserp2@0 dupuserp3")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("uninstall dupuserp3 dupuserp2")
                self.file_contains("etc/passwd", "kermit")
                self.file_contains("etc/shadow", "kermit")
                self.pkg("verify")

                # Make sure we don't get confused when two actions in different
                # namespace groups but with the same key attribute value are
                # adjacent in the action cache.
                self.pkg("-D broken-conflicting-action-handling=1 install "
                    "otheruser othergroup@0")
                self.pkg("update othergroup")

        def test_multiple_drivers(self):
                """Test the behavior of pkg(1) when multiple driver actions
                deliver the same driver."""

                self.multiple_drivers_helper("install")
                self.multiple_drivers_helper("exact-install")

        def multiple_drivers_helper(self, install_cmd):
                self.image_create(self.rurl)

                self.pkg("{0} driverdb".format(install_cmd))

                self.pkg("{0} dupdriver".format(install_cmd), exit=1)

        def test_multiple_depend(self):
                """Test to make sure we can have multiple depend actions on
                (more or less) the same fmri"""

                self.multiple_depend_helper("install")
                self.multiple_depend_helper("exact-install")

        def multiple_depend_helper(self, install_cmd):
                self.image_create(self.rurl)

                # Two identical unversioned require dependencies
                self.pkg("{0} dupdepend1".format(install_cmd))

                # Two dependencies of different types on an identical
                # unversioned fmri
                self.pkg("{0} dupdepend2".format(install_cmd))

                # Two identical versioned require dependencies
                self.pkg("{0} dupdepend3".format(install_cmd))

                # Two dependencies of different types on an identical versioned
                # fmri
                self.pkg("{0} dupdepend4".format(install_cmd))

        def test_varianted_types(self):
                """Test that actions which would otherwise conflict but are
                delivered under different variants don't conflict."""

                self.varianted_types_helper("install")
                self.varianted_types_helper("exact-install")

        def varianted_types_helper(self, install_cmd):
                self.pkg_image_create(repourl=self.rurl,
                    additional_args="--variant foo=one")
                self.pkg("{0} vpath".format(install_cmd))


class TestPkgInstallExplicitInstall(pkg5unittest.SingleDepotTestCase):
        """Test pkg.depend.explicit-install action behaviors."""
        persistent_setup = True

        pkgs = (
                """
                    open group@1.0,5.11-0
                    add depend type=group fmri=pkg:/A
                    close """,
                """
                    open incorp@1.0,5.11-0
                    add depend type=incorporate fmri=pkg:/A@1.0,5.11-0.1
                    close """,
                """
                    open A@1.0,5.11-0.1
                    close """,
                """
                    open A@1.0,5.11-0.1.1.0
                    add depend type=require fmri=pkg:/idr@1.0,5.11-0.1.1.0
                    close """,
                """
                    open idr@1.0,5.11-0.1.1.0
                    add set name=pkg.depend.explicit-install value=true
                    add depend type=incorporate fmri=pkg:/A@1.0,5.11-0.1.1.0
                    close """,
        )

        pkgs2 = (
                 """
                    open A@1.0,5.11-0.1.1.1
                    add depend type=require fmri=pkg:/idr@1.0,5.11-0.1.1.1
                    close """,
                """
                    open idr@1.0,5.11-0.1.1.1
                    add set name=pkg.depend.explicit-install value=false
                    add depend type=incorporate fmri=pkg:/A@1.0,5.11-0.1.1.1
                    close """,
        )

        pkgs3 = (
                """
                    open A@1.0,5.11-0.1.1.2
                    add depend type=require fmri=pkg:/idr@1.0,5.11-0.1.1.2
                    close """,
                """
                    open idr@1.0,5.11-0.1.1.2
                    add depend type=incorporate fmri=pkg:/A@1.0,5.11-0.1.1.2
                    close """,
        )

        pkgs4 = (
                """
                    open C1@1.0
                    add depend type=require-any fmri=pkg:/C2@1.0 fmri=pkg:/C2@2.0
                    close """,
                """
                    open C2@1.0
                    add depend type=require fmri=pkg:/C3@1.0,5.11-0.1
                    close """,
                """
                    open C2@2.0
                    add set name=pkg.depend.explicit-install value=true
                    add depend type=require fmri=pkg:/C3@1.0,5.11-0.1
                    close """,
                """
                    open C3@1.0,5.11-0.1
                    close """,
        )

        pkgs5 = (
                """
                    open Hiera1@1.0
                    add depend type=require fmri=pkg:/Hiera2@1.0
                    close """,
                """
                    open Hiera2@1.0
                    add depend type=require fmri=pkg:/Hiera3@1.0
                    close """,
                """
                    open Hiera3@1.0
                    add set name=pkg.depend.explicit-install value=true
                    close """,
        )

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, self.pkgs)

        def test_01_install(self):
                self.image_create(self.rurl, prefix="")
                # Test install works as expected.
                # This will fail because idr@1.0-0.1.1.0 has
                # pkg.depend.explicit-install set to true.
                self.pkg("install -v group incorp A@1.0-0.1.1.0", exit=1)
                self.pkg("install -v group incorp")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1    i--\n" \
                    "group    1.0-0    i--\n" \
                    "incorp    1.0-0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("uninstall -v group incorp A")
                self.pkg("list -H", exit=1)

                # Test exact-install works as expected.
                # This will fail because idr@1.0-0.1.1.0 has
                # pkg.depend.explicit-install set to true.
                self.pkg("exact-install -v group incorp A@1.0-0.1.1.0", exit=1)
                self.pkg("exact-install -v group incorp")
                self.pkg("verify")
                self.pkg("list -H")
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Test exact-install idr.
                self.pkg("exact-install -v idr")
                self.pkg("list -H")
                expected = \
                    "idr    1.0-0.1.1.0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("install -v group")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1.1.0    i--\n" \
                    "group    1.0-0    i--\n" \
                    "idr    1.0-0.1.1.0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("uninstall -v group idr A")
                self.pkg("list -H", exit=1)

                self.pkg("install -v idr")
                self.pkg("list -H")
                expected = \
                    "idr    1.0-0.1.1.0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("install -v group")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1.1.0    i--\n" \
                    "group    1.0-0    i--\n" \
                    "idr    1.0-0.1.1.0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("uninstall '*'")
                self.pkg("list -H", exit=1)

                self.pkgsend_bulk(self.rurl, self.pkgs2)
                self.pkg("install -v group incorp")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1.1.1    i--\n" \
                    "group    1.0-0    i--\n" \
                    "idr    1.0-0.1.1.1    i--\n" \
                    "incorp    1.0-0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkgsend_bulk(self.rurl, self.pkgs3)
                # test updating all packages.
                self.pkg("update")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1.1.2    i--\n" \
                    "group    1.0-0    i--\n" \
                    "idr    1.0-0.1.1.2    i--\n" \
                    "incorp    1.0-0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("uninstall '*'")

                self.pkgsend_bulk(self.rurl, self.pkgs4)
                # test require-any with pkg.depend.explicit-install tag.
                self.pkg("install C1")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "C1    1.0    i--\n" \
                    "C2    1.0    i--\n" \
                    "C3    1.0-0.1    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)
                self.pkg("uninstall '*'")

                self.pkg("install C1 C2")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "C1    1.0    i--\n" \
                    "C2    2.0    i--\n" \
                    "C3    1.0-0.1    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                # Test hierarchic dependencies.
                self.pkgsend_bulk(self.rurl, self.pkgs5)
                self.pkg("install -v Hiera1@1.0", exit=1)

        def test_02_updateReject(self):
                self.image_create(self.rurl, prefix="")
                self.pkgsend_bulk(self.rurl, self.pkgs2)
                self.pkgsend_bulk(self.rurl, self.pkgs3)
                self.pkg("install -v --reject idr group incorp")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1    i--\n" \
                    "group    1.0-0    i--\n" \
                    "incorp    1.0-0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                self.pkg("exact-install -v --reject idr group")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1    i--\n" \
                    "group    1.0-0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                # This will fail, because idr@1.0-0.1.1.0 is filtered.
                self.pkg("update -v --reject group A@1.0-0.1.1.0", exit=1)
                # Explicitly install idr@1.0-0.1.1.0.
                self.pkg("install idr@1.0-0.1.1.0")
                # Update again.
                self.pkg("update -v --reject group A@1.0-0.1.1.0")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1.1.0    i--\n" \
                    "idr    1.0-0.1.1.0    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)

                # This will fail.
                self.pkg("update -v --reject idr", exit=1)
                self.pkg("update")
                self.pkg("verify")
                self.pkg("list -H")
                expected = \
                    "A    1.0-0.1.1.2    i--\n" \
                    "idr    1.0-0.1.1.2    i--\n"
                output = self.reduceSpaces(self.output)
                expected = self.reduceSpaces(expected)
                self.assertEqualDiff(expected, output)


class TestPkgOSDowngrade(pkg5unittest.ManyDepotTestCase):
        persistent_setup = True

        pkgs = (
            """
                open entire@5.12-5.12.0.0.0.96.0
                add set name=pkg.depend.install-hold value=core-os
                add depend fmri=consolidation/osnet/osnet-incorporation type=require
                add depend fmri=consolidation/osnet/osnet-incorporation@5.12-5.12.0.0.0.96.1 facet.version-lock.consolidation/osnet/osnet-incorporation=true type=incorporate
                add depend fmri=consolidation/osnet/osnet-incorporation@5.12-5.12.0 type=incorporate
                add depend fmri=consolidation/install/install-incorporation type=require
                add depend fmri=consolidation/install/install-incorporation@5.12-5.12.0.0.0.4.0 facet.version-lock.consolidation/install/install-incorporation=true type=incorporate
                close
            """
            """
                open consolidation/install/install-incorporation@5.12-5.12.0.0.0.4.0
                add depend fmri=consolidation/osnet/osnet-incorporation type=require
                close
            """
            """
                open consolidation/osnet/osnet-incorporation@5.12-5.12.0.0.0.96.1
                add set name=pkg.depend.install-hold value=core-os.osnet
                add depend fmri=pkg:/system/data/terminfo/terminfo-core@5.12,5.12-5.12.0.0.0.96.1 type=incorporate
                close
            """
            """
                open system/data/terminfo/terminfo-core@5.12-5.12.0.0.0.96.1
                add depend fmri=consolidation/osnet/osnet-incorporation type=require
                close
            """
        )

        nightly_pkgs = (
            """
                open consolidation/osnet/osnet-incorporation@5.12-5.12.0.0.0.97.32830
                add set name=pkg.depend.install-hold value=core-os.osnet
                add depend fmri=pkg:/system/data/terminfo/terminfo-core@5.12-5.12.0.0.0.95.32487 type=incorporate
                close
            """
            """
                open consolidation/install/install-incorporation@5.12-5.12.0.0.0.4.0
                add depend fmri=consolidation/osnet/osnet-incorporation type=require
                close
            """
            """
                open system/data/terminfo/terminfo-core@5.12-5.12.0.0.0.95.32487
                add depend fmri=consolidation/osnet/osnet-incorporation type=require
                close
            """
        )

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["solaris", "nightly"])
                self.rurl = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()

                self.__pkgs = self.pkgsend_bulk(self.rurl, self.pkgs)
                self.__nightly_pkgs = self.pkgsend_bulk(self.rurl2, self.nightly_pkgs)

        def test_downgrade_update(self):
                """Verify that incorporated packages not affected by install-holds
                will be downgraded if the incorporating package is requested by
                the user or will be updated as part of a general update
                operation."""

                self.image_create(self.rurl, prefix="")
                self.pkg("install --parsable=0 entire terminfo-core")
                self.assertEqualParsable(self.output,
                    add_packages=[self.__pkgs[1], self.__pkgs[2],
                        self.__pkgs[0], self.__pkgs[3]]
                )

                self.pkg("set-publisher --non-sticky solaris")
                self.pkg("change-facet "
                    "version-lock.consolidation/osnet/osnet-incorporation=false")
                self.pkg("set-publisher -P -p {0}".format(self.rurl2))
                self.pkg("publisher")
                self.pkg("facet")
                self.pkg("list -afv")

                # In this case, we expect osnet-incorporation to be upgraded and
                # terminfo-core to be downgraded; install-incorporation should
                # not be modified since it was not named on the command-line.
                self.pkg("update --parsable=0 -n osnet-incorporation")
                self.assertEqualParsable(self.output,
                    change_packages=[
                        [self.__pkgs[2], self.__nightly_pkgs[0]],
                        [self.__pkgs[3], self.__nightly_pkgs[2]]
                    ]
                )

                # In this case, we expect osnet-incorporation and
                # install-incorporation to be upgraded, and terminfo-core to be
                # downgraded.
                self.pkg("update --parsable=0 -n")
                self.assertEqualParsable(self.output,
                    change_packages=[
                        [self.__pkgs[1], self.__nightly_pkgs[1]],
                        [self.__pkgs[2], self.__nightly_pkgs[0]],
                        [self.__pkgs[3], self.__nightly_pkgs[2]]
                    ]
                )


class TestPkgUpdateDowngradeIncorp(pkg5unittest.ManyDepotTestCase):
        persistent_setup = True

        pkgs = (
                """
                    open A@1.0,5.11-0
                    close """,
                """
                    open A@2.0,5.11-0
                    close """,
                """
                    open B@1.0,5.11-0
                    add set pkg.depend.install-hold=B
                    close """,
                """
                    open B@2.0,5.11-0
                    add set pkg.depend.install-hold=B
                    close """,
                """
                    open C@1.0,5.11-0
                    add set pkg.depend.install-hold=parent.C
                    close """,
                """
                    open C@2.0,5.11-0
                    add set pkg.depend.install-hold=parent.C
                    close """,
                """
                    open incorp@1.0,5.11-0
                    add depend type=incorporate fmri=A@2.0
                    close """,
                """
                    open incorp@2.0,5.11-0
                    add depend type=incorporate fmri=A@1.0
                    close """,
                """
                    open parent_incorp@1.0,5.11-0
                    add depend type=incorporate fmri=child_incorp@2.0
                    close """,
                """
                    open parent_incorp@2.0,5.11-0
                    add depend type=incorporate fmri=child_incorp@1.0
                    close """,
                """
                    open child_incorp@1.0,5.11-0
                    add depend type=incorporate fmri=A@1.0
                    close """,
                """
                    open child_incorp@2.0,5.11-0
                    add depend type=incorporate fmri=A@2.0
                    close """,
                """
                    open ihold_incorp@1.0,5.11-0
                    add set pkg.depend.install-hold=parent
                    add depend type=incorporate fmri=B@1.0
                    add depend type=incorporate fmri=C@1.0
                    close """,
                """
                    open ihold_incorp@2.0,5.11-0
                    add set pkg.depend.install-hold=parent
                    add depend type=incorporate fmri=B@2.0
                    add depend type=incorporate fmri=C@2.0
                    close """,

                """
                    open p_incorp@1.0,5.11-0
                    add depend type=incorporate fmri=D@2.0
                    close """,

                """
                    open p_incorp@2.0,5.11-0
                    add depend type=incorporate fmri=D@1.0
                    close """,

                """
                    open D@2.0,5.11-0
                    close """,
                )

        pub2_pkgs = (
                """
                    open D@1.0,5.11-0
                    close """,
                )

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])
                self.rurl = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()

                self.pkgsend_bulk(self.rurl, self.pkgs)
                self.pkgsend_bulk(self.rurl2, self.pub2_pkgs)

        def test_incorp_downgrade(self):
                """ Test that downgrades are allowed if they are incorporated
                by FMRIs which are requested by the user or are about to be
                updated as part of an update-all operation."""

                self.image_create(self.rurl, prefix="")
                self.pkg("install A incorp@1")
                self.pkg("list A@2.0 incorp@1.0")

                # When incorp moves forward, A should move backwards
                self.pkg("update incorp@2")
                self.pkg("list A@1.0 incorp@2.0")

                # start over and test if that also works if we do an update all
                self.pkg("update incorp@1")
                self.pkg("update -v")
                self.pkg("list A@1.0 incorp@2.0")

                # prepare test for nested incorporations
                self.pkg("uninstall incorp")
                self.pkg("update A@2")
                self.pkg("install parent_incorp@1 child_incorp@2")
                self.pkg("list A@2.0 child_incorp@2 parent_incorp@1")

                # test update of nested incorporation supports downgrade
                self.pkg("update -v parent_incorp@2")
                self.pkg("list A@1 child_incorp@1 parent_incorp@2")

                # prepare test for explicit downgrade of incorp
                self.pkg("uninstall parent_incorp")
                self.pkg("update child_incorp@2")
                self.pkg("list A@2 child_incorp@2")

                # test explicit downgrade of incorp downgrades incorp'ed pkgs
                self.pkg("update -v child_incorp@1")
                self.pkg("list A@1 child_incorp@1")


        def test_incorp_downgrade_installhold(self):
                """Test correct handling of install-holds when determining
                which pkgs are ok to downgrade."""

                # prepare test for install-hold
                self.image_create(self.rurl, prefix="")
                self.pkg("install ihold_incorp@2 B")
                self.pkg("list ihold_incorp@2 B@2")
                # test that install hold prevents downgrade
                self.pkg("update -v ihold_incorp@1", exit=1)

                # prep test for parent install-hold
                self.pkg("install --reject B C@2")
                self.pkg("list ihold_incorp@2 C@2")
                # test that downgrade is allowed if install-hold is child of
                # requested FMRI
                self.pkg("update -v ihold_incorp@1")
                self.pkg("list ihold_incorp@1 C@1")

        def test_incorp_downgrade_pubswitch(self):
                """Test that implicit publisher switches of incorporated pkgs
                are not allowed."""

                # prepare test for publisher switch
                self.image_create(self.rurl, prefix="")
                self.pkg("set-publisher --non-sticky test1")
                self.pkg("set-publisher --non-sticky -p {0}".format(self.rurl2))
                self.pkg("list -af")
                self.pkg("install p_incorp@1 D@2")
                self.pkg("list p_incorp@1 D@2")

                self.pkg("update p_incorp@2", exit=1)


if __name__ == "__main__":
        unittest.main()
