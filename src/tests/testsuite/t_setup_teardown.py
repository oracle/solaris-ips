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

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import unittest

from pkg import misc

class TestAllFine(pkg5unittest.SingleDepotTestCase):
        
        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

        def tearDown(self):
                pkg5unittest.SingleDepotTestCase.tearDown(self)

        def test_shouldpass1(self):
                pass

        def test_shouldpass2(self):
                pass

class TestSetupFailing(pkg5unittest.SingleDepotTestCase):
        
        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                raise RuntimeError("setup failing")

        def test_shoulderror1(self):
                pass

        def test_shoulderror2(self):
                pass

class TestSetupFailingEarly(pkg5unittest.SingleDepotTestCase):
        
        def setUp(self):
                raise RuntimeError("setup failing")
                pkg5unittest.SingleDepotTestCase.setUp(self)

        def test_shoulderror1(self):
                pass

class TestSetupFailingP(pkg5unittest.SingleDepotTestCase):
        persistent_setup = True
        
        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                raise RuntimeError("setup failing")

        def test_shoulderror1(self):
                pass

        def test_shoulderror2(self):
                pass

class TestSetupFailingEarlyP(pkg5unittest.SingleDepotTestCase):
        persistent_setup = True
        
        def setUp(self):
                raise RuntimeError("setup failing")
                pkg5unittest.SingleDepotTestCase.setUp(self)

        def test_shoulderror1(self):
                pass

class TestTeardownFailing(pkg5unittest.SingleDepotTestCase):
        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

        def tearDown(self):
                raise RuntimeError("tearDown failing")

        def test_shoulderror1(self):
                pass

        def test_shoulderror2(self):
                pass

class TestTeardownFailingP(pkg5unittest.SingleDepotTestCase):
        persistent_setup = True

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)

        def tearDown(self):
                raise RuntimeError("tearDown failing")

        def test_shouldpass1(self):
                pass

        def test_shouldpass2(self):
                pass

class TestMisc(pkg5unittest.CliTestCase):
        def doassign(self):
                self.test_root = "foo"

        def test_testroot_readonly(self):
                """ Test that test_root is readable but not writable """
                x = self.test_root
                self.assertRaises(AttributeError, self.doassign)

if __name__ == "__main__":
        unittest.main()
