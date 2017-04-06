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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.config as cfg
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.server.repository as repo
import tempfile
import time
import unittest
import zlib

from six.moves.urllib.parse import urlparse
from six.moves.urllib.request import url2pathname

class TestUtilMerge(pkg5unittest.ManyDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False

        scheme10 = """
            open pkg:/scheme@1.0,5.11-0
            close
        """

        tree10 = """
            open tree@1.0,5.11-0
            close
        """

        amber10 = """
            open amber@1.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
            close
        """

        amber20 = """
            open amber@2.0,5.11-0
            add depend fmri=pkg:/tree@1.0 type=require
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

        misc_files = [ "tmp/bronzeA1",  "tmp/bronzeA2",
                    "tmp/bronze1", "tmp/bronze2",
                    "tmp/copyright2", "tmp/copyright3",
                    "tmp/libc.so.1", "tmp/sh"]

        def setUp(self):
                """ Start two depots.
                    depot 1 gets foo and moo, depot 2 gets foo and bar
                    depot1 is mapped to publisher test1 (preferred)
                    depot2 is mapped to publisher test2 """

                # This test suite needs an actual depot.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["os.org", "os.org"],
                    start_depots=True)
                self.make_misc_files(self.misc_files)

                # Publish a set of packages to one repository.
                self.dpath1 = self.dcs[1].get_repodir()
                self.durl1 = self.dcs[1].get_depot_url()
                self.published = self.pkgsend_bulk(self.durl1, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20, self.tree10,
                    self.scheme10))

                # Ensure timestamps of all successive publications are greater.
                time.sleep(1)

                # Publish the same set to another repository (minus the tree
                # and scheme packages).
                self.dpath2 = self.dcs[2].get_repodir()
                self.durl2 = self.dcs[2].get_depot_url()
                self.published += self.pkgsend_bulk(self.durl2, (self.amber10,
                    self.amber20, self.bronze10, self.bronze20))

                self.merge_dir = tempfile.mkdtemp(dir=self.test_root)
                repo.repository_create(self.merge_dir)

        @staticmethod
        def get_repo(uri):
                parts = urlparse(uri, "file", allow_fragments=0)
                path = url2pathname(parts[2])

                try:
                        return repo.Repository(root=path)
                except cfg.ConfigError as e:
                        raise repo.RepositoryError(_("The specified "
                            "repository's configuration data is not "
                            "valid:\n{0}").format(e))

        def test_0_merge(self):
                """Verify that merge functionality works as expected."""

                pkg_names = set()
                flist = []
                for p in self.published:
                        f = fmri.PkgFmri(p)
                        pkg_names.add(f.pkg_name)
                        flist.append(f)

                self.merge([
                    "-d {0}".format(self.merge_dir),
                    "-s arch=sparc,{0}".format(self.durl1),
                    "-s arch=i386,{0}".format(self.durl2),
                    " ".join(pkg_names),
                ])

                # Only get the newest FMRIs for each package.
                flist.sort()
                nlist = {}
                for f in reversed(flist):
                        if f.pkg_name in nlist:
                                continue
                        nlist[f.pkg_name] = f
                nlist = nlist.values()

                def get_expected(f):
                        exp_lines = ["set name=pkg.fmri value={0}".format(f)]
                        for dc in self.dcs.values():
                                repo = dc.get_repo()
                                mpath = repo.manifest(f)
                                if not os.path.exists(mpath):
                                        # Not in this repository, check next.
                                        continue

                                m = open(mpath, "r")
                                for l in m:
                                        if l.find("name=pkg.fmri") > -1:
                                                continue
                                        if l.find("name=variant") > -1:
                                                continue
                                        if not l.strip():
                                                continue
                                        exp_lines.append(l.strip())
                                m.close()

                        if f.pkg_name in ("tree", "scheme"):
                                # These packages are only published for sparc.
                                exp_lines.append("set name=variant.arch value=sparc")
                        else:
                                # Everything else is published for all variants.
                                exp_lines.append("set name=variant.arch value=sparc value=i386")
                        return "\n".join(sorted(exp_lines))

                # Now load the manifest file for each package and verify that
                # the merged manifest matches expectations.
                for f in nlist:
                        mpath = os.path.join(self.merge_dir, "publisher",
                            "os.org", "pkg", f.get_dir_path())

                        m = open(mpath, "r")
                        returned = "".join(sorted(l for l in m))
                        returned = returned.strip()
                        m.close()

                        # Generate expected and verify.
                        expected = get_expected(f)
                        self.assertEqualDiff(expected, returned)


if __name__ == "__main__":
        unittest.main()
