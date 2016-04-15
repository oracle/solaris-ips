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
# Copyright (c) 2011, 2016, Oracle and/or its affiliates. All rights reserved.
#

from __future__ import print_function

try:
        import calendar
        import collections
        import getopt
        import gettext
        import itertools
        import locale
        import os
        import shutil
        import six
        import sys
        import tempfile
        import traceback

        import pkg.actions as actions
        import pkg.fmri
        import pkg.client.api_errors as apx
        import pkg.client.progress as progress
        import pkg.client.publisher as publisher
        import pkg.client.transport.transport as transport
        import pkg.manifest as manifest
        import pkg.misc as misc
        import pkg.publish.transaction as trans

        from functools import reduce
        from pkg.misc import PipeError, emsg, msg
        from six.moves.urllib.parse import quote
except KeyboardInterrupt:
        import sys
        sys.exit(1)

class PkgmergeException(Exception):
        """An exception raised if something goes wrong during the merging
        process."""
        pass


catalog_dict   = {}    # hash table of catalogs by source uri
fmri_cache     = {}
manifest_cache = {}
null_manifest  = manifest.Manifest()
tmpdir         = None
dry_run        = False
xport          = None
dest_xport     = None
pubs           = set()
target_pub     = None

def cleanup():
        """To be called at program finish."""

        if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)

        if dry_run:
                return

        # Attempt to kick off a refresh of target repository for each
        # publisher before exiting.
        for pfx in pubs:
                target_pub.prefix = pfx
                try:
                        dest_xport.publish_refresh_packages(target_pub)
                except apx.TransportError:
                        # If this fails, ignore it as this was a last
                        # ditch attempt anyway.
                        break

def usage(errmsg="", exitcode=2):
        """Emit a usage message and optionally prefix it with a more specific
        error message.  Causes program to exit."""

        if errmsg:
                emsg("pkgmerge: {0}".format(errmsg))

        msg(_("""\
Usage:
        pkgmerge [-n] -d dest_repo -s variant=value[,...],src_repo ...
            [-p publisher_prefix ... ] [pkg_fmri_pattern ...]

Options:
        -d dest_repo
                The filesystem path or URI of the target repository to publish
                the merged packages to.  The target repository must already
                exist; new repositories can be created using pkgrepo(1).

        -n
                Perform a trial run with no changes made to the target
                repository.

        -s variant=value,src_repo
                The variant name and value to use for packages from this source,
                followed by the filesystem path or URI of the source repository
                or package archive to retrieve packages from.  Multiple variants
                may be specified separated by commas.  The same variants must
                be named for all sources.  This option may be specified multiple
                times.

        -p publisher_prefix
                The name of the publisher we should merge packages from.  This
                option may be specified multiple times.  If no -p option is
                used, the default is to merge packages from all publishers in
                all source repositories.

        --help or -?
                Displays a usage message.

Environment:
        TMPDIR, TEMP, TMP
                The absolute path of the directory where temporary data should
                be stored during program execution.
"""))

        sys.exit(exitcode)

def error(text, exitcode=1):
        """Emit an error message prefixed by the command name """

        emsg("pkgmerge: {0}".format(text))

        if exitcode != None:
                sys.exit(exitcode)

def get_tracker():
        try:
                progresstracker = \
                    progress.FancyUNIXProgressTracker()
        except progress.ProgressTrackerException:
                progresstracker = progress.CommandLineProgressTracker()
        return progresstracker

def load_catalog(repouri, pub):
        """Load catalog from specified uri"""
        # Pull catalog only from this host
        pub.repository.origins = [repouri]
        pub.refresh(full_refresh=True, immediate=True)

        catalog_dict[repouri.uri] = dict(
            (name, [
                entry
                for entry in pub.catalog.fmris_by_version(name)
            ])
            for name in pub.catalog.names()
        )

        # Discard catalog.
        pub.remove_meta_root()
        # XXX At the moment, the only way to force the publisher object to
        # discard its copy of a catalog is to set repository.
        pub.repository = pub.repository

def get_all_pkg_names(repouri):
        return list(catalog_dict[repouri.uri].keys())

def get_manifest(repouri, fmri):
        """Fetch the manifest for package-fmri 'fmri' from the source
        in 'repouri'... return as Manifest object."""

        # support null manifests to keep lists ordered for merge
        if not fmri:
                return null_manifest

        mfst_str = xport.get_manifest(fmri, pub=repouri, content_only=True)
        m = manifest.Manifest(fmri)
        m.set_content(content=mfst_str)
        return m

def main_func():
        global dry_run, tmpdir, xport, dest_xport, target_pub

        dest_repo     = None
        source_list   = []
        variant_list  = []
        pub_list      = []
        use_pub_list  = False

        try:
                opts, pargs = getopt.getopt(sys.argv[1:], "d:np:s:?",
                    ["help"])
                for opt, arg in opts:
                        if opt == "-d":
                                dest_repo = misc.parse_uri(arg)
                        elif opt == "-n":
                                dry_run = True
                        elif opt == "-s":
                                s = arg.split(",")
                                if len(s) < 2:
                                        usage("-s option must specify "
                                            "variant=value,repo_uri")

                                # All but last part should be variant.
                                src_vars = {}
                                for v in s[:-1]:
                                        try:
                                                vname, vval = v.split("=")
                                        except ValueError:
                                                usage("-s option must specify "
                                                    "variant=value,repo_uri")

                                        if not vname.startswith("variant."):
                                                vname = "variant.{0}".format(vname)
                                        src_vars[vname] = vval

                                variant_list.append(src_vars)
                                source_list.append(publisher.RepositoryURI(
                                    misc.parse_uri(s[-1])))
                        elif opt == "-p":
                                use_pub_list = True
                                pub_list.append(arg)

                        if opt in ("--help", "-?"):
                                usage(exitcode=0)
        except getopt.GetoptError as e:
                usage(_("illegal option -- {0}").format(e.opt))

        if not source_list:
                usage(_("At least one variant name, value, and package source "
                   "must be provided using -s."))

        if not dest_repo:
                usage(_("A destination package repository must be provided "
                    "using -d."))

        # Determine the unique set of variants across all sources.
        variants = set()
        vcombos = collections.defaultdict(set)
        for src_vars in variant_list:
                for v, vval in six.iteritems(src_vars):
                        variants.add(v)
                        vcombos[v].add((v, vval))

        # merge_fmris() expects this to be a list. Sort it to make sure
        # combo is determinstic in the later construction.
        variants = sorted(variants, reverse=True)

        # Require that the user specified the same variants for all sources.
        for i, src_vars in enumerate(variant_list):
                missing = set(v for v in variants if v not in variant_list[i])
                if missing:
                        missing = ", ".join(missing)
                        source = source_list[i]
                        usage(_("Source {source} missing values for "
                            "variants: {missing}").format(**locals()))

        # Require that each unique variant combination has a source.
        for combo in itertools.product(*vcombos.values()):
                found = False
                for i, src in enumerate(source_list):
                        for vname, vval in combo:
                                if variant_list[i].get(vname,
                                    None) != vval:
                                        found = False
                                        break
                        else:
                                found = True
                                break

                if not found:
                        combo = " ".join(
                            "{0}={1}".format(vname, vval)
                            for vname, vval in combo
                        )
                        usage(_("No source was specified for variant "
                            "combination {combo}.").format(**locals()))

        # initialize transport
        # we use a single endpoint for now, since the transport code
        # uses publisher as a unique key... so we just flop the repo
        # list as needed to access the different catalogs/manifests/files.
        temp_root = misc.config_temp_root()

        tmpdir = tempfile.mkdtemp(dir=temp_root, prefix="pkgmerge")
        xport, xport_cfg = transport.setup_transport()
        xport_cfg.incoming_root = tmpdir

        # we don't use the publisher returned by setup_publisher, as that only
        # returns one of the publishers in source_list.  Instead we use
        # xport_cfg to access all publishers.
        transport.setup_publisher(source_list,
            "pkgmerge", xport, xport_cfg, remote_prefix=True)
        cat_dir = tempfile.mkdtemp(dir=tmpdir)

        # we must have at least one matching publisher if -p was used.
        known_pubs = set([pub.prefix for pub in xport_cfg.gen_publishers()])
        if pub_list and len(set(pub_list).intersection(known_pubs)) == 0:
                error(_("no publishers from source repositories match "
                    "the given -p options."))

        errors = set()
        tracker = get_tracker()

        # iterate over all publishers in our source repositories.  If errors
        # are encountered for a given publisher, we accumulate those, and
        # skip to the next publisher.
        for pub in xport_cfg.gen_publishers():

                if use_pub_list:
                        if pub.prefix not in pub_list:
                                continue
                        else:
                                # remove publishers from pub_list as we go, so
                                # that when we're finished, any remaining
                                # publishers in pub_list suggest superfluous
                                # -p options, which will cause us to exit with
                                # an error.
                                pub_list.remove(pub.prefix)

                pub.meta_root = cat_dir
                pub.transport = xport

                # Use separate transport for destination repository in case
                # source and destination have identical publisher configuration.
                dest_xport, dest_xport_cfg = transport.setup_transport()
                dest_xport_cfg.incoming_root = tmpdir

                # retrieve catalogs for all specified repositories
                for s in source_list:
                        load_catalog(s, pub)

                # determine the list of packages we'll be processing
                if not pargs:
                        # use the latest versions and merge everything
                        fmri_arguments = list(set(
                            name
                            for s in source_list
                            for name in get_all_pkg_names(s)
                        ))
                        exclude_args = []
                else:
                        fmri_arguments = [
                            f
                            for f in pargs
                            if not f.startswith("!")
                        ]

                        exclude_args = [
                            f[1:]
                            for f in pargs
                            if f.startswith("!")
                        ]

                # build fmris to be merged
                masterlist = [
                    build_merge_list(fmri_arguments, exclude_args,
                        catalog_dict[s.uri])
                    for s in source_list
                ]

                # check for unmatched patterns
                in_none = reduce(lambda x, y: x & y,
                    (set(u) for d, u in masterlist))
                if in_none:
                        errors.add(
                            _("The following pattern(s) did not match any "
                            "packages in any of the specified repositories for "
                            "publisher {pub_name}:"
                            "\n{patterns}").format(patterns="\n".join(in_none),
                            pub_name=pub.prefix))
                        continue

                # generate set of all package names to be processed, and dict
                # of lists indexed by order in source_list; if that repo has no
                # fmri for this pkg then use None.
                allpkgs = set(name for d, u in masterlist for name in d)

                processdict = {}
                for p in allpkgs:
                        for d, u in masterlist:
                                processdict.setdefault(p, []).append(
                                    d.setdefault(p, None))

                # check to make sure all fmris are at same version modulo
                # timestamp
                for entry in processdict:
                        if len(set([
                                str(a).rsplit(":")[0]
                                for a in processdict[entry]
                                if a is not None
                            ])) > 1:
                                errors.add(
                                    _("fmris matching the following patterns do"
                                    " not have matching versions across all "
                                    "repositories for publisher {pubs}: "
                                    "{patterns}").format(pub=pub.prefix,
                                    patterns=processdict[entry]))
                                continue

                # we're ready to merge
                if not dry_run:
                        target_pub = transport.setup_publisher(dest_repo,
                            pub.prefix, dest_xport, dest_xport_cfg,
                            remote_prefix=True)
                else:
                        target_pub = None

                tracker.republish_set_goal(len(processdict), 0, 0)
                # republish packages for this publisher. If we encounter any
                # publication errors, we move on to the next publisher.
                try:
                        pkg_tmpdir = tempfile.mkdtemp(dir=tmpdir)
                        republish_packages(pub, target_pub,
                            processdict, source_list, variant_list, variants,
                            tracker, xport, dest_repo, dest_xport, pkg_tmpdir,
                            dry_run=dry_run)
                except (trans.TransactionError, PkgmergeException) as e:
                        errors.add(str(e))
                        tracker.reset()
                        continue
                finally:
                        # if we're handling an exception, this still gets called
                        # in spite of the 'continue' that the handler ends with.
                        if os.path.exists(pkg_tmpdir):
                                shutil.rmtree(pkg_tmpdir)

                tracker.republish_done(dryrun=dry_run)
                tracker.reset()

        # If -p options were supplied, we should have processed all of them
        # by now. Remaining entries suggest -p options that were not merged.
        if use_pub_list and pub_list:
                errors.add(_("the following publishers were not found in "
                    "source repositories: {0}").format(" ".join(pub_list)))

        # If we have encountered errors for some publishers, print them now
        # and exit.
        tracker.flush()
        for message in errors:
                error(message, exitcode=None)
        if errors:
                exit(1)

        return 0

def republish_packages(pub, target_pub, processdict, source_list, variant_list,
        variants, tracker, xport, dest_repo, dest_xport, pkg_tmpdir,
        dry_run=False):
        """Republish packages for publisher pub to dest_repo.

        If we try to republish a package that we have already published,
        an exception is raise.

        pub             the publisher from source_list that we are republishing
        target_pub      the destination publisher
        processdict     a dict indexed by package name of the pkgs to merge
        source_list     a list of source respositories
        variant_list    a list of dicts containing variant names/values
        variants        the unique set of variants across all sources.
        tracker         a progress tracker
        xport           the transport handling our source repositories
        dest_repo       our destination repository
        dest_xport      the transport handling our destination repository
        pkg_tmpdir      a temporary dir used when downloading pkg content
                        which may be deleted and recreated by this method.

        dry_run         True if we should not actually publish
        """

        def get_basename(pfmri):
                open_time = pfmri.get_timestamp()
                return "{0:d}_{0}".format(
                    calendar.timegm(open_time.utctimetuple()),
                    quote(str(pfmri), ""))

        for entry in processdict:
                man, retrievals = merge_fmris(source_list,
                    processdict[entry], variant_list, variants)

                # Determine total bytes to retrieve for this package; this must
                # be done using the retrievals dict since they are coalesced by
                # hash.
                getbytes = sum(
                    misc.get_pkg_otw_size(a)
                    for i, uri in enumerate(source_list)
                    for a in retrievals[i]
                )

                # Determine total bytes to send for this package; this must be
                # done using the manifest since retrievals are coalesced based
                # on hash, but sends are not.
                sendbytes = sum(
                    int(a.attrs.get("pkg.size", 0))
                    for a in man.gen_actions()
                )

                f = man.fmri

                tracker.republish_start_pkg(f, getbytes=getbytes,
                    sendbytes=sendbytes)

                if dry_run:
                        # Dry-run; attempt a merge of everything but don't
                        # write any data or publish packages.
                        continue

                target_pub.prefix = f.publisher

                # Retrieve package data from each package source.
                for i, uri in enumerate(source_list):
                        pub.repository.origins = [uri]
                        mfile = xport.multi_file_ni(pub, pkg_tmpdir,
                            decompress=True, progtrack=tracker)
                        for a in retrievals[i]:
                                mfile.add_action(a)
                        mfile.wait_files()

                trans_id = get_basename(f)
                pkg_name = f.get_fmri()
                pubs.add(target_pub.prefix)
                # Publish merged package.
                t = trans.Transaction(dest_repo,
                    pkg_name=pkg_name, trans_id=trans_id,
                    xport=dest_xport, pub=target_pub,
                    progtrack=tracker)

                # Remove any previous failed attempt to
                # to republish this package.
                try:
                        t.close(abandon=True)
                except:
                        # It might not exist already.
                        pass

                t.open()
                for a in man.gen_actions():
                        if (a.name == "set" and
                            a.attrs["name"] == "pkg.fmri"):
                                # To be consistent with the
                                # server, the fmri can't be
                                # added to the manifest.
                                continue

                        if hasattr(a, "hash"):
                                fname = os.path.join(pkg_tmpdir,
                                    a.hash)
                                a.data = lambda: open(
                                    fname, "rb")
                        t.add(a)

                # Always defer catalog update.
                t.close(add_to_catalog=False)

                # Done with this package.
                tracker.republish_end_pkg(f)

                # Dump retrieved package data after each republication and
                # recreate the directory for the next package.
                shutil.rmtree(pkg_tmpdir)
                os.mkdir(pkg_tmpdir)

def merge_fmris(source_list, fmri_list, variant_list, variants):
        """Merge a list of manifests representing multiple variants,
        returning the merged manifest and a list of lists of actions to
        retrieve from each source"""

        # Merge each variant one at a time.
        merged = {}
        # where to find files...
        hash_source = {}

        for i, variant in enumerate(variants):
                # Build the unique list of remaining variant combinations to
                # use for merging this variant.
                combos = set(
                    tuple(
                        (vname, src_vars[vname])
                        for vname in variants[i + 1:]
                    )
                    for src_vars in variant_list
                )

                if not combos:
                        # If there are no other variants to combine, then simply
                        # combine all manifests.
                        combos = [()]

                # Perform the variant merge for each unique combination of
                # remaining variants.  For example, a pkgmerge of:
                #   -s arch=sparc,debug=false,flavor=32,...
                #   -s arch=sparc,debug=false,flavor=64,...
                #   -s arch=sparc,debug=true,flavor=32,...
                #   -s arch=sparc,debug=true,flavor=64,...
                #   -s arch=i386,debug=false,flavor=32,...
                #   -s arch=i386,debug=false,flavor=64,...
                #   -s arch=i386,debug=true,flavor=32,...
                #   -s arch=i386,debug=true,flavor=64,...
                #
                # ...would produce the following combinations for each variant:
                #   variant.arch
                #     debug=false, flavor=32
                #     debug=false, flavor=64
                #     debug=true, flavor=32
                #     debug=true, flavor=64
                #   variant.debug
                #     flavor=32
                #     flavor=64
                #   variant.flavor
                #
                for combo in combos:
                        # Build the list of sources, fmris, and variant values
                        # involved in this particular combo merge.
                        slist = []
                        flist = []
                        vlist = []
                        sindex = []
                        new_fmri = None
                        for j, src in enumerate(source_list):
                                if combo:
                                        # If filtering on a specific combination
                                        # then skip this source if any of the
                                        # combination parameters don't match.
                                        skip = False
                                        for vname, vval in combo:
                                                if variant_list[j].get(vname,
                                                    None) != vval:
                                                        skip = True
                                                        break

                                        if skip:
                                                continue

                                # Skip this source if it doesn't have a matching
                                # package to merge, or if it has already been
                                # merged with another package.
                                pfmri = fmri_list[j]
                                if not pfmri or \
                                    merged.get(id(pfmri), None) == null_manifest:
                                        continue

                                # The newest FMRI in the set of manifests being
                                # merged will be used as the new FMRI of the
                                # merged package.
                                if new_fmri is None or pfmri.version > new_fmri.version:
                                        new_fmri = pfmri

                                sindex.append(j)
                                slist.append(src)
                                flist.append(pfmri)
                                vlist.append(variant_list[j][variant])

                        if not flist:
                                # Nothing to merge for this combination.
                                continue

                        # Build the list of manifests to be merged.
                        mlist = []
                        for j, s, f in zip(sindex, slist, flist):
                                if id(f) in merged:
                                        # Manifest already merged before, use
                                        # the merged version.
                                        m = merged[id(f)]
                                else:
                                        # Manifest not yet merged, retrieve
                                        # from source; record those w/ payloads
                                        # so we know from where to get them..
                                        m = get_manifest(s, f)
                                        for a in m.gen_actions():
                                                if a.has_payload:
                                                        hash_source.setdefault(a.hash, j)
                                mlist.append(m)

                        m = __merge_fmris(new_fmri, mlist, flist, vlist,
                            variant)

                        for f in flist:
                                if id(f) == id(new_fmri):
                                        # This FMRI was used for the merged
                                        # manifest; any future merges should
                                        # use the merged manifest for this
                                        # FMRI.
                                        merged[id(f)] = m
                                else:
                                        # This package has been merged with
                                        # another so shouldn't be retrieved
                                        # or merged again.
                                        merged[id(f)] = null_manifest

        # Merge process should have resulted in a single non-null manifest.
        m = [v for v in merged.values() if v != null_manifest]
        assert len(m) == 1
        m = m[0]

        # Finally, build a list of actions to retrieve based on position in
        # source_list.

        retrievals = [list() for i in source_list]

        for a in m.gen_actions():
                if a.has_payload:
                        source = hash_source.pop(a.hash, None)
                        if source is not None:
                                retrievals[source].append(a)
        return m, retrievals


def __merge_fmris(new_fmri, manifest_list, fmri_list, variant_list, variant):
        """Private merge implementation."""

        # Remove variant tags, package variant metadata, and signatures
        # from manifests since we're reassigning.  This allows merging
        # pre-tagged, already merged pkgs, or signed packages.

        blended_actions = []
        blend_names = set([variant, variant[8:]])

        for j, m in enumerate(manifest_list):
                deleted_count = 0
                vval = variant_list[j]
                for i, a in enumerate(m.actions[:]):
                        if a.name == "signature" or \
                            (a.name == "set" and a.attrs["name"] == "pkg.fmri"):
                                # signatures and pkg.fmri actions are no longer
                                # valid after merging
                                del m.actions[i - deleted_count]
                                deleted_count += 1
                                continue

                        if variant in a.attrs:
                                if a.attrs[variant] != vval:
                                        # we have an already merged
                                        # manifest; filter out actions
                                        # for other variants
                                        del m.actions[i - deleted_count]
                                        deleted_count += 1
                                        continue
                                else:
                                        del a.attrs[variant]

                        if a.name == "set" and a.attrs["name"] == variant:
                                if vval not in a.attrlist("value"):
                                        raise PkgmergeException(
                                            _("package {pkg} is tagged as "
                                            "not supporting {var_name} "
                                            "{var_value}").format(
                                            pkg=fmri_list[j],
                                            var_name=variant,
                                            var_value=vval))
                                del m.actions[i - deleted_count]
                                deleted_count += 1
                        # checking if we're supposed to blend this action
                        # for this variant.  Handle prepended "variant.".
                        if blend_names & set(a.attrlist("pkg.merge.blend")):
                                blended_actions.append((j, a))

        # add blended actions to other manifests
        for j, m in enumerate(manifest_list):
                for k, a in blended_actions:
                        if k != j:
                                m.actions.append(a)

        # Like the unix utility comm, except that this function
        # takes an arbitrary number of manifests and compares them,
        # returning a tuple consisting of each manifest's actions
        # that are not the same for all manifests, followed by a
        # list of actions that are the same in each manifest.
        try:
                action_lists = list(manifest.Manifest.comm(manifest_list))
        except manifest.ManifestError as e:
                raise PkgmergeException(
                    "Duplicate action(s) in package \"{0}\": \n{1}".format(
                    new_fmri.pkg_name, e))

        # Declare new package FMRI.
        action_lists[-1].insert(0,
            actions.fromstr("set name=pkg.fmri value={0}".format(new_fmri)))

        for a_list, v in zip(action_lists[:-1], variant_list):
                for a in a_list:
                        a.attrs[variant] = v
        # discard any blend tags for this variant from common list
        for a in action_lists[-1]:
                blend_attrs = set(a.attrlist("pkg.merge.blend"))
                match = blend_names & blend_attrs
                for m in list(match):
                        if len(blend_attrs) == 1:
                                del a.attrs["pkg.merge.blend"]
                        else:
                                a.attrlist("pkg.merge.blend").remove(m)
        # combine actions into single list
        allactions = reduce(lambda a, b: a + b, action_lists)

        # figure out which variants are actually there for this pkg
        actual_variant_list = [
            v
            for m, v in zip(manifest_list, variant_list)
        ]

        # add set action to document which variants are supported
        allactions.append(actions.fromstr("set name={0} {1}".format(variant,
            " ".join([
                "value={0}".format(a)
                for a in actual_variant_list
            ])
        )))

        allactions.sort()

        m = manifest.Manifest(pfmri=new_fmri)
        m.set_content(content=allactions)
        return m

def build_merge_list(include, exclude, cat):
        """Given a list of patterns to include and a list of patterns
        to exclude, return a dictionary of fmris to be included,
        along w/ a list of include patterns that don't match"""

        include_dict, include_misses = match_user_fmris(include, cat)
        exclude_dict, ignored = match_user_fmris(exclude, cat)

        for pkg_name in include_dict:
                if pkg_name in exclude_dict:
                        include_dict[pkg_name] -= exclude_dict[pkg_name]

        return dict((k, sorted(list(v), reverse=True)[0])
                    for k,v in six.iteritems(include_dict)
                    if v), include_misses

def match_user_fmris(patterns, cat):
        """Given a user-specified list of patterns, return a dictionary
        of matching fmri sets:

        {pkgname: [fmri, ... ]
         pkgname: [fmri, ... ]
         ...
        }

        Note that patterns starting w/ pkg:/ require an exact match;
        patterns containing '*' will using fnmatch rules; the default
        trailing match rules are used for remaining patterns.
        """

        matchers = []
        fmris    = []
        versions = []

        # ignore dups
        patterns = list(set(patterns))

        # figure out which kind of matching rules to employ
        latest_pats = set()
        for pat in patterns:
                try:
                        parts = pat.split("@", 1)
                        pat_stem = parts[0]
                        pat_ver = None
                        if len(parts) > 1:
                                pat_ver = parts[1]

                        if "*" in pat_stem or "?" in pat_stem:
                                matcher = pkg.fmri.glob_match
                        elif pat_stem.startswith("pkg:/") or \
                            pat_stem.startswith("/"):
                                matcher = pkg.fmri.exact_name_match
                        else:
                                matcher = pkg.fmri.fmri_match

                        if matcher == pkg.fmri.glob_match:
                                fmri = pkg.fmri.MatchingPkgFmri(pat_stem)
                        else:
                                fmri = pkg.fmri.PkgFmri(pat_stem)

                        if not pat_ver:
                                # Do nothing.
                                pass
                        elif "*" in pat_ver or "?" in pat_ver or \
                            pat_ver == "latest":
                                fmri.version = \
                                    pkg.version.MatchingVersion(pat_ver)
                        else:
                                fmri.version = \
                                    pkg.version.Version(pat_ver)

                        if pat_ver and \
                            getattr(fmri.version, "match_latest", None):
                                latest_pats.add(pat)

                        matchers.append(matcher)
                        versions.append(fmri.version)
                        fmris.append(fmri)
                except (pkg.fmri.FmriError,
                    pkg.version.VersionError) as e:
                        raise PkgmergeException(str(e))

        # Create a dictionary of patterns, with each value being a
        # dictionary of pkg names & fmris that match that pattern.
        ret = dict(zip(patterns, [dict() for i in patterns]))

        for name in cat.keys():
                for pat, matcher, fmri, version in \
                    zip(patterns, matchers, fmris, versions):
                        if not matcher(name, fmri.pkg_name):
                                continue # name doesn't match
                        for ver, pfmris in cat[name]:
                                if version and not ver.is_successor(version,
                                    pkg.version.CONSTRAINT_AUTO):
                                        continue # version doesn't match
                                for f in pfmris:
                                        ret[pat].setdefault(f.pkg_name,
                                            []).append(f)

        # Discard all but the newest version of each match.
        if latest_pats:
                # Rebuild ret based on latest version of every package.
                latest = {}
                nret = {}
                for p in patterns:
                        if p not in latest_pats or not ret[p]:
                                nret[p] = ret[p]
                                continue

                        nret[p] = {}
                        for pkg_name in ret[p]:
                                nret[p].setdefault(pkg_name, [])
                                for f in ret[p][pkg_name]:
                                        nver = latest.get(f.pkg_name, None)
                                        latest[f.pkg_name] = max(nver,
                                            f.version)
                                        if f.version == latest[f.pkg_name]:
                                                # Allow for multiple FMRIs of
                                                # the same latest version.
                                                nret[p][pkg_name] = [
                                                    e
                                                    for e in nret[p][pkg_name]
                                                    if e.version == f.version
                                                ]
                                                nret[p][pkg_name].append(f)

                # Assign new version of ret and discard latest list.
                ret = nret
                del latest

        # merge patterns together and create sets
        merge_dict = {}
        for d in ret.values():
                merge_dict.update(d)

        for k in merge_dict:
                merge_dict[k] = set(merge_dict[k])

        unmatched_patterns = [
            p
            for p in ret
            if not ret[p]
        ]

        return merge_dict, unmatched_patterns


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
        try:
                __ret = main_func()
        except (pkg.actions.ActionError, trans.TransactionError,
            RuntimeError, pkg.fmri.FmriError, apx.ApiException) as __e:
                print("pkgmerge: {0}".format(__e), file=sys.stderr)
                __ret = 1
        except (PipeError, KeyboardInterrupt):
                __ret = 1
        except SystemExit as __e:
                raise __e
        except Exception as __e:
                traceback.print_exc()
                error(misc.get_traceback_message(), exitcode=None)
                __ret = 99
        finally:
                cleanup()

        sys.exit(__ret)
