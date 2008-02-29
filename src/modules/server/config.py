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

import errno
import os
import statvfs
import shutil

import pkg.catalog as catalog
import pkg.updatelog as updatelog

import pkg.server.transaction as trans

# OpenSolaris:  statvfs(2) flags field
ST_RDONLY = 0x01
ST_NOSUID = 0x02
ST_NOTRUNC = 0x04

# depot Server Configuration

class SvrConfig(object):
        """Server configuration and state object.  The authority is the default
        authority under which packages will be stored.  Repository locations are
        the primary derived configuration.  State is the current set of
        transactions and packages stored by the repository."""

        def __init__(self, repo_root, authority):
                self.set_repo_root(repo_root)

                self.authority = authority

                self.read_only = False

                self.in_flight_trans = {}

                # XXX naive:  change to
                # catalog_requests = [ (IP-addr, time), ... ]
                # manifest_requests = { fmri : (IP-addr, time), ... }
                # file requests = [ (IP-addr, time), ... ]
                self.catalog_requests = 0
                self.manifest_requests = 0
                self.file_requests = 0
                self.flist_requests = 0
                self.flist_files = 0
                self.pkgs_renamed = 0

        def init_dirs(self):
                root_needed = False

                try:
                        vfs = os.statvfs(self.repo_root)
                except OSError, e:
                        if e.errno == errno.ENOENT:
                                root_needed = True
                        else:
                                raise

                if root_needed:
                        try:
                                os.makedirs(self.repo_root)
                        except OSError, e:
                                raise

                        vfs = os.statvfs(self.repo_root)

                emsg = "repository directories incomplete"

                if vfs[statvfs.F_FLAG] & ST_RDONLY != 0:
                        self.set_read_only()
                        emsg = "repository directories read-only and incomplete"
                else:
                        if not os.path.exists(self.trans_root):
                                os.makedirs(self.trans_root)
                        if not os.path.exists(self.file_root):
                                os.makedirs(self.file_root)
                        if not os.path.exists(self.pkg_root):
                                os.makedirs(self.pkg_root)
                        if not os.path.exists(self.cat_root):
                                os.makedirs(self.cat_root)
                        if not os.path.exists(self.update_root):
                                os.makedirs(self.update_root)

                if os.path.exists(self.trans_root) and \
                    os.path.exists(self.file_root) and \
                    os.path.exists(self.pkg_root) and \
                    os.path.exists(self.cat_root) and \
                    os.path.exists(self.update_root):
                        return

                raise RuntimeError, emsg

        def set_repo_root(self, root):
                self.repo_root = root
                self.trans_root = "%s/trans" % self.repo_root
                self.file_root = "%s/file" % self.repo_root
                self.pkg_root = "%s/pkg" % self.repo_root
                self.cat_root = "%s/catalog" % self.repo_root
                self.update_root = "%s/updatelog" % self.repo_root

        def set_read_only(self):
                self.read_only = True

        def is_read_only(self):
                return self.read_only

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
                """Tell the catalog to set itself up.  Associate an
                instance of the catalog with this depot."""

                self.catalog = catalog.Catalog(self.cat_root,
                    pkg_root = self.pkg_root, read_only = self.read_only)

                # UpdateLog allows server to issue incremental catalog updates
                self.updatelog = updatelog.UpdateLog(self.update_root,
                    self.catalog)

        def destroy_catalog(self):
                """Destroy the catalog.  This is generally done before we
                re-create a new catalog."""

                if os.path.exists(self.cat_root):
                        shutil.rmtree(self.cat_root)

                if os.path.exists(self.update_root):
                        shutil.rmtree(self.update_root)

        def get_status(self):
                """Display simple server status."""

                ret = """\
Number of packages: %d
Number of in-flight transactions: %d

Number of catalogs served: %d
Number of manifests served: %d
Number of files served: %d
Number of flists requested: %d
Number of files served by flist: %d
Number of packages renamed: %d
""" % (self.catalog.npkgs(), len(self.in_flight_trans),
                self.catalog_requests, self.manifest_requests,
                self.file_requests, self.flist_requests, self.flist_files,
                self.pkgs_renamed)

                return ret

        def inc_catalog(self):
                self.catalog_requests += 1

        def inc_manifest(self):
                self.manifest_requests += 1

        def inc_file(self):
                self.file_requests += 1

        def inc_flist(self):
                self.flist_requests += 1

        def inc_flist_files(self):
                self.flist_files += 1

        def inc_renamed(self):
                self.pkgs_renamed += 1

        def search_available(self):
                return self.catalog.search_available()
