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
import platform
import shutil
import tempfile
import time
import urllib

import pkg.Uuid25
import pkg.catalog
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
import pkg.fmri
import pkg.manifest                     as manifest
import pkg.misc                         as misc
import pkg.portable                     as portable
import pkg.server.catalog
import pkg.variant                      as variant
import pkg.version

from pkg.client.debugvalues import DebugValues
from pkg.client.imagetypes import IMG_USER, IMG_ENTIRE
from pkg.misc import CfgCacheError
from pkg.misc import EmptyI, EmptyDict
from pkg.misc import msg, emsg

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

        # This is a temporary, private state that is used to indicate that
        # a package with state PKG_STATE_INSTALLED was installed from a
        # publisher that was preferred at the time of installation.  It
        # will be obsolete in the near future when publishers are ranked
        # instead.
        __PKG_STATE_PREFERRED = 5

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

        # Class properties
        required_subdirs = [ "file", "pkg" ]
        image_subdirs = required_subdirs + [ "index", IMG_PUB_DIR,
            "state/installed", "state/known" ]

        def __init__(self):
                self.__catalogs = {}
                self.__upgraded = False

                self.arch_change = False
                self.attrs = {
                    "Policy-Require-Optional": False,
                    "Policy-Pursue-Latest": True
                }
                self.cfg_cache = None
                self.constraints = constraint.ConstraintSet()
                self.dl_cache_dir = None
                self.dl_cache_incoming = None
                self.history = history.History()
                self.imageplan = None # valid after evaluation succeeds
                self.img_prefix = None
                self.imgdir = None
                self.index_dir = None
                self.is_user_cache_dir = False
                self.new_variants = {}
                self.pkgdir = None
                self.root = None

                # a place to keep info about saved_files; needed by file action
                self.saved_files = {}

                self.state = imagestate.ImageState(self)

                # Transport operations for this image
                self.transport = transport.Transport(self)

                self.type = None

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

        def find_root(self, d, exact_match=False, progtrack=None):
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
                                self.__set_dirs(imgtype=imgtype, root=d,
                                    progtrack=progtrack)
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

                # Forcibly discard image catalogs so they can be re-loaded
                # from the new location if they are already loaded.  This
                # also prevents scribbling on image state information in
                # the wrong location.
                self.__catalogs = {}

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
                        self.__upgrade_image(progtrack=progtrack)
                        return

                # If the image has already been upgraded, first ensure that its
                # structure is valid.
                self.mkdirs()

                # Ensure structure for publishers is valid.
                for pub in self.gen_publishers():
                        pub.create_meta_root()

                # Once its structure is valid, then ensure state information
                # is intact.
                rebuild = False
                kdir = os.path.join(self.imgdir, "state",
                    self.IMG_CATALOG_KNOWN)
                kcattrs = os.path.join(kdir, "catalog.attrs")
                idir = os.path.join(self.imgdir, "state",
                    self.IMG_CATALOG_INSTALLED)
                icattrs = os.path.join(idir, "catalog.attrs")
                if not os.path.isfile(icattrs):
                        rebuild = True
                elif not os.path.isfile(kcattrs) and os.path.isfile(icattrs):
                        # If the known catalog doesn't exist, but the installed
                        # catalog does, then copy the installed catalog to the
                        # known catalog directory so that state information can
                        # be preserved during the rebuild.
                        for fname in os.listdir(idir):
                                portable.copyfile(os.path.join(idir, fname),
                                    os.path.join(kdir, fname))
                        rebuild = True

                if rebuild:
                        self.__rebuild_image_catalogs(progtrack=progtrack)

        def set_attrs(self, imgtype, root, is_zone, prefix, pub_url,
            ssl_key=None, ssl_cert=None, variants=EmptyDict,
            refresh_allowed=True, progtrack=None):

                self.__set_dirs(imgtype=imgtype, root=root, progtrack=progtrack)

                if not os.path.exists(os.path.join(self.imgdir,
                    imageconfig.CFG_FILE)):
                        op = "image-create"
                else:
                        op = "image-set-attributes"

                # Create the publisher object before creating the image
                # so that if creation of the Publisher object fails, an
                # empty, useless image won't be left behind.
                repo = publisher.Repository()
                repo.add_origin(pub_url, ssl_cert=ssl_cert, ssl_key=ssl_key)
                newpub = publisher.Publisher(prefix,
                    meta_root=self._get_publisher_meta_root(prefix),
                    repositories=[repo], transport=self.transport)

                # Initialize and store the configuration object.
                self.cfg_cache = imageconfig.ImageConfig(self.root,
                    self._get_publisher_meta_dir())
                self.history.log_operation_start(op)

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
                return bool(self.root == "/" or DebugValues.get_value("simulate_live_root"))

        def is_zone(self):
                return self.cfg_cache.variants[
                    "variant.opensolaris.zone"] == "nonglobal"

        def get_arch(self):
                if "variant.arch" in self.new_variants:
                        return self.new_variants["variant.arch"]
                else:
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
                """Returns a boolean value indicating whether a publisher
                exists in the image configuration that matches the given
                prefix or alias."""
                for pub in self.gen_publishers(inc_disabled=True):
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

                self.cfg_cache.remove_publisher(pub.prefix)
                self.remove_publisher_metadata(pub, progtrack=progtrack)
                self.save_config()
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
                        e = api_errors.SetDisabledPublisherPreferred(pub)
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

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                # Must assign this first before performing any more operations.
                pub.meta_root = self._get_publisher_meta_root(pub.prefix)
                pub.transport = self.transport
                self.cfg_cache.publishers[pub.prefix] = pub

                if refresh_allowed:
                        try:
                                # First, verify that the publisher has a valid
                                # pkg(5) repository.
                                self.transport.valid_publisher_test(pub)
                                self.refresh_publishers(pubs=[pub],
                                    progtrack=progtrack)
                        except Exception, e:
                                # Remove the newly added publisher since the
                                # retrieval failed.
                                self.cfg_cache.remove_publisher(pub.prefix)
                                self.remove_publisher_metadata(pub,
                                    progtrack=progtrack)
                                self.history.log_operation_end(error=e)
                                raise
                        except:
                                # Remove the newly added publisher since the
                                # retrieval failed.
                                self.cfg_cache.remove_publisher(pub.prefix)
                                self.remove_publisher_metadata(pub,
                                    progtrack=progtrack)
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

        def __call_imageplan_evaluate(self, ip, verbose=False):
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
                        ip.display()

        def image_change_variant(self, variants, progtrack, check_cancelation,
            noexecute, verbose=False):

                ip = imageplan.ImagePlan(self, progtrack, lambda: False,
                    noexecute=noexecute, variants=variants,
                    recursive_removal=True)
                progtrack.evaluate_start()

                # make sure that some variants are actually changing
                variants = dict(set(variants.iteritems()) - \
                    set(self.cfg_cache.variants.iteritems()))

                if not variants:
                        self.__call_imageplan_evaluate(ip, verbose)
                        msg("No variant changes.")
                        return

                #
                # only get manifests for all architectures if we're
                # changing the architecture variant
                #
                if "variant.arch" in variants:
                        self.arch_change = True

                #
                # we can't set self.new_variants until after we
                # instantiate the image plan since the image plan has
                # to cache information like the old excludes, and
                # once we set new_variants things like self.list_excludes()
                # and self.get_arch() will report valus based off of the
                # new variants we're moving too.
                #
                self.new_variants = variants

                for fmri in self.gen_installed_pkgs():
                        m = self.get_manifest(fmri)
                        m_arch = m.get_variants("variant.arch")
                        if not m_arch:
                                # keep packages that don't have an explicit arch
                                ip.propose_fmri(fmri)
                        elif self.get_arch() in m_arch:
                                # keep packages that match the current arch
                                ip.propose_fmri(fmri)
                        else:
                                # remove packages for different archs
                                ip.propose_fmri_removal(fmri)

                self.__call_imageplan_evaluate(ip, verbose)

        def image_config_update(self):
                if not self.new_variants:
                        return
                ic = self.cfg_cache
                ic.variants.update(self.new_variants)
                ic.write(self.imgdir)
                ic = imageconfig.ImageConfig(self.root,
                    self._get_publisher_meta_dir())
                ic.read(self.imgdir)
                self.cfg_cache = ic

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
                ip.update_index = False
                progtrack.evaluate_start()
                ip.pkg_plans = pps

                ip.evaluate()
                if ip.actuators.reboot_needed() and self.is_liveroot():
                        raise api_errors.RebootNeededOnLiveImageException()
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
                                    api_errors.TransportError):
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

        def get_manifest(self, fmri, all_arch=False):
                """return manifest; uses cached version if available.
                all_arch controls whether manifest contains actions
                for all architectures"""

                # Normally elide other arch variants
                if self.arch_change or all_arch:
                        all_arch = True
                        v = EmptyI
                else:
                        arch = {"variant.arch": self.get_arch()}
                        v = [variant.Variants(arch).allow_action]

                m = self.__get_manifest(fmri, v)

                self.__touch_manifest(fmri)
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
                        # XXX This needs to be changed once publisher
                        # priortisation is implemented.
                        states.discard(self.__PKG_STATE_PREFERRED)
                elif state == self.PKG_STATE_INSTALLED:
                        states.add(state)

                        # XXX The below needs to be removed once publisher
                        # priortisation is implemented.

                        # If this package is being marked as 'installed', then
                        # also mark if it is being installed from a publisher
                        # that is currently preferred.
                        if pfmri.publisher == self.get_preferred_publisher():
                                states.add(self.__PKG_STATE_PREFERRED)
                else:
                        # All other states should simply be added to the
                        # existing set of states.
                        states.add(state)

                if self.PKG_STATE_KNOWN not in states and \
                    self.PKG_STATE_INSTALLED not in states:
                        # Package is no longer known or installed, so isn't
                        # upgradable.
                        states.discard(self.PKG_STATE_UPGRADABLE)

                if not states or (len(states) == 1 and
                    (self.PKG_STATE_V0 in states or
                    self.PKG_STATE_V1 in states)):
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
                elif self.PKG_STATE_INSTALLED in states:
                        # If some other state has been changed and the package
                        # is still marked as installed, then simply update the
                        # existing entry (which should already exist).
                        icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                        icat.update_entry(pfmri, metadata=mdata)

        def save_pkg_state(self):
                """Saves current package state information."""

                for name in self.IMG_CATALOG_KNOWN, self.IMG_CATALOG_INSTALLED:
                        cat = self.get_catalog(name)
                        cat.save()

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

                croot = os.path.join(self.imgdir, "state", name)
                try:
                        os.makedirs(croot)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                # Allow operations to work for
                                # unprivileged users.
                                croot = None
                        elif e.errno != errno.EEXIST:
                                raise

                def manifest_cb(f):
                        return self.get_manifest(f, all_arch=True)

                # batch_mode is set to True here as any operations that modify
                # the catalogs (add or remove entries) are only done during an
                # image upgrade or metadata refresh.  In both cases, the catalog
                # is resorted and finalized so this is always safe to use.
                cat = pkg.catalog.Catalog(batch_mode=True,
                    manifest_cb=manifest_cb, meta_root=croot, sign=False)
                self.__catalogs[name] = cat
                return cat

        def remove_catalogs(self):
                """Removes all image catalogs and their directories."""

                self.__catalogs = {}
                for name in (self.IMG_CATALOG_KNOWN,
                    self.IMG_CATALOG_INSTALLED):
                        shutil.rmtree(os.path.join(self.imgdir, "state", name))

        def remove_catalog(self, name):
                """Removes the requested image catalog if it exists.

                'name' must be one of the following image constants:
                    IMG_CATALOG_KNOWN
                        The known catalog contains all of packages that are
                        installed or available from a publisher's repository.

                    IMG_CATALOG_INSTALLED
                        The installed catalog is a subset of the 'known'
                        catalog that only contains installed packages."""

                if not self.imgdir:
                        raise RuntimeError("self.imgdir must be set")

                cat = self.__catalogs.pop(name, None)
                if not cat:
                        croot = os.path.join(self.imgdir, "state", name)
                        cat = pkg.catalog.Catalog(meta_root=croot, sign=False)
                cat.destroy()

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

        def older_version_installed(self, fmri):
                """This method is used by the package plan to determine if an
                older version of the package is installed.  This takes the
                destination fmri and checks if an older package exists."""

                v = self.get_version_installed(fmri)

                assert fmri.has_publisher()

                if v:
                        return v
                return None

        def is_pkg_installed(self, pfmri):
                """Returns a boolean value indicating whether the specified
                package is installed."""

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                try:
                        cat.get_entry(pfmri)
                except api_errors.UnknownCatalogEntry:
                        return False
                return True

        def is_pkg_preferred(self, pfmri):
                """Compatibility function for use by pkg.client.api only.
                Should be removed once publishers are ranked by priority.

                Returns a boolean value indicating whether the specified
                package was installed from a publisher that was preferred at
                the time of installation, or is from the same publisher as
                the currently preferred publisher."""

                if pfmri.publisher == self.get_preferred_publisher():
                        return True

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                try:
                        entry = cat.get_entry(pfmri)
                except api_errors.UnknownCatalogEntry:
                        return False
                states = entry["metadata"]["states"]
                return self.__PKG_STATE_PREFERRED in states

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
                elif self.new_variants:
                        new_vars = self.cfg_cache.variants.copy()
                        new_vars.update(self.new_variants)
                        return [new_vars.allow_action]
                else:
                        return [self.cfg_cache.variants.allow_action]

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

                                dfmri = self.strtofmri(a.attrs["fmri"])
                                if dfmri not in self.__req_dependents:
                                        self.__req_dependents[dfmri] = []
                                self.__req_dependents[dfmri].append(f)

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
                # simpler, but it wouldn't handle catalog operations (such as
                # rename) that might have been applied to the fmri.
                for f in self.__req_dependents.iterkeys():
                        if pfmri.is_successor(f):
                                dependents.extend(self.__req_dependents[f])
                return dependents

        def __rebuild_image_catalogs(self, progtrack=None):
                """Rebuilds the image catalogs based on the available publisher
                catalogs."""

                if not progtrack:
                        progtrack = progress.QuietProgressTracker()

                progtrack.cache_catalogs_start()

                publist = list(self.gen_publishers())
                if not publist:
                        # No publishers, so nothing can be known or installed.
                        self.remove_catalogs()
                        progtrack.cache_catalogs_done()
                        return

                # The image catalogs need to be updated, but this is a bit
                # tricky as previously known packages must remain known even
                # if PKG_STATE_KNOWN is no longer true if any other state
                # information is present.  This is to allow freezing, etc. of
                # package states on a permanent basis even if the package is
                # no longer available from a publisher repository.
                old_kcat = self.get_catalog(self.IMG_CATALOG_KNOWN)

                # batch_mode is set to True here since without it, catalog
                # population time is almost doubled (since the catalog is
                # re-sorted and stats are generated for every operation).
                kcat = pkg.catalog.Catalog(batch_mode=True, sign=False)

                # XXX if any of the below fails for any reason, the old 'known'
                # catalog needs to be re-loaded so the client is in a consistent
                # state.

                # All enabled publisher catalogs must be processed.
                pub_cats = [pub.catalog for pub in publist]

                # XXX For backwards compatibility, 'upgradability' of packages
                # is calculated and stored based on whether a given pkg stem
                # matches the newest version in the catalog.  This is quite
                # expensive (due to overhead), but at least the cost is
                # consolidated here.  This comparison is also cross-publisher,
                # as it used to be.  In the future, it could likely be improved
                # by usage of the SAT solver.
                newest = {}
                for cat in [old_kcat] + pub_cats:
                        for f in cat.fmris():
                                nver = newest.get(f.pkg_name, None)
                                newest[f.pkg_name] = max(nver, f.version)

                # Next, copy all of the entries for the catalog parts that
                # currently exist into the image 'known' catalog.
                def pub_append_cb(src_cat, f, ignored):
                        # Need to get any state information from the old 'known'
                        # catalog and return it so that it will be merged with
                        # the new 'known' catalog.
                        try:
                                entry = old_kcat.get_entry(f)
                                old_kcat.remove_package(f)
                        except api_errors.UnknownCatalogEntry:
                                # If the package can't be found
                                # in the previous 'known'
                                # catalog, then this is a
                                # completely new package.
                                states = set()
                                mdata = { "states": states }
                        else:
                                mdata = entry["metadata"]
                                states = set(mdata["states"])

                        if src_cat.version == 0:
                                states.add(self.PKG_STATE_V0)
                        else:
                                # Assume V1 catalog source.
                                states.add(self.PKG_STATE_V1)

                        states.add(self.PKG_STATE_KNOWN)
                        nver = newest.get(f.pkg_name, None)
                        if not nver or f.version == nver:
                                states.discard(self.PKG_STATE_UPGRADABLE)
                        elif nver:
                                states.add(self.PKG_STATE_UPGRADABLE)
                        mdata["states"] = list(states)
                        return True, mdata

                for cat in pub_cats:
                        kcat.append(cat, cb=pub_append_cb)

                # Next, add any remaining entries in the previous 'known'
                # catalog to the new one, but clear PKG_STATE_KNOWN and
                # drop any entries that have no remaining state information.
                def old_append_cb(src_cat, f, entry):
                        # Need to get any state information from the old 'known'
                        # catalog and return it so that it will be merged with
                        # the new 'known' catalog.
                        mdata = entry["metadata"]
                        states = set(mdata["states"])

                        states.discard(self.PKG_STATE_KNOWN)

                        # Since this package is no longer available, it
                        # can only be considered upgradable if it is
                        # installed and there is a newer version
                        # available.
                        nver = newest.get(f.pkg_name, None)
                        if self.PKG_STATE_INSTALLED not in states or \
                            (nver and f.version == nver):
                                states.discard(self.PKG_STATE_UPGRADABLE)
                        elif nver:
                                states.add(self.PKG_STATE_UPGRADABLE)

                        if not states or (len(states) == 1 and
                            (self.PKG_STATE_V0 in states or
                            self.PKG_STATE_V1 in states)):
                                # This entry is no longer available and
                                # has no meaningful state information, so
                                # should be skipped.
                                return False, None

                        # The package is either installed, frozen, or is
                        # in some other state that needs preservation.
                        mdata["states"] = list(states)
                        return True, mdata

                kcat.append(old_kcat, cb=old_append_cb)

                # Next, remove the old image catalogs.
                self.remove_catalog(self.IMG_CATALOG_KNOWN)
                self.remove_catalog(self.IMG_CATALOG_INSTALLED)

                # Finally, re-populate the 'installed' catalog based on the
                # contents of the new, 'known' catalog and save them both.
                def installed_append_cb(src_cat, f, entry):
                        states = entry["metadata"]["states"]
                        if self.PKG_STATE_INSTALLED in states:
                                return True, None
                        return False, None

                icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                icat.append(kcat, cb=installed_append_cb)

                croot = os.path.join(self.imgdir, "state",
                    self.IMG_CATALOG_KNOWN)
                kcat.meta_root = croot

                for cat in kcat, icat:
                        cat.save()
                progtrack.cache_catalogs_done()

        def refresh_publishers(self, full_refresh=False, immediate=False,
            pubs=None, progtrack=None):
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
                        raise
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
                to_remove = set()
                def add_installed_entry(f):
                        path = "%s/pkg/%s/installed" % \
                            (self.imgdir, f.get_dir_path())
                        pub = installed_file_publisher(path)
                        f.set_publisher(pub)
                        to_remove.add(path)
                        installed[f.pkg_name] = f

                if os.path.isdir(installed_state_dir):
                        for pl in sorted(os.listdir(installed_state_dir)):
                                fmristr = "%s" % urllib.unquote(pl)
                                f = pkg.fmri.PkgFmri(fmristr)
                                add_installed_entry(f)
                                # One additional file to remove for this case.
                                to_remove.add(os.path.join(installed_state_dir,
                                    pl))
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
                kcat = self.get_catalog(self.IMG_CATALOG_KNOWN)
                icat = self.get_catalog(self.IMG_CATALOG_INSTALLED)

                # Neither of these should exist on disk.
                assert not kcat.exists
                assert not icat.exists

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
                                                states.append(
                                                    self.__PKG_STATE_PREFERRED)
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

                                # Set preferred state.
                                states.append(self.__PKG_STATE_PREFERRED)

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

                        # XXX This awaits a proper messaging framework.
                        # Raising an exception here would be a decidedly
                        # bad thing as it would disrupt find_root, etc.
                        emsg("Package operation performance is currently "
                            "degraded.\nThis can be resolved by executing "
                            "'pkg refresh' as a privileged user.\n")
                        return

                # Assume that since mkdirs succeeded that the remaining data
                # can be saved and the image structure can be upgraded.

                # Attempt to save the image catalogs first
                # before changing structure.
                for cat in (kcat, icat):
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

                # Next, remove all of the old catalog and state files.
                shutil.rmtree(os.path.join(self.imgdir, "catalog"))
                for pathname in to_remove:
                        portable.remove(pathname)

                # Finally, mark complete.
                progtrack.cache_catalogs_done()

        def strtofmri(self, myfmri):
                return pkg.fmri.PkgFmri(myfmri, self.attrs["Build-Release"])

        def strtomatchingfmri(self, myfmri):
                return pkg.fmri.MatchingPkgFmri(myfmri,
                    self.attrs["Build-Release"])

        def load_constraints(self, progtrack):
                """Load constraints for all install pkgs"""

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                for f, actions in cat.actions([cat.DEPENDENCY],
                    excludes=self.list_excludes()):
                        if not self.constraints.start_loading(f):
                                # skip loading if already done
                                continue

                        for a in actions:
                                if a.name != "depend":
                                        continue
                                progtrack.evaluate_progress()
                                con = a.parse(self, f.get_name())[1]
                                self.constraints.update_constraints(con)
                        self.constraints.finish_loading(f)

        def __get_installed_unbound_inc_list(self):
                """Returns list of packages containing incorporation
                dependencies on which no other pkgs depend."""

                inc_tuples = []
                dependents = set()

                cat = self.get_catalog(self.IMG_CATALOG_INSTALLED)
                for f, actions in cat.actions([cat.DEPENDENCY],
                    excludes=self.list_excludes()):
                        for a in actions:
                                if a.name != "depend":
                                        continue
                                fmri_name = f.get_pkg_stem()
                                con_fmri = a.get_constrained_fmri(self)
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

                for p in set([ a[0] for a in inc_tuples ]):
                        yield pkg.fmri.PkgFmri(p, self.attrs["Build-Release"])

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
                        pat.publisher, pat.publisher)
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
                        matches = self.__multimatch(name, patterns, matcher)
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
                                            "upgradable": self.PKG_STATE_UPGRADABLE in states
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
                onames = {}
                # First eliminate any duplicate matches that are for unknown
                # publishers (publishers which have been removed from the image
                # configuration).
                publist = set(p.prefix for p in self.get_publishers().values())
                for m, st in matches:
                        if m.publisher in publist:
                                onames[m.get_pkg_stem()] = False
                                olist.append((m, st))

                # Next, if there are still multiple matches, eliminate matches
                # belonging to publishers that no longer have the FMRI in their
                # catalog.
                found_state = False
                if len(onames) > 1:
                        mlist = []
                        mnames = {}
                        for m, st in olist:
                                if not st["in_catalog"]:
                                        continue
                                stem = m.get_pkg_stem()
                                if st["state"] == self.PKG_STATE_INSTALLED:
                                        found_state = True
                                        # This stem has an installed
                                        # version.
                                        mnames[stem] = True
                                else:
                                        mnames.setdefault(stem, False)
                                mlist.append((m, st))
                        olist = mlist
                        onames = mnames

                # Finally, if there are still multiple matches, and an available
                # stem is installed, then eliminate any stems that do not
                # have an installed version.
                if found_state and len(onames) > 1:
                        mlist = []
                        mnames = {}
                        for m, st in olist:
                                stem = m.get_pkg_stem()
                                if onames[stem]:
                                        # This stem has an installed version.
                                        mnames[stem] = onames[stem]
                                        mlist.append((m, st))
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

                inc_list = list(self.__get_installed_unbound_inc_list())

                head = []
                tail = []
                for s in pkg_list:
                        try:
                                p = pkg.fmri.PkgFmri(s,
                                    self.attrs["Build-Release"])
                        except pkg.fmri.IllegalFmri:
                                illegal_fmris.append(s)
                                error = 1
                                continue

                        for inc in inc_list:
                                if inc.pkg_name == p.pkg_name:
                                        head.append((s, p))
                                        break
                        else:
                                tail.append((s, p))
                pkg_list = head + tail

                # This approach works only for cases w/ simple
                # incorporations; the apply_constraints_to_fmri
                # call below binds the version too quickly.  This
                # awaits a proper solver.

                # XXX This logic is very inefficient for cases like image-update
                # where the entire package inventory is matched against each
                # package (think num_installed * available_pkgs).
                ppub = self.get_preferred_publisher()
                for p, conp in pkg_list:
                        progtrack.evaluate_progress()
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
                                if m.publisher == ppub:
                                        pnames[m.get_pkg_stem()] = None
                                        pmatch.append((m, st))
                                else:
                                        npnames[m.get_pkg_stem()] = None
                                        npmatch.append((m, st))

                        if len(pnames) > 1:
                                # There can only be one preferred publisher, so
                                # filtering is pointless and these are truly
                                # ambiguous matches.
                                multiple_matches.append((p, pnames.keys()))
                                error = 1
                                continue
                        elif not pnames and len(npnames) > 1:
                                npmatch, npnames = \
                                    self.__filter_install_matches(npmatch)
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
                                ip.propose_fmri(pmatch[0][0])
                        elif npmatch:
                                ip.propose_fmri(npmatch[0][0])
                        else:
                                error = 1
                                unmatched_fmris.append(p)

                if error != 0:
                        raise api_errors.PlanCreationException(unmatched_fmris,
                            multiple_matches, [], illegal_fmris,
                            constraint_violations=constraint_violations)

                self.__call_imageplan_evaluate(ip, verbose)

        def make_uninstall_plan(self, fmri_list, recursive_removal,
            progresstracker, check_cancelation, noexecute, verbose=False):
                ip = imageplan.ImagePlan(self, progresstracker,
                    check_cancelation, recursive_removal, noexecute=noexecute)

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
                                if e.illegal:
                                        illegal_fmris.append(ppat)
                                else:
                                        try:
                                                list(self.inventory([ppat],
                                                    all_known=True,
                                                    ordered=False))
                                                missing_matches.append(ppat)
                                        except api_errors.InventoryException:
                                                unmatched_fmris.append(ppat)
                                err = 1
                                continue

                        if len(matches) > 1:
                                matchlist = [m[0] for m in matches]
                                multiple_matches.append((ppat, matchlist))
                                err = 1
                                continue

                        # Propose the removal of the first (and only!) match.
                        ip.propose_fmri_removal(matches[0][0])

                if err == 1:
                        raise api_errors.PlanCreationException(unmatched_fmris,
                            multiple_matches, missing_matches, illegal_fmris)

                self.__call_imageplan_evaluate(ip, verbose)

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
                        newimg.find_root(cmddir, progtrack=progtrack)

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
