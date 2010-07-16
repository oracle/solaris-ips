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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.
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
import urlparse
import warnings

import pkg.catalog as catalog
import pkg.client.progress as progress
import pkg.config as cfg
import pkg.fmri
import pkg.manifest as manifest
import pkg.client.api_errors as api_errors
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.misc as misc
import pkg.publish.transaction as trans
import pkg.search_errors as search_errors
import pkg.server.repository as sr
import pkg.version as version

from pkg.client import global_settings
from pkg.misc import (emsg, get_pkg_otw_size, msg, PipeError)

# Globals
cache_dir = None
complete_catalog = None
download_start = False
repo_cache = {}
tmpdirs = []
temp_root = None
xport = None
xport_cfg = None

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
        pkgrecv [-s src_repo_uri] [-d (path|dest_uri)] [-kr] [-m match]
            (fmri|pattern) ...
        pkgrecv [-s src_repo_uri] -n

Options:
        -c cache_dir    The path to a directory that will be used to cache
                        downloaded content.  If one is not supplied, the
                        client will automatically pick a cache directory.
                        In the case where a download is interrupted, and a
                        cache directory was automatically chosen, use this
                        option to resume the download.

        -d path_or_uri  The path of a directory to save the retrieved package
                        to, or the URI of a repository to republish it to.  If
                        not provided, the default value is the current working
                        directory.  If a directory path is provided, then
                        package content will only be retrieved if it does not
                        already exist in the target directory.  If a repository
                        URI is provided, a temporary directory will be created
                        and all of the package data retrieved before attempting
                        to republish it.

        -h              Display this usage message.
        -k              Keep the retrieved package content compressed, ignored
                        when republishing.  Should not be used with pkgsend.
        -m match        Controls matching behaviour using the following values:
                            all-timestamps
                                includes all matching timestamps, not just
                                latest (implies all-versions)
                            all-versions
                                includes all matching versions, not just latest
        -n              List the most recent versions of the packages available
                        from the specified repository and exit.  (All other
                        options except -s will be ignored.)
        -r              Recursively evaluates all dependencies for the provided
                        list of packages and adds them to the list.
        -s src_repo_uri A URI representing the location of a pkg(5)
                        repository to retrieve package data from.

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

def abort(err=None, retcode=1):
        """To be called when a fatal error is encountered."""

        if err:
                # Clear any possible output first.
                msg("")
                error(err)

        cleanup()
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

def get_manifest(pfmri, basedir, contents=False):

        m = None
        pkgdir = os.path.join(basedir, pfmri.get_dir_path())
        mpath = os.path.join(pkgdir, "manifest")

        if not os.path.exists(mpath):
                m = xport.get_manifest(pfmri)
        else:
                try:
                        m = manifest.CachedManifest(pfmri, basedir)
                except:
                        abort(err=_("Unable to parse manifest '%(mpath)s' for "
                            "package '%(pfmri)s'") % locals())

        if contents:
                return m.tostr_unsorted()

        return m

def get_repo(uri):
        if uri in repo_cache:
                return repo_cache[uri]

        parts = urlparse.urlparse(uri, "file", allow_fragments=0)
        path = urllib.url2pathname(parts[2])

        try:
                repo = sr.Repository(read_only=True, repo_root=path)
        except EnvironmentError, _e:
                error("an error occurred while trying to " \
                    "initialize the repository directory " \
                    "structures:\n%s" % _e)
                sys.exit(1)
        except sr.RepositoryError, _e:
                error(_e)
                sys.exit(1)
        except cfg.ConfigError, _e:
                error("repository configuration error: %s" % _e)
                sys.exit(1)
        except (search_errors.IndexingException,
            api_errors.PermissionsException), _e:
                emsg(str(_e), "INDEX")
                sys.exit(1)
        repo_cache[uri] = repo
        return repo

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
        counthash = {}

        try:
                patterns = [
                    pkg.fmri.MatchingPkgFmri(s, "5.11")
                    for s in pfmri_strings
                ]
        except pkg.fmri.FmriError, e:
                abort(err=e)

        # XXX publisher prefixes have to be stripped for catalog matching
        # for now; awaits v1 client support, etc.
        pattern_pubs = {}
        for f in patterns:
                if f.publisher:
                        pattern_pubs[f.get_fmri(anarchy=True)] = f.publisher
                        f.publisher = None

        matches, unmatched = catalog.extract_matching_fmris(fmri_list,
            patterns=patterns, constraint=version.CONSTRAINT_AUTO,
            matcher=pkg.fmri.glob_match)

        if unmatched:
                match_err = api_errors.InventoryException(**unmatched)
                emsg(match_err)
                abort()

        # XXX restore stripped publisher information.
        for m in matches:
                pub = pattern_pubs.pop(str(m), None)
                if pub:
                        m.publisher = pub
        return matches

def get_dependencies(src_uri, fmri_list, basedir, tracker):

        old_limit = sys.getrecursionlimit()
        # The user may be recursing 'entire' or 'redistributable'.
        sys.setrecursionlimit(3000)

        s = set()
        for f in fmri_list:
                pfmri = expand_fmri(f)
                _get_dependencies(src_uri, s, pfmri, basedir, tracker)

        # Restore the previous default.
        sys.setrecursionlimit(old_limit)

        return list(s)

def _get_dependencies(src_uri, s, pfmri, basedir, tracker):
        """Expand all dependencies."""
        tracker.evaluate_progress(fmri=pfmri)
        s.add(pfmri)

        m = get_manifest(pfmri, basedir)
        for a in m.gen_actions_by_type("depend"):
                new_fmri = expand_fmri(a.attrs["fmri"])
                if new_fmri and new_fmri not in s:
                        _get_dependencies(src_uri, s, new_fmri, basedir,
                            tracker)
        return s

def add_hashes_to_multi(mfst, multi):
        """Takes a manifest and a multi object. Adds the hashes to the
        multi object, returns (nfiles, nbytes) tuple."""

        nf = 0
        nb = 0

        for atype in ("file", "license"):
                for a in mfst.gen_actions_by_type(atype):
                        if a.needsdata(None, None):
                                multi.add_action(a)
                                nf += 1
                                nb += get_pkg_otw_size(a)
        return nf, nb

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
                msg(e.get_fmri(anarchy=True))

def fetch_catalog(src_pub, tracker):
        """Fetch the catalog from src_uri."""
        global complete_catalog

        src_uri = src_pub.selected_repository.origins[0].uri
        tracker.catalog_start(src_uri)

        if not src_pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp(dir=temp_root)
                tmpdirs.append(cat_dir)
                src_pub.meta_root = cat_dir

        src_pub.transport = xport
        src_pub.refresh(True, True)

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

def config_temp_root():
        """Examine the environment.  If the environment has set TMPDIR, TEMP,
        or TMP, return None.  This tells tempfile to use the environment
        settings when creating temporary files/directories.  Otherwise,
        return a path that the caller should pass to tempfile instead."""

        default_root = "/var/tmp"

        # In Python's tempfile module, the default temp directory
        # includes some paths that are suboptimal for holding large numbers
        # of files.  If the user hasn't set TMPDIR, TEMP, or TMP in the
        # environment, override the default directory for creating a tempfile.
        tmp_envs = [ "TMPDIR", "TEMP", "TMP" ]
        for ev in tmp_envs:
                env_val = os.getenv(ev)
                if env_val:
                        return None

        return default_root

def main_func():
        global cache_dir, download_start, xport, xport_cfg
        all_timestamps = False
        all_versions = False
        keep_compressed = False
        list_newest = False
        recursive = False
        src_uri = None
        target = None
        incoming_dir = None
        src_pub = None
        targ_pub = None

        temp_root = config_temp_root()

        gettext.install("pkg", "/usr/share/locale")

        global_settings.client_name = "pkgrecv"
        target = os.environ.get("PKG_DEST", None)
        src_uri = os.environ.get("PKG_SRC", None)

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "c:d:hkm:nrs:")
        except getopt.GetoptError, e:
                usage(_("Illegal option -- %s") % e.opt)

        for opt, arg in opts:
                if opt == "-c":
                        cache_dir = arg
                elif opt == "-d":
                        target = arg
                elif opt == "-h":
                        usage(retcode=0)
                elif opt == "-k":
                        keep_compressed = True
                elif opt == "-n":
                        list_newest = True
                elif opt == "-r":
                        recursive = True
                elif opt == "-s":
                        src_uri = arg
                elif opt == "-m":
                        if arg == "all-timestamps":
                                all_timestamps = True
                        elif arg == "all-versions":
                                all_versions = True
                        else:
                                usage(_("Illegal option value -- %s") % arg)

        if not src_uri:
                usage(_("a source repository must be provided"))

        if not cache_dir:
                cache_dir = tempfile.mkdtemp(dir=temp_root)
                # Only clean-up cache dir if implicitly created by pkgrecv.
                # User's cache-dirs should be preserved
                tmpdirs.append(cache_dir)

        incoming_dir = tempfile.mkdtemp(dir=temp_root)
        tmpdirs.append(incoming_dir)

        # Create transport and transport config
        xport, xport_cfg = transport.setup_transport()
        xport_cfg.cached_download_dir = cache_dir
        xport_cfg.incoming_download_dir = incoming_dir

        # Configure src publisher
        src_pub = transport.setup_publisher(src_uri, "source", xport, xport_cfg,
            remote_publishers=True)

        tracker = get_tracker()
        if list_newest:
                if pargs or len(pargs) > 0:
                        usage(_("-n takes no options"))

                fmri_list = fetch_catalog(src_pub, tracker)
                list_newest_fmris(fmri_list)
                return 0

        if pargs == None or len(pargs) == 0:
                usage(_("must specify at least one pkgfmri"))

        defer_refresh = False
        republish = False

        if not target:
                target = basedir = os.getcwd()
        elif target.find("://") != -1:
                basedir = tempfile.mkdtemp(dir=temp_root)
                tmpdirs.append(basedir)
                republish = True

                targ_pub = transport.setup_publisher(target, "target",
                    xport, xport_cfg)

                # Files have to be decompressed for republishing.
                keep_compressed = False
                if target.startswith("file://"):
                        # For efficiency, and publishing speed, don't update
                        # indexes until all file publishing is finished.
                        defer_refresh = True

                        # Check to see if the repository exists first.
                        try:
                                t = trans.Transaction(target, xport=xport,
                                    pub=targ_pub)
                        except trans.TransactionRepositoryInvalidError, e:
                                txt = str(e) + "\n\n"
                                txt += _("To create a repository, use the "
                                    "pkgsend command.")
                                abort(err=txt)
                        except trans.TransactionRepositoryConfigError, e:
                                txt = str(e) + "\n\n"
                                txt += _("The repository configuration for "
                                    "the repository located at '%s' is not "
                                    "valid or the specified path does not "
                                    "exist.  Please correct the configuration "
                                    "of the repository or create a new "
                                    "one.") % target
                                abort(err=txt)
                        except trans.TransactionError, e:
                                abort(err=e)
        else:
                basedir = target
                if not os.path.exists(basedir):
                        try:
                                os.makedirs(basedir, misc.PKG_DIR_MODE)
                        except:
                                error(_("Unable to create basedir '%s'.") % \
                                    basedir)
                                return 1

        xport_cfg.pkgdir = basedir

        all_fmris = fetch_catalog(src_pub, tracker)
        fmri_arguments = pargs
        fmri_list = prune(list(set(expand_matching_fmris(all_fmris,
            fmri_arguments))), all_versions, all_timestamps)

        if recursive:
                msg(_("Retrieving manifests for dependency evaluation ..."))
                tracker.evaluate_start()
                fmri_list = prune(get_dependencies(src_uri, fmri_list, basedir,
                    tracker), all_versions, all_timestamps)
                tracker.evaluate_done()

        def get_basename(pfmri):
                open_time = pfmri.get_timestamp()
                return "%d_%s" % \
                    (calendar.timegm(open_time.utctimetuple()),
                    urllib.quote(str(pfmri), ""))

        # First, retrieve the manifests and calculate package transfer sizes.
        npkgs = len(fmri_list)
        nfiles = 0
        nbytes = 0

        if not recursive:
                msg(_("Retrieving manifests for package evaluation ..."))

        tracker.evaluate_start(npkgs=npkgs)
        retrieve_list = []
        while fmri_list:
                f = fmri_list.pop()
                m = get_manifest(f, basedir)
                pkgdir = os.path.join(basedir, f.get_dir_path())
                mfile = xport.multi_file_ni(src_pub, pkgdir,
                    not keep_compressed, tracker)
 
                nf, nb = add_hashes_to_multi(m, mfile)
                nfiles += nf
                nbytes += nb

                retrieve_list.append((f, mfile))

                tracker.evaluate_progress(fmri=f)
        tracker.evaluate_done()

        # Next, retrieve and store the content for each package.
        msg(_("Retrieving package content ..."))
        tracker.download_set_goal(len(retrieve_list), nfiles, nbytes)

        publish_list = []
        while retrieve_list:
                f, mfile = retrieve_list.pop()
                tracker.download_start_pkg(f.get_fmri(include_scheme=False))

                if mfile:
                        mfile.wait_files()
                        if not download_start:
                                download_start = True

                if republish:
                        publish_list.append(f)
                tracker.download_end_pkg()
        tracker.download_done()
        tracker.reset()

        # Finally, republish the packages if needed.
        while publish_list:
                f = publish_list.pop()
                msg(_("Republishing %s ...") % f)

                m = get_manifest(f, basedir)

                # Get first line of original manifest so that inclusion of the
                # scheme can be determined.
                use_scheme = True
                contents = get_manifest(f, basedir, contents=True)
                if contents.splitlines()[0].find("pkg:/") == -1:
                        use_scheme = False

                pkg_name = f.get_fmri(include_scheme=use_scheme)
                pkgdir = os.path.join(basedir, f.get_dir_path())

                # This is needed so any previous failures for a package
                # can be aborted.
                trans_id = get_basename(f)

                if not targ_pub:
                        targ_pub = transport.setup_publisher(target, "target",
                            xport, xport_cfg)

                try:
                        t = trans.Transaction(target, pkg_name=pkg_name,
                            trans_id=trans_id, refresh_index=not defer_refresh,
                            xport=xport, pub=targ_pub)

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
                                        # To be consistent with the server,
                                        # the fmri can't be added to the
                                        # manifest.
                                        continue

                                if hasattr(a, "hash"):
                                        fname = os.path.join(pkgdir,
                                            a.hash)
                                        a.data = lambda: open(fname,
                                            "rb")
                                t.add(a)
                        t.close(refresh_index=not defer_refresh)
                except trans.TransactionError, e:
                        abort(err=e)
                        return 1

        # Dump all temporary data.
        cleanup()

        if republish:
                if defer_refresh:
                        msg(_("Refreshing repository search indices ..."))
                        try:
                                t = trans.Transaction(target, xport=xport,
                                    pub=targ_pub)
                                t.refresh_index()
                        except trans.TransactionError, e:
                                error(e)
                                return 1
        return 0

if __name__ == "__main__":

        # Make all warnings be errors.
        warnings.simplefilter('error')

        try:
                __ret = main_func()
        except (pkg.actions.ActionError, trans.TransactionError,
            RuntimeError, api_errors.TransportError,
            api_errors.BadRepositoryURI,
            api_errors.UnsupportedRepositoryURI), _e:
                error(_e)
                cleanup(True)
                __ret = 1
        except PipeError:
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                cleanup(False)
                __ret = 1
        except (KeyboardInterrupt, api_errors.CanceledException):
                cleanup(True)
                __ret = 1
        except SystemExit, _e:
                cleanup(False)
                raise _e
        except:
                cleanup(True)
                traceback.print_exc()
                error(
                    _("\n\nThis is an internal error.  Please let the "
                    "developers know about this\nproblem by filing a bug at "
                    "http://defect.opensolaris.org and including the\nabove "
                    "traceback and this message.  The version of pkg(5) is "
                    "'%s'.") % pkg.VERSION)
                __ret = 99
        sys.exit(__ret)
