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
import pkg.actions
import pkg.fmri
import pkg.version

known_types = (
    "conditional",
    "exclude",
    "group",
    "incorporate",
    "optional",
    "origin",
    "parent",
    "require",
    "require-any")

#
# this is a special package name that when present in an fmri defines a
# dependency on the current package in which the dependency is present.
# this is useful with the "parent" dependency type.
#
DEPEND_SELF = "feature/package/dependency/self"

class DependencyAction(generic.Action):
        """Class representing a dependency packaging object.  The fmri attribute
        is expected to be the pkg FMRI that this package depends on.  The type
        attribute is one of these:

        optional - optional dependency on minimum version of other package. In
        other words, if installed, other packages must be at least at specified
        version level.

        require - dependency on minimum version of other package is needed
        for correct function of this package.

        conditional - dependency on minimum version of specified package
        if predicate package is installed at specified version or newer.

        require-any - dependency on minimum version of any of the specified
        packages.

        origin - specified package must be at this version or newer
        in order to install this package; if root-image=true, dependency is
        on version installed in / rather than image being modified.

        parent - dependency on same version of this package being present in
        the parent image.  if the current image is not a child then this
        dependency is ignored.

        incorporate - optional dependency on precise version of other package;
        non-specified portion of version is free to float.

        exclude - package may not be installed together with named version
        or higher - reverse logic of require.

        group - a version of package is required unless stem is in image
        avoid list; version part of fmri is ignored.  Obsolete packages
        are assumed to satisfy dependency."""

        __slots__ = []

        name = "depend"
        key_attr = "fmri"

        def __init__(self, data=None, **attrs):
                generic.Action.__init__(self, data, **attrs)
                if "type" not in self.attrs:
                        raise pkg.actions.InvalidActionError(
                            str(self), _("Missing type attribute"))

                if self.attrs["type"] not in known_types:
                        raise pkg.actions.InvalidActionError(str(self),
                            _("Unknown type (%s) in depend action") %
                            self.attrs["type"])

        def __check_parent_installed(self, image, fmri):

                if not image.linked.ischild():
                        # if we're not a linked child then ignore "parent"
                        # dependencies.
                        return []

                # create a dictionary of packages installed in the parent
                ppkgs_dict = dict([
                    (i.pkg_name, i)
                    for i in image.linked.parent_fmris()
                ])

                errors = []
                if fmri.pkg_name not in ppkgs_dict:
                        errors.append(_("Package is not installed in "
                            "parent image %s") % fmri.pkg_name)
                        return errors

                pf = ppkgs_dict[fmri.pkg_name]
                if fmri.publisher and fmri.publisher != pf.publisher:
                        # package is from a different publisher
                        errors.append(_("Package in parent is from a "
                            "different publisher: %s") % pf)
                        return errors

                if pf.version == fmri.version or pf.version.is_successor(
                    fmri.version, pkg.version.CONSTRAINT_AUTO):
                        # parent dependency is satisfied
                        return []

                if pf.version.is_successor(fmri.version,
                    pkg.version.CONSTRAINT_NONE):
                        errors.append(_("Parent image has a newer "
                            "version of package %s") % pf)
                else:
                        errors.append(_("Parent image has an older "
                            "version of package %s") % pf)

                return errors

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

        def verify(self, image, pfmri, **args):
                """Returns a tuple of lists of the form (errors, warnings,
                info).  The error list will be empty if the action has been
                correctly installed in the given image."""

                errors = []
                warnings = []
                info = []

                # the fmri for the package containing this action should
                # include a publisher
                assert pfmri.publisher

                # XXX Exclude and range between min and max not yet handled
                def __min_version():
                        return pkg.version.Version("0",
                            image.attrs["Build-Release"])

                ctype = self.attrs["type"]

                if ctype not in known_types:
                        errors.append(
                            _("Unknown type (%s) in depend action") % ctype)
                        return errors, warnings, info

                # get a list of fmris and do fmri token substitution
                pfmris = []
                for i in self.attrlist("fmri"):
                        f = pkg.fmri.PkgFmri(i, image.attrs["Build-Release"])
                        if f.pkg_name == DEPEND_SELF:
                                f = pfmri
                        pfmris.append(f)

                if ctype == "parent":
                        # handle "parent" dependencies here
                        assert len(pfmris) == 1
                        errors.extend(self.__check_parent_installed(image,
                            pfmris[0]))
                        return errors, warnings, info

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
                        cfmri = pkg.fmri.PkgFmri(self.attrs["predicate"],
                            image.attrs["Build-Release"])
                        installed_cversion = image.get_version_installed(cfmri)
                        if installed_cversion is not None and \
                            installed_cversion.is_successor(cfmri):
                                min_fmri = pfmri
                                required = True
                elif ctype == "group":
                        if pfmri.pkg_name not in \
                            (image.avoid_set_get() | image.obsolete_set_get()):
                                required = True
                elif ctype == "require-any":
                        for ifmri, rpfmri in zip(installed_versions, pfmris):
                                e = self.__check_installed(image, ifmri, rpfmri,
                                    None, True, ctype)
                                if ifmri and not e:
                                        # this one is present and happy
                                        return [], [], []
                                else:
                                        errors.extend(e)

                        if not errors: # none was installed
                                errors.append(_("Required dependency on one of "
                                    "%s not met") %
                                    ", ".join((str(p) for p in pfmris)))
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

        def pretty_print(self):
                """Write a dependency action across multiple lines.  This is
                designed to be used in exceptions for cleaner printing of
                unsatisfied dependencies."""

                base_indent = "    "
                act = self
                out = base_indent + act.name

                if hasattr(act, "hash") and act.hash != "NOHASH":
                        out += " " + act.hash

                # high order bits in sorting
                def kvord(a):
                        # Variants should always be last attribute.
                        if a[0].startswith("variant."):
                                return 7
                        # Facets should always be before variants.
                        if a[0].startswith("facet."):
                                return 6
                        # List attributes should be before facets and variants.
                        if isinstance(a[1], list):
                                return 5

                        # For depend actions, type should always come
                        # first even though it's not the key attribute,
                        # and fmri should always come after type.
                        if a[0] == "fmri":
                                return 1
                        elif a[0] == "type":
                                return 0
                        # Any other attributes should come just before list,
                        # facet, and variant attributes.
                        if a[0] != act.key_attr:
                                return 4

                        # No special order for all other cases.
                        return 0

                # actual cmp function
                def cmpkv(a, b):
                        c = cmp(kvord(a), kvord(b))
                        if c:
                                return c

                        return cmp(a[0], b[0])

                JOIN_TOK = " \\\n    " + base_indent
                def grow(a, b, rem_values, force_nl=False):
                        if not force_nl:
                                lastnl = a.rfind("\n")
                                if lastnl == -1:
                                        lastnl = 0

                                if rem_values == 1:
                                        # If outputting the last attribute
                                        # value, then use full line length.
                                        max_len = 80
                                else:
                                        # If V1 format, or there are more
                                        # attributes to output, then account for
                                        # line-continuation marker.
                                        max_len = 78

                                # Note this length comparison doesn't include
                                # the space used to append the second part of
                                # the string.
                                if (len(a) - lastnl + len(b) < max_len):
                                        return a + " " + b
                        return a + JOIN_TOK + b

                def astr(aout):
                        # Number of attribute values for first line and
                        # remaining.
                        first_line = True

                        # Total number of remaining attribute values to output.
                        rem_count = sum(len(act.attrlist(k)) for k in act.attrs)

                        # Now build the action output string an attribute at a
                        # time.
                        for k, v in sorted(act.attrs.iteritems(), cmp=cmpkv):
                                # Newline breaks are only forced when there is
                                # more than one value for an attribute.
                                if not (isinstance(v, list) or
                                    isinstance(v, set)):
                                        nv = [v]
                                        use_force_nl = False
                                else:
                                        nv = v
                                        use_force_nl = True

                                for lmt in sorted(nv):
                                        force_nl = use_force_nl and \
                                            k.startswith("pkg.debug")
                                        aout = grow(aout,
                                            "=".join((k,
                                                generic.quote_attr_value(lmt))),
                                            rem_count,
                                            force_nl=force_nl)
                                        # Must be done for each value.
                                        if first_line and JOIN_TOK in aout:
                                                first_line = False
                                        rem_count -= 1
                        return aout
                return astr(out)

        def validate(self, fmri=None):
                """Performs additional validation of action attributes that
                for performance or other reasons cannot or should not be done
                during Action object creation.  An ActionError exception (or
                subclass of) will be raised if any attributes are not valid.
                This is primarily intended for use during publication or during
                error handling to provide additional diagonostics.

                'fmri' is an optional package FMRI (object or string) indicating
                what package contained this action."""

                required_attrs = ["type"]
                dtype = self.attrs.get("type")
                if dtype == "conditional":
                        required_attrs.append("predicate")

                errors = generic.Action._validate(self, fmri=fmri,
                    raise_errors=False, required_attrs=required_attrs,
                    single_attrs=("predicate", "root-image"))

                if "predicate" in self.attrs and dtype != "conditional":
                        errors.append(("predicate", _("a predicate may only be "
                            "specified for conditional dependencies")))
                if "root-image" in self.attrs and dtype != "origin":
                        errors.append(("root-image", _("the root-image "
                            "attribute is only valid for origin dependencies")))

                # Logic here intentionally treats 'predicate' and 'fmri' as
                # having multiple values for simplicity.
                for attr in ("predicate", "fmri"):
                        for f in self.attrlist(attr):
                                try:
                                        pkg.fmri.PkgFmri(f, "5.11")
                                except (pkg.version.VersionError,
                                    pkg.fmri.FmriError), e:
                                        if attr == "fmri" and f == "__TBD":
                                                # pkgdepend uses this special
                                                # value.
                                                continue
                                        errors.append((attr, _("invalid "
                                            "%(attr)s value '%(value)s': "
                                            "%(error)s") % { "attr": attr,
                                            "value": f, "error": str(e) }))

                if errors:
                        raise pkg.actions.InvalidActionAttributesError(self,
                            errors, fmri=fmri)
