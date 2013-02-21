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
# Copyright (c) 2013, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest

class TestPkgRepo(pkg5unittest.SingleDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False

        tree10 = """
            set name=pkg.fmri value=tree@1.0,5.11-0:20110804T203458Z
            set name=pkg.summary value="Leafy SPARC package" variant.arch=sparc
            set name=pkg.summary value="Leafy i386 package" variant.arch=i386
            set name=info.classification value=org.opensolaris.category.2008:System/Core
            set name=variant.arch value=i386 value=sparc
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer"""

        tree20 = """
            set name=pkg.fmri value=tree@2.0,5.11-0:20110804T203458Z
            set name=pkg.summary value="Leafy SPARC package" variant.arch=sparc
            set name=pkg.summary value="Leafy i386 package" variant.arch=i386
            set name=info.classification value=org.opensolaris.category.2008:System/Core
            set name=variant.arch value=i386 value=sparc
            file tmp/empty mode=0555 owner=root group=bin path=/etc/empty
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer"""

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                tfiles = self.make_misc_files(["tmp/empty", "tmp/truck1",
                    "tmp/noaccess"])
                self.tree10_p5m = self.make_manifest(self.tree10)
                self.tree20_p5m = self.make_manifest(self.tree20)
                self.bogus_p5m = os.path.join(self.test_root, "nosuch.p5m")
                self.noaccess_p5m = self.make_misc_files(
                    ["tmp/noaccess.p5m"])[0]
                os.chmod(self.noaccess_p5m, 0000)

        def test_00_base(self):
                """Verify pkgdiff handles basic option and subcommand parsing as
                expected.
                """

                # --help, -? should exit with 0.
                self.pkgdiff("--help", exit=0)
                self.pkgdiff("'-?'", exit=0)

                # unknown options should exit with 2.
                self.pkgdiff("-U", exit=2)
                self.pkgdiff("--unknown", exit=2)

                # no arguments should exit with 2.
                self.pkgdiff("", exit=2)

                # one argument should exit with 2.
                self.pkgdiff(self.tree10_p5m, exit=2)

        def test_01_input(self):
                """Verify that pkgdiff can accept input from both files and
                stdin and works as expected."""

                #
                # Verify file input.
                #

                # Verify that pkgdiff finds no difference for the same file.
                self.pkgdiff(" ".join((self.tree10_p5m, self.tree10_p5m)))

                # Verify that pkgdiff finds a difference for different files.
                self.pkgdiff(" ".join((self.tree10_p5m, self.tree20_p5m)),
                    exit=1)

                # Verify that pkgdiff gracefully handles no such file errors.
                self.pkgdiff(" ".join((self.tree10_p5m, self.bogus_p5m)), exit=3)

                # Verify that pkgdiff gracefully handles permission errors.
                self.pkgdiff(" ".join((self.tree10_p5m, self.noaccess_p5m)),
                    su_wrap=True, exit=3)

                #
                # Verify stdin input.
                #

                # Verify that both arguments cannot be stdin.
                self.pkgdiff("- -", exit=2)

                # Verify that one argument can be stdin with no differences for
                # identical case.
                self.pkgdiff("- %s < %s" % (self.tree10_p5m, self.tree10_p5m))

                # Verify that one argument can be stdin with differences.
                self.pkgdiff("%s - < %s" % (self.tree10_p5m, self.tree20_p5m),
                    exit=1)


if __name__ == "__main__":
        unittest.main()
