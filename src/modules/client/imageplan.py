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

from collections import defaultdict, namedtuple
import errno
import itertools
import operator
import os
import simplejson as json
import sys
import traceback

from pkg.client import global_settings
logger = global_settings.logger

import pkg.actions
import pkg.catalog
import pkg.client.actuator as actuator
import pkg.client.api_errors as api_errors
import pkg.client.indexer as indexer
import pkg.client.pkg_solver as pkg_solver
import pkg.client.pkgdefs as pkgdefs
import pkg.client.pkgplan as pkgplan
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.mediator as med
import pkg.search_errors as se
import pkg.version

from pkg.client.debugvalues import DebugValues
from pkg.mediator import mediator_impl_matches

UNEVALUATED       = 0 # nothing done yet
EVALUATED_PKGS    = 1 # established fmri changes
MERGED_OK         = 2 # created single merged plan
EVALUATED_OK      = 3 # ready to execute
PREEXECUTED_OK    = 4 # finished w/ preexecute
PREEXECUTED_ERROR = 5 # whoops
EXECUTED_OK       = 6 # finished execution
EXECUTED_ERROR    = 7 # failed

ActionPlan = namedtuple("ActionPlan", "p src dst")

IP_MODE_DEFAULT = "default"
IP_MODE_SAVE    = "save"
IP_MODE_LOAD    = "load"
ip_mode_values = frozenset([
    IP_MODE_DEFAULT,
    IP_MODE_SAVE,
    IP_MODE_LOAD,
])

STATE_FILE_PKGS = "pkgs"
STATE_FILE_ACTIONS = "actions"

class ImagePlan(object):
        """ImagePlan object contains the plan for changing the image...
        there are separate routines for planning the various types of
        image modifying operations; evaluation (comparing manifests
        and buildig lists of removeal, install and update actions
        and their execution is all common code"""

        PLANNED_FIX           = "fix"
        PLANNED_INSTALL       = "install"
        PLANNED_NOOP          = "no-op"
        PLANNED_NOTHING       = "no-plan"
        PLANNED_REVERT        = "revert"
        PLANNED_MEDIATOR      = "set-mediator"
        PLANNED_SYNC          = "sync"
        PLANNED_UNINSTALL     = "uninstall"
        PLANNED_UPDATE        = "update"
        PLANNED_VARIANT       = "change-variant"
        __planned_values  = frozenset([
                PLANNED_FIX,
                PLANNED_INSTALL,
                PLANNED_NOTHING,

                PLANNED_REVERT,
                PLANNED_MEDIATOR,
                PLANNED_SYNC,
                PLANNED_UNINSTALL,
                PLANNED_UPDATE,
                PLANNED_VARIANT,
        ])

        MATCH_ALL           = 0
        MATCH_INST_VERSIONS = 1
        MATCH_INST_STEMS    = 2
        MATCH_UNINSTALLED   = 3

        def __init__(self, image, progtrack, check_cancel, noexecute=False,
            mode=IP_MODE_DEFAULT):

                assert mode in ip_mode_values

                self.image = image
                self.pkg_plans = []

                self.state = UNEVALUATED
                self.__progtrack = progtrack
                self.__noexecute = noexecute

                self.__fmri_changes = [] # install  (None, fmri)
                                         # remove   (oldfmri, None)
                                         # update   (oldfmri, newfmri|oldfmri)

                # Used to track users and groups that are part of operation.
                self.added_groups = {}
                self.removed_groups = {}
                self.added_users = {}
                self.removed_users = {}

                self.update_actions  = []
                self.removal_actions = []
                self.install_actions = []

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

                self.__directories = None  # implement ref counting
                self.__symlinks = None     # for dirs and links and
                self.__hardlinks = None    # hardlinks
                self.__licenses = None
                self.__legacy = None
                self.__cached_actions = {}
                self.__fixups = {}

                self.__old_excludes = image.list_excludes()
                self.__new_excludes = self.__old_excludes

                self.__check_cancel = check_cancel

                self.__actuators = actuator.Actuator()

                self.update_index = True

                self.__preexecuted_indexing_error = None
                self._planned_op = self.PLANNED_NOTHING
                self.__pkg_solver = None
                self.__new_mediators = None
                self.__mediators_change = False
                self.__new_variants = None
                self.__new_facets = None
                self.__changed_facets = {}
                self.__removed_facets = set()
                self.__varcets_change = False
                self.__match_inst = {} # dict of fmri -> pattern
                self.__match_rm = {} # dict of fmri -> pattern
                self.__match_update = {} # dict of fmri -> pattern
                self.__need_boot_archive = None
                self.__new_avoid_obs = (None, None)
                self.__salvaged = []
                self.__mode = mode
                self.__cbytes_added = 0  # size of compressed files
                self.__bytes_added = 0   # size of files added
                self.__cbytes_avail = 0  # avail space for downloads
                self.__bytes_avail = 0   # avail space for fs

                if noexecute:
                        return

                # generate filenames for state files
                self.__planfile = dict()
                self.__planfile[STATE_FILE_PKGS] = \
                    "%s.%d.json" % (STATE_FILE_PKGS, image.runid)
                self.__planfile[STATE_FILE_ACTIONS] = \
                    "%s.%d.json" % (STATE_FILE_ACTIONS, image.runid)

                # delete any pre-existing state files
                rm_paths = []
                if mode in [IP_MODE_DEFAULT, IP_MODE_SAVE]:
                        rm_paths.append(self.__planfile[STATE_FILE_PKGS])
                        rm_paths.append(self.__planfile[STATE_FILE_ACTIONS])
                for path in rm_paths:
                        try:
                                os.remove(path)
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        raise

        def __str__(self):

                if self.state == UNEVALUATED:
                        s = "UNEVALUATED:\n"
                        return s

                s = "%s\n" % self.__pkg_solver

                if self.state < EVALUATED_PKGS:
                        return s

                s += "Package version changes:\n"

                for oldfmri, newfmri in self.__fmri_changes:
                        s += "%s -> %s\n" % (oldfmri, newfmri)

                if self.__actuators:
                        s = s + "\nActuators:\n%s\n" % self.__actuators

                if self.__old_excludes != self.__new_excludes:
                        s = s + "\nVariants/Facet changes:\n %s -> %s\n" % \
                            (self.__old_excludes, self.__new_excludes)

                if self.__new_mediators:
                        s = s + "\nMediator changes:\n %s" % \
                            "\n".join(self.mediators_to_strings())

                return s

        @property
        def mediators(self):
                """Returns a list of three-tuples containing information about
                the mediators.  The first element in the tuple is the name of
                the mediator.  The second element is a tuple containing the
                original version and source and the new version and source of
                the mediator.  The third element is a tuple containing the
                original implementation and source and new implementation and
                source."""

                ret = []
                cfg_mediators = self.image.cfg.mediators
                if not (self.__mediators_change and
                    (self.__new_mediators or cfg_mediators)):
                        return ret

                def get_mediation(mediators):
                        mimpl = mver = mimpl_source = \
                            mver_source = None
                        if m in mediators:
                                mimpl = mediators[m].get(
                                    "implementation")
                                mimpl_ver = mediators[m].get(
                                    "implementation-version")
                                if mimpl_ver:
                                        mimpl_ver = \
                                            mimpl_ver.get_short_version()
                                if mimpl and mimpl_ver:
                                        mimpl += "(@%s)" % mimpl_ver
                                mimpl_source = mediators[m].get(
                                    "implementation-source")

                                mver = mediators[m].get("version")
                                if mver:
                                        mver = mver.get_short_version()
                                mver_source = mediators[m].get(
                                    "version-source")
                        return mimpl, mver, mimpl_source, mver_source

                for m in sorted(set(self.__new_mediators.keys() +
                    cfg_mediators.keys())):
                        orig_impl, orig_ver, orig_impl_source, \
                            orig_ver_source = get_mediation(cfg_mediators)
                        new_impl, new_ver, new_impl_source, new_ver_source = \
                            get_mediation(self.__new_mediators)

                        if orig_ver == new_ver and \
                            orig_ver_source == new_ver_source and \
                            orig_impl == new_impl and \
                            orig_impl_source == new_impl_source:
                                # Mediation not changed.
                                continue

                        out = (m,
                            ((orig_ver, orig_ver_source),
                            (new_ver, new_ver_source)),
                            ((orig_impl, orig_impl_source),
                            (new_impl, new_impl_source)))

                        ret.append(out)

                return ret

        def mediators_to_strings(self):
                """Returns list of strings describing mediator changes."""
                ret = []
                for m, ver, impl in self.mediators:
                        ((orig_ver, orig_ver_source),
                            (new_ver, new_ver_source)) = ver
                        ((orig_impl, orig_impl_source),
                            (new_impl, new_impl_source)) = impl
                        out = "mediator %s:\n" % m
                        if orig_ver and new_ver:
                                out += "           version: %s (%s default) " \
                                    "-> %s (%s default)\n" % (orig_ver,
                                    orig_ver_source, new_ver, new_ver_source)
                        elif orig_ver:
                                out += "           version: %s (%s default) " \
                                    "-> None\n" % (orig_ver, orig_ver_source)
                        elif new_ver:
                                out += "           version: None -> " \
                                    "%s (%s default)\n" % (new_ver,
                                    new_ver_source)

                        if orig_impl and new_impl:
                                out += "    implementation: %s (%s default) " \
                                    "-> %s (%s default)\n" % (orig_impl,
                                    orig_impl_source, new_impl, new_impl_source)
                        elif orig_impl:
                                out += "    implementation: %s (%s default) " \
                                    "-> None\n" % (orig_impl, orig_impl_source)
                        elif new_impl:
                                out += "    implementation: None -> " \
                                    "%s (%s default)\n" % (new_impl,
                                    new_impl_source)
                        ret.append(out)
                return ret

        @property
        def salvaged(self):
                """A list of tuples of items that were salvaged during plan
                execution.  Each tuple is of the form (original_path,
                salvage_path).  Where 'original_path' is the path of the item
                before it was salvaged, and 'salvage_path' is where the item was
                moved to.  This property is only valid after plan execution
                has completed."""
                return self.__salvaged

        @property
        def services(self):
                """Returns a list of string tuples describing affected services
                (action, SMF FMRI)."""
                return sorted(
                    ((str(action), str(smf_fmri))
                    for action, smf_fmri in self.__actuators.get_services_list()),
                    key=operator.itemgetter(0, 1)
                )

        @property
        def varcets(self):
                """Returns list of variant/facet changes"""
                if self.__new_variants:
                        vs = self.__new_variants.items()
                else:
                        vs = []
                fs = []
                fs.extend(self.__changed_facets.items())
                fs.extend([(f, None) for f in self.__removed_facets])
                return vs, fs

        def __verbose_str(self):
                s = str(self)

                if self.state == EVALUATED_PKGS:
                        return s

                s = s + "Actions being removed:\n"
                for pplan, o_action, ignore in self.removal_actions:
                        s = s + "\t%s:%s\n" % ( pplan.origin_fmri, o_action)

                s = s + "\nActions being updated:\n"
                for pplan, o_action, d_action in self.update_actions:
                        s = s + "\t%s:%s -> %s%s\n" % (
                            pplan.origin_fmri, o_action,
                            pplan.destination_fmri, d_action )

                s = s + "\nActions being installed:\n"
                for pplan, ignore, d_action in self.removal_actions:
                        s = s + "\t%s:%s\n" % ( pplan.destination_fmri, d_action)

                return s

        @property
        def planned_op(self):
                """Returns a constant value indicating the type of operation
                planned."""

                return self._planned_op

        @property
        def plan_desc(self):
                """Get the proposed fmri changes."""
                return self.__fmri_changes

        @property
        def bytes_added(self):
                """get the (approx) number of bytes added"""
                return self.__bytes_added
        @property
        def cbytes_added(self):
                """get the (approx) number of bytes needed in download cache"""
                return self.__cbytes_added

        @property
        def bytes_avail(self):
                """get the (approx) number of bytes space available"""
                return self.__bytes_avail
        @property
        def cbytes_avail(self):
                """get the (approx) number of download space available"""
                return self.__cbytes_avail

        def __vector_2_fmri_changes(self, installed_dict, vector,
            li_pkg_updates=True, new_variants=None, new_facets=None):
                """Given an installed set of packages, and a proposed vector
                of package changes determine what, if any, changes should be
                made to the image.  This takes into account different
                behaviors during operations like variant changes, and updates
                where the only packages being updated are linked image
                constraints, etc."""

                cat = self.image.get_catalog(self.image.IMG_CATALOG_KNOWN)

                fmri_updates = []
                for a, b in ImagePlan.__dicts2fmrichanges(installed_dict,
                    ImagePlan.__fmris2dict(vector)):
                        if a != b:
                                fmri_updates.append((a, b))
                                continue
                        if new_facets or new_variants:
                                #
                                # In the case of a facet change we reinstall
                                # packages since any action in a package could
                                # have a facet attached to it.
                                #
                                # In the case of variants packages should
                                # declare what variants they contain.  Hence,
                                # theoretically, we should be able to reduce
                                # the number of package reinstalls by removing
                                # re-installs of packages that don't declare
                                # variants.  But unfortunately we've never
                                # enforced this requirement that packages with
                                # action variant tags declare their variants.
                                # So now we're stuck just re-installing every
                                # package.  sigh.
                                #
                                fmri_updates.append((a, b))
                                continue

                if not fmri_updates:
                        # no planned fmri changes
                        return []

                if fmri_updates and not li_pkg_updates:
                        # oops.  the caller requested no package updates and
                        # we couldn't satisfy that request.
                        raise api_errors.PlanCreationException(
                            pkg_updates_required=fmri_updates)

                return fmri_updates

        def __plan_op(self, op):
                """Private helper method used to mark the start of a planned
                operation."""

                self._planned_op = op
                self._image_lm = self.image.get_last_modified()

        def __plan_install_solver(self, li_pkg_updates=True, li_sync_op=False,
            new_facets=None, new_variants=None, pkgs_inst=None,
            reject_list=misc.EmptyI):
                """Use the solver to determine the fmri changes needed to
                install the specified pkgs, sync the specified image, and/or
                change facets/variants within the current image."""

                if not (new_variants or pkgs_inst or li_sync_op or
                    new_facets is not None):
                        # nothing to do
                        self.__fmri_changes = []
                        return

                old_facets = self.image.cfg.facets
                if new_variants or \
                    (new_facets is not None and new_facets != old_facets):
                        self.__varcets_change = True
                        self.__new_variants = new_variants
                        self.__new_facets   = new_facets
                        tmp_new_facets = new_facets
                        if tmp_new_facets is None:
                                tmp_new_facets = pkg.facet.Facets()
                        self.__changed_facets = pkg.facet.Facets(dict(
                            set(tmp_new_facets.iteritems()) -
                            set(old_facets.iteritems())))
                        self.__removed_facets = set(old_facets.keys()) - \
                            set(tmp_new_facets.keys())

                # get ranking of publishers
                pub_ranks = self.image.get_publisher_ranks()

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())

                if reject_list:
                        reject_set = self.match_user_stems(reject_list,
                            self.MATCH_ALL)
                else:
                        reject_set = set()

                if pkgs_inst:
                        inst_dict, references = self.__match_user_fmris(
                            pkgs_inst, self.MATCH_ALL, pub_ranks=pub_ranks,
                            installed_pkgs=installed_dict, reject_set=reject_set)
                        self.__match_inst = references
                else:
                        inst_dict = {}

                self.__new_excludes = self.image.list_excludes(new_variants,
                    new_facets)

                if new_variants:
                        variants = new_variants
                else:
                        variants = self.image.get_variants()

                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict,
                    pub_ranks,
                    variants,
                    self.image.avoid_set_get(),
                    self.image.linked.parent_fmris(),
                    self.__progtrack)

                # Solve... will raise exceptions if no solution is found
                new_vector, self.__new_avoid_obs = \
                    self.__pkg_solver.solve_install(
                        self.image.get_frozen_list(), inst_dict,
                        new_variants=new_variants, new_facets=new_facets,
                        excludes=self.__new_excludes, reject_set=reject_set,
                        relax_all=li_sync_op)

                self.__fmri_changes = self.__vector_2_fmri_changes(
                    installed_dict, new_vector,
                    li_pkg_updates=li_pkg_updates,
                    new_variants=new_variants, new_facets=new_facets)

        def __plan_install(self, li_pkg_updates=True, li_sync_op=False,
            new_facets=None, new_variants=None, pkgs_inst=None,
            reject_list=misc.EmptyI):
                """Determine the fmri changes needed to install the specified
                pkgs, sync the image, and/or change facets/variants within the
                current image."""

                # someone better have called __plan_op()
                assert self._planned_op in self.__planned_values

                plandir = self.image.plandir

                if self.__mode in [IP_MODE_DEFAULT, IP_MODE_SAVE]:
                        self.__plan_install_solver(
                            li_pkg_updates=li_pkg_updates,
                            li_sync_op=li_sync_op,
                            new_facets=new_facets,
                            new_variants=new_variants,
                            pkgs_inst=pkgs_inst,
                            reject_list=reject_list)

                        if self.__mode == IP_MODE_SAVE:
                                self.__save(STATE_FILE_PKGS)
                else:
                        assert self.__mode == IP_MODE_LOAD
                        self.__fmri_changes = self.__load(STATE_FILE_PKGS)

                self.state = EVALUATED_PKGS

        def plan_install(self, pkgs_inst=None, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to install the specified
                pkgs"""

                self.__plan_op(self.PLANNED_INSTALL)
                self.__plan_install(pkgs_inst=pkgs_inst,
                     reject_list=reject_list)

        def plan_change_varcets(self, new_facets=None, new_variants=None,
            reject_list=misc.EmptyI):
                """Determine the fmri changes needed to change the specified
                facets/variants."""

                self.__plan_op(self.PLANNED_VARIANT)
                self.__plan_install(new_facets=new_facets,
                     new_variants=new_variants, reject_list=reject_list)

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

                self.__plan_op(self.PLANNED_MEDIATOR)

                self.__mediators_change = True
                self.__new_mediators = new_mediators
                self.__fmri_changes = []

                cfg_mediators = self.image.cfg.mediators

                # keys() is used since entries are deleted during iteration.
                update_mediators = {}
                for m in self.__new_mediators.keys():
                        for k in ("implementation", "version"):
                                if k in self.__new_mediators[m]:
                                        if self.__new_mediators[m][k] is not None:
                                                # Any mediators being set this
                                                # way are forced to be marked as
                                                # being set by local administrator.
                                                self.__new_mediators[m]["%s-source" % k] = \
                                                    "local"
                                                continue

                                        # Explicit reset requested.
                                        del self.__new_mediators[m][k]
                                        self.__new_mediators[m].pop(
                                            "%s-source" % k, None)
                                        if k == "implementation":
                                                self.__new_mediators[m].pop(
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
                                med_source = cfg_mediators[m].get("%s-source" % k)
                                if med_source != "local":
                                        continue

                                self.__new_mediators[m][k] = \
                                    cfg_mediators[m].get(k)
                                self.__new_mediators[m]["%s-source" % k] = "local"

                                if k == "implementation" and \
                                    "implementation-version" in cfg_mediators[m]:
                                        self.__new_mediators[m]["implementation-version"] = \
                                            cfg_mediators[m].get("implementation-version")

                        if m not in cfg_mediators:
                                # mediation changed.
                                continue

                        # Determine if the only thing changing for mediations is
                        # whether configuration source is changing.  If so,
                        # optimize planning by not loading any package data.
                        for k in ("implementation", "version"):
                                if self.__new_mediators[m].get(k) != \
                                    cfg_mediators[m].get(k):
                                        break
                        else:
                                if (self.__new_mediators[m].get("version-source") != \
                                    cfg_mediators[m].get("version-source")) or \
                                    (self.__new_mediators[m].get("implementation-source") != \
                                    cfg_mediators[m].get("implementation-source")):
                                        update_mediators[m] = \
                                            self.__new_mediators[m]
                                del self.__new_mediators[m]

                if self.__new_mediators:
                        # Some mediations are changing, so merge the update only
                        # ones back in.
                        self.__new_mediators.update(update_mediators)

                        # Determine which packages will be affected.
                        for f in self.image.gen_installed_pkgs():
                                self.__progtrack.evaluate_progress()
                                m = self.image.get_manifest(f)
                                mediated = []
                                for act in m.gen_actions_by_types(("hardlink",
                                    "link")):
                                        try:
                                                mediator = act.attrs["mediator"]
                                        except KeyError:
                                                continue
                                        if mediator in new_mediators:
                                                mediated.append(act)

                                if mediated:
                                        pp = pkgplan.PkgPlan(self.image,
                                            self.__progtrack,
                                            self.__check_cancel)
                                        pp.propose_repair(f, m, mediated,
                                            misc.EmptyI)
                                        pp.evaluate(self.__new_excludes,
                                            self.__new_excludes)
                                        self.pkg_plans.append(pp)
                else:
                        # Only the source property is being updated for
                        # these mediators, so no packages needed loading.
                        self.__new_mediators = update_mediators

                self.state = EVALUATED_PKGS

        def plan_sync(self, li_pkg_updates=True, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to sync the image."""

                self.__plan_op(self.PLANNED_SYNC)

                # check if the sync will try to uninstall packages.
                uninstall = False
                reject_set = self.match_user_stems(reject_list,
                    self.MATCH_INST_VERSIONS, raise_not_installed=False)
                if reject_set:
                        # at least one reject pattern matched an installed
                        # package
                        uninstall = True

                # audits are fast, so do an audit to check if we're in sync.
                rv, err, p_dict = self.image.linked.audit_self(
                    li_parent_sync=False)

                # if we're not trying to uninstall packages and we're
                # already in sync then don't bother invoking the solver.
                if not uninstall and rv == pkgdefs.EXIT_OK:
                        # we don't need to do anything
                        self.__fmri_changes = []
                        self.state = EVALUATED_PKGS
                        return

                self.__plan_install(li_pkg_updates=li_pkg_updates,
                    li_sync_op=True, reject_list=reject_list)

        def plan_uninstall(self, pkgs_to_uninstall):
                self.__plan_op(self.PLANNED_UNINSTALL)
                proposed_dict, self.__match_rm = self.__match_user_fmris(
                    pkgs_to_uninstall, self.MATCH_INST_VERSIONS)
                # merge patterns together
                proposed_removals = set([
                    f
                    for each in proposed_dict.values()
                    for f in each
                ])

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())

                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict,
                    self.image.get_publisher_ranks(),
                    self.image.get_variants(),
                    self.image.avoid_set_get(),
                    self.image.linked.parent_fmris(),
                    self.__progtrack)

                new_vector, self.__new_avoid_obs = \
                    self.__pkg_solver.solve_uninstall(
                        self.image.get_frozen_list(), proposed_removals,
                        self.__new_excludes)

                self.__fmri_changes = [
                    (a, b)
                    for a, b in ImagePlan.__dicts2fmrichanges(installed_dict,
                        ImagePlan.__fmris2dict(new_vector))
                    if a != b
                ]

                self.state = EVALUATED_PKGS

        def __plan_update_solver(self, pkgs_update=None,
            reject_list=misc.EmptyI):
                """Use the solver to determine the fmri changes needed to
                update the specified pkgs or all packages if none were
                specified."""
                # get ranking of publishers
                pub_ranks = self.image.get_publisher_ranks()

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(
                    self.image.gen_installed_pkgs())

                # If specific packages or patterns were provided, then
                # determine the proposed set to pass to the solver.
                if reject_list:
                        reject_set = self.match_user_stems(reject_list,
                            self.MATCH_ALL)
                else:
                        reject_set = set()

                if pkgs_update:
                        update_dict, references = self.__match_user_fmris(
                            pkgs_update, self.MATCH_INST_STEMS,
                            pub_ranks=pub_ranks, installed_pkgs=installed_dict,
                            reject_set=reject_set)
                        self.__match_update = references

                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict,
                    pub_ranks,
                    self.image.get_variants(),
                    self.image.avoid_set_get(),
                    self.image.linked.parent_fmris(),
                    self.__progtrack)

                if pkgs_update:
                        new_vector, self.__new_avoid_obs = \
                            self.__pkg_solver.solve_install(
                                self.image.get_frozen_list(),
                                update_dict, excludes=self.__new_excludes,
                                reject_set=reject_set,
                                trim_proposed_installed=False)
                else:
                        # Updating all installed packages requires a different
                        # solution path.
                        new_vector, self.__new_avoid_obs = \
                            self.__pkg_solver.solve_update_all(
                                self.image.get_frozen_list(),
                                excludes=self.__new_excludes,
                                reject_set=reject_set)

                self.__fmri_changes = self.__vector_2_fmri_changes(
                    installed_dict, new_vector)

        def plan_update(self, pkgs_update=None, reject_list=misc.EmptyI):
                """Determine the fmri changes needed to update the specified
                pkgs or all packages if none were specified."""
                self.__plan_op(self.PLANNED_UPDATE)

                plandir = self.image.plandir

                if self.__mode in [IP_MODE_DEFAULT, IP_MODE_SAVE]:
                        self.__plan_update_solver(
                            pkgs_update=pkgs_update,
                            reject_list=reject_list)

                        if self.__mode == IP_MODE_SAVE:
                                self.__save(STATE_FILE_PKGS)
                else:
                        assert self.__mode == IP_MODE_LOAD
                        self.__fmri_changes = self.__load(STATE_FILE_PKGS)

                self.state = EVALUATED_PKGS

        def plan_revert(self, args, tagged):
                """Plan reverting the specifed files or files tagged as
                specified.  We create the pkgplans here rather than in
                evaluate; by keeping the list of changed_fmris empty we
                skip most of the processing in evaluate"""

                self.__plan_op(self.PLANNED_REVERT)

                revert_dict = defaultdict(list)

                if tagged:
                        # look through all the files on the system; any files
                        # tagged w/ revert-tag set to any of the values on
                        # the command line need to be checked and reverted if
                        # they differ from the manifests.  Note we don't care
                        # if the file is editable or not.

                        tag_set = set(args)
                        for f in self.image.gen_installed_pkgs():
                                self.__progtrack.evaluate_progress()
                                m = self.image.get_manifest(f)
                                for act in m.gen_actions_by_type("file",
                                    self.__new_excludes):
                                        if "revert-tag" in act.attrs and \
                                            (set(act.attrlist("revert-tag")) &
                                             tag_set):
                                                revert_dict[(f, m)].append(act)
                else:
                        # look through all the packages, looking for our files
                        # we could use search for this.

                        revertpaths = set([a.lstrip(os.path.sep) for a in args])
                        overlaypaths = set()
                        for f in self.image.gen_installed_pkgs():
                                self.__progtrack.evaluate_progress()
                                m = self.image.get_manifest(f)
                                for act in m.gen_actions_by_type("file",
                                    self.__new_excludes):
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
                                raise api_errors.PlanCreationException(
                                    nofiles=list(revertpaths))

                for f, m in revert_dict.keys():
                        # build list of actions that will need to be reverted
                        # no sense in replacing files that are original already
                        needs_change = []
                        self.__progtrack.evaluate_progress()
                        for act in revert_dict[(f, m)]:
                                # delete preserve attribute to both find and
                                # enable replacement of modified editable files.
                                act.attrs.pop("preserve", None)
                                act.verify(self.image, forever=True)
                                if act.replace_required == True:
                                        needs_change.append(act)
                        if needs_change:
                                pp = pkgplan.PkgPlan(self.image,
                                    self.__progtrack, self.__check_cancel)
                                pp.propose_repair(f, m, needs_change,
                                    misc.EmptyI)
                                pp.evaluate(self.__new_excludes,
                                    self.__new_excludes)
                                self.pkg_plans.append(pp)

                self.__fmri_changes = []
                self.state = EVALUATED_PKGS

        def plan_fix(self, pkgs_to_fix):
                """Create the list of pkgs to fix"""
                self.__plan_op(self.PLANNED_FIX)

        def plan_noop(self):
                """Create a plan that doesn't change the package contents of
                the current image."""
                self.__plan_op(self.PLANNED_NOOP)
                self.__fmri_changes = []
                self.state = EVALUATED_PKGS

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
                    for k in set(olddict.keys() + newdict.keys())
                ]

        def reboot_advised(self):
                """Check if evaluated imageplan suggests a reboot"""
                assert self.state >= MERGED_OK
                return self.__actuators.reboot_advised()

        def reboot_needed(self):
                """Check if evaluated imageplan requires a reboot"""
                assert self.state >= MERGED_OK
                return self.__actuators.reboot_needed()

        def boot_archive_needed(self):
                """True if boot archive needs to be rebuilt"""
                assert self.state >= MERGED_OK
                return self.__need_boot_archive

        def get_solver_errors(self):
                """Returns a list of strings for all FMRIs evaluated by the
                solver explaining why they were rejected.  (All packages
                found in solver's trim database.)"""

                assert self.state >= EVALUATED_PKGS
                # in case this operation doesn't use solver
                if self.__pkg_solver is None:
                        return []

                return self.__pkg_solver.get_trim_errors()

        def get_plan(self, full=True):
                if full:
                        return str(self)

                output = ""
                for t in self.__fmri_changes:
                        output += "%s -> %s\n" % t
                return output

        def display(self):
                if DebugValues["plan"]:
                        logger.info(self.__verbose_str())
                else:
                        logger.info(str(self))

        def gen_new_installed_pkgs(self):
                """Generates all the fmris which will be in the new image."""
                assert self.state >= EVALUATED_PKGS
                fmri_set = set(self.image.gen_installed_pkgs())

                for p in self.pkg_plans:
                        p.update_pkg_set(fmri_set)

                for pfmri in fmri_set:
                        yield pfmri

        def gen_only_new_installed_pkgs(self):
                """Generates all the fmris which are being installed (or fixed,
                etc.)."""
                assert self.state >= EVALUATED_PKGS

                for p in self.pkg_plans:
                        if p.destination_fmri:
                                yield p.destination_fmri

        def gen_outgoing_pkgs(self):
                """Generates all the fmris which are being removed."""
                assert self.state >= EVALUATED_PKGS

                for p in self.pkg_plans:
                        if p.origin_fmri and p.origin_fmri != p.destination_fmri:
                                yield p.origin_fmri

        def gen_new_installed_actions_bytype(self, atype, implicit_dirs=False):
                """Generates actions of type 'atype' from the packages in the
                future image."""

                return self.__gen_star_actions_bytype(atype,
                    self.gen_new_installed_pkgs, implicit_dirs=implicit_dirs)

        def gen_only_new_installed_actions_bytype(self, atype, implicit_dirs=False):
                """Generates actions of type 'atype' from packages being
                installed."""

                return self.__gen_star_actions_bytype(atype,
                    self.gen_only_new_installed_pkgs, implicit_dirs=implicit_dirs)

        def gen_outgoing_actions_bytype(self, atype, implicit_dirs=False):
                """Generates actions of type 'atype' from packages being
                removed (not necessarily actions being removed)."""

                return self.__gen_star_actions_bytype(atype,
                    self.gen_outgoing_pkgs, implicit_dirs=implicit_dirs)

        def __gen_star_actions_bytype(self, atype, generator, implicit_dirs=False):
                """Generate installed actions of type 'atype' from the package
                fmris emitted by 'generator'.  If 'implicit_dirs' is True, then
                when 'atype' is 'dir', directories only implicitly delivered
                in the image will be emitted as well."""

                assert self.state >= EVALUATED_PKGS

                # Don't bother accounting for implicit directories if we're not
                # looking for them.
                if implicit_dirs and atype != "dir":
                        implicit_dirs = False

                for pfmri in generator():
                        m = self.image.get_manifest(pfmri)
                        dirs = set() # Keep track of explicit dirs
                        for act in m.gen_actions_by_type(atype,
                            self.__new_excludes):
                                if implicit_dirs:
                                        dirs.add(act.attrs["path"])
                                yield act, pfmri
                        if implicit_dirs:
                                da = pkg.actions.directory.DirectoryAction
                                for d in m.get_directories(self.__new_excludes):
                                        if d not in dirs:
                                                yield da(path=d, implicit="true"), pfmri

        def __get_directories(self):
                """ return set of all directories in target image """
                # always consider var and the image directory fixed in image...
                if self.__directories == None:
                        dirs = set([self.image.imgdir.rstrip("/"),
                                    "var",
                                    "var/sadm",
                                    "var/sadm/install"])
                        dirs.update((
                            os.path.normpath(d[0].attrs["path"])
                            for d in self.gen_new_installed_actions_bytype("dir",
                                implicit_dirs=True)
                        ))
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

        def __check_inconsistent_types(self, actions, oactions):
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

        def __check_duplicate_actions(self, actions, oactions):
                """Check whether we deliver more than one action with a given
                key attribute value if only a single action of that type and
                value may be delivered."""

                # We end up with no actions or start with one or none and end
                # with exactly one.
                if len(actions) == 0 or (len(oactions) <= len(actions) == 1):
                        return None

                # Removing actions.
                if len(actions) < len(oactions):
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
                                errors = self.__find_inconsistent_attrs(actions,
                                    ignore=["preserve"])
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

        def __check_inconsistent_attrs(self, actions, oactions):
                """Check whether we have non-identical actions delivering to the
                same point in their namespace."""

                nproblems = self.__find_inconsistent_attrs(actions)
                oproblems = self.__find_inconsistent_attrs(oactions)

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
                        # XXX The lambda: False is temporary until fix is moved
                        # into the API and self.__check_cancel can be used.
                        pp = pkgplan.PkgPlan(self.image, self.__progtrack,
                            lambda: False)
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
                        self.pkg_plans.append(pp)

                        # Repairs end up going into the package plan's update
                        # and remove lists, so ActionPlans needed to be appended
                        # for each action in this fixup pkgplan to the list of
                        # related actions.
                        for action in install:
                                self.update_actions.append(ActionPlan(pp, None,
                                    action))
                        for action in remove:
                                self.removal_actions.append(ActionPlan(pp,
                                    action, None))

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

                if not isinstance(msg, basestring):
                        return False

                if msg == "nothing":
                        for i, ap in enumerate(self.removal_actions):
                                if ap and ap.src.attrs.get(ap.src.key_attr,
                                    None) == key:
                                        self.removal_actions[i] = None
                elif msg == "overlay":
                        pp_needs_trimming = {}
                        for al in (self.install_actions, self.update_actions):
                                for i, ap in enumerate(al):
                                        if not (ap and ap.dst.attrs.get(
                                            ap.dst.key_attr, None) == key):
                                                continue
                                        if ap.dst.attrs.get("overlay") == \
                                            "allow":
                                                # Remove overlaid actions from
                                                # plan.
                                                al[i] = None
                                                pp_needs_trimming.setdefault(id(ap.p),
                                                    { "plan": ap.p, "trim": [] })
                                                pp_needs_trimming[id(ap.p)]["trim"].append(
                                                    id(ap.dst))
                                                break

                        for entry in pp_needs_trimming.values():
                                p = entry["plan"]
                                trim = entry["trim"]
                                # Can't modify the p.actions tuple, so modify
                                # the added member in-place.
                                for prop in ("added", "changed"):
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
                        assert False, "%s() returned something other than " \
                            "'nothing', 'overlay', 'error', or 'fixup': '%s'" % \
                            (func.__name__, msg)

                return True

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
                        return

                # Group action types by namespace groups
                kf = operator.attrgetter("namespace_group")
                types = sorted(pkg.actions.types.itervalues(), key=kf)

                namespace_dict = dict(
                    (ns, list(action_classes))
                    for ns, action_classes in itertools.groupby(types, kf)
                )

                errs = []

                old_fmris = set(self.image.gen_installed_pkgs())
                new_fmris = set(self.gen_new_installed_pkgs())
                gone_fmris = old_fmris - new_fmris

                # If we're removing all packages, there won't be any conflicts.
                if not new_fmris:
                        return

                # Load information about the actions currently on the system.
                actdict = self.image._load_actdict()
                sf = self.image._get_stripped_actions_file()

                # Iterate over action types in namespace groups first; our first
                # check should be for action type consistency.
                for ns, action_classes in namespace_dict.iteritems():
                        # There's no sense in checking actions which have no
                        # limits
                        if all(not c.globally_identical for c in action_classes):
                                continue

                        # The 'new' dict contains information about the system
                        # as it will be.  We start by accumulating actions from
                        # the manifests of the packages being installed.
                        new = {}
                        for klass in action_classes:
                                for a, pfmri in self.gen_only_new_installed_actions_bytype(klass.name, implicit_dirs=True):
                                        self.__progtrack.evaluate_progress()
                                        new.setdefault(a.attrs[klass.key_attr], []).append((a, pfmri))

                        # The 'old' dict contains information about the system
                        # as it is now.  We start by accumulating actions from
                        # the manifests of the packages being removed.
                        old = {}
                        for klass in action_classes:
                                for a, pfmri in self.gen_outgoing_actions_bytype(klass.name, implicit_dirs=True):
                                        self.__progtrack.evaluate_progress()
                                        old.setdefault(a.attrs[klass.key_attr], []).append((a, pfmri))

                        # Update 'old' with all actions from the action cache
                        # which could conflict with the new actions being
                        # installed, or with actions already installed, but not
                        # getting removed.
                        for key in set(itertools.chain(new.iterkeys(), old.keys())):
                                offsets = []
                                for klass in action_classes:
                                        offset = actdict.get((klass.name, key), None)
                                        if offset is not None:
                                                offsets.append(offset)

                                for offset in offsets:
                                        sf.seek(offset)
                                        pns = None
                                        for line in sf:
                                                fmristr, actstr = line.rstrip().split(None, 1)
                                                act = pkg.actions.fromstr(actstr)
                                                if act.attrs[act.key_attr] != key:
                                                        break
                                                if pns is not None and \
                                                    act.namespace_group != pns:
                                                        break
                                                pns = act.namespace_group
                                                pfmri = pkg.fmri.PkgFmri(fmristr, "5.11")
                                                if pfmri not in gone_fmris:
                                                        old.setdefault(key, []).append((act, pfmri))

                        # Now update 'new' with all actions from the action
                        # cache which are staying on the system, and could
                        # conflict with the actions being installed.
                        for key in old.iterkeys():
                                # If we're not changing any fmris, as in the
                                # case of a change-facet/variant, revert, fix,
                                # or set-mediator, then we need to skip modifying
                                # new, as it'll just end up with incorrect
                                # duplicates.
                                if self.planned_op in (self.PLANNED_FIX,
                                    self.PLANNED_VARIANT, self.PLANNED_REVERT,
                                    self.PLANNED_MEDIATOR):
                                        break
                                offsets = []
                                for klass in action_classes:
                                        offset = actdict.get((klass.name, key), None)
                                        if offset is not None:
                                                offsets.append(offset)

                                for offset in offsets:
                                        sf.seek(offset)
                                        pns = None
                                        for line in sf:
                                                fmristr, actstr = line.rstrip().split(None, 1)
                                                act = pkg.actions.fromstr(actstr)
                                                if act.attrs[act.key_attr] != key:
                                                        break
                                                if pns is not None and \
                                                    act.namespace_group != pns:
                                                        break
                                                pns = act.namespace_group
                                                pfmri = pkg.fmri.PkgFmri(fmristr, "5.11")
                                                if pfmri not in gone_fmris:
                                                        new.setdefault(key, []).append((act, pfmri))

                        for key, actions in new.iteritems():
                                offsets = []
                                for klass in action_classes:
                                        offset = actdict.get((klass.name, key), None)
                                        if offset is not None:
                                                offsets.append(offset)

                                oactions = old.get(key, [])

                                self.__progtrack.evaluate_progress()

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
                                if not actions[0][0].refcountable and \
                                    actions[0][0].globally_identical:
                                        if self.__process_conflicts(key,
                                            self.__check_duplicate_actions,
                                            actions, oactions,
                                            api_errors.DuplicateActionError,
                                            errs):
                                                continue

                                # Multiple refcountable but globally unique
                                # actions delivered to the same name must be
                                # identical.
                                elif actions[0][0].globally_identical:
                                        if self.__process_conflicts(key,
                                            self.__check_inconsistent_attrs,
                                            actions, oactions,
                                            api_errors.InconsistentActionAttributeError,
                                            errs):
                                                continue

                sf.close()
                self.__evaluate_fixups()

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

        def __get_manifest(self, pfmri, intent, all_variants=False):
                """Return manifest for pfmri"""
                if pfmri:
                        return self.image.get_manifest(pfmri,
                            all_variants=all_variants or self.__varcets_change,
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
                    "operation": self._planned_op,
                    "old_fmri" : old_fmri,
                    "new_fmri" : new_fmri,
                    "reference": reference
                }

                s = "(%s)" % ";".join([
                    "%s=%s" % (key, info[key]) for key in info
                    if info[key] is not None
                ])

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
                        d = self.__actuators.install
                elif phase == "remove":
                        d = self.__actuators.removal
                elif phase == "update":
                        d = self.__actuators.update

                if callable(value):
                        d[name] = value
                else:
                        d.setdefault(name, []).append(value)

        def evaluate(self):
                """Given already determined fmri changes,
                build pkg plans and figure out exact impact of
                proposed changes"""

                assert self.state == EVALUATED_PKGS, self

                if self._image_lm != self.image.get_last_modified():
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        raise api_errors.InvalidPlanError()

                plandir = self.image.plandir
                if self.__mode in [IP_MODE_DEFAULT, IP_MODE_SAVE]:
                        self.evaluate_pkg_plans()
                        if self.__mode == IP_MODE_SAVE:
                                self.__save(STATE_FILE_ACTIONS)
                else:
                        assert self.__mode == IP_MODE_LOAD
                        self.pkg_plans = self.__load(STATE_FILE_ACTIONS)

                self.merge_actions()

                for p in self.pkg_plans:
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
                                        self.__cbytes_added += \
                                            os.stat(mpath).st_size * 3
                                except EnvironmentError, e:
                                        raise apx._convert_error(e)
                        self.__cbytes_added += cpbytes
                        self.__bytes_added += pbytes

                # Include state directory in cbytes_added for now since it's
                # closest to where the download cache is stored.  (Twice the
                # amount is used because image state update involves using
                # a complete copy of existing state.)
                self.__cbytes_added += \
                    misc.get_dir_size(self.image._statedir) * 2

                # Our slop factor is 25%; overestimating is safer than under-
                # estimating.  This attempts to approximate how much overhead
                # the filesystem will impose on the operation.  Empirical
                # testing suggests that overhead can vary wildly depending on
                # average file size, fragmentation, zfs metadata overhead, etc.
                # For an install of a package such as solaris-small-server into
                # an image, a 12% difference between actual size and installed
                # size was found, so this seems safe enough.  (And helps account
                # for any bootarchives, fs overhead, etc.)
                self.__cbytes_added *= 1.25
                self.__bytes_added *= 1.25

                # XXX For now, include cbytes_added in bytes_added total; in the
                # future, this should only happen if they share the same
                # filesystem.
                self.__bytes_added += self.__cbytes_added

                self.__update_avail_space()

        def __update_avail_space(self):
                """Update amount of available space on FS"""
                self.__cbytes_avail = misc.spaceavail(
                    self.image.write_cache_path)

                self.__bytes_avail = misc.spaceavail(self.image.root)
                # if we don't have a full image yet
                if self.__cbytes_avail < 0:
                        self.__cbytes_avail = self.__bytes_avail

        def evaluate_pkg_plans(self):
                """Internal helper function that does the work of converting
                fmri changes into pkg plans."""

                # prefetch manifests
                prefetch_mfsts = [] # manifest, intents to be prefetched
                eval_list = []     # oldfmri, oldintent, newfmri, newintent
                                   # prefetched intents omitted
                enabled_publishers = set([
                                a.prefix
                                for a in self.image.gen_publishers()
                                ])

                for oldfmri, newfmri in self.__fmri_changes:
                        self.__progtrack.evaluate_progress(oldfmri)
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

                # No longer needed.
                del enabled_publishers
                self.__match_inst = {}
                self.__match_rm = {}

                self.image.transport.prefetch_manifests(prefetch_mfsts,
                    ccancel=self.__check_cancel)

                # No longer needed.
                del prefetch_mfsts

                for oldfmri, old_in, newfmri, new_in in eval_list:
                        pp = pkgplan.PkgPlan(self.image, self.__progtrack,
                            self.__check_cancel)

                        pp.propose(
                            oldfmri, self.__get_manifest(oldfmri, old_in),
                            newfmri, self.__get_manifest(newfmri, new_in,
                            all_variants=True))

                        pp.evaluate(self.__old_excludes, self.__new_excludes)

                        self.pkg_plans.append(pp)
                        pp = None
                        self.__progtrack.evaluate_progress()

                # No longer needed.
                del eval_list

        def __mediate_links(self, mediated_removed_paths):
                """Mediate links in the plan--this requires first determining the
                possible mediation for each mediator.  This is done solely based
                on the metadata of the links that are still or will be installed.
                Returns a dictionary of the proposed mediations."""

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
                                # 5.11 doesn't matter here and is never exposed
                                # to users.
                                med_ver = pkg.version.Version(med_ver, "5.11")
                        med_impl = a.attrs.get("mediator-implementation")
                        if not (med_ver or med_impl):
                                # Link mediation is incomplete.
                                continue
                        med_priority = a.attrs.get("mediator-priority")
                        prop_mediators[mediator].add((med_priority, med_ver,
                            med_impl))
                        mediated_installed_paths[a.attrs["path"]].add((a, pfmri,
                            mediator, med_ver, med_impl))

                # Now select only the "best" mediation for each mediator; items()
                # is used here as the dictionary is altered during iteration.
                cfg_mediators = self.image.cfg.mediators
                changed_mediators = set()
                for mediator, values in prop_mediators.items():
                        med_ver_source = med_impl_source = med_priority = \
                            med_ver = med_impl = med_impl_ver = None

                        mediation = self.__new_mediators.get(mediator)
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
                            cmp=med.cmp_mediations):
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

                cfg_mediators = self.image.cfg.mediators
                for al, ptype in ((self.install_actions, "added"),
                    (self.update_actions, "changed")):
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
                                        # 5.11 doesn't matter here and is never
                                        # exposed to users.
                                        med_ver = pkg.version.Version(med_ver,
                                            "5.11")
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
                        self.removal_actions.append(ActionPlan(
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

                cfg_mediators = self.image.cfg.mediators
                for m in self.__new_mediators:
                        prop_mediators.setdefault(m, self.__new_mediators[m])
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

                for m, new_mediation in prop_mediators.iteritems():
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
                self.__mediators_change = True

                for m in prop_mediators.keys():
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
                            for k in set(prop_mediators[m].keys() +
                                mediation.keys())
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
                                self.__mediators_change = False

                self.__new_mediators = prop_mediators

                # Link mediation is complete.
                self.__progtrack.evaluate_progress()

        def merge_actions(self):
                """Given a set of fmri changes and their associated pkg plan,
                merge all the resultant actions for the packages being
                updated."""

                if self.__new_mediators is None:
                        self.__new_mediators = {}

                if self.image.has_boot_archive():
                        ramdisk_prefixes = tuple(
                            self.image.get_ramdisk_filelist())
                        if not ramdisk_prefixes:
                                self.__need_boot_archive = False
                else:
                        self.__need_boot_archive = False

                # now combine all actions together to create a synthetic
                # single step upgrade operation, and handle editable
                # files moving from package to package.  See theory
                # comment in execute, below.

                for pp in self.pkg_plans:
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

                self.removal_actions = []
                cfg_mediators = self.image.cfg.mediators
                mediated_removed_paths = set()
                for p in self.pkg_plans:
                        for src, dest in p.gen_removal_actions():
                                if src.name == "user":
                                        self.removed_users[src.attrs["username"]] = \
                                            p.origin_fmri
                                elif src.name == "group":
                                        self.removed_groups[src.attrs["groupname"]] = \
                                            p.origin_fmri

                                self.removal_actions.append(ActionPlan(p, src,
                                    dest))
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

                self.__progtrack.evaluate_progress()

                self.update_actions = []
                for p in self.pkg_plans:
                        for src, dest in p.gen_update_actions():
                                if dest.name == "user":
                                        self.added_users[dest.attrs["username"]] = \
                                            p.destination_fmri
                                elif dest.name == "group":
                                        self.added_groups[dest.attrs["groupname"]] = \
                                            p.destination_fmri
                                self.update_actions.append(ActionPlan(p, src,
                                    dest))
                self.__progtrack.evaluate_progress()

                self.install_actions = []
                for p in self.pkg_plans:
                        for src, dest in p.gen_install_actions():
                                if dest.name == "user":
                                        self.added_users[dest.attrs["username"]] = \
                                            p.destination_fmri
                                elif dest.name == "group":
                                        self.added_groups[dest.attrs["groupname"]] = \
                                            p.destination_fmri
                                self.install_actions.append(ActionPlan(p, src,
                                    dest))
                self.__progtrack.evaluate_progress()

                # In case a removed user or group was added back...
                for entry in self.added_groups.keys():
                        if entry in self.removed_groups:
                                del self.removed_groups[entry]
                for entry in self.added_users.keys():
                        if entry in self.removed_users:
                                del self.removed_users[entry]

                self.state = MERGED_OK

                self.__find_all_conflicts()

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

                for i, ap in enumerate(self.removal_actions):
                        if ap is None:
                                continue
                        self.__progtrack.evaluate_progress()

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
                                        if mediator in self.__new_mediators:
                                                src_version = ap.src.attrs.get(
                                                    "mediator-version")
                                                src_impl = ap.src.attrs.get(
                                                    "mediator-implementation")
                                                dest_version = \
                                                    self.__new_mediators[mediator].get(
                                                        "version")
                                                if dest_version:
                                                        # Requested version needs
                                                        # to be a string for
                                                        # comparison.
                                                        dest_version = \
                                                            dest_version.get_short_version()
                                                dest_impl = \
                                                    self.__new_mediators[mediator].get(
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
                                self.removal_actions[i] = None
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
                                            "%s:%s" % (ap.p.origin_fmri.get_name(),
                                            attrs["path"]))
                                        cons_named[fname] = re
                                        fname = None
                                attrs = re = None

                        self.__actuators.scan_removal(ap.src.attrs)
                        if self.__need_boot_archive is None:
                                if ap.src.attrs.get("path", "").startswith(
                                    ramdisk_prefixes):
                                        self.__need_boot_archive = True

                self.__progtrack.evaluate_progress()

                # Construct a mapping from the install actions in a pkgplan to
                # the position they have in the plan's list.  This allows us to
                # remove them efficiently later, if they've been consolidated.
                #
                # NOTE: This means that the action ordering in the package plans
                # must remain fixed, at least for the duration of the imageplan
                # evaluation.
                plan_pos = {}
                for p in self.pkg_plans:
                        for i, a in enumerate(p.gen_install_actions()):
                                plan_pos[id(a[1])] = i

                # This keeps track of which pkgplans have had install actions
                # consolidated away.
                pp_needs_trimming = set()

                # This maps destination actions to the pkgplans they're
                # associated with, which allows us to create the newly
                # discovered update ActionPlans.
                dest_pkgplans = {}

                new_updates = []
                for i, ap in enumerate(self.install_actions):
                        if ap is None:
                                continue
                        self.__progtrack.evaluate_progress()

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
                                ra = self.removal_actions[index].src
                                assert(id(ra) == cons_named[cache_name].id)
                                # If the paths match, don't remove and add;
                                # convert to update.
                                if ap.dst.attrs["path"] == ra.attrs["path"]:
                                        new_updates.append((ra, ap.dst))
                                        # If we delete items here, the indices
                                        # in cons_named will be bogus, so mark
                                        # them for later deletion.
                                        self.removal_actions[index] = None
                                        self.install_actions[i] = None
                                        # No need to handle it in cons_generic
                                        # anymore
                                        del cons_generic[("file", ra.attrs["path"])]
                                        dest_pkgplans[id(ap.dst)] = ap.p
                                else:
                                        ra.attrs["save_file"] = cache_name
                                        ap.dst.attrs["save_file"] = cache_name

                                cache_name = index = ra = None

                        # Similarly, try to prevent files (and other actions)
                        # from unnecessarily being deleted and re-created if
                        # they're simply moving between packages, but only if
                        # they keep their paths (or key-attribute values).
                        keyval = hashify(ap.dst.attrs.get(ap.dst.key_attr, None))
                        if (ap.dst.name, keyval) in cons_generic:
                                nkv = ap.dst.name, keyval
                                index = cons_generic[nkv].idx
                                ra = self.removal_actions[index].src
                                assert(id(ra) == cons_generic[nkv].id)
                                if keyval == ra.attrs[ra.key_attr]:
                                        new_updates.append((ra, ap.dst))
                                        self.removal_actions[index] = None
                                        self.install_actions[i] = None
                                        dest_pkgplans[id(ap.dst)] = ap.p
                                        # Add the action to the pkgplan's update
                                        # list and mark it for removal from the
                                        # install list.
                                        ap.p.actions.changed.append((ra, ap.dst))
                                        ap.p.actions.added[plan_pos[id(ap.dst)]] = None
                                        pp_needs_trimming.add(ap.p)
                                nkv = index = ra = None

                        self.__actuators.scan_install(ap.dst.attrs)
                        if self.__need_boot_archive is None:
                                if ap.dst.attrs.get("path", "").startswith(
                                    ramdisk_prefixes):
                                        self.__need_boot_archive = True

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

                # We want to cull out actions where they've not changed at all,
                # leaving only the changed ones to put into self.update_actions.
                nu_src = manifest.Manifest()
                nu_src.set_content(content=(a[0] for a in new_updates),
                    excludes=self.__old_excludes)
                nu_dst = manifest.Manifest()
                self.__progtrack.evaluate_progress()
                nu_dst.set_content(content=(a[1] for a in new_updates),
                    excludes=self.__new_excludes)
                del new_updates
                self.__progtrack.evaluate_progress()
                nu_add, nu_chg, nu_rem = nu_dst.difference(nu_src,
                    self.__old_excludes, self.__new_excludes)
                self.__progtrack.evaluate_progress()
                # All the differences should be updates
                assert not nu_add
                assert not nu_rem
                del nu_src, nu_dst

                # Extend update_actions with the new tuples.  The package plan
                # is the one associated with the action getting installed.
                self.update_actions.extend([
                    ActionPlan(dest_pkgplans[id(dst)], src, dst)
                    for src, dst in nu_chg
                ])

                del dest_pkgplans, nu_chg

                self.__progtrack.evaluate_progress()

                # Mediate and repair links affected by the plan.
                prop_mediators = self.__mediate_links(mediated_removed_paths)

                for prop in ("removal_actions", "install_actions",
                    "update_actions"):
                        pval = getattr(self, prop)
                        pval[:] = [
                            a
                            for a in pval
                            if a is not None
                        ]

                # Add any necessary repairs to plan.
                self.__evaluate_fixups()

                # Finalize link mediation.
                self.__finalize_mediation(prop_mediators)

                # Go over update actions
                l_actions = self.get_actions("hardlink", self.hardlink_keyfunc)
                l_refresh = []
                for a in self.update_actions:
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
                                            ActionPlan(a[0], l, l)
                                            for l in unique_links.values()
                                        ])
                                path = None

                        # scan both old and new actions
                        # repairs may result in update action w/o orig action
                        if a[1]:
                                self.__actuators.scan_update(a[1].attrs)
                        self.__actuators.scan_update(a[2].attrs)
                        if self.__need_boot_archive is None:
                                if a[2].attrs.get("path", "").startswith(
                                    ramdisk_prefixes):
                                        self.__need_boot_archive = True

                self.update_actions.extend(l_refresh)

                # sort actions to match needed processing order
                self.removal_actions.sort(key = lambda obj:obj[1], reverse=True)
                self.update_actions.sort(key = lambda obj:obj[2])
                self.install_actions.sort(key = lambda obj:obj[2])

                # Pre-calculate size of data retrieval for preexecute().
                npkgs = nfiles = nbytes = 0
                for p in self.pkg_plans:
                        nf, nb = p.get_xferstats()
                        nbytes += nb
                        nfiles += nf

                        # It's not perfectly accurate but we count a download
                        # even if the package will do zero data transfer.  This
                        # makes the pkg stats consistent between download and
                        # install.
                        npkgs += 1
                self.__progtrack.download_set_goal(npkgs, nfiles, nbytes)

                # Evaluation complete.
                self.__progtrack.evaluate_done(self.__target_install_count, \
                    self.__target_update_count, self.__target_removal_count)

                if self.__need_boot_archive is None:
                        self.__need_boot_archive = False

                self.state = EVALUATED_OK

        def nothingtodo(self):
                """Test whether this image plan contains any work to do """

                if self.state == EVALUATED_PKGS:
                        return not (self.__fmri_changes or
                            self.__new_variants or
                            (self.__new_facets is not None) or
                            self.__mediators_change or
                            self.pkg_plans)
                elif self.state >= EVALUATED_OK:
                        return not (self.pkg_plans or self.__new_variants or
                            (self.__new_facets is not None) or
                            self.__mediators_change)

        def preexecute(self):
                """Invoke the evaluated image plan
                preexecute, execute and postexecute
                execute actions need to be sorted across packages
                """

                assert self.state == EVALUATED_OK

                if self._image_lm != self.image.get_last_modified():
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        self.state = PREEXECUTED_ERROR
                        raise api_errors.InvalidPlanError()

                if self.nothingtodo():
                        self.state = PREEXECUTED_OK
                        return

                if self.image.version != self.image.CURRENT_VERSION:
                        # Prevent plan execution if image format isn't current.
                        raise api_errors.ImageFormatUpdateNeeded(
                            self.image.root)

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
                                        except se.IncorrectIndexFileHash, e:
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
                        except se.IndexingException, e:
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
                if self.__cbytes_added > self.__cbytes_avail: 
                        raise api_errors.ImageInsufficentSpace(
                            self.__cbytes_added,
                            self.__cbytes_avail,
                            _("Download cache"))
                if self.__bytes_added > self.__bytes_avail:
                        raise api_errors.ImageInsufficentSpace(
                            self.__bytes_added,
                            self.__bytes_avail,
                            _("Root filesystem"))

                # Remove history about manifest/catalog transactions.  This
                # helps the stats engine by only considering the performance of
                # bulk downloads.
                self.image.transport.stats.reset()

                lic_errors = []
                try:
                        # Check for license acceptance issues first to avoid
                        # wasted time in the download phase and so failure
                        # can occur early.
                        for p in self.pkg_plans:
                                try:
                                        p.preexecute()
                                except api_errors.PkgLicenseErrors, e:
                                        # Accumulate all license errors.
                                        lic_errors.append(e)
                                except EnvironmentError, e:
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
                                for p in self.pkg_plans:
                                        p.download()
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise
                        except (api_errors.InvalidDepotResponseException,
                            api_errors.TransportError), e:
                                if p and p._autofix_pkgs:
                                        e._autofix_pkgs = p._autofix_pkgs
                                raise

                        self.__progtrack.download_done()
                        self.image.transport.shutdown()
                except:
                        self.state = PREEXECUTED_ERROR
                        raise

                self.state = PREEXECUTED_OK

        def execute(self):
                """Invoke the evaluated image plan
                preexecute, execute and postexecute
                execute actions need to be sorted across packages
                """
                assert self.state == PREEXECUTED_OK

                if self._image_lm != self.image.get_last_modified():
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        self.state = EXECUTED_ERROR
                        raise api_errors.InvalidPlanError()

                # check for available space
                self.__update_avail_space()
                if self.__bytes_added > self.__bytes_avail:
                        raise api_errors.ImageInsufficentSpace(
                            self.__bytes_added,
                            self.__bytes_avail,
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
                # 2) Installs of new actions must preceed updates of existing
                # ones.
                #
                #    In order to accomodate changes of file ownership of
                #    existing files to a newly created user, it is necessary
                #    for the installation of that user to preceed the update of
                #    files to reflect their new ownership.
                #

                if self.nothingtodo():
                        self.state = EXECUTED_OK
                        return

                # It's necessary to do this check here because the state of the
                # image before the current operation is performed is desired.
                empty_image = self.__is_image_empty()

                self.__actuators.exec_prep(self.image)

                self.__actuators.exec_pre_actuators(self.image)

                # List of tuples of (src, dest) used to track each pkgplan so
                # that it can be discarded after execution.
                executed_pp = []
                try:
                        try:

                                # execute removals
                                self.__progtrack.actions_set_goal(
                                    _("Removal Phase"),
                                    len(self.removal_actions))
                                for p, src, dest in self.removal_actions:
                                        p.execute_removal(src, dest)
                                        self.__progtrack.actions_add_progress()
                                self.__progtrack.actions_done()

                                # Done with removals; discard them so memory can
                                # be re-used.
                                self.removal_actions = []

                                # execute installs
                                self.__progtrack.actions_set_goal(
                                    _("Install Phase"),
                                    len(self.install_actions))

                                for p, src, dest in self.install_actions:
                                        p.execute_install(src, dest)
                                        self.__progtrack.actions_add_progress()
                                self.__progtrack.actions_done()

                                # Done with installs, so discard them so memory
                                # can be re-used.
                                self.install_actions = []

                                # execute updates
                                self.__progtrack.actions_set_goal(
                                    _("Update Phase"),
                                    len(self.update_actions))

                                for p, src, dest in self.update_actions:
                                        p.execute_update(src, dest)
                                        self.__progtrack.actions_add_progress()

                                self.__progtrack.actions_done()

                                # Done with updates, so discard them so memory
                                # can be re-used.
                                self.update_actions = []

                                # handle any postexecute operations
                                while self.pkg_plans:
                                        # postexecute in reverse, but pkg_plans
                                        # aren't ordered, so does it matter?
                                        # This allows the pkgplan objects to be
                                        # discarded as they're executed which
                                        # allows memory to be-reused sooner.
                                        p = self.pkg_plans.pop()
                                        p.postexecute()
                                        executed_pp.append((p.destination_fmri,
                                            p.origin_fmri))
                                        p = None

                                # save package state
                                self.image.update_pkg_installed_state(
                                    executed_pp, self.__progtrack)

                                # write out variant changes to the image config
                                if self.__varcets_change or \
                                    self.__mediators_change:
                                        self.image.image_config_update(
                                            self.__new_variants,
                                            self.__new_facets,
                                            self.__new_mediators)
                                # write out any changes
                                self.image._avoid_set_save(*self.__new_avoid_obs)

                        except EnvironmentError, e:
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
                                            "'%s'; a file or directory was "
                                            "expected.  Please remove the link "
                                            "and try again.") % e.filename)
                                raise
                except pkg.actions.ActionError:
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        self.state = EXECUTED_ERROR
                        try:
                                self.__actuators.exec_fail_actuators(self.image)
                        except:
                                # Ensure the real cause of failure is raised.
                                pass
                        raise api_errors.InvalidPackageErrors([
                            exc_value]), None, exc_tb
                except:
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        self.state = EXECUTED_ERROR
                        try:
                                self.__actuators.exec_fail_actuators(self.image)
                        finally:
                                # This ensures that the original exception and
                                # traceback are used if exec_fail_actuators
                                # fails.
                                raise exc_value, None, exc_tb
                else:
                        self.__actuators.exec_post_actuators(self.image)

                self.image._create_fast_lookups()

                self.state = EXECUTED_OK

                # reduce memory consumption
                self.added_groups = {}
                self.removed_groups = {}
                self.added_users = {}
                self.removed_users = {}
                self.saved_files = {}
                self.valid_directories = set()
                self.__fmri_changes  = []
                self.__directories   = []
                self.__actuators     = actuator.Actuator()
                self.__cached_actions = {}
                self.__symlinks = None
                self.__hardlinks = None
                self.__licenses = None
                self.__legacy = None

                # Clear out the primordial user and group caches.
                self.image._users = set()
                self.image._groups = set()
                self.image._usersbyname = {}
                self.image._groupsbyname = {}

                # Perform the incremental update to the search indexes
                # for all changed packages
                if self.update_index:
                        self.__progtrack.actions_set_goal(_("Index Phase"),
                            len(executed_pp))
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
                        except Exception, e:
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
                                except Exception, e:
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
                        self.image.gen_installed_pkg_names().next()
                        return False
                except StopIteration:
                        return True

        def match_user_stems(self, patterns, match_type, raise_unmatched=True,
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
                brelease = self.image.attrs["Build-Release"]

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
                                            pat_stem, brelease)
                                else:
                                        fmri = pkg.fmri.PkgFmri(
                                            pat_stem, brelease)

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
                        except pkg.fmri.FmriError, e:
                                illegals.append(e)
                patterns = npatterns
                del npatterns, seen

                # Create a dictionary of patterns, with each value being a
                # set of pkg names that match that pattern.
                ret = dict(zip(patterns, [set() for i in patterns]))

                if universe is not None:
                        assert match_type == self.MATCH_ALL
                        pkg_names = universe
                else:
                        if match_type != self.MATCH_INST_VERSIONS:
                                cat = self.image.get_catalog(
                                    self.image.IMG_CATALOG_KNOWN)
                        else:
                                cat = self.image.get_catalog(
                                    self.image.IMG_CATALOG_INSTALLED)
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

                if match_type == self.MATCH_INST_VERSIONS:
                        not_installed, nonmatch = nonmatch, not_installed
                elif match_type == self.MATCH_UNINSTALLED:
                        already_installed = [
                            name
                            for name in self.image.get_catalog(
                            self.image.IMG_CATALOG_INSTALLED).names()
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

        def __match_user_fmris(self, patterns, match_type,
            pub_ranks=misc.EmptyDict, installed_pkgs=misc.EmptyDict,
            raise_not_installed=True, reject_set=misc.EmptyI):
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
                trailing match rules are used for remaining patterns.

                Exactly duplicated patterns are ignored.

                Routine raises PlanCreationException if errors occur: it is
                illegal to specify multiple different patterns that match the
                same pkg name.  Only patterns that contain wildcards are allowed
                to match multiple packages.

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
                if match_type in [self.MATCH_INST_STEMS, self.MATCH_ALL]:
                        # build installed publisher dictionary
                        installed_pubs = dict((
                            (f.pkg_name, f.get_publisher())
                            for f in installed_pkgs.values()
                        ))

                # figure out which kind of matching rules to employ
                brelease = self.image.attrs["Build-Release"]
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
                                else:
                                        matcher = pkg.fmri.fmri_match

                                if matcher == pkg.fmri.glob_match:
                                        fmri = pkg.fmri.MatchingPkgFmri(
                                            pat_stem, brelease)
                                else:
                                        fmri = pkg.fmri.PkgFmri(
                                            pat_stem, brelease)

                                if not pat_ver:
                                        # Do nothing.
                                        pass
                                elif "*" in pat_ver or "?" in pat_ver or \
                                    pat_ver == "latest":
                                        fmri.version = \
                                            pkg.version.MatchingVersion(pat_ver,
                                                brelease)
                                else:
                                        fmri.version = \
                                            pkg.version.Version(pat_ver,
                                                brelease)

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
                            pkg.version.VersionError), e:
                                illegals.append(e)
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

                if match_type != self.MATCH_INST_VERSIONS:
                        cat = self.image.get_catalog(
                            self.image.IMG_CATALOG_KNOWN)
                        info_needed = [pkg.catalog.Catalog.DEPENDENCY]
                else:
                        cat = self.image.get_catalog(
                            self.image.IMG_CATALOG_INSTALLED)
                        info_needed = []

                variants = self.image.get_variants()
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
                                                elif not pub and match_type != self.MATCH_INST_VERSIONS and \
                                                    name in installed_pubs and \
                                                    pub_ranks[installed_pubs[name]][1] \
                                                    == True and installed_pubs[name] != \
                                                    fpub:
                                                        rejected_pubs.setdefault(pat,
                                                            set()).add(fpub)
                                                        continue # installed sticky pub
                                                elif match_type == self.MATCH_INST_STEMS and \
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

                                                        if self.image.PKG_STATE_RENAMED in states and \
                                                            a.name == "depend" and \
                                                            a.attrs["type"] == "require":
                                                                ren_deps.append(pkg.fmri.PkgFmri(
                                                                    a.attrs["fmri"], "5.11"))
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
                                                        for vn, vv in variants.iteritems():
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
                                                states = metadata["metadata"]["states"]
                                                if self.image.PKG_STATE_OBSOLETE in states:
                                                        obsolete_fmris.append(f)
                                                if self.image.PKG_STATE_RENAMED in states:
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

                                for pkg_name in ret[p].keys():
                                        if pkg_name in targets:
                                                del ret[p][pkg_name]

                # Determine match failures.
                matchdict = {}
                for p in patterns:
                        l = len(ret[p])
                        if l == 0: # no matches at all
                                if p in rejected_vars:
                                        wrongvar.add(p)
                                elif p in rejected_pubs:
                                        wrongpub.append((p, rejected_pubs[p]))
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
                                for k in ret[p].keys():
                                        # for each matching package name
                                        matchdict.setdefault(k, []).append(p)

                for name in matchdict:
                        if len(matchdict[name]) > 1:
                                # different pats, same pkg
                                multispec.append(tuple([name] +
                                    matchdict[name]))

                if match_type != self.MATCH_ALL:
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

                # merge patterns together now that there are no conflicts
                proposed_dict = {}
                for d in ret.values():
                        proposed_dict.update(d)

                # eliminate lower ranked publishers
                if match_type != self.MATCH_INST_VERSIONS:
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
                        for pname, flist in proposed_dict.iteritems():
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

        # We must save the planned fmri change or the pkg_plans
        class __save_encode(json.JSONEncoder):

                def default(self, obj):
                        """Required routine that overrides the default base
                        class version and attempts to serialize 'obj' when
                        attempting to save 'obj' json format."""

                        if isinstance(obj, pkg.fmri.PkgFmri):
                                return str(obj)
                        if isinstance(obj, pkg.client.pkgplan.PkgPlan):
                                return obj.getstate()
                        return json.JSONEncoder.default(self, obj)

        def __save(self, filename):
                """Json encode fmri changes or pkg plans and save them to a
                file."""

                assert filename in [STATE_FILE_PKGS, STATE_FILE_ACTIONS]
                if not os.path.isdir(self.image.plandir):
                        os.makedirs(self.image.plandir)

                # write the output file to a temporary file
                pathtmp = os.path.join(self.image.plandir,
                    "%s.%d.%d.json" % (filename, self.image.runid, os.getpid()))
                oflags = os.O_CREAT | os.O_TRUNC | os.O_WRONLY
                try:
                        fobj = os.fdopen(os.open(pathtmp, oflags, 0644), "wb")
                        if filename == STATE_FILE_PKGS:
                                json.dump(self.__fmri_changes, fobj,
                                    encoding="utf-8", cls=self.__save_encode)
                        elif filename == STATE_FILE_ACTIONS:
                                json.dump(self.pkg_plans, fobj,
                                    encoding="utf-8", cls=self.__save_encode)
                        fobj.close()
                except OSError, e:
                        raise api_errors._convert_error(e)

                # atomically create the desired file
                path = os.path.join(self.image.plandir,
                    "%s.%d.json" % (filename, self.image.runid))

                try:
                        os.rename(pathtmp, path)
                except OSError, e:
                        raise api_errors._convert_error(e)

        def __load_decode(self, dct):
                """Routine that takes a loaded json dictionary and converts
                any keys and/or values from unicode strings into ascii
                strings.  (Keys or values of other types are left
                unchanged.)"""

                # Replace unicode keys/values with strings
                rvdct = {}
                for k, v in dct.items():
                        # unicode must die
                        if type(k) == unicode:
                                k = k.encode("utf-8")
                        if type(v) == unicode:
                                v = v.encode("utf-8")
                        rvdct[k] = v
                return rvdct

        def __load(self, filename):
                """Load Json encoded fmri changes or pkg plans."""

                assert filename in [STATE_FILE_PKGS, STATE_FILE_ACTIONS]

                path = os.path.join(self.image.plandir,
                    "%s.%d.json" % (filename, self.image.runid))

                # load the json file
                try:
                        with open(path) as fobj:
                                # fobj will be closed when we exit this loop
                                data = json.load(fobj, encoding="utf-8",
                                    object_hook=self.__load_decode)
                except OSError, e:
                        raise api_errors._convert_error(e)

                if filename == STATE_FILE_PKGS:
                        assert(type(data) == list)
                        tuples = []
                        for (old, new) in data:
                                if old:
                                        old = pkg.fmri.PkgFmri(str(old))
                                if new:
                                        new = pkg.fmri.PkgFmri(str(new))
                                tuples.append((old, new))
                        return tuples

                elif filename == STATE_FILE_ACTIONS:
                        pkg_plans = []
                        for item in data:
                                pp = pkgplan.PkgPlan(self.image,
                                    self.__progtrack, self.__check_cancel)
                                pp.setstate(item)
                                pkg_plans.append(pp)
                        return pkg_plans

        def freeze_pkgs_match(self, pats):
                """Find the packages which match the given patterns and thus
                should be frozen."""

                pats = set(pats)
                freezes = set()
                pub_ranks = self.image.get_publisher_ranks()
                installed_version_mismatches = {}
                versionless_uninstalled = set()
                multiversions = []

                # Find the installed packages that match the provided patterns.
                inst_dict, references = self.__match_user_fmris(pats,
                    self.MATCH_INST_VERSIONS, pub_ranks=pub_ranks,
                    raise_not_installed=False)

                # Find the installed package stems that match the provided
                # patterns.
                installed_stems_dict = self.match_user_stems(pats,
                    self.MATCH_INST_VERSIONS, raise_unmatched=False,
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
                for full_fmri, pat in references.iteritems():
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
                        stems.setdefault(pkg.fmri.PkgFmri(p,
                            build_release="5.11").get_pkg_stem(anarchy=True,
                            include_scheme=False), set()).add(p)
                # Check whether one stem has been frozen at non-identical
                # versions.
                for k, v in stems.iteritems():
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
