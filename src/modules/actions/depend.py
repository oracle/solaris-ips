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

"""Action describing a package dependency.

This module contains the DependencyAction class, which represents a
relationship between the package containing the action and another package.
"""

import urllib
import generic
import pkg.fmri as fmri

class DependencyAction(generic.Action):
        """Class representing a dependency packaging object.  The fmri attribute
        is expected to be the pkg FMRI that this package depends on.  The type
        attribute is one of

        optional - dependency if present activates additional functionality,
                   but is not needed

        require - dependency is needed for correct function

        transfer - dependency on minimum version of other package that donated
        components to this package at earlier version.  Other package need not
        be installed, but if it is, it must be at the specified version.  Effect
        is the same as optional, but semantics are different.

        incorporate - optional freeze at specified version

        exclude - package non-functional if dependent package is present 
        (unimplemented) """

        name = "depend"
        attributes = ("type", "fmri")
        key_attr = "fmri"
        known_types = ("optional", "require", "transfer", "incorporate")

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)

        def parse(self, image):
                """ decodes attributes into tuple whose contents are
                (boolean required, minimum fmri, maximum fmri)
                XXX still needs exclude support....
                """
                type = self.attrs["type"]
                fmri_string = self.attrs["fmri"]

                f = fmri.PkgFmri(fmri_string, image.attrs["Build-Release"])
                image.fmri_set_default_authority(f)
                
                min_fmri = f
                max_fmri = None
                required = True
                if type == "optional" or type == "transfer":
                        required = False
                elif type == "incorporate":
                        required = False
                        max_fmri = f
                return required, min_fmri, max_fmri

                
        def verify(self, img, **args):
                # XXX maybe too loose w/ early versions

                type = self.attrs["type"]
                pkgfmri = self.attrs["fmri"]

                if type not in self.known_types:
                        return ["Unknown type (%s) in depend action" % type]

                fm = fmri.PkgFmri(pkgfmri, img.attrs["Build-Release"])

                installed_version = img.has_version_installed(fm)

                if not installed_version:
                        if type == "require":
                                return ["Required dependency %s is not installed" % fm]
                        installed_version = img.older_version_installed(fm) 
                        if installed_version:
                                return ["%s dependency %s is downrev (%s)" % (type,
                                    fm,        installed_version)]
                #XXX - leave off for now since we can't handle max fmri constraint
                #w/o backtracking
                #elif type == "incorporate":
                #        if not img.is_installed(fm):
                #                return ["%s dependency %s is uprev (%s)" % (type,
                #                    fm,        installed_version)]
                return []

        def generate_indices(self):
                type = self.attrs["type"]
                fmri = self.attrs["fmri"]
                
                if type not in self.known_types:
                        return {}

                # XXX Ideally, we'd turn the string into a PkgFmri, and separate
                # the stem from the version, or use get_dir_path, but we can't
                # create a PkgFmri without supplying a build release and without
                # it creating a dummy timestamp.  So we have to split it apart
                # manually.
                #
                # XXX This code will need to change once we start using fmris
                # with authorities.
                if fmri.startswith("pkg:/"):
                        fmri = fmri[5:]
                # Note that this creates a directory hierarchy!
                fmri = urllib.quote(fmri, "@").replace("@", "/")

                return {
                    "depend": fmri
                }
