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
import os
import socket
import sys
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

from pkg.client import global_settings
from pkg.client.debugvalues import DebugValues
from pkg.client.history import (RESULT_CANCELED, RESULT_FAILED_BAD_REQUEST,
    RESULT_FAILED_CONFIGURATION, RESULT_FAILED_TRANSPORT, RESULT_FAILED_UNKNOWN,
    RESULT_FAILED_OUTOFMEMORY)
from pkg.misc import EmptyI, msg, emsg, PipeError

CLIENT_API_VERSION = 19
PKG_CLIENT_NAME = "pkg"

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
        emsg(ws + pkg_cmd + text_nows)

def usage(usage_error=None, cmd=None, retcode=2, full=False):
        """Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        if usage_error:
                error(usage_error, cmd=cmd)

        if not full:
                # The full usage message isn't desired.
                emsg(_("Try `pkg --help or -?' for more information."))
                sys.exit(retcode)

        emsg(_("""\
Usage:
        pkg [options] command [cmd_options] [operands]

Basic subcommands:
        pkg install [-nvq] [--no-refresh] [--no-index] package...
        pkg uninstall [-nrvq] [--no-index] package...
        pkg list [-Hafsuv] [--no-refresh] [package...]
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
            (-p|--publisher) name=uri dir
        pkg change-variant [-nvq] [--be-name name] <variant_spec>=<instance>
            [<variant_spec>=<instance> ...]

        pkg set-property propname propvalue
        pkg unset-property propname ...
        pkg property [-H] [propname ...]

        pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert]
            [-O origin_uri] [-m mirror_to_add | --add-mirror=mirror_to_add]
            [-M mirror_to_remove | --remove-mirror=mirror_to_remove]
            [--enable] [--disable] [--no-refresh] [--reset-uuid] publisher
        pkg unset-publisher publisher ...
        pkg publisher [-HPa] [publisher ...]
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

        all_known = False
        all_versions = True
        display_headers = True
        refresh_catalogs = True
        summary = False
        upgradable_only = False
        verbose = False

        opts, pargs = getopt.getopt(args, "Hafsuv", ["no-refresh"])

        for opt, arg in opts:
                if opt == "-a":
                        all_known = True
                elif opt == "-H":
                        display_headers = False
                elif opt == "-s":
                        summary = True
                elif opt == "-u":
                        upgradable_only = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-f":
                        all_versions = False
                elif opt == "--no-refresh":
                        refresh_catalogs = False

        if summary and verbose:
                usage(_("-s and -v may not be combined"), cmd="list")

        if verbose:
                fmt_str = "%-64s %-10s %s"
        elif summary:
                fmt_str = "%-30s %s"
        else:
                fmt_str = "%-45s %-15s %-10s %s"

        if not check_fmri_args(pargs):
                return 1

        img.history.operation_name = "list"
        img.load_catalogs(progress.NullProgressTracker())

        api_inst = api.ImageInterface(img.get_root(), CLIENT_API_VERSION,
            get_tracker(quiet=True), None, PKG_CLIENT_NAME)
        info_needed = frozenset([api.PackageInfo.SUMMARY])

        seen_one_pkg = False
        found = False
        try:
                if all_known and refresh_catalogs:
                        # If the user requested all known packages, ensure that
                        # a publisher metadata refresh is performed if needed
                        # since the catalog may be out of date or invalid as
                        # a result of publisher information changing (such as
                        # an origin uri, etc.).
                        tracker = get_tracker(quiet=not display_headers)
                        try:
                                img.refresh_publishers(progtrack=tracker)
                        except KeyboardInterrupt:
                                raise
                        except:
                                # Ignore the above error and just use what
                                # already exists.
                                pass

                res = misc.get_inventory_list(img, pargs,
                    all_known, all_versions)
                prev_pfmri_str = ""
                prev_state = None
                for pfmri, state in res:
                        if all_versions and prev_pfmri_str and \
                            prev_pfmri_str == pfmri.get_short_fmri() and \
                            prev_state == state:
                                continue
                        prev_pfmri_str = pfmri.get_short_fmri()
                        prev_state = state
                        seen_one_pkg = True
                        if upgradable_only and not state["upgradable"]:
                                continue

                        if not found:
                                if display_headers:
                                        if verbose:
                                                msg(fmt_str % \
                                                    ("FMRI", "STATE", "UFIX"))
                                        elif summary:
                                                msg(fmt_str % \
                                                    ("NAME (PUBLISHER)",
                                                    "SUMMARY"))
                                        else:
                                                msg(fmt_str % \
                                                    ("NAME (PUBLISHER)",
                                                    "VERSION", "STATE", "UFIX"))
                                found = True
                        ufix = "%c%c%c%c" % \
                            (state["upgradable"] and "u" or "-",
                            state["frozen"] and "f" or "-",
                            state["incorporated"] and "i" or "-",
                            state["excludes"] and "x" or "-")

                        if pfmri.preferred_publisher():
                                pub = ""
                        else:
                                pub = " (" + pfmri.get_publisher() + ")"

                        if verbose:
                                pf = pfmri.get_fmri(
                                    img.get_preferred_publisher())
                                msg("%-64s %-10s %s" % (pf, state["state"],
                                    ufix))
                        elif summary:
                                pf = pfmri.get_name() + pub

                                try:
                                        ret = api_inst.info([pfmri], False,
                                            info_needed)
                                        pis = ret[api.ImageInterface.INFO_FOUND]
                                except api_errors.ApiException, e:
                                        error(e)
                                        return 1

                                msg(fmt_str % (pf, pis[0].summary))

                        else:
                                pf = pfmri.get_name() + pub
                                msg(fmt_str % (pf, pfmri.get_version(),
                                    state["state"], ufix))

                if not found:
                        if not seen_one_pkg and not all_known:
                                emsg(_("no packages installed"))
                                img.history.operation_result = \
                                    history.RESULT_NOTHING_TO_DO
                                return 1

                        if upgradable_only:
                                if pargs:
                                        emsg(_("No specified packages have " \
                                            "available updates"))
                                else:
                                        emsg(_("No installed packages have " \
                                            "available updates"))
                                img.history.operation_result = \
                                    history.RESULT_NOTHING_TO_DO
                                return 1

                        img.history.operation_result = \
                            history.RESULT_NOTHING_TO_DO
                        return 1

                img.history.operation_result = history.RESULT_SUCCEEDED
                return 0

        except api_errors.InventoryException, e:
                if e.illegal:
                        for i in e.illegal:
                                error(i)
                        img.history.operation_result = \
                            history.RESULT_FAILED_BAD_REQUEST
                        return 1

                if all_known:
                        state = image.PKG_STATE_KNOWN
                else:
                        state = image.PKG_STATE_INSTALLED
                for pat in e.notfound:
                        error(_("no packages matching "
                            "'%(pattern)s' %(state)s") %
                            { "pattern": pat, "state": state })
                img.history.operation_result = history.RESULT_NOTHING_TO_DO
                return 1

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
        img.load_catalogs(progresstracker)
        fmris, notfound, illegals = img.installed_fmris_from_args(args)

        any_errors = False
        repairs = []
        for f in fmris:
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
                success = img.repair(repairs, progresstracker)
                if not success:
                        progresstracker.verify_done()
                        return 1
        progresstracker.verify_done()
        return 0

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
                return 1

        img.load_catalogs(progresstracker)

        fmris, notfound, illegals = img.installed_fmris_from_args(pargs)

        if illegals:
                for i in illegals:
                        emsg(str(i))
                return 1

        any_errors = False

        header = False
        for f in fmris:
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
                        emsg()
                emsg(_("""\
pkg: no packages matching the following patterns you specified are
installed on the system.\n"""))
                for p in notfound:
                        emsg("        %s" % p)
                if fmris:
                        if any_errors:
                                msg2 = "See above for\nverification failures."
                        else:
                                msg2 = "No packages failed\nverification."
                        emsg(_("\nAll other patterns matched installed "
                            "packages.  %s" % msg2))
                any_errors = True

        if any_errors:
                return 1
        return 0

def __api_prepare(operation, api):
        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        # XXX would be nice to kick the progress tracker.
        try:
                api.prepare()
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return False
        except api_errors.FileInUseException, e:
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

def __api_execute_plan(operation, api, raise_ActionExecutionError=True):
        try:
                api.execute_plan()
        except RuntimeError, e:
                error(_("%s failed: %s") % (operation, e))
                return False
        except api_errors.ImageUpdateOnLiveImageException:
                error(_("%s cannot be done on live image") % operation)
                return False
        except api_errors.CorruptedIndexException, e:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE)
                return False
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE)
                return False
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return False
        except api_errors.MainDictParsingException, e:
                error(str(e))
                return False
        except KeyboardInterrupt:
                raise
        except api_errors.BEException, e:
                error(e)
                return False
        except api_errors.WrapSuccessfulIndexingException:
                raise
        except api_errors.ActionExecutionError, e:
                if not raise_ActionExecutionError:
                        return False
                error(_("An unexpected error happened during " \
                    "%s: %s") % (operation, e))
                raise
        except Exception, e:
                error(_("An unexpected error happened during " \
                    "%s: %s") % (operation, e))
                raise
        return True

def __api_alloc(img_dir, quiet):
        progresstracker = get_tracker(quiet)

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progresstracker, cancel_state_callable=None,
                    pkg_client_name=PKG_CLIENT_NAME)
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
                        emsg("  %s" % d)
                return False
        if e_type == api_errors.CatalogRefreshException:
                if display_catalog_failures(e) != 0:
                        raise RuntimeError("Catalog refresh failed during %s." %
                            op)
                if noexecute:
                        return True
                return False
        if e_type == api_errors.BEException:
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

def change_variant(img_dir, args):
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

        variants = dict();
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
                            (op, name));
                variants[name] = value

        api_inst = __api_alloc(img_dir, quiet)
        if api_inst == None:
                return 1

        try:
                stuff_to_do = api_inst.plan_change_variant(variants,
                    noexecute=noexecute, verbose=verbose, be_name=be_name)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return 1

        if not stuff_to_do:
                msg(_("No updates necessary for this image."))
                return 0

        if noexecute:
                return 0


        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        if not __api_prepare("change-variant", api_inst):
                return 1

        ret_code = 0
        if not __api_execute_plan("change-variant", api_inst):
                ret_code = 1

        if bool(os.environ.get("PKG_MIRROR_STATS", False)):
                print_mirror_stats(api_inst)

        return ret_code

def image_update(img_dir, args):
        """Attempt to take all installed packages specified to latest
        version."""

        # XXX Publisher-catalog issues.
        # XXX Are filters appropriate for an image update?
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

        api_inst = __api_alloc(img_dir, quiet)
        if api_inst == None:
                return 1

        try:
                stuff_to_do, opensolaris_image = \
                    api_inst.plan_update_all(sys.argv[0], refresh_catalogs,
                        noexecute, force=force, verbose=verbose,
                        update_index=update_index, be_name=be_name)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return 1

        if not stuff_to_do:
                msg(_("No updates available for this image."))
                return 0

        if noexecute:
                return 0

        if not __api_prepare(op, api_inst):
                return 1

        ret_code = 0
        if not __api_execute_plan(op, api_inst):
                ret_code = 1

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

def install(img_dir, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Publisher-catalog issues.
        op = "install"
        opts, pargs = getopt.getopt(args, "nvf:q", ["no-refresh", "no-index"])

        quiet = noexecute = verbose = False
        refresh_catalogs = update_index = True
        filters = []
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-f":
                        filters += [ arg ]
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
                return 1

        # XXX not sure where this should live
        pkg_list = [ pat.replace("*", ".*").replace("?", ".")
            for pat in pargs ]

        api_inst = __api_alloc(img_dir, quiet)
        if api_inst == None:
                return 1

        try:
                stuff_to_do = api_inst.plan_install(pkg_list, filters,
                    refresh_catalogs, noexecute, verbose=verbose,
                    update_index=update_index)
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return 1

        if not stuff_to_do:
                msg(_("No updates necessary for this image."))
                return 0

        if noexecute:
                return 0

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        if not __api_prepare(op, api_inst):
                return 1

        ret_code = 0
        if not __api_execute_plan(op, api_inst,
            raise_ActionExecutionError=False):
                ret_code = 1

        if bool(os.environ.get("PKG_MIRROR_STATS", False)):
                print_mirror_stats(api_inst)

        return ret_code


def uninstall(img_dir, args):
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
                return 1

        # XXX not sure where this should live
        pkg_list = [ pat.replace("*", ".*").replace("?", ".")
            for pat in pargs ]

        api_inst = __api_alloc(img_dir, quiet)
        if api_inst == None:
                return 1
        try:
                if not api_inst.plan_uninstall(pkg_list, recursive_removal,
                    noexecute, verbose=verbose, update_index=update_index):
                        assert 0
        except:
                if not __api_plan_exception(op, noexecute=noexecute):
                        return 1
        if noexecute:
                return 0

        # Exceptions which happen here are printed in the above level, with
        # or without some extra decoration done here.
        if not __api_prepare(op, api_inst):
                return 1

        ret_code = 0
        if not __api_execute_plan(op, api_inst):
                ret_code = 1

        return ret_code

def freeze(img, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions.  Package must have been in the INSTALLED state."""
        return 0

def unfreeze(img, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""
        return 0

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

def process_v_1_search(tup, first, return_type, pub):
        """Transforms the tuples returned by search v1 into the four column
        output format.

        The "first" parameter is a boolean stating whether this is the first
        time this function has been called.  This controls the printing of the
        header information.

        The "return_type" parameter is an enumeration that describes the type
        of the information that will be converted.

        The type of the "tup" parameter depends on the value of "return_type".
        If "return_type" is action information, "tup" is a three-tuple of the
        fmri name, the match, and a string representation of the action.  In
        the case where "return_type" is package information, "tup" is a one-
        tuple containing the fmri name."""

        if return_type == api.Query.RETURN_ACTIONS:
                try:
                        pfmri, match, action = tup
                except ValueError:
                        error(_("The server returned a malformed result.\n"
                            "The problematic structure:%r") % (tup,))
                        return False
                if first:
                        msg("%-10s %-9s %-25s %s" %
                            ("INDEX", "ACTION", "VALUE", "PACKAGE"))
                try:
                        out1, out2, out3 = __convert_output(action, match)
                except actions.ActionError, e:
                        error(_("The server returned an invalid action.\n%s") %
                            e)
                        return False
                msg("%-10s %-9s %-25s %s" %
                    (out1, out2, out3,
                    fmri.PkgFmri(str(pfmri)).get_short_fmri()))
        else:
                pfmri = tup
                if first:
                        msg("%s" % ("PACKAGE"))
                pub_name = ''
                # If pub is not None, it's either a RepositoryURI or a Publisher
                # object.  If it's a Publisher, it has a prefix.  Otherwise,
                # use the uri.
                if pub is not None and hasattr(pub, "prefix"):
                        pub_name = " (%s)" % pub.prefix
                elif pub is not None and hasattr(pub, "uri"):
                        pub_name = " (%s)" % pub.uri
                msg("%s%s" %
                    (fmri.PkgFmri(str(pfmri)).get_short_fmri(), pub_name))
        return True

def search(img_dir, args):
        """Search for the given query."""

        opts, pargs = getopt.getopt(args, "alprs:I")

        local = remote = case_sensitive = False
        servers = []
        return_actions = True
        for opt, arg in opts:
                if opt == "-a":
                        return_actions = True
                elif opt == "-l":
                        local = True
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
                                        return 1
                        remote = True
                        servers.append({"origin": arg})
                elif opt == "-I":
                        case_sensitive = True

        if not local and not remote:
                remote = True

        if not pargs:
                usage(_("at least one search term must be provided"),
                    cmd="search")

        searches = []

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    get_tracker(), None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1
        try:
                query = [api.Query(" ".join(pargs), case_sensitive,
                    return_actions)]
        except api_errors.BooleanQueryException, e:
                error(e)
                return 1

        first = True
        good_res = False
        bad_res = False

        try:
                if local:
                        searches.append(api_inst.local_search(query))
                if remote:
                        searches.append(api_inst.remote_search(query,
                            servers=servers))

                # By default assume we don't find anything.
                retcode = 1

                for raw_value in itertools.chain(*searches):
                        try:
                                query_num, pub, (v, return_type, tmp) = \
                                    raw_value
                        except ValueError, e:
                                error(_("The server returned a malformed "
                                    "result:%r") % (raw_value,))
                                bad_res = True
                                continue
                        ret = process_v_1_search(tmp, first,
                            return_type, pub)
                        good_res |= ret
                        bad_res |= not ret
                        first = False
        except (api_errors.IncorrectIndexFileHash,
            api_errors.InconsistentIndexException):
                error(_("The search index appears corrupted.  Please "
                    "rebuild the index with 'pkg rebuild-index'."))
                return 1
        except api_errors.ProblematicSearchServers, e:
                error(e)
                bad_res = True
        except api_errors.SlowSearchUsed, e:
                error(e)
        except (api_errors.IncorrectIndexFileHash,
            api_errors.InconsistentIndexException):
                error(_("The search index appears corrupted.  Please "
                    "rebuild the index with 'pkg rebuild-index'."))
                return 1
        except api_errors.ApiException, e:
                error(e)
                return 1
        if good_res and bad_res:
                retcode = 4
        elif bad_res:
                retcode = 1
        elif not first:
                retcode = 0
        return retcode

def info(img_dir, args):
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
                return 1

        err = 0

        api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
            get_tracker(quiet=True), None, PKG_CLIENT_NAME)

        try:
                info_needed = api.PackageInfo.ALL_OPTIONS
                if not display_license:
                        info_needed = api.PackageInfo.ALL_OPTIONS - \
                            frozenset([api.PackageInfo.LICENSES])
                try:
                        ret = api_inst.info(pargs, info_local, info_needed)
                except api_errors.UnrecognizedOptionsToInfo, e:
                        error(e)
                        return 1
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                multi_match = ret[api.ImageInterface.INFO_MULTI_MATCH]

        except api_errors.PermissionsException, e:
                error(e)
                return 1
        except api_errors.NoPackagesInstalledException:
                error(_("no packages installed"))
                return 1

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

                if pi.state == api.PackageInfo.INSTALLED:
                        state = _("Installed")
                elif pi.state == api.PackageInfo.NOT_INSTALLED:
                        state = _("Not installed")
                else:
                        raise RuntimeError("Encountered unknown package "
                            "information state: %d" % pi.state )
                name_str = _("          Name:")
                msg(name_str, pi.pkg_stem)
                msg(_("       Summary:"), pi.summary)
                if pi.category_info_list:
                        verbose = len(pi.category_info_list) > 1
                        msg(_("      Category:"),
                            pi.category_info_list[0].__str__(verbose))
                        if len(pi.category_info_list) > 1:
                                for ci in pi.category_info_list[1:]:
                                        msg(" " * len(name_str),
                                            ci.__str__(verbose))

                msg(_("         State:"), state)

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
                err = 1
                if pis:
                        emsg()
                if info_local:
                        emsg(_("""\
pkg: info: no packages matching the following patterns you specified are
installed on the system.  Try specifying -r to query remotely:"""))
                elif info_remote:
                        emsg(_("""\
pkg: info: no packages matching the following patterns you specified were
found in the catalog.  Try relaxing the patterns, refreshing, and/or
examining the catalogs:"""))
                emsg()
                for p in notfound:
                        emsg("        %s" % p)

        if illegals:
                err = 1
                for i in illegals:
                        emsg(str(i))

        if multi_match:
                err = 1
                for pfmri, matches in multi_match:
                        error(_("'%s' matches multiple packages") % pfmri)
                        for k in matches:
                                emsg("\t%s" % k)

        if no_licenses:
                err = 1
                error(_("no license information could be found for the "
                    "following packages:"))
                for pfmri in no_licenses:
                        emsg("\t%s" % pfmri)

        return err

def display_contents_results(actionlist, attrs, sort_attrs, action_types,
    display_headers):
        """Print results of a "list" operation """

        # widths is a list of tuples of column width and justification.  Start
        # with the widths of the column headers.
        JUST_UNKN = 0
        JUST_LEFT = -1
        JUST_RIGHT = 1
        widths = [ (len(attr) - attr.find(".") - 1, JUST_UNKN)
            for attr in attrs ]
        lines = []

        for manifest, action in actionlist:
                if action_types and action.name not in action_types:
                        continue
                line = []
                for i, attr in enumerate(attrs):
                        just = JUST_UNKN
                        # As a first approximation, numeric attributes
                        # are right justified, non-numerics left.
                        try:
                                int(action.attrs[attr])
                                just = JUST_RIGHT
                        # attribute is non-numeric or is something like
                        # a list.
                        except (ValueError, TypeError):
                                just = JUST_LEFT
                        # attribute isn't in the list, so we don't know
                        # what it might be
                        except KeyError:
                                pass

                        if attr in action.attrs:
                                a = action.attrs[attr]
                        elif attr == "action.name":
                                a = action.name
                                just = JUST_LEFT
                        elif attr == "action.key":
                                a = action.attrs[action.key_attr]
                                just = JUST_LEFT
                        elif attr == "action.raw":
                                a = action
                                just = JUST_LEFT
                        elif attr == "pkg.name":
                                a = manifest.fmri.get_name()
                                just = JUST_LEFT
                        elif attr == "pkg.fmri":
                                a = manifest.fmri
                                just = JUST_LEFT
                        elif attr == "pkg.shortfmri":
                                a = manifest.fmri.get_short_fmri()
                                just = JUST_LEFT
                        elif attr == "pkg.publisher":
                                a = manifest.fmri.get_publisher()
                                just = JUST_LEFT
                        else:
                                a = ""

                        line.append(a)

                        # XXX What to do when a column's justification
                        # changes?
                        if just != JUST_UNKN:
                                widths[i] = \
                                    (max(widths[i][0], len(str(a))), just)

                if line and [l for l in line if str(l) != ""]:
                        lines.append(line)

        sortidx = 0
        for i, attr in enumerate(attrs):
                if attr == sort_attrs[0]:
                        sortidx = i
                        break

        # Sort numeric columns numerically.
        if widths[sortidx][1] == JUST_RIGHT:
                def key_extract(x):
                        try:
                                return int(x[sortidx])
                        except (ValueError, TypeError):
                                return 0
        else:
                key_extract = lambda x: x[sortidx]

        if display_headers:
                headers = []
                for i, attr in enumerate(attrs):
                        headers.append(str(attr.upper()))
                        widths[i] = \
                            (max(widths[i][0], len(attr)), widths[i][1])

                # Now that we know all the widths, multiply them by the
                # justification values to get positive or negative numbers to
                # pass to the %-expander.
                widths = [ e[0] * e[1] for e in widths ]
                fmt = ("%%%ss " * len(widths)) % tuple(widths)

                msg((fmt % tuple(headers)).rstrip())
        else:
                fmt = "%s\t" * len(widths)
                fmt.rstrip("\t")

        for line in sorted(lines, key=key_extract):
                msg((fmt % tuple(line)).rstrip())

def list_contents(img, args):
        """List package contents.

        If no arguments are given, display for all locally installed packages.
        With -H omit headers and use a tab-delimited format; with -o select
        attributes to display; with -s, specify attributes to sort on; with -t,
        specify which action types to list."""

        # XXX Need remote-info option, to request equivalent information
        # from repository.

        opts, pargs = getopt.getopt(args, "Ho:s:t:mfr")

        valid_special_attrs = [ "action.name", "action.key", "action.raw",
            "pkg.name", "pkg.fmri", "pkg.shortfmri", "pkg.publisher",
            "pkg.size", "pkg.csize" ]

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
                return 1

        if display_raw:
                display_headers = False
                attrs = [ "action.raw" ]

                invalid = set(("-H", "-o", "-t")). \
                    intersection(set([x[0] for x in opts]))

                if len(invalid) > 0:
                        usage(_("-m and %s may not be specified at the same "
                            "time") % invalid.pop(), cmd="contents")

        for a in attrs:
                if a.startswith("action.") and not a in valid_special_attrs:
                        usage(_("Invalid attribute '%s'") % a, cmd="contents")

                if a.startswith("pkg.") and not a in valid_special_attrs:
                        usage(_("Invalid attribute '%s'") % a, cmd="contents")

        img.history.operation_name = "contents"
        img.load_catalogs(progress.QuietProgressTracker())

        err = 0

        if local:
                fmris, notfound, illegals = \
                    img.installed_fmris_from_args(pargs)

                if illegals:
                        for i in illegals:
                                emsg(i)
                        img.history.operation_result = \
                            history.RESULT_FAILED_BAD_REQUEST
                        return 1

                if not fmris and not notfound:
                        error(_("no packages installed"))
                        img.history.operation_result = \
                            history.RESULT_NOTHING_TO_DO
                        return 1
        elif remote:
                # Verify validity of certificates before attempting network
                # operations
                try:
                        img.check_cert_validity()
                except (api_errors.CertificateError,
                    api_errors.PermissionsException), e:
                        img.history.log_operation_end(error=e)
                        return 1

                fmris = []
                notfound = []

                # XXX This loop really needs not to be copied from
                # Image.make_install_plan()!
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
                                if m.preferred_publisher():
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
                                fmris.append(pmatch[0])
                        else:
                                fmris.append(npmatch[0])

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

        manifests = ( img.get_manifest(f, all_arch=display_raw) for f in fmris )

        actionlist = [
            (m, a)
            for m in manifests
            for a in m.gen_actions(excludes)
        ]

        if fmris:
                display_contents_results(actionlist, attrs, sort_attrs,
                    action_types, display_headers)

        if notfound:
                err = 1
                if fmris:
                        emsg()
                if local:
                        emsg(_("""\
pkg: contents: no packages matching the following patterns you specified are
installed on the system.  Try specifying -r to query remotely:"""))
                elif remote:
                        emsg(_("""\
pkg: contents: no packages matching the following patterns you specified were
found in the catalog.  Try relaxing the patterns, refreshing, and/or
examining the catalogs:"""))
                emsg()
                for p in notfound:
                        emsg("        %s" % p)
                img.history.operation_result = history.RESULT_NOTHING_TO_DO
        else:
                img.history.operation_result = history.RESULT_SUCCEEDED
        return err

def display_catalog_failures(cre):
        total = cre.total
        succeeded = cre.succeeded

        txt = _("pkg: %s/%s catalogs successfully updated:") % (succeeded,
            total)
        if cre.failed:
                # This ensures that the text gets printed before the errors.
                emsg(txt)
        else:
                msg(txt)

        for pub, err in cre.failed:
                if isinstance(err, urllib2.HTTPError):
                        emsg("   %s: %s - %s" % \
                            (err.filename, err.code, err.msg))
                elif isinstance(err, urllib2.URLError):
                        if err.args[0][0] == 8:
                                emsg("    %s: %s" % \
                                    (urlparse.urlsplit(
                                        pub["origin"])[1].split(":")[0],
                                    err.args[0][1]))
                        else:
                                if isinstance(err.args[0], socket.timeout):
                                        emsg("    %s: %s" % \
                                            (pub["origin"], "timeout"))
                                else:
                                        emsg("    %s: %s" % \
                                            (pub["origin"], err.args[0][1]))
                else:
                        emsg("   ", err)

        if cre.message:
                emsg(cre.message)

        return succeeded

def publisher_refresh(img_dir, args):
        """Update metadata for the image's publishers."""

        # XXX will need to show available content series for each package
        full_refresh = False
        opts, pargs = getopt.getopt(args, "", ["full"])
        for opt, arg in opts:
                if opt == "--full":
                        full_refresh = True

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    get_tracker(), None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

        try:
                # The user explicitly requested this refresh, so set the
                # refresh to occur immediately.
                api_inst.refresh(full_refresh=full_refresh, immediate=True,
                    pubs=pargs)
        except api_errors.PublisherError, e:
                error(e)
                error(_("'pkg publisher' will show a list of publishers."))
                return 1
        except (api_errors.PermissionsException), e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return 1
        except api_errors.CatalogRefreshException, e:
                if display_catalog_failures(e) == 0:
                        return 1
                else:
                        return 3
        else:
                return 0

def publisher_set(img, img_dir, args):
        """pkg set-publisher [-Ped] [-k ssl_key] [-c ssl_cert] [--reset-uuid]
            [-O origin_url] [-m mirror to add] [-M mirror to remove]
            [--enable] [--disable] [--no-refresh] publisher"""

        preferred = False
        ssl_key = None
        ssl_cert = None
        origin_url = None
        reset_uuid = False
        add_mirror = None
        remove_mirror = None
        refresh_catalogs = True
        disable = None

        opts, pargs = getopt.getopt(args, "Pedk:c:O:M:m:",
            ["add-mirror=", "remove-mirror=", "no-refresh", "reset-uuid",
            "enable", "disable"])

        for opt, arg in opts:
                if opt == "-P":
                        preferred = True
                if opt == "-k":
                        ssl_key = arg
                if opt == "-c":
                        ssl_cert = arg
                if opt == "-O":
                        origin_url = arg
                if opt == "-m" or opt == "--add-mirror":
                        add_mirror = arg
                if opt == "-M" or opt == "--remove-mirror":
                        remove_mirror = arg
                if opt == "--no-refresh":
                        refresh_catalogs = False
                if opt == "--reset-uuid":
                        reset_uuid = True
                if opt == "-e" or opt == "--enable":
                        disable = False
                if opt == "-d" or opt == "--disable":
                        disable = True

        if len(pargs) == 0:
                usage(_("requires a publisher name"), cmd="set-publisher")
        elif len(pargs) > 1:
                usage( _("only one publisher name may be specified"),
                    cmd="set-publisher",)

        name = pargs[0]

        if preferred and disable:
                usage(_("the -p and -d options may not be combined"),
                    cmd="set-publisher")

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    get_tracker(), None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir,
                    cmd="set-publisher")
                return 1

        new_pub = False
        try:
                pub = api_inst.get_publisher(prefix=name, alias=name,
                    duplicate=True)
                if reset_uuid:
                        pub.reset_client_uuid()
                repo = pub.selected_repository
        except api_errors.PermissionsException, e:
                error(e, cmd="set-publisher")
                return 1
        except api_errors.UnknownPublisher:
                if not origin_url:
                        error(_("publisher does not exist. Use -O to define "
                            "origin URI for new publisher."),
                            cmd="set-publisher")
                        return 1
                # No pre-existing, so create a new one.
                repo = publisher.Repository()
                pub = publisher.Publisher(name, repositories=[repo])
                new_pub = True

        if disable is not None:
                # Set disabled property only if provided.
                pub.disabled = disable

        if origin_url:
                try:
                        if not repo.origins:
                                # New publisher case.
                                repo.add_origin(origin_url)
                                origin = repo.origins[0]
                        else:
                                origin = repo.origins[0]
                                origin.uri = origin_url

                        # XXX once image configuration supports storing this
                        # information at the uri level, ssl info should be set
                        # here.
                except api_errors.PublisherError, e:
                        error(e, cmd="set-publisher")
                        return 1

        if add_mirror:
                try:
                        # XXX once image configuration supports storing this
                        # information at the uri level, ssl info should be set
                        # here.
                        repo.add_mirror(add_mirror)
                except (api_errors.PublisherError,
                    api_errors.CertificateError), e:
                        error(e, cmd="set-publisher")
                        return 1

        if remove_mirror:
                try:
                        repo.remove_mirror(remove_mirror)
                except api_errors.PublisherError, e:
                        error(e, cmd="set-publisher")
                        return 1

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
                        return 1

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
                return 1
        except api_errors.InvalidDepotResponseException, e:
                error(_("The origin URIs for '%(pubname)s' do not appear to "
                    "point to a valid pkg server.\nPlease check the server's "
                    "address and client's network configuration."
                    "\nAdditional details:\n\n%(details)s") %
                    { "pubname": pub.prefix, "details": e })
                return 1
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception will
                # be printed on the same line as the spinner.
                error("\n" + str(e))
                return 1

        if preferred:
                api_inst.set_preferred_publisher(prefix=pub.prefix)

        return 0

def publisher_unset(img_dir, args):
        """pkg unset-publisher publisher ..."""

        if len(args) == 0:
                usage(_("at least one publisher must be specified"),
                    cmd="unset-publisher")

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    get_tracker(), None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

        errors = []
        for name in args:
                try:
                        api_inst.remove_publisher(prefix=name, alias=name)
                except (api_errors.PermissionsException,
                    api_errors.PublisherError), e:
                        errors.append((name, e))

        retcode = 0
        if errors:
                if len(errors) == len(args):
                        # If the operation failed for every provided publisher
                        # prefix or alias, complete failure occurred.
                        retcode = 1
                else:
                        # If the operation failed for only some of the provided
                        # publisher prefixes or aliases, then partial failure
                        # occurred.
                        retcode = 3

                txt = ""
                for name, err in errors:
                        txt += "\n"
                        txt += _("Removal failed for '%(pub)s': %(msg)s") % {
                            "pub": name, "msg": err }
                        txt += "\n"
                error(txt, cmd="unset-publisher")

        return retcode

def publisher_list(img_dir, args):
        """pkg publishers"""
        omit_headers = False
        preferred_only = False
        inc_disabled = False

        opts, pargs = getopt.getopt(args, "HPa")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                if opt == "-P":
                        preferred_only = True
                if opt == "-a":
                        inc_disabled = True

        progresstracker = get_tracker(True)

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

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

        retcode = 0
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

                for p in pubs:
                        pfx = p.prefix
                        pstatus = ""
                        if not preferred_only and p == pref_pub:
                                pstatus = _("(preferred)")
                        if p.disabled:
                                pstatus = _("(disabled)")

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
                        retcode = 0
                        c = get_cert_info(uri.ssl_cert)
                        msg(_("              SSL Key:"), uri.ssl_key)
                        msg(_("             SSL Cert:"), uri.ssl_cert)

                        if not c:
                                return retcode

                        if c["errors"]:
                                retcode = 1

                        for e in c["errors"]:
                                emsg("\n" + str(e) + "\n")

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
                                        retcode = 3

                        for uri in r.mirrors:
                                msg(_("           Mirror URI:"), uri)
                                rval = display_ssl_info(uri)
                                if rval == 1:
                                        retcode = 3
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
                return 1

        try:
                img.set_property(propname, propvalue)
        except api_errors.PermissionsException, e:
                # Prepend a newline because otherwise the exception
                # will be printed on the same line as the spinner.
                error("\n" + str(e), cmd="set-property")
                return 1
        return 0

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
                        return 1

                try:
                        img.delete_property(p)
                except KeyError:
                        error(_("no such property: %s") % p,
                            cmd="unset-property")
                        return 1
                except api_errors.PermissionsException, e:
                        # Prepend a newline because otherwise the exception
                        # will be printed on the same line as the spinner.
                        error("\n" + str(e), cmd="unset-property")
                        return 1

        return 0

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
                        return 1

        if not pargs:
                pargs = list(img.properties())

        width = max(max([len(p) for p in pargs]), 8)
        fmt = "%%-%ss %%s" % width
        if not omit_headers:
                msg(fmt % ("PROPERTY", "VALUE"))

        for p in pargs:
                msg(fmt % (p, img.get_property(p)))

        return 0

def image_create(img, args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial publisher for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        imgtype = image.IMG_USER
        is_zone = False
        ssl_key = None
        ssl_cert = None
        pub_name = None
        pub_url = None
        refresh_catalogs = True
        force = False
        variants = {}

        opts, pargs = getopt.getopt(args, "fFPUza:p:k:c:",
            ["force", "full", "partial", "user", "zone", "authority=",
                "publisher=", "no-refresh", "variant="])

        for opt, arg in opts:
                if opt == "-f" or opt == "--force":
                        force = True
                if opt == "-F" or opt == "--full":
                        imgtype = imgtypes.IMG_ENTIRE
                if opt == "-P" or opt == "--partial":
                        imgtype = imgtypes.IMG_PARTIAL
                if opt == "-U" or opt == "--user":
                        imgtype = imgtypes.IMG_USER
                if opt == "-z" or opt == "--zone":
                        is_zone = True
                        imgtype = image.IMG_ENTIRE
                if opt == "--no-refresh":
                        refresh_catalogs = False
                if opt == "-k":
                        ssl_key = arg
                if opt == "-c":
                        ssl_cert = arg

                # -a is deprecated and will be removed at a future date.
                if opt in ("-a", "-p", "--publisher"):
                        try:
                                pub_name, pub_url = arg.split("=", 1)
                        except ValueError:
                                usage(_("publisher argument must be of the "
                                    "form '<prefix>=<url>'."),
                                    cmd="image-create")
                if opt == "--variant":
                        try:
                                v_name, v_value = arg.split("=", 1)
                                if not v_name.startswith("variant."):
                                        v_name = "variant.%s" % v_name
                        except ValueError:
                                usage(_("variant arguments must be of the "
                                    "form '<name>=<value>'."),
                                    cmd="image-create")
                        variants[v_name] = v_value

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

        if not pub_name and not pub_url:
                usage(_("a publisher must be specified"), cmd="image-create")

        if not pub_name or not pub_url:
                usage(_("publisher argument must be of the form "
                    "'<prefix>=<url>'."), cmd="image-create")

        if pub_name.startswith(fmri.PREF_PUB_PFX):
                error(_("a publisher's prefix may not start with the text: %s"
                        % fmri.PREF_PUB_PFX), cmd="image-create")
                return 1

        if not misc.valid_pub_prefix(pub_name):
                error(_("publisher prefix contains invalid characters"),
                    cmd="image-create")
                return 1

        # Bail if there is already an image there
        if img.image_type(image_dir) != None and not force:
                error(_("there is already an image at: %s.\nTo override, use "
                    "the -f (force) option.") % image_dir, cmd="image-create")
                return 1

        # Bail if the directory exists but isn't empty
        if os.path.exists(image_dir) and \
            len(os.listdir(image_dir)) > 0 and not force:
                error(_("the specified image path is not empty: %s.\nTo "
                    "override, use the -f (force) option.") % image_dir,
                    cmd="image-create")
                return 1

        try:
                img.set_attrs(imgtype, image_dir, is_zone, pub_name, pub_url,
                    ssl_key=ssl_key, ssl_cert=ssl_cert, variants=variants,
                    refresh_allowed=refresh_catalogs, progtrack=get_tracker())
        except OSError, e:
                # Ensure messages are displayed after the spinner.
                emsg("\n")
                error(_("cannot create image at %(image_dir)s: %(reason)s") %
                    { "image_dir": image_dir, "reason": e.args[1] },
                    cmd="image-create")
                return 1
        except api_errors.PermissionsException, e:
                # Ensure messages are displayed after the spinner.
                emsg("")
                error(e, cmd="image-create")
                return 1
        except api_errors.InvalidDepotResponseException, e:
                # Ensure messages are displayed after the spinner.
                emsg("\n")
                error(_("The URI '%(pub_url)s' does not appear to point to a "
                    "valid pkg server.\nPlease check the server's "
                    "address and client's network configuration."
                    "\nAdditional details:\n\n%(error)s") %
                    { "pub_url": pub_url, "error": e },
                    cmd="image-create")
                print_proxy_config()
                return 1
        except api_errors.CatalogRefreshException, cre:
                # Ensure messages are displayed after the spinner.
                error("", cmd="image-create")
                if display_catalog_failures(cre) == 0:
                        return 1
                else:
                        return 3
        return 0

def rebuild_index(img_dir, pargs):
        """pkg rebuild-index

        Forcibly rebuild the search indexes. Will remove existing indexes
        and build new ones from scratch."""
        quiet = False

        if pargs:
                usage(_("command does not take operands ('%s')") % \
                    " ".join(pargs), cmd="rebuild-index")
        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    get_tracker(quiet), None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir,
                    cmd="rebuild-index")
                return 1

        try:
                api_inst.rebuild_search_index()
        except api_errors.CorruptedIndexException:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE, cmd="rebuild-index")
                return 1
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE,
                    cmd="rebuild-index")
                return 1
        except api_errors.MainDictParsingException, e:
                error(str(e), cmd="rebuild-index")
                return 1
        else:
                return 0

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
                return 0

        for entry in sorted(os.listdir(img.history.path)):
                # Load the history entry.
                try:
                        he = history.History(root_dir=img.history.root_dir,
                            filename=entry)
                except api_errors.PermissionsException, e:
                        error(e, cmd="history")
                        return 1
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

        return 0

def print_proxy_config():
        """If the user has configured http_proxy or https_proxy in the
        environment, print out the values.  Some transport errors are
        not debuggable without this information handy."""

        http_proxy = os.environ.get("http_proxy", None)
        https_proxy = os.environ.get("https_proxy", None)

        if not http_proxy and not https_proxy:
                return

        emsg(_("\nThe following proxy configuration is set in the"
            " environment:\n"))
        if http_proxy:
                emsg(_("http_proxy: %s\n") % http_proxy)
        if https_proxy:
                emsg(_("https_proxy: %s\n") % https_proxy)


# To allow exception handler access to the image.
__img = None

def main_func():
        global_settings.client_name = PKG_CLIENT_NAME

        global __img
        __img = img = image.Image()

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "R:D:?",
                    ["debug=", "help"])
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        show_usage = False
        for opt, arg in opts:
                if opt == "-D" or opt == "--debug":
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
                        ret = image_create(img, pargs)
                except getopt.GetoptError, e:
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
                return 0

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
                return 1

        try:
                img.find_root(mydir, provided_image_dir)
        except api_errors.ImageNotFoundException, e:
                if e.user_specified:
                        m = "No image rooted at '%s'"
                        if pkg_image_used:
                                m += " (set by $PKG_IMAGE)"
                        error(_(m) % e.user_dir)
                else:
                        error(_("No image found."))
                return 1

        try:
                img.load_config()
        except api_errors.ApiException, e:
                error(_("client configuration error: %s") % e)
                return 1

        try:
                if subcommand == "refresh":
                        return publisher_refresh(mydir, pargs)
                elif subcommand == "list":
                        return list_inventory(img, pargs)
                elif subcommand == "image-update":
                        return image_update(mydir, pargs)
                elif subcommand == "change-variant":
                        return change_variant(mydir, pargs)
                elif subcommand == "install":
                        return install(mydir, pargs)
                elif subcommand == "uninstall":
                        return uninstall(mydir, pargs)
                elif subcommand == "freeze":
                        return freeze(img, pargs)
                elif subcommand == "unfreeze":
                        return unfreeze(img, pargs)
                elif subcommand == "search":
                        return search(mydir, pargs)
                elif subcommand == "info":
                        return info(mydir, pargs)
                elif subcommand == "contents":
                        return list_contents(img, pargs)
                elif subcommand == "fix":
                        return fix_image(img, pargs)
                elif subcommand == "verify":
                        return verify_image(img, pargs)
                elif subcommand in ("set-authority", "set-publisher"):
                        return publisher_set(img, mydir, pargs)
                elif subcommand in ("unset-authority", "unset-publisher"):
                        return publisher_unset(mydir, pargs)
                elif subcommand in ("authority", "publisher"):
                        return publisher_list(mydir, pargs)
                elif subcommand == "set-property":
                        return property_set(img, pargs)
                elif subcommand == "unset-property":
                        return property_unset(img, pargs)
                elif subcommand == "property":
                        return property_list(img, pargs)
                elif subcommand == "history":
                        return history_list(img, pargs)
                elif subcommand == "purge-history":
                        ret_code = img.history.purge()
                        if ret_code == 0:
                                msg(_("History purged."))
                        return ret_code
                elif subcommand == "rebuild-index":
                        return rebuild_index(mydir, pargs)
                else:
                        usage(_("unknown subcommand '%s'") % subcommand)

        except getopt.GetoptError, e:
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
                        __ret = 1
        except SystemExit, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_UNKNOWN)
                raise __e
        except (PipeError, KeyboardInterrupt):
                if __img:
                        __img.history.abort(RESULT_CANCELED)
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                __ret = 1
        except api_errors.CertificateError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_CONFIGURATION)
                error(__e)
                __ret = 1
        except api_errors.PublisherError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_BAD_REQUEST)
                error(__e)
                __ret = 1
        except api_errors.TransportError, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                emsg(_("\nErrors were encountered while attempting to retrieve"
                    " package or file data for\nthe requested operation."))
                emsg(_("Details follow:\n\n%s") % __e)
                print_proxy_config()
                __ret = 1
        except api_errors.InvalidDepotResponseException, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                emsg(_("\nUnable to contact a valid package depot. "
                    "This may be due to a problem with the server, "
                    "network misconfiguration, or an incorrect pkg client "
                    "configuration.  Please check your network settings and "
                    "attempt to contact the server using a web browser."))
                emsg(_("\nAdditional details:\n\n%s") % __e)
                print_proxy_config()
                __ret = 1
        except history.HistoryLoadException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if __img:
                        __img.history.clear()
                error(_("An error was encountered while attempting to load "
                    "history information\nabout past client operations."))
                error(__e)
                __ret = 1
        except history.HistoryStoreException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if __img:
                        __img.history.clear()
                error(_("An error was encountered while attempting to store "
                    "information about the\ncurrent operation in client "
                    "history."))
                error(__e)
                __ret = 1
        except history.HistoryPurgeException, __e:
                # Since a history related error occurred, discard all
                # information about the current operation(s) in progress.
                if __img:
                        __img.history.clear()
                error(_("An error was encountered while attempting to purge "
                    "client history."))
                error(__e)
                __ret = 1
        except api_errors.VersionException, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_UNKNOWN)
                error(_("The pkg command appears out of sync with the "
                    "libraries provided \nby SUNWipkg. The client version is "
                    "%(client)s while the library API version is %(api)s") %
                    {'client': __e.received_version,
                     'api': __e.expected_version
                    })
                __ret = 1
        except api_errors.WrapSuccessfulIndexingException, __e:
                __ret = 0
        except api_errors.WrapIndexingException, __e:
                def func():
                        raise __e.wrapped
                __ret = handle_errors(func, non_wrap_print=False)
                s = ""
                if __ret == 99:
                        s += _("\n%s%s") % (__e, traceback_str)

                s += _("\n\nDespite the error while indexing, the "
                    "image-update, install, or uninstall\nhas completed "
                    "successfuly.")
                error(s)
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
        __ret = handle_errors(main_func)
        sys.exit(__ret)
