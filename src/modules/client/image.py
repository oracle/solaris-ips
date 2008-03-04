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
import grp
import pwd
import urllib
import urllib2
import shutil
import httplib
# import uuid           # XXX interesting 2.5 module

import pkg.catalog as catalog
import pkg.updatelog as updatelog
import pkg.fmri as fmri
import pkg.manifest as manifest
import pkg.version as version
import pkg.client.imageconfig as imageconfig
import pkg.client.imageplan as imageplan
import pkg.client.retrieve as retrieve
import pkg.client.filelist as filelist

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

                self.users = {}
                self.uids = {}
                self.users_lastupdate = 0
                self.groups = {}
                self.gids = {}
                self.groups_lastupdate = 0

                self.catalogs = {}

                self.attrs = {}
                self.link_actions = {}

                self.attrs["Policy-Require-Optional"] = False
                self.attrs["Policy-Pursue-Latest"] = True

        def find_root(self, d):
                # Ascend from current working directory to find first
                # encountered image.
                while True:
                        if os.path.isdir("%s/%s" % (d, img_user_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                self.type = IMG_USER
                                self.root = d
                                self.img_prefix = img_user_prefix
                                self.imgdir = "%s/%s" % (d, self.img_prefix)
                                self.attrs["Build-Release"] = "5.11"
                                return
                        elif os.path.isdir("%s/%s" % (d, img_root_prefix)):
                                # XXX Look at image file to determine filter
                                # tags and repo URIs.
                                # XXX Look at image file to determine if this
                                # image is a partial image.
                                self.type = IMG_ENTIRE
                                self.root = d
                                self.img_prefix = img_root_prefix
                                self.imgdir = "%s/%s" % (d, self.img_prefix)
                                self.attrs["Build-Release"] = "5.11"
                                return

                        assert d != "/"

                        # XXX follow symlinks or not?
                        d = os.path.normpath(os.path.join(d, os.path.pardir))

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

        def set_attrs(self, type, root, is_zone, auth_name, auth_url):
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
                self.cfg_cache.authorities[auth_name]["origin"] = auth_url
                self.cfg_cache.authorities[auth_name]["mirrors"] = None

                self.cfg_cache.preferred_authority = auth_name

                self.cfg_cache.write("%s/cfg_cache" % self.imgdir)

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

                o = self.cfg_cache.authorities[authority]["origin"]

                return o.rstrip("/")

        def get_default_authority(self):
                return self.cfg_cache.preferred_authority

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

                m.extend(catalog.extract_matching_fmris(ips, cat, patterns,
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
                if self.link_actions:
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

        def get_manifest(self, fmri, filtered = False):
                m = manifest.Manifest()

                fmri_dir_path = os.path.join(self.imgdir, "pkg",
                    fmri.get_dir_path())
                mpath = os.path.join(fmri_dir_path, "manifest")

                # If the manifest isn't there, download and retry.
                try:
                        mcontent = file(mpath).read()
                except IOError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        retrieve.get_manifest(self, fmri)
                        mcontent = file(mpath).read()

                m.set_fmri(self, fmri)
                m.set_content(mcontent)

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

        @staticmethod
        def installed_file_authority(filepath):
                """Find the pkg's installed file named by filepath.
                Return the authority that installed this package."""

                f = file(filepath, "r")
                auth = f.readline()
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

                f.write(fmri.authority)
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

                return fmri.PkgFmri(pkgs_inst[0][0], authority = auth)

        def get_pkg_state_by_fmri(self, pfmri):
                """Given pfmri, determine the local state of the package."""

                if self.install_file_present(pfmri):
                        return "installed"

                return "known"

        def fmri_set_default_authority(self, fmri):
                """If the FMRI supplied as an argument does not have
                an authority, set it to the image's preferred authority."""

                if fmri.authority:
                        return

                fmri.set_authority(self.get_default_authority())

        def has_version_installed(self, fmri):
                """Check that the version given in the FMRI or a successor is
                installed in the current image.  Return the FMRI of the
                version that is installed."""

                v = self._get_version_installed(fmri)

                if v and fmri.authority == None:
                        fmri.authority = v.authority
                elif fmri.authority == None:
                        fmri.authority = self.get_default_authority()

                if v and self.fmri_is_successor(v, fmri):
                        return True
                else:
                        # Get the catalog for the correct authority
                        try:
                                cat = self.catalogs[fmri.authority]
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

                assert fmri.authority

                if v:
                        return v
                else:
                        cat = self.catalogs[fmri.authority]

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
                assert fmri.authority

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
                        f = fmri.PkgFmri(pfmri.get_pkg_stem() + "@" + v,
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
                ts = 0

                for auth in self.gen_authorities():
                        total += 1

                        if auth["prefix"] in self.catalogs:
                                cat = self.catalogs[auth["prefix"]]
                                ts = cat.last_modified()

                        if ts and not full_refresh:
                                hdr = {'If-Modified-Since': ts}
                        else:
                                hdr = {}

                        # XXX Mirror selection and retrieval policy?
                        try:
                                c, v = versioned_urlopen(auth["origin"],
                                    "catalog", [0], headers = hdr)
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

                        # root for this catalog
                        croot = "%s/catalog/%s" % (self.imgdir, auth["prefix"])

                        try:
                                updatelog.recv(c, croot, ts)
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
                        c = catalog.Catalog(croot, authority = auth["prefix"])
                        self.catalogs[auth["prefix"]] = c
                        progresstracker.catalog_done()

        def fmri_is_same_pkg(self, fmri, pfmri):
                """Determine whether fmri and pfmri share the same package
                name, even if they're not equivalent versions.  This
                also checks if two packages with different names are actually
                the same because of a rename operation."""

                # If authorities don't match, this can't be a successor
                if fmri.authority != pfmri.authority:
                        return False

                # Get the catalog for the correct authority
                cat = self.catalogs[fmri.authority]

                # If the catalog has a rename record that names fmri as a
                # destination, it's possible that pfmri could be the same pkg by
                # rename.
                
                if fmri.is_same_pkg(pfmri):
                        return True
                else:
                        return cat.rename_is_same_pkg(fmri, pfmri)

        def fmri_is_successor(self, fmri, pfmri):
                """Since the catalog keeps track of renames, it's no longer
                sufficient to rely on the FMRI class to determine whether a
                package is a successor.  This routine takes two FMRIs, and
                if they have the same authority, checks if they've been
                renamed.  If a rename has occurred, this runs the is_successor
                routine from the catalog.  Otherwise, this runs the standard
                fmri.is_successor() code."""

                # If authorities don't match, this can't be a successor
                if fmri.authority != pfmri.authority:
                        return False

                # Get the catalog for the correct authority
                cat = self.catalogs[fmri.authority]

                # If the catalog has a rename record that names fmri as a
                # destination, it's possible that pfmri could be a successor by
                # rename.
                if fmri.is_successor(pfmri):
                        return True
                else:
                        return cat.rename_is_successor(fmri, pfmri)

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

                                yield fmri.PkgFmri(fmristr, authority = auth)

        def getpwnam(self, name):
                """Do a name lookup in the image's password database.

                Keep a cached copy in memory for fast lookups, and fall back to
                the current environment if the password database isn't
                available.
                """

                # XXX What to do about IMG_PARTIAL?
                if self.type == IMG_USER:
                        return pwd.getpwnam(name)

                passwd_file = os.path.join(self.root, "etc/passwd")

                try:
                        passwd_stamp = os.stat(passwd_file).st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        # If the password file doesn't exist, bootstrap
                        # ourselves from the current environment.
                        return pwd.getpwnam(name)

                # If the timestamp on the file isn't newer than the last time we
                # checked, all its entries will already be in our cache, so we
                # won't find the name.
                if passwd_stamp > self.users_lastupdate:
                        self.load_passwd(passwd_file)

                try:
                        return self.users[name]
                except:
                        raise KeyError, "getpwnam(): name not found: %s" % name

        def getpwuid(self, uid):
                """Do a uid lookup in the image's password database.

                Keep a cached copy in memory for fast lookups, and fall back to
                the current environment if the password database isn't
                available.
                """

                # XXX What to do about IMG_PARTIAL?
                if self.type == IMG_USER:
                        return pwd.getpwuid(uid)

                passwd_file = os.path.join(self.root, "etc/passwd")

                try:
                        passwd_stamp = os.stat(passwd_file).st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        # If the password file doesn't exist, bootstrap
                        # ourselves from the current environment.
                        return pwd.getpwuid(uid)

                # If the timestamp on the file isn't newer than the last time we
                # checked, all its entries will already be in our cache, so we
                # won't find the name.
                if passwd_stamp > self.users_lastupdate:
                        self.load_passwd(passwd_file)

                try:
                        return self.uids[uid]
                except:
                        raise KeyError, "getpwuid(): name not found: %d" % uid

        def load_passwd(self, passwd_file):

                self.users.clear()
                self.uids.clear()

                passwd_stamp = os.stat(passwd_file).st_mtime
                f = file(passwd_file)

                for line in f:
                        arr = line.rstrip().split(":")
                        arr[2] = int(arr[2])
                        arr[3] = int(arr[3])
                        pw_entry = pwd.struct_passwd(arr)

                        self.users[pw_entry.pw_name] = pw_entry
                        self.uids[pw_entry.pw_uid] = pw_entry

                self.users_lastupdate = passwd_stamp

                f.close()

        def getgrnam(self, name):
                """Do a name lookup in the image's group database.

                Keep a cached copy in memory for fast lookups, and fall back to
                the current environment if the group database isn't available.
                """

                # XXX What to do about IMG_PARTIAL?
                if self.type == IMG_USER:
                        return grp.getgrnam(name)

                # check if we need to reload cache
                group_file = os.path.join(self.root, "etc/group")

                try:
                        group_stamp = os.stat(group_file).st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        # If the group file doesn't exist, bootstrap ourselves
                        # from the current environment.
                        return grp.getgrnam(name)

                if group_stamp >= self.groups_lastupdate:
                        self.load_groups(group_file)
                try:
                        return self.groups[name]
                except:
                        raise KeyError, "getgrnam(): name not found: %s" % name

        def getgrgid(self, gid):
                """Do a gid lookup in the image's group database.

                Keep a cached copy in memory for fast lookups, and fall back to
                the current environment if the group database isn't available.
                """

                # XXX What to do about IMG_PARTIAL?
                if self.type == IMG_USER:
                        return grp.getgrgid(gid)

                # check if we need to reload cache
                group_file = os.path.join(self.root, "etc/group")

                try:
                        group_stamp = os.stat(group_file).st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        # If the group file doesn't exist, bootstrap ourselves
                        # from the current environment.
                        return grp.getgrgid(gid)

                if group_stamp >= self.groups_lastupdate:
                        self.load_groups(group_file)
                try:
                        return self.gids[gid]
                except:
                        raise KeyError, "getgrgid(): gid not found: %d" % gid

        def load_groups(self, group_file):
                self.groups.clear()
                self.gids.clear()
                group_stamp = os.stat(group_file).st_mtime
                f = file(group_file)
                for line in f:
                        arr = line.rstrip().split(":")
                        arr[2] = int(arr[2])
                        gr_entry = grp.struct_group(arr)

                        self.groups[gr_entry.gr_name] = gr_entry
                        self.gids[gr_entry.gr_gid] = gr_entry

                self.group_lastupdate = group_stamp

                f.close()

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
                                        pkgs_known.extend([ m
                                            for m in self.get_matching_fmris(p)
                                            ])
                                except KeyError:
                                        badpats.append(p)

                        pkgs_known.extend(
                                [ x for x in self.gen_installed_pkgs()
                                for p in patterns
                                if fmri.fmri_match(x.get_pkg_stem(), p)
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
                        return fmri.PkgFmri(urllib.unquote(os.path.dirname(
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
                                        yield k, idx_to_fmri(index)

        def remote_search(self, args, servers = None):
                """Search for the token in args[0] on the servers in 'servers'.
                If 'servers' is empty or None, search on all known servers."""
                failed = []

                if not servers:
                        servers = self.gen_authorities()

                for auth in servers:
                        try:
                                res, v = versioned_urlopen(auth["origin"],
                                    "search", [0], urllib.quote(args[0], ""))
                        except urllib2.HTTPError, e:
                                if e.code != httplib.NOT_FOUND:
                                        failed.append((auth, e))
                                continue
                        except urllib2.URLError, e:
                                failed.append((auth, e))
                                continue

                        for l in res.read().splitlines():
                                yield l.split(" ", 2)[:2]

                if failed:
                        raise RuntimeError, failed

        def get_download_dir(self):
                return os.path.normpath(os.path.join(
                                self.imgdir,
                                "download",
                                str(os.getpid())))

        def cleanup_downloads(self):
                shutil.rmtree(self.get_download_dir(), True)
                              
                    
                    

        def list_install(self, pkg_list, progress, filters = [], verbose = False,
            noexecute = False):
                error = 0
                ip = imageplan.ImagePlan(self, progress, filters = filters)

                for p in pkg_list:
                        try:
                                matches = self.get_matching_fmris(p,
                                    constraint = version.CONSTRAINT_AUTO)
                        except KeyError:
                                # XXX Module directly printing.
                                print _("""\
pkg: no package matching '%s' could be found in current catalog
     suggest relaxing pattern, refreshing and/or examining catalogs""") % p
                                error = 1
                                continue

                        pnames = {}
                        for m in matches:
                                pnames[m.get_pkg_stem()] = 1

                        if len(pnames.keys()) > 1:
                                # XXX Module directly printing.
                                print \
                                    _("pkg: '%s' matches multiple packages") % p
                                for k in pnames.keys():
                                        print "\t%s" % k
                                error = 1
                                continue

                        # matches is a list reverse sorted by version, so take
                        # the first; i.e., the latest.
                        ip.propose_fmri(matches[0])

                if error != 0:
                        raise RuntimeError, "Unable to assemble image plan"

                if verbose:
                        print _("Before evaluation:")
                        print ip

                ip.evaluate()

                if verbose:
                        print _("After evaluation:")
                        print ip

                if not noexecute:
                        ip.execute()

if __name__ == "__main__":
        pass
