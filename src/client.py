#!/usr/bin/python2.7
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
# Copyright (c) 2007, 2016, Oracle and/or its affiliates. All rights reserved.
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

from __future__ import print_function
try:
        import calendar
        import collections
        import datetime
        import errno
        import getopt
        import gettext
        import itertools
        import simplejson as json
        import locale
        import logging
        import os
        import re
        import six
        import socket
        import sys
        import tempfile
        import textwrap
        import time
        import traceback

        import pkg
        import pkg.actions as actions
        import pkg.client.api as api
        import pkg.client.api_errors as api_errors
        import pkg.client.bootenv as bootenv
        import pkg.client.client_api as client_api
        import pkg.client.progress as progress
        import pkg.client.linkedimage as li
        import pkg.client.publisher as publisher
        import pkg.client.options as options
        import pkg.fmri as fmri
        import pkg.misc as misc
        import pkg.pipeutils as pipeutils
        import pkg.portable as portable
        import pkg.version as version

        if sys.version_info[:2] >= (3, 4):
                from importlib import reload
        else:
                from imp import reload
        from pkg.client import global_settings
        from pkg.client.api import (IMG_TYPE_ENTIRE, IMG_TYPE_PARTIAL,
            IMG_TYPE_USER, RESULT_CANCELED, RESULT_FAILED_BAD_REQUEST,
            RESULT_FAILED_CONFIGURATION, RESULT_FAILED_CONSTRAINED,
            RESULT_FAILED_LOCKED, RESULT_FAILED_STORAGE, RESULT_NOTHING_TO_DO,
            RESULT_SUCCEEDED, RESULT_FAILED_TRANSPORT, RESULT_FAILED_UNKNOWN,
            RESULT_FAILED_OUTOFMEMORY)
        from pkg.client.debugvalues import DebugValues
        from pkg.client.pkgdefs import *
        from pkg.misc import EmptyI, msg, emsg, PipeError
except KeyboardInterrupt:
        import sys
        sys.exit(1)

CLIENT_API_VERSION = 83
PKG_CLIENT_NAME = "pkg"

JUST_UNKNOWN = 0
JUST_LEFT = -1
JUST_RIGHT = 1

SYSREPO_HIDDEN_URI = "<system-repository>"

logger = global_settings.logger
pkg_timer = pkg.misc.Timer("pkg client")

valid_special_attrs = ["action.hash", "action.key", "action.name", "action.raw"]

valid_special_prefixes = ["action."]

default_attrs = {}
for atype, aclass in six.iteritems(actions.types):
        default_attrs[atype] = [aclass.key_attr]
        if atype == "depend":
                default_attrs[atype].insert(0, "type")
        if atype == "set":
                default_attrs[atype].append("value")

_api_inst = None

def format_update_error(e):
        # This message is displayed to the user whenever an
        # ImageFormatUpdateNeeded exception is encountered.
        logger.error("\n")
        logger.error(str(e))
        logger.error(_("To continue, execute 'pkg update-format' as a "
            "privileged user and then try again.  Please note that updating "
            "the format of the image will render it unusable with older "
            "versions of the pkg(7) system."))

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if not isinstance(text, six.string_types):
                # Assume it's an object that can be stringified.
                text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        if cmd:
                text_nows = "{0}: {1}".format(cmd, text_nows)
                pkg_cmd = "pkg "
        else:
                pkg_cmd = "pkg: "

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        logger.error(ws + pkg_cmd + text_nows)

def usage(usage_error=None, cmd=None, retcode=EXIT_BADOPT, full=False,
    verbose=False, unknown_cmd=None):
        """Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        if usage_error:
                error(usage_error, cmd=cmd)

        basic_usage = {}
        adv_usage = {}
        priv_usage = {}

        basic_cmds = ["refresh", "install", "uninstall", "update", "list",
            "version"]

        basic_usage["install"] = _(
            "[-nvq] [-C n] [-g path_or_uri ...] [--accept]\n"
            "            [--licenses] [--no-be-activate] [--no-index] [--no-refresh]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [-r [-z image_name ... | -Z image_name ...]]\n"
            "            [--sync-actuators | --sync-actuators-timeout timeout]\n"
            "            [--reject pkg_fmri_pattern ... ] pkg_fmri_pattern ...")
        basic_usage["uninstall"] = _(
            "[-nvq] [-C n] [--ignore-missing] [--no-be-activate] [--no-index]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [-r [-z image_name ... | -Z image_name ...]]\n"
            "            [--sync-actuators | --sync-actuators-timeout timeout]\n"
            "            pkg_fmri_pattern ...")
        basic_usage["update"] = _(
            "[-fnvq] [-C n] [-g path_or_uri ...] [--accept] [--ignore-missing]\n"
            "            [--licenses] [--no-be-activate] [--no-index] [--no-refresh]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [-r [-z image_name ... | -Z image_name ...]]\n"
            "            [--sync-actuators | --sync-actuators-timeout timeout]\n"
            "            [--reject pkg_fmri_pattern ...] [pkg_fmri_pattern ...]")
        basic_usage["list"] = _(
            "[-Hafnqsuv] [-g path_or_uri ...] [--no-refresh]\n"
            "            [pkg_fmri_pattern ...]")
        basic_usage["refresh"] = _("[-q] [--full] [publisher ...]")
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
            "exact-install",
            "",
            "dehydrate",
            "rehydrate"
        ]

        adv_usage["info"] = \
            _("[-lqr] [-g path_or_uri ...] [--license] [pkg_fmri_pattern ...]")
        adv_usage["contents"] = _(
            "[-Hmr] [-a attribute=pattern ...] [-g path_or_uri ...]\n"
            "            [-o attribute ...] [-s sort_key] [-t action_type ...]\n"
            "            [pkg_fmri_pattern ...]")
        adv_usage["search"] = _(
            "[-HIaflpr] [-o attribute ...] [-s repo_uri] query")

        adv_usage["verify"] = _("[-Hqv] [--parsable version] [--unpackaged]\n"
            "            [--unpackaged-only] [pkg_fmri_pattern ...]")
        adv_usage["fix"] = _(
            "[-Hnvq] [--no-be-activate]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [--accept] [--licenses] [--parsable version] [--unpackaged]\n"
            "            [pkg_fmri_pattern ...]")
        adv_usage["revert"] = _(
            "[-nv] [--no-be-activate]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            (--tagged tag-name ... | path-to-file ...)")

        adv_usage["image-create"] = _(
            "[-FPUfz] [--force] [--full|--partial|--user] [--zone]\n"
            "            [-k ssl_key] [-c ssl_cert] [--no-refresh]\n"
            "            [--variant <variant_spec>=<instance> ...]\n"
            "            [-g uri|--origin=uri ...] [-m uri|--mirror=uri ...]\n"
            "            [--facet <facet_spec>=(True|False) ...]\n"
            "            [(-p|--publisher) [<name>=]<repo_uri>] dir")
        adv_usage["change-variant"] = _(
            "[-nvq] [-C n] [-g path_or_uri ...] [--accept]\n"
            "            [--licenses] [--no-be-activate] [--no-index] [--no-refresh]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [-r [-z image_name ... | -Z image_name ...]]\n"
            "            [--sync-actuators | --sync-actuators-timeout timeout]\n"
            "            [--reject pkg_fmri_pattern ... ]\n"
            "            <variant_spec>=<instance> ...")

        adv_usage["change-facet"] = _(
            "[-nvq] [-C n] [-g path_or_uri ...] [--accept]\n"
            "            [--licenses] [--no-be-activate] [--no-index] [--no-refresh]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [-r [-z image_name ... | -Z image_name ...]]\n"
            "            [--sync-actuators | --sync-actuators-timeout timeout]\n"
            "            [--reject pkg_fmri_pattern ... ]\n"
            "            <facet_spec>=[True|False|None] ...")

        adv_usage["mediator"] = _("[-aH] [-F format] [<mediator> ...]")
        adv_usage["set-mediator"] = _(
            "[-nv] [-I <implementation>]\n"
            "            [-V <version>] [--no-be-activate]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            <mediator> ...")
        adv_usage["unset-mediator"] = _("[-nvIV] [--no-be-activate]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            <mediator> ...")

        adv_usage["variant"] = _("[-Haiv] [-F format] [<variant_pattern> ...]")
        adv_usage["facet"] = ("[-Haim] [-F format] [<facet_pattern> ...]")
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
            "            [--proxy proxy to use]\n"
            "            [publisher]")

        adv_usage["unset-publisher"] = _("publisher ...")
        adv_usage["publisher"] = _("[-HPn] [-F format] [publisher ...]")
        adv_usage["history"] = _("[-HNl] [-t [time|time-time],...] [-n number] [-o column,...]")
        adv_usage["purge-history"] = ""
        adv_usage["rebuild-index"] = ""
        adv_usage["update-format"] = ""
        adv_usage["exact-install"] = _("[-nvq] [-C n] [-g path_or_uri ...] [--accept]\n"
            "            [--licenses] [--no-be-activate] [--no-index] [--no-refresh]\n"
            "            [--no-backup-be | --require-backup-be] [--backup-be-name name]\n"
            "            [--deny-new-be | --require-new-be] [--be-name name]\n"
            "            [--reject pkg_fmri_pattern ... ] pkg_fmri_pattern ...")
        adv_usage["dehydrate"] = _("[-nvq] [-p publisher ...]")
        adv_usage["rehydrate"] = _("[-nvq] [-p publisher ...]")

        priv_usage["remote"] = _(
            "--ctlfd=file_descriptor --progfd=file_descriptor")
        priv_usage["list-linked"] = _("-H")
        priv_usage["attach-linked"] = _(
            "[-fnvq] [-C n] [--accept] [--licenses] [--no-index]\n"
            "            [--no-refresh] [--no-pkg-updates] [--linked-md-only]\n"
            "            [--allow-relink]\n"
            "            [--prop-linked <propname>=<propvalue> ...]\n"
            "            (-c|-p) <li-name> <dir>")
        priv_usage["detach-linked"] = _(
            "[-fnvq] [-a|-l <li-name>] [--no-pkg-updates] [--linked-md-only]")
        priv_usage["property-linked"] = _("[-H] [-l <li-name>] [propname ...]")
        priv_usage["audit-linked"] = _(
            "[-H] [-a|-l <li-name>] [--no-parent-sync]")
        priv_usage["pubcheck-linked"] = ""
        priv_usage["sync-linked"] = _(
            "[-nvq] [-C n] [--accept] [--licenses] [--no-index]\n"
            "            [--no-refresh] [--no-parent-sync] [--no-pkg-updates]\n"
            "            [--linked-md-only] [-a|-l <name>]")
        priv_usage["set-property-linked"] = _(
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
                                            "Unable to find usage str for "
                                            "{0}".format(cmd))
                                use_txt = cmd_dic[cmd]
                                if use_txt is not "":
                                        logger.error(
                                            "        pkg {cmd} "
                                            "{use_txt}".format(**locals()))
                                else:
                                        logger.error("        pkg "
                                            "{0}".format(cmd))
        if not full and cmd:
                if cmd not in priv_usage:
                        logger.error(_("Usage:"))
                else:
                        logger.error(_("Private subcommand usage, options "
                            "subject to change at any time:"))
                combined = {}
                combined.update(basic_usage)
                combined.update(adv_usage)
                combined.update(priv_usage)
                print_cmds([cmd], combined)
                sys.exit(retcode)

        elif not full:
                # The full list of subcommands isn't desired.
                known_words = ["help"]
                known_words.extend(basic_cmds)
                known_words.extend(w for w in advanced_cmds if w)
                candidates = misc.suggest_known_words(unknown_cmd, known_words)
                if candidates:
                        # Suggest correct subcommands if we can.
                        words = ", ". join(candidates)
                        logger.error(_("Did you mean:\n    {0}\n").format(words))
                logger.error(_("For a full list of subcommands, run: pkg help"))
                sys.exit(retcode)

        if verbose:
                # Display a verbose usage message of subcommands.
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
        --no-network-cache
        --help or -?

Environment:
        PKG_IMAGE"""))
        else:
                # Display the full list of subcommands.
                logger.error(_("""\
Usage:    pkg [options] command [cmd_options] [operands]"""))
                logger.error(_("The following commands are supported:"))
                logger.error(_("""
Package Information  : list           search         info      contents
Package Transitions  : update         install        uninstall
                       history        exact-install
Package Maintenance  : verify         fix            revert
Publishers           : publisher      set-publisher  unset-publisher
Package Configuration: mediator       set-mediator   unset-mediator
                       facet          change-facet
                       variant        change-variant
Image Constraints    : avoid          unavoid        freeze    unfreeze
Image Configuration  : refresh        rebuild-index  purge-history
                       property       set-property   add-property-value
                       unset-property remove-property-value
Miscellaneous        : image-create   dehydrate      rehydrate
For more info, run: pkg help <command>"""))
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
                        errors.append("Illegal FMRI '{0}': {1}".format(pat,
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
    list_upgradable, omit_headers, origins, quiet, refresh_catalogs, summary,
    verbose):
        """List packages."""

        if verbose:
                fmt_str = "{0:76} {1}"
        elif summary:
                fmt_str = "{0:55} {1}"
        else:
                fmt_str = "{0:49} {1:26} {2}"

        state_map = [
            [("installed", "i")],
            [("frozen", "f")],
            [
                ("obsolete", "o"),
                ("renamed", "r")
            ],
        ]

        ppub = api_inst.get_highest_ranked_publisher()
        if ppub:
                ppub = ppub.prefix

        # getting json output.
        out_json = client_api._list_inventory(op, api_inst, pargs,
            li_parent_sync, list_all, list_installed_newest, list_newest,
            list_upgradable, origins, quiet, refresh_catalogs)

        errors = None
        if "errors" in out_json:
                errors = out_json["errors"]
                errors = _generate_error_messages(out_json["status"], errors,
                    selected_type=["catalog_refresh", "catalog_refresh_failed"])

        if "data" in out_json:
                data = out_json["data"]
                for entry in data:
                        if quiet:
                                continue

                        if not omit_headers:
                                if verbose:
                                        msg(fmt_str.format(
                                            "FMRI", "IFO"))
                                elif summary:
                                        msg(fmt_str.format(
                                            "NAME (PUBLISHER)",
                                            "SUMMARY"))
                                else:
                                        msg(fmt_str.format(
                                            "NAME (PUBLISHER)",
                                            "VERSION", "IFO"))
                                omit_headers = True

                        status = ""
                        for sentry in state_map:
                                for s, v in sentry:
                                        if s in entry["states"]:
                                                st = v
                                                break
                                        else:
                                                st = "-"
                                status += st

                        pub, stem, ver = entry["pub"], entry["pkg"], \
                            entry["version"]
                        if pub == ppub:
                                spub = ""
                        else:
                                spub = " (" + pub + ")"

                        # Display full FMRI (without build version) for
                        # verbose case.
                        # Use class method instead of creating an object for
                        # performance reasons.
                        if verbose:
                                (release, build_release, branch, ts), \
                                    short_ver = version.Version.split(ver)
                                pfmri = "pkg://{0}/{1}@{2}:{3}".format(
                                    pub, stem, short_ver, ts)
                                msg(fmt_str.format(pfmri, status))
                                continue

                        # Display short FMRI + summary.
                        summ = entry["summary"]
                        pf = stem + spub
                        if summary:
                                if summ is None:
                                        summ = ""
                                msg(fmt_str.format(pf, summ))
                                continue

                        # Default case; display short FMRI and version info.
                        sver = version.Version.split(ver)[-1]
                        msg(fmt_str.format(pf, sver, status))
        # Print errors left.
        if errors:
                _generate_error_messages(out_json["status"], errors)

        return out_json["status"]

def get_tracker():
        if global_settings.client_output_parsable_version is not None:
                progresstracker = progress.NullProgressTracker()
        elif global_settings.client_output_quiet:
                progresstracker = progress.QuietProgressTracker()
        elif global_settings.client_output_progfd:
                # This logic handles linked images: for linked children
                # we elide the progress output.
                output_file = os.fdopen(global_settings.client_output_progfd,
                    "w")
                child_tracker = progress.LinkedChildProgressTracker(
                    output_file=output_file)
                dot_tracker = progress.DotProgressTracker(
                    output_file=output_file)
                progresstracker = progress.MultiProgressTracker(
                    [child_tracker, dot_tracker])
        else:
                try:
                        progresstracker = progress.FancyUNIXProgressTracker()
                except progress.ProgressTrackerException:
                        progresstracker = progress.CommandLineProgressTracker()

        return progresstracker

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

def __display_plan(api_inst, verbose, noexecute, op=None):
        """Helper function to display plan to the desired degree.
        Verbose can either be a numerical value, or a list of
        items to display"""

        if isinstance(verbose, int):
                disp = ["basic"]

                if verbose == 0 and noexecute:
                        disp.append("release-notes")
                if verbose > 0:
                        disp.extend(["fmris", "mediators", "services",
                                     "variants/facets", "boot-archive",
                                     "release-notes", "editable", "actuators"])
                if verbose > 1:
                        disp.append("actions")
                if verbose > 2:
                        disp.append("solver-errors")
        else:
                disp = verbose

        if DebugValues["plan"] and "solver-errors" not in disp:
                disp.append("solver-errors")

        plan = api_inst.describe()

        if plan.must_display_notes():
                disp.append("release-notes")

        if api_inst.is_liveroot and not api_inst.is_active_liveroot_be:
                # Warn the user since this isn't likely what they wanted.
                if plan.new_be:
                        logger.warning(_("""\
WARNING: The boot environment being modified is not the active one.  Changes
made in the active BE will not be reflected on the next boot.
"""))
                else:
                        logger.warning(_("""\
WARNING: The boot environment being modified is not the active one.  Changes
made will not be reflected on the next boot.
"""))

        a, r, i, c = [], [], [], []
        for src, dest in plan.get_changes():
                if dest is None:
                        r.append((src, dest))
                elif src is None:
                        i.append((src, dest))
                elif src != dest:
                        c.append((src, dest))
                else:
                        # Changing or repairing package content (e.g. fix,
                        # change-facet, etc.)
                        a.append((dest, dest))

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
                                status.append((s1, s2.format(v)))

                cond_show(_("Packages to remove:"), "{0:d}", len(r))
                cond_show(_("Packages to install:"), "{0:d}", len(i))
                cond_show(_("Packages to update:"), "{0:d}", len(c))
                if varcets or mediators:
                        cond_show(_("Packages to change:"), "{0:d}", len(a))
                else:
                        cond_show(_("Packages to fix:"), "{0:d}", len(a))
                cond_show(_("Mediators to change:"), "{0:d}", len(mediators))
                cond_show(_("Variants/Facets to change:"), "{0:d}",
                    len(varcets))
                if not plan.new_be:
                        cond_show(_("Services to change:"), "{0:d}",
                            len(plan.services))

                if verbose:
                        # Only show space information in verbose mode.
                        abytes = plan.bytes_added
                        if abytes:
                                status.append((_("Estimated space available:"),
                                    misc.bytes_to_str(plan.bytes_avail)))
                                status.append((
                                    _("Estimated space to be consumed:"),
                                    misc.bytes_to_str(plan.bytes_added)))

                # only display BE information if we're operating on the
                # liveroot environment (since otherwise we'll never be
                # manipulating BEs).
                if api_inst.is_liveroot:
                        status.append((_("Create boot environment:"),
                            bool_str(plan.new_be)))

                        if plan.new_be and (verbose or not plan.activate_be):
                                # Only show activation status if verbose or
                                # if new BE will not be activated.
                                status.append((_("Activate boot environment:"),
                                    bool_str(plan.activate_be)))

                        status.append((_("Create backup boot environment:"),
                            bool_str(plan.backup_be)))

        if "boot-archive" in disp:
                status.append((_("Rebuild boot archive:"),
                    bool_str(plan.update_boot_archive)))

        # Right-justify all status strings based on length of longest string.
        if status:
                rjust_status = max(len(s[0]) for s in status)
                rjust_value = max(len(s[1]) for s in status)
                for s in status:
                        logger.info("{0} {1}".format(s[0].rjust(rjust_status),
                            s[1].rjust(rjust_value)))

        need_blank = True
        if "mediators" in disp and mediators:
                if need_blank:
                        logger.info("")

                logger.info(_("Changed mediators:"))
                for x in mediators:
                        logger.info("  {0}".format(x))
                # output has trailing blank
                need_blank = False

        if "variants/facets" in disp and varcets:
                if need_blank:
                        logger.info("")
                need_blank = True

                logger.info(_("Changed variants/facets:"))
                for x in varcets:
                        logger.info("  {0}".format(x))

        if "solver-errors" in disp:
                first = True
                for l in plan.get_solver_errors():
                        if first:
                                if need_blank:
                                        logger.info("")
                                need_blank = True
                                logger.info(_("Solver dependency errors:"))
                                first = False
                        logger.info(l)

        if "fmris" in disp:
                changed = collections.defaultdict(list)
                for src, dest in itertools.chain(r, i, c, a):
                        if src and dest:
                                if src.publisher != dest.publisher:
                                        pparent = "{0} -> {1}".format(
                                            src.publisher, dest.publisher)
                                else:
                                        pparent = dest.publisher
                                pname = dest.pkg_stem

                                # Only display timestamp if version is same and
                                # timestamp is not between the two fmris.
                                sver = src.fmri.version
                                dver = dest.fmri.version
                                ssver = sver.get_short_version()
                                dsver = dver.get_short_version()
                                include_ts = (ssver == dsver and
                                    sver.timestr != dver.timestr)
                                if include_ts:
                                        pver = sver.get_version(
                                            include_build=False)
                                else:
                                        pver = ssver

                                if src != dest:
                                        if include_ts:
                                                pver += " -> {0}".format(
                                                    dver.get_version(
                                                        include_build=False))
                                        else:
                                                pver += " -> {0}".format(dsver)

                        elif dest:
                                pparent = dest.publisher
                                pname = dest.pkg_stem
                                pver = "None -> {0}".format(
                                    dest.fmri.version.get_short_version())
                        else:
                                pparent = src.publisher
                                pname = src.pkg_stem
                                pver = "{0} -> None".format(
                                    src.fmri.version.get_short_version())

                        changed[pparent].append((pname, pver))

                if changed:
                        if need_blank:
                                logger.info("")
                        need_blank = True

                        logger.info(_("Changed packages:"))
                        last_parent = None
                        for pparent, pname, pver in (
                            (pparent, pname, pver)
                            for pparent in sorted(changed)
                            for pname, pver in changed[pparent]
                        ):
                                if pparent != last_parent:
                                        logger.info(pparent)

                                logger.info("  {0}".format(pname))
                                logger.info("    {0}".format(pver))
                                last_parent = pparent

                if "actuators" in disp:
                        # print pkg which have been altered due to pkg actuators
                        # e.g:
                        #
                        # Package-triggered Operations:
                        # TriggerPackage
                        #     update
                        #         PackageA
                        #         PackageB
                        #     uninstall
                        #         PackageC

                        first = True
                        for trigger_pkg, act_dict in plan.gen_pkg_actuators():
                                if first:
                                        first = False
                                        if need_blank:
                                                logger.info("")
                                        need_blank = True
                                        logger.info(
                                            _("Package-triggered Operations:"))
                                logger.info(trigger_pkg)
                                for exec_op in sorted(act_dict):
                                        logger.info("    {0}".format(exec_op))
                                        for pkg in sorted(act_dict[exec_op]):
                                                logger.info(
                                                    "        {0}".format(pkg))

        if "services" in disp and not plan.new_be:
                last_action = None
                for action, smf_fmri in plan.services:
                        if last_action is None:
                                if need_blank:
                                        logger.info("")
                                need_blank = True
                                logger.info(_("Services:"))
                        if action != last_action:
                                logger.info("  {0}:".format(action))
                        logger.info("    {0}".format(smf_fmri))
                        last_action = action

        # Displaying editable file list is redundant for pkg fix.
        if "editable" in disp and op != PKG_OP_FIX:
                moved, removed, installed, updated = plan.get_editable_changes()

                cfg_change_fmt = "    {0}"
                cfg_changes = []
                first = True

                def add_cfg_changes(changes, chg_hdr, chg_fmt=cfg_change_fmt):
                        first = True
                        for chg in changes:
                                if first:
                                        cfg_changes.append("  {0}".format(
                                            chg_hdr))
                                        first = False
                                cfg_changes.append(chg_fmt.format(*chg))

                add_cfg_changes((entry for entry in moved),
                    _("Move:"), chg_fmt="    {0} -> {1}")

                add_cfg_changes(((src,) for (src, dest) in removed),
                    _("Remove:"))

                add_cfg_changes(((dest,) for (src, dest) in installed),
                    _("Install:"))

                add_cfg_changes(((dest,) for (src, dest) in updated),
                    _("Update:"))

                if cfg_changes:
                        if need_blank:
                                logger.info("")
                        need_blank = True
                        logger.info(_("Editable files to change:"))
                        for l in cfg_changes:
                                logger.info(l)

        if "actions" in disp:
                if need_blank:
                        logger.info("")
                need_blank = True

                logger.info(_("Actions:"))
                for a in plan.get_actions():
                        logger.info("  {0}".format(a))


        if plan.has_release_notes():
                if need_blank:
                        logger.info("")
                need_blank = True

                if "release-notes" in disp:
                        logger.info(_("Release Notes:"))
                        for a in plan.get_release_notes():
                                logger.info("  %s", a)
                else:
                        if not plan.new_be and api_inst.is_liveroot and not DebugValues["GenerateNotesFile"]:
                                logger.info(_("Release notes can be viewed with 'pkg history -n 1 -N'"))
                        else:
                                tmp_path = __write_tmp_release_notes(plan)
                                if tmp_path:
                                        logger.info(_("Release notes can be found in {0} before "
                                            "rebooting.").format(tmp_path))
                                logger.info(_("After rebooting, use 'pkg history -n 1 -N' to view release notes."))

def __write_tmp_release_notes(plan):
        """try to write release notes out to a file in /tmp and return the name"""
        if plan.has_release_notes:
                try:
                        fd, path = tempfile.mkstemp(suffix=".txt", prefix="release-notes")
                        # make file world readable
                        os.chmod(path, 0o644)
                        tmpfile = os.fdopen(fd, "w+")
                        for a in plan.get_release_notes():
                                a = misc.force_str(a)
                                print(a, file=tmpfile)
                        tmpfile.close()
                        return path
                except Exception:
                        pass

def __display_parsable_plan(api_inst, parsable_version, child_images=None):
        """Display the parsable version of the plan."""

        assert parsable_version == 0, "parsable_version was {0!r}".format(
            parsable_version)
        plan = api_inst.describe()
        # Set the default values.
        added_fmris = []
        removed_fmris = []
        changed_fmris = []
        affected_fmris = []
        backup_be_created = False
        new_be_created = False
        backup_be_name = None
        be_name = None
        boot_archive_rebuilt = False
        be_activated = True
        space_available = None
        space_required = None
        facets_changed = []
        variants_changed = []
        services_affected = []
        mediators_changed = []
        editables_changed = []
        pkg_actuators = {}
        item_messages = {}
        licenses = []
        if child_images is None:
                child_images = []
        release_notes = []

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
                variants_changed, facets_changed = plan.varcets
                backup_be_created = plan.backup_be
                new_be_created = plan.new_be
                backup_be_name = plan.backup_be_name
                be_name = plan.be_name
                boot_archive_rebuilt = plan.update_boot_archive
                be_activated = plan.activate_be
                space_available = plan.bytes_avail
                space_required = plan.bytes_added
                services_affected = plan.services
                mediators_changed = plan.mediators
                pkg_actuators = [(p, a) for (p, a) in plan.gen_pkg_actuators()]

                emoved, eremoved, einstalled, eupdated = \
                    plan.get_editable_changes()

                # Lists of lists are used here to ensure a consistent ordering
                # and because tuples will be convereted to lists anyway; a
                # dictionary would be more logical for the top level entries,
                # but would make testing more difficult and this is a small,
                # known set anyway.
                emoved = [[e for e in entry] for entry in emoved]
                eremoved = [src for (src, dest) in eremoved]
                einstalled = [dest for (src, dest) in einstalled]
                eupdated = [dest for (src, dest) in eupdated]
                if emoved:
                        editables_changed.append(["moved", emoved])
                if eremoved:
                        editables_changed.append(["removed", eremoved])
                if einstalled:
                        editables_changed.append(["installed", einstalled])
                if eupdated:
                        editables_changed.append(["updated", eupdated])

                for n in plan.get_release_notes():
                        release_notes.append(n)

                for dfmri, src_li, dest_li, acc, disp in \
                    plan.get_licenses():
                        src_tup = ()
                        if src_li:
                                li_txt = misc.decode(src_li.get_text())
                                src_tup = (str(src_li.fmri), src_li.license,
                                    li_txt, src_li.must_accept,
                                    src_li.must_display)
                        dest_tup = ()
                        if dest_li:
                                li_txt = misc.decode(dest_li.get_text())
                                dest_tup = (str(dest_li.fmri),
                                    dest_li.license, li_txt,
                                    dest_li.must_accept, dest_li.must_display)
                        licenses.append(
                            (str(dfmri), src_tup, dest_tup))
                        api_inst.set_plan_license_status(dfmri, dest_li.license,
                            displayed=True)
                item_messages = plan.get_parsable_item_messages()

        ret = {
            "activate-be": be_activated,
            "add-packages": sorted(added_fmris),
            "affect-packages": sorted(affected_fmris),
            "affect-services": sorted(services_affected),
            "backup-be-name": backup_be_name,
            "be-name": be_name,
            "boot-archive-rebuild": boot_archive_rebuilt,
            "change-facets": sorted(facets_changed),
            "change-editables": editables_changed,
            "change-mediators": sorted(mediators_changed),
            "change-packages": sorted(changed_fmris),
            "change-variants": sorted(variants_changed),
            "child-images": child_images,
            "create-backup-be": backup_be_created,
            "create-new-be": new_be_created,
            "image-name": None,
            "item-messages": item_messages,
            "licenses": sorted(licenses, key=lambda x: (x[0], x[1], x[2])),
            "release-notes": release_notes,
            "remove-packages": sorted(removed_fmris),
            "space-available": space_available,
            "space-required": space_required,
            "version": parsable_version,
        }

        if pkg_actuators:
                ret["package-actuators"] = pkg_actuators

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
                        logger.info(_("Package: {0}").format(pfmri.get_fmri(
                            include_build=False)))
                        logger.info(_("License: {0}\n").format(lic))
                        logger.info(dest.get_text())
                        logger.info("\n")

                # Mark license as having been displayed.
                api_inst.set_plan_license_status(pfmri, lic, displayed=True)

def display_plan(api_inst, child_image_plans, noexecute, omit_headers, op,
    parsable_version, quiet, quiet_plan, show_licenses, stage, verbose):
        """Display plan function."""

        plan = api_inst.describe()
        if not plan:
                return

        if stage not in [API_STAGE_DEFAULT, API_STAGE_PLAN] and not quiet_plan:
                # we should have displayed licenses earlier so mark all
                # licenses as having been displayed.
                display_plan_licenses(api_inst, show_req=False)
                return

        if not quiet and parsable_version is None and \
            api_inst.planned_nothingtodo(li_ignore_all=True) and not quiet_plan:
                # nothing todo
                if op == PKG_OP_UPDATE:
                        s = _("No updates available for this image.")
                else:
                        s = _("No updates necessary for this image.")
                if api_inst.ischild():
                        s += " ({0})".format(api_inst.get_linked_name())
                msg(s)

                if op != PKG_OP_FIX or not verbose:
                        # Even nothingtodo, but need to continue to display INFO
                        # message if verbose is True.
                        return

        if parsable_version is None and not quiet_plan:
                display_plan_licenses(api_inst, show_all=show_licenses)

        if not quiet and not quiet_plan:
                __display_plan(api_inst, verbose, noexecute, op=op)

        if parsable_version is not None:
                __display_parsable_plan(api_inst, parsable_version,
                    child_image_plans)
        elif not quiet:
                if not quiet_plan:
                        # Ensure a blank line is inserted before the message
                        # output.
                        msg()

                last_item_id = None
                for item_id, msg_time, msg_type, msg_text in \
                    plan.gen_item_messages(ordered=True):
                        ntd = api_inst.planned_nothingtodo(li_ignore_all=True)
                        if last_item_id is None or last_item_id != item_id:
                                last_item_id = item_id
                                if op == PKG_OP_FIX and not noexecute and \
                                    msg_type == MSG_ERROR:
                                        if ntd:
                                                msg(_("Could not repair: {0:50}"
                                                    ).format(item_id))
                                        else:
                                                msg(_("Repairing: {0:50}"
                                                    ).format(item_id))

                        if op == PKG_OP_FIX:
                                if not verbose and msg_type == MSG_INFO:
                                        # If verbose is False, don't display
                                        # any INFO messages.
                                        continue

                                if not omit_headers:
                                        omit_headers = True
                                        msg(_("{pkg_name:70} {result:>7}").format(
                                            pkg_name=_("PACKAGE"),
                                            result=_("STATUS")))

                        msg(msg_text)

def __print_verify_result(op, api_inst, plan, noexecute, omit_headers,
    verbose, print_packaged=True):
        did_print_something = False
        if print_packaged:
                last_item_id = None
                ntd = api_inst.planned_nothingtodo(li_ignore_all=True)
                for item_id, parent_id, msg_time, msg_level, msg_type, \
                    msg_text in plan.gen_item_messages(ordered=True):
                        if msg_type == MSG_UNPACKAGED:
                                continue
                        if parent_id is None and last_item_id != item_id:
                                if op == PKG_OP_FIX and not noexecute and \
                                    msg_level == MSG_ERROR:
                                        if ntd:
                                                msg(_("Could not repair: {0:50}"
                                                    ).format(item_id))
                                        else:
                                                msg(_("Repairing: {0:50}"
                                                    ).format(item_id))

                        if op in [PKG_OP_FIX, PKG_OP_VERIFY]:
                                if not verbose and msg_level == MSG_INFO:
                                        # If verbose is False, don't display
                                        # any INFO messages.
                                        continue

                                if not omit_headers:
                                        omit_headers = True
                                        msg(_("{pkg_name:70} {result:>7}"
                                            ).format(pkg_name=_("PACKAGE"),
                                            result=_("STATUS")))

                        # Top level message.
                        if not parent_id:
                                msg(msg_text)
                        elif item_id == "overlay_errors":
                                msg(_("\t{0}").format(msg_text))
                        elif last_item_id != item_id:
                                # A new action id; we need to print it out and
                                # then group its subsequent messages.
                                msg(_("\t{0}\n\t\t{1}").format(item_id,
                                    msg_text))
                        else:
                                msg(_("\t\t{0}").format(msg_text))
                        last_item_id = item_id
                        did_print_something = True
        else:
                if not omit_headers:
                        msg(_("UNPACKAGED CONTENTS"))

                # Print warning messages at the beginning.
                for item_id, parent_id, msg_time, msg_level, msg_type, \
                    msg_text in plan.gen_item_messages():
                        if msg_type != MSG_UNPACKAGED:
                                continue
                        if msg_level == MSG_WARNING:
                                msg(_("WARNING: {0}").format(msg_text))
                # Print the rest of messages.
                for item_id, parent_id, msg_time, msg_level, msg_type, \
                    msg_text in plan.gen_item_messages(ordered=True):
                        if msg_type != MSG_UNPACKAGED:
                                continue
                        if msg_level == MSG_INFO:
                                msg(_("{0}:\n\t{1}").format(
                                    item_id, msg_text))
                        elif msg_level == MSG_ERROR:
                                msg(_("ERROR: {0}").format(msg_text))
                        did_print_something = True
        return did_print_something

def display_plan_cb(api_inst, child_image_plans=None, noexecute=False,
    omit_headers=False, op=None, parsable_version=None, quiet=False,
    quiet_plan=False, show_licenses=False, stage=None, verbose=None,
    unpackaged=False, unpackaged_only=False, plan_only=False):
        """Callback function for displaying plan."""

        if plan_only:
                __display_plan(api_inst, verbose, noexecute)
                return

        plan = api_inst.describe()
        if not plan:
                return

        if stage not in [API_STAGE_DEFAULT, API_STAGE_PLAN] and not quiet_plan:
                # we should have displayed licenses earlier so mark all
                # licenses as having been displayed.
                display_plan_licenses(api_inst, show_req=False)
                return

        if not quiet and parsable_version is None and \
            api_inst.planned_nothingtodo(li_ignore_all=True) and not quiet_plan:
                # nothing todo
                if op == PKG_OP_UPDATE:
                        s = _("No updates available for this image.")
                else:
                        s = _("No updates necessary for this image.")
                if api_inst.ischild():
                        s += " ({0})".format(api_inst.get_linked_name())
                msg(s)

                if op not in [PKG_OP_FIX, PKG_OP_VERIFY] or not verbose:
                        # Even nothingtodo, but need to continue to display INFO
                        # message if verbose is True.
                        return

        if parsable_version is None and not quiet_plan:
                display_plan_licenses(api_inst, show_all=show_licenses)

        if not quiet and not quiet_plan:
                __display_plan(api_inst, verbose, noexecute, op=op)

        if parsable_version is not None:
                parsable_plan = plan.get_parsable_plan(parsable_version,
                    child_image_plans, api_inst=api_inst)
                logger.info(json.dumps(parsable_plan))
        elif not quiet:
                if not quiet_plan:
                        # Ensure a blank line is inserted before the message
                        # output.
                        msg()

                # Message print for package verification result.
                if not unpackaged_only:
                        did_print = __print_verify_result(op, api_inst, plan,
                            noexecute, omit_headers, verbose)

                        # Print an extra line to separate output between
                        # packaged and unpackaged content.
                        if did_print and unpackaged and any(entry[4] ==
                            MSG_UNPACKAGED for entry in
                            plan.gen_item_messages()):
                                msg("".join(["-"] * 80))

                if unpackaged or unpackaged_only:
                        __print_verify_result(op, api_inst, plan, noexecute,
                            omit_headers, verbose, print_packaged=False)

def __api_prepare_plan(operation, api_inst):
        """Prepare plan."""

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        # XXX would be nice to kick the progress tracker.
        try:
                api_inst.prepare()
        except (api_errors.PermissionsException, api_errors.UnknownErrors) as e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.TransportError as e:
                # move past the progress tracker line.
                msg("\n")
                raise e
        except api_errors.PlanLicenseErrors as e:
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
        except api_errors.InvalidPlanError as e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ImageInsufficentSpace as e:
                error(str(e))
                return EXIT_OOPS
        except KeyboardInterrupt:
                raise
        except:
                error(_("\nAn unexpected error happened while preparing for "
                    "{0}:").format(operation))
                raise
        return EXIT_OK

def __api_execute_plan(operation, api_inst):
        """Execute plan."""

        rval = None
        try:
                api_inst.execute_plan()
                pd = api_inst.describe()
                if pd.actuator_timed_out:
                        rval = EXIT_ACTUATOR
                else:
                        rval = EXIT_OK
        except RuntimeError as e:
                error(_("{operation} failed: {err}").format(
                    operation=operation, err=e))
                rval = EXIT_OOPS
        except (api_errors.InvalidPlanError,
            api_errors.ActionExecutionError,
            api_errors.InvalidPackageErrors) as e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                rval = EXIT_OOPS
        except (api_errors.LinkedImageException) as e:
                error(_("{operation} failed (linked image exception(s)):\n"
                    "{err}").format(operation=operation, err=e))
                rval = e.lix_exitrv
        except api_errors.ImageUpdateOnLiveImageException:
                error(_("{0} cannot be done on live image").format(operation))
                rval = EXIT_NOTLIVE
        except api_errors.RebootNeededOnLiveImageException:
                error(_("Requested \"{0}\" operation would affect files that "
                    "cannot be modified in live image.\n"
                    "Please retry this operation on an alternate boot "
                    "environment.").format(operation))
                rval = EXIT_NOTLIVE
        except api_errors.CorruptedIndexException as e:
                error("The search index appears corrupted.  Please rebuild the "
                    "index with 'pkg rebuild-index'.")
                rval = EXIT_OOPS
        except api_errors.ProblematicPermissionsIndexException as e:
                error(str(e))
                error(_("\n(Failure to consistently execute pkg commands as a "
                    "privileged user is often a source of this problem.)"))
                rval = EXIT_OOPS
        except (api_errors.PermissionsException, api_errors.UnknownErrors) as e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                rval = EXIT_OOPS
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                rval = EXIT_OOPS
        except api_errors.BEException as e:
                error(e)
                rval = EXIT_OOPS
        except api_errors.WrapSuccessfulIndexingException:
                raise
        except api_errors.ImageInsufficentSpace as e:
                error(str(e))
                rval = EXIT_OOPS
        except Exception as e:
                error(_("An unexpected error happened during "
                    "{operation}: {err}").format(
                    operation=operation, err=e))
                raise
        finally:
                exc_type = exc_value = exc_tb = None
                if rval is None:
                        # Store original exception so that the real cause of
                        # failure can be raised if this fails.
                        exc_type, exc_value, exc_tb = sys.exc_info()

                try:
                        salvaged = api_inst.describe().salvaged
                        newbe = api_inst.describe().new_be
                        if salvaged and (rval == EXIT_OK or not newbe):
                                # Only show salvaged file list if populated
                                # and operation was successful, or if operation
                                # failed and a new BE was not created for
                                # the operation.
                                logger.error("")
                                logger.error(_("The following unexpected or "
                                    "editable files and directories were\n"
                                    "salvaged while executing the requested "
                                    "package operation; they\nhave been moved "
                                    "to the displayed location in the image:\n"))
                                for opath, spath in salvaged:
                                        logger.error("  {0} -> {1}".format(
                                            opath, spath))
                except Exception:
                        if rval is not None:
                                # Only raise exception encountered here if the
                                # exception previously raised was suppressed.
                                raise

                if exc_value or exc_tb:
                        if six.PY2:
                                six.reraise(exc_value, None, exc_tb)
                        else:
                                raise exc_value

        return rval

def __api_alloc(imgdir, exact_match, pkg_image_used):
        """Allocate API instance."""

        progresstracker = get_tracker()
        try:
                return api.ImageInterface(imgdir, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME,
                    exact_match=exact_match)
        except api_errors.ImageNotFoundException as e:
                if e.user_specified:
                        if pkg_image_used:
                                error(_("No image rooted at '{0}' "
                                    "(set by $PKG_IMAGE)").format(e.user_dir))
                        else:
                                error(_("No image rooted at '{0}'").format(
                                    e.user_dir))
                else:
                        error(_("No image found."))
                return
        except api_errors.PermissionsException as e:
                error(e)
                return
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return

def __api_plan_exception(op, noexecute, verbose, api_inst):
        """Handle plan exception."""

        e_type, e, e_traceback = sys.exc_info()

        if e_type == api_errors.ImageNotFoundException:
                error(_("No image rooted at '{0}'").format(e.user_dir), cmd=op)
                return EXIT_OOPS
        if e_type == api_errors.InventoryException:
                error("\n" + _("{operation} failed (inventory exception):\n"
                    "{err}").format(operation=op, err=e))
                return EXIT_OOPS
        if isinstance(e, api_errors.LinkedImageException):
                error(_("{operation} failed (linked image exception(s)):\n"
                    "{err}").format(operation=op, err=e))
                return e.lix_exitrv
        if e_type == api_errors.IpkgOutOfDateException:
                msg(_("""\
WARNING: pkg(7) appears to be out of date, and should be updated before
running {op}.  Please update pkg(7) by executing 'pkg install
pkg:/package/pkg' as a privileged user and then retry the {op}."""
                    ).format(**locals()))
                return EXIT_OOPS
        if e_type == api_errors.NonLeafPackageException:
                error("\n" + str(e), cmd=op)
                return EXIT_OOPS
        if e_type == api_errors.CatalogRefreshException:
                display_catalog_failures(e)
                return EXIT_OOPS
        if e_type == api_errors.ConflictingActionErrors or \
            e_type == api_errors.ImageBoundaryErrors:
                if verbose:
                        __display_plan(api_inst, verbose, noexecute)
                error("\n" + str(e), cmd=op)
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

        if isinstance(e, (api_errors.CertificateError,
            api_errors.UnknownErrors,
            api_errors.PermissionsException,
            api_errors.InvalidPropertyValue,
            api_errors.InvalidResourceLocation)):
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

def __api_plan(_op, _api_inst, _accept=False, _li_ignore=None, _noexecute=False,
    _omit_headers=False, _origins=None, _parsable_version=None, _quiet=False,
    _quiet_plan=False, _show_licenses=False, _stage=API_STAGE_DEFAULT,
    _verbose=0, **kwargs):
        """API plan invocation entry."""

        # All the api interface functions that we invoke have some
        # common arguments.  Set those up now.
        if _op not in (PKG_OP_REVERT, PKG_OP_FIX, PKG_OP_DEHYDRATE,
            PKG_OP_REHYDRATE):
                kwargs["li_ignore"] = _li_ignore
        kwargs["noexecute"] = _noexecute
        if _origins:
                kwargs["repos"] = _origins
        if _stage != API_STAGE_DEFAULT:
                kwargs["pubcheck"] = False

        # display plan debugging information
        if _verbose > 2:
                DebugValues.set_value("plan", "True")

        # plan the requested operation
        stuff_to_do = None

        if _op == PKG_OP_ATTACH:
                api_plan_func = _api_inst.gen_plan_attach
        elif _op in [PKG_OP_CHANGE_FACET, PKG_OP_CHANGE_VARIANT]:
                api_plan_func = _api_inst.gen_plan_change_varcets
        elif _op == PKG_OP_DEHYDRATE:
                api_plan_func = _api_inst.gen_plan_dehydrate
        elif _op == PKG_OP_DETACH:
                api_plan_func = _api_inst.gen_plan_detach
        elif _op == PKG_OP_EXACT_INSTALL:
                api_plan_func = _api_inst.gen_plan_exact_install
        elif _op == PKG_OP_FIX:
                api_plan_func = _api_inst.gen_plan_fix
        elif _op == PKG_OP_INSTALL:
                api_plan_func = _api_inst.gen_plan_install
        elif _op == PKG_OP_REHYDRATE:
                api_plan_func = _api_inst.gen_plan_rehydrate
        elif _op == PKG_OP_REVERT:
                api_plan_func = _api_inst.gen_plan_revert
        elif _op == PKG_OP_SYNC:
                api_plan_func = _api_inst.gen_plan_sync
        elif _op == PKG_OP_UNINSTALL:
                api_plan_func = _api_inst.gen_plan_uninstall
        elif _op == PKG_OP_UPDATE:
                api_plan_func = _api_inst.gen_plan_update
        else:
                raise RuntimeError("__api_plan() invalid op: {0}".format(_op))

        planned_self = False
        child_plans = []
        try:
                for pd in api_plan_func(**kwargs):
                        if planned_self:
                                # we don't display anything for child images
                                # since they currently do their own display
                                # work (unless parsable output is requested).
                                child_plans.append(pd)
                                continue

                        # the first plan description is always for ourself.
                        planned_self = True
                        pkg_timer.record("planning", logger=logger)

                        # if we're in parsable mode don't display anything
                        # until after we finish planning for all children
                        if _parsable_version is None:
                                display_plan(_api_inst, [], _noexecute,
                                    _omit_headers, _op, _parsable_version,
                                    _quiet, _quiet_plan, _show_licenses, _stage,
                                    _verbose)

                        # if requested accept licenses for child images.  we
                        # have to do this before recursing into children.
                        if _accept:
                                accept_plan_licenses(_api_inst)
        except:
                rv = __api_plan_exception(_op, _noexecute, _verbose, _api_inst)
                if rv != EXIT_OK:
                        pkg_timer.record("planning", logger=logger)
                        return rv

        if not planned_self:
                # if we got an exception we didn't do planning for children
                pkg_timer.record("planning", logger=logger)

        elif _api_inst.isparent(_li_ignore):
                # if we didn't get an exception and we're a parent image then
                # we should have done planning for child images.
                pkg_timer.record("planning children", logger=logger)

        # if we didn't display our own plan (due to an exception), or if we're
        # in parsable mode, then display our plan now.
        if not planned_self or _parsable_version is not None:
                try:
                        display_plan(_api_inst, child_plans, _noexecute,
                            _omit_headers, _op, _parsable_version, _quiet,
                            _quiet_plan, _show_licenses, _stage, _verbose)
                except api_errors.ApiException as e:
                        error(e, cmd=_op)
                        return EXIT_OOPS

        # if we didn't accept licenses (due to an exception) then do that now.
        if not planned_self and _accept:
                accept_plan_licenses(_api_inst)

        return EXIT_OK

def __api_plan_file(api_inst):
        """Return the path to the PlanDescription save file."""

        plandir = api_inst.img_plandir
        return os.path.join(plandir, "plandesc")

def __api_plan_save(api_inst):
        """Save an image plan to a file."""

        # get a pointer to the plan
        plan = api_inst.describe()

        # save the PlanDescription to a file
        path = __api_plan_file(api_inst)
        oflags = os.O_CREAT | os.O_TRUNC | os.O_WRONLY
        try:
                fd = os.open(path, oflags, 0o644)
                with os.fdopen(fd, "w") as fobj:
                        plan._save(fobj)

                # cleanup any old style imageplan save files
                for f in os.listdir(api_inst.img_plandir):
                        path = os.path.join(api_inst.img_plandir, f)
                        if re.search("^actions\.[0-9]+\.json$", f):
                                os.unlink(path)
                        if re.search("^pkgs\.[0-9]+\.json$", f):
                                os.unlink(path)
        except OSError as e:
                raise api_errors._convert_error(e)

        pkg_timer.record("saving plan", logger=logger)

def __api_plan_load(api_inst, stage, origins):
        """Loan an image plan from a file."""

        # load an existing plan
        path = __api_plan_file(api_inst)
        plan = api.PlanDescription()
        try:
                with open(path) as fobj:
                        plan._load(fobj)
        except OSError as e:
                raise api_errors._convert_error(e)

        pkg_timer.record("loading plan", logger=logger)

        api_inst.reset()
        api_inst.set_alt_repos(origins)
        api_inst.load_plan(plan, prepared=(stage == API_STAGE_EXECUTE))
        pkg_timer.record("re-initializing plan", logger=logger)

        if stage == API_STAGE_EXECUTE:
                __api_plan_delete(api_inst)

def __api_plan_delete(api_inst):
        """Delete an image plan file."""

        path = __api_plan_file(api_inst)
        try:
                os.unlink(path)
        except OSError as e:
                raise api_errors._convert_error(e)

def _verify_exit_code(api_inst):
        """Determine the exit code of pkg verify, which should be based on
        whether we find errors."""

        plan = api_inst.describe()
        for item_id, msg_time, msg_type, msg_text in plan.gen_item_messages():
                if msg_type == MSG_ERROR:
                        return EXIT_OOPS
        return EXIT_OK

def __api_op(_op, _api_inst, _accept=False, _li_ignore=None, _noexecute=False,
    _omit_headers=False, _origins=None, _parsable_version=None, _quiet=False,
    _quiet_plan=False, _show_licenses=False, _stage=API_STAGE_DEFAULT,
    _verbose=0, **kwargs):
        """Do something that involves the api.

        Arguments prefixed with '_' are primarily used within this
        function.  All other arguments must be specified via keyword
        assignment and will be passed directly on to the api
        interfaces being invoked."""

        if _stage in [API_STAGE_DEFAULT, API_STAGE_PLAN]:
                # create a new plan
                rv = __api_plan(_op=_op, _api_inst=_api_inst,
                    _accept=_accept, _li_ignore=_li_ignore,
                    _noexecute=_noexecute, _omit_headers=_omit_headers,
                    _origins=_origins, _parsable_version=_parsable_version,
                    _quiet=_quiet, _quiet_plan=_quiet_plan,
                    _show_licenses=_show_licenses, _stage=_stage,
                    _verbose=_verbose, **kwargs)

                if rv != EXIT_OK:
                        return rv
                if not _noexecute and _stage == API_STAGE_PLAN:
                        # We always save the plan, even if it is a noop.  We
                        # do this because we want to be able to verify that we
                        # can load and execute a noop plan.  (This mimics
                        # normal api behavior which doesn't prevent an api
                        # consumer from creating a noop plan and then
                        # preparing and executing it.)
                        __api_plan_save(_api_inst)
                # for pkg verify
                if _op == PKG_OP_FIX and _noexecute and _quiet_plan:
                        return _verify_exit_code(_api_inst)
                if _api_inst.planned_nothingtodo():
                        return EXIT_NOP
                if _noexecute or _stage == API_STAGE_PLAN:
                        return EXIT_OK
        else:
                assert _stage in [API_STAGE_PREPARE, API_STAGE_EXECUTE]
                __api_plan_load(_api_inst, _stage, _origins)

        # Exceptions which happen here are printed in the above level,
        # with or without some extra decoration done here.
        if _stage in [API_STAGE_DEFAULT, API_STAGE_PREPARE]:
                ret_code = __api_prepare_plan(_op, _api_inst)
                pkg_timer.record("preparing", logger=logger)

                if ret_code != EXIT_OK:
                        return ret_code
                if _stage == API_STAGE_PREPARE:
                        return EXIT_OK

        ret_code = __api_execute_plan(_op, _api_inst)
        pkg_timer.record("executing", logger=logger)

        return ret_code

class RemoteDispatch(object):
        """RPC Server Class which invoked by the PipedRPCServer when a RPC
        request is recieved."""

        def __dispatch(self, op, pwargs):

                pkg_timer.record("rpc dispatch wait", logger=logger)

                # if we were called with no arguments then pwargs will be []
                if pwargs == []:
                        pwargs = {}

                op_supported = [
                    PKG_OP_AUDIT_LINKED,
                    PKG_OP_DETACH,
                    PKG_OP_PUBCHECK,
                    PKG_OP_SYNC,
                    PKG_OP_UPDATE,
                    PKG_OP_INSTALL,
                    PKG_OP_CHANGE_FACET,
                    PKG_OP_CHANGE_VARIANT,
                    PKG_OP_UNINSTALL
                ]
                if op not in op_supported:
                        raise Exception(
                            'method "{0}" is not supported'.format(op))

                # if a stage was specified, get it.
                stage = pwargs.get("stage", API_STAGE_DEFAULT)
                assert stage in api_stage_values

                # if we're starting a new operation, reset the api.  we do
                # this just in case our parent updated our linked image
                # metadata.
                if stage in [API_STAGE_DEFAULT, API_STAGE_PLAN]:
                        _api_inst.reset()

                if "pargs" not in pwargs:
                        pwargs["pargs"] = []

                op_func = cmds[op][0]

                rv = op_func(op, _api_inst, **pwargs)

                if DebugValues["timings"]:
                        msg(str(pkg_timer))
                pkg_timer.reset()

                return rv

        def _dispatch(self, op, pwargs):
                """Primary RPC dispatch function.

                This function must be kept super simple because if we take an
                exception here then no output will be generated and this
                package remote process will silently exit with a non-zero
                return value (and the lack of an exception message makes this
                failure very difficult to debug).  Hence we wrap the real
                remote dispatch routine with a call to handle_errors(), which
                will catch and display any exceptions encountered."""

                # flush output before and after every operation.
                misc.flush_output()
                misc.truncate_file(sys.stdout)
                misc.truncate_file(sys.stderr)
                rv = handle_errors(self.__dispatch, True, op, pwargs)
                misc.flush_output()
                return rv

def remote(op, api_inst, pargs, ctlfd):
        """Execute commands from a remote pipe"""

        #
        # this is kinda a gross hack.  SocketServer.py uses select.select()
        # which doesn't support file descriptors larger than FD_SETSIZE.
        # Since ctlfd may have been allocated in a parent process with many
        # file descriptors, it may be larger than FD_SETSIZE.  Here in the
        # child, though, the majority of those have been closed, so os.dup()
        # should return a lower-numbered descriptor which will work with
        # select.select().
        #
        ctlfd_new = os.dup(ctlfd)
        os.close(ctlfd)
        ctlfd = ctlfd_new

        rpc_server = pipeutils.PipedRPCServer(ctlfd)
        rpc_server.register_introspection_functions()
        rpc_server.register_instance(RemoteDispatch())

        pkg_timer.record("rpc startup", logger=logger)
        rpc_server.serve_forever()

def change_variant(op, api_inst, pargs,
    accept, act_timeout, backup_be, backup_be_name, be_activate, be_name,
    li_ignore, li_parent_sync, li_erecurse, new_be, noexecute, origins,
    parsable_version, quiet, refresh_catalogs, reject_pats, show_licenses,
    stage, update_index, verbose):
        """Attempt to change a variant associated with an image, updating
        the image contents as necessary."""

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        if not pargs:
                usage(_("{0}: no variants specified").format(op))

        variants = dict()
        for arg in pargs:
                # '=' is not allowed in variant names or values
                if (len(arg.split('=')) != 2):
                        usage(_("{0}: variants must to be of the form "
                            "'<name>=<value>'.").format(op))

                # get the variant name and value
                name, value = arg.split('=')
                if not name.startswith("variant."):
                        name = "variant.{0}".format(name)

                # forcibly lower-case for 'true' or 'false'
                if not value.islower() and value.lower() in ("true", "false"):
                        value = value.lower()

                # make sure the user didn't specify duplicate variants
                if name in variants:
                        usage(_("{subcmd}: duplicate variant specified: "
                            "{variant}").format(subcmd=op, variant=name))
                variants[name] = value

        return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
            _noexecute=noexecute, _origins=origins,
            _parsable_version=parsable_version, _quiet=quiet,
            _show_licenses=show_licenses, _stage=stage, _verbose=verbose,
            act_timeout=act_timeout, backup_be=backup_be,
            backup_be_name=backup_be_name, be_activate=be_activate,
            be_name=be_name, li_erecurse=li_erecurse,
            li_parent_sync=li_parent_sync, new_be=new_be,
            refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
            update_index=update_index, variants=variants)

def change_facet(op, api_inst, pargs,
    accept, act_timeout, backup_be, backup_be_name, be_activate, be_name,
    li_ignore, li_erecurse, li_parent_sync, new_be, noexecute, origins,
    parsable_version, quiet, refresh_catalogs, reject_pats, show_licenses,
    stage, update_index, verbose):
        """Attempt to change the facets as specified, updating
        image as necessary"""

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        if not pargs:
                usage(_("{0}: no facets specified").format(op))

        facets = {}
        allowed_values = {
            "TRUE" : True,
            "FALSE": False,
            "NONE" : None
        }

        for arg in pargs:

                # '=' is not allowed in facet names or values
                if (len(arg.split('=')) != 2):
                        usage(_("{0}: facets must to be of the form "
                            "'facet....=[True|False|None]'").format(op))

                # get the facet name and value
                name, value = arg.split('=')
                if not name.startswith("facet."):
                        name = "facet." + name

                if value.upper() not in allowed_values:
                        usage(_("{0}: facets must to be of the form "
                            "'facet....=[True|False|None]'.").format(op))

                facets[name] = allowed_values[value.upper()]

        return __api_op(op, api_inst, _accept=accept, _li_ignore=li_ignore,
            _noexecute=noexecute, _origins=origins,
            _parsable_version=parsable_version, _quiet=quiet,
            _show_licenses=show_licenses, _stage=stage, _verbose=verbose,
            act_timeout=act_timeout, backup_be=backup_be,
            backup_be_name=backup_be_name, be_activate=be_activate,
            be_name=be_name, facets=facets, li_erecurse=li_erecurse,
            li_parent_sync=li_parent_sync, new_be=new_be,
            refresh_catalogs=refresh_catalogs, reject_list=reject_pats,
            update_index=update_index)

def __handle_client_json_api_output(out_json, op):
        """This is the main client_json_api output handling function used for
        install, update and uninstall and so on."""

        if "errors" in out_json:
                _generate_error_messages(out_json["status"],
                    out_json["errors"], cmd=op)

        if "data" in out_json and "repo_status" in out_json["data"]:
                display_repo_failures(out_json["data"]["repo_status"])

        return out_json["status"]

def _emit_error_general_cb(status, err, cmd=None, selected_type=[],
    add_info=misc.EmptyDict):
        """Callback for emitting general errors."""

        if status == EXIT_BADOPT:
                # Usage errors are not in any specific type, print it only
                # there is no selected type.
                if not selected_type:
                        usage(err["reason"], cmd=cmd)
                else:
                        return False
        elif "errtype" in err:
                if err["errtype"] == "format_update":
                        # if the selected_type is specified and err not in selected type,
                        # Don't print and return False.
                        if selected_type and err["errtype"] not in selected_type:
                                return False
                        emsg("\n")
                        emsg(err["reason"])
                        emsg(_("To continue, execute 'pkg update-format' as a "
                            "privileged user and then try again.  Please note "
                            "that updating the format of the image will render "
                            "it unusable with older versions of the pkg(7) "
                            "system."))
                elif err["errtype"] == "catalog_refresh":
                        if selected_type and err["errtype"] not in selected_type:
                                return False

                        if "reason" in err:
                                emsg(err["reason"])
                        elif "info" in err:
                                msg(err["info"])
                elif err["errtype"] == "catalog_refresh_failed":
                        if selected_type and err["errtype"] not in selected_type:
                                return False

                        if "reason" in err:
                                emsg(" ")
                                emsg(err["reason"])
                elif err["errtype"] == "publisher_set":
                        if selected_type and err["errtype"] not in selected_type:
                                return False

                        emsg(err["reason"])
                elif err["errtype"] == "plan_license":
                        if selected_type and err["errtype"] not in selected_type:
                                return False

                        emsg(err["reason"])
                        emsg(_("To indicate that you "
                            "agree to and accept the terms of the licenses of "
                            "the packages listed above, use the --accept "
                            "option. To display all of the related licenses, "
                            "use the --licenses option."))
                elif err["errtype"] in ["inventory", "inventory_extra"]:
                        if selected_type and err["errtype"] not in selected_type:
                                return False

                        emsg(" ")
                        emsg(err["reason"])
                        if err["errtype"] == "inventory_extra":
                                emsg("Use -af to allow all versions.")
                elif err["errtype"] == "unsupported_repo_op":
                        if selected_type and err["errtype"] not in selected_type:
                                return False

                        emsg(_("""
To add a publisher using this repository, execute the following command as a
privileged user:

pkg set-publisher -g {0} <publisher>
""").format(add_info["repo_uri"]))
                elif "info" in err:
                        msg(err["info"])
                elif "reason" in err:
                        emsg(err["reason"])
        else:
                if selected_type:
                        return False

                if "reason" in err:
                        emsg(err["reason"])
                elif "info" in err:
                        msg(err["info"])
        return True

def _generate_error_messages(status, err_list,
    msg_cb=_emit_error_general_cb, selected_type=[], cmd=None,
    add_info=misc.EmptyDict):
        """Generate error messages."""

        errs_left = [err for err in err_list if not msg_cb(status, err,
            selected_type=selected_type, cmd=cmd, add_info=add_info)]
        # Return errors not being printed.
        return errs_left

def exact_install(op, api_inst, pargs,
    accept, backup_be, backup_be_name, be_activate, be_name, li_ignore,
    li_parent_sync, new_be, noexecute, origins, parsable_version, quiet,
    refresh_catalogs, reject_pats, show_licenses, update_index, verbose):
        """Attempt to take package specified to INSTALLED state.
        The operands are interpreted as glob patterns."""

        out_json = client_api._exact_install(op, api_inst, pargs, accept,
            backup_be, backup_be_name, be_activate, be_name, li_ignore,
            li_parent_sync, new_be, noexecute, origins, parsable_version,
            quiet, refresh_catalogs, reject_pats, show_licenses, update_index,
            verbose, display_plan_cb=display_plan_cb, logger=logger)

        return  __handle_client_json_api_output(out_json, op)

def install(op, api_inst, pargs,
    accept, act_timeout, backup_be, backup_be_name, be_activate, be_name,
    li_ignore, li_erecurse, li_parent_sync, new_be, noexecute, origins,
    parsable_version, quiet, refresh_catalogs, reject_pats, show_licenses,
    stage, update_index, verbose):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        out_json = client_api._install(op, api_inst, pargs,
            accept, act_timeout, backup_be, backup_be_name, be_activate,
            be_name, li_ignore, li_erecurse, li_parent_sync, new_be, noexecute,
            origins, parsable_version, quiet, refresh_catalogs, reject_pats,
            show_licenses, stage, update_index, verbose,
            display_plan_cb=display_plan_cb, logger=logger)

        return  __handle_client_json_api_output(out_json, op)

def update(op, api_inst, pargs, accept, act_timeout, backup_be, backup_be_name,
    be_activate, be_name, force, ignore_missing, li_ignore, li_erecurse,
    li_parent_sync, new_be, noexecute, origins, parsable_version, quiet,
    refresh_catalogs, reject_pats, show_licenses, stage, update_index, verbose):
        """Attempt to take all installed packages specified to latest
        version."""

        out_json = client_api._update(op, api_inst, pargs, accept, act_timeout,
            backup_be, backup_be_name, be_activate, be_name, force,
            ignore_missing, li_ignore, li_erecurse, li_parent_sync, new_be,
            noexecute, origins, parsable_version, quiet, refresh_catalogs,
            reject_pats, show_licenses, stage, update_index, verbose,
            display_plan_cb=display_plan_cb, logger=logger)

        return __handle_client_json_api_output(out_json, op)

def uninstall(op, api_inst, pargs,
    act_timeout, backup_be, backup_be_name, be_activate, be_name,
    ignore_missing, li_ignore, li_erecurse, li_parent_sync, new_be, noexecute,
    parsable_version, quiet, stage, update_index, verbose):
        """Attempt to take package specified to DELETED state."""

        out_json = client_api._uninstall(op, api_inst, pargs,
            act_timeout, backup_be, backup_be_name, be_activate, be_name,
            ignore_missing, li_ignore, li_erecurse, li_parent_sync, new_be,
            noexecute, parsable_version, quiet, stage, update_index, verbose,
            display_plan_cb=display_plan_cb, logger=logger)

        return __handle_client_json_api_output(out_json, op)

def verify(op, api_inst, pargs, omit_headers, parsable_version, quiet, verbose,
    unpackaged, unpackaged_only, verify_paths):
        """Determine if installed packages match manifests."""

        out_json = client_api._verify(op, api_inst, pargs, omit_headers,
            parsable_version, quiet, verbose, unpackaged, unpackaged_only,
            display_plan_cb=display_plan_cb, logger=logger,
            verify_paths=verify_paths)

        # Print error messages.
        if "errors" in out_json:
                _generate_error_messages(out_json["status"],
                    out_json["errors"], cmd=op)

        # Since the verify output has been handled by display_plan_cb, only
        # status code needs to be returned.
        return out_json["status"]

def revert(op, api_inst, pargs,
    backup_be, backup_be_name, be_activate, be_name, new_be, noexecute,
    parsable_version, quiet, tagged, verbose):
        """Attempt to revert files to their original state, either
        via explicit path names or via tagged contents."""

        if not pargs:
                usage(_("at least one file path or tag name required"), cmd=op)

        return __api_op(op, api_inst, _noexecute=noexecute, _quiet=quiet,
            _verbose=verbose, backup_be=backup_be, be_activate=be_activate,
            backup_be_name=backup_be_name, be_name=be_name, new_be=new_be,
            _parsable_version=parsable_version, args=pargs, tagged=tagged)

def dehydrate(op, api_inst, pargs, noexecute, publishers, quiet, verbose):
        """Minimize image size for later redeployment."""

        return __api_op(op, api_inst, _noexecute=noexecute, _quiet=quiet,
            _verbose=verbose, publishers=publishers)

def rehydrate(op, api_inst, pargs, noexecute, publishers, quiet, verbose):
        """Restore content removed from a dehydrated image."""

        return __api_op(op, api_inst, _noexecute=noexecute, _quiet=quiet,
            _verbose=verbose, publishers=publishers)

def fix(op, api_inst, pargs, accept, backup_be, backup_be_name, be_activate,
    be_name, new_be, noexecute, omit_headers, parsable_version, quiet,
    show_licenses, verbose, unpackaged):
        """Fix packaging errors found in the image."""

        out_json = client_api._fix(op, api_inst, pargs, accept, backup_be,
            backup_be_name, be_activate, be_name, new_be, noexecute,
            omit_headers, parsable_version, quiet, show_licenses, verbose,
            unpackaged, display_plan_cb=display_plan_cb, logger=logger)

        # Print error messages.
        if "errors" in out_json:
                _generate_error_messages(out_json["status"],
                    out_json["errors"], cmd=op)

        return out_json["status"]

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
                    for mediator, mediation in six.iteritems(api_inst.mediators)
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
                                med_impl += "(@{0})".format(med_impl_ver)
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
            "mediator" : [("default", "json", "tsv"), _("MEDIATOR"), ""],
            "version" : [("default", "json", "tsv"), _("VERSION"), ""],
            "version-source": [("default", "json", "tsv"), _("VER. SRC."), ""],
            "implementation" : [("default", "json", "tsv"), _("IMPLEMENTATION"),
                ""],
            "implementation-source": [("default", "json", "tsv"),
                _("IMPL. SRC."), ""],
            "implementation-version" : [("json", "tsv"), _("IMPL. VER."), ""],
        }
        desired_field_order = (_("MEDIATOR"), _("VER. SRC."), _("VERSION"),
            _("IMPL. SRC."), _("IMPLEMENTATION"), _("IMPL. VER."))

        # Default output formatting.
        def_fmt = "{0:" + str(max_mname_len) + "} {1:" + str(max_vsrc_len) + \
            "} {2:" + str(max_version_len) + "} {3:" + str(max_isrc_len) + \
            "} {4}"

        if api_inst.get_dehydrated_publishers():
                msg(_("WARNING: pkg mediators may not be accurately shown "
                    "when one or more publishers have been dehydrated. The "
                    "correct mediation will be applied when the publishers "
                    "are rehydrated."))

        if found or (not requested_mediators and output_format == "default"):
                sys.stdout.write(misc.get_listing(desired_field_order,
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

def set_mediator(op, api_inst, pargs,
    backup_be, backup_be_name, be_activate, be_name, med_implementation,
    med_version, new_be, noexecute, parsable_version, quiet, update_index,
    verbose):
        """Set the version and/or implementation for the specified
        mediator(s)."""

        if not pargs:
                usage(_("at least one mediator must be specified"),
                    cmd=op)
        if not (med_version or med_implementation):
                usage(_("a mediator version and/or implementation must be "
                    "specified using -V and -I"), cmd=op)

        if verbose > 2:
                DebugValues.set_value("plan", "True")

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
                    noexecute=noexecute, backup_be=backup_be,
                    backup_be_name=backup_be_name, be_name=be_name,
                    new_be=new_be, be_activate=be_activate):
                        continue
                stuff_to_do = not api_inst.planned_nothingtodo()
        except:
                ret_code = __api_plan_exception(op, api_inst, noexecute,
                    verbose)
                if ret_code != EXIT_OK:
                        return ret_code

        if not stuff_to_do:
                if verbose:
                        __display_plan(api_inst, verbose, noexecute)
                if parsable_version is not None:
                        try:
                                __display_parsable_plan(api_inst,
                                    parsable_version)
                        except api_errors.ApiException as e:
                                error(e, cmd=op)
                                return EXIT_OOPS
                else:
                        msg(_("No changes required."))
                return EXIT_NOP

        if api_inst.get_dehydrated_publishers():
                msg(_("WARNING: pkg mediators may not be accurately shown "
                    "when one or more publishers have been dehydrated. The "
                    "correct mediation will be applied when the publishers "
                    "are rehydrated."))

        if not quiet:
                __display_plan(api_inst, verbose, noexecute)
        if parsable_version is not None:
                try:
                        __display_parsable_plan(api_inst, parsable_version)
                except api_errors.ApiException as e:
                        error(e, cmd=op)
                        return EXIT_OOPS

        if noexecute:
                return EXIT_OK

        ret_code = __api_prepare_plan(op, api_inst)
        if ret_code != EXIT_OK:
                return ret_code

        ret_code = __api_execute_plan(op, api_inst)

        return ret_code

def unset_mediator(op, api_inst, pargs,
    backup_be, backup_be_name, be_activate, be_name, med_implementation,
    med_version, new_be, noexecute, parsable_version, quiet, update_index,
    verbose):
        """Unset the version and/or implementation for the specified
        mediator(s)."""

        if not pargs:
                usage(_("at least one mediator must be specified"),
                    cmd=op)
        if verbose > 2:
                DebugValues.set_value("plan", "True")

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
                    noexecute=noexecute, backup_be=backup_be,
                    backup_be_name=backup_be_name, be_name=be_name,
                    new_be=new_be, be_activate=be_activate):
                        continue
                stuff_to_do = not api_inst.planned_nothingtodo()
        except:
                ret_code = __api_plan_exception(op, api_inst, noexecute,
                    verbose)
                if ret_code != EXIT_OK:
                        return ret_code

        if not stuff_to_do:
                if verbose:
                        __display_plan(api_inst, verbose, noexecute)
                if parsable_version is not None:
                        try:
                                __display_parsable_plan(api_inst,
                                    parsable_version)
                        except api_errors.ApiException as e:
                                error(e, cmd=op)
                                return EXIT_OOPS
                else:
                        msg(_("No changes required."))
                return EXIT_NOP

        if not quiet:
                __display_plan(api_inst, verbose, noexecute)
        if parsable_version is not None:
                try:
                        __display_parsable_plan(api_inst, parsable_version)
                except api_errors.ApiException as e:
                        error(e, cmd=op)
                        return EXIT_OOPS

        if noexecute:
                return EXIT_OK

        ret_code = __api_prepare_plan(op, api_inst)
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
                        logger.info(_(
                            "    {avoid_pkg} (group dependency of "
                            "'{tracking_pkg}')")
                           .format(avoid_pkg=a[0], tracking_pkg=tracking))
                else:
                        logger.info("    {0}".format(a[0]))

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
                        logger.info(_("{name} was frozen at {ver}").format(
                            name=pfmri.pkg_name, ver=vertext))
                return EXIT_OK
        except api_errors.FreezePkgsException as e:
                error("\n{0}".format(e), cmd="freeze")
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
                        logger.info(_("{0} was unfrozen.").format(s))
                return EXIT_OK
        except:
                return __api_plan_exception("unfreeze", False, 0, api_inst)

def __display_cur_frozen(api_inst, display_headers):
        """Display the current frozen list"""

        try:
                lst = sorted(api_inst.get_frozen_list())
        except api_errors.ApiException as e:
                error(e)
                return EXIT_OOPS
        if len(lst) == 0:
                return EXIT_OK

        fmt = "{name:18} {ver:27} {time:24} {comment}"
        if display_headers:
                logger.info(fmt.format(
                    name=_("NAME"),
                    ver=_("VERSION"),
                    time=_("DATE"),
                    comment=_("COMMENT")
                ))

        for pfmri, comment, timestamp in lst:
                vertext = pfmri.version.get_short_version()
                ts = pfmri.version.get_timestamp()
                if ts:
                        vertext += ":" + pfmri.version.timestr
                if not comment:
                        comment = "None"
                logger.info(fmt.format(
                    name=pfmri.pkg_name,
                    comment=comment,
                    time=time.strftime("%d %b %Y %H:%M:%S %Z",
                                time.localtime(timestamp)),
                    ver=vertext
                ))
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
        useful for pkg.misc.list_actions_by_attrs.

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
                            "The problematic structure:{0!r}").format(tup))
                        return False
                try:
                        action = actions.fromstr(action.rstrip())
                except actions.ActionError as e:
                        error(_("The repository returned an invalid or "
                            "unsupported action.\n{0}").format(e))
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
                                usage(_("action level options ('{0}') to -o "
                                    "cannot be used with the -p "
                                    "option").format(a), cmd="search")
                        break

        searches = []

        # Strip pkg:/ or pkg:/// from the fmri.
        # If fmri has pkg:// then strip the prefix
        # from 'pkg://' upto the first slash.

        qtext = re.sub(r"pkg:///|pkg://[^/]*/|pkg:/", "", " ".join(pargs))

        try:
                query = [api.Query(qtext, case_sensitive,
                    return_actions)]
        except api_errors.BooleanQueryException as e:
                error(e)
                return EXIT_OOPS
        except api_errors.ParseError as e:
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
                                        except ValueError as e:
                                                error(_("The repository "
                                                    "returned a malformed "
                                                    "result:{0!r}").format(
                                                    raw_value))
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
                        except api_errors.ApiException as e:
                                err = e
                        lines = list(misc.list_actions_by_attrs(unprocessed_res,
                            attrs, show_all=True, remove_consec_dup_lines=True,
                            last_res=last_line))
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
                                    widths, justs, line).format(
                                    *line)).rstrip())
                                last_line = line
                        st = time.time()
                if err:
                        raise err


        except (api_errors.IncorrectIndexFileHash,
            api_errors.InconsistentIndexException):
                error(_("The search index appears corrupted.  Please "
                    "rebuild the index with 'pkg rebuild-index'."))
                return EXIT_OOPS
        except api_errors.ProblematicSearchServers as e:
                error(e)
                bad_res = True
        except api_errors.SlowSearchUsed as e:
                error(e)
        except (api_errors.IncorrectIndexFileHash,
            api_errors.InconsistentIndexException):
                error(_("The search index appears corrupted.  Please "
                    "rebuild the index with 'pkg rebuild-index'."))
                return EXIT_OOPS
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException as e:
                error(e)
                return EXIT_OOPS
        if good_res and bad_res:
                retcode = EXIT_PARTIAL
        elif bad_res:
                retcode = EXIT_OOPS
        elif good_res:
                retcode = EXIT_OK
        return retcode

def info(op, api_inst, pargs, display_license, info_local, info_remote,
    origins, quiet):
        """Display information about a package or packages.
        """

        ret_json = client_api._info(op, api_inst, pargs, display_license,
            info_local, info_remote, origins, quiet)

        if "data" in ret_json:
                # display_license is true.
                if "licenses" in ret_json["data"]:
                        data_type = "licenses"
                elif "package_attrs" in ret_json["data"]:
                        data_type = "package_attrs"

                for i, pis in enumerate(ret_json["data"][data_type]):
                        if not quiet and i > 0:
                                msg("")

                        if display_license and not quiet:
                                for lic in pis[1]:
                                        msg(lic)
                                continue

                        try:
                                max_width = max(
                                    len(attr[0])
                                    for attr in pis
                                )
                        except ValueError:
                                # Only display header if there are
                                # other attributes to show.
                                continue
                        for attr_l in pis:
                                attr, kval = tuple(attr_l)
                                label = "{0}: ".format(attr.rjust(max_width))
                                res = "\n".join(item for item in kval)
                                if res:
                                        wrapper = textwrap.TextWrapper(
                                            initial_indent=label,
                                            break_on_hyphens=False,
                                            break_long_words=False,
                                            subsequent_indent=(max_width + 2) \
                                            * " ", width=80)
                                        msg(wrapper.fill(res))

        if "errors" in ret_json:
                _generate_error_messages(ret_json["status"], ret_json["errors"],
                    cmd="info")

        return ret_json["status"]

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
        # pass to the format specifier.
        widths = [ e[0] * default_left(e[1]) for e in zip(widths, justs) ]
        fmt = ""
        for n in range(len(widths)):
                if widths[n] < 0:
                        fmt += "{{{0}:<{1:d}}} ".format(n, -widths[n])
                else:
                        fmt += "{{{0}:>{1:d}}} ".format(n, widths[n])

        msg(fmt.format(*headers).rstrip())

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

        fmt = ""
        if display_headers:
                # Now that we know all the widths, multiply them by the
                # justification values to get positive or negative numbers to
                # pass to the format specifier.
                line_widths = [
                    w * guess_unknown(j, a)
                    for w, j, a in zip(widths, justs, line)
                ]
                for n in range(len(line_widths)):
                        if line_widths[n] < 0:
                                fmt += "{{{0}!s:<{1}}} ".format(n,
                                    -line_widths[n])
                        else:
                                fmt += "{{{0}!s:>{1}}} ".format(n,
                                    line_widths[n])
                return fmt
        for n in range(len(widths)):
                fmt += "{{{0}!s}}\t".format(n)
        fmt.rstrip("\t")
        return fmt

def display_contents_results(actionlist, attrs, sort_attrs, display_headers):
        """Print results of a "list" operation.  Returns False if no output
        was produced."""

        justs = calc_justs(attrs)
        lines = list(misc.list_actions_by_attrs(actionlist, attrs))
        widths = calc_widths(lines, attrs)

        if sort_attrs:
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
                line_gen = sorted(lines, key=key_extract)
        else:
                line_gen = lines

        printed_output = False
        for line in line_gen:
                text = (create_output_format(display_headers, widths, justs,
                    line).format(*line)).rstrip()
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
                                usage(_("Invalid attribute '{0}'").format(a),
                                    cmd)

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

                invalid = set(("-H", "-o", "-t", "-s", "-a")). \
                    intersection(set([x[0] for x in opts]))

                if len(invalid) > 0:
                        usage(_("-m and {0} may not be specified at the same "
                            "time").format(invalid.pop()), cmd=subcommand)

        if action_types and all(
            atype not in default_attrs
            for atype in action_types):
                usage(_("no valid action types specified"), cmd=subcommand)

        check_attrs(attrs, subcommand)

        api_inst.progresstracker.set_purpose(
            api_inst.progresstracker.PURPOSE_LISTING)

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
                if not action_types:
                        # XXX Possibly have multiple exclusive attributes per
                        # column? If listing dependencies and files, you could
                        # have a path/fmri column which would list paths for
                        # files and fmris for dependencies.
                        attrs = ["path"]
                else:
                        # Choose default attrs based on specified action
                        # types. A list is used here instead of a set is
                        # because we want to maintain the order of the
                        # attributes in which the users specify.
                        for attr in itertools.chain.from_iterable(
                            default_attrs.get(atype, EmptyI)
                            for atype in action_types):
                                    if attr not in attrs:
                                            attrs.append(attr)

        if not sort_attrs and not display_raw:
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

        # Now get the matching list of packages and display it.
        processed = False
        notfound = EmptyI
        try:
                res = api_inst.get_pkg_list(pkg_list, patterns=pargs,
                    raise_unmatched=True, ranked=remote, return_fmris=True,
                    variants=True, repos=origins)
                manifests = []

                for pfmri, summ, cats, states, pattrs in res:
                        manifests.append(api_inst.get_manifest(pfmri,
                            all_variants=display_raw, repos=origins))
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.InvalidPackageErrors as e:
                error(str(e), cmd=subcommand)
                api_inst.log_operation_end(
                    result=RESULT_FAILED_UNKNOWN)
                return EXIT_OOPS
        except api_errors.CatalogRefreshException as e:
                display_catalog_failures(e)
                return EXIT_OOPS
        except api_errors.InventoryException as e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        api_inst.log_operation_end(
                            result=RESULT_FAILED_BAD_REQUEST)
                        return EXIT_OOPS
                notfound = e.notfound
        else:
                if local and not manifests and not pargs:
                        error(_("no packages installed"), cmd=subcommand)
                        api_inst.log_operation_end(
                            result=RESULT_NOTHING_TO_DO)
                        return EXIT_OOPS

        # Build a generator expression based on whether specific action types
        # were provided.
        if action_types:
                # If query is limited to specific action types, use the more
                # efficient type-based generation mechanism.
                gen_expr = (
                    (m.fmri, a, None, None, None)
                    for m in manifests
                    for a in m.gen_actions_by_types(action_types,
                        attr_match=attr_match, excludes=excludes)
                )
        else:
                gen_expr = (
                    (m.fmri, a, None, None, None)
                    for m in manifests
                    for a in m.gen_actions(attr_match=attr_match,
                        excludes=excludes)
                )

        # Determine if the query returned any results by "peeking" at the first
        # value returned from the generator expression.
        try:
                found = next(gen_expr)
        except StopIteration:
                found = None
                actionlist = []

        if found:
                # If any matching entries were found, create a new generator
                # expression using itertools.chain that includes the first
                # result.
                actionlist = itertools.chain([found], gen_expr)

        rval = EXIT_OK
        if attr_match and manifests and not found:
                rval = EXIT_OOPS
                logger.error(_("""\
pkg: contents: no matching actions found in the listed packages"""))

        if manifests and rval == EXIT_OK:
                displayed_results = display_contents_results(actionlist, attrs,
                    sort_attrs, display_headers)

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
                        logger.error("        {0}".format(p))
                api_inst.log_operation_end(result=RESULT_NOTHING_TO_DO)
        else:
                api_inst.log_operation_end(result=RESULT_SUCCEEDED)
        return rval


def display_catalog_failures(cre, ignore_perms_failure=False):
        total = cre.total
        succeeded = cre.succeeded
        partial = 0
        refresh_errstr = ""

        for pub, err in cre.failed:
                if isinstance(err, api_errors.CatalogOriginRefreshException):
                        if len(err.failed) < err.total:
                                partial += 1

                        refresh_errstr += _("\n{0}/{1} repositories for " \
                            "publisher '{2}' could not be reached for " \
                            "catalog refresh.\n").format(
                            len(err.failed), err.total, pub)
                        for o, e in err.failed:
                                refresh_errstr += "\n"
                                refresh_errstr += str(e)

                        refresh_errstr += "\n"
                else:
                        refresh_errstr += "\n   \n" + str(err)


        partial_str = ":"
        if partial:
                partial_str = _(" ({0} partial):").format(str(partial))

        txt = _("pkg: {succeeded}/{total} catalogs successfully "
            "updated{partial}").format(succeeded=succeeded, total=total,
            partial=partial_str)
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
                return succeeded + partial + len(cre.failed)

        logger.error(refresh_errstr)

        if cre.errmessage:
                logger.error(cre.errmessage)

        return succeeded + partial


def display_repo_failures(fail_dict):

        outstr = """

WARNING: Errors were encountered when attempting to retrieve package
catalog information. Packages added to the affected publisher repositories since
the last retrieval may not be available.

"""
        for pub in fail_dict:
                failed = fail_dict[pub]

                if failed is None or not "errors" in failed:
                        # This pub did not have any repo problems, ignore.
                        continue

                assert type(failed) == dict
                total = failed["total"]
                if int(total) == 1:
                        repo_str = _("repository")
                else:
                        repo_str = _("{0} of {1} repositories").format(
                            len(failed["errors"]), total)

                outstr += _("Errors were encountered when attempting to " \
                    "contact {0} for publisher '{1}'.\n").format(repo_str, pub)
                for err in failed["errors"]:
                        outstr += "\n"
                        outstr += str(err)
                outstr += "\n"

        msg(outstr)

def __refresh(api_inst, pubs, full_refresh=False):
        """Private helper method for refreshing publisher data."""

        try:
                # The user explicitly requested this refresh, so set the
                # refresh to occur immediately.
                api_inst.refresh(full_refresh=full_refresh,
                    ignore_unreachable=False, immediate=True, pubs=pubs)
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.PublisherError as e:
                error(e)
                error(_("'pkg publisher' will show a list of publishers."))
                return EXIT_OOPS
        except (api_errors.UnknownErrors, api_errors.PermissionsException) as e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.CatalogRefreshException as e:
                if display_catalog_failures(e) == 0:
                        return EXIT_OOPS
                return EXIT_PARTIAL
        return EXIT_OK

def publisher_refresh(api_inst, args):
        """Update metadata for the image's publishers."""

        # XXX will need to show available content series for each package
        full_refresh = False
        opts, pargs = getopt.getopt(args, "q", ["full"])
        for opt, arg in opts:
                if opt == "-q":
                        global_settings.client_output_quiet = True
                if opt == "--full":
                        full_refresh = True
        # Reset the progress tracker here, because we may have
        # to switch to a different tracker due to the options parse.
        _api_inst.progresstracker = get_tracker()
        # suppress phase information since we're doing just one thing.
        api_inst.progresstracker.set_major_phase(
            api_inst.progresstracker.PHASE_UTILITY)
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
        except api_errors.CatalogRefreshException as e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                txt = _("Could not refresh the catalog for {0}\n").format(
                    pfx)
                for pub, err in e.failed:
                        txt += "   \n{0}".format(err)
                return EXIT_OOPS, txt
        except api_errors.InvalidDepotResponseException as e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                if pfx:
                        return EXIT_OOPS, _("The origin URIs for '{pubname}' "
                            "do not appear to point to a valid pkg repository."
                            "\nPlease verify the repository's location and the "
                            "client's network configuration."
                            "\nAdditional details:\n\n{details}").format(
                            pubname=pfx, details=str(e))
                return EXIT_OOPS, _("The specified URI does not appear to "
                    "point to a valid pkg repository.\nPlease check the URI "
                    "and the client's network configuration."
                    "\nAdditional details:\n\n{0}").format(str(e))
        except api_errors.ImageFormatUpdateNeeded as e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                format_update_error(e)
                return EXIT_OOPS, ""
        except api_errors.ApiException as e:
                for entry in raise_errors:
                        if isinstance(e, entry):
                                raise
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                return EXIT_OOPS, ("\n" + str(e))

def publisher_set(op, api_inst, pargs, ssl_key, ssl_cert, origin_uri,
    reset_uuid, add_mirrors, remove_mirrors, add_origins, remove_origins,
    enable_origins, disable_origins, refresh_allowed, disable, sticky,
    search_before, search_after, search_first, approved_ca_certs,
    revoked_ca_certs, unset_ca_certs, set_props, add_prop_values,
    remove_prop_values, unset_props, repo_uri, proxy_uri):
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
            [--proxy proxy to use]
            [publisher] """

        out_json = client_api._publisher_set(op, api_inst, pargs, ssl_key,
            ssl_cert, origin_uri, reset_uuid, add_mirrors, remove_mirrors,
            add_origins, remove_origins, enable_origins, disable_origins,
            refresh_allowed, disable, sticky, search_before, search_after,
            search_first, approved_ca_certs, revoked_ca_certs, unset_ca_certs,
            set_props, add_prop_values, remove_prop_values, unset_props,
            repo_uri, proxy_uri)

        errors = None
        if "errors" in out_json:
                errors = out_json["errors"]
                errors = _generate_error_messages(out_json["status"], errors,
                    selected_type=["publisher_set"])

        if "data" in out_json:
                if "header" in out_json["data"]:
                        logger.info(out_json["data"]["header"])
                if "added" in out_json["data"]:
                        logger.info(_("  Added publisher(s): {0}").format(
                            ", ".join(out_json["data"]["added"])))
                if "updated" in out_json["data"]:
                        logger.info(_("  Updated publisher(s): {0}").format(
                            ", ".join(out_json["data"]["updated"])))

        if errors:
                _generate_error_messages(out_json["status"], errors,
                    cmd="set-publisher", add_info={"repo_uri": repo_uri})

        return out_json["status"]

def publisher_unset(api_inst, pargs):
        """pkg unset-publisher publisher ..."""

        opts, pargs = getopt.getopt(pargs, "")
        out_json = client_api._publisher_unset("unset-publisher", api_inst,
            pargs)

        if "errors" in out_json:
                _generate_error_messages(out_json["status"],
                    out_json["errors"], cmd="unset-publisher")

        return out_json["status"]

def publisher_list(op, api_inst, pargs, omit_headers, preferred_only,
    inc_disabled, output_format):
        """pkg publishers."""

        ret_json = client_api._publisher_list(op, api_inst, pargs, omit_headers,
            preferred_only, inc_disabled, output_format)
        retcode = ret_json["status"]

        if len(pargs) == 0:
                # Create a formatting string for the default output
                # format.
                if output_format == "default":
                        fmt = "{0:14} {1:12} {2:8} {3:2} {4} {5}"

                # Create a formatting string for the tsv output
                # format.
                if output_format == "tsv":
                        fmt = "{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\t{7}"

                # Output an header if desired.
                if not omit_headers:
                        msg(fmt.format(*ret_json["data"]["headers"]))

                for p in ret_json["data"]["publishers"]:
                        msg(fmt.format(*p))
        else:
                def display_signing_certs(p):
                        if "Approved CAs" in p:
                                msg(_("         Approved CAs:"),
                                    p["Approved CAs"][0])
                                for h in p["Approved CAs"][1:]:
                                        msg(_("                     :"), h)
                        if "Revoked CAs" in p:
                                msg(_("          Revoked CAs:"),
                                    p["Revoked CAs"][0])
                                for h in p["Revoked CAs"][1:]:
                                        msg(_("                     :"), h)

                def display_ssl_info(uri_data):
                        msg(_("              SSL Key:"), uri_data["SSL Key"])
                        msg(_("             SSL Cert:"), uri_data["SSL Cert"])

                        if "errors" in ret_json:
                                for e in ret_json["errors"]:
                                        if "errtype" in e and \
                                            e["errtype"] == "cert_info":
                                                emsg(e["reason"])

                        if "Cert. Effective Date" in uri_data:
                                msg(_(" Cert. Effective Date:"),
                                    uri_data["Cert. Effective Date"])
                                msg(_("Cert. Expiration Date:"),
                                    uri_data["Cert. Expiration Date"])

                if "data" not in ret_json or "publisher_details" not in \
                    ret_json["data"]:
                        return retcode

                for pub in ret_json["data"]["publisher_details"]:
                        msg("")
                        msg(_("            Publisher:"), pub["Publisher"])
                        msg(_("                Alias:"), pub["Alias"])

                        if "origins" in pub:
                                for od in pub["origins"]:
                                        msg(_("           Origin URI:"),
                                            od["Origin URI"])
                                        if "Proxy" in od:
                                                msg(_("                Proxy:"),
                                                    ", ".join(od["Proxy"]))
                                        display_ssl_info(od)

                        if "mirrors" in pub:
                                for md in pub["mirrors"]:
                                        msg(_("           Mirror URI:"),
                                            md["Mirror URI"])
                                        if "Proxy" in md:
                                                msg(_("                Proxy:"),
                                                    ", ".join(md["Proxy"]))
                                        display_ssl_info(md)

                        msg(_("          Client UUID:"),
                            pub["Client UUID"])
                        msg(_("      Catalog Updated:"),
                            pub["Catalog Updated"])
                        display_signing_certs(pub)
                        msg(_("              Enabled:"),
                            _(pub["enabled"]))

                        if "Properties" not in pub:
                                continue
                        pub_items = sorted(
                            six.iteritems(pub["Properties"]))
                        property_padding = "                      "
                        properties_displayed = False
                        for k, v in pub_items:
                                if not v:
                                        continue
                                if not properties_displayed:
                                        msg(_("           Properties:"))
                                        properties_displayed = True
                                if not isinstance(v, six.string_types):
                                        v = ", ".join(sorted(v))
                                msg(property_padding, k + " =", str(v))
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
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException as e:
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
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException as e:
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
                        usage(_("Signature-policy {0} doesn't allow additional "
                            "parameters.").format(policy), cmd=subcommand)
                elif policy == "require-names":
                        props["signature-required-names"] = params

        # XXX image property management should be in pkg.client.api
        try:
                img.set_properties(props)
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.ApiException as e:
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
                except api_errors.ImageFormatUpdateNeeded as e:
                        format_update_error(e)
                        return EXIT_OOPS
                except api_errors.ApiException as e:
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
                        error(_("no such property: {0}").format(p),
                            cmd=subcommand)
                        return EXIT_OOPS

        if not pargs:
                # If specific properties were named, list them in the order
                # requested; otherwise, list them sorted.
                pargs = sorted(list(img.properties()))

        width = max(max([len(p) for p in pargs]), 8)
        fmt = "{{0:{0}}} {{1}}".format(width)
        if not omit_headers:
                msg(fmt.format("PROPERTY", "VALUE"))

        for p in pargs:
                msg(fmt.format(p, img.get_property(p)))

        return EXIT_OK

def list_variant(op, api_inst, pargs, omit_headers, output_format,
    list_all_items, list_installed, verbose):
        """pkg variant [-Haiv] [-F format] [<variant_pattern> ...]"""

        subcommand = "variant"
        if output_format is None:
                output_format = "default"

        # To work around Python 2.x's scoping limits, a list is used.
        found = [False]
        req_variants = set(pargs)

        # If user explicitly provides variants, display implicit value even if
        # not explicitly set in the image or found in a package.
        implicit = req_variants and True or False

        def gen_current():
                for (name, val, pvals) in api_inst.gen_variants(variant_list,
                    implicit=implicit, patterns=req_variants):
                        if output_format == "default":
                                name_list = name.split(".")[1:]
                                name = ".".join(name_list)
                        found[0] = True
                        yield {
                            "variant": name,
                            "value": val
                        }

        def gen_possible():
                for (name, val, pvals) in api_inst.gen_variants(variant_list,
                    implicit=implicit, patterns=req_variants):
                        if output_format == "default":
                                name_list = name.split(".")[1:]
                                name = ".".join(name_list)
                        found[0] = True
                        for pval in pvals:
                                yield {
                                    "variant": name,
                                    "value": pval
                                }

        if verbose:
                gen_listing = gen_possible
        else:
                gen_listing = gen_current

        if list_all_items:
                if verbose:
                        variant_list = api_inst.VARIANT_ALL_POSSIBLE
                else:
                        variant_list = api_inst.VARIANT_ALL
        elif list_installed:
                if verbose:
                        variant_list = api_inst.VARIANT_INSTALLED_POSSIBLE
                else:
                        variant_list = api_inst.VARIANT_INSTALLED
        else:
                if verbose:
                        variant_list = api_inst.VARIANT_IMAGE_POSSIBLE
                else:
                        variant_list = api_inst.VARIANT_IMAGE

        #    VARIANT VALUE
        #    <variant> <value>
        #    <variant_2> <value_2>
        #    ...
        field_data = {
            "variant" : [("default", "json", "tsv"), _("VARIANT"), ""],
            "value" : [("default", "json", "tsv"), _("VALUE"), ""],
        }
        desired_field_order = (_("VARIANT"), _("VALUE"))

        # Default output formatting.
        def_fmt = "{0:70} {1}"

        # print without trailing newline.
        sys.stdout.write(misc.get_listing(desired_field_order,
            field_data, gen_listing(), output_format, def_fmt,
            omit_headers))

        if not found[0] and req_variants:
                if output_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching variants found"),
                            cmd=subcommand)
                return EXIT_OOPS

        # Successful if no variants exist or if at least one matched.
        return EXIT_OK

def list_facet(op, api_inst, pargs, omit_headers, output_format, list_all_items,
    list_masked, list_installed):
        """pkg facet [-Hai] [-F format] [<facet_pattern> ...]"""

        subcommand = "facet"
        if output_format is None:
                output_format = "default"

        # To work around Python 2.x's scoping limits, a list is used.
        found = [False]
        req_facets = set(pargs)

        facet_list = api_inst.FACET_IMAGE
        if list_all_items:
                facet_list = api_inst.FACET_ALL
        elif list_installed:
                facet_list = api_inst.FACET_INSTALLED

        # If user explicitly provides facets, display implicit value even if
        # not explicitly set in the image or found in a package.
        implicit = req_facets and True or False

        def gen_listing():
                for (name, val, src, masked) in \
                    api_inst.gen_facets(facet_list, implicit=implicit,
                        patterns=req_facets):
                        if output_format == "default":
                                name_list = name.split(".")[1:]
                                name = ".".join(name_list)
                        found[0] = True

                        if not list_masked and masked:
                                continue

                        # "value" and "masked" are intentionally not _().
                        yield {
                            "facet": name,
                            "value": val and "True" or "False",
                            "src": src,
                            "masked": masked and "True" or "False",
                        }

        #    FACET VALUE
        #    <facet> <value> <src>
        #    <facet_2> <value_2> <src2>
        #    ...
        field_data = {
            "facet"  : [("default", "json", "tsv"), _("FACET"), ""],
            "value"  : [("default", "json", "tsv"), _("VALUE"), ""],
            "src"    : [("default", "json", "tsv"), _("SRC"), ""],
        }
        desired_field_order = (_("FACET"), _("VALUE"), _("SRC"))
        def_fmt = "{0:64} {1:5} {2}"

        if list_masked:
                # if we're displaying masked facets, we should also mark which
                # facets are masked in the output.
                field_data["masked"] = \
                    [("default", "json", "tsv"), _("MASKED"), ""]
                desired_field_order += (_("MASKED"),)
                def_fmt = "{0:57} {1:5} {2:6} {3}"

        # print without trailing newline.
        sys.stdout.write(misc.get_listing(desired_field_order,
            field_data, gen_listing(), output_format, def_fmt,
            omit_headers))

        if not found[0] and req_facets:
                if output_format == "default":
                        # Don't pollute other output formats.
                        error(_("no matching facets found"),
                            cmd=subcommand)
                return EXIT_OOPS

        # Successful if no facets exist or if at least one matched.
        return EXIT_OK

def list_linked(op, api_inst, pargs,
    li_ignore, omit_headers):
        """pkg list-linked [-H]

        List all the linked images known to the current image."""

        api_inst.progresstracker.set_purpose(
            api_inst.progresstracker.PURPOSE_LISTING)

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
                fmt += "{{{0}!s:{1}}}".format(col, width)

        if not omit_headers:
                msg(fmt.format(*li_header))
        for row in li_list:
                msg(fmt.format(*row))
        return EXIT_OK

def pubcheck_linked(op, api_inst, pargs):
        """If we're a child image, verify that the parent image
        publisher configuration is a subset of our publisher configuration.
        If we have any children, recurse into them and perform a publisher
        check."""

        try:
                api_inst.linked_publisher_check()
        except api_errors.ImageLockedError as e:
                error(e)
                return EXIT_LOCKED

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
                        usage(_("invalid linked image property: "
                            "'{0}'.").format(p), cmd=op)

                if p in linked_props:
                        usage(_("linked image property specified multiple "
                            "times: '{0}'.").format(p), cmd=op)

                linked_props[p] = v

        return linked_props

def list_property_linked(op, api_inst, pargs,
    li_name, omit_headers):
        """pkg property-linked [-H] [-l <li-name>] [propname ...]

        List the linked image properties associated with a child or parent
        image."""

        api_inst.progresstracker.set_purpose(
            api_inst.progresstracker.PURPOSE_LISTING)

        lin = None
        if li_name:
                lin = api_inst.parse_linked_name(li_name)
        props = api_inst.get_linked_props(lin=lin)

        for p in pargs:
                if p not in props.keys():
                        error(_("{op}: no such property: {p}").format(
                            op=op, p=p))
                        return EXIT_OOPS

        if len(props) == 0:
                return EXIT_OK

        if not pargs:
                pargs = props.keys()

        width = max(max([len(p) for p in pargs if props[p]]), 8)
        fmt = "{{0:{0}}}\t{{1}}".format(width)
        if not omit_headers:
                msg(fmt.format("PROPERTY", "VALUE"))
        for p in sorted(pargs):
                if not props[p]:
                        continue
                msg(fmt.format(p, props[p]))

        return EXIT_OK

def set_property_linked(op, api_inst, pargs,
    accept, backup_be, backup_be_name, be_activate, be_name, li_ignore,
    li_md_only, li_name, li_parent_sync, li_pkg_updates, new_be, noexecute,
    origins, parsable_version, quiet, refresh_catalogs, reject_pats,
    show_licenses, update_index, verbose):
        """pkg set-property-linked
            [-nvq] [--accept] [--licenses] [--no-index] [--no-refresh]
            [--no-parent-sync] [--no-pkg-updates]
            [--linked-md-only] <propname>=<propvalue> ...

        Change the specified linked image properties.  This may result in
        updating the package contents of a child image."""

        api_inst.progresstracker.set_purpose(
            api_inst.progresstracker.PURPOSE_LISTING)

        # make sure we're a child image
        if li_name:
                lin = api_inst.parse_linked_name(li_name)
        else:
                lin = api_inst.get_linked_name()

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        return EXIT_OK

def audit_linked(op, api_inst, pargs,
    li_parent_sync,
    li_target_all,
    li_target_list,
    omit_headers,
    quiet):
        """pkg audit-linked [-a|-l <li-name>]

        Audit one or more child images to see if they are in sync
        with their parent image."""

        api_inst.progresstracker.set_purpose(
            api_inst.progresstracker.PURPOSE_LISTING)

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
        fmt = "{{0!s:{0}}}\t{{1}}".format(width)
        if not omit_headers:
                msg(fmt.format("NAME", "STATUS"))

        if not quiet:
                for k, (rv, err, p_dict) in rvdict.items():
                        if rv == EXIT_OK:
                                msg(fmt.format(k, _("synced")))
                        elif rv == EXIT_DIVERGED:
                                msg(fmt.format(k, _("diverged")))

        rv, err, p_dicts = api_inst.audit_linked_rvdict2rv(rvdict)
        if err:
                error(err, cmd=op)
        return rv

def sync_linked(op, api_inst, pargs, accept, backup_be, backup_be_name,
    be_activate, be_name, li_ignore, li_md_only, li_parent_sync,
    li_pkg_updates, li_target_all, li_target_list, new_be, noexecute, origins,
    parsable_version, quiet, refresh_catalogs, reject_pats, show_licenses,
    stage, update_index, verbose):
        """pkg sync-linked [-a|-l <li-name>]
            [-nvq] [--accept] [--licenses] [--no-index] [--no-refresh]
            [--no-parent-sync] [--no-pkg-updates]
            [--linked-md-only] [-a|-l <name>]

        Sync one or more child images with their parent image."""

        xrval, xres = get_fmri_args(api_inst, reject_pats, cmd=op)
        if not xrval:
                return EXIT_OOPS

        if not li_target_all and not li_target_list:
                # sync the current image
                return __api_op(op, api_inst, _accept=accept,
                    _li_ignore=li_ignore, _noexecute=noexecute,
                    _origins=origins, _parsable_version=parsable_version,
                    _quiet=quiet, _show_licenses=show_licenses, _stage=stage,
                    _verbose=verbose, backup_be=backup_be,
                    backup_be_name=backup_be_name, be_activate=be_activate,
                    be_name=be_name, li_md_only=li_md_only,
                    li_parent_sync=li_parent_sync,
                    li_pkg_updates=li_pkg_updates, new_be=new_be,
                    refresh_catalogs=refresh_catalogs,
                    reject_list=reject_pats,
                    update_index=update_index)

        # sync the requested child image(s)
        api_inst.progresstracker.set_major_phase(
            api_inst.progresstracker.PHASE_UTILITY)
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
                except api_errors.ApiException as e:
                        error(e, cmd=op)
                        return EXIT_OOPS
        return rv

def attach_linked(op, api_inst, pargs,
    accept, allow_relink, attach_child, attach_parent, be_activate,
    backup_be, backup_be_name, be_name, force, li_ignore, li_md_only,
    li_parent_sync, li_pkg_updates, li_props, new_be, noexecute, origins,
    parsable_version, quiet, refresh_catalogs, reject_pats, show_licenses,
    update_index, verbose):
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

        for k, v in li_props:
                if k in [li.PROP_PATH, li.PROP_NAME, li.PROP_MODEL]:
                        usage(_("cannot specify linked image property: "
                            "'{0}'").format(k), cmd=op)

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
                    backup_be=backup_be, backup_be_name=backup_be_name,
                    be_activate=be_activate, be_name=be_name, force=force,
                    li_md_only=li_md_only, li_path=li_path,
                    li_pkg_updates=li_pkg_updates, li_props=li_props,
                    lin=lin, new_be=new_be, refresh_catalogs=refresh_catalogs,
                    reject_list=reject_pats, update_index=update_index)

        # attach the requested child image
        api_inst.progresstracker.set_major_phase(
            api_inst.progresstracker.PHASE_UTILITY)
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
                except api_errors.ApiException as e:
                        error(e, cmd=op)
                        return EXIT_OOPS
        return rv

def detach_linked(op, api_inst, pargs, force, li_md_only, li_pkg_updates,
    li_target_all, li_target_list, noexecute, quiet, verbose):
        """pkg detach-linked
            [-fnvq] [-a|-l <li-name>] [--linked-md-only]

        Detach one or more child linked images."""

        if not li_target_all and not li_target_list:
                # detach the current image
                return __api_op(op, api_inst, _noexecute=noexecute,
                    _quiet=quiet, _verbose=verbose, force=force,
                    li_md_only=li_md_only, li_pkg_updates=li_pkg_updates)

        api_inst.progresstracker.set_major_phase(
            api_inst.progresstracker.PHASE_UTILITY)
        rvdict = api_inst.detach_linked_children(li_target_list, force=force,
            li_md_only=li_md_only, li_pkg_updates=li_pkg_updates,
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

        opts, pargs = getopt.getopt(args, "fFPUzg:m:p:k:c:",
            ["force", "full", "partial", "user", "zone", "facet=", "mirror=",
                "origin=", "publisher=", "no-refresh", "variant=",
                "set-property="])

        for opt, arg in opts:
                if opt in ("-p", "--publisher"):
                        if pub_url:
                                usage(_("The -p option can be specified only "
                                    "once."), cmd=cmd_name)
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
                                f_name = "facet.{0}".format(f_name)
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
                                    "given: {0}").format(arg), cmd=cmd_name)
                        if t[0] in set_props:
                                usage(_("a property may only be set once in a "
                                    "command. {0} was set twice").format(t[0]),
                                    cmd=cmd_name)
                        set_props[t[0]] = t[1]
                elif opt == "--variant":
                        try:
                                v_name, v_value = arg.split("=", 1)
                                if not v_name.startswith("variant."):
                                        v_name = "variant.{0}".format(v_name)
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

        if pub_url and not pub_name and not refresh_allowed:
                usage(_("--no-refresh cannot be used with -p unless a "
                    "publisher prefix is provided."), cmd=cmd_name)

        if not pub_url and (add_origins or add_mirrors):
                usage(_("A publisher must be specified if -g or -m are used."),
                    cmd=cmd_name)

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

        progtrack = get_tracker()
        progtrack.set_major_phase(progtrack.PHASE_UTILITY)
        global _api_inst
        global img
        try:
                _api_inst = api.image_create(PKG_CLIENT_NAME, CLIENT_API_VERSION,
                    image_dir, imgtype, is_zone, facets=facets, force=force,
                    mirrors=list(add_mirrors), origins=list(add_origins),
                    prefix=pub_name, progtrack=progtrack,
                    refresh_allowed=refresh_allowed, ssl_cert=ssl_cert,
                    ssl_key=ssl_key, repo_uri=repo_uri, variants=variants,
                    props=set_props)
                img = _api_inst.img
        except api_errors.InvalidDepotResponseException as e:
                # Ensure messages are displayed after the spinner.
                logger.error("\n")
                error(_("The URI '{pub_url}' does not appear to point to a "
                    "valid pkg repository.\nPlease check the repository's "
                    "location and the client's network configuration."
                    "\nAdditional details:\n\n{error}").format(
                    pub_url=pub_url, error=e),
                    cmd=cmd_name)
                print_proxy_config()
                return EXIT_OOPS
        except api_errors.CatalogRefreshException as cre:
                # Ensure messages are displayed after the spinner.
                error("", cmd=cmd_name)
                if display_catalog_failures(cre) == 0:
                        return EXIT_OOPS
                else:
                        return EXIT_PARTIAL
        except api_errors.ApiException as e:
                error(str(e), cmd=cmd_name)
                return EXIT_OOPS
        finally:
                # Normally this would get flushed by handle_errors
                # but that won't happen if the above code throws, because
                # _api_inst will be None.
                progtrack.flush()

        return EXIT_OK

def rebuild_index(api_inst, pargs):
        """pkg rebuild-index

        Forcibly rebuild the search indexes. Will remove existing indexes
        and build new ones from scratch."""

        if pargs:
                usage(_("command does not take operands ('{0}')").format(
                    " ".join(pargs)), cmd="rebuild-index")

        try:
                api_inst.rebuild_search_index()
        except api_errors.ImageFormatUpdateNeeded as e:
                format_update_error(e)
                return EXIT_OOPS
        except api_errors.CorruptedIndexException:
                error("The search index appears corrupted.  Please rebuild the "
                    "index with 'pkg rebuild-index'.", cmd="rebuild-index")
                return EXIT_OOPS
        except api_errors.ProblematicPermissionsIndexException as e:
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
        # we compute 'reason', 'time' and 'release_note' columns ourselves
        history_cols = {
            "be": (_("BE"), "20", "operation_be"),
            "be_uuid": (_("BE UUID"), "41", "operation_be_uuid"),
            "client": (_("CLIENT"), "19", "client_name"),
            "client_ver": (_("VERSION"), "15", "client_version"),
            "command": (_("COMMAND"), "", "client_args"),
            "finish": (_("FINISH"), "25", "operation_end_time"),
            "id": (_("ID"), "10", "operation_userid"),
            "new_be": (_("NEW BE"), "20", "operation_new_be"),
            "new_be_uuid": (_("NEW BE UUID"), "41", "operation_new_be_uuid"),
            "operation": (_("OPERATION"), "25", "operation_name"),
            "outcome": (_("OUTCOME"), "12", "operation_result"),
            "reason": (_("REASON"), "10", None),
            "release_notes": (_("RELEASE NOTES"), "12", None),
            "snapshot": (_("SNAPSHOT"), "20", "operation_snapshot"),
            "start": (_("START"), "25", "operation_start_time"),
            "time": (_("TIME"), "10", None),
            "user": (_("USER"), "10", "operation_username"),
            # omitting start state, end state, errors for now
            # as these don't nicely fit into columns
        }

        omit_headers = False
        long_format = False
        column_format = False
        show_notes = False
        display_limit = None    # Infinite
        time_vals = [] # list of timestamps for which we want history events
        columns = ["start", "operation", "client", "outcome"]

        opts, pargs = getopt.getopt(args, "HNln:o:t:")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                elif opt == "-N":
                        show_notes = True
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
                                            _("The '{0}' column must be the "
                                            "last item in the -o list").format(
                                            col))
                                        return EXIT_BADOPT

                        for col in columns:
                                if col not in history_cols:
                                        logger.error(
                                            _("Unknown output column "
                                            "'{0}'").format(col))
                                        return EXIT_BADOPT
                        if not __unique_columns(columns):
                                return EXIT_BADOPT

                elif opt == "-t":
                        time_vals.extend(arg.split(","))

        if omit_headers and long_format:
                usage(_("-H and -l may not be combined"), cmd="history")

        if column_format and long_format:
                usage(_("-o and -l may not be combined"), cmd="history")

        if time_vals and display_limit:
                usage(_("-n and -t may not be combined"), cmd="history")

        if column_format and show_notes:
                usage(_("-o and -N may not be combined"), cmd="history")

        if long_format and show_notes:
                usage(_("-l and -N may not be combined"), cmd="history")

        history_fmt = None

        if not long_format and not show_notes:
                headers = []
                # build our format string
                for i, col in enumerate(columns):
                        # no need for trailing space for our last column
                        if columns.index(col) == len(columns) - 1:
                                fmt = ""
                        else:
                                fmt = history_cols[col][1]
                        if history_fmt:
                                history_fmt += "{{{0:d}!s:{1}}}".format(i, fmt)
                        else:
                                history_fmt = "{{0!s:{0}}}".format(fmt)
                        headers.append(history_cols[col][0])
                if not omit_headers:
                        msg(history_fmt.format(*headers))

        def gen_entries():
                """Error handler for history generation; avoids need to indent
                and clobber formatting of logic below."""
                try:
                        for he in api_inst.gen_history(limit=display_limit,
                            times=time_vals):
                                yield he
                except api_errors.HistoryException as e:
                        error(str(e), cmd="history")
                        sys.exit(EXIT_OOPS)

        if show_notes:
                for he in gen_entries():
                        start_time = misc.timestamp_to_time(
                            he.operation_start_time)
                        start_time = datetime.datetime.fromtimestamp(
                            start_time).isoformat()
                        if he.operation_release_notes:
                                msg(_("{0}: Release notes:").format(start_time))
                                for a in he.notes:
                                        msg("    {0}".format(a))
                        else:
                                msg(_("{0}: Release notes: None").format(
                                    start_time))

                return EXIT_OK

        for he in gen_entries():
                # populate a dictionary containing our output
                output = {}
                for col in history_cols:
                        if not history_cols[col][2]:
                                continue
                        output[col] = getattr(he, history_cols[col][2], None)

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
                        output["finish"] = \
                            _("{0} (clock drift detected)").format(
                            output["finish"])

                output["time"] = dt_end - dt_start
                # We can't use timedelta's str() method, since when
                # output["time"].days > 0, it prints eg. "4 days, 3:12:54"
                # breaking our field separation, so we need to do this by hand.
                total_time = output["time"]
                secs = total_time.seconds
                add_hrs = total_time.days * 24
                mins, secs = divmod(secs, 60)
                hrs, mins = divmod(mins, 60)
                output["time"] = "{0}:{1:02d}:{2:02d}".format(
                    add_hrs + hrs, mins, secs)

                output["command"] = " ".join(he.client_args)

                # Where we weren't able to lookup the current name, add a '*' to
                # the entry, indicating the boot environment is no longer
                # present.
                if he.operation_be and he.operation_current_be:
                        output["be"] = he.operation_current_be
                elif he.operation_be_uuid:
                        output["be"] = "{0}*".format(he.operation_be)
                else:
                        output["be"] = he.operation_be

                if he.operation_new_be and he.operation_current_new_be:
                        output["new_be"] = he.operation_current_new_be
                elif he.operation_new_be_uuid:
                        output["new_be"] = "{0}*".format(he.operation_new_be)
                else:
                        output["new_be"] = "{0}".format(he.operation_new_be)

                if he.operation_release_notes:
                        output["release_notes"] = _("Yes")
                else:
                        output["release_notes"] = _("No")

                outcome, reason = he.operation_result_text
                output["outcome"] = outcome
                output["reason"] = reason
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

                enc = locale.getlocale(locale.LC_CTYPE)[1]
                if not enc:
                        enc = locale.getpreferredencoding()

                if long_format:
                        data = __get_long_history_data(he, output)
                        for field, value in data:
                                field = misc.force_str(field, encoding=enc)
                                value = misc.force_str(value, encoding=enc)
                                msg("{0!s:>18}: {1!s}".format(field, value))

                        # Separate log entries with a blank line.
                        msg("")
                else:
                        items = []
                        for col in columns:
                                item = output[col]
                                item = misc.force_str(item, encoding=enc)
                                items.append(item)
                        msg(history_fmt.format(*items))
        return EXIT_OK

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
                logger.error(_("Duplicate column specified: {0}").format(col))
        return not dup_cols

def __get_long_history_data(he, hist_info):
        """Return an array of tuples containing long_format history info"""
        data = []
        data.append((_("Operation"), hist_info["operation"]))

        data.append((_("Outcome"), hist_info["outcome"]))
        data.append((_("Reason"), hist_info["reason"]))
        data.append((_("Client"), hist_info["client"]))
        data.append((_("Version"), hist_info["client_ver"]))

        data.append((_("User"), "{0} ({1})".format(hist_info["user"],
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
        data.append((_("Release Notes"), hist_info["release_notes"]))

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
        api_inst.purge_history()
        msg(_("History purged."))

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
                logger.error(_("http_proxy: {0}\n").format(http_proxy))
        if https_proxy:
                logger.error(_("https_proxy: {0}\n").format(https_proxy))

def update_format(api_inst, pargs):
        """Update image to newest format."""

        try:
                res = api_inst.update_format()
        except api_errors.ApiException as e:
                error(str(e), cmd="update-format")
                return EXIT_OOPS

        if res:
                logger.info(_("Image format updated."))
                return EXIT_OK

        logger.info(_("Image format already current."))
        return EXIT_NOP

def print_version(pargs):
        if pargs:
                usage(_("version: command does not take operands "
                    "('{0}')").format(" ".join(pargs)), cmd="version")
        msg(pkg.VERSION)
        return EXIT_OK

# To allow exception handler access to the image.
_api_inst = None
pargs = None
img = None
orig_cwd = None

#
# Mapping of the internal option name to short and long CLI options.
#
# {option_name: (short, long)}
#
#

opts_mapping = {
    "backup_be_name" :    ("",  "backup-be-name"),
    "be_name" :           ("",  "be-name"),
    "deny_new_be" :       ("",  "deny-new-be"),
    "no_backup_be" :      ("",  "no-backup-be"),
    "be_activate" :       ("",  "no-be-activate"),
    "require_backup_be" : ("",  "require-backup-be"),
    "require_new_be" :    ("",  "require-new-be"),

    "concurrency" :       ("C", "concurrency"),

    "force" :             ("f", ""),

    "ignore_missing" :    ("", "ignore-missing"),

    "li_ignore_all" :     ("I", ""),
    "li_ignore_list" :    ("i", ""),
    "li_md_only" :        ("",  "linked-md-only"),

    "li_pkg_updates" :    ("",  "no-pkg-updates"),

    "li_parent_sync" :    ("",  "no-parent-sync"),

    "li_props" :          ("",  "prop-linked"),

    "li_target_all" :     ("a", ""),
    "li_target_list" :    ("l", ""),

    "li_name" :           ("l", ""),

    # These options are used for explicit recursion into linked children.
    # li_erecurse_all enables explicit recursion into all children if neither
    # li_erecurse_list nor li_erecurse_excl is set. If any children are
    # specified in li_erecurse_list, only recurse into those. If any children
    # are specified in li_erecurse_excl, recurse into all children except for
    # those.
    # Explicit recursion means we run the same operation in the child as we run
    # in the parent. Children we do not explicitely recurse into are still
    # getting synced.
    "li_erecurse_all" :    ("r", "recurse"),
    "li_erecurse_list" :   ("z", ""),
    "li_erecurse_excl" :   ("Z", ""),

    "accept" :            ("",  "accept"),
    "show_licenses" :     ("",  "licenses"),

    "omit_headers" :      ("H",  ""),

    "update_index" :      ("",  "no-index"),

    "unpackaged" :        ("",  "unpackaged"),

    "unpackaged_only" :        ("",  "unpackaged-only"),

    "refresh_catalogs" :  ("",  "no-refresh"),

    "reject_pats" :       ("",  "reject"),

    "verbose" :           ("v",  ""),

    "quiet" :             ("q",  ""),

    "parsable_version" :  ("",  "parsable"),

    "noexecute" :         ("n",  ""),

    "origins" :           ("g",  ""),

    "stage" :             ("",  "stage"),

    "allow_relink" :      ("",  "allow-relink"),
    "attach_child" :      ("c",  ""),
    "attach_parent" :     ("p",  ""),

    "list_available" :    ("a",  ""),
    "list_masked" :       ("m",  ""),
    "list_all_items" :    ("a",  ""),
    "output_format" :     ("F",  "output-format"),

    "tagged" :            ("",  "tagged"),

    "publishers" :        ("p", ""),

    # These options are used in set-mediator and unset-mediator but
    # the long options are only valid in set_mediator (as per the previous
    # implementation). However, the long options are not documented in the
    # manpage for set-mediator either, so I think we're good.
    "med_implementation" : ("I",  "implementation"),
    "med_version" :        ("V",  "version"),

    "list_installed_newest" : ("a",  ""),
    "list_all" :              ("f",  ""),
    "list_newest" :           ("n",  ""),
    "summary" :               ("s",  ""),
    "list_upgradable" :       ("u",  ""),

    "ctlfd" :                 ("",  "ctlfd"),
    "progfd" :                ("",  "progfd"),

    "list_installed" :        ("i",  ""),

    "sync_act" :              ("",  "sync-actuators"),
    "act_timeout" :           ("",  "sync-actuators-timeout"),

    "ssl_key":                ("k", ""),
    "ssl_cert":               ("c", ""),
    "approved_ca_certs":      ("", "approve-ca-cert"),
    "revoked_ca_certs":       ("", "revoke-ca-cert"),
    "unset_ca_certs":         ("", "unset-ca-cert"),
    "origin_uri":             ("O", ""),
    "reset_uuid":             ("", "reset-uuid"),
    "add_mirrors":            ("m", "add-mirror"),
    "remove_mirrors":         ("M", "remove-mirror"),
    "add_origins":            ("g", "add-origin"),
    "remove_origins":         ("G", "remove-origin"),
    "enable_origins":         ("", "enable-origins"),
    "disable_origins":        ("", "disable-origins"),
    "refresh_allowed":        ("", "no-refresh"),
    "enable":                 ("e", "enable"),
    "disable":                ("d", "disable"),
    "sticky":                 ("", "sticky"),
    "non_sticky":             ("", "non-sticky"),
    "repo_uri":               ("p", ""),
    "proxy_uri":              ("", "proxy"),
    "search_before":          ("", "search-before"),
    "search_after":           ("", "search-after"),
    "search_first":           ("P", "search-first"),
    "set_props":              ("", "set-property"),
    "add_prop_values":        ("", "add-property-value"),
    "remove_prop_values":     ("", "remove-property-value"),
    "unset_props":            ("", "unset-property"),
    "preferred_only":         ("P", ""),
    "inc_disabled":           ("n", ""),
    "info_local":             ("l", ""),
    "info_remote":            ("r", ""),
    "display_license":        ("", "license"),
    "publisher_a":            ("a", ""),
    "verify_paths":           ("p", "")
}

#
# cmds dictionary is used to dispatch subcommands.  The format of this
# dictionary is:
#
#       "subcommand-name" : subcommand-cb
#
#       subcommand-cb: the callback function invoked for this subcommand
#
# placeholders in this lookup table for image-create, help and version
# which don't have dedicated methods
#
cmds = {
    "add-property-value"    : [property_add_value],
    "attach-linked"         : [attach_linked, 2],
    "avoid"                 : [avoid],
    "audit-linked"          : [audit_linked, 0],
    "change-facet"          : [change_facet],
    "change-variant"        : [change_variant],
    "contents"              : [list_contents],
    "detach-linked"         : [detach_linked, 0],
    "dehydrate"             : [dehydrate],
    "exact-install"         : [exact_install],
    "facet"                 : [list_facet],
    "fix"                   : [fix],
    "freeze"                : [freeze],
    "help"                  : [None],
    "history"               : [history_list],
    "image-create"          : [None],
    "info"                  : [info],
    "install"               : [install],
    "list"                  : [list_inventory],
    "list-linked"           : [list_linked, 0],
    "mediator"              : [list_mediators],
    "property"              : [property_list],
    "property-linked"       : [list_property_linked],
    "pubcheck-linked"       : [pubcheck_linked, 0],
    "publisher"             : [publisher_list],
    "purge-history"         : [history_purge],
    "rebuild-index"         : [rebuild_index],
    "refresh"               : [publisher_refresh],
    "rehydrate"             : [rehydrate],
    "remote"                : [remote, 0],
    "remove-property-value" : [property_remove_value],
    "revert"                : [revert],
    "search"                : [search],
    "set-mediator"          : [set_mediator],
    "set-property"          : [property_set],
    "set-property-linked"   : [set_property_linked],
    "set-publisher"         : [publisher_set],
    "sync-linked"           : [sync_linked, 0],
    "unavoid"               : [unavoid],
    "unfreeze"              : [unfreeze],
    "uninstall"             : [uninstall],
    "unset-property"        : [property_unset],
    "unset-mediator"        : [unset_mediator],
    "unset-publisher"       : [publisher_unset],
    "update"                : [update],
    "update-format"         : [update_format],
    "variant"               : [list_variant],
    "verify"                : [verify],
    "version"               : [None],
}

# Option value dictionary which pre-defines the valid values for
# some options.
valid_opt_values = {
    "output_format":        ["default", "tsv", "json", "json-formatted"]
}

# These tables are an addendum to the the pkg_op_opts/opts_* lists in
# modules/client/options.py. They contain all the options for functions which
# are not represented in options.py but go through common option processing.
# This list should get shortened and eventually removed by moving more/all
# functions out of client.py.

def opts_cb_remote(api_inst, opts, opts_new):
        options.opts_cb_fd("ctlfd", api_inst, opts, opts_new)
        options.opts_cb_fd("progfd", api_inst, opts, opts_new)

        # move progfd from opts_new into a global
        global_settings.client_output_progfd = opts_new["progfd"]
        del opts_new["progfd"]

opts_remote = [
    opts_cb_remote,
    ("ctlfd",                None),
    ("progfd",               None),
]

def opts_cb_varcet(api_inst, opts, opts_new):
        if opts_new["list_all_items"] and opts_new["list_installed"]:
                raise api_errors.InvalidOptionError(
                    api_errors.InvalidOptionError.INCOMPAT,
                    ["list_all_items", "list_installed"])

opts_list_varcet = \
    options.opts_table_no_headers + \
    [
    opts_cb_varcet,
    ("list_all_items",          False),
    ("list_installed",          False),
    ("output_format",           None, valid_opt_values["output_format"])
]

opts_list_facet = \
    opts_list_varcet + \
    [
    ("list_masked",             False),
]

opts_list_variant = \
    opts_list_varcet + \
    [
    ("verbose",      False)
]

opts_list_mediator = \
    options.opts_table_no_headers + \
    [
    ("list_available",      False),
    ("output_format",       None,  valid_opt_values["output_format"])
]
opts_unset_mediator = \
    options.opts_table_beopts + \
    options.opts_table_no_index + \
    options.opts_table_nqv + \
    options.opts_table_parsable + \
    [
    ("med_implementation",   False),
    ("med_version",          False)
]

cmd_opts = {
    "facet"             : opts_list_facet,
    "mediator"          : opts_list_mediator,
    "unset-mediator"    : opts_unset_mediator,
    "remote"            : opts_remote,
    "variant"           : opts_list_variant,
}


def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        global _api_inst
        global img
        global orig_cwd
        global pargs

        try:
                orig_cwd = os.getcwd()
        except OSError as e:
                try:
                        orig_cwd = os.environ["PWD"]
                        if not orig_cwd or orig_cwd[0] != "/":
                                orig_cwd = None
                except KeyError:
                        orig_cwd = None

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "R:D:?",
                    ["debug=", "help", "runid=", "no-network-cache"])
        except getopt.GetoptError as e:
                usage(_("illegal global option -- {0}").format(e.opt))

        runid = None
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
                                        usage(_("{opt} takes argument of form "
                                            "name=value, not {arg}").format(
                                            opt=opt, arg=arg))
                        DebugValues.set_value(key, value)
                elif opt == "-R":
                        mydir = arg
                elif opt == "--runid":
                        runid = arg
                elif opt in ("--help", "-?"):
                        show_usage = True
                elif opt == "--no-network-cache":
                        global_settings.client_no_network_cache = True

        # The globals in pkg.digest can be influenced by debug flags
        if DebugValues:
                reload(pkg.digest)

        subcommand = None
        if pargs:
                subcommand = pargs.pop(0)
                if subcommand == "help":
                        if pargs:
                                sub = pargs.pop(0)
                                if sub in cmds and \
                                    sub not in ["help", "-?", "--help"]:
                                        usage(retcode=0, full=False, cmd=sub)
                                elif sub == "-v":
                                        # Only display the long usage message
                                        # in the verbose mode.
                                        usage(retcode=0, full=True,
                                            verbose=True)
                                elif sub not in ["help", "-?", "--help"]:
                                        usage(_("unknown subcommand "
                                            "'{0}'").format(sub), unknown_cmd=sub)
                                else:
                                        usage(retcode=0, full=True)
                        else:
                                usage(retcode=0, full=True)

        # A gauntlet of tests to see if we need to print usage information
        if subcommand in cmds and show_usage:
                usage(retcode=0, cmd=subcommand, full=False)
        if subcommand and subcommand not in cmds:
                usage(_("unknown subcommand '{0}'").format(subcommand),
                    unknown_cmd=subcommand)
        if show_usage:
                usage(retcode=0, full=True)
        if not subcommand:
                usage(_("no subcommand specified"), full=True)
        if runid is not None:
                try:
                        runid = int(runid)
                except:
                        usage(_("runid must be an integer"))
                global_settings.client_runid = runid

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
                        usage(_("-R not allowed for {0} subcommand").format(
                              subcommand), cmd=subcommand)
                try:
                        pkg_timer.record("client startup", logger=logger)
                        ret = func(pargs)
                except getopt.GetoptError as e:
                        usage(_("illegal option -- {0}").format(e.opt),
                            cmd=subcommand)
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
        api_inst = __api_alloc(mydir, provided_image_dir, pkg_image_used)
        if api_inst is None:
                return EXIT_OOPS
        _api_inst = api_inst
        img = api_inst.img

        # Find subcommand and execute operation.
        func = cmds[subcommand][0]
        pargs_limit = None
        if len(cmds[subcommand]) > 1:
                pargs_limit = cmds[subcommand][1]

        pkg_timer.record("client startup", logger=logger)

        # Get the available options for the requested operation to create the
        # getopt parsing strings.
        valid_opts = options.get_pkg_opts(subcommand, add_table=cmd_opts)
        if not valid_opts:
                # if there are no options for an op, it has its own processing
                try:
                        return func(api_inst, pargs)
                except getopt.GetoptError as e:
                        usage(_("illegal option -- {0}").format(e.opt),
                            cmd=subcommand)

        try:
                # Parse CLI arguments into dictionary containing corresponding
                # options and values.
                opt_dict, pargs = misc.opts_parse(subcommand, pargs, valid_opts,
                    opts_mapping, usage)

                if pargs_limit is not None and len(pargs) > pargs_limit:
                        usage(_("illegal argument -- {0}").format(
                            pargs[pargs_limit]), cmd=subcommand)

                opts = options.opts_assemble(subcommand, api_inst, opt_dict,
                    add_table=cmd_opts, cwd=orig_cwd)

        except api_errors.InvalidOptionError as e:

                # We can't use the string representation of the exception since
                # it references internal option names. We substitute the CLI
                # options and create a new exception to make sure the messages
                # are correct.

                # Convert the internal options to CLI options. We make sure that
                # when there is a short and a long version for the same option
                # we print both to avoid confusion.
                def get_cli_opt(option):
                        try:
                                s, l = opts_mapping[option]
                                if l and not s:
                                        return "--{0}".format(l)
                                elif s and not l:
                                        return "-{0}".format(s)
                                else:
                                        return "-{0}/--{1}".format(s, l)
                        except KeyError:
                                # ignore if we can't find a match
                                # (happens for repeated arguments or invalid
                                # arguments)
                                return option
                        except TypeError:
                                # ignore if we can't find a match
                                # (happens for an invalid arguments list)
                                return option
                cli_opts = []
                opt_def = []

                for o in e.options:
                        cli_opts.append(get_cli_opt(o))

                        # collect the default value (see comment below)
                        opt_def.append(options.get_pkg_opts_defaults(subcommand,
                            o, add_table=cmd_opts))

                # Prepare for headache:
                # If we have an option 'b' which is set to True by default it
                # will be toggled to False if the users specifies the according
                # option on the CLI.
                # If we now have an option 'a' which requires option 'b' to be
                # set, we can't say "'a' requires 'b'" because the user can only
                # specify 'not b'. So the correct message would be:
                # "'a' is incompatible with 'not b'".
                # We can get there by just changing the type of the exception
                # for all cases where the default value of one of the options is
                # True.
                if e.err_type == api_errors.InvalidOptionError.REQUIRED:
                        if len(opt_def) == 2 and (opt_def[0] or opt_def[1]):
                                e.err_type = \
                                    api_errors.InvalidOptionError.INCOMPAT

                # This new exception will have the CLI options, so can be passed
                # directly to usage().
                new_e = api_errors.InvalidOptionError(err_type=e.err_type,
                    options=cli_opts, msg=e.msg, valid_args=e.valid_args)

                usage(str(new_e), cmd=subcommand)

        # Reset the progress tracker here, because we may have
        # to switch to a different tracker due to the options parse.
        _api_inst.progresstracker = get_tracker()

        return func(op=subcommand, api_inst=api_inst,
            pargs=pargs, **opts)

#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
def handle_errors(func, non_wrap_print=True, *args, **kwargs):
        traceback_str = misc.get_traceback_message()
        try:
                # Out of memory errors can be raised as EnvironmentErrors with
                # an errno of ENOMEM, so in order to handle those exceptions
                # with other errnos, we nest this try block and have the outer
                # one handle the other instances.
                try:
                        __ret = func(*args, **kwargs)
                except (MemoryError, EnvironmentError) as __e:
                        if isinstance(__e, EnvironmentError) and \
                            __e.errno != errno.ENOMEM:
                                raise
                        if _api_inst:
                                _api_inst.abort(
                                    result=RESULT_FAILED_OUTOFMEMORY)
                        error("\n" + misc.out_of_memory())
                        __ret = EXIT_OOPS
        except SystemExit as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_UNKNOWN)
                raise __e
        except (PipeError, KeyboardInterrupt):
                if _api_inst:
                        _api_inst.abort(result=RESULT_CANCELED)
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = EXIT_OOPS
        except api_errors.LinkedImageException as __e:
                error(_("Linked image exception(s):\n{0}").format(
                      str(__e)))
                __ret = __e.lix_exitrv
        except api_errors.CertificateError as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_CONFIGURATION)
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.PublisherError as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_BAD_REQUEST)
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.ImageLockedError as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_LOCKED)
                error(__e)
                __ret = EXIT_LOCKED
        except api_errors.TransportError as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_TRANSPORT)
                logger.error(_("\nErrors were encountered while attempting "
                    "to retrieve package or file data for\nthe requested "
                    "operation."))
                logger.error(_("Details follow:\n\n{0}").format(__e))
                print_proxy_config()
                __ret = EXIT_OOPS
        except api_errors.InvalidCatalogFile as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_STORAGE)
                logger.error(_("""
An error was encountered while attempting to read image state information
to perform the requested operation.  Details follow:\n\n{0}""").format(__e))
                __ret = EXIT_OOPS
        except api_errors.InvalidDepotResponseException as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_TRANSPORT)
                logger.error(_("\nUnable to contact a valid package "
                    "repository. This may be due to a problem with the "
                    "repository, network misconfiguration, or an incorrect "
                    "pkg client configuration.  Please verify the client's "
                    "network configuration and repository's location."))
                logger.error(_("\nAdditional details:\n\n{0}").format(__e))
                print_proxy_config()
                __ret = EXIT_OOPS
        except api_errors.HistoryLoadException as __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if _api_inst:
                        _api_inst.clear_history()
                error(_("An error was encountered while attempting to load "
                    "history information\nabout past client operations."))
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.HistoryStoreException as __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if _api_inst:
                        _api_inst.clear_history()
                error(_("An error was encountered while attempting to store "
                    "information about the\ncurrent operation in client "
                    "history."))
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.HistoryPurgeException as __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if _api_inst:
                        _api_inst.clear_history()
                error(_("An error was encountered while attempting to purge "
                    "client history."))
                error(__e)
                __ret = EXIT_OOPS
        except api_errors.VersionException as __e:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_UNKNOWN)
                error(_("The pkg command appears out of sync with the libraries"
                    " provided\nby pkg:/package/pkg. The client version is "
                    "{client} while the library\nAPI version is {api}.").format(
                    client=__e.received_version,
                    api=__e.expected_version
                    ))
                __ret = EXIT_OOPS
        except api_errors.WrapSuccessfulIndexingException as __e:
                __ret = EXIT_OK
        except api_errors.WrapIndexingException as __e:
                def _wrapper():
                        raise __e.wrapped
                __ret = handle_errors(_wrapper, non_wrap_print=False)
                s = ""
                if __ret == 99:
                        s += _("\n{err}{stacktrace}").format(
                        err=__e, stacktrace=traceback_str)

                s += _("\n\nDespite the error while indexing, the operation "
                    "has completed successfuly.")
                error(s)
        except api_errors.ReadOnlyFileSystemException as __e:
                __ret = EXIT_OOPS
        except api_errors.UnexpectedLinkError as __e:
                error("\n" + str(__e))
                __ret = EXIT_OOPS
        except api_errors.UnrecognizedCatalogPart as __e:
                error("\n" + str(__e))
                __ret = EXIT_OOPS
        except api_errors.InvalidConfigFile as __e:
                error("\n" + str(__e))
                __ret = EXIT_OOPS
        except (api_errors.PkgUnicodeDecodeError, UnicodeEncodeError) as __e:
                error("\n" + str(__e))
                __ret = EXIT_OOPS
        except:
                if _api_inst:
                        _api_inst.abort(result=RESULT_FAILED_UNKNOWN)
                if non_wrap_print:
                        traceback.print_exc()
                        error(traceback_str)
                __ret = 99
        return __ret


def handle_sighupterm(signum, frame):
        """Attempt to gracefully handle SIGHUP and SIGTERM by telling the api
        to abort and record the cancellation before exiting."""

        try:
                if _api_inst:
                        _api_inst.abort(result=RESULT_CANCELED)
        except:
                # If history operation fails for some reason, drive on.
                pass

        # Use os module to immediately exit (bypasses standard exit handling);
        # this is preferred over raising a KeyboardInterupt as whatever module
        # we interrupted may not expect that if they disabled SIGINT handling.
        os._exit(EXIT_OOPS)


if __name__ == "__main__":
        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())

        # Make all warnings be errors.
        import warnings
        warnings.simplefilter('error')
        if six.PY3:
                # disable ResourceWarning: unclosed file
                warnings.filterwarnings("ignore", category=ResourceWarning)

        # Attempt to handle SIGHUP/SIGTERM gracefully.
        import signal
        if portable.osname != "windows":
                # SIGHUP not supported on windows; will cause exception.
                signal.signal(signal.SIGHUP, handle_sighupterm)
        signal.signal(signal.SIGTERM, handle_sighupterm)

        __retval = handle_errors(main_func)
        if DebugValues["timings"]:
                def __display_timings():
                        msg(str(pkg_timer))
                handle_errors(__display_timings)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
