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

import os
import re
import urllib

import pkg.catalog as catalog

class PkgPlan(object):
        """A package plan takes two package FMRIs and an Image, and produces the
        set of actions required to take the Image from the origin FMRI to the
        destination FMRI."""

        def __init__(self, image):
                self.origin_fmri = None
                self.destination_fmri = None
                self.origin_mfst = None
                self.destination_mfst = None

                self.image = image

                self.actions = []

        def set_origin(self, fmri):
                self.origin_fmri = fmri
                self.origin_mfst = manifest.retrieve(fmri)

        def propose_destination(self, fmri, manifest):
                self.destination_fmri = fmri
                self.destination_mfst = manifest

                if os.path.exists("%s/pkg/%s/installed" % (self.image.imgdir,
                    fmri.get_dir_path())):
                        raise RuntimeError, "already installed"

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
                # if origin unset, determine if we're dealing with an previously
                # installed version or if we're dealing with the null package
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
                return

        def preexecute(self):
                # retrieval step
                for a in self.actions:
                        a.preinstall(self.image)
                return

        def execute(self):
                # record that we are in an intermediate state
                for a in self.actions:
                        a.install(self.image)
                return

        def postexecute(self):
                # record that package states are consistent
                for a in self.actions:
                        a.postinstall()

                if self.origin_fmri != None:
                        os.unlink("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.origin_fmri.get_dir_path()))

                file("%s/pkg/%s/installed" % (self.image.imgdir,
                    self.destination_fmri.get_dir_path()), "w")

                return
