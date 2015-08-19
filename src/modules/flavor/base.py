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
# Copyright (c) 2009, 2015, Oracle and/or its affiliates. All rights reserved.
#

import os
from functools import total_ordering

import pkg.actions.depend as depend
import pkg.variant as variant

from pkg.portable import PD_DEFAULT_RUNPATH

class DependencyAnalysisError(Exception):
        pass


class MissingFile(DependencyAnalysisError):
        """Exception that is raised when a dependency checker can't find the
        file provided."""

        def __init__(self, file_path, dirs=None):
                Exception.__init__(self)
                self.file_path = file_path
                self.dirs = dirs

        def __str__(self):
                if not self.dirs:
                        return _("Couldn't find '{0}'").format(self.file_path)
                else:
                        return _("Couldn't find '{path}' in any of the "
                            "specified search directories:\n{dirs}").format(
                            path=self.file_path,
                            dirs="\n".join(
                            ["\t" + d for d in sorted(self.dirs)]))

class MultipleDefaultRunpaths(DependencyAnalysisError):
        """Exception that is raised when multiple $PGKDEPEND_RUNPATH tokens
        are found in a pkg.depend.runpath attribute value."""

        def __init__(self):
                Exception.__init__(self)

        def __str__(self):
                return _(
                    "More than one $PKGDEPEND_RUNPATH token was set on the "
                    "same action in this manifest.")

class InvalidDependBypassValue(DependencyAnalysisError):
        """Exception that is raised when we encounter an incorrect
        pkg.depend.bypass-generate attribute value."""

        def __init__(self, value, error):
                self.value = value
                self.error = error
                Exception.__init__(self)

        def __str__(self):
                return _(
                    "Invalid pkg.depend.bypass-generate value {val}: "
                    "{err}").format(val=self.value, err=self.error)


class InvalidPublishingDependency(DependencyAnalysisError):
        """Exception that is raised when base_names or run_paths as well as
        full_paths are specified for a PublishingDependency."""

        def __init__(self, error):
                self.error = error
                Exception.__init__(self)

        def __str__(self):
                return _(
                    "Invalid publishing dependency: {0}").format(self.error)


@total_ordering
class Dependency(depend.DependencyAction):
        """Base, abstract class to represent the dependencies a dependency
        generator can produce."""

        ERROR = 0
        WARNING = 1

        DUMMY_FMRI = "__TBD"
        DEPEND_DEBUG_PREFIX = "pkg.debug.depend"
        DEPEND_TYPE = "require"

        def __init__(self, action, pkg_vars, proto_dir, attrs):
                """Each dependency needs to know the action that generated it
                and the variants for the package containing that action.

                'action' is the action which produced this dependency.

                'pkg_vars' is the list of variants against which the package
                delivering the action was published.

                'proto_dir' is the proto area where the file the action delivers
                lives.

                'attrs' is a dictionary to containing the relevant action tags
                for the dependency.
                """
                self.action = action
                self.pkg_vars = pkg_vars
                self.proto_dir = proto_dir
                self.dep_vars = self.get_variant_combinations()

                attrs.update([
                    ("fmri", self.DUMMY_FMRI),
                    ("type", self.DEPEND_TYPE),
                    ("{0}.reason".format(self.DEPEND_DEBUG_PREFIX),
                    self.action_path())
                ])

                attrs.update(action.get_variant_template())
                # Only lists are permitted for multi-value action attributes.
                for k, v in attrs.items():
                        if isinstance(v, set):
                                attrs[k] = list(v)

                depend.DependencyAction.__init__(self, **attrs)

        def is_error(self):
                """Return true if failing to resolve this external dependency
                should be considered an error."""

                return True

        def dep_key(self):
                """Return a representation of the location the action depends
                on in a way that is hashable."""

                raise NotImplementedError(_("Subclasses of Dependency must "
                    "implement dep_key. Current class is {0}").format(
                    self.__class__.__name__))

        def get_variant_combinations(self, satisfied=False):
                """Create the combinations of variants that this action
                satisfies or needs satisfied.

                'satisfied' determines whether the combination produced is
                satisfied or unsatisfied."""

                variants = self.action.get_variant_template()
                variants.merge_unknown(self.pkg_vars)
                return variant.VariantCombinations(variants,
                    satisfied=satisfied)

        def action_path(self):
                """Return the path to the file that generated this dependency.
                """

                return self.action.attrs["path"]

        def key(self):
                """Keys for ordering two Dependency objects. Use ComparableMinxin
                to do the rich comparison."""
                return (self.dep_key(), self.action_path(),
                    self.__class__.__name__)

        def __eq__(self, other):
                return self.key() == other.key()

        def __lt__(self, other):
                return self.key() < other.key()

        def __hash__(self):
                return hash(self.key())

        def get_vars_str(self):
                """Produce a string representation of the variants that apply
                to the dependency."""

                if self.dep_vars is not None:
                        return " " + " ".join([
                            ("{0}={1}".format(k, ",".join(self.dep_vars[k])))
                            for k in sorted(self.dep_vars.keys())
                        ])

                return ""

        @staticmethod
        def make_relative(path, dir):
                """If 'path' is an absolute path, make it relative to the
                directory path given, otherwise, make it relative to root."""
                if path.startswith(dir):
                        path = path[len(dir):]
                return path.lstrip("/")


class PublishingDependency(Dependency):
        """This class serves as a base for all dependencies.  It handles
        dependencies with multiple files, multiple paths, or both.

        File dependencies are stored either as a list of base_names and
        a list of run_paths, or are expanded, and stored as a list of
        full_paths to each file that could satisfy the dependency.
        """

        def __init__(self, action, base_names, run_paths, pkg_vars, proto_dir,
            kind, full_paths=None):
                """Construct a PublishingDependency object.

                'action' is the action which produced this dependency.

                'base_names' is the list of files of the dependency.

                'run_paths' is the list of directory paths to the file of the
                dependency.

                'pkg_vars' is the list of variants against which the package
                delivering the action was published.

                'proto_dir' is the proto area where the file the action delivers
                lives.  It may be None if the notion of a proto_dir is
                meaningless for a particular PublishingDependency.

                'kind' is the kind of dependency that this is.

                'full_paths' if not None, is used instead of the combination of
                'base_names' and 'run_paths' when defining dependencies where
                exact paths to files matter (for example, SMF dependencies which
                are satisfied by more than one SMF manifest are not searched for
                using the manifest base_name in a list of run_paths, unlike
                python modules, which use $PYTHONPATH.)  Specifying full_paths
                as well as base_names/run_paths combinations is not allowed.
                """

                if full_paths and (base_names or run_paths):
                        # this should never happen, as consumers should always
                        # construct PublishingDependency objects using either
                        # full_paths or a combination of base_names and
                        # run_paths.
                        raise InvalidPublishingDependency(
                            "A dependency was specified using full_paths={0} as "
                            "well as base_names={1} and run_paths={2}".format(
                            full_paths, base_names, run_paths))

                self.base_names = sorted(base_names)

                if full_paths == None:
                        self.full_paths = []
                else:
                        self.full_paths = full_paths

                if proto_dir is None:
                        self.run_paths = sorted(run_paths)
                        # proto_dir is set to "" so that the proto_dir can be
                        # joined unconditionally with other paths.  This makes
                        # the code path in _check_path simpler.
                        proto_dir = ""
                else:
                        self.run_paths = sorted([
                            self.make_relative(rp, proto_dir)
                            for rp in run_paths
                        ])

                attrs = {"{0}.type".format(self.DEPEND_DEBUG_PREFIX): kind}
                if self.full_paths:
                        attrs["{0}.fullpath".format(self.DEPEND_DEBUG_PREFIX)] = \
                            self.full_paths
                else:
                        attrs.update({
                            "{0}.file".format(
                            self.DEPEND_DEBUG_PREFIX): self.base_names,
                            "{0}.path".format(
                            self.DEPEND_DEBUG_PREFIX): self.run_paths,
                        })

                Dependency.__init__(self, action, pkg_vars, proto_dir, attrs)

        def dep_key(self):
                """Return the a value that represents the path of the
                dependency. It must be hashable."""
                if self.full_paths:
                        return (tuple(self.full_paths))
                else:
                        return (tuple(self.base_names), tuple(self.run_paths))

        def _check_path(self, path_to_check, delivered_files):
                """Takes a dictionary of files that are known to exist, and
                returns the path to the file that satisfies this dependency, or
                None if no such delivered file exists."""

                # Using normpath and realpath are ok here because the dependency
                # is being checked against the files, directories, and links
                # delivered in the proto area.
                if path_to_check in delivered_files:
                        return path_to_check
                norm_path = os.path.normpath(os.path.join(self.proto_dir,
                    path_to_check))
                if norm_path in delivered_files:
                        return norm_path

                real_path = os.path.realpath(norm_path)
                if real_path in delivered_files:
                        return real_path

                return None

        def possibly_delivered(self, delivered_files, links, resolve_links,
            orig_dep_vars):
                """Finds a list of files which satisfy this dependency, and the
                variants under which each file satisfies it.  It takes into
                account links and hardlinks.

                'delivered_files' is a dictionary which maps paths to the
                packages that deliver the path and the variants under which the
                path is present.

                'links' is an Entries namedtuple which contains two
                dictionaries.  One dictionary maps package identity to the links
                that it delivers.  The other dictionary, in this case, should be
                empty.

                'resolve_links' is a function which finds the real paths that a
                path can resolve into, given a set of known links.

                'orig_dep_vars' is the set of variants under which this
                dependency exists."""

                res = []
                # A dependency may be built using this dictionary of attributes.
                # Seeding it with the type is necessary to create a Dependency
                # object.
                attrs = {
                        "type":"require"
                }
                def process_path(path_to_check):
                        res = []
                        # Find the potential real paths that path_to_check could
                        # resolve to.
                        res_pths, res_links = resolve_links(
                            path_to_check, delivered_files, links,
                            orig_dep_vars, attrs)
                        for res_pth, res_pfmri, nearest_fmri, res_vc, \
                            res_via_links in res_pths:
                                p = self._check_path(res_pth, delivered_files)
                                if p:
                                        res.append((p, res_vc))
                        return res

                # if this is an expanded dependency, we iterate over the list of
                # full paths
                if self.full_paths:
                        for path_to_check in self.full_paths:
                                res.extend(process_path(path_to_check))

                # otherwise, it's a dependency with run_path and base_names
                # entries
                else:
                        for bn in self.base_names:
                                for rp in self.run_paths:
                                        path_to_check = os.path.normpath(
                                            os.path.join(rp, bn))
                                        res.extend(process_path(path_to_check))
                return res

        def resolve_internal(self, delivered_files, links, resolve_links, *args,
            **kwargs):
                """Determines whether this dependency (self) can be satisfied by
                the other items in the package which delivers it.  A tuple of
                two values is produced.  The first is either None, meaning the
                dependency was satisfied, or self.ERROR, meaning the dependency
                wasn't totally satisfied by the delivered files.  The second
                value is the set of variants for which the dependency isn't
                satisfied.

                'delivered_files' is a dictionary which maps package identity
                to the files the package delivers.

                'links' is an Entries namedtuple which contains two
                dictionaries.  One dictionary maps package identity to the links
                that it delivers.  The other dictionary, in this case, should be
                empty.

                'resolve_links' is a function which finds the real paths a path
                can resolve into given a set of known links.

                '*args' and '**kwargs' are used because subclasses may need
                more information for their implementations. See pkg.flavor.elf
                for an example of this."""

                missing_vars = self.get_variant_combinations()
                orig_dep_vars = self.get_variant_combinations()
                for p, vc in self.possibly_delivered(delivered_files, links,
                    resolve_links, orig_dep_vars):
                        missing_vars.mark_as_satisfied(vc)
                        if missing_vars.is_satisfied():
                                return None, missing_vars
                return self.ERROR, missing_vars


def insert_default_runpath(default_runpath, run_paths):
        """Insert our default search path where the PD_DEFAULT_PATH token was
        found, returning an updated list of run paths."""
        try:
                new_paths = run_paths
                index = run_paths.index(PD_DEFAULT_RUNPATH)
                new_paths = run_paths[:index] + \
                    default_runpath + run_paths[index + 1:]
                if PD_DEFAULT_RUNPATH in new_paths:
                        raise MultipleDefaultRunpaths()
                return new_paths

        except ValueError:
                # no PD_DEFAULT_PATH token, so we override the
                # whole default search path
                return run_paths
