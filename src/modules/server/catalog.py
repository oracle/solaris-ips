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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import re
import sha
import shutil
import time
import urllib

import pkg.fmri as fmri

class SCatalog(object):
        """An SCatalog is the server's representation of the available package
        catalog in this repository.

        The serialized structure of the repository is an unordered list of
        available package versions, followed by an unordered list of
        incorporation relationships between packages.  This latter section
        allows the graph to be topologically sorted by the client.

        V fmri
        V fmri
        ...
        I fmri fmri
        I fmri fmri
        ...

        XXX It would be nice to include available tags and package sizes,
        although this could also be calculated from the set of manifests.
        """

        def __init__(self):
                self.pkgs = []
                self.relns = {}
                return

        def add_pkg(self, pkg):
                if not pkg in self.pkgs:
                        self.pkgs.append(pkg)

                # for each version in the package,
                #   for each incorporation in the version,
                #     add to the version's list of incorporations

                return

        def matching_pkgs(self, pfmri, constraint):
                # iterate through pkgs, looking for an fmri match
                for pkg in self.pkgs:
                        if pkg.fmri.is_similar(pfmri):
                                return pkg.matching_versions(pfmri, constraint)

                raise KeyError, "%s not found in catalog" % pfmri

        def __str__(self):
                s = ""
                for p in self.pkgs:
                        s = s + p.get_catalog()
                for r in self.relns:
                        s = s + "I %s\n" % r
                return s


