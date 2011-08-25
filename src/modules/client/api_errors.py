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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import errno
import os
import xml.parsers.expat as expat
import urlparse

# pkg classes
import pkg.client.pkgdefs as pkgdefs

# EmptyI for argument defaults; can't import from misc due to circular
# dependency.
EmptyI = tuple()

class ApiException(Exception):
        def __init__(self, *args):
                Exception.__init__(self)
                self.__verbose_info = []

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return unicode(str(self))

        def add_verbose_info(self, info):
                self.__verbose_info.extend(info)

        @property
        def verbose_info(self):
                return self.__verbose_info

class SuidUnsupportedError(ApiException):
        def __str__(self):
                return _("""
The pkg client api module can not be invoked from an setuid executable.""")


class HistoryException(ApiException):
        """Private base exception class for all History exceptions."""

        def __init__(self, *args):
                Exception.__init__(self, *args)
                self.error = args[0]

        def __str__(self):
                return str(self.error)


class HistoryLoadException(HistoryException):
        """Used to indicate that an unexpected error occurred while loading
        History operation information.

        The first argument should be an exception object related to the
        error encountered.
        """
        def __init__(self, *args):
                HistoryException.__init__(self, *args)
                self.parse_failure = isinstance(self.error, expat.ExpatError)


class HistoryRequestException(HistoryException):
        """Used to indicate that invalid time / range values were provided to
        history API functions."""
        pass


class HistoryStoreException(HistoryException):
        """Used to indicate that an unexpected error occurred while storing
        History operation information.

        The first argument should be an exception object related to the
        error encountered.
        """
        pass


class HistoryPurgeException(HistoryException):
        """Used to indicate that an unexpected error occurred while purging
        History operation information.

        The first argument should be an exception object related to the
        error encountered.
        """
        pass


class ImageLockedError(ApiException):
        """Used to indicate that the image is currently locked by another thread
        or process and cannot be modified."""

        def __init__(self, hostname=None, pid=None, pid_name=None):
                ApiException.__init__(self)
                self.hostname = hostname
                self.pid = pid
                self.pid_name = pid_name

        def __str__(self):
                if self.pid is not None and self.pid_name is not None and \
                    self.hostname is not None:
                        return _("The image cannot be modified as it is "
                            "currently in use by another package client: "
                            "%(pid_name)s on %(host)s, pid %(pid)s.") % {
                            "pid_name": self.pid_name, "pid": self.pid,
                            "host": self.hostname }
                if self.pid is not None and self.pid_name is not None:
                        return _("The image cannot be modified as it is "
                            "currently in use by another package client: "
                            "%(pid_name)s on an unknown host, pid %(pid)s.") % {
                            "pid_name": self.pid_name, "pid": self.pid }
                elif self.pid is not None:
                        return _("The image cannot be modified as it is "
                            "currently in use by another package client: "
                            "pid %(pid)s on %(host)s.") % {
                            "pid": self.pid, "host": self.hostname }
                return _("The image cannot be modified as it is currently "
                    "in use by another package client.")

class ImageNotFoundException(ApiException):
        """Used when an image was not found"""
        def __init__(self, user_specified, user_dir, root_dir):
                ApiException.__init__(self)
                self.user_specified = user_specified
                self.user_dir = user_dir
                self.root_dir = root_dir


class ImageFormatUpdateNeeded(ApiException):
        """Used to indicate that an image cannot be used until its format is
        updated."""

        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                return _("The image rooted at %s is written in an older format "
                    "and must be updated before the requested operation can be "
                    "performed.") % self.path

class ImageInsufficentSpace(ApiException):
        """Used when insuffcient space exists for proposed operation"""
        def __init__(self, needed, avail, use):
                self.needed = needed
                self.avail = avail
                self.use = use

        def __str__(self):
                from pkg.misc import bytes_to_str
                return _("Insufficent disk space available (%(avail)s)"
                    "for estimated need (%(needed)s) for %(use)s") % {
                    "avail":  bytes_to_str(self.avail),
                    "needed": bytes_to_str(self.needed),
                    "use": self.use
                    }
                    

class VersionException(ApiException):
        def __init__(self, expected_version, received_version):
                ApiException.__init__(self)
                self.expected_version = expected_version
                self.received_version = received_version


class PlanExistsException(ApiException):
        def __init__(self, plan_type):
                ApiException.__init__(self)
                self.plan_type = plan_type


class PlanPrepareException(ApiException):
        """Base exception class for plan preparation errors."""
        pass


class InvalidPackageErrors(ApiException):
        """Used to indicate that the requested operation could not be completed
        as one or more packages contained invalid metadata."""

        def __init__(self, errors):
                """'errors' should be a list of exceptions or strings
                indicating what packages had errors and why."""

                ApiException.__init__(self)
                self.errors = errors

        def __str__(self):
                return _("The requested operation cannot be completed due "
                    "to invalid package metadata.  Details follow:\n\n"
                    "%s") % "\n".join(str(e) for e in self.errors)


class LicenseAcceptanceError(ApiException):
        """Used to indicate that license-related errors occurred during
        plan evaluation or execution."""

        def __init__(self, pfmri, src=None, dest=None, accepted=None,
            displayed=None):
                ApiException.__init__(self)
                self.fmri = pfmri
                self.src = src
                self.dest = dest
                self.accepted = accepted
                self.displayed = displayed


class PkgLicenseErrors(PlanPrepareException):
        """Used to indicate that plan evaluation or execution failed due
        to license-related errors for a package."""

        def __init__(self, errors):
                """'errors' should be a list of LicenseAcceptanceError
                exceptions."""

                PlanPrepareException.__init__(self)
                self.__errors = errors

        @property
        def errors(self):
                """A list of LicenseAcceptanceError exceptions."""
                return self.__errors


class PlanLicenseErrors(PlanPrepareException):
        """Used to indicate that image plan evaluation or execution failed due
        to license-related errors."""

        def __init__(self, pp_errors):
                """'errors' should be a list of PkgLicenseErrors exceptions."""

                PlanPrepareException.__init__(self)
                self.__errors = pkgs = {}
                for pp_err in pp_errors:
                        for e in pp_err.errors:
                                pkgs.setdefault(str(e.fmri), []).append(e)

        @property
        def errors(self):
                """Returns a dictionary indexed by package FMRI string of
                lists of LicenseAcceptanceError exceptions."""

                return self.__errors

        def __str__(self):
                """Returns a string representation of the license errors."""

                output = ""
                for sfmri in self.__errors:
                        output += ("-" * 40) + "\n"
                        output += _("Package: %s\n\n") % sfmri
                        for e in self.__errors[sfmri]:
                                lic_name = e.dest.attrs["license"]
                                output += _("License: %s\n") % lic_name
                                if e.dest.must_accept and not e.accepted:
                                        output += _("  License requires "
                                            "acceptance.")
                                if e.dest.must_display and not e.displayed:
                                        output += _("  License must be viewed.")
                                output += "\n"
                return output


class ActuatorException(ApiException):
        def __init__(self, e):
                ApiException.__init__(self)
                self.exception = e

        def __str__(self):
                return str(self.exception)


class PrematureExecutionException(ApiException):
        pass


class AlreadyPreparedException(PlanPrepareException):
        pass


class AlreadyExecutedException(ApiException):
        pass


class ImageplanStateException(ApiException):
        def __init__(self, state):
                ApiException.__init__(self)
                self.state = state


class InvalidPlanError(ApiException):
        """Used to indicate that the image plan is no longer valid, likely as a
        result of an image state change since the plan was created."""

        def __str__(self):
                return _("The plan for the current operation is no longer "
                    "valid.  The image has likely been modified by another "
                    "process or client.  Please try the operation again.")


class ImagePkgStateError(ApiException):

        def __init__(self, fmri, states):
                ApiException.__init__(self)
                self.fmri = fmri
                self.states = states

        def __str__(self):
                return _("Invalid package state change attempted '%(states)s' "
                    "for package '%(fmri)s'.") % { "states": self.states,
                    "fmri": self.fmri }


class IpkgOutOfDateException(ApiException):
        pass

class ImageUpdateOnLiveImageException(ApiException):
        pass

class RebootNeededOnLiveImageException(ApiException):
        pass

class CanceledException(ApiException):
        pass

class PlanMissingException(ApiException):
        pass

class NoPackagesInstalledException(ApiException):
        pass

class PermissionsException(ApiException):
        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                if self.path:
                        return _("Could not operate on %s\nbecause of "
                            "insufficient permissions. Please try the "
                            "command again as a privileged user.") % \
                            self.path
                else:
                        return _("""
Could not complete the operation because of insufficient permissions.
Please try the command again as a privileged user.
""")

class FileInUseException(PermissionsException):
        def __init__(self, path):
                PermissionsException.__init__(self, path)
                assert path

        def __str__(self):
                return _("Could not operate on %s\nbecause the file is "
                    "in use. Please stop using the file and try the\n"
                    "operation again.") % self.path


class ReadOnlyFileSystemException(PermissionsException):
        """Used to indicate that the operation was attempted on a
        read-only filesystem"""

        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                if self.path:
                        return _("Could not complete the operation on %s: "
                            "read-only filesystem.") % self.path
                return _("Could not complete the operation: read-only "
                        "filesystem.")


class PackageMatchErrors(ApiException):
        """Used to indicate which patterns were not matched or illegal during
        a package name matching operation."""

        def __init__(self, unmatched_fmris=EmptyI, multiple_matches=EmptyI,
            illegal=EmptyI, multispec=EmptyI):
                ApiException.__init__(self)
                self.unmatched_fmris = unmatched_fmris
                self.multiple_matches = multiple_matches
                self.illegal = illegal
                self.multispec = multispec

        def __str__(self):
                res = []
                if self.unmatched_fmris:
                        s = _("The following pattern(s) did not match any "
                            "packages:")

                        res += [s]
                        res += ["\t%s" % p for p in self.unmatched_fmris]

                if self.multiple_matches:
                        s = _("'%s' matches multiple packages")
                        for p, lst in self.multiple_matches:
                                res.append(s % p)
                                for pfmri in lst:
                                        res.append("\t%s" % pfmri)

                if self.illegal:
                        s = _("'%s' is an illegal FMRI")
                        res += [ s % p for p in self.illegal ]

                if self.multispec:
                        s = _("The following different patterns specify the "
                          "same package(s):")
                        res += [s]
                        for t in self.multispec:
                                res += [
                                    ", ".join([t[i] for i in range(1, len(t))])
                                    + ": %s" % t[0]
                                ]

                return "\n".join(res)


class PlanCreationException(ApiException):
        def __init__(self,
            already_installed=EmptyI,
            badarch=EmptyI,
            illegal=EmptyI,
            installed=EmptyI,
            invalid_mediations=EmptyI,
            linked_pub_error=EmptyI,
            missing_dependency=EmptyI,
            missing_matches=EmptyI,
            multiple_matches=EmptyI,
            multispec=EmptyI,
            no_solution=False,
            no_tmp_origins=False,
            no_version=EmptyI,
            not_avoided=EmptyI,
            nofiles=EmptyI,
            obsolete=EmptyI,
            pkg_updates_required=EmptyI,
            rejected_pats=EmptyI,
            solver_errors=EmptyI,
            unmatched_fmris=EmptyI,
            would_install=EmptyI,
            wrong_publishers=EmptyI,
            wrong_variants=EmptyI):

                ApiException.__init__(self)
                self.already_installed     = already_installed
                self.badarch               = badarch
                self.illegal               = illegal
                self.installed             = installed
                self.invalid_mediations    = invalid_mediations
                self.linked_pub_error      = linked_pub_error
                self.missing_dependency    = missing_dependency
                self.missing_matches       = missing_matches
                self.multiple_matches      = multiple_matches
                self.multispec             = multispec
                self.no_solution           = no_solution
                self.no_tmp_origins        = no_tmp_origins
                self.no_version            = no_version
                self.not_avoided           = not_avoided
                self.nofiles               = nofiles
                self.obsolete              = obsolete
                self.pkg_updates_required  = pkg_updates_required
                self.rejected_pats         = rejected_pats
                self.solver_errors         = solver_errors
                self.unmatched_fmris       = unmatched_fmris
                self.would_install         = would_install
                self.wrong_publishers      = wrong_publishers
                self.wrong_variants        = wrong_variants

        def __str__(self):
                res = []
                if self.unmatched_fmris:
                        s = _("""\
The following pattern(s) did not match any allowable packages.  Try
using a different matching pattern, or refreshing publisher information:
""")
                        res += [s]
                        res += ["\t%s" % p for p in self.unmatched_fmris]

                if self.rejected_pats:
                        s = _("""\
The following pattern(s) only matched packages rejected by user request.  Try
using a different matching pattern, or refreshing publisher information:
""")
                        res += [s]
                        res += ["\t%s" % p for p in self.rejected_pats]

                if self.wrong_variants:
                        s = _("""\
The following pattern(s) only matched packages that are not available
for the current image's architecture, zone type, and/or other variant:""")
                        res += [s]
                        res += ["\t%s" % p for p in self.wrong_variants]

                if self.wrong_publishers:
                        s = _("The following patterns only matched packages "
                            "that are from publishers other than that which "
                            "supplied the already installed version of this package")
                        res += [s]
                        res += ["\t%s: %s" % (p[0], ", ".join(p[1])) for p in self.wrong_publishers]

                if self.multiple_matches:
                        s = _("'%s' matches multiple packages")
                        for p, lst in self.multiple_matches:
                                res.append(s % p)
                                for pfmri in lst:
                                        res.append("\t%s" % pfmri)

                if self.missing_matches:
                        s = _("'%s' matches no installed packages")
                        res += [ s % p for p in self.missing_matches ]

                if self.illegal:
                        s = _("'%s' is an illegal fmri")
                        res += [ s % p for p in self.illegal ]

                if self.badarch:
                        s = _("'%s' supports the following architectures: %s")
                        a = _("Image architecture is defined as: %s")
                        res += [ s % (self.badarch[0],
                            ", ".join(self.badarch[1]))]
                        res += [ a % (self.badarch[2])]

                s = _("'%(p)s' depends on obsolete package '%(op)s'")
                res += [ s % {"p": p, "op": op} for p, op in self.obsolete ]

                if self.installed:
                        s = _("The proposed operation can not be performed for "
                            "the following package(s) as they are already "
                            "installed: ")
                        res += [s]
                        res += ["\t%s" % p for p in self.installed]

                if self.invalid_mediations:
                        s = _("The following mediations are not syntactically "
                            "valid:")
                        for m, entries in self.invalid_mediations.iteritems():
                                for value, error in entries.values():
                                        res.append(error)

                if self.multispec:
                        s = _("The following different patterns specify the "
                              "same package(s):")
                        res += [s]
                        for t in self.multispec:
                                res += [
                                        ", ".join(
                                        [t[i] for i in range(1, len(t))])
                                        + ": %s" % t[0]
                                        ]
                if self.no_solution:
                        res += [_("No solution was found to satisfy constraints")]
                        if isinstance(self.no_solution, list):
                                res.extend(self.no_solution)

                if self.pkg_updates_required:
                        s = _("""\
Syncing this linked image would require the following package updates:
""")
                        res += [s]
                        for (oldfmri, newfmri) in self.pkg_updates_required:
                                res += ["%(oldfmri)s -> %(newfmri)s\n" % \
                                    {"oldfmri": oldfmri, "newfmri": newfmri}]

                if self.no_version:
                        res += self.no_version

                if self.no_tmp_origins:
                        s = _("""
The proposed operation on this parent image can not be performed because
temporary origins were specified and this image has children.  Please either
retry the operation again without specifying any temporary origins, or if
packages from additional origins are required, please configure those origins
persistently.""")
                        res = [s]

                if self.missing_dependency:
                        res += [_("Package %(pkg)s is missing a dependency: "
                            "%(dep)s") %
                            {"pkg": self.missing_dependency[0],
                             "dep": self.missing_dependency[1]}]
                if self.nofiles:
                        res += [_("The following files are not packaged in this image:")]
                        res += ["\t%s" % f for f in self.nofiles]

                if self.solver_errors:
                        res += ["\n"]
                        res += [_("Solver dependency errors:")]
                        res.extend(self.solver_errors)

                if self.already_installed:
                        res += [_("The following packages are already "
                            "installed in this image; use uninstall to "
                            "avoid these:")]
                        res += [ "\t%s" % s for s in self.already_installed]

                if self.would_install:
                        res += [_("The following packages are a target "
                            "of group dependencies; use install to unavoid "
                            "these:")]
                        res += [ "\t%s" % s for s in self.would_install]

                if self.not_avoided:
                        res += [_("The following packages are not on the "
                            "avoid list, so they\ncannot be removed from it.")]
                        res += [ "\t%s" % s for s in sorted(self.not_avoided)]

                def __format_li_pubs(pubs, res):
                        i = 0
                        for pub, sticky in pubs:
                                s = "    %s %d: %s" % (_("PUBLISHER"), i, pub)
                                mod = []
                                if not sticky:
                                        mod.append(_("non-sticky"))
                                if mod:
                                        s += " (%s)" % ",".join(mod)
                                res.append(s)
                                i += 1

                if self.linked_pub_error:
                        res = []
                        (pubs, parent_pubs) = self.linked_pub_error

                        res.append(_("""
Invalid child image publisher configuration.  Child image publisher
configuration must be a superset of the parent image publisher configuration.
Please update the child publisher configuration to match the parent.  If the
child image is a zone this can be done automatically by detaching and
attaching the zone.

The parent image has the following enabled publishers:"""))
                        __format_li_pubs(parent_pubs, res)
                        res.append(_("""
The child image has the following enabled publishers:"""))
                        __format_li_pubs(pubs, res)

                return "\n".join(res)


class ConflictingActionError(ApiException):
        """Used to indicate that the imageplan would result in one or more sets
        of conflicting actions, meaning that more than one action would exist on
        the system with the same key attribute value in the same namespace.
        There are three categories, each with its own subclass:

          - multiple files delivered to the same path or drivers, users, groups,
            etc, delivered with the same key attribute;

          - multiple objects delivered to the same path which aren't the same
            type;

          - multiple directories, links, or hardlinks delivered to the same path
            but with conflicting attributes.
        """

        def __init__(self, data):
                self._data = data

class ConflictingActionErrors(ApiException):
        """A container for multiple ConflictingActionError exception objects
        that can be raised as a single exception."""

        def __init__(self, errors):
                self.__errors = errors

        def __str__(self):
                return "\n\n".join((str(err) for err in self.__errors))

class DuplicateActionError(ConflictingActionError):
        """Multiple actions of the same type have been delivered with the same
        key attribute (when not allowed)."""

        def __str__(self):
                pfmris = set((a[1] for a in self._data))
                kv = self._data[0][0].attrs[self._data[0][0].key_attr]
                action = self._data[0][0].name
                if len(pfmris) > 1:
                        s = _("The following packages all deliver %(action)s "
                            "actions to %(kv)s:\n") % locals()
                        for a, p in self._data:
                                s += "\n  %s" % p
                        s += _("\n\nThese packages may not be installed together. "
                            "Any non-conflicting set may\nbe, or the packages "
                            "must be corrected before they can be installed.")
                else:
                        pfmri = pfmris.pop()
                        s = _("The package %(pfmri)s delivers multiple copies "
                            "of %(action)s %(kv)s") % locals()
                        s += _("\nThis package must be corrected before it "
                            "can be installed.")

                return s

class InconsistentActionTypeError(ConflictingActionError):
        """Multiple actions of different types have been delivered with the same
        'path' attribute.  While this exception could represent other action
        groups which share a single namespace, none such exist."""

        def __str__(self):
                ad = {}
                pfmris = set()
                kv = self._data[0][0].attrs[self._data[0][0].key_attr]
                for a, p in self._data:
                        ad.setdefault(a.name, []).append(p)
                        pfmris.add(p)

                if len(pfmris) > 1:
                        s = _("The following packages deliver conflicting "
                            "action types to %s:\n") % kv
                        for name, pl in ad.iteritems():
                                s += "\n  %s:" % name
                                s += "".join("\n    %s" % p for p in pl)
                        s += _("\n\nThese packages may not be installed together. "
                            "Any non-conflicting set may\nbe, or the packages "
                            "must be corrected before they can be installed.")
                else:
                        pfmri = pfmris.pop()
                        types = list_to_lang(ad.keys())
                        s = _("The package %(pfmri)s delivers conflicting "
                            "action types (%(types)s) to %(kv)s") % locals()
                        s += _("\nThis package must be corrected before it "
                            "can be installed.")
                return s

class InconsistentActionAttributeError(ConflictingActionError):
        """Multiple actions of the same type representing the same object have
        have been delivered, but with conflicting attributes, such as two
        directories at /usr with groups 'root' and 'sys', or two 'root' users
        with uids '0' and '7'."""

        def __str__(self):
                actions = self._data
                keyattr = actions[0][0].attrs[actions[0][0].key_attr]
                actname = actions[0][0].name

                # Trim the action's attributes to only those required to be
                # unique.
                def ou(action):
                        ua = dict(
                            (k, v)
                            for k, v in action.attrs.iteritems()
                            if ((k in action.unique_attrs and
                                not (k == "preserve" and "overlay" in action.attrs)) or
                                ((action.name == "link" or action.name == "hardlink") and
                                k.startswith("mediator")))
                        )
                        action.attrs = ua
                        return action

                d = {}
                for a in actions:
                        if a[0].attrs.get("implicit", "false") == "false":
                                d.setdefault(str(ou(a[0])), set()).add(a[1])
                l = sorted([
                    (len(pkglist), action, pkglist)
                    for action, pkglist in d.iteritems()
                ])

                s = _("The requested change to the system attempts to install "
                    "multiple actions\nfor %(a)s '%(k)s' with conflicting "
                    "attributes:\n\n") % {"a": actname, "k": keyattr}
                allpkgs = set()
                for num, action, pkglist in l:
                        allpkgs.update(pkglist)
                        if num <= 5:
                                if num == 1:
                                        t = _("    %(n)d package delivers '%(a)s':\n")
                                else:
                                        t = _("    %(n)d packages deliver '%(a)s':\n")
                                s += t % {"n": num, "a": action}
                                for pkg in sorted(pkglist):
                                        s += _("        %s\n") % pkg
                        else:
                                t = _("    %d packages deliver '%s', including:\n")
                                s += t % (num, action)
                                for pkg in sorted(pkglist)[:5]:
                                        s += _("        %s\n") % pkg

                if len(allpkgs) == 1:
                        s += _("\nThis package must be corrected before it "
                            "can be installed.")
                else:
                        s += _("\nThese packages may not be installed together."
                            "  Any non-conflicting set may\nbe, or the packages "
                            "must be corrected before they can be installed.")

                return s

def list_to_lang(l):
        """Takes a list of items and puts them into a string, with commas in
        between items, and an "and" between the last two items.  Special cases
        for lists of two or fewer items, and uses the Oxford comma."""

        if not l:
                return ""
        if len(l) == 1:
                return l[0]
        if len(l) == 2:
                # Used for a two-element list
                return _("%(penultimate)s and %(ultimate)s") % {
                    "penultimate": l[0],
                    "ultimate": l[1]
                }
        # In order to properly i18n this construct, we create two templates:
        # one for each element save the last, and one that tacks on the last
        # element.
        # 'elementtemplate' is for each element through the penultimate
        elementtemplate = _("%s, ")
        # 'listtemplate' concatenates the concatenation of non-ultimate elements
        # and the ultimate element.
        listtemplate = _("%(list)sand %(tail)s")
        return listtemplate % {
            "list": "".join(elementtemplate % i for i in l[:-1]),
            "tail": l[-1]
        }

class ActionExecutionError(ApiException):
        """Used to indicate that action execution (such as install, remove,
        etc.) failed even though the action is valid.

        In particular, this exception indicates that something went wrong in the
        application (or unapplication) of the action to the system, and is most
        likely not an error in the pkg(5) code."""

        def __init__(self, action, details=None, error=None, fmri=None,
            use_errno=None):
                """'action' is the object for the action that failed during the
                requested operation.

                'details' is an optional message explaining what operation
                failed, why it failed, and why it cannot continue.  It should
                also include a suggestion as to how to resolve the situation
                if possible.

                'error' is an optional exception object that may have been
                raised when the operation failed.

                'fmri' is an optional package FMRI indicating what package
                was being operated on at the time the error occurred.

                'use_errno' is an optional boolean value indicating whether
                the strerror() text of the exception should be used.  If
                'details' is provided, the default value is False, otherwise
                True."""

                assert (details or error)
                self.action = action
                self.details = details
                self.error = error
                self.fmri = fmri
                if use_errno == None:
                        # If details were provided, don't use errno unless
                        # explicitly requested.
                        use_errno = not details
                self.use_errno = use_errno

        def __str__(self):
                errno = ""
                if self.use_errno and self.error and \
                    hasattr(self.error, "errno"):
                        errno = "[errno %d: %s]" % (self.error.errno,
                            os.strerror(self.error.errno))

                details = self.details or ""

                # Fall back on the wrapped exception if we don't have anything
                # useful.
                if not errno and not details:
                        return str(self.error)

                if errno and details:
                        details = "%s: %s" % (errno, details)

                if details and not self.fmri:
                        details = _("Requested operation failed for action "
                            "%(action)s:\n%(details)s") % {
                            "action": self.action,
                            "details": details }
                elif details:
                        details = _("Requested operation failed for package "
                            "%(fmri)s:\n%(details)s") % { "fmri": self.fmri,
                            "details": details }

                # If we only have one of the two, no need for the colon.
                return "%s%s" % (errno, details)


class CatalogRefreshException(ApiException):
        def __init__(self, failed, total, succeeded, errmessage=None):
                ApiException.__init__(self)
                self.failed = failed
                self.total = total
                self.succeeded = succeeded
                self.errmessage = errmessage


class CatalogError(ApiException):
        """Base exception class for all catalog exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs

        def __str__(self):
                return str(self.data)


class AnarchicalCatalogFMRI(CatalogError):
        """Used to indicate that the specified FMRI is not valid for catalog
        operations because it is missing publisher information."""

        def __str__(self):
                return _("The FMRI '%s' does not contain publisher information "
                    "and cannot be used for catalog operations.") % self.data


class BadCatalogMetaRoot(CatalogError):
        """Used to indicate an operation on the catalog's meta_root failed
        because the meta_root is invalid."""

        def __str__(self):
                return _("Catalog meta_root '%(root)s' is invalid; unable "
                    "to complete operation: '%(op)s'.") % { "root": self.data,
                    "op": self._args.get("operation", None) }


class BadCatalogPermissions(CatalogError):
        """Used to indicate the server catalog files do not have the expected
        permissions."""

        def __init__(self, files):
                """files should contain a list object with each entry consisting
                of a tuple of filename, expected_mode, received_mode."""
                if not files:
                        files = []
                CatalogError.__init__(self, files)

        def __str__(self):
                msg = _("The following catalog files have incorrect "
                    "permissions:\n")
                for f in self._args:
                        fname, emode, fmode = f
                        msg += _("\t%(fname)s: expected mode: %(emode)s, found "
                            "mode: %(fmode)s\n") % { "fname": fname,
                            "emode": emode, "fmode": fmode }
                return msg


class BadCatalogSignatures(CatalogError):
        """Used to indicate that the Catalog signatures are not valid."""

        def __str__(self):
                return _("The signature data for the '%s' catalog file is not "
                    "valid.") % self.data


class BadCatalogUpdateIdentity(CatalogError):
        """Used to indicate that the requested catalog updates could not be
        applied as the new catalog data is significantly different such that
        the old catalog cannot be updated to match it."""

        def __str__(self):
                return _("Unable to determine the updates needed for  "
                    "the current catalog using the provided catalog "
                    "update data in '%s'.") % self.data


class DuplicateCatalogEntry(CatalogError):
        """Used to indicate that the specified catalog operation could not be
        performed since it would result in a duplicate catalog entry."""

        def __str__(self):
                return _("Unable to perform '%(op)s' operation for catalog "
                    "%(name)s; completion would result in a duplicate entry "
                    "for package '%(fmri)s'.") % { "op": self._args.get(
                    "operation", None), "name": self._args.get("catalog_name",
                    None), "fmri": self.data }


class CatalogUpdateRequirements(CatalogError):
        """Used to indicate that an update request for the catalog could not
        be performed because update requirements were not satisfied."""

        def __str__(self):
                return _("Catalog updates can only be applied to an on-disk "
                    "catalog.")


class InvalidCatalogFile(CatalogError):
        """Used to indicate a Catalog file could not be loaded."""

        def __str__(self):
                return _("Catalog file '%s' is invalid.") % self.data


class MismatchedCatalog(CatalogError):
        """Used to indicate that a Catalog's attributes and parts do not
        match.  This is likely the result of an attributes file being
        retrieved which doesn't match the parts that were retrieved such
        as in a misconfigured or stale cache case."""

        def __str__(self):
                return _("The content of the catalog for publisher '%s' "
                    "doesn't match the catalog's attributes.  This is "
                    "likely the result of a mix of older and newer "
                    "catalog files being provided for the publisher.") % \
                    self.data


class ObsoleteCatalogUpdate(CatalogError):
        """Used to indicate that the specified catalog updates are for an older
        version of the catalog and cannot be applied."""

        def __str__(self):
                return _("Unable to determine the updates needed for the "
                    "catalog using the provided catalog update data in '%s'. "
                    "The specified catalog updates are for an older version "
                    "of the catalog and cannot be used.") % self.data


class UnknownCatalogEntry(CatalogError):
        """Used to indicate that an entry for the specified package FMRI or
        pattern could not be found in the catalog."""

        def __str__(self):
                return _("'%s' could not be found in the catalog.") % self.data


class UnknownUpdateType(CatalogError):
        """Used to indicate that the specified CatalogUpdate operation is
        unknown."""

        def __str__(self):
                return _("Unknown catalog update type '%s'") % self.data


class UnrecognizedCatalogPart(CatalogError):
        """Raised when the catalog finds a CatalogPart that is unrecognized
        or invalid."""

        def __str__(self):
                return _("Unrecognized, unknown, or invalid CatalogPart '%s'") \
                    % self.data


class InventoryException(ApiException):
        """Used to indicate that some of the specified patterns to a catalog
        matching function did not match any catalog entries, or were invalid
        patterns."""

        def __init__(self, illegal=EmptyI, matcher=EmptyI, notfound=EmptyI,
            publisher=EmptyI, version=EmptyI):
                ApiException.__init__(self)
                self.illegal = illegal
                self.matcher = matcher
                self.notfound = set(notfound)
                self.publisher = publisher
                self.version = version

                self.notfound.update(matcher)
                self.notfound.update(publisher)
                self.notfound.update(version)
                self.notfound = list(self.notfound)

                assert self.illegal or self.notfound

        def __str__(self):
                outstr = ""
                for x in self.illegal:
                        # Illegal FMRIs have their own __str__ method
                        outstr += "%s\n" % x

                if self.matcher or self.publisher or self.version:
                        outstr += _("No matching package could be found for "
                            "the following FMRIs in any of the catalogs for "
                            "the current publishers:\n")

                        for x in self.matcher:
                                outstr += _("%s (pattern did not match)\n") % x
                        for x in self.publisher:
                                outstr += _("%s (publisher did not "
                                    "match)\n") % x
                        for x in self.version:
                                outstr += _("%s (version did not match)\n") % x
                return outstr


# SearchExceptions

class SearchException(ApiException):
        """Based class used for all search-related api exceptions."""
        pass


class MalformedSearchRequest(SearchException):
        """Raised when the server cannot understand the format of the
        search request."""

        def __init__(self, url):
                SearchException.__init__(self)
                self.url = url

        def __str__(self):
                return str(self.url)


class NegativeSearchResult(SearchException):
        """Returned when the search cannot find any matches."""

        def __init__(self, url):
                SearchException.__init__(self)
                self.url = url

        def __str__(self):
                return _("The search at url %s returned no results.") % self.url


class ProblematicSearchServers(SearchException):
        """This class wraps exceptions which could appear while trying to
        do a search request."""

        def __init__(self, failed=EmptyI, invalid=EmptyI, unsupported=EmptyI):
                SearchException.__init__(self)
                self.failed_servers = failed
                self.invalid_servers  = invalid
                self.unsupported_servers = unsupported

        def __str__(self):
                s = _("Some repositories failed to respond appropriately:\n")
                for pub, err in self.failed_servers:
                        s += _("%(o)s:\n%(msg)s\n") % \
                            { "o": pub, "msg": err}
                for pub in self.invalid_servers:
                        s += _("%s did not return a valid response.\n" \
                            % pub)
                if len(self.unsupported_servers) > 0:
                        s += _("Some repositories don't support requested "
                            "search operation:\n")
                for pub, err in self.unsupported_servers:
                        s += _("%(o)s:\n%(msg)s\n") % \
                            { "o": pub, "msg": err}

                return s


class SlowSearchUsed(SearchException):
        """This exception is thrown when a local search is performed without
        an index.  It's raised after all results have been yielded."""

        def __str__(self):
                return _("Search performance is degraded.\n"
                    "Run 'pkg rebuild-index' to improve search speed.")


class UnsupportedSearchError(SearchException):
        """Returned when a search protocol is not supported by the
        remote server."""

        def __init__(self, url=None, proto=None):
                SearchException.__init__(self)
                self.url = url
                self.proto = proto

        def __str__(self):
                s = _("Search repository does not support the requested "
                    "protocol:")
                if self.url:
                        s += "\nRepository URL: %s" % self.url
                if self.proto:
                        s += "\nRequested operation: %s" % self.proto
                return s

        def __cmp__(self, other):
                if not isinstance(other, UnsupportedSearchError):
                        return -1
                r = cmp(self.url, other.url)
                if r != 0:
                        return r
                return cmp(self.proto, other.proto)


# IndexingExceptions.

class IndexingException(SearchException):
        """ The base class for all exceptions that can occur while indexing. """

        def __init__(self, private_exception):
                SearchException.__init__(self)
                self.cause = private_exception.cause


class CorruptedIndexException(IndexingException):
        """This is used when the index is not in a correct state."""
        pass


class InconsistentIndexException(IndexingException):
        """This is used when the existing index is found to have inconsistent
        versions."""
        def __init__(self, e):
                IndexingException.__init__(self, e)
                self.exception = e

        def __str__(self):
                return str(self.exception)


class IndexLockedException(IndexingException):
        """This is used when an attempt to modify an index locked by another
        process or thread is made."""

        def __init__(self, e):
                IndexingException.__init__(self, e)
                self.exception = e

        def __str__(self):
                return str(self.exception)


class ProblematicPermissionsIndexException(IndexingException):
        """ This is used when the indexer is unable to create, move, or remove
        files or directories it should be able to. """
        def __str__(self):
                return "Could not remove or create " \
                    "%s because of incorrect " \
                    "permissions. Please correct this issue then " \
                    "rebuild the index." % self.cause

class WrapIndexingException(ApiException):
        """This exception is used to wrap an indexing exception during install,
        uninstall, or update so that a more appropriate error message can be
        displayed to the user."""

        def __init__(self, e, tb, stack):
                ApiException.__init__(self)
                self.wrapped = e
                self.tb = tb
                self.stack = stack

        def __str__(self):
                tmp = self.tb.split("\n")
                res = tmp[:1] + [s.rstrip("\n") for s in self.stack] + tmp[1:]
                return "\n".join(res)


class WrapSuccessfulIndexingException(WrapIndexingException):
        """This exception is used to wrap an indexing exception during install,
        uninstall, or update which was recovered from by performing a full
        reindex."""
        pass


# Query Parsing Exceptions
class BooleanQueryException(ApiException):
        """This exception is used when the children of a boolean operation
        have different return types.  The command 'pkg search foo AND <bar>'
        is the simplest example of this."""

        def __init__(self, e):
                ApiException.__init__(self)
                self.e = e

        def __str__(self):
                return str(self.e)


class ParseError(ApiException):
        def __init__(self, e):
                ApiException.__init__(self)
                self.e = e

        def __str__(self):
                return str(self.e)


class NonLeafPackageException(ApiException):
        """Removal of a package which satisfies dependencies has been attempted.

        The first argument to the constructor is the FMRI which we tried to
        remove, and is available as the "fmri" member of the exception.  The
        second argument is the list of dependent packages that prevent the
        removal of the package, and is available as the "dependents" member.
        """

        def __init__(self, *args):
                ApiException.__init__(self, *args)

                self.fmri = args[0]
                self.dependents = args[1]

def _str_autofix(self):

        if getattr(self, "_autofix_pkgs", []):
                s = _("\nThis is happening because the following "
                    "packages needed to be repaired as\npart of this "
                    "operation:\n\n    ")
                s += "\n    ".join(str(f) for f in self._autofix_pkgs)
                s += _("\n\nYou will need to reestablish your access to the "
                        "repository or remove the\npackages in the list above.")
                return s
        return ""

class InvalidDepotResponseException(ApiException):
        """Raised when the depot doesn't have versions of operations
        that the client needs to operate successfully."""
        def __init__(self, url, data):
                ApiException.__init__(self)
                self.url = url
                self.data = data

        def __str__(self):
                s = _("Unable to contact valid package repository")
                if self.url:
                        s += _(": %s") % self.url
                if self.data:
                        s += ("\nEncountered the following error(s):\n%s") % \
                            self.data

                s += _str_autofix(self)

                return s

class DataError(ApiException):
        """Base exception class used for all data related errors."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs


class InvalidP5IFile(DataError):
        """Used to indicate that the specified location does not contain a
        valid p5i-formatted file."""

        def __str__(self):
                if self.data:
                        return _("The provided p5i data is in an unrecognized "
                            "format or does not contain valid publisher "
                            "information: %s") % self.data
                return _("The provided p5i data is in an unrecognized format "
                    "or does not contain valid publisher information.")


class InvalidP5SFile(DataError):
        """Used to indicate that the specified location does not contain a
        valid p5i-formatted file."""

        def __str__(self):
                if self.data:
                        return _("The provided p5s data is in an unrecognized "
                            "format or does not contain valid publisher "
                            "information: %s") % self.data
                return _("The provided p5s data is in an unrecognized format "
                    "or does not contain valid publisher information.")


class UnsupportedP5IFile(DataError):
        """Used to indicate that an attempt to read an unsupported version
        of pkg(5) info file was attempted."""

        def __str__(self):
                return _("Unsupported pkg(5) publisher information data "
                    "format.")


class UnsupportedP5SFile(DataError):
        """Used to indicate that an attempt to read an unsupported version
        of pkg(5) info file was attempted."""

        def __str__(self):
                return _("Unsupported pkg(5) publisher and image information "
                    "data format.")


class UnsupportedP5SVersion(ApiException):
        """Used to indicate that an attempt to read an unsupported version
        of pkg(5) info file was attempted."""

        def __init__(self, v):
                self.version = v
        
        def __str__(self):
                return _("%s is not a supported version for creating a "
                    "syspub response.") % self.version


class TransportError(ApiException):
        """Abstract exception class for all transport exceptions.
        Specific transport exceptions should be implemented in the
        transport code.  Callers wishing to catch transport exceptions
        should use this class.  Subclasses must implement all methods
        defined here that raise NotImplementedError."""

        def __str__(self):
                raise NotImplementedError()

        def _str_autofix(self):
                return _str_autofix(self)


class RetrievalError(ApiException):
        """Used to indicate that a a requested resource could not be
        retrieved."""

        def __init__(self, data, location=None):
                ApiException.__init__(self)
                self.data = data
                self.location = location

        def __str__(self):
                if self.location:
                        return _("Error encountered while retrieving data from "
                            "'%s':\n%s") % (self.location, self.data)
                return _("Error encountered while retrieving data from: %s") % \
                    self.data


class InvalidResourceLocation(ApiException):
        """Used to indicate that an invalid transport location was provided."""

        def __init__(self, data):
                ApiException.__init__(self)
                self.data = data

        def __str__(self):
                return _("'%s' is not a valid location.") % self.data

class BEException(ApiException):
        def __init__(self):
                ApiException.__init__(self)

class InvalidBENameException(BEException):
        def __init__(self, be_name):
                BEException.__init__(self)
                self.be_name = be_name

        def __str__(self):
                return _("'%s' is not a valid boot environment name.") % \
                    self.be_name

class DuplicateBEName(BEException):
        """Used to indicate that there is an existing boot environment
        with this name"""

        def __init__(self, be_name):
                BEException.__init__(self)
                self.be_name = be_name

        def __str__(self):
                return _("The boot environment '%s' already exists.") % \
                    self.be_name

class BENamingNotSupported(BEException):
        def __init__(self, be_name):
                BEException.__init__(self)
                self.be_name = be_name

        def __str__(self):
                return _("""\
Boot environment naming during package install is not supported on this
version of OpenSolaris. Please update without the --be-name option.""")

class UnableToCopyBE(BEException):
        def __str__(self):
                return _("Unable to clone the current boot environment.")

class UnableToRenameBE(BEException):
        def __init__(self, orig, dest):
                BEException.__init__(self)
                self.original_name = orig
                self.destination_name = dest

        def __str__(self):
                d = {
                    "orig": self.original_name,
                    "dest": self.destination_name
                }
                return _("""\
A problem occurred while attempting to rename the boot environment
currently named %(orig)s to %(dest)s.""") % d

class UnableToMountBE(BEException):
        def __init__(self, be_name, be_dir):
                BEException.__init__(self)
                self.name = be_name
                self.mountpoint = be_dir

        def __str__(self):
                return _("Unable to mount %(name)s at %(mt)s") % \
                    {"name": self.name, "mt": self.mountpoint}

class BENameGivenOnDeadBE(BEException):
        def __init__(self, be_name):
                BEException.__init__(self)
                self.name = be_name

        def __str__(self):
                return _("""\
Naming a boot environment when operating on a non-live image is
not allowed.""")


class UnrecognizedOptionsToInfo(ApiException):
        def __init__(self, opts):
                ApiException.__init__(self)
                self._opts = opts

        def __str__(self):
                s = _("Info does not recognize the following options:")
                for o in self._opts:
                        s += _(" '") + str(o) + _("'")
                return s

class IncorrectIndexFileHash(ApiException):
        """This is used when the index hash value doesn't match the hash of the
        packages installed in the image."""
        pass


class PublisherError(ApiException):
        """Base exception class for all publisher exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs

        def __str__(self):
                return str(self.data)


class BadPublisherMetaRoot(PublisherError):
        """Used to indicate an operation on the publisher's meta_root failed
        because the meta_root is invalid."""

        def __str__(self):
                return _("Publisher meta_root '%(root)s' is invalid; unable "
                    "to complete operation: '%(op)s'.") % { "root": self.data,
                    "op": self._args.get("operation", None) }


class BadPublisherAlias(PublisherError):
        """Used to indicate that a publisher alias is not valid."""

        def __str__(self):
                return _("'%s' is not a valid publisher alias.") % self.data


class BadPublisherPrefix(PublisherError):
        """Used to indicate that a publisher name is not valid."""

        def __str__(self):
                return _("'%s' is not a valid publisher name.") % self.data


class ReservedPublisherPrefix(PublisherError):
        """Used to indicate that a publisher name is not valid."""

        def __str__(self):
                fmri = self._args["fmri"]
                return _("'%(pkg_pub)s' is a reserved publisher and does not "
                    "contain the requested package: pkg:/%(pkg_name)s") % \
                    {"pkg_pub": fmri.publisher, "pkg_name": fmri.pkg_name}


class BadRepositoryAttributeValue(PublisherError):
        """Used to indicate that the specified repository attribute value is
        invalid."""

        def __str__(self):
                return _("'%(value)s' is not a valid value for repository "
                    "attribute '%(attribute)s'.") % {
                    "value": self._args["value"], "attribute": self.data }


class BadRepositoryCollectionType(PublisherError):
        """Used to indicate that the specified repository collection type is
        invalid."""

        def __init__(self, *args, **kwargs):
                PublisherError.__init__(self, *args, **kwargs)

        def __str__(self):
                return _("'%s' is not a valid repository collection type.") % \
                    self.data


class BadRepositoryURI(PublisherError):
        """Used to indicate that a repository URI is not syntactically valid."""

        def __str__(self):
                return _("'%s' is not a valid URI.") % self.data


class BadRepositoryURIPriority(PublisherError):
        """Used to indicate that the priority specified for a repository URI is
        not valid."""

        def __str__(self):
                return _("'%s' is not a valid URI priority; integer value "
                    "expected.") % self.data


class BadRepositoryURISortPolicy(PublisherError):
        """Used to indicate that the specified repository URI sort policy is
        invalid."""

        def __init__(self, *args, **kwargs):
                PublisherError.__init__(self, *args, **kwargs)

        def __str__(self):
                return _("'%s' is not a valid repository URI sort policy.") % \
                    self.data


class DisabledPublisher(PublisherError):
        """Used to indicate that an attempt to use a disabled publisher occurred
        during an operation."""

        def __str__(self):
                return _("Publisher '%s' is disabled and cannot be used for "
                    "packaging operations.") % self.data


class DuplicatePublisher(PublisherError):
        """Used to indicate that a publisher with the same name or alias already
        exists for an image."""

        def __str__(self):
                return _("A publisher with the same name or alias as '%s' "
                    "already exists.") % self.data


class DuplicateRepository(PublisherError):
        """Used to indicate that a repository with the same origin uris
        already exists for a publisher."""

        def __str__(self):
                return _("A repository with the same name or origin URIs "
                   "already exists for publisher '%s'.") % self.data


class DuplicateRepositoryMirror(PublisherError):
        """Used to indicate that a repository URI is already in use by another
        repository mirror."""

        def __str__(self):
                return _("Mirror '%s' already exists for the specified "
                    "publisher.") % self.data


class DuplicateRepositoryOrigin(PublisherError):
        """Used to indicate that a repository URI is already in use by another
        repository origin."""

        def __str__(self):
                return _("Origin '%s' already exists for the specified "
                    "publisher.") % self.data


class NoPublisherRepositories(TransportError):
        """Used to indicate that a Publisher has no repository information
        configured and so transport operations cannot be performed."""

        def __init__(self, prefix):
                TransportError.__init__(self)
                self.publisher = prefix

        def __str__(self):
                return _("Unable to retrieve requested package data for "
                    "publisher %s; no repositories are currently configured "
                    "for use with this publisher.") % self.publisher


class MoveRelativeToSelf(PublisherError):
        """Used to indicate an attempt to search a repo before or after itself"""

        def __str__(self):
                return _("Cannot search a repository before or after itself")


class MoveRelativeToUnknown(PublisherError):
        """Used to indicate an attempt to order a publisher relative to an
        unknown publisher."""

        def __init__(self, unknown_pub):
                self.__unknown_pub = unknown_pub

        def __str__(self):
                return _("%s is an unknown publisher; no other publishers can "
                    "be ordered relative to it.") % self.__unknown_pub


class SelectedRepositoryRemoval(PublisherError):
        """Used to indicate that an attempt to remove the selected repository
        for a publisher was made."""

        def __str__(self):
                return _("Cannot remove the selected repository for a "
                    "publisher.")


class UnknownLegalURI(PublisherError):
        """Used to indicate that no matching legal URI could be found using the
        provided criteria."""

        def __str__(self):
                return _("Unknown legal URI '%s'.") % self.data


class UnknownPublisher(PublisherError):
        """Used to indicate that no matching publisher could be found using the
        provided criteria."""

        def __str__(self):
                return _("Unknown publisher '%s'.") % self.data


class UnknownRepositoryPublishers(PublisherError):
        """Used to indicate that one or more publisher prefixes are unknown by
        the specified repository."""

        def __init__(self, known=EmptyI, unknown=EmptyI, location=None,
            origins=EmptyI):
                ApiException.__init__(self)
                self.known = known
                self.location = location
                self.origins = origins
                self.unknown = unknown

        def __str__(self):
                if self.location:
                        return _("The repository at %(location)s does not "
                            "contain package data for %(unknown)s; only "
                            "%(known)s.\n\nThis is either because the "
                            "repository location is not valid, or because the "
                            "provided publisher does not match those known by "
                            "the repository.") % {
                            "unknown": ", ".join(self.unknown),
                            "location": self.location,
                            "known": ", ".join(self.known) }
                if self.origins:
                        return _("One or more of the repository origin(s) "
                            "listed below contains package data for "
                            "%(known)s; not %(unknown)s:\n\n%(origins)s\n\n"
                            "This is either because one of the repository "
                            "origins is not valid for this publisher, or "
                            "because the list of known publishers retrieved "
                            "from the repository origin does not match the "
                            "client.") % { "unknown": ", ".join(self.unknown),
                            "known": ", ".join(self.known),
                            "origins": "\n".join(str(o) for o in self.origins) }
                return _("The specified publisher repository does not "
                    "contain any package data for %(unknown)s; only "
                    "%(known)s.") % { "unknown": ", ".join(self.unknown),
                    "known": ", ".join(self.known) }


class UnknownRelatedURI(PublisherError):
        """Used to indicate that no matching related URI could be found using
        the provided criteria."""

        def __str__(self):
                return _("Unknown related URI '%s'.") % self.data


class UnknownRepository(PublisherError):
        """Used to indicate that no matching repository could be found using the
        provided criteria."""

        def __str__(self):
                return _("Unknown repository '%s'.") % self.data


class UnknownRepositoryMirror(PublisherError):
        """Used to indicate that a repository URI could not be found in the
        list of repository mirrors."""

        def __str__(self):
                return _("Unknown repository mirror '%s'.") % self.data

class UnsupportedRepositoryOperation(TransportError):
        """The publisher has no active repositories that support the
        requested operation."""

        def __init__(self, pub, operation):
                ApiException.__init__(self)
                self.data = None
                self.kwargs = None
                self.pub = pub
                self.op = operation

        def __str__(self):
                return _("Publisher '%(pub)s' has no repositories that support "
                    "the '%(op)s' operation.") % self.__dict__


class RepoPubConfigUnavailable(PublisherError):
        """Used to indicate that the specified repository does not provide
        publisher configuration information."""

        def __init__(self, location=None, pub=None):
                ApiException.__init__(self)
                self.location = location
                self.pub = pub

        def __str__(self):
                if not self.location and not self.pub:
                        return _("The specified package repository does not "
                            "provide publisher configuration information.")
                if self.location:
                        return _("The package repository at %s does not "
                            "provide publisher configuration information or "
                            "the information provided is incomplete.") % \
                            self.location
                return _("One of the package repository origins for %s does "
                    "not provide publisher configuration information or the "
                    "information provided is incomplete.") % self.pub


class UnknownRepositoryOrigin(PublisherError):
        """Used to indicate that a repository URI could not be found in the
        list of repository origins."""

        def __str__(self):
                return _("Unknown repository origin '%s'") % self.data


class UnsupportedRepositoryURI(PublisherError):
        """Used to indicate that the specified repository URI uses an
        unsupported scheme."""

        def __str__(self):
                if self.data:
                        scheme = urlparse.urlsplit(self.data,
                            allow_fragments=0)[0]
                        return _("The URI '%(uri)s' uses the unsupported "
                            "scheme '%(scheme)s'.  Supported schemes are "
                            "file://, http://, and https://.") % {
                            "uri": self.data, "scheme": scheme }
                return _("The specified URI uses an unsupported scheme."
                    "  Supported schemes are: file://, http://, and https://.")


class UnsupportedRepositoryURIAttribute(PublisherError):
        """Used to indicate that the specified repository URI attribute is not
        supported for the URI's scheme."""

        def __str__(self):
                return _("'%(attr)s' is not supported for '%(scheme)s'.") % {
                    "attr": self.data, "scheme": self._args["scheme"] }


class UnknownSysrepoConfiguration(ApiException):
        """Used when a pkg client needs to communicate with the system
        repository but can't find the configuration for it."""

        def __str__(self):
                return _("""\
pkg is configured to use the system repository (via the use-system-repo
property) but it could not get the host and port from
svc:/application/pkg/zones-proxy-client nor svc:/application/pkg/system-repository, and
the PKG_SYSREPO_URL environment variable was not set.  Please try enabling one
of those services or setting the PKG_SYSREPO_URL environment variable.
""")


class ModifyingSyspubException(ApiException):
        """This exception is raised when a user attempts to modify a system
        publisher."""

        def __init__(self, s):
                self.s = s

        def __str__(self):
                return self.s


class SigningException(ApiException):
        """The base class for exceptions related to manifest signing."""

        def __init__(self, pfmri=None, sig=None):
                self.pfmri = pfmri
                self.sig = sig

        # This string method is used by subclasses to fill in the details
        # about the package and signature involved.
        def __str__(self):
                if self.pfmri:
                        if self.sig:
                                return _("The relevant signature action is "
                                    "found in %(pfmri)s and has a hash of "
                                    "%(hsh)s") % \
                                    {"pfmri": self.pfmri, "hsh": self.sig.hash}
                        return _("The package involved is:%s") % self.pfmri
                if self.sig:
                        return _("The relevant signature action's value "
                            "attribute is %s") % self.sig.attrs["value"]
                return ""


class BadFileFormat(SigningException):
        """Exception used when a key, certificate or CRL file is not in a
        recognized format."""

        def __init__(self, txt):
                self.txt = txt

        def __str__(self):
                return self.txt


class UnsupportedSignatureVersion(SigningException):
        """Exception used when a signature reports a version which this version
        of pkg(5) doesn't support."""

        def __init__(self, version, *args, **kwargs):
                SigningException.__init__(self, *args, **kwargs)
                self.version = version

        def __str__(self):
                return _("The signature action %(act)s was made using a "
                    "version (%(ver)s) this version of pkg(5) doesn't "
                    "understand.") % {"act":self.sig, "ver":self.version}


class CertificateException(SigningException):
        """Base class for exceptions encountered while establishing the chain
        of trust."""

        def __init__(self, cert, pfmri=None):
                SigningException.__init__(self, pfmri)
                self.cert = cert


class ModifiedCertificateException(CertificateException):
        """Exception used when a certificate does not match its expected hash
        value."""

        def __init__(self, cert, path, pfmri=None):
                CertificateException.__init__(self, cert, pfmri)
                self.path = path

        def __str__(self):
                return _("Certificate %s has been modified on disk. Its hash "
                    "value is not what was expected.") % self.path


class UntrustedSelfSignedCert(CertificateException):
        """Exception used when a chain of trust is rooted in an untrusted
        self-signed certificate."""

        def __str__(self):
                return _("Chain was rooted in an untrusted self-signed "
                    "certificate.\n") + CertificateException.__str__(self)


class BrokenChain(CertificateException):
        """Exception used when a chain of trust can not be established between
        the leaf certificate and a trust anchor."""

        def __init__(self, cert, cert_exceptions, *args, **kwargs):
                CertificateException.__init__(self, cert, *args, **kwargs)
                self.ext_exs = cert_exceptions

        def __str__(self):
                s = ""
                if self.ext_exs:
                        s = _("The following problems were encountered:\n") + \
                        "\n".join([str(e) for e in self.ext_exs])
                return _("The certificate which issued this "
                    "certificate:%(subj)s could not be found. The issuer "
                    "is:%(issuer)s\n") % {"subj":self.cert.get_subject(),
                    "issuer":self.cert.get_issuer()} + s + \
                    CertificateException.__str__(self)


class RevokedCertificate(CertificateException):
        """Exception used when a chain of trust contains a revoked certificate.
        """

        def __init__(self, cert, reason, *args, **kwargs):
                CertificateException.__init__(self, cert, *args, **kwargs)
                self.reason = reason

        def __str__(self):
                return _("This certificate was revoked:%(cert)s for this "
                    "reason:\n%(reason)s") % {"cert":self.cert.get_subject(),
                    "reason":self.reason} + CertificateException.__str__(self)


class UnverifiedSignature(SigningException):
        """Exception used when a signature could not be verified by the
        expected certificate."""

        def __init__(self, sig, reason, pfmri=None):
                SigningException.__init__(self, pfmri)
                self.sig = sig
                self.reason = reason

        def __str__(self):
                if self.pfmri:
                        return _("A signature in %(pfmri)s could not be "
                            "verified for "
                            "this reason:\n%(reason)s\nThe signature's hash is "
                            "%(hash)s") % {"pfmri": self.pfmri,
                            "reason": self.reason,
                            "hash": self.sig.hash}
                return _("The signature with this signature value:\n"
                    "%(sigval)s\n could not be verified for this reason:\n"
                    "%(reason)s\n") % {"reason": self.reason,
                    "sigval": self.sig.attrs["value"]}


class RequiredSignaturePolicyException(SigningException):
        """Exception used when signatures were required but none were found."""

        def __init__(self, pub, pfmri=None):
                SigningException.__init__(self, pfmri)
                self.pub = pub

        def __str__(self):
                pub_str = self.pub.prefix
                if self.pfmri:
                        return _("The policy for %(pub_str)s requires "
                            "signatures to be present but no signature was "
                            "found in %(fmri_str)s.") % \
                            {"pub_str": pub_str, "fmri_str": self.pfmri}
                return _("The policy for %(pub_str)s requires signatures to be "
                    "present but no signature was found.") % {
                    "pub_str": pub_str}


class MissingRequiredNamesException(SigningException):
        """Exception used when a signature policy required names to be seen
        which weren't seen."""

        def __init__(self, pub, missing_names, pfmri=None):
                SigningException.__init__(self, pfmri)
                self.pub = pub
                self.missing_names = missing_names

        def __str__(self):
                pub_str = self.pub.prefix
                if self.pfmri:
                        return _("The policy for %(pub_str)s requires certain "
                            "CNs to be seen in a chain of trust. The following "
                            "required names couldn't be found for this "
                            "package:%(fmri_str)s.\n%(missing)s") % \
                            {"pub_str": pub_str, "fmri_str": self.pfmri,
                            "missing": "\n".join(self.missing_names)}
                return _("The policy for %(pub_str)s requires certain CNs to "
                    "be seen in a chain of trust. The following required names "
                    "couldn't be found.\n%(missing)s") % {"pub_str": pub_str,
                    "missing": "\n".join(self.missing_names)}

class UnsupportedCriticalExtension(SigningException):
        """Exception used when a certificate in the chain of trust uses a
        critical extension pkg5 doesn't understand."""

        def __init__(self, cert, ext):
                SigningException.__init__(self)
                self.cert = cert
                self.ext = ext

        def __str__(self):
                return _("The certificate whose subject is %(cert)s could not "
                    "be verified "
                    "because it uses a critical extension that pkg5 cannot "
                    "handle yet.\nExtension name:%(name)s\nExtension "
                    "value:%(val)s") % {"cert": self.cert.get_subject(),
                    "name":self.ext.get_name(), "val":self.ext.get_value()}

class UnsupportedExtensionValue(SigningException):
        """Exception used when a certificate in the chain of trust has an
        extension with a value pkg5 doesn't understand."""

        def __init__(self, cert, ext, bad_val=None):
                SigningException.__init__(self)
                self.cert = cert
                self.ext = ext
                self.bad_val = bad_val

        def __str__(self):
                s = _("The certificate whose subject is %(cert)s could not be "
                    "verified because it has an extension with a value that "
                    "pkg(5) does not understand."
                    "\nExtension name:%(name)s\nExtension value:%(val)s") % \
                    {"cert": self.cert.get_subject(),
                    "name":self.ext.get_name(), "val":self.ext.get_value()}
                if self.bad_val:
                        s += _("\nProblematic Value:%s") % (self.bad_val,)
                return s

class InappropriateCertificateUse(SigningException):
        """Exception used when a certificate in the chain of trust has been used
        inappropriately.  An example would be a certificate which was only
        supposed to be used to sign code being used to sign other certificates.
        """

        def __init__(self, cert, ext, use):
                SigningException.__init__(self)
                self.cert = cert
                self.ext = ext
                self.use = use

        def __str__(self):
                return _("The certificate whose subject is %(cert)s could not "
                    "be verified because it has been used inappropriately.  "
                    "The way it is used means that the value for extension "
                    "%(name)s must include '%(use)s' but the value was "
                    "'%(val)s'.") % {"cert": self.cert.get_subject(),
                    "use": self.use, "name":self.ext.get_name(),
                    "val":self.ext.get_value()}

class PathlenTooShort(InappropriateCertificateUse):
        """Exception used when a certificate in the chain of trust has been used
        inappropriately.  An example would be a certificate which was only
        supposed to be used to sign code being used to sign other certificates.
        """

        def __init__(self, cert, actual_length, cert_length):
                SigningException.__init__(self)
                self.cert = cert
                self.al = actual_length
                self.cl = cert_length

        def __str__(self):
                return _("The certificate whose subject is %(cert)s could not "
                    "be verified because it has been used inappropriately.  "
                    "There can only be %(cl)s certificates between this "
                    "certificate and the leaf certificate.  There are %(al)s "
                    "certificates between this certificate and the leaf in "
                    "this chain.") % {
                        "cert": self.cert.get_subject(),
                        "al": self.al,
                        "cl": self.cl
                    }


class AlmostIdentical(ApiException):
        """Exception used when a package already has a signature action which is
        nearly identical to the one being added but differs on some
        attributes."""

        def __init__(self, hsh, algorithm, version, pkg=None):
                self.hsh = hsh
                self.algorithm = algorithm
                self.version = version
                self.pkg = pkg

        def __str__(self):
                s = _("The signature to be added to the package has the same "
                    "hash (%(hash)s), algorithm (%(algorithm)s), and "
                    "version (%(version)s) as an existing signature, but "
                    "doesn't match the signature exactly.  For this signature "
                    "to be added, the existing signature must be removed.") % {
                        "hash": self.hsh,
                        "algorithm": self.algorithm,
                        "version": self.version
                    }
                if self.pkg:
                        s += _("The package being signed was %(pkg)s") % \
                            {"pkg": self.pkg}
                return s


class DuplicateSignaturesAlreadyExist(ApiException):
        """Exception used when a package already has a signature action which is
        nearly identical to the one being added but differs on some
        attributes."""

        def __init__(self, pfmri):
                self.pfmri = pfmri

        def __str__(self):
                return _("%s could not be signed because it already has two "
                    "copies of this signature in it.  One of those signature "
                    "actions must be removed before the package is given to "
                    "users.") % self.pfmri


class InvalidPropertyValue(ApiException):
        """Exception used when a property was set to an invalid value."""

        def __init__(self, s):
                ApiException.__init__(self)
                self.str = s

        def __str__(self):
                return self.str


class CertificateError(ApiException):
        """Base exception class for all certificate exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs

        def __str__(self):
                return str(self.data)


class ExpiredCertificate(CertificateError):
        """Used to indicate that a certificate has expired."""

        def __str__(self):
                publisher = self._args.get("publisher", None)
                uri = self._args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s' needed to access '%(uri)s', "
                                    "has expired.  Please install a valid "
                                    "certificate.") % { "cert": self.data,
                                    "pub": publisher, "uri": uri }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s', has expired.  Please install a valid "
                            "certificate.") % { "cert": self.data,
                            "pub": publisher }
                if uri:
                        return _("Certificate '%(cert)s', needed to access "
                            "'%(uri)s', has expired.  Please install a valid "
                            "certificate.") % { "cert": self.data, "uri": uri }
                return _("Certificate '%s' has expired.  Please install a "
                    "valid certificate.") % self.data


class ExpiringCertificate(CertificateError):
        """Used to indicate that a certificate has expired."""

        def __str__(self):
                publisher = self._args.get("publisher", None)
                uri = self._args.get("uri", None)
                days = self._args.get("days", 0)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s', needed to access '%(uri)s', "
                                    "will expire in '%(days)s' days.") % {
                                    "cert": self.data, "pub": publisher,
                                    "uri": uri, "days": days }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s' will expire in '%(days)s' days.") % {
                            "cert": self.data, "pub": publisher, "days": days }
                if uri:
                        return _("Certificate '%(cert)s', needed to access "
                            "'%(uri)s', will expire in '%(days)s' days.") % {
                            "cert": self.data, "uri": uri, "days": days }
                return _("Certificate '%(cert)s' will expire in "
                    "'%(days)s' days.") % { "cert": self.data, "days": days }


class InvalidCertificate(CertificateError):
        """Used to indicate that a certificate is invalid."""

        def __str__(self):
                publisher = self._args.get("publisher", None)
                uri = self._args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s', needed to access '%(uri)s', is "
                                    "invalid.") % { "cert": self.data,
                                    "pub": publisher, "uri": uri }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s' is invalid.") % { "cert": self.data,
                            "pub": publisher }
                if uri:
                        return _("Certificate '%(cert)s' needed to access "
                            "'%(uri)s' is invalid.") % { "cert": self.data,
                            "uri": uri }
                return _("Invalid certificate '%s'.") % self.data


class NoSuchKey(CertificateError):
        """Used to indicate that a key could not be found."""

        def __str__(self):
                publisher = self._args.get("publisher", None)
                uri = self._args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Unable to locate key '%(key)s' for "
                                    "publisher '%(pub)s' needed to access "
                                    "'%(uri)s'.") % { "key": self.data,
                                    "pub": publisher, "uri": uri }
                        return _("Unable to locate key '%(key)s' for publisher "
                            "'%(pub)s'.") % { "key": self.data, "pub": publisher
                            }
                if uri:
                        return _("Unable to locate key '%(key)s' needed to "
                            "access '%(uri)s'.") % { "key": self.data,
                            "uri": uri }
                return _("Unable to locate key '%s'.") % self.data


class NoSuchCertificate(CertificateError):
        """Used to indicate that a certificate could not be found."""

        def __str__(self):
                publisher = self._args.get("publisher", None)
                uri = self._args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Unable to locate certificate "
                                    "'%(cert)s' for publisher '%(pub)s' needed "
                                    "to access '%(uri)s'.") % {
                                    "cert": self.data, "pub": publisher,
                                    "uri": uri }
                        return _("Unable to locate certificate '%(cert)s' for "
                            "publisher '%(pub)s'.") % { "cert": self.data,
                            "pub": publisher }
                if uri:
                        return _("Unable to locate certificate '%(cert)s' "
                            "needed to access '%(uri)s'.") % {
                            "cert": self.data, "uri": uri }
                return _("Unable to locate certificate '%s'.") % self.data


class NotYetValidCertificate(CertificateError):
        """Used to indicate that a certificate is not yet valid (future
        effective date)."""

        def __str__(self):
                publisher = self._args.get("publisher", None)
                uri = self._args.get("uri", None)
                if publisher:
                        if uri:
                                return _("Certificate '%(cert)s' for publisher "
                                    "'%(pub)s', needed to access '%(uri)s', "
                                    "has a future effective date.") % {
                                    "cert": self.data, "pub": publisher,
                                    "uri": uri }
                        return _("Certificate '%(cert)s' for publisher "
                            "'%(pub)s' has a future effective date.") % {
                            "cert": self.data, "pub": publisher }
                if uri:
                        return _("Certificate '%(cert)s' needed to access "
                            "'%(uri)s' has a future effective date.") % {
                            "cert": self.data, "uri": uri }
                return _("Certificate '%s' has a future effective date.") % \
                    self.data


class ServerReturnError(ApiException):
        """This exception is used when the server returns a line which the
        client cannot parse correctly."""

        def __init__(self, line):
                ApiException.__init__(self)
                self.line = line

        def __str__(self):
                return _("Gave a bad response:%s") % self.line


class MissingFileArgumentException(ApiException):
        """This exception is used when a file was given as an argument but
        no such file could be found."""
        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                return _("Could not find %s") % self.path


class ManifestError(ApiException):
        """Base exception class for all manifest exceptions."""

        def __init__(self, *args, **kwargs):
                ApiException.__init__(self, *args, **kwargs)
                if args:
                        self.data = args[0]
                else:
                        self.data = None
                self._args = kwargs

        def __str__(self):
                return str(self.data)


class BadManifestSignatures(ManifestError):
        """Used to indicate that the Manifest signatures are not valid."""

        def __str__(self):
                if self.data:
                        return _("The signature data for the manifest of the "
                            "'%s' package is not valid.") % self.data
                return _("The signature data for the manifest is not valid.")


class UnknownErrors(ApiException):
        """Used to indicate that one or more exceptions were encountered.
        This is intended for use with where multiple exceptions for multiple
        files are encountered and the errors have been condensed into a
        single exception and re-raised.  One example case would be rmtree()
        with shutil.Error."""

        def __init__(self, msg):
                ApiException.__init__(self)
                self.__msg = msg

        def __str__(self):
                return self.__msg


# Image creation exceptions
class ImageCreationException(ApiException):
        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                raise NotImplementedError()


class ImageAlreadyExists(ImageCreationException):
        def __str__(self):
                return _("there is already an image at: %s.\nTo override, use "
                    "the -f (force) option.") % self.path


class ImageCfgEmptyError(ApiException):
        """Used to indicate that the image configuration is invalid."""

        def __str__(self):
                return _("The configuration data for the image rooted at "
                    "%s is empty or missing.") % self.data


class UnsupportedImageError(ApiException):
        """Used to indicate that the image at a specific location is in a format
        not supported by this version of the pkg(5) API."""

        def __init__(self, path):
                ApiException.__init__(self)
                self.path = path

        def __str__(self):
                return _("The image rooted at %s is invalid or is not "
                    "supported by this version of the packaging system.") % \
                    self.path


class CreatingImageInNonEmptyDir(ImageCreationException):
        def __str__(self):
                return _("the specified image path is not empty: %s.\nTo "
                    "override, use the -f (force) option.") % self.path


def _convert_error(e, ignored_errors=EmptyI):
        """Converts the provided exception into an ApiException equivalent if
        possible.  Returns a new exception object if converted or the original
        if not.

        'ignored_errors' is an optional list of errno values for which None
        should be returned.
        """

        if not hasattr(e, "errno"):
                return e
        if e.errno in ignored_errors:
                return None
        if e.errno in (errno.EACCES, errno.EPERM):
                return PermissionsException(e.filename)
        if e.errno == errno.EROFS:
                return ReadOnlyFileSystemException(e.filename)
        return e

class LinkedImageException(ApiException):

        def __init__(self, bundle=None, lin=None, exitrv=None,
            attach_bad_prop=None,
            attach_bad_prop_value=None,
            attach_child_notsup=None,
            attach_parent_notsup=None,
            attach_root_as_child=None,
            child_bad_img=None,
            child_diverged=None,
            child_dup=None,
            child_nested=None,
            child_not_in_altroot=None,
            child_not_nested=None,
            child_path_eaccess=None,
            child_path_notabs=None,
            child_unknown=None,
            cmd_failed=None,
            detach_child_notsup=None,
            detach_from_parent=None,
            detach_parent_notsup=None,
            img_linked=None,
            lin_malformed=False,
            link_to_self=False,
            parent_bad_img=None,
            parent_bad_notabs=None,
            parent_bad_path=None,
            parent_not_in_altroot=None,
            pkg_op_failed=None,
            self_linked=None,
            self_not_child=None):

                self.attach_bad_prop = attach_bad_prop
                self.attach_bad_prop_value = attach_bad_prop_value
                self.attach_child_notsup = attach_child_notsup
                self.attach_parent_notsup = attach_parent_notsup
                self.attach_root_as_child = attach_root_as_child
                self.child_bad_img = child_bad_img
                self.child_diverged = child_diverged
                self.child_dup = child_dup
                self.child_nested = child_nested
                self.child_not_in_altroot = child_not_in_altroot
                self.child_not_nested = child_not_nested
                self.child_path_eaccess = child_path_eaccess
                self.child_path_notabs = child_path_notabs
                self.child_unknown = child_unknown
                self.cmd_failed = cmd_failed
                self.detach_child_notsup = detach_child_notsup
                self.detach_from_parent = detach_from_parent
                self.detach_parent_notsup = detach_parent_notsup
                self.img_linked = img_linked
                self.lin_malformed = lin_malformed
                self.link_to_self = link_to_self
                self.parent_bad_img = parent_bad_img
                self.parent_bad_notabs = parent_bad_notabs
                self.parent_bad_path = parent_bad_path
                self.parent_not_in_altroot = parent_not_in_altroot
                self.pkg_op_failed = pkg_op_failed
                self.self_linked = self_linked
                self.self_not_child = self_not_child

                # first deal with an error bundle
                if bundle:
                        assert type(bundle) in [tuple, list, set]
                        for e in bundle:
                                assert isinstance(e, LinkedImageException)

                        # set default error return value
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_OOPS

                        self.lix_err = None
                        self.lix_bundle = bundle
                        self.lix_exitrv = exitrv
                        return

                err = None

                if attach_bad_prop:
                        err = _("Invalid linked image attach property: %s") % \
                            attach_bad_prop

                if attach_bad_prop_value:
                        assert type(attach_bad_prop_value) in [tuple, list]
                        assert len(attach_bad_prop_value) == 2
                        err =  _("Invalid linked image attach property "
                            "value: %s") % "=".join(attach_bad_prop_value)

                if attach_child_notsup:
                        err = _("Linked image type does not support child "
                            "attach: %s") % attach_child_notsup

                if attach_parent_notsup:
                        err = _("Linked image type does not support parent "
                            "attach: %s") % attach_parent_notsup

                if attach_root_as_child:
                        err = _("Cannot attach root image as child")

                if child_bad_img:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_EACCESS
                        if lin:
                                err = _("Can't initialize child image "
                                    "(%(lin)s) at path: %(path)s") % {
                                        "lin": lin,
                                        "path": child_bad_img
                                    }
                        else:
                                err = _("Can't initialize child image "
                                    "at path: %s") % child_bad_img

                if child_diverged:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_DIVERGED
                        err = _("Linked image is diverged: %s") % \
                            child_diverged

                if child_dup:
                        err = _("A linked child image with this name "
                            "already exists: %s") % child_dup

                if child_nested:
                        cpath, ipath = child_nested
                        err = _("Child image '%(cpath)s' is nested "
                            "within another image: '%(ipath)s'") % {
                                "cpath": cpath,
                                "ipath": ipath,
                            }

                if child_not_in_altroot:
                        path, altroot = child_not_in_altroot
                        err = _("Child image '%(path)s' is not located "
                           "within the parent's altroot '%(altroot)s'") % {
                                "path": path,
                                "altroot": altroot
                            }

                if child_not_nested:
                        cpath, ppath = child_not_nested
                        err = _("Child image '%(cpath)s' is not nested "
                            "within the parent image '%(ppath)s'") % {
                                "cpath": cpath,
                                "ppath": ppath,
                            }

                if child_path_eaccess:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_EACCESS
                        if lin:
                                err = _("Can't access child image "
                                    "(%(lin)s) at path: %(path)s") % {
                                        "lin": lin,
                                        "path": child_path_eaccess
                                    }
                        else:
                                err = _("Can't access child image "
                                    "at path: %s") % child_path_eaccess

                if child_path_notabs:
                        err = _("Child path not absolute: %s") % \
                            child_path_notabs

                if child_unknown:
                        err = _("Unknown child linked image: %s") % \
                            child_unknown

                if cmd_failed:
                        (rv, cmd, errout) = cmd_failed
                        err = _("The following subprocess returned an "
                            "unexpected exit code of %(rv)d:\n    %(cmd)s") % \
                            {"rv": rv, "cmd": cmd}
                        if not errout:
                                return
                        err += _("\nAnd generated the following error "
                            "message:\n%(errout)s" % {"errout": errout})

                if detach_child_notsup:
                        err = _("Linked image type does not support "
                            "child detach: %s") % detach_child_notsup

                if detach_from_parent:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_PARENTOP
                        err =  _("Parent linked to child, can not detach "
                            "child: %s") % detach_from_parent

                if detach_parent_notsup:
                        err = _("Linked image type does not support "
                            "parent detach: %s") % detach_parent_notsup

                if img_linked:
                        err = _("Image already a linked child: %s") % \
                            img_linked

                if lin_malformed:
                        err = _("Invalid linked image name: %s") % \
                            lin_malformed

                if link_to_self:
                        err = _("Can't link image to itself.")

                if parent_bad_img:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_EACCESS
                        err = _("Can't initialize parent image at path: %s") % \
                            parent_bad_img

                if parent_bad_notabs:
                        err = _("Parent path not absolute: %s") % \
                            parent_bad_notabs

                if parent_bad_path:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_EACCESS
                        err = _("Can't access parent image at path: %s") % \
                            parent_bad_path

                if parent_not_in_altroot:
                        path, altroot = parent_not_in_altroot
                        err = _("Parent image '%(path)s' is not located "
                            "within the child's altroot '%(altroot)s'") % {
                                "path": path,
                                "altroot": altroot
                            }

                if pkg_op_failed:
                        assert lin
                        assert len(pkg_op_failed) == 3
                        op = pkg_op_failed[0]
                        exitrv = pkg_op_failed[1]
                        errout = pkg_op_failed[2]

                        err = _("""
A '%(op)s' operation failed for child '%(lin)s' with an unexpected
return value of %(exitrv)d and the following error message:
%(errout)s

"""
                        ) % {
                            "lin": lin,
                            "op": op,
                            "exitrv": exitrv,
                            "errout": errout,
                        }

                if self_linked:
                        err = _("Current image already a linked child: %s") % \
                            self_linked

                if self_not_child:
                        if exitrv == None:
                                exitrv = pkgdefs.EXIT_NOPARENT
                        err = _("Current image is not a linked child: %s") % \
                            self_not_child

                # set default error return value
                if exitrv == None:
                        exitrv = pkgdefs.EXIT_OOPS

                self.lix_err = err
                self.lix_bundle = None
                self.lix_exitrv = exitrv

        def __str__(self):
                assert self.lix_err or self.lix_bundle
                assert not (self.lix_err and self.lix_bundle), \
                   "self.lix_err = %s, self.lix_bundle = %s" % \
                   (str(self.lix_err), str(self.lix_bundle))

                # single error
                if self.lix_err:
                        return self.lix_err

                # concatenate multiple errors
                bundle_str = []
                for e in self.lix_bundle:
                        bundle_str.append(str(e))
                return "\n".join(bundle_str)


class FreezePkgsException(ApiException):
        """Used if an argument to pkg freeze isn't valid."""

        def __init__(self, multiversions=None, unmatched_wildcards=None,
            version_mismatch=None, versionless_uninstalled=None):
                ApiException.__init__(self)
                self.multiversions = multiversions
                self.unmatched_wildcards = unmatched_wildcards
                self.version_mismatch = version_mismatch
                self.versionless_uninstalled = versionless_uninstalled

        def __str__(self):
                res = []
                if self.multiversions:
                        s = _("""\
The following packages were frozen at two different versions by
the patterns provided.  The package stem and the versions it was frozen at are
provided:""")
                        res += [s]
                        res += ["\t%s\t%s" % (stem, " ".join([
                            str(v) for v in versions]))
                            for stem, versions in sorted(self.multiversions)]

                if self.unmatched_wildcards:
                        s = _("""\
The following patterns contained wildcards but matched no
installed packages.""")
                        res += [s]
                        res += ["\t%s" % pat for pat in sorted(
                            self.unmatched_wildcards)]

                if self.version_mismatch:
                        s = _("""\
The following patterns attempted to freeze the listed packages
at a version different from the version at which the packages are installed.""")
                        res += [s]
                        for pat in sorted(self.version_mismatch):
                                res += ["\t%s" % pat]
                                if len(self.version_mismatch[pat]) > 1:
                                        res += [
                                            "\t\t%s" % stem
                                            for stem
                                            in self.version_mismatch[pat]
                                        ]

                if self.versionless_uninstalled:
                        s = _("""\
The following patterns don't match installed packages and
contain no version information.  Uninstalled packages can only be frozen by
providing a version at which to freeze them.""")
                        res += [s]
                        res += ["\t%s" % p for p in sorted(
                            self.versionless_uninstalled)]
                return "\n".join(res)

class InvalidFreezeFile(ApiException):
        """Used to indicate the freeze state file could not be loaded."""

        def __str__(self):
                return _("The freeze state file '%s' is invalid.") % self.data

class UnknownFreezeFileVersion(ApiException):
        """Used when the version on the freeze state file isn't the version
        that's expected."""

        def __init__(self, found_ver, expected_ver, location):
                self.found = found_ver
                self.expected = expected_ver
                self.loc = location

        def __str__(self):
                return _("The freeze state file '%(loc)s' was expected to have "
                    "a version of %(exp)s, but its version was %(found)s") % {
                    "exp": self.expected,
                    "found": self.found,
                    "loc": self.loc,
                }

class UnparsableJSON(ApiException):
        """Used when JSON has been asked to parse an unparsable string."""

        def __init__(self, s, e):
                self.unparsable = s
                self.json_exception = e

        def __str__(self):
                return _("Because of this error:\n%(err)s\nJSON could not "
                    "parse the following data:\n%(data)s") % \
                    {"err": str(self.json_exception), "data": self.unparsable}
