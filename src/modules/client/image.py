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

# Copyright 2008 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import cPickle
import errno
import os
import urllib
import urllib2
import httplib
import shutil
import sys
import time
import types
 
# import uuid           # XXX interesting 2.5 module

import pkg.catalog as catalog
import pkg.updatelog as updatelog
import pkg.fmri
import pkg.manifest as manifest
import pkg.misc as misc
import pkg.version as version
import pkg.client.imageconfig as imageconfig
import pkg.client.imageplan as imageplan
import pkg.client.retrieve as retrieve
import pkg.client.filelist as filelist
import pkg.portable as portable

from pkg.misc import versioned_urlopen

IMG_ENTIRE = 0
IMG_PARTIAL = 1
IMG_USER = 2

img_user_prefix = ".org.opensolaris,pkg"
img_root_prefix = "var/pkg"

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

          $IROOT/state
               File containing image's opaque state.

        XXX Root path probably can't be absolute, so that we can combine or
        reuse Image contents.

        XXX Image file format?  Image file manipulation API?"""

        def __init__(self):
                self.cfg_cache = None
                self.type = None
                self.root = None
                self.imgdir = None
                self.img_prefix = None
                self.repo_uris = []
                self.filter_tags = {}
                self.catalogs = {}

                self.attrs = {}
                self.link_actions = None

                self.attrs["Policy-Require-Optional"] = False
                self.attrs["Policy-Pursue-Latest"] = True

                self.imageplan = None # valid after evaluation succceds
                
                # contains a dictionary w/ key = pkgname, value is miminum
                # frmi.XXX  Needs rewrite using graph follower
                self.optional_dependencies = {}

        def find_root(self, d):
                # Ascend from the given directory d to find first
                # encountered image.
                startd = d
                # eliminate problem if relative path such as "." is passed in
                d = os.path.realpath(d)
                while True:
                        if os.path.isdir(os.path.join(d, img_user_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                self.type = IMG_USER
                                self.root = d
                                self.img_prefix = img_user_prefix
                                self.imgdir = os.path.join(d, self.img_prefix)
                                self.attrs["Build-Release"] = "5.11"
                                return
                        elif os.path.isdir(os.path.join(d, img_root_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                self.type = IMG_ENTIRE
                                self.root = d
                                self.img_prefix = img_root_prefix
                                self.imgdir = os.path.join(d, self.img_prefix)
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
                if not os.path.isdir(self.imgdir + "/catalog"):
                        os.makedirs(self.imgdir + "/catalog")
                if not os.path.isdir(self.imgdir + "/file"):
                        os.makedirs(self.imgdir + "/file")
                if not os.path.isdir(self.imgdir + "/pkg"):
                        os.makedirs(self.imgdir + "/pkg")
                if not os.path.isdir(self.imgdir + "/index"):
                        os.makedirs(self.imgdir + "/index")

        def set_attrs(self, type, root, is_zone, auth_name, auth_url,
            ssl_key = None, ssl_cert = None):
                self.type = type
                self.root = root
                if self.type == IMG_USER:
                        self.img_prefix = img_user_prefix
                else:
                        self.img_prefix = img_root_prefix
                self.imgdir = os.path.join(self.root, self.img_prefix) 
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

        def is_liveroot(self):
                return self.root == "/"

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

        def get_ssl_credentials(self, authority = None):
                """Return a tuple containing (ssl_key, ssl_cert) for
                the specified authority."""

                if authority == None:
                        authority = self.cfg_cache.preferred_authority

                try:
                        authent = self.cfg_cache.authorities[authority]
                except KeyError:
                        authority = self.cfg_cache.preferred_authority
                        authent = self.cfg_cache.authorities[authority]

                return (authent["ssl_key"], authent["ssl_cert"])

        def get_default_authority(self):
                return self.cfg_cache.preferred_authority

        def has_authority(self, auth_name):
                return auth_name in self.cfg_cache.authorities

        def delete_authority(self, auth_name):
                if not self.has_authority(auth_name):
                        raise KeyError, "no such authority '%s'" % auth_name

                self.cfg_cache.delete_authority(auth_name)
                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)

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
                    auth["ssl_cert"], update_dt)

        def set_preferred_authority(self, auth_name):
                if not self.has_authority(auth_name):
                        raise KeyError, "no such authority '%s'" % auth_name
                self.cfg_cache.preferred_authority = auth_name
                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)

        def set_authority(self, auth_name, origin_url = None, ssl_key = None,
            ssl_cert = None, mirrors = []):

                auths = self.cfg_cache.authorities

                if auth_name in auths:
                        # If authority already exists, only update non-NULL
                        # values passed to set_authority
                        if origin_url:
                                auths[auth_name]["origin"] = \
                                    misc.url_affix_trailing_slash(origin_url)
                        if ssl_key:
                                auths[auth_name]["ssl_key"] = ssl_key
                        if ssl_cert:
                                auths[auth_name]["ssl_cert"] = ssl_cert
                        if mirrors:
                                auths[auth_name]["mirrors"] = mirrors

                else:
                        auths[auth_name] = {}
                        auths[auth_name]["prefix"] = auth_name
                        auths[auth_name]["origin"] = \
                            misc.url_affix_trailing_slash(origin_url)
                        auths[auth_name]["mirrors"] = mirrors
                        auths[auth_name]["ssl_key"] = ssl_key
                        auths[auth_name]["ssl_cert"] = ssl_cert

                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)

        def get_matching_fmris(self, patterns, matcher = None,
            constraint = None, counthash = None):
                """Iterate through all catalogs, looking for packages matching
                'pattern', based on the function in 'matcher' and the versioning
                constraint described by 'constraint'.  If 'matcher' is None,
                uses fmri subset matching as the default.  Returns a list of
                (catalog, fmri) pairs.  If 'counthash' is a dictionary, instead
                store the number of matched fmris for each package name which
                was matched."""

                # XXX Do we want to recognize regex (some) metacharacters and
                # switch automatically to the regex matcher?

                # XXX If the patterns contain an authority, we could reduce the
                # number of catalogs searched by only looking at catalogs whose
                # authorities match FMRIs in the pattern.

                # Check preferred authority first, if package isn't found here,
                # then check all authorities.

                cat = self.catalogs[self.cfg_cache.preferred_authority]

                m = cat.get_matching_fmris(patterns, matcher,
                    constraint, counthash)

                for k, c in self.catalogs.items():
                        if k == self.cfg_cache.preferred_authority:
                                continue
                        m.extend(c.get_matching_fmris(patterns, matcher,
                            constraint, counthash))

                ips = [ ip for ip in self.gen_installed_pkgs() if ip not in m ]

                m.extend(catalog.extract_matching_fmris(ips, patterns,
                    matcher, constraint, counthash))

                if not m:
                        raise KeyError, "packages matching '%s' not found in catalog or image" \
                            % patterns

                return m

        def verify(self, fmri, progresstracker, **args):
                """ generator that returns any errors in installed pkgs
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
                """ generates actions in installed image """

                for fmri in self.gen_installed_pkgs():
                        for act in self.get_manifest(fmri, filtered = True).actions:
                                yield act

        def get_link_actions(self):
                """ return a dictionary of hardlink action lists indexed by
                target """
                if self.link_actions != None:
                        return self.link_actions

                d = {}
                for act in self.gen_installed_actions():
                        if act.name == "hardlink":
                                t = act.get_target_path()
                                if t in d:
                                        d[t].append(act)
                                else:
                                        d[t] = [act]
                self.link_actions = d
                return d

        def has_manifest(self, fmri):
                mpath = fmri.get_dir_path()

                local_mpath = "%s/pkg/%s/manifest" % (self.imgdir, mpath)

                if (os.path.exists(local_mpath)):
                        return True

                return False

        def _fetch_manifest(self, fmri, filtered):
                """Perform steps necessary to get manifest from remote host
                and write resulting contents to disk."""

                m = manifest.Manifest()

                fmri_dir_path = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path())
                mpath = os.path.join(fmri_dir_path, "manifest")

                # Get manifest from remote host
                retrieve.get_manifest(self, fmri)

                mfile = file(mpath, "r")
                mcontent = mfile.read()
                mfile.close()

                m.set_fmri(self, fmri)
                m.set_content(mcontent)

                # Write the originating authority into the manifest.
                # Manifests prior to this change won't contain this information.
                # In that case, the client attempts to re-download the manifest
                # from the depot.
                if not fmri.has_authority():
                        m["authority"] = self.get_default_authority()
                else:
                        m["authority"] = fmri.get_authority()

                # Save manifest with authority information
                mcontent = str(m)
                mfile = file(mpath, "w+")
                mfile.write(mcontent)
                mfile.close()

                # Pickle the manifest's indices, for searching
                try:
                        pfile = file(os.path.join(fmri_dir_path, "index"), "wb")
                        m.pickle(pfile)
                        pfile.close()
                except IOError, e:
                        pass

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

        def get_manifest(self, fmri, filtered = False):
                """Find on-disk manifest and create in-memory Manifest
                object."""

                m = manifest.Manifest()

                fmri_dir_path = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path())
                mpath = os.path.join(fmri_dir_path, "manifest")

                # If the manifest isn't there, download.
                if not os.path.exists(mpath):
                        m = self._fetch_manifest(fmri, filtered)
                else:
                        mcontent = file(mpath).read()
                        m.set_fmri(self, fmri)
                        m.set_content(mcontent)

                # If the manifest isn't from the correct authority, or
                # no authority is attached to the manifest, download a new one.
                if not self._valid_manifest(fmri, m):
                        try:
                                m = self._fetch_manifest(fmri, filtered)
                        except NameError:
                                # In thise case, the client has failed to
                                # download a new manifest with the same name.
                                # We can either give up or drive on.  It makes
                                # the most sense to do the best we can with what
                                # we have.  Keep the old manifest and drive on.
                                pass

                return m

        @staticmethod
        def installed_file_authority(filepath):
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
                        auth = flines[0]
                        auth = auth.strip()
                        newauth = "%s_%s" % (pkg.fmri.PREF_AUTH_PFX, auth)

                if newauth and not read_only:
                        # This is where we actually update the installed
                        # file with the new authority.
                        f.seek(0)
                        f.writelines(["VERSION_1\n", newauth])
                        auth = newauth

                f.close()

                return auth

        def install_file_present(self, fmri):
                """Returns true if the package named by the fmri is installed
                on the system.  Otherwise, returns false."""

                return os.path.exists("%s/pkg/%s/installed" % (self.imgdir,
                    fmri.get_dir_path()))

        def add_install_file(self, fmri):
                """Take an image and fmri. Write a file to disk that
                indicates that the package named by the fmri has been
                installed."""

                f = file("%s/pkg/%s/installed" % (self.imgdir,
                    fmri.get_dir_path()), "w")

                f.writelines(["VERSION_1\n", fmri.get_authority_str()])
                f.close()

        def remove_install_file(self, fmri):
                """Take an image and a fmri.  Remove the file from disk
                that indicates that the package named by the fmri has been
                installed."""

                os.unlink("%s/pkg/%s/installed" % (self.imgdir,
                    fmri.get_dir_path()))

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
                if not auth:
                        auth = self.get_default_authority()

                return pkg.fmri.PkgFmri(pkgs_inst[0][0], authority = auth)

        def get_pkg_state_by_fmri(self, pfmri):
                """Given pfmri, determine the local state of the package."""

                if self.install_file_present(pfmri):
                        return "installed"

                return "known"

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

        def get_dependents(self, pfmri):
                """Return a list of the packages directly dependent on the given
                FMRI."""

                thedir = os.path.join(self.imgdir, "index", "depend",
                    urllib.quote(str(pfmri.get_pkg_stem())[5:], ""))

                if not os.path.isdir(thedir):
                        return []

                for v in os.listdir(thedir):
                        f = pkg.fmri.PkgFmri(pfmri.get_pkg_stem() + "@" + v,
                            self.attrs["Build-Release"])
                        if self.fmri_is_successor(pfmri, f):
                                dependents = [
                                    urllib.unquote(d)
                                    for d in os.listdir(os.path.join(thedir, v))
                                    if os.path.exists(
                                        os.path.join(thedir, v, d, "installed"))
                                ]

                return dependents

        def retrieve_catalogs(self, full_refresh = False):
                failed = []
                total = 0
                succeeded = 0
                cat = None
                full_refresh = False
                ts = 0

                for auth in self.gen_authorities():
                        total += 1

                        if auth["prefix"] in self.catalogs:
                                cat = self.catalogs[auth["prefix"]]
                                ts = cat.last_modified()

                                # Although we may have a catalog with a
                                # timestamp, the user may have changed the
                                # origin URL for the authority.  If this has
                                # occurred, we need to perform a full refresh.
                                if cat.origin() != auth["origin"]:
                                        full_refresh = True

                        if ts and not full_refresh:
                                hdr = {'If-Modified-Since': ts}
                        else:
                                hdr = {}

                        ssl_tuple = self.get_ssl_credentials(auth["prefix"])

                        # XXX Mirror selection and retrieval policy?
                        try:
                                c, v = versioned_urlopen(auth["origin"],
                                    "catalog", [0], ssl_creds = ssl_tuple,
                                    headers = hdr)
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
                        else:
                                succeeded += 1

                if failed:
                        raise RuntimeError, (failed, total, succeeded)

        def load_catalogs(self, progresstracker):
                for auth in self.gen_authorities():
                        croot = "%s/catalog/%s" % (self.imgdir, auth["prefix"])
                        progresstracker.catalog_start(auth["prefix"])
                        if auth["prefix"] == self.cfg_cache.preferred_authority:
                                authpfx = "%s_%s" % (pkg.fmri.PREF_AUTH_PFX,
                                    auth["prefix"])
                                c = catalog.Catalog(croot, authority = authpfx)
                        else:
                                c = catalog.Catalog(croot,
                                    authority = auth["prefix"])
                        self.catalogs[auth["prefix"]] = c
                        progresstracker.catalog_done()

        def fmri_is_same_pkg(self, cfmri, pfmri):
                """Determine whether fmri and pfmri share the same package
                name, even if they're not equivalent versions.  This
                also checks if two packages with different names are actually
                the same because of a rename operation."""

                # If authorities don't match, this can't be a successor
                if not pkg.fmri.is_same_authority(cfmri.authority, pfmri.authority):
                        return False

                # Get the catalog for the correct authority
                cat = self.get_catalog(cfmri)

                # If the catalog has a rename record that names fmri as a
                # destination, it's possible that pfmri could be the same pkg by
                # rename.

                if cfmri.is_same_pkg(pfmri):
                        return True
                else:
                        return cat.rename_is_same_pkg(cfmri, pfmri)

        def fmri_is_successor(self, cfmri, pfmri):
                """Since the catalog keeps track of renames, it's no longer
                sufficient to rely on the FMRI class to determine whether a
                package is a successor.  This routine takes two FMRIs, and
                if they have the same authority, checks if they've been
                renamed.  If a rename has occurred, this runs the is_successor
                routine from the catalog.  Otherwise, this runs the standard
                fmri.is_successor() code."""

                # If authorities don't match, this can't be a successor
                if not pkg.fmri.is_same_authority(cfmri.authority, pfmri.authority):
                        return False

                # Get the catalog for the correct authority
                cat = self.get_catalog(cfmri)

                # If the catalog has a rename record that names fmri as a
                # destination, it's possible that pfmri could be a successor by
                # rename.
                if cfmri.is_successor(pfmri):
                        return True
                else:
                        return cat.rename_is_successor(cfmri, pfmri)

        def gen_known_package_fmris(self):
                """Generate the list of known packages, being the union of the
                   catalogs and the installed image."""

                li = [ x for x in self.gen_installed_pkgs() ]

                # Generate those packages in the set of catalogs.
                for c in self.catalogs.values():
                        for pf in c.fmris():
                                if pf in li:
                                        li.remove(pf)
                                yield pf

        def gen_installed_pkgs(self):
                proot = "%s/pkg" % self.imgdir

                for pd in sorted(os.listdir(proot)):
                        for vd in sorted(os.listdir("%s/%s" % (proot, pd))):
                                path = "%s/%s/%s/installed" % (proot, pd, vd)
                                if not os.path.exists(path):
                                        continue

                                auth = self.installed_file_authority(path)
                                if not auth:
                                        auth = self.get_default_authority()

                                fmristr = urllib.unquote("%s@%s" % (pd, vd))

                                yield pkg.fmri.PkgFmri(fmristr, authority = auth)

        def strtofmri(self, myfmri):
                ret = pkg.fmri.PkgFmri(myfmri, 
                    self.attrs["Build-Release"],
                    authority = self.get_default_authority())
                return ret

        def update_optional_dependency(self, inputfmri):
                """Updates pkgname to min fmri mapping if fmri is newer"""

                myfmri = inputfmri

                if isinstance(myfmri, str):
                        name = pkg.fmri.extract_pkg_name(myfmri)
                        myfmri = self.strtofmri(myfmri)
                else:
                        name = myfmri.get_name()
                        self.fmri_set_default_authority(myfmri)

                ofmri = self.optional_dependencies.get(name, None)
                if not ofmri or self.fmri_is_successor(ofmri, myfmri):
                               self.optional_dependencies[name] = myfmri

        def apply_optional_dependencies(self, myfmri):
                """Updates an fmri if optional dependencies require a newer version.
                Doesn't handle catalog renames... to ease programming for now,
                unversioned fmris are returned upgraded"""

                if isinstance(myfmri, str):
                        name = pkg.fmri.extract_pkg_name(myfmri)
                        myfmri = self.strtofmri(myfmri)
                else:
                        name = myfmri.get_name()

                minfmri = self.optional_dependencies.get(name, None)
                if not minfmri:
                        return myfmri

                if not myfmri.has_version() or self.fmri_is_successor(minfmri, myfmri):
                        return minfmri
                return myfmri

        def load_optional_dependencies(self):
                for fmri in self.gen_installed_pkgs():
                        deps = self.get_manifest(fmri, filtered = True).get_dependencies()
                        for required, min_fmri, max_fmri in deps:
                                if required == False:
                                        self.update_optional_dependency(min_fmri)

        def get_user_by_name(self, name):
                return portable.get_user_by_name(name, self.root, 
                                                 self.type != IMG_USER)

        def get_name_by_uid(self, uid):
                # XXX What to do about IMG_PARTIAL?
                return portable.get_name_by_uid(uid, self.root, 
                                                self.type != IMG_USER)

        def get_group_by_name(self, name):
                return portable.get_group_by_name(name, self.root, 
                                                  self.type != IMG_USER)

        def get_name_by_gid(self, gid):
                return portable.get_name_by_gid(gid, self.root, 
                                                self.type != IMG_USER)

        def gen_inventory(self, patterns, all_known=False):
                """Iterating the package inventory, yielding per-package info.

                Yielded data are of the form package,dict, where dict is:
                  state  : package installation state
                  frozen,
                  incorporated,
                  excludes,
                  upgradable : Booleans indicating the aforementioned flags.
                """
                pkgs_known = []
                badpats = []

                if patterns:
                        for p in patterns:
                                try:
                                        # XXX dp: not sure if this is
                                        # right with respect to the code
                                        # 6 or 7 lines further below.
                                        for m in self.get_matching_fmris(p):
                                                if all_known or self.is_installed(m):
                                                        pkgs_known.extend([ m ])
                                except KeyError:
                                        badpats.append(p)

                        pkgs_known.extend(
                                [ x for x in self.gen_installed_pkgs()
                                for p in patterns
                                if pkg.fmri.fmri_match(x.get_pkg_stem(), p)
                                and not x in pkgs_known ] )
                elif all_known:
                        pkgs_known = [ pf for pf in
                            sorted(self.gen_known_package_fmris()) ]
                else:
                        pkgs_known = sorted(self.gen_installed_pkgs())

                if pkgs_known:
                        counthash = {}
                        self.get_matching_fmris(pkgs_known,
                                                counthash = counthash)

                for p in pkgs_known:
                        if counthash[p] > 1:
                                upgradable = True
                        else:
                                upgradable = False
                        inventory = {
                                "state": self.get_pkg_state_by_fmri(p),
                                "frozen": False,
                                "incorporated": False,
                                "excludes": False,
                                "upgradable": upgradable}
                        yield p, inventory

                if badpats:
                        raise RuntimeError, badpats

        def local_search(self, args):
                """Search the image for the token in args[0]."""
                idxdir = os.path.join(self.imgdir, "pkg")

                # Convert a full directory path to the FMRI it represents.
                def idx_to_fmri(index):
                        return pkg.fmri.PkgFmri(urllib.unquote(os.path.dirname(
                            index[len(idxdir) + 1:]).replace("/", "@")), None)

                indices = (
                    (os.path.join(dir, "index"), os.path.join(dir, "manifest"))
                    for dir, dirnames, filenames in os.walk(idxdir)
                    if "manifest" in filenames and "installed" in filenames
                )

                for index, mfst in indices:
                        # Try loading the index; if that fails, try parsing the
                        # manifest.
                        try:
                                d = cPickle.load(file(index))
                        except:
                                m = manifest.Manifest()
                                try:
                                        mcontent = file(mfst).read()
                                except:
                                        # XXX log something?
                                        continue
                                m.set_content(mcontent)
                                try:
                                        m.pickle(file(index, "wb"))
                                except:
                                        pass
                                d = m.search_dict()

                        for k, v in d.items():
                                if args[0] in v:
                                        # Yield the index name (such as
                                        # "basename", the fmri, and then
                                        # the "match results" which
                                        # include the action name and
                                        # the value of the key attribute
                                        try:
                                                yield k, idx_to_fmri(index), \
                                                    v[args[0]][0], v[args[0]][1]
                                        except TypeError:
                                                yield k, idx_to_fmri(index), \
                                                    "", ""

        def remote_search(self, args, servers = None):
                """Search for the token in args[0] on the servers in 'servers'.
                If 'servers' is empty or None, search on all known servers."""
                failed = []

                if not servers:
                        servers = self.gen_authorities()

                for auth in servers:
                        ssl_tuple = self.get_ssl_credentials(auth["prefix"])

                        try:
                                res, v = versioned_urlopen(auth["origin"],
                                    "search", [0], urllib.quote(args[0], ""),
                                     ssl_creds = ssl_tuple)
                        except urllib2.HTTPError, e:
                                if e.code != httplib.NOT_FOUND:
                                        failed.append((auth, e))
                                continue
                        except urllib2.URLError, e:
                                failed.append((auth, e))
                                continue

                        for l in res.read().splitlines():
                                fields = l.split()
                                if len(fields) < 4:
                                       yield fields[:2] + [ "", "" ]
                                else:
                                       yield fields[:4]
                if failed:
                        raise RuntimeError, failed

        def get_download_dir(self):
                return os.path.normpath(os.path.join(
                                self.imgdir,
                                "download",
                                str(os.getpid())))

        def cleanup_downloads(self):
                shutil.rmtree(self.get_download_dir(), True)

        def salvagedir(self, path):
                """Called when directory contains something and it's not supposed
                to because it's being deleted. XXX Need to work out a better error
                passback mechanism. Path is rooted in /...."""
                
                salvagedir = os.path.normpath(
                    os.path.join(self.imgdir, "lost+found",
                                 path + "-" + time.strftime("%Y-%m-%d+%H:%M:%S")))        

                os.makedirs(salvagedir)
                shutil.move(os.path.normpath(os.path.join(self.root, path)), salvagedir)
                # XXX need a better way to do this.
                print >> sys.stderr, \
                    "\nWarning - directory %s not empty - contents preserved in %s" % \
                    (path, salvagedir)

        def expanddirs(self, dirs):
                """ given a set of directories, return expanded set that includes 
                all components"""
                out = set()
                for d in dirs:
                        p = d
                        while p != "":
                                out.add(p)
                                p = os.path.dirname(p)
                return out
                        
                
        def list_install(self, pkg_list, progress, filters = [],
            verbose = False, noexecute = False):
                """Take a list of packages, specified in pkg_list, and attempt
                to install them on the system.

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
                                matches = self.get_matching_fmris(conp,
                                    constraint = version.CONSTRAINT_AUTO)
                        except KeyError:
                                # XXX Module directly printing.
                                print _("""\
pkg: no package matching '%s' could be found in current catalog
     suggest relaxing pattern, refreshing and/or examining catalogs""") % p
                                error = 1
                                continue

                        pnames = {}
                        pmatch = []
                        npnames = {}
                        npmatch = []
                        for m in matches:
                                if m.preferred_authority():
                                        pnames[m.get_pkg_stem()] = 1
                                        pmatch.append(m)
                                else:
                                        npnames[m.get_pkg_stem()] = 1
                                        npmatch.append(m)

                        if len(pnames.keys()) > 1:
                                # XXX Module directly printing.
                                print \
                                    _("pkg: '%s' matches multiple packages") % p
                                for k in pnames.keys():
                                        print "\t%s" % k
                                error = 1
                                continue
                        elif len(pnames.keys()) < 1 and len(npnames.keys()) > 1:
                                # XXX Module directly printing.
                                print \
                                    _("pkg: '%s' matches multiple packages") % p
                                for k in npnames.keys():
                                        print "\t%s" % k
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
                        print _("Before evaluation:")
                        print ip

                ip.evaluate()
                self.imageplan = ip 

                if verbose:
                        print _("After evaluation:")
                        ip.display()

                if not noexecute:
                        ip.execute()

if __name__ == "__main__":
        pass
