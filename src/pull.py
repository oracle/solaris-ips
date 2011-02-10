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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.
#

import calendar
import getopt
import gettext
import os
import shutil
import sys
import tempfile
import traceback
import urllib
import warnings

import pkg.catalog as catalog
import pkg.client.progress as progress
import pkg.fmri
import pkg.manifest as manifest
import pkg.client.api_errors as apx
import pkg.client.transport.transport as transport
import pkg.misc as misc
import pkg.p5p
import pkg.publish.transaction as trans
import pkg.version as version

from pkg.client import global_settings
from pkg.misc import emsg, get_pkg_otw_size, msg, PipeError

# Globals
cache_dir = None
complete_catalog = None
download_start = False
tmpdirs = []
temp_root = None
xport = None
xport_cfg = None
dest_xport = None
targ_pub = None

def error(text):
        """Emit an error message prefixed by the command name """

        # If we get passed something like an Exception, we can convert
        # it down to a string.
        text = str(text)

        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + "pkgrecv: " + text_nows)

def usage(usage_error=None, retcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error)

        msg(_("""\
Usage:
        pkgrecv [-s src_uri] [-a] [-d (path|dest_uri)] [-c cache_dir]
            [-kr] [-m match] [-n] [--raw] [--key keyfile --cert certfile] 
            (fmri|pattern) ...
        pkgrecv [-s src_repo_uri] --newest 

Options:
        -a              Store the retrieved package data in a pkg(5) archive
                        at the location specified by -d.  The file may not
                        already exist, and this option may only be used with
                        filesystem-based destinations.

        -c cache_dir    The path to a directory that will be used to cache
                        downloaded content.  If one is not supplied, the
                        client will automatically pick a cache directory.
                        In the case where a download is interrupted, and a
                        cache directory was automatically chosen, use this
                        option to resume the download.

        -d path_or_uri  The filesystem path or URI of the target repository to
                        republish packages to.  If not provided, the default
                        value is the current working directory.  The target
                        must already exist.  New repositories can be created
                        using pkgrepo(1).

        -h              Display this usage message.

        -k              Keep the retrieved package content compressed, ignored
                        when republishing.  Should not be used with pkgsend.

        -m match        Controls matching behaviour using the following values:
                            all-timestamps
                                includes all matching timestamps, not just
                                latest (implies all-versions)
                            all-versions
                                includes all matching versions, not just latest

        -n              Perform a trial run with no changes made.

        -r              Recursively evaluates all dependencies for the provided
                        list of packages and adds them to the list.

        -s src_repo_uri A URI representing the location of a pkg(5)
                        repository to retrieve package data from.

        --newest        List the most recent versions of the packages available
                        from the specified repository and exit.  (All other
                        options except -s will be ignored.)

        --raw           Retrieve and store the raw package data in a set of
                        directory structures by stem and version at the location
                        specified by -d.  May only be used with filesystem-
                        based destinations.  This can be used with pkgsend(1)
                        include to conveniently modify and republish packages,
                        perhaps by correcting file contents or providing
                        additional package metadata.

        --key keyfile   Specify a client SSL key file to use for pkg retrieval.

        --cert certfile Specify a client SSL certificate file to use for pkg retrieval.

Environment:
        PKG_DEST        Destination directory or repository URI
        PKG_SRC         Source repository URI"""))
        sys.exit(retcode)

def cleanup(caller_error=False):
        """To be called at program finish."""

        for d in tmpdirs:
                # If the cache_dir is in the list of directories that should
                # be cleaned up, but we're exiting with an error, then preserve
                # the directory so downloads may be resumed.
                if d == cache_dir and caller_error and download_start:
                        error(_("\n\nCached files were preserved in the "
                            "following directory:\n\t%s\nUse pkgrecv -c "
                            "to resume the interrupted download.") % cache_dir)
                        continue
                shutil.rmtree(d, True)

        if caller_error and dest_xport and targ_pub:
                try:
                        dest_xport.publish_refresh_packages(targ_pub)
                except apx.TransportError:
                        # If this fails, ignore it as this was a last ditch
                        # attempt anyway.
                        pass

def abort(err=None, retcode=1):
        """To be called when a fatal error is encountered."""

        if err:
                # Clear any possible output first.
                msg("")
                error(err)

        cleanup(caller_error=True)
        sys.exit(retcode)

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

def get_manifest(pfmri, xport_cfg, contents=False):

        m = None
        pkgdir = xport_cfg.get_pkg_dir(pfmri)
        mpath = xport_cfg.get_pkg_pathname(pfmri)

        if not os.path.exists(mpath):
                m = xport.get_manifest(pfmri)
        else:
                # A FactoredManifest is used here to reduce peak memory
                # usage (notably when -r was specified).
                try:
                        m = manifest.FactoredManifest(pfmri, pkgdir)
                except:
                        abort(err=_("Unable to parse manifest '%(mpath)s' for "
                            "package '%(pfmri)s'") % locals())

        if contents:
                return m.tostr_unsorted()
        return m

def expand_fmri(pfmri, constraint=version.CONSTRAINT_AUTO):
        """Find matching fmri using CONSTRAINT_AUTO cache for performance.
        Returns None if no matching fmri is found."""
        if isinstance(pfmri, str):
                pfmri = pkg.fmri.PkgFmri(pfmri, "5.11")

        for f in complete_catalog.get(pfmri.pkg_name, []):
                if not pfmri.version or \
                    f.version.is_successor(pfmri.version, constraint):
                        return f
        return

def expand_matching_fmris(fmri_list, pfmri_strings):
        """find matching fmris using pattern matching and
        constraint auto."""

        try:
                patterns = [
                    pkg.fmri.MatchingPkgFmri(s, "5.11")
                    for s in pfmri_strings
                ]
        except pkg.fmri.FmriError, e:
                abort(err=e)

        matched_pats = {}

        matches, unmatched = catalog.extract_matching_fmris(fmri_list,
            patterns=patterns, constraint=version.CONSTRAINT_AUTO,
            matcher=pkg.fmri.glob_match, counthash=matched_pats)
        return matched_pats, matches, unmatched

def get_dependencies(src_uri, fmri_list, xport_cfg, tracker):

        old_limit = sys.getrecursionlimit()
        # The user may be recursing 'entire' or 'redistributable'.
        sys.setrecursionlimit(3000)

        s = set()
        for f in fmri_list:
                pfmri = expand_fmri(f)
                _get_dependencies(src_uri, s, pfmri, xport_cfg, tracker)

        # Restore the previous default.
        sys.setrecursionlimit(old_limit)

        return list(s)

def _get_dependencies(src_uri, s, pfmri, xport_cfg, tracker):
        """Expand all dependencies."""
        tracker.evaluate_progress(fmri=pfmri)
        s.add(pfmri)

        m = get_manifest(pfmri, xport_cfg)
        for a in m.gen_actions_by_type("depend"):
                new_fmri = expand_fmri(a.attrs["fmri"])
                if new_fmri and new_fmri not in s:
                        _get_dependencies(src_uri, s, new_fmri, xport_cfg,
                            tracker)
        return s

def add_hashes_to_multi(mfst, multi):
        """Takes a manifest and a multi object. Adds the hashes to the multi
        object, returns (get_bytes, get_files, send_bytes, send_comp_bytes)
        tuple."""

        getb = 0
        getf = 0
        sendb = 0
        sendcb = 0

        for atype in ("file", "license"):
                for a in mfst.gen_actions_by_type(atype):
                        if a.needsdata(None, None):
                                multi.add_action(a)
                                getb += get_pkg_otw_size(a)
                                getf += 1
                                sendb += int(a.attrs.get("pkg.size", 0))
                                sendcb += int(a.attrs.get("pkg.csize", 0))
        return getb, getf, sendb, sendcb

def prune(fmri_list, all_versions, all_timestamps):
        """Returns a filtered version of fmri_list based on the provided
        parameters."""

        if all_timestamps:
                pass
        elif all_versions:
                dedup = {}
                for f in fmri_list:
                        dedup.setdefault(f.get_short_fmri(), []).append(f)
                fmri_list = [sorted(dedup[f], reverse=True)[0] for f in dedup]
        else:
                dedup = {}
                for f in fmri_list:
                        dedup.setdefault(f.pkg_name, []).append(f)
                fmri_list = [sorted(dedup[f], reverse=True)[0] for f in dedup]
        return fmri_list

def list_newest_fmris(fmri_list):
        """List the provided fmris."""

        fm_hash = {}
        fm_list = []

        # Order all fmris by package name
        for f in sorted(fmri_list):
                if f.pkg_name in fm_hash:
                        fm_hash[f.pkg_name].append(f)
                else:
                        fm_hash[f.pkg_name] = [ f ]

        # sort each fmri list
        for k in fm_hash.keys():
                fm_hash[k].sort(reverse = True)
                l = fm_hash[k]
                fm_list.append(l[0])

        for e in fm_list:
                msg(e.get_fmri())

def fetch_catalog(src_pub, tracker, txport):
        """Fetch the catalog from src_uri."""
        global complete_catalog

        src_uri = src_pub.selected_repository.origins[0].uri
        tracker.catalog_start(src_uri)

        if not src_pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp(dir=temp_root,
                    prefix=global_settings.client_name + "-")
                tmpdirs.append(cat_dir)
                src_pub.meta_root = cat_dir

        src_pub.transport = txport
        try:
                src_pub.refresh(True, True)
        except apx.TransportError, e:
                # Assume that a catalog doesn't exist for the target publisher,
                # and drive on.  If there was an actual failure due to a
                # transport issue, let the failure happen whenever some other
                # operation is attempted later.
                return []

        cat = src_pub.catalog

        d = {}
        fmri_list = []
        for f in cat.fmris():
                fmri_list.append(f)
                d.setdefault(f.pkg_name, [f]).append(f)
        for k in d.keys():
                d[k].sort(reverse=True)

        complete_catalog = d
        tracker.catalog_done()
        return fmri_list

def main_func():
        global cache_dir, download_start, xport, xport_cfg, dest_xport, \
            temp_root, targ_pub

        all_timestamps = False
        all_versions = False
        dry_run = False
        keep_compressed = False
        list_newest = False
        recursive = False
        src_uri = None
        target = None
        incoming_dir = None
        src_pub = None
        archive = False
        raw = False
        key = None
        cert = None

        temp_root = misc.config_temp_root()

        gettext.install("pkg", "/usr/share/locale")

        global_settings.client_name = "pkgrecv"
        target = os.environ.get("PKG_DEST", None)
        src_uri = os.environ.get("PKG_SRC", None)

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ac:d:hkm:nrs:", 
                    ["cert=", "key=", "newest", "raw"])
        except getopt.GetoptError, e:
                usage(_("Illegal option -- %s") % e.opt)

        for opt, arg in opts:
                if opt == "-a":
                        archive = True
                elif opt == "-c":
                        cache_dir = arg
                elif opt == "-d":
                        target = arg
                elif opt == "-h":
                        usage(retcode=0)
                elif opt == "-k":
                        keep_compressed = True
                elif opt == "-m":
                        if arg == "all-timestamps":
                                all_timestamps = True
                        elif arg == "all-versions":
                                all_versions = True
                        else:
                                usage(_("Illegal option value -- %s") % arg)
                elif opt == "-n":
                        dry_run = True
                elif opt == "-r":
                        recursive = True
                elif opt == "-s":
                        src_uri = arg
                elif opt == "--newest":
                        list_newest = True
                elif opt == "--raw":
                        raw = True
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg

        if not src_uri:
                usage(_("a source repository must be provided"))
        else:
                src_uri = misc.parse_uri(src_uri)

        if not cache_dir:
                cache_dir = tempfile.mkdtemp(dir=temp_root,
                    prefix=global_settings.client_name + "-")
                # Only clean-up cache dir if implicitly created by pkgrecv.
                # User's cache-dirs should be preserved
                tmpdirs.append(cache_dir)

        incoming_dir = tempfile.mkdtemp(dir=temp_root,
            prefix=global_settings.client_name + "-")
        tmpdirs.append(incoming_dir)

        # Create transport and transport config
        xport, xport_cfg = transport.setup_transport()
        xport_cfg.add_cache(cache_dir, readonly=False)
        xport_cfg.incoming_root = incoming_dir

        # Since publication destinations may only have one repository configured
        # per publisher, create destination as separate transport in case source
        # and destination have identical publisher configuration but different
        # repository endpoints.
        dest_xport, dest_xport_cfg = transport.setup_transport()
        dest_xport_cfg.add_cache(cache_dir, readonly=False)
        dest_xport_cfg.incoming_root = incoming_dir

        # Configure src publisher(s).
        transport.setup_publisher(src_uri, "source", xport, xport_cfg,
            remote_prefix=True, ssl_key=key, ssl_cert=cert)

        args = (pargs, target, list_newest, all_versions,
            all_timestamps, keep_compressed, raw, recursive, dry_run,
            dest_xport_cfg, src_uri)

        if archive:
                # Retrieving package data for archival requires a different mode
                # of operation so gets its own routine.  Notably, it requires
                # that all package data be retrieved before the archival process
                # is started.
                return archive_pkgs(*args)

        # Normal package transfer allows operations on a per-package basis.
        return transfer_pkgs(*args)

def check_processed(any_matched, any_unmatched, total_processed):
        # Reduce unmatched patterns to those that were unmatched for all
        # publishers.
        unmatched = {}
        for pub_unmatched in any_unmatched:
                if not pub_unmatched:
                        # If any publisher matched all patterns, then treat
                        # the operation as successful.
                        unmatched = {}
                        break

                for k in pub_unmatched:
                        unmatched.setdefault(k, set()).update(pub_unmatched[k])

        for k in unmatched:
                map(unmatched[k].discard, any_matched)

        # Prune types of matching that didn't have any match failures.
        for k, v in unmatched.items():
                if not v:
                        del unmatched[k]

        if unmatched:
                # If any match failures remain, abort with an error.
                match_err = apx.InventoryException(**unmatched)
                emsg(match_err)
                if total_processed > 0:
                        # Partial failure.
                        abort(retcode=3)
                abort()

def archive_pkgs(pargs, target, list_newest, all_versions, all_timestamps,
    keep_compresed, raw, recursive, dry_run, dest_xport_cfg, src_uri):
        """Retrieve source package data completely and then archive it."""

        global cache_dir, download_start, xport, xport_cfg, dest_xport, targ_pub

        target = os.path.abspath(target)
        if os.path.exists(target):
                error(_("Target archive '%s' already "
                    "exists.") % target)
                abort()

        # Open the archive early so that permissions failures, etc. can be
        # detected before actual work is started.
        pkg_arc = pkg.p5p.Archive(target, mode="w")

        basedir = tempfile.mkdtemp(dir=temp_root,
            prefix=global_settings.client_name + "-")
        tmpdirs.append(basedir)

        # Retrieve package data for all publishers.
        any_unmatched = []
        any_matched = []
        total_processed = 0
        arc_bytes = 0
        archive_list = []
        for src_pub in xport_cfg.gen_publishers():
                # Root must be per publisher on the off chance that multiple
                # publishers have the same package.
                xport_cfg.pkg_root = os.path.join(basedir, src_pub.prefix)

                tracker = get_tracker()
                msg(_("Retrieving packages for publisher %s ...") %
                    src_pub.prefix)
                if pargs == None or len(pargs) == 0:
                        usage(_("must specify at least one pkgfmri"))

                all_fmris = fetch_catalog(src_pub, tracker, xport)
                fmri_arguments = pargs
                matched_pats, matches, unmatched = expand_matching_fmris(
                    all_fmris, fmri_arguments)

                # Track anything that failed to match.
                any_unmatched.append(unmatched)
                any_matched.extend(matched_pats.keys())
                if not matches:
                        # No matches at all; nothing to do for this publisher.
                        continue

                fmri_list = prune(list(set(matches)), all_versions,
                    all_timestamps)

                if recursive:
                        msg(_("Retrieving manifests for dependency "
                            "evaluation ..."))
                        tracker.evaluate_start()
                        fmri_list = prune(get_dependencies(src_uri, fmri_list,
                            xport_cfg, tracker), all_versions, all_timestamps)
                        tracker.evaluate_done()

                def get_basename(pfmri):
                        open_time = pfmri.get_timestamp()
                        return "%d_%s" % \
                            (calendar.timegm(open_time.utctimetuple()),
                            urllib.quote(str(pfmri), ""))

                # First, retrieve the manifests and calculate package transfer
                # sizes.
                npkgs = len(fmri_list)
                get_bytes = 0
                get_files = 0

                if not recursive:
                        msg(_("Retrieving and evaluating %d package(s)...") %
                            npkgs)

                tracker.evaluate_start(npkgs=npkgs)
                skipped = False
                retrieve_list = []
                while fmri_list:
                        f = fmri_list.pop()

                        m = get_manifest(f, xport_cfg)
                        pkgdir = xport_cfg.get_pkg_dir(f)
                        mfile = xport.multi_file_ni(src_pub, pkgdir,
                            progtrack=tracker)
         
                        getb, getf, arcb, arccb = add_hashes_to_multi(m, mfile)
                        get_bytes += getb
                        get_files += getf

                        # Since files are going into the archive, progress
                        # can be tracked in terms of compressed bytes for
                        # the package files themselves.
                        arc_bytes += arccb

                        # Also include the the manifest file itself in the
                        # amount of bytes to archive.
                        try:
                                fs = os.stat(m.pathname)
                                arc_bytes += fs.st_size
                        except EnvironmentError, e:
                                raise apx._convert_error(e)

                        retrieve_list.append((f, mfile))
                        if not dry_run:
                                archive_list.append((f, m.pathname, pkgdir))
                        tracker.evaluate_progress(fmri=f)

                tracker.evaluate_done()

                # Next, retrieve the content for this publisher's packages.
                tracker.download_set_goal(len(retrieve_list), get_files,
                    get_bytes)

                if dry_run:
                        # Don't call download_done here; it would cause an
                        # assertion failure since nothing was downloaded.
                        # Instead, call the method that simply finishes
                        # up the progress output.
                        tracker.dl_output_done()
                        cleanup()
                        continue

                processed = 0
                while retrieve_list:
                        f, mfile = retrieve_list.pop()
                        tracker.download_start_pkg(f.pkg_name)

                        if mfile:
                                download_start = True
                                mfile.wait_files()

                        # Nothing more to do for this package.
                        tracker.download_end_pkg()

                tracker.download_done()
                tracker.reset()

        # Check processed patterns and abort with failure if some were
        # unmatched.
        check_processed(any_matched, any_unmatched, total_processed)

        if dry_run:
                # Dump all temporary data.
                cleanup()
                return 0

        # Now create archive and then archive retrieved package data.
        while archive_list:
                pfmri, mpath, pkgdir = archive_list.pop()
                pkg_arc.add_package(pfmri, mpath, pkgdir)
        pkg_arc.close(progtrack=tracker)

        # Dump all temporary data.
        cleanup()
        return 0

def transfer_pkgs(pargs, target, list_newest, all_versions, all_timestamps,
    keep_compressed, raw, recursive, dry_run, dest_xport_cfg, src_uri):
        """Retrieve source package data and optionally republish it as each
        package is retrieved.
        """

        global cache_dir, download_start, xport, xport_cfg, dest_xport, targ_pub

        any_unmatched = []
        any_matched = []
        total_processed = 0
        for src_pub in xport_cfg.gen_publishers():
                tracker = get_tracker()
                if list_newest:
                        if pargs or len(pargs) > 0:
                                usage(_("-n takes no options"))

                        fmri_list = fetch_catalog(src_pub, tracker, xport)
                        list_newest_fmris(fmri_list)
                        continue

                msg(_("Processing packages for publisher %s ...") %
                    src_pub.prefix)
                if pargs == None or len(pargs) == 0:
                        usage(_("must specify at least one pkgfmri"))

                republish = False

                if not target:
                        target = basedir = os.getcwd()
                elif target and not raw:
                        basedir = tempfile.mkdtemp(dir=temp_root,
                            prefix=global_settings.client_name + "-")
                        tmpdirs.append(basedir)
                        republish = True

                        # Turn target into a valid URI.
                        target = misc.parse_uri(target)

                        # Setup target for transport.
                        targ_pub = transport.setup_publisher(target,
                            src_pub.prefix, dest_xport, dest_xport_cfg)

                        # Files have to be decompressed for republishing.
                        keep_compressed = False
                        if target.startswith("file://"):
                                # Check to see if the repository exists first.
                                try:
                                        t = trans.Transaction(target,
                                            xport=dest_xport, pub=targ_pub)
                                except trans.TransactionRepositoryInvalidError, e:
                                        txt = str(e) + "\n\n"
                                        txt += _("To create a repository, use "
                                            "the pkgrepo command.")
                                        abort(err=txt)
                                except trans.TransactionRepositoryConfigError, e:
                                        txt = str(e) + "\n\n"
                                        txt += _("The repository configuration "
                                            "for the repository located at "
                                            "'%s' is not valid or the "
                                            "specified path does not exist.  "
                                            "Please correct the configuration "
                                            "of the repository or create a new "
                                            "one.") % target
                                        abort(err=txt)
                                except trans.TransactionError, e:
                                        abort(err=e)
                else:
                        basedir = target = os.path.abspath(target)
                        if not os.path.exists(basedir):
                                try:
                                        os.makedirs(basedir, misc.PKG_DIR_MODE)
                                except Exception, e:
                                        error(_("Unable to create basedir "
                                            "'%s': %s") % (basedir, e))
                                        abort()

                xport_cfg.pkg_root = basedir
                dest_xport_cfg.pkg_root = basedir

                if republish:
                        targ_fmris = fetch_catalog(targ_pub, tracker,
                            dest_xport)

                all_fmris = fetch_catalog(src_pub, tracker, xport)
                fmri_arguments = pargs
                matched_pats, matches, unmatched = expand_matching_fmris(
                    all_fmris, fmri_arguments)

                # Track anything that failed to match.
                any_unmatched.append(unmatched)
                any_matched.extend(matched_pats.keys())
                if not matches:
                        # No matches at all; nothing to do for this publisher.
                        continue

                fmri_list = prune(list(set(matches)), all_versions,
                    all_timestamps)

                if recursive:
                        msg(_("Retrieving manifests for dependency "
                            "evaluation ..."))
                        tracker.evaluate_start()
                        fmri_list = prune(get_dependencies(src_uri, fmri_list,
                            xport_cfg, tracker), all_versions, all_timestamps)
                        tracker.evaluate_done()

                def get_basename(pfmri):
                        open_time = pfmri.get_timestamp()
                        return "%d_%s" % \
                            (calendar.timegm(open_time.utctimetuple()),
                            urllib.quote(str(pfmri), ""))

                # First, retrieve the manifests and calculate package transfer
                # sizes.
                npkgs = len(fmri_list)
                get_bytes = 0
                send_bytes = 0

                if not recursive:
                        msg(_("Retrieving and evaluating %d package(s)...") %
                            npkgs)

                tracker.evaluate_start(npkgs=npkgs)
                skipped = False
                retrieve_list = []
                while fmri_list:
                        f = fmri_list.pop()

                        if republish and f in targ_fmris:
                                if not skipped:
                                        # Ensure a new line is output so message
                                        # is on separate line from spinner.
                                        msg("")
                                msg(_("Skipping %s: already present "
                                    "at destination") % f)
                                skipped = True
                                continue

                        m = get_manifest(f, xport_cfg)
                        pkgdir = xport_cfg.get_pkg_dir(f)
                        mfile = xport.multi_file_ni(src_pub, pkgdir,
                            not keep_compressed, tracker)
         
                        getb, getf, sendb, sendcb = add_hashes_to_multi(m,
                            mfile)
                        get_bytes += getb
                        if republish:
                                # For now, normal republication always uses
                                # uncompressed data as already compressed data
                                # is not supported for publication.
                                send_bytes += sendb

                        retrieve_list.append((f, mfile))

                        tracker.evaluate_progress(fmri=f)
                tracker.evaluate_done()

                # Next, retrieve and store the content for each package.
                tracker.republish_set_goal(len(retrieve_list), get_bytes,
                    send_bytes)

                if dry_run:
                        tracker.republish_done()
                        cleanup()
                        continue

                processed = 0
                while retrieve_list:
                        f, mfile = retrieve_list.pop()
                        tracker.republish_start_pkg(f.pkg_name)

                        if mfile:
                                download_start = True
                                mfile.wait_files()

                        if not republish:
                                # Nothing more to do for this package.
                                tracker.republish_end_pkg()
                                continue

                        m = get_manifest(f, xport_cfg)

                        # Get first line of original manifest so that inclusion
                        # of the scheme can be determined.
                        use_scheme = True
                        contents = get_manifest(f, xport_cfg, contents=True)
                        if contents.splitlines()[0].find("pkg:/") == -1:
                                use_scheme = False

                        pkg_name = f.get_fmri(include_scheme=use_scheme)
                        pkgdir = xport_cfg.get_pkg_dir(f)

                        # This is needed so any previous failures for a package
                        # can be aborted.
                        trans_id = get_basename(f)

                        if not targ_pub:
                                targ_pub = transport.setup_publisher(target,
                                    src_pub.prefix, dest_xport, dest_xport_cfg,
                                    remote_prefix=True)

                        try:
                                t = trans.Transaction(target, pkg_name=pkg_name,
                                    trans_id=trans_id, xport=dest_xport,
                                    pub=targ_pub, progtrack=tracker)

                                # Remove any previous failed attempt to
                                # to republish this package.
                                try:
                                        t.close(abandon=True)
                                except:
                                        # It might not exist already.
                                        pass

                                t.open()
                                for a in m.gen_actions():
                                        if a.name == "set" and \
                                            a.attrs.get("name", "") in ("fmri",
                                            "pkg.fmri"):
                                                # To be consistent with the
                                                # server, the fmri can't be
                                                # added to the manifest.
                                                continue

                                        if hasattr(a, "hash"):
                                                fname = os.path.join(pkgdir,
                                                    a.hash)
                                                a.data = lambda: open(fname,
                                                    "rb")
                                        t.add(a)
                                # Always defer catalog update.
                                t.close(add_to_catalog=False)
                        except trans.TransactionError, e:
                                abort(err=e)

                        # Dump data retrieved so far after each successful
                        # republish to conserve space.
                        try:
                                shutil.rmtree(dest_xport_cfg.incoming_root)
                        except EnvironmentError, e:
                                raise apx._convert_error(e)
                        misc.makedirs(dest_xport_cfg.incoming_root)

                        processed += 1
                        tracker.republish_end_pkg()

                tracker.republish_done()
                tracker.reset()

                if processed > 0:
                        # If any packages were published, trigger an update of
                        # the catalog.
                        total_processed += processed
                        dest_xport.publish_refresh_packages(targ_pub)

                # Prevent further use.
                targ_pub = None

        # Check processed patterns and abort with failure if some were
        # unmatched.
        check_processed(any_matched, any_unmatched, total_processed)

        # Dump all temporary data.
        cleanup()
        return 0

if __name__ == "__main__":

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                __ret = main_func()
        except (KeyboardInterrupt, apx.CanceledException):
                cleanup(True)
                __ret = 1
        except (pkg.actions.ActionError, trans.TransactionError, RuntimeError,
            apx.ApiException), _e:
                error(_e)
                cleanup(True)
                __ret = 1
        except PipeError:
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                cleanup(False)
                __ret = 1
        except SystemExit, _e:
                cleanup(False)
                raise _e
        except:
                cleanup(True)
                traceback.print_exc()
                error(_("""\n
This is an internal error in pkg(5) version %(version)s.  Please let the
developers know about this problem by including the information above (and
this message) when filing a bug at:

%(bug_uri)s""") % { "version": pkg.VERSION, "bug_uri": misc.BUG_URI_CLI })
                __ret = 99
        sys.exit(__ret)
