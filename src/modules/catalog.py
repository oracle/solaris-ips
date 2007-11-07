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
import sha
import shutil
import time
import urllib
import tempfile
import errno

import pkg.fmri as fmri
import pkg.version as version

class CatalogException(Exception):
        def __init__(self, args=None):
                self.args = args

class Catalog(object):
        """A Catalog is the representation of the package FMRIs available to
        this client or repository.  Both purposes utilize the same storage
        format.

        The serialized structure of the repository is an unordered list of
        available package versions, followed by an unordered list of
        incorporation relationships between packages.  This latter section
        allows the graph to be topologically sorted by the client.

        S Last-Modified: [timespec]

        XXX A authority mirror-uri ...
        XXX ...

        V fmri
        V fmri
        ...
        C fmri
        C fmri
        ...
        I fmri fmri
        I fmri fmri
        ...
        """

        # XXX Mirroring records also need to be allowed from client
        # configuration, and not just catalogs.
        #
        # XXX It would be nice to include available tags and package sizes,
        # although this could also be calculated from the set of manifests.
        #
        # XXX Current code is O(N_packages) O(M_versions), should be
        # O(1) O(M_versions), and possibly O(1) O(1).
        #
        # XXX Initial estimates suggest that the Catalog could be composed of
        # 1e5 - 1e7 lines.  Catalogs across these magnitudes will need to be
        # spread out into chunks, and may require a delta-oriented update
        # interface.

        def __init__(self, cat_root, authority = None, pkg_root = None):
                """Create a catalog.  If the path supplied does not exist,
                this will create the required directory structure.
                Otherwise, if the directories are already in place, the
                existing catalog is opened.  If pkg_root is specified
                and no catalog is found at cat_root, the catalog will be
                rebuilt.  authority names the authority that
                is represented by this catalog."""

                self.catalog_root = cat_root
                self.attrs = {}
                self.auth = authority

                self.attrs["npkgs"] = 0

                if not os.path.exists(cat_root):
                        os.makedirs(cat_root) 

                catpath = os.path.normpath(os.path.join(cat_root, "catalog"))

                if pkg_root is not None and not os.path.exists(catpath):
                        self.build_catalog(pkg_root)
                        self.set_time()
                        self.save_attrs()

                self.load_attrs()

        def add_fmri(self, fmri, critical = False):
                """Add a package, named by the fmri, to the catalog.
                Throws an exception if an identical package is already
                present.  Throws an exception if package has no version."""
                if fmri.version == None:
                        raise CatalogException, \
                            "Unversioned FMRI not supported: %s" % fmri

                if critical:
                        pkgstr = "C %s\n" % fmri.get_fmri(anarchy = True)
                else:
                        pkgstr = "V %s\n" % fmri.get_fmri(anarchy = True)

                pathstr = os.path.normpath(os.path.join(self.catalog_root,
                    "catalog"))

                pfile = file(pathstr, "a+")
                pfile.seek(0)

                for entry in pfile:
                        if entry == pkgstr:
                                pfile.close()
                                raise CatalogException, \
                                    "Package is already in the catalog"

                pfile.write(pkgstr)
                pfile.close()

                self.attrs["npkgs"] += 1

                self.set_time()
                self.save_attrs()

        def attrs_as_lines(self):
                """Takes the list of in-memory attributes and returns
                a list of strings, each string naming an attribute."""

                ret = []

                for k,v in self.attrs.items():
                        s = "S %s: %s\n" % (k, v)
                        ret.append(s)

                return ret

        def build_catalog(self, pkg_root):
                """Walk the on-disk package data and build (or rebuild)
                the package catalog."""
                tree = os.walk(pkg_root)

                # XXX eschew os.walk in favor of another os.listdir here?
                for pkg in tree:
                        if pkg[0] == pkg_root:
                                continue

                        for e in os.listdir(pkg[0]):
                                e = urllib.unquote(e)
                                v = version.Version(e, None)
                                f = fmri.PkgFmri(urllib.unquote(
                                        os.path.basename(pkg[0])), None)
                                f.version = v

                                self.add_fmri(f)

                                print f

        def get_matching_fmris(self, patterns, matcher = None,
            constraint = None, counthash = None):
                """Iterate through the catalog, looking for packages matching
                'pattern', based on the function in 'matcher' and the versioning
                constraint described by 'constraint'.  If 'matcher' is None,
                uses fmri subset matching as the default.  Returns a sorted list
                of PkgFmri objects, newest versions first.  If 'counthash' is a
                dictionary, instead store the number of matched fmris for each
                package name which was matched."""

                cat_auth = self.auth

                if not matcher:
                        matcher = fmri.fmri_match

                if not isinstance(patterns, list):
                        patterns = [ patterns ]

                # 'pattern' may be a partially or fully decorated fmri; we want
                # to extract its name and version to match separately against
                # the catalog.
                # XXX "5.11" here needs to be saner
                tuples = {}

                for pattern in patterns:
                        if isinstance(pattern, fmri.PkgFmri):
                                tuples[pattern] = pattern.tuple()
                        else:
                                tuples[pattern] = \
                                    fmri.PkgFmri(pattern, "5.11").tuple()

                ret = []

                try:
                        pfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return ret
                        else:
                                raise

                for entry in pfile:
                        try:
                                cv, pkg, cat_name, cat_version = entry.split()
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.
                                cv, cat_fmri = entry.split()
                                pkg = "pkg"
                                cat_auth, cat_name, cat_version = \
                                    fmri.PkgFmri(cat_fmri, "5.11",
                                        authority = self.auth).tuple()

                        for pattern in patterns:
                                pat_auth, pat_name, pat_version = tuples[pattern]
                                if pkg == "pkg" and \
                                    (pat_auth == cat_auth or not pat_auth) and \
                                    matcher(cat_name, pat_name):
                                        pkgfmri = fmri.PkgFmri("%s@%s" %
                                            (cat_name, cat_version),
                                            authority = cat_auth)
                                        if not pat_version or \
                                            pkgfmri.version.is_successor(
                                            pat_version, constraint) or \
                                            pkgfmri.version == pat_version:
                                                    if counthash is not None:
                                                            if pattern in counthash:
                                                                    counthash[pattern] += 1
                                                            else:
                                                                    counthash[pattern] = 1
                                                    ret.append(pkgfmri)

                pfile.close()

                return sorted(ret, reverse = True)

        def fmris(self):
                """A generator function that produces FMRIs as it
                iterates over the contents of the catalog."""

                try:
                        pfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return
                        else:
                                raise

                for entry in pfile:
                        try:
                                cv, pkg, cat_name, cat_version = entry.split()
                                if pkg == "pkg":
                                        yield fmri.PkgFmri("%s@%s" %
                                            (cat_name, cat_version),
                                            authority = self.auth)
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.
                                cv, cat_fmri = entry.split()
                                yield fmri.PkgFmri(cat_fmri,
                                    authority = self.auth)

                pfile.close()

        def load_attrs(self, filenm = "attrs"):
                """Load attributes from the catalog file into the in-memory
                attributes dictionary"""

                apath = os.path.normpath(
                    os.path.join(self.catalog_root, filenm))
                if not os.path.exists(apath):
                        return

                afile = file(apath, "r")
                attrre = re.compile('^S ([^:]*): (.*)')

                for entry in afile:
                        m = attrre.match(entry)
                        if m != None:
                                self.attrs[m.group(1)] = m.group(2)

                afile.close()

                if "npkgs" in self.attrs:
                        self.attrs["npkgs"] = int(self.attrs["npkgs"])

        def npkgs(self):
                """Returns the number of packages in the catalog."""

                return self.attrs["npkgs"] 

        @staticmethod
        def recv(filep, path):
                """A class method that takes a file-like object and
                a path.  This is the other half of catalog.send().  It
                reads a stream as an incoming catalog and lays it down
                on disk."""

                if not os.path.exists(path):
                        os.makedirs(path)

                attrf = file(os.path.normpath(
                    os.path.join(path, "attrs")), "w+")
                catf = file(os.path.normpath(
                    os.path.join(path, "catalog")), "w+")

                for s in filep:
                        if s.startswith("S "):
                                attrf.write(s)
                        else:
                                # XXX Need to be able to handle old and new
                                # format catalogs.
                                f = fmri.PkgFmri(s[2:])
                                catf.write("%s %s %s %s\n" %
                                    (s[0], "pkg", f.pkg_name, f.version))

                attrf.close()
                catf.close()

        def save_attrs(self, filenm = "attrs"):
                """Save attributes from the in-memory catalog to a file
                specified by filenm."""

                afile = file(os.path.normpath(
                    os.path.join(self.catalog_root, filenm)), "w+")
                for a in self.attrs.keys():
                        s = "S %s: %s\n" % (a, self.attrs[a])
                        afile.write(s)

                afile.close()

        def send(self, filep):
                """Send the contents of this catalog out to the filep
                specified as an argument."""

                # Send attributes first.
                filep.writelines(self.attrs_as_lines())

                try:
                        cfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        # Missing catalog is fine; other errors need to be
                        # reported.
                        if e.errno == errno.ENOENT:
                                return
                        else:
                                raise

                for e in cfile:
                        filep.write(e)

                cfile.close()

        def set_time(self):
                self.attrs["Last-Modified"] = time.strftime("%Y%m%dT%H%M%SZ")


# In order to avoid a fine from the Department of Redundancy Department,
# allow these methods to be invoked without explictly naming the Catalog class.
recv = Catalog.recv
