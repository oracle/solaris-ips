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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import itertools
import os
import urllib

import pkg.actions as actions
import pkg.client.api as api
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
                # Mark the variants as satisfied so it's possible to know if
                # all variant combinations have been covered.
                dep_vars.mark_as_satisfied(delivered_vars)
                attrs = file_dep.attrs.copy()
                attrs.update({"fmri":str(pfmri)})
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
        if isinstance(rps, basestring):
                rps = [rps]
        return [os.path.join(rp, f) for rp in rps for f in files]

def find_package_using_delivered_files(delivered, file_dep, dep_vars,
    orig_dep_vars):
        """Uses a dictionary mapping file paths to packages to determine which
        package delivers the dependency under which variants.

        'delivered' is a dictionary mapping paths to a list of fmri, variants
        pairs.

        'file_dep' is the dependency that is being resolved.

        'dep_vars' are the variants for which the dependency has not yet been
        resolved.

        'orig_dep_vars' is the original set of variants under which the
        dependency must be satisfied."""

        res = None
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
                            dep_vars, orig_dep_vars)
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
        return [(a, v) for a, v in res if a not in multiple_path_errs], \
            dep_vars, errs

def find_package(delivered, installed, file_dep, pkg_vars):
        """Find the packages which resolve the dependency. It returns a list of
        dependency actions with the fmri tag resolved.

        'delivered' is a dictionary mapping paths to a list of fmri, variants
        pairs.

        'file_dep' is the dependency being resolved.

        'pkg_vars' is the variants against which the package was published."""

        file_dep, orig_dep_vars = split_off_variants(file_dep, pkg_vars)
        dep_vars = orig_dep_vars.copy()

        # First try to resolve the dependency against the delivered files.
        res, dep_vars, errs = find_package_using_delivered_files(delivered,
                file_dep, dep_vars, orig_dep_vars)
        if res and dep_vars.is_satisfied():
                return res, dep_vars, errs
        # If the dependency isn't fully satisfied, resolve it against the
        # files installed in the current image.
        inst_res, dep_vars, inst_errs = find_package_using_delivered_files(
            installed, file_dep, dep_vars, orig_dep_vars)
        res.extend(inst_res)
        errs.extend(inst_errs)
        return res, dep_vars, errs

def is_file_dependency(act):
        return act.name == "depend" and \
            act.attrs.get("fmri", None) == base.Dependency.DUMMY_FMRI and \
            "%s.file" % base.Dependency.DEPEND_DEBUG_PREFIX in act.attrs

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

                # d[0] is the action.  d[1] is the VariantSet for this action.
                return d[0].name, d[0].attrs.get(d[0].key_attr, id(d[0]))

        def add_vars(d, d_vars, pkg_vars):
                """Add the variants 'd_vars' to the dependency 'd', after
                removing the variants matching those defined in 'pkg_vars'."""

                d_vars.remove_identical(pkg_vars)
                d.attrs.update(d_vars)
                # Remove any duplicate values for any attributes.
                d.consolidate_attrs()
                return d

        def key_on_variants(a):
                """Return the key (the VariantSets) to sort the grouped tuples
                by."""

                return a[1]

        def sort_by_variant_subsets(a, b):
                """Sort the tuples so that those actions whose variants are
                supersets of others are placed at the front of the list.  This
                function assumes that a and b are both VariantSets."""

                if a.issubset(b):
                        return 1
                elif b.issubset(a):
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
                                if d_vars.issubset(rel_vars):
                                        found_subset = True
                                        merge_deps(rel_res, d)
                                        break
                                assert(not rel_vars.issubset(d_vars))

                        # If no subset was found, then d_vars is a new set of
                        # conditions under which the dependency d should apply
                        # so add it to the results.
                        if not found_subset:
                                subres.append((d, d_vars))

                # Add the variants to the dependency action and remove any
                # variants that are identical to those defined by the package.
                subres = [add_vars(d, d_vars, pkg_vars) for d, d_vars in subres]
                res.extend(subres)
        return res

def split_off_variants(dep, pkg_vars):
        """Take a dependency which may be tagged with variants and move those
        tags into a VariantSet."""

        dep_vars = variants.VariantSets(dep.get_variants())
        dep_vars.merge_unknown(pkg_vars)
        # Since all variant information is being kept in the above VariantSets,
        # remove the variant information from the action.  This prevents
        # confusion about which is the authoritative source of information.
        dep.strip_variants()
        return dep, dep_vars

def prune_debug_attrs(action):
        """Given a dependency action with pkg.debug.depend attributes
        return a matching action with those attributes removed"""

        attrs = dict((k, v) for k, v in action.attrs.iteritems()
                     if not k.startswith(base.Dependency.DEPEND_DEBUG_PREFIX))
        return actions.depend.DependencyAction(**attrs)

def resolve_deps(manifest_paths, api_inst, prune_attrs=False):
        """For each manifest given, resolve the file dependencies to package
        dependencies. It returns a mapping from manifest_path to a list of
        dependencies and a list of unresolved dependencies.

        'manifest_paths' is a list of paths to the manifests being resolved.

        'api_inst' is an ImageInterface which references the current image.

        'prune_attrs' is a boolean indicating whether debugging
        attributes should be stripped from returned actions."""

        def add_fmri_path_mapping(pathdict, pfmri, mfst):
                """Add mappings from path names to FMRIs and variants.

                'pathdict' is a dict path -> (fmri, variants) to which
                entries are added.

                'pfmri' is the FMRI of the current manifest

                'mfst' is the manifest to process."""

                pvariants = mfst.get_all_variants()

                for f in itertools.chain(mfst.gen_actions_by_type("file"),
                     mfst.gen_actions_by_type("hardlink"),
                     mfst.gen_actions_by_type("link")):
                        dep_vars = variants.VariantSets(f.get_variants())
                        dep_vars.merge_unknown(pvariants)
                        pathdict.setdefault(f.attrs["path"], []).append(
                            (pfmri, dep_vars))


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
        for mp, name, mfst, pkg_vars, miss_files in manifests:
                pfmri = fmri.PkgFmri(name).get_short_fmri()
                add_fmri_path_mapping(delivered_files, pfmri, mfst)

        # Build a list of all files delivered in the packages installed on
        # the system.
        for (pub, stem, ver), summ, cats, states in api_inst.get_pkg_list(
            api.ImageInterface.LIST_INSTALLED):
                pfmri = fmri.PkgFmri("pkg:/%s@%s" % (stem, ver))
                mfst = api_inst.get_manifest(pfmri, all_variants=True)
                add_fmri_path_mapping(installed_files, pfmri.get_short_fmri(),
                                      mfst)

        pkg_deps = {}
        errs = []
        for mp, name, mfst, pkg_vars, miss_files in manifests:
                errs.extend(miss_files)
                if mfst is None:
                        pkg_deps[mp] = None
                        continue
                pkg_res = [
                    (d, find_package(delivered_files, installed_files,
                        d, pkg_vars))
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
                        if not res:
                                dep_vars.merge_unknown(pkg_vars)
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
