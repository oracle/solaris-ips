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
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

import re
import shutil
import time
import unittest

class TestPkgHistory(testutils.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        foo1 = """
            open foo@1,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1)

                # Ensure that the second repo's packages are exactly the same
                # as those in the first ... by duplicating the repo.
                self.dcs[2].stop()
                d1dir = self.dcs[1].get_repodir()
                d2dir = self.dcs[2].get_repodir()
                shutil.rmtree(d2dir)
                shutil.copytree(d1dir, d2dir)
                self.dcs[2].start()

                self.image_create(durl1, prefix = "test1")

        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)

        def test_1_history_options(self):
                """Verify all history options are accepted or rejected as
                expected.
                """
                self.pkg("history")
                self.pkg("history -l")
                self.pkg("history -H")
                self.pkg("history -lH", exit=2)

        def test_2_history_record(self):
                """Verify that all image operations that change an image are
                recorded as expected.
                """

                durl2 = self.dcs[2].get_depot_url()
                commands = [
                    "install foo",
                    "uninstall foo",
                    "image-update",
                    "set-authority -O " + durl2 + " test2",
                    "set-authority -P test1",
                    "set-authority -m " + durl2 + " test1",
                    "set-authority -M " + durl2 + " test1",
                    "unset-authority test2",
                    "rebuild-index"
                ]

                operations = [
                    "install",
                    "uninstall",
                    "image-update",
                    "set-authority",
                    "set-preferred-authority",
                    "add-mirror",
                    "delete-mirror",
                    "delete-authority",
                    "rebuild-index"
                ]

                for cmd in commands:
                        self.pkg(cmd)
                        time.sleep(1)

                self.pkg("history -H")
                o = self.output
                self.assert_(
                    re.search("TIME\s+", o.splitlines()[0]) == None)

                # Only the operation is listed in short format.
                for op in operations:
                        # Verify that each operation was recorded.
                        self.assert_(o.find(op) != -1)

                # The actual commands are only found in long format.
                self.pkg("history -l")
                o = self.output
                for cmd in commands:
                        # Verify that each of the commands was recorded.
                        self.assert_(o.find(" %s" % cmd) != -1)

        def test_3_purge_history(self):
                """Verify that the purge-history command works as expected.
                """
                self.pkg("purge-history")
                self.pkg("history -H")
                o = self.output
                # Ensure that the first item in history output is now
                # purge-history.
                self.assert_(
                    re.search("purge-history", o.splitlines()[0]) != None)

if __name__ == "__main__":
        unittest.main()

