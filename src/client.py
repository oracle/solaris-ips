#!/usr/bin/python2.6
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
# Copyright (c) 2007, 2010, Oracle and/or its affiliates. All rights reserved.
#

#
# pkg - package system client utility
#
# The client is going to maintain an on-disk cache of its state, so that
# startup assembly of the graph is reduced.
#
# Client graph is of the entire local catalog.  As operations progress, package
# states will change.
#
# Deduction operation allows the compilation of the local component of the
# catalog, only if an authoritative repository can identify critical files.
#
# Environment variables
#
# PKG_IMAGE - root path of target image
# PKG_IMAGE_TYPE [entire, partial, user] - type of image
#       XXX or is this in the Image configuration?

import calendar
import datetime
import errno
import fnmatch
import getopt
import gettext
import itertools
import locale
import logging
import os
import socket
import sys
import textwrap
import time
import traceback
import warnings

import pkg
import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.bootenv as bootenv
import pkg.client.history as history
import pkg.client.image as image
import pkg.client.progress as progress
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.version as version

from pkg.client import global_settings
from pkg.client.api import IMG_TYPE_ENTIRE, IMG_TYPE_PARTIAL, IMG_TYPE_USER
from pkg.client.debugvalues import DebugValues
from pkg.client.history import (RESULT_CANCELED, RESULT_FAILED_BAD_REQUEST,
    RESULT_FAILED_CONFIGURATION, RESULT_FAILED_LOCKED, RESULT_FAILED_STORAGE,
    RESULT_FAILED_TRANSPORT, RESULT_FAILED_UNKNOWN, RESULT_FAILED_OUTOFMEMORY)
from pkg.misc import EmptyI, msg, PipeError

CLIENT_API_VERSION = 40
PKG_CLIENT_NAME = "pkg"

JUST_UNKNOWN = 0
JUST_LEFT = -1
JUST_RIGHT = 1

# pkg exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2
EXIT_PARTIAL = 3
EXIT_NOP     = 4
EXIT_NOTLIVE = 5
EXIT_LICENSE = 6
EXIT_LOCKED  = 7


logger = global_settings.logger

valid_special_attrs = ["action.hash", "action.key", "action.name", "action.raw"]

valid_special_prefixes = ["action."]

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "%s: %s" % (cmd, text)
                pkg_cmd = "pkg "
        else:
                pkg_cmd = "pkg: "

                # If we get passed something like an Exception, we can convert
                # it down to a string.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        logger.error(ws + pkg_cmd + text_nows)

def usage(usage_error=None, cmd=None, retcode=2, full=False):
        """Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        if usage_error:
                error(usage_error, cmd=cmd)

        if not full:
                # The full usage message isn't desired.
                logger.error(_("Try `pkg --help or -?' for more information."))
                sys.exit(retcode)

        logger.error(_("""\
Usage:
        pkg [options] command [cmd_options] [operands]

Basic subcommands:
        pkg install [-nvq] [--accept] [--licenses] [--no-index] [--no-refresh]
            pkg_fmri_pattern ...
        pkg uninstall [-nrvq] [--no-index] pkg_fmri_pattern ...
        pkg list [-Hafnsuv] [--no-refresh] [pkg_fmri_pattern ...]
        pkg image-update [-fnvq] [--accept] [--be-name name] [--licenses]
            [--no-index] [--no-refresh]
        pkg refresh [--full] [publisher ...]
        pkg version

Advanced subcommands:
        pkg info [-lr] [--license] [pkg_fmri_pattern ...]
        pkg search [-HIaflpr] [-o attribute ...] [-s repo_uri] query
        pkg verify [-Hqv] [pkg_fmri_pattern ...]
        pkg fix [--accept] [--licenses] [pkg_fmri_pattern ...]
        pkg contents [-Hmr] [-a attribute=pattern ...] [-o attribute ...]
            [-s sort_key] [-t action_type ...] [pkg_fmri_pattern ...]
        pkg image-create [-FPUfz] [--force] [--full|--partial|--user] [--zone]
            [-k ssl_key] [-c ssl_cert] [--no-refresh]
            [--variant <variant_spec>=<instance> ...]
            [-g uri|--origin=uri ...] [-m uri|--mirror=uri ...]
            [--facet <facet_spec>=[True|False] ...]
            (-p|--publisher) [<name>=]<repo_uri> dir
        pkg change-variant [-nvq] [--accept] [--be-name name] [--licenses]
            <variant_spec>=<instance> ...
        pkg change-facet [-nvq] [--accept] [--be-name name] [--licenses]
            <facet_spec>=[True|False|None] ...
        pkg variant [-H] [<variant_spec>]
        pkg facet [-H] [<facet_spec>]
        pkg set-property propname propvalue
        pkg unset-property propname ...
        pkg property [-H] [propname ...]

        pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert]
            [-g origin_to_add|--add-origin=origin_to_add ...]
            [-G origin_to_remove|--remove-origin=origin_to_remove ...]
            [-m mirror_to_add|--add-mirror=mirror_to_add ...]
            [-M mirror_to_remove|--remove-mirror=mirror_to_remove ...]
            [-p repo_uri] [--enable] [--disable] [--no-refresh]
            [--reset-uuid] [--non-sticky] [--sticky]
            [--search-after=publisher]
            [--search-before=publisher]
            [publisher]
        pkg unset-publisher publisher ...
        pkg publisher [-HPn] [publisher ...]
        pkg history [-Hl] [-n number]
        pkg purge-history
        pkg rebuild-index

Options:
        -R dir
        --help or -?

Environment:
        PKG_IMAGE"""))
        sys.exit(retcode)

# XXX Subcommands to implement:
#        pkg image-set name value
#        pkg image-unset name
#        pkg image-get [name ...]

INCONSISTENT_INDEX_ERROR_MESSAGE = "The search index appears corrupted.  " + \
    "Please rebuild the index with 'pkg rebuild-index'."

PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE = "\n(Failure of consistent use " + \
    "of pfexec when executing pkg commands is often a\nsource of this problem.)"

def get_fmri_args(api_inst, args, cmd=None):
        """ Convenience routine to check that input args are valid fmris. """

        res = []
        errors = []
        for pat, err, pfmri, matcher in api_inst.parse_fmri_patterns(args):
                if not err:
                        res.append((pat, err, pfmri, matcher))
                        continue
                if isinstance(err, version.VersionError):
                        # For version errors, include the pattern so
                        # that the user understands why it failed.
                        errors.append("Illegal FMRI '%s': %s" % (pat,
                            err))
                else:
                        # Including the pattern is reundant for other
                        # exceptions.
                        errors.append(err)
        if errors:
                error("\n".join(str(e) for e in errors), cmd=cmd)
        return len(errors) == 0, res

def list_inventory(img, args):
        """List packages."""

        opts, pargs = getopt.getopt(args, "Hafnsuv", ["no-refresh"])

        display_headers = True
        refresh_catalogs = True
        pkg_list = api.ImageInterface.LIST_INSTALLED
        summary = False
        verbose = False
        variants = False

        ltypes = set()
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-a":
                        ltypes.add(opt)
                elif opt == "-f":
                        ltypes.add(opt)
                        variants = True
                elif opt == "-n":
                        ltypes.add(opt)
                elif opt == "-s":
                        summary = True
                elif opt == "-u":
                        ltypes.add(opt)
                elif opt == "-v":
                        verbose = True
                elif opt == "--no-refresh":
                        refresh_catalogs = False

        allowed = [
            ("-a", ("-f", "-s", "-v")),
            ("-u", ("-s", "-v")),
            ("-n", ("-s", "-v")),
        ]

        if "-f" in ltypes and "-a" not in ltypes:
                usage(_("-f may only be used in combination with -a"),
                    cmd="list")

        if "-f" in ltypes:
                pkg_list = api.ImageInterface.LIST_ALL
        elif "-a" in ltypes:
                pkg_list = api.ImageInterface.LIST_INSTALLED_NEWEST
        elif "-n" in ltypes:
                pkg_list = api.ImageInterface.LIST_NEWEST
        elif "-u" in ltypes:
                pkg_list = api.ImageInterface.LIST_UPGRADABLE

        for ltype, permitted in allowed:
                if ltype in ltypes:
                        ltypes.discard(ltype)
                        diff = ltypes.difference(permitted)
                        if not diff:
                                # Only allowed options used.
                                continue
                        usage(_("%(opts)s may not be used with %(opt)s") % {
                            "opts": ", ".join(diff), "opt": ltype })

        if summary and verbose:
                usage(_("-s and -v may not be combined"), cmd="list")

        if verbose:
                fmt_str = "%-64s %-10s %s"
        elif summary:
                fmt_str = "%-30s %s"
        else:
                fmt_str = "%-45s %-15s %-10s %s"

        api_inst = __api_alloc(img, quiet=not display_headers)
        if api_inst == None:
                return EXIT_OOPS

        # Each pattern in pats can be a partial or full FMRI, so
        # extract the individual components.  These patterns are
        # transformed here so that partial failure can be detected
        # when more than one pattern is provided.
        rval, res = get_fmri_args(api_inst, pargs, cmd="list")
        if not rval:
                return EXIT_OOPS

        api_inst.log_operation_start("list")
        if pkg_list != api_inst.LIST_INSTALLED and refresh_catalogs:
                # If the user requested packages other than those
                # installed, ensure that a refresh is performed if
                # needed since the catalog may be out of date or
                # invalid as a result of publisher information
                # changing (such as an origin uri, etc.).
                try:
                        api_inst.refresh()
                except api_errors.PermissionsException:
                        # Ignore permission exceptions with the
                        # assumption that an unprivileged user is
                        # executing this command and that the
                        # refresh doesn't matter.
                        pass
                except api_errors.CatalogRefreshException, e:
                        succeeded = display_catalog_failures(e,
                            ignore_perms_failure=True)
                        if succeeded != e.total:
                                # If total number of publishers does
                                # not match 'successful' number
                                # refreshed, abort.
                                return EXIT_OOPS

                except:
                        # Ignore the above error and just use what
                        # already exists.
                        pass

        state_map = [
            [(api.PackageInfo.UPGRADABLE, "u")],
            [(api.PackageInfo.FROZEN, "f")],
            [(api.PackageInfo.OBSOLETE, "o"),
            (api.PackageInfo.RENAMED, "r")],
            [(api.PackageInfo.EXCLUDES, "x")],
            [(api.PackageInfo.INCORPORATED, "i")],
        ]

        # Now get the matching list of packages and display it.
        found = False
        ppub = api_inst.get_preferred_publisher().prefix
        try:
                res = api_inst.get_pkg_list(pkg_list, patterns=pargs,
                    raise_unmatched=True, variants=variants)
                for pt, summ, cats, states in res:
                        found = True
                        if display_headers:
                                if verbose:
                                        msg(fmt_str % \
                                            ("FMRI", "STATE", "UFOXI"))
                                elif summary:
                                        msg(fmt_str % \
                                            ("NAME (PUBLISHER)",
                                            "SUMMARY"))
                                else:
                                        msg(fmt_str % \
                                            ("NAME (PUBLISHER)",
                                            "VERSION", "STATE", "UFOXI"))
                                display_headers = False

                        ufoxi = ""
                        for sentry in state_map:
                                for s, v in sentry:
                                        if s in states:
                                                st = v
                                                break
                                        else:
                                                st = "-"
                                ufoxi += st

                        pub, stem, ver = pt
                        if pub == ppub:
                                spub = ""
                        else:
                                spub = " (" + pub + ")"

                        # Check for installed state first.
                        st_str = ""
                        if api.PackageInfo.INSTALLED in states:
                                st_str = _("installed")
                        elif api.PackageInfo.UNSUPPORTED in states:
                                st_str = _("unsupported")
                        else:
                                st_str = _("known")

                        # Display full FMRI for verbose case.
                        if verbose:
                                pfmri = "pkg://%s/%s@%s" % (pub, stem, ver)
                                msg("%-64s %-10s %s" % (pfmri, st_str, ufoxi))
                                continue

                        # Display short FMRI + summary.
                        pf = stem + spub
                        if summary:
                                if summ is None:
                                        summ = ""
                                msg(fmt_str % (pf, summ))
                                continue

                        # Default case; display short FMRI and version info.
                        sver = version.Version.split(ver)[-1]
                        msg(fmt_str % (pf, sver, st_str, ufoxi))

                if not found and not pargs:
                        if pkg_list == api_inst.LIST_INSTALLED:
                                error(_("no packages installed"))
                                api_inst.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                return EXIT_OOPS
                        elif pkg_list == api_inst.LIST_INSTALLED_NEWEST:
                                error(_("no packages installed or available "
                                    "for installation"))
                                api_inst.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                return EXIT_OOPS
                        elif pkg_list == api_inst.LIST_UPGRADABLE:
                                error(_("no packages are installed or are "
                                    "installed and have newer versions "
                                    "available"))
                                api_inst.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                return EXIT_OOPS
                        else:
                                api_inst.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                return EXIT_OOPS

                api_inst.log_operation_end()
                return EXIT_OK
        except (api_errors.InvalidPackageErrors,
            api_errors.ActionExecutionError,
            api_errors.PermissionsException), e:
                error(e, cmd="list")
                return EXIT_OOPS
        except api_errors.InventoryException, e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_BAD_REQUEST)
                        return EXIT_OOPS

                if found:
                        # Ensure a blank line is inserted after list for
                        # partial failure case.
                        logger.error(" ")

                if pkg_list == api.ImageInterface.LIST_ALL or \
                    pkg_list == api.ImageInterface.LIST_NEWEST:
                        error(_("no packages matching '%s' known") % \
                            ", ".join(e.notfound), cmd="list")
                elif pkg_list == api.ImageInterface.LIST_INSTALLED_NEWEST:
                        error(_("no packages matching '%s' allowed by "
                            "installed incorporations or image variants that "
                            "are known or installed") % \
                            ", ".join(e.notfound), cmd="list")
                        logger.error("Use -af to allow all versions.")
                elif pkg_list == api.ImageInterface.LIST_UPGRADABLE:
                        error(_("no packages matching '%s' are installed "
                            "and have newer versions available") % \
                            ", ".join(e.notfound), cmd="list")
                else:
                        error(_("no packages matching '%s' installed") % \
                            ", ".join(e.notfound), cmd="list")

                if found and e.notfound:
                        # Only some patterns matched.
                        api_inst.log_operation_end()
                        return EXIT_PARTIAL
                api_inst.log_operation_end(result=history.RESULT_NOTHING_TO_DO)
                return EXIT_OOPS

def get_tracker(quiet=False):
        if quiet:
                progresstracker = progress.QuietProgressTracker()
        else:
                try:
                        progresstracker = \
                            progress.FancyUNIXProgressTracker()
                except progress.ProgressTrackerException:
                        progresstracker = progress.CommandLineProgressTracker()
        return progresstracker

def fix_image(img, args):
        progresstracker = get_tracker(False)

        opts, pargs = getopt.getopt(args, "", ["accept", "licenses"])

        accept = show_licenses = False
        for opt, arg in opts:
                if opt == "--accept":
                        accept = True
                elif opt == "--licenses":
                        show_licenses = True

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        found = False
        try:
                res = api_inst.get_pkg_list(api.ImageInterface.LIST_INSTALLED,
                    patterns=pargs, raise_unmatched=True, return_fmris=True)

                repairs = []
                for entry in res:
                        pfmri = entry[0]
                        found = True
                        entries = []

                        # Since every entry returned by verify might not be
                        # something needing repair, the relevant information
                        # for each package must be accumulated first to find
                        # an overall success/failure result and then the
                        # related messages output for it.
                        for act, errors, warnings, pinfo in img.verify(pfmri,
                            progresstracker, verbose=True, forever=True):
                                if not errors:
                                        # Fix will silently skip packages that
                                        # don't have errors, but will display
                                        # the additional messages if there
                                        # is at least one error.
                                        continue

                                # Informational messages are ignored by fix.
                                entries.append((act, errors, warnings ))

                        if not entries:
                                # Nothing to fix for this package.
                                continue

                        msg(_("Verifying: %(pkg_name)-50s %(result)7s") % {
                            "pkg_name": pfmri.get_pkg_stem(),
                            "result": _("ERROR") })

                        failed = []
                        for act, errors, warnings in entries:
                                failed.append(act)
                                msg("\t%s" % act.distinguished_name())
                                for x in errors:
                                        msg("\t\t%s" % x)
                                for x in warnings:
                                        msg("\t\t%s" % x)
                        repairs.append((pfmri, failed))
        except api_errors.InventoryException, e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        return EXIT_OOPS

                if found:
                        # Ensure a blank line is inserted after list for
                        # partial failure case.
                        logger.error(" ")

                error(_("no packages matching '%s' installed") % \
                    ", ".join(e.notfound), cmd="fix")

                if found and e.notfound:
                        # Only some patterns matched.
                        return EXIT_PARTIAL
                return EXIT_OOPS

        # Repair anything we failed to verify
        if repairs:
                # Create a snapshot in case they want to roll back
                success = False
                try:
                        be = bootenv.BootEnv(img.get_root())
                        if be.exists():
                                msg(_("Created ZFS snapshot: %s") %
                                    be.snapshot_name)
                except RuntimeError:
                        # Error is printed by the BootEnv call.
                        be = bootenv.BootEnvNull(img.get_root())
                img.bootenv = be
                try:
                        success = img.repair(repairs, progresstracker,
                            accept=accept, show_licenses=show_licenses)
                except (api_errors.InvalidPlanError,
                    api_errors.InvalidPackageErrors,
                    api_errors.ActionExecutionError,
                    api_errors.PermissionsException), e:
                        logger.error("\n")
                        logger.error(str(e))
                except api_errors.PlanLicenseErrors, e:
                        # Prepend a newline because otherwise the exception will
                        # be printed on the same line as the spinner.
                        logger.error("\n")
                        error(_("The following packages require their "
                            "licenses to be accepted before they can be "
                            "repaired: "))
                        logger.error(str(e))
                        logger.error(_("To indicate that you agree to and "
                            "accept the terms of the licenses of the packages "
                            "listed above, use the --accept option.  To "
                            "display all of the related licenses, use the "
                            "--licenses option."))
                        return EXIT_LICENSE
                except api_errors.RebootNeededOnLiveImageException:
                        error(_("Requested \"fix\" operation would affect "
                            "files that cannot be modified in live image.\n"
                            "Please retry this operation on an alternate boot "
                            "environment."))
                        return EXIT_NOTLIVE

                if not success:
                        progresstracker.verify_done()
                        return EXIT_OOPS
        progresstracker.verify_done()
        return EXIT_OK

def verify_image(img, args):
        opts, pargs = getopt.getopt(args, "vfqH")

        quiet = verbose = False
        # for now, always check contents of files
        forever = display_headers = True

        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                if opt == "-v":
                        verbose = True
                elif opt == "-f":
                        forever = True
                elif opt == "-q":
                        quiet = True
                        display_headers = False

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd="verify")

        api_inst = __api_alloc(img, quiet=quiet)
        if api_inst == None:
                return EXIT_OOPS

        any_errors = False
        processed = False
        notfound = EmptyI
        progresstracker = get_tracker(quiet)
        try:
                res = api_inst.get_pkg_list(api.ImageInterface.LIST_INSTALLED,
                    patterns=pargs, raise_unmatched=True, return_fmris=True)

                for entry in res:
                        pfmri = entry[0]
                        entries = []
                        result = _("OK")
                        failed = False
                        processed = True

                        # Since every entry returned by verify might not be
                        # something needing repair, the relevant information
                        # for each package must be accumulated first to find
                        # an overall success/failure result and then the
                        # related messages output for it.
                        for act, errors, pwarnings, pinfo in img.verify(pfmri,
                            progresstracker, verbose=verbose, forever=forever):
                                if errors:
                                        failed = True
                                        if quiet:
                                                # Nothing more to do.
                                                break
                                        result = _("ERROR")
                                elif not failed and pwarnings:
                                        result = _("WARNING")

                                entries.append((act, errors, pwarnings, pinfo))

                        any_errors = any_errors or failed
                        if (not failed and not verbose) or quiet:
                                # Nothing more to do.
                                continue

                        # Could this be moved into the progresstracker?
                        if display_headers:
                                display_headers = False
                                msg(_("Verifying: %(pkg_name)-50s "
                                    "%(result)7s") % { "pkg_name": _("PACKAGE"),
                                    "result": _("STATUS") })

                        msg(_("%(pkg_name)-50s %(result)7s") % {
                            "pkg_name": pfmri.get_pkg_stem(),
                            "result": result })

                        for act, errors, warnings, pinfo in entries:
                                msg("\t%s" % act.distinguished_name())
                                for x in errors:
                                        msg("\t\t%s" % x)
                                for x in warnings:
                                        msg("\t\t%s" % x)
                                if verbose:
                                        # Only display informational messages if
                                        # verbose is True.
                                        for x in pinfo:
                                                msg("\t\t%s" % x)
        except api_errors.InventoryException, e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_BAD_REQUEST)
                        return EXIT_OOPS
                notfound = e.notfound

        if processed:
                progresstracker.verify_done()

        if notfound:
                if processed:
                        # Ensure a blank line is inserted after verify output.
                        logger.error(" ")

                error(_("no packages matching '%s' installed") % \
                    ", ".join(notfound), cmd="fix")

                if processed:
                        if any_errors:
                                msg2 = "See above for\nverification failures."
                        else:
                                msg2 = "No packages failed\nverification."
                        logger.error(_("\nAll other patterns matched "
                            "installed packages.  %s" % msg2))
                any_errors = True

        if any_errors:
                return EXIT_OOPS
        return EXIT_OK

def accept_plan_licenses(api_inst):
        """Helper function that marks all licenses for the current plan as
        accepted if they require acceptance."""

        plan = api_inst.describe()
        for pfmri, src, dest, accepted, displayed in plan.get_licenses():
                if not dest.must_accept:
                        continue
                api_inst.set_plan_license_status(pfmri, dest.license,
                    accepted=True)

def display_plan_licenses(api_inst, show_all=False):
        """Helper function to display licenses for the current plan.

        'show_all' is an optional boolean value indicating whether all licenses
        should be displayed or only those that have must-display=true."""

        plan = api_inst.describe()

        for pfmri, src, dest, accepted, displayed in plan.get_licenses():
                if not show_all and not dest.must_display:
                        continue
                elif not show_all and dest.must_display and displayed:
                        # License already displayed, so doesn't need to be
                        # displayed again.
                        continue

                lic = dest.license
                logger.info("-" * 60)
                logger.info(_("Package: %s") % pfmri)
                logger.info(_("License: %s\n") % lic)
                logger.info(dest.get_text())
                logger.info("\n")

                # Mark license as having been displayed.
                api_inst.set_plan_license_status(pfmri, lic, displayed=True)

def __api_prepare(operation, api_inst, accept=False, show_licenses=False):
        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        # XXX would be nice to kick the progress tracker.
        try:
                display_plan_licenses(api_inst, show_all=show_licenses)
                if accept:
                        accept_plan_licenses(api_inst)
                api_inst.prepare()
        except (api_errors.PermissionsException, api_errors.UnknownErrors), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.TransportError, e:
                # move past the progress tracker line.
                msg("\n")
                raise e
        except api_errors.PlanLicenseErrors, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                logger.error("\n")
                error(_("The following packages require their "
                    "licenses to be accepted before they can be installed "
                    "or updated: "))
                logger.error(str(e))
                logger.error(_("To indicate that you agree to and accept the "
                    "terms of the licenses of the packages listed above, "
                    "use the --accept option.  To display all of the related "
                    "licenses, use the --licenses option."))
                return EXIT_LICENSE
        except api_errors.InvalidPlanError, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except KeyboardInterrupt:
                raise
        except:
                error(_("\nAn unexpected error happened while preparing for " \
                    "%s:") % operation)
                raise
        return EXIT_OK

def __api_execute_plan(operation, api_inst):
        try:
                api_inst.execute_plan()
        except RuntimeError, e:
                error(_("%s failed: %s") % (operation, e))
                return EXIT_OOPS
        except (api_errors.InvalidPlanError,
            api_errors.ActionExecutionError,
            api_errors.InvalidPackageErrors), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.ImageUpdateOnLiveImageException:
                error(_("%s cannot be done on live image") % operation)
                return EXIT_NOTLIVE
        except api_errors.RebootNeededOnLiveImageException:
                error(_("Requested \"%s\" operation would affect files that "
                    "cannot be modified in live image.\n"
                    "Please retry this operation on an alternate boot "
                    "environment.") % operation)
                return EXIT_NOTLIVE
        except api_errors.CorruptedIndexException, e:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE)
                return EXIT_OOPS
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE)
                return EXIT_OOPS
        except (api_errors.PermissionsException, api_errors.UnknownErrors), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.MainDictParsingException, e:
                error(str(e))
                return EXIT_OOPS
        except KeyboardInterrupt:
                raise
        except api_errors.BEException, e:
                error(e)
                return EXIT_OOPS
        except api_errors.WrapSuccessfulIndexingException:
                raise
        except Exception, e:
                error(_("An unexpected error happened during " \
                    "%s: %s") % (operation, e))
                raise
        return EXIT_OK

def __api_alloc(img, quiet=False):
        progresstracker = get_tracker(quiet)

        try:
                api_inst = api.ImageInterface(img, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("No image rooted at '%s'") % e.user_dir)
                return None
        except api_errors.PermissionsException, e:
                error(e)
                return None
        return api_inst

def __api_plan_exception(op, noexecute):
        e_type, e, e_traceback = sys.exc_info()

        if e_type == api_errors.ImageNotFoundException:
                error(_("No image rooted at '%s'") % e.user_dir)
                return False
        if e_type == api_errors.InventoryException:
                error(_("%s failed (inventory exception):\n%s") % (op, e))
                return False
        if e_type == api_errors.IpkgOutOfDateException:
                msg(_("""\
WARNING: pkg(5) appears to be out of date, and should be updated before
running %(op)s.  Please update pkg(5) using 'pfexec pkg install
pkg:/package/pkg' and then retry the %(op)s."""
                    ) % locals())
                return False
        if e_type == api_errors.NonLeafPackageException:
                error(_("""\
Cannot remove '%s' due to the following packages that depend on it:"""
                    ) % e[0])
                for d in e[1]:
                        logger.error("  %s" % d)
                return False
        if e_type == api_errors.CatalogRefreshException:
                if display_catalog_failures(e) != 0:
                        return False
                if noexecute:
                        return True
                return False
        if e_type in (api_errors.InvalidPlanError,
            api_errors.ActionExecutionError,
            api_errors.InvalidPackageErrors):
                error("\n" + str(e))
                return False
        if issubclass(e_type, api_errors.BEException):
                error(_(e))
                return False
        if e_type in (api_errors.CertificateError,
            api_errors.UnknownErrors,
            api_errors.PlanCreationException,
            api_errors.PermissionsException):
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return False
        if e_type == fmri.IllegalFmri:
                error(e, cmd=op)
                return False

        # if we didn't deal with the exception above, pass it on.
        raise
        # NOTREACHED

def change_variant(img, args):
        """Attempt to change a variant associated with an image, updating
        the image contents as necessary."""

        op = "change-variant"
        opts, pargs = getopt.getopt(args, "nvq", ["accept", "be-name=",
            "licenses"])

        accept = quiet = noexecute = show_licenses = verbose = False
        be_name = None
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--accept":
                        accept = True
                elif opt == "--be-name":
                        be_name = arg
                elif opt == "--licenses":
                        show_licenses = True

        if verbose and quiet:
                usage(_("%s: -v and -q may not be combined") % op)

        if not pargs:
                usage(_("%s: no variants specified") % op)

        variants = dict()
        for arg in pargs:
                # '=' is not allowed in variant names or values
                if (len(arg.split('=')) != 2):
                        usage(_("%s: variants must to be of the form "
                            "'<name>=<value>'.") % op)

                # get the variant name and value
                name, value = arg.split('=')
                if not name.startswith("variant."):
                        name = "variant.%s" % name

                # make sure the user didn't specify duplicate variants
                if name in variants:
                        usage(_("%s: duplicate variant specified: %s") %
                            (op, name))
                variants[name] = value

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

        stuff_to_do = None
        try:
                stuff_to_do = api_inst.plan_change_varcets(variants,
                    facets=None, noexecute=noexecute, verbose=verbose,
                    be_name=be_name)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return EXIT_OOPS

        if not stuff_to_do:
                msg(_("No updates necessary for this image."))
                return EXIT_NOP

        if noexecute:
                if show_licenses:
                        display_plan_licenses(api_inst, show_all=True)
                return EXIT_OK

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        ret_code = __api_prepare("change-variant", api_inst, accept=accept,
            show_licenses=show_licenses)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan("change-variant", api_inst)

        return ret_code

def change_facet(img, args):
        """Attempt to change the facets as specified, updating
        image as necessary"""

        op = "change-facet"
        opts, pargs = getopt.getopt(args, "nvq", ["accept", "be-name=",
            "licenses"])

        accept = quiet = noexecute = show_licenses = verbose = False
        be_name = None
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--accept":
                        accept = True
                elif opt == "--be-name":
                        be_name = arg
                elif opt == "--licenses":
                        show_licenses = True

        if verbose and quiet:
                usage(_("%s: -v and -q may not be combined") % op)

        if not pargs:
                usage(_("%s: no facets specified") % op)

        facets = img.get_facets()
        allowed_values = {
            "TRUE" : True,
            "FALSE": False,
            "NONE" : None
        }

        for arg in pargs:

                # '=' is not allowed in facet names or values
                if (len(arg.split('=')) != 2):
                        usage(_("%s: facets must to be of the form "
                            "'facet....=[True|False|None]'") % op)

                # get the facet name and value
                name, value = arg.split('=')
                if not name.startswith("facet."):
                        name = "facet." + name

                if value.upper() not in allowed_values:
                        usage(_("%s: facets must to be of the form "
                            "'facet....=[True|False|None]'.") % op)

                v = allowed_values[value.upper()]

                if v is None and name in facets:
                        del facets[name]
                else:
                        facets[name] = v

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

        stuff_to_do = None
        try:
                stuff_to_do = api_inst.plan_change_varcets(variants=None,
                    facets=facets, noexecute=noexecute, verbose=verbose,
                    be_name=be_name)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return EXIT_OOPS

        if not stuff_to_do:
                msg(_("Facet change has no effect on image"))
                return EXIT_NOP

        if noexecute:
                if show_licenses:
                        display_plan_licenses(api_inst, show_all=True)
                return EXIT_OK

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        ret_code = __api_prepare(op, api_inst, accept=accept,
            show_licenses=show_licenses)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        return ret_code

def image_update(img, args):
        """Attempt to take all installed packages specified to latest
        version."""

        # XXX Publisher-catalog issues.
        # XXX Leaf package refinements.

        op = "image-update"
        opts, pargs = getopt.getopt(args, "fnvq", ["accept", "be-name=",
            "licenses", "no-refresh", "no-index"])

        accept = force = quiet = noexecute = show_licenses = verbose = False
        refresh_catalogs = update_index = True
        be_name = None
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "-f":
                        force = True
                elif opt == "--accept":
                        accept = True
                elif opt == "--be-name":
                        be_name = arg
                elif opt == "--licenses":
                        show_licenses = True
                elif opt == "--no-refresh":
                        refresh_catalogs = False
                elif opt == "--no-index":
                        update_index = False

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd=op)

        if pargs:
                usage(_("command does not take operands ('%s')") % \
                    " ".join(pargs), cmd=op)

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

        stuff_to_do = opensolaris_image = None
        try:
                stuff_to_do, opensolaris_image = \
                    api_inst.plan_update_all(sys.argv[0], refresh_catalogs,
                        noexecute, force=force, verbose=verbose,
                        update_index=update_index, be_name=be_name)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return EXIT_OOPS

        if not stuff_to_do:
                msg(_("No updates available for this image."))
                return EXIT_NOP

        if noexecute:
                if show_licenses:
                        display_plan_licenses(api_inst, show_all=True)
                return EXIT_OK

        ret_code = __api_prepare(op, api_inst, accept=accept,
            show_licenses=show_licenses)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        if ret_code == 0 and opensolaris_image:
                msg("\n" + "-" * 75)
                msg(_("NOTE: Please review release notes posted at:\n" ))
                msg(misc.get_release_notes_url())
                msg("-" * 75 + "\n")

        return ret_code

def install(img, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Publisher-catalog issues.
        op = "install"
        opts, pargs = getopt.getopt(args, "nvq", ["accept", "licenses",
            "no-refresh", "no-index"])

        accept = quiet = noexecute = show_licenses = verbose = False
        refresh_catalogs = update_index = True

        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--accept":
                        accept = True
                elif opt == "--licenses":
                        show_licenses = True
                elif opt == "--no-refresh":
                        refresh_catalogs = False
                elif opt == "--no-index":
                        update_index = False

        if not pargs:
                usage(_("at least one package name required"), cmd=op)

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd=op)

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

        rval, res = get_fmri_args(api_inst, pargs, cmd=op)
        if not rval:
                return EXIT_OOPS

        stuff_to_do = None
        try:
                stuff_to_do = api_inst.plan_install(pargs,
                    refresh_catalogs, noexecute, verbose=verbose,
                    update_index=update_index)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return EXIT_OOPS

        if not stuff_to_do:
                msg(_("No updates necessary for this image."))
                return EXIT_NOP

        if noexecute:
                if show_licenses:
                        display_plan_licenses(api_inst, show_all=True)
                return EXIT_OK

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        ret_code = __api_prepare(op, api_inst, accept=accept,
            show_licenses=show_licenses)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        return ret_code


def uninstall(img, args):
        """Attempt to take package specified to DELETED state."""

        op = "uninstall"
        opts, pargs = getopt.getopt(args, "nrvq", ["no-index"])

        quiet = noexecute = recursive_removal = verbose = False
        update_index = True
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-r":
                        recursive_removal = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--no-index":
                        update_index = False

        if not pargs:
                usage(_("at least one package name required"), cmd=op)

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd=op)

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

        rval, res = get_fmri_args(api_inst, pargs, cmd=op)
        if not rval:
                return EXIT_OOPS

        try:
                if not api_inst.plan_uninstall(pargs, recursive_removal,
                    noexecute, verbose=verbose, update_index=update_index):
                        assert 0
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return EXIT_OOPS
        if noexecute:
                return EXIT_OK

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        ret_code = __api_prepare(op, api_inst)
        if ret_code != EXIT_OK:
                return ret_code

        return __api_execute_plan(op, api_inst)

def freeze(img, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions.  Package must have been in the INSTALLED state."""
        return EXIT_OK

def unfreeze(img, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""
        return EXIT_OK

def __convert_output(a_str, match):
        """Converts a string to a three tuple with the information to fill
        the INDEX, ACTION, and VALUE columns.

        The "a_str" parameter is the string representation of an action.

        The "match" parameter is a string whose precise interpretation is given
        below.

        For most action types, match defines which attribute the query matched
        with.  For example, it states whether the basename or path attribute of
        a file action matched the query.  Attribute (set) actions are treated
        differently because they only have one attribute, and many values
        associated with that attribute.  For those actions, the match parameter
        states which value matched the query."""

        a = actions.fromstr(a_str.rstrip())
        if isinstance(a, actions.attribute.AttributeAction):
                return a.attrs.get(a.key_attr), a.name, match
        return match, a.name, a.attrs.get(a.key_attr)

def produce_matching_token(action, match):
        """Given an action and a match value (see convert_output for more
        details on this parameter), return the token which matched the query."""

        if isinstance(action, actions.attribute.AttributeAction):
                return match
        if match == "basename":
                return action.attrs.get("path")
        r = action.attrs.get(match)
        if r:
                return r
        return action.attrs.get(action.key_attr)

def produce_matching_type(action, match):
        """Given an action and a match value (see convert_output for more
        details on this parameter), return the kind of match this was.  For
        example, if the query matched a portion of a path of an action, this
        will return 'path'.  If the action is an attribute action, it returns
        the name set in the action. """

        if not isinstance(action, actions.attribute.AttributeAction):
                return match
        return action.attrs.get("name")

def v1_extract_info(tup, return_type, pub):
        """Given a result from search, massages the information into a form
        useful for produce_lines.

        The "return_type" parameter is an enumeration that describes the type
        of the information that will be converted.

        The type of the "tup" parameter depends on the value of "return_type".
        If "return_type" is action information, "tup" is a three-tuple of the
        fmri name, the match, and a string representation of the action.  In
        the case where "return_type" is package information, "tup" is a one-
        tuple containing the fmri name.

        The "pub" parameter contains information about the publisher from which
        the result was obtained."""

        action = None
        match = None
        match_type = None

        if return_type == api.Query.RETURN_ACTIONS:
                try:
                        pfmri, match, action = tup
                except ValueError:
                        error(_("The repository returned a malformed result.\n"
                            "The problematic structure:%r") % (tup,))
                        return False
                try:
                        action = actions.fromstr(action.rstrip())
                except actions.ActionError, e:
                        error(_("The repository returned an invalid or "
                            "unsupported action.\n%s") % e)
                        return False
                match_type = produce_matching_type(action, match)
                match = produce_matching_token(action, match)
        else:
                pfmri = tup
        return pfmri, action, pub, match, match_type

def search(img, args):
        """Search for the given query."""

        # Constants which control the paging behavior for search output.
        page_timeout = .5
        max_timeout = 5
        min_page_size = 5

        search_attrs = valid_special_attrs[:]
        search_attrs.extend(["search.match", "search.match_type"])

        search_prefixes = valid_special_prefixes[:]
        search_prefixes.extend(["search."])

        opts, pargs = getopt.getopt(args, "Haflo:prs:I")

        default_attrs_action = ["search.match_type", "action.name",
            "search.match", "pkg.shortfmri"]

        default_attrs_package = ["pkg.shortfmri", "pkg.publisher"]

        local = remote = case_sensitive = False
        servers = []
        attrs = []

        display_headers = True
        prune_versions = True
        return_actions = True
        use_default_attrs = True

        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-a":
                        return_actions = True
                elif opt == "-f":
                        prune_versions = False
                elif opt == "-l":
                        local = True
                elif opt == "-o":
                        attrs.extend(arg.split(","))
                        use_default_attrs = False
                elif opt == "-p":
                        return_actions = False
                elif opt == "-r":
                        remote = True
                elif opt == "-s":
                        if not misc.valid_pub_url(arg):
                                orig_arg = arg
                                arg = "http://" + arg
                                if not misc.valid_pub_url(arg):
                                        error(_("%s is not a valid "
                                            "repository URL.") % orig_arg)
                                        return EXIT_OOPS
                        remote = True
                        servers.append({"origin": arg})
                elif opt == "-I":
                        case_sensitive = True

        if not local and not remote:
                remote = True

        if not pargs:
                usage(_("at least one search term must be provided"),
                    cmd="search")

        check_attrs(attrs, "search", reference=search_attrs,
            prefixes=search_prefixes)

        action_attr = False
        for a in attrs:
                if a.startswith("action.") or a.startswith("search.match"):
                        action_attr = True
                        if not return_actions:
                                usage(_("action level options ('%s') to -o "
                                    "cannot be used with the -p option") % a,
                                    cmd="search")
                        break

        searches = []

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        try:
                query = [api.Query(" ".join(pargs), case_sensitive,
                    return_actions)]
        except api_errors.BooleanQueryException, e:
                error(e)
                return EXIT_OOPS

        good_res = False
        bad_res = False

        try:
                if local:
                        searches.append(api_inst.local_search(query))
                if remote:
                        searches.append(api_inst.remote_search(query,
                            servers=servers, prune_versions=prune_versions))
                # By default assume we don't find anything.
                retcode = EXIT_OOPS

                # get initial set of results
                justs = calc_justs(attrs)
                page_again = True
                widths = []
                st = None
                err = None
                header_attrs = attrs
                last_line = None
                shown_headers = False
                while page_again:
                        unprocessed_res = []
                        page_again = False
                        # Indexless search raises a slow search exception. In
                        # that case, catch the exception, finish processing the
                        # results, then propogate the error.
                        try:
                                for raw_value in itertools.chain(*searches):
                                        if not st:
                                                st = time.time()
                                        try:
                                                query_num, pub, \
                                                    (v, return_type, tmp) = \
                                                    raw_value
                                        except ValueError, e:
                                                error(_("The repository "
                                                    "returned a malformed "
                                                    "result:%r") %
                                                    (raw_value,))
                                                bad_res = True
                                                continue
                                        # This check is necessary since a
                                        # a pacakge search can be specified
                                        # using the <> operator.
                                        if action_attr and \
                                            return_type != \
                                            api.Query.RETURN_ACTIONS:
                                                usage(_("action level options "
                                                    "to -o cannot be used with "
                                                    "the queries that return "
                                                    "packages"), cmd="search")
                                        if use_default_attrs and not justs:
                                                if return_type == \
                                                    api.Query.RETURN_ACTIONS:
                                                        attrs = \
                                                            default_attrs_action
                                                        header_attrs = \
                                                            ["index", "action",
                                                            "value", "package"]
                                                else:
                                                        attrs = default_attrs_package
                                                        header_attrs = \
                                                            ["package",
                                                            "publisher"]
                                                justs = calc_justs(attrs)
                                        ret = v1_extract_info(
                                            tmp, return_type, pub)
                                        bad_res |= isinstance(ret, bool)
                                        if ret:
                                                good_res = True
                                                unprocessed_res.append(ret)
                                        # Check whether the paging timeout
                                        # should be increased.
                                        if time.time() - st > page_timeout:
                                                if len(unprocessed_res) > \
                                                    min_page_size:
                                                        page_again = True
                                                        break
                                                else:
                                                        page_timeout = min(
                                                            page_timeout * 2,
                                                            max_timeout)
                        except api_errors.ApiException, e:
                                err = e
                        lines = produce_lines(unprocessed_res, attrs,
                            show_all=True, remove_consec_dup_lines=True,
                            last_res=last_line)
                        if not lines:
                                continue
                        old_widths = widths[:]
                        widths = calc_widths(lines, attrs, widths)
                        # If headers are being displayed and the layout of the
                        # columns have changed, print the headers again using
                        # the new widths.
                        if display_headers and (not shown_headers or
                            old_widths[:-1] != widths[:-1]):
                                shown_headers = True
                                print_headers(header_attrs, widths, justs)
                        for line in lines:
                                msg((create_output_format(display_headers,
                                    widths, justs, line) %
                                    tuple(line)).rstrip())
                        last_line = lines[-1]
                        st = time.time()
                if err:
                        raise err


        except (api_errors.IncorrectIndexFileHash,
            api_errors.InconsistentIndexException):
                error(_("The search index appears corrupted.  Please "
                    "rebuild the index with 'pkg rebuild-index'."))
                return EXIT_OOPS
        except api_errors.ProblematicSearchServers, e:
                error(e)
                bad_res = True
        except api_errors.SlowSearchUsed, e:
                error(e)
        except (api_errors.IncorrectIndexFileHash,
            api_errors.InconsistentIndexException):
                error(_("The search index appears corrupted.  Please "
                    "rebuild the index with 'pkg rebuild-index'."))
                return EXIT_OOPS
        except api_errors.ApiException, e:
                error(e)
                return EXIT_OOPS
        if good_res and bad_res:
                retcode = EXIT_PARTIAL
        elif bad_res:
                retcode = EXIT_OOPS
        elif good_res:
                retcode = EXIT_OK
        return retcode

def info(img, args):
        """Display information about a package or packages.
        """

        display_license = False
        info_local = False
        info_remote = False

        opts, pargs = getopt.getopt(args, "lr", ["license"])
        for opt, arg in opts:
                if opt == "-l":
                        info_local = True
                elif opt == "-r":
                        info_remote = True
                elif opt == "--license":
                        display_license = True

        if not info_local and not info_remote:
                info_local = True
        elif info_local and info_remote:
                usage(_("-l and -r may not be combined"), cmd="info")

        if info_remote and not pargs:
                usage(_("must request remote info for specific packages"),
                    cmd="info")

        err = 0

        api_inst = __api_alloc(img, quiet=True)
        if api_inst == None:
                return EXIT_OOPS

        info_needed = api.PackageInfo.ALL_OPTIONS
        if not display_license:
                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    frozenset([api.PackageInfo.LICENSES])
        info_needed -= api.PackageInfo.ACTION_OPTIONS
        info_needed |= frozenset([api.PackageInfo.DEPENDENCIES])

        try:
                ret = api_inst.info(pargs, info_local, info_needed)
        except (api_errors.InvalidPackageErrors,
            api_errors.ActionExecutionError,
            api_errors.UnrecognizedOptionsToInfo,
            api_errors.UnknownErrors,
            api_errors.PermissionsException), e:
                error(e)
                return EXIT_OOPS
        except api_errors.NoPackagesInstalledException:
                error(_("no packages installed"))
                return EXIT_OOPS

        pis = ret[api.ImageInterface.INFO_FOUND]
        notfound = ret[api.ImageInterface.INFO_MISSING]
        illegals = ret[api.ImageInterface.INFO_ILLEGALS]

        if illegals:
                # No other results will be returned if illegal patterns were
                # specified.
                for i in illegals:
                        logger.error(str(i))
                return EXIT_OOPS

        no_licenses = []
        for i, pi in enumerate(pis):
                if i > 0:
                        msg("")

                if display_license:
                        if not pi.licenses:
                                no_licenses.append(pi.fmri)
                        else:
                                for lic in pi.licenses:
                                        msg(lic)
                        continue

                state = ""
                if api.PackageInfo.OBSOLETE in pi.states:
                        state = _("Obsolete")
                elif api.PackageInfo.RENAMED in pi.states:
                        state = _("Renamed")

                if state:
                        fmt = "%%s (%s)" % state
                else:
                        fmt = "%s"

                if api.PackageInfo.INSTALLED in pi.states:
                        state = fmt % _("Installed")
                elif api.PackageInfo.UNSUPPORTED in pi.states:
                        state = fmt % _("Unsupported")
                else:
                        state = fmt % _("Not installed")

                name_str = _("          Name:")
                msg(name_str, pi.pkg_stem)
                msg(_("       Summary:"), pi.summary)
                if pi.description:
                        desc_label = _("   Description:")
                        start_loc = len(desc_label) + 1
                        end_loc = 80
                        res = textwrap.wrap(pi.description,
                            width=end_loc - start_loc)
                        pad = "\n" + " " * start_loc
                        res = pad.join(res)
                        msg(desc_label, res)
                if pi.category_info_list:
                        verbose = len(pi.category_info_list) > 1
                        msg(_("      Category:"),
                            pi.category_info_list[0].__str__(verbose))
                        if len(pi.category_info_list) > 1:
                                for ci in pi.category_info_list[1:]:
                                        msg(" " * len(name_str),
                                            ci.__str__(verbose))

                msg(_("         State:"), state)

                # Renamed packages have dependencies, but the dependencies
                # may not apply to this image's variants so won't be
                # returned.
                if api.PackageInfo.RENAMED in pi.states:
                        renamed_to = ""
                        if pi.dependencies:
                                renamed_to = pi.dependencies[0]
                        msg(_("    Renamed to:"), renamed_to)
                        for dep in pi.dependencies[1:]:
                                msg(" " * len(name_str), dep)

                # XXX even more info on the publisher would be nice?
                msg(_("     Publisher:"), pi.publisher)
                msg(_("       Version:"), pi.version)
                msg(_(" Build Release:"), pi.build_release)
                msg(_("        Branch:"), pi.branch)
                msg(_("Packaging Date:"), pi.packaging_date)
                msg(_("          Size:"), misc.bytes_to_str(pi.size))
                msg(_("          FMRI:"), pi.fmri)
                # XXX add license/copyright info here?

        if notfound:
                if pis:
                        err = EXIT_PARTIAL
                        logger.error("")
                else:
                        err = EXIT_OOPS

                if info_local:
                        logger.error(_("""\
pkg: info: no packages matching the following patterns you specified are
installed on the system.  Try specifying -r to query remotely:"""))
                elif info_remote:
                        logger.error(_("""\
pkg: info: no packages matching the following patterns you specified were
found in the catalog.  Try relaxing the patterns, refreshing, and/or
examining the catalogs:"""))
                logger.error("")
                for p in notfound:
                        logger.error("        %s" % p)

        if no_licenses:
                if len(no_licenses) == len(pis):
                        err = EXIT_OOPS
                else:
                        err = EXIT_PARTIAL
                error(_("no license information could be found for the "
                    "following packages:"))
                for pfmri in no_licenses:
                        logger.error("\t%s" % pfmri)
        return err

def calc_widths(lines, attrs, widths=None):
        """Given a set of lines and a set of attributes, calculate the minimum
        width each column needs to hold its contents."""

        if not widths:
                widths = [ len(attr) - attr.find(".") - 1 for attr in attrs ]
        for l in lines:
                for i, a in enumerate(l):
                        if len(str(a)) > widths[i]:
                                widths[i] = len(str(a))
        return widths

def calc_justs(attrs):
        """Given a set of output attributes, find any attributes with known
        justification directions and assign them."""

        def __chose_just(attr):
                if attr in ["action.name", "action.key", "action.raw",
                    "pkg.name", "pkg.fmri", "pkg.shortfmri", "pkg.publisher"]:
                        return JUST_LEFT
                return JUST_UNKNOWN
        return [ __chose_just(attr) for attr in attrs ]

def produce_lines(actionlist, attrs, action_types=None, show_all=False,
    remove_consec_dup_lines=False, last_res=None):
        """Produces a list of n tuples (where n is the length of attrs)
        containing the relevant information about the actions.

        The "actionlist" parameter is a list of tuples which contain the fmri
        of the package that's the source of the action, the action, and the
        publisher the action's package came from. If the actionlist was
        generated by searching, the last two pieces, "match" and "match_type"
        contain information about why this action was selected.

        The "attrs" parameter is a list of the attributes of the action that
        should be displayed.

        The "action_types" parameter may contain a list of the types of actions
        that should be displayed.

        The "show_all" parameter determines whether an action that lacks one
        or more of the desired attributes will be displayed or not.

        The "remove_consec_dup_lines" parameter determines whether consecutive
        duplicate lines should be removed from the results.

        The "last_res" paramter is a seed to compare the first result against
        for duplicate removal.
        """

        # Assert that if last_res is set, we should be removing duplicate
        # lines.
        assert(remove_consec_dup_lines or not last_res)
        lines = []
        if last_res:
                lines.append(last_res)
        for pfmri, action, pub, match, match_type in actionlist:
                if action_types and action.name not in action_types:
                        continue
                line = []
                for attr in attrs:
                        if action and attr in action.attrs:
                                a = action.attrs[attr]
                        elif attr == "action.name":
                                a = action.name
                        elif attr == "action.key":
                                a = action.attrs[action.key_attr]
                        elif attr == "action.raw":
                                a = action
                        elif attr == "action.hash":
                                a = getattr(action, "hash", "")
                        elif attr == "pkg.name":
                                a = pfmri.get_name()
                        elif attr == "pkg.fmri":
                                a = pfmri
                        elif attr == "pkg.shortfmri":
                                a = pfmri.get_short_fmri()
                        elif attr == "pkg.publisher":
                                a = pfmri.get_publisher()
                                if a is None:
                                        a = pub
                                        if a is None:
                                                a = ""
                        elif attr == "search.match":
                                a = match
                        elif attr == "search.match_type":
                                a = match_type
                        else:
                                a = ""

                        line.append(a)

                if (line and [l for l in line if str(l) != ""] or show_all) \
                    and (not remove_consec_dup_lines or not lines or
                    lines[-1] != line):
                        lines.append(line)
        if last_res:
                lines.pop(0)
        return lines

def default_left(v):
        """For a given justification "v", use the default of left justification
        if "v" is JUST_UNKNOWN."""

        if v == JUST_UNKNOWN:
                return JUST_LEFT
        return v

def print_headers(attrs, widths, justs):
        """Print out the headers for the columns in the output.

        The "attrs" parameter provides the headings that should be used.

        The "widths" parameter provides the current estimates of the width
        for each column. These may be changed due to the length of the headers.
        This function does modify the values contained in "widths" outside this
        function.

        The "justs" parameter contains the justifications to use with each
        header."""

        headers = []
        for i, attr in enumerate(attrs):
                headers.append(str(attr.upper()))
                widths[i] = max(widths[i], len(attr))

        # Now that we know all the widths, multiply them by the
        # justification values to get positive or negative numbers to
        # pass to the %-expander.
        widths = [ e[0] * default_left(e[1]) for e in zip(widths, justs) ]
        fmt = ("%%%ss " * len(widths)) % tuple(widths)

        msg((fmt % tuple(headers)).rstrip())

def guess_unknown(j, v):
        """If the justificaton to use for a value is unknown, assume that if
        it is an integer, the output should be right justified, otherwise it
        should be left justified."""

        if j != JUST_UNKNOWN:
                return j
        try:
                int(v)
                return JUST_RIGHT
        except (ValueError, TypeError):
                # attribute is non-numeric or is something like
                # a list.
                return JUST_LEFT

def create_output_format(display_headers, widths, justs, line):
        """Produce a format string that can be used to display results.

        The "display_headers" parameter is whether headers have been displayed
        or not. If they have not, then use a simple tab system. If they
        have, use the information in the other parameters to control the
        formatting of the line.

        The "widths" parameter contains the width to use for each column.

        The "justs" parameter contains the justifications to use for each
        column.

        The "line" parameter contains the information that will be displayed
        using the resulting format. It's needed so that a choice can be made
        about columns with unknown justifications.
        """

        if display_headers:
                # Now that we know all the widths, multiply them by the
                # justification values to get positive or negative numbers to
                # pass to the %-expander.
                line_widths = [
                    w * guess_unknown(j, a)
                    for w, j, a in zip(widths, justs, line)
                ]
                fmt = ("%%%ss " * len(line_widths)) % tuple(line_widths)

                return fmt
        fmt = "%s\t" * len(widths)
        fmt.rstrip("\t")
        return fmt

def display_contents_results(actionlist, attrs, sort_attrs, action_types,
    display_headers):
        """Print results of a "list" operation.  Returns False if no output
        was produced."""

        justs = calc_justs(attrs)
        lines = produce_lines(actionlist, attrs, action_types)
        widths = calc_widths(lines, attrs)

        sortidx = 0
        for i, attr in enumerate(attrs):
                if attr == sort_attrs[0]:
                        sortidx = i
                        break

        # Sort numeric columns numerically.
        if justs[sortidx] == JUST_RIGHT:
                def key_extract(x):
                        try:
                                return int(x[sortidx])
                        except (ValueError, TypeError):
                                return 0
        else:
                key_extract = lambda x: x[sortidx]

        printed_output = False
        for line in sorted(lines, key=key_extract):
                text = (create_output_format(display_headers, widths, justs,
                    line) % tuple(line)).rstrip()
                if not text:
                        continue
                if not printed_output and display_headers:
                        print_headers(attrs, widths, justs)
                printed_output = True
                msg(text)
        return printed_output

def check_attrs(attrs, cmd, reference=None, prefixes=None):
        """For a set of output attributes ("attrs") passed to a command ("cmd"),
        if the attribute lives in a known name space, check whether it is valid.
        """

        if reference is None:
                reference = valid_special_attrs
        if prefixes is None:
                prefixes = valid_special_prefixes
        for a in attrs:
                for p in prefixes:
                        if a.startswith(p) and not a in reference:
                                usage(_("Invalid attribute '%s'") % a, cmd)

def list_contents(img, args):
        """List package contents.

        If no arguments are given, display for all locally installed packages.
        With -H omit headers and use a tab-delimited format; with -o select
        attributes to display; with -s, specify attributes to sort on; with -t,
        specify which action types to list."""

        # XXX Need remote-info option, to request equivalent information
        # from repository.

        opts, pargs = getopt.getopt(args, "Ha:o:s:t:mfr")

        subcommand = "contents"
        display_headers = True
        display_raw = False
        output_fields = False
        remote = False
        local = False
        attrs = []
        sort_attrs = []
        action_types = []
        attr_match = {}
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-a":
                        try:
                                attr, match = arg.split("=", 1)
                        except ValueError:
                                usage(_("-a takes an argument of the form "
                                    "<attribute>=<pattern>"), cmd=subcommand)
                        attr_match.setdefault(attr, []).append(match)
                elif opt == "-o":
                        output_fields = True
                        attrs.extend(arg.split(","))
                elif opt == "-s":
                        sort_attrs.append(arg)
                elif opt == "-t":
                        action_types.extend(arg.split(","))
                elif opt == "-r":
                        remote = True
                elif opt == "-m":
                        display_raw = True

        if not remote and not local:
                local = True
        elif local and remote:
                usage(_("-l and -r may not be combined"), cmd=subcommand)

        if remote and not pargs:
                usage(_("contents: must request remote contents for specific "
                   "packages"), cmd=subcommand)

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        if display_raw:
                display_headers = False
                attrs = ["action.raw"]

                invalid = set(("-H", "-o", "-t")). \
                    intersection(set([x[0] for x in opts]))

                if len(invalid) > 0:
                        usage(_("-m and %s may not be specified at the same "
                            "time") % invalid.pop(), cmd=subcommand)

        check_attrs(attrs, subcommand)

        api_inst.log_operation_start(subcommand)
        if local:
                pkg_list = api.ImageInterface.LIST_INSTALLED
        elif remote:
                pkg_list = api.ImageInterface.LIST_NEWEST

        #
        # If the user specifies no specific attrs, and no specific
        # sort order, then we fill in some defaults.
        #
        if not attrs:
                # XXX Possibly have multiple exclusive attributes per column?
                # If listing dependencies and files, you could have a path/fmri
                # column which would list paths for files and fmris for
                # dependencies.
                attrs = ["path"]

        if not sort_attrs:
                # XXX reverse sorting
                # Most likely want to sort by path, so don't force people to
                # make it explicit
                if "path" in attrs:
                        sort_attrs = ["path"]
                else:
                        sort_attrs = attrs[:1]

        # if we want a raw display (contents -m), disable the automatic
        # variant filtering that normally limits working set.
        if display_raw:
                excludes = EmptyI
        else:
                excludes = api_inst.excludes

        def mmatches(action):
                """Given an action, return True if any of its attributes' values
                matches the pattern for the same attribute in the attr_match
                dictionary, and False otherwise."""

                # If no matches have been specified, all actions match
                if not attr_match:
                        return True

                matchset = set(attr_match.keys())
                attrset = set(action.attrs.keys())

                iset = attrset.intersection(matchset)

                # Iterate over the set of attributes common to the action and
                # the match specification.  If the values match the pattern in
                # the specification, then return True (implementing an OR across
                # multiple possible matches).
                for attr in iset:
                        for match in attr_match[attr]:
                                for attrval in action.attrlist(attr):
                                        if fnmatch.fnmatch(attrval, match):
                                                return True
                return False

        # Now get the matching list of packages and display it.
        processed = False
        notfound = EmptyI
        try:
                res = api_inst.get_pkg_list(pkg_list, patterns=pargs,
                    raise_unmatched=True, return_fmris=True, variants=True)
                manifests = []

                for pfmri, summ, cats, states in res:
                        manifests.append(api_inst.get_manifest(pfmri,
                            all_variants=display_raw))
        except api_errors.InvalidPackageErrors, e:
                error(str(e), cmd=subcommand)
                api_inst.log_operation_end(
                    result=history.RESULT_FAILED_UNKNOWN)
                return EXIT_OOPS
        except api_errors.InventoryException, e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_BAD_REQUEST)
                        return EXIT_OOPS
                notfound = e.notfound
        else:
                if local and not manifests and not pargs:
                        error(_("no packages installed"), cmd=subcommand)
                        api_inst.log_operation_end(
                            result=history.RESULT_NOTHING_TO_DO)
                        return EXIT_OOPS

        actionlist = [
            (m.fmri, a, None, None, None)
            for m in manifests
            for a in m.gen_actions(excludes)
            if mmatches(a)
        ]

        rval = EXIT_OK
        if attr_match and manifests and not actionlist:
                rval = EXIT_OOPS
                logger.error(_("""\
pkg: contents: no matching actions found in the listed packages"""))

        if manifests and rval == EXIT_OK:
                displayed_results = display_contents_results(actionlist, attrs,
                    sort_attrs, action_types, display_headers)

                if not displayed_results:
                        if output_fields:
                                error(gettext.ngettext("""\
This package contains no actions with the fields specified using the -o
option. Please specify other fields, or use the -m option to show the raw
package manifests.""", """\
These packages contain no actions with the fields specified using the -o
option. Please specify other fields, or use the -m option to show the raw
package manifests.""", len(pargs)))
                        else:
                                error(gettext.ngettext("""\
This package delivers no filesystem content, but may contain metadata. Use
the -o option to specify fields other than 'path', or use the -m option to show
the raw package manifests.""", """\
These packages deliver no filesystem content, but may contain metadata. Use
the -o option to specify fields other than 'path', or use the -m option to show
the raw package manifests.""", len(pargs)))

        if notfound:
                rval = EXIT_OOPS
                if manifests:
                        logger.error("")
                if local:
                        logger.error(_("""\
pkg: contents: no packages matching the following patterns you specified are
installed on the system.  Try specifying -r to query remotely:"""))
                elif remote:
                        logger.error(_("""\
pkg: contents: no packages matching the following patterns you specified were
found in the catalog.  Try relaxing the patterns, refreshing, and/or
examining the catalogs:"""))
                logger.error("")
                for p in notfound:
                        logger.error("        %s" % p)
                api_inst.log_operation_end(
                    result=history.RESULT_NOTHING_TO_DO)
        else:
                api_inst.log_operation_end(result=history.RESULT_SUCCEEDED)
        return rval


def display_catalog_failures(cre, ignore_perms_failure=False):
        total = cre.total
        succeeded = cre.succeeded

        txt = _("pkg: %s/%s catalogs successfully updated:") % (succeeded,
            total)
        if cre.failed:
                # This ensures that the text gets printed before the errors.
                logger.error(txt)
        else:
                msg(txt)

        for pub, err in cre.failed:
                if ignore_perms_failure and \
                    not isinstance(err, api_errors.PermissionsException):
                        # If any errors other than a permissions exception are
                        # found, then don't ignore them.
                        ignore_perms_failure = False
                        break

        if cre.failed and ignore_perms_failure:
                # Consider those that failed to have succeeded and add them
                # to the actual successful total.
                return succeeded + len(cre.failed)

        for pub, err in cre.failed:
                logger.error("   ")
                logger.error(str(err))

        if cre.errmessage:
                logger.error(cre.errmessage)

        return succeeded

def __refresh(api_inst, pubs, full_refresh=False):
        """Private helper method for refreshing publisher data."""

        try:
                # The user explicitly requested this refresh, so set the
                # refresh to occur immediately.
                api_inst.refresh(full_refresh=full_refresh,
                    immediate=True, pubs=pubs)
        except api_errors.PublisherError, e:
                error(e)
                error(_("'pkg publisher' will show a list of publishers."))
                return EXIT_OOPS
        except (api_errors.UnknownErrors, api_errors.PermissionsException), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.CatalogRefreshException, e:
                if display_catalog_failures(e) == 0:
                        return EXIT_OOPS
                return EXIT_PARTIAL
        return EXIT_OK

def publisher_refresh(img, args):
        """Update metadata for the image's publishers."""

        # XXX will need to show available content series for each package
        full_refresh = False
        opts, pargs = getopt.getopt(args, "", ["full"])
        for opt, arg in opts:
                if opt == "--full":
                        full_refresh = True

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS
        return __refresh(api_inst, pargs, full_refresh=full_refresh)

def _get_ssl_cert_key(root, is_zone, ssl_cert, ssl_key):
        if ssl_cert is not None or ssl_key is not None:
                # In the case of zones, the ssl cert given is assumed to
                # be relative to the root of the image, not truly absolute.
                if is_zone:
                        if ssl_cert is not None:
                                ssl_cert = os.path.abspath(
                                    root + os.sep + ssl_cert)
                        if ssl_key is not None:
                                ssl_key = os.path.abspath(
                                    root + os.sep + ssl_key)
                elif orig_cwd:
                        if ssl_cert and not os.path.isabs(ssl_cert):
                                ssl_cert = os.path.normpath(os.path.join(
                                    orig_cwd, ssl_cert))
                        if ssl_key and not os.path.isabs(ssl_key):
                                ssl_key = os.path.normpath(os.path.join(
                                    orig_cwd, ssl_key))
        return ssl_cert, ssl_key

def _set_pub_error_wrap(func, pfx, raise_errors, *args, **kwargs):
        """Helper function to wrap set-publisher private methods.  Returns
        a tuple of (return value, message).  Callers should check the return
        value for errors."""

        try:
                return func(*args, **kwargs)
        except api_errors.CatalogRefreshException, e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                txt = _("Could not refresh the catalog for %s\n") % \
                    pfx
                for pub, err in e.failed:
                        txt += "   \n%s" % err
                return EXIT_OOPS, txt
        except api_errors.InvalidDepotResponseException, e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                if pfx:
                        return EXIT_OOPS, _("The origin URIs for '%(pubname)s' "
                            "do not appear to point to a valid pkg repository."
                            "\nPlease verify the repository's location and the "
                            "client's network configuration."
                            "\nAdditional details:\n\n%(details)s") % {
                            "pubname": pfx, "details": str(e) }
                return EXIT_OOPS, _("The specified URI does not appear to "
                    "point to a valid pkg repository.\nPlease check the URI "
                    "and the client's network configuration."
                    "\nAdditional details:\n\n%s") % str(e)
        except api_errors.ApiException, e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                return EXIT_OOPS, ("\n" + str(e))

def publisher_set(img, args):
        """pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert] [--reset-uuid]
            [-g|--add-origin origin to add] [-G|--remove-origin origin to
            remove] [-m|--add-mirror mirror to add] [-M|--remove-mirror mirror
            to remove] [-p repo_uri] [--enable] [--disable] [--no-refresh]
            [--sticky] [--non-sticky ] [--search-before=publisher]
            [--search-after=publisher] [publisher]"""

        preferred = False
        ssl_key = None
        ssl_cert = None
        origin_uri = None
        reset_uuid = False
        add_mirrors = set()
        remove_mirrors = set()
        add_origins = set()
        remove_origins = set()
        refresh_allowed = True
        disable = None
        sticky = None
        search_before = None
        search_after = None
        repo_uri = None
        clear_sys_repo = False
        sys_repo_uri = None
        socket_path = None

        opts, pargs = getopt.getopt(args, "Pedk:c:O:G:g:M:m:p:",
            ["add-mirror=", "remove-mirror=", "add-origin=",
            "clear-system-repo", "remove-origin=", "no-refresh", "reset-uuid",
            "enable", "disable", "sticky", "non-sticky", "search-before=",
            "search-after=", "system-repo=", "socket-path="])

        for opt, arg in opts:
                if opt == "-c":
                        ssl_cert = arg
                elif opt == "-d" or opt == "--disable":
                        disable = True
                elif opt == "-e" or opt == "--enable":
                        disable = False
                elif opt == "-g" or opt == "--add-origin":
                        add_origins.add(arg)
                elif opt == "-G" or opt == "--remove-origin":
                        remove_origins.add(arg)
                elif opt == "-k":
                        ssl_key = arg
                elif opt == "-O":
                        origin_uri = arg
                elif opt == "-m" or opt == "--add-mirror":
                        add_mirrors.add(arg)
                elif opt == "-M" or opt == "--remove-mirror":
                        remove_mirrors.add(arg)
                elif opt == "-p":
                        repo_uri = arg
                elif opt == "-P":
                        preferred = True
                elif opt == "--reset-uuid":
                        reset_uuid = True
                elif opt == "--no-refresh":
                        refresh_allowed = False
                elif opt == "--sticky":
                        sticky = True
                elif opt == "--non-sticky":
                        sticky = False
                elif opt == "--search-before":
                        search_before = arg
                elif opt == "--search-after":
                        search_after = arg
                elif opt == "--clear-system-repo":
                        clear_sys_repo = True
                elif opt == "--system-repo":
                        sys_repo_uri = arg
                elif opt == "--socket-path":
                        socket_path = arg

        name = None
        if len(pargs) == 0 and not repo_uri:
                usage(_("requires a publisher name"), cmd="set-publisher")
        elif len(pargs) > 1:
                usage( _("only one publisher name may be specified"),
                    cmd="set-publisher",)
        elif pargs:
                name = pargs[0]

        if preferred and disable:
                usage(_("the -P and -d options may not be combined"),
                    cmd="set-publisher")

        if origin_uri and (add_origins or remove_origins):
                usage(_("the -O and -g, --add-origin, -G, or --remove-origin "
                    "options may not be combined"), cmd="set-publisher")

        if search_before and search_after:
                usage(_("search_before and search_after may not be combined"),
                      cmd="set-publisher")

        if repo_uri and (add_origins or add_mirrors or remove_origins or
            remove_mirrors or disable != None or not refresh_allowed or
            reset_uuid or sys_repo_uri or socket_path):
                usage(_("the -p option may not be combined with the -g, "
                    "--add-origin, -G, --remove-origin, -m, --add-mirror, "
                    "-M, --remove-mirror, --enable, --disable, --no-refresh, "
                    "--reset-uuid options, or --system-repo "),
                    cmd="set-publisher")

        if sys_repo_uri and clear_sys_repo:
                usage(_("The --system-repo and --clear-system-repo options "
                    "may not be combined."), cmd="set-publisher")

        if sys_repo_uri and not socket_path:
                usage(_("The --socket-path argument must be used with "
                    "--system-repo."), cmd="set-publisher")

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        # Get sanitized SSL Cert/Key input values.
        ssl_cert, ssl_key = _get_ssl_cert_key(api_inst.root, api_inst.is_zone,
            ssl_cert, ssl_key)

        if not repo_uri:
                # Normal case.
                ret = _set_pub_error_wrap(_add_update_pub, name, [],
                    api_inst, name, disable=disable, sticky=sticky,
                    origin_uri=origin_uri, add_mirrors=add_mirrors,
                    remove_mirrors=remove_mirrors, add_origins=add_origins,
                    remove_origins=remove_origins, ssl_cert=ssl_cert,
                    ssl_key=ssl_key, search_before=search_before,
                    search_after=search_after, reset_uuid=reset_uuid,
                    refresh_allowed=refresh_allowed, preferred=preferred,
                    socket_path=socket_path, clear_sys_repo=clear_sys_repo,
                    sys_repo_uri=sys_repo_uri)
                rval, rmsg = ret
                if rmsg:
                        error(rmsg, cmd="set-publisher")
                return rval

        pubs = None
        # Automatic configuration via -p case.
        def get_pubs():
                repo = publisher.RepositoryURI(repo_uri,
                    ssl_cert=ssl_cert, ssl_key=ssl_key)
                return EXIT_OK, api_inst.get_publisherdata(repo=repo)

        ret = None
        try:
                ret = _set_pub_error_wrap(get_pubs, name,
                    [api_errors.UnsupportedRepositoryOperation])
        except api_errors.UnsupportedRepositoryOperation, e:
                # Fail if the operation can't be done automatically.
                error(str(e), cmd="set-publisher")
                logger.error(_("""
To add a publisher using this repository, execute the following command as a
privileged user:

  pkg set-publisher -g %s <publisher>
""") % repo_uri)
                return EXIT_OOPS
        else:
                rval, rmsg = ret
                if rval != EXIT_OK:
                        error(rmsg, cmd="set-publisher")
                        return rval
                pubs = rmsg

        # For the automatic publisher configuration case, update or add
        # publishers based on whether they exist and if they match any
        # specified publisher prefix.
        if not pubs:
                error(_("""
The specified repository did not contain any publisher configuration
information.  This is likely the result of a repository configuration
error.  Please contact the repository administrator for further
assistance."""))
                return EXIT_OOPS

        if name and name not in pubs:
                known = [p.prefix for p in pubs]
                unknown = [name]
                e = api_errors.UnknownRepositoryPublishers(known=known,
                    unknown=unknown, location=repo_uri)
                error(str(e))
                return EXIT_OOPS

        added = []
        updated = []
        failed = []

        for src_pub in pubs:
                prefix = src_pub.prefix
                if name and prefix != name:
                        # User didn't request this one.
                        continue

                src_repo = src_pub.selected_repository
                if not api_inst.has_publisher(prefix=prefix):
                        add_origins = []
                        if not src_repo or not src_repo.origins:
                                # If the repository publisher configuration
                                # didn't include configuration information
                                # for the publisher's repositories, assume
                                # that the origin for the new publisher
                                # matches the URI provided.
                                add_origins.append(repo_uri)
                        rval, rmsg = _set_pub_error_wrap(_add_update_pub, name,
                            [], api_inst, prefix, pub=src_pub,
                            add_origins=add_origins, ssl_cert=ssl_cert,
                            ssl_key=ssl_key, sticky=sticky,
                            search_after=search_after,
                            search_before=search_before)
                        if rval == EXIT_OK:
                                added.append(prefix)
                else:
                        # The update case is special and requires some
                        # finesse.  In particular, the update should
                        # only happen if the repo_uri specified is
                        # already known to the existing publisher.  This
                        # is just a sanity check to ensure that random
                        # repositories can't attempt to hijack other
                        # publishers.
                        dest_pub = api_inst.get_publisher(prefix=prefix,
                            duplicate=True)
                        dest_repo = dest_pub.selected_repository

                        if not dest_repo.has_origin(repo_uri):
                                failed.append((prefix, _("""\
    The specified repository location is not a known source of publisher
    configuration updates for '%s'.

    This new repository location must be added as an origin to the publisher
    to accept configuration updates from this repository.""") % prefix))
                                continue

                        if not src_repo:
                                # The repository doesn't have to provide origin
                                # information for publishers.  If it doesn't,
                                # the origin of every publisher returned is
                                # assumed to match the URI that the user
                                # provided.  Since this is an update case,
                                # nothing special needs to be done.
                                add_mirrors = []
                                add_origins = []
                        else:
                                # Avoid duplicates by adding only those mirrors
                                # or origins not already known.
                                add_mirrors = [
                                    u.uri
                                    for u in src_repo.mirrors
                                    if u.uri not in dest_repo.mirrors
                                ]
                                add_origins = [
                                    u.uri
                                    for u in src_repo.origins
                                    if u.uri not in dest_repo.origins
                                ]

                                # Special bits to update; for these, take the
                                # new value as-is (don't attempt to merge).
                                for prop in ("collection_type", "description",
                                    "legal_uris", "name", "refresh_seconds",
                                    "registration_uri", "related_uris"):
                                        src_val = getattr(src_repo, prop)
                                        if src_val is not None:
                                                setattr(dest_repo, prop,
                                                    src_val)

                        # If an alias doesn't already exist, update it too.
                        if src_pub.alias and not dest_pub.alias:
                                dest_pub.alias = src_pub.alias

                        rval, rmsg = _set_pub_error_wrap(_add_update_pub, name,
                            [], api_inst, prefix, pub=dest_pub,
                            add_mirrors=add_mirrors, add_origins=add_origins)

                        if rval == EXIT_OK:
                                updated.append(prefix)

                if rval != EXIT_OK:
                        if rmsg:
                                error(rmsg, cmd="set-publisher")
                        failed.append((prefix, msg))
                        continue

        first = True
        for pub, rmsg in failed:
                if first:
                        first = False
                        error("failed to add or update one or more "
                            "publishers", cmd="set-publisher")
                logger.error("  %s:" % pub)
                logger.error(rmsg)

        if added or updated:
                if first:
                        logger.info("pkg set-publisher:")
                if added:
                        logger.info(_("  Added publisher(s): %s") %
                            ", ".join(added))
                if updated:
                        logger.info(_("  Updated publisher(s): %s") %
                            ", ".join(updated))

        if failed:
                if len(failed) != len(pubs):
                        # Not all publishers retrieved could be added or
                        # updated.
                        return EXIT_PARTIAL
                return EXIT_OOPS

        # Now that the configuration was successful, attempt to refresh the
        # catalog data for all of the configured publishers.  If the refresh
        # had been allowed earlier while configuring each publisher, then this
        # wouldn't be necessary and some possibly invalid configuration could
        # have been eliminated sooner.  However, that would be much slower as
        # each refresh requires a client image state rebuild.
        return __refresh(api_inst, added + updated)

def _add_update_pub(api_inst, prefix, pub=None, disable=None, sticky=None,
    origin_uri=None, add_mirrors=EmptyI, remove_mirrors=EmptyI,
    add_origins=EmptyI, remove_origins=EmptyI, ssl_cert=None, ssl_key=None,
    search_before=None, search_after=None, socket_path=None, sys_repo_uri=None,
    reset_uuid=None, refresh_allowed=False, preferred=False,
    clear_sys_repo=False):

        repo = None
        new_pub = False
        if not pub:
                try:
                        pub = api_inst.get_publisher(prefix=prefix,
                            alias=prefix, duplicate=True)
                        if reset_uuid:
                                pub.reset_client_uuid()
                        repo = pub.selected_repository
                except api_errors.UnknownPublisher:
                        if not origin_uri and not add_origins \
                            and not sys_repo_uri:
                                return EXIT_OOPS, _("publisher does not exist. "
                                    "Use -g to define origin URI for new "
                                    "publisher.")
                        # No pre-existing, so create a new one.
                        repo = publisher.Repository()
                        pub = publisher.Publisher(prefix, repositories=[repo])
                        new_pub = True
        elif not api_inst.has_publisher(prefix=pub.prefix):
                new_pub = True

        if not repo:
                repo = pub.selected_repository
                if not repo:
                        # Could be a new publisher from auto-configuration
                        # case where no origin was provided in repository
                        # configuration.
                        repo = publisher.Repository()
                        pub.add_repository(repo)

        if disable is not None:
                # Set disabled property only if provided.
                pub.disabled = disable

        if sticky is not None:
                # Set stickiness only if provided
                pub.sticky = sticky

        if origin_uri:
                # For compatibility with old -O behaviour, treat -O as a wipe
                # of existing origins and add the new one.

                # Only use existing cert information if the new URI uses
                # https for transport.
                if repo.origins and not (ssl_cert or ssl_key) and \
                    origin_uri.startswith("https:"):
                        for uri in repo.origins:
                                if ssl_cert is None:
                                        ssl_cert = uri.ssl_cert
                                if ssl_key is None:
                                        ssl_key = uri.ssl_key
                                break

                repo.reset_origins()
                repo.add_origin(origin_uri)

                # XXX once image configuration supports storing this
                # information at the uri level, ssl info should be set
                # here.

        if clear_sys_repo:
                repo.clear_system_repo()
        elif sys_repo_uri and socket_path:
                repo.set_system_repo(sys_repo_uri, socket_path=socket_path)

        for entry in (("mirror", add_mirrors, remove_mirrors), ("origin",
            add_origins, remove_origins)):
                etype, add, remove = entry
                # XXX once image configuration supports storing this
                # information at the uri level, ssl info should be set
                # here.
                for u in add:
                        getattr(repo, "add_%s" % etype)(u)
                for u in remove:
                        getattr(repo, "remove_%s" % etype)(u)

        # None is checked for here so that a client can unset a ssl_cert or
        # ssl_key by using -k "" or -c "".
        if ssl_cert is not None or ssl_key is not None:
                # Assume the user wanted to update the ssl_cert or ssl_key
                # information for *all* of the currently selected
                # repository's origins and mirrors.
                for uri in repo.origins:
                        if ssl_cert is not None:
                                uri.ssl_cert = ssl_cert
                        if ssl_key is not None:
                                uri.ssl_key = ssl_key
                for uri in repo.mirrors:
                        if ssl_cert is not None:
                                uri.ssl_cert = ssl_cert
                        if ssl_key is not None:
                                uri.ssl_key = ssl_key

        if new_pub:
                api_inst.add_publisher(pub,
                    refresh_allowed=refresh_allowed)
        else:
                api_inst.update_publisher(pub,
                    refresh_allowed=refresh_allowed)

        if preferred:
                api_inst.set_preferred_publisher(prefix=pub.prefix)

        if search_before:
                api_inst.set_pub_search_before(pub.prefix, search_before)

        if search_after:
                api_inst.set_pub_search_after(pub.prefix, search_after)

        return EXIT_OK, None

def publisher_unset(img, args):
        """pkg unset-publisher publisher ..."""

        if len(args) == 0:
                usage(_("at least one publisher must be specified"),
                    cmd="unset-publisher")

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        errors = []
        for name in args:
                try:
                        api_inst.remove_publisher(prefix=name, alias=name)
                except (api_errors.PermissionsException,
                    api_errors.PublisherError), e:
                        errors.append((name, e))

        retcode = EXIT_OK
        if errors:
                if len(errors) == len(args):
                        # If the operation failed for every provided publisher
                        # prefix or alias, complete failure occurred.
                        retcode = EXIT_OOPS
                else:
                        # If the operation failed for only some of the provided
                        # publisher prefixes or aliases, then partial failure
                        # occurred.
                        retcode = EXIT_PARTIAL

                txt = ""
                for name, err in errors:
                        txt += "\n"
                        txt += _("Removal failed for '%(pub)s': %(msg)s") % {
                            "pub": name, "msg": err }
                        txt += "\n"
                error(txt, cmd="unset-publisher")

        return retcode

def publisher_list(img, args):
        """pkg publishers"""
        omit_headers = False
        preferred_only = False
        inc_disabled = True
        valid_formats = ( "tsv", )
        format = "default"
        field_data = {
            "publisher" : [("default", "tsv"), _("PUBLISHER"), ""],
            "attrs" : [("default"), "", ""],
            "type" : [("default", "tsv"), _("TYPE"), ""],
            "status" : [("default", "tsv"), _("STATUS"), ""],
            "uri" : [("default", "tsv"), _("URI"), ""],
            "sticky" : [("tsv"), _("STICKY"), ""],
            "preferred" : [("tsv"), _("PREFERRED"), ""],
            "enabled" : [("tsv"), _("ENABLED"), ""]
        }

        desired_field_order = (_("PUBLISHER"), "", _("STICKY"),
                               _("PREFERRED"), _("ENABLED"), _("TYPE"),
                               _("STATUS"), _("URI"))

        # Custom sort function for preserving field ordering
        def sort_fields(one, two):
                return desired_field_order.index(get_header(one)) - \
                    desired_field_order.index(get_header(two))

        # Functions for manipulating field_data records

        def filter_default(record):
                return "default" in record[0]

        def filter_tsv(record):
                return "tsv" in record[0]

        def get_header(record):
                return record[1]

        def get_value(record):
                return record[2]

        def set_value(record, value):
                record[2] = value

        # 'a' is left over
        opts, pargs = getopt.getopt(args, "F:HPan")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                if opt == "-P":
                        preferred_only = True
                if opt == "-n":
                        inc_disabled = False
                if opt == "-F":
                        format = arg
                        if format not in valid_formats:
                                usage(_("Unrecognized format %(format)s."
                                    " Supported formats: %(valid)s") % \
                                    { "format": format,
                                    "valid": valid_formats }, cmd="publisher")
                                return EXIT_OOPS

        api_inst = __api_alloc(img, quiet=True)
        if api_inst == None:
                return EXIT_OOPS

        cert_cache = {}
        def get_cert_info(ssl_cert):
                if not ssl_cert:
                        return None
                if ssl_cert not in cert_cache:
                        c = cert_cache[ssl_cert] = {}
                        errors = c["errors"] = []
                        times = c["info"] = {
                            "effective": "",
                            "expiration": "",
                        }

                        try:
                                cert = misc.validate_ssl_cert(ssl_cert)
                        except (EnvironmentError,
                            api_errors.CertificateError,
                            api_errors.PermissionsException), e:
                                # If the cert information can't be retrieved,
                                # add the errors to a list and continue on.
                                errors.append(e)
                                c["valid"] = False
                        else:
                                nb = cert.get_notBefore()
                                t = time.strptime(nb, "%Y%m%d%H%M%SZ")
                                nb = datetime.datetime.utcfromtimestamp(
                                    calendar.timegm(t))
                                times["effective"] = nb.strftime("%c")

                                na = cert.get_notAfter()
                                t = time.strptime(na, "%Y%m%d%H%M%SZ")
                                na = datetime.datetime.utcfromtimestamp(
                                    calendar.timegm(t))
                                times["expiration"] = na.strftime("%c")
                                c["valid"] = True

                return cert_cache[ssl_cert]

        retcode = EXIT_OK
        if len(pargs) == 0:

                pref_pub = api_inst.get_preferred_publisher()
                if preferred_only:
                        pubs = [pref_pub]
                else:
                        pubs = [
                            p for p in api_inst.get_publishers()
                            if inc_disabled or not p.disabled
                        ]

                # if more than one, list in publisher search order
                if len(pubs) > 1:
                        so = api_inst.get_pub_search_order()
                        pub_dict = dict([(p.prefix, p) for p in pubs])
                        pubs = [
                                pub_dict[name]
                                for name in so
                                if name in pub_dict
                                ]
                # Create a formatting string for the default output
                # format
                if format == "default":
                        fmt = "%-24s %-12s %-8s %-8s %s"
                        filter_func = filter_default

                # Create a formatting string for the tsv output
                # format
                if format == "tsv":
                        fmt = "%s\t%s\t%s\t%s\t%s\t%s\t%s"
                        filter_func = filter_tsv

                # Extract our list of headers from the field_data
                # dictionary Make sure they are extracted in the
                # desired order by using our custom sort function
                hdrs = map(get_header, sorted(filter(filter_func,
                           field_data.values()), sort_fields))

                # Output an header if desired
                if not omit_headers:
                        msg(fmt % tuple(hdrs))

                for p in pubs:
                        # Store all our publisher related data in
                        # field_data ready for output

                        set_value(field_data["publisher"], p.prefix)
                        # Setup the synthetic attrs field if the
                        # format is default.
                        if format == "default":
                                pstatus = ""

                                if not p.sticky:
                                        pstatus_list = [_("non-sticky")]
                                else:
                                        pstatus_list = []

                                if not preferred_only and p == pref_pub:
                                        pstatus_list.append(_("preferred"))
                                if p.disabled:
                                        pstatus_list.append(_("disabled"))
                                if pstatus_list:
                                        pstatus = "(%s)" % \
                                            ", ".join(pstatus_list)
                                set_value(field_data["attrs"], pstatus)

                        if p.sticky:
                                set_value(field_data["sticky"], _("true"))
                        else:
                                set_value(field_data["sticky"], _("false"))
                        if p == pref_pub:
                                set_value(field_data["preferred"], _("true"))
                        else:
                                set_value(field_data["preferred"], _("false"))
                        if not p.disabled:
                                set_value(field_data["enabled"], _("true"))
                        else:
                                set_value(field_data["enabled"], _("false"))


                        # Only show the selected repository's information in
                        # summary view.
                        r = p.selected_repository

                        # Update field_data for each origin and output
                        # a publisher record in our desired format.
                        for uri in r.origins:
                                # XXX get the real origin status
                                if r._is_system_repo(uri):
                                        set_value(field_data["type"],
                                            _("system"))
                                else:
                                        set_value(field_data["type"],
                                            _("origin"))
                                set_value(field_data["status"], _("online"))
                                set_value(field_data["uri"], str(uri))
                                values = map(get_value,
                                             sorted(filter(filter_func,
                                             field_data.values()), sort_fields))
                                msg(fmt % tuple(values))
                        # Update field_data for each mirror and output
                        # a publisher record in our desired format.
                        for uri in r.mirrors:
                                # XXX get the real mirror status
                                set_value(field_data["type"], _("mirror"))
                                set_value(field_data["status"], _("online"))
                                set_value(field_data["uri"], str(uri))
                                values = map(get_value,
                                             sorted(filter(filter_func,
                                             field_data.values()), sort_fields))
                                msg(fmt % tuple(values))
        else:
                def display_ssl_info(uri):
                        retcode = EXIT_OK
                        c = get_cert_info(uri.ssl_cert)
                        msg(_("              SSL Key:"), uri.ssl_key)
                        msg(_("             SSL Cert:"), uri.ssl_cert)

                        if not c:
                                return retcode

                        if c["errors"]:
                                retcode = EXIT_OOPS

                        for e in c["errors"]:
                                logger.error("\n" + str(e) + "\n")

                        if c["valid"]:
                                msg(_(" Cert. Effective Date:"),
                                    c["info"]["effective"])
                                msg(_("Cert. Expiration Date:"),
                                    c["info"]["expiration"])
                        return retcode

                def display_repository(r):
                        retcode = 0
                        for uri in r.origins:
                                if r._is_system_repo(uri):
                                        msg(_("           System URI:"), uri)
                                        msg(_("          Socket Path:"),
                                            uri.socket_path)
                                else:
                                        msg(_("           Origin URI:"), uri)
                                rval = display_ssl_info(uri)
                                if rval == 1:
                                        retcode = EXIT_PARTIAL

                        for uri in r.mirrors:
                                msg(_("           Mirror URI:"), uri)
                                rval = display_ssl_info(uri)
                                if rval == 1:
                                        retcode = EXIT_PARTIAL
                        return retcode

                for name in pargs:
                        # detailed print
                        pub = api_inst.get_publisher(prefix=name, alias=name)
                        dt = api_inst.get_publisher_last_update_time(pub.prefix)
                        if dt:
                                dt = dt.strftime("%c")

                        msg("")
                        msg(_("            Publisher:"), pub.prefix)
                        msg(_("                Alias:"), pub.alias)

                        for r in pub.repositories:
                                rval = display_repository(r)
                                if rval != 0:
                                        # There was an error in displaying some
                                        # of the information about a repository.
                                        # However, continue on.
                                        retcode = rval

                        msg(_("          Client UUID:"), pub.client_uuid)
                        msg(_("      Catalog Updated:"), dt)
                        if pub.disabled:
                                msg(_("              Enabled:"), _("No"))
                        else:
                                msg(_("              Enabled:"), _("Yes"))
        return retcode

def property_set(img, args):
        """pkg set-property propname propvalue"""

        # ensure no options are passed in
        opts, pargs = getopt.getopt(args, "")
        try:
                propname, propvalue = pargs
        except ValueError:
                usage(_("requires a property name and value"),
                    cmd="set-property")

        if propname == "preferred-publisher":
                error(_("set-publisher must be used to change the preferred "
                    "publisher"), cmd="set-property")
                return EXIT_OOPS

        try:
                img.set_property(propname, propvalue)
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception
                # will be printed on the same line as the spinner.
                error("\n" + str(e), cmd="set-property")
                return EXIT_OOPS
        return EXIT_OK

def property_unset(img, args):
        """pkg unset-property propname ..."""

        # is this an existing property in our image?
        # if so, delete it
        # if not, error

        # ensure no options are passed in
        opts, pargs = getopt.getopt(args, "")
        if not pargs:
                usage(_("requires at least one property name"),
                    cmd="unset-property")

        for p in pargs:
                if p == "preferred-publisher":
                        error(_("set-publisher must be used to change the "
                            "preferred publisher"), cmd="unset-property")
                        return EXIT_OOPS

                try:
                        img.delete_property(p)
                except KeyError:
                        error(_("no such property: %s") % p,
                            cmd="unset-property")
                        return EXIT_OOPS
                except api_errors.PermissionsException, e:
                        # Prepend a newline because otherwise the exception
                        # will be printed on the same line as the spinner.
                        error("\n" + str(e), cmd="unset-property")
                        return EXIT_OOPS

        return EXIT_OK

def property_list(img, args):
        """pkg property [-H] [propname ...]"""
        omit_headers = False

        opts, pargs = getopt.getopt(args, "H")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        for p in pargs:
                if not img.has_property(p):
                        error(_("property: no such property: %s") % p)
                        return EXIT_OOPS

        if not pargs:
                pargs = list(img.properties())

        width = max(max([len(p) for p in pargs]), 8)
        fmt = "%%-%ss %%s" % width
        if not omit_headers:
                msg(fmt % ("PROPERTY", "VALUE"))

        for p in pargs:
                msg(fmt % (p, img.get_property(p)))

        return EXIT_OK

def variant_list(img, args):
        """pkg variant [-H] [<variant_spec>]"""

        omit_headers = False

        opts, pargs = getopt.getopt(args, "H")

        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        variants = img.get_variants()

        for p in pargs:
                if p not in variants:
                        error(_("no such variant: %s") % p, cmd="variant")
                        return EXIT_OOPS

        if not pargs:
                pargs = variants.keys()

        width = max(max([len(p) for p in pargs]), 8)
        fmt = "%%-%ss %%s" % width
        if not omit_headers:
                msg(fmt % ("VARIANT", "VALUE"))

        for p in pargs:
                msg(fmt % (p, variants[p]))

        return EXIT_OK

def facet_list(img, args):
        """pkg facet [-H] [<facet_spec>]"""

        omit_headers = False

        opts, pargs = getopt.getopt(args, "H")

        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        facets = img.get_facets()

        for i, p in enumerate(pargs[:]):
                if not p.startswith("facet."):
                        pargs[i] = "facet." + p

        if not pargs:
                pargs = facets.keys()

        if pargs:
                width = max(max([len(p) for p in pargs]), 8)
        else:
                width = 8

        fmt = "%%-%ss %%s" % width

        if not omit_headers:
                msg(fmt % ("FACETS", "VALUE"))

        for p in pargs:
                msg(fmt % (p, facets[p]))

        return EXIT_OK

def image_create(args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial publisher for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        force = False
        imgtype = IMG_TYPE_USER
        is_zone = False
        add_mirrors = set()
        add_origins = set()
        pub_name = None
        pub_url = None
        refresh_allowed = True
        sock_path = None
        ssl_key = None
        ssl_cert = None
        sys_repo = False
        sys_repo_uri = None
        variants = {}
        facets = pkg.facet.Facets()

        opts, pargs = getopt.getopt(args, "fFPUza:g:m:p:k:c:",
            ["force", "full", "partial", "user", "zone", "authority=", "facet=",
                "mirror=", "origin=", "publisher=", "no-refresh", "variant=",
                "system-repo", "socket-path="])

        for opt, arg in opts:
                # -a is deprecated and will be removed at a future date.
                if opt in ("-a", "-p", "--publisher"):
                        pub_url = None
                        try:
                                pub_name, pub_url = arg.split("=", 1)
                        except ValueError:
                                pub_name = None
                                pub_url = arg
                elif opt == "-c":
                        ssl_cert = arg
                elif opt == "-f" or opt == "--force":
                        force = True
                elif opt in ("-g", "--origin"):
                        add_origins.add(arg)
                elif opt == "-k":
                        ssl_key = arg
                elif opt in ("-m", "--mirror"):
                        add_mirrors.add(arg)
                elif opt == "-z" or opt == "--zone":
                        is_zone = True
                        imgtype = IMG_TYPE_ENTIRE
                elif opt == "-F" or opt == "--full":
                        imgtype = IMG_TYPE_ENTIRE
                elif opt == "-P" or opt == "--partial":
                        imgtype = IMG_TYPE_PARTIAL
                elif opt == "-U" or opt == "--user":
                        imgtype = IMG_TYPE_USER
                elif opt == "--system-repo":
                        sys_repo = True
                elif opt == "--socket-path":
                        sock_path = arg
                elif opt == "--no-refresh":
                        refresh_allowed = False
                elif opt == "--variant":
                        try:
                                v_name, v_value = arg.split("=", 1)
                                if not v_name.startswith("variant."):
                                        v_name = "variant.%s" % v_name
                        except ValueError:
                                usage(_("variant arguments must be of the "
                                    "form '<name>=<value>'."),
                                    cmd="image-create")
                        variants[v_name] = v_value
                if opt == "--facet":
                        allow = { "TRUE":True, "FALSE":False }
                        f_name, f_value = arg.split("=", 1)
                        if not f_name.startswith("facet."):
                                f_name = "facet.%s" % f_name
                        if f_value.upper() not in allow:
                                usage(_("Facet arguments must be"
                                    "form 'facet..=[True|False]'"),
                                    cmd="image-create")
                        facets[f_name] = allow[f_value.upper()]

        if not pargs:
                usage(_("an image directory path must be specified"),
                    cmd="image-create")
        elif len(pargs) > 1:
                usage(_("only one image directory path may be specified"),
                    cmd="image-create")
        image_dir = pargs[0]

        if not pub_name and not pub_url:
                usage(_("publisher argument must be of the form "
                    "'<prefix>=<uri> or '<uri>''."), cmd="image-create")
        elif not pub_name and not refresh_allowed:
                usage(_("--no-refresh cannot be used with -p unless a "
                    "publisher prefix is provided."))

        if sys_repo and sock_path:
                repo_uri = None
                sys_repo_uri = pub_url
        elif not refresh_allowed and pub_url:
                # Auto-config can't be done if refresh isn't allowed, so treat
                # this as a manual configuration case.
                add_origins.add(pub_url)
                repo_uri = None
        else:
                repo_uri = pub_url

        # Get sanitized SSL Cert/Key input values.
        ssl_cert, ssl_key = _get_ssl_cert_key(image_dir, is_zone, ssl_cert,
            ssl_key)

        global __img
        try:
                progtrack = get_tracker()
                api_inst = api.image_create(PKG_CLIENT_NAME, CLIENT_API_VERSION,
                    image_dir, imgtype, is_zone, facets=facets, force=force,
                    mirrors=add_mirrors, origins=add_origins, prefix=pub_name,
                    progtrack=progtrack, refresh_allowed=refresh_allowed,
                    socket_path=sock_path, ssl_cert=ssl_cert,
                    ssl_key=ssl_key, sys_repo=sys_repo_uri, repo_uri=repo_uri,
                    variants=variants)
                __img = api_inst.img
        except api_errors.InvalidDepotResponseException, e:
                # Ensure messages are displayed after the spinner.
                logger.error("\n")
                error(_("The URI '%(pub_url)s' does not appear to point to a "
                    "valid pkg repository.\nPlease check the repository's "
                    "location and the client's network configuration."
                    "\nAdditional details:\n\n%(error)s") %
                    { "pub_url": pub_url, "error": e },
                    cmd="image-create")
                print_proxy_config()
                return EXIT_OOPS
        except api_errors.CatalogRefreshException, cre:
                # Ensure messages are displayed after the spinner.
                error("", cmd="image-create")
                if display_catalog_failures(cre) == 0:
                        return EXIT_OOPS
                else:
                        return EXIT_PARTIAL
        except api_errors.ApiException, e:
                error(str(e), cmd="image-create")
                return EXIT_OOPS
        return EXIT_OK

def rebuild_index(img, pargs):
        """pkg rebuild-index

        Forcibly rebuild the search indexes. Will remove existing indexes
        and build new ones from scratch."""

        if pargs:
                usage(_("command does not take operands ('%s')") % \
                    " ".join(pargs), cmd="rebuild-index")

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        try:
                api_inst.rebuild_search_index()
        except api_errors.CorruptedIndexException:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE, cmd="rebuild-index")
                return EXIT_OOPS
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE,
                    cmd="rebuild-index")
                return EXIT_OOPS
        except api_errors.MainDictParsingException, e:
                error(str(e), cmd="rebuild-index")
                return EXIT_OOPS
        else:
                return EXIT_OK

def history_list(img, args):
        """Display history about the current image.
        """

        omit_headers = False
        long_format = False
        display_limit = None    # Infinite

        opts, pargs = getopt.getopt(args, "Hln:")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                elif opt == "-l":
                        long_format = True
                elif opt == "-n":
                        try:
                                display_limit = int(arg)
                        except ValueError:
                                logger.error(
                                    _("Argument to -n must be numeric"))
                                return EXIT_BADOPT

                        if display_limit <= 0:
                                logger.error(
                                    _("Argument to -n must be positive"))
                                return EXIT_BADOPT

        if omit_headers and long_format:
                usage(_("-H and -l may not be combined"), cmd="history")

        if not long_format:
                if not omit_headers:
                        msg("%-19s %-25s %-15s %s" % (_("TIME"),
                            _("OPERATION"), _("CLIENT"), _("OUTCOME")))

        if not os.path.exists(img.history.path):
                # Nothing to display.
                return EXIT_OK

        if display_limit:
                n = -display_limit
                entries = sorted(os.listdir(img.history.path))[n:]
        else:
                entries = sorted(os.listdir(img.history.path))

        for entry in entries:
                # Load the history entry.
                try:
                        he = history.History(root_dir=img.history.root_dir,
                            filename=entry)
                except api_errors.PermissionsException, e:
                        error(e, cmd="history")
                        return EXIT_OOPS
                except history.HistoryLoadException, e:
                        if e.parse_failure:
                                # Ignore corrupt entries.
                                continue
                        raise

                # Retrieve and format some of the data shared between each
                # output format.
                start_time = misc.timestamp_to_time(
                    he.operation_start_time)
                start_time = datetime.datetime.fromtimestamp(
                    start_time).isoformat()

                res = he.operation_result
                if len(res) > 1:
                        outcome = "%s (%s)" % (_(res[0]), _(res[1]))
                else:
                        outcome = _(res[0])

                if long_format:
                        data = []
                        data.append(("Operation", he.operation_name))

                        data.append(("Outcome", outcome))
                        data.append(("Client", he.client_name))
                        data.append(("Version", he.client_version))

                        data.append(("User", "%s (%s)" % \
                            (he.operation_username, he.operation_userid)))

                        data.append(("Start Time", start_time))

                        end_time = misc.timestamp_to_time(
                            he.operation_end_time)
                        end_time = datetime.datetime.fromtimestamp(
                            end_time).isoformat()
                        data.append(("End Time", end_time))

                        data.append(("Command", " ".join(he.client_args)))

                        state = he.operation_start_state
                        if state:
                                data.append(("Start State", "\n" + state))

                        state = he.operation_end_state
                        if state:
                                data.append(("End State", "\n" + state))

                        errors = "\n".join(he.operation_errors)
                        if errors:
                                data.append(("Errors", "\n" + errors))

                        for field, value in data:
                                msg("%15s: %s" % (_(field), value))

                        # Separate log entries with a blank line.
                        msg("")
                else:
                        msg("%-19s %-25s %-15s %s" % (start_time,
                            he.operation_name, he.client_name, outcome))

        return EXIT_OK

def history_purge(img, pargs):
        """Purge image history"""
        ret_code = img.history.purge()
        if ret_code == EXIT_OK:
                msg(_("History purged."))
        return ret_code

def print_proxy_config():
        """If the user has configured http_proxy or https_proxy in the
        environment, print out the values.  Some transport errors are
        not debuggable without this information handy."""

        http_proxy = os.environ.get("http_proxy", None)
        https_proxy = os.environ.get("https_proxy", None)

        if not http_proxy and not https_proxy:
                return

        logger.error(_("\nThe following proxy configuration is set in the"
            " environment:\n"))
        if http_proxy:
                logger.error(_("http_proxy: %s\n") % http_proxy)
        if https_proxy:
                logger.error(_("https_proxy: %s\n") % https_proxy)


# To allow exception handler access to the image.
__img = None
orig_cwd = None

def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        global __img
        global orig_cwd

        try:
                orig_cwd = os.getcwd()
        except OSError, e:
                try:
                        orig_cwd = os.environ["PWD"]
                        if not orig_cwd or orig_cwd[0] != "/":
                                orig_cwd = None
                except KeyError:
                        orig_cwd = None

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "R:D:?",
                    ["debug=", "help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        show_usage = False
        for opt, arg in opts:
                if opt == "-D" or opt == "--debug":
                        if arg in ["plan", "transport"]:
                                key = arg
                                value = "True"
                        else:
                                try:
                                        key, value = arg.split("=", 1)
                                except (AttributeError, ValueError):
                                        usage(_("%(opt)s takes argument of form "
                                            "name=value, not %(arg)s") % { "opt":  opt,
                                            "arg": arg })
                        DebugValues.set_value(key, value)
                elif opt == "-R":
                        mydir = arg
                elif opt in ("--help", "-?"):
                        show_usage = True

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        show_usage = True

        if show_usage:
                usage(retcode=0, full=True)
        elif not subcommand:
                usage(_("no subcommand specified"))

        # This call only affects sockets created by Python.  The transport
        # framework uses the defaults in global_settings, which may be
        # overridden in the environment.  The default socket module should
        # only be used in rare cases by ancillary code, making it safe to
        # code the value here, at least for now.
        socket.setdefaulttimeout(30) # in secs

        if subcommand == "image-create":
                if "mydir" in locals():
                        usage(_("-R not allowed for %s subcommand") %
                              subcommand)
                try:
                        ret = image_create(pargs)
                except getopt.GetoptError, e:
                        if e.opt in ("help", "?"):
                                usage(full=True)
                        usage(_("illegal option -- %s") % e.opt, cmd=subcommand)
                return ret
        elif subcommand == "version":
                if "mydir" in locals():
                        usage(_("-R not allowed for %s subcommand") %
                              subcommand)
                if pargs:
                        usage(_("version: command does not take operands " \
                            "('%s')") % " ".join(pargs))
                msg(pkg.VERSION)
                return EXIT_OK

        provided_image_dir = True
        pkg_image_used = False

        if "mydir" not in locals():
                try:
                        mydir = os.environ["PKG_IMAGE"]
                        pkg_image_used = True
                except KeyError:
                        provided_image_dir = False
                        mydir = orig_cwd

        if mydir == None:
                error(_("Could not find image.  Use the -R option or set "
                    "$PKG_IMAGE to point\nto an image, or change the working "
                    "directory to one inside the image."))
                return EXIT_OOPS

        try:
                __img = img = image.Image(mydir, provided_image_dir)
        except api_errors.ImageNotFoundException, e:
                if e.user_specified:
                        m = "No image rooted at '%s'"
                        if pkg_image_used:
                                m += " (set by $PKG_IMAGE)"
                        error(_(m) % e.user_dir)
                else:
                        error(_("No image found."))
                return EXIT_OOPS
        except api_errors.PermissionsException, e:
                error(e)
                return EXIT_OOPS

        cmds = {
                "authority"        : publisher_list,
                "change-facet"     : change_facet,
                "change-variant"   : change_variant,
                "contents"         : list_contents,
                "facet"            : facet_list,
                "fix"              : fix_image,
                "freeze"           : freeze,
                "history"          : history_list,
                "image-update"     : image_update,
                "info"             : info,
                "install"          : install,
                "list"             : list_inventory,
                "property"         : property_list,
                "publisher"        : publisher_list,
                "purge-history"    : history_purge,
                "rebuild-index"    : rebuild_index,
                "refresh"          : publisher_refresh,
                "search"           : search,
                "set-authority"    : publisher_set,
                "set-property"     : property_set,
                "set-publisher"    : publisher_set,
                "unfreeze"         : unfreeze,
                "uninstall"        : uninstall,
                "unset-authority"  : publisher_unset,
                "unset-property"   : property_unset,
                "unset-publisher"  : publisher_unset,
                "variant"          : variant_list,
                "verify"           : verify_image
               }

        func = cmds.get(subcommand, None)
        if not func:
                usage(_("unknown subcommand '%s'") % subcommand)
        try:
                return func(img, pargs)

        except getopt.GetoptError, e:
                if e.opt in ("help", "?"):
                        usage(full=True)
                usage(_("illegal option -- %s") % e.opt, cmd=subcommand)

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
def handle_errors(func, non_wrap_print=True, *args, **kwargs):
        traceback_str = _("\n\nThis is an internal error.  Please let the "
            "developers know about this\nproblem by filing a bug at "
            "http://defect.opensolaris.org and including the\nabove "
            "traceback and this message.  The version of pkg(5) is "
            "'%s'.") % pkg.VERSION
        try:
                # Out of memory errors can be raised as EnvironmentErrors with
                # an errno of ENOMEM, so in order to handle those exceptions
                # with other errnos, we nest this try block and have the outer
                # one handle the other instances.
                try:
                        __ret = func(*args, **kwargs)
                except (MemoryError, EnvironmentError), __e:
                        if isinstance(__e, EnvironmentError) and \
                            __e.errno != errno.ENOMEM:
                                raise
                        if __img:
                                __img.history.abort(RESULT_FAILED_OUTOFMEMORY)
                        error("\n" + misc.out_of_memory())
                        __ret = EXIT_OOPS
        except SystemExit, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_UNKNOWN)
                raise __e
        except (PipeError, KeyboardInterrupt):
                if __img:
                        __img.history.abort(RESULT_CANCELED)
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = EXIT_OOPS
        except api_errors.CertificateError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_CONFIGURATION)
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.PublisherError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_BAD_REQUEST)
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.ImageLockedError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_LOCKED)
                error(__e)
                __ret = EXIT_LOCKED
        except api_errors.TransportError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                logger.error(_("\nErrors were encountered while attempting "
                    "to retrieve package or file data for\nthe requested "
                    "operation."))
                logger.error(_("Details follow:\n\n%s") % __e)
                print_proxy_config()
                __ret = EXIT_OOPS
        except api_errors.InvalidCatalogFile, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_STORAGE)
                logger.error(_("""
An error was encountered while attempting to read image state information
to perform the requested operation.  Details follow:\n\n%s""") % __e)
                __ret = EXIT_OOPS
        except api_errors.InvalidDepotResponseException, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                logger.error(_("\nUnable to contact a valid package "
                    "repository. This may be due to a problem with the "
                    "repository, network misconfiguration, or an incorrect "
                    "pkg client configuration.  Please verify the client's "
                    "network configuration and repository's location."))
                logger.error(_("\nAdditional details:\n\n%s") % __e)
                print_proxy_config()
                __ret = EXIT_OOPS
        except history.HistoryLoadException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if __img:
                        __img.history.clear()
                error(_("An error was encountered while attempting to load "
                    "history information\nabout past client operations."))
                error(__e)
                __ret = EXIT_OOPS
        except history.HistoryStoreException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if __img:
                        __img.history.clear()
                error(_("An error was encountered while attempting to store "
                    "information about the\ncurrent operation in client "
                    "history."))
                error(__e)
                __ret = EXIT_OOPS
        except history.HistoryPurgeException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if __img:
                        __img.history.clear()
                error(_("An error was encountered while attempting to purge "
                    "client history."))
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.VersionException, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_UNKNOWN)
                error(_("The pkg command appears out of sync with the libraries"
                    " provided\nby pkg:/package/pkg. The client version is "
                    "%(client)s while the library\nAPI version is %(api)s.") %
                    {'client': __e.received_version,
                     'api': __e.expected_version
                    })
                __ret = EXIT_OOPS
        except api_errors.WrapSuccessfulIndexingException, __e:
                __ret = EXIT_OK
        except api_errors.WrapIndexingException, __e:
                def _wrapper():
                        raise __e.wrapped
                __ret = handle_errors(_wrapper, non_wrap_print=False)
                s = ""
                if __ret == 99:
                        s += _("\n%s%s") % (__e, traceback_str)

                s += _("\n\nDespite the error while indexing, the "
                    "image-update, install, or uninstall\nhas completed "
                    "successfuly.")
                error(s)
        except api_errors.ReadOnlyFileSystemException, __e:
                __ret = EXIT_OOPS
        except:
                if __img:
                        __img.history.abort(RESULT_FAILED_UNKNOWN)
                if non_wrap_print:
                        traceback.print_exc()
                        error(traceback_str)
                __ret = 99
        return __ret

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale")

        # Make all warnings be errors.
        warnings.simplefilter('error')

        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
