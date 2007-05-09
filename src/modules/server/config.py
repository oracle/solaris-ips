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

import os
import urllib

import pkg.catalog as catalog
import pkg.fmri as fmri
import pkg.package as package

import pkg.server.transaction as trans

# depot Server Configuration

class SvrConfig(object):
        """Server configuration and state object.  The authority is the default
        authority under which packages will be stored.  Repository locations are
        the primary derived configuration.  State is the current set of
        transactions and packages stored by the repository."""

        def __init__(self, repo_root, authority):
                self.repo_root = repo_root
                self.trans_root = "%s/trans" % self.repo_root
                self.file_root = "%s/file" % self.repo_root
                self.pkg_root = "%s/pkg" % self.repo_root

                self.authority = authority

                self.catalog = catalog.Catalog()
                self.in_flight_trans = {}

                self.catalog_requests = 0
                self.manifest_requests = 0
                self.file_requests = 0

        def init_dirs(self):
                # XXX refine try/except
                try:
                        os.makedirs(self.trans_root)
                        os.makedirs(self.file_root)
                        os.makedirs(self.pkg_root)
                except OSError:
                        pass

        def acquire_in_flight(self):
                """Walk trans_root, acquiring valid transaction IDs."""
                tree = os.walk(self.trans_root)

                for txn in tree:
                        if txn[0] == self.trans_root:
                                continue

                        t = trans.Transaction()
                        t.reopen(self, txn[0])

                        self.in_flight_trans[t.get_basename()] = t

        def acquire_catalog(self):
                """Walk pkg_root, constructing in-memory catalog.

                XXX An alternate implementation would be to treat an on-disk
                catalog as authoritative, although interruptions between package
                version commits and catalog updates would still require a walk
                of the package version tree."""

                tree = os.walk(self.pkg_root)

                for pkg in tree:
                        if pkg[0] == self.pkg_root:
                                continue

                        # XXX
                        f = fmri.PkgFmri(urllib.unquote(
                            os.path.basename(pkg[0])), None)
                        p = package.Package(self, f)
                        p.load()

                        self.catalog.add_pkg(p)

        def get_status(self):
                """Display simple server status."""

                ret = """\
Number of packages: %d
Number of in-flight transactions: %d

Number of catalogs served: %d
Number of manifests served: %d
Number of files served: %d
""" % (len(self.catalog.pkgs), len(self.in_flight_trans), self.catalog_requests,
                self.manifest_requests, self.file_requests)

                return ret

        def inc_catalog(self):
                self.catalog_requests += 1

        def inc_manifest(self):
                self.manifest_requests += 1

        def inc_file(self):
                self.file_requests += 1

