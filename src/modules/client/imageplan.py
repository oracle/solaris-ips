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
# Copyright (c) 2007, 2017, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function
from collections import defaultdict, namedtuple
import contextlib
import errno
import fnmatch
import io
import itertools
import mmap
import operator
import os
import shutil
import six
import stat
import sys
import tempfile
import time
import traceback
import weakref

from functools import cmp_to_key, reduce

from pkg.client import global_settings
logger = global_settings.logger

import pkg.actions
import pkg.actions.driver as driver
import pkg.catalog
import pkg.client.api_errors as api_errors
import pkg.client.bootenv as bootenv
import pkg.client.indexer as indexer
import pkg.client.linkedimage.zone as zone
import pkg.client.pkg_solver as pkg_solver
import pkg.client.pkgdefs as pkgdefs
import pkg.client.pkgplan as pkgplan
import pkg.client.plandesc as plandesc
import pkg.digest as digest
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.mediator as med
import pkg.portable as portable
import pkg.search_errors as se
import pkg.version

from pkg.client.debugvalues import DebugValues
from pkg.client.plandesc import _ActionPlan
from pkg.mediator import mediator_impl_matches
from pkg.client.pkgdefs import (PKG_OP_DEHYDRATE, PKG_OP_REHYDRATE, MSG_ERROR,
    MSG_WARNING, MSG_INFO, MSG_GENERAL, MSG_UNPACKAGED, PKG_OP_VERIFY)


def _reorder_hardlinks(hardlinks):
        """Re-order the list of hardlinks to handle hard links whose
        target is another hard link."""

        reordered = []

        # Capture the paths for all given hardlinks.
        paths = [hardlink.dst.attrs["path"] for hardlink in hardlinks]

        def add_targets(path, hardlinks, reordered):
                """Find those hardlinks whose target is path."""

                srcs = [l for l in hardlinks
                    if l.dst.get_target_path() == path]
                for hardlink in srcs:
                        hardlinks.remove(hardlink)
                        reordered.append(hardlink)
                        # ... process hardlinks whose dst is _this_ hardlink.
                        add_targets(hardlink.dst.attrs["path"], hardlinks,
                            reordered)

        # Find hardlinks whose dst is _not_ another hardlink.
        unchained = [l for l in hardlinks
            if l.dst.get_target_path() not in paths]
        for hardlink in unchained:
                hardlinks.remove(hardlink)
                reordered.append(hardlink)
                # ... process hardlinks whose target is _this_ hardlink.
                add_targets(hardlink.dst.attrs["path"], hardlinks,
                    reordered)

        # Append remaining hardlinks (likely circular or otherwise broken).
        reordered.extend(hardlinks)

        return reordered


class ImagePlan(object):
        """ImagePlan object contains the plan for changing the image...
        there are separate routines for planning the various types of
        image modifying operations; evaluation (comparing manifests
        and building lists of removal, install and update actions
        and their execution is all common code"""

        MATCH_ALL           = 0
        MATCH_INST_VERSIONS = 1
        MATCH_INST_STEMS    = 2
        MATCH_UNINSTALLED   = 3

        def __init__(self, image, op, progtrack, check_cancel, noexecute=False,
            pd=None):

                self.image = image
                self.__progtrack = progtrack
                self.__check_cancel = check_cancel
                self.__noexecute = noexecute

                # The set of processed target object directories known to be
                # valid (those that are not symlinks and thus are valid for
                # use during installation).  This is used by the pkg.actions
                # classes during install() operations.
                self.valid_directories = set()

                # A place to keep info about saved_files; needed by file action.
                self.saved_files = {}

                self.__target_install_count = 0
                self.__target_update_count  = 0
                self.__target_removal_count = 0

                self.__directories = None # implement ref counting
                self.__symlinks = None    # for dirs and links and
                self.__hardlinks = None   # hardlinks
                self.__licenses = None
                self.__legacy = None
                self.__cached_actions = {}
                self.__fixups = {}
                self.operations_pubs = None # pubs being operated in hydrate

                self.__old_excludes = image.list_excludes()
                self.__new_excludes = self.__old_excludes

                self.__preexecuted_indexing_error = None
                self.__match_inst = {} # dict of fmri -> pattern
                self.__match_rm = {} # dict of fmri -> pattern
                self.__match_update = {} # dict of fmri -> pattern

                self.__pkg_actuators = set()
                self._retrieved = set()

                self.pd = None
                if pd is None:
                        pd = plandesc.PlanDescription(op)
                assert(pd._op == op)
                self.__setup_plan(pd)

        def __str__(self):

                if self.pd.state == plandesc.UNEVALUATED:
                        s = "UNEVALUATED:\n"
                        return s

                s = "{0}\n".format(self.pd._solver_summary)

                if self.pd.state < plandesc.EVALUATED_PKGS:
                        return s

                s += "Package version changes:\n"

                for oldfmri, newfmri in self.pd._fmri_changes:
                        s += "{0} -> {1}\n".format(oldfmri, newfmri)

                if self.pd._actuators:
                        s = s + "\nActuators:\n{0}\n".format(self.pd._actuators)

                if self.__old_excludes != self.__new_excludes:
                        s += "\nVariants/Facet changes:\n {0}".format(
                            "\n".join(self.pd.get_varcets()))

                if self.pd._mediators_change:
                        s = s + "\nMediator changes:\n {0}".format(
                            "\n".join(self.pd.get_mediators()))

                return s

        def __setup_plan(self, plan):
                assert plan.state in [
                    plandesc.UNEVALUATED, plandesc.EVALUATED_PKGS,
                    plandesc.EVALUATED_OK]

                self.pd = plan
                self.__update_avail_space()

                # make sure we init this even if we don't call solver
                self.pd._new_avoid_obs = (self.image.avoid_set_get(),
                    self.image.avoid_set_get(implicit=True),
                    self.image.obsolete_set_get())

                if self.pd.state == plandesc.UNEVALUATED:
                        self.image.linked.init_plan(plan)
                        return

                # figure out excludes
                self.__new_excludes = self.image.list_excludes(
                    self.pd._new_variants, self.pd._new_facets)

                # tell the linked image subsystem about this plan
                self.image.linked.setup_plan(plan)

                for pp in self.pd.pkg_plans:
                        pp.image = self.image
                        if pp.origin_fmri and pp.destination_fmri:
                                self.__target_update_count += 1
                        elif pp.destination_fmri:
                                self.__target_install_count += 1
                        elif pp.origin_fmri:
                                self.__target_removal_count += 1

        def skip_preexecute(self):
                assert self.pd.state in \
                    [plandesc.PREEXECUTED_OK, plandesc.EVALUATED_OK], \
                    "{0} not in [{1}, {2}]".format(self.pd.state,
                    plandesc.PREEXECUTED_OK, plandesc.EVALUATED_OK)

                if self.pd.state == plandesc.PREEXECUTED_OK:
                        # can't skip preexecute since we already preexecuted it
                        return

                if self.image.version != self.image.CURRENT_VERSION:
                        # Prevent plan execution if image format isn't current.
                        raise api_errors.ImageFormatUpdateNeeded(
                            self.image.root)

                if self.image.transport:
                        self.image.transport.shutdown()

                self.pd.state = plandesc.PREEXECUTED_OK

        @property
        def state(self):
                return self.pd.state

        @property
        def planned_op(self):
                """Returns a constant value indicating the type of operation
                planned."""

                return self.pd._op

        @property
        def plan_desc(self):
                """Get the proposed fmri changes."""
                return self.pd._fmri_changes

        def describe(self):
                """Return a pointer to the plan description."""
                return self.pd

        @property
        def bytes_added(self):
                """get the (approx) number of bytes added"""
                return self.pd._bytes_added
        @property
        def cbytes_added(self):
                """get the (approx) number of bytes needed in download cache"""
                return self.pd._cbytes_added

        @property
        def bytes_avail(self):
                """get the (approx) number of bytes space available"""
                return self.pd._bytes_avail
        @property
        def cbytes_avail(self):
                """get the (approx) number of download space available"""
                return self.pd._cbytes_avail

        def __finish_plan(self, pdstate, fmri_changes=None):
                """Private helper function that must be called at the end of
                every planning operation to ensure final plan state is set and
                any general post-plan work is performed."""

                pd = self.pd
                pd.state = pdstate
                if not fmri_changes is None:
                        pd._fmri_changes = fmri_changes

        def __vector_2_fmri_changes(self, installed_dict, vector,
            li_pkg_updates=True, new_variants=None, new_facets=None,
            fmri_changes=None):
                """Given an installed set of packages, and a proposed vector
                of package changes determine what, if any, changes should be
                made to the image.  This takes into account different
                behaviors during operations like variant changes, and updates
                where the only packages being updated are linked image
                constraints, etc."""

                fmri_updates = []
                if fmri_changes is not None:
                        affected = [f[0] for f in fmri_changes]
                else:
                        affected = None

                for a, b in ImagePlan.__dicts2fmrichanges(installed_dict,
                    ImagePlan.__fmris2dict(vector)):
                        if a != b:
                                fmri_updates.append((a, b))
                                continue

                        if (new_facets is not None or new_variants):
                                if affected is None or a in affected:
                                        # If affected list of packages has not
                                        # been predetermined for package fmris
                                        # that are unchanged, or if the fmri
                                        # exists in the list of affected
                                        # packages, add it to the list.
                                        fmri_updates.append((a, a))

                # cache li_pkg_updates in the plan description for later
                # evaluation
                self.pd._li_pkg_updates = li_pkg_updates

                return fmri_updates

        def __plan_op(self):
                """Private helper method used to mark the start of a planned
                operation."""

                self.pd._image_lm = self.image.get_last_modified(string=True)

        def __merge_inherited_facets(self, new_facets=None):
                """Merge any new facets settings with (possibly changing)
                inherited facets."""

                if new_facets is not None:
                        # make sure we don't accidentally update the caller
                        # supplied facets.
                        new_facets = pkg.facet.Facets(new_facets)

                        # we don't allow callers to specify inherited facets
                        # (they can only come from parent images.)
                        new_facets._clear_inherited()

                # get the existing image facets.
                old_facets = self.image.cfg.facets

                if new_facets is None:
                        # the user did not request any facet changes, but we
                        # still need to see if inherited facets are changing.
                        # so set new_facets to the existing facet set with
                        # inherited facets removed.
                        new_facets = pkg.facet.Facets(old_facets)
                        new_facets._clear_inherited()

                # get the latest inherited facets and merge them into the user
                # specified facets.
                new_facets.update(self.image.linked.inherited_facets())

                if new_facets == old_facets:
                        # there are no caller specified or inherited facet
                        # changes.
                        return (None, False, False)

                facet_change = bool(old_facets._cmp_values(new_facets)) or \
                    bool(old_facets._cmp_priority(new_facets))
                masked_facet_change = bool(not facet_change) and \
                    bool(old_facets._cmp_all_values(new_facets))

                # Something better be changing.  But if visible facets are
                # changing we don't report masked facet changes.
                assert facet_change != masked_facet_change

                return (new_facets, facet_change, masked_facet_change)

        def __evaluate_excludes(self, new_variants=None, new_facets=None,
            dehydrate=None, rehydrate=None):
                """Private helper function used to determine new facet and
                variant state for image."""

                # merge caller supplied and inherited facets
                new_facets, facet_change, masked_facet_change = \
                    self.__merge_inherited_facets(new_facets)

                # if we're changing variants or facets, save that to the plan.
                if new_variants or facet_change or masked_facet_change:
                        self.pd._varcets_change = True
                        if new_variants:
                                # This particular data are passed as unicode
                                # instead of bytes in the child image due to the
                                # jsonrpclib update, so we use force_str here to
                                # reduce the pain in comparing json data type.
                                self.pd._new_variants = {}
                                for k, v in new_variants.items():
                                        self.pd._new_variants[misc.force_str(k)] = \
                                            misc.force_str(v)
                        else:
                                self.pd._new_variants = new_variants
                        self.pd._old_facets   = self.image.cfg.facets
                        self.pd._new_facets   = new_facets
                        self.pd._facet_change = facet_change
                        self.pd._masked_facet_change = masked_facet_change

                self.__new_excludes = self.image.list_excludes(new_variants,
                    new_facets)

                # Previously dehydrated publishers.
                old_dehydrated = set(self.image.cfg.get_property("property",
                    "dehydrated"))

                # We only want to exclude all actions in the old image that
                # belong to an already dehydrated publisher.
                if old_dehydrated:
                        self.__old_excludes.append(
                            self.image.get_dehydrated_exclude_func(
                            old_dehydrated))

                # Publishers to rehydrate
                if rehydrate is None:
                        rehydrate = set()
                rehydrate = set(rehydrate)

                # Publishers to dehydrate
                if dehydrate is None:
                        dehydrate = set()
                dehydrate = set(dehydrate) | (old_dehydrated - rehydrate)

                self.operations_pubs = sorted(dehydrate)
                # Only allows actions in new image that cannot be dehydrated
                # or that are in the dehydrate list and not in the rehydrate
                # list.
                if dehydrate:
                        self.__new_excludes.append(
                            self.image.get_dehydrated_exclude_func(dehydrate))

                return (new_variants, new_facets, facet_change,
                    masked_facet_change)

        def __run_solver(self, solver_cb, retry_wo_parent_deps=True):
                """Run the solver, and if it fails, optionally retry the
                operation once while relaxing installed parent
                dependencies."""

                # have the solver try to satisfy parent dependencies.
                ignore_inst_parent_deps = False

                # In some error cases, significant recursion may be required,
                # and the default (1000) is not enough.  In testing, this was
                # found to be sufficient for the solver's needs.
                prlimit = sys.getrecursionlimit()
                if prlimit < 3000:
                        sys.setrecursionlimit(3000)

                try:
                        return solver_cb(ignore_inst_parent_deps)
                except api_errors.PlanCreationException as e:
                        # if we're currently in sync don't retry the
                        # operation
                        if self.image.linked.insync(latest_md=False):
                                raise e
                        # if PKG_REQUIRE_SYNC is set in the
                        # environment we require an in-sync image.
                        if "PKG_REQUIRE_SYNC" in os.environ:
                                raise e
                        # caller doesn't want us to retry
                        if not retry_wo_parent_deps:
                                raise e
                        # we're an out-of-sync child image so retry
                        # this operation while ignoring parent
                        # dependencies for any installed packages.  we
                        # do this so that users can manipulate out of
                        # sync images in an attempt to bring them back
                        # in sync.  since we don't ignore parent
                        # dependencies for uninstalled packages, the
                        # user won't be able to take the image further
                        # out of sync.
                        ignore_inst_parent_deps = True
                        return solver_cb(ignore_inst_parent_deps)
                finally:
                        # restore original recursion limit
                        sys.setrecursionlimit(prlimit)

        def __add_actuator(self, trigger_fmri, trigger_op, exec_op, values,
            solver_inst, installed_dict):
                """Add a single actuator to the solver 'solver_inst' and update
                the plan. 'trigger_fmri' is pkg which triggered the operation
                and is only used in the plan. 'trigger_op' is the name of the
                operation which triggered the change, 'exec_op' is the name of
                the operation which should be performed.
                'values' contains the fmris of the pkgs which should get
                changed."""

                if not isinstance(values, list):
                        values = [values]

                pub_ranks = self.image.get_publisher_ranks()

                matched_vals, unmatched = self.__match_user_fmris(
                    self.image, values, self.MATCH_INST_STEMS,
                    pub_ranks=pub_ranks, installed_pkgs=installed_dict,
                    raise_not_installed=False,
                    default_matcher=pkg.fmri.exact_name_match)

                triggered_fmris = set()
                for m in matched_vals.values():
                        triggered_fmris |= set(m)

                # Removals are done by stem so we have to make sure we only add
                # removal FMRIs for versions which are actually installed. If
                # the actuator specifies a version which is not installed, treat
                # as nop.
                # For updates, we have to remove versions which are already in
                # the image because we don't want them in the proposed list for
                # the solver. Otherwise we might trim on the installed version
                # which prevents us from downgrading.
                for t in triggered_fmris.copy():
                        if (exec_op == pkgdefs.PKG_OP_UNINSTALL and
                            t not in installed_dict.values()) or \
                            (exec_op != pkgdefs.PKG_OP_UNINSTALL
                            and t in installed_dict.values()):
                                triggered_fmris.remove(t)
                                continue
                        self.__pkg_actuators.add((trigger_fmri, t.pkg_name,
                            trigger_op, exec_op))

                solver_inst.add_triggered_op(trigger_op, exec_op,
                    triggered_fmris)


        def __decode_pkg_actuator_attrs(self, action, op):
                """Read and decode pkg actuator data from action 'action'."""

                # we ignore any non-supported operations
                supported_exec_ops = [pkgdefs.PKG_OP_UPDATE,
                    pkgdefs.PKG_OP_UNINSTALL]

                if not action.attrs["name"].startswith("pkg.additional-"):
                        return

                # e.g.: set name=pkg.additional-update-on-uninstall value=...
                try:
                        trigger_op = action.attrs["name"].split("-")[3]
                        exec_op = action.attrs["name"].split("-")[1]
                except KeyError:
                        # Ignore invalid pkg actuators.
                        return

                if trigger_op != op or exec_op not in supported_exec_ops:
                        # Ignore unsupported pkg actuators.
                        return

                for f in action.attrlist("value"):
                        # Ignore values which are not valid FMRIs, we don't
                        # support globbing here.
                        try:
                                pkg.fmri.PkgFmri(f)
                        except pkg.fmri.IllegalFmri:
                                continue
                        yield (exec_op, f)

        def __set_pkg_actuators(self, patterns, op, solver_inst):
                """Check the manifests for the pkgs specified by 'patterns' and
                add them to the solver instance specified by 'solver_inst'. 'op'
                defines the trigger operation which called this function."""

                trigger_entries = {}

                ignore = DebugValues["ignore-pkg-actuators"]
                if ignore and ignore.lower() == "true":
                        return

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())
                pub_ranks = self.image.get_publisher_ranks()

                # Match only on installed stems. This makes sure no new pkgs
                # will get installed when an update is specified.  Note that
                # this allows trailing matches (i.e. 'ambiguous') matches that
                # may result in failure as the list of patterns are assumed to
                # be from user input.
                matched_vals, unmatched = self.__match_user_fmris(
                    self.image, patterns, self.MATCH_INST_VERSIONS,
                    pub_ranks=pub_ranks, installed_pkgs=installed_dict,
                    raise_not_installed=False)

                pfmris = set()
                for m in matched_vals:
                        pfmris |= set(matched_vals[m])

                for f in pfmris:
                        if not isinstance(f, pkg.fmri.PkgFmri):
                                f = pkg.fmri.PkgFmri(f)
                        for a in self.image.get_catalog(
                            self.image.IMG_CATALOG_INSTALLED).get_entry_actions(
                            f, [pkg.catalog.Catalog.SUMMARY]):
                                for exec_op, efmri in \
                                    self.__decode_pkg_actuator_attrs(a, op):
                                        self.__add_actuator(f, op,
                                            exec_op, efmri, solver_inst,
                                            installed_dict)

        def __add_pkg_actuators_to_pd(self, user_pkgs):
                """ Add pkg actuators to PlanDescription. Skip any changes which
                would have been triggered by an actuator but were also requested
                explicitly by the user to avoid confusion. """

                for (tf, p, t, e) in self.__pkg_actuators:
                        for (before, after) in self.pd._fmri_changes:
                                if (before and before.pkg_name == p or
                                    after and after.pkg_name == p) and \
                                    p not in user_pkgs:
                                        self.pd.add_pkg_actuator(tf.pkg_name, e,
                                            p)

        def __plan_install_solver(self, li_pkg_updates=True, li_sync_op=False,
            new_facets=None, new_variants=None, pkgs_inst=None,
            reject_list=misc.EmptyI, fmri_changes=None, exact_install=False):
                """Use the solver to determine the fmri changes needed to
                install the specified pkgs, sync the specified image, and/or
                change facets/variants within the current image."""

                # evaluate what varcet changes are required
                new_variants, new_facets, \
                    facet_change, masked_facet_change = \
                    self.__evaluate_excludes(new_variants, new_facets)

                # check if we need to uninstall any packages.
                uninstall = self.__any_reject_matches(reject_list)

                # check if anything is actually changing.
                if not (li_sync_op or pkgs_inst or uninstall or
                    new_variants or facet_change or fmri_changes is not None):
                        # the solver is not necessary.
                        self.pd._fmri_changes = []
                        return

                # get ranking of publishers
                pub_ranks = self.image.get_publisher_ranks()

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())

                if reject_list:
                        reject_set = self.match_user_stems(self.image,
                            reject_list, self.MATCH_ALL)
                else:
                        reject_set = set()

                if pkgs_inst:
                        inst_dict, references = self.__match_user_fmris(
                            self.image, pkgs_inst, self.MATCH_ALL,
                            pub_ranks=pub_ranks, installed_pkgs=installed_dict,
                            reject_set=reject_set)
                        self.__match_inst = references
                else:
                        inst_dict = {}

                if new_variants:
                        variants = new_variants
                else:
                        variants = self.image.get_variants()

                installed_dict_tmp = {}
                # If exact_install is on, clear the installed_dict.
                if exact_install:
                        installed_dict_tmp = installed_dict.copy()
                        installed_dict = {}

                def solver_cb(ignore_inst_parent_deps):
                        avoid_set = self.image.avoid_set_get()
                        frozen_list = self.image.get_frozen_list()
                        # If exact_install is on, ignore avoid_set and
                        # frozen_list.
                        if exact_install:
                                avoid_set = set()
                                frozen_list = []

                        # instantiate solver
                        solver = pkg_solver.PkgSolver(
                            self.image.get_catalog(
                                self.image.IMG_CATALOG_KNOWN),
                            installed_dict,
                            pub_ranks,
                            variants,
                            avoid_set,
                            self.image.linked.parent_fmris(),
                            self.__progtrack)

                        if reject_list:
                                # use reject_list, not reject_set, to preserve
                                # input intent (e.g. 'pkg:/', '/' prefixes).
                                self.__set_pkg_actuators(reject_list,
                                    pkgdefs.PKG_OP_UNINSTALL, solver)

                        # run solver
                        new_vector, new_avoid_obs = \
                            solver.solve_install(
                                frozen_list,
                                inst_dict,
                                new_variants=new_variants,
                                excludes=self.__new_excludes,
                                reject_set=reject_set,
                                trim_proposed_installed=False,
                                relax_all=li_sync_op,
                                ignore_inst_parent_deps=\
                                    ignore_inst_parent_deps,
                                exact_install=exact_install,
                                installed_dict_tmp=installed_dict_tmp)

                        return solver, new_vector, new_avoid_obs

                # We can't retry this operation while ignoring parent
                # dependencies if we're doing a linked image sync.
                retry_wo_parent_deps = not li_sync_op

                # Solve; will raise exceptions if no solution is found.
                solver, new_vector, self.pd._new_avoid_obs = \
                    self.__run_solver(solver_cb, \
                        retry_wo_parent_deps=retry_wo_parent_deps)

                # Restore the installed_dict for checking fmri changes.
                if exact_install:
                        installed_dict = installed_dict_tmp.copy()

                self.pd._fmri_changes = self.__vector_2_fmri_changes(
                    installed_dict, new_vector,
                    li_pkg_updates=li_pkg_updates,
                    new_variants=new_variants, new_facets=new_facets,
                    fmri_changes=fmri_changes)

                self.__add_pkg_actuators_to_pd(reject_set)

                self.pd._solver_summary = str(solver)
                if DebugValues["plan"]:
                        self.pd._solver_errors = solver.get_trim_errors()

        def __plan_install(self, li_pkg_updates=True, li_sync_op=False,
            new_facets=None, new_variants=None, pkgs_inst=None,
            reject_list=misc.EmptyI):
                """Determine the fmri changes needed to install the specified
                pkgs, sync the image, and/or change facets/variants within the
                current image."""

                self.__plan_op()
                self.__plan_install_solver(
                    li_pkg_updates=li_pkg_updates,
                    li_sync_op=li_sync_op,
                    new_facets=new_facets,
                    new_variants=new_variants,
                    pkgs_inst=pkgs_inst,
                    reject_list=reject_list)
                self.__finish_plan(plandesc.EVALUATED_PKGS)

        def __plan_exact_install(self, li_pkg_updates=True, li_sync_op=False,
            new_facets=None, new_variants=None, pkgs_inst=None,
            reject_list=misc.EmptyI):
                """Determine the fmri changes needed to install exactly the
                specified pkgs, sync the image, and/or change facets/variants
                within the current image."""

                self.__plan_op()
                self.__plan_install_solver(
                    li_pkg_updates=li_pkg_updates,
                    li_sync_op=li_sync_op,
                    new_facets=new_facets,
                    new_variants=new_variants,
                    pkgs_inst=pkgs_inst,
                    reject_list=reject_list,
                    exact_install=True)
                self.__finish_plan(plandesc.EVALUATED_PKGS)

        def set_be_options(self, backup_be, backup_be_name, new_be,
            be_activate, be_name):
                self.pd._backup_be = backup_be
                self.pd._backup_be_name = backup_be_name
                self.pd._new_be = new_be
                self.pd._be_activate = be_activate
                self.pd._be_name = be_name

        def __set_update_index(self, value):
                self.pd._update_index = value

        def __get_update_index(self):
                return self.pd._update_index

        update_index = property(__get_update_index, __set_update_index)

        def plan_install(self, pkgs_inst=None, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to install the specified
                pkgs"""

                self.__plan_install(pkgs_inst=pkgs_inst,
                     reject_list=reject_list)

        def plan_exact_install(self, pkgs_inst=None, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to install exactly the
                specified pkgs"""

                self.__plan_exact_install(pkgs_inst=pkgs_inst,
                     reject_list=reject_list)

        def __get_attr_fmri_changes(self, get_mattrs):
                # Attempt to optimize package planning by determining which
                # packages are actually affected by changing attributes (e.g.,
                # facets, variants).  This also provides an accurate list of
                # affected packages as a side effect (normally, all installed
                # packages are seen as changed).  This assumes that facets and
                # variants are not both changing at the same time.
                use_solver = False
                cat = self.image.get_catalog(
                    self.image.IMG_CATALOG_INSTALLED)
                cat_info = frozenset([cat.DEPENDENCY])

                fmri_changes = []
                pt = self.__progtrack
                rem_pkgs = self.image.count_installed_pkgs()

                pt.plan_start(pt.PLAN_PKGPLAN, goal=rem_pkgs)
                for f in self.image.gen_installed_pkgs():
                        m = self.image.get_manifest(f,
                            ignore_excludes=True)

                        # Get the list of attributes involved in this operation
                        # that the package uses and that have changed.
                        use_solver, mattrs = get_mattrs(m, use_solver)
                        if not mattrs:
                                # Changed attributes unused.
                                pt.plan_add_progress(pt.PLAN_PKGPLAN)
                                rem_pkgs -= 1
                                continue

                        # Changed attributes are used in this package.
                        fmri_changes.append((f, f))

                        # If any dependency actions are tagged with one
                        # of the changed attributes, assume the solver
                        # must be used.
                        for act in cat.get_entry_actions(f, cat_info):
                                for attr in mattrs:
                                        if use_solver:
                                                break
                                        if (act.name == "depend" and
                                            attr in act.attrs):
                                                use_solver = True
                                                break
                                if use_solver:
                                        break

                        rem_pkgs -= 1
                        pt.plan_add_progress(pt.PLAN_PKGPLAN)

                pt.plan_done(pt.PLAN_PKGPLAN)
                pt.plan_all_done()

                return use_solver, fmri_changes

        def __facet_change_fastpath(self):
                """The following optimizations only work correctly if only
                facets are changing (not variants, uninstalls, etc)."""

                old_facets = self.pd._old_facets
                new_facets = self.pd._new_facets

                # List of changed facets are those that have a new value,
                # and those that have been removed.
                changed_facets = [
                        f
                        for f in new_facets
                        if f not in old_facets or \
                            old_facets[f] != new_facets[f]
                ]
                changed_facets.extend(
                        f
                        for f in old_facets
                        if f not in new_facets
                )

                def get_fattrs(m, use_solver):
                        # Get the list of facets involved in this
                        # operation that the package uses.  To
                        # accurately determine which packages are
                        # actually being changed, we must compare the
                        # old effective value for each facet that is
                        # changing with its new effective value.
                        return use_solver, list(
                            f
                            for f in m.gen_facets(
                                excludes=self.__new_excludes,
                                patterns=changed_facets)
                            if new_facets[f] != old_facets[f]
                        )

                return self.__get_attr_fmri_changes(get_fattrs)

        def __variant_change_fastpath(self):
                """The following optimizations only work correctly if only
                variants are changing (not facets, uninstalls, etc)."""

                nvariants = self.pd._new_variants

                def get_vattrs(m, use_solver):
                        # Get the list of variants involved in this
                        # operation that the package uses.
                        mvars = []
                        for (variant, pvals) in m.gen_variants(
                            excludes=self.__new_excludes,
                            patterns=nvariants
                        ):
                                if nvariants[variant] not in pvals:
                                        # If the new value for the
                                        # variant is unsupported by this
                                        # package, then the solver
                                        # should be triggered so the
                                        # package can be removed.
                                        use_solver = True
                                mvars.append(variant)
                        return use_solver, mvars

                return self.__get_attr_fmri_changes(get_vattrs)

        def __get_publishers_with_repos(self, publishers=misc.EmptyI):
                """Return publishers that have repositories configured.

                'publishers' is an optional list of publisher prefixes to
                limit the returned results to.

                A PlanCreationException will be raised if any of the publishers
                specified do not exist, if any of the specified publishers have
                no configured repositories, or if all known publishers have
                no configured repositories."""

                all_pubs = [ p.prefix for p in self.image.gen_publishers() ]
                if not publishers:
                        if all_pubs:
                                publishers = all_pubs
                        else:
                                return misc.EmptyI

                configured_pubs = [
                    pub.prefix
                    for pub in self.image.gen_publishers()
                    if pub.prefix in publishers and \
                        (pub.repository and pub.repository.origins)
                ]

                unconfigured_pubs = set(publishers) - set(configured_pubs)
                if unconfigured_pubs:
                        raise api_errors.PlanCreationException(
                            no_repo_pubs=unconfigured_pubs)

                return configured_pubs

        def __plan_common_hydration(self, publishers, dehydrate=False):
                self.__plan_op()

                # get publishers to dehydrate or rehydrate
                pubs = self.__get_publishers_with_repos(publishers=publishers)

                if not pubs:
                        # Nothing to do.
                        self.__finish_plan(plandesc.EVALUATED_PKGS)
                        return

                # List of packages that will be modified.
                fmri_changes = [
                    (f, f)
                    for f in self.image.gen_installed_pkgs(pubs=pubs)
                ]

                # Evaluate current facets / variants.
                if dehydrate:
                        self.__evaluate_excludes(dehydrate=pubs)
                else:
                        self.__evaluate_excludes(rehydrate=pubs)

                # If solver isn't involved, assume the list of packages
                # has been determined.
                assert fmri_changes is not None
                self.__finish_plan(plandesc.EVALUATED_PKGS,
                    fmri_changes=fmri_changes)

        def plan_dehydrate(self, publishers=None):
                """Dehydrate packages for given publishers.  If no publishers
                are specified, packages for all publishers with configured
                repositories will be dehydrated."""

                self.__plan_common_hydration(publishers, dehydrate=True)

        def plan_rehydrate(self, publishers=None):
                """Rehydrate packages for given publishers.  If no publishers
                are specified, packages for all dehydrated publishers with
                configured repositories will be rehydrated."""

                self.__plan_common_hydration(publishers)

        def plan_change_varcets(self, new_facets=None, new_variants=None,
            reject_list=misc.EmptyI):
                """Determine the fmri changes needed to change the specified
                facets/variants."""

                self.__plan_op()

                # assume none of our optimizations will work.
                fmri_changes = None

                # convenience function to invoke the solver.
                def plan_install_solver():
                        self.__plan_install_solver(
                            new_facets=new_facets,
                            new_variants=new_variants,
                            reject_list=reject_list,
                            fmri_changes=fmri_changes)
                        self.__finish_plan(plandesc.EVALUATED_PKGS)

                # evaluate what varcet changes are required
                new_variants, new_facets, \
                    facet_change, masked_facet_change = \
                    self.__evaluate_excludes(new_variants, new_facets)

                # uninstalling packages requires the solver.
                uninstall = self.__any_reject_matches(reject_list)
                if uninstall:
                        plan_install_solver()
                        return

                # All operations (including varcet changes) need to try and
                # keep linked images in sync.  Linked image audits are fast,
                # so do one now and if we're not in sync we need to invoke the
                # solver.
                if not self.image.linked.insync():
                        plan_install_solver()
                        return

                # if facets and variants are changing at the same time, then
                # we need to invoke the solver.
                if new_variants and facet_change:
                        plan_install_solver()
                        return

                # By default, we assume the solver must be used.  If any of the
                # optimizations below can be applied, they'll determine whether
                # the solver can be used.
                use_solver = True

                # the following facet optimization only works if we're not
                # changing variants at the same time.
                if facet_change:
                        assert not new_variants
                        use_solver, fmri_changes = \
                            self.__facet_change_fastpath()

                # the following variant optimization only works if we're not
                # changing facets at the same time.
                if new_variants:
                        assert not facet_change
                        use_solver, fmri_changes = \
                            self.__variant_change_fastpath()

                if use_solver:
                        plan_install_solver()
                        return

                # If solver isn't involved, assume the list of packages
                # has been determined.
                assert fmri_changes is not None
                self.__finish_plan(plandesc.EVALUATED_PKGS,
                    fmri_changes=fmri_changes)


        def plan_set_mediators(self, new_mediators):
                """Determine the changes needed to set the specified mediators.

                'new_mediators' is a dict of dicts of the mediators to set
                version and implementation for.  It should be of the form:

                   {
                       mediator-name: {
                           "implementation": mediator-implementation-string,
                           "version": mediator-version-string
                       }
                   }

                   'implementation' is an optional string that specifies the
                   implementation of the mediator for use in addition to or
                   instead of 'version'.  A value of None will be interpreted
                   as requesting a reset of implementation to its optimal
                   default.

                   'version' is an optional string that specifies the version
                   (expressed as a dot-separated sequence of non-negative
                   integers) of the mediator for use.  A value of None will be
                   interpreted as requesting a reset of version to its optimal
                   default.
                """

                self.__plan_op()
                self.__evaluate_excludes()

                self.pd._mediators_change = True
                self.pd._new_mediators = new_mediators
                cfg_mediators = self.image.cfg.mediators

                pt = self.__progtrack

                pt.plan_start(pt.PLAN_MEDIATION_CHG)
                # keys() is used since entries are deleted during iteration.
                update_mediators = {}
                for m in list(self.pd._new_mediators.keys()):
                        pt.plan_add_progress(pt.PLAN_MEDIATION_CHG)
                        for k in ("implementation", "version"):
                                if k in self.pd._new_mediators[m]:
                                        if self.pd._new_mediators[m][k] is not None:
                                                # Any mediators being set this
                                                # way are forced to be marked as
                                                # being set by local administrator.
                                                self.pd._new_mediators[m]["{0}-source".format(k)] = \
                                                    "local"
                                                continue

                                        # Explicit reset requested.
                                        del self.pd._new_mediators[m][k]
                                        self.pd._new_mediators[m].pop(
                                            "{0}-source".format(k), None)
                                        if k == "implementation":
                                                self.pd._new_mediators[m].pop(
                                                    "implementation-version",
                                                    None)
                                        continue

                                if m not in cfg_mediators:
                                        # Nothing to do if not previously
                                        # configured.
                                        continue

                                # If the mediator was configured by the local
                                # administrator, merge existing configuration.
                                # This is necessary since callers are only
                                # required to specify the components they want
                                # to change.
                                med_source = cfg_mediators[m].get("{0}-source".format(k))
                                if med_source != "local":
                                        continue

                                self.pd._new_mediators[m][k] = \
                                    cfg_mediators[m].get(k)
                                self.pd._new_mediators[m]["{0}-source".format(k)] = "local"

                                if k == "implementation" and \
                                    "implementation-version" in cfg_mediators[m]:
                                        self.pd._new_mediators[m]["implementation-version"] = \
                                            cfg_mediators[m].get("implementation-version")

                        if m not in cfg_mediators:
                                # mediation changed.
                                continue

                        # Determine if the only thing changing for mediations is
                        # whether configuration source is changing.  If so,
                        # optimize planning by not loading any package data.
                        for k in ("implementation", "version"):
                                if self.pd._new_mediators[m].get(k) != \
                                    cfg_mediators[m].get(k):
                                        break
                        else:
                                if (self.pd._new_mediators[m].get("version-source") != \
                                    cfg_mediators[m].get("version-source")) or \
                                    (self.pd._new_mediators[m].get("implementation-source") != \
                                    cfg_mediators[m].get("implementation-source")):
                                        update_mediators[m] = \
                                            self.pd._new_mediators[m]
                                del self.pd._new_mediators[m]

                if self.pd._new_mediators:
                        # Some mediations are changing, so merge the update only
                        # ones back in.
                        self.pd._new_mediators.update(update_mediators)

                        # Determine which packages will be affected.
                        for f in self.image.gen_installed_pkgs():
                                pt.plan_add_progress(pt.PLAN_MEDIATION_CHG)
                                m = self.image.get_manifest(f,
                                    ignore_excludes=True)
                                mediated = []
                                for act in m.gen_actions_by_types(("hardlink",
                                    "link"), excludes=self.__new_excludes):
                                        try:
                                                mediator = act.attrs["mediator"]
                                        except KeyError:
                                                continue
                                        if mediator in new_mediators:
                                                mediated.append(act)

                                if mediated:
                                        pp = pkgplan.PkgPlan(self.image)
                                        pp.propose_repair(f, m, mediated,
                                            misc.EmptyI)
                                        pp.evaluate(self.__new_excludes,
                                            self.__new_excludes,
                                            can_exclude=True)
                                        self.pd.pkg_plans.append(pp)
                else:
                        # Only the source property is being updated for
                        # these mediators, so no packages needed loading.
                        self.pd._new_mediators = update_mediators

                pt.plan_done(pt.PLAN_MEDIATION_CHG)
                self.__finish_plan(plandesc.EVALUATED_PKGS)

        def __any_reject_matches(self, reject_list):
                """Check if any reject patterns match installed packages (in
                which case a packaging operation should attempt to uninstall
                those packages)."""

                # return true if any packages in reject list
                # match any installed packages
                return bool(reject_list) and \
                    bool(self.match_user_stems(self.image, reject_list,
                        self.MATCH_INST_VERSIONS, raise_not_installed=False))

        def plan_sync(self, li_pkg_updates=True, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to sync the image."""

                self.__plan_op()

                # check if we need to uninstall any packages.
                uninstall = self.__any_reject_matches(reject_list)

                # check if inherited facets are changing
                new_facets = self.__evaluate_excludes()[1]

                # audits are fast, so do an audit to check if we're in sync.
                insync = self.image.linked.insync()

                # if we're not trying to uninstall packages, and inherited
                # facets are not changing, and we're already in sync, then
                # don't bother invoking the solver.
                if not uninstall and not new_facets is not None and insync:
                        # we don't need to do anything
                        self.__finish_plan(plandesc.EVALUATED_PKGS,
                            fmri_changes=[])
                        return

                self.__plan_install(li_pkg_updates=li_pkg_updates,
                    li_sync_op=True, reject_list=reject_list)

        def plan_uninstall(self, pkgs_to_uninstall, ignore_missing=False):
                self.__plan_op()
                proposed_dict, self.__match_rm = self.__match_user_fmris(
                    self.image, pkgs_to_uninstall, self.MATCH_INST_VERSIONS,
                    raise_not_installed=not ignore_missing)

                # merge patterns together
                proposed_removals = set([
                    f
                    for each in proposed_dict.values()
                    for f in each
                ])

                # check if inherited facets are changing
                new_facets = self.__evaluate_excludes()[1]

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())

                def solver_cb(ignore_inst_parent_deps):
                        # instantiate solver
                        solver = pkg_solver.PkgSolver(
                            self.image.get_catalog(
                                self.image.IMG_CATALOG_KNOWN),
                            installed_dict,
                            self.image.get_publisher_ranks(),
                            self.image.get_variants(),
                            self.image.avoid_set_get(),
                            self.image.linked.parent_fmris(),
                            self.__progtrack)

                        # check for triggered ops
                        self.__set_pkg_actuators(pkgs_to_uninstall,
                            pkgdefs.PKG_OP_UNINSTALL, solver)

                        # run solver
                        new_vector, new_avoid_obs = \
                            solver.solve_uninstall(
                                self.image.get_frozen_list(),
                                proposed_removals,
                                self.__new_excludes,
                                ignore_inst_parent_deps=\
                                    ignore_inst_parent_deps)

                        return solver, new_vector, new_avoid_obs

                # Solve; will raise exceptions if no solution is found.
                solver, new_vector, self.pd._new_avoid_obs = \
                    self.__run_solver(solver_cb)

                self.pd._fmri_changes = self.__vector_2_fmri_changes(
                    installed_dict, new_vector,
                    new_facets=new_facets)

                self.__add_pkg_actuators_to_pd(
                    [x.pkg_name for x in proposed_removals])

                self.pd._solver_summary = str(solver)
                if DebugValues["plan"]:
                        self.pd._solver_errors = solver.get_trim_errors()

                self.__finish_plan(plandesc.EVALUATED_PKGS)

        def __plan_update_solver(self, pkgs_update=None,
            ignore_missing=False, reject_list=misc.EmptyI):
                """Use the solver to determine the fmri changes needed to
                update the specified pkgs or all packages if none were
                specified."""

                # check if inherited facets are changing
                new_facets = self.__evaluate_excludes()[1]

                # get ranking of publishers
                pub_ranks = self.image.get_publisher_ranks()

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())

                # If specific packages or patterns were provided, then
                # determine the proposed set to pass to the solver.
                if reject_list:
                        reject_set = self.match_user_stems(self.image,
                            reject_list, self.MATCH_ALL)
                else:
                        reject_set = set()

                if pkgs_update:
                        update_dict, references = self.__match_user_fmris(
                            self.image, pkgs_update, self.MATCH_INST_STEMS,
                            pub_ranks=pub_ranks, installed_pkgs=installed_dict,
                            raise_not_installed=not ignore_missing,
                            reject_set=reject_set)
                        self.__match_update = references

                def solver_cb(ignore_inst_parent_deps):
                        # instantiate solver
                        solver = pkg_solver.PkgSolver(
                            self.image.get_catalog(
                                self.image.IMG_CATALOG_KNOWN),
                            installed_dict,
                            pub_ranks,
                            self.image.get_variants(),
                            self.image.avoid_set_get(),
                            self.image.linked.parent_fmris(),
                            self.__progtrack)

                        if reject_list:
                                # use reject_list, not reject_set, to preserve
                                # input intent (e.g. 'pkg:/', '/' prefixes).
                                self.__set_pkg_actuators(reject_list,
                                    pkgdefs.PKG_OP_UNINSTALL, solver)

                        # run solver
                        if pkgs_update:
                                new_vector, new_avoid_obs = \
                                    solver.solve_install(
                                        self.image.get_frozen_list(),
                                        update_dict,
                                        excludes=self.__new_excludes,
                                        reject_set=reject_set,
                                        trim_proposed_installed=False,
                                        ignore_inst_parent_deps=\
                                            ignore_inst_parent_deps)
                        else:
                                # Updating all installed packages requires a
                                # different solution path.
                                new_vector, new_avoid_obs = \
                                    solver.solve_update_all(
                                        self.image.get_frozen_list(),
                                        excludes=self.__new_excludes,
                                        reject_set=reject_set)

                        return solver, new_vector, new_avoid_obs

                # We can't retry this operation while ignoring parent
                # dependencies if we're doing a unconstrained update.
                retry_wo_parent_deps = bool(pkgs_update)

                # Solve; will raise exceptions if no solution is found.
                solver, new_vector, self.pd._new_avoid_obs = \
                    self.__run_solver(solver_cb, \
                        retry_wo_parent_deps=retry_wo_parent_deps)

                self.pd._fmri_changes = self.__vector_2_fmri_changes(
                    installed_dict, new_vector,
                    new_facets=new_facets)

                self.__add_pkg_actuators_to_pd(reject_set)

                self.pd._solver_summary = str(solver)
                if DebugValues["plan"]:
                        self.pd._solver_errors = solver.get_trim_errors()

        def plan_update(self, pkgs_update=None,
            ignore_missing=False, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to update the specified
                pkgs or all packages if none were specified."""

                self.__plan_op()
                self.__plan_update_solver(
                    ignore_missing=ignore_missing,
                    pkgs_update=pkgs_update,
                    reject_list=reject_list)
                self.__finish_plan(plandesc.EVALUATED_PKGS)

        def plan_revert(self, args, tagged):
                """Plan reverting the specified files or files tagged as
                specified.  We create the pkgplans here rather than in
                evaluate; by keeping the list of changed_fmris empty we
                skip most of the processing in evaluate.
                We also process revert tags on directories here"""

                self.__plan_op()
                self.__evaluate_excludes()

                revert_dict = defaultdict(list)
                revert_dirs = defaultdict(list)

                pt = self.__progtrack
                pt.plan_all_start()

                # since the fmri list stays empty, we can set this;
                # we need this set so we can build directories and
                # actions lists as we're doing checking with installed
                # actions earlier here.
                self.pd.state = plandesc.EVALUATED_PKGS

                # We could have a specific 'revert' tracker item, but
                # "package planning" seems as good a term as any.
                pt.plan_start(pt.PLAN_PKGPLAN,
                    goal=self.image.count_installed_pkgs())
                if tagged:
                        # look through all the files on the system; any files
                        # tagged w/ revert-tag set to any of the values on
                        # the command line need to be checked and reverted if
                        # they differ from the manifests.  Note we don't care
                        # if the file is editable or not.

                        # look through directories to see if any have our
                        # revert-tag set; we then need to check the value
                        # to find any unpackaged files that need deletion.
                        tag_set = set(args)
                        for f in self.image.gen_installed_pkgs():
                                pt.plan_add_progress(pt.PLAN_PKGPLAN)
                                m = self.image.get_manifest(f,
                                    ignore_excludes=True)
                                for act in m.gen_actions_by_type("file",
                                    excludes=self.__new_excludes):
                                        if "revert-tag" in act.attrs and \
                                            (set(act.attrlist("revert-tag")) &
                                             tag_set):
                                                revert_dict[(f, m)].append(act)

                                for act in m.gen_actions_by_type("dir",
                                    excludes=self.__new_excludes):
                                        if "revert-tag" not in act.attrs:
                                                continue
                                        for a in act.attrlist("revert-tag"):
                                                tag_parts = a.split("=", 2)
                                                if tag_parts[0] not in tag_set or \
                                                    len(tag_parts) != 2:
                                                        continue
                                                revert_dirs[(f, m)].append(
                                                    self.__gen_matching_acts(
                                                    act.attrs["path"],
                                                    tag_parts[1]))
                else:
                        # look through all the packages, looking for our files
                        # we could use search for this.  We don't support reverting
                        # directories by ad-hoc means.

                        revertpaths = set([a.lstrip(os.path.sep) for a in args])
                        overlaypaths = set()
                        for f in self.image.gen_installed_pkgs():
                                pt.plan_add_progress(pt.PLAN_PKGPLAN)
                                m = self.image.get_manifest(f,
                                    ignore_excludes=True)
                                for act in m.gen_actions_by_type("file",
                                    excludes=self.__new_excludes):
                                        path = act.attrs["path"]
                                        if path in revertpaths or \
                                            path in overlaypaths:
                                                revert_dict[(f, m)].append(act)
                                                if act.attrs.get("overlay") == \
                                                    "allow":
                                                        # Action allows overlay,
                                                        # all matching actions
                                                        # must be collected.
                                                        # The imageplan will
                                                        # automatically handle
                                                        # the overlaid action
                                                        # if an overlaying
                                                        # action is present.
                                                        overlaypaths.add(path)
                                                revertpaths.discard(path)

                        revertpaths.difference_update(overlaypaths)
                        if revertpaths:
                                pt.plan_done(pt.PLAN_PKGPLAN)
                                pt.plan_all_done()
                                raise api_errors.PlanCreationException(
                                    nofiles=list(revertpaths))

                for f, m in revert_dict.keys():
                        # build list of actions that will need to be reverted
                        # no sense in replacing files that are original already
                        needs_change = []
                        pt.plan_add_progress(pt.PLAN_PKGPLAN, nitems=0)
                        for act in revert_dict[(f, m)]:
                                # delete preserve and preserve-version
                                # attributes to both find and enable
                                # replacement of modified editable files.
                                act.attrs.pop("preserve", None)
                                act.attrs.pop("preserve-version", None)
                                act.verify(self.image, forever=True)
                                if act.replace_required == True:
                                        needs_change.append(act)

                        revert_dict[(f, m)] = needs_change

                for f, m in revert_dirs:
                        needs_delete = []
                        for unchecked, checked in revert_dirs[(f, m)]:
                                # just add these...
                                needs_delete.extend(checked)
                                # look for these
                                for un in unchecked:
                                        path = un.attrs["path"]
                                        if path not in self.get_actions("file") \
                                            and path not in self.get_actions("hardlink") \
                                            and path not in self.get_actions("link"):
                                                needs_delete.append(un)
                        revert_dirs[(f, m)] = needs_delete

                # build the pkg plans, making sure to propose only one repair
                # per fmri
                for f, m in set(list(revert_dirs.keys()) + list(revert_dict.keys())):
                        needs_delete = revert_dirs[(f, m)]
                        needs_change = revert_dict[(f, m)]
                        if not needs_delete and not needs_change:
                                continue

                        pp = pkgplan.PkgPlan(self.image)
                        pp.propose_repair(f, m, needs_change, needs_delete)
                        pp.evaluate(self.__new_excludes, self.__new_excludes,
                            can_exclude=True)
                        self.pd.pkg_plans.append(pp)

                pt.plan_done(pt.PLAN_PKGPLAN)
                pt.plan_all_done()
                self.__finish_plan(plandesc.EVALUATED_PKGS, fmri_changes=[])

        def __gen_matching_acts(self, path, pattern):
                # return two lists of actions that match pattern at path
                # include (recursively) directories only if they are not
                # implicitly or explicitly packaged.  First list may
                # contain packaged objects, second does not.

                if path == os.path.sep: # not doing root
                        return [], []

                dir_loc  = os.path.join(self.image.root, path)

                # If this is a mount point, disable this; too easy
                # to break things.  This means this doesn't work
                # on /var and /tmp - that's ok.

                try:
                        # if dir is missing, nothing to delete :)
                        my_dev = os.stat(dir_loc).st_dev
                except OSError:
                        return [], []

                # disallow mount points for safety's sake.
                if my_dev != os.stat(os.path.dirname(dir_loc)).st_dev:
                        return [], []

                # Any explicit or implicitly packaged directories are
                # ignored; checking all directory entries is cheap.
                paths = [
                    os.path.join(dir_loc, a)
                    for a in fnmatch.filter(os.listdir(dir_loc), pattern)
                    if os.path.join(path, a) not in self.__get_directories()
                ]

                # now we have list of items to be removed.  We know that
                # any directories are not packaged, so expand those here
                # and generate actions
                unchecked = []
                checked = []

                for path in paths:
                        if os.path.isdir(path) and not os.path.islink(path):
                                # we have a directory that needs expanding;
                                # add it in and then walk the contents
                                checked.append(self.__gen_del_act(path))
                                for dirpath, dirnames, filenames in os.walk(path):
                                        # crossed mountpoints - don't go here.
                                        if os.stat(dirpath).st_dev != my_dev:
                                                continue
                                        for name in dirnames + filenames:
                                                checked.append(
                                                    self.__gen_del_act(
                                                    os.path.join(dirpath, name)))
                        else:
                                unchecked.append(self.__gen_del_act(path))
                return unchecked, checked

        def __gen_del_act(self, path):
                # With fully qualified path, return action suitable for
                # deletion from image. Don't bother getting owner
                # and group right; we're just going to blow it up anyway.

                rootdir = self.image.root
                pubpath = pkg.misc.relpath(path, rootdir)
                pstat = os.lstat(path)
                mode = oct(stat.S_IMODE(pstat.st_mode))
                if stat.S_ISLNK(pstat.st_mode):
                        return pkg.actions.link.LinkAction(None,
                            target=os.readlink(path), path=pubpath)
                elif stat.S_ISDIR(pstat.st_mode):
                        return pkg.actions.directory.DirectoryAction(None,
                            mode=mode, owner="root",
                            group="bin", path=pubpath)
                else: # treat everything else as a file
                        return pkg.actions.file.FileAction(None,
                            mode=mode, owner="root",
                            group="bin", path=pubpath)

        def __get_overlaying(self, img, act, pfmri):
                """Given an action with attribute overlay=allow, if there is an
                overlaying action installed in the image, return the overlaying
                package's FMRI and the action."""

                for f in img.gen_installed_pkgs():
                        if f == pfmri:
                                # Not interested in ourselves.
                                continue
                        m = img.get_manifest(f)
                        matching = list(m.gen_actions_by_types([act.name],
                            {"path": [act.attrs["path"]]}))
                        if matching:
                                # Only one action can overlay another, so we
                                # know we've found a match at this point.
                                return f, matching[0]
                return None, None

        def __process_verify_result(self, act, pfmri, pt,
            verifypaths=None, overlaypaths=None, ovlying_fmri=None,
            ovlying_act=None, skip_ovlying=False, ovly_entries=None):
                """Process delayed actions."""
                if not ovlying_act and not skip_ovlying:
                        # Find the overlaying fmri/action.
                        ovlying_fmri, ovlying_act = self.__get_overlaying(
                            self.image, act, pfmri)
                # If overlaying action is found, we use the overlaying action
                # for verification.
                if ovlying_act:
                        # Update overlaying entries with the newly found
                        # overlaying action.
                        if ovly_entries:
                                ovlying_path = ovlying_act.attrs.get("path")
                                if ovlying_path in ovly_entries:
                                        ovly_entries[ovlying_path].append(
                                            (ovlying_fmri, ovlying_act,
                                            "overlaying"))
                        for oing_act, errors, warnings, pinfo, is_overlaid in \
                            self.image.verify(pfmri, pt,
                            verifypaths=verifypaths, overlaypaths=overlaypaths,
                            single_act=ovlying_act, verbose=True,
                            forever=True):
                                return oing_act, errors, warnings, pinfo, \
                                    ovlying_fmri
                else:
                        for olaid_act, errors, warnings, pinfo, is_overlaid \
                            in self.image.verify(pfmri, pt,
                            verifypaths=verifypaths, overlaypaths=overlaypaths,
                            single_act=act, verbose=True, forever=True):
                                return olaid_act, errors, warnings, pinfo, \
                                    None
                return act, [], [], [], None

        def __is_active_liveroot_be(self, img):
                """Check if an image is in an active live be."""

                if not img.is_liveroot():
                        return False, None

                try:
                        be_name, be_uuid = bootenv.BootEnv.get_be_name(
                            img.root)
                        return True, be_name
                except api_errors.BEException:
                        # If boot environment logic isn't supported, return
                        # False.  This is necessary for user images and for
                        # the test suite.
                        return False, None

        def __alt_image_root_with_new_be(self, dup_be_name, orig_img_root):
                img_root = orig_img_root
                mntpoint = None
                if not dup_be_name:
                        dup_be_name = "duplicate_livebe_for_verify"
                isalbe, src_be_name = self.__is_active_liveroot_be(self.image)
                if not isalbe:
                        return img_root, mntpoint

                try:
                        bootenv.BootEnv.cleanup_be(dup_be_name)
                        temp_root = misc.config_temp_root()
                        mntpoint = tempfile.mkdtemp(dir=temp_root,
                            prefix="pkg-verify" + "-")
                        bootenv.BootEnv.copy_be(src_be_name, dup_be_name)
                        bootenv.BootEnv.mount_be(dup_be_name, mntpoint)
                        img_root = mntpoint
                except Exception as e:
                        did_create = dup_be_name in \
                            bootenv.BootEnv.get_be_names()
                        warn = _("Cannot create or mount a copy of current be. "
                            "Reporting unpackaged content aganist current live "
                            "image.")
                        fallback = False
                        timestamp = misc.time_to_timestamp(time.time())
                        if did_create:
                                try:
                                        if img_root != mntpoint:
                                                bootenv.BootEnv.mount_be(
                                                    dup_be_name, mntpoint)
                                                img_root = mntpoint
                                except Exception as e:
                                        # Cannot mount be, fallback.
                                        fallback = True
                        else:
                                # Cannot create be, fallback.
                                fallback = True

                        if fallback:
                                shutil.rmtree(mntpoint, ignore_errors=True)
                                self.pd.add_item_message("warnings", timestamp,
                                    MSG_WARNING, warn, msg_type=MSG_UNPACKAGED,
                                    parent="unpackaged")
                return img_root, mntpoint

        def __process_unpackaged(self, proposed_fmris, pt=None,
            dup_be_name="duplicate_livebe_for_verify"):
                allentries = {}
                img_root = self.image.get_root()

                for fmri in proposed_fmris:
                        m = self.image.get_manifest(fmri)
                        for act in m.gen_actions():
                                if act.name in ["link", "hardlink", "dir",
                                    "file"]:
                                        install_path = os.path.normpath(
                                            os.path.join(img_root,
                                            act.attrs["path"]))
                                        allentries[install_path] = act.name
                        # Process possible implicit directories.
                        for d in m.get_directories(()):
                                install_path = os.path.normpath(
                                    os.path.join(img_root, d))
                                if install_path not in allentries:
                                        allentries[install_path] = "dir"
                        if pt:
                                pt.plan_add_progress(pt.PLAN_PKG_VERIFY)

                def handle_walk_error(oserror_inst):
                        timestamp = misc.time_to_timestamp(time.time())
                        self.pd.add_item_message("errors", timestamp,
                            MSG_ERROR, str(oserror_inst),
                            msg_type=MSG_UNPACKAGED, parent="unpackaged")

                orig_img_root = img_root
                img_root, mntpoint = self.__alt_image_root_with_new_be(
                    dup_be_name, orig_img_root)

                # Walk through file system structure.
                for root, dirs, files in os.walk(img_root,
                    onerror=handle_walk_error):
                        newdirs = []
                        # Since we possibly changed the img_root into the
                        # mounted be root, we need to change it back for look
                        # up.
                        orig_root = os.path.normpath(os.path.join(
                            orig_img_root, os.path.relpath(root, img_root)))
                        for d in sorted(dirs):
                                timestamp = misc.time_to_timestamp(time.time())
                                path = os.path.normpath(os.path.join(
                                    orig_root, d))
                                # Since the mntpoint is created solely for
                                # verify purpose, ignore it.
                                if mntpoint and path == mntpoint:
                                        continue
                                if path not in allentries or allentries[path] \
                                    not in ["dir", "link"]:
                                        self.pd.add_item_message(
                                            _("dir: {0}").format(path),
                                            timestamp,
                                            MSG_INFO,
                                            _("Unpackaged directory"),
                                            msg_type=MSG_UNPACKAGED,
                                            parent="unpackaged")
                                else:
                                        newdirs.append(d)
                        dirs[:] = newdirs

                        for f in sorted(files):
                                timestamp = misc.time_to_timestamp(time.time())
                                path = os.path.normpath(os.path.join(
                                    orig_root, f))
                                if path not in allentries or allentries[path] \
                                    not in ["file", "link", "hardlink"]:
                                        self.pd.add_item_message(
                                            _("file: {0}").format(path),
                                            timestamp, MSG_INFO,
                                            _("Unpackaged file"),
                                            msg_type=MSG_UNPACKAGED,
                                            parent="unpackaged")

        def __process_msgs(self, entries, pfmri, msg_level, result, needs_fix,
            repairs):
                """Generate plan message for verify result."""

                timestamp = misc.time_to_timestamp(time.time())
                ffmri = str(pfmri)
                self.pd.add_item_message(ffmri, timestamp,
                    msg_level, _("{pkg_name:70} {result:>7}").format(
                    pkg_name=pfmri.get_pkg_stem(),
                    result=result))
                timestamp = misc.time_to_timestamp(time.time())

                for act, errors, warnings, info, oing_fmri in entries:
                        if act:
                                item_id = act.distinguished_name()
                                if oing_fmri:
                                    item_id += ' (from {0})'.format(
                                        oing_fmri.get_pkg_stem(anarchy=True))
                                parent = ffmri
                        else:
                                item_id = ffmri
                                parent = None
                        for x in errors:
                                self.pd.add_item_message(item_id,
                                    timestamp, MSG_ERROR,
                                    _("ERROR: {0}").format(x),
                                    parent=parent)
                        for x in warnings:
                                self.pd.add_item_message(item_id,
                                    timestamp, MSG_WARNING,
                                    _("WARNING: {0}").format(x),
                                    parent=parent)
                        for x in info:
                                self.pd.add_item_message(item_id,
                                    timestamp, MSG_INFO,
                                    _("{0}").format(x),
                                    parent=parent)

                if needs_fix:
                    # Eliminate policy-based entries with no repair
                    # action.
                    for x in needs_fix:
                        if x[0] in repairs:
                            if x[1] is not None:
                                repairs[x[0]].append(
                                    x[1])
                        else:
                            if x[1] is None:
                                repairs[x[0]] = []
                            else:
                                repairs[x[0]] = [x[1]]

        def __get_overlaying_act_from_cache(self, path, overlay_entries):
                """Get overlaying action from overlay_entries cache."""

                for e in overlay_entries[path]:
                        if e[2] == 'overlaying':
                                return e[0], e[1]
                return None, None

        def __add_to_processed(self, oing_fmri, overlay, def_pkgs, pfmri, act,
            errors, warnings, pinfo):
                """Add newly processed actions results into cache."""

                # If found overlaying package.
                if oing_fmri:
                        # If the action is an overlaid one, attach the
                        # overlaying fmri for msg print.
                        if overlay == "overlaid":
                            def_pkgs[
                                pfmri].append((act, errors, warnings, pinfo,
                                oing_fmri))
                        # The overlaying action is itself.
                        else:
                            def_pkgs[
                                pfmri].append((act, errors, warnings, pinfo,
                                None))
                else:
                        def_pkgs[
                            pfmri].append((act, errors, warnings, pinfo,
                            None))

        def __process_per_overlay_action(self, args, pfmri, entry,
            def_pkgs, verifypaths, overlaypaths, overlay_entries, pt):
                """Process per overlay action."""

                act = entry[0]
                overlay = entry[1]
                path = act.attrs.get("path")
                # Try the overlay_entries cache first.
                oing_fmri, oing_act = \
                    self.__get_overlaying_act_from_cache(
                        path, overlay_entries)
                # If found, process it directly.
                if oing_act:
                    act, errors, warnings, pinfo, \
                    oing_fmri = \
                        self.__process_verify_result(
                            act, pfmri, pt,
                            verifypaths=verifypaths,
                            overlaypaths=overlaypaths,
                            ovlying_fmri=oing_fmri,
                            ovlying_act=oing_act)
                elif args:
                        # Not all fmris were processed, we need to find the
                        # overlaying action.
                        #
                        # Also need to collect newly found overlaying
                        # actions into overlay_entries if any.
                        act, errors, warnings, pinfo, oing_fmri = \
                            self.__process_verify_result(
                            act, pfmri, pt,
                            verifypaths=verifypaths,
                            overlaypaths=overlaypaths,
                            ovly_entries=overlay_entries)
                else:
                        # All fmris were processed, if the cache didn't contain
                        # the action, that means no overlaying action.
                        #
                        # We need to skip overlaying action finding, since we
                        # already know no overlaying action in the cache.
                        act, errors, warnings, pinfo, oing_fmri = \
                            self.__process_verify_result(
                            act, pfmri, pt,
                            verifypaths=verifypaths,
                            overlaypaths=overlaypaths,
                            skip_ovlying=True)
                self.__add_to_processed(oing_fmri, overlay, def_pkgs, pfmri,
                    act, errors, warnings, pinfo)

        def __check_attr_mismatch_between_actions(self, overlaid, overlaying):
                """Check attribute mismatch between overlaying and overlaid
                 actions."""

                overlaid_act = overlaid[1]
                overlaying_act = overlaying[1]
                o_attr_overlaid = overlaid_act.attrs.get("overlay-attributes")
                o_attr_overlaying = overlaying_act.attrs.get(
                    "overlay-attributes")
                owner_overlaid = overlaid_act.attrs["owner"]
                owner_overlaying = overlaying_act.attrs["owner"]
                mode_overlaid = overlaid_act.attrs["mode"]
                mode_overlaying = overlaying_act.attrs["mode"]
                group_overlaid = overlaid_act.attrs["group"]
                group_overlaying = overlaying_act.attrs["group"]

                msgs = []
                if owner_overlaid != owner_overlaying:
                        msgs.append(_("owner: {0} does not match overlaid "
                            "package owner: {1}").format(owner_overlaying,
                            owner_overlaid))
                if mode_overlaid != mode_overlaying:
                        msgs.append(_("mode: {0} does not match overlaid "
                            "package mode: {1}").format(mode_overlaying,
                            mode_overlaid))
                if group_overlaid != group_overlaying:
                        msgs.append(_("group: {0} does not match overlaid "
                            "package group: {1}").format(group_overlaying,
                            group_overlaid))
                if not msgs:
                        return

                item_id = str(overlaying[0])
                act_id = overlaid_act.distinguished_name()
                msg_level = MSG_INFO
                result = "OK"

                if o_attr_overlaid == "deny" or o_attr_overlaying == "deny":
                        msg_level = MSG_ERROR

                # Check if there is already an FMRI-level message;
                # update it or add a new one if necessary.
                item_msgs = self.pd.get_parsable_item_messages()
                added_msgs = None
                if item_id in item_msgs and "messages" in item_msgs[item_id]:
                        added_msgs = item_msgs[item_id]["messages"]
                add_msg = False
                if added_msgs:
                        if (added_msgs[0]["msg_level"] == MSG_INFO and
                            msg_level == MSG_ERROR):
                                # Empty the current message list.
                                added_msgs[:] = []
                                add_msg = True
                else:
                        add_msg = True

                timestamp = misc.time_to_timestamp(time.time())
                if add_msg:
                        self.pd.add_item_message(item_id, timestamp, msg_level,
                            _("{pkg_name:70} {result:>7}").format(
                            pkg_name=overlaying[0].get_pkg_stem(),
                            result=result))
                self.pd.add_item_message(act_id, timestamp, msg_level,
                    _("Overlaid package: {0}").format(
                    overlaid[0].get_pkg_stem()), parent=item_id)

                for msg in msgs:
                        if msg_level == MSG_ERROR:
                                imsg = _("ERROR: {0}").format(msg)
                        else:
                                imsg = msg
                        self.pd.add_item_message(act_id, timestamp, msg_level,
                            imsg, parent=item_id)

        def __verify_fmris(self, repairs, args, proposed_fmris, pt, verifypaths,
            overlaypaths):
                """Verify FRMIs."""

                path_only = bool(verifypaths or overlaypaths)
                overlay_entries = {}
                def_pkgs = {}  # deferred packages
                def_acts = {}  # deferred actions
                for pfmri in proposed_fmris:
                        entries = []
                        needs_fix = []
                        result = "OK"
                        failed = False
                        msg_level = MSG_INFO

                        # Since every entry returned by verify might not be
                        # something needing repair, the relevant information
                        # for each package must be accumulated first to find
                        # an overall success/failure result and then the
                        # related messages output for it.
                        verify_path_count = len(verifypaths)
                        overlay_path_count = len(overlaypaths)
                        for act, errors, warnings, pinfo, overlay in \
                            self.image.verify(pfmri, pt,
                            verifypaths=verifypaths,
                            overlaypaths=overlaypaths, verbose=True,
                            forever=True):
                                if not path_only and overlay:
                                        path = act.attrs.get("path")
                                        if path not in overlay_entries:
                                            overlay_entries[path] = []
                                        overlay_entries[path].append(
                                            (pfmri, act, overlay))

                                        if pfmri not in def_acts:
                                            def_acts[pfmri] = []
                                        def_acts[pfmri].append((act, overlay))
                                else:
                                        entries.append((act, errors, warnings,
                                            pinfo, None))
                                # Try to determine the package's status and
                                # message type. This is subject to change if
                                # the package contains overlay actions.
                                if errors:
                                        failed = True
                                        result = "ERROR"
                                        msg_level = MSG_ERROR
                                        # Some errors are based on policy (e.g.
                                        # signature policy) and not a specific
                                        # action, so act may be None.
                                        needs_fix.append((pfmri, act))
                                elif not failed and warnings:
                                        result = "WARNING"
                                        msg_level = MSG_WARNING

                        # Defer final processing of package if verification was
                        # deferred for any of its actions.
                        if pfmri in def_acts:
                                def_pkgs[pfmri] = entries
                                continue

                        if (path_only and verify_path_count == len(verifypaths)
                            and overlay_path_count == len(overlaypaths)):
                                # When verifying paths, omit packages without any
                                # matches from output.
                                continue
                        self.__process_msgs(entries, pfmri, msg_level, result,
                            needs_fix, repairs)
                        if path_only and not overlaypaths and not verifypaths:
                                return

                # No need to proceed for path only case.
                if path_only:
                        return

                # Process deferred actions.
                for pfmri, entries in def_acts.items():
                        for entry in entries:
                                self.__process_per_overlay_action(args, pfmri,
                                    entry, def_pkgs, verifypaths,
                                    overlaypaths, overlay_entries, pt)

                # Generate messages for all processed packages with overlay
                # actions.
                for pfmri, entries in def_pkgs.items():
                        failed = False
                        result = "OK"
                        msg_level = MSG_INFO
                        needs_fix = []
                        for act, errors, warnings, pinfo, oing_fmri in entries:
                                # Try to determine the package's status and
                                # message type.
                                if errors:
                                        failed = True
                                        result = "ERROR"
                                        msg_level = MSG_ERROR
                                        if oing_fmri:
                                                # Only append overlaying action
                                                # if not all packages are
                                                # verified. Otherwise, the
                                                # overlaying action will be
                                                # append later.
                                                if args:
                                                        needs_fix.append((
                                                            oing_fmri, act))
                                        else:
                                                needs_fix.append((pfmri, act))
                                elif not failed and warnings:
                                        result = "WARNING"
                                        msg_level = MSG_WARNING

                        self.__process_msgs(entries, pfmri, msg_level, result,
                            needs_fix, repairs)

                # Generate overlay-specific messages.
                for path, entries in overlay_entries.items():
                        overlaid = None
                        overlaying = None
                        for e in entries:
                                if e[2] == "overlaid":
                                        overlaid = e
                                elif e[2] == "overlaying":
                                        overlaying = e
                        if overlaid and overlaying:
                                self.__check_attr_mismatch_between_actions(
                                    overlaid, overlaying)

        def plan_fix(self, args, unpackaged=False, unpackaged_only=False,
                verify_paths=misc.EmptyI):
                """Determine the changes needed to fix the image."""

                self.__plan_op()
                self.__evaluate_excludes()

                pt = self.__progtrack
                pt.plan_all_start()

                if args:
                        proposed_dict, self.__match_rm = self.__match_user_fmris(
                            self.image, args, self.MATCH_INST_VERSIONS)

                        # merge patterns together
                        proposed_fixes = sorted(set([
                            f
                            for each in proposed_dict.values()
                            for f in each
                        ]))
                else:
                        # No FMRIs specified, verify all packages
                        proposed_fixes = list(self.image.gen_installed_pkgs(
                            ordered=True))

                repairs = {}
                overlaypaths = set()
                verifypaths = set(a.lstrip(os.path.sep) for a in verify_paths)

                if not verify_paths:
                        pt.plan_start(pt.PLAN_PKG_VERIFY, goal=len(proposed_fixes))

                        # Verify unpackaged contents.
                        if unpackaged or unpackaged_only:
                                dup_be_name = "duplicate_livebe_for_verify"
                                try:
                                        self.__process_unpackaged(
                                            proposed_fixes, pt=pt,
                                            dup_be_name=dup_be_name)
                                finally:
                                        # Clean up the BE used for verify.
                                        bootenv.BootEnv.cleanup_be(dup_be_name)
                                pt.plan_done(pt.PLAN_PKG_VERIFY)
                                if unpackaged_only:
                                        self.__finish_plan(plandesc.EVALUATED_PKGS)
                                        return
                                # Otherwise we reset the goals for packaged
                                # contents.
                                pt.plan_start(pt.PLAN_PKG_VERIFY, goal=len(
                                    proposed_fixes))
                        self.__verify_fmris(repairs, args, proposed_fixes, pt,
                            verifypaths, overlaypaths)
                else:
                        pt.plan_start(pt.PLAN_PKG_VERIFY, goal=len(verifypaths))

                        self.__verify_fmris(repairs, args, proposed_fixes, pt,
                            verifypaths, overlaypaths)

                        timestamp = misc.time_to_timestamp(time.time())
                        for path_not_found in verifypaths:
                                pt.plan_add_progress(pt.PLAN_PKG_VERIFY)
                                self.pd.add_item_message("path not found",
                                    timestamp, MSG_WARNING,
                                    _("{path} is not found in the image").format(
                                        path=path_not_found))

                        if args and overlaypaths:
                                # Only perform verification for the rest of packages
                                # if FMRIs are provided and there are actions with
                                # overlay=allow found in those FMRIs. In the second
                                # pass, only look for actions with overlay=true.
                                pfixes = set(proposed_fixes)
                                path_fmri = [
                                    f
                                    for f in self.image.gen_installed_pkgs(
                                        ordered=True)
                                        if f not in pfixes
                                ]
                                self.__verify_fmris(repairs, args, path_fmri, pt,
                                    set(), overlaypaths)

                pt.plan_done(pt.PLAN_PKG_VERIFY)
                # If no repairs, finish the plan.
                if not repairs:
                        self.__finish_plan(plandesc.EVALUATED_PKGS)
                        return

                # Repair anything we failed to verify.
                pt.plan_start(pt.PLAN_PKG_FIX, goal=len(repairs))
                for fmri, actions in repairs.items():
                        pt.plan_add_progress(pt.PLAN_PKG_FIX)
                        # Need to get all variants otherwise evaluating the
                        # pkgplan will fail in signature verification.
                        m = self.image.get_manifest(fmri, ignore_excludes=True)
                        pp = pkgplan.PkgPlan(self.image)
                        pp.propose_repair(fmri, m, actions, [])
                        pp.evaluate(self.__old_excludes, self.__new_excludes)
                        self.pd.pkg_plans.append(pp)

                pt.plan_done(pt.PLAN_PKG_FIX)
                pt.plan_all_done()
                self.__finish_plan(plandesc.EVALUATED_PKGS)

        def plan_noop(self):
                """Create a plan that doesn't change the package contents of
                the current image."""
                self.__plan_op()
                self.pd._fmri_changes = []
                self.pd.state = plandesc.EVALUATED_PKGS

        @staticmethod
        def __fmris2dict(fmri_list):
                return  dict([
                    (f.pkg_name, f)
                    for f in fmri_list
                ])

        @staticmethod
        def __dicts2fmrichanges(olddict, newdict):
                return [
                    (olddict.get(k, None), newdict.get(k, None))
                    for k in set(list(olddict.keys()) + list(newdict.keys()))
                ]

        def reboot_advised(self):
                """Check if evaluated imageplan suggests a reboot"""
                assert self.state >= plandesc.MERGED_OK
                return self.pd._actuators.reboot_advised()

        def reboot_needed(self):
                """Check if evaluated imageplan requires a reboot"""
                assert self.pd.state >= plandesc.MERGED_OK
                return self.pd._actuators.reboot_needed()

        def boot_archive_needed(self):
                """True if boot archive needs to be rebuilt"""
                assert self.pd.state >= plandesc.MERGED_OK
                return self.pd._need_boot_archive

        def get_solver_errors(self):
                """Returns a list of strings for all FMRIs evaluated by the
                solver explaining why they were rejected.  (All packages
                found in solver's trim database.)"""
                return self.pd.get_solver_errors()

        def get_plan(self, full=True):
                if full:
                        return str(self)

                output = ""
                for t in self.pd._fmri_changes:
                        output += "{0} -> {1}\n".format(*t)
                return output

        def gen_new_installed_pkgs(self):
                """Generates all the fmris which will be in the new image."""
                assert self.pd.state >= plandesc.EVALUATED_PKGS
                fmri_set = set(self.image.gen_installed_pkgs())

                for p in self.pd.pkg_plans:
                        p.update_pkg_set(fmri_set)

                for pfmri in fmri_set:
                        yield pfmri

        def __gen_only_new_installed_info(self):
                """Generates fmri-manifest pairs for all packages which are
                being installed (or fixed, etc.)."""
                assert self.pd.state >= plandesc.EVALUATED_PKGS

                for p in self.pd.pkg_plans:
                        if p.destination_fmri:
                                assert p.destination_manifest
                                yield p.destination_fmri, p.destination_manifest

        def __gen_outgoing_info(self):
                """Generates fmri-manifest pairs for all the packages which are
                being removed."""
                assert self.pd.state >= plandesc.EVALUATED_PKGS

                for p in self.pd.pkg_plans:
                        if p.origin_fmri and \
                            p.origin_fmri != p.destination_fmri:
                                assert p.origin_manifest
                                yield p.origin_fmri, p.origin_manifest

        def gen_new_installed_actions_bytype(self, atype, implicit_dirs=False):
                """Generates actions of type 'atype' from the packages in the
                future image."""

                return self.__gen_star_actions_bytype(atype,
                    self.gen_new_installed_pkgs, implicit_dirs=implicit_dirs)

        def gen_only_new_installed_actions_bytype(self, atype,
            implicit_dirs=False, excludes=misc.EmptyI):
                """Generates actions of type 'atype' from packages being
                installed."""

                return self.__gen_star_actions_bytype_from_extant_manifests(
                    atype, self.__gen_only_new_installed_info, excludes,
                    implicit_dirs=implicit_dirs)

        def gen_outgoing_actions_bytype(self, atype,
            implicit_dirs=False, excludes=misc.EmptyI):
                """Generates actions of type 'atype' from packages being
                removed (not necessarily actions being removed)."""

                return self.__gen_star_actions_bytype_from_extant_manifests(
                    atype, self.__gen_outgoing_info, excludes,
                    implicit_dirs=implicit_dirs)

        def __gen_star_actions_bytype(self, atype, generator, implicit_dirs=False):
                """Generate installed actions of type 'atype' from the package
                fmris emitted by 'generator'.  If 'implicit_dirs' is True, then
                when 'atype' is 'dir', directories only implicitly delivered
                in the image will be emitted as well."""

                assert self.pd.state >= plandesc.EVALUATED_PKGS

                # Don't bother accounting for implicit directories if we're not
                # looking for them.
                if implicit_dirs:
                        if atype != "dir":
                                implicit_dirs = False
                        else:
                                da = pkg.actions.directory.DirectoryAction

                for pfmri in generator():
                        m = self.image.get_manifest(pfmri, ignore_excludes=True)
                        if implicit_dirs:
                                dirs = set() # Keep track of explicit dirs
                        for act in m.gen_actions_by_type(atype,
                            excludes=self.__new_excludes):
                                if implicit_dirs:
                                        dirs.add(act.attrs["path"])
                                yield act, pfmri
                        if implicit_dirs:
                                for d in m.get_directories(self.__new_excludes):
                                        if d not in dirs:
                                                yield da(path=d, implicit="true"), pfmri

        def __gen_star_actions_bytype_from_extant_manifests(self, atype,
            generator, excludes, implicit_dirs=False):
                """Generate installed actions of type 'atype' from the package
                manifests emitted by 'generator'.  'excludes' is a list of
                variants and facets which should be excluded from the actions
                generated.  If 'implicit_dirs' is True, then when 'atype' is
                'dir', directories only implicitly delivered in the image will
                be emitted as well."""

                assert self.pd.state >= plandesc.EVALUATED_PKGS

                # Don't bother accounting for implicit directories if we're not
                # looking for them.
                if implicit_dirs:
                        if atype != "dir":
                                implicit_dirs = False
                        else:
                                da = pkg.actions.directory.DirectoryAction

                for pfmri, m in generator():
                        if implicit_dirs:
                                dirs = set() # Keep track of explicit dirs
                        for act in m.gen_actions_by_type(atype,
                            excludes=excludes):
                                if implicit_dirs:
                                        dirs.add(act.attrs["path"])
                                yield act, pfmri

                        if implicit_dirs:
                                for d in m.get_directories(excludes):
                                        if d not in dirs:
                                                yield da(path=d,
                                                    implicit="true"), pfmri

        def __get_directories(self):
                """ return set of all directories in target image """
                # always consider var and the image directory fixed in image...
                if self.__directories == None:
                        # It's faster to build a large set and make a small
                        # update to it than to do the reverse.
                        dirs = set((
                            os.path.normpath(d[0].attrs["path"])
                            for d in self.gen_new_installed_actions_bytype("dir",
                                implicit_dirs=True)
                        ))
                        dirs.update([
                            self.image.imgdir.rstrip("/"),
                            "var",
                            "var/sadm",
                            "var/sadm/install"
                        ])
                        self.__directories = dirs
                return self.__directories

        def __get_symlinks(self):
                """ return a set of all symlinks in target image"""
                if self.__symlinks == None:
                        self.__symlinks = set((
                            a.attrs["path"]
                            for a, pfmri in self.gen_new_installed_actions_bytype("link")
                        ))
                return self.__symlinks

        def __get_hardlinks(self):
                """ return a set of all hardlinks in target image"""
                if self.__hardlinks == None:
                        self.__hardlinks = set((
                            a.attrs["path"]
                            for a, pfmri in self.gen_new_installed_actions_bytype("hardlink")
                        ))
                return self.__hardlinks

        def __get_licenses(self):
                """ return a set of all licenses in target image"""
                if self.__licenses == None:
                        self.__licenses = set((
                            a.attrs["license"]
                            for a, pfmri in self.gen_new_installed_actions_bytype("license")
                        ))
                return self.__licenses

        def __get_legacy(self):
                """ return a set of all legacy actions in target image"""
                if self.__legacy == None:
                        self.__legacy = set((
                            a.attrs["pkg"]
                            for a, pfmri in self.gen_new_installed_actions_bytype("legacy")
                        ))
                return self.__legacy

        @staticmethod
        def __check_inconsistent_types(actions, oactions):
                """Check whether multiple action types within a namespace group
                deliver to a given name in that space."""

                ntypes = set((a[0].name for a in actions))
                otypes = set((a[0].name for a in oactions))

                # We end up with nothing at this path, or start and end with one
                # of the same type, or we just add one type to an empty path.
                if len(ntypes) == 0 or (len(ntypes) == 1 and len(otypes) <= 1):
                        return None

                # We have fewer types, so actions are getting removed.
                if len(ntypes) < len(otypes):
                        # If we still end up in a broken state, signal the
                        # caller that we should move forward, but not remove
                        # anything at this path.  Note that the type on the
                        # filesystem may not match any of the remaining types.
                        if len(ntypes) > 1:
                                return "nothing", None

                        assert len(ntypes) == 1

                        # If we end up in a sane state, signal the caller that
                        # we should make sure the right contents are in place.
                        # This implies that the actions remove() method should
                        # handle when the action isn't present.
                        if actions[0][0].name != "dir":
                                return "fixup", actions[0]

                        # If we end up with a directory, then we need to be
                        # careful to choose a non-implicit directory as the
                        # fixup action.
                        for a in actions:
                                if "implicit" not in a[0].attrs:
                                        return "fixup", a
                        else:
                                # If we only have implicit directories left,
                                # make up the rest of the attributes.
                                a[0].attrs.update({"mode": "0755", "owner":
                                    "root", "group": "root"})
                                return "fixup", a

                # If the broken packages remain unchanged across the plan, then
                # we can ignore it.  We just check that the packages haven't
                # changed.
                sort_key = operator.itemgetter(1)
                actions = sorted(actions, key=sort_key)
                oactions = sorted(oactions, key=sort_key)
                if ntypes == otypes and \
                    all(o[1] == n[1] for o, n in zip(oactions, actions)):
                        return "nothing", None

                return "error", actions

        @staticmethod
        def __check_duplicate_actions(actions, oactions):
                """Check whether we deliver more than one action with a given
                key attribute value if only a single action of that type and
                value may be delivered."""

                # We end up with no actions or start with one or none and end
                # with exactly one.
                if len(actions) == 0 or (len(oactions) <= len(actions) == 1):
                        if (len(oactions) > 1 and
                            any(a[0].attrs.get("overlay") == "true"
                                for a in oactions)):
                                # If more than one action is being removed and
                                # one of them is an overlay, then suppress
                                # removal of the overlaid actions (if any) to
                                # ensure preserve rules of overlay action apply.
                                return "overlay", None
                        return None

                # Removing actions.
                if len(actions) < len(oactions):
                        # If any of the new actions is an overlay, suppress
                        # the removal of the overlaid action.
                        if any(a[0].attrs.get("overlay") == "true"
                            for a in actions):
                                return "overlay", None

                        # If we still end up in a broken state, signal the
                        # caller that we should move forward, but not remove
                        # any actions.
                        if len(actions) > 1 or \
                            any("preserve" in a[0].attrs for a in actions):
                                return "nothing", None

                        # If we end up in a sane state, signal the caller that
                        # we should make sure the right contents are in place.
                        # This implies that the action's remove() method should
                        # handle when the action isn't present.
                        return "fixup", actions[0]

                # If the broken paths remain unchanged across the plan, then we
                # can ignore it.  We have to resort to stringifying the actions
                # in order to sort them since the usual sort is much lighter
                # weight.
                oactions.sort(key=lambda x: str(x[0]))
                actions.sort(key=lambda x: str(x[0]))
                if len(oactions) == len(actions) and \
                    all(o[0] == n[0] for o, n, in zip(oactions, actions)):
                        return "nothing", None

                # For file actions, delivery of two actions to a single point is
                # permitted if:
                #   * there are only two actions in conflict
                #   * one action has 'preserve' set and 'overlay=allow'
                #   * the other action has 'overlay=true'
                if len(actions) == 2:
                        overlayable = overlay = None
                        for act, ignored in actions:
                                if (act.name == "file" and
                                    act.attrs.get("overlay") == "allow" and
                                    "preserve" in act.attrs):
                                        overlayable = act
                                elif (act.name == "file" and
                                    act.attrs.get("overlay") == "true"):
                                        overlay = act
                        if overlayable and overlay:
                                # Found both an overlayable action and the
                                # action that overlays it.
                                ignore = ["preserve"]
                                # If neither overlay nor overlayable action
                                # has "deny" set in "overlay-attributes"
                                if ("deny" not in overlay.attrlist(
                                    "overlay-attributes") and "deny" not in
                                    overlayable.attrlist(
                                    "overlay-attributes")):
                                        ignore.extend(["owner", "group",
                                            "mode", "sysattr"])
                                # Need to verify mismatched attributes between
                                # overlaying action and overlaid action in
                                # testsuite.
                                elif DebugValues[
                                    "broken-conflicting-action-handling"]:
                                        ignore.extend(["owner", "group",
                                            "mode", "sysattr"])
                                errors = ImagePlan.__find_inconsistent_attrs(
                                    actions, ignore=ignore)
                                if errors:
                                        # overlay is not permitted if unique
                                        # attributes (except 'preserve') are
                                        # inconsistent
                                        return ("error", actions,
                                            api_errors.InconsistentActionAttributeError)
                                return "overlay", None

                return "error", actions

        @staticmethod
        def __find_inconsistent_attrs(actions, ignore=misc.EmptyI):
                """Find all the problem Action pairs.

                'ignore' is an optional list of attributes to ignore when
                checking for inconsistent attributes.  By default, all
                attributes listed in the 'unique_attrs' property of an
                Action are checked.
                """

                # We iterate over all pairs of actions to see if any conflict
                # with the rest.  If two actions are "safe" together, then we
                # can ignore one of them for the rest of the run, since we can
                # compare the rest of the actions against just one copy of
                # essentially identical actions.
                seen = set()
                problems = []
                for a1, a2 in itertools.combinations(actions, 2):
                        # Implicit directories don't contribute to problems.
                        if a1[0].name == "dir" and "implicit" in a1[0].attrs:
                                continue

                        if a2 in seen:
                                continue

                        # Find the attributes which are different between the
                        # two actions, and if there are none, skip the action.
                        # We have to treat "implicit" specially for implicit
                        # directories because none of the attributes except for
                        # "path" will exist.
                        diffs = a1[0].differences(a2[0])
                        if not diffs or "implicit" in diffs:
                                seen.add(a2)
                                continue

                        # If none of the different attributes is one that must
                        # be identical, then we can skip this action.
                        if not any(
                            d for d in diffs
                            if (d in a1[0].unique_attrs and
                                d not in ignore)):
                                seen.add(a2)
                                continue

                        if ((a1[0].name == "link" or a1[0].name == "hardlink") and
                           (a1[0].attrs.get("mediator") == a2[0].attrs.get("mediator")) and
                           (a1[0].attrs.get("mediator-version") != a2[0].attrs.get("mediator-version") or
                            a1[0].attrs.get("mediator-implementation") != a2[0].attrs.get("mediator-implementation"))):
                                # If two links share the same mediator and have
                                # different mediator versions and/or
                                # implementations, then permit them to collide.
                                # The imageplan will select which ones to remove
                                # and install based on the mediator configuration
                                # in the image.
                                seen.add(a2)
                                continue

                        problems.append((a1, a2))

                return problems

        @staticmethod
        def __check_inconsistent_attrs(actions, oactions):
                """Check whether we have non-identical actions delivering to the
                same point in their namespace."""

                nproblems = ImagePlan.__find_inconsistent_attrs(actions)
                oproblems = ImagePlan.__find_inconsistent_attrs(oactions)

                # If we end up with more problems than we started with, we
                # should error out.  If we end up with the same number as
                # before, then we simply leave things alone.  And if we end up
                # with fewer, then we try to clean up.
                if len(nproblems) > len(oproblems):
                        return "error", actions
                elif not nproblems and not oproblems:
                        return
                elif len(nproblems) == len(oproblems):
                        return "nothing", None
                else:
                        if actions[0][0].name != "dir":
                                return "fixup", actions[0]

                        # Find a non-implicit directory action to use
                        for a in actions:
                                if "implicit" not in a[0].attrs:
                                        return "fixup", a
                        else:
                                return "nothing", None

        def __propose_fixup(self, inst_action, rem_action, pfmri):
                """Add to the current plan a pseudo repair plan to fix up
                correctable conflicts."""

                pp, install, remove = self.__fixups.get(pfmri,
                    (None, None, None))
                if pp is None:
                        pp = pkgplan.PkgPlan(self.image)
                        if inst_action:
                                install = [inst_action]
                                remove = []
                        else:
                                install = []
                                remove = [rem_action]
                        self.__fixups[pfmri] = pp, install, remove
                elif inst_action:
                        install.append(inst_action)
                else:
                        remove.append(rem_action)

        def __evaluate_fixups(self):
                nfm = manifest.NullFactoredManifest
                for pfmri, (pp, install, remove) in self.__fixups.items():
                        pp.propose_repair(pfmri, nfm, install, remove,
                            autofix=True)
                        pp.evaluate(self.__old_excludes, self.__new_excludes)
                        self.pd.pkg_plans.append(pp)

                        # Repairs end up going into the package plan's update
                        # and remove lists, so _ActionPlans needed to be
                        # appended for each action in this fixup pkgplan to
                        # the list of related actions.
                        for action in install:
                                self.pd.update_actions.append(
                                    _ActionPlan(pp, None, action))
                        for action in remove:
                                self.pd.removal_actions.append(
                                    _ActionPlan(pp, action, None))

                # Don't process this particular set of fixups again.
                self.__fixups = {}

        def __process_conflicts(self, key, func, actions, oactions, errclass, errs):
                """The conflicting action checking functions all need to be
                dealt with in a similar fashion, so we do that work in one
                place."""

                ret = func(actions, oactions)
                if ret is None:
                        return False

                if len(ret) == 3:
                        # Allow checking functions to override default errclass.
                        msg, actions, errclass = ret
                else:
                        msg, actions = ret

                if not isinstance(msg, six.string_types):
                        return False

                if msg == "nothing":
                        for i, ap in enumerate(self.pd.removal_actions):
                                if ap and ap.src.attrs.get(ap.src.key_attr,
                                    None) == key:
                                        self.pd.removal_actions[i] = None
                elif msg == "overlay":
                        pp_needs_trimming = {}
                        moved = set()
                        # Suppress install and update of overlaid file.
                        for al in (self.pd.install_actions,
                            self.pd.update_actions):
                                for i, ap in enumerate(al):
                                        if not ap:
                                                # Action has been removed.
                                                continue

                                        attrs = ap.dst.attrs
                                        if attrs.get(ap.dst.key_attr) != key:
                                                if ("preserve" in attrs and
                                                    "original_name" in attrs):
                                                        # Possible move to a
                                                        # different location for
                                                        # editable file.
                                                        # Overlay attribute is
                                                        # not checked in case it
                                                        # was dropped as part of
                                                        # move.
                                                        moved.add(
                                                            attrs["original_name"])
                                                continue

                                        if attrs.get("overlay") != "allow":
                                                    # Only care about overlaid
                                                    # actions.
                                                    continue

                                        # Remove conflicting, overlaid actions
                                        # from plan.
                                        al[i] = None
                                        pp_needs_trimming.setdefault(id(ap.p),
                                            { "plan": ap.p, "trim": [] })
                                        pp_needs_trimming[id(ap.p)]["trim"].append(
                                            id(ap.dst))
                                        break

                        # Suppress removal of overlaid file.
                        al = self.pd.removal_actions
                        for i, ap in enumerate(al):
                                if not ap:
                                        continue

                                attrs = ap.src.attrs
                                if not attrs.get(ap.src.key_attr) == key:
                                        continue

                                if attrs.get("overlay") != "allow":
                                        # Only interested in overlaid actions.
                                        continue

                                orig_name = attrs.get("original_name",
                                    "{0}:{1}".format(ap.p.origin_fmri.get_name(),
                                        attrs["path"]))
                                if orig_name in moved:
                                        # File has moved locations; removal will
                                        # be executed, but file will be saved
                                        # for the move skipping unlink.
                                        ap.src.attrs["save_file"] = \
                                            [orig_name, "false"]
                                        break

                                al[i] = None
                                pp_needs_trimming.setdefault(id(ap.p),
                                    { "plan": ap.p, "trim": [] })
                                pp_needs_trimming[id(ap.p)]["trim"].append(
                                    id(ap.src))
                                break

                        for entry in pp_needs_trimming.values():
                                p = entry["plan"]
                                trim = entry["trim"]
                                # Can't modify the p.actions tuple, so modify
                                # the added member in-place.
                                for prop in ("added", "changed", "removed"):
                                        pval = getattr(p.actions, prop)
                                        pval[:] = [
                                            a
                                            for a in pval
                                            if id(a[1]) not in trim
                                        ]
                elif msg == "fixup":
                        self.__propose_fixup(actions[0], None, actions[1])
                elif msg == "error":
                        errs.append(errclass(actions))
                else:
                        assert False, "{0}() returned something other than " \
                            "'nothing', 'overlay', 'error', or 'fixup': '{1}'".format(
                            func.__name__, msg)

                return True

        def __seed(self, gen_func, action_classes, excludes):
                """Build a mapping from action keys to action, pfmri tuples for
                a set of action types.

                The 'gen_func' is a function which takes an action type and
                'implicit_dirs' and returns action-pfmri pairs.

                The 'action_classes' parameter is a list of action types."""

                d = {}
                for klass in action_classes:
                        self.__progtrack.plan_add_progress(
                            self.__progtrack.PLAN_ACTION_CONFLICT)
                        for a, pfmri in \
                            gen_func(klass.name, implicit_dirs=True,
                            excludes=excludes):
                                d.setdefault(a.attrs[klass.key_attr],
                                    []).append((a, pfmri))
                return d

        @staticmethod
        def __act_dup_check(tgt, key, actstr, fmristr):
                """Check for duplicate actions/fmri tuples in 'tgt', which is
                indexed by 'key'."""

                #
                # When checking for duplicate actions we have to account for
                # the fact that actions which are part of a package plan are
                # not stripped.  But the actions we're iterating over here are
                # coming from the stripped action cache, so they have had
                # assorted attributes removed (like variants, facets, etc.) So
                # to check for duplicates we have to make sure to strip the
                # actions we're comparing against.  Of course we can't just
                # strip the actions which are part of a package plan because
                # we could be removing data critical to the execution of that
                # action like original_name, etc.  So before we strip an
                # action we have to make a copy of it.
                #
                # If we're dealing with a directory action and an "implicit"
                # attribute exists, we need to preserve it.  We assume it's a
                # synthetic attribute that indicates that the action was
                # created implicitly (and hence won't conflict with an
                # explicit directory action defining the same directory).
                # Note that we've assumed that no one will ever add an
                # explicit "implicit" attribute to a directory action.
                #
                preserve = {"dir": ["implicit"]}
                if key not in tgt:
                        return False
                for act, pfmri in tgt[key]:
                        # check the fmri first since that's easy
                        if fmristr != str(pfmri):
                                continue
                        act = pkg.actions.fromstr(str(act))
                        act.strip(preserve=preserve)
                        if actstr == str(act):
                                return True
                return False

        def __update_act(self, keys, tgt, skip_dups, offset_dict,
            action_classes, sf, skip_fmris, fmri_dict):
                """Update 'tgt' with action/fmri pairs from the stripped
                action cache that are associated with the specified action
                'keys'.

                The 'skip_dups' parameter indicates if we should avoid adding
                duplicate action/pfmri pairs into 'tgt'.

                The 'offset_dict' parameter contains a mapping from key to
                offsets into the actions.stripped file and the number of lines
                to read.

                The 'action_classes' parameter contains the list of action types
                where one action can conflict with another action.

                The 'sf' parameter is the actions.stripped file from which we
                read the actual actions indicated by the offset dictionary
                'offset_dict.'

                The 'skip_fmris' parameter contains a set of strings
                representing the packages which we should not process actions
                for.

                The 'fmri_dict' parameter is a cache of previously built PkgFmri
                objects which is used so the same string isn't translated into
                the same PkgFmri object multiple times."""

                for key in keys:
                        offsets = []
                        for klass in action_classes:
                                offset = offset_dict.get((klass.name, key),
                                    None)
                                if offset is not None:
                                        offsets.append(offset)

                        for offset, cnt in offsets:
                                sf.seek(offset)
                                pns = None
                                i = 0
                                while 1:
                                        # sf is reading in binary mode
                                        line = misc.force_str(sf.readline())
                                        i += 1
                                        if i > cnt:
                                                break
                                        line = line.rstrip()
                                        if line == "":
                                                break
                                        fmristr, actstr = line.split(None, 1)
                                        if fmristr in skip_fmris:
                                                continue
                                        act = pkg.actions.fromstr(actstr)
                                        assert act.attrs[act.key_attr] == key
                                        assert pns is None or \
                                            act.namespace_group == pns
                                        pns = act.namespace_group

                                        try:
                                                pfmri = fmri_dict[fmristr]
                                        except KeyError:
                                                pfmri = pkg.fmri.PkgFmri(
                                                    fmristr)
                                                fmri_dict[fmristr] = pfmri
                                        if skip_dups and self.__act_dup_check(
                                            tgt, key, actstr, fmristr):
                                                continue
                                        tgt.setdefault(key, []).append(
                                            (act, pfmri))

        def __fast_check(self, new, old, ns):
                """Check whether actions being added and removed are
                sufficiently similar that further conflict checking on those
                actions isn't needed.

                The 'new' parameter is a dictionary mapping keys to the incoming
                actions with that as a key.  The incoming actions are actions
                delivered by packages which are being installed or updated to.

                The 'old' parameter is a dictionary mapping keys to the outgoing
                actions with that as a key.  The outgoing actions are actions
                delivered by packages which are being removed or updated from.

                The 'ns' parameter is the action namespace for the actions in
                'new' and 'old'."""

                # .keys() is being used because we're removing keys from the
                # dictionary as we go.
                for key in list(new.keys()):
                        actions = new[key]
                        assert len(actions) > 0
                        oactions = old.get(key, [])
                        # If new actions are being installed, then we need to do
                        # the full conflict checking.
                        if not oactions:
                                continue

                        unmatched_old_actions = set(range(0, len(oactions)))

                        # If the action isn't refcountable and there's more than
                        # one action, that's an error so we let
                        # __check_conflicts handle it.
                        entry = actions[0][0]
                        if not entry.refcountable and \
                            entry.globally_identical and \
                            len(actions) > 1:
                                continue

                        # Check that each incoming action has a match in the
                        # outgoing actions.
                        next_key = False
                        for act, pfmri in actions:
                                matched = False
                                aname = act.name
                                aattrs = act.attrs
                                # Compare this action with each outgoing action.
                                for i, (oact, opfmri) in enumerate(oactions):
                                        if aname != oact.name:
                                                continue
                                        # Check whether all attributes which
                                        # need to be unique are identical for
                                        # these two actions.
                                        oattrs = oact.attrs
                                        if all((
                                            aattrs.get(a) == oattrs.get(a)
                                            for a in act.unique_attrs
                                        )):
                                                matched = True
                                                break

                                # If this action didn't have a match in the old
                                # action, then this key needs full conflict
                                # checking so move on to the next key.
                                if not matched:
                                        next_key = True
                                        break
                                unmatched_old_actions.discard(i)
                        if next_key:
                                continue

                        # Check that each outgoing action has a match in the
                        # incoming actions.
                        for i, (oact, opfmri) in enumerate(oactions):
                                if i not in unmatched_old_actions:
                                        continue
                                matched = False
                                for act, pfmri in actions:
                                        if act.name != oact.name:
                                                continue
                                        if all((
                                            act.attrs.get(a) ==
                                                oact.attrs.get(a)
                                            for a in act.unique_attrs
                                        )):
                                                matched = True
                                                break
                                if not matched:
                                        next_key = True
                                        break
                                unmatched_old_actions.discard(i)
                        if next_key or unmatched_old_actions:
                                continue
                        # We know that each incoming action matches at least one
                        # outgoing action and each outgoing action matches at
                        # least one incoming action, so no further conflict
                        # checking is needed.
                        del new[key]
                        del old[key]

                # .keys() is being used because we're removing keys from the
                # dictionary as we go.
                for key in list(old.keys()):
                        # If actions that aren't in conflict are being removed,
                        # then nothing more needs to be done.
                        if key not in new:
                                del old[key]

        def __check_conflicts(self, new, old, action_classes, ns,
            errs):
                """Check all the newly installed actions for conflicts with
                existing actions."""

                for key, actions in six.iteritems(new):
                        oactions = old.get(key, [])

                        self.__progtrack.plan_add_progress(
                            self.__progtrack.PLAN_ACTION_CONFLICT)

                        if len(actions) == 1 and len(oactions) < 2:
                                continue

                        # Actions delivering to the same point in a
                        # namespace group's namespace should have the
                        # same type.
                        if type(ns) != int:
                                if self.__process_conflicts(key,
                                    self.__check_inconsistent_types,
                                    actions, oactions,
                                    api_errors.InconsistentActionTypeError,
                                    errs):
                                        continue

                        # By virtue of the above check, all actions at
                        # this point in this namespace are the same.
                        assert(len(set(a[0].name for a in actions)) <= 1)
                        assert(len(set(a[0].name for a in oactions)) <= 1)

                        # Multiple non-refcountable actions delivered to
                        # the same name is an error.
                        entry = actions[0][0]
                        if not entry.refcountable and entry.globally_identical:
                                if self.__process_conflicts(key,
                                    self.__check_duplicate_actions,
                                    actions, oactions,
                                    api_errors.DuplicateActionError,
                                    errs):
                                        continue

                        # Multiple refcountable but globally unique
                        # actions delivered to the same name must be
                        # identical.
                        elif entry.globally_identical:
                                if self.__process_conflicts(key,
                                    self.__check_inconsistent_attrs,
                                    actions, oactions,
                                    api_errors.InconsistentActionAttributeError,
                                    errs):
                                        continue

                # Ensure that overlay and preserve file semantics are handled
                # as expected when conflicts only exist in packages that are
                # being removed.
                for key, oactions in six.iteritems(old):
                        self.__progtrack.plan_add_progress(
                            self.__progtrack.PLAN_ACTION_CONFLICT)

                        if len(oactions) < 2:
                                continue

                        if key in new:
                                # Already processed.
                                continue

                        if any(a[0].name != "file" for a in oactions):
                                continue

                        entry = oactions[0][0]
                        if not entry.refcountable and entry.globally_identical:
                                if self.__process_conflicts(key,
                                    self.__check_duplicate_actions,
                                    [], oactions,
                                    api_errors.DuplicateActionError,
                                    errs):
                                        continue

        @staticmethod
        def _check_actions(nsd):
                """Return the keys in the namespace dictionary ('nsd') which
                map to actions that conflict with each other."""

                def noop(*args):
                        return None

                bad_keys = set()
                for ns, key_dict in six.iteritems(nsd):
                        if type(ns) != int:
                                type_func = ImagePlan.__check_inconsistent_types
                        else:
                                type_func = noop
                        for key, actions in six.iteritems(key_dict):
                                if len(actions) == 1:
                                        continue
                                if type_func(actions, []) is not None:
                                        bad_keys.add(key)
                                        continue
                                if not actions[0][0].refcountable and \
                                    actions[0][0].globally_identical:
                                        if ImagePlan.__check_duplicate_actions(
                                            actions, []) is not None:
                                                bad_keys.add(key)
                                                continue
                                elif actions[0][0].globally_identical and \
                                    ImagePlan.__check_inconsistent_attrs(
                                    actions, []) is not None:
                                        bad_keys.add(key)
                                        continue
                return bad_keys

        def __clear_pkg_plans(self):
                """Now that we're done reading the manifests, we can clear them
                from the pkgplans."""

                for p in self.pd.pkg_plans:
                        p.clear_dest_manifest()
                        p.clear_origin_manifest()

        def __find_all_conflicts(self):
                """Find all instances of conflicting actions.

                There are three categories of conflicting actions.  The first
                involves the notion of a 'namespace group': a set of action
                classes which install into the same namespace.  The only example
                of this is the set of filesystem actions: file, dir, link, and
                hardlink.  If more than one action delivers to a given pathname,
                all of those actions need to be of the same type.

                The second category involves actions which cannot be delivered
                multiple times to the same point in their namespace.  For
                example, files must be delivered exactly once, as must users,
                but directories or symlinks can be delivered multiple times, and
                we refcount them.

                The third category involves actions which may be delivered
                multiple times, but all of those actions must be identical in
                their core attributes.
                """

                 # We need to be able to create broken images from the testsuite.
                if DebugValues["broken-conflicting-action-handling"]:
                        self.__clear_pkg_plans()
                        return

                errs = []

                pt = self.__progtrack
                pt.plan_start(pt.PLAN_ACTION_CONFLICT)

                # Using strings instead of PkgFmri objects in sets allows for
                # much faster performance.
                new_fmris = set((str(s) for s in self.gen_new_installed_pkgs()))

                # If we're removing all packages, there won't be any conflicts.
                if not new_fmris:
                        pt.plan_done(pt.PLAN_ACTION_CONFLICT)
                        self.__clear_pkg_plans()
                        return

                # figure out which installed packages are being removed by
                # this operation
                old_fmris = set((
                    str(s) for s in self.image.gen_installed_pkgs()
                ))
                gone_fmris = old_fmris - new_fmris

                # figure out which new packages are being touched by this
                # operation.
                changing_fmris = set([
                        str(p.destination_fmri)
                        for p in self.pd.pkg_plans
                        if p.destination_fmri
                ])

                # Group action types by namespace groups
                kf = operator.attrgetter("namespace_group")
                # Unequal types are not comparable in Python 3, therefore
                # convert them to the same type 'int' first.
                def key(a):
                        kf = a.namespace_group
                        if kf is None:
                            return -1
                        elif kf == "path":
                            return 20
                        return kf
                types = sorted(six.itervalues(pkg.actions.types), key=key)

                namespace_dict = dict(
                    (ns, list(action_classes))
                    for ns, action_classes in itertools.groupby(types, kf)
                )

                pt.plan_add_progress(pt.PLAN_ACTION_CONFLICT)
                # Load information about the actions currently on the system.
                offset_dict = self.image._load_actdict(self.__progtrack)
                sf = self.image._get_stripped_actions_file()

                conflict_clean_image = \
                    self.image._load_conflicting_keys() == set()

                fmri_dict = weakref.WeakValueDictionary()
                # Iterate over action types in namespace groups first; our first
                # check should be for action type consistency.
                for ns, action_classes in six.iteritems(namespace_dict):
                        pt.plan_add_progress(pt.PLAN_ACTION_CONFLICT)
                        # There's no sense in checking actions which have no
                        # limits
                        if all(not c.globally_identical
                            for c in action_classes):
                                continue

                        # The 'new' dict contains information about the system
                        # as it will be.  We start by accumulating actions from
                        # the manifests of the packages being installed.
                        new = self.__seed(
                            self.gen_only_new_installed_actions_bytype,
                            action_classes, self.__new_excludes)

                        # The 'old' dict contains information about the system
                        # as it is now.  We start by accumulating actions from
                        # the manifests of the packages being removed.
                        old = self.__seed(self.gen_outgoing_actions_bytype,
                            action_classes, self.__old_excludes)

                        if conflict_clean_image:
                                self.__fast_check(new, old, ns)

                        with contextlib.closing(mmap.mmap(sf.fileno(), 0,
                            access=mmap.ACCESS_READ)) as msf:
                                # Skip file header.
                                msf.readline()
                                msf.readline()

                                # Update 'old' with all actions from the action
                                # cache which could conflict with the new
                                # actions being installed, or with actions
                                # already installed, but not getting removed.
                                keys = set(itertools.chain(six.iterkeys(new),
                                    six.iterkeys(old)))
                                self.__update_act(keys, old, False,
                                    offset_dict, action_classes, msf,
                                    gone_fmris, fmri_dict)

                                # Now update 'new' with all actions from the
                                # action cache which are staying on the system,
                                # and could conflict with the actions being
                                # installed.
                                keys = set(six.iterkeys(old))
                                self.__update_act(keys, new, True,
                                    offset_dict, action_classes, msf,
                                    gone_fmris | changing_fmris, fmri_dict)

                        self.__check_conflicts(new, old, action_classes, ns,
                            errs)

                del fmri_dict
                self.__clear_pkg_plans()
                sf.close()
                self.__evaluate_fixups()
                pt.plan_done(pt.PLAN_ACTION_CONFLICT)

                if errs:
                        raise api_errors.ConflictingActionErrors(errs)

        @staticmethod
        def default_keyfunc(name, act):
                """This is the default function used by get_actions when
                the caller provides no key."""

                attr_name = pkg.actions.types[name].key_attr
                return act.attrs[attr_name]

        @staticmethod
        def hardlink_keyfunc(name, act):
                """Keyfunc used in evaluate when calling get_actions
                for hardlinks."""

                return act.get_target_path()

        def get_actions(self, name, key=None):
                """Return a dictionary of actions of the type given by 'name'
                describing the target image.  If 'key' is given and not None,
                the dictionary's key will be the name of the action type's key
                attribute.  Otherwise, it's a callable taking an action as an
                argument which returns the key.  This dictionary is cached for
                quick future lookups."""
                if key is None:
                        key = self.default_keyfunc

                if (name, key) in self.__cached_actions:
                        return self.__cached_actions[(name, key)]

                d = {}
                for act, pfmri in self.gen_new_installed_actions_bytype(name):
                        t = key(name, act)
                        d.setdefault(t, []).append(act)
                self.__cached_actions[(name, key)] = d
                return self.__cached_actions[(name, key)]

        def __get_manifest(self, pfmri, intent, ignore_excludes=False):
                """Return manifest for pfmri"""
                if pfmri:
                        return self.image.get_manifest(pfmri,
                            ignore_excludes=ignore_excludes or
                            self.pd._varcets_change,
                            intent=intent)
                else:
                        return manifest.NullFactoredManifest

        def __create_intent(self, old_fmri, new_fmri, enabled_publishers):
                """Return intent strings (or None).  Given a pair
                of fmris describing a package operation, this
                routine returns intent strings to be passed to
                originating publisher describing manifest
                operations.  We never send publisher info to
                prevent cross-publisher leakage of info."""

                if self.__noexecute:
                        return None, None

                __match_intent = dict()
                __match_intent.update(self.__match_inst)
                __match_intent.update(self.__match_rm)
                __match_intent.update(self.__match_update)

                if new_fmri:
                        reference = __match_intent.get(new_fmri, None)
                        # don't leak prev. version info across publishers
                        if old_fmri:
                                if old_fmri.get_publisher() != \
                                    new_fmri.get_publisher():
                                        old_fmri = "unknown"
                                else:
                                        old_fmri = \
                                            old_fmri.get_fmri(anarchy=True)
                        # don't send pub
                        new_fmri = new_fmri.get_fmri(anarchy=True)
                else:
                        reference = __match_intent.get(old_fmri, None)
                        # don't try to send intent info to disabled publisher
                        if old_fmri.get_publisher() in enabled_publishers:
                                # don't send pub
                                old_fmri = old_fmri.get_fmri(anarchy=True)
                        else:
                                old_fmri = None

                info = {
                    "operation": self.pd._op,
                    "old_fmri" : old_fmri,
                    "new_fmri" : new_fmri,
                    "reference": reference
                }

                s = "({0})".format(";".join([
                    "{0}={1}".format(key, info[key]) for key in info
                    if info[key] is not None
                ]))

                if new_fmri:
                        return None, s    # only report new on upgrade
                elif old_fmri:
                        return s, None    # uninstall w/ enabled pub
                else:
                        return None, None # uninstall w/ disabled pub

        def add_actuator(self, phase, name, value):
                """Add an actuator to the plan.

                The actuator name ('reboot-needed', 'restart_fmri', etc.) is
                given in 'name', and the fmri string or callable is given in
                'value'.  The 'phase' parameter must be one of 'install',
                'remove', or 'update'.
                """

                if phase == "install":
                        d = self.pd._actuators.install
                elif phase == "remove":
                        d = self.pd._actuators.removal
                elif phase == "update":
                        d = self.pd._actuators.update

                if hasattr(value, "__call__"):
                        d[name] = value
                else:
                        d.setdefault(name, []).append(value)

        def __evaluate_pkg_preserved_files(self):
                """Private helper function that determines which preserved files
                have changed in ImagePlan and how."""

                assert self.state >= plandesc.MERGED_OK

                pd = self.pd

                # Track movement of preserved ("editable") files for plan
                # summary and cache management.
                moved = []
                removed = []
                installed = []
                updated = []

                # __merge_actions() adds the 'save_file' attribute to src
                # actions that are being moved somewhere else and to dest
                # actions that will be restored from a src action.  This only
                # happens when at least one of the files involved has a
                # 'preserve' attribute, so it's safe to treat either as a
                # 'preserved' ("editable") file.

                # The removal_actions are processed first since we'll determine
                # how to transform them while processing the install and update
                # actions based on the destination file state.
                for ap in pd.removal_actions:
                        src = ap.src
                        if src.name != "file":
                                continue
                        if not ("preserve" in src.attrs or
                            "save_file" in src.attrs or
                            "overlay" in src.attrs):
                                # Removed action has to be a preserved file or a
                                # source of a restore.
                                continue
                        if "elfhash" in src.attrs:
                                # Ignore erroneously tagged files.
                                continue

                        if src.attrs.get("preserve") in ("abandon",
                            "install-only"):
                                # these files are never removed.
                                continue

                        entry = [src.attrs["path"]]
                        save_file = src.attrs.get("save_file")
                        if save_file:
                                entry.append(save_file[0])
                                entry.append(src)
                        removed.append(entry)

                for ap in itertools.chain(pd.install_actions,
                    pd.update_actions):
                        orig = ap.src
                        dest = ap.dst
                        if dest.name != "file":
                                continue

                        dpres_type = dest.attrs.get("preserve")
                        if not ((orig and ("preserve" in orig.attrs or
                            "save_file" in orig.attrs or
                            "overlay" in orig.attrs)) or
                            (dpres_type or
                            "save_file" in dest.attrs or
                            "overlay" in dest.attrs)):
                                # At least one of the actions has to be a
                                # preserved file or a target of a restore.
                                continue
                        if "elfhash" in dest.attrs:
                                # Ignore erroneously tagged files.
                                continue

                        tpath = dest.attrs["path"]
                        entry = [tpath]
                        save_file = dest.attrs.get("save_file")
                        if save_file:
                                tcache_name = save_file[0]
                                for (ridx, rentry) in enumerate(removed):
                                        if len(rentry) == 1:
                                                continue

                                        rpath, rcache_name, rorig = rentry
                                        if rcache_name == tcache_name:
                                                # If the cache name for this new
                                                # file matches one of those for
                                                # a removed file, the removed
                                                # file will be renamed to this
                                                # action's path before the
                                                # action is processed.
                                                del removed[ridx]
                                                save_file = rpath
                                                orig = rorig
                                                break
                                else:
                                        save_file = None

                        if not orig and dpres_type == "install-only":
                                # For install-only, we can rely on
                                # _check_preserve.
                                try:
                                        if not dest._check_preserve(orig, ap.p):
                                                installed.append(entry)
                                except EnvironmentError as e:
                                        if e.errno != errno.EACCES:
                                                raise
                                continue
                        elif not orig:
                                # We can't rely on _check_preserve for this case
                                # as there's no existing on-disk file at the
                                # destination path yet.
                                if (dpres_type != "legacy" and
                                    dpres_type != "abandon"):
                                        # 'abandon' actions are never delivered;
                                        # 'legacy' actions are only delivered if
                                        # we're updating something already
                                        # installed or moving an existing file.
                                        installed.append(entry)
                                continue
                        elif orig.name != "file":
                                # File is being replaced with another object
                                # type.
                                updated.append(entry)
                                continue

                        # The order of these checks is significant in
                        # determining how a preserved file changed!
                        #
                        # First, check for on-disk content changes.
                        opath = orig.get_installed_path(self.image.get_root())
                        try:
                                pres_type = dest._check_preserve(orig, ap.p,
                                    orig_path=opath)
                        except EnvironmentError as e:
                                if e.errno == errno.EACCES:
                                        continue
                                else:
                                        raise

                        final_path = dest.get_installed_path(
                            self.image.get_root())

                        # If a removed action is going to be restored to
                        # complete the operation, show the removed action path
                        # as the source for the move omitting the steps
                        # in-between.  For example:
                        #  moved: testme -> newme
                        #  moved: newme -> newme.legacy
                        #  installed: newme
                        # ...becomes:
                        #  moved: testme -> newme.legacy
                        #  installed: newme
                        if save_file:
                                mpath = save_file
                        else:
                                mpath = tpath

                        if pres_type == "abandon":
                                # newly-tagged preserve=abandon files never
                                # delivered.
                                continue
                        elif pres_type == "renameold":
                                moved.append([mpath, tpath + ".old"])
                                installed.append(entry)
                                continue
                        elif pres_type == "renameold.update":
                                moved.append([mpath, tpath + ".update"])
                                installed.append(entry)
                                continue
                        elif pres_type == "legacy":
                                if orig.attrs.get("preserve") == "legacy":
                                        updated.append(entry)
                                        continue
                                # Move only happens on preserve transition and
                                # only if original already exists.
                                if os.path.isfile(opath):
                                        moved.append([mpath, tpath + ".legacy"])
                                installed.append(entry)
                                continue
                        elif pres_type == True and save_file:
                                # If the source and destination path are the
                                # same, the content won't be updated.
                                if mpath != tpath:
                                        # New content ignored in favour of old.
                                        moved.append([mpath, tpath])
                                continue

                        # Next, if on-disk file will be preserved and some other
                        # unique_attr is changing (such as mode, etc.) mark the
                        # file as "updated".
                        if (pres_type == True and
                            ImagePlan.__find_inconsistent_attrs(
                                ((orig,), (dest,)),
                                ignore=("path", "preserve"))):

                                # For 'install-only', we can only update for
                                # inconsistent attributes if the file already
                                # exists.
                                if (dpres_type != "install-only" or
                                    os.path.isfile(final_path)):
                                        updated.append(entry)
                                continue

                        # For remaining cases, what happens is based on the
                        # result of _check_preserve().
                        if pres_type == "renamenew":
                                if save_file:
                                        moved.append([mpath, tpath])
                                # Delivered content changed.
                                installed.append([tpath + ".new"])
                        elif pres_type is None:
                                # Delivered content or unique_attrs changed.
                                updated.append(entry)
                        elif pres_type == False:
                                if save_file:
                                        moved.append([mpath, tpath])
                                        continue

                                if not os.path.isfile(final_path):
                                        # File is missing or of wrong type.
                                        installed.append(entry)
                                        continue

                                # If a file is moving between packages, it will
                                # appear as an update, but may not have not have
                                # different content or unique_attrs.  Check to
                                # see if it does.
                                if ImagePlan.__find_inconsistent_attrs(
                                    ((orig,), (dest,)),
                                    ignore=("path", "preserve")):
                                        # Different unique_attrs.
                                        updated.append(entry)
                                        continue

                                attr, shash, ohash, hfunc = \
                                    digest.get_common_preferred_hash(dest, orig)
                                if shash != ohash:
                                        # Delivered content changed.
                                        updated.append(entry)
                                        continue

                # Pre-sort results for consumers.
                installed.sort()
                moved.sort()
                removed.sort()
                updated.sort()

                self.pd._preserved = {
                    "installed": installed,
                    "moved": moved,
                    "removed": removed,
                    "updated": updated,
                }

        def __evaluate_pkg_downloads(self):
                """Private helper function that determines package data to be
                downloaded and updates the plan accordingly."""

                assert self.state >= plandesc.MERGED_OK

                pd = self.pd

                for p in pd.pkg_plans:
                        cpbytes, pbytes = p.get_bytes_added()
                        if p.destination_fmri:
                                mpath = self.image.get_manifest_path(
                                    p.destination_fmri)
                                try:
                                        # Manifest data is essentially stored
                                        # three times (original, cache, catalog).
                                        # For now, include this in cbytes_added
                                        # since that's closest to where the
                                        # download cache is stored.
                                        pd._cbytes_added += \
                                            os.stat(mpath).st_size * 3
                                except EnvironmentError as e:
                                        raise api_errors._convert_error(e)
                        pd._cbytes_added += cpbytes
                        pd._bytes_added += pbytes

                # Include state directory in cbytes_added for now since it's
                # closest to where the download cache is stored.  (Twice the
                # amount is used because image state update involves using
                # a complete copy of existing state.)
                pd._cbytes_added += misc.get_dir_size(self.image._statedir) * 2

                # Our slop factor is 25%; overestimating is safer than under-
                # estimating.  This attempts to approximate how much overhead
                # the filesystem will impose on the operation.  Empirical
                # testing suggests that overhead can vary wildly depending on
                # average file size, fragmentation, zfs metadata overhead, etc.
                # For an install of a package such as solaris-small-server into
                # an image, a 12% difference between actual size and installed
                # size was found, so this seems safe enough.  (And helps account
                # for any bootarchives, fs overhead, etc.)
                pd._cbytes_added *= 1.25
                pd._bytes_added *= 1.25

                # XXX For now, include cbytes_added in bytes_added total; in the
                # future, this should only happen if they share the same
                # filesystem.
                pd._bytes_added += pd._cbytes_added
                self.__update_avail_space()

        def evaluate(self):
                """Given already determined fmri changes,
                build pkg plans and figure out exact impact of
                proposed changes"""

                assert self.pd.state == plandesc.EVALUATED_PKGS, self

                if self.pd._image_lm != \
                    self.image.get_last_modified(string=True):
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        raise api_errors.InvalidPlanError()

                self.__evaluate_pkg_plans()
                self.__merge_actions()
                self.__compile_release_notes()

                if not self.pd._li_pkg_updates and self.pd.pkg_plans:
                        # oops.  the caller requested no package updates and
                        # we couldn't satisfy that request.
                        fmri_updates = [
                                (p.origin_fmri, p.destination_fmri)
                                for p in self.pd.pkg_plans
                        ]
                        raise api_errors.PlanCreationException(
                            pkg_updates_required=fmri_updates)

                # These must be done after action merging.
                self.__evaluate_pkg_preserved_files()
                self.__evaluate_pkg_downloads()

        def __update_avail_space(self):
                """Update amount of available space on FS"""

                self.pd._cbytes_avail = misc.spaceavail(
                    self.image.write_cache_path)

                self.pd._bytes_avail = misc.spaceavail(self.image.root)
                # if we don't have a full image yet
                if self.pd._cbytes_avail < 0:
                        self.pd._cbytes_avail = self.pd._bytes_avail

        def __include_note(self, installed_dict, act, containing_fmri):
                """Decide if a release note should be shown/included.  If
                feature/pkg/self is fmri, fmri is containing package;
                if version is then 0, this is note is displayed on initial
                install only.  Otherwise, if version earlier than specified
                fmri is present in code, display release note."""

                for fmristr in act.attrlist("release-note"):
                        try:
                                pfmri = pkg.fmri.PkgFmri(fmristr)
                        except pkg.fmri.FmriError:
                                continue # skip malformed fmris
                        # any special handling here?
                        if pfmri.pkg_name == "feature/pkg/self":
                                if str(pfmri.version) == "0,5.11" \
                                    and containing_fmri.pkg_name \
                                    not in installed_dict:
                                        return True
                                else:
                                        pfmri.pkg_name = \
                                            containing_fmri.pkg_name
                        if pfmri.pkg_name not in installed_dict:
                                continue
                        installed_fmri = installed_dict[pfmri.pkg_name]
                        # if neither is successor they are equal
                        if pfmri.is_successor(installed_fmri):
                                return True
                return False

        def __get_note_text(self, act, pfmri):
                """Retrieve text for release note from repo"""
                try:
                        pub = self.image.get_publisher(pfmri.publisher)
                        hash_attr, hash_val, hash_func = \
                            digest.get_least_preferred_hash(act)
                        return self.image.transport.get_content(pub, hash_val,
                            fmri=pfmri, hash_func=hash_func)
                finally:
                        self.image.cleanup_downloads()

        def __compile_release_notes(self):
                """Figure out what release notes need to be displayed"""
                release_notes = self.pd._actuators.get_release_note_info()
                must_display = False
                notes = []

                if release_notes:
                        installed_dict = ImagePlan.__fmris2dict(
                            self.image.gen_installed_pkgs())
                        for act, pfmri in release_notes:
                                if self.__include_note(installed_dict, act,
                                    pfmri):
                                        if act.attrs.get("must-display",
                                            "false") == "true":
                                                must_display = True
                                        for l in self.__get_note_text(
                                            act, pfmri).splitlines():
                                                notes.append(misc.decode(l))

                        self.pd.release_notes = (must_display, notes)

        def __save_release_notes(self):
                """Save a copy of the release notes and store the file name"""
                if self.pd.release_notes[1]:
                        # create a file in imgdir/notes
                        dpath = os.path.join(self.image.imgdir, "notes")
                        misc.makedirs(dpath)
                        fd, path = tempfile.mkstemp(suffix=".txt",
                            dir=dpath, prefix="release-notes-")
                        tmpfile = os.fdopen(fd, "w")
                        for note in self.pd.release_notes[1]:
                                note = misc.force_str(note)
                                print(note, file=tmpfile)
                        # make file world readable
                        os.chmod(path, 0o644)
                        tmpfile.close()
                        self.pd.release_notes_name = os.path.basename(path)

        def __evaluate_pkg_plans(self):
                """Internal helper function that does the work of converting
                fmri changes into pkg plans."""

                pt = self.__progtrack
                # prefetch manifests
                prefetch_mfsts = [] # manifest, intents to be prefetched
                eval_list = []     # oldfmri, oldintent, newfmri, newintent
                                   # prefetched intents omitted
                enabled_publishers = set([
                                a.prefix
                                for a in self.image.gen_publishers()
                                ])

                #
                # XXX this could be improved, or perhaps the "do we have it?"
                # logic could be moved into prefetch_manifests, and
                # PLAN_FIND_MFST could go away?  This can be slow.
                #
                pt.plan_start(pt.PLAN_FIND_MFST)
                for oldfmri, newfmri in self.pd._fmri_changes:
                        pt.plan_add_progress(pt.PLAN_FIND_MFST)
                        old_in, new_in = self.__create_intent(oldfmri, newfmri,
                            enabled_publishers)
                        if oldfmri:
                                if not self.image.has_manifest(oldfmri):
                                        prefetch_mfsts.append((oldfmri, old_in))
                                        old_in = None # so we don't send it twice
                        if newfmri:
                                if not self.image.has_manifest(newfmri):
                                        prefetch_mfsts.append((newfmri, new_in))
                                        new_in = None
                        eval_list.append((oldfmri, old_in, newfmri, new_in))
                        old_in = new_in = None
                pt.plan_done(pt.PLAN_FIND_MFST)

                # No longer needed.
                del enabled_publishers
                self.__match_inst = {}
                self.__match_rm = {}
                self.__match_update = {}

                self.image.transport.prefetch_manifests(prefetch_mfsts,
                    ccancel=self.__check_cancel, progtrack=self.__progtrack)

                # No longer needed.
                del prefetch_mfsts

                max_items = len(eval_list)
                pt.plan_start(pt.PLAN_PKGPLAN, goal=max_items)
                same_excludes = self.__old_excludes == self.__new_excludes

                for oldfmri, old_in, newfmri, new_in in eval_list:
                        pp = pkgplan.PkgPlan(self.image)

                        if oldfmri == newfmri:
                                # When creating intent, we always prefer to send
                                # the new intent over old intent (see
                                # __create_intent), so it's not necessary to
                                # touch the old manifest in this situation.
                                m = self.__get_manifest(newfmri, new_in,
                                    ignore_excludes=True)
                                pp.propose(
                                    oldfmri, m,
                                    newfmri, m)
                                can_exclude = same_excludes
                        else:
                                pp.propose(
                                    oldfmri,
                                    self.__get_manifest(oldfmri, old_in),
                                    newfmri,
                                    self.__get_manifest(newfmri, new_in,
                                    ignore_excludes=True))
                                can_exclude = True

                        pp.evaluate(self.__old_excludes, self.__new_excludes,
                            can_exclude=can_exclude)

                        self.pd.pkg_plans.append(pp)
                        pt.plan_add_progress(pt.PLAN_PKGPLAN, nitems=1)
                        pp = None

                # No longer needed.
                del eval_list
                pt.plan_done(pt.PLAN_PKGPLAN)

        def __mediate_links(self, mediated_removed_paths):
                """Mediate links in the plan--this requires first determining the
                possible mediation for each mediator.  This is done solely based
                on the metadata of the links that are still or will be installed.
                Returns a dictionary of the proposed mediations."""

                #
                # If we're not changing mediators, and we're not changing
                # variants or facets (which could affect mediators), and we're
                # not changing any packages (which could affect mediators),
                # then mediators can't be changing so there's nothing to do
                # here.
                #
                if not self.pd._mediators_change and \
                    not self.pd._varcets_change and \
                    not self.pd._fmri_changes:
                        # return the currently configured mediators
                        return defaultdict(set, self.pd._cfg_mediators)

                prop_mediators = defaultdict(set)
                mediated_installed_paths = defaultdict(set)
                for a, pfmri in itertools.chain(
                    self.gen_new_installed_actions_bytype("link"),
                    self.gen_new_installed_actions_bytype("hardlink")):
                        mediator = a.attrs.get("mediator")
                        if not mediator:
                                # Link is not mediated.
                                continue
                        med_ver = a.attrs.get("mediator-version")
                        if med_ver:
                                med_ver = pkg.version.Version(med_ver)
                        med_impl = a.attrs.get("mediator-implementation")
                        if not (med_ver or med_impl):
                                # Link mediation is incomplete.
                                continue
                        med_priority = a.attrs.get("mediator-priority")
                        prop_mediators[mediator].add((med_priority, med_ver,
                            med_impl))
                        mediated_installed_paths[a.attrs["path"]].add((a, pfmri,
                            mediator, med_ver, med_impl))

                # Now select only the "best" mediation for each mediator;
                # items() is used here as the dictionary is altered during
                # iteration.
                cfg_mediators = self.pd._cfg_mediators
                changed_mediators = set()
                for mediator, values in prop_mediators.items():
                        med_ver_source = med_impl_source = med_priority = \
                            med_ver = med_impl = med_impl_ver = None

                        mediation = self.pd._new_mediators.get(mediator)
                        cfg_mediation = cfg_mediators.get(mediator)
                        if mediation:
                                med_ver = mediation.get("version")
                                med_ver_source = mediation.get("version-source")
                                med_impl = mediation.get("implementation")
                                med_impl_source = mediation.get(
                                    "implementation-source")
                        elif mediation is None and cfg_mediation:
                                # If a reset of mediation was not requested,
                                # use previously configured mediation as the
                                # default.
                                med_ver = cfg_mediation.get("version")
                                med_ver_source = cfg_mediation.get(
                                    "version-source")
                                med_impl = cfg_mediation.get("implementation")
                                med_impl_source = cfg_mediation.get(
                                    "implementation-source")

                        # Pick first "optimal" version and/or implementation.
                        for opt_priority, opt_ver, opt_impl in sorted(values,
                            key=cmp_to_key(med.cmp_mediations)):
                                if med_ver_source == "local":
                                        if opt_ver != med_ver:
                                                # This mediation not allowed
                                                # by local configuration.
                                                continue
                                if med_impl_source == "local":
                                        if not mediator_impl_matches(opt_impl,
                                            med_impl):
                                                # This mediation not allowed
                                                # by local configuration.
                                                continue

                                med_source = opt_priority
                                if not med_source:
                                        # 'source' is equivalent to priority,
                                        # but if no priority was specified,
                                        # treat this as 'system' to indicate
                                        # the mediation component was arbitrarily
                                        # selected.
                                        med_source = "system"

                                if med_ver_source != "local":
                                        med_ver = opt_ver
                                        med_ver_source = med_source
                                if med_impl_source != "local":
                                        med_impl = opt_impl
                                        med_impl_source = med_source
                                elif med_impl and "@" not in med_impl:
                                        # In the event a versionless
                                        # implementation is set by the
                                        # administrator, the version component
                                        # has to be stored separately for display
                                        # purposes.
                                        impl_ver = \
                                            med.parse_mediator_implementation(
                                            opt_impl)[1]
                                        if impl_ver:
                                                med_impl_ver = impl_ver
                                break

                        if cfg_mediation and \
                             (med_ver != cfg_mediation.get("version") or
                             not mediator_impl_matches(med_impl,
                                 cfg_mediation.get("implementation"))):
                                # If mediation has changed for a mediator, then
                                # all links for already installed packages will
                                # have to be removed if they are for the old
                                # mediation or repaired (installed) if they are
                                # for the new mediation.
                                changed_mediators.add(mediator)

                        prop_mediators[mediator] = {}
                        if med_ver:
                                prop_mediators[mediator]["version"] = med_ver
                        if med_ver_source:
                                prop_mediators[mediator]["version-source"] = \
                                    med_ver_source
                        if med_impl:
                                prop_mediators[mediator]["implementation"] = \
                                    med_impl
                        if med_impl_ver:
                                prop_mediators[mediator]["implementation-version"] = \
                                    med_impl_ver
                        if med_impl_source:
                                prop_mediators[mediator]["implementation-source"] = \
                                    med_impl_source

                # Determine which install and update actions should not be
                # executed based on configured and proposed mediations.  Also
                # transform any install or update actions belonging to a
                # changing mediation into removals.

                # This keeps track of which pkgplans need to be trimmed.
                act_removals = {}

                # This keeps track of which mediated paths are being delivered
                # and which need removal.
                act_mediated_paths = { "installed": {}, "removed": {} }

                for al, ptype in ((self.pd.install_actions, "added"),
                    (self.pd.update_actions, "changed")):
                        for i, ap in enumerate(al):
                                if not ap or not (ap.dst.name == "link" or
                                    ap.dst.name == "hardlink"):
                                        continue

                                mediator = ap.dst.attrs.get("mediator")
                                if not mediator:
                                        # Link is not mediated.
                                        continue

                                med_ver = ap.dst.attrs.get("mediator-version")
                                if med_ver:
                                        med_ver = pkg.version.Version(med_ver)
                                med_impl = ap.dst.attrs.get(
                                    "mediator-implementation")

                                prop_med_ver = prop_mediators[mediator].get(
                                    "version")
                                prop_med_impl = prop_mediators[mediator].get(
                                    "implementation")

                                if med_ver == prop_med_ver and \
                                    mediator_impl_matches(med_impl,
                                        prop_med_impl):
                                        # Action should be delivered.
                                        act_mediated_paths["installed"][ap.dst.attrs["path"]] = \
                                            None
                                        mediated_installed_paths.pop(
                                            ap.dst.attrs["path"], None)
                                        continue

                                # Ensure action is not delivered.
                                al[i] = None

                                act_removals.setdefault(id(ap.p),
                                    { "plan": ap.p, "added": [], "changed": [] })
                                act_removals[id(ap.p)][ptype].append(id(ap.dst))

                                cfg_med_ver = cfg_mediators.get(mediator,
                                    misc.EmptyDict).get("version")
                                cfg_med_impl = cfg_mediators.get(mediator,
                                    misc.EmptyDict).get("implementation")

                                if (mediator in cfg_mediators and
                                    mediator in prop_mediators and
                                    (med_ver == cfg_med_ver and
                                    mediator_impl_matches(med_impl,
                                        cfg_med_impl))):
                                        # Install / update actions should only be
                                        # transformed into removals if they match
                                        # the previous configuration and are not
                                        # allowed by the proposed mediation.
                                        act_mediated_paths["removed"].setdefault(
                                            ap.dst.attrs["path"], []).append(ap)

                # As an optimization, only remove rejected, mediated paths if
                # another link is not being delivered to the same path.
                for ap in (
                    ap
                    for path in act_mediated_paths["removed"]
                    for ap in act_mediated_paths["removed"][path]
                    if path not in act_mediated_paths["installed"]
                ):
                        ap.p.actions.removed.append((ap.dst,
                            None))
                        self.pd.removal_actions.append(_ActionPlan(
                            ap.p, ap.dst, None))
                act_mediated_paths = None

                for a, pfmri, mediator, med_ver, med_impl in (
                    med_link
                    for entry in mediated_installed_paths.values()
                    for med_link in entry):
                        if mediator not in changed_mediators:
                                # Action doesn't need repairing.
                                continue

                        new_med_ver = prop_mediators[mediator].get("version")
                        new_med_impl = prop_mediators[mediator].get(
                            "implementation")

                        if med_ver == new_med_ver and \
                            mediator_impl_matches(med_impl, new_med_impl):
                                # Action needs to be repaired (installed) since
                                # mediation now applies.
                                self.__propose_fixup(a, None, pfmri)
                                continue

                        if mediator not in cfg_mediators:
                                # Nothing to do.
                                continue

                        cfg_med_ver = cfg_mediators[mediator].get("version")
                        cfg_med_impl = cfg_mediators[mediator].get(
                            "implementation")
                        if a.attrs["path"] not in mediated_removed_paths and \
                            med_ver == cfg_med_ver and \
                            mediator_impl_matches(med_impl, cfg_med_impl):
                                # Action needs to be removed since mediation no
                                # longer applies and is not already set for
                                # removal.
                                self.__propose_fixup(None, a, pfmri)

                # Now trim pkgplans and elide empty entries from list of actions
                # to execute.
                for entry in act_removals.values():
                        p = entry["plan"]
                        for prop in ("added", "changed"):
                                trim = entry[prop]
                                # Can't modify the p.actions tuple directly, so
                                # modify the members in place.
                                pval = getattr(p.actions, prop)
                                pval[:] = [
                                    a
                                    for a in pval
                                    if id(a[1]) not in trim
                                ]

                return prop_mediators

        def __finalize_mediation(self, prop_mediators):
                """Merge requested and previously configured mediators that are
                being set but don't affect the plan and update proposed image
                configuration."""

                cfg_mediators = self.pd._cfg_mediators
                for m in self.pd._new_mediators:
                        prop_mediators.setdefault(m, self.pd._new_mediators[m])
                for m in cfg_mediators:
                        if m in prop_mediators:
                                continue

                        mediation = cfg_mediators[m]
                        new_mediation = mediation.copy()
                        if mediation.get("version-source") != "local":
                                new_mediation.pop("version", None)
                                del new_mediation["version-source"]
                        if mediation.get("implementation-source") != "local":
                                new_mediation.pop("implementation", None)
                                new_mediation.pop("implementation-version", None)
                                del new_mediation["implementation-source"]

                        if new_mediation:
                                # Only preserve the portion of configured
                                # mediations provided by the image administrator.
                                prop_mediators[m] = new_mediation

                for m, new_mediation in six.iteritems(prop_mediators):
                        # If after processing all mediation data, a source wasn't
                        # marked for a particular component, mark it as being
                        # sourced from 'system'.
                        if "implementation-source" in new_mediation and \
                            "version-source" not in new_mediation:
                                new_mediation["version-source"] = "system"
                        elif "version-source" in new_mediation and \
                            "implementation-source" not in new_mediation:
                                new_mediation["implementation-source"] = "system"

                # The proposed mediators become the new mediators (this accounts
                # for mediation selection done as part of a packaging operation
                # instead of being explicitly requested).

                # Initially assume mediation is changing.
                self.pd._mediators_change = True

                for m in list(prop_mediators.keys()):
                        if m not in cfg_mediators:
                                if prop_mediators[m]:
                                        # Fully-defined mediation not in previous
                                        # configuration; mediation has changed.
                                        break

                                # No change in mediation; elide it.
                                del prop_mediators[m]
                                continue

                        mediation = cfg_mediators[m]
                        if any(
                            k
                            for k in set(list(prop_mediators[m].keys()) +
                                list(mediation.keys()))
                            if prop_mediators[m].get(k) != mediation.get(k)):
                                # Mediation has changed.
                                break
                else:
                        for m in cfg_mediators:
                                if m not in prop_mediators:
                                        # Mediation has been removed from
                                        # configuration.
                                        break
                        else:
                                self.pd._mediators_change = False

                self.pd._new_mediators = prop_mediators
                # Link mediation is complete.

        def __check_reserved(self, action):
                """Check whether files are delivered to var/pkg or
                .org.opensolaris.pkg"""

                if not "path" in action.attrs:
                        return True

                dirs = ["cache", "gui_cache", "history", "license",
                    "linked", "lost+found", "publisher", "ssl", "state"
                ]

                # Also check whether files are delivered to other
                # reserved directories besides var/pkg
                if portable.osname == "sunos":
                        reserved_dirs = ["var/tmp", "var/share", "tmp", "system/volatile"]
                else:
                        reserved_dirs = []

                files = ["pkg5.image", "lock"]
                path = action.get_installed_path(self.image.root)
                dir_path = path + "/"

                for d in dirs:
                        dir_p = os.path.join(self.image.imgdir, d) + "/"
                        if dir_path.startswith(dir_p):
                                return False

                for d in reserved_dirs:
                        dir_p = os.path.join(self.image.root, d) + "/"
                        # can package these directories but not deliver anything to them
                        if dir_path.startswith(dir_p) and dir_path != dir_p:
                                return False

                for f in files:
                        fname = os.path.join(self.image.imgdir, f)
                        if path == fname:
                                return False
                return True

        def __merge_actions(self):
                """Given a set of fmri changes and their associated pkg plan,
                merge all the resultant actions for the packages being
                updated."""

                pt = self.__progtrack
                if self.pd._new_mediators is None:
                        self.pd._new_mediators = {}

                if self.image.has_boot_archive():
                        ramdisk_prefixes = tuple(
                            self.image.get_ramdisk_filelist())
                        if not ramdisk_prefixes:
                                self.pd._need_boot_archive = False
                else:
                        self.pd._need_boot_archive = False

                # now combine all actions together to create a synthetic
                # single step upgrade operation, and handle editable
                # files moving from package to package.  See theory
                # comment in execute, below.

                for pp in self.pd.pkg_plans:
                        if pp.origin_fmri and pp.destination_fmri:
                                self.__target_update_count += 1
                        elif pp.destination_fmri:
                                self.__target_install_count += 1
                        elif pp.origin_fmri:
                                self.__target_removal_count += 1

                # we now have a workable set of pkgplans to add/upgrade/remove
                # now combine all actions together to create a synthetic single
                # step upgrade operation, and handle editable files moving from
                # package to package.  See theory comment in execute, below.
                self.pd.removal_actions = []

                pt.plan_start(pt.PLAN_ACTION_MERGE)
                # cache the current image mediators within the plan
                cfg_mediators = self.pd._cfg_mediators = \
                    self.image.cfg.mediators

                mediated_removed_paths = set()
                for p in self.pd.pkg_plans:
                        pt.plan_add_progress(pt.PLAN_ACTION_MERGE)
                        for src, dest in p.gen_removal_actions():
                                if src.name == "user":
                                        self.pd.removed_users[src.attrs[
                                            "username"]] = p.origin_fmri
                                elif src.name == "group":
                                        self.pd.removed_groups[src.attrs[
                                            "groupname"]] = p.origin_fmri

                                self.pd.removal_actions.append(
                                    _ActionPlan(p, src, dest))
                                if (not (src.name == "link" or
                                    src.name == "hardlink") or
                                    "mediator" not in src.attrs):
                                        continue

                                # Keep track of which mediated paths have been
                                # removed from the system so that which paths
                                # need to be repaired can be determined.
                                mediator = src.attrs["mediator"]
                                src_version = src.attrs.get(
                                    "mediator-version")
                                src_impl = src.attrs.get(
                                    "mediator-implementation")

                                mediation = cfg_mediators.get(mediator)
                                if not mediation:
                                        # Shouldn't happen, but if it does,
                                        # drive on.
                                        continue

                                cfg_version = mediation.get("version")
                                if cfg_version:
                                        # For comparison, version must be a
                                        # string.
                                        cfg_version = \
                                            cfg_version.get_short_version()
                                cfg_impl = mediation.get("implementation")

                                if src_version == cfg_version and \
                                    mediator_impl_matches(src_impl, cfg_impl):
                                        mediated_removed_paths.add(
                                            src.attrs["path"])

                self.pd.update_actions = []
                self.pd._rm_aliases = {}
                for p in self.pd.pkg_plans:
                        pt.plan_add_progress(pt.PLAN_ACTION_MERGE)
                        for src, dest in p.gen_update_actions():
                                if dest.name == "user":
                                        self.pd.added_users[dest.attrs[
                                            "username"]] = p.destination_fmri
                                elif dest.name == "group":
                                        self.pd.added_groups[dest.attrs[
                                            "groupname"]] = p.destination_fmri
                                elif dest.name == "driver" and src:
                                        rm = \
                                            set(src.attrlist("alias")) - \
                                            set(dest.attrlist("alias"))
                                        if rm:
                                                self.pd._rm_aliases.setdefault(
                                                    dest.attrs["name"],
                                                    set()).update(rm)
                                self.pd.update_actions.append(
                                    _ActionPlan(p, src, dest))

                self.pd.install_actions = []
                errs = []
                for p in self.pd.pkg_plans:
                        pfmri = None
                        if p.destination_fmri:
                                pfmri = p.destination_fmri.get_fmri()
                        err_actions = api_errors.ImageBoundaryError(pfmri)
                        pt.plan_add_progress(pt.PLAN_ACTION_MERGE)
                        for src, dest in p.gen_install_actions():
                                if dest.name == "user":
                                        self.pd.added_users[dest.attrs[
                                            "username"]] = p.destination_fmri
                                elif dest.name == "group":
                                        self.pd.added_groups[dest.attrs[
                                            "groupname"]] = p.destination_fmri
                                # Check whether files are delivered in reserved
                                # locations.
                                if not self.__check_reserved(dest):
                                        err_actions.append_error(
                                            action=dest,
                                            err_type=api_errors.\
                                            ImageBoundaryError.RESERVED)
                                self.pd.install_actions.append(
                                    _ActionPlan(p, src, dest))
                        if not err_actions.isEmpty():
                                errs.append(err_actions)

                if errs:
                        raise api_errors.ImageBoundaryErrors(errs)

                # In case a removed user or group was added back...
                for entry in self.pd.added_groups.keys():
                        if entry in self.pd.removed_groups:
                                del self.pd.removed_groups[entry]
                for entry in self.pd.added_users.keys():
                        if entry in self.pd.removed_users:
                                del self.pd.removed_users[entry]

                self.pd.state = plandesc.MERGED_OK
                pt.plan_done(pt.PLAN_ACTION_MERGE)

                if not self.nothingtodo():
                        self.__find_all_conflicts()

                pt.plan_start(pt.PLAN_ACTION_CONSOLIDATE)
                ConsolidationEntry = namedtuple("ConsolidationEntry", "idx id")

                # cons_named maps original_name tags to the index into
                # removal_actions so we can retrieve them later.  cons_generic
                # maps the (action.name, action.key-attribute-value) tuple to
                # the same thing.  The reason for both is that cons_named allows
                # us to deal with files which change their path as well as their
                # package, while cons_generic doesn't require the "receiving"
                # package to have marked the file in any special way, plus
                # obviously it handles all actions even if they don't have
                # paths.
                cons_named = {}
                cons_generic = {}

                def hashify(v):
                        """handle key values that may be lists"""
                        if isinstance(v, list):
                                return frozenset(v)
                        else:
                                return v

                for i, ap in enumerate(self.pd.removal_actions):
                        if ap is None:
                                continue
                        pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)

                        # If the action type needs to be reference-counted, make
                        # sure it doesn't get removed if another instance
                        # remains in the target image.
                        remove = True
                        if ap.src.name == "dir" and \
                            os.path.normpath(ap.src.attrs["path"]) in \
                            self.__get_directories():
                                remove = False
                        elif ap.src.name == "link" or ap.src.name == "hardlink":
                                lpath = os.path.normpath(ap.src.attrs["path"])
                                if ap.src.name == "link":
                                        inst_links = self.__get_symlinks()
                                else:
                                        inst_links = self.__get_hardlinks()
                                if lpath in inst_links:
                                        # Another link delivers to the same
                                        # location, so assume it can't be
                                        # safely removed initially.
                                        remove = False

                                        # If link is mediated, and the mediator
                                        # doesn't match the new mediation
                                        # criteria, it is safe to remove.
                                        mediator = ap.src.attrs.get("mediator")
                                        if mediator in self.pd._new_mediators:
                                                src_version = ap.src.attrs.get(
                                                    "mediator-version")
                                                src_impl = ap.src.attrs.get(
                                                    "mediator-implementation")
                                                dest_version = \
                                                    self.pd._new_mediators[mediator].get(
                                                        "version")
                                                if dest_version:
                                                        # Requested version needs
                                                        # to be a string for
                                                        # comparison.
                                                        dest_version = \
                                                            dest_version.get_short_version()
                                                dest_impl = \
                                                    self.pd._new_mediators[mediator].get(
                                                        "implementation")
                                                if dest_version is not None and \
                                                    src_version != dest_version:
                                                        remove = True
                                                if dest_impl is not None and \
                                                    not mediator_impl_matches(
                                                        src_impl, dest_impl):
                                                        remove = True

                        elif ap.src.name == "license" and \
                            ap.src.attrs["license"] in self.__get_licenses():
                                remove = False
                        elif ap.src.name == "legacy" and \
                            ap.src.attrs["pkg"] in self.__get_legacy():
                                remove = False

                        if not remove:
                                self.pd.removal_actions[i] = None
                                if "mediator" in ap.src.attrs:
                                        mediated_removed_paths.discard(
                                            ap.src.attrs["path"])
                                continue

                        # store names of files being removed under own name
                        # or original name if specified
                        if ap.src.globally_identical:
                                attrs = ap.src.attrs
                                # Store the index into removal_actions and the
                                # id of the action object in that slot.
                                re = ConsolidationEntry(i, id(ap.src))
                                cons_generic[(ap.src.name,
                                    hashify(attrs[ap.src.key_attr]))] = re
                                if ap.src.name == "file":
                                        fname = attrs.get("original_name",
                                            "{0}:{1}".format(
                                            ap.p.origin_fmri.get_name(),
                                            attrs["path"]))
                                        cons_named[fname] = re
                                        fname = None
                                attrs = re = None

                        self.pd._actuators.scan_removal(ap)
                        if self.pd._need_boot_archive is None:
                                if self.pd._op != PKG_OP_DEHYDRATE and \
                                    ap.src.attrs.get("path", "").startswith(
                                    ramdisk_prefixes):
                                        self.pd._need_boot_archive = True

                # reduce memory consumption
                self.__directories = None
                self.__symlinks = None
                self.__hardlinks = None
                self.__licenses = None
                self.__legacy = None

                pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)

                # Construct a mapping from the install actions in a pkgplan to
                # the position they have in the plan's list.  This allows us to
                # remove them efficiently later, if they've been consolidated.
                #
                # NOTE: This means that the action ordering in the package plans
                # must remain fixed, at least for the duration of the imageplan
                # evaluation.
                plan_pos = {}
                for p in self.pd.pkg_plans:
                        for i, a in enumerate(p.gen_install_actions()):
                                plan_pos[id(a[1])] = i

                # This keeps track of which pkgplans have had install actions
                # consolidated away.
                pp_needs_trimming = set()

                # This maps destination actions to the pkgplans they're
                # associated with, which allows us to create the newly
                # discovered update _ActionPlans.
                dest_pkgplans = {}

                new_updates = []
                for i, ap in enumerate(self.pd.install_actions):
                        if ap is None:
                                continue
                        pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)

                        # In order to handle editable files that move their path
                        # or change pkgs, for all new files with original_name
                        # attribute, make sure file isn't being removed by
                        # checking removal list.  If it is, tag removal to save
                        # file, and install to recover cached version... caching
                        # is needed if directories are removed or don't exist
                        # yet.
                        if (ap.dst.name == "file" and
                            "original_name" in ap.dst.attrs and
                            ap.dst.attrs["original_name"] in cons_named):
                                cache_name = ap.dst.attrs["original_name"]
                                index = cons_named[cache_name].idx
                                ra = self.pd.removal_actions[index].src
                                assert(id(ra) == cons_named[cache_name].id)
                                # If the paths match, don't remove and add;
                                # convert to update.
                                if ap.dst.attrs["path"] == ra.attrs["path"]:
                                        new_updates.append((ra, ap.dst))
                                        # If we delete items here, the indices
                                        # in cons_named will be bogus, so mark
                                        # them for later deletion.
                                        self.pd.removal_actions[index] = None
                                        self.pd.install_actions[i] = None
                                        # No need to handle it in cons_generic
                                        # anymore
                                        del cons_generic[("file", ra.attrs["path"])]
                                        dest_pkgplans[id(ap.dst)] = ap.p
                                else:
                                        # The 'true' indicates the file should
                                        # be removed from source.  The removal
                                        # action is changed using setdefault so
                                        # that any overlay rules applied during
                                        # conflict checking remain intact.
                                        ra.attrs.setdefault("save_file",
                                            [cache_name, "true"])
                                        ap.dst.attrs["save_file"] = [cache_name,
                                            "true"]

                                cache_name = index = ra = None

                        # Similarly, try to prevent files (and other actions)
                        # from unnecessarily being deleted and re-created if
                        # they're simply moving between packages, but only if
                        # they keep their paths (or key-attribute values).
                        keyval = hashify(ap.dst.attrs.get(ap.dst.key_attr, None))
                        if (ap.dst.name, keyval) in cons_generic:
                                nkv = ap.dst.name, keyval
                                index = cons_generic[nkv].idx
                                ra = self.pd.removal_actions[index].src
                                assert(id(ra) == cons_generic[nkv].id)
                                if keyval == ra.attrs[ra.key_attr]:
                                        new_updates.append((ra, ap.dst))
                                        self.pd.removal_actions[index] = None
                                        self.pd.install_actions[i] = None
                                        dest_pkgplans[id(ap.dst)] = ap.p
                                        # Add the action to the pkgplan's update
                                        # list and mark it for removal from the
                                        # install list.
                                        ap.p.actions.changed.append((ra, ap.dst))
                                        ap.p.actions.added[plan_pos[id(ap.dst)]] = None
                                        pp_needs_trimming.add(ap.p)
                                nkv = index = ra = None

                        self.pd._actuators.scan_install(ap)
                        if self.pd._need_boot_archive is None:
                                if ap.dst.attrs.get("path", "").startswith(
                                    ramdisk_prefixes):
                                        self.pd._need_boot_archive = True

                del ConsolidationEntry, cons_generic, cons_named, plan_pos

                # Remove from the pkgplans the install actions which have been
                # consolidated away.
                for p in pp_needs_trimming:
                        # Can't modify the p.actions tuple, so modify the added
                        # member in-place.
                        p.actions.added[:] = [
                            a
                            for a in p.actions.added
                            if a is not None
                        ]
                del pp_needs_trimming

                pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)

                # We want to cull out actions where they've not changed at all,
                # leaving only the changed ones to put into
                # self.pd.update_actions.
                nu_src = manifest.Manifest()
                nu_src.set_content(content=(a[0] for a in new_updates),
                    excludes=self.__old_excludes)
                nu_dst = manifest.Manifest()
                pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)
                nu_dst.set_content(content=(a[1] for a in new_updates),
                    excludes=self.__new_excludes)
                del new_updates
                pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)
                nu_add, nu_chg, nu_rem = nu_dst.difference(nu_src,
                    self.__old_excludes, self.__new_excludes)
                pt.plan_add_progress(pt.PLAN_ACTION_CONSOLIDATE)
                # All the differences should be updates
                assert not nu_add
                assert not nu_rem
                del nu_src, nu_dst

                # Extend update_actions with the new tuples.  The package plan
                # is the one associated with the action getting installed.
                self.pd.update_actions.extend([
                    _ActionPlan(dest_pkgplans[id(dst)], src, dst)
                    for src, dst in nu_chg
                ])

                del dest_pkgplans, nu_chg

                pt.plan_done(pt.PLAN_ACTION_CONSOLIDATE)
                pt.plan_start(pt.PLAN_ACTION_MEDIATION)
                pt.plan_add_progress(pt.PLAN_ACTION_MEDIATION)

                # Mediate and repair links affected by the plan.
                prop_mediators = self.__mediate_links(mediated_removed_paths)

                pt.plan_add_progress(pt.PLAN_ACTION_MEDIATION)
                for prop in ("removal_actions", "install_actions",
                    "update_actions"):
                        pval = getattr(self.pd, prop)
                        pval[:] = [
                            a
                            for a in pval
                            if a is not None
                        ]

                pt.plan_add_progress(pt.PLAN_ACTION_MEDIATION)

                # Add any necessary repairs to plan.
                self.__evaluate_fixups()

                pt.plan_add_progress(pt.PLAN_ACTION_MEDIATION)

                # Finalize link mediation.
                self.__finalize_mediation(prop_mediators)

                pt.plan_done(pt.PLAN_ACTION_MEDIATION)
                pt.plan_start(pt.PLAN_ACTION_FINALIZE)

                # Go over update actions
                l_refresh = []
                l_actions = {}
                if self.pd.update_actions:
                        # iterating over actions is slow, so don't do it
                        # unless we have to.
                        l_actions = self.get_actions("hardlink",
                            self.hardlink_keyfunc)
                for a in self.pd.update_actions:
                        # For any files being updated that are the target of
                        # _any_ hardlink actions, append the hardlink actions
                        # to the update list so that they are not broken.
                        # Since we reference count hardlinks, update each one
                        # only once.
                        if a[2].name == "file":
                                path = a[2].attrs["path"]
                                if path in l_actions:
                                        unique_links = dict((l.attrs["path"], l)
                                            for l in l_actions[path])
                                        l_refresh.extend([
                                            _ActionPlan(a[0], l, l)
                                            for l in unique_links.values()
                                        ])
                                path = None

                        # scan both old and new actions
                        # repairs may result in update action w/o orig action
                        self.pd._actuators.scan_update(a)
                        if self.pd._need_boot_archive is None:
                                if a[2].attrs.get("path", "").startswith(
                                    ramdisk_prefixes):
                                        self.pd._need_boot_archive = True

                self.pd.update_actions.extend(l_refresh)

                # sort actions to match needed processing order
                remsort = operator.itemgetter(1)
                addsort = operator.itemgetter(2)
                self.pd.removal_actions.sort(key=remsort, reverse=True)
                self.pd.update_actions.sort(key=addsort)
                self.pd.install_actions.sort(key=addsort)

                # find the first and last hardlink in the install_actions
                fhl = lhl = -1
                for i, ap in enumerate(self.pd.install_actions):
                        if ap.dst.name == "hardlink":
                                if fhl == -1:
                                        fhl = i
                                lhl = i
                        elif fhl != -1:
                                break

                # now reorder the hardlinks to respect inter-dependencies
                if fhl != -1:
                        hardlinks = self.pd.install_actions[fhl:lhl + 1]
                        hardlinks = _reorder_hardlinks(hardlinks)
                        self.pd.install_actions[fhl:lhl + 1] = hardlinks

                # cleanup pkg_plan objects which don't actually contain any
                # changes and add any new ones to list of changes
                for p in list(self.pd.pkg_plans):
                        if p.origin_fmri != p.destination_fmri or \
                            p.actions.removed or p.actions.changed or \
                            p.actions.added:
                                pair = (p.origin_fmri, p.destination_fmri)
                                if pair not in self.pd._fmri_changes:
                                        self.pd._fmri_changes.append(pair)
                                continue
                        self.pd.pkg_plans.remove(p)
                        fmri = p.origin_fmri
                        if (fmri, fmri) in self.pd._fmri_changes:
                                self.pd._fmri_changes.remove(
                                    (fmri, fmri))
                        del p

                #
                # Sort the package plans by fmri to create predictability (and
                # some sense of order) in the download output; this is not
                # a perfect sort of this, but we only really care for things
                # we fetch over the wire.
                #
                def key_func(a):
                        if a.destination_fmri:
                                return a.destination_fmri
                        return ""

                self.pd.pkg_plans.sort(key=key_func)

                pt.plan_done(pt.PLAN_ACTION_FINALIZE)

                if self.pd._need_boot_archive is None:
                        self.pd._need_boot_archive = False

                self.pd.state = plandesc.EVALUATED_OK

        def nothingtodo(self):
                """Test whether this image plan contains any work to do """

                if self.pd.state in [plandesc.EVALUATED_PKGS,
                    plandesc.MERGED_OK]:
                        return not (self.pd._fmri_changes or
                            self.pd._new_variants or
                            (self.pd._new_facets is not None) or
                            self.pd._mediators_change or
                            self.pd.pkg_plans)
                elif self.pd.state >= plandesc.EVALUATED_OK:
                        return not (self.pd.pkg_plans or
                            self.pd._new_variants or
                            (self.pd._new_facets is not None) or
                            self.pd._mediators_change)
                assert 0, "Shouldn't call nothingtodo() for state = {0:d}".format(
                    self.pd.state)

        def preexecute(self):
                """Invoke the evaluated image plan
                preexecute, execute and postexecute
                execute actions need to be sorted across packages
                """

                assert self.pd.state == plandesc.EVALUATED_OK

                if self.pd._image_lm != \
                    self.image.get_last_modified(string=True):
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        self.pd.state = plandesc.PREEXECUTED_ERROR
                        raise api_errors.InvalidPlanError()

                if self.nothingtodo():
                        self.pd.state = plandesc.PREEXECUTED_OK
                        return

                if self.image.version != self.image.CURRENT_VERSION:
                        # Prevent plan execution if image format isn't current.
                        raise api_errors.ImageFormatUpdateNeeded(
                            self.image.root)

                if DebugValues["plandesc_validate"]:
                        # get a json copy of the plan description so that
                        # later we can verify that it wasn't updated during
                        # the pre-execution stage.
                        pd_json1 = self.pd.getstate(self.pd,
                            reset_volatiles=True)

                # Checks the index to make sure it exists and is
                # consistent. If it's inconsistent an exception is thrown.
                # If it's totally absent, it will index the existing packages
                # so that the incremental update that follows at the end of
                # the function will work correctly. It also repairs the index
                # for this BE so the user can boot into this BE and have a
                # correct index.
                if self.update_index:
                        ind = None
                        try:
                                self.image.update_index_dir()
                                ind = indexer.Indexer(self.image,
                                    self.image.get_manifest,
                                    self.image.get_manifest_path,
                                    progtrack=self.__progtrack,
                                    excludes=self.__old_excludes)
                                if ind.check_index_existence():
                                        try:
                                                ind.check_index_has_exactly_fmris(
                                                        self.image.gen_installed_pkg_names())
                                        except se.IncorrectIndexFileHash as e:
                                                self.__preexecuted_indexing_error = \
                                                    api_errors.WrapSuccessfulIndexingException(
                                                        e,
                                                        traceback.format_exc(),
                                                        traceback.format_stack()
                                                        )
                                                ind.rebuild_index_from_scratch(
                                                        self.image.\
                                                            gen_installed_pkgs()
                                                        )
                        except se.IndexingException as e:
                                # If there's a problem indexing, we want to
                                # attempt to finish the installation anyway. If
                                # there's a problem updating the index on the
                                # new image, that error needs to be
                                # communicated to the user.
                                self.__preexecuted_indexing_error = \
                                    api_errors.WrapSuccessfulIndexingException(
                                        e, traceback.format_exc(),
                                        traceback.format_stack())

                        # No longer needed.
                        del ind

                # check if we're going to have enough room
                # stat fs again just in case someone else is using space...
                self.__update_avail_space()
                if self.pd._cbytes_added > self.pd._cbytes_avail:
                        raise api_errors.ImageInsufficentSpace(
                            self.pd._cbytes_added,
                            self.pd._cbytes_avail,
                            _("Download cache"))
                if self.pd._bytes_added > self.pd._bytes_avail:
                        raise api_errors.ImageInsufficentSpace(
                            self.pd._bytes_added,
                            self.pd._bytes_avail,
                            _("Root filesystem"))

                # Remove history about manifest/catalog transactions.  This
                # helps the stats engine by only considering the performance of
                # bulk downloads.
                self.image.transport.stats.reset()

                #
                # Calculate size of data retrieval and pass it to progress
                # tracker.
                #
                npkgs = nfiles = nbytes = 0
                for p in self.pd.pkg_plans:
                        nf, nb = p.get_xferstats()
                        nbytes += nb
                        nfiles += nf

                        # It's not perfectly accurate but we count a download
                        # even if the package will do zero data transfer.  This
                        # makes the pkg stats consistent between download and
                        # install.
                        npkgs += 1
                self.__progtrack.download_set_goal(npkgs, nfiles, nbytes)

                lic_errors = []
                try:
                        # Check for license acceptance issues first to avoid
                        # wasted time in the download phase and so failure
                        # can occur early.
                        for p in self.pd.pkg_plans:
                                try:
                                        p.preexecute()
                                except api_errors.PkgLicenseErrors as e:
                                        # Accumulate all license errors.
                                        lic_errors.append(e)
                                except EnvironmentError as e:
                                        if e.errno == errno.EACCES:
                                                raise api_errors.PermissionsException(
                                                    e.filename)
                                        if e.errno == errno.EROFS:
                                                raise api_errors.ReadOnlyFileSystemException(
                                                    e.filename)
                                        raise

                        if lic_errors:
                                raise api_errors.PlanLicenseErrors(lic_errors)

                        try:
                                for p in self.pd.pkg_plans:
                                        p.download(self.__progtrack,
                                            self.__check_cancel)
                        except EnvironmentError as e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise
                        except (api_errors.InvalidDepotResponseException,
                            api_errors.TransportError) as e:
                                if p and p._autofix_pkgs:
                                        e._autofix_pkgs = p._autofix_pkgs
                                raise

                        self.image.transport.shutdown()
                        self.__progtrack.download_done()
                except:
                        self.pd.state = plandesc.PREEXECUTED_ERROR
                        raise

                self.pd.state = plandesc.PREEXECUTED_OK

                if DebugValues["plandesc_validate"]:
                        # verify that preexecution did not update the plan
                        pd_json2 = self.pd.getstate(self.pd,
                            reset_volatiles=True)
                        pkg.misc.json_diff("PlanDescription",
                            pd_json1, pd_json2, pd_json1, pd_json2)
                        del pd_json1, pd_json2

        def execute(self):
                """Invoke the evaluated image plan
                preexecute, execute and postexecute
                execute actions need to be sorted across packages
                """
                assert self.pd.state == plandesc.PREEXECUTED_OK

                if self.pd._image_lm != \
                    self.image.get_last_modified(string=True):
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        self.pd.state = plandesc.EXECUTED_ERROR
                        raise api_errors.InvalidPlanError()

                # load data from previously downloaded actions
                try:
                        for p in self.pd.pkg_plans:
                                p.cacheload()
                except EnvironmentError as e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        raise

                # check for available space
                self.__update_avail_space()
                if (self.pd._bytes_added - self.pd._cbytes_added) > self.pd._bytes_avail:
                        raise api_errors.ImageInsufficentSpace(
                            self.pd._bytes_added - self.pd._cbytes_added,
                            self.pd._bytes_avail,
                            _("Root filesystem"))

                #
                # what determines execution order?
                #
                # The following constraints are key in understanding imageplan
                # execution:
                #
                # 1) All non-directory actions (files, users, hardlinks,
                # symbolic links, etc.) must appear in only a single installed
                # package.
                #
                # 2) All installed packages must be consistent in their view of
                # action types; if /usr/openwin is a directory in one package,
                # it must be a directory in all packages, never a symbolic link;
                # this includes implicitly defined directories.
                #
                # A key goal in IPS is to be able to undergo an arbitrary
                # transformation in package contents in a single step.  Packages
                # must be able to exchange files, convert directories to
                # symbolic links, etc.; so long as the start and end states meet
                # the above two constraints IPS must be able to transition
                # between the states directly.  This leads to the following:
                #
                # 1) All actions must be ordered across packages; packages
                # cannot be updated one at a time.
                #
                #    This is readily apparent when one considers two packages
                #    exchanging files in their new versions; in each case the
                #    package now owning the file must be installed last, but it
                #    is not possible for each package to be installed before the
                #    other.  Clearly, all the removals must be done first,
                #    followed by the installs and updates.
                #
                # 2) Installs of new actions must precede updates of existing
                # ones.
                #
                #    In order to accommodate changes of file ownership of
                #    existing files to a newly created user, it is necessary
                #    for the installation of that user to precede the update of
                #    files to reflect their new ownership.
                #
                #    The exception to this rule is driver actions.  Aliases of
                #    existing drivers which are going to be removed must be
                #    removed before any new drivers are installed or updated.
                #    This prevents an error if an alias is moving from one
                #    driver to another.

                if self.nothingtodo():
                        self.pd.state = plandesc.EXECUTED_OK
                        return

                pt = self.__progtrack
                pt.set_major_phase(pt.PHASE_EXECUTE)

                # It's necessary to do this check here because the state of the
                # image before the current operation is performed is desired.
                empty_image = self.__is_image_empty()

                if not empty_image:
                        # Before proceeding, remove fast lookups database so
                        # that if _create_fast_lookups is interrupted later the
                        # client isn't left with invalid state.
                        self.image._remove_fast_lookups()

                if not self.image.is_liveroot():
                        # Check if the child is a running zone. If so run the
                        # actuator in the zone.

                        # Linked Image code uses trailing slashes, Image code
                        # does not. So we make sure that our path comparisons
                        # are always on tha same page.
                        root = os.path.normpath(self.image.root)

                        rzones = zone.list_running_zones()
                        for z, path in six.iteritems(rzones):
                                if os.path.normpath(path) == root:
                                        self.pd._actuators.set_zone(z)
                                        # there should be only on zone per path
                                        break

                self.pd._actuators.exec_prep(self.image)

                self.pd._actuators.exec_pre_actuators(self.image)

                # List of tuples of (src, dest) used to track each pkgplan so
                # that it can be discarded after execution.
                executed_pp = []
                try:
                        try:
                                pt.actions_set_goal(pt.ACTION_REMOVE,
                                    len(self.pd.removal_actions))
                                pt.actions_set_goal(pt.ACTION_INSTALL,
                                    len(self.pd.install_actions))
                                pt.actions_set_goal(pt.ACTION_UPDATE,
                                    len(self.pd.update_actions))

                                # execute removals
                                for p, src, dest in self.pd.removal_actions:
                                        p.execute_removal(src, dest)
                                        pt.actions_add_progress(
                                            pt.ACTION_REMOVE)
                                pt.actions_done(pt.ACTION_REMOVE)

                                # Update driver alias database to reflect the
                                # aliases drivers have lost in the new image.
                                # This prevents two drivers from ever attempting
                                # to have the same alias at the same time.
                                for name, aliases in \
                                    six.iteritems(self.pd._rm_aliases):
                                        driver.DriverAction.remove_aliases(name,
                                            aliases, self.image)

                                # Done with removals; discard them so memory can
                                # be re-used.
                                self.pd.removal_actions = []

                                # execute installs; if action throws a retry
                                # exception try it again afterward.
                                retries = []
                                for p, src, dest in self.pd.install_actions:
                                        try:
                                                p.execute_install(src, dest)
                                                pt.actions_add_progress(
                                                    pt.ACTION_INSTALL)
                                        except pkg.actions.ActionRetry:
                                                retries.append((p, src, dest))
                                for p, src, dest in retries:
                                        p.execute_retry(src, dest)
                                        pt.actions_add_progress(
                                            pt.ACTION_INSTALL)
                                retries = []
                                pt.actions_done(pt.ACTION_INSTALL)

                                # Done with installs, so discard them so memory
                                # can be re-used.
                                self.pd.install_actions = []

                                # execute updates
                                for p, src, dest in self.pd.update_actions:
                                        p.execute_update(src, dest)
                                        pt.actions_add_progress(
                                            pt.ACTION_UPDATE)

                                pt.actions_done(pt.ACTION_UPDATE)
                                pt.actions_all_done()
                                pt.set_major_phase(pt.PHASE_FINALIZE)

                                # Done with updates, so discard them so memory
                                # can be re-used.
                                self.pd.update_actions = []

                                # handle any postexecute operations
                                while self.pd.pkg_plans:
                                        # postexecute in reverse, but pkg_plans
                                        # aren't ordered, so does it matter?
                                        # This allows the pkgplan objects to be
                                        # discarded as they're executed which
                                        # allows memory to be-reused sooner.
                                        p = self.pd.pkg_plans.pop()
                                        p.postexecute()
                                        executed_pp.append((p.destination_fmri,
                                            p.origin_fmri))
                                        p = None

                                # save package state
                                self.image.update_pkg_installed_state(
                                    executed_pp, self.__progtrack)

                                # write out variant changes to the image config
                                if self.pd._varcets_change or \
                                    self.pd._mediators_change:
                                        self.image.image_config_update(
                                            self.pd._new_variants,
                                            self.pd._new_facets,
                                            self.pd._new_mediators)
                                # write out any changes
                                self.image._avoid_set_save(
                                    *self.pd._new_avoid_obs)
                                # An essential step to set the property
                                # "dehydrated" if dehydrate/rehydrate succeeds.
                                if self.pd._op in (PKG_OP_DEHYDRATE,
                                    PKG_OP_REHYDRATE):
                                        self.image.cfg.set_property("property",
                                            "dehydrated", self.operations_pubs)
                                        self.image.save_config()
                                else:
                                        # Mark image as modified if not calling
                                        # save_config (which will do it for us).
                                        self.image.update_last_modified()

                        except EnvironmentError as e:
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EPERM:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                elif e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                elif e.errno == errno.ELOOP:
                                        act = pkg.actions.unknown.UnknownAction()
                                        raise api_errors.ActionExecutionError(
                                            act, _("A link targeting itself or "
                                            "part of a link loop was found at "
                                            "'{0}'; a file or directory was "
                                            "expected.  Please remove the link "
                                            "and try again.").format(
                                            e.filename))
                                raise
                except pkg.actions.ActionError:
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        self.pd.state = plandesc.EXECUTED_ERROR
                        try:
                                self.pd._actuators.exec_fail_actuators(
                                    self.image)
                        except:
                                # Ensure the real cause of failure is raised.
                                pass
                        if six.PY2:
                                six.reraise(api_errors.InvalidPackageErrors([
                                    exc_value]), None, exc_tb)
                        else:
                                # six.reraise requires the first argument
                                # callable if the second argument is None.
                                # Also the traceback is automatically attached,
                                # in Python 3, so we can simply raise it.
                                raise api_errors.InvalidPackageErrors([
                                    exc_value])
                except:
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        self.pd.state = plandesc.EXECUTED_ERROR
                        try:
                                self.pd._actuators.exec_fail_actuators(
                                    self.image)
                        finally:
                                # This ensures that the original exception and
                                # traceback are used if exec_fail_actuators
                                # fails.
                                if six.PY2:
                                        six.reraise(exc_value, None, exc_tb)
                                else:
                                        raise exc_value

                else:
                        self.pd._actuators.exec_post_actuators(self.image)

                self.image._create_fast_lookups(progtrack=self.__progtrack)
                self.__save_release_notes()

                # success
                self.pd.state = plandesc.EXECUTED_OK
                self.pd._executed_ok()

                # reduce memory consumption
                self.saved_files = {}
                self.valid_directories = set()
                self.__cached_actions = {}

                # Clear out the primordial user and group caches.
                self.image._users = set()
                self.image._groups = set()
                self.image._usersbyname = {}
                self.image._groupsbyname = {}

                # Perform the incremental update to the search indexes
                # for all changed packages
                if self.update_index:
                        self.image.update_index_dir()
                        ind = indexer.Indexer(self.image,
                            self.image.get_manifest,
                            self.image.get_manifest_path,
                            progtrack=self.__progtrack,
                            excludes=self.__new_excludes)
                        try:
                                if empty_image:
                                        ind.setup()
                                if empty_image or ind.check_index_existence():
                                        ind.client_update_index(([],
                                            executed_pp), self.image)
                        except KeyboardInterrupt:
                                raise
                        except se.ProblematicPermissionsIndexException:
                                # ProblematicPermissionsIndexException
                                # is included here as there's little
                                # chance that trying again will fix this
                                # problem.
                                raise api_errors.WrapIndexingException(e,
                                    traceback.format_exc(),
                                    traceback.format_stack())
                        except Exception as e:
                                # It's important to delete and rebuild
                                # from scratch rather than using the
                                # existing indexer because otherwise the
                                # state will become confused.
                                del ind
                                # XXX Once we have a framework for
                                # emitting a message to the user in this
                                # spot in the code, we should tell them
                                # something has gone wrong so that we
                                # continue to get feedback to allow
                                # us to debug the code.
                                try:
                                        ind = indexer.Indexer(self.image,
                                            self.image.get_manifest,
                                            self.image.get_manifest_path,
                                            progtrack=self.__progtrack,
                                            excludes=self.__new_excludes)
                                        ind.rebuild_index_from_scratch(
                                            self.image.gen_installed_pkgs())
                                except Exception as e:
                                        raise api_errors.WrapIndexingException(
                                            e, traceback.format_exc(),
                                            traceback.format_stack())
                                raise \
                                    api_errors.WrapSuccessfulIndexingException(
                                        e, traceback.format_exc(),
                                        traceback.format_stack())
                        if self.__preexecuted_indexing_error is not None:
                                raise self.__preexecuted_indexing_error

        def __is_image_empty(self):
                try:
                        next(self.image.gen_installed_pkg_names())
                        return False
                except StopIteration:
                        return True

        @staticmethod
        def match_user_stems(image, patterns, match_type, raise_unmatched=True,
            raise_not_installed=True, return_matchdict=False, universe=None):
                """Given a user specified list of patterns, return a set
                of matching package stems.  Any versions specified are
                ignored.

                'match_type' indicates how matching should be restricted.  The
                possible values are:

                    MATCH_ALL
                        Matching is performed using all known package stems.

                    MATCH_INST_VERSIONS
                        Matching is performed using only installed package
                        stems.

                    MATCH_UNINSTALLED
                        Matching is performed using uninstalled packages;
                        it is an error for a pattern to match an installed
                        package.

                Note that patterns starting w/ pkg:/ require an exact match;
                patterns containing '*' will using fnmatch rules; the default
                trailing match rules are used for remaining patterns.

                Exactly duplicated patterns are ignored.

                Routine raises PlanCreationException if errors occur: it is
                illegal to specify multiple different patterns that match the
                same pkg name.  Only patterns that contain wildcards are allowed
                to match multiple packages.

                'raise_unmatched' determines whether an exception will be
                raised if any patterns didn't match any packages.

                'raise_not_installed' determines whether an exception will be
                raised if any pattern matches a package that's not installed.

                'return_matchdict' determines whether the dictionary containing
                which patterns matched which stems or the list of stems is
                returned.

                'universe' contains a list of tuples of publishers and package
                names against which the patterns should be matched.
                """
                # avoid checking everywhere
                if not patterns:
                        return set()

                illegals      = []
                nonmatch      = []
                multimatch    = []
                not_installed = []
                multispec     = []
                already_installed = []

                matchers = []
                fmris    = []
                pubs     = []

                wildcard_patterns = set()

                # ignore dups
                patterns = list(set(patterns))

                # figure out which kind of matching rules to employ
                seen = set()
                npatterns = []
                for pat in patterns:
                        try:
                                parts = pat.split("@", 1)
                                pat_stem = parts[0]

                                if "*" in pat_stem or "?" in pat_stem:
                                        matcher = pkg.fmri.glob_match
                                        wildcard_patterns.add(pat)
                                elif pat_stem.startswith("pkg:/") or \
                                    pat_stem.startswith("/"):
                                        matcher = pkg.fmri.exact_name_match
                                else:
                                        matcher = pkg.fmri.fmri_match

                                if matcher == pkg.fmri.glob_match:
                                        fmri = pkg.fmri.MatchingPkgFmri(
                                            pat_stem)
                                else:
                                        fmri = pkg.fmri.PkgFmri(pat_stem)

                                sfmri = str(fmri)
                                if sfmri in seen:
                                        # A different form of the same pattern
                                        # was specified already; ignore this
                                        # one (e.g. pkg:/network/ping,
                                        # /network/ping).
                                        wildcard_patterns.discard(pat)
                                        continue

                                seen.add(sfmri)
                                npatterns.append(pat)
                                matchers.append(matcher)
                                pubs.append(fmri.publisher)
                                fmris.append(fmri)
                        except pkg.fmri.FmriError as e:
                                illegals.append(e)
                patterns = npatterns
                del npatterns, seen

                # Create a dictionary of patterns, with each value being a
                # set of pkg names that match that pattern.
                ret = dict(zip(patterns, [set() for i in patterns]))

                if universe is not None:
                        assert match_type == ImagePlan.MATCH_ALL
                        pkg_names = universe
                else:
                        if match_type != ImagePlan.MATCH_INST_VERSIONS:
                                cat = image.get_catalog(image.IMG_CATALOG_KNOWN)
                        else:
                                cat = image.get_catalog(
                                    image.IMG_CATALOG_INSTALLED)
                        pkg_names = cat.pkg_names()

                # construct matches for each pattern
                for pkg_pub, name in pkg_names:
                        for pat, matcher, fmri, pub in \
                            zip(patterns, matchers, fmris, pubs):
                                if pub and pkg_pub != pub:
                                        continue
                                if matcher(name, fmri.pkg_name):
                                        ret[pat].add(name)

                matchdict = {}
                for p in patterns:
                        l = len(ret[p])
                        if l == 0: # no matches at all
                                nonmatch.append(p)
                        elif l > 1 and p not in wildcard_patterns:
                                # multiple matches
                                multimatch.append((p, list(ret[p])))
                        else:
                                # single match or wildcard
                                for k in ret[p]:
                                        # for each matching package name
                                        matchdict.setdefault(k, []).append(p)

                for name in matchdict:
                        if len(matchdict[name]) > 1:
                                # different pats, same pkg
                                multispec.append(tuple([name] +
                                    matchdict[name]))

                if match_type == ImagePlan.MATCH_INST_VERSIONS:
                        not_installed, nonmatch = nonmatch, not_installed
                elif match_type == ImagePlan.MATCH_UNINSTALLED:
                        already_installed = [
                            name
                            for name in image.get_catalog(
                            image.IMG_CATALOG_INSTALLED).names()
                            if name in matchdict
                        ]
                if illegals or (raise_unmatched and nonmatch) or multimatch \
                    or (not_installed and raise_not_installed) or multispec \
                    or already_installed:
                        raise api_errors.PlanCreationException(
                            already_installed=already_installed,
                            illegal=illegals,
                            missing_matches=not_installed,
                            multiple_matches=multimatch,
                            multispec=multispec,
                            unmatched_fmris=nonmatch)

                if return_matchdict:
                        return matchdict
                return set(matchdict.keys())

        @staticmethod
        def __match_user_fmris(image, patterns, match_type,
            pub_ranks=misc.EmptyDict, installed_pkgs=misc.EmptyDict,
            raise_not_installed=True, reject_set=misc.EmptyI,
            default_matcher=None):
                """Given a user-specified list of patterns, return a dictionary
                of matching fmris:

                {pkgname: [fmri1, fmri2, ...]
                 pkgname: [fmri1, fmri2, ...],
                 ...
                }

                Constraint used is always AUTO as per expected UI behavior.

                'match_type' indicates how matching should be restricted.  The
                possible values are:

                    MATCH_ALL
                        Matching is performed using all known package stems
                        and versions.  In this case, 'installed_pkgs' must also
                        be provided.

                    MATCH_INST_VERSIONS
                        Matching is performed using only installed package
                        stems and versions.

                    MATCH_INST_STEMS
                        Matching is performed using all known package versions
                        for stems matching installed packages.  In this case,
                        'installed_pkgs' must also be provided.


                Note that patterns starting w/ pkg:/ require an exact match;
                patterns containing '*' will using fnmatch rules; the default
                trailing match rules are used for remaining patterns unless
                'default_matcher' is specified.

                'default_matcher' is an optional pkg.fmri.match_* method to
                determine which matching rules should be applied to patterns
                that do not use wildcards or start with 'pkg:/' or '/'.

                Exactly duplicated patterns are ignored.

                Routine raises PlanCreationException if errors occur: it is
                illegal to specify multiple different patterns that match the
                same pkg name unless exactly one of those patterns contained no
                wildcards.  Only patterns that contain wildcards are allowed to
                match multiple packages.

                FMRI lists are trimmed by publisher, either by pattern
                specification, installed version or publisher ranking (in that
                order) when match_type is not MATCH_INST_VERSIONS.

                'raise_not_installed' determines whether an exception will be
                raised if any pattern matches a package that's not installed.

                'reject_set' is a set() containing the stems of packages that
                should be excluded from matches.
                """

                # problems we check for
                illegals      = []
                nonmatch      = []
                multimatch    = []
                not_installed = []
                multispec     = []
                exclpats      = []
                wrongpub      = []
                wrongvar      = set()

                matchers = []
                fmris    = []
                pubs     = []
                versions = []

                wildcard_patterns = set()

                renamed_fmris = defaultdict(set)
                obsolete_fmris = []

                # ignore dups
                patterns = list(set(patterns))

                installed_pubs = misc.EmptyDict
                if match_type in [ImagePlan.MATCH_INST_STEMS,
                    ImagePlan.MATCH_ALL]:
                        # build installed publisher dictionary
                        installed_pubs = dict((
                            (f.pkg_name, f.get_publisher())
                            for f in installed_pkgs.values()
                        ))

                # figure out which kind of matching rules to employ
                latest_pats = set()
                seen = set()
                npatterns = []
                for pat in patterns:
                        try:
                                parts = pat.split("@", 1)
                                pat_stem = parts[0]
                                pat_ver = None
                                if len(parts) > 1:
                                        pat_ver = parts[1]

                                if "*" in pat_stem or "?" in pat_stem:
                                        matcher = pkg.fmri.glob_match
                                        wildcard_patterns.add(pat)
                                elif pat_stem.startswith("pkg:/") or \
                                    pat_stem.startswith("/"):
                                        matcher = pkg.fmri.exact_name_match
                                elif default_matcher:
                                        matcher = default_matcher
                                else:
                                        matcher = pkg.fmri.fmri_match

                                if matcher == pkg.fmri.glob_match:
                                        fmri = pkg.fmri.MatchingPkgFmri(
                                            pat_stem)
                                else:
                                        fmri = pkg.fmri.PkgFmri(
                                            pat_stem)

                                if not pat_ver:
                                        # Do nothing.
                                        pass
                                elif "*" in pat_ver or "?" in pat_ver or \
                                    pat_ver == "latest":
                                        fmri.version = \
                                            pkg.version.MatchingVersion(pat_ver)
                                else:
                                        fmri.version = \
                                            pkg.version.Version(pat_ver)

                                sfmri = str(fmri)
                                if sfmri in seen:
                                        # A different form of the same pattern
                                        # was specified already; ignore this
                                        # one (e.g. pkg:/network/ping,
                                        # /network/ping).
                                        wildcard_patterns.discard(pat)
                                        continue

                                seen.add(sfmri)
                                npatterns.append(pat)
                                if pat_ver and \
                                    getattr(fmri.version, "match_latest", None):
                                        latest_pats.add(pat)

                                matchers.append(matcher)
                                pubs.append(fmri.publisher)
                                versions.append(fmri.version)
                                fmris.append(fmri)

                        except (pkg.fmri.FmriError,
                            pkg.version.VersionError) as e:
                                # illegals should be a list of fmri patterns so that
                                # PackageMatchErrors can construct correct error message.
                                illegals.append(pat)
                patterns = npatterns
                del npatterns, seen

                # Create a dictionary of patterns, with each value being a
                # dictionary of pkg names & fmris that match that pattern.
                ret = dict(zip(patterns, [dict() for i in patterns]))

                # Track patterns rejected due to user request (--reject).
                rejected_pats = set()

                # Track patterns rejected due to variants.
                rejected_vars = set()

                # keep track of publishers we reject due to implict selection
                # of installed publisher to produce better error message.
                rejected_pubs = {}

                if match_type != ImagePlan.MATCH_INST_VERSIONS:
                        cat = image.get_catalog(image.IMG_CATALOG_KNOWN)
                        info_needed = [pkg.catalog.Catalog.DEPENDENCY]
                else:
                        cat = image.get_catalog(image.IMG_CATALOG_INSTALLED)
                        info_needed = []

                variants = image.get_variants()
                for name in cat.names():
                        for pat, matcher, fmri, version, pub in \
                            zip(patterns, matchers, fmris, versions, pubs):
                                if not matcher(name, fmri.pkg_name):
                                        continue # name doesn't match
                                for ver, entries in cat.entries_by_version(name,
                                    info_needed=info_needed):
                                        if version and not ver.is_successor(version,
                                            pkg.version.CONSTRAINT_AUTO):
                                                continue # version doesn't match
                                        for f, metadata in entries:
                                                fpub = f.publisher
                                                if pub and pub != fpub:
                                                        continue # specified pubs conflict
                                                elif match_type == ImagePlan.MATCH_INST_STEMS and \
                                                    f.pkg_name not in installed_pkgs:
                                                        # Matched stem is not
                                                        # in list of installed
                                                        # stems.
                                                        continue
                                                elif f.pkg_name in reject_set:
                                                        # Pattern is excluded.
                                                        rejected_pats.add(pat)
                                                        continue

                                                states = metadata["metadata"]["states"]
                                                ren_deps = []
                                                omit_package = False
                                                # Check for renamed packages and
                                                # that the package matches the
                                                # image's variants.
                                                for astr in metadata.get("actions",
                                                    misc.EmptyI):
                                                        try:
                                                                a = pkg.actions.fromstr(
                                                                    astr)
                                                        except pkg.actions.ActionError:
                                                                # Unsupported or
                                                                # invalid package;
                                                                # drive on and
                                                                # filter as much as
                                                                # possible.  The
                                                                # solver will reject
                                                                # this package later.
                                                                continue

                                                        if pkgdefs.PKG_STATE_RENAMED in states and \
                                                            a.name == "depend" and \
                                                            a.attrs["type"] == "require":
                                                                ren_deps.append(pkg.fmri.PkgFmri(
                                                                    a.attrs["fmri"]))
                                                                continue
                                                        elif a.name != "set":
                                                                continue

                                                        atname = a.attrs["name"]
                                                        if not atname.startswith("variant."):
                                                                continue

                                                        # For all variants set
                                                        # in the image, elide
                                                        # packages that are not
                                                        # for a matching variant
                                                        # value.
                                                        atvalue = a.attrs["value"]
                                                        is_list = type(atvalue) == list
                                                        for vn, vv in six.iteritems(variants):
                                                                if vn == atname and \
                                                                    ((is_list and
                                                                    vv not in atvalue) or \
                                                                    (not is_list and
                                                                    vv != atvalue)):
                                                                        omit_package = True
                                                                        break

                                                if omit_package:
                                                        # Package skipped due to
                                                        # variant.
                                                        rejected_vars.add(pat)
                                                        continue

                                                ret[pat].setdefault(f.pkg_name,
                                                    []).append(f)

                                                if not pub and match_type != ImagePlan.MATCH_INST_VERSIONS and \
                                                    name in installed_pubs and \
                                                    pub_ranks[installed_pubs[name]][1] \
                                                    == True and installed_pubs[name] != \
                                                    fpub:
                                                        # Fmri publisher
                                                        # filtering is handled
                                                        # later.
                                                        rejected_pubs.setdefault(pat,
                                                            set()).add(fpub)

                                                states = metadata["metadata"]["states"]
                                                if pkgdefs.PKG_STATE_OBSOLETE in states:
                                                        obsolete_fmris.append(f)
                                                if pkgdefs.PKG_STATE_RENAMED in states:
                                                        renamed_fmris[f] = ren_deps

                # remove multiple matches if all versions are obsolete
                for p in patterns:
                        if len(ret[p]) > 1 and p not in wildcard_patterns:
                                # create dictionary of obsolete status vs
                                # pkg_name
                                obsolete = dict([
                                    (pkg_name, reduce(operator.or_,
                                    [f in obsolete_fmris for f in ret[p][pkg_name]]))
                                    for pkg_name in ret[p]
                                ])
                                # remove all obsolete match if non-obsolete
                                # match also exists
                                if set([True, False]) == set(obsolete.values()):
                                        for pkg_name in obsolete:
                                                if obsolete[pkg_name]:
                                                        del ret[p][pkg_name]

                # remove newer multiple match if renamed version exists
                for p in patterns:
                        if len(ret[p]) > 1 and p not in wildcard_patterns:
                                renamed_matches = [
                                    pfmri
                                    for pkg_name in ret[p]
                                    for pfmri in ret[p][pkg_name]
                                    if pfmri in renamed_fmris
                                    ]
                                targets = set([
                                    pf.pkg_name
                                    for f in renamed_matches
                                    for pf in renamed_fmris[f]
                                ])

                                for pkg_name in list(ret[p].keys()):
                                        if pkg_name in targets:
                                                del ret[p][pkg_name]

                # Determine match failures.
                # matchdict maps package stems to input patterns.
                matchdict = {}
                for p in patterns:
                        l = len(ret[p])
                        if l == 0: # no matches at all
                                if p in rejected_vars:
                                        wrongvar.add(p)
                                elif p in rejected_pats:
                                        exclpats.append(p)
                                else:
                                        nonmatch.append(p)
                        elif l > 1 and p not in wildcard_patterns:
                                # multiple matches
                                multimatch.append((p, set([
                                    f.get_pkg_stem()
                                    for n in ret[p]
                                    for f in ret[p][n]
                                ])))
                        else:
                                # single match or wildcard
                                for k, pfmris in six.iteritems(ret[p]):
                                        # for each matching package name
                                        matchdict.setdefault(k, []).append(
                                            (p, pfmris))

                proposed_dict = {}
                for name, lst in six.iteritems(matchdict):
                        nwc_ps = [
                            (p, set(pfmris))
                            for p, pfmris in lst
                            if p not in wildcard_patterns
                        ]
                        pub_named = False
                        # If there are any non-wildcarded patterns that match
                        # this package name, prefer the fmris they selected over
                        # any the wildcarded patterns selected.
                        if nwc_ps:
                                rel_ps = nwc_ps
                                # Remove the wildcarded patterns that match this
                                # package from the result dictionary.
                                for p, pfmris in lst:
                                        if p not in wildcard_patterns:
                                                if p.startswith("pkg://") or \
                                                    p.startswith("//"):
                                                        pub_named = True
                                                        break
                        else:
                                tmp_ps = [
                                    (p, set(pfmris))
                                    for p, pfmris in lst
                                    if p in wildcard_patterns
                                ]
                                # If wildcarded package names then compare
                                # patterns to see if any specify a particular
                                # publisher.  If they do, prefer the package
                                # from that publisher.
                                rel_ps = [
                                    (p, set(pfmris))
                                    for p, pfmris in tmp_ps
                                    if p.startswith("pkg://") or
                                    p.startswith("//")
                                ]
                                if rel_ps:
                                        pub_named = True
                                else:
                                        rel_ps = tmp_ps

                        # Find the intersection of versions which matched all
                        # the relevant patterns.
                        common_pfmris = rel_ps[0][1]
                        for p, vs in rel_ps[1:]:
                                common_pfmris &= vs
                        # If none of the patterns specified a particular
                        # publisher and the package in question is installed
                        # from a sticky publisher, then remove all pfmris which
                        # have a different publisher.
                        inst_pub = installed_pubs.get(name)
                        stripped_by_publisher = False
                        if not pub_named and common_pfmris and \
                            match_type != ImagePlan.MATCH_INST_VERSIONS and \
                            inst_pub and pub_ranks[inst_pub][1] == True:
                                common_pfmris = set(
                                    p for p in common_pfmris
                                    if p.publisher == inst_pub
                                )
                                stripped_by_publisher = True
                        if common_pfmris:
                                # The solver depends on these being in sorted
                                # order.
                                proposed_dict[name] = sorted(common_pfmris)
                        elif stripped_by_publisher:
                                for p, vs in rel_ps:
                                        wrongpub.append((p, rejected_pubs[p]))
                        else:
                                multispec.append(tuple([name] +
                                    [p for p, vs in rel_ps]))

                if match_type != ImagePlan.MATCH_ALL:
                        not_installed, nonmatch = nonmatch, not_installed

                if illegals or nonmatch or multimatch or \
                    (not_installed and raise_not_installed) or multispec or \
                    wrongpub or wrongvar or exclpats:
                        if not raise_not_installed:
                                not_installed = []
                        raise api_errors.PlanCreationException(
                            unmatched_fmris=nonmatch,
                            multiple_matches=multimatch, illegal=illegals,
                            missing_matches=not_installed, multispec=multispec,
                            wrong_publishers=wrongpub, wrong_variants=wrongvar,
                            rejected_pats=exclpats)

                # eliminate lower ranked publishers
                if match_type != ImagePlan.MATCH_INST_VERSIONS:
                        # no point for installed pkgs....
                        for pkg_name in proposed_dict:
                                pubs_found = set([
                                    f.publisher
                                    for f in proposed_dict[pkg_name]
                                ])
                                # 1000 is hack for installed but unconfigured
                                # publishers
                                best_pub = sorted([
                                    (pub_ranks.get(p, (1000, True))[0], p)
                                    for p in pubs_found
                                ])[0][1]

                                # Include any installed FMRIs that were allowed
                                # by all of the previous filtering, even if they
                                # aren't from the "best" available publisher, to
                                # account for the scenario where the installed
                                # version is the newest or best version for the
                                # plan solution.  While doing so, also eliminate
                                # any exact duplicate FMRIs from publishers
                                # other than the installed publisher to prevent
                                # thrashing in the solver due to many equiv.
                                # solutions and unexpected changes in package
                                # publishers that weren't explicitly requested.
                                inst_f = installed_pkgs.get(f.pkg_name, None)
                                inst_v = None
                                if inst_f not in proposed_dict[pkg_name]:
                                        # Should only apply if it's part of the
                                        # proposed set.
                                        inst_f = None
                                else:
                                        inst_v = inst_f.version

                                proposed_dict[pkg_name] = [
                                    f for f in proposed_dict[pkg_name]
                                    if f == inst_f or \
                                        (f.publisher == best_pub and
                                        f.version != inst_v)
                                ]

                # construct references so that we can know which pattern
                # generated which fmris...
                references = dict([
                    (f, p)
                    for p in ret.keys()
                    for flist in ret[p].values()
                    for f in flist
                    if f in proposed_dict[f.pkg_name]
                ])

                # Discard all but the newest version of each match.
                if latest_pats:
                        # Rebuild proposed_dict based on latest version of every
                        # package.
                        sort_key = operator.attrgetter("version")
                        for pname, flist in six.iteritems(proposed_dict):
                                # Must sort on version; sorting by FMRI would
                                # sort by publisher, then by version which is
                                # not desirable.
                                platest = sorted(flist, key=sort_key)[-1]
                                if references[platest] not in latest_pats:
                                        # Nothing to do.
                                        continue

                                # Filter out all versions except the latest for
                                # each matching package.  Allow for multiple
                                # FMRIs of the same latest version.  (There
                                # might be more than one publisher with the
                                # same version.)
                                proposed_dict[pname] = [
                                    f for f in flist
                                    if f.version == platest.version
                                ]

                        # Construct references again to match final state
                        # of proposed_dict.
                        references = dict([
                            (f, p)
                            for p in ret.keys()
                            for flist in ret[p].values()
                            for f in flist
                            if f in proposed_dict[f.pkg_name]
                        ])

                return proposed_dict, references

        @staticmethod
        def freeze_pkgs_match(image, pats):
                """Find the packages which match the given patterns and thus
                should be frozen."""

                pats = set(pats)
                freezes = set()
                pub_ranks = image.get_publisher_ranks()
                installed_version_mismatches = {}
                versionless_uninstalled = set()
                multiversions = []

                # Find the installed packages that match the provided patterns.
                inst_dict, references = ImagePlan.__match_user_fmris(image,
                    pats, ImagePlan.MATCH_INST_VERSIONS, pub_ranks=pub_ranks,
                    raise_not_installed=False)

                # Find the installed package stems that match the provided
                # patterns.
                installed_stems_dict = ImagePlan.match_user_stems(image, pats,
                    ImagePlan.MATCH_INST_VERSIONS, raise_unmatched=False,
                    raise_not_installed=False, return_matchdict=True)

                stems_of_fmri_matches = set(inst_dict.keys())
                stems_of_stems_matches = set(installed_stems_dict.keys())

                assert stems_of_fmri_matches.issubset(stems_of_stems_matches)

                # For each package stem which matched a pattern only when
                # versions were ignored ...
                for stem in stems_of_stems_matches - stems_of_fmri_matches:
                        # If more than one pattern matched this stem, then
                        # match_user_stems should've raised an exception.
                        assert len(installed_stems_dict[stem]) == 1
                        bad_pat = installed_stems_dict[stem][0]
                        installed_version_mismatches.setdefault(
                            bad_pat, []).append(stem)
                        # If this pattern is bad, then we don't care about it
                        # anymore.
                        pats.discard(bad_pat)

                # For each fmri, pattern where the pattern matched the fmri
                # including the version ...
                for full_fmri, pat in six.iteritems(references):
                        parts = pat.split("@", 1)
                        # If the pattern doesn't include a version, then add the
                        # version the package is installed at to the list of
                        # things to freeze.  If it does include a version, then
                        # just freeze using the version from the pattern, and
                        # the name from the matching fmri.
                        if len(parts) < 2 or parts[1] == "":
                                freezes.add(full_fmri.get_fmri(anarchy=True,
                                    include_scheme=False))
                        else:
                                freezes.add(full_fmri.pkg_name + "@" + parts[1])
                        # We're done with this pattern now.
                        pats.discard(pat)

                # Any wildcarded patterns remaining matched no installed
                # packages and so are invalid arguments to freeze.
                unmatched_wildcards = set([
                    pat for pat in pats if "*" in pat or "?" in pat
                ])
                pats -= unmatched_wildcards

                # Now check the remaining pats to ensure they have a version
                # component.  If they don't, then they can't be used to freeze
                # uninstalled packages.
                for pat in pats:
                        parts = pat.split("@", 1)
                        if len(parts) < 2 or parts[1] == "":
                                versionless_uninstalled.add(pat)
                pats -= versionless_uninstalled
                freezes |= pats

                stems = {}
                for p in freezes:
                        stems.setdefault(pkg.fmri.PkgFmri(p).get_pkg_stem(
                            anarchy=True, include_scheme=False), set()).add(p)
                # Check whether one stem has been frozen at non-identical
                # versions.
                for k, v in six.iteritems(stems):
                        if len(v) > 1:
                                multiversions.append((k, v))
                        else:
                                stems[k] = v.pop()

                if versionless_uninstalled or unmatched_wildcards or \
                    installed_version_mismatches or multiversions:
                        raise api_errors.FreezePkgsException(
                            multiversions=multiversions,
                            unmatched_wildcards=unmatched_wildcards,
                            version_mismatch=installed_version_mismatches,
                            versionless_uninstalled=versionless_uninstalled)
                return stems
