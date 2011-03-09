#!/usr/bin/python2.6
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
# Copyright (c) 2010, 2011, Oracle and/or its affiliates. All rights reserved.
#

import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import re
import shutil
import sys
import unittest

import pkg.actions as action
import pkg.actions.signature as signature
import pkg.client.api_errors as apx
import pkg.fmri as fmri
import pkg.portable as portable
import M2Crypto as m2

class TestPkgSign(pkg5unittest.SingleDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            add dir mode=0755 owner=root group=bin path=/usr/lib/python2.4/vendor-packages/OpenSSL
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
            add set name=com.sun.service.incorporated_changes value="6556919 6627937"
            add set name=com.sun.service.random_test value=42 value=79
            add set name=com.sun.service.bug_ids value="4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937"
            add set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"
            add set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z
            add set description='FOOO bAr O OO OOO'
            add set name='weirdness' value='] [ * ?'
            close """

        varsig_pkg = """
            open example_pkg@1.0,5.15-0
            add set name=variant.arch value=sparc value=i386
            add dir mode=0755 owner=root group=bin path=/bin
            add signature tmp/example_file value=d2ff algorithm=sha256 variant.arch=i386
            close """

        var_pkg = """
            open var_pkg@1.0,5.11-0
            add set name=variant.arch value=sparc value=i386
            add dir mode=0755 owner=root group=bin path=/bin variant.arch=sparc
            add dir mode=0755 owner=root group=bin path=/baz variant.arch=i386
            close """

        image_files = ['simple_file']
        misc_files = ['tmp/example_file']

        def seed_ta_dir(self, certs, dest_dir=None):
                if isinstance(certs, basestring):
                        certs = [certs]
                if not dest_dir:
                        dest_dir = self.ta_dir
                self.assert_(dest_dir)
                self.assert_(self.raw_trust_anchor_dir)
                for c in certs:
                        name = "%s_cert.pem" % c
                        portable.copyfile(
                            os.path.join(self.raw_trust_anchor_dir, name),
                            os.path.join(dest_dir, name))

        def pkg_image_create(self, *args, **kwargs):
                pkg5unittest.SingleDepotTestCase.pkg_image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path, "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path, f), "wb") as fh:
                                fh.close()

        def image_create(self, *args, **kwargs):
                pkg5unittest.SingleDepotTestCase.image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path, "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path, f), "wb") as fh:
                                fh.close()

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self)
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                self.ta_dir = None

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

        def test_sign_0(self):
                """Test that packages signed with hashes only work correctly."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                # Test that things work with unsigned packages.
                self.image_create(self.rurl1)

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli handles RequiredSignaturePolicyExceptions.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy require-names foo")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli handles MissingRequiredNamesException.
                self.pkg("install example_pkg", exit=1)

                self.pkg("unset-property signature-policy")

                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher "
                    "--set-property signature-policy=require-signatures test")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-publisher "
                    "--set-property signature-policy=require-names "
                    "--set-property signature-required-names=foo test")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])

                self.pkgsign(self.rurl1, plist[0])
                self.image_destroy()
                self.image_create(self.rurl1)

                # Test that things work hashes instead of signatures.
                self.pkg("refresh --full")

                self.pkg("set-publisher --unset-property signature-policy "
                    "--unset-property signature-required-names test")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("search -l sha256")
                self._api_uninstall(api_obj, ["example_pkg"])

                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-names foo")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])

                self.pkg("unset-property signature-policy")

                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --set-property "
                    "signature-policy=require-signatures test")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-publisher "
                    "--set-property signature-policy=require-names "
                    "--set-property signature-required-names=foo test")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])

        def test_sign_1(self):
                """Test that packages signed using private keys function
                correctly.  Uses a chain of certificates three certificates
                long."""

                ca_path = os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem")
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                td = os.environ["TMPDIR"]
                sd = os.path.join(td, "tmp_sign")
                os.makedirs(sd)
                os.environ["TMPDIR"] = sd
                self.pkgsign(self.rurl1, sign_args)
                # Ensure that all temp files from signing have been removed.
                self.assertEqual(os.listdir(sd), [])
                os.environ["TMPDIR"] = td

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                # Find the hash of the publisher CA cert used.
                hsh = self.calc_file_hash(ca_path)

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("search -l rsa-sha256")
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                emptyCA = os.path.join(self.img_path, "emptyCA")
                os.makedirs(emptyCA)
                self.pkg("set-property trust-anchor-directory emptyCA")
                # This should fail because the chain is rooted in an untrusted
                # self-signed cert.
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                # Test that the cli handles BrokenChain exceptions.
                self.pkg("install example_pkg", exit=1)
                # Now seed the emptyCA directory to test that certs can be
                # pulled from it correctly.
                self.seed_ta_dir("ta3", dest_dir=emptyCA)
                
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-names foo")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy "
                    "require-names 'cs1_p1_ta3'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("add-property-value signature-required-names "
                    "'pubCA1_ta3'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("remove-property-value signature-required-names "
                    "'cs1_p1_ta3'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                # Test setting publisher level policies.
                self.pkg("unset-property signature-policy")

                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher "
                    "--set-property signature-policy=require-signatures test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher "
                    "--set-property signature-policy=require-names "
                    "--set-property signature-required-names='cs1_p1_ta3' test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --add-property-value "
                    "signature-required-names='pubCA1_ta3' test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --remove-property-value "
                    "signature-required-names='cs1_p1_ta3' test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --add-property-value "
                    "signature-required-names='foo' test")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-publisher --remove-property-value "
                    "signature-required-names='foo' test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                # Test combining publisher and image require-names policies.
                self.pkg("set-property signature-policy require-names foo")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-names "
                    "pubCA1_ta3")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("unset-property signature-policy")

                # Test removing and adding ca certs
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                self.pkg("set-publisher --revoke-ca-cert=%s test" % hsh)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                self.pkg("set-publisher --approve-ca-cert=%s test" % ca_path)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("set-publisher --revoke-ca-cert=%s test" % hsh)
                self.pkg("verify", exit=1)
                self.pkg("fix", exit=1)
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                # These should fail because the image, though not the publisher
                # verifies signatures.
                self.pkg("set-property signature-policy verify")
                self.pkg("verify", exit=1)
                self.pkg("fix", exit=1)
                self.pkg("set-property signature-policy ignore")
                self.pkg("verify")
                self.pkg("fix")
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                # These should fail because the publisher, though not the image
                # verifies signatures.
                self.pkg("verify", exit=1)
                self.pkg("fix", exit=1)
                self.pkg("set-publisher --approve-ca-cert=%s test" % ca_path)
                self.pkg("verify")
                self.pkg("fix")
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg"])

                # Test removing a signing cert.
                # Find the hash of the publisher CA cert used.
                hsh = self.calc_file_hash(ca_path)
                r.remove_signing_certs([hsh], ca=True)
                self.image_destroy()
                self.image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_sign_2(self):
                """Test that verification of the CS cert failing means the
                install fails."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_sign_3(self):
                """Test that using a chain seven certificates long works.  It
                also tests that setting a second publisher ca cert doesn't
                cause anything to break."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta1_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i1_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i2_ta1_cert.pem")], ca=False)
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "%(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_pubCA1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_pubCA1_cert.pem"),
                      "pkg": plist[0]
                    }
                
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_multiple_signatures(self):
                """Test that having a package signed with more than one
                signature doesn't cause anything to break."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta1_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i1_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i2_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "%(pkg)s" % {
                        "key":
                        os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                        "cert":
                        os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                        "i1":
                        os.path.join(self.chain_certs_dir,
                            "ch1_pubCA1_cert.pem"),
                        "i2":
                        os.path.join(self.chain_certs_dir,
                            "ch2_pubCA1_cert.pem"),
                        "pkg": plist[0]
                    }
                self.pkgsign(self.rurl1, sign_args)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                    "name": plist[0],
                    "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                    "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir(["ta1", "ta2"])
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-names "
                    "'cs1_ta2'")
                self.pkg("add-property-value signature-required-names 'i1_ta1'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("add-property-value signature-required-names 'foo'")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])

        def test_sign_4(self):
                """Test that not providing a needed intermediate cert makes
                verification fail."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta1_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i1_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i2_ta1_cert.pem")], ca=False)
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i2)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_pubCA1_cert.pem"),
                      "pkg": plist[0]
                    }
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")

                self.pkg("install example_pkg", exit=1)

        def test_sign_5(self):
                """Test that http repos work."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([
                    os.path.join(self.pub_cas_dir, "pubCA1_ta1_cert.pem"),
                    os.path.join(self.pub_cas_dir, "pubCA1_ta3_cert.pem")],
                    ca=True)
                r.add_signing_certs([
                    os.path.join(self.inter_certs_dir, "i1_ta1_cert.pem"),
                    os.path.join(self.inter_certs_dir, "i2_ta1_cert.pem")],
                    ca=False)
                self.dcs[1].start()
                
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "%(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_pubCA1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_pubCA1_cert.pem"),
                      "pkg": plist[0]
                    }
                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_length_two_chains(self):
                """Check that chains of length two work correctly."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")], ca=True)
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      "pkg": plist[0]
                    }
                
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)

                self.pkg("set-property signature-policy verify")
                # This should trigger a UntrustedSelfSignedCert error.
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UntrustedSelfSignedCert,
                    self._api_install, api_obj, ["example_pkg"])
                # Test that the cli handles an UntrustedSelfSignedCert.
                self.pkg("install example_pkg", exit=1)
                self.seed_ta_dir("ta2")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-names foo")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.MissingRequiredNamesException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-names "
                    "'cs1_ta2'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("add-property-value signature-required-names 'ta2'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

        def test_variant_sigs(self):
                """Test that variant tagged signatures are ignored."""
                plist = self.pkgsend_bulk(self.rurl1, self.varsig_pkg)
                self.pkg_image_create(self.rurl1)

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])

        def test_bad_opts_1(self):
                self.pkgsign(self.durl1, "--help")
                self.dcs[1].start()
                self.pkgsign(self.durl1, "foo@1.2.3", exit=1)
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                # Test that passing sign-all and a fmri results in an error.
                self.pkgsign(self.durl1, "--sign-all %(name)s" % {
                      "name": plist[0]
                    }, exit=2)

                # Test that passing a repo that doesn't exist doesn't cause
                # a traceback.
                self.pkgsign("http://foobar.baz",
                    "%(name)s" % { "name": plist[0] }, exit=1)

                # Test that passing neither sign-all nor a fmri results in an
                # error.
                self.pkgsign(self.durl1, "", exit=2)
                
                # Test bad sig.alg setting.
                self.pkgsign(self.durl1, "-a foo -k %(key)s -c %(cert)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)

                # Test missing cert option
                self.pkgsign(self.durl1, "-k %(key)s %(name)s" %
                    { "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test missing key option
                self.pkgsign(self.durl1, "-c %(cert) %(name)s" %
                    { "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test -i with missing -c and -k
                self.pkgsign(self.durl1, "-i %(i1)s %(name)s" %
                    { "i1": os.path.join(self.chain_certs_dir,
                          "ch1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a cert as a key
                self.pkgsign(self.durl1, "-c %(cert)s -k %(cert)s %(name)s" %
                    { "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=1)
                # Test passing a non-existent certificate file
                self.pkgsign(self.durl1, "-c /shouldnotexist -k %(key)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a non-existent key file
                self.pkgsign(self.durl1, "-c %(cert)s -k /shouldnotexist "
                    "%(name)s" % {
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a file that's not a key file as a key file
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s %(name)s" %
                    { "key": os.path.join(self.test_root, "tmp/example_file"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=1)
                # Test passing a non-existent file as an intermediate cert
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s -i %(i1)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "shouldnot/exist"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a directory as an intermediate cert
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s -i %(i1)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "i1": self.chain_certs_dir,
                      "name": plist[0]
                    }, exit=2)
                # Test setting the signature algorithm to be one which requires
                # a key and cert, but not passing -k or -c.
                self.pkgsign(self.durl1, "-a rsa-sha256 %s" % plist[0], exit=2)
                # Test setting the signature algorithm to be one which does not
                # use a key and cert, but passing -k and -c.
                self.pkgsign(self.durl1, "-a sha256 -k %(key)s -c %(cert)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test that installing a package signed using a bogus
                # certificate fails.
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s %(name)s" %
                    { "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.test_root, "tmp/example_file"),
                      "name": plist[0]
                    })
                self.pkg_image_create(self.durl1)
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BadFileFormat, self._api_install, api_obj,
                    ["example_pkg"])
                # Test that the cli handles a BadFileFormat exception.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property trust-anchor-directory %s" %
                    os.path.join("simple_file"))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidPropertyValue, self._api_install,
                    api_obj, ["example_pkg"])
                # Test that the cli handles an InvalidPropertyValue exception.
                self.pkg("install example_pkg", exit=1)

        def test_bad_opts_2(self):
                """Test that having a bogus trust anchor will stop install."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign(self.rurl1, "-k %(key)s -c %(cert)s %(name)s" %
                    { "key": os.path.join(self.keys_dir, "cs1_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem"),
                      "name": plist[0]
                    })
                self.pkg_image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")
                self.pkg("set-property trust-anchor-directory %s" %
                    os.path.join("simple_file"))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidPropertyValue, self._api_install,
                    api_obj, ["example_pkg"])

        def test_multiple_hash_algs(self):
                """Test that signing with other hash algorithms works
                correctly."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                sign_args = "-a rsa-sha512 -k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                sign_args = "-a sha384 %(name)s" % {"name": plist[0]}
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property require-signatures verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_mismatched_sigs(self):
                """Test that if the certificate can't validate the signature,
                an error happens."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnverifiedSignature, self._api_install,
                    api_obj, ["example_pkg"])
                # Test that the cli handles an UnverifiedSignature exception.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("unset-property signature-policy")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_mismatched_hashes(self):
                """Test that if the hash signature isn't correct, an error
                happens."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "%(name)s" % { "name": plist[0] }
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)

                # Make sure the manifest is locally stored.
                self.pkg("install -n example_pkg")
                # Append an action to the manifest.
                pfmri = fmri.PkgFmri(plist[0])
                s = self.get_img_manifest(pfmri)
                s += "\nset name=foo value=bar"
                self.write_img_manifest(pfmri, s)

                self.pkg("set-property signature-policy verify")
                # This should fail because the text of manifest has changed
                # so the hash should no longer validate.
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnverifiedSignature, self._api_install,
                    api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("unset-property signature-policy")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unknown_sig_alg(self):
                """Test that if the certificate can't validate the signature,
                an error happens."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                # Make sure the manifest is locally stored.
                api_obj = self.get_img_api_obj()
                api_obj.plan_install(["example_pkg"], noexecute=True)
                # Change the signature action.
                pfmri = fmri.PkgFmri(plist[0])
                s = self.get_img_manifest(pfmri)
                s = s.replace("rsa-sha256", "rsa-foobar")
                self.write_img_manifest(pfmri, s)
                
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                # This passes because 'foobar' isn't a recognized hash algorithm
                # so the signature action is skipped.
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                # Write manifest to image cache again.
                self.write_img_manifest(pfmri, s)

                # Change the signature action.
                pfmri = fmri.PkgFmri(plist[0])
                s = self.get_img_manifest(pfmri)
                s = s.replace("rsa-foobar", "foo-sha256")
                self.write_img_manifest(pfmri, s)

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("install example_pkg", exit=1)
                # This passes because 'foobar' isn't a recognized signature
                # algorithm so the signature action is skipped.
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unsupported_critical_extension_1(self):
                """Test that packages signed using a certificate with an
                unsupported critical extension will not have valid signatures.
                """

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs2_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs2_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnsupportedCriticalExtension,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli can handle an UnsupportedCriticalExtension.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unsupported_critical_extension_2(self):
                """Test that packages signed using a certificate whose chain of
                trust contains a certificate with an unsupported critical
                extension will not have valid signatures."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA2_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p2_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p2_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnsupportedCriticalExtension,
                    self._api_install, api_obj, ["example_pkg"])

        def test_unsupported_critical_extension_3(self):
                """Test that packages signed using a certificate whose chain of
                trust contains a certificate with an unsupported critical
                extension will not have valid signatures."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta1_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i1_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i2_ta1_cert.pem")], ca=False)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs4_pubCA1_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs4_pubCA1_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_pubCA1_cert.pem"),
                        "i2": os.path.join(self.chain_certs_dir,
                            "ch2.2_pubCA1_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_inappropriate_use_of_code_signing_cert(self):
                """Test that signing a certificate with a code signing
                certificate results in a broken chain."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_cs8_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_cs8_p1_ta3_cert.pem"),
                        "i1": os.path.join(self.cs_dir,
                            "cs8_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                # This raises a BrokenChain exception because the certificate
                # check_ca method checks the keyUsage extension if it's set
                # as well as the basicConstraints extension.
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_inappropriate_use_of_cert_signing_cert(self):
                """Test that using a CA cert without the digitalSignature
                value for the keyUsage extension to sign a package means
                that the package's signature doesn't verify."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "pubCA1_ta3_key.pem"),
                        "cert": os.path.join(self.pub_cas_dir,
                            "pubCA1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InappropriateCertificateUse,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli can handle an InappropriateCertificateUse
                # exception.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_no_crlsign_on_revoking_ca(self):
                """Test that if a CRL is signed with a CA that has the keyUsage
                extension but not the cRLSign value is not considered a valid
                CRL."""
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA2_ta4_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "pu"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "pubCA2_ta4_crl.pem"),
                    os.path.join(rstore.file_root, "pu", "pubCA2_ta4_crl.pem"))
                
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p2_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p2_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This succeeds because the CA which signed the revoking CRL
                # did not have the cRLSign keyUsage extension set.
                self._api_install(api_obj, ["example_pkg"])

        def test_unknown_value_for_non_critical_extension(self):
                """Test that an unknown value for a recognized non-critical
                extension causes an exception to be raised."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs5_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs5_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnsupportedExtensionValue,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli can handle an UnsupportedCriticalExtension.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unknown_value_for_critical_extension(self):
                """Test that an unknown value for a recognized critical
                extension causes an exception to be raised."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs6_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs6_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnsupportedExtensionValue,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unset_keyUsage_for_code_signing(self):
                """Test that if keyUsage has not been set, the code signing
                certificate is considered valid."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs7_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs7_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unset_keyUsage_for_cert_signing(self):
                """Test that if keyUsage has not been set, the CA certificate is
                considered valid."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA5_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p5_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p5_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_no_server_update(self):
                """Test that packages signed using private keys function
                correctly.  Uses a chain of certificates three certificates
                long."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "--no-index --no-catalog -k %(key)s -c %(cert)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                # This fails because the index hasn't been updated.
                self.pkg("search -r rsa-sha256", exit=1)
                self.pkg("set-property signature-policy require-signatures")
                # This fails because the catalog hasn't been updated with
                # the signed manifest yet.
                self.pkg("install example_pkg", exit=1)
                r.rebuild()
                self.pkg("install example_pkg")

        def test_bogus_client_certs(self):
                """Tests that if a certificate stored on the client is replaced
                with a different certificate, installation fails."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                cs_path = os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                cs2_path = os.path.join(self.cs_dir, "cs1_ta2_cert.pem")
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": cs_path
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                # Replace the client CS cert.
                hsh = self.calc_file_hash(cs_path)
                pth = os.path.join(self.img_path, "var", "pkg", "publisher",
                    "test", "certs", hsh)
                portable.copyfile(cs2_path, pth)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.ModifiedCertificateException,
                    self._api_install, api_obj, ["example_pkg"])
                # Test that the cli handles a ModifiedCertificateException.
                self.pkg("install example_pkg", exit=1)

                # Test that removing the CS cert will cause it to be downloaded
                # again and the installation will then work.

                portable.remove(pth)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                # Repeat the test but change the CA cert instead of the CS cert.

                # Replace the client CA cert.
                hsh = self.calc_file_hash(ca_path)
                pth = os.path.join(self.img_path, "var", "pkg", "publisher",
                    "test", "certs", hsh)
                portable.copyfile(cs2_path, pth)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.ModifiedCertificateException,
                    self._api_install, api_obj, ["example_pkg"])

                # Test that removing the CA cert will cause it to be downloaded
                # again and the installation will then work.

                portable.remove(pth)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_crl_0(self):
                """Test that the X509 CRL revocation works correctly."""

                crl = m2.X509.load_crl(os.path.join(self.crl_dir,
                    "pubCA1_ta4_crl.pem"))
                revoked_cert = m2.X509.load_cert(os.path.join(self.cs_dir,
                    "cs1_ta4_cert.pem"))
                assert crl.is_revoked(revoked_cert)[0]

        def test_bogus_inter_certs(self):
                """Test that if SignatureAction.set_signature is given invalid
                paths to intermediate certs, it errors as expected.  This
                cannot be tested from the command line because the command
                line rejects certificates that aren't of the right format."""

                attrs = {
                    "algorithm": "sha256",
                }
                key_pth = os.path.join(self.keys_dir, "cs_pubCA1_key.pem")
                cert_pth = os.path.join(self.cs_dir, "cs1_pubCA1_cert.pem")
                sig_act = signature.SignatureAction(cert_pth, **attrs)
                self.assertRaises(action.ActionDataError, sig_act.set_signature,
                    [sig_act], key_path=key_pth,
                    chain_paths=["/shouldnot/exist"])
                self.assertRaises(action.ActionDataError, sig_act.set_signature,
                    [sig_act], key_path=key_pth, chain_paths=[self.test_root])

        def test_sign_all(self):
                """Test that the --sign-all option works correctly, signing
                all packages in a repository."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                plist = self.pkgsend_bulk(self.rurl1, self.var_pkg)

                sign_args = "-k %(key)s -c %(cert)s --sign-all" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_install(api_obj, ["var_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["var_pkg"])

        def test_crl_1(self):
                """Test that revoking a code signing certificate by the
                publisher CA works correctly."""
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta4_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "pu"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "pubCA1_ta4_crl.pem"),
                    os.path.join(rstore.file_root, "pu", "pubCA1_ta4_crl.pem"))
                
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RevokedCertificate, self._api_install,
                    api_obj, ["example_pkg"])
                # Test that cli handles RevokedCertificate exception.
                self.pkg("install example_pkg", exit=1)

        def test_crl_2(self):
                """Test that revoking a code signing certificate by the
                publisher CA works correctly."""
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta5_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ta"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ta5_crl.pem"),
                    os.path.join(rstore.file_root, "ta", "ta5_crl.pem"))
                
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs1_ta5_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_ta5_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta5")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_crl_3(self):
                """Test that a CRL with a bad file format does not cause
                breakage."""
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta4_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ex"))
                portable.copyfile(os.path.join(self.test_root,
                    "tmp/example_file"),
                    os.path.join(rstore.file_root, "ex", "example_file"))
                
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs2_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs2_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_crl_4(self):
                """Test that a CRL which cannot be retrieved does not cause
                breakage."""
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta4_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs2_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs2_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_crl_5(self):
                """Test that revocation by CRL validated by a grandparent of the
                certificate in question works."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta1_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i1_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i2_ta1_cert.pem")], ca=False)

                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "pu"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "pubCA1_ta1_crl.pem"),
                    os.path.join(rstore.file_root, "pu", "pubCA1_ta1_crl.pem"))

                self.dcs[1].start()
                
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "%(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs2_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs2_pubCA1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_pubCA1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_pubCA1_cert.pem"),
                      "pkg": plist[0]
                    }
                
                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RevokedCertificate, self._api_install,
                    api_obj, ["example_pkg"])

        def test_crl_6(self):
                """Test that revocation by CRL validated by an intermediate
                certificate of the certificate in question works."""

                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([os.path.join(self.pub_cas_dir,
                    "pubCA1_ta1_cert.pem")], ca=True)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i1_ta1_cert.pem")], ca=False)
                r.add_signing_certs([os.path.join(self.inter_certs_dir,
                    "i2_ta1_cert.pem")], ca=False)

                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ch"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ch1_pubCA1_crl.pem"),
                    os.path.join(rstore.file_root, "ch", "ch1_pubCA1_crl.pem"))

                self.dcs[1].start()
                
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "%(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs3_pubCA1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs3_pubCA1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_pubCA1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_pubCA1_cert.pem"),
                      "pkg": plist[0]
                    }
                
                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RevokedCertificate, self._api_install,
                    api_obj, ["example_pkg"])

        def test_crl_7(self):
                """Test that a CRL location which isn't in a known URI format
                doesn't cause breakage."""
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta4_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs3_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs3_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidResourceLocation,
                    self._api_install, api_obj, ["example_pkg"])
                # Test that the cli can handle a InvalidResourceLocation
                # exception.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("verify", exit=1)

        def test_var_pkg(self):
                """Test that actions tagged with variants don't break signing.
                """

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.var_pkg)

                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_p1_ta3_cert.pem"),
                        "pkg": plist[0]
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--variant variant.arch=i386")
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["var_pkg"])
                self.assert_(os.path.exists(os.path.join(self.img_path, "baz")))
                self.assert_(not os.path.exists(
                    os.path.join(self.img_path, "bin")))

        def test_disabled_append(self):
                """Test that publishing to a depot which doesn't support append
                fails as expected."""

                self.dcs[1].set_disable_ops(["append"])
                self.dcs[1].start()
                
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                
                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_p1_ta3_cert.pem"),
                        "pkg": plist[0]
                }
                self.pkgsign(self.durl1, sign_args, exit=1)

        def test_disabled_add(self):
                """Test that publishing to a depot which doesn't support add
                fails as expected."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                self.dcs[1].set_disable_ops(["add"])
                self.dcs[1].start()
                
                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_p1_ta3_cert.pem"),
                        "pkg": plist[0]
                }
                self.pkgsign(self.durl1, sign_args, exit=1)

        def test_disabled_file(self):
                """Test that publishing to a depot which doesn't support file
                fails as expected."""

                self.dcs[1].set_disable_ops(["file"])
                self.dcs[1].start()

                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(pkg)s" % {
                    "key": os.path.join(self.keys_dir, "cs1_p1_ta3_key.pem"),
                    "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem"),
                    "i1": os.path.join(self.chain_certs_dir,
                        "ch1_pubCA1_cert.pem"),
                    "pkg": plist[0]
                }
                self.pkgsign(self.durl1, sign_args, exit=1)

        def test_expired_certs(self):
                """Test that expiration dates on the signing cert are
                ignored."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs3_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs3_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self._api_install(api_obj, ["example_pkg"])

        def test_future_certs(self):
                """Test that expiration dates on the signing cert are
                ignored."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs4_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs4_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self._api_install(api_obj, ["example_pkg"])

        def test_expired_ca_certs(self):
                """Test that expiration dates on a CA cert are ignored."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA3_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p3_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p3_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self._api_install(api_obj, ["example_pkg"])

        def test_future_ca_certs(self):
                """Test that expiration dates on a CA cert are ignored."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA4_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p4_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p4_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self._api_install(api_obj, ["example_pkg"])

        def test_cert_retrieval_failure(self):
                """Test that a certificate that can't be retrieved doesn't
                cause a traceback."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.var_pkg)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()
                
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta3")

                self.pkg("info -r var_pkg")
                self.dcs[1].stop()
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self.assertRaises(apx.TransportError, self._api_install,
                    api_obj, ["var_pkg"], refresh_catalogs=False)

                # Test that a TransportError from certificate retrieval is
                # handled correctly.
                self.pkg("install --no-refresh var_pkg", exit=1)

        def test_manual_pub_cert_approval(self):
                """Test that manually approving a publisher's CA cert works
                correctly."""

                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property signature-policy=require-signatures")
                self.pkg("set-publisher --approve-ca-cert %s test" % ca_path)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_higher_signature_version(self):
                
                ca_path = os.path.join(os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem"))
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                
                self.pkgsign(self.rurl1, sign_args)
                mp = r.manifest(plist[0])
                with open(mp, "r") as fh:
                        ls = fh.readlines()
                s = []
                old_ver = action.generic.Action.sig_version
                new_ver = old_ver + 1
                # Replace the published manifest with one whose signature
                # action has a version one higher than what the current
                # supported version is.
                for l in ls:
                        if not l.startswith("signature"):
                                s.append(l)
                                continue
                        tmp = l.replace("version=%s" % old_ver,
                            "version=%s" % new_ver)
                        s.append(tmp)
                with open(mp, "wb") as fh:
                        for l in s:
                                fh.write(l)
                # Rebuild the repository catalog so that hash verification for
                # the manifest won't cause problems.
                r.rebuild()

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])
                # This passes because it ignores the signature with a version
                # it doesn't understand.
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_using_default_cert_loc(self):
                """Test that the default location is properly image relative
                and is used."""

                ca_path = os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem")
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                
                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_using_pkg_image_cert_loc(self):
                """Test that trust anchors are properly pulled from the image
                that the pkg command was run from."""

                ca_path = os.path.join(self.pub_cas_dir,
                    "pubCA1_ta3_cert.pem")
                r = self.get_repo(self.dcs[1].get_repodir())
                r.add_signing_certs([ca_path], ca=True)

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_p1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir, "cs1_p1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                orig_img_path = self.img_path
                
                # This changes self.img_path to point to the newly created
                # sub image.
                self.create_sub_image(self.rurl1)
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This raises an exception because the command is run from
                # within the sub-image, which has now trust anchors installed.
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                # This should work because the command is run from within the
                # original image which contains the trust anchors needed to
                # validate the chain.
                api_obj = self.get_img_api_obj(
                    cmd_path=os.path.join(orig_img_path, "pkg"))
                self._api_install(api_obj, ["example_pkg"])
                # Check that the package is installed into the correct image.
                self.pkg("list example_pkg")
                self.pkg("-R %s list example_pkg" % orig_img_path, exit=1)
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg"])
                # Repeat the test using the pkg command interface instead of the
                # api.
                self.pkg("-R %s install example_pkg" % self.img_path,
                    alt_img_path=orig_img_path)
                self.pkg("list example_pkg")
                self.pkg("-R %s list example_pkg" % orig_img_path, exit=1)

if __name__ == "__main__":
        unittest.main()
