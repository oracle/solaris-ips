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

#
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
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

import pkg.catalog as catalog
import pkg.client.progress as progress
import pkg.fmri
import pkg.manifest as manifest
import pkg.pkgtarfile as ptf
import pkg.portable as portable
import pkg.publish.transaction as trans
import pkg.server.config as config
import pkg.server.repository as repo
import pkg.server.repositoryconfig as rc
import pkg.version as version

from pkg.client import global_settings
from pkg.misc import (emsg, get_pkg_otw_size, gunzip_from_stream, msg,
    versioned_urlopen, PipeError)

# Globals
complete_catalog = None
repo_cache = {}
tmpdirs = []

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
        pkgrecv [-s src_repo_uri] [-d (path|dest_uri)] [-k] [-m] [-n] [-r]
            (fmri|pattern) ...
        pkgrecv [-s src_repo_uri] -n

Options:
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
                        from the specified repository and exit (all other
                        options except -s will be ignored).
        -r              Recursively evaluates all dependencies for the provided
                        list of packages and adds them to the list.
        -s src_repo_uri A URI representing the location of a pkg(5)
                        repository to retrieve package data from.

Environment:
        PKG_DEST        Destination directory or repository URI
        PKG_SRC         Source repository URI"""))
        sys.exit(retcode)

def cleanup():
        """To be called at program finish."""
        for d in tmpdirs:
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

def get_manifest(src_uri, pfmri, basedir, contents=False):

        m = None
        pkgdir = os.path.join(basedir, pfmri.get_dir_path())
        mpath = os.path.join(pkgdir, "manifest")

        raw = None
        overwrite = False
        if not os.path.exists(mpath):
                raw = fetch_manifest(src_uri, pfmri)
                overwrite = True
        else:
                try:
                        raw = file(mpath, "rb").read()
                except:
                        abort(err=_("Unable to load manifest '%s' for package "
                            " '%s'.") % (mpath, pfmri))

        if contents:
                return raw

        try:
                m = manifest.CachedManifest(pfmri, basedir, None,
                    contents=raw)
        except:
                abort(err=_("Unable to parse manifest '%s' for package "
                    "'%s'") % (mpath, pfmri))

        if overwrite:
                # Overwrite the manifest file so that the on-disk version will
                # be consistent with the server (due to fmri addition).
                try:
                        f = open(mpath, "wb")
                        f.write(raw)
                        f.close()
                except:
                        abort(err=_("Unable to write manifest '%s' for package "
                           " '%s'.") % (mpath, pfmri))
        return m

def get_repo(uri):
        if uri in repo_cache:
                return repo_cache[uri]

        parts = urlparse.urlparse(uri, "file", allow_fragments=0)
        path = urllib.url2pathname(parts[2])

        scfg = config.SvrConfig(path, None, None)
        scfg.set_read_only()
        try:
                scfg.init_dirs()
        except (config.SvrConfigError, EnvironmentError), e:
                raise repo.RepositoryError(_("An error occurred while "
                    "trying to initialize the repository directory "
                    "structures:\n%s") % e)

        scfg.acquire_in_flight()

        try:
                scfg.acquire_catalog()
        except catalog.CatalogPermissionsException, e:
                raise repo.RepositoryError(str(e))

        try:
                repo_cache[uri] = repo.Repository(scfg)
        except rc.InvalidAttributeValueError, e:
                raise repo.RepositoryError(_("The specified repository's "
                    "configuration data is not valid:\n%s") % e)

        return repo_cache[uri]

def fetch_manifest(src_uri, pfmri):
        """Return the manifest data for package-fmri 'fmri' from the repository
        at 'src_uri'."""

        if src_uri.startswith("file://"):
                try:
                        r = get_repo(src_uri)
                        m = file(r.manifest(pfmri), "rb")
                except (EnvironmentError, repo.RepositoryError), e:
                        abort(err=e)
        else:
                # Request manifest from repository.
                try:
                        m = versioned_urlopen(src_uri, "manifest", [0],
                            pfmri.get_url_path())[0]
                except Exception, e:
                        abort(err=_("Unable to retrieve manifest %s from "
                            "%s: %s") % (pfmri.get_url_path(), src_uri, e))
                except:
                        abort()

        # Read from repository, return to caller.
        try:
                mfst_str = m.read()
        except:
                abort(err=_("Error occurred while reading from: %s") % src_uri)

        if hasattr(m, "close"):
                m.close()

        return mfst_str

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

        matches = catalog.extract_matching_fmris(fmri_list,
            patterns=patterns, constraint=version.CONSTRAINT_AUTO,
            counthash=counthash, matcher=pkg.fmri.glob_match)

        bail = False

        for f in patterns:
                if f not in counthash:
                        emsg(_("No match found for %s") % f.pkg_name)
                        bail = True

        if bail:
                abort()

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

        m = get_manifest(src_uri, pfmri, basedir)
        for a in m.gen_actions_by_type("depend"):
                new_fmri = expand_fmri(a.attrs["fmri"])
                if new_fmri and new_fmri not in s:
                        _get_dependencies(src_uri, s, new_fmri, basedir,
                            tracker)
        return s

def get_hashes_and_sizes(m):
        """Returns a dict of hashes and transfer sizes of actions with content
        in a manifest."""

        seen_hashes = set()
        def repeated(a):
                if a in seen_hashes:
                        return True
                seen_hashes.add(a)
                return False

        cshashes = {}
        for atype in ("file", "license"):
                for a in m.gen_actions_by_type(atype):
                        if hasattr(a, "hash") and not repeated(a.hash):
                                sz = int(a.attrs.get("pkg.size", 0))
                                csize = int(a.attrs.get("pkg.csize", 0))
                                otw_sz = get_pkg_otw_size(a)
                                cshashes[a.hash] = (sz, csize, otw_sz)
        return cshashes

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

def fetch_files_byhash(src_uri, cshashes, destdir, keep_compressed, tracker):
        """Given a list of tuples containing content hash, and size and download
        the content from src_uri into destdir."""

        def valid_file(h):
                # XXX this should check data digest
                fname = os.path.join(destdir, h)
                if os.path.exists(fname):
                        if keep_compressed:
                                sz = cshashes[h][1]
                        else:
                                sz = cshashes[h][0]

                        if sz == 0:
                                return True

                        try:
                                fs = os.stat(fname)
                        except:
                                pass
                        else:
                                if fs.st_size == sz:
                                        return True
                return False

        if src_uri.startswith("file://"):
                try:
                        r = get_repo(src_uri)
                except repo.RepositoryError, e:
                        abort(err=e)

                for h in cshashes.keys():
                        dest = os.path.join(destdir, h)

                        # Check to see if the file already exists first, so the
                        # user can continue interrupted pkgrecv operations.
                        retrieve = not valid_file(h)

                        try:
                                if retrieve and keep_compressed:
                                        src = r.file(h)
                                        shutil.copy(src, dest)
                                elif retrieve:
                                        src = file(r.file(h), "rb")
                                        outfile = open(dest, "wb")
                                        gunzip_from_stream(src, outfile)
                                        outfile.close()
                        except (EnvironmentError,
                            repo.RepositoryError), e:
                                try:
                                        portable.remove(dest)
                                except:
                                        pass
                                abort(err=e)

                        tracker.download_add_progress(1, cshashes[h][2])
                return

        req_dict = {}
        for i, k in enumerate(cshashes.keys()):
                # Check to see if the file already exists first, so the user can
                # continue interrupted pkgrecv operations.
                if valid_file(k):
                        tracker.download_add_progress(1, cshashes[k][2])
                        continue

                entry = "File-Name-%s" % i
                req_dict[entry] = k

        req_str = urllib.urlencode(req_dict)
        if not req_str:
                # Nothing to retrieve.
                return

        tmpdir = tempfile.mkdtemp()
        tmpdirs.append(tmpdir)

        try:
                f = versioned_urlopen(src_uri, "filelist", [0],
                    data=req_str)[0]
        except:
                abort(err=_("Unable to retrieve content from: %s") % src_uri)

        tar_stream = ptf.PkgTarFile.open(mode = "r|", fileobj = f)

        for info in tar_stream:
                gzfobj = None
                try:
                        if not keep_compressed:
                                # Uncompress as we retrieve the files
                                gzfobj = tar_stream.extractfile(info)
                                fpath = os.path.join(tmpdir,
                                    info.name)
                                outfile = open(fpath, "wb")
                                gunzip_from_stream(gzfobj, outfile)
                                outfile.close()
                                gzfobj.close()
                        else:
                                # We want to keep the files compressed
                                # on disk.
                                tar_stream.extract_to(info, tmpdir,
                                    info.name)

                        # Copy the file into place (rename can cause a cross-
                        # link device failure) and then remove the original.
                        src = os.path.join(tmpdir, info.name)
                        shutil.copy(src, os.path.join(destdir, info.name))
                        portable.remove(src)

                        tracker.download_add_progress(1, cshashes[info.name][2])
                except KeyboardInterrupt:
                        raise
                except:
                        abort(err=_("Unable to extract file: %s") % info.name)

        shutil.rmtree(tmpdirs.pop(), True)

        tar_stream.close()
        f.close()

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
                msg(e)

def fetch_catalog(src_uri, tracker):
        """Fetch the catalog from src_uri."""
        global complete_catalog

        tracker.catalog_start(src_uri)

        if src_uri.startswith("file://"):
                try:
                        r = get_repo(src_uri)
                        c = r.catalog()
                except repo.RepositoryError, e:
                        error(e)
                        abort()
        else:
                # open connection for catalog
                try:
                        c = versioned_urlopen(src_uri, "catalog", [0])[0]
                except:
                        abort(err=_("Unable to download catalog from: %s") % \
                            src_uri)

        # Create a temporary directory for catalog.
        cat_dir = tempfile.mkdtemp()
        tmpdirs.append(cat_dir)

        # Call catalog.recv to retrieve catalog.
        try:
                catalog.recv(c, cat_dir)
        except: 
                abort(err=_("Error while reading from: %s") % src_uri)

        if hasattr(c, "close"):
                c.close()

        cat = catalog.Catalog(cat_dir)

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
        all_timestamps = False
        all_versions = False
        keep_compressed = False
        list_newest = False
        recursive = False
        src_uri = None
        target = None

        # XXX /usr/lib/locale is OpenSolaris-specific.
        gettext.install("pkgrecv", "/usr/lib/locale")

        global_settings.client_name = "pkgrecv"
        target = os.environ.get("PKG_DEST", None)
        src_uri = os.environ.get("PKG_SRC", None)

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "d:hkm:nrs:")
        except getopt.GetoptError, e:
                usage(_("Illegal option -- %s") % e.opt)

        for opt, arg in opts:
                if opt == "-d":
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

        tracker = get_tracker()
        if list_newest:
                if pargs or len(pargs) > 0:
                        usage(_("-n takes no options"))

                fmri_list = fetch_catalog(src_uri, tracker)
                list_newest_fmris(fmri_list)
                return 0

        if pargs == None or len(pargs) == 0:
                usage(_("must specify at least one pkgfmri"))

        all_fmris = fetch_catalog(src_uri, tracker)
        fmri_arguments = pargs
        fmri_list = prune(list(set(expand_matching_fmris(all_fmris,
            fmri_arguments))), all_versions, all_timestamps)

        create_repo = False
        defer_refresh = False
        republish = False

        if not target:
                target = basedir = os.getcwd()
        elif target.find("://") != -1:
                basedir = tempfile.mkdtemp()
                tmpdirs.append(basedir)
                republish = True

                # Files have to be decompressed for republishing.
                keep_compressed = False

                # Automatically create repository at target location if it
                # doesn't exist.
                if target.startswith("file://"):
                        create_repo = True
                        # For efficiency, and publishing speed, don't update
                        # indexes until all file publishing is finished.
                        defer_refresh = True
        else:
                basedir = target
                if not os.path.exists(basedir):
                        try:
                                os.makedirs(basedir, 0755)
                        except:
                                error(_("Unable to create basedir '%s'.") % \
                                    basedir)
                                return 1

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
                m = get_manifest(src_uri, f, basedir)
                cshashes = get_hashes_and_sizes(m)

                for entry in cshashes.itervalues():
                        nfiles += 1
                        nbytes += entry[2]

                retrieve_list.append((f, cshashes))

                tracker.evaluate_progress(fmri=f)
        tracker.evaluate_done()
        tracker.reset()

        # Next, retrieve and store the content for each package.
        msg(_("Retrieving package content ..."))
        tracker.download_set_goal(len(retrieve_list), nfiles, nbytes)

        publish_list = []
        while retrieve_list:
                f, cshashes = retrieve_list.pop()
                tracker.download_start_pkg(f.get_fmri(include_scheme=False))

                if len(cshashes) > 0:
                        pkgdir = os.path.join(basedir, f.get_dir_path())
                        fetch_files_byhash(src_uri, cshashes, pkgdir,
                            keep_compressed, tracker)

                if republish:
                        publish_list.append(f)
                tracker.download_end_pkg()
        tracker.download_done()
        tracker.reset()

        # Finally, republish the packages if needed.
        while publish_list:
                f = publish_list.pop()
                msg(_("Republishing %s ...") % f)

                m = get_manifest(src_uri, f, basedir)

                # Get first line of original manifest so that inclusion of the
                # scheme can be determined.
                use_scheme = True
                contents = get_manifest(src_uri, f, basedir, contents=True)
                if contents.splitlines()[0].find("pkg:/") == -1:
                        use_scheme = False

                pkg_name = f.get_fmri(include_scheme=use_scheme)
                pkgdir = os.path.join(basedir, f.get_dir_path())

                # This is needed so any previous failures for a package
                # can be aborted.
                trans_id = get_basename(f)

                try:
                        t = trans.Transaction(target, create_repo=create_repo,
                            pkg_name=pkg_name, trans_id=trans_id)

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
                                    a.attrs.get("name", "") == "fmri":
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
                                t = trans.Transaction(target)
                                t.refresh_index()
                        except trans.TransactionError, e:
                                error(e)
                                return 1
        return 0

if __name__ == "__main__":
        try:
                __ret = main_func()
        except (pkg.actions.ActionError, trans.TransactionError,
            RuntimeError), _e:
                error(_e)
                cleanup()
                __ret = 1
        except (PipeError, KeyboardInterrupt):
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                cleanup()
                __ret = 1
        except SystemExit, _e:
                cleanup()
                raise _e
        except:
                cleanup()
                traceback.print_exc()
                error(
                    _("\n\nThis is an internal error.  Please let the "
                    "developers know about this\nproblem by filing a bug at "
                    "http://defect.opensolaris.org and including the\nabove "
                    "traceback and this message.  The version of pkg(5) is "
                    "'%s'.") % pkg.VERSION)
                __ret = 99
        sys.exit(__ret)
