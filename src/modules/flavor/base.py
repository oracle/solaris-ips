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

import os

import pkg.actions.depend as depend
import pkg.variant as variant

class DependencyAnalysisError(Exception):
        pass


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
                vs = variant.VariantSets(action.get_variants())
                if vs == {}:
                        self.dep_vars = None
                else:
                        self.dep_vars = vs

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


class SinglePathDependency(Dependency):
        """This class serves as a base for all dependencies which represent an
        action depending on a specific file."""

        def __init__(self, action, dep_path, pkg_vars, proto_dir, attrs):
                """Construct a SinglePathDependency object.
                
                'action' is the action which produced this dependency.

                'dep_path' is the path the action depends on.

                'pkg_vars' is the list of variants against which the package
                delivering the action was published.

                'proto_dir' is the proto area where the file the action delivers
                lives.

                'attrs' is a dictionary to containing the relevant action tags
                for the dependency.
                """

                if dep_path is not None:
                        self.dep_path = self.make_relative(dep_path, proto_dir)
                        attrs["%s.file" % self.DEPEND_DEBUG_PREFIX] = \
                            self.dep_path
                else:
                        self.dep_path = None
                
                Dependency.__init__(self, action, pkg_vars, proto_dir, attrs)

        def dep_key(self):
                """Return the a value that represents the path of the
                dependency. It must be hashable."""
                return self.dep_path

        def possibly_delivered(self, delivered_files, **kwargs):
                """Takes a dictionary of files that have been delivered, and
                returns the path to the file that satisfies this dependency, or
                None if no such delivered file exists."""

                # Using normpath and realpath are ok here because the dependency
                # is being checked against the files, directories, and links
                # delivered in the proto area.
                if self.dep_path in delivered_files:
                        return self.dep_path
                norm_path = os.path.normpath(os.path.join(self.proto_dir,
                    self.dep_path))
                if norm_path in delivered_files:
                        return norm_path

                real_path = os.path.realpath(norm_path)
                if real_path in delivered_files:
                        return real_path

                return None

        def resolve_internal(self, delivered_files, **kwargs):
                """Takes a dictionary of files that have been delivered, and
                returns a tuple of two values.  The first is either None,
                meaning the dependency was satisfied, or self.ERROR, meaning the
                dependency wasn't totally satisfied by the delivered files.  The
                second value is the set of variants when the dependency isn't
                satisfied."""

                p = self.possibly_delivered(delivered_files=delivered_files,
                    **kwargs)
                if p is not None:
                        missing_vars = self.get_var_diff(delivered_files[p])
                        if missing_vars:
                                return self.ERROR, missing_vars
                        return None, None
                else:
                        return self.ERROR, self.dep_vars


class MultiplePathDependency(SinglePathDependency):
        """This class serves as a base for all dependencies which represent an
        action depending on a basename with many potential paths to that
        basename."""

        def __init__(self, action, base_name, run_paths, pkg_vars, proto_dir,
            attrs):
                """Construct a SinglePathDependency object.
                
                'action' is the action which produced this dependency.

                'base_name' is the name of the file of the dependency.

                'run_paths' is the list of directory paths to the file of the
                dependency.

                'pkg_vars' is the list of variants against which the package
                delivering the action was published.

                'proto_dir' is the proto area where the file the action delivers
                lives.

                'attrs' is a dictionary to containing the relevant action tags
                for the dependency.
                """

                self.base_name = base_name
                self.run_paths = [
                    self.make_relative(rp, proto_dir) for rp in run_paths
                ]
                
                attrs.update([
                    ("%s.file" % self.DEPEND_DEBUG_PREFIX, self.base_name),
                    ("%s.path" % self.DEPEND_DEBUG_PREFIX, self.run_paths)
                ])
                
                SinglePathDependency.__init__(self, action, None, pkg_vars,
                    proto_dir, attrs)

        def dep_key(self):
                """Return the a value that represents the path of the
                dependency. It must be hashable."""
                return (self.base_name, tuple(self.run_paths))
                
        def possibly_delivered(self, delivered_files, delivered_base_names,
            **kwargs):
                """Takes a dictionary of files that have been delivered
                ('delivered_files'), a dictionary of base names that have
                been delivered ('delivered_base_names'), and returns the path
                to a file that satisfies this dependency, or None if no such
                delivered file exists."""

                for rp in self.run_paths:
                        self.dep_path = os.path.join(rp, self.base_name)
                        p = SinglePathDependency.possibly_delivered(self,
                            delivered_files=delivered_files)
                        if p is not None:
                                return p
                return None
