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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest


class TestPkgPropertyBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        def test_pkg_properties(self):
                """pkg: set, unset, and display properties"""

                self.image_create(self.rurl)

		self.pkg("set-property -@", exit=2)
                self.pkg("get-property -@", exit=2)
                self.pkg("property -@", exit=2)

                self.pkg("set-property title sample")
                self.pkg('set-property description "more than one word"')
                self.pkg("property")
                self.pkg("property | grep title")
                self.pkg("property | grep description")
                self.pkg("property | grep 'sample'")
                self.pkg("property | grep 'more than one word'")
                self.pkg("unset-property description")
                self.pkg("property -H")
                self.pkg("property title")
                self.pkg("property -H title")
                self.pkg("property description", exit=1)
                self.pkg("unset-property description", exit=1)
                self.pkg("unset-property", exit=2)

                self.pkg("set-property signature-policy verify")
                self.pkg("set-property signature-policy verify foo", exit=2)
                self.pkg("set-property signature-policy vrify", exit=1)
                self.pkg("set-property signature-policy require-names", exit=1)
                self.pkg("set-property signature-policy require-names foo")

                self.pkg("add-property-value signature-policy verify", exit=1)
                self.pkg("add-property-value signature-required-names foo")
                self.pkg("add-property-value signature-required-names bar")
                self.pkg("remove-property-value signature-required-names foo")
                self.pkg("remove-property-value signature-required-names baz",
                    exit=1)
                self.pkg("add-property-value foo", exit=2)
                self.pkg("remove-property-value foo", exit=2)
                self.pkg("set-property foo", exit=2)
                self.pkg("set-property foo bar")
                self.pkg("remove-property-value foo bar", exit=1)
                self.pkg("set-property", exit=2)

                self.pkg("set-property trust-anchor-directory %s %s" %
                    (self.test_root, self.test_root), exit=1)

                # Verify that properties with single values can be set and
                # retrieved as expected.
                self.pkg("set-property flush-content-cache-on-success False")
                self.pkg("property -H flush-content-cache-on-success |"
                    "grep -i flush-content-cache-on-success.*false$")

        def test_missing_permissions(self):
                """Bug 2393"""

                self.image_create(self.rurl)

                self.pkg("property")
                self.pkg("set-property require-optional True", su_wrap=True,
                    exit=1)
                self.pkg("set-property require-optional True")
                self.pkg("unset-property require-optional", su_wrap=True,
                    exit=1)
                self.pkg("unset-property require-optional")


if __name__ == "__main__":
        unittest.main()
