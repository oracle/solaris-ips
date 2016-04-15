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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
from collections import namedtuple, defaultdict
from functools import reduce

import errno
import fnmatch
import hashlib
import os
import re
import six
import tempfile
from itertools import groupby, chain, product, repeat
from operator import itemgetter
from six.moves import zip

import pkg.actions as actions
import pkg.client.api_errors as apx
import pkg.facet as facet
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.portable as portable
import pkg.variant as variant
import pkg.version as version

from pkg.misc import EmptyDict, EmptyI, expanddirs, PKG_FILE_MODE, PKG_DIR_MODE
from pkg.actions.attribute import AttributeAction
from pkg.actions.directory import DirectoryAction

def _compile_fnpats(fn_pats):
        """Private helper function that returns a compiled version of a
        dictionary of fnmatch patterns."""

        return dict(
            (key, [
                re.compile(fnmatch.translate(pat), re.IGNORECASE).match
                for pat in pats
            ])
            for (key, pats) in six.iteritems(fn_pats)
        )


def _attr_matches(action, attr_match):
        """Private helper function: given an action, return True if any of its
        attributes' values matches the pattern for the same attribute in the
        attr_match dictionary, and False otherwise. Note that the patterns must
        be pre-comiled using re.compile() or _compile_fnpats."""

        if not attr_match:
                return True

        for (attr, matches) in six.iteritems(attr_match):
                if attr in action.attrs:
                        for match in matches:
                                for attrval in action.attrlist(attr):
                                        if match(attrval):
                                                return True
        return False


class ManifestDifference(
    namedtuple("ManifestDifference", "added changed removed")):

        __slots__ = []

        __state__desc = tuple([
            [ ( actions.generic.NSG, actions.generic.NSG ) ],
            [ ( actions.generic.NSG, actions.generic.NSG ) ],
            [ ( actions.generic.NSG, actions.generic.NSG ) ],
        ])

        __state__commonize = frozenset([
            actions.generic.NSG,
        ])

        @staticmethod
        def getstate(obj, je_state=None):
                """Returns the serialized state of this object in a format
                that that can be easily stored using JSON, pickle, etc."""
                return misc.json_encode(ManifestDifference.__name__,
                    tuple(obj),
                    ManifestDifference.__state__desc,
                    commonize=ManifestDifference.__state__commonize,
                    je_state=je_state)

        @staticmethod
        def fromstate(state, jd_state=None):
                """Allocate a new object using previously serialized state
                obtained via getstate()."""

                # decode serialized state into python objects
                state = misc.json_decode(ManifestDifference.__name__,
                    state,
                    ManifestDifference.__state__desc,
                    commonize=ManifestDifference.__state__commonize,
                    jd_state=jd_state)

                return ManifestDifference(*state)

class Manifest(object):
        """A Manifest is the representation of the actions composing a specific
        package version on both the client and the repository.  Both purposes
        utilize the same storage format.

        The serialized structure of a manifest is an unordered list of actions.

        The special action, "set", represents a package attribute.

        The reserved attribute, "fmri", represents the package and version
        described by this manifest.  It is available as a string via the
        attributes dictionary, and as an FMRI object from the fmri member.

        The list of manifest-wide reserved attributes is

        base_directory          Default base directory, for non-user images.
        fmri                    Package FMRI.
        isa                     Package is intended for a list of ISAs.
        platform                Package is intended for a list of platforms.
        relocatable             Suitable for User Image.

        All non-prefixed attributes are reserved to the framework.  Third
        parties may prefix their attributes with a reversed domain name, domain
        name, or stock symbol.  An example might be

        com.example,supported

        as an indicator that a specific package version is supported by the
        vendor, example.com.

        manifest.null is provided as the null manifest.  Differences against the
        null manifest result in the complete set of attributes and actions of
        the non-null manifest, meaning that all operations can be viewed as
        tranitions between the manifest being installed and the manifest already
        present in the image (which may be the null manifest).
        """

        def __init__(self, pfmri=None):
                self.fmri = pfmri

                self._cache = {}
                self._absent_cache = []
                self.actions = []
                self.actions_bytype = {}
                self.attributes = {} # package-wide attributes
                self.signatures = EmptyDict
                self.excludes = EmptyI
                if pfmri is not None:
                        if not isinstance(pfmri, fmri.PkgFmri):
                                pfmri = fmri.PkgFmri(pfmri)
                        self.publisher = pfmri.publisher
                else:
                        self.publisher = None

        def __str__(self):
                r = ""
                if "pkg.fmri" not in self.attributes and self.fmri != None:
                        r += "set name=pkg.fmri value={0}\n".format(self.fmri)

                for act in sorted(self.actions):
                        r += "{0}\n".format(act)
                return r

        def as_lines(self):
                """A generator function that returns the unsorted manifest
                contents as lines of text."""

                if "pkg.fmri" not in self.attributes and self.fmri != None:
                        yield "set name=pkg.fmri value={0}\n".format(self.fmri)

                for act in self.actions:
                        yield "{0}\n".format(act)

        def tostr_unsorted(self):
                return "".join((l for l in self.as_lines()))

        def difference(self, origin, origin_exclude=EmptyI,
            self_exclude=EmptyI):
                """Return three lists of action pairs representing origin and
                destination actions.  The first list contains the pairs
                representing additions, the second list contains the pairs
                representing updates, and the third list contains the pairs
                representing removals.  All three lists are in the order in
                which they should be executed."""
                # XXX Do we need to find some way to assert that the keys are
                # all unique?

                if isinstance(origin, EmptyFactoredManifest):
                        # No origin was provided, so nothing has been changed or
                        # removed; only added.  In addition, this doesn't need
                        # to be sorted since the caller likely already does
                        # (such as pkgplan/imageplan).
                        return ManifestDifference(
                            [(None, a) for a in self.gen_actions(
                            excludes=self_exclude)], [], [])

                def hashify(v):
                        """handle key values that may be lists"""
                        if type(v) is not list:
                                return v
                        return tuple(v)

                def dictify(mf, excludes):
                        # Transform list of actions into a dictionary keyed by
                        # action key attribute, key attribute and mediator, or
                        # id if there is no key attribute.
                        for a in mf.gen_actions(excludes=excludes):
                                if (a.name == "link" or
                                    a.name == "hardlink") and \
                                    a.attrs.get("mediator"):
                                        akey = (a.name, tuple([
                                            a.attrs[a.key_attr],
                                            a.attrs.get("mediator-version"),
                                            a.attrs.get("mediator-implementation")
                                        ]))
                                else:
                                        akey = (a.name, hashify(a.attrs.get(
                                            a.key_attr, id(a))))
                                yield (akey, a)

                sdict = dict(dictify(self, self_exclude))
                odict = dict(dictify(origin, origin_exclude))

                sset = set(six.iterkeys(sdict))
                oset = set(six.iterkeys(odict))

                added = [(None, sdict[i]) for i in sset - oset]
                removed = [(odict[i], None) for i in oset - sset]
                changed = [
                    (odict[i], sdict[i])
                    for i in oset & sset
                    if odict[i].different(sdict[i])
                ]

                # XXX Do changed actions need to be sorted at all?  This is
                # likely to be the largest list, so we might save significant
                # time by not sorting.  Should we sort above?  Insert into a
                # sorted list?

                # singlesort = lambda x: x[0] or x[1]
                addsort = itemgetter(1)
                remsort = itemgetter(0)
                removed.sort(key=remsort, reverse=True)
                added.sort(key=addsort)
                changed.sort(key=addsort)

                return ManifestDifference(added, changed, removed)

        @staticmethod
        def comm(compare_m):
                """Like the unix utility comm, except that this function
                takes an arbitrary number of manifests and compares them,
                returning a tuple consisting of each manifest's actions
                that are not the same for all manifests, followed by a
                list of actions that are the same in each manifest."""

                # Must specify at least one manifest.
                assert compare_m
                dups = []

                # construct list of dictionaries of actions in each
                # manifest, indexed by unique key and variant combination
                m_dicts = []
                for m in compare_m:
                        m_dict = {}
                        for a in m.gen_actions():
                                # The unique key for each action is based on its
                                # type, key attribute, and unique variants set
                                # on the action.
                                try:
                                        key = set(a.attrlist(a.key_attr))
                                        if (a.name == "link" or
                                           a.name == "hardlink") and \
                                           a.attrs.get("mediator"):
                                                for v in ("mediator-version",
                                                    "mediator-implementation"):
                                                        key.update([
                                                            "{0}={1}".format(v,
                                                            a.attrs.get(v))])
                                        key.update(
                                            "{0}={1}".format(v, a.attrs[v])
                                            for v in a.get_varcet_keys()[0]
                                        )

                                        key = tuple(key)
                                except KeyError:
                                        # If there is no key attribute for the
                                        # action, then fallback to the object
                                        # id for the action as its identifier.
                                        key = (id(a),)

                                # catch duplicate actions here...
                                if m_dict.setdefault((a.name, key), a) != a:
                                        dups.append((m_dict[(a.name, key)], a))

                        m_dicts.append(m_dict)

                if dups:
                        raise ManifestError(duplicates=dups)

                # construct list of key sets in each dict
                m_sets = [
                    set(m.keys())
                    for m in m_dicts
                ]

                common_keys = reduce(lambda a, b: a & b, m_sets)

                # determine which common_keys have common actions
                for k in common_keys.copy():
                        for i in range(len(m_dicts) - 1):
                                if m_dicts[i][k].different(
                                    m_dicts[i + 1][k]):
                                        common_keys.remove(k)
                                        break
                return tuple(
                    [
                        [m_dicts[i][k] for k in m_sets[i] - common_keys]
                        for i in range(len(m_dicts))
                    ]
                    +
                    [
                        [ m_dicts[0][k] for k in common_keys ]
                    ]
                )

        def combined_difference(self, origin, ov=EmptyI, sv=EmptyI):
                """Where difference() returns three lists, combined_difference()
                returns a single list of the concatenation of the three."""
                return list(chain(*self.difference(origin, ov, sv)))

        def humanized_differences(self, other, ov=EmptyI, sv=EmptyI):
                """Output expects that self is newer than other.  Use of sets
                requires that we convert the action objects into some marshalled
                form, otherwise set member identities are derived from the
                object pointers, rather than the contents."""

                l = self.difference(other, ov, sv)
                out = ""

                for src, dest in chain(*l):
                        if not src:
                                out += "+ {0}\n".format(str(dest))
                        elif not dest:
                                out += "- {0}\n" + str(src)
                        else:
                                out += "{0} -> {1}\n".format(src, dest)
                return out

        def _gen_dirs_to_str(self):
                """Generate contents of dircache file containing all dirctories
                referenced explicitly or implicitly from self.actions.  Include
                variants as values; collapse variants where possible."""

                def gen_references(a):
                        for d in expanddirs(a.directory_references()):
                                yield d

                dirs = self._actions_to_dict(gen_references)
                for d in dirs:
                        for v in dirs[d]:
                                a = DirectoryAction(path=d, **v)
                                yield str(a) + "\n"

        def _gen_mediators_to_str(self):
                """Generate contents of mediatorcache file containing all
                mediators referenced explicitly or implicitly from self.actions.
                Include variants as values; collapse variants where possible."""

                def gen_references(a):
                        if (a.name == "link" or a.name == "hardlink") and \
                            "mediator" in a.attrs:
                                yield (a.attrs.get("mediator"),
                                   a.attrs.get("mediator-priority"),
                                   a.attrs.get("mediator-version"),
                                   a.attrs.get("mediator-implementation"))

                mediators = self._actions_to_dict(gen_references)
                for mediation, mvariants in six.iteritems(mediators):
                        values = {
                            "mediator-priority": mediation[1],
                            "mediator-version": mediation[2],
                            "mediator-implementation": mediation[3],
                        }
                        for mvariant in mvariants:
                                a = "set name=pkg.mediator " \
                                    "value={0} {1} {2}\n".format(mediation[0],
                                     " ".join((
                                         "=".join(t)
                                          for t in six.iteritems(values)
                                          if t[1]
                                     )),
                                     " ".join((
                                         "=".join(t)
                                         for t in six.iteritems(mvariant)
                                     ))
                                )
                                yield a

        def _gen_attrs_to_str(self):
                """Generate set action supplemental data containing all facets
                and variants from self.actions and size information.  Each
                returned line must be newline-terminated."""

                emit_variants = "pkg.variant" not in self
                emit_facets = "pkg.facet" not in self
                emit_sizes = "pkg.size" not in self and "pkg.csize" not in self

                if not any((emit_variants, emit_facets, emit_sizes)):
                        # Package already has these attributes.
                        return

                # List of possible variants and possible values for them.
                variants = defaultdict(set)

                # Seed with declared set of variants as actions may be common to
                # both and so will not be tagged with variant.
                for name in self.attributes:
                        if name[:8] == "variant.":
                                variants[name] = set(self.attributes[name])

                # List of possible facets and under what variant combinations
                # they were seen.
                facets = defaultdict(set)

                # Unique (facet, value) (variant, value) combinations.
                refs = defaultdict(lambda: defaultdict(int))

                for a in self.gen_actions():
                        name = a.name
                        attrs = a.attrs
                        if name == "set":
                                if attrs["name"][:12] == "pkg.variant":
                                        emit_variants = False
                                elif attrs["name"][:9] == "pkg.facet":
                                        emit_facets = False

                        afacets = []
                        avariants = []
                        for attr, val in six.iteritems(attrs):
                                if attr[:8] == "variant.":
                                        variants[attr].add(val)
                                        avariants.append((attr, val))
                                elif attr[:6] == "facet.":
                                        afacets.append((attr, val))

                        for name, val in afacets:
                                # Facet applicable to this particular variant
                                # combination.
                                varkey = tuple(sorted(avariants))
                                facets[varkey].add(name)

                        # This *must* be sorted to ensure reproducible set
                        # action generation for sizes and to ensure each
                        # combination is actually unique.
                        varcetkeys = tuple(sorted(chain(afacets, avariants)))
                        refs[varcetkeys]["csize"] += misc.get_pkg_otw_size(a)
                        if name == "signature":
                                refs[varcetkeys]["csize"] += \
                                    a.get_action_chain_csize()
                        refs[varcetkeys]["size"] += a.get_size()

                # Prevent scope leak.
                afacets = avariants = attrs = varcetkeys = None

                if emit_variants:
                        # Unnecessary if we can guarantee all variants will be
                        # declared at package level.  Omit the "variant." prefix
                        # from attribute values since that's implicit and can be
                        # added back when the action is parsed.
                        yield "{0}\n".format(AttributeAction(None,
                            name="pkg.variant",
                            value=sorted(v[8:] for v in variants)))

                # Emit a set action for every variant used with possible values
                # if one does not already exist.
                for name in variants:
                        # merge_facets needs the variant values sorted and this
                        # is desirable when generating the variant attr anyway.
                        variants[name] = sorted(variants[name])
                        if name not in self.attributes:
                                yield "{0}\n".format(AttributeAction(None,
                                    name=name, value=variants[name]))

                if emit_facets:
                        # Get unvarianted facet set.
                        cfacets = facets.pop((), set())

                        # For each variant combination, remove unvarianted
                        # facets since they are common to all variants.
                        for varkey, fnames in list(facets.items()):
                                fnames.difference_update(cfacets)
                                if not fnames:
                                        # No facets unique to this combo;
                                        # discard.
                                        del facets[varkey]

                        # If all possible variant combinations supported by the
                        # package have at least one facet, then the intersection
                        # of facets for all variants can be merged with the
                        # common set.
                        merge_facets = len(facets) > 0
                        if merge_facets:
                                # Determine unique set of variant combinations
                                # seen for faceted actions.
                                vcombos = set((
                                    tuple(
                                        vpair[0]
                                        for vpair in varkey
                                    )
                                    for varkey in facets
                                ))

                                # For each unique variant combination, determine
                                # if the cartesian product of all variant values
                                # supported by the package for the combination
                                # has been seen.  In other words, if the
                                # combination is ((variant.arch,)) and the
                                # package supports (i386, sparc), then both
                                # (variant.arch, i386) and (variant.arch, sparc)
                                # must exist.  This code assumes variant values
                                # for each variant are already sorted.
                                for pair in chain.from_iterable(
                                    product(*(
                                        tuple((name, val)
                                            for val in variants[name])
                                        for name in vcombo)
                                    )
                                    for vcombo in vcombos
                                ):
                                        if pair not in facets:
                                                # If any combination the package
                                                # supports has not been seen for
                                                # one or more facets, then some
                                                # facets are unique to one or
                                                # more combinations.
                                                merge_facets = False
                                                break

                        if merge_facets:
                                # Merge the facets common to all variants if safe;
                                # if we always merged them, then facets only
                                # used by a single variant (think i386-only or
                                # sparc-only content) would be seen unvarianted
                                # (that's bad).
                                vfacets = list(facets.values())
                                vcfacets = vfacets[0].intersection(*vfacets[1:])

                                if vcfacets:
                                        # At least one facet is shared between
                                        # all variant combinations; move the
                                        # common ones to the unvarianted set.
                                        cfacets.update(vcfacets)

                                        # Remove facets common to all combos.
                                        for varkey, fnames in list(
                                            facets.items()):
                                                fnames.difference_update(vcfacets)
                                                if not fnames:
                                                        # No facets unique to
                                                        # this combo; discard.
                                                        del facets[varkey]

                        # Omit the "facet." prefix from attribute values since
                        # that's implicit and can be added back when the action
                        # is parsed.
                        val = sorted(f[6:] for f in cfacets)
                        if not val:
                                # If we don't do this, action stringify will
                                # emit this as "set name=pkg.facet" which is
                                # then transformed to "set name=name
                                # value=pkg.facet".  Not what we wanted, but is
                                # expected for historical reasons.
                                val = ""

                        # Always emit an action enumerating the list of facets
                        # common to all variants, even if there aren't any.
                        # That way if there are also no variant-specific facets,
                        # package operations will know that no facets are used
                        # by the package instead of having to scan the whole
                        # manifest.
                        yield "{0}\n".format(AttributeAction(None,
                            name="pkg.facet.common", value=val))

                        # Now emit a pkg.facet action for each variant
                        # combination containing the list of facets unique to
                        # that combination.
                        for varkey, fnames in six.iteritems(facets):
                                # A unique key for each combination is needed,
                                # and using a hash obfuscates that interface
                                # while giving us a reliable way to generate
                                # a reproducible, unique identifier.  The key
                                # string below looks like this before hashing:
                                #     variant.archi386variant.debug.osnetTrue...
                                key = hashlib.sha1(
                                    misc.force_bytes("".join(
                                    "{0}{1}".format(*v) for v in varkey))
                                ).hexdigest()

                                # Omit the "facet." prefix from attribute values
                                # since that's implicit and can be added back
                                # when the action is parsed.
                                act = AttributeAction(None,
                                    name="pkg.facet.{0}".format(key),
                                    value=sorted(f[6:] for f in fnames))
                                attrs = act.attrs
                                # Tag action with variants.
                                for v in varkey:
                                        attrs[v[0]] = v[1]
                                yield "{0}\n".format(act)

                # Emit pkg.[c]size attribute for [compressed] size of package
                # for each facet/variant combination.
                csize = 0
                size = 0
                for varcetkeys in refs:
                        rcsize = refs[varcetkeys]["csize"]
                        rsize = refs[varcetkeys]["size"]

                        if not varcetkeys:
                                # For unfaceted/unvarianted actions, keep a
                                # running total so a single [c]size action can
                                # be generated.
                                csize += rcsize
                                size += rsize
                                continue

                        if emit_sizes and (rcsize > 0 or rsize > 0):
                                # Only emit if > 0; actions may be
                                # faceted/variant without payload.

                                # A unique key for each combination is needed,
                                # and using a hash obfuscates that interface
                                # while giving us a reliable way to generate
                                # a reproducible, unique identifier.  The key
                                # string below looks like this before hashing:
                                #     facet.docTruevariant.archi386...
                                key = hashlib.sha1(misc.force_bytes(
                                    "".join("{0}{1}".format(*v) for v in varcetkeys)
                                )).hexdigest()

                                # The sizes are abbreviated in the name of byte
                                # conservation.
                                act = AttributeAction(None,
                                    name="pkg.sizes.{0}".format(key),
                                    value=["csz={0}".format(rcsize),
                                    "sz={0}".format(rsize)])
                                attrs = act.attrs
                                for v in varcetkeys:
                                        attrs[v[0]] = v[1]
                                yield "{0}\n".format(act)

                if emit_sizes:
                        act = AttributeAction(None, name="pkg.sizes.common",
                            value=["csz={0}".format(csize),
                            "sz={0}".format(size)])
                        yield "{0}\n".format(act)

        def _actions_to_dict(self, references):
                """create dictionary of all actions referenced explicitly or
                implicitly from self.actions... include variants as values;
                collapse variants where possible"""

                refs = {}
                # build a dictionary containing all actions tagged w/
                # variants
                for a in self.actions:
                        v, f = a.get_varcet_keys()
                        variants = dict((name, a.attrs[name]) for name in v + f)
                        for ref in references(a):
                                if ref not in refs:
                                        refs[ref] = [variants]
                                elif variants not in refs[ref]:
                                        refs[ref].append(variants)

                # remove any tags if any entries are always delivered (NULL)
                for ref in refs:
                        if {} in refs[ref]:
                                refs[ref] = [{}]
                                continue
                        # could collapse refs where all variants are present
                        # (the current logic only collapses them if at least
                        # one reference is delivered without a facet or
                        # variant)
                return refs

        def get_directories(self, excludes):
                """ return a list of directories implicitly or
                explicitly referenced by this object"""

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI
                try:
                        alist = self._cache["manifest.dircache"]
                except KeyError:
                        # generate actions that contain directories
                        alist = self._cache["manifest.dircache"] = [
                            actions.fromstr(s.rstrip())
                            for s in self._gen_dirs_to_str()
                        ]

                s = set([
                    a.attrs["path"]
                    for a in alist
                    if not excludes or a.include_this(excludes,
                        publisher=self.publisher)
                ])

                return list(s)

        def gen_facets(self, excludes=EmptyI, patterns=EmptyI):
                """A generator function that returns the supported facet
                attributes (strings) for this package based on the specified (or
                current) excludes that also match at least one of the patterns
                provided.  Facets must be true or false so a list of possible
                facet values is not returned."""

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI

                try:
                        facets = self["pkg.facet"]
                except KeyError:
                        facets = None

                if facets is not None and excludes == EmptyI:
                        # No excludes? Then use the pre-determined set of
                        # facets.
                        for f in misc.yield_matching("facet.", facets, patterns):
                                yield f
                        return

                # If different excludes were specified, then look for pkg.facet
                # actions containing the list of facets.
                found = False
                seen = set()
                for a in self.gen_actions_by_type("set", excludes=excludes):
                        if a.attrs["name"][:10] == "pkg.facet.":
                                # Either a pkg.facet.common action or a
                                # pkg.facet.X variant-specific action.
                                found = True
                                val = a.attrlist("value")
                                if len(val) == 1 and val[0] == "":
                                        # No facets.
                                        continue

                                for f in misc.yield_matching("facet.", (
                                    "facet.{0}".format(n)
                                    for n in val
                                ), patterns):
                                        if f in seen:
                                                # Prevent duplicates; it's
                                                # possible a given facet may be
                                                # valid for more than one unique
                                                # variant combination that's
                                                # allowed by current excludes.
                                                continue

                                        seen.add(f)
                                        yield f

                if not found:
                        # Fallback to sifting actions to yield possible.
                        facets = self._get_varcets(excludes=excludes)[1]
                        for f in misc.yield_matching("facet.", facets, patterns):
                                yield f

        def gen_variants(self, excludes=EmptyI, patterns=EmptyI):
                """A generator function that yields a list of tuples of the form
                (variant, [values]).  Where 'variant' is the variant attribute
                name (e.g. 'variant.arch') and '[values]' is a list of the
                variant values supported by this package.  Variants returned are
                those allowed by the specified (or current) excludes that also
                match at least one of the patterns provided."""

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI

                try:
                        variants = self["pkg.variant"]
                except KeyError:
                        variants = None

                if variants is not None and excludes == EmptyI:
                        # No excludes? Then use the pre-determined set of
                        # variants.
                        for v in misc.yield_matching("variant.", variants,
                            patterns):
                                yield v, self.attributes.get(v, [])
                        return

                # If different excludes were specified, then look for
                # pkg.variant action containing the list of variants.
                found = False
                variants = defaultdict(set)
                for a in self.gen_actions_by_type("set", excludes=excludes):
                        aname = a.attrs["name"]
                        if aname == "pkg.variant":
                                val = a.attrlist("value")
                                if len(val) == 1 and val[0] == "":
                                        # No variants.
                                        return
                                for v in val:
                                        found = True
                                        # Ensure variant entries exist (debug
                                        # variants may not) via defaultdict.
                                        variants["variant.{0}".format(v)]
                        elif aname[:8] == "variant.":
                                for v in a.attrlist("value"):
                                        found = True
                                        variants[aname].add(v)

                if not found:
                        # Fallback to sifting actions to get possible.
                        variants = self._get_varcets(excludes=excludes)[0]

                for v in misc.yield_matching("variant.", variants, patterns):
                        yield v, variants[v]

        def gen_mediators(self, excludes=EmptyI):
                """A generator function that yields tuples of the form (mediator,
                mediations) expressing the set of possible mediations for this
                package, where 'mediations' is a set() of possible mediations for
                the mediator.  Each mediation is a tuple of the form (priority,
                version, implementation).
                """

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI
                try:
                        alist = self._cache["manifest.mediatorcache"]
                except KeyError:
                        # generate actions that contain mediators
                        alist = self._cache["manifest.mediatorcache"] = [
                            actions.fromstr(s.rstrip())
                            for s in self._gen_mediators_to_str()
                        ]

                ret = defaultdict(set)
                for attrs in (
                    act.attrs
                    for act in alist
                    if not excludes or act.include_this(excludes)):
                        med_ver = attrs.get("mediator-version")
                        if med_ver:
                                try:
                                        med_ver = version.Version(med_ver)
                                except version.VersionError:
                                        # Consider this mediation unavailable
                                        # if it can't be parsed for whatever
                                        # reason.
                                        continue

                        ret[attrs["value"]].add((
                            attrs.get("mediator-priority"),
                            med_ver,
                            attrs.get("mediator-implementation"),
                        ))

                for m in ret:
                        yield m, ret[m]

        def gen_actions(self, attr_match=None, excludes=EmptyI):
                """Generate actions in manifest through ordered callable list"""

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI

                if attr_match:
                        attr_match = _compile_fnpats(attr_match)

                pub = self.publisher
                for a in self.actions:
                        for c in excludes:
                                if not c(a, publisher=pub):
                                        break
                        else:
                                # These conditions are split by performance.
                                if not attr_match:
                                        yield a
                                elif _attr_matches(a, attr_match):
                                        yield a

        def gen_actions_by_type(self, atype, attr_match=None, excludes=EmptyI):
                """Generate actions in the manifest of type "type"
                through ordered callable list"""

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI

                if attr_match:
                        attr_match = _compile_fnpats(attr_match)

                pub = self.publisher
                for a in self.actions_bytype.get(atype, []):
                        for c in excludes:
                                if not c(a, publisher=pub):
                                        break
                        else:
                                # These conditions are split by performance.
                                if not attr_match:
                                        yield a
                                elif _attr_matches(a, attr_match):
                                        yield a

        def gen_actions_by_types(self, atypes, attr_match=None, excludes=EmptyI):
                """Generate actions in the manifest of types "atypes"
                through ordered callable list."""

                for atype in atypes:
                        for a in self.gen_actions_by_type(atype,
                            attr_match=attr_match, excludes=excludes):
                                yield a

        def gen_key_attribute_value_by_type(self, atype, excludes=EmptyI):
                """Generate the value of the key attribute for each action
                of type "type" in the manifest."""

                return (
                    a.attrs.get(a.key_attr)
                    for a in self.gen_actions_by_type(atype, excludes=excludes)
                )

        def duplicates(self, excludes=EmptyI):
                """Find actions in the manifest which are duplicates (i.e.,
                represent the same object) but which are not identical (i.e.,
                have all the same attributes)."""

                def fun(a):
                        """Return a key on which actions can be sorted."""
                        return a.name, a.attrs.get(a.key_attr, id(a))

                alldups = []
                acts = [a for a in self.gen_actions(excludes=excludes)]

                for k, g in groupby(sorted(acts, key=fun), fun):
                        glist = list(g)
                        dups = set()
                        for i in range(len(glist) - 1):
                                if glist[i].different(glist[i + 1]):
                                        dups.add(glist[i])
                                        dups.add(glist[i + 1])
                        if dups:
                                alldups.append((k, dups))
                return alldups

        def __content_to_actions(self, content):
                """Parse manifest content, stripping line-continuation
                characters from the input as it is read; this results in actions
                with values across multiple lines being passed to the
                action parsing code whitespace-separated instead.
                
                For example:
                        
                set name=pkg.summary \
                    value="foo"
                set name=pkg.description value="foo " \
                      "bar baz"

                ...will each be passed to action parsing as:

                set name=pkg.summary value="foo"
                set name=pkg.description value="foo " "bar baz"
                """

                accumulate = ""
                lineno = 0
                errors = []

                if isinstance(content, six.string_types):
                        # Get an iterable for the string.
                        content = content.splitlines()

                for l in content:
                        lineno += 1
                        l = l.lstrip()
                        if l.endswith("\\"):          # allow continuation chars
                                accumulate += l[0:-1] # elide backslash
                                continue
                        elif accumulate:
                                l = accumulate + l
                                accumulate = ""

                        if not l or l[0] == "#": # ignore blank lines & comments
                                continue

                        try:
                                yield actions.fromstr(l)
                        except actions.ActionError as e:
                                # Accumulate errors and continue so that as
                                # much of the action data as possible can be
                                # parsed.
                                e.fmri = self.fmri
                                e.lineno = lineno
                                errors.append(e)

                if errors:
                        raise apx.InvalidPackageErrors(errors)

        def set_content(self, content=None, excludes=EmptyI, pathname=None,
            signatures=False):
                """Populate the manifest with actions.

                'content' is an optional value containing either the text
                representation of the manifest or an iterable of
                action objects.

                'excludes' is optional.  If provided it must be a length two
                list with the variants to be excluded as the first element and
                the facets to be excluded as the second element.

                'pathname' is an optional filename containing the location of
                the manifest content.

                'signatures' is an optional boolean value that indicates whether
                a manifest signature should be generated.  This is only possible
                when 'content' is a string or 'pathname' is provided.
                """

                assert content is not None or pathname is not None
                assert not (content and pathname)

                self.actions = []
                self.actions_bytype = {}
                self.attributes = {}
                self._cache = {}
                self._absent_cache = []

                # So we could build up here the type/key_attr dictionaries like
                # sdict and odict in difference() above, and have that be our
                # main datastore, rather than the simple list we have now.  If
                # we do that here, we can even assert that the "same" action
                # can't be in a manifest twice.  (The problem of having the same
                # action more than once in packages that can be installed
                # together has to be solved somewhere else, though.)
                if pathname:
                        try:
                                with open(pathname, "r") as mfile:
                                        content = mfile.read()
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                if six.PY3 and isinstance(content, bytes):
                        raise TypeError("content must be str, not bytes")

                if isinstance(content, six.string_types):
                        if signatures:
                                # Generate manifest signature based upon
                                # input content, but only if signatures
                                # were requested. In order to interoperate with
                                # older clients, we must use sha-1 here.
                                self.signatures = {
                                    "sha-1": self.hash_create(content)
                                }
                        content = self.__content_to_actions(content)

                for action in content:
                        self.add_action(action, excludes)
                self.excludes = excludes
                # Make sure that either no excludes were provided or that both
                # variants and facet excludes were or that variant, facet and
                # hydrate excludes were.
                assert len(self.excludes) != 1

        def exclude_content(self, excludes):
                """Remove any actions from the manifest which should be
                excluded."""

                self.set_content(content=self.actions, excludes=excludes)

        def add_action(self, action, excludes):
                """Performs any needed transformations on the action then adds
                it to the manifest.

                The "action" parameter is the action object that should be
                added to the manifest.

                The "excludes" parameter is the variants to exclude from the
                manifest."""

                attrs = action.attrs
                aname = action.name

                # XXX handle legacy transition issues; not needed once support
                # for upgrading images from older releases (< build 151) has
                # been removed.
                if "opensolaris.zone" in attrs and \
                    "variant.opensolaris.zone" not in attrs:
                        attrs["variant.opensolaris.zone"] = \
                            attrs["opensolaris.zone"]

                if aname == "set" and attrs["name"] == "authority":
                        # Translate old action to new.
                        attrs["name"] = "publisher"

                if excludes and not action.include_this(excludes,
                    publisher=self.publisher):
                        return
                self.actions.append(action)
                try:
                        self.actions_bytype[aname].append(action)
                except KeyError:
                        self.actions_bytype.setdefault(aname, []).append(action)

                # add any set actions to attributes
                if aname == "set":
                        self.fill_attributes(action)

        def fill_attributes(self, action):
                """Fill attribute array w/ set action contents."""
                try:
                        keyvalue = action.attrs["name"]
                        if keyvalue[:10] == "pkg.sizes.":
                                # To reduce manifest bloat, size and csize
                                # are set on a single action so need splitting
                                # into separate attributes.
                                attrval = action.attrlist("value")
                                for entry in attrval:
                                        szname, szval = entry.split("=", 1)
                                        if szname == "sz":
                                                szname = "pkg.size"
                                        elif szname == "csz":
                                                szname = "pkg.csize"
                                        else:
                                                # Skip unknowns.
                                                continue

                                        self.attributes.setdefault(szname, 0)
                                        self.attributes[szname] += int(szval)
                                return
                except (KeyError, TypeError, ValueError):
                        # ignore broken set actions
                        pass

                # Ensure facet and variant attributes are always lists.
                if keyvalue[:10] == "pkg.facet.":
                        # Possible facets list is spread over multiple actions.
                        val = action.attrlist("value")
                        if len(val) == 1 and val[0] == "":
                                # No facets.
                                val = []

                        seen = self.attributes.setdefault("pkg.facet", [])
                        for f in val:
                                entry = "facet.{0}".format(f)
                                if entry not in seen:
                                        # Prevent duplicates; it's possible a
                                        # given facet may be valid for more than
                                        # one unique variant combination that's
                                        # allowed by current excludes.
                                        seen.append(f)
                        return
                elif keyvalue == "pkg.variant":
                        val = action.attrlist("value")
                        if len(val) == 1 and val[0] == "":
                                # No variants.
                                val = []

                        self.attributes[keyvalue] = [
                            "variant.{0}".format(v)
                            for v in val
                        ]
                        return
                elif keyvalue[:8] == "variant.":
                        self.attributes[keyvalue] = action.attrlist("value")
                        return

                if keyvalue == "fmri":
                        # Ancient manifest compatibility.
                        keyvalue = "pkg.fmri"
                self.attributes[keyvalue] = action.attrs["value"]

        @staticmethod
        def search_dict(file_path, excludes, return_line=False,
            log=None):
                """Produces the search dictionary for a specific manifest.
                A dictionary is constructed which maps a tuple of token,
                action type, key, and the value that matched the token to
                the byte offset into the manifest file. file_path is the
                path to the manifest file. excludes is the variants which
                should be allowed in this image. return_line is a debugging
                flag which makes the function map the information to the
                string of the line, rather than the byte offset to allow
                easier debugging."""

                if log is None:
                        log = lambda x: None

                try:
                        file_handle = open(file_path, "r")
                except EnvironmentError as e:
                        if e.errno != errno.ENOENT:
                                raise
                        log((_("{fp}:\n{e}").format(
                            fp=file_path, e=e)))
                        return {}
                cur_pos = 0
                line = file_handle.readline()
                action_dict = {}
                def __handle_list(lst, cp):
                        """Translates what actions.generate_indices produces
                        into a dictionary mapping token, action_name, key, and
                        the value that should be displayed for matching that
                        token to byte offsets into the manifest file.

                        The "lst" parameter is the data to be converted.

                        The "cp" parameter is the byte offset into the file
                        for the action which produced lst."""

                        for action_name, subtype, tok, full_value in lst:
                                if action_name == "set":
                                        if full_value is None:
                                                full_value = tok
                                else:
                                        if full_value is None:
                                                full_value = subtype
                                        if full_value is None:
                                                full_value = action_name
                                if isinstance(tok, list):
                                        __handle_list([
                                            (action_name, subtype, t,
                                            full_value)
                                            for t in tok
                                        ], cp)
                                else:
                                        if (tok, action_name, subtype,
                                            full_value) in action_dict:
                                                action_dict[(tok, action_name,
                                                    subtype, full_value)
                                                    ].append(cp)
                                        else:
                                                action_dict[(tok, action_name,
                                                    subtype, full_value)] = [cp]
                while line:
                        l = line.strip()
                        if l and l[0] != "#":
                                try:
                                        action = actions.fromstr(l)
                                except actions.ActionError as e:
                                        log((_("{fp}:\n{e}").format(
                                            fp=file_path, e=e)))
                                else:
                                        if not excludes or \
                                            action.include_this(excludes):
                                                if "path" in action.attrs:
                                                        np = action.attrs["path"].lstrip(os.path.sep)
                                                        action.attrs["path"] = \
                                                            np
                                                try:
                                                        inds = action.generate_indices()
                                                except KeyError as k:
                                                        log(_("{fp} contains "
                                                            "an action which is"
                                                            " missing the "
                                                            "expected attribute"
                                                            ": {at}.\nThe "
                                                            "action is:"
                                                            "{act}").format(
                                                                fp=file_path,
                                                                at=k.args[0],
                                                                act=l
                                                           ))
                                                else:
                                                        arg = cur_pos
                                                        if return_line:
                                                                arg = l
                                                        __handle_list(inds, arg)
                        cur_pos = file_handle.tell()
                        line = file_handle.readline()
                file_handle.close()
                return action_dict

        @staticmethod
        def hash_create(mfstcontent):
                """This method takes a string representing the on-disk
                manifest content, and returns a hash value."""

                # This must be an SHA-1 hash in order to interoperate with
                # older clients.
                sha_1 = hashlib.sha1()
                if isinstance(mfstcontent, six.text_type):
                        # Byte stream expected, so pass encoded.
                        sha_1.update(mfstcontent.encode("utf-8"))
                else:
                        sha_1.update(mfstcontent)

                return sha_1.hexdigest()

        def validate(self, signatures):
                """Verifies whether the signatures for the contents of
                the manifest match the specified signature data.  Raises
                the 'BadManifestSignatures' exception on failure."""

                if signatures != self.signatures:
                        raise apx.BadManifestSignatures(self.fmri)

        def store(self, mfst_path):
                """Store the manifest contents to disk."""

                t_dir = os.path.dirname(mfst_path)
                t_prefix = os.path.basename(mfst_path) + "."

                try:
                        os.makedirs(t_dir, mode=PKG_DIR_MODE)
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        if e.errno != errno.EEXIST:
                                raise

                try:
                        fd, fn = tempfile.mkstemp(dir=t_dir, prefix=t_prefix)
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                mfile = os.fdopen(fd, "w")

                #
                # We specifically avoid sorting manifests before writing
                # them to disk-- there's really no point in doing so, since
                # we'll sort actions globally during packaging operations.
                #
                mfile.write(self.tostr_unsorted())
                mfile.close()

                try:
                        os.chmod(fn, PKG_FILE_MODE)
                        portable.rename(fn, mfst_path)
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        def get_variants(self, name):
                if name not in self.attributes:
                        return None
                variants = self.attributes[name]
                if not isinstance(variants, str):
                        return variants
                return [variants]

        def get_all_variants(self):
                """Return a dictionary mapping variant tags to their values."""
                return variant.VariantCombinationTemplate(dict((
                    (name, self.attributes[name])
                    for name in self.attributes
                    if name.startswith("variant.")
                )))

        def get(self, key, default):
                try:
                        return self[key]
                except KeyError:
                        return default

        def getbool(self, key, default):
                """Returns the boolean of the value of the attribute 'key'."""

                ret = self.get(key, default).lower()
                if ret == "true":
                        return True
                elif ret == "false":
                        return False
                else:
                        raise ValueError(_("Attribute value '{0}' not 'true' or "
                            "'false'".format(ret)))

        def get_size(self, excludes=EmptyI):
                """Returns an integer tuple of the form (size, csize), where
                'size' represents the total uncompressed size, in bytes, of the
                Manifest's data payload, and 'csize' represents the compressed
                version of that.

                'excludes' is a list of a list of variants and facets which
                should be allowed when calculating the total."""

                if self.excludes == excludes:
                        excludes = EmptyI
                assert excludes == EmptyI or self.excludes == EmptyI

                csize = 0
                size = 0

                attrs = self.attributes
                if ("pkg.size" in attrs and "pkg.csize" in attrs) and \
                    (excludes == EmptyI or self.excludes == excludes):
                        # If specified excludes match loaded excludes, then use
                        # cached attributes; this is safe as manifest attributes
                        # are reset or updated every time exclude_content,
                        # set_content, or add_action is called.
                        return (attrs["pkg.size"], attrs["pkg.csize"])

                for a in self.gen_actions(excludes=excludes):
                        size += a.get_size()
                        csize += misc.get_pkg_otw_size(a)

                if excludes == EmptyI:
                        # Cache for future calls.
                        attrs["pkg.size"] = size
                        attrs["pkg.csize"] = csize

                return (size, csize)

        def _get_varcets(self, excludes=EmptyI):
                """Private helper function to get list of facets/variants."""

                variants = defaultdict(set)
                facets = defaultdict(set)

                nexcludes = excludes
                if nexcludes:
                        # Facet filtering should never be applied when excluding
                        # actions; only variant filtering.  This is ugly, but
                        # our current variant/facet filtering system doesn't
                        # allow you to be selective and various bits in
                        # pkg.manifest assume you always filter on both so we
                        # have to fake up a filter for facets.
                        if six.PY2:
                                nexcludes = [
                                    x for x in excludes
                                    if x.__func__ != facet._allow_facet
                                ]
                        else:
                                nexcludes = [
                                    x for x in excludes
                                    if x.__func__ != facet.Facets.allow_action
                                ]
                        # Excludes list must always have zero or 2+ items; so
                        # fake second entry.
                        nexcludes.append(lambda x, publisher: True)
                        assert len(nexcludes) > 1

                for action in self.gen_actions():
                        # append any variants and facets to manifest dict
                        attrs = action.attrs
                        v_list, f_list = action.get_varcet_keys()

                        if not (v_list or f_list):
                                continue

                        try:
                                for v, d in zip(v_list, repeat(variants)):
                                        d[v].add(attrs[v])

                                if not excludes or action.include_this(
                                    nexcludes, publisher=self.publisher):
                                        # While variants are package level (you
                                        # can't install a package without
                                        # setting the variant first), facets
                                        # from the current action should only be
                                        # included if the action is not
                                        # excluded.
                                        for v, d in zip(f_list, repeat(facets)):
                                                d[v].add(attrs[v])
                        except TypeError:
                                # Lists can't be set elements.
                                raise actions.InvalidActionError(action,
                                    _("{forv} '{v}' specified multiple times").format(
                                    forv=v.split(".", 1)[0], v=v))

                return (variants, facets)

        def __getitem__(self, key):
                """Return the value for the package attribute 'key'."""
                return self.attributes[key]

        def __setitem__(self, key, value):
                """Set the value for the package attribute 'key' to 'value'."""
                self.attributes[key] = value
                for a in self.actions:
                        if a.name == "set" and a.attrs["name"] == key:
                                a.attrs["value"] = value
                                return

                new_attr = AttributeAction(None, name=key, value=value)
                self.actions.append(new_attr)
                self.actions_bytype.setdefault("set", []).append(new_attr)

        def __contains__(self, key):
                return key in self.attributes

null = Manifest()

class FactoredManifest(Manifest):
        """This class serves as a wrapper for the Manifest class for callers
        that need efficient access to package data on a per-action type basis.
        It achieves this by partitioning the manifest into multiple files (one
        per action type) and then storing an on-disk cache of the directories
        explictly and implicitly referenced by the manifest each tagged with
        the appropriate variants/facets."""

        def __init__(self, fmri, cache_root, contents=None, excludes=EmptyI,
            pathname=None):
                """Raises KeyError exception if factored manifest is not present
                and contents are None; delays reading of manifest until required
                if cache file is present.

                'fmri' is a PkgFmri object representing the identity of the
                package.

                'cache_root' is the pathname of the directory where the manifest
                and cache files should be stored or loaded from.

                'contents' is an optional string to use as the contents of the
                manifest if a cached copy does not already exist.

                'excludes' is optional.  If provided it must be a length two
                list with the variants to be excluded as the first element and
                the facets to be exclduded as the second element.

                'pathname' is an optional string containing the pathname of a
                manifest.  If not provided, it is assumed that the manifest is
                stored in a file named 'manifest' in the directory indicated by
                'cache_root'.  If provided, and contents is also provided, then
                'contents' will be stored in 'pathname' if it does not already
                exist.
                """

                Manifest.__init__(self, fmri)
                self.__cache_root = cache_root
                self.__pathname = pathname
                # Make sure that either no excludes were provided or 2+ excludes
                # were.
                assert len(self.excludes) != 1
                self.loaded = False

                # Do we have a cached copy?
                if not os.path.exists(self.pathname):
                        if contents is None:
                                raise KeyError(fmri)
                        # we have no cached copy; save one
                        # don't specify excludes so on-disk copy has
                        # all variants
                        self.set_content(content=contents)
                        self.__finiload()
                        if self.__storeback():
                                self.__unload()
                        if excludes:
                                self.exclude_content(excludes)
                        return

                # we have a cached copy of the manifest
                mdpath = self.__cache_path("manifest.dircache")

                # have we computed the dircache?
                if not os.path.exists(mdpath): # we're adding cache
                        self.excludes = EmptyI # to existing manifest
                        self.__load()
                        if self.__storeback():
                                self.__unload()
                        if excludes:
                                self.excludes = excludes
                                self.__load()
                        return
                self.exclude_content(excludes)

        def __cache_path(self, name):
                return os.path.join(self.__cache_root, name)

        def __load(self):
                """Load all manifest contents from on-disk copy of manifest"""
                self.set_content(excludes=self.excludes, pathname=self.pathname)
                self.__finiload()

        def __unload(self):
                """Unload manifest; used to reduce peak memory comsumption
                when downloading new manifests"""
                self.actions = []
                self.actions_bytype = {}
                self.attributes = {}
                self.loaded = False

        def __finiload(self):
                """Finish loading.... this part of initialization is common
                to multiple code paths"""
                self.loaded = True

        def __storeback(self):
                """ store the current action set; also create per-type
                caches.  Return True if data was saved, False if not"""
                assert self.loaded
                try:
                        self.store(self.pathname)
                        self.__storebytype()
                        return True
                except apx.PermissionsException:
                        # this allows us to try to cache new manifests
                        # when non-root w/o failures.
                        return False

        def __storebytype(self):
                """ create manifest.<typename> files to accelerate partial
                parsing of manifests.  Separate from __storeback code to
                allow upgrade to reuse existing on disk manifests"""

                assert self.loaded

                t_dir = self.__cache_root

                # Ensure target cache directory and intermediates exist.
                misc.makedirs(t_dir)

                # create per-action type cache; use rename to avoid corrupt
                # files if ^C'd in the middle.  All action types are considered
                # so that empty cache files are created if no action of that
                # type exists for the package (avoids full manifest loads
                # later).
                for n, acts in six.iteritems(self.actions_bytype):
                        t_prefix = "manifest.{0}.".format(n)

                        try:
                                fd, fn = tempfile.mkstemp(dir=t_dir,
                                    prefix=t_prefix)
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                        f = os.fdopen(fd, "w")
                        try:
                                for a in acts:
                                        f.write("{0}\n".format(a))
                                if n == "set":
                                        # Add supplemental action data; yes this
                                        # does mean the cache is not the same as
                                        # retrieved manifest, but that's ok.
                                        # Signature verification is done using
                                        # the raw manifest.
                                        f.writelines(self._gen_attrs_to_str())
                        except EnvironmentError as e:
                                raise apx._convert_error(e)
                        finally:
                                f.close()

                        try:
                                os.chmod(fn, PKG_FILE_MODE)
                                portable.rename(fn,
                                    self.__cache_path("manifest.{0}".format(n)))
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                def create_cache(name, refs):
                        try:
                                fd, fn = tempfile.mkstemp(dir=t_dir,
                                    prefix=name + ".")
                                with os.fdopen(fd, "w") as f:
                                        f.writelines(refs())
                                os.chmod(fn, PKG_FILE_MODE)
                                portable.rename(fn, self.__cache_path(name))
                        except EnvironmentError as e:
                                raise apx._convert_error(e)

                create_cache("manifest.dircache", self._gen_dirs_to_str)
                create_cache("manifest.mediatorcache",
                    self._gen_mediators_to_str)

        @staticmethod
        def clear_cache(cache_root):
                """Remove all manifest cache files found in the given directory
                (excluding the manifest itself) and the cache_root if it is
                empty afterwards.
                """

                try:
                        for cname in os.listdir(cache_root):
                                if not cname.startswith("manifest."):
                                        continue
                                try:
                                        portable.remove(os.path.join(
                                            cache_root, cname))
                                except EnvironmentError as e:
                                        if e.errno != errno.ENOENT:
                                                raise

                        # Ensure cache dir is removed if the last cache file is
                        # removed; we don't care if it fails.
                        try:
                                os.rmdir(cache_root)
                        except:
                                pass
                except EnvironmentError as e:
                        if e.errno != errno.ENOENT:
                                # Only raise error if failure wasn't due to
                                # cache directory not existing.
                                raise apx._convert_error(e)

        def __load_cached_data(self, name):
                """Private helper function for loading arbitrary cached manifest
                data.
                """

                mpath = self.__cache_path(name)
                if os.path.exists(mpath):
                        # we have cached copy on disk; use it
                        try:
                                with open(mpath, "r") as f:
                                        self._cache[name] = [
                                            a for a in
                                            (
                                                actions.fromstr(s.rstrip())
                                                for s in f
                                            )
                                            if not self.excludes or
                                                a.include_this(self.excludes,
                                                    publisher=self.publisher)
                                        ]
                                return
                        except EnvironmentError as e:
                                raise apx._convert_error(e)
                        except actions.ActionError as e:
                                # Cache file is malformed; hopefully due to bugs
                                # that have been resolved (as opposed to actual
                                # corruption).  Assume we should just ignore the
                                # cache and load action data.
                                try:
                                        self.clear_cache(self.__cache_root)
                                except Exception as e:
                                        # Ignore errors encountered during cache
                                        # dump for this specific case.
                                        pass

                # no cached copy
                if not self.loaded:
                        # need to load from disk
                        self.__load()
                assert self.loaded

        def get_directories(self, excludes):
                """ return a list of directories implicitly or explicitly
                referenced by this object
                """
                self.__load_cached_data("manifest.dircache")
                return Manifest.get_directories(self, excludes)

        def gen_actions_by_type(self, atype, attr_match=None, excludes=EmptyI):
                """ generate actions of the specified type;
                use already in-memory stuff if already loaded,
                otherwise use per-action types files"""

                if self.loaded: #if already loaded, use in-memory cached version
                        # invoke subclass method to generate action by action
                        for a in Manifest.gen_actions_by_type(self, atype,
                            attr_match=attr_match, excludes=excludes):
                                yield a
                        return

                # This checks if we've already written out the factored
                # manifest files.  If so, we'll use it, and if not, then
                # we'll load the full manifest.
                mpath = self.__cache_path("manifest.dircache")

                if not os.path.exists(mpath):
                        # no cached copy :-(
                        if not self.loaded:
                                # get manifest from disk
                                self.__load()
                        # invoke subclass method to generate action by action
                        for a in Manifest.gen_actions_by_type(self, atype,
                            attr_match=attr_match, excludes=excludes):
                                yield a
                        return

                if excludes == EmptyI:
                        excludes = self.excludes
                assert excludes == self.excludes or self.excludes == EmptyI

                if atype in self._absent_cache:
                        # No such action in the manifest; must be done *after*
                        # asserting excludes are correct to avoid hiding
                        # failures.
                        return

                # Assume a cached copy exists; if not, tag the action type to
                # avoid pointless I/O later.
                mpath = self.__cache_path("manifest.{0}".format(atype))

                if attr_match:
                        attr_match = _compile_fnpats(attr_match)

                try:
                        with open(mpath, "r") as f:
                                for l in f:
                                        a = actions.fromstr(l.rstrip())
                                        if (excludes and
                                            not a.include_this(excludes,
                                                publisher=self.publisher)):
                                                continue
                                        # These conditions are split by
                                        # performance.
                                        if not attr_match:
                                                yield a
                                        elif _attr_matches(a, attr_match):
                                                yield a

                except EnvironmentError as e:
                        if e.errno == errno.ENOENT:
                                self._absent_cache.append(atype)
                                return # no such action in this manifest
                        raise apx._convert_error(e)

        def gen_facets(self, excludes=EmptyI, patterns=EmptyI):
                """A generator function that returns the supported facet
                attributes (strings) for this package based on the specified (or
                current) excludes that also match at least one of the patterns
                provided.  Facets must be true or false so a list of possible
                facet values is not returned."""

                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.gen_facets(self, excludes=excludes,
                    patterns=patterns)

        def gen_variants(self, excludes=EmptyI, patterns=EmptyI):
                """A generator function that yields a list of tuples of the form
                (variant, [values]).  Where 'variant' is the variant attribute
                name (e.g. 'variant.arch') and '[values]' is a list of the
                variant values supported by this package.  Variants returned are
                those allowed by the specified (or current) excludes that also
                match at least one of the patterns provided."""

                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.gen_variants(self, excludes=excludes,
                    patterns=patterns)

        def gen_mediators(self, excludes=EmptyI):
                """A generator function that yields set actions expressing the
                set of possible mediations for this package.
                """
                self.__load_cached_data("manifest.mediatorcache")
                return Manifest.gen_mediators(self, excludes=excludes)

        def __load_attributes(self):
                """Load attributes dictionary from cached set actions;
                this speeds up pkg info a lot"""

                mpath = self.__cache_path("manifest.set")
                if not os.path.exists(mpath):
                        return False
                with open(mpath, "r") as f:
                        for l in f:
                                a = actions.fromstr(l.rstrip())
                                if not self.excludes or \
                                    a.include_this(self.excludes,
                                        publisher=self.publisher):
                                        self.fill_attributes(a)

                return True

        def get_size(self, excludes=EmptyI):
                """Returns an integer tuple of the form (size, csize), where
                'size' represents the total uncompressed size, in bytes, of the
                Manifest's data payload, and 'csize' represents the compressed
                version of that.

                'excludes' is a list of a list of variants and facets which
                should be allowed when calculating the total."""
                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.get_size(self, excludes=excludes)

        def __getitem__(self, key):
                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.__getitem__(self, key)

        def __setitem__(self, key, value):
                """No assignments to factored manifests allowed."""
                assert "FactoredManifests are not dicts"

        def __contains__(self, key):
                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.__contains__(self, key)

        def get(self, key, default):
                try:
                        return self[key]
                except KeyError:
                        return default

        def get_variants(self, name):
                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.get_variants(self, name)

        def get_all_variants(self):
                if not self.loaded and not self.__load_attributes():
                        self.__load()
                return Manifest.get_all_variants(self)

        @staticmethod
        def search_dict(cache_path, excludes, return_line=False):
                return Manifest.search_dict(cache_path, excludes,
                    return_line=return_line)

        def gen_actions(self, attr_match=None, excludes=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.gen_actions(self, attr_match=attr_match,
                    excludes=excludes)

        def __str__(self, excludes=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.__str__(self)

        def duplicates(self, excludes=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.duplicates(self, excludes=excludes)

        def difference(self, origin, origin_exclude=EmptyI,
            self_exclude=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.difference(self, origin,
                    origin_exclude=origin_exclude,
                    self_exclude=self_exclude)

        def store(self, mfst_path):
                """Store the manifest contents to disk."""
                if not self.loaded:
                        self.__load()
                super(FactoredManifest, self).store(mfst_path)

        @property
        def pathname(self):
                """The absolute pathname of the file containing the manifest."""

                if self.__pathname:
                        return self.__pathname
                return os.path.join(self.__cache_root, "manifest")


class EmptyFactoredManifest(Manifest):
        """Special class for pkgplan's need for a empty manifest;
        the regular null manifest doesn't support get_directories
        and making the factored manifest code handle this case is
        too ugly..."""

        def __init__(self):
                Manifest.__init__(self)

        def difference(self, origin, origin_exclude=EmptyI,
            self_exclude=EmptyI):
                """Return three lists of action pairs representing origin and
                destination actions.  The first list contains the pairs
                representing additions, the second list contains the pairs
                representing updates, and the third list contains the pairs
                representing removals.  All three lists are in the order in
                which they should be executed."""

                # The difference for this case is simply everything in the
                # origin has been removed.  This is an optimization for
                # uninstall.
                return ManifestDifference([], [],
                    [(a, None) for a in origin.gen_actions(excludes=
                    origin_exclude)])

        @staticmethod
        def get_directories(excludes):
                return []

        def exclude_content(self, *args, **kwargs):
                # This method is overridden so that self.excludes is never set
                # on the singleton NullFactoredManifest.
                return

        def set_content(self, *args, **kwargs):
                raise RuntimeError("Cannot call set_content on an "
                    "EmptyFactoredManifest")

NullFactoredManifest = EmptyFactoredManifest()

class ManifestError(Exception):
        """Simple Exception class to handle manifest specific errors"""

        def __init__(self, duplicates=EmptyI):
                self.__duplicates = duplicates

        def __str__(self):
                ret = []
                for d in self.__duplicates:
                        ret.append("{0}\n{1}\n\n".format(*d))

                return "\n".join(ret)
