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

import os
import stat

import pkg.flavor.base as base
import pkg.flavor.python as python

from pkg.portable import PD_LOCAL_PATH, PD_PROTO_DIR
from pkg.misc import force_str

class ScriptNonAbsPath(base.DependencyAnalysisError):
        """Exception that is raised when a file uses a relative path for the
        binary with which it should be run."""

        def __init__(self, lp, bin):
                Exception.__init__(self)
                self.lp = lp
                self.bin = bin

        def __str__(self):
                return _("{lp} says it should be run with '{bin}' which is "
                    "a relative path.").format(**vars(self))

class ScriptDependency(base.PublishingDependency):
        """Class representing the dependency created by having #! at the top
        of a file."""

        def __init__(self, action, path, pkg_vars, proto_dir):
                base_names = [os.path.basename(path)]
                paths = [os.path.dirname(path)]
                base.PublishingDependency.__init__(self, action,
                    base_names, paths, pkg_vars, proto_dir, "script")

        def __repr__(self):
                return "PBDep({0}, {1}, {2}, {3}, {4})".format(self.action,
                    self.base_names, self.run_paths, self.pkg_vars,
                    self.dep_vars)

def process_script_deps(action, pkg_vars, **kwargs):
        """Given an action, if the file starts with #! a list containing a
        ScriptDependency is returned. Further, if the file is of a known type,
        it is further analyzed and any dependencies found are added to the list
        returned."""

        if action.name != "file":
                return [], [], {}

        f = action.data()
        l = force_str(f.readline())
        f.close()

        deps = []
        elist = []
        pkg_attrs = {}

        script_path = None
        run_paths = kwargs.get("run_paths", [])
        # add #! dependency
        if l.startswith("#!"):
                # Determine whether the file will be delivered executable.
                ex_bit = int(action.attrs.get("mode", "0"), 8) & \
                    (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                if ex_bit:
                        p = (l[2:].split()[0])
                        # first part of string is path (removes options)
                        # we don't handle dependencies through links, so fix up
                        # the common one
                        p = p.strip()
                        if not os.path.isabs(p):
                                elist.append(ScriptNonAbsPath(
                                    action.attrs[PD_LOCAL_PATH], p))
                        else:
                                if p.startswith("/bin"):
                                        # Use p[1:] to strip off the leading /.
                                        p = os.path.join("/usr", p[1:])
                                deps.append(ScriptDependency(action, p,
                                    pkg_vars, action.attrs[PD_PROTO_DIR]))
                                script_path = l
                if "python" in l:
                        ds, errs, py_attrs = python.process_python_dependencies(
                            action, pkg_vars, script_path, run_paths)
                        elist.extend(errs)
                        deps.extend(ds)
                        for key in py_attrs:
                                if key in pkg_attrs:
                                        pkg_attrs[key].extend(py_attrs[key])
                                else:
                                        pkg_attrs[key] = py_attrs[key]
        return deps, elist, pkg_attrs
