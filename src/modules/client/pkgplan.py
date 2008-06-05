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

import errno
import itertools
import os

import pkg.manifest as manifest
import pkg.client.filelist as filelist
import pkg.actions.directory as directory
from pkg.misc import msg

class PkgPlan(object):
        """A package plan takes two package FMRIs and an Image, and produces the
        set of actions required to take the Image from the origin FMRI to the
        destination FMRI.

        If the destination FMRI is None, the package is removed.
        """

        def __init__(self, image, progtrack):
                self.origin_fmri = None
                self.destination_fmri = None
                self.origin_mfst = manifest.null
                self.destination_mfst = manifest.null

                self.image = image
                self.progtrack = progtrack

                self.actions = []

                self.xfersize = -1
                self.xferfiles = -1

                self.origin_filters = []
                self.destination_filters = []

        def __str__(self):
                s = "%s -> %s\n" % (self.origin_fmri, self.destination_fmri)

                for src, dest in itertools.chain(*self.actions):
                        s += "  %s -> %s\n" % (src, dest)

                return s

        def propose_destination(self, fmri, mfst):
                self.destination_fmri = fmri
                self.destination_mfst = mfst

                if self.image.install_file_present(fmri):
                        raise RuntimeError, "already installed"

        def propose_removal(self, fmri, mfst):
                self.origin_fmri = fmri
                self.origin_mfst = mfst

                if not self.image.install_file_present(fmri):
                        raise RuntimeError, "not installed"

        def get_actions(self):
                raise NotImplementedError()

        def get_nactions(self):
                return len(self.actions[0]) + len(self.actions[1]) + \
                    len(self.actions[2])

        def update_pkg_set(self, fmri_set):
                """ updates a set of installed fmris to reflect
                proposed new state"""

                if self.origin_fmri:
                        fmri_set.discard(self.origin_fmri)

                if self.destination_fmri:
                        fmri_set.add(self.destination_fmri)
                        
        def evaluate(self, filters = []):
                """Determine the actions required to transition the package."""
                # if origin unset, determine if we're dealing with an previously
                # installed version or if we're dealing with the null package
                #
                # XXX Perhaps make the pkgplan creator make this explicit, so we
                # don't have to check?
                f = None
                if not self.origin_fmri:
                        f = self.image.older_version_installed(
                            self.destination_fmri)
                        if f:
                                self.origin_fmri = f
                                self.origin_mfst = self.image.get_manifest(f)

                self.destination_filters = filters

                # Try to load the filter used for the last install of the
                # package.
                self.origin_filters = []
                if self.origin_fmri:
                        try:
                                f = file("%s/pkg/%s/filters" % \
                                    (self.image.imgdir,
                                    self.origin_fmri.get_dir_path()), "r")
                        except EnvironmentError, e:
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

                # figure out how many implicit directories disappear in this
                # transition and add directory remove actions.  These won't
                # do anything unless no pkgs reference that directory in
                # new state....

                tmpset = set()

                for a in self.origin_mfst.actions:
                        tmpset.update(a.directory_references())

                absent_dirs = self.image.expanddirs(tmpset)

                tmpset = set()

                for a in self.destination_mfst.actions:
                        tmpset.update(a.directory_references())

                absent_dirs.difference_update(self.image.expanddirs(tmpset))

                for a in absent_dirs:
                        self.actions[2].append([directory.DirectoryAction(path=a), None])

                # over the list of update actions, check for any that are the
                # target of hardlink actions, and add the renewal of those hardlinks
                # to the install set
                link_actions = self.image.get_link_actions()

                # iterate over copy since we're appending to list

                for a in self.actions[1][:]:
                        if a[1].name == "file" and a[1].attrs["path"] in link_actions:
                                la = link_actions[a[1].attrs["path"]]
                                self.actions[1].extend([(a, a) for a in la])

        def get_xferstats(self):
                if self.xfersize != -1:
                        return (self.xferfiles, self.xfersize)

                self.xfersize = 0
                self.xferfiles = 0
                for src, dest in itertools.chain(*self.actions):
                        if dest and dest.needsdata(src):
                                self.xfersize += \
                                    int(dest.attrs.get("pkg.size", 0))
                                self.xferfiles += 1

                return (self.xferfiles, self.xfersize)

        def will_xfer(self):
                nf, nb = self.get_xferstats()
                if nf > 0:
                        return True
                else:
                        return False

        def get_xfername(self):
                if self.destination_fmri:
                        return self.destination_fmri.get_name()
                if self.origin_fmri:
                        return self.origin_fmri.get_name()
                return None

        def preexecute(self):
                """Perform actions required prior to installation or removal of a package.

                This method executes each action's preremove() or preinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                flist = None
                flist_supported = True

                if flist_supported:
                        self.progtrack.download_start_pkg(self.get_xfername())

                # retrieval step
                if self.destination_fmri == None:
                        self.image.remove_install_file(self.origin_fmri)

                        try:
                                os.unlink("%s/pkg/%s/filters" % (
                                    self.image.imgdir,
                                    self.origin_fmri.get_dir_path()))
                        except EnvironmentError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                for src, dest in itertools.chain(*self.actions):
                        if dest:
                                dest.preinstall(self, src)
                        else:
                                src.preremove(self)

                        if dest and dest.needsdata(src) and flist_supported:

                                if flist and flist.is_full():
                                        try:
                                                flist.get_files()
                                                self.progtrack.download_add_progress(flist.get_nfiles(), flist.get_nbytes())
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
                                self.progtrack.download_add_progress(flist.get_nfiles(), flist.get_nbytes())
                        except filelist.FileListException:
                                pass
                        flist = None

                if flist_supported:
                        self.progtrack.download_end_pkg()

        def gen_install_actions(self):
                for src, dest in self.actions[0]:
                        yield src, dest

        def gen_removal_actions(self):
                for src, dest in self.actions[2]:
                        yield src, dest

        def gen_update_actions(self):
                for src, dest in self.actions[1]:
                        yield src, dest

        def execute_install(self, src, dest):
                """ perform action for installation of package"""
                try:
                        dest.install(self, src)
                except Exception, e:
                        msg("Action install failed for '%s' (%s):\n  %s: %s" % \
                            (dest.attrs.get(dest.key_attr, id(dest)),
                             self.destination_fmri.get_pkg_stem(),
                             e.__class__.__name__, e))
                        raise

        def execute_update(self, src, dest):
                """ handle action updates"""
                try:
                        dest.install(self, src)
                except Exception, e:
                        msg("Action upgrade failed for '%s' (%s):\n %s: %s" % \
                             (dest.attrs.get(dest.key_attr, id(dest)),
                             self.destination_fmri.get_pkg_stem(),
                             e.__class__.__name__, e))
                        raise

        def execute_removal(self, src, dest):
                """ handle action removals"""
                try:
                        src.remove(self)
                except Exception, e:
                        msg("Action removal failed for '%s' (%s):\n  %s: %s" % \
                            (src.attrs.get(src.key_attr, id(src)),
                             self.origin_fmri.get_pkg_stem(),
                             e.__class__.__name__, e))
                        raise

        def postexecute(self):
                """Perform actions required after installation or removal of a package.

                This method executes each action's postremove() or postinstall()
                methods, as well as any package-wide steps that need to be taken
                at such a time.
                """
                # record that package states are consistent
                for src, dest in itertools.chain(*self.actions):
                        if dest:
                                dest.postinstall(self, src)
                        else:
                                src.postremove(self)

                # In the case of an upgrade, remove the installation turds from
                # the origin's directory.
                # XXX should this just go in preexecute?
                if self.origin_fmri != None and self.destination_fmri != None:
                        self.image.remove_install_file(self.origin_fmri)

                        try:
                                os.unlink("%s/pkg/%s/filters" % (
                                    self.image.imgdir,
                                    self.origin_fmri.get_dir_path()))
                        except EnvironmentError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                if self.destination_fmri != None:
                        self.image.add_install_file(self.destination_fmri)

                        # Save the filters we used to install the package, so
                        # they can be referenced later.
                        if self.destination_filters:
                                f = file("%s/pkg/%s/filters" % \
                                    (self.image.imgdir,
                                    self.destination_fmri.get_dir_path()), "w")

                                f.writelines([
                                    myfilter + "\n"
                                    for myfilter, code in self.destination_filters
                                ])
                                f.close()

