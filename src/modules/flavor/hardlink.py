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

import pkg.flavor.base as base

class HardlinkDependency(base.SinglePathDependency):
        """Class representing the dependency by having an action that's a
        hardlink to a path."""

        def __init__(self, *args, **kwargs):
                attrs = kwargs.get("attrs", {})
                attrs["%s.type" % self.DEPEND_DEBUG_PREFIX] = "hardlink"

                base.SinglePathDependency.__init__(self, attrs=attrs, *args,
                    **kwargs)

        def __repr__(self):
                return "HLDep(%s, %s, %s)" % (self.action, self.dep_path,
                    self.pkg_vars)

def process_hardlink_deps(action, pkg_vars, proto_dir):
        """Given an action, the variants against which the action's package was
        published, and the proto area, produce a list with one
        HardlinkDependency object in it."""

        target = action.get_target_path()
        return [HardlinkDependency(action, target, pkg_vars, proto_dir)]
