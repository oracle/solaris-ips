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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import errno
import os
import sha
import shutil
import time
import urllib

import pkg.fmri as fmri
import pkg.misc as misc
import pkg.version as version

# XXX Is a PkgVersion more than a wrapper around a hypothetical Manifest object?
#
class PkgVersion(object):
        """A PkgVersion is a single version node of a group of files.  It
        consists of the versioning data and authority required to construct a
        legitimate, fully versioned FMRI, its dependencies and incorporations on
        other package FMRIs, and the contents metadata used to request and
        install its extended content.

        The dependencies are presented as a list of Dependency objects.

        The contents are presented as a list of Contents objects.

        The marshalled form of a PkgVersion is either a Manifest or a
        MarshalledPackage."""

        def __init__(self, pkg, version):
                self.pkg = pkg
                self.version = version
                self.contents = []
                self.dependencies = []

        def __cmp__(self, other):
                assert self.pkg == other.pkg
                return self.version.__cmp__(other.version)

        def set_contents(self, contents):
                self.contents = contents

        def add_content(self, content):
                self.contents += content
                return

        def set_dependencies(self, dependencies):
                self.dependencies = dependencies

        def add_dependency(self, dependency):
                self.dependencies += dependency
                return

        def __str__(self):
                """The __str__ method for a PkgVersion returns the manifest for
                the PkgVersion."""
                return

class Package(object):
        """A Package is a named list of PkgVersions in the package graph.
        Packages have a package FMRI without a specific version."""

        def __init__(self, pfmri):
                # Strip any version off pfmri; require caller to explicitly add
                # versions via add_version().
                self.fmri = fmri.PkgFmri(pfmri.pkg_name, None)
                self.pversions = []

                self.dir = ""
                self.bulk_state = None

        def __cmp__(self, other):
                if self.fmri and not other.fmri:
                        return -1

                if other.fmri and not self.fmri:
                        return 1

                if not self.fmri and not other.fmri:
                        return 0

                return self.fmri.__cmp__(other.fmri)

        def set_dir(self, cfg):
                authority, pkg_name, version = self.fmri.tuple()
                self.dir = "%s/%s" % (cfg.pkg_root,
                    urllib.quote(pkg_name, ""))

                # Bulk state represents whether the server knows of any version
                # of this package.  It is false for a new package.
                self.bulk_state = True
                try:
                        os.stat(self.dir)
                except:
                        self.bulk_state = False

        def load(self, cfg):
                """Iterate through directory and build version list.  Each entry
                is a separate version of the package."""
                if self.bulk_state == None:
                        self.set_dir(cfg)

                if not self.bulk_state:
                        return

                for e in os.listdir(self.dir):
                        e = urllib.unquote(e)
                        print self.fmri, e
                        v = version.Version(e, None)
                        pn = PkgVersion(self, v)
                        self.pversions.append(pn)

                self.pversions.sort()
                return

        def can_open_version(self, version):
                # validate that this version can be opened
                #   if we specified no release, fail
                #   if we specified a release without branch, open next branch
                #   if we specified a release with branch major, open same
                #     branch, next minor
                #   if we specified a release with branch major and minor, use
                #   as specified, new timestamp
                # we should disallow new package creation, if so flagged

                return True

        def update(self, cfg, trans):
                """Moves the files associated with the transaction into the
                appropriate position in the server repository, returning a
                Package object on success.  Registration of the new package
                version with the catalog is the caller's responsibility."""

                # Assume that there's only one version associated with this
                # package, because we should only be called from a server
                # transaction.
                assert len(self.pversions) == 1

                if not self.bulk_state:
                        os.makedirs(self.dir)

                version = self.pversions[0].version

                # mv manifest to pkg_name / version
                # A package may have no files, so there needn't be a manifest.
                if os.path.exists("%s/manifest" % trans.dir):
                        os.rename("%s/manifest" % trans.dir, "%s/%s" %
                            (self.dir, urllib.quote(str(version), "")))

                # Move each file to file_root, with appropriate directory
                # structure.
                for f in os.listdir(trans.dir):
                        path = misc.hash_file_name(f)
                        src_path = "%s/%s" % (trans.dir, f)
                        dst_path = "%s/%s" % (cfg.file_root, path)
                        try:
                                os.rename(src_path, dst_path)
                        except OSError, e:
                                # XXX We might want to be more careful with this
                                # exception, and only try makedirs() if rename()
                                # failed because the directory didn't exist.
                                #
                                # I'm not sure it matters too much, except that
                                # if makedirs() fails, we'll see that exception,
                                # rather than the original one from rename().
                                #
                                # Interestingly, rename() failing due to missing
                                # path component fails with ENOENT, not ENOTDIR
                                # like rename(2) suggests (6578404).
                                try:
                                        os.makedirs(os.path.dirname(dst_path))
                                except OSError, e:
                                        if e.errno != errno.EEXIST:
                                                raise
                                os.rename(src_path, dst_path)

                # XXX We don't actually use this value; should we bother?
                return Package(fmri.PkgFmri(self.fmri.pkg_name, version))

        def add_version(self, fmri):
                v = fmri.version

                for pv in self.pversions:
                        if v == pv.version:
                                # XXX Should we be asserting here?
                                return

                pv = PkgVersion(self, v)
                self.pversions.append(pv)

                # XXX sort?

        def matching_versions(self, pfmri, constraint):
                ret = []

                for pv in self.pversions:
                        f = fmri.PkgFmri("%s@%s" % (self.fmri, pv.version),
                            None)
                        if f.is_successor(pfmri):
                                ret.append(f)

                return ret

        def get_state(self, version):
                return "state"

        def get_manifest(self, version):
                return

        def get_catalog_entry(self):
                ret = ""
                for pv in self.pversions:
                        ret = ret + "V %s@%s\n" % (self.fmri, pv.version)
                return ret

