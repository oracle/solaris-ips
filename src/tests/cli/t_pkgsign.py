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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
from . import testutils
if __name__ == "__main__":
        testutils.setup_environment("../../../proto")
import pkg5unittest

import os
import re
import shutil
import sys
import tempfile
import unittest

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

import pkg.actions as action
import pkg.actions.signature as signature
import pkg.client.api_errors as apx
import pkg.digest as digest
import pkg.facet as facet
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.portable as portable

from pkg.client.debugvalues import DebugValues
from pkg.pkggzip import PkgGzipFile

try:
        import pkg.sha512_t
        sha512_supported = True
except ImportError:
        sha512_supported = False

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
            add dir mode=0755 owner=root group=bin path=/usr/lib/python2.7/vendor-packages/OpenSSL
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
            add set name=com.sun.service.incorporated_changes value="6556919 6627937"
            add set name=com.sun.service.random_test value=42 value=79
            add set name=com.sun.service.bug_ids value="4641790 4725245 4817791 4851433 4897491 4913776 6178339 6556919 6627937"
            add set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"
            add set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z
            add set description='FOOO bAr O OO OOO'
            add set name='weirdness' value='] [ * ?'
            close """

        example_pkg20 = """
            open example_pkg@2.0,5.11-0
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

        facet_pkg = """
            open facet_pkg@1.0,5.11-0
            add set name=variant.arch value=sparc value=i386
            add file tmp/example_file mode=0444 owner=root group=bin path=usr/share/doc/i386_doc.txt facet.doc=true variant.arch=i386
            add file tmp/example_file mode=0444 owner=root group=bin path=usr/share/doc/sparc_devel.txt facet.devel=true variant.arch=sparc
            close """

        med_pkg = """
            open med_pkg@1.0,5.11-0
            add file tmp/example_file mode=0755 owner=root group=bin path=/bin/example-1.6
            add file tmp/example_file mode=0755 owner=root group=bin path=/bin/example-1.7
            add link path=bin/example target=bin/example-1.6 mediator=example mediator-version=1.6
            add link path=bin/example target=bin/example-1.7 mediator=example mediator-version=1.7
            close """

        conflict_pkgs = """
            open conflict_a_pkg@1.0,5.11-0
            add file tmp/example_file mode=0444 owner=root group=root path=etc/release
            close
            open conflict_b_pkg@1.0,5.11-0
            add file tmp/example_file2 mode=0444 owner=root group=root path=etc/release
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

        def pkg(self, command, *args, **kwargs):
                # The value for crl_host is pulled from DebugValues because
                # crl__host needs to be set there so the api object calls work
                # as desired.
                command = "--debug crl_host={0} {1}".format(
                    DebugValues["crl_host"], command)
                return pkg5unittest.SingleDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self, image_count=2)
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                DebugValues["crl_host"] = self.durl1

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
                sign_args = "-k {key} -c {cert} -i {ch1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=chain_cert_path
                )
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
                self.pkg("set-publisher --revoke-ca-cert={0} test".format(hsh))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.BrokenChain, self._api_install, api_obj,
                    ["example_pkg"])
                self.pkg("set-publisher --approve-ca-cert={0} test".format(
                    chain_cert_path))
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])
                self.pkg("set-publisher --revoke-ca-cert={0} test".format(hsh))
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
                self.pkg("fix", exit=4)
                self.pkg("set-publisher --set-property signature-policy=verify "
                    "test")
                # These should fail because the publisher, though not the image
                # verifies signatures.
                self.pkg("verify", exit=1)
                self.pkg("fix", exit=1)
                self.pkg("set-publisher --approve-ca-cert={0} test".format(
                    chain_cert_path))
                self.pkg("verify")
                self.pkg("fix", exit=4)
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg"])

                # Test that manually approving a trust anchor works.
                self.pkg("set-publisher --unset-ca-cert={0} test".format(hsh))
                self.pkg("set-publisher --approve-ca-cert={0} test".format(
                    ta_cert_path))
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_2(self):
                """Test that verification of the CS cert failing means the
                install fails."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"))

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
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} -i {i6} {pkg}".format(**{
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
                    })

                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_multiple_signatures(self):
                """Test that having a package signed with more than one
                signature doesn't cause anything to break."""

                self.base_multiple_signatures("sha256")
                if sha512_supported:
                        self.base_multiple_signatures("sha512t_256")

        def test_no_empty_chain(self):
                """Test that signing do not create empty chain"""
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10,
                    debug_hash="sha1+sha512t_256")
                sign_args = "-k {key} -c {cert} {pkg}".format(**{
                    "key": os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                    "cert": os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                    "pkg": plist[0]})

                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta2")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

                # Make sure signing haven't created empty chain attrs
                self.pkg("contents -m")
                self.assertTrue(self.output.count("chain=") == 0)

        def base_multiple_signatures(self, hash_alg):
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {pkg}".format(**{
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
                    })
                self.pkgsign(self.rurl1, sign_args,
                    debug_hash="sha1+{0}".format(hash_alg))

                sign_args = "-k {key} -c {cert} {name}".format(
                    name=plist[0],
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                    cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"))

                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir(["ta1", "ta2"])
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

                # Make sure we've got exactly 1 signature with SHA2 hashes
                self.pkg("contents -m")
                self.assertTrue(self.output.count("pkg.chain.{0}".format(hash_alg)) == 1)
                self.assertTrue(self.output.count("pkg.chain.chashes") == 1)
                # and SHA1 hashes on both signatures
                self.assertTrue(self.output.count("chain=") == 1)
                self.assertTrue(self.output.count("chain.chashes=") == 1)

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
                sign_args = "-k {key} -c {cert} -i {i2} -i {i3} "\
                    "-i {i4} -i {i5} {pkg}".format(**{
                        "key": os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
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
                    })
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")

                self.pkg("install example_pkg", exit=1)

        def base_sign_5(self):
                """Test that http repos work."""

                self.dcs[1].start()
                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {pkg}".format(**{
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
                    })
                self.pkgsign(self.durl1, sign_args)
                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta1")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_5(self):
                """Test that http repos work."""

                self.base_sign_5()

                # Verify that older logic of publication api works.
                self.dcs[1].stop()
                self.dcs[1].set_disable_ops(["manifest/1"])
                self.base_sign_5()

        def test_length_two_chains(self):
                """Check that chains of length two work correctly."""

                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {ta} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      ta=ta_path,
                      pkg=plist[0]
                   )

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
                sign_args = "-k {key} -c {cert} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      pkg=plist[0]
                   )

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

                # Test that passing a repo that doesn't exist doesn't cause
                # a traceback.
                self.pkgsign("http://foobar.baz",
                    "{name}".format(name=plist[0]), exit=1)

                # Test that passing no fmris or patterns results in an error.
                self.pkgsign(self.durl1, "", exit=2)

                # Test bad sig.alg setting.
                self.pkgsign(self.durl1, "-a foo -k {key} -c {cert} "
                    "{name}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]), exit=2)

                # Test missing cert option
                self.pkgsign(self.durl1, "-k {key} {name}".format(
                    key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      name=plist[0]), exit=2)
                # Test missing key option
                self.pkgsign(self.durl1, "-c %(cert) {name}".format(
                    cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]), exit=2)
                # Test -i with missing -c and -k
                self.pkgsign(self.durl1, "-i {i1} {name}".format(
                    i1=os.path.join(self.chain_certs_dir,
                          "ch1_ta1_cert.pem"),
                      name=plist[0]), exit=2)
                # Test passing a cert as a key
                self.pkgsign(self.durl1, "-c {cert} -k {cert} {name}".format(
                    cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]), exit=1)
                # Test passing a non-existent certificate file
                self.pkgsign(self.durl1, "-c /shouldnotexist -k {key} "
                    "{name}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      name=plist[0]), exit=2)
                # Test passing a non-existent key file
                self.pkgsign(self.durl1, "-c {cert} -k /shouldnotexist "
                    "{name}".format(
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]), exit=2)
                # Test passing a file that's not a key file as a key file
                self.pkgsign(self.durl1, "-k {key} -c {cert} {name}".format(
                    key=os.path.join(self.test_root, "tmp/example_file"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]), exit=1)
                # Test passing a non-existent file as an intermediate cert
                self.pkgsign(self.durl1, "-k {key} -c {cert} -i {i1} "
                    "{name}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      i1=os.path.join(self.chain_certs_dir,
                          "shouldnot/exist"),
                      name=plist[0]), exit=2)
                # Test passing a directory as an intermediate cert
                self.pkgsign(self.durl1, "-k {key} -c {cert} -i {i1} "
                    "{name}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      i1=self.chain_certs_dir,
                      name=plist[0]), exit=2)
                # Test setting the signature algorithm to be one which requires
                # a key and cert, but not passing -k or -c.
                self.pkgsign(self.durl1, "-a rsa-sha256 {0}".format(plist[0]), exit=2)
                # Test setting the signature algorithm to be one which does not
                # use a key and cert, but passing -k and -c.
                self.pkgsign(self.durl1, "-a sha256 -k {key} -c {cert} "
                    "{name}".format(
                      key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]), exit=2)
                # Test that signing a package using a bogus certificate fails.
                self.pkgsign(self.durl1, "-k {key} -c {cert} {name}".format(
                    key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.test_root, "tmp/example_file"),
                      name=plist[0]), exit =1)
                self.pkg_image_create(self.durl1)
                self.pkg("set-property signature-policy verify")
                self.pkg("set-property trust-anchor-directory {0}".format(
                    os.path.join("simple_file")))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidPropertyValue, self._api_install,
                    api_obj, ["example_pkg"])
                # Test that the cli handles an InvalidPropertyValue exception.
                self.pkg("install example_pkg", exit=1)

        def test_bad_opts_2(self):
                """Test that having a bogus trust anchor will stop install."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign(self.rurl1, "-k {key} -c {cert} {name}".format(
                    key=os.path.join(self.keys_dir, "cs1_ch5_ta1_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ch5_ta1_cert.pem"),
                      name=plist[0]))
                self.pkg_image_create(self.rurl1)
                self.pkg("set-property signature-policy verify")
                self.pkg("set-property trust-anchor-directory {0}".format(
                    os.path.join("simple_file")))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidPropertyValue, self._api_install,
                    api_obj, ["example_pkg"])

        def test_dry_run_option(self):
                """Test that -n doesn't actually sign packages."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-n -k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(additional_args=\
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["example_pkg"])

        def test_multiple_hash_algs(self):
                """Test that signing with other hash algorithms works
                correctly."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign_simple(self.rurl1, plist[0])

                sign_args = "-a rsa-sha512 -k {key} -c {cert} -i {i1} " \
                    "{name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)

                sign_args = "-a sha384 {name}".format(name=plist[0])
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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
                sign_args = "{name}".format(name=plist[0])
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)

                # Make sure the manifest is locally stored.
                self.pkg("install -n example_pkg")
                # Append an action to the manifest.
                pfmri = fmri.PkgFmri(plist[0])
                s = self.get_img_manifest(pfmri)
                s += "\nset name=foo value=bar"
                self.write_img_manifest(pfmri, s)

                DebugValues["manifest_validate"] = "Never"

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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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

                DebugValues["manifest_validate"] = "Never"

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
                self.pkg("--debug manifest_validate=Never install "
                    "example_pkg", exit=1)
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs2_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs2_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1.1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1.1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1.1_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {name}".format(**{
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
                })
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
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "{name}".format(**{
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_cs8_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_cs8_ch1_ta3_cert.pem"),
                        "i1": os.path.join(self.cs_dir,
                            "cs8_ch1_ta3_cert.pem"),
                        "i2": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                })
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
                sign_args = "-k {key} -c {cert} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "ch1_ta3_key.pem"),
                        cert=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1.1_ta4_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1.1_ta4_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1.1_ta4_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)

                self.dcs[1].start()

                self.pkg_image_create(self.durl1)
                self.seed_ta_dir("ta4")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                # This succeeds because the CA which signed the revoking CRL
                # did not have the cRLSign keyUsage extension set.
                self._api_install(api_obj, ["example_pkg"])

        def test_invalid_extension_1(self):
                """Test that an invalid value in the extension causes an
                exception to be raised."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs9_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs9_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidCertificateExtensions,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli can handle an InvalidCertificateExtensions.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_invalid_extension_2(self):
                """Test that a critical extension that Cryptography can't
                understand causes an exception to be raised."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cust_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cust_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("cust")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.InvalidCertificateExtensions,
                    self._api_install, api_obj, ["example_pkg"])
                # Tests that the cli can handle an InvalidCertificateExtensions.
                self.pkg("install example_pkg", exit=1)
                self.pkg("set-property signature-policy ignore")
                self.pkg("set-publisher --set-property signature-policy=ignore "
                    "test")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_keyusage_values(self):
                """Test that more keyUsage extension values are supported."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs5_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs5_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_unset_keyUsage_for_code_signing(self):
                """Test that if keyUsage has not been set, the code signing
                certificate is considered valid."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs7_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs7_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1.4_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1.4_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1.4_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_no_server_update(self):
                """Test --no-index and --no-catalog."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "--no-index --no-catalog -i {i1} -k {key} " \
                    "-c {cert} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} " \
                    "{name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=cs_path,
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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

                with open(os.path.join(self.crl_dir, "ch1_ta4_crl.pem"),
                    "rb") as f:
                        crl = x509.load_pem_x509_crl(
                            f.read(), default_backend())

                with open(os.path.join(self.cs_dir,
                    "cs1_ch1_ta4_cert.pem"), "rb") as f:
                        cert = x509.load_pem_x509_certificate(
                            f.read(), default_backend())

                self.assertTrue(crl.issuer == cert.issuer)
                for rev in crl:
                        if rev.serial_number == cert.serial:
                                break
                else:
                        self.assertTrue(False, "Can not find revoked "
                            "certificate in CRL!")

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

                self.pkgsign_simple(self.rurl1, "'*'")

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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta4_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta4_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem"))
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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta5_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta5_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta5_cert.pem"))
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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs2_ch1_ta4_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs2_ch1_ta4_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem"))
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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs2_ch1_ta4_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs2_ch1_ta4_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {pkg}".format(**{
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
                    })

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
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {pkg}".format(**{
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
                    })

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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs3_ch1_ta4_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs3_ch1_ta4_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem"))
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
                        with open(log_path, "r") as fh:
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

                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=" ".join(plist),
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta4_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta4_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta4_cert.pem"))
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

        def __setup_signed_simple(self, pkg_srcs, pkg_names):
                plist = self.pkgsend_bulk(self.rurl1, pkg_srcs)

                for pfmri in plist:
                        self.pkgsign_simple(self.rurl1, pfmri)

                self.pkg_image_create(self.rurl1,
                    additional_args="--variant variant.arch=i386")
                self.seed_ta_dir("ta3")

                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, pkg_names)
                return api_obj

        def test_var_pkg(self):
                """Test that actions tagged with variants don't break signing.
                """

                api_obj = self.__setup_signed_simple([self.var_pkg],
                    ["var_pkg"])
                self.pkg("verify")
                self.assertTrue(os.path.exists(os.path.join(self.img_path(),
                    "baz")))
                self.assertTrue(not os.path.exists(
                    os.path.join(self.img_path(), "bin")))

                # verify changing variant after install also works
                self._api_change_varcets(api_obj,
                    variants={ "variant.arch": "sparc" },
                    refresh_catalogs=False)

                self.assertTrue(not os.path.exists(
                    os.path.join(self.img_path(), "baz")))
                self.assertTrue(os.path.exists(
                    os.path.join(self.img_path(), "bin")))
                self.pkg("verify")

        def test_facet_pkg(self):
                """Test that actions tagged with facets don't break signing."""

                api_obj = self.__setup_signed_simple([self.facet_pkg],
                    ["facet_pkg"])
                self.pkg("verify")
                self.assertTrue(os.path.exists(os.path.join(self.img_path(),
                    "usr", "share", "doc", "i386_doc.txt")))
                self.assertTrue(not os.path.exists(os.path.join(self.img_path(),
                    "usr", "share", "doc", "sparc_devel.txt")))

                # verify changing facet after install also works
                nfacets = facet.Facets({ "facet.doc": False })
                self._api_change_varcets(api_obj, facets=nfacets,
                    refresh_catalogs=False)
                self.assertTrue(not os.path.exists(os.path.join(self.img_path(),
                    "usr", "share", "doc", "i386_doc.txt")))
                self.assertTrue(not os.path.exists(os.path.join(self.img_path(),
                    "usr", "share", "doc", "sparc_devel.txt")))
                self.pkg("verify")

        def test_mediator_pkg(self):
                """Test that actions tagged with mediators don't break
                signing."""

                def check_target(links, target):
                        for lpath in links:
                                ltarget = os.readlink(lpath)
                                self.assertTrue(ltarget.endswith(target))

                api_obj = self.__setup_signed_simple([self.med_pkg],
                    ["med_pkg"])
                self.pkg("verify")

                # verify /bin/example mediation points to example-1.7 by default
                ex_link = self.get_img_file_path("bin/example")
                check_target([ex_link], "example-1.7")

                # verify changing mediation after install works as expected
                self.pkg("set-mediator -V1.6 example")
                check_target([ex_link], "example-1.6")
                self.pkg("verify")

                # Verify removal of mediated links when no mediation applies
                # works as expected.
                self.pkg("set-mediator -V1.8 example")
                self.assertTrue(not os.path.exists(ex_link))
                self.pkg("verify")

                # Verify mediated links are restored when mediation is reset.
                self.pkg("set-property signature-policy require-signatures")
                self.pkg("set-mediator -V1.6 example")
                check_target([ex_link], "example-1.6")
                self.pkg("verify")

        def test_fix_revert_pkg(self):
                """Test that fix and revert works with signed packages."""

                api_obj = self.__setup_signed_simple([self.facet_pkg],
                    ["facet_pkg"])
                self.pkg("verify")
                doc_path = self.get_img_file_path("usr/share/doc/i386_doc.txt")
                self.assertTrue(os.path.exists(doc_path))

                # Remove doc, then verify that fix and revert will restore it.
                for cmd in ("fix", "revert usr/share/doc/i386_doc.txt"):
                        portable.remove(doc_path)
                        self.assertTrue(not os.path.exists(doc_path))
                        self.pkg(cmd)
                        self.assertTrue(os.path.exists(doc_path))

        def test_conflicting_pkgs(self):
                """Test that conflicting package repair works with signed
                packages."""

                DebugValues["broken-conflicting-action-handling"] = 1
                try:
                        # Install conflicting packages.
                        api_obj = self.__setup_signed_simple([self.conflict_pkgs],
                            ["conflict_a_pkg", "conflict_b_pkg"])
                        rel_path = self.get_img_file_path("etc/release")
                        self.assertTrue(os.path.exists(rel_path))
                finally:
                        del DebugValues["broken-conflicting-action-handling"]

                # Now remove one of the conflicting packages and verify that the
                # repair happens as expected.
                self._api_uninstall(api_obj, ["conflict_b_pkg"])
                self.pkg("verify")
                self.file_contains("etc/release", "tmp/example_file")

        def test_disabled_append(self):
                """Test that publishing to a depot which doesn't support append
                fails as expected."""

                self.dcs[1].set_disable_ops(["append"])
                self.dcs[1].start()

                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)

                self.pkgsign_simple(self.durl1, plist[0], exit=1)

        def test_disabled_add(self):
                """Test that publishing to a depot which doesn't support add
                fails as expected."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                # New publication uses manifest/1 to upload manifest as-is
                # and avoid using add ops. Disable manifest/1 to fall back
                # to older logic here for testing.
                self.dcs[1].set_disable_ops(["add", "manifest/1"])
                self.dcs[1].start()

                sign_args = "-k {key} -c {cert} {pkg}".format(
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        pkg=plist[0])
                self.pkgsign(self.durl1, sign_args, exit=1)

        def test_disabled_file(self):
                """Test that publishing to a depot which doesn't support file
                fails as expected."""

                # New publication uses manifest/1 which uses file/1, so if we
                # disable file ops, we can't use the new publication model.
                # Disable manifest/1 to fall back to older logic here for
                # testing.
                self.dcs[1].set_disable_ops(["file", "manifest/1"])
                self.dcs[1].start()

                plist = self.pkgsend_bulk(self.durl1, self.example_pkg10)

                self.pkgsign_simple(self.durl1, plist[0], exit=1)

        def test_expired_certs(self):
                """Test that expiration dates on the signing cert are
                ignored."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs3_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs3_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs4_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs4_ch1_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1.2_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1.2_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1.2_ta3_cert.pem"))
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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1.3_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1.3_ta3_cert.pem"),
                        i1=os.path.join(self.chain_certs_dir,
                            "ch1.3_ta3_cert.pem"))
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
                self.pkgsign_simple(self.rurl1, plist[0])

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
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        i1=ca_path)
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property signature-policy=require-signatures")
                self.pkg("set-publisher --approve-ca-cert {0} test".format(ca_path))
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_higher_signature_version(self):
                """Test that a signature version that isn't recognized is
                ignored."""

                r = self.get_repo(self.dcs[1].get_repodir())
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign_simple(self.rurl1, plist[0])
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
                        tmp = l.replace("version={0}".format(old_ver),
                            "version={0}".format(new_ver))
                        s.append(tmp)
                with open(mp, "w") as fh:
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
                self.pkgsign_simple(self.rurl1, plist[0])

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property "
                        "signature-policy=require-signatures")
                self.seed_ta_dir("ta3")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_using_pkg_image_cert_loc(self):
                """Test that trust anchors are properly pulled from the image
                that the pkg command was run from."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign_simple(self.rurl1, plist[0])

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
                self.pkg("-R {0} list example_pkg".format(self.img_path(0)), exit=1)
                api_obj = self.get_img_api_obj()
                self._api_uninstall(api_obj, ["example_pkg"])
                # Repeat the test using the pkg command interface instead of the
                # api.
                self.pkg("-D simulate_cmdpath={0} -R {1} install example_pkg".format(
                    cmd_path, self.img_path()))
                self.pkg("list example_pkg")
                self.pkg("-R {0} list example_pkg".format(self.img_path(0)), exit=1)

        def test_big_pathlen(self):
                """Test that a chain cert which has a larger pathlen value than
                is needed is allowed."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {pkg}".format(**{
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
                    })

                self.pkgsign(self.rurl1, sign_args)
                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")

                self.pkg("set-property signature-policy verify")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_small_pathlen(self):
                """Test that a chain cert which has a smaller pathlen value than
                is needed is disallowed."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} {pkg}".format(**{
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
                    })

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
                self.pkgsign_simple(self.rurl1, plist[0])

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property "
                        "signature-policy=require-signatures")
                self.seed_ta_dir("ta3")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["obs"])

        def test_bug_16861_2(self):
                """Test whether renamed packages can be signed and still
                function."""

                plist = self.pkgsend_bulk(self.rurl1, [self.example_pkg10,
                    renamed_pkg, self.need_renamed_pkg])
                for name in plist:
                        self.pkgsign_simple(self.rurl1, name)

                self.pkg_image_create(self.rurl1,
                    additional_args="--set-property "
                        "signature-policy=require-signatures")
                self.seed_ta_dir("ta3")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["need_renamed"])

        def test_bug_16867_1(self):
                """Test whether signing a package multiple times makes a package
                uninstallable."""

                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign_simple(self.rurl1, plist[0])
                self.pkgsign_simple(self.rurl1, plist[0])

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_bug_16867_2(self):
                """Test whether signing a package which already has multiple
                identical signatures results in an error."""

                r = self.get_repo(self.dcs[1].get_repodir())
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                self.pkgsign_simple(self.rurl1, plist[0])

                mp = r.manifest(plist[0])
                with open(mp, "r") as fh:
                        ls = fh.readlines()
                s = []
                for l in ls:
                        # Double all signature actions.
                        if l.startswith("signature"):
                                s.append(l)
                        s.append(l)
                with open(mp, "w") as fh:
                        for l in s:
                                fh.write(l)

                hash_alg_list = ["sha256"]
                if sha512_supported:
                        hash_alg_list.append("sha512t_256")
                for hash_alg in hash_alg_list:
                        # Rebuild the catalog so that hash verification for the
                        # manifest won't cause problems.
                        r.rebuild()
                        # This should fail because the manifest already has
                        # identical signature actions in it.
                        self.pkgsign_simple(self.rurl1, plist[0], exit=1)

                        # The addition of SHA-256 hashes should still result in
                        # us believing the signatures are identical.
                        self.pkgsign_simple(self.rurl1, plist[0], exit=1,
                            debug_hash="sha1+{0}".format(hash_alg))

                        self.pkg_image_create(self.rurl1)
                        self.seed_ta_dir("ta3")
                        self.pkg("set-property signature-policy verify")

                        # This fails because the manifest contains duplicate
                        # signatures.
                        api_obj = self.get_img_api_obj()
                        self.assertRaises(apx.UnverifiedSignature,
                                self._api_install, api_obj, ["example_pkg"])

        def test_bug_16867_hashes_1(self):
                """Test whether signing a package a second time with hashes
                fails."""

                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)
                sign_args = "{name}".format(
                        name=plist[0],
               )
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
                self.pkgsign_simple(self.rurl1, plist[0])

                mp = r.manifest(plist[0])
                with open(mp, "r") as fh:
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
                with open(mp, "w") as fh:
                        for l in s:
                                fh.write(l)
                # Rebuild the catalog so that hash verification for the manifest
                # won't cause problems.
                r.rebuild()
                # This should fail because the manifest already has almost
                # identical signature actions in it.
                self.pkgsign_simple(self.rurl1, plist[0], exit=1)

        def test_bug_17740_default_pub(self):
                """Test that signing a package in the default publisher of a
                multi-publisher repository works."""

                self.pkgrepo("add_publisher -s {0} pub2".format(self.rurl1))
                plist = self.pkgsend_bulk(self.rurl1, self.example_pkg10)

                self.pkgsign_simple(self.rurl1, "'ex*'")

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, plist)

        def test_bug_17740_alternate_pub(self):
                """Test that signing a package in an alternate publisher of a
                multi-publisher repository works."""

                self.pkgrepo("add_publisher -s {0} pub2".format(self.rurl1))
                plist = self.pkgsend_bulk(self.rurl1, self.pub2_pkg)

                self.pkgsign_simple(self.rurl1, "'*2pk*'")

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, plist)

        def test_bug_17740_name_collision_1(self):
                """Test that when two publishers have packages with the same
                name, the publisher in the sign command is respected.  This test
                signs the package from the default publisher."""

                self.pkgrepo("add_publisher -s {0} pub2".format(self.rurl1))
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.pub2_example])

                self.pkgsign_simple(self.rurl1, "pkg://test/example_pkg")

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["pkg://pub2/example_pkg"])
                self._api_install(api_obj, ["pkg://test/example_pkg"])

        def test_bug_17740_name_collision_2(self):
                """Test that when two publishers have packages with the same
                name, the publisher in the sign command is respected.  This test
                signs the package from the non-default publisher."""

                self.pkgrepo("add_publisher -s {0} pub2".format(self.rurl1))
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.pub2_example])

                self.pkgsign_simple(self.rurl1, "pkg://pub2/example_pkg")

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
                api_obj = self.get_img_api_obj()
                self.assertRaises(apx.RequiredSignaturePolicyException,
                    self._api_install, api_obj, ["pkg://test/example_pkg"])
                self._api_install(api_obj, ["pkg://pub2/example_pkg"])

        def test_bug_17740_anarchistic_pkg(self):
                """Test that signing a package present in both repositories
                signs both packages."""

                self.pkgrepo("add_publisher -s {0} pub2".format(self.rurl1))
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.pub2_example])

                self.pkgsign_simple(self.rurl1, "example_pkg")

                self.pkg_image_create(additional_args=
                    "--set-property signature-policy=require-signatures")
                self.seed_ta_dir("ta3")
                self.pkg("set-publisher -p {0}".format(self.rurl1))
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

                # Specify location as filesystem path.
                self.pkgsign_simple(self.dc.get_repodir(), plist[0])

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
                self.pkg("fix", exit=4)
                portable.remove(os.path.join(self.img_path(),
                    "bin/example_path"))
                self.pkg("verify", exit=1)
                self.assertTrue("signature" not in self.errout)
                self.pkg("fix")
                self.assertTrue("signature" not in self.errout)

        def test_bug_18880_sig(self):
                plist = self.pkgsend_bulk(self.rurl1, self.bug_18880_pkg)
                sign_args = "-k {key} -c {cert} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      pkg=plist[0])
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1, variants={"variant.foo":"bar"})
                api_obj = self.get_img_api_obj()
                self.seed_ta_dir("ta2")
                self._api_install(api_obj, ["b18880"])
                self.pkg("verify")
                self.pkg("fix", exit=4)
                portable.remove(os.path.join(self.img_path(),
                    "bin/example_path"))
                self.pkg("verify", exit=1)
                self.assertTrue("signature" not in self.errout)
                self.pkg("fix")
                self.assertTrue("signature" not in self.errout)

        def test_bug_19055(self):
                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.example_pkg20])
                sign_args = "-k {key} -c {cert} -i {ch1} {name}".format(
                        name=" ".join(plist),
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)
                repo = self.dc.get_repo()
                for pfmri in plist:
                        found = False
                        with open(repo.manifest(pfmri), "r") as fh:
                                for l in fh:
                                        if l.startswith("signature"):
                                                found = True
                                                break
                        self.assertTrue(found, "{0} was not signed.".format(pfmri))

        def test_bug_19114_1(self):
                """Test that an unparsable trust anchor which isn't needed
                doesn't cause problems."""

                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10])
                sign_args = "-k {key} -c {cert} -i {ch1} {name}".format(
                        name=" ".join(plist),
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1)
                api_obj = self.get_img_api_obj()
                self.seed_ta_dir("ta3")
                # Create an empty file in the trust anchor directory
                fh = open(os.path.join(self.ta_dir, "empty"), "wb")
                fh.close()
                # This install should succeed because the trust anchor needed to
                # verify the certificate is still there.
                self._api_install(api_obj, ["example_pkg"])

        def test_bug_19114_2(self):
                """Test that a unparsable trust anchor which is needed during
                installation triggers the proper exception."""

                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10])
                sign_args = "-k {key} -c {cert} -i {ch1} {name}".format(
                        name=" ".join(plist),
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"))
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1)
                api_obj = self.get_img_api_obj()
                self.seed_ta_dir("ta3")
                # Replace the trust anchor with an empty file.
                fh = open(os.path.join(self.ta_dir, "ta3_cert.pem"), "wb")
                fh.close()
                # This install should fail because the needed trust anchor has
                # been emptied.
                try:
                        self._api_install(api_obj, ["example_pkg"])
                except apx.BrokenChain as e:
                        assert len(e.ext_exs) == 1
                else:
                        raise RuntimeError("Didn't get expected exception")
                self.pkg("install example_pkg", exit=1)

        def test_signed_mediators(self):
                """Test that packages with mediated links and other varianted
                actions work correctly when signed."""

                bar = """\
set name=pkg.fmri value=bar@1.7
set name=variant.num value=one value=two
link mediator=foobar mediator-version=1.7 path=usr/foobar target=whee1.7
"""

                foo = """\
set name=pkg.fmri value=foo@1.6
set name=variant.num value=one value=two
set name=foo value=bar variant.arch=one
link mediator=foobar mediator-version=1.6 path=usr/foobar target=whee1.6
"""

                foo_pth = self.make_manifest(foo)
                bar_pth = self.make_manifest(bar)
                self.make_misc_files(["tmp/foo"])
                self.pkgsend(self.rurl1, "publish -d {0} {1}".format(
                    self.test_root, foo_pth))
                self.pkgsend(self.rurl1, "publish -d {0} {1}".format(
                    self.test_root, bar_pth))
                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                ta_cert_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta3_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ch1} '*'".format(
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=chain_cert_path)
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1, variants={"variant.num":"one"})
                self.seed_ta_dir("ta3")
                self.pkg("install foo bar")
                self.pkg("set-mediator -V 1.6 foobar")

        def test_reverting_signed_packages(self):
                """Test that reverting signed packages with variants works."""

                b = """\
set name=pkg.fmri value=B@1.0,5.11-0
set name=variant.num value=one value=two
file tmp/foo mode=0555 owner=root group=bin path=etc/fileB revert-tag=bob
dir mode=0755 owner=root group=bin path=etc variant.num=two
"""

                c = """\
set name=pkg.fmri value=C@1.0,5.11-0
set name=variant.num value=one value=two
file tmp/foo mode=0555 owner=root group=bin path=etc2/fileC revert-tag=bob variant.num=two
dir mode=0755 owner=root group=bin path=etc2 variant.num=two
"""

                b_pth = self.make_manifest(b)
                c_pth = self.make_manifest(c)
                self.make_misc_files(["tmp/foo"])
                self.pkgsend(self.rurl1, "publish -d {0} {1}".format(
                    self.test_root, b_pth))
                self.pkgsend(self.rurl1, "publish -d {0} {1}".format(
                    self.test_root, c_pth))
                chain_cert_path = os.path.join(self.chain_certs_dir,
                    "ch1_ta3_cert.pem")
                ta_cert_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta3_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ch1} '*'".format(
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=chain_cert_path)
                self.pkgsign(self.rurl1, sign_args)
                self.image_create(self.rurl1, variants={"variant.num":"one"})
                self.seed_ta_dir("ta3")
                self.pkg("install B")
                self.pkg("verify B")
                # Now test reverting by file.
                with open(
                    os.path.join(self.get_img_path(), "etc/fileB"), "w") as fh:
                        fh.write("\n")
                self.pkg("verify B", exit=1)
                self.pkg("revert /etc/fileB")
                self.pkg("verify B")
                # Now test reverting by tag since that's a separate code path in
                # ImagePlan.plan_revert.
                with open(
                    os.path.join(self.get_img_path(), "etc/fileB"), "w") as fh:
                        fh.write("\n")
                self.pkg("verify B", exit=1)
                self.pkg("revert --tagged bob")
                self.pkg("verify B")
                # Now test reverting a file that's delivered in another variant.
                self.pkg("install C")
                self.pkg("verify C")
                self.pkg("revert etc2/fileC", exit=1)


class TestPkgSignMultiDepot(pkg5unittest.ManyDepotTestCase):
        # Tests in this suite use the read only data directory.
        need_ro_data = True

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            add dir mode=0755 owner=root group=bin path=/usr/lib/python2.7/vendor-packages/OpenSSL
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

        def pkg(self, command, *args, **kwargs):
                # The value for crl_host is pulled from DebugValues because
                # crl_host needs to be set there so the api object calls work
                # as desired.
                command = "--debug crl_host={0} {1}".format(
                    DebugValues["crl_host"], command)
                return pkg5unittest.ManyDepotTestCase.pkg(self, command,
                    *args, **kwargs)

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self,
                    ["test", "test", "crl", "test"])
                self.make_misc_files(self.misc_files)
                self.durl1 = self.dcs[1].get_depot_url()
                self.rurl1 = self.dcs[1].get_repo_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.rurl2 = self.dcs[2].get_repo_url()
                self.durl4 = self.dcs[4].get_depot_url()
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
                sign_args = "-k {key} -c {cert} -i {ta} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      ta=ta_path,
                      pkg=plist[0]
                   )

                self.pkgsign(self.rurl2, sign_args)

                repo_location = self.dcs[1].get_repodir()
                self.pkgrecv(self.rurl2, "-d {0} example_pkg".format(self.rurl1))
                shutil.rmtree(repo_location)
                self.pkgrepo("create {0}".format(repo_location))

                # Add another signature that is just signed with the hash of
                # the manifest.
                sign_args = "{pkg}".format(
                    pkg=plist[0]
                )
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d {0} example_pkg".format(self.rurl1))
                shutil.rmtree(repo_location)
                self.pkgrepo("create {0}".format(repo_location))

                # Add another signature that is just signed with the hash of
                # the manifest. Test "-a" option.
                sign_args = "-a sha256 {pkg}".format(
                    pkg=plist[0]
                )
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d {0} example_pkg".format(self.rurl1))
                shutil.rmtree(repo_location)
                self.pkgrepo("create {0}".format(repo_location))

                # Add another signature which includes the same chain cert used
                # in the first signature.
                sign_args = "-k {key} -c {cert} -i {ch1} -i {ta} " \
                    "{name}".format(**{
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "ta": ta_path,
                })
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d {0} example_pkg".format(self.rurl1))
                shutil.rmtree(repo_location)
                self.pkgrepo("create {0}".format(repo_location))

                # Add another signature to further test duplicate chain
                # certificates as well as having a chain cert that's a signing
                # certificate in other signatures.
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} -i {ch1} -i {ta} " \
                    "-i {cs1_ch1_ta3} {name} ".format(**{
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
                })
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d {0} example_pkg".format(self.rurl1))

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")
                self.seed_ta_dir("ta2")
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg"])

        def test_sign_pkgrecv_delivered_cert(self):
                """Check that if a cache directory contains the payload for a
                signature action with intermediate certificates but nothing
                else, pkgrecv still works."""

                manf = """
open a@1,5.11-0
close
"""
                self.pkgsend_bulk(self.rurl2, manf)

                cert_path = os.path.join(self.cs_dir, "cs1_ta2_cert.pem")
                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ta} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=cert_path,
                      ta=ta_path,
                      pkg="a"
                   )

                self.pkgsign(self.rurl2, sign_args)

                # Artificially fill the cache directory with a gzipped version
                # of the transformed certificate file, as if pkgrecv had put it
                # there itself.
                repo_location = self.dcs[1].get_repodir()
                cache_dir = os.path.join(self.test_root, "cache")
                os.mkdir(cache_dir)

                with open(cert_path, "rb") as f:
                        cert = x509.load_pem_x509_certificate(
                            f.read(), default_backend())


                fd, new_cert = tempfile.mkstemp(dir=self.test_root)
                with os.fdopen(fd, "wb") as fh:
                        fh.write(cert.public_bytes(
                            serialization.Encoding.PEM))

                # the file-store uses the least-preferred hash when storing
                # content
                alg = digest.HASH_ALGS["hash"]
                file_name = misc.get_data_digest(new_cert,
                    hash_func=alg)[0]
                subdir = os.path.join(cache_dir, file_name[:2])
                os.mkdir(subdir)
                fp = os.path.join(subdir, file_name)
                fh = PkgGzipFile(fp, "wb")
                fh.write(cert.public_bytes(serialization.Encoding.PEM))
                fh.close()

                self.pkgrecv(self.rurl2, "-c {0} -d {1} '*'".format(
                    cache_dir, self.rurl1))

        def test_sign_pkgrecv_delivered_intermediate_cert(self):
                """Check that if a cache directory contains an intermediate file
                for a signature action with intermediate certificates but
                nothing else, pkgrecv still works."""

                manf = """
open a@1,5.11-0
close
"""
                self.pkgsend_bulk(self.rurl2, manf)

                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ta} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      ta=ta_path,
                      pkg="a"
                   )

                self.pkgsign(self.rurl2, sign_args)

                # Artificially fill the cache directory with a gzipped version
                # of the transformed certificate file, as if pkgrecv had put it
                # there itself.
                repo_location = self.dcs[1].get_repodir()
                cache_dir = os.path.join(self.test_root, "cache")
                os.mkdir(cache_dir)

                with open(ta_path, "rb") as f:
                        cert = x509.load_pem_x509_certificate(
                            f.read(), default_backend())

                fd, new_cert = tempfile.mkstemp(dir=self.test_root)
                with os.fdopen(fd, "wb") as fh:
                        fh.write(cert.public_bytes(
                            serialization.Encoding.PEM))

                for attr in digest.DEFAULT_HASH_ATTRS:
                        if attr == "pkg.content-hash":
                                continue
                        alg = digest.HASH_ALGS[attr]
                        file_name = misc.get_data_digest(new_cert,
                            hash_func=alg)[0]
                        subdir = os.path.join(cache_dir, file_name[:2])
                        os.mkdir(subdir)
                        fp = os.path.join(subdir, file_name)
                        fh = PkgGzipFile(fp, "wb")
                        fh.write(cert.public_bytes(
                            serialization.Encoding.PEM))
                        fh.close()

                self.pkgrecv(self.rurl2, "-c {0} -d {1} '*'".format(
                    cache_dir, self.rurl1))

        def test_sign_pkgrecv_cache_sign_interaction(self):
                """Check that if a cache directory is used and multiple packages
                are signed with the same certificates and intermediate
                certificates are involved, pkgrecv continues to work."""

                self.__test_sign_pkgrecv_cache_sign_interaction()
                # Verify that older logic of publication api works.
                self.dcs[1].stop()
                self.dcs[2].stop()
                self.dcs[1].set_disable_ops(["manifest/1"])
                self.dcs[2].set_disable_ops(["manifest/1"])
                self.__test_sign_pkgrecv_cache_sign_interaction()

        def __test_sign_pkgrecv_cache_sign_interaction(self):
                self.dcs[1].start()
                self.dcs[2].start()
                manf = """
open a@1,5.11-0
close
"""
                self.pkgsend_bulk(self.durl2, manf)
                manf = """
open b@1,5.11-0
close
"""
                self.pkgsend_bulk(self.durl2, manf)

                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ta} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      ta=ta_path,
                      pkg="'*'"
                   )

                self.pkgsign(self.durl2, sign_args)

                cache_dir = os.path.join(self.test_root, "cache")
                self.pkgrecv(self.durl2, "-c {0} -d {1} '*'".format(
                    cache_dir, self.durl1))

        def test_sign_pkgrecv_a(self):
                """Check that signed packages can be archived."""

                plist = self.pkgsend_bulk(self.rurl2, self.example_pkg10)

                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta2_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ta} {pkg}".format(
                    key=os.path.join(self.keys_dir, "cs1_ta2_key.pem"),
                      cert=os.path.join(self.cs_dir, "cs1_ta2_cert.pem"),
                      ta=ta_path,
                      pkg=plist[0]
                   )

                self.pkgsign(self.rurl2, sign_args)

                arch_location = os.path.join(self.test_root, "pkg_arch")
                self.pkgrecv(self.rurl2, "-a -d {0} example_pkg".format(arch_location))
                portable.remove(arch_location)

                # Add another signature which includes the same chain cert used
                # in the first signature.
                sign_args = "-k {key} -c {cert} -i {ch1} -i {ta} " \
                    "{name}".format(
                        name=plist[0],
                        key=os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        cert=os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        ch1=os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        ta=ta_path)
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-a -d {0} example_pkg".format(arch_location))
                portable.remove(arch_location)

                # Add another signature to further test duplicate chain
                # certificates as well as having a chain cert that's a signing
                # certificate in other signatures.
                sign_args = "-k {key} -c {cert} -i {i1} -i {i2} " \
                    "-i {i3} -i {i4} -i {i5} -i {ch1} -i {ta} " \
                    "-i {cs1_ch1_ta3} {name} ".format(**{
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
                })
                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-a -d {0} example_pkg".format(arch_location))

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta1")
                self.seed_ta_dir("ta2")
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")

                api_obj = self.get_img_api_obj()
                self.pkg("install -g file://{0} example_pkg".format(arch_location))

        def test_bug_16861_recv(self):
                """Check that signed obsolete and renamed packages can be
                transferred from one repo to another."""

                plist = self.pkgsend_bulk(self.rurl2, [renamed_pkg,
                    obsolete_pkg])
                for name in plist:
                        sign_args = "-k {key} -c {cert} -i {i1} " \
                            "-i {i2} -i {i3} -i {i4} -i {i5} " \
                            "{name}".format(**{
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
                        })
                        self.pkgsign(self.rurl2, sign_args)

                self.pkgrecv(self.rurl2, "-d {0} renamed obs".format(self.rurl1))

        def test_bug_18463(self):
                """Check that the crl host is only contacted twice, instead of
                twice per package."""

                self.dcs[3].start()

                plist = self.pkgsend_bulk(self.rurl1,
                    [self.example_pkg10, self.foo10])
                sign_args = "-k {key} -c {cert} -i {i1} {name}".format(**{
                        "name": "{0} {1}".format(plist[0], plist[1]),
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1.1_ta4_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1.1_ta4_cert.pem"),
                        "i1": os.path.join(self.chain_certs_dir,
                            "ch1.1_ta4_cert.pem")
                })
                self.pkgsign(self.rurl1, sign_args)

                self.pkg_image_create(self.rurl1)
                self.seed_ta_dir("ta4")
                self.pkg("set-property check-certificate-revocation true")
                self.pkg("set-property signature-policy require-signatures")
                api_obj = self.get_img_api_obj()
                self._api_install(api_obj, ["example_pkg", "foo"])
                cnt = 0
                with open(self.dcs[3].get_logpath(), "r") as fh:
                        for l in fh:
                                if "ch1.1_ta4_crl.pem" in l:
                                        cnt += 1
                self.assertEqual(cnt, 2)

        def test_sign_pkgrecv_across_repositories(self):
                """Check that signed packages can be pkgrecved to a new
                repository that enables new hashes but the new hashes won't
                be added to the packages so that the existing signatures won't
                be invalidated"""

                # We create an image simply so we can use "contents -g" to
                # inspect the repository.
                self.image_create()
                self.dcs[1].start()
                self.dcs[2].start()
                plist = self.pkgsend_bulk(self.rurl2, self.example_pkg10)
                ta_path = os.path.join(self.raw_trust_anchor_dir,
                    "ta3_cert.pem")
                sign_args = "-k {key} -c {cert} -i {ch1} -i {ta} " \
                    "{name}".format(**{
                        "name": plist[0],
                        "key": os.path.join(self.keys_dir,
                            "cs1_ch1_ta3_key.pem"),
                        "cert": os.path.join(self.cs_dir,
                            "cs1_ch1_ta3_cert.pem"),
                        "ch1": os.path.join(self.chain_certs_dir,
                            "ch1_ta3_cert.pem"),
                        "ta": ta_path,
                })

                self.pkgsign(self.rurl2, sign_args)
                self.pkgrecv(self.rurl2, "-d {0} example_pkg".format(self.durl1))
                self.pkg("contents -g {0} -m example_pkg".format(self.durl1))
                self.assertTrue("pkg.content-hash=file:sha256" not in self.output)
                self.image_create(self.durl1)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")
                self.pkg("install example_pkg")
                self.image_destroy()

                self.dcs[4].set_debug_feature("hash=sha1+sha256")
                self.dcs[4].start()
                self.image_create(self.durl4, destroy=True)
                # pkgrecv to a new repository which enables SHA-2 hashes
                self.pkgrecv(self.durl1, "-d {0} example_pkg".format(self.durl4))
                self.pkg("contents -g {0} -m example_pkg".format(self.durl4))
                # make sure that we don not get multiple hashes
                self.assertTrue("pkg.content-hash=file:sha256" not in self.output)
                self.seed_ta_dir("ta3")
                self.pkg("set-property signature-policy verify")
                # should not invalidate the signature
                self.pkg("install example_pkg")

                self.dcs[4].stop()
                self.dcs[4].unset_debug_feature("hash=sha1+sha256")


if __name__ == "__main__":
        unittest.main()
