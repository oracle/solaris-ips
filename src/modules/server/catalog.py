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
# Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

try:
        import cherrypy
except ImportError:
        # Optional dependency.
        pass

import errno
import os
import shutil
import signal
import sys
import threading

import pkg.catalog as catalog
import pkg.fmri as fmri
import pkg.indexer as indexer
import pkg.manifest as manifest
import pkg.pkgsubprocess as subprocess
import pkg.search_errors as se
import pkg.server.query_parser as query_p

from pkg.misc import EmptyI
from pkg.server.errors import SvrConfigError

class ServerCatalog(catalog.Catalog):
        """The catalog information which is only needed by the server."""

        def __init__(self, cat_root, publisher=None, pkg_root=None,
            read_only=False, index_root=None, repo_root=None,
            rebuild=False, verbose=False, fork_allowed=False,
            has_writable_root=False):

                self.fork_allowed = fork_allowed
                self.index_root = index_root
                self.repo_root = repo_root
                # XXX this is a cheap hack to determine whether information
                # about catalog operations should be logged using cherrypy.
                self.verbose = verbose

                # The update_handle lock protects the update_handle variable.
                # This allows update_handle to be checked and acted on in a
                # consistent step, preventing the dropping of needed updates.
                # The check at the top of refresh index should always be done
                # prior to deciding to spin off a process for indexing as it
                # prevents more than one indexing process being run at the same
                # time.
                self.searchdb_update_handle_lock = threading.Lock()

                if os.name == 'posix':
                        try:
                                signal.signal(signal.SIGCHLD,
                                    self.child_handler)
                        except ValueError:
                                self.__log("Tried to create signal handler in "
                                    "a thread other than the main thread.")

                self.searchdb_update_handle = None
                self._search_available = False
                self.deferred_searchdb_updates = []
                self.deferred_searchdb_updates_lock = threading.Lock()

                self.refresh_again = False

                catalog.Catalog.__init__(self, cat_root, publisher, pkg_root,
                    read_only, rebuild)

                searchdb_file = os.path.join(self.repo_root, "search")
                try:
                        os.unlink(searchdb_file + ".pag")
                except OSError:
                        pass
                try:
                        os.unlink(searchdb_file + ".dir")
                except OSError:
                        pass

                if not read_only or has_writable_root:
                        try:
                                try:
                                        self.refresh_index()
                                except se.InconsistentIndexException, e:
                                        s = _("Index corrupted or out of date. "
                                            "Removing old index directory (%s) "
                                            " and rebuilding search "
                                            "indexes.") % e.cause
                                        self.__log(s, "INDEX")
                                        shutil.rmtree(self.index_root)
                                        try:
                                                self.refresh_index()
                                        except se.IndexingException, e:
                                                self.__log(str(e), "INDEX")
                                except se.IndexingException, e:
                                        self.__log(str(e), "INDEX")
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        if has_writable_root:
                                                raise SvrConfigError(
                                                    _("writable root not "
                                                    "writable by current user "
                                                    "id or group."))
                                        else:
                                                raise SvrConfigError(
                                                    _("unable to write to "
                                                    "index directory."))
                                raise
                else:
                        self._check_search()

        @staticmethod
        def whence(cmd):
                if cmd[0] != '/':
                        tmp_cmd = cmd
                        cmd = None
                        path = os.environ['PATH'].split(':')
                        path.append(os.environ['PWD'])
                        for p in path:
                                if os.path.exists(os.path.join(p, tmp_cmd)):
                                        cmd = os.path.join(p, tmp_cmd)
                                        break
                        assert cmd
                return cmd

        def __log(self, msg, context=None):
                """Used to notify callers about operations performed by the
                catalog."""
                if self.verbose and "cherrypy" in globals():
                        # XXX generic logging mechanism needed
                        cherrypy.log(msg, context)

        def __index_log(self, msg):
                self.__log(msg, "INDEX")

        def refresh_index(self):
                """ This function refreshes the search indexes if there any new
                packages. It starts a subprocess which results in a call to
                run_update_index (see below) which does the actual update.
                """

                self.searchdb_update_handle_lock.acquire()

                if self.searchdb_update_handle:
                        self.refresh_again = True
                        self.searchdb_update_handle_lock.release()
                        return

                try:
                        fmris_to_index = set(self.fmris())

                        indexer.Indexer.check_for_updates(self.index_root,
                            fmris_to_index)

                        if fmris_to_index:
                                if os.name == "posix" and self.fork_allowed:
                                        cmd = self.whence(sys.argv[0])
                                        args = (sys.executable, cmd,
                                            "--refresh-index", "-d",
                                            self.repo_root)
                                        if os.path.normpath(
                                            self.index_root) != \
                                            os.path.normpath(os.path.join(
                                            self.repo_root, "index")):
                                                writ, t = os.path.split(
                                                    self.index_root)
                                                args += ("--writable-root",
                                                    writ)
                                        try:
                                                self.searchdb_update_handle = \
                                                    subprocess.Popen(args,
                                                    stderr=subprocess.STDOUT)
                                        except Exception, e:
                                                self.__log("Starting the "
                                                    "indexing process failed: "
                                                    "%s" % e)
                                                raise
                                else:
                                        self.run_update_index()
                        else:
                                # Since there is nothing to index, setup
                                # the index and declare search available.
                                # We only log this if this represents
                                # a change in status of the server.
                                ind = indexer.Indexer(self.index_root,
                                    self.get_server_manifest,
                                    self.get_manifest_path, log=self.__index_log)
                                ind.setup()
                                if not self._search_available:
                                        self.__index_log("Search Available")
                                self._search_available = True
                finally:
                        self.searchdb_update_handle_lock.release()

        def run_update_index(self):
                """ Determines which fmris need to be indexed and passes them
                to the indexer.

                Note: Only one instance of this method should be running.
                External locking is expected to ensure this behavior. Calling
                refresh index is the preferred method to use to reindex.
                """
                fmris_to_index = set(self.fmris())

                indexer.Indexer.check_for_updates(self.index_root,
                    fmris_to_index)

                if fmris_to_index:
                        self.__index_log("Updating search indices")
                        self.__update_searchdb_unlocked(fmris_to_index)
                else:
                        ind = indexer.Indexer(self.index_root,
                            self.get_server_manifest, self.get_manifest_path,
                            log=self.__index_log)
                        ind.setup()

        def _check_search(self):
                ind = indexer.Indexer(self.index_root,
                    self.get_server_manifest, self.get_manifest_path,
                    log=self.__index_log)
                if ind.check_index_existence():
                        self._search_available = True
                        self.__index_log("Search Available")

        def build_catalog(self):
                """ Creates an Indexer instance and after building the
                catalog, refreshes the index.
                """
                self._check_search()
                catalog.Catalog.build_catalog(self)
                # refresh_index doesn't use file modification times
                # to determine which packages need to be indexed, so use
                # it to reindex if it's needed.
                self.refresh_index()

        def child_handler(self, sig, frame):
                """ Handler method for the SIGCHLD signal.  Checks to see if the
                search database update child has finished, and enables searching
                if it finished successfully, or logs an error if it didn't.
                """
                try:
                        signal.signal(signal.SIGCHLD, self.child_handler)
                except ValueError:
                        self.__log("Tried to create signal handler in a thread "
                            "other than the main thread.")
                # If there's no update_handle, then another subprocess was
                # spun off and that was what finished. If the poll() returns
                # None, then while the indexer was running, another process
                # that was spun off finished.
                rc = None
                if not self.searchdb_update_handle:
                        return
                rc = self.searchdb_update_handle.poll()
                if rc == None:
                        return

                if rc == 0:
                        self._search_available = True
                        self.__index_log(
                            "Search indexes updated and available.")
                        # Need to acquire this lock to prevent the possibility
                        # of a race condition with refresh_index where a needed
                        # refresh is dropped. It is possible that an extra
                        # refresh will be done with this code, but that refresh
                        # should be very quick to finish.
                        self.searchdb_update_handle_lock.acquire()
                        self.searchdb_update_handle = None
                        self.searchdb_update_handle_lock.release()

                        if self.refresh_again:
                                self.refresh_again = False
                                self.refresh_index()
                elif rc > 0:
                        # If the refresh of the index failed, defensively
                        # declare that search is unavailable.
                        self.__index_log("ERROR building search database, exit "
                            "code: %s" % rc)
                        try:
                                self.__log(
                                    self.searchdb_update_handle.stderr.read())
                                self.searchdb_update_handle.stderr.read()
                        except KeyboardInterrupt:
                                raise
                        except:
                                pass
                        self.searchdb_update_handle_lock.acquire()
                        self.searchdb_update_handle = None
                        self.searchdb_update_handle_lock.release()

        def __update_searchdb_unlocked(self, fmris):
                """ Creates an indexer then hands it fmris It assumes that all
                needed locking has already occurred.
                """
                assert self.index_root

                if fmris:
                        index_inst = indexer.Indexer(self.index_root,
                            self.get_server_manifest, self.get_manifest_path,
                            log=self.__index_log)
                        index_inst.server_update_index(fmris)

        def get_manifest_path(self, f):
                return os.path.join(self.pkg_root, f.get_dir_path())

        def get_server_manifest(self, f, add_to_cache=False):
                assert not add_to_cache
                m = manifest.Manifest()
                mcontent = file(self.get_manifest_path(f)).read()
                m.set_fmri(None, fmri)
                m.set_content(mcontent, EmptyI)
                return m

        def search(self, q):
                assert self.index_root
                l = query_p.QueryLexer()
                l.build()
                qp = query_p.QueryParser(l)
                query = qp.parse(q.encoded_text())
                query.set_info(q.num_to_return, q.start_point, self.index_root,
                    self.get_manifest_path, q.case_sensitive)
                return query.search(self.fmris)                

        def search_available(self):
                return self._search_available or self._check_search()

        @staticmethod
        def read_catalog(cat, path, pub=None):
                """Read the catalog file in "path" and combine it with the
                existing data in "catalog"."""

                catf = file(os.path.join(path, "catalog"))
                for line in catf:
                        if not line.startswith("V pkg") and \
                            not line.startswith("C pkg"):
                                continue

                        f = fmri.PkgFmri(line[7:])
                        ServerCatalog.cache_fmri(cat, f, pub)

                catf.close()
