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

import time

import pkg.actions
import pkg.catalog           as catalog
import pkg.client.api_errors as api_errors
import pkg.client.image
import pkg.fmri
import pkg.misc as misc
import pkg.solver
import pkg.version           as version

from collections import defaultdict
from pkg.client.debugvalues import DebugValues
from pkg.misc import EmptyI, EmptyDict, N_

SOLVER_INIT    = "Initialized"
SOLVER_OXY     = "Not possible"
SOLVER_FAIL    = "Failed"
SOLVER_SUCCESS = "Succeeded"

class DependencyException(Exception):
        """local exception used to pass failure to match
        dependencies in packages out of nested evaluation"""

        def __init__(self, reason, fmris=EmptyI):
                Exception.__init__(self)
                self.__fmris = fmris
                self.__reason = reason
        @property
        def fmris(self):
                return self.__fmris
        @property
        def reason(self):
                return self.__reason


class PkgSolver(object):

        def __init__(self, cat, installed_dict, pub_ranks, variants, avoids,
            parent_pkgs, progtrack):
                """Create a PkgSolver instance; catalog should contain all
                known pkgs, installed fmris should be a dict of fmris indexed
                by name that define pkgs current installed in the image.
                Pub_ranks dict contains (rank, stickiness, enabled) for each
                publisher.  variants are the current image variants; avoids is
                the set of pkg stems being avoided in the image."""

                # check if we're allowed to use the solver
                if DebugValues["no_solver"]:
                        raise RuntimeError, "no_solver set, but solver invoked"

                self.__catalog = cat
                self.__publisher = {}		# indexed by stem
                self.__possible_dict = defaultdict(list) # indexed by stem
                self.__pub_ranks = pub_ranks    # rank indexed by pub
                self.__trim_dict = defaultdict(set) # fmris trimmed from
                                                # consideration


                self.__installed_dict = installed_dict.copy() # indexed by stem
                self.__installed_pkgs = frozenset(self.__installed_dict)
                self.__installed_fmris = frozenset(
                    self.__installed_dict.values())

                self.__pub_trim = {}		# pkg names already
                                                # trimmed by pub.
                self.__removal_fmris = set()    # installed fmris we're
                                                # going to remove

                self.__req_pkg_names = set()    # package names that must be
                                                # present in solution by spec.
                for f in self.__installed_fmris: # record only sticky pubs
                        pub = f.get_publisher()
                        if self.__pub_ranks[pub][1]:
                                self.__publisher[f.pkg_name] = f.get_publisher()

                self.__id2fmri = {} 		# map ids -> fmris
                self.__fmri2id = {} 		# and reverse

                self.__solver = pkg.solver.msat_solver()

                self.__poss_set = set()         # possible fmris after assign
                self.__progtrack = progtrack    # progress tracker

                self.__addclause_failure = False

                self.__variant_dict = {}        # fmris -> variant cache
                self.__variants = variants      # variants supported by image

                self.__cache = {}
                self.__trimdone = False         # indicate we're finished
                                                # trimming
                self.__fmri_state = {}          # cache of obsolete, renamed
                                                # bits so we can print something
                                                # reasonable
                self.__state = SOLVER_INIT
                self.__iterations = 0
                self.__clauses     = 0
                self.__variables   = 0
                self.__timings = []
                self.__start_time = 0
                self.__dep_dict = {}
                self.__inc_list = []
                self.__dependents = None
                self.__root_fmris = None        # set of fmris installed in root image;
                                                # used for origin dependencies
                self.__avoid_set = avoids.copy()# set of stems we're avoiding
                self.__obs_set = None           #
                self.__reject_set = set()       # set of stems we're rejecting

                assert isinstance(parent_pkgs, (type(None), frozenset))
                self.__parent_pkgs = parent_pkgs
                self.__parent_dict = dict()
                if self.__parent_pkgs != None:
                        self.__parent_dict = dict([
                            (f.pkg_name, f)
                            for f in self.__parent_pkgs
                        ])

        def __str__(self):

                s = "Solver: ["
                if self.__state in [SOLVER_FAIL, SOLVER_SUCCESS]:
                        s += " Variables: %d Clauses: %d Iterations: %d" % (
                            self.__variables, self.__clauses, self.__iterations)
                s += " State: %s]" % self.__state

                s += "\nTimings: ["
                s += ", ".join(["%s: %6.3f" % a for a in self.__timings])
                s += "]"

                if self.__inc_list:

                        incs = "\n\t".join([str(a) for a in self.__inc_list])
                else:
                        incs = "None"

                s += "\nMaintained incorporations: %s\n" % incs

                return s

        def __cleanup(self, rval):
                """Discards all solver information except for that needed to
                show failure information or to stringify the solver object.
                This allows early garbage collection to take place, and should
                be performed after a solution is successfully returned."""

                self.__catalog = None
                self.__installed_dict = {}
                self.__installed_pkgs = frozenset()
                self.__installed_fmris = frozenset()
                self.__publisher = {}
                self.__possible_dict = {}
                self.__pub_ranks = None
                self.__pub_trim = {}
                self.__removal_fmris = set()
                self.__id2fmri = None
                self.__fmri2id = None
                self.__solver = None
                self.__poss_set = None
                self.__progtrack = None
                self.__addclause_failure = False
                self.__variant_dict = None
                self.__variants = None
                self.__cache = None
                self.__trimdone = None
                self.__fmri_state = None
                self.__start_time = None
                self.__dep_dict = None
                self.__dependents = None

                if DebugValues["plan"]:
                        # Remaining data must be kept.
                        return rval

                self.__trim_dict = None
                return rval

        def __timeit(self, phase=None):
                """Add timing records; set phase to None to reset"""
                if phase == None:
                        self.__start_time = time.time()
                        self.__timings = []
                else:
                        now = time.time()
                        self.__timings.append((phase, now - self.__start_time))
                        self.__start_time = now

        def solve_install(self, existing_freezes, proposed_dict,
            new_variants=None, new_facets=None, excludes=EmptyI,
            reject_set=frozenset(), trim_proposed_installed=True,
            relax_all=False):
                """Logic to install packages, change variants, and/or change
                facets.

                Returns FMRIs to be installed / upgraded in system and a new
                set of packages to be avoided.

                'existing_freezes' is a list of incorp. style FMRIs that
                constrain package motion.

                'proposed_dict' contains user specified FMRIs indexed by
                pkg_name that should be installed within an image.

                'new_variants' a dictionary containing variants which are
                being updated.  (It should not contain existing variants which
                are not changing.)

                'new_facets' a dictionary containing all the facets for an
                image.  (This includes facets which are changing and also
                facets which are not.)

                'reject_set' contains user specified package names that should
                not be present within the final image.  (These packages may or
                may not be currently installed.)

                'trim_proposed_installed' is a boolean indicating whether the
                solver should elide versions of proposed packages older than
                those installed from the set of possible solutions.  If False,
                package downgrades are allowed, but only for installed
                packages matching those in the proposed_dict.

                'relax_all' indicates if the solver should relax all install
                holds, or only install holds specified by proposed packages.
                """

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT
                self.__state = SOLVER_OXY

                proposed_pkgs = set(proposed_dict)

                self.__progtrack.evaluate_progress()
                self.__timeit()

                if new_variants:
                        self.__variants = new_variants

                        #
                        # Entire packages can be tagged with variants thereby
                        # making those packages uninstallable in certain
                        # images.  So if we're changing variants such that
                        # some currently installed packages are becomming
                        # uninstallable add them to the removal package set.
                        #
                        for f in self.__installed_fmris:
                                d = self.__get_variant_dict(f)
                                for k in new_variants:
                                        if k in d and \
                                            new_variants[k] not in d[k]:
                                                self.__removal_fmris |= set([f])

                # proposed_dict already contains publisher selection logic,
                # so prevent any further trimming of named packages based
                # on publisher if they are installed.
                for name in proposed_dict:
                        if name in self.__installed_dict:
                                self.__mark_pub_trimmed(name)
                        else:
                                self.__publisher[name] = \
                                    proposed_dict[name][0].get_publisher()

                self.__removal_fmris |= set([
                    self.__installed_dict[name]
                    for name in reject_set
                    if name in self.__installed_dict
                ])

                # remove packages to be installed from avoid_set
                self.__avoid_set -= proposed_pkgs
                self.__reject_set = reject_set

                # trim fmris that user explicitly disallowed
                for name in reject_set:
                        self.__trim(self.__get_catalog_fmris(name),
                            N_("This version rejected by user request"))

                self.__req_pkg_names = (self.__installed_pkgs |
                    proposed_pkgs) - reject_set

                self.__progtrack.evaluate_progress()

                # find list of incorps we don't let change as a side
                # effect of other changes; exclude any specified on
                # command line
                # translate proposed_dict into a set
                if relax_all:
                        relax_pkgs = self.__installed_pkgs
                else:
                        relax_pkgs = proposed_pkgs

                inc_list, con_lists = self.__get_installed_unbound_inc_list(
                    relax_pkgs, excludes=excludes)

                self.__inc_list = inc_list
                self.__progtrack.evaluate_progress()

                # If requested, trim any proposed fmris older than those of
                # corresponding installed packages.
                self.__timeit("phase 1")
                for f in self.__installed_fmris - self.__removal_fmris:
                        if not trim_proposed_installed and \
                            f.pkg_name in proposed_dict:
                                # Don't trim versions if newest version in
                                # proposed dict is older than installed
                                # version.
                                verlist = proposed_dict[f.pkg_name]
                                if verlist[-1].version < f.version:
                                        # Assume downgrade is intentional.
                                        continue
                        self.__trim_older(f)

                self.__progtrack.evaluate_progress()

                # trim fmris we excluded via proposed_fmris
                for name in proposed_dict:
                        self.__trim(set(self.__get_catalog_fmris(name)) -
                            set(proposed_dict[name]),
                            N_("This version excluded by specified installation version"))
                        # trim packages excluded by incorps in proposed.
                        self.__trim_recursive_incorps(proposed_dict[name], excludes)
                self.__timeit("phase 2")
                self.__progtrack.evaluate_progress()

                # now trim pkgs we cannot update due to maintained
                # incorporations
                for i, flist in zip(inc_list, con_lists):
                        reason = (N_("This version is excluded by installed "
                            "incorporation {0}"), (i,))
                        self.__trim(self.__comb_auto_fmris(i)[1], reason)
                        for f in flist:
                                self.__trim(self.__comb_auto_fmris(f)[1],
                                    reason)

                self.__timeit("phase 3")
                self.__progtrack.evaluate_progress()

                # now trim any pkgs we cannot update due to freezes
                for f, r, t in existing_freezes:
                        if r:
                                reason = (N_("This version is excluded by a "
                                    "freeze on {0} at version {1}.  The "
                                    "reason for the freeze is: {2}"),
                                    (f.pkg_name, f.version, r))
                        else:
                                reason = (N_("This version is excluded by a "
                                    "freeze on {0} at version {1}."),
                                    (f.pkg_name, f.version))
                        self.__trim(self.__comb_auto_fmris(f, dotrim=False)[1],
                            reason)

                self.__progtrack.evaluate_progress()

                # elide any proposed versions that don't match variants (arch
                # usually)
                self.__timeit("phase 4")
                for name in proposed_dict:
                        for fmri in proposed_dict[name]:
                                self.__trim_nonmatching_variants(fmri)

                # remove any versions from proposed_dict that are in trim_dict
                self.__timeit("phase 5")
                ret = []
                for name in proposed_dict:
                        tv = self.__dotrim(proposed_dict[name])
                        if tv:
                                proposed_dict[name] = tv
                                continue

                        ret.extend([_("No matching version of %s can be "
                            "installed:") % name])
                        ret.extend(self.__fmri_list_errors(proposed_dict[name]))
                        # continue processing and accumulate all errors

                if ret:
                        solver_errors = None
                        if DebugValues["plan"]:
                                solver_errors = self.get_trim_errors()
                        raise api_errors.PlanCreationException(
                            no_version=ret, solver_errors=solver_errors)

                self.__progtrack.evaluate_progress()

                # build set of possible pkgs
                self.__timeit("phase 6")

                # generate set of possible fmris
                #
                # ensure existing pkgs stay installed; explicitly add in
                # installed fmris in case publisher change has occurred and
                # some pkgs aren't part of new publisher
                possible_set = set()
                for f in self.__installed_fmris - self.__removal_fmris:
                        possible_set |= self.__comb_newer_fmris(f)[0] | set([f])

                # add the proposed fmris
                for flist in proposed_dict.values():
                        possible_set.update(flist)

                self.__timeit("phase 7")
                possible_set.update(self.__generate_dependency_closure(
                    possible_set, excludes=excludes))

                # remove any possibles that must be excluded because of
                # origin and parent dependencies
                for f in possible_set.copy():
                        if not self.__trim_nonmatching_origins(f, excludes):
                                possible_set.remove(f)
                        elif not self.__trim_nonmatching_parents(f, excludes):
                                possible_set.remove(f)

                # remove any versions from proposed_dict that are in trim_dict
                # as trim dict has been updated w/ missing dependencies
                self.__timeit("phase 8")
                ret = []
                for name in proposed_dict:
                        tv = self.__dotrim(proposed_dict[name])
                        if tv:
                                proposed_dict[name] = tv
                                continue

                        ret.extend([_("No matching version of %s can be "
                            "installed:") % name])
                        ret.extend(self.__fmri_list_errors(proposed_dict[name]))
                        # continue processing and accumulate all errors
                if ret:
                        solver_errors = None
                        if DebugValues["plan"]:
                                solver_errors = self.get_trim_errors()
                        raise api_errors.PlanCreationException(
                            no_version=ret, solver_errors=solver_errors)

                self.__timeit("phase 9")
                self.__progtrack.evaluate_progress()

                # generate ids, possible_dict for clause generation
                self.__assign_fmri_ids(possible_set)

                # generate clauses for only one version of each package, and for
                # dependencies for each package.  Do so for all possible fmris.

                for name in self.__possible_dict:
                        self.__progtrack.evaluate_progress()
                        # Ensure only one version of a package is installed
                        self.__addclauses(self.__gen_highlander_clauses(
                            self.__possible_dict[name]))
                        # generate dependency clauses for each pkg
                        for fmri in self.__possible_dict[name]:
                                for da in self.__get_dependency_actions(fmri,
                                    excludes=excludes):
                                        self.__addclauses(
                                            self.__gen_dependency_clauses(fmri,
                                            da))

                self.__timeit("phase 10")

                # generate clauses for proposed and installed pkgs
                # note that we create clauses that require one of the
                # proposed pkgs to work; this allows the possible_set
                # to always contain the existing pkgs

                for name in proposed_dict:
                        self.__progtrack.evaluate_progress()
                        self.__addclauses(
                            self.__gen_one_of_these_clauses(
                                set(proposed_dict[name]) &
                                set(self.__possible_dict[name])))

                ret = []
                for name in self.__installed_pkgs - proposed_pkgs - \
                    reject_set - self.__avoid_set:
                        if (self.__installed_dict[name] in
                            self.__removal_fmris):
                                continue

                        if name in self.__possible_dict:
                                self.__progtrack.evaluate_progress()
                                self.__addclauses(
                                    self.__gen_one_of_these_clauses(
                                        self.__possible_dict[name]))
                                continue

                        # no version of this package is allowed
                        ret.extend([_("The installed package %s is not "
                            "permissible.") % name])
                        ret.extend(self.__fmri_list_errors(
                            [self.__installed_dict[name]]))
                        # continue processing and accumulate all errors
                if ret:
                        solver_errors = None
                        if DebugValues["plan"]:
                                solver_errors = self.get_trim_errors()
                        raise api_errors.PlanCreationException(
                            no_version=ret, solver_errors=solver_errors)

                # save a solver instance so we can come back here
                # this is where errors happen...
                saved_solver = self.__save_solver()
                try:
                        saved_solution = self.__solve()
                except api_errors.PlanCreationException, exp:
                        # no solution can be found.
                        # make sure all package trims appear
                        self.__trimdone = False

                        info = []
                        incs = []

                        if inc_list:
                                incs.append("")
                                incs.append("maintained incorporations:")
                                incs.append("")
                                for il in inc_list:
                                        incs.append("  %s" % il)
                        else:
                                incs.append("")
                                incs.append("maintained incorporations: None")
                                incs.append("")

                        ms = self.__generate_dependency_errors(
                            [ b for a in proposed_dict.values() for b in a ],
                            excludes=excludes)

                        if ms:
                                info.append("")
                                info.append(_("Plan Creation: dependency error(s) in proposed packages:"))
                                info.append("")
                                for s in ms:
                                        info.append("  %s" % s)
                        ms = self.__check_installed()

                        if ms:
                                info.append("")
                                info.append(_("Plan Creation: Errors in installed packages due to proposed changes:"))
                                info.append("")
                                for s in ms:
                                        info.append("  %s" % s)
                        if not info: # both error detection methods insufficent.
                                info.append(_("Plan Creation: Package solver is unable to compute solution."))
                                info.append(_("Dependency analysis is unable to determine exact cause."))
                                info.append(_("Try specifying expected results to obtain more detailed error messages."))
                                info.append(_("Include specific version of packages you wish installed."))
                        exp.no_solution = incs + info

                        solver_errors = None
                        if DebugValues["plan"]:
                                exp.solver_errors = self.get_trim_errors()
                        raise exp

                self.__timeit("phase 11")

                # we have a solution that works... attempt to
                # reduce collateral damage to other packages
                # while still keeping command line pkgs at their
                # optimum level

                self.__restore_solver(saved_solver)

                # fix the fmris that were specified on the cmd line
                # at their optimum (newest) level along with the
                # new dependencies, but try and avoid upgrading
                # already installed pkgs or adding un-needed new pkgs.

                for fmri in saved_solution:
                        if fmri.pkg_name in proposed_dict:
                                self.__addclauses(
                                    self.__gen_one_of_these_clauses([fmri]))

                # save context
                saved_solver = self.__save_solver()

                saved_solution = self.__solve(older=True)
                # Now we have the oldest possible original fmris
                # but we may have some that are not original
                # Since we want to move as far forward as possible
                # when we have to move a package, fix the originals
                # and drive forward again w/ the remainder
                self.__restore_solver(saved_solver)

                for fmri in (saved_solution & self.__installed_fmris):
                        self.__addclauses(
                            self.__gen_one_of_these_clauses([fmri]))

                solution = self.__solve()

                solution = self.__update_solution_set(solution, excludes)

                self.__timeit("phase 12")
                return self.__cleanup((self.__elide_possible_renames(solution,
                    excludes), (self.__avoid_set, self.__obs_set)))

        def solve_update_all(self, existing_freezes, excludes=EmptyI,
            reject_set=frozenset()):
                """Logic to update all packages within an image to the latest
                versions possible.

                Returns FMRIs to be installed / upgraded in system and a new
                set of packages to be avoided.

                'existing_freezes' is a list of incorp. style FMRIs that
                constrain pkg motion

                'reject_set' contains user specified FMRIs that should not be
                present within the final image.  (These packages may or may
                not be currently installed.)
                """

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT
                self.__state = SOLVER_OXY

                self.__progtrack.evaluate_progress()
                self.__timeit()

                self.__removal_fmris = frozenset([
                    self.__installed_dict[name]
                    for name in reject_set
                    if name in self.__installed_dict
                ])
                self.__reject_set = reject_set

                # trim fmris that user explicitly disallowed
                for name in reject_set:
                        self.__trim(self.__get_catalog_fmris(name),
                            N_("This version rejected by user request"))

                self.__req_pkg_names = self.__installed_pkgs - reject_set

                # trim fmris we cannot install because they're older
                for f in self.__installed_fmris:
                        self.__trim_older(f)

                # now trim any pkgs we cannot update due to freezes
                for f, r, t in existing_freezes:
                        if r:
                                reason = (N_("This version is excluded by a "
                                    "freeze on {0} at version {1}.  The "
                                    "reason for the freeze is: {2}"),
                                    (f.pkg_name, f.version, r))
                        else:
                                reason = (N_("This version is excluded by a "
                                    "freeze on {0} at version {1}."),
                                    (f.pkg_name, f.version))
                        self.__trim(self.__comb_auto_fmris(f, dotrim=False)[1],
                            reason)

                self.__progtrack.evaluate_progress()

                self.__timeit("phase 1")

                # generate set of possible fmris
                possible_set = set()
                for f in self.__installed_fmris - self.__removal_fmris:
                        matching = self.__comb_newer_fmris(f)[0]
                        if not matching:            # disabled publisher...
                                matching = set([f]) # staying put is an option
                        possible_set |= matching

                self.__timeit("phase 2")

                possible_set.update(self.__generate_dependency_closure(
                    possible_set, excludes=excludes))

                # remove any possibles that must be excluded because of
                # origin and parent dependencies
                for f in possible_set.copy():
                        if not self.__trim_nonmatching_origins(f, excludes):
                                possible_set.remove(f)
                        elif not self.__trim_nonmatching_parents(f, excludes):
                                possible_set.remove(f)

                self.__timeit("phase 3")

                # generate ids, possible_dict for clause generation
                self.__assign_fmri_ids(possible_set)

                # generate clauses for only one version of each package, and for
                # dependencies for each package.  Do so for all possible fmris.

                for name in self.__possible_dict:
                        # Ensure only one version of a package is installed
                        self.__addclauses(self.__gen_highlander_clauses(
                            self.__possible_dict[name]))
                        # generate dependency clauses for each pkg
                        for fmri in self.__possible_dict[name]:
                                for da in self.__get_dependency_actions(fmri,
                                    excludes=excludes):
                                        self.__addclauses(
                                            self.__gen_dependency_clauses(fmri,
                                                da))
                self.__timeit("phase 4")

                # generate clauses for installed pkgs
                ret = []
                for name in self.__installed_pkgs - self.__avoid_set:
                        if (self.__installed_dict[name] in
                            self.__removal_fmris):
                                # we're uninstalling this package
                                continue

                        if name in self.__possible_dict:
                                self.__progtrack.evaluate_progress()
                                self.__addclauses(
                                    self.__gen_one_of_these_clauses(
                                    self.__possible_dict[name]))
                                continue

                        # no version of this package is allowed
                        ret.extend([_("The installed package %s is not "
                            "permissible.") % name])
                        ret.extend(self.__fmri_list_errors(
                            [self.__installed_dict[name]]))
                        # continue processing and accumulate all errors
                if ret:
                        solver_errors = None
                        if DebugValues["plan"]:
                                solver_errors = self.get_trim_errors()
                        raise api_errors.PlanCreationException(
                            no_version=ret, solver_errors=solver_errors)

                self.__timeit("phase 5")

                solution = self.__solve()

                self.__update_solution_set(solution, excludes)

                for f in solution.copy():
                        if self.__fmri_is_obsolete(f):
                                solution.remove(f)

                # check if we cannot upgrade (heuristic)
                if solution == self.__installed_fmris:
                        # no solution can be found.
                        incorps = self.__get_installed_upgradeable_incorps(excludes)
                        if incorps:
                                info = []
                                info.append(_("Plan Creation: Package solver has not found a solution to update to latest available versions."))
                                info.append(_("This may indicate an overly constrained set of packages are installed."))
                                info.append(" ")
                                info.append(_("latest incorporations:"))
                                info.append(" ")
                                info.extend(("  %s" % f for f in incorps))
                                ms = self.__generate_dependency_errors(incorps,
                                    excludes=excludes)
                                ms.extend(self.__check_installed())

                                if ms:
                                        info.append(" ")
                                        info.append(_("The following indicates why the system cannot update to the latest version:"))
                                        info.append(" ")
                                        for s in ms:
                                                info.append("  %s" % s)
                                else:
                                        info.append(_("Dependency analysis is unable to determine exact cause."))
                                        info.append(_("Try specifying expected results to obtain more detailed error messages."))

                                solver_errors = None
                                if DebugValues["plan"]:
                                        solver_errors = self.get_trim_errors()
                                raise api_errors.PlanCreationException(
                                    no_solution=info,
                                    solver_errors=solver_errors)

                return self.__cleanup((self.__elide_possible_renames(solution,
                    excludes), (self.__avoid_set, self.__obs_set)))

        def solve_uninstall(self, existing_freezes, uninstall_list, excludes):
                """Compute changes needed for uninstall"""

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT

                # generate list of installed pkgs w/ possible renames removed to
                # forestall failing removal due to presence of unneeded renamed
                # pkg

                orig_installed_set = self.__installed_fmris
                renamed_set = orig_installed_set - \
                    self.__elide_possible_renames(orig_installed_set, excludes)

                proposed_removals = set(uninstall_list) | renamed_set

                # check for dependents
                for pfmri in proposed_removals:
                        dependents = self.__get_dependents(pfmri, excludes) - \
                            proposed_removals
                        if dependents:
                                raise api_errors.NonLeafPackageException(pfmri,
                                    dependents)

                reject_set = set(f.pkg_name for f in proposed_removals)
                # Run it through the solver; w/ more complex dependencies we're
                # going to be out of luck w/o it.

                return self.solve_install(existing_freezes, {},
                    excludes=excludes, reject_set=reject_set)

        def __update_solution_set(self, solution, excludes):
                """Update avoid set w/ any missing packages (due to reject).
                Remove obsolete packages from solution.
                Keep track of which obsolete packages have group
                dependencies so verify of group packages w/ obsolete
                members works."""

                solution_stems = set(f.pkg_name for f in solution)
                tracked_stems = set([
                    pkg.fmri.PkgFmri(a.attrs["fmri"], "5.11").pkg_name
                    for fmri in solution
                    for a in self.__get_dependency_actions(fmri, excludes=excludes,
                        trim_invalid=False)
                    if a.attrs["type"] == "group"
                ])

                self.__avoid_set |= (tracked_stems - solution_stems)

                ret = solution.copy()
                obs = set()

                for f in solution:
                        if self.__fmri_is_obsolete(f):
                                ret.remove(f)
                                obs.add(f.pkg_name)


                self.__obs_set = obs & tracked_stems

                return ret

        def __save_solver(self):
                """Create a saved copy of the current solver state and return it"""
                return (self.__addclause_failure,
                        pkg.solver.msat_solver(self.__solver))

        def __restore_solver(self, solver):
                """Set the current solver state to the previously saved one"""

                self.__addclause_failure, self.__solver = solver
                self.__iterations = 0

        def __solve(self, older=False, max_iterations=2000):
                """Perform iterative solution; try for newest pkgs unless
                older=True"""
                solution_vector = []
                self.__state = SOLVER_FAIL
                eliminated = set()
                while not self.__addclause_failure and self.__solver.solve([]):
                        self.__iterations += 1

                        if self.__iterations > max_iterations:
                                break

                        solution_vector = self.__get_solution_vector()
                        if not solution_vector:
                                break

                        # prevent the selection of any older pkgs
                        for fid in solution_vector:
                                pfmri = self.__getfmri(fid)
                                matching, remaining = \
                                    self.__comb_newer_fmris(pfmri)
                                if not older:
                                        remove = remaining
                                else:
                                        remove = matching - set([pfmri]) - \
                                            eliminated
                                for f in remove:
                                        self.__addclauses([[-self.__getid(f)]])


                        # prevent the selection of this exact combo;
                        # permit [] solution
                        self.__addclauses([[-i for i in solution_vector]])

                if not self.__iterations:
                        solver_errors = None
                        if DebugValues["plan"]:
                                solver_errors = self.get_trim_errors()
                        raise api_errors.PlanCreationException(no_solution=True,
                            solver_errors=solver_errors)

                self.__state = SOLVER_SUCCESS

                solution = set([self.__getfmri(i) for i in solution_vector])

                return solution

        def __get_solution_vector(self):
                """Return solution vector from solver"""
                return frozenset([
                    (i + 1) for i in range(self.__solver.get_variables())
                    if self.__solver.dereference(i)
                ])

        def __assign_fmri_ids(self, possible_set):
                """ give a set of possible fmris, assign ids"""

                # generate dictionary of possible pkgs fmris by pkg stem

                self.__possible_dict.clear()
                self.__poss_set |= possible_set

                for f in possible_set:
                        self.__possible_dict[f.pkg_name].append(f)
                for name in self.__possible_dict:
                        self.__possible_dict[name].sort()
                # assign clause numbers (ids) to possible pkgs
                pkgid = 1
                for name in sorted(self.__possible_dict.keys()):
                        for fmri in reversed(self.__possible_dict[name]):
                                self.__id2fmri[pkgid] = fmri
                                self.__fmri2id[fmri] = pkgid
                                pkgid += 1

                self.__variables = pkgid - 1
                self.__trimdone = True

        def __getid(self, fmri):
                """Translate fmri to variable number (id)"""
                return self.__fmri2id[fmri]

        def __getfmri(self, fid):
                """Translate variable number (id) to fmris"""
                return self.__id2fmri[fid]

        def __get_fmris_by_version(self, pkg_name):
                """Cache for catalog entries; helps performance"""
                if pkg_name not in self.__cache:
                        self.__cache[pkg_name] = \
                            [t for t in self.__catalog.fmris_by_version(pkg_name)]
                return self.__cache[pkg_name]

        def __get_catalog_fmris(self, pkg_name):
                """ return the list of fmris in catalog for this pkg name"""
                if pkg_name not in self.__pub_trim:
                        self.__filter_publishers(pkg_name)

                if self.__trimdone:
                        return self.__possible_dict.get(pkg_name, [])
                else:
                        return [
                                f
                                for tp in self.__get_fmris_by_version(pkg_name)
                                for f in tp[1]
                                ]

        def __comb_newer_fmris(self, fmri, dotrim=True, obsolete_ok=True):
                """Returns tuple of set of fmris that are matched within
                CONSTRAINT.NONE of specified version and set of remaining
                fmris."""
                return self.__comb_common(fmri, dotrim,
                    version.CONSTRAINT_NONE, obsolete_ok)

        def __comb_common(self, fmri, dotrim, constraint, obsolete_ok):
                """Underlying impl. of other comb routines"""
                tp = (fmri, dotrim, constraint, obsolete_ok) # cache index
                # determine if the data is cacheable or cached:
                if (not self.__trimdone and dotrim) or tp not in self.__cache:

                        # use frozensets so callers don't inadvertently update
                        # these sets (which may be cached).
                        all_fmris = set(self.__get_catalog_fmris(fmri.pkg_name))
                        matching = frozenset([
                            f
                            for f in all_fmris
                            if f not in self.__trim_dict or not dotrim
                            if not fmri.version or
                                fmri.version == f.version or
                                f.version.is_successor(fmri.version,
                                    constraint=constraint)
                            if obsolete_ok or not self.__fmri_is_obsolete(f)
                        ])
                        remaining = frozenset(all_fmris - matching)

                        # if we haven't finished trimming, don't cache this
                        if not self.__trimdone:
                                return matching, remaining
                        # cache the result
                        self.__cache[tp] = (matching, remaining)

                return self.__cache[tp]

        def __comb_older_fmris(self, fmri, dotrim=True, obsolete_ok=True):
                """Returns tuple of set of fmris that are older than
                specified version and set of remaining fmris."""
                newer, older = self.__comb_newer_fmris(fmri, dotrim=False,
                    obsolete_ok=obsolete_ok)
                if not dotrim:
                        return older, newer
                else:
                        # we're going to return the older packages, so we need
                        # to make sure that any trimmed packages are removed
                        # from the matching set and added to the nom-matching
                        # ones.
                        trimmed_older = set([
                                f
                                for f in older
                                if f in self.__trim_dict
                                ])
                        return older - trimmed_older, newer | trimmed_older

        def __comb_auto_fmris(self, fmri, dotrim=True, obsolete_ok=True):
                """Returns tuple of set of fmris that are match within
                CONSTRAINT.AUTO of specified version and set of remaining fmris."""
                return self.__comb_common(fmri, dotrim, version.CONSTRAINT_AUTO, obsolete_ok)

        def __fmri_loadstate(self, fmri, excludes):
                """load fmri state (obsolete == True, renamed == True)"""

                try:
                        relevant = dict([
                                (a.attrs["name"], a.attrs["value"])
                                for a in self.__catalog.get_entry_actions(fmri,
                                [catalog.Catalog.DEPENDENCY], excludes=excludes)
                                if a.name == "set" and \
                                    a.attrs["name"] in ["pkg.renamed",
                                    "pkg.obsolete"]
                                ])
                except api_errors.InvalidPackageErrors:
                        # Trim package entries that have unparseable action data
                        # so that they can be filtered out later.
                        self.__fmri_state[fmri] = ("false", "false")
                        self.__trim(fmri, N_("Package contains invalid or unsupported actions"))
                        return

                self.__fmri_state[fmri] = (
                    relevant.get("pkg.obsolete", "false").lower() == "true",
                    relevant.get("pkg.renamed", "false").lower() == "true")

        def __fmri_is_obsolete(self, fmri, excludes=EmptyI):
                """check to see if fmri is obsolete"""
                if fmri not in self.__fmri_state:
                        self.__fmri_loadstate(fmri, excludes)
                return self.__fmri_state[fmri][0]

        def __fmri_is_renamed(self, fmri, excludes=EmptyI):
                """check to see if fmri is renamed"""
                if fmri not in self.__fmri_state:
                        self.__fmri_loadstate(fmri, excludes)
                return self.__fmri_state[fmri][1]

        def __get_dependency_actions(self, fmri, excludes=EmptyI,
            trim_invalid=True):
                """Return list of all dependency actions for this fmri"""

                try:
                        return [
                            a
                            for a in self.__catalog.get_entry_actions(fmri,
                            [catalog.Catalog.DEPENDENCY], excludes=excludes)
                            if a.name == "depend"
                        ]

                except api_errors.InvalidPackageErrors:
                        if trim_invalid:
                                # Trim package entries that have unparseable
                                # action data so that they can be filtered out
                                # later.
                                self.__fmri_state[fmri] = ("false", "false")
                                self.__trim(fmri, N_("Package contains invalid "
                                    "or unsupported actions"))
                                return []
                        else:
                                raise

        def __get_variant_dict(self, fmri):
                """Return dictionary of variants suppported by fmri"""
                try:
                        if fmri not in self.__variant_dict:
                                self.__variant_dict[fmri] = dict(
                                    self.__catalog.get_entry_all_variants(fmri))
                except api_errors.InvalidPackageErrors:
                        # Trim package entries that have unparseable action data
                        # so that they can be filtered out later.
                        self.__variant_dict[fmri] = {}
                        self.__trim(fmri, N_("Package contains invalid or unsupported actions"))
                return self.__variant_dict[fmri]

        def __generate_dependency_closure(self, fmri_set, excludes=EmptyI,
            dotrim=True):
                """return set of all fmris the set of specified fmris could
                depend on; while trimming those packages that cannot be
                installed"""

                needs_processing = fmri_set
                already_processed = set()

                while (needs_processing):
                        fmri = needs_processing.pop()
                        self.__progtrack.evaluate_progress()
                        already_processed.add(fmri)
                        needs_processing |= (self.__generate_dependencies(fmri,
                            excludes, dotrim) - already_processed)
                return already_processed

        def __generate_dependencies(self, fmri, excludes=EmptyI, dotrim=True):
                """return set of direct (possible) dependencies of this pkg;
                trim those packages whose dependencies cannot be satisfied"""
                try:
                        return set([
                             f
                             for da in self.__get_dependency_actions(fmri,
                                 excludes)
                             if da.attrs["type"] != "incorporate" and
                                 da.attrs["type"] != "optional" and
                                 da.attrs["type"] != "exclude" and
                                 da.attrs["type"] != "parent"
                             for f in self.__parse_dependency(da, fmri,
                                 dotrim, check_req=True)[1]
                        ])

                except DependencyException, e:
                        self.__trim(fmri, e.reason, e.fmris)
                        return set([])

        def __elide_possible_renames(self, fmris, excludes=EmptyI):
                """Return fmri list (which must be self-complete) with all
                renamed fmris that have no other fmris depending on them
                removed"""

                # figure out which have been renamed
                renamed_fmris = set([
                    pfmri
                    for pfmri in fmris
                    if self.__fmri_is_renamed(pfmri, excludes)
                ])

                # return if nothing has been renamed
                if not renamed_fmris:
                        return set(fmris)

                fmris_by_name = dict(((pfmri.pkg_name, pfmri) for pfmri in fmris))

                # figure out which renamed fmris have dependencies; compute transitively
                # so we can handle multiple renames

                needs_processing = set(fmris) - renamed_fmris
                already_processed = set()

                while needs_processing:
                        pfmri = needs_processing.pop()
                        already_processed.add(pfmri)
                        for da in self.__get_dependency_actions(pfmri, excludes):
                                if da.attrs["type"] not in ["incorporate", "optional", "origin"]:
                                        for f in da.attrlist("fmri"):
                                                name = pkg.fmri.PkgFmri(f, "5.11").pkg_name
                                                if name not in fmris_by_name:
                                                        continue
                                                new_fmri = fmris_by_name[name]
                                                # since new_fmri will not be treated as renamed, make sure
                                                # we check any dependencies it has
                                                if new_fmri not in already_processed:
                                                        needs_processing.add(new_fmri)
                                                renamed_fmris.discard(new_fmri)
                return set(fmris) - renamed_fmris


        def __get_dependents(self, pfmri, excludes=EmptyI):
                """return set of installed fmris that have require dependencies
                on specified installed fmri"""
                if self.__dependents is None:
                        self.__dependents = {}
                        for f in self.__installed_fmris:
                                for da in self.__get_dependency_actions(f,
                                    excludes):
                                        if da.attrs["type"] != "require":
                                                continue
                                        pkg_name = pkg.fmri.PkgFmri(
                                            da.attrs["fmri"], "5.11").pkg_name
                                        self.__dependents.setdefault(
                                            self.__installed_dict[pkg_name],
                                            set()).add(f)
                return self.__dependents.get(pfmri, set())

        def __trim_recursive_incorps(self, fmri_list, excludes):
                """trim packages affected by incorporations"""
                processed = set()

                work = [fmri_list]

                while work:
                        fmris = work.pop()
                        processed.add(frozenset(fmris))
                        d = self.__combine_incorps(fmris, excludes)
                        for name in d:
                                self.__trim(d[name][1],
                                    (N_("Excluded by proposed incorporation '{0}'"), (fmris[0].pkg_name,)))
                                to_do = d[name][0]
                                if to_do and frozenset(to_do) not in processed:
                                        work.append(list(to_do))

        def __combine_incorps(self, fmri_list, excludes):
                """Given a list of fmris, one of which must be present, produce
                a dictionary indexed by package name, which contains a tuple
                of two sets (matching fmris, nonmatching)"""

                dict_list = [
                    self.__get_incorp_nonmatch_dict(f, excludes)
                    for f in fmri_list
                ]
                # The following ignores constraints that appear in only some of
                # the versions.  This also handles obsoletions & renames.
                all_keys = reduce(set.intersection, (set(d.keys()) for d in dict_list))

                return dict(
                        (k,
                         (reduce(set.union,
                                 (d.get(k, (set(), set()))[0]
                                  for d in dict_list)),
                          reduce(set.intersection,
                                 (d.get(k, (set(), set()))[1]
                                  for d in dict_list))))
                        for k in all_keys)


        def __get_incorp_nonmatch_dict(self, fmri, excludes):
                """Given a fmri with incorporation dependencies, produce a
                dictionary containing (matching, non matching fmris),
                indexed by pkg name"""
                ret = dict()
                for da in self.__get_dependency_actions(fmri,
                    excludes=excludes):
                        if da.attrs["type"] != "incorporate":
                                continue
                        nm, m, c, d, r = self.__parse_dependency(da, fmri,
                            dotrim=False)
                        for n in nm:
                                ret.setdefault(n.pkg_name,
                                    (set(), set()))[1].add(n)
                        for n in m:
                                ret.setdefault(n.pkg_name,
                                    (set(), set()))[0].add(n)
                return ret

        def __parse_dependency(self, dependency_action, fmri,
            dotrim=True, check_req=False):

                """Return tuple of (disallowed fmri list, allowed fmri list,
                conditional_list, dependency_type, required)"""

                dtype = dependency_action.attrs["type"]
                fmris = [pkg.fmri.PkgFmri(f, "5.11") for f in dependency_action.attrlist("fmri")]
                fmri = fmris[0]

                required = True     # true if match is required for containing pkg
                conditional = None  # if this dependency has conditional fmris
                obsolete_ok = False # true if obsolete pkgs satisfy this dependency

                if dtype == "require":
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim, obsolete_ok=obsolete_ok)

                elif dtype == "optional":
                        obsolete_ok = True
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim,
                            obsolete_ok=obsolete_ok)
                        if fmri.pkg_name not in self.__req_pkg_names:
                                required = False

                elif dtype == "exclude":
                        obsolete_ok = True
                        matching, nonmatching = \
                            self.__comb_older_fmris(fmri, dotrim,
                            obsolete_ok=obsolete_ok)
                        if fmri.pkg_name not in self.__req_pkg_names:
                                required = False

                elif dtype == "incorporate":
                        obsolete_ok = True
                        matching, nonmatching = \
                            self.__comb_auto_fmris(fmri, dotrim,
                            obsolete_ok=obsolete_ok)
                        if fmri.pkg_name not in self.__req_pkg_names:
                                required = False

                elif dtype == "conditional":
                        cond_fmri = pkg.fmri.PkgFmri(
                            dependency_action.attrs["predicate"], "5.11")
                        conditional, nonmatching = self.__comb_newer_fmris(
                            cond_fmri, dotrim, obsolete_ok=obsolete_ok)
                        # Required is only really helpful for solver error
                        # messaging.  At this point in time, there isn't enough
                        # information to determine whether the dependency will
                        # be required or not, so setting this to True leads to
                        # false positives for error conditions.  As such, this
                        # should always be False for now.
                        required = False
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim,
                            obsolete_ok=obsolete_ok)

                elif dtype == "require-any":
                        matching = []
                        nonmatching = []
                        for f in fmris:
                                m, nm = self.__comb_newer_fmris(f, dotrim,
                                    obsolete_ok=obsolete_ok)
                                matching.extend(m)
                                nonmatching.extend(nm)

                        matching = set(matching)
                        nonmatching = set(nonmatching)

                elif dtype == "parent":
                        if self.__parent_pkgs == None:
                                # ignore this dependency
                                matching = nonmatching = frozenset()
                        else:
                                matching, nonmatching = \
                                    self.__comb_auto_fmris(fmri, dotrim=False,
                                    obsolete_ok=True)

                        # not required in the planned image
                        required = False

                elif dtype == "origin":
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim=False,
                            obsolete_ok=obsolete_ok)
                        required = False

                elif dtype == "group":
                        obsolete_ok = True
                        # remove version explicitly
                        fmri.version = None
                        if fmri.pkg_name in self.__avoid_set or \
                            fmri.pkg_name in self.__reject_set:
                                required = False
                                matching = nonmatching = frozenset()
                        else:
                                matching, nonmatching = self.__comb_newer_fmris(fmri,
                                    dotrim, obsolete_ok=obsolete_ok)

                else: # only way this happens is if new type is incomplete
                        raise api_errors.InvalidPackageErrors(
                            "Unknown dependency type %s" % dtype)

                # check if we're throwing exceptions and we didn't find any
                # matches on a required package

                if not check_req or matching or not required:
                        return nonmatching, matching, conditional, dtype, required

                # we're going to toss an exception
                if dtype == "exclude":
                        matching, nonmatching = self.__comb_older_fmris(
                            fmri, dotrim=False, obsolete_ok=False)
                        if not matching:
                                raise DependencyException(
                                    (N_("Package contains 'exclude' dependency {0} on installed package"),
                                    (fmri,)))
                        else:
                                raise DependencyException(
                                    (N_("All versions matching 'exclude' dependency {0} are rejected"),
                                    (fmri,)), matching)
                        # not reached
                elif dtype == "incorporate":
                        matching, nonmatching = \
                            self.__comb_auto_fmris(fmri, dotrim=False,
                            obsolete_ok=obsolete_ok)

                # check if allowing obsolete packages helps

                elif obsolete_ok == False:
                        # see if allowing obsolete pkgs gets us some matches
                        if len(fmris) == 1:
                                matching, nonmatching = \
                                    self.__comb_newer_fmris(fmri, dotrim,
                                    obsolete_ok=True)
                        else:
                                matching = []
                                nonmatching = []
                                for f in fmris:
                                        m, nm = self.__comb_newer_fmris(f,
                                            dotrim, obsolete_ok=True)
                                        matching.extend(m)
                                        nonmatching.extend(nm)
                        if matching:
                                if len(fmris) == 1:
                                        raise DependencyException(
                                            (N_("All acceptable versions of '{0}' dependency on {1} are obsolete"),
                                            (dtype, fmri)))
                                else:
                                        raise DependencyException(
                                            (N_("All acceptable versions of '{0}' dependencies on {1} are obsolete"),
                                            (dtype, fmris)))
                        # something else is wrong
                        matching, nonmatching = self.__comb_newer_fmris(fmri,
                            dotrim=False, obsolete_ok=obsolete_ok)
                else:
                        # try w/o trimming anything
                        matching, nonmatching = self.__comb_newer_fmris(fmri,
                            dotrim=False, obsolete_ok=obsolete_ok)

                if not matching:
                        raise DependencyException(
                            (N_("A version for '{0}' dependency on {1} cannot be found"),
                            (dtype, fmri)))
                else:
                        raise DependencyException(
                            (N_("All versions matching '{0}' dependency {1} are rejected"),
                            (dtype, fmri)),
                            matching)

        def __generate_dependency_errors(self, fmri_list, excludes=EmptyI):
                """ Returns a list of strings describing why fmris cannot
                be installed, or returns an empty list if installation
                is possible. """
                ret = []

                needs_processing = set(fmri_list)
                already_processed = set()

                while needs_processing:
                        fmri = needs_processing.pop()
                        errors, newfmris = self.__do_error_work(fmri,
                            excludes)
                        ret.extend(errors)
                        already_processed.add(fmri)
                        needs_processing |= newfmris - already_processed
                return ret

        def get_trim_errors(self):
                """Returns a list of strings for all FMRIs evaluated by the
                solver explaining why they were rejected.  (All packages
                found in solver's trim database.)"""

                # At a minimum, a solve_*() method must have been called first.
                assert self.__state != SOLVER_INIT
                assert DebugValues["plan"]

                return self.__fmri_list_errors(self.__trim_dict.iterkeys(),
                    already_seen=set())

        def __check_installed(self):
                """Generate list of strings describing why currently
                installed packages cannot be installed, or empty list"""
                ret = []
                for f in self.__installed_fmris - self.__removal_fmris:
                        matching, nonmatching = \
                            self.__comb_newer_fmris(f, dotrim=True, obsolete_ok=True)
                        if matching:
                                continue
                        # there are no matches when disallowed packages are excluded
                        matching, nonmatching = \
                            self.__comb_newer_fmris(f, dotrim=False, obsolete_ok=True)

                        ret.append(_("No suitable version of installed package %s found") % f)
                        ret.extend(self.__fmri_list_errors(matching))

                return ret

        def __fmri_list_errors(self, fmri_list, indent="", already_seen=None):
                """Given a list of fmris, return indented strings why they don't work"""
                ret = []

                fmri_reasons = [
                        self.__fmri_errors(f, indent, already_seen)
                        for f in sorted(fmri_list)
                        ]

                last_reason = None
                for fmri_id, reason in fmri_reasons:
                        if reason == last_reason:
                                ret.extend([" " * len(fmri_id[0]) + fmri_id[1]])
                                continue
                        else: # ends run
                                if last_reason:
                                        ret.extend(last_reason)
                                ret.extend([fmri_id[0] + fmri_id[1]])
                                last_reason = reason
                if last_reason:
                        ret.extend(last_reason)
                return ret

        def __fmri_errors(self, fmri, indent="", already_seen=None):
                """return a list of strings w/ indents why this fmri is not suitable"""

                if already_seen is None:
                        already_seen = set()

                fmri_id = [_("%s  Reject:  ") % indent, str(fmri)]

                tag = _("Reason:")

                if fmri in already_seen:
                        reason = _("%s  %s  [already rejected; see above]") % (indent, tag)
                        return fmri_id, [reason]

                already_seen.add(fmri)

                ms = []

                for reason_t, fmris in sorted(self.__trim_dict[fmri]):
                        if isinstance(reason_t, tuple):
                                reason = _(reason_t[0]).format(*reason_t[1])
                        else:
                                reason = _(reason_t)
                        ms.append("%s  %s  %s" % (indent, tag, reason))
                        tag = " " * len(tag)
                        ms.extend(self.__fmri_list_errors([
                            f
                            for f in fmris
                            if f not in already_seen
                            ], indent + "  ", already_seen))
                return fmri_id, ms

        def __do_error_work(self, fmri, excludes):

                needs_processing = set()

                if fmri in self.__trim_dict:
                        return self.__fmri_list_errors([fmri]), needs_processing

                for a in self.__get_dependency_actions(fmri, excludes):
                        try:
                                match = self.__parse_dependency(a, fmri,
                                   check_req=True)[1]
                        except DependencyException, e:
                                self.__trim(fmri, e.reason, e.fmris)
                                s = _("No suitable version of required package %s found:") % fmri
                                return [s] + self.__fmri_list_errors([fmri]), set()
                        needs_processing |= match
                return [], needs_processing


        # clause generation routines

        def __gen_dependency_clauses(self, fmri, da, dotrim=True):
                """Return clauses to implement this dependency"""
                nm, m, cond, dtype, req = self.__parse_dependency(da, fmri,
                    dotrim)

                if dtype == "require" or dtype == "require-any":
                        return self.__gen_require_clauses(fmri, m)
                elif dtype == "group":
                        if not m and not nm:
                                return [] # no clauses needed; pkg avoided
                        else:
                                return self.__gen_require_clauses(fmri, m)
                elif dtype == "conditional":
                        return self.__gen_require_conditional_clauses(fmri, m, cond)
                elif dtype in ["origin", "parent"]:
                        # handled by trimming proposed set, not by solver
                        return []
                else:
                        return self.__gen_negation_clauses(fmri, nm)


        def __gen_highlander_clauses(self, fmri_list):
                """Return a list of clauses that specifies only one or zero
                of the fmris in fmri_list may be installed.  This prevents
                multiple versions of the same package being installed
                at once"""

                # pair wise negation
                # if a has 4 versions, we need
                # [
                #  [-a.1, -a.2],
                #  [-a.1, -a.3],
                #  [-a.1, -a.4],
                #  [-a.2, -a.3],
                #  [-a.2, -a.4],
                #  [-a.3, -a.4]
                # ]
                # n*(n-1)/2 algorithms suck

                if len(fmri_list) == 1: # avoid generation of singletons
                        return []

                id_list = [ -self.__getid(fmri) for fmri in fmri_list]
                l = len(id_list)

                return [
                        [id_list[i], id_list[j]]
                        for i in range(l-1)
                        for j in range(i+1, l)
                        ]

        def __gen_require_clauses(self, fmri, matching_fmri_list):
                """generate clause for require dependency: if fmri is
                installed, one of fmri_list is required"""
                # if a.1 requires b.2, b.3 or b.4:
                # !a.1 | b.2 | b.3 | b.4

                return [
                        [-self.__getid(fmri)] +
                        [self.__getid(fmri) for fmri in matching_fmri_list]
                        ]

        def __gen_require_conditional_clauses(self, fmri, matching_fmri_list,
            conditional_fmri_list):
                """Generate clauses for conditional dependency: if
                fmri is installed and one of conditional_fmri_list is installed,
                one of fmri list is required"""
                # if a.1 requires c.2, c.3, c.4 if b.2 or newer is installed:
                # !a.1 | !b.2 | c.2 | c.3 | c.4
                # !a.1 | !b.3 | c.2 | c.3 | c.4
                mlist = [self.__getid(f) for f in matching_fmri_list]

                return [
                        [-self.__getid(fmri)] + [-self.__getid(c)] + mlist
                        for c in conditional_fmri_list
                        ]

        def __gen_negation_clauses(self, fmri, non_matching_fmri_list):
                """ generate clauses for optional, incorporate and
                exclude dependencies to exclude non-acceptable versions"""
                # if present, fmri must match ok list
                # if a.1 optionally requires b.3:
                # [
                #   [!a.1 | !b.1],
                #   [!a.1 | !b.2]
                # ]
                fmri_id = self.__getid(fmri)
                return [
                    [-fmri_id, -self.__getid(f)]
                    for f in non_matching_fmri_list
                ]

        def __gen_one_of_these_clauses(self, fmri_list):
                """generate clauses such that at least one of the fmri_list
                members gets installed"""
                # If a has four versions,
                # a.1|a.2|a.3|a.4
                # plus highlander clauses
                assert fmri_list, "Empty list of which one is required"
                return [[self.__getid(fmri) for fmri in fmri_list]]

        def __addclauses(self, clauses):
                """add list of clause lists to solver"""

                for c in clauses:
                        try:
                                if not self.__solver.add_clause(c):
                                        self.__addclause_failure = True
                                self.__clauses += 1
                        except TypeError:
                                e = _("List of integers, not %s, expected") % c
                                raise TypeError, e

        def __get_installed_upgradeable_incorps(self, excludes=EmptyI):
                """Return the latest version of installed upgradeable incorporations w/ install holds"""
                installed_incs = []

                for f in self.__installed_fmris - self.__removal_fmris:
                        for d in self.__catalog.get_entry_actions(f,
                            [catalog.Catalog.DEPENDENCY],
                            excludes=excludes):
                                if d.name == "set" and d.attrs["name"] == "pkg.depend.install-hold":
                                        installed_incs.append(f)

                ret = []
                for f in installed_incs:
                        match, unmatch = self.__comb_newer_fmris(f, dotrim=False)
                        latest = sorted(match, reverse=True)[0]
                        if latest != f:
                                ret.append(latest)
                return ret

        def __get_installed_unbound_inc_list(self, proposed_pkgs, excludes=EmptyI):
                """Return the list of incorporations that are to not to change
                during this install operation, and the lists of fmris they constrain."""

                incorps = set()
                versioned_dependents = set()
                pkg_cons = {}
                install_holds = {}

                # determine installed packages that contain incorporation dependencies,
                # determine those packages that are depended on by explict version,
                # and those that have pkg.depend.install-hold values.

                for f in self.__installed_fmris - self.__removal_fmris:
                        for d in self.__catalog.get_entry_actions(f,
                            [catalog.Catalog.DEPENDENCY],
                            excludes=excludes):
                                if d.name == "depend":
                                        fmris = [pkg.fmri.PkgFmri(fl, "5.11") for fl in
                                            d.attrlist("fmri")]
                                        if d.attrs["type"] == "incorporate":
                                                incorps.add(f.pkg_name)
                                                pkg_cons.setdefault(f, []).append(fmris[0])
                                        for fmri in fmris:
                                                if fmri.version is not None:
                                                        versioned_dependents.add(fmri.pkg_name)
                                elif d.name == "set" and d.attrs["name"] == "pkg.depend.install-hold":
                                        install_holds[f.pkg_name] = d.attrs["value"]

                # find install holds that appear on command line and are thus relaxed
                relaxed_holds = set([
                        install_holds[name]
                        for name in proposed_pkgs
                        if name in install_holds
                        ])
                # add any other install holds that are relaxed because they have values
                # that start w/ the relaxed ones...
                relaxed_holds |= set([
                        hold
                        for hold in install_holds.values()
                        if [ r for r in relaxed_holds if hold.startswith(r + ".") ]
                        ])
                # versioned_dependents contains all the packages that are depended on
                # w/ a explicit version.  We now modify this list so that it does not
                # contain any packages w/ install_holds, unless those holds were
                # relaxed.
                versioned_dependents -= set([
                    pkg_name
                    for pkg_name, hold_value in install_holds.iteritems()
                    if hold_value not in relaxed_holds
                    ])
                # Build the list of fmris that 1) contain incorp. dependencies
                # 2) are not in the set of versioned_dependents and 3) do
                # not explicitly appear on the install command line.
                ret = [
                    self.__installed_dict[pkg_name]
                    for pkg_name in incorps - versioned_dependents
                    if pkg_name not in proposed_pkgs
                    if self.__installed_dict[pkg_name] not in self.__removal_fmris
                ]
                # For each incorporation above that will not change, return a list
                # of the fmris that incorporation constrains
                con_lists = [
                        [
                        i
                        for i in pkg_cons[inc]
                        ]
                        for inc in ret
                        ]

                return ret, con_lists

        def __mark_pub_trimmed(self, pkg_name):
                """Record that a given package stem has been trimmed based on
                publisher."""

                self.__pub_trim[pkg_name] = True

        def __filter_publishers(self, pkg_name):
                """Given a list of fmris for various versions of
                a package from various publishers, trim those
                that are not suitable"""

                if pkg_name in self.__pub_trim: # already done
                        return
                self.__mark_pub_trimmed(pkg_name)

                fmri_list = self.__get_catalog_fmris(pkg_name)
                version_dict = {}


                if pkg_name in self.__publisher:
                        acceptable_pubs = [self.__publisher[pkg_name]]
                        if pkg_name in self.__installed_dict:
                                reason = (N_("Currently installed package '{0}' is from sticky publisher '{1}'."),
                                    (pkg_name, self.__publisher[pkg_name]))
                        else:
                                reason = N_("Package is from publisher other than specified one.")
                else:
                        # order by pub_rank; choose highest possible tier for
                        # pkgs; guard against unconfigured publishers in known catalog
                        pubs_found = list(set([f.get_publisher() for f in fmri_list]))
                        ranked = sorted([
                                        (self.__pub_ranks[p][0], p)
                                        for p in pubs_found
                                        if self.__pub_ranks.get(p, (0, False, False))[2]
                                        ])
                        acceptable_pubs = [ r[1]
                                            for r in ranked
                                            if r[0] == ranked[0][0]
                                            ]
                        if acceptable_pubs:
                                reason = (N_("Higher ranked publisher {0} was selected"), (acceptable_pubs[0],))
                        else:
                                reason = N_("Package publisher is ranked lower in search order")

                # generate a dictionary, indexed by version, of acceptable fmris
                for f in fmri_list:
                        if f.get_publisher() in acceptable_pubs:
                                version_dict.setdefault(f.version, []).append(f)

                # allow installed packages to co-exist to meet dependency reqs.
                # in case new publisher not proper superset of original.
                # avoid multiple publishers w/ the exact same fmri to prevent
                # thrashing in the solver due to many equiv. solutions.

                inst_f = self.__installed_dict.get(pkg_name, None)

                if inst_f:
                        version_dict[inst_f.version] = [inst_f]

                acceptable_list = []
                for l in version_dict.values():
                        acceptable_list.extend(l)

                for f in set(fmri_list) - set(acceptable_list):
                        self.__trim(f, reason)

        # routines to manage the trim dictionary
        # trim dictionary contains the reasons an fmri was rejected for consideration
        # reason is a tuple of a string w/ format chars and args, or just a string.
        # fmri_adds are any fmris that caused the rejection

        def __trim(self, fmri_list, reason, fmri_adds=EmptyI):
                """Remove specified fmri(s) from consideration for specified reason"""

                try:
                        it = iter(fmri_list)
                except TypeError:
                        it = [fmri_list]

                tup = (reason, frozenset(fmri_adds))

                for fmri in it:
                        self.__trim_dict[fmri].add(tup)

        def __trim_older(self, fmri):
                """Trim any fmris older than this one"""
                reason = (N_("Newer version {0} is already installed"), (fmri,))
                self.__trim(self.__comb_newer_fmris(fmri, dotrim=False)[1], reason)

        def __trim_nonmatching_variants(self, fmri):
                vd = self.__get_variant_dict(fmri)

                for v in self.__variants.keys():
                        if v in vd and self.__variants[v] not in vd[v]:
                                if vd == "variant.arch":
                                        reason = N_("Package doesn't support image architecture")
                                else:
                                        reason = (N_("Package doesn't support image variant {0}"), (v,))

                                self.__trim(fmri, reason)

        def __trim_nonmatching_parents1(self, pkg_fmri, fmri):
                if fmri in self.__parent_pkgs:
                        # exact fmri installed in parent
                        return True

                if fmri.pkg_name not in self.__parent_dict:
                        # package is not installed in parent
                        reason = (N_("Package is not installed in "
                            "parent image: {0}"), (fmri.pkg_name,))
                        self.__trim(pkg_fmri, reason)
                        return False

                pf = self.__parent_dict[fmri.pkg_name]
                if fmri.publisher and fmri.publisher != pf.publisher:
                        # package is from a different publisher in the parent
                        reason = (N_("Package in parent is from a "
                            "different publisher: {0}"), (pf,))
                        self.__trim(pkg_fmri, reason)
                        return False

                if pf.version == fmri.version or pf.version.is_successor(
                    fmri.version, version.CONSTRAINT_AUTO):
                        # parent dependency is satisfied
                        return True

                # version mismatch
                if pf.version.is_successor(fmri.version,
                    version.CONSTRAINT_NONE):
                        reason = (N_("Parent image has a incompatible newer "
                            "version: {0}"), (pf,))
                else:
                        reason = (N_("Parent image has an older version of "
                            "package: {0}"), (pf,))

                self.__trim(pkg_fmri, reason)
                return False

        def __trim_nonmatching_parents(self, pkg_fmri, excludes):
                """Trim any pkg_fmri that contains a parent dependency that
                is not satisfied by the parent image."""

                # the fmri for the package should include a publisher
                assert pkg_fmri.publisher

                # if we're not a child then ignore "parent" dependencies.
                if self.__parent_pkgs == None:
                        return True

                # Find all the fmris that we depend on in our parent.
                # Use a set() to eliminate any dups.
                pkg_deps = set([
                    pkg.fmri.PkgFmri(f, "5.11")
                    for da in self.__get_dependency_actions(pkg_fmri, excludes)
                    if da.attrs["type"] == "parent"
                    for f in da.attrlist("fmri")
                ])

                if not pkg_deps:
                        # no parent dependencies.
                        return True

                allowed = True
                for f in pkg_deps:
                        fmri = f
                        if f.pkg_name == pkg.actions.depend.DEPEND_SELF:
                                # check if this package depends on itself.
                                fmri = pkg_fmri
                        if not self.__trim_nonmatching_parents1(pkg_fmri, fmri):
                                allowed = False
                return allowed

        def __trim_nonmatching_origins(self, fmri, excludes):
                """Trim any fmri that contains a origin dependency that is
                not satisfied by the current image or root-image"""

                for da in self.__get_dependency_actions(fmri, excludes):

                        if da.attrs["type"] != "origin":
                                continue

                        req_fmri = pkg.fmri.PkgFmri(da.attrs["fmri"], "5.11")

                        if da.attrs.get("root-image", "").lower() == "true":
                                if self.__root_fmris is None:
                                        img = pkg.client.image.Image(
                                            misc.liveroot(),
                                            allow_ondisk_upgrade=False,
                                            user_provided_dir=True,
                                            should_exist=True)
                                        self.__root_fmris = dict([
                                            (f.pkg_name, f)
                                            for f in img.gen_installed_pkgs()
                                        ])

                                installed = self.__root_fmris.get(
                                    req_fmri.pkg_name, None)
                                reason = (N_("Installed version in root image "
                                    "is too old for origin dependency %s"),
                                    (req_fmri,))
                        else:
                                installed = self.__installed_dict.get(
                                    req_fmri.pkg_name, None)
                                reason = (N_("Installed version in image "
                                    "being upgraded is too old for origin "
                                    "dependency %s"), (req_fmri,))

                        # assumption is that for root-image, publishers align;
                        # otherwise these sorts of cross-environment
                        # dependencies don't work well

                        if not installed or \
                            not req_fmri.version or \
                            req_fmri.version == installed.version or \
                            installed.version.is_successor(req_fmri.version, version.CONSTRAINT_NONE):
                                continue

                        self.__trim(fmri, reason)

                        return False
                return True

        def __dotrim(self, fmri_list):
                """Return fmri_list trimmed of any fmris in self.__trim_dict"""


                ret = [
                        f
                        for f in fmri_list
                        if f not in self.__trim_dict
                        ]
                return ret
