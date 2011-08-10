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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.
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

try:
        import calendar
        import collections
        import datetime
        import errno
        import fnmatch
        import getopt
        import gettext
        import glob
        import itertools
        import simplejson as json
        import locale
        import logging
        import os
        import socket
        import sys
        import textwrap
        import time
        import traceback

        import pkg
        import pkg.actions as actions
        import pkg.client.api as api
        import pkg.client.api_errors as api_errors
        import pkg.client.bootenv as bootenv
        import pkg.client.history as history
        import pkg.client.progress as progress
        import pkg.client.linkedimage as li
        import pkg.client.publisher as publisher
        import pkg.fmri as fmri
        import pkg.misc as misc
        import pkg.version as version

        from pkg.client import global_settings
        from pkg.client.api import IMG_TYPE_ENTIRE, IMG_TYPE_PARTIAL, \
            IMG_TYPE_USER
        from pkg.client.debugvalues import DebugValues
        from pkg.client.history import (RESULT_CANCELED,
            RESULT_FAILED_BAD_REQUEST, RESULT_FAILED_CONFIGURATION,
            RESULT_FAILED_LOCKED, RESULT_FAILED_STORAGE,
            RESULT_FAILED_TRANSPORT, RESULT_FAILED_UNKNOWN,
            RESULT_FAILED_OUTOFMEMORY)
        from pkg.client.pkgdefs import *
        from pkg.misc import EmptyI, msg, PipeError
except KeyboardInterrupt:
        import sys
        sys.exit(1)

CLIENT_API_VERSION = 66
PKG_CLIENT_NAME = "pkg"

JUST_UNKNOWN = 0
JUST_LEFT = -1
JUST_RIGHT = 1

logger = global_settings.logger

valid_special_attrs = ["action.hash", "action.key", "action.name", "action.raw"]

valid_special_prefixes = ["action."]

def format_update_error(e):
        # This message is displayed to the user whenever an
        # ImageFormatUpdateNeeded exception is encountered.
        logger.error("\n")
        logger.error(str(e))
        logger.error(_("To continue, execute 'pkg update-format' as a "
            "privileged user and then try again.  Please note that updating "
            "the format of the image will render it unusable with older "
            "versions of the pkg(5) system."))

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if not isinstance(text, basestring):
                # Assume it's an object that can be stringified.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        if cmd:
                text_nows = "%s: %s" % (cmd, text_nows)
                pkg_cmd = "pkg "
        else:
                pkg_cmd = "pkg: "

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        logger.error(ws + pkg_cmd + text_nows)

def usage(usage_error=None, cmd=None, retcode=EXIT_BADOPT, full=False):
        """Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        if usage_error:
                error(usage_error, cmd=cmd)

        basic_usage = {}
        adv_usage = {}

        basic_cmds = ["refresh", "install", "uninstall", "update", "list",
            "version"]

        basic_usage["install"] = _(
            "[-nvq] [-g path_or_uri ...] [--accept] [--licenses]\n"
            "            [--no-be-activate] [--no-index] [--no-refresh] [--deny-new-be |\n"
            "            --require-new-be] [--be-name name] [--reject pkg_fmri_pattern ... ]\n"
            "            pkg_fmri_pattern ...")
        basic_usage["uninstall"] = _(
            "[-nvq] [--no-be-activate] [--no-index] [--deny-new-be |\n"
            "            --require-new-be] [--be-name name] pkg_fmri_pattern ...")
        basic_usage["update"] = _(
            "[-fnvq] [-g path_or_uri ...] [--accept] [--licenses]\n"
            "            [--no-be-activate] [--no-index] [--no-refresh] [--deny-new-be |\n"
            "            --require-new-be] [--be-name name] [--reject pkg_fmri_pattern ...]\n"
            "            [pkg_fmri_pattern ...]")
        basic_usage["list"] = _(
            "[-Hafnsuv] [-g path_or_uri ...] [--no-refresh]\n"
            "            [pkg_fmri_pattern ...]")
        basic_usage["refresh"] = _("[--full] [publisher ...]")
        basic_usage["version"] = ""

        advanced_cmds = [
            "info",
            "contents",
            "search",
            "",
            "verify",
            "fix",
            "revert",
            "",
            "mediator",
            "set-mediator",
            "unset-mediator",
            "",
            "variant",
            "change-variant",
            "",
            "facet",
            "change-facet",
            "",
            "avoid",
            "unavoid",
            "",
            "freeze",
            "unfreeze",
            "",
            "property",
            "set-property",
            "add-property-value",
            "remove-property-value",
            "unset-property",
            "",
            "publisher",
            "set-publisher",
            "unset-publisher",
            "",
            "history",
            "purge-history",
            "",
            "rebuild-index",
            "update-format",
            "image-create",
            "",
            "attach-linked",
            "detach-linked",
            "list-linked",
            "audit-linked",
            "sync-linked",
            "property-linked",
        ]

        adv_usage["info"] = \
            _("[-lr] [-g path_or_uri ...] [--license] [pkg_fmri_pattern ...]")
        adv_usage["contents"] = _(
            "[-Hmr] [-a attribute=pattern ...] [-g path_or_uri ...]\n"
            "            [-o attribute ...] [-s sort_key] [-t action_type ...]\n"
            "            [pkg_fmri_pattern ...]")
        adv_usage["search"] = _(
            "[-HIaflpr] [-o attribute ...] [-s repo_uri] query")

        adv_usage["verify"] = _("[-Hqv] [pkg_fmri_pattern ...]")
        adv_usage["fix"] = _("[--accept] [--licenses] [pkg_fmri_pattern ...]")
        adv_usage["revert"] = _(
            "[-nv] [--no-be-activate] [--be-name name] [--deny-new-be |\n"
            "            --require-new-be] (--tagged tag-name ... | path-to-file ...)")

        adv_usage["image-create"] = _(
            "[-FPUfz] [--force] [--full|--partial|--user] [--zone]\n"
            "            [-k ssl_key] [-c ssl_cert] [--no-refresh]\n"
            "            [--variant <variant_spec>=<instance> ...]\n"
            "            [-g uri|--origin=uri ...] [-m uri|--mirror=uri ...]\n"
            "            [--facet <facet_spec>=(True|False) ...]\n"
            "            [(-p|--publisher) [<name>=]<repo_uri>] dir")
        adv_usage["change-variant"] = _(
            "[-nvq] [-g path_or_uri ...] [--accept] [--licenses]\n"
            "            [--no-be-activate] [--deny-new-be | --require-new-be]\n"
            "            [--be-name name] <variant_spec>=<instance> ...")

        adv_usage["change-facet"] = _(
            "[-nvq] [-g path_or_uri ...] [--accept] [--licenses]\n"
            "            [--no-be-activate] [--deny-new-be | --require-new-be]\n"
            "            [--be-name name] <facet_spec>=[True|False|None] ...")

        adv_usage["mediator"] = _("[-aH] [-F format] [<mediator> ...]")
        adv_usage["set-mediator"] = _(
            "[-nv] [-I <implementation>] [-V <version>]\n"
            "            [--no-be-activate] [--deny-new-be | --require-new-be]\n"
            "            [--be-name name] <mediator> ...")
        adv_usage["unset-mediator"] = _("[-nvIV] [--no-be-activate]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            <mediator> ...")

        adv_usage["variant"] = _("[-H] [<variant_spec>]")
        adv_usage["facet"] = ("[-H] [<facet_spec>]")
        adv_usage["avoid"] = _("[pkg_fmri_pattern] ...")
        adv_usage["unavoid"] = _("[pkg_fmri_pattern] ...")
        adv_usage["freeze"] = _("[-n] [-c reason] [pkg_fmri_pattern] ...")
        adv_usage["unfreeze"] = _("[-n] [pkg_name_pattern] ...")
        adv_usage["set-property"] = _("propname propvalue")
        adv_usage["add-property-value"] = _("propname propvalue")
        adv_usage["remove-property-value"] = _("propname propvalue")
        adv_usage["unset-property"] = _("propname ...")
        adv_usage["property"] = _("[-H] [propname ...]")

        adv_usage["set-publisher"] = _("[-Ped] [-k ssl_key] [-c ssl_cert]\n"
            "            [-g origin_to_add|--add-origin=origin_to_add ...]\n"
            "            [-G origin_to_remove|--remove-origin=origin_to_remove ...]\n"
            "            [-m mirror_to_add|--add-mirror=mirror_to_add ...]\n"
            "            [-M mirror_to_remove|--remove-mirror=mirror_to_remove ...]\n"
            "            [-p repo_uri] [--enable] [--disable] [--no-refresh]\n"
            "            [--reset-uuid] [--non-sticky] [--sticky]\n"
            "            [--search-after=publisher]\n"
            "            [--search-before=publisher]\n"
            "            [--search-first]\n"
            "            [--approve-ca-cert=path_to_CA]\n"
            "            [--revoke-ca-cert=hash_of_CA_to_revoke]\n"
            "            [--unset-ca-cert=hash_of_CA_to_unset]\n"
            "            [--set-property name_of_property=value]\n"
            "            [--add-property-value name_of_property=value_to_add]\n"
            "            [--remove-property-value name_of_property=value_to_remove]\n"
            "            [--unset-property name_of_property_to_delete]\n"
            "            [publisher]")

        adv_usage["unset-publisher"] = _("publisher ...")
        adv_usage["publisher"] = _("[-HPn] [publisher ...]")
        adv_usage["history"] = _("[-Hl] [-t [time|time-time],...] [-n number] [-o column,...]")
        adv_usage["purge-history"] = ""
        adv_usage["rebuild-index"] = ""
        adv_usage["update-format"] = ""

        adv_usage["list-linked"] = _("-H")
        adv_usage["attach-linked"] = _(
            "[-fnvq] [--accept] [--licenses] [--no-index]\n"
            "            [--no-refresh] [--no-pkg-updates] [--linked-md-only]\n"
            "            [--allow-relink]\n"
            "            [--prop-linked <propname>=<propvalue> ...]\n"
            "            (-c|-p) <li-name> <dir>")
        adv_usage["detach-linked"] = _(
            "[-fnvq] [-a|-l <li-name>] [--linked-md-only]")
        adv_usage["property-linked"] = _("[-H] [-l <li-name>] [propname ...]")
        adv_usage["audit-linked"] = _("[-a|-l <li-name>]")
        adv_usage["sync-linked"] = _(
            "[-nvq] [--accept] [--licenses] [--no-index]\n"
            "            [--no-refresh] [--no-parent-sync] [--no-pkg-updates]\n"
            "            [--linked-md-only] [-a|-l <name>]")
        adv_usage["set-property-linked"] = _(
            "[-nvq] [--accept] [--licenses] [--no-index] [--no-refresh]\n"
            "            [--no-parent-sync] [--no-pkg-updates]\n"
            "            [--linked-md-only] <propname>=<propvalue> ...")

        def print_cmds(cmd_list, cmd_dic):
                for cmd in cmd_list:
                        if cmd is "":
                                logger.error("")
                        else:
                                if cmd not in cmd_dic:
                                        # this should never happen - callers
                                        # should check for valid subcommands
                                        # before calling usage(..)
                                        raise ValueError(
                                            "Unable to find usage str for %s" %
                                            cmd)
                                usage = cmd_dic[cmd]
                                if usage is not "":
                                        logger.error(
                                            "        pkg %(cmd)s %(usage)s" %
                                            locals())
                                else:
                                        logger.error("        pkg %s" % cmd)
        if not full and cmd:
                logger.error("Usage:")
                combined = {}
                combined.update(basic_usage)
                combined.update(adv_usage)
                print_cmds([cmd], combined)
                sys.exit(retcode)

        elif not full:
                # The full usage message isn't desired.
                logger.error(_("Try `pkg --help or -?' for more information."))
                sys.exit(retcode)

        logger.error(_("""\
Usage:
        pkg [options] command [cmd_options] [operands]
"""))
        logger.error(_("Basic subcommands:"))
        print_cmds(basic_cmds, basic_usage)

        logger.error(_("\nAdvanced subcommands:"))
        print_cmds(advanced_cmds, adv_usage)

        logger.error(_("""
Options:
        -R dir
        --help or -?

Environment:
        PKG_IMAGE"""))
        sys.exit(retcode)

def get_fmri_args(api_inst, pargs, cmd=None):
        """ Convenience routine to check that input args are valid fmris. """

        res = []
        errors = []
        for pat, err, pfmri, matcher in api_inst.parse_fmri_patterns(pargs):
                if not err:
                        res.append((pat, err, pfmri, matcher))
                        continue
                if isinstance(err, version.VersionError):
                        # For version errors, include the pattern so
                        # that the user understands why it failed.
                        errors.append("Illegal FMRI '%s': %s" % (pat,
                            err))
                else:
                        # Including the pattern is redundant for other
                        # exceptions.
                        errors.append(err)
        if errors:
                error("\n".join(str(e) for e in errors), cmd=cmd)
        return len(errors) == 0, res

def list_inventory(op, api_inst, pargs,
    li_parent_sync, list_all, list_installed_newest, list_newest,
    list_upgradable, omit_headers, origins, refresh_catalogs, summary,
    verbose):
        """List packages."""

        api_inst.progresstracker = get_tracker(quiet=omit_headers)

        variants = False
        pkg_list = api.ImageInterface.LIST_INSTALLED
        if list_all:
                variants = True
                pkg_list = api.ImageInterface.LIST_ALL
        elif list_installed_newest:
                pkg_list = api.ImageInterface.LIST_INSTALLED_NEWEST
        elif list_newest:
                pkg_list = api.ImageInterface.LIST_NEWEST
        elif list_upgradable:
                pkg_list = api.ImageInterface.LIST_UPGRADABLE

        if verbose:
                fmt_str = "%-76s %s"
        elif summary:
                fmt_str = "%-55s %s"
        else:
                fmt_str = "%-55s %-20s %s"

        # Each pattern in pats can be a partial or full FMRI, so
        # extract the individual components.  These patterns are
        # transformed here so that partial failure can be detected
        # when more than one pattern is provided.
        rval, res = get_fmri_args(api_inst, pargs, cmd=op)
        if not rval:
                return EXIT_OOPS

        api_inst.log_operation_start(op)
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
            [(api.PackageInfo.INSTALLED, "i")],
            [(api.PackageInfo.FROZEN, "f")],
            [
                (api.PackageInfo.OBSOLETE, "o"),
                (api.PackageInfo.RENAMED, "r")
            ],
        ]

        # Now get the matching list of packages and display it.
        found = False
        ppub = api_inst.get_highest_ranked_publisher()
        if ppub:
                ppub = ppub.prefix
        try:
                res = api_inst.get_pkg_list(pkg_list, patterns=pargs,
                    raise_unmatched=True, repos=origins, variants=variants)
                for pt, summ, cats, states, attrs in res:
                        found = True
                        if not omit_headers:
                                if verbose:
                                        msg(fmt_str %
                                            ("FMRI", "IFO"))
                                elif summary:
                                        msg(fmt_str %
                                            ("NAME (PUBLISHER)",
                                            "SUMMARY"))
                                else:
                                        msg(fmt_str %
                                            ("NAME (PUBLISHER)",
                                            "VERSION", "IFO"))
                                omit_headers = True

                        status = ""
                        for sentry in state_map:
                                for s, v in sentry:
                                        if s in states:
                                                st = v
                                                break
                                        else:
                                                st = "-"
                                status += st

                        pub, stem, ver = pt
                        if pub == ppub:
                                spub = ""
                        else:
                                spub = " (" + pub + ")"

                        # Display full FMRI for verbose case.
                        if verbose:
                                pfmri = "pkg://%s/%s@%s" % (pub, stem, ver)
                                msg(fmt_str % (pfmri, status))
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
                        msg(fmt_str % (pf, sver, status))

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
                error(e, cmd=op)
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
                            ", ".join(e.notfound), cmd=op)
                elif pkg_list == api.ImageInterface.LIST_INSTALLED_NEWEST:
                        error(_("no packages matching '%s' allowed by "
                            "installed incorporations, or image variants that "
                            "are known or installed") % \
                            ", ".join(e.notfound), cmd=op)
                        logger.error("Use -af to allow all versions.")
                elif pkg_list == api.ImageInterface.LIST_UPGRADABLE:
                        error(_("no packages matching '%s' are installed "
                            "and have newer versions available") % \
                            ", ".join(e.notfound), cmd=op)
                else:
                        error(_("no packages matching '%s' installed") % \
                            ", ".join(e.notfound), cmd=op)

                if found and e.notfound:
                        # Only some patterns matched.
                        api_inst.log_operation_end()
                        return EXIT_PARTIAL
                api_inst.log_operation_end(result=history.RESULT_NOTHING_TO_DO)
                return EXIT_OOPS

def get_tracker(parsable_version=None, quiet=False, verbose=0):
        if quiet:
                progresstracker = progress.QuietProgressTracker(
                    parsable_version=parsable_version)
        else:
                try:
                        progresstracker = \
                            progress.FancyUNIXProgressTracker(
                                parsable_version=parsable_version, quiet=quiet,
                                verbose=verbose)
                except progress.ProgressTrackerException:
                        progresstracker = progress.CommandLineProgressTracker(
                            parsable_version=parsable_version, quiet=quiet,
                            verbose=verbose)
        return progresstracker

def fix_image(api_inst, args):
        progresstracker = get_tracker(quiet=False)

        opts, pargs = getopt.getopt(args, "", ["accept", "licenses"])

        accept = show_licenses = False
        for opt, arg in opts:
                if opt == "--accept":
                        accept = True
                elif opt == "--licenses":
                        show_licenses = True

        # XXX fix should be part of pkg.client.api
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
                                entries.append((act, errors, warnings))

                        if not entries:
                                # Nothing to fix for this package.
                                continue

                        msg(_("Verifying: %(pkg_name)-50s %(result)7s") % {
                            "pkg_name": pfmri.get_pkg_stem(),
                            "result": _("ERROR") })

                        failed = []
                        for act, errors, warnings in entries:
                                if act:
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
                # Since BootEnv records the snapshot name in the image history,
                # we need to manage our own history start/end & exception
                # handling rather then delegating to <Image>.repair()
                api_inst.log_operation_start("fix")
                # Create a snapshot in case they want to roll back
                success = False
                try:
                        be = bootenv.BootEnv(img)
                        if be.exists():
                                msg(_("Created ZFS snapshot: %s") %
                                    be.snapshot_name)
                except RuntimeError:
                        # Error is printed by the BootEnv call.
                        be = bootenv.BootEnvNull(img)
                img.bootenv = be
                try:
                        success = img.repair(repairs, progresstracker,
                            accept=accept, show_licenses=show_licenses,
                            new_history_op=False)
                except (api_errors.InvalidPlanError,
                    api_errors.InvalidPackageErrors,
                    api_errors.ActionExecutionError,
                    api_errors.PermissionsException,
                    api_errors.SigningException,
                    api_errors.InvalidResourceLocation,
                    api_errors.ConflictingActionErrors), e:
                        logger.error(str(e))
                except api_errors.ImageFormatUpdateNeeded, e:
                        format_update_error(e)
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_CONFIGURATION)
                        return EXIT_OOPS
                except api_errors.PlanLicenseErrors, e:
                        error(_("The following packages require their "
                            "licenses to be accepted before they can be "
                            "repaired: "))
                        logger.error(str(e))
                        logger.error(_("To indicate that you agree to and "
                            "accept the terms of the licenses of the packages "
                            "listed above, use the --accept option.  To "
                            "display all of the related licenses, use the "
                            "--licenses option."))
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_CONSTRAINED)
                        return EXIT_LICENSE
                except api_errors.RebootNeededOnLiveImageException:
                        error(_("Requested \"fix\" operation would affect "
                            "files that cannot be modified in live image.\n"
                            "Please retry this operation on an alternate boot "
                            "environment."))
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_CONSTRAINED)
                        return EXIT_NOTLIVE
                except Exception, e:
                        api_inst.log_operation_end(error=e)
                        raise

                if not success:
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_UNKNOWN)
                        return EXIT_OOPS
                api_inst.log_operation_end(result=history.RESULT_SUCCEEDED)
        return EXIT_OK

def verify_image(api_inst, args):
        opts, pargs = getopt.getopt(args, "vfqH")

        quiet = False
        verbose = 0
        # for now, always check contents of files
        forever = display_headers = True

        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                if opt == "-v":
                        verbose = verbose + 1
                elif opt == "-f":
                        forever = True
                elif opt == "-q":
                        quiet = True
                        display_headers = False

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd="verify")
        if verbose > 2:
                DebugValues.set_value("plan", "True")

        # XXX verify should be part of pkg.client.api
        any_errors = False
        processed = False
        notfound = EmptyI
        progresstracker = get_tracker(quiet=quiet, verbose=verbose)
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
                        for act, errors, warnings, pinfo in img.verify(pfmri,
                            progresstracker, verbose=verbose, forever=forever):
                                if errors:
                                        failed = True
                                        if quiet:
                                                # Nothing more to do.
                                                break
                                        result = _("ERROR")
                                elif not failed and warnings:
                                        result = _("WARNING")

                                entries.append((act, errors, warnings, pinfo))

                        any_errors = any_errors or failed
                        if (not failed and not verbose) or quiet:
                                # Nothing more to do.
                                continue

                        if display_headers:
                                display_headers = False
                                msg(_("%(pkg_name)-70s %(result)7s") % {
                                    "pkg_name": _("PACKAGE"),
                                    "result": _("STATUS") })

                        msg(_("%(pkg_name)-70s %(result)7s") % {
                            "pkg_name": pfmri.get_pkg_stem(),
                            "result": result })

                        for act, errors, warnings, pinfo in entries:
                                if act:
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
                        return EXIT_OOPS
                notfound = e.notfound
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS

        if notfound:
                if processed:
                        # Ensure a blank line is inserted after verify output.
                        logger.error(" ")

                error(_("no packages matching '%s' installed") % \
                    ", ".join(notfound), cmd="verify")

                if processed:
                        if any_errors:
                                msg2 = _("See above for\nverification failures.")
                        else:
                                msg2 = _("No packages failed\nverification.")
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

display_plan_options = ["basic", "fmris", "variants/facets", "services",
    "actions", "boot-archive"]

def __display_plan(api_inst, verbose):
        """Helper function to display plan to the desired degree.
        Verbose can either be a numerical value, or a list of
        items to display"""

        if isinstance(verbose, int):
                disp = ["basic"]
                if verbose > 0:
                        disp.extend(["fmris", "mediators", "services",
                            "variants/facets", "boot-archive"])
                if verbose > 1:
                        disp.append("actions")
                if verbose > 2:
                        disp.append("solver-errors")
        else:
                disp = verbose

        if DebugValues["plan"] and "solver-errors" not in disp:
                disp.append("solver-errors")

        plan = api_inst.describe()

        a, r, i, c = [], [], [], []
        for src, dest in plan.get_changes():
                if dest is None:
                        r.append((src, dest))
                elif src is None:
                        i.append((src, dest))
                elif src != dest:
                        c.append((src, dest))
                else:
                        a.append((src, dest))

        def bool_str(val):
                if val:
                        return _("Yes")
                return _("No")

        status = []
        varcets = plan.get_varcets()
        mediators = plan.get_mediators()
        if "basic" in disp:
                def cond_show(s1, s2, v):
                        if v:
                                status.append((s1, s2 % v))

                cond_show(_("Packages to remove:"), "%d", len(r))
                cond_show(_("Packages to install:"), "%d", len(i))
                cond_show(_("Packages to update:"), "%d", len(c))
                cond_show(_("Mediators to change:"), "%d", len(mediators))
                cond_show(_("Variants/Facets to change:"), "%d", len(varcets))

                if verbose:
                        # Only show space information in verbose mode.
                        abytes = plan.bytes_added
                        if abytes:
                                status.append((_("Estimated space available:"),
                                    misc.bytes_to_str(plan.bytes_avail)))
                                status.append((
                                    _("Estimated space to be consumed:"),
                                    misc.bytes_to_str(plan.bytes_added)))

                if varcets or mediators:
                        cond_show(_("Packages to change:"), "%d", len(a))
                else:
                        cond_show(_("Packages to fix:"), "%d", len(a))

                status.append((_("Create boot environment:"),
                    bool_str(plan.new_be)))

                if plan.new_be and (verbose or not plan.activate_be):
                        # Only show activation status if verbose or if new BE
                        # will not be activated.
                        status.append((_("Activate boot environment:"),
                            bool_str(plan.activate_be)))

                if not plan.new_be:
                        cond_show(_("Services to change:"), "%d",
                            len(plan.get_services()))

        if "boot-archive" in disp:
                status.append((_("Rebuild boot archive:"),
                    bool_str(plan.update_boot_archive)))

        # Right-justify all status strings based on length of longest string.
        rjust_status = max(len(s[0]) for s in status)
        rjust_value = max(len(s[1]) for s in status)
        for s in status:
                logger.info("%s %s" % (s[0].rjust(rjust_status),
                    s[1].rjust(rjust_value)))

        if status:
                # Ensure there is a blank line between status information and
                # remainder.
                logger.info("")

        if "mediators" in disp and mediators:
                logger.info(_("Changed mediators:"))
                for x in mediators:
                        logger.info("  %s" % x)

        if "variants/facets" in disp and varcets:
                logger.info(_("Changed variants/facets:"))
                for x in varcets:
                        logger.info("  %s" % x)

        if "solver-errors" in disp:
                first = True
                for l in plan.get_solver_errors():
                        if first:
                                logger.info(_("Solver dependency errors:"))
                                first = False
                        logger.info(l)

        if "fmris" in disp:
                changed = collections.defaultdict(list)
                for src, dest in itertools.chain(r, i, c):
                        if src and dest:
                                if src.publisher != dest.publisher:
                                        pparent = "%s -> %s" % (src.publisher,
                                            dest.publisher)
                                else:
                                        pparent = dest.publisher
                                pname = dest.pkg_stem
                                pver = "%s -> %s" % (src.fmri.version,
                                    dest.fmri.version)
                        elif dest:
                                pparent = dest.publisher
                                pname = dest.pkg_stem
                                pver = "None -> %s" % dest.fmri.version
                        else:
                                pparent = src.publisher
                                pname = src.pkg_stem
                                pver = "%s -> None" % src.fmri.version

                        changed[pparent].append((pname, pver))

                if changed:
                        logger.info(_("Changed packages:"))
                        last_parent = None
                        for pparent, pname, pver in (
                            (pparent, pname, pver)
                            for pparent in sorted(changed)
                            for pname, pver in changed[pparent]
                        ):
                                if pparent != last_parent:
                                        logger.info(pparent)

                                logger.info("  %s" % pname)
                                logger.info("    %s" % pver)
                                last_parent = pparent

                if len(a):
                        logger.info(_("Affected fmris:"))
                        for src, dest in a:
                                logger.info("  %s", src)

        if "services" in disp and not plan.new_be:
                last_action = None
                for action, smf_fmri in plan.get_services():
                        if last_action is None:
                                logger.info("Services:")
                        if action != last_action:
                                logger.info("  %s:" % action)
                        logger.info("    %s" % smf_fmri)
                        last_action = action

        if "actions" in disp:
                logger.info("Actions:")
                for a in plan.get_actions():
                        logger.info("  %s" % a)

def __display_parsable_plan(api_inst, parsable_version,
    child_images=None):
        """Display the parsable version of the plan."""

        assert parsable_version == 0, "parsable_version was %r" % \
            parsable_version
        plan = api_inst.describe()
        # Set the default values.
        added_fmris = []
        removed_fmris = []
        changed_fmris = []
        affected_fmris = []
        new_be_created = False
        be_name = None
        boot_archive_rebuilt = False
        be_activated = True
        space_available = None
        space_required = None
        facets_changed = []
        variants_changed = []
        services_affected = []
        mediators_changed = []
        licenses = []
        if child_images is None:
                child_images = []

        if plan:
                for rem, add in plan.get_changes():
                        assert rem is not None or add is not None
                        if rem is not None and add is not None:
                                # Lists of lists are used here becuase json will
                                # convert lists of tuples into lists of lists
                                # anyway.
                                if rem.fmri == add.fmri:
                                        affected_fmris.append(str(rem))
                                else:
                                        changed_fmris.append(
                                            [str(rem), str(add)])
                        elif rem is not None:
                                removed_fmris.append(str(rem))
                        else:
                                added_fmris.append(str(add))
                variants_changed, facets_changed = plan.get_parsable_varcets()
                new_be_created = plan.new_be
                be_name = plan.be_name
                boot_archive_rebuilt = plan.update_boot_archive
                be_activated = plan.activate_be
                space_available = plan.bytes_avail
                space_required = plan.bytes_added
                services_affected = plan.get_services()
                mediators_changed = plan.get_parsable_mediators()
                for dfmri, src_li, dest_li, acc, disp in \
                    plan.get_licenses():
                        src_tup = None
                        if src_li:
                                src_tup = (str(src_li.fmri), src_li.license,
                                    src_li.get_text(), src_li.must_accept,
                                    src_li.must_display)
                        dest_tup = None
                        if dest_li:
                                dest_tup = (str(dest_li.fmri),
                                    dest_li.license, dest_li.get_text(),
                                    dest_li.must_accept, dest_li.must_display)
                        licenses.append(
                            (str(dfmri), src_tup, dest_tup))
                        api_inst.set_plan_license_status(dfmri, dest_li.license,
                            displayed=True)
        ret = {
            "create-new-be": new_be_created,
            "be-name": be_name,
            "boot-archive-rebuild": boot_archive_rebuilt,
            "activate-be": be_activated,
            "space-available": space_available,
            "space-required": space_required,
            "remove-packages": sorted(removed_fmris),
            "add-packages": sorted(added_fmris),
            "change-packages": sorted(changed_fmris),
            "affect-packages": sorted(affected_fmris),
            "change-facets": sorted(facets_changed),
            "change-variants": sorted(variants_changed),
            "affect-services": sorted(services_affected),
            "change-mediators": sorted(mediators_changed),
            "image-name": None,
            "child-images": child_images,
            "version": parsable_version,
            "licenses": sorted(licenses)
        }
        # The image name for the parent image is always None.  If this image is
        # a child image, then the image name will be set when the parent image
        # processes this dictionary.
        logger.info(json.dumps(ret))

def display_plan_licenses(api_inst, show_all=False, show_req=True):
        """Helper function to display licenses for the current plan.

        'show_all' is an optional boolean value indicating whether all licenses
        should be displayed or only those that have must-display=true."""

        plan = api_inst.describe()
        for pfmri, src, dest, accepted, displayed in plan.get_licenses():
                if not show_all and not dest.must_display:
                        continue

                if not show_all and dest.must_display and displayed:
                        # License already displayed, so doesn't need to be
                        # displayed again.
                        continue

                lic = dest.license
                if show_req:
                        logger.info("-" * 60)
                        logger.info(_("Package: %s") % pfmri)
                        logger.info(_("License: %s\n") % lic)
                        logger.info(dest.get_text())
                        logger.info("\n")

                # Mark license as having been displayed.
                api_inst.set_plan_license_status(pfmri, lic, displayed=True)

def display_plan(api_inst, child_image_plans, noexecute, op, parsable_version,
    quiet, show_licenses, stage, verbose):

        plan = api_inst.describe()
        if not plan:
                return

        if stage not in [API_STAGE_DEFAULT, API_STAGE_PLAN]:
                # we should have displayed licenses earlier so mark all
                # licenses as having been displayed.
                display_plan_licenses(api_inst, show_req=False)
                return

        if api_inst.planned_nothingtodo(li_ignore_all=True):
                # nothing todo
                if op == PKG_OP_UPDATE:
                        s = _("No updates available for this image.")
                else:
                        s = _("No updates necessary for this image.")
                if api_inst.ischild():
                        s + " (%s)" % api_inst.get_linked_name()
                msg(s)
                return

        if parsable_version is None:
                display_plan_licenses(api_inst, show_all=show_licenses)

        if not quiet:
                __display_plan(api_inst, verbose)
        if parsable_version is not None:
                __display_parsable_plan(api_inst, parsable_version,
                    child_image_plans)

def __api_prepare(operation, api_inst, accept=False):
        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        # XXX would be nice to kick the progress tracker.
        try:
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
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ImageInsufficentSpace, e:
                error(str(e))
                return EXIT_OOPS
        except KeyboardInterrupt:
                raise
        except:
                error(_("\nAn unexpected error happened while preparing for "
                    "%s:") % operation)
                raise
        return EXIT_OK

def __api_execute_plan(operation, api_inst):
        rval = None
        try:
                api_inst.execute_plan()
                rval = EXIT_OK
        except RuntimeError, e:
                error(_("%s failed: %s") % (operation, e))
                rval = EXIT_OOPS
        except (api_errors.InvalidPlanError,
            api_errors.ActionExecutionError,
            api_errors.InvalidPackageErrors), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                rval = EXIT_OOPS
        except (api_errors.LinkedImageException), e:
                error(_("%s failed (linked image exception(s)):\n%s") %
                      (operation, str(e)))
                rval = e.lix_exitrv
        except api_errors.ImageUpdateOnLiveImageException:
                error(_("%s cannot be done on live image") % operation)
                rval = EXIT_NOTLIVE
        except api_errors.RebootNeededOnLiveImageException:
                error(_("Requested \"%s\" operation would affect files that "
                    "cannot be modified in live image.\n"
                    "Please retry this operation on an alternate boot "
                    "environment.") % operation)
                rval = EXIT_NOTLIVE
        except api_errors.CorruptedIndexException, e:
                error("The search index appears corrupted.  Please rebuild the "
                    "index with 'pkg rebuild-index'.")
                rval = EXIT_OOPS
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e))
                error(_("\n(Failure to consistently execute pkg commands as a "
                    "privileged user is often a source of this problem.)"))
                rval = EXIT_OOPS
        except (api_errors.PermissionsException, api_errors.UnknownErrors), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                rval = EXIT_OOPS
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                rval = EXIT_OOPS
        except api_errors.BEException, e:
                error(e)
                rval = EXIT_OOPS
        except api_errors.WrapSuccessfulIndexingException:
                raise
        except api_errors.ImageInsufficentSpace, e:
                error(str(e))
                return EXIT_OOPS
        except Exception, e:
                error(_("An unexpected error happened during "
                    "%s: %s") % (operation, e))
                raise
        finally:
                exc_type = exc_value = exc_tb = None
                if rval is None:
                        # Store original exception so that the real cause of
                        # failure can be raised if this fails.
                        exc_type, exc_value, exc_tb = sys.exc_info()

                try:
                        salvaged = api_inst.describe().get_salvaged()
                        if salvaged:
                                logger.error("")
                                logger.error(_("The following unexpected or "
                                    "editable files and directories were\n"
                                    "salvaged while executing the requested "
                                    "package operation; they\nhave been moved "
                                    "to the displayed location in the image:\n"))
                                for opath, spath in salvaged:
                                        logger.error("  %s -> %s" % (opath,
                                            spath))
                except Exception:
                        if rval is not None:
                                # Only raise exception encountered here if the
                                # exception previously raised was suppressed.
                                raise

                if exc_value or exc_tb:
                        raise exc_value, None, exc_tb

        return rval

def __api_alloc(imgdir, exact_match, pkg_image_used, quiet, runid=-1):
        progresstracker = get_tracker(quiet=quiet)

        def qv(val):
                # Escape shell metacharacters; '\' must be escaped first to
                # prevent escaping escapes.
                for c in "\\ \t\n'`;&()|^<>?*":
                        val = val.replace(c, "\\" + c)
                return val

        try:
                return api.ImageInterface(imgdir, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME,
                    exact_match=exact_match, runid=runid)
        except api_errors.ImageNotFoundException, e:
                if e.user_specified:
                        if pkg_image_used:
                                error(_("No image rooted at '%s' "
                                    "(set by $PKG_IMAGE)") % e.user_dir)
                        else:
                                error(_("No image rooted at '%s'") % e.user_dir)
                else:
                        error(_("No image found."))
                return
        except api_errors.PermissionsException, e:
                error(e)
                return
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return

def __api_plan_exception(op, noexecute, verbose, api_inst):
        e_type, e, e_traceback = sys.exc_info()

        if e_type == api_errors.ImageNotFoundException:
                error(_("No image rooted at '%s'") % e.user_dir, cmd=op)
                return EXIT_OOPS
        if e_type == api_errors.InventoryException:
                error("\n" + _("%s failed (inventory exception):\n%s") % (op,
                    e))
                return EXIT_OOPS
        if isinstance(e, api_errors.LinkedImageException):
                error(_("%s failed (linked image exception(s)):\n%s") %
                      (op, str(e)))
                return e.lix_exitrv
        if e_type == api_errors.IpkgOutOfDateException:
                msg(_("""\
WARNING: pkg(5) appears to be out of date, and should be updated before
running %(op)s.  Please update pkg(5) by executing 'pkg install
pkg:/package/pkg' as a privileged user and then retry the %(op)s."""
                    ) % locals())
                return EXIT_OOPS
        if e_type == api_errors.NonLeafPackageException:
                error(_("""\
Cannot remove '%s' due to the following packages that depend on it:"""
                    ) % e.fmri, cmd=op)
                for d in e.dependents:
                        logger.error("  %s" % d)
                return EXIT_OOPS
        if e_type == api_errors.CatalogRefreshException:
                if display_catalog_failures(e) != 0:
                        return EXIT_OOPS
                if noexecute:
                        return EXIT_OK
                return EXIT_OOPS
        if e_type == api_errors.ConflictingActionErrors:
                error("\n" + str(e), cmd=op)
                if verbose:
                        __display_plan(api_inst, verbose)
                return EXIT_OOPS
        if e_type in (api_errors.InvalidPlanError,
            api_errors.ReadOnlyFileSystemException,
            api_errors.ActionExecutionError,
            api_errors.InvalidPackageErrors):
                error("\n" + str(e), cmd=op)
                return EXIT_OOPS
        if e_type == api_errors.ImageFormatUpdateNeeded:
                format_update_error(e)
                return EXIT_OOPS

        if e_type == api_errors.ImageUpdateOnLiveImageException:
                error("\n" + _("The proposed operation cannot be performed on "
                    "a live image."), cmd=op)
                return EXIT_NOTLIVE

        if issubclass(e_type, api_errors.BEException):
                error("\n" + str(e), cmd=op)
                return EXIT_OOPS

        if e_type == api_errors.PlanCreationException:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                txt = str(e)
                if e.multiple_matches:
                        txt += "\n\n" + _("Please provide one of the package "
                            "FMRIs listed above to the install command.")
                error("\n" + txt, cmd=op)
                if verbose:
                        logger.error("\n".join(e.verbose_info))
                if e.invalid_mediations:
                        # Bad user input for mediation.
                        return EXIT_BADOPT
                return EXIT_OOPS

        if e_type in (api_errors.CertificateError,
            api_errors.UnknownErrors,
            api_errors.PermissionsException,
            api_errors.InvalidPropertyValue,
            api_errors.InvalidResourceLocation):
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e), cmd=op)
                return EXIT_OOPS
        if e_type == fmri.IllegalFmri:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e), cmd=op)
                return EXIT_OOPS
        if isinstance(e, api_errors.SigningException):
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e), cmd=op)
                return EXIT_OOPS

        # if we didn't deal with the exception above, pass it on.
        raise
        # NOTREACHED

def __api_op(_op, _api_inst, _accept=False, _li_ignore=None, _noexecute=False,
    _origins=None, _parsable_version=None, _quiet=False,
    _review_release_notes=False, _show_licenses=False, _stage=API_STAGE_DEFAULT,
    _verbose=0, **kwargs):
        """Do something that involves the api.

        Arguments prefixed with '_' are primarily used within this
        function.  All other arguments must be specified via keyword
        assignment and will be passed directly on to the api
        interfaces being invoked."""

        # massage arguments
        if type(_li_ignore) == list:
                # parse any linked image names specified on the command line
                _li_ignore = _api_inst.parse_linked_name_list(_li_ignore)

        # All the api interface functions that we inovke have some
        # common arguments.  Set those up now.
        kwargs["accept"] = _accept
        kwargs["li_ignore"] = _li_ignore
        kwargs["noexecute"] = _noexecute
        if _origins != None:
                kwargs["repos"] = _origins

        # display plan debugging information
        if _verbose > 2:
                DebugValues.set_value("plan", "True")

        # plan the requested operation
        stuff_to_do = None

        if _op == PKG_OP_ATTACH:
                api_plan_func = _api_inst.gen_plan_attach
        elif _op in [PKG_OP_CHANGE_FACET, PKG_OP_CHANGE_VARIANT]:
                api_plan_func = _api_inst.gen_plan_change_varcets
        elif _op == PKG_OP_DETACH:
                api_plan_func = _api_inst.gen_plan_detach
        elif _op == PKG_OP_INSTALL:
                api_plan_func = _api_inst.gen_plan_install
        elif _op == PKG_OP_SYNC:
                api_plan_func = _api_inst.gen_plan_sync
        elif _op == PKG_OP_UNINSTALL:
                api_plan_func = _api_inst.gen_plan_uninstall
        elif _op == PKG_OP_UPDATE:
                api_plan_func = _api_inst.gen_plan_update
        else:
                raise RuntimeError("__api_op() invalid op: %s" % _op)

        first_plan = True
        plan_displayed = False
        child_plans = []
        try:
                for pd in api_plan_func(**kwargs):
                        if not first_plan:
                                #
                                # we don't display anything for child images
                                # since they currently do their own display
                                # work unless parsable output is requested.
                                #
                                child_plans.append(pd)
                                continue

                        # the first plan description is always for ourself.
                        first_plan = False
                        if _parsable_version is None:
                                display_plan(_api_inst, [], _noexecute,
                                    _op, _parsable_version, _quiet,
                                    _show_licenses, _stage, _verbose)
                                plan_displayed = True
        except:
                rv = __api_plan_exception(_op, _noexecute, _verbose, _api_inst)
                if rv != EXIT_OK:
                        return rv

        if not plan_displayed:
                try:
                        display_plan(_api_inst, child_plans, _noexecute, _op,
                            _parsable_version, _quiet, _show_licenses, _stage,
                            _verbose)
                except api_errors.ApiException, e:
                        error(e, cmd=op)
                        return EXIT_OOPS

        stuff_to_do = not _api_inst.planned_nothingtodo()
        if not stuff_to_do:
                return EXIT_NOP

        if _noexecute or _stage in [API_STAGE_PUBCHECK, API_STAGE_PLAN]:
                return EXIT_OK

        # Exceptions which happen here are printed in the above level,
        # with or without some extra decoration done here.
        ret_code = __api_prepare(_op, _api_inst, accept=_accept)
        if ret_code != EXIT_OK:
                return ret_code

        if _stage == API_STAGE_PREPARE:
                return EXIT_OK

        ret_code = __api_execute_plan(_op, _api_inst)
        if _review_release_notes and ret_code == 0 and \
            _stage == API_STAGE_DEFAULT and _api_inst.solaris_image():
                msg("\n" + "-" * 75)
                msg(_("NOTE: Please review release notes posted at:\n" ))
                msg(misc.get_release_notes_url())
                msg("-" * 75 + "\n")

        return ret_code

def opts_err_opt1_req_opt2(opt1, opt2, op):
        msg = _("%(opt1)s may only be used in combination with %(opt2)s") % \
            {"opt1": opt1, "opt2": opt2}
        usage(msg, cmd=op)

def opts_err_incompat(opt1, opt2, op):
        msg = _("the %(opt1)s and %(opt2)s options may not be combined") % \
            {"opt1": opt1, "opt2": opt2}
        usage(msg, cmd=op)

def opts_err_repeated(opt1, op):
        msg = _("option '%s' repeated") % (opt1)
        usage(msg, cmd=op)

def opts_table_cb_beopts(op, api_inst, opts, opts_new):

        # synthesize require_new_be and deny_new_be into new_be
        del opts_new["require_new_be"]
        del opts_new["deny_new_be"]
        opts_new["new_be"] = None

        if opts["require_new_be"] and opts["deny_new_be"]:
                opts_err_incompat("--require-new-be", "--deny-new-be", op)

        # create a new key called "new_be" in the options array
        if opts["require_new_be"]:
                opts_new["new_be"] = True
        if opts["deny_new_be"]:
                opts_new["new_be"] = False

def opts_table_cb_li_ignore(op, api_inst, opts, opts_new):

        # synthesize li_ignore_all and li_ignore_list into li_ignore
        del opts_new["li_ignore_all"]
        del opts_new["li_ignore_list"]
        opts_new["li_ignore"] = None

        # check if there's nothing to ignore
        if not opts["li_ignore_all"] and not opts["li_ignore_list"]:
                return

        if opts["li_ignore_all"]:

                # can't ignore all and specific images
                if opts["li_ignore_list"]:
                        opts_err_incompat("-I", "-i", op)

                # can't ignore all and target anything.
                if "li_target_all" in opts and opts["li_target_all"]:
                        opts_err_incompat("-I", "-a", op)
                if "li_target_list" in opts and opts["li_target_list"]:
                        opts_err_incompat("-I", "-l", op)
                if "li_name" in opts and opts["li_name"]:
                        opts_err_incompat("-I", "-l", op)

                opts_new["li_ignore"] = []
                return

        assert opts["li_ignore_list"]

        # it doesn't make sense to specify images to ignore if the
        # user is already specifying images to operate on.
        if "li_target_all" in opts and opts["li_target_all"]:
                opts_err_incompat("-i", "-a", op)
        if "li_target_list" in opts and opts["li_target_list"]:
                opts_err_incompat("-i", "-l", op)
        if "li_name" in opts and opts["li_name"]:
                opts_err_incompat("-i", "-l", op)

        li_ignore = []
        for li_name in opts["li_ignore_list"]:
                # check for repeats
                if li_name in li_ignore:
                        opts_err_repeated("-i %s" % (li_name), op)
                # add to ignore list
                li_ignore.append(li_name)

        opts_new["li_ignore"] = li_ignore

def opts_table_cb_li_no_psync(op, api_inst, opts, opts_new):
        # if a target child linked image was specified, the no-parent-sync
        # option doesn't make sense since we know that both the parent and
        # child image are accessible

        if "li_target_all" not in opts:
                # we don't accept linked image target options
                assert "li_target_list" not in opts
                return

        if opts["li_target_all"] and not opts["li_parent_sync"]:
                opts_err_incompat("-a", "--no-parent-sync", op)
        if opts["li_target_list"] and not opts["li_parent_sync"]:
                opts_err_incompat("-l", "--no-parent-sync", op)

def opts_table_cb_li_props(op, api_inst, opts, opts_new):
        """convert linked image prop list into a dictionary"""

        opts_new["li_props"] = __parse_linked_props(opts["li_props"], op)

def opts_table_cb_li_target(op, api_inst, opts, opts_new):
        # figure out which option the user specified
        if opts["li_target_all"] and opts["li_target_list"]:
                opts_err_incompat("-a", "-l", op)
        elif opts["li_target_all"]:
                arg1 = "-a"
        elif opts["li_target_list"]:
                arg1 = "-l"
        else:
                return

        if "be_activate" in opts and not opts["be_activate"]:
                opts_err_incompat(arg1, "--no-be-activate", op)
        if "be_name" in opts and opts["be_name"]:
                opts_err_incompat(arg1, "--be-name", op)
        if "deny_new_be" in opts and opts["deny_new_be"]:
                opts_err_incompat(arg1, "--deny-new-be", op)
        if "require_new_be" in opts and opts["require_new_be"]:
                opts_err_incompat(arg1, "--require-new-be", op)
        if "reject_pats" in opts and opts["reject_pats"]:
                opts_err_incompat(arg1, "--reject", op)
        if "origins" in opts and opts["origins"]:
                opts_err_incompat(arg1, "-g", op)

        # validate linked image name
        li_target_list = []
        for li_name in opts["li_target_list"]:
                # check for repeats
                if li_name in li_target_list:
                        opts_err_repeated("-l %s" % (li_name), op)
                # add to ignore list
                li_target_list.append(li_name)

        opts_new["li_target_list"] = li_target_list

def opts_table_cb_li_target1(op, api_inst, opts, opts_new):
        # figure out which option the user specified
        if opts["li_name"]:
                arg1 = "-l"
        else:
                return

        if "be_activate" in opts and not opts["be_activate"]:
                opts_err_incompat(arg1, "--no-be-activate", op)
        if "be_name" in opts and opts["be_name"]:
                opts_err_incompat(arg1, "--be-name", op)
        if "deny_new_be" in opts and opts["deny_new_be"]:
                opts_err_incompat(arg1, "--deny-new-be", op)
        if "require_new_be" in opts and opts["require_new_be"]:
                opts_err_incompat(arg1, "--require-new-be", op)
        if "reject_pats" in opts and opts["reject_pats"]:
                opts_err_incompat(arg1, "--require", op)
        if "origins" in opts and opts["origins"]:
                opts_err_incompat(arg1, "-g", op)

def opts_table_cb_no_headers_vs_quiet(op, api_inst, opts, opts_new):
        # check if we accept the -q option
        if "quiet" not in opts:
                return

        # -q implies -H
        if opts["quiet"]:
                opts_new["omit_headers"] = True

def opts_table_cb_nqv(op, api_inst, opts, opts_new):
        if opts["verbose"] and opts["quiet"]:
                opts_err_incompat("-v", "-q", op)

def opts_table_cb_parsable(op, api_inst, opts, opts_new):
        if opts["parsable_version"] and opts.get("verbose", False):
                opts_err_incompat("--parsable", "-v", op)
        if opts["parsable_version"]:
                try:
                        opts_new["parsable_version"] = int(
                            opts["parsable_version"])
                except ValueError:
                        usage(_("--parsable expects an integer argument."),
                            cmd=op)
                opts_new["quiet"] = True

def opts_table_cb_origins(op, api_inst, opts, opts_new):
        origins = set()
        for o in opts["origins"]:
                origins.add(misc.parse_uri(o, cwd=orig_cwd))
        opts_new["origins"] = origins

def opts_table_cb_stage(op, api_inst, opts, opts_new):
        if opts["stage"] == None:
                opts_new["stage"] = API_STAGE_DEFAULT
                return

        if opts_new["stage"] not in api_stage_values:
                usage(_("invalid operation stage: '%s'") % opts["stage"],
                    cmd=op)

def opts_cb_li_attach(op, api_inst, opts, opts_new):
        if opts["attach_parent"] and opts["attach_child"]:
                opts_err_incompat("-c", "-p", op)

        if not opts["attach_parent"] and not opts["attach_child"]:
                usage(_("either -c or -p must be specified"), cmd=op)

        if opts["attach_child"]:
                # if we're attaching a new child then that doesn't affect
                # any other children, so ignoring them doesn't make sense.
                if opts["li_ignore_all"]:
                        opts_err_incompat("-c", "-I", op)
                if opts["li_ignore_list"]:
                        opts_err_incompat("-c", "-i", op)

def opts_table_cb_md_only(op, api_inst, opts, opts_new):
        # if the user didn't specify linked-md-only we're done
        if not opts["li_md_only"]:
                return

        # li_md_only implies no li_pkg_updates
        if "li_pkg_updates" in opts:
                opts_new["li_pkg_updates"] = False

        #
        # if li_md_only is false that means we're not updating any packages
        # within the current image so there are a ton of options that no
        # longer apply to the current operation, and hence are incompatible
        # with li_md_only.
        #
        arg1 = "--linked-md-only"
        if "be_name" in opts and opts["be_name"]:
                opts_err_incompat(arg1, "--be-name", op)
        if "deny_new_be" in opts and opts["deny_new_be"]:
                opts_err_incompat(arg1, "--deny-new-be", op)
        if "require_new_be" in opts and opts["require_new_be"]:
                opts_err_incompat(arg1, "--require-new-be", op)
        if "li_parent_sync" in opts and not opts["li_parent_sync"]:
                opts_err_incompat(arg1, "--no-parent-sync", op)
        if "reject_pats" in opts and opts["reject_pats"]:
                opts_err_incompat(arg1, "--reject", op)

def opts_cb_list(op, api_inst, opts, opts_new):
        if opts_new["origins"] and not opts_new["list_newest"]:
                # Use of -g implies -a unless -n is provided.
                opts_new["list_installed_newest"] = True

        if opts_new["list_all"] and not opts_new["list_installed_newest"]:
                opts_err_opt1_req_opt2("-f", "-a", op)

        if opts_new["list_installed_newest"] and opts_new["list_newest"]:
                opts_err_incompat("-a", "-n", op)

        if opts_new["list_installed_newest"] and opts_new["list_upgradable"]:
                opts_err_incompat("-a", "-u", op)

        if opts_new["summary"] and opts_new["verbose"]:
                opts_err_incompat("-s", "-v", op)

#
# options common to multiple pkg(1) subcommands.  The format for specifying
# options is a list which can contain:
#
# - Function pointers which define callbacks that are invoked after all
#   options (aside from extra pargs) have been parsed.  These callbacks can
#   verify the the contents and combinations of different options.
#
# - Tuples formatted as:
#       (s, l, k, v)
#   where the values are:
#       s: a short option, ex: -f
#       l: a long option, ex: --foo
#       k: the key value for the options dictionary
#       v: the default value. valid values are: True/False, None, [], 0
#
opts_table_beopts = [
    opts_table_cb_beopts,
    ("",  "be-name=",        "be_name",              None),
    ("",  "deny-new-be",     "deny_new_be",          False),
    ("",  "no-be-activate",  "be_activate",          True),
    ("",  "require-new-be",  "require_new_be",       False),
]

opts_table_force = [
    ("f", "",                "force",                False),
]

opts_table_li_ignore = [
    opts_table_cb_li_ignore,
    ("I", "",                "li_ignore_all",        False),
    ("i", "",                "li_ignore_list",       []),
]

opts_table_li_md_only = [
    opts_table_cb_md_only,
    ("",  "linked-md-only",    "li_md_only",         False),
]

opts_table_li_no_pkg_updates = [
    ("",  "no-pkg-updates",  "li_pkg_updates",       True),
]

opts_table_li_no_psync = [
    opts_table_cb_li_no_psync,
    ("",  "no-parent-sync",  "li_parent_sync",       True),
]

opts_table_li_props = [
    opts_table_cb_li_props,
    ("", "prop-linked",      "li_props",             []),
]

opts_table_li_target = [
    opts_table_cb_li_target,
    ("a", "",                "li_target_all",        False),
    ("l", "",                "li_target_list",       []),
]

opts_table_li_target1 = [
    opts_table_cb_li_target1,
    ("l", "",                "li_name",              None),
]

opts_table_licenses = [
    ("",  "accept",          "accept",               False),
    ("",  "licenses",        "show_licenses",        False),
]

opts_table_no_headers = [
    opts_table_cb_no_headers_vs_quiet,
    ("H", "",                "omit_headers",         False),
]

opts_table_no_index = [
    ("",  "no-index",        "update_index",         True),
]

opts_table_no_refresh = [
    ("",  "no-refresh",      "refresh_catalogs",     True),
]

opts_table_reject = [
    ("", "reject=",          "reject_pats",          []),
]

opts_table_verbose = [
    ("v", "",                "verbose",              0),
]

opts_table_quiet = [
    ("q", "",                "quiet",                False),
]

opts_table_parsable = [
    opts_table_cb_parsable,
    ("", "parsable=",        "parsable_version",    None),
]

opts_table_nqv = \
    opts_table_quiet + \
    opts_table_verbose + \
    [
    opts_table_cb_nqv,
    ("n", "",                "noexecute",            False),
]

opts_table_origins = [
    opts_table_cb_origins,
    ("g", "",                "origins",              []),
]

opts_table_stage = [
    opts_table_cb_stage,
    ("",  "stage",           "stage",                None),
]

#
# Options for pkg(1) subcommands.  Built by combining the option tables above,
# with some optional subcommand unique options defined below.
#
opts_install = \
    opts_table_beopts + \
    opts_table_li_ignore + \
    opts_table_li_no_psync + \
    opts_table_licenses + \
    opts_table_reject + \
    opts_table_no_index + \
    opts_table_no_refresh + \
    opts_table_nqv + \
    opts_table_parsable + \
    opts_table_origins + \
    []

# "update" cmd inherits all "install" cmd options
opts_update = \
    opts_install + \
    opts_table_force + \
    opts_table_stage + \
    []

# "attach-linked" cmd inherits all "install" cmd options
opts_attach_linked = \
    opts_install + \
    opts_table_force + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_props + \
    [
    opts_cb_li_attach,
    ("",  "allow-relink",   "allow_relink",         False),
    ("c", "",               "attach_child",         False),
    ("p", "",               "attach_parent",        False),
]

opts_list_mediator = \
    opts_table_no_headers + \
    [
    ("a", "",                "list_available",      False),
    ("F", "output-format",   "output_format",       None)
]

opts_set_mediator = \
    opts_table_beopts + \
    opts_table_no_index + \
    opts_table_nqv + \
    opts_table_parsable + \
    [
    ("I", "implementation",  "med_implementation",   None),
    ("V", "version",         "med_version",          None)
]

opts_unset_mediator = \
    opts_table_beopts + \
    opts_table_no_index + \
    opts_table_nqv + \
    opts_table_parsable + \
    [
    ("I", "",               "med_implementation",   False),
    ("V", "",               "med_version",          False)
]

# "set-property-linked" cmd inherits all "install" cmd options
opts_set_property_linked = \
    opts_install + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_target1 + \
    []

# "sync-linked" cmd inherits all "install" cmd options
opts_sync_linked = \
    opts_install + \
    opts_table_li_md_only + \
    opts_table_li_no_pkg_updates + \
    opts_table_li_target + \
    opts_table_stage + \
    []

opts_uninstall = \
    opts_table_beopts + \
    opts_table_li_ignore + \
    opts_table_no_index + \
    opts_table_nqv + \
    opts_table_parsable + \
    opts_table_stage

opts_audit_linked = \
    opts_table_li_no_psync + \
    opts_table_li_target + \
    opts_table_no_headers + \
    opts_table_quiet + \
    []

opts_detach_linked = \
    opts_table_force + \
    opts_table_li_target + \
    opts_table_nqv + \
    []

opts_list_linked = \
    opts_table_li_ignore + \
    opts_table_no_headers + \
    []

opts_list_property_linked = \
    opts_table_li_target1 + \
    opts_table_no_headers + \
    []

opts_list_inventory = \
    opts_table_li_no_psync + \
    opts_table_no_refresh + \
    opts_table_no_headers + \
    opts_table_origins + \
    opts_table_verbose + \
    [
    opts_cb_list,
    ("a", "",               "list_installed_newest", False),
    ("f", "",               "list_all",              False),
    ("n", "",               "list_newest",           False),
    ("s", "",               "summary",               False),
    ("u", "",               "list_upgradable",       False),
]

def change_variant(op, api_inst, pargs,
    accept, be_activate, be_name, li_ignore, li_parent_sync, new_be,
    noexecute, origins, parsable_version, quiet, refresh_catalogs, reject_pats,
    show_licenses, update_index, verbose):
        """Attempt to change a variant associated with an image, updating
        the image contents as necessary."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

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

        return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
            _noexecute=noexecute, _origins=origins,
            _parsable_version=parsable_version, _quiet=quiet,
            _show_licenses=show_licenses, _verbose=verbose,
            be_activate=be_activate, be_name=be_name,
            li_parent_sync=li_parent_sync, new_be=new_be,
            refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
            update_index=update_index, variants=variants)

def change_facet(op, api_inst, pargs,
    accept, be_activate, be_name, li_ignore, li_parent_sync, new_be,
    noexecute, origins, parsable_version, quiet, refresh_catalogs, reject_pats,
    show_licenses, update_index, verbose):
        """Attempt to change the facets as specified, updating
        image as necessary"""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        if not pargs:
                usage(_("%s: no facets specified") % op)

        # XXX facets should be accessible through pkg.client.api
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

                if v is None:
                        facets.pop(name, None)
                else:
                        facets[name] = v

        return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
            _noexecute=noexecute, _origins=origins,
            _parsable_version=parsable_version, _quiet=quiet,
            _show_licenses=show_licenses, _verbose=verbose,
            be_activate=be_activate, be_name=be_name,
            li_parent_sync=li_parent_sync, new_be=new_be, facets=facets,
            refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
            update_index=update_index)

def install(op, api_inst, pargs,
    accept, be_activate, be_name, li_ignore, li_parent_sync, new_be,
    noexecute, origins, parsable_version, quiet, refresh_catalogs, reject_pats,
    show_licenses, update_index, verbose):

        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        if not pargs:
                usage(_("at least one package name required"), cmd=op)

        rval, res = get_fmri_args(api_inst, pargs, cmd=op)
        if not rval:
                return EXIT_OOPS

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
            _noexecute=noexecute, _origins=origins, _quiet=quiet,
            _show_licenses=show_licenses, _verbose=verbose,
            be_activate=be_activate, be_name=be_name,
            li_parent_sync=li_parent_sync, new_be=new_be,
            _parsable_version=parsable_version, pkgs_inst=pargs,
            refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
            update_index=update_index)

def uninstall(op, api_inst, pargs,
    be_activate, be_name, new_be, li_ignore, update_index, noexecute,
    parsable_version, quiet, verbose, stage):
        """Attempt to take package specified to DELETED state."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        if not pargs:
                usage(_("at least one package name required"), cmd=op)

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd=op)

        rval, res = get_fmri_args(api_inst, pargs, cmd=op)
        if not rval:
                return EXIT_OOPS

        return __api_op(op, api_inst, _li_ignore=li_ignore,
            _noexecute=noexecute, _quiet=quiet, _stage=stage,
            _verbose=verbose, be_activate=be_activate, be_name=be_name,
            new_be=new_be, _parsable_version=parsable_version,
            pkgs_to_uninstall=pargs, update_index=update_index)

def update(op, api_inst, pargs,
    accept, be_activate, be_name, force, li_ignore, li_parent_sync,
    new_be, noexecute, origins, parsable_version, quiet, refresh_catalogs,
    reject_pats, show_licenses, stage, update_index, verbose):
        """Attempt to take all installed packages specified to latest
        version."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        rval, res = get_fmri_args(api_inst, pargs, cmd=op)
        if not rval:
                return EXIT_OOPS

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        api_inst.set_stage(stage)

        if res and "*" not in pargs and "*@*" not in pargs:
                # If there are specific installed packages to update,
                # then take only those packages to the latest version
                # allowed by the patterns specified.  (The versions
                # specified can be older than what is installed.)
                pkgs_update = pargs
                review_release_notes = False
        else:
                # If no packages were specified, or '*' was one of the
                # patterns provided, attempt to update all installed packages.
                pkgs_update = None
                review_release_notes = True

        return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
            _noexecute=noexecute, _origins=origins,
            _parsable_version=parsable_version, _quiet=quiet,
            _review_release_notes=review_release_notes,
            _show_licenses=show_licenses, _stage=stage, _verbose=verbose,
            be_activate=be_activate, be_name=be_name, force=force,
            li_parent_sync=li_parent_sync, new_be=new_be,
            pkgs_update=pkgs_update, refresh_catalogs=refresh_catalogs,
            reject_list=reject_pats, update_index=update_index)

def revert(api_inst, args):
        """Attempt to revert files to their original state, either
        via explicit path names or via tagged contents."""

        op = "revert"
        opts, pargs = getopt.getopt(args, "nvq", ["tagged", "deny-new-be",
            "no-be-activate", "parsable=", "require-new-be", "be-name="])

        quiet = tagged = noexecute = False
        verbose = 0
        new_be = None
        be_activate = True
        be_name = None
        parsable_version = None

        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = verbose + 1
                elif opt == "-q":
                        quiet = True
                elif opt == "--deny-new-be":
                        new_be = False
                elif opt == "--no-be-activate":
                        be_activate = False
                elif opt == "--require-new-be":
                        new_be = True
                elif opt == "--be-name":
                        be_name = arg
                elif opt == "--tagged":
                        tagged = True
                elif opt == "--parsable":
                        try:
                                parsable_version = int(arg)
                        except ValueError:
                                usage(_("--parsable takes an integer "
                                    "indicating the version of parsable output "
                                    "to display."), cmd=op)
                        quiet = True

        if not pargs:
                usage(_("at least one file path or tag name required"), cmd=op)
        if verbose > 2:
                DebugValues.set_value("plan", "True")
        if verbose and (parsable_version is not None):
                usage(_("verbose and parsable are incompatible options."),
                    cmd=op)

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        stuff_to_do = None
        try:
                for pd in api_inst.gen_plan_revert(pargs, tagged=tagged,
                    noexecute=noexecute, be_name=be_name, new_be=new_be,
                    be_activate=be_activate):
                        continue
                stuff_to_do = not api_inst.planned_nothingtodo()
        except:
                ret_code = __api_plan_exception(op, noexecute, verbose,
                    api_inst)
                if ret_code != EXIT_OK:
                        return ret_code

        if not stuff_to_do:
                if verbose:
                        __display_plan(api_inst, verbose)
                if parsable_version is not None:
                        try:
                                __display_parsable_plan(api_inst,
                                    parsable_version)
                        except api_errors.ApiException, e:
                                error(e, cmd=op)
                                return EXIT_OOPS
                else:
                        msg(_("No files need to be reverted."))
                return EXIT_NOP

        if not quiet:
                __display_plan(api_inst, verbose)
        if parsable_version is not None:
                try:
                        __display_parsable_plan(api_inst, parsable_version)
                except api_errors.ApiException, e:
                        error(e, cmd=op)
                        return EXIT_OOPS

        if noexecute:
                return EXIT_OK

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        ret_code = __api_prepare(op, api_inst, accept=False)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        return ret_code

def list_mediators(op, api_inst, pargs, omit_headers, output_format,
    list_available):
        """Display configured or available mediator version(s) and
        implementation(s)."""

        subcommand = "mediator"
        if output_format is None:
                output_format = "default"

        # mediator information is returned as a dictionary of dictionaries
        # of version and implementation indexed by mediator name.
        mediations = collections.defaultdict(list)
        if list_available:
                gen_mediators = api_inst.gen_available_mediators()
        else:
                # Configured mediator information
                gen_mediators = (
                    (mediator, mediation)
                    for mediator, mediation in api_inst.mediators.iteritems()
                )

        # Set minimum widths for mediator and version columns by using the
        # length of the column headers and values to be displayed.
        mediators = set()
        max_mname_len = len(_("MEDIATOR"))
        max_vsrc_len = len(_("VER. SRC."))
        max_version_len = len(_("VERSION"))
        max_isrc_len = len(_("IMPL. SRC."))
        for mname, values in gen_mediators:
                max_mname_len = max(max_mname_len, len(mname))
                med_version = values.get("version", "")
                max_version_len = max(max_version_len, len(med_version))
                mediators.add(mname)
                mediations[mname].append(values)

        requested_mediators = set(pargs)
        if requested_mediators:
                found = mediators & requested_mediators
                notfound = requested_mediators - found
        else:
                found = mediators
                notfound = set()

        def gen_listing():
                for mediator, mediation in (
                    (mname, mentry)
                    for mname in sorted(found)
                    for mentry in mediations[mname]
                ):
                        med_impl = mediation.get("implementation")
                        med_impl_ver = mediation.get("implementation-version")
                        if output_format == "default" and med_impl and \
                            med_impl_ver:
                                med_impl += "(@%s)" % med_impl_ver
                        yield {
                            "mediator": mediator,
                            "version": mediation.get("version"),
                            "version-source": mediation.get("version-source"),
                            "implementation": med_impl,
                            "implementation-source": mediation.get(
                                "implementation-source"),
                            "implementation-version": med_impl_ver,
                        }

        #    MEDIATOR VER. SRC.  VERSION IMPL. SRC. IMPLEMENTATION IMPL. VER.
        #    <med_1>  <src_1>    <ver_1> <src_1>    <impl_1_value> <impl_1_ver>
        #    <med_2>  <src_2>    <ver_2> <src_2>    <impl_2_value> <impl_2_ver>
        #    ...
        field_data = {
            "mediator" : [("default", "tsv"), _("MEDIATOR"), ""],
            "version" : [("default", "tsv"), _("VERSION"), ""],
            "version-source": [("default", "tsv"), _("VER. SRC."), ""],
            "implementation" : [("default", "tsv"), _("IMPLEMENTATION"), ""],
            "implementation-source": [("default", "tsv"), _("IMPL. SRC."), ""],
            "implementation-version" : [("tsv",), _("IMPL. VER."), ""],
        }
        desired_field_order = ((_("MEDIATOR"), _("VER. SRC."), _("VERSION"),
            _("IMPL. SRC."), _("IMPLEMENTATION"), _("IMPL. VER.")))

        # Default output formatting.
        def_fmt = "%-" + str(max_mname_len) + "s %-" + str(max_vsrc_len) + \
            "s %-" + str(max_version_len) + "s %-" + str(max_isrc_len) + "s %s"

        if found or (not requested_mediators and output_format == "default"):
                sys.stdout.write(misc.get_col_listing(desired_field_order,
                    field_data, gen_listing(), output_format, def_fmt,
                    omit_headers, escape_output=False))

        if found and notfound:
                return EXIT_PARTIAL
        if requested_mediators and not found:
                if output_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching mediators found"),
                            cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK

def set_mediator(op, api_inst, pargs, be_activate, be_name, med_implementation,
    med_version, new_be, noexecute, parsable_version, quiet, update_index,
    verbose):
        """Set the version and/or implementation for the specified
        mediator(s)."""

        op = "set-mediator"
        if not pargs:
                usage(_("at least one mediator must be specified"),
                    cmd=op)
        if not (med_version or med_implementation):
                usage(_("a mediator version and/or implementation must be "
                    "specified using -V and -I"), cmd=op)

        if verbose > 2:
                DebugValues.set_value("plan", "True")

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        # Now set version and/or implementation for all matching mediators.
        # The user may specify 'None' as a special value to explicitly
        # request mediations that do not have the related component.
        mediators = collections.defaultdict(dict)
        for m in pargs:
                if med_version == "":
                        # Request reset of version.
                        mediators[m]["version"] = None
                elif med_version == "None":
                        # Explicit selection of no version.
                        mediators[m]["version"] = ""
                elif med_version:
                        mediators[m]["version"] = med_version

                if med_implementation == "":
                        # Request reset of implementation.
                        mediators[m]["implementation"] = None
                elif med_implementation == "None":
                        # Explicit selection of no implementation.
                        mediators[m]["implementation"] = ""
                elif med_implementation:
                        mediators[m]["implementation"] = med_implementation

        stuff_to_do = None
        try:
                for pd in api_inst.gen_plan_set_mediators(mediators,
                    noexecute=noexecute, be_name=be_name, new_be=new_be,
                    be_activate=be_activate):
                        continue
                stuff_to_do = not api_inst.planned_nothingtodo()
        except:
                ret_code = __api_plan_exception(op, api_inst, noexecute,
                    verbose)
                if ret_code != EXIT_OK:
                        return ret_code

        if not stuff_to_do:
                if verbose:
                        __display_plan(api_inst, verbose)
                if parsable_version is not None:
                        try:
                                __display_parsable_plan(api_inst,
                                    parsable_version)
                        except api_errors.ApiException, e:
                                error(e, cmd=op)
                                return EXIT_OOPS
                else:
                        msg(_("No changes required."))
                return EXIT_NOP

        if not quiet:
                __display_plan(api_inst, verbose)
        if parsable_version is not None:
                try:
                        __display_parsable_plan(api_inst, parsable_version)
                except api_errors.ApiException, e:
                        error(e, cmd=op)
                        return EXIT_OOPS

        if noexecute:
                return EXIT_OK

        ret_code = __api_prepare(op, api_inst, accept=False)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        return ret_code

def unset_mediator(op, api_inst, pargs, be_activate, be_name,
    med_implementation, med_version, new_be, noexecute, parsable_version,quiet,
    update_index, verbose):
        """Unset the version and/or implementation for the specified
        mediator(s)."""

        op = "unset-mediator"
        if not pargs:
                usage(_("at least one mediator must be specified"),
                    cmd=op)
        if verbose > 2:
                DebugValues.set_value("plan", "True")

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        # Build dictionary of mediators to unset based on input.
        mediators = collections.defaultdict(dict)
        if not (med_version or med_implementation):
                # Unset both if nothing specific requested.
                med_version = True
                med_implementation = True

        # Now unset version and/or implementation for all matching mediators.
        for m in pargs:
                if med_version:
                        mediators[m]["version"] = None
                if med_implementation:
                        mediators[m]["implementation"] = None

        stuff_to_do = None
        try:
                for pd in api_inst.gen_plan_set_mediators(mediators,
                    noexecute=noexecute, be_name=be_name, new_be=new_be,
                    be_activate=be_activate):
                        continue
                stuff_to_do = not api_inst.planned_nothingtodo()
        except:
                ret_code = __api_plan_exception(op, api_inst, noexecute,
                    verbose)
                if ret_code != EXIT_OK:
                        return ret_code

        if not stuff_to_do:
                if verbose:
                        __display_plan(api_inst, verbose)
                if parsable_version is not None:
                        try:
                                __display_parsable_plan(api_inst,
                                    parsable_version)
                        except api_errors.ApiException, e:
                                error(e, cmd=op)
                                return EXIT_OOPS
                else:
                        msg(_("No changes required."))
                return EXIT_NOP

        if not quiet:
                __display_plan(api_inst, verbose)
        if parsable_version is not None:
                try:
                        __display_parsable_plan(api_inst, parsable_version)
                except api_errors.ApiException, e:
                        error(e, cmd=op)
                        return EXIT_OOPS

        if noexecute:
                return EXIT_OK

        ret_code = __api_prepare(op, api_inst, accept=False)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        return ret_code

def avoid(api_inst, args):
        """Place the specified packages on the avoid list"""
        if not args:
                return __display_avoids(api_inst)

        try:
                api_inst.avoid_pkgs(args)
                return EXIT_OK
        except:
                return __api_plan_exception("avoid", False, 0, api_inst)

def unavoid(api_inst, args):
        """Remove the specified packages from the avoid list"""
        if not args:
                return __display_avoids(api_inst)

        try:
                api_inst.avoid_pkgs(args, unavoid=True)
                return EXIT_OK
        except:
                return __api_plan_exception("unavoid", False, 0, api_inst)

def __display_avoids(api_inst):
        """Display the current avoid list, and the pkgs that are tracking
        that pkg"""
        for a in api_inst.get_avoid_list():
                tracking = " ".join(a[1])
                if tracking:
                        logger.info(_("    %s (group dependency of '%s')")
                            % (a[0], tracking))
                else:
                        logger.info("    %s" % a[0])

        return EXIT_OK

def freeze(api_inst, args):
        """Place the specified packages on the frozen list"""

        opts, pargs = getopt.getopt(args, "Hc:n")
        comment = None
        display_headers = True
        dry_run = False
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-c":
                        comment = arg
                elif opt == "-n":
                        dry_run = True

        if comment and not pargs:
                usage(usage_error=_("At least one package to freeze must be "
                    "given when -c is used."), cmd="freeze")
        if not display_headers and pargs:
                usage(usage_error=_("-H may only be specified when listing the "
                    "currently frozen packages."))
        if not pargs:
                return __display_cur_frozen(api_inst, display_headers)

        try:
                pfmris = api_inst.freeze_pkgs(pargs, dry_run=dry_run,
                    comment=comment)
                for pfmri in pfmris:
                        vertext = pfmri.version.get_short_version()
                        ts = pfmri.version.get_timestamp()
                        if ts:
                                vertext += ":" + pfmri.version.timestr
                        logger.info(_("%(name)s was frozen at %(ver)s") %
                            {"name": pfmri.pkg_name, "ver": vertext})
                return EXIT_OK
        except api_errors.FreezePkgsException, e:
                error("\n%s" % e, cmd="freeze")
                return EXIT_OOPS
        except:
                return __api_plan_exception("freeze", False, 0, api_inst)

def unfreeze(api_inst, args):
        """Remove the specified packages from the frozen list"""

        opts, pargs = getopt.getopt(args, "Hn")
        display_headers = True
        dry_run = False
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-n":
                        dry_run = True

        if not pargs:
                return __display_cur_frozen(api_inst, display_headers)

        try:
                pkgs = api_inst.freeze_pkgs(pargs, unfreeze=True,
                    dry_run=dry_run)
                if not pkgs:
                        return EXIT_NOP
                for s in pkgs:
                        logger.info(_("%s was unfrozen.") % s)
                return EXIT_OK
        except:
                return __api_plan_exception("unfreeze", False, 0, api_inst)

def __display_cur_frozen(api_inst, display_headers):
        """Display the current frozen list"""

        try:
                lst = sorted(api_inst.get_frozen_list())
        except api_errors.ApiException, e:
                error(e)
                return EXIT_OOPS
        if len(lst) == 0:
                return EXIT_OK

        fmt = "%(name)-18s %(ver)-27s %(time)-24s %(comment)s"
        if display_headers:
                logger.info(fmt % {
                    "name": _("NAME"),
                    "ver": _("VERSION"),
                    "time": _("DATE"),
                    "comment": _("COMMENT")
                })
        
        for pfmri, comment, timestamp in lst:
                vertext = pfmri.version.get_short_version()
                ts = pfmri.version.get_timestamp()
                if ts:
                        vertext += ":" + pfmri.version.timestr
                if not comment:
                        comment = "None"
                logger.info(fmt % {
                    "name": pfmri.pkg_name,
                    "comment": comment,
                    "time": time.strftime("%d %b %Y %H:%M:%S %Z",
                                time.localtime(timestamp)),
                    "ver": vertext
                })
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

def search(api_inst, args):
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
                        remote = True
                        servers.append({
                            "origin": misc.parse_uri(arg, cwd=orig_cwd) })
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
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
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

def info(api_inst, args):
        """Display information about a package or packages.
        """

        display_license = False
        info_local = False
        info_remote = False
        origins = set()

        opts, pargs = getopt.getopt(args, "g:lr", ["license"])
        for opt, arg in opts:
                if opt == "-g":
                        origins.add(misc.parse_uri(arg, cwd=orig_cwd))
                        info_remote = True
                elif opt == "-l":
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

        api_inst.progresstracker = get_tracker(quiet=True)

        info_needed = api.PackageInfo.ALL_OPTIONS
        if not display_license:
                info_needed = api.PackageInfo.ALL_OPTIONS - \
                    frozenset([api.PackageInfo.LICENSES])
        info_needed -= api.PackageInfo.ACTION_OPTIONS
        info_needed |= frozenset([api.PackageInfo.DEPENDENCIES])

        try:
                ret = api_inst.info(pargs, info_local, info_needed,
                    repos=origins)
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.NoPackagesInstalledException:
                error(_("no packages installed"))
                return EXIT_OOPS
        except api_errors.ApiException, e:
                error(e)
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
                if api.PackageInfo.INSTALLED in pi.states:
                        state = _("Installed")
                elif api.PackageInfo.UNSUPPORTED in pi.states:
                        state = _("Unsupported")
                else:
                        state = _("Not installed")

                lparen = False
                if api.PackageInfo.OBSOLETE in pi.states:
                        state += " (%s" % _("Obsolete")
                        lparen = True
                elif api.PackageInfo.RENAMED in pi.states:
                        state += " (%s" % _("Renamed")
                        lparen = True
                if api.PackageInfo.FROZEN in pi.states:
                        if lparen:
                                state += ", %s)" % _("Frozen")
                        else:
                                state += " (%s)" % _("Frozen")
                elif lparen:
                        state += ")"

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
                hum_ver = pi.get_attr_values("pkg.human-version")
                if hum_ver and hum_ver[0] != pi.version:
                        msg(_("       Version:"), "%s (%s)" %
                            (pi.version, hum_ver[0]))
                else:
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
                        elif attr in ("hash", "action.hash"):
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

def list_contents(api_inst, args):
        """List package contents.

        If no arguments are given, display for all locally installed packages.
        With -H omit headers and use a tab-delimited format; with -o select
        attributes to display; with -s, specify attributes to sort on; with -t,
        specify which action types to list."""

        opts, pargs = getopt.getopt(args, "Ha:g:o:s:t:mfr")

        subcommand = "contents"
        display_headers = True
        display_raw = False
        origins = set()
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
                elif opt == "-g":
                        origins.add(misc.parse_uri(arg, cwd=orig_cwd))
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

        if origins:
                remote = True
        elif not remote:
                local = True

        if remote and not pargs:
                usage(_("contents: must request remote contents for specific "
                   "packages"), cmd=subcommand)

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
                    raise_unmatched=True, return_fmris=True, variants=True,
                    repos=origins)
                manifests = []

                for pfmri, summ, cats, states, pattrs in res:
                        manifests.append(api_inst.get_manifest(pfmri,
                            all_variants=display_raw, repos=origins))
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
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
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
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

def publisher_refresh(api_inst, args):
        """Update metadata for the image's publishers."""

        # XXX will need to show available content series for each package
        full_refresh = False
        opts, pargs = getopt.getopt(args, "", ["full"])
        for opt, arg in opts:
                if opt == "--full":
                        full_refresh = True
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
        except api_errors.ImageFormatUpdateNeeded, e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                format_update_error(e)
                return EXIT_OOPS, ""
        except api_errors.ApiException, e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                return EXIT_OOPS, ("\n" + str(e))

def publisher_set(api_inst, args):
        """pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert] [--reset-uuid]
            [-g|--add-origin origin to add] [-G|--remove-origin origin to
            remove] [-m|--add-mirror mirror to add] [-M|--remove-mirror mirror
            to remove] [-p repo_uri] [--enable] [--disable] [--no-refresh]
            [--sticky] [--non-sticky ] [--search-before=publisher]
            [--search-after=publisher]
            [--approve-ca-cert path to CA]
            [--revoke-ca-cert hash of CA to remove]
            [--unset-ca-cert hash of CA to unset]
            [--set-property name of property=value]
            [--add-property-value name of property=value to add]
            [--remove-property-value name of property=value to remove]
            [--unset-property name of property to delete]
            [publisher] """

        cmd_name = "set-publisher"

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
        search_first = False
        repo_uri = None

        approved_ca_certs = []
        revoked_ca_certs = []
        unset_ca_certs = []
        set_props = {}
        add_prop_values = {}
        remove_prop_values = {}
        unset_props = set()

        opts, pargs = getopt.getopt(args, "Pedk:c:O:G:g:M:m:p:",
            ["add-mirror=", "remove-mirror=", "add-origin=", "remove-origin=",
            "no-refresh", "reset-uuid", "enable", "disable", "sticky",
            "non-sticky", "search-after=", "search-before=", "search-first",
            "approve-ca-cert=", "revoke-ca-cert=", "unset-ca-cert=",
            "set-property=", "add-property-value=", "remove-property-value=",
            "unset-property="])

        for opt, arg in opts:
                if opt == "-c":
                        ssl_cert = arg
                elif opt == "-d" or opt == "--disable":
                        disable = True
                elif opt == "-e" or opt == "--enable":
                        disable = False
                elif opt == "-g" or opt == "--add-origin":
                        add_origins.add(misc.parse_uri(arg, cwd=orig_cwd))
                elif opt == "-G" or opt == "--remove-origin":
                        if arg == "*":
                                # Allow wildcard to support an easy, scriptable
                                # way of removing all existing entries.
                                remove_origins.add("*")
                        else:
                                remove_origins.add(misc.parse_uri(arg,
                                    cwd=orig_cwd))
                elif opt == "-k":
                        ssl_key = arg
                elif opt == "-O":
                        origin_uri = arg
                elif opt == "-m" or opt == "--add-mirror":
                        add_mirrors.add(misc.parse_uri(arg, cwd=orig_cwd))
                elif opt == "-M" or opt == "--remove-mirror":
                        if arg == "*":
                                # Allow wildcard to support an easy, scriptable
                                # way of removing all existing entries.
                                remove_mirrors.add("*")
                        else:
                                remove_mirrors.add(misc.parse_uri(arg,
                                    cwd=orig_cwd))
                elif opt == "-p":
                        repo_uri = misc.parse_uri(arg, cwd=orig_cwd)
                elif opt in ("-P", "--search-first"):
                        search_first = True
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
                elif opt == "--approve-ca-cert":
                        approved_ca_certs.append(arg)
                elif opt == "--revoke-ca-cert":
                        revoked_ca_certs.append(arg)
                elif opt == "--unset-ca-cert":
                        unset_ca_certs.append(arg)
                elif opt == "--set-property":
                        t = arg.split("=", 1)
                        if len(t) < 2:
                                usage(_("properties to be set must be of the "
                                    "form '<name>=<value>'. This is what was "
                                    "given: %s") % arg, cmd=cmd_name)
                        if t[0] in set_props:
                                usage(_("a property may only be set once in a "
                                    "command. %s was set twice") % t[0],
                                    cmd=cmd_name)
                        set_props[t[0]] = t[1]
                elif opt == "--add-property-value":
                        t = arg.split("=", 1)
                        if len(t) < 2:
                                usage(_("property values to be added must be "
                                    "of the form '<name>=<value>'. This is "
                                    "what was given: %s") % arg, cmd=cmd_name)
                        add_prop_values.setdefault(t[0], [])
                        add_prop_values[t[0]].append(t[1])
                elif opt == "--remove-property-value":
                        t = arg.split("=", 1)
                        if len(t) < 2:
                                usage(_("property values to be removed must be "
                                    "of the form '<name>=<value>'. This is "
                                    "what was given: %s") % arg, cmd=cmd_name)
                        remove_prop_values.setdefault(t[0], [])
                        remove_prop_values[t[0]].append(t[1])
                elif opt == "--unset-property":
                        unset_props.add(arg)

        name = None
        if len(pargs) == 0 and not repo_uri:
                usage(_("requires a publisher name"), cmd="set-publisher")
        elif len(pargs) > 1:
                usage(_("only one publisher name may be specified"),
                    cmd="set-publisher")
        elif pargs:
                name = pargs[0]

        if origin_uri and (add_origins or remove_origins):
                usage(_("the -O and -g, --add-origin, -G, or --remove-origin "
                    "options may not be combined"), cmd="set-publisher")

        if (search_before and search_after) or \
            (search_before and search_first) or (search_after and search_first):
                usage(_("search-before, search-after, and search-first (-P) "
                    "may not be combined"), cmd="set-publisher")

        if repo_uri and (add_origins or add_mirrors or remove_origins or
            remove_mirrors or disable != None or not refresh_allowed or
            reset_uuid):
                usage(_("the -p option may not be combined with the -g, "
                    "--add-origin, -G, --remove-origin, -m, --add-mirror, "
                    "-M, --remove-mirror, --enable, --disable, --no-refresh, "
                    "or --reset-uuid options"), cmd="set-publisher")

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
                    search_after=search_after, search_first=search_first,
                    reset_uuid=reset_uuid, refresh_allowed=refresh_allowed,
                    set_props=set_props, add_prop_values=add_prop_values,
                    remove_prop_values=remove_prop_values,
                    unset_props=unset_props, approved_cas=approved_ca_certs,
                    revoked_cas=revoked_ca_certs, unset_cas=unset_ca_certs)

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

        for src_pub in sorted(pubs):
                prefix = src_pub.prefix
                if name and prefix != name:
                        # User didn't request this one.
                        continue

                src_repo = src_pub.repository
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
                            search_before=search_before,
                            search_first=search_first,
                            set_props=set_props,
                            add_prop_values=add_prop_values,
                            remove_prop_values=remove_prop_values,
                            unset_props=unset_props)
                        if rval == EXIT_OK:
                                added.append(prefix)

                        # When multiple publishers result from a single -p
                        # operation, this ensures that the new publishers are
                        # ordered correctly.
                        search_first = False
                        search_after = prefix
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
                        dest_repo = dest_pub.repository

                        if dest_repo.origins and \
                            not dest_repo.has_origin(repo_uri):
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
                                if not dest_repo.origins:
                                        add_origins = [repo_uri]
                                else:
                                        add_origins = []
                                add_mirrors = []
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
                            add_mirrors=add_mirrors, add_origins=add_origins,
                            set_props=set_props,
                            add_prop_values=add_prop_values,
                            remove_prop_values=remove_prop_values,
                            unset_props=unset_props)

                        if rval == EXIT_OK:
                                updated.append(prefix)

                if rval != EXIT_OK:
                        failed.append((prefix, rmsg))
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
    search_before=None, search_after=None, search_first=False,
    reset_uuid=None, refresh_allowed=False,
    set_props=EmptyI, add_prop_values=EmptyI,
    remove_prop_values=EmptyI, unset_props=EmptyI, approved_cas=EmptyI,
    revoked_cas=EmptyI, unset_cas=EmptyI):

        repo = None
        new_pub = False
        if not pub:
                try:
                        pub = api_inst.get_publisher(prefix=prefix,
                            alias=prefix, duplicate=True)
                        if reset_uuid:
                                pub.reset_client_uuid()
                        repo = pub.repository
                except api_errors.UnknownPublisher, e:
                        if not origin_uri and not add_origins and \
                            (remove_origins or remove_mirrors or
                            remove_prop_values or add_mirrors):
                                return EXIT_OOPS, str(e)

                        # No pre-existing, so create a new one.
                        repo = publisher.Repository()
                        pub = publisher.Publisher(prefix, repository=repo)
                        new_pub = True
        elif not api_inst.has_publisher(prefix=pub.prefix):
                new_pub = True

        if not repo:
                repo = pub.repository
                if not repo:
                        # Could be a new publisher from auto-configuration
                        # case where no origin was provided in repository
                        # configuration.
                        repo = publisher.Repository()
                        pub.repository = repo

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
                    any(origin_uri.startswith(scheme + ":")
                        for scheme in publisher.SSL_SCHEMES):

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

        for entry in (("mirror", add_mirrors, remove_mirrors), ("origin",
            add_origins, remove_origins)):
                etype, add, remove = entry
                # XXX once image configuration supports storing this
                # information at the uri level, ssl info should be set
                # here.
                if "*" in remove:
                        getattr(repo, "reset_%ss" % etype)()
                else:
                        for u in remove:
                                getattr(repo, "remove_%s" % etype)(u)

                for u in add:
                        getattr(repo, "add_%s" % etype)(u)

        # None is checked for here so that a client can unset a ssl_cert or
        # ssl_key by using -k "" or -c "".
        if ssl_cert is not None or ssl_key is not None:
                # Assume the user wanted to update the ssl_cert or ssl_key
                # information for *all* of the currently selected
                # repository's origins and mirrors that use SSL schemes.
                found_ssl = False
                for uri in repo.origins:
                        if uri.scheme not in publisher.SSL_SCHEMES:
                                continue
                        found_ssl = True
                        if ssl_cert is not None:
                                uri.ssl_cert = ssl_cert
                        if ssl_key is not None:
                                uri.ssl_key = ssl_key
                for uri in repo.mirrors:
                        if uri.scheme not in publisher.SSL_SCHEMES:
                                continue
                        found_ssl = True
                        if ssl_cert is not None:
                                uri.ssl_cert = ssl_cert
                        if ssl_key is not None:
                                uri.ssl_key = ssl_key

                if (ssl_cert or ssl_key) and not found_ssl:
                        # None of the origins or mirrors for the publisher
                        # use SSL schemes so the cert and key information
                        # won't be retained.
                        usage(_("Publisher '%s' does not have any SSL-based "
                            "origins or mirrors.") % prefix)

        if set_props or add_prop_values or remove_prop_values or unset_props:
                pub.update_props(set_props=set_props,
                    add_prop_values=add_prop_values,
                    remove_prop_values=remove_prop_values,
                    unset_props=unset_props)

        if new_pub:
                api_inst.add_publisher(pub,
                    refresh_allowed=refresh_allowed, approved_cas=approved_cas,
                    revoked_cas=revoked_cas, unset_cas=unset_cas,
                    search_after=search_after, search_before=search_before,
                    search_first=search_first)
        else:
                for ca in approved_cas:
                        try:
                                ca = os.path.normpath(
                                    os.path.join(orig_cwd, ca))
                                with open(ca, "rb") as fh:
                                        s = fh.read()
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT:
                                        raise api_errors.MissingFileArgumentException(
                                            ca)
                                elif e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            ca)
                                raise
                        pub.approve_ca_cert(s)

                for hsh in revoked_cas:
                        pub.revoke_ca_cert(hsh)

                for hsh in unset_cas:
                        pub.unset_ca_cert(hsh)

                api_inst.update_publisher(pub,
                    refresh_allowed=refresh_allowed, search_after=search_after,
                    search_before=search_before, search_first=search_first)

        return EXIT_OK, None

def publisher_unset(api_inst, args):
        """pkg unset-publisher publisher ..."""

        if len(args) == 0:
                usage(_("at least one publisher must be specified"),
                    cmd="unset-publisher")

        errors = []
        for name in args:
                try:
                        api_inst.remove_publisher(prefix=name, alias=name)
                except api_errors.ImageFormatUpdateNeeded, e:
                        format_update_error(e)
                        return EXIT_OOPS
                except (api_errors.PermissionsException,
                    api_errors.PublisherError,
                    api_errors.ModifyingSyspubException), e:
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

def publisher_list(api_inst, args):
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
            "enabled" : [("tsv"), _("ENABLED"), ""],
            "syspub" : [("tsv"), _("SYSPUB"), ""]
        }

        desired_field_order = (_("PUBLISHER"), "", _("STICKY"),
                               _("SYSPUB"), _("ENABLED"), _("TYPE"),
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

        api_inst.progresstracker = get_tracker(quiet=True)

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
                pref_pub = api_inst.get_highest_ranked_publisher()
                if preferred_only:
                        pubs = [pref_pub]
                else:
                        pubs = [
                            p for p in api_inst.get_publishers()
                            if inc_disabled or not p.disabled
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

                                if p.disabled:
                                        pstatus_list.append(_("disabled"))
                                if p.sys_pub:
                                        pstatus_list.append(_("syspub"))
                                if pstatus_list:
                                        pstatus = "(%s)" % \
                                            ", ".join(pstatus_list)
                                set_value(field_data["attrs"], pstatus)

                        if p.sticky:
                                set_value(field_data["sticky"], _("true"))
                        else:
                                set_value(field_data["sticky"], _("false"))
                        if not p.disabled:
                                set_value(field_data["enabled"], _("true"))
                        else:
                                set_value(field_data["enabled"], _("false"))
                        if p.sys_pub:
                                set_value(field_data["syspub"], _("true"))
                        else:
                                set_value(field_data["syspub"], _("false"))

                        # Only show the selected repository's information in
                        # summary view.
                        r = p.repository

                        # Update field_data for each origin and output
                        # a publisher record in our desired format.
                        for uri in sorted(r.origins):
                                # XXX get the real origin status
                                set_value(field_data["type"], _("origin"))
                                set_value(field_data["status"], _("online"))
                                set_value(field_data["uri"], str(uri))
                                values = map(get_value,
                                    sorted(filter(filter_func,
                                    field_data.values()), sort_fields)
                                )
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
                                    field_data.values()), sort_fields)
                                )
                                msg(fmt % tuple(values))

                        if not r.origins and not r.mirrors:
                                set_value(field_data["type"], "")
                                set_value(field_data["status"], "")
                                set_value(field_data["uri"], "")
                                values = map(get_value,
                                    sorted(filter(filter_func,
                                    field_data.values()), sort_fields)
                                )
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

                def display_signing_certs(p):
                        if p.approved_ca_certs:
                                msg(_("         Approved CAs:"),
                                    p.approved_ca_certs[0])
                                for h in p.approved_ca_certs[1:]:
                                        msg(_("                     :"), h)
                        if p.revoked_ca_certs:
                                msg(_("          Revoked CAs:"),
                                    p.revoked_ca_certs[0])
                                for h in p.revoked_ca_certs[1:]:
                                        msg(_("                     :"), h)

                for name in pargs:
                        # detailed print
                        pub = api_inst.get_publisher(prefix=name, alias=name)
                        dt = api_inst.get_publisher_last_update_time(pub.prefix)
                        if dt:
                                dt = dt.strftime("%c")

                        msg("")
                        msg(_("            Publisher:"), pub.prefix)
                        msg(_("                Alias:"), pub.alias)

                        rval = display_repository(pub.repository)
                        if rval != 0:
                                # There was an error in displaying some
                                # of the information about a repository.
                                # However, continue on.
                                retcode = rval

                        msg(_("          Client UUID:"), pub.client_uuid)
                        msg(_("      Catalog Updated:"), dt)
                        display_signing_certs(pub)
                        if pub.disabled:
                                msg(_("              Enabled:"), _("No"))
                        else:
                                msg(_("              Enabled:"), _("Yes"))
                        msg(_("     Signature Policy:"), pub.signature_policy.name)
                        if "signature-required-names" in pub.properties:
                                names = pub.properties["signature-required-names"]
                                if names:
                                        msg(_("  Sig. Required Names:"), names[0])
                                        for n in names[1:]:
                                                msg(_("                     :"), n)
        return retcode

def property_add_value(api_inst, args):
        """pkg add-property-value propname propvalue"""

        # ensure no options are passed in
        subcommand = "add-property-value"
        opts, pargs = getopt.getopt(args, "")
        try:
                propname, propvalue = pargs
        except ValueError:
                usage(_("requires a property name and value"), cmd=subcommand)

        # XXX image property management should be in pkg.client.api
        try:
                img.add_property_value(propname, propvalue)
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException, e:
                error(str(e), cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK

def property_remove_value(api_inst, args):
        """pkg remove-property-value propname propvalue"""

        # ensure no options are passed in
        subcommand = "remove-property-value"
        opts, pargs = getopt.getopt(args, "")
        try:
                propname, propvalue = pargs
        except ValueError:
                usage(_("requires a property name and value"), cmd=subcommand)

        # XXX image property management should be in pkg.client.api
        try:
                img.remove_property_value(propname, propvalue)
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException, e:
                error(str(e), cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK

def property_set(api_inst, args):
        """pkg set-property propname propvalue [propvalue ...]"""

        # ensure no options are passed in
        subcommand = "set-property"
        opts, pargs = getopt.getopt(args, "")
        try:
                propname = pargs[0]
                propvalues = pargs[1:]
        except IndexError:
                propvalues = []
        if len(propvalues) == 0:
                usage(_("requires a property name and at least one value"),
                    cmd=subcommand)
        elif propname not in ("publisher-search-order",
            "signature-policy", "signature-required-names") and \
            len(propvalues) == 1:
                # All other properties are single value, so if only one (or no)
                # value was specified, transform it.  If multiple values were
                # specified, allow the value to be passed on so that the
                # configuration classes can re-raise the appropriate error.
                propvalues = propvalues[0]

        props = { propname: propvalues }
        if propname == "signature-policy":
                policy = propvalues[0]
                props[propname] = policy
                params = propvalues[1:]
                if policy != "require-names" and len(params):
                        usage(_("Signature-policy %s doesn't allow additional "
                            "parameters.") % policy, cmd=subcommand)
                elif policy == "require-names":
                        props["signature-required-names"] = params

        # XXX image property management should be in pkg.client.api
        try:
                img.set_properties(props)
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException, e:
                error(str(e), cmd=subcommand)
                return EXIT_OOPS
        return EXIT_OK

def property_unset(api_inst, args):
        """pkg unset-property propname ..."""

        # is this an existing property in our image?
        # if so, delete it
        # if not, error

        # ensure no options are passed in
        subcommand = "unset-property"
        opts, pargs = getopt.getopt(args, "")
        if not pargs:
                usage(_("requires at least one property name"),
                    cmd=subcommand)

        # XXX image property management should be in pkg.client.api
        for p in pargs:
                try:
                        img.delete_property(p)
                except api_errors.ImageFormatUpdateNeeded, e:
                        format_update_error(e)
                        return EXIT_OOPS
                except api_errors.ApiException, e:
                        error(str(e), cmd=subcommand)
                        return EXIT_OOPS

        return EXIT_OK

def property_list(api_inst, args):
        """pkg property [-H] [propname ...]"""
        omit_headers = False

        subcommand = "property"
        opts, pargs = getopt.getopt(args, "H")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        # XXX image property management should be in pkg.client.api
        for p in pargs:
                if not img.has_property(p):
                        error(_("no such property: %s") % p, cmd=subcommand)
                        return EXIT_OOPS

        if not pargs:
                # If specific properties were named, list them in the order
                # requested; otherwise, list them sorted.
                pargs = sorted(list(img.properties()))

        width = max(max([len(p) for p in pargs]), 8)
        fmt = "%%-%ss %%s" % width
        if not omit_headers:
                msg(fmt % ("PROPERTY", "VALUE"))

        for p in pargs:
                msg(fmt % (p, img.get_property(p)))

        return EXIT_OK

def variant_list(api_inst, args):
        """pkg variant [-H] [<variant_spec>]"""

        omit_headers = False

        opts, pargs = getopt.getopt(args, "H")

        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        # XXX image variants should be accessible through pkg.client.api
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

def facet_list(api_inst, args):
        """pkg facet [-H] [<facet_spec>]"""

        omit_headers = False

        opts, pargs = getopt.getopt(args, "H")

        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True

        # XXX image facets should be accessible through pkg.client.api
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

def list_linked(op, api_inst, pargs,
    li_ignore, omit_headers):
        """pkg list-linked [-H]

        List all the linked images known to the current image."""

        api_inst.progresstracker = get_tracker(quiet=omit_headers)

        if li_ignore and type(li_ignore) == list:
                li_ignore = api_inst.parse_linked_name_list(li_ignore)

        li_list = api_inst.list_linked(li_ignore)
        if len(li_list) == 0:
                return EXIT_OK

        fmt = ""
        li_header = [_("NAME"), _("RELATIONSHIP"), _("PATH")]
        for col in range(0, len(li_header)):
                width = max([len(row[col]) for row in li_list])
                width = max(width, len(li_header[col]))
                if (fmt != ''):
                        fmt += "\t"
                fmt += "%%-%ss" % width

        if not omit_headers:
                msg(fmt % tuple(li_header))
        for row in li_list:
                msg(fmt % tuple(row))
        return EXIT_OK

def __parse_linked_props(args, op):
        """"Parse linked image property options that were specified on the
        command line into a dictionary.  Make sure duplicate properties were
        not specified."""

        linked_props = dict()
        for pv in args:
                try:
                        p, v = pv.split("=", 1)
                except ValueError:
                        usage(_("linked image property arguments must be of "
                            "the form '<name>=<value>'."), cmd=op)

                if p not in li.prop_values:
                        usage(_("invalid linked image property: '%s'.") % p,
                            cmd=op)

                if p in linked_props:
                        usage(_("linked image property specified multiple "
                            "times: '%s'.") % p, cmd=op)

                linked_props[p] = v

        return linked_props

def list_property_linked(op, api_inst, pargs,
    li_name, omit_headers):
        """pkg property-linked [-H] [-l <li-name>] [propname ...]

        List the linked image properties associated with a child or parent
        image."""

        api_inst.progresstracker = get_tracker(quiet=omit_headers)

        lin=None
        if li_name:
                lin = api_inst.parse_linked_name(li_name)
        props = api_inst.get_linked_props(lin=lin)

        for p in pargs:
                if p not in props.keys():
                        error(_("%(op)s: no such property: %(p)s") %
                            {"op": op, "p": p})
                        return EXIT_OOPS

        if len(props) == 0:
                return EXIT_OK

        if not pargs:
                pargs = props.keys()

        width = max(max([len(p) for p in pargs if props[p]]), 8)
        fmt = "%%-%ss\t%%s" % width
        if not omit_headers:
                msg(fmt % ("PROPERTY", "VALUE"))
        for p in sorted(pargs):
                if not props[p]:
                        continue
                msg(fmt % (p, props[p]))

        return EXIT_OK

def set_property_linked(op, api_inst, pargs,
    accept, be_activate, be_name, li_ignore, li_md_only, li_name,
    li_parent_sync, li_pkg_updates, new_be, noexecute, origins,
    parsable_version, quiet, refresh_catalogs, reject_pats, show_licenses,
    update_index, verbose):
        """pkg set-property-linked
            [-nvq] [--accept] [--licenses] [--no-index] [--no-refresh]
            [--no-parent-sync] [--no-pkg-updates]
            [--linked-md-only] <propname>=<propvalue> ...

        Change the specified linked image properties.  This may result in
        updating the package contents of a child image."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        # make sure we're a child image
        if li_name:
                lin = api_inst.parse_linked_name(li_name)
        else:
                lin = api_inst.get_linked_name()

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        LIXXX

def audit_linked(op, api_inst, pargs,
    li_parent_sync, li_target_all, li_target_list, omit_headers, quiet):
        """pkg audit-linked [-a|-l <li-name>]

        Audit one or more child images to see if they are in sync
        with their parent image."""

        api_inst.progresstracker = get_tracker(quiet=omit_headers)

        li_target_list = api_inst.parse_linked_name_list(li_target_list)

        # audit the requested child image(s)
        if not li_target_all and not li_target_list:
                # audit the current image
                rvdict = api_inst.audit_linked(li_parent_sync=li_parent_sync)
        else:
                # audit the requested child image(s)
                rvdict = api_inst.audit_linked_children(li_target_list)
                if not rvdict:
                        # may not have had any children
                        return EXIT_OK

        # display audit return values
        width = max(max([len(k) for k in rvdict.keys()]), 8)
        fmt = "%%-%ss\t%%s" % width
        if not omit_headers:
                msg(fmt % ("NAME", "STATUS"))

        if not quiet:
                for k, (rv, err, p_dict) in rvdict.items():
                        if rv == EXIT_OK:
                                msg(fmt % (k, _("synced")))
                        elif rv == EXIT_DIVERGED:
                                msg(fmt % (k, _("diverged")))

        rv, err, p_dicts = api_inst.audit_linked_rvdict2rv(rvdict)
        if err:
                error(err, cmd=op)
        return rv

def sync_linked(op, api_inst, pargs,
    accept, be_activate, be_name, li_ignore, li_parent_sync, new_be,
    noexecute, origins, parsable_version, quiet, refresh_catalogs, reject_pats,
    show_licenses, update_index, verbose, li_md_only, li_pkg_updates,
    li_target_all, li_target_list, stage):

        """pkg audit-linked [-a|-l <li-name>]
            [-nvq] [--accept] [--licenses] [--no-index] [--no-refresh]
            [--no-parent-sync] [--no-pkg-updates]
            [--linked-md-only] [-a|-l <name>]

        Sync one or more child images with their parent image."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        api_inst.set_stage(stage)

        li_target_list = api_inst.parse_linked_name_list(li_target_list)

        if not li_target_all and not li_target_list:
                # sync the current image
                return __api_op(op, api_inst, _accept=accept,
                    _li_ignore=li_ignore, _noexecute=noexecute,
                    _origins=origins, _parsable_version=parsable_version,
                    _quiet=quiet, _show_licenses=show_licenses, _stage=stage,
                    _verbose=verbose, be_activate=be_activate,
                    be_name=be_name, li_md_only=li_md_only,
                    li_parent_sync=li_parent_sync,
                    li_pkg_updates=li_pkg_updates, new_be=new_be,
                    refresh_catalogs=refresh_catalogs,
                    reject_list=reject_pats,
                    update_index=update_index)

        # sync the requested child image(s)
        rvdict = api_inst.sync_linked_children(li_target_list,
            noexecute=noexecute, accept=accept, show_licenses=show_licenses,
            refresh_catalogs=refresh_catalogs, update_index=update_index,
            li_pkg_updates=li_pkg_updates, li_md_only=li_md_only)

        rv, err, p_dicts = api_inst.sync_linked_rvdict2rv(rvdict)
        if err:
                error(err, cmd=op)
        if parsable_version is not None and rv == EXIT_OK:
                try:
                        __display_parsable_plan(api_inst, parsable_version,
                            p_dicts)
                except api_errors.ApiException, e:
                        error(e, cmd=op)
                        return EXIT_OOPS
        return rv

def attach_linked(op, api_inst, pargs,
    accept, allow_relink, attach_child, attach_parent, be_activate,
    be_name, force, li_ignore, li_md_only, li_parent_sync, li_pkg_updates,
    li_props, new_be, noexecute, origins, parsable_version, quiet,
    refresh_catalogs, reject_pats, show_licenses, update_index, verbose):
        """pkg attach-linked
            [-fnvq] [--accept] [--licenses] [--no-index] [--no-refresh]
            [--no-pkg-updates] [--linked-md-only]
            [--allow-relink]
            [--parsable-version=<version>]
            [--prop-linked <propname>=<propvalue> ...]
            (-c|-p) <li-name> <dir>

        Attach a child linked image.  The child could be this image attaching
        itself to a parent, or another image being attach as a child with
        this image being the parent."""

        api_inst.progresstracker = get_tracker(
            parsable_version=parsable_version, quiet=quiet, verbose=verbose)

        for k, v in li_props:
                if k in [li.PROP_PATH, li.PROP_NAME, li.PROP_MODEL]:
                        usage(_("cannot specify linked image property: '%s'") %
                            k, cmd=op)

        if len(pargs) < 2:
                usage(_("a linked image name and path must be specified"),
                    cmd=op)

        li_name = pargs[0]
        li_path = pargs[1]

        # parse the specified name
        lin = api_inst.parse_linked_name(li_name, allow_unknown=True)

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        if attach_parent:
                # attach the current image to a parent
                return __api_op(op, api_inst, _accept=accept,
                    _li_ignore=li_ignore, _noexecute=noexecute,
                    _origins=origins, _parsable_version=parsable_version,
                    _quiet=quiet, _show_licenses=show_licenses,
                    _verbose=verbose, allow_relink=allow_relink,
                    be_activate=be_activate, be_name=be_name, force=force,
                    li_md_only=li_md_only, li_path=li_path,
                    li_pkg_updates=li_pkg_updates, li_props=li_props,
                    lin=lin, new_be=new_be, refresh_catalogs=refresh_catalogs,
                    reject_list=reject_pats, update_index=update_index)

        # attach the requested child image
        (rv, err, p_dict) = api_inst.attach_linked_child(lin, li_path, li_props,
            accept=accept, allow_relink=allow_relink, force=force,
            li_md_only=li_md_only, li_pkg_updates=li_pkg_updates,
            noexecute=noexecute, refresh_catalogs=refresh_catalogs,
            reject_list=reject_pats, show_licenses=show_licenses,
            update_index=update_index)

        if err:
                error(err, cmd=op)
        if parsable_version is not None and rv == EXIT_OK:
                assert p_dict is not None
                try:
                        __display_parsable_plan(api_inst, parsable_version,
                            [p_dict])
                except api_errors.ApiException, e:
                        error(e, cmd=op)
                        return EXIT_OOPS
        return rv

def detach_linked(op, api_inst, pargs, force, li_target_all, li_target_list,
    noexecute, quiet, verbose):
        """pkg detach-linked
            [-fnvq] [-a|-l <li-name>] [--linked-md-only]

        Detach one or more child linked images."""

        api_inst.progresstracker = get_tracker(quiet=quiet, verbose=verbose)

        li_target_list = api_inst.parse_linked_name_list(li_target_list)

        if not li_target_all and not li_target_list:
                # detach the current image
                return __api_op(op, api_inst, _noexecute=noexecute,
                    _quiet=quiet, _verbose=verbose, force=force)

        # detach the requested child image(s)
        rvdict = api_inst.detach_linked_children(li_target_list, force=force,
            noexecute=noexecute)

        rv, err, p_dicts = api_inst.detach_linked_rvdict2rv(rvdict)
        if err:
                error(err, cmd=op)
        return rv

def image_create(args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial publisher for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        cmd_name = "image-create"

        force = False
        imgtype = IMG_TYPE_USER
        is_zone = False
        add_mirrors = set()
        add_origins = set()
        pub_name = None
        pub_url = None
        refresh_allowed = True
        ssl_key = None
        ssl_cert = None
        variants = {}
        facets = pkg.facet.Facets()
        set_props = {}
        version = None

        opts, pargs = getopt.getopt(args, "fFPUza:g:m:p:k:c:",
            ["force", "full", "partial", "user", "zone", "authority=", "facet=",
                "mirror=", "origin=", "publisher=", "no-refresh", "variant=",
                "set-property="])

        for opt, arg in opts:
                # -a is deprecated and will be removed at a future date.
                if opt in ("-a", "-p", "--publisher"):
                        pub_url = None
                        try:
                                pub_name, pub_url = arg.split("=", 1)
                        except ValueError:
                                pub_name = None
                                pub_url = arg
                        if pub_url:
                                pub_url = misc.parse_uri(pub_url, cwd=orig_cwd)
                elif opt == "-c":
                        ssl_cert = arg
                elif opt == "-f" or opt == "--force":
                        force = True
                elif opt in ("-g", "--origin"):
                        add_origins.add(misc.parse_uri(arg, cwd=orig_cwd))
                elif opt == "-k":
                        ssl_key = arg
                elif opt in ("-m", "--mirror"):
                        add_mirrors.add(misc.parse_uri(arg, cwd=orig_cwd))
                elif opt == "-z" or opt == "--zone":
                        is_zone = True
                        imgtype = IMG_TYPE_ENTIRE
                elif opt == "-F" or opt == "--full":
                        imgtype = IMG_TYPE_ENTIRE
                elif opt == "-P" or opt == "--partial":
                        imgtype = IMG_TYPE_PARTIAL
                elif opt == "-U" or opt == "--user":
                        imgtype = IMG_TYPE_USER
                elif opt == "--facet":
                        allow = { "TRUE": True, "FALSE": False }
                        try:
                                f_name, f_value = arg.split("=", 1)
                        except ValueError:
                                f_name = arg
                                f_value = ""
                        if not f_name.startswith("facet."):
                                f_name = "facet.%s" % f_name
                        if not f_name or f_value.upper() not in allow:
                                usage(_("Facet arguments must be of the "
                                    "form '<name>=(True|False)'"),
                                    cmd=cmd_name)
                        facets[f_name] = allow[f_value.upper()]
                elif opt == "--no-refresh":
                        refresh_allowed = False
                elif opt == "--set-property":
                        t = arg.split("=", 1)
                        if len(t) < 2:
                                usage(_("properties to be set must be of the "
                                    "form '<name>=<value>'. This is what was "
                                    "given: %s") % arg, cmd=cmd_name)
                        if t[0] in set_props:
                                usage(_("a property may only be set once in a "
                                    "command. %s was set twice") % t[0],
                                    cmd=cmd_name)
                        set_props[t[0]] = t[1]
                elif opt == "--variant":
                        try:
                                v_name, v_value = arg.split("=", 1)
                                if not v_name.startswith("variant."):
                                        v_name = "variant.%s" % v_name
                        except ValueError:
                                usage(_("variant arguments must be of the "
                                    "form '<name>=<value>'."),
                                    cmd=cmd_name)
                        variants[v_name] = v_value

        if not pargs:
                usage(_("an image directory path must be specified"),
                    cmd=cmd_name)
        elif len(pargs) > 1:
                usage(_("only one image directory path may be specified"),
                    cmd=cmd_name)
        image_dir = pargs[0]

        if not pub_name and not refresh_allowed:
                usage(_("--no-refresh cannot be used with -p unless a "
                    "publisher prefix is provided."), cmd=cmd_name)

        if not refresh_allowed and pub_url:
                # Auto-config can't be done if refresh isn't allowed, so treat
                # this as a manual configuration case.
                add_origins.add(pub_url)
                repo_uri = None
        else:
                repo_uri = pub_url

        # Get sanitized SSL Cert/Key input values.
        ssl_cert, ssl_key = _get_ssl_cert_key(image_dir, is_zone, ssl_cert,
            ssl_key)

        global img
        try:
                progtrack = get_tracker()
                api_inst = api.image_create(PKG_CLIENT_NAME, CLIENT_API_VERSION,
                    image_dir, imgtype, is_zone, facets=facets, force=force,
                    mirrors=list(add_mirrors), origins=list(add_origins),
                    prefix=pub_name, progtrack=progtrack,
                    refresh_allowed=refresh_allowed, ssl_cert=ssl_cert,
                    ssl_key=ssl_key, repo_uri=repo_uri, variants=variants,
                    props=set_props)
                img = api_inst.img
        except api_errors.InvalidDepotResponseException, e:
                # Ensure messages are displayed after the spinner.
                logger.error("\n")
                error(_("The URI '%(pub_url)s' does not appear to point to a "
                    "valid pkg repository.\nPlease check the repository's "
                    "location and the client's network configuration."
                    "\nAdditional details:\n\n%(error)s") %
                    { "pub_url": pub_url, "error": e },
                    cmd=cmd_name)
                print_proxy_config()
                return EXIT_OOPS
        except api_errors.CatalogRefreshException, cre:
                # Ensure messages are displayed after the spinner.
                error("", cmd=cmd_name)
                if display_catalog_failures(cre) == 0:
                        return EXIT_OOPS
                else:
                        return EXIT_PARTIAL
        except api_errors.ApiException, e:
                error(str(e), cmd=cmd_name)
                return EXIT_OOPS
        return EXIT_OK

def rebuild_index(api_inst, pargs):
        """pkg rebuild-index

        Forcibly rebuild the search indexes. Will remove existing indexes
        and build new ones from scratch."""

        if pargs:
                usage(_("command does not take operands ('%s')") % \
                    " ".join(pargs), cmd="rebuild-index")

        try:
                api_inst.rebuild_search_index()
        except api_errors.ImageFormatUpdateNeeded, e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.CorruptedIndexException:
                error("The search index appears corrupted.  Please rebuild the "
                    "index with 'pkg rebuild-index'.", cmd="rebuild-index")
                return EXIT_OOPS
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e))
                error(_("\n(Failure to consistently execute pkg commands as a "
                    "privileged user is often a source of this problem.)"))
                return EXIT_OOPS
        else:
                return EXIT_OK

def history_list(api_inst, args):
        """Display history about the current image.
        """
        # define column name, header, field width and <History> attribute name
        # we compute 'reason' and 'time' columns ourselves
        history_cols = {
            "be": (_("BE"), "%-20s", "operation_be"),
            "be_uuid": (_("BE UUID"), "%-41s", "operation_be_uuid"),
            "client": (_("CLIENT"), "%-19s", "client_name"),
            "client_ver": (_("VERSION"), "%-15s", "client_version"),
            "command": (_("COMMAND"), "%s", "client_args"),
            "finish": (_("FINISH"), "%-25s", "operation_end_time"),
            "id": (_("ID"), "%-10s", "operation_userid"),
            "new_be": (_("NEW BE"), "%-20s", "operation_new_be"),
            "new_be_uuid": (_("NEW BE UUID"), "%-41s", "operation_new_be_uuid"),
            "operation": (_("OPERATION"), "%-25s", "operation_name"),
            "outcome": (_("OUTCOME"), "%-12s", "operation_result"),
            "reason": (_("REASON"), "%-10s", None),
            "snapshot": (_("SNAPSHOT"), "%-20s", "operation_snapshot"),
            "start": (_("START"), "%-25s", "operation_start_time"),
            "time": (_("TIME"), "%-10s", None),
            "user": (_("USER"), "%-10s", "operation_username"),
            # omitting start state, end state, errors for now
            # as these don't nicely fit into columns
        }

        omit_headers = False
        long_format = False
        column_format = False
        display_limit = None    # Infinite
        time_vals = [] # list of timestamps for which we want history events
        columns = ["start", "operation", "client", "outcome"]

        # XXX history should be accessible through pkg.client.api
        if not os.path.exists(img.history.path):
                # Nothing to display.
                return EXIT_OK

        opts, pargs = getopt.getopt(args, "Hln:o:t:")
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
                elif opt == "-o":
                        column_format = True
                        columns = arg.split(",")

                        # 'command' and 'reason' are multi-field columns, we
                        # insist they be the last item in the -o output,
                        # otherwise scripts could be broken by different numbers
                        # of output fields
                        if "command" in columns and "reason" in columns:
                                # Translators: 'command' and 'reason' are
                                # keywords and should not be translated
                                logger.error(_("'command' and 'reason' columns "
                                    "cannot be used together."))
                                return EXIT_BADOPT

                        for col in ["command", "reason"]:
                                if col in columns and \
                                    columns.index(col) != len(columns) - 1:
                                        logger.error(
                                            _("The '%s' column must be the "
                                            "last item in the -o list") % col)
                                        return EXIT_BADOPT

                        for col in columns:
                                if col not in history_cols:
                                        logger.error(
                                            _("Unknown output column '%s'") %
                                            col)
                                        return EXIT_BADOPT
                        if not __unique_columns(columns):
                                return EXIT_BADOPT

                elif opt == "-t":
                        time_vals = arg.split(",")
                        # make entries a set to cope with multiple overlapping
                        # ranges or time values
                        entries = set()
                        for time_val in time_vals:
                                try:
                                        # used for the 'now' alias, we calculate
                                        # this once only
                                        utc_now = datetime.datetime.utcnow().strftime(
                                            "%Y%m%dT%H%M%SZ")
                                        files = __get_history_paths(time_val,
                                            img.history.path, utc_now)
                                        if files == EXIT_BADOPT:
                                                return EXIT_BADOPT
                                        entries.update(files)
                                except ValueError:
                                        logger.error(_("Invalid time format "
                                        "'%s'.  Please use "
                                        "%%Y-%%m-%%dT%%H:%%M:%%S or\n"
                                        "%%Y-%%m-%%dT%%H:%%M:%%S-%%Y-%%m-%%dT%%H:%%M:%%S"
                                        ) % time_val)
                                        return EXIT_BADOPT
                        entries = sorted(entries)

        if omit_headers and long_format:
                usage(_("-H and -l may not be combined"), cmd="history")

        if column_format and long_format:
                usage(_("-o and -l may not be combined"), cmd="history")

        if time_vals and display_limit:
                usage(_("-n and -t may not be combined"), cmd="history")

        history_fmt = None

        if not long_format:
                headers = []
                # build our format string
                for col in columns:
                        # no need for trailing space for our last column
                        if columns.index(col) == len(columns) - 1:
                                fmt = "%s"
                        else:
                                fmt = history_cols[col][1]
                        if history_fmt:
                                history_fmt = "%s%s" % (history_fmt, fmt)
                        else:
                                history_fmt = "%s" % fmt
                        headers.append(history_cols[col][0])
                if not omit_headers:
                        msg(history_fmt % tuple(headers))

        if display_limit:
                n = -display_limit
                entries = sorted(os.listdir(img.history.path))[n:]
        elif not time_vals:
                entries = sorted(os.listdir(img.history.path))

        uuid_be_dic = bootenv.BootEnv.get_uuid_be_dic()
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

                # populate a dictionary containing our output
                output = {}
                for col in history_cols:
                        if not history_cols[col][2]:
                                continue
                        output[col] = he.__getattribute__(history_cols[col][2])

                # format some of the History object attributes ourselves
                output["start"] = misc.timestamp_to_time(
                    he.operation_start_time)
                output["start"] = datetime.datetime.fromtimestamp(
                    output["start"]).isoformat()
                output["finish"] = misc.timestamp_to_time(
                    he.operation_end_time)
                output["finish"] = datetime.datetime.fromtimestamp(
                    output["finish"]).isoformat()

                dt_start = misc.timestamp_to_datetime(he.operation_start_time)
                dt_end = misc.timestamp_to_datetime(he.operation_end_time)
                if dt_start > dt_end:
                        error(_("History operation appeared to end before it "
                            "started.  Start time: %(start_time)s, "
                            "End time: %(end_time)s") %
                            (output["start"], output["finish"]), cmd="history")
                        return EXIT_OOPS

                output["time"] = dt_end - dt_start
                # This should never happen.  We can't use timedelta's str()
                # method, since it prints eg. "4 days, 3:12:54" breaking our
                # field separation, so we need to do this by hand.
                if output["time"].days > 0:
                        total_time = output["time"]
                        secs = total_time.seconds
                        add_hrs = total_time.days * 24
                        mins, secs = divmod(secs, 60)
                        hrs, mins = divmod(mins, 60)
                        output["time"] = "%s:%s:%s" % \
                            (add_hrs + hrs, mins, secs)

                output["be"] = he.operation_be
                be_uuid = he.operation_be_uuid
                output["command"] = " ".join(he.client_args)
                output["new_be"] = he.operation_new_be
                new_be_uuid = he.operation_new_be_uuid

                # lookup be and new_be names from the saved uuid, in case
                # the boot environment names have changed since we stored the
                # History object.  Where we weren't able to lookup the current
                # name, add a '*' to the entry, indicating the boot environment
                # is no longer present
                if be_uuid in uuid_be_dic:
                        output["be"] = uuid_be_dic[be_uuid]
                elif be_uuid:
                        output["be"] = "%s*" % output["be"]

                if new_be_uuid in uuid_be_dic:
                        output["new_be"] = uuid_be_dic[new_be_uuid]
                elif new_be_uuid:
                        output["new_be"] = "%s*" % output["new_be"]

                output["outcome"] = history.result_l10n[he.operation_result[0]]
                output["reason"] = history.result_l10n[he.operation_result[1]]
                output["snapshot"] = he.operation_snapshot

                # be, snapshot and new_be use values in parenthesis
                # since these cannot appear in valid BE or snapshot names
                if not output["be"]:
                        output["be"] = _("(Unknown)")

                if not output["be_uuid"]:
                        output["be_uuid"] = _("(Unknown)")

                if not output["snapshot"]:
                        output["snapshot"] = _("(None)")

                if not output["new_be"]:
                        output["new_be"] = _("(None)")

                if not output["new_be_uuid"]:
                        output["new_be_uuid"] = _("(None)")

                if long_format:
                        data = __get_long_history_data(he, output)
                        for field, value in data:
                                msg("%18s: %s" % (field, value))

                        # Separate log entries with a blank line.
                        msg("")
                else:
                        items = []
                        for col in columns:
                                items.append(output[col])
                        msg(history_fmt % tuple(items))
        return EXIT_OK

def __get_history_paths(time_val, history_path, utc_now):
        """Given a local timestamp, either as a discrete value, or a range of
        values, formatted as '<timestamp>-<timestamp>', and a path to find
        history xml files, return an array of paths that match that timestamp.
        utc_now is the current time expressed in UTC"""

        files = []
        if len(time_val) > 20 or time_val.startswith("now-"):
                if time_val.startswith("now-"):
                        start = utc_now
                        finish = __utc_format(time_val[4:], utc_now)
                else:
                        # our ranges are 19 chars of timestamp, a '-', and
                        # another timestamp
                        start = __utc_format(time_val[:19], utc_now)
                        finish = __utc_format(time_val[20:], utc_now)
                if start > finish:
                        logger.error(_("Start time must be older than finish "
                            "time: %s") % time_val)
                        return EXIT_BADOPT
                files = __get_history_range(history_path, start, finish)
        else:
                # there can be multiple event files per timestamp
                prefix = __utc_format(time_val, utc_now)
                files = glob.glob(os.path.join(history_path, "%s*" % prefix))
        if not files:
                logger.error(_("No history entries found for %s") % time_val)
                return EXIT_BADOPT
        return files

def __unique_columns(columns):
        """Return true if each entry in the provided list of columns only
        appears once."""

        seen_cols = set()
        dup_cols = set()
        for col in columns:
                if col in seen_cols:
                        dup_cols.add(col)
                seen_cols.add(col)
        for col in dup_cols:
                logger.error(_("Duplicate column specified: %s") % col)
        return not dup_cols

def __utc_format(time_str, utc_now):
        """ Given a local time value string, formatted with "%Y-%m-%dT%H:%M:%S,
        return a UTC representation of that value, formatted with
        %Y%m%dT%H%M%SZ.  This raises a ValueError if the time was incorrectly
        formatted.  If the time_str is "now", we return the value of utc_now"""

        if time_str == "now":
                return utc_now

        local_dt = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
        secs = time.mktime(local_dt.timetuple())
        utc_dt = datetime.datetime.utcfromtimestamp(secs)
        return utc_dt.strftime("%Y%m%dT%H%M%SZ")

def __get_history_range(path, start, finish):
        """Given an img.history.path and start and finish dates, formatted
        as UTC date strings as per __utc_format(), return a list of history
        file names that fall within that date range.  A range of two equal
        dates is equivalent of just retrieving history for that single
        date string."""

        entries = []
        all_entries = sorted(os.listdir(path))

        for entry in all_entries:
                # our timestamps are always 16 character datestamps
                basename = os.path.basename(entry)[:16]
                if basename >= start:
                        if basename > finish:
                                # we can stop looking now.
                                break
                        entries.append(entry)
        return entries

def __get_long_history_data(he, hist_info):
        """Return an array of tuples containing long_format history info"""
        data = []
        data.append((_("Operation"), hist_info["operation"]))

        data.append((_("Outcome"), hist_info["outcome"]))
        data.append((_("Reason"), hist_info["reason"]))
        data.append((_("Client"), hist_info["client"]))
        data.append((_("Version"), hist_info["client_ver"]))

        data.append((_("User"), "%s (%s)" % (hist_info["user"],
            hist_info["id"])))

        if hist_info["be"]:
                data.append((_("Boot Env."), hist_info["be"]))
        if hist_info["be_uuid"]:
                data.append((_("Boot Env. UUID"), hist_info["be_uuid"]))
        if hist_info["new_be"]:
                data.append((_("New Boot Env."), hist_info["new_be"]))
        if hist_info["new_be_uuid"]:
                data.append((_("New Boot Env. UUID"),
                    hist_info["new_be_uuid"]))
        if hist_info["snapshot"]:
                data.append((_("Snapshot"), hist_info["snapshot"]))

        data.append((_("Start Time"), hist_info["start"]))
        data.append((_("End Time"), hist_info["finish"]))
        data.append((_("Total Time"), hist_info["time"]))
        data.append((_("Command"), hist_info["command"]))

        state = he.operation_start_state
        if state:
                data.append((_("Start State"), "\n" + state))

        state = he.operation_end_state
        if state:
                data.append((_("End State"), "\n" + state))

        errors = "\n".join(he.operation_errors)
        if errors:
                data.append((_("Errors"), "\n" + errors))
        return data

def history_purge(api_inst, pargs):
        """Purge image history"""

        # history should be accessible through pkg.client.api
        be_name, be_uuid = bootenv.BootEnv.get_be_name(img.root)
        ret_code = img.history.purge(
            be_name=be_name, be_uuid=be_uuid)
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

def update_format(api_inst, pargs):
        """Update image to newest format."""

        try:
                res = api_inst.update_format()
        except api_errors.ApiException, e:
                error(str(e), cmd="update-format")
                return EXIT_OOPS

        if res:
                logger.info(_("Image format updated."))
                return EXIT_OK

        logger.info(_("Image format already current."))
        return EXIT_NOP

def print_version(pargs):
        if pargs:
                usage(_("version: command does not take operands ('%s')") %
                    " ".join(pargs), cmd="version")
        msg(pkg.VERSION)
        return EXIT_OK

# To allow exception handler access to the image.
img = None
orig_cwd = None

def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        global img
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
                    ["debug=", "help", "runid="])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        runid = os.getpid()
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
                                            "name=value, not %(arg)s") % {
                                            "opt":  opt, "arg": arg })
                        DebugValues.set_value(key, value)
                elif opt == "-R":
                        mydir = arg
                elif opt == "--runid":
                        runid = arg
                elif opt in ("--help", "-?"):
                        show_usage = True

        # placeholders in this lookup table for image-create, help and version
        # which don't have dedicated methods
        cmds = {
            "add-property-value"    : (property_add_value, None),
            "attach-linked"         : (attach_linked, opts_attach_linked, 2),
            "avoid"                 : (avoid, None),
            "audit-linked"          : (audit_linked, opts_audit_linked),
            "authority"             : (publisher_list, None),
            "change-facet"          : (change_facet, opts_install, -1),
            "change-variant"        : (change_variant, opts_install, -1),
            "contents"              : (list_contents, None),
            "detach-linked"         : (detach_linked, opts_detach_linked),
            "facet"                 : (facet_list, None),
            "fix"                   : (fix_image, None),
            "freeze"                : (freeze, None),
            "help"                  : (None, None),
            "history"               : (history_list, None),
            "image-create"          : (None, None),
            "info"                  : (info, None),
            "install"               : (install, opts_install, -1),
            "list"                  : (list_inventory, opts_list_inventory, -1),
            "list-linked"           : (list_linked, opts_list_linked),
            "mediator"              : (list_mediators, opts_list_mediator, -1),
            "property"              : (property_list, None),
            "property-linked"       : (list_property_linked,
                                          opts_list_property_linked, -1),
            "publisher"             : (publisher_list, None),
            "purge-history"         : (history_purge, None),
            "rebuild-index"         : (rebuild_index, None),
            "refresh"               : (publisher_refresh, None),
            "remove-property-value" : (property_remove_value, None),
            "revert"                : (revert, None),
            "search"                : (search, None),
            "set-authority"         : (publisher_set, None),
            "set-mediator"          : (set_mediator, opts_set_mediator, -1),
            "set-property"          : (property_set, None),
            "set-property-linked"   : (set_property_linked,
                                          opts_set_property_linked, -1),
            "set-publisher"         : (publisher_set, None),
            "sync-linked"           : (sync_linked, opts_sync_linked),
            "unavoid"               : (unavoid, None),
            "unfreeze"              : (unfreeze, None),
            "uninstall"             : (uninstall, opts_uninstall, -1),
            "unset-authority"       : (publisher_unset, None),
            "unset-property"        : (property_unset, None),
            "update-format"         : (update_format, None),
            "unset-mediator"        : (unset_mediator, opts_unset_mediator, -1),
            "unset-publisher"       : (publisher_unset, None),
            "update"                : (update, opts_update, -1),
            "update-format"         : (update_format, None),
            "variant"               : (variant_list, None),
            "verify"                : (verify_image, None),
            "version"               : (None, None),
        }

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                # 'image-update' is an alias for 'update' for compatibility.
                subcommand = subcommand.replace("image-update", "update")
                if subcommand == "help":
                        if pargs:
                                sub = pargs.pop(0)
                                if sub in cmds and \
                                    sub not in ["help", "-?", "--help"]:
                                        usage(retcode=0, full=False, cmd=sub)
                                elif sub not in ["help", "-?", "--help"]:
                                        usage(_("unknown subcommand '%s'") %
                                            sub, full=True)
                                else:
                                        usage(retcode=0, full=True)
                        else:
                                usage(retcode=0, full=True)

        # A gauntlet of tests to see if we need to print usage information
        if subcommand in cmds and show_usage:
                usage(retcode=0, cmd=subcommand, full=False)
        if subcommand and subcommand not in cmds:
                usage(_("unknown subcommand '%s'") % subcommand, full=True)
        if show_usage:
                usage(retcode=0, full=True)
        if not subcommand:
                usage(_("no subcommand specified"))
        if runid:
                try:
                        runid = int(runid)
                except:
                        usage(_("runid must be an integer"))

        for opt in ["--help", "-?"]:
                if opt in pargs:
                        usage(retcode=0, full=False, cmd=subcommand)

        # This call only affects sockets created by Python.  The transport
        # framework uses the defaults in global_settings, which may be
        # overridden in the environment.  The default socket module should
        # only be used in rare cases by ancillary code, making it safe to
        # code the value here, at least for now.
        socket.setdefaulttimeout(30) # in secs

        cmds_no_image = {
                "version"        : print_version,
                "image-create"   : image_create,
        }
        func = cmds_no_image.get(subcommand, None)
        if func:
                if "mydir" in locals():
                        usage(_("-R not allowed for %s subcommand") %
                              subcommand, cmd=subcommand)
                try:
                        ret = func(pargs)
                except getopt.GetoptError, e:
                        usage(_("illegal option -- %s") % e.opt, cmd=subcommand)
                return ret

        provided_image_dir = True
        pkg_image_used = False
        if "mydir" not in locals():
                mydir, provided_image_dir = api.get_default_image_root(
                    orig_cwd=orig_cwd)
                if os.environ.get("PKG_IMAGE"):
                        # It's assumed that this has been checked by the above
                        # function call and hasn't been removed from the
                        # environment.
                        pkg_image_used = True

        if not mydir:
                error(_("Could not find image.  Use the -R option or set "
                    "$PKG_IMAGE to the\nlocation of an image."))
                return EXIT_OOPS

        # Get ImageInterface and image object.
        api_inst = __api_alloc(mydir, provided_image_dir, pkg_image_used, False,
            runid=runid)
        if api_inst is None:
                return EXIT_OOPS
        img = api_inst.img

        # Find subcommand and execute operation.
        pargs_limit = 0
        func = cmds[subcommand][0]
        opts_cmd = cmds[subcommand][1]
        if len(cmds[subcommand]) > 2:
                pargs_limit = cmds[subcommand][2]
        try:
                if opts_cmd == None:
                        return func(api_inst, pargs)

                opts, pargs = misc.opts_parse(subcommand, api_inst, pargs,
                    opts_cmd, pargs_limit, usage)
                return func(op=subcommand, api_inst=api_inst,
                    pargs=pargs, **opts)

        except getopt.GetoptError, e:
                usage(_("illegal option -- %s") % e.opt, cmd=subcommand)

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
def handle_errors(func, non_wrap_print=True, *args, **kwargs):
        traceback_str = _("""\n
This is an internal error in pkg(5) version %(version)s.  Please let the
developers know about this problem by including the information above (and
this message) when filing a bug at:

%(bug_uri)s""") % { "version": pkg.VERSION, "bug_uri": misc.BUG_URI_CLI }

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
                        if img:
                                img.history.abort(RESULT_FAILED_OUTOFMEMORY)
                        error("\n" + misc.out_of_memory())
                        __ret = EXIT_OOPS
        except SystemExit, __e:
                if img:
                        img.history.abort(RESULT_FAILED_UNKNOWN)
                raise __e
        except (PipeError, KeyboardInterrupt):
                if img:
                        img.history.abort(RESULT_CANCELED)
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = EXIT_OOPS
        except api_errors.LinkedImageException, __e:
                error(_("Linked image exception(s):\n%s") %
                      str(__e))
                __ret = __e.lix_exitrv
        except api_errors.CertificateError, __e:
                if img:
                        img.history.abort(RESULT_FAILED_CONFIGURATION)
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.PublisherError, __e:
                if img:
                        img.history.abort(RESULT_FAILED_BAD_REQUEST)
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.ImageLockedError, __e:
                if img:
                        img.history.abort(RESULT_FAILED_LOCKED)
                error(__e)
                __ret = EXIT_LOCKED
        except api_errors.TransportError, __e:
                if img:
                        img.history.abort(RESULT_FAILED_TRANSPORT)
                logger.error(_("\nErrors were encountered while attempting "
                    "to retrieve package or file data for\nthe requested "
                    "operation."))
                logger.error(_("Details follow:\n\n%s") % __e)
                print_proxy_config()
                __ret = EXIT_OOPS
        except api_errors.InvalidCatalogFile, __e:
                if img:
                        img.history.abort(RESULT_FAILED_STORAGE)
                logger.error(_("""
An error was encountered while attempting to read image state information
to perform the requested operation.  Details follow:\n\n%s""") % __e)
                __ret = EXIT_OOPS
        except api_errors.InvalidDepotResponseException, __e:
                if img:
                        img.history.abort(RESULT_FAILED_TRANSPORT)
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
                if img:
                        img.history.clear()
                error(_("An error was encountered while attempting to load "
                    "history information\nabout past client operations."))
                error(__e)
                __ret = EXIT_OOPS
        except history.HistoryStoreException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if img:
                        img.history.clear()
                error(_("An error was encountered while attempting to store "
                    "information about the\ncurrent operation in client "
                    "history."))
                error(__e)
                __ret = EXIT_OOPS
        except history.HistoryPurgeException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if img:
                        img.history.clear()
                error(_("An error was encountered while attempting to purge "
                    "client history."))
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.VersionException, __e:
                if img:
                        img.history.abort(RESULT_FAILED_UNKNOWN)
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

                s += _("\n\nDespite the error while indexing, the operation "
                    "has completed successfuly.")
                error(s)
        except api_errors.ReadOnlyFileSystemException, __e:
                __ret = EXIT_OOPS
        except:
                if img:
                        img.history.abort(RESULT_FAILED_UNKNOWN)
                if non_wrap_print:
                        traceback.print_exc()
                        error(traceback_str)
                __ret = 99
        return __ret

if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale")

        # Make all warnings be errors.
        import warnings
        warnings.simplefilter('error')

        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
