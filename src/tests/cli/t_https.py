#!/usr/bin/python2.7
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
# Copyright (c) 2011, 2015, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import hashlib
import os
import shutil
import six
import stat
import tempfile
import certgenerator

import pkg.misc as misc
import pkg.portable as portable
from pkg.client.debugvalues import DebugValues
from pkg.client.transport.exception import TransportFailures


class TestHTTPS(pkg5unittest.HTTPSTestClass):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        misc_files = ["tmp/example_file"]

        def setUp(self):
                pub1_name = "test"
                pub2_name = "tmp"

                pkg5unittest.HTTPSTestClass.setUp(self, [pub1_name, pub2_name],
                    start_depots=True)
                
                self.rurl1 = self.dcs[1].get_repo_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.tmppub = pub2_name

                self.make_misc_files(self.misc_files)
                self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.acurl1 = self.ac.url + "/{0}".format(pub1_name)
                self.acurl2 = self.ac.url + "/{0}".format(pub2_name)
                # Our proxy is served by the same Apache controller, but uses
                # a different port.
                self.proxyurl = self.ac.url.replace("https", "http")
                self.proxyurl = self.proxyurl.replace(str(self.https_port),
                    str(self.proxy_port))

        def test_01_basics(self):
                """Test that adding a https publisher works and that a package
                can be installed from that publisher."""

                self.ac.start()
                # Test that creating an image using a HTTPS repo without
                # providing any keys or certificates fails.
                self.assertRaises(TransportFailures, self.image_create,
                    self.acurl1)
                self.pkg_image_create(repourl=self.acurl1, exit=1)
                api_obj = self.image_create()

                # Test that adding a HTTPS repo fails if the image does not
                # contain the trust anchor to verify the server's identity.
                self.pkg("set-publisher -k {key} -c {cert} -p {url}".format(
                    url=self.acurl1,
                    cert=os.path.join(self.cs_dir, self.get_cli_cert("test")),
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                   ), exit=1)

                # Add the trust anchor needed to verify the server's identity to
                # the image.
                self.seed_ta_dir("ta7")
                self.pkg("set-publisher -k {key} -c {cert} -p {url}".format(
                    url=self.acurl1,
                    cert=os.path.join(self.cs_dir, self.get_cli_cert("test")),
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                   ))
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

                # Verify that if the image location changes, SSL operations
                # are still possible.  (The paths to key and cert should be
                # updated on load.)
                opath = self.img_path()
                npath = opath.replace("image0", "new.image")
                portable.rename(opath, npath)
                odebug = DebugValues["ssl_ca_file"]
                DebugValues["ssl_ca_file"] = odebug.replace("image0",
                    "new.image")
                self.pkg("-R {0} refresh --full test".format(npath))

                # Listing the test publisher causes its cert and key to be
                # validated.
                self.pkg("-R {0} publisher test".format(npath))
                assert os.path.join("new.image", "var", "pkg", "ssl") in \
                    self.output

                # Restore image to original location.
                portable.rename(npath, opath)
                DebugValues["ssl_ca_file"] = odebug

                # verify that we can reach the repository using a HTTPS-capable
                # HTTP proxy.
                self.image_create()
                self.seed_ta_dir("ta7")
                self.pkg("set-publisher --proxy {proxy} "
                    "-k {key} -c {cert} -p {url}".format(
                    url=self.acurl1,
                    cert=os.path.join(self.cs_dir, self.get_cli_cert("test")),
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                    proxy=self.proxyurl))
                self.pkg("install example_pkg")

                # Now try to use the bad proxy, ensuring that we cannot set
                # the publisher (and verifying that we were indeed using the
                # proxy previously)
                bad_proxyurl = self.proxyurl.replace(str(self.proxy_port),
                    str(self.bad_proxy_port))
                self.image_create()
                self.seed_ta_dir("ta7")
                self.pkg("set-publisher --proxy {proxy} "
                    "-k {key} -c {cert} -p {url}".format(
                    url=self.acurl1,
                    cert=os.path.join(self.cs_dir, self.get_cli_cert("test")),
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                    proxy=bad_proxyurl), exit=1)

                # Set the bad proxy in the image, verify we can't refresh,
                # then use an OS environment override to force the use of a
                # good proxy.
                self.pkg("set-publisher --no-refresh --proxy {proxy} "
                    "-k {key} -c {cert} -g {url} test".format(
                    url=self.acurl1,
                    cert=os.path.join(self.cs_dir, self.get_cli_cert("test")),
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                    proxy=bad_proxyurl), exit=0)
                self.pkg("refresh", exit=1)
                proxy_env = {"https_proxy": self.proxyurl}
                self.pkg("refresh", env_arg=proxy_env)
                self.pkg("install example_pkg", env_arg=proxy_env)

        def test_correct_cert_validation(self):
                """ Test that an expired cert for one publisher doesn't prevent
                making changes to other publishers due to certifcate checks on
                all configured publishers. (Bug 17018362)"""

                bad_cert_path = os.path.join(self.cs_dir,
                    "cs3_ch1_ta3_cert.pem")
                good_cert_path = os.path.join(self.cs_dir,
                    self.get_cli_cert("test"))
                self.ac.start()
                self.image_create()

                # Set https-based publisher with correct cert.
                self.seed_ta_dir("ta7")
                self.pkg("set-publisher -k {key} -c {cert} -p {url}".format(
                    url=self.acurl1,
                    cert=good_cert_path,
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                   ))
                # Set a second publisher
                self.pkg("set-publisher -p {url}".format(url=self.rurl2))

                # Replace cert of first publisher with one that is expired.
                # It doesn't need to match the key because we just want to
                # test if the cert validation code works correctly so we are not
                # actually using the cert.

                # Cert is stored by content hash in the pkg config of the image,
                # which must be a SHA-1 hash for backwards compatibility.
                ch = misc.get_data_digest(good_cert_path,
                    hash_func=hashlib.sha1)[0]
                pkg_cert_path = os.path.join(self.get_img_path(), "var", "pkg",
                    "ssl", ch)
                shutil.copy(bad_cert_path, pkg_cert_path)

                # Refreshing the second publisher should not try to validate
                # the cert for the first publisher.
                self.pkg("refresh {0}".format(self.tmppub))

        def test_expired_certs(self):
                """ Test that certificate validation needs to validate all
                certificates before raising an exception. (Bug 15507548)"""

                bad_cert_path = os.path.join(self.cs_dir,
                    "cs3_ch1_ta3_cert.pem")
                good_cert_path_1 = os.path.join(self.cs_dir,
                    self.get_cli_cert("test"))
                good_cert_path_2 = os.path.join(self.cs_dir,
                    self.get_cli_cert("tmp"))
                self.ac.start()
                self.image_create()

                # Set https-based publisher with correct cert.
                self.seed_ta_dir("ta7")
                self.pkg("set-publisher -k {key} -c {cert} -p {url}".format(
                    url=self.acurl1,
                    cert=good_cert_path_1,
                    key=os.path.join(self.keys_dir, self.get_cli_key("test")),
                   ))
                # Set a second publisher
                self.pkg("set-publisher -k {key} -c {cert} -p {url}".format(
                    url=self.acurl2,
                    cert=good_cert_path_2,
                    key=os.path.join(self.keys_dir, self.get_cli_key("tmp")),
                   ))
 
                # Replace cert of first publisher with one that is expired.

                # Cert is stored by content hash in the pkg config of the image,
                # which must be a SHA-1 hash for backwards compatibility.
                ch = misc.get_data_digest(good_cert_path_1,
                    hash_func=hashlib.sha1)[0]
                pkg_cert_path = os.path.join(self.get_img_path(), "var", "pkg",
                    "ssl", ch)
                shutil.copy(bad_cert_path, pkg_cert_path)

                # Replace the second certificate with one that is expired.
                ch = misc.get_data_digest(good_cert_path_2,
                    hash_func=hashlib.sha1)[0]
                pkg_cert_path = os.path.join(self.get_img_path(), "var", "pkg",
                    "ssl", ch)
                shutil.copy(bad_cert_path, pkg_cert_path)

                # Refresh all publishers should try to validate all certs.
                self.pkg("refresh", exit=1)
                self.assert_("Publisher: tmp" in self.errout, self.errout)
                self.assert_("Publisher: test" in self.errout, self.errout)

        def test_expiring_certs(self):
                """Test that image-create will not raise exception for
                expiring certificates. (Bug 17768096)"""

                tmp_dir = tempfile.mkdtemp(dir=self.test_root)

                # Retrive the correct CA and use it to generate a new cert.
                test_ca = self.get_pub_ta("test")
                test_cs = "cs1_{0}".format(test_ca)

                # Add a certificate to the length 2 chain that is going to
                # expire in 27 days.
                cg = certgenerator.CertGenerator(base_dir=tmp_dir)
                cg.make_cs_cert(test_cs, test_ca, ca_path=self.path_to_certs,
                    expiring=True, https=True)
                self.ac.start()
                self.image_create()

                # Set https-based publisher with expiring cert.
                self.seed_ta_dir("ta7")
                self.pkg("image-create -f --user -k {key} -c {cert} "
                    "-p test={url} {path}/image".format(
                    url=self.acurl1,
                    cert=os.path.join(cg.cs_dir, "{0}_cert.pem".format(test_cs)),
                    key=os.path.join(cg.keys_dir, "{0}_key.pem".format(test_cs)),
                    path=tmp_dir
                   ))


class TestDepotHTTPS(pkg5unittest.SingleDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=/usr/bin/example_path
            close"""

        misc_files = {
            "tmp/example_file": "tmp/example_file",
            "tmp/test_ssl_auth": """
#!/usr/bin/sh
reserved=$1
port=$2
echo "123"
""",
            "tmp/test_ssl_auth_bad": """
#!/usr/bin/sh
reserved=$1
port=$2
echo "12345"
""",
        }

        def pkg(self, command, *args, **kwargs):
                # The value for ssl_ca_file is pulled from DebugValues because
                # ssl_ca_file needs to be set there so the api object calls work
                # as desired.
                command = "--debug ssl_ca_file={0} {1}".format(
                    DebugValues["ssl_ca_file"], command)
                return pkg5unittest.SingleDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, six.string_types):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                for c in certs:
                        name = "{0}_cert.pem".format(c)
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))
                        DebugValues["ssl_ca_file"] = os.path.join(dest_dir,
                            name)

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.testdata_dir = os.path.join(self.test_root, "testdata")
                mpaths = self.make_misc_files(self.misc_files)
                self.ssl_auth_script = mpaths[1]
                self.ssl_auth_bad_script = mpaths[2]

                # Make shell scripts executable.
                os.chmod(self.ssl_auth_script, stat.S_IRWXU)
                os.chmod(self.ssl_auth_bad_script, stat.S_IRWXU)

                # Set up the paths to the certificates that will be needed.
                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.pub_cas_dir = os.path.join(self.path_to_certs,
                    "publisher_cas")
                self.inter_certs_dir = os.path.join(self.path_to_certs,
                    "inter_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

                self.pkgsend_bulk(self.rurl, self.example_pkg10)

                self.server_ssl_cert = os.path.join(self.cs_dir,
                    "cs1_ta7_cert.pem")
                self.server_ssl_key = os.path.join(self.keys_dir,
                    "cs1_ta7_key.pem")
                self.server_ssl_reqpass_key = os.path.join(self.keys_dir,
                    "cs1_ta7_reqpass_key.pem")

        def test_01_basics(self):
                """Test that adding an https publisher works and that a package
                can be installed from that publisher."""

                def test_ssl_settings(exit=0):
                        # Image must be created first before seeding cert files.
                        self.pkg_image_create()
                        self.seed_ta_dir("ta7")

                        if exit != 0:
                                self.dc.start_expected_fail(exit=exit)
                                self.dc.disable_ssl()
                                return

                        # Start depot *after* seeding certs.
                        self.dc.start()

                        self.pkg("set-publisher -p {0}".format(self.durl))
                        api_obj = self.get_img_api_obj()
                        self._api_install(api_obj, ["example_pkg"])

                        self.dc.stop()
                        self.dc.disable_ssl()

                # Verify using 'builtin' ssl authentication for server with
                # a key that has no passphrase.
                self.dc.enable_ssl(key_path=self.server_ssl_key,
                    cert_path=self.server_ssl_cert)
                test_ssl_settings()

                # Verify using 'exec' ssl authentication for server with a key
                # that has no passphrase.
                self.dc.enable_ssl(key_path=self.server_ssl_key,
                    cert_path=self.server_ssl_cert,
                    dialog="exec:{0}".format(self.ssl_auth_script))
                test_ssl_settings()

                # Verify using 'exec' ssl authentication for server with a key
                # that has a passphrase of '123'.
                self.dc.enable_ssl(key_path=self.server_ssl_reqpass_key,
                    cert_path=self.server_ssl_cert,
                    dialog="exec:{0}".format(self.ssl_auth_script))
                test_ssl_settings()

                # Verify using 'exec' ssl authentication for server with a key
                # that has a passphrase of 123' but the wrong passphrase is
                # supplied.
                self.dc.enable_ssl(key_path=self.server_ssl_reqpass_key,
                    cert_path=self.server_ssl_cert,
                    dialog="exec:{0}".format(self.ssl_auth_bad_script))
                test_ssl_settings(exit=1)


if __name__ == "__main__":
        unittest.main()
