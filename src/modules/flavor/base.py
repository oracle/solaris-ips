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
# Copyright (c) 2009, 2010, Oracle and/or its affiliates. All rights reserved.
#

import os

import pkg.actions.depend as depend
import pkg.variant as variant

class DependencyAnalysisError(Exception):

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)


class MissingFile(DependencyAnalysisError):
        """Exception that is raised when a dependency checker can't find the
        file provided."""

        def __init__(self, file_path):
                Exception.__init__(self)
                self.file_path = file_path

        def __str__(self):
                return _("Couldn't find %s") % self.file_path


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
                self.dep_vars = variant.VariantSets(action.get_variants())

                attrs.update([
                    ("fmri", self.DUMMY_FMRI),
                    ("type", self.DEPEND_TYPE),
                    ("%s.reason" % self.DEPEND_DEBUG_PREFIX, self.action_path())
                ])

                if self.dep_vars is not None:
                        attrs.update(self.dep_vars)

                depend.DependencyAction.__init__(self, **attrs)

        def is_error(self):
                """Return true if failing to resolve this external dependency
                should be considered an error."""

                return True

        def dep_key(self):
                """Return a representation of the location the action depends
                on in a way that is hashable."""

                raise NotImplementedError(_("Subclasses of Dependency must "
                    "implement dep_key. Current class is %s") %
                    self.__class__.__name__)

        def get_var_diff(self, ext_vars):
                """Find the difference of the set of variants declared for the
                action that produced this dependency, and another set of
                variants."""

                vars = variant.VariantSets(self.action.get_variants())
                for k in self.pkg_vars:
                        if k not in vars:
                                vars[k] = self.pkg_vars[k]
                return vars.difference(ext_vars)

        def get_var_set(self):
                vars = variant.VariantSets(self.action.get_variants())
                for k in self.pkg_vars:
                        if k not in vars:
                                vars[k] = self.pkg_vars[k]
                return vars

        def action_path(self):
                """Return the path to the file that generated this dependency.
                """

                return self.action.attrs["path"]

        def __cmp__(self, other):
                """Generic way of ordering two Dependency objects."""

                r = cmp(self.dep_key(), other.dep_key())
                if r == 0:
                        r = cmp(self.action_path(), other.action_path())
                if r == 0:
                        r = cmp(self.__class__.__name__,
                            other.__class__.__name__)
                return r

        def get_vars_str(self):
                """Produce a string representation of the variants that apply
                to the dependency."""

                if self.dep_vars is not None:
                        return " " + " ".join([
                            ("%s=%s" % (k, ",".join(self.dep_vars[k])))
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
        dependencies with multiple files, multiple paths, or both."""

        def __init__(self, action, base_names, run_paths, pkg_vars, proto_dir,
            kind):
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
                """

                self.base_names = sorted(base_names)

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

                attrs = {
                    "%s.file" % self.DEPEND_DEBUG_PREFIX: self.base_names,
                    "%s.path" % self.DEPEND_DEBUG_PREFIX: self.run_paths,
                    "%s.type" % self.DEPEND_DEBUG_PREFIX: kind
                }

                Dependency.__init__(self, action, pkg_vars, proto_dir, attrs)

        def dep_key(self):
                """Return the a value that represents the path of the
                dependency. It must be hashable."""
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

        def possibly_delivered(self, delivered_files):
                """Takes a dictionary of known files, and returns the pathes to
                the files that satisfy this dependency."""

                res = []
                for bn in self.base_names:
                        for rp in self.run_paths:
                                path_to_check = os.path.join(rp, bn)
                                p = self._check_path(path_to_check,
                                    delivered_files)
                                if p:
                                        res.append(p)
                return res

        def resolve_internal(self, delivered_files, *args, **kwargs):
                """Takes a dictionary of files delivered in the same package,
                and returns a tuple of two values.  The first is either None,
                meaning the dependency was satisfied, or self.ERROR, meaning the
                dependency wasn't totally satisfied by the delivered files.  The
                second value is the set of variants for which the dependency
                isn't satisfied.

                '*args' and '**kwargs' are used because subclasses may need
                more information for their implementations. See pkg.flavor.elf
                for an example of this."""

                missing_vars = self.get_var_set()
                for p in self.possibly_delivered(delivered_files):
                        missing_vars.mark_as_satisfied(delivered_files[p])
                        if missing_vars.is_satisfied():
                                return None, missing_vars
                return self.ERROR, missing_vars
