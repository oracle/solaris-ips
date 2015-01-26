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
# Copyright (c) 2013, 2015, Oracle and/or its affiliates. All rights reserved.
#

#
# pkgsurf - Detailed operation description:
#
# After determining the packages present in the target repo, pkgsurf tries to
# find the associated version of each package in the reference repo. Packages
# which can't be found in the reference are ignored (not reversioned). Only the
# latest version of the reference packages are considered. 
# We then compare the target and ref manifest for content changes. Any
# difference in the manifests' actions is considered a content change unless
# they differ in:
#  - the pkg FMRI (since this is what we'll adjust anyway)
#  - a set action whose name attribute is specified with -i/--ignore
#  - a signature action (signature will change when FMRI changes)
#  - a depend action (see below)
#   
# Changes in depend actions are not considered a content change, however,
# further analysis is required since the package can only be reversioned if the
# dependency package didn't have a content change and its dependencies didn't
# have a content change either.
#
# For the depend actions it is therefore required to recurse through the whole
# dependency chain to determine a content change. Only if no package in the
# chain had a content change the can the manifest be reversioned.
#
# Reversioning certain packages will break the inter-dependency integrity of the
# target repo since certain package versions might not be available any longer.
# Therefore pkgsurf will go through all depend actions in the repo and, if they
# point to a reversioned package, adjust them to the correct version.
# This requires that signature actions in these adjusted packages need to be
# dropped since the manifest data changed.
#
# In the regular case, the new dependency FMRI of a certain package is taken
# from the associated manifest of the reference version of this package.
# However, if dependencies got added/removed it might not be found. In this case
# pkgsurf uses the FMRI of the actual package which got reversioned as the new
# dependency FMRI.
#
# pkgsurf deletes and inserts manifests in place for the target repo. File data
# does not need to be modified since we only operate on packages with no content
# change. It runs a catalog rebuild as the last step to regain catalog integrity
# within the repo. 

import getopt
import gettext
import locale
import os
import shutil
import sys
import tempfile
import traceback

from itertools import repeat

import pkg.actions as actions
import pkg.client.api_errors as api_errors
import pkg.client.pkgdefs as pkgdefs
import pkg.client.progress as progress
import pkg.client.publisher as publisher
import pkg.client.transport.transport as transport
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.portable as portable
import pkg.server.repository as sr

from pkg.client import global_settings
from pkg.misc import emsg, msg, PipeError

PKG_CLIENT_NAME = "pkgsurf"

temp_root = None
repo_modified = False
repo_finished = False
repo_uri = None

def error(text, cmd=None):
        """Emit an error message prefixed by the command name """

        if cmd:
                text = "\n{0}: {1}".format(cmd, text)

        else:
                text = "\n{0}: {1}".format(PKG_CLIENT_NAME, text)


        # If the message starts with whitespace, assume that it should come
        # *before* the command-name prefix.
        text_nows = text.lstrip()
        ws = text[:len(text) - len(text_nows)]

        # This has to be a constant value as we can't reliably get our actual
        # program name on all platforms.
        emsg(ws + text_nows)

def cleanup(no_msg=False):
	"""Remove temporary directories. Print error msg in case operation
        was not finished."""

        global temp_root

        if repo_modified and not repo_finished and not no_msg:
                error(_("""
The target repository has been modified but the operation did not finish
successfully. It is now in an inconsistent state.

To re-try the operation, run the following commands:
  /usr/bin/pkgrepo rebuild -s {repo} --no-index
  {argv}
""").format(repo=repo_uri, argv=" ".join(sys.argv)))

        if temp_root:
                shutil.rmtree(temp_root)
                temp_root = None

def usage(usage_error=None, cmd=None, retcode=pkgdefs.EXIT_BADOPT):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if usage_error:
                error(usage_error, cmd=cmd)

        emsg(_("""\
Usage:
        pkgsurf -s target_path -r ref_uri [-n] [-p publisher ...] [-i name ...]
            [-c pattern ...]

Options:
        -c pattern      Treat every package whose FMRI matches 'pattern' as 
                        changed and do not reversion it. Can be specified
                        multiple times.

        -i name         Ignore set actions with the name field set to 'name' for
                        determination of content change.  Can be specified
                        multiple times.

        -n              Perform a trial run with no changes made.

        -p publisher    Only operate on given publisher. Can be specified
                        multiple times.

        -r ref_uri      URI of reference repository.

        -s target_path  Path to target repository. Repository should only
                        contain one version of each package. Must be a
                        filesystem-based repository.

        -?/--help       Print this message.
"""))


        sys.exit(retcode)

def abort(err=None, retcode=pkgdefs.EXIT_OOPS):
        """To be called when a fatal error is encountered."""

        if err:
                # Clear any possible output first.
                msg("")
                error(err)

        cleanup()
        sys.exit(retcode)

def fetch_catalog(src_pub, xport, temp_root):
        """Fetch the catalog from src_uri."""

        if not src_pub.meta_root:
                # Create a temporary directory for catalog.
                cat_dir = tempfile.mkdtemp(dir=temp_root)
                src_pub.meta_root = cat_dir

        src_pub.transport = xport
        src_pub.refresh(full_refresh=True, immediate=True)

        return src_pub.catalog

def get_latest(cat):
        """ Get latest packages (surface) from given catalog.
        Returns a dict of the form:
                { pkg-name: pkg-fmri, ... }
        """
        matching, ref, unmatched = cat.get_matching_fmris(["*@latest"])

        del ref

        matches = {}
        for m in matching:
                matches[m] = matching[m][0]

        return matches

def get_matching_pkgs(cat, patterns):
        """Get the matching pkg FMRIs from catalog 'cat' based on the input
        patterns 'patterns'."""

        versions = set()
        for p in patterns:
                if "@" in p:
                     versions.add(p)

        if versions:
                msg = _("Packages specified to not be reversioned cannot "
                    "contain versions:\n\t")
                msg += "\n\t".join(versions)
                abort(msg)

        matching, ref, unmatched = cat.get_matching_fmris(patterns)

        if unmatched:
                msg = _("The specified packages were not found in the "
                    "repository:\n\t")
                msg += "\n\t".join(unmatched)
                abort(msg)

        return matching.keys()

def get_manifest(repo, pub, pfmri):
        """ Retrieve a manifest with FMRI 'pfmri' of publisher 'pub' from
        repository object 'repo'. """

        path = repo.manifest(pfmri, pub)
        mani = manifest.Manifest(pfmri)
        try:
                mani.set_content(pathname=path)
        except Exception, e:
                abort(err=_("Can not open manifest file {file}: {err}\n"
                    "Please run 'pkgrepo verify -s {rroot}' to check the "
                    "integrity of the repository.").format(
                    file=path, err=str(e), rroot=repo.root))
        return mani

def get_tracker():
        try:
                progresstracker = \
                    progress.FancyUNIXProgressTracker()
        except progress.ProgressTrackerException:
                progresstracker = progress.CommandLineProgressTracker()
        progresstracker.set_major_phase(progresstracker.PHASE_UTILITY)
        return progresstracker

def subs_undef_fmri_str(fmri_str, latest_ref_pkgs):
        """ Substitute correct dependency FMRI if no counterpart can be found in
        the reference manifest. Use the original FMRI in case the current
        version of dependency pkg in the repo is still a successor of the
        specified dependency FMRI, otherwise substitute the complete version of
        the pkg currently present in the repo."""

        dpfmri = fmri.PkgFmri(fmri_str)
        ndpfmri = latest_ref_pkgs[dpfmri.get_name()]

        if ndpfmri.is_successor(dpfmri):
                return fmri_str

        return ndpfmri.get_short_fmri(anarchy=True)

def get_dep_fmri_str(fmri_str, pkg, act, latest_ref_pkgs, reversioned_pkgs,
    ref_xport):
        """Get the adjusted dependency FMRI of package 'pkg' specified in
        action 'act' based on if the FMRI belongs to a reversioned package or
        not. 'fmri_str' contains the original FMRI string from the manifest to
        be adjusted. This has to be passed in separately since in case of
        require-any dependencies an action can contain multiple FMRIs. """

        dpfmri = fmri.PkgFmri(fmri_str)

        # Versionless dependencies don't need to be changed.
        if not dpfmri.version:
                return fmri_str

        # Dep package hasn't been changed, no adjustment necessary.
        if dpfmri.get_pkg_stem() not in reversioned_pkgs:
                return fmri_str                

        # Find the dependency action of the reference package
        # and replace the current version with it.
        try:
                ref_mani = ref_xport.get_manifest(latest_ref_pkgs[pkg])
        except KeyError:
                # This package is not in the ref repo so we just substitute the
                # dependency.
                return subs_undef_fmri_str(fmri_str, latest_ref_pkgs)

        for ra in ref_mani.gen_actions_by_type("depend"):
                # Any difference other than the FMRI means we
                # can't use this action as a reference.
                diffs = act.differences(ra)
                if "fmri" in diffs:
                        diffs.remove("fmri")
                if diffs:
                        continue

                fmris = ra.attrlist("fmri")

                for rf in fmris:
                        rpfmri = fmri.PkgFmri(rf)
                        if rpfmri.get_pkg_stem() != dpfmri.get_pkg_stem():
                                continue

                        # Only substitute dependency if it actually
                        # changed.
                        if not rpfmri.version \
                            or rpfmri.get_version() != dpfmri.get_version():
                                return rf

                        return fmri_str

        # If a varcet changed we might not find the matching action.
        return subs_undef_fmri_str(fmri_str, latest_ref_pkgs)

def adjust_dep_action(pkg, act, latest_ref_pkgs, reversioned_pkgs, ref_xport):
        """Adjust dependency FMRIs of action 'act' if it is of type depend.
        The adjusted action will reference only FMRIs which are present in the
        reversioned repo. """

        modified = False

        # Drop signatures (changed dependency will void signature value).
        if act.name == "signature":
                return
        # Ignore anything other than depend actions.
        elif act.name != "depend":
                return act

        # Require-any deps are list so convert every dep FMRI into a list.
        fmris = act.attrlist("fmri")

        new_dep = []
        for f in fmris:
                new_f = get_dep_fmri_str(f, pkg, act, latest_ref_pkgs,
                    reversioned_pkgs, ref_xport)
                if not modified and f != new_f:
                        modified = True
                new_dep.append(new_f)

        if not modified:
                return act

        if len(new_dep) == 1:
                new_dep = new_dep[0]

        nact = actions.fromstr(str(act))
        nact.attrs["fmri"] = new_dep

        return nact

def use_ref(a, deps, ignores):
        """Determine if the given action indicates that the pkg can be
        reversioned."""

        if a.name == "set" and "name" in a.attrs:
                if a.attrs["name"] in ignores:
                        return True
                # We ignore the pkg FMRI because this is what 
                # will always change.
                if a.attrs["name"] == "pkg.fmri":
                        return True

        # Signature will always change.
        if a.name == "signature":
                return True

        if a.name == "depend":
                # TODO: support dependency lists
                # For now, treat as content change.
                if not isinstance(a.attrs["fmri"], basestring):
                        return False
                dpfmri = fmri.PkgFmri(a.attrs["fmri"])
                deps.add(dpfmri.get_pkg_stem())
                return True

        return False

def do_reversion(pub, ref_pub, target_repo, ref_xport, changes, ignores):
        """Do the repo reversion.
        Return 'True' if repo got modified, 'False' otherwise."""

        global temp_root, tracker, dry_run, repo_finished, repo_modified

        target_cat = target_repo.get_catalog(pub=pub)
        ref_cat = fetch_catalog(ref_pub, ref_xport, temp_root)

        latest_pkgs = get_latest(target_cat)
        latest_ref_pkgs = get_latest(ref_cat)

        no_revs = get_matching_pkgs(target_cat, changes)

        # We use bulk prefetching for faster transport of the manifests.
        # Prefetch requires an intent which it sends to the server. Here
        # we just use operation=reversion for all FMRIs.
        intent = "operation=reversion;"
        ref_pkgs = zip(latest_ref_pkgs.values(), repeat(intent))

        # Retrieve reference manifests.
        # Try prefetching manifests in bulk first for faster, parallel
        # transport. Retryable errors during prefetch are ignored and
        # manifests are retrieved again during the "Reading" phase.
        ref_xport.prefetch_manifests(ref_pkgs, progtrack=tracker)

        # Need to change the output of mfst_fetch since otherwise we
        # would see "Download Manifests x/y" twice, once from the
        # prefetch and once from the actual manifest analysis.
        tracker.mfst_fetch = progress.GoalTrackerItem(_("Analyzing Manifests"))

        tracker.manifest_fetch_start(len(latest_pkgs))

        reversioned_pkgs = set()
        depend_changes = {}
        dups = 0   # target pkg has equal version to ref pkg
        new_p = 0  # target pkg not in ref
        sucs = 0   # ref pkg is successor to pkg in targ
        nrevs = 0  # pkgs requested to not be reversioned by user

        for p in latest_pkgs:
                # First check if the package is in the list of FMRIs the user
                # doesn't want to reversion.
                if p in no_revs:
                        nrevs += 1
                        tracker.manifest_fetch_progress(completion=True)
                        continue

                # Check if the package is in the ref repo, if not: ignore.
                if not p in latest_ref_pkgs:
                        new_p += 1
                        tracker.manifest_fetch_progress(completion=True)
                        continue

                pfmri = latest_pkgs[p]
                # Ignore if latest package is the same in targ and ref.
                if pfmri == latest_ref_pkgs[p]:
                        dups += 1
                        tracker.manifest_fetch_progress(completion=True)
                        continue

                # Ignore packages where ref version is higher.
                if latest_ref_pkgs[p].is_successor(pfmri):
                        sucs += 1
                        tracker.manifest_fetch_progress(completion=True)
                        continue

                # Pull the manifests for target and ref repo.
                dm = get_manifest(target_repo, pub, pfmri)
                rm = ref_xport.get_manifest(latest_ref_pkgs[p])
                tracker.manifest_fetch_progress(completion=True)

                tdeps = set()
                rdeps = set()

                # Diff target and ref manifest.
                # action only in targ, action only in ref, common action
                ta, ra, ca = manifest.Manifest.comm([dm, rm])

                # Check for manifest changes.
                if not all(use_ref(a, tdeps, ignores) for a in ta) \
                    or not all(use_ref(a, rdeps, ignores) for a in ra):
                        continue

                # Both dep lists should be equally long in case deps have just 
                # changed. If not, it means a dep has been added or removed and
                # that means content change.
                if len(tdeps) != len(rdeps):
                        continue

                # If len is not different we still have to make sure that 
                # entries have the same pkg stem. The test above just saves time
                # in some cases.
                if not all(td in rdeps for td in tdeps):
                        continue

                # Pkg only contains dependency change. Keep for further
                # analysis.
                if tdeps:
                        depend_changes[pfmri.get_pkg_stem(
                            anarchy=True)] = tdeps
                        continue

                # Pkg passed all checks and can be reversioned.
                reversioned_pkgs.add(pfmri.get_pkg_stem(anarchy=True))

        tracker.manifest_fetch_done()

        def has_changed(pstem, seen=None, depth=0):
                """Determine if a package or any of its dependencies has
                changed.
                Function will check if a dependency had a content change. If it
                only had a dependency change, analyze its dependencies 
                recursively. Only if the whole dependency chain didn't have any
                content change it is safe to reversion the package. 

                Note about circular dependencies: The function keeps track of 
                pkgs it already processed by stuffing them into the set 'seen'.
                However, 'seen' gets updated before the child dependencies of 
                the current pkg are examined. This works if 'seen' is only used
                for one dependency chain since the function immediately comes 
                back with a True result if a pkg has changed further down the
                tree. However, if 'seen' is re-used between runs, it will
                return prematurely, likely returning wrong results. """

                MAX_DEPTH = 100

                if not seen:
                        seen = set()

                if pstem in seen:
                        return False

                depth += 1
                if depth > MAX_DEPTH:
                        # Let's make sure we don't run into any
                        # recursion limits. If the dep chain is too deep
                        # just treat as changed pkg.
                        error(_("Dependency chain depth of >{md:d} detected for"
                            " {p}.").format(md=MAX_DEPTH, p=p))
                        return True

                # Pkg has no change at all.
                if pstem in reversioned_pkgs:
                        return False

                # Pkg must have content change, if it had no change it would be
                # in reversioned_pkgs, and if it had just a dep change it would
                # be in depend_changes.
                if pstem not in depend_changes:
                        return True

                # We need to update 'seen' here, otherwise we won't find this
                # entry in case of a circular dependency.
                seen.add(pstem)

                return any(
                    has_changed(d, seen, depth)
                    for d in depend_changes[pstem]
                )

        # Check if packages which just have a dep change can be reversioned by
        # checking if child dependencies also have no content change.
        dep_revs = 0
        for p in depend_changes:
                if not has_changed(p):
                        dep_revs += 1
                        reversioned_pkgs.add(p)

        status = []
        status.append((_("Packages to process:"), str(len(latest_pkgs))))
        status.append((_("New packages:"), str(new_p)))
        status.append((_("Unmodified packages:"), str(dups)))
        if sucs:
                # This only happens if reference repo is ahead of target repo,
                # so only show if it actually happened.
                status.append((_("Packages with successors in "
                    "reference repo:"), str(sucs)))
        if nrevs:
                # This only happens if user specified pkgs to not revert,
                # so only show if it actually happened.
                status.append((_("Packages not to be reversioned by user "
                    "request:"), str(nrevs)))
        status.append((_("Packages with no content change:"),
            str(len(reversioned_pkgs) - dep_revs)))
        status.append((_("Packages which only have dependency change:"),
            str(len(depend_changes))))
        status.append((_("Packages with unchanged dependency chain:"),
            str(dep_revs)))
        status.append((_("Packages to be reversioned:"),
            str(len(reversioned_pkgs))))

        rjust_status = max(len(s[0]) for s in status)
        rjust_value = max(len(s[1]) for s in status)
        for s in status:
                msg("{0} {1}".format(s[0].rjust(rjust_status),
                    s[1].rjust(rjust_value)))

        if not reversioned_pkgs:
                msg(_("\nNo packages to reversion."))
                return False

        if dry_run:
                msg(_("\nReversioning packages (dry-run)."))
        else:
                msg(_("\nReversioning packages."))

        # Start the main pass. Reversion packages from reversioned_pkgs to the
        # version in the ref repo. For packages which don't get reversioned,
        # check if the dependency versions are still correct, fix if necessary.
        tracker.reversion_start(len(latest_pkgs), len(reversioned_pkgs))

        for p in latest_pkgs:
                tracker.reversion_add_progress(pfmri, pkgs=1)
                modified = False

                # Get the pkg fmri (pfmri) of the latest version based on if it
                # has been reversioned or not.
                stem = latest_pkgs[p].get_pkg_stem(anarchy=True)
                if stem in reversioned_pkgs:
                        tracker.reversion_add_progress(pfmri, reversioned=1)
                        if dry_run:
                                continue
                        pfmri = latest_ref_pkgs[p]
                        # Retrieve manifest from ref repo and replace the one in
                        # the target repo. We don't have to adjust depndencies
                        # for these packages because they will not depend on
                        # anything we'll reversion.
                        rmani = ref_xport.get_manifest(pfmri)
                        opath = target_repo.manifest(latest_pkgs[p], pub)
                        os.remove(opath)
                        path = target_repo.manifest(pfmri, pub)
                        try:
                                repo_modified = True
                                repo_finished = False
                                portable.rename(rmani.pathname, path)
                        except OSError, e:
                                abort(err=_("Could not reversion manifest "
                                    "{path}: {err}").format(path=path,
                                    err=str(e)))
                        continue

                # For packages we don't reversion we have to check if they 
                # depend on a reversioned package.
                # Since the version of this dependency might be removed from the
                # repo, we have to adjust the dep version to the one of the
                # reversioned pkg.
                pfmri = latest_pkgs[p]
                omani = get_manifest(target_repo, pub, pfmri)
                mani = manifest.Manifest(pfmri)
                for act in omani.gen_actions():
                        nact = adjust_dep_action(p, act, latest_ref_pkgs,
                            reversioned_pkgs, ref_xport)
                        if nact:
                                mani.add_action(nact, misc.EmptyI)
                                if nact is not act:
                                        modified = True

                # Only touch manifest if something actually changed.
                if modified:
                        tracker.reversion_add_progress(pfmri, adjusted=1)
                        if not dry_run:
                                path = target_repo.manifest(pfmri, pub)
                                repo_modified = True
                                repo_finished = False
                                mani.store(path)
        tracker.reversion_done()

        return True

def main_func():

        global temp_root, repo_modified, repo_finished, repo_uri, tracker
        global dry_run

        misc.setlocale(locale.LC_ALL, "", error)
        gettext.install("pkg", "/usr/share/locale",
            codeset=locale.getpreferredencoding())
        global_settings.client_name = PKG_CLIENT_NAME

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "?c:i:np:r:s:",
                    ["help"])
        except getopt.GetoptError, e:
                usage(_("illegal option -- {0}").format(e.opt))

        dry_run = False
        ref_repo_uri = None
        repo_uri = os.getenv("PKG_REPO", None)
        changes = set()
        ignores = set()
        publishers = set()
        
        processed_pubs = 0

        for opt, arg in opts:
                if opt == "-c":
                        changes.add(arg)
                elif opt == "-i":
                        ignores.add(arg)
                elif opt == "-n":
                        dry_run = True
                elif opt == "-p":
                        publishers.add(arg)
                elif opt == "-r":
                        ref_repo_uri = misc.parse_uri(arg)
                elif opt == "-s":
                        repo_uri = misc.parse_uri(arg)
                elif opt == "-?" or opt == "--help":
                        usage(retcode=pkgdefs.EXIT_OK)

        if pargs:
                usage(_("Unexpected argument(s): {0}").format(" ".join(pargs)))

        if not repo_uri:
                usage(_("A target repository must be provided."))

        if not ref_repo_uri:
                usage(_("A reference repository must be provided."))

        t = misc.config_temp_root()
        temp_root = tempfile.mkdtemp(dir=t,
            prefix=global_settings.client_name + "-")

        ref_incoming_dir = tempfile.mkdtemp(dir=temp_root)
        ref_pkg_root = tempfile.mkdtemp(dir=temp_root)

        ref_xport, ref_xport_cfg = transport.setup_transport()
        ref_xport_cfg.incoming_root = ref_incoming_dir
        ref_xport_cfg.pkg_root = ref_pkg_root
        transport.setup_publisher(ref_repo_uri, "ref", ref_xport,
            ref_xport_cfg, remote_prefix=True)

        target = publisher.RepositoryURI(misc.parse_uri(repo_uri))
        if target.scheme != "file":
                abort(err=_("Target repository must be filesystem-based."))
        try:
                target_repo = sr.Repository(read_only=dry_run,
                    root=target.get_pathname())
        except sr.RepositoryError, e:
                abort(str(e))

        tracker = get_tracker()

        for pub in target_repo.publishers:
                if publishers and pub not in publishers \
                    and '*' not in publishers:
                        continue

                msg(_("Processing packages for publisher {0} ...").format(pub))
                # Find the matching pub in the ref repo.
                for ref_pub in ref_xport_cfg.gen_publishers():
                        if ref_pub.prefix == pub:
                                found = True
                                break
                else:
                        txt = _("Publisher {0} not found in reference "
                            "repository.").format(pub)
                        if publishers:
                                abort(err=txt)
                        else:
                                txt += _(" Skipping.")
                                msg(txt)
                        continue

                processed_pubs += 1

                rev = do_reversion(pub, ref_pub, target_repo, ref_xport,
                    changes, ignores)

                # Only rebuild catalog if anything got actually reversioned.
                if rev and not dry_run:
                        msg(_("Rebuilding repository catalog."))
                        target_repo.rebuild(pub=pub)
                repo_finished = True

        ret = pkgdefs.EXIT_OK
        if processed_pubs == 0:
                msg(_("No matching publishers could be found."))
                ret = pkgdefs.EXIT_OOPS
        cleanup()
        return ret


#
# Establish a specific exit status which means: "python barfed an exception"
# so that we can more easily detect these in testing of the CLI commands.
#
if __name__ == "__main__":
        try:
                __ret = main_func()
        except PipeError:
                # We don't want to display any messages here to prevent
                # possible further broken pipe (EPIPE) errors.
                cleanup(no_msg =True)
                __ret = pkgdefs.EXIT_OOPS
        except (KeyboardInterrupt, api_errors.CanceledException):
                cleanup()
                __ret = pkgdefs.EXIT_OOPS
        except (actions.ActionError, RuntimeError,
            api_errors.ApiException), _e:
                error(_e)
                cleanup()
                __ret = pkgdefs.EXIT_OOPS
        except SystemExit, _e:
                cleanup()
                raise _e
        except:
                traceback.print_exc()
                error(misc.get_traceback_message())
                __ret = 99
        sys.exit(__ret)
