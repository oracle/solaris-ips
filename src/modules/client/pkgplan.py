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

# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import errno
import os
import re
import urllib

import pkg.catalog as catalog

class PkgPlan(object):
        """A package plan takes two package FMRIs and an Image, and produces the
        set of actions required to take the Image from the origin FMRI to the
        destination FMRI.
        
        If the destination FMRI is None, the package is removed.
        """

        def __init__(self, image):
                self.origin_fmri = None
                self.destination_fmri = None
                self.origin_mfst = None
                self.destination_mfst = None

                self.image = image

                self.actions = []

        def __str__(self):
                return "%s -> %s" % (self.origin_fmri, self.destination_fmri)

        def set_origin(self, fmri):
                self.origin_fmri = fmri
                self.origin_mfst = manifest.retrieve(fmri)

        def propose_destination(self, fmri, manifest):
                self.destination_fmri = fmri
                self.destination_mfst = manifest

                if os.path.exists("%s/pkg/%s/installed" % (self.image.imgdir,
                    fmri.get_dir_path())):
                        raise RuntimeError, "already installed"

        def propose_removal(self, fmri, manifest):
                self.origin_fmri = fmri
                self.origin_mfst = manifest

                if not os.path.exists("%s/pkg/%s/installed" % \
                    (self.image.imgdir, fmri.get_dir_path())):
                        raise RuntimeError, "not installed"

        def is_valid(self):
                if self.origin_fmri == None:
                        return True

                if not self.origin_fmri.is_same_pkg(self.destination_fmri):
                        return False

                if self.origin_fmri > self.destination_fmri:
                        return False

                return True

        def get_actions(self):
                return []

        def evaluate(self):
                """Determine the actions required to transition the package."""
                # if origin unset, determine if we're dealing with an previously
                # installed version or if we're dealing with the null package
                #
                # XXX Perhaps make the pkgplan creator make this explicit, so we
                # don't have to check?
                f = None
                if self.origin_fmri == None:
                        try:
                                f = self.image.get_version_installed(
                                    self.destination_fmri)
                                self.origin_fmri = f
                        except LookupError:
                                pass

                # if null package, then our plan is the set of actions for the
                # destination version
                if self.origin_fmri == None:
                        self.actions = self.destination_mfst.actions
                elif self.destination_fmri == None:
                        # XXX
                        self.actions = sorted(self.origin_mfst.actions,
                            reverse = True)
                else:
                        # if a previous package, then our plan is derived from
                        # the set differences between the previous manifest's
                        # actions and the union of the destination manifest's
                        # actions with the critical actions of the critical
                        # versions in the version interval between origin and
                        # destination.
                        if not self.image.has_manifest(self.origin_fmri):
                                retrieve.get_manifest(self.image,
                                    self.origin_fmri)

                        self.origin_mfst = self.image.get_manifest(
                            self.origin_fmri)

                        self.actions = self.destination_mfst.difference(
                            self.origin_mfst)

        def preexecute(self):
                """Perform actions required prior to installation or removal of a package.
                
                This method executes each action's preremove() or preinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                # retrieval step
                if self.destination_fmri == None:
                        os.unlink("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.origin_fmri.get_dir_path()))

                for a in self.actions:
                        if self.destination_fmri == None:
                                a.preremove(self.image)
                        else:
                                a.preinstall(self.image)

        def execute(self):
                """Perform actions for installation or removal of a package.
                
                This method executes each action's remove() or install()
                methods.
                """
                # record that we are in an intermediate state
                for a in self.actions:
                        if self.destination_fmri == None:
                                a.remove(self.image)
                        else:
                                a.install(self.image)

        def postexecute(self):
                """Perform actions required after installation or removal of a package.
                
                This method executes each action's postremove() or postinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                # record that package states are consistent
                for a in self.actions:
                        if self.destination_fmri == None:
                                a.postremove()
                        else:
                                a.postinstall()

                # XXX should this just go in preexecute?
                if self.origin_fmri != None and self.destination_fmri != None:
                        os.unlink("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.origin_fmri.get_dir_path()))

                if self.destination_fmri != None:
                        file("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.destination_fmri.get_dir_path()), "w")

        def make_indices(self):
                """Create the reverse index databases for a particular package.
                
                These are the databases mapping packaging object attribute
                values back to their corresponding packages, allowing the
                packaging system to look up a package based on, say, the
                basename of a file that was installed.

                XXX Need a method to remove what we put down here.
                """

                # XXX bail out, for now.
                if self.destination_fmri == None:
                        return

                target = os.path.join("..", "..", "..", "pkg",
                    self.destination_fmri.get_dir_path())

                gen = (
                    (k, v)
                    for action in self.actions
                    for k, v in action.generate_indices().iteritems()
                )

                for idx, val in gen:
                        idxdir = os.path.join(self.image.imgdir, "index", idx)

                        try:
                                os.makedirs(idxdir)
                        except OSError, e:
                                if e.errno != errno.EEXIST:
                                        raise

                        if not isinstance(val, list):
                                val = [ val ]

                        for v in val:
                                dir = os.path.join(idxdir, v)

                                try:
                                        os.makedirs(dir)
                                except OSError, e:
                                        if e.errno != errno.EEXIST:
                                                raise

                                link = os.path.join(dir,
                                    self.destination_fmri.get_url_path())

                                if not os.path.lexists(link):
                                        os.symlink(target, link)
