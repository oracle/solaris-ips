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

import unittest
import os
import tempfile

class TestPkgPublisherBasics(testutils.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        def test_pkg_publisher_bogus_opts(self):
                """ pkg bogus option checks """

                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-publisher -@ test3", exit=2)
                self.pkg("publisher -@ test5", exit=2)
                self.pkg("set-publisher -k", exit=2)
                self.pkg("set-publisher -c", exit=2)
                self.pkg("set-publisher -O", exit=2)
                self.pkg("unset-publisher", exit=2)

        def test_publisher_add_remove(self):
                """pkg: add and remove a publisher"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-publisher -O http://%s1 test1" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher --no-refresh -O http://%s1 test1" %
                    self.bogus_url)
                self.pkg("publisher | grep test")
                self.pkg("set-publisher -P -O http://%s2 test2" %
                    self.bogus_url, exit=1)
                self.pkg("set-publisher -P --no-refresh -O http://%s2 test2" %
                    self.bogus_url)
                self.pkg("publisher | grep test2")
                self.pkg("unset-publisher test1")
                self.pkg("publisher | grep test1", exit=1)

                # Now verify that partial success (3) or complete failure (1)
                # is properly returned if an attempt to remove one or more
                # publishers only results in some of them being removed:

                # ...when one of two provided is unknown.
                self.pkg("set-publisher --no-refresh -O http://%s2 test3" %
                    self.bogus_url)
                self.pkg("unset-publisher test3 test4", exit=3)

                # ...when one of two provided is preferred (test2).
                self.pkg("set-publisher --no-refresh -O http://%s2 test3" %
                    self.bogus_url)
                self.pkg("unset-publisher test2 test3", exit=3)

                # ...when all provided are unknown.
                self.pkg("unset-publisher test3 test4", exit=1)
                self.pkg("unset-publisher test3", exit=1)

                # ...when all provided are preferred.
                self.pkg("unset-publisher test2", exit=1)

                # Now verify that success occurs when attempting to remove
                # one or more publishers:

                # ...when one is provided and not preferred.
                self.pkg("set-publisher --no-refresh -O http://%s2 test3" %
                    self.bogus_url)
                self.pkg("unset-publisher test3")

                # ...when two are provided and not preferred.
                self.pkg("set-publisher --no-refresh -O http://%s2 test3" %
                    self.bogus_url)
                self.pkg("set-publisher --no-refresh -O http://%s2 test4" %
                    self.bogus_url)
                self.pkg("unset-publisher test3 test4")

        def test_publisher_uuid(self):
                """verify uuid is set manually and automatically for a
                publisher"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                self.pkg("set-publisher -O http://%s1 --no-refresh --reset-uuid test1" %
                    self.bogus_url)
                self.pkg("set-publisher --no-refresh --reset-uuid test1")
                self.pkg("set-publisher -O http://%s1 --no-refresh test2" %
                    self.bogus_url)
                self.pkg("publisher test2 | grep 'Client UUID: '")
                self.pkg("publisher test2 | grep -v 'Client UUID: None'")

        def test_publisher_bad_opts(self):
                """pkg: more insidious option abuse for set-publisher"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                key_fh, key_path = tempfile.mkstemp()
                cert_fh, cert_path = tempfile.mkstemp()

                self.pkg(
                    "set-publisher -O http://%s1 test1 -O http://%s2 test2" %
                    (self.bogus_url, self.bogus_url), exit=2)

                self.pkg("set-publisher -O http://%s1 test1" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher -O http://%s2 test2" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher --no-refresh -O https://%s1 test1" %
                    self.bogus_url)
                self.pkg("set-publisher --no-refresh -O http://%s2 test2" %
                    self.bogus_url)

                self.pkg("set-publisher --no-refresh -k %s test1" % key_path)
                os.close(key_fh)
                os.unlink(key_path)
                self.pkg("set-publisher --no-refresh -k %s test2" % key_path, exit=1)

                self.pkg("set-publisher --no-refresh -c %s test1" % cert_path)
                os.close(cert_fh)
                os.unlink(cert_path)
                self.pkg("set-publisher --no-refresh -c %s test2" % cert_path, exit=1)

                self.pkg("publisher test1")
                self.pkg("publisher test3", exit=1)
                self.pkg("publisher -H | grep URI", exit=1)

                # Now verify that setting ssl_cert or ssl_key to "" works.
                self.pkg('set-publisher --no-refresh -c "" test1')
                self.pkg('publisher -H test1 | grep "SSL Cert: None"')

                self.pkg('set-publisher --no-refresh -k "" test1')
                self.pkg('publisher -H test1 | grep "SSL Key: None"')

        def test_publisher_validation(self):
                """Verify that we catch poorly formed auth prefixes and URL"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)

                self.pkg("set-publisher -O http://%s1 test1" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher --no-refresh -O http://%s1 test1" %
                    self.bogus_url)

                self.pkg(("set-publisher -O http://%s2 " % self.bogus_url) +
                    "$%^8", exit=1)
                self.pkg(("set-publisher -O http://%s2 " % self.bogus_url) +
                    "8^$%", exit=1)
                self.pkg("set-publisher -O http://*^5$% test2", exit=1)
                self.pkg("set-publisher -O http://%s1:abcde test2" %
                    self.bogus_url, exit=1)
                self.pkg("set-publisher -O ftp://%s2 test2" % self.bogus_url,
                    exit=1)

        def test_mirror(self):
                """Test set-mirror and unset-mirror."""
                durl = self.dc.get_depot_url()
                pfx = "mtest"
                self.image_create(durl, prefix = pfx)

                self.pkg("set-publisher -m http://%s1 mtest" % self.bogus_url)
                self.pkg("set-publisher -m http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-publisher -m http://%s5" % self.bogus_url, exit=2)
                self.pkg("set-publisher -m mtest", exit=2)
                self.pkg("set-publisher -m http://%s1 mtest" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher -m http://%s5 test" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher -m %s7 mtest" % self.bogus_url, exit=1)

                self.pkg("set-publisher -M http://%s1 mtest" % self.bogus_url)
                self.pkg("set-publisher -M http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-publisher -M mtest http://%s2 http://%s4" %
                    (self.bogus_url, self.bogus_url), exit=2)
                self.pkg("set-publisher -M http://%s5" % self.bogus_url, exit=2)
                self.pkg("set-publisher -M mtest", exit=2)
                self.pkg("set-publisher -M http://%s5 test" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher -M http://%s6 mtest" % self.bogus_url,
                    exit=1)
                self.pkg("set-publisher -M %s7 mtest" % self.bogus_url, exit=1)

        def test_missing_perms(self):
                """Bug 2393"""
                durl = self.dc.get_depot_url()
                pfx = "mtest"
                self.image_create(durl, prefix=pfx)

                self.pkg("set-publisher --no-refresh -O http://%s1 test1" %
                    self.bogus_url, su_wrap=True, exit=1)
                self.pkg("set-publisher --no-refresh -O http://%s1 foo" %
                    self.bogus_url)
                self.pkg("publisher | grep foo")
                self.pkg("set-publisher -P --no-refresh -O http://%s2 test2" %
                    self.bogus_url, su_wrap=True, exit=1)
                self.pkg("unset-publisher foo", su_wrap=True, exit=1)
                self.pkg("unset-publisher foo")

                self.pkg("set-publisher -m http://%s1 mtest" % self.bogus_url, \
                    su_wrap=True, exit=1)
                self.pkg("set-publisher -m http://%s2 mtest" %
                    self.bogus_url)

                self.pkg("set-publisher -M http://%s2 mtest" %
                    self.bogus_url, su_wrap=True, exit=1)
                self.pkg("set-publisher -M http://%s2 mtest" %
                    self.bogus_url)

                # Now change the first publisher to a https URL so that
                # certificate failure cases can be tested.
                key_fh, key_path = tempfile.mkstemp(dir=self.get_test_prefix())
                cert_fh, cert_path = tempfile.mkstemp(dir=self.get_test_prefix())

                self.pkg("set-publisher --no-refresh -O https://%s1 test1" %
                    self.bogus_url)
                self.pkg("set-publisher --no-refresh -c %s test1" % cert_path)
                self.pkg("set-publisher --no-refresh -k %s test1" % key_path)

                os.close(key_fh)
                os.close(cert_fh)

                # Make the cert/key unreadable by unprivileged users.
                os.chmod(key_path, 0000)
                os.chmod(cert_path, 0000)

                # Verify that an unreadable/invalid certificate results in a
                # partial failure when displaying publisher information.
                self.pkg("publisher test1", exit=3)
                self.pkg("publisher test1", su_wrap=True, exit=3)

        def test_mirror_longopt(self):
                """Test set-mirror and unset-mirror."""
                durl = self.dc.get_depot_url()
                pfx = "mtest"
                self.image_create(durl, prefix = pfx)

                self.pkg("set-publisher --add-mirror=http://%s1 mtest" %
                    self.bogus_url)
                self.pkg("set-publisher --add-mirror=http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-publisher --add-mirror=http://%s5" %
                    self.bogus_url, exit=2)
                self.pkg("set-publisher --add-mirror=mtest", exit=2)
                self.pkg("set-publisher --add-mirror=http://%s1 mtest" %
                    self.bogus_url, exit=1)
                self.pkg("set-publisher --add-mirror=http://%s5 test" %
                    self.bogus_url, exit=1)
                self.pkg("set-publisher --add-mirror=%s7 mtest" %
                    self.bogus_url, exit=1)

                self.pkg("set-publisher --remove-mirror=http://%s1 mtest" %
                    self.bogus_url)
                self.pkg("set-publisher --remove-mirror=http://%s2 mtest" %
                    self.bogus_url)
                self.pkg("set-publisher --remove-mirror=mtest http://%s2 http://%s4" %
                    (self.bogus_url, self.bogus_url), exit=2)
                self.pkg("set-publisher --remove-mirror=http://%s5" %
                    self.bogus_url, exit=2)
                self.pkg("set-publisher --remove-mirror=mtest", exit=2)
                self.pkg("set-publisher --remove-mirror=http://%s5 test" %
                    self.bogus_url, exit=1)
                self.pkg("set-publisher --remove-mirror=http://%s6 mtest" %
                    self.bogus_url, exit=1)
                self.pkg("set-publisher --remove-mirror=%s7 mtest" %
                    self.bogus_url, exit=1)


class TestPkgPublisherMany(testutils.ManyDepotTestCase):
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
                self.pkg("set-publisher -O " + durl2 + " test2")

        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)

        def test_enable_disable(self):
                """Test enable and disable."""

                self.pkg("publisher | grep test1")
                self.pkg("publisher | grep test2")

                self.pkg("set-publisher -d test2")
                self.pkg("publisher | grep test2", exit=1)
                self.pkg("list -a bar", exit=1)
                self.pkg("publisher -a | grep test2")
                self.pkg("set-publisher -P test2", exit=1)
                self.pkg("publisher test2")
                self.pkg("set-publisher -e test2")
                self.pkg("publisher | grep test2")
                self.pkg("list -a bar")

                self.pkg("set-publisher --disable test2")
                self.pkg("publisher | grep test2", exit=1)
                self.pkg("list -a bar", exit=1)
                self.pkg("publisher -a | grep test2")
                self.pkg("set-publisher --enable test2")
                self.pkg("publisher | grep test2")
                self.pkg("list -a bar")

                # should fail because test is the preferred publisher
                self.pkg("set-publisher -d test1", exit=1)
                self.pkg("set-publisher --disable test1", exit=1)

if __name__ == "__main__":
        unittest.main()
