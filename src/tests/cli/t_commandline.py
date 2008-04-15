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

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")

import unittest
import os
import tempfile

class TestCommandLine(testutils.SingleDepotTestCase):

        def test_pkg_bogus_opts(self):
                """ pkg bogus option checks """

                # create a image to avoid non-existant image messages
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("-@", exit=2)
                self.pkg("list -@", exit=2)
                self.pkg("list -v -s", exit=2)
                self.pkg("contents -@", exit=2)
                self.pkg("image-update -@", exit=2)
                self.pkg("image-create -@", exit=2)
                self.pkg("image-create --bozo", exit=2)
                self.pkg("install -@ foo", exit=2)
                self.pkg("uninstall -@ foo", exit=2)
                self.pkg("set-authority -@ test3", exit=2)
                self.pkg("authority -@ test5", exit=2)

        def test_pkg_vq_1153(self):
                """ test that -v and -q are mutually exclusive """
                self.pkg("verify -vq", exit=2)
                self.pkg("install -vq foo", exit=2)
                self.pkg("uninstall -vq foo", exit=2)
                self.pkg("image-update -vq", exit=2)

        def test_pkg_missing_args(self):
                """ pkg: Lack of needed arguments should yield complaint """
                # create a image to avoid non-existant image messages
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("-s status", exit=2)
                self.pkg("-R status", exit=2)
                self.pkg("contents -o", exit=2)
                self.pkg("contents -s", exit=2)
                self.pkg("contents -t", exit=2)
                self.pkg("set-authority -k", exit=2)
                self.pkg("set-authority -c", exit=2)
                self.pkg("set-authority -O", exit=2)
                self.pkg("unset-authority", exit=2)


        def test_pkgsend_bogus_opts(self):
                """ pkgsend bogus option checks """
                durl = "bogus"
                self.pkgsend(durl, "-@ open foo@1.0,5.11-0", exit=2)
                self.pkgsend(durl, "close -@", exit=2)

        def test_authority_add_remove(self):
                """pkg: add and remove an authority"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-authority -O http://test1 test1")
                self.pkg("authority | grep test")
                self.pkg("set-authority -P -O http://test2 test2")
                self.pkg("authority | grep test2")
                self.pkg("unset-authority test1")
                self.pkg("authority | grep test1", exit=1)
                self.pkg("unset-authority test2", exit=1)

        def test_authority_bad_opts(self):
                """pkg: more insidious option abuse for set-authority"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                key_fh, key_path = tempfile.mkstemp()
                cert_fh, cert_path = tempfile.mkstemp()

                self.pkg(
                    "set-authority -O http://test1 test1 -O http://test2 test2",
                     exit=2)

                self.pkg("set-authority -O http://test1 test1")
                self.pkg("set-authority -O http://test2 test2")

                self.pkg("set-authority -k %s test1" % key_path)
                os.close(key_fh)
                os.unlink(key_path)
                self.pkg("set-authority -k %s test2" % key_path, exit=1)

                self.pkg("set-authority -c %s test1" % cert_path)
                os.close(cert_fh)
                os.unlink(cert_path)
                self.pkg("set-authority -c %s test2" % cert_path, exit=1)

                self.pkg("authority test1")
                self.pkg("authority test3", exit=1)
                self.pkg("authority -H | grep URL", exit=1)


if __name__ == "__main__":
        unittest.main()
