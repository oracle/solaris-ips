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

# Copyright (c) 2012, 2020, Oracle and/or its affiliates. All rights reserved.

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import unittest
import os
import pty
import six
import sys
import threading

import pkg.client.printengine as printengine

class TestPrintEngine(pkg5unittest.Pkg5TestCase):
        def test_posix_printengine_tty(self):
                """Test POSIX print engine tty mode."""
                sio = six.StringIO()
                def __drain(masterf):
                        """Drain data from masterf and discard until eof."""
                        while True:
                                chunksz = 1024
                                termdata = masterf.read(chunksz)
                                if len(termdata) < chunksz:
                                        # assume we hit EOF
                                        break
                                print(termdata, file=sio)

                #
                # - Allocate a pty
                # - Create a thread to drain off the master side; without
                #   this, the slave side will block when trying to write.
                # - Connect the printengine to the slave side
                # - Set it running
                #
                (master, slave) = pty.openpty()
                slavef = os.fdopen(slave, "w")
                masterf = os.fdopen(master, "r")

                t = threading.Thread(target=__drain, args=(masterf,))
                t.start()

                printengine.test_posix_printengine(slavef, True)
                slavef.close()

                t.join()
                masterf.close()
                self.assertTrue(len(sio.getvalue()) > 0)

        def test_posix_printengine_badtty(self):
                """Try to make ttymode POSIX print engines on non-ttys."""
                f = six.StringIO()
                self.assertRaises(printengine.PrintEngineException,
                    printengine.POSIXPrintEngine, f, True)

                tpath = self.make_misc_files("testfile")
                f = open(tpath[0], "w")
                self.assertRaises(printengine.PrintEngineException,
                    printengine.POSIXPrintEngine, f, True)
                f.close()

        def test_posix_printengine_notty(self):
                """Smoke test POSIX print engine non-tty mode."""
                sio = six.StringIO()
                printengine.test_posix_printengine(sio, False)
                self.assertTrue(len(sio.getvalue()) > 0)

        def test_logging_printengine(self):
                """Smoke test logging print engine."""
                sio = six.StringIO()
                printengine.test_logging_printengine(sio)
                self.assertTrue(len(sio.getvalue()) > 0)

if __name__ == "__main__":
        unittest.main()
