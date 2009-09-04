#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import os
import errno
from itertools import groupby, chain, repeat
from pkg.misc import EmptyI, expanddirs

import pkg.actions as actions
import pkg.portable as portable
import pkg.variant as variant
from pkg.actions.attribute import AttributeAction

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

        def __init__(self):
                self.img = None
                self.fmri = None

                self.actions = []
                self.actions_bytype = {}
                self.variants = {}   # variants seen in package
                self.facets = {}     # facets seen in package
                self.attributes = {} # package-wide attributes

        def __str__(self):
                r = ""
                if "fmri" not in self.attributes and self.fmri != None:
                        r += "set name=fmri value=%s\n" % self.fmri

                for act in sorted(self.actions):
                        r += "%s\n" % act
                return r

        def tostr_unsorted(self):
                r = ""
                if "fmri" not in self.attributes and self.fmri != None:
                        r += "set name=fmri value=%s\n" % self.fmri

                for act in self.actions:
                        r += "%s\n" % act
                return r


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

                if isinstance(origin, EmptyCachedManifest):
                        # No origin was provided, so nothing has been changed or
                        # removed; only added.  In addition, this doesn't need
                        # to be sorted since the caller likely already does
                        # (such as pkgplan/imageplan).
                        return (
                            [(None, a) for a in self.gen_actions(self_exclude)],
                            [], [])

                sdict = dict(
                    ((a.name, a.attrs.get(a.key_attr, id(a))), a)
                    for a in self.gen_actions(self_exclude)
                )
                odict = dict(
                    ((a.name, a.attrs.get(a.key_attr, id(a))), a)
                    for a in origin.gen_actions(origin_exclude)
                )

                sset = set(sdict.keys())
                oset = set(odict.keys())

                added = [(None, sdict[i]) for i in sset - oset]
                removed = [(odict[i], None) for i in oset - sset]
                # XXX for now, we force license actions to always be
                # different to insure that existing license files for
                # new versions are always installed
                changed = [
                    (odict[i], sdict[i])
                    for i in oset & sset
                    if odict[i].different(sdict[i]) or i[0] == "license"
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

                return (added, changed, removed)

        @staticmethod
        def comm(*compare_m):
                """Like the unix utility comm, except that this function
                takes an arbitrary number of manifests and compares them,
                returning a tuple consisting of each manifest's actions
                that are not the same for all manifests, followed by a
                list of actions that are the same in each manifest."""

                # construct list of dictionaries of actions in each
                # manifest, indexed by unique keys
                m_dicts = [
                    dict(
                    ((a.name, a.attrs.get(a.key_attr, id(a))), a)
                    for a in m.actions)
                    for m in compare_m
                ]
                # construct list of key sets in each dict
                #
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

        def set_fmri(self, img, fmri):
                self.img = img
                self.fmri = fmri

        def set_content(self, content, excludes=EmptyI):
                """content is the text representation of the manifest"""
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
                for l in content.splitlines():
                        l = l.lstrip()
                        if not l or l[0] == "#":
                                continue

                        try:
                                action = actions.fromstr(l)
                        except actions.ActionError, e:
                                # Add the FMRI to the exception and re-raise
                                e.fmri = self.fmri
                                raise
                        # XXX handle legacy transition issues; not needed after
                        # 2009.06 release & republication are complete.
                        if "opensolaris.zone" in action.attrs and \
                            "variant.opensolaris.zone" not in action.attrs:
                                action.attrs["variant.opensolaris.zone"] = \
                                    action.attrs["opensolaris.zone"]

                        if action.name == "set" and \
                            action.attrs["name"] == "authority":
                                # Translate old action to new.
                                action.attrs["name"] = "publisher"

                        if action.attrs.has_key("path"):
                                np = action.attrs["path"].lstrip(os.path.sep)
                                action.attrs["path"] = np

                        if not action.include_this(excludes):
                                continue

                        self.actions.append(action)

                        if action.name not in self.actions_bytype:
                                self.actions_bytype[action.name] = [ action ]
                        else:
                                self.actions_bytype[action.name].append(action)
                        # add any set actions to attributes
                        if action.name == "set":
                                self.fill_attributes(action)
                        # append any variants and facets to manifest dict
                        v_list, f_list = action.get_varcet_keys()

                        if v_list or f_list:
                                for v, d in zip(v_list, repeat(self.variants)) \
                                    + zip(f_list, repeat(self.facets)):
                                        if v not in d:
                                                d[v] = set([action.attrs[v]])
                                        else:
                                                d[v].add(action.attrs[v])
                return

        def fill_attributes(self, action):
                """Fill attribute array w/ set action contents."""
                try:
                        keyvalue = action.attrs["name"]
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

                file_handle = file(file_path)
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

        def store(self, mfst_path):
                """Store the manifest contents to disk."""

                tmp_path = mfst_path + ".tmp"
                try:
                        mfile = file(tmp_path, "w")
                except IOError:
                        try:
                                os.makedirs(os.path.dirname(mfst_path))
                        except OSError, e:
                                if e.errno != errno.EEXIST:
                                        raise
                        mfile = file(tmp_path, "w")

                #
                # We specifically avoid sorting manifests before writing
                # them to disk-- there's really no point in doing so, since
                # we'll sort actions globally during packaging operations.
                #
                mfile.write(self.tostr_unsorted())
                mfile.close()
                portable.rename(tmp_path, mfst_path)

        def get_variants(self, name):
                if name not in self.attributes:
                        return None
                variants = self.attributes[name]
                if not isinstance(variants, str):
                        return variants
                return [variants]

        def get_all_variants(self):
                """Return a dictionary mapping variant tags to their values."""
                return variant.VariantSets(dict((
                    (name, self.attributes[name])
                    for name in self.attributes
                    if name.startswith("variant.")
                )))

        def get(self, key, default):
                try:
                        return self[key]
                except KeyError:
                        return default

        def get_size(self, excludes=EmptyI):
                """Returns an integer representing the total size, in bytes, of
                the Manifest's data payload.

                'excludes' is a list of variants which should be allowed when
                calculating the total.
                """

                size = 0
                for a in self.gen_actions(excludes):
                        size += int(a.attrs.get("pkg.size", "0"))

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

        def __contains__(self, key):
                return key in self.attributes

null = Manifest()

class CachedManifest(Manifest):
        """This class handles a cache of manifests for the client;
        it partitions the manifest into multiple files (one per
        action type) and also builds an on-disk cache of the 
        directories explictly and implicitly referenced by the 
        manifest, tagging each one w/ the appropriate variants/facets."""

        def __file_path(self, file):
                return os.path.join(self.__pkgdir,
                    self.fmri.get_dir_path(), file)

        def __init__(self, fmri, pkgdir, preferred_pub, excludes=EmptyI, contents=None):
                """Raises KeyError exception if cached manifest
                is not present and contents are None; delays
                reading of manifest until required if cache file
                is present"""

                Manifest.__init__(self)
                self.__pkgdir = pkgdir
                self.__pub    = preferred_pub
                self.loaded   = False
                self.set_fmri(None, fmri)
                self.excludes = excludes

                mpath = self.__file_path("manifest")

                # Do we have a cached copy?
                if not os.path.exists(mpath): 
                        if not contents:
                                raise KeyError, fmri
                        # we have no cached copy; save one
                        # don't specify excludes so on-disk copy has
                        # all variants
                        self.set_content(contents) 
                        self.__finiload()
                        if self.__storeback():
                                self.__unload()
                        elif excludes:
                                self.set_content(contents, excludes)
                        return

                # we have a cached copy of the manifest
                mdpath = self.__file_path("manifest.dircache")
                
                # have we computed the dircache?
                if not os.path.exists(mdpath): # we're adding cache
                        self.excludes = EmptyI # to existing manifest
                        self.__load()
                        if self.__storeback():
                                self.__unload()
                        elif excludes:
                                self.excludes = excludes
                                self.__load()

        def __load(self):
                """Load all manifest contents from on-disk copy of manifest"""
                f = file(self.__file_path("manifest"))
                data = f.read()
                f.close()
                self.set_content(data, self.excludes)
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
                # this needs to change; we should not modify on-disk manifest
                if self.fmri and "publisher" not in self.attributes:
                        if not self.fmri.has_publisher():
                                pub = self.__pub
                        else:
                                pub = self.fmri.get_publisher()

                        # This shouldn't be set unless available.
                        if pub:
                                Manifest.__setitem__(self, "publisher", pub)

        def __storeback(self):
                """ store the current action set; also create per-type
                caches.  Return True if data was saved, False if not"""
                assert self.loaded
                try:
                        self.store(self.__file_path("manifest"))
                        self.__storebytype()
                        return True

                except  EnvironmentError, e:
                        # this allows us to try to cache new manifests
                        # when non-root w/o failures
                        if e.errno not in (errno.EROFS, errno.EACCES):
                                raise
                        return False

        def __storebytype(self):
                """ create manifest.<typename> files to accelerate partial
                parsing of manifests.  Separate from __storeback code to 
                allow upgrade to reuse existing on disk manifests"""

                assert self.loaded

                # create per-action type cache; use rename to avoid
                # corrupt files if ^C'd in the middle 
                # XXX consider use of per-process tmp file names
                for n in self.actions_bytype.keys():
                        f = file(self.__file_path("manifest.%s.tmp" % n), 
                            "w")
                        for a in self.actions_bytype[n]:
                                f.write("%s\n" % a)
                        f.close()
                        portable.rename(self.__file_path("manifest.%s.tmp" % n),
                            self.__file_path("manifest.%s" % n))
                # create dircache
                f = file(self.__file_path("manifest.dircache.tmp"), "w")
                dirs = self.__actions_to_dirs()

                for s in self.__gen_dirs_to_str(dirs):
                        f.write(s)

                f.close()
                portable.rename(self.__file_path("manifest.dircache.tmp"),
                    self.__file_path("manifest.dircache"))

        def __gen_dirs_to_str(self, dirs):
                """ from a dictionary of paths, generate contents of dircache 
                file"""
                for d in dirs:                        
                        for v in dirs[d]:
                                yield "dir path=%s %s\n" % \
                                    (d, " ".join("%s=%s" % t \
                                    for t in v.iteritems()))
        
        def __actions_to_dirs(self):
                """ create dictionary of all directories referenced 
                by actions explicitly or implicitly from self.actions...  
                include variants as values; collapse variants where possible"""
                assert self.loaded
                        
                dirs = {}
                # build a dictionary containing all directories tagged w/ 
                # variants
                for a in self.actions:
                        v, f = a.get_varcet_keys()
                        variants = dict((name, a.attrs[name]) for name in v + f)
                        for d in expanddirs(a.directory_references()): 
                                if d not in dirs:
                                        dirs[d] = [variants]
                                elif variants not in dirs[d]:
                                        dirs[d].append(variants)

                # remove any tags if any entries are always installed (NULL)
                for d in dirs:
                        if {} in dirs[d]:
                                dirs[d] = [{}]
                                continue
                        # could collapse dirs where all variants are present
                return dirs
                
        def get_directories(self, excludes):
                """ return a list of directories implicitly or
                explicitly referenced by this object"""
                
                mpath = self.__file_path("manifest.dircache")

                if not os.path.exists(mpath):
                        # no cached copy
                        if not self.loaded:
                                # need to load from disk
                                self.__load()
                        # generate actions that contain directories
                        alist = [
                                actions.fromstr(s.strip()) 
                                for s in self.__gen_dirs_to_str(
                                    self.__actions_to_dirs())
                                ]
                else: 
                        # we have cached copy on disk; use it
                        f = file(mpath)
                        alist = [actions.fromstr(s.strip()) for s in f]
                        f.close()
                s = set([
                         a.attrs["path"] 
                         for a in alist 
                         if a.include_this(excludes)
                         ])
                return list(s)

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

                mpath = self.__file_path("manifest.dircache")

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
                        mpath = self.__file_path("manifest.%s" % atype)

                        if not os.path.exists(mpath):
                                return # no such action in this manifest

                        f = file(mpath)
                        for l in f:
                                a = actions.fromstr(l.strip())
                                if a.include_this(excludes):
                                        yield a
                        f.close()

        def __load_attributes(self):
                """Load attributes dictionary from cached set actions;
                this speeds up pkg info a lot"""

                mpath = self.__file_path("manifest.set")
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
                """No assignments to cached manifests allowed."""
                assert "CachedManifests are not dicts"

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

        @staticmethod
        def search_dict(file_path, excludes, return_line=False):
                if not self.loaded:
                        self.__load()
                return Manifest.search_dict(file_path, excludes,
                    return_line=return_line)

        def gen_actions(self, excludes=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.gen_actions(self, excludes=excludes)

        def duplicates(self, excludes=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.duplicates(self, excludes=excludes)

        def difference(self, origin, origin_exclude=EmptyI, self_exclude=EmptyI):
                if not self.loaded:
                        self.__load()
                return Manifest.difference(self, origin, 
                    origin_exclude=origin_exclude, 
                    self_exclude=self_exclude)

                
class EmptyCachedManifest(Manifest):
        """Special class for pkgplan's need for a empty manifest;
        the regular null manifest doesn't support get_directories
        and making the cached manifest code handle this case is
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
                return ([], [],
                    [(a, None) for a in origin.gen_actions(self_exclude)])

        def get_directories(self, excludes):
                return []

NullCachedManifest = EmptyCachedManifest()
