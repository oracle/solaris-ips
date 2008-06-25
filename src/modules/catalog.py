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

"""Interfaces and implementation for the Catalog object, as well as functions
that operate on lists of package FMRIs."""

import os
import re
import urllib
import errno
import anydbm as dbm
import signal
import threading
import datetime
import sys
import cPickle

import pkg.fmri as fmri
import pkg.version as version
import pkg.manifest as manifest

class CatalogException(Exception):
        def __init__(self, args=None):
                self.args = args

class RenameException(Exception):
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

        In order to improve the time to search the catalog, a cached list
        of package names is kept in the catalog instance.  In an effort
        to prevent the catalog from having to generate this list every time
        it is constructed, the array that contains the names is pickled and
        saved and pkg_names.pkl.
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

        def __init__(self, cat_root, authority = None, pkg_root = None,
            read_only = False):
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
                self.renamed = None
                self.pkg_names = set()
                self.searchdb_update_handle = None
                self.searchdb = None
                self._search_available = False
                self.deferred_searchdb_updates = []
                # We need to lock the search database against multiple
                # simultaneous updates from separate threads closing
                # publication transactions.
                self.searchdb_lock = threading.Lock()
                self.pkg_root = pkg_root
                self.read_only = read_only
                if self.pkg_root:
                        self.searchdb_file = os.path.dirname(self.pkg_root) + \
                            "/search"

                self.attrs["npkgs"] = 0

                if not os.path.exists(cat_root):
                        os.makedirs(cat_root)

                # Rebuild catalog, if we're the depot and it's necessary
                if pkg_root is not None:
                        self.build_catalog()

                self.load_attrs()
                self.check_prefix()

                if self.pkg_names:
                        return

                # Load the list of pkg names.  If it doesn't exist, build a list
                # of pkg names. If the catalog gets rebuilt in build_catalog,
                # add_fmri() will generate the list of package names instead.
                try:
                        pkg_names = Catalog.load_pkg_names(self.catalog_root)
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                pkg_names = Catalog.build_pkg_names(
                                    self.catalog_root) 
                                if pkg_names and not self.read_only:
                                        Catalog.save_pkg_names(
                                            self.catalog_root,
                                            pkg_names)
                        else:
                                raise

                self.pkg_names = pkg_names



        def add_fmri(self, fmri, critical = False):
                """Add a package, named by the fmri, to the catalog.
                Throws an exception if an identical package is already
                present.  Throws an exception if package has no version."""
                if fmri.version == None:
                        raise CatalogException, \
                            "Unversioned FMRI not supported: %s" % fmri

                # Callers should verify that the FMRI they're going to add is
                # valid; however, this check is here in case they're
                # lackadaisical
                if not self.valid_new_fmri(fmri):
                        raise CatalogException, \
                            "Existing renames make adding FMRI %s invalid." \
                            % fmri

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

                # Add this pkg name to the list of package names
                self.pkg_names.add(fmri.pkg_name)
                Catalog.save_pkg_names(self.catalog_root, self.pkg_names)

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

                for k, v in self.attrs.items():
                        s = "S %s: %s\n" % (k, v)
                        ret.append(s)

                return ret

        @staticmethod
        def _fmri_from_path(pkg, vers):
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
                                    pkg[0], e)).st_mtime

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
                        try:
                                self.searchdb = \
                                    dbm.open(self.searchdb_file, "w")

                                self._search_available = True
                        except dbm.error, e:
                                print >> sys.stderr, \
                                    "Failed to open search database", \
                                    "for writing: %s (errno=%s)" % \
                                    (e.args[1], e.args[0])
                                try:
                                        self.searchdb = \
                                            dbm.open(self.searchdb_file, "r")

                                        self._search_available = True
                                except dbm.error, e:
                                        print >> sys.stderr, \
                                            "Failed to open search " + \
                                            "database: %s (errno=%s)" % \
                                            (e.args[1], e.args[0])
                else:
                        if os.name == 'posix':
                                from pkg.subprocess_method import Mopen, PIPE
                                try: 
                                        signal.signal(signal.SIGCHLD,
                                                self.child_handler)
                                        self.searchdb_update_handle = \
                                            Mopen(self.update_searchdb,
                                                [fmri_list], {}, stderr = PIPE)
                                except ValueError:
                                        # If we are in a subthread already,
                                        # the signal method will not work.
                                        self.update_searchdb(fmri_list)
                        else:
                                # On non-unix, where there is no convenient
                                # way to fork subprocesses, just update the
                                # searchdb inline.
                                self.update_searchdb(fmri_list)

        def child_handler(self, sig, frame):
                """Handler method for the SIGCLD signal.  Checks to see if the
                search database update child has finished, and enables searching
                if it finished successfully, or logs an error if it didn't."""
                if not self.searchdb_update_handle:
                        return

                rc = self.searchdb_update_handle.poll()
                if rc == 0:
                        try:
                                self.searchdb = \
                                    dbm.open(self.searchdb_file, "w")

                                self._search_available = True
                                self.searchdb_update_handle = None
                        except dbm.error, e:
                                print >> sys.stderr, \
                                    "Failed to open search database", \
                                    "for writing: %s (errno=%s)" % \
                                    (e.args[1], e.args[0])
                                try:
                                        self.searchdb = \
                                            dbm.open(self.searchdb_file, "r")

                                        self._search_available = True
                                        self.searchdb_update_handle = None
                                        return
                                except dbm.error, e:
                                        print >> sys.stderr, \
                                            "Failed to open search " + \
                                            "database: %s (errno=%s)" % \
                                            (e.args[1], e.args[0])
                                        return

                        if self.deferred_searchdb_updates:
                                self.update_searchdb(
                                    self.deferred_searchdb_updates)
                elif rc > 0:
                        # XXX This should be logged instead
                        print "ERROR building search database:"
                        print self.searchdb_update_handle.stderr.read()

        def __update_searchdb_unlocked(self, fmri_list):
                if fmri_list:
                        if self.searchdb is None:
                                try:
                                        self.searchdb = \
                                            dbm.open(self.searchdb_file, "c")
                                except dbm.error, e:
                                        # Since we're here explicitly to update
                                        # the database, if we fail, there's
                                        # nothing more to do.
                                        print >> sys.stderr, \
                                            "Failed to open search database", \
                                            "for writing: %s (errno=%s)" % \
                                            (e.args[1], e.args[0])
                                        return 1

                        if not self.searchdb.has_key("indir_num"):
                                self.searchdb["indir_num"] = "0"
                else:
                        try:
                                self.searchdb = \
                                    dbm.open(self.searchdb_file, "n")
                        except dbm.error, e:
                                print >> sys.stderr, \
                                    "Failed to open search database", \
                                    "for writing: %s (errno=%s)" % \
                                    (e.args[1], e.args[0])
                                return 1

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

                try:
                        self.__update_searchdb_unlocked(fmri_list)
                finally:
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
                # self.searchdb: token -> (type, fmri, action name, key value)

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
                                action, keyval = search_dict[tok_type][tok]
                                s = "%s %s %s %s" % \
                                   (tok_type, fmri, action, keyval)
                                s_ptr = self.next_token()
                                try:
                                        self.searchdb[s_ptr] = s
                                except:
                                        print >> sys.stderr, "Couldn't add " \
                                            "'%s' (s_ptr = %s) to search " \
                                            "database" % (s, s_ptr)
                                        continue

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

                tuples = {}
                names_matched = set()

                if self.attrs["npkgs"] == 0:
                        return []

                if matcher is None:
                        matcher = fmri.fmri_match

                if not isinstance(patterns, list):
                        patterns = [ patterns ]

                # 'patterns' may be partially or fully decorated fmris; we want
                # to extract their names and versions to match separately
                # against the catalog.
                #
                # XXX "5.11" here needs to be saner
                for pattern in patterns:
                        if isinstance(pattern, fmri.PkgFmri):
                                tuples[pattern] = pattern.tuple()
                        else:
                                tuples[pattern] = \
                                    fmri.PkgFmri(pattern, "5.11").tuple()

                # Walk list of pkg names and patterns.  See if any of the
                # patterns match known package names
                for p in self.pkg_names:
                        for t in tuples.values():
                                if matcher(p, t[1]):
                                        names_matched.add(p)

                pkgs = self._list_fmris_matched(names_matched)

                ret = extract_matching_fmris(pkgs, patterns, matcher,
                    constraint, counthash)

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
                                if entry[0] not in tuple("CV"):
                                        continue

                                cv, pkg, cat_name, cat_version = entry.split()
                                if pkg == "pkg":
                                        yield fmri.PkgFmri("%s@%s" %
                                            (cat_name, cat_version),
                                            authority = self.auth)
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.  If *this* doesn't work, we
                                # have a corrupt catalog.
                                try:
                                        cv, cat_fmri = entry.split()
                                except ValueError:
                                        raise RuntimeError, \
                                            "corrupt catalog entry for " \
                                            "authority '%s': %s" % \
                                            (self.auth, entry)
                                yield fmri.PkgFmri(cat_fmri,
                                    authority = self.auth)

                pfile.close()

        def fmri_renamed_dest(self, fmri):
                """Returns a list of RenameRecords where fmri is listed as the
                 destination package."""

                # Don't bother doing this if no FMRI is present
                if not fmri:
                        return

                # Load renamed packages, if needed
                if self.renamed is None:
                        self._load_renamed()

                for rr in self.renamed:
                        if rr.destname == fmri.pkg_name and \
                            fmri.version >= rr.destversion:
                                yield rr

        def fmri_renamed_src(self, fmri):
                """Returns a list of RenameRecords where fmri is listed as
                the source package."""

                # Don't bother doing this if no FMRI is present
                if not fmri:
                        return

                # Load renamed packages, if needed
                if self.renamed is None:
                        self._load_renamed()

                for rr in self.renamed:
                        if rr.srcname == fmri.pkg_name and \
                            fmri.version < rr.srcversion:
                                yield rr

        def _list_fmris_matched(self, pkg_names):
                """Given a list of pkg_names, return all of the FMRIs
                that contain an pkg_name entry as a substring."""
                fmris = []

                try:
                        pfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return fmris
                        else:
                                raise

                for entry in pfile:
                        if not entry[1].isspace() or \
                            not entry[0] in known_prefixes:
                                continue

                        try:
                                if entry[0] not in tuple("CV"):
                                        continue

                                cv, pkg, cat_name, cat_version = entry.split()
                                if pkg != "pkg":
                                        continue
                                if cat_name not in pkg_names:
                                        continue
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.  If *this* doesn't work, we
                                # have a corrupt catalog.
                                try:
                                        cv, cat_fmri = entry.split()
                                except ValueError:
                                        raise RuntimeError, \
                                            "corrupt catalog entry for " \
                                            "authority '%s': %s" % \
                                            (self.auth, entry)
                                cat_name = fmri.extract_pkg_name(cat_fmri)
                                if cat_name not in pkg_names:
                                        continue
                                fmris.append(fmri.PkgFmri(cat_fmri, "5.11",
                                        authority = self.auth))
                                continue

                        fmris.append(fmri.PkgFmri("%s@%s" %
                            (cat_name, cat_version), "5.11",
                            authority = self.auth))

                pfile.close()

                return fmris

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

        @staticmethod
        def build_pkg_names(cat_root):
                """Read the catalog and build the array of fmri pkg names
                that is contained within the catalog.  Returns a list
                of strings of package names."""

                pkg_names = set()
                ppath = os.path.normpath(os.path.join(cat_root,
                    "catalog"))

                try:
                        pfile = file(ppath, "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return pkg_names
                        else:
                                raise

                for entry in pfile:
                        try:
                                if entry[0] not in tuple("CV"):
                                        continue

                                cv, pkg, cat_name, cat_version = entry.split()
                                if pkg != "pkg":
                                        continue
                        except ValueError:
                                # Handle old two-column catalog file, mostly in
                                # use on server.  If *this* doesn't work, we
                                # have a corrupt catalog.
                                try:
                                        cv, cat_fmri = entry.split()
                                except ValueError:
                                        raise RuntimeError, \
                                            "corrupt catalog entry in file " \
                                            "'%s': %s" % (ppath, entry)
                                cat_name = fmri.extract_pkg_name(cat_fmri)

                        pkg_names.add(cat_name)

                pfile.close()

                return pkg_names

        @staticmethod
        def save_pkg_names(cat_root, pkg_names):
                """Pickle the list of package names in the catalog for faster
                re-loading."""

                if not pkg_names:
                        return

                ppath = os.path.normpath(os.path.join(cat_root,
                    "pkg_names.pkl"))

                try:
                        pfile = file(ppath, "wb")
                except IOError, e:
                        if e.errno == errno.EACCES:
                                # Don't bother saving, if we don't have
                                # permission.
                                return
                        else:
                                raise

                cPickle.dump(pkg_names, pfile, -1)
                pfile.close()

        @staticmethod
        def load_pkg_names(cat_root):
                """Load pickled list of package names.  This function
                may raise an IOError if the file doesn't exist.  Callers
                should be sure to catch this exception and rebuild
                the package names, if required."""

                ppath = os.path.normpath(os.path.join(cat_root,
                    "pkg_names.pkl"))

                pfile = file(ppath, "rb")
                pkg_names = cPickle.load(pfile) 
                pfile.close()

                return pkg_names

        def _load_renamed(self):
                """Load the catalog's rename records into self.renamed"""

                self.renamed = []

                try:
                        pfile = file(os.path.normpath(
                            os.path.join(self.catalog_root, "catalog")), "r")
                except IOError, e:
                        if e.errno == errno.ENOENT:
                                return
                        else:
                                raise

                self.renamed = [
                    RenamedPackage(*entry.split()[1:]) for entry in pfile
                    if entry[0] == "R"
                ]

                pfile.close()

        def npkgs(self):
                """Returns the number of packages in the catalog."""

                return self.attrs["npkgs"] 

        def origin(self):
                """Returns the URL of the catalog's origin."""

                return self.attrs.get("origin", None)

        @staticmethod
        def recv(filep, path, auth=None):
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
                        elif s.startswith("R "):
                                catf.write(s)
                        else:
                                # XXX Need to be able to handle old and new
                                # format catalogs.
                                f = fmri.PkgFmri(s[2:])
                                catf.write("%s %s %s %s\n" %
                                    (s[0], "pkg", f.pkg_name, f.version))

                # Write the authority's origin into our attributes
                if auth:
                        origstr = "S origin: %s\n" % auth["origin"]
                        attrf.write(origstr)

                attrf.close()
                catf.close()

                # Save a list of package names for easier searching
                pkg_names = Catalog.build_pkg_names(path)
                Catalog.save_pkg_names(path, pkg_names)

        def rename_package(self, srcname, srcvers, destname, destvers):
                """Record that the name of package oldname has been changed
                to newname as of version vers.  Returns a timestamp
                of when the catalog was modified and a RenamedPackage
                object that describes the rename."""

                rr = RenamedPackage(srcname, srcvers, destname, destvers)

                # Check that the destination (new) package is already in the
                # catalog.  Also check that the old package does not exist at
                # the version that is being renamed.
                if rr.new_fmri():
                        newfm = self.get_matching_fmris(rr.new_fmri())
                        if len(newfm) < 1:
                                raise CatalogException, \
                                    "Destination FMRI %s must be in catalog" % \
                                    rr.new_fmri()

                oldfm = self.get_matching_fmris(rr.old_fmri())
                if len(oldfm) > 0:
                        raise CatalogException, \
                            "Src FMRI %s must not be in catalog" % \
                            rr.old_fmri()

                # Load renamed packages, if needed
                if self.renamed is None:
                        self._load_renamed()

                # Check that rename record isn't already in catalog
                if rr in self.renamed:
                        raise CatalogException, \
                            "Rename %s is already in the catalog" % rr

                # Keep renames acyclic.  Check that the destination of this
                # rename isn't the source of another rename.
                if rr.new_fmri() and \
                    self.rename_is_predecessor(rr.new_fmri(), rr.old_fmri()):
                        raise RenameException, \
                            "Can't rename %s. Causes cycle in rename graph." \
                            % rr.srcname

                pathstr = os.path.normpath(os.path.join(self.catalog_root,
                    "catalog"))
                pfile = file(pathstr, "a+")
                pfile.write("%s\n" % rr)
                pfile.close()

                self.renamed.append(rr)

                ts = datetime.datetime.now()
                self.set_time(ts)

                return (ts, rr)

        def rename_is_same_pkg(self, fmri, pfmri):
                """Returns true if fmri and pfmri are the same package because
                of a rename operation."""

                for s in self.fmri_renamed_src(fmri):
                        if s.destname == pfmri.pkg_name:
                                return True
                        elif s.new_fmri() and \
                            self.rename_is_same_pkg(s.new_fmri(), pfmri):
                                return True

                for d in self.fmri_renamed_dest(fmri):
                        if d.srcname == pfmri.pkg_name:
                                return True
                        elif self.rename_is_same_pkg(d.old_fmri(), pfmri):
                                return True

                return False

        def rename_is_successor(self, fmri, pfmri):
                """Returns true if fmri is a successor to pfmri by way
                of a rename operation."""

                for d in self.fmri_renamed_dest(fmri):
                        if d.srcname == pfmri.pkg_name and \
                            pfmri.version <= d.srcversion:
                                return True
                        else:
                                return self.rename_is_successor(d.old_fmri(),
                                    pfmri)

                return False

        def rename_is_predecessor(self, fmri, pfmri):
                """Returns true if fmri is a predecessor to pfmri by
                a rename operation."""

                for s in self.fmri_renamed_src(fmri):
                        if s.destname == pfmri.pkg_name and \
                            s.destversion < pfmri.version:
                                return True
                        elif s.new_fmri():
                                return self.rename_is_predecessor(s.new_fmri(),
                                    pfmri)

                return False

        def rename_newer_pkgs(self, fmri):
                """Returns a list of packages that are newer than fmri."""

                pkgs = []

                for s in self.fmri_renamed_src(fmri):
                        if s.new_fmri():
                                pkgs.append(s.new_fmri())
                                nl = self.rename_newer_pkgs(s.new_fmri())
                                pkgs.extend(nl)

                return pkgs

        def rename_older_pkgs(self, fmri):
                """Returns a list of packages that are older than fmri."""

                pkgs = []

                for d in self.fmri_renamed_dest(fmri):
                        pkgs.append(d.old_fmri())
                        ol = self.rename_older_pkgs(d.old_fmri())
                        pkgs.extend(ol) 

                return pkgs

        def save_attrs(self, filenm = "attrs"):
                """Save attributes from the in-memory catalog to a file
                specified by filenm."""

                try:
                        afile = file(os.path.normpath(
                            os.path.join(self.catalog_root, filenm)), "w+")
                except IOError, e:
                        # This may get called in a situation where
                        # the user does not have write access to the attrs
                        # file.
                        if e.errno == errno.EACCES:
                                return
                        else:
                                raise

                for a in self.attrs.keys():
                        s = "S %s: %s\n" % (a, self.attrs[a])
                        afile.write(s)

                afile.close()

        def send(self, filep):
                """Send the contents of this catalog out to the filep
                specified as an argument."""

                def output():
                        # Send attributes first.
                        for line in self.attrs_as_lines():
                                yield line

                        try:
                                cfile = file(os.path.normpath(
                                    os.path.join(self.catalog_root, "catalog")),
                                    "r")
                        except IOError, e:
                                # Missing catalog is fine; other errors need to
                                # be reported.
                                if e.errno == errno.ENOENT:
                                        return
                                else:
                                        raise

                        for e in cfile:
                                yield e

                        cfile.close()

                if filep:
                        for line in output():
                                filep.write(line)
                else:
                        return output()

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

        def valid_new_fmri(self, fmri):
                """Check that the fmri supplied as an argument would be
                valid to add to the catalog.  This checks to make sure that
                rename/freeze operations would not prohibit the caller
                from adding this FMRI."""

                if self.renamed is None:
                        self._load_renamed()

                for rr in self.renamed:
                        if rr.srcname == fmri.pkg_name and \
                            fmri.version >= rr.srcversion:
                                return False

                return True


# In order to avoid a fine from the Department of Redundancy Department,
# allow these methods to be invoked without explictly naming the Catalog class.
recv = Catalog.recv

# Prefixes that this catalog knows how to handle
known_prefixes = frozenset("CSVR")

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
        minutes = int(ts[14:16])
        sec = int(ts[17:19])
        # usec is not in the string if 0
        try:
                usec = int(ts[20:26])
        except ValueError:
                usec = 0

        dt = datetime.datetime(year, month, day, hour, minutes, sec, usec)

        return dt


def extract_matching_fmris(pkgs, patterns, matcher = None,
    constraint = None, counthash = None):
        """Iterate through the given list of PkgFmri objects,
        looking for packages matching 'pattern', based on the function
        in 'matcher' and the versioning constraint described by
        'constraint'.  If 'matcher' is None, uses fmri subset matching
        as the default.  Returns a sorted list of PkgFmri objects,
        newest versions first.  If 'counthash' is a dictionary, instead
        store the number of matched fmris for each package name which
        was matched."""

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
                        assert pattern != None
                        tuples[pattern] = \
                            fmri.PkgFmri(pattern, "5.11").tuple()

        ret = []

        for p in pkgs:
                cat_auth, cat_name, cat_version = p.tuple()

                for pattern in patterns:
                        pat_auth, pat_name, pat_version = tuples[pattern]
                        if (fmri.is_same_authority(pat_auth, cat_auth) or not \
                            pat_auth) and matcher(cat_name, pat_name):
                                if not pat_version or \
                                    p.version.is_successor(
                                    pat_version, constraint) or \
                                    p.version == pat_version:
                                        if counthash is not None:
                                                if pattern in counthash:
                                                        counthash[pattern] += 1
                                                else:
                                                        counthash[pattern] = 1

                                        if pat_auth:
                                                p.set_authority(pat_auth)
                                        ret.append(p)

        return sorted(ret, reverse = True)

class RenamedPackage(object):
        """An in-memory representation of a rename object.  This object records
        information about a package that has had its name changed.

        Renaming a package presents a number of challenges.  The packaging
        system must still be able to recognize and decode dependencies on
        packages with the old name.  In order for this to work correctly, the
        rename record must contain both the old and new name of the package.  It
        is also undesireable to have a renamed package receive subsequent
        versions.  However, it still should be possible to publish bugfixes to
        the old package lineage.  This means that we must also record
        versioning information at the time a package is renamed.

        This versioning information allows us to determine which portions
        of the version and namespace are allowed to add new versions.

        If a package is re-named to the NULL package at a specific version,
        this is equivalent to freezing the package.  No further updates to
        the version history may be made under that name. (NULL is never open)

        The rename catalog format is as follows:

        R <srcname> <srcversion> <destname> <destversion>
        """

        def __init__(self, srcname, srcversion, destname, destversion):
                """Create a RenamedPackage object.  Srcname is the original
                name of the package, destname is the name this package
                will take after the operation is successful.


                Versionstr is the version at which this change takes place.  No
                versions >= version of srcname will be permitted."""

                if destname == "NULL":
                        self.destname = None
                        destversion = None
                else:
                        self.destname = destname

                self.srcname = srcname

                if not srcversion and not destversion:
                        raise RenameException, \
                            "Must supply a source or destination version"
                elif not srcversion:
                        self.srcversion = version.Version(destversion, None)
                        self.destversion = self.srcversion
                elif not destversion:
                        self.srcversion = version.Version(srcversion, None)
                        self.destversion = self.srcversion
                else:
                        self.destversion = version.Version(destversion, None)
                        self.srcversion = version.Version(srcversion, None)

        def __str__(self):
                if not self.destname:
                        return "R %s %s NULL NULL" % (self.srcname,
                            self.srcversion)

                return "R %s %s %s %s" % (self.srcname, self.srcversion,
                    self.destname, self.destversion)

        def __eq__(self, other):
                """Implementing our own == function allows us to properly
                check whether a rename object is in a list of renamed
                objects."""

                if not isinstance(other, RenamedPackage):
                        return False

                if self.srcname != other.srcname:
                        return False

                if self.destname != other.destname:
                        return False

                if self.srcversion != other.srcversion:
                        return False

                if self.destversion != other.destversion:
                        return False

                return True

        def new_fmri(self):
                """Return a FMRI that represents the destination name and
                version of the renamed package."""

                if not self.destname:
                        return None

                fmstr = "pkg:/%s@%s" % (self.destname, self.destversion)

                fm = fmri.PkgFmri(fmstr, None)

                return fm

        def old_fmri(self):
                """Return a FMRI that represents the most recent version
                of the package had it not been renamed."""

                fmstr = "pkg:/%s@%s" % (self.srcname, self.srcversion)

                fm = fmri.PkgFmri(fmstr, None)

                return fm
