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
# Copyright (c) 2008, 2011, Oracle and/or its affiliates. All rights reserved.

import cStringIO
import codecs
import datetime
import errno
import logging
import os
import os.path
import platform
import shutil
import stat
import sys
import tempfile
import urllib

import pkg.actions as actions
import pkg.catalog as catalog
import pkg.client.api_errors as apx
import pkg.client.progress as progress
import pkg.client.publisher as publisher
import pkg.config as cfg
import pkg.file_layout.file_manager as file_manager
import pkg.fmri as fmri
import pkg.indexer as indexer
import pkg.lockfile as lockfile
import pkg.manifest
import pkg.p5i as p5i
import pkg.portable as portable
import pkg.misc as misc
import pkg.nrlock
import pkg.search_errors as se
import pkg.query_parser as qp
import pkg.server.catalog as old_catalog
import pkg.server.query_parser as sqp
import pkg.server.transaction as trans
import pkg.version

CURRENT_REPO_VERSION = 4
from pkg.pkggzip import PkgGzipFile

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
                return _("A package repository (or a directory with content) "
                    "already exists at '%s'.") % self.data


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
                if not self.data:
                        return _("The specified path does not contain a valid "
                            "package repository.")
                return _("The path '%s' does not contain a valid package "
                    "repository.") % self.data


class RepositoryInvalidFMRIError(RepositoryError):
        """Used to indicate that the FMRI provided is invalid."""


class RepositoryUnqualifiedFMRIError(RepositoryError):
        """Used to indicate that the FMRI provided is valid, but is missing
        publisher information."""

        def __str__(self):
                return _("This operation requires that a default publisher has "
                    "been set or that a publisher be specified in the FMRI "
                    "'%s'.") % self.data


class RepositoryInvalidTransactionIDError(RepositoryError):
        """Used to indicate that an invalid Transaction ID was supplied."""

        def __str__(self):
                return _("No transaction matching '%s' could be found.") % \
                    self.data


class RepositoryLockedError(RepositoryError):
        """Used to indicate that the repository is currently locked by another
        thread or process and cannot be modified."""

        def __init__(self, hostname=None, pid=None):
                RepositoryError.__init__(self)
                self.hostname = hostname
                self.pid = pid

        def __str__(self):
                if self.pid is not None:
                        # Even if the host is none, use this message.
                        return _("The repository cannot be modified as it is "
                            "currently in use by another process: "
                            "pid %(pid)s on %(host)s.") % {
                            "pid": self.pid, "host": self.hostname }
                return _("The repository cannot be modified as it is currently "
                    "in use by another process.")


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


class RepositoryNoPublisherError(RepositoryError):
        """Used to indicate that the requested repository operation could not be
        completed as not default publisher has been set and one was not
        specified.
        """

        def __str__(self):
                return _("The requested operation could not be completed as a "
                    "default publisher has not been configured.")


class RepositoryNoSuchFileError(RepositoryError):
        """Used to indicate that the file provided does not exist."""

        def __str__(self):
                return _("No such file '%s'.") % self.data


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


class RepositoryDuplicatePublisher(RepositoryError):
        """Raised when the publisher specified for an operation already exists,
        and so cannot be added again.
        """

        def __str__(self):
                return _("Publisher '%s' already exists.") % self.data


class RepositoryUnknownPublisher(RepositoryError):
        """Raised when the publisher specified for an operation is unknown to
        the repository.
        """

        def __str__(self):
                if not self.data:
                        return _("No publisher was specified or no default "
                            "publisher has been configured for the repository.")
                return _("No publisher matching '%s' could be found.") % \
                    self.data


class RepositoryVersionError(RepositoryError):
        """Raised when the repository specified uses an unsupported format
        (version).
        """

        def __init__(self, location, version):
                RepositoryError.__init__(self)
                self.location = location
                self.version = version

        def __str__(self):
                return("The repository at '%(location)s' is version "
                    "'%(version)s'; only versions up to are supported.") % \
                    self.__dict__


class RepositoryUnsupportedOperationError(RepositoryError):
        """Raised when the repository is unable to support an operation,
        based upon its current configuration.
        """

        def __str__(self):
                return("Operation not supported for this configuration.")


class _RepoStore(object):
        """The _RepoStore object provides an interface for performing operations
        on a set of package data contained within a repository.  This class is
        intended only for use by the Repository class.
        """

        def __init__(self, file_root=None, log_obj=None, mirror=False, pub=None,
            read_only=False, root=None,
            sort_file_max_size=indexer.SORT_FILE_MAX_SIZE, writable_root=None):
                """Prepare the repository for use."""

                self.__catalog = None
                self.__catalog_root = None
                self.__file_root = None
                self.__in_flight_trans = {}
                self.__read_only = read_only
                self.__root = None
                self.__sort_file_max_size = sort_file_max_size
                self.__tmp_root = None
                self.__writable_root = None
                self.cache_store = None
                self.catalog_version = -1
                self.manifest_root = None
                self.trans_root = None

                self.log_obj = log_obj
                self.mirror = mirror
                self.publisher = pub

                # Set before root, since it's possible to have the
                # file_root in an entirely different location.  The root
                # will govern file_root, if a value for file_root is not
                # supplied.
                if file_root:
                        self.__set_file_root(file_root)

                # Must be set before remaining roots.
                self.__set_root(root)

                # Ideally, callers would just specify overrides for the feed
                # cache root, index_root, etc.  But this must be set after all
                # of the others above.
                self.__set_writable_root(writable_root)

                self.__search_available = False
                self.__refresh_again = False

                self.__lock = pkg.nrlock.NRLock()
                if self.__tmp_root:
                        self.__lockfile = lockfile.LockFile(os.path.join(
                            self.__tmp_root, "lock"),
                            set_lockstr=lockfile.generic_lock_set_str,
                            get_lockstr=lockfile.generic_lock_get_str,
                            failure_exc=RepositoryLockedError,
                            provide_mutex=False)
                else:
                        self.__lockfile = None

                # Initialize.
                self.__lock_rstore(blocking=True)
                try:
                        self.__init_state()
                finally:
                        self.__unlock_rstore()

        def __set_read_only(self, value):
                self.__read_only = value
                if self.__catalog:
                        self.__catalog.read_only = value

        def __mkdtemp(self):
                """Create a temp directory under repository directory for
                various purposes."""

                if not self.root:
                        return

                if self.writable_root:
                        root = self.writable_root
                else:
                        root = self.root

                tempdir = os.path.normpath(os.path.join(root, "tmp"))
                misc.makedirs(tempdir)
                try:
                        return tempfile.mkdtemp(dir=tempdir)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        def __add_package(self, pfmri, manifest=None):
                """Private version; caller responsible for repository
                locking."""

                if not manifest:
                        manifest = self._get_manifest(pfmri, sig=True)
                c = self.catalog
                c.add_package(pfmri, manifest=manifest)

        def __replace_package(self, pfmri, manifest=None):
                """Private version; caller responsible for repository
                locking."""

                if not manifest:
                        manifest = self._get_manifest(pfmri, sig=True)
                c = self.catalog
                c.remove_package(pfmri)
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
                        if not self.__search_available:
                                # State change to available.
                                self.__index_log("Search Available")
                                self.reset_search()
                        self.__search_available = True
                else:
                        if self.__search_available:
                                # State change to unavailable.
                                self.__index_log("Search Unavailable")
                                self.reset_search()
                        self.__search_available = False

        def __destroy_catalog(self):
                """Destroy the catalog."""

                self.__catalog = None
                if self.catalog_root and os.path.exists(self.catalog_root):
                        shutil.rmtree(self.catalog_root)

        @staticmethod
        def __fmri_from_path(pkgpath, ver):
                """Helper method that takes the full path to the package
                directory and the name of the manifest file, and returns an FMRI
                constructed from the information in those components."""

                v = pkg.version.Version(urllib.unquote(ver), None)
                f = fmri.PkgFmri(urllib.unquote(os.path.basename(pkgpath)))
                f.version = v
                return f

        def _get_manifest(self, pfmri, sig=False):
                """This function should be private; but is protected instead due
                to its usage as a callback."""

                mpath = self.manifest(pfmri)
                m = pkg.manifest.Manifest(pfmri)
                try:
                        m.set_content(pathname=mpath, signatures=sig)
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                raise RepositoryManifestNotFoundError(
                                    e.filename)
                        raise
                return m

        def __index_log(self, msg):
                return self.__log(msg, "INDEX")

        def __get_transaction(self, trans_id):
                """Return the in-flight transaction with the matching trans_id.
                """

                if not self.trans_root:
                        raise RepositoryInvalidTransactionIDError(trans_id)

                try:
                        return self.__in_flight_trans[trans_id]
                except KeyError:
                        # Transaction not cached already, so load and
                        # cache if possible.
                        t = trans.Transaction()
                        try:
                                t.reopen(self, trans_id)
                        except trans.TransactionUnknownIDError:
                                raise RepositoryInvalidTransactionIDError(
                                    trans_id)

                        if not t:
                                raise RepositoryInvalidTransactionIDError(
                                    trans_id)
                        self.__in_flight_trans[trans_id] = t
                        return t

        def __discard_transaction(self, trans_id):
                """Discard any state information cached for a Transaction."""
                self.__in_flight_trans.pop(trans_id, None)

        def get_lock_status(self):
                """Returns a tuple of booleans of the form (storage_locked,
                index_locked).
                """

                storage_locked = False
                try:
                        self.__lock_rstore()
                except RepositoryLockedError:
                        storage_locked = True
                except:
                        pass
                else:
                        self.__unlock_rstore()

                index_locked = False
                if self.index_root and os.path.exists(self.index_root) and \
                    (not self.read_only or self.writable_root):
                        try:
                                ind = indexer.Indexer(self.index_root,
                                    self._get_manifest, self.manifest,
                                    log=self.__index_log,
                                    sort_file_max_size=self.__sort_file_max_size)
                                ind.lock(blocking=False)
                        except se.IndexLockedException:
                                index_locked = True
                        except:
                                pass
                        finally:
                                if ind and not index_locked:
                                        # If ind is defined, the index exists,
                                        # and a lock was obtained because
                                        # index_locked is False, so call
                                        # unlock().
                                        ind.unlock()
                return storage_locked, index_locked

        def get_status(self):
                """Return a dictionary of status information about the
                repository storage object.
                """

                try:
                        cat = self.catalog
                        pkg_count = cat.package_count
                        pkg_ver_count = cat.package_version_count
                        lcat_update = catalog.datetime_to_basic_ts(
                            cat.last_modified)
                except:
                        # Can't get the info, drive on.
                        pkg_count = 0
                        pkg_ver_count = 0
                        lcat_update = ""

                storage_locked, index_locked = self.get_lock_status()
                if storage_locked:
                        rstatus = "processing"
                elif index_locked:
                        rstatus = "indexing"
                else:
                        rstatus = "online"

                return {
                    "package-count": pkg_count,
                    "package-version-count": pkg_ver_count,
                    "last-catalog-update": lcat_update,
                    "status": rstatus,
                }

        def __lock_rstore(self, blocking=False, process=True):
                """Locks the repository preventing multiple consumers from
                modifying it during operations."""

                # First, attempt to obtain a thread lock.
                if not self.__lock.acquire(blocking=blocking):
                        raise RepositoryLockedError()

                if not process or (self.read_only and
                    not self.writable_root) or not (self.__tmp_root and
                    os.path.exists(self.__tmp_root)):
                        # Process lock wasn't desired, or repository structure
                        # doesn't exist yet or is readonly so a file lock cannot
                        # be obtained.
                        return

                try:
                        # Attempt to obtain a file lock.
                        self.__lockfile.lock(blocking=blocking)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                self.__lock.release()
                                raise apx.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                self.__lock.release()
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)

                        self.__lock.release()
                        raise
                except:
                        # If process lock fails, ensure thread lock is released.
                        self.__lock.release()
                        raise

        def __log(self, msg, context="", severity=logging.INFO):
                if self.log_obj:
                        self.log_obj.log(msg=msg, context=context,
                            severity=severity)

        def __purge_search_index(self):
                """Private helper function to dump repository search data."""

                if not self.index_root or not os.path.exists(self.index_root):
                        return

                ind = indexer.Indexer(self.index_root,
                    self._get_manifest,
                    self.manifest,
                    log=self.__index_log,
                    sort_file_max_size=self.__sort_file_max_size)

                # To prevent issues with NFS consumers, attempt to lock the
                # index first, but don't hold the lock as holding a lock while
                # removing the directory containing it can cause rmtree() to
                # fail.
                ind.lock(blocking=False)
                ind.unlock()

                # Since the lock succeeded, immediately try to rename the index
                # directory to prevent other consumers from using the index
                # while it is being removed since a lock can't be held.
                portable.rename(self.index_root, self.index_root + ".old")
                try:
                        shutil.rmtree(self.index_root + ".old")
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        if e.errno != errno.ENOENT:
                                raise

                # Discard in-memory search data.
                self.reset_search()

        def __rebuild(self, build_catalog=True, build_index=False, lm=None,
            incremental=False):
                """Private version; caller responsible for repository
                locking."""

                if not (build_catalog or build_index) or not self.manifest_root:
                        # Nothing to do.
                        return

                if build_catalog:
                        if not incremental:
                                self.__destroy_catalog()
                        default_pub = self.publisher
                        if self.read_only:
                                # Temporarily mark catalog as not read-only so
                                # that it can be modified.
                                self.catalog.read_only = False

                        # Set batch_mode for catalog to speed up rebuild.
                        self.catalog.batch_mode = True

                        # Pointless to log incremental updates since a new 
                        # catalog is being built.  This also helps speed up
                        # rebuild.
                        self.catalog.log_updates = incremental

                        def add_package(f):
                                m = self._get_manifest(f, sig=True)
                                if "pkg.fmri" in m:
                                        f = fmri.PkgFmri(m["pkg.fmri"])
                                if default_pub and not f.publisher:
                                        f.publisher = default_pub
                                self.__add_package(f, manifest=m)
                                self.__log(str(f))

                        # XXX eschew os.walk in favor of another os.listdir
                        # here?
                        for pkgpath in os.walk(self.manifest_root):
                                if pkgpath[0] == self.manifest_root:
                                        continue

                                for fname in os.listdir(pkgpath[0]):
                                        try:
                                                f = self.__fmri_from_path(
                                                    pkgpath[0], fname)
                                                add_package(f)
                                        except (apx.InvalidPackageErrors,
                                            actions.ActionError,
                                            fmri.FmriError,
                                            pkg.version.VersionError), e:
                                                # Don't add packages with
                                                # corrupt manifests to the
                                                # catalog.
                                                name = os.path.join(pkgpath[0],
                                                    fname)
                                                self.__log(_("Skipping "
                                                    "%(name)s; invalid "
                                                    "manifest: %(error)s") % {
                                                    "name": name, "error": e })
                                        except apx.DuplicateCatalogEntry, e:
                                                # Raise dups if not in
                                                # incremental mode.
                                                if not incremental:
                                                        raise

                        # Private add_package doesn't automatically save catalog
                        # so that operations can be batched (there is
                        # significant overhead in writing the catalog).
                        self.catalog.batch_mode = False
                        self.catalog.log_updates = True
                        self.catalog.read_only = self.read_only
                        self.catalog.finalize()
                        self.__save_catalog(lm=lm)

                if not incremental:
                        # Only discard search data if this isn't an incremental
                        # rebuild.
                        self.__purge_search_index()

                if build_index:
                        self.__refresh_index()
                else:
                        self.__check_search()

        def __refresh_index(self):
                """Private version; caller responsible for repository
                locking."""

                if not self.index_root:
                        return
                if self.read_only and not self.writable_root:
                        raise RepositoryReadOnlyError()

                cat = self.catalog
                self.__index_log("Checking for updated package data.")
                fmris_to_index = indexer.Indexer.check_for_updates(
                    self.index_root, cat)

                if fmris_to_index:
                        return self.__run_update_index()

                # Since there is nothing to index, setup the index
                # and declare search available.  This is only logged
                # if this represents a change in status of the server.
                ind = indexer.Indexer(self.index_root,
                    self._get_manifest,
                    self.manifest,
                    log=self.__index_log,
                    sort_file_max_size=self.__sort_file_max_size)
                ind.setup()
                if not self.__search_available:
                        self.__index_log("Search Available")
                self.__search_available = True

        def __init_state(self):
                """Private version; caller responsible for repository
                locking."""

                # Discard current catalog information (it will be re-loaded
                # when needed).
                self.__catalog = None

                # Determine location and version of catalog data.
                self.__init_catalog()

                # Prepare search for use (ensuring most current data is loaded).
                self.reset_search()

                if self.mirror:
                        # In mirror mode, nothing more to do.
                        return

                # If no catalog exists on-disk yet, ensure an empty one does
                # so that clients can discern that a repository has an empty
                # catalog, as opposed to missing one entirely (which could
                # easily happen with multiple origins).  This must be done
                # before the search checks below.
                if not self.read_only and self.catalog_root and \
                    not self.catalog.exists:
                        self.__save_catalog()

                self.__check_search()

        def __init_catalog(self):
                """Private function to determine version and location of
                catalog data.  This will also perform any necessary
                transformations of existing catalog data if the repository
                is read-only and a writable_root has been provided.
                """

                # Reset versions to default.
                self.catalog_version = -1

                if not self.catalog_root or self.mirror:
                        return

                def get_file_lm(pathname):
                        try:
                                mod_time = os.stat(pathname).st_mtime
                        except EnvironmentError, e:
                                if e.errno == errno.ENOENT:
                                        return None
                                raise
                        return datetime.datetime.utcfromtimestamp(mod_time)

                # To determine if a transformation is needed, first check for a
                # v0 catalog attrs file.
                need_transform = False
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
                                need_transform = True

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
                                # previously run with writable-root and
                                # read_only is now being run with only
                                # writable_root.
                                need_transform = True
                elif writ_cat_root and v0_lm and self.read_only:
                        # The catalog lives in the writable_root if a v0 catalog
                        # exists, writ_cat_root is set, and readonly is True.
                        self.__set_catalog_root(writ_cat_root)

                if self.mirror:
                        need_transform = False

                if need_transform and self.read_only and not self.writable_root:
                        # Catalog data can't be transformed.
                        need_transform = False

                if need_transform:
                        # v1 catalog should be destroyed if it exists already.
                        self.catalog.destroy()

                        # Create the transformed catalog.
                        self.__log(_("Transforming repository catalog; this "
                            "process will take some time."))
                        self.__rebuild(lm=v0_lm)

                        if not self.read_only and self.root:
                                v0_cat = os.path.join(self.root,
                                    "catalog", "catalog")
                                for f in v0_attrs, v0_cat:
                                        if os.path.exists(f):
                                                portable.remove(f)

                                # If this fails, it doesn't really matter, but
                                # it should be removed if possible.
                                shutil.rmtree(os.path.join(self.root,
                                    "updatelog"), True)

                # Determine effective catalog version after all transformation
                # work is complete.
                if os.path.exists(v0_attrs):
                        # The only place a v1 catalog should exist, at all, is
                        # either in catalog_root or in a subdirectory of
                        # writable_root if a v0 catalog exists.
                        v1_cat = None
                        # If a writable root was specified, but the repository
                        # is not in read-only mode, then the catalog must not be
                        # stored using the writable root (this is consistent
                        # with the storage of package data in this case).
                        if self.writable_root and self.read_only:
                                writ_cat_root = os.path.join(
                                    self.writable_root, "catalog")
                                v1_cat = catalog.Catalog(
                                    meta_root=writ_cat_root, read_only=True)

                        if v1_cat and v1_cat.exists:
                                self.catalog_version = 1
                                self.__set_catalog_root(v1_cat.meta_root)
                        else:
                                self.catalog_version = 0
                elif self.catalog.exists:
                        self.catalog_version = 1

                if self.catalog_version >= 1 and not self.publisher:
                        # If there's no information available to determine
                        # the publisher identity, then assume it's the first
                        # publisher in this repository store's catalog.
                        # (This is reasonably safe since there should only
                        # ever be one.)
                        pubs = list(p for p in self.catalog.publishers())
                        if pubs:
                                self.publisher = pubs[0]

        def __save_catalog(self, lm=None):
                """Private helper function that attempts to save the catalog in
                an atomic fashion."""

                # Ensure new catalog is created in a temporary location so that
                # it can be renamed into place *after* creation to prevent
                # unexpected failure causing future updates to fail.
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
                                raise apx.UnknownErrors(msg)
                        elif e.errno == errno.EACCES or e.errno == errno.EPERM:
                                raise apx.PermissionsException(
                                    e.filename)
                        elif e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                # Save the new catalog data in the temporary location.
                self.__set_catalog_root(tmp_cat_root)
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
                self.__set_catalog_root(old_cat_root)
                if orig_cat_root:
                        shutil.rmtree(orig_cat_root)

                # Set catalog version.
                self.catalog_version = self.catalog.version

        def __set_catalog_root(self, root):
                self.__catalog_root = root
                if self.__catalog:
                        # If the catalog is loaded already, then reset
                        # its meta_root.
                        self.catalog.meta_root = root

        def __set_root(self, root):
                if root:
                        root = os.path.abspath(root)
                        self.__root = root
                        self.__tmp_root = os.path.join(root, "tmp")
                        self.__set_catalog_root(os.path.join(root, "catalog"))
                        self.index_root = os.path.join(root, "index")
                        self.manifest_root = os.path.join(root, "pkg")
                        self.trans_root = os.path.join(root, "trans")
                        if not self.file_root:
                                self.__set_file_root(os.path.join(root, "file"))
                else:
                        self.__root = None
                        self.__set_catalog_root(None)
                        self.index_root = None
                        self.manifest_root = None
                        self.trans_root = None

        def __set_file_root(self, root):
                self.__file_root = root
                if not root:
                        self.cache_store = None
                        return

                self.cache_store = file_manager.FileManager(root,
                    self.read_only)

        def __set_writable_root(self, root):
                if root:
                        root = os.path.abspath(root)
                        self.__tmp_root = os.path.join(root, "tmp")
                        self.index_root = os.path.join(root, "index")
                elif self.root:
                        self.__tmp_root = os.path.join(self.root, "tmp")
                        self.index_root = os.path.join(self.root,
                            "index")
                else:
                        self.__tmp_root = None
                        self.index_root = None
                self.__writable_root = root

        def __unlock_rstore(self):
                """Unlocks the repository so other consumers may modify it."""

                try:
                        if self.__lockfile:
                                self.__lockfile.unlock()
                finally:
                        self.__lock.release()

        def __update_searchdb_unlocked(self, fmris):
                """Creates an indexer then hands it fmris; it assumes that all
                needed locking has already occurred.
                """
                assert self.index_root

                if fmris:
                        index_inst = indexer.Indexer(self.index_root,
                            self._get_manifest, self.manifest,
                            log=self.__index_log,
                            sort_file_max_size=self.__sort_file_max_size)
                        index_inst.server_update_index(fmris)
                        if not self.__search_available:
                                self.__index_log("Search Available")
                        self.__search_available = True

        def abandon(self, trans_id):
                """Aborts a transaction with the specified Transaction ID.
                Returns the current package state."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.trans_root:
                        raise RepositoryUnsupportedOperationError()

                t = self.__get_transaction(trans_id)
                try:
                        pstate = t.abandon()
                        self.__discard_transaction(trans_id)
                        return pstate
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def add(self, trans_id, action):
                """Adds an action and its content to a transaction with the
                specified Transaction ID."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.trans_root:
                        raise RepositoryUnsupportedOperationError()

                t = self.__get_transaction(trans_id)
                try:
                        t.add_content(action)
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def add_content(self, refresh_index=False):
                """Looks for packages added to the repository that are not in
                the catalog and adds them.

                'refresh_index' is an optional boolean value indicating whether
                search indexes should be updated.
                """
                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.catalog_root or self.catalog_version == 0:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_rstore()
                try:
                        self.__rebuild(build_catalog=True,
                            build_index=refresh_index, incremental=True)
                finally:
                        self.__unlock_rstore()

        def add_file(self, trans_id, data, size=None):
                """Adds a file to an in-flight transaction.

                'trans_id' is the identifier of a transaction that
                the file should be added to.

                'data' is the string object containing the payload of the
                file to add.

                'size' is an optional integer value indicating the size of
                the provided payload.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.trans_root:
                        raise RepositoryUnsupportedOperationError()

                t = self.__get_transaction(trans_id)
                try:
                        t.add_file(data, size)
                except trans.TransactionError, e:
                        raise RepositoryError(e)
                return

        def add_package(self, pfmri):
                """Adds the specified FMRI to the repository's catalog."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.catalog_root or self.catalog_version < 1:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_rstore(blocking=True)
                try:
                        self.__add_package(pfmri)
                        self.__save_catalog()
                finally:
                        self.__unlock_rstore()

        def replace_package(self, pfmri):
                """Replaces the information for the specified FMRI in the
                repository's catalog."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.catalog_root or self.catalog_version < 1:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_rstore(blocking=True)
                try:
                        self.__replace_package(pfmri)
                        self.__save_catalog()
                finally:
                        self.__unlock_rstore()

        @property
        def catalog(self):
                """Returns the Catalog object for the repository's catalog."""

                if self.__catalog:
                        # Already loaded.
                        return self.__catalog

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.catalog_root:
                        # Object not available.
                        raise RepositoryUnsupportedOperationError()
                if self.catalog_version == 0:
                        return old_catalog.ServerCatalog(self.catalog_root,
                            read_only=True, publisher=self.publisher)

                self.__catalog = catalog.Catalog(meta_root=self.catalog_root,
                    log_updates=True, read_only=self.read_only)
                return self.__catalog

        def catalog_0(self):
                """Returns a generator object for the full version of
                the catalog contents.  Incremental updates are not provided
                as the v0 updatelog does not support renames, obsoletion,
                package removal, etc."""

                if not self.catalog_root or self.catalog_version < 0:
                        raise RepositoryUnsupportedOperationError()

                if self.catalog_version == 0:
                        # If catalog is v0, it must be read and returned
                        # directly to the caller.
                        if not self.publisher:
                                raise RepositoryUnsupportedOperationError()
                        c = old_catalog.ServerCatalog(self.catalog_root,
                            read_only=True, publisher=self.publisher)
                        output = cStringIO.StringIO()
                        c.send(output)
                        output.seek(0)
                        for l in output:
                                yield l
                        return

                # For all other cases where the catalog object is available,
                # fake a v0 catalog for the caller's sake.
                c = self.catalog

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
                if not self.catalog_root or self.catalog_version < 1:
                        raise RepositoryUnsupportedOperationError()

                assert name
                return os.path.normpath(os.path.join(self.catalog_root, name))

        def reset_search(self):
                """Discards currenty loaded search data so that it will be
                reloaded the next a search is performed.
                """
                if not self.index_root:
                        # Nothing to do.
                        return
                sqp.TermQuery.clear_cache(self.index_root)

        def close(self, trans_id, add_to_catalog=True):
                """Closes the transaction specified by 'trans_id'.

                Returns a tuple containing the package FMRI and the current
                package state in the catalog."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.trans_root:
                        raise RepositoryUnsupportedOperationError()

                # The repository store should not be locked at this point
                # as transaction will trigger that indirectly through
                # add_package().
                t = self.__get_transaction(trans_id)
                try:
                        pfmri, pstate = t.close(
                            add_to_catalog=add_to_catalog)
                        self.__discard_transaction(trans_id)
                        return pfmri, pstate
                except (apx.CatalogError,
                    trans.TransactionError), e:
                        raise RepositoryError(e)

        def file(self, fhash):
                """Returns the absolute pathname of the file specified by the
                provided SHA1-hash name."""

                if not self.file_root:
                        raise RepositoryUnsupportedOperationError()

                if fhash is None:
                        raise RepositoryFileNotFoundError(fhash)

                fp = self.cache_store.lookup(fhash)
                if fp is not None:
                        return fp
                raise RepositoryFileNotFoundError(fhash)

        def get_publisher(self):
                """Return the Publisher object for this storage object or None
                if not available.
                """

                if not self.publisher:
                        raise RepositoryUnsupportedOperationError()

                if self.root:
                        # Determine if configuration for publisher exists
                        # on-disk already and then return that if it does.
                        p5ipath = os.path.join(self.root, "pub.p5i")
                        if os.path.exists(p5ipath):
                                pubs = p5i.parse(location=p5ipath)
                                if pubs:
                                        # Only expecting one, so only return
                                        # the first.
                                        return pubs[0][0]

                # No p5i exists, or existing one doesn't contain publisher info,
                # so return a stub publisher object.
                return publisher.Publisher(self.publisher)

        def has_transaction(self, trans_id):
                """Returns a boolean value indicating whether the given
                in-flight Transaction ID exists.
                """

                try:
                        self.__get_transaction(trans_id)
                        return True
                except RepositoryInvalidTransactionIDError:
                        return False

        @property
        def in_flight_transactions(self):
                """The number of transactions awaiting completion."""
                return len(self.__in_flight_trans)

        @property
        def locked(self):
                """A boolean value indicating whether the repository is locked.
                """

                return self.__lockfile and self.__lockfile.locked

        def manifest(self, pfmri):
                """Returns the absolute pathname of the manifest file for the
                specified FMRI."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.manifest_root:
                        raise RepositoryUnsupportedOperationError()
                return os.path.join(self.manifest_root, pfmri.get_dir_path())

        def open(self, client_release, pfmri):
                """Starts a transaction for the specified client release and
                FMRI.  Returns the Transaction ID for the new transaction."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.trans_root:
                        raise RepositoryUnsupportedOperationError()

                try:
                        t = trans.Transaction()
                        t.open(self, client_release, pfmri)
                        self.__in_flight_trans[t.get_basename()] = t
                        return t.get_basename()
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def append(self, client_release, pfmri):
                """Starts an append transaction for the specified client
                release and FMRI.  Returns the Transaction ID for the new
                transaction."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.trans_root:
                        raise RepositoryUnsupportedOperationError()

                try:
                        t = trans.Transaction()
                        t.append(self, client_release, pfmri)
                        self.__in_flight_trans[t.get_basename()] = t
                        return t.get_basename()
                except trans.TransactionError, e:
                        raise RepositoryError(e)

        def refresh_index(self):
                """This function refreshes the search indexes if there any new
                packages.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.index_root:
                        raise RepositoryUnsupportedOperationError()

                # Acquire only the thread-lock.  The Indexer has its own
                # process lock.  This allows indexing and publication to occur
                # simultaneously.
                self.__lock_rstore(process=False)
                try:
                        try:
                                try:
                                        self.__refresh_index()
                                except se.InconsistentIndexException, e:
                                        s = _("Index corrupted or out of date. "
                                            "Removing old index directory (%s) "
                                            " and rebuilding search "
                                            "indexes.") % e.cause
                                        self.__log(s, "INDEX")
                                        try:
                                                self.__rebuild(
                                                    build_catalog=False,
                                                    build_index=True)
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
                finally:
                        self.__unlock_rstore()

        def remove_packages(self, packages, progtrack=None):
                """Removes the specified packages from the repository store.  No
                other modifying operations may be performed until complete.

                'packages' is a list of FMRIs of packages to remove.

                'progtrack' is an optional ProgressTracker object.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.catalog_root or self.catalog_version < 1:
                        raise RepositoryUnsupportedOperationError()
                if not self.manifest_root:
                        raise RepositoryUnsupportedOperationError()
                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                def get_hashes(pfmri):
                        """Given an FMRI, return a set containing all of the
                        hashes of the files its manifest references."""

                        m = self._get_manifest(pfmri)
                        hashes = set()
                        for a in m.gen_actions():
                                if not a.has_payload or not a.hash:
                                        # Nothing to archive.
                                        continue

                                # Action payload.
                                hashes.add(a.hash)

                                # Signature actions have additional payloads.
                                if a.name == "signature":
                                        hashes.update(a.attrs.get("chain",
                                            "").split())
                        return hashes

                self.__lock_rstore()
                c = self.catalog
                try:
                        # First, dump all search data as it will be invalidated
                        # as soon as the catalog is updated.
                        progtrack.actions_set_goal(_("Delete search index"), 1)
                        self.__purge_search_index()
                        progtrack.actions_add_progress()
                        progtrack.actions_done()

                        # Next, remove all of the packages to be removed
                        # from the catalog (if they are present).  That way
                        # any active clients are less likely to be surprised
                        # when files for packages start disappearing.
                        progtrack.actions_set_goal(_("Update catalog"), 1)
                        c.batch_mode = True
                        save_catalog = False
                        for pfmri in packages:
                                try:
                                        c.remove_package(pfmri)
                                except apx.UnknownCatalogEntry:
                                        # Assume already removed from catalog or
                                        # not yet added to it.
                                        continue
                                save_catalog = True

                        c.batch_mode = False
                        if save_catalog:
                                # Only need to re-write catalog if at least one
                                # package had to be removed from it.
                                c.finalize(pfmris=packages)
                                c.save()

                        progtrack.actions_add_progress()
                        progtrack.actions_done()

                        # Next, build a list of all of the hashes for the files
                        # that can potentially be removed from the repository.
                        # This will also indirectly abort the operation should
                        # any of the packages not actually have a manifest in
                        # the repository.
                        pfiles = set()
                        progtrack.actions_set_goal(
                            _("Analyze removed packages"), len(packages))
                        for pfmri in packages:
                                pfiles.update(get_hashes(pfmri))
                                progtrack.actions_add_progress()
                        progtrack.actions_done()

                        # Now for the slow part; iterate over every manifest in
                        # the repository (excluding the ones being removed) and
                        # remove any hashes in use from the list to be removed.
                        # However, if the package being removed doesn't have any
                        # payloads, then we can skip checking all of the
                        # packages in the repository for files in use.
                        if pfiles:
                                # Number of packages to check is total found in
                                # repo minus number to be removed.
                                slist = os.listdir(self.manifest_root)
                                remaining = sum(
                                    1
                                    for s in slist
                                    for v in os.listdir(os.path.join(
                                        self.manifest_root, s))
                                )

                                progtrack.actions_set_goal(
                                    _("Analyze repository packages"), remaining)
                                for name in slist:
                                        # Stem must be decoded before use.
                                        try:
                                                pname = urllib.unquote(name)
                                        except Exception:
                                                # Assume error is result of
                                                # unexpected file in directory;
                                                # just skip it and drive on.
                                                continue

                                        pdir = os.path.join(self.manifest_root,
                                            name)
                                        for ver in os.listdir(pdir):
                                                if not pfiles:
                                                        # Skip remaining entries
                                                        # since no files are
                                                        # safe to remove, but
                                                        # update progress.
                                                        progtrack.actions_add_progress()
                                                        continue

                                                # Version must be decoded before
                                                # use.
                                                pver = urllib.unquote(ver)
                                                try:
                                                        pfmri = fmri.PkgFmri(
                                                            "@".join((pname,
                                                            pver)), publisher=self.publisher)
                                                except Exception:
                                                        # Assume error is result
                                                        # of unexpected file in
                                                        # directory; just skip
                                                        # it and drive on.
                                                        progtrack.actions_add_progress()
                                                        continue

                                                if pfmri in packages:
                                                        # Package is one of
                                                        # those queued for
                                                        # removal.
                                                        progtrack.actions_add_progress()
                                                        continue

                                                # Any files in use by another
                                                # package can't be removed.
                                                pfiles -= get_hashes(pfmri)
                                                progtrack.actions_add_progress()
                                progtrack.actions_done()

                        # Next, remove the manifests of the packages to be
                        # removed.  (This is done before removing the files
                        # so that clients won't have a chance to retrieve a
                        # manifest which has missing files.)
                        progtrack.actions_set_goal(
                            _("Remove package manifests"), len(packages))
                        for pfmri in packages:
                                mpath = self.manifest(pfmri)
                                portable.remove(mpath)
                                progtrack.actions_add_progress()
                        progtrack.actions_done()

                        # Next, remove any package files that are not
                        # referenced by other packages.
                        progtrack.actions_set_goal(
                            _("Remove package files"), len(pfiles))
                        for h in pfiles:
                                # File might already be gone (don't care if
                                # it is).
                                fpath = self.cache_store.lookup(h)
                                if fpath is not None:
                                        portable.remove(fpath)
                                        progtrack.actions_add_progress()
                        progtrack.actions_done()

                        # Finally, tidy up repository structure by discarding
                        # unused package data directories for any packages
                        # removed.
                        def rmdir(d):
                                """rmdir; but ignores non-empty directories."""
                                try:
                                        os.rmdir(d)
                                except OSError, e:
                                        if e.errno not in (
                                            errno.ENOTEMPTY,
                                            errno.EEXIST):
                                                raise

                        for name in set(
                            f.get_dir_path(stemonly=True)
                            for f in packages):
                                rmdir(os.path.join(self.manifest_root, name))

                        if self.file_root:
                                try:
                                        for entry in os.listdir(self.file_root):
                                                rmdir(os.path.join(
                                                    self.file_root, entry))
                                except EnvironmentError, e:
                                        if e.errno != errno.ENOENT:
                                                raise
                except EnvironmentError, e:
                        raise apx._convert_error(e)
                finally:
                        # This ensures batch_mode is reset in the event of an
                        # error.
                        c.batch_mode = False
                        self.__unlock_rstore()

        def rebuild(self, build_catalog=True, build_index=False):
                """Rebuilds the repository catalog and search indexes using the
                package manifests currently in the repository.

                'build_catalog' is an optional boolean value indicating whether
                package catalogs should be rebuilt.  If True, existing search
                data will be discarded.

                'build_index' is an optional boolean value indicating whether
                search indexes should be built.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.catalog_root or self.catalog_version == 0:
                        raise RepositoryUnsupportedOperationError()

                self.__lock_rstore()
                try:
                        self.__rebuild(build_catalog=build_catalog,
                            build_index=build_index)
                finally:
                        self.__unlock_rstore()

        def __run_update_index(self):
                """ Determines which fmris need to be indexed and passes them
                to the indexer.

                Note: Only one instance of this method should be running.
                External locking is expected to ensure this behavior. Calling
                refresh index is the preferred method to use to reindex.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.index_root or self.catalog_version < 1:
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
                        if not self.__search_available:
                                self.__index_log("Search Available")
                        self.__search_available = True

        def search(self, queries):
                """Searches the index for each query in the list of queries.
                Each entry should be the output of str(Query), or a Query
                object."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.index_root or not self.catalog_root:
                        raise RepositoryUnsupportedOperationError()

                self.__check_search()
                if not self.search_available:
                        raise RepositorySearchUnavailableError()

                def _search(q):
                        assert self.index_root
                        l = sqp.QueryLexer()
                        l.build()
                        qqp = sqp.QueryParser(l)
                        query = qqp.parse(q.text)
                        query.set_info(num_to_return=q.num_to_return,
                            start_point=q.start_point,
                            index_dir=self.index_root,
                            get_manifest_path=self.manifest,
                            case_sensitive=q.case_sensitive)
                        if q.return_type == sqp.Query.RETURN_PACKAGES:
                                query.propagate_pkg_return()
                        return query.search(self.catalog.fmris)

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
                return (self.__search_available and self.index_root and
                    os.path.exists(self.index_root)) or self.__check_search()

        def update_publisher(self, pub):
                """Updates the configuration information for the publisher
                defined by the provided Publisher object.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.root:
                        raise RepositoryUnsupportedOperationError()

                p5ipath = os.path.join(self.root, "pub.p5i")
                fn = None
                try:
                        dirname = os.path.dirname(p5ipath)
                        fd, fn = tempfile.mkstemp(dir=dirname)

                        st = None
                        try:
                                st = os.stat(p5ipath)
                        except OSError, e:
                                if e.errno != errno.ENOENT:
                                        raise

                        if st:
                                os.fchmod(fd, stat.S_IMODE(st.st_mode))
                                try:
                                        portable.chown(fn, st.st_uid, st.st_gid)
                                except OSError, e:
                                        if e.errno != errno.EPERM:
                                                raise
                        else:
                                os.fchmod(fd, misc.PKG_FILE_MODE)

                        with os.fdopen(fd, "wb") as f:
                                with codecs.EncodedFile(f, "utf-8") as ef:
                                        p5i.write(ef, [pub])
                        portable.rename(fn, p5ipath)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(e.filename)
                        elif e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        raise
                finally:
                        if fn and os.path.exists(fn):
                                os.unlink(fn)

        def valid_new_fmri(self, pfmri):
                """Check that the FMRI supplied as an argument would be valid
                to add to the repository catalog.  This checks to make sure
                that any past catalog operations (such as a rename or freeze)
                would not prohibit the caller from adding this FMRI."""

                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.catalog_root:
                        raise RepositoryUnsupportedOperationError()
                if not fmri.is_valid_pkg_name(pfmri.get_name()):
                        return False
                if not pfmri.version:
                        return False

                c = self.catalog
                entry = c.get_entry(pfmri)
                return entry is None

        def valid_append_fmri(self, pfmri):
                if self.mirror:
                        raise RepositoryMirrorError()
                if not self.catalog_root:
                        raise RepositoryUnsupportedOperationError()
                if not fmri.is_valid_pkg_name(pfmri.get_name()):
                        return False
                if not pfmri.version:
                        return False
                if not pfmri.version.timestr:
                        return False

                c = self.catalog
                entry = c.get_entry(pfmri)
                return entry is not None

        catalog_root = property(lambda self: self.__catalog_root)
        file_root = property(lambda self: self.__file_root)
        read_only = property(lambda self: self.__read_only, __set_read_only)
        root = property(lambda self: self.__root)
        writable_root = property(lambda self: self.__writable_root)


class Repository(object):
        """A Repository object is a representation of data contained within a
        pkg(5) repository and an interface to manipulate it."""

        def __init__(self, cfgpathname=None, create=False, file_root=None,
            log_obj=None, mirror=False, properties=misc.EmptyDict,
            read_only=False, root=None,
            sort_file_max_size=indexer.SORT_FILE_MAX_SIZE, writable_root=None):
                """Prepare the repository for use."""

                # This lock is used to protect the repository from multiple
                # threads modifying it at the same time.  This must be set
                # first.
                self.__lock = pkg.nrlock.NRLock()
                self.__prop_lock = pkg.nrlock.NRLock()

                # Setup any root overrides or root defaults first.
                self.__file_root = file_root
                self.__pub_root = None
                self.__root = None
                self.__tmp_root = None
                self.__writable_root = None

                # Set root after roots above.
                self.__set_root(root)

                # Set writable root last.
                self.__set_writable_root(writable_root)

                # Stats
                self.__catalog_requests = 0
                self.__file_requests = 0
                self.__manifest_requests = 0

                # Initialize.
                self.__cfgpathname = cfgpathname
                self.__cfg = None
                self.__mirror = mirror
                self.__read_only = read_only
                self.__rstores = None
                self.__sort_file_max_size = sort_file_max_size
                self.log_obj = log_obj
                self.version = -1

                self.__lock_repository()
                try:
                        self.__init_state(create=create, properties=properties)
                finally:
                        self.__unlock_repository()

        def __init_format(self, create=False, properties=misc.EmptyI):
                """Private helper function to determine repository format and
                validity.
                """

                try:
                        if not create and self.root and \
                            os.path.isfile(self.root):
                                raise RepositoryInvalidError(self.root)
                except EnvironmentError, e:
                        raise apx._convert_error(e)

                cfgpathname = None
                if self.__cfgpathname:
                        # Use the custom configuration.
                        cfgpathname = self.__cfgpathname
                elif self.root:
                        # Fallback to older standard configuration.
                        cfgpathname = os.path.join(self.root,
                            "cfg_cache")

                if self.root:
                        # Determine if the standard configuration file exists,
                        # and if so, ignore any custom location specified as it
                        # is only valid for older formats.
                        cfgpath = os.path.join(self.root,
                            "pkg5.repository")
                        if (cfgpathname and not os.path.exists(cfgpathname)) or \
                            os.path.isfile(cfgpath):
                                cfgpathname = cfgpath

                # Load the repository configuration.
                self.__cfg = RepositoryConfig(target=cfgpathname,
                    overrides=properties)

                try:
                        self.version = int(self.cfg.get_property("repository",
                            "version"))
                except (cfg.PropertyConfigError, ValueError):
                        # If version couldn't be read from configuration,
                        # then allow fallback path below to set things right.
                        self.version = -1

                if self.version <= 0 and self.root:
                        # If version doesn't exist, attempt to determine version
                        # based on structure.
                        pub_root = os.path.join(self.root, "publisher")
                        cat_root = os.path.join(self.root, "catalog")
                        if os.path.exists(pub_root) or \
                            (self.cfg.version > 3 and
                            not os.path.exists(cat_root)):
                                # If publisher root exists or new configuration
                                # format exists (and the old catalog root
                                # does not), assume this is a v4 repository.
                                self.version = 4
                        elif self.root:
                                if os.path.exists(cat_root):
                                        if os.path.exists(os.path.join(
                                            cat_root, "attrs")):
                                                # Old catalog implies v2.
                                                self.version = 2
                                        else:
                                                # Assume version 3 otherwise.
                                                self.version = 3

                                        # Reload the repository configuration
                                        # so that configuration definitions
                                        # can match.
                                        self.__cfg = RepositoryConfig(
                                            target=cfgpathname,
                                            overrides=properties,
                                            version=self.version)
                                else:
                                        raise RepositoryInvalidError(
                                            self.root)
                        else:
                                raise RepositoryInvalidError()

                        self.cfg.set_property("repository", "version",
                            self.version)
                elif self.version <= 0 and self.file_root:
                        # If only file root specified, treat as version 4
                        # repository.
                        self.version = 4

                # Setup roots.
                if self.root and not self.file_root:
                        # Don't create the default file root at this point, but
                        # set its default location if it exists.
                        froot = os.path.join(self.root, "file")
                        if not self.file_root and os.path.exists(froot):
                                self.__file_root = froot

                if self.version > CURRENT_REPO_VERSION:
                        raise RepositoryVersionError(self.root,
                            self.version)
                if self.version == 4:
                        if self.root and not self.pub_root:
                                # Don't create the publisher root at this point,
                                # but set its expected location.
                                self.__pub_root = os.path.join(self.root,
                                    "publisher")

                        if not create and cfgpathname and \
                            not os.path.exists(cfgpathname) and \
                            not (os.path.exists(self.pub_root) or
                            os.path.exists(os.path.join(
                                self.root, "pkg5.image")) and
                            Image(self.root, augment_ta_from_parent_image=False,
                                allow_ondisk_upgrade=False,
                                should_exist=True).version >= 3):
                                # If this isn't a repository creation operation,
                                # and the base configuration file doesn't exist,
                                # this isn't a valid repository.
                                raise RepositoryInvalidError(self.root)

                # Setup repository stores.
                def_pub = self.cfg.get_property("publisher", "prefix")
                if self.version == 4:
                        # For repository versions 4+, there is a repository
                        # store for the top-level file root...
                        froot = self.file_root
                        if not froot:
                                froot = os.path.join(self.root, "file")
                        rstore = _RepoStore(file_root=froot,
                            log_obj=self.log_obj, mirror=self.mirror,
                            read_only=self.read_only)
                        self.__rstores[rstore.publisher] = rstore

                        # ...and then one for each publisher if any are known.
                        if self.pub_root and os.path.exists(self.pub_root):
                                for pub in os.listdir(self.pub_root):
                                        self.__new_rstore(pub)

                        # If a default publisher is set, ensure that a storage
                        # object always exists for it.
                        if def_pub and def_pub not in self.__rstores:
                                self.__new_rstore(def_pub)
                else:
                        # For older repository versions, there is only one
                        # repository store, and it might have an associated
                        # publisher prefix.
                        rstore = _RepoStore(file_root=self.file_root,
                            log_obj=self.log_obj, pub=def_pub,
                            mirror=self.mirror,
                            read_only=self.read_only,
                            root=self.root,
                            writable_root=self.writable_root)
                        self.__rstores[rstore.publisher] = rstore

                if not self.root:
                        # Nothing more to do.
                        return

                try:
                        fs = os.stat(self.root)
                except OSError, e:
                        # If the stat failed due to this, then assume the
                        # repository is possibly valid but that there is a
                        # permissions issue.
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(
                                    e.filename)
                        elif e.errno == errno.ENOENT:
                                raise RepositoryInvalidError(self.root)
                        raise

                if not stat.S_ISDIR(stat.S_IFMT(fs.st_mode)):
                        # Not a directory.
                        raise RepositoryInvalidError(self.root)

                # Ensure obsolete search data is removed.
                if self.version >= 3 and not self.read_only:
                        searchdb_file = os.path.join(self.root, "search")
                        for ext in ".pag", ".dir":
                                try:
                                        os.unlink(searchdb_file + ext)
                                except OSError:
                                        # If these can't be removed, it doesn't
                                        # matter.
                                        continue

        def __init_state(self, create=False, properties=misc.EmptyDict):
                """Private helper function to initialize state."""

                # Discard current repository storage state data.
                self.__rstores = {}

                # Determine format, configuration location, and validity.
                self.__init_format(create=create, properties=properties)

                # Ensure default configuration is written.
                self.__write_config()

        def __lock_repository(self):
                """Locks the repository preventing multiple consumers from
                modifying it during operations."""

                # XXX need filesystem lock too?
                self.__lock.acquire()

        def __log(self, msg, context="", severity=logging.INFO):
                if self.log_obj:
                        self.log_obj.log(msg=msg, context=context,
                            severity=severity)

        def __set_mirror(self, value):
                self.__prop_lock.acquire()
                try:
                        self.__mirror = value
                        for rstore in self.rstores:
                                rstore.mirror = value
                finally:
                        self.__prop_lock.release()

        def __set_read_only(self, value):
                self.__prop_lock.acquire()
                try:
                        self.__read_only = value
                        for rstore in self.rstores:
                                rstore.read_only = value
                finally:
                        self.__prop_lock.release()

        def __set_root(self, root):
                self.__prop_lock.acquire()
                try:
                        if root:
                                root = os.path.abspath(root)
                                self.__root = root
                                self.__tmp_root = os.path.join(root, "tmp")
                        else:
                                self.__root = None
                finally:
                        self.__prop_lock.release()

        def __set_writable_root(self, root):
                self.__prop_lock.acquire()
                try:
                        if root:
                                root = os.path.abspath(root)
                                self.__tmp_root = os.path.join(root, "tmp")
                        elif self.root:
                                self.__tmp_root = os.path.join(self.root,
                                    "tmp")
                        else:
                                self.__tmp_root = None
                        self.__writable_root = root
                finally:
                        self.__prop_lock.release()

        def __unlock_repository(self):
                """Unlocks the repository so other consumers may modify it."""

                # XXX need filesystem unlock too?
                self.__lock.release()

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

        def __new_rstore(self, pub):
                assert pub
                if pub in self.__rstores:
                        raise RepositoryDuplicatePublisher(pub)

                if self.pub_root:
                        # Newer repository format stores repository data
                        # partitioned by publisher.
                        root = os.path.join(self.pub_root, pub)
                else:
                        # Older repository formats store repository data
                        # in a shared root area.
                        root = self.root

                writ_root = None
                if self.writable_root:
                        writ_root = os.path.join(self.writable_root,
                            "publisher", pub)

                froot = self.file_root
                if self.root and froot and \
                    froot.startswith(self.root):
                        # Ignore the file root if it's the default one.
                        froot = None

                rstore = _RepoStore(file_root=froot, log_obj=self.log_obj,
                    mirror=self.mirror, pub=pub, read_only=self.read_only,
                    root=root,
                    sort_file_max_size=self.__sort_file_max_size,
                    writable_root=writ_root)
                self.__rstores[pub] = rstore
                return rstore

        def abandon(self, trans_id):
                """Aborts a transaction with the specified Transaction ID.
                Returns the current package state.
                """

                rstore = self.get_trans_rstore(trans_id)
                return rstore.abandon(trans_id)

        def add(self, trans_id, action):
                """Adds an action and its content to a transaction with the
                specified Transaction ID.
                """

                rstore = self.get_trans_rstore(trans_id)
                return rstore.add(trans_id, action)

        def add_publisher(self, pub):
                """Creates a repository storage area for the publisher defined
                by the provided Publisher object and then stores the publisher's
                configuration information.  Only supported for version 4 and
                later repositories.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.pub_root or self.version < 4:
                        raise RepositoryUnsupportedOperationError()

                # Create the new repository storage area.
                rstore = self.__new_rstore(pub.prefix)

                # Update the publisher's configuration.
                try:
                        rstore.update_publisher(pub)
                except:
                        # If the above fails, be certain to delete the new
                        # repository storage area and then re-raise the
                        # original exception.
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        try:
                                shutil.rmtree(rstore.root)
                        finally:
                                # This ensures that the original exception and
                                # traceback are used.
                                raise exc_value, None, exc_tb

        def add_package(self, pfmri):
                """Adds the specified FMRI to the repository's catalog."""

                rstore = self.get_pub_rstore(pfmri.publisher)
                return rstore.add_package(pfmri)

        def append(self, client_release, pfmri, pub=None):
                """Starts an append transaction for the specified client
                release and FMRI.  Returns the Transaction ID for the new
                transaction."""

                try:
                        if not isinstance(pfmri, fmri.PkgFmri):
                                pfmri = fmri.PkgFmri(pfmri, client_release)
                except fmri.FmriError, e:
                        raise RepositoryInvalidFMRIError(e)
 
                if pub and not pfmri.publisher:
                        pfmri.publisher = pub

                try:
                        rstore = self.get_pub_rstore(pfmri.publisher)
                except RepositoryUnknownPublisher, e:
                        if not pfmri.publisher:
                                # No publisher given in FMRI and no default
                                # publisher so treat as invalid FMRI.
                                raise RepositoryUnqualifiedFMRIError(pfmri)
                        raise
                return rstore.append(client_release, pfmri)

        def catalog_0(self, pub=None):
                """Returns a generator object for the full version of
                the catalog contents.  Incremental updates are not provided
                as the v0 updatelog does not support renames, obsoletion,
                package removal, etc.

                'pub' is the prefix of the publisher to return catalog data for.
                If not specified, the default publisher will be used.  If no
                default publisher has been configured, an AssertionError will be
                raised.
                """

                self.inc_catalog()
                rstore = self.get_pub_rstore(pub)
                return rstore.catalog_0()

        def catalog_1(self, name, pub=None):
                """Returns the absolute pathname of the named catalog file.

                'pub' is the prefix of the publisher to return catalog data for.
                If not specified, the default publisher will be used.  If no
                default publisher has been configured, an AssertionError will be
                raised.
                """

                self.inc_catalog()
                rstore = self.get_pub_rstore(pub)
                return rstore.catalog_1(name)

        def close(self, trans_id, add_to_catalog=True):
                """Closes the transaction specified by 'trans_id'.

                Returns a tuple containing the package FMRI and the current
                package state in the catalog.
                """

                self.inc_catalog()
                rstore = self.get_trans_rstore(trans_id)
                return rstore.close(trans_id, add_to_catalog=add_to_catalog)

        def file(self, fhash, pub=None):
                """Returns the absolute pathname of the file specified by the
                provided SHA1-hash name.

                'pub' is the prefix of the publisher to return catalog data for.
                If not specified, the default publisher will be used.  If no
                default publisher has been configured, an AssertionError will be
                raised.
                """

                self.inc_file()
                if pub:
                        rstore = self.get_pub_rstore(pub)
                        return rstore.file(fhash)

                # If a publisher wasn't specified, every repository store will
                # have to be tried since default publisher can't safely apply
                # here.
                for rstore in self.rstores:
                        try:
                                return rstore.file(fhash)
                        except RepositoryFileNotFoundError:
                                # Ignore and try next repository store.
                                pass

                # Not found in any repository store.
                raise RepositoryFileNotFoundError(fhash)

        def get_catalog(self, pub=None):
                """Return the catalog object for the given publisher.

                'pub' is the optional name of the publisher to return the
                catalog for.  If not provided, the default publisher's
                catalog will be returned.
                """

                try:
                        rstore = self.get_pub_rstore(pub)
                        return rstore.catalog
                except RepositoryUnknownPublisher:
                        if pub:
                                # In this case, an unknown publisher's
                                # catalog was requested.
                                raise
                        # No catalog to return.
                        raise RepositoryUnsupportedOperationError()

        def get_pub_rstore(self, pub=None):
                """Return a repository storage object matching the given
                publisher (if provided).  If not provided, a repository
                storage object for the default publisher will be returned.
                A RepositoryUnknownPublisher exception will be raised if
                no storage object for the given publisher exists.
                """

                if pub is None:
                        pub = self.cfg.get_property("publisher", "prefix")
                if not pub:
                        raise RepositoryUnknownPublisher(pub)

                try:
                        rstore = self.__rstores[pub]
                except KeyError:
                        raise RepositoryUnknownPublisher(pub)
                return rstore

        def __get_cfg_publisher(self, pub):
                """Return a publisher object for the given publisher prefix
                based on the repository's configuration information.
                """
                assert self.version < 4

                alias = self.cfg.get_property("publisher", "alias")

                rargs = {}
                for prop in ("collection_type", "description",
                    "legal_uris", "mirrors", "name", "origins",
                    "refresh_seconds", "registration_uri",
                    "related_uris"):
                        rargs[prop] = self.cfg.get_property(
                            "repository", prop)

                repo = publisher.Repository(**rargs)
                return publisher.Publisher(pub, alias=alias,
                    repository=repo)

        def get_publishers(self):
                """Return publisher objects for all publishers known by the
                repository.
                """
                return [
                    self.get_publisher(pub)
                    for pub in self.publishers
                ]

        def get_publisher(self, pub):
                """Return the publisher object for the given publisher.  Raises
                RepositoryUnknownPublisher if no matching publisher can be
                found.
                """

                if not pub:
                        raise RepositoryUnknownPublisher(pub)
                if self.version < 4:
                        return self.__get_cfg_publisher(pub)

                rstore = self.get_pub_rstore(pub)
                if not rstore:
                        raise RepositoryUnknownPublisher(pub)
                return rstore.get_publisher()

        def get_status(self):
                """Return a dictionary of status information about the
                repository.
                """

                if self.locked:
                        rstatus = "processing"
                else:
                        rstatus = "online"

                rdata = {
                    "repository": {
                        "configuration": self.cfg.get_index(),
                        "publishers": {},
                        "requests": {
                            "catalog": self.catalog_requests,
                            "file": self.file_requests,
                            "manifests": self.manifest_requests,
                        },
                        "status": rstatus, # Overall repository state.
                        "version": self.version, # Version of repository.
                    },
                    "version": 1, # Version of status structure.
                }

                for rstore in self.rstores:
                        if not rstore.publisher:
                                continue
                        pubdata = rdata["repository"]["publishers"]
                        pubdata[rstore.publisher] = rstore.get_status()
                return rdata

        def get_trans_rstore(self, trans_id):
                """Return a repository storage object matching the given
                Transaction ID.  If no repository storage object has a
                matching Transaction ID, a RepositoryInvalidTransactionIDError
                will be raised.
                """

                for rstore in self.rstores:
                        if rstore.has_transaction(trans_id):
                                return rstore
                raise RepositoryInvalidTransactionIDError(trans_id)

        @property
        def in_flight_transactions(self):
                """The number of transactions awaiting completion."""

                return sum(
                    rstore.in_flight_transactions
                    for rstore in self.rstores
                )

        def inc_catalog(self):
                self.__catalog_requests += 1

        def inc_file(self):
                self.__file_requests += 1

        def inc_manifest(self):
                self.__manifest_requests += 1

        @property
        def locked(self):
                """A boolean value indicating whether the repository is locked.
                """

                return self.__lock and self.__lock.locked

        def manifest(self, pfmri, pub=None):
                """Returns the absolute pathname of the manifest file for the
                specified FMRI.
                """

                self.inc_manifest()

                try:
                        if not isinstance(pfmri, fmri.PkgFmri):
                                pfmri = fmri.PkgFmri(pfmri)
                except fmri.FmriError, e:
                        raise RepositoryInvalidFMRIError(e)
 
                if not pub and pfmri.publisher:
                        pub = pfmri.publisher
                elif pub and not pfmri.publisher:
                        pfmri.publisher = pub

                if pub:
                        try:
                                rstore = self.get_pub_rstore(pub)
                        except RepositoryUnknownPublisher, e:
                                raise RepositoryManifestNotFoundError(pfmri)
                        return rstore.manifest(pfmri)

                # If a publisher wasn't specified, every repository store will
                # have to be tried since default publisher can't safely apply
                # here.  It's assumed that it's unlikely that two publishers
                # share the exact same FMRI.  Since this case is only for
                # compatibility, it shouldn't be much of a concern.
                mpath = None
                for rstore in self.rstores:
                        if not rstore.publisher:
                                continue
                        mpath = rstore.manifest(pfmri)
                        if not mpath or not os.path.exists(mpath):
                                continue
                        return mpath
                raise RepositoryManifestNotFoundError(pfmri)

        def open(self, client_release, pfmri, pub=None):
                """Starts a transaction for the specified client release and
                FMRI.  Returns the Transaction ID for the new transaction.
                """

                try:
                        if not isinstance(pfmri, fmri.PkgFmri):
                                pfmri = fmri.PkgFmri(pfmri, client_release)
                except fmri.FmriError, e:
                        raise RepositoryInvalidFMRIError(e)
 
                if pub and not pfmri.publisher:
                        pfmri.publisher = pub

                try:
                        rstore = self.get_pub_rstore(pfmri.publisher)
                except RepositoryUnknownPublisher, e:
                        if not pfmri.publisher:
                                # No publisher given in FMRI and no default
                                # publisher so treat as invalid FMRI.
                                raise RepositoryUnqualifiedFMRIError(pfmri)
                        # A publisher was provided, but no repository storage
                        # object exists yet, so add one.
                        rstore = self.__new_rstore(pfmri.publisher)
                return rstore.open(client_release, pfmri)

        def get_matching_fmris(self, patterns, pubs=misc.EmptyI):
                """Given a user-specified list of FMRI pattern strings, return
                a tuple of ('matching', 'references'), where matching is a dict
                of matching fmris and references is a dict of the patterns
                indexed by matching FMRI respectively:

                {
                 pkgname: [fmri1, fmri2, ...],
                 pkgname: [fmri1, fmri2, ...],
                 ...
                }

                {
                 fmri1: [pat1, pat2, ...],
                 fmri2: [pat1, pat2, ...],
                 ...
                }

                'patterns' is the list of package patterns to match.

                'pubs' is an optional set of publisher prefixes to restrict the
                results to.

                Constraint used is always AUTO as per expected UI behavior when
                determining successor versions.

                Note that patterns starting w/ pkg:/ require an exact match;
                patterns containing '*' will using fnmatch rules; the default
                trailing match rules are used for remaining patterns.

                Exactly duplicated patterns are ignored.

                Routine raises PackageMatchErrors if errors occur: it is illegal
                to specify multiple different patterns that match the same
                package name.  Only patterns that contain wildcards are allowed
                to match multiple packages.
                """

                def merge(src, dest):
                        for k, v in src.iteritems():
                                if k in dest:
                                        dest[k].extend(v)
                                else:
                                        dest[k] = v

                matching = {}
                references = {}
                unmatched = None
                for rstore in self.rstores:
                        if not rstore.catalog_root or not rstore.publisher:
                                # No catalog to aggregate matches from.
                                continue
                        if pubs and rstore.publisher not in pubs:
                                # Doesn't match specified publisher.
                                continue

                        # Get matching items from target catalog and then
                        # merge the result.
                        mdict, mrefs, munmatched = \
                            rstore.catalog.get_matching_fmris(patterns,
                                raise_unmatched=False)
                        merge(mdict, matching)
                        merge(mrefs, references)
                        if unmatched is None:
                                unmatched = munmatched
                        else:
                                # The only unmatched entries that are
                                # interesting are the ones that have no
                                # matches for any publisher.
                                unmatched.intersection_update(munmatched)

                        del mdict, mrefs, munmatched

                if unmatched:
                        # One or more patterns didn't match a package from any
                        # publisher.
                        raise apx.PackageMatchErrors(unmatched_fmris=unmatched)
                if not matching:
                        # No packages or no publishers matching 'pubs'.
                        raise apx.PackageMatchErrors(unmatched_fmris=patterns)

                return matching, references

        @property
        def publishers(self):
                """A set containing the list of publishers known to the
                repository."""

                pubs = set()
                pub = self.cfg.get_property("publisher", "prefix")
                if pub:
                        pubs.add(pub)

                for rstore in self.rstores:
                        if rstore.publisher:
                                pubs.add(rstore.publisher)
                return pubs

        def refresh_index(self, pub=None):
                """ This function refreshes the search indexes if there any new
                packages.
                """

                for rstore in self.rstores:
                        if not rstore.publisher:
                                continue
                        if pub and rstore.publisher and rstore.publisher != pub:
                                continue
                        rstore.refresh_index()

        def remove_packages(self, packages, progtrack=None, pub=None):
                """Removes the specified packages from the repository.

                'packages' is a list of FMRIs of packages to remove.

                'progtrack' is an optional ProgressTracker object.

                'pub' is an optional publisher prefix to limit the operation to.
                """

                plist = set()
                pubs = set()
                for p in packages:
                        try:
                                pfmri = p
                                if not isinstance(pfmri, fmri.PkgFmri):
                                        pfmri = fmri.PkgFmri(pfmri)
                                if pub and not pfmri.publisher:
                                        pfmri.publisher = pub
                                if pfmri.publisher:
                                        pubs.add(pfmri.publisher)
                                plist.add(pfmri)
                        except fmri.FmriError, e:
                                raise RepositoryInvalidFMRIError(e)

                if len(pubs) > 1:
                        # Don't allow removal of packages from different
                        # publishers at the same time.  Current transaction
                        # model relies on a single publisher at a time and
                        # transport is mapped the same way.
                        raise RepositoryUnsupportedOperationError()

                if not pub and pubs:
                        # Use publisher specified in one of the FMRIs instead
                        # of default publisher.
                        pub = list(pubs)[0]

                try:
                        rstore = self.get_pub_rstore(pub)
                except RepositoryUnknownPublisher, e:
                        for p in plist:
                                if not pfmri.publisher:
                                        # No publisher given in FMRI and no
                                        # default publisher so treat as
                                        # invalid FMRI.
                                        raise RepositoryUnqualifiedFMRIError(
                                            pfmri)
                        raise

                # Before moving on, assign publisher for every FMRI that doesn't
                # have one already.
                for p in plist:
                        if not pfmri.publisher:
                                pfmri.publisher = rstore.publisher

                rstore.remove_packages(packages, progtrack=progtrack)

        def add_content(self, pub=None, refresh_index=False):
                """Looks for packages added to the repository that are not in
                the catalog, adds them, and then updates search data by default.
                """

                for rstore in self.rstores:
                        if not rstore.publisher:
                                continue
                        if pub and rstore.publisher and rstore.publisher != pub:
                                continue
                        rstore.add_content(refresh_index=refresh_index)

        def add_file(self, trans_id, data, size=None):
                """Adds a file to a transaction with the specified Transaction
                ID."""

                rstore = self.get_trans_rstore(trans_id)
                return rstore.add_file(trans_id, data=data, size=size)

        def rebuild(self, build_catalog=True, build_index=False, pub=None):
                """Rebuilds the repository catalog and search indexes using the
                package manifests currently in the repository.

                'build_catalog' is an optional boolean value indicating whether
                package catalogs should be rebuilt.  If True, existing search
                data will be discarded.

                'build_index' is an optional boolean value indicating whether
                search indexes should be built.
                """

                for rstore in self.rstores:
                        if not rstore.publisher:
                                continue
                        if pub and rstore.publisher and rstore.publisher != pub:
                                continue
                        rstore.rebuild(build_catalog=build_catalog,
                            build_index=build_index)

        def reload(self):
                """Reloads the repository state information."""

                self.__lock_repository()
                self.__init_state()
                self.__unlock_repository()

        def replace_package(self, pfmri):
                """Replaces the information for the specified FMRI in the
                repository's catalog."""

                rstore = self.get_pub_rstore(pfmri.publisher)
                return rstore.replace_package(pfmri)

        def reset_search(self, pub=None):
                """Discards currenty loaded search data so that it will be
                reloaded for the next search operation.
                """
                for rstore in self.rstores:
                        if pub and rstore.publisher and rstore.publisher != pub:
                                continue
                        rstore.reset_search()

        def search(self, queries, pub=None):
                """Searches the index for each query in the list of queries.
                Each entry should be the output of str(Query), or a Query
                object.
                """

                rstore = self.get_pub_rstore(pub)
                return rstore.search(queries)

        def supports(self, op, ver):
                """Returns a boolean value indicating whether the specified
                operation is supported at the given version.
                """

                if op == "search" and self.root:
                        return True
                if op == "catalog" and ver == 1:
                        # For catalog v1 to be "supported", all storage objects
                        # must use it.
                        for rstore in self.rstores:
                                if rstore.catalog_version == 0:
                                        return False
                        return True
                # Assume operation is supported otherwise.
                return True

        def update_publisher(self, pub):
                """Updates the configuration information for the publisher
                defined by the provided Publisher object.  Only supported
                for version 4 and later repositories.
                """

                if self.mirror:
                        raise RepositoryMirrorError()
                if self.read_only:
                        raise RepositoryReadOnlyError()
                if not self.pub_root or self.version < 4:
                        raise RepositoryUnsupportedOperationError()

                # Get the repository storage area for the given publisher.
                rstore = self.get_pub_rstore(pub.prefix)

                # Update the publisher's configuration.
                rstore.update_publisher(pub)

        def valid_new_fmri(self, pfmri):
                """Check that the FMRI supplied as an argument would be valid
                to add to the repository catalog.  This checks to make sure
                that any past catalog operations (such as a rename or freeze)
                would not prohibit the caller from adding this FMRI."""

                rstore = self.get_pub_rstore(pfmri.publisher)
                return rstore.valid_new_fmri(pfmri)

        def write_config(self):
                """Save the repository's current configuration data."""

                self.__lock_repository()
                try:
                        self.__write_config()
                finally:
                        self.__unlock_repository()

        catalog_requests = property(lambda self: self.__catalog_requests)
        cfg = property(lambda self: self.__cfg)
        file_requests = property(lambda self: self.__file_requests)
        file_root = property(lambda self: self.__file_root)
        manifest_requests = property(lambda self: self.__manifest_requests)
        mirror = property(lambda self: self.__mirror, __set_mirror)
        pub_root = property(lambda self: self.__pub_root)
        read_only = property(lambda self: self.__read_only, __set_read_only)
        root = property(lambda self: self.__root)
        rstores = property(lambda self: self.__rstores.values())
        writable_root = property(lambda self: self.__writable_root)


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
            2: [
                cfg.PropertySection("publisher", [
                    cfg.PropPublisher("alias"),
                    cfg.PropPublisher("prefix"),
                ]),
                cfg.PropertySection("repository", [
                    cfg.PropDefined("collection_type", ["core",
                        "supplemental"], default="core"),
                    cfg.PropDefined("description"),
                    cfg.PropPubURI("detailed_url"),
                    cfg.PropSimplePubURIList("legal_uris"),
                    cfg.PropDefined("maintainer"),
                    cfg.PropPubURI("maintainer_url"),
                    cfg.PropSimplePubURIList("mirrors"),
                    cfg.PropDefined("name",
                        default="package repository"),
                    cfg.PropSimplePubURIList("origins"),
                    cfg.PropInt("refresh_seconds", default=14400),
                    cfg.PropPubURI("registration_uri"),
                    cfg.PropSimplePubURIList("related_uris"),
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
                    cfg.PropSimplePubURIList("legal_uris"),
                    cfg.PropDefined("maintainer"),
                    cfg.PropPubURI("maintainer_url"),
                    cfg.PropSimplePubURIList("mirrors"),
                    cfg.PropDefined("name",
                        default="package repository"),
                    cfg.PropSimplePubURIList("origins"),
                    cfg.PropInt("refresh_seconds", default=14400),
                    cfg.PropPubURI("registration_uri"),
                    cfg.PropSimplePubURIList("related_uris"),
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
            4: [
                cfg.PropertySection("publisher", [
                    cfg.PropPublisher("prefix"),
                ]),
                cfg.PropertySection("repository", [
                    cfg.PropInt("version"),
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


def repository_create(repo_uri, properties=misc.EmptyDict, version=None):
        """Create a repository at given location and return the Repository
        object for the new repository.  If a repository (or directory at
        the given location) already exists, a RepositoryExistsError will be
        raised.  Other errors can raise exceptions of class ApiException.
        """

        if isinstance(repo_uri, basestring):
                repo_uri = publisher.RepositoryURI(misc.parse_uri(repo_uri))

        path = repo_uri.get_pathname()
        if not path:
                # Bad URI?
                raise RepositoryInvalidError(str(repo_uri))

        if version is not None and (version < 3 or
            version > CURRENT_REPO_VERSION):
                raise RepositoryUnsupportedOperationError()

        try:
                os.makedirs(path, misc.PKG_DIR_MODE)
        except EnvironmentError, e:
                if e.filename == path and (e.errno == errno.EEXIST or
                    os.path.exists(e.filename)):
                        entries = os.listdir(e.filename)
                        # If the directory isn't empty (excluding the
                        # special .zfs snapshot directory) don't allow
                        # a repository to be created here.
                        if entries and not entries == [".zfs"]:
                                raise RepositoryExistsError(e.filename)
                elif e.errno == errno.EACCES:
                        raise apx.PermissionsException(e.filename)
                elif e.errno == errno.EROFS:
                        raise apx.ReadOnlyFileSystemException(e.filename)
                elif e.errno != errno.EEXIST or e.filename != path:
                        raise

        if version == 3:
                # Version 3 repositories are expected to contain an additional
                # set of specific directories...
                for d in ("catalog", "file", "index", "pkg", "trans", "tmp"):
                        misc.makedirs(os.path.join(path, d))

                # ...and this file (which can be empty).
                try:
                        with file(os.path.join(path, "cfg_cache"), "wb") as cf:
                                cf.write("\n")
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise apx.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise apx.ReadOnlyFileSystemException(
                                    e.filename)
                        elif e.errno != errno.EEXIST:
                                raise

        return Repository(create=True, read_only=False, properties=properties,
            root=path)
