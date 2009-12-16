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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import itertools
import os
import urllib

import pkg.actions as actions
import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.flavor.base as base
import pkg.flavor.elf as elf_dep
import pkg.flavor.hardlink as hardlink
import pkg.flavor.script as script
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.portable as portable
import pkg.variant as variants

paths_prefix = "%s.path" % base.Dependency.DEPEND_DEBUG_PREFIX
files_prefix = "%s.file" % base.Dependency.DEPEND_DEBUG_PREFIX

class DependencyError(Exception):
        """The parent class for all dependency exceptions."""
        pass

class MultiplePackagesPathError(DependencyError):
        """This exception is used when a file dependency has paths which
        cause two packages to deliver files which fulfill the dependency."""

        def __init__(self, res, source):
                self.res = res
                self.source = source

        def __str__(self):
                return _("The file dependency %s has paths which resolve "
                    "to multiple packages. The actions are as follows:\n%s" %
                    (self.source, "\n".join(["\t%s" % a for a in self.res])))

class AmbiguousPathError(DependencyError):
        """This exception is used when multiple packages deliver a path which
        is depended upon."""

        def __init__(self, pkgs, source):
                self.pkgs = pkgs
                self.source = source

        def __str__(self):
                return _("The file dependency %s depends on a path delivered "
                    "by multiple packages. Those packages are:%s" %
                    (self.source, " ".join([str(p) for p in self.pkgs])))

class UnresolvedDependencyError(DependencyError):
        """This exception is used when no package delivers a file which is
        depended upon."""
        
        def __init__(self, pth, file_dep, pvars):
                self.path = pth
                self.file_dep = file_dep
                self.pvars = pvars

        def __str__(self):
                return _("%s has unresolved dependency '%s' under the "
                    "following combinations of variants:\n%s") % \
                    (self.path, self.file_dep,
                    "\n".join([
                        " ".join([("%s:%s" % (name, val)) for name, val in grp])
                        for grp in self.pvars.get_unsatisfied()
                    ]))
                
def list_implicit_deps(file_path, proto_dir, dyn_tok_conv, kernel_paths,
    remove_internal_deps=True):
        """Given the manifest provided in file_path, use the known dependency
        generators to produce a list of dependencies the files delivered by
        the manifest have.

        'file_path' is the path to the manifest for the package.

        'proto_dir' is the path to the proto area which holds the files that
        will be delivered by the package.

        'dyn_tok_conv' is the dictionary which maps the dynamic tokens, like
        $PLATFORM, to the values they should be expanded to.

        'kernel_paths' contains the run paths which kernel modules should use.
        """

        proto_dir = os.path.abspath(proto_dir)
        m, missing_manf_files = __make_manifest(file_path, [proto_dir])
        pkg_vars = m.get_all_variants()
        deps, elist, missing = list_implicit_deps_for_manifest(m, proto_dir,
            pkg_vars, dyn_tok_conv, kernel_paths)
        if remove_internal_deps:
                deps = resolve_internal_deps(deps, m, proto_dir, pkg_vars)
        return deps, missing_manf_files + elist, missing

def resolve_internal_deps(deps, mfst, proto_dir, pkg_vars):
        """Given a list of dependencies, remove those which are satisfied by
        others delivered by the same package.

        'deps' is a list of Dependency objects.

        'mfst' is the Manifest of the package that delivered the dependencies
        found in deps.

        'proto_dir' is the path to the proto area which holds the files that
        will be delivered by the package.

        'pkg_vars' are the variants that this package was published against."""

        res = []
        delivered = {}
        delivered_bn = {}
        for a in mfst.gen_actions_by_type("file"):
                pvars = variants.VariantSets(a.get_variants())
                if not pvars:
                        pvars = pkg_vars
                p = a.attrs["path"]
                delivered.setdefault(p, variants.VariantSets()).merge(pvars)
                p = os.path.join(proto_dir, p)
                np = os.path.normpath(p)
                rp = os.path.realpath(p)
                # adding the normalized path
                delivered.setdefault(np, variants.VariantSets()).merge(pvars)
                # adding the real path
                delivered.setdefault(rp, variants.VariantSets()).merge(pvars)
                bn = os.path.basename(p)
                delivered_bn.setdefault(bn, variants.VariantSets()).merge(pvars)
                
        for d in deps:
                etype, pvars = d.resolve_internal(delivered_files=delivered,
                    delivered_base_names=delivered_bn)
                if etype is None:
                        continue
                d.dep_vars = pvars
                res.append(d)
        return res

def no_such_file(action, **kwargs):
        """Function to handle dispatch of files not found on the system."""

        return [], [base.MissingFile(action.attrs["path"])]

# Dictionary which maps codes from portable.get_file_type to the functions which
# find dependencies for those types of files.
dispatch_dict = {
    portable.ELF: elf_dep.process_elf_dependencies,
    portable.EXEC: script.process_script_deps,
    portable.UNFOUND: no_such_file
}

def list_implicit_deps_for_manifest(mfst, proto_dir, pkg_vars, dyn_tok_conv,
    kernel_paths):
        """For a manifest, produce the list of dependencies generated by the
        files it installs.

        'mfst' is the Manifest of the package that delivered the dependencies
        found in deps.

        'proto_dir' is the path to the proto area which holds the files that
        will be delivered by the package.

        'pkg_vars' are the variants that this package was published against.

        'dyn_tok_conv' is the dictionary which maps the dynamic tokens, like
        $PLATFORM, to the values they should be expanded to.

        'kernel_paths' contains the run paths which kernel modules should use.

        Returns a tuple of three lists.

        'deps' is a list of dependencies found for the given Manifest.

        'elist' is a list of errors encountered while finding dependencies.

        'missing' is a dictionary mapping a file type that isn't recognized by
        portable.get_file_type to a file which produced that filetype."""

        deps = []
        elist = []
        missing = {}
        act_list = list(mfst.gen_actions_by_type("file"))
        file_types = portable.get_file_type(act_list, proto_dir)

        for i, file_type in enumerate(file_types):
                a = act_list[i]
                try:
                        func = dispatch_dict[file_type]
                except KeyError:
                        if file_type not in missing:
                                missing[file_type] = os.path.join(proto_dir,
                                    a.attrs["path"])
                else:
                        try:
                                ds, errs = func(action=a, proto_dir=proto_dir,
                                    pkg_vars=pkg_vars,
                                    dyn_tok_conv=dyn_tok_conv,
                                    kernel_paths=kernel_paths)
                                deps.extend(ds)
                                elist.extend(errs)
                        except base.DependencyAnalysisError, e:
                                elist.append(e)
        for a in mfst.gen_actions_by_type("hardlink"):
                deps.extend(hardlink.process_hardlink_deps(a, pkg_vars,
                    proto_dir))
        return deps, elist, missing

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
                        a, local_path = actions.internalizestr(l,
                            basedirs=basedirs,
                            load_data=load_data)
                        if local_path:
                                assert portable.PD_LOCAL_PATH not in a.attrs
                                a.attrs[portable.PD_LOCAL_PATH] = local_path
                        acts.append(a)
                except actions.ActionDataError, e:
                        new_a, local_path = actions.internalizestr(
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
        m.set_content(acts)
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

def helper(lst, file_dep, dep_vars, orig_dep_vars, pkg_vars):
        """Creates the depend actions from lst for the dependency and determines
        which variants have been accounted for.

        'lst' is a list of fmri, variants pairs. The fmri a package which can
        satisfy the dependency. The variants are the variants under which it
        satisfies the dependency.

        'file_dep' is the dependency that needs to be satisfied.

        'dep_vars' is the variants under which 'file_dep' has not yet been
        satisfied.

        'orig_dep_vars' is the original set of variants under which the
        dependency must be satisfied.
        
        'pkg_vars' is the list of variants against which the package delivering
        the action was published."""

        res = []
        vars = []
        errs = set()
        for pfmri, delivered_vars in lst:
                # If the pfmri package isn't present under any of the variants
                # where the dependency is, skip it.
                if not orig_dep_vars.intersects(delivered_vars):
                        continue
                for found_vars, found_fmri in vars:
                        # Because we don't have the concept of one-of
                        # dependencies, depending on a file which is delivered
                        # in multiple packages under a set of variants
                        # prevents automatic resolution of dependencies.
                        if found_fmri != pfmri and \
                            (delivered_vars.intersects(found_vars) or
                            found_vars.intersects(delivered_vars)):
                                errs.add(found_fmri)
                                errs.add(pfmri)
                # Find the variants under which pfmri is relevant.
                action_vars = orig_dep_vars.intersection(delivered_vars)
                action_vars.remove_identical(pkg_vars)
                # Mark the variants as satisfied so it's possible to know if
                # all variant combinations have been covered.
                dep_vars.mark_as_satisfied(delivered_vars)
                attrs = file_dep.attrs.copy()
                attrs.update({"fmri":str(pfmri)})
                attrs.update(action_vars)                
                # Add this package as satisfying the dependency.
                res.append((actions.depend.DependencyAction(**attrs),
                    action_vars))
                vars.append((action_vars, pfmri))
        if errs:
                # If any packages are in errs, then more than one file delivered
                # the same path under some configuaration of variants. This
                # situation is unresolvable.
                raise AmbiguousPathError(errs, file_dep)
        return res, dep_vars

def make_paths(file_dep):
        """Find all the possible paths which could satisfy the dependency
        'file_dep'."""

        rps = file_dep.attrs.get(paths_prefix, [""])
        files = file_dep.attrs[files_prefix]
        if isinstance(files, basestring):
                files = [files]
        return [os.path.join(rp, f) for rp in rps for f in files]

def find_package_using_delivered_files(delivered, file_dep, dep_vars,
    orig_dep_vars, pkg_vars):
        """Uses a dictionary mapping file paths to packages to determine which
        package delivers the dependency under which variants.

        'delivered' is a dictionary mapping paths to a list of fmri, variants
        pairs.

        'file_dep' is the dependency that is being resolved.

        'dep_vars' are the variants for which the dependency has not yet been
        resolved.

        'orig_dep_vars' is the original set of variants under which the
        dependency must be satisfied.
        
        'pkg_vars' is the list of variants against which the package delivering
        the action was published."""

        res = None
        variants_with_matches = []
        errs = []
        multiple_path_errs = {}
        for p in make_paths(file_dep):
                delivered_list = []
                if p in delivered:
                        delivered_list = delivered[p]
                # XXX Eventually, this needs to be changed to use the
                # link information provided by the manifests being
                # resolved against, including the packages currently being
                # published.
                try:
                        new_res, dep_vars = helper(delivered_list, file_dep,
                            dep_vars, orig_dep_vars, pkg_vars)
                except AmbiguousPathError, e:
                        errs.append(e)
                else:
                        # We know which path satisfies this dependency, so
                        # remove the list of files and paths, and replace them
                        # with the single path that works.
                        for na, nv in new_res:
                                na.attrs.pop(paths_prefix, None)
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
                                        if v.intersects(new_v) or \
                                            new_v.intersects(v):
                                                multiple_path_errs.setdefault(a,
                                                    set([a]))
                                                multiple_path_errs[a].add(new_a)
                                        else:
                                                res.append((new_a, new_v))
        for a in multiple_path_errs:
                errs.append(MultiplePackagesPathError(multiple_path_errs[a],
                    file_dep))

        # Extract the actions from res, and only return those which don't have
        # multiple path errors.
        return [a for a, v in res if a not in multiple_path_errs], dep_vars, \
            errs

def find_package(api_inst, delivered, installed, file_dep, pkg_vars):
        """Find the packages which resolve the dependency. It returns a list of
        dependency actions with the fmri tag resolved.

        'api_inst' is an ImageInterface which references the current image.

        'delivered' is a dictionary mapping paths to a list of fmri, variants
        pairs.

        'file_dep' is the dependency being resolved.

        "pkg_vars' is the variants against which the package was published."""

        orig_dep_vars = variants.VariantSets(file_dep.get_variants())
        orig_dep_vars.merge_unknown(pkg_vars)
        dep_vars = orig_dep_vars.copy()
        # First try to resolve the dependency against the delivered files.
        res, dep_vars, errs = find_package_using_delivered_files(delivered,
                file_dep, dep_vars, orig_dep_vars, pkg_vars)
        if res and dep_vars.is_satisfied():
                return res, dep_vars, errs
        # If the dependency isn't fully satisfied, resolve it against the
        # files installed in the current image.
        inst_res, dep_vars, inst_errs = find_package_using_delivered_files(
            installed, file_dep, dep_vars, orig_dep_vars, pkg_vars)
        res.extend(inst_res)
        errs.extend(inst_errs)
        return res, dep_vars, errs

def is_file_dependency(act):
        return act.name == "depend" and \
            act.attrs.get("fmri", None) == base.Dependency.DUMMY_FMRI and \
            "%s.file" % base.Dependency.DEPEND_DEBUG_PREFIX in act.attrs

def resolve_deps(manifest_paths, api_inst):
        """For each manifest given, resolve the file dependencies to package
        dependencies. It returns a mapping from manifest_path to a list of
        dependencies and a list of unresolved dependencies.

        'manifest_paths' is a list of paths to the manifests being resolved.

        'api_inst' is an ImageInterface which references the current image."""

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

        delivered_files = {}
        installed_files = {}
        # Build a list of all files delivered in the manifests being resolved.
        for n, f_list, pkg_vars in (
            (name,
            itertools.chain(mfst.gen_actions_by_type("file"),
                mfst.gen_actions_by_type("hardlink"),
                mfst.gen_actions_by_type("link")),
            pv)
            for mp, name, mfst, pv, miss_files in manifests
        ):
                for f in f_list:
                        dep_vars = variants.VariantSets(f.get_variants())
                        dep_vars.merge_unknown(pkg_vars)
                        delivered_files.setdefault(
                            f.attrs["path"], []).append((n, dep_vars))
        # Build a list of all files delivered in the packages installed on
        # the system.
        for (pub, stem, ver), summ, cats, states in api_inst.get_pkg_list(
            api.ImageInterface.LIST_INSTALLED):
                pfmri = fmri.PkgFmri("pkg:/%s@%s" % (stem, ver))
                mfst = api_inst.get_manifest(pfmri, all_variants=True)
                pv = mfst.get_all_variants()
                for f in itertools.chain(mfst.gen_actions_by_type("file"),
                    mfst.gen_actions_by_type("hardlink"),
                    mfst.gen_actions_by_type("link")):
                        dep_vars = variants.VariantSets(f.get_variants())
                        dep_vars.merge_unknown(pkg_vars)
                        installed_files.setdefault(
                            f.attrs["path"], []).append((pfmri, dep_vars))

        pkg_deps = {}
        errs = []
        for mp, name, mfst, pkg_vars, miss_files in manifests:
                errs.extend(miss_files)
                if mfst is None:
                        pkg_deps[mp] = None
                        continue
                pkg_res = [
                    (d, find_package(api_inst, delivered_files, installed_files,
                        d, pkg_vars))
                    for d in mfst.gen_actions_by_type("depend")
                    if is_file_dependency(d)
                ]
                deps = []
                for file_dep, (res, dep_vars, pkg_errs) in pkg_res:
                        errs.extend(pkg_errs)
                        if not res:
                                dep_vars.merge_unknown(pkg_vars)
                                errs.append(UnresolvedDependencyError(mp,
                                    file_dep, dep_vars))
                        else:
                                deps.extend(res)
                                if not dep_vars.is_satisfied():
                                        errs.append(UnresolvedDependencyError(
                                            mp, file_dep, dep_vars))
                pkg_deps[mp] = deps
                        
        return pkg_deps, errs
