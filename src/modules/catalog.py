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
# Copyright (c) 2007, 2011, Oracle and/or its affiliates. All rights reserved.

"""Interfaces and implementation for the Catalog object, as well as functions
that operate on lists of package FMRIs."""

import copy
import calendar
import collections
import datetime
import errno
import fnmatch
import hashlib
import os
import simplejson as json
import stat
import statvfs
import threading

import pkg.actions
import pkg.client.api_errors as api_errors
import pkg.fmri as fmri
import pkg.misc as misc
import pkg.portable as portable
import pkg.version

from operator import itemgetter
from pkg.misc import EmptyDict, EmptyI

class _JSONWriter(object):
        """Private helper class used to serialize catalog data and generate
        signatures."""

        def __init__(self, data, single_pass=False, pathname=None, sign=True):
                self.__data = data
                self.__fileobj = None

                # Determines whether data is encoded in a single pass (uses
                # more memory) or iteratively.
                self.__single_pass = single_pass

                # Default to a 32K buffer.
                self.__bufsz = 32 * 1024 

                if sign:
                        if not pathname:
                                # Only needed if not writing to __fileobj.
                                self.__sha_1 = hashlib.sha1()
                        self.__sha_1_value = None

                self.__sign = sign
                self.pathname = pathname

                if not pathname:
                        return

                # Call statvfs to find optimal blocksize for destination.
                dest_dir = os.path.dirname(self.pathname)
                try:
                        destvfs = os.statvfs(dest_dir)
                        # Set the file buffer size to the blocksize of our
                        # filesystem.
                        self.__bufsz = destvfs[statvfs.F_BSIZE]
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                except AttributeError, e:
                        # os.statvfs is not available on some platforms.
                        pass

                try:
                        tfile = open(pathname, "wb", self.__bufsz)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise
                self.__fileobj = tfile

        def signatures(self):
                """Returns a dictionary mapping digest algorithms to the
                hex-encoded digest values of the text of the catalog."""

                if not self.__sign:
                        return {}
                return { "sha-1": self.__sha_1_value }

        def _dump(self, obj, fp, skipkeys=False, ensure_ascii=True,
            check_circular=True, allow_nan=True, cls=json.JSONEncoder,
            indent=None, separators=None, encoding='utf-8', default=None, **kw):
                iterable = cls(skipkeys=skipkeys, ensure_ascii=ensure_ascii,
                    check_circular=check_circular, allow_nan=allow_nan,
                    indent=indent, separators=separators, encoding=encoding,
                    default=default, **kw).iterencode(obj,
                    _one_shot=self.__single_pass)
                fp.writelines(iterable)

        def save(self):
                """Serializes and stores the provided data in JSON format."""

                # sort_keys is necessary to ensure consistent signature
                # generation.  It has a minimal performance cost as well (on
                # on SPARC and x86), so shouldn't be an issue.  However, it
                # is only needed if the caller has indicated that the content
                # should be signed.

                # Whenever possible, avoid using the write wrapper (self) as
                # this can greatly increase write times.
                out = self.__fileobj
                if not out:
                        out = self

                self._dump(self.__data, out, check_circular=False,
                    separators=(",", ":"), sort_keys=self.__sign)
                out.write("\n")

                if self.__fileobj:
                        self.__fileobj.close()

                if not self.__sign or not self.__fileobj:
                        # Can't sign unless a file object is provided.  And if
                        # one is provided, but no signing is to be done, then
                        # ensure the fileobject is discarded.
                        self.__fileobj = None
                        if self.__sign:
                                self.__sha_1_value = self.__sha_1.hexdigest()
                        return

                # Ensure file object goes out of scope.
                self.__fileobj = None

                # Calculating sha-1 this way is much faster than intercepting
                # write calls because of the excessive number of write calls
                # that json.dump() triggers (1M+ for /dev catalog files).
                self.__sha_1_value = misc.get_data_digest(self.pathname)[0]

                # Open the JSON file so that the signature data can be added.
                sfile = file(self.pathname, "rb+", self.__bufsz)

                # The last bytes should be "}\n", which is where the signature
                # data structure needs to be appended.
                sfile.seek(-2, os.SEEK_END)

                # Add the signature data and close.
                sfoffset = sfile.tell()
                if sfoffset > 1:
                        # Catalog is not empty, so a separator is needed.
                        sfile.write(",")
                sfile.write('"_SIGNATURE":')
                self._dump(self.signatures(), sfile, check_circular=False,
                    separators=(",", ":"))
                sfile.write("}\n")
                sfile.close()

        def write(self, data):
                """Wrapper function that should not be called by external
                consumers."""

                if self.__sign:
                        self.__sha_1.update(data)

        def writelines(self, iterable):
                """Wrapper function that should not be called by external
                consumers."""

                for l in iterable:
                        self.__sha_1.update(l)


class CatalogPartBase(object):
        """A CatalogPartBase object is an abstract class containing core
        functionality shared between CatalogPart and CatalogAttrs."""

        # The file mode to be used for all catalog files.
        __file_mode = stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH

        __meta_root = None
        last_modified = None
        loaded = False
        name = None
        sign = True
        signatures = None

        def __init__(self, name, meta_root=None, sign=True):
                """Initializes a CatalogPartBase object."""

                self.meta_root = meta_root
                self.name = name
                self.sign = sign
                self.signatures = {}

                if not self.meta_root or not self.exists:
                        # Operations shouldn't attempt to load the part data
                        # unless meta_root is defined and the data exists.
                        self.loaded = True
                        self.last_modified = datetime.datetime.utcnow()
                else:
                        self.last_modified = self.__last_modified()

        @staticmethod
        def _gen_signatures(data):
                f = _JSONWriter(data)
                f.save()
                return f.signatures()

        def __get_meta_root(self):
                return self.__meta_root

        def __last_modified(self):
                """A UTC datetime object representing the time the file used to
                to store object metadata was modified, or None if it does not
                exist yet."""

                if not self.exists:
                        return None

                try:
                        mod_time = os.stat(self.pathname).st_mtime
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                return None
                        raise
                return datetime.datetime.utcfromtimestamp(mod_time)

        def __set_meta_root(self, path):
                if path:
                        path = os.path.abspath(path)
                self.__meta_root = path

        def destroy(self):
                """Removes any on-disk files that exist for the catalog part and
                discards all content."""

                if self.pathname:
                        if os.path.exists(self.pathname):
                                try:
                                        portable.remove(self.pathname)
                                except EnvironmentError, e:
                                        if e.errno == errno.EACCES:
                                                raise api_errors.PermissionsException(
                                                    e.filename)
                                        if e.errno == errno.EROFS:
                                                raise api_errors.ReadOnlyFileSystemException(
                                                    e.filename)
                                        raise
                self.signatures = {}
                self.loaded = False
                self.last_modified = None

        @property
        def exists(self):
                """A boolean value indicating wheher a file for the catalog part
                exists at <self.meta_root>/<self.name>."""

                if not self.pathname:
                        return False
                return os.path.exists(self.pathname)

        def load(self):
                """Load the serialized data for the catalog part and return the
                resulting structure."""

                location = os.path.join(self.meta_root, self.name)

                try:
                        fobj = file(location, "rb")
                except EnvironmentError, e:
                        if e.errno == errno.ENOENT:
                                raise api_errors.RetrievalError(e,
                                    location=location)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        raise

                try:
                        struct = json.load(fobj)
                except EnvironmentError, e:
                        raise api_errors.RetrievalError(e)
                except ValueError, e:
                        # Not a valid catalog file.
                        raise api_errors.InvalidCatalogFile(location)

                self.loaded = True
                # Signature data, if present, should be removed from the struct
                # on load and then stored in the signatures object property.
                self.signatures = struct.pop("_SIGNATURE", {})
                return struct

        @property
        def pathname(self):
                """The absolute path of the file used to store the data for
                this part or None if meta_root or name is not set."""

                if not self.meta_root or not self.name:
                        return None
                return os.path.join(self.meta_root, self.name)

        def save(self, data, single_pass=False):
                """Serialize and store the transformed catalog part's 'data' in
                a file using the pathname <self.meta_root>/<self.name>.

                'data' must be a dict.

                'single_pass' is an optional boolean indicating whether the data
                should be serialized in a single pass.  This is significantly
                faster, but requires that the entire set of data be serialized
                in-memory instead of iteratively writing it to the target
                storage object."""

                f = _JSONWriter(data, single_pass=single_pass,
                    pathname=self.pathname, sign=self.sign)
                f.save()

                # Update in-memory copy to reflect stored data.
                self.signatures = f.signatures()

                # Ensure the permissions on the new file are correct.
                try:
                        os.chmod(self.pathname, self.__file_mode)
                except EnvironmentError, e:
                        if e.errno == errno.EACCES:
                                raise api_errors.PermissionsException(
                                    e.filename)
                        if e.errno == errno.EROFS:
                                raise api_errors.ReadOnlyFileSystemException(
                                    e.filename)
                        raise

                # Finally, set the file times to match the last catalog change.
                if self.last_modified:
                        mtime = calendar.timegm(
                            self.last_modified.utctimetuple())
                        os.utime(self.pathname, (mtime, mtime))

        meta_root = property(__get_meta_root, __set_meta_root)


class CatalogPart(CatalogPartBase):
        """A CatalogPart object is the representation of a subset of the package
        FMRIs available from a package repository."""

        __data = None
        ordered = None

        def __init__(self, name, meta_root=None, ordered=True, sign=True):
                """Initializes a CatalogPart object."""

                self.__data = {}
                self.ordered = ordered
                CatalogPartBase.__init__(self, name, meta_root=meta_root,
                    sign=sign)

        def __iter_entries(self, last=False, ordered=False, pubs=EmptyI):
                """Private generator function to iterate over catalog entries.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the CatalogPart has been saved since the last
                modifying operation, or sort() has has been called, this will
                also be the newest version of the package.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                self.load()
                if ordered:
                        stems = self.pkg_names(pubs=pubs)
                else:
                        stems = (
                            (pub, stem)
                            for pub in self.publishers(pubs=pubs)
                            for stem in self.__data[pub]
                        )

                if last:
                        return (
                            (pub, stem, self.__data[pub][stem][-1])
                            for pub, stem in stems
                        )

                if ordered:
                        return (
                            (pub, stem, entry)
                            for pub, stem in stems
                            for entry in reversed(self.__data[pub][stem])
                        )
                return (
                    (pub, stem, entry)
                    for pub, stem in stems
                    for entry in self.__data[pub][stem]
                )

        def add(self, pfmri=None, metadata=None, op_time=None, pub=None,
            stem=None, ver=None):
                """Add a catalog entry for a given FMRI or FMRI components.

                'metadata' is an optional dict containing the catalog
                metadata that should be stored for the specified FMRI.

                The dict representing the entry is returned to callers,
                but should not be modified.
                """

                assert pfmri or (pub and stem and ver)
                if pfmri and not pfmri.publisher:
                        raise api_errors.AnarchicalCatalogFMRI(str(pfmri))

                if not self.loaded:
                        # Hot path, so avoid calling load unless necessary, even
                        # though it performs this check already.
                        self.load()

                if pfmri:
                        pub, stem, ver = pfmri.tuple()
                        ver = str(ver)

                pkg_list = self.__data.setdefault(pub, {})
                ver_list = pkg_list.setdefault(stem, [])
                for entry in ver_list:
                        if entry["version"] == ver:
                                if not pfmri:
                                        pfmri = "pkg://%s/%s@%s" % (pub, stem,
                                            ver)
                                raise api_errors.DuplicateCatalogEntry(
                                    pfmri, operation="add",
                                    catalog_name=self.pathname)

                if metadata is not None:
                        entry = metadata
                else:
                        entry = {}
                entry["version"] = ver

                ver_list.append(entry)
                if self.ordered:
                        self.sort(pfmris=set([pfmri]))

                if not op_time:
                        op_time = datetime.datetime.utcnow()
                self.last_modified = op_time
                self.signatures = {}
                return entry

        def destroy(self):
                """Removes any on-disk files that exist for the catalog part and
                discards all content."""

                self.__data = {}
                return CatalogPartBase.destroy(self)

        def entries(self, cb=None, last=False, ordered=False, pubs=EmptyI):
                """A generator function that produces tuples of the form
                (fmri, entry) as it iterates over the contents of the catalog
                part (where entry is the related catalog entry for the fmri).
                Callers should not modify any of the data that is returned.

                'cb' is an optional callback function that will be executed for
                each package. It must accept two arguments: 'pkg' and 'entry'.
                'pkg' is an FMRI object and 'entry' is the dictionary structure
                of the catalog entry for the package.  If the callback returns
                False, then the entry will not be included in the results.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the CatalogPart has been saved since the last
                modifying operation, or sort() has has been called, this will
                also be the newest version of the package.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                Results are always in catalog version order on a per-
                publisher, per-stem basis.
                """

                for pub, stem, entry in self.__iter_entries(last=last,
                    ordered=ordered, pubs=pubs):
                        f = fmri.PkgFmri("%s@%s" % (stem, entry["version"]),
                            publisher=pub)
                        if cb is None or cb(f, entry):
                                yield f, entry

        def entries_by_version(self, name, pubs=EmptyI):
                """A generator function that produces tuples of (version,
                entries), where entries is a list of tuples of the format
                (fmri, entry) where entry is the catalog entry for the
                FMRI) as it iterates over the CatalogPart contents.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                self.load()

                versions = {}
                entries = {}
                for pub in self.publishers(pubs=pubs):
                        ver_list = self.__data[pub].get(name, ())
                        for entry in ver_list:
                                sver = entry["version"]
                                pfmri = fmri.PkgFmri("%s@%s" % (name,
                                    sver), publisher=pub)

                                versions[sver] = pfmri.version
                                entries.setdefault(sver, [])
                                entries[sver].append((pfmri, entry))

                for key, ver in sorted(versions.iteritems(), key=itemgetter(1)):
                        yield ver, entries[key]

        def fmris(self, last=False, objects=True, ordered=False, pubs=EmptyI):
                """A generator function that produces FMRIs as it iterates
                over the contents of the catalog part.

                'last' is a boolean value that indicates only the last fmri
                for each package on a per-publisher basis should be returned.
                As long as the CatalogPart has been saved since the last
                modifying operation, or sort() has has been called, this will
                also be the newest version of the package.

                'objects' is an optional boolean value indicating whether
                FMRIs should be returned as FMRI objects or as strings.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                Results are always in catalog version order on a per-
                publisher, per-stem basis."""

                if objects:
                        for pub, stem, entry in self.__iter_entries(last=last,
                            ordered=ordered, pubs=pubs):
                                yield fmri.PkgFmri("%s@%s" % (stem,
                                    entry["version"]), publisher=pub)
                        return

                for pub, stem, entry in self.__iter_entries(last=last,
                    ordered=ordered, pubs=pubs):
                        yield "pkg://%s/%s@%s" % (pub,
                            stem, entry["version"])
                return

        def fmris_by_version(self, name, pubs=EmptyI):
                """A generator function that produces tuples of (version,
                fmris), where fmris is a list of the fmris related to the
                version.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                self.load()

                versions = {}
                entries = {}
                for pub in self.publishers(pubs=pubs):
                        ver_list = self.__data[pub].get(name, None)
                        if not ver_list:
                                continue

                        for entry in ver_list:
                                sver = entry["version"]
                                pfmri = fmri.PkgFmri("%s@%s" % (name,
                                    sver), publisher=pub)

                                versions[sver] = pfmri.version
                                entries.setdefault(sver, [])
                                entries[sver].append(pfmri)

                for key, ver in sorted(versions.iteritems(), key=itemgetter(1)):
                        yield ver, entries[key]

        def get_entry(self, pfmri=None, pub=None, stem=None, ver=None):
                """Returns the catalog part entry for the given package FMRI or
                FMRI components."""

                assert pfmri or (pub and stem and ver)
                if pfmri and not pfmri.publisher:
                        raise api_errors.AnarchicalCatalogFMRI(str(pfmri))

                # Since this is a hot path, this function checks for loaded
                # status before attempting to call the load function.
                if not self.loaded:
                        self.load()

                if pfmri:
                        pub, stem, ver = pfmri.tuple()
                        ver = str(ver)

                pkg_list = self.__data.get(pub, None)
                if not pkg_list:
                        return

                ver_list = pkg_list.get(stem, ())
                for entry in ver_list:
                        if entry["version"] == ver:
                                return entry

        def get_package_counts(self):
                """Returns a tuple of integer values (package_count,
                package_version_count).  The first is the number of
                unique packages (per-publisher), and the second is the
                number of unique package versions (per-publisher and
                stem)."""

                self.load()
                package_count = 0
                package_version_count = 0
                for pub in self.publishers():
                        for stem in self.__data[pub]:
                                package_count += 1
                                package_version_count += \
                                    len(self.__data[pub][stem])
                return (package_count, package_version_count)

        def get_package_counts_by_pub(self):
                """Returns a generator of tuples of the form (pub,
                package_count, package_version_count).  'pub' is the publisher
                prefix, 'package_count' is the number of unique packages for the
                publisher, and 'package_version_count' is the number of unique
                package versions for the publisher.
                """

                self.load()
                for pub in self.publishers():
                        package_count = 0
                        package_version_count = 0
                        for stem in self.__data[pub]:
                                package_count += 1
                                package_version_count += \
                                    len(self.__data[pub][stem])
                        yield pub, package_count, package_version_count

        def load(self):
                """Load and transform the catalog part's data, preparing it
                for use."""

                if self.loaded:
                        # Already loaded, or only in-memory.
                        return
                self.__data = CatalogPartBase.load(self)

        def names(self, pubs=EmptyI):
                """Returns a set containing the names of all the packages in
                the CatalogPart.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                self.load()
                return set((
                    stem
                    for pub in self.publishers(pubs=pubs)
                    for stem in self.__data[pub]
                ))

        def pkg_names(self, pubs=EmptyI):
                """A generator function that produces package tuples of the form
                (pub, stem) as it iterates over the contents of the CatalogPart.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.  If specified, publishers will be sorted in
                the order given.

                Results are always returned sorted by stem and then by
                publisher."""

                self.load()

                # Results have to be sorted by stem first, and by
                # publisher prefix second.
                pkg_list = [
                        "%s!%s" % (stem, pub)
                        for pub in self.publishers(pubs=pubs)
                        for stem in self.__data[pub]
                ]

                pub_sort = None
                if pubs:
                        pos = dict((p, i) for (i, p) in enumerate(pubs))
                        def pos_sort(a, b):
                                astem, apub = a.split("!", 1)
                                bstem, bpub = b.split("!", 1)
                                res = cmp(astem, bstem)
                                if res != 0:
                                        return res
                                return cmp(pos[apub], pos[bpub])
                        pub_sort = pos_sort

                for entry in sorted(pkg_list, cmp=pub_sort):
                        stem, pub = entry.split("!", 1)
                        yield pub, stem

        def publishers(self, pubs=EmptyI):
                """A generator function that returns publisher prefixes as it
                iterates over the package data in the CatalogPart.

                'pubs' is an optional list that contains the prefixes of the
                publishers to restrict the results to."""

                self.load()
                for pub in self.__data:
                        # Any entries starting with "_" are part of the
                        # reserved catalog namespace.
                        if not pub[0] == "_" and (not pubs or pub in pubs):
                                yield pub

        def remove(self, pfmri, op_time=None):
                """Remove a package and its metadata."""

                if not pfmri.publisher:
                        raise api_errors.AnarchicalCatalogFMRI(pfmri.get_fmri())

                self.load()
                pkg_list = self.__data.get(pfmri.publisher, None)
                if not pkg_list:
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())

                ver = str(pfmri.version)
                ver_list = pkg_list.get(pfmri.pkg_name, [])
                for i, entry in enumerate(ver_list):
                        if entry["version"] == ver:
                                # Safe to do this since a 'break' is done
                                # immediately after removals are performed.
                                del ver_list[i]
                                if not ver_list:
                                        # When all version entries for a
                                        # package are removed, its stem
                                        # should be also.
                                        del pkg_list[pfmri.pkg_name]
                                if not pkg_list:
                                        # When all package stems for a
                                        # publisher have been removed,
                                        # it should be also.
                                        del self.__data[pfmri.publisher]
                                break
                else:
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())

                if not op_time:
                        op_time = datetime.datetime.utcnow()
                self.last_modified = op_time
                self.signatures = {}

        def save(self, single_pass=False):
                """Transform and store the catalog part's data in a file using
                the pathname <self.meta_root>/<self.name>.

                'single_pass' is an optional boolean indicating whether the data
                should be serialized in a single pass.  This is significantly
                faster, but requires that the entire set of data be serialized
                in-memory instead of iteratively writing it to the target
                storage object."""

                if not self.meta_root:
                        # Assume this is in-memory only.
                        return

                # Ensure content is loaded before attempting save.
                self.load()

                CatalogPartBase.save(self, self.__data, single_pass=single_pass)

        def sort(self, pfmris=None, pubs=None):
                """Re-sorts the contents of the CatalogPart such that version
                entries for each package stem are in ascending order.

                'pfmris' is an optional set of FMRIs to restrict the sort to.
                This is useful during catalog operations as only entries for
                the corresponding package stem(s) need to be sorted.

                'pubs' is an optional set of publisher prefixes to restrict
                the sort to.  This is useful during catalog operations as only
                entries for the corresponding publisher stem(s) need to be
                sorted.  This option has no effect if 'pfmris' is also
                provided.

                If neither 'pfmris' or 'pubs' is provided, all entries will be
                sorted."""

                def order(a, b):
                        # XXX version requires build string; 5.11 is not sane.
                        v1 = pkg.version.Version(a["version"], "5.11")
                        v2 = pkg.version.Version(b["version"], "5.11")
                        return cmp(v1, v2)

                self.load()
                if pfmris is not None:
                        processed = set()
                        for f in pfmris:
                                pkg_stem = f.get_pkg_stem()
                                if pkg_stem in processed:
                                        continue
                                processed.add(pkg_stem)

                                # The specified FMRI may not exist in this
                                # CatalogPart, so continue if it does not
                                # exist.
                                pkg_list = self.__data.get(f.publisher, None)
                                if pkg_list:
                                        ver_list = pkg_list.get(f.pkg_name,
                                            None)
                                        if ver_list:
                                                ver_list.sort(cmp=order)
                        return

                for pub in self.publishers(pubs=pubs):
                        for stem in self.__data[pub]:
                                self.__data[pub][stem].sort(cmp=order)

        def tuples(self, last=False, ordered=False, pubs=EmptyI):
                """A generator function that produces FMRI tuples as it
                iterates over the contents of the catalog part.

                'last' is a boolean value that indicates only the last FMRI
                tuple for each package on a per-publisher basis should be
                returned.  As long as the CatalogPart has been saved since
                the last modifying operation, or sort() has has been called,
                this will also be the newest version of the package.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                return (
                    (pub, stem, entry["version"])
                    for pub, stem, entry in self.__iter_entries(last=last,
                        ordered=ordered, pubs=pubs)
                )

        def tuple_entries(self, cb=None, last=False, ordered=False, pubs=EmptyI):
                """A generator function that produces tuples of the form ((pub,
                stem, version), entry) as it iterates over the contents of the
                catalog part (where entry is the related catalog entry for the
                fmri).  Callers should not modify any of the data that is
                returned.

                'cb' is an optional callback function that will be executed for
                each package. It must accept two arguments: 'pkg' and 'entry'.
                'pkg' is an FMRI tuple and 'entry' is the dictionary structure
                of the catalog entry for the package.  If the callback returns
                False, then the entry will not be included in the results.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the CatalogPart has been saved since the last
                modifying operation, or sort() has has been called, this will
                also be the newest version of the package.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                Results are always in catalog version order on a per-publisher,
                per-stem basis."""

                for pub, stem, entry in self.__iter_entries(last=last,
                    ordered=ordered, pubs=pubs):
                        t = (pub, stem, entry["version"])
                        if cb is None or cb(t, entry):
                                yield t, entry

        def validate(self, signatures=None):
                """Verifies whether the signatures for the contents of the
                CatalogPart match the specified signature data, or if not
                provided, the current signature data.  Raises the exception
                named 'BadCatalogSignatures' on failure."""

                if not self.signatures and not signatures:
                        # Nothing to validate.
                        return

                # Ensure content is loaded before attempting to retrieve
                # or generate signature data.
                self.load()
                if not signatures:
                        signatures = self.signatures

                new_signatures = self._gen_signatures(self.__data)
                if new_signatures != signatures:
                        raise api_errors.BadCatalogSignatures(self.pathname)


class CatalogUpdate(CatalogPartBase):
        """A CatalogUpdate object is an augmented representation of a subset
        of the package data contained within a Catalog."""

        # Properties.
        __data = None
        last_modified = None

        # Operation constants.
        ADD = "add"
        REMOVE = "remove"

        def __init__(self, name, meta_root=None, sign=True):
                """Initializes a CatalogUpdate object."""

                self.__data = {}
                CatalogPartBase.__init__(self, name, meta_root=meta_root,
                    sign=sign)

        def add(self, pfmri, operation, op_time, metadata=None):
                """Records the specified catalog operation and any related
                catalog metadata for the specified package FMRI.

                'operation' must be one of the following constant values
                provided by the CatalogUpdate class:
                    ADD
                    REMOVE

                'op_time' is a UTC datetime object indicating the time
                the catalog operation was performed.

                'metadata' is an optional dict containing the catalog
                metadata that should be stored for the specified FMRI
                indexed by catalog part (e.g. "dependency", "summary",
                etc.)."""

                if not pfmri.publisher:
                        raise api_errors.AnarchicalCatalogFMRI(pfmri.get_fmri())

                if operation not in (self.ADD, self.REMOVE):
                        raise api_errors.UnknownUpdateType(operation)

                self.load()
                self.__data.setdefault(pfmri.publisher, {})
                pkg_list = self.__data[pfmri.publisher]

                pkg_list.setdefault(pfmri.pkg_name, [])
                ver_list = pkg_list[pfmri.pkg_name]

                if metadata is not None:
                        entry = metadata
                else:
                        entry = {}
                entry["op-time"] = datetime_to_basic_ts(op_time)
                entry["op-type"] = operation
                entry["version"] = str(pfmri.version)
                ver_list.append(entry)

                # To ensure the update log is viewed as having been updated
                # at the exact same time as the catalog, the last_modified
                # time of the update log must match the operation time.
                self.last_modified = op_time
                self.signatures = {}

        def load(self):
                """Load and transform the catalog update's data, preparing it
                for use."""

                if self.loaded:
                        # Already loaded, or only in-memory.
                        return
                self.__data = CatalogPartBase.load(self)

        def publishers(self):
                """A generator function that returns publisher prefixes as it
                iterates over the package data in the CatalogUpdate."""

                self.load()
                for pub in self.__data:
                        # Any entries starting with "_" are part of the
                        # reserved catalog namespace.
                        if not pub[0] == "_":
                                yield pub

        def save(self):
                """Transform and store the catalog update's data in a file using
                the pathname <self.meta_root>/<self.name>."""

                if not self.meta_root:
                        # Assume this is in-memory only.
                        return

                # Ensure content is loaded before attempting save.
                self.load()

                CatalogPartBase.save(self, self.__data)

        def updates(self):
                """A generator function that produces tuples of the format
                (fmri, op_type, op_time, metadata).  Where:

                    * 'fmri' is a PkgFmri object for the package.

                    * 'op_type' is a CatalogUpdate constant indicating
                      the catalog operation performed.

                    * 'op_time' is a UTC datetime object representing the
                      time time the catalog operation was performed.

                    * 'metadata' is a dict containing the catalog metadata
                      for the FMRI indexed by catalog part name.

                Results are always in ascending operation time order on a
                per-publisher, per-stem basis.
                """

                self.load()

                def get_update(pub, stem, entry):
                        mdata = {}
                        for key in entry:
                                if key.startswith("catalog."):
                                        mdata[key] = entry[key]
                        op_time = basic_ts_to_datetime(entry["op-time"])
                        pfmri = fmri.PkgFmri("%s@%s" % (stem, entry["version"]),
                            publisher=pub)
                        return (pfmri, entry["op-type"], op_time, mdata)

                for pub in self.publishers():
                        for stem in self.__data[pub]:
                                for entry in self.__data[pub][stem]:
                                        yield get_update(pub, stem, entry)
                return

        def validate(self, signatures=None):
                """Verifies whether the signatures for the contents of the
                CatalogUpdate match the specified signature data, or if not
                provided, the current signature data.  Raises the exception
                named 'BadCatalogSignatures' on failure."""

                if not self.signatures and not signatures:
                        # Nothing to validate.
                        return

                # Ensure content is loaded before attempting to retrieve
                # or generate signature data.
                self.load()
                if not signatures:
                        signatures = self.signatures

                new_signatures = self._gen_signatures(self.__data)
                if new_signatures != signatures:
                        raise api_errors.BadCatalogSignatures(self.pathname)


class CatalogAttrs(CatalogPartBase):
        """A CatalogAttrs object is the representation of the attributes of a
        Catalog object."""

        # Properties.
        __data = None

        def __init__(self, meta_root=None, sign=True):
                """Initializes a CatalogAttrs object."""

                self.__data = {}
                CatalogPartBase.__init__(self, name="catalog.attrs",
                    meta_root=meta_root, sign=sign)

                if self.loaded:
                        # If the data is already seen as 'loaded' during init,
                        # this is actually a new object, so setup some sane
                        # defaults.
                        created = self.__data["last-modified"]
                        self.__data = {
                            "created": created,
                            "last-modified": created,
                            "package-count": 0,
                            "package-version-count": 0,
                            "parts": {},
                            "updates": {},
                            "version": 1,
                        }
                else:
                        # Assume that the attributes of the catalog can be
                        # obtained from a file.
                        self.load()

        def __get_created(self):
                return self.__data["created"]

        def __get_last_modified(self):
                return self.__data["last-modified"]

        def __get_package_count(self):
                return self.__data["package-count"]

        def __get_package_version_count(self):
                return self.__data["package-version-count"]

        def __get_parts(self):
                return self.__data["parts"]

        def __get_updates(self):
                return self.__data["updates"]

        def __get_version(self):
                return self.__data["version"]

        def __set_created(self, value):
                self.__data["created"] = value
                self.signatures = {}

        def __set_last_modified(self, value):
                self.__data["last-modified"] = value
                self.signatures = {}

        def __set_package_count(self, value):
                self.__data["package-count"] = value
                self.signatures = {}

        def __set_package_version_count(self, value):
                self.__data["package-version-count"] = value
                self.signatures = {}

        def __set_parts(self, value):
                self.__data["parts"] = value
                self.signatures = {}

        def __set_updates(self, value):
                self.__data["updates"] = value
                self.signatures = {}

        def __set_version(self, value):
                self.__data["version"] = value
                self.signatures = {}

        def __transform(self):
                """Duplicate and transform 'self.__data' for saving."""

                # Use a copy to prevent the in-memory version from being
                # affected by the transformations.
                struct = copy.deepcopy(self.__data)
                for key, val in struct.iteritems():
                        if isinstance(val, datetime.datetime):
                                # Convert datetime objects to an ISO-8601
                                # basic format string.
                                struct[key] = datetime_to_basic_ts(val)
                                continue

                        if key in ("parts", "updates"):
                                for e in val:
                                        lm = val[e].get("last-modified", None)
                                        if lm:
                                                lm = datetime_to_basic_ts(lm)
                                                val[e]["last-modified"] = lm
                return struct

        def load(self):
                """Load and transform the catalog attribute data."""

                if self.loaded:
                        # Already loaded, or only in-memory.
                        return

                struct = CatalogPartBase.load(self)
                for key, val in struct.iteritems():
                        if key in ("created", "last-modified"):
                                # Convert ISO-8601 basic format strings to
                                # datetime objects.  These dates can be
                                # 'null' due to v0 catalog transformations.
                                if val:
                                        struct[key] = basic_ts_to_datetime(val)
                                continue

                        if key in ("parts", "updates"):
                                for e in val:
                                        lm = val[e].get("last-modified", None)
                                        if lm:
                                                lm = basic_ts_to_datetime(lm)
                                                val[e]["last-modified"] = lm
                self.__data = struct

        def save(self):
                """Transform and store the catalog attribute data in a file
                using the pathname <self.meta_root>/<self.name>."""

                if not self.meta_root:
                        # Assume this is in-memory only.
                        return

                # Ensure content is loaded before attempting save.
                self.load()

                CatalogPartBase.save(self, self.__transform(), single_pass=True)

        def validate(self, signatures=None):
                """Verifies whether the signatures for the contents of the
                CatalogAttrs match the specified signature data, or if not
                provided, the current signature data.  Raises the exception
                named 'BadCatalogSignatures' on failure."""

                if not self.signatures and not signatures:
                        # Nothing to validate.
                        return

                # Ensure content is loaded before attempting to retrieve
                # or generate signature data.
                self.load()
                if not signatures:
                        signatures = self.signatures

                new_signatures = self._gen_signatures(self.__transform())
                if new_signatures != signatures:
                        raise api_errors.BadCatalogSignatures(self.pathname)

        created = property(__get_created, __set_created)

        last_modified = property(__get_last_modified, __set_last_modified)

        package_count = property(__get_package_count, __set_package_count)

        package_version_count = property(__get_package_version_count,
            __set_package_version_count)

        parts = property(__get_parts, __set_parts)

        updates = property(__get_updates, __set_updates)

        version = property(__get_version, __set_version)


class Catalog(object):
        """A Catalog is the representation of the package FMRIs available from
        a package repository."""

        __BASE_PART = "catalog.base.C"
        __DEPS_PART = "catalog.dependency.C"
        __SUMM_PART_PFX = "catalog.summary"

        # The file mode to be used for all catalog files.
        __file_mode = stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH

        # These properties are declared here so that they show up in the pydoc
        # documentation as private, and for clarity in the property declarations
        # found near the end of the class definition.
        _attrs = None
        __batch_mode = None
        __lock = None
        __manifest_cb = None
        __meta_root = None
        __sign = None

        # These are used to cache or store CatalogPart and CatalogUpdate objects
        # as they are used.  It should not be confused with the CatalogPart
        # names and CatalogUpdate names stored in the CatalogAttrs object.
        __parts = None
        __updates = None

        # Class Constants
        DEPENDENCY, SUMMARY = range(2)
        PKG_STATE_OBSOLETE, PKG_STATE_RENAMED, PKG_STATE_UNSUPPORTED = range(3)

        def __init__(self, batch_mode=False, meta_root=None, log_updates=False,
            manifest_cb=None, read_only=False, sign=True):
                """Initializes a Catalog object.

                'batch_mode' is an optional boolean value that indicates that
                the caller intends to perform multiple modifying operations on
                catalog before saving.  This is useful for performance reasons
                as the contents of the catalog will not be sorted after each
                change, and the package counts will not be updated (except at
                save()).  By default this value is False.  If this value is
                True, callers are responsible for calling finalize() to ensure
                that catalog entries are in the correct order and package counts
                accurately reflect the catalog contents.

                'meta_root' is an optional absolute pathname of a directory
                that catalog metadata can be written to and read from, and
                must already exist.  If no path is supplied, then it is
                assumed that the catalog object will be used for in-memory
                operations only.

                'log_updates' is an optional boolean value indicating whether
                updates to the catalog should be logged.  This enables consumers
                of the catalog to perform incremental updates.

                'manifest_cb' is an optional callback used by actions() and
                get_entry_actions() to lazy-load Manifest Actions if the catalog
                does not have the actions data for a requested package entry.

                'read_only' is an optional boolean value that indicates if
                operations that modify the catalog are allowed (an assertion
                error will be raised if one is attempted and this is True).

                'sign' is an optional boolean value that indicates that the
                the catalog data should have signature data generated and
                embedded when serialized.  This option is primarily a matter
                of convenience for callers that wish to trade integrity checks
                for improved catalog serialization performance."""

                self.__batch_mode = batch_mode
                self.__manifest_cb = manifest_cb
                self.__parts = {}
                self.__updates = {}

                # Must be set after the above.
                self.log_updates = log_updates
                self.meta_root = meta_root
                self.read_only = read_only
                self.sign = sign

                # Must be set after the above.
                self._attrs = CatalogAttrs(meta_root=self.meta_root, sign=sign)

                # This lock is used to protect the catalog file from multiple
                # threads writing to it at the same time.
                self.__lock = threading.Lock()

                # Must be done last.
                self.__set_perms()

        def __actions(self, info_needed, excludes=EmptyI, cb=None, locales=None,
            last_version=False, ordered=False, pubs=EmptyI):
                assert info_needed
                if not locales:
                        locales = set(("C",))
                else:
                        locales = set(locales)

                for f, entry in self.__entries(cb=cb, info_needed=info_needed,
                    locales=locales, last_version=last_version,
                    ordered=ordered, pubs=pubs):
                        if "actions" in entry:
                                yield f, self.__gen_actions(f, entry["actions"],
                                    excludes)
                        elif self.__manifest_cb:
                                yield f, self.__gen_lazy_actions(f, info_needed,
                                    locales, excludes)
                        else:
                                yield f, EmptyI

        def __append(self, src, cb=None, pfmri=None, pubs=EmptyI):
                """Private version; caller responsible for locking."""

                base = self.get_part(self.__BASE_PART)
                src_base = src.get_part(self.__BASE_PART, must_exist=True)
                if src_base is None:
                        if pfmri:
                                raise api_errors.UnknownCatalogEntry(pfmri)
                        # Nothing to do
                        return

                # Use the same operation time and date for all operations so
                # that the last modification times will be synchronized.  This
                # also has the benefit of avoiding extra datetime object
                # instantiations.
                op_time = datetime.datetime.utcnow()

                # For each entry in the 'src' catalog, add its BASE entry to the
                # current catalog along and then add it to the 'd'iscard dict if
                # 'cb' is defined and returns False.
                if pfmri:
                        entry = src_base.get_entry(pfmri)
                        if entry is None:
                                raise api_errors.UnknownCatalogEntry(
                                    pfmri.get_fmri())
                        entries = [(pfmri, entry)]
                else:
                        entries = src_base.entries()

                d = {}
                for f, entry in entries:
                        if pubs and f.publisher not in pubs:
                                continue

                        nentry = copy.deepcopy(entry)
                        if cb is not None:
                                merge, mdata = cb(src, f, entry)
                                if not merge:
                                        pub = d.setdefault(f.publisher, {})
                                        plist = pub.setdefault(f.pkg_name,
                                            set())
                                        plist.add(f.version)
                                        continue

                                if mdata:
                                        if "metadata" in nentry:
                                                nentry["metadata"].update(mdata)
                                        else:
                                                nentry["metadata"] = mdata
                        base.add(f, metadata=nentry, op_time=op_time)

                if d and pfmri:
                        # If the 'd'iscards dict is populated and pfmri is
                        # defined, then there is nothing more to do.
                        return

                # Finally, merge any catalog part entries that exist unless the
                # FMRI is found in the 'd'iscard dict.
                for name in src.parts.keys():
                        if name == self.__BASE_PART:
                                continue

                        part = src.get_part(name, must_exist=True)
                        if part is None:
                                # Part doesn't exist in-memory or on-disk, so
                                # skip it.
                                continue

                        if pfmri:
                                entry = part.get_entry(pfmri)
                                if entry is None:
                                        # Package isn't in this part; skip it.
                                        continue
                                entries = [(pfmri, entry)]
                        else:
                                entries = part.entries()

                        npart = self.get_part(name)
                        for f, entry in entries:
                                if pubs and f.publisher not in pubs:
                                        continue
                                if f.publisher in d and \
                                    f.pkg_name in d[f.publisher] and \
                                    f.version in d[f.publisher][f.pkg_name]:
                                        # Skip this package.
                                        continue

                                nentry = copy.deepcopy(entry)
                                npart.add(f, metadata=nentry, op_time=op_time)

        def __entries(self, cb=None, info_needed=EmptyI,
            last_version=False, locales=None, ordered=False, pubs=EmptyI,
            tuples=False):
                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.
                        return

                if not locales:
                        locales = set(("C",))
                else:
                        locales = set(locales)

                parts = []
                if self.DEPENDENCY in info_needed:
                        part = self.get_part(self.__DEPS_PART, must_exist=True)
                        if part is not None:
                                parts.append(part)

                if self.SUMMARY in info_needed:
                        for locale in locales:
                                part = self.get_part(
                                    "%s.%s" % (self.__SUMM_PART_PFX, locale),
                                    must_exist=True)
                                if part is None:
                                        # Data not available for this
                                        # locale.
                                        continue
                                parts.append(part)

                def merge_entry(src, dest):
                        for k, v in src.iteritems():
                                if k == "actions":
                                        dest.setdefault(k, [])
                                        dest[k] += v
                                elif k != "version":
                                        dest[k] = v

                if tuples:
                        for r, bentry in base.tuple_entries(cb=cb,
                            last=last_version, ordered=ordered, pubs=pubs):
                                pub, stem, ver = r
                                mdata = {}
                                merge_entry(bentry, mdata)
                                for part in parts:
                                        entry = part.get_entry(pub=pub,
                                            stem=stem, ver=ver)
                                        if entry is None:
                                                # Part doesn't have this FMRI,
                                                # so skip it.
                                                continue
                                        for k, v in entry.iteritems():
                                                if k == "actions":
                                                        mdata.setdefault(k, [])
                                                        mdata[k] += v
                                                elif k != "version":
                                                        mdata[k] = v
                                yield r, mdata
                        return

                for f, bentry in base.entries(cb=cb, last=last_version,
                    ordered=ordered, pubs=pubs):
                        mdata = {}
                        merge_entry(bentry, mdata)
                        for part in parts:
                                entry = part.get_entry(f)
                                if entry is None:
                                        # Part doesn't have this FMRI,
                                        # so skip it.
                                        continue
                                for k, v in entry.iteritems():
                                        if k == "actions":
                                                mdata.setdefault(k, [])
                                                mdata[k] += v
                                        elif k != "version":
                                                mdata[k] = v
                        yield f, mdata

        def __finalize(self, pfmris=None, pubs=None, sort=True):
                """Private finalize method; exposes additional controls for
                internal callers."""

                package_count = 0
                package_version_count = 0

                part = self.get_part(self.__BASE_PART, must_exist=True)
                if part is not None:
                        # If the base Catalog didn't exist (in-memory or on-
                        # disk) that implies there is nothing to sort and
                        # there are no packages (since the base catalog part
                        # must always exist for packages to be present).
                        package_count, package_version_count = \
                            part.get_package_counts()

                        if sort:
                                # Some operations don't need this, such as
                                # remove...
                                for part in self.__parts.values():
                                        part.sort(pfmris=pfmris, pubs=pubs)

                self._attrs.package_count = package_count
                self._attrs.package_version_count = \
                    package_version_count

        @staticmethod
        def __gen_actions(pfmri, actions, excludes=EmptyI):
                errors = None
                for astr in actions:
                        try:
                                a = pkg.actions.fromstr(astr)
                        except pkg.actions.ActionError, e:
                                # Accumulate errors and continue so that as
                                # much of the action data as possible can be
                                # parsed.
                                if errors is None:
                                        # Allocate this here to avoid overhead
                                        # of list allocation/deallocation.
                                        errors = []
                                if not isinstance(pfmri, fmri.PkgFmri):
                                        # pfmri is assumed to be a FMRI tuple.
                                        pub, stem, ver = pfmri
                                        pfmri = fmri.PkgFmri("%s@%s" % (stem,
                                            ver), publisher=pub)
                                e.fmri = pfmri
                                errors.append(e)
                                continue

                        if a.name == "set" and \
                            (a.attrs["name"].startswith("facet") or
                            a.attrs["name"].startswith("variant")):
                                # Don't filter actual facet or variant
                                # set actions.
                                yield a
                        elif a.include_this(excludes):
                                yield a

                if errors is not None:
                        raise api_errors.InvalidPackageErrors(errors)

        def __gen_lazy_actions(self, f, info_needed, locales=EmptyI,
            excludes=EmptyI):
                # Note that the logic below must be kept in sync with
                # group_actions found in add_package.
                m = self.__manifest_cb(self, f)
                if not m:
                        # If the manifest callback returns None, then
                        # assume there is no action data to yield.
                        return

                if Catalog.DEPENDENCY in info_needed:
                        atypes = ("depend", "set")
                elif Catalog.SUMMARY in info_needed:
                        atypes = ("set",)
                else:
                        raise RuntimeError(_("Unknown info_needed "
                            "type: %s" % info_needed))

                for a, attr_name in self.__gen_manifest_actions(m, atypes,
                    excludes):
                        if (a.name == "depend" or \
                            attr_name.startswith("variant") or \
                            attr_name.startswith("facet") or \
                            attr_name.startswith("pkg.depend.") or \
                            attr_name in ("pkg.obsolete",
                                "pkg.renamed")):
                                if Catalog.DEPENDENCY in info_needed:
                                        yield a
                        elif Catalog.SUMMARY in info_needed and a.name == "set":
                                if attr_name in ("fmri", "pkg.fmri"):
                                        continue

                                comps = attr_name.split(":")
                                if len(comps) > 1:
                                        # 'set' is locale-specific.
                                        if comps[1] not in locales:
                                                continue
                                yield a

        @staticmethod
        def __gen_manifest_actions(m, atypes, excludes):
                """Private helper function to iterate over a Manifest's actions
                by action type, returning tuples of (action, attr_name)."""
                for atype in atypes:
                        for a in m.gen_actions_by_type(atype):
                                if not a.include_this(excludes):
                                        continue

                                if atype == "set":
                                        yield a, a.attrs["name"]
                                else:
                                        yield a, None

        def __get_batch_mode(self):
                return self.__batch_mode

        def __get_last_modified(self):
                return self._attrs.last_modified

        def __get_meta_root(self):
                return self.__meta_root

        def __get_sign(self):
                return self.__sign

        def __get_update(self, name, cache=True, must_exist=False):
                # First, check if the update has already been cached,
                # and if so, return it.
                ulog = self.__updates.get(name, None)
                if ulog is not None:
                        return ulog
                elif not self.meta_root and must_exist:
                        return

                # Next, if the update hasn't been cached,
                # create an object for it.
                ulog = CatalogUpdate(name, meta_root=self.meta_root,
                    sign=self.__sign)
                if self.meta_root and must_exist and not ulog.exists:
                        # Update doesn't exist on-disk,
                        # so don't return anything.
                        return
                if cache:
                        self.__updates[name] = ulog
                return ulog

        def __get_version(self):
                return self._attrs.version

        def __lock_catalog(self):
                """Locks the catalog preventing multiple threads or external
                consumers of the catalog from modifying it during operations.
                """

                # XXX need filesystem lock too?
                self.__lock.acquire()

        def __log_update(self, pfmri, operation, op_time, entries=None):
                """Helper function to log catalog changes."""

                if not self.__batch_mode:
                        # The catalog.attrs needs to be updated to reflect
                        # the changes made.  A sort doesn't need to be done
                        # here as the individual parts will automatically do
                        # that as needed in this case.
                        self.__finalize(sort=False)

                # This must be set to exactly the same time as the update logs
                # so that the changes in the update logs are not marked as
                # being newer than the catalog or vice versa.
                attrs = self._attrs
                attrs.last_modified = op_time

                if not self.log_updates:
                        return

                updates = {}
                for pname in entries:
                        # The last component of the updatelog filename is the
                        # related locale.
                        locale = pname.split(".", 2)[2]
                        updates.setdefault(locale, {})
                        parts = updates[locale]
                        parts[pname] = entries[pname]

                logdate = datetime_to_update_ts(op_time)
                for locale, metadata in updates.iteritems():
                        name = "update.%s.%s" % (logdate, locale)
                        ulog = self.__get_update(name)
                        ulog.add(pfmri, operation, metadata=metadata,
                            op_time=op_time)
                        attrs.updates[name] = {
                            "last-modified": op_time
                        }

                for name, part in self.__parts.iteritems():
                        # Signature data for each part needs to be cleared,
                        # and will only be available again after save().
                        attrs.parts[name] = {
                            "last-modified": part.last_modified
                        }

        @staticmethod
        def __parse_fmri_patterns(patterns):
                """A generator function that yields a list of tuples of the form
                (pattern, error, fmri, matcher) based on the provided patterns,
                where 'error' is any exception encountered while parsing the
                pattern, 'fmri' is the resulting FMRI object, and 'matcher' is
                one of the following pkg.fmri matching functions:

                        pkg.fmri.exact_name_match
                                Indicates that the name portion of the pattern
                                must match exactly and the version (if provided)
                                must be considered a successor or equal to the
                                target FMRI.

                        pkg.fmri.fmri_match
                                Indicates that the name portion of the pattern
                                must be a proper subset and the version (if
                                provided) must be considered a successor or
                                equal to the target FMRI.

                        pkg.fmri.glob_match
                                Indicates that the name portion of the pattern
                                uses fnmatch rules for pattern matching (shell-
                                style wildcards) and that the version can either
                                match exactly, match partially, or contain
                                wildcards.
                """

                brelease = "5.11"
                for pat in patterns:
                        error = None
                        matcher = None
                        npat = None
                        try:
                                parts = pat.split("@", 1)
                                pat_stem = parts[0]
                                pat_ver = None
                                if len(parts) > 1:
                                        pat_ver = parts[1]

                                if "*" in pat_stem or "?" in pat_stem:
                                        matcher = fmri.glob_match
                                elif pat_stem.startswith("pkg:/") or \
                                    pat_stem.startswith("/"):
                                        matcher = fmri.exact_name_match
                                else:
                                        matcher = fmri.fmri_match

                                if matcher == fmri.glob_match:
                                        npat = fmri.MatchingPkgFmri(pat_stem,
                                            brelease)
                                else:
                                        npat = fmri.PkgFmri(pat_stem, brelease)

                                if not pat_ver:
                                        # Do nothing.
                                        pass
                                elif "*" in pat_ver or "?" in pat_ver or \
                                    pat_ver == "latest":
                                        npat.version = \
                                            pkg.version.MatchingVersion(pat_ver,
                                                brelease)
                                else:
                                        npat.version = \
                                            pkg.version.Version(pat_ver,
                                                brelease)

                        except (fmri.FmriError, pkg.version.VersionError), e:
                                # Whatever the error was, return it.
                                error = e
                        yield (pat, error, npat, matcher)

        def __save(self):
                """Private save function.  Caller is responsible for locking
                the catalog."""

                attrs = self._attrs
                if self.log_updates:
                        for name, ulog in self.__updates.iteritems():
                                ulog.save()

                                # Replace the existing signature data
                                # with the new signature data.
                                entry = attrs.updates[name] = {
                                    "last-modified": ulog.last_modified
                                }
                                for n, v in ulog.signatures.iteritems():
                                        entry["signature-%s" % n] = v

                # Save any CatalogParts that are currently in-memory,
                # updating their related information in catalog.attrs
                # as they are saved.
                for name, part in self.__parts.iteritems():
                        # Must save first so that signature data is
                        # current.

                        # single-pass encoding is not used for summary part as
                        # it increases memory usage substantially (30MB at 
                        # current for /dev).  No significant difference is
                        # detectable for other parts though.
                        single_pass = name in (self.__BASE_PART,
                            self.__DEPS_PART)
                        part.save(single_pass=single_pass)

                        # Now replace the existing signature data with
                        # the new signature data.
                        entry = attrs.parts[name] = {
                            "last-modified": part.last_modified
                        }
                        for n, v in part.signatures.iteritems():
                                entry["signature-%s" % n] = v

                # Finally, save the catalog attributes.
                attrs.save()

        def __set_batch_mode(self, value):
                self.__batch_mode = value
                for part in self.__parts.values():
                        part.ordered = not self.__batch_mode

        def __set_last_modified(self, value):
                self._attrs.last_modified = value

        def __set_meta_root(self, pathname):
                if pathname:
                        pathname = os.path.abspath(pathname)
                self.__meta_root = pathname

                # If the Catalog's meta_root changes, the meta_root of all of
                # its parts must be changed too.
                if self._attrs:
                        self._attrs.meta_root = pathname

                for part in self.__parts.values():
                        part.meta_root = pathname

                for ulog in self.__updates.values():
                        ulog.meta_root = pathname

        def __set_perms(self):
                """Sets permissions on attrs and parts if not read_only and if
                the current user can do so; raises BadCatalogPermissions if the
                permissions are wrong and cannot be corrected."""

                if not self.meta_root:
                        # Nothing to do.
                        return

                files = [self._attrs.name]
                files.extend(self._attrs.parts.keys())
                files.extend(self._attrs.updates.keys())

                # Force file_mode, so that unprivileged users can read these.
                bad_modes = []
                for name in files:
                        pathname = os.path.join(self.meta_root, name)
                        try:
                                if self.read_only:
                                        fmode = stat.S_IMODE(os.stat(
                                            pathname).st_mode)
                                        if fmode != self.__file_mode:
                                                bad_modes.append((pathname,
                                                    "%o" % self.__file_mode,
                                                    "%o" % fmode))
                                else:
                                        os.chmod(pathname, self.__file_mode)
                        except EnvironmentError, e:
                                # If the file doesn't exist yet, move on.
                                if e.errno == errno.ENOENT:
                                        continue

                                # If the mode change failed for another reason,
                                # check to see if we actually needed to change
                                # it, and if so, add it to bad_modes.
                                fmode = stat.S_IMODE(os.stat(
                                    pathname).st_mode)
                                if fmode != self.__file_mode:
                                        bad_modes.append((pathname,
                                            "%o" % self.__file_mode,
                                            "%o" % fmode))

                if bad_modes:
                        raise api_errors.BadCatalogPermissions(bad_modes)

        def __set_sign(self, value):
                self.__sign = value

                # If the Catalog's sign property changes, the value of that
                # property for its attributes, etc. must be changed too.
                if self._attrs:
                        self._attrs.sign = value

                for part in self.__parts.values():
                        part.sign = value

                for ulog in self.__updates.values():
                        ulog.sign = value

        def __set_version(self, value):
                self._attrs.version = value

        def __unlock_catalog(self):
                """Unlocks the catalog allowing other catalog consumers to
                modify it."""

                # XXX need filesystem unlock too?
                self.__lock.release()

        def actions(self, info_needed, excludes=EmptyI, cb=None,
            last=False, locales=None, ordered=False, pubs=EmptyI):
                """A generator function that produces tuples of the format
                (fmri, actions) as it iterates over the contents of the
                catalog (where 'actions' is a generator that returns the
                Actions corresponding to the requested information).

                If the catalog doesn't contain any action data for the package
                entry, and manifest_cb was defined at Catalog creation time,
                the action data will be lazy-loaded by the actions generator;
                otherwise it will return an empty iterator.  This means that
                the manifest_cb will be executed even for packages that don't
                actually have any actions corresponding to info_needed.  For
                example, if a package doesn't have any dependencies, the
                manifest_cb will still be executed.  This was considered a
                reasonable compromise as packages are generally expected to
                have DEPENDENCY and SUMMARY information.

                'excludes' is a list of variants which will be used to determine
                what should be allowed by the actions generator in addition to
                what is specified by 'info_needed'.

                'cb' is an optional callback function that will be executed for
                each package before its action data is retrieved. It must accept
                two arguments: 'pkg' and 'entry'.  'pkg' is an FMRI object and
                'entry' is the dictionary structure of the catalog entry for the
                package.  If the callback returns False, then the entry will not
                be included in the results.  This can significantly improve
                performance by avoiding action data retrieval for results that
                will not be used.

                'info_needed' is a set of one or more catalog constants
                indicating the types of catalog data that will be returned
                in 'actions' in addition to the above:

                        DEPENDENCY
                                Depend and set Actions for package obsoletion,
                                renaming, variants.

                        SUMMARY
                                Any remaining set Actions not listed above, such
                                as pkg.summary, pkg.description, etc.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the catalog has been saved since the last modifying
                operation, or finalize() has has been called, this will also be
                the newest version of the package.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pfmri' is an optional FMRI to limit the returned results to.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                return self.__actions(info_needed, excludes=excludes,
                    cb=cb, last_version=last, locales=locales, ordered=ordered,
                    pubs=pubs)

        def add_package(self, pfmri, manifest=None, metadata=None):
                """Add a package and its related metadata to the catalog and
                its parts as needed.

                'manifest' is an optional Manifest object that will be used
                to retrieve the metadata related to the package.

                'metadata' is an optional dict of additional metadata to store
                with the package's BASE record."""

                assert not self.read_only

                def group_actions(actions):
                        dep_acts = { "C": [] }
                        # Summary actions are grouped by locale, since each
                        # goes to a locale-specific catalog part.
                        sum_acts = { "C": [] }
                        for act in actions:
                                if act.name == "depend":
                                        dep_acts["C"].append(str(act))
                                        continue

                                name = act.attrs["name"]
                                if name.startswith("variant") or \
                                    name.startswith("facet") or \
                                    name.startswith("pkg.depend.") or \
                                    name in ("pkg.obsolete", "pkg.renamed"):
                                        # variant and facet data goes to the
                                        # dependency catalog part.
                                        dep_acts["C"].append(str(act))
                                        continue
                                elif name in ("fmri", "pkg.fmri"):
                                        # Redundant in the case of the catalog.
                                        continue

                                # All other set actions go to the summary
                                # catalog parts, grouped by locale.  To
                                # determine the locale, the set attribute's
                                # name is split by ':' into its field and
                                # locale components.  If ':' is not present,
                                # then the 'C' locale is assumed.
                                comps = name.split(":")
                                if len(comps) > 1:
                                        locale = comps[1]
                                else:
                                        locale = "C"
                                if locale not in sum_acts:
                                        sum_acts[locale] = []
                                sum_acts[locale].append(str(act))

                        return {
                            "dependency": dep_acts,
                            "summary": sum_acts,
                        }

                self.__lock_catalog()
                try:
                        entries = {}
                        # Use the same operation time and date for all
                        # operations so that the last modification times
                        # of all catalog parts and update logs will be
                        # synchronized.
                        op_time = datetime.datetime.utcnow()

                        # Always add packages to the base catalog.
                        entry = {}
                        if metadata:
                                entry["metadata"] = metadata
                        if manifest:
                                for k, v in manifest.signatures.iteritems():
                                        entry["signature-%s" % k] = v
                        part = self.get_part(self.__BASE_PART)
                        entries[part.name] = part.add(pfmri, metadata=entry,
                            op_time=op_time)

                        if manifest:
                                # Without a manifest, only the base catalog data
                                # can be populated.

                                # Only dependency and set actions are currently
                                # used by the remaining catalog parts.
                                actions = []
                                for atype in "depend", "set":
                                        actions += manifest.gen_actions_by_type(
                                            atype)

                                gacts = group_actions(actions)
                                for ctype in gacts:
                                        for locale in gacts[ctype]:
                                                acts = gacts[ctype][locale]
                                                if not acts:
                                                        # Catalog entries only
                                                        # added if actions are
                                                        # present for this
                                                        # ctype.
                                                        continue

                                                part = self.get_part("catalog"
                                                    ".%s.%s" % (ctype, locale))
                                                entry = { "actions": acts }
                                                entries[part.name] = part.add(
                                                    pfmri, metadata=entry,
                                                    op_time=op_time)

                        self.__log_update(pfmri, CatalogUpdate.ADD, op_time,
                            entries=entries)
                finally:
                        self.__unlock_catalog()

        def append(self, src, cb=None, pfmri=None, pubs=EmptyI):
                """Appends the entries in the specified 'src' catalog to that
                of the current catalog.  The caller is responsible for ensuring
                that no duplicates exist and must call finalize() afterwards to
                to ensure consistent catalog state.  This function cannot be
                used when log_updates or read_only is enabled.

                'cb' is an optional callback function that must accept src,
                an FMRI, and entry.  Where 'src' is the source catalog the
                FMRI's entry is being copied from, and entry is the source
                catalog entry.  It must return a tuple of the form (append,
                metadata), where 'append' is a boolean value indicating if
                the specified package should be appended, and 'metadata' is
                a dict of additional metadata to store with the package's
                BASE record.

                'pfmri' is an optional FMRI of a package to append.  If not
                provided, all FMRIs in the 'src' catalog will be appended.
                This filtering is applied before any provided callback.

                'pubs' is an optional list of publisher prefixes to restrict
                the append operation to.  FRMIs that have a publisher not in
                the list will be skipped.  This filtering is applied before
                any provided callback.  If not provided, no publisher
                filtering will be applied."""

                assert not self.log_updates and not self.read_only

                self.__lock_catalog()
                try:
                        # Append operations are much slower if batch mode is
                        # not enabled.  This ensures that the current state
                        # is stored and then reset on completion or failure.
                        # Since append() is never used as part of the
                        # publication process (log_updates == True),
                        # this is safe.
                        old_batch_mode = self.batch_mode
                        self.batch_mode = True
                        self.__append(src, cb=cb, pfmri=pfmri, pubs=pubs)
                finally:
                        self.batch_mode = old_batch_mode
                        self.__unlock_catalog()

        def apply_updates(self, path):
                """Apply any CatalogUpdates available to the catalog based on
                the list returned by get_updates_needed.  The caller must
                retrieve all of the resources indicated by get_updates_needed
                and place them in the directory indicated by 'path'."""

                if not self.meta_root:
                        raise api_errors.CatalogUpdateRequirements()

                # Used to store the original time each part was modified
                # as a basis for determining whether to apply specific
                # updates.
                old_parts = self._attrs.parts
                def apply_incremental(name):
                        # Load the CatalogUpdate from the path specified.
                        # (Which is why __get_update is not used.)
                        ulog = CatalogUpdate(name, meta_root=path)
                        for pfmri, op_type, op_time, metadata in ulog.updates():
                                for pname, pdata in metadata.iteritems():
                                        part = self.get_part(pname,
                                            must_exist=True)
                                        if part is None:
                                                # Part doesn't exist; skip.
                                                continue

                                        lm = old_parts[pname]["last-modified"]
                                        if op_time <= lm:
                                                # Only add updates to the part
                                                # that occurred after the last
                                                # time it was originally
                                                # modified.
                                                continue

                                        if op_type == CatalogUpdate.ADD:
                                                part.add(pfmri, metadata=pdata,
                                                    op_time=op_time)
                                        elif op_type == CatalogUpdate.REMOVE:
                                                part.remove(pfmri,
                                                    op_time=op_time)
                                        else:
                                                raise api_errors.UnknownUpdateType(
                                                    op_type)

                def apply_full(name):
                        src = os.path.join(path, name)
                        dest = os.path.join(self.meta_root, name)
                        portable.copyfile(src, dest)

                self.__lock_catalog()
                try:
                        old_batch_mode = self.batch_mode
                        self.batch_mode = True

                        updates = self.get_updates_needed(path)
                        if updates == None:
                                # Nothing has changed, so nothing to do.
                                return

                        for name in updates:
                                if name.startswith("update."):
                                        # The provided update is an incremental.
                                        apply_incremental(name)
                                else:
                                        # The provided update is a full update.
                                        apply_full(name)

                        # Next, verify that all of the updated parts have a
                        # signature that matches the new catalog.attrs file.
                        new_attrs = CatalogAttrs(meta_root=path)
                        new_sigs = {}
                        for name, mdata in new_attrs.parts.iteritems():
                                new_sigs[name] = {}
                                for key in mdata:
                                        if not key.startswith("signature-"):
                                                continue
                                        sig = key.split("signature-")[1]
                                        new_sigs[name][sig] = mdata[key]

                        # This must be done to ensure that the catalog
                        # signature matches that of the source.
                        self.batch_mode = old_batch_mode
                        self.finalize()

                        for name, part in self.__parts.iteritems():
                                part.validate(signatures=new_sigs[name])

                        # Finally, save the catalog, and then copy the new
                        # catalog attributes file into place and reload it.
                        self.__save()
                        apply_full(self._attrs.name)

                        self._attrs = CatalogAttrs(meta_root=self.meta_root)
                        self.__set_perms()
                finally:
                        self.batch_mode = old_batch_mode
                        self.__unlock_catalog()

        def categories(self, excludes=EmptyI, pubs=EmptyI):
                """Returns a set of tuples of the form (scheme, category)
                containing the names of all categories in use by the last
                version of each unique package in the catalog on a per-
                publisher basis.

                'excludes' is a list of variants which will be used to
                determine what category actions will be checked.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                acts = self.__actions([self.SUMMARY], excludes=excludes,
                    last_version=True, pubs=pubs)
                return set((
                    sc
                    for f, acts in acts
                    for a in acts
                    if a.has_category_info()
                    for sc in a.parse_category_info()
                ))

        @property
        def created(self):
                """A UTC datetime object indicating the time the catalog was
                created."""
                return self._attrs.created

        def destroy(self):
                """Removes any on-disk files that exist for the catalog and
                discards all content."""

                for name in self._attrs.parts:
                        part = self.get_part(name)
                        part.destroy()

                for name in self._attrs.updates:
                        ulog = self.__get_update(name, cache=False)
                        ulog.destroy()

                self._attrs = CatalogAttrs(meta_root=self.meta_root,
                    sign=self.__sign)
                self.__parts = {}
                self.__updates = {}
                self._attrs.destroy()

                if not self.meta_root or not os.path.exists(self.meta_root):
                        return

                # Finally, ensure that if there are any leftover files from
                # an interrupted destroy in the past that they are removed
                # as well.
                for fname in os.listdir(self.meta_root):
                        if not fname.startswith("catalog.") and \
                            not fname.startswith("update."):
                                continue

                        pname = os.path.join(self.meta_root, fname)
                        if not os.path.isfile(pname):
                                continue

                        try:
                                portable.remove(pname)
                        except EnvironmentError, e:
                                if e.errno == errno.EACCES:
                                        raise api_errors.PermissionsException(
                                            e.filename)
                                if e.errno == errno.EROFS:
                                        raise api_errors.ReadOnlyFileSystemException(
                                            e.filename)
                                raise

        def entries(self, info_needed=EmptyI, last=False, locales=None,
            ordered=False, pubs=EmptyI):
                """A generator function that produces tuples of the format
                (fmri, metadata) as it iterates over the contents of the
                catalog (where 'metadata' is a dict containing the requested
                information).

                'metadata' always contains the following information at a
                 minimum:

                        BASE
                                'metadata' will be populated with Manifest
                                signature data, if available, using key-value
                                pairs of the form 'signature-<name>': value.

                'info_needed' is an optional list of one or more catalog
                constants indicating the types of catalog data that will
                be returned in 'metadata' in addition to the above:

                        DEPENDENCY
                                'metadata' will contain depend and set Actions
                                for package obsoletion, renaming, variants,
                                and facets stored in a list under the
                                key 'actions'.

                        SUMMARY
                                'metadata' will contain any remaining Actions
                                not listed above, such as pkg.summary,
                                pkg.description, etc. in a list under the key
                                'actions'.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the catalog has been saved since the last modifying
                operation, or finalize() has has been called, this will also be
                the newest version of the package.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.
                Note that unlike actions(), catalog entries will not lazy-load
                action data if it is missing from the catalog.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                return self.__entries(info_needed=info_needed,
                    last_version=last, locales=locales, ordered=ordered,
                    pubs=pubs)

        def entries_by_version(self, name, info_needed=EmptyI, locales=None,
            pubs=EmptyI):
                """A generator function that produces tuples of the format
                (version, entries) as it iterates over the contents of the
                the catalog, where entries is a list of tuples of the format
                (fmri, metadata) and metadata is a dict containing the
                requested information.

                'metadata' always contains the following information at a
                 minimum:

                        BASE
                                'metadata' will be populated with Manifest
                                signature data, if available, using key-value
                                pairs of the form 'signature-<name>': value.

                'info_needed' is an optional list of one or more catalog
                constants indicating the types of catalog data that will
                be returned in 'metadata' in addition to the above:

                        DEPENDENCY
                                'metadata' will contain depend and set Actions
                                for package obsoletion, renaming, variants,
                                and facets stored in a list under the
                                key 'actions'.

                        SUMMARY
                                'metadata' will contain any remaining Actions
                                not listed above, such as pkg.summary,
                                pkg.description, etc. in a list under the key
                                'actions'.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.
                        return

                if not locales:
                        locales = set(("C",))
                else:
                        locales = set(locales)

                parts = []
                if self.DEPENDENCY in info_needed:
                        part = self.get_part(self.__DEPS_PART, must_exist=True)
                        if part is not None:
                                parts.append(part)

                if self.SUMMARY in info_needed:
                        for locale in locales:
                                part = self.get_part(
                                    "%s.%s" % (self.__SUMM_PART_PFX, locale),
                                    must_exist=True)
                                if part is None:
                                        # Data not available for this
                                        # locale.
                                        continue
                                parts.append(part)

                def merge_entry(src, dest):
                        for k, v in src.iteritems():
                                if k == "actions":
                                        dest.setdefault(k, [])
                                        dest[k] += v
                                elif k != "version":
                                        dest[k] = v

                for ver, entries in base.entries_by_version(name, pubs=pubs):
                        nentries = []
                        for f, bentry in entries:
                                mdata = {}
                                merge_entry(bentry, mdata)
                                for part in parts:
                                        entry = part.get_entry(f)
                                        if entry is None:
                                                # Part doesn't have this FMRI,
                                                # so skip it.
                                                continue
                                        merge_entry(entry, mdata)
                                nentries.append((f, mdata))
                        yield ver, nentries

        def entry_actions(self, info_needed, excludes=EmptyI, cb=None,
            last=False, locales=None, ordered=False, pubs=EmptyI):
                """A generator function that produces tuples of the format
                ((pub, stem, version), entry, actions) as it iterates over
                the contents of the catalog (where 'actions' is a generator
                that returns the Actions corresponding to the requested
                information).

                If the catalog doesn't contain any action data for the package
                entry, and manifest_cb was defined at Catalog creation time,
                the action data will be lazy-loaded by the actions generator;
                otherwise it will return an empty iterator.  This means that
                the manifest_cb will be executed even for packages that don't
                actually have any actions corresponding to info_needed.  For
                example, if a package doesn't have any dependencies, the
                manifest_cb will still be executed.  This was considered a
                reasonable compromise as packages are generally expected to
                have DEPENDENCY and SUMMARY information.

                'excludes' is a list of variants which will be used to determine
                what should be allowed by the actions generator in addition to
                what is specified by 'info_needed'.

                'cb' is an optional callback function that will be executed for
                each package before its action data is retrieved. It must accept
                two arguments: 'pkg' and 'entry'.  'pkg' is an FMRI object and
                'entry' is the dictionary structure of the catalog entry for the
                package.  If the callback returns False, then the entry will not
                be included in the results.  This can significantly improve
                performance by avoiding action data retrieval for results that
                will not be used.

                'info_needed' is a set of one or more catalog constants
                indicating the types of catalog data that will be returned
                in 'actions' in addition to the above:

                        DEPENDENCY
                                Depend and set Actions for package obsoletion,
                                renaming, variants.

                        SUMMARY
                                Any remaining set Actions not listed above, such
                                as pkg.summary, pkg.description, etc.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the catalog has been saved since the last modifying
                operation, or finalize() has has been called, this will also be
                the newest version of the package.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pfmri' is an optional FMRI to limit the returned results to.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                for r, entry in self.__entries(cb=cb, info_needed=info_needed,
                    locales=locales, last_version=last, ordered=ordered,
                    pubs=pubs, tuples=True):
                        if "actions" in entry:
                                yield (r, entry,
                                    self.__gen_actions(r, entry["actions"],
                                    excludes))
                        elif self.__manifest_cb:
                                pub, stem, ver = r
                                f = fmri.PkgFmri("%s@%s" % (stem, ver),
                                    publisher=pub)
                                yield (r, entry,
                                    self.__gen_lazy_actions(f, info_needed,
                                    locales, excludes))
                        else:
                                yield r, entry, EmptyI

        @property
        def exists(self):
                """A boolean value indicating whether the Catalog exists
                on-disk."""

                # If the Catalog attrs file exists on-disk,
                # then the catalog does.
                attrs = self._attrs
                return attrs.exists

        def finalize(self, pfmris=None, pubs=None):
                """This function re-sorts the contents of the Catalog so that
                version entries are in the correct order and sets the package
                counts for the Catalog based on its current contents.

                'pfmris' is an optional set of FMRIs that indicate what package
                entries have been changed since this function was last called.
                It is used to optimize the finalization process.

                'pubs' is an optional set of publisher prefixes that indicate
                what publisher has had package entries changed.  It is used
                to optimize the finalization process.  This option has no effect
                if 'pfmris' is also provided."""

                return self.__finalize(pfmris=pfmris, pubs=pubs)

        def fmris(self, last=False, objects=True, ordered=False, pubs=EmptyI):
                """A generator function that produces FMRIs as it iterates
                over the contents of the catalog.

                'last' is a boolean value that indicates only the last FMRI
                for each package on a per-publisher basis should be returned.
                As long as the catalog has been saved since the last modifying
                operation, or finalize() has has been called, this will also be
                the newest version of the package.

                'objects' is an optional boolean value indicating whether
                FMRIs should be returned as FMRI objects or as strings.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.

                        # This construction is necessary to get python to
                        # return no results properly to callers expecting
                        # a generator function.
                        return iter(())
                return base.fmris(last=last, objects=objects, ordered=ordered,
                    pubs=pubs)

        def fmris_by_version(self, name, pubs=EmptyI):
                """A generator function that produces tuples of (version,
                fmris), where fmris is a of the fmris related to the
                version, for the given package name.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.

                        # This construction is necessary to get python to
                        # return no results properly to callers expecting
                        # a generator function.
                        return iter(())
                return base.fmris_by_version(name, pubs=pubs)

        def get_entry(self, pfmri, info_needed=EmptyI, locales=None):
                """Returns a dict containing the metadata for the specified
                FMRI containing the requested information.  If the specified
                FMRI does not exist in the catalog, a value of None will be
                returned.

                'metadata' always contains the following information at a
                 minimum:

                        BASE
                                'metadata' will be populated with Manifest
                                signature data, if available, using key-value
                                pairs of the form 'signature-<name>': value.

                'info_needed' is an optional list of one or more catalog
                constants indicating the types of catalog data that will
                be returned in 'metadata' in addition to the above:

                        DEPENDENCY
                                'metadata' will contain depend and set Actions
                                for package obsoletion, renaming, variants,
                                and facets stored in a list under the
                                key 'actions'.

                        SUMMARY
                                'metadata' will contain any remaining Actions
                                not listed above, such as pkg.summary,
                                pkg.description, etc. in a list under the key
                                'actions'.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.
                """

                def merge_entry(src, dest):
                        for k, v in src.iteritems():
                                if k == "actions":
                                        dest.setdefault(k, [])
                                        dest[k] += v
                                elif k != "version":
                                        dest[k] = v

                parts = []
                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        return

                if not locales:
                        locales = set(("C",))
                else:
                        locales = set(locales)

                # Always attempt to retrieve the BASE entry as FMRIs
                # must be present in the BASE catalog part.
                mdata = {}
                bentry = base.get_entry(pfmri)
                if bentry is None:
                        return
                merge_entry(bentry, mdata)

                if self.DEPENDENCY in info_needed:
                        part = self.get_part(self.__DEPS_PART,
                            must_exist=True)
                        if part is not None:
                                parts.append(part)

                if self.SUMMARY in info_needed:
                        for locale in locales:
                                part = self.get_part(
                                    "%s.%s" % (self.__SUMM_PART_PFX, locale),
                                    must_exist=True)
                                if part is None:
                                        # Data not available for this
                                        # locale.
                                        continue
                                parts.append(part)

                for part in parts:
                        entry = part.get_entry(pfmri)
                        if entry is None:
                                # Part doesn't have this FMRI,
                                # so skip it.
                                continue
                        merge_entry(entry, mdata)
                return mdata

        def get_entry_actions(self, pfmri, info_needed, excludes=EmptyI,
            locales=None):
                """A generator function that produces Actions as it iterates
                over the catalog entry of the specified FMRI corresponding to
                the requested information).  If the catalog doesn't contain
                any action data for the package entry, and manifest_cb was
                defined at Catalog creation time, the action data will be
                lazy-loaded by the actions generator; otherwise it will
                return an empty iterator.

                'excludes' is a list of variants which will be used to determine
                what should be allowed by the actions generator in addition to
                what is specified by 'info_needed'.  If not provided, only
                'info_needed' will determine what actions are returned.

                'info_needed' is a set of one or more catalog constants
                indicating the types of catalog data that will be returned
                in 'actions' in addition to the above:

                        DEPENDENCY
                                Depend and set Actions for package obsoletion,
                                renaming, variants.

                        SUMMARY
                                Any remaining set Actions not listed above, such
                                as pkg.summary, pkg.description, etc.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.
                """

                assert info_needed
                if not locales:
                        locales = set(("C",))
                else:
                        locales = set(locales)

                entry = self.get_entry(pfmri, info_needed=info_needed,
                    locales=locales)
                if entry is None:
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())

                if "actions" in entry:
                        return self.__gen_actions(pfmri, entry["actions"],
                            excludes)
                elif self.__manifest_cb:
                        return self.__gen_lazy_actions(pfmri, info_needed,
                            locales, excludes)
                else:
                        return EmptyI

        def get_entry_all_variants(self, pfmri):
                """A generator function that yields tuples of the format
                (var_name, variants); where var_name is the name of the
                variant and variants is a list of the variants for that
                name."""

                info_needed = [self.DEPENDENCY]
                entry = self.get_entry(pfmri, info_needed=info_needed)
                if entry is None:
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())

                if "actions" in entry:
                        actions = self.__gen_actions(pfmri, entry["actions"])
                elif self.__manifest_cb:
                        actions = self.__gen_lazy_actions(pfmri,
                            info_needed)
                else:
                        return

                for a in actions:
                        if a.name != "set":
                                continue

                        attr_name = a.attrs["name"]
                        if not attr_name.startswith("variant"):
                                continue
                        yield attr_name, a.attrs["value"]

        def get_entry_signatures(self, pfmri):
                """A generator function that yields tuples of the form (sig,
                value) where 'sig' is the name of the signature, and 'value' is
                the raw catalog value for the signature.  Please note that the
                data type of 'value' is dependent on the signature, so it may
                be a string, list, dict, etc."""

                entry = self.get_entry(pfmri)
                if entry is None:
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())
                return (
                    (k.split("signature-")[1], v)
                    for k, v in entry.iteritems()
                    if k.startswith("signature-")
                )

        def get_entry_variants(self, pfmri, name):
                """A generator function that returns the variants for the
                specified variant name.  If no variants exist for the
                specified name, None will be returned."""

                for var_name, values in self.get_entry_all_variants(pfmri):
                        if var_name == name:
                                # A package can only have one set of values
                                # for a single variant name, so return it.
                                return values
                return None

        def gen_packages(self, collect_attrs=False, matched=None,
            patterns=EmptyI, pubs=EmptyI, unmatched=None, return_fmris=False):
                """A generator function that produces tuples of the form:

                    (
                        (
                            pub,    - (string) the publisher of the package
                            stem,   - (string) the name of the package
                            version - (string) the version of the package
                        ),
                        states,     - (list) states
                        attributes  - (dict) package attributes
                    )

                Results are always sorted by stem, publisher, and then in
                descending version order.

                'collect_attrs' is an optional boolean that indicates whether
                all package attributes should be collected and returned in the
                fifth element of the return tuple.  If False, that element will
                be an empty dictionary.

                'matched' is an optional set to add matched patterns to.

                'patterns' is an optional list of FMRI wildcard strings to
                filter results by.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to.

                'unmatched' is an optional set to add unmatched patterns to.

                'return_fmris' is an optional boolean value that indicates that
                an FMRI object should be returned in place of the (pub, stem,
                ver) tuple that is normally returned."""

                brelease = "5.11"

                # Each pattern in patterns can be a partial or full FMRI, so
                # extract the individual components for use in filtering.
                newest = False
                illegals = []
                pat_tuples = {}
                latest_pats = set()
                seen = set()
                npatterns = set()
                for pat, error, pfmri, matcher in self.__parse_fmri_patterns(
                    patterns):
                        if error:
                                illegals.append(error)
                                continue

                        # Duplicate patterns are ignored.
                        sfmri = str(pfmri)
                        if sfmri in seen:
                                # A different form of the same pattern
                                # was specified already; ignore this
                                # one (e.g. pkg:/network/ping,
                                # /network/ping).
                                continue

                        # Track used patterns.
                        seen.add(sfmri)
                        npatterns.add(pat)

                        if getattr(pfmri.version, "match_latest", None):
                                latest_pats.add(pat)
                        pat_tuples[pat] = (pfmri.tuple(), matcher)

                patterns = npatterns
                del npatterns, seen

                if illegals:
                        raise api_errors.PackageMatchErrors(illegal=illegals)

                # Keep track of listed stems for all other packages on a
                # per-publisher basis.
                nlist = collections.defaultdict(int)

                # Track matching patterns.
                matched_pats = set()
                pkg_matching_pats = None

                # Need dependency and summary actions.
                cat_info = frozenset([self.DEPENDENCY, self.SUMMARY])

                for t, entry, actions in self.entry_actions(cat_info,
                    ordered=True, pubs=pubs):
                        pub, stem, ver = t

                        omit_ver = False
                        omit_package = None

                        pkg_stem = "!".join((pub, stem))
                        if newest and pkg_stem in nlist:
                                # A newer version has already been listed, so
                                # any additional entries need to be marked for
                                # omission before continuing.
                                omit_package = True
                        else:
                                nlist[pkg_stem] += 1

                        if matched is not None or unmatched is not None:
                                pkg_matching_pats = set()
                        if not omit_package:
                                ever = None
                                for pat in patterns:
                                        (pat_pub, pat_stem, pat_ver), matcher = \
                                            pat_tuples[pat]

                                        if pat_pub is not None and \
                                            pub != pat_pub:
                                                # Publisher doesn't match.
                                                if omit_package is None:
                                                        omit_package = True
                                                continue

                                        if matcher == fmri.exact_name_match:
                                                if pat_stem != stem:
                                                        # Stem doesn't match.
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        continue
                                        elif matcher == fmri.fmri_match:
                                                if not ("/" + stem).endswith(
                                                    "/" + pat_stem):
                                                        # Stem doesn't match.
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        continue
                                        elif matcher == fmri.glob_match:
                                                if not fnmatch.fnmatchcase(stem,
                                                    pat_stem):
                                                        # Stem doesn't match.
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        continue

                                        if pat_ver is not None:
                                                if ever is None:
                                                        # Avoid constructing a
                                                        # version object more
                                                        # than once for each
                                                        # entry.
                                                        ever = pkg.version.Version(ver,
                                                            brelease)
                                                if not ever.is_successor(pat_ver,
                                                    pkg.version.CONSTRAINT_AUTO):
                                                        if omit_package is None:
                                                                omit_package = \
                                                                    True
                                                        omit_ver = True
                                                        continue

                                        if pat in latest_pats and \
                                            nlist[pkg_stem] > 1:
                                                # Package allowed by pattern,
                                                # but isn't the "latest"
                                                # version.
                                                if omit_package is None:
                                                        omit_package = True
                                                omit_ver = True
                                                continue

                                        # If this entry matched at least one
                                        # pattern, then ensure it is returned.
                                        omit_package = False
                                        if (matched is None and
                                            unmatched is None):
                                                # It's faster to stop as soon
                                                # as a match is found.
                                                break

                                        # If caller has requested other match
                                        # cases be returned, then all patterns
                                        # must be tested for every entry.  This
                                        # is slower, so only done if necessary.
                                        pkg_matching_pats.add(pat)

                        if omit_package:
                                # Package didn't match critera; skip it.
                                continue

                        # Collect attribute data if requested.
                        summ = None

                        omit_var = False
                        states = set()
                        if collect_attrs:
                                ddm = lambda: collections.defaultdict(list)
                                attrs = collections.defaultdict(ddm)
                        else:
                                attrs = EmptyDict

                        try:
                                for a in actions:
                                        if a.name != "set":
                                                continue

                                        atname = a.attrs["name"]
                                        atvalue = a.attrs["value"]
                                        if collect_attrs:
                                                atvlist = a.attrlist("value")

                                                # XXX Need to describe this data
                                                # structure sanely somewhere.
                                                mods = frozenset(
                                                    (k, frozenset(a.attrlist(k)))
                                                    for k in a.attrs.iterkeys()
                                                    if k not in ("name", "value")
                                                )
                                                attrs[atname][mods].extend(
                                                    atvlist)

                                        if atname == "pkg.summary":
                                                summ = atvalue
                                                continue

                                        if atname == "description":
                                                if summ is None:
                                                        # Historical summary
                                                        # field.
                                                        summ = atvalue
                                                        collect_attrs and \
                                                            attrs["pkg.summary"] \
                                                            [mods]. \
                                                            extend(atvlist)
                                                continue

                                        if atname == "pkg.renamed":
                                                if atvalue == "true":
                                                        states.add(
                                                            self.PKG_STATE_RENAMED)
                                                continue
                                        if atname == "pkg.obsolete":
                                                if atvalue == "true":
                                                        states.add(
                                                            self.PKG_STATE_OBSOLETE)
                                                continue
                        except api_errors.InvalidPackageErrors:
                                # Ignore errors for packages that have invalid
                                # or unsupported metadata.
                                states.add(self.PKG_STATE_UNSUPPORTED)

                        if omit_package:
                                # Package didn't match criteria; skip it.
                                if omit_ver and nlist[pkg_stem] == 1:
                                        del nlist[pkg_stem]
                                continue

                        if matched is not None or unmatched is not None:
                                # Only after all other filtering has been
                                # applied are the patterns that the package
                                # matched considered "matching".
                                matched_pats.update(pkg_matching_pats)

                        # Return the requested package data.
                        if return_fmris:
                                pfmri = fmri.PkgFmri("%s@%s" % (stem, ver),
                                    build_release=brelease, publisher=pub)
                                yield (pfmri, states, attrs)
                        else:
                                yield (t, states, attrs)

                if matched is not None:
                        # Caller has requested that matched patterns be
                        # returned.
                        matched.update(matched_pats)
                if unmatched is not None:
                        # Caller has requested that unmatched patterns be
                        # returned.
                        unmatched.update(set(pat_tuples.keys()) - matched_pats)

        def get_matching_fmris(self, patterns, raise_unmatched=True):
                """Given a user-specified list of FMRI pattern strings, return
                a tuple of ('matching', 'references', 'unmatched'), where
                matching is a dict of matching fmris, references is a dict of
                the patterns indexed by matching FMRI, and unmatched is a set of
                the patterns that did not match any FMRIs respectively:

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

                set(['unmatched1', 'unmatchedN'])

                'patterns' is the list of package patterns to match.

                'raise_unmatched' is an optional boolean indicating that an
                exception should be raised if any patterns are not matched.

                Constraint used is always AUTO as per expected UI behavior when
                determining successor versions.

                Note that patterns starting w/ pkg:/ require an exact match;
                patterns containing '*' will using fnmatch rules; the default
                trailing match rules are used for remaining patterns.

                Exactly duplicated patterns are ignored.

                Routine raises PackageMatchErrors if errors occur: it is
                illegal to specify multiple different patterns that match the
                same package name.  Only patterns that contain wildcards are
                allowed to match multiple packages.
                """

                # problems we check for
                illegals = []
                unmatched = set()
                multimatch = []
                multispec = []
                pat_data = []
                wildcard_patterns = set()

                brelease = "5.11"

                # Each pattern in patterns can be a partial or full FMRI, so
                # extract the individual components for use in filtering.
                latest_pats = set()
                seen = set()
                npatterns = set()
                for pat, error, pfmri, matcher in self.__parse_fmri_patterns(
                    patterns):
                        if error:
                                illegals.append(error)
                                continue

                        # Duplicate patterns are ignored.
                        sfmri = str(pfmri)
                        if sfmri in seen:
                                # A different form of the same pattern
                                # was specified already; ignore this
                                # one (e.g. pkg:/network/ping,
                                # /network/ping).
                                continue

                        # Track used patterns.
                        seen.add(sfmri)
                        npatterns.add(pat)
                        if "*" in pfmri.pkg_name or "?" in pfmri.pkg_name:
                                wildcard_patterns.add(pat)

                        if getattr(pfmri.version, "match_latest", None):
                                latest_pats.add(pat)
                        pat_data.append((matcher, pfmri))

                patterns = npatterns
                del npatterns, seen

                if illegals:
                        raise api_errors.PackageMatchErrors(illegal=illegals)

                # Create a dictionary of patterns, with each value being a
                # dictionary of pkg names & fmris that match that pattern.
                ret = dict(zip(patterns, [dict() for i in patterns]))

                for name in self.names():
                        for pat, (matcher, pfmri) in zip(patterns, pat_data):
                                pub = pfmri.publisher
                                version = pfmri.version
                                if not matcher(name, pfmri.pkg_name):
                                        continue # name doesn't match
                                for ver, entries in self.entries_by_version(name):
                                        if version and not ver.is_successor(
                                            version, pkg.version.CONSTRAINT_AUTO):
                                                continue # version doesn't match
                                        for f, metadata in entries:
                                                fpub = f.publisher
                                                if pub and pub != fpub:
                                                        # specified pubs
                                                        # conflict
                                                        continue 
                                                ret[pat].setdefault(f.pkg_name,
                                                    []).append(f)

                # Discard all but the newest version of each match.
                if latest_pats:
                        # Rebuild ret based on latest version of every package.
                        latest = {}
                        nret = {}
                        for p in patterns:
                                if p not in latest_pats or not ret[p]:
                                        nret[p] = ret[p]
                                        continue

                                nret[p] = {}
                                for pkg_name in ret[p]:
                                        nret[p].setdefault(pkg_name, [])
                                        for f in ret[p][pkg_name]:
                                                nver = latest.get(f.pkg_name,
                                                    None)
                                                if nver > f.version:
                                                        # Not the newest.
                                                        continue
                                                if nver == f.version:
                                                        # Allow for multiple
                                                        # FMRIs of the same
                                                        # latest version.
                                                        nret[p][pkg_name].append(
                                                            f)
                                                        continue

                                                latest[f.pkg_name] = f.version
                                                nret[p][pkg_name] = [f]

                        # Assign new version of ret and discard latest list.
                        ret = nret
                        del latest

                # Determine match failures.
                matchdict = {}
                for p in patterns:
                        l = len(ret[p])
                        if l == 0: # no matches at all
                                unmatched.add(p)
                        elif l > 1 and p not in wildcard_patterns:
                                # multiple matches
                                multimatch.append((p, [
                                    ret[p][n][0].get_pkg_stem()
                                    for n in ret[p]
                                ]))
                        else:
                                # single match or wildcard
                                for k in ret[p].keys():
                                        # for each matching package name
                                        matchdict.setdefault(k, []).append(p)

                for name in matchdict:
                        if len(matchdict[name]) > 1:
                                # different pats, same pkg
                                multispec.append(tuple([name] +
                                    matchdict[name]))

                if (raise_unmatched and unmatched) or multimatch or multispec:
                        raise api_errors.PackageMatchErrors(
                            multiple_matches=multimatch,
                            multispec=multispec,
                            unmatched_fmris=unmatched)

                # merge patterns together now that there are no conflicts
                proposed_dict = {}
                for d in ret.values():
                        proposed_dict.update(d)

                # construct references so that we can know which pattern
                # generated which fmris...
                references = dict([
                    (f, p)
                    for p in ret.keys()
                    for flist in ret[p].values()
                    for f in flist
                ])

                return proposed_dict, references, unmatched

        def get_package_counts_by_pub(self):
                """Returns a generator of tuples of the form (pub,
                package_count, package_version_count).  'pub' is the publisher
                prefix, 'package_count' is the number of unique packages for the
                publisher, and 'package_version_count' is the number of unique
                package versions for the publisher.
                """

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.

                        # This construction is necessary to get python to
                        # return no results properly to callers expecting
                        # a generator function.
                        return iter(())
                return base.get_package_counts_by_pub()

        def get_part(self, name, must_exist=False):
                """Returns the CatalogPart object for the named catalog part.

                'must_exist' is an optional boolean value that indicates that
                the catalog part must already exist in-memory or on-disk, if
                not a value of None will be returned."""

                # First, check if the part has already been cached, and if so,
                # return it.
                part = self.__parts.get(name, None)
                if part is not None:
                        return part
                elif not self.meta_root and must_exist:
                        return

                # If the caller said the part must_exist, then it must already
                # be part of the catalog attributes to be valid.
                aparts = self._attrs.parts
                if must_exist and name not in aparts:
                        return

                # Next, since the part hasn't been cached, create an object
                # for it and add it to catalog attributes.
                part = CatalogPart(name, meta_root=self.meta_root,
                    ordered=not self.__batch_mode, sign=self.__sign)
                if must_exist and self.meta_root and not part.exists:
                        # This is a double-check for the client case where
                        # there is a part that is known to the catalog but
                        # that the client has purposefully not retrieved.
                        # (Think locale specific data.)
                        return

                self.__parts[name] = part

                if name not in aparts:
                        # Add a new entry to the catalog attributes for this new
                        # part since it didn't exist previously.
                        aparts[name] = {
                            "last-modified": part.last_modified
                        }
                return part

        def get_updates_needed(self, path):
                """Returns a list of the catalog files needed to update
                the existing catalog parts, based on the contents of the
                catalog.attrs file in the directory indicated by 'path'.
                A value of None will be returned if the the catalog has
                not been modified, while an empty list will be returned
                if no catalog parts need to be updated, but the catalog
                itself has changed."""

                new_attrs = CatalogAttrs(meta_root=path)
                if not new_attrs.exists:
                        # No updates needed (not even to attrs), so return None.
                        return None

                old_attrs = self._attrs
                if old_attrs.created != new_attrs.created:
                        # It's very likely that the catalog has been recreated
                        # or this is a completely different catalog than was
                        # expected.  In either case, an update isn't possible.
                        raise api_errors.BadCatalogUpdateIdentity(path)

                if new_attrs.last_modified == old_attrs.last_modified:
                        # No updates needed (not even to attrs), so return None.
                        return None

                # First, verify that all of the catalog parts the client has
                # still exist.  If they no longer exist, the catalog is no
                # longer valid and cannot be updated.
                parts = {}
                incremental = True
                for name in old_attrs.parts:
                        if name not in new_attrs.parts:
                                raise api_errors.BadCatalogUpdateIdentity(path)

                        old_lm = old_attrs.parts[name]["last-modified"]
                        new_lm = new_attrs.parts[name]["last-modified"]

                        if new_lm == old_lm:
                                # Part hasn't changed.
                                continue
                        elif new_lm < old_lm:
                                raise api_errors.ObsoleteCatalogUpdate(path)

                        # The last component of the update name is the locale.
                        locale = name.split(".", 2)[2]

                        # Now check to see if an update log is still offered for
                        # the last time this catalog part was updated.  If it
                        # does not, then an incremental update cannot be safely
                        # performed since updates may be missing.
                        logdate = datetime_to_update_ts(old_lm)
                        logname = "update.%s.%s" % (logdate, locale)

                        if logname not in new_attrs.updates:
                                incremental = False

                        parts.setdefault(locale, set())
                        parts[locale].add(name)

                # XXX in future, add current locale to this.  For now, just
                # ensure that all of the locales of parts that were changed
                # and exist on-disk are included.
                locales = set(("C",))
                locales.update(set(parts.keys()))

                # Now determine if there are any new parts for this locale that
                # this version of the API knows how to use that the client
                # doesn't already have.
                for name in new_attrs.parts:
                        if name in parts or name in old_attrs.parts:
                                continue

                        # The last component of the name is the locale.
                        locale = name.split(".", 2)[2]
                        if locale not in locales:
                                continue

                        # Currently, only these parts are used by the client,
                        # so only they need to be retrieved.
                        if name == self.__BASE_PART or \
                            name == self.__DEPS_PART or \
                            name.startswith(self.__SUMM_PART_PFX):
                                incremental = False

                                # If a new part has been added for the current
                                # locale, then incremental updates can't be
                                # performed since updates for this locale can
                                # only be applied to parts that already exist.
                                parts.setdefault(locale, set())
                                parts[locale].add(name)

                if not parts:
                        # No updates needed to catalog parts on-disk, but
                        # catalog has changed.
                        return []
                elif not incremental:
                        # Since an incremental update cannot be performed,
                        # just return the updated parts for retrieval.
                        updates = set()
                        for locale in parts:
                                updates.update(parts[locale])
                        return updates

                # Finally, determine the update logs needed based on the catalog
                # parts that need updating on a per-locale basis.
                updates = set()
                for locale in parts:
                        # Determine the newest catalog part for a given locale,
                        # this will be used to determine which update logs are
                        # needed for an incremental update.
                        last_lm = None
                        for name in parts[locale]:
                                if name not in old_attrs.parts:
                                        continue

                                lm = old_attrs.parts[name]["last-modified"]
                                if not last_lm or lm > last_lm:
                                        last_lm = lm

                        for name, uattrs in new_attrs.updates.iteritems():
                                up_lm = uattrs["last-modified"]

                                # The last component of the update name is the
                                # locale.
                                up_locale = name.split(".", 2)[2]

                                if not up_locale == locale:
                                        # This update log doesn't apply to the
                                        # locale being evaluated for updates.
                                        continue

                                if up_lm <= last_lm:
                                        # Older or same as newest catalog part
                                        # for this locale; so skip.
                                        continue

                                # If this updatelog was changed after the
                                # newest catalog part for this locale, then
                                # it is needed to update one or more catalog
                                # parts for this locale.
                                updates.add(name)

                # Ensure updates are in chronological ascending order.
                return sorted(updates)

        def names(self, pubs=EmptyI):
                """Returns a set containing the names of all the packages in
                the Catalog.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.
                        return set()
                return base.names(pubs=pubs)

        @property
        def package_count(self):
                """The number of unique packages in the catalog."""
                return self._attrs.package_count

        @property
        def package_version_count(self):
                """The number of unique package versions in the catalog."""
                return self._attrs.package_version_count

        @property
        def parts(self):
                """A dict containing the list of CatalogParts that the catalog
                is composed of along with information about each part."""

                return self._attrs.parts

        def pkg_names(self, pubs=EmptyI):
                """A generator function that produces package tuples of the form
                (pub, stem) as it iterates over the contents of the catalog.

                'pubs' is an optional list that contains the prefixes of the
                publishers to restrict the results to."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.

                        # This construction is necessary to get python to
                        # return no results properly to callers expecting
                        # a generator function.
                        return iter(())
                return base.pkg_names(pubs=pubs)

        def publishers(self):
                """Returns a set containing the prefixes of all the publishers
                in the Catalog."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.
                        return set()
                return set(p for p in base.publishers())

        def remove_package(self, pfmri):
                """Remove a package and its metadata."""

                assert not self.read_only

                self.__lock_catalog()
                try:
                        # The package has to be removed from every known part.
                        entries = {}

                        # Use the same operation time and date for all
                        # operations so that the last modification times
                        # of all catalog parts and update logs will be
                        # synchronized.
                        op_time = datetime.datetime.utcnow()

                        for name in self._attrs.parts:
                                part = self.get_part(name)
                                if part is None:
                                        continue

                                pkg_entry = part.get_entry(pfmri)
                                if pkg_entry is None:
                                        if name == self.__BASE_PART:
                                                # Entry should exist in at least
                                                # the base part.
                                                raise api_errors.UnknownCatalogEntry(
                                                    pfmri.get_fmri())
                                        # Skip; package's presence is optional
                                        # in other parts.
                                        continue

                                part.remove(pfmri, op_time=op_time)
                                if self.log_updates:
                                        entries[part.name] = pkg_entry

                        self.__log_update(pfmri, CatalogUpdate.REMOVE, op_time,
                            entries=entries)
                finally:
                        self.__unlock_catalog()

        def save(self):
                """Finalize current state and save to file if possible."""

                self.__lock_catalog()
                try:
                        self.__save()
                finally:
                        self.__unlock_catalog()

        @property
        def signatures(self):
                """Returns a dict of the files the catalog is composed of along
                with the last known signatures of each if they are available."""

                attrs = self._attrs
                sigs = {
                    attrs.name: attrs.signatures
                }

                for items in (attrs.parts, attrs.updates):
                        for name in items:
                                entry = sigs[name] = {}
                                for k in items[name]:
                                        try:
                                                sig = k.split("signature-")[1]
                                                entry[sig] = items[name][k]
                                        except IndexError:
                                                # Not a signature entry.
                                                continue
                return sigs

        def tuples(self, last=False, ordered=False, pubs=EmptyI):
                """A generator function that produces FMRI tuples as it
                iterates over the contents of the catalog.

                'last' is a boolean value that indicates only the last FMRI
                tuple for each package on a per-publisher basis should be
                returned.  As long as the catalog has been saved since the
                last modifying operation, or finalize() has has been called,
                this will also be the newest version of the package.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        # Catalog contains nothing.

                        # This construction is necessary to get python to
                        # return no results properly to callers expecting
                        # a generator function.
                        return iter(())
                return base.tuples(last=last, ordered=ordered, pubs=pubs)

        def tuple_entries(self, info_needed=EmptyI, last=False, locales=None,
            ordered=False, pubs=EmptyI):
                """A generator function that produces tuples of the format
                ((pub, stem, version), entry, actions) as it iterates over
                the contents of the catalog (where 'metadata' is a dict
                containing the requested information).

                'metadata' always contains the following information at a
                 minimum:

                        BASE
                                'metadata' will be populated with Manifest
                                signature data, if available, using key-value
                                pairs of the form 'signature-<name>': value.

                'info_needed' is an optional list of one or more catalog
                constants indicating the types of catalog data that will
                be returned in 'metadata' in addition to the above:

                        DEPENDENCY
                                'metadata' will contain depend and set Actions
                                for package obsoletion, renaming, variants,
                                and facets stored in a list under the
                                key 'actions'.

                        SUMMARY
                                'metadata' will contain any remaining Actions
                                not listed above, such as pkg.summary,
                                pkg.description, etc. in a list under the key
                                'actions'.

                'last' is a boolean value that indicates only the last entry
                for each package on a per-publisher basis should be returned.
                As long as the catalog has been saved since the last modifying
                operation, or finalize() has has been called, this will also be
                the newest version of the package.

                'locales' is an optional set of locale names for which Actions
                should be returned.  The default is set(('C',)) if not provided.
                Note that unlike actions(), catalog entries will not lazy-load
                action data if it is missing from the catalog.

                'ordered' is an optional boolean value that indicates that
                results should sorted by stem and then by publisher and
                be in descending version order.  If False, results will be
                in a ascending version order on a per-publisher, per-stem
                basis.

                'pubs' is an optional list of publisher prefixes to restrict
                the results to."""

                return self.__entries(info_needed=info_needed,
                    locales=locales, last_version=last, ordered=ordered,
                    pubs=pubs, tuples=True)

        @property
        def updates(self):
                """A dict containing the list of known updates for the catalog
                along with information about each update."""

                return self._attrs.updates

        def update_entry(self, metadata, pfmri=None, pub=None, stem=None,
            ver=None):
                """Updates the metadata stored in a package's BASE catalog
                record for the specified package.  Cannot be used when read_only
                or log_updates is enabled; should never be used with a Catalog
                intended for incremental update usage.

                'metadata' must be a dict of additional metadata to store with
                the package's BASE record.

                'pfmri' is the FMRI of the package to update the entry for.

                'pub' is the publisher of the package.

                'stem' is the stem of the package.

                'ver' is the version string of the package.

                'pfmri' or 'pub', 'stem', and 'ver' must be provided.
                """

                assert pfmri or (pub and stem and ver)
                assert not self.log_updates and not self.read_only

                base = self.get_part(self.__BASE_PART, must_exist=True)
                if base is None:
                        if not pfmri:
                                pfmri = fmri.PkgFmri("%s@%s" % (stem, ver),
                                    publisher=pub)
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())

                # get_entry returns the actual catalog entry, so updating it
                # simply requires reassignment.
                entry = base.get_entry(pfmri=pfmri, pub=pub, stem=stem, ver=ver)
                if entry is None:
                        if not pfmri:
                                pfmri = fmri.PkgFmri("%s@%s" % (stem, ver),
                                    publisher=pub)
                        raise api_errors.UnknownCatalogEntry(pfmri.get_fmri())
                if metadata is None:
                        if "metadata" in entry:
                                del entry["metadata"]
                        return
                entry["metadata"] = metadata

                op_time = datetime.datetime.utcnow()
                attrs = self._attrs
                attrs.last_modified = op_time
                attrs.parts[base.name] = {
                    "last-modified": op_time
                }
                base.last_modified = op_time

        def validate(self):
                """Verifies whether the signatures for the contents of the
                catalog match the current signature data.  Raises the
                exception named 'BadCatalogSignatures' on failure."""

                self._attrs.validate()

                def get_sigs(mdata):
                        sigs = {}
                        for key in mdata:
                                if not key.startswith("signature-"):
                                        continue
                                sig = key.split("signature-")[1]
                                sigs[sig] = mdata[key]
                        if not sigs:
                                # Allow validate() to perform its own fallback
                                # logic if signature data isn't available.
                                return None
                        return sigs

                for name, mdata in self._attrs.parts.iteritems():
                        part = self.get_part(name, must_exist=True)
                        if part is None:
                                # Part does not exist; no validation needed.
                                continue
                        part.validate(signatures=get_sigs(mdata))

                for name, mdata in self._attrs.updates.iteritems():
                        ulog = self.__get_update(name, cache=False,
                            must_exist=True)
                        if ulog is None:
                                # Update does not exist; no validation needed.
                                continue
                        ulog.validate(signatures=get_sigs(mdata))

        batch_mode = property(__get_batch_mode, __set_batch_mode)
        last_modified = property(__get_last_modified, __set_last_modified,
            doc="A UTC datetime object indicating the last time the catalog "
            "was modified.")
        meta_root = property(__get_meta_root, __set_meta_root)
        sign = property(__get_sign, __set_sign)
        version = property(__get_version, __set_version)


# Methods used by external callers
def verify(filename):
        """Convert the catalog part named by filename into the correct
        type of Catalog object and then call its validate method to ensure
        that is contents are self-consistent."""

        path, fn = os.path.split(filename)
        catobj = None

        if fn.startswith("catalog"):
                if fn.endswith("attrs"):
                        catobj = CatalogAttrs(meta_root=path)
                else:
                        catobj = CatalogPart(fn, meta_root=path)
        elif fn.startswith("update"):
                catobj = CatalogUpdate(fn, meta_root=path)
        else:
                # Unrecognized.
                raise api_errors.UnrecognizedCatalogPart(fn)

        # With the else case above, this should never be None.
        assert catobj

        catobj.validate()

# Methods used by Catalog classes.
def datetime_to_ts(dt):
        """Take datetime object dt, and convert it to a ts in ISO-8601
        format. """

        return dt.isoformat()

def datetime_to_basic_ts(dt):
        """Take datetime object dt, and convert it to a ts in ISO-8601
        basic format. """

        val = dt.isoformat()
        val = val.replace("-", "")
        val = val.replace(":", "")

        if not dt.tzname():
                # Assume UTC.
                val += "Z"
        return val

def datetime_to_update_ts(dt):
        """Take datetime object dt, and convert it to a ts in ISO-8601
        basic partial format. """

        val = dt.isoformat()
        val = val.replace("-", "")
        # Drop the minutes and seconds portion.
        val = val.rsplit(":", 2)[0]
        val = val.replace(":", "")

        if not dt.tzname():
                # Assume UTC.
                val += "Z"
        return val

def now_to_basic_ts():
        """Returns the current UTC time as timestamp in ISO-8601 basic
        format."""
        return datetime_to_basic_ts(datetime.datetime.utcnow())

def now_to_update_ts():
        """Returns the current UTC time as timestamp in ISO-8601 basic
        partial format."""
        return datetime_to_update_ts(datetime.datetime.utcnow())

def ts_to_datetime(ts):
        """Take timestamp ts in ISO-8601 format, and convert it to a
        datetime object."""

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
        return datetime.datetime(year, month, day, hour, minutes, sec, usec)

def basic_ts_to_datetime(ts):
        """Take timestamp ts in ISO-8601 basic format, and convert it to a
        datetime object."""

        year = int(ts[0:4])
        month = int(ts[4:6])
        day = int(ts[6:8])
        hour = int(ts[9:11])
        minutes = int(ts[11:13])
        sec = int(ts[13:15])
        # usec is not in the string if 0
        try:
                usec = int(ts[16:22])
        except ValueError:
                usec = 0
        return datetime.datetime(year, month, day, hour, minutes, sec, usec)

def update_ts_to_datetime(ts):
        """Take timestamp ts in ISO-8601 basic partial format, and convert it
        to a datetime object."""

        year = int(ts[0:4])
        month = int(ts[4:6])
        day = int(ts[6:8])
        hour = int(ts[9:11])
        return datetime.datetime(year, month, day, hour)

def extract_matching_fmris(pkgs, patterns=None, matcher=None,
    constraint=None, counthash=None, reverse=True, versions=None):
        """Iterate through the given list of PkgFmri objects,
        looking for packages matching 'pattern' in 'patterns', based on the
        function in 'matcher' and the versioning constraint described by
        'constraint'.  If 'matcher' is None, uses fmri subset matching
        as the default.  If 'patterns' is None, 'versions' may be specified,
        and looks for packages matching the patterns specified in 'versions'.
        When using 'versions', the 'constraint' parameter is ignored.

        'versions' should be a list of strings of the format:
            release,build_release-branch:datetime

        ...with a value of '*' provided for any component to be ignored. '*' or
        '?' may be used within each component value and will act as wildcard
        characters ('*' for one or more characters, '?' for a single character).

        'reverse' is an optional boolean value indicating whether results
        should be in descending name and version order.  If false, results
        will be in ascending name, descending version order.

        If 'counthash' is a dictionary, instead store the number of matched
        fmris for each package that matches."""

        if not matcher:
                matcher = fmri.fmri_match

        if patterns is None:
                patterns = []
        elif not isinstance(patterns, list):
                patterns = [ patterns ]

        if versions is None:
                versions = []
        elif not isinstance(versions, list):
                versions = [ pkg.version.MatchingVersion(versions, None) ]
        else:
                for i, ver in enumerate(versions):
                        versions[i] = pkg.version.MatchingVersion(ver, None)

        # 'pattern' may be a partially or fully decorated fmri; we want
        # to extract its name and version to match separately against
        # the catalog.
        tuples = {}

        if patterns:
                matched = {
                    "matcher": set(),
                    "publisher": set(),
                    "version": set(),
                }
        elif versions:
                matched = {
                    "version": set(),
                }

        for pattern in patterns:
                if isinstance(pattern, fmri.PkgFmri):
                        tuples[pattern] = pattern.tuple()
                else:
                        assert pattern != None
                        # XXX "5.11" here needs to be saner
                        tuples[pattern] = \
                            fmri.PkgFmri(pattern, "5.11").tuple()

        def by_pattern(p):
                cat_pub, cat_name = p.tuple()[:2]
                pat_match = False
                for pattern in patterns:
                        pat_pub, pat_name, pat_version = tuples[pattern]

                        if not pat_pub or fmri.is_same_publisher(pat_pub,
                            cat_pub):
                                matched["publisher"].add(pattern)
                        else:
                                continue

                        if matcher(cat_name, pat_name):
                                matched["matcher"].add(pattern)
                        else:
                                continue

                        if not pat_version or (p.version.is_successor(
                            pat_version, constraint) or \
                            p.version == pat_version):
                                matched["version"].add(pattern)
                        else:
                                continue

                        if counthash is not None:
                                counthash.setdefault(pattern, 0)
                                counthash[pattern] += 1
                        pat_match = True

                if pat_match:
                        return p

        def by_version(p):
                pat_match = False
                for ver in versions:
                        if p.version == ver:
                                matched["version"].add(ver)
                                if counthash is not None:
                                        sver = str(ver)
                                        if sver in counthash:
                                                counthash[sver] += 1
                                        else:
                                                counthash[sver] = 1
                                pat_match = True
                if pat_match:
                        return p

        ret = []
        if patterns:
                unmatched = copy.deepcopy(matched)
                for pattern in patterns:
                        for k in unmatched:
                                unmatched[k].add(pattern)

                for p in pkgs:
                        res = by_pattern(p)
                        if res:
                                ret.append(res)
        elif versions:
                unmatched = copy.deepcopy(matched)
                for ver in versions:
                        for k in unmatched:
                                unmatched[k].add(ver)

                for p in pkgs:
                        res = by_version(p)
                        if res:
                                ret.append(res)
        else:
                # No patterns and no versions means that no filtering can be
                # applied.  It seems silly to call this function in that case,
                # but the caller will get what it asked for...
                ret = list(pkgs)

        if patterns or versions:
                match_types = unmatched.keys()
                for k in match_types:
                        # The transformation back to list is important as the
                        # unmatched results will likely be used to raise an
                        # InventoryException which expects lists.
                        unmatched[k] = list(unmatched[k] - matched[k])
                        if not unmatched[k]:
                                del unmatched[k]
                                continue
                if not unmatched:
                        unmatched = None
        else:
                unmatched = None

        if not reverse:
                def order(a, b):
                        res = cmp(a.pkg_name, b.pkg_name)
                        if res != 0:
                                return res
                        res = cmp(a.version, b.version) * -1
                        if res != 0:
                                return res
                        return cmp(a.publisher, b.publisher)
                ret.sort(cmp=order)
        else:
                ret.sort(reverse=True)

        return ret, unmatched
