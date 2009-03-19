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

import pkg.client.api_errors as api_errors
import pkg.client.imagestate as imagestate
import pkg.client.pkgplan as pkgplan
import pkg.client.indexer as indexer
import pkg.client.variant as variant
import pkg.search_errors as se
import pkg.client.actuator as actuator
import pkg.fmri as fmri

from pkg.client.filter import compile_filter
from pkg.misc import msg

from pkg.client.retrieve import ManifestRetrievalError
from pkg.client.retrieve import DatastreamRetrievalError

UNEVALUATED       = 0 # nothing done yet
EVALUATED_PKGS    = 1 # established fmri changes
EVALUATED_OK      = 2 # ready to execute
PREEXECUTED_OK    = 3 # finished w/ preexecute
PREEXECUTED_ERROR = 4 # whoops
EXECUTED_OK       = 5 # finished execution
EXECUTED_ERROR    = 6 # failed

class ImagePlan(object):
        """An image plan takes a list of requested packages, an Image (and its
        policy restrictions), and returns the set of package operations needed
        to transform the Image to the list of requested packages.

        Use of an ImagePlan involves the identification of the Image, the
        Catalogs (implicitly), and a set of complete or partial package FMRIs.
        The Image's policy, which is derived from its type and configuration
        will cause the formulation of the plan or an exception state.

        XXX In the current formulation, an ImagePlan can handle [null ->
        PkgFmri] and [PkgFmri@Version1 -> PkgFmri@Version2], for a set of
        PkgFmri objects.  With a correct Action object definition, deletion
        should be able to be represented as [PkgFmri@V1 -> null].

        XXX Should we allow downgrades?  There's an "arrow of time" associated
        with the smf(5) configuration method, so it's better to direct
        manipulators to snapshot-based rollback, but if people are going to do
        "pkg delete fmri; pkg install fmri@v(n - 1)", then we'd better have a
        plan to identify when this operation is safe or unsafe."""

        def __init__(self, image, progtrack, check_cancelation,
            recursive_removal=False, filters=None, variants=None,
            noexecute=False):
                if filters is None:
                        filters = []
                self.image = image
                self.state = UNEVALUATED
                self.recursive_removal = recursive_removal
                self.progtrack = progtrack

                self.noexecute = noexecute
                if noexecute:
                        self.__intent = imagestate.INTENT_EVALUATE
                else:
                        self.__intent = imagestate.INTENT_PROCESS

                self.target_fmris = []
                self.target_rem_fmris = []
                self.pkg_plans = []
                self.target_insall_count = 0
                self.target_update_count = 0

                self.__directories = None
                self.__link_actions = None

                ifilters = [
                    "%s = %s" % (k, v)
                    for k, v in image.cfg_cache.filters.iteritems()
                ]
                self.filters = [ compile_filter(f) for f in filters + ifilters ]

                self.old_excludes = image.list_excludes()
                self.new_excludes = image.list_excludes(variants)

                self.check_cancelation = check_cancelation

                self.actuators = None

                self.update_index = True

        def __str__(self):
                if self.state == UNEVALUATED:
                        s = "UNEVALUATED:\n"
                        for t in self.target_fmris:
                                s = s + "+%s\n" % t
                        for t in self.target_rem_fmris:
                                s = s + "-%s\n" % t
                        return s

                s = "Package changes:\n"
                for pp in self.pkg_plans:
                        s = s + "%s\n" % pp

                s = s + "Actuators:\n%s" % self.actuators
                
                s = s + "Variants: %s -> %s\n" % (self.old_excludes, self.new_excludes)
                return s

        def get_plan(self, full=True):
                if full:
                        return str(self)

                output = ""
                for pp in self.pkg_plans:
                        output += "%s -> %s\n" % (pp.origin_fmri,
                            pp.destination_fmri)

                return output

        def display(self):
                for pp in self.pkg_plans:
                        msg("%s -> %s" % (pp.origin_fmri, pp.destination_fmri))
                msg("Actuators:\n%s" % self.actuators)

        def is_proposed_fmri(self, pfmri):
                for pf in self.target_fmris:
                        if self.image.fmri_is_same_pkg(pfmri, pf):
                                return not self.image.fmri_is_successor(pfmri,
                                    pf)
                return False

        def is_proposed_rem_fmri(self, pfmri):
                for pf in self.target_rem_fmris:
                        if self.image.fmri_is_same_pkg(pfmri, pf):
                                return True
                return False

        def propose_fmri(self, pfmri):
                # is a version of fmri.stem in the inventory?
                if self.image.has_version_installed(pfmri):
                        return

                #   is there a freeze or incorporation statement?
                #   do any of them eliminate this fmri version?
                #     discard

                #
                # update so that we meet any optional dependencies
                #

                pfmri = self.image.constraints.apply_constraints_to_fmri(pfmri)
                self.image.fmri_set_default_publisher(pfmri)

                # Add fmri to target list only if it (or a successor) isn't
                # there already.
                for i, p in enumerate(self.target_fmris):
                        if self.image.fmri_is_successor(pfmri, p):
                                self.target_fmris[i] = pfmri
                                break
                        if self.image.fmri_is_successor(p, pfmri):
                                break
                else:
                        self.target_fmris.append(pfmri)
                return

        def get_proposed_version(self, pfmri):
                """ Return version of fmri already proposed, or None
                if not proposed yet."""
                for p in self.target_fmris:
                        if pfmri.get_name() == p.get_name():
                                return p
                else:
                        return None

        def older_version_proposed(self, pfmri):
                # returns true if older version of this pfmri has been proposed
                # already
                for p in self.target_fmris:
                        if self.image.fmri_is_successor(pfmri, p):
                                return True
                return False

        # XXX Need to make sure that the same package isn't being added and
        # removed in the same imageplan.
        def propose_fmri_removal(self, pfmri):
                if not self.image.has_version_installed(pfmri):
                        return

                for i, p in enumerate(self.target_rem_fmris):
                        if self.image.fmri_is_successor(pfmri, p):
                                self.target_rem_fmris[i] = pfmri
                                break
                else:
                        self.target_rem_fmris.append(pfmri)

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
                for pfmri in self.gen_new_installed_pkgs():
                        m = self.image.get_manifest(pfmri)
                        for act in m.gen_actions(self.new_excludes):
                                yield act

        def gen_new_installed_actions_bytype(self, atype):
                """generates actions in new installed image"""
                for pfmri in self.gen_new_installed_pkgs():
                        m = self.image.get_manifest(pfmri)
                        for act in m.gen_actions_by_type(atype,
                            self.new_excludes):
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
                        for fmri in self.gen_new_installed_pkgs():
                                m = self.image.get_manifest(fmri)
                                for d in m.get_directories(self.new_excludes):
                                        dirs.add(os.path.normpath(d))
                        self.__directories = dirs
                return self.__directories

        def get_link_actions(self):
                """return a dictionary of hardlink action lists indexed by
                target """
                if self.__link_actions == None:
                        d = {}
                        for act in \
                            self.gen_new_installed_actions_bytype("hardlink"):
                                t = act.get_target_path()
                                if t in d:
                                        d[t].append(act)
                                else:
                                        d[t] = [act]
                self.__link_actions = d
                return self.__link_actions

        def evaluate_fmri(self, pfmri):
                self.progtrack.evaluate_progress(pfmri)
                self.image.state.set_target(pfmri, self.__intent)

                if self.check_cancelation():
                        raise api_errors.CanceledException()

                self.image.fmri_set_default_publisher(pfmri)

                m = self.image.get_manifest(pfmri)

                # check to make sure package is not tagged as being only
                # for other architecture(s)
                supported = m.get_variants("variant.arch")
                if supported and self.image.get_arch() not in supported:
                        raise api_errors.PlanCreationException(badarch=(pfmri,
                            supported, self.image.get_arch()))

                # build list of (action, fmri, constraint) of dependencies
                a_list = [
                    (a,) + a.parse(self.image, pfmri.get_name())
                    for a in m.gen_actions_by_type("depend", self.new_excludes)
                ]

                # Update constraints first to avoid problems w/ depth first
                # traversal of dependencies; we may violate an existing
                # constraint here.
                if self.image.constraints.start_loading(pfmri):
                        for a, f, constraint in a_list:
                                self.image.constraints.update_constraints(
                                    constraint)
                        self.image.constraints.finish_loading(pfmri)

                # now check what work is required
                for a, f, constraint in a_list:

                        # discover if we have an installed or proposed
                        # version of this pkg already; proposed fmris
                        # will always be newer
                        ref_fmri = self.get_proposed_version(f)
                        if not ref_fmri:
                                ref_fmri = self.image.get_version_installed(f)

                        # check if new constraint requires us to make any
                        # changes to already proposed pkgs or existing ones.
                        if not constraint.check_for_work(ref_fmri):
                                continue
                        # Apply any active optional/incorporation constraints
                        # from other packages

                        cf = self.image.constraints.apply_constraints_to_fmri(f)

                        # This will be the newest version of the specified
                        # dependency package, coming from the preferred
                        # publisher, if it's available there.  Package names
                        # specified in dependencies are treated as exact.
                        cf = self.image.inventory([ cf ], all_known=True,
                            matcher=fmri.exact_name_match, preferred=True,
                            first_only=True).next()[0]

                        # XXX LOG "adding dependency %s" % pfmri

                        #msg("adding dependency %s" % cf)

                        self.propose_fmri(cf)
                        self.evaluate_fmri(cf)

                self.image.state.set_target()

        def add_pkg_plan(self, pfmri):
                """add a pkg plan to imageplan for fully evaluated frmi"""
                m = self.image.get_manifest(pfmri)
                pp = pkgplan.PkgPlan(self.image, self.progtrack, \
                    self.check_cancelation)

                try:
                        pp.propose_destination(pfmri, m)
                except RuntimeError:
                        msg("pkg: %s already installed" % pfmri)
                        return

                pp.evaluate(self.old_excludes, self.new_excludes)

                if pp.origin_fmri:
                        self.target_update_count += 1
                else:
                        self.target_insall_count += 1

                self.pkg_plans.append(pp)

        def evaluate_fmri_removal(self, pfmri):
                # prob. needs breaking up as well
                assert self.image.has_manifest(pfmri)

                self.progtrack.evaluate_progress(pfmri)

                dependents = self.image.get_dependents(pfmri, self.progtrack)

                # Don't consider those dependencies already being removed in
                # this imageplan transaction.
                for i, d in enumerate(dependents):
                        if d in self.target_rem_fmris:
                                del dependents[i]

                if dependents and not self.recursive_removal:
                        raise api_errors.NonLeafPackageException(pfmri,
                            dependents)

                pp = pkgplan.PkgPlan(self.image, self.progtrack, \
                    self.check_cancelation)

                self.image.state.set_target(pfmri, self.__intent)
                m = self.image.get_manifest(pfmri)

                try:
                        pp.propose_removal(pfmri, m)
                except RuntimeError:
                        self.image.state.set_target()
                        msg("pkg %s not installed" % pfmri)
                        return

                pp.evaluate([], self.old_excludes)

                for d in dependents:
                        if self.is_proposed_rem_fmri(d):
                                continue
                        if not self.image.has_version_installed(d):
                                continue
                        self.target_rem_fmris.append(d)
                        self.progtrack.evaluate_progress(d)
                        self.evaluate_fmri_removal(d)

                # Post-order append will ensure topological sorting for acyclic
                # dependency graphs.  Cycles need to be arbitrarily broken, and
                # are done so in the loop above.
                self.pkg_plans.append(pp)
                self.image.state.set_target()

        def evaluate(self):
                assert self.state == UNEVALUATED

                outstring = ""

                # Operate on a copy, as it will be modified in flight.
                for f in self.target_fmris[:]:
                        self.progtrack.evaluate_progress(f)
                        try:
                                self.evaluate_fmri(f)
                        except KeyError, e:
                                outstring += "Attempting to install %s " \
                                    "causes:\n\t%s\n" % (f.get_name(), e)
                        except (ManifestRetrievalError,
                            DatastreamRetrievalError), e:
                                raise api_errors.NetworkUnavailableException(
                                    str(e))

                if outstring:
                        raise RuntimeError("No packages were installed because "
                            "package dependencies could not be satisfied\n" +
                            outstring)

                for f in self.target_fmris:
                        self.add_pkg_plan(f)
                        self.progtrack.evaluate_progress(f)

                for f in self.target_rem_fmris[:]:
                        self.evaluate_fmri_removal(f)
                        self.progtrack.evaluate_progress(f)

                # we now have a workable set of packages to add/upgrade/remove
                # now combine all actions together to create a synthetic single
                # step upgrade operation, and handle editable files moving from
                # package to package.  See theory comment in execute, below.

                self.state = EVALUATED_PKGS

                self.removal_actions = [
                    (p, src, dest)
                    for p in self.pkg_plans
                    for src, dest in p.gen_removal_actions()
                ]

                self.update_actions = [
                    (p, src, dest)
                    for p in self.pkg_plans
                    for src, dest in p.gen_update_actions()
                ]

                self.install_actions = [
                    (p, src, dest)
                    for p in self.pkg_plans
                    for src, dest in p.gen_install_actions()
                ]

                self.progtrack.evaluate_progress()

                self.actuators = actuator.Actuator()

                # iterate over copy of removals since we're modding list
                # keep track of deletion count so later use of index works
                named_removals = {}
                deletions = 0
                for i, a in enumerate(self.removal_actions[:]):
                        # remove dir removals if dir is still in final image
                        if a[1].name == "dir" and \
                            os.path.normpath(a[1].attrs["path"]) in \
                            self.get_directories():
                                del self.removal_actions[i - deletions]
                                deletions += 1
                                continue
                        # store names of files being removed under own name
                        # or original name if specified
                        if a[1].name == "file":
                                attrs = a[1].attrs
                                fname = attrs.get("original_name",
                                    "%s:%s" % (a[0].origin_fmri.get_name(),
                                    attrs["path"]))
                                named_removals[fname] = \
                                    (i - deletions,
                                    id(self.removal_actions[i-deletions][1]))

                        self.actuators.scan_removal(a[1].attrs)

                self.progtrack.evaluate_progress()

                for a in self.install_actions:
                        # In order to handle editable files that move their path
                        # or change pkgs, for all new files with original_name
                        # attribute, make sure file isn't being removed by
                        # checking removal list.  If it is, tag removal to save
                        # file, and install to recover cached version... caching
                        # is needed if directories are removed or don't exist
                        # yet.
                        if (a[2].name == "file" and "original_name" in
                            a[2].attrs and a[2].attrs["original_name"] in
                            named_removals):
                                cache_name = a[2].attrs["original_name"]
                                index = named_removals[cache_name][0]
                                assert(id(self.removal_actions[index][1]) ==
                                       named_removals[cache_name][1])
                                self.removal_actions[index][1].attrs[
                                    "save_file"] = cache_name
                                a[2].attrs["save_file"] = cache_name

                        self.actuators.scan_install(a[2].attrs)

                self.progtrack.evaluate_progress()
                # Go over update actions
                l_actions = self.get_link_actions()
                l_refresh = []
                for a in self.update_actions:
                        # For any files being updated that are the target of
                        # _any_ hardlink actions, append the hardlink actions
                        # to the update list so that they are not broken.
                        if a[2].name == "file":
                                path = a[2].attrs["path"]
                                if path in l_actions:
                                        l_refresh.extend([
                                            (a[0], l, l)
                                            for l in l_actions[path]
                                        ])

                        # scan both old and new actions
                        # repairs may result in update action w/o orig action
                        if a[1]:
                                self.actuators.scan_update(a[1].attrs)
                        self.actuators.scan_update(a[2].attrs)
                self.update_actions.extend(l_refresh)

                # sort actions to match needed processing order
                self.removal_actions.sort(key = lambda obj:obj[1], reverse=True)
                self.update_actions.sort(key = lambda obj:obj[2])
                self.install_actions.sort(key = lambda obj:obj[2])

                remove_npkgs = len(self.target_rem_fmris)
                npkgs = 0
                nfiles = 0
                nbytes = 0
                nactions = 0
                for p in self.pkg_plans:
                        nf, nb = p.get_xferstats()
                        nbytes += nb
                        nfiles += nf
                        nactions += p.get_nactions()

                        # It's not perfectly accurate but we count a download
                        # even if the package will do zero data transfer.  This
                        # makes the pkg stats consistent between download and
                        # install.
                        npkgs += 1

                self.progtrack.download_set_goal(npkgs, nfiles, nbytes)

                self.progtrack.evaluate_done(self.target_insall_count, \
                    self.target_update_count, remove_npkgs)

                self.state = EVALUATED_OK

        def nothingtodo(self):
                """ Test whether this image plan contains any work to do """

                return not self.pkg_plans

        def preexecute(self):
                """Invoke the evaluated image plan
                preexecute, execute and postexecute
                execute actions need to be sorted across packages
                """

                assert self.state == EVALUATED_OK

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
                        try:
                                self.image.update_index_dir()
                                ind = indexer.Indexer(self.image,
                                    self.image.get_manifest,
                                    self.image.get_manifest_path,
                                    progtrack=self.progtrack,
                                    excludes=self.old_excludes)
                                if not ind.check_index_existence():
                                        # XXX Once we have a framework for
                                        # emitting a message to the user in
                                        # this spot in the code, we should tell
                                        # them something has gone wrong so that
                                        # we continue to get feedback to
                                        # allow us to debug the code.
                                        ind.rebuild_index_from_scratch(
                                            self.image.gen_installed_pkgs())
                                else:
                                        try:
                                                ind.check_index_has_exactly_fmris(
                                                        self.image.gen_installed_pkg_names())
                                        except se.IncorrectIndexFileHash:
                                                ind.rebuild_index_from_scratch(
                                                        self.image.gen_installed_pkgs())
                        except se.IndexingException:
                                # If there's a problem indexing, we want to
                                # attempt to finish the installation anyway. If
                                # there's a problem updating the index on the
                                # new image, that error needs to be
                                # communicated to the user.
                                pass

                try:
                        try:
                                for p in self.pkg_plans:
                                        p.preexecute()

                                for p in self.pkg_plans:
                                        p.download()
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                raise

                        self.progtrack.download_done()
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

                self.actuators.exec_prep(self.image)

                self.actuators.exec_pre_actuators(self.image)

                try:
                        try:

                                # execute removals

                                self.progtrack.actions_set_goal("Removal Phase",
                                    len(self.removal_actions))
                                for p, src, dest in self.removal_actions:
                                        p.execute_removal(src, dest)
                                        self.progtrack.actions_add_progress()
                                self.progtrack.actions_done()

                                # execute installs

                                self.progtrack.actions_set_goal("Install Phase",
                                    len(self.install_actions))

                                for p, src, dest in self.install_actions:
                                        p.execute_install(src, dest)
                                        self.progtrack.actions_add_progress()
                                self.progtrack.actions_done()

                                # execute updates

                                self.progtrack.actions_set_goal("Update Phase",
                                    len(self.update_actions))

                                for p, src, dest in self.update_actions:
                                        p.execute_update(src, dest)
                                        self.progtrack.actions_add_progress()

                                self.progtrack.actions_done()

                                # handle any postexecute operations

                                for p in self.pkg_plans:
                                        p.postexecute()

                                self.image.clear_pkg_state()
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES or \
                                    e.errno == errno.EPERM:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                raise
                except:
                        self.actuators.exec_fail_actuators(self.image)
                        raise
                else:
                        self.actuators.exec_post_actuators(self.image)

                self.state = EXECUTED_OK

                # reduce memory consumption

                del self.removal_actions
                del self.update_actions
                del self.install_actions

                del self.target_rem_fmris
                del self.target_fmris
                del self.__directories

                del self.actuators

                # Perform the incremental update to the search indexes
                # for all changed packages
                if self.update_index:
                        plan_info = [
                            (p.destination_fmri, p.origin_fmri)
                            for p
                            in self.pkg_plans
                        ]
                        del self.pkg_plans
                        self.progtrack.actions_set_goal("Index Phase",
                            len(plan_info))
                        self.image.update_index_dir()
                        ind = indexer.Indexer(self.image,
                            self.image.get_manifest,
                            self.image.get_manifest_path,
                            progtrack=self.progtrack,
                            excludes=self.new_excludes)
                        try:
                                ind.client_update_index((self.filters,
                                    plan_info), self.image)
                        except (KeyboardInterrupt,
                            se.ProblematicPermissionsIndexException):
                                # ProblematicPermissionsIndexException is
                                # included here as there's little chance that
                                # trying again will fix this problem.
                                raise
                        except Exception, e:
                                # It's important to delete and rebuild from
                                # scratch rather than using the existing
                                # indexer because otherwise the state will
                                # become confused.
                                del(ind)
                                # XXX Once we have a framework for emitting a
                                # message to the user in this spot in the code,
                                # we should tell them something has gone wrong
                                # so that we continue to get feedback to allow
                                # us to debug the code.
                                ind = indexer.Indexer(self.image,
                                    self.image.get_manifest,
                                    self.image.get_manifest_path,
                                    progtrack=self.progtrack,
                                    excludes=self.new_excludes)
                                ind.rebuild_index_from_scratch(
                                    self.image.gen_installed_pkgs())
