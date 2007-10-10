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

import pkg.manifest as manifest
import pkg.client.filelist as filelist

class PkgPlan(object):
        """A package plan takes two package FMRIs and an Image, and produces the
        set of actions required to take the Image from the origin FMRI to the
        destination FMRI.

        If the destination FMRI is None, the package is removed.
        """

        def __init__(self, image):
                self.origin_fmri = None
                self.destination_fmri = None
                self.origin_mfst = manifest.null
                self.destination_mfst = manifest.null

                self.image = image

                self.actions = []

        def __str__(self):
                s = "%s -> %s\n" % (self.origin_fmri, self.destination_fmri)

                for src, dest in self.actions:
                        s += "  %s -> %s\n" % (src, dest)

                return s

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

        def evaluate(self, filters = []):
                """Determine the actions required to transition the package."""
                # if origin unset, determine if we're dealing with an previously
                # installed version or if we're dealing with the null package
                #
                # XXX Perhaps make the pkgplan creator make this explicit, so we
                # don't have to check?
                f = None
                if not self.origin_fmri:
                        try:
                                f = self.image.get_version_installed(
                                    self.destination_fmri)
                                self.origin_fmri = f
                                self.origin_mfst = self.image.get_manifest(f)
                        except LookupError:
                                pass

                self.destination_filters = filters

                # Try to load the filter used for the last install of the
                # package.
                self.origin_filters = []
                if self.origin_fmri:
                        try:
                                f = file("%s/pkg/%s/filters" % \
                                    (self.image.imgdir,
                                    self.origin_fmri.get_dir_path()), "r")
                        except IOError, e:
                                if e.errno != errno.ENOENT:
                                        raise
                        else:
                                self.origin_filters = [
                                    (l.strip(), compile(
                                        l.strip(), "<filter string>", "eval"))
                                    for l in f.readlines()
                                ]

                self.destination_mfst.filter(self.destination_filters)
                self.origin_mfst.filter(self.origin_filters)

                # Assume that origin actions are unique, but make sure that
                # destination ones are.
                ddups = self.destination_mfst.duplicates()
                if ddups:
                        raise RuntimeError, ["Duplicate actions", ddups]

                self.actions = self.destination_mfst.difference(
                    self.origin_mfst)

        def preexecute(self):
                """Perform actions required prior to installation or removal of a package.

                This method executes each action's preremove() or preinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                flist = None
                flist_supported = True

                # retrieval step
                if self.destination_fmri == None:
                        os.unlink("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.origin_fmri.get_dir_path()))

                        try:
                                os.unlink("%s/pkg/%s/filters" % (
                                    self.image.imgdir,
                                    self.origin_fmri.get_dir_path()))
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                for src, dest in self.actions:
                        if dest:
                                dest.preinstall(self, src)
                        else:
                                src.preremove(self)

                        if dest and dest.needsdata(src) and flist_supported:

                                if flist and flist.is_full():
                                        try:
                                                flist.get_files()
                                        except filelist.FileListException:
                                                flist_supported = False
                                                flist = None
                                                continue

                                        flist = None

                                if flist is None:
                                        flist = filelist.FileList(
                                                    self.image,
                                                    self.destination_fmri)

                                flist.add_action(dest)


                # Get any remaining files
                if flist:
                        try:
                                flist.get_files()
                        except filelist.FileListException:
                                pass
                        flist = None

        def execute(self):
                """Perform actions for installation or removal of a package.

                This method executes each action's remove() or install()
                methods.
                """

                # record that we are in an intermediate state

                # It might be nice to have a single action.execute() method, but
                # I can't think of an example where it would make especially
                # good sense (i.e., where "remove" is as similar to "upgrade" as
                # is "install").
                for src, dest in self.actions:
                        if dest:
                                try:
                                        dest.install(self, src)
                                except Exception, e:
                                        print "Action install failed for '%s' (%s):\n  %s: %s" % \
                                            (dest.attrs.get(dest.key_attr, id(dest)),
                                            self.destination_fmri.get_pkg_stem(),
                                            e.__class__.__name__, e)
                                        raise
                        else:
                                src.remove(self)

        def postexecute(self):
                """Perform actions required after installation or removal of a package.

                This method executes each action's postremove() or postinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                # record that package states are consistent
                for src, dest in self.actions:
                        if dest:
                                dest.postinstall(self, src)
                        else:
                                src.postremove(self)

                # In the case of an upgrade, remove the installation turds from
                # the origin's directory.
                # XXX should this just go in preexecute?
                if self.origin_fmri != None and self.destination_fmri != None:
                        os.unlink("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.origin_fmri.get_dir_path()))

                        try:
                                os.unlink("%s/pkg/%s/filters" % (
                                    self.image.imgdir,
                                    self.origin_fmri.get_dir_path()))
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                if self.destination_fmri != None:
                        file("%s/pkg/%s/installed" % (self.image.imgdir,
                            self.destination_fmri.get_dir_path()), "w")

                        # Save the filters we used to install the package, so
                        # they can be referenced later.
                        if self.destination_filters:
                                f = file("%s/pkg/%s/filters" % \
                                    (self.image.imgdir,
                                    self.destination_fmri.get_dir_path()), "w")

                                f.writelines([
                                    filter + "\n"
                                    for filter, code in self.destination_filters
                                ])
                                f.close()
