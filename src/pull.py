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
# Copyright (c) 2008, 2013, Oracle and/or its affiliates. All rights reserved.
#

import calendar
import errno
import getopt
import gettext
import locale
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
import pkg.client.pkgdefs as pkgdefs
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.misc as misc
import pkg.p5p
import pkg.pkgsubprocess as subprocess
import pkg.publish.transaction as trans
import pkg.server.repository as sr
import pkg.version as version

from pkg.client import global_settings
from pkg.misc import emsg, get_pkg_otw_size, msg, PipeError
from pkg.client.debugvalues import DebugValues

# Globals
archive = False
cache_dir = None
src_cat = None
download_start = False
tmpdirs = []
temp_root = None
xport = None
xport_cfg = None
dest_xport = None
targ_pub = None
target = None

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
        pkgrecv [-aknrv] [-s src_uri] [-d (path|dest_uri)] [-c cache_dir]
            [-m match] [--raw] [--key src_key --cert src_cert]
            [--dkey dest_key --dcert dest_cert]
            (fmri|pattern) ...
        pkgrecv [-s src_repo_uri] --newest
        pkgrecv [-nv] [-s src_repo_uri] [-d path] [-p publisher ...]
            [--key src_key --cert src_cert] --clone

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
                        republish packages to.  The target must already exist.
                        New repositories can be created using pkgrepo(1).

        -h              Display this usage message.

        -k              Keep the retrieved package content compressed, ignored
                        when republishing.  Should not be used with pkgsend.

        -m match        Controls matching behaviour using the following values:
                            all-timestamps (default)
                                includes all matching timestamps (implies
                                all-versions)
                            all-versions
                                includes all matching versions
                            latest
                                includes only the latest version of each package

        -n              Perform a trial run with no changes made.

        -v              Display verbose output.

        -p publisher    Only clone the given publisher. Can be specified
                        multiple times. Only valid with --clone.

        -r              Recursively evaluates all dependencies for the provided
                        list of packages and adds them to the list.

        -s src_repo_uri A URI representing the location of a pkg(5)
                        repository to retrieve package data from.

        --clone         Make an exact copy of the source repository. By default,
                        the clone operation will only succeed if publishers in
                        the  source  repository  are  also  present  in  the
                        destination.  By using -p, the operation can be limited
                        to  specific  publishers  which  will  be  added  to the
                        destination repository if not already present.
                        Packages in the destination repository which are not in
                        the source will be removed.
                        Cloning will leave the destination repository altered in
                        case of an error.

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

        --key src_key   Specify a client SSL key file to use for pkg retrieval.

        --cert src_cert Specify a client SSL certificate file to use for pkg
                        retrieval.

        --dkey dest_key Specify a client SSL key file to use for pkg
                        publication.

        --dcert dest_cert Specify a client SSL certificate file to use for pkg
                          publication.

Environment:
        PKG_DEST        Destination directory or URI
        PKG_SRC         Source URI or path"""))
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
                shutil.rmtree(d, ignore_errors=True)

        if caller_error and dest_xport and targ_pub and not archive:
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

def get_tracker():
        try:
                progresstracker = \
                    progress.FancyUNIXProgressTracker()
        except progress.ProgressTrackerException:
                progresstracker = progress.CommandLineProgressTracker()
        progresstracker.set_major_phase(progresstracker.PHASE_UTILITY)
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
                pfmri = pkg.fmri.PkgFmri(pfmri)

        # Iterate in reverse so newest version is evaluated first.
        versions = [e for e in src_cat.fmris_by_version(pfmri.pkg_name)]
        for v, fmris in reversed(versions):
                for f in fmris:
                        if not pfmri.version or \
                            f.version.is_successor(pfmri.version, constraint):
                                return f
        return

def get_dependencies(fmri_list, xport_cfg, tracker):

        old_limit = sys.getrecursionlimit()
        # The user may be recursing 'entire' or 'redistributable'.
        sys.setrecursionlimit(3000)

        s = set()
        for f in fmri_list:
                _get_dependencies(s, f, xport_cfg, tracker)

        # Restore the previous default.
        sys.setrecursionlimit(old_limit)

        return list(s)

def _get_dependencies(s, pfmri, xport_cfg, tracker):
        """Expand all dependencies."""
        # XXX???
        # tracker.evaluate_progress(pkgfmri=pfmri)
        s.add(pfmri)

        m = get_manifest(pfmri, xport_cfg)
        for a in m.gen_actions_by_type("depend"):
                for fmri_str in a.attrlist("fmri"):
                        new_fmri = expand_fmri(fmri_str)
                        if new_fmri and new_fmri not in s:
                                _get_dependencies(s, new_fmri, xport_cfg, tracker)
        return s

def get_sizes(mfst):
        """Takes a manifest and return
        (get_bytes, get_files, send_bytes, send_comp_bytes) tuple."""

        getb = 0
        getf = 0
        sendb = 0
        sendcb = 0

        for a in mfst.gen_actions():
                if a.has_payload:
                        getb += get_pkg_otw_size(a)
                        getf += 1
                        sendb += int(a.attrs.get("pkg.size", 0))
                        sendcb += int(a.attrs.get("pkg.csize", 0))
                        if a.name == "signature":
                                getf += len(a.get_chain_certs())
                                getb += a.get_action_chain_csize()
        return getb, getf, sendb, sendcb

def add_hashes_to_multi(mfst, multi):
        """Takes a manifest and a multi object and adds the hashes to the multi
        object."""

        for a in mfst.gen_actions():
                if a.has_payload:
                        multi.add_action(a)

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

def fetch_catalog(src_pub, tracker, txport, target_catalog,
    include_updates=False):
        """Fetch the catalog from src_uri.

        target_catalog is a hint about whether this is a destination catalog,
        which helps the progress tracker render the refresh output properly."""

        src_uri = src_pub.repository.origins[0].uri
        tracker.refresh_start(1, full_refresh=True,
            target_catalog=target_catalog)
        tracker.refresh_start_pub(src_pub)

        if not src_pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp(dir=temp_root,
                    prefix=global_settings.client_name + "-")
                tmpdirs.append(cat_dir)
                src_pub.meta_root = cat_dir

        src_pub.transport = txport
        try:
                src_pub.refresh(full_refresh=True, immediate=True,
                    progtrack=tracker, include_updates=include_updates)
        except apx.TransportError, e:
                # Assume that a catalog doesn't exist for the target publisher,
                # and drive on.  If there was an actual failure due to a
                # transport issue, let the failure happen whenever some other
                # operation is attempted later.
                return catalog.Catalog(read_only=True)
        finally:
                tracker.refresh_end_pub(src_pub)
                tracker.refresh_done()

        return src_pub.catalog

def main_func():
        global archive, cache_dir, download_start, xport, xport_cfg, \
            dest_xport, temp_root, targ_pub, target

        all_timestamps = True
        all_versions = False
        dry_run = False
        keep_compressed = False
        list_newest = False
        recursive = False
        src_uri = None
        incoming_dir = None
        src_pub = None
        raw = False
        key = None
        cert = None
        dkey = None
        dcert = None
        publishers = []
        clone = False
        verbose = False

        temp_root = misc.config_temp_root()

        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())

        global_settings.client_name = "pkgrecv"
        target = os.environ.get("PKG_DEST", None)
        src_uri = os.environ.get("PKG_SRC", None)

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "ac:D:d:hkm:np:rs:v",
                    ["cert=", "key=", "dcert=", "dkey=", "newest", "raw",
                    "debug=", "clone"])
        except getopt.GetoptError, e:
                usage(_("Illegal option -- %s") % e.opt)

        for opt, arg in opts:
                if opt == "-a":
                        archive = True
                elif opt == "-c":
                        cache_dir = arg
                elif opt == "--clone":
                        clone = True
                elif opt == "-d":
                        target = arg
                elif opt == "-D" or opt == "--debug":
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
                elif opt == "-h":
                        usage(retcode=0)
                elif opt == "-k":
                        keep_compressed = True
                elif opt == "-m":
                        if arg == "all-timestamps":
                                all_timestamps = True
                                all_versions = False
                        elif arg == "all-versions":
                                all_timestamps = False
                                all_versions = True
                        elif arg == "latest":
                                all_timestamps = False
                                all_versions = False
                        else:
                                usage(_("Illegal option value -- %s") % arg)
                elif opt == "-n":
                        dry_run = True
                elif opt == "-p":
                        publishers.append(arg)
                elif opt == "-r":
                        recursive = True
                elif opt == "-s":
                        src_uri = arg
                elif opt == "-v":
                        verbose = True
                elif opt == "--newest":
                        list_newest = True
                elif opt == "--raw":
                        raw = True
                elif opt == "--key":
                        key = arg
                elif opt == "--cert":
                        cert = arg
                elif opt == "--dkey":
                        dkey = arg
                elif opt == "--dcert":
                        dcert = arg

        if not list_newest and not target:
                usage(_("a destination must be provided"))

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
        else:
                if clone:
                        usage(_("--clone can not be used with -c.\n"
                            "Content will be downloaded directly to the "
                            "destination repository and re-downloading after a "
                            "pkgrecv failure will not be required."))

        if clone and raw:
                usage(_("--clone can not be used with --raw.\n"))

        if clone and archive:
                usage(_("--clone can not be used with -a.\n"))

        if clone and list_newest:
                usage(_("--clone can not be used with --newest.\n"))

        if publishers and not clone:
                usage(_("-p can only be used with --clone.\n"))

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
            all_timestamps, keep_compressed, raw, recursive, dry_run, verbose,
            dest_xport_cfg, src_uri, dkey, dcert)

        if clone:
                args += (publishers,)
                return clone_repo(*args)

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
        unmatched = set(any_unmatched) - set(any_matched)

        if not unmatched:
                return

        # If any match failures remain, abort with an error.
        rval = 1
        if total_processed > 0:
                rval = 3
        abort(str(apx.PackageMatchErrors(unmatched_fmris=unmatched)),
            retcode=rval)

def get_matches(src_pub, tracker, xport, pargs, any_unmatched, any_matched,
    all_versions, all_timestamps, recursive):
        """Returns the set of matching FMRIs for the given arguments."""
        global src_cat

        src_cat = fetch_catalog(src_pub, tracker, xport, False)
        # Avoid overhead of going through matching if user requested all
        # packages.
        if "*" not in pargs and "*@*" not in pargs:
                try:
                        matches, refs, unmatched = \
                            src_cat.get_matching_fmris(pargs)
                except apx.PackageMatchErrors, e:
                        abort(str(e))

                # Track anything that failed to match.
                any_unmatched.extend(unmatched)
                any_matched.extend(set(p for p in refs.values()))
                matches = list(set(f for m in matches.values() for f in m))
        else:
                matches = [f for f in src_cat.fmris()]

        if not matches:
                # No matches at all; nothing to do for this publisher.
                return matches

        matches = prune(matches, all_versions, all_timestamps)
        if recursive:
                msg(_("Retrieving manifests for dependency "
                    "evaluation ..."))
                matches = prune(get_dependencies(matches, xport_cfg, tracker),
                    all_versions, all_timestamps)

        return matches

def archive_pkgs(pargs, target, list_newest, all_versions, all_timestamps,
    keep_compresed, raw, recursive, dry_run, verbose, dest_xport_cfg, src_uri,
    dkey, dcert):
        """Retrieve source package data completely and then archive it."""

        global cache_dir, download_start, xport, xport_cfg

        target = os.path.abspath(target)
        if os.path.exists(target):
                error(_("Target archive '%s' already "
                    "exists.") % target)
                abort()

        # Open the archive early so that permissions failures, etc. can be
        # detected before actual work is started.
        if not dry_run:
                pkg_arc = pkg.p5p.Archive(target, mode="w")

        basedir = tempfile.mkdtemp(dir=temp_root,
            prefix=global_settings.client_name + "-")
        tmpdirs.append(basedir)

        # Retrieve package data for all publishers.
        any_unmatched = []
        any_matched = []
        invalid_manifests = []
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

                matches = get_matches(src_pub, tracker, xport, pargs,
                    any_unmatched, any_matched, all_versions, all_timestamps,
                    recursive)
                if not matches:
                        # No matches at all; nothing to do for this publisher.
                        continue

                # First, retrieve the manifests and calculate package transfer
                # sizes.
                npkgs = len(matches)
                get_bytes = 0
                get_files = 0

                if not recursive:
                        msg(_("Retrieving and evaluating %d package(s)...") %
                            npkgs)


                tracker.manifest_fetch_start(npkgs)

                good_matches = []
                for f in matches:
                        try:
                                m = get_manifest(f, xport_cfg)
                        except apx.InvalidPackageErrors, e:
                                invalid_manifests.extend(e.errors)
                                continue
                        good_matches.append(f)
                        getb, getf, arcb, arccb = get_sizes(m)
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

                        tracker.manifest_fetch_progress(completion=True)
                matches = good_matches

                tracker.manifest_fetch_done()

                # Next, retrieve the content for this publisher's packages.
                tracker.download_set_goal(len(matches), get_files,
                    get_bytes)

                if verbose:
                        if not dry_run:
                                msg(_("\nArchiving packages ..."))
                        else:
                                msg(_("\nArchiving packages (dry-run) ..."))
                        status = []
                        status.append((_("Packages to add:"), str(len(matches))))
                        status.append((_("Files to retrieve:"), str(get_files)))
                        status.append((_("Estimated transfer size:"),
                            misc.bytes_to_str(get_bytes)))

                        rjust_status = max(len(s[0]) for s in status)
                        rjust_value = max(len(s[1]) for s in status)
                        for s in status:
                                msg("%s %s" % (s[0].rjust(rjust_status),
                                    s[1].rjust(rjust_value)))

                        msg(_("\nPackages to archive:"))
                        for f in sorted(matches):
                                fmri = f.get_fmri(anarchy=True,
                                    include_scheme=False)
                                msg(fmri)
                        msg()

                if dry_run:
                        # Don't call download_done here; it would cause an
                        # assertion failure since nothing was downloaded.
                        # Instead, call the method that simply finishes
                        # up the progress output.
                        tracker.download_done(dryrun=True)
                        cleanup()
                        total_processed = len(matches)
                        continue

                for f in matches:
                        tracker.download_start_pkg(f)
                        pkgdir = xport_cfg.get_pkg_dir(f)
                        mfile = xport.multi_file_ni(src_pub, pkgdir,
                            progtrack=tracker)
                        m = get_manifest(f, xport_cfg)
                        add_hashes_to_multi(m, mfile)

                        if mfile:
                                download_start = True
                                mfile.wait_files()

                        if not dry_run:
                                archive_list.append((f, m.pathname, pkgdir))

                        # Nothing more to do for this package.
                        tracker.download_end_pkg(f)
                        total_processed += 1

                tracker.download_done()
                tracker.reset()

        # Check processed patterns and abort with failure if some were
        # unmatched.
        check_processed(any_matched, any_unmatched, total_processed)

        if not dry_run:
                # Now create archive and then archive retrieved package data.
                while archive_list:
                        pfmri, mpath, pkgdir = archive_list.pop()
                        pkg_arc.add_package(pfmri, mpath, pkgdir)
                pkg_arc.close(progtrack=tracker)

        # Dump all temporary data.
        cleanup()

        if invalid_manifests:
                error(_("The following errors were encountered.  The packages "
                    "listed were not\nreceived.\n%s") %
                    "\n".join(str(im) for im in invalid_manifests))
        if invalid_manifests and total_processed:
                return pkgdefs.EXIT_PARTIAL
        if invalid_manifests:
                return pkgdefs.EXIT_OOPS
        return pkgdefs.EXIT_OK


def clone_repo(pargs, target, list_newest, all_versions, all_timestamps,
    keep_compressed, raw, recursive, dry_run, verbose, dest_xport_cfg, src_uri,
    dkey, dcert, publishers):

        global cache_dir, download_start, xport, xport_cfg, dest_xport

        invalid_manifests = []
        total_processed = 0
        modified_pubs = set()
        deleted_pkgs = False
        old_c_root = None
        del_search_index = set()

        # Turn target into a valid URI.
        target = publisher.RepositoryURI(misc.parse_uri(target))

        if target.scheme != "file":
                abort(err=_("Destination clone repository must be "
                    "filesystem-based."))

        # Initialize the target repo.
        try:
                repo = sr.Repository(read_only=False,
                    root=target.get_pathname())
        except sr.RepositoryInvalidError, e:
                txt = str(e) + "\n\n"
                txt += _("To create a repository, use the pkgrepo command.")
                abort(err=txt)

        def copy_catalog(src_cat_root, pub):
                # Copy catalog files.
                c_root = repo.get_pub_rstore(pub).catalog_root
                rstore_root = repo.get_pub_rstore(pub).root
                try:
                        # We just use mkdtemp() to find ourselves a directory
                        # which does not already exist. The created dir is not
                        # used.
                        old_c_root = tempfile.mkdtemp(dir=rstore_root,
                            prefix='catalog-')
                        shutil.rmtree(old_c_root)
                        shutil.move(c_root, old_c_root)
                        shutil.copytree(src_cat_root, c_root)
                except Exception, e:
                        abort(err=_("Unable to copy catalog files: %s") % e)
                return old_c_root

        # Check if all publishers in src are also in target. If not, add
        # depending on what publishers were specified by user.
        pubs_to_sync = []
        pubs_to_add = []
        src_pubs = {}
        for sp in xport_cfg.gen_publishers():
                src_pubs[sp.prefix] = sp
        dst_pubs = repo.get_publishers()

        pubs_specified = False
        unknown_pubs = []
        for p in publishers:
                if p not in src_pubs and p != '*':
                        abort(err=_("The publisher %s does not exist in the "
                            "source repository." % p))
                pubs_specified = True

        for sp in src_pubs:
                if sp not in dst_pubs and (sp in publishers or \
                    '*' in publishers):
                        pubs_to_add.append(src_pubs[sp])
                        pubs_to_sync.append(src_pubs[sp])
                elif sp in dst_pubs and (sp in publishers or '*' in publishers
                    or not pubs_specified):
                        pubs_to_sync.append(src_pubs[sp])
                elif not pubs_specified:
                        unknown_pubs.append(sp)

        # We only print warning if the user didn't specify any valid publishers
        # to add/sync.
        if len(unknown_pubs):
                txt = _("\nThe following publishers are present in the "
                    "source repository but not in the target repository.\n"
                    "Please use -p to specify which publishers need to be "
                    "cloned or -p '*' to clone all publishers.")
                for p in unknown_pubs:
                        txt += "\n    %s\n" % p
                abort(err=txt)

        # Create non-existent publishers.
        for p in pubs_to_add:
                if not dry_run:
                        msg(_("Adding publisher %s ...") % p.prefix)
                        # add_publisher() will create a p5i file in the repo
                        # store, containing origin and possible mirrors from
                        # the src repo. These may not be valid for the new repo
                        # so skip creation of this file.
                        repo.add_publisher(p, skip_config=True)
                else:
                        msg(_("Adding publisher %s (dry-run) ...") % p.prefix)

        for src_pub in pubs_to_sync:
                msg(_("Processing packages for publisher %s ...") %
                    src_pub.prefix)
                tracker = get_tracker()

                src_basedir = tempfile.mkdtemp(dir=temp_root,
                    prefix=global_settings.client_name + "-")
                tmpdirs.append(src_basedir)

                xport_cfg.pkg_root = src_basedir

                # We make the destination repo our cache directory to save on
                # IOPs. Have to remove all the old caches first.
                if not dry_run:
                        xport_cfg.clear_caches(shared=True)
                        xport_cfg.add_cache(
                            repo.get_pub_rstore(src_pub.prefix).file_root,
                            readonly=False)

                # Retrieve src and dest catalog for comparison.
                src_pub.meta_root = src_basedir

                src_cat = fetch_catalog(src_pub, tracker, xport, False,
                    include_updates=True)
                src_cat_root = src_cat.meta_root

                try:
                        targ_cat = repo.get_catalog(pub=src_pub.prefix)
                except sr.RepositoryUnknownPublisher:
                        targ_cat = catalog.Catalog(read_only=True)

                src_fmris = set([x for x in src_cat.fmris(last=False)])
                targ_fmris = set([x for x in targ_cat.fmris(last=False)])

                del src_cat
                del targ_cat

                to_add = []
                to_rm = []

                # We use bulk prefetching for faster transport of the manifests.
                # Prefetch requires an intent which it sends to the server. Here
                # we just use operation=clone for all FMRIs.
                intent = "operation=clone;"

                # Find FMRIs which need to be added/removed.
                to_add_set = src_fmris - targ_fmris
                to_rm = targ_fmris - src_fmris

                for f in to_add_set:
                        to_add.append((f, intent))

                del src_fmris
                del targ_fmris
                del to_add_set

                # We have to do package removal first because after the sync we
                # don't have the old catalog anymore and if we delete packages
                # after the sync based on the current catalog we might delete
                # files required by packages still in the repo.
                if len(to_rm) > 0:
                        msg(_("Packages to remove:"))
                        for f in to_rm:
                                msg("    %s" % f.get_fmri(anarchy=True,
                                    include_build=False))

                        if not dry_run:
                                msg(_("Removing packages ..."))
                                if repo.get_pub_rstore(
                                    src_pub.prefix).search_available:
                                        del_search_index.add(src_pub.prefix)
                                repo.remove_packages(to_rm, progtrack=tracker,
                                    pub=src_pub.prefix)
                                deleted_pkgs = True
                                total_processed += len(to_rm)
                                modified_pubs.add(src_pub.prefix)

                if len(to_add) == 0:
                        msg(_("No packages to add."))
                        if deleted_pkgs:
                                old_c_root = copy_catalog(src_cat_root,
                                    src_pub.prefix)
                        continue

                get_bytes = 0
                get_files = 0

                msg(_("Retrieving and evaluating %d package(s)...") %
                    len(to_add))

                # Retrieve manifests.
                # Try prefetching manifests in bulk first for faster, parallel
                # transport. Retryable errors during prefetch are ignored and
                # manifests are retrieved again during the "Reading" phase.
                src_pub.transport.prefetch_manifests(to_add, progtrack=tracker)

                # Need to change the output of mfst_fetch since otherwise we
                # would see "Download Manifests x/y" twice, once from the
                # prefetch and once from the actual manifest analysis.
                old_gti = tracker.mfst_fetch
                tracker.mfst_fetch = progress.GoalTrackerItem(
                    _("Reading Manifests"))
                tracker.manifest_fetch_start(len(to_add))
                for f, i in to_add:
                        try:
                                m = get_manifest(f, xport_cfg)
                        except apx.InvalidPackageErrors, e:
                                invalid_manifests.extend(e.errors)
                                continue
                        getb, getf, sendb, sendcb = get_sizes(m)
                        get_bytes += getb
                        get_files += getf

                        if dry_run:
                                tracker.manifest_fetch_progress(completion=True)
                                continue

                        # Move manifest into dest repo.
                        targ_path = os.path.join(
                            repo.get_pub_rstore(src_pub.prefix).root, 'pkg')
                        dp = m.fmri.get_dir_path()
                        dst_path = os.path.join(targ_path, dp)
                        src_path = os.path.join(src_basedir, dp, 'manifest')
                        dir_name = os.path.dirname(dst_path)
                        try:
                                misc.makedirs(dir_name)
                                shutil.move(src_path, dst_path)
                        except Exception, e:
                                txt = _("Unable to copy manifest: %s") % e
                                abort(err=txt)

                        tracker.manifest_fetch_progress(completion=True)

                tracker.manifest_fetch_done()
                # Restore old GoalTrackerItem for manifest download.
                tracker.mfst_fetch = old_gti

                if verbose:
                        if not dry_run:
                                msg(_("\nRetrieving packages ..."))
                        else:
                                msg(_("\nRetrieving packages (dry-run) ..."))

                        status = []
                        status.append((_("Packages to add:"), str(len(to_add))))
                        status.append((_("Files to retrieve:"), str(get_files)))
                        status.append((_("Estimated transfer size:"),
                            misc.bytes_to_str(get_bytes)))

                        rjust_status = max(len(s[0]) for s in status)
                        rjust_value = max(len(s[1]) for s in status)
                        for s in status:
                                msg("%s %s" % (s[0].rjust(rjust_status),
                                    s[1].rjust(rjust_value)))

                        msg(_("\nPackages to transfer:"))
                        for f, i in sorted(to_add):
                                fmri = f.get_fmri(anarchy=True,
                                    include_scheme=False)
                                msg("%s" % fmri)
                        msg()

                if dry_run:
                        continue

                tracker.download_set_goal(len(to_add), get_files, get_bytes)

                # Retrieve package files.
                for f, i in to_add:
                        tracker.download_start_pkg(f)
                        mfile = xport.multi_file_ni(src_pub, None,
                            progtrack=tracker)
                        m = get_manifest(f, xport_cfg)
                        add_hashes_to_multi(m, mfile)

                        if mfile:
                                mfile.wait_files()

                        tracker.download_end_pkg(f)
                        total_processed += 1

                tracker.download_done
                tracker.reset()

                modified_pubs.add(src_pub.prefix)
                old_c_root = copy_catalog(src_cat_root, src_pub.prefix)

        if invalid_manifests:
                error(_("The following packages could not be retrieved:\n%s") %
                    "\n".join(str(im) for im in invalid_manifests))

        ret = 0
        # Run pkgrepo verify to check repo.
        if total_processed:
                msg(_("\n\nVerifying repository contents."))
                cmd = os.path.join(os.path.dirname(misc.api_cmdpath()),
                    "pkgrepo")
                args = [cmd, 'verify', '-s',
                    target.get_pathname()]

                try:
                        ret = subprocess.call(args)
                except OSError, e:
                        raise RuntimeError, "cannot execute %s: %s" % (args, e)

        # Cleanup. If verification was ok, remove backup copy of old catalog.
        # If not, move old catalog back into place and remove messed up catalog.
        for pub in modified_pubs:
                c_root = repo.get_pub_rstore(pub).catalog_root
                try:
                        if ret:
                                shutil.rmtree(c_root)
                                shutil.move(old_c_root, c_root)
                        else:
                                shutil.rmtree(old_c_root)
                except Exception, e:
                        error(_("Unable to remove catalog files: %s") % e)
                        # We don't abort here to make sure we can
                        # restore/delete as much as we can.
                        continue

        if ret:
                txt = _("Pkgrepo verify found errors in the updated repository."
                    "\nThe original package catalog has been restored.\n")
                if deleted_pkgs:
                        txt += _("Deleted packages can not be restored.\n")
                txt += _("The clone operation can be retried; package content "
                    "that has already been retrieved will not be downloaded "
                    "again.")
                abort(err=txt)

        if del_search_index:
                txt = _("\nThe search index for the following publishers has "
                    "been removed due to package removals.\n")
                for p in del_search_index:
                        txt += "    %s\n" % p
                txt += _("\nTo restore the search index for all publishers run"
                    "\n'pkgrepo refresh --no-catalog -s %s'.\n") % \
                    target.get_pathname()
                msg(txt)

        cleanup()
        if invalid_manifests and total_processed:
                return pkgdefs.EXIT_PARTIAL
        if invalid_manifests:
                return pkgdefs.EXIT_OOPS
        return pkgdefs.EXIT_OK

def transfer_pkgs(pargs, target, list_newest, all_versions, all_timestamps,
    keep_compressed, raw, recursive, dry_run, verbose, dest_xport_cfg, src_uri,
    dkey, dcert):
        """Retrieve source package data and optionally republish it as each
        package is retrieved.
        """

        global cache_dir, download_start, xport, xport_cfg, dest_xport, targ_pub

        any_unmatched = []
        any_matched = []
        invalid_manifests = []
        total_processed = 0

        for src_pub in xport_cfg.gen_publishers():
                tracker = get_tracker()
                if list_newest:
                        # Make sure the prog tracker knows we're doing a listing
                        # operation so that it suppresses irrelevant output.
                        tracker.set_purpose(tracker.PURPOSE_LISTING)

                        if pargs or len(pargs) > 0:
                                usage(_("--newest takes no options"))

                        src_cat = fetch_catalog(src_pub, tracker,
                            xport, False)
                        for f in src_cat.fmris(ordered=True, last=True):
                                msg(f.get_fmri(include_build=False))
                        continue

                msg(_("Processing packages for publisher %s ...") %
                    src_pub.prefix)
                if pargs == None or len(pargs) == 0:
                        usage(_("must specify at least one pkgfmri"))

                republish = False

                if not raw:
                        basedir = tempfile.mkdtemp(dir=temp_root,
                            prefix=global_settings.client_name + "-")
                        tmpdirs.append(basedir)
                        republish = True

                        # Turn target into a valid URI.
                        target = misc.parse_uri(target)

                        # Setup target for transport.
                        targ_pub = transport.setup_publisher(target,
                            src_pub.prefix, dest_xport, dest_xport_cfg,
                            ssl_key=dkey, ssl_cert=dcert)

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
                                            "'%(dir)s': %(err)s") %
                                            {"dir": basedir, "err": e})
                                        abort()

                xport_cfg.pkg_root = basedir
                dest_xport_cfg.pkg_root = basedir

                if republish:
                        targ_cat = fetch_catalog(targ_pub, tracker,
                            dest_xport, True)

                matches = get_matches(src_pub, tracker, xport, pargs,
                    any_unmatched, any_matched, all_versions, all_timestamps,
                    recursive)
                if not matches:
                        # No matches at all; nothing to do for this publisher.
                        continue

                def get_basename(pfmri):
                        open_time = pfmri.get_timestamp()
                        return "%d_%s" % \
                            (calendar.timegm(open_time.utctimetuple()),
                            urllib.quote(str(pfmri), ""))

                # First, retrieve the manifests and calculate package transfer
                # sizes.
                npkgs = len(matches)
                get_bytes = 0
                get_files = 0
                send_bytes = 0

                if not recursive:
                        msg(_("Retrieving and evaluating %d package(s)...") %
                            npkgs)

                tracker.manifest_fetch_start(npkgs)

                pkgs_to_get = []
                while matches:
                        f = matches.pop()
                        if republish and targ_cat.get_entry(f):
                                tracker.manifest_fetch_progress(completion=True)
                                continue
                        try:
                                m = get_manifest(f, xport_cfg)
                        except apx.InvalidPackageErrors, e:
                                invalid_manifests.extend(e.errors)
                                continue
                        pkgs_to_get.append(f)

                        getb, getf, sendb, sendcb = get_sizes(m)
                        get_bytes += getb
                        get_files += getf
                        if republish:
                                # For now, normal republication always uses
                                # uncompressed data as already compressed data
                                # is not supported for publication.
                                send_bytes += sendb

                        tracker.manifest_fetch_progress(completion=True)
                tracker.manifest_fetch_done()

                # Next, retrieve and store the content for each package.
                tracker.republish_set_goal(len(pkgs_to_get), get_bytes,
                    send_bytes)

                if verbose:
                        if not dry_run:
                                msg(_("\nRetrieving packages ..."))
                        else:
                                msg(_("\nRetrieving packages (dry-run) ..."))
                        status = []
                        status.append((_("Packages to add:"),
                            str(len(pkgs_to_get))))
                        status.append((_("Files to retrieve:"),
                            str(get_files)))
                        status.append((_("Estimated transfer size:"),
                            misc.bytes_to_str(get_bytes)))

                        rjust_status = max(len(s[0]) for s in status)
                        rjust_value = max(len(s[1]) for s in status)
                        for s in status:
                                msg("%s %s" % (s[0].rjust(rjust_status),
                                    s[1].rjust(rjust_value)))

                        msg(_("\nPackages to transfer:"))
                        for f in sorted(pkgs_to_get):
                                fmri = f.get_fmri(anarchy=True,
                                    include_scheme=False)
                                msg("%s" % fmri)
                        msg()

                if dry_run:
                        tracker.republish_done(dryrun=True)
                        cleanup()
                        continue

                processed = 0
                pkgs_to_get = sorted(pkgs_to_get)
                for f in pkgs_to_get:
                        tracker.republish_start_pkg(f)
                        pkgdir = xport_cfg.get_pkg_dir(f)
                        mfile = xport.multi_file_ni(src_pub, pkgdir,
                            not keep_compressed, tracker)
                        m = get_manifest(f, xport_cfg)
                        add_hashes_to_multi(m, mfile)

                        if mfile:
                                download_start = True
                                mfile.wait_files()

                        if not republish:
                                # Nothing more to do for this package.
                                tracker.republish_end_pkg(f)
                                continue

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
                                    remote_prefix=True, ssl_key=dkey,
                                    ssl_cert=dcert)

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
                                        if a.name == "signature":
                                                # We always store content in the
                                                # repository by the least-
                                                # preferred hash.
                                                for fp in a.get_chain_certs(
                                                    least_preferred=True):
                                                        fname = os.path.join(
                                                            pkgdir, fp)
                                                        t.add_file(fname)
                                # Always defer catalog update.
                                t.close(add_to_catalog=False)
                        except trans.TransactionError, e:
                                abort(err=e)

                        # Dump data retrieved so far after each successful
                        # republish to conserve space.
                        try:
                                shutil.rmtree(dest_xport_cfg.incoming_root)
                                shutil.rmtree(pkgdir)
                                if cache_dir in tmpdirs:
                                        # If cache_dir is listed in tmpdirs,
                                        # then it's safe to dump cache contents.
                                        # Otherwise, it's a user cache directory
                                        # and shouldn't be dumped.
                                        shutil.rmtree(cache_dir)
                                        misc.makedirs(cache_dir)
                        except EnvironmentError, e:
                                raise apx._convert_error(e)
                        misc.makedirs(dest_xport_cfg.incoming_root)

                        processed += 1
                        tracker.republish_end_pkg(f)

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
        if invalid_manifests:
                error(_("The following errors were encountered.  The packages "
                    "listed were not\nreceived.\n%s") %
                    "\n".join(str(im) for im in invalid_manifests))
        if invalid_manifests and total_processed:
                return pkgdefs.EXIT_PARTIAL
        if invalid_manifests:
                return pkgdefs.EXIT_OOPS
        return pkgdefs.EXIT_OK

if __name__ == "__main__":

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                __ret = main_func()
        except (KeyboardInterrupt, apx.CanceledException):
                try:
                        cleanup(True)
                except:
                        __ret = 99
                else:
                        __ret = 1
        except (pkg.actions.ActionError, trans.TransactionError, RuntimeError,
            apx.ApiException), _e:
                error(_e)
                try:
                        cleanup(True)
                except:
                        __ret = 99
                else:
                        __ret = 1
        except PipeError:
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                try:
                        cleanup(False)
                except:
                        __ret = 99
                else:
                        __ret = 1
        except SystemExit, _e:
                try:
                        cleanup(False)
                except:
                        __ret = 99
                raise _e
        except EnvironmentError, _e:
                if _e.errno != errno.ENOSPC and _e.errno != errno.EDQUOT:
                        raise

                txt = "\n"
                if _e.errno == errno.EDQUOT:
                        txt += _("Storage space quota exceeded.")
                else:
                        txt += _("No storage space left.")

                temp_root_path = misc.get_temp_root_path()
                tdirs = [temp_root_path]
                if cache_dir not in tmpdirs:
                        # Only include in message if user specified.
                        tdirs.append(cache_dir)
                if target and target.startswith("file://"):
                        tdirs.append(target)

                txt += "\n"
                error(txt + _("Please verify that the filesystem containing "
                   "the following directories has enough space available:\n"
                   "%s") % "\n".join(tdirs))
                try:
                        cleanup()
                except:
                        __ret = 99
                else:
                        __ret = 1
        except:
                traceback.print_exc()
                error(misc.get_traceback_message())
                __ret = 99
                # Cleanup must be called *after* error messaging so that
                # exceptions processed during cleanup don't cause the wrong
                # traceback to be printed.
                try:
                        cleanup(True)
                except:
                        pass
        sys.exit(__ret)
