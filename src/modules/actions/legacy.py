#!/usr/bin/python2.4
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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

"""module describing a legacy packaging object

This module contains the LegacyAction class, which represents a legacy SVr4
package.  On installation, this action will lay down file with sufficient data
to fool the SVr4 packaging tools into thinking that package is installed, albeit
empty."""

import os
import errno
from stat import *
import generic

class LegacyAction(generic.Action):
        """Class representing a legacy SVr4 packaging object."""

        name = "legacy"
        key_attr = "pkg"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def directory_references(self):
                return [os.path.normpath(os.path.join("var/sadm/pkg", self.attrs["pkg"]))]

        def install(self, pkgplan, orig):
                """Client-side method that installs the dummy package files.  
                Use per-pkg hardlinks to create reference count for pkginfo file"""

                pkgdir = os.path.join(pkgplan.image.get_root(), "var/sadm/pkg",
                    self.attrs["pkg"])

                if not os.path.isdir(pkgdir):
                        os.makedirs(pkgdir, 0755)

                pkginfo = os.path.join(pkgdir, "pkginfo")

                if not os.path.isfile(pkginfo):
                        legacy_info = pkgplan.get_legacy_info()
                        svr4attrs = {
                            "pkg": self.attrs["pkg"],
                            "name": legacy_info["description"],
                            "arch": pkgplan.image.get_arch(),
                            "version": legacy_info["version"],
                            "category": "system",
                            "vendor": None, 
                            "desc": None, 
                            "hotline": None
                            }

                        attrs = (
                            (a.upper(), b)
                            for a in svr4attrs
                            for b in ( self.attrs.get(a, svr4attrs[a]), )
                            if b
                            )

                        pfile = file(pkginfo, "w")
                        for k, v in attrs:
                                pfile.write("%s=%s\n" % (k, v))
                        pfile.close()

                # create another hardlink to pkginfo file if
                # this is not just an upgrade; we use this to make
                # uninstall easier

                if not orig:
                        linkfile = os.path.join(pkgdir, 
                            "pkginfo.%d" % (os.stat(pkginfo)[ST_NLINK] + 1))
                        os.link(pkginfo, linkfile)

                # the svr4 pkg commands need contents file to work, but the
                # needed directories are in the SUNWpkgcmds package....
                # Since this file is always of zero length, we can let this
                # fail until those directories (and the commands that
                # need them) appear.

                try:
                        file(os.path.join(pkgplan.image.get_root(),
                            "var/sadm/install/contents"), "a").close()
                except IOError, e:
                        if e.errno != errno.ENOENT:
                                raise

                os.chmod(pkginfo, 0644)

        def verify(self, img, **args):
                pkgdir = os.path.join(img.get_root(), "var/sadm/pkg",
                    self.attrs["pkg"])

                # XXX this could be a better check & exactly validate pkginfo contents

                if not os.path.isdir(pkgdir):
                        return ["Missing directory var/sadm/pkg/%s" %
                            self.attrs["pkg"]]
                pkginfo = os.path.join(pkgdir, "pkginfo")

                if not os.path.isfile(os.path.join(pkgdir, "pkginfo")):
                        return ["Missing file var/sadm/pkg/%s/pkginfo" %
                            self.attrs["pkg"]]
                return []

        def remove(self, pkgplan):

                # pkg directory is removed via implicit directory removal
                
                pkgdir = os.path.join(pkgplan.image.get_root(), "var/sadm/pkg",
                    self.attrs["pkg"])

                pkginfo = os.path.join(pkgdir, "pkginfo")

                if os.path.isfile(pkginfo):
                        link_count = os.stat(pkginfo)[ST_NLINK]
                        linkfile = os.path.join(pkgdir,
                            "pkginfo.%d" % (link_count))
                        
                        if os.path.isfile(linkfile):
                                os.unlink(linkfile)

                        # do this conditionally to be kinder
                        # to installations done w/ older versions
                        if link_count <= 2: # last one
                                os.unlink(pkginfo)

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                return [("legacy", "legacy_pkg", self.attrs["pkg"], None)]
