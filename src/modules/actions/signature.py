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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

import hashlib
import os
import shutil
import tempfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

from . import generic
import pkg.actions
import pkg.client.api_errors as apx
import pkg.digest as digest
import pkg.misc as misc

valid_hash_algs = ("sha256", "sha384", "sha512")
valid_sig_algs = ("rsa",)

class SignatureAction(generic.Action):
        """Class representing the signature-type packaging object."""

        __slots__ = ["hash", "hash_alg", "sig_alg", "cert_ident",
            "chain_cert_openers"]

        name = "signature"
        key_attr = "value"
        ordinality = generic._orderdict[name]

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

                # chain_hshes and chain_chshes are dictionaries which map a
                # given hash or compressed hash attribute to a list of the hash
                # values for each path in chain_certs.
                chain_hshes = {}
                chain_chshes = {}
                chain_csizes = []
                chain_sizes = []

                for attr in digest.DEFAULT_CHAIN_ATTRS:
                        chain_hshes[attr] = []
                for attr in digest.DEFAULT_CHAIN_CHASH_ATTRS:
                        chain_chshes[attr] = []

                for pth in chain_certs:
                        if not os.path.exists(pth):
                                raise pkg.actions.ActionDataError(
                                    _("No such file: '{0}'.").format(pth),
                                    path=pth)
                        elif os.path.isdir(pth):
                                raise pkg.actions.ActionDataError(
                                    _("'{0}' is not a file.").format(pth),
                                    path=pth)
                        file_opener = self.make_opener(pth)
                        self.chain_cert_openers.append(file_opener)
                        self.attrs.setdefault("chain.sizes", [])
                        self.attrs.setdefault("chain.csizes", [])

                        try:
                                fs = os.stat(pth)
                                chain_sizes.append(str(fs.st_size))
                        except EnvironmentError as e:
                                raise pkg.actions.ActionDataError(e, path=pth)
                        # misc.get_data_digest takes care of closing the file
                        # that's opened below.
                        with file_opener() as fh:
                                hshes, data = misc.get_data_digest(fh,
                                    length=fs.st_size, return_content=True,
                                    hash_attrs=digest.DEFAULT_CHAIN_ATTRS,
                                    hash_algs=digest.CHAIN_ALGS)

                        for attr in hshes:
                                chain_hshes[attr].append(hshes[attr])

                        # We need a filename to use for the uncompressed chain
                        # cert, so get the preferred chain hash value from the
                        # chain_hshes
                        chain_val = None
                        for attr in digest.RANKED_CHAIN_ATTRS:
                                if not chain_val and attr in hshes:
                                        chain_val = hshes[attr]

                        csize, chashes = misc.compute_compressed_attrs(
                            chain_val, None, data, fs.st_size, chash_dir,
                            chash_attrs=digest.DEFAULT_CHAIN_CHASH_ATTRS,
                            chash_algs=digest.CHAIN_CHASH_ALGS)

                        chain_csizes.append(csize)
                        for attr in chashes:
                                chain_chshes[attr].append(
                                    chashes[attr].hexdigest())

                # Remove any unused hash attributes.
                for cattrs in (chain_hshes, chain_chshes):
                        for attr in list(cattrs.keys()):
                                if not cattrs[attr]:
                                        cattrs.pop(attr, None)

                if chain_hshes:
                        # These attributes are stored as a single value with
                        # spaces in it rather than multiple values to ensure
                        # the ordering remains consistent.
                        self.attrs["chain.sizes"] = " ".join(chain_sizes)
                        self.attrs["chain.csizes"] = " ".join(chain_csizes)

                        for attr in digest.DEFAULT_CHAIN_ATTRS:
                                self.attrs[attr] = " ".join(chain_hshes[attr])
                        for attr in digest.DEFAULT_CHAIN_CHASH_ATTRS:
                                self.attrs[attr] = " ".join(chain_chshes[attr])

        def __get_hash_by_name(self, name):
                """Get the cryptopgraphy Hash() class based on the OpenSSL
                algorithm name."""

                for h in hashes.HashAlgorithm._abc_registry:
                        if h.name == name:
                                return h

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
                # The length of 'chain' is also going to be the length
                # of pkg.chain.<hash alg>, so there's no need to look for
                # other hash attributes here.
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
                if hasattr(self.data, "__call__"):
                        size = int(self.attrs.get("pkg.size", 0))
                        tmp_dir = tempfile.mkdtemp()
                        with self.data() as fh:
                                hashes, data = misc.get_data_digest(fh,
                                    size, return_content=True,
                                    hash_attrs=digest.DEFAULT_HASH_ATTRS,
                                    hash_algs=digest.HASH_ALGS)
                                tmp_a.attrs.update(hashes)
                                # "hash" is special since it shouldn't appear in
                                # the action attributes, it gets set as a member
                                # instead.
                                if "hash" in tmp_a.attrs:
                                        tmp_a.hash = tmp_a.attrs["hash"]
                                        del tmp_a.attrs["hash"]

                        # The use of self.hash here is just to point to a
                        # filename, the type of hash used for self.hash is
                        # irrelevant. Note that our use of self.hash for the
                        # basename will need to be modified when we finally move
                        # off SHA-1 hashes.
                        csize, chashes = misc.compute_compressed_attrs(
                            os.path.basename(self.hash), self.hash, data, size,
                            tmp_dir)
                        shutil.rmtree(tmp_dir)
                        tmp_a.attrs["pkg.csize"] = csize
                        for attr in chashes:
                                tmp_a.attrs[attr] = chashes[attr].hexdigest()
                elif self.hash:
                        tmp_a.hash = self.hash
                        for attr in digest.DEFAULT_HASH_ATTRS:
                                if attr in self.attrs:
                                        tmp_a.attrs[attr] = self.attrs[attr]

                csizes = []
                chain_hashes = {}
                chain_chashes = {}
                for attr in digest.DEFAULT_CHAIN_ATTRS:
                        chain_hashes[attr] = []
                for attr in digest.DEFAULT_CHAIN_CHASH_ATTRS:
                        chain_chashes[attr] = []

                sizes = self.attrs.get("chain.sizes", "").split()
                for i, c in enumerate(self.chain_cert_openers):
                        size = int(sizes[i])
                        tmp_dir = tempfile.mkdtemp()
                        hshes, data = misc.get_data_digest(c(), size,
                            return_content=True,
                            hash_attrs=digest.DEFAULT_CHAIN_ATTRS,
                            hash_algs=digest.CHAIN_ALGS)

                        for attr in hshes:
                            chain_hashes[attr].append(hshes[attr])

                        csize, chashes = misc.compute_compressed_attrs("tmp",
                            None, data, size, tmp_dir,
                            chash_attrs=digest.DEFAULT_CHAIN_CHASH_ATTRS,
                            chash_algs=digest.CHAIN_CHASH_ALGS)
                        shutil.rmtree(tmp_dir)
                        csizes.append(csize)
                        for attr in chashes:
                                chain_chashes[attr].append(
                                    chashes[attr].hexdigest())

                if chain_hashes:
                        for attr in digest.DEFAULT_CHAIN_ATTRS:
                                if chain_hashes[attr]:
                                        tmp_a.attrs[attr] = " ".join(
                                            chain_hashes[attr])

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

                chain_attr, chain_val, hash_func = \
                    digest.get_least_preferred_hash(self,
                    hash_type=digest.CHAIN)
                # We may not have any chain certs for this signature
                if not chain_val:
                        return
                for c in chain_val.split():
                        pub.get_cert_by_hash(c, only_retrieve=True,
                            hash_func=hash_func)

        def get_chain_certs(self, least_preferred=False):
                """Return a list of the chain certificates needed to validate
                this signature. When retrieving the content from the
                repository, we use the "least preferred" hash for backwards
                compatibility, but when verifying the content, we use the
                "most preferred" hash."""

                if least_preferred:
                        chain_attr, chain_val, hash_func = \
                            digest.get_least_preferred_hash(self,
                            hash_type=digest.CHAIN)
                else:
                        chain_attr, chain_val, hash_func = \
                            digest.get_preferred_hash(self,
                            hash_type=digest.CHAIN)
                if not chain_val:
                        return []
                return chain_val.split()

        def get_chain_certs_chashes(self, least_preferred=False):
                """Return a list of the chain certificates needed to validate
                this signature."""

                if least_preferred:
                        chain_chash_attr, chain_chash_val, hash_func = \
                            digest.get_least_preferred_hash(self,
                            hash_type=digest.CHAIN_CHASH)
                else:
                        chain_chash_attr, chain_chash_val, hash_func = \
                            digest.get_preferred_hash(self,
                            hash_type=digest.CHAIN_CHASH)
                if not chain_chash_val:
                        return []
                return chain_chash_val.split()

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
                                t = "{0}-{1}".format(s, h)
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
                        h = hashlib.new(self.hash_alg)
                        h.update(misc.force_bytes(self.actions_to_str(
                            acts, ver)))
                        computed_hash = h.digest()
                        # The attrs value is stored in hex so that it's easy
                        # to read.
                        if misc.hex_to_binary(self.attrs["value"]) != \
                            computed_hash:
                                raise apx.UnverifiedSignature(self,
                                    _("The signature value did not match the "
                                    "expected value. action: {0}").format(self))
                        return True
                # Verify a signature that's not just a hash.
                if self.sig_alg is None:
                        return None
                # Get the certificate paired with the key which signed this
                # action.
                attr, hash_val, hash_func = \
                    digest.get_least_preferred_hash(self)
                cert = pub.get_cert_by_hash(hash_val, verify_hash=True,
                    hash_func=hash_func)
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
                except apx.SigningException as e:
                        e.act = self
                        raise
                # Check that the certificate verifies against this signature.
                pub_key = cert.public_key()
                hhash = self.__get_hash_by_name(self.hash_alg)
                verifier = pub_key.verifier(
                    misc.hex_to_binary(self.attrs["value"]), padding.PKCS1v15(),
                    hhash())
                verifier.update(misc.force_bytes(
                    self.actions_to_str(acts, ver)))
                try:
                        verifier.verify()
                except InvalidSignature:
                        raise apx.UnverifiedSignature(self,
                            _("The signature value did not match the expected "
                            "value."))

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
                        h = hashlib.new(self.hash_alg)
                        h.update(misc.force_bytes(self.actions_to_str(acts,
                            generic.Action.sig_version)))
                        self.attrs["value"] = h.hexdigest()
                else:
                        # If a private key is used, then the certificate it's
                        # paired with must be provided.
                        assert self.data is not None
                        self.__set_chain_certs_data(chain_paths, chash_dir)

                        try:
                                with open(key_path, "rb") as f:
                                        priv_key = serialization.load_pem_private_key(
                                            f.read(), password=None,
                                            backend=default_backend())
                        except ValueError:
                                raise apx.BadFileFormat(_("{0} was expected to "
                                    "be a RSA key but could not be read "
                                    "correctly.").format(key_path))

                        hhash = self.__get_hash_by_name(self.hash_alg)
                        signer = priv_key.signer(padding.PKCS1v15(), hhash())
                        signer.update(misc.force_bytes(self.actions_to_str(acts,
                            generic.Action.sig_version)))
                        self.attrs["value"] = \
                                misc.binary_to_hex(signer.finalize())

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
                for attr in digest.DEFAULT_HASH_ATTRS:
                        # we already have an index entry for self.hash
                        if attr == "hash":
                                continue
                        hash = self.attrs[attr]
                        res.append((self.name, attr, hash, None))
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
                # Determine if we share any hash attribute values with the other
                # action.
                matching_hash_attrs = set()
                for attr in digest.DEFAULT_HASH_ATTRS:
                        if attr == "hash":
                                # we deal with the 'hash' member later
                                continue
                        if attr in self.attrs and attr in other.attrs and \
                            self.attrs[attr] == other.attrs[attr] and \
                            self.assrs[attr]:
                                    matching_hash_attrs.add(attr)
                        if hsh and hsh == other.attrs.get(attr):
                                # Technically 'hsh' isn't a hash attr, it's
                                # a hash attr value, but that's enough for us
                                # to consider it as potentially identical.
                                matching_hash_attrs.add(hsh)

                if hsh == other.hash or self.hash == other.hash or \
                    matching_hash_attrs:
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
