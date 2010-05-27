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
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
#

from collections import namedtuple
import errno
import operator
import os
import traceback

from pkg.client import global_settings
logger = global_settings.logger

import pkg.actions
import pkg.catalog
import pkg.client.actuator   as actuator
import pkg.client.indexer    as indexer
import pkg.client.api_errors as api_errors
import pkg.client.pkgplan    as pkgplan
import pkg.client.pkg_solver as pkg_solver
import pkg.fmri
import pkg.manifest          as manifest
import pkg.search_errors     as se
import pkg.version
import sys

from pkg.client.debugvalues import DebugValues

UNEVALUATED       = 0 # nothing done yet
EVALUATED_PKGS    = 1 # established fmri changes
EVALUATED_OK      = 2 # ready to execute
PREEXECUTED_OK    = 3 # finished w/ preexecute
PREEXECUTED_ERROR = 4 # whoops
EXECUTED_OK       = 5 # finished execution
EXECUTED_ERROR    = 6 # failed

class ImagePlan(object):
        """ImagePlan object contains the plan for changing the image...
        there are separate routines for planning the various types of
        image modifying operations; evaluation (comparing manifests
        and buildig lists of removeal, install and update actions
        and their execution is all common code"""

        PLANNED_NOTHING   = "no-plan"
        PLANNED_INSTALL   = "install"
        PLANNED_UNINSTALL = "uninstall"
        PLANNED_UPDATE    = "image-update"
        PLANNED_FIX       = "fix"
        PLANNED_VARIANT   = "change-variant"

        def __init__(self, image, progtrack, check_cancel, noexecute=False):
                self.image = image
                self.pkg_plans = []

                self.state = UNEVALUATED
                self.__progtrack = progtrack
                self.__noexecute = noexecute
                
                self.__fmri_changes = [] # install  (None, fmri)
                                         # update   (oldfmri, newfmri)
                                         # remove   (oldfmri, None)
                                         # reinstall(oldfmri, oldfmri)

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
                self.__cached_actions = {} 

                self.__old_excludes = image.list_excludes()
                self.__new_excludes = self.__old_excludes

                self.__check_cancelation = check_cancel

                self.__actuators = None

                self.update_index = True

                self.__preexecuted_indexing_error = None
                self._planned_op = self.PLANNED_NOTHING
                self.__pkg_solver = None
                self.__new_variants = None
                self.__new_facets = None
                self.__variant_change = False
                self.__references = {} # dict of fmri -> pattern

        def __str__(self):

                if self.state == UNEVALUATED:
                        s = "UNEVALUATED:\n"
                        return s

                s = "%s\n" % self.__pkg_solver 

                if self.state < EVALUATED_PKGS:
                        return s

                s += "Package version changes:\n"

                for pp in self.pkg_plans:
                        s += "%s -> %s\n" % (pp.origin_fmri, pp.destination_fmri)

                if self.__actuators:
                        s = s + "Actuators:\n%s\n" % self.__actuators

                if self.__old_excludes != self.__new_excludes:
                        s = s + "Variants/Facet changes: %s -> %s\n" % (self.__old_excludes,
                            self.__new_excludes)

                return s

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

        def show_failure(self, verbose):
                """Here's where extensive messaging needs to go"""

                if self.__pkg_solver:
                        logger.info(_("Planning for %s failed: %s\n") % 
                            (self._planned_op, self.__pkg_solver.gen_failure_report(verbose)))

        def __plan_op(self, op):
                """Private helper method used to mark the start of a planned
                operation."""

                self._planned_op = op
                self._image_lm = self.image.get_last_modified()

        def plan_install(self, pkgs_to_install):
                """Determine the fmri changes needed to install the specified pkgs"""
                self.__plan_op(self.PLANNED_INSTALL)

                # get ranking of publishers
                pub_ranks = self.image.get_publisher_ranks()

                # build installed dict
                installed_dict = ImagePlan.__fmris2dict(self.image.gen_installed_pkgs())
                
                # build installed publisher dictionary
                installed_pubs = dict((
                                (f.pkg_name, f.get_publisher()) 
                                for f in installed_dict.values()
                                ))

                proposed_dict, self.__references = self.match_user_fmris(pkgs_to_install, 
                    True, pub_ranks, installed_pubs)
                
                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict, 
                    pub_ranks,
                    self.image.get_variants(),
                    self.__progtrack)

                # Solve... will raise exceptions if no solution is found 
                new_vector = self.__pkg_solver.solve_install([], proposed_dict, 
                    self.__new_excludes)

                self.__fmri_changes = [ 
                        (a, b)
                        for a, b in ImagePlan.__dicts2fmrichanges(installed_dict, 
                            ImagePlan.__fmris2dict(new_vector))
                        if a != b
                        ]
 
                self.state = EVALUATED_PKGS

        def plan_uninstall(self, pkgs_to_uninstall, recursive_removal=False):
                self.__plan_op(self.PLANNED_UNINSTALL)
                proposed_dict, self.__references = self.match_user_fmris(pkgs_to_uninstall, 
                    False, None, None)
                # merge patterns together
                proposed_removals = set([
                                f 
                                for each in proposed_dict.values()
                                for f in each
                                ])

                # build installed dict
                installed_dict = dict([
                        (f.pkg_name, f)
                        for f in self.image.gen_installed_pkgs()
                        ])
                                
                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict, 
                    self.image.get_publisher_ranks(),
                    self.image.get_variants(),
                    self.__progtrack)

                new_vector = self.__pkg_solver.solve_uninstall([], 
                    proposed_removals, recursive_removal, self.__new_excludes)

                self.__fmri_changes = [ 
                        (a, b)
                        for a, b in ImagePlan.__dicts2fmrichanges(installed_dict, 
                            ImagePlan.__fmris2dict(new_vector))
                        if a != b
                        ]

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

        def plan_update(self):
                """Determine the fmri changes needed to update all
                pkgs"""
                self.__plan_op(self.PLANNED_UPDATE)

                # build installed dict
                installed_dict = dict([
                        (f.pkg_name, f)
                        for f in self.image.gen_installed_pkgs()
                        ])
                                
                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict, 
                    self.image.get_publisher_ranks(),
                    self.image.get_variants(),
                    self.__progtrack)

                new_vector = self.__pkg_solver.solve_update([],  self.__new_excludes)

                self.__fmri_changes = [ 
                        (a, b)
                        for a, b in ImagePlan.__dicts2fmrichanges(installed_dict, 
                            ImagePlan.__fmris2dict(new_vector))
                        if a != b
                        ]
              
                self.state = EVALUATED_PKGS


        def plan_fix(self, pkgs_to_fix):
                """Create the list of pkgs to fix"""
                self.__plan_op(self.PLANNED_FIX)
                # XXX complete this

        def plan_change_varcets(self, variants, facets):
                """Determine the fmri changes needed to change
                the specified variants/facets"""
                self.__plan_op(self.PLANNED_VARIANT)

                if variants == None and facets == None: # nothing to do
                        self.state = EVALUATED_PKGS
                        return

                self.__variant_change = True

                # build installed dict
                installed_dict = dict([
                        (f.pkg_name, f)
                        for f in self.image.gen_installed_pkgs()
                        ])
                                
                # instantiate solver
                self.__pkg_solver = pkg_solver.PkgSolver(
                    self.image.get_catalog(self.image.IMG_CATALOG_KNOWN),
                    installed_dict, 
                    self.image.get_publisher_ranks(),
                    self.image.get_variants(),
                    self.__progtrack)

                self.__new_excludes = self.image.list_excludes(variants, facets)

                new_vector = self.__pkg_solver.solve_change_varcets([],
                    variants, facets, self.__new_excludes)

                self.__new_variants = variants
                self.__new_facets   = facets

                self.__fmri_changes = [ 
                        (a, b)
                        for a, b in ImagePlan.__dicts2fmrichanges(installed_dict, 
                            ImagePlan.__fmris2dict(new_vector))              
                        ]

                self.state = EVALUATED_PKGS
                return

        def reboot_needed(self):
                """Check if evaluated imageplan requires a reboot"""
                assert self.state >= EVALUATED_OK
                return self.__actuators.reboot_needed()


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
                """ generates all the fmris in the new set of installed pkgs"""
                assert self.state >= EVALUATED_PKGS
                fmri_set = set(self.image.gen_installed_pkgs())

                for p in self.pkg_plans:
                        p.update_pkg_set(fmri_set)

                for pfmri in fmri_set:
                        yield pfmri

        def gen_new_installed_actions(self):
                """generates actions in new installed image"""
                assert self.state >= EVALUATED_PKGS
                for pfmri in self.gen_new_installed_pkgs():
                        m = self.image.get_manifest(pfmri)
                        for act in m.gen_actions(self.__new_excludes):
                                yield act

        def gen_new_installed_actions_bytype(self, atype):
                """generates actions in new installed image"""
                assert self.state >= EVALUATED_PKGS
                for pfmri in self.gen_new_installed_pkgs():
                        m = self.image.get_manifest(pfmri)
                        for act in m.gen_actions_by_type(atype,
                            self.__new_excludes):
                                yield act

        def get_directories(self):
                """ return set of all directories in target image """
                # always consider var and var/pkg fixed in image....
                # XXX should be fixed for user images
                if self.__directories == None:
                        dirs = set(["var",
                                    "var/pkg",
                                    "var/sadm",
                                    "var/sadm/install"])
                        for pfmri in self.gen_new_installed_pkgs():
                                m = self.image.get_manifest(pfmri)
                                for d in m.get_directories(self.__new_excludes):
                                        dirs.add(os.path.normpath(d))
                        self.__directories = dirs
                return self.__directories

        def __get_symlinks(self):
                """ return a set of all symlinks in target image"""
                if self.__symlinks == None:
                        self.__symlinks = set((
                                        a.attrs["path"]
                                        for a in self.gen_new_installed_actions_bytype("link")
                                        ))
                return self.__symlinks

        def __get_hardlinks(self):
                """ return a set of all hardlinks in target image"""
                if self.__hardlinks == None:
                        self.__hardlinks = set((
                                        a.attrs["path"]
                                        for a in self.gen_new_installed_actions_bytype("hardlink")
                                        ))
                return self.__hardlinks

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
                for act in self.gen_new_installed_actions_bytype(name):
                        t = key(name, act)
                        d.setdefault(t, []).append(act)
                self.__cached_actions[(name, key)] = d
                return self.__cached_actions[(name, key)]

        def __get_manifest(self, pfmri, intent):
                """Return manifest for pfmri"""
                if pfmri:
                        return self.image.get_manifest(pfmri, 
                            all_variants=self.__variant_change, intent=intent)
                else:
                        return manifest.NullCachedManifest

        def __create_intent(self, old_fmri, new_fmri, enabled_publishers):
                """Return intent strings (or None).  Given a pair
                of fmris describing a package operation, this
                routine returns intent strings to be passed to
                originating publisher describing manifest
                operations.  We never send publisher info to
                prevent cross-publisher leakage of info."""

                if self.__noexecute:
                        return None, None

                if new_fmri:
                        reference = self.__references.get(new_fmri, None)
                        # don't leak prev. version info across publishers
                        if old_fmri:
                                if old_fmri.get_publisher() != \
                                    new_fmri.get_publisher():
                                        old_fmri = "unknown"
                                else:
                                        old_fmri = old_fmri.get_fmri(anarchy=True)
                        new_fmri = new_fmri.get_fmri(anarchy=True)# don't send pub
                else:
                        reference = self.__references.get(old_fmri, None)
                        # don't try to send intent info to disabled publisher
                        if old_fmri.get_publisher() in enabled_publishers:
                                old_fmri = old_fmri.get_fmri(anarchy=True)# don't send pub
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

        def evaluate(self, verbose=False):
                """Given already determined fmri changes, 
                build pkg plans and figure out exact impact of
                proposed changes"""

                assert self.state == EVALUATED_PKGS, self

                if self._image_lm != self.image.get_last_modified():
                        # State has been modified since plan was created; this
                        # plan is no longer valid.
                        raise api_errors.InvalidPlanError()

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
                self.__references = None

                self.image.transport.prefetch_manifests(prefetch_mfsts, 
                    progtrack=self.__progtrack,
                    ccancel=self.__check_cancelation)

                # No longer needed.
                del prefetch_mfsts

                for oldfmri, old_in, newfmri, new_in in eval_list:
                        pp = pkgplan.PkgPlan(self.image, self.__progtrack,
                            self.__check_cancelation)

                        pp.propose(oldfmri, self.__get_manifest(oldfmri, old_in),
                                   newfmri, self.__get_manifest(newfmri, new_in))

                        pp.evaluate(self.__old_excludes, self.__new_excludes)

                        if pp.origin_fmri and pp.destination_fmri:
                                self.__target_update_count += 1
                        elif pp.destination_fmri:
                                self.__target_install_count += 1
                        elif pp.origin_fmri:
                                self.__target_removal_count += 1

                        self.pkg_plans.append(pp)
                        pp = None
                        self.__progtrack.evaluate_progress()

                # No longer needed.
                del eval_list

                # we now have a workable set of pkgplans to add/upgrade/remove
                # now combine all actions together to create a synthetic single
                # step upgrade operation, and handle editable files moving from
                # package to package.  See theory comment in execute, below.

                ActionPlan = namedtuple("ActionPlan", "p src dst")

                self.removal_actions = []
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

                self.__actuators = actuator.Actuator()

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
                for i, ap in enumerate(self.removal_actions):
                        self.__progtrack.evaluate_progress()
                        # remove dir removals if dir is still in final image
                        if ap.src.name == "dir" and \
                            os.path.normpath(ap.src.attrs["path"]) in \
                            self.get_directories():
                                self.removal_actions[i] = None
                                continue
                        # remove link removal if link is still in final image
                        # (implement reference count on removal due to borked pkgs)
                        if ap.src.name == "link" and \
                            os.path.normpath(ap.src.attrs["path"]) in \
                            self.__get_symlinks():
                                self.removal_actions[i] = None
                                continue
                        # discard hardlink removal if hardlink is still in final
                        # image.
                        if ap.src.name == "hardlink" and \
                            os.path.normpath(ap.src.attrs["path"]) in \
                            self.__get_hardlinks():
                                self.removal_actions[i] = None
                                continue
                       
                        # store names of files being removed under own name
                        # or original name if specified
                        if ap.src.globally_unique:
                                attrs = ap.src.attrs
                                # Store the index into removal_actions and the
                                # id of the action object in that slot.
                                re = ConsolidationEntry(i, id(ap.src))
                                cons_generic[(ap.src.name, attrs[ap.src.key_attr])] = re
                                if ap.src.name == "file":
                                        fname = attrs.get("original_name",
                                            "%s:%s" % (ap.p.origin_fmri.get_name(),
                                            attrs["path"]))
                                        cons_named[fname] = re
                                        fname = None
                                attrs = re = None

                        self.__actuators.scan_removal(ap.src.attrs)

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
                pp_needs_trimming = []

                # This maps destination actions to the pkgplans they're
                # associated with, which allows us to create the newly
                # discovered update ActionPlans.
                dest_pkgplans = {}

                new_updates = []
                for i, ap in enumerate(self.install_actions):
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
                        keyval = ap.dst.attrs.get(ap.dst.key_attr, None)
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
                                        pp_needs_trimming.append(ap.p)
                                nkv = index = ra = None

                        self.__actuators.scan_install(ap.dst.attrs)

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
                nu_src.set_content((a[0] for a in new_updates),
                    excludes=self.__old_excludes)
                nu_dst = manifest.Manifest()
                self.__progtrack.evaluate_progress()
                nu_dst.set_content((a[1] for a in new_updates),
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

                self.removal_actions = [
                    a
                    for a in self.removal_actions
                    if a is not None
                ]

                self.install_actions = [
                    a
                    for a in self.install_actions
                    if a is not None
                ]

                self.__progtrack.evaluate_progress()
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
                self.state = EVALUATED_OK

        def nothingtodo(self):
                """ Test whether this image plan contains any work to do """

                # handle case w/ -n no verbose
                if self.state == EVALUATED_PKGS:
                        return not self.__fmri_changes
                elif self.state >= EVALUATED_OK:
                        return not self.pkg_plans

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
                # A key goal in IPS is to be able to undergo an arbtrary
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
                                    executed_pp)

                                # write out variant changes to the image config
                                if self.__variant_change:
                                        self.image.image_config_update(
                                            self.__new_variants,
                                            self.__new_facets)

                        except EnvironmentError, e:
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EPERM:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                elif e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
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
                self.__actuators     = []
                self.__cached_actions = {}
                self.__symlinks = None
                self.__hardlinks = None

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

        def match_user_fmris(self, patterns, all_known, pub_ranks, installed_pubs):
                """Given a user-specified list of patterns, return a dictionary
                of matching fmris:

                {pkgname: [fmri1, fmri2, ...]
                 pkgname: [fmri1, fmri2, ...],
                 ...
                }

                Constraint used is always AUTO as per expected UI behavior.
                If all_known is true, matching is done against all known package,
                otherwise just all installed pkgs.

                Note that patterns starting w/ pkg:/ require an exact match; patterns 
                containing '*' will using fnmatch rules; the default trailing match 
                rules are used for remaining patterns.

                Exactly duplicated patterns are ignored.

                Routine raises PlanCreationException if errors occur:
                it is illegal to specify multiple different pattens that match
                the same pkg name.  Only patterns that contain wildcards are allowed
                to match multiple packages.

                Fmri lists are trimmed by publisher, either by pattern specification,
                installed version or publisher ranking, in that order when all_known
                is True.
                """

                # problems we check for
                illegals      = []
                nonmatch      = []
                multimatch    = []
                not_installed = []
                multispec     = []
                wrongpub      = []

                matchers = []
                fmris    = []
                pubs     = []
                versions = []

                wildcard_patterns = []

                renamed_fmris = {}
                obsolete_fmris = []

                # ignore dups
                patterns = list(set(patterns))
                # print patterns, all_known, pub_ranks, installed_pubs

                # figure out which kind of matching rules to employ
                try:
                        for pat in patterns:
                                if "*" in pat or "?" in pat:
                                        matcher = pkg.fmri.glob_match
                                        fmri = pkg.fmri.MatchingPkgFmri(
                                                                pat, "5.11")
                                        wildcard_patterns.append(pat)
                                elif pat.startswith("pkg:/"):
                                        matcher = pkg.fmri.exact_name_match
                                        fmri = pkg.fmri.PkgFmri(pat,
                                                            "5.11")
                                else:
                                        matcher = pkg.fmri.fmri_match
                                        fmri = pkg.fmri.PkgFmri(pat,
                                                            "5.11")

                                matchers.append(matcher)
                                pubs.append(fmri.get_publisher())
                                versions.append(fmri.version)
                                fmris.append(fmri)

                except pkg.fmri.IllegalFmri, e:
                        illegals.append(e)
                
                # Create a dictionary of patterns, with each value being
                # a dictionary of pkg names & fmris that match that pattern.
                ret = dict(zip(patterns, [dict() for i in patterns]))

                # keep track of publishers we reject due to implict selection of
                # installed publisher to produce better error message.
                rejected_pubs = {}

                if all_known:
                        cat = self.image.get_catalog(self.image.IMG_CATALOG_KNOWN)
                        info_needed = [pkg.catalog.Catalog.DEPENDENCY]
                else:
                        cat = self.image.get_catalog(self.image.IMG_CATALOG_INSTALLED)
                        info_needed = []

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
                                                fpub = f.get_publisher()
                                                if pub and pub != fpub:
                                                        continue # specified pubs conflict
                                                elif not pub and all_known and \
                                                    name in installed_pubs and \
                                                    pub_ranks[installed_pubs[name]][1] \
                                                    == True and installed_pubs[name] != \
                                                    fpub:
                                                        rejected_pubs.setdefault(pat, 
                                                            set()).add(fpub)                                                            
                                                        continue # installed sticky pub
                                                ret[pat].setdefault(f.pkg_name, 
                                                    []).append(f)
                                                states = metadata["metadata"]["states"]
                                                if self.image.PKG_STATE_OBSOLETE in states:
                                                        obsolete_fmris.append(f)
                                                if self.image.PKG_STATE_RENAMED in states and \
                                                    "actions" in metadata:
                                                        renamed_fmris[f] = metadata["actions"]

                # remove multiple matches if all versions are obsolete
                for p in patterns:                
                        if len(ret[p]) > 1 and p not in wildcard_patterns:
                                # create dictionary of obsolete status vs pkg_name
                                obsolete = dict([                                        
                                        (pkg_name, reduce(operator.or_, 
                                        [f in obsolete_fmris for f in ret[p][pkg_name]]))
                                        for pkg_name in ret[p]
                                        ])
                                # remove all obsolete match if non-obsolete match also exists
                                if set([True, False]) == set(obsolete.values()):
                                        for pkg_name in obsolete:
                                                if obsolete[pkg_name]:
                                                        del ret[p][pkg_name]

                # remove newer multiple match if renamed version exists
                for p in patterns:                
                        if len(ret[p]) > 1 and p not in wildcard_patterns:
                                targets = []
                                renamed_matches = (
                                    pfmri
                                    for pkg_name in ret[p]
                                    for pfmri in ret[p][pkg_name]
                                    if pfmri in renamed_fmris
                                    )
                                for f in renamed_matches:
                                        for a in renamed_fmris[f]:
                                                a = pkg.actions.fromstr(a)
                                                if a.name != "depend":
                                                        continue
                                                if a.attrs["type"] != "require":
                                                        continue
                                                targets.append(pkg.fmri.PkgFmri(
                                                    a.attrs["fmri"], "5.11"
                                                    ).pkg_name)

                                for pkg_name in ret[p].keys():
                                        if pkg_name in targets:
                                                del ret[p][pkg_name]

                matchdict = {} 
                for p in patterns:
                        l = len(ret[p])
                        if l == 0: # no matches at all
                                if not all_known or p not in rejected_pubs:
                                        nonmatch.append(p)
                                elif p in rejected_pubs:
                                        wrongpub.append((p, rejected_pubs[p]))
                        elif l > 1 and p not in wildcard_patterns:  # multiple matches
                                multimatch.append((p, [n for n in ret[p]]))
                        else:      # single match or wildcard
                                for k in ret[p].keys(): # for each matching package name
                                        matchdict.setdefault(k, []).append(p)
                
                for name in matchdict:
                        if len(matchdict[name]) > 1: # different pats, same pkg
                                multispec.append(tuple([name] + matchdict[name]))

                if not all_known:
                        not_installed, nonmatch = nonmatch, not_installed
                        
                if illegals or nonmatch or multimatch or not_installed or \
                    multispec or wrongpub:
                        raise api_errors.PlanCreationException(unmatched_fmris=nonmatch,
                            multiple_matches=multimatch, illegal=illegals,
                            missing_matches=not_installed, multispec=multispec, wrong_publishers=wrongpub)
                # merge patterns together now that there are no conflicts
                proposed_dict = {}
                for d in ret.values():
                        proposed_dict.update(d)
                
                # eliminate lower ranked publishers

                if all_known: # no point for installed pkgs....
                        for pkg_name in proposed_dict:
                                pubs_found = set([
                                                f.get_publisher()
                                                for f in proposed_dict[pkg_name]
                                                ])
                                # 1000 is hack for installed but unconfigured publishers
                                best_pub = sorted([
                                                (pub_ranks.get(p, (1000, True))[0], p) 
                                                for p in pubs_found
                                                ])[0][1]

                                proposed_dict[pkg_name] = [
                                        f
                                        for f in proposed_dict[pkg_name]
                                        if f.get_publisher() == best_pub
                                        ]

                # construct references so that we can know which pattern
                # generated which fmris...

                references = dict([
                        (f, p)
                        for p in ret.keys()
                        for flist in ret[p].values()
                        for f in flist
                        ])
                
                return proposed_dict, references
