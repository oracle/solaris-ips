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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
#

from collections import namedtuple, defaultdict
import errno
import hashlib
import os
import tempfile
from itertools import groupby, chain, repeat

import pkg.actions as actions
import pkg.client.api_errors as apx
import pkg.misc as misc
import pkg.portable as portable
import pkg.variant as variant
import pkg.version as version

from pkg.misc import EmptyDict, EmptyI, expanddirs, PKG_FILE_MODE, PKG_DIR_MODE
from pkg.actions.attribute import AttributeAction

ManifestDifference = namedtuple("ManifestDifference", "added changed removed")

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

                self.actions = []
                self.actions_bytype = {}
                self.variants = {}   # variants seen in package
                self.facets = {}     # facets seen in package
                self.attributes = {} # package-wide attributes
                self.signatures = EmptyDict
                self._cache = {}

        def __str__(self):
                r = ""
                if "pkg.fmri" not in self.attributes and self.fmri != None:
                        r += "set name=pkg.fmri value=%s\n" % self.fmri

                for act in sorted(self.actions):
                        r += "%s\n" % act
                return r

        def as_lines(self):
                """A generator function that returns the unsorted manifest
                contents as lines of text."""

                if "pkg.fmri" not in self.attributes and self.fmri != None:
                        yield "set name=pkg.fmri value=%s\n" % self.fmri

                for act in self.actions:
                        yield "%s\n" % act

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
                            [(None, a) for a in self.gen_actions(self_exclude)],
                            [], [])

                def hashify(v):
                        """handle key values that may be lists"""
                        if isinstance(v, list):
                                return frozenset(v)
                        else:
                                return v

                sdict = dict(
                    ((a.name, hashify(a.attrs.get(a.key_attr, id(a)))), a)
                    for a in self.gen_actions(self_exclude)
                )
                odict = dict(
                    ((a.name, hashify(a.attrs.get(a.key_attr, id(a)))), a)
                    for a in origin.gen_actions(origin_exclude)
                )

                sset = set(sdict.keys())
                oset = set(odict.keys())

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
                addsort = lambda x: x[1]
                remsort = lambda x: x[0]
                removed.sort(key = remsort, reverse = True)
                added.sort(key = addsort)
                changed.sort(key = addsort)

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
                                        key.update(
                                            "%s=%s" % (v, a.attrs[v])
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
                                out += "+ %s\n" % str(dest)
                        elif not dest:
                                out += "- %s\n" + str(src)
                        else:
                                out += "%s -> %s\n" % (src, dest)
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
                                yield "dir path=%s %s\n" % \
                                    (d, " ".join("%s=%s" % t \
                                    for t in v.iteritems()))

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
                for mediation, mvariants in mediators.iteritems():
                        values = {
                            "mediator-priority": mediation[1],
                            "mediator-version": mediation[2],
                            "mediator-implementation": mediation[3],
                        }
                        for mvariant in mvariants:
                                a = "set name=pkg.mediator " \
                                    "value=%s %s %s\n".rstrip() % (mediation[0],
                                     " ".join((
                                         "=".join(t)
                                          for t in values.iteritems()
                                          if t[1]
                                     )),
                                     " ".join((
                                         "=".join(t)
                                         for t in mvariant.iteritems()
                                     ))
                                )
                                yield a

        def _actions_to_dict(self, references):
                """create dictionary of all actions referenced explicitly or
                implicitly from self.actions... include variants as values;
                collapse variants where possible"""

                refs = {}
                # build a dictionary containing all directories tagged w/
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

                try:
                        alist = self._cache["manifest.dircache"]
                except KeyError:
                        # generate actions that contain directories
                        alist = self._cache["manifest.dircache"] = [
                            actions.fromstr(s.strip())
                            for s in self._gen_dirs_to_str()
                        ]

                s = set([
                    a.attrs["path"]
                    for a in alist
                    if a.include_this(excludes)
                ])

                return list(s)

        def gen_mediators(self, excludes=EmptyI):
                """A generator function that yields tuples of the form (mediator,
                mediations) expressing the set of possible mediations for this
                package, where 'mediations' is a set() of possible mediations for
                the mediator.  Each mediation is a tuple of the form (priority,
                version, implementation).
                """

                try:
                        alist = self._cache["manifest.mediatorcache"]
                except KeyError:
                        # generate actions that contain mediators
                        alist = self._cache["manifest.mediatorcache"] = [
                            actions.fromstr(s.strip())
                            for s in self._gen_mediators_to_str()
                        ]

                ret = defaultdict(set)
                for attrs in (
                    act.attrs
                    for act in alist
                    if act.include_this(excludes)):
                        med_ver = attrs.get("mediator-version")
                        if med_ver:
                                try:
                                        med_ver = version.Version(med_ver,
                                            "5.11")
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

        def gen_actions(self, excludes=EmptyI):
                """Generate actions in manifest through ordered callable list"""
                for a in self.actions:
                        for c in excludes:
                                if not c(a):
                                        break
                        else:
                                yield a

        def gen_actions_by_type(self, atype, excludes=EmptyI):
                """Generate actions in the manifest of type "type"
                through ordered callable list"""
                for a in self.actions_bytype.get(atype, []):
                        for c in excludes:
                                if not c(a):
                                        break
                        else:
                                yield a

        def gen_actions_by_types(self, atypes, excludes=EmptyI):
                """Generate actions in the manifest of types "atypes"
                through ordered callable list."""
                for atype in atypes:
                        for a in self.gen_actions_by_type(atype,
                            excludes=excludes):
                                yield a

        def gen_key_attribute_value_by_type(self, atype, excludes=EmptyI):
                """Generate the value of the key atrribute for each action
                of type "type" in the manifest."""

                return (
                    a.attrs.get(a.key_attr)
                    for a in self.gen_actions_by_type(atype, excludes)
                )

        def duplicates(self, excludes=EmptyI):
                """Find actions in the manifest which are duplicates (i.e.,
                represent the same object) but which are not identical (i.e.,
                have all the same attributes)."""

                def fun(a):
                        """Return a key on which actions can be sorted."""
                        return a.name, a.attrs.get(a.key_attr, id(a))

                alldups = []
                acts = [a for a in self.gen_actions(excludes)]

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
                accumulate = ""
                lineno = 0
                errors = []

                if isinstance(content, basestring):
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
                        except actions.ActionError, e:
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

                'excludes' is an optional list of variants to exclude from the
                manifest.

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
                self.variants = {}
                self.facets = {}
                self.attributes = {}

                # So we could build up here the type/key_attr dictionaries like
                # sdict and odict in difference() above, and have that be our
                # main datastore, rather than the simple list we have now.  If
                # we do that here, we can even assert that the "same" action
                # can't be in a manifest twice.  (The problem of having the same
                # action more than once in packages that can be installed
                # together has to be solved somewhere else, though.)
                if pathname:
                        try:
                                with open(pathname, "rb") as mfile:
                                        content = mfile.read()
                        except EnvironmentError, e:
                                raise apx._convert_error(e)
                if isinstance(content, basestring):
                        if signatures:
                                # Generate manifest signature based upon
                                # input content, but only if signatures
                                # were requested.
                                self.signatures = {
                                    "sha-1": self.hash_create(content)
                                }
                        content = self.__content_to_actions(content)

                for action in content:
                        self.add_action(action, excludes)

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

                # XXX handle legacy transition issues; not needed after
                # 2009.06 release & republication are complete.
                if "opensolaris.zone" in action.attrs and \
                    "variant.opensolaris.zone" not in action.attrs:
                        action.attrs["variant.opensolaris.zone"] = \
                            action.attrs["opensolaris.zone"]

                if action.name == "set" and action.attrs["name"] == "authority":
                        # Translate old action to new.
                        action.attrs["name"] = "publisher"

                if action.attrs.has_key("path"):
                        np = action.attrs["path"].lstrip(os.path.sep)
                        action.attrs["path"] = np

                if not action.include_this(excludes):
                        return

                self.actions.append(action)
                self.actions_bytype.setdefault(action.name, []).append(action)

                # add any set actions to attributes
                if action.name == "set":
                        self.fill_attributes(action)
                # append any variants and facets to manifest dict
                v_list, f_list = action.get_varcet_keys()

                if not (v_list or f_list):
                        return

                try:
                        for v, d in zip(v_list, repeat(self.variants)) \
                            + zip(f_list, repeat(self.facets)):
                                d.setdefault(v, set()).add(action.attrs[v])
                except TypeError:
                        # Lists can't be set elements.
                        raise actions.InvalidActionError(action,
                            _("%(forv)s '%(v)s' specified multiple times") %
                            {"forv": v.split(".", 1)[0], "v": v})

        def fill_attributes(self, action):
                """Fill attribute array w/ set action contents."""
                try:
                        keyvalue = action.attrs["name"]
                        if keyvalue == "fmri":
                                keyvalue = "pkg.fmri"
                        if keyvalue not in self.attributes:
                                self.attributes[keyvalue] = \
                                    action.attrs["value"]
                except KeyError: # ignore broken set actions
                        pass

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

                file_handle = file(file_path, "rb")
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
                                except actions.ActionError, e:
                                        log((_("%(fp)s:\n%(e)s") %
                                            { "fp": file_path, "e": e }))
                                else:
                                        if action.include_this(excludes):
                                                if action.attrs.has_key("path"):
                                                        np = action.attrs["path"].lstrip(os.path.sep)
                                                        action.attrs["path"] = \
                                                            np
                                                try:
                                                        inds = action.generate_indices()
                                                except KeyError, k:
                                                        log(_("%(fp)s contains "
                                                            "an action which is"
                                                            " missing the "
                                                            "expected attribute"
                                                            ": %(at)s.\nThe "
                                                            "action is:"
                                                            "%(act)s") %
                                                            {
                                                                "fp": file_path,
                                                                "at": k.args[0],
                                                                "act":l
                                                            })
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

                sha_1 = hashlib.sha1()
                if isinstance(mfstcontent, unicode):
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
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        if e.errno != errno.EEXIST:
                                raise

                try:
                        fd, fn = tempfile.mkstemp(dir=t_dir, prefix=t_prefix)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                mfile = os.fdopen(fd, "wb")

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
                except EnvironmentError, e:
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
                        raise ValueError(_("Attribute value '%s' not 'true' or "
                            "'false'" % ret))

        def get_size(self, excludes=EmptyI):
                """Returns an integer representing the total size, in bytes, of
                the Manifest's data payload.

                'excludes' is a list of variants which should be allowed when
                calculating the total.
                """

                size = 0
                for a in self.gen_actions(excludes):
                        size += a.get_size()
                return size

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

                'excludes' is an optional list of excludes to apply to the
                manifest after loading.

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
                self.excludes = excludes
                self.loaded = False

                # Do we have a cached copy?
                if not os.path.exists(self.pathname):
                        if not contents:
                                raise KeyError, fmri
                        # we have no cached copy; save one
                        # don't specify excludes so on-disk copy has
                        # all variants
                        self.set_content(content=contents)
                        self.__finiload()
                        if self.__storeback():
                                self.__unload()
                        elif excludes:
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
                        elif excludes:
                                self.excludes = excludes
                                self.__load()

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
                self.variants = {}
                self.facets = {}
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

                # create per-action type cache; use rename to avoid
                # corrupt files if ^C'd in the middle
                for n in self.actions_bytype.keys():
                        t_prefix = "manifest.%s." % n

                        fd, fn = tempfile.mkstemp(dir=t_dir, prefix=t_prefix)
                        f = os.fdopen(fd, "wb")

                        for a in self.actions_bytype[n]:
                                f.write("%s\n" % a)
                        f.close()
                        os.chmod(fn, PKG_FILE_MODE)
                        portable.rename(fn, self.__cache_path("manifest.%s" % n))

                def create_cache(name, refs):
                        try:
                                fd, fn = tempfile.mkstemp(dir=t_dir,
                                    prefix="manifest.dircache.")
                                with os.fdopen(fd, "wb") as f:
                                        f.writelines(refs())
                                os.chmod(fn, PKG_FILE_MODE)
                                portable.rename(fn, self.__cache_path(name))
                        except EnvironmentError, e:
                                raise apx._convert_error(e)

                create_cache("manifest.dircache", self._gen_dirs_to_str)
                create_cache("manifest.mediatorcache",
                    self._gen_mediators_to_str)

        @staticmethod
        def clear_cache(cache_root):
                """Remove all manifest cache files found in the given directory
                (excluding the manifest itself).
                """

                try:
                        for cname in os.listdir(cache_root):
                                if not cname.startswith("manifest."):
                                        continue
                                try:
                                        portable.remove(os.path.join(
                                            cache_root, cname))
                                except EnvironmentError, e:
                                        if e.errno != errno.ENOENT:
                                                raise
                except EnvironmentError, e:
                        if e.errno != errno.ENOENT:
                                # Only raise error if failure wasn't due to
                                # cache directory not existing.
                                raise apx._convert_error(e)

        def __load_cached_data(self, name):
                """Private helper function for loading arbitrary cached manifest
                data.
                """

                mpath = self.__cache_path(name)
                if not os.path.exists(mpath):
                        # no cached copy
                        if not self.loaded:
                                # need to load from disk
                                self.__load()
                        assert self.loaded
                        return

                # we have cached copy on disk; use it
                try:
                        with open(mpath, "rb") as f:
                                self._cache[name] = [
                                    actions.fromstr(s.strip())
                                    for s in f
                                ]
                except EnvironmentError, e:
                        raise apx._convert_error(e)

        def get_directories(self, excludes):
                """ return a list of directories implicitly or explicitly
                referenced by this object
                """
                self.__load_cached_data("manifest.dircache")
                return Manifest.get_directories(self, excludes)

        def gen_actions_by_type(self, atype, excludes=EmptyI):
                """ generate actions of the specified type;
                use already in-memory stuff if already loaded,
                otherwise use per-action types files"""

                if self.loaded: #if already loaded, use in-memory cached version
                        # invoke subclass method to generate action by action
                        for a in Manifest.gen_actions_by_type(self, atype,
                            excludes):
                                yield a
                        return

                # This checks if we've already written out the factorerd
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
                            excludes):
                                yield a
                else:
                        # we have a cached copy - use it
                        mpath = self.__cache_path("manifest.%s" % atype)

                        if not os.path.exists(mpath):
                                return # no such action in this manifest

                        f = file(mpath)
                        for l in f:
                                a = actions.fromstr(l.strip())
                                if a.include_this(excludes):
                                        yield a
                        f.close()

        def gen_mediators(self, excludes):
                """A generator function that yields set actions expressing the
                set of possible mediations for this package.
                """
                self.__load_cached_data("manifest.mediatorcache")
                return Manifest.gen_mediators(self, excludes)

        def __load_attributes(self):
                """Load attributes dictionary from cached set actions;
                this speeds up pkg info a lot"""

                mpath = self.__cache_path("manifest.set")
                if not os.path.exists(mpath):
                        return False
                f = file(mpath)
                for l in f:
                        a = actions.fromstr(l.strip())
                        if a.include_this(self.excludes):
                                self.fill_attributes(a)
                f.close()
                return True

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

        def gen_actions(self, excludes=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.gen_actions(self, excludes=excludes)

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
                    [(a, None) for a in origin.gen_actions(origin_exclude)])

        @staticmethod
        def get_directories(excludes):
                return []

NullFactoredManifest = EmptyFactoredManifest()

class ManifestError(Exception):
        """Simple Exception class to handle manifest specific errors"""

        def __init__(self, duplicates=EmptyI):
                self.__duplicates = duplicates

        def __str__(self):
                ret = []
                for d in self.__duplicates:
                        ret.append("%s\n%s\n\n" % d)

                return "\n".join(ret)


