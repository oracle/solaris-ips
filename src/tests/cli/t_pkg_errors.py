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
# Copyright (c) 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

class TestPkgSolverErrors(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        pkgs = (
            """
            open entire@1.0
            add depend type=incorporate fmri=perl-516@1.0
            close """,

            """
            open entire@1.1
            add depend type=incorporate fmri=perl-516@1.1
            close """,

            """
            open osnet@1.0
            add depend type=require fmri=perl-516
            add depend type=incorporate fmri=baz@1.0
            close """,

            """
            open perl-516@1.0
            add dir mode=0755 owner=root group=bin path=/perl516_1.1
            add depend type=require fmri=entire
            close """,

            """
            open perl-516@1.1
            add set name=pkg.obsolete value=true
            add set name=pkg.summary value="A test package"
            close """
            )

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.pkgsend_bulk(self.rurl, self.pkgs)

        def test_incorporation_mixes(self):
            self.image_create(self.rurl, prefix="")

            # install entire, osnet and perl

            self.pkg("install perl-516 entire@1.0 osnet")
            self.pkg("install entire@latest", exit=1)
            self.assertFalse("No solution" in self.errout)
            self.assertTrue("Package 'osnet' must be uninstalled"
                " or upgraded if the requested operation is to be performed."
                in self.errout)
