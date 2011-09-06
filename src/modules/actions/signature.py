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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

import os
import shutil
import tempfile

import generic
import pkg.actions
import pkg.client.api_errors as apx
import pkg.misc as misc
import M2Crypto as m2

valid_hash_algs = ("sha256", "sha384", "sha512")
valid_sig_algs = ("rsa",)

class SignatureAction(generic.Action):
        """Class representing the signature-type packaging object."""

        __slots__ = ["hash", "hash_alg", "sig_alg", "cert_ident",
            "chain_cert_openers"]

        name = "signature"
        key_attr = "value"

        def __init__(self, data, **attrs):
                generic.Action.__init__(self, data, **attrs)

                self.hash = None
                self.chain_cert_openers = []

                try:
                        self.sig_alg, self.hash_alg = self.decompose_sig_alg(
                            self.attrs["algorithm"])
                except KeyError:
                        raise pkg.actions.InvalidActionError(str(self),
                            _("Missing algorithm attribute"))
                if "value" not in self.attrs:
                        self.attrs["value"] = ""
                if "version" not in self.attrs:
                        self.attrs["version"] = \
                            str(generic.Action.sig_version)

        @property
        def has_payload(self):
                # If there's a hash, then there's a certificate to deliver
                # with this action.
                if not self.hash:
                        return False
                return True

        def needsdata(self, orig, pkgplan):
                return self.has_payload

        @staticmethod
        def make_opener(pth):
                def file_opener():
                        return open(pth, "rb")
                return file_opener

        def __set_chain_certs_data(self, chain_certs, chash_dir):
                """Store the information about the certs needed to validate
                this signature in the signature.

                The 'chain_certs' parameter is a list of paths to certificates.
                """

                self.chain_cert_openers = []
                hshes = []
                sizes = []
                chshes = []
                csizes = []
                for pth in chain_certs:
                        if not os.path.exists(pth):
                                raise pkg.actions.ActionDataError(
                                    _("No such file: '%s'.") % pth, path=pth)
                        elif os.path.isdir(pth):
                                raise pkg.actions.ActionDataError(
                                    _("'%s' is not a file.") % pth, path=pth)
                        file_opener = self.make_opener(pth)
                        self.chain_cert_openers.append(file_opener)
                        self.attrs.setdefault("chain.sizes", [])
                        try:
                                fs = os.stat(pth)
                                sizes.append(str(fs.st_size))
                        except EnvironmentError, e:
                                raise pkg.actions.ActionDataError(e, path=pth)
                        # misc.get_data_digest takes care of closing the file
                        # that's opened below.
                        with file_opener() as fh:
                                hsh, data = misc.get_data_digest(fh,
                                    length=fs.st_size, return_content=True)
                        hshes.append(hsh)
                        csize, chash = misc.compute_compressed_attrs(hsh,
                            None, data, fs.st_size, chash_dir)
                        csizes.append(csize)
                        chshes.append(chash.hexdigest())
                if hshes:
                        # These attributes are stored as a single value with
                        # spaces in it rather than multiple values to ensure
                        # the ordering remains consistent.
                        self.attrs["chain.sizes"] = " ".join(sizes)
                        self.attrs["chain"] = " ".join(hshes)
                        self.attrs["chain.chashes"] = " ".join(chshes)
                        self.attrs["chain.csizes"] = " ".join(csizes)

        def get_size(self):
                res = generic.Action.get_size(self)
                for s in self.attrs.get("chain.sizes", "").split():
                        res += int(s)
                return res

        def get_action_chain_csize(self):
                res = 0
                for s in self.attrs.get("chain.csizes", "").split():
                        res += int(s)
                return res

        def get_chain_csize(self, chain):
                for c, s in zip(self.attrs.get("chain", "").split(),
                    self.attrs.get("chain.csizes", "").split()):
                        if c == chain:
                                return int(s)
                return None

        def get_chain_size(self, chain):
                for c, s in zip(self.attrs.get("chain", "").split(),
                    self.attrs.get("chain.sizes", "").split()):
                        if c == chain:
                                return int(s)
                return None

        def sig_str(self, a, version):
                """Create a stable string representation of an action that
                is deterministic in its creation.  If creating a string from an
                action is non-deterministic, then manifest signing cannot work.

                The parameter 'a' is the signature action that's going to use
                the string produced.  It's needed for the signature string
                action, and is here to keep the method signature the same.
                """

                # Any changes to this function mean Action.sig_version must be
                # incremented.

                if version != generic.Action.sig_version:
                        raise apx.UnsupportedSignatureVersion(version, sig=self)
                # Signature actions don't sign other signature actions.  So if
                # the action that's doing the signing isn't ourself, return
                # nothing.
                if str(a) != str(self):
                        return None

                # It's necessary to sign the action as the client will see it,
                # post publication.  To do that, it's necessary to simulate the
                # publication process on a copy of the action, converting
                # paths to hashes and adding size information.
                tmp_a = SignatureAction(None, **self.attrs)
                # The signature action can't sign the value of the value
                # attribute, but it can sign that attribute's name.
                tmp_a.attrs["value"] = ""
                if callable(self.data):
                        size = int(self.attrs.get("pkg.size", 0))
                        tmp_dir = tempfile.mkdtemp()
                        with self.data() as fh:
                                tmp_a.hash, data = misc.get_data_digest(fh,
                                    size, return_content=True)
                        csize, chash = misc.compute_compressed_attrs(
                            os.path.basename(self.hash), self.hash, data, size,
                            tmp_dir)
                        shutil.rmtree(tmp_dir)
                        tmp_a.attrs["pkg.csize"] = csize
                        tmp_a.attrs["chash"] = chash.hexdigest()
                elif self.hash:
                        tmp_a.hash = self.hash

                hashes = []
                csizes = []
                chashes = []
                sizes = self.attrs.get("chain.sizes", "").split()
                for i, c in enumerate(self.chain_cert_openers):
                        size = int(sizes[i])
                        tmp_dir = tempfile.mkdtemp()
                        hsh, data = misc.get_data_digest(c(), size,
                            return_content=True)
                        hashes.append(hsh)
                        csize, chash = misc.compute_compressed_attrs("tmp",
                            None, data, size, tmp_dir)
                        shutil.rmtree(tmp_dir)
                        csizes.append(csize)
                        chashes.append(chash.hexdigest())
                if hashes:
                        tmp_a.attrs["chain"] = " ".join(hashes)

                # Now that tmp_a looks like the post-published action, transform
                # it into a string using the generic sig_str method.
                return generic.Action.sig_str(tmp_a, tmp_a, version)
 
        def actions_to_str(self, acts, version):
                """Transforms a collection of actions into a string that is
                used to sign those actions."""

                # If a is None, then the action was another signature action so
                # discard it from the information to be signed.
                return "\n".join(sorted(
                    (a for a in
                     (b.sig_str(self, version) for b in acts)
                     if a is not None)))

        def retrieve_chain_certs(self, pub):
                """Retrieve the chain certificates needed to validate this
                signature."""

                for c in self.attrs.get("chain", "").split():
                        pub.get_cert_by_hash(c, only_retrieve=True)

        def get_chain_certs(self):
                """Return a list of the chain certificates needed to validate
                this signature."""
                return self.attrs.get("chain", "").split()

        def get_chain_certs_chashes(self):
                """Return a list of the chain certificates needed to validate
                this signature."""
                return self.attrs.get("chain.chashes", "").split()

        def is_signed(self):
                """Returns True if this action is signed using a key, instead
                of simply being a hash.  Since variant tagged signature
                actions are not handled yet, it also returns False in that
                case."""

                return self.hash is not None and not self.get_variant_template()

        @staticmethod
        def decompose_sig_alg(val):
                """Split the sig_alg attribute up in to something useful."""

                for s in valid_sig_algs:
                        for h in valid_hash_algs:
                                t = "%s-%s" % (s, h)
                                if val == t:
                                        return s, h
                for h in valid_hash_algs:
                        if h == val:
                                return None, h
                return None, None

        def verify_sig(self, acts, pub, trust_anchors, use_crls,
            required_names=None):
                """Try to verify this signature.  It can return True or
                None.  None means we didn't know how to verify this signature.
                If we do know how to verify the signature but it doesn't verify,
                then an exception is raised.

                The 'acts' parameter is the iterable of actions against which
                to verify the signature.

                The 'pub' parameter is the publisher that published the
                package this action signed.

                The 'trust_anchors' parameter contains the trust anchors to use
                when verifying the signature.

                The 'required_names' parameter is a set of strings that must
                be seen as a CN in the chain of trust for the certificate."""

                ver = int(self.attrs["version"])
                # If this signature is tagged with variants, if the version is
                # higher than one we know about, or it uses an unrecognized
                # hash algorithm, we can't handle it yet.
                if self.get_variant_template() or \
                    ver > generic.Action.sig_version or not self.hash_alg:
                        return None
                # Turning this into a list makes debugging vastly more
                # tractable.
                acts = list(acts)
                # If self.hash is None, then the signature is storing a hash
                # of the actions, not a signed value.
                if self.hash is None:
                        assert self.sig_alg is None
                        dgst = m2.EVP.MessageDigest(self.hash_alg)
                        res = dgst.update(self.actions_to_str(acts, ver))
                        assert res == 1, \
                            "Res was expected to be 1, but was %s" % res
                        computed_hash = dgst.final()
                        # The attrs value is stored in hex so that it's easy
                        # to read.
                        if misc.hex_to_binary(self.attrs["value"]) != \
                            computed_hash:
                                raise apx.UnverifiedSignature(self,
                                    _("The signature value did not match the "
                                    "expected value. action:%s") % self)
                        return True
                # Verify a signature that's not just a hash.
                if self.sig_alg is None:
                        return None
                # Get the certificate paired with the key which signed this
                # action.
                cert = pub.get_cert_by_hash(self.hash, verify_hash=True)
                # Make sure that the intermediate certificates that are needed
                # to validate this signature are present.
                self.retrieve_chain_certs(pub)
                try:
                        # This import is placed here to break a circular
                        # import seen when merge.py is used.
                        from pkg.client.publisher import CODE_SIGNING_USE
                        # Verify the certificate whose key created this
                        # signature action.
                        pub.verify_chain(cert, trust_anchors, 0, use_crls,
                            required_names=required_names,
                            usages=CODE_SIGNING_USE)
                except apx.SigningException, e:
                        e.act = self
                        raise
                # Check that the certificate verifies against this signature.
                pub_key = cert.get_pubkey(md=self.hash_alg)
                pub_key.verify_init()
                pub_key.verify_update(self.actions_to_str(acts, ver))
                res = pub_key.verify_final(
                    misc.hex_to_binary(self.attrs["value"]))
                if not res:
                        raise apx.UnverifiedSignature(self,
                            _("The signature value did not match the expected "
                            "value. Res: %s") % res)
                return True

        def set_signature(self, acts, key_path=None, chain_paths=misc.EmptyI,
            chash_dir=None):
                """Sets the signature value for this action.

                The 'acts' parameter is the iterable of actions this action
                should sign.

                The 'key_path' parameter is the path to the file containing the
                private key which is used to sign the actions.

                The 'chain_paths' parameter is an iterable of paths to
                certificates which are needed to form the chain of trust from
                the certificate associated with the key in 'key_path' to one of
                the CAs for the publisher of the actions.

                The 'chash_dir' parameter is the temporary directory to use
                while calculating the compressed hashes for chain certs."""

                # Turning this into a list makes debugging vastly more
                # tractable.
                acts = list(acts)

                # If key_path is None, then set value to be the hash
                # of the actions.
                if key_path is None:
                        # If no private key is set, then no certificate should
                        # have been given.
                        assert self.data is None
                        dgst = m2.EVP.MessageDigest(self.hash_alg)
                        res = dgst.update(self.actions_to_str(acts,
                            generic.Action.sig_version))
                        assert res == 1, \
                            "Res was expected to be 1, it was %s" % res
                        self.attrs["value"] = \
                            misc.binary_to_hex(dgst.final())
                else:
                        # If a private key is used, then the certificate it's
                        # paired with must be provided.
                        assert self.data is not None
                        self.__set_chain_certs_data(chain_paths, chash_dir)

                        try:
                                priv_key = m2.RSA.load_key(key_path)
                        except m2.RSA.RSAError:
                                raise apx.BadFileFormat(_("%s was expected to "
                                    "be a RSA key but could not be read "
                                    "correctly.") % key_path)
                        signer = m2.EVP.PKey(md=self.hash_alg)
                        signer.assign_rsa(priv_key, 1)
                        del priv_key
                        signer.sign_init()
                        signer.sign_update(self.actions_to_str(acts,
                            generic.Action.sig_version))

                        self.attrs["value"] = \
                            misc.binary_to_hex(signer.sign_final())

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                res = []
                if self.hash is not None:
                        res.append((self.name, "certificate", self.hash,
                            self.hash))
                res.append((self.name, "algorithm",
                    self.attrs["algorithm"], self.attrs["algorithm"]))
                res.append((self.name, "signature", self.attrs["value"],
                    self.attrs["value"]))
                return res

        def identical(self, other, hsh):
                """Check whether another action is identical to this
                signature."""
                # Only signature actions can be identical to other signature
                # actions.
                if self.name != other.name:
                        return False
                # If the code signing certs are identical, the more checking is
                # needed.
                if hsh == other.hash or self.hash == other.hash:
                        # If the algorithms are using different algorithms or
                        # have different versions, then they're not identical.
                        if self.attrs["algorithm"]  != \
                            other.attrs["algorithm"] or \
                            self.attrs["version"] != other.attrs["version"]:
                                return False
                        # If the values are the same, then they're identical.
                        if self.attrs["value"] == other.attrs["value"]:
                                return True
                        raise apx.AlmostIdentical(hsh,
                            self.attrs["algorithm"], self.attrs["version"])
                return False
        def __getstate__(self):
                """This object doesn't have a default __dict__, instead it
                stores its contents via __slots__.  Hence, this routine must
                be provide to translate this object's contents into a
                dictionary for pickling"""

                pstate = generic.Action.__getstate__(self)
                state = {}
                for name in SignatureAction.__slots__:
                        if not hasattr(self, name):
                                continue
                        state[name] = getattr(self, name)
                return (state, pstate)

        def __setstate__(self, state):
                """This object doesn't have a default __dict__, instead it
                stores its contents via __slots__.  Hence, this routine must
                be provide to translate a pickled dictionary copy of this
                object's contents into a real in-memory object."""

                (state, pstate) = state
                generic.Action.__setstate__(self, pstate)
                for name in state:
                        setattr(self, name, state[name])

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action.
                """

                # 'value' can only be required at publication time since signing
                # relies on the ability to construct actions without one despite
                # the fact that it is the key attribute.
                generic.Action._validate(self, fmri=fmri,
                    numeric_attrs=("pkg.csize", "pkg.size"),
                    required_attrs=("value",), single_attrs=("algorithm",
                    "chash", "value"))
