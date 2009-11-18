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

                # Verify that compatibility commands for publisher work (only
                # minimal verification is needed since these commands map
                # directly to the publisher ones).  All of these are deprecated
                # and will be removed at a future date.
                self.pkg("authority test2")
                self.pkg("set-authority --no-refresh -O http://%s2 test1" %
                    self.bogus_url)
                self.pkg("unset-authority test1")

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
                self.pkg("set-publisher --no-refresh -k %s test2" % key_path,
                    exit=1)

                self.pkg("set-publisher --no-refresh -c %s test1" % cert_path)
                os.close(cert_fh)
                os.unlink(cert_path)
                self.pkg("set-publisher --no-refresh -c %s test2" % cert_path,
                    exit=1)

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
                self.image_create(durl, prefix="test")

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

        def test_missing_perms(self):
                """Bug 2393"""
                durl = self.dc.get_depot_url()
                self.image_create(durl, prefix="test")

                self.pkg("set-publisher --no-refresh -O http://%s1 test1" %
                    self.bogus_url, su_wrap=True, exit=1)
                self.pkg("set-publisher --no-refresh -O http://%s1 foo" %
                    self.bogus_url)
                self.pkg("publisher | grep foo")
                self.pkg("set-publisher -P --no-refresh -O http://%s2 test2" %
                    self.bogus_url, su_wrap=True, exit=1)
                self.pkg("unset-publisher foo", su_wrap=True, exit=1)
                self.pkg("unset-publisher foo")

                self.pkg("set-publisher -m http://%s1 test" % self.bogus_url, \
                    su_wrap=True, exit=1)
                self.pkg("set-publisher -m http://%s2 test" %
                    self.bogus_url)

                self.pkg("set-publisher -M http://%s2 test" %
                    self.bogus_url, su_wrap=True, exit=1)
                self.pkg("set-publisher -M http://%s2 test" %
                    self.bogus_url)

                # Now change the first publisher to a https URL so that
                # certificate failure cases can be tested.
                key_fh, key_path = tempfile.mkstemp(dir=self.get_test_prefix())
                cert_fh, cert_path = tempfile.mkstemp(
                    dir=self.get_test_prefix())

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


class TestPkgPublisherMany(testutils.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_depot = True

        foo1 = """
            open foo@1,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            close """

        baz1 = """
            open baz@1,5.11-0
            close """

        def setUp(self):
                testutils.ManyDepotTestCase.setUp(self, ["test1", "test2", "test3", 
                    "test1", "test1"])

                durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(durl1, self.foo1)

                durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(durl2, self.bar1)

                durl3 = self.dcs[3].get_depot_url()
                self.pkgsend_bulk(durl3, self.baz1)

                self.image_create(durl1, prefix="test1")
                self.pkg("set-publisher -O " + durl2 + " test2")
                self.pkg("set-publisher -O " + durl3 + " test3")

        def tearDown(self):
                testutils.ManyDepotTestCase.tearDown(self)

        def __test_mirror_origin(self, etype, add_opt, remove_opt):
                durl1 = self.dcs[1].get_depot_url()
                durl3 = self.dcs[3].get_depot_url()
                durl4 = self.dcs[4].get_depot_url()

                # Test single add.
                self.pkg("set-publisher %s http://%s1 test1" % (add_opt,
                    self.bogus_url))
                self.pkg("set-publisher %s http://%s2 test1" % (add_opt,
                    self.bogus_url))
                self.pkg("set-publisher %s http://%s5" % (add_opt,
                    self.bogus_url), exit=2)
                self.pkg("set-publisher %s test1" % add_opt, exit=2)
                self.pkg("set-publisher %s http://%s1 test1" % (add_opt,
                    self.bogus_url), exit=1)
                self.pkg("set-publisher %s http://%s5 test11" % (add_opt,
                    self.bogus_url), exit=1)
                self.pkg("set-publisher %s %s7 test1" % (add_opt,
                    self.bogus_url), exit=1)

                # Test single remove.
                self.pkg("set-publisher %s http://%s1 test1" % (remove_opt,
                    self.bogus_url))
                self.pkg("set-publisher %s http://%s2 test1" % (remove_opt,
                    self.bogus_url))
                self.pkg("set-publisher %s test11 http://%s2 http://%s4" % (
                    remove_opt, self.bogus_url, self.bogus_url), exit=2)
                self.pkg("set-publisher %s http://%s5" % (remove_opt,
                    self.bogus_url), exit=2)
                self.pkg("set-publisher %s test1" % remove_opt, exit=2)
                self.pkg("set-publisher %s http://%s5 test11" % (remove_opt,
                    self.bogus_url), exit=1)
                self.pkg("set-publisher %s http://%s6 test1" % (remove_opt,
                    self.bogus_url), exit=1)
                self.pkg("set-publisher %s %s7 test1" % (remove_opt,
                    self.bogus_url), exit=1)

                # Test a combined add and remove.
                self.pkg("set-publisher %s %s test1" % (add_opt, durl3))
                self.pkg("set-publisher %s %s %s %s test1" % (add_opt, durl4,
                    remove_opt, durl3))
                self.pkg("publisher | grep %s.*%s" % (etype, durl4))
                self.pkg("publisher | grep %s.*%s" % (etype, durl3), exit=1)
                self.pkg("set-publisher %s %s test1" % (remove_opt, durl4))

                # Verify that if one of multiple URLs is not a valid URL, pkg
                # will exit with an error, and does not add the valid one.
                self.pkg("set-publisher %s %s %s http://b^^^/ogus test1" % (
                    add_opt, durl3, add_opt), exit=1)
                self.pkg("publisher | grep %s.*%s" % (etype, durl3), exit=1)

                # Verify that multiple can be added at one time.
                self.pkg("set-publisher %s %s %s %s test1" % (add_opt, durl3,
                    add_opt, durl4))
                self.pkg("publisher | grep %s.*%s" % (etype, durl3))
                self.pkg("publisher | grep %s.*%s" % (etype, durl4))

                # Verify that multiple can be removed at one time.
                self.pkg("set-publisher %s %s %s %s test1" % (remove_opt, durl3,
                    remove_opt, durl4))
                self.pkg("publisher | grep %s.*%s" % (etype, durl3), exit=1)
                self.pkg("publisher | grep %s.*%s" % (etype, durl4), exit=1)

        def test_set_mirrors_origins(self):
                """Test set-publisher functionality for mirrors and origins."""
                durl1 = self.dcs[1].get_depot_url()
                durl3 = self.dcs[3].get_depot_url()
                durl4 = self.dcs[4].get_depot_url()
                self.image_create(durl1, prefix="test1")

                # Test short options for mirrors.
                self.__test_mirror_origin("mirror", "-m", "-M")

                # Test long options for mirrors.
                self.__test_mirror_origin("mirror", "--add-mirror",
                    "--remove-mirror")

                # Test short options for origins.
                self.__test_mirror_origin("origin", "-g", "-G")

                # Test long options for origins.
                self.__test_mirror_origin("origin", "--add-origin",
                    "--remove-origin")

                # Finally, verify that if multiple origins are present that -O
                # will discard all others.
                self.pkg("set-publisher -g %s -g %s test1" % (durl3, durl4))
                self.pkg("set-publisher -O %s test1" % durl4)
                self.pkg("publisher | grep origin.*%s" % durl1, exit=1)
                self.pkg("publisher | grep origin.*%s" % durl3, exit=1)

        def test_enable_disable(self):
                """Test enable and disable."""

                self.pkg("publisher")
                self.pkg("publisher | grep test1")
                self.pkg("publisher | grep test2")

                self.pkg("set-publisher -d test2")
                self.pkg("publisher | grep test2") # always show
                self.pkg("publisher -n | grep test2", exit=1) # unless -n

                self.pkg("list -a bar", exit=1)
                self.pkg("publisher -a | grep test2")
                self.pkg("set-publisher -P test2", exit=1)
                self.pkg("publisher test2")
                self.pkg("set-publisher -e test2")
                self.pkg("publisher | grep test2")
                self.pkg("list -a bar")

                self.pkg("set-publisher --disable test2")
                self.pkg("publisher | grep test2")
                self.pkg("publisher -n | grep test2", exit=1)
                self.pkg("list -a bar", exit=1)
                self.pkg("publisher -a | grep test2")
                self.pkg("set-publisher --enable test2")
                self.pkg("publisher | grep test2")
                self.pkg("list -a bar")

                # should fail because test is the preferred publisher
                self.pkg("set-publisher -d test1", exit=1)
                self.pkg("set-publisher --disable test1", exit=1)

        def test_search_order(self):
                """Test moving search order around"""
                # following should be order from above test
                self.pkg("publisher") # ease debugging
                self.pkg("publisher -H | head -1 | egrep test1")
                self.pkg("publisher -H | head -2 | egrep test2")
                self.pkg("publisher -H | head -3 | egrep test3")
                # make test2 disabled, make sure order is preserved                
                self.pkg("set-publisher --disable test2")
                self.pkg("publisher") # ease debugging
                self.pkg("publisher -H | head -1 | egrep test1")
                self.pkg("publisher -H | head -2 | egrep test2")
                self.pkg("publisher -H | head -3 | egrep test3")
                self.pkg("set-publisher --enable test2")
                # make test3 preferred
                self.pkg("set-publisher -P test3")
                self.pkg("publisher") # ease debugging
                self.pkg("publisher -H | head -1 | egrep test3")
                self.pkg("publisher -H | head -2 | egrep test1")
                self.pkg("publisher -H | head -3 | egrep test2")
                # move test3 after test1
                self.pkg("set-publisher --search-after=test1 test3")
                self.pkg("publisher") # ease debugging              
                self.pkg("publisher -H | head -1 | egrep test1")
                self.pkg("publisher -H | head -2 | egrep test3")
                self.pkg("publisher -H | head -3 | egrep test2")
                # move test2 before test3
                self.pkg("set-publisher --search-before=test3 test2")
                self.pkg("publisher") # ease debugging              
                self.pkg("publisher -H | head -1 | egrep test1")
                self.pkg("publisher -H | head -2 | egrep test2")
                self.pkg("publisher -H | head -3 | egrep test3")
                # make sure we cannot get ahead or behind of ourselves
                self.pkg("set-publisher --search-before=test3 test3", exit=1)
                self.pkg("set-publisher --search-after=test3 test3", exit=1)

if __name__ == "__main__":
        unittest.main()
