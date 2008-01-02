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
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import re
import sha
import shutil
import time
import urllib
import tempfile
import errno
import dbm
import signal
import threading
import datetime

import pkg.fmri as fmri
import pkg.version as version
import pkg.manifest as manifest
from pkg.subprocess_method import Mopen, PIPE

class CatalogException(Exception):
        def __init__(self, args=None):
                self.args = args

class Catalog(object):
        """A Catalog is the representation of the package FMRIs available to
        this client or repository.  Both purposes utilize the same storage
        format.

        The serialized structure of the repository is an unordered list of
        available package versions, followed by an unordered list of
        incorporation relationships between packages.  This latter section
        allows the graph to be topologically sorted by the client.

        S Last-Modified: [timespec]

        XXX A authority mirror-uri ...
        XXX ...

        V fmri
        V fmri
        ...
        C fmri
        C fmri
        ...
        I fmri fmri
        I fmri fmri
        ...
        """

        # XXX Mirroring records also need to be allowed from client
        # configuration, and not just catalogs.
        #
        # XXX It would be nice to include available tags and package sizes,
        # although this could also be calculated from the set of manifests.
        #
        # XXX Current code is O(N_packages) O(M_versions), should be
        # O(1) O(M_versions), and possibly O(1) O(1).
        #
        # XXX Initial estimates suggest that the Catalog could be composed of
        # 1e5 - 1e7 lines.  Catalogs across these magnitudes will need to be
        # spread out into chunks, and may require a delta-oriented update
        # interface.

        def __init__(self, cat_root, authority = None, pkg_root = None):
                """Create a catalog.  If the path supplied does not exist,
                this will create the required directory structure.
                Otherwise, if the directories are already in place, the
                existing catalog is opened.  If pkg_root is specified
                and no catalog is found at cat_root, the catalog will be
                rebuilt.  authority names the authority that
                is represented by this catalog."""

                self.catalog_root = cat_root
                self.attrs = {}
                self.auth = authority
                self.searchdb_update_handle = None
                self.searchdb = None
                self._search_available = False
                self.deferred_searchdb_updates = []
                # We need to lock the search database against multiple
                # simultaneous updates from separate threads closing
                # publication transactions.
                self.searchdb_lock = threading.Lock()
                self.pkg_root = pkg_root
                if self.pkg_root:
                        self.searchdb_file = os.path.dirname(self.pkg_root) + \
                            "/search"

                self.attrs["npkgs"] = 0

                if not os.path.exists(cat_root):
                        os.makedirs(cat_root) 

                catpath = os.path.normpath(os.path.join(cat_root, "catalog"))

                if pkg_root is not None:
                        self.build_catalog()

                self.load_attrs()
                self.check_prefix()

        def add_fmri(self, fmri, critical = False):
                """Add a package, named by the fmri, to the catalog.
                Throws an exception if an identical package is already
                present.  Throws an exception if package has no version."""
                if fmri.version == None:
                        raise CatalogException, \
                            "Unversioned FMRI not supported: %s" % fmri

                if critical:
                        pkgstr = "C %s\n" % fmri.get_fmri(anarchy = True)
                else:
                        pkgstr = "V %s\n" % fmri.get_fmri(anarchy = True)

                pathstr = os.path.normpath(os.path.join(self.catalog_root,
                    "catalog"))

                pfile = file(pathstr, "a+")
                pfile.seek(0)

                for entry in pfile:
                        if entry == pkgstr:
                                pfile.close()
                                raise CatalogException, \
                                    "Package %s is already in the catalog" % \
                                    fmri

                pfile.write(pkgstr)
                pfile.close()

                self.attrs["npkgs"] += 1

                ts = datetime.datetime.now()
                self.set_time(ts)

                return ts

        def added_prefix(self, p):
                """Perform any catalog transformations necessary if
                prefix p is found in the catalog.  Previously, we didn't
                know how to handle this prefix and now we do.  If we
                need to transform the entry from server to client form,
                make sure that happens here."""

                # Nothing to do now.
                pass

        def attrs_as_lines(self):
                """Takes the list of in-memory attributes and returns
                a list of strings, each string naming an attribute."""

                ret = []

                for k,v in self.attrs.items():
                        s = "S %s: %s\n" % (k, v)
                        ret.append(s)

                return ret

        def _fmri_from_path(self, pkg, vers):
                """Helper method that takes the full path to the package
                directory and the name of the manifest file, and returns an FMRI
                constructed from the information in those components."""

                v = version.Version(urllib.unquote(vers), None)
                f = fmri.PkgFmri(urllib.unquote(os.path.basename(pkg)), None)
                f.version = v
                return f

        def check_prefix(self):
                """If this version of the catalog knows about new prefixes,
                check the on disk catalog to see if we can perform any
                transformations based upon previously unknown catalog formats.

                This routine will add a catalog attribute if it doesn't exist,
                otherwise it checks this attribute against a hard-coded
                version-specific tuple to see if new methods were added.

                If new methods were added, it will call an additional routine
                that updates the on-disk catalog, if necessary."""


                # If a prefixes attribute doesn't exist, write one and get on
                # with it.
                if not "prefix" in self.attrs:
                        self.attrs["prefix"] = "".join(known_prefixes)
                        self.save_attrs()
                        return

                # Prefixes attribute does exist.  Check if it has changed.
                pfx_set = set(self.attrs["prefix"])

                # Nothing to do if prefixes haven't changed
                if pfx_set == known_prefixes:
                        return

                # If known_prefixes contains a prefix not in pfx_set,
                # add the prefix and perform a catalog transform.
                new = known_prefixes.difference(pfx_set)
                if new:
                        for p in new:
                                self.added_prefix(p)

                        pfx_set.update(new)

                        # Write out updated prefixes list
                        self.attrs["prefix"] = "".join(pfx_set)
                        self.save_attrs()

        def build_catalog(self):
                """Walk the on-disk package data and build (or rebuild) the
                package catalog and search database."""
                try:
                        idx_mtime = \
                            os.stat(self.searchdb_file + ".pag").st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        idx_mtime = 0

                try:
                        cat_mtime = os.stat(os.path.join(
                            self.catalog_root, "catalog")).st_mtime
                except OSError, e:
                        if e.errno != errno.ENOENT:
                                raise
                        cat_mtime = 0

                fmri_list = []

                # XXX eschew os.walk in favor of another os.listdir here?
                tree = os.walk(self.pkg_root)
                for pkg in tree:
                        if pkg[0] == self.pkg_root:
                                continue

                        for e in os.listdir(pkg[0]):
                                ver_mtime = os.stat(os.path.join(
                                    self.pkg_root, pkg[0], e)).st_mtime

                                # XXX force a rebuild despite mtimes?
                                # XXX queue this and fork later?
                                if ver_mtime > cat_mtime:
                                        f = self._fmri_from_path(pkg[0], e)

                                        self.add_fmri(f)
                                        print f

                                # XXX force a rebuild despite mtimes?
                                # If the database doesn't exist, don't bother
                                # building the list; we'll just build it all.
                                if ver_mtime > idx_mtime > 0:
                                        fmri_list.append((pkg[0], e))

                # If we have no updates to make to the search database but it
                # already exists, just make it available.  If we do have updates
                # to make (including possibly building it from scratch), fork it
                # off into another process; when that's done, we'll mark it
                # available.
                if not fmri_list and idx_mtime > 0:
                        self.searchdb = dbm.open(self.searchdb_file, "w")
                        self._search_available = True
                else:
                        signal.signal(signal.SIGCHLD, self.child_handler)
                        self.searchdb_update_handle = \
                            Mopen(self.update_searchdb, [fmri_list], {},
                                stderr = PIPE)

        def child_handler(self, sig, frame):
                """Handler method for the SIGCLD signal.  Checks to see if the
                search database update child has finished, and enables searching
                if it finished successfully, or logs an error if it didn't."""
                if not self.searchdb_update_handle:
                        return

                rc = self.searchdb_update_handle.poll()
                if rc == 0:
                        self.searchdb = dbm.open(self.searchdb_file, "w")
                        self._search_available = True
                        self.searchdb_update_handle = None
                        if self.deferred_searchdb_updates:
                                self.update_searchdb(
                                    self.deferred_searchdb_updates)
                elif rc > 0:
                        # XXX This should be logged instead
                        print "ERROR building search database:"
                        print self.searchdb_update_handle.stderr.read()

        def update_searchdb(self, fmri_list):
                """Update the search database with the FMRIs passed in via
                'fmri_list'.  If 'fmri_list' is empty or None, then rebuild the
                database from scratch.  'fmri_list' should be a list of tuples
                where the first element is the full path to the package name in
                pkg_root and the second element is the version string."""

                # If we're in the process of updating the database in our
                # separate process, and this particular update until that's
                # done.
                if self.searchdb_update_handle:
                        self.deferred_searchdb_updates += fmri_list
                        return

                self.searchdb_lock.acquire()

                new = False
                if fmri_list:
                        if not self.searchdb:
                                self.searchdb = \
                                    dbm.open(self.searchdb_file, "c")

                        if not self.searchdb.has_key("indir_num"):
                                self.searchdb["indir_num"] = "0"
                else:
                        # new = True
                        self.searchdb = dbm.open(self.searchdb_file, "n")
                        self.searchdb["indir_num"] = "0"
                        # XXX We should probably iterate over the catalog, for
                        # cases where manifests have stuck around, but have been
                        # moved to historical and removed from the catalog.
                        fmri_list = (
                            (os.path.join(self.pkg_root, pkg), ver)
                            for pkg in os.listdir(self.pkg_root)
                            for ver in os.listdir(
                                os.path.join(self.pkg_root, pkg))
                        )

                for pkg, vers in fmri_list:
                        mfst_path = os.path.join(pkg, vers)
                        mfst = manifest.Manifest()
                        mfst_file = file(mfst_path)
                        mfst.set_content(mfst_file.read())
                        mfst_file.close()

                        f = self._fmri_from_path(pkg, vers)

                        self.update_index(f, mfst.search_dict())

                self.searchdb_lock.release()

                # If we rebuilt the database from scratch ... XXX why would we
                # want to do this?
                # if new:
                #         self.searchdb.close()
                #         self.searchdb = None
                self._search_available = True

        # Five digits of a base-62 number represents a little over 900 million.
        # Assuming 1 million tokens used in a WOS build (current imports use
        # just short of 500k, but we don't have all the l10n packages, and may
        # not have all the search tokens we want) and keeping every nightly
        # build gives us 2.5 years before we run out of token space.  We're
        # likely to garbage collect manifests and rebuild the db before then.
        #
        # XXX We're eventually going to run into conflicts with real tokens
        # here.  This is unlikely until we hit, say "alias", which is a ways
        # off, but we should still look at solving this.
        idx_tok_len = 5

        def next_token(self):
                alphabet = "abcdefghijklmnopqrstuvwxyz"
                k = "0123456789" + alphabet + alphabet.upper()

                num = int(self.searchdb["indir_num"])

                s = ""
                for i in range(1, self.idx_tok_len + 1):
                        junk, tail = divmod(num, 62 ** i)
                        idx, junk = divmod(tail, 62 ** (i - 1))
                        s = k[idx] + s

                # XXX Do we want to log warnings as we approach index capacity?
                self.searchdb["indir_num"] = \
                    str(int(self.searchdb["indir_num"]) + 1)

                return s

        def update_index(self, fmri, search_dict):
                """Update the search database with the data from the manifest
                for 'fmri', which has been collected into 'search_dict'"""
                # self.searchdb: token -> (type, fmri, action)
                # XXX search_dict doesn't have action info, but should

                # Don't update the database if it already has this FMRI's
                # indices.
                if self.searchdb.has_key(str(fmri)):
                        return

                self.searchdb[str(fmri)] = "True"
                for tok_type in search_dict.keys():
                        for tok in search_dict[tok_type]:
                                # XXX The database files are so damned huge (if
                                # holey) because we have zillions of copies of
                                # the full fmri strings.  We might want to
                                # indirect these as well.
                                s = "%s %s" % (tok_type, fmri)
                                s_ptr = self.next_token()
                                self.searchdb[s_ptr] = s

                                self.update_chain(tok, s_ptr)

        def update_chain(self, token, data_token):
                """Because of the size limitations of the underlying database
                records, not only do we have to store pointers to the actual
                search data, but once the pointer records fill up, we have to
                chain those records up to spillover records.  This method adds
                the pointer to the data to the end of the last link in the
                chain, overflowing as necessary.  The search token is passed in
                as 'token', and the pointer to the actual data which should be
                returned is passed in as 'data_token'."""

                while True:
                        try:
                                cur = self.searchdb[token]
                        except KeyError:
                                cur = ""
                        l = len(cur)

                        # According to the ndbm man page, the total length of
                        # key and value must be less than 1024.  Seems like the
                        # actual value is 1018, probably due to some padding or
                        # accounting bytes or something.  The 2 is for the space
                        # separator and the plus-sign for the extension token.
                        # XXX The comparison should be against 1017, but that
                        # crahes in the if clause below trying to append the
                        # extension token.  Dunno why.
                        if len(token) + l + self.idx_tok_len + 2 > 1000:
                                # If we're adding the first element in the next
                                # link of the chain, add the extension token to
                                # the end of this link, and put the token
                                # pointing to the data at the beginning of the
                                # next link.
                                if cur[-(self.idx_tok_len + 1)] != "+":
                                        nindir_tok = "+" + self.next_token()
                                        self.searchdb[token] += " " + nindir_tok
                                        self.searchdb[nindir_tok] = data_token
                                        break # from while True; we're done
                                # If we find an extension token, start looking
                                # at the next chain link.
                                else:
                                        token = cur[-(self.idx_tok_len + 1):]
                                        continue

                        # If we get here, it's safe to append the data token to
                        # the current link, and get out.
                        if cur:
                                self.searchdb[token] += " " + data_token
                        else:
                                self.searchdb[token] = data_token
                        break

        def search(self, token):
                """Search through the search database for 'token'.  Return a
                list of token type / fmri pairs."""
                ret = []

                while True:
                        # For each indirect token in the search token's value,
                        # add its value to the return list.  If we see a chain
                        # token, switch to its value and continue.  If we fall
                        # out of the loop without seeing a chain token, we can
                        # return.
                        for tok in self.searchdb[token].split():
                                if tok[0] == "+":
                                        token = tok
                                        break
                                else:
                                        ret.append(
                                            self.searchdb[tok].split(" ", 1))
                        else:
                                return ret

        def get_matching_fmris(self, patterns, matcher = None,
            constraint = None, counthash = None):
                """Iterate through the catalog, looking for packages matching
                'pattern', based on the function in 'matcher' and the versioning
                constraint described by 'constraint'.  If 'matcher' is None,
                uses fmri subset matching as the default.  Returns a sorted list
                of PkgFmri objects, newest versions first.  If 'counthash' is a
                dictionary, instead store the number of matched fmris for each
                package name which was matched."""

                cat_auth = self.auth

                if not matcher:
                        matcher = fmri.fmri_match

                if not isinstance(patterns, list):
                        patterns = [ patterns ]

                # 'pattern' may be a partially or fully decorated fmri; we want
                # to extract its name and version to match separately against
                # the catalog.
                # XXX "5.11" here needs to be saner
                tuples = {}

                for pattern in patterns:
                        if isinstance(pattern, fmri.PkgFmri):
                                tuples[pattern] = pattern.tuple()
                        else:
                                tuples[pattern] = \
                                    fmri.PkgFmri(pattern, "5.11").tuple()

                ret = []

                try:
                        pfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return ret
                        else:
                                raise

                for entry in pfile:
                        if not entry[1].isspace() or \
                            not entry[0] in known_prefixes:
                                continue

                        try:
                                cv, pkg, cat_name, cat_version = entry.split()
                                if cv not in tuple("CV") or pkg != "pkg":
                                        continue
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.
                                cv, cat_fmri = entry.split()
                                pkg = "pkg"
                                cat_auth, cat_name, cat_version = \
                                    fmri.PkgFmri(cat_fmri, "5.11",
                                        authority = self.auth).tuple()

                        for pattern in patterns:
                                pat_auth, pat_name, pat_version = tuples[pattern]
                                if pkg == "pkg" and \
                                    (pat_auth == cat_auth or not pat_auth) and \
                                    matcher(cat_name, pat_name):
                                        pkgfmri = fmri.PkgFmri("%s@%s" %
                                            (cat_name, cat_version),
                                            authority = cat_auth)
                                        if not pat_version or \
                                            pkgfmri.version.is_successor(
                                            pat_version, constraint) or \
                                            pkgfmri.version == pat_version:
                                                    if counthash is not None:
                                                            if pattern in counthash:
                                                                    counthash[pattern] += 1
                                                            else:
                                                                    counthash[pattern] = 1
                                                    ret.append(pkgfmri)

                pfile.close()

                return sorted(ret, reverse = True)

        def fmris(self):
                """A generator function that produces FMRIs as it
                iterates over the contents of the catalog."""

                try:
                        pfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return
                        else:
                                raise

                for entry in pfile:
                        if not entry[1].isspace() or \
                            not entry[0] in known_prefixes:
                                continue

                        try:
                                cv, pkg, cat_name, cat_version = entry.split()
                                if cv in tuple("CV") and pkg == "pkg":
                                        yield fmri.PkgFmri("%s@%s" %
                                            (cat_name, cat_version),
                                            authority = self.auth)
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.
                                cv, cat_fmri = entry.split()
                                if cv in tuple("CV"):
                                        yield fmri.PkgFmri(cat_fmri,
                                            authority = self.auth)

                pfile.close()

        def last_modified(self):
                """Return the time at which the catalog was last modified."""

                return self.attrs.get("Last-Modified", None)

        def load_attrs(self, filenm = "attrs"):
                """Load attributes from the catalog file into the in-memory
                attributes dictionary"""

                apath = os.path.normpath(
                    os.path.join(self.catalog_root, filenm))
                if not os.path.exists(apath):
                        return

                afile = file(apath, "r")
                attrre = re.compile('^S ([^:]*): (.*)')

                for entry in afile:
                        m = attrre.match(entry)
                        if m != None:
                                self.attrs[m.group(1)] = m.group(2)

                afile.close()

                # convert npkgs to integer value
                if "npkgs" in self.attrs:
                        self.attrs["npkgs"] = int(self.attrs["npkgs"])

        def npkgs(self):
                """Returns the number of packages in the catalog."""

                return self.attrs["npkgs"] 

        @staticmethod
        def recv(filep, path):
                """A static method that takes a file-like object and
                a path.  This is the other half of catalog.send().  It
                reads a stream as an incoming catalog and lays it down
                on disk."""

                if not os.path.exists(path):
                        os.makedirs(path)

                attrf = file(os.path.normpath(
                    os.path.join(path, "attrs")), "w+")
                catf = file(os.path.normpath(
                    os.path.join(path, "catalog")), "w+")

                for s in filep:
                        if not s[1].isspace():
                                continue
                        elif not s[0] in known_prefixes:
                                catf.write(s)
                        elif s.startswith("S "):
                                attrf.write(s)
                        else:
                                # XXX Need to be able to handle old and new
                                # format catalogs.
                                f = fmri.PkgFmri(s[2:])
                                catf.write("%s %s %s %s\n" %
                                    (s[0], "pkg", f.pkg_name, f.version))

                attrf.close()
                catf.close()

        def save_attrs(self, filenm = "attrs"):
                """Save attributes from the in-memory catalog to a file
                specified by filenm."""

                afile = file(os.path.normpath(
                    os.path.join(self.catalog_root, filenm)), "w+")
                for a in self.attrs.keys():
                        s = "S %s: %s\n" % (a, self.attrs[a])
                        afile.write(s)

                afile.close()

        def send(self, filep):
                """Send the contents of this catalog out to the filep
                specified as an argument."""

                # Send attributes first.
                filep.writelines(self.attrs_as_lines())

                try:
                        cfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        # Missing catalog is fine; other errors need to be
                        # reported.
                        if e.errno == errno.ENOENT:
                                return
                        else:
                                raise

                for e in cfile:
                        filep.write(e)

                cfile.close()

        def set_time(self, ts = None):
                """Set time to timestamp if supplied by caller.  Otherwise
                use the system time."""

                if ts and isinstance(ts, str):
                        self.attrs["Last-Modified"] = ts
                elif ts and isinstance(ts, datetime.datetime):
                        self.attrs["Last-Modified"] = ts.isoformat()
                else:
                        self.attrs["Last-Modified"] = timestamp()

                self.save_attrs()

        def search_available(self):
                return self._search_available


# In order to avoid a fine from the Department of Redundancy Department,
# allow these methods to be invoked without explictly naming the Catalog class.
recv = Catalog.recv

# Prefixes that this catalog knows how to handle
known_prefixes = frozenset("CSV")

# Method used by Catalog and UpdateLog.  Since UpdateLog needs to know
# about Catalog, keep it in Catalog to avoid circular dependency problems.
def timestamp():
        """Return an integer timestamp that can be used for comparisons."""

        tobj = datetime.datetime.now()                
        tstr = tobj.isoformat()

        return tstr

def ts_to_datetime(ts):
        """Take timestamp ts in string isoformat, and convert it to a datetime
        object."""

        year = int(ts[0:4])
        month = int(ts[5:7])
        day = int(ts[8:10])
        hour = int(ts[11:13])
        min = int(ts[14:16])
        sec = int(ts[17:19])
        usec = int(ts[20:26])

        dt = datetime.datetime(year, month, day, hour, min, sec, usec)

        return dt

