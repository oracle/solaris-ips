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
# Copyright (c) 2014, 2016, Oracle and/or its affiliates. All rights reserved.
#

import os
import subprocess

class CertGenerator(object):
        """A class which creates certificates."""

        def __init__(self, base_dir="."):
                # Allow relative path, but convert it to absolute path first.
                self.base_dir = os.path.abspath(base_dir)

                conf_dict = {"base_dir": self.base_dir}
                self.cnf_file = os.path.join(self.base_dir, "openssl.cnf")
                with open(self.cnf_file, "wb") as fh:
                        fh.write(self.openssl_conf.format(**conf_dict))

                # Set up the needed files.
                fh = open(os.path.join(self.base_dir, "index"), "wb")
                fh.close()

                fh = open(os.path.join(self.base_dir, "serial"), "wb")
                fh.write("01\n")
                fh.close()

                # Set up the names of the needed directories.
                self.keys_loc = "keys"
                self.cs_loc = "code_signing_certs"
                self.chain_certs_loc = "chain_certs"
                self.trust_anchors_loc = "trust_anchors"
                self.crl_loc = "crl"

                # Set up the paths to the certificates that will be needed.
                self.keys_dir = os.path.join(self.base_dir, self.keys_loc)
                self.cs_dir = os.path.join(self.base_dir, self.cs_loc)
                self.chain_certs_dir = os.path.join(self.base_dir,
                    self.chain_certs_loc)
                self.raw_trust_anchor_dir = os.path.join(self.base_dir,
                    self.trust_anchors_loc)
                self.crl_dir = os.path.join(self.base_dir, self.crl_loc)

                os.mkdir(self.keys_dir)
                os.mkdir(self.cs_dir)
                os.mkdir(self.chain_certs_dir)
                os.mkdir(self.raw_trust_anchor_dir)
                os.mkdir(self.crl_dir)

        def convert_pem_to_text(self, tmp_pth, out_pth, kind="x509"):
                """Convert a pem file to a human friendly text file."""

                assert not os.path.exists(out_pth)

                cmd = ["openssl", kind, "-in", tmp_pth,
                    "-text"]

                fh = open(out_pth, "wb")
                p = subprocess.Popen(cmd, stdout=fh)
                assert p.wait() == 0
                fh.close()

        def make_ca_cert(self, new_name, parent_name, parent_loc=None,
            ext="v3_ca", ta_path=None, expired=False, future=False, https=False):
                """Create a new CA cert."""

                if not parent_loc:
                        parent_loc = self.trust_anchors_loc
                if not ta_path:
                        ta_path = self.base_dir
                subj_str_to_use = self.subj_str
                if https:
                        subj_str_to_use = self.https_subj_str
                cmd = ["openssl", "req", "-new", "-nodes",
                    "-keyout", "{0}/{1}_key.pem".format(self.keys_dir, new_name),
                    "-out", "{0}/{1}.csr".format(self.chain_certs_dir, new_name),
                    "-sha256", "-subj", subj_str_to_use.format(new_name, new_name)]
                p = subprocess.Popen(cmd)
                assert p.wait() == 0

                cmd = ["openssl", "ca", "-policy", "policy_anything",
                    "-extensions", ext,
                    "-out", "{0}/{1}_cert.pem".format(self.chain_certs_dir,
                        new_name),
                    "-in", "{0}/{1}.csr".format(self.chain_certs_dir, new_name),
                    "-cert", "{0}/{1}/{2}_cert.pem".format(ta_path, parent_loc,
                        parent_name),
                    "-outdir", "{0}".format(self.chain_certs_dir),
                    "-keyfile", "{0}/{1}/{2}_key.pem".format(ta_path, self.keys_loc,
                        parent_name),
                    "-config", self.cnf_file,
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

        def make_cs_cert(self, new_name, parent_name, parent_loc=None,
                ext="v3_req", ca_path=None, expiring=False, expired=False,
                    future=False, https=False, passphrase=None):
                """Create a new code signing cert."""

                if not parent_loc:
                        parent_loc = self.trust_anchors_loc
                if not ca_path:
                        ca_path = self.base_dir
                subj_str_to_use = self.subj_str
                if https:
                        subj_str_to_use = self.https_subj_str
                cmd = ["openssl", "genrsa", "-out", "{0}/{1}_key.pem".format(
                    self.keys_dir, new_name), "1024"]
                p = subprocess.Popen(cmd)
                assert p.wait() == 0

                cmd = ["openssl", "req", "-new", "-nodes",
                    "-key", "{0}/{1}_key.pem".format(self.keys_dir, new_name),
                    "-out", "{0}/{1}.csr".format(self.cs_dir, new_name),
                    "-sha256", "-subj", subj_str_to_use.format(new_name, new_name)]
                p = subprocess.Popen(cmd)
                assert p.wait() == 0

                if passphrase:
                        # Add a passphrase to the key just created using a new filename.
                        cmd = ["openssl", "rsa", "-des3",
                            "-in", "{0}/{1}_key.pem".format(self.keys_dir, new_name),
                            "-out", "{0}/{1}_reqpass_key.pem".format(self.keys_dir,
                                new_name),
                            "-passout", "pass:{0}".format(passphrase)]
                        p = subprocess.Popen(cmd)
                        assert p.wait() == 0

                cmd = ["openssl", "ca", "-policy", "policy_anything",
                    "-extensions", ext,
                    "-out", "{0}/{1}_cert.pem".format(self.cs_dir, new_name),
                    "-in", "{0}/{1}.csr".format(self.cs_dir, new_name),
                    "-cert", "{0}/{1}/{2}_cert.pem".format(ca_path, parent_loc,
                        parent_name),
                    "-outdir", "{0}".format(self.cs_dir),
                    "-keyfile", "{0}/{1}/{2}_key.pem".format(ca_path, self.keys_loc,
                        parent_name),
                    "-config", self.cnf_file,
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
                elif expiring:
                        cmd.append("-days")
                        cmd.append("27")
                else:
                        cmd.append("-days")
                        cmd.append("1000")
                p = subprocess.Popen(cmd)
                assert p.wait() == 0

        def make_trust_anchor(self, name, https=False):
                """Make a new trust anchor."""

                subj_str_to_use = self.subj_str
                if https:
                        subj_str_to_use = self.https_subj_str
                cmd = ["openssl", "req", "-new", "-x509", "-nodes",
                    "-keyout", "{0}/{1}_key.pem".format(self.keys_dir, name),
                    "-subj", subj_str_to_use.format(name, name),
                    "-out", "{0}/{1}/{2}_cert.tmp".format(self.base_dir, name, name),
                    "-days", "1000",
                    "-sha256"]

                os.mkdir("{0}/{1}".format(self.base_dir, name))

                p = subprocess.Popen(cmd)
                assert p.wait() == 0
                self.convert_pem_to_text("{0}/{1}/{2}_cert.tmp".format(self.base_dir,
                    name, name), "{0}/{1}/{2}_cert.pem".format(self.base_dir, name,
                        name))

                try:
                        os.link("{0}/{1}/{2}_cert.pem".format(self.base_dir, name, name),
                            "{0}/{1}_cert.pem".format(self.raw_trust_anchor_dir, name))
                except:
                        shutil.copy("{0}/{1}/{2}_cert.pem".format(self.base_dir, name,
                            name), "{0}/{1}_cert.pem".format(self.raw_trust_anchor_dir,
                                name))

        def revoke_cert(self, ca, revoked_cert, ca_dir=None, cert_dir=None,
                ca_path=None):
                """Revoke a certificate using the CA given."""

                if not ca_dir:
                        ca_dir = ca
                if not cert_dir:
                        cert_dir = self.cs_loc
                if not ca_path:
                        ca_path = self.base_dir
                cmd = ["openssl", "ca", "-keyfile", "{0}/{1}/{2}_key.pem".format(
                    ca_path, self.keys_loc, ca),
                    "-cert", "{0}/{1}/{2}_cert.pem".format(ca_path, ca_dir, ca),
                    "-config", self.cnf_file,
                    "-revoke", "{0}/{1}/{2}_cert.pem".format(self.base_dir, cert_dir,
                    revoked_cert)]
                p = subprocess.Popen(cmd)
                assert p.wait() == 0

                cmd = ["openssl", "ca", "-gencrl",
                    "-keyfile", "{0}/{1}/{2}_key.pem".format(ca_path, self.keys_loc, ca),
                    "-cert", "{0}/{1}/{2}_cert.pem".format(ca_path, ca_dir, ca),
                    "-config", self.cnf_file,
                    "-out", "{0}/{1}_crl.tmp".format(self.crl_dir, ca),
                    "-crldays", "1000"]
                p = subprocess.Popen(cmd)
                assert p.wait() == 0
                self.convert_pem_to_text("{0}/{1}_crl.tmp".format(self.crl_dir, ca),
                    "{0}/{1}_crl.pem".format(self.crl_dir, ca), kind="crl")

        subj_str = "/C=US/ST=California/L=Santa Clara/O=pkg5/CN={0}/emailAddress={1}"
        https_subj_str = "/C=US/ST=California/L=Santa Clara/O=pkg5/OU={0}/" \
            "CN=localhost/emailAddress={1}"

        openssl_conf = """\
HOME                    = .
RANDFILE                = $ENV::HOME/.rnd

[ ca ]
default_ca      = CA_default

[ CA_default ]
dir             = {base_dir}
crl_dir         = $dir/crl
database        = $dir/index
serial          = $dir/serial

x509_extensions = usr_cert
unique_subject  = no

default_md      = sha256
preserve        = no

policy          = policy_match

# For the 'anything' policy
# At this point in time, you must list all acceptable 'object'
# types.
[ policy_anything ]
countryName             = optional
stateOrProvinceName     = optional
localityName            = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

####################################################################
[ req ]
default_bits            = 2048
default_keyfile         = ./private/ca-key.pem
default_md              = sha256

prompt                  = no
distinguished_name      = root_ca_distinguished_name

x509_extensions = v3_ca
string_mask = nombstr

[ root_ca_distinguished_name ]
commonName = ta1
countryName = US
stateOrProvinceName = California
localityName = Santa Clara
0.organizationName = pkg5
emailAddress = ta1@pkg5

[ usr_cert ]

# These extensions are added when 'ca' signs a request.

subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer:always

[ v3_req ]

# Extensions to add to a certificate request.

basicConstraints = critical,CA:FALSE
keyUsage = critical, digitalSignature

[ v3_confused_cs ]

# Have CA be true, but don't have keyUsage allow certificate signing to created
# a confused certificate.

basicConstraints = critical,CA:true
keyUsage = critical, digitalSignature

[ v3_no_keyUsage ]

# The extensions to use for a code signing certificate without a keyUsage
# extension.

basicConstraints = critical,CA:FALSE

[ v3_ca ]

# Extensions for a typical CA.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true
keyUsage = critical, keyCertSign, cRLSign

[ v3_ca_lp4 ]

# Extensions for a typical CA.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true,pathlen:4
keyUsage = critical, keyCertSign, cRLSign

[ v3_ca_lp3 ]

# Extensions for a typical CA

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true,pathlen:3
keyUsage = critical, keyCertSign, cRLSign

[ v3_ca_lp2 ]

# Extensions for a typical CA.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true,pathlen:2
keyUsage = critical, keyCertSign, cRLSign

[ v3_ca_lp1 ]

# Extensions for a typical CA.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true,pathlen:1
keyUsage = critical, keyCertSign, cRLSign

[ v3_ca_lp0 ]

# Extensions for a typical CA.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true,pathlen:0
keyUsage = critical, keyCertSign, cRLSign

[ v3_ca_no_crl ]

# Extensions for a CA which cannot sign a CRL.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true
keyUsage = critical, keyCertSign

[ v3_ca_no_keyUsage ]

# Extensions for a CA without keyUsage information.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true

[ issuer_ext ]

# Used for a code signing cert with an unsupported critical extension.

basicConstraints = critical,CA:FALSE
issuerAltName = critical,issuer:copy

[ issuer_ext_ca ]

# Used for a CA cert with an unsupported critical extension.

basicConstraints = critical,CA:TRUE
issuerAltName = critical,issuer:copy

[ issuer_ext_non_critical ]

# Used to test a recognized non-critical extension with an unrecognized value.

basicConstraints = critical,CA:FALSE
keyUsage = keyAgreement

[ issuer_ext_bad_val ]

# Used to test a recognized critical extension with an unrecognized value.
# keyAgreement needs to be set because otherwise Cryptography complains that
# encipherOnly requires keyAgreement.

basicConstraints = critical,CA:FALSE
keyUsage = critical, encipherOnly, keyAgreement

[ invalid_ext ]

# Used to test an invalid extension. Cryptography complains that enciperOnly
# requires keyAgreement, so this is an invalid extension.

basicConstraints = critical,CA:FALSE
keyUsage = encipherOnly

[ crl_ext ]

# Used for testing certificate revocation.

basicConstraints = critical,CA:FALSE
crlDistributionPoints = URI:http://localhost:12001/file/0/ch1_ta4_crl.pem

[ ch5_ta1_crl ]

# Used for testing certificate revocation.

basicConstraints = critical,CA:FALSE
crlDistributionPoints = URI:http://localhost:12001/file/0/ch5_ta1_crl.pem

[ ch1.1_ta4_crl ]

# Used for testing certificate revocation.

basicConstraints = critical,CA:FALSE
crlDistributionPoints = URI:http://localhost:12001/file/0/ch1.1_ta4_crl.pem

[ ch1_ta1_crl ]

# Used for testing certificate revocation at the level of a chain certificate.

basicConstraints = critical,CA:FALSE
crlDistributionPoints = URI:http://localhost:12001/file/0/ch1_pubCA1_crl.pem

[ crl_ca ]

# Used for testing CA certificate revocation by a trust anchor.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical,CA:true
crlDistributionPoints = URI:http://localhost:12001/file/0/ta5_crl.pem
keyUsage = critical, keyCertSign, cRLSign

[ bad_crl ]

# Used for testing a CRL with a bad file format.

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always

basicConstraints = critical,CA:false

crlDistributionPoints = URI:http://localhost:12001/file/0/example_file

[ bad_crl_loc ]

# PKIX recommendation.
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always

basicConstraints = critical,CA:false

crlDistributionPoints = URI:foo://bar/baz
"""


