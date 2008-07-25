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
# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import subprocess
import threading
import signal
import os
import sys
import cherrypy

import pkg.catalog as catalog
import pkg.indexer as indexer
import pkg.server.query_engine as query_e

from pkg.misc import SERVER_DEFAULT_MEM_USE_KB
from pkg.misc import emsg

class ServerCatalog(catalog.Catalog):
        """The catalog information which is only needed by the server."""

        def __init__(self, cat_root, authority = None, pkg_root = None,
            read_only = False, index_root = None, repo_root = None,
            rebuild = True):

                self.index_root = index_root
                self.repo_root = repo_root

                # The update_handle lock protects the update_handle variable.
                # This allows update_handle to be checked and acted on in a
                # consistent step, preventing the dropping of needed updates.
                # The check at the top of refresh index should always be done
                # prior to deciding to spin off a process for indexing as it
                # prevents more than one indexing process being run at the same
                # time.
                self.searchdb_update_handle_lock = threading.Lock()

                if self.index_root:
                        self.query_engine = \
                            query_e.ServerQueryEngine(self.index_root)

                if os.name == 'posix':
                        try:
                                signal.signal(signal.SIGCHLD,
                                    self.child_handler)
                        except ValueError:
                                emsg("Tried to create signal handler in "
                                    "a thread other than the main thread")

                self.searchdb_update_handle = None
                self._search_available = False
                self.deferred_searchdb_updates = []
                self.deferred_searchdb_updates_lock = threading.Lock()

                self.refresh_again = False

                catalog.Catalog.__init__(self, cat_root, authority, pkg_root,
                    read_only, rebuild)

        def whence(self, cmd):
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
                                if os.name == 'posix':
                                        cmd = self.whence(sys.argv[0])
                                        args = (cmd, "--refresh-index", "-d",
                                            self.repo_root)
                                        try:
                                                self.searchdb_update_handle = \
                                                    subprocess.Popen(args,
                                                        stderr = \
                                                        subprocess.STDOUT)
                                        except Exception, e:
                                                emsg("Starting the indexing "
                                                    "process failed")
                                                raise
                                else:
                                        self.run_update_index()
                        else:
                                # Since there is nothing to index, setup
                                # the index and declare search available.
                                # We only log this if this represents
                                # a change in status of the server.
                                ind = indexer.Indexer(self.index_root,
                                    SERVER_DEFAULT_MEM_USE_KB)
                                ind.setup()
                                if not self._search_available:
                                        cherrypy.log("Search Available",
                                            "INDEX")
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
                        self.__update_searchdb_unlocked(fmris_to_index)
                else:
                        ind = indexer.Indexer(self.index_root,
                            SERVER_DEFAULT_MEM_USE_KB)
                        ind.setup()

        def build_catalog(self):
                """ Creates an Indexer instance and after building the
                catalog, refreshes the index.
                """
                ind = indexer.Indexer(self.index_root, SERVER_DEFAULT_MEM_USE_KB)
                if ind.check_index_existence():
                        self._search_available = True
                        cherrypy.log("Search Available", "INDEX")
                catalog.Catalog.build_catalog(self)
                # refresh_index doesn't use file modification times
                # to determine which packages need to be indexed, so use
                # it to reindex if it's needed.
                self.refresh_index()

        def child_handler(self, sig, frame):
                """ Handler method for the SIGCLD signal.  Checks to see if the
                search database update child has finished, and enables searching
                if it finished successfully, or logs an error if it didn't.
                """
                try:
                        signal.signal(signal.SIGCHLD, self.child_handler)
                except ValueError:
                        emsg("Tried to create signal handler in "
                            "a thread other than the main thread")
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
                        cherrypy.log("Search indexes updated and available.",
                            "INDEX")
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
                        # XXX This should be logged instead
                        # If the refresh of the index failed, defensively
                        # declare that search is unavailable.
                        self._search_available = False
                        emsg(_("ERROR building search database, rc: %s"))
                        emsg(_(self.searchdb_update_handle.stderr.read()))

        def __update_searchdb_unlocked(self, fmri_list):
                """ Takes a fmri_list and calls the indexer with a list of fmri
                and manifest file path pairs. It assumes that all needed
                locking has already occurred.
                """
                assert self.index_root
                fmri_manifest_list = []

                # Rather than storing those, simply pass along the
                # file and have the indexer take care of opening and
                # reading the manifest file. Since the indexer 
                # processes and discards the manifest structure (and its
                # search dictionary for that matter) this
                # is much more memory efficient.

                for f in fmri_list:
                        mfst_path = os.path.join(self.pkg_root,
                                                 f.get_dir_path())
                        fmri_manifest_list.append((f, mfst_path))

                if fmri_manifest_list:
                        index_inst = indexer.Indexer(self.index_root,
                            SERVER_DEFAULT_MEM_USE_KB)
                        index_inst.server_update_index(fmri_manifest_list)

        def search(self, token):
                """Search through the search database for 'token'.  Return a
                list of token type / fmri pairs."""
                assert self.index_root
                if not self.query_engine:
                        self.query_engine = \
                            query_e.ServerQueryEngine(self.index_root)
                query = query_e.Query(token)
                return self.query_engine.search(query)
