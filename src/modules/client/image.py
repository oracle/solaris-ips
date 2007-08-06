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

import getopt
import os
import re
import urllib

import pkg.catalog as catalog
import pkg.fmri as fmri
import pkg.manifest as manifest

IMG_ENTIRE = 0
IMG_PARTIAL = 1
IMG_USER = 2

img_user_prefix = ".org.opensolaris,pkg"
img_root_prefix = "var/pkg"

class Image(object):
        """An Image object is a directory tree containing the laid-down contents
        of a self-consistent graph of Packages.

        An Image has a root path.

        An Image of type IMG_ENTIRE does not have a parent Image.  Other Image
        types must have a parent Image.  The external state of the parent Image
        must be accessible from the Image's context, or duplicated within the
        Image (IMG_PARTIAL for zones, for instance).

        The parent of a user Image can be a partial Image.  The parent of a
        partial Image must be an entire Image.

        An Image of type IMG_USER stores its external state at self.root +
        ".org.opensolaris,pkg".

        An Image of type IMG_ENTIRE or IMG_PARTIAL stores its external state at
        self.root + "/var/pkg".

        An Image needs to be able to have a different repository set than the
        system's root Image.

        Directory layout

          $IROOT/catalog
               Directory containing catalogs for URIs of interest.  Filename is
               the escaped URI of the catalog.

          $IROOT/file
               Directory containing file hashes of installed packages.

          $IROOT/pkg
               Directory containing manifests and states of installed packages.

          $IROOT/index
               Directory containing reverse-index databases.

        XXX Root path probably can't be absolute, so that we can combine or
        reuse Image contents.

        XXX Image file format?  Image file manipulation API?"""

        def __init__(self):
                self.type = None
                self.root = None
                self.imgdir = None
                self.repo_uris = []
                self.filter_tags = {}

                self.catalogs = {}
                self.authorities = {}

                self.attrs = {}

                self.attrs["Policy-Require-Optional"] = False
                self.attrs["Policy-Pursue-Latest"] = True

        def find_parent(self, d):
                # Ascend from current working directory to find first
                # encountered image.
                while True:
                        if os.path.isdir("%s/%s" % (d, img_user_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                self.type = IMG_USER
                                self.root = d
                                self.imgdir = "%s/%s" % (d, img_user_prefix)
                                self.attrs["Build-Release"] = "5.11"
                                return
                        elif os.path.isdir("%s/%s" % (d, img_root_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                self.type = IMG_ENTIRE
                                self.root = d
                                self.imgdir = "%s/%s" % (d, img_root_prefix)
                                self.attrs["Build-Release"] = "5.11"
                                return

                        assert d != "/"

                        # XXX follow symlinks or not?
                        d = os.path.normpath(os.path.join(d, os.path.pardir))

        def mkdirs(self):
                if not os.path.isdir(self.imgdir + "/catalog"):
                        os.makedirs(self.imgdir + "/catalog")
                if not os.path.isdir(self.imgdir + "/file"):
                        os.makedirs(self.imgdir + "/file")
                if not os.path.isdir(self.imgdir + "/pkg"):
                        os.makedirs(self.imgdir + "/pkg")
                if not os.path.isdir(self.imgdir + "/index"):
                        os.makedirs(self.imgdir + "/index")

        def set_attrs(self, type, root):
                self.type = type
                self.root = root
                if self.type == IMG_USER:
                        self.imgdir = self.root + "/" + img_user_prefix
                else:
                        self.imgdir = self.root + "/" + img_root_prefix

        def get_root(self):
                return self.root

        def set_resource(self, resource):
                return

        def get_matching_pkgs(self, pfmri):
                """Exact matches to the given FMRI.  Returns a list of (catalog,
                pkg) pairs."""

                m = []
                for c in self.catalogs.values():
                        m.extend([(c, p) \
                            for p in c.get_matching_pkgs(pfmri, None)])

                return m

        def get_regex_matching_fmris(self, regex):
                """FMRIs matching the given regular expression.  Returns of a
                list of (catalog, PkgFmri) pairs."""

                m = []
                for c in self.catalogs.values():
                        m.extend([(c, p) \
                            for p in c.get_regex_matching_fmris(regex)])

                return m

        def has_manifest(self, fmri):
                mpath = fmri.get_dir_path()

                local_mpath = "%s/pkg/%s/manifest" % (self.imgdir, mpath)

                if (os.path.exists(local_mpath)):
                        return True

                return False

        def get_manifest(self, fmri):
                m = manifest.Manifest()
                mcontent = file("%s/pkg/%s/manifest" % 
                    (self.imgdir, fmri.get_dir_path())).read()
                m.set_fmri(fmri)
                m.set_content(mcontent)
                return m

        def get_version_installed(self, pfmri):
                pd = pfmri.get_pkg_stem()
                pdir = "%s/pkg/%s" % (self.imgdir,
                    pfmri.get_dir_path(stemonly = True))

                try:
                        pkgs_inst = [ urllib.unquote("%s@%s" % (pd, vd))
                            for vd in os.listdir(pdir)
                            if os.path.exists("%s/%s/installed" % (pdir, vd)) ]
                except OSError:
                        raise LookupError, "no packages ever installed"

                if len(pkgs_inst) == 0:
                        raise LookupError, "no packages installed"

                assert len(pkgs_inst) <= 1

                return fmri.PkgFmri(pkgs_inst[0], None)

        def is_installed(self, fmri):
                """Check that the version given in the FMRI or a successor is
                installed in the current image."""

                try:
                        v = self.get_version_installed(fmri)
                except LookupError:
                        return False

                if v.is_successor(fmri):
                        return True

                return False

        def get_dependents(self, pfmri):
                """Return a list of the packages directly dependent on the given FMRI."""

                thedir = os.path.join(self.imgdir, "index", "depend",
                    urllib.quote(str(pfmri.get_pkg_stem())[5:], ""))

                if not os.path.isdir(thedir):
                        return []

                for v in os.listdir(thedir):
                        f = fmri.PkgFmri(pfmri.get_pkg_stem() + "@" + v,
                            self.attrs["Build-Release"])
                        if pfmri.is_successor(f):
                                dependents = [
                                    urllib.unquote(d)
                                    for d in os.listdir(os.path.join(thedir, v))
                                ]

                return dependents

        def reload_catalogs(self):
                cdir = "%s/%s" % (self.imgdir, "catalog")
                for cf in os.listdir(cdir):
                        c = catalog.Catalog()
                        c.load("%s/%s" % (cdir, cf))

                        self.catalogs[cf] = c

                        # XXX XXX
                        # build up authorities

        def display_catalogs(self):
                for c in self.catalogs.values():
                        c.display()

        def display_inventory(self, args):
                """XXX Reimplement if we carve out the inventory as a has-a
                object from image."""

                opts = []
                pargs = []

                verbose = False
                upgradable_only = False

                if len(args) > 0:
                         opts, pargs = getopt.getopt(args, "uv")

                for opt, arg in opts:
                        if opt == "-u":
                                upgradable_only = True
                        if opt == "-v":
                                verbose = True

                fmt_str = "%-50s %-10s %c%c%c%c"

                proot = "%s/pkg" % self.imgdir

                pkgs_inst = [ urllib.unquote("%s@%s" % (pd, vd))
                    for pd in os.listdir(proot)
                    for vd in os.listdir("%s/%s" % (proot, pd))
                    if os.path.exists("%s/%s/%s/installed" % (proot, pd, vd)) ]

                if len(pkgs_inst) == 0:
                        print "pkg: no packages installed"
                        return

                print fmt_str % ("FMRI", "STATE", "U", "F", "I", "X")

                for p in pkgs_inst:
                        f = fmri.PkgFmri(p, None)

                        upgradable = "-"
                        frozen = "-"
                        incorporated = "-"
                        excludes = "-"

                        if len(self.get_matching_pkgs(f)) > 1:
                                upgradable = "u"
                        elif upgradable_only:
                                continue

                        if not verbose:
                                pf = f.get_short_fmri()
                        else:
                                pf = str(f)

                        print fmt_str % (pf, "installed", upgradable, frozen,
                            incorporated, excludes)


if __name__ == "__main__":
        # XXX Need to construct a trivial image and catalog.
        pass
