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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import pkg.client.api_errors as api_errors
import pkg.catalog           as catalog
import pkg.solver
import pkg.version           as version
import time

from pkg.misc import EmptyDict, EmptyI


SOLVER_INIT    = "Initialized"
SOLVER_OXY     = "Not possible"
SOLVER_FAIL    = "Failed"
SOLVER_SUCCESS = "Succeeded"

class PkgSolver(object):

        def __init__(self, cat, installed_fmris, pub_ranks, variants, progtrack):
                """Create a PkgSolver instance; catalog
                should contain all known pkgs, installed fmris
                should be a dict of fmris indexed by name that define
                pkgs current installed in the image. Pub_ranks dict contains
                (rank, stickiness, enabled) for each publisher."""
                self.__catalog = cat
                self.__installed_fmris = {}	# indexed by stem
                self.__publisher = {}		# indexed by stem
                self.__possible_dict = {}	# indexed by stem
                self.__pub_ranks = pub_ranks    # rank indexed by pub
                self.__trim_dict = {}           # fmris trimmed from
                				# consideration

                self.__pub_trim = {}		# pkg names already
                                                # trimmed by pub.
                self.__installed_fmris = installed_fmris.copy()

                for f in installed_fmris.values(): # record only sticky pubs
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
                self.__failure_info = ""
                self.__dep_dict = {}
                self.__inc_list = []
                self.__dependents = None

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
                self.__installed_fmris = None
                self.__publisher = None
                self.__possible_dict = None
                self.__pub_ranks = None
                self.__trim_dict = None
                self.__pub_trim = None
                self.__publisher = None
                self.__id2fmri = None
                self.__fmri2id = None
                self.__solver = None
                self.__poss_set = None
                self.__progtrack = None
                self.__addclause_failure = None
                self.__variant_dict = None
                self.__variants = None
                self.__cache = None
                self.__trimdone = None
                self.__fmri_state = None
                self.__start_time = None
                self.__dep_dict = None
                self.__dependents = None
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

        def gen_failure_report(self, verbose):
                """grab saved failure list"""
                if not verbose:
                        return "\nUse -v option for more details"
                else:
                        return "\n".join(self.__failure_info)

        def solve_install(self, existing_freezes, proposed_dict, excludes=EmptyI):
                """Existing_freezes is a list of incorp. style
                fmris that constrain pkg motion, proposed_dict
                contains user specified fmris indexed by pkg_name;
                returns FMRIs to be installed/upgraded in system"""

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT

                self.__state = SOLVER_OXY

                self.__progtrack.evaluate_progress()

                self.__timeit()

                # proposed_dict already contains publisher selection logic,
                # so overwrite __publisher dict w/ values therein
                for name in proposed_dict:
                        self.__publisher[name] = proposed_dict[name][0].get_publisher()

                self.__progtrack.evaluate_progress()

                # find list of incorps we don't let change as a side
                # effect of other changes; exclude any specified on
                # command line
                inc_list, con_lists = self.__get_installed_unbound_inc_list(proposed_dict,
                    excludes=excludes)

                self.__inc_list = inc_list
                self.__progtrack.evaluate_progress()

                # trim fmris we cannot install because they're older
                self.__timeit("phase 1")

                for f in self.__installed_fmris.values():
                        self.__trim_older(f)

                self.__progtrack.evaluate_progress()

                # trim fmris we excluded via proposed_fmris
                for name in proposed_dict:
                        reason = _("This version excluded by specified installation version")
                        self.__trim(set(self.__get_catalog_fmris(name)) -
                            set(proposed_dict[name]), reason)

                self.__timeit("phase 2")
                self.__progtrack.evaluate_progress()

                # now trim pkgs we cannot update due to unconstrained incorporations
                for i, flist in zip(inc_list, con_lists):
                        reason = _("This version is excluded by installed incorporation %s") % i
                        self.__trim(self.__comb_auto_fmris(i)[1], reason)
                        for f in flist:
                                self.__trim(self.__comb_auto_fmris(f)[1], reason)

                self.__timeit("phase 3")
                self.__progtrack.evaluate_progress()

                # now trim any pkgs we cannot update due to freezes
                for f in existing_freezes:
                        reason = _("This version is excluded by freeze %s") % f
                        self.__trim(self.__comb_auto_fmris(f)[1], reason)

                self.__progtrack.evaluate_progress()

                # elide any proposed versions that don't match variants (arch usually)
                self.__timeit("phase 4")
                for name in proposed_dict:
                        for fmri in proposed_dict[name]:
                                self.__trim_nonmatching_variants(fmri)

                # remove any versions from proposed_dict that are in trim_dict
                self.__timeit("phase 5")
                for name in proposed_dict:
                        tv = self.__dotrim(proposed_dict[name])
                        if not tv:
                                ret = [_("No matching version of %s can be installed:") % name]

                                for f in proposed_dict[name]:
                                        ret += ["%s: %s\n" % (f, "\n\t".join(self.__trim_dict[f]))]
                                raise api_errors.PlanCreationException(no_version=ret)
                        proposed_dict[name] = tv

                self.__progtrack.evaluate_progress()

                # build set of possible pkgs
                self.__timeit("phase 6")

                possible_set = set()
                # ensure existing pkgs stay installed; explicitly add in installed fmris
                # in case publisher change has occurred and some pkgs aren't part of new
                # publisher
                for f in self.__installed_fmris.values():
                        possible_set |= self.__comb_newer_fmris(f)[0] | set([f])

                # add the proposed fmris
                for flist in proposed_dict.values():
                        possible_set.update(flist)

                self.__timeit("phase 7")
                possible_set.update(self.__generate_dependency_closure(possible_set,
                    excludes=excludes))

                # remove any versions from proposed_dict that are in trim_dict as
                # trim dict has been updated w/ missing dependencies
                self.__timeit("phase 8")
                for name in proposed_dict:
                        tv = self.__dotrim(proposed_dict[name])
                        if not tv:
                                ret = [_("No version of %s can be installed:") % name]

                                for f in proposed_dict[name]:
                                        ret += ["%s: %s\n" % (f, "\n\t".join(self.__trim_dict[f]))]
                                raise api_errors.PlanCreationException(no_version=ret)
                        proposed_dict[name] = tv

                self.__timeit("phase 9")
                self.__progtrack.evaluate_progress()

                # generate ids, possible_dict for clause generation
                self.__assign_fmri_ids(possible_set)

                # generate clauses for only one version of each package, and
                # for dependencies for each package.  Do so for all possible fmris.

                for name in self.__possible_dict.keys():
                        self.__progtrack.evaluate_progress()
                        # insure that at most one version of a package is installed
                        self.__addclauses(self.__gen_highlander_clauses(
                            self.__possible_dict[name]))
                        # generate dependency clauses for each pkg
                        for fmri in self.__possible_dict[name]:
                                for da in self.__get_dependency_actions(fmri,
                                    excludes=excludes):
                                        self.__addclauses(self.__gen_dependency_clauses(
                                            fmri, da))

                self.__timeit("phase 10")

                # Save a solver instance to check for inherited obsolete pkgs
                # in case we upgraded to a pkg version that now supports
                # obsoletion.
                obsolete_check_solver = self.__save_solver()

                # generate clauses for proposed and installed pkgs
                # note that we create clauses that require one of the
                # proposed pkgs to work; this allows the possible_set
                # to always contain the existing pkgs

                for name in proposed_dict:
                        self.__progtrack.evaluate_progress()
                        self.__addclauses(self.__gen_one_of_these_clauses(
                            set(proposed_dict[name]) & set(self.__possible_dict[name])))

                for name in set(self.__installed_fmris.keys()) - set(proposed_dict.keys()):
                        self.__progtrack.evaluate_progress()
                        self.__addclauses(self.__gen_one_of_these_clauses(
                            self.__possible_dict[name]))

                # save a solver instance so we can come back here
                # this is where errors happen...
                saved_solver = self.__save_solver()
                try:
                        saved_solution = self.__solve()
                except api_errors.PlanCreationException:
                        # no solution can be found.  Check to make sure
                        # our currently installed packages are coherent.
                        # this may not be the case if we upgraded to here
                        # using an older version of pkg and pkgs got obsoleted
                        # out from under us...
                        self.__restore_solver(obsolete_check_solver)
                        # add clauses for installed pkgs
                        for f in self.__installed_fmris.values():
                                self.__addclauses(self.__gen_one_of_these_clauses([f]))
                        try:
                                self.__solve()
                                # worked, so handle as regular error
                        except api_errors.PlanCreationException:
                                # can't solve for existing pkgs; check to see
                                # if we have installed obsolete pkgs w/ non-obsolete deps
                                inst_obs_deps = set([
                                    f
                                    for a in self.__installed_fmris.values()
                                    if self.__fmri_is_obsolete(a)
                                    for f in self.__get_dependents(a, excludes)
                                    if not self.__fmri_is_obsolete(f)
                                    ])

                                if inst_obs_deps:
                                        ret = [
                                                _("Package(s) are installed that depend on obsolete empty packages."),
                                                _("These package(s) must be uninstalled to continue:\n\t%s\n") % \
                                                    "\n\t".join([str(a) for a in inst_obs_deps]),
                                                _("The pkg command to perform needed uninstall is\n\tpkg uninstall %s\n") %
                                                    " ".join(a.pkg_name for a in inst_obs_deps)
                                                ]
                                        raise api_errors.PlanCreationException(no_version=ret)

                        info = []
                        info.append("package solver error")
                        info.append("attempted operation: install")
                        info.append("already installed packages:")
                        for name in sorted(self.__installed_fmris):
                                f = self.__installed_fmris[name]
                                info.append("    %s" % f)
                                for s in self.__print_dependencies(f, excludes=excludes):
                                        info.append("        %s" % s)
                        info.append("proposed pkgs:")
                        for name in proposed_dict:
                                info.append("    %s" % name)
                                for f in proposed_dict[name]:
                                        info.append("        %s %s" %
                                            (f, self.__trim_dict.get(f, "")))
                                        for s in self.__print_dependencies(f, excludes=excludes):
                                                info.append("            %s" % s)

                        if inc_list:
                                info.append("maintained incorporations:")
                                for il in inc_list:
                                        info.append("    %s" % il)
                        else:
                                info.append("maintained incorporations: None")

                        s = "Performance: ["
                        s += ", ".join(["%s: %6.3f" % a for a in self.__timings])
                        s += "]"
                        info.append(s)

                        self.__failure_info = info
                        raise

                self.__timeit("phase 11")

                # check to see if we actually got anything done
                # that we requested... it is possible that the
                # solver cannot find anything to do for the
                # requested packages, but actually just
                # picked some other packages to upgrade

                installed_set = set(self.__installed_fmris.values())
                proposed_changes = [
                        f
                        for f in saved_solution - installed_set
                        if f.pkg_name in proposed_dict
                ]

                if not proposed_changes:
                        return self.__cleanup(installed_set)

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

                for fmri in (saved_solution & set(self.__installed_fmris.values())):
                        self.__addclauses(self.__gen_one_of_these_clauses([fmri]))

                solution = self.__solve()

                for f in solution.copy():
                        if self.__fmri_is_obsolete(f):
                                solution.remove(f)

                self.__timeit("phase 12")
                return self.__cleanup(self.__elide_possible_renames(solution,
                    excludes))

        def solve_update(self, existing_freezes, excludes=EmptyI):
                # trim fmris we cannot install because they're older
                self.__timeit()

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT

                for f in self.__installed_fmris.values():
                        self.__trim_older(f)

                self.__timeit("phase 1")

                # generate set of possible fmris
                possible_set = set()

                for f in self.__installed_fmris.values():
                        matching = self.__comb_newer_fmris(f)[0]
                        if not matching:            # disabled publisher...
                                matching = set([f]) # staying put is an option
                        possible_set |=  matching

                self.__timeit("phase 2")

                possible_set.update(self.__generate_dependency_closure(possible_set,
                    excludes=excludes))

                self.__timeit("phase 3")

                # generate ids, possible_dict for clause generation
                self.__assign_fmri_ids(possible_set)

                # generate clauses for only one version of each package, and
                # for dependencies for each package.  Do so for all possible fmris.

                for name in self.__possible_dict.keys():
                        # insure that at most one version of a package is installed
                        self.__addclauses(self.__gen_highlander_clauses(
                            self.__possible_dict[name]))
                        # generate dependency clauses for each pkg
                        for fmri in self.__possible_dict[name]:
                                for da in self.__get_dependency_actions(fmri,
                                    excludes=excludes):
                                        self.__addclauses(self.__gen_dependency_clauses(
                                            fmri, da))
                self.__timeit("phase 4")

                # generate clauses for installed pkgs

                for name in self.__installed_fmris.keys():
                        self.__addclauses(self.__gen_one_of_these_clauses(
                            self.__possible_dict[name]))

                self.__timeit("phase 5")
                solution = self.__solve()

                for f in solution.copy():
                        if self.__fmri_is_obsolete(f):
                                solution.remove(f)

                return self.__cleanup(self.__elide_possible_renames(solution,
                    excludes))

        def solve_uninstall(self, existing_freezes, uninstall_list, recursive, excludes):
                """Compute changes needed for uninstall"""

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT

                # generate list of installed pkgs w/ possible renames removed to forestall
                # failing removal due to presence of unneeded renamed pkg

                orig_installed_set = set(self.__installed_fmris.values())
                renamed_set = orig_installed_set - \
                    self.__elide_possible_renames(orig_installed_set, excludes)

                if recursive is True:
                        needs_processing = set(uninstall_list) | renamed_set
                        proposed_removals = set()

                        while needs_processing:
                                pfmri = needs_processing.pop()
                                proposed_removals.add(pfmri)
                                needs_processing |= self.__get_dependents(pfmri, excludes) - proposed_removals
                else:
                        proposed_removals = set(uninstall_list) | renamed_set

                # check for dependents
                for pfmri in proposed_removals:
                        dependents = self.__get_dependents(pfmri, excludes) - proposed_removals
                        if dependents:
                                raise api_errors.NonLeafPackageException(pfmri, dependents)

                # remove any additional pkgs
                return self.__cleanup(self.__elide_possible_renames(
                    orig_installed_set - proposed_removals, excludes))

        def solve_change_varcets(self, existing_freezes, new_variants, new_facets, new_excludes):
                """Compute packaging changes needed to effect
                desired variant and or facet change"""

                # Once solution has been returned or failure has occurred, a new
                # solver must be used.
                assert self.__state == SOLVER_INIT

                # First, determine if there are any packages that are
                # not compatible w/ the new variants, and compute
                # their removal

                keep_set = set()
                removal_set = set()

                if new_variants:
                        self.__variants = new_variants
                self.__excludes = new_excludes #must include facet changes

                if new_variants:
                        for f in self.__installed_fmris.values():
                                d = self.__get_variant_dict(f)
                                for k in new_variants.keys():
                                        if k in d and new_variants[k] not in \
                                            d[k]:
                                                removal_set.add(f)
                                                break
                                else:
                                        keep_set.add(f)
                else: # keep the same pkgs as a starting point for facet changes only
                        keep_set = set(self.__installed_fmris.values())

                # XXX check existing freezes to see if they permit removals

                # recompute solution as if a blank image was being
                # considered; if a generic package depends on a
                # architecture specific one, the operation will fail.

                if not keep_set:
                        # in case this deletes our last package
                        return self.__cleanup([])

                blank_solver = PkgSolver(self.__catalog, {} , self.__pub_ranks,
                    self.__variants, self.__progtrack)

                proposed_dict = dict([(f.pkg_name, [f]) for f in keep_set])
                return self.__cleanup(blank_solver.solve_install(
                    existing_freezes, proposed_dict, new_excludes))

        def __save_solver(self):
                """Create a saved copy of the current solver state and return it"""
                return (self.__addclause_failure,
                        pkg.solver.msat_solver(self.__solver))

        def __restore_solver(self, solver):
                """Set the current solver state to the previously saved one"""

                self.__addclause_failure, self.__solver = solver
                self.__iterations = 0

        def __solve(self, older=False, max_iterations=2000):
                """Perform iterative solution; try for newest pkgs unless older=True"""
                solution_vector = []
                self.__state = SOLVER_FAIL
                eliminated = set()
                while not self.__addclause_failure and self.__solver.solve([]):
                        self.__iterations += 1

                        if self.__iterations > max_iterations:
                                break

                        solution_vector = self.__get_solution_vector()

                        # prevent the selection of any older pkgs
                        for fid in solution_vector:
                                if not older:
                                        for f in self.__comb_newer_fmris(
                                            self.__getfmri(fid))[1]:
                                                if f not in eliminated:
                                                        eliminated.add(f)
                                                        self.__addclauses([[-self.__getid(f)]])
                                else:
                                        pfmri = self.__getfmri(fid)
                                        for f in self.__comb_newer_fmris(pfmri)[0] - \
                                            set([pfmri]):
                                                if f not in eliminated:
                                                        eliminated.add(f)
                                                        self.__addclauses([[-self.__getid(f)]])

                        # prevent the selection of this exact combo; permit [] solution
                        if not solution_vector:
                                break
                        self.__addclauses([[-i for i in solution_vector]])

                if not self.__iterations:
                        raise api_errors.PlanCreationException(no_solution=True)

                self.__state = SOLVER_SUCCESS

                solution = set([self.__getfmri(i) for i in solution_vector])

                return solution

        def __get_solution_vector(self):
                """Return solution vector from solver"""
                return sorted([
                    (i + 1) for i in range(self.__solver.get_variables())
                    if self.__solver.dereference(i)
                ])

        def __assign_fmri_ids(self, possible_set):
                """ give a set of possible fmris, assign ids"""
                # generate dictionary of possible pkgs fmris by pkg stem
                self.__possible_dict.clear()
                self.__poss_set |= possible_set

                for f in possible_set:
                        self.__possible_dict.setdefault(f.pkg_name, []).append(f)
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

        def __get_catalog_fmris(self, pkg_name, dotrim=True):
                """ return the list of fmris in catalog for this pkg name"""
                if dotrim and pkg_name not in self.__pub_trim:
                        self.__filter_publishers(pkg_name)

                return [
                        f
                        for tp in self.__get_fmris_by_version(pkg_name)
                        for f in tp[1]
                        if not dotrim or (f not in self.__trim_dict and
                                          (not self.__poss_set or f in self.__poss_set))
                        ]

        def __comb_newer_fmris(self, fmri, dotrim=True, obsolete_ok=True):
                """Returns tuple of set of fmris that are match witinin
                CONSTRAINT.NONE of specified version and set of remaining fmris."""
                return self.__comb_common(fmri, dotrim, version.CONSTRAINT_NONE, obsolete_ok)

        def __comb_common(self, fmri, dotrim, constraint, obsolete_ok):
                """Underlying impl. of other comb routines"""
                tp = (fmri, dotrim, constraint, obsolete_ok) # cache index
                # determine if the data is cacheable or cached:
                if (not self.__trimdone and dotrim) or tp not in self.__cache:
                        all_fmris = set(self.__get_catalog_fmris(fmri.pkg_name, dotrim))
                        matching = set([
                                        f
                                        for f in all_fmris
                                        if not fmri.version or
                                        fmri.version == f.version or
                                        f.version.is_successor(fmri.version,
                                            constraint=constraint)
                                        if obsolete_ok or not self.__fmri_is_obsolete(f)
                                        ])
                        # if we haven't finished triming, don't cache this
                        if not self.__trimdone and dotrim:
                                return matching, all_fmris - matching
                        # cache the result
                        self.__cache[tp] = (matching, all_fmris - matching)
                return self.__cache[tp]

        def __comb_older_fmris(self, fmri, dotrim=True, obsolete_ok=True):
                """Returns tuple of set of fmris that are older than
                specified version and set of remaining fmris."""
                newer, older = self.__comb_newer_fmris(fmri, dotrim, obsolete_ok)
                return older, newer

        def __comb_auto_fmris(self, fmri, dotrim=True, obsolete_ok=True):
                """Returns tuple of set of fmris that are match witinin
                CONSTRAINT.AUTO of specified version and set of remaining fmris."""
                return self.__comb_common(fmri, dotrim, version.CONSTRAINT_AUTO, obsolete_ok)

        def __fmri_loadstate(self, fmri, excludes):
                """load fmri state (obsolete == True, renamed == True)"""

                supported = True
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
                        self.__trim(fmri, _("Package contains invalid or unsupported actions"))
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

        def __get_dependency_actions(self, fmri, excludes=EmptyI):
                """Return list of all dependency actions for this fmri"""

                return [
                        a
                        for a in self.__catalog.get_entry_actions(fmri,
                            [catalog.Catalog.DEPENDENCY], excludes=excludes)
                        if a.name == "depend"
                        ]

        def __get_variant_dict(self, fmri, excludes=EmptyI):
                """Return dictionary of variants suppported by fmri"""
                try:
                        if fmri not in self.__variant_dict:
                                self.__variant_dict[fmri] = dict(
                                    self.__catalog.get_entry_all_variants(fmri))
                except api_errors.InvalidPackageErrors:
                        # Trim package entries that have unparseable action data
                        # so that they can be filtered out later.
                        self.__variant_dict[fmri] = {}
                        self.__trim(fmri, _("Package contains invalid or unsupported actions"))
                return self.__variant_dict[fmri]

        def __generate_dependency_closure(self, fmri_set, excludes=EmptyI, dotrim=True):
                """return set of all fmris the set of specified fmris could depend on"""

                needs_processing = fmri_set
                already_processed = set()

                while (needs_processing):
                        fmri = needs_processing.pop()
                        self.__progtrack.evaluate_progress()
                        already_processed.add(fmri)
                        needs_processing |= (self.__generate_dependencies(fmri, excludes,
                            dotrim) - already_processed)
                return already_processed

        def __generate_dependencies(self, fmri, excludes=EmptyI, dotrim=True):
                """return set of direct dependencies of this pkg"""
                try:
                        return set([
                             f
                             for da in self.__get_dependency_actions(fmri, excludes)
                             for f in self.__parse_dependency(da, dotrim, check_req=True)[1]
                             if da.attrs["type"] == "require"
                             ])

                except api_errors.InvalidPackageErrors:
                        # Trim package entries that have unparseable action data
                        # so that they can be filtered out later.
                        self.__trim(fmri, _("Package contains invalid or unsupported actions"))
                        return set([])
                except RuntimeError, e:
                        self.__trim(fmri, str(e))
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
                                if da.attrs["type"] == "require":
                                        new_fmri = fmris_by_name[pkg.fmri.PkgFmri(da.attrs["fmri"], "5.11").pkg_name]
                                        # since new_fmri will not be treated as renamed, make sure
                                        # we check any dependencies it has
                                        if new_fmri not in already_processed:
                                                needs_processing.add(new_fmri)
                                        renamed_fmris.discard(new_fmri)
                return set(fmris) - renamed_fmris


        def __get_dependents(self, pfmri, excludes=EmptyI):
                """return set of installed fmris that depend on specified installed fmri"""
                if self.__dependents is None:
                        self.__dependents = {}
                        for f in self.__installed_fmris.values():
                                for da in self.__get_dependency_actions(f, excludes):
                                        if da.attrs["type"] == "require":
                                                self.__dependents.setdefault(
                                                    self.__installed_fmris[pkg.fmri.PkgFmri(
                                                    da.attrs["fmri"], "5.11").pkg_name],
                                                    set()).add(f)
                return self.__dependents.get(pfmri, set())

        def __parse_dependency(self, dependency_action, dotrim=True, check_req=False):
                """Return tuple of (disallowed fmri list, allowed fmri list,
                    dependency_type)"""
                dtype = dependency_action.attrs["type"]
                fmri =  pkg.fmri.PkgFmri(dependency_action.attrs["fmri"], "5.11")

                if dtype == "require":
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim, obsolete_ok=False)
                elif dtype == "optional":
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim, obsolete_ok=True)
                elif dtype == "exclude":
                        matching, nonmatching = \
                            self.__comb_older_fmris(fmri, dotrim, obsolete_ok=True)
                elif dtype == "incorporate":
                        matching, nonmatching = \
                            self.__comb_auto_fmris(fmri, dotrim, obsolete_ok=True)
                else:
                        matching, nonmatching = [], [] # no idea what this dependency is

                if check_req and not matching and dtype == "require":
                        matching, nonmatching = \
                            self.__comb_newer_fmris(fmri, dotrim, obsolete_ok=True)
                        if not matching:
                                raise RuntimeError, \
                                    "Suitable required dependency %s cannot be found" % fmri
                        else:
                                raise RuntimeError, \
                                    "Required dependency %s is obsolete" % fmri

                return nonmatching, matching, dtype

        def __disp_fmri(self, f, excludes=EmptyI):
                """annotate fmris if they're obsolete, renamed or installed"""
                if not self.__dep_dict:
                        for fi in self.__installed_fmris.values():
                                for df in self.__generate_dependencies(fi, excludes=excludes):
                                        self.__dep_dict.setdefault(df.pkg_name, []).append(fi)

                installed = f == self.__installed_fmris.get(f.pkg_name, None)

                if self.__fmri_is_obsolete(f, excludes):
                        deps = self.__dep_dict.get(f.pkg_name, [])
                        if deps:
                                s = " (OBSOLETE and incompatible with installed pkgs: %s)" % (
                                    ", ".join([str(fd) for fd in deps]))
                        else:
                                s = " (OBSOLETE)"
                elif self.__fmri_is_renamed(f, excludes):
                        s = " (RENAMED)"
                elif installed:
                        s = " (INSTALLED)"
                else:
                        s = ""
                return "%s%s" % (f, s)

        def __print_dependencies(self, fmri, excludes=EmptyI):
                """ used to display dependencies when things go wrong"""
                ret = []

                for a in self.__get_dependency_actions(fmri, excludes):
                        ms = []
                        unmatch, match, dtype = self.__parse_dependency(a)
                        if not match:
                                untrimmed_match = self.__parse_dependency(a, dotrim=False)[1]

                        dfmri =  pkg.fmri.PkgFmri(a.attrs["fmri"], "5.11")

                        if dtype == "require":
                                if not match:
                                        ms.append("FAIL: No matching packages found")

                                        for f in untrimmed_match:
                                                ms.append("    Ruled out %s because: %s" % (
                                                    f, ", ".join(self.__trim_dict.get(f, "no info?"))))

                                else:
                                        ms.append("Requires one of: " + ", ".join(
                                            [self.__disp_fmri(f, excludes) for f in match]))

                        elif dtype == "incorporate":
                                pkg_name = dfmri.pkg_name

                                if not match:
                                        if pkg_name in self.__installed_fmris:
                                                ms.append("FAIL: no suitable newer version for installed pkg %s" %\
                                                    self.__installed_fmris[pkg_name])

                                                for f in untrimmed_match:
                                                        ms.append("   Ruled out %s because: %s\n" % (
                                                            f, ", ".join(self.__trim_dict.get(f, "no info?"))))

                                elif pkg_name in self.__installed_fmris:
                                        ms.append("Requires one of: " + ", ".join(
                                            [self.__disp_fmri(f, excludes) for f in match]))
                        else:   # handles both optional and exclude dependencies as they're
                                # just opposites of each other.
                                if not unmatch:
                                        ms.append("No packages excluded")
                                else:
                                        ms.append("Excludes: " + ", ".join(
                                            [self.__disp_fmri(f, excludes) for f in unmatch]))

                        if ms:
                                ret.append("%15s: %s" % (dtype, a.attrs["fmri"]))
                                for m in ms:
                                        ret.append("%s%s" % (" " * 20, m))

                return ret

        # clause generation routines

        def __gen_dependency_clauses(self, fmri, da, dotrim=True):
                """Return clauses to implement this dependency"""
                nm, m, dtype = self.__parse_dependency(da, dotrim)
                if dtype == "require":
                        return self.__gen_require_clauses(fmri, m)
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
                return [[-fmri_id, -self.__getid(f)] for f in non_matching_fmri_list]

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
                                raise TypeError, "List of integers, not %s, expected" % c

        def __get_installed_unbound_inc_list(self, proposed_fmris, excludes=EmptyI):
                """Return the list of incorporations that are to not to change
                during this install operation, and the lists of fmris they constrain."""

                incorps = set()
                versioned_dependents = set()
                pkg_cons = {}
                install_holds = {}

                # determine installed packages that contain incorporation dependencies,
                # determine those packages that are depended on by explict version,
                # and those that have pkg.depend.install-hold values.

                for f in self.__installed_fmris.values():
                        for d in self.__catalog.get_entry_actions(f,
                            [catalog.Catalog.DEPENDENCY],
                            excludes=excludes):
                                if d.name == "depend":
                                        fmri = pkg.fmri.PkgFmri(d.attrs["fmri"], "5.11")
                                        if d.attrs["type"] == "incorporate":
                                                incorps.add(f.pkg_name)
                                                pkg_cons.setdefault(f, []).append(fmri)
                                        if "@" in d.attrs["fmri"]:
                                                versioned_dependents.add(fmri.pkg_name)
                                elif d.name == "set" and d.attrs["name"] == "pkg.depend.install-hold":
                                        install_holds[f.pkg_name] = d.attrs["value"]

                # find install holds that appear on command line and are thus relaxed
                relaxed_holds = set([
                        install_holds[name]
                        for name in proposed_fmris
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
                    self.__installed_fmris[pkg_name]
                    for pkg_name in incorps - versioned_dependents
                    if pkg_name not in proposed_fmris
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

        def __filter_publishers(self, pkg_name):
                """Given a list of fmris for various versions of
                a package from various publishers, trim those
                that are not suitable"""

                if pkg_name in self.__pub_trim: # already done
                        return

                fmri_list = self.__get_catalog_fmris(pkg_name, dotrim=False)
                version_dict = {}

                self.__pub_trim[pkg_name] = True

                # XXX need to set up per disgruntled publisher reasons
                if pkg_name in self.__publisher:
                        acceptable_pubs = [self.__publisher[pkg_name]]
                        reason = _("Publisher differs from installed or specified version")
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
                        reason = _("Publisher is lower ranked")

                # generate a dictionary, indexed by version, of acceptable fmris
                for f in fmri_list:
                        if f.get_publisher() in acceptable_pubs:
                                version_dict.setdefault(f.version, []).append(f)

                # allow installed packages to co-exist to meet dependency reqs.
                # in case new publisher not proper superset of original.
                # avoid multiple publishers w/ the exact same fmri to prevent
                # thrashing in the solver due to many equiv. solutions.

                inst_f = self.__installed_fmris.get(pkg_name, None)

                if inst_f:
                        version_dict[inst_f.version] = [inst_f]

                acceptable_list = []
                for l in version_dict.values():
                        acceptable_list.extend(l)

                for f in set(fmri_list) - set(acceptable_list):
                        self.__trim(f, reason)

        # routines to manage the trim dictionary
        def __trim(self, fmri_list, reason):
                """Remove specified fmri(s) from consideration for specified reason"""
                try:
                        it = iter(fmri_list)
                except TypeError:
                        it = [fmri_list]
                for fmri in it:
                        self.__trim_dict.setdefault(fmri, []).append(reason)

        def __trim_older(self, fmri):
                """Trim any fmris older than this one"""
                reason = _("Newer version %s is already installed") % fmri
                self.__trim(self.__comb_newer_fmris(fmri)[1], reason)

        def __trim_nonmatching_variants(self, fmri):
                vd = self.__get_variant_dict(fmri)

                for v in self.__variants.keys():
                        if v in vd and self.__variants[v] not in vd[v]:
                                if vd == "variant.arch":
                                        reason = _("Package doesn't support image architecture")
                                else:
                                        reason = _("Package doesn't support image variant %s") % v

                                self.__trim(fmri, reason)

        def __dotrim(self, fmri_list):
                """Return fmri_list trimmed of any fmris in self.__trim_dict"""


                ret = [
                        f
                        for f in fmri_list
                        if f not in self.__trim_dict
                        ]
                return ret
