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

from pkg.client.debugvalues import DebugValues

obsolete_pkg = """
    open obs@1.0,5.11-0
    add set name=pkg.obsolete value=true
    add set name=pkg.summary value="An obsolete package"
    close """

renamed_pkg = """
    open renamed@1.0,5.11-0
    add set name=pkg.renamed value=true
    add depend fmri=example_pkg@1.0 type=require
    close """


class TestPkgSign(pkg5unittest.SingleDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

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

        need_renamed_pkg = """
            open need_renamed@1.0,5.11-0
            add depend fmri=renamed type=require
            close """

        pub2_example = """
            open pkg://pub2/example_pkg@1.0,5.11-0
            add set description='a package with an alternate publisher'
            close """

        pub2_pkg = """
            open pkg://pub2/pub2pkg@1.0,5.11-0
            add set description='a package with an alternate publisher'
            close """

        bug_18880_pkg = """
            open b18880@1.0,5.11-0
            add file tmp/example_file mode=0555 owner=root group=bin path=bin/example_path variant.foo=bar
            add file tmp/example_file2 mode=0555 owner=root group=bin path=bin/example_path variant.foo=baz
            close"""

        image_files = ['simple_file']
        misc_files = ['tmp/example_file', 'tmp/example_file2']

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
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path(), f), "wb") as fh:
                                fh.close()

        def image_create(self, *args, **kwargs):
                pkg5unittest.SingleDepotTestCase.image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path(), f), "wb") as fh:
                                fh.close()

        def pkg(self, command, *args, **kwargs):
                # The value for crl_host is pulled from DebugValues because
                # crl__host needs to be set there so the api object calls work
                # as desired.
                command = "--debug crl_host=%s %s" % \
                    (DebugValues["crl_host"], command)
                return pkg5unittest.SingleDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, image_count=2)
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                DebugValues["crl_host"] = self.durl1
                self.ta_dir = None

                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
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

                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                ta_cert_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta3_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": chain_cert_path
                }
                td = os.environ["TMPDIR"]
                sd = os.path.join(td, "tmp_sign")
                os.makedirs(sd)
                os.environ["TMPDIR"] = sd

                # Specify location as filesystem path.
                self.pkgsign(self.dc.get_repodir(), sign_args)

                # Ensure that all temp files from signing have been removed.
                self.assertEqual(os.listdir(sd), [])
                os.environ["TMPDIR"] = td

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                # Find the hash of the publisher CA cert used.
                hsh = self.calc_pem_hash(chain_cert_path)

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

                emptyCA = os.path.join(self.img_path(), "emptyCA")
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
                    "require-names 'cs1_ch1_ta3'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("add-property-value signature-required-names "
                    "'ch1_ta3'")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("remove-property-value signature-required-names "
                    "'cs1_ch1_ta3'")
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
                    "--set-property signature-required-names='cs1_ch1_ta3' "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --add-property-value "
                    "signature-required-names='ch1_ta3' test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("set-publisher --remove-property-value "
                    "signature-required-names='cs1_ch1_ta3' test")
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
                    "ch1_ta3")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("unset-property signature-policy")

                # Test removing and adding chain certs
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                self.pkg("set-publisher --revoke-ca-cert=%s test" % hsh)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                self.pkg("set-publisher --approve-ca-cert=%s test" %
                    chain_cert_path)
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
                self.pkg("set-publisher --approve-ca-cert=%s test" %
                    chain_cert_path)
                self.pkg("verify")
                self.pkg("fix")
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg"])

                # Test that manually approving a trust anchor works.
                self.pkg("set-publisher --unset-ca-cert=%s test" % hsh)
                self.pkg("set-publisher --approve-ca-cert=%s test" %
                    ta_cert_path)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_2(self):
                """Test that verification of the CS cert failing means the
                install fails."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem")
                }

                # Specify repository location as relative path.
                cwd = os.getcwd()
                repodir = self.dc.get_repodir()
                os.chdir(os.path.dirname(repodir))
                self.pkgsign(os.path.basename(repodir), sign_args)
                os.chdir(cwd)

                self.image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_sign_3(self):
                """Test that using a chain seven certificates long works.  It
                also tests that having an extra chain certificate doesn't break
                anything."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s -i %(i6)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem"),
                      "i6": os.path.join(self.chain_certs_dir,
                          "ch1_ta3_cert.pem"),
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(pkg)s" % {
                        "key":
                        os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                        "cert":
                        os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                        "i1":
                        os.path.join(self.chain_certs_dir,
                            "ch1_ta1_cert.pem"),
                        "i2":
                        os.path.join(self.chain_certs_dir,
                            "ch2_ta1_cert.pem"),
                        "i3":
                        os.path.join(self.chain_certs_dir,
                            "ch3_ta1_cert.pem"),
                        "i4":
                        os.path.join(self.chain_certs_dir,
                            "ch4_ta1_cert.pem"),
                        "i5":
                        os.path.join(self.chain_certs_dir,
                            "ch5_ta1_cert.pem"),
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
                self.pkg("add-property-value signature-required-names "
                    "'ch1_ta1'")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i2)s -i %(i3)s "\
                    "-i %(i4)s -i %(i5)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                        "i2":
                        os.path.join(self.chain_certs_dir,
                            "ch2_ta1_cert.pem"),
                        "i3":
                        os.path.join(self.chain_certs_dir,
                            "ch3_ta1_cert.pem"),
                        "i4":
                        os.path.join(self.chain_certs_dir,
                            "ch4_ta1_cert.pem"),
                        "i5":
                        os.path.join(self.chain_certs_dir,
                            "ch5_ta1_cert.pem"),
                      "pkg": plist[0]
                    }
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")

                self.pkg("install example_pkg", exit=1)

        def test_sign_5(self):
                """Test that http repos work."""

                self.dcs[1].start()
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem"),
                      "pkg": plist[0]
                    }
                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_length_two_chains(self):
                """Check that chains of length two work correctly."""

                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(ta)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      "ta": ta_path,
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

        def test_length_two_chains_two(self):
                """Check that chains of length two work correctly when the trust
                anchor is not included as an intermediate cert."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      "pkg": plist[0]
                    }

                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)

                self.pkg("set-property signature-policy verify")
                # This should trigger a BrokenChain error.
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain,
                    self._api_install, api_obj, ["example_pkg"])
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
                self.pkgsign(self.durl1, "example_pkg", exit=1)
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)

                # Test that not specifying a destination repository fails.
                self.pkgsign("", "'*'", exit=2)

                # Test that passing two patterns which match the same name
                # fails.
                self.pkgsign(self.durl1, "'e*' '*x*'", exit=1)

                # Test that passing a repo that doesn't exist doesn't cause
                # a traceback.
                self.pkgsign("http://foobar.baz",
                    "%(name)s" % { "name": plist[0] }, exit=1)

                # Test that passing no fmris or patterns results in an error.
                self.pkgsign(self.durl1, "", exit=2)

                # Test bad sig.alg setting.
                self.pkgsign(self.durl1, "-a foo -k %(key)s -c %(cert)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)

                # Test missing cert option
                self.pkgsign(self.durl1, "-k %(key)s %(name)s" %
                    { "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test missing key option
                self.pkgsign(self.durl1, "-c %(cert) %(name)s" %
                    { "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test -i with missing -c and -k
                self.pkgsign(self.durl1, "-i %(i1)s %(name)s" %
                    { "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a cert as a key
                self.pkgsign(self.durl1, "-c %(cert)s -k %(cert)s %(name)s" %
                    { "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=1)
                # Test passing a non-existent certificate file
                self.pkgsign(self.durl1, "-c /shouldnotexist -k %(key)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a non-existent key file
                self.pkgsign(self.durl1, "-c %(cert)s -k /shouldnotexist "
                    "%(name)s" % {
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a file that's not a key file as a key file
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s %(name)s" %
                    { "key": os.path.join(self.test_root, "tmp/example_file"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=1)
                # Test passing a non-existent file as an intermediate cert
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s -i %(i1)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "shouldnot/exist"),
                      "name": plist[0]
                    }, exit=2)
                # Test passing a directory as an intermediate cert
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s -i %(i1)s "
                    "%(name)s" % {
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
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
                      "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    }, exit=2)
                # Test that signing a package using a bogus certificate fails.
                self.pkgsign(self.durl1, "-k %(key)s -c %(cert)s %(name)s" %
                    { "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.test_root, "tmp/example_file"),
                      "name": plist[0]
                    }, exit =1)
                self.pkg_image_create(self.durl1)
                self.pkg("set-property signature-policy verify")
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
                    { "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      "name": plist[0]
                    })
                self.pkg_image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")
                self.pkg("set-property trust-anchor-directory %s" %
                    os.path.join("simple_file"))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidPropertyValue, self._api_install,
                    api_obj, ["example_pkg"])

        def test_dry_run_option(self):
                """Test that -n doesn't actually sign packages."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-n -k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=\
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p %s" % self.rurl1)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])

        def test_multiple_hash_algs(self):
                """Test that signing with other hash algorithms works
                correctly."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                sign_args = "-a rsa-sha512 -k %(key)s -c %(cert)s -i %(i1)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("unset-property signature-policy")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnverifiedSignature, self._api_install,
                    api_obj, ["example_pkg"])

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
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self.pkg("unset-property signature-policy")
                # Make sure the manifest is locally stored.
                self.pkg("install -n example_pkg")
                # Append an action to the manifest.
                pfmri = fmri.PkgFmri(plist[0])
                s = self.get_img_manifest(pfmri)
                s += "\nset name=foo value=bar"
                self.write_img_manifest(pfmri, s)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnverifiedSignature, self._api_install,
                    api_obj, ["example_pkg"])

        def test_unknown_sig_alg(self):
                """Test that if the certificate can't validate the signature,
                an error happens."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                # Make sure the manifest is locally stored.
                api_obj = self.get_img_api_obj()
                for pd in api_obj.gen_plan_install(["example_pkg"],
                    noexecute=True):
                        continue
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs2_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs2_ch1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unsupported_critical_extension_2(self):
                """Test that packages signed using a certificate whose chain of
                trust contains a certificate with an unsupported critical
                extension will not have valid signatures."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.1_ta3_cert.pem"),
                        "i1":os.path.join(self.chain_certs_dir,
                            "ch1.1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_unsupported_critical_extension_3(self):
                """Test that packages signed using a certificate whose chain of
                trust contains a certificate with an unsupported critical
                extension will not have valid signatures."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch5.1_ta1_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch5.1_ta1_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta1_cert.pem"),
                        "i2": os.path.join(self.chain_certs_dir,
                            "ch2_ta1_cert.pem"),
                        "i3": os.path.join(self.chain_certs_dir,
                            "ch3_ta1_cert.pem"),
                        "i4": os.path.join(self.chain_certs_dir,
                            "ch4_ta1_cert.pem"),
                        "i5": os.path.join(self.chain_certs_dir,
                            "ch5.1_ta1_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2) s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_cs8_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_cs8_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.cs_dir,
                            "cs8_ch1_ta3_cert.pem"),
                        "i2": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
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
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_inappropriate_use_of_cert_signing_cert(self):
                """Test that using a CA cert without the digitalSignature
                value for the keyUsage extension to sign a package means
                that the package's signature doesn't verify."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "ch1_ta3_key.pem"),
                        "cert": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_no_crlsign_on_revoking_ca(self):
                """Test that if a CRL is signed with a CA that has the keyUsage
                extension but not the cRLSign value is not considered a valid
                CRL."""

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ch"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ch1.1_ta4_crl.pem"),
                    os.path.join(rstore.file_root, "ch", "ch1.1_ta4_crl.pem"))

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1.1_ta4_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs5_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs5_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unknown_value_for_critical_extension(self):
                """Test that an unknown value for a recognized critical
                extension causes an exception to be raised."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs6_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs6_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnsupportedExtensionValue,
                    self._api_install, api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unset_keyUsage_for_code_signing(self):
                """Test that if keyUsage has not been set, the code signing
                certificate is considered valid."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs7_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs7_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.4_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.4_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1.4_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "--no-index --no-catalog -i %(i1)s -k %(key)s " \
                    "-c %(cert)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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
                r = self.get_repo(self.dcs[1].get_repodir())
                r.rebuild()
                self.pkg("install example_pkg")

        def test_bogus_client_certs(self):
                """Tests that if a certificate stored on the client is replaced
                with a different certificate, installation fails."""

                chain_cert_path = os.path.join(os.path.join(
                     self.chain_certs_dir, "ch1_ta3_cert.pem"))
                cs_path = os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem")
                cs2_path = os.path.join(self.cs_dir, "cs1_ta2_cert.pem")

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": cs_path,
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])

                # Replace the client CS cert.
                hsh = self.calc_pem_hash(cs_path)
                pth = os.path.join(self.img_path(), "var", "pkg", "publisher",
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

                # Repeat the test but change the chain cert instead of the CS
                # cert.

                # Replace the client chain cert.
                hsh = self.calc_pem_hash(chain_cert_path)
                pth = os.path.join(self.img_path(), "var", "pkg", "publisher",
                    "test", "certs", hsh)
                portable.copyfile(cs2_path, pth)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

                # Test that removing the chain cert will cause it to be
                # downloaded again and the installation will then work.

                portable.remove(pth)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_crl_0(self):
                """Test that the X509 CRL revocation works correctly."""

                crl = m2.X509.load_crl(os.path.join(self.crl_dir,
                    "ch1_ta4_crl.pem"))
                revoked_cert = m2.X509.load_cert(os.path.join(self.cs_dir,
                    "cs1_ch1_ta4_cert.pem"))
                assert crl.is_revoked(revoked_cert)[0]

        def test_bogus_inter_certs(self):
                """Test that if SignatureAction.set_signature is given invalid
                paths to intermediate certs, it errors as expected.  This
                cannot be tested from the command line because the command
                line rejects certificates that aren't of the right format."""

                attrs = {
                    "algorithm": "sha256",
                }
                key_pth = os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem")
                cert_pth = os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem")
                sig_act = signature.SignatureAction(cert_pth, **attrs)
                self.assertRaises(action.ActionDataError, sig_act.set_signature,
                    [sig_act], key_path=key_pth,
                    chain_paths=["/shouldnot/exist"])
                self.assertRaises(action.ActionDataError, sig_act.set_signature,
                    [sig_act], key_path=key_pth, chain_paths=[self.test_root])

        def test_signing_all(self):
                """Test that using '*' works correctly, signing all packages in
                a repository."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                plist = self.pkgsend_bulk(self.rurl1, self.var_pkg)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s '*'" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ch"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ch1_ta4_crl.pem"),
                    os.path.join(rstore.file_root, "ch", "ch1_ta4_crl.pem"))

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # Check that when the check-certificate-revocation is False, its
                # default value, that the install succeedes.
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("set-property check-certificate-revocation true")
                self.pkg("verify", su_wrap=True, exit=1)
                self._api_uninstall(api_obj, ["example_pkg"])
                api_obj.reset()
                self.assertRaises(apx.RevokedCertificate, self._api_install,
                    api_obj, ["example_pkg"])
                # Test that cli handles RevokedCertificate exception.
                self.pkg("install example_pkg", exit=1)

        def test_crl_2(self):
                """Test that revoking a code signing certificate by the
                publisher CA works correctly."""

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ta"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ta5_crl.pem"),
                    os.path.join(rstore.file_root, "ta", "ta5_crl.pem"))

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta5_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta5_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta5_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta5")
                self.pkg("set-property check-certificate-revocation true")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])

        def test_crl_3(self):
                """Test that a CRL with a bad file format does not cause
                breakage."""

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ex"))
                portable.copyfile(os.path.join(self.test_root,
                    "tmp/example_file"),
                    os.path.join(rstore.file_root, "ex", "example_file"))

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs2_ch1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs2_ch1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")
                self.pkg("set-property check-certificate-revocation true")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_crl_4(self):
                """Test that a CRL which cannot be retrieved does not cause
                breakage."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs2_ch1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs2_ch1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")
                self.pkg("set-property check-certificate-revocation true")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_crl_5(self):
                """Test that revocation by CRL validated by a grandparent of the
                certificate in question works."""

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ch"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ch5_ta1_crl.pem"),
                    os.path.join(rstore.file_root, "ch", "ch5_ta1_crl.pem"))

                self.dcs[1].start()

                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs2_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs2_ch5_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem"),
                      "pkg": plist[0]
                    }

                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")
                self.pkg("set-property check-certificate-revocation true")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RevokedCertificate, self._api_install,
                    api_obj, ["example_pkg"])

        def test_crl_6(self):
                """Test that revocation by CRL validated by an intermediate
                certificate of the certificate in question works."""

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ch"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ch5_ta1_crl.pem"),
                    os.path.join(rstore.file_root, "ch", "ch5_ta1_crl.pem"))

                self.dcs[1].start()

                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir, "cs2_ch5_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs2_ch5_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5_ta1_cert.pem"),
                      "pkg": plist[0]
                    }

                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")
                self.pkg("set-property check-certificate-revocation true")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RevokedCertificate, self._api_install,
                    api_obj, ["example_pkg"])

        def test_crl_7(self):
                """Test that a CRL location which isn't in a known URI format
                doesn't cause breakage."""

                r = self.get_repo(self.dcs[1].get_repodir())
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs3_ch1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs3_ch1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")
                self.pkg("set-property check-certificate-revocation true")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidResourceLocation,
                    self._api_install, api_obj, ["example_pkg"])
                # Test that the cli can handle a InvalidResourceLocation
                # exception.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("verify", exit=1)

        def test_crl_8(self):
                """Test that if two packages share the same CRL, it's only
                downloaded once even if it can't be stored permanently in the
                image."""

                def cnt_crl_contacts(log_path):
                        c = 0
                        with open(log_path, "rb") as fh:
                                for line in fh:
                                        if "ch1_ta4_crl.pem" in line:
                                                c += 1
                        return c

                r = self.get_repo(self.dcs[1].get_repodir())
                rstore = r.get_pub_rstore(pub="test")
                os.makedirs(os.path.join(rstore.file_root, "ch"))
                portable.copyfile(os.path.join(self.crl_dir,
                    "ch1_ta4_crl.pem"),
                    os.path.join(rstore.file_root, "ch", "ch1_ta4_crl.pem"))

                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.var_pkg])

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": " ".join(plist),
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg", "var_pkg"])
                self.pkg("set-property check-certificate-revocation true")
                # Check that the server is only contacted once per CRL, not once
                # per package with that CRL.
                self.pkg("verify", su_wrap=True, exit=1)
                self.assertEqual(cnt_crl_contacts(self.dcs[1].get_logpath()), 1)
                self.pkg("verify", exit=1)
                # Pkg should contact the server once more then store it in its
                # permanent location.
                self.assertEqual(cnt_crl_contacts(self.dcs[1].get_logpath()), 2)
                # Check that once the crl file is in its permanent location,
                # it's not retrieved again.
                self.pkg("verify", su_wrap=True, exit=1)
                self.assertEqual(cnt_crl_contacts(self.dcs[1].get_logpath()), 2)
                self.pkg("verify", exit=1)
                self.assertEqual(cnt_crl_contacts(self.dcs[1].get_logpath()), 2)

        def test_var_pkg(self):
                """Test that actions tagged with variants don't break signing.
                """

                plist = self.pkgsend_bulk(self.rurl1, self.var_pkg)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(pkg)s" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "pkg": plist[0]
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--variant variant.arch=i386")
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["var_pkg"])
                self.assert_(os.path.exists(os.path.join(self.img_path(), "baz")))
                self.assert_(not os.path.exists(
                    os.path.join(self.img_path(), "bin")))

                self.pkg("verify")

        def test_disabled_append(self):
                """Test that publishing to a depot which doesn't support append
                fails as expected."""

                self.dcs[1].set_disable_ops(["append"])
                self.dcs[1].start()

                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % {
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
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
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
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
                    "key": os.path.join(self.keys_dir, "cs1_ch1_ta3_key.pem"),
                    "cert": os.path.join(self.cs_dir, "cs1_ch1_ta3_cert.pem"),
                    "i1": os.path.join(self.chain_certs_dir,
                        "ch1_ta3_cert.pem"),
                    "pkg": plist[0]
                }
                self.pkgsign(self.durl1, sign_args, exit=1)

        def test_expired_certs(self):
                """Test that expiration dates on the signing cert are
                ignored."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs3_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs3_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs4_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs4_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self._api_install(api_obj, ["example_pkg"])

        def test_expired_chain_certs(self):
                """Test that expiration dates on a chain cert are ignored."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.2_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.2_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1.2_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This should succeed because we currently ignore certificate
                # expiration and start dates.
                self._api_install(api_obj, ["example_pkg"])

        def test_future_chain_certs(self):
                """Test that expiration dates on a chain cert are ignored."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.3_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.3_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1.3_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.var_pkg)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                ca_path = os.path.join(os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem"))

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": ca_path
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property signature-policy=require-signatures")
                self.pkg("set-publisher --approve-ca-cert %s test" % ca_path)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_higher_signature_version(self):

                r = self.get_repo(self.dcs[1].get_repodir())
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
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

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                # This changes the default image we're operating on.
                self.set_image(1)
                self.image_create(self.rurl1, destroy=False)
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This raises an exception because the command is run from
                # within the sub-image, which has now trust anchors installed.
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                # This should work because the command is run from within the
                # original image which contains the trust anchors needed to
                # validate the chain.
                cmd_path = os.path.join(self.img_path(0), "pkg")
                api_obj = self.get_img_api_obj(cmd_path=cmd_path)
                self._api_install(api_obj, ["example_pkg"])
                # Check that the package is installed into the correct image.
                self.pkg("list example_pkg")
                self.pkg("-R %s list example_pkg" % self.img_path(0), exit=1)
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg"])
                # Repeat the test using the pkg command interface instead of the
                # api.
                self.pkg("-D simulate_cmdpath=%s -R %s install example_pkg" % \
                    (cmd_path, self.img_path()))
                self.pkg("list example_pkg")
                self.pkg("-R %s list example_pkg" % self.img_path(0), exit=1)

        def test_big_pathlen(self):
                """Test that a chain cert which has a larger pathlen value than
                is needed is allowed."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir,
                          "cs1_ch5.2_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir,
                          "cs1_ch5.2_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5.2_ta1_cert.pem"),
                      "pkg": plist[0]
                    }

                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_small_pathlen(self):
                """Test that a chain cert which has a smaller pathlen value than
                is needed is allowed."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s %(pkg)s" % {
                      "key": os.path.join(self.keys_dir,
                          "cs1_ch5.3_ta1_key.pem"),
                      "cert": os.path.join(self.cs_dir,
                          "cs1_ch5.3_ta1_cert.pem"),
                      "i1": os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      "i2": os.path.join(self.chain_certs_dir,
                          "ch2_ta1_cert.pem"),
                      "i3": os.path.join(self.chain_certs_dir,
                          "ch3_ta1_cert.pem"),
                      "i4": os.path.join(self.chain_certs_dir,
                          "ch4.3_ta1_cert.pem"),
                      "i5": os.path.join(self.chain_certs_dir,
                          "ch5.3_ta1_cert.pem"),
                      "pkg": plist[0]
                    }

                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.PathlenTooShort, self._api_install,
                    api_obj, ["example_pkg"])
                # Check that the cli hands PathlenTooShort exceptions.
                self.pkg("install example_pkg", exit=1)

        def test_bug_16861_1(self):
                """Test whether obsolete packages can be signed and still
                function."""

                plist = self.pkgsend_bulk(self.rurl1, obsolete_pkg)
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["obs"])

        def test_bug_16861_2(self):
                """Test whether renamed packages can be signed and still
                function."""

                plist = self.pkgsend_bulk(self.rurl1, [self.example_pkg10,
                    renamed_pkg, self.need_renamed_pkg])
                for name in plist:
                        sign_args = "-k %(key)s -c %(cert)s -i %(i1)s " \
                            "%(name)s" % {
                                "name": name,
                                "key": os.path.join(self.keys_dir,
                                    "cs1_ch1_ta3_key.pem"),
                                "cert": os.path.join(self.cs_dir,
                                    "cs1_ch1_ta3_cert.pem"),
                                "i1": os.path.join(self.chain_certs_dir,
                                    "ch1_ta3_cert.pem")
                        }
                        self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["need_renamed"])

        def test_bug_16867_1(self):
                """Test whether signing a package multiple times makes a package
                uninstallable."""

                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": chain_cert_path
                }
                self.pkgsign(self.rurl1, sign_args)
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_bug_16867_2(self):
                """Test whether signing a package which already has multiple
                identical signatures results in an error."""

                r = self.get_repo(self.dcs[1].get_repodir())
                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": chain_cert_path
                }
                self.pkgsign(self.rurl1, sign_args)

                mp = r.manifest(plist[0])
                with open(mp, "rb") as fh:
                        ls = fh.readlines()
                s = []
                for l in ls:
                        # Double all signature actions.
                        if l.startswith("signature"):
                                s.append(l)
                        s.append(l)
                with open(mp, "wb") as fh:
                        for l in s:
                                fh.write(l)
                # Rebuild the catalog so that hash verification for the manifest
                # won't cause problems.
                r.rebuild()
                # This should fail because the manifest already has identical
                # signature actions in it.
                self.pkgsign(self.rurl1, sign_args, exit=1)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                # This fails because the manifest contains duplicate signatures.
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.UnverifiedSignature, self._api_install,
                    api_obj, ["example_pkg"])

        def test_bug_16867_hashes_1(self):
                """Test whether signing a package a second time with hashes
                fails."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "%(name)s" % {
                        "name": plist[0],
                }
                self.pkgsign(self.rurl1, sign_args)
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_bug_16867_almost_identical(self):
                """Test whether signing a package which already has a similar
                but not identical signature results in an error."""

                r = self.get_repo(self.dcs[1].get_repodir())
                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": chain_cert_path
                }
                self.pkgsign(self.rurl1, sign_args)

                mp = r.manifest(plist[0])
                with open(mp, "rb") as fh:
                        ls = fh.readlines()
                s = []
                for l in ls:
                        # Double all signature actions.
                        if l.startswith("signature"):
                                a = action.fromstr(l)
                                a.attrs["value"] = "foo"
                                s.append(str(a))
                        else:
                                s.append(l)
                with open(mp, "wb") as fh:
                        for l in s:
                                fh.write(l)
                # Rebuild the catalog so that hash verification for the manifest
                # won't cause problems.
                r.rebuild()
                # This should fail because the manifest already has almost
                # identical signature actions in it.
                self.pkgsign(self.rurl1, sign_args, exit=1)

        def test_bug_17740_default_pub(self):
                """Test that signing a package in the default publisher of a
                multi-publisher repository works."""

                self.pkgrepo("add_publisher -s %s pub2" % self.rurl1)
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": "'ex*'",
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p %s" % self.rurl1)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, plist)

        def test_bug_17740_alternate_pub(self):
                """Test that signing a package in an alternate publisher of a
                multi-publisher repository works."""

                self.pkgrepo("add_publisher -s %s pub2" % self.rurl1)
                plist = self.pkgsend_bulk(self.rurl1, self.pub2_pkg)

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": "'*2pk*'",
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p %s" % self.rurl1)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, plist)

        def test_bug_17740_name_collision_1(self):
                """Test that when two publishers have packages with the same
                name, the publisher in the sign command is respected.  This test
                signs the package from the default publisher."""

                self.pkgrepo("add_publisher -s %s pub2" % self.rurl1)
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.pub2_example])

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": "pkg://test/example_pkg",
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p %s" % self.rurl1)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["pkg://pub2/example_pkg"])
                self._api_install(api_obj, ["pkg://test/example_pkg"])

        def test_bug_17740_name_collision_2(self):
                """Test that when two publishers have packages with the same
                name, the publisher in the sign command is respected.  This test
                signs the package from the non-default publisher."""

                self.pkgrepo("add_publisher -s %s pub2" % self.rurl1)
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.pub2_example])

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": "pkg://pub2/example_pkg",
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p %s" % self.rurl1)
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["pkg://test/example_pkg"])
                self._api_install(api_obj, ["pkg://pub2/example_pkg"])

        def test_bug_17740_anarchistic_pkg(self):
                """Test that signing a package present in both repositories
                signs both packages."""

                self.pkgrepo("add_publisher -s %s pub2" % self.rurl1)
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.pub2_example])

                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": "example_pkg",
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p %s" % self.rurl1)
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["pkg://test/example_pkg"])
                self._api_uninstall(api_obj, ["example_pkg"])
                self._api_install(api_obj, ["pkg://pub2/example_pkg"])

        def test_18620(self):
                """Test that verifying a signed package doesn't require
                privs."""

                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                ta_cert_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta3_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s %(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": chain_cert_path
                }

                # Specify location as filesystem path.
                self.pkgsign(self.dc.get_repodir(), sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy ignore")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("set-property signature-policy verify")
                self.pkg("verify", su_wrap=True)

        def test_bug_18880_hash(self):
                plist = self.pkgsend_bulk(self.rurl1, self.bug_18880_pkg)
                self.pkgsign(self.rurl1, plist[0])
                self.image_create(self.rurl1, variants={"variant.foo":"bar"})
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["b18880"])
                self.pkg("verify")
                self.pkg("fix")
                portable.remove(os.path.join(self.img_path(),
                    "bin/example_path"))
                self.pkg("verify", exit=1)
                self.assert_("signature" not in self.errout)
                self.pkg("fix")
                self.assert_("signature" not in self.errout)

        def test_bug_18880_sig(self):
                plist = self.pkgsend_bulk(self.rurl1, self.bug_18880_pkg)
                sign_args = "-k %(key)s -c %(cert)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      "pkg": plist[0]
                    }
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1, variants={"variant.foo":"bar"})
                api_obj = self.get_img_api_obj()
                self.seed_ta_dir("ta2")
                self._api_install(api_obj, ["b18880"])
                self.pkg("verify")
                self.pkg("fix")
                portable.remove(os.path.join(self.img_path(),
                    "bin/example_path"))
                self.pkg("verify", exit=1)
                self.assert_("signature" not in self.errout)
                self.pkg("fix")
                self.assert_("signature" not in self.errout)


class TestPkgSignMultiDepot(pkg5unittest.ManyDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

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

        foo10 = """
            open foo@1.0,5.11-0
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
                pkg5unittest.ManyDepotTestCase.pkg_image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path(), f), "wb") as fh:
                                fh.close()

        def image_create(self, *args, **kwargs):
                pkg5unittest.ManyDepotTestCase.image_create(self,
                    *args, **kwargs)
                self.ta_dir = os.path.join(self.img_path(), "etc/certs/CA")
                os.makedirs(self.ta_dir)
                for f in self.image_files:
                        with open(os.path.join(self.img_path(), f), "wb") as fh:
                                fh.close()

        def pkg(self, command, *args, **kwargs):
                # The value for crl_host is pulled from DebugValues because
                # crl_host needs to be set there so the api object calls work
                # as desired.
                command = "--debug crl_host=%s %s" % \
                    (DebugValues["crl_host"], command)
                return pkg5unittest.ManyDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self,
                    ["test", "test", "crl"])
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                DebugValues["crl_host"] = self.dcs[3].get_depot_url()
                self.ta_dir = None

                self.path_to_certs = os.path.join(self.ro_data_root,
                    "signing_certs", "produced")
                self.keys_dir = os.path.join(self.path_to_certs, "keys")
                self.cs_dir = os.path.join(self.path_to_certs,
                    "code_signing_certs")
                self.chain_certs_dir = os.path.join(self.path_to_certs,
                    "chain_certs")
                self.raw_trust_anchor_dir = os.path.join(self.path_to_certs,
                    "trust_anchors")
                self.crl_dir = os.path.join(self.path_to_certs, "crl")

        def test_sign_pkgrecv(self):
                """Check that signed packages can be transferred between
                repos."""

                plist = self.pkgsend_bulk(self.rurl2, self.example_pkg10)
                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                sign_args = "-k %(key)s -c %(cert)s -i %(ta)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      "ta": ta_path,
                      "pkg": plist[0]
                    }

                self.pkgsign(self.rurl2, sign_args)

                repo_location = self.dcs[1].get_repodir()
                self.pkgrecv(self.rurl2, "-d %s example_pkg" % self.rurl1)
                shutil.rmtree(repo_location)
                self.pkgrepo("create %s" % repo_location)

                # Add another signature which includes the same chain cert used
                # in the first signature.
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s -i %(ta)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "ta": ta_path,
                }
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d %s example_pkg" % self.rurl1)
                shutil.rmtree(repo_location)
                self.pkgrepo("create %s" % repo_location)

                # Add another signature to further test duplicate chain
                # certificates as well as having a chain cert that's a signing
                # certificate in other signatures.
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s -i %(ch1)s -i %(ta)s " \
                    "-i %(cs1_ch1_ta3)s %(name)s " % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch5_ta1_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch5_ta1_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta1_cert.pem"),
                        "i2": os.path.join(self.chain_certs_dir,
                            "ch2_ta1_cert.pem"),
                        "i3": os.path.join(self.chain_certs_dir,
                            "ch3_ta1_cert.pem"),
                        "i4": os.path.join(self.chain_certs_dir,
                            "ch4_ta1_cert.pem"),
                        "i5": os.path.join(self.chain_certs_dir,
                            "ch5_ta1_cert.pem"),
                        "ta": ta_path,
                        "ch1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "cs1_ch1_ta3": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                }
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d %s example_pkg" % self.rurl1)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")
                self.seed_ta_dir("ta2")
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_pkgrecv_a(self):
                """Check that signed packages can be archived."""

                plist = self.pkgsend_bulk(self.rurl2, self.example_pkg10)

                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                sign_args = "-k %(key)s -c %(cert)s -i %(ta)s %(pkg)s" % \
                    { "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      "ta": ta_path,
                      "pkg": plist[0]
                    }

                self.pkgsign(self.rurl2, sign_args)

                arch_location = os.path.join(self.test_root, "pkg_arch")
                self.pkgrecv(self.rurl2, "-a -d %s example_pkg" % arch_location)
                portable.remove(arch_location)

                # Add another signature which includes the same chain cert used
                # in the first signature.
                sign_args = "-k %(key)s -c %(cert)s -i %(ch1)s -i %(ta)s " \
                    "%(name)s" % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "ta": ta_path,
                }
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-a -d %s example_pkg" % arch_location)
                portable.remove(arch_location)

                # Add another signature to further test duplicate chain
                # certificates as well as having a chain cert that's a signing
                # certificate in other signatures.
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s -i %(i2)s " \
                    "-i %(i3)s -i %(i4)s -i %(i5)s -i %(ch1)s -i %(ta)s " \
                    "-i %(cs1_ch1_ta3)s %(name)s " % {
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch5_ta1_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch5_ta1_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1_ta1_cert.pem"),
                        "i2": os.path.join(self.chain_certs_dir,
                            "ch2_ta1_cert.pem"),
                        "i3": os.path.join(self.chain_certs_dir,
                            "ch3_ta1_cert.pem"),
                        "i4": os.path.join(self.chain_certs_dir,
                            "ch4_ta1_cert.pem"),
                        "i5": os.path.join(self.chain_certs_dir,
                            "ch5_ta1_cert.pem"),
                        "ta": ta_path,
                        "ch1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "cs1_ch1_ta3": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                }
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-a -d %s example_pkg" % arch_location)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")
                self.seed_ta_dir("ta2")
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self.pkg("install -g file://%s example_pkg" % arch_location)

        def test_bug_16861_recv(self):
                """Check that signed obsolete and renamed packages can be
                transferred from one repo to another."""

                plist = self.pkgsend_bulk(self.rurl2, [renamed_pkg,
                    obsolete_pkg])
                for name in plist:
                        sign_args = "-k %(key)s -c %(cert)s -i %(i1)s " \
                            "-i %(i2)s -i %(i3)s -i %(i4)s -i %(i5)s " \
                            "%(name)s" % {
                                "name": name,
                                "key": os.path.join(self.keys_dir,
                                    "cs1_ch5_ta1_key.pem"),
                                "cert": os.path.join(self.cs_dir,
                                    "cs1_ch5_ta1_cert.pem"),
                                "i1": os.path.join(self.chain_certs_dir,
                                    "ch1_ta1_cert.pem"),
                                "i2": os.path.join(self.chain_certs_dir,
                                    "ch2_ta1_cert.pem"),
                                "i3": os.path.join(self.chain_certs_dir,
                                    "ch3_ta1_cert.pem"),
                                "i4": os.path.join(self.chain_certs_dir,
                                    "ch4_ta1_cert.pem"),
                                "i5": os.path.join(self.chain_certs_dir,
                                    "ch5_ta1_cert.pem"),
                        }
                        self.pkgsign(self.rurl2, sign_args)

                self.pkgrecv(self.rurl2, "-d %s renamed obs" % self.rurl1)

        def test_bug_18463(self):
                """Check that the crl host is only contacted once, instead of
                once per package."""

                self.dcs[3].start()

                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.foo10])
                sign_args = "-k %(key)s -c %(cert)s -i %(i1)s %(name)s" % {
                        "name": "%s %s" % (plist[0], plist[1]),
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1.1_ta4_cert.pem")
                }
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta4")
                self.pkg("set-property check-certificate-revocation true")
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg", "foo"])
                cnt = 0
                with open(self.dcs[3].get_logpath(), "rb") as fh:
                        for l in fh:
                                if "ch1.1_ta4_crl.pem" in l:
                                        cnt += 1
                self.assertEqual(cnt, 1)


if __name__ == "__main__":
        unittest.main()
