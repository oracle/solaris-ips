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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
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

import getopt
import gettext
import itertools
import os
import socket
import sys
import traceback
import urllib2
import urlparse
import datetime
import time
import calendar

import OpenSSL.crypto

import pkg.client.image as image
import pkg.client.filelist as filelist
import pkg.client.progress as progress
import pkg.client.history as history
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.search_errors as search_errors
import pkg.fmri as fmri
import pkg.misc as misc
from pkg.misc import msg, emsg, PipeError
import pkg.version
import pkg.Uuid25
import pkg

from pkg.client.history import RESULT_FAILED_UNKNOWN
from pkg.client.history import RESULT_CANCELED
from pkg.client.history import RESULT_FAILED_TRANSPORT
from pkg.client.history import RESULT_SUCCEEDED
from pkg.client.history import RESULT_FAILED_SEARCH
from pkg.client.history import RESULT_FAILED_STORAGE
from pkg.client.retrieve import ManifestRetrievalError
from pkg.client.retrieve import DatastreamRetrievalError

CLIENT_API_VERSION = 0
PKG_CLIENT_NAME = "pkg"

def error(text):
        """Emit an error message prefixed by the command name """

        # If we get passed something like an Exception, we can convert it
        # down to a string.
        text = str(text)
        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + "pkg: " + text_nows)

def usage(usage_error = None):
        """Emit a usage message and optionally prefix it with a more
            specific error message.  Causes program to exit. """

        if usage_error:
                error(usage_error)

        emsg(_("""\
Usage:
        pkg [options] command [cmd_options] [operands]

Basic subcommands:
        pkg install [-nvq] package...
        pkg uninstall [-nrvq] package...
        pkg list [-aHsuv] [package...]
        pkg image-update [-nvq]
        pkg refresh [--full]
        pkg version
        pkg help

Advanced subcommands:
        pkg info [-lr] [--license] [pkg_fmri_pattern ...]
        pkg search [-lrI] [-s server] token
        pkg verify [-fHqv] [pkg_fmri_pattern ...]
        pkg contents [-Hmr] [-o attribute ...] [-s sort_key] [-t action_type ... ]
            pkg_fmri_pattern [...]
        pkg image-create [-FPUz] [--full|--partial|--user] [--zone]
            [-k ssl_key] [-c ssl_cert] -a <prefix>=<url> dir

        pkg set-property propname propvalue
        pkg unset-property propname ...
        pkg property [-H] [propname ...]

        pkg set-authority [-P] [-k ssl_key] [-c ssl_cert] [--reset-uuid]
            [-O origin_url] [-m mirror to add | --add-mirror=mirror to add]
            [-M mirror to remove | --remove-mirror=mirror to remove] authority
        pkg unset-authority authority ...
        pkg authority [-HP] [authname]
        pkg history [-Hl]
        pkg purge-history
        pkg rebuild-index

Options:
        -R dir

Environment:
        PKG_IMAGE"""))
        sys.exit(2)

# XXX Subcommands to implement:
#        pkg image-set name value
#        pkg image-unset name
#        pkg image-get [name ...]

INCONSISTENT_INDEX_ERROR_MESSAGE = "The search index appears corrupted.  " + \
    "Please rebuild the index with 'pkg rebuild-index'."

PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE = " (Failure of consistent use " + \
    "of pfexec when running pkg commands is often a source of this problem.)"

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
        all_known = False
        display_headers = True
        upgradable_only = False
        verbose = False
        summary = False

        opts, pargs = getopt.getopt(args, "aHsuv")

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

        if summary and verbose:
                usage(_("-s and -v may not be combined"))

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

        seen_one_pkg = False
        found = False
        try:
                for pfmri, state in img.inventory(pargs, all_known):
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
                                                    ("NAME (AUTHORITY)",
                                                    "SUMMARY"))
                                        else:
                                                msg(fmt_str % \
                                                    ("NAME (AUTHORITY)",
                                                    "VERSION", "STATE", "UFIX"))
                                found = True

                        ufix = "%c%c%c%c" % \
                            (state["upgradable"] and "u" or "-",
                            state["frozen"] and "f" or "-",
                            state["incorporated"] and "i" or "-",
                            state["excludes"] and "x" or "-")

                        if pfmri.preferred_authority():
                                auth = ""
                        else:
                                auth = " (" + pfmri.get_authority() + ")"

                        if verbose:
                                pf = pfmri.get_fmri(img.get_default_authority())
                                msg("%-64s %-10s %s" % (pf, state["state"],
                                    ufix))
                        elif summary:
                                pf = pfmri.get_name() + auth

                                m = img.get_manifest(pfmri, filtered=True)
                                msg(fmt_str % (pf, m.get("description", "")))

                        else:
                                pf = pfmri.get_name() + auth
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
                        error(_("no packages matching '%s' %s") % (pat, state))
                img.history.operation_result = history.RESULT_NOTHING_TO_DO
                return 1

def get_tracker(quiet = False):
        if quiet:
                progresstracker = progress.QuietProgressTracker()
        else:
                try:
                        progresstracker = \
                            progress.FancyUNIXProgressTracker()
                except progress.ProgressTrackerException:
                        progresstracker = progress.CommandLineProgressTracker()
        return progresstracker

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
                usage(_("verify: -v and -q may not be combined"))

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
                                msg("\t%s" % err[0])
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

def image_update(img_dir, args):
        """Attempt to take all installed packages specified to latest
        version."""

        # XXX Authority-catalog issues.
        # XXX Are filters appropriate for an image update?
        # XXX Leaf package refinements.

        opts, pargs = getopt.getopt(args, "b:fnvq", ["no-refresh"])

        force = quiet = noexecute = verbose = False
        refresh_catalogs = True
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxbytes_default = int(arg)
                elif opt == "-q":
                        quiet = True
                elif opt == "-f":
                        force = True
                elif opt == "--no-refresh":
                        refresh_catalogs = False

        if verbose and quiet:
                usage(_("image-update: -v and -q may not be combined"))

        if pargs:
                usage(_("image-update: command does not take operands " \
                    "('%s')") % " ".join(pargs))

        progresstracker = get_tracker(quiet)

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progresstracker, cancel_state_callable=None,
                    pkg_client_name=PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("No image rooted at '%s'") % e.user_dir)
                return 1

        try:
                # cre is either None or a catalog refresh exception which was
                # caught while planning.
                stuff_to_do, opensolaris_image, cre = \
                    api_inst.plan_update_all(sys.argv[0], refresh_catalogs,
                        noexecute, force=force, verbose=verbose)
                if cre and not display_catalog_failures(cre):
                        raise RuntimeError("Catalog refresh failed during"
                            " image-update.")
                if not stuff_to_do:
                        msg(_("No updates available for this image."))
                        return 0
        except api_errors.CatalogRefreshException, e:
                if display_catalog_failures(e) == 0:
                        if not noexecute:
                                return 1
                else:
                        raise RuntimeError("Catalog refresh failed during"
                            " image-update.")
        except (api_errors.PlanCreationException,
            api_errors.NetworkUnavailableException), e:
                msg(str(e))
                return 1
        except api_errors.IpkgOutOfDateException:
                msg(_("WARNING: pkg(5) appears to be out of date, and should " \
                    "be updated before\nrunning image-update.\n"))
                msg(_("Please update pkg(5) using 'pfexec pkg install " \
                    "SUNWipkg' and then retry\nthe image-update."))
                return 1
        except api_errors.ImageNotFoundException, e:
                error(_("No image rooted at '%s'") % e.user_dir)
                return 1
        if noexecute:
                return 0

        ret_code = 0
        
        try:
                api_inst.prepare()
        except KeyboardInterrupt:
                raise
        except:
                error(_("\nAn unexpected error happened while preparing for " \
                    "image-update:"))
                raise

        try:
                api_inst.execute_plan()
        except RuntimeError, e:
                error(_("image-update failed: %s") % e)
                ret_code = 1
        except api_errors.ImageUpdateOnLiveImageException:
                error(_("image-update cannot be done on live image"))
                ret_code = 1
        except api_errors.CorruptedIndexException, e:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE)
                ret_code = 1
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE)
                ret_code = 1
        except Exception, e:
                error(_("\nAn unexpected error happened during " \
                    "image-update: %s") % e)
                raise

        if ret_code == 0 and opensolaris_image:
                msg("\n" + "-" * 75)
                msg(_("NOTE: Please review release notes posted at:\n" \
                    "   http://opensolaris.org/os/project/indiana/" \
                    "resources/rn3/"))
                msg("-" * 75 + "\n")

        return ret_code

def install(img_dir, args):
        """Attempt to take package specified to INSTALLED state.  The operands
        are interpreted as glob patterns."""

        # XXX Authority-catalog issues.

        opts, pargs = getopt.getopt(args, "nvb:f:q", ["no-refresh"])

        quiet = noexecute = verbose = False
        refresh_catalogs = True
        filters = []
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-b":
                        filelist.FileList.maxbytes_default = int(arg)
                elif opt == "-f":
                        filters += [ arg ]
                elif opt == "-q":
                        quiet = True
                elif opt == "--no-refresh":
                        refresh_catalogs = False

        if not pargs:
                usage(_("install: at least one package name required"))

        if verbose and quiet:
                usage(_("install: -v and -q may not be combined"))

        progresstracker = get_tracker(quiet)

        if not check_fmri_args(pargs):
                return 1
        
        # XXX not sure where this should live
        pkg_list = [ pat.replace("*", ".*").replace("?", ".")
            for pat in pargs ]

        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

        try:
                if not api_inst.plan_install(pkg_list, filters,
                    refresh_catalogs, noexecute, verbose=verbose):
                        msg(_("Nothing to install in this image (is this "
                            "package already installed?)"))
                        return 0
        except api_errors.InvalidCertException:
                return 1
        except (api_errors.PlanCreationException,
            api_errors.NetworkUnavailableException), e:
                msg(str(e))
                return 1
        except api_errors.InventoryException, e:
                error(_("install failed (inventory exception): %s") % e)
                return 1
        except fmri.IllegalFmri, e:
                error(e)
                return 1



        if noexecute:
                return 0

        try:
                api_inst.prepare()
        except Exception, e:
                error(_("\nAn unexpected error happened while preparing for " \
                    "install:"))
                raise

        ret_code = 0
        
        try:
                api_inst.execute_plan()
        except RuntimeError, e:
                error(_("installation failed: %s") % e)
                ret_code = 1
        except api_errors.CorruptedIndexException, e:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE)
                ret_code = 1
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE)
                ret_code = 1
        except Exception, e:
                error(_("An unexpected error happened during " \
                    "installation: %s") % e)
                raise

        return ret_code


def uninstall(img_dir, args):
        """Attempt to take package specified to DELETED state."""

        opts, pargs = getopt.getopt(args, "nrvq")

        quiet = noexecute = recursive_removal = verbose = False
        for opt, arg in opts:
                if opt == "-n":
                        noexecute = True
                elif opt == "-r":
                        recursive_removal = True
                elif opt == "-v":
                        verbose = True
                elif opt == "-q":
                        quiet = True

        if not pargs:
                usage(_("uninstall: at least one package name required"))

        if verbose and quiet:
                usage(_("uninstall: -v and -q may not be combined"))

        progresstracker = get_tracker(quiet)

        if not check_fmri_args(pargs):
                return 1

        # XXX not sure where this should live
        pkg_list = [ pat.replace("*", ".*").replace("?", ".")
            for pat in pargs ]
        
        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

        try:
                if not api_inst.plan_uninstall(pkg_list, recursive_removal,
                    noexecute, verbose=verbose):
                        assert 0
        except api_errors.NonLeafPackageException, e:
                error("""Cannot remove '%s' due to
the following packages that depend on it:""" % e[0])
                for d in e[1]:
                        emsg("  %s" % d)
                return 1
        except (api_errors.PlanCreationException,
            api_errors.NetworkUnavailableException), e:
                msg(str(e))
                return 1


        if noexecute:
                return 0

        try:
                api_inst.prepare()
        except Exception, e:
                error(_("\nAn unexpected error happened while preparing for " \
                    "uninstall:"))
                raise

        ret_code = 0
        
        try:
                api_inst.execute_plan()
        except RuntimeError, e:
                error(_("uninstallation failed: %s") % e)
                ret_code = 1
        except api_errors.CorruptedIndexException, e:
                error(INCONSISTENT_INDEX_ERROR_MESSAGE)
                ret_code = 1
        except api_errors.ProblematicPermissionsIndexException, e:
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE)
                ret_code = 1
        except Exception, e:
                error(_("An unexpected error happened during " \
                    "uninstallation: %s") % e)
                raise

        return ret_code

def freeze(img, args):
        """Attempt to take package specified to FROZEN state, with given
        restrictions.  Package must have been in the INSTALLED state."""
        return 0

def unfreeze(img, args):
        """Attempt to return package specified to INSTALLED state from FROZEN
        state."""
        return 0

def search(img, args):
        """Search through the reverse index databases for the given token."""

        # Verify validity of certificates before attempting network operations
        if not img.check_cert_validity():
                return 1

        opts, pargs = getopt.getopt(args, "lrs:I")

        local = remote = case_sensitive = False
        servers = []
        for opt, arg in opts:
                if opt == "-l":
                        local = True
                elif opt == "-r":
                        remote = True
                elif opt == "-s":
                        if not arg.startswith("http://") and \
                            not arg.startswith("https://"):
                                arg = "http://" + arg
                        remote = True
                        servers.append({"origin": arg})
                elif opt == "-I":
                        case_sensitive = True

        if not local and not remote:
                local = True

        if remote and case_sensitive:
                emsg("Case sensitive remote search not currently supported.")
                usage()

        if not pargs:
                usage()

        searches = []
        if local:
                try:
                        searches.append(img.local_search(pargs, case_sensitive))
                except (search_errors.InconsistentIndexException,
                        search_errors.IncorrectIndexFileHash):
                        error("The search index appears corrupted.  Please "
                            "rebuild the index with 'pkg rebuild-index'.")
                        return 1

        if remote:
                searches.append(img.remote_search(pargs, servers))

        # By default assume we don't find anything.
        retcode = 1

        try:
                first = True
                for index, mfmri, action, value in itertools.chain(*searches):
                        retcode = 0
                        if first:
                                if action and value:
                                        msg("%-10s %-9s %-25s %s" % ("INDEX",
                                            "ACTION", "VALUE", "PACKAGE"))
                                else:
                                        msg("%-10s %s" % ("INDEX", "PACKAGE"))
                                first = False
                        if action and value:
                                msg("%-10s %-9s %-25s %s" % (index, action,
                                    value, fmri.PkgFmri(str(mfmri)
                                    ).get_short_fmri()))
                        else:
                                msg("%-10s %s" % (index, mfmri))

        except RuntimeError, failed:
                emsg("Some servers failed to respond:")
                for auth, err in failed.args[0]:
                        if isinstance(err, urllib2.HTTPError):
                                emsg("    %s: %s (%d)" % \
                                    (auth["origin"], err.msg, err.code))
                        elif isinstance(err, urllib2.URLError):
                                if isinstance(err.args[0], socket.timeout):
                                        emsg("    %s: %s" % \
                                            (auth["origin"], "timeout"))
                                else:
                                        emsg("    %s: %s" % \
                                            (auth["origin"], err.args[0][1]))

                retcode = 4

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
                usage(_("info: -l and -r may not be combined"))

        if info_remote and not pargs:
                usage(_("info: must request remote info for specific packages"))

        if not check_fmri_args(pargs):
                return 1

        err = 0

        api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
            progress.NullProgressTracker(), None, PKG_CLIENT_NAME)

        try:
                ret = api_inst.info(pargs, info_local, display_license)
                pis = ret[api.ImageInterface.INFO_FOUND]
                notfound = ret[api.ImageInterface.INFO_MISSING]
                illegals = ret[api.ImageInterface.INFO_ILLEGALS]
                multi_match = ret[api.ImageInterface.INFO_MULTI_MATCH]
                
        except api_errors.NoPackagesInstalledException:
                error(_("no packages installed"))
                return 1

        for i, pi in enumerate(pis):
                if i > 0:
                        msg("")

                if display_license:
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
                
                msg("          Name:", pi.pkg_stem)
                msg("       Summary:", pi.summary)
                msg("         State:", state)

                # XXX even more info on the authority would be nice?
                msg("     Authority:", pi.authority)
                msg("       Version:", pi.version)
                msg(" Build Release:", pi.build_release)
                msg("        Branch:", pi.branch)
                msg("Packaging Date:", pi.packaging_date)
                msg("          Size: %s", misc.bytes_to_str(pi.size))
                msg("          FMRI:", pi.fmri)
                # XXX add license/copyright info here?

        if notfound:
                err = 1
                if pis:
                        emsg()
                if info_local:
                        emsg(_("""\
pkg: no packages matching the following patterns you specified are
installed on the system.  Try specifying -r to query remotely:"""))
                elif info_remote:
                        emsg(_("""\
pkg: no packages matching the following patterns you specified were
found in the catalog.  Try relaxing the patterns, refreshing, and/or
examining the catalogs:"""))
                emsg()
                for p in notfound:
                        emsg("        %s" % p)

        if illegals:
                for i in illegals:
                        emsg(str(i))
                err = 1

        if multi_match:
                err = 1
                for pfmri, matches in  multi_match:
                        error(_("'%s' matches multiple packages") % pfmri)
                        for k in matches:
                                msg("\t%s" % k[0])
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
                        elif attr == "pkg.authority":
                                a = manifest.fmri.get_authority()
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
            "pkg.name", "pkg.fmri", "pkg.shortfmri", "pkg.authority",
            "pkg.size" ]

        display_headers = True
        display_raw = False
        display_nofilters = False
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
                elif opt == "-f":
                        # Undocumented, for now.
                        display_nofilters = True

        if not remote and not local:
                local = True
        elif local and remote:
                usage(_("contents: -l and -r may not be combined"))

        if remote and not pargs:
                usage(_("contents: must request remote contents for specific "
                   "packages"))

        if not check_fmri_args(pargs):
                return 1

        if display_raw:
                display_headers = False
                attrs = [ "action.raw" ]

                invalid = set(("-H", "-o", "-t")). \
                    intersection(set([x[0] for x in opts]))

                if len(invalid) > 0:
                        usage(_("contents: -m and %s may not be specified " \
                            "at the same time") % invalid.pop())

        for a in attrs:
                if a.startswith("action.") and not a in valid_special_attrs:
                        usage(_("Invalid attribute '%s'") % a)

                if a.startswith("pkg.") and not a in valid_special_attrs:
                        usage(_("Invalid attribute '%s'") % a)

        img.history.operation_name = "contents"
        img.load_catalogs(progress.NullProgressTracker())

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
                if not img.check_cert_validity():
                        img.history.operation_result = \
                            history.RESULT_FAILED_TRANSPORT
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
                                if m.preferred_authority():
                                        pnames[m.get_pkg_stem()] = 1
                                        pmatch.append(m)
                                else:
                                        npnames[m.get_pkg_stem()] = 1
                                        npmatch.append(m)

                        if len(pnames.keys()) > 1:
                                msg(_("pkg: '%s' matches multiple packages") % \
                                    p)
                                for k in pnames.keys():
                                        msg("\t%s" % k)
                                continue
                        elif len(pnames.keys()) < 1 and len(npnames.keys()) > 1:
                                msg(_("pkg: '%s' matches multiple packages") % \
                                    p)
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

        filt = not display_nofilters
        manifests = ( img.get_manifest(f, filtered=filt) for f in fmris )

        actionlist = [ (m, a)
                    for m in manifests
                    for a in m.actions ]

        if fmris:
                display_contents_results(actionlist, attrs, sort_attrs,
                    action_types, display_headers)

        if notfound:
                err = 1
                if fmris:
                        emsg()
                if local:
                        emsg(_("""\
pkg: no packages matching the following patterns you specified are
installed on the system.  Try specifying -r to query remotely:"""))
                elif remote:
                        emsg(_("""\
pkg: no packages matching the following patterns you specified were
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
        msg(_("pkg: %s/%s catalogs successfully updated:") % (succeeded, total))

        for auth, err in cre.failed:
                if isinstance(err, urllib2.HTTPError):
                        emsg("   %s: %s - %s" % \
                            (err.filename, err.code, err.msg))
                elif isinstance(err, urllib2.URLError):
                        if err.args[0][0] == 8:
                                emsg("    %s: %s" % \
                                    (urlparse.urlsplit(
                                        auth["origin"])[1].split(":")[0],
                                    err.args[0][1]))
                        else:
                                if isinstance(err.args[0], socket.timeout):
                                        emsg("    %s: %s" % \
                                            (auth["origin"], "timeout"))
                                else:
                                        emsg("    %s: %s" % \
                                            (auth["origin"], err.args[0][1]))
                else:
                        emsg("   ", err)

        if cre.message:
                emsg(cre.message)
                        
        return succeeded

def catalog_refresh(img_dir, args):
        """Update image's catalogs."""

        # XXX will need to show available content series for each package
        full_refresh = False
        opts, pargs = getopt.getopt(args, "", ["full"])
        for opt, arg in opts:
                if opt == "--full":
                        full_refresh = True

        progresstracker = get_tracker(True)
                        
        try:
                api_inst = api.ImageInterface(img_dir, CLIENT_API_VERSION,
                    progresstracker, None, PKG_CLIENT_NAME)
        except api_errors.ImageNotFoundException, e:
                error(_("'%s' is not an install image") % e.user_dir)
                return 1

        try:
                api_inst.refresh(full_refresh, pargs)
        except api_errors.UnrecognizedAuthorityException, e:
                tmp = _("%s is not a recognized authority to " \
                    "refresh. \n'pkg authority' will show a" \
                    " list of authorities.")
                error(tmp % e.auth)
                return 1
        except api_errors.CatalogRefreshException, e:
                if display_catalog_failures(e) == 0:
                        return 1
                else:
                        return 3
        else:
                return 0

def authority_set(img, args):
        """pkg set-authority [-P] [-k ssl_key] [-c ssl_cert] [--reset-uuid]
            [-O origin_url] [-m mirror to add] [-M mirror to remove] 
            [--no-refresh] authority"""

        preferred = False
        ssl_key = None
        ssl_cert = None
        origin_url = None
        reset_uuid = False
        add_mirror = None
        remove_mirror = None
        refresh_catalogs = True

        opts, pargs = getopt.getopt(args, "Pk:c:O:M:m:",
            ["add-mirror=", "remove-mirror=", "no-refresh", "reset-uuid"])

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

        if len(pargs) != 1:
                usage(
                    _("pkg: set-authority: one and only one authority " \
                        "may be set"))

        auth = pargs[0]

        if ssl_key:
                ssl_key = os.path.abspath(ssl_key)
                if not os.path.exists(ssl_key):
                        error(_("set-authority: SSL key file '%s' does not " \
                            "exist") % ssl_key)
                        return 1

        if ssl_cert:
                ssl_cert = os.path.abspath(ssl_cert)
                if not os.path.exists(ssl_cert):
                        error(_("set-authority: SSL key cert '%s' does not " \
                            "exist") % ssl_cert)
                        return 1


        if not img.has_authority(auth) and origin_url == None:
                error(_("set-authority: authority does not exist. Use " \
                    "-O to define origin URL for new authority"))
                return 1

        elif not img.has_authority(auth) and not misc.valid_auth_prefix(auth):
                error(_("set-authority: authority name has invalid characters"))
                return 1

        if origin_url and not misc.valid_auth_url(origin_url):
                error(_("set-authority: authority URL is invalid"))
                return 1

        uuid = None
        if reset_uuid:
                uuid = pkg.Uuid25.uuid1()

        try:
                img.set_authority(auth, origin_url=origin_url,
                    ssl_key=ssl_key, ssl_cert=ssl_cert,
                    refresh_allowed=refresh_catalogs, uuid=uuid)
        except api_errors.CatalogRefreshException, e:
                error(_("set-authority failed: %s") % e)
                return 1

        if preferred:
                img.set_preferred_authority(auth)


        if add_mirror:

                if not misc.valid_auth_url(add_mirror):
                        error(_("set-authority: added mirror's URL is invalid"))
                        return 1

                if img.has_mirror(auth, add_mirror):
                        error(_("set-authority: mirror already exists"))
                        return 1

                img.add_mirror(auth, add_mirror)

        if remove_mirror:

                if not misc.valid_auth_url(remove_mirror):
                        error(_("set-authority: removed mirror has bad URL"))
                        return 1

                if not img.has_mirror(auth, remove_mirror):
                        error(_("set-authority: mirror does not exist"))
                        return 1


                img.del_mirror(auth, remove_mirror)


        return 0

def authority_unset(img, args):
        """pkg unset-authority authority ..."""

        # is this an existing authority in our image?
        # if so, delete it
        # if not, error
        preferred_auth = img.get_default_authority()

        if len(args) == 0:
                usage()

        for a in args:
                if not img.has_authority(a):
                        error(_("unset-authority: no such authority: %s") \
                            % a)
                        return 1

                if a == preferred_auth:
                        error(_("unset-authority: removal of preferred " \
                            "authority not allowed."))
                        return 1

                img.delete_authority(a)

        return 0

def authority_list(img, args):
        """pkg authorities"""
        omit_headers = False
        preferred_only = False
        preferred_authority = img.get_default_authority()

        opts, pargs = getopt.getopt(args, "HP")
        for opt, arg in opts:
                if opt == "-H":
                        omit_headers = True
                if opt == "-P":
                        preferred_only = True

        if len(pargs) == 0:
                if not omit_headers:
                        msg("%-35s %s" % ("AUTHORITY", "URL"))

                if preferred_only:
                        auths = [img.get_authority(preferred_authority)]
                else:
                        auths = img.gen_authorities()

                for a in auths:
                        # summary list
                        pfx, url, ssl_key, ssl_cert, dt, mir = \
                            img.split_authority(a)

                        if not preferred_only and pfx == preferred_authority:
                                pfx += " (preferred)"
                        msg("%-35s %s" % (pfx, url))
        else:
                img.load_catalogs(get_tracker())

                for a in pargs:
                        if not img.has_authority(a):
                                error(_("authority: no such authority: %s") \
                                    % a)
                                return 1

                        # detailed print
                        auth = img.get_authority(a)
                        pfx, url, ssl_key, ssl_cert, dt, mir = \
                            img.split_authority(auth)

                        if dt:
                                dt = dt.ctime()

                        if ssl_cert:
                                try:
                                        cert = img.build_cert(ssl_cert)
                                except (IOError, OpenSSL.crypto.Error):
                                        error(_("SSL certificate for %s" \
                                            "is invalid or non-existent.") % \
                                            pfx)
                                        error(_("Please check file at %s") %\
                                            ssl_cert)
                                        continue

                                nb = cert.get_notBefore()
                                t = time.strptime(nb, "%Y%m%d%H%M%SZ")
                                nb = datetime.datetime.utcfromtimestamp(
                                    calendar.timegm(t))

                                na = cert.get_notAfter()
                                t = time.strptime(na, "%Y%m%d%H%M%SZ")
                                na = datetime.datetime.utcfromtimestamp(
                                    calendar.timegm(t))
                        else:
                                cert = None

                        msg("")
                        msg("           Authority:", pfx)
                        msg("          Origin URL:", url)
                        msg("             SSL Key:", ssl_key)
                        msg("            SSL Cert:", ssl_cert)
                        if cert:
                                msg(" Cert Effective Date:", nb.ctime())
                                msg("Cert Expiration Date:", na.ctime())
                        msg("                UUID:", auth["uuid"])
                        msg("     Catalog Updated:", dt)
                        msg("             Mirrors:", mir)

        return 0

def property_set(img, args):
        """pkg set-property propname propvalue"""

        # ensure no options are passed in
        opts, pargs = getopt.getopt(args, "")
        try:
                propname, propvalue = pargs
        except ValueError:
                usage(
                    _("pkg: set-property: requires a property name and value"))

        try:
                img.set_property(propname, propvalue)
        except RuntimeError, e:
                error(_("set-property failed: %s") % e)
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
                usage(
                    _("pkg: unset-property requires at least one property name"))

        for p in pargs:
                try:
                        img.delete_property(p)
                except KeyError:
                        error(_("unset-property: no such property: %s") % p)
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
                pargs = img.properties()

        width = max(max([len(p) for p in pargs]), 8)
        fmt = "%%-%ss %%s" % width
        if not omit_headers:
                msg(fmt % ("PROPERTY", "VALUE"))

        for p in pargs:
                msg(fmt % (p, img.get_property(p)))

        return 0

def image_create(img, args):
        """Create an image of the requested kind, at the given path.  Load
        catalog for initial authority for convenience.

        At present, it is legitimate for a user image to specify that it will be
        deployed in a zone.  An easy example would be a program with an optional
        component that consumes global zone-only information, such as various
        kernel statistics or device information."""

        imgtype = image.IMG_USER
        is_zone = False
        ssl_key = None
        ssl_cert = None
        auth_name = None
        auth_url = None
        refresh_catalogs = True

        opts, pargs = getopt.getopt(args, "FPUza:k:c:",
            ["full", "partial", "user", "zone", "authority=", "no-refresh"])

        for opt, arg in opts:
                if opt == "-F" or opt == "--full":
                        imgtype = image.IMG_ENTIRE
                if opt == "-P" or opt == "--partial":
                        imgtype = image.IMG_PARTIAL
                if opt == "-U" or opt == "--user":
                        imgtype = image.IMG_USER
                if opt == "-z" or opt == "--zone":
                        is_zone = True
                if opt == "--no-refresh":
                        refresh_catalogs = False
                if opt == "-k":
                        ssl_key = arg
                if opt == "-c":
                        ssl_cert = arg
                if opt == "-a" or opt == "--authority":
                        try:
                                auth_name, auth_url = arg.split("=", 1)
                        except ValueError:
                                usage(_("image-create requires authority "
                                    "argument to be of the form "
                                    "'<prefix>=<url>'."))

        if len(pargs) != 1:
                usage(_("image-create requires a single image directory path"))

        if ssl_key:
                ssl_key = os.path.abspath(ssl_key)
                if not os.path.exists(ssl_key):
                        msg(_("pkg: set-authority: SSL key file '%s' does " \
                            "not exist") % ssl_key)
                        return 1

        if ssl_cert:
                ssl_cert = os.path.abspath(ssl_cert)
                if not os.path.exists(ssl_cert):
                        msg(_("pkg: set-authority: SSL key cert '%s' does " \
                            "not exist") % ssl_cert)
                        return 1

        if not auth_name and not auth_url:
                usage("image-create requires an authority argument")

        if not auth_name or not auth_url:
                usage(_("image-create requires authority argument to be of "
                    "the form '<prefix>=<url>'."))

        if auth_name.startswith(fmri.PREF_AUTH_PFX):
                error(_("image-create requires that a prefix not match: %s"
                        % fmri.PREF_AUTH_PFX))
                return 1

        if not misc.valid_auth_prefix(auth_name):
                error(_("image-create: authority prefix has invalid " \
                    "characters"))
                return 1

        if not misc.valid_auth_url(auth_url):
                error(_("image-create: authority URL is invalid"))
                return 1

        try:
                img.set_attrs(imgtype, pargs[0], is_zone, auth_name, auth_url,
                    ssl_key=ssl_key, ssl_cert=ssl_cert)
        except OSError, e:
                error(_("cannot create image at %s: %s") % \
                    (pargs[0], e.args[1]))
                return 1

        if refresh_catalogs:
                try:
                        img.retrieve_catalogs()
                except api_errors.CatalogRefreshException, cre:
                        if display_catalog_failures(cre) == 0:
                                return 1
                        else:
                                return 3
        return 0


def rebuild_index(img, pargs):
        """pkg rebuild-index

        Forcibly rebuild the search indexes. Will remove existing indexes
        and build new ones from scratch."""
        quiet = False

        if pargs:
                usage(_("rebuild-index: command does not take operands " \
                    "('%s')") % " ".join(pargs))

        try:
                img.history.operation_name = "rebuild-index"
                img.rebuild_search_index(get_tracker(quiet))
        except api_errors.CorruptedIndexException:
                img.history.operation_result = RESULT_FAILED_SEARCH
                error(INCONSISTENT_INDEX_ERROR_MESSAGE)
                return 1
        except api_errors.ProblematicPermissionsIndexException, e:
                img.history.operation_result = RESULT_FAILED_STORAGE
                error(str(e) + PROBLEMATIC_PERMISSIONS_ERROR_MESSAGE)
                return 1
        else:
                img.history.operation_result = RESULT_SUCCEEDED
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
                usage(_("history: -H and -l may not be combined"))

        if not long_format:
                if not omit_headers:
                        msg("%-19s %-25s %-15s %s" % (_("TIME"),
                            _("OPERATION"), _("CLIENT"), _("OUTCOME")))

        for entry in sorted(os.listdir(img.history.path)):
                # Load the history entry.
                he = history.History(root_dir=img.history.root_dir,
                    filename=entry)

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

# To allow exception handler access to the image.
__img = None

def main_func():
        global __img
        __img = img = image.Image()
        img.history.client_name = PKG_CLIENT_NAME

        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkg", "/usr/lib/locale")

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "R:")
        except getopt.GetoptError, e:
                usage(_("illegal global option -- %s") % e.opt)

        if pargs == None or len(pargs) == 0:
                usage()

        subcommand = pargs[0]
        del pargs[0]

        socket.setdefaulttimeout(
            int(os.environ.get("PKG_CLIENT_TIMEOUT", "30"))) # in seconds

        # Override default MAX_TIMEOUT_COUNT if a value has been specified
        # in the environment.
        timeout_max = misc.MAX_TIMEOUT_COUNT
        misc.MAX_TIMEOUT_COUNT = int(os.environ.get("PKG_TIMEOUT_MAX",
            timeout_max))

        if subcommand == "image-create":
                try:
                        ret = image_create(img, pargs)
                except getopt.GetoptError, e:
                        usage(_("illegal %s option -- %s") % \
                            (subcommand, e.opt))
                return ret
        elif subcommand == "version":
                if pargs:
                        usage(_("version: command does not take operands " \
                            "('%s')") % " ".join(pargs))
                msg(pkg.VERSION)
                return 0
        elif subcommand == "help":
                try:
                        usage()
                except SystemExit:
                        return 0

        provided_image_dir = True
        pkg_image_used = False
                
        for opt, arg in opts:
                if opt == "-R":
                        mydir = arg

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

        img.load_config()

        try:
                if subcommand == "refresh":
                        return catalog_refresh(mydir, pargs)
                elif subcommand == "list":
                        return list_inventory(img, pargs)
                elif subcommand == "image-update":
                        return image_update(mydir, pargs)
                elif subcommand == "install":
                        return install(mydir, pargs)
                elif subcommand == "uninstall":
                        return uninstall(mydir, pargs)
                elif subcommand == "freeze":
                        return freeze(img, pargs)
                elif subcommand == "unfreeze":
                        return unfreeze(img, pargs)
                elif subcommand == "search":
                        return search(img, pargs)
                elif subcommand == "info":
                        return info(mydir, pargs)
                elif subcommand == "contents":
                        return list_contents(img, pargs)
                elif subcommand == "verify":
                        return verify_image(img, pargs)
                elif subcommand == "set-authority":
                        return authority_set(img, pargs)
                elif subcommand == "unset-authority":
                        return authority_unset(img, pargs)
                elif subcommand == "authority":
                        return authority_list(img, pargs)
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
                        return rebuild_index(img, pargs)
                else:
                        usage(_("unknown subcommand '%s'") % subcommand)

        except getopt.GetoptError, e:
                usage(_("illegal %s option -- %s") % (subcommand, e.opt))


#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
        try:
                __ret = main_func()
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
        except misc.TransferTimedOutException:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                error(_("maximum number of timeouts exceeded during "
                    "download."))
                __ret = 1
        except misc.InvalidContentException, __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                error(_("One or more hosts providing content for this install"
                    "has provided a file with invalid content."))
                error(__e)
                __ret = 1
        except (ManifestRetrievalError,
            DatastreamRetrievalError), __e:
                if __img:
                        __img.history.abort(RESULT_FAILED_TRANSPORT)
                error(_("An error was encountered while attempting to retrieve"
                    " package or file data for the requested operation."))
                error(__e)
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
        except:
                if __img:
                        __img.history.abort(RESULT_FAILED_UNKNOWN)
                traceback.print_exc()
                error(
                    _("\n\nThis is an internal error.  Please let the "
                    "developers know about this\nproblem by filing a bug at"
                    "http://defect.opensolaris.org and including the\nabove"
                    "traceback and this message.  The version of pkg(5) is "
                    "'%s'.") % pkg.VERSION)
                __ret = 99

        sys.exit(__ret)
