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

# Copyright (c) 2011, Oracle and/or its affiliates. All rights reserved.

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os.path
import os
import platform
import shutil
import unittest

class TestImporter(pkg5unittest.SingleDepotTestCase):
        """Tests perform basic sanity checking of importer.py."""
        persistent_setup = False

        def setUp(self):

                pkg5unittest.ManyDepotTestCase.setUp(self,
                    ["opensolaris.org"], start_depots=True)

                self.repo_uri = self.dcs[1].get_depot_url()

                self.packages_path = "%s/../../packages/%s" % \
                    (pkg5unittest.g_proto_area, platform.processor())

                self.skip_test = False
                self.svr4_path = os.path.join(self.packages_path, "svr4")
                self.repo_path = os.path.join(self.packages_path, "repo")

                self.repo_path = os.path.abspath(self.repo_path)
                self.svr4_path = os.path.abspath(self.svr4_path)
                if not os.path.exists(self.svr4_path):
                        self.skip_test = True

                test_relative = os.path.sep.join(
                    ["..", "..", "src", "tests", "distro-import"])
                test_src = os.path.join(pkg5unittest.g_proto_area,
                    test_relative)
                self.data_dir = os.path.join(test_src, "data")


        def test_importer_basics(self):
                """Test some very basic functionality of importer.py.
                This imports two SVR4 packages from our gate, a dummy group
                package depending on these, entire and solaris_re-incorporation.
                """

                if self.skip_test:
                        raise pkg5unittest.TestSkippedException(
                            "%s does not exist" % self.svr4_path)

                cluster_file = os.path.join(self.data_dir, "pkg5test_cluster")

                saved_cwd = os.getcwd()
                os.chdir(self.data_dir)
		args = ["-b 0.162", "-s %s" % self.repo_uri,
                    "-w %s" % self.svr4_path,
                    "-R file://%s@consolidation/ips/ips-incorporation" %
                    self.repo_path, cluster_file ]

                retcode, stdout, stderr = \
                    self.importer(args=args, out=True, stderr=True, exit=0)
                dep_err = ("package/pkg: unresolved dependency depend fmri=none"
                    " importer.depsource=lib/svc/manifest/application/pkg/pkg-server.xml"
                    " importer.file=lib/svc/manifest/milestone/network.xml "
                    "type=require: suggest None")
                self.assert_(dep_err in stdout, "Unable to find expected "
                    "dependency error in importer output")

                os.chdir(saved_cwd)
                tmp = os.path.join(self.test_root, "pkgrecv-importer-dest")
                os.mkdir(tmp)

                # verify we can pkgrecv all packages we have imported
                pkg_list = ("package/pkg entire system/zones/brand/ipkg "
                "consolidation/solaris_re/solaris_re-incorporation "
                "pkg5test_install")

                self.pkgrecv(server_url=self.repo_uri,
                    command="-a -d %s/archive.p5p %s" % (tmp, pkg_list))

                # Verify we can retrieve package contents of a package, and
                # ensure the org.opensolaris.smf.fmri value is set
                # (since this came from an SVR4 package, the only thing that
                # would have added this, is the importer)
                self.pkg_image_create(self.repo_uri, "opensolaris.org")
                ret, stdout = self.pkg("contents -rm package/pkg", out=True,
                    exit=0)
                self.assert_("org.opensolaris.smf.fmri" in stdout,
                    "Expected package contents to include SMF FMRI attribute")
                shutil.rmtree(tmp)


        def test_importer_failures(self):
                """Test that the importer fails when it should when encountering
                duplicate actions, and duplicate variants.
                """

                if self.skip_test:
                        raise pkg5unittest.TestSkippedException(
                            "%s does not exist" % self.svr4_path)

                os.chdir(self.data_dir)

                for f in ["pkg5test_dup_variants_cluster",
                    "pkg5test_dup_actions_cluster"]:
                        cluster_file = os.path.join(self.data_dir, f)

                        args = ["-b 0.162", "-s %s" % self.repo_uri,
                            "-w %s" % self.svr4_path,
                            "-R file://%s@consolidation/ips/ips-incorporation" %
                            self.repo_path, cluster_file ]

                        retcode, out, stderr = \
                            self.importer(args=args, out=True, stderr=True,
                                exit=1)

if __name__ == "__main__":
        unittest.main()
