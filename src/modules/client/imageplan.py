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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import pkg.fmri as fmri
import os.path
import pkg.client.pkgplan as pkgplan
import pkg.client.retrieve as retrieve # XXX inventory??
import pkg.version as version
from pkg.client.filter import compile_filter

UNEVALUATED = 0
EVALUATED_OK = 1
EVALUATED_ERROR = 2
EXECUTED_OK = 3
EXECUTED_ERROR = 4

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

                self.directories = None

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
                        print "%s -> %s" % (pp.origin_fmri, pp.destination_fmri)

 
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
                assert self.state == EVALUATED_OK
                fmri_set = set(self.image.gen_installed_pkgs())

                for p in self.pkg_plans:
                        p.update_pkg_set(fmri_set)

                for fmri in fmri_set:
                        yield fmri

        def get_directories(self):
                """ return set of all directories in target image """
                # always consider var and var/pkg fixed in image....
                # XXX should be fixed for user images
                if self.directories == None:
                        dirs = set(["var/pkg", "var/sadm/install"])
                        dirs.update(
                            [ 
                                d
                                for fmri in self.gen_new_installed_pkgs()
                                for act in self.image.get_manifest(fmri, filtered = True).actions
                                for d in act.directory_references()
                        ])
                        self.directories = self.image.expanddirs(dirs)

                return self.directories

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
        
                        self.image.fmri_set_default_authority(f)

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

                        # XXX Do we want implicit freezing based on the portions
                        # of a version present?
                        mvs = self.image.get_matching_fmris(a.attrs["fmri"], 
                            constraint = version.CONSTRAINT_AUTO)

                        # fmris in mvs are sorted with latest version first, 
                        # so take the newest entry that still matches fmri
                        # within the above constraint
                        cf = mvs[0]

                        # XXX LOG "adding dependency %s" % pfmri

                        #print "adding dependency %s" % cf

                        self.propose_fmri(cf)
                        self.evaluate_fmri(cf)

        def add_pkg_plan(self, pfmri):
                """add a pkg plan to imageplan for fully evaluated frmi"""
                m = self.image.get_manifest(pfmri)
                pp = pkgplan.PkgPlan(self.image, self.progtrack)

                try:
                        pp.propose_destination(pfmri, m)
                except RuntimeError:
                        print "pkg: %s already installed" % pfmri
                        return

                pp.evaluate(self.filters)

                self.pkg_plans.append(pp)

        def evaluate_fmri_removal(self, pfmri):
                # prob. needs breaking up as well 
                assert self.image.has_manifest(pfmri)

                dependents = self.image.get_dependents(pfmri)

                # Don't consider those dependencies already being removed in
                # this imageplan transaction.
                for i, d in enumerate(dependents):
                        if fmri.PkgFmri(d, None) in self.target_rem_fmris:
                                del dependents[i]

                if dependents and not self.recursive_removal:
                        # XXX Module function is printing, should raise or have
                        # complex return.
                        print """\
Cannot remove '%s' due to the following packages that directly depend on it:"""\
                        % pfmri
                        for d in dependents:
                                print " ", fmri.PkgFmri(d, "")
                        return

                m = self.image.get_manifest(pfmri)

                pp = pkgplan.PkgPlan(self.image, self.progtrack)

                try:
                        pp.propose_removal(pfmri, m)
                except RuntimeError:
                        print "pkg %s not installed" % pfmri
                        return

                pp.evaluate()

                for d in dependents:
                        rf = fmri.PkgFmri(d, None)
                        if self.is_proposed_rem_fmri(rf):
                                print "%s is already proposed for removal" % rf
                                continue
                        if not self.image.has_version_installed(rf):
                                print "%s is not installed" % rf
                                continue
                        self.target_rem_fmris.append(rf)
                        self.evaluate_fmri_removal(rf)

                # Post-order append will ensure topological sorting for acyclic
                # dependency graphs.  Cycles need to be arbitrarily broken, and
                # are done so in the loop above.
                self.pkg_plans.append(pp)

        def evaluate(self):
                assert self.state == UNEVALUATED

                self.progtrack.evaluate_start()

                # Operate on a copy, as it will be modified in flight.
                for f in self.target_fmris[:]:
                        self.progtrack.evaluate_progress()
                        self.evaluate_fmri(f)

                for f in self.target_fmris:
                        self.add_pkg_plan(f)
                        self.progtrack.evaluate_progress()

                for f in self.target_rem_fmris[:]:
                        self.evaluate_fmri_removal(f)
                        self.progtrack.evaluate_progress()

                self.progtrack.evaluate_done()

                self.state = EVALUATED_OK
                
        def nothingtodo(self):
		""" Test whether this image plan contains any work to do """

		return not self.pkg_plans

        def execute(self):
                """Invoke the evaluated image plan
                preexecute, execute and postexecute
                execute actions need to be sorted across packages
                """
                
                assert self.state == EVALUATED_OK

		if self.nothingtodo():
			self.state = EXECUTED_OK
			return

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

                for p in self.pkg_plans:
                        p.preexecute()

                self.progtrack.download_done()

                #
                # now we're ready to start install.  At this point we
                # should do a merge between removals and installs so that
                # any actions moving from pkg to pkg are seen as updates rather
                # than removal and re-install, since these two have separate
                # semanticas.
                #
                # General install method is removals, updates and then 
                # installs.  User and group installs are moved to be ahead of
                # updates so that a package that adds a new user can specify
                # that owner for existing files.

                # generate list of removal actions, sort and execute

                actions = [ (p, src, dest)
                            for p in self.pkg_plans
                            for src, dest in p.gen_removal_actions()
                            ]

                actions.sort(key = lambda obj:obj[1], reverse=True)

                self.progtrack.actions_set_goal("Removal Phase", len(actions))
                for p, src, dest in actions:
                        p.execute_removal(src, dest)
                        self.progtrack.actions_add_progress()
                self.progtrack.actions_done()

                # generate list of update actions, sort and execute

                update_actions = [ (p, src, dest)
                            for p in self.pkg_plans
                            for src, dest in p.gen_update_actions()
                            ]

                install_actions = [ (p, src, dest)
                            for p in self.pkg_plans
                            for src, dest in p.gen_install_actions()
                            ]

                # move any user/group actions into modify list to 
                # permit package to add user/group and change existing
                # files to that user/group in a single update
                # iterate over copy since we're modify install_actions
                
                for a in install_actions[:]:
                        if a[2].name == "user" or a[2].name == "group":
                                update_actions.append(a)
                                install_actions.remove(a)

                update_actions.sort(key = lambda obj:obj[2])

                self.progtrack.actions_set_goal("Update Phase", len(update_actions))

                for p, src, dest in update_actions:
                        p.execute_update(src, dest)
                        self.progtrack.actions_add_progress()

                self.progtrack.actions_done()

                # generate list of install actions, sort and execute

                install_actions.sort(key = lambda obj:obj[2])

                self.progtrack.actions_set_goal("Install Phase", len(install_actions))

                for p, src, dest in install_actions:
                        p.execute_install(src, dest)
                        self.progtrack.actions_add_progress()
                self.progtrack.actions_done()

                # handle any postexecute operations

                for p in self.pkg_plans:
                        p.postexecute()

                self.state = EXECUTED_OK

