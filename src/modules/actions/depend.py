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

"""Action describing a package dependency.

This module contains the DependencyAction class, which represents a
relationship between the package containing the action and another package.
"""

import urllib
import generic
import pkg.fmri as fmri
import pkg.version
import pkg.client.constraint as constraint
from pkg.client.imageconfig import REQUIRE_OPTIONAL

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
        is the same as optional, but the semantics are different.  OpenSolaris
        doesn't use these for bundled packages, as incorporations are preferred.

        incorporate - optional freeze at specified version

        exclude - package non-functional if dependent package is present
        (unimplemented) """

        name = "depend"
        attributes = ("type", "fmri")
        key_attr = "fmri"
        known_types = ("optional", "require", "transfer", "incorporate")

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                if "type" not in self.attrs:
                        raise pkg.actions.InvalidActionError(
                            str(self), _("Missing type attribute"))

                if "fmri" not in self.attrs:
                        raise pkg.actions.InvalidActionError(
                            str(self), _("Missing fmri attribute"))

                if self.attrs["type"] not in self.known_types:
                        raise pkg.actions.InvalidActionError(str(self),
                            _("Unknown type (%s) in depend action") %
                            self.attrs["type"])

                try:
                        if "fmri" in self.attrs:
                                self.clean_fmri()
                except ValueError:
                        print "Warning: failed to clean FMRI: %s" % \
                            self.attrs["fmri"]

        def clean_fmri(self):
                """ Clean up an invalid depend fmri into one which
                we can recognize.
                Example: 2.01.01.38-0.96  -> 2.1.1.38-0.96
                This also corrects self.attrs["fmri"] as external code
                knows about that, too.
                """
                #
                # This hack corrects a problem in pre-2008.11 packaging
                # metadata: some depend actions were specified with invalid
                # fmris of the form 2.38.01.01.3 (the padding zero is considered
                # invalid).  When we get an invalid FMRI, we use regular
                # expressions to perform a replacement operation which
                # cleans up these problems.
                #
                # n.b. that this parser is not perfect: it will fix only
                # the 'release' and 'branch' part of depend fmris-- these
                # are the only places we've seen rules violations.
                #
                # Lots of things could go wrong here-- the caller should
                # catch ValueError.
                #
                fmri_string = self.attrs["fmri"]

                #
                # Start by locating the @ and the "," or "-" or ":" which
                # is to the right of said @.
                #
                verbegin = fmri_string.find("@")
                if verbegin == -1:
                        return
                verend = fmri_string.find(",", verbegin)
                if verend == -1:
                        verend = fmri_string.find("-", verbegin)
                if verend == -1:
                        verend = fmri_string.find(":", verbegin)
                if verend == -1:
                        verend = len(fmri_string)

                # skip over the @ sign
                verbegin += 1
                verdots = fmri_string[verbegin:verend]
                dots = verdots.split(".")

                # Do the correction
                cleanvers = ".".join([str(int(s)) for s in dots])

                #
                # Next, find the branch if it exists, the first '-'
                # following the version.
                #
                branchbegin = fmri_string.find("-", verend)
                if branchbegin != -1:
                        branchend = fmri_string.find(":", branchbegin)
                        if branchend == -1:
                                branchend = len(fmri_string)

                        # skip over the -
                        branchbegin += 1
                        branchdots = fmri_string[branchbegin:branchend]
                        dots = branchdots.split(".")

                        # Do the correction
                        cleanbranch = ".".join([str(int(x)) for x in dots])

                if branchbegin == -1:
                        cleanfmri = fmri_string[:verbegin] + cleanvers + \
                            fmri_string[verend:]
                else:
                        cleanfmri = fmri_string[:verbegin] + cleanvers + \
                            fmri_string[verend:branchbegin] + cleanbranch + \
                            fmri_string[branchend:]

                # XXX enable if you need to debug
                #if cleanfmri != fmri_string:
                #       print "corrected invalid fmri: %s -> %s" % \
                #           (fmri_string, cleanfmri)
                self.attrs["fmri"] = cleanfmri

        def get_constrained_fmri(self, image):
                """ returns fmri of incorporation pkg or None if not
                an incorporation"""

                ctype = self.attrs["type"]
                if ctype != "incorporate":
                        return None

                pkgfmri = self.attrs["fmri"]
                f = fmri.PkgFmri(pkgfmri, image.attrs["Build-Release"])
                image.fmri_set_default_publisher(f)

                return f

        def parse(self, image, source_name):
                """decode depend action into fmri & constraint"""
                ctype = self.attrs["type"]
                fmristr = self.attrs["fmri"]
                f = fmri.PkgFmri(fmristr, image.attrs["Build-Release"])
                min_ver = f.version

                if min_ver == None:
                        min_ver = pkg.version.Version("0",
                            image.attrs["Build-Release"])

                name = f.get_name()
                max_ver = None
                presence = None

                if ctype == "require":
                        presence = constraint.Constraint.ALWAYS
                elif ctype == "exclude":
                        presence = constraint.Constraint.NEVER
                elif ctype == "incorporate":
                        presence = constraint.Constraint.MAYBE
                        max_ver = min_ver
                elif ctype == "optional":
                        if image.cfg_cache.get_policy(REQUIRE_OPTIONAL):
                                presence = constraint.Constraint.ALWAYS
                        else:
                                presence = constraint.Constraint.MAYBE
                elif ctype == "transfer":
                        presence = constraint.Constraint.MAYBE

                assert presence

                return f, constraint.Constraint(name, min_ver, max_ver,
                    presence, source_name)

        def verify(self, image, **args):
                # XXX Exclude and range between min and max not yet handled

                ctype = self.attrs["type"]

                if ctype not in self.known_types:
                        return ["Unknown type (%s) in depend action" % ctype]

                pkgfmri = self.attrs["fmri"]
                f = fmri.PkgFmri(pkgfmri, image.attrs["Build-Release"])

                installed_version = image.get_version_installed(f)

                min_fmri, cons = self.parse(image, "")

                if cons.max_ver:
                        max_fmri = min_fmri.copy()
                        max_fmri.version = cons.max_ver
                else:
                        max_fmri = None

                required = (cons.presence == constraint.Constraint.ALWAYS)

                if installed_version:
                        vi = installed_version.version
                        if min_fmri and min_fmri.version and \
                            min_fmri.version.is_successor(vi,
                            pkg.version.CONSTRAINT_NONE):
                                return ["%s dependency %s is downrev (%s)" %
                                    (ctype, min_fmri, installed_version)]
                        if max_fmri and vi > max_fmri.version and \
                            not vi.is_successor(max_fmri.version,
                            pkg.version.CONSTRAINT_AUTO):
                                return ["%s dependency %s is uprev (%s)" %
                                    (ctype, max_fmri, installed_version)]
                elif required:
                        return ["Required dependency %s is not installed" % f]

                return []

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                ctype = self.attrs["type"]
                pfmri = self.attrs["fmri"]

                if ctype not in self.known_types:
                        return []

                #
                # XXX Ideally, we'd turn the string into a PkgFmri, and separate
                # the stem from the version, or use get_dir_path, but we can't
                # create a PkgFmri without supplying a build release and without
                # it creating a dummy timestamp.  So we have to split it apart
                # manually.
                #
                # XXX This code will need to change if we start using fmris
                # with publishers in dependencies.
                #
                if pfmri.startswith("pkg:/"):
                        pfmri = pfmri[5:]
                # Note that this creates a directory hierarchy!
                inds = [
                        ("depend", ctype, pfmri, None)
                ]

                if "@" in pfmri:
                        stem = pfmri.split("@")[0]
                        inds.append(("depend", ctype, stem, None))
                return inds
