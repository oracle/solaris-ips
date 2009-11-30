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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import unittest
import os
import sys
import pkg.client.bootenv as bootenv

# Set the path so that modules above can be found
path_to_parent = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, path_to_parent)
import pkg5unittest

class TestBootEnv(pkg5unittest.Pkg5TestCase):
        def setUp(self):
                pass
                
        def test_api_consistency(self):
                """Make sure every public method in BootEnv exists in
                BootEnvNull.
                """
                nullm = dir(bootenv.BootEnvNull)
                for m in dir(bootenv.BootEnv):
                        if m.startswith("_"):
                                continue
                        self.assert_(m in nullm,
                            "missing method %s in BootEnvNull" % m)
            
if __name__ == "__main__":
        unittest.main()
