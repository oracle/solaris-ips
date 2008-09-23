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

import cPickle
import errno
import os
import socket
import urllib
import urllib2
import httplib
import shutil
import tempfile
import time
import datetime
import calendar

import OpenSSL.crypto as osc

from pkg.misc import msg, emsg

# import uuid           # XXX interesting 2.5 module

import pkg.catalog as catalog
import pkg.updatelog as updatelog
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.version
import pkg.client.history as history
import pkg.client.imageconfig as imageconfig
import pkg.client.imageplan as imageplan
import pkg.client.retrieve as retrieve
import pkg.portable as portable
import pkg.client.query_engine as query_e
import pkg.client.indexer as indexer
import pkg.search_errors as search_errors

from pkg.misc import versioned_urlopen
from pkg.misc import TransferTimedOutException
from pkg.misc import CLIENT_DEFAULT_MEM_USE_KB
from pkg.client.imagetypes import *

img_user_prefix = ".org.opensolaris,pkg"
img_root_prefix = "var/pkg"

PKG_STATE_INSTALLED = "installed"
PKG_STATE_KNOWN = "known"

# Minimum number of days to issue warning before a certificate expires
MIN_WARN_DAYS = datetime.timedelta(days=30)

class CatalogRefreshException(Exception):
        def __init__(self, failed, total, succeeded):
                Exception.__init__(self)
                self.failed = failed
                self.total = total
                self.succeeded = succeeded

class InventoryException(Exception):
        def __init__(self, notfound=None, illegal=None):
                Exception.__init__(self)
                if notfound is None:
                        self.notfound = []
                else:
                        self.notfound = notfound
                if illegal is None:
                        self.illegal = []
                else:
                        self.illegal = illegal
                assert(self.notfound or self.illegal)

        def __str__(self):
                outstr = ""
                for x in self.illegal:
                        # Illegal FMRIs have their own __str__ method
                        outstr += "%s\n" % x
                for x in self.notfound:
                        outstr += "Not found in inventory: %s\n" % str(x)
                return outstr

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
                self.img_prefix = None
                self.index_dir = None
                self.repo_uris = []
                self.filter_tags = {}
                self.catalogs = {}
                self._catalog = {}
                self.pkg_states = None

                self.attrs = {}

                self.attrs["Policy-Require-Optional"] = False
                self.attrs["Policy-Pursue-Latest"] = True

                self.imageplan = None # valid after evaluation succceds

                # contains a dictionary w/ key = pkgname, value is miminum
                # frmi.XXX  Needs rewrite using graph follower
                self.optional_dependencies = {}

                # a place to keep info about saved_files; needed by file action
                self.saved_files = {}
 
        def find_root(self, d):

                def check_subdirs(sub_d, prefix):
                        for n in self.required_subdirs:
                                if not os.path.isdir(
                                    os.path.join(sub_d, prefix, n)):
                                        return False
                        return True

                # Ascend from the given directory d to find first
                # encountered image.
                startd = d
                # eliminate problem if relative path such as "." is passed in
                d = os.path.realpath(d)
                while True:
                        if os.path.isdir(os.path.join(d, img_user_prefix)) and \
                            os.path.isfile(os.path.join(d, img_user_prefix,
                                "cfg_cache")) and \
                            check_subdirs(d, img_user_prefix):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                self.type = IMG_USER
                                self.root = d
                                self.img_prefix = img_user_prefix
                                self.imgdir = os.path.join(d, self.img_prefix)
                                self.history.root_dir = self.imgdir
                                self.attrs["Build-Release"] = "5.11"
                                return
                        elif os.path.isdir(os.path.join(d, img_root_prefix)) \
                              and os.path.isfile(os.path.join(d,
                              img_root_prefix,"cfg_cache")) and \
                              check_subdirs(d, img_root_prefix):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                self.type = IMG_ENTIRE
                                self.root = d
                                self.img_prefix = img_root_prefix
                                self.imgdir = os.path.join(d, self.img_prefix)
                                self.history.root_dir = self.imgdir
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
                                raise ValueError, "directory %s not contained within an image" % startd

        def load_config(self):
                """Load this image's cached configuration from the default
                location."""

                # XXX Incomplete with respect to doc/image.txt description of
                # configuration.

                if self.root == None:
                        raise RuntimeError, "self.root must be set"

                ic = imageconfig.ImageConfig()

                if os.path.isfile("%s/cfg_cache" % self.imgdir):
                        ic.read("%s/cfg_cache" % self.imgdir)

                self.cfg_cache = ic

        # XXX mkdirs and set_attrs() need to be combined into a create
        # operation.
        def mkdirs(self):
                for sd in self.image_subdirs:
                        if not os.path.isdir(os.path.join(self.imgdir, sd)):
                                os.makedirs(os.path.join(self.imgdir, sd))

        def set_attrs(self, type, root, is_zone, auth_name, auth_url,
            ssl_key = None, ssl_cert = None):
                self.type = type
                self.root = root
                if self.type == IMG_USER:
                        self.img_prefix = img_user_prefix
                else:
                        self.img_prefix = img_root_prefix
                self.imgdir = os.path.join(self.root, self.img_prefix)
                self.history.root_dir = self.imgdir

                if not os.path.exists(os.path.join(self.imgdir, "cfg_cache")):
                        self.history.operation_name = "image-create"
                else:
                        self.history.operation_name = "image-set-attributes"

                self.mkdirs()

                self.cfg_cache = imageconfig.ImageConfig()

                if is_zone:
                        self.cfg_cache.filters["opensolaris.zone"] = "nonglobal"

                self.cfg_cache.authorities[auth_name] = {}
                self.cfg_cache.authorities[auth_name]["prefix"] = auth_name
                self.cfg_cache.authorities[auth_name]["origin"] = \
                    misc.url_affix_trailing_slash(auth_url)
                self.cfg_cache.authorities[auth_name]["mirrors"] = []
                self.cfg_cache.authorities[auth_name]["ssl_key"] = ssl_key
                self.cfg_cache.authorities[auth_name]["ssl_cert"] = ssl_cert

                self.cfg_cache.preferred_authority = auth_name

                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)
                self.history.operation_result = history.RESULT_SUCCEEDED

        def is_liveroot(self):
                return self.root == "/"

        def is_zone(self):
                zone = self.cfg_cache.filters.get("opensolaris.zone", "")
                return zone == "nonglobal"

        def get_root(self):
                return self.root

        def gen_authorities(self):
                if not self.cfg_cache:
                        raise RuntimeError, "empty ImageConfig"
                if not self.cfg_cache.authorities:
                        raise RuntimeError, "no defined authorities"
                for a in self.cfg_cache.authorities:
                        yield self.cfg_cache.authorities[a]

        def get_url_by_authority(self, authority = None):
                """Return the URL prefix associated with the given authority.
                For the undefined case, represented by None, return the
                preferred authority."""

                # XXX This function is a possible location to insert one or more
                # policies regarding use of mirror responses, etc.

                if authority == None:
                        authority = self.cfg_cache.preferred_authority

                try:
                        o = self.cfg_cache.authorities[authority]["origin"]
                except KeyError:
                        # If the authority that we're trying to get no longer
                        # exists, fall back to preferred authority.
                        authority = self.cfg_cache.preferred_authority
                        o = self.cfg_cache.authorities[authority]["origin"]

                return o.rstrip("/")

        def select_mirror(self, auth = None, chosen_set = None):
                """For the given authority, look through the status of
                the mirrors.  Pick the best one.  This method returns
                a DepotStatus object or None.  The chosen_set argument
                contains a set object that lists the mirrors that were
                previously chosen.  This allows us to choose both
                by depot status statistics and ensures we don't
                always pick the same depot."""

                if auth == None:
                        auth = self.cfg_cache.preferred_authority
                try:
                        slst = self.cfg_cache.mirror_status[auth]
                except KeyError:
                        # If the authority that we're trying to get no longer
                        # exists, fall back to preferred authority.
                        auth = self.cfg_cache.preferred_authority
                        slst = self.cfg_cache.mirror_status[auth]

                if len(slst) == 0:
                        if auth in self.cfg_cache.authority_status:
                                return self.cfg_cache.authority_status[auth]
                        else:
                                return None

                # Choose mirror with fewest errors.
                # If mirrors have same number of errors, choose mirror
                # with smaller number of good transactions.  Assume it's
                # being underused, not high-latency.
                #
                # XXX Will need to revisit the above assumption.
                def cmp_depotstatus(a, b):
                        res = cmp(a.errors, b.errors)
                        if res == 0:
                                return cmp(a.good_tx, b.good_tx)
                        return res                        

                slst.sort(cmp = cmp_depotstatus)

                if chosen_set and len(chosen_set) == len(slst):
                        chosen_set.clear()
                        chosen_set = None

                if chosen_set and slst[0] in chosen_set:
                        for ds in slst:
                                if ds not in chosen_set:
                                        return ds

                return slst[0]

        def get_ssl_credentials(self, authority = None, origin = None):
                """Return a tuple containing (ssl_key, ssl_cert) for the
                specified authority prefix.  If the authority isn't specified,
                attempt to determine the authority by the given origin.  If
                neither is specified, use the preferred authority.
                """

                if authority is None:
                        if origin is None:
                                authority = self.cfg_cache.preferred_authority
                        else:
                                auths = self.cfg_cache.authorities
                                for pfx, auth in auths.iteritems():
                                        if auth["origin"] == origin:
                                                authority = pfx
                                                break
                                else:
                                        return None

                try:
                        authent = self.cfg_cache.authorities[authority]
                except KeyError:
                        authority = self.cfg_cache.preferred_authority
                        authent = self.cfg_cache.authorities[authority]

                return (authent["ssl_key"], authent["ssl_cert"])

        @staticmethod
        def build_cert(path):
                """Take the file given in path, open it, and use it to create
                an X509 certificate object."""

                cf = file(path, "rb")
                certdata = cf.read()
                cf.close()
                cert = osc.load_certificate(osc.FILETYPE_PEM, certdata)

                return cert

        def check_cert_validity(self):
                """Look through the authorities defined for the image.  Print
                a message and exit with an error if one of the certificates
                has expired.  If certificates are getting close to expiration,
                print a warning instead."""

                for a in self.gen_authorities():
                        pfx, url, ssl_key, ssl_cert, dt, mir = \
                            self.split_authority(a)

                        if not ssl_cert:
                                continue

                        try:
                                cert = self.build_cert(ssl_cert)
                        except IOError, e:
                                if e.errno == errno.ENOENT:
                                        emsg(_("Certificate for authority %s" \
                                            " not found") % pfx)
                                        emsg(_("File was supposed to exist at" \
                                           "  path %s") % ssl_cert)
                                        return False 
                                else:
                                        raise
                        # OpenSSL.crypto.Error
                        except osc.Error, e:
                                emsg(_("Certificate for authority %s at" \
                                    " %s has an invalid format.") % \
                                    (pfx, ssl_cert))
                                return False

                        if cert.has_expired():
                                emsg(_("Certificate for authority %s" \
                                    " has expired") % pfx)
                                emsg(_("Please install a valid certificate"))
                                return False

                        now = datetime.datetime.utcnow()
                        nb = cert.get_notBefore()
                        t = time.strptime(nb, "%Y%m%d%H%M%SZ")
                        nbdt = datetime.datetime.utcfromtimestamp(
                            calendar.timegm(t))

                        # PyOpenSSL's has_expired() doesn't validate the notBefore
                        # time on the certificate.  Don't ask me why.

                        if nbdt > now:
                                emsg(_("Certificate for authority %s is" \
                                    " invalid") % pfx)
                                emsg(_("Certificate effective date is in" \
                                    " the future"))
                                return False
                        
                        na = cert.get_notAfter()
                        t = time.strptime(na, "%Y%m%d%H%M%SZ")
                        nadt = datetime.datetime.utcfromtimestamp(
                            calendar.timegm(t))

                        diff = nadt - now

                        if diff <= MIN_WARN_DAYS:
                                emsg(_("Certificate for authority %s will" \
                                    " expire in %d days" % (pfx, diff.days)))

                return True

        def get_default_authority(self):
                return self.cfg_cache.preferred_authority

        def has_authority(self, auth_name):
                return auth_name in self.cfg_cache.authorities

        def delete_authority(self, auth_name):
                self.history.operation_name = "delete-authority"
                if not self.has_authority(auth_name):
                        error = "no such authority '%s'" % auth_name
                        self.history.operation_errors.append(error)
                        self.history.operation_result = \
                            history.RESULT_FAILED_UNKNOWN
                        raise KeyError, error
                self.cfg_cache.delete_authority(auth_name)
                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)
                self.destroy_catalog(auth_name)
                self.cache_catalogs()
                self.history.operation_result = history.RESULT_SUCCEEDED

        def get_authority(self, auth_name):
                if not self.has_authority(auth_name):
                        raise KeyError, "no such authority '%s'" % auth_name

                return self.cfg_cache.authorities[auth_name]

        def split_authority(self, auth):
                prefix = auth["prefix"]
                update_dt = None

                try:
                        cat = self.catalogs[prefix]
                except KeyError:
                        cat = None

                if cat:
                        update_dt = cat.last_modified()
                        if update_dt:
                                update_dt = catalog.ts_to_datetime(update_dt)

                return (prefix, auth["origin"], auth["ssl_key"],
                    auth["ssl_cert"], update_dt, auth["mirrors"])

        def set_preferred_authority(self, auth_name):
                self.history.operation_name = "set-preferred-authority"
                if not self.has_authority(auth_name):
                        error = "no such authority '%s'" % auth_name
                        self.history.operation_errors.append(error)
                        self.history.operation_result = \
                            history.RESULT_FAILED_UNKNOWN
                        raise KeyError, error
                self.cfg_cache.preferred_authority = auth_name
                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)
                self.history.operation_result = history.RESULT_SUCCEEDED

        def set_authority(self, auth_name, origin_url = None, ssl_key = None,
            ssl_cert = None, refresh_allowed = True):
                self.history.operation_name = "set-authority"
                auths = self.cfg_cache.authorities

                refresh_needed = False

                if auth_name in auths:
                        # If authority already exists, only update non-NULL
                        # values passed to set_authority
                        if origin_url:
                                auths[auth_name]["origin"] = \
                                    misc.url_affix_trailing_slash(origin_url)
                                refresh_needed = True
                        if ssl_key:
                                auths[auth_name]["ssl_key"] = ssl_key
                        if ssl_cert:
                                auths[auth_name]["ssl_cert"] = ssl_cert

                else:
                        auths[auth_name] = {}
                        auths[auth_name]["prefix"] = auth_name
                        auths[auth_name]["origin"] = \
                            misc.url_affix_trailing_slash(origin_url)
                        auths[auth_name]["mirrors"] = []
                        auths[auth_name]["ssl_key"] = ssl_key
                        auths[auth_name]["ssl_cert"] = ssl_cert
                        refresh_needed = True

                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)
                
                if refresh_needed and refresh_allowed:
                        self.destroy_catalog(auth_name)
                        self.destroy_catalog_cache()
                        self.retrieve_catalogs(full_refresh=True,
                            auths=[auths[auth_name]])

                self.history.operation_result = history.RESULT_SUCCEEDED

        def add_mirror(self, auth_name, mirror):
                """Add the mirror URL contained in mirror to
                auth_name's list of mirrors."""
                self.history.operation_name = "add-mirror"
                auths = self.cfg_cache.authorities
                auths[auth_name]["mirrors"].append(mirror)
                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)
                self.history.operation_result = history.RESULT_SUCCEEDED

        def has_mirror(self, auth_name, url):
                """Returns true if url is in auth_name's list of mirrors."""

                return url in self.cfg_cache.authorities[auth_name]["mirrors"]

        def del_mirror(self, auth_name, mirror):
                """Remove the mirror URL contained in mirror from
                auth_name's list of mirrors."""

                self.history.operation_name = "delete-mirror"
                auths = self.cfg_cache.authorities

                if mirror in self.cfg_cache.authorities[auth_name]["mirrors"]:
                        auths[auth_name]["mirrors"].remove(mirror)
                        self.cfg_cache.write("%s/cfg_cache" % self.imgdir)

                self.history.operation_result = history.RESULT_SUCCEEDED

        def verify(self, fmri, progresstracker, **args):
                """generator that returns any errors in installed pkgs
                as tuple of action, list of errors"""

                for act in self.get_manifest(fmri, filtered = True).actions:
                        errors = act.verify(self, pkg_fmri=fmri, **args)
                        progresstracker.verify_add_progress(fmri)
                        actname = act.distinguished_name()
                        if errors:
                                progresstracker.verify_yield_error(actname,
                                    errors)
                                yield (actname, errors)

        def gen_installed_actions(self):
                """generates actions in installed image """

                for fmri in self.gen_installed_pkgs():
                        for act in self.get_manifest(fmri, filtered = True).actions:
                                yield act

        def get_fmri_manifest_pairs(self):
                """For each installed fmri, finds the path to its manifest file
                and adds the pair of the fmri and the path to a list. Once all
                installed fmris have been processed, the list is returned."""
                return [
                    (fmri, self.get_manifest_path(fmri))
                    for fmri in self.gen_installed_pkgs()
                ]

        def has_manifest(self, fmri):
                mpath = fmri.get_dir_path()

                local_mpath = "%s/pkg/%s/manifest" % (self.imgdir, mpath)

                if (os.path.exists(local_mpath)):
                        return True

                return False

        def _fetch_manifest_with_retries(self, fmri):
                """Wrapper function around _fetch_manifest to handle some
                exceptions and keep track of additional state."""

                m = None
                retry_count = misc.MAX_TIMEOUT_COUNT

                while not m:
                        try:
                                m = self._fetch_manifest(fmri)
                        except TransferTimedOutException:
                                retry_count -= 1

                                if retry_count <= 0:
                                        raise
                return m

        def _fetch_manifest(self, fmri):
                """Perform steps necessary to get manifest from remote host
                and write resulting contents to disk.  Helper routine for
                get_manifest.  Does not filter the results, caller must do
                that.  """

                m = manifest.Manifest()
                m.set_fmri(self, fmri)

                fmri_dir_path = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path())
                mpath = os.path.join(fmri_dir_path, "manifest")

                # Get manifest as a string from the remote host, then build
                # it up into an in-memory manifest, then write the finished
                # representation to disk.
                try:
                        mcontent = retrieve.get_manifest(self, fmri)
                        m.set_content(mcontent)
                except socket.timeout:
                        raise TransferTimedOutException

                # Write the originating authority into the manifest.
                # Manifests prior to this change won't contain this information.
                # In that case, the client attempts to re-download the manifest
                # from the depot.
                if not fmri.has_authority():
                        m["authority"] = self.get_default_authority()
                else:
                        m["authority"] = fmri.get_authority()

                try:
                        m.store(mpath)
                except EnvironmentError, e:
                        if e.errno not in (errno.EROFS, errno.EACCES):
                                raise

                return m

        def _valid_manifest(self, fmri, manifest):
                """Check authority attached to manifest.  Make sure
                it matches authority specified in FMRI."""

                authority = fmri.get_authority()
                if not authority:
                        authority = self.get_default_authority()

                if not "authority" in manifest:
                        return False

                if manifest["authority"] != authority:
                        return False

                return True

        def get_manifest_path(self, fmri):
                """Find on-disk manifest and create in-memory Manifest
                object, applying appropriate filters as needed."""
                mpath = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path(), "manifest")
                return mpath

        def get_manifest(self, fmri, filtered = False):
                """Find on-disk manifest and create in-memory Manifest
                object, applying appropriate filters as needed."""

                m = manifest.Manifest()

                fmri_dir_path = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path())
                mpath = os.path.join(fmri_dir_path, "manifest")

                # If the manifest isn't there, download.
                if not os.path.exists(mpath):
                        m = self._fetch_manifest_with_retries(fmri)
                else:
                        mcontent = file(mpath).read()
                        m.set_fmri(self, fmri)
                        m.set_content(mcontent)

                # If the manifest isn't from the correct authority, or
                # no authority is attached to the manifest, download a new one.
                if not self._valid_manifest(fmri, m):
                        try:
                                m = self._fetch_manifest_with_retries(fmri)
                        except NameError:
                                # In thise case, the client has failed to
                                # download a new manifest with the same name.
                                # We can either give up or drive on.  It makes
                                # the most sense to do the best we can with what
                                # we have.  Keep the old manifest and drive on.
                                pass

                # XXX perhaps all of the below should live in Manifest.filter()?
                if filtered:
                        filters = []
                        try:
                                f = file("%s/filters" % fmri_dir_path, "r")
                        except IOError, e:
                                if e.errno != errno.ENOENT:
                                        raise
                        else:
                                filters = [
                                    (l.strip(), compile(
                                        l.strip(), "<filter string>", "eval"))
                                    for l in f.readlines()
                                ]
                        m.filter(filters)

                return m

        def installed_file_authority(self, filepath):
                """Find the pkg's installed file named by filepath.
                Return the authority that installed this package."""

                read_only = False

                try:
                        f = file(filepath, "r+")
                except IOError, e:
                        if e.errno == errno.EACCES or e.errno == errno.EROFS:
                                read_only = True
                        else:
                                raise
                if read_only:
                        f = file(filepath, "r")

                flines = f.readlines()
                newauth = None

                try:
                        version, auth = flines
                except ValueError:
                        # If we get a ValueError, we've encoutered an
                        # installed file of a previous format.  If we want
                        # upgrade to work in this situation, it's necessary
                        # to assume that the package was installed from
                        # the preferred authority.  Here, we set up
                        # the authority to record that.
                        if flines:
                                auth = flines[0]
                                auth = auth.strip()
                                newauth = "%s_%s" % (pkg.fmri.PREF_AUTH_PFX,
                                    auth)
                        else:
                                newauth = "%s_%s" % (pkg.fmri.PREF_AUTH_PFX,
                                    self.get_default_authority())

                        # Exception handler is only part of this code that
                        # sets newauth
                        auth = newauth

                if newauth and not read_only:
                        # This is where we actually update the installed
                        # file with the new authority.
                        f.seek(0)
                        f.writelines(["VERSION_1\n", newauth])

                f.close()

                assert auth

                return auth

        def _install_file(self, fmri):
                """Returns the path to the "installed" file for a given fmri."""
                return "%s/pkg/%s/installed" % (self.imgdir, fmri.get_dir_path())

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
                        self.update_installed_pkgs()

                f = file(self._install_file(fmri), "w")

                f.writelines(["VERSION_1\n", fmri.get_authority_str()])
                f.close()

                fi = file("%s/state/installed/%s" % (self.imgdir,
                    fmri.get_link_path()), "w")
                fi.close()
                self.pkg_states[urllib.unquote(fmri.get_link_path())] = \
                    (PKG_STATE_INSTALLED, fmri)

        def remove_install_file(self, fmri):
                """Take an image and a fmri.  Remove the file from disk
                that indicates that the package named by the fmri has been
                installed."""

                # XXX This can be removed at some point in the future once we
                # think this link is available on all systems
                if not os.path.isdir("%s/state/installed" % self.imgdir):
                        self.update_installed_pkgs()

                os.unlink(self._install_file(fmri))
                try:
                        os.unlink("%s/state/installed/%s" % (self.imgdir,
                            fmri.get_link_path()))
                except EnvironmentError, e:
                        if e.errno != errno.ENOENT:
                                raise
                self.pkg_states[urllib.unquote(fmri.get_link_path())] = \
                    (PKG_STATE_KNOWN, fmri)

        def update_installed_pkgs(self):
                """Take the image's record of installed packages from the
                prototype layout, with an installed file in each
                $META/pkg/stem/version directory, to the $META/state/installed
                summary directory form."""

                tmpdir = "%s/state/installed.build" % self.imgdir

                # Create the link forest in a temporary directory.  We should
                # only execute this method once (if ever) in the lifetime of an
                # image, but if the path already exists and makedirs() blows up,
                # just be quiet if it's already a directory.  If it's not a
                # directory or something else weird happens, re-raise.
                try:
                        os.makedirs(tmpdir)
                except OSError, e:
                        if e.errno != errno.EEXIST or \
                            not os.path.isdir(tmpdir):
                                raise
                        return

                proot = "%s/pkg" % self.imgdir

                for pd, vd in (
                    (p, v)
                    for p in sorted(os.listdir(proot))
                    for v in sorted(os.listdir("%s/%s" % (proot, p)))
                    ):
                        path = "%s/%s/%s/installed" % (proot, pd, vd)
                        if not os.path.exists(path):
                                continue

                        fmristr = urllib.unquote("%s@%s" % (pd, vd))
                        auth = self.installed_file_authority(path)
                        f = pkg.fmri.PkgFmri(fmristr, authority = auth)
                        fi = file("%s/%s" % (tmpdir, f.get_link_path()), "w")
                        fi.close()

                # Someone may have already created this directory.  Junk the
                # directory we just populated if that's the case.
                try:
                        portable.rename(tmpdir, "%s/state/installed" % self.imgdir)
                except EnvironmentError, e:
                        if e.errno != errno.EEXIST:
                                raise
                        shutil.rmtree(tmpdir)

        def _get_version_installed(self, pfmri):
                pd = pfmri.get_pkg_stem()
                pdir = "%s/pkg/%s" % (self.imgdir,
                    pfmri.get_dir_path(stemonly = True))

                try:
                        pkgs_inst = [ (urllib.unquote("%s@%s" % (pd, vd)),
                            "%s/%s/installed" % (pdir, vd))
                            for vd in os.listdir(pdir)
                            if os.path.exists("%s/%s/installed" % (pdir, vd)) ]
                except OSError:
                        return None

                if len(pkgs_inst) == 0:
                        return None

                assert len(pkgs_inst) <= 1

                auth = self.installed_file_authority(pkgs_inst[0][1])

                return pkg.fmri.PkgFmri(pkgs_inst[0][0], authority = auth)

        def get_pkg_state_by_fmri(self, pfmri):
                """Given pfmri, determine the local state of the package."""

                return self.pkg_states.get(pfmri.get_fmri(anarchy = True)[5:],
                    (PKG_STATE_KNOWN, None))[0]

        def get_pkg_auth_by_fmri(self, pfmri):
                """Return the authority from which 'pfmri' was installed."""

                f = self.pkg_states.get(pfmri.get_fmri(anarchy = True)[5:],
                    (PKG_STATE_KNOWN, None))[1]
                if f:
                        # Return the non-preferred-prefixed name
                        return f.get_authority()
                return None

        def fmri_set_default_authority(self, fmri):
                """If the FMRI supplied as an argument does not have
                an authority, set it to the image's preferred authority."""

                if fmri.has_authority():
                        return

                fmri.set_authority(self.get_default_authority(), True)

        def get_catalog(self, fmri, exception = False):
                """Given a FMRI, look at the authority and return the
                correct catalog for this image."""

                # If FMRI has no authority, or is default authority,
                # then return the catalog for the preferred authority
                if not fmri.has_authority() or fmri.preferred_authority():
                        cat = self.catalogs[self.get_default_authority()]
                else:
                        try:
                                cat = self.catalogs[fmri.get_authority()]
                        except KeyError:
                                # If the authority that installed this package
                                # has vanished, pick the default authority
                                # instead.
                                if exception:
                                        raise
                                else:
                                        cat = self.catalogs[\
                                            self.get_default_authority()]

                return cat

        def has_version_installed(self, fmri):
                """Check that the version given in the FMRI or a successor is
                installed in the current image."""

                v = self._get_version_installed(fmri)

                if v and not fmri.has_authority():
                        fmri.set_authority(v.get_authority_str())
                elif not fmri.has_authority():
                        fmri.set_authority(self.get_default_authority(), True)

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

                                v = self._get_version_installed(f)

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

                v = self._get_version_installed(fmri)

                assert fmri.has_authority()

                if v:
                        return v
                else:
                        cat = self.get_catalog(fmri)

                        rpkgs = cat.rename_older_pkgs(fmri)
                        for f in rpkgs:
                                v = self._get_version_installed(f)
                                if v and self.fmri_is_successor(fmri, v):
                                        return v

                return None

        def is_installed(self, fmri):
                """Check that the exact version given in the FMRI is installed
                in the current image."""

                # All FMRIs passed to is_installed shall have an authority
                assert fmri.has_authority()

                v = self._get_version_installed(fmri)
                if not v:
                        return False

                return v == fmri

        def __build_dependents(self, progtrack):
                """Build a dictionary mapping packages to the list of packages
                that have required dependencies on them."""
                self.__req_dependents = {}

                for fmri in self.gen_installed_pkgs():
                        progtrack.evaluate_progress()
                        mfst = self.get_manifest(fmri, filtered = True)

                        for dep in mfst.gen_actions_by_type("depend"):
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

        def retrieve_catalogs(self, full_refresh = False,
            auths = None):
                failed = []
                total = 0
                succeeded = 0
                cat = None
                ts = 0

                if not auths:
                        auths = self.gen_authorities()

                for auth in auths:
                        total += 1

                        full_refresh_this_auth = False
                        
                        if auth["prefix"] in self.catalogs:
                                cat = self.catalogs[auth["prefix"]]
                                ts = cat.last_modified()

                                # Although we may have a catalog with a
                                # timestamp, the user may have changed the
                                # origin URL for the authority.  If this has
                                # occurred, we need to perform a full refresh.
                                if cat.origin() != auth["origin"]:
                                        full_refresh_this_auth = True

                        if ts and not full_refresh and \
                            not full_refresh_this_auth:
                                hdr = {'If-Modified-Since': ts}
                        else:
                                hdr = {}

                        ssl_tuple = self.get_ssl_credentials(auth["prefix"])

                        # XXX Mirror selection and retrieval policy?
                        try:
                                c, v = versioned_urlopen(auth["origin"],
                                    "catalog", [0], ssl_creds = ssl_tuple,
                                    headers = hdr, imgtype = self.type)
                        except urllib2.HTTPError, e:
                                # Server returns NOT_MODIFIED if catalog is up
                                # to date
                                if e.code == httplib.NOT_MODIFIED:
                                        succeeded += 1
                                else:
                                        failed.append((auth, e))
                                continue

                        except urllib2.URLError, e:
                                failed.append((auth, e))
                                continue
                        except ValueError, e:
                                failed.append((auth, e))
                                continue

                        # root for this catalog
                        croot = "%s/catalog/%s" % (self.imgdir, auth["prefix"])

                        try:
                                updatelog.recv(c, croot, ts, auth)
                        except IOError, e:
                                failed.append((auth, e))
                        except socket.timeout, e:
                                failed.append((auth, e))
                        else:
                                succeeded += 1

                self.cache_catalogs()
                
                if failed:
                        raise CatalogRefreshException(failed, total, succeeded)

        CATALOG_CACHE_VERSION = 1

        def cache_catalogs(self):
                """Read in all the catalogs and cache the data."""
                cache = {}
                for auth in self.gen_authorities():
                        croot = "%s/catalog/%s" % (self.imgdir, auth["prefix"])
                        # XXX Should I be removing pkg_names.pkl now that we're
                        # not using it anymore?
                        try:
                                catalog.Catalog.read_catalog(cache,
                                    croot, auth = auth["prefix"])
                        except EnvironmentError, e:
                                # If a catalog file is just missing, ignore it.
                                # If there's a worse error, make sure the user
                                # knows about it.
                                if e.errno == errno.ENOENT:
                                        pass
                                else:
                                        raise

                pickle_file = os.path.join(self.imgdir, "catalog/catalog.pkl")

                try:
                        pf = file(pickle_file, "wb")
                        # Version the dump file
                        cPickle.dump((self.CATALOG_CACHE_VERSION, cache), pf,
                            protocol = cPickle.HIGHEST_PROTOCOL)
                        pf.close()
                except (cPickle.PickleError, EnvironmentError):
                        try:
                                os.remove(pickle_file)
                        except EnvironmentError:
                                pass

                self._catalog = cache

        def load_catalog_cache(self):
                """Read in the cached catalog data."""

                self.__load_pkg_states()

                cache_file = os.path.join(self.imgdir, "catalog/catalog.pkl")
                try:
                        version, self._catalog = \
                            cPickle.load(file(cache_file, "rb"))
                except (cPickle.PickleError, EnvironmentError):
                        raise RuntimeError

                # If we don't recognize the version, complain.
                if version != self.CATALOG_CACHE_VERSION:
                        raise RuntimeError

                # Add the packages which are installed, but not in the catalog.
                # XXX Should we have a different state for these, so we can flag
                # them to the user?
                for state, f in self.pkg_states.values():
                        if state != PKG_STATE_INSTALLED:
                                continue
                        auth, name, vers = f.tuple()

                        if name not in self._catalog or \
                            vers not in self._catalog[name]["versions"]:
                                catalog.Catalog.cache_fmri(self._catalog, f,
                                    f.get_authority())

        def load_catalogs(self, progresstracker):
                for auth in self.gen_authorities():
                        croot = "%s/catalog/%s" % (self.imgdir, auth["prefix"])
                        progresstracker.catalog_start(auth["prefix"])
                        if auth["prefix"] == self.cfg_cache.preferred_authority:
                                authpfx = "%s_%s" % (pkg.fmri.PREF_AUTH_PFX,
                                    auth["prefix"])
                                c = catalog.Catalog(croot,
                                    authority=authpfx)
                        else:
                                c = catalog.Catalog(croot,
                                    authority = auth["prefix"])
                        self.catalogs[auth["prefix"]] = c
                        progresstracker.catalog_done()

                # Try to load the catalog cache file.  If that fails, load the
                # data from the canonical text copies of the catalogs from each
                # authority.  Try to save it, to spare the time in the future.
                # XXX Given that this is a read operation, should we be writing?
                try:
                        self.load_catalog_cache()
                except RuntimeError:
                        self.cache_catalogs()

        def destroy_catalog_cache(self):
                pickle_file = os.path.join(self.imgdir, "catalog/catalog.pkl")
                try:
                        portable.remove(pickle_file)
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        
        def destroy_catalog(self, auth_name):
                try:
                        shutil.rmtree("%s/catalog/%s" %
                            (self.imgdir, auth_name))
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise

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

                # Get the catalog for the correct authority
                cat = self.get_catalog(cfmri)
                return cat.rename_is_same_pkg(cfmri, pfmri)


        def fmri_is_successor(self, cfmri, pfmri):
                """Since the catalog keeps track of renames, it's no longer
                sufficient to rely on the FMRI class to determine whether a
                package is a successor.  This routine takes two FMRIs, and
                if they have the same authority, checks if they've been
                renamed.  If a rename has occurred, this runs the is_successor
                routine from the catalog.  Otherwise, this runs the standard
                fmri.is_successor() code."""

                # Get the catalog for the correct authority
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
                if self.pkg_states is not None:
                        for i in self.pkg_states.values():
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
                return (i[1] for i in self.pkg_states.values())

        def __load_pkg_states(self):
                """Build up the package state dictionary.

                This dictionary maps the full fmri string to a tuple of the
                state, the prefix of the authority from which it's installed,
                and the fmri object.

                Note that this dictionary only maps installed packages.  Use
                get_pkg_state_by_fmri() to retrieve the state for arbitrary
                packages.
                """

                if self.pkg_states is not None:
                        return

                installed_state_dir = "%s/state/installed" % self.imgdir

                self.pkg_states = {}

                # If the state directory structure has already been created,
                # loading information from it is fast.  The directory is
                # populated with symlinks, named by their (url-encoded) FMRI,
                # which point to the "installed" file in the corresponding
                # directory under /var/pkg.
                if os.path.isdir(installed_state_dir):
                        for pl in sorted(os.listdir(installed_state_dir)):
                                fmristr = urllib.unquote(pl)
                                tmpf = pkg.fmri.PkgFmri(fmristr)
                                path = self._install_file(tmpf)
                                auth = self.installed_file_authority(path)
                                f = pkg.fmri.PkgFmri(fmristr, authority = auth)

                                self.pkg_states[fmristr] = \
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
                                auth = self.installed_file_authority(path)
                                f = pkg.fmri.PkgFmri(fmristr, authority = auth)

                                self.pkg_states[fmristr] = \
                                    (PKG_STATE_INSTALLED, f)

        def clear_pkg_state(self):
                self.pkg_states = None

        def strtofmri(self, myfmri):
                return pkg.fmri.PkgFmri(myfmri, self.attrs["Build-Release"])

        def strtomatchingfmri(self, myfmri):
                return pkg.fmri.MatchingPkgFmri(myfmri, self.attrs["Build-Release"])

        def update_optional_dependency(self, inputfmri):
                """Updates pkgname to min fmri mapping if fmri is newer"""

                myfmri = inputfmri

                if isinstance(myfmri, str):
                        name = pkg.fmri.extract_pkg_name(myfmri)
                        myfmri = self.strtomatchingfmri(myfmri)
                else:
                        name = myfmri.get_name()

                try:
                        myfmri = self.inventory([ myfmri ], all_known = True,
                            matcher = pkg.fmri.exact_name_match).next()[0]
                except InventoryException:
                        # If we didn't find the package in the authority it's
                        # currently installed from, try again without specifying
                        # the authority.  This will get the first available
                        # instance of the package preferring the preferred
                        # authority.  Make sure to unset the authority on a copy
                        # of myfmri, just in case myfmri is the same object as
                        # the input fmri.
                        myfmri = myfmri.copy()
                        myfmri.set_authority(None)
                        myfmri = self.inventory([ myfmri ], all_known = True,
                            matcher = pkg.fmri.exact_name_match).next()[0]

                ofmri = self.optional_dependencies.get(name, None)
                if not ofmri or self.fmri_is_successor(myfmri, ofmri):
                        self.optional_dependencies[name] = myfmri

        def apply_optional_dependencies(self, myfmri):
                """Updates an fmri if optional dependencies require a newer version.
                Doesn't handle catalog renames... to ease programming for now,
                unversioned fmris are returned upgraded"""

                if isinstance(myfmri, str):
                        name = pkg.fmri.extract_pkg_name(myfmri)
                        myfmri = self.strtomatchingfmri(myfmri)
                else:
                        name = myfmri.get_name()

                minfmri = self.optional_dependencies.get(name, None)
                if not minfmri:
                        return myfmri

                if self.fmri_is_successor(minfmri, myfmri):
                        return minfmri
                return myfmri

        def load_optional_dependencies(self):
                for fmri in self.gen_installed_pkgs():
                        mfst = self.get_manifest(fmri, filtered = True)

                        for dep in mfst.gen_actions_by_type("depend"):
                                required, min_fmri, max_fmri = dep.parse(self)
                                if required == False:
                                        self.update_optional_dependency(min_fmri)

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
                the package version, the authority, and the raw authority
                string."""
                return [
                    (i, pat, pat.tuple()[2],
                        pat.get_authority(), pat.get_authority_str())
                    for i, pat in enumerate(patterns)
                    if matcher(name, pat.tuple()[1])
                ]

        def __inventory(self, patterns = None, all_known = False, matcher = None,
            constraint = pkg.version.CONSTRAINT_AUTO):
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
                                                    pkg.fmri.MatchingPkgFmri(pat,
                                                        "5.11")
                                        else:
                                                patterns[i] = \
                                                    pkg.fmri.PkgFmri(pat,
                                                    "5.11")
                                except pkg.fmri.IllegalFmri, e:
                                        illegals.append(e)

                if illegals:
                        raise InventoryException(illegal=illegals)

                pauth = self.cfg_cache.preferred_authority

                # matchingpats is the set of all the patterns which matched a
                # package in the catalog.  This allows us to return partial
                # failure if some patterns match and some don't.
                # XXX It would be nice to keep track of why some patterns failed
                # to match -- based on name, version, or authority.
                matchingpats = set()

                # XXX Perhaps we shouldn't sort here, but in the caller, to save
                # memory?
                for name in sorted(self._catalog.keys()):
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
                                # for authorities.
                                authlist = set(self._catalog[name][str(ver)][1])
                                nomatch = []
                                for i, match in enumerate(vmatches):
                                        if match[3] and \
                                            match[3] not in authlist:
                                                nomatch.append(i)

                                amatches = [
                                    vmatches[i]
                                    for i, match in enumerate(vmatches)
                                    if i not in nomatch
                                ]

                                if vmatches and not amatches:
                                        continue

                                # If no patterns were specified or any still-
                                # matching pattern specified no authority, we
                                # use the entire authlist for this version.
                                # Otherwise, we use the intersection of authlist
                                # and the auths in the patterns.
                                aset = set(i[3] for i in amatches)
                                if aset and None not in aset:
                                        authlist = set(
                                            m[3:5]
                                            for m in amatches
                                            if m[3] in authlist
                                        )
                                else:
                                        authlist = zip(authlist, authlist)

                                pfmri = self._catalog[name][str(ver)][0]

                                inst_state = self.get_pkg_state_by_fmri(pfmri)
                                inst_auth = self.get_pkg_auth_by_fmri(pfmri)
                                state = {
                                    "upgradable": ver != newest,
                                    "frozen": False,
                                    "incorporated": False,
                                    "excludes": False
                                }

                                # We yield copies of the fmri objects in the
                                # catalog because we add the authorities in, and
                                # don't want to mess up the canonical catalog.
                                # If a pattern had specified an authority as
                                # preferred, be sure to emit an fmri that way,
                                # too.
                                yielded = False
                                if all_known:
                                        for auth, rauth in authlist:
                                                nfmri = pfmri.copy()
                                                nfmri.set_authority(rauth,
                                                    auth == pauth)
                                                if auth == inst_auth:
                                                        state["state"] = \
                                                            PKG_STATE_INSTALLED
                                                else:
                                                        state["state"] = \
                                                            PKG_STATE_KNOWN
                                                yield nfmri, state
                                                yielded = True
                                elif inst_state == PKG_STATE_INSTALLED:
                                        nfmri = pfmri.copy()
                                        nfmri.set_authority(inst_auth,
                                            inst_auth == pauth)
                                        state["state"] = inst_state
                                        yield nfmri, state
                                        yielded = True

                                if yielded:
                                        matchingpats |= set(i[:2] for i in amatches)

                nonmatchingpats = [
                    opatterns[i]
                    for i, f in set(enumerate(patterns)) - matchingpats
                ]
                if nonmatchingpats:
                        raise InventoryException(notfound=nonmatchingpats)

        def inventory(self, *args, **kwargs):
                """Enumerate the package FMRIs in the image's catalog.

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
                "subsetting" constraint is used."""

                # "preferred" and "first_only" are private arguments that are
                # currently only used in evaluate_fmri(), but could be made more
                # generally useful.  "preferred" ensures that all potential
                # matches from the preferred authority are generated before
                # those from non-preferred authorities.  In the current
                # implementation, this consumes more memory.  "first_only"
                # signals us to return only the first match, which allows us to
                # save all the memory that "preferred" currently eats up.
                preferred = kwargs.pop("preferred", False)
                first_only = kwargs.pop("first_only", False)
                pauth = self.cfg_cache.preferred_authority

                if not preferred:
                        for f in self.__inventory(*args, **kwargs):
                                yield f
                else:
                        nplist = []
                        firstnp = None
                        for f in self.__inventory(*args, **kwargs):
                                if f[0].get_authority() == pauth:
                                        yield f
                                        if first_only:
                                                return
                                else:
                                        if first_only:
                                                if not firstnp:
                                                        firstnp = f
                                        else:
                                                nplist.append(f)
                        if first_only:
                                yield firstnp
                                return

                        for f in nplist:
                                yield f

        def update_index_dir(self, postfix="index"):
                """Since the index directory will not reliably be updated when
                the image root is, this should be called prior to using the
                index directory.
                """
                self.index_dir = os.path.join(self.imgdir, postfix)

        def degraded_local_search(self, args):
                msg("Search capabilities and performance are degraded.\n"
                    "To improve, run 'pkg rebuild-index'.")
                idxdir = os.path.join(self.imgdir, "pkg")

                # Convert a full directory path to the FMRI it represents.
                def idx_to_fmri(index):
                        return pkg.fmri.PkgFmri(urllib.unquote(os.path.dirname(
                            index[len(idxdir) + 1:]).replace(os.path.sep, "@")),
                            None)
                
                res = []

                for fmri, mfst in self.get_fmri_manifest_pairs():
                        m = manifest.Manifest()
                        try:
                                mcontent = file(mfst).read()
                        except:
                                # XXX log something?
                                continue
                        m.set_content(mcontent)
                        new_dict = m.search_dict()

                        tok = args[0]

                        for tok_type in new_dict.keys():
                                if new_dict[tok_type].has_key(tok):
                                        ak_list = new_dict[tok_type][tok]
                                        for action, keyval in ak_list:
                                                res.append((tok_type, fmri, \
                                                    action, keyval))
                return res

                
        def local_search(self, args, case_sensitive):
                """Search the image for the token in args[0]."""
                assert args[0]
                self.update_index_dir()
                qe = query_e.ClientQueryEngine(self.index_dir)
                query = query_e.Query(args[0], case_sensitive)
                try:
                        res = qe.search(query, self.gen_installed_pkg_names())
                except search_errors.NoIndexException:
                        res = self.degraded_local_search(args)
                return res

        def remote_search(self, args, servers = None):
                """Search for the token in args[0] on the servers in 'servers'.
                If 'servers' is empty or None, search on all known servers."""
                failed = []

                if not servers:
                        servers = self.gen_authorities()

                for auth in servers:
                        ssl_tuple = self.get_ssl_credentials(
                            authority = auth.get("prefix", None),
                            origin = auth["origin"])

                        try:
                                res, v = versioned_urlopen(auth["origin"],
                                    "search", [0], urllib.quote(args[0], ""),
                                     ssl_creds = ssl_tuple, imgtype = self.type)
                        except urllib2.HTTPError, e:
                                if e.code != httplib.NOT_FOUND:
                                        failed.append((auth, e))
                                continue
                        except urllib2.URLError, e:
                                failed.append((auth, e))
                                continue

                        try:
                                for line in res.read().splitlines():
                                        fields = line.split()
                                        if len(fields) < 4:
                                                yield fields[:2] + [ "", "" ]
                                        else:
                                                yield fields[:4]
                        except socket.timeout, e:
                                failed.append((auth, e))
                                continue

                if failed:
                        raise RuntimeError, failed

        def incoming_download_dir(self):
                """Return the directory path for incoming downloads
                that have yet to be completed.  Once a file has been
                successfully downloaded, it is moved to the cached download
                directory."""

                return os.path.normpath(os.path.join(self.imgdir, "download",
                    "incoming-%d" % os.getpid()))

        def cached_download_dir(self):
                """Return the directory path for cached content.
                Files that have been successfully downloaded live here."""

                return os.path.normpath(os.path.join(self.imgdir, "download"))

        def cleanup_downloads(self):
                """Clean up any downloads that were in progress but that
                did not successfully finish."""

                shutil.rmtree(self.incoming_download_dir(), True)

        def cleanup_cached_content(self):
                """Delete the directory that stores all of our cached
                downloaded content.  This may take a while for a large
                directory hierarchy."""

                if self.cfg_cache.flush_content_cache:
                        msg("Deleting content cache")
                        shutil.rmtree(self.cached_download_dir(), True)

        def salvagedir(self, path):
                """Called when directory contains something and it's not supposed
                to because it's being deleted. XXX Need to work out a better error
                passback mechanism. Path is rooted in /...."""

                salvagedir = os.path.normpath(
                    os.path.join(self.imgdir, "lost+found",
                    path + "-" + time.strftime("%Y%m%dT%H%M%SZ")))

                parent = os.path.dirname(salvagedir)
                if not os.path.exists(parent):
                        os.makedirs(parent)
                shutil.move(os.path.normpath(os.path.join(self.root, path)), salvagedir)
                # XXX need a better way to do this.
                emsg("\nWarning - directory %s not empty - contents preserved "
                        "in %s" % (path, salvagedir))

        def temporary_file(self):
                """ create a temp file under image directory for various purposes"""
                tempdir = os.path.normpath(os.path.join(self.imgdir, "tmp"))
                if not os.path.exists(tempdir):
                        os.makedirs(tempdir)
                fd, name = tempfile.mkstemp(dir=tempdir)
                os.close(fd)
                return name

        def expanddirs(self, dirs):
                """given a set of directories, return expanded set that includes
                all components"""
                out = set()
                for d in dirs:
                        p = d
                        while p != "":
                                out.add(p)
                                p = os.path.dirname(p)
                return out


        def make_install_plan(self, pkg_list, progress, filters = [],
            verbose = False, noexecute = False):
                """Take a list of packages, specified in pkg_list, and attempt
                to assemble an appropriate image plan.  This is a helper
                routine for some common operations in the client.

                This method checks all authorities for a package match;
                however, it defaults to choosing the preferred authority
                when an ambiguous package name is specified.  If the user
                wishes to install a package from a non-preferred authority,
                the full FMRI that contains an authority should be used
                to name the package."""

                error = 0
                ip = imageplan.ImagePlan(self, progress, filters = filters)

                self.load_optional_dependencies()

                for p in pkg_list:
                        try:
                                conp = self.apply_optional_dependencies(p)
                                matches = list(self.inventory([ conp ],
                                    all_known = True))
                        except InventoryException:
                                # XXX Module directly printing.
                                msg(_("""\
pkg: no package matching '%s' could be found in current catalog
     suggest relaxing pattern, refreshing and/or examining catalogs""") % p)
                                error = 1
                                continue

                        pnames = {}
                        pmatch = []
                        npnames = {}
                        npmatch = []
                        for m, state in matches:
                                if m.preferred_authority():
                                        pnames[m.get_pkg_stem()] = 1
                                        pmatch.append(m)
                                else:
                                        npnames[m.get_pkg_stem()] = 1
                                        npmatch.append(m)

                        if len(pnames.keys()) > 1:
                                # XXX Module directly printing.
                                msg(_("pkg: '%s' matches multiple packages") % \
                                    p)
                                for k in pnames.keys():
                                        msg("\t%s" % k)
                                error = 1
                                continue
                        elif len(pnames.keys()) < 1 and len(npnames.keys()) > 1:
                                # XXX Module directly printing.
                                msg(_("pkg: '%s' matches multiple packages") % \
                                    p)
                                for k in npnames.keys():
                                        msg("\t%s" % k)
                                error = 1
                                continue

                        # matches is a list reverse sorted by version, so take
                        # the first; i.e., the latest.
                        if len(pmatch) > 0:
                                ip.propose_fmri(pmatch[0])
                        else:
                                ip.propose_fmri(npmatch[0])

                if error != 0:
                        raise RuntimeError, "Unable to assemble image plan"

                if verbose:
                        msg(_("Before evaluation:"))
                        msg(ip)

                # A plan can be requested without actually performing an
                # operation on the image.
                if self.history.operation_name:
                        self.history.operation_start_state = ip.get_plan()

                ip.evaluate()
                self.imageplan = ip

                if self.history.operation_name:
                        self.history.operation_end_state = \
                            ip.get_plan(full=False)

                if verbose:
                        msg(_("After evaluation:"))
                        msg(ip.display())

        def rebuild_search_index(self, progtracker):
                """Rebuilds the search indexes.  Removes all 
                existing indexes and replaces them from scratch rather than 
                performing the incremental update which is usually used."""
                self.update_index_dir()
                if not os.path.isdir(self.index_dir):
                        self.mkdirs()
                ind = indexer.Indexer(self.index_dir,
                    CLIENT_DEFAULT_MEM_USE_KB, progtracker)
                ind.rebuild_index_from_scratch(self.get_fmri_manifest_pairs())

if __name__ == "__main__":
        pass
