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
# Copyright (c) 2013, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest

class TestPkgRepo(pkg5unittest.SingleDepotTestCase):
        # Cleanup after every test.
        persistent_setup = False

        stub1 = """
            dir owner=root group=root mode=0755 path=etc
            file tmp/empty mode=0555 owner=root group=bin path=/etc/empty
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer"""

        stub2 = """
            dir owner=root group=root mode=0755 path=etc
            file tmp/empty mode=0555 owner=root group=bin path=/etc/empty
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/ditch """

        tree10 = """
            set name=pkg.fmri value=tree@1.0,5.11-0:20110804T203458Z
            set name=pkg.summary value="Leafy SPARC package" variant.arch=sparc
            set name=pkg.summary value="Leafy i386 package" variant.arch=i386
            set name=info.classification value=org.opensolaris.category.2008:System/Core
            set name=variant.arch value=i386 value=sparc
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer"""

        tree20 = """
            set name=pkg.fmri value=tree@2.0,5.11-0:20120804T203458Z
            set name=pkg.summary value="Leafy SPARC package" variant.arch=sparc
            set name=pkg.summary value="Leafy i386 package" variant.arch=i386
            set name=info.classification value=org.opensolaris.category.2008:System/Core
            set name=variant.arch value=i386 value=sparc
            dir owner=root group=root mode=0755 path=etc
            file tmp/empty mode=0555 owner=root group=bin path=/etc/empty
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer"""

        tree30 = """
            set name=pkg.fmri value=tree@3.0,5.11-0:20130804T203458Z
            set name=pkg.summary value="Leafy SPARC package" variant.arch=sparc
            set name=pkg.summary value="Leafy i386 package" variant.arch=i386
            set name=info.classification value=org.opensolaris.category.2008:System/Core
            set name=variant.arch value=i386 value=sparc
            dir owner=root group=root mode=0755 path=etc
            file tmp/empty mode=0555 owner=root group=bin path=/etc/empty
            file tmp/truck1 mode=0444 owner=root group=bin path=/etc/trailer"""

        hashed10 = """
            set name=pkg.fmri value=hashed@1.0:20130804T203459Z
            license 6aba708bd383553aa84bba4fefe8495239927767 chash=60c3aa47dce2ba0132efdace8d3b88b6589767f4 license=lic_OTN
            file 4ab5de3107a63f5cf454485f720cac025f1b7002 chash=dc03afd488e3b3e4c4993d2403d7e15603b0a391 path=etc/motd"""

        hashed20 = """
            set name=pkg.fmri value=hashed@2.0:20130904T203001Z
            license 7ab6de3107a63f5cf454485f720cac025f1b7001 chash=cc05afd488e3b3e4c4993d2403d7e15603b0a398 license=lic_OTN
            file 3aba408bd383553aa84bba4fefe8495239927763 chash=f0c2aa47dce2ba0132efdace8d3b88b6589767f3 path=etc/motd"""

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                tfiles = self.make_misc_files(["tmp/empty", "tmp/truck1",
                    "tmp/noaccess"])
                self.stub1_p5m = self.make_manifest(self.stub1)
                self.stub2_p5m = self.make_manifest(self.stub2)
                self.tree10_p5m = self.make_manifest(self.tree10)
                self.tree20_p5m = self.make_manifest(self.tree20)
                self.tree30_p5m = self.make_manifest(self.tree30)
                self.hashed10_p5m = self.make_manifest(self.hashed10)
                self.hashed20_p5m = self.make_manifest(self.hashed20)
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
                self.pkgdiff("- {0} < {1}".format(self.tree10_p5m, self.tree10_p5m))

                # Verify that one argument can be stdin with differences.
                self.pkgdiff("{0} - < {1}".format(self.tree10_p5m, self.tree20_p5m),
                    exit=1)

        def test_02_type_filter(self):
                """Verify that pkgdiff action type filtering works as expected."""

                # Verify unknown types cause graceful failure.
                self.pkgdiff(" ".join(("-t bogus,nosuchtype", self.tree10_p5m,
                    self.tree10_p5m)), exit=2)
                self.pkgdiff(" ".join(("-t bogus", "-t nosuchtype",
                    self.tree10_p5m, self.tree10_p5m)), exit=2)
                self.pkgdiff(" ".join(("-t bogus", "-t file", self.tree10_p5m,
                    self.tree10_p5m)), exit=2)

                # Verify no differences for same manifest.
                self.pkgdiff(" ".join(("-t file", self.tree10_p5m,
                    self.tree10_p5m)))

                # Verify differences found for file actions between 1.0 and 2.0.
                self.pkgdiff(" ".join(("-t file", self.tree10_p5m,
                    self.tree20_p5m)), exit=1)

                # Verify differences found for dir actions between 1.0 and 2.0.
                self.pkgdiff(" ".join(("-t dir", self.tree10_p5m,
                    self.tree20_p5m)), exit=1)

                # Verify no differences found for file actions between 2.0 and
                # 3.0.
                self.pkgdiff(" ".join(("-t file", self.tree20_p5m,
                    self.tree30_p5m)))

                # Verify no differences found for dir and file actions between
                # 2.0 and 3.0 using both option forms.
                self.pkgdiff(" ".join(("-t dir,file", self.tree20_p5m,
                    self.tree30_p5m)), stderr=True)

                self.pkgdiff(" ".join(("-t dir", "-t file", self.tree20_p5m,
                    self.tree30_p5m)))

                # Verify differences found when only one action of a given type
                # of two differs between stub1 and stub2 and other actions are
                # the same.
                self.pkgdiff(" ".join(("-t file", self.stub1_p5m,
                    self.stub2_p5m)), exit=1)

        def test_03_hash(self):
                """Verify that hash attributes are compared as expected."""

                # Verify no differences for same manifest.
                self.pkgdiff(" ".join(("-t file", self.hashed10_p5m,
                    self.hashed10_p5m)))

                # Verify differences found for file actions between 1.0 and 2.0;
                # in particular, that the 'old' hash values match 1.0 and the
                # 'new' hash values match 2.0.
                self.pkgdiff(" ".join(("-t file", self.hashed10_p5m,
                    self.hashed20_p5m)), exit=1)
                expected = """\
file path=etc/motd 
 - 4ab5de3107a63f5cf454485f720cac025f1b7002
 + 3aba408bd383553aa84bba4fefe8495239927763
 - chash=dc03afd488e3b3e4c4993d2403d7e15603b0a391
 + chash=f0c2aa47dce2ba0132efdace8d3b88b6589767f3
"""
                actual = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, actual)

                # Again, but only comparing hash attribute.
                self.pkgdiff(" ".join(("-t file -o hash", self.hashed10_p5m,
                    self.hashed20_p5m)), exit=1)
                expected = """\
file path=etc/motd 
 - 4ab5de3107a63f5cf454485f720cac025f1b7002
 + 3aba408bd383553aa84bba4fefe8495239927763
"""
                actual = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, actual)

                # Again, ignoring hash attributes (should find no differences).
                self.pkgdiff(" ".join(("-t file -i hash -i chash",
                    self.hashed10_p5m, self.hashed20_p5m)), exit=0)

                # Verify differences found for license actions between 2.0 and 1.0;
                # in particular, that the 'old' hash values match 2.0 and the
                # 'new' hash values match 1.0.
                self.pkgdiff(" ".join(("-t license", self.hashed20_p5m,
                    self.hashed10_p5m)), exit=1)
                expected = """\
license license=lic_OTN 
 - 7ab6de3107a63f5cf454485f720cac025f1b7001
 + 6aba708bd383553aa84bba4fefe8495239927767
 - chash=cc05afd488e3b3e4c4993d2403d7e15603b0a398
 + chash=60c3aa47dce2ba0132efdace8d3b88b6589767f4
"""
                actual = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, actual)

                # Again, but only comparing hash attribute.
                self.pkgdiff(" ".join(("-t license -o hash", self.hashed20_p5m,
                    self.hashed10_p5m)), exit=1)
                expected = """\
license license=lic_OTN 
 - 7ab6de3107a63f5cf454485f720cac025f1b7001
 + 6aba708bd383553aa84bba4fefe8495239927767
"""
                actual = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, actual)

                # Again, ignoring hash attributes (should find no differences).
                self.pkgdiff(" ".join(("-t license -i hash -i chash",
                    self.hashed20_p5m, self.hashed10_p5m)), exit=0)


if __name__ == "__main__":
        unittest.main()
