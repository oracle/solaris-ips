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
# Copyright (c) 2010, Oracle and/or its affiliates. All rights reserved.
#

import os
import shutil
import subprocess
import sys

# Locations defined in openssl.cnf
output_dir = "./produced"
cnf_file = "openssl.cnf"
mk_file = "Makefile"

subj_str = "/C=US/ST=California/L=Menlo Park/O=pkg5/CN=%s/emailAddress=%s"

def convert_pem_to_text(tmp_pth, out_pth, kind="x509"):
        """Convert a pem file to a human friendly text file."""

        assert not os.path.exists(out_pth)
        
        cmd = ["openssl", kind, "-in", tmp_pth,
            "-text"]

        fh = open(out_pth, "wb")
        p = subprocess.Popen(cmd, stdout=fh)
        assert p.wait() == 0
        fh.close()

def make_ca_cert(new_loc, new_name, parent_loc, parent_name, ext="v3_ca",
    expired=False, future=False):
        """Create a new CA cert."""

        cmd = ["openssl", "req", "-new", "-nodes",
            "-keyout", "./keys/%s_key.pem" % new_name,
            "-out", "./%s/%s.csr" % (new_loc, new_name),
            "-sha256", "-subj", subj_str % (new_name, new_name)]
        p = subprocess.Popen(cmd)
        assert p.wait() == 0

        cmd = ["openssl", "ca", "-policy", "policy_anything",
            "-extensions", ext,
            "-out", "./%s/%s_cert.pem" % (new_loc, new_name),
            "-in", "./%s/%s.csr" % (new_loc, new_name),
            "-cert", "./%s/%s_cert.pem" % (parent_loc, parent_name),
            "-outdir", "./%s" % new_loc,
            "-keyfile", "./keys/%s_key.pem" % parent_name, "-config", cnf_file,
            "-batch"]
        if expired:
                cmd.append("-startdate")
                cmd.append("090101010101Z")
                cmd.append("-enddate")
                cmd.append("090102010101Z")
        elif future:
                cmd.append("-startdate")
                cmd.append("350101010101Z")
                cmd.append("-enddate")
                cmd.append("350102010101Z")
        else:
                cmd.append("-days")
                cmd.append("1000")
        p = subprocess.Popen(cmd)
        assert p.wait() == 0


def make_cs_cert(new_loc, new_name, parent_loc, parent_name, ext="v3_req",
    expired=False, future=False):
        """Create a new code signing cert."""

        cmd = ["openssl", "req", "-new", "-nodes",
            "-keyout", "./keys/%s_key.pem" % new_name,
            "-out", "./%s/%s.csr" % (new_loc, new_name),
            "-sha256", "-subj", subj_str % (new_name, new_name)]
        p = subprocess.Popen(cmd)
        assert p.wait() == 0

        cmd = ["openssl", "ca", "-policy", "policy_anything",
            "-extensions", ext,
            "-out", "./%s/%s_cert.pem" % (new_loc, new_name),
            "-in", "./%s/%s.csr" % (new_loc, new_name),
            "-cert", "./%s/%s_cert.pem" % (parent_loc, parent_name),
            "-outdir", "./%s" % new_loc,
            "-keyfile", "./keys/%s_key.pem" % parent_name, "-config", cnf_file,
            "-batch"]
        if expired:
                cmd.append("-startdate")
                cmd.append("090101010101Z")
                cmd.append("-enddate")
                cmd.append("090102010101Z")
        elif future:
                cmd.append("-startdate")
                cmd.append("350101010101Z")
                cmd.append("-enddate")
                cmd.append("350102010101Z")
        else:
                cmd.append("-days")
                cmd.append("1000")
        p = subprocess.Popen(cmd)
        assert p.wait() == 0

def make_trust_anchor(name):
        """Make a new trust anchor."""

        cmd = ["openssl", "req", "-new", "-x509", "-nodes",
            "-keyout", "./keys/%s_key.pem" % name,
            "-subj", subj_str % (name, name),
            "-out", "./%s/%s_cert.tmp" % (name, name), "-days", "1000",
            "-sha256"]

        os.mkdir("./%s" % name)

        p = subprocess.Popen(cmd)
        assert p.wait() == 0
        convert_pem_to_text("./%s/%s_cert.tmp" % (name, name),
            "./%s/%s_cert.pem" % (name, name))

        try:
                os.link("./%s/%s_cert.pem" % (name, name),
                    "./trust_anchors/%s_cert.pem" % name)
        except:
                shutil.copy("./%s/%s_cert.pem" % (name, name),
                    "./trust_anchors/%s_cert.pem" % name)

def revoke_cert(ca, revoked_cert, ca_dir=None, cert_dir="code_signing_certs"):
        """Revoke a certificate using the CA given."""

        if not ca_dir:
                ca_dir = ca
        cmd = ["openssl", "ca", "-keyfile", "keys/%s_key.pem" % ca,
            "-cert", "%s/%s_cert.pem" % (ca_dir, ca),
            "-config", cnf_file,
            "-revoke", "%s/%s_cert.pem" % (cert_dir, revoked_cert)]
        p = subprocess.Popen(cmd)
        assert p.wait() == 0

        cmd = ["openssl", "ca", "-gencrl",
            "-keyfile", "keys/%s_key.pem" % ca,
            "-cert", "%s/%s_cert.pem" % (ca_dir, ca),
            "-config", cnf_file,
            "-out", "crl/%s_crl.tmp" % ca,
            "-crldays", "1000"]
        p = subprocess.Popen(cmd)
        assert p.wait() == 0
        convert_pem_to_text("crl/%s_crl.tmp" % ca, "crl/%s_crl.pem" % ca,
            kind="crl")

        
if __name__ == "__main__":
        # Remove any existing output from previous runs of this program.
        if os.path.isdir(output_dir):
                shutil.rmtree(output_dir)
        os.mkdir(output_dir)
        shutil.copy(cnf_file, os.path.join(output_dir, cnf_file))
        os.chdir(output_dir)

        # Set up the needed files and directories.
        fh = open("index", "wb")
        fh.close()

        fh = open("serial", "wb")
        fh.write("01\n")
        fh.close()

        os.mkdir("crl")
        os.mkdir("keys")
        os.mkdir("trust_anchors")
        os.mkdir("inter_certs")
        os.mkdir("publisher_cas")
        os.mkdir("chain_certs")
        os.mkdir("code_signing_certs")

        # Make a length 7 chain.
        make_trust_anchor("ta1")
        make_ca_cert("inter_certs", "i1_ta1", "trust_anchors", "ta1")
        make_ca_cert("inter_certs", "i2_ta1", "inter_certs", "i1_ta1")
        make_ca_cert("publisher_cas", "pubCA1_ta1", "inter_certs", "i2_ta1")
        make_ca_cert("chain_certs", "ch1_pubCA1", "publisher_cas", "pubCA1_ta1")
        make_ca_cert("chain_certs", "ch2_pubCA1", "chain_certs", "ch1_pubCA1")
        make_cs_cert("code_signing_certs", "cs1_pubCA1",
            "chain_certs", "ch2_pubCA1")
        # Make a chain where the publisher CA has revoked the code signing cert.
        make_cs_cert("code_signing_certs", "cs2_pubCA1",
            "chain_certs", "ch2_pubCA1", ext="pubCA1_ta1_crl")
        revoke_cert("pubCA1_ta1", "cs2_pubCA1", ca_dir="publisher_cas")
        # Make a chain where the chain cert has revoked the code signing cert.
        make_cs_cert("code_signing_certs", "cs3_pubCA1",
            "chain_certs", "ch2_pubCA1", ext="ch1_ta1_crl")
        revoke_cert("ch1_pubCA1", "cs3_pubCA1", ca_dir="chain_certs")
        # Make a chain where the chain cert has an unsupported critical
        # extension.
        make_ca_cert("chain_certs", "ch2.2_pubCA1", "chain_certs", "ch1_pubCA1",
            ext="issuer_ext_ca")
        make_cs_cert("code_signing_certs", "cs4_pubCA1",
            "chain_certs", "ch2.2_pubCA1")

        # Make a length 2 chain
        make_trust_anchor("ta2")
        make_cs_cert("code_signing_certs", "cs1_ta2", "trust_anchors", "ta2")

        # Make a length 3 chain
        make_trust_anchor("ta3")
        make_ca_cert("publisher_cas", "pubCA1_ta3", "trust_anchors", "ta3")
        make_cs_cert("code_signing_certs", "cs1_p1_ta3",
            "publisher_cas", "pubCA1_ta3")
        # Add a certificate to the length 3 chain with an unsupported critical
        # extension.
        make_cs_cert("code_signing_certs", "cs2_p1_ta3",
            "publisher_cas", "pubCA1_ta3", ext="issuer_ext")
        # Add a certificate to the length 3 chain that has already expired.
        make_cs_cert("code_signing_certs", "cs3_p1_ta3",
            "publisher_cas", "pubCA1_ta3", expired=True)
        # Add a certificate to the length 3 chain that is in the future.
        make_cs_cert("code_signing_certs", "cs4_p1_ta3",
            "publisher_cas", "pubCA1_ta3", future=True)
        # Make a chain where the CA has an unsupported critical extension.
        make_ca_cert("publisher_cas", "pubCA2_ta3", "trust_anchors", "ta3",
            ext="issuer_ext_ca")
        make_cs_cert("code_signing_certs", "cs1_p2_ta3",
            "publisher_cas", "pubCA2_ta3")
        # Make a chain where the CA is expired but the CS is current.
        make_ca_cert("publisher_cas", "pubCA3_ta3", "trust_anchors", "ta3",
            expired=True)
        make_cs_cert("code_signing_certs", "cs1_p3_ta3",
            "publisher_cas", "pubCA3_ta3")
        # Make a chain where the CA is in the future but the CS is current.
        make_ca_cert("publisher_cas", "pubCA4_ta3", "trust_anchors", "ta3",
            future=True)
        make_cs_cert("code_signing_certs", "cs1_p4_ta3",
            "publisher_cas", "pubCA4_ta3")

        # Revoke a code signing certificate from the publisher.
        make_trust_anchor("ta4")
        make_ca_cert("publisher_cas", "pubCA1_ta4", "trust_anchors", "ta4")
        make_cs_cert("code_signing_certs", "cs1_ta4",
            "publisher_cas", "pubCA1_ta4", ext="crl_ext")
        revoke_cert("pubCA1_ta4", "cs1_ta4", ca_dir="publisher_cas")
        make_cs_cert("code_signing_certs", "cs2_ta4",
            "publisher_cas", "pubCA1_ta4", ext="bad_crl")
        make_cs_cert("code_signing_certs", "cs3_ta4",
            "publisher_cas", "pubCA1_ta4", ext="bad_crl_loc")

        # Revoke a CA cert from the trust anchor
        make_trust_anchor("ta5")
        make_ca_cert("publisher_cas", "pubCA1_ta5", "trust_anchors", "ta5",
            ext="crl_ca")
        make_cs_cert("code_signing_certs", "cs1_ta5",
            "publisher_cas", "pubCA1_ta5")
        revoke_cert("ta5", "pubCA1_ta5", cert_dir="publisher_cas")

        os.remove(cnf_file)
        os.chdir("../")
