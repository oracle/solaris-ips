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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#
# pkg - package system client utility
#
# We use urllib2 for GET and POST operations, but httplib for PUT and DELETE
# operations.
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
import urllib2
import urlparse

import pkg
import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.bootenv as bootenv
import pkg.client.history as history
import pkg.client.image as image
import pkg.client.imagetypes as imgtypes
import pkg.client.progress as progress
import pkg.client.publisher as publisher
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.version as version

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.client.history import (RESULT_CANCELED, RESULT_FAILED_BAD_REQUEST,
    RESULT_FAILED_CONFIGURATION, RESULT_FAILED_TRANSPORT, RESULT_FAILED_UNKNOWN,
    RESULT_FAILED_OUTOFMEMORY)
from pkg.misc import EmptyI, msg, PipeError

CLIENT_API_VERSION = 26
PKG_CLIENT_NAME = "pkg"

JUST_UNKNOWN = 0
JUST_LEFT = -1
JUST_RIGHT = 1

#pkg exit codes
EXIT_OK      = 0
EXIT_OOPS    = 1
EXIT_BADOPT  = 2
EXIT_PARTIAL = 3
EXIT_NOP     = 4
EXIT_NOTLIVE = 5


logger = global_settings.logger

valid_special_attrs = ["action.name", "action.key", "action.raw"]

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
        pkg install [-nvq] [--no-refresh] [--no-index] package...
        pkg uninstall [-nrvq] [--no-index] package...
        pkg list [-Hafnsuv] [--no-refresh] [package...]
        pkg image-update [-fnvq] [--be-name name] [--no-refresh] [--no-index]
        pkg refresh [--full] [publisher ...]
        pkg version

Advanced subcommands:
        pkg info [-lr] [--license] [pkg_fmri_pattern ...]
        pkg search [-alprI] [-s server] query
        pkg verify [-Hqv] [pkg_fmri_pattern ...]
        pkg fix [pkg_fmri_pattern ...]
        pkg contents [-Hmr] [-o attribute ...] [-s sort_key]
            [-t action_type ... ] [pkg_fmri_pattern ...]
        pkg image-create [-fFPUz] [--force] [--full|--partial|--user] [--zone]
            [-k ssl_key] [-c ssl_cert] [--no-refresh]
            [--variant <variant_spec>=<instance>] 
            [--facet <facet_spec>=[True,False]]
            (-p|--publisher) name=uri dir
        pkg change-variant [-nvq] [--be-name name] <variant_spec>=<instance>
            [<variant_spec>=<instance> ...]
        pkg change-facet -nvq [--be-name name] <facet_spec>=[True|False|None] ...
        pkg variant -H [<variant_spec>]
        pkg facet -H [<facet_spec>]
        pkg set-property propname propvalue
        pkg unset-property propname ...
        pkg property [-H] [propname ...]

        pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert]
            [-g origin_to_add | --add-origin=origin_to_add]
            [-G origin_to_remove | --remove-origin=origin_to_remove]
            [-m mirror_to_add | --add-mirror=mirror_to_add]
            [-M mirror_to_remove | --remove-mirror=mirror_to_remove]
            [--enable] [--disable] [--no-refresh] [--reset-uuid] 
            [--non-sticky] [--sticky] [--search-after=publisher]
            [--search-before=publisher] publisher
        pkg unset-publisher publisher ...
        pkg publisher [-HPn] [publisher ...]
        pkg history [-Hl]
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

def check_fmri_args(args):
        """ Convenience routine to check that input args are valid fmris. """
        ret = True
        for x in args:
                try:
                        #
                        # Pass a bogus build release-- needed to satisfy
                        # fmri's checks in the common case that a version but
                        # no build release was specified by the user.
                        #
                        fmri.MatchingPkgFmri(x, build_release="1.0")
                except fmri.IllegalFmri, e:
                        error(e)
                        ret = False
        return ret

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
                        pkg_list = api.ImageInterface.LIST_INSTALLED_NEWEST
                elif opt == "-f":
                        ltypes.add(opt)
                        pkg_list = api.ImageInterface.LIST_ALL
                        variants = True
                elif opt == "-n":
                        ltypes.add(opt)
                        pkg_list = api.ImageInterface.LIST_NEWEST
                elif opt == "-s":
                        summary = True
                elif opt == "-u":
                        ltypes.add(opt)
                        pkg_list = api.ImageInterface.LIST_UPGRADABLE
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

        if not check_fmri_args(pargs):
                return EXIT_OOPS

        api_inst = __api_alloc(img, quiet=not display_headers)
        if api_inst == None:
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

        pats = EmptyI
        if pargs:
                pats = pargs

        found = False
        ppub = api_inst.get_preferred_publisher().prefix
        try:
                res = api_inst.get_pkg_list(pkg_list, patterns=pats,
                    variants=variants)
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
                        else:
                                st_str = _("known")

                        if verbose:
                                pfmri = "pkg://%s/%s@%s" % (pub, stem, ver)
                                msg("%-64s %-10s %s" % (pfmri, st_str, ufoxi))
                                continue

                        pf = stem + spub
                        if summary:
                                msg(fmt_str % (pf, summ))
                                continue

                        sver = version.Version.split(ver)[-1]
                        msg(fmt_str % (pf, sver, st_str, ufoxi))

                if not found:
                        if pargs:
                                raise api_errors.InventoryException(
                                    notfound=pargs)
                        if pkg_list == api_inst.LIST_INSTALLED:
                                logger.error(_("no packages installed"))
                                api_inst.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                return EXIT_OOPS
                        if pkg_list == api_inst.LIST_UPGRADABLE:
                                if pargs:
                                        logger.error(_("No specified packages "
                                            "have newer versions available."))
                                else:
                                        logger.error(_("No installed packages "
                                            "have newer versions available."))
                                api_inst.log_operation_end(
                                    result=history.RESULT_NOTHING_TO_DO)
                                return EXIT_OOPS

                        api_inst.log_operation_end(
                            result=history.RESULT_NOTHING_TO_DO)
                        return EXIT_OOPS

                api_inst.log_operation_end()
                return EXIT_OK
        except api_errors.InventoryException, e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        api_inst.log_operation_end(
                            result=history.RESULT_FAILED_BAD_REQUEST)
                        return EXIT_OOPS

                if pkg_list == api.ImageInterface.LIST_ALL:
                        state = _("known")
                elif pkg_list == api.ImageInterface.LIST_INSTALLED_NEWEST:
                        state = _("known or installed")
                else:
                        state = _("installed")
                for pat in e.notfound:
                        error(_("no packages matching "
                            "'%(pattern)s' %(state)s") %
                            { "pattern": pat, "state": state })
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
        fmris, notfound, illegals = img.installed_fmris_from_args(args)

        any_errors = False
        repairs = []
        for f, fstate in fmris:
                failed_actions = []
                for err in img.verify(f, progresstracker,
                    verbose=True, forever=True):
                        if not failed_actions:
                                msg("Verifying: %-50s %7s" %
                                    (f.get_pkg_stem(), "ERROR"))
                        act = err[0]
                        failed_actions.append(act)
                        msg("\t%s" % act.distinguished_name())
                        for x in err[1]:
                                msg("\t\t%s" % x)
                if failed_actions:
                        repairs.append((f, failed_actions))

        # Repair anything we failed to verify
        if repairs:
                # Create a snapshot in case they want to roll back
                try:
                        be = bootenv.BootEnv(img.get_root())
                        if be.exists():
                                msg(_("Created ZFS snapshot: %s" %
                                    be.snapshot_name))
                except RuntimeError:
                        pass # Error is printed by the BootEnv call.
                try:
                        success = img.repair(repairs, progresstracker)
                except api_errors.RebootNeededOnLiveImageException:
                        error(_("Requested \"fix\" operation would affect "
                            "files that cannot be modified in live image.\n"
                            "Please retry this operation on an alternate boot "
                            "environment."))
                        success = False
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

        progresstracker = get_tracker(quiet)

        if not check_fmri_args(pargs):
                return EXIT_OOPS

        fmris, notfound, illegals = img.installed_fmris_from_args(pargs)

        if illegals:
                for i in illegals:
                        logger.error(str(i))
                return EXIT_OOPS

        any_errors = False

        header = False
        for f, fstate in fmris:
                pkgerr = False
                for err in img.verify(f, progresstracker,
                    verbose=verbose, forever=forever):
                        #
                        # Eventually this code should probably
                        # move into the progresstracker
                        #
                        if not pkgerr:
                                if display_headers and not header:
                                        msg("%-50s %7s" % ("PACKAGE", "STATUS"))
                                        header = True

                                if not quiet:
                                        msg("%-50s %7s" % (f.get_pkg_stem(),
                                            "ERROR"))
                                pkgerr = True

                        if not quiet:
                                msg("\t%s" % err[0].distinguished_name())
                                for x in err[1]:
                                        msg("\t\t%s" % x)
                if verbose and not pkgerr:
                        if display_headers and not header:
                                msg("%-50s %7s" % ("PACKAGE", "STATUS"))
                                header = True
                        msg("%-50s %7s" % (f.get_pkg_stem(), "OK"))

                any_errors = any_errors or pkgerr

        if fmris:
                progresstracker.verify_done()

        if notfound:
                if fmris:
                        logger.error("")
                logger.error(_("""\
pkg: no packages matching the following patterns you specified are
installed on the system.\n"""))
                for p in notfound:
                        logger.error("        %s" % p)
                if fmris:
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

def __api_prepare(operation, api_inst, verbose=False):
        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        # XXX would be nice to kick the progress tracker.
        try:
                api_inst.prepare()
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return False
        except api_errors.TransportError, e:
                # move past the progress tracker line.
                msg("\n")
                if verbose:
                        e.verbose = True
                raise e
        except KeyboardInterrupt:
                raise
        except:
                error(_("\nAn unexpected error happened while preparing for " \
                    "%s:") % operation)
                raise
        return True

def __api_execute_plan(operation, api_inst, raise_ActionExecutionError=True):
        try:
                api_inst.execute_plan()
        except RuntimeError, e:
                error(_("%s failed: %s") % (operation, e))
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
        except api_errors.ReadOnlyFileSystemException, e:
                error(e)
                raise
        except api_errors.PermissionsException, e:
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
        except api_errors.ActionExecutionError, e:
                if not raise_ActionExecutionError:
                        return EXIT_OOPS
                error(_("An unexpected error happened during " \
                    "%s: %s") % (operation, e))
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
running %s.  Please update pkg(5) using 'pfexec pkg install
SUNWipkg' and then retry the %s."""
                    ) % (op, op))
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
        if issubclass(e_type, api_errors.BEException):
                error(_(e))
                return False
        if e_type in (api_errors.CertificateError,
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
        opts, pargs = getopt.getopt(args, "nvq", ["be-name="])

        quiet = noexecute = verbose = False
        be_name = None
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--be-name":
                        be_name = arg

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

        try:
                stuff_to_do = api_inst.plan_change_varcets(variants, facets=None,
                    noexecute=noexecute, verbose=verbose, be_name=be_name)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return EXIT_OOPS

        if not stuff_to_do:
                msg(_("No updates necessary for this image."))
                return EXIT_NOP

        if noexecute:
                return EXIT_OOPS


        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        if not __api_prepare("change-variant", api_inst, verbose=verbose):
                return EXIT_OOPS

        ret_code = __api_execute_plan("change-variant", api_inst)

        if bool(os.environ.get("PKG_MIRROR_STATS", False)):
                print_mirror_stats(api_inst)

        return ret_code

def change_facet(img, args):
        """Attempt to change the facets as specified, updating
        image as necessary"""

        op = "change-facet"
        opts, pargs = getopt.getopt(args, "nvq", ["be-name="])

        quiet = noexecute = verbose = False
        be_name = None
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--be-name":
                        be_name = arg

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
                return EXIT_OK


        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        if not __api_prepare(op, api_inst, verbose=verbose):
                return EXIT_OOPS

        ret_code = __api_execute_plan(op, api_inst)

        if bool(os.environ.get("PKG_MIRROR_STATS", False)):
                print_mirror_stats(api_inst)

        return ret_code

def image_update(img, args):
        """Attempt to take all installed packages specified to latest
        version."""

        # XXX Publisher-catalog issues.
        # XXX Leaf package refinements.

        op = "image-update"
        opts, pargs = getopt.getopt(args, "fnvq", ["be-name=", "no-refresh",
            "no-index"])

        force = quiet = noexecute = verbose = False
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
                elif opt == "--no-refresh":
                        refresh_catalogs = False
                elif opt == "--no-index":
                        update_index = False
                elif opt == "--be-name":
                        be_name = arg

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd="image-update")

        if pargs:
                usage(_("command does not take operands ('%s')") % \
                    " ".join(pargs), cmd="image-update")

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

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
                return EXIT_OK

        if not __api_prepare(op, api_inst, verbose=verbose):
                return EXIT_OOPS

        ret_code = __api_execute_plan(op, api_inst)

        if ret_code == 0 and opensolaris_image:
                msg("\n" + "-" * 75)
                msg(_("NOTE: Please review release notes posted at:\n" ))
                msg(misc.get_release_notes_url())
                msg("-" * 75 + "\n")

        if bool(os.environ.get("PKG_MIRROR_STATS", False)):
                print_mirror_stats(api_inst)

        return ret_code

def print_mirror_stats(api_inst):
        """Given an api_inst object, print depot status information."""

        status_fmt = "%-10s %-35s %10s %10s"
        print status_fmt % ("Publisher", "URI", "Success", "Failure")

        for ds in api_inst.img.gen_depot_status():
                print status_fmt % (ds.prefix, ds.url, ds.good_tx, ds.errors)

def install(img, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Publisher-catalog issues.
        op = "install"
        opts, pargs = getopt.getopt(args, "nvq", ["no-refresh", "no-index"])

        quiet = noexecute = verbose = False
        refresh_catalogs = update_index = True

        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True
                elif opt == "--no-refresh":
                        refresh_catalogs = False
                elif opt == "--no-index":
                        update_index = False

        if not pargs:
                usage(_("at least one package name required"), cmd="install")

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd="install")

        if not check_fmri_args(pargs):
                return EXIT_OOPS

        api_inst = __api_alloc(img, quiet)
        if api_inst == None:
                return EXIT_OOPS

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
                return EXIT_OK

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        if not __api_prepare(op, api_inst, verbose=verbose):
                return EXIT_OOPS

        ret_code = __api_execute_plan(op, api_inst,
            raise_ActionExecutionError=False)

        if bool(os.environ.get("PKG_MIRROR_STATS", False)):
                print_mirror_stats(api_inst)

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
                usage(_("at least one package name required"), cmd="uninstall")

        if verbose and quiet:
                usage(_("-v and -q may not be combined"), cmd="uninstall")

        if not check_fmri_args(pargs):
                return EXIT_OOPS

        api_inst = __api_alloc(img, quiet)
        if api_inst is None:
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
        if not __api_prepare(op, api_inst, verbose=verbose):
                return EXIT_OOPS

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
                        error(_("The server returned a malformed result.\n"
                            "The problematic structure:%r") % (tup,))
                        return False
                try:
                        action = actions.fromstr(action.rstrip())
                except actions.ActionError, e:
                        error(_("The server returned an invalid action.\n%s") %
                            e)
                        return False
                match_type = produce_matching_type(action, match)
                match = produce_matching_token(action, match)
        else:
                pfmri = tup
        pfmri = fmri.PkgFmri(str(pfmri))
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

        opts, pargs = getopt.getopt(args, "Halo:prs:I")

        default_attrs_action = ["search.match_type", "action.name",
            "search.match", "pkg.shortfmri"]

        default_attrs_package = ["pkg.shortfmri", "pkg.publisher"]

        local = remote = case_sensitive = False
        servers = []
        attrs = []
        return_actions = True
        display_headers = True
        use_default_attrs = True
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-a":
                        return_actions = True
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
                                            "server URL.") % orig_arg)
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
                            servers=servers))
                # By default assume we don't find anything.
                retcode = EXIT_OOPS

                # get initial set of results
                justs = calc_justs(attrs)
                page_again = True
                widths = []
                st = None
                ssu = None
                header_attrs = attrs
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
                                                error(_("The server returned a "
                                                    "malformed result:%r") %
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
                        except api_errors.SlowSearchUsed, e:
                                ssu = e
                        lines = produce_lines(unprocessed_res, attrs,
                            show_all=True)
                        old_widths = widths[:]
                        widths = calc_widths(lines, attrs, widths)
                        # If headers are being displayed and the layout of the
                        # columns have changed, print the headers again using
                        # the new widths.
                        if display_headers and old_widths[:-1] != widths[:-1]:
                                print_headers(header_attrs, widths, justs)
                        for line in lines:
                                msg((create_output_format(display_headers,
                                    widths, justs, line) %
                                    tuple(line)).rstrip())
                        st = time.time()
                if ssu:
                        raise ssu


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
                retcode = EXIT_NOP
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

        if not check_fmri_args(pargs):
                return EXIT_OOPS

        err = 0

        api_inst = __api_alloc(img, quiet=True)
        if api_inst == None:
                return EXIT_OOPS

        try:
                info_needed = api.PackageInfo.ALL_OPTIONS
                if not display_license:
                        info_needed = api.PackageInfo.ALL_OPTIONS - \
                            frozenset([api.PackageInfo.LICENSES])
                info_needed -= api.PackageInfo.ACTION_OPTIONS
                info_needed |= frozenset([api.PackageInfo.DEPENDENCIES])

                try:
                        ret = api_inst.info(pargs, info_local, info_needed)
                except api_errors.UnrecognizedOptionsToInfo, e:
                        error(e)
                        return EXIT_OOPS
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                multi_match = ret[api.ImageInterface.INFO_MULTI_MATCH]

        except api_errors.PermissionsException, e:
                error(e)
                return EXIT_OOPS
        except api_errors.NoPackagesInstalledException:
                error(_("no packages installed"))
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

                if api.PackageInfo.RENAMED in pi.states:
                        msg(_("    Renamed to:"), pi.dependencies[0])
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
                err = EXIT_OOPS
                if pis:
                        logger.error("")
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

        if illegals:
                err = EXIT_OOPS
                for i in illegals:
                        logger.error(str(i))

        if multi_match:
                err = EXIT_OOPS
                for pfmri, matches in multi_match:
                        error(_("'%s' matches multiple packages") % pfmri)
                        for k in matches:
                                logger.error("\t%s" % k)

        if no_licenses:
                err = EXIT_OOPS
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
        
def produce_lines(actionlist, attrs, action_types=None, show_all=False):
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
        """

        lines = []
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

                if line and [l for l in line if str(l) != ""] or show_all:
                        lines.append(line)
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
        """Print results of a "list" operation """

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

        if display_headers:
                print_headers(attrs, widths, justs)

        for line in sorted(lines, key=key_extract):
                msg((create_output_format(display_headers, widths, justs,
                    line) % tuple(line)).rstrip())

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

        opts, pargs = getopt.getopt(args, "Ho:s:t:mfr")

        display_headers = True
        display_raw = False
        remote = False
        local = False
        attrs = []
        sort_attrs = []
        action_types = []
        for opt, arg in opts:
                if opt == "-H":
                        display_headers = False
                elif opt == "-o":
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
                usage(_("-l and -r may not be combined"), cmd="contents")

        if remote and not pargs:
                usage(_("contents: must request remote contents for specific "
                   "packages"), cmd="contents")

        if not check_fmri_args(pargs):
                return EXIT_OOPS

        if display_raw:
                display_headers = False
                attrs = [ "action.raw" ]

                invalid = set(("-H", "-o", "-t")). \
                    intersection(set([x[0] for x in opts]))

                if len(invalid) > 0:
                        usage(_("-m and %s may not be specified at the same "
                            "time") % invalid.pop(), cmd="contents")

        check_attrs(attrs, "contents")

        img.history.operation_name = "contents"

        err = EXIT_OK

        if local:
                fmris, notfound, illegals = \
                    img.installed_fmris_from_args(pargs)

                if illegals:
                        for i in illegals:
                                logger.error(i)
                        img.history.operation_result = \
                            history.RESULT_FAILED_BAD_REQUEST
                        return EXIT_OOPS

                if not fmris and not notfound:
                        error(_("no packages installed"))
                        img.history.operation_result = \
                            history.RESULT_NOTHING_TO_DO
                        return EXIT_OOPS
        elif remote:
                # Verify validity of certificates before attempting network
                # operations
                try:
                        img.check_cert_validity()
                except (api_errors.CertificateError,
                    api_errors.PermissionsException), e:
                        img.history.log_operation_end(error=e)
                        return EXIT_OOPS

                fmris = []
                notfound = []

                # XXX This loop really needs not to be copied from
                # Image.make_install_plan()!
                ppub = img.get_preferred_publisher()
                for p in pargs:
                        try:
                                matches = list(img.inventory([ p ],
                                    all_known = True))
                        except api_errors.InventoryException, e:
                                assert(len(e.notfound) == 1)
                                notfound.append(e.notfound[0])
                                continue

                        pnames = {}
                        pmatch = []
                        npnames = {}
                        npmatch = []
                        for m, state in matches:
                                if m.get_publisher() == ppub:
                                        pnames[m.get_pkg_stem()] = 1
                                        pmatch.append(m)
                                else:
                                        npnames[m.get_pkg_stem()] = 1
                                        npmatch.append(m)

                        if len(pnames.keys()) > 1:
                                msg(_("pkg: contents: '%s' matches multiple "
                                    "packages") % p)
                                for k in pnames.keys():
                                        msg("\t%s" % k)
                                continue
                        elif len(pnames.keys()) < 1 and len(npnames.keys()) > 1:
                                msg(_("pkg: contents: '%s' matches multiple "
                                    "packages") % p)
                                for k in npnames.keys():
                                        msg("\t%s" % k)
                                continue

                        # matches is a list reverse sorted by version, so take
                        # the first; i.e., the latest.
                        if len(pmatch) > 0:
                                fmris.append((pmatch[0], None))
                        else:
                                fmris.append((npmatch[0], None))

        #
        # If the user specifies no specific attrs, and no specific
        # sort order, then we fill in some defaults.
        #
        if not attrs:
                # XXX Possibly have multiple exclusive attributes per column?
                # If listing dependencies and files, you could have a path/fmri
                # column which would list paths for files and fmris for
                # dependencies.
                attrs = [ "path" ]

        if not sort_attrs:
                # XXX reverse sorting
                # Most likely want to sort by path, so don't force people to
                # make it explicit
                if "path" in attrs:
                        sort_attrs = [ "path" ]
                else:
                        sort_attrs = attrs[:1]

        # if we want a raw display (contents -m), disable the automatic
        # variant filtering that normally limits working set.

        if display_raw:
                excludes = EmptyI
        else:
                excludes = img.list_excludes()

        manifests = (
            img.get_manifest(f, all_variants=display_raw)
            for f, state in fmris
        )

        actionlist = [
            (m.fmri, a, None, None, None)
            for m in manifests
            for a in m.gen_actions(excludes)
        ]

        if fmris:
                display_contents_results(actionlist, attrs, sort_attrs,
                    action_types, display_headers)

        if notfound:
                err = EXIT_OOPS
                if fmris:
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
                img.history.operation_result = history.RESULT_NOTHING_TO_DO
        else:
                img.history.operation_result = history.RESULT_SUCCEEDED
        img.cleanup_downloads()
        return err

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
                if isinstance(err, urllib2.HTTPError):
                        logger.error("   %s: %s - %s" % \
                            (err.filename, err.code, err.msg))
                elif isinstance(err, urllib2.URLError):
                        if err.args[0][0] == 8:
                                logger.error("    %s: %s" % \
                                    (urlparse.urlsplit(
                                        pub["origin"])[1].split(":")[0],
                                    err.args[0][1]))
                        else:
                                if isinstance(err.args[0], socket.timeout):
                                        logger.error("    %s: %s" % \
                                            (pub["origin"], "timeout"))
                                else:
                                        logger.error("    %s: %s" % \
                                            (pub["origin"], err.args[0][1]))
                else:
                        logger.error("   ")
                        logger.error(str(err))

        if cre.message:
                logger.error(cre.message)

        return succeeded

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

        try:
                # The user explicitly requested this refresh, so set the
                # refresh to occur immediately.
                api_inst.refresh(full_refresh=full_refresh,
                    immediate=True, pubs=pargs)
        except api_errors.PublisherError, e:
                error(e)
                error(_("'pkg publisher' will show a list of publishers."))
                return EXIT_OOPS
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS
        except api_errors.CatalogRefreshException, e:
                if display_catalog_failures(e) == 0:
                        return EXIT_OOPS
                else:
                        return EXIT_PARTIAL
        else:
                return EXIT_OK

def publisher_set(img, args):
        """pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert] [--reset-uuid]
            [-g|--add-origin origin to add] [-G|--remove-origin origin to
            remove] [-m|--add-mirror mirror to add] [-M|--remove-mirror mirror
            to remove] [--enable] [--disable] [--no-refresh] [--sticky] [--non-sticky ]
            [--search-before=publisher] [--search-after=publisher] publisher"""

        preferred = False
        ssl_key = None
        ssl_cert = None
        origin_url = None
        reset_uuid = False
        add_mirrors = set()
        remove_mirrors = set()
        add_origins = set()
        remove_origins = set()
        refresh_catalogs = True
        disable = None
        sticky = None
        search_before = None
        search_after = None

        opts, pargs = getopt.getopt(args, "Pedk:c:O:G:g:M:m:",
            ["add-mirror=", "remove-mirror=", "add-origin=", "remove-origin=",
            "no-refresh", "reset-uuid", "enable", "disable", "sticky", 
            "non-sticky", "search-before=", "search-after="])

        for opt, arg in opts:
                if opt == "-c":
                        ssl_cert = arg
                if opt == "-d" or opt == "--disable":
                        disable = True
                if opt == "-e" or opt == "--enable":
                        disable = False
                if opt == "-g" or opt == "--add-origin":
                        add_origins.add(arg)
                if opt == "-G" or opt == "--remove-origin":
                        remove_origins.add(arg)
                if opt == "-k":
                        ssl_key = arg
                if opt == "-O":
                        origin_url = arg
                if opt == "-m" or opt == "--add-mirror":
                        add_mirrors.add(arg)
                if opt == "-M" or opt == "--remove-mirror":
                        remove_mirrors.add(arg)
                if opt == "-P":
                        preferred = True
                if opt == "--reset-uuid":
                        reset_uuid = True
                if opt == "--no-refresh":
                        refresh_catalogs = False
                if opt == "--sticky":
                        sticky = True
                if opt == "--non-sticky":
                        sticky = False
                if opt == "--search-before":
                        search_before = arg
                if opt == "--search-after":
                        search_after = arg
                        
        if len(pargs) == 0:
                usage(_("requires a publisher name"), cmd="set-publisher")
        elif len(pargs) > 1:
                usage( _("only one publisher name may be specified"),
                    cmd="set-publisher",)

        name = pargs[0]

        if preferred and disable:
                usage(_("the -p and -d options may not be combined"),
                    cmd="set-publisher")

        if origin_url and (add_origins or remove_origins):
                usage(_("the -O and -g, --add-origin, -G, or --remove-origin "
                    "options may not be combined"), cmd="set-publisher")

        if search_before and search_after:
                usage(_("search_before and search_after may not be combined"),
                      cmd="set-publisher")

        api_inst = __api_alloc(img)
        if api_inst == None:
                return EXIT_OOPS

        new_pub = False
        try:
                pub = api_inst.get_publisher(prefix=name, alias=name,
                    duplicate=True)
                if reset_uuid:
                        pub.reset_client_uuid()
                repo = pub.selected_repository
        except api_errors.PermissionsException, e:
                error(e, cmd="set-publisher")
                return EXIT_OOPS
        except api_errors.UnknownPublisher:
                if not origin_url and not add_origins:
                        error(_("publisher does not exist. Use -g to define "
                            "origin URI for new publisher."),
                            cmd="set-publisher")
                        return EXIT_OOPS
                # No pre-existing, so create a new one.
                repo = publisher.Repository()
                pub = publisher.Publisher(name, repositories=[repo])
                new_pub = True

        if disable is not None:
                # Set disabled property only if provided.
                pub.disabled = disable

        if sticky is not None:
                # Set stickiness only if provided
                pub.sticky = sticky

        if origin_url:
                # For compatibility with old -O behaviour, treat -O as a wipe
                # of existing origins and add the new one.
                try:
                        # Only use existing cert information if the new URI uses
                        # https for transport.
                        if repo.origins and not (ssl_cert or ssl_key) and \
                            origin_url.startswith("https:"):
                                for uri in repo.origins:
                                        if ssl_cert is None:
                                                ssl_cert = uri.ssl_cert
                                        if ssl_key is None:
                                                ssl_key = uri.ssl_key
                                        break

                        repo.reset_origins()
                        repo.add_origin(origin_url)

                        # XXX once image configuration supports storing this
                        # information at the uri level, ssl info should be set
                        # here.
                except api_errors.PublisherError, e:
                        error(e, cmd="set-publisher")
                        return EXIT_OOPS

        for entry in (("mirror", add_mirrors, remove_mirrors), ("origin",
            add_origins, remove_origins)):
                etype, add, remove = entry
                # XXX once image configuration supports storing this
                # information at the uri level, ssl info should be set
                # here.
                try:
                        for u in add:
                                getattr(repo, "add_%s" % etype)(u)
                        for u in remove:
                                getattr(repo, "remove_%s" % etype)(u)
                except (api_errors.PublisherError,
                    api_errors.CertificateError), e:
                        error(e, cmd="set-publisher")
                        return EXIT_OOPS

        # None is checked for here so that a client can unset a ssl_cert or
        # ssl_key by using -k "" or -c "".
        if ssl_cert is not None or ssl_key is not None:
                #
                # In the case of zones, the ssl cert given is assumed to
                # be relative to the root of the image, not truly absolute.
                #
                if img.is_zone():
                        if ssl_cert is not None:
                                ssl_cert = os.path.abspath(
                                    img.get_root() + os.sep + ssl_cert)
                        if ssl_key is not None:
                                ssl_key = os.path.abspath(
                                    img.get_root() + os.sep + ssl_key)

                # Assume the user wanted to update the ssl_cert or ssl_key
                # information for *all* of the currently selected
                # repository's origins and mirrors.
                try:
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
                except (api_errors.PublisherError,
                    api_errors.CertificateError), e:
                        error(e, cmd="set-publisher")
                        return EXIT_OOPS

        try:
                if new_pub:
                        api_inst.add_publisher(pub,
                            refresh_allowed=refresh_catalogs)
                else:
                        api_inst.update_publisher(pub,
                            refresh_allowed=refresh_catalogs)
        except api_errors.CatalogRefreshException, e:
                text = "Could not refresh the catalog for %s"
                error(_(text) % pub)
                return EXIT_OOPS
        except api_errors.InvalidDepotResponseException, e:
                error(_("The origin URIs for '%(pubname)s' do not appear to "
                    "point to a valid pkg server.\nPlease check the server's "
                    "address and client's network configuration."
                    "\nAdditional details:\n\n%(details)s") %
                    { "pubname": pub.prefix, "details": e })
                return EXIT_OOPS
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return EXIT_OOPS

        if preferred:
                api_inst.set_preferred_publisher(prefix=pub.prefix)

        if search_before:
                api_inst.set_pub_search_before(pub.prefix, search_before)

        if search_after:
                api_inst.set_pub_search_after(pub.prefix, search_after)


        return EXIT_OK

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

        # 'a' is left over
        opts, pargs = getopt.getopt(args, "HPan")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                if opt == "-P":
                        preferred_only = True
                if opt == "-n":
                        inc_disabled = False

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
                fmt = "%-24s %-12s %-8s %-8s %s"
                if not omit_headers:
                        msg(fmt % (_("PUBLISHER"), "", _("TYPE"), _("STATUS"),
                            _("URI")))

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
                for p in pubs:
                        pfx = p.prefix
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
                                pstatus = "(%s)" % ", ".join(pstatus_list)
                        else:
                                pstatus = ""

                        # Only show the selected repository's information in
                        # summary view.
                        r = p.selected_repository
                        for uri in r.origins:
                                # XXX get the real origin status
                                msg(fmt % (pfx, pstatus, _("origin"), "online",
                                    uri))
                        for uri in r.mirrors:
                                # XXX get the real mirror status
                                msg(fmt % (pfx, pstatus, _("mirror"), "online",
                                    uri))
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
        imgtype = image.IMG_USER
        is_zone = False
        mirrors = set()
        origins = set()
        pub_name = None
        refresh_catalogs = True
        ssl_key = None
        ssl_cert = None
        variants = {}
        facets = pkg.facet.Facets()

        opts, pargs = getopt.getopt(args, "fFPUza:g:m:p:k:c:",
            ["force", "full", "partial", "user", "zone", "authority=", "facet=",
                "mirror=", "origin=", "publisher=", "no-refresh", "variant="])

        for opt, arg in opts:
                # -a is deprecated and will be removed at a future date.
                if opt in ("-a", "-p", "--publisher"):
                        pub_url = None
                        try:
                                pub_name, pub_url = arg.split("=", 1)
                        except ValueError:
                                pub_name = None
                                pub_url = None

                        if pub_name is None or pub_url is None:
                                usage(_("publisher argument must be of the "
                                    "form '<prefix>=<url>'."),
                                    cmd="image-create")
                        origins.add(pub_url)
                elif opt == "-c":
                        ssl_cert = arg
                elif opt == "-f" or opt == "--force":
                        force = True
                elif opt in ("-g", "--origin"):
                        origins.add(arg)
                elif opt == "-k":
                        ssl_key = arg
                elif opt in ("-m", "--mirror"):
                        mirrors.add(arg)
                elif opt == "-z" or opt == "--zone":
                        is_zone = True
                        imgtype = image.IMG_ENTIRE
                elif opt == "-F" or opt == "--full":
                        imgtype = imgtypes.IMG_ENTIRE
                elif opt == "-P" or opt == "--partial":
                        imgtype = imgtypes.IMG_PARTIAL
                elif opt == "-U" or opt == "--user":
                        imgtype = imgtypes.IMG_USER
                elif opt == "--no-refresh":
                        refresh_catalogs = False
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

        if len(pargs) != 1:
                usage(_("only one image directory path may be specified"),
                    cmd="image-create")
        image_dir = pargs[0]

        if ssl_key:
                # When creating zones, the path is image-root-relative.
                if is_zone:
                        ssl_key = os.path.normpath(image_dir + os.sep + \
                            ssl_key)
                else:
                        ssl_key = os.path.abspath(ssl_key)

        if ssl_cert:
                # When creating zones, the path is image-root-relative.
                if is_zone:
                        ssl_cert = os.path.normpath(image_dir + os.sep + \
                            ssl_cert)
                else:
                        ssl_cert = os.path.abspath(ssl_cert)

        if not pub_name and not origins:
                usage(_("a publisher must be specified"), cmd="image-create")

        if not pub_name or not origins:
                usage(_("publisher argument must be of the form "
                    "'<prefix>=<url>'."), cmd="image-create")

        if pub_name.startswith(fmri.PREF_PUB_PFX):
                error(_("a publisher's prefix may not start with the text: %s"
                        % fmri.PREF_PUB_PFX), cmd="image-create")
                return EXIT_OOPS

        if not misc.valid_pub_prefix(pub_name):
                error(_("publisher prefix contains invalid characters"),
                    cmd="image-create")
                return EXIT_OOPS

        global __img
        try:
                progtrack = get_tracker()
                __img = img = image.Image(root=image_dir, imgtype=imgtype,
                    should_exist=False, progtrack=progtrack, force=force)
                img.set_attrs(is_zone, pub_name, facets=facets,
                    origins=origins, ssl_key=ssl_key, ssl_cert=ssl_cert,
                    refresh_allowed=refresh_catalogs, progtrack=progtrack,
                    variants=variants, mirrors=mirrors)
                img.cleanup_downloads()
        except OSError, e:
                # Ensure messages are displayed after the spinner.
                img.cleanup_downloads()
                logger.error("\n")
                error(_("cannot create image at %(image_dir)s: %(reason)s") %
                    { "image_dir": image_dir, "reason": e.args[1] },
                    cmd="image-create")
                return EXIT_OOPS
        except api_errors.PublisherError, e:
                error(e, cmd="image-create")
                return EXIT_OOPS
        except api_errors.PermissionsException, e:
                # Ensure messages are displayed after the spinner.
                img.cleanup_downloads()
                logger.error("")
                error(e, cmd="image-create")
                return EXIT_OOPS
        except api_errors.InvalidDepotResponseException, e:
                # Ensure messages are displayed after the spinner.
                img.cleanup_downloads()
                logger.error("\n")
                error(_("The URI '%(pub_url)s' does not appear to point to a "
                    "valid pkg server.\nPlease check the server's "
                    "address and client's network configuration."
                    "\nAdditional details:\n\n%(error)s") %
                    { "pub_url": pub_url, "error": e },
                    cmd="image-create")
                print_proxy_config()
                return EXIT_OOPS
        except api_errors.CatalogRefreshException, cre:
                # Ensure messages are displayed after the spinner.
                img.cleanup_downloads()
                error("", cmd="image-create")
                if display_catalog_failures(cre) == 0:
                        return EXIT_OOPS
                else:
                        return EXIT_PARTIAL
        except api_errors.ImageCreationException, e:
                error(e, cmd="image-create")
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

        opts, pargs = getopt.getopt(args, "Hl")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                elif opt == "-l":
                        long_format = True

        if omit_headers and long_format:
                usage(_("-H and -l may not be combined"), cmd="history")

        if not long_format:
                if not omit_headers:
                        msg("%-19s %-25s %-15s %s" % (_("TIME"),
                            _("OPERATION"), _("CLIENT"), _("OUTCOME")))

        if not os.path.exists(img.history.path):
                # Nothing to display.
                return EXIT_OK

        for entry in sorted(os.listdir(img.history.path)):
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

def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        global __img

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
                        try:
                                provided_image_dir = False
                                mydir = os.getcwd()
                        except OSError, e:
                                try:
                                        mydir = os.environ["PWD"]
                                        if not mydir or mydir[0] != "/":
                                                mydir = None
                                except KeyError:
                                        mydir = None

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
        except api_errors.TransportError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                logger.error(_("\nErrors were encountered while attempting "
                    "to retrieve package or file data for\nthe requested "
                    "operation."))
                logger.error(_("Details follow:\n\n%s") % __e)
                print_proxy_config()
                __ret = EXIT_OOPS
        except api_errors.InvalidDepotResponseException, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                logger.error(_("\nUnable to contact a valid package depot. "
                    "This may be due to a problem with the server, "
                    "network misconfiguration, or an incorrect pkg client "
                    "configuration.  Please check your network settings and "
                    "attempt to contact the server using a web browser."))
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
                error(_("The pkg command appears out of sync with the "
                    "libraries provided \nby SUNWipkg. The client version is "
                    "%(client)s while the library API version is %(api)s") %
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
        __retval = handle_errors(main_func)
        try:
                logging.shutdown()
        except IOError:
                # Ignore python's spurious pipe problems.
                pass
        sys.exit(__retval)
