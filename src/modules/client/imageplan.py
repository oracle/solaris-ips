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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import pkg.fmri as fmri
import pkg.client.pkgplan as pkgplan
import pkg.client.retrieve as retrieve # XXX inventory??
import pkg.version as version
import pkg.indexer as indexer
import pkg.search_errors as se
from pkg.client.filter import compile_filter
from pkg.misc import msg
from pkg.misc import CLIENT_DEFAULT_MEM_USE_KB

UNEVALUATED       = 0 # nothing done yet
EVALUATED_PKGS    = 1 # established fmri changes
EVALUATED_OK      = 2 # ready to execute
PREEXECUTED_OK    = 3 # finished w/ preexecute
PREEXECUTED_ERROR = 4 # whoops
EXECUTED_OK       = 5 # finished execution
EXECUTED_ERROR    = 6 # failed

class NonLeafPackageException(Exception):
        """Removal of a package which satisfies dependencies has been attempted.
        
        The first argument to the constructor is the FMRI which we tried to
        remove, and is available as the "fmri" member of the exception.  The
        second argument is the list of dependent packages that prevent the
        removal of the package, and is available as the "dependents" member.
        """

        def __init__(self, *args):
                Exception.__init__(self, *args)

                self.fmri = args[0]
                self.dependents = args[1]

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

        def __init__(self, image, progtrack, recursive_removal = False, filters = []):
                self.image = image
                self.state = UNEVALUATED
                self.recursive_removal = recursive_removal
                self.progtrack = progtrack

                self.target_fmris = []
                self.target_rem_fmris = []
                self.pkg_plans = []

                self.__directories = None
                self.__link_actions = None

                ifilters = [
                    "%s = %s" % (k, v)
                    for k, v in image.cfg_cache.filters.iteritems()
                ]
                self.filters = [ compile_filter(f) for f in filters + ifilters ]

        def __str__(self):
                if self.state == UNEVALUATED:
                        s = "UNEVALUATED:\n"
                        for t in self.target_fmris:
                                s = s + "+%s\n" % t
                        for t in self.target_rem_fmris:
                                s = s + "-%s\n" % t
                        return s

                s = ""
                for pp in self.pkg_plans:
                        s = s + "%s\n" % pp
                return s

        def display(self):
                for pp in self.pkg_plans:
                        msg("%s -> %s" % (pp.origin_fmri, pp.destination_fmri))


        def is_proposed_fmri(self, fmri):
                for pf in self.target_fmris:
                        if self.image.fmri_is_same_pkg(fmri, pf):
                                return not self.image.fmri_is_successor(fmri, pf)
                return False

        def is_proposed_rem_fmri(self, fmri):
                for pf in self.target_rem_fmris:
                        if self.image.fmri_is_same_pkg(fmri, pf):
                                return True
                return False

        def propose_fmri(self, fmri):
                # is a version of fmri.stem in the inventory?
                if self.image.has_version_installed(fmri):
                        return

                #   is there a freeze or incorporation statement?
                #   do any of them eliminate this fmri version?
                #     discard

                #
                # update so that we meet any optional dependencies
                #

                fmri = self.image.apply_optional_dependencies(fmri)

                # Add fmri to target list only if it (or a successor) isn't
                # there already.
                for i, p in enumerate(self.target_fmris):
                        if self.image.fmri_is_successor(fmri, p):
                                self.target_fmris[i] = fmri
                                break
                        if self.image.fmri_is_successor(p, fmri):
                                break
                else:
                        self.target_fmris.append(fmri)

                return

        def older_version_proposed(self, fmri):
                # returns true if older version of this fmri has been
                # proposed already
                for p in self.target_fmris:
                        if self.image.fmri_is_successor(fmri, p):
                                return True
                return False

        # XXX Need to make sure that the same package isn't being added and
        # removed in the same imageplan.
        def propose_fmri_removal(self, fmri):
                if not self.image.has_version_installed(fmri):
                        return

                for i, p in enumerate(self.target_rem_fmris):
                        if self.image.fmri_is_successor(fmri, p):
                                self.target_rem_fmris[i] = fmri
                                break
                else:
                        self.target_rem_fmris.append(fmri)

        def gen_new_installed_pkgs(self):
                """ generates all the actions in the new set of installed pkgs"""
                assert self.state >= EVALUATED_PKGS
                fmri_set = set(self.image.gen_installed_pkgs())

                for p in self.pkg_plans:
                        p.update_pkg_set(fmri_set)

                for fmri in fmri_set:
                        yield fmri

        def gen_new_installed_actions(self):
                """generates actions in new installed image"""

                for fmri in self.gen_new_installed_pkgs():
                        for act in self.image.get_manifest(fmri, 
                            filtered=True).actions:
                                yield act

        def get_directories(self):
                """ return set of all directories in target image """
                # always consider var and var/pkg fixed in image....
                # XXX should be fixed for user images
                if self.__directories == None:
                        dirs = set(["var/pkg", "var/sadm/install"])
                        dirs.update(
                            [
                                os.path.normpath(d)
                                for act in self.gen_new_installed_actions()
                                for d in act.directory_references()
                        ])
                        self.__directories = self.image.expanddirs(dirs)

                return self.__directories

        def get_link_actions(self):
                """return a dictionary of hardlink action lists indexed by
                target """
                if self.__link_actions == None:
                        d = {}
                        for act in self.gen_new_installed_actions():
                                if act.name == "hardlink":
                                        t = act.get_target_path()
                                        if t in d:
                                                d[t].append(act)
                                        else:
                                                d[t] = [act]
                        self.__link_actions = d
                return self.__link_actions
                
        def evaluate_fmri(self, pfmri):

                self.progtrack.evaluate_progress()
                m = self.image.get_manifest(pfmri)

                # [manifest] examine manifest for dependencies
                for a in m.actions:
                        if a.name != "depend":
                                continue

                        type = a.attrs["type"]

                        f = fmri.PkgFmri(a.attrs["fmri"],
                            self.image.attrs["Build-Release"])

                        if self.image.has_version_installed(f) and \
                                    type != "exclude":
                                continue

                        # XXX This alone only prevents infinite recursion when a
                        # cycle member is on the commandline, as we never update
                        # target_fmris.  Is target_fmris supposed to be just
                        # what was specified on the commandline, or include what
                        # we've found while processing dependencies?
                        # XXX probably should just use propose_fmri() here
                        # instead of this and the has_version_installed() call
                        # above.
                        if self.is_proposed_fmri(f):
                                continue

                        # XXX LOG  "%s not in pending transaction;
                        # checking catalog" % f

                        required = True
                        excluded = False
                        if type == "optional" and \
                            not self.image.attrs["Policy-Require-Optional"]:
                                required = False
                        elif type == "transfer" and \
                            not self.image.older_version_installed(f):
                                required = False
                        elif type == "exclude":
                                excluded = True
                        elif type == "incorporate":
                                self.image.update_optional_dependency(f)
                                if self.image.older_version_installed(f) or \
                                    self.older_version_proposed(f):
                                        required = True
                                else:
                                        required = False

                        if not required:
                                continue

                        if excluded:
                                raise RuntimeError, "excluded by '%s'" % f

                        # treat-as-required, treat-as-required-unless-pinned,
                        # ignore
                        # skip if ignoring
                        #     if pinned
                        #       ignore if treat-as-required-unless-pinned
                        #     else
                        #       **evaluation of incorporations**
                        #     [imageplan] pursue installation of this package
                        #     -->
                        #     backtrack or reset??

                        # This will be the newest version of the specified
                        # dependency package, coming from the preferred
                        # authority, if it's available there.
                        cf = self.image.inventory([ a.attrs["fmri"] ],
                            all_known = True, preferred = True,
                            first_only = True).next()[0]

                        # XXX LOG "adding dependency %s" % pfmri

                        #msg("adding dependency %s" % cf)

                        self.propose_fmri(cf)
                        self.evaluate_fmri(cf)

        def add_pkg_plan(self, pfmri):
                """add a pkg plan to imageplan for fully evaluated frmi"""
                m = self.image.get_manifest(pfmri)
                pp = pkgplan.PkgPlan(self.image, self.progtrack)

                try:
                        pp.propose_destination(pfmri, m)
                except RuntimeError:
                        msg("pkg: %s already installed" % pfmri)
                        return

                pp.evaluate(self.filters)

                self.pkg_plans.append(pp)

        def evaluate_fmri_removal(self, pfmri):
                # prob. needs breaking up as well
                assert self.image.has_manifest(pfmri)

                self.progtrack.evaluate_progress()

                dependents = self.image.get_dependents(pfmri, self.progtrack)

                # Don't consider those dependencies already being removed in
                # this imageplan transaction.
                for i, d in enumerate(dependents):
                        if d in self.target_rem_fmris:
                                del dependents[i]

                if dependents and not self.recursive_removal:
                        raise NonLeafPackageException(pfmri, dependents)

                m = self.image.get_manifest(pfmri)

                pp = pkgplan.PkgPlan(self.image, self.progtrack)

                try:
                        pp.propose_removal(pfmri, m)
                except RuntimeError:
                        msg("pkg %s not installed" % pfmri)
                        return

                pp.evaluate()

                for d in dependents:
                        if self.is_proposed_rem_fmri(d):
                                continue
                        if not self.image.has_version_installed(d):
                                continue
                        self.target_rem_fmris.append(d)
                        self.progtrack.evaluate_progress()
                        self.evaluate_fmri_removal(d)

                # Post-order append will ensure topological sorting for acyclic
                # dependency graphs.  Cycles need to be arbitrarily broken, and
                # are done so in the loop above.
                self.pkg_plans.append(pp)

        def evaluate(self):
                assert self.state == UNEVALUATED

                self.progtrack.evaluate_start()

                outstring = ""

                # Operate on a copy, as it will be modified in flight.
                for f in self.target_fmris[:]:
                        self.progtrack.evaluate_progress()
                        try:
                                self.evaluate_fmri(f)
                        except KeyError, e:
                                outstring += "Attemping to install %s causes:\n\t%s\n" % \
                                    (f.get_name(), e)

                if outstring:
                        raise RuntimeError("No packages were installed because "
                            "package dependencies could not be satisfied\n" +
                            outstring)

                for f in self.target_fmris:
                        self.add_pkg_plan(f)
                        self.progtrack.evaluate_progress()

                for f in self.target_rem_fmris[:]:
                        self.evaluate_fmri_removal(f)
                        self.progtrack.evaluate_progress()

                # we now have a workable set of packages to add/upgrade/remove
                # now combine all actions together to create a synthetic single
                # step upgrade operation, and handle editable files moving from
                # package to package.  See theory comment in execute, below.

                self.state = EVALUATED_PKGS

                self.removal_actions = [ (p, src, dest)
                                         for p in self.pkg_plans
                                         for src, dest in p.gen_removal_actions()
                ]

                self.update_actions = [ (p, src, dest)
                                        for p in self.pkg_plans
                                        for src, dest in p.gen_update_actions()
                ]

                self.install_actions = [ (p, src, dest)
                                         for p in self.pkg_plans
                                         for src, dest in p.gen_install_actions()
                ]

                self.progtrack.evaluate_progress()

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
                                    "%s:%s" % (a[0].origin_fmri.get_name(), attrs["path"]))
                                named_removals[fname] = \
                                    (i - deletions,
                                    id(self.removal_actions[i-deletions][1]))

                self.progtrack.evaluate_progress()

                for a in self.install_actions:
                        # In order to handle editable files that move their path or
                        # change pkgs, for all new files with original_name attribute,
                        # make sure file isn't being removed by checking removal list.
                        # if it is, tag removal to save file, and install to recover
                        # cached version... caching is needed if directories
                        # are removed or don't exist yet.
                        if a[2].name == "file" and "original_name" in a[2].attrs and \
                            a[2].attrs["original_name"] in named_removals:
                                cache_name = a[2].attrs["original_name"]
                                index = named_removals[cache_name][0]
                                assert(id(self.removal_actions[index][1]) == 
                                       named_removals[cache_name][1])
                                self.removal_actions[index][1].attrs["save_file"] = \
                                    cache_name
                                a[2].attrs["save_file"] = cache_name

                self.progtrack.evaluate_progress()
                # Go over update actions
                l_actions = self.get_link_actions()
                l_refresh = []
                for a in self.update_actions:
                        # for any files being updated that are the target of
                        # _any_ hardlink actions, append the hardlink actions
                        # to the update list so that they are not broken...
                        if a[2].name == "file": 
                                path = a[2].attrs["path"]
                                if path in l_actions:
                                        l_refresh.extend([(a[0], l, l) for l in l_actions[path]])
                self.update_actions.extend(l_refresh)

                # sort actions to match needed processing order
                self.removal_actions.sort(key = lambda obj:obj[1], reverse=True)
                self.update_actions.sort(key = lambda obj:obj[2])
                self.install_actions.sort(key = lambda obj:obj[2])

                self.progtrack.evaluate_done()

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
                # the function will work correctly.
                try:
                        self.image.update_index_dir()
                        ind = indexer.Indexer(self.image.index_dir,
                            CLIENT_DEFAULT_MEM_USE_KB, progtrack=self.progtrack)
                        ind.check_index(self.image.get_fmri_manifest_pairs(),
                            force_rebuild=False)
                except (KeyboardInterrupt,
                    se.ProblematicPermissionsIndexException):
                        # ProblematicPermissionsIndexException is included here
                        # as there's little chance that trying again will fix
                        # this problem.
                        raise
                except Exception, e:
                        # XXX Once we have a framework for emitting a message
                        # to the user in this spot in the code, we should tell
                        # them something has gone wrong so that we continue to
                        # get feedback to allow us to debug the code.
                        self._index_exception = e
                        del(ind)
                        self.image.rebuild_search_index(self.progtrack)

                npkgs = 0
                nfiles = 0
                nbytes = 0
                nactions = 0
                try:
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

                        for p in self.pkg_plans:
                                p.preexecute()

                        for p in self.pkg_plans:
                                p.download()

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
                # 1) All non-directory actions (files, users, hardlinks, symbolic
                # links, etc.) must appear in only a single installed package. 
                #
                # 2) All installed packages must be consistent in their view of
                # action types; if /usr/openwin is a directory in one package, it
                # must be a directory in all packages, never a symbolic link.  This
                # includes implicitly defined directories.
                # 
                # A key goal in IPS is to be able to undergo an arbtrary transformation
                # in package contents in a single step.  Packages must be able to exchange
                # files, convert directories to symbolic links, etc.; so long as the start
                # and end states meet the above two constraints IPS must be able to transition
                # between the states directly.  This leads to the following:
                # 
                # 1) All actions must be ordered across packages; packages cannot be updated 
                #    one at a time.
                #
                #    This is readily apparent when one considers two packages exchanging 
                #    files in their new versions; in each case the package now owning the
                #    file must be installed last, but it is not possible for each package to
                #    to be installed before the other.  Clearly, all the removals must be done 
                #    first, followed by the installs and updates.
                #
                # 2) Installs of new actions must preceed updates of existing ones.
                #    
                #    In order to accomodate changes of file ownership of existing files
                #    to a newly created user, it is necessary for the installation of that
                #    user to preceed the update of files to reflect their new ownership.
                #

                if self.nothingtodo():
                        self.state = EXECUTED_OK
                        return

                # execute removals

                self.progtrack.actions_set_goal("Removal Phase", len(self.removal_actions))
                for p, src, dest in self.removal_actions:
                        p.execute_removal(src, dest)
                        self.progtrack.actions_add_progress()
                self.progtrack.actions_done()

                # execute installs

                self.progtrack.actions_set_goal("Install Phase", len(self.install_actions))

                for p, src, dest in self.install_actions:
                        p.execute_install(src, dest)
                        self.progtrack.actions_add_progress()
                self.progtrack.actions_done()

                # execute updates

                self.progtrack.actions_set_goal("Update Phase", len(self.update_actions))

                for p, src, dest in self.update_actions:
                        p.execute_update(src, dest)
                        self.progtrack.actions_add_progress()

                self.progtrack.actions_done()



                # handle any postexecute operations

                for p in self.pkg_plans:
                        p.postexecute()
                        
                self.state = EXECUTED_OK
                
                # reduce memory consumption

                del self.removal_actions
                del self.update_actions
                del self.install_actions

                del self.target_rem_fmris
                del self.target_fmris
                del self.__directories
                
                # Perform the incremental update to the search indexes
                # for all changed packages
                plan_info = []
                for p in self.pkg_plans:
                        d_fmri = p.destination_fmri
                        d_manifest_path = None
                        if d_fmri:
                                d_manifest_path = \
                                    self.image.get_manifest_path(d_fmri)
                        o_fmri = p.origin_fmri
                        o_manifest_path = None
                        o_filter_file = None
                        if o_fmri:
                                o_manifest_path = \
                                    self.image.get_manifest_path(o_fmri)
                        plan_info.append((d_fmri, d_manifest_path, o_fmri,
                                          o_manifest_path))
                del self.pkg_plans
                self.progtrack.actions_set_goal("Index Phase", len(plan_info))
                try:
                        self.image.update_index_dir()
                        ind = indexer.Indexer(self.image.index_dir,
                            CLIENT_DEFAULT_MEM_USE_KB, progtrack=self.progtrack)
                        ind.client_update_index((self.filters, plan_info))
                except (KeyboardInterrupt,
                    se.ProblematicPermissionsIndexException):
                        # ProblematicPermissionsIndexException is included here
                        # as there's little chance that trying again will fix
                        # this problem.
                        raise
                except Exception, e:
                        del(ind)
                        # XXX Once we have a framework for emitting a message
                        # to the user in this spot in the code, we should tell
                        # them something has gone wrong so that we continue to
                        # get feedback to allow us to debug the code.
                        self.image.rebuild_search_index(self.progtrack)
