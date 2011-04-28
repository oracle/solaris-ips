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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.fmri as fmri
import pkg.publish.transaction as trans
import urlparse
import urllib

class TestPkgPublicationApi(pkg5unittest.SingleDepotTestCase):
        """Various publication tests."""

        # Restart the depot and recreate the repository every test.
        persistent_setup = False

        def setUp(self):
                # This test suite needs an actual depot.
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)

        def test_stress_http_publish(self):
                """Publish lots of packages rapidly ensuring that http
                publication can handle it."""

                durl = self.dc.get_depot_url()
                repouriobj = publisher.RepositoryURI(durl)
                repo = publisher.Repository(origins=[repouriobj])
                pub = publisher.Publisher(prefix="repo1", repository=repo)
                xport_cfg = transport.GenericTransportCfg()
                xport_cfg.add_publisher(pub)
                xport = transport.Transport(xport_cfg)

                # Each version number must be unique since multiple packages
                # will be published within the same second.
                for i in range(100):
                        pf = fmri.PkgFmri("foo@%d.0" % i, "5.11")
                        t = trans.Transaction(durl, pkg_name=str(pf),
                            xport=xport, pub=pub)
                        t.open()
                        pkg_fmri, pkg_state = t.close()
                        self.debug("%s: %s" % (pkg_fmri, pkg_state))

        def test_stress_file_publish(self):
                """Publish lots of packages rapidly ensuring that file
                publication can handle it."""

                location = self.dc.get_repodir()
                location = os.path.abspath(location)
                location = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(location), "", "", ""))

                repouriobj = publisher.RepositoryURI(location)
                repo = publisher.Repository(origins=[repouriobj])
                pub = publisher.Publisher(prefix="repo1", repository=repo)
                xport_cfg = transport.GenericTransportCfg()
                xport_cfg.add_publisher(pub)
                xport = transport.Transport(xport_cfg)

                # Each version number must be unique since multiple packages
                # will be published within the same second.
                for i in range(100):
                        pf = fmri.PkgFmri("foo@%d.0" % i, "5.11")
                        t = trans.Transaction(location, pkg_name=str(pf),
                            xport=xport, pub=pub)
                        t.open()
                        pkg_fmri, pkg_state = t.close()
                        self.debug("%s: %s" % (pkg_fmri, pkg_state))


if __name__ == "__main__":
        unittest.main()
