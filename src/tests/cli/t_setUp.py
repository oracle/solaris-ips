#!/usr/bin/python2.4
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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
import pkg5unittest

if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import unittest

class TestSetUp(testutils.SingleDepotTestCase):
        """Test whether an exception in setUp leaves a depot running.
        If it does, the second test will fail with a DepotStateException.
        If the baseline.SuccessfulException is raised, BaselineTestCase
        will report the test a success.
        """

        def setUp(self):
                testutils.SingleDepotTestCase.setUp(self)
                raise pkg5unittest.SuccessfulException("Died in setup")

        def test_first_depot_start(self):
                """Attempt to start a depot, which dies because of an exception
                raised during setUP.
                """

                durl = self.dc.get_depot_url()

        def test_second_depot_start(self):
                """Test whether the first depot was shut down.  If this test
                raises a exception because a depot was already running on that
                port, then the test has failed.  If it raises the
                SuccessfulException, then it has passed because it was able to
                successfully start a depot."""

                durl = self.dc.get_depot_url()


if __name__ == "__main__":
        unittest.main()
