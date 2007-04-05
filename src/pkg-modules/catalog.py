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
#
#ident	"%Z%%M%	%I%	%E% SMI"

class Catalog(object):
        """A Catalog is the representation of the package FMRIs available to
        this client or repository.  Both purposes utilize the same storage
        format."""

        def __init__(self, authority, catalog_root):
                self.authority = authority
                self.catalog_root = catalog_root

                # XXX We should try to open the directory, so that we fail
                # early.

        def add_package_fmri(self, pkg_fmri):
                return

        def delete_package_fmri(self, pkg_fmri):
                return

        def to_string(self):
                """Return the catalog in its marshallable format."""
                return ""

        def from_string(self, str):
                """Parse the given string back into the on-disk catalog."""
                return

        def difference(self, catalog):
                """Return a pair of lists, the first list being those package
                FMRIs present in the current object but not in the presented
                catalog, the second being those present in the presented catalog
                but not in the current catalog."""
                return

