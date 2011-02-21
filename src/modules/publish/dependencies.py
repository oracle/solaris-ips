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
import os
import re
import urllib

from collections import namedtuple

import pkg.actions as actions
import pkg.client.api as api
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

        def __init__(self, res, source, vc):
                self.res = res
                self.source = source
                self.vc = vc

        def __str__(self):
                return _("The file dependency %(src)s has paths which resolve "
                    "to multiple packages under this combination of "
                    "variants:\n%(vars)s\nThe actions are as "
                    "follows:\n%(acts)s") % {
                        "src":self.source,
                        "acts":"\n".join(["\t%s" % a for a in self.res]),
                        "vars":"\n".join([
                            " ".join([
                                ("%s:%s" % (name, val)) for name, val in grp
                            ])
                            for grp in self.vc.sat_set])
                    }

class AmbiguousPathError(DependencyError):
        """This exception is used when multiple packages deliver a path which
        is depended upon."""

        def __init__(self, pkgs, source):
                self.pkgs = pkgs
                self.source = source

        def __str__(self):
                return _("The file dependency %(src)s depends on a path "
                    "delivered by multiple packages. Those packages "
                    "are:%(pkgs)s") % {
                        "src":self.source,
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
                return _("%(pth)s has unresolved dependency '%(dep)s' under "
                    "the following combinations of variants:\n%(combo)s") % \
                    {
                        "pth":self.path,
                        "dep":self.file_dep,
                        "combo":"\n".join([
                            " ".join([
                                ("%s:%s" % (name, val))
                                for name, val in sorted(grp)
                            ])
                            for grp in self.pvars.not_sat_set
                    ])}

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
        links = Entries({}, {})

        # A fake pkg name is used because there is no requirement that a package
        # name itself to generate its dependencies.  Also, the name is entirely
        # a private construction which should not escape to the user.
        add_fmri_path_mapping(files.delivered, links.delivered,
            fmri.PkgFmri("INTERNAL@0-0", build_release="0"), mfst)
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
        fh = open(fp, "rb")
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
                                path = e.path
                                # If the path was not set, then parse the
                                # action, without trying to load the data and
                                # use the path defined in the action.
                                if not path:
                                        path = new_a.attrs["path"]
                                missing_files.append(base.MissingFile(path))
        fh.close()
        m.set_content(content=acts)
        return m, missing_files

def choose_name(fp, mfst):
        """Find the package name for this manifest. If it's defined in a set
        action in the manifest, use that. Otherwise use the basename of the
        path to the manifest as the name.
        'fp' is the path to the file for the manifest.

        'mfst' is the Manifest object."""

        if mfst is None:
                return urllib.unquote(os.path.basename(fp))
        name = mfst.get("pkg.fmri", mfst.get("fmri", None))
        if name is not None:
                return name
        return urllib.unquote(os.path.basename(fp))

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
        for pfmri, delivered_vars in lst:
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
                        res_paths.append((path, pfmri, inter))
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
        # The links in delivered packages (ie, those current being resolved)
        # should be preferred over links from the installed system.
        rel_links = links.delivered.get(cur_path, [])
        tmp = set()
        for pfmri, vc, rel_target in rel_links:
                tmp.add(pfmri.get_name())
        # Only considered links from installed packages which are not also being
        # resolved.
        for pfmri, vc, rel_target in links.installed.get(cur_path, []):
                if pfmri.get_name() in tmp:
                        continue
                rel_links.append((pfmri, vc, rel_target))
        # If there weren't any relevant links, then add the next path component
        # to the path being considered and try again.
        if not rel_links:
                return resolve_links(path, files_dict, links, path_vars,
                    file_dep_attrs, index=index+1)

        for link_pfmri, link_vc, rel_target in rel_links:
                # If the variants needed to reach the current path and the
                # variants for the link don't intersect, then the link
                # is irrelevant.
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
                res_paths.extend(rec_paths)
                # Now add in the dependencies for the current link.
                for rec_path, rec_pfmri, rec_vc in rec_paths:
                        attrs = file_dep_attrs.copy()
                        attrs.update({
                            "fmri": link_pfmri.get_short_fmri(),
                            type_prefix: "link",
                            target_prefix: next_path,
                            files_prefix: path
                        })
                        attrs.pop(paths_prefix, None)
                        attrs.pop(fullpaths_prefix, None)

                        assert vc_intersection.intersects(rec_vc), \
                            "vc:%s\nvc_intersection:%s" % \
                            (rec_vc, vc_intersection)
                        # The dependency is created with the same variants as
                        # the path.  This works because the set of relevant
                        # variants is restricted as links are applied so the
                        # variants used for the path are the intersection of
                        # the variants for each of the links used to reach the
                        # path and the variants under which the file is
                        # delivered.
                        res_links.append((
                            actions.depend.DependencyAction(**attrs), rec_vc))
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
                delivered_list = \
                    [(pfmri, vc) for (path, pfmri, vc) in paths_info]
                try:
                        new_res, dep_vars = helper(delivered_list, file_dep,
                            dep_vars, orig_dep_vars)
                except AmbiguousPathError, e:
                        errs.append(e)
                else:
                        # We know which path satisfies this dependency, so
                        # remove the list of files and paths, and replace them
                        # with the single path that works.
                        for na, nv in new_res:
                                na.attrs.pop(paths_prefix, None)
                                na.attrs.pop(fullpaths_prefix, None)
                                na.attrs[files_prefix] = [p]

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

def find_package(files, links, file_dep, pkg_vars, use_system):
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

        'pkg_vars' is the variants against which the package was published."""

        file_dep, orig_dep_vars = split_off_variants(file_dep, pkg_vars)
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

def combine(deps, pkg_vars):
        """Combine duplicate dependency actions.

        'deps' is a list of tuples. Each tuple contains a dependency action and
        the variants associated with that dependency.

        'pkg_vars' are the variants that the package for which dependencies are
        being generated was published against."""

        def action_group_key(d):
                """Return a key on which the tuples can be sorted and grouped
                so that the groups match the duplicate actions that the code
                in pkg.manifest notices."""

                # d[0] is the action.  d[1] is the VariantCombination for this
                # action.
                return d[0].name, d[0].attrs.get(d[0].key_attr, id(d[0]))

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

        def key_on_variants(a):
                """Return the key (the VariantSets) to sort the grouped tuples
                by."""

                return a[1]

        def sort_by_variant_subsets(a, b):
                """Sort the tuples so that those actions whose variants are
                supersets of others are placed at the front of the list.  This
                function assumes that a and b are both VariantSets."""

                if a.issubset(b, satisfied=True):
                        return 1
                elif b.issubset(a, satisfied=True):
                        return -1
                return 0

        # Here is an example of how this code should work.  Assume that the code
        # is looking at dependencies for a package published against
        # variant.foo = bar, baz and variant.num = one, two.  These are
        # abbreviated below as v.f and v.n.  The following dependencies have
        # been found for this package:
        # 1) depend pkg_a reason=file_1, VariantSet is v.f=bar,baz v.n=one,two
        # 2) depend pkg_a reason=file_2, VariantSet is v.f=bar v.n=one
        # 3) depend pkg_b reason=file_3, VariantSet is v.f=bar v.n=one
        # 4) depend pkg_b reason=file_3, VariantSet is v.f=baz v.n=two
        # 5) depend pkg_b reason=file_3 path=p1, VariantSet is v.f=bar
        #        v.n=one,two
        #
        # First, these dependencies are grouped by their fmris.  This produces
        # two lists, the first contains dependencies 1 and 2, the second
        # contains dependencies 3, 4, and 5.
        #
        # The first group of dependencies is sorted by their VariantSet's.
        # Dependency 1 comes before dependency 2 because 2's variants are a
        # subset of 1's variants.  Dependency 1 is put in the temporary result
        # list (subres) since at least one dependency on pkg_a must exist.
        # Next, dependency 2 is compared to dependency 1 to see if it its
        # variants are subset of 1's. Since they are, the two dependencies are
        # merged.  This means that values of all tags in either dependency
        # appear in the merged dependency.  In this case, the merged dependency
        # would look something like:
        # depend pkg_a reason=file_1 reason=file_2
        # The variant set associated with the merged dependency would still be
        # dependency 1's variant set.
        #
        # The last thing that happens with this group of dependencies is that
        # add_vars is called on each result.  This first removes those variants
        # which match the package's identically.  What remains is added to the
        # dependency's attribute dictionary.  Since the package variants and the
        # dependency's variants are identical in this case, nothing is added.
        # Lastly, any duplicate values for a tag are removed.  Again, since
        # there are no duplicates, nothing is changed.  The final dependency
        # that's added to final_res is:
        # depend pkg_a reason=file_1 reason=file_2
        #
        # The second group of dependencies is also sorted by their VariantSet's.
        # This sort is a partial ordering.  Dependency 5 must come before
        # dependency 3, but dependency 4 can be anywhere in the list.  Let's
        # assume that the order is [4, 5, 3].
        #
        # Dependency 4 is added to the temporary result list (subres).
        # Dependency 5 is checked to see if its variants are subset of 4's
        # variants.  Since they are not, dependency 5 is added to subres.
        # Dependency 3 is checked against 4 to see if its variants are a subset.
        # Since they're not, 3's variants are then checked against 5's variants.
        # Since 3's variants are a subset of 5's variants, 3 is merged with 5,
        # producing this dependency:
        # depend pkg_b reason=file_3 reason=file_3 path=p1, VariantSet is
        # v.f=bar v.n=one,two
        #
        # The two results from this group (dependency 4 and the merge of 5 and
        # 3) than has add_vars called on it.  The final results are:
        # dependency pkg_b reason=file_3 v.f=baz v.n=two
        # dependency pkg_b reason=file_3 path=p1 v.f=bar
        #
        # The v.n tags have been removed from the second result because they
        # were identical to the package's variants.  The duplicate reasons have
        # also been coalesced.
        #
        # After everything is done, the final set of dependencies for this
        # package are:
        # depend pkg_a reason=file_1 reason=file_2
        # dependency pkg_b reason=file_3 v.f=baz v.n=two
        # dependency pkg_b reason=file_3 path=p1 v.f=bar

        res = []
        # For each group of dependencies (g) for a particular fmri (k) ...
        for k, g in itertools.groupby(sorted(deps, key=action_group_key),
            action_group_key):

                # Sort the dependencies so that any dependency whose variants
                # are a subset of the variants of another dependency follow it.
                glist = sorted(g, cmp=sort_by_variant_subsets,
                    key=key_on_variants)
                subres = [glist[0]]

                # d is a dependency action. d_vars are the variants under which
                # d will be applied.
                for d, d_vars in glist[1:]:
                        found_subset = False
                        for rel_res, rel_vars in subres:

                                # If d_vars is a subset of any variant set
                                # already in the results, then d should be
                                # combined with that dependency.
                                if d_vars.issubset(rel_vars, satisfied=True):
                                        found_subset = True
                                        merge_deps(rel_res, d)
                                        break
                                assert(not rel_vars.issubset(d_vars,
                                    satisfied=True))

                        # If no subset was found, then d_vars is a new set of
                        # conditions under which the dependency d should apply
                        # so add it to the results.
                        if not found_subset:
                                subres.append((d, d_vars))

                # Add the variants to the dependency action and remove any
                # variants that are identical to those defined by the package.
                subres = [add_vars(d, d_vars, pkg_vars) for d, d_vars in subres]
                res.extend(itertools.chain.from_iterable(subres))
        return res

def split_off_variants(dep, pkg_vars):
        """Take a dependency which may be tagged with variants and move those
        tags into a VariantSet."""

        dep_vars = dep.get_variant_template()
        dep_vars.merge_unknown(pkg_vars)
        # Since all variant information is being kept in the above VariantSets,
        # remove the variant information from the action.  This prevents
        # confusion about which is the authoritative source of information.
        dep.strip_variants()
        return dep, variants.VariantCombinations(dep_vars, satisfied=False)

def prune_debug_attrs(action):
        """Given a dependency action with pkg.debug.depend attributes
        return a matching action with those attributes removed"""

        attrs = dict((k, v) for k, v in action.attrs.iteritems()
                     if not k.startswith(base.Dependency.DEPEND_DEBUG_PREFIX))
        return actions.depend.DependencyAction(**attrs)

def add_fmri_path_mapping(files_dict, links_dict, pfmri, mfst):
        """Add mappings from path names to FMRIs and variants.

        'files_dict' is a dictionary which maps package identity to the files
        the package delivers and the variants under which each file is
        present.

        'links_dict' is a dictionary which maps package identity to the links
        the package delivers and the variants under which each link is
        present.

        'pfmri' is the FMRI of the current manifest

        'mfst' is the manifest to process."""

        pvariants = mfst.get_all_variants()

        for f in mfst.gen_actions_by_type("file"):
                dep_vars = f.get_variant_template()
                dep_vars.merge_unknown(pvariants)
                vc = variants.VariantCombinations(dep_vars,
                    satisfied=True)
                files_dict.setdefault(f.attrs["path"], []).append(
                    (pfmri, vc))
        for f in itertools.chain(mfst.gen_actions_by_type("hardlink"),
             mfst.gen_actions_by_type("link")):
                dep_vars = f.get_variant_template()
                dep_vars.merge_unknown(pvariants)
                vc = variants.VariantCombinations(dep_vars,
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
        links = Entries({}, {})

        # Build a list of all files delivered in the manifests being resolved.
        for mp, name, mfst, pkg_vars, miss_files in manifests:
                pfmri = fmri.PkgFmri(name)
                add_fmri_path_mapping(files.delivered, links.delivered, pfmri,
                    mfst)

        # Build a list of all files delivered in the packages installed on
        # the system.
        if use_system:
                for (pub, stem, ver), summ, cats, states in \
                    api_inst.get_pkg_list(api.ImageInterface.LIST_INSTALLED):
                        pfmri = fmri.PkgFmri("pkg:/%s@%s" % (stem, ver))
                        mfst = api_inst.get_manifest(pfmri, all_variants=True)
                        add_fmri_path_mapping(files.installed, links.installed,
                            pfmri, mfst)

        pkg_deps = {}
        errs = []
        for mp, name, mfst, pkg_vars, miss_files in manifests:
                errs.extend(miss_files)
                if mfst is None:
                        pkg_deps[mp] = None
                        continue
                pkg_res = [
                    (d, find_package(files, links, d, pkg_vars,
                        use_system))
                    for d in mfst.gen_actions_by_type("depend")
                    if is_file_dependency(d)
                ]
                # Seed the final results with those dependencies defined
                # manually.
                deps = [
                    split_off_variants(d, pkg_vars)
                    for d in mfst.gen_actions_by_type("depend")
                    if not is_file_dependency(d)
                ]
                for file_dep, (res, dep_vars, pkg_errs) in pkg_res:
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
                deps = combine(deps, pkg_vars)

                if prune_attrs:
                        deps = [prune_debug_attrs(d) for d in deps]
                pkg_deps[mp] = deps

        return pkg_deps, errs
