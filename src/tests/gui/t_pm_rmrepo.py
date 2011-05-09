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

# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest
import unittest

try:
        import ldtp
        import ldtputils
        if not "getmin" in dir(ldtp):
            raise ImportError
except ImportError:
        raise ImportError, "ldtp 2.X package not installed."

class TestPkgGuiRmRepoBasics(pkg5unittest.ManyDepotTestCase):

        # pygtk requires unicode as the default encoding.
        default_utf8 = True

        foo1 = """
            open foo@1,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            close """

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"],
                    start_depots=True)

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1)

                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.bar1)

                self.image_create(durl1, prefix="test1")

                self.pkg("set-publisher -O " + durl2 + " test2")

        def testRmRepository(self):
                repo_name = "test2"
                pm_str = "%s/usr/bin/packagemanager" % pkg5unittest.g_proto_area
                ldtp.launchapp(pm_str,["-R", self.get_img_path()])
                ldtp.waittillguiexist('Package Manager', state = ldtp.state.ENABLED)

                ldtp.selectmenuitem('Package Manager', 'mnuFile;mnuManage Publishers...')
                
                ldtp.waittillguiexist('dlgManage Publishers')

                ldtp.selectrow('dlgManage Publishers', 'Publishers', repo_name)

                ldtp.click('dlgManage Publishers', 'btnRemove')

                ldtp.click('dlgManage Publishers', 'btnOK')

                ldtp.waittillguiexist('dlgManage Publishers Confirmation')

                ldtp.click('dlgManage Publishers Confirmation', 'btnOK')

                ldtp.waittillguinotexist('dlgManage Publishers')

                # Verify result
                self.pkg('publisher | grep %s' % repo_name, exit=1)

                # Quit Package Manager
                ldtp.selectmenuitem('Package Manager', 'mnuFile;mnuQuit')

if __name__ == "__main__":
	unittest.main()
