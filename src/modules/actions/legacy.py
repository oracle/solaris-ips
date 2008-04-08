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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
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
                        manifest = pkgplan.destination_mfst
                        svr4attrs = {
                            "pkg": self.attrs["pkg"],
                            "name": manifest.get("description", "none provided"),
                            "arch": "i386",
                            "version": pkgplan.destination_fmri.version,
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

                # create hardlink to pkginfo file for this pkg; may be
                # there already on upgrade

                linkfile = os.path.join(pkgdir, 
                    "pkginfo." + pkgplan.destination_fmri.get_url_path())

                if not os.path.isfile(linkfile):
                        os.link(pkginfo, linkfile)

                # the svr4 pkg commands need contents file to work, but the
                # needed directories are in the SUNWpkgcmds package....
                # Since this file is always of zero length, we can let this
                # fail until those directories (and the commands that
                # need them) appear.

                try:
                        file(os.path.join(pkgplan.image.get_root(),
                            "var/sadm/install/contents"), "w").close()
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

                linkfile = os.path.join(pkgdir, 
                    "pkginfo." + pkgplan.origin_fmri.get_url_path())
                
                if os.stat(linkfile)[ST_NLINK] == 2:
                        try:
                                os.unlink(os.path.join(pkgdir, "pkginfo"))
                        except OSError, e:
                                if e.errno not in (errno.EEXIST, errno.ENOENT):   
                                        #          can happen if all refs deleted
                                        raise    # in same pkg invocation
                os.unlink(linkfile)

        def generate_indices(self):
                return {
                    "legacy_pkg": self.attrs["pkg"]
                }
