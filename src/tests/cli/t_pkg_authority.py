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

import unittest
import os
import tempfile

class TestPkgAuthorityBasics(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_pkg_authority_bogus_opts(self):
                """ pkg bogus option checks """

                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-authority -@ test3", exit=2)
                self.pkg("authority -@ test5", exit=2)
                self.pkg("set-authority -k", exit=2)
                self.pkg("set-authority -c", exit=2)
                self.pkg("set-authority -O", exit=2)
                self.pkg("unset-authority", exit=2)

        def test_authority_add_remove(self):
                """pkg: add and remove an authority"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-authority -O http://%s1 test1" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority --no-refresh -O http://%s1 test1" %
                    self.bogus_url)
                self.pkg("authority | grep test")
                self.pkg("set-authority -P -O http://%s2 test2" %
                    self.bogus_url, exit=1)
                self.pkg("set-authority -P --no-refresh -O http://%s2 test2" %
                    self.bogus_url)
                self.pkg("authority | grep test2")
                self.pkg("unset-authority test1")
                self.pkg("authority | grep test1", exit=1)
                self.pkg("unset-authority test2", exit=1)

        def test_authority_uuid(self):
                """pkg: set the uuid for an authority"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("set-authority -O http://%s1 --no-refresh --reset-uuid test1" %
                    self.bogus_url)
                self.pkg("set-authority --no-refresh --reset-uuid test1")

        def test_authority_bad_opts(self):
                """pkg: more insidious option abuse for set-authority"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                key_fh, key_path = tempfile.mkstemp()
                cert_fh, cert_path = tempfile.mkstemp()

                self.pkg(
                    "set-authority -O http://%s1 test1 -O http://%s2 test2" %
                    (self.bogus_url, self.bogus_url), exit=2)

                self.pkg("set-authority -O http://%s1 test1" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority -O http://%s2 test2" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority --no-refresh -O http://%s1 test1" %
                    self.bogus_url)
                self.pkg("set-authority --no-refresh -O http://%s2 test2" %
                    self.bogus_url)

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

        def test_authority_validation(self):
                """Verify that we catch poorly formed auth prefixes and URL"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-authority -O http://%s1 test1" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority --no-refresh -O http://%s1 test1" %
                    self.bogus_url)

                self.pkg(("set-authority -O http://%s2 " % self.bogus_url) +
                    "$%^8", exit=1)
                self.pkg(("set-authority -O http://%s2 " % self.bogus_url) +
                    "8^$%", exit=1)
                self.pkg("set-authority -O http://*^5$% test2", exit=1)
                self.pkg("set-authority -O http://%s1:abcde test2" %
                    self.bogus_url, exit=1)
                self.pkg("set-authority -O ftp://%s2 test2" % self.bogus_url,
                    exit=1)

        def test_mirror(self):
                """Test set-mirror and unset-mirror."""
                durl = self.dc.get_depot_url()
                pfx = "mtest"
                self.image_create(durl, prefix = pfx)

                self.pkg("set-authority -m http://%s1 mtest" % self.bogus_url)
                self.pkg("set-authority -m http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-authority -m http://%s5" % self.bogus_url, exit=2)
                self.pkg("set-authority -m mtest", exit=2)
                self.pkg("set-authority -m http://%s1 mtest" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority -m http://%s5 test" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority -m %s7 mtest" % self.bogus_url, exit=1)

                self.pkg("set-authority -M http://%s1 mtest" % self.bogus_url)
                self.pkg("set-authority -M http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-authority -M mtest http://%s2 http://%s4" %
                    (self.bogus_url, self.bogus_url), exit=2)
                self.pkg("set-authority -M http://%s5" % self.bogus_url, exit=2)
                self.pkg("set-authority -M mtest", exit=2)
                self.pkg("set-authority -M http://%s5 test" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority -M http://%s6 mtest" % self.bogus_url,
                    exit=1)
                self.pkg("set-authority -M %s7 mtest" % self.bogus_url, exit=1)

        def test_missing_perms(self):
                """Bug 2393"""
                durl = self.dc.get_depot_url()
                pfx = "mtest"
                self.image_create(durl, prefix=pfx)

                self.pkg("set-authority --no-refresh -O http://%s1 test1" %
                    self.bogus_url, su_wrap="noaccess", exit=1)
                self.pkg("set-authority --no-refresh -O http://%s1 foo" %
                    self.bogus_url)
                self.pkg("authority | grep foo")
                self.pkg("set-authority -P --no-refresh -O http://%s2 test2" %
                    self.bogus_url, su_wrap="noaccess", exit=1)
                self.pkg("unset-authority foo", su_wrap="noaccess", exit=1)
                self.pkg("unset-authority foo")

                self.pkg("set-authority -m http://%s1 mtest" % self.bogus_url, \
                    su_wrap="noaccess", exit=1)
                self.pkg("set-authority -m http://%s2 mtest" %
                    self.bogus_url)

                self.pkg("set-authority -M http://%s2 mtest" %
                    self.bogus_url, su_wrap="noaccess", exit=1)
                self.pkg("set-authority -M http://%s2 mtest" %
                    self.bogus_url)

        def test_mirror_longopt(self):
                """Test set-mirror and unset-mirror."""
                durl = self.dc.get_depot_url()
                pfx = "mtest"
                self.image_create(durl, prefix = pfx)

                self.pkg("set-authority --add-mirror=http://%s1 mtest" %
                    self.bogus_url)
                self.pkg("set-authority --add-mirror=http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-authority --add-mirror=http://%s5" %
                    self.bogus_url, exit=2)
                self.pkg("set-authority --add-mirror=mtest", exit=2)
                self.pkg("set-authority --add-mirror=http://%s1 mtest" %
                    self.bogus_url, exit=1)
                self.pkg("set-authority --add-mirror=http://%s5 test" %
                    self.bogus_url, exit=1)
                self.pkg("set-authority --add-mirror=%s7 mtest" %
                    self.bogus_url, exit=1)

                self.pkg("set-authority --remove-mirror=http://%s1 mtest" %
                    self.bogus_url)
                self.pkg("set-authority --remove-mirror=http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-authority --remove-mirror=mtest http://%s2 http://%s4" %
                    (self.bogus_url, self.bogus_url), exit=2)
                self.pkg("set-authority --remove-mirror=http://%s5" %
                    self.bogus_url, exit=2)
                self.pkg("set-authority --remove-mirror=mtest", exit=2)
                self.pkg("set-authority --remove-mirror=http://%s5 test" %
                    self.bogus_url, exit=1)
                self.pkg("set-authority --remove-mirror=http://%s6 mtest" %
                    self.bogus_url, exit=1)
                self.pkg("set-authority --remove-mirror=%s7 mtest" %
                    self.bogus_url, exit=1)

class TestPkgAuthorityMany(testutils.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        foo1 = """
            open foo@1,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, 2)

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1)

                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.bar1)

                self.image_create(durl1, prefix = "test1")
                self.pkg("set-authority -O " + durl2 + " test2")

        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)

        def test_enable_disable(self):
                """Test enable and disable."""

                self.pkg("authority | grep test1")
                self.pkg("authority | grep test2")

                self.pkg("set-authority -d test2")
                self.pkg("authority | grep test2", exit=1)
                self.pkg("list -a bar", exit=1)
                self.pkg("authority -a | grep test2")
                self.pkg("set-authority -P test2", exit=1)
                self.pkg("authority test2")
                self.pkg("set-authority -e test2")
                self.pkg("authority | grep test2")
                self.pkg("list -a bar")

                self.pkg("set-authority --disable test2")
                self.pkg("authority | grep test2", exit=1)
                self.pkg("list -a bar", exit=1)
                self.pkg("authority -a | grep test2")
                self.pkg("set-authority --enable test2")
                self.pkg("authority | grep test2")
                self.pkg("list -a bar")

                # should fail because test is the preferred authority
                self.pkg("set-authority -d test1", exit=1)
                self.pkg("set-authority --disable test1", exit=1)

if __name__ == "__main__":
        unittest.main()
