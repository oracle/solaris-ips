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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
#


"""Action describing a package dependency.

This module contains the DependencyAction class, which represents a
relationship between the package containing the action and another package.
"""

import generic
import pkg.fmri as fmri
import pkg.version

known_types = ("optional", "require", "exclude", "incorporate", 
    "conditional", "require-any", "origin")

class DependencyAction(generic.Action):
        """Class representing a dependency packaging object.  The fmri attribute
        is expected to be the pkg FMRI that this package depends on.  The type
        attribute is one of these:

        optional - optional dependency on minimum version of other package. In
        other words, if installed, other packages must be at least at specified
        version level.

        require -  dependency on minimum version of other package is needed 
        for correct function of this package.

        conditional - dependency on minimum version of specified package
        if predicate package is installed at specified version or newer.

        require-any - dependency on minimum version of any of the specified
        packages.

        origin - specified package must be at this version or newer
        in order to install this package; if root-image=true, dependency is
        on version installed in / rather than image being modified.

        incorporate - optional dependency on precise version of other package; 
        non-specified portion of version is free to float.

        exclude - package may not be installed together with named version 
        or higher - reverse logic of require."""

        __slots__ = []

        name = "depend"
        key_attr = "fmri"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                if "type" not in self.attrs:
                        raise pkg.actions.InvalidActionError(
                            str(self), _("Missing type attribute"))

                if "fmri" not in self.attrs:
                        raise pkg.actions.InvalidActionError(
                            str(self), _("Missing fmri attribute"))

                if len(self.attrlist("fmri")) > 1 and \
                    self.attrs["type"] != "require-any":
                        raise pkg.actions.InvalidActionError(str(self), 
                            _("Multiple fmris specifed for %s dependency type") % 
                            self.attrs["type"])

                if self.attrs["type"] not in known_types:
                        raise pkg.actions.InvalidActionError(str(self),
                            _("Unknown type (%s) in depend action") %
                            self.attrs["type"])

                if "type" == "conditional" and \
                    "predicate" not in self.attrs:
                        raise pkg.actions.InvalidActionError(str(self),
                            _("No predicate specified for conditional dependency"))
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
                knows about that, too."""

                # This hack corrects a problem in pre-2008.11 packaging
                # metadata: some depend actions were specified with invalid
                # fmris of the form 2.38.01.01.3 (the padding zero is considered
                # invalid).  When we get an invalid FMRI, we use regular
                # expressions to perform a replacement operation which
                # cleans up these problems.  It is hoped that someday this
                # function may be removed completely once applicable releases
                # are EOL'd.
                #
                # n.b. that this parser is not perfect: it will fix only
                # the 'release' and 'branch' part of depend fmris-- these
                # are the only places we've seen rules violations.
                #
                # Lots of things could go wrong here-- the caller should
                # catch ValueError.
                #
                fmri_string = self.attrs["fmri"]
                if not isinstance(fmri_string, basestring):
                        return 
                #
                # First, try to eliminate fmris that don't need cleaning since
                # this process is relatively expensive (when considering tens
                # of thousands of executions).  This currently leaves us with
                # about 5-8% false positives, but is still a huge win overall.
                # This won't account for cases like 'foo@00.1.2', but there
                # are currently no known cases of that and the publication
                # tools don't allow that syntax (currently) anyway.
                #
                if fmri_string.find(".0") == -1:
                        # Nothing to do.
                        return

                #
                # Next, locate the @ and the "," or "-" or ":" which
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

        def __check_installed(self, image, installed_version, min_fmri,
            max_fmri, required, ctype):
                errors = []
                if not installed_version:
                        return errors
                vi = installed_version.version
                if min_fmri and min_fmri.version and \
                    min_fmri.version.is_successor(vi,
                    pkg.version.CONSTRAINT_NONE):
                        errors.append(
                            _("%(dep_type)s dependency %(dep_val)s "
                            "is downrev (%(inst_ver)s)") % {
                            "dep_type": ctype, "dep_val": min_fmri,
                            "inst_ver": installed_version })
                        return errors
                if max_fmri and max_fmri.version and  \
                    vi > max_fmri.version and \
                    not vi.is_successor(max_fmri.version,
                    pkg.version.CONSTRAINT_AUTO):
                        errors.append(
                            _("%(dep_type)s dependency %(dep_val)s "
                            "is uprev (%(inst_ver)s)") % {
                            "dep_type": ctype, "dep_val": max_fmri,
                            "inst_ver": installed_version })
                        return errors
                if required and image.PKG_STATE_OBSOLETE in \
                    image.get_pkg_state(installed_version):
                        errors.append(
                            _("%s dependency on an obsolete package (%s);"
                            "this package must be uninstalled manually") % 
                            (ctype, installed_version))                                  
                        return errors
                return errors

        def verify(self, image, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []

                # XXX Exclude and range between min and max not yet handled
                def __min_version():
                        return pkg.version.Version("0",
                            image.attrs["Build-Release"])

                ctype = self.attrs["type"]

                if ctype not in known_types:
                        errors.append(
                            _("Unknown type (%s) in depend action") % ctype)
                        return errors, warnings, info

                pfmris = [
                    fmri.PkgFmri(f, image.attrs["Build-Release"]) 
                    for f in self.attrlist("fmri")
                ]

                installed_versions = [
                    image.get_version_installed(f) 
                    for f in pfmris
                ]

                installed_version = installed_versions[0]
                pfmri = pfmris[0]

                min_fmri = None
                max_fmri = None
                required = False

                if ctype == "require":
                        required = True
                        min_fmri = pfmri
                elif ctype == "incorporate":
                        max_fmri = pfmri
                        min_fmri = pfmri
                elif ctype == "optional":
                        min_fmri = pfmri
                elif ctype == "exclude":
                        max_fmri = pfmri
                        min_fmri = pfmri.copy()
                        min_fmri.version = __min_version()
                elif ctype == "conditional":
                        cfmri = fmri.PkgFmri(self.attrs["predicate"],
                            image.attrs["Build-Release"])
                        installed_cversion = image.get_version_installed(cfmri)
                        if installed_cversion is not None and \
                            installed_cversion.is_successor(cfmri):
                                min_fmri = pfmri
                                required = True
                elif ctype == "require-any":
                        for ifmri, pfmri in zip(installed_versions, pfmris):
                                e = self.__check_installed(image, ifmri, pfmri, None, True, ctype)
                                if ifmri and not e: # this one is present and happy
                                        return [], [], []
                                else:
                                        errors.extend(e)

                        if not errors: # none was installed
                                errors.append(_("Required dependency on one of %s not met"),
                                    ", ".join(pfmris))
                        return errors, warnings, info

                # do checking for other dependency types

                errors.extend(self.__check_installed(image, installed_version,
                    min_fmri, max_fmri, required, ctype))

                if required and not installed_version:
                        errors.append(_("Required dependency %s is not "
                            "installed") % pfmri)

                # cannot verify origin since it applys to upgrade
                # operation, not final state

                return errors, warnings, info
            

        def generate_indices(self):
                """Generates the indices needed by the search dictionary.  See
                generic.py for a more detailed explanation."""

                ctype = self.attrs["type"]
                pfmris = self.attrs["fmri"]

                if ctype not in known_types:
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
                if isinstance(pfmris, basestring):
                        pfmris = [pfmris]
                inds = []
                for p in pfmris:
                        if p.startswith("pkg:/"):
                                p = p[5:]
                        # Note that this creates a directory hierarchy!
                        inds.append(
                                ("depend", ctype, p, None)
                        )

                        if "@" in p:
                                stem = p.split("@")[0]
                                inds.append(("depend", ctype, stem, None))
                return inds
