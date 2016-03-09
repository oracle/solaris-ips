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
import os
import pkg.pkgsubprocess as subprocess
import shutil
import sys

sys.path.append("../../")
import certgenerator

output_dir = "./produced"

if __name__ == "__main__":
        # Remove any existing output from previous runs of this program.
        if os.path.isdir(output_dir):
                shutil.rmtree(output_dir)
        os.mkdir(output_dir)

        cg = certgenerator.CertGenerator(base_dir=output_dir)

        # Make a length 7 chain.
        cg.make_trust_anchor("ta1")
        cg.make_ca_cert("ch1_ta1", "ta1", ext="v3_ca_lp4")
        cg.make_ca_cert("ch2_ta1", "ch1_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp3")
        cg.make_ca_cert("ch3_ta1", "ch2_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp2")
        cg.make_ca_cert("ch4_ta1", "ch3_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp1")
        cg.make_ca_cert("ch5_ta1", "ch4_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp0")
        cg.make_cs_cert("cs1_ch5_ta1", "ch5_ta1", parent_loc="chain_certs")
        # Make a chain where a chain cert has revoked the code signing cert.
        cg.make_cs_cert("cs2_ch5_ta1", "ch5_ta1", parent_loc="chain_certs",
            ext="ch5_ta1_crl")
        cg.revoke_cert("ch5_ta1", "cs2_ch5_ta1", ca_dir="chain_certs")
        # Make a chain where the chain cert has an unsupported critical
        # extension.
        cg.make_ca_cert("ch5.1_ta1", "ch4_ta1", parent_loc="chain_certs",
            ext="issuer_ext_ca")
        cg.make_cs_cert("cs1_ch5.1_ta1", "ch5.1_ta1", parent_loc="chain_certs")
        # Make a chain where a chain cert has a larger number than is needed.
        cg.make_ca_cert("ch5.2_ta1", "ch4_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp1")
        cg.make_cs_cert("cs1_ch5.2_ta1", "ch5.2_ta1", parent_loc="chain_certs")
        # Make a chain where a chain cert has a smaller number than is needed.
        cg.make_ca_cert("ch4.3_ta1", "ch3_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp0")
        cg.make_ca_cert("ch5.3_ta1", "ch4.3_ta1", parent_loc="chain_certs",
            ext="v3_ca_lp0")
        cg.make_cs_cert("cs1_ch5.3_ta1", "ch5.3_ta1", parent_loc="chain_certs")

        # Make a length 2 chain
        cg.make_trust_anchor("ta2")
        cg.make_cs_cert("cs1_ta2", "ta2")

        # Make a length 3 chain
        cg.make_trust_anchor("ta3")
        cg.make_ca_cert("ch1_ta3", "ta3")
        cg.make_cs_cert("cs1_ch1_ta3", "ch1_ta3", parent_loc="chain_certs")
        # Add a certificate to the length 3 chain with an unsupported critical
        # extension.
        cg.make_cs_cert("cs2_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            ext="issuer_ext")
        # Add a certificate to the length 3 chain that has already expired.
        cg.make_cs_cert("cs3_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            expired=True)
        # Add a certificate to the length 3 chain that is in the future.
        cg.make_cs_cert("cs4_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            future=True)
        # Add a certificate to the length 3 chain that has an unknown value for
        # a recognized non-critical extension.
        cg.make_cs_cert("cs5_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            ext="issuer_ext_non_critical")
        # Add a certificate to the length 3 chain that has an unknown value for
        # a recognized critical extension.
        cg.make_cs_cert("cs6_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            ext="issuer_ext_bad_val")
        # Add a certificate to the length 3 chain that has keyUsage information
        # but cannot be used to sign code.
        cg.make_cs_cert("cs7_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            ext="v3_no_keyUsage")
        # Make a chain where a CS is used to sign another CS.
        cg.make_cs_cert("cs8_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            ext="v3_confused_cs")
        cg.make_cs_cert("cs1_cs8_ch1_ta3", "cs8_ch1_ta3",
            parent_loc="code_signing_certs")
        # Add a certificate to the length 3 chain that has an invalid extension.
        cg.make_cs_cert("cs9_ch1_ta3", "ch1_ta3", parent_loc="chain_certs",
            ext="invalid_ext")
        # Make a chain where the CA has an unsupported critical extension.
        cg.make_ca_cert("ch1.1_ta3", "ta3", ext="issuer_ext_ca")
        cg.make_cs_cert("cs1_ch1.1_ta3", "ch1.1_ta3", parent_loc="chain_certs")
        # Make a chain where the CA is expired but the CS is current.
        cg.make_ca_cert("ch1.2_ta3", "ta3", expired=True)
        cg.make_cs_cert("cs1_ch1.2_ta3", "ch1.2_ta3", parent_loc="chain_certs")
        # Make a chain where the CA is in the future but the CS is current.
        cg.make_ca_cert("ch1.3_ta3", "ta3", future=True)
        cg.make_cs_cert("cs1_ch1.3_ta3", "ch1.3_ta3", parent_loc="chain_certs")
        # Make a chain where the CA does not have keyUsage set.
        cg.make_ca_cert("ch1.4_ta3", "ta3", future=True, ext="v3_ca_no_keyUsage")
        cg.make_cs_cert("cs1_ch1.4_ta3", "ch1.4_ta3", parent_loc="chain_certs")

        # Revoke a code signing certificate from the publisher.
        cg.make_trust_anchor("ta4")
        cg.make_ca_cert("ch1_ta4", "ta4")
        cg.make_cs_cert("cs1_ch1_ta4", "ch1_ta4", parent_loc="chain_certs",
            ext="crl_ext")
        cg.revoke_cert("ch1_ta4", "cs1_ch1_ta4", ca_dir="chain_certs")
        cg.make_cs_cert("cs2_ch1_ta4", "ch1_ta4", parent_loc="chain_certs",
            ext="bad_crl")
        cg.make_cs_cert("cs3_ch1_ta4", "ch1_ta4", parent_loc="chain_certs",
            ext="bad_crl_loc")
        # Revoke a code signing certificate but sign the CRL with a CA
        # certificate that does not have that keyUsage set.
        cg.make_ca_cert("ch1.1_ta4", "ta4", ext="v3_ca_no_crl")
        cg.make_cs_cert("cs1_ch1.1_ta4", "ch1.1_ta4", parent_loc="chain_certs",
            ext="ch1.1_ta4_crl")
        cg.revoke_cert("ch1.1_ta4", "cs1_ch1.1_ta4", ca_dir="chain_certs")

        # Revoke a CA cert from the trust anchor
        cg.make_trust_anchor("ta5")
        cg.make_ca_cert("ch1_ta5", "ta5", ext="crl_ca")
        cg.make_cs_cert("cs1_ch1_ta5", "ch1_ta5", parent_loc="chain_certs")
        cg.revoke_cert("ta5", "ch1_ta5", cert_dir="chain_certs")

        # Make more length 2 chains for testing https repos.
        cg.make_trust_anchor("ta6", https=True)
        cg.make_cs_cert("cs1_ta6", "ta6", https=True)
        cg.make_trust_anchor("ta7", https=True)
        # A passphrase is added to this one to test depot HTTPS functionality.
        cg.make_cs_cert("cs1_ta7", "ta7", https=True, passphrase="123")
        cg.make_trust_anchor("ta8", https=True)
        cg.make_cs_cert("cs1_ta8", "ta8", https=True)
        cg.make_trust_anchor("ta9", https=True)
        cg.make_cs_cert("cs1_ta9", "ta9", https=True)
        cg.make_trust_anchor("ta10", https=True)
        cg.make_cs_cert("cs1_ta10", "ta10", https=True)
        cg.make_trust_anchor("ta11", https=True)
        cg.make_cs_cert("cs1_ta11", "ta11", https=True)

        # Create a combined CA file to test different client certs with Apache
        fhw = open(os.path.join(output_dir, "combined_cas.pem"), "w")
        for x in range(6,12):
                if x == 7:
                        # ta requires a password to unlock cert, don't use
                        continue
                fn = "{0}/ta{1:d}/ta{2:d}_cert.pem".format(output_dir, x, x)
                fhr = open(fn, "r")
                fhw.write(fhr.read())
                fhr.close()
        fhw.close()

        # Create a certificate with an extension that Cryptography can't
        # understand. We can't do it by the OpenSSL CLI, but we can use a C
        # program that calls OpenSSL libraries to do it.
        os.chdir("../../../util/mkcert")
        cmdline = "./certgen"
        p = subprocess.Popen(cmdline, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=True)
        p.wait()

        output, error = p.communicate()
        if p.returncode == 127:
                print("certgen not found; execute 'make' in the mkcert "
                    "directory first")
                sys.exit(p.returncode)
        elif p.returncode != 0:
                print("failed: {0} {1}".format(output, error))
                sys.exit(p.returncode)

        # copy the generated cert files from util/mkcert to the ro_data area
        shutil.copy("cust_key.pem",
            "../../tests/ro_data/signing_certs/produced/keys/")
        shutil.copy("cust_cert.pem",
            "../../tests/ro_data/signing_certs/produced/code_signing_certs/")
        shutil.copy("cust_cert.pem",
            "../../tests/ro_data/signing_certs/produced/trust_anchors/")
