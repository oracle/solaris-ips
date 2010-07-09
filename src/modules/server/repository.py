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
# Copyright (c) 2008, 2010, Oracle and/or its affiliates. All rights reserved.

import datetime
import errno
import logging
import os
import os.path
import shutil
import signal
import sys
import tempfile
import threading
import urllib

import pkg.actions as actions
import pkg.catalog as catalog
import pkg.client.api_errors as api_errors
import pkg.config as cfg
import pkg.file_layout.file_manager as file_manager
import pkg.fmri as fmri
import pkg.indexer as indexer
import pkg.manifest as manifest
import pkg.portable as portable
import pkg.misc as misc
import pkg.pkgsubprocess as subprocess
import pkg.search_errors as se
import pkg.query_parser as qp
import pkg.server.query_parser as sqp
import pkg.server.transaction as trans
import pkg.version as version

from pkg.misc import EmptyI, EmptyDict

class RepositoryError(Exception):
        """Base exception class for all Repository exceptions."""

        def __init__(self, *args):
                Exception.__init__(self, *args)
                if args:
                        self.data = args[0]

        def __unicode__(self):
                # To workaround python issues 6108 and 2517, this provides a
                # a standard wrapper for this class' exceptions so that they
                # have a chance of being stringified correctly.
                return str(self)

        def __str__(self):
                return str(self.data)


class RepositoryExistsError(RepositoryError):
        """Used to indicate that a repository already exists at the specified
        location.
        """

        def __str__(self):
                return _("A package repository already exists at '%s'.") % \
                    self.data


class RepositoryFileNotFoundError(RepositoryError):
        """Used to indicate that the hash name provided for the requested file
        does not exist."""

        def __str__(self):
                return _("No file could be found for the specified "
                    "hash name: '%s'.") % self.data


class RepositoryInvalidError(RepositoryError):
        """Used to indicate that a valid repository could not be found at the
        specified location."""

        def __str__(self):
                return _("The path '%s' does not contain a valid package "
                    "repository.") % self.data


class RepositoryInvalidFMRIError(RepositoryError):
        """Used to indicate that the FMRI provided is invalid."""


class RepositoryInvalidTransactionIDError(RepositoryError):
        """Used to indicate that an invalid Transaction ID was supplied."""

        def __str__(self):
                return _("The specified Transaction ID '%s' is invalid.") % \
                    self.data


class RepositoryManifestNotFoundError(RepositoryError):
        """Used to indicate that the requested manifest could not be found."""

        def __str__(self):
                return _("No manifest could be found for the FMRI: '%s'.") % \
                    self.data


class RepositoryMirrorError(RepositoryError):
        """Used to indicate that the requested operation could not be performed
        as the repository is in mirror mode."""

        def __str__(self):
                return _("The requested operation cannot be performed when the "
                    "repository is used in mirror mode.")


class RepositoryReadOnlyError(RepositoryError):
        """Used to indicate that the requested operation could not be performed
        as the repository is currently read-only."""

        def __str__(self):
                return _("The repository is read-only and cannot be modified.")


class RepositorySearchTokenError(RepositoryError):
        """Used to indicate that the token(s) provided to search were undefined
        or invalid."""

        def __str__(self):
                if self.data is None:
                        return _("No token was provided to search.") % self.data

                return _("The specified search token '%s' is invalid.") % \
                    self.data


class RepositorySearchUnavailableError(RepositoryError):
        """Used to indicate that search is not currently available."""

        def __str__(self):
                return _("Search functionality is temporarily unavailable.")


class RepositoryUnsupportedOperationError(RepositoryError):
        """Raised when the repository is unable to support an operation,
        based upon its current configuration."""

        def __str__(self):
                return("Operation not supported for this configuration.")

class RepositoryUpgradeError(RepositoryError):
        """Used to indicate that the specified repository root cannot be used
        as the catalog or format of it is an older version that needs to be
        upgraded before use and cannot be."""

        def __str__(self):
                return _("The format of the repository or its contents needs "
                    "to be upgraded before it can be used to serve package "
                    "data.  However, it is currently read-only and cannot be "
                    "upgraded.  If using pkg.depotd, please restart the server "
                    "without read-only so that the repository can be upgraded.")


class Repository(object):
        """A Repository object is a representation of data contained within a
        pkg(5) repository and an interface to manipulate it."""

        __catalog = None
        __lock = None

        def __init__(self, auto_create=False, catalog_root=None,
            cfgpathname=None, file_root=None, fork_allowed=False,
            index_root=None, log_obj=None, manifest_root=None, mirror=False,
            properties=EmptyDict, read_only=False, repo_root=None,
            trans_root=None, refresh_index=True,
            sort_file_max_size=indexer.SORT_FILE_MAX_SIZE, writable_root=None):
                """Prepare the repository for use."""

                # This lock is used to protect the repository from multiple
                # threads modifying it at the same time.
                self.__lock = threading.Lock()

                self.auto_create = auto_create
                self.cfg = None
                self.cfgpathname = None
                self.fork_allowed = fork_allowed
                self.log_obj = log_obj
                self.mirror = mirror
                self.read_only = read_only
                self.__sort_file_max_size = sort_file_max_size
                self.__tmp_root = None
                self.__file_root = None

                # Set before repo root, since it's possible to have
                # the file root in an entirely different location.  Repo
                # root will govern file_root, if an argument to file_root
                # is not supplied in __init__.
                if file_root:
                        self.file_root = file_root

                # Must be set before most other roots.
                self.repo_root = repo_root

                # These are all overrides for the default values that setting
                # repo_root will provide.  If a caller provides one of these,
                # they are responsible for creating the corresponding path
                # and setting its mode appropriately.
                if catalog_root:
                        self.catalog_root = catalog_root
                if index_root:
                        self.index_root = index_root
                if manifest_root:
                        self.manifest_root = manifest_root
                if trans_root:
                        self.trans_root = trans_root

                # Must be set before writable_root.
                if self.mirror:
                        self.__required_dirs = [self.file_root]
                else:
                        self.__required_dirs = [self.trans_root, self.manifest_root,
                            self.catalog_root, self.file_root]

                # Ideally, callers would just specify overrides for the feed
                # cache root, index_root, etc.  But this must be set after all
                # of the others above.
                self.writable_root = writable_root

                # Must be set after all other roots.
                self.__optional_dirs = [self.index_root]

                # Stats
                self.catalog_requests = 0
                self.manifest_requests = 0
                self.file_requests = 0
                self.flist_requests = 0
                self.flist_files = 0
                self.pkgs_renamed = 0

                # The update_handle lock protects the update_handle variable.
                # This allows update_handle to be checked and acted on in a
                # consistent step, preventing the dropping of needed updates.
                # The check at the top of refresh index should always be done
                # prior to deciding to spin off a process for indexing as it
                # prevents more than one indexing process being run at the same
                # time.
                self.__searchdb_update_handle_lock = threading.Lock()

                if os.name == "posix" and self.fork_allowed:
                        try:
                                signal.signal(signal.SIGCHLD,
                                    self._child_handler)
                        except ValueError:
                                self.__log("Tried to create signal handler in "
                                    "a thread other than the main thread.")

                self.__searchdb_update_handle = None
                self.__search_available = False
                self.__deferred_searchdb_updates = []
                self.__deferred_searchdb_updates_lock = threading.Lock()
                self.__refresh_again = False

                # Initialize.
                self.__lock_repository()
                try:
                        self.__init_config(cfgpathname=cfgpathname,
                            properties=properties)
                        self.__init_dirs()
                        self.__init_state(refresh_index=refresh_index)
                finally:
                        self.__unlock_repository()

        def _child_handler(self, sig, frame):
                """ Handler method for the SIGCHLD signal.  Checks to see if the
                search database update child has finished, and enables searching
                if it finished successfully, or logs an error if it didn't.
                """

                try:
                        signal.signal(signal.SIGCHLD, self._child_handler)
                except ValueError:
                        self.__log("Tried to create signal handler in a thread "
                            "other than the main thread.")

                # If there's no update_handle, then another subprocess was
                # spun off and that was what finished. If the poll() returns
                # None, then while the indexer was running, another process
                # that was spun off finished.
                rval = None
                if not self.__searchdb_update_handle:
                        return
                rval = self.__searchdb_update_handle.poll()
                if rval == None:
                        return

                if rval == 0:
                        self.__search_available = True
                        self.__index_log("Search indexes updated and "
                            "available.")
                        # Need to acquire this lock to prevent the possibility
                        # of a race condition with refresh_index where a needed
                        # refresh is dropped. It is possible that an extra
                        # refresh will be done with this code, but that refresh
                        # should be very quick to finish.
                        self.__searchdb_update_handle_lock.acquire()
                        self.__searchdb_update_handle = None
                        self.__searchdb_update_handle_lock.release()

                        if self.__refresh_again:
                                self.__refresh_again = False
                                self.refresh_index()
                elif rval > 0:
                        # If the refresh of the index failed, defensively
                        # declare that search is unavailable.
                        self.__index_log("ERROR building search database, exit "
                            "code: %s" % rval)
                        try:
                                self.__log(
                                    self.__searchdb_update_handle.stderr.read())
                                self.__searchdb_update_handle.stderr.read()
                        except KeyboardInterrupt:
                                raise
                        except:
                                pass
                        self.__searchdb_update_handle_lock.acquire()
                        self.__searchdb_update_handle = None
                        self.__searchdb_update_handle_lock.release()

        def __mkdtemp(self):
                """Create a temp directory under repository directory for
                various purposes."""

                if not self.repo_root:
                        return

                root = self.repo_root
                if self.writable_root:
                        root = self.writable_root

                tempdir = os.path.normpath(os.path.join(root, "tmp"))
                try:
                        if not os.path.exists(tempdir):
                                os.makedirs(tempdir)
                        return tempfile.mkdtemp(dir=tempdir)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        def __upgrade(self):
                """Upgrades the repository's format and contents if needed."""

                def get_file_lm(pathname):
                        try:
                                mod_time = os.stat(pathname).st_mtime
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT:
                                        return None
                                raise
                        return datetime.datetime.utcfromtimestamp(mod_time)

                if not self.catalog_root:
                        return

                # To determine if an upgrade is needed, first check for a v0
                # catalog attrs file.
                need_upgrade = False
                v0_attrs = os.path.join(self.catalog_root, "attrs")

                # The only place a v1 catalog should exist, at all,
                # is either in self.catalog_root, or in a subdirectory
                # of self.writable_root if a v0 catalog exists.
                v1_cat = None
                writ_cat_root = None
                if self.writable_root:
                        writ_cat_root = os.path.join(
                            self.writable_root, "catalog")
                        v1_cat = catalog.Catalog(
                            meta_root=writ_cat_root, read_only=True)

                v0_lm = None
                if os.path.exists(v0_attrs):
                        # If a v0 catalog exists, then assume any existing v1
                        # catalog needs to be kept in sync if it exists.  If
                        # one doesn't exist, then it needs to be created.
                        v0_lm = get_file_lm(v0_attrs)
                        if not v1_cat or not v1_cat.exists or \
                            v0_lm != v1_cat.last_modified:
                                need_upgrade = True

                if writ_cat_root and not self.read_only:
                        # If a writable root was specified, but the server is
                        # not in read-only mode, then the catalog must not be
                        # stored using the writable root (this is consistent
                        # with the storage of package data in this case).  As
                        # such, destroy any v1 catalog data that might exist
                        # and proceed.
                        shutil.rmtree(writ_cat_root, True)
                        writ_cat_root = None
                        if os.path.exists(v0_attrs) and not self.catalog.exists:
                                # A v0 catalog exists, but no v1 catalog exists;
                                # this can happen when a repository that was
                                # previously run with --writable-root and
                                # --readonly is now being run with only
                                # --writable-root.
                                need_upgrade = True
                elif writ_cat_root and v0_lm and self.read_only:
                        # The catalog lives in the writable_root if a v0 catalog
                        # exists, writ_cat_root is set, and readonly is True.
                        self.catalog_root = writ_cat_root

                if not need_upgrade or self.mirror:
                        # If an upgrade isn't needed, or this is a mirror, then
                        # nothing more should be done to the existing catalog
                        # data.
                        return

                if self.read_only and not self.writable_root:
                        # Any further operations would attempt to alter the
                        # existing catalog data, which can't be done due to
                        # read_only status.
                        raise RepositoryUpgradeError()

                if self.catalog.exists:
                        # v1 catalog should be destroyed if it exists already.
                        self.catalog.destroy()
                elif writ_cat_root and not os.path.exists(writ_cat_root):
                        try:
                                os.mkdir(writ_cat_root, misc.PKG_DIR_MODE)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise

                # To upgrade the repository, the catalog will have to
                # be rebuilt.
                self.__log(_("Upgrading repository; this process will "
                    "take some time."))
                self.__rebuild(lm=v0_lm)

                if not self.read_only and self.repo_root:
                        v0_cat = os.path.join(self.repo_root, "catalog",
                            "catalog")
                        for f in v0_attrs, v0_cat:
                                if os.path.exists(f):
                                        portable.remove(f)

                        # If this fails, it doesn't really matter, but it should
                        # be removed if possible.
                        shutil.rmtree(os.path.join(self.repo_root, "updatelog"),
                            True)

        def __add_package(self, pfmri, manifest=None):
                """Private version; caller responsible for repository
                locking."""

                if not manifest:
                        manifest = self._get_manifest(pfmri, sig=True)
                c = self.catalog
                c.add_package(pfmri, manifest=manifest)

        def __check_search(self):
                if not self.index_root:
                        return

                ind = indexer.Indexer(self.index_root,
                    self._get_manifest, self.manifest,
                    log=self.__index_log,
                    sort_file_max_size=self.__sort_file_max_size)
                cie = False
                try:
                        cie = ind.check_index_existence()
                except se.InconsistentIndexException:
                        pass
                if cie:
                        self.__search_available = True
                        self.__index_log("Search Available")

        def __destroy_catalog(self):
                """Destroy the catalog."""

                self.__catalog = None
                if self.catalog_root and os.path.exists(self.catalog_root):
                        shutil.rmtree(self.catalog_root)

        @staticmethod
        def __fmri_from_path(pkg, ver):
                """Helper method that takes the full path to the package
                directory and the name of the manifest file, and returns an FMRI
                constructed from the information in those components."""

                v = version.Version(urllib.unquote(ver), None)
                f = fmri.PkgFmri(urllib.unquote(os.path.basename(pkg)))
                f.version = v
                return f

        def _get_manifest(self, pfmri, sig=False):
                """This function should be private; but is protected instead due
                to its usage as a callback."""

                mpath = self.manifest(pfmri)
                m = manifest.Manifest()
                try:
                        f = open(mpath, "rb")
                        content = f.read()
                        f.close()
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                raise RepositoryManifestNotFoundError(
                                    e.filename)
                        raise
                m.set_fmri(None, pfmri)
                m.set_content(content, EmptyI, signatures=sig)
                return m

        def __get_catalog_root(self):
                return self.__catalog_root

        def __get_repo_root(self):
                return self.__repo_root

        def __get_writable_root(self):
                return self.__writable_root

        def __index_log(self, msg):
                return self.__log(msg, "INDEX")

        def __init_config(self, cfgpathname=None, properties=EmptyDict):
                """Private helper function to initialize configuration."""

                # Load configuration information.
                if not cfgpathname:
                        cfgpathname = self.cfgpathname
                self.__load_config(cfgpathname, properties=properties)

                # Set any specified properties again for cases where no existing
                # configuration could be loaded and so that individual property
                # validation messages can be re-raised to caller.
                for section in properties:
                        for prop, value in properties[section].iteritems():
                                self.cfg.set_property(section, prop, value)

        def __init_dirs(self, create=False):
                """Verify and instantiate repository directory structure."""
                if not self.repo_root:
                        return
                emsg = _("repository directories incomplete")
                for d in self.__required_dirs + self.__optional_dirs:
                        if create or self.auto_create or (self.writable_root and
                            d.startswith(self.writable_root)):
                                try:
                                        os.makedirs(d)
                                except EnvironmentError, e:
                                        if e.errno in (errno.EACCES,
                                            errno.EROFS):
                                                emsg = _("repository "
                                                    "directories not writeable "
                                                    "by current user id or "
                                                    "group and are incomplete")
                                        elif e.errno != errno.EEXIST:
                                                raise

                for d in self.__required_dirs:
                        if not os.path.exists(d):
                                if create or self.auto_create:
                                        raise RepositoryError(emsg)
                                raise RepositoryInvalidError(self.repo_root)

                searchdb_file = os.path.join(self.repo_root, "search")
                for ext in ".pag", ".dir":
                        try:
                                os.unlink(searchdb_file + ext)
                        except OSError:
                                # If these can't be removed, it doesn't matter.
                                continue

        def __load_config(self, cfgpathname=None, properties=EmptyDict):
                """Load stored configuration data and configure the repository
                appropriately."""

                if not self.repo_root:
                        self.cfg = RepositoryConfig(target=cfgpathname,
                            overrides=properties)
                        return

                default_cfg_path = False

                # Now load our repository configuration / metadata.
                if not cfgpathname:
                        cfgpathname = os.path.join(self.repo_root,
                            "cfg_cache")
                        default_cfg_path = True

                # Create or load the repository configuration.
                self.cfg = RepositoryConfig(target=cfgpathname,
                    overrides=properties)

                self.cfgpathname = cfgpathname

        def __load_in_flight(self):
                """Walk trans_root, acquiring valid transaction IDs."""

                if self.mirror:
                        # Mirrors don't permit publication.
                        return

                if not self.trans_root:
                        return

                self.__in_flight_trans = {}
                for txn in os.walk(self.trans_root):
                        if txn[0] == self.trans_root:
                                continue
                        t = trans.Transaction()
                        t.reopen(self, txn[0])
                        self.__in_flight_trans[t.get_basename()] = t

        def __lock_repository(self):
                """Locks the repository preventing multiple consumers from
                modifying it during operations."""

                # XXX need filesystem lock too?
                self.__lock.acquire()

        def __log(self, msg, context="", severity=logging.INFO):
                if self.log_obj:
                        self.log_obj.log(msg=msg, context=context,
                            severity=severity)

        def __rebuild(self, lm=None, incremental=False):
                """Private version; caller responsible for repository
                locking."""

                if not self.manifest_root:
                        return

                default_pub = self.cfg.get_property("publisher", "prefix")

                if self.read_only:
                        # Temporarily mark catalog as not read-only so that it
                        # can be modified.
                        self.catalog.read_only = False

                # Set batch_mode for catalog to speed up rebuild.
                self.catalog.batch_mode = True

                # Pointless to log incremental updates since a new catalog
                # is being built.  This also helps speed up rebuild.
                self.catalog.log_updates = incremental

                def add_package(f):
                        m = self._get_manifest(f, sig=True)
                        if "pkg.fmri" in m:
                                f = fmri.PkgFmri(m["pkg.fmri"])
                        if default_pub and not f.publisher:
                                f.publisher = default_pub
                        self.__add_package(f, manifest=m)
                        self.__log(str(f))

                # XXX eschew os.walk in favor of another os.listdir here?
                for pkg in os.walk(self.manifest_root):
                        if pkg[0] == self.manifest_root:
                                continue

                        for e in os.listdir(pkg[0]):
                                f = self.__fmri_from_path(pkg[0], e)
                                try:
                                        add_package(f)
                                except (api_errors.InvalidPackageErrors,
                                    actions.ActionError), e:
                                        # Don't add packages with corrupt
                                        # manifests to the catalog.
                                        self.__log(_("Skipping %(fmri)s; "
                                            "invalid manifest: %(error)s") % {
                                            "fmri": f, "error": e })
                                except api_errors.DuplicateCatalogEntry, e:
                                        # ignore dups if incremental mode
                                        if incremental:
                                                continue
                                        raise

                # Private add_package doesn't automatically save catalog
                # so that operations can be batched (there is significant
                # overhead in writing the catalog).
                self.catalog.batch_mode = False
                self.catalog.log_updates = True
                self.catalog.read_only = self.read_only
                self.catalog.finalize()
                self.__save_catalog(lm=lm)

                if not incremental and self.index_root and \
                    os.path.exists(self.index_root):
                        # Search data is no longer valid and search can't handle
                        # package removal, so discard existing search data.
                        try:
                                shutil.rmtree(self.index_root)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                if e.errno != errno.ENOENT:
                                        raise
                self.__init_dirs(create=True)

        def __refresh_index(self, synchronous=False):
                """Private version; caller responsible for repository
                locking."""

                if not self.index_root:
                        return
                if self.read_only and not self.writable_root:
                        raise RepositoryReadOnlyError()

                self.__searchdb_update_handle_lock.acquire()

                if self.__searchdb_update_handle:
                        self.__refresh_again = True
                        self.__searchdb_update_handle_lock.release()
                        return

                cat = self.catalog
                forked = False

                try:
                        fmris_to_index = indexer.Indexer.check_for_updates(
                            self.index_root, cat)

                        pub = self.cfg.get_property("publisher", "prefix")
                        if fmris_to_index:
                                if os.name == "posix" and self.fork_allowed:
                                        cmd = self.__whence(sys.argv[0])
                                        args = (sys.executable, cmd,
                                            "--refresh-index", "-d",
                                            self.repo_root)
                                        if pub:
                                                args += ("--set-property",
                                                    "publisher.prefix=%s" % pub)
                                        if os.path.normpath(
                                            self.index_root) != \
                                            os.path.normpath(os.path.join(
                                            self.repo_root, "index")):
                                                writ, t = os.path.split(
                                                    self.index_root)
                                                args += ("--writable-root",
                                                    writ)
                                        if self.read_only:
                                                args += ("--readonly",)
                                        try:
                                                self.__searchdb_update_handle = \
                                                    subprocess.Popen(args,
                                                    stderr=subprocess.STDOUT)
                                        except Exception, e:
                                                self.__log("Starting the "
                                                    "indexing process failed: "
                                                    "%s" % e)
                                                raise
                                        forked = True
                                else:
                                        self.run_update_index()
                        else:
                                # Since there is nothing to index, setup
                                # the index and declare search available.
                                # We only log this if this represents
                                # a change in status of the server.
                                ind = indexer.Indexer(self.index_root,
                                    self._get_manifest,
                                    self.manifest,
                                    log=self.__index_log,
                                    sort_file_max_size=self.__sort_file_max_size)
                                ind.setup()
                                if not self.__search_available:
                                        self.__index_log("Search Available")
                                self.__search_available = True
                finally:
                        self.__searchdb_update_handle_lock.release()
                        if forked and synchronous:
                                while self.__searchdb_update_handle is not None:
                                        try:
                                                self.__searchdb_update_handle.wait()
                                                self.__searchdb_update_handle = None
                                        except OSError, e:
                                                if e.errno == errno.EINTR:
                                                        continue
                                                break


        def __init_state(self, refresh_index=True):
                """Private version; caller responsible for repository
                locking."""

                # Discard current catalog information (it will be re-loaded
                # when needed).
                self.__catalog = None

                # Load in-flight transaction information.
                self.__load_in_flight()

                # Ensure default configuration is written.
                self.__write_config()

                # Ensure repository state is current before attempting
                # to load it.
                self.__upgrade()

                if self.mirror or not self.repo_root:
                        # In mirror-mode, or no repo_root, nothing to do.
                        return

                # If no catalog exists on-disk yet, ensure an empty one does
                # so that clients can discern that a repository has an empty
                # empty catalog, as opposed to missing one entirely (which
                # could easily happen with multiple origins).  This must be
                # done before the search checks below.
                if not self.read_only and not self.catalog.exists:
                        self.catalog.save()

                if refresh_index and not self.read_only or self.writable_root:
                        try:
                                try:
                                        self.__refresh_index()
                                except se.InconsistentIndexException, e:
                                        s = _("Index corrupted or out of date. "
                                            "Removing old index directory (%s) "
                                            " and rebuilding search "
                                            "indexes.") % e.cause
                                        self.__log(s, "INDEX")
                                        shutil.rmtree(self.index_root)
                                        try:
                                                self.__refresh_index()
                                        except se.IndexingException, e:
                                                self.__log(str(e), "INDEX")
                                except se.IndexingException, e:
                                        self.__log(str(e), "INDEX")
                        except EnvironmentError, e:
                                if e.errno in (errno.EACCES, errno.EROFS):
                                        if self.writable_root:
                                                raise RepositoryError(
                                                    _("writable root not "
                                                    "writable by current user "
                                                    "id or group."))
                                        raise RepositoryError(_("unable to "
                                            "write to index directory."))
                                raise
                else:
                        self.__check_search()

        def __save_catalog(self, lm=None):
                """Private helper function that attempts to save the catalog in
                an atomic fashion."""

                # Ensure new catalog is created in a temporary location so that
                # it can be renamed into place *after* creation to prevent
                # unexpected failure from causing future upgrades to fail.
                old_cat_root = self.catalog_root
                tmp_cat_root = self.__mkdtemp()

                try:
                        if os.path.exists(old_cat_root):
                                # Now remove the temporary directory and then
                                # copy the contents of the existing catalog
                                # directory to the new, temporary name.  This
                                # is necessary since the catalog only saves the
                                # data that has been loaded or changed, so new
                                # parts will get written out, but old ones could
                                # be lost.
                                shutil.rmtree(tmp_cat_root)
                                shutil.copytree(old_cat_root, tmp_cat_root)

                        # Ensure the permissions on the new temporary catalog
                        # directory are correct.
                        os.chmod(tmp_cat_root, misc.PKG_DIR_MODE)
                except EnvironmentError, e:
                        # shutil.Error can contains a tuple of lists of errors.
                        # Some of the error entries may be a tuple others will
                        # be a string due to poor error handling in shutil.
                        if isinstance(e, shutil.Error) and \
                            type(e.args[0]) == list:
                                msg = ""
                                for elist in e.args:
                                        for entry in elist:
                                                if type(entry) == tuple:
                                                        msg += "%s\n" % \
                                                            entry[-1]
                                                else:
                                                        msg += "%s\n" % entry
                                raise api_errors.UnknownErrors(msg)
                        elif e.errno == errno.EACCES or e.errno == errno.EPERM:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        elif e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                # Save the new catalog data in the temporary location.
                self.catalog_root = tmp_cat_root
                if lm:
                        self.catalog.last_modified = lm
                self.catalog.save()

                orig_cat_root = None
                if os.path.exists(old_cat_root):
                        # Preserve the old catalog data before continuing.
                        orig_cat_root = os.path.join(os.path.dirname(
                            old_cat_root), "old." + os.path.basename(
                            old_cat_root))
                        shutil.move(old_cat_root, orig_cat_root)

                # Finally, rename the new catalog data into place, reset the
                # catalog's location, and remove the old catalog data.
                shutil.move(tmp_cat_root, old_cat_root)
                self.catalog_root = old_cat_root
                if orig_cat_root:
                        shutil.rmtree(orig_cat_root)

        def __set_catalog_root(self, root):
                self.__catalog_root = root
                if self.__catalog:
                        # If the catalog is loaded already, then reset
                        # its meta_root.
                        self.catalog.meta_root = root

        def __set_repo_root(self, root):
                if root:
                        root = os.path.abspath(root)
                        self.__repo_root = root
                        self.__tmp_root = os.path.join(root, "tmp")
                        self.catalog_root = os.path.join(root, "catalog")
                        self.feed_cache_root = root
                        self.index_root = os.path.join(root, "index")
                        self.manifest_root = os.path.join(root, "pkg")
                        self.trans_root = os.path.join(root, "trans")
                        if not self.file_root:
                                self.file_root = os.path.join(root, "file")
                else:
                        self.__repo_root = None
                        self.catalog_root = None
                        self.feed_cache_root = None
                        self.index_root = None
                        self.manifest_root = None
                        self.trans_root = None
 
        def __get_file_root(self):
                return self.__file_root

        def __set_file_root(self, root):
                self.__file_root = root
                try:
                        self.cache_store = file_manager.FileManager(root,
                            self.read_only)
                except file_manager.NeedToModifyReadOnlyFileManager:
                        if self.repo_root:
                                try:
                                        fs = os.lstat(self.repo_root)
                                except OSError, e:
                                        # If the stat failed due to this, then
                                        # assume the repository is possibly
                                        # valid but that there is a permissions
                                        # issue.
                                        if e.errno == errno.EACCES:
                                                raise api_errors.\
                                                    PermissionsException(
                                                    e.filename)
                                        if e.errno == errno.ENOENT:
                                                raise RepositoryInvalidError(
                                                    self.repo_root)
                                        raise
                                # If the stat succeeded, then regardless of
                                # whether repo_root is really a directory, the
                                # repository is invalid.
                                raise RepositoryInvalidError(self.repo_root)
                        # If repository root hasn't been specified yet,
                        # just raise the error with the path that is available.
                        raise RepositoryInvalidError(root)

        def __set_writable_root(self, root):
                if root:
                        root = os.path.abspath(root)
                        self.__tmp_root = os.path.join(root, "tmp")
                        self.feed_cache_root = root
                        self.index_root = os.path.join(root, "index")
                elif self.repo_root:
                        self.__tmp_root = os.path.join(self.repo_root, "tmp")
                        self.feed_cache_root = self.repo_root
                        self.index_root = os.path.join(self.repo_root, "index")
                else:
                        self.__tmp_root = None
                        self.feed_cache_root = None
                        self.index_root = None
                self.__writable_root = root

        def __unlock_repository(self):
                """Unlocks the repository so other consumers may modify it."""

                # XXX need filesystem unlock too?
                self.__lock.release()

        def __update_searchdb_unlocked(self, fmris):
                """ Creates an indexer then hands it fmris It assumes that all
                needed locking has already occurred.
                """
                assert self.index_root

                if fmris:
                        index_inst = indexer.Indexer(self.index_root,
                            self._get_manifest, self.manifest,
                            log=self.__index_log,
                            sort_file_max_size=self.__sort_file_max_size)
                        index_inst.server_update_index(fmris)

        @staticmethod
        def __whence(cmd):
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

        def __write_config(self):
                """Save the repository's current configuration data."""

                # No changes should be written to disk in readonly mode.
                if self.read_only:
                        return

                # Save a new configuration (or refresh existing).
                try:
                        self.cfg.write()
                except EnvironmentError, e:
                        # If we're unable to write due to the following
                        # errors, it isn't critical to the operation of
                        # the repository.
                        if e.errno not in (errno.EPERM, errno.EACCES,
                            errno.EROFS):
                                raise

        def abandon(self, trans_id):
                """Aborts a transaction with the specified Transaction ID.
                Returns the current package state."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        try:
                                t = self.__in_flight_trans[trans_id]
                        except KeyError:
                                raise RepositoryInvalidTransactionIDError(
                                    trans_id)

                        try:
                                pstate = t.abandon()
                                del self.__in_flight_trans[trans_id]
                                return pstate
                        except trans.TransactionError, e:
                                raise RepositoryError(e)
                finally:
                        self.__unlock_repository()

        def add(self, trans_id, action):
                """Adds an action and its content to a transaction with the
                specified Transaction ID."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        try:
                                t = self.__in_flight_trans[trans_id]
                        except KeyError:
                                raise RepositoryInvalidTransactionIDError(
                                    trans_id)

                        try:
                                t.add_content(action)
                        except trans.TransactionError, e:
                                raise RepositoryError(e)
                finally:
                        self.__unlock_repository()

        def add_package(self, pfmri):
                """Adds the specified FMRI to the repository's catalog."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        self.__add_package(pfmri)
                        self.__save_catalog()
                finally:
                        self.__unlock_repository()

        @property
        def catalog(self):
                """Returns the Catalog object for the repository's catalog."""

                if self.__catalog:
                        # Already loaded.
                        return self.__catalog

                if self.mirror:
                        raise RepositoryMirrorError()

                self.__catalog = catalog.Catalog(meta_root=self.catalog_root,
                    log_updates=True, read_only=self.read_only)
                return self.__catalog

        def catalog_0(self):
                """Returns a generator object for the full version of
                the catalog contents.  Incremental updates are not provided
                as the v0 updatelog does not support renames, obsoletion,
                package removal, etc."""

                if not self.catalog_root:
                        raise RepositoryUnsupportedOperationError()

                c = self.catalog
                self.inc_catalog()

                # Yield each catalog attr in the v0 format:
                # S Last-Modified: 2009-08-28T15:01:48.546606
                # S prefix: CRSV
                # S npkgs: 46292
                yield "S Last-Modified: %s\n" % c.last_modified.isoformat()
                yield "S prefix: CRSV\n"
                yield "S npkgs: %s\n" % c.package_version_count

                # Now yield each FMRI in the catalog in the v0 format:
                # V pkg:/SUNWdvdrw@5.21.4.10.8,5.11-0.86:20080426T173208Z
                for pub, stem, ver in c.tuples():
                        yield "V pkg:/%s@%s\n" % (stem, ver)

        def catalog_1(self, name):
                """Returns the absolute pathname of the named catalog file."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.catalog_root:
                        raise RepositoryUnsupportedOperationError()

                assert name
                self.inc_catalog()

                return os.path.normpath(os.path.join(self.catalog_root, name))

        def close(self, trans_id, refresh_index=True, add_to_catalog=True):
                """Closes the transaction specified by 'trans_id'.

                Returns a tuple containing the package FMRI and the current
                package state in the catalog."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                try:
                        t = self.__in_flight_trans[trans_id]
                except KeyError:
                        raise RepositoryInvalidTransactionIDError(trans_id)

                try:
                        pfmri, pstate = t.close(refresh_index=refresh_index,
                        add_to_catalog=add_to_catalog)
                        del self.__in_flight_trans[trans_id]
                        return pfmri, pstate
                except (api_errors.CatalogError, trans.TransactionError), e:
                        raise RepositoryError(e)

        def file(self, fhash):
                """Returns the absolute pathname of the file specified by the
                provided SHA1-hash name."""

                self.inc_file()

                if fhash is None:
                        raise RepositoryFileNotFoundError(fhash)

                fp = self.cache_store.lookup(fhash)
                if fp is not None:
                        return fp
                raise RepositoryFileNotFoundError(fhash)

        @property
        def in_flight_transactions(self):
                """The number of transactions awaiting completion."""
                return len(self.__in_flight_trans)

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

        def manifest(self, pfmri):
                """Returns the absolute pathname of the manifest file for the
                specified FMRI."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.inc_manifest()

                try:
                        if not isinstance(pfmri, fmri.PkgFmri):
                                pfmri = fmri.PkgFmri(pfmri)
                        fpath = pfmri.get_dir_path()
                except fmri.FmriError, e:
                        raise RepositoryInvalidFMRIError(e)

                return os.path.join(self.manifest_root, fpath)

        def open(self, client_release, pfmri):
                """Starts a transaction for the specified client release and
                FMRI.  Returns the Transaction ID for the new transaction."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        try:
                                t = trans.Transaction()
                                t.open(self, client_release, pfmri)
                                self.__in_flight_trans[t.get_basename()] = t
                                return t.get_basename()
                        except trans.TransactionError, e:
                                raise RepositoryError(e)
                finally:
                        self.__unlock_repository()

        def refresh_index(self):
                """ This function refreshes the search indexes if there any new
                packages.  It starts a subprocess which results in a call to
                run_update_index (see below) which does the actual update."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        self.__refresh_index()
                finally:
                        self.__unlock_repository()

        def add_content(self, refresh_index=True):
                """Looks for packages added to the repository that are not in
                the catalog, adds them, and then updates search data by default.
                """
                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        self.__check_search()
                        self.__rebuild(incremental=True)
                        if refresh_index:
                                self.__refresh_index(synchronous=True)
                finally:
                        self.__unlock_repository()

        def rebuild(self, build_index=True):
                """Rebuilds the repository catalog and search indexes using the
                package manifests currently in the repository.

                'build_index' is an optional boolean value indicating whether
                search indexes should be built.  Regardless of this value, any
                existing search data will be discarded.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_repository()
                try:
                        self.__destroy_catalog()
                        self.__init_dirs(create=True)
                        self.__check_search()
                        self.__rebuild()
                        if build_index:
                                self.__refresh_index()
                finally:
                        self.__unlock_repository()

        def reload(self, cfgpathname=None, properties=EmptyDict):
                """Reloads the repository state information from disk."""

                self.__lock_repository()
                self.__init_config(cfgpathname=cfgpathname,
                    properties=properties)
                self.__init_state()
                self.__unlock_repository()

        def run_update_index(self):
                """ Determines which fmris need to be indexed and passes them
                to the indexer.

                Note: Only one instance of this method should be running.
                External locking is expected to ensure this behavior. Calling
                refresh index is the preferred method to use to reindex.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.index_root:
                        raise RepositoryUnsupportedOperationError()

                c = self.catalog
                fmris_to_index = indexer.Indexer.check_for_updates(
                    self.index_root, c)

                if fmris_to_index:
                        self.__index_log("Updating search indexes")
                        self.__update_searchdb_unlocked(fmris_to_index)
                else:
                        ind = indexer.Indexer(self.index_root,
                            self._get_manifest, self.manifest,
                            log=self.__index_log,
                            sort_file_max_size=self.__sort_file_max_size)
                        ind.setup()

        def search(self, queries):
                """Searches the index for each query in the list of queries.
                Each entry should be the output of str(Query), or a Query
                object."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.index_root:
                        raise RepositoryUnsupportedOperationError()

                def _search(q):
                        assert self.index_root
                        l = sqp.QueryLexer()
                        l.build()
                        qp = sqp.QueryParser(l)
                        query = qp.parse(q.text)
                        query.set_info(num_to_return=q.num_to_return,
                            start_point=q.start_point,
                            index_dir=self.index_root,
                            get_manifest_path=self.manifest,
                            case_sensitive=q.case_sensitive)
                        return query.search(c.fmris)

                c = self.catalog
                query_lst = []
                try:
                        for s in queries:
                                if not isinstance(s, qp.Query):
                                        query_lst.append(
                                            sqp.Query.fromstr(s))
                                else:
                                        query_lst.append(s)
                except sqp.QueryException, e:
                        raise RepositoryError(e)
                return [_search(q) for q in query_lst]

        @property
        def search_available(self):
                return self.__search_available or self.__check_search()

        def valid_new_fmri(self, pfmri):
                """Check that the FMRI supplied as an argument would be valid
                to add to the repository catalog.  This checks to make sure
                that any past catalog operations (such as a rename or freeze)
                would not prohibit the caller from adding this FMRI."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.repo_root:
                        raise RepositoryUnsupportedOperationError()
                if not fmri.is_valid_pkg_name(pfmri.get_name()):
                        return False
                if not pfmri.version:
                        return False

                c = self.catalog
                entry = c.get_entry(pfmri)
                return entry is None

        def write_config(self):
                """Save the repository's current configuration data."""

                self.__lock_repository()
                try:
                        self.__write_config()
                finally:
                        self.__unlock_repository()

        catalog_root = property(__get_catalog_root, __set_catalog_root)
        file_root = property(__get_file_root, __set_file_root)
        repo_root = property(__get_repo_root, __set_repo_root)
        writable_root = property(__get_writable_root, __set_writable_root)


class RepositoryConfig(object):
        """Returns an object representing a configuration interface for a
        a pkg(5) repository.

        The class of the object returned will depend upon the specified
        configuration target (which is used as to retrieve and store
        configuration data).

        'target' is the optional location to retrieve existing configuration
        data or store the configuration data when requested.  The location
        can be the pathname of a file or an SMF FMRI.  If a pathname is
        provided, and does not exist, it will be created.

        'overrides' is a dictionary of property values indexed by section name
        and property name.  If provided, it will override any values read from
        an existing file or any defaults initially assigned.

        'version' is an integer value specifying the set of configuration data
        to use for the operation.  If not provided, the version will be based
        on the target if supported.  If a version cannot be determined, the
        newest version will be assumed.
        """

        # This dictionary defines the set of default properties and property
        # groups for a repository configuration indexed by version.
        __defs = {
            3: [
                cfg.PropertySection("publisher", [
                    cfg.PropPublisher("alias"),
                    cfg.PropPublisher("prefix"),
                ]),
                cfg.PropertySection("repository", [
                    cfg.PropDefined("collection_type", ["core",
                        "supplemental"], default="core"),
                    cfg.PropDefined("description"),
                    cfg.PropPubURI("detailed_url"),
                    cfg.PropPubURIList("legal_uris"),
                    cfg.PropDefined("maintainer"),
                    cfg.PropPubURI("maintainer_url"),
                    cfg.PropPubURIList("mirrors"),
                    cfg.PropDefined("name",
                        default="package repository"),
                    cfg.PropPubURIList("origins"),
                    cfg.PropInt("refresh_seconds", default=14400),
                    cfg.PropPubURI("registration_uri"),
                    cfg.PropPubURIList("related_uris"),
                ]),
                cfg.PropertySection("feed", [
                    cfg.PropUUID("id"),
                    cfg.PropDefined("name",
                        default="package repository feed"),
                    cfg.PropDefined("description"),
                    cfg.PropDefined("icon", allowed=["", "<pathname>"],
                        default="web/_themes/pkg-block-icon.png"),
                    cfg.PropDefined("logo", allowed=["", "<pathname>"],
                        default="web/_themes/pkg-block-logo.png"),
                    cfg.PropInt("window", default=24),
                ]),
            ],
        }

        def __new__(cls, target=None, overrides=misc.EmptyDict, version=None):
                if not target:
                        return cfg.Config(definitions=cls.__defs,
                            overrides=overrides, version=version)
                elif target.startswith("svc:"):
                        return cfg.SMFConfig(target, definitions=cls.__defs,
                            overrides=overrides, version=version)
                return cfg.FileConfig(target, definitions=cls.__defs,
                    overrides=overrides, version=version)

def repository_create(repo_uri):
        """Create a repository at given location and return the Repository
        object for the new repository.  If the repository already exists,
        a RepositoryExistsError will be raised.  Other errors can raise
        exceptions of class ApiException.
        """

        path = repo_uri.get_pathname()
        if not path:
                # Bad URI?
                raise RepositoryInvalidError(str(repo_uri))

        try:
                Repository(auto_create=False, read_only=True, repo_root=path)
        except RepositoryInvalidError:
                # No valid repository found; so create one.
                repo = Repository(auto_create=True, repo_root=path)
                assert os.path.exists(repo.repo_root)
                return repo
        # A repository isn't supposed to exist at this location.
        raise RepositoryExistsError(path)
