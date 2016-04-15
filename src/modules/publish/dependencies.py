#!/usr/bin/python
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
# Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
#

import copy
import itertools
import operator
import os
import re
import six

from collections import namedtuple
from six.moves.urllib.parse import unquote

import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as apx
import pkg.flavor.base as base
import pkg.flavor.elf as elf_dep
import pkg.flavor.hardlink as hardlink
import pkg.flavor.script as script
import pkg.flavor.smf_manifest as smf_manifest
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.portable as portable
import pkg.variant as variants

paths_prefix = "{0}.path".format(base.Dependency.DEPEND_DEBUG_PREFIX)
files_prefix = "{0}.file".format(base.Dependency.DEPEND_DEBUG_PREFIX)
reason_prefix = "{0}.reason".format(base.Dependency.DEPEND_DEBUG_PREFIX)
type_prefix = "{0}.type".format(base.Dependency.DEPEND_DEBUG_PREFIX)
target_prefix = "{0}.target".format(base.Dependency.DEPEND_DEBUG_PREFIX)
bypassed_prefix = "{0}.bypassed".format(base.Dependency.DEPEND_DEBUG_PREFIX)
via_links_prefix = "{0}.via-links".format(base.Dependency.DEPEND_DEBUG_PREFIX)
path_id_prefix = "{0}.path-id".format(base.Dependency.DEPEND_DEBUG_PREFIX)

# A tag used to hold the product of the paths_prefix and files_prefix
# contents, used when bypassing dependency generation
fullpaths_prefix = "{0}.fullpath".format(base.Dependency.DEPEND_DEBUG_PREFIX)

Entries = namedtuple("Entries", ["delivered", "installed"])
# This namedtuple is used to hold two items. The first, delivered, is used to
# hold items which are part of packages being delivered.  The second, installed,
# is used to hold items which are part of packages installed on the system.

LinkInfo = namedtuple("LinkInfo", ["path", "pfmri", "nearest_pfmri",
    "variant_combination", "via_links"])
# This namedtuple is used to hold the information needed when resolving links.
# The 'path' is the path of the file that ultimately resolved the link.  The
# 'pfmri' is the package fmri that delivered 'path.'  The 'nearest_pfmri' is the
# package that delivered the next element in the link chain.  The
# 'variant-combination' is the combination of variants under which the link is
# satisfied.  'via-links' contains the links used to reach 'path.'

class DependencyError(Exception):
        """The parent class for all dependency exceptions."""
        pass

class DropPackageWarning(DependencyError):
        """This exception is used when a package is dropped as it cannot
        satisfy all dependencies."""

        def __init__(self, pkgs, dep):
                self.pkgs = pkgs
                self.dep = dep

        def __str__(self):
                pkg_str = ", ".join(f.get_pkg_stem() for f in self.pkgs)
                return _("WARNING: package {0} was ignored as it cannot "
                    "satisfy all dependencies:\n{1}\n").format(pkg_str,
                    prune_debug_attrs(self.dep))

class UnresolvedDependencyError(DependencyError):
        """This exception is used when no package delivers a file which is
        depended upon."""

        def __init__(self, pth, file_dep, pvars):
                self.path = pth
                self.file_dep = file_dep
                self.pvars = pvars

        def __str__(self):
                dep_str = "\n" + self.file_dep.pretty_print()
                if self.pvars.not_sat_set:
                        return _("{pth} has unresolved dependency '{dep}' "
                            "under the following combinations of "
                            "variants:\n{combo}").format(
                                pth=self.path,
                                dep=dep_str + "\n",
                                combo="\n".join([
                                    " ".join([
                                        ("{0}:{1}".format(name, val))
                                        for name, val in sorted(grp)
                                    ])
                                    for grp in self.pvars.not_sat_set
                            ]))
                else:
                        return _("{pth} has unresolved dependency "
                            "'{dep}'.").format(
                            pth=self.path, dep=dep_str)


class MissingPackageVariantError(DependencyError):
        """This exception is used when an action is tagged with a variant or
        variant value which the package is not tagged with."""

        def __init__(self, act_vars, pkg_vars, pth):
                self.act_vars = act_vars
                self.pkg_vars = pkg_vars
                self.path = pth

        def __str__(self):
                return _("The action delivering {path} is tagged with a "
                    "variant type or value not tagged on the package. "
                    "Dependencies on this file may fail to be reported.\n"
                    "The action's variants are: {act}\nThe package's "
                    "variants are: {pkg}").format(
                        path=self.path,
                        act=self.act_vars,
                        pkg=self.pkg_vars
                   )


class BadPackageFmri(DependencyError):
        """This exception is used when a manifest's fmri isn't a valid fmri."""

        def __init__(self, path, e):
                self.path = path
                self.exc = e

        def __str__(self):
                return _("The manifest '{path}' has an invalid package "
                    "FMRI:\n\t{exc}").format(path=self.path, exc=self.exc)


class ExtraVariantedDependency(DependencyError):
        """This exception is used when one or more dependency actions have a
        variant set on them which is not in the package's set of variants."""

        def __init__(self, pkg, reason_variants, manual_dep):
                self.pkg = pkg
                assert len(reason_variants) > 0
                self.rvs = reason_variants
                self.manual = manual_dep

        def __str__(self):
                s = ""
                for r, diff in sorted(six.iteritems(self.rvs)):
                        for kind in diff.type_diffs:
                                s += _("\t{r:15} Variant '{kind}' is not "
                                    "declared.\n").format(
                                    r=r, kind=kind)
                        for k, v in diff.value_diffs:
                                s += _("\t{r:15} Variant '{kind}' is not "
                                    "declared to have value '{val}'.\n").format(
                                    r=r, val=v, kind=k)
                if not self.manual:
                        return _("The package '{pkg}' contains actions with "
                            "the\npaths seen below which have variants set on "
                            "them which are not set on the\npackage.  These "
                            "variants must be set on the package or removed "
                            "from the actions.\n\n{rvs}").format(
                            pkg=self.pkg,
                            rvs=s
                       )
                else:
                        return _("The package '{pkg}' contains manually "
                            "specified dependencies\nwhich have variants set "
                            "on them which are not set on the package.  "
                            "These\nvariants must be set on the package or "
                            "removed from the actions.\n\n{rvs}").format(
                            pkg=self.pkg,
                            rvs=s
                       )

class NeedConditionalRequireAny(DependencyError):
        """This exception is used when pkgdepend would need a dependency which
        was both require-any and conditional to properly represent the
        dependency."""

        def __init__(self, conditionals, pkg_vars):
                self.conditionals = conditionals
                self.pkg_vct = pkg_vars

        def __str__(self):
                s = _("""\
pkgdepend has inferred conditional dependencies with different targets but
which share a predicate.  pkg(5) can not represent these dependencies.  This
issue can be resolved by changing the packaging of the links which generated the
conditional dependencies so that they have different predicates or share the
same FMRI.  Each pair of problematic conditional dependencies follows:
""")
                for i, (d1, d2, v) in enumerate(self.conditionals):
                        i += 1
                        v.simplify(self.pkg_vct)
                        if v.is_empty() or not v.sat_set:
                                s += _("Pair {0}\n").format(i)
                        else:
                                s += _("Pair {0} is only problematic in the "
                                    "listed variant combinations:").format(i)
                                s += "\n\t\t" + "\n\t\t".join([
                                    " ".join([
                                        ("{0}:{1}".format(name, val))
                                        for name, val in sorted(grp)
                                    ]) for grp in v.sat_set
                                ])
                                s += "\n"
                        s += d1.pretty_print() + "\n"
                        s += d2.pretty_print() + "\n"
                return s

class __NotSubset(DependencyError):
        def __init__(self, diff):
                self.diff = variants.VCTDifference(tuple(diff.type_diffs),
                    tuple(diff.value_diffs))


def list_implicit_deps(file_path, proto_dirs, dyn_tok_conv, run_paths,
    remove_internal_deps=True, convert=True, ignore_bypass=False):
        """Given the manifest provided in file_path, use the known dependency
        generators to produce a list of dependencies the files delivered by
        the manifest have.

        'file_path' is the path to the manifest for the package.

        'proto_dirs' is a list of paths to proto areas which hold the files that
        will be delivered by the package.

        'dyn_tok_conv' is the dictionary which maps the dynamic tokens, like
        $PLATFORM, to the values they should be expanded to.

        'run_paths' contains the run paths that are used to find modules.

        'convert' determines whether PublishingDependencies will be transformed
        to DependencyActions prior to being returned.  This is primarily an
        option to facilitate testing and debugging.

        'ignore_bypass' determines whether to bypass generation of dependencies
        against certain files or directories.  This is primarily an option to
        facilitate testing and debugging.
        """

        m, manifest_errs = __make_manifest(file_path, proto_dirs)
        pkg_vars = m.get_all_variants()
        deps, elist, missing, pkg_attrs = list_implicit_deps_for_manifest(m,
            proto_dirs, pkg_vars, dyn_tok_conv, run_paths,
            ignore_bypass=ignore_bypass)
        rid_errs = []
        if remove_internal_deps:
                deps, rid_errs = resolve_internal_deps(deps, m, proto_dirs,
                    pkg_vars)
        if convert:
                deps = convert_to_standard_dep_actions(deps)

        return deps, manifest_errs + elist + rid_errs, missing, pkg_attrs

def convert_to_standard_dep_actions(deps):
        """Convert pkg.base.Dependency objects to
        pkg.actions.dependency.Dependency objects."""

        def norm_attrs(a):
                """Normalize attribute values as lists instead of sets; only
                lists are permitted for multi-value action attributes."""
                for k, v in a.items():
                        if isinstance(v, set):
                                a[k] = list(v)

        res = []
        for d in deps:
                tmp = []
                for c in d.dep_vars.not_sat_set:
                        attrs = d.attrs.copy()
                        attrs.update(c)
                        norm_attrs(attrs)
                        tmp.append(actions.depend.DependencyAction(**attrs))
                if not tmp:
                        attrs = d.attrs.copy()
                        norm_attrs(attrs)
                        tmp.append(actions.depend.DependencyAction(**attrs))
                res.extend(tmp)
        return res

def resolve_internal_deps(deps, mfst, proto_dirs, pkg_vars):
        """Given a list of dependencies, remove those which are satisfied by
        others delivered by the same package.

        'deps' is a list of Dependency objects.

        'mfst' is the Manifest of the package that delivered the dependencies
        found in deps.

        'proto_dir' is the path to the proto area which holds the files that
        will be delivered by the package.

        'pkg_vars' are the variants that this package was published against."""

        res = []
        errs = []
        delivered = {}
        delivered_bn = {}

        files = Entries({}, {})
        links = {}

        # A fake pkg name is used because there is no requirement that a package
        # name itself to generate its dependencies.  Also, the name is entirely
        # a private construction which should not escape to the user.
        add_fmri_path_mapping(files.delivered, links,
            fmri.PkgFmri("INTERNAL@0-0", "0"), mfst)
        for a in mfst.gen_actions_by_type("file"):
                pvars = a.get_variant_template()
                if not pvars:
                        pvars = pkg_vars
                else:
                        if not pvars.issubset(pkg_vars):
                                # This happens when an action in a package is
                                # tagged with a variant type or value which the
                                # package has not been tagged with.
                                errs.append(
                                    MissingPackageVariantError(pvars, pkg_vars,
                                        a.attrs["path"]))
                        pvars.merge_unknown(pkg_vars)
                pvc = variants.VariantCombinations(pvars, satisfied=True)
                p = a.attrs["path"]
                bn = os.path.basename(p)
                delivered_bn.setdefault(bn, copy.copy(pvc))

        for d in deps:
                etype, pvars = d.resolve_internal(
                    delivered_files=files.delivered,
                    delivered_base_names=delivered_bn, links=links,
                    resolve_links=resolve_links)
                if etype is None:
                        continue
                pvars.simplify(pkg_vars)
                d.dep_vars = pvars
                res.append(d)
        return res, errs

def no_such_file(action, **kwargs):
        """Function to handle dispatch of files not found on the system."""

        return [], [base.MissingFile(action.attrs["path"])], {}

# Dictionary which maps codes from portable.get_file_type to the functions which
# find dependencies for those types of files.
dispatch_dict = {
    portable.ELF: elf_dep.process_elf_dependencies,
    portable.EXEC: script.process_script_deps,
    portable.SMF_MANIFEST: smf_manifest.process_smf_manifest_deps,
    portable.UNFOUND: no_such_file
}

def list_implicit_deps_for_manifest(mfst, proto_dirs, pkg_vars, dyn_tok_conv,
    run_paths, ignore_bypass=False):
        """For a manifest, produce the list of dependencies generated by the
        files it installs.

        'mfst' is the Manifest of the package that delivered the dependencies
        found in deps.

        'proto_dirs' are the paths to the proto areas which hold the files that
        will be delivered by the package.

        'pkg_vars' are the variants that this package was published against.

        'dyn_tok_conv' is the dictionary which maps the dynamic tokens, like
        $PLATFORM, to the values they should be expanded to.

        'run_paths' contains the run paths used to find modules, this is
        overridden by any manifest or action attributes setting
        'pkg.depend.runpath' (portable.PD_RUN_PATH)

        'ignore_bypass' set to True will prevent us from looking up any
        pkg.depend.bypass-generate attributes - this is primarily to aid
        debugging and testing.

        Returns a tuple of three lists.

        'deps' is a list of dependencies found for the given Manifest.

        'elist' is a list of errors encountered while finding dependencies.

        'missing' is a dictionary mapping a file type that isn't recognized by
        portable.get_file_type to a file which produced that filetype.

        'pkg_attrs' is a dictionary containing metadata that was gathered
        during dependency analysis. Typically these would get turned into
        AttributeActions for that package. """

        deps = []
        elist = []
        missing = {}
        pkg_attrs = {}
        act_list = list(mfst.gen_actions_by_type("file"))
        file_types = portable.get_file_type(act_list)

        if portable.PD_RUN_PATH in mfst:
                # check for multiple values in a set attribute
                run_path_str = mfst[portable.PD_RUN_PATH]
                es = __verify_run_path(run_path_str)
                if es:
                        return deps, elist + es, missing, pkg_attrs
                run_paths = run_path_str.split(":")

        mf_bypass = []
        if portable.PD_BYPASS_GENERATE in mfst:
                mf_bypass = __makelist(mfst[portable.PD_BYPASS_GENERATE])

        for i, file_type in enumerate(file_types):
                a = act_list[i]

                a_run_paths = run_paths
                if portable.PD_RUN_PATH in a.attrs:
                        a_run_path_str = a.attrs[portable.PD_RUN_PATH]
                        es = __verify_run_path(a_run_path_str)
                        if es:
                                return deps, elist + es, missing, pkg_attrs
                        a_run_paths = a_run_path_str.split(":")

                bypass = __makelist(
                    a.attrs.get(portable.PD_BYPASS_GENERATE, mf_bypass))
                # If we're bypassing all depdendency generation, we can avoid
                # calling our dispatch_dict function altogether.
                if (".*" in bypass or "^.*$" in bypass) and not ignore_bypass:
                        pkg_attrs[bypassed_prefix] = "{0}:.*".format(
                            a.attrs["path"])
                        continue
                try:
                        func = dispatch_dict[file_type]
                except KeyError:
                        if file_type not in missing:
                                missing[file_type] = \
                                    a.attrs[portable.PD_LOCAL_PATH]
                else:
                        try:
                                ds, errs, attrs = func(action=a,
                                    pkg_vars=pkg_vars,
                                    dyn_tok_conv=dyn_tok_conv,
                                    run_paths=a_run_paths)

                                # prune out any dependencies on the files we've
                                # been asked to avoid creating dependencies on
                                if bypass and not ignore_bypass:
                                        ds = \
                                            __bypass_deps(ds, bypass, pkg_attrs)

                                deps.extend(ds)
                                elist.extend(errs)
                                __update_pkg_attrs(pkg_attrs, attrs)
                        except base.DependencyAnalysisError as e:
                                elist.append(e)
        for a in mfst.gen_actions_by_type("hardlink"):
                deps.extend(hardlink.process_hardlink_deps(a, pkg_vars))
        return deps, elist, missing, pkg_attrs

def __update_pkg_attrs(pkg_attrs, new_attrs):
        """Update the pkg_attrs dictionary with the contents of new_attrs."""
        for key in new_attrs:
                pkg_attrs.setdefault(key, []).extend(new_attrs[key])

def __verify_run_path(run_path_str):
        """Verify we've been passed a single item and ensure it contains
        at least one non-null string."""
        if not isinstance(run_path_str, str):
                # require a colon separated string to potentially enforce
                # ordering in the future
                return [base.DependencyAnalysisError(
                    _("Manifest specified multiple values for {0} rather "
                    "than a single colon-separated string.").format(
                    portable.PD_RUN_PATH))]
        if set(run_path_str.split(":")) == set([""]):
                return [base.DependencyAnalysisError(
                    _("Manifest did not specify any entries for {0}, expecting "
                    "a colon-separated string.").format(portable.PD_RUN_PATH))]
        return []

def __makelist(value):
        """Given a value, return it if that value is a list, or if it's a
        string, return a single-element list of just that string."""
        if isinstance(value, list):
                return value
        elif isinstance(value, str):
                if value:
                        return [value]
                else:
                        return []
        else:
                raise ValueError("Value was not a string or a list")

def __bypass_deps(ds, bypass, pkg_attrs):
        """Return a list of dependencies, excluding any of those that should be
        bypassed.

        ds         the list of dependencies to operate on
        bypass     a list of paths on which we should not generate dependencies
        pkg_attrs  the set of package attributes for this manifest, produced as
                   a by-product of this dependency generation

        We support regular expressions as entries in the bypass list, matching
        one or more files.

        If a bypass-list entry is provided that does not contain one of the
        following characters: ["/", "*", "?"], it is assumed to be a filename,
        and expanded to the regular expression ".*/<entry>"

        All bypass-list entries are assumed to be regular expressions that are
        rooted at ^ and $.

        The special match-all wildcard ".*" is dealt with separately,
        by list_implicit_deps_for_manifest(..)
        """

        new_ds = []
        for dep in ds:
                full_paths = set(make_paths(dep))
                bypassed_files = set()
                bypass_regexps = []
                try:
                        for item in bypass:
                                # try to determine if this is a regexp,
                                # rather than a filename
                                if "*" in item or "?" in item:
                                        pass
                                # if it appears to be a filename, make it match
                                # all paths to that filename.
                                elif "/" not in item:
                                        item = ".*{0}{1}".format(os.path.sep,
                                            item)

                                # always anchor our regular expressions,
                                # otherwise, we get partial matches for files,
                                # eg. bypassing "foo.c" would otherwise also
                                # bypass "foo.cc"
                                if item:
                                        if not item.endswith("$"):
                                                item = item + "$"
                                        if not item.startswith("^"):
                                                item = "^" + item
                                        bypass_regexps.append(re.compile(item))
                except re.error as e:
                        raise base.InvalidDependBypassValue(item, e)

                for path in full_paths:
                        if path in bypass:
                                bypassed_files.add(path)
                                continue
                        for regexp in bypass_regexps:
                                if regexp.match(path):
                                        bypassed_files.add(path)

                if bypassed_files:
                        # remove the old runpath and basename entries from
                        # the dependency if they were present
                        dep.attrs.pop(files_prefix, None)
                        dep.attrs.pop(paths_prefix, None)
                        dep.base_names = []
                        dep.run_paths = []

                        # determine our new list of paths
                        full_paths = full_paths - bypassed_files

                        dep.full_paths = sorted(list(full_paths))
                        dep.attrs[fullpaths_prefix] = dep.full_paths
                        pkg_attrs[bypassed_prefix] = \
                            sorted(list(bypassed_files))

                        # only include the dependency if it still contains data
                        if full_paths:
                                new_ds.append(dep)
                else:
                        new_ds.append(dep)
        return new_ds

def __make_manifest(fp, basedirs=None, load_data=True):
        """Given the file path, 'fp', return a Manifest for that path."""

        m = manifest.Manifest()
        try:
                fh = open(fp, "r")
        except EnvironmentError as e:
                raise apx._convert_error(e)
        acts = []
        missing_files = []
        action_errs = []
        accumulate = ""
        for l in fh:
                l = l.strip()
                if l.endswith("\\"):
                        accumulate += l[0:-1]
                        continue
                elif accumulate:
                        l = accumulate + l
                        accumulate = ""
                if not l or l[0] == '#':
                        continue
                try:
                        a, local_path, used_bd = actions.internalizestr(l,
                            basedirs=basedirs,
                            load_data=load_data)

                except actions.ActionDataError as e:
                        new_a, local_path, used_bd = actions.internalizestr(
                            l, basedirs=basedirs, load_data=False)
                        if new_a.name == "license":
                                local_path = None
                                a = new_a
                        else:
                                missing_files.append(base.MissingFile(
                                    new_a.attrs["path"], basedirs))
                                continue
                except actions.ActionError as e:
                        action_errs.append(e)
                        continue
                else:
                        # If this action has a payload, add the information
                        # about where that payload file lives to the action.
                        if local_path:
                                assert portable.PD_LOCAL_PATH not in a.attrs
                                a.attrs[portable.PD_LOCAL_PATH] = local_path
                                a.attrs[portable.PD_PROTO_DIR] = used_bd
                                a.attrs[portable.PD_PROTO_DIR_LIST] = basedirs
                try:
                        a.validate()
                except actions.ActionError as e:
                        action_errs.append(e)
                else:
                        acts.append(a)
        fh.close()
        m.set_content(content=acts)
        return m, missing_files + action_errs

def choose_name(fp, mfst):
        """Find the package name for this manifest.  If it's defined in a set
        action in the manifest, use that.  Otherwise use the basename of the
        path to the manifest as the name.  If a proper package fmri is found,
        then also return a PkgFmri object so that we can track which packages
        are being processed.

        'fp' is the path to the file for the manifest.

        'mfst' is the Manifest object."""

        if mfst is None:
                return unquote(os.path.basename(fp)), None
        name = mfst.get("pkg.fmri", mfst.get("fmri", None))
        if name is not None:
                try:
                        pfmri = fmri.PkgFmri(name)
                except fmri.IllegalFmri:
                        pfmri = None
                return name, pfmri
        return unquote(os.path.basename(fp)), None

def make_paths(file_dep):
        """Find all the possible paths which could satisfy the dependency
        'file_dep'."""

        if file_dep.attrs.get(fullpaths_prefix, []):
                return file_dep.attrs[fullpaths_prefix]

        rps = file_dep.attrs.get(paths_prefix, [""])
        files = file_dep.attrs[files_prefix]
        if isinstance(files, six.string_types):
                files = [files]
        if isinstance(rps, six.string_types):
                rps = [rps]
        return [os.path.join(rp, f) for rp in rps for f in files]

def resolve_links(path, files_dict, links, path_vars, file_dep_attrs, index=1):
        """This method maps a path to one or more real paths and the variants
        under which each real path can exist.

        'path' is the original text of the path which is being resolved to a
        real path.

        'files_dict' is a dictionary which maps package identity to the files
        the package delivers and the variants under which each file is present.

        'links' is an Entries namedtuple which contains two dictionaries.  One
        dictionary maps package identity to the links that it delivers.  The
        other dictionary, contains the same information for links that are
        installed on the system.

        'path_vars' is the set of variants under which 'path' exists.

        'file_dep_attrs' is the dictonary of attributes for the file dependency
        for 'path'.

        'index' indicates how much of 'path' should be checked against the file
        and link dictionaries."""

        res_paths = []
        res_links = []

        # If the current path is a known file, then we might be done resolving
        # the path.
        if path in files_dict:
                # Copy the variants so that marking the variants as satisified
                # doesn't change the sate of 'path_vars.'
                tmp_vars = copy.copy(path_vars)
                # If tmp_vars has been satisfied, then this function should
                # never have been called.
                assert(tmp_vars.is_empty() or not tmp_vars.is_satisfied())
                # Check each package which delivers a file with this path.
                for pfmri, p_vc in files_dict[path]:
                        # If the file is delivered under a set of variants which
                        # are irrelevant to the path being considered, skip it.
                        if not path_vars.intersects(p_vc):
                                continue
                        # The intersection of the variants which apply to the
                        # current path and the variants for the delivered file
                        # is the combination of variants where the original
                        # path resolves to the delivered file.
                        inter = path_vars.intersection(p_vc)
                        inter.mark_all_as_satisfied()
                        tmp_vars.mark_as_satisfied(p_vc)
                        res_paths.append(LinkInfo(path, pfmri, pfmri, inter,
                            []))
                # If the path was resolved under all relevant variants, then
                # we're done.
                if res_paths and tmp_vars.is_satisfied():
                        return res_paths, res_links

        lst = path.split(os.path.sep)
        # If there aren't any more pieces of the path left to check, then
        # there's nothing to do so return whatever has been found so far.
        if index > len(lst):
                return res_paths, res_links

        # Create the path to check for links.
        cur_path = os.path.join(*lst[0:index])
        # Find the links which match the path being checked.
        rel_links = links.get(cur_path, False)
        # If there weren't any relevant links, then add the next path component
        # to the path being considered and try again.
        if not rel_links:
                return resolve_links(path, files_dict, links, path_vars,
                    file_dep_attrs, index=index+1)

        links_found = {}
        for link_pfmri, link_vc, rel_target in rel_links:
                # If the variants needed to reach the current path and the
                # variants for the link don't intersect, then the link is
                # irrelevant.
                if not path_vars.intersects(link_vc):
                        continue
                vc_intersection = path_vars.intersection(link_vc)
                # If the link only matters under variants that are satisfied,
                # then it's not an interesting link for this purpose.
                if vc_intersection.is_satisfied() and \
                    not vc_intersection.is_empty():
                        continue
                # Apply the link to the current path to get the new relevant
                # path.
                next_path = os.path.normpath(os.path.join(
                    os.path.dirname(cur_path), rel_target,
                    *lst[index:])).lstrip(os.path.sep)
                # Index is reset back to the default because an element in path
                # the link provides could actually be a link.
                rec_paths, link_deps = resolve_links(next_path, files_dict,
                    links, vc_intersection, file_dep_attrs)
                if not rec_paths:
                        continue
                # The current path was able to be resolved to a real path, so
                # add the paths and the dependencies from links found to the
                # results.
                res_links.extend(link_deps)
                for rec_path, rec_pfmri, nearest_pfmri, rec_vc, via_links in \
                    rec_paths:
                        via_links.append(path)
                        assert vc_intersection.intersects(rec_vc), \
                            "vc:{0}\nvc_intersection:{1}".format(
                            rec_vc, vc_intersection)
                        links_found.setdefault(next_path, []).append(
                            (link_pfmri, nearest_pfmri, rec_vc))
                        res_paths.append(LinkInfo(rec_path, rec_pfmri,
                            link_pfmri, rec_vc, via_links))

        # Now add in the dependencies for the current link.
        for next_path in links_found.keys():
                cur_deps = group_by_variant_combinations(links_found[next_path])
                for pfmri_pairs, vc in cur_deps:
                        # Make a copy of path_vars which is unsatisfied, then
                        # mark the specific combinations which are satisfied by
                        # this group of pfmris.
                        dep_vc = path_vars.unsatisfied_copy()
                        dep_vc.mark_as_satisfied(vc)
                        for l_pfmri, r_pfmri in pfmri_pairs:
                                if l_pfmri == r_pfmri:
                                        continue
                                dep_type = "conditional"
                                attrs = file_dep_attrs.copy()
                                attrs.update({
                                    "fmri": l_pfmri.get_short_fmri(),
                                    "predicate": r_pfmri.get_short_fmri(),
                                    type_prefix: "link",
                                    files_prefix: [path],
                                    "type": dep_type,
                                })
                                attrs.pop(paths_prefix, None)
                                attrs.pop(fullpaths_prefix, None)
                                # The dependency is created with the same
                                # variants as the path.  This works because the
                                # set of relevant variants is restricted as
                                # links are applied so the variants used for the
                                # path are the intersection of the variants for
                                # each of the links used to reach the path and
                                # the variants under which the file is
                                # delivered.
                                res_links.append((
                                    actions.depend.DependencyAction(**attrs),
                                    dep_vc))

        return res_paths, res_links

def find_package_using_delivered_files(files_dict, links, file_dep, dep_vars,
    orig_dep_vars):
        """Maps a dependency on a file to the packages which can satisfy that
        dependency.

        'files_dict' is a dictionary mapping paths to a list of fmri, variants
        pairs.

        'links' is an Entries namedtuple which contains two dictionaries.  One
        dictionary maps package identity to the links that it delivers.  The
        other dictionary, contains the same information for links that are
        installed on the system.

        'file_dep' is the dependency that is being resolved.

        'dep_vars' are the variants for which the dependency has not yet been
        resolved.

        'orig_dep_vars' is the original set of variants under which the
        dependency must be satisfied."""

        res = []
        errs = []
        link_deps = []
        cur_deps = []

        pths = sorted(make_paths(file_dep))
        pth_id = ":".join(pths)
        for p in pths:
                # If orig_dep_vars is satisfied, then this function should never
                # have been called.
                assert(orig_dep_vars.is_empty() or
                    not orig_dep_vars.is_satisfied())
                # Find the packages which satisfy this path of the file
                # dependency and the links needed to reach the files which those
                # packages provide.
                paths_info, path_deps = resolve_links(os.path.normpath(p),
                    files_dict, links, orig_dep_vars, file_dep.attrs.copy())
                link_deps.extend(path_deps)
                cur_deps += paths_info
        # Because all of the package dependencies are ultimately satisfying the
        # same file dependency, they should all be grouped together.
        cur_deps = group_by_variant_combinations([
            (t.path, t.pfmri, t.via_links, t.variant_combination)
            for t in cur_deps
        ])

        for l, vc in cur_deps:
                dep_vars.mark_as_satisfied(vc)
                attrs = file_dep.attrs.copy()
                dep_type = "require-any"
                # Find the packages which satisify this file dependency.  Using
                # the short fmri is appropriate for these purposes because
                # dependencies can never be inferred on different versions of
                # the same package during a single run of resolve.
                pfmri_names = sorted(set([
                    pfmri.get_short_fmri()
                    for path, pfmri, vl in l
                ]))
                paths = sorted(set([
                    path for path, pfmri, vl in l
                ]))
                via_links = []
                # If only a single package satisfies this dependency, then a
                # require dependency should be created, otherwise a require-any
                # is needed.
                if len(pfmri_names) == 1:
                        dep_type = "require"
                        pfmri_names = pfmri_names[0]
                        via_links = l[0][2]
                        via_links.reverse()
                        via_links = ":".join(via_links)
                else:
                        for path, pfmri, vl in l:
                                vl.reverse()
                                via_links.append(":".join(vl))
                attrs.pop(paths_prefix, None)
                attrs.pop(fullpaths_prefix, None)
                attrs.update({
                    "type": dep_type,
                    "fmri": pfmri_names,
                    files_prefix: paths,
                })
                if via_links:
                        attrs[via_links_prefix] = via_links
                res.append((actions.depend.DependencyAction(**attrs), vc))

        res.extend(link_deps)
        # Add the path id so that these dependencies analyzed for simplification
        # as a group.
        for d, v in res:
                d.attrs[path_id_prefix] = pth_id
        return res, dep_vars, errs

def find_package(files, links, file_dep, orig_dep_vars, pkg_vars, use_system):
        """Find the packages which resolve the dependency. It returns a list of
        dependency actions with the fmri tag resolved.

        'files' is an Entries namedtuple which contains two dictionaries.  One
        dictionary maps package identity to the files that it delivers.  The
        other dictionary, contains the same information for files that are
        installed on the system.

        'links' is an Entries namedtuple which contains two dictionaries.  One
        dictionary maps package identity to the links that it delivers.  The
        other dictionary, contains the same information for links that are
        installed on the system.

        'file_dep' is the dependency being resolved.

        'orig_dep_vars' is the original set of variants under which the
        dependency must be satisfied.

        'pkg_vars' is the variants against which the package was published."""

        # If the file dependency has already satisfied all its variants, then
        # this function should never have been called.
        assert(orig_dep_vars.is_empty() or not orig_dep_vars.is_satisfied())
        dep_vars = copy.copy(orig_dep_vars)
        # First try to resolve the dependency against the delivered files.
        res, dep_vars, errs = find_package_using_delivered_files(
                files.delivered, links, file_dep, dep_vars, orig_dep_vars)
        # If dep_vars is satisfied then we found at least one solution.  It's
        # possible that more than one solution was found, causing an error.
        assert(not dep_vars.is_satisfied() or
            (res or errs or dep_vars.is_empty()))
        if ((res or errs) and dep_vars.is_satisfied()) or not use_system:
                return res, dep_vars, errs

        # If the dependency isn't fully satisfied, resolve it against the
        # files installed in the current image.
        #
        # We only need to resolve for the variants not already satisfied
        # above.
        const_dep_vars = copy.copy(dep_vars)
        # If dep_vars has been satisfied, then we should have exited the
        # function above.
        assert(const_dep_vars.is_empty() or not const_dep_vars.is_satisfied())
        inst_res, dep_vars, inst_errs = find_package_using_delivered_files(
            files.installed, links, file_dep, dep_vars, const_dep_vars)
        res.extend(inst_res)
        errs.extend(inst_errs)
        return res, dep_vars, errs

def is_file_dependency(act):
        return act.name == "depend" and \
            act.attrs.get("fmri", None) == base.Dependency.DUMMY_FMRI and \
            (files_prefix in act.attrs or fullpaths_prefix in act.attrs)

def group_by_variant_combinations(lst):
        """The goal of this function is to produce the smallest list of (info
        list, VariantCombinations) tuples which has the following properties:

        1. The intersection between any two satisfied sets of the
        VariantCombinations must be empty.

        2. If a piece of information was satisfied under a particular
        combination of variants, that information must be paired with the
        VariantCombination which has that combination in its satisfied set.

        Note: A piece of information can appear more than once in the result.

        The 'lst' parameter is a list of tuples.  The last item in each tuple
        must be a VariantCombination. The rest of each tuple is the "piece of
        information" discussed above."""

        seed = []
        for item in lst:
                # Separate the VariantCombination out from the info to be
                # grouped.
                i_vc = item[-1]
                info = item[:-1]
                # If there's only a single piece of information, then take it
                # out of a list.
                if len(info) == 1:
                        info = info[0]
                new_res = []
                for old_info, old_vc in seed:
                        # If i_vc is None, then variant combinations under which
                        # 'info' is satisfied have been covered by previous
                        # old_vc's and info has already been merged in, so just
                        # finish extending the list with the existing
                        # information.
                        if i_vc is None:
                                new_res.append((old_info, old_vc))
                                continue
                        # Check to see how i_vc and old_vc's satisfied sets
                        # overlap.
                        only_i, intersect, only_old = \
                            i_vc.separate_satisfied(old_vc)
                        assert only_i or intersect or only_old
                        assert only_i or i_vc.issubset(old_vc, True)
                        assert only_old or old_vc.issubset(i_vc, True)
                        assert intersect or (only_i and only_old)
                        # If there are any variant combinations where old_vc is
                        # satisfied but i_vc is not, add the VariantCombination
                        # for those combinations to the list along with the
                        # old_info.
                        if only_old:
                                new_res.append((old_info, only_old))
                        # If i_vc and old_vc are both satisfied under some
                        # variant combinations, then add info into the old_info
                        # under those variant combinations.
                        if intersect:
                                tmp = old_info[:]
                                tmp.append(info)
                                new_res.append((tmp, intersect))
                        # The relevant variant combinations to consider now are
                        # those that didn't overlap with old_vc.
                        i_vc = only_i
                # If i_vc is not None, then i_vc was satisfied under some
                # variant combinations which no other VariantCombination was, so
                # add it to the list.
                if i_vc is not None:
                        new_res.append(([info], i_vc))
                seed = new_res
        return seed

def merge_deps(dest, src):
        """Add the information contained in src's attrs to dest."""

        for k, v in src.attrs.items():
                # If any of these dependencies already have a variant set,
                # then something's gone horribly wrong.
                assert(not k.startswith("variant."))
                if k not in dest.attrs:
                        dest.attrs[k] = v
                elif v != dest.attrs[k]:
                        # For now, just merge the values. Duplicate values
                        # will be removed in a later step.
                        if isinstance(v, six.string_types):
                                v = [v]
                        if isinstance(dest.attrs[k], list):
                                dest.attrs[k].extend(v)
                        else:
                                t = [dest.attrs[k]]
                                t.extend(v)
                                dest.attrs[k] = t

def __predicate_path_id_attrget(d):
        # d is a tuple containing two items.  d[0] is the action.  d[1]
        # is the VariantCombination for this action.  The
        # VariantCombination isn't useful for our grouping needs.
        try:
                return d[0].attrs["predicate"], \
                    d[0].attrs.get(path_id_prefix, None)
        except KeyError:
                raise RuntimeError("Expected this to have a predicate:{0}".format(
                    d[0]))

def __collapse_conditionals(deps):
        """Under certain conditions, conditional dependencies can be transformed
        into require-any or require dependencies.  This function is responsible
        for performing the transformation.

        The 'deps' parameter is a list of dependency action and
        VariantCombination tuples."""

        # Construct a dictionary which maps a package name to a list of
        # dependencies which require that package.
        req_dict = {}
        for d, v in deps:
                if d.attrs["type"] != "require":
                        continue
                t_pfmri = fmri.PkgFmri(d.attrs["fmri"])
                req_dict.setdefault(t_pfmri.get_pkg_stem(include_scheme=False),
                    []).append((t_pfmri, d, v))

        cond_deps = {}
        preds_to_process = set()
        for (predicate, path_id), group in itertools.groupby(sorted(
            [(d, v) for d, v in deps if d.attrs["type"] == "conditional"],
            key=__predicate_path_id_attrget), __predicate_path_id_attrget):
                group = list(group)
                cond_deps.setdefault(predicate, []).append((path_id, group))
                preds_to_process.add(predicate)

        new_req_deps = []

        # While there are still require dependencies which might be used to
        # transform a conditional dependency...
        while preds_to_process:
                # Pick a fmri which might be the predicate of a conditional
                # dependency that could be collapsed.
                predicate = preds_to_process.pop()
                t_pfmri = fmri.PkgFmri(predicate)
                t_name = t_pfmri.get_pkg_stem(include_scheme=False)
                # If there are no require dependencies with that package name as
                # a target, then there's nothing to do.
                if t_name not in req_dict:
                        continue
                rel_reqs = []
                # Only require dependencies whose fmri is a successor to the
                # fmri under consideration are interesting.
                for req_fmri, d, v in req_dict[t_name]:
                        if req_fmri.is_successor(t_pfmri):
                                rel_reqs.append((d, v))
                if not rel_reqs:
                        continue

                new_group = []
                for path_id, group in cond_deps.get(predicate, []):
                        tmp_deps = []
                        # Group all of the conditional dependencies inferred for
                        # path_id by the variant combinations under which
                        # they're valid.
                        tmp_deps = group_by_variant_combinations(group)

                        collapse_deps = []
                        no_collapse = []
                        # Separate the conditional dependencies into those that
                        # can be collapsed and those that can't.  If a
                        # conditional dependency intersects with any of the
                        # relevant required dependencies found earlier, it can
                        # be collapsed.
                        for ds, v in tmp_deps:
                                for req_d, req_v in rel_reqs:
                                        only_tmp, intersect, only_req = \
                                            v.separate_satisfied(req_v)
                                        assert only_tmp or intersect or only_req
                                        assert only_tmp or \
                                            v.issubset(req_v, True)
                                        assert only_req or v.issubset(v, True)
                                        assert intersect or \
                                            (only_tmp and only_req)
                                        if intersect:
                                                collapse_deps.append(
                                                    (ds, intersect))
                                        v = only_tmp
                                        if v is None:
                                                break
                                if v is not None:
                                        no_collapse.extend([(d, v) for d in ds])

                        if no_collapse:
                                new_group.append((path_id, no_collapse))

                        # If path_id is None, then these conditional
                        # dependencies were not inferred links needed to reach a
                        # file dependency.  In that case, the conditional
                        # dependencies can be individually collapsed to require
                        # dependencies but cannot be collapsed together into a
                        # require-any dependency.
                        if path_id is None:
                                for ds, v in collapse_deps:
                                        for d in ds:
                                                res_dep = actions.depend.DependencyAction(**d.attrs)
                                                del res_dep.attrs["predicate"]
                                                res_dep.attrs["type"] = \
                                                    "require"
                                                new_req_deps.append(
                                                    (res_dep, v))
                                                # Since a new require dependency
                                                # has been created, its possible
                                                # that conditional dependencies
                                                # could be collapsed using that,
                                                # so add the fmri to the
                                                # predicates to be processed.
                                                preds_to_process.add(
                                                    res_dep.attrs["fmri"])
                                                t_pfmri = fmri.PkgFmri(
                                                    d.attrs["fmri"])
                                                req_dict.setdefault(
                                                    t_pfmri.get_pkg_stem(
                                                        include_scheme=False),
                                                    []).append(
                                                        (t_pfmri, res_dep, v))
                                continue

                        # Since path_id is not None, these conditional
                        # dependencies were all inferred while trying to satisfy
                        # a dependency on the same "file."  Since they all have
                        # the same predicate, they must be collapsed into a
                        # require-any dependency because each represents a valid
                        # step through the link path to reach the dependened
                        # upon file.
                        for ds, v in collapse_deps:
                                res_dep = actions.depend.DependencyAction(
                                    **ds[0].attrs)
                                for d in ds[1:]:
                                        merge_deps(res_dep, d)
                                d = ds[-1]
                                res_dep.attrs["fmri"] = list(set(
                                    res_dep.attrlist("fmri")))
                                if len(res_dep.attrlist("fmri")) > 1:
                                        res_dep.attrs["type"] = "require-any"
                                else:
                                        res_dep.attrs["type"] = "require"
                                        res_dep.attrs["fmri"] = \
                                            res_dep.attrs["fmri"][0]
                                        # Since a new require dependency has
                                        # been created, its possible that
                                        # conditional dependencies could be
                                        # collapsed using that, so add the fmri
                                        # to the predicates to be processed.
                                        preds_to_process.add(
                                            res_dep.attrs["fmri"])
                                        t_pfmri = fmri.PkgFmri(d.attrs["fmri"])
                                        req_dict.setdefault(
                                            t_pfmri.get_pkg_stem(
                                                include_scheme=False),
                                            []).append((t_pfmri, res_dep, v))
                                del res_dep.attrs["predicate"]
                                new_req_deps.append((res_dep, v))
                # Now that all the new require dependencies have been removed,
                # update the remaining conditional dependencies for this
                # predicate.
                if new_group:
                        cond_deps[predicate] = new_group
                elif predicate in cond_deps:
                        del cond_deps[predicate]

        # The result is the original non-conditional dependencies ...
        res = [(d, v) for d, v in deps if d.attrs["type"] != "conditional"]
        # plus the new require or require-any dependencies made by collapsing
        # the conditional dependencies ...
        res += new_req_deps
        # plus the conditional dependencies that couldn't be collapsed.
        for l in cond_deps.values():
                for path_id, dep_pairs in l:
                        res.extend(dep_pairs)
        return res

def __remove_unneeded_require_and_require_any(deps, pkg_fmri):
        """Drop any unneeded require or require any dependencies and record any
        dropped require-any dependencies which were inferred."""

        res = []
        omitted_req_any = {}
        fmri_dict = {}
        warnings = []
        # 
        # We assume that the subsets are shorter than the supersets.
        # 
        # Example:
        # #1 depend fmri=a, fmri=b, fmri=c, type=require-any
        # #2 depend fmri=a, fmri=b, type=require=any
        # #2 is treated as a subset of #1
        #
        # Sort the dependencies by length to visit the subsets before the
        # supersets.
        # 
        for cur_dep, cur_vars in sorted(deps, key=lambda i: len(str(i))):
                if cur_dep.attrs["type"] not in ("require", "require-any"):
                        res.append((cur_dep, cur_vars))
                        continue

                cur_fmris = []
                for f in cur_dep.attrlist("fmri"):
                        cur_fmris.append(fmri.PkgFmri(f))
                skip = False
                # If we're resolving a pkg with a known name ...
                if pkg_fmri is not None:
                        for pfmri in cur_fmris:
                                # Then if this package is a successor to any of
                                # the packages the dependency requires, then we
                                # can omit the dependency.
                                if pkg_fmri.is_successor(pfmri):
                                        skip = True
                if skip:
                        continue

                # If this dependency isn't a require-any dependency, then it
                # should be included in the output.
                if cur_dep.attrs["type"] != "require-any":
                        res.append((cur_dep, cur_vars))
                        continue

                marked = False
                # Now the require-any dependency is going to be compared to all
                # the known require dependencies to see if it can be omitted.
                # It can be omitted if one of the packages it requires is
                # already required.  Because a require-any dependency could be
                # omitted under some, but not all, variant combinations, the
                # satisfied set of the variant combination of the require-any
                # dependency is used for bookkeeping.  Each require dependency
                # which has a successor to one of the packages in the
                # require-any dependency marks the variant combinations under
                # which it's valid as unsatisfied in the require-any dependency.
                # At the end, if the require-any dependency is still satisfied
                # under any variant combinations, then it's included in the
                # result.
                successors = []
                for comp_dep, comp_vars in deps:
                        if comp_dep.attrs["type"] != "require":
                                continue
                        successor = False
                        comp_fmri = fmri.PkgFmri(comp_dep.attrs["fmri"])
                        # Check to see whether the package required by the
                        # require dependency is a successor to any of the
                        # packages required by the require-any dependency.
                        for c in cur_fmris:
                                if comp_fmri.is_successor(c):
                                        successor = True
                                        break
                        if not successor:
                                continue
                        # If comp_vars is empty, then no variants have been
                        # declared for these packages, so having a matching
                        # require dependency is enough to omit this require-any
                        # dependency.
                        only_cur, inter, only_comp = \
                            cur_vars.separate_satisfied(comp_vars)
                        if cur_vars.mark_as_unsatisfied(comp_vars) or \
                            comp_vars.is_empty():
                                marked = True
                                successors.append((comp_fmri, inter))

                # If one require-any dependency is the subset of the other
                # require-any dependency, we should drop the superset because
                # ultimately they should end up with the package dependency
                # as the subset requires.
                #
                # Note that we only drop the deps we generate (with the
                # pkgdepend.debug.depend.* prefix); we ignore the deps a
                # developer added.
                is_superset = False
                if files_prefix in cur_dep.attrs or \
                    fullpaths_prefix in cur_dep.attrs:
                        # convert to a set for set operation
                        cur_fmris_set = set(cur_fmris)
                        for (comp_dep, comp_vars), comp_fmris_set in \
                            six.iteritems(fmri_dict):
                                if comp_fmris_set != cur_fmris_set and \
                                    comp_fmris_set.issubset(cur_fmris_set) and \
                                    cur_vars == comp_vars:
                                        is_superset = True
                                        drop_f = cur_fmris_set - comp_fmris_set
                                        warnings.append(DropPackageWarning(
                                            drop_f, comp_dep))
                                        break
                        if not is_superset:
                                fmri_dict.setdefault((cur_dep, cur_vars),
                                    cur_fmris_set)

                # If the require-any dependency was never changed or is not a
                # superset of any other require-any dependency, then include
                # it.  If it was changed, check whether there are situations
                # where the require-any dependency is needed.
                if not marked and not is_superset:
                        res.append((cur_dep, cur_vars))
                        continue
                if cur_vars.sat_set and not is_superset:
                        res.append((cur_dep, cur_vars))
                path_id = cur_dep.attrs.get(path_id_prefix, None)
                if path_id:
                        omitted_req_any[path_id] = successors

        return res, omitted_req_any, warnings

def __remove_extraneous_conditionals(deps, omitted_req_any):
        """Remove conditional dependencies which other dependencies have made
        unnecessary.  If an inferred require-any dependency was collapsed to a
        require dependency, then only the conditional dependencies needed to
        reach the require dependency should be retained."""

        def fmri_attrget(d):
                return fmri.PkgFmri(d[0].attrs["fmri"]).get_pkg_stem(
                    include_scheme=False)

        def path_id_attrget(d):
                return d[0].attrs.get(path_id_prefix, None)

        req_dict = {}
        for target, group in itertools.groupby(sorted(
            [(d, v) for d, v in deps if d.attrs["type"] == "require"],
            key=fmri_attrget), fmri_attrget):
                req_dict[target] = list(group)

        needed_cond_deps = []
        for path_id, group in itertools.groupby(sorted(
            [(d, v) for d, v in deps if d.attrs["type"] == "conditional"],
            key=path_id_attrget), path_id_attrget):
                # Because of how the list was created, each dependency in
                # successors is not satisfied under the same set of variant
                # values as any other dependency in successors.
                successors = omitted_req_any.get(path_id, [])
                for d, v in group:
                        # If this conditional dependency was part of a path to a
                        # require-any dependency which was reduced to a require
                        # dependency under some combinations of variants, then
                        # make sure this conditional doesn't apply under those
                        # combinations of variants.
                        skip = False
                        for s_d, s_v in successors:
                                # If s_v is empty, then s_d applies under all
                                # variant combinations.
                                if s_v.is_empty():
                                        skip = True
                                        break
                                v.mark_as_unsatisfied(s_v)
                        if skip or (not v.is_empty() and not v.sat_set):
                                continue

                        # If this conditional dependency's fmri is also the fmri
                        # of a require dependency, then it can be ignored under
                        # those combinations of variants under which the require
                        # dependency applies.
                        d_fmri = fmri.PkgFmri(d.attrs["fmri"])
                        for r_d, r_v in req_dict.get(d_fmri.get_pkg_stem(
                            include_scheme=False), []):
                                r_fmri = fmri.PkgFmri(r_d.attrs["fmri"])
                                if not r_fmri.is_successor(d_fmri):
                                        continue
                                if r_v.is_empty():
                                        skip = True
                                        break
                                v.mark_as_unsatisfied(r_v)
                        if not skip and (v.is_empty() or v.sat_set):
                                needed_cond_deps.append((d, v))

        return [(d, v) for d, v in deps if d.attrs["type"] != "conditional"] + \
            needed_cond_deps

def combine(deps, pkg_vars, pkg_fmri, pkg_name):
        """Combine duplicate dependency actions.

        'deps' is a list of tuples. Each tuple contains a dependency action and
        the variants associated with that dependency.

        'pkg_vars' are the variants that the package for which dependencies are
        being generated was published against.

        'pkg_fmri' is the name of the package being resolved.  This can be None.

        'pkg_name' is either the same as 'pkg_fmri', if 'pkg_fmri' is not None,
        or it's the basename of the path to the manifest being resolved."""

        def action_group_key(d):
                """Return a key on which the tuples can be sorted and grouped
                so that the groups match the duplicate actions that the code
                in pkg.manifest notices."""

                # d is a tuple containing two items.  d[0] is the action.  d[1]

                # is the VariantCombination for this action.  The
                # VariantCombination isn't useful for our grouping needs.
                return d[0].name, d[0].attrs.get("type", None), \
                    d[0].attrs.get("predicate", None), \
                    d[0].attrs.get(d[0].key_attr, id(d[0]))

        def add_vars(d, d_vars, pkg_vars):
                """Add the variants 'd_vars' to the dependency 'd', after
                removing the variants matching those defined in 'pkg_vars'."""

                d_vars.simplify(pkg_vars)
                res = []
                for s in d_vars.sat_set:
                        attrs = d.attrs.copy()
                        attrs.update(s)
                        t = actions.depend.DependencyAction(**attrs)
                        t.consolidate_attrs()
                        res.append(t)
                if not res:
                        d.consolidate_attrs()
                        res = [d]
                return res

        # Transform conditional dependencies into require or require-any
        # dependencies where possible.
        res = __collapse_conditionals(deps)

        errs = []

        # Remove require dependencies on this package and require-any
        # dependencies which are unneeded.
        res, omitted_require_any, warnings = \
            __remove_unneeded_require_and_require_any(res, pkg_fmri)

        # Now remove all conditionals which are no longer needed.
        res = __remove_extraneous_conditionals(res, omitted_require_any)

        # There are certain dependency relationships between packages that the
        # current dependency types can't properly represent.  One is the case
        # where if A is present then either B or C must be installed.  In this
        # situation, find_package_using_delivered_files will have inferred a
        # conditional dependency on B if A is present and another one on C if A
        # is present.  The following code detects this situation and provides an
        # error to the user.
        conflicts = []
        for (predicate, path_id), group in itertools.groupby(sorted(
            [(d, v) for d, v in res if d.attrs["type"] == "conditional"],
            key=__predicate_path_id_attrget), __predicate_path_id_attrget):
                if not path_id:
                        continue
                group = list(group)
                for i, (d1, v1) in enumerate(group):
                        for d2, v2 in group[i + 1:]:
                                only_v1, inter, only_v2 = \
                                    v1.separate_satisfied(v2)
                                if (inter.is_empty() or inter.sat_set) and \
                                    d1.attrs["fmri"] != d2.attrs["fmri"]:
                                        conflicts.append((d1, d2, inter))
        if conflicts:
                errs.append(NeedConditionalRequireAny(conflicts, pkg_vars))

        # For each group of dependencies (g) for a particular fmri (k) merge
        # together depedencies on the same fmri with different variants.
        new_res = []
        for k, group in itertools.groupby(sorted(res, key=action_group_key),
            action_group_key):
                group = list(group)
                res_dep = group[0][0]
                res_vars = variants.VariantCombinations(pkg_vars, False)
                for cur_dep, cur_vars in group:
                        merge_deps(res_dep, cur_dep)
                        res_vars.mark_as_satisfied(cur_vars)
                new_res.append((res_dep, res_vars))
        res = new_res

        # Merge the variant information into the depend action.
        new_res = []
        for d, vc in res:
                new_res.extend(add_vars(d, vc, pkg_vars))
        res = new_res

        return res, errs, warnings

def split_off_variants(dep, pkg_vars, satisfied=False):
        """Take a dependency which may be tagged with variants and move those
        tags into a VariantSet."""

        dep_vars = dep.get_variant_template()
        if not dep_vars.issubset(pkg_vars):
                raise __NotSubset(dep_vars.difference(pkg_vars))
        dep_vars.merge_unknown(pkg_vars)
        # Since all variant information is being kept in the above VariantSets,
        # remove the variant information from the action.  This prevents
        # confusion about which is the authoritative source of information.
        dep.strip_variants()
        return dep, variants.VariantCombinations(dep_vars, satisfied=satisfied)

def prune_debug_attrs(action):
        """Given a dependency action with pkg.debug.depend attributes
        return a matching action with those attributes removed"""

        attrs = dict((k, v) for k, v in six.iteritems(action.attrs)
                     if not k.startswith(base.Dependency.DEPEND_DEBUG_PREFIX))
        return actions.depend.DependencyAction(**attrs)

def add_fmri_path_mapping(files_dict, links_dict, pfmri, mfst,
    distro_vars=None, use_template=False):
        """Add mappings from path names to FMRIs and variants.

        'files_dict' is a dictionary which maps package identity to the files
        the package delivers and the variants under which each file is
        present.

        'links_dict' is a dictionary which maps package identity to the links
        the package delivers and the variants under which each link is
        present.

        'pfmri' is the FMRI of the current manifest.

        'mfst' is the manifest to process.

        'distro_vars' is a VariantCombinationTemplate which contains all the
        variant types and values known.

        'use_template is a boolean which indicates whether to fill the
        dictionaries with VariantCombinationTemplates instead of
        VariantCombinations."""

        assert not distro_vars or not use_template
        if not use_template:
                pvariants = mfst.get_all_variants()
                if distro_vars:
                        pvariants.merge_unknown(distro_vars)

        for f in mfst.gen_actions_by_type("file"):
                vc = f.get_variant_template()
                if not use_template:
                        vc.merge_unknown(pvariants)
                        vc = variants.VariantCombinations(vc,
                            satisfied=True)
                files_dict.setdefault(f.attrs["path"], []).append(
                    (pfmri, vc))
        for f in itertools.chain(mfst.gen_actions_by_type("hardlink"),
             mfst.gen_actions_by_type("link")):
                vc = f.get_variant_template()
                if not use_template:
                        vc.merge_unknown(pvariants)
                        vc = variants.VariantCombinations(vc,
                            satisfied=True)
                links_dict.setdefault(f.attrs["path"], []).append(
                    (pfmri, vc, f.attrs["target"]))

def __safe_fmri_parse(txt):
        dep_name = None
        try:
                dep_name = fmri.PkgFmri(txt).pkg_name
        except fmri.IllegalFmri:
                pass
        return dep_name

def resolve_deps(manifest_paths, api_inst, system_patterns, prune_attrs=False):
        """For each manifest given, resolve the file dependencies to package
        dependencies. It returns a mapping from manifest_path to a list of
        dependencies and a list of unresolved dependencies.

        'manifest_paths' is a list of paths to the manifests being resolved.

        'api_inst' is an ImageInterface which references the current image.

        'system_patterns' is a list of patterns which determines the system
        packages that are resolved against.

        'prune_attrs' is a boolean indicating whether debugging
        attributes should be stripped from returned actions."""

        # The variable 'manifests' is a list of 5-tuples. The first element
        # of the tuple is the path to the manifest. The second is the name of
        # the package contained in the manifest. The third is the manifest
        # object for the manifest in that location. The fourth is the list of
        # variants the package was published against. The fifth is the list of
        # files referenced in the manifest that couldn't be found.
        manifests = [
            (mp, choose_name(mp, mfst), mfst, mfst.get_all_variants(),
            manifest_errs)
            for mp, (mfst, manifest_errs) in
            ((mp, __make_manifest(mp, load_data=False))
            for mp in manifest_paths)
        ]

        files = Entries({}, {})
        links = {}

        # This records all the variants used in any package known.  It is used
        # to ensure that all packages live in the same variant universe for
        # purposes of dependency resolution.
        distro_vars = variants.VariantCombinationTemplate()

        resolving_pkgs = set()

        for mp, (name, pfmri), mfst, pkg_vars, miss_files in manifests:
                distro_vars.merge_values(pkg_vars)
                if pfmri:
                        resolving_pkgs.add(pfmri.pkg_name)

        def __merge_actvct_with_pkgvct(act_vct, pkg_vct):
                act_vct.merge_unknown(pkg_vct)
                return variants.VariantCombinations(act_vct, satisfied=True)

        sys_fmris = set()
        unmatched_patterns = set()
        if system_patterns:
                pkg_list = api_inst.get_pkg_list(
                        api.ImageInterface.LIST_INSTALLED,
                        patterns=system_patterns, raise_unmatched=True)
                tmp_files = {}
                tmp_links = {}
                package_vars = {}
                pkg_cnt = 0
                # Gather information from installed packages
                # Because get_pkg_list returns a generator, the
                # InventoryException raised when a pattern has no matches isn't
                # raised until all the matching patterns have been iterated
                # over.
                try:
                        for (pub, stem, ver), summ, cats, states, attrs in \
                            pkg_list:
                                # If this package is being resolved, then that's
                                # the information to use.
                                if stem in resolving_pkgs:
                                        continue
                                # To get the manifest, we need an fmri with a
                                # publisher because we need to be able to check
                                # if the package is installed.
                                pfmri = fmri.PkgFmri(publisher=pub, name=stem,
                                    version=ver)
                                mfst = api_inst.get_manifest(pfmri,
                                    all_variants=True)
                                # But we don't want fmris with publishers as
                                # targets of dependencies, so remove the
                                # publisher.
                                pfmri.publisher = None
                                sys_fmris.add(pfmri.pkg_name)
                                distro_vars.merge_values(
                                    mfst.get_all_variants())
                                package_vars[stem] = mfst.get_all_variants()
                                add_fmri_path_mapping(tmp_files, tmp_links,
                                    pfmri, mfst, use_template=True)
                                pkg_cnt += 1
                except apx.InventoryException as e:
                        # If "*" didn't match any packages, then the image was
                        # empty.
                        try:
                                e.notfound.remove("*")
                        except ValueError:
                                pass
                        unmatched_patterns.update(e.notfound)
                del pkg_list
                # Move all package variants into the same universe.
                for pkg_vct in package_vars.values():
                        pkg_vct.merge_unknown(distro_vars)
                # Populate the installed files dictionary.
                for pth, l in six.iteritems(tmp_files):
                        new_val = [
                            (p, __merge_actvct_with_pkgvct(tmpl,
                                package_vars[p.pkg_name]))
                            for (p, tmpl) in l
                        ]
                        files.installed[pth] = new_val
                del tmp_files
                # Populate the link dictionary using the installed packages'
                # information.
                for pth, l in six.iteritems(tmp_links):
                        new_val = [
                            (p, __merge_actvct_with_pkgvct(tmpl,
                                package_vars[p.pkg_name]), target)
                            for (p, tmpl, target) in l
                        ]
                        links[pth] = new_val
                del tmp_links
                del package_vars

        res_fmris = set()
        # Build a list of all files delivered in the manifests being resolved.
        for mp, (name, pfmri), mfst, pkg_vars, miss_files in manifests:
                try:
                        if pfmri is None:
                                pfmri = fmri.PkgFmri(name)
                except fmri.IllegalFmri as e:
                        raise BadPackageFmri(mp, e)
                add_fmri_path_mapping(files.delivered, links, pfmri, mfst,
                    distro_vars)
                res_fmris.add(pfmri.pkg_name)

        pkg_deps = {}
        errs = []
        warnings = []
        external_deps = set()
        for mp, (name, pfmri), mfst, pkg_vars, manifest_errs in manifests:
                name_to_use = pfmri or name
                # The add_fmri_path_mapping function moved the actions it found
                # into the distro_vars universe of variants, so we need to move
                # pkg_vars (and by extension the variants on depend actions)
                # into that universe too.
                pkg_vars.merge_unknown(distro_vars)
                errs.extend(manifest_errs)
                if mfst is None:
                        pkg_deps[mp] = None
                        continue
                ds = []
                bad_ds = {}
                for d in mfst.gen_actions_by_type("depend"):
                        if not is_file_dependency(d):
                                continue
                        try:
                                r = split_off_variants(d, pkg_vars)
                                ds.append(r)
                        except __NotSubset as e:
                                diff = bad_ds.setdefault(d.attrs[reason_prefix],
                                    variants.VCTDifference(set(), set()))
                                diff.type_diffs.update(e.diff.type_diffs)
                                diff.value_diffs.update(e.diff.value_diffs)
                if bad_ds:
                        errs.append(ExtraVariantedDependency(name_to_use,
                            bad_ds, False))

                pkg_res = [
                    (d, find_package(files, links, d, d_vars, pkg_vars,
                        bool(system_patterns)))
                    for d, d_vars in ds
                ]

                # Seed the final results with those dependencies defined
                # manually.
                deps = []
                bad_deps = {}
                for d in mfst.gen_actions_by_type("depend"):
                        if is_file_dependency(d):
                                continue
                        try:
                                r = split_off_variants(d, pkg_vars,
                                    satisfied=True)
                                deps.append(r)
                        except __NotSubset as e:
                                diff = bad_deps.setdefault(
                                    d.attrs.get("fmri", None),
                                    variants.VCTDifference(set(), set()))
                                diff.type_diffs.update(e.diff.type_diffs)
                                diff.value_diffs.update(e.diff.value_diffs)
                if bad_deps:
                        errs.append(ExtraVariantedDependency(name_to_use,
                            bad_deps, True))

                for file_dep, (res, dep_vars, pkg_errs) in pkg_res:
                        for e in pkg_errs:
                                if hasattr(e, "pkg_name"):
                                        e.pkg_name = name_to_use
                        errs.extend(pkg_errs)
                        dep_vars.simplify(pkg_vars)
                        if not res:
                                errs.append(UnresolvedDependencyError(mp,
                                    file_dep, dep_vars))
                        else:
                                deps.extend(res)
                                if not dep_vars.is_satisfied():
                                        errs.append(UnresolvedDependencyError(
                                            mp, file_dep, dep_vars))
                # Add variant information to the dependency actions and combine
                # what would otherwise be duplicate dependencies.
                deps, combine_errs, combine_warnings = combine(deps, pkg_vars,
                    pfmri, name_to_use)
                errs.extend(combine_errs)
                warnings.extend(combine_warnings)

                ext_pfmris = [
                    pkg_name
                    for pkg_name in (
                                 __safe_fmri_parse(pfmri)
                                 for a in deps
                                 for pfmri in a.attrlist("fmri")
                                 if a.attrs["type"] in
                                 ("conditional", "require", "require-any")
                             )
                    if pkg_name is not None
                    if pkg_name not in res_fmris
                ]
                external_deps.update(ext_pfmris)
                sys_fmris.difference_update(ext_pfmris)

                if prune_attrs:
                        deps = [prune_debug_attrs(d) for d in deps]
                pkg_deps[mp] = deps

        sys_fmris.update(unmatched_patterns)
        return pkg_deps, errs, warnings, sys_fmris, external_deps
