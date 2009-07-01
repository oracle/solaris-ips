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

import datetime as dt
import errno
import os
import platform
import shutil
import tempfile
import time
import urllib

import pkg.Uuid25
import pkg.catalog                      as catalog
import pkg.client.api_errors            as api_errors
import pkg.client.constraint            as constraint
import pkg.client.history               as history
import pkg.client.imageconfig           as imageconfig
import pkg.client.imageplan             as imageplan
import pkg.client.imagestate            as imagestate
import pkg.client.pkgplan               as pkgplan
import pkg.client.progress              as progress
import pkg.client.publisher             as publisher
import pkg.client.transport.transport   as transport
import pkg.client.variant               as variant
import pkg.fmri
import pkg.manifest                     as manifest
import pkg.misc                         as misc
import pkg.portable                     as portable
import pkg.version

from pkg.client import global_settings
from pkg.client.imagetypes import IMG_USER, IMG_ENTIRE
from pkg.misc import CfgCacheError
from pkg.misc import EmptyI, EmptyDict
from pkg.misc import msg, emsg

CATALOG_CACHE_FILE = "catalog_cache"
img_user_prefix = ".org.opensolaris,pkg"
img_root_prefix = "var/pkg"

PKG_STATE_INSTALLED = "installed"
PKG_STATE_KNOWN = "known"

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

          $IROOT/catalog
               Directory containing catalogs for URIs of interest.  Filename is
               the escaped URI of the catalog.

          $IROOT/file
               Directory containing file hashes of installed packages.

          $IROOT/pkg
               Directory containing manifests and states of installed packages.

          $IROOT/index
               Directory containing reverse-index databases.

          $IROOT/cfg_cache
               File containing image's cached configuration.

          $IROOT/opaque
               File containing image's opaque state.

          $IROOT/state/installed
               Directory containing files whose names identify the installed
               packages.

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

        required_subdirs = [ "catalog", "file", "pkg" ]
        image_subdirs = required_subdirs + [ "index", "state/installed" ]

        def __init__(self):
                self.cfg_cache = None
                self.type = None
                self.root = None
                self.history = history.History()
                self.imgdir = None
                self.pkgdir = None
                self.img_prefix = None
                self.index_dir = None
                self.repo_uris = []
                self.filter_tags = {}
                self.__catalogs = {}
                self._catalog = {}
                self.__pkg_states = None
                self.dl_cache_dir = None
                self.dl_cache_incoming = None
                self.is_user_cache_dir = False
                self.state = imagestate.ImageState(self)
                self.attrs = {
                    "Policy-Require-Optional": False,
                    "Policy-Pursue-Latest": True
                }
                self.__catalog_cache_mod_time = None

                self.imageplan = None # valid after evaluation succeeds

                self.constraints = constraint.ConstraintSet()

                # Transport operations for this image
                self.transport = transport.Transport(self)

                # a place to keep info about saved_files; needed by file action
                self.saved_files = {}

                self.__manifest_cache = {}

                # right now we don't explicitly set dir/file modes everywhere;
                # set umask to proper value to prevent problems w/ overly
                # locked down umask.
                os.umask(0022)

        def _check_subdirs(self, sub_d, prefix):
                for n in self.required_subdirs:
                        if not os.path.isdir(os.path.join(sub_d, prefix, n)):
                                return False
                return True

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

        def find_root(self, d, exact_match=False):
                # Ascend from the given directory d to find first
                # encountered image. If exact_match is true, if the
                # image found doesn't match startd, raise an
                # ImageNotFoundException.
                startd = d
                # eliminate problem if relative path such as "." is passed in
                d = os.path.realpath(d)
                while True:
                        imgtype = self.image_type(d)
                        if imgtype == IMG_USER:
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                if exact_match and \
                                    os.path.realpath(startd) != \
                                    os.path.realpath(d):
                                        raise api_errors.ImageNotFoundException(
                                            exact_match, startd, d)
                                self.__set_dirs(imgtype=imgtype, root=d)
                                self.attrs["Build-Release"] = "5.11"
                                return
                        elif imgtype == IMG_ENTIRE:
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                if exact_match and \
                                    os.path.realpath(startd) != \
                                    os.path.realpath(d):
                                        raise api_errors.ImageNotFoundException(
                                            exact_match, startd, d)
                                self.__set_dirs(imgtype=imgtype, root=d)
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

        def load_config(self):
                """Load this image's cached configuration from the default
                location."""

                # XXX Incomplete with respect to doc/image.txt description of
                # configuration.

                if self.root == None:
                        raise RuntimeError, "self.root must be set"

                ic = imageconfig.ImageConfig(self.root)
                ic.read(self.imgdir)

                # make sure we define architecture variant; upgrade config
                # file if possible.
                changed = False
                if "variant.arch" not in ic.variants:
                        ic.variants["variant.arch"] = platform.processor()
                        try:
                                ic.write(self.imgdir)
                                changed = True
                        except api_errors.PermissionsException:
                                pass
                # make sure we define zone variant; upgrade config if possible
                if "variant.opensolaris.zone" not in ic.variants:
                        zone = ic.filters.get("opensolaris.zone", "")
                        if zone == "nonglobal":
                                ic.variants[
                                    "variant.opensolaris.zone"] = "nonglobal"
                        else:
                                ic.variants[
                                    "variant.opensolaris.zone"] = "global"
                        try:
                                ic.write(self.imgdir)
                                changed = True
                        except api_errors.PermissionsException:
                                pass

                #
                # If we made changes to the configuration, reload it;
                # this lets any processing which is a side-effect of
                # these changes take place.
                #
                if changed:
                        ic = imageconfig.ImageConfig(self.root)
                        ic.read(self.imgdir)

                self.cfg_cache = ic

        def save_config(self):
                # First, create the image directories if they haven't been, so
                # the cfg_cache can be written.
                self.mkdirs()
                self.cfg_cache.write(self.imgdir)

        # XXX mkdirs and set_attrs() need to be combined into a create
        # operation.
        def mkdirs(self):
                for sd in self.image_subdirs:
                        if not os.path.isdir(os.path.join(self.imgdir, sd)):
                                os.makedirs(os.path.join(self.imgdir, sd))

        def __set_dirs(self, imgtype, root):
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

                self.imgdir = os.path.join(self.root, self.img_prefix)
                self.pkgdir = os.path.join(self.imgdir, "pkg")
                self.history.root_dir = self.imgdir

                if "PKG_CACHEDIR" in os.environ:
                        self.dl_cache_dir = os.path.normpath( \
                            os.environ["PKG_CACHEDIR"])
                        self.is_user_cache_dir = True
                else:
                        self.dl_cache_dir = os.path.normpath( \
                            os.path.join(self.imgdir, "download"))
                self.dl_cache_incoming = os.path.normpath(os.path.join(
                    self.dl_cache_dir, "incoming-%d" % os.getpid()))

        def set_attrs(self, imgtype, root, is_zone, prefix, pub_url,
            ssl_key=None, ssl_cert=None, variants=EmptyDict,
            refresh_allowed=True, progtrack=None):

                self.__set_dirs(imgtype=imgtype, root=root)

                # Create the publisher object before creating the image...
                repo = publisher.Repository()
                repo.add_origin(pub_url, ssl_cert=ssl_cert, ssl_key=ssl_key)
                newpub = publisher.Publisher(prefix,
                    meta_root=self._get_publisher_meta_root(prefix),
                    repositories=[repo])

                # Initialize and store the configuration object.
                self.cfg_cache = imageconfig.ImageConfig(self.root)

                # ...so that if creation of the Publisher object fails, an
                # empty, useless image won't be left behind.
                if not os.path.exists(os.path.join(self.imgdir,
                    imageconfig.CFG_FILE)):
                        self.history.log_operation_start("image-create")
                else:
                        self.history.log_operation_start("image-set-attributes")

                # Determine and add the default variants for the image.
                if is_zone:
                        self.cfg_cache.filters["opensolaris.zone"] = "nonglobal"
                        self.cfg_cache.variants[
                            "variant.opensolaris.zone"] = "nonglobal"
                else:
                        self.cfg_cache.variants[
                            "variant.opensolaris.zone"] = "global"

                self.cfg_cache.variants["variant.arch"] = \
                    variants.get("variant.arch", platform.processor())

                # After setting up the default variants, add any overrides or
                # additional variants specified.
                self.cfg_cache.variants.update(variants)

                # Now everything is ready for publisher configuration.
                self.cfg_cache.preferred_publisher = newpub.prefix
                self.add_publisher(newpub, refresh_allowed=refresh_allowed,
                    progtrack=progtrack)

                # No need to save configuration as add_publisher will do that
                # if successful.

                self.history.log_operation_end()

        def is_liveroot(self):
                return self.root == "/"

        def is_zone(self):
                return self.cfg_cache.variants[
                    "variant.opensolaris.zone"] == "nonglobal"

        def get_arch(self):
                return self.cfg_cache.variants["variant.arch"]

        def get_root(self):
                return self.root

        def gen_publishers(self, inc_disabled=False):
                if not self.cfg_cache:
                        raise CfgCacheError, "empty ImageConfig"
                for p in self.cfg_cache.publishers:
                        pub = self.cfg_cache.publishers[p]
                        if inc_disabled or not pub.disabled:
                                yield self.cfg_cache.publishers[p]

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
                for pub in self.gen_publishers():
                        if prefix == pub.prefix or (alias and
                            alias == pub.alias):
                                return True
                return False

        def remove_publisher(self, prefix=None, alias=None, progtrack=None):
                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                self.history.log_operation_start("remove-publisher")
                try:
                        pub = self.get_publisher(prefix=prefix,
                            alias=alias)
                except api_errors.ApiException, e:
                        self.history.log_operation_end(e)
                        raise

                if pub.prefix == self.cfg_cache.preferred_publisher:
                        e = api_errors.RemovePreferredPublisher()
                        self.history.log_operation_end(error=e)
                        raise e

                self.cfg_cache.remove_publisher(prefix)
                self.save_config()
                self.remove_publisher_metadata(pub)
                self.load_catalogs(progtrack, force=True)
                self.history.log_operation_end()

        def get_publishers(self):
                return self.cfg_cache.publishers

        def get_publisher(self, prefix=None, alias=None, origin=None):
                publishers = [p for p in self.get_publishers().values()]
                for pub in publishers:
                        if prefix and prefix == pub.prefix:
                                return pub
                        elif alias and alias == pub.alias:
                                return pub
                        elif origin and \
                            pub.selected_repository.has_origin(origin):
                                return pub
                raise api_errors.UnknownPublisher(max(prefix, alias, origin))

        def get_publisher_last_update_time(self, prefix, cached=True):
                """Returns a datetime object (or 'None') representing the last
                time the catalog for a publisher was updated.

                If the catalog has already been loaded, this reflects the
                in-memory state of the catalog.

                If the catalog has not already been loaded or 'cached' is False,
                then the catalog will be temporarily loaded and the most recent
                information returned."""

                if not cached:
                        try:
                                cat = self.__catalogs[prefix]
                        except KeyError:
                                pass
                        else:
                                update_dt = cat.last_modified()
                                if update_dt:
                                        update_dt = catalog.ts_to_datetime(
                                            update_dt)
                                return update_dt

                # Temporarily retrieve the catalog object, but don't
                # cache it as that would interfere with load_catalogs.
                try:
                        croot = "%s/catalog/%s" % (self.imgdir, prefix)
                        cat = catalog.Catalog(croot, publisher=prefix)
                except (EnvironmentError, catalog.CatalogException):
                        cat = None

                update_dt = None
                if cat:
                        update_dt = cat.last_modified()
                        if update_dt:
                                update_dt = catalog.ts_to_datetime(update_dt)
                return update_dt

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

                self.history.log_operation_start("set-preferred-publisher")

                if not pub:
                        try:
                                pub = self.get_publisher(prefix=prefix,
                                    alias=alias)
                        except api_errors.UnknownPublisher, e:
                                self.history.log_operation_end(error=e)
                                raise

                if pub.disabled:
                        e = api_errors.SetPreferredPublisherDisabled(pub)
                        self.history.log_operation_end(error=e)
                        raise e
                self.cfg_cache.preferred_publisher = pub.prefix
                self.save_config()
                self.history.log_operation_end()

        def set_property(self, prop_name, prop_value):
                assert prop_name != "preferred-publisher"
                self.cfg_cache.properties[prop_name] = prop_value
                self.save_config()

        def get_property(self, prop_name):
                return self.cfg_cache.properties[prop_name]

        def has_property(self, prop_name):
                return prop_name in self.cfg_cache.properties

        def delete_property(self, prop_name):
                assert prop_name != "preferred-publisher"
                del self.cfg_cache.properties[prop_name]
                self.save_config()

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
                self.history.log_operation_start("add-publisher")
                for p in self.cfg_cache.publishers.values():
                        if pub == p or (pub.alias and pub.alias == p.alias):
                                error = api_errors.DuplicatePublisher(pub)
                                self.history.log_operation_end(error=error)
                                raise error

                # Must assign this first before performing any more operations.
                pub.meta_root = self._get_publisher_meta_root(pub.prefix)
                self.cfg_cache.publishers[pub.prefix] = pub

                # This ensures that if data is leftover from a publisher
                # with the same prefix as this one that it gets purged
                # first to prevent usage of stale data.
                self.remove_publisher_metadata(pub)

                if refresh_allowed:
                        try:
                                # First, verify that the publisher has a valid
                                # pkg(5) repository.
                                self.transport.valid_publisher_test(pub)

                                self.__retrieve_catalogs(full_refresh=True,
                                    pubs=[pub], progtrack=progtrack)
                        except Exception, e:
                                # Remove the newly added publisher since the
                                # retrieval failed.
                                del self.cfg_cache.publishers[pub.prefix]
                                self.history.log_operation_end(error=e)
                                raise
                        except:
                                # Remove the newly added publisher since the
                                # retrieval failed.
                                del self.cfg_cache.publishers[pub.prefix]
                                self.history.log_operation_end(
                                    result=history.RESULT_FAILED_UNKNOWN)
                                raise

                # Only after success should the configuration be saved.
                self.save_config()
                self.history.log_operation_end()

        def verify(self, fmri, progresstracker, **args):
                """generator that returns any errors in installed pkgs
                as tuple of action, list of errors"""

                for act in self.get_manifest(fmri).gen_actions(
                    self.list_excludes()):
                        errors = act.verify(self, pkg_fmri=fmri, **args)
                        progresstracker.verify_add_progress(fmri)
                        actname = act.distinguished_name()
                        if errors:
                                progresstracker.verify_yield_error(actname,
                                    errors)
                                yield (act, errors)

        def repair(self, repairs, progtrack):
                """Repair any actions in the fmri that failed a verify."""
                # XXX: This (lambda x: False) is temporary until we move pkg fix
                # into the api and can actually use the
                # api::__check_cancelation() function.
                pps = []
                for fmri, actions in repairs:
                        msg("Repairing: %-50s" % fmri.get_pkg_stem())
                        m = self.get_manifest(fmri)
                        pp = pkgplan.PkgPlan(self, progtrack, lambda: False)
                        pp.propose_repair(fmri, m, actions)
                        pp.evaluate(self.list_excludes(), self.list_excludes())
                        pps.append(pp)

                ip = imageplan.ImagePlan(self, progtrack, lambda: False)
                progtrack.evaluate_start()
                ip.pkg_plans = pps

                ip.evaluate()
                ip.preexecute()
                ip.execute()

                return True

        def has_manifest(self, fmri):
                mpath = fmri.get_dir_path()

                local_mpath = "%s/pkg/%s/manifest" % (self.imgdir, mpath)

                if (os.path.exists(local_mpath)):
                        return True

                return False

        def __fetch_manifest(self, fmri, excludes=EmptyI):
                """A wrapper call for getting manifests.  This invokes
                the transport method, gets the manifest, and performs
                any additional image-related processing."""

                m = self.transport.get_manifest(fmri, excludes,
                    self.state.get_intent_str(fmri))

                # What is the client currently processing?
                targets = self.state.get_targets()
                
                intent = None
                for entry in targets:
                        target, reason = entry

                        # Ignore the publisher for comparison.
                        np_target = target.get_fmri(anarchy=True)
                        np_fmri = fmri.get_fmri(anarchy=True)
                        if np_target == np_fmri:
                                intent = reason

                # If no intent could be found, assume INTENT_INFO.
                self.state.set_touched_manifest(fmri, 
                    max(intent, imagestate.INTENT_INFO))

                return m

        def __touch_manifest(self, fmri):
                """Perform steps necessary to 'touch' a manifest to provide
                intent information.  Ignores most exceptions as this operation
                is only for informational purposes."""

                # What is the client currently processing?
                target, intent = self.state.get_target()

                # Ignore dry-runs of operations or operations which do not have
                # a set target.
                if not target or intent == imagestate.INTENT_EVALUATE:
                        return

                if not self.state.get_touched_manifest(fmri, intent):
                        # If the manifest for this fmri hasn't been "seen"
                        # before, determine if intent information needs to be
                        # provided.

                        # Ignore the publisher for comparison.
                        np_target = target.get_fmri(anarchy=True)
                        np_fmri = fmri.get_fmri(anarchy=True)
                        if np_target == np_fmri:
                                # If the client is currently processing
                                # the given fmri (for an install, etc.)
                                # then intent information is needed.
                                try:
                                        self.transport.touch_manifest(fmri,
                                            self.state.get_intent_str(fmri))
                                except (api_errors.UnknownPublisher,
                                    api_errors.TransportError), e:
                                        # It's not fatal if we can't find
                                        # or reach the publisher.
                                        pass
                                self.state.set_touched_manifest(fmri, intent)

        def get_manifest_path(self, fmri):
                """Return path to on-disk manifest"""
                mpath = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path(), "manifest")
                return mpath

        def __get_manifest(self, fmri, excludes=EmptyI):
                """Find on-disk manifest and create in-memory Manifest
                object.... grab from server if needed"""

                try:
                        return manifest.CachedManifest(fmri, self.pkgdir,
                            self.cfg_cache.preferred_publisher,
                            excludes)
                except KeyError:
                        return self.__fetch_manifest(fmri, excludes)

        def get_manifest(self, fmri, add_to_cache=True, all_arch=False):
                """return manifest; uses cached version if available.
                all_arch controls whether manifest contains actions
                for all architectures"""

                # Normally elide other arch variants
                if all_arch:
                        add_to_cache = False
                        v = EmptyI
                else:
                        arch = {"variant.arch": self.get_arch()}
                        v = [variant.Variants(arch).allow_action]

                # XXX This is a temporary workaround so that GUI api consumsers
                # are not negatively impacted by manifest caching.  This should
                # be removed by bug 4231 whenever a better way to handle caching
                # is found.
                if global_settings.client_name == "pkg" and not all_arch:
                        if fmri in self.__manifest_cache:
                                m = self.__manifest_cache[fmri]
                        else:
                                m = self.__get_manifest(fmri, v)
                                if add_to_cache:
                                        self.__manifest_cache[fmri] = m
                else:
                        m = self.__get_manifest(fmri, v)

                self.__touch_manifest(fmri)
                return m

        def uncache_manifest(self, fmri):
                """Remove specified FMRI from manifest cache."""

                if fmri in self.__manifest_cache:
                        del self.__manifest_cache[fmri]

        def installed_file_publisher(self, filepath):
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
                        # If we get a ValueError, we've encountered an
                        # installed file of a previous format.  If we want
                        # upgrade to work in this situation, it's necessary
                        # to assume that the package was installed from
                        # the preferred publisher.  Here, we set up
                        # the publisher to record that.
                        if flines:
                                pub = flines[0]
                                pub = pub.strip()
                                newpub = "%s_%s" % (pkg.fmri.PREF_PUB_PFX,
                                    pub)
                        else:
                                newpub = "%s_%s" % (pkg.fmri.PREF_PUB_PFX,
                                    self.get_preferred_publisher())

                        pub = newpub

                        try:
                                f = file(filepath, "w")
                                f.writelines(["VERSION_1\n", newpub])
                                f.close()
                        except IOError, e:
                                if e.errno not in (errno.EACCES, errno.EROFS):
                                        raise
                assert pub

                return pub

        def _install_file(self, fmri):
                """Returns the path to the "installed" file for a given fmri."""

                return "%s/pkg/%s/installed" % (self.imgdir,
                    fmri.get_dir_path())

        def install_file_present(self, fmri):
                """Returns true if the package named by the fmri is installed
                on the system.  Otherwise, returns false."""

                return os.path.exists(self._install_file(fmri))

        def add_install_file(self, fmri):
                """Take an image and fmri. Write a file to disk that
                indicates that the package named by the fmri has been
                installed."""

                # XXX This can be removed at some point in the future once we
                # think this link is available on all systems
                if not os.path.isdir("%s/state/installed" % self.imgdir):
                        self.__update_installed_pkgs()

                try:
                        f = file(self._install_file(fmri), "w")
                except EnvironmentError:
                        try:
                                os.makedirs(os.path.dirname(
                                    self._install_file(fmri)))
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno != errno.EEXIST and \
                                    not os.path.isdir(e.filename):
                                        raise

                        f = file(self._install_file(fmri), "w")

                f.writelines(["VERSION_1\n", fmri.get_publisher_str()])
                f.close()

                fi = file("%s/state/installed/%s" % (self.imgdir,
                    fmri.get_link_path()), "w")
                fi.close()
                self.__pkg_states[urllib.unquote(fmri.get_link_path())] = \
                    (PKG_STATE_INSTALLED, fmri)

        def remove_install_file(self, fmri):
                """Take an image and a fmri.  Remove the file from disk
                that indicates that the package named by the fmri has been
                installed."""

                # XXX This can be removed at some point in the future once we
                # think this link is available on all systems
                if not os.path.isdir("%s/state/installed" % self.imgdir):
                        self.__update_installed_pkgs()

                os.unlink(self._install_file(fmri))
                try:
                        os.unlink("%s/state/installed/%s" % (self.imgdir,
                            fmri.get_link_path()))
                except EnvironmentError, e:
                        if e.errno != errno.ENOENT:
                                raise
                self.__pkg_states[urllib.unquote(fmri.get_link_path())] = \
                    (PKG_STATE_KNOWN, fmri)

        def __update_installed_pkgs(self):
                """Take the image's record of installed packages from the
                prototype layout, with an installed file in each
                $META/pkg/stem/version directory, to the $META/state/installed
                summary directory form."""

                # If the directory is empty or it doesn't exist, we should
                # populate it.  The easy test is to try to remove the directory,
                # which will fail if it's already got entries in it, or doesn't
                # exist.  Other errors are beyond our capability to handle.
                statedir = os.path.join(self.imgdir, "state", "installed")
                try:
                        os.rmdir(statedir)
                except EnvironmentError, e:
                        if e.errno in (errno.EEXIST, errno.ENOTEMPTY):
                                return
                        elif e.errno == errno.EACCES:
                                # The directory may exist and be non-empty
                                # even though we got EACCES.  Try
                                # to determine its emptiness another way.
                                try:
                                        if os.path.isdir(statedir) and \
                                            len(os.listdir(statedir)) > 0:
                                                return
                                except EnvironmentError:
                                        # ignore this error, pass on the
                                        # original access error
                                        pass
                                raise api_errors.PermissionsException(
                                    e.filename)
                        elif e.errno != errno.ENOENT:
                                raise

                tmpdir = os.path.join(self.imgdir, "state", "installed.build")

                # Create the link forest in a temporary directory.  We should
                # only execute this method once (if ever) in the lifetime of an
                # image, but if the path already exists and makedirs() blows up,
                # just be quiet if it's already a directory.  If it's not a
                # directory or something else weird happens, re-raise.
                try:
                        os.makedirs(tmpdir)
                except OSError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno != errno.EEXIST or \
                            not os.path.isdir(tmpdir):
                                raise
                        return

                proot = os.path.join(self.imgdir, "pkg")

                for pd, vd in (
                    (p, v)
                    for p in sorted(os.listdir(proot))
                    for v in sorted(os.listdir(os.path.join(proot, p)))
                    ):
                        path = os.path.join(proot, pd, vd, "installed")
                        if not os.path.exists(path):
                                continue

                        fmristr = urllib.unquote("%s@%s" % (pd, vd))
                        pub = self.installed_file_publisher(path)
                        f = pkg.fmri.PkgFmri(fmristr, publisher = pub)
                        fi = file(os.path.join(tmpdir, f.get_link_path()), "w")
                        fi.close()

                # Someone may have already created this directory.  Junk the
                # directory we just populated if that's the case.
                try:
                        portable.rename(tmpdir, statedir)
                except EnvironmentError, e:
                        if e.errno != errno.EEXIST:
                                raise
                        shutil.rmtree(tmpdir)

        def get_version_installed(self, pfmri):
                """Returns an fmri of the installed package matching the
                package stem of the given fmri or None if no match is found."""

                for f in self.gen_installed_pkgs():
                        if self.fmri_is_same_pkg(f, pfmri):
                                return f
                return None

        def get_pkg_state_by_fmri(self, pfmri):
                """Given pfmri, determine the local state of the package."""

                return self.__pkg_states.get(pfmri.get_fmri(anarchy = True)[5:],
                    (PKG_STATE_KNOWN, None))[0]

        def get_pkg_pub_by_fmri(self, pfmri):
                """Return the publisher from which 'pfmri' was installed."""

                f = self.__pkg_states.get(pfmri.get_fmri(anarchy = True)[5:],
                    (PKG_STATE_KNOWN, None))[1]
                if f:
                        # Return the non-preferred-prefixed name
                        return f.get_publisher()
                return None

        def fmri_set_default_publisher(self, fmri):
                """If the FMRI supplied as an argument does not have
                a publisher, set it to the image's preferred publisher."""

                if fmri.has_publisher():
                        return

                fmri.set_publisher(self.get_preferred_publisher(), True)

        def get_catalog(self, fmri, exception = False):
                """Given a FMRI, look at the publisher and return the
                correct catalog for this image."""

                # If FMRI has no publisher, or is default publisher,
                # then return the catalog for the preferred publisher
                if not fmri.has_publisher() or fmri.preferred_publisher():
                        cat = self.__catalogs[self.get_preferred_publisher()]
                else:
                        try:
                                cat = self.__catalogs[fmri.get_publisher()]
                        except KeyError:
                                # If the publisher that installed this package
                                # has vanished, pick the default publisher
                                # instead.
                                if exception:
                                        raise
                                else:
                                        cat = self.__catalogs[\
                                            self.get_preferred_publisher()]

                return cat

        def has_version_installed(self, fmri):
                """Check that the version given in the FMRI or a successor is
                installed in the current image."""

                v = self.get_version_installed(fmri)

                if v and not fmri.has_publisher():
                        fmri.set_publisher(v.get_publisher_str())
                elif not fmri.has_publisher():
                        fmri.set_publisher(self.get_preferred_publisher(), True)

                if v and self.fmri_is_successor(v, fmri):
                        return True
                else:
                        try:
                                cat = self.get_catalog(fmri, exception = True)
                        except KeyError:
                                return False

                        # If fmri has been renamed, get the list of newer
                        # packages that are equivalent to fmri.
                        rpkgs = cat.rename_newer_pkgs(fmri)
                        for f in rpkgs:

                                v = self.get_version_installed(f)

                                if v and self.fmri_is_successor(v, fmri):
                                        return True

                return False

        def older_version_installed(self, fmri):
                """This method is used by the package plan to determine if an
                older version of the package is installed.  This takes
                the destination fmri and checks if an older package exists.
                This looks first under the existing name, and then sees
                if an older version is installed under another name.  This
                allows upgrade correctly locate the src fmri, if one exists."""

                v = self.get_version_installed(fmri)

                assert fmri.has_publisher()

                if v:
                        return v
                else:
                        cat = self.get_catalog(fmri)

                        rpkgs = cat.rename_older_pkgs(fmri)
                        for f in rpkgs:
                                v = self.get_version_installed(f)
                                if v and self.fmri_is_successor(fmri, v):
                                        return v

                return None

        def is_installed(self, fmri):
                """Check that the exact version given in the FMRI is installed
                in the current image."""

                # All FMRIs passed to is_installed shall have a publisher
                assert fmri.has_publisher()

                v = self.get_version_installed(fmri)
                if not v:
                        return False

                return v == fmri

        def list_excludes(self, new_variants=None):
                """Generate a list of callables that each return True if an
                action is to be included in the image using the currently
                defined variants for the image, or an updated set if
                new_variants are specified.  The callables take a single action
                argument.  Variants, facets and filters will be handled in
                this fashion."""

                # XXX simple for now; facets and filters need impl.
                if new_variants:
                        new_vars = self.cfg_cache.variants.copy()
                        new_vars.update(new_variants)
                        return [new_vars.allow_action]
                else:
                        return [self.cfg_cache.variants.allow_action]

        def __build_dependents(self, progtrack):
                """Build a dictionary mapping packages to the list of packages
                that have required dependencies on them."""

                self.__req_dependents = {}

                for fmri in self.gen_installed_pkgs():
                        progtrack.evaluate_progress(fmri)
                        mfst = self.get_manifest(fmri)

                        for dep in mfst.gen_actions_by_type("depend",
                            self.list_excludes()):
                                if dep.attrs["type"] != "require":
                                        continue
                                dfmri = self.strtofmri(dep.attrs["fmri"])
                                if dfmri not in self.__req_dependents:
                                        self.__req_dependents[dfmri] = []
                                self.__req_dependents[dfmri].append(fmri)

        def get_dependents(self, pfmri, progtrack):
                """Return a list of the packages directly dependent on the given
                FMRI."""

                if not hasattr(self, "_Image__req_dependents"):
                        self.__build_dependents(progtrack)

                dependents = []
                # We run through all the keys, in case a package is depended
                # upon under multiple versions.  That is, if pkgA depends on
                # libc@1 and pkgB depends on libc@2, we need to return both pkgA
                # and pkgB.  If we used package names as keys, this would be
                # simpler, but it wouldn't handle package rename.
                for f in self.__req_dependents.iterkeys():
                        if self.fmri_is_successor(pfmri, f):
                                dependents.extend(self.__req_dependents[f])
                return dependents

        def refresh_publishers(self, full_refresh=False, immediate=False,
            pubs=None, progtrack=None, validate=True):
                """Refreshes the metadata (e.g. catalog) for one or more
                publishers.

                'full_refresh' is an optional boolean value indicating whether
                a full retrieval of publisher metadata (e.g. catalogs) or only
                an update to the existing metadata should be performed.  When
                True, 'immediate' is also set to True.

                'immediate' is an optional boolean value indicating whether the
                a refresh should occur now.  If False, a publisher's selected
                repository will only be checked for updates if the update
                interval period recorded in the image configuration has been
                exceeded; ignored when 'full_refresh' is True.

                'pubs' is a list of publisher prefixes or publisher objects
                to refresh.  Passing an empty list or using the default value
                implies all publishers.

                'validate' is an optional, boolean value indicating whether a
                connectivity test should be performed before attempting to
                retrieve publisher metadata."""

                if full_refresh:
                        immediate = True

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                self.history.log_operation_start("refresh-publishers")

                # Verify validity of certificates before attempting network
                # operations.
                try:
                        self.check_cert_validity()
                except api_errors.ExpiringCertificate, e:
                        # XXX need client messaging framework
                        misc.emsg(e)

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
                        if immediate or p.needs_refresh:
                                pubs_to_refresh.append(p)

                if not pubs_to_refresh:
                        # Trigger a load of the catalogs if they haven't been
                        # loaded yet for the sake of our caller.
                        self.load_catalogs(progtrack)
                        self.history.log_operation_end()
                        return

                try:
                        if validate:
                                # Before an attempt is made to retrieve catalogs
                                # from the publisher repositories, a check needs
                                # to be done to ensure that the client isn't
                                # stuck behind a captive portal.
                                self.transport.captive_portal_test()

                        self.__retrieve_catalogs(full_refresh=full_refresh,
                            pubs=pubs_to_refresh, progtrack=progtrack)
                except (api_errors.ApiException, catalog.CatalogException), e:
                        # Reload catalogs; this picks up any updates and
                        # ensures the catalog is loaded for callers.
                        self.load_catalogs(progtrack, force=True)
                        self.history.log_operation_end(error=e)
                        raise
                self.history.log_operation_end()

        def __retrieve_catalogs(self, full_refresh=False, pubs=None,
            progtrack=None):
                """Retrieves the catalogs for the specified publishers
                performing full or incremental updates as needed or indicated.

                'full_refresh' is a boolean value indicating whether a full
                update should be forced for the specified publishers.

                'pubs' is an optional list of publisher objects to refresh the
                metadata for.  If not provided or 'None', all publishers will be
                refreshed.  Disabled publishers are always ignored regardless of
                whether this list is provided.

                'progtrack' is an optional ProgressTracker object."""

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                failed = []
                total = 0

                if not pubs:
                        pubs = list(self.gen_publishers())

                try:
                        # Ensure Image directory structure is valid.
                        self.mkdirs()

                        # Load the catalogs, if they haven't been already, so
                        # incremental updates can be performed.
                        self.load_catalogs(progtrack)
                except EnvironmentError, e:
                        self.history.log_operation_end(error=e)
                        raise

                progtrack.refresh_start(len(pubs))

                def catalog_changed(prefix, old_ts, old_size):
                        if not old_ts or not old_size:
                                # It didn't exist before.
                                return True

                        croot = "%s/catalog/%s" % (self.imgdir, prefix)
                        c = catalog.Catalog(croot, publisher=prefix)
                        if c.last_modified() != old_ts:
                                return True
                        if c.size() != old_size:
                                return True
                        return False

                updated = 0
                succeeded = 0
                for pub in pubs:
                        if pub.disabled:
                                continue

                        total += 1
                        progtrack.refresh_progress(pub.prefix)

                        full_refresh_this_pub = False

                        cat = None
                        ts = None
                        size = 0
                        if pub.prefix in self.__catalogs:
                                cat = self.__catalogs[pub.prefix]
                                ts = cat.last_modified()
                                size = cat.size()

                                # Although we may have a catalog with a
                                # timestamp, the user may have changed the
                                # origin URL for the publisher.  If this has
                                # occurred, we need to perform a full refresh.
                                repo = pub.selected_repository
                                if cat.origin() not in repo.origins:
                                        full_refresh_this_pub = True

                        if full_refresh or full_refresh_this_pub:
                                # Set timestamp to None in order
                                # to perform full refresh.
                                ts = None

                        try:
                                self.transport.get_catalog(pub, ts)
                        except api_errors.TransportError, e:
                                failed.append((pub, e))
                        else:
                                if catalog_changed(pub.prefix, ts, size):
                                        updated += 1
                                pub.last_refreshed = dt.datetime.utcnow()
                                succeeded += 1

                if updated > 0:
                        # If any publisher metadata was changed, then destroy
                        # the catalog cache, update the installed package list,
                        # and force a reload of all catalog data.
                        self.__destroy_catalog_cache()
                        self.__update_installed_pkgs()
                        self.load_catalogs(progtrack, force=True)

                progtrack.refresh_done()

                if failed:
                        raise api_errors.CatalogRefreshException(failed, total,
                            succeeded)

                return updated > 0

        CATALOG_CACHE_VERSION = 4

        def __cache_catalogs(self, progtrack, pubs=None):
                """Read in all the catalogs and cache the data.

                'pubs' is a list of publisher objects to include when caching
                the image's configured publisher metadata.
                """

                progtrack.cache_catalogs_start()
                cache = {}
                publist = []

                try:
                        publist = dict(
                            (p.prefix, p) for p in self.gen_publishers()
                        )
                except CfgCacheError:
                        # No publishers defined.  If the caller hasn't
                        # supplied publishers to cache, raise the error
                        if not pubs:
                                raise

                if pubs:
                        # If caller passed publishers, include this in
                        # the list of publishers to cache.  These might
                        # be publisher objects that haven't been added
                        # to the image configuration yet.
                        for p in pubs:
                                publist[p.prefix] = p

                for pub in publist.itervalues():
                        try:
                                catalog.Catalog.read_catalog(cache,
                                    pub.meta_root, pub=pub.prefix)
                        except EnvironmentError, e:
                                # If a catalog file is just missing, ignore it.
                                # If there's a worse error, make sure the user
                                # knows about it.
                                if e.errno == errno.ENOENT:
                                        pass
                                else:
                                        raise

                self._catalog = cache

                # Use the current time until the actual file timestamp can be
                # retrieved at the end.  That way, if an exception is raised
                # or an early return occurs, it will still be set.
                self.__catalog_cache_mod_time = int(time.time())

                # Remove old catalog cache files.
                croot = os.path.join(self.imgdir, "catalog")
                for fname in ("pkg_names.pkl", "catalog.pkl"):
                        fpath = os.path.join(croot, fname)
                        try:
                                portable.remove(fpath)
                        except KeyboardInterrupt:
                                raise
                        except:
                                # If for any reason, the file can't be removed,
                                # it doesn't matter.
                                pass

                try:
                        cfd, ctmp = tempfile.mkstemp(dir=croot)
                        cf = os.fdopen(cfd, "wb")
                except EnvironmentError:
                        # If the cache can't be written, it doesn't matter.
                        progtrack.cache_catalogs_done()
                        return

                def cleanup():
                        try:
                                if cf:
                                        cf.close()
                        except EnvironmentError:
                                pass

                        try:
                                portable.remove(ctmp)
                        except EnvironmentError:
                                pass

                # First, the list of all publishers is built assigning each
                # one a sequentially incremented integer as they are discovered.
                # This number is used as a mapping code for publishers to reduce
                # the size of the catalog cache.
                pubs = {}
                for pkg_name in cache:
                        vers = cache[pkg_name]
                        for k, v in vers.iteritems():
                                if k == "versions":
                                        continue
                                for p in v[1]:
                                        if p not in pubs:
                                                pubs[p] = str(len(pubs))

                # '|' is used to separate fields of information (such
                # as fmri name and each version).
                # '!' is used to separate items within a field (such as
                # information about a version).
                # '^' is used to separate item values (such as a publisher and
                # its index number).

                # First line of file is the version of the catalog cache.
                try:
                        cf.write("%s\n" % self.CATALOG_CACHE_VERSION)
                except EnvironmentError:
                        # If the cache can't be written, it doesn't matter.
                        cleanup()
                        progtrack.cache_catalogs_done()
                        return
                except:
                        cleanup()
                        raise

                # Second line of the file is the list of publisher prefixes
                # and their index number used to decode the fmri entries.
                publine = "!".join([
                    "^".join((p, pubs[p])) for p in pubs
                ])

                try:
                        cf.write("%s\n" % publine)
                except EnvironmentError:
                        # If the cache can't be written, it doesn't matter.
                        cleanup()
                        progtrack.cache_catalogs_done()
                        return
                except:
                        cleanup()
                        raise

                # All lines after the first two are made up of a package's
                # version-specific fmri and the list of publishers that have
                # it in their catalog, or where it was installed from.
                for pkg_name in sorted(cache.keys()):
                        vers = cache[pkg_name]

                        # Iteration has to be performed over versions to retain
                        # sort order.
                        first = True
                        release = None
                        build_release = None
                        branch = None
                        for v in vers["versions"]:
                                f, fpubs = vers[str(v)]
                                known = "^".join(
                                    pubs[p] for p in fpubs
                                    if fpubs[p]
                                )

                                unknown = "^".join(
                                    pubs[p] for p in fpubs
                                    if not fpubs[p]
                                )

                                if first:
                                        # When writing the first entry for a
                                        # package, write its full fmri.
                                        first = False
                                        release = f.version.release
                                        build_release = f.version.build_release
                                        branch = f.version.branch
                                        sfmri = f.get_fmri(anarchy=True,
                                            include_scheme=False)
                                else:
                                        # For successive entries, write only
                                        # what is not shared by the previous
                                        # entry.
                                        rmatch = f.version.release == release
                                        brmatch = f.version.build_release == \
                                            build_release
                                        bmatch = f.version.branch == branch

                                        sver = str(f.version)
                                        if rmatch and brmatch and bmatch:
                                                # If release, build_release, and
                                                # branch match the last entry,
                                                # they can be omitted.
                                                sfmri = ":" + sver.split(":")[1]
                                        elif rmatch and brmatch:
                                                # If release and build_release
                                                # match the last entry, they can
                                                # be omitted.
                                                sfmri = "-" + sver.split("-")[1]
                                        elif rmatch:
                                                # If release matches the last
                                                # entry, it can be omitted.
                                                sfmri = "," + sver.split(",")[1]
                                        else:
                                                # Nothing matched the previous
                                                # entry except the name, so the
                                                # full version must be written.
                                                sfmri = "@" + sver

                                        release = f.version.release
                                        build_release = f.version.build_release
                                        branch = f.version.branch

                                line = sfmri + "|" + known + "!" + unknown
                                try:
                                        cf.write(line + "\n")
                                except EnvironmentError:
                                        # If the cache can't be written, it
                                        # doesn't matter.
                                        progtrack.cache_catalogs_done()
                                        cleanup()
                                        return
                                except:
                                        cleanup()
                                        raise

                cfpath = os.path.join(croot, CATALOG_CACHE_FILE)
                try:
                        cf.close()
                        cf = None
                        os.chmod(ctmp, 0644)
                        portable.rename(ctmp, cfpath)
                except EnvironmentError:
                        # If the cache can't be written, it doesn't matter.
                        progtrack.cache_catalogs_done()
                        cleanup()
                        return
                except:
                        cleanup()
                        raise

                # Update the mod time with the actual timestamp from the file.
                self.__catalog_cache_mod_time = \
                    self.__get_catalog_cache_mod_time()

                progtrack.cache_catalogs_done()

        def __get_catalog_cache_mod_time(self):
                """Internal helper function used to obtain last modification
                time of the on-disk catalog cache."""

                croot = os.path.join(self.imgdir, "catalog")
                cache_file = os.path.join(croot, CATALOG_CACHE_FILE)
                try:
                        mod_time = os.stat(cache_file).st_mtime
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno != errno.ENOENT:
                                raise
                        mod_time = None
                return mod_time

        def __load_catalog_cache(self, progtrack):
                """Read in the cached catalog data."""

                progtrack.load_catalog_cache_start()
                croot = os.path.join(self.imgdir, "catalog")
                cache_file = os.path.join(croot, CATALOG_CACHE_FILE)
                mod_time = self.__get_catalog_cache_mod_time()
                if self._catalog:
                        if mod_time == self.__catalog_cache_mod_time:
                                # Cache already loaded and up to date.
                                progtrack.load_catalog_cache_done()
                                return

                try:
                        cf = file(cache_file, "rb")
                except EnvironmentError, e:
                        self._catalog = {}
                        self.__catalog_cache_mod_time = None
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.ENOENT:
                                raise api_errors.CatalogCacheMissing()
                        raise

                # First line should be version.
                try:
                        ver = cf.readline().strip()
                        ver = int(ver)
                except ValueError:
                        ver = None

                # If we don't recognize the version, complain.
                if ver != self.CATALOG_CACHE_VERSION:
                        raise api_errors.CatalogCacheBadVersion(
                            ver, expected=self.CATALOG_CACHE_VERSION)

                # Second line should be the list of publishers.
                publine = cf.readline().strip()
                if not publine:
                        publine = ""

                pubidx = {}
                for e in publine.split("!"):
                        try:
                                p, idx = e.split("^")
                        except ValueError:
                                raise api_errors.CatalogCacheInvalid(
                                    publine, line_number=2)
                        pubidx[idx] = p

                if not pubidx:
                        raise api_errors.CatalogCacheInvalid(
                            publine, line_number=2)

                self._catalog = {}

                # Read until EOF.
                pkg_name = None
                sver = None
                for lnum, line in ((i + 3, l.strip())
                    for i, l in enumerate(cf)):
                        # The first of these line for each package is of
                        # the format:
                        # fmri|pub1_known^pub2...!pub1_unknown^pub2...
                        #
                        # Successive versions of the same package are of
                        # the format:
                        # @ver|pub1_known^pub2...!pub1_unknown^pub2...
                        try:
                                sfmri, spubs = line.split("|", 1)
                                sfmri = sfmri.strip()
                        except (AttributeError, ValueError):
                                raise api_errors.CatalogCacheInvalid(
                                    line, line_number=lnum)

                        if sfmri[0] in (":", "-", ",", "@") and \
                            not pkg_name:
                                # The previous line should have been a
                                # full fmri or provided enough info
                                # to construct one for this entry.
                                raise api_errors.CatalogCacheInvalid(
                                    line, line_number=lnum)
                        elif sfmri[0] == ":":
                                # Everything but the timestamp is the
                                # same as the previous entry.
                                sfmri = "%s@%s%s" % (pkg_name,
                                    sver.split(":")[0], sfmri)
                        elif sfmri[0] == "-":
                                # Everything but the branch is the same
                                # as the previous entry.
                                sfmri = "%s@%s%s" % (pkg_name,
                                    sver.split("-")[0], sfmri)
                        elif sfmri[0] == ",":
                                # Everything but the release is the same
                                # as the previous entry.
                                sfmri = "%s@%s%s" % (pkg_name,
                                    sver.split(",")[0], sfmri)
                        elif sfmri[0] == "@":
                                # If the entry starts with this, then
                                # only the package name is shared.
                                sfmri = pkg_name + sfmri

                        known, unknown = spubs.split("!")

                        # Transform the publisher index numbers into
                        # their equivalent prefixes.
                        pubs = {}
                        for k in known.split("^"):
                                if k in pubidx:
                                        pubs[pubidx[k]] = True
                        for u in unknown.split("^"):
                                if u in pubidx:
                                        pubs[pubidx[u]] = False

                        if not pubs:
                                raise api_errors.CatalogCacheInvalid(
                                    line, line_number=lnum)

                        # Build the FMRI from the provided string and
                        # cache the result using the publisher info.
                        try:
                                pfmri = pkg.fmri.PkgFmri(sfmri)
                                pkg_name = pfmri.pkg_name
                                sver = sfmri.split("@", 1)[1]
                        except (pkg.fmri.FmriError, IndexError), e:
                                raise api_errors.CatalogCacheInvalid(
                                    line, line_number=lnum)
                        catalog.Catalog.fast_cache_fmri(self._catalog,
                            pfmri, sver, pubs)

                try:
                        cf.close()
                except EnvironmentError:
                        # All of the data was retrieved, so this error
                        # doesn't matter.
                        pass

                # Now that all of the data has been loaded, set the
                # modification time.
                self.__catalog_cache_mod_time = mod_time

                progtrack.load_catalog_cache_done()

        def load_catalogs(self, progtrack, force=False):
                """Load publisher catalog data.

                'progtrack' should be a ProgressTracker object that will be used
                to provide progress information to clients.

                'force' is an optional, boolean value that, when 'True', will
                cause the publisher catalog data to be loaded again even if it
                has been already.  It defaults to 'False', which will cause the
                catalog data to only be loaded when not already loaded or when
                the catalog cache has been modified (which should only happen in
                the case of another process modifying it)."""

                if not force and self.__catalogs and \
                    self.__pkg_states is not None:
                        last_mod_time = self.__catalog_cache_mod_time
                        if last_mod_time:
                                mod_time = self.__get_catalog_cache_mod_time()
                                if mod_time == last_mod_time:
                                        # Don't load the catalogs as they are
                                        # already loaded and state information
                                        # is up to date.
                                        return
                                elif not mod_time:
                                        # Don't load the catalogs since no cache
                                        # exists on-disk but an in-memory one
                                        # does.  This can happen for
                                        # unprivileged users, or in a readonly
                                        # environment such as a Live CD where
                                        # the cache does not exist for space
                                        # or other reasons.
                                        return

                assert progtrack

                # Flush existing catalog data.
                self.__catalogs = {}

                for pub in self.gen_publishers():
                        croot = "%s/catalog/%s" % (self.imgdir, pub.prefix)
                        progtrack.catalog_start(pub.prefix)
                        if pub.prefix == self.cfg_cache.preferred_publisher:
                                pubpfx = "%s_%s" % (pkg.fmri.PREF_PUB_PFX,
                                    pub.prefix)
                                c = catalog.Catalog(croot,
                                    publisher=pubpfx)
                        else:
                                c = catalog.Catalog(croot,
                                    publisher=pub.prefix)
                        self.__catalogs[pub.prefix] = c
                        progtrack.catalog_done()

                # Load package state information as this will be used during
                # catalog cache generation.
                self.__load_pkg_states()

                # Try to load the catalog cache file.  If that fails, call
                # cache_catalogs so that the data from the canonical text copies
                # of the catalogs from each publisher will be loaded and the
                # data cached.
                #
                # XXX Given that this is a read operation, should we be writing?
                try:
                        self.__load_catalog_cache(progtrack)
                except api_errors.CatalogCacheError:
                        # If the load failed because of a bad version,
                        # corruption, or because it was missing, just try to
                        # rebuild it automatically.
                        self.__cache_catalogs(progtrack)

                # Add the packages which are installed, but not in the catalog.
                # XXX Should we have a different state for these, so we can flag
                # them to the user?
                for state, f in self.__pkg_states.values():
                        if state != PKG_STATE_INSTALLED:
                                continue

                        # cache_fmri will automatically determine whether the
                        # fmri is in the catalog and then cache if needed.  The
                        # fmri (or its version or publisher information) could
                        # be missing for a number of reasons:
                        #   * the package's publisher was removed, and no other
                        #     publisher has a matching catalog entry
                        #   * the fmri does not exist in the catalogs of any
                        #     existing publisher, even though the publisher
                        #     of the installed package has a catalog
                        #   * the package's publisher was removed or does not
                        #     exist in the installed package publisher's
                        #     catalog, but another publisher has a matching
                        #     catalog entry, so the fmri has been cached with
                        #     the other publisher's information, and the
                        #     installed publisher's information is missing
                        #
                        # The state of the package itself may be installed, but
                        # the package is unknown to the publisher (not in its
                        # catalog).
                        catalog.Catalog.cache_fmri(self._catalog, f,
                            f.get_publisher(), known=False)

        def __destroy_catalog_cache(self):
                croot = os.path.join(self.imgdir, "catalog")

                # Remove catalog cache files (including old ones).
                croot = os.path.join(self.imgdir, "catalog")
                for fname in ("pkg_names.pkl", "catalog.pkl", "catalog_cache"):
                        fpath = os.path.join(croot, fname)
                        try:
                                portable.remove(fpath)
                        except KeyboardInterrupt:
                                raise
                        except:
                                # If for any reason, the file can't be removed,
                                # it doesn't matter as it will be overwritten.
                                pass

                # Reset the in-memory cache.
                self._catalog = {}
                self.__catalog_cache_mod_time = None

        def _get_publisher_meta_root(self, prefix):
                return os.path.join(self.imgdir, "catalog", prefix)

        def has_catalog(self, prefix):
                return os.path.exists(os.path.join(
                    self._get_publisher_meta_root(prefix), "catalog"))

        def remove_publisher_metadata(self, pub):
                """Removes the metadata for the specified publisher object."""

                try:
                        del self.__catalogs[pub.prefix]
                except KeyError:
                        # May not have been loaded yet.
                        pass

                pub.remove_meta_root()
                self.__destroy_catalog_cache()

        def fmri_is_same_pkg(self, cfmri, pfmri):
                """Determine whether fmri and pfmri share the same package
                name, even if they're not equivalent versions.  This
                also checks if two packages with different names are actually
                the same because of a rename operation."""

                # If the catalog has a rename record that names fmri as a
                # destination, it's possible that pfmri could be the same pkg by
                # rename.
                if cfmri.is_same_pkg(pfmri):
                        return True

                # Get the catalog for the correct publisher
                cat = self.get_catalog(cfmri)
                return cat.rename_is_same_pkg(cfmri, pfmri)


        def fmri_is_successor(self, cfmri, pfmri):
                """Since the catalog keeps track of renames, it's no longer
                sufficient to rely on the FMRI class to determine whether a
                package is a successor.  This routine takes two FMRIs, and
                if they have the same publisher, checks if they've been
                renamed.  If a rename has occurred, this runs the is_successor
                routine from the catalog.  Otherwise, this runs the standard
                fmri.is_successor() code."""

                # Get the catalog for the correct publisher
                cat = self.get_catalog(cfmri)

                # If the catalog has a rename record that names fmri as a
                # destination, it's possible that pfmri could be a successor by
                # rename.
                if cfmri.is_successor(pfmri):
                        return True
                else:
                        return cat.rename_is_successor(cfmri, pfmri)

        def gen_installed_pkg_names(self):
                """Generate the string representation of all installed
                packages. This is faster than going through gen_installed_pkgs
                when all that will be done is to extract the strings from
                the result.
                """
                if self.__pkg_states is not None:
                        for i in self.__pkg_states.values():
                                yield i[1].get_fmri(anarchy=True)
                else:
                        installed_state_dir = "%s/state/installed" % \
                            self.imgdir
                        if os.path.isdir(installed_state_dir):
                                for pl in os.listdir(installed_state_dir):
                                        yield "pkg:/" + urllib.unquote(pl)
                        else:
                                proot = "%s/pkg" % self.imgdir
                                for pd in sorted(os.listdir(proot)):
                                        for vd in \
                                            sorted(os.listdir("%s/%s" %
                                            (proot, pd))):
                                                path = "%s/%s/%s/installed" % \
                                                    (proot, pd, vd)
                                                if not os.path.exists(path):
                                                        continue

                                                yield urllib.unquote(
                                                    "pkg:/%s@%s" % (pd, vd))

        # This could simply call self.inventory() (or be replaced by inventory),
        # but it turns out to be about 20% slower.
        def gen_installed_pkgs(self):
                """Return an iteration through the installed packages."""
                self.__load_pkg_states()
                return (i[1] for i in self.__pkg_states.values())

        def __load_pkg_states(self):
                """Build up the package state dictionary.

                This dictionary maps the full fmri string to a tuple of the
                state, the prefix of the publisher from which it's installed,
                and the fmri object.

                Note that this dictionary only maps installed packages.  Use
                get_pkg_state_by_fmri() to retrieve the state for arbitrary
                packages.
                """

                if self.__pkg_states is not None:
                        return

                installed_state_dir = "%s/state/installed" % self.imgdir

                self.__pkg_states = {}

                # If the state directory structure has already been created,
                # loading information from it is fast.  The directory is
                # populated with symlinks, named by their (url-encoded) FMRI,
                # which point to the "installed" file in the corresponding
                # directory under /var/pkg.
                if os.path.isdir(installed_state_dir):
                        for pl in sorted(os.listdir(installed_state_dir)):
                                fmristr = urllib.unquote(pl)
                                f = pkg.fmri.PkgFmri(fmristr)
                                path = self._install_file(f)
                                pub = self.installed_file_publisher(path)
                                f.set_publisher(pub)

                                self.__pkg_states[fmristr] = \
                                    (PKG_STATE_INSTALLED, f)

                        return

                # Otherwise, we must iterate through the earlier installed
                # state.  One day, this can be removed.
                proot = "%s/pkg" % self.imgdir
                for pd in sorted(os.listdir(proot)):
                        for vd in sorted(os.listdir("%s/%s" % (proot, pd))):
                                path = "%s/%s/%s/installed" % (proot, pd, vd)
                                if not os.path.exists(path):
                                        continue

                                fmristr = urllib.unquote("%s@%s" % (pd, vd))
                                pub = self.installed_file_publisher(path)
                                f = pkg.fmri.PkgFmri(fmristr, publisher = pub)

                                self.__pkg_states[fmristr] = \
                                    (PKG_STATE_INSTALLED, f)

        def clear_pkg_state(self):
                self.__pkg_states = None
                self.__manifest_cache = {}

        def strtofmri(self, myfmri):
                return pkg.fmri.PkgFmri(myfmri, self.attrs["Build-Release"])

        def strtomatchingfmri(self, myfmri):
                return pkg.fmri.MatchingPkgFmri(myfmri,
                    self.attrs["Build-Release"])

        def load_constraints(self, progtrack):
                """Load constraints for all install pkgs"""
                for fmri in self.gen_installed_pkgs():
                        # skip loading if already done
                        if self.constraints.start_loading(fmri):
                                mfst = self.get_manifest(fmri)
                                for dep in mfst.gen_actions_by_type("depend",
                                    self.list_excludes()):
                                        progtrack.evaluate_progress()
                                        f, con = dep.parse(self,
                                            fmri.get_name())
                                        self.constraints.update_constraints(con)
                                self.constraints.finish_loading(fmri)

        def get_installed_unbound_inc_list(self):
                """Returns list of packages containing incorporation
                dependencies on which no other pkgs depend."""

                inc_tuples = []
                dependents = set()

                for fmri in self.gen_installed_pkgs():
                        fmri_name = fmri.get_pkg_stem()
                        mfst = self.get_manifest(fmri)
                        for dep in mfst.gen_actions_by_type("depend",
                            self.list_excludes()):
                                con_fmri = dep.get_constrained_fmri(self)
                                if con_fmri:
                                        con_name = con_fmri.get_pkg_stem()
                                        dependents.add(con_name)
                                        inc_tuples.append((fmri_name, con_name))
                # remove those incorporations which are depended on by other
                # incorporations.
                deletions = 0
                for i, a in enumerate(inc_tuples[:]):
                        if a[0] in dependents:
                                del inc_tuples[i - deletions]

                return list(set([ a[0] for a in inc_tuples ]))

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
        def __multimatch(name, patterns, matcher):
                """Applies a matcher to a name across a list of patterns.
                Returns all tuples of patterns which match the name.  Each tuple
                contains the index into the original list, the pattern itself,
                the package version, the publisher, and the raw publisher
                string."""
                return [
                    (i, pat, pat.tuple()[2],
                        pat.get_publisher(), pat.get_publisher_str())
                    for i, pat in enumerate(patterns)
                    if matcher(name, pat.tuple()[1])
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

                illegals = []
                for i, pat in enumerate(patterns):
                        if not isinstance(pat, pkg.fmri.PkgFmri):
                                try:
                                        if "*" in pat or "?" in pat:
                                                matcher = pkg.fmri.glob_match
                                                patterns[i] = \
                                                    pkg.fmri.MatchingPkgFmri(
                                                        pat, "5.11")
                                        else:
                                                patterns[i] = \
                                                    pkg.fmri.PkgFmri(pat,
                                                    "5.11")
                                except pkg.fmri.IllegalFmri, e:
                                        illegals.append(e)

                if illegals:
                        raise api_errors.InventoryException(illegal=illegals)

                ppub = self.cfg_cache.preferred_publisher

                # matchingpats is the set of all the patterns which matched a
                # package in the catalog.  This allows us to return partial
                # failure if some patterns match and some don't.
                # XXX It would be nice to keep track of why some patterns failed
                # to match -- based on name, version, or publisher.
                matchingpats = set()

                if ordered:
                        entries = sorted(self._catalog.keys())
                else:
                        entries = self._catalog.keys()

                for name in entries:
                        # Eliminate all patterns not matching "name".  If there
                        # are no patterns left, go on to the next name, but only
                        # if there were any to start with.
                        matches = self.__multimatch(name, patterns, matcher)
                        if patterns and not matches:
                                continue

                        newest = self._catalog[name]["versions"][-1]
                        for ver in reversed(self._catalog[name]["versions"]):
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
                                pubstate = self._catalog[name][str(ver)][1]

                                nomatch = []
                                for i, match in enumerate(vmatches):
                                        if match[3] and \
                                            match[3] not in pubstate:
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
                                            m[3:5]
                                            for m in pmatches
                                            if m[3] in pubstate
                                        )
                                else:
                                        publist = zip(pubstate.keys(),
                                            pubstate.keys())

                                pfmri = self._catalog[name][str(ver)][0]

                                inst_state = self.get_pkg_state_by_fmri(pfmri)
                                inst_pub = self.get_pkg_pub_by_fmri(pfmri)
                                state = {
                                    "upgradable": ver != newest,
                                    "frozen": False,
                                    "incorporated": False,
                                    "excludes": False
                                }

                                # We yield copies of the fmri objects in the
                                # catalog because we add the publishers in, and
                                # don't want to mess up the canonical catalog.
                                # If a pattern had specified a publisher as
                                # preferred, be sure to emit an fmri that way,
                                # too.
                                yielded = False
                                if all_known:
                                        for pub, rpub in publist:
                                                nfmri = pfmri.copy()
                                                nfmri.set_publisher(rpub,
                                                    pub == ppub)
                                                st = state.copy()
                                                if pub == inst_pub:
                                                        st["state"] = \
                                                            PKG_STATE_INSTALLED
                                                else:
                                                        st["state"] = \
                                                            PKG_STATE_KNOWN
                                                st["in_catalog"] = pubstate[pub]
                                                yield nfmri, st
                                                yielded = True
                                elif inst_state == PKG_STATE_INSTALLED:
                                        nfmri = pfmri.copy()
                                        nfmri.set_publisher(inst_pub,
                                            inst_pub == ppub)
                                        state["state"] = inst_state
                                        state["in_catalog"] = pubstate[inst_pub]
                                        yield nfmri, state
                                        yielded = True

                                if yielded:
                                        matchingpats |= set(
                                            i[:2] for i in pmatches)

                nonmatchingpats = [
                    opatterns[i]
                    for i, f in set(enumerate(patterns)) - matchingpats
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
                ppub = self.cfg_cache.preferred_publisher

                if not preferred:
                        for f in self.__inventory(*args, **kwargs):
                                yield f
                else:
                        nplist = []
                        firstnp = None
                        for f in self.__inventory(*args, **kwargs):
                                if f[0].get_publisher() == ppub:
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
                        msg("Deleting content cache")
                        shutil.rmtree(self.dl_cache_dir, True)

        def salvagedir(self, path):
                """Called when directory contains something and it's not
                supposed to because it's being deleted. XXX Need to work out a
                better error passback mechanism. Path is rooted in /...."""

                salvagedir = os.path.normpath(
                    os.path.join(self.imgdir, "lost+found",
                    path + "-" + time.strftime("%Y%m%dT%H%M%SZ")))

                parent = os.path.dirname(salvagedir)
                if not os.path.exists(parent):
                        os.makedirs(parent)
                shutil.move(os.path.normpath(os.path.join(self.root, path)),
                    salvagedir)
                # XXX need a better way to do this.
                emsg("\nWarning - directory %s not empty - contents preserved "
                        "in %s" % (path, salvagedir))

        def temporary_file(self):
                """create a temp file under image directory for various
                purposes"""
                tempdir = os.path.normpath(os.path.join(self.imgdir, "tmp"))
                if not os.path.exists(tempdir):
                        os.makedirs(tempdir)
                fd, name = tempfile.mkstemp(dir=tempdir)
                os.close(fd)
                return name

        def __filter_install_matches(self, matches, names):
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
                their unique names and a dict containing package state
                information."""

                olist = []
                onames = {}
                # First eliminate any duplicate matches that are for unknown
                # publishers (publishers which have been removed from the image
                # configuration).
                publist = [p.prefix for p in self.get_publishers().values()]

                for m in matches:
                        if m.get_publisher() in publist:
                                stem = m.get_pkg_stem()
                                onames[stem] = names[stem]
                                olist.append(m)

                # Next, if there are still multiple matches, eliminate fmris
                # belonging to publishers that no longer have the fmri in their
                # catalog.
                found_state = False
                if len(onames) > 1:
                        mlist = []
                        mnames = {}
                        for m in olist:
                                stem = m.get_pkg_stem()
                                st = onames[stem]
                                if st["in_catalog"]:
                                        if st["state"] == PKG_STATE_INSTALLED:
                                                found_state = True
                                        mnames[stem] = onames[stem]
                                        mlist.append(m)
                        olist = mlist
                        onames = mnames

                # Finally, if there are still multiple matches, and a known stem
                # has been found in the provided state, then eliminate any stems
                # that do not have the specified state.
                if found_state and len(onames) > 1:
                        mlist = []
                        mnames = {}
                        for m in olist:
                                stem = m.get_pkg_stem()
                                if onames[stem]["state"] == PKG_STATE_INSTALLED:
                                        mnames[stem] = onames[stem]
                                        mlist.append(m)
                        olist = mlist
                        onames = mnames

                return olist, onames

        def make_install_plan(self, pkg_list, progtrack, check_cancelation,
            noexecute, filters=None, verbose=False, multimatch_ignore=False):
                """Take a list of packages, specified in pkg_list, and attempt
                to assemble an appropriate image plan.  This is a helper
                routine for some common operations in the client.

                This method checks all publishers for a package match;
                however, it defaults to choosing the preferred publisher
                when an ambiguous package name is specified.  If the user
                wishes to install a package from a non-preferred publisher,
                the full FMRI that contains a publisher should be used
                to name the package.

                'multimatch_ignore' is an optional, boolean value that
                indicates whether packages that have multiple matches for
                only non-preferred publishers should be ignored when creating
                the install plan.  This is intended to be used during an
                image-update.
                """

                self.load_catalogs(progtrack)

                if filters is None:
                        filters = []

                error = 0
                ip = imageplan.ImagePlan(self, progtrack, check_cancelation,
                    filters=filters, noexecute=noexecute)

                progtrack.evaluate_start()
                self.load_constraints(progtrack)

                unmatched_fmris = []
                multiple_matches = []
                illegal_fmris = []
                constraint_violations = []

                # order package list so that any unbound incorporations are
                # done first

                inc_list = self.get_installed_unbound_inc_list()

                head = []
                tail = []


                for p in pkg_list:
                        if p in inc_list:
                                head.append(p)
                        else:
                                tail.append(p)
                pkg_list = head + tail

                # This approach works only for cases w/ simple
                # incorporations; the apply_constraints_to_fmri
                # call below binds the version too quickly.  This
                # awaits a proper solver.

                for p in pkg_list:
                        progtrack.evaluate_progress()
                        try:
                                conp = pkg.fmri.PkgFmri(p,
                                    self.attrs["Build-Release"])
                        except pkg.fmri.IllegalFmri:
                                illegal_fmris.append(p)
                                error = 1
                                continue
                        try:
                                conp = \
                                    self.constraints.apply_constraints_to_fmri(
                                    conp, auto=True)
                        except constraint.ConstraintException, e:
                                error = 1
                                constraint_violations.extend(str(e).split("\n"))
                                continue

                        # If we were passed in an fmri object or a string that
                        # anchors the package stem with the scheme, match on the
                        # stem exactly as given.  Otherwise we can let the
                        # default, looser matching mechanism be used.
                        # inventory() will override if globbing characters are
                        # used.
                        matcher = None
                        if isinstance(p, pkg.fmri.PkgFmri) or \
                            p.startswith("pkg:/"):
                                matcher = pkg.fmri.exact_name_match

                        try:
                                matches = list(self.inventory([conp],
                                    all_known=True, matcher=matcher,
                                    ordered=False))
                        except api_errors.InventoryException, e:
                                assert(not (e.notfound and e.illegal))
                                assert(e.notfound or e.illegal)
                                error = 1
                                if e.notfound:
                                        unmatched_fmris.append(p)
                                else:
                                        illegal_fmris.append(p)
                                continue

                        pnames = {}
                        pmatch = []
                        npnames = {}
                        npmatch = []
                        for m, st in matches:
                                if m.preferred_publisher():
                                        pnames[m.get_pkg_stem()] = st
                                        pmatch.append(m)
                                else:
                                        npnames[m.get_pkg_stem()] = st
                                        npmatch.append(m)

                        if len(pnames) > 1:
                                # There can only be one preferred publisher, so
                                # filtering is pointless and these are truly
                                # ambiguous matches.
                                multiple_matches.append((p, pnames.keys()))
                                error = 1
                                continue
                        elif not pnames and len(npnames) > 1:
                                npmatch, npnames = \
                                    self.__filter_install_matches(npmatch,
                                    npnames)
                                if len(npnames) > 1:
                                        if multimatch_ignore:
                                                # Caller has requested that this
                                                # package be skipped if multiple
                                                # matches are found.
                                                continue
                                        # If there are still multiple matches
                                        # after filtering, fail.
                                        multiple_matches.append((p,
                                            npnames.keys()))
                                        error = 1
                                        continue

                        # matches is a list reverse sorted by version, so take
                        # the first; i.e., the latest.
                        if pmatch:
                                ip.propose_fmri(pmatch[0])
                        else:
                                ip.propose_fmri(npmatch[0])

                if error != 0:
                        raise api_errors.PlanCreationException(unmatched_fmris,
                            multiple_matches, [], illegal_fmris,
                            constraint_violations=constraint_violations)

                if verbose:
                        msg(_("Before evaluation:"))
                        msg(ip)

                # A plan can be requested without actually performing an
                # operation on the image.
                if self.history.operation_name:
                        self.history.operation_start_state = ip.get_plan()

                try:
                        ip.evaluate()
                except constraint.ConstraintException, e:
                        raise api_errors.PlanCreationException(
                            constraint_violations=str(e).split("\n"))

                self.imageplan = ip

                if self.history.operation_name:
                        self.history.operation_end_state = \
                            ip.get_plan(full=False)

                if verbose:
                        msg(_("After evaluation:"))
                        msg(ip.display())

        def make_uninstall_plan(self, fmri_list, recursive_removal,
            progresstracker, check_cancelation, noexecute, verbose=False):
                ip = imageplan.ImagePlan(self, progresstracker,
                    check_cancelation, recursive_removal, noexecute=noexecute)

                self.load_catalogs(progresstracker)

                err = 0

                unmatched_fmris = []
                multiple_matches = []
                missing_matches = []
                illegal_fmris = []

                progresstracker.evaluate_start()

                for ppat in fmri_list:
                        progresstracker.evaluate_progress()
                        try:
                                matches = list(self.inventory([ppat],
                                    ordered=False))
                        except api_errors.InventoryException, e:
                                assert(not (e.notfound and e.illegal))
                                if e.notfound:
                                        try:
                                                list(self.inventory([ppat],
                                                    all_known=True,
                                                    ordered=False))
                                                missing_matches.append(ppat)
                                        except api_errors.InventoryException:
                                                unmatched_fmris.append(ppat)
                                elif e.illegal:
                                        illegal_fmris.append(ppat)
                                else:
                                        raise RuntimeError("Caught inventory "
                                            "exception without unmatched or "
                                            "illegal fmris set.")
                                err = 1
                                continue

                        if len(matches) > 1:
                                matchlist = [m for m, state in matches]
                                multiple_matches.append((ppat, matchlist))
                                err = 1
                                continue

                        # Propose the removal of the first (and only!) match.
                        ip.propose_fmri_removal(matches[0][0])

                if err == 1:
                        raise api_errors.PlanCreationException(unmatched_fmris,
                            multiple_matches, missing_matches, illegal_fmris)
                if verbose:
                        msg(_("Before evaluation:"))
                        msg(ip)

                self.history.operation_start_state = ip.get_plan()
                ip.evaluate()
                self.history.operation_end_state = ip.get_plan(full=False)
                self.imageplan = ip

                if verbose:
                        msg(_("After evaluation:"))
                        ip.display()

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
                        newimg = Image()
                        cmdpath = os.path.join(os.getcwd(), actual_cmd)
                        cmdpath = os.path.realpath(cmdpath)
                        cmddir = os.path.dirname(os.path.realpath(cmdpath))
                        #
                        # Find the path to ourselves, and use that
                        # as a way to locate the image we're in.  It's
                        # not perfect-- we could be in a developer's
                        # workspace, for example.
                        #
                        newimg.find_root(cmddir)
                        newimg.load_config()

                        if refresh_allowed:
                                # If refreshing publisher metadata is allowed,
                                # then perform a refresh so that a new SUNWipkg
                                # can be discovered.
                                try:
                                        newimg.refresh_publishers(
                                            progtrack=progtrack)
                                except api_errors.CatalogRefreshException, cre:
                                        cre.message = \
                                            _("SUNWipkg update check failed.")
                                        raise
                        else:
                                # If refresh wasn't called, the catalogs have to
                                # be manually loaded.
                                newimg.load_catalogs(progtrack)
                        img = newimg

                # XXX call to progress tracker that SUNWipkg is being refreshed

                img.make_install_plan(["SUNWipkg"], progtrack,
                    check_cancelation, noexecute, filters = [])

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
                                found.append(m[0])
                except api_errors.InventoryException, e:
                        illegals = e.illegal
                        notfound = e.notfound

                return found, notfound, illegals
