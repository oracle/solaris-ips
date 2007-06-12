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

        def find_parent(self):
                # Ascend from current working directory to find first
                # encountered image.
                while True:
                        d = os.getcwd()

                        if os.path.isdir("%s/%s" % (d, img_user_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                self.type = IMG_USER
                                self.root = d
                                self.imgdir = "%s/%s" % (d, img_user_prefix)
                                return
                        elif os.path.isdir("%s/%s" % (d, img_root_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                self.type = IMG_ENTIRE
                                self.root = d
                                self.imgdir = "%s/%s" % (d, img_root_prefix)
                                return

                        assert d != "/"

                        os.chdir("..")

        def mkdirs(self):
                if not os.path.isdir(self.imgdir + "/catalog"):
                        os.makedirs(self.imgdir + "/catalog")
                if not os.path.isdir(self.imgdir + "/file"):
                        os.makedirs(self.imgdir + "/file")
                if not os.path.isdir(self.imgdir + "/pkg"):
                        os.makedirs(self.imgdir + "/pkg")

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

        def get_matching_pkgs(self, pattern):
                """The pattern is a glob pattern, which we translate to an RE
                pattern.

                XXX This is going to need to return (catalog, fmri) pairs."""

                m = []
                for c in self.catalogs.values():
                        m.extend(c.get_matching_pkgs(pattern, None))

                return m

        def retrieve_manifest(self, catalog, fmri):
                """Turn FMRI to Image's path to manifest.  If present, return.
                If not present, calculate URI and retrieve.

                XXX Which catalog did we fetch this fmri from?"""

                authority, pkg_name, version = fmri.tuple()

                mpath = fmri.get_dir_path()

                local_mpath = "%s/pkg/%s/manifest" % (self.imgdir, mpath)

                if (os.path.exists(local_mpath)):
                        print "short circuit retrieve"
                        return local_mpath # or return object?

                # XXX convert authority reference to server
                if authority == None:
                        authority = "localhost:10000"
                url_mpath = "http://%s/manifest/%s" % (authority,
                                fmri.get_url_path())

                print url_mpath
                try:
                        m = urllib.urlopen(url_mpath)
                except:
                        raise NameError, "could not open %s" % url_mpath

                data = m.read()
                print local_mpath
                try:
                        mfile = file(local_mpath, "w")
                        print >>mfile, data
                except IOError, e:
                        os.makedirs(os.path.dirname(local_mpath))
                        mfile = file(local_mpath, "w")
                        print >>mfile, data

                return local_mpath


