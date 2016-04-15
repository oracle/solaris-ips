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
# Copyright (c) 2008, 2016, Oracle and/or its affiliates. All rights reserved.
#

from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import hashlib
import os
import pkg.client.image as image
import pkg.misc
import shutil
import six
import tempfile
import unittest


class TestPkgPublisherBasics(pkg5unittest.SingleDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        # Dummy package
        foo1 = """
            open foo@1,5.11-0
            close """

        def setUp(self):
                # This test suite needs actual depots.
                pkg5unittest.SingleDepotTestCase.setUp(self, start_depot=True)

                self.durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(self.durl1, self.foo1)

        def test_pkg_publisher_bogus_opts(self):
                """ pkg bogus option checks """

                self.image_create(self.rurl)

                self.pkg("set-publisher -@ test3", exit=2)
                self.pkg("publisher -@ test5", exit=2)
                self.pkg("set-publisher -k", exit=2)
                self.pkg("set-publisher -c", exit=2)
                self.pkg("set-publisher -O", exit=2)
                self.pkg("unset-publisher", exit=2)
                self.pkg("unset-publisher -k", exit=2)

        def test_publisher_add_remove(self):
                """pkg: add and remove a publisher"""

                self.image_create(self.rurl)

                self.pkg("set-publisher -O http://{0}1 test1".format(self.bogus_url),
                    exit=1)

                # Verify that a publisher can be added initially disabled.
                self.pkg("set-publisher -d --no-refresh -O http://{0}1 test1".format(
                    self.bogus_url))

                self.pkg("publisher | grep test")
                self.pkg("set-publisher -P -O http://{0}2 test2".format(
                    self.bogus_url), exit=1)
                self.pkg("set-publisher -P --no-refresh -O http://{0}2 test2".format(
                    self.bogus_url))
                self.pkg("publisher | grep test2")
                self.pkg("unset-publisher test1")
                self.pkg("publisher | grep test1", exit=1)

                # Now verify that partial success (3) or complete failure (1)
                # is properly returned if an attempt to remove one or more
                # publishers only results in some of them being removed:

                # ...when one of two provided is unknown.
                self.pkg("set-publisher --no-refresh -O http://{0}2 test3".format(
                    self.bogus_url))
                self.pkg("unset-publisher test3 test4", exit=3)

                # ...when all provided are unknown.
                self.pkg("unset-publisher test3 test4", exit=1)
                self.pkg("unset-publisher test3", exit=1)

                # Now verify that success occurs when attempting to remove
                # one or more publishers:

                # ...when one is provided and not preferred.
                self.pkg("set-publisher --no-refresh -O http://{0}2 test3".format(
                    self.bogus_url))
                self.pkg("unset-publisher test3")

                # ...when two are provided and not preferred.
                self.pkg("set-publisher --no-refresh -O http://{0}2 test3".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh -O http://{0}2 test4".format(
                    self.bogus_url))
                self.pkg("unset-publisher test3 test4")

                # Ensure that some package manifests are cached for the
                # publisher.
                self.pkg("info -r '//test/*'")

                # Now verify that success occurs when attempting to remove a
                # publisher that has already had its private directory removed
                # from $IMG_DIR/pkg.
                api_inst = self.get_img_api_obj()
                pub = api_inst.get_publisher(prefix="test")
                self.assertTrue(os.path.exists(pub.meta_root))
                pub.remove_meta_root()
                self.assertTrue(not os.path.exists(pub.meta_root))

                pub_cache_path = os.path.join(self.img_path(), "var", "pkg",
                    "cache", "publisher", "test")
                self.assertTrue(os.path.exists(pub_cache_path),
                    os.listdir(os.path.join(self.img_path(), "var", "pkg",
                    "cache", "publisher")))
                shutil.rmtree(pub_cache_path)
                self.assertTrue(not os.path.exists(pub_cache_path))

                self.pkg("unset-publisher test")

        def test_publisher_uuid(self):
                """verify uuid is set manually and automatically for a
                publisher"""

                self.image_create(self.rurl)
                self.pkg("set-publisher -O http://{0}1 --no-refresh --reset-uuid test1".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh --reset-uuid test1")
                self.pkg("set-publisher -O http://{0}1 --no-refresh test2".format(
                    self.bogus_url))
                self.pkg("publisher test2 | grep 'Client UUID: '")
                self.pkg("publisher test2 | grep -v 'Client UUID: None'")

        def test_publisher_bad_opts(self):
                """pkg: more insidious option abuse for set-publisher"""

                self.image_create(self.rurl)

                key_path = os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem")
                cert_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")

                self.pkg(
                    "set-publisher -O http://{0}1 test1 -O http://{1}2 test2".format(
                    self.bogus_url, self.bogus_url), exit=2)

                self.pkg("set-publisher -O http://{0}1 test1".format(self.bogus_url),
                    exit=1)
                self.pkg("set-publisher -O http://{0}2 test2".format(self.bogus_url),
                    exit=1)
                self.pkg("set-publisher --no-refresh -O https://{0}1 test1".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh -O http://{0}2 test2".format(
                    self.bogus_url))

                # Set key for test1.
                self.pkg("set-publisher --no-refresh -k {0} test1".format(key_path))

                # This should fail since test2 doesn't have any SSL origins or
                # mirrors.
                self.pkg("set-publisher --no-refresh -k {0} test2".format(key_path),
                    exit=2)

                # Listing publishers should succeed even if key file is gone.
                # This test relies on using the same implementation used in
                # image.py __store_publisher_ssl() which sets the paths to the
                # SSL keys/certs.
                img_key_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(key_path,
                    hash_func=hashlib.sha1)[0])
                os.unlink(img_key_path)
                self.pkg("publisher test1")

                # This should fail since key has been removed even though test2
                # has an https origin.
                self.pkg("set-publisher --no-refresh -O https://{0}2 test2".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh -k {0} test2".format(
                    img_key_path), exit=1)

                # Reset for next test.
                self.pkg("set-publisher --no-refresh -k '' test1")
                self.pkg("set-publisher --no-refresh -O http://{0}2 test2".format(
                    self.bogus_url))

                # Set cert for test1.
                self.pkg("set-publisher --no-refresh -c {0} test1".format(cert_path))

                # This should fail since test2 doesn't have any SSL origins or
                # mirrors.
                self.pkg("set-publisher --no-refresh -c {0} test2".format(cert_path),
                    exit=2)

                # Listing publishers should be possible if cert file is gone.
                img_cert_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(cert_path,
                    hash_func=hashlib.sha1)[0])
                os.unlink(img_cert_path)
                self.pkg("publisher test1", exit=3)

                # This should fail since cert has been removed even though test2
                # has an https origin.
                self.pkg("set-publisher --no-refresh -O https://{0}2 test2".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh -c {0} test2".format(
                    img_cert_path), exit=1)

                # Reset for next test.
                self.pkg("set-publisher --no-refresh -O http://{0}2 test2".format(
                    self.bogus_url))

                # Expect partial failure since cert file is gone for test1.
                self.pkg("publisher test1", exit=3)
                self.pkg("publisher test3", exit=1)
                self.pkg("publisher -H | grep URI", exit=1)

                # Now verify that setting ssl_cert or ssl_key to "" works.
                self.pkg('set-publisher --no-refresh -c "" test1')
                self.pkg('publisher -H test1 | grep "SSL Cert: None"')

                self.pkg('set-publisher --no-refresh -k "" test1')
                self.pkg('publisher -H test1 | grep "SSL Key: None"')

                self.pkg("set-publisher --set-property foo test1", exit=2)
                self.pkg("set-publisher --set-property foo=bar --set-property "
                    "foo=baz test1", exit=2)
                self.pkg("set-publisher --add-property-value foo test1", exit=2)
                self.pkg("set-publisher --remove-property-value foo test1",
                    exit=2)
                self.pkg("set-publisher --approve-ca-cert /shouldnotexist/foo "
                    "test1", exit=1)

                key_fh, key_path = tempfile.mkstemp()
                self.pkg("set-publisher --approve-ca-cert {0} test1".format(key_path),
                    exit=1, su_wrap=True)
                os.unlink(key_path)

                self.pkg("set-publisher --no-refresh --set-property "
                    "signature-policy=ignore test1")
                self.pkg("publisher test1")
                self.assertTrue("signature-policy = ignore" in self.output)
                self.pkg("set-publisher --no-refresh --set-property foo=bar "
                    "test1")
                self.pkg("publisher test1")
                self.assertTrue("foo = bar" in self.output)
                self.pkg("set-publisher --no-refresh  --remove-property-value "
                    "foo=baz test1", exit=1)
                self.pkg("publisher test1")
                self.assertTrue("foo = bar" in self.output)
                self.pkg("set-publisher --no-refresh  --set-property "
                    "signature-policy=require-names test1", exit=1)
                self.pkg("set-publisher --no-refresh --remove-property-value "
                    "bar=baz test1", exit=1)

                self.pkg("publisher")
                self.pkg("set-publisher --no-refresh --search-after foo test1",
                    exit=1)
                self.pkg("set-publisher --no-refresh --search-before foo test1",
                    exit=1)

        def test_publisher_validation(self):
                """Verify that we catch poorly formed auth prefixes and URL"""

                self.image_create(self.rurl, prefix="test")

                self.pkg("set-publisher -O http://{0}1 test1".format(self.bogus_url),
                    exit=1)
                self.pkg("set-publisher --no-refresh -O http://{0}1 test1".format(
                    self.bogus_url))

                self.pkg(("set-publisher -O http://{0}2 ".format(self.bogus_url)) +
                    "$%^8", exit=1)
                self.pkg(("set-publisher -O http://{0}2 ".format(self.bogus_url)) +
                    "8^$%", exit=1)
                self.pkg("set-publisher -O http://*^5$% test2", exit=1)
                self.pkg("set-publisher -O http://{0}1:abcde test2".format(
                    self.bogus_url), exit=1)
                self.pkg("set-publisher -O ftp://{0}2 test2".format(self.bogus_url),
                    exit=1)

                # Verify single character in hostname is valid publisher
                self.pkg("set-publisher --no-refresh -g http://a/ a")
                self.pkg("set-publisher --no-refresh -g http://a.example.com " \
                    "a.example.com")

        def test_missing_perms(self):
                """Verify graceful failure if certificates are unreadable by
                unprivileged users."""

                self.image_create(self.rurl, prefix="test")

                self.pkg("set-publisher --no-refresh -O http://{0}1 test1".format(
                    self.bogus_url), su_wrap=True, exit=1)
                self.pkg("set-publisher --no-refresh -O http://{0}1 foo".format(
                    self.bogus_url))
                self.pkg("publisher | grep foo")
                self.pkg("set-publisher -P --no-refresh -O http://{0}2 test2".format(
                    self.bogus_url), su_wrap=True, exit=1)
                self.pkg("unset-publisher foo", su_wrap=True, exit=1)
                self.pkg("unset-publisher foo")

                self.pkg("set-publisher -m http://{0}1 test".format(self.bogus_url),
                    su_wrap=True, exit=1)
                self.pkg("set-publisher -m http://{0}2 test".format(
                    self.bogus_url))

                self.pkg("set-publisher -M http://{0}2 test".format(
                    self.bogus_url), su_wrap=True, exit=1)
                self.pkg("set-publisher -M http://{0}2 test".format(
                    self.bogus_url))

                # Now change the first publisher to a https URL so that
                # certificate failure cases can be tested.
                key_path = os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem")
                cert_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")

                self.pkg("set-publisher --no-refresh -O https://{0}1 test1".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh -c {0} test1".format(cert_path))
                self.pkg("set-publisher --no-refresh -k {0} test1".format(key_path))

                # This test relies on using the same implementation used in
                # image.py __store_publisher_ssl() which sets the paths to the
                # SSL keys/certs.
                img_key_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(key_path,
                    hash_func=hashlib.sha1)[0])
                img_cert_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(cert_path,
                    hash_func=hashlib.sha1)[0])

                # Make the cert/key unreadable by unprivileged users.
                os.chmod(img_key_path, 0000)
                os.chmod(img_cert_path, 0000)

                # Verify that an unreadable certificate results in a
                # partial failure when displaying publisher information.
                self.pkg("publisher test1", su_wrap=True, exit=3)

                # Corrupt key/cert and verify invalid cert/key results in a
                # partial failure when displaying publisher information.
                open(img_key_path, "wb").close()
                open(img_cert_path, "wb").close()
                self.pkg("publisher test1", exit=3)

        def test_publisher_tsv_format(self):
                """Ensure tsv formatted output is correct."""

                self.image_create(self.rurl)

                self.pkg("set-publisher --no-refresh -O https://{0}1 test1".format(
                    self.bogus_url))
                self.pkg("set-publisher --no-refresh -O http://{0}2 test2".format(
                    self.bogus_url))

                base_string = ("test\ttrue\tfalse\ttrue\torigin\tonline\t"
                    "{0}/\t-\n"
                    "test1\ttrue\tfalse\ttrue\torigin\tonline\t"
                    "https://{1}1/\t-\n"
                    "test2\ttrue\tfalse\ttrue\torigin\tonline\t"
                    "http://{2}2/\t-\n".format(self.rurl, self.bogus_url,
                    self.bogus_url))
                # With headers
                self.pkg("publisher -F tsv")
                expected = "PUBLISHER\tSTICKY\tSYSPUB\tENABLED" \
                    "\tTYPE\tSTATUS\tURI\tPROXY\n" + base_string
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

                # Without headers
                self.pkg("publisher -HF tsv")
                expected = base_string
                output = self.reduceSpaces(self.output)
                self.assertEqualDiff(expected, output)

        def test_old_publisher_ca_certs(self):
                """Check that approving and revoking CA certs is reflected in
                the output of pkg publisher and that setting the CA certs when
                setting an existing publisher works correctly."""

                cert_dir = os.path.join(self.ro_data_root,
                    "signing_certs", "produced", "chain_certs")

                app1 = os.path.join(cert_dir, "ch1_ta1_cert.pem")
                app2 = os.path.join(cert_dir, "ch1_ta3_cert.pem")
                rev1 = os.path.join(cert_dir, "ch1_ta4_cert.pem")
                rev2 = os.path.join(cert_dir, "ch1_ta5_cert.pem")
                app1_h = self.calc_pem_hash(app1)
                app2_h = self.calc_pem_hash(app2)
                rev1_h = self.calc_pem_hash(rev1)
                rev2_h = self.calc_pem_hash(rev2)
                self.image_create(self.rurl)
                self.pkg("set-publisher "
                    "--approve-ca-cert {0} "
                    "--approve-ca-cert {1} --revoke-ca-cert {2} "
                    "--revoke-ca-cert {3} test ".format(
                    app1, app2, rev1_h, rev2_h))
                self.pkg("publisher test")
                r1 = "         Approved CAs: {0}"
                r2 = "                     : {0}"
                r3 = "          Revoked CAs: {0}"
                ls = self.output.splitlines()
                found_approved = False
                found_revoked = False
                for i in range(0, len(ls)):
                        if "Approved CAs" in ls[i]:
                                found_approved = True
                                if not ((r1.format(app1_h) == ls[i] and
                                    r2.format(app2_h) == ls[i+1] or \
                                    (r1.format(app2_h) == ls[i]) and
                                    r2.format(app1_h) == ls[i+1])):
                                        raise RuntimeError("Expected to see "
                                            "{0} and {1} as approved certs. "
                                            "Output was:\n{2}".format(app1_h,
                                            app2_h, self.output))
                        elif "Revoked CAs" in ls[i]:
                                found_approved = True
                                if not ((r3.format(rev1_h) == ls[i] and
                                    r2.format(rev2_h) == ls[i+1]) or \
                                    (r3.format(rev2_h) == ls[i] and
                                    r2.format(rev1_h) == ls[i+1])):
                                        raise RuntimeError("Expected to see "
                                            "{0} and {1} as revoked certs. "
                                            "Output was:\n{2}".format(rev1_h,
                                            rev2_h, self.output))

        def test_publisher_properties(self):
                """Test that properties set on publishers are correctly
                displayed in the output of pkg publisher <publisher name>."""

                self.image_create(self.rurl)
                self.pkg("publisher test")
                self.assertTrue("Properties:" not in self.output)

                self.pkg("set-publisher --set-property foo=bar test")
                self.pkg("publisher test")
                self.assertTrue("Properties:" in self.output)
                self.assertTrue("foo = bar" in self.output)
                self.pkg("set-publisher --add-property-value foo=bar1 test",
                    exit=1)

                self.pkg("set-publisher --set-property "
                    "signature-policy=require-names --add-property-value "
                    "signature-required-names=n1 test")
                self.pkg("publisher test")
                self.assertTrue("signature-policy = require-names" in self.output)
                self.assertTrue("signature-required-names = n1" in self.output)

                self.pkg("set-publisher --add-property-value "
                    "signature-required-names=n2 test")
                self.pkg("publisher test")
                self.assertTrue("signature-required-names = n1, n2" in self.output)

        def test_bug_7141684(self):
                """Test that pkg(1) client does not traceback if no publisher
                configured and we try to get preferred publisher"""

                self.image_create()
                self.pkg("publisher -P", exit=0)

                self.pkg("set-publisher -g {0} test".format(self.durl1))
                self.pkg("install foo")
                self.pkg("unset-publisher test")
                self.pkg("publisher -P", exit=0)

        def test_publisher_proxies(self):
                """Tests that set-publisher can add and remove proxy values
                per origin."""

                self.image_create(self.rurl)
                self.pkg("publisher test")
                self.assertTrue("Proxy:" not in self.output)

                # check origin and mirror addition/removal when proxies are used
                for add, remove in [("-g", "-G"), ("-m", "-M")]:
                        self.image_create(self.rurl)
                        # we can't proxy file repositories
                        self.pkg("set-publisher --no-refresh {add} {url} "
                            "--proxy http://foo test".format(
                            add=add, url=self.rurl), exit=1)
                        self.pkg("publisher test")
                        self.assertTrue("Proxy:" not in self.output)

                        # we can set the proxy for http repos
                        self.pkg("set-publisher --no-refresh {add} {url} "
                            "--proxy http://foo test".format(
                            add=add, url=self.durl))

                        self.pkg("publisher test")
                        self.assertTrue("Proxy: http://foo" in self.output)

                        # remove the file-based repository and ensure we still
                        # have a proxied http-based publisher
                        self.pkg("set-publisher --no-refresh -G {0} test".format(
                            self.rurl))
                        self.pkg("publisher -F tsv")
                        self.assertTrue("{0}/\thttp://foo".format(
                            self.durl in self.output))
                        self.assertTrue(self.rurl not in self.output)

                        # ensure we can't add duplicate proxied or unproxied
                        # repositories
                        self.pkg("set-publisher --no-refresh {add} {url} "
                            "--proxy http://foo test".format(
                            add=add, url=self.durl), exit=1)
                        self.pkg("set-publisher --no-refresh {add} {url} "
                            "test".format(add=add, url=self.durl), exit=1)

                        # we should have 1 proxied occurrence of our http url
                        self.pkg("publisher -F tsv")
                        self.assertTrue("{0}/\thttp://foo".format(
                            self.durl in self.output))
                        self.assertTrue("\t\t{0}".format(self.durl not in self.output))

                        # when removing a proxied url, then adding the same url
                        # unproxied, the proxy configuration does get removed
                        self.pkg("set-publisher --no-refresh {remove} {url}"
                            " test".format(remove=remove, url=self.durl),
                            exit=0)
                        self.pkg("set-publisher --no-refresh {add} {url} "
                            "test".format(add=add, url=self.durl), exit=0)
                        self.pkg("publisher -F tsv")
                        self.assertTrue("{0}/\thttp://foo".format(
                            self.durl not in self.output))
                        self.pkg("set-publisher --no-refresh {remove} "
                            "{url} test".format(
                            remove=remove, url=self.durl))

                        # when we add multiple urls, and they all get the same
                        # proxy value, leaving an existing non-proxied url
                        # as non-proxied.
                        self.pkg("set-publisher --no-refresh {add} http://a "
                            "test".format(add=add))
                        self.pkg("set-publisher --no-refresh {add} http://b "
                            "{add} http://c --proxy http://foo test".format(
                            add=add))
                        self.pkg("publisher -F tsv")
                        self.assertTrue("http://a/\t-" in self.output)
                        self.assertTrue("http://b/\thttp://foo" in self.output)
                        self.assertTrue("http://c/\thttp://foo" in self.output)

        def test_publisher_special_repo_name(self):
                """Tests that set-publisher can use the repository name with
                special characters."""

                self.image_create()

                # "%" is a special character in SafeConfigParser, but needs
                # to be supported anyway.
                repo_dir = os.path.join(self.test_root, "repotest{0}ymbol")
                self.create_repo(repo_dir, properties={ "publisher": {
                    "prefix": "test1" } })
                self.pkg("set-publisher -p {0} test1".format(repo_dir))
                shutil.rmtree(repo_dir)

                # "+" will be converted into "%2B" by URL quoting routines.
                # "%" is a special character in SafeConfigParser, but we need
                # to support it here.
                repo_dir = os.path.join(self.test_root, "repotest+symbol")
                self.create_repo(repo_dir, properties={ "publisher": {
                    "prefix": "test2" } })
                self.pkg("set-publisher -g {0} test2".format(repo_dir))
                shutil.rmtree(repo_dir)

                # "%()" is the syntax of expansion language in SafeConfigParser
                # but needs to be raw characters here.
                repo_dir = os.path.join(self.test_root, "{junkrepo}")
                self.create_repo(repo_dir, properties={ "publisher": {
                    "prefix": "test3" } })
                self.pkg("set-publisher -g {0} test3".format(repo_dir))
                shutil.rmtree(repo_dir)

        def test_remove_unused_cert_key(self):
                """Ensure that unused client certificate files are removed."""

                self.image_create(self.rurl)

                # Set the first publisher to a https URL
                key_path = os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem")
                cert_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")

                img_key_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(key_path,
                    hash_func=hashlib.sha1)[0])
                img_cert_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(cert_path,
                    hash_func=hashlib.sha1)[0])

                self.pkg("set-publisher --no-refresh -O https://{0} -c {1} \
                    -k {2} test1" .format(self.bogus_url, cert_path, key_path))

                # cert and key should exist
                self.assertTrue(os.path.exists(img_key_path))
                self.assertTrue(os.path.exists(img_cert_path))

                # Now change test1 to http URL to check whether
                # certificate and key are removed
                self.pkg("set-publisher --no-refresh -O http://{0} \
                    test1".format(self.bogus_url))

                # cert and key should not exist.
                self.assertTrue(not os.path.exists(img_key_path))
                self.assertTrue(not os.path.exists(img_cert_path))

                # Now test if cert and key is still in use
                # we should not remove them
                self.pkg("set-publisher --no-refresh -O https://{0} -c {1} \
                    -k {2} test1".format(self.bogus_url, cert_path, key_path))

                self.pkg("set-publisher --no-refresh -O https://{0} -c {1} \
                    -k {2} foo".format(self.bogus_url, cert_path, key_path))

                # cert and key should exist
                self.assertTrue(os.path.exists(img_key_path))
                self.assertTrue(os.path.exists(img_cert_path))

                # Remove ssl for test1
                self.pkg("set-publisher --no-refresh -O http://{0} \
                    foo".format(self.bogus_url))

                # cert and key should still exist.
                self.assertTrue(os.path.exists(img_key_path))
                self.assertTrue(os.path.exists(img_cert_path))

                # Test unset-publisher
                self.pkg("set-publisher --no-refresh -O https://{0} -c {1} \
                    -k {2} foo".format(self.bogus_url, cert_path, key_path))

                # cert and key should exist.
                self.assertTrue(os.path.exists(img_key_path))
                self.assertTrue(os.path.exists(img_cert_path))

                self.pkg("unset-publisher foo")
                # cert and key should still exist.
                self.assertTrue(os.path.exists(img_key_path))
                self.assertTrue(os.path.exists(img_cert_path))

                self.pkg("unset-publisher test1")
                # cert and key should not exist.
                self.assertTrue(not os.path.exists(img_key_path))
                self.assertTrue(not os.path.exists(img_cert_path))


class TestPkgPublisherMany(pkg5unittest.ManyDepotTestCase):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        foo1 = """
            open foo@1,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            close """

        baz1 = """
            open baz@1,5.11-0
            close """

        test3_pub_cfg = {
            "publisher": {
                "alias": "t3",
                "prefix": "test3",
            },
            "repository": {
                "collection_type": "supplemental",
                "description": "This repository serves packages for test3.",
                "legal_uris": [
                    "http://www.opensolaris.org/os/copyrights",
                    "http://www.opensolaris.org/os/tou",
                    "http://www.opensolaris.org/os/trademark"
                ],
                "name": "The Test3 Repository",
                "refresh_seconds": 86400,
                "registration_uri": "",
                "related_uris": [
                    "http://pkg.opensolaris.org/contrib",
                    "http://jucr.opensolaris.org/pending",
                    "http://jucr.opensolaris.org/contrib"
                ],
            },
        }

        def setUp(self):
                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test3",  "test1", "test1", "test3"], start_depots=True)

                self.durl1 = self.dcs[1].get_depot_url()
                self.pkgsend_bulk(self.durl1, self.foo1)

                self.durl2 = self.dcs[2].get_depot_url()
                self.pkgsend_bulk(self.durl2, self.bar1)

                self.durl3 = self.dcs[3].get_depot_url()
                self.pkgsend_bulk(self.durl3, self.baz1)

                self.image_create(self.durl1, prefix="test1")
                self.pkg("set-publisher -O " + self.durl2 + " test2")
                self.pkg("set-publisher -O " + self.durl3 + " test3")

        def __test_mirror_origin(self, etype, add_opt, remove_opt):
                durl1 = self.dcs[1].get_depot_url()
                durl4 = self.dcs[4].get_depot_url()
                durl5 = self.dcs[5].get_depot_url()

                # Test single add; --no-refresh must be used here since the URI
                # being added is for a non-existent repository.
                self.pkg("set-publisher --no-refresh {0} http://{1}1 test1".format(
                    add_opt, self.bogus_url))
                self.pkg("set-publisher --no-refresh {0} http://{1}2 test1".format(
                    add_opt, self.bogus_url))
                self.pkg("set-publisher --no-refresh {0} http://{1}5".format(add_opt,
                    self.bogus_url), exit=2)
                self.pkg("set-publisher {0} test1".format(add_opt), exit=2)
                self.pkg("set-publisher --no-refresh {0} http://{1}1 test1".format(
                    add_opt, self.bogus_url), exit=1)
                self.pkg("set-publisher {0} http://{1}5 test11".format(add_opt,
                    self.bogus_url), exit=1)
                if etype == "origin":
                        self.pkg("set-publisher {0} {1}7 test1".format(
                            add_opt, self.bogus_url), exit=1)

                # Test single remove.
                self.pkg("set-publisher --no-refresh {0} http://{1}1 test1".format(
                    remove_opt, self.bogus_url))
                self.pkg("set-publisher --no-refresh {0} http://{1}2 test1".format(
                    remove_opt, self.bogus_url))
                # URIs to remove not specified using options, so they are seen
                # as publisher names -- only one publisher name may be
                # specified at a time.
                self.pkg("set-publisher {0} test11 http://{1}2 http://{2}4".format(
                    remove_opt, self.bogus_url, self.bogus_url), exit=2)
                self.pkg("set-publisher {0} http://{1}5".format(remove_opt,
                    self.bogus_url), exit=2)
                # publisher name specified to remove as URI.
                self.pkg("set-publisher {0} test1".format(remove_opt), exit=2)
                # URI already removed or never existed.
                self.pkg("set-publisher {0} http://{1}5 test11".format(remove_opt,
                    self.bogus_url), exit=1)
                self.pkg("set-publisher {0} http://{1}6 test1".format(remove_opt,
                    self.bogus_url), exit=1)
                self.pkg("set-publisher {0} {1}7 test1".format(remove_opt,
                    self.bogus_url), exit=1)

                # Test a combined add and remove.
                self.pkg("set-publisher {0} {1} test1".format(add_opt, durl4))
                self.pkg("set-publisher {0} {1} {2} {3} test1".format(add_opt, durl5,
                    remove_opt, durl4))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl5))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl4), exit=1)
                self.pkg("set-publisher {0} {1} test1".format(remove_opt, durl5))
                self.pkg("set-publisher {0} {1} {2} {3} {4} \* test1".format(add_opt,
                    durl4, add_opt, durl5, remove_opt))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl4))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl5))
                self.pkg("set-publisher {0} \* test1".format(remove_opt))
                if etype == "origin":
                        self.pkg("set-publisher {0} {1} test1".format(add_opt, durl1))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl4), exit=1)
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl5), exit=1)

                # Verify that if one of multiple URLs is not a valid URL, pkg
                # will exit with an error, and does not add the valid one.
                self.pkg("set-publisher {0} {1} {2} http://b^^^/ogus test1".format(
                    add_opt, durl4, add_opt), exit=1)
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl4), exit=1)

                # Verify that multiple can be added at one time.
                self.pkg("set-publisher {0} {1} {2} {3} test1".format(add_opt, durl4,
                    add_opt, durl5))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl4))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl5))

                # Verify that multiple can be removed at one time.
                self.pkg("set-publisher {0} {1} {2} {3} test1".format(remove_opt, durl4,
                    remove_opt, durl5))
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl4), exit=1)
                self.pkg("publisher | grep {0}.*{1}".format(etype, durl5), exit=1)

        def __verify_pub_cfg(self, prefix, pub_cfg):
                """Private helper method to verify publisher configuration."""

                # pretend like the Image object is being allocated from
                # a pkg command run from within the target image.
                cmdpath = os.path.join(self.get_img_path(), "pkg")

                img = image.Image(self.get_img_path(), should_exist=True,
                    user_provided_dir=True, cmdpath=cmdpath)
                pub = img.get_publisher(prefix=prefix)
                for section in pub_cfg:
                        for prop, val in six.iteritems(pub_cfg[section]):
                                if section == "publisher":
                                        pub_val = getattr(pub, prop)
                                else:
                                        pub_val = getattr(
                                            pub.repository, prop)

                                if prop in ("legal_uris", "mirrors", "origins",
                                    "related_uris"):
                                        # The publisher will have these as lists,
                                        # so transform both sets of data first
                                        # for reliable comparison.  Remove any
                                        # trailing slashes so comparison can
                                        # succeed.
                                        if not val:
                                                val = set()
                                        else:
                                                val = set(val)
                                        new_pub_val = set()
                                        for u in pub_val:
                                                uri = u.uri
                                                if uri.endswith("/"):
                                                        uri = uri[:-1]
                                                new_pub_val.add(uri)
                                        pub_val = new_pub_val
                                self.assertEqual(val, pub_val)

        def __update_repo_pub_cfg(self, dc, pubcfg):
                """Private helper method to update a repository's publisher
                configuration based on the provided dictionary structure."""

                rpath = dc.get_repodir()
                props = ""
                for sname in pubcfg:
                        for pname, pval in six.iteritems(pubcfg[sname]):
                                if sname == "publisher" and pname == "prefix":
                                        continue
                                pname = pname.replace("_", "-")
                                if isinstance(pval, list):
                                        props += "{0}/{1}='({2})' ".format(
                                            sname, pname, " ".join(pval))
                                else:
                                        props += "{0}/{1}='{2}' ".format(
                                            sname, pname, pval)

                pfx = pubcfg["publisher"]["prefix"]
                self.pkgrepo("set -s {0} -p {1} {2}".format(rpath, pfx, props))
                self.pkgrepo("get -p all -s {0}".format(rpath))

        def test_set_auto(self):
                """Verify that set-publisher -p works as expected."""

                # Test the single add/update case first.
                durl1 = self.dcs[1].get_depot_url()
                durl3 = self.dcs[3].get_depot_url()
                durl4 = self.dcs[4].get_depot_url()
                self.image_create(durl1, prefix="test1")

                # Should fail because test3 publisher does not exist.
                self.pkg("publisher test3", exit=1)

                # Should fail because repository is for test3 not test2.
                self.pkg("set-publisher -p {0} test2".format(durl3), exit=1)

                # Verify that a publisher can be configured even if the
                # the repository's publisher configuration does not
                # include origin information.  In this case, the client
                # will assume that the provided repository URI for
                # auto-configuration is also the origin to use for
                # all configured publishers.
                t3cfg = {
                    "publisher": {
                        "prefix": "test3",
                    },
                    "repository": {
                        "origins": [durl3],
                    },
                }
                self.pkg("set-publisher -p {0}".format(durl3))

                # Load image configuration to verify publisher was configured
                # as expected.
                self.__verify_pub_cfg("test3", t3cfg)

                # Update configuration of just this depot with more information
                # for comparison basis.
                self.dcs[3].stop()

                # Origin and mirror info wasn't known until this point, so add
                # it to the test configuration.
                t3cfg = self.test3_pub_cfg.copy()
                t3cfg["repository"]["origins"] = [durl3]
                t3cfg["repository"]["mirrors"] = [durl1, durl3, durl4]
                self.__update_repo_pub_cfg(self.dcs[3], t3cfg)
                self.dcs[3].start()

                # Should succeed and configure test3 publisher.
                self.pkg("set-publisher -p {0}".format(durl3))

                # Load image configuration to verify publisher was configured
                # as expected.
                self.__verify_pub_cfg("test3", t3cfg)

                # Now test the update case.  This verifies that the existing,
                # configured origins and mirrors will not be lost (only added
                # to) and that new data will be accepted.
                durl6 = self.dcs[6].get_depot_url()
                self.dcs[6].stop()
                t6cfg = {}
                for section in t3cfg:
                        t6cfg[section] = {}
                        for prop in t3cfg[section]:
                                val = t3cfg[section][prop]
                                if prop == "refresh_seconds":
                                        val = 1800
                                elif prop == "collection_type":
                                        val = "core"
                                elif prop not in ("alias", "prefix"):
                                        # Clear all other props.
                                        val = ""
                                t6cfg[section][prop] = val
                t6cfg["repository"]["origins"] = [durl3, durl6]
                t6cfg["repository"]["mirrors"] = [durl1, durl3, durl4, durl6]
                self.__update_repo_pub_cfg(self.dcs[6], t6cfg)
                self.dcs[6].start()

                self.pkg("set-publisher -p {0}".format(durl6))

                # Load image configuration to verify publisher was configured
                # as expected.
                self.__verify_pub_cfg("test3", t6cfg)

                # Test multi-publisher add case.
                self.pkgrepo("set -s {0} -p test2 publisher/alias=''".format(
                    self.dcs[6].get_repodir()))
                self.pkg("unset-publisher test3")
                self.dcs[6].refresh()
                self.pkg("set-publisher -P -p {0}".format(durl6))

                # Determine publisher order from output and then verify it
                # matches expected.
                def get_pubs():
                        self.pkg("publisher -HF tsv")
                        pubs = []
                        for l in self.output.splitlines():
                                pub, ignored = l.split("\t", 1)
                                if pub not in pubs:
                                        pubs.append(pub)
                        return pubs

                # Since -P was used, new publishers should be set first in
                # search order alphabetically.
                self.assertEqual(get_pubs(), ["test2", "test3", "test1"])

                # Now change search order and verify that using -P and -p again
                # won't change it since publishers already exist.
                self.pkg("set-publisher --search-after=test1 test2")
                self.pkg("set-publisher --search-after=test2 test3")
                self.assertEqual(get_pubs(), ["test1", "test2", "test3"])
                self.pkg("set-publisher -P -p {0}".format(durl6))
                self.assertEqual(get_pubs(), ["test1", "test2", "test3"])

                # Check that --proxy arguments are set on all auto-configured
                # publishers.  We use $no_proxy='*' in the environment so that
                # we can persist a dummy --proxy value to the image
                # configuration, yet still reach the test depot to obtain the
                # publisher/ response.
                self.pkg("unset-publisher test3")
                self.pkg("unset-publisher test2")
                self.pkg("set-publisher -P --proxy http://myproxy -p {0}".format(
                    durl6), env_arg={"no_proxy": "*"})
                self.assertEqual(get_pubs(), ["test2", "test3", "test1"])

                # Verify that only test2 and test3 have proxies set, since
                # test1 already existed, it should not use a proxy. The proxy
                # column is the last one printed on each line.
                self.pkg("publisher -HF tsv")
                for l in self.output.splitlines():
                        if l.startswith("test2") or l.startswith("test3"):
                                self.assertEqual("http://myproxy",
                                    l.split()[-1])
                        else:
                                self.assertEqual("-", l.split()[-1])

        def test_set_mirrors_origins(self):
                """Test set-publisher functionality for mirrors and origins."""

                durl1 = self.dcs[1].get_depot_url()
                rurl1 = self.dcs[1].get_repo_url()
                self.image_create(durl1, prefix="test1")

                # Verify that https origins can be mixed with other types
                # of origins.
                self.pkg("set-publisher -g {0} test1".format(rurl1))
                self.pkg("set-publisher --no-refresh -g https://test.invalid1 "
                    "test1")

                # Verify that a cert and key can be set even when non-https
                # origins are present.
                key_path = os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem")
                cert_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")

                self.pkg("set-publisher --no-refresh -k {0} -c {1} test1".format(
                    key_path, cert_path))
                self.pkg("publisher test1")

                # This test relies on using the same implementation used in
                # image.py __store_publisher_ssl() which sets the paths to the
                # SSL keys/certs.
                img_key_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(key_path,
                    hash_func=hashlib.sha1)[0])
                img_cert_path = os.path.join(self.img_path(), "var", "pkg",
                    "ssl", pkg.misc.get_data_digest(cert_path,
                    hash_func=hashlib.sha1)[0])
                self.assertTrue(img_key_path in self.output)
                self.assertTrue(img_cert_path in self.output)

                # Verify that removing all SSL origins does not leave key
                # and cert information intact.
                self.pkg("set-publisher -G '*' -g {0} test1".format(durl1))
                self.pkg("publisher test1")
                self.assertTrue(img_key_path not in self.output)
                self.assertTrue(img_cert_path not in self.output)

                # Verify that https mirrors can be mixed with other types of
                # origins.
                self.pkg("set-publisher -m {0} test1".format(rurl1))
                self.pkg("set-publisher --no-refresh -m https://test.invalid1 "
                    "test1")
                self.pkg("set-publisher --no-refresh -k {0} -c {1} test1".format(
                    key_path, cert_path))

                # Verify that removing all SSL mirrors does not leave key
                # and cert information intact.
                self.pkg("set-publisher -M '*' -m {0} test1".format(durl1))
                self.pkg("publisher test1")
                self.assertTrue(img_key_path not in self.output)
                self.assertTrue(img_cert_path not in self.output)

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

                # Verify that if multiple origins are present that -O will
                # discard all others.
                durl4 = self.dcs[4].get_depot_url()
                durl5 = self.dcs[5].get_depot_url()
                self.pkg("set-publisher -g {0} -g {1} test1".format(durl4, durl5))
                self.pkg("set-publisher -O {0} test1".format(durl4))
                self.pkg("publisher | grep origin.*{0}".format(durl1), exit=1)
                self.pkg("publisher | grep origin.*{0}".format(durl5), exit=1)

                # Verify that if a publisher is set to use a file repository
                # that removing that repository will not prevent the pkg(1)
                # command from operating or the set-publisher commands
                # from working.
                repo_path = os.path.join(self.test_root, "badrepo")
                repo_uri = "file:{0}".format(repo_path)
                self.create_repo(repo_path, properties={ "publisher": {
                    "prefix": "test1" } })
                self.pkg("set-publisher -O {0} test1".format(repo_uri))
                shutil.rmtree(repo_path)

                self.pkg("publisher")
                self.pkg("set-publisher -O {0} test1".format(
                    self.dcs[1].get_repo_url()))

                # Now verify that publishers using origins or mirrors that have
                # IPv6 addresses can be added and removed.
                self.pkg("set-publisher -g http://[::1] "
                    "-m http://[::FFFF:129.144.52.38]:80 "
                    "-m http://[2010:836B:4179::836B:4179] "
                    "-g http://[FEDC:BA98:7654:3210:FEDC:BA98:7654:3210]:80 "
                    "--no-refresh testipv6")
                self.pkg("publisher | "
                    "grep 'http://\[::FFFF:129.144.52.38\]:80/'")
                self.pkg("set-publisher -G http://[::1] "
                    "-M http://[::FFFF:129.144.52.38]:80 "
                    "-M http://[2010:836B:4179::836B:4179] "
                    "-G http://[FEDC:BA98:7654:3210:FEDC:BA98:7654:3210]:80 "
                    "-g http://[::192.9.5.5]/dev "
                    "--no-refresh testipv6")
                self.pkg("publisher | "
                    "grep 'http://\[::FFFF:129.144.52.38\]:80/'", exit=1)
                self.pkg("unset-publisher testipv6")

        def test_enable_disable(self):
                """Test enable and disable."""

                self.pkg("publisher")
                self.pkg("publisher | grep test1")
                self.pkg("publisher | grep test2")

                self.pkg("set-publisher -d test2")
                self.pkg("publisher | grep test2") # always show
                self.pkg("publisher -n | grep test2", exit=1) # unless -n

                self.pkg("list -a bar", exit=1)
                self.pkg("set-publisher -P test2")
                self.pkg("publisher test2")
                self.pkg("set-publisher -e test2")
                self.pkg("publisher -n | grep test2")
                self.pkg("list -a bar")

                self.pkg("set-publisher --disable test2")
                self.pkg("publisher | grep test2")
                self.pkg("publisher -n | grep test2", exit=1)
                self.pkg("list -a bar", exit=1)
                self.pkg("set-publisher --enable test2")
                self.pkg("publisher -n | grep test2")
                self.pkg("list -a bar")

        def test_search_order(self):
                """Test moving search order around"""

                # The expected publisher order is test1, test2, test3, with all
                # publishers enabled and sticky.
                self.pkg("set-publisher -e -P test1")
                self.pkg("set-publisher -e --search-after test1 test2")
                self.pkg("set-publisher -e --search-after test2 test3")
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

                # make sure that setting search order while adding a publisher
                # works
                self.pkg("unset-publisher test2")
                self.pkg("unset-publisher test3")
                self.pkg("set-publisher --search-before=test1 test2")
                self.pkg("set-publisher --search-after=test2 test3")
                self.pkg("publisher") # ease debugging
                self.pkg("publisher -H | head -1 | egrep test2")
                self.pkg("publisher -H | head -2 | egrep test3")
                self.pkg("publisher -H | head -3 | egrep test1")

        def test_publishers_only_from_installed_packages(self):
                """Test that get_highest_rank_publisher works when there are
                installed packages but no configured publishers."""

                self.pkg("install foo bar baz")
                self.pkg("unset-publisher test1")
                self.pkg("unset-publisher test2")
                self.pkg("unset-publisher test3")
                self.pkg("publisher")

                # set publishers to expected configuration
                self.pkg("set-publisher -p {0}".format(self.durl1))
                self.pkg("set-publisher -p {0}".format(self.durl2))
                self.pkg("set-publisher -p {0}".format(self.durl3))

        def test_bug_18283(self):
                """Test that having a unset publisher with packages installed
                doesn't break adding a publisher with the -P option."""

                # Test what happens when another publisher is configured.
                self.pkg("unset-publisher test2")
                self.pkg("install foo")
                self.pkg("unset-publisher test1")
                self.pkg("set-publisher -P -p {0}".format(self.durl2))

                # Test what happens when no publishers are configured
                self.pkg("unset-publisher test2")
                self.pkg("unset-publisher test3")
                self.pkg("set-publisher -P -p {0}".format(self.durl2))

                # set publishers to expected configuration
                self.pkg("set-publisher -P -p {0}".format(self.durl1))
                self.pkg("set-publisher -p {0}".format(self.durl3))


class TestMultiPublisherRepo(pkg5unittest.ManyDepotTestCase):

        foo1 = """
            open foo@1,5.11-0
            close """

        bar1 = """
            open bar@1,5.11-0
            close """

        baz1 = """
            open pkg://another-pub/baz@1,5.11-0
            close """


        def setUp(self):
                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.pkgsend_bulk(self.rurl1, self.foo1 + self.baz1)

                self.rurl2 = self.dcs[2].get_repo_url()
                self.pkgsend_bulk(self.rurl2, self.bar1)

        def test_multi_publisher_search_before(self):
                """Test that using search before and -p on a multipublisher
                repository works."""

                self.image_create(self.rurl2)
                self.pkg("set-publisher --search-before test2 -p {0}".format(
                    self.rurl1))
                self.pkg("publisher -HF tsv")
                lines = self.output.splitlines()
                self.assertEqual(lines[0].split()[0], "another-pub")
                self.assertEqual(lines[1].split()[0], "test1")
                self.assertEqual(lines[2].split()[0], "test2")

        def test_multiple_p_option(self):
                """Verify that providing multiple repositories using
                -p option fails"""
                self.image_create()
                self.pkg("set-publisher -p {0} -p {1}".format(self.rurl1,
                    self.rurl2), exit=2)


class TestPkgPublisherCACerts(pkg5unittest.ManyDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        def setUp(self):
                # This test suite needs actual depots.
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2"])

                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.image_create(self.rurl1, prefix="test1")

        def test_new_publisher_ca_certs_with_refresh(self):
                """Check that approving and revoking CA certs is reflected in
                the output of pkg publisher and that setting the CA certs when
                setting a new publisher works correctly."""

                cert_dir = os.path.join(self.ro_data_root,
                    "signing_certs", "produced", "chain_certs")

                app1 = os.path.join(cert_dir, "ch4_ta1_cert.pem")
                app2 = os.path.join(cert_dir, "ch1_ta3_cert.pem")
                rev1 = os.path.join(cert_dir, "ch1_ta4_cert.pem")
                rev2 = os.path.join(cert_dir, "ch1_ta5_cert.pem")
                app1_h = self.calc_pem_hash(app1)
                app2_h = self.calc_pem_hash(app2)
                rev1_h = self.calc_pem_hash(rev1)
                rev2_h = self.calc_pem_hash(rev2)
                self.pkg("set-publisher -O {0} "
                    "--approve-ca-cert {1} "
                    "--approve-ca-cert {2} --revoke-ca-cert {3} "
                    "--revoke-ca-cert {4} test2 ".format(self.dcs[2].get_repo_url(),
                    app1, app2, rev1_h, rev2_h))
                self.pkg("publisher test2")
                r1 = "         Approved CAs: {0}"
                r2 = "                     : {0}"
                r3 = "          Revoked CAs: {0}"
                ls = self.output.splitlines()
                found_approved = False
                found_revoked = False
                for i in range(0, len(ls)):
                        if "Approved CAs" in ls[i]:
                                found_approved = True
                                if not ((r1.format(app1_h) == ls[i] and
                                    r2.format(app2_h) == ls[i+1]) or \
                                    (r1.format(app2_h) == ls[i] and
                                    r2.format(app1_h) == ls[i+1])):
                                        raise RuntimeError("Expected to see "
                                            "{0} and {1} as approved certs. "
                                            "Output was:\n{2}".format(app1_h,
                                            app2_h, self.output))
                        elif "Revoked CAs" in ls[i]:
                                found_approved = True
                                if not ((r3.format(rev1_h) == ls[i] and
                                    r2.format(rev2_h) == ls[i+1]) or \
                                    (r3.format(rev2_h) == ls[i] and
                                    r2.format(rev1_h) == ls[i+1])):
                                        raise RuntimeError("Expected to see "
                                            "{0} and {1} as revoked certs. "
                                            "Output was:\n{2}".format(rev1_h,
                                            rev2_h, self.output))

        def test_new_publisher_ca_certs_no_refresh(self):
                """Check that approving and revoking CA certs is reflected in
                the output of pkg publisher and that setting the CA certs when
                setting a new publisher works correctly."""

                cert_dir = os.path.join(self.ro_data_root,
                    "signing_certs", "produced", "chain_certs")

                app1 = os.path.join(cert_dir, "ch3_ta1_cert.pem")
                app2 = os.path.join(cert_dir, "ch1_ta3_cert.pem")
                rev1 = os.path.join(cert_dir, "ch1_ta4_cert.pem")
                rev2 = os.path.join(cert_dir, "ch1_ta5_cert.pem")
                app1_h = self.calc_pem_hash(app1)
                app2_h = self.calc_pem_hash(app2)
                rev1_h = self.calc_pem_hash(rev1)
                rev2_h = self.calc_pem_hash(rev2)
                self.pkg("set-publisher -O {0} --no-refresh "
                    "--approve-ca-cert {1} "
                    "--approve-ca-cert {2} --revoke-ca-cert {3} "
                    "--revoke-ca-cert {4} test2 ".format(self.dcs[2].get_repo_url(),
                    app1, app2, rev1_h, rev2_h))
                self.pkg("publisher test2")
                r1 = "         Approved CAs: {0}"
                r2 = "                     : {0}"
                r3 = "          Revoked CAs: {0}"
                ls = self.output.splitlines()
                found_approved = False
                found_revoked = False
                for i in range(0, len(ls)):
                        if "Approved CAs" in ls[i]:
                                found_approved = True
                                if not ((r1.format(app1_h) == ls[i] and
                                    r2.format(app2_h) == ls[i+1]) or \
                                    (r1.format(app2_h) == ls[i] and
                                    r2.format(app1_h) == ls[i+1])):
                                        raise RuntimeError("Expected to see "
                                            "{0} and {1} as approved certs. "
                                            "Output was:\n{2}".format(app1_h,
                                            app2_h, self.output))
                        elif "Revoked CAs" in ls[i]:
                                found_approved = True
                                if not ((r3.format(rev1_h) == ls[i] and
                                    r2.format(rev2_h) == ls[i+1]) or \
                                    (r3.format(rev2_h) == ls[i] and
                                    r2.format(rev1_h) == ls[i+1])):
                                        raise RuntimeError("Expected to see "
                                            "{0} and {1} as revoked certs. "
                                            "Output was:\n{2}".format(rev1_h,
                                            rev2_h, self.output))


if __name__ == "__main__":
        unittest.main()
