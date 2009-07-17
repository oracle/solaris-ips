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
import pkg.flavor.python as python

class ScriptDependency(base.SinglePathDependency):
        """Class representing the dependency created by having #! at the top
        of a file."""

        def __init__(self, *args, **kwargs):
                attrs = kwargs.get("attrs", {})
                attrs["%s.type" % self.DEPEND_DEBUG_PREFIX] = "script"
                base.SinglePathDependency.__init__(self, attrs=attrs, *args,
                    **kwargs)
        
        def __repr__(self):
                return "PBDep(%s, %s, %s, %s)" % (self.action, self.dep_path,
                    self.pkg_vars, self.dep_vars)

def process_script_deps(action, proto_dir, pkg_vars, **kwargs):
        """Given an action and a place to find the file it references, if the
        file starts with #! a list containing a ScriptDependency is returned.
        Further, if the file is of a known type, it is further analyzed and
        any dependencies found are added to the list returned."""

        # localpath is path to actual file
        # path is path in installed image

        if action.name != "file":
                return []

        path = action.attrs[action.key_attr]
        
        localpath = os.path.join(proto_dir, path)

        try:
                f = open(localpath, "rb")
        except EnvironmentError:
                raise base.MissingFile(localpath)
        l = f.readline()
        f.close()

        # add #! dependency
        if l.startswith("#!"):
                # usedlist omits leading /
                p = (l[2:].split()[0]) # first part of string is path (removes
                # options)
                # we don't handle dependencies through links, so fix up the
                # common one
                p = p.strip()
                if p.startswith("/bin"):
                        p = os.path.join("/usr", p)
                deps = [ScriptDependency(action, p, pkg_vars, proto_dir)]
                elist = []
                if "python" in l:
                        ds, errs = python.process_python_dependencies(localpath,
                            proto_dir, action, pkg_vars)
                        elist.extend(errs)
                        deps.extend(ds)
                return deps, elist
        return [], []
