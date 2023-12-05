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
# Copyright (c) 2013, 2023, Oracle and/or its affiliates.
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

# pkg(7) uses cryptographic hash functions for a number of tasks. We define the
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

LEGACY_HASH_ATTRS = ["hash"]
LEGACY_CHASH_ATTRS = ["chash"]
LEGACY_CONTENT_HASH_ATTRS = ["elfhash"]
LEGACY_CHAIN_ATTRS = ["chain"]
LEGACY_CHAIN_CHASH_ATTRS = ["chain.chashes"]

RANKED_HASHES = []
if DebugValues["hash"]:
    _hashes = reversed(DebugValues["hash"].split("+"))
else:
    _hashes = ("sha512t_256", "sha256", "sha1")

for alg in _hashes:
    if alg == "sha512t_256":
        if not sha512_supported:
            continue
    RANKED_HASHES.append(alg)

PREFERRED_HASH = RANKED_HASHES[0]
REVERSE_RANKED_HASHES = RANKED_HASHES[::-1]

DEFAULT_HASH_ATTRS = []
DEFAULT_CHASH_ATTRS = []
DEFAULT_GELF_HASH_ATTRS = []
DEFAULT_CHAIN_ATTRS = []
DEFAULT_CHAIN_CHASH_ATTRS = []

if "sha1" in RANKED_HASHES:
    DEFAULT_HASH_ATTRS.append("hash")
    DEFAULT_CHASH_ATTRS.append("chash")
    DEFAULT_GELF_HASH_ATTRS.append("elfhash")
    DEFAULT_CHAIN_ATTRS.append("chain")
    DEFAULT_CHAIN_CHASH_ATTRS.append("chain.chashes")

if PREFERRED_HASH != "sha1":
    DEFAULT_HASH_ATTRS.append("pkg.content-hash")
    DEFAULT_CHASH_ATTRS.append("pkg.content-hash")
    DEFAULT_GELF_HASH_ATTRS.append("pkg.content-hash")
    DEFAULT_CHAIN_ATTRS.append("pkg.chain.{0}".format(PREFERRED_HASH))
    DEFAULT_CHAIN_CHASH_ATTRS.append("pkg.chain.chashes.{0}".format(PREFERRED_HASH))

UNSIGNED_GELF_HASH_MAP = {
    "gelf:" + PREFERRED_HASH: "gelf.unsigned:" + PREFERRED_HASH
}

# The types of hashes we compute or consult for actions.
HASH = 0
HASH_GELF = 1
CHASH = 2
CHAIN = 3
CHAIN_CHASH = 4

EXTRACT_FILE = "file"
EXTRACT_GELF = "gelf"
EXTRACT_GZIP = "gzip"

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
# pkg(7) is updated.

# Dictionaries of the pkg(7) hash and content-hash attributes we know about.
if DebugValues["hash"] == "sha1":
    # Simulate older non-SHA2 aware pkg(7) code
    HASH_ALGS = {"hash": hashlib.sha1}
    GELF_HASH_ALGS = {"elfhash": hashlib.sha1}
else:
    HASH_ALGS = {
        "hash":            hashlib.sha1,
        "pkg.hash.sha256": hashlib.sha256,
        "file:sha256": hashlib.sha256,
        "gzip:sha256": hashlib.sha256,
    }

    GELF_HASH_ALGS = {
        "elfhash":     hashlib.sha1,
        "gelf:sha256": hashlib.sha256,
        "file:sha256": hashlib.sha256
    }

    if sha512_supported:
        HASH_ALGS["pkg.hash.sha512t_256"] = pkg.sha512_t.SHA512_t
        HASH_ALGS["file:sha512t_256"] = pkg.sha512_t.SHA512_t
        HASH_ALGS["gzip:sha512t_256"] = pkg.sha512_t.SHA512_t
        GELF_HASH_ALGS["gelf:sha512t_256"] = pkg.sha512_t.SHA512_t
        GELF_HASH_ALGS["file:sha512t_256"] = pkg.sha512_t.SHA512_t

# A dictionary of the compressed hash attributes we know about.
CHASH_ALGS = {}
for key in HASH_ALGS:
    CHASH_ALGS[key.replace("hash", "chash")] = HASH_ALGS[key]

# A dictionary of signature action chain hash attributes we know about.
CHAIN_ALGS = {}
for key in HASH_ALGS:
    CHAIN_ALGS[key.replace("hash", "chain")] = HASH_ALGS[key]

# A dictionary of signature action chain chash attributes we know about.
CHAIN_CHASH_ALGS = {}
for key in HASH_ALGS:
    CHAIN_CHASH_ALGS[key.replace("hash", "chain.chashes")] = HASH_ALGS[key]

ALL_HASH_ATTRS = (DEFAULT_HASH_ATTRS + DEFAULT_CHASH_ATTRS +
    DEFAULT_GELF_HASH_ATTRS)

def is_hash_attr(attr_name):
    """Tells whether or not the named attribute contains a hash value."""

    return attr_name in ALL_HASH_ATTRS

def _get_hash_dics(hash_type):
    """Based on the 'hash_type', return a tuple describing the ranking of
    hash attributes from "most preferred" to "least preferred" and a mapping
    of those attributes to the hash algorithms that are used to
    compute those attributes.

    If 'reverse' is true, return the rank_tuple in reverse order, from least
    preferred hash to most preferred hash.
    """

    if hash_type == HASH:
        hash_attrs = DEFAULT_HASH_ATTRS
        hash_dic = HASH_ALGS
    elif hash_type == CHASH:
        hash_attrs = DEFAULT_CHASH_ATTRS
        hash_dic = CHASH_ALGS
    elif hash_type == HASH_GELF:
        hash_attrs = DEFAULT_GELF_HASH_ATTRS
        hash_dic = GELF_HASH_ALGS
    elif hash_type == CHAIN:
        hash_attrs = DEFAULT_CHAIN_ATTRS
        hash_dic = CHAIN_ALGS
    elif hash_type == CHAIN_CHASH:
        hash_attrs = DEFAULT_CHAIN_CHASH_ATTRS
        hash_dic = CHAIN_CHASH_ALGS
    else:
        hash_attrs = None
        hash_dic = None

    return hash_attrs, hash_dic


class ContentHash(dict):
    """This class breaks out the stringified tuples from
    pkg.content-hash

    "extract_method:hash_alg:hash_val"

    into a dict with entries

        "extract_method:hash_alg": "hash_val"
    """
    def __init__(self, vals):
        dict.__init__(self)

        if isinstance(vals, str):
            vals = (vals,)

        for v in vals:
            vs = v.rsplit(":", 1)
            self[vs[0]] = vs[1]


def get_preferred_hash(action, hash_type=HASH, reversed=False):
    """Returns a tuple of the form (hash_attr, hash_val, hash_func)
    where 'hash_attr' is the preferred hash attribute name, 'hash_val'
    is the preferred hash value, and 'hash_func' is the function
    used to compute the preferred hash based on the available
    pkg.content-hash or pkg.*hash.* attributes declared in the action."""

    hash_attrs, hash_dic = _get_hash_dics(hash_type)
    if not (hash_attrs and hash_dic):
        raise ValueError("Unknown hash_type {0} passed to "
            "get_preferred_hash".format(hash_type))

    if hash_type == HASH_GELF:
        extract_method = EXTRACT_GELF
    elif hash_type == CHASH:
        extract_method = EXTRACT_GZIP
    else:
        extract_method = EXTRACT_FILE
    if reversed:
        ranked_hashes = REVERSE_RANKED_HASHES
    else:
        ranked_hashes = RANKED_HASHES

    for alg in ranked_hashes:
        if alg == "sha1":
            # The corresponding hash attr should be in the
            # first position if "sha1" is enabled.
            attr = hash_attrs[0]
            if not action:
                return attr, None, hash_dic[attr]
            if hash_type == HASH:
                if action.hash:
                    return attr, action.hash, hash_dic[attr]
            else:
                if attr in action.attrs:
                    return (attr, action.attrs[attr],
                        hash_dic[attr])
        elif hash_type in (HASH, HASH_GELF, CHASH):
            # Currently only HASH, HASH_GELF and CHASH support
            # pkg.content-hash.
            ch_type = "{0}:{1}".format(extract_method, alg)
            attr = "pkg.content-hash"
            if not action:
                return attr, None, hash_dic[ch_type]
            if attr in action.attrs:
                ch = ContentHash(action.attrs[attr])
                if ch_type in ch:
                    return (attr, ch[ch_type],
                        hash_dic[ch_type])
        elif hash_type in (CHAIN, CHAIN_CHASH):
            # The corresponding hash attr should be in the
            # last position if sha2 or higher algorithm is enabled.
            attr = hash_attrs[-1]
            if attr in action.attrs:
                return attr, action.attrs[attr], hash_dic[attr]

    # fallback to the default hash member since it's not in action.attrs
    if hash_type == HASH:
        return None, action.hash, hashlib.sha1
    # an action can legitimately have no chash
    if hash_type == CHASH:
        return None, None, hashlib.sha1
    # an action can legitimately have no GELF content-hash if it's not a
    # file type we know about
    if hash_type == HASH_GELF:
        return None, None, None
    # an action can legitimately have no chain
    if hash_type == CHAIN:
        return None, None, None
    # an action can legitimately have no chain_chash
    if hash_type == CHAIN_CHASH:
        return None, None, None

    # This should never happen.
    if reversed:
        raise Exception("Error determining the least preferred hash "
            "for {0} {1}".format(action, hash_type))
    else:
        raise Exception("Error determining the preferred hash for "
            "{0} {1}".format(action, hash_type))


def get_least_preferred_hash(action, hash_type=HASH):
    """Returns a tuple of the least preferred hash attribute name, the hash
    value that should result when we compute the hash, and the function used
    to compute the hash based on the available hash and pkg.*hash.*
    attributes declared in the action."""

    return get_preferred_hash(action, hash_type=hash_type, reversed=True)


def get_common_preferred_hash(action, old_action, hash_type=HASH,
    cmp_policy=None):
    """Returns the most preferred hash attribute of those present
    on a new action and/or an installed (old) version of that
    action. We return the name of the hash attribute, the new and
    original values of that attribute, and the function used
    to compute the hash.

    The pkg.content-hash attribute may be multi-valued. When
    selecting this attribute, a secondary selection will be made
    based on a ranked list of value prefixes. The most preferred
    value will then be returned.

    Normally, payload comparisons should only be made based on
    hashes that include signatures in the extracted data. This
    constraint can be relaxed by setting cmp_policy=CMP_UNSIGNED. In
    this case, the most preferred hash will be selected first, and
    then we'll check for unsigned versions of that hash on both
    actions. When both actions have that unsigned hash, its values
    will be returned in place of the signed values.

    If no common attribute is found, we fallback to the legacy
    <Action>.hash member assuming it is not None for the new and
    orig actions, and specify hashlib.sha1 as the algorithm. If no
    'hash' member is set, we return a tuple of None objects.

    """

    if not old_action:
        return None, None, None, None

    hash_attrs, hash_dic = _get_hash_dics(hash_type)
    if hash_type == HASH_GELF:
        extract_method = EXTRACT_GELF
    elif hash_type == CHASH:
        extract_method = EXTRACT_GZIP
    else:
        extract_method = EXTRACT_FILE

    if not (hash_attrs and hash_dic):
        raise ValueError("Unknown hash_type {0} passed to "
            "get_preferred_common_hash".format(hash_type))

    new_hashes = frozenset(a for a in action.attrs if a in hash_attrs)
    old_hashes = frozenset(a for a in old_action.attrs if a in hash_attrs)

    all_hashes = new_hashes | old_hashes

    for alg in RANKED_HASHES:
        if alg == "sha1":
            attr = hash_attrs[0]
            # The corresponding hash attr should be in the
            # first position if "sha1" is enabled.
            if attr not in all_hashes:
                continue
            new_hash = action.attrs.get(attr)
            old_hash = old_action.attrs.get(attr)
            return attr, new_hash, old_hash, hash_dic[attr]
        elif hash_type in (HASH, HASH_GELF, CHASH):
            # Currently only HASH, HASH_GELF and CHASH support
            # pkg.content-hash.
            attr = "pkg.content-hash"
            if attr not in all_hashes:
                continue
            nh = ContentHash(
                    action.attrs.get(attr, {}))
            oh = ContentHash(
                    old_action.attrs.get(attr, {}))
            new_types = frozenset(nh)
            old_types = frozenset(oh)
            all_types = new_types | old_types

            ch_type = "{0}:{1}".format(extract_method, alg)
            if ch_type not in all_types:
                continue

            new_hash = nh.get(ch_type)
            old_hash = oh.get(ch_type)

            # Here we've matched a ranked hash type in at
            # least one of the pkg.content-hash value
            # sets, so we know we'll be returning. If
            # we're allowing comparison on unsigned hash
            # values, and both value sets have this hash
            # type, and both value sets have a
            # corresponding unsigned hash, swap in those
            # unsigned hash values.
            from pkg.misc import CMP_UNSIGNED
            if (cmp_policy == CMP_UNSIGNED and new_hash and
                old_hash and ch_type in UNSIGNED_GELF_HASH_MAP):
                ut = UNSIGNED_GELF_HASH_MAP[ch_type]
                if ut in nh and ut in oh:
                    new_hash = nh[ut]
                    old_hash = oh[ut]

            return attr, new_hash, old_hash, hash_dic.get(ch_type)
        elif hash_type in (CHAIN, CHAIN_CHASH):
            # The corresponding hash attr should be in the
            # last position if sha2 or higher algorithm is enabled.
            attr = hash_attrs[-1]
            if attr not in all_hashes:
                continue
            new_hash = action.attrs.get(attr)
            old_hash = old_action.attrs.get(attr)
            return attr, new_hash, old_hash, hash_dic[attr]

    if action.hash and old_action.hash:
        return None, action.hash, old_action.hash, hashlib.sha1
    return None, None, None, None
