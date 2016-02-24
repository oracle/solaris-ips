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
# Copyright (c) 2010, 2016, Oracle and/or its affiliates. All rights reserved.
#

from pkg.lint.engine import lint_fmri_successor

import collections
import copy
import os.path
import pkg.fmri
import pkg.lint.base as base
from pkg.actions import ActionError
from pkg.actions.file import FileAction
import re
import six
import stat

ObsoleteFmri = collections.namedtuple("ObsoleteFmri", "is_obsolete, fmri")

class PkgDupActionChecker(base.ActionChecker):
        """A class to check duplicate actions/attributes."""

        name = "pkglint.dupaction"

        def __init__(self, config):
                # dictionaries mapping path names to a list of tuples that are
                # installing to that path name. Each tuple represents a single
                # action and the fmri that delivers that action, to allow for a
                # given fmri delivering multiple copies of actions that install
                # to that path.
                # eg. pathdb[path] = [(fmri, action), (fmri, action) ... ]

                # The paths dictionaries for large repositories are rather
                # memory hungry and may well be useful services for other
                # checkers, so could be rolled into the engine itself (at the
                # cost of all checker classes paying the toll on engine
                # startup time.
                # We maintain similar dictionaries for other attributes that
                # should not be duplicated across (and within) manifests.

                self.description = _("Checks for duplicate IPS actions.")

                self.ref_paths = {}
                self.lint_paths = {}

                # similar dictionaries for drivers
                self.ref_drivers = {}
                self.lint_drivers = {}

                # and users / groups
                self.ref_usernames = {}
                self.ref_uids = {}
                self.lint_usernames = {}
                self.lint_uids = {}

                self.ref_groupnames = {}
                self.lint_groupnames = {}

                self.ref_gids = {}
                self.lint_gids = {}

                self.ref_legacy_pkgs = {}
                self.lint_legacy_pkgs = {}

                self.processed_paths = {}
                self.processed_drivers = {}
                self.processed_paths = {}
                self.processed_usernames = {}
                self.processed_uids = {}
                self.processed_groupnames = {}
                self.processed_gids = {}

                self.processed_refcount_paths = {}
                self.processed_refcount_legacy_pkgs = {}

                self.processed_overlays = {}

                # mark which paths we've done duplicate-type checking on
                self.seen_dup_types = {}
                self.seen_mediated_links = []

                super(PkgDupActionChecker, self).__init__(config)

        def startup(self, engine):
                """Called to initialise a given checker using the supplied
                    engine."""

                def seed_dict(mf, attr, dic, atype=None, verbose=False):
                        """Updates a dictionary of { attr: [(fmri, action), ..]}
                        where attr is the value of that attribute from
                        actions of a given type atype, in the given
                        manifest."""

                        pkg_vars = mf.get_all_variants()

                        def mf_gen(atype):
                                if atype:
                                        for a in mf.gen_actions_by_type(atype):
                                                yield a
                                else:
                                        for a in mf.gen_actions():
                                                yield a

                        for action in mf_gen(atype):
                                if atype and action.name != atype:
                                        continue
                                if attr not in action.attrs:
                                        continue

                                variants = action.get_variant_template()
                                variants.merge_unknown(pkg_vars)
                                # Action attributes must be lists or strings.
                                for k, v in six.iteritems(variants):
                                        if isinstance(v, set):
                                                action.attrs[k] = list(v)
                                        else:
                                                action.attrs[k] = v

                                p = action.attrs[attr]
                                if p not in dic:
                                        dic[p] = [(mf.fmri, action)]
                                else:
                                        dic[p].append((mf.fmri, action))

                # construct a set of FMRIs being presented for linting, and
                # avoid seeding the reference dictionary for any packages
                # that have new versions available in the lint repository, or
                # lint manifests given on the command line.
                lint_fmris = {}
                for m in engine.gen_manifests(engine.lint_api_inst,
                    release=engine.release, pattern=engine.pattern):
                        lint_fmris.setdefault(
                            m.fmri.get_name(), []).append(m.fmri)
                for m in engine.lint_manifests:
                        lint_fmris.setdefault(
                            m.fmri.get_name(), []).append(m.fmri)

                engine.logger.debug(
                    _("Seeding reference action duplicates dictionaries."))

                for manifest in engine.gen_manifests(engine.ref_api_inst,
                    release=engine.release):
                        # Only put this manifest into the reference dictionary
                        # if it's not an older version of the same package.
                        if any(
                            lint_fmri_successor(fmri, manifest.fmri)
                            for fmri
                            in lint_fmris.get(manifest.fmri.get_name(), [])
                        ):
                                continue
                        else:
                                seed_dict(manifest, "path", self.ref_paths)
                                seed_dict(manifest, "pkg", self.ref_legacy_pkgs,
                                    atype="legacy")
                                seed_dict(manifest, "name", self.ref_drivers,
                                    atype="driver")
                                seed_dict(manifest, "username",
                                    self.ref_usernames, atype="user")
                                seed_dict(manifest, "uid", self.ref_uids,
                                    atype="user")
                                seed_dict(manifest, "groupname",
                                    self.ref_groupnames, atype="group")
                                seed_dict(manifest, "gid", self.ref_gids,
                                    atype="group")

                engine.logger.debug(
                    _("Seeding lint action duplicates dictionaries."))

                # we provide a search pattern, to allow users to lint a
                # subset of the packages in the lint_repository
                for manifest in engine.gen_manifests(engine.lint_api_inst,
                    release=engine.release, pattern=engine.pattern):
                        seed_dict(manifest, "path", self.lint_paths)
                        seed_dict(manifest, "pkg", self.lint_legacy_pkgs,
                            atype="legacy")
                        seed_dict(manifest, "name", self.lint_drivers,
                            atype="driver")
                        seed_dict(manifest, "username", self.lint_usernames,
                            atype="user")
                        seed_dict(manifest, "uid", self.lint_uids, atype="user")
                        seed_dict(manifest, "groupname", self.lint_groupnames,
                            atype="group")
                        seed_dict(manifest, "gid", self.lint_gids,
                            atype="group")

                engine.logger.debug(
                    _("Seeding local action duplicates dictionaries."))

                for manifest in engine.lint_manifests:
                        seed_dict(manifest, "path", self.lint_paths)
                        seed_dict(manifest, "pkg", self.lint_legacy_pkgs,
                            atype="legacy")
                        seed_dict(manifest, "name", self.lint_drivers,
                            atype="driver")
                        seed_dict(manifest, "username", self.lint_usernames,
                            atype="user")
                        seed_dict(manifest, "uid", self.lint_uids, atype="user")
                        seed_dict(manifest, "groupname", self.lint_groupnames,
                            atype="group")
                        seed_dict(manifest, "gid", self.lint_gids,
                            atype="group")

                dup_dictionaries = [(self.lint_paths, self.ref_paths),
                    (self.lint_legacy_pkgs, self.ref_legacy_pkgs),
                    (self.lint_drivers, self.ref_drivers),
                    (self.lint_usernames, self.ref_usernames),
                    (self.lint_uids, self.ref_uids),
                    (self.lint_groupnames, self.ref_groupnames),
                    (self.lint_gids, self.ref_gids)]

                for lint_dic, ref_dic in dup_dictionaries:
                        self._merge_dict(lint_dic, ref_dic,
                            ignore_pubs=engine.ignore_pubs)
                        self.lint_dic = {}

        def duplicate_paths(self, action, manifest, engine, pkglint_id="001"):
                """Checks for duplicate paths on non-ref-counted actions."""

                self.dup_attr_check(["file", "license"], "path", self.ref_paths,
                    self.processed_paths, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id)

        duplicate_paths.pkglint_desc = _(
            "Paths should be unique.")

        def duplicate_drivers(self, action, manifest, engine, pkglint_id="002"):
                """Checks for duplicate driver names."""

                self.dup_attr_check(["driver"], "name", self.ref_drivers,
                    self.processed_drivers, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id)

        duplicate_drivers.pkglint_desc = _("Driver names should be unique.")

        def duplicate_usernames(self, action, manifest, engine,
            pkglint_id="003"):
                """Checks for duplicate user names."""

                self.dup_attr_check(["user"], "username", self.ref_usernames,
                    self.processed_usernames, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id)

        duplicate_usernames.pkglint_desc = _("User names should be unique.")

        def duplicate_uids(self, action, manifest, engine, pkglint_id="004"):
                """Checks for duplicate uids."""

                self.dup_attr_check(["user"], "uid", self.ref_uids,
                    self.processed_uids, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id)

        duplicate_uids.pkglint_desc = _("UIDs should be unique.")

        def duplicate_groupnames(self, action, manifest, engine,
            pkglint_id="005"):
                """Checks for duplicate group names."""

                self.dup_attr_check(["group"], "groupname", self.ref_groupnames,
                    self.processed_groupnames, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id)

        duplicate_groupnames.pkglint_desc = _(
            "Group names should be unique.")

        def duplicate_gids(self, action, manifest, engine, pkglint_id="006"):
                """Checks for duplicate gids."""

                self.dup_attr_check(["group"], "name", self.ref_gids,
                    self.processed_gids, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id)

        duplicate_gids.pkglint_desc = _("GIDs should be unique.")

        def duplicate_refcount_path_attrs(self, action, manifest, engine,
            pkglint_id="007"):
                """Checks that for duplicated reference-counted actions,
                all attributes in those duplicates are the same."""

                if not action.refcountable:
                        return

                for attr, ref_dic, processed_dic in [
                    ("path", self.ref_paths, self.processed_refcount_paths),
                    ("pkg", self.ref_legacy_pkgs,
                    self.processed_refcount_legacy_pkgs)]:
                        p = action.attrs.get(attr, None)
                        if not p:
                                continue

                        if p in ref_dic and len(ref_dic[p]) == 1:
                                continue

                        if p in processed_dic:
                                continue

                        lint_id = "{0}{1}".format(self.name, pkglint_id)

                        fmris = set()
                        targ = action
                        differences = set()
                        for (pfmri, a) in ref_dic[p]:
                                if engine.linted(action=a, manifest=manifest,
                                    lint_id=lint_id):
                                        continue
                                fmris.add(pfmri)

                                for key in a.differences(targ):
                                        # we allow certain attribute values to
                                        # differ. Mediated-link validation is
                                        # provided by mediated_links(..).
                                        if key.startswith("variant") or \
                                            key.startswith("facet") or \
                                            key.startswith("mediator") or \
                                            key.startswith("target") or \
                                            key.startswith("pkg.linted"):
                                                continue

                                        conflict_vars, conflict_actions = \
                                            self.conflicting_variants([a, targ],
                                                manifest.get_all_variants())
                                        if not conflict_actions:
                                                continue
                                        differences.add(key)
                        suspects = []

                        if differences:
                                action_types = set()
                                for key in sorted(differences):
                                        # a dictionary to map unique values for
                                        # this key the fmris that deliver them
                                        attr = {}
                                        for (pfmri, a) in ref_dic[p]:
                                                if engine.linted(action=a,
                                                    manifest=manifest,
                                                    lint_id=lint_id):
                                                        continue

                                                action_types.add(a.name)
                                                if key in a.attrs:
                                                        val = a.attrs[key]
                                                        if val in attr:
                                                                attr[val].append(pfmri)
                                                        else:
                                                                attr[val] = \
                                                                    [pfmri]
                                        for val in sorted(attr):
                                                suspects.append(
                                                    "{0}: {1} -> {2}".format(
                                                    key, val,
                                                    " ".join([pfmri.get_name()
                                                    for pfmri in
                                                    sorted(attr[val])
                                                    ])))

                                # if we deliver different action types, that
                                # gets dealt with by duplicate_path_types().
                                if len(action_types) != 1:
                                        processed_dic[p] = True
                                        continue

                                engine.error(_("{type} action for {attr} "
                                    "is reference-counted but has different "
                                    "attributes across {count} duplicates: "
                                    "{suspects}").format(
                                    type=action.name,
                                    attr=p,
                                    count=len(fmris),
                                    suspects=
                                    " ".join([key for key in suspects])),
                                    msgid=lint_id, ignore_linted=True)
                        processed_dic[p] = True

        duplicate_refcount_path_attrs.pkglint_desc = _(
            "Duplicated reference counted actions should have the same attrs.")

        def dup_attr_check(self, action_names, attr_name, ref_dic,
            processed_dic, action, engine, pkg_vars, msgid="",
            only_overlays=False):
                """This method does generic duplicate action checking where
                we know the type of action and name of an action attributes
                across actions/manifests that should not be duplicated.

                'action_names' A list of the type of actions to check

                'attr_name' The attribute name we're checking

                'ref_dic' Built in setup() this dictionary maps attr_name values
                to a list of all (fmri, action) tuples that deliver that
                attr_name value.

                'processed_dic' Records whether we've already called this method
                for a given attr_name value

                'action' The current action we're checking

                'engine' The LintEngine calling this method

                'msgid' The pkglint_id to use when logging messages.

                'only_overlays' Only report about misuse of the 'overlay'
                attribute for file actions."""

                if attr_name not in action.attrs:
                        return

                if action.name not in action_names:
                        return

                name = action.attrs[attr_name]

                if name in processed_dic:
                        return

                if name in ref_dic and len(ref_dic[name]) == 1:
                        return

                fmris = set()
                actions = set()
                for (pfmri, a) in ref_dic[name]:
                        # mediated links get ignored here
                        if a.name in ["link", "hardlink"] and \
                            "mediator" in a.attrs:
                                continue
                        actions.add(a)
                        fmris.add(pfmri)

                conflict_vars, conflict_actions = \
                    self.conflicting_variants(actions, pkg_vars)

                # prune out any valid overlay file action-pairs.
                if attr_name == "path" and action.name == "file":
                        conflict_actions, errors = self._prune_overlays(
                            conflict_actions, ref_dic, pkg_vars)
                        if only_overlays:
                                for error, sub_id in errors:
                                        engine.error(error,
                                            msgid="{0}{1}.{2}".format(
                                            self.name, msgid, sub_id))
                                processed_dic[name] = True
                                return

                        if conflict_actions:
                                 conflict_vars, conflict_actions = \
                                        self.conflicting_variants(actions,
                                            pkg_vars)
                if conflict_actions:
                        plist = [f.get_fmri() for f in sorted(fmris)]

                        if not conflict_vars:
                                engine.error(_("{attr_name} {name} is "
                                    "a duplicate delivered by {pkgs} "
                                    "under all variant combinations").format(
                                    attr_name=attr_name,
                                    name=name,
                                    pkgs=" ".join(plist)),
                                    msgid="{0}{1}.1".format(self.name, msgid))
                        else:
                                for fz in conflict_vars:
                                        engine.error(_("{attr_name} {name} "
                                            "is a duplicate delivered by "
                                            "{pkgs} declaring overlapping "
                                            "variants {vars}").format(
                                            attr_name=attr_name,
                                            name=name,
                                            pkgs=" ".join(plist),
                                            vars=
                                            " ".join(["{0}={1}".format(k, v)
                                                for (k, v)
                                                in sorted(fz)])),
                                            msgid="{0}{1}.2".format(self.name,
                                                msgid))
                processed_dic[name] = True

        def duplicate_path_types(self, action, manifest, engine,
            pkglint_id="008"):
                """Checks to see if the action containing a path attribute
                has that action delivered by multiple action types."""

                if "path" not in action.attrs:
                        return

                p = action.attrs["path"]

                if p in self.seen_dup_types:
                        return

                lint_id = "{0}{1}".format(self.name, pkglint_id)
                types = set()
                fmris = set()
                actions = set()
                for (pfmri, a) in self.ref_paths[p]:
                        if engine.linted(action=a, manifest=manifest,
                            lint_id=lint_id):
                                continue
                        # we deal with mediated links in mediated_links(..)
                        # since self.conflicting_variants() would otherwise flag
                        # these as conflicting
                        if a.name in ["link", "hardlink"] and \
                            "mediator" in a.attrs:
                                continue
                        actions.add(a)
                        types.add(a.name)
                        fmris.add(pfmri)

                if len(types) > 1:
                        conflict_vars, conflict_actions = \
                            self.conflicting_variants(actions,
                                manifest.get_all_variants())
                        if conflict_actions:
                                plist = [f.get_fmri() for f in sorted(fmris)]
                                plist.sort()
                                engine.error(
                                    _("path {path} is delivered by multiple "
                                    "action types across {pkgs}").format(
                                    path=p,
                                    pkgs=
                                    " ".join(plist)),
                                    msgid=lint_id, ignore_linted=True)
                self.seen_dup_types[p] = True

        duplicate_path_types.pkglint_desc = _(
            "Paths should be delivered by one action type only.")

        def overlays(self, action, manifest, engine, pkglint_id="009"):
                """Checks that any duplicate file actions which specify overlay
                attributes do so according to the rules.

                Much of the implementation here is done by _prune_overlays(..),
                called by dup_attr_check."""

                if action.name != "file":
                        return

                self.dup_attr_check(["file"], "path", self.ref_paths,
                    self.processed_overlays, action, engine,
                    manifest.get_all_variants(), msgid=pkglint_id,
                    only_overlays=True)

        overlays.pkglint_desc = _("Overlaying actions should be valid.")

        def mediated_links(self, action, manifest, engine, pkglint_id="010"):
                """Checks that groups of mediated-links are valid.  We perform
                minimal validation of mediated links here, since the generic
                action-validation check, pkglint.action009, will run the
                validate() method on each action.

                We check that all mediators for a given path are part of the
                same mediation namespace, and that all links for a given path
                have a 'mediator' attribute to declare that namespace.  We also
                check, that if mediators are being used, that all actions
                deliver the same type of action for that mediated link.

                There is some overlap with duplicate_path_types here,
                in that duplicate reference-counted actions with a path
                attribute where that list of actions contains link or hardlink
                actions will be reported here instead, in case the user simply
                got the type of action wrong.
                """

                if action.name not in ["link", "hardlink"]:
                        return

                # a link without a path will get picked up elsewhere
                p = action.attrs.get("path", None)
                if not p:
                        return

                if p in self.seen_mediated_links:
                        return

                if len(self.ref_paths[p]) == 1:
                        return

                ref_mediator = action.attrs.get("mediator", None)
                different_namespaces = []
                missing_mediators = []

                types_id = "{0}{1}.1".format(self.name, pkglint_id)
                missing_id = "{0}{1}.2".format(self.name, pkglint_id)
                diff_id = "{0}{1}.3".format(self.name, pkglint_id)

                # gather the actions and their fmris that have either
                # different namespaces, or missing mediators.  We ignore
                # variants at this point.
                for pfmri, action in self.ref_paths[p]:
                        mediator = action.attrs.get("mediator", None)
                        if not mediator:
                                if engine.linted(action, lint_id=missing_id):
                                        continue
                                missing_mediators.append((pfmri, action))
                        elif mediator != ref_mediator:
                                if engine.linted(action, lint_id=diff_id):
                                        continue
                                different_namespaces.append((pfmri, action))

                def variant_conflicts(mediator_list, lint_id):
                        """Look for conflicting variants across the given list,
                        allowing for pkg.linted values matching lint_id."""
                        conflicts = []
                        for pfmri, action in mediator_list:
                                # compare every action for this path to see if
                                # we have at least one variant conflict.  We
                                # need to do this individually since
                                # conflicting_variants(..) isn't mediator-aware
                                for pfm, ac in self.ref_paths[p]:
                                        if ac == action:
                                                continue
                                        if engine.linted(ac, lint_id=lint_id):
                                                continue
                                        conf_var, conf_ac = \
                                            self.conflicting_variants(
                                                [ac, action], {})
                                        for conf in conf_ac:
                                                conflicts.append((pfm, conf))
                        return conflicts

                action_types = set([])

                seen_conflicts = variant_conflicts(different_namespaces,
                    diff_id)
                if seen_conflicts:
                        plist = []
                        for pfmri, action in seen_conflicts:
                                plist.append(str(pfmri))
                                action_types.add((action, pfmri))

                        plist = sorted(set(plist))
                        engine.error(_("path {path} uses different "
                            "mediator namespaces across actions in "
                            "{fmris}").format(fmris=" ".join(plist),
                            path=p), msgid=diff_id)

                if missing_mediators:
                        seen_conflicts = variant_conflicts(missing_mediators,
                            missing_id)
                        if seen_conflicts:
                                plist = []
                                ac_names = set([])
                                for pfmri, action in seen_conflicts:
                                        plist.append(str(pfmri))
                                        action_types.add((action, pfmri))
                                        ac_names.add(action.name)

                                # if we have more than one action type, then
                                # this error would only confuse. A user
                                # mixing 'dir' and 'link' actions should not
                                # be advised that adding a 'mediator' attribute
                                # to their dir action would fix things.
                                if len(ac_names) == 1:
                                        plist = sorted(set(plist))
                                        engine.error(_("path {path} has "
                                            "missing mediator attributes "
                                            "across actions in {fmris}").format(
                                            fmris=" ".join(plist),
                                            path=p), msgid=missing_id)

                if len(set([ac.name for ac, pfmri in action_types])) > 1:
                        plist = set([])
                        for ac, pfmri in action_types:
                                if not engine.linted(ac, lint_id=types_id):
                                        plist.add(str(pfmri))
                        if not plist:
                                self.seen_mediated_links.append(p)
                                return
                        plist = sorted(plist)
                        engine.error(_("path {path} uses multiple action "
                            "types for potentially mediated links across "
                            "actions in {fmris}").format(fmris=" ".join(plist),
                            path=p), msgid=types_id)

                self.seen_mediated_links.append(p)

        mediated_links.pkglint_desc = _("Mediated-links should be valid.")

        def _merge_dict(self, src, target, ignore_pubs=True):
                """Merges the given src dictionary into the target
                dictionary, giving us the target content as it would appear,
                were the packages in src to get published to the
                repositories that made up target.

                We need to only merge packages at the same or successive
                version from the src dictionary into the target dictionary.
                If the src dictionary contains a package with no version
                information, it is assumed to be more recent than the same
                package with no version in the target."""

                for p in src:
                        if p not in target:
                                target[p] = src[p]
                                continue

                        def build_dic(arr):
                                """Builds a dictionary of fmri:action entries"""
                                dic = {}
                                for (pfmri, action) in arr:
                                        if pfmri in dic:
                                                dic[pfmri].append(action)
                                        else:
                                                dic[pfmri] = [action]
                                return dic

                        src_dic = build_dic(src[p])
                        targ_dic = build_dic(target[p])

                        for src_pfmri in src_dic:
                                # we want to remove entries deemed older than
                                # src_pfmri from targ_dic.
                                for targ_pfmri in targ_dic.copy():
                                        sname = src_pfmri.get_name()
                                        tname = targ_pfmri.get_name()
                                        if lint_fmri_successor(src_pfmri,
                                            targ_pfmri,
                                            ignore_pubs=ignore_pubs):
                                                targ_dic.pop(targ_pfmri)
                        targ_dic.update(src_dic)
                        l = []
                        for pfmri in targ_dic:
                                for action in targ_dic[pfmri]:
                                        l.append((pfmri, action))
                        target[p] = l

        def _prune_overlays(self, actions, ref_dic, pkg_vars):
                """Given a list of file actions that all deliver to the same
                path, return that list minus any actions that are attempting to
                use overlays. Also return a list of tuples containing any
                overlay-related errors encountered, in the the format:

                    [ (<error msg>, <id>), ... ]

                """

                if not actions:
                        return [], []

                path = actions[0].attrs["path"]
                # action_fmris is a list of (fmri, action) tuples
                action_fmris = ref_dic[path]
                # When printing errors, we emit all FMRIs that are taking part
                # in the duplication of this path.
                fmris = sorted(set(
                    [str(fmri) for fmri, action in action_fmris]))

                def _remove_attrs(action):
                        """returns a string representation of the given action
                        with all non-variant attributes other than path and
                        overlay removed. Used for comparison of overlay actions.
                        """
                        action_copy = copy.deepcopy(action)
                        for key in action_copy.attrs.keys():
                                if key in ["path", "overlay"]:
                                        continue
                                elif key.startswith("variant"):
                                        continue
                                else:
                                        del action_copy.attrs[key]
                        return str(action_copy)

                def _get_fmri(action, action_fmris):
                        """return the fmri for a given action."""
                        for fmri, ac in action_fmris:
                                if action == ac:
                                        return fmri

                # buckets for actions according to their overlay attribute value
                # any actions that do not specify overlay attributes, or use
                # them incorrectly get put into ret_actions, and returned for
                # our generic duplicate-attribute code to deal with.
                allow_overlay = []
                overlay = []
                ret_actions = []

                errors = set()

                # sort our list of actions into the corresponding bucket
                for action in actions:
                        overlay_attr = action.attrs.get("overlay", None)
                        if overlay_attr and overlay_attr == "allow":
                                if not action.attrs.get("preserve", None):
                                        errors.add(
                                            (_("path {path} missing "
                                            "'preserve' attribute for "
                                            "'overlay=allow' action "
                                            "in {fmri}").format(path=path,
                                            fmri=_get_fmri(
                                            action, action_fmris)), "1"))
                                else:
                                        allow_overlay.append(action)

                        elif overlay_attr and overlay_attr == "true":
                                overlay.append(action)
                        else:
                                ret_actions.append(action)

                if not (overlay or allow_overlay):
                        return actions, []

                def _render_variants(conflict_vars):
                        """pretty print a group of variants"""
                        vars = set()
                        for group in conflict_vars:
                                for key, val in group:
                                        vars.add("{0}={1}".format(key, val))
                        return ", ".join(list(vars))

                def _unique_attrs(action):
                        """return a dictionary containing only attrs that must
                        be unique across overlay actions."""
                        attrs = {}
                        for key in FileAction.unique_attrs:
                                if key == "preserve":
                                        continue
                                attrs[key] = action.attrs.get(key, None)
                        return attrs

                # Ensure none of the groups of overlay actions have
                # conflicting variants within them.
                conflict_vars, conflict_overlays = self.conflicting_variants(
                    overlay, pkg_vars)
                if conflict_vars:
                        errors.add(
                            (_("path {path} has duplicate 'overlay=true' "
                            "actions for the following variants across across "
                            "{fmris}: {var}").format(
                            path=path, fmris=", ".join(list(fmris)),
                            var=_render_variants(conflict_vars)), "2"))

                # verify that if we're only delivering overlay=allow actions,
                # none of them conflict with each other (we check corresponding
                # overlay=true actions, if any, later)
                if not overlay:
                        conflict_vars, conflict_overlays = \
                            self.conflicting_variants(allow_overlay, pkg_vars)
                        if conflict_vars:
                                errors.add(
                                    (_("path {path} has duplicate "
                                    "'overlay=allow' actions for the following "
                                    "variants across across "
                                    "{fmris}: {var}").format(
                                    path=path, fmris=", ".join(
                                    list(fmris)),
                                    var=_render_variants(conflict_vars)),
                                    "3"))

                # Check for valid, complimentary sets of overlay and
                # allow_overlay actions.
                seen_mismatch = False
                for a1 in overlay:
                        # Our assertions on how to detect clashing overlay +
                        # allow_overlay actions:
                        #
                        # 1. each overlay action must have at least one conflict
                        #    from the set of allow_overlay actions.
                        #
                        # 2. from that set of conflicts, when we remove the
                        #    overlay action itself, there must be no conflicts
                        #    within that set of overlay=allow actions.
                        #
                        # 3. all attributes required to be the same between
                        #    complimentary sets of allow_overlay and overlay
                        #    actions are the same.

                        conflict_vars, conflict_actions = \
                            self.conflicting_variants([a1] + allow_overlay,
                            pkg_vars)

                        if conflict_actions:
                                conflict_actions.remove(a1)
                                conflict_vars_sub, conflict_actions_allow = \
                                    self.conflicting_variants(conflict_actions,
                                    pkg_vars)

                                if conflict_actions_allow:
                                        errors.add(
                                            (_("path {path} uses "
                                            "overlay='true' actions but has "
                                            "duplicate 'overlay=allow' actions "
                                            "for the following variants across "
                                            "{fmris}: {vars}").format(
                                            path=path,
                                            fmris=", ".join(list(fmris)),
                                            vars=_render_variants(
                                            conflict_vars_sub)), "4"))
                                else:
                                        # check that none of the attributes
                                        # required to be the same between
                                        # overlay and allow actions differ.
                                        a1_attrs = _unique_attrs(a1)
                                        for a2 in conflict_actions:
                                                if a1_attrs != _unique_attrs(
                                                    a2):
                                                        seen_mismatch = True
                        else:
                                errors.add(
                                    (_("path {path} uses 'overlay=true' "
                                    "actions but has no corresponding "
                                    "'overlay=allow' actions across {fmris}"
                                    ).format(
                                    path=path, fmris=", ".join(
                                    list(fmris))), "5"))

                if seen_mismatch:
                        errors.add(
                            (_("path {path} has mismatching attributes for "
                            "'overlay=true' and 'overlay=allow' action-pairs "
                            "across {fmris}").format(path=path,
                            fmris=", ".join(list(fmris))), "6"))

                if (overlay or allow_overlay) and ret_actions:
                        errors.add(
                            (_("path {path} has both overlay and non-overlay "
                            "actions across {fmris}").format(
                            path=path, fmris=", ".join(list(fmris))),
                            "7"))

                return ret_actions, errors

        def dir_parents(self, action, manifest, engine, pkglint_id="011"):
                """Checks that if any paths are delivered by this action, and
                if we know about the parent path, that parent must be a
                directory."""

                if "path" not in action.attrs:
                        return
                path = action.attrs["path"]
                parent_path = os.path.dirname(path)
                parents = self.ref_paths.get(parent_path, None)
                if not parents:
                        return
                for parent_pfmri, parent_action in parents:
                        if parent_action.name == "dir":
                                continue
                        # check for conflicting variants - if the parent and
                        # child paths can't be installed together, then this
                        # is allowed.
                        conflict_vars, conflict_actions = \
                            self.conflicting_variants([action, parent_action],
                            manifest.get_all_variants())
                        if not conflict_actions:
                                continue
                        engine.error(_("Expecting a dir action for "
                            "{parent_path}, but {parent_fmri} delivers it "
                            "as a {parent_type}. {child_path} is delivered "
                            "by {child_fmri}").format(
                            parent_path=parent_path,
                            parent_fmri=parent_pfmri,
                            parent_type=parent_action.name,
                            child_path=path,
                            child_fmri=manifest.fmri),
                            "{0}{1}".format(self.name, pkglint_id))

        dir_parents.pkglint_desc = _("Parent paths should be directories.")


class PkgActionChecker(base.ActionChecker):

        name = "pkglint.action"

        def __init__(self, config):
                self.description = _("Various checks on actions")

                # a list of fmris which were declared as dependencies, but
                # which we weren't able to locate a manifest for.
                self.missing_deps = []

                # maps package names to tuples of (obsolete, fmri) values where
                # 'obsolete' is a boolean, True if the package is obsolete
                self.obsolete_pkgs = {}
                super(PkgActionChecker, self).__init__(config)

        def startup(self, engine):
                """Cache all manifest FMRIs, tracking whether they're
                obsolete or not."""


                def seed_obsolete_dict(mf, dic):
                        """Updates a dictionary of { pkg_name: ObsoleteFmri }
                        items, tracking which were marked as obsolete."""

                        name = mf.fmri.get_name()

                        if "pkg.obsolete" in mf and \
                            mf["pkg.obsolete"].lower() == "true":
                                dic[name] = ObsoleteFmri(True, mf.fmri)
                        elif "pkg.renamed" not in mf or \
                            mf["pkg.renamed"].lower() == "false":
                                # we can't yet tell if a renamed
                                # package gets obsoleted further down
                                # its rename chain, so don't decide now
                                dic[name] = ObsoleteFmri(False, mf.fmri)

                engine.logger.debug(_("Seeding reference action dictionaries."))
                for manifest in engine.gen_manifests(engine.ref_api_inst,
                    release=engine.release):
                        seed_obsolete_dict(manifest, self.obsolete_pkgs)

                engine.logger.debug(_("Seeding lint action dictionaries."))
                # we provide a search pattern, to allow users to lint a
                # subset of the packages in the lint_repository
                for manifest in engine.gen_manifests(engine.lint_api_inst,
                    release=engine.release, pattern=engine.pattern):
                        seed_obsolete_dict(manifest, self.obsolete_pkgs)

                engine.logger.debug(_("Seeding local action dictionaries."))
                for manifest in engine.lint_manifests:
                        seed_obsolete_dict(manifest, self.obsolete_pkgs)

        def underscores(self, action, manifest, engine, pkglint_id="001"):
                """In general, pkg(5) discourages the use of underscores in
                attributes."""

                for key in action.attrs.keys():
                        if "_" in key:
                                if key in ["original_name", "refresh_fmri",
                                    "restart_fmri", "suspend_fmri",
                                    "disable_fmri", "clone_perms"] or \
                                        key.startswith("facet.locale.") or \
                                        key.startswith("facet.version-lock."):
                                        continue
                                engine.warning(
                                    _("underscore in attribute name {key} in "
                                    "{fmri}").format(
                                    key=key,
                                    fmri=manifest.fmri),
                                    msgid="{0}{1}.1".format(self.name,
                                    pkglint_id))

                if action.name != "set":
                        return

                name = action.attrs["name"]

                if "_" not in name:
                        return

                obs_map = {
                    "info.maintainer_url": "info.maintainer-url",
                    "info.upstream_url": "info.upstream-url",
                    "info.source_url": "info.source-url",
                    "info.repository_url": "info.repository-url",
                    "info.repository_changeset": "info.repository-changeset",
                    "info.defect_tracker.url": "info.defect-tracker.url",
                    "opensolaris.arc_url": "org.opensolaris.caseid"
                }

                # These names are deprecated, and so we warn, but we're a tiny
                # bit nicer about it.
                if name in obs_map:
                        engine.warning(_("underscore in obsolete 'set' action "
                            "name {name} should be {new} in {fmri}").format(
                                name=name,
                                new=obs_map[name],
                                fmri=manifest.fmri
                           ),
                            msgid="{0}{1}.3".format(self.name, pkglint_id))
                        return

                engine.warning(_("underscore in 'set' action name {name} in "
                    "{fmri}").format(name=name,
                    fmri=manifest.fmri),
                    msgid="{0}{1}.2".format(self.name, pkglint_id))

        underscores.pkglint_desc = _(
            "Underscores are discouraged in action attributes.")

        def unusual_perms(self, action, manifest, engine, pkglint_id="002"):
                """Checks that the permissions in this action look sane."""

                if "mode" in action.attrs:
                        mode = action.attrs["mode"]
                        path = action.attrs["path"]
                        st = None
                        try:
                                st = stat.S_IMODE(int(mode, 8))
                        except ValueError:
                                pass

                        if action.name == "dir":
                                # check for at least one executable bit
                                if st and \
                                    (stat.S_IXUSR & st or stat.S_IXGRP & st
                                    or stat.S_IXOTH & st):
                                        pass
                                elif st:
                                        engine.warning(_("directory action for "
                                            "{path} delivered in {pkg} with "
                                            "mode={mode} "
                                            "that has no executable bits").format(
                                            path=path,
                                            pkg=manifest.fmri,
                                            mode=mode),
                                            msgid="{0}{1}.1".format(
                                            self.name, pkglint_id))

                        if not st:
                                engine.error(_("broken mode mode={mode} "
                                    "delivered in action for {path} in "
                                    "{pkg}").format(
                                    path=path,
                                    pkg=manifest.fmri,
                                    mode=mode),
                                    msgid="{0}{1}.2".format(self.name,
                                    pkglint_id))

                        if len(mode) < 3:
                                engine.error(_("mode={mode} is too short in "
                                    "action for {path} in {pkg}").format(
                                    path=path,
                                    pkg=manifest.fmri,
                                    mode=mode),
                                    msgid="{0}{1}.3".format(self.name,
                                    pkglint_id))
                                return

                        # now check for individual access permissions
                        user = mode[-3]
                        group = mode[-2]
                        other = mode[-1]

                        if (other > group or
                            group > user or
                            other > user):
                                engine.warning(_("unusual mode mode={mode} "
                                    "delivered in action for {path} in "
                                    "{pkg}").format(
                                    path=path,
                                    pkg=manifest.fmri,
                                    mode=mode),
                                    msgid="{0}{1}.4".format(self.name,
                                    pkglint_id))

        unusual_perms.pkglint_desc = _(
            "Paths should not have unusual permissions.")

        def legacy(self, action, manifest, engine, pkglint_id="003"):
                """Cross-check that the 'pkg' attribute points to a package
                that depends on the package containing this legacy action.
                Also check that all the required tags are present on this
                legacy action."""

                if action.name != "legacy":
                        return

                name = manifest.fmri.get_name()

                for required in [ "category", "desc", "hotline", "name",
                    "pkg", "vendor", "version" ]:
                        if required not in action.attrs:
                                engine.error(
                                    _("{attr} missing from legacy "
                                    "action in {pkg}").format(
                                    attr=required,
                                    pkg=manifest.fmri),
                                    msgid="{0}{1}.1".format(self.name,
                                    pkglint_id))

                if "pkg" in action.attrs:

                        legacy = engine.get_manifest(action.attrs["pkg"],
                            search_type=engine.LATEST_SUCCESSOR)
                        # Some legacy ancestor packages never existed as pkg(5)
                        # stubs
                        if legacy:
                                self.check_legacy_rename(legacy, action,
                                    manifest, engine, pkglint_id)

                if "version" in action.attrs:
                        # this could be refined
                        if "REV=" not in action.attrs["version"]:
                                engine.warning(
                                    _("legacy action in {0} does not "
                                    "contain a REV= string").format(
                                    manifest.fmri),
                                    msgid="{0}{1}.3".format(self.name,
                                    pkglint_id))

        def check_legacy_rename(self, legacy, action, manifest, engine,
            lint_id):
                """Part of the legacy(..) check, not an individual check.
                Given a legacy action, if the package pointed to by the 'pkg'
                attribute of that action exists (say pkg=SUNWlegacy), we check
                that a user who types:

                pkg install SUNWlegacy

                gets the package containing the legacy action installed on their
                system, possibly following renames along the way.

                legacy          A package manifest with the same name as the
                                'pkg' attribute of the legacy action
                action          The legacy action we're investigating
                manifest        The manifest we're investigating
                engine          Our lint engine
                lint_id         The id of this check
                """

                if "pkg.renamed" in legacy and \
                    legacy["pkg.renamed"].lower() == "true":
                        mf = None
                        try:
                                mf = engine.follow_renames(action.attrs["pkg"],
                                    target=manifest.fmri, old_mfs=[],
                                    legacy=True)
                        except base.LintException as e:
                                # we've tried to rename to ourselves
                                engine.error(
                                    _("legacy renaming: {0}").format(str(e)),
                                    msgid="{0}{1}.5".format(self.name, lint_id))
                                return

                        if mf is None:
                                engine.error(_("legacy package {legacy} did "
                                    "not result in a dependency on {pkg} when"
                                    " following package renames").format(
                                    legacy=legacy.fmri,
                                    pkg=manifest.fmri),
                                    msgid="{0}{1}.4".format(
                                    self.name, lint_id))

                        elif not lint_fmri_successor(manifest.fmri, mf.fmri,
                            ignore_pubs=engine.ignore_pubs):
                                engine.error(_("legacy package {legacy} did "
                                    "not result in a dependency on {pkg}").format(
                                    legacy=legacy.fmri,
                                    pkg=manifest.fmri),
                                    msgid="{0}{1}.2".format(
                                    self.name, lint_id))

        legacy.pkglint_desc = _(
            "'legacy' actions should have valid attributes.")

        def unknown(self, action, manifest, engine, pkglint_id="004"):
                """We should never have actions called 'unknown'."""

                if action.name is "unknown":
                        engine.error(_("unknown action found in {0}").format(
                            manifest.fmri),
                            msgid="{0}{1}".format(self.name, pkglint_id))

        unknown.pkglint_desc = _("'unknown' actions should never occur.")

        def dep_obsolete(self, action, manifest, engine, pkglint_id="005"):
                """We should not have a require dependency on a package that has
                been marked as obsolete.

                This check also produces warnings when it is unable to find
                manifests marked as dependencies for a given package in order
                to check for their obsoletion.  This can help to detect errors
                in the fmri attribute field of the depend action, though can be
                noisy if all dependencies are intentionally not present in the
                repository being linted or referenced.

                The pkglint paramter pkglint.action005.1.missing-deps can be
                used to declare which fmris we know could be missing, and for
                which we should not emit a warning message if those manifests
                are not available.
                """

                msg = _("dependency on obsolete package in {0}:")

                if action.name != "depend":
                        return

                if action.attrs["type"] != "require":
                        return

                # We check for renames as part of pkglint.manifest002.5, so
                # don't do that here.
                if "pkg.renamed" in manifest and \
                    manifest["pkg.renamed"].lower() == "true":
                        return

                name = None
                declared_fmri = None
                dep_fmri = action.attrs["fmri"]

                # normalize the fmri
                if not dep_fmri.startswith("pkg:/"):
                        dep_fmri = "pkg:/{0}".format(dep_fmri)

                try:
                        declared_fmri = pkg.fmri.PkgFmri(dep_fmri)
                        name = declared_fmri.get_name()
                except pkg.fmri.IllegalFmri:
                        try:
                                declared_fmri = pkg.fmri.PkgFmri(dep_fmri)
                                name = declared_fmri.get_name()
                        except:
                                # A very broken fmri value - we'll give up now.
                                # valid_fmri() will pick up the trail from here.
                                return

                # if we've been unable to find a dependency for a given
                # fmri in the past, no need to keep complaining about it
                if dep_fmri in self.missing_deps:
                        return

                # There's a good chance that dependencies can be satisfied from
                # the manifests we cached during startup() Check there first.
                if name and name in self.obsolete_pkgs:

                        if not self.obsolete_pkgs[name].is_obsolete:
                                # the cached package is not obsolete, but we'll
                                # verify the version is valid
                                found_fmri = self.obsolete_pkgs[name].fmri
                                if not declared_fmri.has_version():
                                        return
                                elif lint_fmri_successor(found_fmri,
                                    declared_fmri,
                                    ignore_pubs=engine.ignore_pubs):
                                        return

                # A non-obsolete dependency wasn't found in the local cache,
                # or the one in the cache was found not to be a successor of
                # the fmri in the depend action.
                lint_id = "{0}{1}".format(self.name, pkglint_id)

                mf = None
                found_obsolete = False
                try:
                        mf = engine.follow_renames(
                            dep_fmri, old_mfs=[], warn_on_obsolete=True)
                except base.LintException as err:
                        found_obsolete = True
                        engine.error("{0} {1}".format(msg.format(manifest.fmri),
                            err), msgid=lint_id)

                # We maintain a whitelist of dependencies which may be missing
                # during this lint run (eg. packages that are present in a
                # different repository)  Consult that list before complaining
                # about each fmri being missing.

                # If unversioned FMRIs are present in the list, versioned
                # dependencies will match those if their package name and
                # publisher match.
                known_missing_deps = engine.get_param(
                    "{0}.1.missing-deps".format(lint_id), action=action,
                    manifest=manifest)
                if known_missing_deps:
                        known_missing_deps = known_missing_deps.split(" ")
                else:
                        known_missing_deps = []

                if not mf and not found_obsolete:
                        self.missing_deps.append(dep_fmri)
                        if dep_fmri in known_missing_deps:
                                return
                        if "@" in dep_fmri and \
                            dep_fmri.split("@")[0] in known_missing_deps:
                                return
                        engine.warning(_("obsolete dependency check "
                            "skipped: unable to find dependency {dep}"
                            " for {pkg}").format(
                            dep=dep_fmri,
                            pkg=manifest.fmri),
                            msgid="{0}.1".format(lint_id))

        dep_obsolete.pkglint_desc = _(
            "Packages should not have dependencies on obsolete packages.")

        def valid_fmri(self, action, manifest, engine, pkglint_id="006"):
                """We should be given a valid FMRI as a dependency, allowing
                for a potentially missing component value"""

                if "fmri" not in action.attrs:
                        return
                fmris = action.attrs["fmri"]
                if isinstance(fmris, six.string_types):
                        fmris = [fmris]

                for fmri in fmris:
                        try:
                                pfmri = pkg.fmri.PkgFmri(fmri)
                        except pkg.fmri.IllegalFmri:
                                # we also need to just verify that the fmri
                                # isn't just missing a build_release value
                                try:
                                        pfmri = pkg.fmri.PkgFmri(fmri)
                                except pkg.fmri.IllegalFmri:
                                        engine.error("invalid FMRI in action "
                                            "{action} in {pkg}".format(
                                            pkg=manifest.fmri,
                                            action=action),
                                            msgid="{0}{1}".format(
                                            self.name, pkglint_id))

        valid_fmri.pkglint_desc = _("pkg(5) FMRIs should be valid.")

        def license(self, action, manifest, engine, pkglint_id="007"):
                """License actions should not have path attributes."""

                if action.name is "license" and "path" in action.attrs:
                        engine.error(
                            _("license action in {pkg} has a path attribute, "
                            "{path}").format(
                            pkg=manifest.fmri,
                            path=action.attrs["path"]),
                            msgid="{0}{1}".format(self.name, pkglint_id))

        license.pkglint_desc = _("'license' actions should not have paths.")

        def linted(self, action, manifest, engine, pkglint_id="008"):
                """Log an INFO message with the key/value pairs of all
                pkg.linted* attributes set on this action.

                Essentially this exists to prevent users from adding
                pkg.linted values to manifests that don't really need them."""

                linted_attrs = [(key, action.attrs[key])
                    for key in sorted(action.attrs.keys())
                    if key.startswith("pkg.linted")]

                if linted_attrs:
                        engine.info(_("pkg.linted attributes detected for "
                            "{pkg} {action}: {linted}").format(
                            pkg=manifest.fmri,
                            action=str(action),
                            linted=", ".join(["{0}={1}".format(key, val)
                             for key,val in linted_attrs])),
                             msgid="{0}{1}".format(self.name, pkglint_id),
                             ignore_linted=True)

        linted.pkglint_desc = _("Show actions with pkg.linted attributes.")

        def validate(self, action, manifest, engine, pkglint_id="009"):
                """Validate all actions."""
                if not engine.do_pub_checks:
                        return
                try:
                        action.validate()
                except ActionError as err:
                        # we want the details all on one line to
                        # stay consistent with the rest of the pkglint
                        # error messaging
                        details = "; ".join([val.lstrip()
                            for val in str(err).split("\n")])
                        engine.error(
                            _("Publication error with action in {pkg}: "
                            "{details}").format(
                            pkg=manifest.fmri, details=details),
                            msgid="{0}{1}".format(self.name, pkglint_id))

        validate.pkglint_desc = _("Publication checks for actions.")

        def username_format(self, action, manifest, engine, pkglint_id="010"):
                """Checks username length, and format."""

                if action.name is not "user":
                        return

                username = action.attrs["username"]

                if len(username) == 0:
                        engine.error(
                            _("username attribute value must be set "
                            "in {pkg}").format(pkg=manifest.fmri),
                            msgid="{0}{1}.4".format(self.name, pkglint_id))
                        return

                if len(username) > 32:
                        engine.error(
                            _("Username {name} in {pkg} > 32 chars").format(
                            name=username,
                            pkg=manifest.fmri),
                            msgid="{0}{1}.1".format(self.name, pkglint_id))

                if not re.match("[a-z].*", username):
                        engine.warning(
                            _("Username {name} in {pkg} does not have an "
                            "initial lower-case alphabetical "
                            "character").format(
                            name=username,
                            pkg=manifest.fmri),
                            msgid="{0}{1}.2".format(self.name, pkglint_id))

                if len(username)> 0 and not \
                    re.match("^[a-z]([a-zA-Z1-9._-])*$", username):
                        engine.warning(
                            _("Username {name} in {pkg} is discouraged - see "
                            "passwd(4)").format(
                            name=username,
                            pkg=manifest.fmri),
                            msgid="{0}{1}.3".format(self.name, pkglint_id))

        username_format.pkglint_desc = _("User names should be valid.")

        def version_incorporate(self, action, manifest, engine,
            pkglint_id="011"):
                """Checks that 'incorporate' dependencies have a version."""

                if action.name != "depend":
                        return
                if action.attrs.get("type") != "incorporate":
                        return

                fmri = action.attrs["fmri"]
                pfmri = pkg.fmri.PkgFmri(fmri)
                if not pfmri.version:
                        engine.error(
                            _("'incorporate' depend action on {fmri} in "
                            "{pkg} does not have a version.").format(
                            fmri=fmri,
                            pkg=manifest.fmri),
                            msgid="{0}{1}".format(self.name, pkglint_id))

        version_incorporate.pkglint_desc = _("'incorporate' dependencies should"
            " have a version.")

        def facet_value(self, action, manifest, engine, pkglint_id="012"):
                """facet values should be set to a valid value in pkg(5)"""

                for key in action.attrs.keys():
                        if key.startswith("facet"):
                                value = action.attrs[key].lower()
                                if value not in ["true", "false", "all"]:
                                        engine.warning(
                                            _("facet value should be set to "
                                            "'true', 'false' or 'all' in "
                                            "attribute name {key} "
                                            "in {fmri}").format(
                                           key=key,
                                           fmri=manifest.fmri),
                                           msgid="{0}{1}".format(self.name,
                                           pkglint_id))

        facet_value.pkglint_desc = _("facet value should be set to "
            "a valid value in an action attribute")

        def supported_pkg_actuator(self, action, manifest, engine,
            pkglint_id="013"):
                """pkg_actuators should be set to a valid value in pkg(5)"""

                start_pattern = "pkg.additional-"
                supported_actuators = [
                    start_pattern + "update-on-uninstall",
                    start_pattern  + "uninstall-on-uninstall",
                ]

                if not "name" in action.attrs or \
                    not action.attrs["name"].startswith(start_pattern):
                        return

                if not action.attrs["name"] in supported_actuators:
                        engine.warning(
                            _("invalid package actuator name {attr} in {fmri}\n"
                            "supported values: {sact}").format(
                                attr=action.attrs["name"],
                                fmri=manifest.fmri,
                                sact=", ".join(supported_actuators)
                            ), msgid="{0}{1}".format(self.name, pkglint_id))

                if  action.attrs["name"] == \
                    start_pattern + "uninstall-on-uninstall":
                        for v in action.attrlist("value"):
                                pfmri = pkg.fmri.PkgFmri(v)
                                if not pfmri.version:
                                        continue
                                engine.warning("invalid package-triggered "
                                    "uninstall FMRI {tf} in {fmri}: should "
                                    "not contain a version".format(
                                        tf=str(pfmri),
                                        fmri=manifest.fmri
                                    ), msgid="{0}{1}".format(self.name,
                                        pkglint_id))

                if  action.attrs["name"] == \
                    start_pattern + "update-on-uninstall":
                        for v in action.attrlist("value"):
                                pfmri = pkg.fmri.PkgFmri(v)
                                if pfmri.version:
                                        continue
                                engine.warning("invalid package-triggered "
                                    "update FMRI {tf} in {fmri}: should "
                                    "contain a specific version".format(
                                        tf=str(pfmri),
                                        fmri=manifest.fmri
                                    ), msgid="{0}{1}".format(self.name,
                                        pkglint_id))

        supported_pkg_actuator.pkglint_desc = _("package actuator should be "
            "set to a valid value")
