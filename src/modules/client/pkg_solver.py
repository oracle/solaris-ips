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
# Copyright (c) 2007, 2024, Oracle and/or its affiliates.
#

"""Provides the interfaces and exceptions needed to determine which packages
should be installed, updated, or removed to perform a requested operation."""

import operator
import time

from collections import defaultdict
# Redefining built-in; pylint: disable=W0622
from functools import reduce

import pkg.actions
import pkg.catalog as catalog
import pkg.client.api_errors as api_errors
import pkg.client.image
import pkg.fmri
import pkg.misc as misc
import pkg.solver
import pkg.version as version

from pkg.actions.depend import known_types as dep_types
from pkg.client.debugvalues import DebugValues
from pkg.client.firmware import Driver, Cpu
from pkg.client.pkgdefs import PKG_OP_UNINSTALL, PKG_OP_UPDATE
from pkg.misc import EmptyI, EmptyDict, N_

SOLVER_INIT    = "Initialized"
SOLVER_OXY     = "Not possible"
SOLVER_FAIL    = "Failed"
SOLVER_SUCCESS = "Succeeded"

#
# Constants representing reasons why packages were trimmed from possible set.
# The reasons listed below do *not* always map 1:1 to the error text produced;
# instead, they indicate the 'type' of trim applied. Values below must be
# unique, but can be changed at any time.
#
_TRIM_DEP_MISSING = 0              # no matching pkg version found for dep
_TRIM_DEP_OBSOLETE = 1             # all versions allowed by dep are obsolete
_TRIM_DEP_TRIMMED = 2              # all versions allowed by dep already trimmed
_TRIM_FIRMWARE = 3                 # firmware version requirement
_TRIM_FREEZE = 4                   # pkg not allowed by freeze
_TRIM_INSTALLED_EXCLUDE = 5        # pkg excludes installed pkg
_TRIM_INSTALLED_INC = 6            # not allowed by installed pkg incorporation
_TRIM_INSTALLED_NEWER = 7          # newer version installed already
_TRIM_INSTALLED_ORIGIN = 8         # installed version in image too old
_TRIM_INSTALLED_ROOT_ORIGIN = 9    # installed version in root image too old
_TRIM_PARENT_MISSING = 10          # parent image must have this pkg too
_TRIM_PARENT_NEWER = 11            # parent image has newer version
_TRIM_PARENT_OLDER = 12            # parent image has older version
_TRIM_PARENT_PUB = 13              # parent image has different publisher
_TRIM_PROPOSED_INC = 14            # not allowed by requested pkg incorporation
_TRIM_PROPOSED_PUB = 15            # didn't match requested publisher
_TRIM_PROPOSED_VER = 16            # didn't match requested version
_TRIM_PUB_RANK = 17                # pkg from higher or lower ranked publisher
_TRIM_PUB_STICKY = 18              # pkg publisher != installed pkg publisher
_TRIM_REJECT = 19                  # --reject
_TRIM_UNSUPPORTED = 20             # invalid or unsupported actions
_TRIM_VARIANT = 21                 # unsupported variant (e.g. i386 on sparc)
_TRIM_EXPLICIT_INSTALL = 22        # pkg.depend.explicit-install is true.
_TRIM_SYNCED_INC = 23              # incorporation must be in sync with parent
_TRIM_CPU = 24                     # cpu version requirement
_TRIM_MAX = 25                     # number of trim constants


class DependencyException(Exception):
    """local exception used to pass failure to match
    dependencies in packages out of nested evaluation"""

    def __init__(self, reason_id, reason, fmris=EmptyI):
        Exception.__init__(self)
        self.__fmris = fmris
        self.__reason_id = reason_id
        self.__reason = reason

    @property
    def fmris(self):
        """The FMRIs related to the exception."""
        return self.__fmris

    @property
    def reason_id(self):
        """A constant indicating why the related FMRIs were rejected."""
        return self.__reason_id

    @property
    def reason(self):
        """A string describing why the related FMRIs were rejected."""
        return self.__reason


class PkgSolver:
    """Provides a SAT-based solution solver to determine which packages
    should be installed, updated, or removed to perform a requested
    operation."""

    def __init__(self, cat, installed_dict, pub_ranks, variants, avoids,
        parent_pkgs, progtrack):
        """Create a PkgSolver instance; catalog should contain all
        known pkgs, installed fmris should be a dict of fmris indexed
        by name that define pkgs current installed in the image.
        Pub_ranks dict contains (rank, stickiness, enabled) for each
        publisher.  variants are the current image variants; avoids is
        the set of pkg stems being avoided in the image due to
        administrator action (e.g. --reject, uninstall)."""

        # Value 'DebugValues' is unsubscriptable;
        # pylint: disable=E1136
        # check if we're allowed to use the solver
        if DebugValues["no_solver"]:
            raise RuntimeError("no_solver set, but solver invoked")

        self.__catalog = cat
        self.__known_incs = set()       # stems with incorporate deps
        self.__publisher = {}           # indexed by stem
        self.__possible_dict = defaultdict(list)  # indexed by stem

        #
        # Get rank indexed by pub
        #
        self.__pub_ranks = {}

        # To ease cross-publisher (i.e. consolidation) flag days, treat
        # adjacent, non-sticky publishers as having the same rank so
        # that any of them may be used to satisfy package dependencies.
        last_rank = None
        last_sticky = None
        rank_key = operator.itemgetter(1)
        for p, pstate in sorted(pub_ranks.items(), key=rank_key):
            rank, sticky, enabled = pstate
            if sticky or sticky != last_sticky:
                last_rank = rank
                last_sticky = sticky
            else:
                rank = last_rank
            self.__pub_ranks[p] = (rank, sticky, enabled)

        self.__depend_ts = False        # flag used to indicate whether
                                        # any dependencies with
                                        # timestamps were seen; used in
                                        # error output generation
        self.__trim_dict = defaultdict(set) # fmris trimmed from
                                        # consideration

        self.__installed_dict = installed_dict.copy() # indexed by stem
        self.__installed_pkgs = frozenset(self.__installed_dict)
        self.__installed_fmris = frozenset(
            self.__installed_dict.values())

        self.__pub_trim = {}            # pkg names already
                                        # trimmed by pub.
        self.__removal_fmris = set()    # installed fmris we're
                                        # going to remove

        self.__req_pkg_names = set()    # package names that must be
                                        # present in solution by spec.
        for f in self.__installed_fmris: # record only sticky pubs
            pub = f.publisher
            if self.__pub_ranks[pub][1]:
                self.__publisher[f.pkg_name] = pub

        self.__id2fmri = {}             # map ids -> fmris
        self.__fmri2id = {}             # and reverse

        self.__solver = pkg.solver.msat_solver()

        self.__progtrack = progtrack    # progress tracker
        self.__progitem = None          # progress tracker plan item

        self.__addclause_failure = False

        self.__variant_dict = {}        # fmris -> variant cache
        self.__variants = variants      # variants supported by image

        self.__cache = {}
        self.__actcache = {}
        self.__trimdone = False         # indicate we're finished
                                        # trimming
        self.__fmri_state = {}          # cache of obsolete, renamed
                                        # bits so we can print something
                                        # reasonable
        self.__state = SOLVER_INIT
        self.__iterations = 0
        self.__clauses     = 0
        self.__variables   = 0
        self.__subphasename = None
        self.__timings = []
        self.__start_time = 0
        self.__inc_list = []
        self.__dependents = None
        # set of fmris installed in root image; used for origin
        # dependencies
        self.__root_fmris = None
        # set of stems avoided by admin (e.g. --reject, uninstall)
        self.__avoid_set = avoids.copy()
        # set of stems avoided by solver due to dependency constraints
        # (e.g. all fmris that satisfy group dependency trimmed); this
        # intentionally starts empty for every new solver invocation and
        # is only stored in image configuration for diagnostic purposes.
        self.__implicit_avoid_set = set()
        # set of obsolete stems
        self.__obs_set = None
        # set of stems we're rejecting
        self.__reject_set = set()
        # pkgs that have parent deps
        self.__linked_pkgs = set()

        # Internal cache of created fmri objects.  Used so that the same
        # PkgFmri doesn't need to be created more than once.  This isn't
        # a weakref dictionary because in two of the four places where
        # PkgFmri's are created, the name is extracted and the PkgFmri
        # object is immediately discarded.
        self.__fmridict = {}

        # Packages with explicit install action set to true.
        self.__expl_install_dict = {}

        assert isinstance(parent_pkgs, (type(None), frozenset))
        self.__parent_pkgs = parent_pkgs
        self.__parent_dict = dict()
        if self.__parent_pkgs is not None:
            self.__parent_dict = dict([
                (f.pkg_name, f)
                for f in self.__parent_pkgs
            ])

        # cache of firmware and cpu dependencies
        self.__firmware = Driver()
        self.__cpu = Cpu()

        self.__triggered_ops = {
            PKG_OP_UNINSTALL : {
                PKG_OP_UPDATE    : set(),
                PKG_OP_UNINSTALL : set(),
            },
        }

        self.__allowed_downgrades = set()  # allowed downrev FMRIs
        self.__dg_incorp_cache = {}        # cache for downgradable
                                           # incorp deps

    def __str__(self):
        s = "Solver: ["
        if self.__state in [SOLVER_FAIL, SOLVER_SUCCESS]:
            s += (" Variables: {0:d} Clauses: {1:d} Iterations: "
                "{2:d}").format(self.__variables, self.__clauses,
                    self.__iterations)
        s += " State: {0}]".format(self.__state)

        s += "\nTimings: ["
        s += ", ".join([
            "{0}: {1: 6.3f}".format(*a)
            for a in self.__timings
        ])
        s += "]"

        if self.__inc_list:
            incs = "\n\t".join([str(a) for a in self.__inc_list])
        else:
            incs = "None"

        s += "\nMaintained incorporations: {0}\n".format(incs)

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
        self.__progtrack = None
        self.__addclause_failure = False
        self.__variant_dict = None
        self.__variants = None
        self.__cache = None
        self.__actcache = None
        self.__trimdone = None
        self.__fmri_state = None
        self.__start_time = None
        self.__dependents = None
        self.__fmridict = {}
        self.__firmware = None
        self.__cpu = None
        self.__allowed_downgrades = None
        self.__dg_incorp_cache = None
        self.__linked_pkgs = set()

        # Value 'DebugValues' is unsubscriptable;
        # pylint: disable=E1136
        if DebugValues["plan"]:
            # Remaining data must be kept.
            return rval

        self.__trim_dict = None
        return rval

    def __progress(self):
        """Bump progress tracker to indicate processing is active."""
        assert self.__progitem
        self.__progtrack.plan_add_progress(self.__progitem)

    def __start_subphase(self, subphase=None, reset=False):
        """Add timing records and tickle progress tracker.  Ends
        previous subphase if ongoing."""
        if reset:
            self.__timings = []
        if self.__subphasename is not None:
            self.__end_subphase()
        self.__start_time = time.time()
        self.__subphasename = "phase {0:d}".format(subphase)
        self.__progress()

    def __end_subphase(self):
        """Mark the end of a solver subphase, recording time taken."""
        now = time.time()
        self.__timings.append((self.__subphasename,
            now - self.__start_time))
        self.__start_time = None
        self.__subphasename = None

    def __trim_frozen(self, existing_freezes):
        """Trim any packages we cannot update due to freezes."""
        for f, r, _t in existing_freezes:
            if r:
                reason = (N_("This version is excluded by a "
                    "freeze on {0} at version {1}.  The "
                    "reason for the freeze is: {2}"),
                    (f.pkg_name, f.version.get_version(
                        include_build=False), r))
            else:
                reason = (N_("This version is excluded by a "
                    "freeze on {0} at version {1}."),
                    (f.pkg_name, f.version.get_version(
                        include_build=False)))
            self.__trim(self.__comb_auto_fmris(f, dotrim=False)[1],
                _TRIM_FREEZE, reason)

    def __raise_solution_error(self, no_version=EmptyI, no_solution=EmptyI):
        """Raise a plan exception due to solution errors."""

        solver_errors = None
        # Value 'DebugValues' is unsubscriptable;
        # pylint: disable=E1136
        if DebugValues["plan"]:
            solver_errors = self.get_trim_errors()
        raise api_errors.PlanCreationException(no_solution=no_solution,
            no_version=no_version, solver_errors=solver_errors)

    def __trim_proposed(self, proposed_dict):
        """Remove any versions from proposed_dict that are in trim_dict
        and raise an exception if no matching version of a proposed
        package can be installed at this point."""

        if proposed_dict is None:
            # Nothing to do.
            return

        # Used to de-dup errors.
        already_seen = set()

        ret = []
        for name in proposed_dict:
            tv = self.__dotrim(proposed_dict[name])
            if tv:
                proposed_dict[name] = tv
                continue

            ret.extend([_("No matching version of {0} can be "
                "installed:").format(name)])
            ret.extend(self.__fmri_list_errors(proposed_dict[name],
                already_seen=already_seen))
            # continue processing and accumulate all errors
        if ret:
            self.__raise_solution_error(no_version=ret)

    def __set_removed_and_required_packages(self, rejected, proposed=None):
        """Sets the list of package to be removed from the image, the
        list of packages to reject, the list of packages to avoid
        during the operation, and the list of packages that must not be
        removed from the image.

        'rejected' is a set of package stems to reject.

        'proposed' is an optional set of FMRI objects representing
        packages to install or update.

        Upon return:
          * self.__removal_fmris will contain the list of FMRIs to be
            removed from the image due to user request or due to past
            bugs that caused wrong variant to be installed by mistake.

          * self.__reject_set will contain the list of packages to avoid
            or that were rejected by user request as appropriate."""

        if proposed is None:
            proposed = set()
        else:
            # remove packages to be installed from avoid sets
            self.__avoid_set -= proposed
            self.__implicit_avoid_set -= proposed

        self.__removal_fmris |= set([
            self.__installed_dict[name]
            for name in rejected
            if name in self.__installed_dict
        ] + [
            f
            for f in self.__installed_fmris
            if not self.__trim_nonmatching_variants(f)
        ])

        self.__reject_set = rejected

        # trim fmris that user explicitly disallowed
        for name in rejected:
            self.__trim(self.__get_catalog_fmris(name),
                _TRIM_REJECT,
                N_("This version rejected by user request"))

        self.__req_pkg_names = (self.__installed_pkgs |
            proposed) - rejected
        self.__req_pkg_names -= set(
            f.pkg_name
            for f in self.__removal_fmris
        )

    def __set_proposed_required(self, proposed_dict, excludes):
        """Add the common set of conditional, group, and require
        dependencies of proposed packages to the list of package stems
        known to be a required part of the solution.  This will improve
        error messaging if no solution is found."""

        if proposed_dict is None:
            return

        req_dep_names = set()
        for name in proposed_dict:
            # Find intersection of the set of conditional, group,
            # and require dependencies for all proposed versions of
            # the proposed package.  The result is the set of
            # package stems we know will be required to be part of
            # the solution.
            comm_deps = None
            propvers = set(self.__dotrim(proposed_dict[name]))
            for f in propvers:
                prop_deps = set(
                    dname for (dtype, dname) in (
                        (da.attrs["type"],
                            pkg.fmri.extract_pkg_name(
                                da.attrs["fmri"]))
                        for da in self.__get_dependency_actions(
                            f, excludes)
                        if da.attrs["type"] == "conditional" or
                            da.attrs["type"] == "group" or
                            da.attrs["type"] == "require"
                    )
                    if dtype != "group" or
                        (dname not in self.__avoid_set and
                         dname not in self.__reject_set)
                )

                if comm_deps is None:
                    comm_deps = prop_deps
                else:
                    comm_deps &= prop_deps

            if comm_deps:
                req_dep_names |= comm_deps

        self.__req_pkg_names = frozenset(req_dep_names |
            self.__req_pkg_names)

    def __update_possible_closure(self, possible, excludes,
        full_trim=False, filter_explicit=True, proposed_dict=None):
        """Update the provided possible set of fmris with the transitive
        closure of dependencies that can be satisfied, trimming those
        packages that cannot be installed.

        'possible' is a set of FMRI objects representing all possible
        versions of packages to consider for the operation.

        'full_trim' is an optional boolean indicating whether a full
        trim of the dependency graph should be performed.  This is NOT
        required for the solver to find a solution.  Trimming is only
        needed to reduce the size of clauses and to provide error
        messages.  This requires multiple passes to determine if the
        transitive closure of dependencies can be satisfied.  This is
        not required for correctness (and it greatly increases runtime).
        However, it does greatly improve error messaging for some error
        cases.

        'filter_explicit' is an optional boolean indicating whether
        packages with pkg.depend.explicit-install set to true will be
        filtered out.

        'proposed_dict' contains user specified FMRI objects indexed by
        pkg_name that should be installed or updated within an image.

        An example of a case where full_trim will be useful (dueling
        incorporations):

        Installed:
          entire
            incorporates java-7-incorporation
        Proposed:
          osnet-incorporation
            incorporates system/resource-mgmt/dynamic-resource-pools
          system/resource-mgmt/dynamic-resource-pools
            requires new version of java not allowed by installed
              java-7-incorporation"""

        first = True
        while True:
            tsize = len(self.__trim_dict)
            res = self.__generate_dependency_closure(
                possible, excludes=excludes, full_trim=full_trim,
                filter_explicit=filter_explicit,
                proposed_dict=proposed_dict)
            if first:
                # The first pass will return the transitive
                # closure of all dependencies; subsequent passes
                # are only done for trimming, so need to update
                # the possible set only on first pass.
                possible.update(res)
                first = False

            nsize = len(self.__trim_dict)
            if not full_trim or nsize == tsize:
                # Nothing more to trim.
                break

        # Remove trimmed items from possible_set.
        possible.difference_update(self.__trim_dict.keys())

    def __enforce_unique_packages(self, excludes):
        """Constrain the solver solution so that only one version of
        each package can be installed and generate dependency clauses
        for possible packages."""

        # Generate clauses for only one version of each package, and
        # for dependencies for each package.  Do so for all possible
        # fmris.
        for name in self.__possible_dict:
            self.__progress()
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

    def __generate_operation_clauses(self, proposed=None,
        proposed_dict=None):
        """Generate initial solver clauses for the proposed packages (if
        any) and installed packages.

        'proposed' is a set of FMRI objects representing packages to
        install or update.

        'proposed_dict' contains user specified FMRI objects indexed by
        pkg_name that should be installed or updated within an image."""

        assert ((proposed is None and proposed_dict is None) or
            (proposed is not None and proposed_dict is not None))

        if proposed is None:
            proposed = set()
        if proposed_dict is None:
            proposed_dict = EmptyDict

        # Generate clauses for proposed and installed pkgs note that we
        # create clauses that require one of the proposed pkgs to work;
        # this allows the possible_set to always contain the existing
        # pkgs.
        for name in proposed_dict:
            self.__progress()
            self.__addclauses(
                self.__gen_one_of_these_clauses(
                    set(proposed_dict[name]) &
                    set(self.__possible_dict[name])))

        for name in (self.__installed_pkgs - proposed -
            self.__reject_set - self.__avoid_set):
            self.__progress()

            if (self.__installed_dict[name] in
                self.__removal_fmris):
                # we're uninstalling this package
                continue

            if name in self.__possible_dict:
                self.__addclauses(
                    self.__gen_one_of_these_clauses(
                        self.__possible_dict[name]))

    def __begin_solve(self):
        """Prepares solver for solution creation returning a
        ProgressTracker object to be used for the operation."""

        # Once solution has been returned or failure has occurred, a new
        # solver must be used.
        assert self.__state == SOLVER_INIT
        self.__state = SOLVER_OXY

        pt = self.__progtrack
        # Check to see if we were invoked by solve_uninstall, in
        # which case we don't want to restart what we've already
        # started.
        if self.__progitem is None:
            self.__progitem = pt.PLAN_SOLVE_SETUP
            pt.plan_start(pt.PLAN_SOLVE_SETUP)
        self.__start_subphase(1, reset=True)

        return pt

    def __end_solve(self, solution, excludes):
        """Returns the solution result to the caller after completing
        all necessary solution cleanup."""

        pt = self.__progtrack
        self.__end_subphase()  # end the last subphase.
        pt.plan_done(pt.PLAN_SOLVE_SOLVER)
        return self.__cleanup((self.__elide_possible_renames(solution,
            excludes), (self.__avoid_set, self.__implicit_avoid_set,
                self.__obs_set)))

    def __assert_installed_allowed(self, excludes, proposed=None):
        """Raises a PlanCreationException if the proposed operation
        would require the removal of installed packages that are not
        marked for removal by the proposed operation."""

        if proposed is None:
            proposed = set()

        uninstall_fmris = []
        for name in (self.__installed_pkgs - proposed -
            self.__reject_set - self.__avoid_set):
            self.__progress()

            if (self.__installed_dict[name] in
                self.__removal_fmris):
                # we're uninstalling this package
                continue

            if name in self.__possible_dict:
                continue

            # no version of this package is allowed
            uninstall_fmris.append(self.__installed_dict[name])

        # Used to de-dup errors.
        already_seen = set()
        ret = []
        msg = N_("Package '{0}' must be uninstalled or upgraded "
            "if the requested operation is to be performed.")

        # First check for solver failures caused by missing parent
        # dependencies.  We do this because missing parent dependency
        # failures cause other cascading failures, so it's better to
        # just emit these failures first, have the user fix them, and
        # have them re-run the operation, so then we can provide more
        # concise error output about other problems.
        for fmri in uninstall_fmris:
            # Unused variable; pylint: disable=W0612
            for reason_id, reason_t, fmris in \
                self.__trim_dict.get(fmri, EmptyI):
                if reason_id == _TRIM_PARENT_MISSING:
                    break
            else:
                continue
            res = self.__fmri_list_errors([fmri],
                already_seen=already_seen)
            assert res
            ret.extend([msg.format(fmri.pkg_name)])
            ret.extend(res)

        if ret:
            self.__raise_solution_error(no_version=ret)

        for fmri in uninstall_fmris:
            flist = [fmri]
            if fmri in self.__linked_pkgs:
                depend_self = any(
                    da
                    for da in self.__get_dependency_actions(
                        fmri, excludes)
                    if da.attrs["type"] == "parent" and
                    pkg.actions.depend.DEPEND_SELF in
                        da.attrlist("fmri")
                )

                if depend_self:
                    pf = self.__parent_dict.get(
                        fmri.pkg_name)
                    if pf and pf != fmri:
                        # include parent's version of
                        # parent-constrained packages in
                        # error messaging for clarity if
                        # different
                        flist.append(pf)

            res = self.__fmri_list_errors(flist,
                already_seen=already_seen)

            # If no errors returned, that implies that all of the
            # reasons the FMRI was rejected aren't interesting.
            if res:
                ret.extend([msg.format(fmri.pkg_name)])
                ret.extend(res)

        if ret:
            self.__raise_solution_error(no_version=ret)

    def __assert_trim_errors(self, possible_set, excludes, proposed=None,
        proposed_dict=None):
        """Raises a PlanCreationException if any further trims would
        prevent the installation or update of proposed or
        installed/required packages.

        'proposed' is an optional set of FMRI objects representing
        packages to install or update.

        'proposed_dict' contains user specified FMRIs indexed by
        pkg_name that should be installed within an image.

        'possible_set' is the set of FMRIs potentially allowed for use
        in the proposed operation."""

        # make sure all package trims appear
        self.__trimdone = False

        # Ensure required dependencies of proposed packages are flagged
        # to improve error messaging when parsing the transitive
        # closure of all dependencies.
        self.__set_proposed_required(proposed_dict, excludes)

        # First, perform a full trim of the package version space; this
        # is normally skipped for performance reasons as it's not
        # required for correctness.
        self.__update_possible_closure(possible_set, excludes,
            full_trim=True, filter_explicit=False,
            proposed_dict=proposed_dict)

        # Now try re-asserting that proposed (if any) and installed
        # packages are allowed after the trimming; these calls will
        # raise an exception if all the proposed or any of the
        # installed/required packages are trimmed.
        self.__set_proposed_required(proposed_dict, excludes)
        self.__trim_proposed(proposed_dict)
        self.__assign_possible(possible_set)
        self.__assert_installed_allowed(excludes, proposed=proposed)

    def __raise_install_error(self, exp, inc_list, proposed_dict,
        possible_set, excludes):
        """Private logic for solve_install() to process a
        PlanCreationException and re-raise as appropriate.

        'exp' is the related exception object raised by the solver when
        no solution was found.

        'inc_list' is a list of package FMRIs representing installed
        incorporations that are being maintained.

        'proposed_dict' contains user specified FMRIs indexed by
        pkg_name that should be installed within an image.

        'possible_set' is the set of FMRIs potentially allowed for use
        in the proposed operation.
        """

        # Before making a guess, apply extra trimming to see if we can
        # reject the operation based on changing packages.
        self.__assert_trim_errors(possible_set, excludes,
            proposed_dict=proposed_dict)

        # Despite all of the trimming done, we still don't know why the
        # solver couldn't find a solution, so make a best effort guess
        # at the reason why.
        info = []
        incs = []

        incs.append("")
        if inc_list:
            incs.append("maintained incorporations:")
            skey = operator.attrgetter('pkg_name')
            for il in sorted(inc_list, key=skey):
                incs.append("  {0}".format(il.get_short_fmri()))
        else:
            incs.append("maintained incorporations: None")
        incs.append("")

        ms = self.__generate_dependency_errors([
            b for a in proposed_dict.values()
            for b in a
        ], excludes=excludes)
        if ms:
            info.append("")
            info.append(_("Plan Creation: dependency error(s) in "
                "proposed packages:"))
            info.append("")
            for s in ms:
                info.append("  {0}".format(s))

        ms = self.__check_installed()
        if ms:
            info.append("")
            info.append(_("Plan Creation: Errors in installed "
                "packages due to proposed changes:"))
            info.append("")
            for s in ms:
                info.append("  {0}".format(s))

        if not info: # both error detection methods insufficent.
            info.append(_("Plan Creation: Package solver is "
                "unable to compute solution."))
            info.append(_("Dependency analysis is unable to "
                "determine exact cause."))
            info.append(_("Try specifying expected results to "
                "obtain more detailed error messages."))
            info.append(_("Include specific version of packages "
                "you wish installed."))
        exp.no_solution = incs + info

        # Value 'DebugValues' is unsubscriptable;
        # pylint: disable=E1136
        if DebugValues["plan"]:
            exp.solver_errors = self.get_trim_errors()
        raise exp

    def add_triggered_op(self, trigger_op, exec_op, fmris):
        """Add the set of FMRIs in 'fmris' to the internal dict of
        pkg-actuators. 'trigger_op' is the operation which triggered
        the pkg change, 'exec_op' is the operation which is supposed to
        be executed."""

        assert trigger_op in self.__triggered_ops, "{0} is " \
            "not a valid trigger op for pkg actuators".format(
            trigger_op)
        assert exec_op in self.__triggered_ops[trigger_op], "{0} is " \
            "not a valid execution op for pkg actuators".format(exec_op)
        assert isinstance(fmris, set)

        self.__triggered_ops[trigger_op][exec_op] |= fmris

    def solve_install(self, existing_freezes, proposed_dict,
        new_variants=None, excludes=EmptyI,
        reject_set=frozenset(), trim_proposed_installed=True,
        relax_all=False, ignore_inst_parent_deps=False,
        exact_install=False, installed_dict_tmp=EmptyDict):
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

        'ignore_inst_parent_deps' indicates if the solver should
        ignore parent dependencies for installed packages.  This
        allows us to modify images with unsatisfied parent
        dependencies (i.e., out-of-sync images).  Any packaging
        operation which needs to guarantee that we have an in-sync
        image (for example, sync-linked operations, or any recursive
        packaging operations) should NOT enable this behavior.

        'exact_install' is a flag to indicate whether we treat the
        current image as an empty one. Any previously installed
        packages that are not either specified in proposed_dict or
        are a dependency (require, origin and parent dependencies)
        of those packages will be removed.

        'installed_dict_tmp' a dictionary containing the current
        installed FMRIs indexed by pkg_name. Used when exact_install
        is on."""

        pt = self.__begin_solve()

        # reject_set is a frozenset(), need to make copy to modify
        r_set = set(reject_set)
        for f in self.__triggered_ops[PKG_OP_UNINSTALL][PKG_OP_UPDATE]:
            if f.pkg_name in proposed_dict:
                proposed_dict[f.pkg_name].append(f)
            else:
                proposed_dict[f.pkg_name] = [f]
        for f in \
            self.__triggered_ops[PKG_OP_UNINSTALL][PKG_OP_UNINSTALL]:
            r_set.add(f.pkg_name)
        # re-freeze reject set
        reject_set = frozenset(r_set)

        proposed_pkgs = set(proposed_dict)

        if new_variants:
            self.__variants = new_variants

            #
            # Entire packages can be tagged with variants thereby
            # making those packages uninstallable in certain
            # images.  So if we're changing variants such that
            # some currently installed packages are becoming
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
                    proposed_dict[name][0].publisher

        # Determine which packages are to be removed, rejected, and
        # avoided and also determine which ones must not be removed
        # during the operation.
        self.__set_removed_and_required_packages(rejected=reject_set,
            proposed=proposed_pkgs)
        self.__progress()

        # find list of incorps we don't let change as a side effect of
        # other changes; exclude any specified on command line if the
        # proposed version is already installed and is not being removed
        # translate proposed_dict into a set
        if relax_all:
            relax_pkgs = self.__installed_pkgs
        else:
            relax_pkgs = set(
                name
                for name in proposed_pkgs
                if not any(
                    f for f in proposed_dict[name]
                    if len(proposed_dict[name]) == 1 and
                        f in (self.__installed_fmris -
                            self.__removal_fmris)
                )
            )
            relax_pkgs |= \
                self.__installed_unsatisfied_parent_deps(excludes,
                    ignore_inst_parent_deps)

        inc_list, con_lists = self.__get_installed_unbound_inc_list(
            relax_pkgs, excludes=excludes)
        self.__inc_list = inc_list

        self.__start_subphase(2)
        # generate set of possible fmris
        #
        # ensure existing pkgs stay installed; explicitly add in
        # installed fmris in case publisher change has occurred and
        # some pkgs aren't part of new publisher
        possible_set = set()
        self.__allowed_downgrades = set()
        for f in self.__installed_fmris - self.__removal_fmris:
            possible_set |= self.__comb_newer_fmris(f)[0] | set([f])

        # Add the proposed fmris, populate self.__expl_install_dict and
        # check for allowed downgrades.
        self.__expl_install_dict = defaultdict(list)
        for name, flist in proposed_dict.items():
            possible_set.update(flist)
            for f in flist:
                self.__progress()
                self.__allowed_downgrades |= \
                    self.__allow_incorp_downgrades(f,
                    excludes=excludes)
                if self.__is_explicit_install(f):
                    self.__expl_install_dict[name].append(f)

        # For linked image sync we have to analyze all pkgs of the
        # possible_set because no proposed pkgs will be given. However,
        # that takes more time so only do this for syncs. The relax_all
        # flag is an indicator of a sync operation.
        if not proposed_dict.values() and relax_all:
            for f in possible_set:
                self.__progress()
                self.__allowed_downgrades |= \
                    self.__allow_incorp_downgrades(f,
                    excludes=excludes, relax_all=True)

        possible_set |= self.__allowed_downgrades

        self.__start_subphase(3)
        # If requested, trim any proposed fmris older than those of
        # corresponding installed packages.
        candidate_fmris = self.__installed_fmris - \
            self.__removal_fmris

        for f in candidate_fmris:
            self.__progress()
            if not trim_proposed_installed and \
                f.pkg_name in proposed_dict:
                # Don't trim versions if newest version in
                # proposed dict is older than installed
                # version.
                verlist = proposed_dict[f.pkg_name]
                if verlist[-1].version < f.version:
                    # Assume downgrade is intentional.
                    continue
            valid_trigger = False
            for tf in self.__triggered_ops[
                PKG_OP_UNINSTALL][PKG_OP_UPDATE]:
                if tf.pkg_name == f.pkg_name:
                    self.__trim_older(tf)
                    valid_trigger = True
            if valid_trigger:
                continue

            self.__trim_older(f)

        # trim fmris we excluded via proposed_fmris
        for name in proposed_dict:
            self.__progress()
            self.__trim(set(self.__get_catalog_fmris(name)) -
                set(proposed_dict[name]),
                _TRIM_PROPOSED_VER,
                N_("This version excluded by specified "
                    "installation version"))
            # trim packages excluded by incorps in proposed.
            self.__trim_recursive_incorps(proposed_dict[name],
                excludes, _TRIM_PROPOSED_INC)

        # Trim packages with unsatisfied parent dependencies.  For any
        # remaining allowable linked packages check if they are in
        # relax_pkgs.  (Which means that either a version of them was
        # requested explicitly on the command line or a version of them
        # is installed which has unsatisfied parent dependencies and
        # needs to be upgraded.)  In that case add the allowable
        # packages to possible_linked so we can call
        # __trim_recursive_incorps() on them to trim out more packages
        # that may be disallowed due to synced incorporations.
        if self.__is_child():
            possible_linked = defaultdict(set)
            for f in possible_set.copy():
                self.__progress()
                if not self.__trim_nonmatching_parents(f,
                    excludes, ignore_inst_parent_deps):
                    possible_set.remove(f)
                    continue
                if (f in self.__linked_pkgs and
                    f.pkg_name in relax_pkgs):
                    possible_linked[f.pkg_name].add(f)
            for name in possible_linked:
                # calling __trim_recursive_incorps can be
                # expensive so don't call it for versions except
                # the one currently installed in the parent if
                # it has been proposed.
                if name in proposed_dict:
                    pf = self.__parent_dict.get(name)
                    possible_linked[name] -= \
                        set(proposed_dict[name]) - \
                        set([pf])
                if not possible_linked[name]:
                    continue
                self.__progress()
                self.__trim_recursive_incorps(
                    list(possible_linked[name]),
                    excludes, _TRIM_SYNCED_INC)
            del possible_linked

        self.__start_subphase(4)
        # now trim pkgs we cannot update due to maintained
        # incorporations
        for i, flist in zip(inc_list, con_lists):
            reason = (N_("This version is excluded by installed "
                "incorporation {0}"), (i.get_short_fmri(
                    anarchy=True, include_scheme=False),))
            self.__trim(self.__comb_auto_fmris(i)[1],
                _TRIM_INSTALLED_INC, reason)
            for f in flist:
                # dotrim=False here as we only want to trim
                # packages that don't satisfy the incorporation.
                self.__trim(self.__comb_auto_fmris(f,
                    dotrim=False)[1], _TRIM_INSTALLED_INC,
                    reason)

        self.__start_subphase(5)
        # now trim any pkgs we cannot update due to freezes
        self.__trim_frozen(existing_freezes)

        self.__start_subphase(6)
        # elide any proposed versions that don't match variants (arch
        # usually)
        for name in proposed_dict:
            for fmri in proposed_dict[name]:
                self.__trim_nonmatching_variants(fmri)

        self.__start_subphase(7)
        # remove any versions from proposed_dict that are in trim_dict
        try:
            self.__trim_proposed(proposed_dict)
        except api_errors.PlanCreationException as exp:
            # One or more proposed packages have been rejected.
            self.__raise_install_error(exp, inc_list, proposed_dict,
                set(), excludes)

        self.__start_subphase(8)

        # Ensure required dependencies of proposed packages are flagged
        # to improve error messaging when parsing the transitive
        # closure of all dependencies.
        self.__set_proposed_required(proposed_dict, excludes)

        # Update the set of possible fmris with the transitive closure
        # of all dependencies.
        self.__update_possible_closure(possible_set, excludes,
            proposed_dict=proposed_dict)

        self.__start_subphase(9)
        # trim any non-matching variants, origins or parents
        for f in possible_set:
            self.__progress()
            if not self.__trim_nonmatching_parents(f, excludes,
                ignore_inst_parent_deps):
                continue
            if not self.__trim_nonmatching_variants(f):
                continue
            self.__trim_nonmatching_origins(f, excludes,
                exact_install=exact_install,
                installed_dict_tmp=installed_dict_tmp)

        self.__start_subphase(10)
        # remove all trimmed fmris from consideration
        possible_set.difference_update(self.__trim_dict.keys())
        # remove any versions from proposed_dict that are in trim_dict
        # as trim dict has been updated w/ missing dependencies
        try:
            self.__trim_proposed(proposed_dict)
        except api_errors.PlanCreationException as exp:
            # One or more proposed packages have been rejected.
            self.__raise_install_error(exp, inc_list, proposed_dict,
                possible_set, excludes)

        self.__start_subphase(11)
        #
        # Generate ids, possible_dict for clause generation.  Prepare
        # the solver for invocation.
        #
        self.__assign_fmri_ids(possible_set)

        # Constrain the solution so that only one version of each
        # package can be installed.
        self.__enforce_unique_packages(excludes)

        self.__start_subphase(12)
        # Add proposed and installed packages to solver.
        self.__generate_operation_clauses(proposed=proposed_pkgs,
            proposed_dict=proposed_dict)
        try:
            self.__assert_installed_allowed(excludes,
                proposed=proposed_pkgs)
        except api_errors.PlanCreationException as exp:
            # One or more installed packages can't be retained or
            # upgraded.
            self.__raise_install_error(exp, inc_list, proposed_dict,
                possible_set, excludes)

        pt.plan_done(pt.PLAN_SOLVE_SETUP)

        self.__progitem = pt.PLAN_SOLVE_SOLVER
        pt.plan_start(pt.PLAN_SOLVE_SOLVER)
        self.__start_subphase(13)
        # save a solver instance so we can come back here
        # this is where errors happen...
        saved_solver = self.__save_solver()
        try:
            saved_solution = self.__solve()
        except api_errors.PlanCreationException as exp:
            # no solution can be found.
            self.__raise_install_error(exp, inc_list, proposed_dict,
                possible_set, excludes)

        self.__start_subphase(14)
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

        self.__start_subphase(15)
        # save context
        saved_solver = self.__save_solver()

        saved_solution = self.__solve(older=True)

        self.__start_subphase(16)
        # Now we have the oldest possible original fmris
        # but we may have some that are not original
        # Since we want to move as far forward as possible
        # when we have to move a package, fix the originals
        # and drive forward again w/ the remainder
        self.__restore_solver(saved_solver)

        for fmri in saved_solution & self.__installed_fmris:
            self.__addclauses(
                self.__gen_one_of_these_clauses([fmri]))

        solution = self.__solve()
        self.__progress()
        solution = self.__update_solution_set(solution, excludes)

        return self.__end_solve(solution, excludes)

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

        pt = self.__begin_solve()

        # Determine which packages are to be removed, rejected, and
        # avoided and also determine which ones must not be removed
        # during the operation.
        self.__set_removed_and_required_packages(rejected=reject_set)
        self.__progress()

        if self.__is_child():
            synced_parent_pkgs = \
                self.__installed_unsatisfied_parent_deps(excludes,
                    False)
        else:
            synced_parent_pkgs = frozenset()

        self.__start_subphase(2)
        # generate set of possible fmris
        possible_set = set()
        for f in self.__installed_fmris - self.__removal_fmris:
            self.__progress()
            matching = self.__comb_newer_fmris(f)[0]
            if not matching:            # disabled publisher...
                matching = set([f]) # staying put is an option
            possible_set |= matching

        self.__allowed_downgrades = set()
        for f in possible_set:
            self.__allowed_downgrades |= \
                self.__allow_incorp_downgrades(f, excludes=excludes,
                    relax_all=True)
        possible_set |= self.__allowed_downgrades

        # trim fmris we cannot install because they're older
        for f in self.__installed_fmris:
            self.__progress()
            self.__trim_older(f)

        # now trim any pkgs we cannot update due to freezes
        self.__trim_frozen(existing_freezes)

        # Trim packages with unsatisfied parent dependencies.  Then
        # for packages with satisfied parent dependenices (which will
        # include incorporations), call __trim_recursive_incorps() to
        # trim out more packages that are disallowed due to the synced
        # incorporations.
        if self.__is_child():
            possible_linked = defaultdict(set)
            for f in possible_set.copy():
                self.__progress()
                if not self.__trim_nonmatching_parents(f,
                    excludes):
                    possible_set.remove(f)
                    continue
                if (f in self.__linked_pkgs and
                    f.pkg_name not in synced_parent_pkgs):
                    possible_linked[f.pkg_name].add(f)
            for name in possible_linked:
                self.__progress()
                self.__trim_recursive_incorps(
                    list(possible_linked[name]), excludes,
                    _TRIM_SYNCED_INC)
            del possible_linked

        self.__start_subphase(3)
        # Update the set of possible FMRIs with the transitive closure
        # of all dependencies.
        self.__update_possible_closure(possible_set, excludes)

        # trim any non-matching origins or parents
        for f in possible_set:
            if self.__trim_nonmatching_parents(f, excludes):
                if self.__trim_nonmatching_variants(f):
                    self.__trim_nonmatching_origins(f,
                        excludes)

        self.__start_subphase(4)

        # remove all trimmed fmris from consideration
        possible_set.difference_update(self.__trim_dict.keys())

        #
        # Generate ids, possible_dict for clause generation.  Prepare
        # the solver for invocation.
        #
        self.__assign_fmri_ids(possible_set)

        # Constrain the solution so that only one version of each
        # package can be installed.
        self.__enforce_unique_packages(excludes)

        self.__start_subphase(5)
        # Add installed packages to solver.
        self.__generate_operation_clauses()
        try:
            self.__assert_installed_allowed(excludes)
        except api_errors.PlanCreationException:
            # Attempt a full trim to see if we can raise a sensible
            # error.  If not, re-raise.
            self.__assert_trim_errors(possible_set, excludes)
            raise

        pt.plan_done(pt.PLAN_SOLVE_SETUP)

        self.__progitem = pt.PLAN_SOLVE_SOLVER
        pt.plan_start(pt.PLAN_SOLVE_SOLVER)
        self.__start_subphase(6)
        try:
            solution = self.__solve()
        except api_errors.PlanCreationException:
            # No solution can be found; attempt a full trim to see
            # if we can raise a sensible error.  If not, re-raise.
            self.__assert_trim_errors(possible_set, excludes)
            raise

        self.__update_solution_set(solution, excludes)

        for f in solution.copy():
            if self.__fmri_is_obsolete(f):
                solution.remove(f)

        # If solution doesn't match installed set of packages, then an
        # upgrade solution was found (heuristic):
        if solution != self.__installed_fmris:
            return self.__end_solve(solution, excludes)

        incorps = self.__get_installed_upgradeable_incorps(
            excludes)
        if not incorps or self.__is_child():
            # If there are no installed, upgradeable incorporations,
            # then assume that no updates were available.  Also if
            # we're a linked image child we may not be able to
            # update to the latest available incorporations due to
            # parent constraints, so don't generate an error.
            return self.__end_solve(solution, excludes)

        # Before making a guess, apply extra trimming to see if we can
        # reject the operation based on changing packages.
        self.__assert_trim_errors(possible_set, excludes)

        # Despite all of the trimming done, we still don't know why the
        # solver couldn't find a solution, so make a best-effort guess
        # at the reason why.
        skey = operator.attrgetter('pkg_name')
        info = []
        info.append(_("No solution found to update to latest available "
            "versions."))
        info.append(_("This may indicate an overly constrained set of "
            "packages are installed."))
        info.append(" ")
        info.append(_("latest incorporations:"))
        info.append(" ")
        info.extend((
            "  {0}".format(f)
            for f in sorted(incorps, key=skey)
        ))
        info.append(" ")

        ms = self.__generate_dependency_errors(incorps,
            excludes=excludes)
        ms.extend(self.__check_installed())

        if ms:
            info.append(_("The following indicates why the system "
                "cannot update to the latest version:"))
            info.append(" ")
            for s in ms:
                info.append("  {0}".format(s))
        else:
            info.append(_("Dependency analysis is unable to "
                "determine the cause."))
            info.append(_("Try specifying expected versions to "
                "obtain more detailed error messages."))

        self.__raise_solution_error(no_solution=info)

    def solve_uninstall(self, existing_freezes, uninstall_list, excludes,
        ignore_inst_parent_deps=False):
        """Compute changes needed for uninstall"""

        self.__begin_solve()

        # generate list of installed pkgs w/ possible renames removed to
        # forestall failing removal due to presence of unneeded renamed
        # pkg
        orig_installed_set = self.__installed_fmris
        renamed_set = orig_installed_set - \
            self.__elide_possible_renames(orig_installed_set, excludes)

        proposed_removals = set(uninstall_list) | renamed_set | \
            self.__triggered_ops[PKG_OP_UNINSTALL][PKG_OP_UNINSTALL]

        # find pkgs which are going to be installed/updated
        triggered_set = set()
        for f in self.__triggered_ops[PKG_OP_UNINSTALL][PKG_OP_UPDATE]:
            triggered_set.add(f)

        # check for dependents
        for pfmri in proposed_removals:
            self.__progress()
            dependents = self.__get_dependents(pfmri, excludes) - \
                proposed_removals

            # Check if any of the dependents are going to be updated
            # to a different version which might not have the same
            # dependency constraints. If so, remove from dependents
            # list.

            # Example:
            # A@1 depends on B
            # A@2 does not depend on B
            #
            # A@1 is currently installed, B is requested for removal
            # -> not allowed
            # pkg actuator updates A to 2
            # -> now removal of B is allowed
            candidates = dict(
                 (tf, f)
                 for f in dependents
                 for tf in triggered_set
                 if f.pkg_name == tf.pkg_name
            )

            for tf in candidates:
                remove = True
                for da in self.__get_dependency_actions(tf,
                    excludes):
                    if da.attrs["type"] != "require":
                        continue
                    pkg_name = pkg.fmri.PkgFmri(
                        da.attrs["fmri"]).pkg_name
                    if pkg_name == pfmri.pkg_name:
                        remove = False
                        break
                if remove:
                    dependents.remove(candidates[tf])

            if dependents:
                raise api_errors.NonLeafPackageException(pfmri,
                    dependents)

        reject_set = set(f.pkg_name for f in proposed_removals)

        # Run it through the solver; with more complex dependencies
        # we're going to be out of luck without it.
        self.__state = SOLVER_INIT # reset to initial state
        return self.solve_install(existing_freezes, {},
            excludes=excludes, reject_set=reject_set,
            ignore_inst_parent_deps=ignore_inst_parent_deps)

    def __update_solution_set(self, solution, excludes):
        """Update avoid sets w/ any missing packages (due to reject).
        Remove obsolete packages from solution.  Keep track of which
        obsolete packages have group dependencies so verify of group
        packages w/ obsolete members works."""

        solution_stems = set(f.pkg_name for f in solution)
        tracked_stems = set()
        for fmri in solution:
            for a in self.__get_dependency_actions(fmri,
                excludes=excludes, trim_invalid=False):
                if (a.attrs["type"] != "group" and
                    a.attrs["type"] != "group-any"):
                    continue

                for t in a.attrlist("fmri"):
                    try:
                        tmp = self.__fmridict[t]
                    except KeyError:
                        tmp = pkg.fmri.PkgFmri(t)
                        self.__fmridict[t] = tmp
                    tracked_stems.add(tmp.pkg_name)

        avoided = (tracked_stems - solution_stems)
        # Add stems omitted by solution and explicitly rejected.
        self.__avoid_set |= avoided & self.__reject_set

        ret = solution.copy()
        obs = set()

        for f in solution:
            if self.__fmri_is_obsolete(f):
                ret.remove(f)
                obs.add(f.pkg_name)

        self.__obs_set = obs & tracked_stems

        # Add stems omitted by solution but not explicitly rejected, not
        # previously avoided, and not avoided due to obsoletion.
        self.__implicit_avoid_set |= avoided - self.__avoid_set - \
            self.__obs_set

        return ret

    def __save_solver(self):
        """Duplicate current current solver state and return it."""
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
            self.__progress()
            self.__iterations += 1

            if self.__iterations > max_iterations:
                break

            solution_vector = self.__get_solution_vector()
            if not solution_vector:
                break

            # prevent the selection of any older pkgs except for
            # those that are part of the set of allowed downgrades;
            for fid in solution_vector:
                pfmri = self.__getfmri(fid)
                matching, remaining = \
                    self.__comb_newer_fmris(pfmri)
                if not older:
                    # without subtraction of allowed
                    # downgrades, an initial solution will
                    # exclude any solutions containing
                    # earlier versions of downgradeable
                    # packages
                    remove = remaining - \
                        self.__allowed_downgrades
                else:
                    remove = matching - set([pfmri]) - \
                        eliminated
                for f in remove:
                    self.__addclauses([[-self.__getid(f)]])

            # prevent the selection of this exact combo;
            # permit [] solution
            self.__addclauses([[-i for i in solution_vector]])

        if not self.__iterations:
            self.__raise_solution_error(no_solution=True)

        self.__state = SOLVER_SUCCESS

        solution = set([self.__getfmri(i) for i in solution_vector])

        return solution

    def __get_solution_vector(self):
        """Return solution vector from solver"""
        return frozenset([
            (i + 1) for i in range(self.__solver.get_variables())
            if self.__solver.dereference(i)
        ])

    def __assign_possible(self, possible_set):
        """Assign __possible_dict of possible package FMRIs by pkg stem
        and mark trimming complete."""

        # generate dictionary of possible pkgs fmris by pkg stem
        self.__possible_dict.clear()

        for f in possible_set:
            self.__possible_dict[f.pkg_name].append(f)
        for name in self.__possible_dict:
            self.__possible_dict[name].sort()
        self.__trimdone = True

    def __assign_fmri_ids(self, possible_set):
        """ give a set of possible fmris, assign ids"""

        self.__assign_possible(possible_set)

        # assign clause numbers (ids) to possible pkgs
        pkgid = 1
        for name in sorted(self.__possible_dict.keys()):
            for fmri in reversed(self.__possible_dict[name]):
                self.__id2fmri[pkgid] = fmri
                self.__fmri2id[fmri] = pkgid
                pkgid += 1

        self.__variables = pkgid - 1

    def __getid(self, fmri):
        """Translate fmri to variable number (id)"""
        return self.__fmri2id[fmri]

    def __getfmri(self, fid):
        """Translate variable number (id) to fmris"""
        return self.__id2fmri[fid]

    def __get_fmris_by_version(self, pkg_name):
        """Cache for catalog entries; helps performance"""
        if pkg_name not in self.__cache:
            self.__cache[pkg_name] = [
                t
                for t in self.__catalog.fmris_by_version(pkg_name)
            ]
        return self.__cache[pkg_name]

    def __get_catalog_fmris(self, pkg_name):
        """ return the list of fmris in catalog for this pkg name"""
        if pkg_name not in self.__pub_trim:
            self.__filter_publishers(pkg_name)

        if self.__trimdone:
            return self.__possible_dict.get(pkg_name, [])

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

        self.__progress()

        tp = (fmri, dotrim, constraint, obsolete_ok) # cache index
        # determine if the data is cacheable or cached:
        if (not self.__trimdone and dotrim) or tp not in self.__cache:
            # use frozensets so callers don't inadvertently update
            # these sets (which may be cached).
            all_fmris = set(self.__get_catalog_fmris(fmri.pkg_name))
            matching = frozenset([
                f
                for f in all_fmris
                if not dotrim or not self.__trim_dict.get(f)
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

        # we're going to return the older packages, so we need
        # to make sure that any trimmed packages are removed
        # from the matching set and added to the non-matching
        # ones.
        trimmed_older = set([
            f
            for f in older
            if self.__trim_dict.get(f)
        ])
        return older - trimmed_older, newer | trimmed_older

    def __comb_auto_fmris(self, fmri, dotrim=True, obsolete_ok=True):
        """Returns tuple of set of fmris that are match within
        CONSTRAINT.AUTO of specified version and set of remaining
        fmris."""
        return self.__comb_common(fmri, dotrim, version.CONSTRAINT_AUTO,
            obsolete_ok)

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
            self.__trim_unsupported(fmri)
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

    def __get_actions(self, fmri, name, excludes=EmptyI,
        trim_invalid=True):
        """Return list of actions of type 'name' for this 'fmri' in
        Catalog.DEPENDENCY section."""

        try:
            return self.__actcache[(fmri, name)]
        except KeyError:
            pass

        try:
            acts = [
                a
                for a in self.__catalog.get_entry_actions(fmri,
                [catalog.Catalog.DEPENDENCY], excludes=excludes)
                if a.name == name
            ]

            if name == "depend":
                for a in acts:
                    if a.attrs["type"] in dep_types:
                        continue
                    raise api_errors.InvalidPackageErrors([
                        "Unknown dependency type {0}".
                        format(a.attrs["type"])])

            self.__actcache[(fmri, name)] = acts
            return acts
        except api_errors.InvalidPackageErrors:
            if not trim_invalid:
                raise

            # Trim package entries that have unparseable action
            # data so that they can be filtered out later.
            self.__fmri_state[fmri] = ("false", "false")
            self.__trim_unsupported(fmri)
            return []

    def __get_dependency_actions(self, fmri, excludes=EmptyI,
        trim_invalid=True):
        """Return list of all dependency actions for this fmri."""

        return self.__get_actions(fmri, "depend",
            excludes=excludes, trim_invalid=trim_invalid)

    def __get_set_actions(self, fmri, excludes=EmptyI,
        trim_invalid=True):
        """Return list of all set actions for this fmri in
        Catalog.DEPENDENCY section."""

        return self.__get_actions(fmri, "set",
            excludes=excludes, trim_invalid=trim_invalid)

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
            self.__trim_unsupported(fmri)
        return self.__variant_dict[fmri]

    def __is_explicit_install(self, fmri):
        """check if given fmri has explicit install actions."""

        for sa in self.__get_set_actions(fmri):
            if sa.attrs["name"] == "pkg.depend.explicit-install" \
                and sa.attrs["value"].lower() == "true":
                return True
        return False

    def __filter_explicit_install(self, fmri, excludes):
        """Check packages which have 'pkg.depend.explicit-install'
        action set to true, and prepare to filter."""

        will_filter = True
        # Filter out fmris with 'pkg.depend.explicit-install' set to
        # true and not explicitly proposed, already installed in the
        # current image, or is parent-constrained and is installed in
        # the parent image.
        if self.__is_explicit_install(fmri):
            pkg_name = fmri.pkg_name
            if pkg_name in self.__expl_install_dict and \
                fmri in self.__expl_install_dict[pkg_name]:
                will_filter = False
            elif pkg_name in self.__installed_dict:
                will_filter = False
            elif pkg_name in self.__parent_dict:
                # If this is a linked package that is
                # constrained to be the same version as parent,
                # and the parent has it installed, ignore
                # pkg.depend.explicit-install so that IDR
                # versions of packages can be used
                # automatically.
                will_filter = not any(
                    da
                    for da in self.__get_dependency_actions(
                        fmri, excludes)
                    if da.attrs["type"] == "parent" and
                        pkg.actions.depend.DEPEND_SELF in
                            da.attrlist("fmri")
                )
        else:
            will_filter = False
        return will_filter

    def __generate_dependency_closure(self, fmri_set, excludes=EmptyI,
        dotrim=True, full_trim=False, filter_explicit=True,
        proposed_dict=None):
        """return set of all fmris the set of specified fmris could
        depend on; while trimming those packages that cannot be
        installed"""

        # Use a copy of the set provided by the caller to prevent
        # unexpected modification!
        needs_processing = set(fmri_set)
        already_processed = set()

        while needs_processing:
            self.__progress()
            fmri = needs_processing.pop()
            already_processed.add(fmri)
            # Trim filtered packages.
            if filter_explicit and \
                self.__filter_explicit_install(fmri, excludes):
                reason = (N_("Uninstalled fmri {0} can "
                    "only be installed if explicitly "
                    "requested"), (fmri,))
                self.__trim((fmri,), _TRIM_EXPLICIT_INSTALL,
                    reason)
                continue

            needs_processing |= (self.__generate_dependencies(fmri,
                excludes, dotrim, full_trim,
                proposed_dict=proposed_dict) - already_processed)
        return already_processed

    def __generate_dependencies(self, fmri, excludes=EmptyI, dotrim=True,
        full_trim=False, proposed_dict=None):
        """return set of direct (possible) dependencies of this pkg;
        trim those packages whose dependencies cannot be satisfied"""
        try:
            return set([
                 f
                 for da in self.__get_dependency_actions(fmri,
                     excludes)
                 # check most common ones first; what is checked
                 # here is a matter of optimization / messaging, not
                 # correctness.
                 if da.attrs["type"] == "require" or
                     da.attrs["type"] == "group" or
                     da.attrs["type"] == "conditional" or
                     da.attrs["type"] == "require-any" or
                     da.attrs["type"] == "group-any" or
                     (full_trim and (
                         da.attrs["type"] == "incorporate" or
                         da.attrs["type"] == "optional" or
                         da.attrs["type"] == "exclude"))
                 for f in self.__parse_dependency(da, fmri,
                     dotrim, check_req=True,
                     proposed_dict=proposed_dict)[1]
            ])

        except DependencyException as e:
            self.__trim((fmri,), e.reason_id, e.reason,
                fmri_adds=e.fmris)
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

        fmris_by_name = dict(
            (pfmri.pkg_name, pfmri)
            for pfmri in fmris
        )

        # figure out which renamed fmris have dependencies; compute
        # transitively so we can handle multiple renames

        needs_processing = set(fmris) - renamed_fmris
        already_processed = set()

        while needs_processing:
            pfmri = needs_processing.pop()
            already_processed.add(pfmri)
            for da in self.__get_dependency_actions(
                pfmri, excludes):
                if da.attrs["type"] not in \
                    ("incorporate", "optional", "origin"):
                    for f in da.attrlist("fmri"):
                        try:
                            tmp = self.__fmridict[f]
                        except KeyError:
                            tmp = \
                                pkg.fmri.PkgFmri(f)
                            self.__fmridict[f] = tmp
                        name = tmp.pkg_name
                        if name not in fmris_by_name:
                            continue
                        new_fmri = fmris_by_name[name]
                        # since new_fmri will not be
                        # treated as renamed, make sure
                        # we check any dependencies it
                        # has
                        if new_fmri not in \
                            already_processed:
                            needs_processing.add(
                                new_fmri)
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
                        da.attrs["fmri"]).pkg_name
                    self.__dependents.setdefault(
                        self.__installed_dict[pkg_name],
                        set()).add(f)
        return self.__dependents.get(pfmri, set())

    def __trim_recursive_incorps(self, fmri_list, excludes, reason_id):
        """trim packages affected by incorporations"""
        processed = set()

        work = [fmri_list]

        if reason_id == _TRIM_PROPOSED_INC:
            reason = N_(
                "Excluded by proposed incorporation '{0}'")
        elif reason_id == _TRIM_SYNCED_INC:
            reason = N_(
                "Excluded by synced parent incorporation '{0}'")
        else:
            raise AssertionError(
                "Invalid reason_id value: {0}".format(reason_id))

        while work:
            fmris = work.pop()
            enc_pkg_name = fmris[0].get_name()
            # If the package is not installed then any dependenices
            # it has are irrelevant.
            if enc_pkg_name not in self.__installed_dict:
                continue
            processed.add(frozenset(fmris))
            d = self.__combine_incorps(fmris, excludes)
            for name in d:
                self.__trim(d[name][1], reason_id,
                    (reason, (fmris[0].pkg_name,)))
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
        all_keys = reduce(set.intersection,
            (set(d.keys()) for d in dict_list))

        return dict(
            (k,
             (reduce(set.union,
                 (d.get(k, (set(), set()))[0]
                  for d in dict_list)),
              reduce(set.intersection,
                 (d.get(k, (set(), set()))[1]
                  for d in dict_list))))
            for k in all_keys
        )

    def __get_incorp_nonmatch_dict(self, fmri, excludes):
        """Given a fmri with incorporation dependencies, produce a
        dictionary containing (matching, non matching fmris),
        indexed by pkg name.  Note that some fmris may be
        incorporated more than once at different levels of
        specificity"""
        ret = dict()
        for da in self.__get_dependency_actions(fmri,
            excludes=excludes):
            if da.attrs["type"] != "incorporate":
                continue
            nm, m, _c, _d, _r, f = self.__parse_dependency(da, fmri,
                dotrim=False)
            # Collect all incorp. dependencies affecting
            # a package in a list.  Note that it is
            # possible for both matching and non-matching
            # sets to be NULL, and we'll need at least
            # one item in the list for reduce to work.
            ret.setdefault(f.pkg_name, (list(), list()))
            ret[f.pkg_name][0].append(set(m))
            ret[f.pkg_name][1].append(set(nm))

        # For each of the packages constrained, combine multiple
        # incorporation dependencies.  Matches are intersected,
        # non-matches form a union.
        for pkg_name in ret:
            ret[pkg_name] = (
                reduce(set.intersection, ret[pkg_name][0]),
                reduce(set.union, ret[pkg_name][1]))
        return ret

    def __parse_group_dependency(self, dotrim, obsolete_ok, fmris):
        """Returns (matching, nonmatching) fmris for given list of group
        dependencies."""

        matching = []
        nonmatching = []
        for f in fmris:
            # remove version explicitly; don't
            # modify cached fmri
            if f.version is not None:
                fmri = f.copy()
                fmri.version = None
            else:
                fmri = f

            m, nm = self.__comb_newer_fmris(fmri,
                dotrim, obsolete_ok=obsolete_ok)
            matching.extend(m)
            nonmatching.extend(nm)

        return frozenset(matching), frozenset(nonmatching)

    def __parse_dependency(self, dependency_action, source,
        dotrim=True, check_req=False, proposed_dict=None):
        """Return tuple of (disallowed fmri list, allowed fmri list,
        conditional_list, dependency_type, required)"""

        dtype = dependency_action.attrs["type"]
        fmris = []
        for fmristr in dependency_action.attrlist("fmri"):
            try:
                fmri = self.__fmridict[fmristr]
            except KeyError:
                fmri = pkg.fmri.PkgFmri(fmristr)
                self.__fmridict[fmristr] = fmri

            if not self.__depend_ts:
                fver = fmri.version
                if fver and fver.timestr:
                    # Include timestamp in all error
                    # output for dependencies.
                    self.__depend_ts = True

            fmris.append(fmri)

        fmri = fmris[0]

        # true if match is required for containing pkg
        required = True
        # if this dependency has conditional fmris
        conditional = None
        # true if obsolete pkgs satisfy this dependency
        obsolete_ok = False

        if dtype == "require":
            matching, nonmatching = \
                self.__comb_newer_fmris(fmri, dotrim,
                    obsolete_ok=obsolete_ok)

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
            # Track packages that deliver incorporate deps.
            self.__known_incs.add(source.pkg_name)

        elif dtype == "conditional":
            cond_fmri = pkg.fmri.PkgFmri(
                dependency_action.attrs["predicate"])
            conditional, nonmatching = self.__comb_newer_fmris(
                cond_fmri, dotrim, obsolete_ok=obsolete_ok)
            # Required is only really helpful for solver error
            # messaging.  The only time we know that this dependency
            # is required is when the predicate package must be part
            # of the solution.
            if cond_fmri.pkg_name not in self.__req_pkg_names:
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
            # Parent dependency fmris must exist outside of the
            # current image, so we don't report any new matching
            # or nonmatching requirements for the solver.
            matching = nonmatching = frozenset()
            required = False

        elif dtype == "origin":
            matching, nonmatching = \
                self.__comb_newer_fmris(fmri, dotrim=False,
                obsolete_ok=obsolete_ok)
            required = False

        elif dtype == "group" or dtype == "group-any":
            obsolete_ok = True
            # Determine potential fmris for matching.
            potential = [
                fmri
                for fmri in fmris
                if not (fmri.pkg_name in self.__avoid_set or
                    fmri.pkg_name in self.__reject_set)
            ]
            required = len(potential) > 0

            # Determine matching fmris.
            matching = nonmatching = frozenset()
            if required:
                matching, nonmatching = \
                    self.__parse_group_dependency(dotrim,
                        obsolete_ok, potential)
                if not matching and not nonmatching:
                    # No possible stems at all? Ignore
                    # dependency.
                    required = False

            # If more than one stem matched, prefer stems for which
            # no obsoletion exists.
            mstems = frozenset(f.pkg_name for f in matching)
            if required and len(mstems) > 1:
                ostems = set()
                ofmris = set()
                for f in matching:
                    if self.__fmri_is_obsolete(f):
                        ostems.add(f.pkg_name)
                        ofmris.add(f)

                # If not all matching stems had an obsolete
                # version, remove the obsolete fmris from
                # consideration.  This makes the assumption that
                # at least one of the remaining, non-obsolete
                # stems will be installable.  If that is not
                # true, the solver may not find anything to do,
                # or may not find a solution if the system is
                # overly constrained.  This is believed
                # unlikely, so seems a reasonable compromise.
                # In that scenario, a client can move forward by
                # using --reject to remove the related group
                # dependencies.
                if mstems - ostems:
                    matching -= ofmris
                    nonmatching |= ofmris

        else: # only way this happens is if new type is incomplete
            raise api_errors.InvalidPackageErrors([
                "Unknown dependency type {0}".format(dtype)])

        # check if we're throwing exceptions and we didn't find any
        # matches on a required package
        if not check_req or matching or not required:
            return (nonmatching, matching, conditional, dtype,
                required, fmri)
        elif dotrim and source in self.__inc_list and \
             dtype == "incorporate":
            # This is an incorporation package that will not be
            # removed, so if dependencies can't be satisfied, try
            # again with dotrim=False to ignore rejections due to
            # proposed packages.
            return self.__parse_dependency(dependency_action,
                source, dotrim=False, check_req=check_req,
                proposed_dict=proposed_dict)

        # Neither build or publisher is interesting for dependencies.
        fstr = fmri.get_fmri(anarchy=True, include_build=False,
            include_scheme=False)

        # we're going to toss an exception
        if dtype == "exclude":
            # If we reach this point, we know that a required
            # package (already installed or proposed) was excluded.
            matching, nonmatching = self.__comb_older_fmris(
                fmri, dotrim=False, obsolete_ok=False)

            # Determine if excluded package is already installed.
            installed = False
            for f in nonmatching:
                if f in self.__installed_fmris:
                    installed = True
                    break

            if not matching and installed:
                # The exclude dependency doesn't allow the
                # version of the package that is already
                # installed.
                raise DependencyException(
                    _TRIM_INSTALLED_EXCLUDE,
                    (N_("Package contains 'exclude' dependency "
                        "{0} on installed package"), (fstr,)))
            elif not matching and not installed:
                # The exclude dependency doesn't allow any
                # version of the package that is proposed.
                raise DependencyException(
                    _TRIM_INSTALLED_EXCLUDE,
                    (N_("Package contains 'exclude' dependency "
                        "{0} on proposed package"), (fstr,)))
            else:
                # All versions of the package allowed by the
                # exclude dependency were trimmed by other
                # dependencies.  If changed, update _fmri_errors
                # _TRIM_DEP_TRIMMED.
                raise DependencyException(
                    _TRIM_DEP_TRIMMED,
                    (N_("No version allowed by 'exclude' "
                        "dependency {0} could be installed"),
                        (fstr,)), matching)
            # not reached
        elif dtype == "incorporate":
            matching, nonmatching = \
                self.__comb_auto_fmris(fmri, dotrim=False,
                obsolete_ok=obsolete_ok)

        # check if allowing obsolete packages helps

        elif not obsolete_ok:
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
                        _TRIM_DEP_OBSOLETE,
                        (N_("All acceptable versions of "
                            "'{0}' dependency on {1} are "
                            "obsolete"), (dtype, fstr)))
                else:
                    sfmris = frozenset([
                        fmri.get_fmri(anarchy=True,
                            include_build=False,
                            include_scheme=False)
                        for f in fmris
                    ])
                    raise DependencyException(
                        _TRIM_DEP_OBSOLETE,
                        (N_("All acceptable versions of "
                            "'{0}' dependencies on {1} are "
                            "obsolete"), (dtype, sfmris)))
            # something else is wrong
            matching, nonmatching = self.__comb_newer_fmris(fmri,
                dotrim=False, obsolete_ok=obsolete_ok)
        else:
            # try w/o trimming anything
            matching, nonmatching = self.__comb_newer_fmris(fmri,
                dotrim=False, obsolete_ok=obsolete_ok)

        if not matching:
            raise DependencyException(_TRIM_DEP_MISSING,
                (N_("No version for '{0}' dependency on {1} can "
                    "be found"), (dtype, fstr)))

        # If this is a dependency of a proposed package for which only
        # one version is possible, then mark all other versions as
        # rejected by this package.  This ensures that other proposed
        # packages will be included in error messaging if their
        # dependencies can only be satisfied if this one is not
        # proposed.
        if dotrim and nonmatching and proposed_dict and \
            proposed_dict.get(source.pkg_name, []) == [source]:
            nm = self.__parse_dependency(dependency_action, source,
                dotrim=False, check_req=check_req,
                proposed_dict=proposed_dict)[0]
            self.__trim(nm, _TRIM_DEP_TRIMMED,
                (N_("Rejected by '{0}' dependency in proposed "
                    "package '{1}'"), (dtype, source.pkg_name)),
                fmri_adds=[source])

        # If changed, update _fmri_errors _TRIM_DEP_TRIMMED.
        raise DependencyException(_TRIM_DEP_TRIMMED,
            (N_("No version matching '{0}' dependency {1} can be "
                "installed"), (dtype, fstr)), matching)

    def __installed_unsatisfied_parent_deps(self, excludes,
        ignore_inst_parent_deps):
        """If we're a child image then we need to relax packages
        that are dependent upon themselves in the parent image.  This
        is necessary to keep those packages in sync."""

        relax_pkgs = set()

        # check if we're a child image.
        if not self.__is_child():
            return relax_pkgs

        # if we're ignoring parent dependencies there is no reason to
        # relax install-holds in packages constrained by those
        # dependencies.
        if ignore_inst_parent_deps:
            return relax_pkgs

        for f in self.__installed_fmris:
            for da in self.__get_dependency_actions(f, excludes):
                if da.attrs["type"] != "parent":
                    continue
                self.__linked_pkgs.add(f)

                if (pkg.actions.depend.DEPEND_SELF
                    not in da.attrlist("fmri")):
                    continue

                # We intentionally do not rely on 'insync' state
                # as a change in facets/variants may result in
                # changed parent constraints.
                pf = self.__parent_dict.get(f.pkg_name)
                if pf != f:
                    # We only need to relax packages that
                    # don't match the parent.
                    relax_pkgs.add(f.pkg_name)
                    break

        return relax_pkgs

    def __generate_dependency_errors(self, fmri_list, excludes=EmptyI):
        """ Returns a list of strings describing why fmris cannot
        be installed, or returns an empty list if installation
        is possible. """
        ret = []

        needs_processing = set(fmri_list)
        already_processed = set()
        already_seen = set()

        while needs_processing:
            fmri = needs_processing.pop()
            errors, newfmris = self.__do_error_work(fmri,
                excludes, already_seen)
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
        # Value 'DebugValues' is unsubscriptable;
        # pylint: disable=E1136
        assert DebugValues["plan"]

        return self.__fmri_list_errors(self.__trim_dict.keys(),
            already_seen=set(), verbose=True)

    def __check_installed(self):
        """Generate list of strings describing why currently
        installed packages cannot be installed, or empty list"""

        # Used to de-dup errors.
        already_seen = set()

        ret = []
        for f in self.__installed_fmris - self.__removal_fmris:
            matching = self.__comb_newer_fmris(f, dotrim=True,
                obsolete_ok=True)[0]
            if matching:
                continue
            # no matches when disallowed packages are excluded
            matching = self.__comb_newer_fmris(f, dotrim=False,
                obsolete_ok=True)[0]

            ret.append(_("No suitable version of installed package "
                "{0} found").format(f.pkg_name))
            ret.extend(self.__fmri_list_errors(matching,
                already_seen=already_seen))

        return ret

    def __fmri_list_errors(self, fmri_list, indent="", already_seen=None,
        omit=None, verbose=False):
        """Given a list of FMRIs, return indented strings indicating why
        they were rejected."""
        ret = []

        if omit is None:
            omit = set()

        fmri_reasons = []
        skey = operator.attrgetter('pkg_name')
        for f in sorted(fmri_list, key=skey):
            res = self.__fmri_errors(f, indent,
                already_seen=already_seen, omit=omit,
                verbose=verbose)
            # If None was returned, that implies that all of the
            # reasons the FMRI was rejected aren't interesting.
            if res is not None:
                fmri_reasons.append(res)

        last_run = []

        def collapse_fmris():
            """Collapse a range of FMRIs into format:

               first_fmri
                 to
               last_fmri

               ...based on verbose state."""

            if last_run:
                indent = last_run.pop(0)
                if verbose or len(last_run) <= 1:
                    ret.extend(last_run)
                elif (not self.__depend_ts and
                    ret[-1].endswith(last_run[-1].strip())):
                    # If timestamps are not being displayed
                    # and the last FMRI is the same as the
                    # first in the range then we only need
                    # to show the first.
                    pass
                else:
                    ret.append(indent + "  " + _("to"))
                    ret.append(last_run[-1])
            last_run[::] = []

        last_reason = None
        for fmri_id, reason in fmri_reasons:
            if reason == last_reason:
                indent = " " * len(fmri_id[0])
                if not last_run:
                    last_run.append(indent)
                last_run.append(indent + fmri_id[1])
                continue
            else: # ends run
                collapse_fmris()
                if last_reason:
                    ret.extend(last_reason)
                ret.append(fmri_id[0] + fmri_id[1])
                last_reason = reason
        if last_reason:
            collapse_fmris()
            ret.extend(last_reason)
        return ret

    def __fmri_errors(self, fmri, indent="", already_seen=None,
        omit=None, verbose=False):
        """return a list of strings w/ indents why this fmri is not
        suitable"""

        if already_seen is None:
            already_seen = set()
        if omit is None:
            omit = set()

        fmri_id = [_("{0}  Reject:  ").format(indent)]
        if not verbose and not self.__depend_ts:
            # Exclude build and timestamp for brevity.
            fmri_id.append(fmri.get_short_fmri())
        else:
            # Include timestamp for clarity if any dependency
            # included a timestamp; exclude build for brevity.
            fmri_id.append(fmri.get_fmri(include_build=False))

        tag = _("Reason:")

        if fmri in already_seen:
            if fmri in omit:
                return

            # note to translators: 'indent' will be a series of
            # whitespaces.
            reason = _("{indent}  {tag}  [already rejected; see "
                "above]").format(indent=indent, tag=tag)
            return fmri_id, [reason]

        already_seen.add(fmri)

        if not verbose:
            # By default, omit packages from errors that were only
            # rejected due to a newer version being installed, or
            # because they didn't match user-specified input.  It's
            # tempting to omit _TRIM_REJECT here as well, but that
            # leads to some very mysterious errors for
            # administrators if the only reason an operation failed
            # is because a required dependency was rejected.
            for reason_id, reason_t, fmris in \
                self.__trim_dict.get(fmri, EmptyI):
                if reason_id not in (_TRIM_INSTALLED_NEWER,
                    _TRIM_PROPOSED_PUB, _TRIM_PROPOSED_VER):
                    break
            else:
                omit.add(fmri)
                return

        ms = []
        for reason_id, reason_t, fmris in sorted(
            self.__trim_dict.get(fmri, EmptyI)):

            if not verbose:
                if reason_id in (_TRIM_INSTALLED_NEWER,
                    _TRIM_PROPOSED_PUB, _TRIM_PROPOSED_VER):
                    continue

            if isinstance(reason_t, tuple):
                reason = _(reason_t[0]).format(*reason_t[1])
            else:
                reason = _(reason_t)

            ms.append("{0}  {1}  {2}".format(indent, tag, reason))

            if reason in already_seen:
                # If we've already explained why something was
                # rejected before, skip it.
                continue

            # Use the reason text and not the id, as the text is
            # specific to a particular rejection.
            already_seen.add(reason)

            # By default, don't include error output for
            # dependencies on incorporation packages that don't
            # specify a version since any version-specific
            # dependencies will have caused a rejection elsewhere.
            if (not verbose and
                reason_id == _TRIM_DEP_TRIMMED and
                len(reason_t[1]) == 2):
                dtype, fstr = reason_t[1]
                if dtype == "require" and "@" not in fstr:
                    # Assumes fstr does not include
                    # publisher or scheme.
                    if fstr in self.__known_incs:
                        continue

            # Add the reasons why each package version that
            # satisfied a dependency was rejected.
            res = self.__fmri_list_errors([
                    f
                    for f in sorted(fmris)
                    if f not in already_seen
                    if verbose or f not in omit
                ],
                indent + "  ",
                already_seen=already_seen,
                omit=omit,
                verbose=verbose
            )

            if res:
                ms.append(indent + "    " + ("-" * 40))
                ms.extend(res)
                ms.append(indent + "    " + ("-" * 40))

        return fmri_id, ms

    def __do_error_work(self, fmri, excludes, already_seen):
        """Private helper function used by __generate_dependency_errors
        to determine why packages were rejected."""

        needs_processing = set()

        if self.__trim_dict.get(fmri):
            return self.__fmri_list_errors([fmri],
                already_seen=already_seen), needs_processing

        for a in self.__get_dependency_actions(fmri, excludes):
            try:
                matching = self.__parse_dependency(a, fmri,
                    check_req=True)[1]
            except DependencyException as e:
                self.__trim((fmri,), e.reason_id, e.reason,
                    fmri_adds=e.fmris)
                s = _("No suitable version of required package "
                    "{0} found:").format(fmri.pkg_name)
                return ([s] + self.__fmri_list_errors([fmri],
                    already_seen=already_seen),
                    set())
            needs_processing |= matching
        return [], needs_processing

    # clause generation routines
    def __gen_dependency_clauses(self, fmri, da, dotrim=True):
        """Return clauses to implement this dependency"""
        nm, m, cond, dtype, _req, _depf = self.__parse_dependency(da,
            fmri, dotrim)

        if dtype == "require" or dtype == "require-any":
            return self.__gen_require_clauses(fmri, m)
        elif dtype == "group" or dtype == "group-any":
            if not m:
                return [] # no clauses needed; pkg avoided
            else:
                return self.__gen_require_clauses(fmri, m)
        elif dtype == "conditional":
            return self.__gen_require_conditional_clauses(fmri, m,
                cond)
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
                raise TypeError(_("List of integers, not {0}, "
                    "expected").format(c))

    def __get_child_holds(self, install_holds, pkg_cons, inc_set):
        """Returns the list of installed packages that are incorporated
        by packages, delivering an install-hold, and that do not have an
        install-hold but incorporate packages.

        'install_holds' is a dict of installed package stems indicating
        the pkg.depend.install-hold delivered by the package that are
        not being removed.

        'pkg_cons' is a dict of installed package fmris and the
        incorporate constraints they deliver.

        'inc_set' is a list of packages that incorporate other packages
        and deliver install-hold actions.  It acts as the starting point
        where we fan out to find "child" packages that incorporate other
        packages."""

        unprocessed = set(inc_set)
        processed = set()
        proc_cons = set()
        incorps = set()

        while unprocessed:
            self.__progress()
            ifmri = unprocessed.pop()
            processed.add(ifmri)

            if ifmri in self.__removal_fmris:
                # This package will be removed, so
                # nothing to do.
                continue

            cons = pkg_cons.get(ifmri, [])
            if cons and ifmri.pkg_name not in install_holds:
                # If this package incorporates other
                # packages and does not deliver an
                # install-hold, then consider it a
                # 'child' hold.
                incorps.add(ifmri)

            # Find all incorporation constraints that result
            # in only one possible match.  If there is only
            # one possible match for an incorporation
            # constraint then that package will not be
            # upgraded and should be checked for
            # incorporation constraints.
            for con in cons:
                if (con.pkg_name in install_holds or
                    con in proc_cons):
                    # Already handled.
                    continue
                matching = list(
                    self.__comb_auto_fmris(con)[0])
                if len(matching) == 1:
                    if matching[0] not in processed:
                        unprocessed.add(matching[0])
                else:
                    # Track which constraints have
                    # already been processed
                    # seperately from which
                    # package FMRIs have been
                    # processed to avoid (unlikely)
                    # collision.
                    proc_cons.add(con)

        return incorps

    def __get_installed_upgradeable_incorps(self, excludes=EmptyI):
        """Return the latest version of installed upgradeable
        incorporations w/ install holds"""

        installed_incs = []
        for f in self.__installed_fmris - self.__removal_fmris:
            for d in self.__catalog.get_entry_actions(f,
                [catalog.Catalog.DEPENDENCY], excludes=excludes):
                if (d.name == "set" and d.attrs["name"] ==
                    "pkg.depend.install-hold"):
                    installed_incs.append(f)

        ret = []
        for f in installed_incs:
            matching = self.__comb_newer_fmris(f, dotrim=False)[0]
            latest = sorted(matching, reverse=True)[0]
            if latest != f:
                ret.append(latest)
        return ret

    def __get_installed_unbound_inc_list(self, proposed_pkgs,
        excludes=EmptyI):
        """Return the list of incorporations that are to not to change
        during this install operation, and the lists of fmris they
        constrain."""

        incorps = set()
        versioned_dependents = set()
        pkg_cons = {}
        install_holds = {}

        # Determine installed packages that contain incorporation
        # dependencies, those packages that are depended on by explict
        # version, and those that have pkg.depend.install-hold values.
        for f in self.__installed_fmris - self.__removal_fmris:
            for d in self.__catalog.get_entry_actions(f,
                [catalog.Catalog.DEPENDENCY],
                excludes=excludes):
                if d.name == "depend":
                    fmris = []
                    for fl in d.attrlist("fmri"):
                        try:
                            tmp = self.__fmridict[
                                fl]
                        except KeyError:
                            tmp = pkg.fmri.PkgFmri(
                                fl)
                            self.__fmridict[fl] = \
                                tmp
                        fmris.append(tmp)
                    if d.attrs["type"] == "incorporate":
                        incorps.add(f.pkg_name)
                        pkg_cons.setdefault(f,
                            []).append(fmris[0])
                    versioned_dependents.update(
                        fmri.pkg_name
                        for fmri in fmris
                        if fmri.version is not None
                    )
                elif (d.name == "set" and d.attrs["name"] ==
                    "pkg.depend.install-hold"):
                    install_holds[f.pkg_name] = \
                        d.attrs["value"]

        # find install holds that appear on command line and are thus
        # relaxed
        relaxed_holds = set([
            install_holds[name]
            for name in proposed_pkgs
            if name in install_holds
        ])

        # add any other install holds that are relaxed because they have
        # values that start w/ the relaxed ones...
        relaxed_holds |= set([
            hold
            for hold in install_holds.values()
            if [ r for r in relaxed_holds if hold.startswith(r + ".") ]
        ])

        # Expand the list of install holds to include packages that are
        # incorporated by packages delivering an install-hold and that
        # do not have an install-hold, but incorporate packages.
        child_holds = self.__get_child_holds(install_holds, pkg_cons,
            set(inc for inc in pkg_cons
                if inc.pkg_name in install_holds and
                install_holds[inc.pkg_name] not in relaxed_holds
            )
        )

        for child_hold in child_holds:
            assert child_hold.pkg_name not in install_holds
            install_holds[child_hold.pkg_name] = child_hold.pkg_name

        # versioned_dependents contains all the packages that are
        # depended on w/ a explicit version.  We now modify this list so
        # that it does not contain any packages w/ install_holds, unless
        # those holds were relaxed.
        versioned_dependents -= set([
            pkg_name
            for pkg_name, hold_value in install_holds.items()
            if hold_value not in relaxed_holds
        ])
        # Build the list of fmris that 1) contain incorp. dependencies
        # 2) are not in the set of versioned_dependents and 3) do not
        # explicitly appear on the install command line.
        installed_dict = self.__installed_dict
        ret = [
            installed_dict[pkg_name]
            for pkg_name in incorps - versioned_dependents
            if pkg_name not in proposed_pkgs
            if installed_dict[pkg_name] not in self.__removal_fmris
        ]
        # For each incorporation above that will not change, return a
        # list of the fmris that incorporation constrains
        con_lists = [
            [ i for i in pkg_cons[inc] ]
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

        if pkg_name in self.__publisher:
            acceptable_pubs = [self.__publisher[pkg_name]]
            if pkg_name in self.__installed_dict:
                reason_id = _TRIM_PUB_STICKY
                reason = (N_("Currently installed package "
                    "'{0}' is from sticky publisher '{1}'."),
                    (pkg_name, self.__publisher[pkg_name]))
            else:
                reason_id = _TRIM_PROPOSED_PUB
                reason = N_("Package is from publisher other "
                    "than specified one.")
        else:
            # order by pub_rank; choose highest possible tier for
            # pkgs; guard against unconfigured publishers in known
            # catalog
            pubs_found = set((f.publisher for f in fmri_list))
            ranked = sorted([
                (self.__pub_ranks[p][0], p)
                for p in pubs_found
                if self.__pub_ranks.get(p, (0, False, False))[2]
            ])
            acceptable_pubs = [
                r[1]
                for r in ranked
                if r[0] == ranked[0][0]
            ]
            reason_id = _TRIM_PUB_RANK
            if acceptable_pubs:
                reason = (N_("Higher ranked publisher {0} was "
                    "selected"), (acceptable_pubs[0],))
            else:
                reason = N_("Package publisher is ranked lower "
                    "in search order")

        # allow installed packages to co-exist to meet dependency reqs.
        # in case new publisher not proper superset of original.  avoid
        # multiple publishers w/ the exact same fmri to prevent
        # thrashing in the solver due to many equiv. solutions.
        inst_f = self.__installed_dict.get(pkg_name)
        self.__trim([
            f
            for f in fmri_list
            if (f.publisher not in acceptable_pubs and
                    (not inst_f or f != inst_f)) or
                (inst_f and f.publisher != inst_f.publisher and
                    f.version == inst_f.version)
        ], reason_id, reason)

    # routines to manage the trim dictionary
    # trim dictionary contains the reasons an fmri was rejected for
    # consideration reason is a tuple of a string w/ format chars and args,
    # or just a string.  fmri_adds are any fmris that caused the rejection

    def __trim(self, fmri_list, reason_id, reason, fmri_adds=EmptyI):
        """Remove specified fmri(s) from consideration for specified
        reason."""

        self.__progress()
        assert reason_id in range(_TRIM_MAX)
        tup = (reason_id, reason, frozenset(fmri_adds))

        for fmri in fmri_list:
            self.__trim_dict[fmri].add(tup)

    def __trim_older(self, fmri):
        """Trim any fmris older than this one"""
        reason = (N_("Newer version {0} is already installed"), (fmri,))
        self.__trim(self.__comb_newer_fmris(fmri, dotrim=False)[1] -
            self.__allowed_downgrades, _TRIM_INSTALLED_NEWER, reason)

    def __trim_nonmatching_variants(self, fmri):
        """Trim packages that don't support image architecture or other
        image variant."""

        vd = self.__get_variant_dict(fmri)
        reason = ""

        for v in self.__variants.keys():
            if v in vd and self.__variants[v] not in vd[v]:
                if vd == "variant.arch":
                    reason = N_("Package doesn't support "
                        "image architecture")
                else:
                    reason = (N_("Package supports image "
                        "variant {0}={1} but doesn't "
                        "support this image's {0}={2}"),
                        (v, str(vd[v]),
                        str(self.__variants[v])))

                self.__trim((fmri,), _TRIM_VARIANT, reason)
        return reason == ""

    def __trim_nonmatching_parents1(self, pkg_fmri, fmri):
        """Private helper function for __trim_nonmatching_parents that
        trims any pkg_fmri that matches a parent dependency and that is
        not installed in the parent image, that is from a different
        publisher than the parent image, or that is a different version
        than the parent image."""

        if fmri in self.__parent_pkgs:
            # exact fmri installed in parent
            return True

        if fmri.pkg_name not in self.__parent_dict:
            # package is not installed in parent
            if self.__is_zone():
                reason = (N_("Package {0} is not installed in "
                    "global zone."), (fmri.pkg_name,))
            else:
                reason = (N_("Package {0} is not installed in "
                    "parent image."), (fmri.pkg_name,))
            self.__trim((pkg_fmri,), _TRIM_PARENT_MISSING, reason)
            return False

        pf = self.__parent_dict[fmri.pkg_name]
        if fmri.publisher and fmri.publisher != pf.publisher:
            # package is from a different publisher in the parent
            if self.__is_zone():
                reason = (N_("Package in global zone is from "
                    "a different publisher: {0}"), (pf,))
            else:
                reason = (N_("Package in parent is from a "
                    "different publisher: {0}"), (pf,))
            self.__trim((pkg_fmri,), _TRIM_PARENT_PUB, reason)
            return False

        if pf.version == fmri.version:
            # parent dependency is satisfied, which applies to both
            # DEPEND_SELF and other cases
            return True
        elif (pkg_fmri != fmri and
            pf.version.is_successor(fmri.version,
                version.CONSTRAINT_NONE)):
            # *not* DEPEND_SELF; parent dependency is satisfied
            return True

        # version mismatch
        if pf.version.is_successor(fmri.version,
            version.CONSTRAINT_NONE):
            reason_id = _TRIM_PARENT_NEWER
            if self.__is_zone():
                reason = (N_("Global zone has a "
                    "newer version: {0}"), (pf,))
            else:
                reason = (N_("Parent image has a "
                    "newer version: {0}"), (pf,))
        else:
            reason_id = _TRIM_PARENT_OLDER
            if self.__is_zone():
                reason = (N_("Global zone has an older "
                    "version of package: {0}"), (pf,))
            else:
                reason = (N_("Parent image has an older "
                    "version of package: {0}"), (pf,))

        self.__trim((pkg_fmri,), reason_id, reason)
        return False

    def __trim_nonmatching_parents(self, pkg_fmri, excludes,
        ignore_inst_parent_deps=False):
        """Trim any pkg_fmri that contains a parent dependency that
        is not satisfied by the parent image."""

        # the fmri for the package should include a publisher
        assert pkg_fmri.publisher

        # if we're not a child then ignore "parent" dependencies.
        if not self.__is_child():
            return True

        # check if we're ignoring parent dependencies for installed
        # packages.
        if ignore_inst_parent_deps and \
            pkg_fmri in self.__installed_fmris:
            return True

        # Find all the fmris that we depend on in our parent.
        # Use a set() to eliminate any dups.
        pkg_deps = set([
            pkg.fmri.PkgFmri(f)
            for da in self.__get_dependency_actions(pkg_fmri, excludes)
            if da.attrs["type"] == "parent"
            for f in da.attrlist("fmri")
        ])

        if not pkg_deps:
            # no parent dependencies.
            return True
        self.__linked_pkgs.add(pkg_fmri)

        allowed = True
        for f in pkg_deps:
            fmri = f
            if f.pkg_name == pkg.actions.depend.DEPEND_SELF:
                # check if this package depends on itself.
                fmri = pkg_fmri
            if not self.__trim_nonmatching_parents1(pkg_fmri, fmri):
                allowed = False
        return allowed

    def __trim_nonmatching_origins(self, fmri, excludes,
        exact_install=False, installed_dict_tmp=EmptyDict):
        """Trim any fmri that contains a origin dependency that is
        not satisfied by the current image or root-image"""

        for da in self.__get_dependency_actions(fmri, excludes):
            if da.attrs["type"] != "origin":
                continue

            req_fmri = pkg.fmri.PkgFmri(da.attrs["fmri"])

            if da.attrs.get("root-image", "").lower() == "true":
                # Are firmware (driver) updates needed?
                if req_fmri.pkg_name.startswith(
                    "feature/firmware/"):
                    fw_ok, reason = \
                        self.__firmware.check(da,
                        req_fmri.pkg_name)
                    if not fw_ok:
                        self.__trim((fmri,),
                            _TRIM_FIRMWARE, reason)
                        return False
                    continue

                # Check that the CPU is supported in the
                # new root-image
                if req_fmri.pkg_name.startswith(
                    "feature/cpu"):
                    cpu_ok, reason = \
                        self.__cpu.check(da,
                        req_fmri.pkg_name)
                    if not cpu_ok:
                        self.__trim((fmri,),
                                    _TRIM_CPU,
                                    reason)
                        return False
                    continue

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
                    req_fmri.pkg_name)
                reason_id = _TRIM_INSTALLED_ROOT_ORIGIN
                reason = (N_("Installed version in root image "
                    "is too old for origin " "dependency {0}"),
                    (req_fmri,))
            else:
                # Always use the full installed dict for origin
                # dependency.
                if exact_install:
                    installed = installed_dict_tmp.get(
                        req_fmri.pkg_name)
                else:
                    installed = self.__installed_dict.get(
                        req_fmri.pkg_name)
                reason_id = _TRIM_INSTALLED_ORIGIN
                reason = (N_("Installed version in image "
                    "being upgraded is too old for origin "
                    "dependency {0}"), (req_fmri,))

            # assumption is that for root-image, publishers align;
            # otherwise these sorts of cross-environment
            # dependencies don't work well

            if (not installed or not req_fmri.version or
                req_fmri.version == installed.version or
                installed.version.is_successor(req_fmri.version,
                    version.CONSTRAINT_NONE)):
                continue

            self.__trim((fmri,), reason_id, reason)

            return False
        return True

    def __trim_unsupported(self, fmri):
        """Indicate given package FMRI is unsupported."""
        self.__trim((fmri,), _TRIM_UNSUPPORTED,
            N_("Package contains invalid or unsupported actions"))

    def __get_older_incorp_pkgs(self, fmri, install_holds, excludes=EmptyI,
        relax_all=False, depth=0):
        """Get all incorporated pkgs for the given 'fmri' whose versions
        are older than what is currently installed in the image."""

        candidates = set()
        if fmri in self.__dg_incorp_cache:
            candidates |= self.__dg_incorp_cache[fmri]
            return candidates

        if depth > 10:
            # Safeguard against circular dependencies.
            # If it happens, just end the recursion tree.
            return candidates

        self.__dg_incorp_cache[fmri] = set()
        self.__progress()

        # Get all matching incorporated packages for this fmri; this is
        # a list of sets, where each set represents all of the fmris
        # matching the incorporate dependency for a single package stem.
        #
        # Only add potential FMRIs to the list of allowed downgrades if
        # the currently installed version is not allowed by the related
        # incorporate dependency.  This prevents two undesirable
        # behaviours:
        #
        # - downgrades when a package is no longer incorporated in
        #   a newer version of an incorporating package and an older
        #   version is otherwise allowed
        # - upgrades of packages that are no longer incorporated
        #   in a newer version of an incorporating package and a newer
        #   version is otherwise allowed
        for matchdg, _ in self.__get_incorp_nonmatch_dict(fmri, excludes).values():
            match = next(iter(matchdg), None)
            if (not match or
                match.pkg_name not in self.__installed_dict):
                continue

            inst_fmri = self.__installed_dict[match.pkg_name]
            if inst_fmri in matchdg:
                continue

            inst_ver = inst_fmri.version
            for df in matchdg:
                if df.version == inst_ver:
                    # If installed version is not changing,
                    # there is no need to check for
                    # downgraded incorporate deps.
                    continue

                is_successor = df.version.is_successor(inst_ver,
                    None)
                if relax_all and is_successor:
                    # If all install-holds are relaxed, and
                    # this package is being upgraded, it is
                    # not a downgrade candidate and there is
                    # no need to recursively check for
                    # downgraded incorporate deps here as
                    # will be checked directly later in
                    # solve_update_all.
                    continue

                # Do not allow implicit publisher switches.
                if df.publisher != fmri.publisher:
                    continue

                # Do not allow pkgs marked for removal.
                if fmri in self.__removal_fmris:
                    continue

                # Do not allow pkgs with install-holds but
                # filter out child holds
                install_hold = False
                for ha in [
                    sa
                    for sa in self.__get_actions(df, "set")
                    if sa.attrs["name"] ==
                        "pkg.depend.install-hold"
                ]:
                    install_hold = True
                    for h in install_holds:
                        if ha.attrs["value"].startswith(
                            h):
                            # This is a child hold
                            # of an incorporating
                            # pkg, ignore.
                            install_hold = False
                            break
                    if not install_hold:
                        break
                if install_hold:
                    continue

                if not is_successor:
                    self.__dg_incorp_cache[fmri].add(df)
                    candidates.add(df)

                if not relax_all:
                    # If all install-holds are not relaxed,
                    # then we need to check if pkg has
                    # incorporate deps of its own since not
                    # every package is being checked
                    # individually.
                    candidates |= \
                        self.__get_older_incorp_pkgs(df,
                            install_holds,
                            excludes=excludes,
                            relax_all=relax_all,
                            depth=depth + 1)

        return candidates

    def __allow_incorp_downgrades(self, fmri, excludes=EmptyI,
        relax_all=False):
        """Find packages which have lower versions than installed but
        are incorporated by a package in the proposed list."""

        install_holds = set([
            sa.attrs["value"]
            for sa in self.__get_actions(fmri, "set")
            if sa.attrs["name"] == "pkg.depend.install-hold"
        ])

        # Get all pkgs which are incorporated by 'fmri',
        # including nested incorps.
        candidates = self.__get_older_incorp_pkgs(fmri, install_holds,
            excludes=excludes, relax_all=relax_all)

        return candidates

    def __dotrim(self, fmri_list):
        """Return fmri_list trimmed of any fmris in self.__trim_dict"""

        return [
            f
            for f in fmri_list
            if not self.__trim_dict.get(f)
        ]

    def __is_child(self):
        """Return True if this image is a linked image child."""
        return self.__parent_pkgs is not None

    def __is_zone(self):
        """Return True if image is a nonglobal zone"""
        if 'variant.opensolaris.zone' in self.__variants:
            return self.__variants['variant.opensolaris.zone'] == \
                'nonglobal'
        else:
            return False
