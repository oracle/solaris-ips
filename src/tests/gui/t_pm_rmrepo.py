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

# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

from cli import testutils

if __name__ == "__main__":
        testutils.setup_environment("../../../proto")

try:
        import ldtp
except ImportError:
        raise ImportError, "SUNWldtp package not installed."

class TestPkgGuiRmRepoBasics(testutils.ManyDepotTestCase):

        persistent_depot = False

        foo1 = """
            open foo@1,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, ["test1", "test2"])

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1)

                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.bar1)

                self.image_create(durl1, prefix="test1")
                self.pkg("set-publisher -O " + durl2 + " test2")

        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)
        
        def testRmRepository(self):
                repo_name = "test2"

                ldtp.launchapp("%s/usr/bin/packagemanager" % testutils.g_proto_area)

                ldtp.selectmenuitem('frmPackageManager', 'mnuManageRepositories')
                
                ldtp.waittillguiexist('dlgManageRepositories')

                ldtp.selectrow('dlgManageRepositories', 'Repositories', repo_name)

                ldtp.click('dlgManageRepositories', 'btnRemove')

                ldtp.click('dlgManageRepositories', 'btnClose')

                ldtp.waittillguiexist('frmPackageManager')

                # Verify result
                self.pkg('publisher | grep %s' % repo_name, exit=1)

                # Quit Package Manager
                ldtp.selectmenuitem('frmPackageManager', 'mnuQuit')
