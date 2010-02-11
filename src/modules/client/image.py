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
# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.
#

import datetime
import errno
import fcntl
import os
import platform
import shutil
import tempfile
import time
import urllib

from contextlib import contextmanager
from pkg.client import global_settings
logger = global_settings.logger

import pkg.actions
import pkg.catalog
import pkg.client.api_errors            as api_errors
import pkg.client.history               as history
import pkg.client.imageconfig           as imageconfig
import pkg.client.imageplan             as imageplan
import pkg.client.pkgplan               as pkgplan
import pkg.client.progress              as progress
import pkg.client.publisher             as publisher
import pkg.client.transport.transport   as transport
import pkg.fmri
import pkg.manifest                     as manifest
import pkg.misc                         as misc
import pkg.portable                     as portable
import pkg.server.catalog
import pkg.version

from pkg.client.debugvalues import DebugValues
from pkg.client.imagetypes import IMG_USER, IMG_ENTIRE
from pkg.misc import CfgCacheError, EmptyI, EmptyDict

img_user_prefix = ".org.opensolaris,pkg"
img_root_prefix = "var/pkg"

IMG_PUB_DIR = "publisher"

class Image(object):
        """An Image object is a directory tree containing the laid-down contents
        of a self-consistent graph of Packages.

        An Image has a root path.

        An Image of type IMG_ENTIRE does not have a parent Image.  Other Image
        types must have a parent Image.  The external state of the parent Image
        must be accessible from the Image's context, or duplicated within the
        Image (IMG_PARTIAL for zones, for instance).

        The parent of a user Image can be a partial Image.  The parent of a
        partial Image must be an entire Image.

        An Image of type IMG_USER stores its external state at self.root +
        ".org.opensolaris,pkg".

        An Image of type IMG_ENTIRE or IMG_PARTIAL stores its external state at
        self.root + "/var/pkg".

        An Image needs to be able to have a different repository set than the
        system's root Image.

        Directory layout

          $IROOT/file
               Directory containing file hashes of installed packages.

          $IROOT/pkg
               Directory containing manifests.

          $IROOT/index
               Directory containing search indices.

          $IROOT/cfg_cache
               File containing image's cached configuration.

          $IROOT/opaque
               File containing image's opaque state.

          $IROOT/publisher
                Directory containing publisher metadata.

        All of these directories and files other than state are considered
        essential for any image to be complete. To add a new essential file or
        subdirectory, the following steps should be done.

        If it's a directory, add it to the image_subdirs list below and it will
        be created automatically. The programmer must fill the directory as
        needed. If a file is added, the programmer is responsible for creating
        that file during image creation at an appropriate place and time.

        If a directory is required to be present in order for an image to be
        identifiable as such, it should go into required_subdirs instead.
        However, upgrade issues abound; this list should probably not change.

        Once those steps have been carried out, the change should be added
        to the test suite for image corruption (t_pkg_install_corrupt_image.py).
        This will likely also involve a change to
        SingleDepotTestCaseCorruptImage in testutils.py. Each of these files
        outline what must be updated.

        XXX Root path probably can't be absolute, so that we can combine or
        reuse Image contents.

        XXX Image file format?  Image file manipulation API?"""

        # Class constants
        IMG_CATALOG_KNOWN = "known"
        IMG_CATALOG_INSTALLED = "installed"

        # Please note that the values of these PKG_STATE constants should not
        # be changed as it would invalidate existing catalog data stored in the
        # image.  This means that if a constant is removed, the values of the
        # other constants should not change, etc.

        # This state indicates that a package is present in a repository
        # catalog.
        PKG_STATE_KNOWN = 0

        # This is a transitory state used to indicate that a package is no
        # longer present in a repository catalog; it is only used to clear
        # PKG_STATE_KNOWN.
        PKG_STATE_UNKNOWN = 1

        # This state indicates that a package is installed.
        PKG_STATE_INSTALLED = 2

        # This is a transitory state used to indicate that a package is no
        # longer installed; it is only used to clear PKG_STATE_INSTALLED.
        PKG_STATE_UNINSTALLED = 3
        PKG_STATE_UPGRADABLE = 4

        # These states are used to indicate the package's related catalog
        # version.  This is helpful to consumers of the catalog data so that
        # they can be aware of what metadata may not immediately available
        # (require manifest retrieval) based on the catalog version.
        PKG_STATE_V0 = 6
        PKG_STATE_V1 = 7

        PKG_STATE_OBSOLETE = 8
        PKG_STATE_RENAMED = 9

        # Class properties
        required_subdirs = [ "file", "pkg" ]
        image_subdirs = required_subdirs + [ "index", IMG_PUB_DIR,
            "state/installed", "state/known" ]

        def __init__(self, root, user_provided_dir=False, progtrack=None,
            should_exist=True, imgtype=None, force=False):
                if should_exist:
                        assert(imgtype is None)
                        assert(not force)
                else:
                        assert(imgtype is not None)
                self.__init_catalogs()
                self.__upgraded = False

                self.attrs = {
                    "Policy-Require-Optional": False,
                    "Policy-Pursue-Latest": True
                }
                self.blocking_locks = False
                self.cfg_cache = None
                self.dl_cache_dir = None
                self.dl_cache_incoming = None
                self.history = history.History()
                self.imageplan = None # valid after evaluation succeeds
                self.img_prefix = None
                self.imgdir = None
                self.index_dir = None
                self.is_user_cache_dir = False
                self.pkgdir = None
                self.root = root
                self.__lock = pkg.nrlock.NRLock()
                self.__locked = False
                self.__lockf = None
                self.__req_dependents = None

                # Transport operations for this image
                self.transport = transport.Transport(self)

                if should_exist:
                        self.find_root(self.root, user_provided_dir,
                            progtrack)
                else:
                        if not force and self.image_type(self.root) != None:
                                raise api_errors.ImageAlreadyExists(self.root)
                        if not force and os.path.exists(self.root) and \
                            len(os.listdir(self.root)) > 0:
                                raise api_errors.CreatingImageInNonEmptyDir(
                                    self.root)
                        self.__set_dirs(root=self.root, imgtype=imgtype,
                            progtrack=progtrack)

                # a place to keep info about saved_files; needed by file action
                self.saved_files = {}

                # right now we don't explicitly set dir/file modes everywhere;
                # set umask to proper value to prevent problems w/ overly
                # locked down umask.
                os.umask(0022)

        def _check_subdirs(self, sub_d, prefix):
                for n in self.required_subdirs:
                        if not os.path.isdir(os.path.join(sub_d, prefix, n)):
                                return False
                return True

        def __catalog_loaded(self, name):
                """Returns a boolean value indicating whether the named catalog
                has already been loaded.  This is intended to be used as an
                optimization function to determine which catalog to request."""

                return name in self.__catalogs

        def __init_catalogs(self):
                """Initializes default catalog state.  Actual data is provided
                on demand via get_catalog()"""

                # This is used to cache image catalogs.
                self.__catalogs = {}

                # This is used to keep track of what packages have been added
                # to IMG_CATALOG_KNOWN by set_pkg_state().
                self.__catalog_new_installs = set()

        @property
        def locked(self):
                """Returns a boolean value indicating whether the image is
                currently locked."""

                return self.__locked

        @contextmanager
        def locked_op(self, op, allow_unprivileged=False):
                """Helper method for executing an image-modifying operation
                that needs locking.  It also automatically handles calling
                log_operation_start and log_operation_end.  Locking behaviour
                is controlled by the blocking_locks image property.

                'allow_unprivileged' is an optional boolean value indicating
                that permissions-related exceptions should be ignored when
                attempting to obtain the lock as the related operation will
                still work correctly even though the image cannot (presumably)
                be modified.
                """

                error = None
                self.lock(allow_unprivileged=allow_unprivileged)
                try:
                        self.history.log_operation_start(op)
                        yield
                except Exception, e:
                        error = e
                        raise
                finally:
                        self.history.log_operation_end(error=error)
                        self.unlock()

        def lock(self, allow_unprivileged=False):
                """Locks the image in preparation for an image-modifying
                operation.  Raises an ImageLockedError exception on failure.
                Locking behaviour is controlled by the blocking_locks image
                property.

                'allow_unprivileged' is an optional boolean value indicating
                that permissions-related exceptions should be ignored when
                attempting to obtain the lock as the related operation will
                still work correctly even though the image cannot (presumably)
                be modified.
                """

                blocking = self.blocking_locks

                # First, attempt to obtain a thread lock.
                if not self.__lock.acquire(blocking=blocking):
                        raise api_errors.ImageLockedError()

                self.__locked = True
                try:
                        # Attempt to obtain a file lock.
                        self.__lock_process()
                except api_errors.PermissionsException:
                        if not allow_unprivileged:
                                self.__lock.release()
                                raise
                except:
                        # If process lock fails, ensure thread lock is released.
                        self.__lock.release()
                        raise

        def __lock_process(self):
                """Locks the image to prevent modification by other
                processes."""

                if not os.path.exists(self.imgdir):
                        # Image structure doesn't exist yet so a file lock
                        # cannot be obtained.  This path should only happen
                        # during image-create.
                        return

                # Attempt to obtain a file lock for the image.
                lfpath = os.path.join(self.imgdir, "lock")

                lock_type = fcntl.LOCK_EX
                if not self.blocking_locks:
                        lock_type |= fcntl.LOCK_NB

                # Attempt an initial open of the lock file.
                lf = None
                try:
                        lf = open(lfpath, "ab+")
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                # Attempt to lock the file.
                try:
                        fcntl.lockf(lf, lock_type)
                except IOError, e:
                        if e.errno not in (errno.EAGAIN, errno.EACCES):
                                raise

                        # If the lock failed (because it is likely contended),
                        # then extract the information about the lock acquirer
                        # and raise an exception.
                        pid_data = lf.read().strip()
                        pid, pid_name, hostname, lock_ts = \
                            pid_data.split("\n", 4)
                        raise api_errors.ImageLockedError(pid=pid,
                            pid_name=pid_name, hostname=hostname)

                # Store lock time as ISO-8601 basic UTC timestamp in lock file.
                lock_ts = pkg.catalog.now_to_basic_ts()

                # Store information about the lock acquirer and write it.
                try:
                        lf.truncate(0)
                        lf.write("\n".join((str(os.getpid()),
                            global_settings.client_name,
                            platform.node(), lock_ts, "\n")))
                        lf.flush()
                        self.__lockf = lf
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        def unlock(self):
                """Unlocks the image."""

                if self.__lockf:
                        # To avoid race conditions with the next caller waiting
                        # for the lock file, it is simply truncated instead of
                        # removed.
                        self.__lockf.truncate(0)
                        self.__lockf.close()
                        self.__lockf = None
                self.__locked = False
                self.__lock.release()

        def image_type(self, d):
                """Returns the type of image at directory: d; or None"""
                rv = None
                if os.path.isdir(os.path.join(d, img_user_prefix)) and \
                        os.path.isfile(os.path.join(d, img_user_prefix,
                            imageconfig.CFG_FILE)) and \
                            self._check_subdirs(d, img_user_prefix):
                        rv = IMG_USER
                elif os.path.isdir(os.path.join(d, img_root_prefix)) \
                         and os.path.isfile(os.path.join(d,
                             img_root_prefix, imageconfig.CFG_FILE)) and \
                             self._check_subdirs(d, img_root_prefix):
                        rv = IMG_ENTIRE
                return rv

        def find_root(self, d, exact_match=False, progtrack=None):
                # Ascend from the given directory d to find first
                # encountered image.  If exact_match is true, if the
                # image found doesn't match startd, raise an
                # ImageNotFoundException.

                startd = d
                # eliminate problem if relative path such as "." is passed in
                d = os.path.realpath(d)
                while True:
                        imgtype = self.image_type(d)
                        if imgtype == IMG_USER:
                                # XXX Should look at image file to determine
                                # repo URIs.
                                if exact_match and \
                                    os.path.realpath(startd) != \
                                    os.path.realpath(d):
                                        raise api_errors.ImageNotFoundException(
                                            exact_match, startd, d)
                                self.__set_dirs(imgtype=imgtype, root=d,
                                    progtrack=progtrack)
                                self.attrs["Build-Release"] = "5.11"
                                return
                        elif imgtype == IMG_ENTIRE:
                                # XXX Look at image file to determine
                                # repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                if exact_match and \
                                    os.path.realpath(startd) != \
                                    os.path.realpath(d):
                                        raise api_errors.ImageNotFoundException(
                                            exact_match, startd, d)
                                self.__set_dirs(imgtype=imgtype, root=d,
                                    progtrack=progtrack)
                                self.attrs["Build-Release"] = "5.11"
                                return

                        # XXX follow symlinks or not?
                        oldpath = d
                        d = os.path.normpath(os.path.join(d, os.path.pardir))

                        # Make sure we are making progress and aren't in an
                        # infinite loop.
                        #
                        # (XXX - Need to deal with symlinks here too)
                        if d == oldpath:
                                raise api_errors.ImageNotFoundException(
                                    exact_match, startd, d)

        def __load_config(self):
                """Load this image's cached configuration from the default
                location."""

                # XXX Incomplete with respect to doc/image.txt description of
                # configuration.

                if self.root == None:
                        raise RuntimeError, "self.root must be set"

                ic = imageconfig.ImageConfig(self.root,
                    self._get_publisher_meta_dir())
                ic.read(self.imgdir)
                self.cfg_cache = ic

                for pub in self.gen_publishers(inc_disabled=True):
                        pub.transport = self.transport

        def save_config(self):
                # First, create the image directories if they haven't been, so
                # the cfg_cache can be written.
                self.mkdirs()
                self.cfg_cache.write(self.imgdir)

        # XXX mkdirs and set_attrs() need to be combined into a create
        # operation.
        def mkdirs(self):
                for sd in self.image_subdirs:
                        if os.path.isdir(os.path.join(self.imgdir, sd)):
                                continue

                        try:
                                os.makedirs(os.path.join(self.imgdir, sd))
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise

        def __set_dirs(self, imgtype, root, progtrack=None):
                self.type = imgtype
                self.root = root
                if self.type == IMG_USER:
                        self.img_prefix = img_user_prefix
                else:
                        self.img_prefix = img_root_prefix

                # Change directory to the root of the image so that we can
                # remove any directories beneath us.  If we're changing the
                # image, don't chdir, as we're likely changing to a new BE
                # and want to be able to unmount it later.
                if not self.imgdir and os.path.isdir(root):
                        os.chdir(root)

                        # The specified root may have been a relative path.
                        self.root = os.getcwd()

                if not os.path.isabs(self.root):
                        self.root = os.path.abspath(self.root)

                # If current image is locked, then it should be unlocked
                # and then relocked after the imgdir is changed.  This
                # ensures that alternate BE scenarios work.
                relock = self.imgdir and self.__locked
                if relock:
                        self.unlock()

                self.imgdir = os.path.join(self.root, self.img_prefix)
                self.pkgdir = os.path.join(self.imgdir, "pkg")
                self.history.root_dir = self.imgdir

                if relock:
                        self.lock()

                if "PKG_CACHEDIR" in os.environ:
                        self.dl_cache_dir = os.path.normpath( \
                            os.environ["PKG_CACHEDIR"])
                        self.is_user_cache_dir = True
                else:
                        self.dl_cache_dir = os.path.normpath( \
                            os.path.join(self.imgdir, "download"))
                self.dl_cache_incoming = os.path.normpath(os.path.join(
                    self.dl_cache_dir, "incoming-%d" % os.getpid()))

                # Test if we have the permissions to create the cache
                # incoming directory in this hiearachy.  If not, we'll need to
                # move it somewhere else.
                try:
                        os.makedirs(self.dl_cache_incoming)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES or e.errno == errno.EROFS:
                                self.dl_cache_dir = tempfile.mkdtemp(
                                    prefix="download-%d-" % os.getpid())
                                self.dl_cache_incoming = os.path.normpath(
                                    os.path.join(self.dl_cache_dir,
                                    "incoming-%d" % os.getpid()))
                else:
                        os.removedirs(self.dl_cache_incoming)

                # Forcibly discard image catalogs so they can be re-loaded
                # from the new location if they are already loaded.  This
                # also prevents scribbling on image state information in
                # the wrong location.
                self.__init_catalogs()

                if not os.path.exists(os.path.join(self.imgdir,
                    imageconfig.CFG_FILE)):
                        # New images inherently use the newest image format.
                        # This must be set *before* creating the Publisher
                        # object so that the correct meta_root is set.
                        self.__upgraded = True
                else:
                        self.__upgraded = not os.path.exists(os.path.join(
                            self.imgdir, "catalog"))
                        self.__load_config()
                        self.__check_image(progtrack=progtrack)

        def __check_image(self, progtrack=None):
                """This does some basic sanity checks on the image structure
                and attempts to correct any errors it finds."""

                if not self.__upgraded:
                        with self.locked_op("upgrade-image",
                            allow_unprivileged=True):
                                return self.__upgrade_image(progtrack=progtrack)

                # If the image has already been upgraded, first ensure that its
                # structure is valid.
                self.mkdirs()

                # Ensure structure for publishers is valid.
                for pub in self.gen_publishers():
                        pub.create_meta_root()

                # Once its structure is valid, then ensure state information
                # is intact.
                kdir = os.path.join(self.imgdir, "state",
                    self.IMG_CATALOG_KNOWN)
                kcattrs = os.path.join(kdir, "catalog.attrs")
                idir = os.path.join(self.imgdir, "state",
                    self.IMG_CATALOG_INSTALLED)
                icattrs = os.path.join(idir, "catalog.attrs")
                if not os.path.isfile(kcattrs) and os.path.isfile(icattrs):
                        # If the known catalog doesn't exist, but the installed
                        # catalog does, then copy the installed catalog to the
                        # known catalog directory so that state information can
                        # be preserved during the rebuild.
                        for fname in os.listdir(idir):
                                portable.copyfile(os.path.join(idir, fname),
                                    os.path.join(kdir, fname))
                        self.__rebuild_image_catalogs(progtrack=progtrack)

        def create(self, pubs, facets=EmptyDict, is_zone=False,  progtrack=None,
            refresh_allowed=True, variants=EmptyDict):
                """Creates a new image with the given attributes if it does not
                exist; should not be used with an existing image.

                'is_zone' is a boolean indicating whether the image is a zone.

                'pubs' is a list of Publisher objects to configure the image
                with.

                'refresh_allowed' is an optional boolean indicating that
                network operations (such as publisher data retrieval) are
                allowed.

                'progtrack' is an optional ProgressTracker object.

                'variants' is an optional dictionary of variant names and
                values.

                'facets' is an optional dictionary of facet names and values.
                """

                for p in pubs:
                        p.meta_root = self._get_publisher_meta_root(p.prefix)
                        p.transport = self.transport

                # Initialize and store the configuration object.
                self.cfg_cache = imageconfig.ImageConfig(self.root,
                    self._get_publisher_meta_dir())
                self.history.log_operation_start("image-create")

                # Determine and add the default variants for the image.
                if is_zone:
                        self.cfg_cache.variants[
                            "variant.opensolaris.zone"] = "nonglobal"
                else:
                        self.cfg_cache.variants[
                            "variant.opensolaris.zone"] = "global"

                self.cfg_cache.variants["variant.arch"] = \
                    variants.get("variant.arch", platform.processor())

                # After setting up the default variants, add any overrides or
                # additional variants or facets specified.
                self.cfg_cache.variants.update(variants)
                self.cfg_cache.facets.update(facets)

                # Now everything is ready for publisher configuration.
                # Since multiple publishers are allowed, they are all
                # added at once without any publisher data retrieval.
                # A single retrieval is then performed afterwards, if
                # allowed, to nimimize the amount of work the client
                # needs to perform.
                for p in pubs:
                        self.add_publisher(p, refresh_allowed=False,
                            progtrack=progtrack)

                if refresh_allowed:
                        self.refresh_publishers(progtrack=progtrack)

                # Assume first publisher in list is preferred.
                self.cfg_cache.preferred_publisher = pubs[0].prefix

                # No need to save configuration as add_publisher will do that
                # if successful.
                self.history.log_operation_end()

        def is_liveroot(self):
                return bool(self.root == "/" or
                    DebugValues.get_value("simulate_live_root"))

        def is_zone(self):
                return self.cfg_cache.variants[
                    "variant.opensolaris.zone"] == "nonglobal"

        def get_arch(self):
                return self.cfg_cache.variants["variant.arch"]

        def get_root(self):
                return self.root

        def get_last_modified(self):
                """Returns a UTC datetime object representing the time the
                image's state last changed or None if unknown."""

                # Always get last_modified time from known catalog.  It's
                # retrieved from the catalog itself since that is accurate
                # down to the micrsecond (as opposed to the filesystem which
                # has an OS-specific resolution).
                return self.__get_catalog(self.IMG_CATALOG_KNOWN).last_modified

        def gen_publishers(self, inc_disabled=False):
                if not self.cfg_cache:
                        raise CfgCacheError, "empty ImageConfig"
                for p in self.cfg_cache.publishers:
                        pub = self.cfg_cache.publishers[p]
                        if inc_disabled or not pub.disabled:
                                yield self.cfg_cache.publishers[p]

        def get_publisher_ranks(self):
                """Returns dictionary of publishers by name; each
                entry contains a tuple of search order index starting
                at 0, and a boolean indicating whether or not
                this publisher is "sticky"."""

                # automatically make disabled publishers not sticky
                so = self.cfg_cache.publisher_search_order

                ret = dict([
                    (p.prefix, (so.index(p.prefix), p.sticky))
                    for p in self.gen_publishers()
                ])

                # add any publishers for pkgs that are installed,
                # but have been deleted... so they're not sticky.
                for pub in self.get_installed_pubs():
                        ret.setdefault(pub, (len(ret) + 1, False))
                return ret

        def check_cert_validity(self):
                """Look through the publishers defined for the image.  Print
                a message and exit with an error if one of the certificates
                has expired.  If certificates are getting close to expiration,
                print a warning instead."""

                for p in self.gen_publishers():
                        for r in p.repositories:
                                for uri in r.origins:
                                        if uri.ssl_cert:
                                                misc.validate_ssl_cert(
                                                    uri.ssl_cert,
                                                    prefix=p.prefix, uri=uri)
                return True

        def has_publisher(self, prefix=None, alias=None):
                """Returns a boolean value indicating whether a publisher
                exists in the image configuration that matches the given
                prefix or alias."""
                for pub in self.gen_publishers(inc_disabled=True):
                        if prefix == pub.prefix or (alias and
                            alias == pub.alias):
                                return True
                return False

        def remove_publisher(self, prefix=None, alias=None, progtrack=None):
                """Removes the publisher with the matching identity from the
                image."""

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                with self.locked_op("remove-publisher"):
                        pub = self.get_publisher(prefix=prefix,
                            alias=alias)

                        if pub.prefix == self.cfg_cache.preferred_publisher:
                                raise api_errors.RemovePreferredPublisher()

                        self.cfg_cache.remove_publisher(pub.prefix)
                        self.remove_publisher_metadata(pub, progtrack=progtrack)
                        self.save_config()

        def get_publishers(self):
                return self.cfg_cache.publishers

        def get_publisher(self, prefix=None, alias=None, origin=None):
                publishers = [p for p in self.cfg_cache.publishers.values()]
                for pub in publishers:
                        if prefix and prefix == pub.prefix:
                                return pub
                        elif alias and alias == pub.alias:
                                return pub
                        elif origin and \
                            pub.selected_repository.has_origin(origin):
                                return pub
                raise api_errors.UnknownPublisher(max(prefix, alias, origin))

        def pub_search_before(self, being_moved, staying_put):
                """Moves publisher "being_moved" to before "staying_put"
                in search order."""
                with self.locked_op("search-before"):
                        self.__pub_search_common(being_moved, staying_put,
                            after=False)

        def pub_search_after(self, being_moved, staying_put):
                """Moves publisher "being_moved" to after "staying_put"
                in search order."""
                with self.locked_op("search-after"):
                        self.__pub_search_common(being_moved, staying_put,
                            after=True)

        def __pub_search_common(self, being_moved, staying_put, after=True):
                """Shared logic for altering publisher search order."""

                bm = self.get_publisher(being_moved).prefix
                sp = self.get_publisher(staying_put).prefix

                if bm == sp:
                        raise api_errors.MoveRelativeToSelf()

                # compute new order and set it
                so = self.cfg_cache.publisher_search_order
                so.remove(bm)
                if after:
                        so.insert(so.index(sp) + 1, bm)
                else:
                        so.insert(so.index(sp), bm)
                self.cfg_cache.change_publisher_search_order(so)
                self.save_config()

        def get_preferred_publisher(self):
                """Returns the prefix of the preferred publisher."""
                return self.cfg_cache.preferred_publisher

        def set_preferred_publisher(self, prefix=None, alias=None, pub=None):
                """Sets the preferred publisher for packaging operations.

                'prefix' is an optional string value specifying the name of
                a publisher; ignored if 'pub' is provided.

                'alias' is an optional string value specifying the alias of
                a publisher; ignored if 'pub' is provided.

                'pub' is an optional Publisher object identifying the
                publisher to set as the preferred publisher.

                One of the above parameters must be provided."""

                with self.locked_op("set-preferred-publisher"):
                        if not pub:
                                pub = self.get_publisher(prefix=prefix,
                                    alias=alias)

                                if pub.disabled:
                                        raise api_errors.SetDisabledPublisherPreferred(
                                            pub)
                                self.cfg_cache.preferred_publisher = pub.prefix
                                self.save_config()

        def set_property(self, prop_name, prop_value):
                assert prop_name != "preferred-publisher"
                with self.locked_op("set-property"):
                        self.cfg_cache.properties[prop_name] = prop_value
                        self.save_config()

        def get_property(self, prop_name):
                return self.cfg_cache.properties[prop_name]

        def has_property(self, prop_name):
                return prop_name in self.cfg_cache.properties

        def delete_property(self, prop_name):
                assert prop_name != "preferred-publisher"
                with self.locked_op("unset-property"):
                        del self.cfg_cache.properties[prop_name]
                        self.save_config()

        def destroy(self):
                """Destroys the image; image object should not be used
                afterwards."""

                if not self.imgdir or not os.path.exists(self.imgdir):
                        return

                if os.path.abspath(self.imgdir) == "/":
                        # Paranoia.
                        return

                try:
                        shutil.rmtree(self.imgdir)
                except shutil.Error, e:
                        # shutil.Error contains a list of lists of tuples of
                        # errors with the last part of the tuple being the
                        # actual exception.
                        msg = ""
                        for entries in e:
                                for entry in entries:
                                        # Last part of entry is actual
                                        # exception.
                                        msg += "%s\n" % str(entry[-1])
                        raise api_errors.UnknownErrors(msg)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        def properties(self):
                for p in self.cfg_cache.properties:
                        yield p

        def add_publisher(self, pub, refresh_allowed=True, progtrack=None):
                """Adds the provided publisher object to the image
                configuration.

                'refresh_allowed' is an optional, boolean value indicating
                whether the publisher's metadata should be retrieved when adding
                it to the image's configuration.

                'progtrack' is an optional ProgressTracker object."""

                # API consumer error.
                repo = pub.selected_repository
                assert repo and repo.origins

                with self.locked_op("add-publisher"):
                        for p in self.cfg_cache.publishers.values():
                                if pub.prefix == p.prefix or \
                                    pub.prefix == p.alias or \
                                    pub.alias and (pub.alias == p.alias or
                                    pub.alias == p.prefix):
                                        raise api_errors.DuplicatePublisher(pub)

                        if not progtrack:
                                progtrack = progress.QuietProgressTracker()

                        # Must assign this first before performing operations.
                        pub.meta_root = self._get_publisher_meta_root(
                            pub.prefix)
                        pub.transport = self.transport
                        self.cfg_cache.publishers[pub.prefix] = pub

                        # Ensure that if the publisher's meta directory already
                        # exists for some reason that the data within is not
                        # used.
                        pub.remove_meta_root()

                        if refresh_allowed:
                                try:
                                        # First, verify that the publisher has a
                                        # valid pkg(5) repository.
                                        self.transport.valid_publisher_test(pub)
                                        pub.validate_config()
                                        self.refresh_publishers(pubs=[pub],
                                            progtrack=progtrack)
                                except Exception, e:
                                        # Remove the newly added publisher since
                                        # it is invalid or the retrieval failed.
                                        self.cfg_cache.remove_publisher(
                                            pub.prefix)
                                        raise
                                except:
                                        # Remove the newly added publisher since
                                        # the retrieval failed.
                                        self.cfg_cache.remove_publisher(
                                            pub.prefix)
                                        raise

                        # Only after success should the configuration be saved.
                        self.save_config()

        def verify(self, fmri, progresstracker, **args):
                """Generator that returns a tuple of the form (action, errors,
                warnings, info) if there are any error, warning, or other
                messages about an action contained within the specified
                package.  Where the returned messages are lists of strings
                indicating fatal problems, potential issues (that can be
                ignored), or extra information to be displayed respectively.

                'fmri' is the fmri of the package to verify.

                'progresstracker' is a ProgressTracker object.

                'args' is a dict of additional keyword arguments to be passed
                to each action verification routine."""

                for act in self.get_manifest(fmri).gen_actions(
                    self.list_excludes()):
                        errors, warnings, info = act.verify(self, pkg_fmri=fmri,
                            **args)
                        progresstracker.verify_add_progress(fmri)
                        actname = act.distinguished_name()
                        if errors:
                                progresstracker.verify_yield_error(actname,
                                    errors)
                        if warnings:
                                progresstracker.verify_yield_warning(actname,
                                    warnings)
                        if info:
                                progresstracker.verify_yield_info(actname,
                                    info)
                        if errors or warnings or info:
                                yield act, errors, warnings, info

        def __call_imageplan_evaluate(self, ip, verbose=False):
                # A plan can be requested without actually performing an
                # operation on the image.
                if self.history.operation_name:
                        self.history.operation_start_state = ip.get_plan()

                ip.evaluate(verbose)

                self.imageplan = ip

                if self.history.operation_name:
                        self.history.operation_end_state = \
                            ip.get_plan(full=False)

                if verbose:
                        ip.display()

        def image_change_varcets(self, variants, facets, progtrack, check_cancelation,
            noexecute, verbose=False):


                ip = imageplan.ImagePlan(self, progtrack, check_cancelation,
                    noexecute=noexecute)

                progtrack.evaluate_start()

                # Always start with most current (on-disk) state information.
                self.__init_catalogs()

                # compute dict of changing variants
                if variants:
                        variants = dict(set(variants.iteritems()) - \
                           set(self.cfg_cache.variants.iteritems()))
                # facets are always the entire set

                try:
                        ip.plan_change_varcets(variants, facets)
                        self.__call_imageplan_evaluate(ip, verbose)
                except pkg.actions.ActionError, e:
                        raise api_errors.InvalidPackageErrors([e])

        def image_config_update(self, new_variants, new_facets):
                """update variants in image config"""
                ic = self.cfg_cache

                if new_variants is not None:
                        ic.variants.update(new_variants)

                if new_facets is not None:
                        ic.facets = new_facets

                ic.write(self.imgdir)
                ic = imageconfig.ImageConfig(self.root,
                    self._get_publisher_meta_dir())
                ic.read(self.imgdir)
                self.cfg_cache = ic

        def repair(self, *args, **kwargs):
                """Repair any actions in the fmri that failed a verify."""
                with self.locked_op("fix"):
                        try:
                                return self.__repair(*args, **kwargs)
                        except pkg.actions.ActionError, e:
                                raise api_errors.InvalidPackageErrors([e])

        def __repair(self, repairs, progtrack, accept=False,
            show_licenses=False):
                """Private repair method; caller is responsible for locking."""

                ilm = self.get_last_modified()

                # XXX: This (lambda x: False) is temporary until we move pkg fix
                # into the api and can actually use the
                # api::__check_cancelation() function.
                pps = []
                for fmri, actions in repairs:
                        logger.info("Repairing: %-50s" % fmri.get_pkg_stem())
                        m = self.get_manifest(fmri)
                        pp = pkgplan.PkgPlan(self, progtrack, lambda: False)
                        pp.propose_repair(fmri, m, actions)
                        pp.evaluate(self.list_excludes(), self.list_excludes())
                        pps.append(pp)
                ip = imageplan.ImagePlan(self, progtrack, lambda: False)
                ip._image_lm = ilm
                self.imageplan = ip

                ip.update_index = False
                ip.state = imageplan.EVALUATED_PKGS
                progtrack.evaluate_start()

                # Always start with most current (on-disk) state information.
                self.__init_catalogs()

                ip.pkg_plans = pps

                ip.evaluate()
                if ip.reboot_needed() and self.is_liveroot():
                        raise api_errors.RebootNeededOnLiveImageException()

                logger.info("\n")
                for pp in ip.pkg_plans:
                        for lic, entry in pp.get_licenses():
                                dest = entry["dest"]
                                lic = dest.attrs["license"]
                                if show_licenses or dest.must_display:
                                        # Display license if required.
                                        logger.info("-" * 60)
                                        logger.info(_("Package: %s") % \
                                            pp.destination_fmri)
                                        logger.info(_("License: %s\n") % lic)
                                        logger.info(dest.get_text(self,
                                            pp.destination_fmri))
                                        logger.info("\n")

                                # Mark license as having been displayed.
                                pp.set_license_status(lic, displayed=True)

                                if dest.must_accept and accept:
                                        # Mark license as accepted if
                                        # required and requested.
                                        pp.set_license_status(lic,
                                            accepted=accept)

                ip.preexecute()
                ip.execute()

                return True

        def has_manifest(self, fmri):
                mpath = fmri.get_dir_path()

                local_mpath = "%s/pkg/%s/manifest" % (self.imgdir, mpath)

                if (os.path.exists(local_mpath)):
                        return True

                return False

        def get_manifest_path(self, fmri):
                """Return path to on-disk manifest"""
                mpath = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path(), "manifest")
                return mpath

        def __get_manifest(self, fmri, excludes=EmptyI, intent=None):
                """Find on-disk manifest and create in-memory Manifest
                object.... grab from server if needed"""

                try:
                        ret = manifest.CachedManifest(fmri, self.pkgdir,
                            self.cfg_cache.preferred_publisher,
                            excludes)
                        # if we have a intent string, let depot
                        # know for what we're using the cached manifest
                        if intent:
                                try:
                                        self.transport.touch_manifest(fmri, intent)
                                except (api_errors.UnknownPublisher,
                                    api_errors.TransportError):
                                        # It's not fatal if we can't find
                                        # or reach the publisher.
                                        pass
                except KeyError:
                        ret = self.transport.get_manifest(fmri, excludes,
                            intent)
                return ret

        def get_manifest(self, fmri, all_variants=False, intent=None):
                """return manifest; uses cached version if available.
                all_variants controls whether manifest contains actions
                for all variants"""

                # Normally elide other arch variants, facets

                if all_variants:
                        excludes = EmptyI
                else:
                        excludes = [ self.cfg_cache.variants.allow_action ]
 
                try:
                        m = self.__get_manifest(fmri, excludes=excludes,
                            intent=intent)
                except pkg.actions.ActionError, e:
                        raise api_errors.InvalidPackageErrors([e])

                return m

        def set_pkg_state(self, pfmri, state):
                """Sets the recorded image state of the specified package.
                The caller is responsible for also calling save_pkg_state
                after they are finished updating package state information.
                'state' must be one of the following image constants:

                    PKG_STATE_INSTALLED
                        Indicates that the package is installed.

                    PKG_STATE_KNOWN
                        Indicates that the package is currently present in
                        a repository catalog.

                    PKG_STATE_UNINSTALLED
                        Clears the INSTALLED state of the package.

                    PKG_STATE_UNKNOWN
                        Clears the KNOWN state of the package."""

                kcat = self.get_catalog(self.IMG_CATALOG_KNOWN)
                entry = kcat.get_entry(pfmri)

                mdata = entry.get("metadata", {})
                states = set(mdata.get("states", set()))
                if state == self.PKG_STATE_UNKNOWN:
                        states.discard(self.PKG_STATE_KNOWN)
                elif state == self.PKG_STATE_UNINSTALLED:
                        icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                        icat.remove_package(pfmri)
                        states.discard(self.PKG_STATE_INSTALLED)
                else:
                        # All other states should simply be added to the
                        # existing set of states.
                        states.add(state)

                if self.PKG_STATE_KNOWN not in states and \
                    self.PKG_STATE_INSTALLED not in states:
                        # This entry is no longer available and has no
                        # meaningful state information, so should be
                        # discarded.
                        kcat.remove_package(pfmri)
                        return

                if (self.PKG_STATE_INSTALLED in states and
                    self.PKG_STATE_UNINSTALLED in states) or (
                    self.PKG_STATE_KNOWN in states and
                    self.PKG_STATE_UNKNOWN in states):
                        raise api_errors.ImagePkgStateError(pfmri, states)

                # Catalog format only supports lists.
                mdata["states"] = list(states)

                # Now record the package state.
                kcat.update_entry(pfmri, metadata=mdata)

                if state == self.PKG_STATE_INSTALLED:
                        # If the package is being marked as installed, then
                        # it shouldn't already exist in the installed catalog
                        # and should be added.
                        icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                        icat.append(kcat, pfmri=pfmri)
                        self.__catalog_new_installs.add(pfmri)
                elif self.PKG_STATE_INSTALLED in states:
                        # If some other state has been changed and the package
                        # is still marked as installed, then simply update the
                        # existing entry (which should already exist).
                        icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                        icat.update_entry(pfmri, metadata=mdata)

        def save_pkg_state(self):
                """Saves current package state information."""

                # Temporarily redirect the catalogs to a different location,
                # so that if the save is interrupted, the image won't be left
                # with invalid state, and then save them.
                tmp_state_root = self.temporary_dir()

                try:
                        for name in (self.IMG_CATALOG_KNOWN,
                            self.IMG_CATALOG_INSTALLED):
                                cpath = os.path.join(tmp_state_root, name)

                                # Must copy the old catalog data to the new
                                # destination as only changed files will be
                                # written.
                                cat = self.get_catalog(name)
                                shutil.copytree(cat.meta_root, cpath)
                                cat.meta_root = cpath
                                cat.finalize(pfmris=self.__catalog_new_installs)
                                cat.save()

                        # Next, preserve the old installed state dir, rename the
                        # new one into place, and then remove the old one.
                        state_root = os.path.join(self.imgdir, "state")
                        orig_state_root = self.__salvagedir(state_root)
                        portable.rename(tmp_state_root, state_root)
                        shutil.rmtree(orig_state_root, True)
                finally:
                        # Regardless of success, the following must happen.
                        for name in (self.IMG_CATALOG_KNOWN,
                            self.IMG_CATALOG_INSTALLED):
                                cat = self.get_catalog(name)
                                cat.meta_root = os.path.join(self.imgdir,
                                    "state", name)
                        if os.path.exists(tmp_state_root):
                                shutil.rmtree(tmp_state_root, True)

        def get_catalog(self, name):
                """Returns the requested image catalog.

                'name' must be one of the following image constants:
                    IMG_CATALOG_KNOWN
                        The known catalog contains all of packages that are
                        installed or available from a publisher's repository.

                    IMG_CATALOG_INSTALLED
                        The installed catalog is a subset of the 'known'
                        catalog that only contains installed packages."""

                if not self.imgdir:
                        raise RuntimeError("self.imgdir must be set")

                try:
                        return self.__catalogs[name]
                except KeyError:
                        pass

                return self.__get_catalog(name)

        def __get_catalog(self, name):
                """Private method to retrieve catalog; this bypasses the
                normal automatic caching."""

                croot = os.path.join(self.imgdir, "state", name)
                try:
                        os.makedirs(croot)
                except EnvironmentError, e:
                        if e.errno in (errno.EACCES, errno.EROFS):
                                # Allow operations to work for
                                # unprivileged users.
                                croot = None
                        elif e.errno != errno.EEXIST:
                                raise

                def manifest_cb(cat, f):
                        # Only allow lazy-load for packages from non-v1 sources.
                        # Assume entries for other sources have all data
                        # required in catalog.  This prevents manifest retrieval
                        # for packages that don't have any related action data
                        # in the catalog because they don't have any related
                        # action data in their manifest.
                        entry = cat.get_entry(f)
                        states = entry["metadata"]["states"]
                        if self.PKG_STATE_V1 not in states:
                                return self.get_manifest(f, all_variants=True)
                        return None

                # batch_mode is set to True here as any operations that modify
                # the catalogs (add or remove entries) are only done during an
                # image upgrade or metadata refresh.  In both cases, the catalog
                # is resorted and finalized so this is always safe to use.
                cat = pkg.catalog.Catalog(batch_mode=True,
                    manifest_cb=manifest_cb, meta_root=croot, sign=False)
                self.__catalogs[name] = cat
                return cat

        def __remove_catalogs(self):
                """Removes all image catalogs and their directories."""

                self.__init_catalogs()
                for name in (self.IMG_CATALOG_KNOWN,
                    self.IMG_CATALOG_INSTALLED):
                        shutil.rmtree(os.path.join(self.imgdir, "state", name))

        def get_version_installed(self, pfmri):
                """Returns an fmri of the installed package matching the
                package stem of the given fmri or None if no match is found."""

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                for ver, fmris in cat.fmris_by_version(pfmri.pkg_name):
                        return fmris[0]
                return None

        def fmri_set_default_publisher(self, fmri):
                """If the FMRI supplied as an argument does not have
                a publisher, set it to the image's preferred publisher."""

                if fmri.has_publisher():
                        return

                fmri.set_publisher(self.get_preferred_publisher(), True)

        def has_version_installed(self, fmri):
                """Check that the version given in the FMRI or a successor is
                installed in the current image."""

                v = self.get_version_installed(fmri)

                if v and not fmri.publisher:
                        fmri.set_publisher(v.get_publisher_str())
                elif not fmri.publisher:
                        fmri.set_publisher(self.get_preferred_publisher(), True)

                if v and v.is_successor(fmri):
                        return True
                return False

        def get_pkg_state(self, pfmri):
                """Returns the list of states a package is in for this image."""

                cat = self.get_catalog(self.IMG_CATALOG_KNOWN)
                entry = cat.get_entry(pfmri)
                if entry is None:
                        return []
                return entry["metadata"]["states"]

        def is_pkg_installed(self, pfmri):
                """Returns a boolean value indicating whether the specified
                package is installed."""

                # Avoid loading the installed catalog if the known catalog
                # is already loaded.  This is safe since the installed
                # catalog is a subset of the known, and a specific entry
                # is being retrieved.
                if not self.__catalog_loaded(self.IMG_CATALOG_KNOWN):
                        cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                else:
                        cat = self.get_catalog(self.IMG_CATALOG_KNOWN)

                entry = cat.get_entry(pfmri)
                if entry is None:
                        return False
                states = entry["metadata"]["states"]
                return self.PKG_STATE_INSTALLED in states

        def list_excludes(self, new_variants=None, new_facets=None):
                """Generate a list of callables that each return True if an
                action is to be included in the image using the currently
                defined variants & facets for the image, or an updated set if
                new_variants or new_facets are specified."""

                if new_variants:
                        new_vars = self.cfg_cache.variants.copy()
                        new_vars.update(new_variants)
                        var_call = new_vars.allow_action
                else:
                        var_call = self.cfg_cache.variants.allow_action
                if new_facets:
                        fac_call = new_facets.allow_action
                else:
                        fac_call = self.cfg_cache.facets.allow_action

                return [var_call, fac_call]

        def get_variants(self):
                """ return a copy of the current image variants"""
                return self.cfg_cache.variants.copy()

        def get_facets(self):
                """ Return a copy of the current image facets"""
                return self.cfg_cache.facets.copy()

        def __build_dependents(self, progtrack):
                """Build a dictionary mapping packages to the list of packages
                that have required dependencies on them."""

                self.__req_dependents = {}

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                for f, actions in cat.actions([cat.DEPENDENCY],
                    excludes=self.list_excludes()):
                        progtrack.evaluate_progress(f)
                        for a in actions:
                                if a.name != "depend" or \
                                    a.attrs["type"] != "require":
                                        continue
                                name = self.strtofmri(a.attrs["fmri"]).pkg_name
                                self.__req_dependents.setdefault(name, []).append(f)

        def get_dependents(self, pfmri, progtrack):
                """Return a list of the packages directly dependent on the given
                FMRI."""

                if self.__req_dependents is None:
                        self.__build_dependents(progtrack)

                return self.__req_dependents.get(pfmri.pkg_name, [])

        def __rebuild_image_catalogs(self, progtrack=None):
                """Rebuilds the image catalogs based on the available publisher
                catalogs."""

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                progtrack.cache_catalogs_start()

                publist = list(self.gen_publishers())
                if not publist:
                        # No publishers, so nothing can be known or installed.
                        self.__remove_catalogs()
                        progtrack.cache_catalogs_done()
                        return

                self.history.log_operation_start("rebuild-image-catalogs")

                # Mark all operations as occurring at this time.
                op_time = datetime.datetime.utcnow()

                # The image catalogs need to be updated, but this is a bit
                # tricky as previously known packages must remain known even
                # if PKG_STATE_KNOWN is no longer true if any other state
                # information is present.  This is to allow freezing, etc. of
                # package states on a permanent basis even if the package is
                # no longer available from a publisher repository.  However,
                # this is only True of installed packages.
                old_icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)

                # batch_mode is set to True here since without it, catalog
                # population time is almost doubled (since the catalog is
                # re-sorted and stats are generated for every operation).
                # In addition, the new catalog is first created in a new
                # temporary directory so that it can be moved into place
                # at the very end of this process (to minimize the chance
                # that failure or interruption will cause the image to be
                # left in an inconsistent state).
                tmp_state_root = self.temporary_dir()

                kcat = pkg.catalog.Catalog(batch_mode=True,
                    meta_root=os.path.join(tmp_state_root,
                    self.IMG_CATALOG_KNOWN), sign=False)

                # XXX if any of the below fails for any reason, the old 'known'
                # catalog needs to be re-loaded so the client is in a consistent
                # state.

                # All enabled publisher catalogs must be processed.
                pub_cats = [(pub.prefix, pub.catalog) for pub in publist]

                # XXX For backwards compatibility, 'upgradability' of packages
                # is calculated and stored based on whether a given pkg stem
                # matches the newest version in the catalog.  This is quite
                # expensive (due to overhead), but at least the cost is
                # consolidated here.  This comparison is also cross-publisher,
                # as it used to be.  In the future, it could likely be improved
                # by usage of the SAT solver.
                newest = {}
                for pfx, cat in [(None, old_icat)] + pub_cats:
                        for f in cat.fmris(last=True, pubs=[pfx]):
                                nver, snver = newest.get(f.pkg_name, (None,
                                    None))
                                if f.version > nver:
                                        newest[f.pkg_name] = (f.version,
                                            str(f.version))

                # Next, copy all of the entries for the catalog parts that
                # currently exist into the image 'known' catalog.

                # Iterator for source parts.
                sparts = (
                   (pfx, cat, name, cat.get_part(name, must_exist=True))
                   for pfx, cat in pub_cats
                   for name in cat.parts
                )

                # Build list of installed packages based on actual state
                # information just in case there is a state issue from an
                # older client.
                inst_stems = {}
                for t, entry in old_icat.tuple_entries():
                        states = entry["metadata"]["states"]
                        if self.PKG_STATE_INSTALLED not in states:
                                continue
                        pub, stem, ver = t
                        inst_stems.setdefault(pub, {})
                        inst_stems[pub].setdefault(stem, {})
                        inst_stems[pub][stem][ver] = False

                # Create the new installed catalog in a temporary location.
                icat = pkg.catalog.Catalog(batch_mode=True,
                    meta_root=os.path.join(tmp_state_root,
                    self.IMG_CATALOG_INSTALLED), sign=False)

                for pfx, cat, name, spart in sparts:
                        # 'spart' is the source part.
                        if spart is None:
                                # Client hasn't retrieved this part.
                                continue

                        # New known part.
                        nkpart = kcat.get_part(name)
                        nipart = icat.get_part(name)
                        base = name.startswith("catalog.base.")

                        # Avoid accessor overhead since this will be
                        # used for every entry.
                        cat_ver = cat.version

                        for t, sentry in spart.tuple_entries(pubs=[pfx]):
                                pub, stem, ver = t

                                installed = False
                                if pub in inst_stems and \
                                    stem in inst_stems[pub] and \
                                    ver in inst_stems[pub][stem]:
                                        installed = True
                                        inst_stems[pub][stem][ver] = True

                                # copy() is too slow here and catalog entries
                                # are shallow so this should be sufficient.
                                entry = dict(sentry.iteritems())
                                if not base:
                                        # Nothing else to do except add the
                                        # entry for non-base catalog parts.
                                        nkpart.add(metadata=entry,
                                            op_time=op_time, pub=pub, stem=stem,
                                            ver=ver)
                                        if installed:
                                                nipart.add(metadata=entry,
                                                    op_time=op_time, pub=pub,
                                                    stem=stem, ver=ver)
                                        continue

                                # Only the base catalog part stores package
                                # state information and/or other metadata.
                                mdata = entry["metadata"] = {}
                                states = [self.PKG_STATE_KNOWN]
                                if cat_ver == 0:
                                        states.append(self.PKG_STATE_V0)
                                else:
                                        # Assume V1 catalog source.
                                        states.append(self.PKG_STATE_V1)

                                if installed:
                                        states.append(self.PKG_STATE_INSTALLED)

                                nver, snver = newest.get(stem, (None, None))
                                if snver is not None and ver != snver:
                                        states.append(self.PKG_STATE_UPGRADABLE)

                                # Determine if package is obsolete or has been
                                # renamed and mark with appropriate state.
                                dp = cat.get_part("catalog.dependency.C",
                                    must_exist=True)

                                dpent = None
                                if dp is not None:
                                        dpent = dp.get_entry(pub=pub, stem=stem,
                                            ver=ver)
                                if dpent is not None:
                                        for a in dpent["actions"]:
                                                if not a.startswith("set"):
                                                        continue

                                                if a.find("pkg.obsolete") != -1:
                                                        if a.find("true") == -1:
                                                                continue
                                                        states.append(
                                                            self.PKG_STATE_OBSOLETE)
                                                elif a.find("pkg.renamed") != -1:
                                                        if a.find("true") == -1:
                                                                continue
                                                        states.append(
                                                            self.PKG_STATE_RENAMED)
                                mdata["states"] = states

                                # Add base entries.
                                nkpart.add(metadata=entry, op_time=op_time,
                                    pub=pub, stem=stem, ver=ver)
                                if installed:
                                        nipart.add(metadata=entry,
                                            op_time=op_time, pub=pub, stem=stem,
                                            ver=ver)

                # Now add installed packages to list of known packages using
                # previous state information.  While doing so, track any
                # new entries as the versions for the stem of the entry will
                # need to be passed to finalize() for sorting.
                final_fmris = []
                for name in old_icat.parts:
                        # Old installed part.
                        ipart = old_icat.get_part(name, must_exist=True)

                        # New known part.
                        nkpart = kcat.get_part(name)

                        # New installed part.
                        nipart = icat.get_part(name)

                        base = name.startswith("catalog.base.")

                        mdata = None
                        for t, entry in ipart.tuple_entries():
                                pub, stem, ver = t

                                if pub not in inst_stems or \
                                    stem not in inst_stems[pub] or \
                                    ver not in inst_stems[pub][stem] or \
                                    inst_stems[pub][stem][ver]:
                                        # Entry is no longer valid or is already
                                        # known.
                                        continue

                                if base:
                                        mdata = entry["metadata"]
                                        states = set(mdata["states"])
                                        states.discard(self.PKG_STATE_KNOWN)

                                        nver, snver = newest.get(stem, (None,
                                            None))
                                        if snver is not None and ver == snver:
                                                states.discard(
                                                    self.PKG_STATE_UPGRADABLE)
                                        elif snver is not None:
                                                states.add(
                                                    self.PKG_STATE_UPGRADABLE)
                                        mdata["states"] = list(states)

                                # Add entries.
                                nkpart.add(metadata=entry, op_time=op_time,
                                    pub=pub, stem=stem, ver=ver)
                                nipart.add(metadata=entry, op_time=op_time,
                                    pub=pub, stem=stem, ver=ver)
                                final_fmris.append(pkg.fmri.PkgFmri(
                                    "%s@%s" % (stem, ver), publisher=pub))

                # Save the new catalogs.
                for cat in kcat, icat:
                        os.makedirs(cat.meta_root, mode=misc.PKG_DIR_MODE)
                        cat.finalize(pfmris=final_fmris)
                        cat.save()

                # Next, preserve the old installed state dir, rename the
                # new one into place, and then remove the old one.
                state_root = os.path.join(self.imgdir, "state")
                orig_state_root = self.__salvagedir(state_root)
                portable.rename(tmp_state_root, state_root)
                shutil.rmtree(orig_state_root, True)

                # Ensure in-memory catalogs get reloaded.
                self.__init_catalogs()

                progtrack.cache_catalogs_done()
                self.history.log_operation_end()

        def refresh_publishers(self, full_refresh=False, immediate=False,
            pubs=None, progtrack=None):
                """Refreshes the metadata (e.g. catalog) for one or more
                publishers.  Callers are responsible for locking the image.

                'full_refresh' is an optional boolean value indicating whether
                a full retrieval of publisher metadata (e.g. catalogs) or only
                an update to the existing metadata should be performed.  When
                True, 'immediate' is also set to True.

                'immediate' is an optional boolean value indicating whether the
                a refresh should occur now.  If False, a publisher's selected
                repository will only be checked for updates if the update
                interval period recorded in the image configuration has been
                exceeded.

                'pubs' is a list of publisher prefixes or publisher objects
                to refresh.  Passing an empty list or using the default value
                implies all publishers."""

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                self.history.log_operation_start("refresh-publishers")

                # Verify validity of certificates before attempting network
                # operations.
                try:
                        self.check_cert_validity()
                except api_errors.ExpiringCertificate, e:
                        logger.error(str(e))

                pubs_to_refresh = []

                if not pubs:
                        # Omit disabled publishers.
                        pubs = [p for p in self.gen_publishers()]
                for pub in pubs:
                        p = pub
                        if not isinstance(p, publisher.Publisher):
                                p = self.get_publisher(prefix=p)
                        if p.disabled:
                                e = api_errors.DisabledPublisher(p)
                                self.history.log_operation_end(error=e)
                                raise e
                        pubs_to_refresh.append(p)

                if not pubs_to_refresh:
                        self.history.log_operation_end()
                        return

                try:
                        # Ensure Image directory structure is valid.
                        self.mkdirs()
                except Exception, e:
                        self.history.log_operation_end(error=e)
                        raise

                progtrack.refresh_start(len(pubs_to_refresh))

                failed = []
                total = 0
                succeeded = set()
                updated = 0
                for pub in pubs_to_refresh:
                        total += 1
                        progtrack.refresh_progress(pub.prefix)
                        try:
                                if pub.refresh(full_refresh=full_refresh,
                                    immediate=immediate):
                                        updated += 1
                        except api_errors.PermissionsException, e:
                                failed.append((pub, e))
                                # No point in continuing since no data can
                                # be written.
                                break
                        except api_errors.ApiException, e:
                                failed.append((pub, e))
                                continue
                        succeeded.add(pub.prefix)
                progtrack.refresh_done()

                if updated:
                        self.__rebuild_image_catalogs(progtrack=progtrack)

                if failed:
                        e = api_errors.CatalogRefreshException(failed, total,
                            len(succeeded))
                        self.history.log_operation_end(error=e)
                        raise e
                self.history.log_operation_end()

        def _get_publisher_meta_dir(self):
                if self.__upgraded:
                        return IMG_PUB_DIR
                return "catalog"

        def _get_publisher_meta_root(self, prefix):
                return os.path.join(self.imgdir, self._get_publisher_meta_dir(),
                    prefix)

        def remove_publisher_metadata(self, pub, progtrack=None):
                """Removes the metadata for the specified publisher object."""

                pub.remove_meta_root()
                self.__rebuild_image_catalogs(progtrack=progtrack)

        def gen_installed_pkg_names(self, anarchy=True):
                """A generator function that produces FMRI strings as it
                iterates over the list of installed packages.  This is
                faster than gen_installed_pkgs when only the FMRI string
                is needed."""

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                for f in cat.fmris(objects=False):
                        if anarchy:
                                # Catalog entries always have publisher prefix.
                                yield "pkg:/%s" % f[6:].split("/", 1)[-1]
                                continue
                        yield f

        def gen_installed_pkgs(self):
                """Return an iteration through the installed packages."""

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                for f in cat.fmris():
                        yield f

        def get_installed_pubs(self):
                """Returns a set containing the prefixes of all publishers with
                installed packages."""

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                return cat.publishers()

        def __upgrade_image(self, progtrack=None):
                """Transform the existing image structure and its data to
                the newest format."""

                if self.__upgraded:
                        return

                assert self.imgdir

                def installed_file_publisher(filepath):
                        """Find the pkg's installed file named by filepath.
                        Return the publisher that installed this package."""

                        f = file(filepath)
                        try:
                                flines = f.readlines()
                                version, pub = flines
                                version = version.strip()
                                pub = pub.strip()
                                f.close()
                        except ValueError:
                                # If ValueError occurs, the installed file is of
                                # a previous format.  For upgrades to work, it's
                                # necessary to assume that the package was
                                # installed from the preferred publisher.  Here,
                                # the publisher is setup to record that.
                                if flines:
                                        pub = flines[0]
                                        pub = pub.strip()
                                        newpub = "%s_%s" % (
                                            pkg.fmri.PREF_PUB_PFX, pub)
                                else:
                                        newpub = "%s_%s" % (
                                            pkg.fmri.PREF_PUB_PFX,
                                            self.get_preferred_publisher())
                                pub = newpub
                        assert pub
                        return pub

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                # Not technically 'caching', but close enough ...
                progtrack.cache_catalogs_start()

                # First, load the old package state information.
                installed_state_dir = "%s/state/installed" % self.imgdir

                # If the state directory structure has already been created,
                # loading information from it is fast.  The directory is
                # populated with files, named by their (url-encoded) FMRI,
                # which point to the "installed" file in the corresponding
                # directory under /var/pkg.
                installed = {}
                def add_installed_entry(f):
                        path = "%s/pkg/%s/installed" % \
                            (self.imgdir, f.get_dir_path())
                        pub = installed_file_publisher(path)
                        f.set_publisher(pub)
                        installed[f.pkg_name] = f

                if os.path.isdir(installed_state_dir):
                        for pl in sorted(os.listdir(installed_state_dir)):
                                fmristr = "%s" % urllib.unquote(pl)
                                f = pkg.fmri.PkgFmri(fmristr)
                                add_installed_entry(f)
                else:
                        # Otherwise, we must iterate through the earlier
                        # installed state.  One day, this can be removed.
                        proot = "%s/pkg" % self.imgdir
                        for pd in sorted(os.listdir(proot)):
                                for vd in sorted(os.listdir("%s/%s" % \
                                    (proot, pd))):
                                        path = "%s/pkg/%s/installed" % \
                                            (self.imgdir, pd, vd)
                                        if not os.path.exists(path):
                                                continue

                                        fmristr = urllib.unquote("%s@%s" % (pd,
                                            vd))
                                        f = pkg.fmri.PkgFmri(fmristr)
                                        add_installed_entry(f)

                # Create the new image catalogs.
                kcat = pkg.catalog.Catalog(batch_mode=True, sign=False)
                icat = pkg.catalog.Catalog(batch_mode=True, sign=False)

                # XXX For backwards compatibility, 'upgradability' of packages
                # is calculated and stored based on whether a given pkg stem
                # matches the newest version in the catalog.  This is quite
                # expensive (due to overhead), but at least the cost is
                # consolidated here.  This comparison is also cross-publisher,
                # as it used to be.
                newest = {}
                old_pub_cats = []
                for pub in self.gen_publishers():
                        try:
                                old_cat = pkg.server.catalog.ServerCatalog(
                                    pub.meta_root, read_only=True,
                                    publisher=pub.prefix)

                                old_pub_cats.append((pub, old_cat))
                                for f in old_cat.fmris():
                                        nver = newest.get(f.pkg_name, None)
                                        newest[f.pkg_name] = max(nver,
                                            f.version)

                        except EnvironmentError, e:
                                # If a catalog file is just missing, ignore it.
                                # If there's a worse error, make sure the user
                                # knows about it.
                                if e.errno != errno.ENOENT:
                                        raise

                # Next, load the existing catalog data and convert it.
                pub_cats = []
                for pub, old_cat in old_pub_cats:
                        new_cat = pub.catalog
                        new_cat.batch_mode = True
                        new_cat.sign = False
                        if new_cat.exists:
                                new_cat.destroy()

                        # First convert the old publisher catalog to
                        # the new format.
                        for f in old_cat.fmris():
                                new_cat.add_package(f)

                                # Now populate the image catalogs.
                                states = [self.PKG_STATE_KNOWN,
                                    self.PKG_STATE_V0]
                                mdata = { "states": states }
                                if f.version != newest[f.pkg_name]:
                                        states.append(self.PKG_STATE_UPGRADABLE)

                                inst_fmri = installed.get(f.pkg_name, None)
                                if inst_fmri and \
                                    inst_fmri.version == f.version and \
                                    pkg.fmri.is_same_publisher(f.publisher,
                                    inst_fmri.publisher):
                                        states.append(self.PKG_STATE_INSTALLED)
                                        if inst_fmri.preferred_publisher():
                                                # Strip the PREF_PUB_PFX.
                                                inst_fmri.set_publisher(
                                                    inst_fmri.get_publisher())
                                        icat.add_package(f, metadata=mdata)
                                        del installed[f.pkg_name]
                                kcat.add_package(f, metadata=mdata)

                        # Normally, the Catalog's attributes are automatically
                        # populated as a result of catalog operations.  But in
                        # this case, the new Catalog's attributes should match
                        # those of the old catalog.
                        old_lm = old_cat.last_modified()
                        if old_lm:
                                # Can be None for empty v0 catalogs.
                                old_lm = pkg.catalog.ts_to_datetime(old_lm)
                        new_cat.last_modified = old_lm
                        new_cat.version = 0

                        # Add to the list of catalogs to save.
                        new_cat.batch_mode = False
                        pub_cats.append(new_cat)

                # Discard the old catalog objects.
                old_pub_cats = None

                for f in installed.values():
                        # Any remaining FMRIs need to be added to all of the
                        # image catalogs.
                        states = [self.PKG_STATE_INSTALLED, self.PKG_STATE_V0]
                        mdata = { "states": states }
                        # This package may be installed from a publisher that
                        # is no longer known or has been disabled.
                        if f.pkg_name in newest and \
                            f.version != newest[f.pkg_name]:
                                states.append(self.PKG_STATE_UPGRADABLE)

                        if f.preferred_publisher():
                                # Strip the PREF_PUB_PFX.
                                f.set_publisher(f.get_publisher())

                        icat.add_package(f, metadata=mdata)
                        kcat.add_package(f, metadata=mdata)

                for cat in pub_cats + [kcat, icat]:
                        cat.finalize()

                # Data conversion finished.
                self.__upgraded = True

                try:
                        # Ensure Image directory structure is valid.
                        self.mkdirs()
                except api_errors.PermissionsException, e:
                        progtrack.cache_catalogs_done()

                        # An unprivileged user is attempting to use the
                        # new client with an old image.  Since none of
                        # the changes can be saved, warn the user and
                        # then return.

                        # Because the new image catalogs couldn't be saved,
                        # store them in the image's internal cache so that
                        # operations can function as expected.
                        self.__catalogs[self.IMG_CATALOG_KNOWN] = kcat
                        self.__catalogs[self.IMG_CATALOG_INSTALLED] = icat

                        # Raising an exception here would be a decidedly
                        # bad thing as it would disrupt find_root, etc.
                        logger.warning("Package operation performance is "
                            "currently degraded.\nThis can be resolved by "
                            "executing 'pkg refresh' as a privileged user.\n")
                        return

                # This has to be done after the permissions check above.
                tmp_state_root = self.temporary_dir()

                # Create new image catalogs.
                kcat.meta_root = os.path.join(tmp_state_root,
                    self.IMG_CATALOG_KNOWN)
                icat.meta_root = os.path.join(tmp_state_root,
                    self.IMG_CATALOG_INSTALLED)

                # Assume that since mkdirs succeeded that the remaining data
                # can be saved and the image structure can be upgraded.  But
                # first, attempt to save the image catalogs before changing
                # structure.
                for cat in icat, kcat:
                        os.makedirs(cat.meta_root, mode=misc.PKG_DIR_MODE)
                        cat.save()

                # Next, reset the publisher meta_roots to reflect the new
                # directory structure and move each publisher's catalog files
                # to the new catalog root.
                for pub in self.gen_publishers():
                        old_root = pub.meta_root
                        pub.meta_root = self._get_publisher_meta_root(
                            pub.prefix)
                        pub.create_meta_root()
                        for fname in os.listdir(old_root):
                                src = os.path.join(old_root, fname)
                                if fname == "last_refreshed":
                                        dest = os.path.join(pub.meta_root,
                                            fname)
                                else:
                                        dest = os.path.join(pub.catalog_root,
                                            fname)
                                portable.rename(src, dest)

                # Next, save all of the new publisher catalogs.
                for cat in pub_cats:
                        cat.save()

                # Next, preserve the old catalog and state directories.
                # Then, rename the new state directory into place, and then
                # remove the old catalog and state directories.
                cat_root = os.path.join(self.imgdir, "catalog")
                orig_cat_root = self.__salvagedir(cat_root)

                state_root = os.path.join(self.imgdir, "state")
                orig_state_root = self.__salvagedir(state_root)

                portable.rename(tmp_state_root, state_root)

                # Ensure in-memory catalogs get reloaded.
                self.__init_catalogs()

                # Finally, dump the old, unused dirs and mark complete.
                shutil.rmtree(orig_cat_root, True)
                shutil.rmtree(orig_state_root, True)
                progtrack.cache_catalogs_done()

        def strtofmri(self, myfmri):
                return pkg.fmri.PkgFmri(myfmri, self.attrs["Build-Release"])

        def strtomatchingfmri(self, myfmri):
                return pkg.fmri.MatchingPkgFmri(myfmri,
                    self.attrs["Build-Release"])

        def get_user_by_name(self, name):
                return portable.get_user_by_name(name, self.root,
                    self.type != IMG_USER)

        def get_name_by_uid(self, uid, returnuid = False):
                # XXX What to do about IMG_PARTIAL?
                try:
                        return portable.get_name_by_uid(uid, self.root,
                            self.type != IMG_USER)
                except KeyError:
                        if returnuid:
                                return uid
                        else:
                                raise

        def get_group_by_name(self, name):
                return portable.get_group_by_name(name, self.root,
                    self.type != IMG_USER)

        def get_name_by_gid(self, gid, returngid = False):
                try:
                        return portable.get_name_by_gid(gid, self.root,
                            self.type != IMG_USER)
                except KeyError:
                        if returngid:
                                return gid
                        else:
                                raise

        @staticmethod
        def __multimatch(name, patterns):
                """Applies a matcher to a name across a list of patterns.
                Returns all tuples of patterns which match the name.  Each tuple
                contains the index into the original list, the pattern itself,
                the package version, the publisher, and the raw publisher
                string."""
                return [
                    (i, pat, pat.tuple()[2],
                        pat.publisher, pat.publisher)
                    for i, (pat, m) in enumerate(patterns)
                    if m(name, pat.tuple()[1])
                ]

        def __inventory(self, patterns=None, all_known=False, matcher=None,
            constraint=pkg.version.CONSTRAINT_AUTO, ordered=True):
                """Private method providing the back-end for inventory()."""

                if not matcher:
                        matcher = pkg.fmri.fmri_match

                if not patterns:
                        patterns = []

                # Store the original patterns before we possibly turn them into
                # PkgFmri objects, so we can give them back to the user in error
                # messages.
                opatterns = patterns[:]

                # Match the matching function with the pattern so that we can
                # change it per-pattern, depending on whether it has glob
                # characters or nails down the pattern with a leading pkg:/.
                patterns = [ (i, matcher) for i in patterns ]

                illegals = []
                for i, (pat, m) in enumerate(patterns):
                        if not isinstance(pat, pkg.fmri.PkgFmri):
                                try:
                                        if "*" in pat or "?" in pat:
                                                patterns[i] = (
                                                    pkg.fmri.MatchingPkgFmri(
                                                        pat, "5.11"),
                                                    pkg.fmri.glob_match)
                                        elif pat.startswith("pkg:/"):
                                                patterns[i] = (
                                                    pkg.fmri.PkgFmri(pat,
                                                        "5.11"),
                                                    pkg.fmri.exact_name_match)
                                        else:
                                                patterns[i] = (
                                                    pkg.fmri.PkgFmri(pat,
                                                        "5.11"),
                                                    pkg.fmri.fmri_match)
                                except pkg.fmri.IllegalFmri, e:
                                        illegals.append(e)

                if illegals:
                        raise api_errors.InventoryException(illegal=illegals)

                # matchingpats is the set of all the patterns which matched a
                # package in the catalog.  This allows us to return partial
                # failure if some patterns match and some don't.
                # XXX It would be nice to keep track of why some patterns failed
                # to match -- based on name, version, or publisher.
                matchingpats = set()

                if all_known:
                        cat = self.get_catalog(self.IMG_CATALOG_KNOWN)
                else:
                        cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)

                if ordered:
                        names = sorted(cat.names())
                else:
                        names = cat.names()

                for name in names:
                        # Eliminate all patterns not matching "name".  If there
                        # are no patterns left, go on to the next name, but only
                        # if there were any to start with.
                        matches = self.__multimatch(name, patterns)
                        if patterns and not matches:
                                continue

                        rversions = reversed(list(cat.entries_by_version(name)))
                        for ver, entries in rversions:
                                # If a pattern specified a version and that
                                # version isn't succeeded by "ver", then record
                                # the pattern for removal from consideration.
                                nomatch = []
                                for i, match in enumerate(matches):
                                        if match[2] and \
                                            not ver.is_successor(match[2],
                                                constraint):
                                                nomatch.append(i)

                                # Eliminate the name matches that didn't match
                                # on versions.  We need to create a new list
                                # because we need to reuse the original
                                # "matches" for each new version.
                                vmatches = [
                                    matches[i]
                                    for i, match in enumerate(matches)
                                    if i not in nomatch
                                ]

                                # If we deleted all contenders (if we had any to
                                # begin with), go on to the next version.
                                if matches and not vmatches:
                                        continue

                                # Like the version skipping above, do the same
                                # for publishers.
                                publist = set([f[0].publisher for f in entries])

                                nomatch = []
                                for i, match in enumerate(vmatches):
                                        if match[3] and \
                                            match[3] not in publist:
                                                nomatch.append(i)

                                pmatches = [
                                    vmatches[i]
                                    for i, match in enumerate(vmatches)
                                    if i not in nomatch
                                ]

                                if vmatches and not pmatches:
                                        continue

                                # If no patterns were specified or any still-
                                # matching pattern specified no publisher, we
                                # use the entire list of publishers for this
                                # version.  Otherwise, we use the intersection
                                # of the list of publishers in pubstate, and
                                # the publishers in the patterns.
                                aset = set(i[3] for i in pmatches)
                                if aset and None not in aset:
                                        publist = set(
                                            m[3]
                                            for m in pmatches
                                            if m[3] in publist
                                        )

                                matchingpats |= set(i[:2] for i in vmatches)

                                for f, entry in entries:
                                        if f.publisher not in publist:
                                                continue

                                        states = entry["metadata"]["states"]

                                        known = self.PKG_STATE_KNOWN in states
                                        st = {
                                            "frozen": False,
                                            "in_catalog": known,
                                            "incorporated": False,
                                            "excludes": False,
                                            "upgradable": self.PKG_STATE_UPGRADABLE in states,
                                            "obsolete": self.PKG_STATE_OBSOLETE in states,
                                            "renamed": self.PKG_STATE_RENAMED in states
                                        }

                                        if self.PKG_STATE_INSTALLED in states:
                                                st["state"] = \
                                                    self.PKG_STATE_INSTALLED
                                        elif known:
                                                # XXX long-term, a package could
                                                # be 'frozen' or something else
                                                # and no longer available (in a
                                                # catalog).
                                                st["state"] = \
                                                    self.PKG_STATE_KNOWN
                                        else:
                                                # Must be in some other state;
                                                # see comment above.
                                                st["state"] = None

                                        yield f, st

                nonmatchingpats = [
                    opatterns[i]
                    for i, f in set(enumerate((p[0] for p in patterns))) - matchingpats
                ]

                if nonmatchingpats:
                        raise api_errors.InventoryException(
                            notfound=nonmatchingpats)

        def inventory(self, *args, **kwargs):
                """Enumerate the package FMRIs in the image's catalog, yielding
                a list of tuples of the format (fmri, pkg state dict).

                If "patterns" is None (the default) or an empty sequence, all
                package names will match.  Otherwise, it is a list of patterns
                to match against FMRIs in the catalog.

                If "all_known" is False (the default), only installed packages
                will be enumerated.  If True, all known packages will be
                enumerated.

                The "matcher" parameter should specify a function taking two
                string arguments: a name and a pattern, returning True if the
                pattern matches the name, and False otherwise.  By default, the
                matcher will be pkg.fmri.fmri_match().

                The "constraint" parameter defines how a version specified in a
                pattern matches a version in the catalog.  By default, a natural
                "subsetting" constraint is used.

                The "ordered" parameter is a boolean value that indicates
                whether the returned list should first be sorted by name before
                being sorted by version (descending).  By default, this is True.
                """

                # "preferred" is a private argument that is currently only used
                # in evaluate_fmri(), but could be made more generally useful.
                # "preferred" ensures that all potential matches from the
                # preferred publisher are generated before those from
                # non-preferred publishers.  In the current implementation, this
                # consumes more memory.
                preferred = kwargs.pop("preferred", False)
                if not preferred:
                        for f in self.__inventory(*args, **kwargs):
                                yield f
                else:
                        ppub = self.get_preferred_publisher()
                        nplist = []
                        for f in self.__inventory(*args, **kwargs):
                                if f[0].publisher == ppub:
                                        yield f
                                else:
                                        nplist.append(f)

                        for f in nplist:
                                yield f

        def update_index_dir(self, postfix="index"):
                """Since the index directory will not reliably be updated when
                the image root is, this should be called prior to using the
                index directory.
                """
                self.index_dir = os.path.join(self.imgdir, postfix)

        def incoming_download_dir(self):
                """Return the directory path for incoming downloads
                that have yet to be completed.  Once a file has been
                successfully downloaded, it is moved to the cached download
                directory."""

                return self.dl_cache_incoming

        def cached_download_dir(self):
                """Return the directory path for cached content.
                Files that have been successfully downloaded live here."""

                return self.dl_cache_dir

        def cleanup_downloads(self):
                """Clean up any downloads that were in progress but that
                did not successfully finish."""

                shutil.rmtree(self.dl_cache_incoming, True)

        def cleanup_cached_content(self):
                """Delete the directory that stores all of our cached
                downloaded content.  This may take a while for a large
                directory hierarchy.  Don't clean up caches if the
                user overrode the underlying setting using PKG_CACHEDIR. """

                if not self.is_user_cache_dir and \
                    self.cfg_cache.get_policy(imageconfig.FLUSH_CONTENT_CACHE):
                        logger.info("Deleting content cache")
                        shutil.rmtree(self.dl_cache_dir, True)

        def __salvagedir(self, path):
                sdir = os.path.normpath(
                    os.path.join(self.imgdir, "lost+found",
                    path + "-" + time.strftime("%Y%m%dT%H%M%SZ")))

                parent = os.path.dirname(sdir)
                if not os.path.exists(parent):
                        os.makedirs(parent)
                shutil.move(os.path.normpath(os.path.join(self.root, path)),
                    sdir)
                return sdir

        def salvagedir(self, path):
                """Called when directory contains something and it's not
                supposed to because it's being deleted. XXX Need to work out a
                better error passback mechanism. Path is rooted in /...."""

                sdir = self.__salvagedir(path)
                logger.warning("\nWarning - directory %s not empty - contents "
                    "preserved in %s" % (path, sdir))

        def temporary_dir(self):
                """create a temp directory under image directory for various
                purposes"""
                tempdir = os.path.normpath(os.path.join(self.imgdir, "tmp"))
                try:
                        if not os.path.exists(tempdir):
                                os.makedirs(tempdir)
                        rval = tempfile.mkdtemp(dir=tempdir)

                        # Force standard mode.
                        os.chmod(rval, misc.PKG_DIR_MODE)
                        return rval
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

        def temporary_file(self):
                """create a temp file under image directory for various
                purposes"""
                tempdir = os.path.normpath(os.path.join(self.imgdir, "tmp"))
                try:
                        if not os.path.exists(tempdir):
                                os.makedirs(tempdir)
                        fd, name = tempfile.mkstemp(dir=tempdir)
                        os.close(fd)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise
                return name

        def __filter_install_matches(self, matches):
                """Attempts to eliminate redundant matches found during
                packaging operations:

                    * First, stems of installed packages for publishers that
                      are now unknown (no longer present in the image
                      configuration) are dropped.

                    * Second, if multiple matches are still present, stems of
                      of installed packages, that are not presently in the
                      corresponding publisher's catalog, are dropped.

                    * Finally, if multiple matches are still present, all
                      stems except for those in state PKG_STATE_INSTALLED are
                      dropped.

                Returns a list of the filtered matches, along with a dict of
                their unique names."""

                olist = []
                onames = set()

                # First eliminate any duplicate matches that are for unknown
                # publishers (publishers which have been removed from the image
                # configuration).
                publist = set(p.prefix for p in self.get_publishers().values())
                for m, st in matches:
                        if m.publisher in publist:
                                onames.add(m.get_pkg_stem())
                                olist.append((m, st))

                # Next, if there are still multiple matches, eliminate matches
                # belonging to publishers that no longer have the FMRI in their
                # catalog.
                found_state = False
                if len(onames) > 1:
                        mlist = []
                        mnames = set()
                        for m, st in olist:
                                if not st["in_catalog"]:
                                        continue
                                if st["state"] == self.PKG_STATE_INSTALLED:
                                        found_state = True
                                mnames.add(m.get_pkg_stem())
                                mlist.append((m, st))
                        olist = mlist
                        onames = mnames

                # Finally, if there are still multiple matches, and a known
                # stem is installed, then eliminate any stems that do not
                # have an installed version.
                if found_state and len(onames) > 1:
                        mlist = []
                        mnames = set()
                        for m, st in olist:
                                if st["state"] == self.PKG_STATE_INSTALLED:
                                        mnames.add(m.get_pkg_stem())
                                        mlist.append((m, st))
                        olist = mlist
                        onames = mnames

                return olist, onames

        def make_install_plan(self, pkg_list, progtrack, check_cancelation,
            noexecute, verbose=False):
                """Take a list of packages, specified in pkg_list, and attempt
                to assemble an appropriate image plan.  This is a helper
                routine for some common operations in the client.
                """

                ip = imageplan.ImagePlan(self, progtrack, check_cancelation,
                    noexecute=noexecute)

                progtrack.evaluate_start()

                # Always start with most current (on-disk) state information.
                self.__init_catalogs()

                try:
                        ip.plan_install(pkg_list)
                except pkg.actions.ActionError, e:
                        raise api_errors.InvalidPackageErrors([e])
                except api_errors.ApiException:
                        ip.show_failure(verbose)
                        raise

                try:
                        self.__call_imageplan_evaluate(ip, verbose)
                except pkg.actions.ActionError, e:
                        raise api_errors.InvalidPackageErrors([e])

        def make_update_plan(self, progtrack, check_cancelation,
            noexecute, verbose=False):
                """Create a plan to update all packages as far as
                possible."""

                progtrack.evaluate_start()

                ip = imageplan.ImagePlan(self, progtrack, check_cancelation,
                    noexecute=noexecute)

                # Always start with most current (on-disk) state information.
                self.__init_catalogs()

                try:
                        ip.plan_update()
                        self.__call_imageplan_evaluate(ip, verbose)
                except pkg.actions.ActionError, e:
                        raise api_errors.InvalidPackageErrors([e])

        def make_uninstall_plan(self, fmri_list, recursive_removal,
            progtrack, check_cancelation, noexecute, verbose=False):
                """Create uninstall plan to remove the specified packages;
                do so recursively iff recursive_removal is set"""

                progtrack.evaluate_start()

                ip = imageplan.ImagePlan(self, progtrack,
                    check_cancelation, noexecute=noexecute)

                # Always start with most current (on-disk) state information.
                self.__init_catalogs()

                try:
                        ip.plan_uninstall(fmri_list, recursive_removal)
                        self.__call_imageplan_evaluate(ip, verbose)
                except pkg.actions.ActionError, e:
                        raise api_errors.InvalidPackageErrors([e])

        def ipkg_is_up_to_date(self, actual_cmd, check_cancelation, noexecute,
            refresh_allowed=True, progtrack=None):
                """ Test whether SUNWipkg is updated to the latest version
                    known to be available for this image """

                #
                # This routine makes the distinction between the "target image",
                # which will be altered, and the "running image", which is
                # to say whatever image appears to contain the version of the
                # pkg command we're running.
                #

                #
                # There are two relevant cases here:
                #     1) Packaging code and image we're updating are the same
                #        image.  (i.e. 'pkg image-update')
                #
                #     2) Packaging code's image and the image we're updating are
                #        different (i.e. 'pkg image-update -R')
                #
                # In general, we care about getting the user to run the
                # most recent packaging code available for their build.  So,
                # if we're not in the liveroot case, we create a new image
                # which represents "/" on the system.
                #

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                img = self

                if not img.is_liveroot():
                        cmdpath = os.path.join(os.getcwd(), actual_cmd)
                        cmdpath = os.path.realpath(cmdpath)
                        cmddir = os.path.dirname(os.path.realpath(cmdpath))
                        #
                        # Find the path to ourselves, and use that
                        # as a way to locate the image we're in.  It's
                        # not perfect-- we could be in a developer's
                        # workspace, for example.
                        #
                        newimg = Image(cmddir, progtrack=progtrack)

                        if refresh_allowed:
                                # If refreshing publisher metadata is allowed,
                                # then perform a refresh so that a new SUNWipkg
                                # can be discovered.
                                newimg.lock()
                                try:
                                        newimg.refresh_publishers(
                                            progtrack=progtrack)
                                except api_errors.CatalogRefreshException, cre:
                                        cre.errmessage = \
                                            _("SUNWipkg update check failed.")
                                        raise
                                finally:
                                        newimg.unlock()

                        img = newimg

                # XXX call to progress tracker that SUNWipkg is being refreshed

                img.make_install_plan(["SUNWipkg"], progtrack,
                    check_cancelation, noexecute)

                return img.imageplan.nothingtodo()

        def installed_fmris_from_args(self, args):
                """Helper function to translate client command line arguments
                into a list of installed fmris.  Used by info, contents,
                verify.
                """
                found = []
                notfound = []
                illegals = []
                try:
                        for m in self.inventory(args, ordered=False):
                                found.append(m)
                except api_errors.InventoryException, e:
                        illegals = e.illegal
                        notfound = e.notfound
                return found, notfound, illegals
