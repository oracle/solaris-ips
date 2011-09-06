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
# Copyright (c) 2009, 2011, Oracle and/or its affiliates. All rights reserved.
#

import copy
import itertools
import operator
import os
import re
import urllib

from collections import namedtuple

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
import pkg.portable as portable
import pkg.variant as variants

paths_prefix = "%s.path" % base.Dependency.DEPEND_DEBUG_PREFIX
files_prefix = "%s.file" % base.Dependency.DEPEND_DEBUG_PREFIX
reason_prefix = "%s.reason" % base.Dependency.DEPEND_DEBUG_PREFIX
type_prefix = "%s.type" % base.Dependency.DEPEND_DEBUG_PREFIX
target_prefix = "%s.target" % base.Dependency.DEPEND_DEBUG_PREFIX
bypassed_prefix = "%s.bypassed" % base.Dependency.DEPEND_DEBUG_PREFIX
via_links_prefix = "%s.via-links" % base.Dependency.DEPEND_DEBUG_PREFIX

# A tag used to hold the product of the paths_prefix and files_prefix
# contents, used when bypassing dependency generation
fullpaths_prefix = "%s.fullpath" % base.Dependency.DEPEND_DEBUG_PREFIX

Entries = namedtuple("Entries", ["delivered", "installed"])
# This namedtuple is used to hold two items. The first, delivered, is used to
# hold items which are part of packages being delivered.  The second, installed,
# is used to hold items which are part of packages installed on the system.

class DependencyError(Exception):
        """The parent class for all dependency exceptions."""
        pass

class MultiplePackagesPathError(DependencyError):
        """This exception is used when a file dependency has paths which cause
        two or more packages to deliver files which fulfill the dependency under
        some combination of variants."""

        def __set_pkg_name(self, name):
                self.__pkg_name = str(name)

        pkg_name = property(lambda self: self.__pkg_name, __set_pkg_name)

        def __init__(self, res, source, vc, pkg_name=None):
                self.res = res
                self.source = source
                self.vc = vc
                self.pkg_name = pkg_name

        def __str__(self):
                if self.vc.sat_set and self.pkg_name:
                        return _("The file dependency %(src)s delivered in "
                            "package %(pkg)s has paths which resolve to "
                            "multiple packages under this combination of "
                            "variants:\n%(vars)s\nThe actions "
                            "are:\n%(acts)s") % {
                                "src":self.source,
                                "acts":"\n".join(
                                    ["\t%s" % a for a in self.res]),
                                "vars":"\n".join([
                                    " ".join([
                                        ("%s:%s" % (name, val))
                                        for name, val in grp
                                    ])
                                    for grp in self.vc.sat_set]),
                                "pkg": self.pkg_name
                            }
                elif self.vc.sat_set:
                        return _("The file dependency %(src)s has paths which"
                            "resolve to multiple packages under this "
                            "combination of variants:\n%(vars)s\nThe actions "
                            "are:\n%(acts)s") % {
                                "src":self.source,
                                "acts":"\n".join(
                                    ["\t%s" % a for a in self.res]),
                                "vars":"\n".join([
                                    " ".join([
                                        ("%s:%s" % (name, val))
                                        for name, val in grp
                                    ])
                                    for grp in self.vc.sat_set])
                            }
                elif self.pkg_name:
                        return _("The file dependency %(src)s delivered in "
                            "%(pkg)s has paths which resolve to multiple "
                            "packages.\nThe actions are:\n%(acts)s") % {
                                "src":self.source,
                                "acts":"\n".join(
                                ["\t%s" % a for a in self.res]),
                                "pkg":self.pkg_name
                            }
                else:
                        return _("The file dependency %(src)s has paths which "
                            "resolve to multiple packages.\nThe actions "
                            "are:\n%(acts)s") % {
                                "src":self.source,
                                "acts":"\n".join(
                                ["\t%s" % a for a in self.res])
                            }

class AmbiguousPathError(DependencyError):
        """This exception is used when multiple packages deliver a path which
        is depended upon."""

        def __init__(self, pkgs, source):
                self.pkgs = pkgs
                self.source = source

        def __str__(self):
                s_str = "\n" + self.source.pretty_print() + "\n"
                return _("The file dependency %(src)s depends on a path "
                    "delivered by multiple packages. Those packages "
                    "are:%(pkgs)s") % {
                        "src":s_str,
                        "pkgs":" ".join([str(p) for p in self.pkgs])
                    }

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
                        return _("%(pth)s has unresolved dependency '%(dep)s' "
                            "under the following combinations of "
                            "variants:\n%(combo)s") % \
                            {
                                "pth":self.path,
                                "dep":dep_str + "\n",
                                "combo":"\n".join([
                                    " ".join([
                                        ("%s:%s" % (name, val))
                                        for name, val in sorted(grp)
                                    ])
                                    for grp in self.pvars.not_sat_set
                            ])}
                else:
                        return _("%(pth)s has unresolved dependency "
                            "'%(dep)s'.") % \
                            { "pth":self.path, "dep":dep_str }


class MissingPackageVariantError(DependencyError):
        """This exception is used when an action is tagged with a variant or
        variant value which the package is not tagged with."""

        def __init__(self, act_vars, pkg_vars, pth):
                self.act_vars = act_vars
                self.pkg_vars = pkg_vars
                self.path = pth

        def __str__(self):
                return _("The action delivering %(path)s is tagged with a "
                    "variant type or value not tagged on the package. "
                    "Dependencies on this file may fail to be reported.\n"
                    "The action's variants are: %(act)s\nThe package's "
                    "variants are: %(pkg)s") % {
                        "path": self.path,
                        "act": self.act_vars,
                        "pkg": self.pkg_vars
                    }


class BadDependencyFmri(DependencyError):
        """This exception is used when dependency actions have text in their
        fmri attributes which are not valid fmris."""

        def __init__(self, pkg, fmris):
                self.pkg = pkg
                self.fmris = fmris

        def __str__(self):
                return _("The package %(pkg)s contains depend actions with "
                    "values in their fmri attributes which are not valid "
                    "fmris.  The bad values are:\n%(fmris)s\n") % {
                    "pkg": self.pkg,
                    "fmris": "\n".join(["\t%s" % f for f in sorted(self.fmris)])
                }


class BadPackageFmri(DependencyError):
        """This exception is used when a manifest's fmri isn't a valid fmri."""

        def __init__(self, path, e):
                self.path = path
                self.exc = e

        def __str__(self):
                return _("The manifest '%(path)s' has an invalid package "
                    "FMRI:\n\t%(exc)s") % { "path": self.path, "exc": self.exc }


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
                for r, diff in sorted(self.rvs.iteritems()):
                        for kind in diff.type_diffs:
                                s += _("\t%(r)-15s Variant '%(kind)s' is not "
                                    "declared.\n") % \
                                    {"r":r, "kind":kind}
                        for k, v in diff.value_diffs:
                                s += _("\t%(r)-15s Variant '%(kind)s' is not "
                                    "declared to have value '%(val)s'.\n") % \
                                    {"r":r, "val":v, "kind":k}
                if not self.manual:
                        return _("The package '%(pkg)s' contains actions with "
                            "the\npaths seen below which have variants set on "
                            "them which are not set on the\npackage.  These "
                            "variants must be set on the package or removed "
                            "from the actions.\n\n%(rvs)s") % {
                            "pkg": self.pkg,
                            "rvs": s
                        }
                else:
                        return _("The package '%(pkg)s' contains manually "
                            "specified dependencies\nwhich have variants set "
                            "on them which are not set on the package.  "
                            "These\nvariants must be set on the package or "
                            "removed from the actions.\n\n%(rvs)s") % {
                            "pkg": self.pkg,
                            "rvs": s
                        }


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

        m, missing_manf_files = __make_manifest(file_path, proto_dirs)
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

        return deps, missing_manf_files + elist + rid_errs, missing, pkg_attrs

def convert_to_standard_dep_actions(deps):
        """Convert pkg.base.Dependency objects to
        pkg.actions.dependency.Dependency objects."""

        res = []
        for d in deps:
                tmp = []
                for c in d.dep_vars.not_sat_set:
                        attrs = d.attrs.copy()
                        attrs.update(c)
                        tmp.append(actions.depend.DependencyAction(**attrs))
                if not tmp:
                        tmp.append(actions.depend.DependencyAction(**d.attrs))
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
                        pkg_attrs[bypassed_prefix] = "%s:.*" % a.attrs["path"]
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
                        except base.DependencyAnalysisError, e:
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
                    _("Manifest specified multiple values for %s rather "
                    "than a single colon-separated string.") %
                    portable.PD_RUN_PATH)]
        if set(run_path_str.split(":")) == set([""]):
                return [base.DependencyAnalysisError(
                    _("Manifest did not specify any entries for %s, expecting "
                    "a colon-separated string.") % portable.PD_RUN_PATH)]
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
                                        item = ".*%s%s" % (os.path.sep, item)

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
                except re.error, e:
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
                fh = open(fp, "rb")
        except EnvironmentError, e:
                raise apx._convert_error(e)
        acts = []
        missing_files = []
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
                        if local_path:
                                assert portable.PD_LOCAL_PATH not in a.attrs
                                a.attrs[portable.PD_LOCAL_PATH] = local_path
                                a.attrs[portable.PD_PROTO_DIR] = used_bd
                                a.attrs[portable.PD_PROTO_DIR_LIST] = basedirs
                        acts.append(a)
                except actions.ActionDataError, e:
                        new_a, local_path, used_bd = actions.internalizestr(
                            l, basedirs=basedirs, load_data=False)
                        if new_a.name == "license":
                                acts.append(new_a)
                        else:
                                missing_files.append(base.MissingFile(
                                    new_a.attrs["path"], basedirs))
        fh.close()
        m.set_content(content=acts)
        return m, missing_files

def choose_name(fp, mfst):
        """Find the package name for this manifest.  If it's defined in a set
        action in the manifest, use that.  Otherwise use the basename of the
        path to the manifest as the name.  If a proper package fmri is found,
        then also return a PkgFmri object so that we can track which packages
        are being processed.

        'fp' is the path to the file for the manifest.

        'mfst' is the Manifest object."""

        if mfst is None:
                return urllib.unquote(os.path.basename(fp)), None
        name = mfst.get("pkg.fmri", mfst.get("fmri", None))
        if name is not None:
                try:
                        pfmri = fmri.PkgFmri(name, "5.11")
                except fmri.IllegalFmri:
                        pfmri = None
                return name, pfmri
        return urllib.unquote(os.path.basename(fp)), None

def helper(lst, file_dep, dep_vars, orig_dep_vars):
        """Creates the depend actions from lst for the dependency and determines
        which variants have been accounted for.

        'lst' is a list of fmri, variants pairs. The fmri a package which can
        satisfy the dependency. The variants are the variants under which it
        satisfies the dependency.

        'file_dep' is the dependency that needs to be satisfied.

        'dep_vars' is the variants under which 'file_dep' has not yet been
        satisfied.

        'orig_dep_vars' is the original set of variants under which the
        dependency must be satisfied."""

        res = []
        vars = []
        errs = set()
        for path, pfmri, delivered_vars, via_links in lst:
                # If the pfmri package isn't present under any of the variants
                # where the dependency is, skip it.
                if not orig_dep_vars.intersects(delivered_vars,
                    only_not_sat=True):
                        continue
                vc = orig_dep_vars.intersection(delivered_vars)
                vc.mark_all_as_satisfied()
                for found_vars, found_fmri in vars:
                        # Because we don't have the concept of one-of
                        # dependencies, depending on a file which is delivered
                        # in multiple packages under a set of variants
                        # prevents automatic resolution of dependencies.
                        if found_fmri != pfmri and \
                            found_vars.intersects(delivered_vars):
                                errs.add(found_fmri)
                                errs.add(pfmri)
                # Find the variants under which pfmri is relevant.
                action_vars = vc
                # Mark the variants as satisfied so it's possible to know if
                # all variant combinations have been covered.
                dep_vars.mark_as_satisfied(delivered_vars)
                attrs = file_dep.attrs.copy()
                attrs.update({"fmri":pfmri.get_short_fmri()})
                # We know which path satisfies this dependency, so remove the
                # list of files and paths, and replace them with the single path
                # that works.
                attrs.pop(paths_prefix, None)
                attrs.pop(fullpaths_prefix, None)
                attrs[files_prefix] = [path]
                if via_links:
                        via_links.reverse()
                        attrs[via_links_prefix] = ":".join(via_links)
                # Add this package as satisfying the dependency.
                res.append((actions.depend.DependencyAction(**attrs),
                    action_vars))
                vars.append((action_vars, pfmri))
        if errs:
                # If any packages are in errs, then more than one file delivered
                # the same path under some configuration of variants. This
                # situation is unresolvable.
                raise AmbiguousPathError(errs, file_dep)
        return res, dep_vars

def make_paths(file_dep):
        """Find all the possible paths which could satisfy the dependency
        'file_dep'."""

        if file_dep.attrs.get(fullpaths_prefix, []):
                return file_dep.attrs[fullpaths_prefix]

        rps = file_dep.attrs.get(paths_prefix, [""])
        files = file_dep.attrs[files_prefix]
        if isinstance(files, basestring):
                files = [files]
        if isinstance(rps, basestring):
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
                        res_paths.append((path, pfmri, inter, []))
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
                for rec_path, rec_pfmri, rec_vc, via_links in rec_paths:
                        via_links.append(path)
                        assert vc_intersection.intersects(rec_vc), \
                            "vc:%s\nvc_intersection:%s" % \
                            (rec_vc, vc_intersection)
                        links_found.setdefault(next_path, []).append(
                            (link_pfmri, rec_vc))
                res_paths.extend(rec_paths)
        # Now add in the dependencies for the current link.
        for next_path in links_found.keys():

                # Create a bin for each possible variant combination.
                vcs = [(vc, []) for vc in path_vars.split_combinations()]

                # For each pfmri which delivers this link, if it intersects with
                # a variant combination, add it to that combination's bin.
                for pfmri, pvc in links_found[next_path]:
                        for vc, l in vcs:
                                if pvc.intersects(vc):
                                        l.append(pfmri)

                # Group the variant combinations by their bin of fmris.
                sort_key = operator.itemgetter(1)
                for pfmris, group in itertools.groupby(
                    sorted(vcs, key=sort_key),
                    key=sort_key):

                        # If pfmris is empty, then no packages delivered the
                        # link under this combination of variants, so skip it.
                        if not pfmris:
                                continue

                        # Make a copy of path_vars which is unsatisfied, then
                        # mark the specific combinations which are satisfied by
                        # this group of pfmris.
                        dep_vc = path_vars.unsatisfied_copy()
                        for vc, pfmris in group:
                                dep_vc.mark_as_satisfied(vc)

                        dep_type = "require-any"
                        names = [p.get_short_fmri() for p in pfmris]
                        # If there's only one fmri delivering this link, then
                        # it's a require dependency, not a require-any.
                        if len(pfmris) == 1:
                                dep_type = "require"
                                names = names[0]

                        attrs = file_dep_attrs.copy()
                        attrs.update({
                            "fmri": names,
                            type_prefix: "link",
                            target_prefix: next_path,
                            files_prefix: [path],
                            "type": dep_type
                        })
                        attrs.pop(paths_prefix, None)
                        attrs.pop(fullpaths_prefix, None)

                        # The dependency is created with the same variants as
                        # the path.  This works because the set of relevant
                        # variants is restricted as links are applied so the
                        # variants used for the path are the intersection of the
                        # variants for each of the links used to reach the path
                        # and the variants under which the file is delivered.
                        res_links.append((
                            actions.depend.DependencyAction(**attrs), dep_vc))

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
        multiple_path_errs = []
        multiple_path_pkgs = set()
        for p in make_paths(file_dep):
                # If orig_dep_vars is satisfied, then this function should never
                # have been called.
                assert(orig_dep_vars.is_empty() or
                    not orig_dep_vars.is_satisfied())
                paths_info, path_deps = resolve_links(os.path.normpath(p),
                    files_dict, links, orig_dep_vars, file_dep.attrs.copy())
                link_deps.extend(path_deps)
                try:
                        new_res, dep_vars = helper(paths_info, file_dep,
                            dep_vars, orig_dep_vars)
                except AmbiguousPathError, e:
                        errs.append(e)
                else:
                        if not res:
                                res = new_res
                                continue
                        # If there are previous results, then it's necessary to
                        # check the new results against the previous results
                        # to see if different paths for the same dependency are
                        # satisfied by different packages.
                        for a, v in res:
                                for new_a, new_v in new_res:
                                        if a.attrs["fmri"] == \
                                            new_a.attrs["fmri"]:
                                                a.attrs[files_prefix].extend(
                                                    new_a.attrs[files_prefix])
                                                continue
                                        # Check to see if there's a
                                        # configuration of variants under which
                                        # both packages can deliver a path which
                                        # satisfies the dependencies.
                                        if v.intersects(new_v):
                                                multiple_path_errs.append((a,
                                                    new_a,
                                                    v.intersection(new_v)))
                                                multiple_path_pkgs.add(a)
                                                multiple_path_pkgs.add(new_a)
                                        elif new_v.intersects(v):
                                                multiple_path_errs.append((a,
                                                    new_a,
                                                    new_v.intersection(v)))
                                                multiple_path_pkgs.add(a)
                                                multiple_path_pkgs.add(new_a)
                                        else:
                                                res.append((new_a, new_v))

        for a1, a2, vc in multiple_path_errs:
                errs.append(MultiplePackagesPathError([a1, a2],
                    file_dep, vc))

        # Extract the actions from res, and only return those which don't have
        # multiple path errors.
        return [(a, v) for a, v in res if a not in multiple_path_pkgs] + \
            link_deps, dep_vars, errs

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
                        if isinstance(v, basestring):
                                v = [v]
                        if isinstance(dest.attrs[k], list):
                                dest.attrs[k].extend(v)
                        else:
                                t = [dest.attrs[k]]
                                t.extend(v)
                                dest.attrs[k] = t

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

        res = []
        req_fmris = []
        bad_fmris = set()
        errs = []

        # For each group of dependencies (g) for a particular fmri (k) ...
        for k, group in itertools.groupby(sorted(deps, key=action_group_key),
            action_group_key):
                group = list(group)
                res_dep = group[0][0]
                res_vars = variants.VariantCombinations(pkg_vars, False)
                for cur_dep, cur_vars in group:
                        merge_deps(res_dep, cur_dep)
                        res_vars.mark_as_satisfied(cur_vars)
                res.append((res_dep, res_vars))
        new_res = []
        for cur_dep, cur_vars in res:
                if cur_dep.attrs["type"] not in ("require", "require-any"):
                        new_res.append((cur_dep, cur_vars))
                        continue
                cur_fmris = []
                for f in cur_dep.attrlist("fmri"):
                        try:
                                # XXX version requires build string; 5.11 is not
                                # sane.
                                cur_fmris.append(fmri.PkgFmri(f, "5.11"))
                        except fmri.IllegalFmri:
                                bad_fmris.add(f)
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
                        new_res.append((cur_dep, cur_vars))
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
                for comp_dep, comp_vars in res:
                        if comp_dep.attrs["type"] != "require":
                                continue
                        comp_fmri = fmri.PkgFmri(comp_dep.attrs["fmri"], "5.11")
                        successor = False
                        # Check to see whether the package required by the
                        # require dependency is a successor to any of the
                        # packages required by the require-any dependency.
                        for c in cur_fmris:
                                if c.is_successor(comp_fmri):
                                        successor = True
                                        break
                        if not successor:
                                continue
                        # If comp_vars is empty, then no variants have been
                        # declared for these packages, so having a matching
                        # require dependency is enough to omit this require-any
                        # dependency.
                        if cur_vars.mark_as_unsatisfied(comp_vars) or \
                            comp_vars.is_empty():
                                marked = True
                # If the require-any dependency was never changed, then include
                # it.  If it was changed, check whether there are situations
                # where the require-any dependency is needed.
                if not marked or cur_vars.sat_set:
                        new_res.append((cur_dep, cur_vars))
        res = []
        # Merge the variant information into the depend action.
        for d, vc in new_res:
                res.extend(add_vars(d, vc, pkg_vars))

        if bad_fmris:
                errs.append(BadDependencyFmri(pkg_name, bad_fmris))
        return res, errs

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

        attrs = dict((k, v) for k, v in action.attrs.iteritems()
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

def resolve_deps(manifest_paths, api_inst, prune_attrs=False, use_system=True):
        """For each manifest given, resolve the file dependencies to package
        dependencies. It returns a mapping from manifest_path to a list of
        dependencies and a list of unresolved dependencies.

        'manifest_paths' is a list of paths to the manifests being resolved.

        'api_inst' is an ImageInterface which references the current image.

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
            missing_files)
            for mp, (mfst, missing_files) in
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

        if use_system:
                pkg_list = api_inst.get_pkg_list(
                    api.ImageInterface.LIST_INSTALLED)
                tmp_files = {}
                tmp_links = {}
                package_vars = {}
                pkg_cnt = 0
                # Gather information from installed packages
                for (pub, stem, ver), summ, cats, states, attrs in pkg_list:
                        # If this package is being resolved, then that's the
                        # information to use.
                        if stem in resolving_pkgs:
                                continue
                        pfmri = fmri.PkgFmri("pkg:/%s@%s" % (stem, ver))
                        mfst = api_inst.get_manifest(pfmri, all_variants=True)
                        distro_vars.merge_values(mfst.get_all_variants())
                        package_vars[stem] = mfst.get_all_variants()
                        add_fmri_path_mapping(tmp_files, tmp_links, pfmri, mfst,
                            use_template=True)
                        pkg_cnt += 1
                del pkg_list
                # Move all package variants into the same universe.
                for pkg_vct in package_vars.values():
                        pkg_vct.merge_unknown(distro_vars)
                # Populate the installed files dictionary.
                for pth, l in tmp_files.iteritems():
                        new_val = [
                            (p, __merge_actvct_with_pkgvct(tmpl,
                                package_vars[p.pkg_name]))
                            for (p, tmpl) in l
                        ]
                        files.installed[pth] = new_val
                del tmp_files
                # Populate the link dictionary using the installed packages'
                # information.
                for pth, l in tmp_links.iteritems():
                        new_val = [
                            (p, __merge_actvct_with_pkgvct(tmpl,
                                package_vars[p.pkg_name]), target)
                            for (p, tmpl, target) in l
                        ]
                        links[pth] = new_val
                del tmp_links
                del package_vars
                                   
        # Build a list of all files delivered in the manifests being resolved.
        for mp, (name, pfmri), mfst, pkg_vars, miss_files in manifests:
                try:
                        if pfmri is None:
                                pfmri = fmri.PkgFmri(name, "5.11")
                except fmri.IllegalFmri, e:
                        raise BadPackageFmri(mp, e)
                add_fmri_path_mapping(files.delivered, links, pfmri, mfst,
                    distro_vars)

        pkg_deps = {}
        errs = []
        for mp, (name, pfmri), mfst, pkg_vars, miss_files in manifests:
                name_to_use = pfmri or name
                # The add_fmri_path_mapping function moved the actions it found
                # into the distro_vars universe of variants, so we need to move
                # pkg_vars (and by extension the variants on depend actions)
                # into that universe too.
                pkg_vars.merge_unknown(distro_vars)
                errs.extend(miss_files)
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
                        except __NotSubset, e:
                                diff = bad_ds.setdefault(d.attrs[reason_prefix],
                                    variants.VCTDifference(set(), set()))
                                diff.type_diffs.update(e.diff.type_diffs)
                                diff.value_diffs.update(e.diff.value_diffs)
                if bad_ds:
                        errs.append(ExtraVariantedDependency(name_to_use,
                            bad_ds, False))

                pkg_res = [
                    (d, find_package(files, links, d, d_vars, pkg_vars,
                        use_system))
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
                        except __NotSubset, e:
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
                deps, combine_errs = combine(deps, pkg_vars, pfmri, name_to_use)
                errs.extend(combine_errs)

                if prune_attrs:
                        deps = [prune_debug_attrs(d) for d in deps]
                pkg_deps[mp] = deps

        return pkg_deps, errs
