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
# Copyright (c) 2013, 2015, Oracle and/or its affiliates. All rights reserved.
#

import hashlib
try:
        import pkg.sha512_t
        sha512_supported = True
except ImportError:
        sha512_supported = False

# When running the test suite, we alter our behaviour depending on certain
# debug flags.
from pkg.client.debugvalues import DebugValues

# pkg(5) uses cryptographic hash functions for a number of tasks. We define the
# default hash function, along with the hash name here. Note that the use of
# hashes in package metadata is *not* governed by this value, since multiple
# hashes are supported for payload-bearing actions in a package.
#
# Some uses of hashes are image-format specific, and may require image version
# increments, in which case the required algorithm is hardcoded where it is
# used, along with with an appropriate comment.
#
# Other uses are essentially volatile, and the hash used has no persistence
# (e.g. saving the hash to a file in a temporary directory, when the hash gets
# regenerated on service restart). For those volatile uses, DEFAULT_HASH_FUNC is
# recommended.
DEFAULT_HASH_FUNC = hashlib.sha1
DEFAULT_HASH_NAME = "sha-1"

# DEFAULT_XXX_ATTRS are the attributes added to actions by the packaging system
# at publication time.
#
# Notably, the hashes we add to an action at publication *do not* need to
# correspond to the hashes we may use to verify action payload during install or
# update, allowing an upgrade path where we could choose to drop publication
# support for a certain hash algorithm, but still retain the ability to install
# actions using that hash.
#
# The order of these lists of attributes is significant only to the
# extent that the repository code will store the file in the repository using
# the first hash value in the list when using the *old* publication model (ie.
# a transaction, with multiple add_file(..) methods to add content)
#
# Otherwise, when publishing, we always store files in the repository
# using the "least preferred" hash for maximum backwards compatibility with
# older packaging tools that expect to be able to find those hashes in the
# repository, but do add additional hashes to the action metadata.
#
# When using the transport to download content from a repository, we use the
# least preferred_hash for file retrieval, but verify the installed content
# using the "most preferred" hash. See get_preferred_hash(..),
# get_least_preferred_hash(..) and get_common_preferred_hash(..)
#
if DebugValues["hash"] == "sha1+sha512_256" and sha512_supported:
        # Simulate pkg(5) where SHA-1 and SHA-512/256 are used for publication
        DEFAULT_HASH_ATTRS = ["hash", "pkg.hash.sha512_256"]
        DEFAULT_CHASH_ATTRS = ["chash", "pkg.chash.sha512_256"]
        DEFAULT_CONTENT_HASH_ATTRS = ["elfhash", "pkg.content-hash.sha512_256"]
        DEFAULT_CHAIN_ATTRS = ["chain", "pkg.chain.sha512_256"]
        DEFAULT_CHAIN_CHASH_ATTRS = ["chain.chashes",
            "pkg.chain.chashes.sha512_256"]

elif DebugValues["hash"] == "sha1+sha256":
        # Simulate pkg(5) where SHA-1 and SHA-256 are used for publication
        DEFAULT_HASH_ATTRS = ["hash", "pkg.hash.sha256"]
        DEFAULT_CHASH_ATTRS = ["chash", "pkg.chash.sha256"]
        DEFAULT_CONTENT_HASH_ATTRS = ["elfhash", "pkg.content-hash.sha256"]
        DEFAULT_CHAIN_ATTRS = ["chain", "pkg.chain.sha256"]
        DEFAULT_CHAIN_CHASH_ATTRS = ["chain.chashes",
            "pkg.chain.chashes.sha256"]

elif DebugValues["hash"] == "sha512_256" and sha512_supported:
        # Simulate pkg(5) where SHA-1 is no longer used for publication
        DEFAULT_HASH_ATTRS = ["pkg.hash.sha512_256"]
        DEFAULT_CHASH_ATTRS = ["pkg.chash.sha512_256"]
        DEFAULT_CONTENT_HASH_ATTRS = ["pkg.content-hash.sha512_256"]
        DEFAULT_CHAIN_ATTRS = ["pkg.chain.sha512_256"]
        DEFAULT_CHAIN_CHASH_ATTRS = ["pkg.chain.chashes.sha512_256"]

elif DebugValues["hash"] == "sha256":
        # Simulate pkg(5) where SHA-1 is no longer used for publication
        DEFAULT_HASH_ATTRS = ["pkg.hash.sha256"]
        DEFAULT_CHASH_ATTRS = ["pkg.chash.sha256"]
        DEFAULT_CONTENT_HASH_ATTRS = ["pkg.content-hash.sha256"]
        DEFAULT_CHAIN_ATTRS = ["pkg.chain.sha256"]
        DEFAULT_CHAIN_CHASH_ATTRS = ["pkg.chain.chashes.sha256"]

else:
        # The current default is to add just a single hash value for each hash
        # type
        DEFAULT_HASH_ATTRS = ["hash"]
        DEFAULT_CHASH_ATTRS = ["chash"]
        # 'elfhash' was the only content-hash attribute originally supported
        DEFAULT_CONTENT_HASH_ATTRS = ["elfhash"]
        DEFAULT_CHAIN_ATTRS = ["chain"]
        DEFAULT_CHAIN_CHASH_ATTRS = ["chain.chashes"]

# The types of hashes we compute or consult for actions.
HASH = 0
CHASH = 1
CONTENT_HASH = 2
CHAIN = 3
CHAIN_CHASH = 4

# In the dictionaries below, we map the action attributes to the name of the
# class or factory-method that returns an object used to compute that attribute.
# The class or factory-method takes a 0-parameter constructor to return an
# object which must have an 'update(data)'  method , used to update the hash
# value being computed with this data, along with a 'hexdigest()' method to
# return the hexadecimal value of the hash.
#
# At present, some of these are hashlib factory methods. When maintaining these
# dictionaries, it is important to *never remove* entries from them, otherwise
# clients with installed packages will not be able to verify their content when
# pkg(5) is updated.

# A dictionary of the pkg(5) hash attributes we know about.
if DebugValues["hash"] == "sha1":
        # Simulate older non-SHA2 aware pkg(5) code
        HASH_ALGS = {"hash": hashlib.sha1}
else:
        HASH_ALGS = {
            "hash":            hashlib.sha1,
            "pkg.hash.sha256": hashlib.sha256,
        }

        if sha512_supported:
                HASH_ALGS["pkg.hash.sha512_256"] = pkg.sha512_t.SHA512_t

# A dictionary of the compressed hash attributes we know about.
CHASH_ALGS = {}
for key in HASH_ALGS:
        CHASH_ALGS[key.replace("hash", "chash")] = HASH_ALGS[key]

# A dictionary of the content-hash attributes we know about.
# For now, ELF files are the only ones which have a specific content-hash
# attribute.
CONTENT_HASH_ALGS = {}
for key in HASH_ALGS:
        if key == "hash":
                CONTENT_HASH_ALGS["elfhash"] = HASH_ALGS[key]
        # For now, we don't want content-hash in attributes by default since
        # the algorithm for it is changing soon.
        elif DebugValues["hash"]:
                CONTENT_HASH_ALGS[key.replace("hash", "content-hash")] = \
                    HASH_ALGS[key]

# A dictionary of signature action chain hash attributes we know about.
CHAIN_ALGS = {}
for key in HASH_ALGS:
        CHAIN_ALGS[key.replace("hash", "chain")] = HASH_ALGS[key]

# A dictionary of signature action chain chash attributes we know about.
CHAIN_CHASH_ALGS = {}
for key in HASH_ALGS:
        CHAIN_CHASH_ALGS[key.replace("hash", "chain.chashes")] = HASH_ALGS[key]


# Ordered lists of "most preferred" hash algorithm to "least preferred"
# algorithm for each hash attribute we use. It's important to *never remove*
# items from this list, otherwise we would strand clients installed with
# packages using hashes that correspond to that item. Instead promote/demote the
# hash algorithm so that better hashes are used for new packages.
# 'hash' is a dummy attribute name, since it really references the action.hash
# member.
#
if DebugValues["hash"] == "sha1":
        RANKED_HASH_ATTRS = ("hash")
elif DebugValues["hash"] == "sha2":
        if sha512_supported:
                RANKED_HASH_ATTRS = ("pkg.hash.sha512_256",)
        else:
                RANKED_HASH_ATTRS = ("pkg.hash.sha256",)
else:
        RANKED_HASH_ATTRS = (
            "pkg.hash.sha256",
            "hash",
        )

        if sha512_supported:
                RANKED_HASH_ATTRS = (
                    "pkg.hash.sha512_256",
                ) + RANKED_HASH_ATTRS

RANKED_CHASH_ATTRS = tuple(key.replace("hash", "chash")
    for key in RANKED_HASH_ATTRS)
_content_hash_attrs = []
for key in RANKED_HASH_ATTRS:
        if key == "hash":
                _content_hash_attrs.append("elfhash")
        # For now, we don't want content-hash in attributes by default since
        # the algorithm for it is changing soon.
        elif DebugValues["hash"]:
                _content_hash_attrs.append(key.replace("hash", "content-hash"))

RANKED_CONTENT_HASH_ATTRS = tuple(_content_hash_attrs)
RANKED_CHAIN_ATTRS = tuple(key.replace("hash", "chain") for key in
    RANKED_HASH_ATTRS)
RANKED_CHAIN_CHASH_ATTRS = tuple(key.replace("hash", "chain.chashes") for key in
    RANKED_HASH_ATTRS)


# We keep reverse-order lists for all of the hash attribute we know about
# because hash retrieval from the repository is always done using the least
# preferred hash, allowing for backwards compatibility with existing clients.
# Rather than compute the reverse-list every time we call
# get_least_preferred_hash(..) we compute them here.
REVERSE_RANKED_HASH_ATTRS = RANKED_HASH_ATTRS[::-1]
REVERSE_RANKED_CHASH_ATTRS = RANKED_CHASH_ATTRS[::-1]
REVERSE_RANKED_CONTENT_HASH_ATTRS = RANKED_CONTENT_HASH_ATTRS[::-1]
REVERSE_RANKED_CHAIN_ATTRS = RANKED_CHAIN_ATTRS[::-1]
REVERSE_RANKED_CHAIN_CHASH_ATTRS = RANKED_CHAIN_CHASH_ATTRS[::-1]


def _get_hash_dics(hash_type, reverse=False):
        """Based on the 'hash_type', return a tuple describing the ranking of
        hash attributes from "most preferred" to "least preferred" and a
        mapping of those attributes to the hash algorithms that are used to
        compute those attributes.

        If 'reverse' is true, return the rank_tuple in reverse order, from least
        preferred hash to most preferred hash.
        """

        if hash_type == HASH:
                if reverse:
                        rank_tuple = REVERSE_RANKED_HASH_ATTRS
                else:
                        rank_tuple = RANKED_HASH_ATTRS
                hash_dic = HASH_ALGS
        elif hash_type == CHASH:
                if reverse:
                        rank_tuple = REVERSE_RANKED_CHASH_ATTRS
                else:
                        rank_tuple = RANKED_CHASH_ATTRS
                hash_dic = CHASH_ALGS
        elif hash_type == CONTENT_HASH:
                if reverse:
                        rank_tuple = REVERSE_RANKED_CONTENT_HASH_ATTRS
                else:
                        rank_tuple = RANKED_CONTENT_HASH_ATTRS
                hash_dic = CONTENT_HASH_ALGS
        elif hash_type == CHAIN:
                if reverse:
                        rank_tuple = REVERSE_RANKED_CHAIN_ATTRS
                else:
                        rank_tuple = RANKED_CHAIN_ATTRS
                hash_dic = CHAIN_ALGS
        elif hash_type == CHAIN_CHASH:
                if reverse:
                        rank_tuple = REVERSE_RANKED_CHAIN_CHASH_ATTRS
                else:
                        rank_tuple = RANKED_CHAIN_CHASH_ATTRS
                hash_dic = CHAIN_CHASH_ALGS
        else:
                rank_tuple = None
                hash_dic = None

        return rank_tuple, hash_dic


def get_preferred_hash(action, hash_type=HASH):
        """Returns a tuple of the form (hash_attr, hash_val, hash_func)
        where 'hash_attr' is the preferred hash attribute name, 'hash_val'
        is the the preferred hash value, and 'hash_func' is the function
        used to compute the preferred hash based on the available
        pkg.*hash.* attributes declared in the action."""

        rank_tuple, hash_dic = _get_hash_dics(hash_type)
        if not (rank_tuple and hash_dic):
                raise ValueError("Unknown hash_type {0} passed to "
                    "get_preferred_hash".format(hash_type))

        for hash_attr_name in rank_tuple:
                if hash_attr_name in action.attrs:
                        return hash_attr_name, action.attrs[hash_attr_name], \
                            hash_dic[hash_attr_name]

        # fallback to the default hash member since it's not in action.attrs
        if hash_type == HASH:
                return None, action.hash, hashlib.sha1
        # an action can legitimately have no chash
        if hash_type == CHASH:
                return None, None, DEFAULT_HASH_FUNC
        # an action can legitimately have no content-hash if it's not a file
        # type we know about
        if hash_type == CONTENT_HASH:
                return None, None, None
        # an action can legitimately have no chain
        if hash_type == CHAIN:
                return None, None, None
        # an action can legitimately have no chain_chash
        if hash_type == CHAIN_CHASH:
                return None, None, None

        # This should never happen.
        raise Exception("Error determining the preferred hash for {0} {1}".format(
            action, hash_type))


def get_least_preferred_hash(action, hash_type=HASH):
        """Returns a tuple of the least preferred hash attribute name, the hash
        value that should result when we compute the hash, and the function used
        to compute the hash based on the available hash and pkg.*hash.*
        attributes declared in the action."""

        # the default hash member since it's not in action.attrs
        if hash_type == HASH:
                if not action:
                        return "hash", None, hashlib.sha1

                # This is nearly always true, except when we're running the
                # test suite and have intentionally disabled SHA-1 hashes.
                if "hash" in DEFAULT_HASH_ATTRS:
                        return None, action.hash, hashlib.sha1

        rank_list, hash_dic = _get_hash_dics(hash_type, reverse=True)
        if not (rank_list and hash_dic):
                raise ValueError("Unknown hash_type {0} passed to "
                    "get_preferred_hash".format(hash_type))

        if not action:
                return rank_list[0], None, hash_dic[rank_list[0]]

        for hash_attr_name in rank_list:
                if hash_attr_name in action.attrs:
                        return hash_attr_name, action.attrs[hash_attr_name], \
                            hash_dic[hash_attr_name]

        # an action can legitimately have no chash
        if hash_type == CHASH:
                return None, None, DEFAULT_HASH_FUNC
        # an action can legitimately have no content-hash if it's not a file
        # type we know about
        if hash_type == CONTENT_HASH:
                return None, None, None
        # an action can legitimately have no chain
        if hash_type == CHAIN:
                return None, None, None

        # This should never happen.
        raise Exception("Error determining the least preferred hash for {0} {1}".format(
            action, hash_type))


def get_common_preferred_hash(action, old_action, hash_type=HASH):
        """Returns the best common hash attribute of those shared between a new
        action and an installed (old) version of that action. We return the
        name of the common attribute, the new and original values of that
        attribute, and the function used to compute the hash.

        If no common attribute is found, we fallback to the legacy <Action>.hash
        member assuming it is not None for the new and orig actions, and specify
        hashlib.sha1 as the algorithm. If no 'hash' member is set, we return
        a tuple of None objects."""

        if not old_action:
                return None, None, None, None

        rank_list, hash_dic = _get_hash_dics(hash_type)
        if not (rank_list and hash_dic):
                raise ValueError("Unknown hash_type {0} passed to "
                    "get_preferred_common_hash".format(hash_type))

        common_attrs = set(
            action.attrs.keys()).intersection(set(old_action.attrs.keys()))
        for hash_attr_name in rank_list:
                if hash_attr_name in common_attrs:
                        return hash_attr_name, action.attrs[hash_attr_name], \
                            old_action.attrs[hash_attr_name], \
                            hash_dic[hash_attr_name]

        if action.hash and old_action.hash:
                return None, action.hash, old_action.hash, hashlib.sha1
        return None, None, None, None
