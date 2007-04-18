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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

class Package(object):
        """A Package is a node in the package graph.  It consists of the
        versioning data and authority required to construct a legitimate FMRI,
        its dependencies and incorporations of other package FMRIs, and the
        contents metadata used to request and install its extended content.

        The dependencies are presented as a list of Dependency objects.

        The contents are presented as a list of Contents objects."""

        def __init__(self, authority, name, version, dependencies, contents):
                self.authority = authority
                self.name = name
                self.version = version
                self.dependencies = dependencies
                self.contents = contents

                # XXX We should try to open the directory, so that we fail
                # early.

        def add_content(self, content):
                self.contents += content
                return

        def add_dependency(self, dependency):
                self.dependencies += dependency
                return

# XXX PackageHistory or PackageSequence class?  Or is it sufficient to have a
# content_differences(self, pkg) in the Package class?
