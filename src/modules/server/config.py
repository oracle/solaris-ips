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

import errno
import os
import os.path
import random
import shutil

import pkg.server.catalog as catalog
import pkg.server.transaction as trans
import pkg.updatelog as updatelog

from pkg.server.errors import SvrConfigError

# depot Server Configuration
class SvrConfig(object):
        """Server configuration and state object.  The publisher is the default
        publisher under which packages will be stored.  Repository locations are
        the primary derived configuration.  State is the current set of
        transactions and packages stored by the repository.

        If 'auto_create' is True, a new repository will be created at the
        location specified by 'repo_root' if one does not already exist."""

        def __init__(self, repo_root, content_root, publisher,
            auto_create=False, fork_allowed=False, writable_root=None):
                self.set_repo_root(repo_root)
                self.set_content_root(content_root)
                self.has_writable_root = False
                if writable_root:
                        self.set_writable_root(writable_root)

                self.required_dirs = [self.trans_root, self.file_root,
                    self.pkg_root, self.cat_root, self.update_root]
                self.optional_dirs = [self.index_root]

                self.auto_create = auto_create
                self.publisher = publisher
                self.fork_allowed = fork_allowed
                self.read_only = False
                self.mirror = False

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
                emsg = _("repository directories incomplete")
                if self.auto_create:
                        for d in self.required_dirs + self.optional_dirs:
                                try:
                                        os.makedirs(d)
                                except EnvironmentError, e:
                                        if e.errno == errno.EACCES:
                                                emsg = _("repository "
                                                    "directories not writeable "
                                                    "by current user id or "
                                                    "group and are incomplete")
                                        elif e.errno != errno.EEXIST:
                                                raise

                for d in self.required_dirs:
                        if not os.path.exists(d):
                                if self.auto_create:
                                        raise SvrConfigError(emsg)
                                raise SvrConfigError(_("The specified "
                                    "repository root '%s' is not a valid "
                                    "repository.") % self.repo_root)

                if self.content_root and not os.path.exists(self.content_root):
                        raise SvrConfigError(_("The specified content root "
                            "'%s' does not exist.") % self.content_root)

                return

        def set_repo_root(self, root):
                self.repo_root = os.path.abspath(root)
                self.trans_root = os.path.join(self.repo_root, "trans")
                self.file_root = os.path.join(self.repo_root, "file")
                self.pkg_root = os.path.join(self.repo_root, "pkg")
                self.cat_root = os.path.join(self.repo_root, "catalog")
                self.update_root = os.path.join(self.repo_root, "updatelog")
                self.index_root = os.path.join(self.repo_root, "index")
                self.feed_cache_root = self.repo_root

        def set_content_root(self, root):
                if root:
                        self.content_root = os.path.abspath(root)
                        self.web_root = os.path.join(self.content_root, "web")
                else:
                        self.content_root = None
                        self.web_root = None

        def set_writable_root(self, root):
                root = os.path.abspath(root)
                self.index_root = os.path.join(root, "index")
                self.feed_cache_root = root
                self.has_writable_root = True

        def set_read_only(self):
                self.read_only = True

        def set_mirror(self):
                self.mirror = True

        def is_read_only(self):
                return self.read_only

        def feed_cache_read_only(self):
                return self.read_only and not self.has_writable_root

        def is_mirror(self):
                return self.mirror

        def acquire_in_flight(self):
                """Walk trans_root, acquiring valid transaction IDs."""
                tree = os.walk(self.trans_root)

                for txn in tree:
                        if txn[0] == self.trans_root:
                                continue

                        t = trans.Transaction()
                        t.reopen(self, txn[0])

                        self.in_flight_trans[t.get_basename()] = t

        def acquire_catalog(self, rebuild=False, verbose=False):
                """Tell the catalog to set itself up.  Associate an
                instance of the catalog with this depot."""

                if self.is_mirror():
                        return

                if rebuild:
                        self.destroy_catalog()

                self.catalog = catalog.ServerCatalog(self.cat_root,
                    pkg_root=self.pkg_root, read_only=self.read_only,
                    index_root=self.index_root, repo_root=self.repo_root,
                    rebuild=rebuild, verbose=verbose,
                    fork_allowed=self.fork_allowed,
                    has_writable_root=self.has_writable_root)

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

                if self.mirror:
                        ret = """\
Number of files served: %d
Number of flists requested: %d
Number of files served by flist: %d
""" % (self.file_requests, self.flist_requests, self.flist_files)
                else:
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

class NastySvrConfig(SvrConfig):
        """A subclass of SvrConfig that helps implement options
        for the Nasty server, which misbehaves in order to test
        the client's failure resistance."""

        def __init__(self, repo_root, content_root, publisher,
            auto_create=False, fork_allowed=False, writable_root=None):

                # Call parent's constructor
                SvrConfig.__init__(self, repo_root, content_root, publisher,
                    auto_create, fork_allowed, writable_root)

                self.nasty = 0
 
        def acquire_catalog(self, rebuild=False, verbose=False):
                """Tell the catalog to set itself up.  Associate an
                instance of the catalog with this depot."""

                if self.is_mirror():
                        return

                if rebuild:
                        self.destroy_catalog()

                self.catalog = catalog.NastyServerCatalog(self.cat_root,
                    pkg_root=self.pkg_root, read_only=self.read_only,
                    index_root=self.index_root, repo_root=self.repo_root,
                    rebuild=rebuild, verbose=verbose,
                    fork_allowed=self.fork_allowed,
                    has_writable_root=self.has_writable_root)

                # UpdateLog allows server to issue incremental catalog updates
                self.updatelog = updatelog.NastyUpdateLog(self.update_root,
                    self.catalog)

        def set_nasty(self, level):
                """Set the nasty level using an integer."""

                self.nasty = level

        def is_nasty(self):
                """Returns true if nasty has been enabled."""

                if self.nasty > 0:
                        return True
                return False

        def need_nasty(self):
                """Randomly returns true when the server should misbehave."""

                if random.randint(1, 100) <= self.nasty:
                        return True
                return False

        def need_nasty_bonus(self, bonus=0):
                """Used to temporarily apply extra nastiness to an operation."""

                if self.nasty + bonus > 95:
                        nasty = 95
                else:
                        nasty = self.nasty + bonus

                if random.randint(1, 100) <= nasty:
                        return True
                return False

        def need_nasty_occasionally(self):
                if random.randint(1, 500) <= self.nasty:
                        return True
                return False

        def need_nasty_infrequently(self):
                if random.randint(1, 2000) <= self.nasty:
                        return True
                return False

        def need_nasty_rarely(self):
                if random.randint(1, 20000) <= self.nasty:
                        return True
                return False

