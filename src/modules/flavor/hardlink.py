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

import pkg.flavor.base as base

class HardlinkDependency(base.PublishingDependency):
        """Class representing the dependency by having an action that's a
        hardlink to a path."""
        def __init__(self, action, path, pkg_vars):
                base_names = [os.path.basename(path)]
                paths = [os.path.dirname(path)]
                base.PublishingDependency.__init__(self, action,
                    base_names, paths, pkg_vars, None, "hardlink")

        def __repr__(self):
                return "HLDep({0}, {1}, {2}, {3}, {4})".format(self.action,
                    self.base_names, self.run_paths, self.pkg_vars,
                    self.dep_vars)

def process_hardlink_deps(action, pkg_vars):
        """Given an action, and the variants against which the action's package
        was published, produce a list with one HardlinkDependency object in
        it."""

        target = action.get_target_path()
        return [HardlinkDependency(action, target, pkg_vars)]
