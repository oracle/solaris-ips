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

import os
import re
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

        def __init__(self, fmri):
                self.fmri = fmri
                self.pversions = []

                self.dir = ""
                self.bulk_state = None

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
                        print e
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

                if not self.bulk_state:
                        os.makedirs(self.dir)

                (authority, name, version) = self.fmri.tuple()

                # mv manifest to pkg_name / version
                # A package may have no files, so there needn't be a manifest.
                if os.path.exists("%s/manifest" % trans.dir):
                        os.rename("%s/manifest" % trans.dir, "%s/%s" %
                            (self.dir, urllib.quote(version.__str__(), "")))

                # Move each file to file_root, with appropriate directory
                # structure.
                for f in os.listdir(trans.dir):
                        path = misc.hash_file_name(f)
                        try:
                                os.rename("%s/%s" % (trans.dir, f),
                                    "%s/%s" % (cfg.file_root, path))
                        except OSError, e:
                                os.makedirs("%s/%s" % (cfg.file_root,
                                        os.path.dirname(path)))
                                os.rename("%s/%s" % (trans.dir, f),
                                    "%s/%s" % (cfg.file_root, path))

                return Package(self.fmri)

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
                pf = fmri.PkgFmri(pfmri, None)

                for pv in self.pversions:
                        f = fmri.PkgFmri("%s@%s" % (self.fmri, pv.version),
                            None)
                        if f.is_successor(pf):
                                ret.append(f)

                return ret

        def get_state(self, version):
                return 0;

        def get_manifest(self, version):
                return

        def get_catalog_entry(self):
                ret = ""
                for pv in self.pversions:
                        ret = ret + "V %s@%s\n" % (self.fmri, pv.version)
                return ret

