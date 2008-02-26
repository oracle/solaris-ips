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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import unittest
import os
import testutils
import shutil

import pkg.depotcontroller as dc

class TestDepotController(testutils.pkg5TestCase):

        def setUp(self):
                testutils.pkg5TestCase.setUp(self)

                self.__dc = dc.DepotController()
                self.__pid = os.getpid()

                depotpath = os.path.join(self.get_test_prefix(), "depot")
                logpath = os.path.join(self.get_test_prefix(), self.id())

                try:
                        os.makedirs(depotpath, 0755)
                except:
                        pass

                self.__dc.set_repodir(depotpath)
                self.__dc.set_logpath(logpath)

        def tearDown(self):
                testutils.pkg5TestCase.tearDown(self)

                self.__dc.kill()
                shutil.rmtree(self.__dc.get_repodir())
                os.remove(self.__dc.get_logpath())


        def testStartStop(self):
                self.__dc.set_port(12000)
                for i in range(0, 5):
                        self.__dc.start()
                        self.assert_(self.__dc.is_alive())
                        self.__dc.stop()
                        self.assert_(not self.__dc.is_alive())



if __name__ == "__main__":
        unittest.main()
