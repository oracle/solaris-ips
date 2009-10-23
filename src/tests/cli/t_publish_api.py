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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import os
import pkg.fmri as fmri
import pkg.publish.transaction as trans
import urlparse
import urllib

class TestPkgPublicationApi(testutils.SingleDepotTestCase):
        """Various publication tests."""

        # Restart the depot and recreate the repository every test.
        persistent_depot = False

        def test_stress_http_publish(self):
                """Publish lots of packages rapidly ensuring that http
                publication can handle it."""

                durl = self.dc.get_depot_url()

                # Each version number must be unique since multiple packages
                # will be published within the same second.
                for i in range(100):
                        pf = fmri.PkgFmri("foo@%d.0" % i, "5.11")
                        t = trans.Transaction(durl, pkg_name=str(pf))
                        t.open()
                        pkg_fmri, pkg_state = t.close(refresh_index=True)
                        self.debug("%s: %s" % (pkg_fmri, pkg_state))

        def test_stress_file_publish(self):
                """Publish lots of packages rapidly ensuring that file
                publication can handle it."""

                location = self.dc.get_repodir()
                location = os.path.abspath(location)
                location = urlparse.urlunparse(("file", "",
                    urllib.pathname2url(location), "", "", ""))

                # Each version number must be unique since multiple packages
                # will be published within the same second.
                for i in range(100):
                        pf = fmri.PkgFmri("foo@%d.0" % i, "5.11")
                        t = trans.Transaction(location, pkg_name=str(pf))
                        t.open()
                        pkg_fmri, pkg_state = t.close(refresh_index=True)
                        self.debug("%s: %s" % (pkg_fmri, pkg_state))

