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

import pkg.flavor.base as base
import pkg.flavor.depthlimitedmf as modulefinder

class PythonModuleMissingPath(base.DependencyAnalysisError):
        """Exception that is raised when a module reports a module as a
        dependency without a path to that module."""

        def __init__(self, name, localpath):
                Exception.__init__(self)
                self.name = name
                self.localpath = localpath

        def __str__(self):
                return _("Could not find the file for %s imported "
                    "in %s") % (self.name, self.localpath)


class PythonDependency(base.SinglePathDependency):
        """Class representing the dependency created by importing a module
        in python."""

        def __init__(self, *args, **kwargs):
                attrs = kwargs.get("attrs", {})
                attrs["%s.type" % self.DEPEND_DEBUG_PREFIX] = "python"

                base.SinglePathDependency.__init__(self, attrs=attrs, *args,
                    **kwargs)

        def __repr__(self):
                return "PythonDep(%s, %s, %s)" % (self.action, self.dep_path,
                    self.pkg_vars)


def process_python_dependencies(localpath, proto_dir, action, pkg_vars):
        """Given the path to a python file, the proto area containing that file,
        the action that produced the dependency, and the variants against which
        the action's package was published, produce a list of PythonDependency
        objects."""

        mf = modulefinder.DepthLimitedModuleFinder(proto_dir)
        mf.run_script(localpath, depth=1)
        deps = []
        errs = []
        for m in mf.modules.values():
                if m.__name__ == "__main__":
                        # The file at localpath is returned as a loaded module
                        # under the name __main__.
                        continue
                
                if m.__file__ is not None:
                        deps.append(PythonDependency(action, m.__file__,
                            pkg_vars, proto_dir))
                else:
                        errs.append(PythonModuleMissingPath(m.__name__,
                            localpath))
        return deps, errs
