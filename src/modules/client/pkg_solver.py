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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import pkg.client.api_errors as api_errors
import pkg.catalog           as catalog
import pkg.solver
import pkg.version           as version
import time
import sys

from pkg.misc import EmptyI


SOLVER_INIT    = "Initialized"
SOLVER_OXY     = "Not poseable"
SOLVER_FAIL    = "Failed"
SOLVER_SUCCESS = "Succeeded"

class PkgSolver(object):

        def __init__(self, cat, installed_fmris, pub_ranks, variants, progtrack):
                """Create a PkgSolver instance; catalog
                should contain all known pkgs, installed fmris
                should be a dict of fmris indexed by name that define
                pkgs current installed in the image. Pub_ranks dict contains
                (rank, stickiness) for each publisher; disabled publishers
                should not be included"""
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
                self.__trimdone = False         # indicate we're finished trimming
                self.__fmri_state = {}          # cache of obsolete, renamed bits
                # so we can print something reasonable
                self.__state = SOLVER_INIT
                self.__iterations = 0
                self.__clauses     = 0
                self.__variables   = 0
                self.__timings = []
                self.__start_time = 0
                self.__failure_info = ""

        def __str__(self):

                s = "Solver: [" 
                if self.__state in [SOLVER_FAIL, SOLVER_SUCCESS]:
                        s += " Variables: %d Clauses: %d Iterations: %d" % (
                            self.__variables, self.__clauses, self.__iterations)
                s += " State: %s]" % self.__state

                s += "\nTimings: ["
                s += ", ".join(["%s: %s" % a for a in self.__timings])
                s += "]"
                return s

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

                for f in self.__installed_fmris.values():
                        possible_set |= self.__comb_newer_fmris(f)[0]

                for name in proposed_dict:
                        for f in proposed_dict[name]:
                                possible_set.add(f)
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
                # generate clauses for installed and to be installed pkgs    
                for name in set(proposed_dict.keys() + 
                    self.__installed_fmris.keys()) :
                        self.__progtrack.evaluate_progress()
                        self.__addclauses(self.__gen_one_of_these_clauses(
                            self.__possible_dict[name]))

                # save a solver instance so we can come back here
                # this is where errors happen...
                saved_solver = self.__save_solver()
                try:
                        saved_solution = self.__solve()
                except api_errors.PlanCreationException:
                        info = []
                        info.append("package solver error")
                        info.append("attempted operation: install")
                        info.append("already installed packages:")
                        for name in sorted(self.__installed_fmris):
                                f = self.__installed_fmris[name]
                                info.append("\t%s" % f)
                                for s in self.__print_dependencies(f, excludes):
                                        info.append("\t\t\t%s" % s)
                        info.append("proposed pkgs:")
                        for name in proposed_dict:
                                info.append("\t%s" % name)
                                for f in proposed_dict[name]:
                                        info.append("\t\t%s %s" % 
                                            (f, self.__trim_dict.get(f, "")))
                                        for s in self.__print_dependencies(f, excludes):
                                                info.append("\t\t\t%s" % s)
                        
                        if inc_list:
                                il = ", ".join([str(i) for i in inc_list])
                        else:
                                il = "None"

                        info.append("maintained incorporations: %s" % il)
                        
                        self.__failure_info = info
                        raise

                self.__timeit("phase 11")
                
                # we have a solution that works... attempt to
                # reduce collateral damage to other packages
                # while still keeping command line pkgs at their
                # optimum level

                self.__restore_solver(saved_solver)

                # fix the fmris that were specified on the cmd line
                # at their optimum (newest) level along with the
                # new dependencies, but try and avoid upgrading 
                # already installed pkgs.

                for fmri in saved_solution:
                        if fmri.pkg_name in proposed_dict or \
                           fmri.pkg_name not in self.__installed_fmris:
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
                return solution

        def solve_update(self, existing_freezes, excludes=EmptyI):
                # trim fmris we cannot install because they're older
                self.__timeit()

                for f in self.__installed_fmris.values():
                        self.__trim_older(f)                

                self.__timeit("phase 1")

                # generate set of possible fmris
                possible_set = set()

                for f in self.__installed_fmris.values():
                        possible_set.add(f) # in case we cannot talk to publisher
                        possible_set |= self.__comb_newer_fmris(f)[0]

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
                        
                return solution 

        def solve_change_varcets(self, existing_freezes, new_variants, new_facets, new_excludes):
                """Compute packaging changes needed to effect
                desired variant and or facet change"""

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
                        return [] # in case this deletes our last package

                blank_solver = PkgSolver(self.__catalog, {} , self.__pub_ranks, 
                    self.__variants, self.__progtrack)

                proposed_dict = dict([(f.pkg_name, [f]) for f in keep_set])
                return blank_solver.solve_install(existing_freezes, proposed_dict, new_excludes)

        def __save_solver(self):
                """Create a saved copy of the current solver state and return it"""
                return (self.__addclause_failure, 
                        pkg.solver.msat_solver(self.__solver))

        def __restore_solver(self, solver):
                """Set the current solver state to the previously saved one"""

                self.__addclause_failure, self.__solver = solver
                self.__iterations = 0
        
        def __solve(self, older=False):
                """Perform iterative solution; try for newest pkgs unless older=True"""
                solution_vector = []
                self.__state = SOLVER_FAIL

                while not self.__addclause_failure and self.__solver.solve([]):
                        self.__iterations += 1
                        solution_vector = self.__get_solution_vector()
                        # prevent the selection of any older pkgs
                        for fid in solution_vector:
                                if not older:
                                        for f in self.__comb_newer_fmris(
                                            self.__getfmri(fid))[1]:
                                                self.__addclauses([[-self.__getid(f)]])
                                else:
                                        pfmri = self.__getfmri(fid)
                                        for f in self.__comb_newer_fmris(pfmri)[0] - \
                                            set([pfmri]):
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
                tp = (fmri, dotrim, constraint) # cache index
                # determine if the data is cachable or cached:
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
                
                relevant = dict([ 
                        (a.attrs["name"], a.attrs["value"])
                        for a in self.__catalog.get_entry_actions(fmri, 
                        [catalog.Catalog.DEPENDENCY], excludes=excludes)
                        if a.name == "set" and \
                            a.attrs["name"] in ["pkg.renamed", "pkg.obsolete"]
                        ])
                self.__fmri_state[fmri] = (
                    relevant.get("pkg.obsolete", "false").lower() == "true",
                    relevant.get("pkg.renamed", "false").lower() == "true")
                        
        def __fmri_is_obsolete(self, fmri, excludes=EmptyI):
                """check to see if fmri is obsolete"""
                if fmri not in self.__fmri_state:
                        self.__fmri_loadstate(fmri, excludes)
                return self.__fmri_state[fmri][0]

        def __fmri_is_renamed(self, fmri, excludes=EmptyI):
                """check to see if fmri is obsolete"""
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
                if fmri not in self.__variant_dict:
                        self.__variant_dict[fmri] = dict(
                            self.__catalog.get_entry_all_variants(fmri)
#                            [
#                            (a.attrs["name"], a.attrs["value"])
#                            for a in self.__catalog.get_entry_actions(fmri, 
#                                [catalog.Catalog.DEPENDENCY], excludes=excludes)
#                            if a.name == "set" and a.attrs["name"].startswith("variant.")
#                            ]
                            )
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

                except RuntimeError, e:
                        self.__trim(fmri, str(e))
                        return set([])

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
                        matching, nonmatching = [],[] # no idea what this dependency is

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

        def __print_dependencies(self, fmri, excludes=EmptyI):
                """ used to display dependencies when things go wrong"""
                ret = []

                for a in self.__get_dependency_actions(fmri, excludes):

                        unmatch, match, dtype = self.__parse_dependency(a)

                        if dtype == "require":
                                if not match:
                                        ms = "No matching packages found"
                                else:
                                        ms = "Requires: " + ", ".join([str(f) for f in match])
                        else:
                                if not unmatch:
                                        ms = "No packages excluded"
                                else:
                                        ms = "Excludes: " + ", ".join([str(f) for f in unmatch])

                        ret.append("%s dependency: %s: %s" % (dtype, a.attrs["fmri"], ms))

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
                """Return the list of incorporations that are installed and do not
                have any other pkg depending on any specific version being installed,
                along w/ the list of constrained fmris"""
                pkgs = {}
                incorps = set()
                versioned_dependents = set()
                proposed_names = proposed_fmris.keys()
                pkg_cons = {}

                for f in self.__installed_fmris.values():
                        pkgs[f.pkg_name] = f
                        for d in self.__get_dependency_actions(f, excludes):
                                fmri = pkg.fmri.PkgFmri(d.attrs["fmri"], "5.11")
                                if d.attrs["type"] == "incorporate":
                                        incorps.add(f.pkg_name)
                                        pkg_cons.setdefault(f, []).append(fmri)
                                if fmri.has_version:
                                        versioned_dependents.add(fmri.pkg_name)

                ret = [
                    pkgs[f] 
                    for f in incorps - versioned_dependents
                    if f not in proposed_names
                ]

                con_list = [
                        [
                        i
                        for i in pkg_cons[inc]
                        ]
                        for inc in ret
                        ]

                return ret, con_list                

        def __filter_publishers(self, pkg_name):
                """Given a list of fmris for various versions of
                a package from various publishers, trim those
                that are not suitable"""

                if pkg_name in self.__pub_trim: # already done
                        return

                fmri_list = self.__get_catalog_fmris(pkg_name, dotrim=False)
                version_dict = {}


                self.__pub_trim[pkg_name] = True

                if pkg_name in self.__publisher:
                        acceptable_pubs = [self.__publisher[pkg_name]]
                        reason = _("Publisher differs from installed or specifed version")
                else:
                        # order by pub_rank; choose highest possible tier for
                        # pkgs
                        pubs_found = list(set([f.get_publisher() for f in fmri_list]))
                        ranked = sorted([(self.__pub_ranks[p][0], p) for p in pubs_found])
                        acceptable_pubs = [ r[1] 
                                            for r in ranked 
                                            if r[0] == ranked[0][0]
                                            ]
                        reason = _("Publisher is lower ranked")

                # generate a dictionary, indexed by version, of acceptable fmris
                for f in fmri_list:
                        if f.get_publisher() in acceptable_pubs:
                                version_dict.setdefault(f.get_version(), []).append(f)

                # add installed packages; always prefer the installed fmri
                # if they match exactly to prevent needless re-installs
                # avoid multiple publishers w/ exactly the same fmri to prevent 
                # thrashing in the solver due to many equiv. solutions.

                for f in fmri_list:
                        v = f.get_version()
                        if self.__installed_fmris.get(pkg_name, None) == f:
                                if v not in version_dict:
                                        version_dict[v] = [f]
                                else:
                                        for i, nf in enumerate(version_dict[v][:]):
                                                if nf.version == f.version:
                                                        version_dict[v][i] = f
                acceptable_list = []
                version_dict.values()
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
